"""
Generate a full 6-hour correlated demo dataset:
  data/raw/demo_6hr_kpi.csv           – KPI @ 5-min intervals, 4 cells
  data/raw/demo_6hr_stats.csv         – DU/CU srsRAN stats @ 1-min, 4 cells
  data/raw/PCAPCONVERSION/demo_6hr_pcap.csv – Wireshark-style PCAP CSV

Three correlated anomaly events are injected so the dashboard's
cross-source correlation engine fires on upload:
  Event A  (Hour 1.5) – PRB congestion spike on PCI_2
  Event B  (Hour 3.0) – SNR degradation + HO failure on PCI_3
  Event C  (Hour 5.0) – RRC drop cascade on PCI_1 & PCI_4 (multi-cell)

Usage:
  python scripts/generate_6hr_demo.py
"""

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

rng = np.random.default_rng(42)

# ── constants ────────────────────────────────────────────────────────────────
CELLS    = ["PCI_1", "PCI_2", "PCI_3", "PCI_4"]
GNBS     = {"PCI_1": "gNB-1", "PCI_2": "gNB-1", "PCI_3": "gNB-2", "PCI_4": "gNB-2"}
HOURS    = 6
NOW      = datetime.now().replace(second=0, microsecond=0)
START    = NOW - timedelta(hours=HOURS)

# Anomaly windows (start_hour, end_hour, affected_cells, type)
EVENTS = [
    (1.5, 2.5,  ["PCI_2"],           "prb_congestion"),
    (3.0, 4.0,  ["PCI_3"],           "snr_degradation"),
    (5.0, 5.75, ["PCI_1", "PCI_4"], "rrc_drop_cascade"),
]

# PCAP protocol mix
PROTOCOLS = ["NAS-5GS", "NGAP", "PFCP", "GTPv2", "HTTP/2", "DNS", "ICMP", "UDP", "RRC"]
PROTO_W   = [0.20, 0.18, 0.12, 0.10, 0.15, 0.10, 0.05, 0.07, 0.03]
SRC_IPS   = ["10.0.0.1", "10.0.0.2", "10.1.0.1", "10.1.0.2",
             "192.168.1.10", "192.168.1.11", "172.16.0.1", "172.16.0.2"]
DST_IPS   = ["10.0.0.10", "10.0.0.11", "10.1.0.10", "10.1.0.11",
             "192.168.2.10", "192.168.2.11", "172.16.1.1", "172.16.1.2"]

NAS_MSGS  = ["Registration Request", "Registration Accept", "Authentication Request",
             "Authentication Response", "PDU Session Establishment", "Deregistration Request"]
NGAP_MSGS = ["InitialUEMessage", "InitialContextSetupRequest", "PathSwitchRequest",
             "HandoverRequest", "UEContextReleaseRequest", "NGSetupRequest"]
RRC_MSGS  = ["RRCSetup", "RRCSetupComplete", "RRCReconfiguration",
             "RRCReconfigurationComplete", "MeasurementReport", "RRCRelease"]


# ── helpers ──────────────────────────────────────────────────────────────────
def _ramp(frac: float, healthy, critical):
    return healthy + (critical - healthy) * frac

def _noise(scale=1.0):
    return rng.normal(0, scale)

def _event_frac(hour_offset: float, cell: str) -> float:
    """Return 0-1 severity fraction for this cell at this time."""
    for (h_start, h_end, cells, _) in EVENTS:
        if cell in cells and h_start <= hour_offset <= h_end:
            duration = h_end - h_start
            mid      = h_start + duration / 2
            frac     = 1.0 - abs(hour_offset - mid) / (duration / 2)
            return max(0.0, min(1.0, frac))
    return 0.0

def _event_type(hour_offset: float, cell: str) -> str:
    for (h_start, h_end, cells, etype) in EVENTS:
        if cell in cells and h_start <= hour_offset <= h_end:
            return etype
    return "normal"


# ── KPI generator ────────────────────────────────────────────────────────────
def gen_kpi() -> pd.DataFrame:
    step_min = 5
    steps    = HOURS * 60 // step_min + 1
    rows     = []

    for i in range(steps):
        ts           = START + timedelta(minutes=step_min * i)
        hour_offset  = i * step_min / 60
        # Traffic load follows a realistic diurnal pattern
        load_factor  = 0.5 + 0.5 * np.sin(np.pi * hour_offset / HOURS)

        for cell in CELLS:
            f     = _event_frac(hour_offset, cell)
            etype = _event_type(hour_offset, cell)

            # Base values modulated by load
            base_dl = 200 + 150 * load_factor
            base_ul = 70  + 50  * load_factor

            if etype == "prb_congestion":
                dl_tp   = round(_ramp(f, base_dl, 15.0)  + _noise(2), 2)
                ul_tp   = round(_ramp(f, base_ul,  5.0)  + _noise(1), 2)
                prb_dl  = round(_ramp(f, 38.0, 99.5)     + _noise(0.3), 2)
                prb_ul  = round(_ramp(f, 31.0, 97.0)     + _noise(0.3), 2)
                lat     = round(_ramp(f,  8.0, 85.0)     + _noise(0.5), 2)
                rrc_dr  = round(_ramp(f,  0.2,  4.5)     + _noise(0.05), 3)
                ho_sr   = round(_ramp(f, 98.5, 93.0)     + _noise(0.1), 3)
                avail   = round(_ramp(f, 99.9, 98.5)     + _noise(0.05), 3)
                rrc_sr  = round(_ramp(f, 99.9, 97.5)     + _noise(0.05), 3)
            elif etype == "snr_degradation":
                dl_tp   = round(_ramp(f, base_dl, 25.0)  + _noise(2), 2)
                ul_tp   = round(_ramp(f, base_ul, 10.0)  + _noise(1), 2)
                prb_dl  = round(_ramp(f, 38.0, 88.0)     + _noise(0.5), 2)
                prb_ul  = round(_ramp(f, 31.0, 80.0)     + _noise(0.5), 2)
                lat     = round(_ramp(f,  8.0, 55.0)     + _noise(0.5), 2)
                rrc_dr  = round(_ramp(f,  0.2,  3.8)     + _noise(0.05), 3)
                ho_sr   = round(_ramp(f, 98.5, 82.0)     + _noise(0.2), 3)
                avail   = round(_ramp(f, 99.9, 97.5)     + _noise(0.05), 3)
                rrc_sr  = round(_ramp(f, 99.9, 96.5)     + _noise(0.05), 3)
            elif etype == "rrc_drop_cascade":
                dl_tp   = round(_ramp(f, base_dl, 40.0)  + _noise(3), 2)
                ul_tp   = round(_ramp(f, base_ul, 15.0)  + _noise(1), 2)
                prb_dl  = round(_ramp(f, 38.0, 70.0)     + _noise(0.5), 2)
                prb_ul  = round(_ramp(f, 31.0, 65.0)     + _noise(0.5), 2)
                lat     = round(_ramp(f,  8.0, 42.0)     + _noise(0.3), 2)
                rrc_dr  = round(_ramp(f,  0.2,  8.5)     + _noise(0.1), 3)
                ho_sr   = round(_ramp(f, 98.5, 88.0)     + _noise(0.2), 3)
                avail   = round(_ramp(f, 99.9, 96.0)     + _noise(0.05), 3)
                rrc_sr  = round(_ramp(f, 99.9, 91.0)     + _noise(0.1), 3)
            else:
                dl_tp   = round(base_dl + _noise(3), 2)
                ul_tp   = round(base_ul + _noise(1), 2)
                prb_dl  = round(35.0 + 10 * load_factor + _noise(0.5), 2)
                prb_ul  = round(28.0 +  8 * load_factor + _noise(0.5), 2)
                lat     = round(7.5 + _noise(0.3), 2)
                rrc_dr  = round(0.15 + _noise(0.02), 3)
                ho_sr   = round(98.5 + _noise(0.1), 3)
                avail   = round(99.9 + _noise(0.02), 3)
                rrc_sr  = round(99.9 + _noise(0.05), 3)

            ho_att = int(rng.integers(18, 35))
            rows.append({
                "Timestamp":                   ts.isoformat(),
                "Cell_ID":                     cell,
                "gNB_ID":                      GNBS[cell],
                "Channel_Type":                "TDD",
                "Cell_Availability_%":         min(100.0, max(0.0, avail)),
                "RRC_Connection_Attempts":     int(rng.integers(250, 350)),
                "RRC_Connection_Rejects":      max(0, int(_ramp(f, 0.5, 30) + _noise(1))),
                "RRC_Success_Rate_%":          min(100.0, max(0.0, rrc_sr)),
                "Avg_RRC_Connected_Users":     round(float(40 + 30 * load_factor + _noise(2)), 1),
                "Peak_RRC_Connected_Users":    round(float(55 + 35 * load_factor + _noise(2)), 1),
                "Registration_Success_Rate_%": min(100.0, max(0.0, round(_ramp(f, 99.6, 90.0) + _noise(0.05), 3))),
                "PDU_Session_Success_Rate_%":  min(100.0, max(0.0, round(_ramp(f, 99.3, 91.0) + _noise(0.05), 3))),
                "RRC_Drop_Rate_%":             max(0.0, rrc_dr),
                "Handover_Attempts":           ho_att,
                "Handover_Success_Rate_%":     min(100.0, max(0.0, ho_sr)),
                "Xn_HO_Prep_Success_Rate_%":   min(100.0, max(0.0, round(_ramp(f, 98.9, 88.0) + _noise(0.1), 3))),
                "Xn_HO_Exec_Success_Rate_%":   min(100.0, max(0.0, round(_ramp(f, 98.8, 88.0) + _noise(0.1), 3))),
                "NG_HO_Prep_Success_Rate_%":   min(100.0, max(0.0, round(_ramp(f, 98.4, 87.0) + _noise(0.1), 3))),
                "NG_HO_Exec_Success_Rate_%":   min(100.0, max(0.0, round(_ramp(f, 98.0, 87.0) + _noise(0.1), 3))),
                "PRB_Utilization_DL_%":        min(100.0, max(0.0, prb_dl)),
                "PRB_Utilization_UL_%":        min(100.0, max(0.0, prb_ul)),
                "DL_Throughput_Mbps":          max(0.0, dl_tp),
                "UL_Throughput_Mbps":          max(0.0, ul_tp),
                "Total_Traffic_GB":            round(float(dl_tp * step_min * 60 / 8 / 1e3 + _noise(0.01)), 5),
                "RACH_Success_Rate_%":         min(100.0, max(0.0, round(_ramp(f, 99.1, 91.0) + _noise(0.1), 3))),
                "Latency_ms":                  max(1.0, lat),
            })

    return pd.DataFrame(rows)


# ── DU/CU Stats generator ─────────────────────────────────────────────────────
def gen_stats() -> pd.DataFrame:
    step_min = 1
    steps    = HOURS * 60 + 1
    rows     = []

    for i in range(steps):
        ts          = START + timedelta(minutes=step_min * i)
        hour_offset = i / 60
        load_factor = 0.5 + 0.5 * np.sin(np.pi * hour_offset / HOURS)

        for cell in CELLS:
            f     = _event_frac(hour_offset, cell)
            etype = _event_type(hour_offset, cell)

            nof_ue = max(1, int(round(8 + 56 * load_factor + _noise(3))))

            if etype == "prb_congestion":
                dl_brate = float(_ramp(f, 55e6, 2.5e6) + _noise(1e6))
                ul_brate = float(_ramp(f, 22e6, 1.2e6) + _noise(0.5e6))
                dl_prb   = int(round(_ramp(f, 35, 99)))
                ul_prb   = int(round(_ramp(f, 28, 97)))
                dl_mcs   = round(_ramp(f, 14.0, 3.0), 1)
                ul_mcs   = round(_ramp(f, 13.0, 2.5), 1)
                snr_p    = round(_ramp(f, 18.0, 14.0) + _noise(0.3), 2)
                snr_c    = round(_ramp(f, 20.0, 15.0) + _noise(0.3), 2)
                dl_nok   = max(0, int(_ramp(f, 12, 450) + _noise(10)))
                ul_nok   = max(0, int(_ramp(f,  8, 360) + _noise(8)))
            elif etype == "snr_degradation":
                dl_brate = float(_ramp(f, 55e6, 5e6)   + _noise(1e6))
                ul_brate = float(_ramp(f, 22e6, 2e6)   + _noise(0.5e6))
                dl_prb   = int(round(_ramp(f, 35, 88)))
                ul_prb   = int(round(_ramp(f, 28, 82)))
                dl_mcs   = round(_ramp(f, 14.0, 1.5), 1)
                ul_mcs   = round(_ramp(f, 13.0, 1.0), 1)
                snr_p    = round(_ramp(f, 18.0, -4.0)  + _noise(0.5), 2)
                snr_c    = round(_ramp(f, 20.0, -2.0)  + _noise(0.5), 2)
                dl_nok   = max(0, int(_ramp(f, 12, 380) + _noise(10)))
                ul_nok   = max(0, int(_ramp(f,  8, 300) + _noise(8)))
            elif etype == "rrc_drop_cascade":
                dl_brate = float(_ramp(f, 55e6, 8e6)   + _noise(1e6))
                ul_brate = float(_ramp(f, 22e6, 3e6)   + _noise(0.5e6))
                dl_prb   = int(round(_ramp(f, 35, 72)))
                ul_prb   = int(round(_ramp(f, 28, 65)))
                dl_mcs   = round(_ramp(f, 14.0, 4.0), 1)
                ul_mcs   = round(_ramp(f, 13.0, 3.5), 1)
                snr_p    = round(_ramp(f, 18.0,  6.0)  + _noise(0.3), 2)
                snr_c    = round(_ramp(f, 20.0,  8.0)  + _noise(0.3), 2)
                dl_nok   = max(0, int(_ramp(f, 12, 280) + _noise(10)))
                ul_nok   = max(0, int(_ramp(f,  8, 220) + _noise(8)))
            else:
                dl_brate = float(50e6 + 20e6 * load_factor + _noise(1e6))
                ul_brate = float(20e6 +  8e6 * load_factor + _noise(0.5e6))
                dl_prb   = max(1, int(round(28 + 18 * load_factor + _noise(1))))
                ul_prb   = max(1, int(round(22 + 14 * load_factor + _noise(1))))
                dl_mcs   = round(13.5 + _noise(0.3), 1)
                ul_mcs   = round(12.5 + _noise(0.3), 1)
                snr_p    = round(18.0 + _noise(0.4), 2)
                snr_c    = round(20.0 + _noise(0.4), 2)
                dl_nok   = max(0, int(rng.integers(5, 25)))
                ul_nok   = max(0, int(rng.integers(3, 18)))

            dl_ok = max(1, int(rng.integers(800, 1200)))
            ul_ok = max(1, int(rng.integers(600, 1000)))

            label = "Anomaly" if f > 0.25 else "Normal"

            rows.append({
                "timestamp":    ts.isoformat(),
                "pci":          cell,
                "cell_type":    "TDD",
                "nof_ue":       nof_ue,
                "dl_brate":     round(max(0, dl_brate), 0),
                "ul_brate":     round(max(0, ul_brate), 0),
                "dl_nof_ok":    dl_ok,
                "dl_nof_nok":   dl_nok,
                "ul_nof_ok":    ul_ok,
                "ul_nof_nok":   ul_nok,
                "dl_mcs":       max(0.0, dl_mcs),
                "ul_mcs":       max(0.0, ul_mcs),
                "dl_prb":       min(100, max(0, dl_prb)),
                "ul_prb":       min(100, max(0, ul_prb)),
                "pusch_snr_db": snr_p,
                "pucch_snr_db": snr_c,
                "anomaly_label": label,
            })

    return pd.DataFrame(rows)


# ── PCAP CSV generator ────────────────────────────────────────────────────────
def gen_pcap() -> pd.DataFrame:
    """Wireshark-style CSV: No., Time, Source, Destination, Protocol, Length, Info"""
    rows        = []
    pkt_no      = 1
    t_sec       = 0.0          # relative time in seconds
    interval    = 0.25         # avg ~4 packets/sec per cell pair
    total_secs  = HOURS * 3600

    # Inject anomaly bursts: high-frequency retransmit storms
    anomaly_windows = []
    for (h_start, h_end, cells, etype) in EVENTS:
        anomaly_windows.append((h_start * 3600, h_end * 3600, cells, etype))

    def _in_anomaly(t):
        for (ws, we, cells, etype) in anomaly_windows:
            if ws <= t <= we:
                return True, cells, etype
        return False, [], ""

    while t_sec < total_secs:
        in_anom, anom_cells, etype = _in_anomaly(t_sec)
        step = interval * (0.3 if in_anom else 1.0)  # more packets during anomaly
        t_sec += max(0.05, rng.exponential(step))
        if t_sec > total_secs:
            break

        proto = rng.choice(PROTOCOLS, p=PROTO_W)
        src   = rng.choice(SRC_IPS)
        dst   = rng.choice(DST_IPS)
        leng  = int(rng.integers(49, 1500))

        # Build info string
        if proto == "NAS-5GS":
            info = rng.choice(NAS_MSGS)
            if in_anom and etype == "rrc_drop_cascade":
                info = rng.choice(["Deregistration Request", "Registration Request",
                                   "Service Reject", "Authentication Failure"])
        elif proto == "NGAP":
            info = rng.choice(NGAP_MSGS)
            if in_anom and etype == "snr_degradation":
                info = rng.choice(["HandoverRequest", "PathSwitchRequest",
                                   "UEContextReleaseRequest", "HandoverFailure"])
        elif proto == "RRC":
            info = rng.choice(RRC_MSGS)
        elif proto in ("UDP", "HTTP/2"):
            sport = rng.integers(1024, 65535)
            dport = rng.integers(1024, 65535)
            info  = f"{sport}  >  {dport} Len={leng - 42}"
            if in_anom and etype == "prb_congestion":
                info += " [RETRANSMISSION]"
        elif proto == "GTPv2":
            info = rng.choice(["Create Session Request", "Create Session Response",
                               "Modify Bearer Request", "Delete Session Request"])
        elif proto == "PFCP":
            info = rng.choice(["Session Establishment Request", "Session Modification Request",
                               "Session Deletion Request", "Heartbeat Request"])
        elif proto == "DNS":
            info = rng.choice(["Standard query", "Standard query response"])
        elif proto == "ICMP":
            info = rng.choice(["Echo (ping) request", "Echo (ping) reply",
                               "Destination unreachable"])
        else:
            info = f"Packet {pkt_no}"

        rows.append({
            "No.":         pkt_no,
            "Time":        round(t_sec, 6),
            "Source":      src,
            "Destination": dst,
            "Protocol":    proto,
            "Length":      leng,
            "Info":        info,
        })
        pkt_no += 1

    df = pd.DataFrame(rows)
    return df


# ── main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    raw_dir  = Path("data/raw")
    pcap_dir = Path("data/raw/PCAPCONVERSION")
    raw_dir.mkdir(parents=True, exist_ok=True)
    pcap_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating 6-hour demo data  [{START.isoformat()} → {NOW.isoformat()}]")
    print()

    print("  [1/3] KPI data (5-min intervals, 4 cells) ...")
    kpi_df = gen_kpi()
    kpi_path = raw_dir / "demo_6hr_kpi.csv"
    kpi_df.to_csv(kpi_path, index=False)
    print(f"        ✅  {len(kpi_df):,} rows  →  {kpi_path}")

    print("  [2/3] DU/CU Stats (1-min intervals, 4 cells) ...")
    stats_df = gen_stats()
    stats_path = raw_dir / "demo_6hr_stats.csv"
    stats_df.to_csv(stats_path, index=False)
    print(f"        ✅  {len(stats_df):,} rows  →  {stats_path}")

    print("  [3/3] PCAP CSV (Wireshark format, 6 hrs of packets) ...")
    pcap_df = gen_pcap()
    pcap_path = pcap_dir / "demo_6hr_pcap.csv"
    # Quote all fields like Wireshark exports
    pcap_df.to_csv(pcap_path, index=False, quoting=1)
    print(f"        ✅  {len(pcap_df):,} packets  →  {pcap_path}")

    print()
    print("  Correlated anomaly events injected:")
    for h_start, h_end, cells, etype in EVENTS:
        ts_start = START + timedelta(hours=h_start)
        ts_end   = START + timedelta(hours=h_end)
        print(f"    • {etype.upper():22s}  {', '.join(cells):16s}  "
              f"{ts_start.strftime('%H:%M')} → {ts_end.strftime('%H:%M')}")
    print()
    print("  Upload order for demo:")
    print("    1. demo_6hr_kpi.csv   → KPI Analysis tab")
    print("    2. demo_6hr_stats.csv → DU/CU Stats tab")
    print("    3. demo_6hr_pcap.csv  → PCAP Analysis tab")
    print("    Cross-source correlation will fire automatically.")
