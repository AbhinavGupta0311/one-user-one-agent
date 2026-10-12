"""
12 Candidate Goals Catalogue with eligibility rules, deadline calculations,
telemetry observability detection, and dynamic rule patching.
"""
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from src.core.models import GoalDefinition, GoalAssignment, Event, ViewerProfile

class GoalCatalogue:
    def __init__(self):
        self._goals: Dict[str, GoalDefinition] = {}
        self._initialize_goals()
        
    def _initialize_goals(self):
        definitions = [
            GoalDefinition(
                goal_id="G01_first_full_episode_3d",
                name="First Full Episode in 3 Days",
                description="Encourage new viewer to complete their first full episode.",
                horizon_days=3,
                success_signal="play_complete_first_episode",
                observable_in_telemetry=True,
                is_underspecified=False,
                eligibility_rule_id="G01-r1",
                rule_version=1
            ),
            GoalDefinition(
                goal_id="G02_first_paid_plan_7d",
                name="Convert to Paid Subscription within 7 Days",
                description="Move active trial or freemium viewer to a paid monthly or annual subscription.",
                horizon_days=7,
                success_signal="purchase_confirmed",
                observable_in_telemetry=True,
                is_underspecified=False,
                eligibility_rule_id="G02-r1",
                rule_version=1
            ),
            GoalDefinition(
                goal_id="G03_second_session_24h",
                name="Second Session Return within 24 Hours",
                description="Drive a returning visit within 24 hours of first session.",
                horizon_days=1,
                success_signal="app_open_within_24h",
                observable_in_telemetry=True,
                is_underspecified=False,
                eligibility_rule_id="G03-r1",
                rule_version=1
            ),
            GoalDefinition(
                goal_id="G04_complete_series_14d",
                name="Finish Multi-Episode Series within 14 Days",
                description="Drive episodic series completion for viewers who started episode 1 or 2.",
                horizon_days=14,
                success_signal="series_3_episodes_completed",
                observable_in_telemetry=True,
                is_underspecified=False,
                eligibility_rule_id="G04-r1",
                rule_version=1
            ),
            GoalDefinition(
                goal_id="G05_micro_drama_binge_48h",
                name="Micro-Drama Binge in 48 Hours",
                description="Guide viewers who watch snackable micro-dramas to complete 5+ episodes.",
                horizon_days=2,
                success_signal="micro_drama_5_episodes",
                observable_in_telemetry=True,
                is_underspecified=False,
                eligibility_rule_id="G05-r1",
                rule_version=1
            ),
            GoalDefinition(
                goal_id="G06_reactivate_dormant_7d",
                name="Reactivate Dormant Viewer within 7 Days",
                description="Re-engage viewers who have been absent for 7+ days with high-affinity titles.",
                horizon_days=7,
                success_signal="dormant_return_watch_gte_20m",
                observable_in_telemetry=True,
                is_underspecified=False,
                eligibility_rule_id="G06-r1",
                rule_version=1
            ),
            GoalDefinition(
                goal_id="G07_weekend_family_watch_3d",
                name="Weekend Family Feature Watch within 3 Days",
                description="Feature length family viewing during Friday through Sunday.",
                horizon_days=3,
                success_signal="play_feature_film",
                observable_in_telemetry=True,
                is_underspecified=False,
                eligibility_rule_id="G07-r1",
                rule_version=1
            ),
            GoalDefinition(
                goal_id="G08_explore_new_dialect_5d",
                name="Cross-Dialect Discovery within 5 Days",
                description="Broaden viewer taste to secondary regional dialect.",
                horizon_days=5,
                success_signal="play_secondary_dialect",
                observable_in_telemetry=True,
                is_underspecified=False,
                eligibility_rule_id="G08-r1",
                rule_version=1
            ),
            GoalDefinition(
                goal_id="G09_add_to_watchlist_2d",
                name="Add 2+ Titles to Watchlist within 48 Hours",
                description="Deepen catalog intent by encouraging watchlist additions.",
                horizon_days=2,
                success_signal="watchlist_added_gte_2",
                observable_in_telemetry=True,
                is_underspecified=False,
                eligibility_rule_id="G09-r1",
                rule_version=1
            ),
            GoalDefinition(
                goal_id="G10_share_referral_link_7d",
                name="Share Referral Link within 7 Days (Underspecified)",
                description="Viral growth sharing. Rule does not define if receiver click or signup is required.",
                horizon_days=7,
                success_signal="referral_shared_ambiguous",
                observable_in_telemetry=True,
                is_underspecified=True,
                underspecified_reason="Rule lacks specification whether raw link click or confirmed referral signup counts.",
                eligibility_rule_id="G10-r1",
                rule_version=1
            ),
            GoalDefinition(
                goal_id="G11_social_group_watch_4d",
                name="Social Watch Room Attendance (Missing Telemetry Signal)",
                description="Join synchronous watch room with peers. Signal missing from app telemetry.",
                horizon_days=4,
                success_signal="watch_room_attendance_unlogged",
                observable_in_telemetry=False,
                is_underspecified=False,
                underspecified_reason="Telemetric event stream does not capture watch room join/leave events.",
                eligibility_rule_id="G11-r1",
                rule_version=1
            ),
            GoalDefinition(
                goal_id="G12_download_offline_3d",
                name="Offline Download within 3 Days (Underspecified)",
                description="Download episode for offline commuting. Telemetry only captures download_started.",
                horizon_days=3,
                success_signal="download_started_vs_completed",
                observable_in_telemetry=True,
                is_underspecified=True,
                underspecified_reason="App logs download_started but omits download_finished_100% byte verification.",
                eligibility_rule_id="G12-r1",
                rule_version=1
            ),
        ]
        for g in definitions:
            self._goals[g.goal_id] = g

    def get_goal(self, goal_id: str) -> Optional[GoalDefinition]:
        return self._goals.get(goal_id)

    def list_all_goals(self) -> List[GoalDefinition]:
        return list(self._goals.values())

    def patch_goal_rule(self, goal_id: str, new_rule_id: str, updated_success_signal: str, reason: str):
        """Used during replay to test mid-flight goal rule corrections."""
        if goal_id in self._goals:
            goal = self._goals[goal_id]
            goal.eligibility_rule_id = new_rule_id
            goal.success_signal = updated_success_signal
            goal.rule_version += 1
            goal.description += f" [Updated v{goal.rule_version}: {reason}]"

    def evaluate_eligibility(
        self,
        goal_id: str,
        profile: ViewerProfile,
        history_events: List[Event],
        now: datetime
    ) -> Tuple[bool, str, List[str]]:
        """
        Evaluates eligibility deterministically based on real recorded evidence.
        Returns (is_eligible, reason, evidence_list).
        NEVER allows generated text or hallucination to fabricate eligibility.
        """
        goal = self._goals.get(goal_id)
        if not goal:
            return False, f"Unknown goal {goal_id}", []

        # Reject goals that cannot be observed in telemetry to prevent hallucinated success
        if not goal.observable_in_telemetry:
            return False, f"Goal {goal_id} rejected: telemetry signal '{goal.success_signal}' is absent from event stream", []

        # Reject underspecified goals unless strict fallback is configured
        if goal.is_underspecified:
            return False, f"Goal {goal_id} rejected: rule is underspecified ({goal.underspecified_reason})", []

        play_completes = [e for e in history_events if e.event_type == "play_complete"]
        play_starts = [e for e in history_events if e.event_type == "play_start"]
        purchases = [e for e in history_events if e.event_type == "purchase"]

        # Rule evaluation
        if goal_id == "G01_first_full_episode_3d":
            if profile.subscription_status in ["trial", "anonymous"]:
                if len(play_completes) == 0:
                    evidence = [f"event_count:play_complete=0", f"profile_status:{profile.subscription_status}"]
                    return True, "Viewer is trial/anonymous and has not finished any episode yet", evidence
            return False, "Viewer has already completed an episode or is not in trial", []

        elif goal_id == "G02_first_paid_plan_7d":
            # Viewer has not paid yet
            if profile.subscription_status != "paid" and len(purchases) == 0:
                evidence = [f"profile_status:{profile.subscription_status}", f"purchase_events={len(purchases)}"]
                return True, "Viewer has not subscribed and has 0 purchase events", evidence
            return False, "Viewer has already subscribed or made a purchase", []

        elif goal_id == "G03_second_session_24h":
            # Has 1 session recorded
            app_opens = [e for e in history_events if e.event_type == "app_open"]
            if len(app_opens) >= 1:
                evidence = [f"app_opens_count={len(app_opens)}", f"latest_open={app_opens[-1].event_id}"]
                return True, "Viewer has active initial session; eligible for 24h return goal", evidence
            return False, "Viewer has no prior recorded sessions", []

        elif goal_id == "G04_complete_series_14d":
            series_starts = [e for e in play_starts if e.metadata.get("content_type") == "series"]
            if len(series_starts) > 0 and len(play_completes) < 3:
                evidence = [f"series_starts={len(series_starts)}", f"play_completes={len(play_completes)}"]
                return True, "Viewer began a series and has remaining episodes to finish", evidence
            return False, "Viewer has not started a series or has already completed 3+ episodes", []

        elif goal_id == "G05_micro_drama_binge_48h":
            micro_starts = [e for e in play_starts if e.metadata.get("content_type") == "micro_drama"]
            if len(micro_starts) >= 1:
                evidence = [f"micro_drama_starts={len(micro_starts)}"]
                return True, "Viewer has engaged with micro-dramas", evidence
            return False, "Viewer has no micro-drama history", []

        elif goal_id == "G06_reactivate_dormant_7d":
            # Check gap before latest trigger
            if len(history_events) >= 2:
                last_event_time = history_events[-2].server_timestamp
                gap_days = (now - last_event_time).total_seconds() / 86400.0
                if gap_days >= 7.0:
                    evidence = [f"inactivity_days={gap_days:.1f}"]
                    return True, f"Viewer had {gap_days:.1f} days dormancy prior to this return", evidence
            return False, "Viewer was not dormant for 7+ days", []

        elif goal_id == "G07_weekend_family_watch_3d":
            weekday = now.weekday() # Monday is 0, Sunday is 6
            if weekday in [3, 4, 5, 6]: # Thu evening, Fri, Sat, Sun
                evidence = [f"trigger_day={now.strftime('%A')}"]
                return True, "Trigger falls within weekend watch window", evidence
            return False, "Trigger is outside Thursday-Sunday weekend window", []

        elif goal_id == "G08_explore_new_dialect_5d":
            if len(play_starts) >= 3:
                evidence = [f"play_starts={len(play_starts)}"]
                return True, "Viewer has sufficient watch volume to recommend secondary dialect", evidence
            return False, "Viewer lacks baseline watch volume (< 3 plays)", []

        elif goal_id == "G09_add_to_watchlist_2d":
            views = [e for e in history_events if e.event_type == "page_view"]
            if len(views) >= 2:
                evidence = [f"page_views={len(views)}"]
                return True, "Viewer is browsing catalog pages; eligible for watchlist goal", evidence
            return False, "Viewer has not browsed detail pages", []

        return False, "Default rule non-match", []
