"""
Test suite for Late, Duplicate, and Out-of-Order Triggers.
Verifies idempotency and safe degradation on buffered offline events.
"""
import pytest
from datetime import datetime, timedelta
from src.core.models import Event, ViewerProfile, CatalogTitle
from src.storage.state_store import StateStore
from src.goals.catalogue import GoalCatalogue
from src.agent.provider import LLMProvider
from src.agent.viewer_agent import ViewerAgent

@pytest.fixture
def agent_fixture(tmp_path):
    store = StateStore(storage_dir=str(tmp_path / "state"))
    goal_cat = GoalCatalogue()
    llm = LLMProvider(mode="mock")
    catalog = {
        "T0001": CatalogTitle(
            title_id="T0001", title_name="Title 1", dialects=["d1"], languages=["hi"],
            genres=["drama"], content_type="film", availability_start=datetime(2026, 1, 1),
            availability_end=datetime(2026, 12, 31), description="Valid description"
        ),
        "T0002": CatalogTitle(
            title_id="T0002", title_name="Title 2", dialects=["d1"], languages=["hi"],
            genres=["drama"], content_type="film", availability_start=datetime(2026, 1, 1),
            availability_end=datetime(2026, 12, 31), description="Valid description"
        ),
        "T0003": CatalogTitle(
            title_id="T0003", title_name="Title 3", dialects=["d1"], languages=["hi"],
            genres=["drama"], content_type="film", availability_start=datetime(2026, 1, 1),
            availability_end=datetime(2026, 12, 31), description="Valid description"
        )
    }
    agent = ViewerAgent(
        viewer_id="V-TEST-DUP",
        state_store=store,
        goal_catalogue=goal_cat,
        catalog_titles=catalog,
        llm_provider=llm
    )
    return agent, store

def test_duplicate_trigger_idempotency(agent_fixture):
    agent, store = agent_fixture
    now = datetime(2026, 8, 15, 14, 0, 0)
    
    event = Event(
        event_id="E-TRIG-001",
        viewer_id="V-TEST-DUP",
        event_type="app_open",
        client_timestamp=now,
        server_timestamp=now,
        app_dialect="d1"
    )

    # First trigger: processes normally
    d1 = agent.handle_trigger(event, now)
    assert d1.status in ["PUBLISHED", "ABSTAINED"]

    # Second trigger with identical event ID: must be dropped as duplicate
    d2 = agent.handle_trigger(event, now + timedelta(seconds=2))
    assert d2.status == "DROPPED_DUPLICATE"
    assert "Duplicate trigger ID" in d2.abstain_reason
    assert "idempotency" in d2.checks.passed

def test_stale_offline_buffered_event_handling(agent_fixture):
    agent, store = agent_fixture
    now = datetime(2026, 8, 15, 14, 0, 0)
    
    # Event buffered 10 days ago (older than 7-day max threshold)
    stale_event = Event(
        event_id="E-STALE-OLD",
        viewer_id="V-TEST-DUP",
        event_type="app_open",
        client_timestamp=now - timedelta(days=10),
        server_timestamp=now - timedelta(days=10),
        app_dialect="d1"
    )

    success, msg = agent.ingest_event(stale_event, now)
    assert success is False
    assert "discarded as stale telemetry" in msg
