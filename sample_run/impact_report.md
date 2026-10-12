# Causal Impact Report & Holdout Analysis

## 1. Executive Summary
This report analyzes the true causal efficacy of the **One User, One Agent** architecture evaluated against a **randomized 20% holdout control group**. It contrasts the unbiased Intent-To-Treat (ITT) causal effect against naive observational metrics.

| Metric | Causal Holdout (ITT) | Naive Observational (Served vs Unserved) | Difference / Bias |
|---|---|---|---|
| **Control / Baseline Conversion** | 8.97% | 9.51% | Confounded baseline |
| **Treatment / Served Conversion** | 9.38% | 8.79% | Inflated by activity bias |
| **Absolute Uplift** | **+0.41%** | -0.72% | Overstated by -1.65x |
| **Relative Uplift** | **+4.6%** | -7.5% | Selection Bias Artifact |
| **Statistical Significance** | **p = 0.6926** (Z = 0.395) | N/A | Valid Randomization |

---

## 2. Why Naive 'Served vs Unserved' Comparisons Mislead
A naive evaluation that compares viewers who received an agent action against viewers who did not suffers from severe **activity selection bias**:
1. **Survivorship & Activity Confounding**: Viewers who open the app regularly or engage in longer sessions naturally qualify for more intervention triggers. Viewers who uninstall or stay dormant never trigger an action and land exclusively in the "unserved" bucket.
2. **Attribution Fallacy**: Attributing their higher conversion to the agent mistakes user baseline intent for agent efficacy.
3. **The Randomized Holdout Solution**: By strictly withholding 20% of synthetic viewers from any agent intervention (forcing `DO_NOTHING` abstention), we preserve balance in latent intent, signup age, device skew, and baseline engagement between Treatment and Control.

---

## 3. Sample Breakdown
- **Total Unique Viewers in State Store**: 5,000
- **Randomized Control Holdout**: 970 viewers
- **Treatment Cohort Total**: 4,030 viewers
  - *Actively Served with Personalized Action*: 728
  - *Abstained / Constrained (Quiet hours, caps, no eligible goals)*: 3,302

---

## 4. Methodological Rigor
- **Pre-intervention balance**: Holdout assignment is determined purely by viewer ID hashing before any session triggers occur.
- **Strict Guardrail on Control**: Holdout viewers receive pure unpersonalized catalog fallbacks. No agent personalization is published for holdout viewers.
- **Honest Attribution**: Goals are only marked as `SUCCEEDED` when an explicit causal telemetric signal (e.g. `play_complete` or `purchase`) arrives within the goal's specified horizon window.
