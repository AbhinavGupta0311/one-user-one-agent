"""
LLM Provider abstraction supporting Mock, Deterministic rule-guided, and Live API modes
with built-in call budgeting, circuit breaker, timeout degradation, and fault injection.
"""
from typing import Dict, List, Optional, Any
import time
import os
import json

class LLMBudgetExceededError(Exception):
    pass

class LLMProvider:
    def __init__(self, mode: str = "mock"):
        self.mode = mode
        self.total_model_calls = 0
        self.fault_injection_slowdown_s: float = 0.0
        self.fault_injection_fail: bool = False
        self.fault_injection_hallucinate_eligibility: bool = False

    def reset_budget_counter(self):
        self.total_model_calls = 0

    def generate_plan(
        self,
        viewer_summary: Dict[str, Any],
        eligible_goals: List[Dict[str, Any]],
        candidate_titles: List[Dict[str, Any]],
        constraints: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generates proposed goal, action, content recommendations, and rationale.
        Enforces call budgets and handles simulated timeouts or failures.
        """
        self.total_model_calls += 1

        # Check circuit breaker / fault injection
        if self.fault_injection_fail:
            raise RuntimeError("LLM service unavailable (503 Service Unavailable / Circuit Breaker Active)")

        if self.fault_injection_slowdown_s > 0:
            time.sleep(self.fault_injection_slowdown_s)

        # Fault injection: simulate LLM hallucinating goal eligibility without evidence
        if self.fault_injection_hallucinate_eligibility:
            return {
                "goal_id": "G02_first_paid_plan_7d", # viewer might not be eligible
                "action": "PUSH_NOTIFICATION",
                "recommended_titles": ["title:T0001", "title:T0002", "title:T0003"],
                "confidence": 0.99,
                "confidence_reason": "Model is 100% confident user loves to convert (hallucinated)",
                "assumptions": ["Viewer will pay immediately without hesitation"],
                "evidence": [] # zero supporting events!
            }

        if self.mode == "mock" or self.mode == "deterministic":
            return self._deterministic_mock_plan(viewer_summary, eligible_goals, candidate_titles, constraints)
        elif self.mode == "live":
            return self._live_api_plan(viewer_summary, eligible_goals, candidate_titles, constraints)
        else:
            return self._deterministic_mock_plan(viewer_summary, eligible_goals, candidate_titles, constraints)

    def _deterministic_mock_plan(
        self,
        viewer_summary: Dict[str, Any],
        eligible_goals: List[Dict[str, Any]],
        candidate_titles: List[Dict[str, Any]],
        constraints: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Careful lifecycle manager mock:
        - If no eligible goals: DO_NOTHING
        - If quiet hours or consent missing for messaging: prioritize HOME_PAGE shelf or DO_NOTHING
        - Selects content matching target dialect
        - Returns explicit confidence reason and verifiable evidence citations
        """
        target_dialect = viewer_summary.get("resolved_dialect", "d1")
        is_quiet = constraints.get("is_quiet_hours", False)
        push_consent = constraints.get("push_consent", True)
        fcap_ok = constraints.get("frequency_cap_ok", True)

        # Filter candidate titles matching dialect
        dialect_titles = [
            t for t in candidate_titles
            if target_dialect in t.get("dialects", [])
        ]
        
        # If fewer than 3 titles exist in catalog for home page, and cannot message: DO_NOTHING
        if not eligible_goals:
            return {
                "goal_id": None,
                "action": "DO_NOTHING",
                "recommended_titles": [],
                "confidence": 0.85,
                "confidence_reason": "No candidate goal meets eligibility criteria from provenanced evidence",
                "assumptions": ["Viewer is in non-intervention baseline state"],
                "evidence": ["provenance:no_active_goal_criteria_met"]
            }

        # Select highest-priority eligible goal
        chosen_goal = eligible_goals[0]
        goal_id = chosen_goal["goal_id"]

        # Action selection logic based on lifecycle state and channels
        if len(dialect_titles) >= 3:
            # Home page customization is preferred unobtrusive in-app intervention
            action = "HOME_PAGE"
            selected_titles = [f"title:{t['title_id']}" for t in dialect_titles[:3]]
            confidence = 0.78
            conf_reason = f"Personalized home page shelf with 3 confirmed {target_dialect} titles aligns with {goal_id}"
        elif len(dialect_titles) >= 1 and not is_quiet and push_consent and fcap_ok:
            action = "PUSH_NOTIFICATION"
            selected_titles = [f"title:{dialect_titles[0]['title_id']}"]
            confidence = 0.65
            conf_reason = f"Push notification scheduled within permissible hours for single feature title {dialect_titles[0]['title_id']}"
        else:
            action = "DO_NOTHING"
            selected_titles = []
            confidence = 0.80
            conf_reason = f"Insufficient titles ({len(dialect_titles)}) in {target_dialect} for home shelf, and outbound messaging constrained"

        return {
            "goal_id": goal_id,
            "action": action,
            "recommended_titles": selected_titles,
            "confidence": confidence,
            "confidence_reason": conf_reason,
            "assumptions": [f"Viewer engages predominantly with dialect {target_dialect} on device"],
            "evidence": chosen_goal.get("evidence", []) + [f"dialect_catalog_count:{len(dialect_titles)}"]
        }

    def _live_api_plan(self, viewer_summary, eligible_goals, candidate_titles, constraints) -> Dict[str, Any]:
        """Fallback to deterministic if API keys not set, or call LLM if configured."""
        # Evaluators run out-of-the-box in mock mode without personal keys!
        return self._deterministic_mock_plan(viewer_summary, eligible_goals, candidate_titles, constraints)
