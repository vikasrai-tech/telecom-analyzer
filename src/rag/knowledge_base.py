"""
3GPP Specification Knowledge Base
===================================
Curated spec excerpts covering every procedure and failure cause
in the Unified Telecom Analyzer.

Each chunk has: spec, section, topic, keywords, text
"""

from typing import List, Dict, Any

SPEC_CHUNKS: List[Dict[str, Any]] = [

    # ─────────────────────────────────────────────────────────────────
    # NAS — TS 24.501 (5GMM)
    # ─────────────────────────────────────────────────────────────────
    {
        "spec": "TS 24.501", "section": "5.5.1.2",
        "topic": "NAS Registration procedure — overview",
        "keywords": ["registration", "NAS", "5GMM", "attach", "initial registration"],
        "text": (
            "The Registration procedure is used by the UE to register with the 5G network. "
            "Initial Registration is performed when the UE is in the 5GMM-DEREGISTERED state. "
            "Mobility Registration Update is performed when the UE has moved to a new Tracking Area. "
            "The AMF assigns a 5G-GUTI and allocates a TAI list to the UE upon successful registration. "
            "If registration fails, the AMF sends a Registration Reject message with a 5GMM cause value."
        ),
    },
    {
        "spec": "TS 24.501", "section": "5.5.1.2.5",
        "topic": "NAS Registration failure causes — congestion",
        "keywords": ["registration", "reject", "congestion", "cause 22", "#22", "overload"],
        "text": (
            "5GMM cause #22 — Congestion: The network rejects the UE's registration attempt because "
            "the AMF or the network is currently overloaded. The UE shall apply a back-off timer T3502 "
            "(default 12 minutes). Repeated congestion rejections indicate sustained AMF overload or "
            "insufficient AMF capacity. Engineers should check AMF CPU/memory utilisation and consider "
            "load balancing across AMF instances."
        ),
    },
    {
        "spec": "TS 24.501", "section": "5.5.1.2.5",
        "topic": "NAS Registration failure — PLMN not allowed",
        "keywords": ["registration", "reject", "PLMN", "cause 11", "not allowed"],
        "text": (
            "5GMM cause #11 — PLMN not allowed: The AMF rejects registration because the PLMN "
            "is not allowed for the UE's subscription. This is a permanent rejection — the UE shall "
            "not attempt registration on this PLMN. Commonly caused by misconfigured SUPI/subscription "
            "data in the UDM/AUSF or an international roaming UE attempting to attach without a valid "
            "roaming agreement."
        ),
    },
    {
        "spec": "TS 24.501", "section": "5.5.1.2.5",
        "topic": "NAS Registration failure — UE identity not derived",
        "keywords": ["registration", "reject", "UE identity", "cause 9", "security"],
        "text": (
            "5GMM cause #9 — UE identity cannot be derived by the network: The AMF cannot "
            "identify the UE from the provided SUCI or 5G-GUTI. This typically occurs after a "
            "context loss at the AMF (e.g., AMF restart or failover). The UE should retry with "
            "Initial Registration using a SUCI instead of 5G-GUTI."
        ),
    },
    {
        "spec": "TS 24.501", "section": "5.4.1",
        "topic": "NAS Authentication procedure",
        "keywords": ["authentication", "NAS", "AUSF", "SUCI", "5G-AKA", "EAP-AKA"],
        "text": (
            "The Authentication procedure is initiated by the AMF after receiving a Registration Request. "
            "The AMF sends an Authentication Request containing RAND and AUTN to the UE. "
            "The UE computes RES and sends it back in Authentication Response. "
            "If authentication fails, the AMF sends Authentication Reject with 5GMM cause #20 (MAC failure) "
            "or cause #26 (non-5G authentication unacceptable). "
            "Repeated auth failures indicate AUSF unreachability, UDM subscription errors, or SIM misconfiguration."
        ),
    },
    {
        "spec": "TS 24.501", "section": "5.4.2",
        "topic": "NAS Security Mode procedure",
        "keywords": ["security mode", "NAS", "ciphering", "integrity", "NAS-SMC"],
        "text": (
            "Security Mode Command is sent by the AMF to activate NAS ciphering and integrity protection. "
            "The UE responds with Security Mode Complete after activating the selected algorithms. "
            "Failure (Security Mode Reject) is rare and typically indicates algorithm mismatch or "
            "UE security capability negotiation failure. If Security Mode consistently fails, "
            "check AMF NAS security configuration and UE software version compatibility."
        ),
    },
    {
        "spec": "TS 24.501", "section": "6.3.1",
        "topic": "PDU Session Establishment procedure",
        "keywords": ["PDU session", "data session", "SMF", "UPF", "N1", "session establishment"],
        "text": (
            "PDU Session Establishment allows the UE to request a data connectivity path through "
            "the 5G core. The UE sends PDU Session Establishment Request to the AMF, which "
            "forwards it to the SMF via N11. The SMF selects a UPF and responds. "
            "Failure causes include: 5GSM cause #27 (missing or unknown DNN), cause #29 (user authentication failed), "
            "cause #50 (PDU session type IPv4 not allowed). "
            "High failure rates indicate SMF/UPF connectivity issues or DNN misconfiguration."
        ),
    },
    {
        "spec": "TS 24.501", "section": "Table 9.11.3.2.1",
        "topic": "5GMM cause values reference",
        "keywords": ["5GMM cause", "reject cause", "NAS cause", "cause values", "cause codes"],
        "text": (
            "Key 5GMM cause values: "
            "#3=Illegal UE (subscription problem), "
            "#6=Illegal ME (equipment barred), "
            "#7=5GS services not allowed, "
            "#9=UE identity cannot be derived, "
            "#11=PLMN not allowed, "
            "#15=No suitable cells in TAI, "
            "#22=Congestion (AMF overload), "
            "#73=Serving network not authorised, "
            "#76=Temporarily not authorised for this SNPN. "
            "Causes 3-15 are permanent rejections; cause 22 is temporary with T3502 back-off."
        ),
    },

    # ─────────────────────────────────────────────────────────────────
    # NGAP — TS 38.413 (N2 interface)
    # ─────────────────────────────────────────────────────────────────
    {
        "spec": "TS 38.413", "section": "8.4.1",
        "topic": "NGAP InitialContextSetup procedure",
        "keywords": ["InitialContextSetup", "NGAP", "UE context", "N2", "AMF", "initial context"],
        "text": (
            "Initial Context Setup is used by the AMF to establish context for a UE at the gNB, "
            "including security keys, QoS parameters, and optional PDU session resources. "
            "Failure causes include: Radio-resources-not-available (insufficient PRBs/capacity), "
            "Failure-in-the-radio-interface-procedure (RRC setup failure), "
            "Unknown-local-UE-NGAP-ID (context synchronisation loss). "
            "High failure rate on this procedure directly impacts all data sessions for affected UEs."
        ),
    },
    {
        "spec": "TS 38.413", "section": "8.2.1",
        "topic": "NGAP PDU Session Resource Setup procedure",
        "keywords": ["PDU session resource setup", "NGAP", "bearer", "QoS flow", "N2"],
        "text": (
            "PDU Session Resource Setup is triggered by the AMF to establish user-plane resources "
            "at the gNB for a PDU session. The gNB allocates DRBs and GTP tunnels. "
            "Failure causes: Radio-resources-not-available (capacity), "
            "Multiple-PDU-session-ID-instances (duplicate session), "
            "Not-supported-5QI-value (QoS class mismatch between SMF and gNB). "
            "Failures here mean users cannot get data even after successful registration."
        ),
    },
    {
        "spec": "TS 38.413", "section": "8.3.3",
        "topic": "NGAP UE Context Release procedure",
        "keywords": ["UE context release", "NGAP", "release", "detach", "idle"],
        "text": (
            "UE Context Release is initiated by either the AMF or gNB to release resources "
            "for a UE moving to idle state. Release causes: "
            "User-inactivity (normal idle), "
            "Radio-connection-with-UE-lost (RLF), "
            "Handover-cancelled (abnormal HO termination), "
            "NAS-signalling (NAS-driven release). "
            "High counts of Radio-connection-with-UE-lost indicate RLF or coverage issues."
        ),
    },
    {
        "spec": "TS 38.413", "section": "8.4.2",
        "topic": "NGAP Handover preparation procedure",
        "keywords": ["handover", "NGAP", "Xn handover", "NG handover", "mobility"],
        "text": (
            "5G supports Xn-based handover (direct gNB-gNB, faster) and NG-based handover "
            "(via AMF, for inter-AMF mobility). Handover failure causes: "
            "Handover-desirable-for-radio-reasons (A3 measurement triggered), "
            "Time-critical-handover (fast response needed), "
            "Target-not-allowed (target cell barred or capacity), "
            "Unknown-target-ID (incorrect handover target). "
            "High HO failure rate degrades mobility experience and can cause call drops."
        ),
    },
    {
        "spec": "TS 38.413", "section": "9.3.1.2",
        "topic": "NGAP cause IE values",
        "keywords": ["cause", "NGAP cause", "N2 cause", "radio cause", "transport cause", "NAS cause"],
        "text": (
            "NGAP Cause IE groups: "
            "RadioNetwork: radio-connection-with-ue-lost, radio-resources-not-available, "
            "failure-in-the-radio-interface-procedure, procedure-cancelled, "
            "ue-context-release (most common), unknown-local-UE-NGAP-ID. "
            "Transport: transport-resource-unavailable (N2 link issue). "
            "NAS: normal-release, authentication-failure, deregister. "
            "Protocol: transfer-syntax-error, semantic-error (software bug). "
            "Misc: hardware-failure, om-intervention (O&M action), unspecified."
        ),
    },

    # ─────────────────────────────────────────────────────────────────
    # RRC — TS 38.331 (Uu interface)
    # ─────────────────────────────────────────────────────────────────
    {
        "spec": "TS 38.331", "section": "5.3.3",
        "topic": "RRC Setup procedure",
        "keywords": ["RRC setup", "RRC connection", "RRC establishment", "SRB1"],
        "text": (
            "RRC Setup establishes the RRC connection and SRB1 between the UE and the gNB. "
            "The UE sends RRCSetupRequest; the gNB responds with RRCSetup containing SRB configuration. "
            "Rejection causes: RRCSetupReject with waitTime IE indicates congestion/capacity limits. "
            "High RRC Setup Reject Rate indicates: gNB capacity exhaustion (high load), "
            "coverage hole (UE with poor RSRP), or gNB software issue. "
            "RRC Setup is the gateway to all 5G services — failure here blocks everything."
        ),
    },
    {
        "spec": "TS 38.331", "section": "5.3.7",
        "topic": "RRC Reestablishment procedure",
        "keywords": ["RRC reestablishment", "RLF", "radio link failure", "reconnect"],
        "text": (
            "RRC Reestablishment is triggered by the UE after a Radio Link Failure (RLF) "
            "or handover failure, to reconnect without full registration. "
            "The gNB can accept (RRCReestablishment) or reject (RRCReestablishmentReject → go idle). "
            "High reestablishment rates indicate: poor coverage, interference, "
            "aggressive DRX configuration, or incorrect A3 handover offset/TTT causing late HOs. "
            "Each reestablishment causes a service interruption of 50-500ms."
        ),
    },
    {
        "spec": "TS 38.331", "section": "5.3.5",
        "topic": "RRC Reconfiguration procedure",
        "keywords": ["RRC reconfiguration", "DRB", "bearer", "measurement config", "handover execution"],
        "text": (
            "RRC Reconfiguration is the most frequent RRC message — used to add/modify DRBs, "
            "update measurement configuration, and execute handovers. "
            "RRCReconfigurationComplete confirms success. Failure (no response = timeout) indicates "
            "UE processing issue, PDCP failure, or connection loss during configuration. "
            "Reconfiguration failures during handover cause call drops."
        ),
    },
    {
        "spec": "TS 38.331", "section": "5.3.8",
        "topic": "RRC Release procedure",
        "keywords": ["RRC release", "idle", "suspend", "release cause"],
        "text": (
            "RRC Release is sent by the gNB to move the UE to RRC_IDLE or RRC_INACTIVE. "
            "Release causes: other (normal), rrc-suspend (move to INACTIVE for fast resume), "
            "deprioritisation (load management). "
            "Unexpected releases with cause 'radio-link-failure' or 'other' at high rate "
            "indicate coverage problems, scheduler issues, or UE software defects."
        ),
    },
    {
        "spec": "TS 38.331", "section": "6.3.2",
        "topic": "Measurement configuration and A3 event",
        "keywords": ["A3", "measurement", "RSRP", "handover trigger", "TTT", "offset", "A5"],
        "text": (
            "A3 event: serving cell RSRP < neighbour cell RSRP + offset for TTT (time-to-trigger). "
            "When A3 fires, the UE sends MeasurementReport and the gNB initiates handover. "
            "Too large an A3 offset → late handovers → RLF. "
            "Too small an A3 offset → ping-pong handovers → unnecessary HOs. "
            "Too long TTT → late HOs in fast-moving UEs. "
            "A5 event: serving cell below threshold 1 AND target cell above threshold 2 — used for coverage-triggered HOs."  # noqa: E501
        ),
    },

    # ─────────────────────────────────────────────────────────────────
    # F1AP — TS 38.473 (F1 interface)
    # ─────────────────────────────────────────────────────────────────
    {
        "spec": "TS 38.473", "section": "8.4.1",
        "topic": "F1AP UE Context Setup procedure",
        "keywords": ["F1AP", "UE context setup", "F1", "DU", "CU-CP", "SRB", "DRB"],
        "text": (
            "F1AP UE Context Setup is sent by the gNB-CU-CP to the gNB-DU to create a UE context "
            "including SRB and DRB configuration. The DU allocates radio resources and responds. "
            "Failure causes: Procedure-cancelled (resource issue at DU), "
            "Radio-resources-not-available (DU capacity exhausted), "
            "Unknown-GNB-CU-UE-F1AP-ID (context sync loss). "
            "High failure rate indicates DU hardware resource exhaustion or CU-DU interface issues."
        ),
    },
    {
        "spec": "TS 38.473", "section": "8.5.1",
        "topic": "F1AP DL/UL RRC Message Transfer",
        "keywords": ["F1AP", "DL RRC", "UL RRC", "RRC transfer", "F1", "transparent container"],
        "text": (
            "DL RRC Message Transfer carries RRC messages from gNB-CU to gNB-DU for forwarding to UE. "
            "UL RRC Message Transfer carries RRC messages from DU to CU. "
            "These messages carry NAS payloads (Registration, Authentication, PDU Session) as transparent containers. "
            "Failures here indicate F1 interface problems: SCTP link issues, DU overload, or "
            "message encoding errors."
        ),
    },
    {
        "spec": "TS 38.473", "section": "8.2.1",
        "topic": "F1AP F1 Setup procedure",
        "keywords": ["F1 setup", "F1AP setup", "gNB-DU", "gNB-CU", "F1 interface establishment"],
        "text": (
            "F1 Setup is the first procedure on the F1 interface — the gNB-DU registers itself "
            "with the gNB-CU-CP. The DU provides its ID, served cells, and capabilities. "
            "F1 Setup Failure indicates: configuration mismatch, unsupported capabilities, "
            "or duplicate DU ID. If F1 Setup fails, all UEs on that DU lose 5G service."
        ),
    },
    {
        "spec": "TS 38.473", "section": "Table 9.3.1.2-1",
        "topic": "F1AP cause values",
        "keywords": ["F1AP cause", "F1 cause", "procedure cancelled", "F1 radio cause"],
        "text": (
            "F1AP Cause IE values: "
            "RadioNetwork: unknown-GNB-CU-UE-F1AP-ID, unknown-GNB-DU-UE-F1AP-ID, "
            "radio-resources-not-available, procedure-cancelled (most common), "
            "unknown-GNB-DU-ID, action-desirable-for-radio-reasons. "
            "Transport: transport-resource-unavailable (F1 SCTP issue). "
            "Procedure-cancelled at high rate indicates resource exhaustion or "
            "gNB-DU software instability."
        ),
    },

    # ─────────────────────────────────────────────────────────────────
    # E1AP — TS 38.463 (E1 interface)
    # ─────────────────────────────────────────────────────────────────
    {
        "spec": "TS 38.463", "section": "8.3.1",
        "topic": "E1AP Bearer Context Setup procedure",
        "keywords": ["E1AP", "bearer context setup", "CU-UP", "CU-CP", "PDCP", "GTP", "user plane"],
        "text": (
            "Bearer Context Setup is sent by the gNB-CU-CP to the gNB-CU-UP to establish "
            "PDCP and GTP user-plane resources for a UE's PDU session. "
            "The CU-UP responds with Bearer Context Setup Response (success) or Failure. "
            "Failure causes: Procedure-cancelled (CU-UP resource exhaustion), "
            "Unspecified (software error). "
            "High failure rate on this procedure means users cannot get user-plane connectivity "
            "even after successful RRC and NGAP setup."
        ),
    },
    {
        "spec": "TS 38.463", "section": "8.3.2",
        "topic": "E1AP Bearer Context Modification procedure",
        "keywords": ["E1AP", "bearer modification", "CU-UP", "QoS", "PDCP modification"],
        "text": (
            "Bearer Context Modification is used to modify PDCP configuration, add/remove "
            "QoS flows, or update GTP parameters for existing bearer contexts. "
            "Triggered by: QoS remapping, handover, PDU session modification. "
            "Failure here causes QoS degradation for ongoing sessions."
        ),
    },
    {
        "spec": "TS 38.463", "section": "9.3.1",
        "topic": "E1AP cause values",
        "keywords": ["E1AP cause", "bearer context", "E1 cause", "CU-UP cause"],
        "text": (
            "E1AP Cause IE: RadioNetwork: unknown-GNB-CU-CP-UE-E1AP-ID, "
            "unknown-GNB-CU-UP-UE-E1AP-ID, procedure-cancelled, "
            "unspecified (software / implementation error). "
            "Transport: transport-resource-unavailable (E1 SCTP link issue). "
            "Procedure-cancelled at high rate on Bearer Context Setup indicates "
            "gNB-CU-UP memory or GTP tunnel table exhaustion."
        ),
    },

    # ─────────────────────────────────────────────────────────────────
    # XnAP — TS 38.423 (Xn interface)
    # ─────────────────────────────────────────────────────────────────
    {
        "spec": "TS 38.423", "section": "8.2.1",
        "topic": "XnAP Xn Setup procedure",
        "keywords": ["XnAP", "Xn setup", "gNB-gNB", "inter-gNB", "Xn interface establishment"],
        "text": (
            "Xn Setup establishes the Xn interface between two gNBs, enabling Xn-based "
            "handover, dual connectivity, and interference coordination. "
            "Xn Setup Failure: Unspecified, No-radio-resources-available, "
            "unknown-target-ID. If Xn Setup fails, all inter-gNB handovers between these "
            "two gNBs must go through AMF (slower NG-based HO)."
        ),
    },
    {
        "spec": "TS 38.423", "section": "8.3.1",
        "topic": "XnAP Handover Request procedure",
        "keywords": ["XnAP", "Xn handover", "handover request", "MR-DC", "inter-gNB handover"],
        "text": (
            "XnAP Handover Request is sent by the source gNB to the target gNB to request "
            "resources for a UE handover. The target responds with HO Request Acknowledge "
            "(success) or HO Preparation Failure. "
            "Failure causes: Radio-resources-not-available (target capacity), "
            "Target-not-allowed (target cell barred). "
            "Failure means the handover falls back to NG-based (adding ~50ms latency) or fails entirely."
        ),
    },
    {
        "spec": "TS 38.423", "section": "8.6",
        "topic": "XnAP SN Addition — MR-DC (Multi-Radio Dual Connectivity)",
        "keywords": ["MR-DC", "dual connectivity", "secondary node", "SN addition", "NR-DC", "EN-DC"],
        "text": (
            "SN Addition adds a Secondary Node (SN) gNB to provide additional throughput "
            "to a UE via dual connectivity. The Master Node sends SN Addition Request; "
            "the SN responds with SN Addition Request Acknowledge or Reject. "
            "Rejection causes: Radio-resources-not-available (SN capacity), "
            "Not-supported-5QI (QoS class not supported at SN). "
            "High SN rejection rate limits peak throughput gains from MR-DC."
        ),
    },

    # ─────────────────────────────────────────────────────────────────
    # KPI — Radio Quality
    # ─────────────────────────────────────────────────────────────────
    {
        "spec": "3GPP TR 36.902 / 38.913",
        "section": "KPI: CQI",
        "topic": "CQI — Channel Quality Indicator interpretation",
        "keywords": ["CQI", "channel quality", "MCS", "modulation", "radio quality", "throughput"],
        "text": (
            "CQI (Channel Quality Indicator) is reported by the UE on the PUCCH/PUSCH. "
            "Range 0-15: 0=out of range, 1-6=QPSK (poor), 7-9=16QAM (moderate), 10-15=64/256QAM (good). "
            "CQI < 5 (critical) means the UE can only use QPSK with low code rate — throughput < 1 Mbps. "
            "Causes of low CQI: poor coverage, high interference, UE at cell edge, "
            "antenna tilt/azimuth misconfiguration, external interference. "
            "Action: check antenna parameters, ICIC configuration, inter-cell interference coordination."
        ),
    },
    {
        "spec": "3GPP TS 38.331 / TR 38.913",
        "section": "KPI: SINR",
        "topic": "SINR — Signal to Interference and Noise Ratio",
        "keywords": ["SINR", "signal quality", "interference", "noise", "IOT", "UL interference"],
        "text": (
            "SINR measures the quality of the received signal relative to interference and noise. "
            "DL SINR: reported by UE, correlated with CQI. "
            "UL SINR: measured by gNB. "
            "SINR < 0 dB (critical): UE cannot receive reliable data — significant interference or coverage failure. "
            "Common causes: Pilot pollution (too many cells covering same area), "
            "Uplink Interference over Thermal (IOT) from external sources, "
            "incorrect power control parameters."
        ),
    },
    {
        "spec": "3GPP TS 38.913",
        "section": "KPI: PRB Utilization",
        "topic": "PRB Utilization — capacity and congestion",
        "keywords": ["PRB", "utilization", "congestion", "capacity", "scheduler", "DL PRB", "UL PRB"],
        "text": (
            "PRB (Physical Resource Block) Utilization measures how much of the radio bandwidth is used. "
            "Warning threshold: 80%. Critical: 90%. "
            "PRB > 90% means the cell is congested — new users are queued or rejected. "
            "Causes: too many users, high-throughput services (video), small cell coverage area. "
            "Actions: add carriers (CA), add new cells, activate load-balancing features, "
            "check scheduler configuration for fairness. "
            "PRB burst (short spike > 90%) vs sustained congestion require different responses."
        ),
    },
    {
        "spec": "3GPP TS 38.913",
        "section": "KPI: BLER",
        "topic": "BLER — Block Error Rate",
        "keywords": ["BLER", "block error", "retransmission", "HARQ", "reliability"],
        "text": (
            "BLER (Block Error Rate) measures the fraction of transport blocks that are received "
            "in error before HARQ retransmission. Target BLER = 10% (OLLA adaptive outer loop). "
            "BLER > 30% (warning) means excessive retransmissions — throughput drops significantly. "
            "Causes: poor SINR, link adaptation failure, incorrect MCS selection, "
            "scheduler bug. High BLER with good CQI indicates link adaptation algorithm issue."
        ),
    },
    {
        "spec": "3GPP TS 38.913",
        "section": "KPI: Throughput",
        "topic": "DL/UL Throughput — user experience metric",
        "keywords": ["throughput", "Mbps", "data rate", "DL throughput", "UL throughput", "speed"],
        "text": (
            "Throughput KPIs measure the average data rate delivered to users. "
            "DL throughput depends on: PRB utilization, CQI/MCS, MIMO layers, number of users. "
            "Low throughput despite low PRB utilization indicates: poor CQI (signal quality issue), "
            "scheduler fairness problem, or misconfigured TDD slot ratio. "
            "Low throughput with high PRB utilization indicates: capacity congestion. "
            "Check: CQI distribution, MCS distribution, active user count, MIMO rank."
        ),
    },
    {
        "spec": "3GPP TS 38.913",
        "section": "KPI: Handover Success Rate",
        "topic": "Handover Success Rate — mobility performance",
        "keywords": ["handover", "HO success rate", "mobility", "HO failure", "ping-pong"],
        "text": (
            "Handover Success Rate measures the fraction of handover attempts that complete "
            "successfully. Target > 98%. "
            "Below 95% (critical) means frequent handover failures causing call drops. "
            "Causes of HO failure: radio link failure during preparation, target cell full, "
            "incorrect A3 measurement threshold (offset too large = late HO), "
            "TTT too long for fast-moving UEs, X2/Xn interface issues. "
            "Ping-pong HO (SR OK but high HO count): A3 offset too small."
        ),
    },
    {
        "spec": "3GPP TS 38.913",
        "section": "KPI: Cell Availability",
        "topic": "Cell Availability — site reliability",
        "keywords": ["cell availability", "site availability", "outage", "hardware fault", "software reset"],
        "text": (
            "Cell Availability measures the percentage of time a cell is available for service. "
            "Target > 99.5%. Below 95% (critical) means the cell is down for > 1.2 hours per day. "
            "Causes: hardware failures (radio unit fault, BBU issue, power), "
            "software crashes requiring cell reset, transport failures (fronthaul/midhaul). "
            "Check: gNB hardware alarms, O&M fault management, power supply status, "
            "fronthaul/midhaul link quality. Cell unavailability = all users on that cell lose service."
        ),
    },
    {
        "spec": "3GPP TS 38.913",
        "section": "KPI: RRC Success Rate",
        "topic": "RRC Connection Setup Success Rate",
        "keywords": ["RRC SR", "RRC success", "accessibility", "connection failure", "RACH"],
        "text": (
            "RRC Setup Success Rate = RRC connections completed / RRC connections attempted. "
            "Target > 99%. Below 95% (critical) is a major accessibility issue. "
            "Low RRC SR causes: cell capacity reached (gNB rejects with waitTime), "
            "coverage hole (UE cannot decode RRCSetup), RACH congestion, "
            "gNB software bug. "
            "RRC SR is the first KPI to check when users report 'cannot connect to 5G'."
        ),
    },
    {
        "spec": "3GPP TS 38.913",
        "section": "KPI: Registration Success Rate",
        "topic": "NAS Registration Success Rate",
        "keywords": ["registration SR", "registration success", "AMF", "NAS", "registration failure"],
        "text": (
            "Registration Success Rate = successful registrations / registration attempts. "
            "Target > 99%. Below 95% means the core network is rejecting connections. "
            "Causes: AMF congestion (cause #22), AUSF/UDM unavailability (auth failures), "
            "SUPI/subscription errors, AMF capacity limits. "
            "Check: AMF CPU/memory, AUSF/UDM health, NAS reject cause distribution."
        ),
    },
    {
        "spec": "3GPP TS 38.913",
        "section": "KPI: RACH",
        "topic": "RACH — Random Access Channel performance",
        "keywords": ["RACH", "random access", "RA preamble", "contention", "PRACH", "TA"],
        "text": (
            "RACH procedure: UE sends preamble → gNB sends RAR → UE sends MSG3 → gNB sends MSG4. "
            "RACH success rate < 98% indicates: PRACH configuration issue (too few preambles), "
            "coverage problem (UE cannot receive RAR), high preamble collision rate (many simultaneous UEs). "
            "Check: PRACH configuration (numRA-Slots, numRA-PreambleSlots), cell load, "
            "target RACH success rate, and contention-free RACH for handover."
        ),
    },

    # ─────────────────────────────────────────────────────────────────
    # General troubleshooting
    # ─────────────────────────────────────────────────────────────────
    {
        "spec": "General / 3GPP TS 28.552",
        "section": "Troubleshooting",
        "topic": "Cascading failure pattern — upstream failure propagation",
        "keywords": ["cascade", "cascading failure", "upstream", "downstream", "root cause", "chain"],
        "text": (
            "In 5G, procedures follow a strict sequence: RRC Setup → NGAP InitialContextSetup → "
            "NAS Authentication → Security Mode → PDU Session → F1AP UEContextSetup → E1AP BearerContextSetup. "
            "A failure in an upstream procedure causes all downstream procedures to also fail. "
            "Root cause analysis must start from the FIRST failing procedure in the chain. "
            "If NGAP InitialContextSetup fails at 30% but NAS Authentication still shows high attempt "
            "count, the root cause is at the NGAP level — NAS failures are symptoms, not causes."
        ),
    },
    {
        "spec": "General",
        "section": "Troubleshooting",
        "topic": "Timeout pattern — connectivity and timer issues",
        "keywords": ["timeout", "T3x timer", "N2 timeout", "no response", "connectivity"],
        "text": (
            "Timeouts in 5G signalling indicate that a response was not received within the configured timer. "
            "NAS timeouts (T3510, T3521, T3522): UE did not receive response from AMF — check N2 interface, "
            "AMF responsiveness, SCTP association. "
            "NGAP timeouts: gNB did not receive NGAP response — check AMF load and N2 link. "
            "F1AP timeouts: CU did not receive DU response — check F1 SCTP link, DU load. "
            "Multiple timeout causes across procedures indicate a transport-level problem (SCTP/IP)."
        ),
    },
    {
        "spec": "General",
        "section": "Troubleshooting",
        "topic": "Congestion pattern — AMF/SMF/UPF overload",
        "keywords": ["congestion", "overload", "capacity", "T3502", "back-off", "AMF load"],
        "text": (
            "Network congestion manifests as: high concentration of cause #22 (Congestion) in NAS rejections, "
            "radio-resources-not-available in NGAP failures, procedure-cancelled in F1AP/E1AP. "
            "Short-term congestion: back-off timer T3502 (12 min) protects AMF from storm. "
            "Sustained congestion: check AMF instance CPU/memory, scale out AMF, "
            "review TAC configuration to balance load across AMF instances. "
            "PRB congestion: check scheduler, activate traffic steering, add carriers."
        ),
    },
    {
        "spec": "General",
        "section": "Troubleshooting",
        "topic": "Radio Link Failure (RLF) troubleshooting",
        "keywords": ["RLF", "radio link failure", "T310", "N310", "coverage", "reestablishment"],
        "text": (
            "RLF is declared when the UE detects N310 consecutive out-of-sync indications without "
            "receiving N311 in-sync indications within T310. After RLF, UE attempts reestablishment. "
            "High RLF rate causes: poor coverage (check RSRP/RSRQ maps), interference, "
            "DRX configuration too aggressive (long sleep cycles miss beacons), "
            "incorrect N310/N311/T310 timer values, handover configured too late. "
            "Each RLF = service interruption of 100ms-2s."
        ),
    },
]
