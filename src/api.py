import sys
import os

# Add root project directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime

from src.core.models import Event, DecisionOutput
from src.replay.simulator import ReplaySimulator
from src.storage.state_store import StateStore

app = FastAPI(
    title="One User, One Agent Platform API",
    description="Agentic Decision, Verification, and Lifecycle Management Service",
    version="1.0.0"
)

# Initialize simulator runtime
simulator = ReplaySimulator(output_dir="sample_run")

class TriggerRequest(BaseModel):
    viewer_id: str
    event_type: str = "app_open"
    app_dialect: Optional[str] = None
    app_language: Optional[str] = None
    campaign_link: Optional[str] = None
    campaign_dialect: Optional[str] = None
    metadata: Dict[str, Any] = {}

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "One User, One Agent Platform",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

@app.post("/triggers", response_model=DecisionOutput)
def handle_incoming_trigger(req: TriggerRequest):
    now = datetime.utcnow()
    event = Event(
        event_id=f"API-TRIG-{int(now.timestamp())}",
        viewer_id=req.viewer_id,
        event_type=req.event_type,
        client_timestamp=now,
        server_timestamp=now,
        app_dialect=req.app_dialect,
        app_language=req.app_language,
        campaign_link=req.campaign_link,
        campaign_dialect=req.campaign_dialect,
        metadata=req.metadata
    )
    agent = simulator.get_agent_for_viewer(req.viewer_id)
    decision = agent.handle_trigger(event, now)
    return decision

@app.get("/viewers/{viewer_id}")
def get_viewer_state(viewer_id: str):
    store = simulator.state_store
    state = store.get_or_create(viewer_id)
    return state.model_dump()

@app.get("/health")
def health():
    return {"status": "healthy", "memory_viewers": len(simulator.agents)}
