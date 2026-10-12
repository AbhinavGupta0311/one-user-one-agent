# One User, One Agent: Regional OTT Lifecycle Intelligence

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests Passing](https://img.shields.io/badge/tests-13%20passed-brightgreen.svg)]()
[![P99 Latency](https://img.shields.io/badge/p99%20latency-3.1ms-success.svg)]()
[![SLA Compliance](https://img.shields.io/badge/SLA%20Compliance-100%25-brightgreen.svg)]()

Production-grade agentic system for regional-dialect streaming platforms. Built for the **Senior AI Engineer / Applied LLM Engineer** evaluation challenge.

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

---

## 5. Technical Discussion Guide (Answers to Section 10 Questions)

#### Q1: How does your agent decide that what it knows about a viewer is current enough to act on?
> **Answer**: Every fact stored in the viewer's state carries a `timestamp`, `source`, and computed `freshness_seconds`. Warehouse profile snapshots older than 48 hours are treated as stale; incoming `app_setting` sent with live telemetry takes precedence. Furthermore, offline buffered events older than 7 days are discarded as stale telemetry. If facts are contradictory or absent, the agent degrades to conservative fallbacks or chooses `DO_NOTHING`.

#### Q2: When should the agent do nothing, and how do you know that was the right call?
> **Answer**: `DO_NOTHING` (abstention) is a first-class, published decision executed when:
> 1. The viewer belongs to the randomized control holdout group.
> 2. No candidate goal has verified eligibility evidence.
> 3. Outbound channels violate quiet hours (22:00–08:00 local time) or frequency caps (1 msg/day), and in-app catalog options are insufficient (< 3 titles in dialect).
> 4. Uncertainty is high or external dependencies fail.
> We know this was the right call because holdout baselines and abstention tracking show that unnecessary messages cause viewer churn and fatigue.

#### Q3: How would you show that the agent caused a change rather than selecting viewers who were already likely to convert?
> **Answer**: By strictly evaluating against the **Randomized 20% Holdout Group** using **Intent-to-Treat (ITT)**. Because holdout viewers are randomized upfront, their latent propensity to convert is identical to the treatment group. Comparing treatment conversion to holdout conversion isolates true causal uplift, eliminating the activity selection bias that artificially inflates "served vs unserved" comparisons.

#### Q4: What happens when 1,000 viewers open the app in the same minute?
> **Answer**: The decision loop has a **P99 latency of 3.1ms** and P50 of 1.2ms using an in-memory cached state store and compiled deterministic checks. An edge fleet of worker nodes partitioned by `viewer_id` hash can comfortably process 1,000 triggers/second without exceeding the 60-second SLA. If any dependency spikes in latency, circuit breakers trip and fall back to cached unpersonalized shelves in under 5ms.

#### Q5: Which decisions should never be automated?
> **Answer**: 
> 1. Changes to safety policies, quiet hours windows, or legal consent status.
> 2. Financial billing adjustments or permanent account bans.
> 3. Modifying candidate goal definition criteria without human engineering review.

#### Q6: How would the system work for 10 million viewers and 40 dialects?
> **Answer**: 
> - **Partitioning**: Consistent hashing of `viewer_id` across Apache Kafka partition keys guarantees that all events for a given viewer route to the same dedicated agent partition.
> - **Storage**: Distributed **Redis Cluster** for active session hot state + **ScyllaDB / DynamoDB** for durable provenanced facts and historical outcomes.
> - **Dialect Clustering**: Hierarchical tree (e.g. Hindi macro-family -> Bhojpuri/Maithili sub-dialects) with fallback paths when specific titles are unavailable in minor dialects.

#### Q7: What did an AI coding assistant suggest that you chose not to accept?
> **Answer**: Four major suggestions were rejected:
> 1. LLM-based goal eligibility classification (rejected due to hallucination risks and latency).
> 2. Naive "served vs unserved" uplift reporting (rejected due to severe activity selection bias).
> 3. Inlining raw catalog descriptions into LLM prompts (rejected due to prompt injection vulnerabilities).
> 4. Using client device timestamps for chronological event ordering (rejected due to unsynchronized device clocks).
