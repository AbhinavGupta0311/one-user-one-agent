"""
Intervention Catalogue and channel constraints (Quiet Hours, Frequency Caps, Consent, Title Count).
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from src.core.models import ViewerProfile, CatalogTitle, ActionRecord
from src.core.config import DEFAULT_CONFIG

class InterventionCatalogue:
    ALLOWED_ACTIONS = [
        "HOME_PAGE",
        "HERO_SLOT",
        "PUSH_NOTIFICATION",
        "WHATSAPP_MESSAGE",
        "IN_APP_MODAL",
        "DO_NOTHING"
    ]
    
    OUTBOUND_CHANNELS = ["PUSH_NOTIFICATION", "WHATSAPP_MESSAGE"]

    @staticmethod
    def get_local_time(utc_dt: datetime, offset_minutes: int) -> datetime:
        return utc_dt + timedelta(minutes=offset_minutes)

    @classmethod
    def is_quiet_hours(cls, utc_dt: datetime, offset_minutes: int) -> Tuple[bool, str]:
        """
        Quiet hours: 22:00 (10 PM) to 08:00 (8 AM) local viewer time.
        Outbound messaging during quiet hours is strictly forbidden.
        """
        local_time = cls.get_local_time(utc_dt, offset_minutes)
        hour = local_time.hour
        
        # 22:00 - 23:59 or 00:00 - 07:59
        if hour >= DEFAULT_CONFIG.quiet_hours_start_hour or hour < DEFAULT_CONFIG.quiet_hours_end_hour:
            return True, f"Local time {local_time.strftime('%H:%M')} is within quiet hours (22:00-08:00)"
        return False, f"Local time {local_time.strftime('%H:%M')} is within permissible active hours"

    @classmethod
    def check_frequency_cap(
        cls,
        action: str,
        recent_actions: List[ActionRecord],
        now: datetime
    ) -> Tuple[bool, str]:
        """
        Frequency cap: At most 1 outbound message (push/whatsapp) per viewer per day.
        """
        if action not in cls.OUTBOUND_CHANNELS:
            return True, "Action is not subject to outbound messaging frequency cap"

        one_day_ago = now - timedelta(days=1)
        outbound_today = [
            a for a in recent_actions
            if a.channel in cls.OUTBOUND_CHANNELS
            and a.status == "DELIVERED"
            and a.executed_at >= one_day_ago
        ]

        if len(outbound_today) >= DEFAULT_CONFIG.max_messages_per_viewer_per_day:
            return False, f"Frequency cap exceeded: viewer received {len(outbound_today)} message(s) in past 24 hours"

        return True, "Frequency cap satisfied (0 messages in last 24h)"

    @classmethod
    def check_consent(cls, action: str, profile: ViewerProfile) -> Tuple[bool, str]:
        """
        Consent rules:
        - PUSH_NOTIFICATION requires push_consent == True
        - WHATSAPP_MESSAGE requires whatsapp_consent == True
        """
        if action == "PUSH_NOTIFICATION":
            if not profile.push_consent:
                return False, "Viewer has opted out of push notifications"
            return True, "Push notification consent verified"

        elif action == "WHATSAPP_MESSAGE":
            if not profile.whatsapp_consent:
                return False, "Viewer has not opted in to WhatsApp messages"
            return True, "WhatsApp messaging consent verified"

        return True, "In-app / UI surface does not require outbound consent"

    @classmethod
    def validate_content_payload(
        cls,
        action: str,
        content_titles: List[CatalogTitle],
        target_dialect: str
    ) -> Tuple[bool, str]:
        """
        Content rules:
        - HOME_PAGE row requires at least 3 titles available in the viewer's target dialect.
        - HERO_SLOT requires at least 1 title available in target dialect.
        """
        if action == "HOME_PAGE":
            valid_titles = [t for t in content_titles if target_dialect in t.dialects and t.is_active]
            if len(valid_titles) < DEFAULT_CONFIG.min_titles_for_homepage_row:
                return False, f"HOME_PAGE row requires at least 3 titles in dialect {target_dialect}; only {len(valid_titles)} found"
            return True, f"HOME_PAGE row valid with {len(valid_titles)} titles"

        elif action == "HERO_SLOT":
            valid_titles = [t for t in content_titles if target_dialect in t.dialects and t.is_active]
            if len(valid_titles) < 1:
                return False, f"HERO_SLOT requires at least 1 valid title in dialect {target_dialect}"
            return True, "HERO_SLOT valid with target title"

        return True, "Content payload valid for action"
