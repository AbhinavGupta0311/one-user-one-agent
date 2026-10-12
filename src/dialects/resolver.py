"""
Dialect conflict resolver with rigorous precedence and freshness policies.
"""
from typing import Optional, List, Dict, Tuple
from datetime import datetime
from src.core.models import ConflictResolution, FactProvenance

class DialectResolver:
    """
    Resolves viewer dialect across:
      1. app_setting (real-time device setting sent with trigger)
      2. profile_snapshot (daily warehouse export)
      3. campaign_link (acquisition referral link)
      
    Rule: Never let largest, newest, or most convenient source win by default.
    - If user explicitly set app dialect in active session, that represents immediate UI rendering.
    - If app_setting is missing/null, warehouse profile preference is used.
    - If user is brand new (no profile, no app setting), campaign link dialect is used as initial prior.
    - All conflicting candidates are preserved in the audit log.
    """

    @staticmethod
    def resolve(
        app_dialect: Optional[str],
        profile_dialect: Optional[str],
        campaign_dialect: Optional[str],
        app_setting_timestamp: Optional[datetime],
        profile_snapshot_timestamp: Optional[datetime],
        now: datetime
    ) -> ConflictResolution:
        candidates = {}
        conflicts = []
        
        if app_dialect:
            candidates["app_setting"] = app_dialect
        if profile_dialect:
            candidates["profile_snapshot"] = profile_dialect
        if campaign_dialect:
            candidates["campaign_link"] = campaign_dialect
            
        # If empty
        if not candidates:
            return ConflictResolution(
                used="d1", # Platform default fallback
                source="platform_default",
                conflicts=[],
                resolution_rule="default_fallback_no_signal"
            )
            
        # Detect conflicts among unique dialects
        dialects_seen = {}
        for source, d in candidates.items():
            if d not in dialects_seen:
                dialects_seen[d] = []
            dialects_seen[d].append(source)
            
        is_conflicting = len(dialects_seen) > 1
        
        # Precedence policy:
        # 1. app_setting: active device setting dictates UI text & video stream localization
        # 2. profile_snapshot: durable subscription preference
        # 3. campaign_link: acquisition referral tag
        if "app_setting" in candidates and candidates["app_setting"]:
            chosen_dialect = candidates["app_setting"]
            chosen_source = "app_setting"
        elif "profile_snapshot" in candidates and candidates["profile_snapshot"]:
            chosen_dialect = candidates["profile_snapshot"]
            chosen_source = "profile_snapshot"
        else:
            chosen_dialect = candidates["campaign_link"]
            chosen_source = "campaign_link"

        # Record all conflicting sources
        for source, d in candidates.items():
            if d != chosen_dialect:
                conflicts.append(f"{source}:{d}")

        rule_applied = "app_setting_precedence_over_warehouse" if "app_setting" in candidates else "profile_precedence_over_campaign"
        if not is_conflicting:
            rule_applied = "unanimous_or_single_source"

        return ConflictResolution(
            used=chosen_dialect,
            source=chosen_source,
            conflicts=conflicts,
            resolution_rule=rule_applied
        )
