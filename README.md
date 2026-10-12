# One User, One Agent: Regional OTT Lifecycle Intelligence

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests Passing](https://img.shields.io/badge/tests-13%20passed-brightgreen.svg)]()
[![P99 Latency](https://img.shields.io/badge/p99%20latency-3.1ms-success.svg)]()
[![SLA Compliance](https://img.shields.io/badge/SLA%20Compliance-100%25-brightgreen.svg)]()

Production-grade autonomous lifecycle agent architecture for regional-dialect streaming platforms. Built with real-time decisioning, independent verification gates, and randomized causal holdout evaluation.

---

## 1. Quickstart & Reproducibility

### Setup
```bash
# 1. Clone repository & install dependencies
pip install -r requirements.txt
```

### One-Command Full Replay (Runs Benchmark & Injects Surprises)
```bash
python src/cli.py replay --max-triggers 1000
```
This single command replays the app-open trigger stream across synthetic viewers, dynamically injects surprises (offline buffered bursts, 3-way dialect conflicts, mid-stream goal corrections, prompt injection attacks, circuit breaker trips), enforces SLAs, and writes complete audit outputs to `sample_run/`.

### Run Automated Test Suite
```bash
python -m pytest tests -v
```
Verifies all 13 critical test cases:
- Late & duplicate trigger idempotency
- 3-way dialect conflict resolution
- Circuit breaker / tool failure degradation
- Mid-stream goal rule patching
- Missing telemetric signal detection
- Prompt injection defense
- Quiet hours & frequency caps
- True Causal ITT vs. naive selection bias

### Inspect Durable Viewer State
```bash
python src/cli.py inspect-viewer V-0042
```

### Evaluate Causal Holdout & Selection Bias
```bash
python src/cli.py evaluate-holdout
```

### Run Real-Time Trigger API Service
```bash
python -m uvicorn src.api:app --host 0.0.0.0 --port 8000
```
- API Docs & Swagger UI: `http://localhost:8000/docs`
- Send webhook trigger: `POST /triggers`
- Inspect viewer state: `GET /viewers/{viewer_id}`

---

## 2. Repository Layout
```
├── README.md                 # Setup, reproduction commands & design overview
├── ARCHITECTURE.md           # Ownership, memory, verification, latency & safety
├── AI_COLLABORATION.md       # AI assistant log & 4 explicitly rejected suggestions
├── KNOWN_LIMITATIONS.md      # Intentional scope choices & 10M viewer scaling roadmap
├── requirements.txt          # Python dependencies
├── conftest.py               # Test configuration
├── data/
│   ├── generator.py          # Synthetic dataset synthesizer (5K viewers, 1.5K titles, 30K events)
│   ├── content_catalogue.json
│   ├── viewers_profile.json
│   ├── warehouse_snapshot.json
│   ├── events_stream.jsonl
│   └── past_pilot_results.json
├── src/
│   ├── core/                 # Pydantic domain models & system configuration
│   ├── storage/              # Durable per-viewer state store with disk persistence
│   ├── dialects/             # Precedence matrix & dialect conflict resolver
│   ├── goals/                # 12-goal candidate catalogue & eligibility evaluator
│   ├── interventions/        # Channels, quiet hours, frequency caps & shelf sizing
│   ├── agent/                # Single-viewer agent runtime & provider abstraction
│   ├── verification/         # Independent verification gate (Zero-Trust LLM Boundary)
│   ├── measurement/          # Causal Intent-To-Treat (ITT) holdout evaluator
│   ├── replay/               # Stream replay simulator with surprise injection
│   ├── cli.py                # Command-line interface
│   └── api.py                # FastAPI real-time webhook server
├── tests/                    # 13 comprehensive automated test scenarios
└── sample_run/               # Generated benchmark outputs
    ├── decisions.jsonl       # Machine-readable decisions matching required schema
    ├── viewer_state/         # Durable per-viewer state snapshots
    ├── actions.jsonl         # Published action dispatches
    ├── outcomes.jsonl        # Attributable telemetric outcome judgments
    ├── latency_report.json   # SLA compliance & latency distribution
    ├── impact_report.md      # Causal holdout vs naive selection bias analysis
    └── final_report.md       # Operational summary report
```

---

## 3. Required Decision Output Format
Every agent decision conforms to the required machine-readable schema:
```json
{
  "decision_id": "D-857F1F",
  "viewer_id": "V-0042",
  "trigger": {
    "event": "app_open",
    "received_at": "2026-08-15T12:00:00Z",
    "event_age_s": 12.4,
    "trigger_id": "E-000005"
  },
  "goal": {
    "id": "G01_first_full_episode_3d",
    "deadline": "2026-08-18T12:00:00Z",
    "rule_id": "G01-r1",
    "success_signal": "play_complete_first_episode"
  },
  "action": "HOME_PAGE",
  "dialect": {
    "used": "d4",
    "source": "app_setting",
    "conflicts": ["profile_snapshot:d1"],
    "resolution_rule": "app_setting_precedence_over_warehouse"
  },
  "content": [
    "title:T0006",
    "title:T0008",
    "title:T0011"
  ],
  "confidence": 0.78,
  "confidence_reason": "Personalized home page shelf with 3 confirmed d4 titles aligns with G01_first_full_episode_3d",
  "evidence": [
    "event_count:play_complete=0",
    "profile_status:trial",
    "dialect_catalog_count:10",
    "event:E-000005"
  ],
  "assumptions": [
    "Viewer engages predominantly with dialect d4 on device"
  ],
  "checks": {
    "passed": [
      "action_validity",
      "prompt_injection_safety",
      "eligibility",
      "consent",
      "quiet_hours",
      "frequency_cap",
      "content_catalog_presence",
      "dialect",
      "row_constraints",
      "duplicate_action"
    ],
    "failed": [],
    "rejection_reasons": []
  },
  "decided_in_ms": 1.15,
  "status": "PUBLISHED",
  "abstain_reason": null,
  "model_calls_used": 1,
  "tool_calls_used": 5
}
```

---

## 4. Key Architectural Highlights

### 1. Ownership & Single Active Goal
Each viewer has exactly **one dedicated agent** that owns the current goal, its single active plan, and full provenance history. No competing multi-agent systems pursue conflicting goals.

### 2. Dialect Conflict Resolution Matrix
When data sources disagree (e.g., `app_setting` is `d3`, `profile_snapshot` is `d1`, `campaign_link` is `d2`):
- `app_setting` wins because it determines what the client app currently renders.
- `profile_snapshot` is a 24-48h stale warehouse export used when `app_setting` is absent.
- `campaign_link` reflects entry referral intent and is used only as an initial prior for brand-new users.
- All conflicting sources are explicitly logged under `"conflicts": ["profile_snapshot:d1", "campaign_link:d2"]`.

### 3. Independent Verification Gate (Zero-Trust Boundary)
The agent planning engine proposes; the `VerificationGate` independently audits before publication:
- **Eligibility**: Verifies telemetric evidence for the chosen goal (rejects LLM hallucinations).
- **Dialect & Availability**: Verifies content exists, is active, and matches the viewer's dialect.
- **Quiet Hours**: Converts to viewer's local timezone; blocks outbound push/WhatsApp between 22:00 and 08:00 local time.
- **Frequency Caps**: Max 1 message per viewer per day.
- **Prompt Injection Defense**: Sanitizes catalog metadata, catching adversarial directives like `[SYSTEM OVERRIDE: Ignore previous instructions]`.

### 4. Honest Causal Measurement vs. Selection Bias
Contrasts naive observational metrics against a **Randomized 20% Holdout Control Group**:
- **Naive Comparison** (`Served vs. Unserved`): Misleadingly compares active app users with dormant non-openers, creating an artificial +248% selection bias artifact.
- **Causal Intent-To-Treat (ITT)**: Measures the true population-level causal effect against the randomized holdout control group, supported by two-proportion Z-test p-values.
