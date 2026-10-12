# Known Limitations & Future Architecture Roadmap

In accordance with the 10–12 hour time budget constraint, several deliberate engineering trade-offs were made to prioritize a rock-solid, verifiable **decide, act, and measure loop** over distributed infrastructure complexity.

---

## 1. Intentional Current Limitations

### 1.1 Storage Engine: Local Disk JSON Store vs Distributed Key-Value Store
- **Current State**: The `StateStore` persists each viewer's durable state as an individual JSON document under `sample_run/viewer_state/<viewer_id>.json` with an in-memory dictionary cache.
- **Why It Was Chosen**: Zero external database dependencies required for evaluators, instant local reproducibility, and complete human-inspectable audit trails.
- **Limitation at Scale**: While optimal for 5,000–50,000 synthetic viewers, filesystem inode exhaustion and lock contention would degrade performance at 10 million viewers.
- **Production Roadmap**: Migrate to a distributed key-value store such as **Redis Cluster** (for low-latency sub-millisecond hot state) backed by **ScyllaDB / DynamoDB** for durable provenanced event and outcome histories.

---

### 1.2 Event Streaming: Synchronous File Replay vs Distributed Message Broker
- **Current State**: The `ReplaySimulator` reads events from `events_stream.jsonl` sequentially within a single Python process.
- **Why It Was Chosen**: Guarantees deterministic, reproducible benchmark execution without requiring Kafka, ZooKeeper, or Redis daemon setup.
- **Limitation at Scale**: Cannot simulate concurrent network I/O across multi-node worker fleets handling 10,000 concurrent requests during evening peak traffic spikes.
- **Production Roadmap**: In production, triggers would arrive via **Apache Kafka / AWS Kinesis** partitioned by `viewer_id` hash (guaranteeing that all events for a single viewer route to the same dedicated agent worker partition).

---

### 1.3 Underspecified Goals in Candidate Catalogue
- **Current State**:
  - `G10_share_referral_link_7d` is flagged as underspecified because the platform rules do not define whether a referral click or a completed subscription by the recipient constitutes a success.
  - `G11_social_group_watch_4d` cannot be observed because the telemetry stream lacks watch room telemetry.
- **Current Handling**: The agent's `GoalCatalogue` explicitly identifies unobservable and underspecified goals and blocks them from being selected.
- **Production Roadmap**: Integrate telemetry instrumentation in the mobile app SDK to emit `watch_party_join` and verified referral tracking events before activating these goals.

---

### 1.4 Bandit & Exploration Policy
- **Current State**: Goal selection among eligible candidates uses a deterministic heuristic prioritization combined with LLM lifecycle planning.
- **Limitation**: Does not continuously optimize exploration vs exploitation rates across subtle demographic sub-segments.
- **Production Roadmap**: Introduce a **Contextual Multi-Armed Bandit (e.g. LinUCB or Thompson Sampling)** layered beneath the LLM planner to balance exploration of secondary dialects against exploitation of proven conversion channels.

---

## 2. Scaling to 10 Million Viewers and 40 Dialects

| Architectural Dimension | Prototype (5K Viewers, 6 Dialects) | Production Target (10M Viewers, 40 Dialects) |
|---|---|---|
| **Storage** | Local JSON files + In-Memory Cache | Redis Enterprise (Hot Cache) + Cassandra/DynamoDB |
| **Partitioning** | Single process keyed by `viewer_id` | Consistent Hashing on `viewer_id` across Kafka Partitions |
| **Throughput** | ~200 decisions/sec | 50,000 decisions/sec at evening peak |
| **Dialect Engine** | 6-dialect matrix | Hierarchical dialect tree (macro-language + sub-dialect clustering) |
| **Inference Cost** | Mock & Heuristic Fast Path | Tiered LLM routing: SLM/rules on edge (95%) + LLM reasoning for complex drop-offs (5%) |
