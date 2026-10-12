"""
Test suite for Tool Failure, Circuit Breaker, and Budget Constraints.
Verifies agent degrades safely when LLM or tools fail, and respects budgets.
"""
from datetime import datetime
from src.core.models import Event, CatalogTitle
from src.storage.state_store import StateStore
from src.goals.catalogue import GoalCatalogue
from src.agent.provider import LLMProvider
from src.agent.viewer_agent import ViewerAgent

def test_llm_failure_graceful_degradation(tmp_path):
    store = StateStore(storage_dir=str(tmp_path / "state"))
    goal_cat = GoalCatalogue()
    
    # LLM provider with simulated outage / circuit breaker trip
    llm = LLMProvider(mode="mock")
    llm.fault_injection_fail = True

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
        viewer_id="V-FAIL-TEST",
        state_store=store,
        goal_catalogue=goal_cat,
        catalog_titles=catalog,
        llm_provider=llm
    )

    now = datetime(2026, 8, 15, 14, 0, 0)
    event = Event(
        event_id="E-FAIL-01",
        viewer_id="V-FAIL-TEST",
        event_type="app_open",
        client_timestamp=now,
        server_timestamp=now,
        app_dialect="d1"
    )

    # Must NOT crash or raise unhandled exception!
    decision = agent.handle_trigger(event, now)

    # Should degrade safely to fallback safe action or DO_NOTHING
    assert decision.status in ["PUBLISHED", "ABSTAINED"]
    assert "Dependency failure fallback" in decision.confidence_reason
    assert "system_recovery:fallback_applied" in decision.evidence

def test_tool_budget_counter_within_bounds(tmp_path):
    store = StateStore(storage_dir=str(tmp_path / "state"))
    goal_cat = GoalCatalogue()
    llm = LLMProvider(mode="mock")
    agent = ViewerAgent(
        viewer_id="V-BUDGET-TEST",
        state_store=store,
        goal_catalogue=goal_cat,
        catalog_titles={},
        llm_provider=llm
    )
    now = datetime(2026, 8, 15, 14, 0, 0)
    event = Event(
        event_id="E-BUD-01",
        viewer_id="V-BUDGET-TEST",
        event_type="app_open",
        client_timestamp=now,
        server_timestamp=now,
        app_dialect="d1"
    )
    decision = agent.handle_trigger(event, now)
    assert decision.model_calls_used <= 8
    assert decision.tool_calls_used <= 20
