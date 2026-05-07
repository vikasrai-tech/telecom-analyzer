"""
Synthetic PCAP Generator for Testing
=====================================

WHY SYNTHETIC DATA:
    Real 5G PCAPs are hard to get publicly — vendor captures are 
    confidential, public samples are rare. Synthetic data lets us:
    1. Control exactly which messages appear
    2. Know ground truth (exactly 5 successes, 2 failures)
    3. Test edge cases (timeout, missing response, etc.)
    4. Reproduce tests exactly — no dependency on external files

WHY SCAPY:
    Scapy is a Python packet manipulation library. It can:
    - Create any packet type from scratch
    - Write packets to PCAP files
    - Already installed in our telecom env (requirements.txt)
    
    Alternative was writing raw bytes — too complex and error-prone.

WHAT THIS SCRIPT CREATES:
    A small PCAP file with realistic 5G NAS Registration messages:
    - 3 successful registrations (Request → Accept)
    - 1 failed registration (Request → Reject with cause)
    - 1 timeout (Request with no response)
    
    Ground truth: attempts=5, success=3, failure=2
    Parser must produce exactly these numbers — if not, bug exists.

3GPP REFERENCE:
    NAS message types defined in TS 24.501 Table 9.7.1
    - 0x41 = Registration Request
    - 0x42 = Registration Accept  
    - 0x44 = Registration Reject
"""

from scapy.all import (
    Ether, IP, UDP, Raw,
    wrpcap, Packet
)
from pathlib import Path
import struct
import time

# WHY THESE CONSTANTS:
# NAS message types are defined by 3GPP in TS 24.501
# Using constants instead of magic numbers makes code self-documenting
NAS_REGISTRATION_REQUEST = 0x41  # TS 24.501 Section 8.2.6.1
NAS_REGISTRATION_ACCEPT  = 0x42  # TS 24.501 Section 8.2.6.2
NAS_REGISTRATION_REJECT  = 0x44  # TS 24.501 Section 8.2.6.4

# 5GMM cause codes (TS 24.501 Section 9.11.3.2)
CAUSE_CONGESTION          = 0x16  # Decimal 22
CAUSE_AUTH_FAILURE        = 0x15  # Decimal 21


def make_nas_packet(
    src_ip: str,
    dst_ip: str, 
    msg_type: int,
    tmsi: int,
    cause: int = None,
    timestamp: float = None
) -> Packet:
    """
    Create a single NAS message packet.
    
    WHY UDP PORT 38412:
        NGAP (which carries NAS) uses SCTP protocol in real networks.
        Scapy's SCTP support is limited for 5G messages.
        We use UDP port 38412 (NGAP's registered port) as a simplification.
        Our parser will look for NAS payload content, not transport protocol.
        This is standard practice in test environments.
    
    WHY RAW PAYLOAD:
        Full NAS message encoding is complex (ASN.1 + 3GPP specifics).
        For testing our procedure tracker, we only need:
        - Message type byte (what kind of message)
        - TMSI (which UE sent it — for correlation)
        - Cause code (why it failed — for failure analysis)
        Real pyshark will parse actual 5G captures; this tests our logic.
    
    ARGS:
        src_ip: Source IP (UE side)
        dst_ip: Destination IP (AMF side)
        msg_type: NAS message type byte (0x41, 0x42, 0x44)
        tmsi: 5G-S-TMSI — UE identifier for correlation
        cause: Failure cause code (only for Reject messages)
        timestamp: Packet timestamp (for ordering)
    """
    # Build minimal NAS payload:
    # Byte 0: Extended protocol discriminator (0x7e = 5GMM)
    # Byte 1: Security header (0x00 = plain NAS)
    # Byte 2: Message type (Registration Request/Accept/Reject)
    # Bytes 3-6: TMSI (4 bytes, big-endian)
    # Byte 7: Cause code (only present in Reject)
    
    # WHY BIG-ENDIAN (>I):
    # Network protocols use big-endian byte order by convention
    # struct.pack('>I', tmsi) = 4 bytes, most significant byte first
    # This matches how 3GPP encodes integer fields
    
    payload = bytes([
        0x7e,      # 5GMM protocol discriminator (TS 24.501 §9.2)
        0x00,      # Plain NAS message (no security)
        msg_type,  # Message type
    ])
    payload += struct.pack('>I', tmsi)  # TMSI as 4 bytes
    
    if cause is not None:
        payload += bytes([cause])
    
    # WHY ETHER/IP/UDP LAYERS:
    # PCAP files capture full network stack.
    # pyshark expects complete packet frames.
    # Without Ethernet + IP headers, pyshark cannot parse the file.
    pkt = (
        Ether() /          # Layer 2: Ethernet frame
        IP(src=src_ip,     # Layer 3: IP header
           dst=dst_ip) /
        UDP(sport=38412,   # Layer 4: UDP (simulating SCTP/NGAP port)
            dport=38412) /
        Raw(load=payload)  # Application layer: NAS payload
    )
    
    if timestamp:
        pkt.time = timestamp
    
    return pkt


def generate_test_pcap(output_path: str) -> None:
    """
    Generate a test PCAP with known ground truth.
    
    GROUND TRUTH (what parser MUST produce):
        NAS_Registration:
            attempts: 5
            success:  3  
            failure:  2  (1 reject + 1 timeout)
            failure_causes:
                congestion: 1
                timeout: 1
    
    WHY KNOWN GROUND TRUTH MATTERS:
        This is the basis of unit testing.
        We KNOW what the correct answer is.
        If parser gives different answer → parser has a bug.
        This is called "oracle-based testing" in software engineering.
    """
    packets = []
    base_time = time.time()
    
    # UE IP addresses (simulating different UEs)
    amf_ip = "10.0.0.1"   # AMF (core network side)
    
    print("Generating synthetic 5G NAS test PCAP...")
    print("Ground truth: 5 attempts, 3 success, 2 failure")
    print()
    
    # ── Scenario 1: UE-1 successful registration ──────────────────
    # TMSI 1001 sends request, gets accept
    print("Adding: UE-1 (TMSI=1001) → Registration Request")
    packets.append(make_nas_packet(
        src_ip="10.0.1.1", dst_ip=amf_ip,
        msg_type=NAS_REGISTRATION_REQUEST,
        tmsi=1001,
        timestamp=base_time + 0.1
    ))
    print("Adding: AMF → UE-1 (TMSI=1001) → Registration Accept ✓")
    packets.append(make_nas_packet(
        src_ip=amf_ip, dst_ip="10.0.1.1",
        msg_type=NAS_REGISTRATION_ACCEPT,
        tmsi=1001,
        timestamp=base_time + 0.3
    ))
    
    # ── Scenario 2: UE-2 successful registration ──────────────────
    print("Adding: UE-2 (TMSI=1002) → Registration Request")
    packets.append(make_nas_packet(
        src_ip="10.0.1.2", dst_ip=amf_ip,
        msg_type=NAS_REGISTRATION_REQUEST,
        tmsi=1002,
        timestamp=base_time + 1.0
    ))
    print("Adding: AMF → UE-2 (TMSI=1002) → Registration Accept ✓")
    packets.append(make_nas_packet(
        src_ip=amf_ip, dst_ip="10.0.1.2",
        msg_type=NAS_REGISTRATION_ACCEPT,
        tmsi=1002,
        timestamp=base_time + 1.2
    ))
    
    # ── Scenario 3: UE-3 REJECTED (congestion) ───────────────────
    # This tests failure counting and cause code extraction
    print("Adding: UE-3 (TMSI=1003) → Registration Request")
    packets.append(make_nas_packet(
        src_ip="10.0.1.3", dst_ip=amf_ip,
        msg_type=NAS_REGISTRATION_REQUEST,
        tmsi=1003,
        timestamp=base_time + 2.0
    ))
    print("Adding: AMF → UE-3 (TMSI=1003) → Registration REJECT (congestion) ✗")
    packets.append(make_nas_packet(
        src_ip=amf_ip, dst_ip="10.0.1.3",
        msg_type=NAS_REGISTRATION_REJECT,
        tmsi=1003,
        cause=CAUSE_CONGESTION,
        timestamp=base_time + 2.1
    ))
    
    # ── Scenario 4: UE-4 successful registration ──────────────────
    print("Adding: UE-4 (TMSI=1004) → Registration Request")
    packets.append(make_nas_packet(
        src_ip="10.0.1.4", dst_ip=amf_ip,
        msg_type=NAS_REGISTRATION_REQUEST,
        tmsi=1004,
        timestamp=base_time + 3.0
    ))
    print("Adding: AMF → UE-4 (TMSI=1004) → Registration Accept ✓")
    packets.append(make_nas_packet(
        src_ip=amf_ip, dst_ip="10.0.1.4",
        msg_type=NAS_REGISTRATION_ACCEPT,
        tmsi=1004,
        timestamp=base_time + 3.2
    ))
    
    # ── Scenario 5: UE-5 TIMEOUT (no response) ───────────────────
    # Request sent but AMF never responds
    # Parser must detect this as failure after timeout
    print("Adding: UE-5 (TMSI=1005) → Registration Request (no response — timeout)")
    packets.append(make_nas_packet(
        src_ip="10.0.1.5", dst_ip=amf_ip,
        msg_type=NAS_REGISTRATION_REQUEST,
        tmsi=1005,
        timestamp=base_time + 4.0
        # No corresponding Accept/Reject — simulates timeout
    ))
    
    # Write all packets to PCAP file
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    
    # WHY wrpcap:
    # scapy's wrpcap() writes packets to standard PCAP format
    # readable by Wireshark, tshark, pyshark — industry standard
    wrpcap(str(output), packets)
    
    print()
    print(f"✓ PCAP written to: {output}")
    print(f"  Total packets: {len(packets)}")
    print()
    print("Expected parser output:")
    print("  NAS_Registration:")
    print("    attempts: 5")
    print("    success:  3")
    print("    failure:  2")
    print("    failure_causes: {congestion: 1, timeout: 1}")


if __name__ == "__main__":
    generate_test_pcap("data/raw/test_nas_registration.pcap")
    print("\nNow run the parser on this file to verify it works correctly.")