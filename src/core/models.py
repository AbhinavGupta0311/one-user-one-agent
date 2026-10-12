"""
Core domain models and schemas for One User, One Agent.
"""
from __future__ import annotations
from typing import Dict, List, Optional, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field

class FactProvenance(BaseModel):
    fact_key: str
    value: Any
    source: str # e.g. "app_setting", "warehouse_profile", "event_stream", "campaign_link"
    timestamp: datetime
    freshness_seconds: float
    confidence: float = 1.0
    notes: Optional[str] = None

class ConflictResolution(BaseModel):
    used: str
    source: str
    conflicts: List[str] = Field(default_factory=list)
    resolution_rule: str = "freshness_and_precedence"

class Event(BaseModel):
    event_id: str
    viewer_id: str
    event_type: str # app_open, play_start, play_progress, play_complete, search, purchase, message_delivered, message_clicked
    client_timestamp: datetime
    server_timestamp: datetime
    app_dialect: Optional[str] = None
    app_language: Optional[str] = None
    campaign_link: Optional[str] = None
    campaign_dialect: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @property
    def clock_skew_seconds(self) -> float:
        return (self.server_timestamp - self.client_timestamp).total_seconds()

class ViewerProfile(BaseModel):
    viewer_id: str
    signup_date: Optional[datetime] = None
    subscription_status: Literal["anonymous", "trial", "paid", "expired", "churned"] = "trial"
    preferred_dialect: Optional[str] = None
    preferred_language: Optional[str] = None
    timezone_offset_minutes: int = 330 # default IST UTC+05:30
    push_consent: bool = True
    whatsapp_consent: bool = False
    is_holdout: bool = False
    version: int = 1
    snapshot_date: Optional[datetime] = None

class CatalogTitle(BaseModel):
    title_id: str
    title_name: str
    dialects: List[str]
    languages: List[str]
    genres: List[str]
    content_type: Literal["film", "series", "micro_drama"]
    episodes_count: int = 1
    availability_start: datetime
    availability_end: datetime
    description: str
    is_active: bool = True

class GoalDefinition(BaseModel):
    goal_id: str
    name: str
    description: str
    horizon_days: int
    success_signal: str # e.g. "play_complete_episode_1", "purchase_confirmed", "session_count_gte_2"
    observable_in_telemetry: bool = True
    is_underspecified: bool = False
    underspecified_reason: Optional[str] = None
    eligibility_rule_id: str
    rule_version: int = 1

class TriggerInfo(BaseModel):
    event: str
    received_at: str
    event_age_s: float
    trigger_id: Optional[str] = None

class GoalAssignment(BaseModel):
    id: str
    deadline: str
    rule_id: Optional[str] = None
    success_signal: Optional[str] = None

class VerificationCheckResult(BaseModel):
    passed: List[str] = Field(default_factory=list)
    failed: List[str] = Field(default_factory=list)
    rejection_reasons: List[str] = Field(default_factory=list)

class DecisionOutput(BaseModel):
    decision_id: str
    viewer_id: str
    trigger: TriggerInfo
    goal: Optional[GoalAssignment] = None
    action: str # "HOME_PAGE", "HERO_SLOT", "PUSH_NOTIFICATION", "WHATSAPP_MESSAGE", "IN_APP_MODAL", "DO_NOTHING"
    dialect: ConflictResolution
    content: List[str] = Field(default_factory=list) # e.g. ["title:T0412", "title:T0977", "title:T1203"]
    confidence: float
    confidence_reason: str
    evidence: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    checks: VerificationCheckResult
    decided_in_ms: float
    status: Literal["PUBLISHED", "ABSTAINED", "FALLBACK", "REJECTED_BY_VERIFIER", "DROPPED_DUPLICATE", "DROPPED_STALE"]
    abstain_reason: Optional[str] = None
    model_calls_used: int = 0
    tool_calls_used: int = 0

class ActionRecord(BaseModel):
    action_id: str
    decision_id: str
    viewer_id: str
    channel: str
    executed_at: datetime
    content_ids: List[str]
    dialect: str
    status: Literal["DELIVERED", "FAILED", "SUPPRESSED_QUIET_HOURS", "SUPPRESSED_FREQ_CAP", "NOOP"]

class OutcomeJudgement(BaseModel):
    judgement_id: str
    decision_id: str
    viewer_id: str
    goal_id: str
    judged_at: datetime
    status: Literal["SUCCEEDED", "FAILED", "INCONCLUSIVE", "HOLDOUT_BASELINE"]
    attributable_signals: List[str] = Field(default_factory=list)
    reasoning: str
    learning_feedback: str
