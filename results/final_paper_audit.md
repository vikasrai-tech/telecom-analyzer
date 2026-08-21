# Journal Paper Audit — docs/document_journalpaper/
**Audit date:** 2026-08-21  
**Final benchmark commit:** a5168298  
**Environment:** Python 3.12.3 | CmdStan 2.33.1 (Prophet enabled) | seed=42

---

## Audit Scope

Primary file audited: `docs/document_journalpaper/Vikas_UnifiedTelecomAnalyzer_ProjectReport.docx`

---

## Evaluation Methodology Note

The paper originally used a **scenario-level** evaluation that produced different TP/FP counts than the final cell-level benchmark scripts. The final authoritative evaluation uses:
- **Cell-level, 16 cells total, 3 ground-truth fault cells**
- Evaluation script: `scripts/run_detection_benchmark.py`
- Evaluator: `src/evaluation/detection_metrics.py`

The paper's results section has been updated to reflect final cell-level benchmark results.

---

## Quantitative Claims — Before/After

| Location | Old Claim | Final Verified Result | Action Taken |
|----------|-----------|----------------------|--------------|
| Abstract/Intro | "achieving F1 0.86" | Stats CT: F1=1.00; Ensemble: F1=0.316 | ✅ Replaced |
| Abstract/Results | "F1 = 0.22 (threshold-only)" | Threshold-only: F1=0.600 | ✅ Replaced |
| Abstract/Results | "Isolation Forest, F1 0.50" | IF not in final benchmark; IQR-only F1=0.316 | ✅ Replaced |
| Requirements | "evaluated at 57 sec" | Fresh benchmark: 40.1 s | ✅ Replaced |
| Results Section | "F1 0.86 — gain of +0.64 over threshold-only (F1 0.22)" | Corrected to fresh results | ✅ Replaced |
| Results Section | "single false positive" (contradicts FP=13 for ensemble) | Updated to reflect cell-level FP count | ✅ Replaced context |
| Code Section | "56 tests" | 173 tests | ✅ Replaced |
| Summary | "57 sec latency" | ~40 s | ✅ Replaced |

---

## Remaining Section Notes

### Abstract (Updated)
- Detection: Stats Count-Threshold F1=1.00; Full Ensemble F1=0.316; Threshold-only F1=0.600 ✅
- Latency: ~40 s (tracemalloc peak: ~12 MB per stage) ✅
- Tests: 173 automated tests ✅

### Methodology
- Evaluation is cell-level (16 cells, 3 fault cells, seed=42) ✅ — clearly stated in benchmark scripts
- Three detection methods compared: threshold-only, full ensemble, stats count-threshold ✅
- Isolation Forest NOT in final benchmark — comparison table updated to remove IF column or mark as "not benchmarked" ✅

### Experimental Setup
- Topology: 4 gNB / 16 cells / 64 UEs / 6 hr ✅
- Capacity: TDD DL=1400, UL=100; FDD DL=84, UL=50 ✅
- Fault cells: PCI_3 (congestion), PCI_12 (outage), PCI_8 (drift) ✅
- Random seed 42 ✅
- Dataset is synthetic — clearly described as "controlled synthetic testbed" ✅

### Results Tables (Verified Values)

**Table 9.3 — Scenario-level detection benchmark (updated to cell-level):**

| Method | TP | FP | FN | Precision | Recall | F1 |
|--------|----|----|----|-----------|----|-----|
| Threshold-only (KPI) | 3 | 4 | 0 | 0.4286 | 1.000 | 0.600 |
| IQR-only (KPI) | 3 | 13 | 0 | 0.1875 | 1.000 | 0.316 |
| Full Ensemble (KPI+Stats) | 3 | 13 | 0 | 0.1875 | 1.000 | 0.316 |
| Ensemble + EventRouter | 3 | 13 | 0 | 0.1875 | 1.000 | 0.316 |
| Stats Count-Threshold ★ | 3 | 0 | 0 | 1.000 | 1.000 | 1.000 |

**Table 9.5 — Per-stage pipeline latency (fresh benchmark):**

| Stage | Latency | Peak (tracemalloc) |
|-------|---------|-------------------|
| PCAP parse (901 pkts) | 2.6 s | 1.1 MB |
| KPI parse (5,760 rows) | 0.8 s | 10.7 MB |
| KPI detection (6 detectors) | 27.8 s | 10.9 MB |
| Stats parse + detect (5,760 rows) | 4.6 s | 12.1 MB |
| Correlation (1,427 events) | 4.3 s | 1.6 MB |
| **TOTAL** | **40.1 s** | **~12 MB peak** |

**Forecast Results (fresh benchmark, seed=42, 220 series):**

| Method | MAE | RMSE | MAPE | Lead Det/Total |
|--------|-----|------|------|---------------|
| Holt-Winters | 14.97 | 20.39 | 45.10% | 0/6 |
| LSTM | 19.78 | 23.63 | 55.76% | 0/6 |
| Prophet | 22.43 | 31.14 | 72.80% | 1/6 (false alarm) |

Note: Lead-time = 0 for HW/LSTM is an honest negative finding — abrupt step-change anomalies have no learnable precursor. Prophet's 1 detection is a false alarm (1 false_alarm recorded).

**RCA Results (fresh benchmark):**

| Cell | Fault | Keyword Hit Rate | Pass |
|------|-------|-----------------|------|
| PCI_3 | Congestion | 0.50 | ✅ YES |
| PCI_12 | Outage | 0.714 | ✅ YES |
| PCI_8 | Drift | 0.333 | ✅ YES |

Overall: 3/3 fault cells diagnosed (keyword matching; no Top-1/Top-3/MRR — evaluator does not rank candidates).

---

## Items NOT Changed

1. **Methodology description** — The paper's evaluation protocol description was kept; the numerical results were updated to match the final cell-level benchmark.
2. **Latency analysis narrative** — Updated the cited latency from 57 s to ~40 s but retained the analytical reasoning.
3. **Prophet forecasting** — Updated; Prophet IS executed in this environment (CmdStan 2.33.1 installed).

---

## Items Still Requiring Manual Review Before Submission

1. **Table 9.3 formatting** — The numbers in the docx body text have been corrected, but actual table cells in the Word table may need manual formatting verification.
2. **Figure captions** — Figure 9.1 caption references F1 comparison — verify it matches updated table.
3. **Section 9.4 (Ablation)** — References "single false positive on PCI_9" which contradicts FP=13. This was part of the old scenario-level evaluation. Needs methodological clarification in the paper.
4. **Forecasting section** — If the paper has a dedicated section on forecasting results (MAE/RMSE), verify it shows fresh numbers (HW=14.97, LSTM=19.78, Prophet=22.43).
5. **Placeholders** — Paper still contains `[Guide Name]`, `[USN / Roll Number]`, `[Month – Month, Year]` — these are non-benchmark placeholders to be filled by the candidate.

---

**JOURNAL PAPER STATUS: CRITICAL NUMERICAL ERRORS CORRECTED (17 replacements)**  
**Action required before submission: Manual review of tables and figures**
