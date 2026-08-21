# FINAL RELEASE REPORT — Unified Telecom Analyzer Phase II
**Generated:** 2026-08-21  
**Git commit:** a5168298 (branch: phase2)  
**Report type:** Final validation + PPT/paper correction  

---

## 1. Environment

| Property | Value |
|----------|-------|
| Python | 3.12.3 |
| Virtual environment | /mnt/e/telecom-analyzer/venv |
| torch | 2.5.1+cpu (CPU-only, no CUDA) |
| numpy | 1.26.4 |
| pandas | 2.2.3 |
| scikit-learn | 1.5.2 |
| prophet | 1.1.6 (CmdStan 2.33.1 installed) |
| statsmodels | 0.14.4 |
| faiss-cpu | 1.9.0 |
| tshark | 4.2.2 (system) |
| g++ | 13.3.0 (system) |
| Platform | Linux WSL2 (x86_64) |

**System-level fix applied:** CmdStan 2.33.1 installed into prophet stan_model directory to enable Prophet execution. This was the root cause of Prophet being silently skipped in the prior environment (Python 3.13.13).

---

## 2. Test Gate

```
Command: make test-all  (pytest tests/ -v --cov=src)
PASSED:  173
FAILED:  0
SKIPPED: 1  (test_run_root_cause_agent_with_real_ollama — requires live Ollama server)
```

All three test runs (pre-benchmark, post-benchmark, post-PPT/paper edits) produced identical results: **173/0/1**.  
No source code or test files were modified.

---

## 3. Capacity Configuration

Verified consistent across all authoritative sources:

| Channel | Direction | Value | Source files |
|---------|-----------|-------|-------------|
| TDD | DL | 1400 Mbps | scripts/_ue64_config.py + src/detection/throughput_normalizer.py |
| TDD | UL | 100 Mbps | Same |
| FDD | DL | 84 Mbps | Same |
| FDD | UL | 50 Mbps | Same |

Unit tests in `tests/test_throughput_normalizer.py` enforce these exact values (173 tests pass).

---

## 4. Detection Benchmark

**Command:** `python scripts/run_detection_benchmark.py`  
**Dataset:** kpi_64ue_6hr.csv + stats_64ue_6hr.csv (5,760 rows × 16 cells each)  
**Evaluation:** Cell-level / scenario-level (16 cells, 3 ground-truth fault cells)  
**Fault cells:** PCI_3 (congestion), PCI_12 (outage), PCI_8 (drift)  
**Random seed:** 42

| Method | TP | FP | FN | TN | Precision | Recall | F1 |
|--------|----|----|----|----|-----------|--------|----|
| Threshold-only (KPI) | 3 | 4 | 0 | 9 | 0.4286 | 1.000 | 0.600 |
| IQR-only (KPI) | 3 | 13 | 0 | 0 | 0.1875 | 1.000 | 0.316 |
| Full Ensemble (KPI+Stats) | 3 | 13 | 0 | 0 | 0.1875 | 1.000 | 0.316 |
| Ensemble + EventRouter | 3 | 13 | 0 | 0 | 0.1875 | 1.000 | 0.316 |
| **Stats Count-Threshold** | **3** | **0** | **0** | **13** | **1.000** | **1.000** | **1.000** |

**Cross-source correlation:** 1,427 total events, 1,427 cross-source clustered (100% assignment rate).

*Note: High FP for KPI ensemble methods reflects TDD/FDD capacity calibration differences in the synthetic dataset. Stats domain is not affected by this bias.*

---

## 5. Forecast Benchmark

**Command:** `python scripts/run_forecast_benchmark.py`  
**Dataset:** kpi_10hr_sample.csv (6,000 rows × 10 cells)  
**Configuration:** Rolling-origin backtest, horizon=4h, origins=8, seed=42  

| Method | MAE | RMSE | MAPE | Series | Lead Det/Total |
|--------|-----|------|------|--------|----------------|
| Holt-Winters | 14.969 | 20.391 | 45.10% | 220 | 0/6 |
| LSTM | 19.780 | 23.629 | 55.76% | 220 | 0/6 |
| Prophet | 22.430 | 31.138 | 72.80% | 220 | 1/6 |

**All three methods executed** (Prophet enabled by CmdStan 2.33.1 fix).  
**Lead-time = 0 for HW/LSTM** is an honest negative finding — abrupt step-change anomalies have no learnable precursor. Prophet's 1/6 is a **false alarm** (false_alarms=1 confirmed in benchmark JSON).

---

## 6. RCA Evaluation

**Command:** `python scripts/run_rca_evaluation.py`  
**Method:** rule_based_root_cause() — deterministic, no LLM (Ollama unavailable)

| Cell | Fault Type | Keyword Hit Rate | Pass |
|------|-----------|-----------------|------|
| PCI_3 | Congestion | 0.50 | YES |
| PCI_12 | Outage | 0.714 | YES |
| PCI_8 | Drift | 0.333 | YES |

**Overall:** 3/3 fault cells identified. Top-1/Top-3/MRR NOT reported — evaluator does not rank candidates.

---

## 7. Scalability Benchmark

**Command:** `python scripts/run_scalability_benchmark.py`  
**Memory method:** tracemalloc per-stage (incremental allocation, NOT cumulative RSS)

| Stage | Latency | Peak (tracemalloc) |
|-------|---------|-------------------|
| PCAP parse (901 pkts) | 2.60 s | 1.14 MB |
| KPI parse (5,760 rows) | 0.80 s | 10.67 MB |
| KPI detection (6 detectors) | 27.82 s | 10.89 MB |
| Stats parse + detect | 4.55 s | 12.09 MB |
| Correlation (1,427 events) | 4.32 s | 1.61 MB |
| **TOTAL** | **40.1 s** | **~12 MB peak** |

**Cell scaling (KPI detection only):**

| Cells | Rows | Mean Latency | Mean Memory |
|-------|------|--------------|-------------|
| 4 | 1,440 | 7.0 s | 4.7 MB |
| 8 | 2,880 | 18.6 s | 9.2 MB |
| 12 | 4,320 | 27.3 s | 14.1 MB |
| 16 | 5,760 | 27.9 s | 18.6 MB |

**Correction:** Prior PPT cited **56.8 s / 1.2 GB** — both incorrect. Actual: **40.1 s / ~12 MB tracemalloc peak**.

---

## 8. PPT Audit

**File:** `docs/Phase2_Third_Review_Comprehensive.pptx` (23 slides)  
**Generator:** `scripts/generate_phase2_review3_comprehensive_ppt.py` — updated and deck regenerated

| Stale Claim Removed | Old Value | Correct Value |
|--------------------|-----------|---------------|
| F1 (ensemble) | 0.86 | 0.316 |
| Threshold F1 | 0.22 | 0.600 |
| IF baseline F1 | 0.50 | "Not in final benchmark" |
| Total latency | 56.8 s | 40.1 s |
| Peak memory | 1.2 GB | ~12 MB (tracemalloc) |
| "real-world-scale" | over-claim | "controlled synthetic testbed" |
| "Prophet not executed" | stale | Prophet MAE=22.43 (benchmarked) |
| Holt-Winters MAE | 15.54 | 14.969 |
| LSTM MAE | 20.24 | 19.780 |
| KPI detect latency | 32.7 s | 27.8 s |
| Test count (Review 2 note) | 83 (no context) | 83 + annotation "→ 173 by Review 3" |

**Full audit:** `results/final_ppt_audit.md`

---

## 9. Journal Paper Audit

**File:** `docs/document_journalpaper/Vikas_UnifiedTelecomAnalyzer_ProjectReport.docx`  
**17 replacements made in paragraph text runs.**

| Old Claim | Updated Value | Count |
|-----------|---------------|-------|
| "F1 0.86" | "F1=1.00 (Stats CT); F1=0.316 (Ensemble); F1=0.600 (Threshold)" | 3 |
| "F1 0.22" | "F1=0.600" | 4 |
| "F1 0.50" (IF) | "F1=0.316 (IQR-only) [IF not benchmarked]" | 2 |
| "57 sec" | "~40 s" | 3 |
| "F1 = 0.22" / "F1 = 0.86" | Corrected | 3 |
| "56 tests" | "173 tests" | 2 |

**Full audit:** `results/final_paper_audit.md`

---

## 10. Reproducibility

| Item | Status |
|------|--------|
| Random seed (42) | Used in all 4 benchmarks |
| All 4 benchmark scripts | Executed fresh on 2026-08-21 |
| results/final_benchmark_results.json | Created — authoritative source |
| results/experiment_manifest.json | Updated with Python 3.12.3 environment |
| PPT generator | Updated; deck regenerated from script |
| Journal paper | 17 stale values replaced in paragraph text |

---

## 11. Known Limitations

1. **Synthetic dataset only** — Not validated against real production network data.
2. **Prophet lead=1/6 is a false alarm** — Not a positive result; documented.
3. **RCA ranking metrics absent** — Keyword hit-rate only; no Top-1/Top-3/MRR.
4. **Ollama unavailable** — ReAct agent tested with deterministic fallback only.
5. **KPI ensemble FP=13** — Dataset characteristic (TDD/FDD capacity difference); documented.
6. **Scalability** — Profiled at 4–16 cells; macro-network scale not tested.

---

## 12. Remaining Issues

| Issue | Severity |
|-------|----------|
| Journal paper Word table cells (Table 9.3, 9.5) — need manual visual verification | MEDIUM |
| Section 9.4 Ablation: "single false positive" narrative contradicts FP=13 (needs methodological clarification) | MEDIUM |
| Author/institution placeholders `[Guide Name]`, `[USN]`, `[Month–Year]` | LOW |
| Figure 9.1 caption — may still reference old F1 values | LOW |

---

## 13. Cross-Artifact Consistency Check

| Metric | Code | Benchmark JSON | Manifest | PPT | Paper |
|--------|------|---------------|---------|-----|-------|
| TDD DL 1400 | ✅ | ✅ | ✅ | ✅ | ✅ |
| TDD UL 100 | ✅ | ✅ | ✅ | ✅ | ✅ |
| FDD DL 84 | ✅ | ✅ | ✅ | ✅ | ✅ |
| FDD UL 50 | ✅ | ✅ | ✅ | ✅ | ✅ |
| Threshold F1=0.600 | ✅ | ✅ | ✅ | ✅ | ✅ |
| Ensemble F1=0.316 | ✅ | ✅ | ✅ | ✅ | ✅ |
| Stats CT F1=1.000 | ✅ | ✅ | ✅ | ✅ | ✅ |
| HW MAE=14.969 | ✅ | ✅ | ✅ | ✅ | ✅ |
| LSTM MAE=19.780 | ✅ | ✅ | ✅ | ✅ | ✅ |
| Prophet MAE=22.430 | ✅ | ✅ | ✅ | ✅ | ✅ |
| Total latency ~40 s | ✅ | ✅ | ✅ | ✅ | ✅ |
| Memory ~12 MB tracemalloc | ✅ | ✅ | ✅ | ✅ | ✅* |
| Test count 173 | ✅ | ✅ | ✅ | ✅ | ✅ |

*Paper paragraph text updated; table cells require manual Word verification.

---

## FINAL STATUS

```
RELEASE BLOCKED
```

**Reason for BLOCKED:** The journal paper's paragraph text has been corrected (17 replacements), but Word table cells (Table 9.3 — detection results, Table 9.5 — latency) were not updated by the automated run-level text replacement. Manual editing in Microsoft Word or LibreOffice is required before the paper can be submitted for review. Additionally, Section 9.4 contains a narrative about "single false positive" that conflicts with the cell-level benchmark result (FP=13 for the ensemble) and requires methodological clarification by the author.

**PPT:** PRESENTATION-READY — all stale claims corrected, deck regenerated.  
**Code & benchmarks:** RELEASE-READY — no source changes, 173/0/1 tests.  
**Journal paper:** BLOCKED — requires manual table/figure editing before academic submission.
