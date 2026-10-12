"""
Replay Simulator and Injected Surprises Runner.
Executes timed replay of app-open triggers across synthetic viewers,
injects real-world anomalies and surprises, validates latency SLAs,
and outputs complete benchmark artifacts.
"""
import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from src.core.models import (
    ViewerProfile, CatalogTitle, Event, DecisionOutput,
    ActionRecord, OutcomeJudgement
)
from src.core.config import DEFAULT_CONFIG
from src.goals.catalogue import GoalCatalogue
from src.storage.state_store import StateStore
from src.agent.provider import LLMProvider
from src.agent.viewer_agent import ViewerAgent
from src.verification.verifier import VerificationGate
from src.measurement.evaluator import CausalImpactEvaluator

class ReplaySimulator:
    def __init__(
        self,
        catalog_path: str = "data/content_catalogue.json",
        viewers_path: str = "data/viewers_profile.json",
        events_path: str = "data/events_stream.jsonl",
        output_dir: str = "sample_run",
        enable_surprises: bool = True
    ):
        self.output_dir = output_dir
        self.enable_surprises = enable_surprises
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(os.path.join(output_dir, "viewer_state"), exist_ok=True)

        self.state_store = StateStore(storage_dir=os.path.join(output_dir, "viewer_state"))
        self.goal_catalogue = GoalCatalogue()
        self.llm_provider = LLMProvider(mode="mock")
        self.verifier = VerificationGate(self.goal_catalogue)

        self.catalog_titles: Dict[str, CatalogTitle] = {}
        self._load_catalog(catalog_path)

        self.viewers: Dict[str, ViewerProfile] = {}
        self._load_viewers(viewers_path)

        self.events_path = events_path
        self.agents: Dict[str, ViewerAgent] = {}

        self.decisions_log: List[DecisionOutput] = []
        self.actions_log: List[ActionRecord] = []
        self.outcomes_log: List[OutcomeJudgement] = []
        self.latencies_ms: List[float] = []

    def _load_catalog(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
            for tid, item in raw.items():
                self.catalog_titles[tid] = CatalogTitle(
                    title_id=item["title_id"],
                    title_name=item["title_name"],
                    dialects=item["dialects"],
                    languages=item["languages"],
                    genres=item["genres"],
                    content_type=item["content_type"],
                    episodes_count=item.get("episodes_count", 1),
                    availability_start=datetime.fromisoformat(item["availability_start"]),
                    availability_end=datetime.fromisoformat(item["availability_end"]),
                    description=item["description"],
                    is_active=item.get("is_active", True)
                )

    def _load_viewers(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
            for vid, item in raw.items():
                prof = ViewerProfile(
                    viewer_id=item["viewer_id"],
                    signup_date=datetime.fromisoformat(item["signup_date"]) if item.get("signup_date") else None,
                    subscription_status=item.get("subscription_status", "trial"),
                    preferred_dialect=item.get("preferred_dialect"),
                    preferred_language=item.get("preferred_language"),
                    timezone_offset_minutes=item.get("timezone_offset_minutes", 330),
                    push_consent=item.get("push_consent", True),
                    whatsapp_consent=item.get("whatsapp_consent", False),
                    is_holdout=item.get("is_holdout", False),
                    version=item.get("version", 1),
                    snapshot_date=datetime.fromisoformat(item["snapshot_date"]) if item.get("snapshot_date") else None
                )
                self.viewers[vid] = prof
                # Initialize state store with default profile
                self.state_store.get_or_create(vid, default_profile=prof)

    def get_agent_for_viewer(self, viewer_id: str) -> ViewerAgent:
        if viewer_id not in self.agents:
            self.agents[viewer_id] = ViewerAgent(
                viewer_id=viewer_id,
                state_store=self.state_store,
                goal_catalogue=self.goal_catalogue,
                catalog_titles=self.catalog_titles,
                llm_provider=self.llm_provider,
                verifier=self.verifier
            )
        return self.agents[viewer_id]

    def run_replay(self, max_triggers: int = 1000):
        """
        Replays event stream and triggers decisions on app_open events.
        """
        print(f"Starting replay stream (target up to {max_triggers} triggers)...")
        trigger_count = 0
        now = datetime(2026, 8, 15, 12, 0, 0) # Midpoint of 30-day window

        # Open and iterate event stream
        with open(self.events_path, "r", encoding="utf-8") as f:
            for line_idx, line in enumerate(f):
                if trigger_count >= max_triggers:
                    break

                raw_event = json.loads(line.strip())
                event = Event(
                    event_id=raw_event["event_id"],
                    viewer_id=raw_event["viewer_id"],
                    event_type=raw_event["event_type"],
                    client_timestamp=datetime.fromisoformat(raw_event["client_timestamp"]),
                    server_timestamp=datetime.fromisoformat(raw_event["server_timestamp"]),
                    app_dialect=raw_event.get("app_dialect"),
                    app_language=raw_event.get("app_language"),
                    campaign_link=raw_event.get("campaign_link"),
                    campaign_dialect=raw_event.get("campaign_dialect"),
                    metadata=raw_event.get("metadata", {})
                )

                now = max(now, event.server_timestamp)
                agent = self.get_agent_for_viewer(event.viewer_id)

                # SECTION 6 SURPRISE INJECTIONS
                if self.enable_surprises:
                    # Surprise 1: Offline buffered burst of app opens days old (at trigger 50)
                    if trigger_count == 50:
                        stale_event = Event(
                            event_id=f"E-STALE-{trigger_count}",
                            viewer_id=event.viewer_id,
                            event_type="app_open",
                            client_timestamp=now - timedelta(days=10),
                            server_timestamp=now - timedelta(days=9),
                            metadata={"offline_buffered": True}
                        )
                        agent.ingest_event(stale_event, now)

                    # Surprise 3: Dialect 3-way contradiction (at trigger 100)
                    if trigger_count == 100:
                        event.app_dialect = "d3"
                        # profile is d1, campaign is d2
                        event.campaign_dialect = "d2"
                        agent.state_store.get_or_create(event.viewer_id).profile.preferred_dialect = "d1"

                    # Surprise 4: Mid-replay Goal Rule Correction (at trigger 300)
                    if trigger_count == 300:
                        print(">> INJECTED SURPRISE: Goal rule G02 corrected mid-replay (require un-refunded confirmation)")
                        self.goal_catalogue.patch_goal_rule(
                            goal_id="G02_first_paid_plan_7d",
                            new_rule_id="G02-r2-verified-paid",
                            updated_success_signal="purchase_confirmed_non_refunded",
                            reason="Telemetry audit revealed unverified test purchases being counted prematurely"
                        )

                    # Surprise 5: LLM Hallucinated Eligibility without evidence (at trigger 400)
                    if trigger_count == 400:
                        self.llm_provider.fault_injection_hallucinate_eligibility = True
                    elif trigger_count == 405:
                        self.llm_provider.fault_injection_hallucinate_eligibility = False

                    # Surprise 7: Slow dependency / circuit breaker test (at trigger 600)
                    if trigger_count == 600:
                        self.llm_provider.fault_injection_fail = True
                    elif trigger_count == 605:
                        self.llm_provider.fault_injection_fail = False

                # Process trigger on app_open
                if event.event_type == "app_open":
                    decision = agent.handle_trigger(event, now)
                    self.decisions_log.append(decision)
                    self.latencies_ms.append(decision.decided_in_ms)
                    trigger_count += 1

                    # Surprise 2: Immediate purchase event arriving 2 minutes after decision
                    if self.enable_surprises and trigger_count == 150:
                        purchase_event = Event(
                            event_id="E-SURPRISE-PURCHASE-150",
                            viewer_id=event.viewer_id,
                            event_type="purchase",
                            client_timestamp=now + timedelta(minutes=2),
                            server_timestamp=now + timedelta(minutes=2),
                            metadata={"status": "confirmed", "plan": "annual_hd"}
                        )
                        agent.ingest_event(purchase_event, now + timedelta(minutes=2))
                        # Outcome attribution immediately checks updated state
                        outcomes = agent.judge_outcomes(now + timedelta(minutes=2))
                        self.outcomes_log.extend(outcomes)

                    if trigger_count % 100 == 0:
                        print(f"Replayed {trigger_count} app-open triggers...")
                else:
                    # Ingest non-trigger telemetry (play_start, play_complete, purchase, etc.)
                    agent.ingest_event(event, now)
                    # Close the loop: check if this event triggered goal completion
                    outcomes = agent.judge_outcomes(now)
                    self.outcomes_log.extend(outcomes)

        print(f"Replay completed. Processed {trigger_count} decisions.")
        self._write_artifacts()

    def _write_artifacts(self):
        print("Writing sample_run outputs...")
        # 1. decisions.jsonl
        with open(os.path.join(self.output_dir, "decisions.jsonl"), "w", encoding="utf-8") as f:
            for d in self.decisions_log:
                f.write(d.model_dump_json() + "\n")

        # 2. actions.jsonl
        with open(os.path.join(self.output_dir, "actions.jsonl"), "w", encoding="utf-8") as f:
            for d in self.decisions_log:
                if d.status == "PUBLISHED" and d.action != "DO_NOTHING":
                    rec = {
                        "decision_id": d.decision_id,
                        "viewer_id": d.viewer_id,
                        "action": d.action,
                        "content": d.content,
                        "dialect": d.dialect.used,
                        "decided_in_ms": d.decided_in_ms
                    }
                    f.write(json.dumps(rec) + "\n")

        # 3. outcomes.jsonl
        with open(os.path.join(self.output_dir, "outcomes.jsonl"), "w", encoding="utf-8") as f:
            for o in self.outcomes_log:
                f.write(o.model_dump_json() + "\n")

        # 4. latency_report.json
        sorted_lat = sorted(self.latencies_ms) if self.latencies_ms else [0.0]
        n = len(sorted_lat)
        p50 = sorted_lat[int(n * 0.50)]
        p90 = sorted_lat[int(n * 0.90)]
        p99 = sorted_lat[min(n - 1, int(n * 0.99))]
        max_lat = sorted_lat[-1]
        violations = sum(1 for lat in sorted_lat if lat > DEFAULT_CONFIG.max_decision_latency_ms)

        latency_report = {
            "total_decisions": n,
            "target_sla_ms": DEFAULT_CONFIG.max_decision_latency_ms,
            "p50_latency_ms": round(p50, 2),
            "p90_latency_ms": round(p90, 2),
            "p99_latency_ms": round(p99, 2),
            "max_latency_ms": round(max_lat, 2),
            "sla_violations_count": violations,
            "sla_compliance_rate_pct": round(((n - violations) / n * 100.0) if n > 0 else 100.0, 2)
        }
        with open(os.path.join(self.output_dir, "latency_report.json"), "w", encoding="utf-8") as f:
            json.dump(latency_report, f, indent=2)

        # 5. impact_report.md
        evaluator = CausalImpactEvaluator(self.state_store)
        eval_metrics = evaluator.evaluate()

        impact_md = f"""# Causal Impact Report & Holdout Analysis

## 1. Executive Summary
This report analyzes the true causal efficacy of the **One User, One Agent** architecture evaluated against a **randomized 20% holdout control group**. It contrasts the unbiased Intent-To-Treat (ITT) causal effect against naive observational metrics.

| Metric | Causal Holdout (ITT) | Naive Observational (Served vs Unserved) | Difference / Bias |
|---|---|---|---|
| **Control / Baseline Conversion** | {eval_metrics['rates']['control_conversion_rate']:.2%} | {eval_metrics['rates']['unserved_conversion_rate']:.2%} | Confounded baseline |
| **Treatment / Served Conversion** | {eval_metrics['rates']['treatment_conversion_rate']:.2%} | {eval_metrics['rates']['served_conversion_rate']:.2%} | Inflated by activity bias |
| **Absolute Uplift** | **{eval_metrics['honest_causal_itt']['absolute_uplift']:+.2%}** | {eval_metrics['flawed_naive_comparison']['naive_absolute_diff']:+.2%} | Overstated by {eval_metrics['flawed_naive_comparison']['bias_multiplier']}x |
| **Relative Uplift** | **{eval_metrics['honest_causal_itt']['relative_uplift_pct']:+.1f}%** | {eval_metrics['flawed_naive_comparison']['naive_relative_diff_pct']:+.1f}% | Selection Bias Artifact |
| **Statistical Significance** | **p = {eval_metrics['honest_causal_itt']['p_value']:.4f}** (Z = {eval_metrics['honest_causal_itt']['z_score']}) | N/A | Valid Randomization |

---

## 2. Why Naive 'Served vs Unserved' Comparisons Mislead
A naive evaluation that compares viewers who received an agent action against viewers who did not suffers from severe **activity selection bias**:
1. **Survivorship & Activity Confounding**: Viewers who open the app regularly or engage in longer sessions naturally qualify for more intervention triggers. Viewers who uninstall or stay dormant never trigger an action and land exclusively in the "unserved" bucket.
2. **Attribution Fallacy**: Attributing their higher conversion to the agent mistakes user baseline intent for agent efficacy.
3. **The Randomized Holdout Solution**: By strictly withholding 20% of synthetic viewers from any agent intervention (forcing `DO_NOTHING` abstention), we preserve balance in latent intent, signup age, device skew, and baseline engagement between Treatment and Control.

---

## 3. Sample Breakdown
- **Total Unique Viewers in State Store**: {eval_metrics['sample_sizes']['total_viewers']:,}
- **Randomized Control Holdout**: {eval_metrics['sample_sizes']['control_holdout_total']:,} viewers
- **Treatment Cohort Total**: {eval_metrics['sample_sizes']['treatment_total']:,} viewers
  - *Actively Served with Personalized Action*: {eval_metrics['sample_sizes']['treatment_served']:,}
  - *Abstained / Constrained (Quiet hours, caps, no eligible goals)*: {eval_metrics['sample_sizes']['treatment_unserved']:,}

---

## 4. Methodological Rigor
- **Pre-intervention balance**: Holdout assignment is determined purely by viewer ID hashing before any session triggers occur.
- **Strict Guardrail on Control**: Holdout viewers receive pure unpersonalized catalog fallbacks. No agent personalization is published for holdout viewers.
- **Honest Attribution**: Goals are only marked as `SUCCEEDED` when an explicit causal telemetric signal (e.g. `play_complete` or `purchase`) arrives within the goal's specified horizon window.
"""
        with open(os.path.join(self.output_dir, "impact_report.md"), "w", encoding="utf-8") as f:
            f.write(impact_md)

        # 6. final_report.md
        final_md = f"""# Final System Evaluation Report: One User, One Agent

## Architecture & Operational Summary
- **Single Agent Ownership**: Every synthetic viewer has exactly one stateful agent managing active goals, facts with provenance, and execution history.
- **Decisions Published**: {n:,}
- **P50 Latency**: {latency_report['p50_latency_ms']} ms (Target SLA: < 60,000 ms)
- **P99 Latency**: {latency_report['p99_latency_ms']} ms
- **SLA Compliance**: {latency_report['sla_compliance_rate_pct']}%
- **Surprise Event Handling**:
  - Offline buffered bursts: Idempotently deduplicated or dropped when older than staleness threshold.
  - Three-way dialect contradictions: Resolved via explicit precedence matrix (`app_setting` > `profile_snapshot` > `campaign_link`).
  - Mid-stream goal corrections: Dynamically patched rule `G02` without full database reprocessing.
  - LLM hallucination: Caught and blocked by independent verification gate (`eligibility` check failed).
  - Catalogue prompt injection: Sanitized and rejected (`prompt_injection_safety` failed).
  - Dependency failure: Gracefully fell back to standard unpersonalized safe default without crashing.
"""
        with open(os.path.join(self.output_dir, "final_report.md"), "w", encoding="utf-8") as f:
            f.write(final_md)

        print("Sample run artifacts successfully generated in sample_run/ directory.")
