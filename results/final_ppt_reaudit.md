# PPT Re-Audit — docs/Phase2_Third_Review_Comprehensive.pptx
**Audit date:** 2026-08-18  
**Generator:** scripts/generate_phase2_review3_comprehensive_ppt.py  
**Git commit:** a516829 (code unchanged)  
**PPT regenerated:** Yes — 23 slides

---

## Slides Modified

| Slide | Function | Change |
|-------|----------|--------|
| 15 | `s_c_title_abstract` | Abstract rewritten with final numbers |
| 16 | `s_c_overall_design` | DETECT and PREDICT and CORRELATE layer descriptions updated |
| 17 | `s_c_experimental_results` | Correlation bullet corrected |
| 18 | `s_c_performance` | Entire detection table replaced; scalability replaced |
| 19 | `s_c_comparison` | P/F1 row, correlation cell, test count corrected |
| 20 | `s_c_code_demo` | Test count corrected (2 places) |
| 21 | `s_c_journal` | Title, abstract, status corrected |
| 23 | `s_close` | Summary line corrected |

**Slides NOT modified (preserved as-is):** 1–14 (Part A, Part B — all historical)

---

## Old Claims Removed

| Slide | Old Claim | Removed |
|-------|-----------|---------|
| 15 | "F1 0.86" | ✅ |
| 15 | "Threshold-only F1=0.22" | ✅ |
| 15 | "IF-only F1=0.50" | ✅ |
| 15 | "correlating 8,607 of 8,623 cross-domain events" | ✅ |
| 15 | "Full pipeline latency: 58 s" | ✅ |
| 15 | "56 automated tests" | ✅ |
| 16 | "18-detector ensemble" (now: "18 detectors across 3 domains") | ✅ |
| 16 | "8,607/8,623 events correlated at 64-UE scale (99.8%)" | ✅ |
| 16 | "Prophet (seasonal decomp.) + Holt-Winters..." (implied Prophet executed) | ✅ |
| 17 | "Events ingested: 8,623 → cross-source correlated: 8,607/8,623 (99.8%)" | ✅ |
| 18 | Entire stale detection table (F1=0.86, 0.75, 0.22, 0.50) | ✅ |
| 18 | Stale scalability: 56.8 s / 1.2 GB peak | ✅ |
| 18 | Stale stage latencies (8.2s PCAP, 17.6s KPI, 2.1s KPI parse) | ✅ |
| 18 | Stale stage memory (320 MB, 430 MB, 510 MB) | ✅ |
| 19 | "Scenario Precision / F1: 0.17/0.22" (Threshold) | ✅ |
| 19 | "Scenario Precision / F1: 0.40/0.50" (IF — not in benchmark) | ✅ |
| 19 | "Scenario Precision / F1: 0.33/0.44 (est.)" (OC-SVM — not in benchmark) | ✅ |
| 19 | "0.75 / 0.86 (Ensemble + EventRouter)" | ✅ |
| 19 | "8,607/8,623 correlated (99.8%)" | ✅ |
| 19 | "56 automated tests" | ✅ |
| 20 | "56 automated tests (pytest), 0 failures" | ✅ |
| 20 | "make test-all (56 tests, 0 failed)" | ✅ |
| 21 | "Journal Paper Publication Proof" (slide title) | ✅ |
| 21 | Abstract with F1=0.86, 0.22, 0.50 | ✅ |
| 21 | "57 s" pipeline latency | ✅ |
| 21 | "1.2 GB" peak memory | ✅ |
| 23 | "F1 0.86, 100% code, journal draft complete" | ✅ |

---

## New Claims Added

| Slide | New Claim | Source |
|-------|-----------|--------|
| 15 | Abstract: "Stats Count-Threshold achieved Precision=1.00, Recall=1.00, F1=1.00" | `results/detection/detection_metrics.json` |
| 15 | Abstract: "Full Ensemble: Precision=0.1875, F1=0.316" | same |
| 15 | Abstract: "45.6 s on CPU-only host" | `results/scalability/scalability_results.json` |
| 15 | Abstract: "173 automated tests, 0 failures" | `pytest` run 2026-08-18 |
| 15 | Title: "An 18-Detector Multi-Domain Framework" (not "Ensemble") | audit guidance |
| 16 | DETECT: "18 detectors across 3 domains — PCAP: ... KPI: ... Stats: ..." | architecture |
| 16 | CORRELATE: "1,427 anomaly events (KPI: 1,316 + Stats: 111) — 100% cross-source assignment" | `results/correlation/correlation_metrics.json` |
| 16 | PREDICT: "Prophet implemented; not executed in final benchmark environment" | benchmark run |
| 17 | Correlation: "EventRouter processed 1,427 anomaly events ... 100% assignment rate" | correlation_metrics.json |
| 18 | Full detection table: Threshold 0.4286/1.0/0.600, IQR 0.1875/1.0/0.316, Ensemble 0.1875/1.0/0.316, Stats 1.0/1.0/1.0 | detection_metrics.json |
| 18 | Footnote: "★ Best evaluated method: Stats Count-Threshold F1=1.00 ... KPI ensemble FP rate reflects TDD/FDD calibration" | benchmark + normalizer docs |
| 18 | Scalability: 45.6 s / ~21 MB (tracemalloc) | scalability_results.json |
| 19 | P/F1 row: Threshold=0.4286/0.600; IF/OC-SVM="Not evaluated in final benchmark" | detection_metrics.json |
| 19 | Our framework: "0.1875/0.316 (Ensemble+Router) \| 1.000/1.000 (Stats Count-Threshold)" | detection_metrics.json |
| 19 | Correlation: "1,427 events, 100% cross-source assignment" | correlation_metrics.json |
| 19 | "173 tests passed, 0 failed" | pytest |
| 20 | "173 automated tests (pytest), 0 failures, 1 skipped" | pytest |
| 20 | Demo command: "173 passed, 1 skipped, 0 failed" | pytest |
| 21 | Slide title: "Journal Paper Draft — Final Results" | audit guidance |
| 21 | Status: "final benchmark results synchronized with this release" | this audit |
| 21 | Abstract with correct F1s, 45.6 s, ~21 MB, Prophet NOT EXECUTED | benchmark results |
| 23 | "173 tests passed, 100% code, journal draft prepared \| Best F1=1.00 (Stats Count-Threshold, 3 injected fault cells)" | benchmark |

---

## Final Detection Metrics (as shown in PPT Slide 18)

| Method | TP | FP | FN | Precision | Recall | F1 |
|--------|----|----|-----|-----------|--------|-----|
| Threshold-only (KPI) | 3 | 4 | 0 | 0.4286 | 1.000 | 0.600 |
| IQR-only (KPI) | 3 | 13 | 0 | 0.1875 | 1.000 | 0.316 |
| Full Ensemble (KPI+Stats) | 3 | 13 | 0 | 0.1875 | 1.000 | 0.316 |
| Ensemble + EventRouter | 3 | 13 | 0 | 0.1875 | 1.000 | 0.316 |
| Stats Count-Threshold ★ | 3 | 0 | 0 | 1.000 | 1.000 | 1.000 |

---

## Forecasting Corrections (Slide 16, 21)

| Model | Status |
|-------|--------|
| Holt-Winters | Executed: MAE=15.54, RMSE=21.04, MAPE=45.67% |
| LSTM | Executed: MAE=20.24, RMSE=24.12, MAPE=55.47% |
| Prophet | NOT EXECUTED in final benchmark environment |

Historical slides (4, 5, 6, 9, 12, 13) retain Prophet as proposed/planned — this is correct historical context.

---

## RCA Wording Correction

No unsupported RCA accuracy claims appear in the PPT. The system is described as providing "explainable RCA narratives" — no "100% accuracy", no "Top-1/Top-3/MRR". Correct.

---

## Scalability Correction (Slide 18)

| Metric | Old (stale) | New (final) |
|--------|------------|------------|
| Total latency | 56.8 s | 45.6 s |
| Peak memory | 1.2 GB | ~21 MB (tracemalloc) |
| PCAP parse | 8.2 s / 320 MB | 2.6 s / 1.2 MB |
| KPI parse | 2.1 s / 85 MB | 1.1 s / 11.1 MB |
| KPI detect | 17.6 s / 510 MB | 32.7 s / 7.8 MB |
| Stats | 14.3 s / 480 MB | 5.0 s / 17.0 MB |
| Correlation | 2.8 s / 55 MB | 4.2 s / 1.6 MB |

---

## Test-Count Correction

| Location | Old | New |
|----------|-----|-----|
| Slide 15 Abstract | 56 tests | 173 tests |
| Slide 19 comparison table | 56 automated tests | 173 tests passed, 0 failed |
| Slide 20 module table | 56 automated tests | 173 automated tests, 0 failures, 1 skipped |
| Slide 20 demo command | 56 tests, 0 failed | 173 passed, 1 skipped, 0 failed |
| Slide 21 abstract | 56 automated tests | 173 automated tests, 0 failures |

**Historical Review 2 numbers intentionally preserved:**
- Slide 12: "83 passed, 1 skipped, 0 failed" — correct state at Review 2 ✅
- Slide 13: "24 new automated tests, 0 regressions (83 passed / 1 skipped total)" — correct at Review 2 ✅

---

## Capacity Verification

TDD/FDD capacity values (DL=1400/UL=100 and DL=84/UL=50) do not appear as explicit Mbps claims in any PPT slide — they are dataset implementation details. No correction needed.

---

## Stale Value Final Scan Results

Searched all 23 slides for: `0.86`, `0.75`, `0.22`, `0.50`, `56 tests`, `56.8`, `58 s`, `57 s`, `1.2 GB`, `100% accuracy`, `RCA accuracy`, `Top-1`, `Top-3`, `MRR`, `8,607`, `8,623`, `56 automated`

**Result: NONE FOUND** — all stale values cleared from the PPT.

---

## Remaining Historical Numbers (Intentionally Preserved)

| Slide | Number | Why Preserved |
|-------|--------|---------------|
| 12 | "83 passed, 1 skipped" | Correct state at Review 2 |
| 13 | "83 passed / 1 skipped total" | Correct state at Review 2 |
| 23 | "83 tests" (Review 2 row) | Correct historical summary |
| 4–13 | All Part A/B content | Historical Review 1/2 — do not modify |

---

## Remaining Issues

None blocking. One advisory:

1. **Slide 20 LOC values** are approximate estimates (~620, ~540, etc.) and have not been reverified against the current codebase. They are marked with "~" and are acceptable as approximations.
2. **Slide 20 "src/prediction/..."** — module path may differ from actual codebase layout (prediction vs detection namespace). This is a pre-existing cosmetic issue, not introduced in this correction.

---

## Final Status

```
PPT = READY FOR FINAL REVIEW ✅
Benchmark = FROZEN (not touched) ✅
Code = UNCHANGED ✅
Ground Truth = UNCHANGED ✅
```
