# Week 1 Action Guide

This is your first week of coding. Goal: **walking skeleton running on
your machine, first commit pushed to GitHub.**

Total estimated time: **8-10 hours** spread across the week.

---

## Day 1-2 (Saturday-Sunday) — Setup (4-5 hours)

Follow `docs/SETUP.md` from start to finish. Don't skip steps.

**End of Day 2 deliverable:**
- Ubuntu 22.04 running in WSL2
- VS Code connected to WSL
- Conda environment `telecom` created
- `tshark --version`, `ollama --version`, `docker --version` all work
- Phi-3 Mini downloaded and tested

If something breaks, **stop and fix it before moving on**. Setup issues
compound — a broken tshark in week 1 becomes a parser nightmare in week 3.

---

## Day 3 (one weekday evening) — Run the skeleton (1 hour)

```bash
cd ~/projects/telecom-analyzer
conda activate telecom
streamlit run src/dashboard/app.py
```

Open browser, upload any small file, verify each section appears:
- Parsed summary metrics
- Anomalies table
- LLM explanation
- Feedback widget

**End of Day 3 deliverable:** Screenshot of the running dashboard.

---

## Day 4 (one weekday evening) — Tests + first commit (1 hour)

```bash
make test       # all tests should pass
make lint       # no errors
make format     # auto-formats code
```

Then your first real commit:
```bash
git add .
git commit -m "feat: walking skeleton with stub pipeline"
git push origin main
```

Verify GitHub Actions CI passes (green checkmark on the commit).

---

## Day 5-6 (next weekend) — Replace first stub (3-4 hours)

This is the **first real coding** of your project. Goal: replace the
PCAP parser stub with real `pyshark` parsing.

**Scope for this exercise (intentionally narrow):**

1. Write `src/parsers/pcap_parser_real.py` that:
   - Takes a PCAP file path
   - Uses `pyshark.FileCapture` to iterate packets
   - Counts how many packets are NGAP, NAS, RRC, total
2. Update the dashboard to call the real parser when a PCAP is uploaded
3. Keep the stub for non-PCAP types (DU/CU, KPI) for now
4. Add a test in `tests/test_pcap_parser_real.py` using a tiny PCAP fixture

**Test PCAP files to use (download once, save under `tests/fixtures/`):**

- `free5gc.pcap` from telekom/5g-trace-visualizer GitHub
- Any small capture from Wireshark sample-captures wiki

**End of Week 1 deliverable:**
- Real PCAP parsing for packet counts (procedure aggregation comes
  in Week 2-3)
- Dashboard shows real numbers when you upload a real PCAP
- Test suite still green
- Commit message: `feat(parser): real pyshark-based packet counting`

---

## Anti-patterns to avoid this week

❌ **Don't try to implement procedure tracking yet.**
   That's Week 2-3 work. This week is just packet counting.

❌ **Don't add new dependencies unless you actually need them.**
   `requirements.txt` is locked. Adding things bloats the env.

❌ **Don't refactor the folder structure.**
   It's intentional. Refactoring before you have working code wastes time.

❌ **Don't write code without committing.**
   At least one commit per coding session, even if work is incomplete.
   Use feature branches if commits are very rough.

❌ **Don't run Phi-3 Mini in a loop while developing.**
   Each call uses ~3 GB RAM. Keep it for explicit testing only.

---

## What success looks like by end of Week 1

When your guide asks "what did you do this week?", you can show:

1. ✅ Full local environment working (WSL2, conda, tshark, Ollama, Docker)
2. ✅ Streamlit dashboard runs end-to-end with stub pipeline
3. ✅ Real PCAP parser counts NGAP/NAS/RRC packets correctly
4. ✅ Tests passing locally and in GitHub Actions
5. ✅ At least 3 commits on GitHub with meaningful messages

This is **30-40% of your "First Review" target** (PES guideline expects
30% code at First Review). You will be on track.

---

## When things go wrong

- **Setup issues:** `docs/SETUP.md` troubleshooting section
- **Code questions:** ask Claude with specific error messages
- **Stuck for >2 hours:** stop, switch to a different sub-task, come back
- **Guide meeting:** show what works, ask specific questions, don't
  pretend things work when they don't

Good luck. The first week is the hardest. After this, momentum carries
you forward.
