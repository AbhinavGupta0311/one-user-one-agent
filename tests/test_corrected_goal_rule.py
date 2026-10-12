"""
Test suite for Dynamically Corrected Goal Rules.
Verifies mid-stream correction applies cleanly without full reprocessing.
"""
from datetime import datetime
from src.core.models import Event, ViewerProfile
from src.goals.catalogue import GoalCatalogue

def test_goal_rule_dynamic_patch_and_attribution():
    catalog = GoalCatalogue()
    now = datetime(2026, 8, 15, 12, 0, 0)
    profile = ViewerProfile(viewer_id="V-RULE-TEST", subscription_status="trial")

    # Initial rule
    goal_initial = catalog.get_goal("G02_first_paid_plan_7d")
    assert goal_initial.rule_version == 1
    assert goal_initial.success_signal == "purchase_confirmed"

    # Patch rule mid-flight
    catalog.patch_goal_rule(
        goal_id="G02_first_paid_plan_7d",
        new_rule_id="G02-r2-verified-paid",
        updated_success_signal="purchase_confirmed_non_refunded",
        reason="Reject refunded test purchases"
    )

    goal_updated = catalog.get_goal("G02_first_paid_plan_7d")
    assert goal_updated.rule_version == 2
    assert goal_updated.success_signal == "purchase_confirmed_non_refunded"
    assert goal_updated.eligibility_rule_id == "G02-r2-verified-paid"

def test_missing_telemetry_signal_rejection():
    """
    Goal G11 (Social Watch Room) cannot be observed in telemetry stream.
    The catalogue must reject eligibility to prevent hallucinated success.
    """
    catalog = GoalCatalogue()
    now = datetime(2026, 8, 15, 12, 0, 0)
    profile = ViewerProfile(viewer_id="V-MISS-SIGNAL", subscription_status="trial")

    is_elig, reason, ev = catalog.evaluate_eligibility(
        goal_id="G11_social_group_watch_4d",
        profile=profile,
        history_events=[],
        now=now
    )
    assert is_elig is False
    assert "telemetry signal" in reason
    assert "absent from event stream" in reason
