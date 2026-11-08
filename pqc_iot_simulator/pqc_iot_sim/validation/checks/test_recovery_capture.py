"""Regression for incomplete captures and retransmissions inflating coverage."""

import struct

import pytest

from pqc_iot_simulator.pqc_iot_sim.validation.recovery_network import pcap_counts


def capture(path, segments):
    raw = bytearray(struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))
    for outgoing, sequence, payload in segments:
        source, destination = (b"\x0a\x00\x00\x01", b"\x0a\x00\x00\x02")
        ports = (40001, 39881)
        if not outgoing:
            source, destination = destination, source
            ports = ports[::-1]
        ip = struct.pack(
            "!BBHHHBBH4s4s",
            0x45,
            0,
            40 + len(payload),
            1,
            0,
            64,
            6,
            0,
            source,
            destination,
        )
        tcp = struct.pack("!HHIIBBHHH", *ports, sequence, 0, 0x50, 0x18, 65535, 0, 0)
        packet = bytes(12) + b"\x08\x00" + ip + tcp + payload
        raw.extend(struct.pack("<IIII", 0, 0, len(packet), len(packet)))
        raw.extend(packet)
    path.write_bytes(raw)


def test_overlapping_retransmissions_do_not_fill_missing_stream_bytes(tmp_path):
    path = tmp_path / "traffic.pcap"
    capture(
        path,
        [
            (True, 100, b"abcde"),
            (True, 103, b"defgh"),
            (True, 100, b"abcde"),
            (False, 300, b"ACK"),
        ],
    )
    result = pcap_counts(path, "10.0.0.1")
    flow = result["tcp_flows"]["40001"]
    assert flow["tx_payload"] == 15
    assert flow["tx_unique_payload"] == 8
    assert flow["rx_unique_payload"] == 3
    assert len(result["tcp_flows"]) == 1
    # An expected 10-byte application stream is incomplete despite 15 captured
    # bytes; the integration gate compares unique coverage, not that sum.
    assert flow["tx_unique_payload"] != 10


def test_truncated_capture_is_rejected(tmp_path):
    path = tmp_path / "traffic.pcap"
    capture(path, [(True, 100, b"one"), (False, 300, b"two")])
    path.write_bytes(path.read_bytes()[:-1])
    with pytest.raises(RuntimeError, match="truncated"):
        pcap_counts(path, "10.0.0.1")
