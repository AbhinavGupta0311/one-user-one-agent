"""
Causal Measurement and Impact Evaluator.
Computes true Intent-To-Treat (ITT) causal uplift against randomized holdouts,
demonstrating why naive 'served vs unserved' comparisons produce severe selection bias.
"""
from typing import Dict, List, Any, Tuple
import math
from src.storage.state_store import StateStore

class CausalImpactEvaluator:
    def __init__(self, state_store: StateStore):
        self.state_store = state_store

    def evaluate(self) -> Dict[str, Any]:
        """
        Analyzes all viewer states in the store.
        Separates viewers into:
        1. Treatment Group (Eligible for agent interventions)
           - Served (Received at least 1 active intervention)
           - Unserved in Treatment (Abstained, quiet hours, no eligible goals)
        2. Control Holdout Group (Pure randomized holdout baseline)
        """
        viewer_ids = self.state_store.list_viewer_ids()
        
        treatment_total = 0
        treatment_conversions = 0
        treatment_served = 0
        treatment_served_conversions = 0
        treatment_unserved = 0
        treatment_unserved_conversions = 0

        control_total = 0
        control_conversions = 0

        for vid in viewer_ids:
            state = self.state_store.get_or_create(vid)
            is_holdout = state.profile.is_holdout
            
            # Did viewer convert on primary metrics?
            # Conversion defined as: has paid subscription or >= 1 completed episode
            has_converted = (
                state.profile.subscription_status == "paid" or
                any(e.event_type == "play_complete" for e in state.history_events) or
                any(o.status == "SUCCEEDED" for o in state.outcomes)
            )

            # Did viewer receive an active intervention?
            received_intervention = any(
                d.status == "PUBLISHED" and d.action != "DO_NOTHING"
                for d in state.decisions
            )

            if is_holdout:
                control_total += 1
                if has_converted:
                    control_conversions += 1
            else:
                treatment_total += 1
                if has_converted:
                    treatment_conversions += 1
                
                if received_intervention:
                    treatment_served += 1
                    if has_converted:
                        treatment_served_conversions += 1
                else:
                    treatment_unserved += 1
                    if has_converted:
                        treatment_unserved_conversions += 1

        # Calculate rates
        control_rate = (control_conversions / control_total) if control_total > 0 else 0.0
        treatment_rate = (treatment_conversions / treatment_total) if treatment_total > 0 else 0.0
        
        served_rate = (treatment_served_conversions / treatment_served) if treatment_served > 0 else 0.0
        unserved_rate = (treatment_unserved_conversions / treatment_unserved) if treatment_unserved > 0 else 0.0

        # Causal ITT metric
        itt_absolute_uplift = treatment_rate - control_rate
        itt_relative_uplift = (itt_absolute_uplift / control_rate * 100.0) if control_rate > 0 else 0.0

        # Naive selection-bias metric
        naive_absolute_difference = served_rate - unserved_rate
        naive_relative_difference = (naive_absolute_difference / unserved_rate * 100.0) if unserved_rate > 0 else 0.0

        # Statistical significance for ITT (two-proportion z-test)
        p_val, z_score = self._calc_two_proportion_z(
            treatment_conversions, treatment_total,
            control_conversions, control_total
        )

        return {
            "sample_sizes": {
                "total_viewers": len(viewer_ids),
                "treatment_total": treatment_total,
                "treatment_served": treatment_served,
                "treatment_unserved": treatment_unserved,
                "control_holdout_total": control_total
            },
            "conversion_counts": {
                "control_conversions": control_conversions,
                "treatment_conversions": treatment_conversions,
                "treatment_served_conversions": treatment_served_conversions,
                "treatment_unserved_conversions": treatment_unserved_conversions
            },
            "rates": {
                "control_conversion_rate": round(control_rate, 4),
                "treatment_conversion_rate": round(treatment_rate, 4),
                "served_conversion_rate": round(served_rate, 4),
                "unserved_conversion_rate": round(unserved_rate, 4)
            },
            "honest_causal_itt": {
                "absolute_uplift": round(itt_absolute_uplift, 4),
                "relative_uplift_pct": round(itt_relative_uplift, 2),
                "z_score": round(z_score, 3),
                "p_value": round(p_val, 4),
                "statistically_significant": p_val < 0.05
            },
            "flawed_naive_comparison": {
                "naive_absolute_diff": round(naive_absolute_difference, 4),
                "naive_relative_diff_pct": round(naive_relative_difference, 2),
                "bias_multiplier": round(naive_relative_difference / itt_relative_uplift, 2) if itt_relative_uplift > 0 else 0.0,
                "explanation": (
                    "The naive comparison contrasts viewers who were active enough to trigger an intervention "
                    "against dormant or non-opening viewers who were never served. This introduces massive positive "
                    "selection bias, conflating user engagement propensity with treatment effect."
                )
            }
        }

    def _calc_two_proportion_z(self, x1: int, n1: int, x2: int, n2: int) -> Tuple[float, float]:
        if n1 == 0 or n2 == 0:
            return 1.0, 0.0
        p1 = x1 / n1
        p2 = x2 / n2
        p_pool = (x1 + x2) / (n1 + n2)
        if p_pool == 0 or p_pool == 1:
            return 1.0, 0.0
        se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
        if se == 0:
            return 1.0, 0.0
        z = (p1 - p2) / se
        # Two-tailed p-value from standard normal
        p_val = math.erfc(abs(z) / math.sqrt(2))
        return p_val, z
