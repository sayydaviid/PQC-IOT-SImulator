import struct
import pytest
from pqc_iot_simulator.pqc_iot_sim.research.tls.context_capture import (
    capture_client_hellos,
)
from pqc_iot_simulator.pqc_iot_sim.research.tls.ticket_sizes import capture_hellos


def packet(source, destination, sequence, flags, payload=b""):
    tcp = (
        struct.pack("!HHIIBBHHH", 39911, 39911, sequence, 0, 5 << 4, flags, 65535, 0, 0)
        + payload
    )
    ip = struct.pack(
        "!BBHHHBBH4s4s",
        0x45,
        0,
        20 + len(tcp),
        0,
        0,
        64,
        6,
        0,
        bytes(source),
        bytes(destination),
    )
    frame = b"\0" * 12 + b"\x08\x00" + ip + tcp
    return struct.pack("<IIII", 0, 0, len(frame), len(frame)) + frame


def pcap(tmp_path, extra=b""):
    client, server = (10, 0, 0, 1), (10, 0, 0, 2)
    body = b"\x03\x03" + b"R" * 32 + b"\0" + b"\0\2\x13\2" + b"\1\0" + b"\0\0"
    hello = b"\1" + len(body).to_bytes(3, "big") + body

    def record(message):
        return b"\x16\x03\x03" + len(message).to_bytes(2, "big") + message

    raw = struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    raw += packet(client, server, 100, 2) + packet(server, client, 500, 0x12)
    raw += packet(client, server, 101, 0x18, record(hello))
    raw += packet(server, client, 501, 0x18, record(b"\2\0\0\0")) + extra
    path = tmp_path / "same_ports.pcap"
    path.write_bytes(raw)
    return path, hello


def test_equal_client_and_server_ports_do_not_reverse_the_tls_direction(tmp_path):
    path, hello = pcap(tmp_path)
    with pytest.raises(ValueError, match="missing ClientHello"):
        capture_hellos(path)
    result = capture_client_hellos(path)
    assert len(result) == 1
    assert result[0]["client_tcp_port"] == 39911
    assert result[0]["clienthello_handshake_bytes"] == len(hello)


def test_ambiguous_client_ips_are_rejected_instead_of_silently_filtered(tmp_path):
    path, _ = pcap(tmp_path, packet((10, 0, 0, 3), (10, 0, 0, 2), 700, 2))
    with pytest.raises(ValueError, match="exactly one client IP"):
        capture_client_hellos(path)
