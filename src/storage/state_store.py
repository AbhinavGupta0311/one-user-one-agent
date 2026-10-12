"""
Durable Per-Viewer State Store.
Maintains provenanced facts, event idempotency keys, single active goal,
decisions history, actions, outcomes, and cross-session learnings.
"""
from __future__ import annotations
import json
import os
from typing import Dict, List, Optional, Set, Any
from datetime import datetime
from pydantic import BaseModel, Field
from src.core.models import (
    ViewerProfile, Event, DecisionOutput, ActionRecord,
    OutcomeJudgement, FactProvenance, GoalAssignment
)

class ViewerState(BaseModel):
    viewer_id: str
    profile: ViewerProfile
    active_goal: Optional[GoalAssignment] = None
    active_plan_notes: Optional[str] = None
    provenance_facts: Dict[str, FactProvenance] = Field(default_factory=dict)
    processed_event_ids: Set[str] = Field(default_factory=set)
    processed_trigger_ids: Set[str] = Field(default_factory=set)
    history_events: List[Event] = Field(default_factory=list)
    decisions: List[DecisionOutput] = Field(default_factory=list)
    actions: List[ActionRecord] = Field(default_factory=list)
    outcomes: List[OutcomeJudgement] = Field(default_factory=list)
    learnings: List[str] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    def record_fact(self, key: str, value: Any, source: str, ts: datetime, now: datetime, notes: Optional[str] = None):
        freshness = max(0.0, (now - ts).total_seconds())
        self.provenance_facts[key] = FactProvenance(
            fact_key=key,
            value=value,
            source=source,
            timestamp=ts,
            freshness_seconds=freshness,
            notes=notes
        )
        self.last_updated = now

    def is_event_processed(self, event_id: str) -> bool:
        return event_id in self.processed_event_ids

    def mark_event_processed(self, event_id: str):
        self.processed_event_ids.add(event_id)

    def is_trigger_processed(self, trigger_id: str) -> bool:
        return trigger_id in self.processed_trigger_ids

    def mark_trigger_processed(self, trigger_id: str):
        self.processed_trigger_ids.add(trigger_id)


class StateStore:
    def __init__(self, storage_dir: str = "sample_run/viewer_state"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self._memory_cache: Dict[str, ViewerState] = {}

    def get_or_create(self, viewer_id: str, default_profile: Optional[ViewerProfile] = None) -> ViewerState:
        if viewer_id in self._memory_cache:
            return self._memory_cache[viewer_id]

        file_path = os.path.join(self.storage_dir, f"{viewer_id}.json")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                state = ViewerState.model_validate(data)
                self._memory_cache[viewer_id] = state
                return state

        profile = default_profile or ViewerProfile(viewer_id=viewer_id)
        state = ViewerState(viewer_id=viewer_id, profile=profile)
        self._memory_cache[viewer_id] = state
        return state

    def save(self, state: ViewerState):
        self._memory_cache[state.viewer_id] = state
        file_path = os.path.join(self.storage_dir, f"{state.viewer_id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(state.model_dump_json(indent=2))

    def list_viewer_ids(self) -> List[str]:
        disk_files = [f.replace(".json", "") for f in os.listdir(self.storage_dir) if f.endswith(".json")]
        all_ids = set(disk_files).union(self._memory_cache.keys())
        return sorted(list(all_ids))
