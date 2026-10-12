"""
CLI Interface for One User, One Agent platform.
Provides commands for:
  - replay: Replays trigger stream with injected surprises
  - inspect-viewer: Views durable state, facts, provenance, decisions for a viewer
  - evaluate-holdout: Runs causal ITT impact evaluation against holdout
  - generate-data: Generates synthetic benchmark datasets
"""
import argparse
import json
import sys
import os

# Add root project directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.replay.simulator import ReplaySimulator
from src.storage.state_store import StateStore
from src.measurement.evaluator import CausalImpactEvaluator
import data.generator as generator

def cmd_replay(args):
    print(f"=== Replaying Trigger Stream (Max Triggers: {args.max_triggers}) ===")
    sim = ReplaySimulator(
        catalog_path=args.catalog,
        viewers_path=args.viewers,
        events_path=args.events,
        output_dir=args.output_dir,
        enable_surprises=not args.no_surprises
    )
    sim.run_replay(max_triggers=args.max_triggers)

def cmd_inspect_viewer(args):
    store = StateStore(storage_dir=args.state_dir)
    state = store.get_or_create(args.viewer_id)
    print(f"=== Viewer State Inspection: {args.viewer_id} ===")
    print(f"Subscription: {state.profile.subscription_status} | Holdout: {state.profile.is_holdout}")
    print(f"Preferred Dialect (Profile): {state.profile.preferred_dialect}")
    print(f"Active Goal: {state.active_goal.model_dump_json() if state.active_goal else 'None'}")
    print("\n--- Provenanced Facts ---")
    for k, v in state.provenance_facts.items():
        print(f"  [{k}] = {v.value} (source: {v.source}, freshness: {v.freshness_seconds:.1f}s)")
    print(f"\n--- History Events: {len(state.history_events)} ---")
    for ev in state.history_events[-5:]:
        print(f"  {ev.event_type} at {ev.server_timestamp} (id: {ev.event_id})")
    print(f"\n--- Decisions: {len(state.decisions)} ---")
    for d in state.decisions[-3:]:
        print(f"  Decision {d.decision_id}: {d.action} | Status: {d.status} | Confidence: {d.confidence} ({d.confidence_reason})")
    print(f"\n--- Outcomes Judged: {len(state.outcomes)} ---")
    for o in state.outcomes:
        print(f"  {o.status} for {o.goal_id}: {o.reasoning}")

def cmd_evaluate_holdout(args):
    store = StateStore(storage_dir=args.state_dir)
    evaluator = CausalImpactEvaluator(store)
    results = evaluator.evaluate()
    print("=== Causal Impact & Holdout Evaluation ===")
    print(json.dumps(results, indent=2))

def cmd_generate_data(args):
    print("=== Regenerating Synthetic Datasets ===")
    generator.main()

def main():
    parser = argparse.ArgumentParser(description="One User, One Agent OTT System CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Replay command
    p_replay = subparsers.add_parser("replay", help="Replay trigger stream")
    p_replay.add_argument("--max-triggers", type=int, default=500, help="Max triggers to process")
    p_replay.add_argument("--catalog", default="data/content_catalogue.json")
    p_replay.add_argument("--viewers", default="data/viewers_profile.json")
    p_replay.add_argument("--events", default="data/events_stream.jsonl")
    p_replay.add_argument("--output-dir", default="sample_run")
    p_replay.add_argument("--no-surprises", action="store_true", help="Disable surprise injections")
    p_replay.set_defaults(func=cmd_replay)

    # Inspect viewer
    p_inspect = subparsers.add_parser("inspect-viewer", help="Inspect durable state for a viewer")
    p_inspect.add_argument("viewer_id", help="Viewer ID (e.g. V-0001)")
    p_inspect.add_argument("--state-dir", default="sample_run/viewer_state")
    p_inspect.set_defaults(func=cmd_inspect_viewer)

    # Evaluate holdout
    p_eval = subparsers.add_parser("evaluate-holdout", help="Run causal ITT evaluation against holdout")
    p_eval.add_argument("--state-dir", default="sample_run/viewer_state")
    p_eval.set_defaults(func=cmd_evaluate_holdout)

    # Generate data
    p_gen = subparsers.add_parser("generate-data", help="Generate synthetic benchmark data")
    p_gen.set_defaults(func=cmd_generate_data)

    parsed = parser.parse_args()
    parsed.func(parsed)

if __name__ == "__main__":
    main()
