"""
Test suite for Conflicting Sources and Dialect Precedence.
Verifies precedence rules: app_setting > profile_snapshot > campaign_link.
Ensures conflicts are never ignored or silently discarded.
"""
from datetime import datetime
from src.dialects.resolver import DialectResolver

def test_three_way_dialect_conflict():
    now = datetime(2026, 8, 15, 12, 0, 0)
    
    # Three sources point to three different dialects
    # app_setting: d3 (device setting active right now)
    # profile_snapshot: d1 (warehouse record 24h old)
    # campaign_link: d2 (referral link clicked last week)
    resolution = DialectResolver.resolve(
        app_dialect="d3",
        profile_dialect="d1",
        campaign_dialect="d2",
        app_setting_timestamp=now,
        profile_snapshot_timestamp=now,
        now=now
    )

    # Resolution must use app_setting for active UI rendering
    assert resolution.used == "d3"
    assert resolution.source == "app_setting"
    
    # Must preserve conflicting sources explicitly
    assert "profile_snapshot:d1" in resolution.conflicts
    assert "campaign_link:d2" in resolution.conflicts
    assert resolution.resolution_rule == "app_setting_precedence_over_warehouse"

def test_fallback_to_profile_when_app_setting_absent():
    now = datetime(2026, 8, 15, 12, 0, 0)
    resolution = DialectResolver.resolve(
        app_dialect=None,
        profile_dialect="d4",
        campaign_dialect="d2",
        app_setting_timestamp=None,
        profile_snapshot_timestamp=now,
        now=now
    )
    assert resolution.used == "d4"
    assert resolution.source == "profile_snapshot"
    assert "campaign_link:d2" in resolution.conflicts

def test_campaign_link_prior_for_brand_new_viewer():
    now = datetime(2026, 8, 15, 12, 0, 0)
    resolution = DialectResolver.resolve(
        app_dialect=None,
        profile_dialect=None,
        campaign_dialect="d5",
        app_setting_timestamp=None,
        profile_snapshot_timestamp=None,
        now=now
    )
    assert resolution.used == "d5"
    assert resolution.source == "campaign_link"
    assert len(resolution.conflicts) == 0
