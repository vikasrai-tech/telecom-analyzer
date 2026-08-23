"""
IE Extractor — extracts Information Elements from pyshark layer objects.

For real 5G captures, pyshark/tshark dissects all protocol layers.
This module maps tshark field names → human-readable IE names and
builds a structured dict for each message.

Strategy:
  1. Try every known tshark field name from the protocol's field map.
  2. Fall back to iterating layer.field_names for anything not in the map.
  3. Return {} if the layer has no fields (synthetic PCAP raw payload).
"""

from typing import Dict, Any, List
from .protocol_defs import ALL_TSHARK_FIELD_MAPS, get_ie_schema


def _try_field(layer, field_name: str) -> str:
    """Safely get one field value from a pyshark layer. Returns '' on failure."""
    try:
        val = getattr(layer, field_name, None)
        if val is not None:
            s = str(val).strip()
            if s:
                return s
    except Exception:
        pass
    return ""


def _extract_all_fields(layer, field_map: Dict[str, str]) -> Dict[str, str]:
    """
    Step 1: extract all fields in our known field_map.
    Step 2: iterate layer.field_names for anything remaining.
    """
    ies: Dict[str, str] = {}

    # Step 1 — known fields
    for tshark_name, readable in field_map.items():
        val = _try_field(layer, tshark_name)
        if val:
            ies[readable] = val
        # Also try replacing '.' with '_' — tshark attribute access uses underscores
        alt = tshark_name.replace('.', '_')
        if alt != tshark_name:
            val2 = _try_field(layer, alt)
            if val2 and readable not in ies:
                ies[readable] = val2

    # Step 2 — sweep remaining field_names not already captured
    captured_readable = set(ies.keys())
    if hasattr(layer, 'field_names'):
        for fname in layer.field_names:
            readable = field_map.get(fname, "")
            if readable in captured_readable:
                continue  # already have it
            val = _try_field(layer, fname)
            if val:
                # Use field map if available, otherwise prettify the raw name
                label = readable or fname.split('.')[-1].replace('_', ' ').title()
                ies[label] = val

    return ies


def extract_nas_ies(packet) -> Dict[str, str]:
    """Extract NAS IEs from a pyshark nas_5gs layer."""
    try:
        return _extract_all_fields(packet.nas_5gs, ALL_TSHARK_FIELD_MAPS["NAS"])
    except Exception:
        return {}


def extract_ngap_ies(packet) -> Dict[str, str]:
    """Extract NGAP IEs from a pyshark ngap layer."""
    try:
        return _extract_all_fields(packet.ngap, ALL_TSHARK_FIELD_MAPS["NGAP"])
    except Exception:
        return {}


def extract_rrc_ies(packet) -> Dict[str, str]:
    """Extract RRC IEs from a pyshark nr_rrc layer."""
    try:
        return _extract_all_fields(packet.nr_rrc, ALL_TSHARK_FIELD_MAPS["RRC"])
    except Exception:
        return {}


def extract_f1ap_ies(packet) -> Dict[str, str]:
    """Extract F1AP IEs from a pyshark f1ap layer."""
    try:
        return _extract_all_fields(packet.f1ap, ALL_TSHARK_FIELD_MAPS["F1AP"])
    except Exception:
        return {}


def extract_e1ap_ies(packet) -> Dict[str, str]:
    """Extract E1AP IEs from a pyshark e1ap layer."""
    try:
        return _extract_all_fields(packet.e1ap, ALL_TSHARK_FIELD_MAPS["E1AP"])
    except Exception:
        return {}


def extract_xnap_ies(packet) -> Dict[str, str]:
    """Extract XnAP IEs from a pyshark xnap layer."""
    try:
        return _extract_all_fields(packet.xnap, ALL_TSHARK_FIELD_MAPS["XnAP"])
    except Exception:
        return {}


def get_expected_ies(proc_name: str, role: str) -> List[Dict]:
    """
    Return the IE schema (expected IEs) for a given procedure + role.
    Useful for the dashboard to show which IEs are defined vs. observed.
    """
    return get_ie_schema(proc_name, role)


def build_message_event(layer: str, proc_name: str, role: str,
                        ue_id: str, timestamp: float,
                        observed_ies: Dict[str, str]) -> Dict[str, Any]:
    """Build a structured message event for the message log."""
    expected = get_expected_ies(proc_name, role)
    mandatory_missing = [
        ie["name"] for ie in expected
        if ie["presence"] == "Mandatory" and ie["name"] not in observed_ies
    ]
    return {
        "timestamp": timestamp,
        "layer": layer,
        "procedure": proc_name,
        "message_type": f"{proc_name}_{role}",
        "role": role,
        "ue_id": ue_id,
        "ies": observed_ies,
        "expected_ie_count": len(expected),
        "observed_ie_count": len(observed_ies),
        "mandatory_missing": mandatory_missing,
    }
