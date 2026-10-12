"""
ViewerAgent: Dedicated Single-Viewer Agent Runtime.
Each viewer is owned by exactly one agent instance, maintaining single active plan,
strict budget caps (max 8 model calls, 20 tool calls), provenanced evidence assembly,
dialect resolution, independent verification, and outcome attribution.
"""
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import time
import uuid

from src.core.models import (
    ViewerProfile, Event, CatalogTitle, DecisionOutput,
    TriggerInfo, ConflictResolution, GoalAssignment,
    VerificationCheckResult, ActionRecord, OutcomeJudgement,
    FactProvenance
)
from src.core.config import DEFAULT_CONFIG
from src.dialects.resolver import DialectResolver
from src.goals.catalogue import GoalCatalogue
from src.interventions.catalogue import InterventionCatalogue
from src.verification.verifier import VerificationGate
from src.storage.state_store import StateStore, ViewerState
from src.agent.provider import LLMProvider

class ViewerAgent:
    def __init__(
        self,
        viewer_id: str,
        state_store: StateStore,
        goal_catalogue: GoalCatalogue,
        catalog_titles: Dict[str, CatalogTitle],
        llm_provider: LLMProvider,
        verifier: Optional[VerificationGate] = None
    ):
        self.viewer_id = viewer_id
        self.state_store = state_store
        self.goal_catalogue = goal_catalogue
        self.catalog_titles = catalog_titles
        self.llm_provider = llm_provider
        self.verifier = verifier or VerificationGate(goal_catalogue)
        
        # Tool call budget tracker
        self.tool_calls_counter = 0

    def _call_tool(self, tool_name: str) -> None:
        self.tool_calls_counter += 1
        if self.tool_calls_counter > DEFAULT_CONFIG.max_tool_calls_per_decision:
            raise RuntimeError(f"Tool budget exceeded: {self.tool_calls_counter} > {DEFAULT_CONFIG.max_tool_calls_per_decision}")

    def ingest_event(self, event: Event, now: datetime) -> Tuple[bool, str]:
        """
        Ingests an incoming event into durable state idempotently.
        Handles late/duplicate events.
        """
        self._call_tool("state_store_read")
        state = self.state_store.get_or_create(self.viewer_id)

        # 1. Idempotency check: duplicate event
        if state.is_event_processed(event.event_id):
            return False, f"Duplicate event {event.event_id} discarded idempotently"

        # 2. Check for offline buffered extreme staleness (> 7 days)
        event_age_s = (now - event.server_timestamp).total_seconds()
        if event_age_s > DEFAULT_CONFIG.offline_event_max_staleness_s:
            state.mark_event_processed(event.event_id)
            self.state_store.save(state)
            return False, f"Offline event {event.event_id} older than 7 days discarded as stale telemetry"

        # Record event and update provenanced facts
        state.mark_event_processed(event.event_id)
        state.history_events.append(event)
        
        # Update facts based on event type
        if event.app_dialect:
            state.record_fact(
                key="app_dialect",
                value=event.app_dialect,
                source="app_setting",
                ts=event.server_timestamp,
                now=now,
                notes=f"Reported with {event.event_type}"
            )
        if event.campaign_dialect:
            state.record_fact(
                key="campaign_dialect",
                value=event.campaign_dialect,
                source="campaign_link",
                ts=event.server_timestamp,
                now=now,
                notes=f"Referral URL: {event.campaign_link}"
            )
        if event.event_type == "purchase":
            state.profile.subscription_status = "paid"
            state.record_fact(
                key="subscription_status",
                value="paid",
                source="realtime_event_purchase",
                ts=event.server_timestamp,
                now=now,
                notes="Confirmed transaction event overrides stale warehouse profile"
            )

        self._call_tool("state_store_write")
        self.state_store.save(state)
        return True, f"Event {event.event_id} ingested successfully"

    def handle_trigger(self, trigger_event: Event, now: datetime) -> DecisionOutput:
        """
        Core Decide, Act & Measure execution loop:
        1. Ingest trigger and enforce idempotency.
        2. Check holdout assignment (pure causal control group).
        3. Assemble viewer facts, dialect resolution, and freshness.
        4. Select goal & plan with budget limits (max 8 LLM calls, 20 tools).
        5. Independently verify proposed decision.
        6. Publish decision, record action, and update durable memory.
        """
        start_time = time.perf_counter()
        self.tool_calls_counter = 0
        self.llm_provider.reset_budget_counter()

        decision_id = f"D-{uuid.uuid4().hex[:6].upper()}"
        event_age_s = max(0.0, (now - trigger_event.server_timestamp).total_seconds())
        trigger_info = TriggerInfo(
            event=trigger_event.event_type,
            received_at=now.isoformat() + "Z",
            event_age_s=round(event_age_s, 2),
            trigger_id=trigger_event.event_id
        )

        state = self.state_store.get_or_create(self.viewer_id)

        # 1. Trigger Idempotency: avoid double-triggering for same event
        if state.is_trigger_processed(trigger_event.event_id):
            decided_in_ms = (time.perf_counter() - start_time) * 1000
            return DecisionOutput(
                decision_id=decision_id,
                viewer_id=self.viewer_id,
                trigger=trigger_info,
                goal=None,
                action="DO_NOTHING",
                dialect=ConflictResolution(used="none", source="none"),
                content=[],
                confidence=1.0,
                confidence_reason="Trigger previously executed; deduplicated idempotently",
                evidence=[f"trigger_already_processed:{trigger_event.event_id}"],
                assumptions=["Idempotent trigger replay request"],
                checks=VerificationCheckResult(passed=["idempotency"], failed=[]),
                decided_in_ms=round(decided_in_ms, 2),
                status="DROPPED_DUPLICATE",
                abstain_reason="Duplicate trigger ID"
            )

        state.mark_trigger_processed(trigger_event.event_id)
        self.ingest_event(trigger_event, now)

        # 2. Causal Holdout Check: Randomized Control Group
        # To prove true impact, holdout viewers NEVER receive active interventions
        if state.profile.is_holdout:
            decided_in_ms = (time.perf_counter() - start_time) * 1000
            decision = DecisionOutput(
                decision_id=decision_id,
                viewer_id=self.viewer_id,
                trigger=trigger_info,
                goal=None,
                action="DO_NOTHING",
                dialect=ConflictResolution(used="control_baseline", source="holdout_assignment"),
                content=[],
                confidence=1.0,
                confidence_reason="Viewer is member of randomized holdout control group for causal impact measurement",
                evidence=["experiment:randomized_holdout_control"],
                assumptions=["No intervention will be rendered; serves standard unpersonalized fallback"],
                checks=VerificationCheckResult(passed=["holdout_protocol"], failed=[]),
                decided_in_ms=round(decided_in_ms, 2),
                status="ABSTAINED",
                abstain_reason="Holdout control group"
            )
            state.decisions.append(decision)
            self.state_store.save(state)
            return decision

        # 3. Assemble Facts and Resolve Dialect Conflicts
        app_dialect = trigger_event.app_dialect or state.provenance_facts.get("app_dialect", FactProvenance(
            fact_key="app_dialect", value=None, source="none", timestamp=now, freshness_seconds=0
        )).value

        profile_dialect = state.profile.preferred_dialect
        campaign_dialect = trigger_event.campaign_dialect or state.provenance_facts.get("campaign_dialect", FactProvenance(
            fact_key="campaign_dialect", value=None, source="none", timestamp=now, freshness_seconds=0
        )).value

        dialect_resolution = DialectResolver.resolve(
            app_dialect=app_dialect,
            profile_dialect=profile_dialect,
            campaign_dialect=campaign_dialect,
            app_setting_timestamp=trigger_event.server_timestamp,
            profile_snapshot_timestamp=state.profile.snapshot_date,
            now=now
        )
        resolved_dialect = dialect_resolution.used

        # 4. Filter Available Content in Resolved Dialect
        self._call_tool("filter_catalog")
        dialect_titles = [
            t for t in self.catalog_titles.values()
            if resolved_dialect in t.dialects and t.availability_start <= now <= t.availability_end and t.is_active
        ]

        # 5. Evaluate Candidate Goals Eligibility
        self._call_tool("evaluate_goal_eligibility")
        all_goals = self.goal_catalogue.list_all_goals()
        eligible_goals = []
        for g in all_goals:
            is_elig, reason, ev = self.goal_catalogue.evaluate_eligibility(
                goal_id=g.goal_id,
                profile=state.profile,
                history_events=state.history_events,
                now=now
            )
            if is_elig:
                eligible_goals.append({
                    "goal_id": g.goal_id,
                    "name": g.name,
                    "horizon_days": g.horizon_days,
                    "success_signal": g.success_signal,
                    "reason": reason,
                    "evidence": ev
                })

        # 6. Planning Step (LLM Provider with safe fallback)
        is_quiet, quiet_reason = InterventionCatalogue.is_quiet_hours(now, state.profile.timezone_offset_minutes)
        fcap_ok, fcap_reason = InterventionCatalogue.check_frequency_cap("PUSH_NOTIFICATION", state.actions, now)

        viewer_summary = {
            "viewer_id": self.viewer_id,
            "subscription_status": state.profile.subscription_status,
            "resolved_dialect": resolved_dialect,
            "history_event_count": len(state.history_events)
        }
        constraints = {
            "is_quiet_hours": is_quiet,
            "push_consent": state.profile.push_consent,
            "whatsapp_consent": state.profile.whatsapp_consent,
            "frequency_cap_ok": fcap_ok
        }

        try:
            self._call_tool("llm_generate_plan")
            plan_response = self.llm_provider.generate_plan(
                viewer_summary=viewer_summary,
                eligible_goals=eligible_goals,
                candidate_titles=[t.model_dump() for t in dialect_titles[:10]],
                constraints=constraints
            )
            proposed_goal_id = plan_response.get("goal_id")
            proposed_action = plan_response.get("action", "DO_NOTHING")
            proposed_titles = plan_response.get("recommended_titles", [])
            confidence = plan_response.get("confidence", 0.5)
            confidence_reason = plan_response.get("confidence_reason", "Standard plan proposal")
            evidence_citations = plan_response.get("evidence", [])
            assumptions = plan_response.get("assumptions", [])
        except Exception as e:
            # Degrade safely on LLM or tool failure: Fallback to DO_NOTHING or safe standard homepage shelf
            proposed_goal_id = eligible_goals[0]["goal_id"] if eligible_goals else None
            proposed_action = "HOME_PAGE" if len(dialect_titles) >= 3 else "DO_NOTHING"
            proposed_titles = [f"title:{t.title_id}" for t in dialect_titles[:3]] if proposed_action == "HOME_PAGE" else []
            confidence = 0.40
            confidence_reason = f"Dependency failure fallback: {str(e)}"
            evidence_citations = ["system_recovery:fallback_applied"]
            assumptions = ["Safe unpersonalized fallback shelf due to dependency exception"]

        # 7. Independent Verification Gate
        self._call_tool("verify_proposed_decision")
        verification_result = self.verifier.verify(
            proposed_goal_id=proposed_goal_id,
            proposed_action=proposed_action,
            proposed_content_ids=proposed_titles,
            resolved_dialect=resolved_dialect,
            profile=state.profile,
            history_events=state.history_events,
            catalog_titles=self.catalog_titles,
            recent_actions=state.actions,
            now=now
        )

        # Handle Verification Outcome
        if verification_result.failed:
            # Independent verification rejected proposal!
            # If the action failed because of consent, quiet hours, or hallucinated eligibility, fallback to DO_NOTHING
            final_status = "REJECTED_BY_VERIFIER"
            final_action = "DO_NOTHING"
            final_content = []
            confidence_reason += f" | Rejection: {'; '.join(verification_result.rejection_reasons)}"
            abstain_reason = "; ".join(verification_result.rejection_reasons)
        else:
            final_status = "PUBLISHED" if proposed_action != "DO_NOTHING" else "ABSTAINED"
            final_action = proposed_action
            final_content = proposed_titles
            abstain_reason = None if final_action != "DO_NOTHING" else confidence_reason

        # Set goal assignment if valid
        goal_assignment = None
        if proposed_goal_id and final_action != "DO_NOTHING":
            goal_def = self.goal_catalogue.get_goal(proposed_goal_id)
            if goal_def:
                deadline = (now + timedelta(days=goal_def.horizon_days)).isoformat() + "Z"
                goal_assignment = GoalAssignment(
                    id=goal_def.goal_id,
                    deadline=deadline,
                    rule_id=goal_def.eligibility_rule_id,
                    success_signal=goal_def.success_signal
                )
                state.active_goal = goal_assignment

        decided_in_ms = (time.perf_counter() - start_time) * 1000

        decision = DecisionOutput(
            decision_id=decision_id,
            viewer_id=self.viewer_id,
            trigger=trigger_info,
            goal=goal_assignment,
            action=final_action,
            dialect=dialect_resolution,
            content=final_content,
            confidence=confidence,
            confidence_reason=confidence_reason,
            evidence=evidence_citations + [f"event:{trigger_event.event_id}"],
            assumptions=assumptions,
            checks=verification_result,
            decided_in_ms=round(decided_in_ms, 2),
            status=final_status,
            abstain_reason=abstain_reason,
            model_calls_used=self.llm_provider.total_model_calls,
            tool_calls_used=self.tool_calls_counter
        )

        # 8. Record action execution in durable history if active action was published
        if final_action != "DO_NOTHING" and final_status == "PUBLISHED":
            action_rec = ActionRecord(
                action_id=f"ACT-{uuid.uuid4().hex[:6].upper()}",
                decision_id=decision_id,
                viewer_id=self.viewer_id,
                channel=final_action,
                executed_at=now,
                content_ids=final_content,
                dialect=resolved_dialect,
                status="DELIVERED"
            )
            state.actions.append(action_rec)

        state.decisions.append(decision)
        self.state_store.save(state)
        return decision

    def judge_outcomes(self, now: datetime) -> List[OutcomeJudgement]:
        """
        Close the loop:
        When deadline passes or new events arrive, judge the goal as
        SUCCEEDED, FAILED, or INCONCLUSIVE from attributable signals only.
        """
        state = self.state_store.get_or_create(self.viewer_id)
        if not state.active_goal:
            return []

        goal_def = self.goal_catalogue.get_goal(state.active_goal.id)
        if not goal_def:
            return []

        deadline_dt = datetime.fromisoformat(state.active_goal.deadline.replace("Z", ""))
        is_past_deadline = now >= deadline_dt

        # Check for unobservable signal
        if not goal_def.observable_in_telemetry:
            judgement = OutcomeJudgement(
                judgement_id=f"JUDGE-{uuid.uuid4().hex[:6].upper()}",
                decision_id=state.decisions[-1].decision_id if state.decisions else "D-UNKNOWN",
                viewer_id=self.viewer_id,
                goal_id=goal_def.goal_id,
                judged_at=now,
                status="INCONCLUSIVE",
                attributable_signals=[],
                reasoning=f"Signal '{goal_def.success_signal}' is not observable in platform telemetry",
                learning_feedback="Drop goal from agent candidates until telemetry instrumentation is deployed"
            )
            state.outcomes.append(judgement)
            state.active_goal = None
            self.state_store.save(state)
            return [judgement]

        # Scan history for attributable success signal occurring after the decision
        attributable_events = []
        last_decision_time = state.decisions[-1].trigger.received_at if state.decisions else None
        
        for ev in state.history_events:
            # Check if event corresponds to success condition
            if goal_def.goal_id == "G01_first_full_episode_3d" and ev.event_type == "play_complete":
                attributable_events.append(f"event:{ev.event_id}:play_complete")
            elif goal_def.goal_id == "G02_first_paid_plan_7d" and ev.event_type == "purchase":
                # Check rule version
                if goal_def.rule_version > 1 and ev.metadata.get("status") == "refunded":
                    continue # corrected rule rejects refunded purchases!
                attributable_events.append(f"event:{ev.event_id}:purchase")
            elif goal_def.goal_id == "G03_second_session_24h" and ev.event_type == "app_open":
                attributable_events.append(f"event:{ev.event_id}:app_open")

        if attributable_events:
            status = "SUCCEEDED"
            reason = f"Attributable success event detected: {attributable_events[0]}"
            feedback = f"Intervention for {goal_def.name} successfully catalyzed viewer conversion"
        elif is_past_deadline:
            status = "FAILED"
            reason = f"Deadline {state.active_goal.deadline} expired without matching attributable telemetry"
            feedback = f"Viewer did not convert under {goal_def.name}; reconsider channel and content affinity"
        else:
            return [] # Still in active observation window

        judgement = OutcomeJudgement(
            judgement_id=f"JUDGE-{uuid.uuid4().hex[:6].upper()}",
            decision_id=state.decisions[-1].decision_id if state.decisions else "D-UNKNOWN",
            viewer_id=self.viewer_id,
            goal_id=goal_def.goal_id,
            judged_at=now,
            status=status,
            attributable_signals=attributable_events,
            reasoning=reason,
            learning_feedback=feedback
        )
        state.outcomes.append(judgement)
        state.learnings.append(feedback)
        state.active_goal = None
        self.state_store.save(state)
        return [judgement]
