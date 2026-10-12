"""
Configuration and constants for One User, One Agent platform.
"""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
import os

class SystemConfig(BaseModel):
    # Latency limits
    max_decision_latency_ms: int = 60000  # 60s target constraint
    timeout_failure_ms: int = 300000     # 5 min counts as strict failure
    
    # Model and tool budgets per decision
    max_model_calls_per_decision: int = 8
    max_tool_calls_per_decision: int = 20
    
    # Messaging rules
    quiet_hours_start_hour: int = 22  # 22:00 local time
    quiet_hours_end_hour: int = 8     # 08:00 local time
    max_messages_per_viewer_per_day: int = 1
    min_titles_for_homepage_row: int = 3
    
    # Randomized holdout ratio for true causal evaluation
    holdout_ratio: float = 0.20  # 20% control group
    
    # Freshness thresholds (in seconds)
    warehouse_snapshot_ttl_s: int = 86400 * 2  # 48 hours max age
    offline_event_max_staleness_s: int = 86400 * 7 # 7 days max acceptance for offline buffering
    
    # Dialect precedence order when timestamps equal
    # app_setting (real-time UI intent) > profile (warehouse) > campaign (referral link)
    dialect_precedence: List[str] = Field(
        default_factory=lambda: ["app_setting", "profile_snapshot", "campaign_link"]
    )
    
    # LLM execution mode
    provider_mode: str = os.getenv("LLM_PROVIDER_MODE", "mock")  # "mock", "deterministic", "openai", "gemini"

DEFAULT_CONFIG = SystemConfig()
