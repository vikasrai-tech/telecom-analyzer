"""
Protocol Definitions — Complete 3GPP IE schemas
================================================
Covers all six protocol layers:
  TS 24.501  — NAS  (5GMM + 5GSM)
  TS 38.413  — NGAP (N2: gNB-CU ↔ AMF)
  TS 38.331  — RRC  (Uu: UE ↔ gNB)
  TS 38.473  — F1AP (F1: gNB-DU ↔ gNB-CU)
  TS 38.463  — E1AP (E1: gNB-CU-CP ↔ gNB-CU-UP)
  TS 38.423  — XnAP (Xn: gNB ↔ gNB)

Each message definition lists:
  - IEs (mandatory M / optional O / conditional C)
  - 3GPP spec + section reference
  - pyshark tshark field name hint (for real captures)
"""

from typing import Dict, List, Any

# ─────────────────────────────────────────────────────────────────────
# Common type aliases
# ─────────────────────────────────────────────────────────────────────
IE = Dict[str, Any]     # {name, presence, type, spec, tshark_field}

def ie(name, presence, ie_type, spec, tshark_field=""):
    return {"name": name, "presence": presence, "type": ie_type,
            "spec": spec, "tshark_field": tshark_field}

M, O, C = "Mandatory", "Optional", "Conditional"

# ═════════════════════════════════════════════════════════════════════
# NAS — TS 24.501
# ═════════════════════════════════════════════════════════════════════

# ── 5GMM Message IEs ─────────────────────────────────────────────────

NAS_REGISTRATION_REQUEST_IES: List[IE] = [
    ie("5GS Registration Type",           M, "V",   "TS 24.501 §9.11.3.7",  "nas_5gs.mm.5gs_reg_type"),
    ie("ngKSI",                           M, "V",   "TS 24.501 §9.11.3.32", "nas_5gs.mm.nas_key_set_id"),
    ie("Mobile Identity (SUCI/5G-GUTI/IMEI/5G-S-TMSI)", M, "LV-E", "TS 24.501 §9.11.3.4",  "nas_5gs.mm.5g_tmsi"),
    ie("Non-current ngKSI",               O, "TV",  "TS 24.501 §9.11.3.32", "nas_5gs.mm.ncc"),
    ie("5GMM Capability",                 O, "TLV", "TS 24.501 §9.11.3.1",  "nas_5gs.mm.5gmm_cap"),
    ie("UE Security Capability",          O, "TLV", "TS 24.501 §9.11.3.54", "nas_5gs.mm.ue_security_cap"),
    ie("Requested NSSAI",                 O, "TLV", "TS 24.501 §9.11.3.37", "nas_5gs.mm.req_nssai"),
    ie("Last Visited Registered TAI",     O, "TLV", "TS 24.501 §9.11.3.8",  "nas_5gs.mm.tai"),
    ie("S1 UE Network Capability",        O, "TLV", "TS 24.501 §9.11.3.48", "nas_5gs.mm.s1_ue_network_cap"),
    ie("Uplink Data Status",              O, "TLV", "TS 24.501 §9.11.3.57", "nas_5gs.mm.ul_data_status"),
    ie("PDU Session Status",              O, "TLV", "TS 24.501 §9.11.3.44", "nas_5gs.mm.pdu_ses_status"),
    ie("MICO Indication",                 O, "TV",  "TS 24.501 §9.11.3.31", "nas_5gs.mm.mico_ind"),
    ie("UE Status",                       O, "TLV", "TS 24.501 §9.11.3.56", "nas_5gs.mm.ue_status"),
    ie("Additional GUTI",                 O, "TLV", "TS 24.501 §9.11.3.4",  "nas_5gs.mm.5g_guti"),
    ie("Allowed PDU Session Status",      O, "TLV", "TS 24.501 §9.11.3.13", "nas_5gs.mm.allow_pdu_ses_sts"),
    ie("UE Usage Setting",                O, "TLV", "TS 24.501 §9.11.3.55", "nas_5gs.mm.ue_usage_setting"),
    ie("Requested DRX Parameters",        O, "TLV", "TS 24.501 §9.11.3.2a", "nas_5gs.mm.drx_param"),
    ie("EPS NAS Message Container",       O, "TLV-E","TS 24.501 §9.11.3.21","nas_5gs.mm.eps_nas_msg_cont"),
    ie("LADN Indication",                 O, "TLV-E","TS 24.501 §9.11.3.29","nas_5gs.mm.ladn_ind"),
    ie("Payload Container Type",          O, "TV",  "TS 24.501 §9.11.3.40", "nas_5gs.mm.payload_cont_type"),
    ie("Payload Container",               O, "TLV-E","TS 24.501 §9.11.3.39","nas_5gs.mm.payload_cont"),
    ie("Network Slicing Indication",      O, "TV",  "TS 24.501 §9.11.3.36", "nas_5gs.mm.nw_slicing_ind"),
    ie("5GS Update Type",                 O, "TLV", "TS 24.501 §9.11.3.9a", "nas_5gs.mm.5gs_update_type"),
    ie("NAS Message Container",           O, "TLV-E","TS 24.501 §9.11.3.33","nas_5gs.mm.nas_msg_cont"),
    ie("EPS Bearer Context Status",       O, "TLV", "TS 24.501 §9.11.3.23", "nas_5gs.mm.eps_bearer_ctx_status"),
]

NAS_REGISTRATION_ACCEPT_IES: List[IE] = [
    ie("5GS Registration Result",         M, "LV",  "TS 24.501 §9.11.3.6",  "nas_5gs.mm.5gs_reg_res"),
    ie("5G-GUTI",                         O, "TLV", "TS 24.501 §9.11.3.4",  "nas_5gs.mm.5g_guti"),
    ie("Equivalent PLMNs",                O, "TLV", "TS 24.501 §9.11.3.45", "nas_5gs.mm.eq_plmns"),
    ie("TAI List",                        O, "TLV", "TS 24.501 §9.11.3.9",  "nas_5gs.mm.tai_list"),
    ie("Allowed NSSAI",                   O, "TLV", "TS 24.501 §9.11.3.37", "nas_5gs.mm.allowed_nssai"),
    ie("Rejected NSSAI",                  O, "TLV", "TS 24.501 §9.11.3.46", "nas_5gs.mm.rejected_nssai"),
    ie("Configured NSSAI",                O, "TLV", "TS 24.501 §9.11.3.37", "nas_5gs.mm.conf_nssai"),
    ie("5GS Network Feature Support",     O, "TLV", "TS 24.501 §9.11.3.5",  "nas_5gs.mm.5gs_nw_feat_sup"),
    ie("PDU Session Status",              O, "TLV", "TS 24.501 §9.11.3.44", "nas_5gs.mm.pdu_ses_status"),
    ie("PDU Session Reactivation Result", O, "TLV", "TS 24.501 §9.11.3.42", "nas_5gs.mm.pdu_ses_react_res"),
    ie("LADN Information",                O, "TLV-E","TS 24.501 §9.11.3.30","nas_5gs.mm.ladn_inf"),
    ie("MICO Indication",                 O, "TV",  "TS 24.501 §9.11.3.31", "nas_5gs.mm.mico_ind"),
    ie("Network Slicing Indication",      O, "TV",  "TS 24.501 §9.11.3.36", "nas_5gs.mm.nw_slicing_ind"),
    ie("Service Area List",               O, "TLV", "TS 24.501 §9.11.3.49", "nas_5gs.mm.sal"),
    ie("T3512 Value",                     O, "TLV", "TS 24.501 §9.11.3.18", "nas_5gs.mm.t3512"),
    ie("Non-3GPP De-registration Timer",  O, "TLV", "TS 24.501 §9.11.3.18", "nas_5gs.mm.non3gpp_dereg_timer"),
    ie("T3502 Value",                     O, "TLV", "TS 24.501 §9.11.3.18", "nas_5gs.mm.t3502"),
    ie("Emergency Number List",           O, "TLV", "TS 24.501 §9.11.3.23a","nas_5gs.mm.emerg_num_list"),
    ie("Extended Emergency Number List",  O, "TLV-E","TS 24.501 §9.11.3.26","nas_5gs.mm.ext_emerg_num_list"),
    ie("SOR Transparent Container",       O, "TLV-E","TS 24.501 §9.11.3.51","nas_5gs.mm.sor_trasp_cont"),
    ie("EAP Message",                     O, "TLV-E","TS 24.501 §9.11.3.20","nas_5gs.mm.eap_msg"),
    ie("NSSAI Inclusion Mode",            O, "TV",  "TS 24.501 §9.11.3.37a","nas_5gs.mm.nssai_inc_mode"),
    ie("Operator-defined Access Cat Defs",O, "TLV-E","TS 24.501 §9.11.3.38","nas_5gs.mm.op_def_acc_cat_def"),
    ie("5GS DRX Parameters",             O, "TLV", "TS 24.501 §9.11.3.2a", "nas_5gs.mm.drx_param"),
]

NAS_REGISTRATION_REJECT_IES: List[IE] = [
    ie("5GMM Cause",                      M, "V",   "TS 24.501 §9.11.3.2",  "nas_5gs.mm.5gmm_cause"),
    ie("T3346 Value",                     O, "TLV", "TS 24.501 §9.11.3.18", "nas_5gs.mm.t3346"),
    ie("T3502 Value",                     O, "TLV", "TS 24.501 §9.11.3.18", "nas_5gs.mm.t3502"),
    ie("EAP Message",                     O, "TLV-E","TS 24.501 §9.11.3.20","nas_5gs.mm.eap_msg"),
    ie("Rejected NSSAI",                  O, "TLV", "TS 24.501 §9.11.3.46", "nas_5gs.mm.rejected_nssai"),
]

NAS_AUTHENTICATION_REQUEST_IES: List[IE] = [
    ie("ngKSI",                           M, "V",   "TS 24.501 §9.11.3.32", "nas_5gs.mm.nas_key_set_id"),
    ie("ABBA",                            M, "LV",  "TS 24.501 §9.11.3.10", "nas_5gs.mm.abba"),
    ie("Authentication Parameter RAND",   O, "TLV", "TS 24.501 §9.11.3.16", "nas_5gs.mm.rand"),
    ie("Authentication Parameter AUTN",   O, "TLV", "TS 24.501 §9.11.3.15", "nas_5gs.mm.autn"),
    ie("EAP Message",                     O, "TLV-E","TS 24.501 §9.11.3.20","nas_5gs.mm.eap_msg"),
]

NAS_AUTHENTICATION_RESPONSE_IES: List[IE] = [
    ie("Authentication Response Parameter (RES*)", O, "TLV", "TS 24.501 §9.11.3.17", "nas_5gs.mm.res_star"),
    ie("EAP Message",                     O, "TLV-E","TS 24.501 §9.11.3.20","nas_5gs.mm.eap_msg"),
]

NAS_AUTHENTICATION_REJECT_IES: List[IE] = [
    ie("EAP Message",                     O, "TLV-E","TS 24.501 §9.11.3.20","nas_5gs.mm.eap_msg"),
]

NAS_AUTHENTICATION_FAILURE_IES: List[IE] = [
    ie("5GMM Cause",                      M, "V",   "TS 24.501 §9.11.3.2",  "nas_5gs.mm.5gmm_cause"),
    ie("Authentication Failure Parameter (AUTS)", O, "TLV", "TS 24.501 §9.11.3.14", "nas_5gs.mm.auts"),
]

NAS_SECURITY_MODE_COMMAND_IES: List[IE] = [
    ie("Selected NAS Security Algorithms",M, "V",   "TS 24.501 §9.11.3.50", "nas_5gs.mm.nas_int_alg"),
    ie("ngKSI",                           M, "V",   "TS 24.501 §9.11.3.32", "nas_5gs.mm.nas_key_set_id"),
    ie("Replayed UE Security Capabilities",M,"LV",  "TS 24.501 §9.11.3.54", "nas_5gs.mm.ue_security_cap"),
    ie("IMEISV Request",                  O, "TV",  "TS 24.501 §9.11.3.28", "nas_5gs.mm.imeisv_req"),
    ie("Additional 5G Security Information",O,"TLV","TS 24.501 §9.11.3.12","nas_5gs.mm.add_5g_sec_inf"),
    ie("EAP Message",                     O, "TLV-E","TS 24.501 §9.11.3.20","nas_5gs.mm.eap_msg"),
    ie("ABBA",                            O, "TLV", "TS 24.501 §9.11.3.10", "nas_5gs.mm.abba"),
    ie("Replayed S1 UE Security Capabilities",O,"TLV","TS 24.501 §9.11.3.48","nas_5gs.mm.s1_ue_security_cap"),
]

NAS_SECURITY_MODE_COMPLETE_IES: List[IE] = [
    ie("IMEISV",                          O, "TLV", "TS 24.501 §9.11.3.28", "nas_5gs.mm.imeisv"),
    ie("NAS Message Container",           O, "TLV-E","TS 24.501 §9.11.3.33","nas_5gs.mm.nas_msg_cont"),
    ie("Non-IMEISV PEI",                  O, "TLV", "TS 24.501 §9.11.3.4",  "nas_5gs.mm.pei"),
]

NAS_SECURITY_MODE_REJECT_IES: List[IE] = [
    ie("5GMM Cause",                      M, "V",   "TS 24.501 §9.11.3.2",  "nas_5gs.mm.5gmm_cause"),
]

NAS_PDU_SESSION_EST_REQUEST_IES: List[IE] = [
    ie("Integrity Protection Maximum Data Rate", M, "V", "TS 24.501 §9.11.4.7",  "nas_5gs.sm.integ_prot_max_data_rate"),
    ie("PDU Session Type",                O, "TV",  "TS 24.501 §9.11.4.11", "nas_5gs.sm.pdu_ses_type"),
    ie("SSC Mode",                        O, "TV",  "TS 24.501 §9.11.4.16", "nas_5gs.sm.ssc_mode"),
    ie("5GSM Capability",                 O, "TLV", "TS 24.501 §9.11.4.1",  "nas_5gs.sm.5gsm_cap"),
    ie("Maximum Number of Supported Packet Filters", O, "TV", "TS 24.501 §9.11.4.9", "nas_5gs.sm.max_pkt_flt"),
    ie("Always-on PDU Session Requested", O, "TV",  "TS 24.501 §9.11.4.3",  "nas_5gs.sm.always_on_pdu_ses_req"),
    ie("SM PDU DN Request Container",     O, "TLV", "TS 24.501 §9.11.4.15", "nas_5gs.sm.sm_pdu_dn_req_cont"),
    ie("Extended Protocol Configuration Options", O, "TLV-E", "TS 24.501 §9.11.4.6", "nas_5gs.sm.ext_prot_conf_opt"),
    ie("IP Header Compression Configuration", O, "TLV", "TS 24.501 §9.11.4.6a", "nas_5gs.sm.ip_hdr_comp_conf"),
    ie("DS-TT Ethernet Port MAC Address", O, "TLV", "TS 24.501 §9.11.4.2a", "nas_5gs.sm.ds_tt_eth_port_mac_addr"),
    ie("UE-DS-TT Residence Time",         O, "TLV", "TS 24.501 §9.11.4.2b", "nas_5gs.sm.ue_ds_tt_res_time"),
    ie("Port Management Information Container", O, "TLV-E", "TS 24.501 §9.11.4.27", "nas_5gs.sm.port_mgmt_inf_cont"),
    ie("Ethernet Header Compression Configuration", O, "TLV", "TS 24.501 §9.11.4.6b", "nas_5gs.sm.eth_hdr_comp_conf"),
]

NAS_PDU_SESSION_EST_ACCEPT_IES: List[IE] = [
    ie("PDU Session Type",                M, "V",   "TS 24.501 §9.11.4.11", "nas_5gs.sm.pdu_ses_type"),
    ie("SSC Mode",                        M, "V",   "TS 24.501 §9.11.4.16", "nas_5gs.sm.ssc_mode"),
    ie("QoS Rules",                       M, "LV-E","TS 24.501 §9.11.4.13", "nas_5gs.sm.qos_rules"),
    ie("Session AMBR",                    M, "LV",  "TS 24.501 §9.11.4.14", "nas_5gs.sm.ses_ambr"),
    ie("5GSM Cause",                      O, "TV",  "TS 24.501 §9.11.4.2",  "nas_5gs.sm.5gsm_cause"),
    ie("PDU Address",                     O, "TLV", "TS 24.501 §9.11.4.10", "nas_5gs.sm.pdu_addr"),
    ie("RQ Timer Value",                  O, "TV",  "TS 24.501 §9.11.4.18", "nas_5gs.sm.rq_timer_val"),
    ie("Always-on PDU Session Indication",O, "TV",  "TS 24.501 §9.11.4.3",  "nas_5gs.sm.always_on_pdu_ses_ind"),
    ie("Mapped EPS Bearer Contexts",      O, "TLV-E","TS 24.501 §9.11.4.8", "nas_5gs.sm.mapped_eps_b_cont"),
    ie("EAP Message",                     O, "TLV-E","TS 24.501 §9.11.3.20","nas_5gs.sm.eap_msg"),
    ie("QoS Flow Descriptions",           O, "TLV-E","TS 24.501 §9.11.4.12","nas_5gs.sm.qos_fd"),
    ie("Extended Protocol Configuration Options", O, "TLV-E","TS 24.501 §9.11.4.6","nas_5gs.sm.ext_prot_conf_opt"),
    ie("DNN",                             O, "TLV", "TS 24.501 §9.11.2.1b", "nas_5gs.sm.dnn"),
    ie("S-NSSAI",                         O, "TLV", "TS 24.501 §9.11.2.8",  "nas_5gs.sm.snssai"),
]

NAS_PDU_SESSION_EST_REJECT_IES: List[IE] = [
    ie("5GSM Cause",                      M, "V",   "TS 24.501 §9.11.4.2",  "nas_5gs.sm.5gsm_cause"),
    ie("Back-off Timer Value",            O, "TLV", "TS 24.501 §9.11.4.18", "nas_5gs.sm.backoff_timer"),
    ie("Allowed SSC Mode",                O, "TV",  "TS 24.501 §9.11.4.5",  "nas_5gs.sm.allow_ssc_mode"),
    ie("EAP Message",                     O, "TLV-E","TS 24.501 §9.11.3.20","nas_5gs.sm.eap_msg"),
    ie("Extended Protocol Configuration Options", O, "TLV-E","TS 24.501 §9.11.4.6","nas_5gs.sm.ext_prot_conf_opt"),
    ie("Re-attempt Indicator",            O, "TLV", "TS 24.501 §9.11.4.17", "nas_5gs.sm.reattempt_ind"),
    ie("5GSM Congestion Re-attempt Indicator", O, "TLV", "TS 24.501 §9.11.4.21", "nas_5gs.sm.5gsm_cong_reattempt_ind"),
]

NAS_DEREGISTRATION_REQUEST_IES: List[IE] = [
    ie("De-registration Type",            M, "V",   "TS 24.501 §9.11.3.20", "nas_5gs.mm.de_reg_type"),
    ie("ngKSI",                           M, "V",   "TS 24.501 §9.11.3.32", "nas_5gs.mm.nas_key_set_id"),
    ie("5GS Mobile Identity",             M, "LV-E","TS 24.501 §9.11.3.4",  "nas_5gs.mm.5g_tmsi"),
    ie("5GMM Cause",                      O, "TV",  "TS 24.501 §9.11.3.2",  "nas_5gs.mm.5gmm_cause"),
    ie("T3346 Value",                     O, "TLV", "TS 24.501 §9.11.3.18", "nas_5gs.mm.t3346"),
    ie("ReAttempt Indicator",             O, "TLV", "TS 24.501 §9.11.3.47", "nas_5gs.mm.reattempt_ind"),
]

NAS_SERVICE_REQUEST_IES: List[IE] = [
    ie("ngKSI",                           M, "V",   "TS 24.501 §9.11.3.32", "nas_5gs.mm.nas_key_set_id"),
    ie("5G-S-TMSI",                       M, "LV",  "TS 24.501 §9.11.3.4",  "nas_5gs.mm.5g_tmsi"),
    ie("Uplink Data Status",              O, "TLV", "TS 24.501 §9.11.3.57", "nas_5gs.mm.ul_data_status"),
    ie("PDU Session Status",              O, "TLV", "TS 24.501 §9.11.3.44", "nas_5gs.mm.pdu_ses_status"),
    ie("Allowed PDU Session Status",      O, "TLV", "TS 24.501 §9.11.3.13", "nas_5gs.mm.allow_pdu_ses_sts"),
    ie("NAS Message Container",           O, "TLV-E","TS 24.501 §9.11.3.33","nas_5gs.mm.nas_msg_cont"),
]

# Complete NAS message → IE list mapping
NAS_MESSAGE_IE_SCHEMAS: Dict[str, List[IE]] = {
    "NAS_Registration_request":              NAS_REGISTRATION_REQUEST_IES,
    "NAS_Registration_accept":               NAS_REGISTRATION_ACCEPT_IES,
    "NAS_Registration_reject":               NAS_REGISTRATION_REJECT_IES,
    "NAS_Authentication_request":            NAS_AUTHENTICATION_REQUEST_IES,
    "NAS_Authentication_response":           NAS_AUTHENTICATION_RESPONSE_IES,
    "NAS_Authentication_reject":             NAS_AUTHENTICATION_REJECT_IES,
    "NAS_Authentication_failure":            NAS_AUTHENTICATION_FAILURE_IES,
    "NAS_SecurityMode_command":              NAS_SECURITY_MODE_COMMAND_IES,
    "NAS_SecurityMode_complete":             NAS_SECURITY_MODE_COMPLETE_IES,
    "NAS_SecurityMode_reject":               NAS_SECURITY_MODE_REJECT_IES,
    "NAS_PDUSession_Establishment_request":  NAS_PDU_SESSION_EST_REQUEST_IES,
    "NAS_PDUSession_Establishment_accept":   NAS_PDU_SESSION_EST_ACCEPT_IES,
    "NAS_PDUSession_Establishment_reject":   NAS_PDU_SESSION_EST_REJECT_IES,
    "NAS_Deregistration_request":            NAS_DEREGISTRATION_REQUEST_IES,
    "NAS_ServiceRequest_request":            NAS_SERVICE_REQUEST_IES,
}

# ── pyshark tshark field → human-readable name for NAS ───────────────
NAS_TSHARK_FIELD_MAP: Dict[str, str] = {
    "nas_5gs.mm.5gs_reg_type":        "5GS Registration Type",
    "nas_5gs.mm.nas_key_set_id":      "ngKSI",
    "nas_5gs.mm.5g_tmsi":             "5G-TMSI",
    "nas_5gs.mm.5g_guti":             "5G-GUTI",
    "nas_5gs.mm.mcc":                 "MCC",
    "nas_5gs.mm.mnc":                 "MNC",
    "nas_5gs.mm.amf_region_id":       "AMF Region ID",
    "nas_5gs.mm.amf_set_id":          "AMF Set ID",
    "nas_5gs.mm.amf_pointer":         "AMF Pointer",
    "nas_5gs.mm.5gs_reg_res":         "Registration Result",
    "nas_5gs.mm.tai_list":            "TAI List",
    "nas_5gs.mm.allowed_nssai":       "Allowed NSSAI",
    "nas_5gs.mm.req_nssai":           "Requested NSSAI",
    "nas_5gs.mm.rejected_nssai":      "Rejected NSSAI",
    "nas_5gs.mm.5gmm_cause":          "5GMM Cause",
    "nas_5gs.mm.t3512":               "T3512 Timer",
    "nas_5gs.mm.t3502":               "T3502 Timer",
    "nas_5gs.mm.t3346":               "T3346 Timer",
    "nas_5gs.mm.ue_security_cap":     "UE Security Capability",
    "nas_5gs.mm.nas_int_alg":         "NAS Integrity Algorithm",
    "nas_5gs.mm.nas_enc_alg":         "NAS Ciphering Algorithm",
    "nas_5gs.mm.rand":                "RAND",
    "nas_5gs.mm.autn":                "AUTN",
    "nas_5gs.mm.res_star":            "RES*",
    "nas_5gs.mm.auts":                "AUTS",
    "nas_5gs.mm.abba":                "ABBA",
    "nas_5gs.mm.imeisv":              "IMEISV",
    "nas_5gs.mm.pei":                 "PEI",
    "nas_5gs.mm.de_reg_type":         "De-registration Type",
    "nas_5gs.mm.5gmm_cap":            "5GMM Capability",
    "nas_5gs.mm.5gs_update_type":     "5GS Update Type",
    "nas_5gs.mm.mico_ind":            "MICO Indication",
    "nas_5gs.mm.nw_slicing_ind":      "Network Slicing Indication",
    "nas_5gs.mm.nssai_inc_mode":      "NSSAI Inclusion Mode",
    "nas_5gs.mm.drx_param":           "DRX Parameters",
    "nas_5gs.mm.ul_data_status":      "Uplink Data Status",
    "nas_5gs.mm.pdu_ses_status":      "PDU Session Status",
    "nas_5gs.mm.sal":                 "Service Area List",
    "nas_5gs.sm.5gsm_cause":          "5GSM Cause",
    "nas_5gs.sm.pdu_ses_type":        "PDU Session Type",
    "nas_5gs.sm.ssc_mode":            "SSC Mode",
    "nas_5gs.sm.snssai":              "S-NSSAI",
    "nas_5gs.sm.dnn":                 "DNN",
    "nas_5gs.sm.pdu_addr":            "PDU Address (IP)",
    "nas_5gs.sm.ses_ambr":            "Session AMBR",
    "nas_5gs.sm.qos_rules":           "QoS Rules",
    "nas_5gs.sm.qos_fd":              "QoS Flow Descriptions",
    "nas_5gs.sm.5gsm_cap":            "5GSM Capability",
    "nas_5gs.sm.integ_prot_max_data_rate": "Integrity Protection Max Data Rate",
    "nas_5gs.sm.always_on_pdu_ses_req": "Always-on PDU Session Requested",
    "nas_5gs.sm.always_on_pdu_ses_ind": "Always-on PDU Session Indication",
    "nas_5gs.sm.backoff_timer":       "Back-off Timer Value",
    "nas_5gs.sm.max_pkt_flt":         "Max Packet Filters",
    "nas_5gs.sm.eap_msg":             "EAP Message",
}

# ═════════════════════════════════════════════════════════════════════
# NGAP — TS 38.413
# ═════════════════════════════════════════════════════════════════════

NGAP_INITIAL_CONTEXT_SETUP_REQUEST_IES: List[IE] = [
    ie("AMF-UE-NGAP-ID",              M, "INTEGER", "TS 38.413 §9.3.3.1",  "ngap.aMF_UE_NGAP_ID"),
    ie("RAN-UE-NGAP-ID",              M, "INTEGER", "TS 38.413 §9.3.3.2",  "ngap.rAN_UE_NGAP_ID"),
    ie("Old AMF-UE-NGAP-ID",          O, "INTEGER", "TS 38.413 §9.3.3.1",  "ngap.oldAMF_UE_NGAP_ID"),
    ie("UE Aggregate Maximum Bit Rate",M, "SEQUENCE","TS 38.413 §9.3.1.63","ngap.uEAggregateMaximumBitRateUL"),
    ie("Core Network Assistance Info", O, "SEQUENCE","TS 38.413 §9.3.1.15","ngap.coreNetworkAssistanceInformation"),
    ie("GUAMI",                        M, "SEQUENCE","TS 38.413 §9.3.3.25","ngap.gUAMI"),
    ie("PDU Session Resource Setup List", M, "LIST", "TS 38.413 §9.3.4.1", "ngap.pDUSessionResourceSetupListCxtReq"),
    ie("Allowed NSSAI",               M, "LIST",    "TS 38.413 §9.3.1.43","ngap.allowedNSSAI"),
    ie("UE Security Capabilities",    M, "SEQUENCE","TS 38.413 §9.3.1.86","ngap.uESecurityCapabilities"),
    ie("Security Key",                M, "BIT-STR", "TS 38.413 §9.3.1.77","ngap.securityKey"),
    ie("Trace Activation",            O, "SEQUENCE","TS 38.413 §9.3.1.60","ngap.traceActivation"),
    ie("Mobility Restriction List",   O, "SEQUENCE","TS 38.413 §9.3.1.46","ngap.mobilityRestrictionList"),
    ie("UE Radio Capability",         O, "OCTET-STR","TS 38.413 §9.3.1.85","ngap.uERadioCapability"),
    ie("Index to RAT/Frequency Selection Priority", O, "INTEGER", "TS 38.413 §9.3.1.73", "ngap.indexToRFSP"),
    ie("Masked IMEISV",               O, "BIT-STR", "TS 38.413 §9.3.1.44","ngap.maskedIMEISV"),
    ie("NAS PDU",                     O, "OCTET-STR","TS 38.413 §9.3.1.47","ngap.nAS_PDU"),
    ie("Emergency Fallback Indicator",O, "SEQUENCE","TS 38.413 §9.3.1.21","ngap.emergencyFallbackIndicator"),
    ie("RRC Inactive Transition Report Request", O, "ENUM", "TS 38.413 §9.3.1.72", "ngap.rRCInactiveTransitionReportRequest"),
    ie("UE Radio Capability for Paging", O, "SEQUENCE", "TS 38.413 §9.3.1.84", "ngap.uERadioCapabilityForPaging"),
    ie("Redirection Voice Fallback",  O, "ENUM",    "TS 38.413 §9.3.1.67","ngap.redirectionVoiceFallback"),
    ie("Location Reporting Request Type", O, "SEQUENCE", "TS 38.413 §9.3.1.38", "ngap.locationReportingRequestType"),
    ie("CN Assisted RAN Tuning",      O, "SEQUENCE","TS 38.413 §9.3.1.13","ngap.cNAssistedRANTuning"),
    ie("Sidelink Indicator",          O, "ENUM",    "TS 38.413 §9.3.1.78","ngap.sidelinkIndicator"),
]

NGAP_INITIAL_CONTEXT_SETUP_RESPONSE_IES: List[IE] = [
    ie("AMF-UE-NGAP-ID",              M, "INTEGER", "TS 38.413 §9.3.3.1",  "ngap.aMF_UE_NGAP_ID"),
    ie("RAN-UE-NGAP-ID",              M, "INTEGER", "TS 38.413 §9.3.3.2",  "ngap.rAN_UE_NGAP_ID"),
    ie("PDU Session Resource Setup Response List", O, "LIST", "TS 38.413 §9.3.4.1", "ngap.pDUSessionResourceSetupListCxtRes"),
    ie("PDU Session Resource Failed To Setup List", O, "LIST", "TS 38.413 §9.3.4.1", "ngap.pDUSessionResourceFailedToSetupListCxtRes"),
    ie("Criticality Diagnostics",     O, "SEQUENCE","TS 38.413 §9.3.1.16","ngap.criticalityDiagnostics"),
]

NGAP_INITIAL_CONTEXT_SETUP_FAILURE_IES: List[IE] = [
    ie("AMF-UE-NGAP-ID",              M, "INTEGER", "TS 38.413 §9.3.3.1",  "ngap.aMF_UE_NGAP_ID"),
    ie("RAN-UE-NGAP-ID",              M, "INTEGER", "TS 38.413 §9.3.3.2",  "ngap.rAN_UE_NGAP_ID"),
    ie("PDU Session Resource Failed List", O, "LIST", "TS 38.413 §9.3.4.1","ngap.pDUSessionResourceFailedToSetupListCxtFail"),
    ie("Cause",                       M, "CHOICE",  "TS 38.413 §9.3.1.2",  "ngap.cause"),
    ie("Criticality Diagnostics",     O, "SEQUENCE","TS 38.413 §9.3.1.16", "ngap.criticalityDiagnostics"),
]

NGAP_PDU_SESSION_RESOURCE_SETUP_REQUEST_IES: List[IE] = [
    ie("AMF-UE-NGAP-ID",              M, "INTEGER", "TS 38.413 §9.3.3.1",  "ngap.aMF_UE_NGAP_ID"),
    ie("RAN-UE-NGAP-ID",              M, "INTEGER", "TS 38.413 §9.3.3.2",  "ngap.rAN_UE_NGAP_ID"),
    ie("RAN Paging Priority",         O, "INTEGER", "TS 38.413 §9.3.1.51", "ngap.rANPagingPriority"),
    ie("NAS PDU",                     O, "OCTET-STR","TS 38.413 §9.3.1.47","ngap.nAS_PDU"),
    ie("PDU Session Resource Setup List", M, "LIST","TS 38.413 §9.3.4.1",  "ngap.pDUSessionResourceSetupListSUReq"),
    ie("UE Aggregate Maximum Bit Rate",O, "SEQUENCE","TS 38.413 §9.3.1.63","ngap.uEAggregateMaximumBitRateUL"),
]

NGAP_UE_CONTEXT_RELEASE_COMMAND_IES: List[IE] = [
    ie("UE-NGAP-IDs",                 M, "CHOICE",  "TS 38.413 §9.3.3.25","ngap.uE_NGAP_IDs"),
    ie("Cause",                       M, "CHOICE",  "TS 38.413 §9.3.1.2",  "ngap.cause"),
]

NGAP_UE_CONTEXT_RELEASE_COMPLETE_IES: List[IE] = [
    ie("AMF-UE-NGAP-ID",              M, "INTEGER", "TS 38.413 §9.3.3.1",  "ngap.aMF_UE_NGAP_ID"),
    ie("RAN-UE-NGAP-ID",              M, "INTEGER", "TS 38.413 §9.3.3.2",  "ngap.rAN_UE_NGAP_ID"),
    ie("User Location Information",   O, "CHOICE",  "TS 38.413 §9.3.1.88","ngap.userLocationInformation"),
    ie("Information on Recommended Cells and RAN Nodes", O, "SEQUENCE", "TS 38.413 §9.3.1.30", "ngap.infoOnRecommendedCellsAndRANNodesForPaging"),
    ie("PDU Session Resource List (HO)", O, "LIST", "TS 38.413 §9.3.4.1", "ngap.pDUSessionResourceListCxtRelCpl"),
    ie("Criticality Diagnostics",     O, "SEQUENCE","TS 38.413 §9.3.1.16","ngap.criticalityDiagnostics"),
]

NGAP_HANDOVER_REQUEST_IES: List[IE] = [
    ie("AMF-UE-NGAP-ID",              M, "INTEGER", "TS 38.413 §9.3.3.1",  "ngap.aMF_UE_NGAP_ID"),
    ie("Handover Type",               M, "ENUM",    "TS 38.413 §9.3.1.26","ngap.handoverType"),
    ie("Cause",                       M, "CHOICE",  "TS 38.413 §9.3.1.2",  "ngap.cause"),
    ie("UE Aggregate Maximum Bit Rate",M, "SEQUENCE","TS 38.413 §9.3.1.63","ngap.uEAggregateMaximumBitRateUL"),
    ie("Core Network Assistance Info", O, "SEQUENCE","TS 38.413 §9.3.1.15","ngap.coreNetworkAssistanceInformation"),
    ie("UE Security Capabilities",    M, "SEQUENCE","TS 38.413 §9.3.1.86","ngap.uESecurityCapabilities"),
    ie("Security Context",            M, "SEQUENCE","TS 38.413 §9.3.1.76","ngap.securityContext"),
    ie("New Security Context Indicator",O,"ENUM",   "TS 38.413 §9.3.1.48","ngap.newSecurityContextInd"),
    ie("NASC",                        O, "OCTET-STR","TS 38.413 §9.3.1.47","ngap.nAS_PDU"),
    ie("PDU Session Resource List (HO)",M,"LIST",   "TS 38.413 §9.3.4.1", "ngap.pDUSessionResourceListHOReq"),
    ie("Allowed NSSAI",               M, "LIST",    "TS 38.413 §9.3.1.43","ngap.allowedNSSAI"),
    ie("Mobility Restriction List",   O, "SEQUENCE","TS 38.413 §9.3.1.46","ngap.mobilityRestrictionList"),
    ie("Location Reporting Request Type", O, "SEQUENCE", "TS 38.413 §9.3.1.38", "ngap.locationReportingRequestType"),
    ie("RRC Inactive Transition Report Request", O, "ENUM", "TS 38.413 §9.3.1.72", "ngap.rRCInactiveTransitionReportRequest"),
    ie("GUAMI",                        M, "SEQUENCE","TS 38.413 §9.3.3.25","ngap.gUAMI"),
    ie("Redirection Voice Fallback",  O, "ENUM",    "TS 38.413 §9.3.1.67","ngap.redirectionVoiceFallback"),
    ie("CN Assisted RAN Tuning",      O, "SEQUENCE","TS 38.413 §9.3.1.13","ngap.cNAssistedRANTuning"),
    ie("SRVCC Operation Possible",    O, "ENUM",    "TS 38.413 §9.3.1.81","ngap.sRVCCOperationPossible"),
    ie("IAB Authorized",              O, "ENUM",    "TS 38.413 §9.3.1.28","ngap.iABAuthorized"),
    ie("Enhanced Coverage Restriction",O,"ENUM",   "TS 38.413 §9.3.1.22","ngap.enhancedCoverageRestriction"),
    ie("UE Differentiation Info",     O, "SEQUENCE","TS 38.413 §9.3.1.62","ngap.uEDifferentiationInfo"),
    ie("NR V2X Services Authorized",  O, "SEQUENCE","TS 38.413 §9.3.1.49","ngap.nRV2XServicesAuthorized"),
    ie("LTE V2X Services Authorized", O, "SEQUENCE","TS 38.413 §9.3.1.39","ngap.lTEV2XServicesAuthorized"),
    ie("PC5 QoS Parameters",          O, "SEQUENCE","TS 38.413 §9.3.1.52","ngap.pC5QoSParameters"),
    ie("CE Mode B Restricted",        O, "ENUM",    "TS 38.413 §9.3.1.8", "ngap.cEmodeBRestricted"),
    ie("UE History Information from the UE", O, "OCTET-STR", "TS 38.413 §9.3.1.62a", "ngap.uEHistoryInformationFromTheUE"),
]

NGAP_NGSETUP_REQUEST_IES: List[IE] = [
    ie("Global RAN Node ID",          M, "CHOICE",  "TS 38.413 §9.3.3.5",  "ngap.globalRANNodeID"),
    ie("RAN Node Name",               O, "PrintStr","TS 38.413 §9.3.1.53","ngap.rANNodeName"),
    ie("Supported TA List",           M, "LIST",    "TS 38.413 §9.3.1.83","ngap.supportedTAList"),
    ie("Default Paging DRX",          M, "ENUM",    "TS 38.413 §9.3.1.17","ngap.defaultPagingDRX"),
    ie("UE Retention Information",    O, "ENUM",    "TS 38.413 §9.3.1.61","ngap.uERetentionInformation"),
    ie("NB-IoT Default Paging DRX",   O, "ENUM",    "TS 38.413 §9.3.1.17a","ngap.nBIoTDefaultPagingDRX"),
    ie("Extended RAN Node Name",      O, "SEQUENCE","TS 38.413 §9.3.1.23","ngap.extendedRANNodeName"),
]

NGAP_PAGING_IES: List[IE] = [
    ie("UE Paging Identity",          M, "CHOICE",  "TS 38.413 §9.3.3.22","ngap.uEPagingIdentity"),
    ie("Paging DRX",                  O, "ENUM",    "TS 38.413 §9.3.1.55","ngap.pagingDRX"),
    ie("TAI List for Paging",         M, "LIST",    "TS 38.413 §9.3.1.58","ngap.tAIListForPaging"),
    ie("Paging Priority",             O, "ENUM",    "TS 38.413 §9.3.1.56","ngap.pagingPriority"),
    ie("UE Radio Capability for Paging", O, "SEQUENCE", "TS 38.413 §9.3.1.84", "ngap.uERadioCapabilityForPaging"),
    ie("Paging Origin",               O, "ENUM",    "TS 38.413 §9.3.1.57","ngap.pagingOrigin"),
    ie("Assisted Information for Paging", O, "SEQUENCE", "TS 38.413 §9.3.1.4", "ngap.assistedInformationForPaging"),
    ie("NB-IoT Paging DRX",           O, "ENUM",    "TS 38.413 §9.3.1.17a","ngap.nBIoTPagingDRX"),
    ie("Enhanced Coverage Restriction",O, "ENUM",   "TS 38.413 §9.3.1.22","ngap.enhancedCoverageRestriction"),
    ie("WUS Assistance Information",  O, "SEQUENCE","TS 38.413 §9.3.1.92","ngap.wUSAssistanceInformation"),
    ie("EUTRA Paging DRX",            O, "ENUM",    "TS 38.413 §9.3.1.17b","ngap.eUTRAPagingDRX"),
    ie("CE-mode-B Restricted",        O, "ENUM",    "TS 38.413 §9.3.1.8", "ngap.cEmodeBRestricted"),
    ie("NR Paging eDRX Info",         O, "SEQUENCE","TS 38.413 §9.3.1.50","ngap.nRPagingeDRXInfo"),
    ie("NR Paging Time Window",       O, "ENUM",    "TS 38.413 §9.3.1.50a","ngap.nRPagingTimeWindow"),
]

NGAP_MESSAGE_IE_SCHEMAS: Dict[str, List[IE]] = {
    "NGAP_InitialContextSetup_request":          NGAP_INITIAL_CONTEXT_SETUP_REQUEST_IES,
    "NGAP_InitialContextSetup_response":         NGAP_INITIAL_CONTEXT_SETUP_RESPONSE_IES,
    "NGAP_InitialContextSetup_failure":          NGAP_INITIAL_CONTEXT_SETUP_FAILURE_IES,
    "NGAP_PDUSessionResourceSetup_request":      NGAP_PDU_SESSION_RESOURCE_SETUP_REQUEST_IES,
    "NGAP_UEContextRelease_request":             NGAP_UE_CONTEXT_RELEASE_COMMAND_IES,
    "NGAP_UEContextRelease_complete":            NGAP_UE_CONTEXT_RELEASE_COMPLETE_IES,
    "NGAP_HandoverPreparation_request":          NGAP_HANDOVER_REQUEST_IES,
    "NGAP_NGSetup_request":                      NGAP_NGSETUP_REQUEST_IES,
    "NGAP_Paging_request":                       NGAP_PAGING_IES,
}

NGAP_TSHARK_FIELD_MAP: Dict[str, str] = {
    "ngap.aMF_UE_NGAP_ID":              "AMF-UE-NGAP-ID",
    "ngap.rAN_UE_NGAP_ID":              "RAN-UE-NGAP-ID",
    "ngap.cause":                       "Cause",
    "ngap.radioNetwork":                "Cause (Radio Network)",
    "ngap.transport":                   "Cause (Transport)",
    "ngap.nas":                         "Cause (NAS)",
    "ngap.protocol":                    "Cause (Protocol)",
    "ngap.misc":                        "Cause (Misc)",
    "ngap.uEAggregateMaximumBitRateUL": "UE AMBR UL (bps)",
    "ngap.uEAggregateMaximumBitRateDL": "UE AMBR DL (bps)",
    "ngap.securityKey":                 "Security Key (KeNB/NH)",
    "ngap.encryptionAlgorithms":        "Encryption Algorithms",
    "ngap.integrityProtectionAlgorithms": "Integrity Protection Algorithms",
    "ngap.allowedNSSAI":                "Allowed NSSAI",
    "ngap.uESecurityCapabilities":      "UE Security Capabilities",
    "ngap.nAS_PDU":                     "NAS PDU (embedded)",
    "ngap.nRCGI":                       "NR-CGI",
    "ngap.pLMNIdentity":                "PLMN Identity",
    "ngap.gNBId":                       "gNB ID",
    "ngap.tAC":                         "TAC",
    "ngap.globalRANNodeID":             "Global RAN Node ID",
    "ngap.rANNodeName":                 "RAN Node Name",
    "ngap.supportedTAList":             "Supported TA List",
    "ngap.handoverType":                "Handover Type",
    "ngap.gUAMI":                       "GUAMI",
    "ngap.pagingDRX":                   "Paging DRX",
    "ngap.defaultPagingDRX":            "Default Paging DRX",
    "ngap.uEPagingIdentity":            "UE Paging Identity",
    "ngap.tAIListForPaging":            "TAI List for Paging",
    "ngap.indexToRFSP":                 "Index to RFSP",
    "ngap.maskedIMEISV":                "Masked IMEISV",
    "ngap.mobilityRestrictionList":     "Mobility Restriction List",
    "ngap.rRCInactiveTransitionReportRequest": "RRC Inactive Transition Report Request",
    "ngap.userLocationInformation":     "User Location Information",
    "ngap.criticalityDiagnostics":      "Criticality Diagnostics",
    "ngap.procedurecode":               "Procedure Code",
    "ngap.successfuloutcome":           "Successful Outcome",
    "ngap.unsuccessfuloutcome":         "Unsuccessful Outcome",
    "ngap.initiatingmessage":           "Initiating Message",
}

# ═════════════════════════════════════════════════════════════════════
# RRC — TS 38.331
# ═════════════════════════════════════════════════════════════════════

RRC_SETUP_REQUEST_IES: List[IE] = [
    ie("ue-Identity (randomValue or ng-5G-S-TMSI-Part1)", M, "CHOICE", "TS 38.331 §6.3.2", "nr_rrc.ue_Identity"),
    ie("establishmentCause",             M, "ENUM",    "TS 38.331 §6.3.2",  "nr_rrc.establishmentCause"),
]

RRC_SETUP_IES: List[IE] = [
    ie("radioBearerConfig",             M, "SEQUENCE", "TS 38.331 §6.3.2",  "nr_rrc.radioBearerConfig"),
    ie("masterCellGroup",               M, "OCTET-STR","TS 38.331 §6.3.2",  "nr_rrc.masterCellGroup"),
    ie("lateNonCriticalExtension",      O, "OCTET-STR","TS 38.331 §6.3.2",  ""),
]

RRC_REESTABLISHMENT_REQUEST_IES: List[IE] = [
    ie("ue-Identity (C-RNTI + physCellId + shortMAC-I)", M, "SEQUENCE", "TS 38.331 §6.3.2", "nr_rrc.c_rnti"),
    ie("reestablishmentCause",          M, "ENUM",    "TS 38.331 §6.3.2",  "nr_rrc.reestablishmentCause"),
]

RRC_REESTABLISHMENT_IES: List[IE] = [
    ie("nextHopChainingCount",          M, "INTEGER", "TS 38.331 §6.3.2",  "nr_rrc.nextHopChainingCount"),
    ie("lateNonCriticalExtension",      O, "OCTET-STR","TS 38.331 §6.3.2", ""),
]

RRC_RECONFIGURATION_IES: List[IE] = [
    ie("radioBearerConfig",             O, "SEQUENCE", "TS 38.331 §6.3.2", "nr_rrc.radioBearerConfig"),
    ie("secondaryCellGroup",            O, "OCTET-STR","TS 38.331 §6.3.2", "nr_rrc.secondaryCellGroup"),
    ie("measConfig",                    O, "SEQUENCE", "TS 38.331 §6.3.2", "nr_rrc.measConfig"),
    ie("lateNonCriticalExtension",      O, "OCTET-STR","TS 38.331 §6.3.2", ""),
    ie("masterCellGroup",               O, "OCTET-STR","TS 38.331 §6.3.2", "nr_rrc.masterCellGroup"),
    ie("fullConfig",                    O, "ENUM",    "TS 38.331 §6.3.2",  ""),
    ie("dedicatedNAS-MessageList",      O, "LIST",    "TS 38.331 §6.3.2",  ""),
    ie("masterKeyUpdate",               O, "SEQUENCE","TS 38.331 §6.3.2",  "nr_rrc.nextHopChainingCount"),
    ie("dedicatedSIB1-Delivery",        O, "OCTET-STR","TS 38.331 §6.3.2", ""),
    ie("dedicatedSystemInformationDelivery", O, "OCTET-STR", "TS 38.331 §6.3.2", ""),
    ie("onDemandSIB-RequestList",       O, "SEQUENCE","TS 38.331 §6.3.2",  ""),
    ie("OtherConfig",                   O, "SEQUENCE","TS 38.331 §6.3.2",  ""),
    ie("nonCriticalExtension",          O, "SEQUENCE","TS 38.331 §6.3.2",  ""),
]

RRC_RELEASE_IES: List[IE] = [
    ie("redirectedCarrierInfo",         O, "CHOICE",  "TS 38.331 §6.3.2", "nr_rrc.redirectedCarrierInfo"),
    ie("cellReselectionPriorities",     O, "SEQUENCE","TS 38.331 §6.3.2",  ""),
    ie("suspendConfig",                 O, "SEQUENCE","TS 38.331 §6.3.2",  "nr_rrc.fullI_RNTI"),
    ie("deprioritisationReq",           O, "SEQUENCE","TS 38.331 §6.3.2",  ""),
    ie("waitTime",                      O, "INTEGER", "TS 38.331 §6.3.2",  ""),
    ie("releaseCause",                  M, "ENUM",    "TS 38.331 §6.3.2",  "nr_rrc.releaseCause"),
]

RRC_SECURITY_MODE_COMMAND_IES: List[IE] = [
    ie("securityAlgorithmConfig",       M, "SEQUENCE","TS 38.331 §6.3.2",  "nr_rrc.cipheringAlgorithm"),
]

RRC_UE_CAPABILITY_ENQUIRY_IES: List[IE] = [
    ie("ue-CapabilityRAT-RequestList",  M, "LIST",    "TS 38.331 §6.3.2",  "nr_rrc.rat_Type"),
    ie("frequencyBandListFilter",       O, "LIST",    "TS 38.331 §6.3.2",  ""),
    ie("requestedFreqBandsNR-MRDC",     O, "LIST",    "TS 38.331 §6.3.2",  ""),
    ie("requestedCapabilityNR",         O, "OCTET-STR","TS 38.331 §6.3.2", ""),
]

RRC_MEASUREMENT_REPORT_IES: List[IE] = [
    ie("measId",                        M, "INTEGER", "TS 38.331 §6.3.5",  "nr_rrc.measId"),
    ie("measResultServingMOList",       M, "LIST",    "TS 38.331 §6.3.5",  "nr_rrc.measResultServingMOList"),
    ie("measResultNeighCells",          O, "CHOICE",  "TS 38.331 §6.3.5",  "nr_rrc.measResultNeighCells"),
]

RRC_MESSAGE_IE_SCHEMAS: Dict[str, List[IE]] = {
    "RRC_Setup_request":                  RRC_SETUP_REQUEST_IES,
    "RRC_Setup_complete":                 RRC_SETUP_IES,
    "RRC_Reestablishment_request":        RRC_REESTABLISHMENT_REQUEST_IES,
    "RRC_Reestablishment_complete":       RRC_REESTABLISHMENT_IES,
    "RRC_Reconfiguration_command":        RRC_RECONFIGURATION_IES,
    "RRC_Release_command":                RRC_RELEASE_IES,
    "RRC_SecurityMode_command":           RRC_SECURITY_MODE_COMMAND_IES,
    "RRC_UECapabilityEnquiry_request":    RRC_UE_CAPABILITY_ENQUIRY_IES,
    "RRC_MeasurementReport_request":      RRC_MEASUREMENT_REPORT_IES,
}

RRC_TSHARK_FIELD_MAP: Dict[str, str] = {
    "nr_rrc.c_rnti":                     "C-RNTI",
    "nr_rrc.physCellId":                 "Physical Cell ID",
    "nr_rrc.arfcn_ValueNR":              "NR-ARFCN",
    "nr_rrc.subcarrierSpacing":          "Subcarrier Spacing",
    "nr_rrc.establishmentCause":         "Establishment Cause",
    "nr_rrc.reestablishmentCause":       "Reestablishment Cause",
    "nr_rrc.releaseCause":               "Release Cause",
    "nr_rrc.nextHopChainingCount":       "Next Hop Chaining Count",
    "nr_rrc.cipheringAlgorithm":         "Ciphering Algorithm",
    "nr_rrc.integrityProtAlgorithm":     "Integrity Protection Algorithm",
    "nr_rrc.measId":                     "Measurement ID",
    "nr_rrc.rat_Type":                   "RAT Type",
    "nr_rrc.drb_Identity":               "DRB Identity",
    "nr_rrc.srb_Identity":               "SRB Identity",
    "nr_rrc.t304":                       "T304 Timer",
    "nr_rrc.t310":                       "T310 Timer",
    "nr_rrc.t311":                       "T311 Timer",
    "nr_rrc.fullI_RNTI":                 "Full I-RNTI (Resume ID)",
    "nr_rrc.redirectedCarrierInfo":      "Redirected Carrier Info",
}

# ═════════════════════════════════════════════════════════════════════
# F1AP — TS 38.473
# ═════════════════════════════════════════════════════════════════════

DISC_F1AP = 0x1a    # synthetic payload discriminator

F1AP_PROCS: Dict[int, str] = {
    0x01: "F1AP_F1Setup",                      # TS 38.473 §8.2.3
    0x02: "F1AP_UEContextSetup",               # TS 38.473 §8.3.1
    0x03: "F1AP_UEContextModification",        # TS 38.473 §8.3.3
    0x04: "F1AP_UEContextRelease",             # TS 38.473 §8.3.2
    0x05: "F1AP_DLRRCMessageTransfer",         # TS 38.473 §8.4.2
    0x06: "F1AP_ULRRCMessageTransfer",         # TS 38.473 §8.4.3
    0x07: "F1AP_InitialULRRCMessageTransfer",  # TS 38.473 §8.4.1
    0x08: "F1AP_Paging",                       # TS 38.473 §8.7.1
    0x09: "F1AP_gNBDUConfigurationUpdate",     # TS 38.473 §8.2.5
    0x0a: "F1AP_gNBCUConfigurationUpdate",     # TS 38.473 §8.2.6
    0x0b: "F1AP_UEContextModificationRequired",# TS 38.473 §8.3.4
    0x0c: "F1AP_ErrorIndication",              # TS 38.473 §8.9.1
    0x0d: "F1AP_SRBSetup",                     # TS 38.473 §8.3.1
    0x0e: "F1AP_DRBSetup",                     # TS 38.473 §8.3.1
}

F1AP_SETUP_REQUEST_IES: List[IE] = [
    ie("Transaction ID",              M, "INTEGER",  "TS 38.473 §9.3.1.7",  "f1ap.transactionID"),
    ie("gNB-DU-ID",                   M, "INTEGER",  "TS 38.473 §9.3.1.9",  "f1ap.gNB_DU_ID"),
    ie("gNB-DU-Name",                 O, "PrintStr", "TS 38.473 §9.3.1.10", "f1ap.gNB_DU_Name"),
    ie("gNB-DU-Served-Cells-List",    M, "LIST",     "TS 38.473 §9.3.2.1",  "f1ap.gNB_DU_Served_Cells_List"),
    ie("gNB-CU-Name",                 O, "PrintStr", "TS 38.473 §9.3.1.14", "f1ap.gNB_CU_Name"),
    ie("RRC-Version",                 M, "SEQUENCE", "TS 38.473 §9.3.1.39", "f1ap.rRC_Version"),
    ie("Transport-Layer-Address-Info",O, "SEQUENCE", "TS 38.473 §9.3.1.51", "f1ap.transport_Layer_Address_Info"),
    ie("BAP-Address",                 O, "BIT-STR",  "TS 38.473 §9.3.1.54", "f1ap.bAP_Address"),
    ie("Extended gNB-DU-Name",        O, "SEQUENCE", "TS 38.473 §9.3.1.131","f1ap.extendedgNBDUName"),
]

F1AP_SETUP_RESPONSE_IES: List[IE] = [
    ie("Transaction ID",              M, "INTEGER",  "TS 38.473 §9.3.1.7",  "f1ap.transactionID"),
    ie("gNB-CU-Name",                 O, "PrintStr", "TS 38.473 §9.3.1.14", "f1ap.gNB_CU_Name"),
    ie("Cells-to-be-Activated-List",  O, "LIST",     "TS 38.473 §9.3.2.1",  "f1ap.cells_to_be_Activated_List"),
    ie("RRC-Version",                 M, "SEQUENCE", "TS 38.473 §9.3.1.39", "f1ap.rRC_Version"),
    ie("Transport-Layer-Address-Info",O, "SEQUENCE", "TS 38.473 §9.3.1.51", "f1ap.transport_Layer_Address_Info"),
    ie("UL-BH-Non-UP-Traffic-Mapping",O, "LIST",    "TS 38.473 §9.3.1.115","f1ap.uL_BH_Non_UP_Traffic_Mapping"),
    ie("BAP-Address",                 O, "BIT-STR",  "TS 38.473 §9.3.1.54", "f1ap.bAP_Address"),
    ie("Extended gNB-CU-Name",        O, "SEQUENCE", "TS 38.473 §9.3.1.131","f1ap.extendedgNBCUName"),
]

F1AP_UE_CONTEXT_SETUP_REQUEST_IES: List[IE] = [
    ie("gNB-CU-UE-F1AP-ID",          M, "INTEGER",  "TS 38.473 §9.3.3.1",  "f1ap.gNB_CU_UE_F1AP_ID"),
    ie("gNB-DU-UE-F1AP-ID",          O, "INTEGER",  "TS 38.473 §9.3.3.2",  "f1ap.gNB_DU_UE_F1AP_ID"),
    ie("SP-Cell-ID (NR-CGI)",         M, "SEQUENCE", "TS 38.473 §9.3.1.12", "f1ap.nRCGI"),
    ie("Serv-Cell-Index",             M, "INTEGER",  "TS 38.473 §9.3.1.41", "f1ap.serv_Cell_Index"),
    ie("SP-Cell-UL-Config",           O, "ENUM",     "TS 38.473 §9.3.1.48", "f1ap.sP_Cell_UL_Config"),
    ie("DU-to-CU-RRC-Information",    M, "SEQUENCE", "TS 38.473 §9.3.1.33", "f1ap.dU_To_CU_RRC_Information"),
    ie("Candidate-SP-Cell-List",      O, "LIST",     "TS 38.473 §9.3.1.106","f1ap.candidate_SP_Cell_List"),
    ie("DRX-Cycle",                   O, "SEQUENCE", "TS 38.473 §9.3.1.24", "f1ap.dRX_Cycle"),
    ie("Resource-Coordination-Transfer-Container", O, "OCTET-STR", "TS 38.473 §9.3.1.38", "f1ap.resource_Coordination_Transfer_Container"),
    ie("SCell-to-be-Setup-List",      O, "LIST",     "TS 38.473 §9.3.1.5",  "f1ap.sCell_to_be_Setup_List"),
    ie("SRB-to-be-Setup-List",        O, "LIST",     "TS 38.473 §9.3.2.7",  "f1ap.sRBs_to_be_Setup_List"),
    ie("DRB-to-be-Setup-List",        O, "LIST",     "TS 38.473 §9.3.2.4",  "f1ap.dRBs_to_be_Setup_List"),
    ie("InactivityMonitoringRequest", O, "ENUM",     "TS 38.473 §9.3.1.68", "f1ap.inactivityMonitoringRequest"),
    ie("RAT-FrequencyPriorityInformation", O, "CHOICE", "TS 38.473 §9.3.1.113", "f1ap.rAT_FrequencyPriorityInformation"),
    ie("RRC-Container",               O, "OCTET-STR","TS 38.473 §9.3.1.48", "f1ap.rRC_Container"),
    ie("masked-IMEISV",               O, "BIT-STR",  "TS 38.473 §9.3.1.45", "f1ap.masked_IMEISV"),
    ie("servingPLMN",                 O, "OCTET-STR","TS 38.473 §9.3.1.47", "f1ap.servingPLMN"),
    ie("GNB-DU-UE-AMBR-UL",          O, "INTEGER",  "TS 38.473 §9.3.1.4",  "f1ap.gNB_DU_UE_AMBR_UL"),
    ie("UE-Associatd-LC-F1AP-IDs",   O, "SEQUENCE", "TS 38.473 §9.3.3.5",  "f1ap.uE_associatedLC_F1AP_IDs"),
]

F1AP_DL_RRC_MESSAGE_IES: List[IE] = [
    ie("gNB-CU-UE-F1AP-ID",          M, "INTEGER",  "TS 38.473 §9.3.3.1",  "f1ap.gNB_CU_UE_F1AP_ID"),
    ie("gNB-DU-UE-F1AP-ID",          M, "INTEGER",  "TS 38.473 §9.3.3.2",  "f1ap.gNB_DU_UE_F1AP_ID"),
    ie("Old-gNB-DU-UE-F1AP-ID",      O, "INTEGER",  "TS 38.473 §9.3.3.2",  "f1ap.oldgNB_DU_UE_F1AP_ID"),
    ie("SRBID",                       M, "INTEGER",  "TS 38.473 §9.3.1.42", "f1ap.sRBID"),
    ie("Execute-Duplication",         O, "ENUM",     "TS 38.473 §9.3.1.68", "f1ap.execute_Duplication"),
    ie("RRC-Container",               M, "OCTET-STR","TS 38.473 §9.3.1.48", "f1ap.rRC_Container"),
    ie("RAT-FrequencyPriorityInformation", O, "CHOICE", "TS 38.473 §9.3.1.113", "f1ap.rAT_FrequencyPriorityInformation"),
    ie("RLC-PDU-Delivery-Delay-Result", O, "LIST", "TS 38.473 §9.3.1.100", "f1ap.rLC_PDU_Delivery_Delay_Result"),
    ie("Buffered-Data-List",          O, "LIST",     "TS 38.473 §9.3.1.130","f1ap.buffered_Data_List"),
    ie("UE-Context-Not-Retrievable",  O, "ENUM",     "TS 38.473 §9.3.1.68", "f1ap.uE_Context_Not_Retrievable"),
]

F1AP_UL_RRC_MESSAGE_IES: List[IE] = [
    ie("gNB-CU-UE-F1AP-ID",          M, "INTEGER",  "TS 38.473 §9.3.3.1",  "f1ap.gNB_CU_UE_F1AP_ID"),
    ie("gNB-DU-UE-F1AP-ID",          M, "INTEGER",  "TS 38.473 §9.3.3.2",  "f1ap.gNB_DU_UE_F1AP_ID"),
    ie("SRBID",                       M, "INTEGER",  "TS 38.473 §9.3.1.42", "f1ap.sRBID"),
    ie("RRC-Container",               M, "OCTET-STR","TS 38.473 §9.3.1.48", "f1ap.rRC_Container"),
    ie("Selected-PLMN-ID",            O, "OCTET-STR","TS 38.473 §9.3.1.47", "f1ap.selectedPLMN_ID"),
    ie("RLC-PDCP-SNs",                O, "SEQUENCE", "TS 38.473 §9.3.1.99", "f1ap.rLC_PDCP_SNs"),
    ie("PDCP-Count",                  O, "SEQUENCE", "TS 38.473 §9.3.1.66", "f1ap.pdcp_Count"),
    ie("New-PDCP-UE-Data-PDU",        O, "OCTET-STR","TS 38.473 §9.3.1.130","f1ap.new_PDCP_UE_Data_PDU"),
]

F1AP_INITIAL_UL_RRC_MESSAGE_IES: List[IE] = [
    ie("gNB-DU-UE-F1AP-ID",          M, "INTEGER",  "TS 38.473 §9.3.3.2",  "f1ap.gNB_DU_UE_F1AP_ID"),
    ie("NR-CGI",                      M, "SEQUENCE", "TS 38.473 §9.3.1.12", "f1ap.nRCGI"),
    ie("C-RNTI",                      M, "INTEGER",  "TS 38.473 §9.3.1.13", "f1ap.c_RNTI"),
    ie("RRC-Container (RRCSetupRequest)", M, "OCTET-STR","TS 38.473 §9.3.1.48", "f1ap.rRC_Container"),
    ie("DU-to-CU-RRC-Information",    M, "SEQUENCE", "TS 38.473 §9.3.1.33", "f1ap.dU_To_CU_RRC_Information"),
    ie("SubFrameAssignment",          O, "ENUM",     "TS 38.473 §9.3.1.49", "f1ap.subFrameAssignment"),
    ie("PDCCH-SearchSpace-ID",        O, "INTEGER",  "TS 38.473 §9.3.1.25", "f1ap.pDCCH_SearchSpace_ID"),
    ie("UL-TX-Direct-Current-List",   O, "LIST",     "TS 38.473 §9.3.1.55", "f1ap.uL_TX_Direct_Current_List"),
]

F1AP_MESSAGE_IE_SCHEMAS: Dict[str, List[IE]] = {
    "F1AP_F1Setup_request":                     F1AP_SETUP_REQUEST_IES,
    "F1AP_F1Setup_response":                    F1AP_SETUP_RESPONSE_IES,
    "F1AP_UEContextSetup_request":              F1AP_UE_CONTEXT_SETUP_REQUEST_IES,
    "F1AP_DLRRCMessageTransfer_request":        F1AP_DL_RRC_MESSAGE_IES,
    "F1AP_ULRRCMessageTransfer_request":        F1AP_UL_RRC_MESSAGE_IES,
    "F1AP_InitialULRRCMessageTransfer_request": F1AP_INITIAL_UL_RRC_MESSAGE_IES,
}

F1AP_TSHARK_FIELD_MAP: Dict[str, str] = {
    "f1ap.transactionID":         "Transaction ID",
    "f1ap.gNB_DU_ID":             "gNB-DU-ID",
    "f1ap.gNB_CU_UE_F1AP_ID":    "gNB-CU-UE-F1AP-ID",
    "f1ap.gNB_DU_UE_F1AP_ID":    "gNB-DU-UE-F1AP-ID",
    "f1ap.nRCGI":                 "NR-CGI",
    "f1ap.pLMN_Identity":         "PLMN Identity",
    "f1ap.nRCellIdentity":        "NR Cell Identity",
    "f1ap.cause":                 "Cause",
    "f1ap.sRBID":                 "SRB ID",
    "f1ap.dRBID":                 "DRB ID",
    "f1ap.c_RNTI":                "C-RNTI",
    "f1ap.rRC_Container":         "RRC Container",
    "f1ap.gNB_DU_Name":           "gNB-DU Name",
    "f1ap.gNB_CU_Name":           "gNB-CU Name",
    "f1ap.rRC_Version":           "RRC Version",
    "f1ap.gNB_DU_UE_AMBR_UL":    "gNB-DU UE AMBR UL",
    "f1ap.procedureCode":         "Procedure Code",
    "f1ap.serv_Cell_Index":       "Serving Cell Index",
}

F1AP_CAUSE_NAMES: Dict[int, str] = {
    0x01: "radio-network-unspecified",
    0x02: "rl-failure-rlc",
    0x03: "unknown-or-already-allocated-gNBCU-UE-F1AP-ID",
    0x04: "unknown-or-already-allocated-gNBDU-UE-F1AP-ID",
    0x05: "unknown-or-inconsistent-pair-of-UE-F1AP-ID",
    0x06: "interaction-with-other-procedure",
    0x07: "not-supported-qci-value",
    0x08: "action-desirable-for-radio-reasons",
    0x09: "no-radio-resources-available",
    0x0a: "procedure-cancelled",
    0x0b: "normal-release",
    0x0c: "cell-not-available",
    0x0d: "rl-failure-others",
    0x0e: "ue-rejection",
    0x0f: "resources-not-available-for-the-slice",
    0x10: "amf-initiated-abnormal-release",
    0x11: "release-due-to-pre-emption",
}

# ═════════════════════════════════════════════════════════════════════
# E1AP — TS 38.463
# ═════════════════════════════════════════════════════════════════════

DISC_E1AP = 0x1b    # synthetic payload discriminator

E1AP_PROCS: Dict[int, str] = {
    0x01: "E1AP_GNBCUUPSetup",              # TS 38.463 §8.2.3
    0x02: "E1AP_BearerContextSetup",         # TS 38.463 §8.3.1
    0x03: "E1AP_BearerContextModification",  # TS 38.463 §8.3.3
    0x04: "E1AP_BearerContextRelease",       # TS 38.463 §8.3.2
    0x05: "E1AP_BearerContextStatusNotification", # TS 38.463 §8.3.6
    0x06: "E1AP_DLDataNotification",         # TS 38.463 §8.4.2
    0x07: "E1AP_GNBCUCPConfigurationUpdate", # TS 38.463 §8.2.5
    0x08: "E1AP_GNBCUUPConfigurationUpdate", # TS 38.463 §8.2.6
    0x09: "E1AP_ULDataNotification",         # TS 38.463 §8.4.3
    0x0a: "E1AP_DataUsageReport",            # TS 38.463 §8.4.4
    0x0b: "E1AP_GNBCUUPCounterCheck",        # TS 38.463 §8.5.1
    0x0c: "E1AP_ResourceStatusRequest",      # TS 38.463 §8.6.1
    0x0d: "E1AP_IABUPConfigurationUpdate",   # TS 38.463 §8.7.1
    0x0e: "E1AP_ErrorIndication",            # TS 38.463 §8.9.1
}

E1AP_BEARER_CONTEXT_SETUP_REQUEST_IES: List[IE] = [
    ie("gNB-CU-CP-UE-E1AP-ID",       M, "INTEGER",  "TS 38.463 §9.3.3.1",  "e1ap.gNB_CU_CP_UE_E1AP_ID"),
    ie("Security Information",        M, "SEQUENCE", "TS 38.463 §9.3.1.38", "e1ap.security_Information"),
    ie("UE DL Aggregate Maximum Bit Rate", M, "INTEGER", "TS 38.463 §9.3.1.2", "e1ap.uE_DL_Aggregate_Maximum_Bit_Rate"),
    ie("UE DL Maximum Integrity Protected Data Rate", O, "INTEGER", "TS 38.463 §9.3.1.67", "e1ap.uE_DL_Maximum_Integrity_Protected_Data_Rate"),
    ie("Serving PLMN",                M, "OCTET-STR","TS 38.463 §9.3.1.40", "e1ap.serving_PLMN"),
    ie("Activity Notification Level", M, "ENUM",     "TS 38.463 §9.3.1.3",  "e1ap.activityNotificationLevel"),
    ie("UE Inactivity Timer",         O, "INTEGER",  "TS 38.463 §9.3.1.55", "e1ap.uE_Inactivity_Timer"),
    ie("Bearer Context Status Change",O, "ENUM",     "TS 38.463 §9.3.1.4",  "e1ap.bearerContextStatusChange"),
    ie("System Bearer Context Setup Request", M, "CHOICE", "TS 38.463 §9.3.1.42", "e1ap.system_Bearer_Context_Setup_Request"),
    ie("RAN UE ID",                   O, "OCTET-STR","TS 38.463 §9.3.1.35", "e1ap.rAN_UE_ID"),
    ie("gNB-DU-ID",                   O, "INTEGER",  "TS 38.463 §9.3.3.3",  "e1ap.gNB_DU_ID"),
    ie("Trace Activation",            O, "SEQUENCE", "TS 38.463 §9.3.1.45", "e1ap.traceActivation"),
    ie("PDCP Count Reset Indication", O, "ENUM",     "TS 38.463 §9.3.1.70", "e1ap.pdcp_Count_Reset"),
]

E1AP_GNBCUUP_SETUP_REQUEST_IES: List[IE] = [
    ie("Transaction ID",              M, "INTEGER",  "TS 38.463 §9.3.1.7",  "e1ap.transactionID"),
    ie("gNB-CU-UP-ID",               M, "INTEGER",  "TS 38.463 §9.3.3.2",  "e1ap.gNB_CU_UP_ID"),
    ie("gNB-CU-UP-Name",             O, "PrintStr", "TS 38.463 §9.3.1.17", "e1ap.gNB_CU_UP_Name"),
    ie("CN Support",                  M, "ENUM",     "TS 38.463 §9.3.1.11", "e1ap.cN_Support"),
    ie("Supported PLMNs",             M, "LIST",     "TS 38.463 §9.3.1.41", "e1ap.supported_PLMNs"),
    ie("UE-Inactivity-Timer",        O, "INTEGER",  "TS 38.463 §9.3.1.55", "e1ap.uE_Inactivity_Timer"),
    ie("Transport-Layer-Address-Info",O, "SEQUENCE", "TS 38.463 §9.3.1.51", "e1ap.transport_Layer_Address_Info"),
    ie("PDCP-Count-Reset",           O, "ENUM",     "TS 38.463 §9.3.1.70", "e1ap.pdcp_Count_Reset"),
    ie("Extended gNB-CU-UP-Name",    O, "SEQUENCE", "TS 38.463 §9.3.1.131","e1ap.extendedgNBCUUPName"),
]

E1AP_MESSAGE_IE_SCHEMAS: Dict[str, List[IE]] = {
    "E1AP_GNBCUUPSetup_request":         E1AP_GNBCUUP_SETUP_REQUEST_IES,
    "E1AP_BearerContextSetup_request":   E1AP_BEARER_CONTEXT_SETUP_REQUEST_IES,
}

E1AP_TSHARK_FIELD_MAP: Dict[str, str] = {
    "e1ap.transactionID":               "Transaction ID",
    "e1ap.gNB_CU_CP_UE_E1AP_ID":       "gNB-CU-CP-UE-E1AP-ID",
    "e1ap.gNB_CU_UP_UE_E1AP_ID":       "gNB-CU-UP-UE-E1AP-ID",
    "e1ap.gNB_CU_UP_ID":               "gNB-CU-UP-ID",
    "e1ap.gNB_CU_UP_Name":             "gNB-CU-UP Name",
    "e1ap.gNB_DU_ID":                  "gNB-DU-ID",
    "e1ap.cause":                       "Cause",
    "e1ap.pDU_Session_ID":             "PDU Session ID",
    "e1ap.sNSSAI":                     "S-NSSAI",
    "e1ap.dRB_ID":                     "DRB ID",
    "e1ap.serving_PLMN":               "Serving PLMN",
    "e1ap.uE_DL_Aggregate_Maximum_Bit_Rate": "UE DL Aggregate Max Bit Rate",
    "e1ap.activityNotificationLevel":  "Activity Notification Level",
    "e1ap.cN_Support":                 "CN Support",
    "e1ap.supported_PLMNs":            "Supported PLMNs",
    "e1ap.procedureCode":              "Procedure Code",
    "e1ap.security_Information":       "Security Information",
}

E1AP_CAUSE_NAMES: Dict[int, str] = {
    0x01: "radio-network-unspecified",
    0x02: "unknown-or-already-allocated-gNBCUCPUEE1APID",
    0x03: "unknown-or-already-allocated-gNBCUUPUEE1APID",
    0x04: "unknown-or-inconsistent-pair-of-UE-E1AP-ID",
    0x05: "encryption-and-integrity-protection-algorithms-not-supported",
    0x06: "UE-context-release",
    0x07: "UP-integrity-protection-not-possible",
    0x08: "UP-confidentiality-protection-not-possible",
    0x09: "multiple-PDU-session-ID-instances",
    0x0a: "unknown-PDU-session-ID",
    0x0b: "multiple-QoS-flow-ID-instances",
    0x0c: "unknown-QoS-flow-ID",
    0x0d: "multiple-DRB-ID-instances",
    0x0e: "unknown-DRB-ID",
    0x0f: "invalid-QoS-combination",
    0x10: "not-supported-5QI-value",
    0x11: "NG-intra-system-handover-triggered",
    0x12: "NG-inter-system-handover-triggered",
    0x13: "XN-handover-triggered",
    0x14: "not-supported-QCI-value",
    0x15: "PDU-session-resource-released",
    0x16: "CU-UP-PDCP-count-wrap-around",
    0x17: "no-radio-resources-available",
    0x18: "resources-not-available-for-the-slice",
    0x19: "PDU-session-resources-flushed-due-to-exceedance-of-max-data-rate",
    0x1a: "PDCP-sequence-number-not-available",
}

# ═════════════════════════════════════════════════════════════════════
# XnAP — TS 38.423
# ═════════════════════════════════════════════════════════════════════

DISC_XNAP = 0x1c    # synthetic payload discriminator

XNAP_PROCS: Dict[int, str] = {
    0x01: "XnAP_XnSetup",                          # TS 38.423 §8.3.5
    0x02: "XnAP_HandoverRequest",                   # TS 38.423 §8.3.1
    0x03: "XnAP_XnUEContextRelease",                # TS 38.423 §8.3.3
    0x04: "XnAP_RANPaging",                         # TS 38.423 §8.3.4
    0x05: "XnAP_SecondaryNodeAddition",             # TS 38.423 §8.4.1 (MR-DC)
    0x06: "XnAP_SecondaryNodeModification",         # TS 38.423 §8.4.3
    0x07: "XnAP_SecondaryNodeRelease",              # TS 38.423 §8.4.5
    0x08: "XnAP_CellActivation",                    # TS 38.423 §8.3.7
    0x09: "XnAP_SONConfiguration",                  # TS 38.423 §8.5.1
    0x0a: "XnAP_RNL_InformationTransfer",          # TS 38.423 §8.5.4
    0x0b: "XnAP_RRCTransfer",                      # TS 38.423 §8.3.6
    0x0c: "XnAP_SNodeAdditionRequestAcknowledge",  # TS 38.423 §8.4.1
    0x0d: "XnAP_SNodeReleaseRequest",              # TS 38.423 §8.4.5
    0x0e: "XnAP_ErrorIndication",                  # TS 38.423 §8.7.1
}

XNAP_SETUP_REQUEST_IES: List[IE] = [
    ie("Global NG-RAN Node ID",        M, "CHOICE",  "TS 38.423 §9.3.1.1",  "xnap.globalNG_RAN_NodeID"),
    ie("TA Support List",              M, "LIST",    "TS 38.423 §9.3.1.19", "xnap.tA_Support_List"),
    ie("PLMN Support Info",            M, "LIST",    "TS 38.423 §9.3.1.18", "xnap.pLMN_Support_Info"),
    ie("Extended UL-X2-GBR PRB Usage",O, "INTEGER", "TS 38.423 §9.3.1.30", "xnap.extended_UL_X2_GBR_PRB_usage"),
    ie("Extended DL-X2-GBR PRB Usage",O, "INTEGER", "TS 38.423 §9.3.1.30", "xnap.extended_DL_X2_GBR_PRB_usage"),
    ie("SRAN-Node-Network-Access-Rate-Reduction", O, "INTEGER", "TS 38.423 §9.3.1.38", ""),
    ie("NB-IoT Support Info",          O, "LIST",    "TS 38.423 §9.3.1.43", ""),
]

XNAP_HANDOVER_REQUEST_IES: List[IE] = [
    ie("Old NG-RAN Node UE XnAP ID",  M, "INTEGER", "TS 38.423 §9.3.3.1",  "xnap.oldNG_RAN_node_UE_XnAP_ID"),
    ie("Cause",                        M, "CHOICE",  "TS 38.423 §9.3.1.2",  "xnap.cause"),
    ie("Target Cell ID",               M, "CHOICE",  "TS 38.423 §9.3.1.20", "xnap.targetCell_ID"),
    ie("GUAMI",                        M, "SEQUENCE","TS 38.423 §9.3.1.22", "xnap.gUAMI"),
    ie("UE Context Information",       M, "SEQUENCE","TS 38.423 §9.3.1.23", "xnap.uE_Context_Info"),
    ie("Target Cell ID (List)",        O, "LIST",    "TS 38.423 §9.3.1.20", ""),
    ie("RRC Context",                  O, "OCTET-STR","TS 38.423 §9.3.1.37","xnap.rRC_Context"),
    ie("GUAMI (List)",                 O, "LIST",    "TS 38.423 §9.3.1.22", ""),
    ie("Expected UE Behaviour",        O, "SEQUENCE","TS 38.423 §9.3.1.27", ""),
    ie("Source NG-RAN Node Mobility Parameters", O, "SEQUENCE", "TS 38.423 §9.3.1.39", ""),
    ie("QMC Info",                     O, "SEQUENCE","TS 38.423 §9.3.1.54", ""),
    ie("Source NODE ID",               O, "CHOICE",  "TS 38.423 §9.3.1.49", ""),
]

XNAP_SN_ADDITION_REQUEST_IES: List[IE] = [
    ie("Old NG-RAN Node UE XnAP ID",  M, "INTEGER", "TS 38.423 §9.3.3.1",  "xnap.oldNG_RAN_node_UE_XnAP_ID"),
    ie("New NG-RAN Node UE XnAP ID",  M, "INTEGER", "TS 38.423 §9.3.3.2",  "xnap.newNG_RAN_node_UE_XnAP_ID"),
    ie("UE Security Capabilities",    M, "SEQUENCE","TS 38.423 §9.3.1.21", "xnap.uE_Security_Capabilities"),
    ie("SN UE Security Capabilities", O, "SEQUENCE","TS 38.423 §9.3.1.21", ""),
    ie("SN-Requested Configuration",  M, "SEQUENCE","TS 38.423 §9.3.1.40", "xnap.sN_Requested_Configuration"),
    ie("MN-to-SN Container",          O, "OCTET-STR","TS 38.423 §9.3.1.36","xnap.mN_To_SN_Container"),
    ie("PLMN Identity",               M, "OCTET-STR","TS 38.423 §9.3.1.17","xnap.pLMN_Identity"),
    ie("Expected UE Behaviour",       O, "SEQUENCE", "TS 38.423 §9.3.1.27",""),
    ie("PDU Session Resources to be Added", M, "LIST", "TS 38.423 §9.3.1.31", "xnap.pDU_Session_Resources"),
    ie("SgNB Security Key",           O, "BIT-STR", "TS 38.423 §9.3.1.41", "xnap.sGNBSecurityKey"),
]

XNAP_MESSAGE_IE_SCHEMAS: Dict[str, List[IE]] = {
    "XnAP_XnSetup_request":                  XNAP_SETUP_REQUEST_IES,
    "XnAP_HandoverRequest_request":           XNAP_HANDOVER_REQUEST_IES,
    "XnAP_SecondaryNodeAddition_request":     XNAP_SN_ADDITION_REQUEST_IES,
}

XNAP_TSHARK_FIELD_MAP: Dict[str, str] = {
    "xnap.globalNG_RAN_NodeID":      "Global NG-RAN Node ID",
    "xnap.cause":                    "Cause",
    "xnap.oldNG_RAN_node_UE_XnAP_ID": "Old NG-RAN Node UE XnAP-ID",
    "xnap.newNG_RAN_node_UE_XnAP_ID": "New NG-RAN Node UE XnAP-ID",
    "xnap.targetCell_ID":            "Target Cell ID",
    "xnap.gUAMI":                    "GUAMI",
    "xnap.uE_Context_ID":            "UE Context ID",
    "xnap.rRC_Context":              "RRC Context",
    "xnap.pLMN_Identity":            "PLMN Identity",
    "xnap.pDU_Session_Resources":    "PDU Session Resources",
    "xnap.sGNBSecurityKey":          "SgNB Security Key",
    "xnap.uE_Security_Capabilities": "UE Security Capabilities",
    "xnap.tA_Support_List":          "TA Support List",
    "xnap.pLMN_Support_Info":        "PLMN Support Info",
    "xnap.procedureCode":            "Procedure Code",
    "xnap.mN_To_SN_Container":       "MN-to-SN Container",
    "xnap.nR_CGI":                   "NR-CGI",
}

XNAP_CAUSE_NAMES: Dict[int, str] = {
    0x01: "radio-network-unspecified",
    0x02: "handover-desirable-for-radio-reasons",
    0x03: "time-critical-handover",
    0x04: "resource-optimisation-handover",
    0x05: "reduce-load-in-serving-cell",
    0x06: "user-inactivity",
    0x07: "radio-connection-with-UE-lost",
    0x08: "failure-in-radio-interface-procedure",
    0x09: "bearer-option-not-supported",
    0x0a: "MCG-mobility",
    0x0b: "SCG-mobility",
    0x0c: "count-reaches-max-value",
    0x0d: "unknown-old-EN-DC-UE-X2AP-ID",
    0x0e: "pDCP-Change-with-PSCell-Change",
    0x0f: "requested-item-not-supported-on-time",
    0x10: "unknown-or-already-allocated-ng-ran-node-ue-xnap-id",
    0x11: "inconsistent-access-and-mobility-policy",
    0x12: "inter-system-handover-triggered",
    0x13: "not-all-requested-PDU-sessions-can-be-forwarded",
    0x14: "no-suitable-cells-in-target-cell-list",
}

# ═════════════════════════════════════════════════════════════════════
# Unified message IE schema lookup
# ═════════════════════════════════════════════════════════════════════

ALL_MESSAGE_IE_SCHEMAS: Dict[str, List[IE]] = {
    **NAS_MESSAGE_IE_SCHEMAS,
    **NGAP_MESSAGE_IE_SCHEMAS,
    **RRC_MESSAGE_IE_SCHEMAS,
    **F1AP_MESSAGE_IE_SCHEMAS,
    **E1AP_MESSAGE_IE_SCHEMAS,
    **XNAP_MESSAGE_IE_SCHEMAS,
}

ALL_TSHARK_FIELD_MAPS: Dict[str, Dict[str, str]] = {
    "NAS":  NAS_TSHARK_FIELD_MAP,
    "NGAP": NGAP_TSHARK_FIELD_MAP,
    "RRC":  RRC_TSHARK_FIELD_MAP,
    "F1AP": F1AP_TSHARK_FIELD_MAP,
    "E1AP": E1AP_TSHARK_FIELD_MAP,
    "XnAP": XNAP_TSHARK_FIELD_MAP,
}


def get_ie_schema(proc_name: str, role: str) -> List[IE]:
    """Return IE list for a given procedure + role, or [] if unknown."""
    key = f"{proc_name}_{role}"
    return ALL_MESSAGE_IE_SCHEMAS.get(key, [])


# ═════════════════════════════════════════════════════════════════════
# Message routing tables (msg_type byte → procedure name + role)
# Used by pcap_parser_real.py to dispatch incoming messages
# ═════════════════════════════════════════════════════════════════════

# ── NAS 5GMM message types (TS 24.501 Table 9.7.1) ───────────────────
# byte_value → (procedure_name, role)
NAS_5GMM_MSGS: Dict[int, tuple] = {
    # Registration (§8.2.6)
    0x41: ('NAS_Registration',           'request'),
    0x42: ('NAS_Registration',           'accept'),
    0x43: ('NAS_Registration',           'complete'),
    0x44: ('NAS_Registration',           'reject'),
    # Deregistration UE-initiated (§8.2.11)
    0x45: ('NAS_Deregistration',         'request'),
    0x46: ('NAS_Deregistration',         'accept'),
    # Deregistration Network-initiated
    0x47: ('NAS_Deregistration_Network', 'command'),
    0x48: ('NAS_Deregistration_Network', 'complete'),
    # Authentication (§8.2.1)
    0x56: ('NAS_Authentication',         'request'),
    0x57: ('NAS_Authentication',         'response'),
    0x58: ('NAS_Authentication',         'reject'),
    0x59: ('NAS_Authentication',         'failure'),
    # Security Mode (§8.2.25)
    0x5c: ('NAS_SecurityMode',           'command'),
    0x5d: ('NAS_SecurityMode',           'complete'),
    0x5e: ('NAS_SecurityMode',           'reject'),
    # Service Request (§8.2.14)
    0x64: ('NAS_ServiceRequest',         'request'),
    0x65: ('NAS_ServiceRequest',         'reject'),
    0x66: ('NAS_ServiceRequest',         'accept'),
    # Identity (§8.2.19)
    0x6b: ('NAS_Identity',               'request'),
    0x6c: ('NAS_Identity',               'response'),
    # Configuration Update (§8.2.10)
    0x68: ('NAS_ConfigUpdate',           'command'),
    0x69: ('NAS_ConfigUpdate',           'complete'),
}

# ── NAS 5GSM message types (TS 24.501 Table 9.7.2) ───────────────────
NAS_5GSM_MSGS: Dict[int, tuple] = {
    # PDU Session Establishment (§8.3.1)
    0xc1: ('NAS_PDUSession_Establishment', 'request'),
    0xc2: ('NAS_PDUSession_Establishment', 'accept'),
    0xc3: ('NAS_PDUSession_Establishment', 'reject'),
    # PDU Session Modification (§8.3.4)
    0xc9: ('NAS_PDUSession_Modification',  'command'),
    0xca: ('NAS_PDUSession_Modification',  'complete'),
    0xcb: ('NAS_PDUSession_Modification',  'reject'),
    0xcc: ('NAS_PDUSession_Modification',  'request'),
    # PDU Session Release (§8.3.7)
    0xd1: ('NAS_PDUSession_Release',       'command'),
    0xd2: ('NAS_PDUSession_Release',       'request'),
    0xd3: ('NAS_PDUSession_Release',       'reject'),
    0xd4: ('NAS_PDUSession_Release',       'complete'),
}

# ── NGAP procedure codes — synthetic PCAP simulation ─────────────────
NGAP_PROCS: Dict[int, str] = {
    0x01: 'NGAP_InitialContextSetup',
    0x02: 'NGAP_PDUSessionResourceSetup',
    0x03: 'NGAP_PDUSessionResourceRelease',
    0x04: 'NGAP_UEContextRelease',
    0x05: 'NGAP_HandoverPreparation',
    0x06: 'NGAP_NGSetup',
    0x07: 'NGAP_Paging',
    0x08: 'NGAP_UEContextModification',
    0x09: 'NGAP_PathSwitchRequest',
}

# ── NGAP procedure codes — real captures (TS 38.413 §9.2 Table 9.2.1-1) ──
REAL_NGAP_PROC_MAP: Dict[int, str] = {
    16: 'NGAP_InitialContextSetup',
    29: 'NGAP_PDUSessionResourceSetup',
    27: 'NGAP_PDUSessionResourceRelease',
    44: 'NGAP_UEContextRelease',
    14: 'NGAP_HandoverPreparation',
    23: 'NGAP_NGSetup',
    26: 'NGAP_Paging',
    43: 'NGAP_UEContextModification',
    28: 'NGAP_PathSwitchRequest',
}

# ── RRC procedure codes — synthetic PCAP simulation (TS 38.331) ───────
RRC_PROCS: Dict[int, str] = {
    0x01: 'RRC_Setup',
    0x02: 'RRC_Reestablishment',
    0x03: 'RRC_Reconfiguration',
    0x04: 'RRC_Release',
    0x05: 'RRC_SecurityMode',
    0x06: 'RRC_UECapabilityEnquiry',
}

# ── Cause code name maps ──────────────────────────────────────────────
NAS_CAUSE_NAMES: Dict[int, str] = {
    0x02: "imsi-unknown-in-hss",
    0x03: "illegal-ue",
    0x06: "illegal-me",
    0x07: "5gs-not-allowed",
    0x09: "ue-identity-not-derived",
    0x0a: "implicitly-detached",
    0x0b: "plmn-not-allowed",
    0x0c: "ta-not-allowed",
    0x0f: "no-suitable-cells",
    0x14: "mac-failure",
    0x15: "auth-failure",
    0x16: "congestion",
    0x1a: "semantically-incorrect-message",
    0x5f: "protocol-error",
}

NGAP_CAUSE_NAMES: Dict[int, str] = {
    0x01: "radio-network-unspecified",
    0x02: "rl-failure-rlc",
    0x03: "unknown-local-ue-ngap-id",
    0x04: "inconsistent-remote-ue-ngap-id",
    0x05: "handover-desirable-for-radio-reason",
    0x06: "time-critical-handover",
    0x07: "resource-optimisation-handover",
    0x08: "reduce-load-in-serving-cell",
    0x09: "user-inactivity",
    0x0a: "radio-connection-with-ue-lost",
    0x0b: "radio-resources-not-available",
    0x0c: "invalid-qos-combination",
    0x0d: "failure-in-radio-interface-procedure",
    0x0e: "interaction-with-other-procedure",
    0x0f: "unknown-pdu-session-id",
    0x10: "unknown-qos-flow-id",
    0x11: "multiple-pdu-session-id-instances",
    0x12: "multiple-qos-flow-id-instances",
    0x13: "encryption-integrity-keys-not-available",
}

RRC_CAUSE_NAMES: Dict[int, str] = {
    0x01: "other-failure",
    0x02: "handover-failure",
    0x03: "other-radio-link-failure",
    0x04: "rlf-report-available",
    0x05: "t310-expiry",
    0x06: "random-access-problem",
    0x07: "rlc-max-num-retx",
    0x08: "t312-expiry",
}
