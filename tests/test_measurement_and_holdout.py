"""
Test suite for Causal Measurement and Holdout Evaluation.
Proves that Intent-to-Treat (ITT) against randomized holdout isolates true causal uplift,
while naive served vs unserved comparison suffers from extreme activity selection bias.
"""
from datetime import datetime
from src.core.models import ViewerProfile, DecisionOutput, TriggerInfo, ConflictResolution, VerificationCheckResult
from src.storage.state_store import StateStore
from src.measurement.evaluator import CausalImpactEvaluator

def test_causal_evaluator_and_selection_bias(tmp_path):
    store = StateStore(storage_dir=str(tmp_path / "state"))
    now = datetime(2026, 8, 15, 12, 0, 0)

    # 1. Create Control Holdout Viewers (20 viewers, 4 organic conversions = 20%)
    for i in range(1, 21):
        vid = f"V-CTRL-{i:03d}"
        prof = ViewerProfile(viewer_id=vid, is_holdout=True, subscription_status="paid" if i <= 4 else "trial")
        st = store.get_or_create(vid, default_profile=prof)
        st.profile = prof
        store.save(st)

    # 2. Create Treatment Viewers (80 viewers, 24 conversions = 30%)
    # - 40 are active served (20 convert = 50%)
    # - 40 are unserved/dormant (4 convert = 10%)
    for i in range(1, 81):
        vid = f"V-TRT-{i:03d}"
        is_served = (i <= 40)
        has_converted = (i <= 20) or (41 <= i <= 44)
        status = "paid" if has_converted else "trial"
        prof = ViewerProfile(viewer_id=vid, is_holdout=False, subscription_status=status)
        st = store.get_or_create(vid, default_profile=prof)
        st.profile = prof
        if is_served:
            st.decisions.append(DecisionOutput(
                decision_id=f"D-TRT-{i}",
                viewer_id=vid,
                trigger=TriggerInfo(event="app_open", received_at=now.isoformat(), event_age_s=1.0),
                action="HOME_PAGE",
                dialect=ConflictResolution(used="d1", source="profile"),
                content=["title:T0001", "title:T0002", "title:T0003"],
                confidence=0.8,
                confidence_reason="Test served",
                checks=VerificationCheckResult(passed=["all"]),
                decided_in_ms=10.0,
                status="PUBLISHED"
            ))
        store.save(st)

    evaluator = CausalImpactEvaluator(store)
    res = evaluator.evaluate()

    # Control rate should be exactly 20% (4 / 20)
    assert res["rates"]["control_conversion_rate"] == 0.20
    # Treatment rate should be exactly 30% (24 / 80)
    assert res["rates"]["treatment_conversion_rate"] == 0.30
    
    # Honest Causal ITT Absolute Uplift = 30% - 20% = +10%
    assert res["honest_causal_itt"]["absolute_uplift"] == 0.10
    assert res["honest_causal_itt"]["relative_uplift_pct"] == 50.0

    # Naive Comparison: Served (50%) vs Unserved (10%) = +40%
    assert res["rates"]["served_conversion_rate"] == 0.50
    assert res["rates"]["unserved_conversion_rate"] == 0.10
    assert res["flawed_naive_comparison"]["naive_absolute_diff"] == 0.40
    assert res["flawed_naive_comparison"]["naive_relative_diff_pct"] == 400.0

    # Naive comparison inflates uplift by 8x!
    assert res["flawed_naive_comparison"]["bias_multiplier"] == 8.0
