"""
Independent Verification Gate.
Audits proposed decisions before publication.
NEVER trusts LLM claims as evidence or approval.
"""
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
from src.core.models import (
    DecisionOutput, ViewerProfile, CatalogTitle, Event,
    ActionRecord, VerificationCheckResult
)
from src.goals.catalogue import GoalCatalogue
from src.interventions.catalogue import InterventionCatalogue

class VerificationGate:
    """
    Independent verification gate enforcing trust boundaries.
    The decision engine proposes; the verification gate independently audits.
    """
    
    INJECTION_KEYWORDS = [
        "ignore previous instructions",
        "message every viewer",
        "bypass consent",
        "override safety",
        "send whatsapp to all",
        "grant free subscription"
    ]

    def __init__(self, goal_catalogue: GoalCatalogue):
        self.goal_catalogue = goal_catalogue

    def verify(
        self,
        proposed_goal_id: Optional[str],
        proposed_action: str,
        proposed_content_ids: List[str],
        resolved_dialect: str,
        profile: ViewerProfile,
        history_events: List[Event],
        catalog_titles: Dict[str, CatalogTitle],
        recent_actions: List[ActionRecord],
        now: datetime
    ) -> VerificationCheckResult:
        passed = []
        failed = []
        reasons = []

        # 1. Action validity
        if proposed_action not in InterventionCatalogue.ALLOWED_ACTIONS:
            failed.append("action_validity")
            reasons.append(f"Invalid proposed action: {proposed_action}")
        else:
            passed.append("action_validity")

        # 2. If action is DO_NOTHING, pass immediately without outbound/content checks
        if proposed_action == "DO_NOTHING":
            passed.append("abstention_safety")
            return VerificationCheckResult(
                passed=passed,
                failed=failed,
                rejection_reasons=reasons
            )

        # 3. Prompt Injection / Malicious Instruction Check on Title Descriptions
        injection_detected = False
        for cid in proposed_content_ids:
            title_key = cid.replace("title:", "")
            title = catalog_titles.get(title_key)
            if title:
                desc_lower = title.description.lower()
                for kw in self.INJECTION_KEYWORDS:
                    if kw in desc_lower:
                        injection_detected = True
                        break
        if injection_detected:
            failed.append("prompt_injection_safety")
            reasons.append("Malicious instruction or prompt injection attempt detected in catalog content description")
        else:
            passed.append("prompt_injection_safety")

        # 4. Independent Goal Eligibility Check
        if proposed_goal_id:
            is_eligible, elig_reason, elig_evidence = self.goal_catalogue.evaluate_eligibility(
                goal_id=proposed_goal_id,
                profile=profile,
                history_events=history_events,
                now=now
            )
            if not is_eligible:
                failed.append("eligibility")
                reasons.append(f"Independent eligibility check failed: {elig_reason}")
            else:
                passed.append("eligibility")
        else:
            # If proposing active intervention without a goal
            failed.append("eligibility")
            reasons.append("Active intervention proposed without an assigned goal")

        # 5. Outbound Consent Check
        consent_ok, consent_reason = InterventionCatalogue.check_consent(proposed_action, profile)
        if not consent_ok:
            failed.append("consent")
            reasons.append(consent_reason)
        else:
            passed.append("consent")

        # 6. Quiet Hours Check
        if proposed_action in InterventionCatalogue.OUTBOUND_CHANNELS:
            is_quiet, quiet_reason = InterventionCatalogue.is_quiet_hours(now, profile.timezone_offset_minutes)
            if is_quiet:
                failed.append("quiet_hours")
                reasons.append(quiet_reason)
            else:
                passed.append("quiet_hours")
        else:
            passed.append("quiet_hours")

        # 7. Frequency Cap Check
        fcap_ok, fcap_reason = InterventionCatalogue.check_frequency_cap(proposed_action, recent_actions, now)
        if not fcap_ok:
            failed.append("frequency_cap")
            reasons.append(fcap_reason)
        else:
            passed.append("frequency_cap")

        # 8. Dialect & Availability & Row Minimum Check
        titles_objects = []
        missing_titles = []
        for cid in proposed_content_ids:
            title_key = cid.replace("title:", "")
            if title_key in catalog_titles:
                t = catalog_titles[title_key]
                # Check window
                if t.availability_start <= now <= t.availability_end and t.is_active:
                    titles_objects.append(t)
                else:
                    reasons.append(f"Title {title_key} is outside availability window or inactive")
            else:
                missing_titles.append(title_key)

        if missing_titles:
            failed.append("content_catalog_presence")
            reasons.append(f"Titles not found in catalog: {missing_titles}")
        else:
            passed.append("content_catalog_presence")

        # Check content titles for dialect match
        non_matching_dialect_titles = [t.title_id for t in titles_objects if resolved_dialect not in t.dialects]
        if non_matching_dialect_titles:
            failed.append("dialect")
            reasons.append(f"Content titles {non_matching_dialect_titles} do not contain resolved dialect '{resolved_dialect}'")
        else:
            passed.append("dialect")

        # Check row sizing (HOME_PAGE requires >= 3 valid titles in dialect)
        row_ok, row_reason = InterventionCatalogue.validate_content_payload(
            proposed_action, titles_objects, resolved_dialect
        )
        if not row_ok:
            failed.append("row_constraints")
            reasons.append(row_reason)
        else:
            passed.append("row_constraints")

        # 9. Duplicate Action Check (idempotency safety)
        # If this exact action was already delivered in the current session (past 15 mins)
        fifteen_min_ago = now - timedelta(minutes=15)
        duplicate_recent = [
            a for a in recent_actions
            if a.channel == proposed_action and a.executed_at >= fifteen_min_ago
        ]
        if len(duplicate_recent) > 0 and proposed_action not in ["HOME_PAGE", "HERO_SLOT"]:
            failed.append("duplicate_action")
            reasons.append(f"Duplicate action {proposed_action} delivered within last 15 minutes")
        else:
            passed.append("duplicate_action")

        return VerificationCheckResult(
            passed=passed,
            failed=failed,
            rejection_reasons=reasons
        )
