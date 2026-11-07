import struct

from pqc_iot_simulator.pqc_iot_sim.research.tls.capture import covered, tls_capture


def write_capture(path, segments):
    raw = bytearray(struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))
    client_ack = 0
    for tx, sequence, payload, flags in segments:
        if tx and flags & 2:
            client_ack = (sequence + 1) % 2**32
        source, destination = b"\x0a\x00\x00\x01", b"\x0a\x00\x00\x02"
        ports = (40001, 39900)
        if not tx:
            source, destination, ports = destination, source, ports[::-1]
        ip = struct.pack(
            "!BBHHHBBH4s4s",
            0x45,
            0,
            40 + len(payload),
            0,
            0,
            64,
            6,
            0,
            source,
            destination,
        )
        tcp = struct.pack(
            "!HHIIBBHHH",
            *ports,
            sequence,
            client_ack if not tx else 0,
            0x50,
            flags,
            65535,
            0,
            0,
        )
        packet = bytes(12) + b"\x08\x00" + ip + tcp + payload
        raw.extend(struct.pack("<IIII", 0, 0, len(packet), len(packet)))
        raw.extend(packet)
    path.write_bytes(raw)


def test_lost_closing_alert_after_verified_data_is_separate(tmp_path):
    path = tmp_path / "traffic.pcap"
    write_capture(
        path,
        [
            (True, 100, b"", 2),
            (False, 300, b"", 18),
            (True, 101, b"12345678", 24),
            (False, 301, b"123", 24),
        ],
    )
    capture = tls_capture(path, "10.0.0.1")
    row = {
        "client_tcp_port": 40001,
        "acknowledged": False,
        "tx_data_tls_bytes": 8,
        "tx_tls_bytes": 32,
        "rx_tls_bytes": 3,
    }
    assert covered(capture, row)
    row["acknowledged"] = True
    assert not covered(capture, row)


def test_extra_tail_cannot_mask_missing_internal_bytes(tmp_path):
    path = tmp_path / "traffic.pcap"
    write_capture(
        path,
        [
            (True, 100, b"", 2),
            (False, 300, b"", 18),
            (True, 101, b"1234", 24),
            (True, 109, b"extra-tail", 24),
            (False, 301, b"123", 24),
        ],
    )
    capture = tls_capture(path, "10.0.0.1")
    assert not covered(
        capture,
        {
            "client_tcp_port": 40001,
            "acknowledged": False,
            "tx_data_tls_bytes": 8,
            "tx_tls_bytes": 32,
            "rx_tls_bytes": 3,
        },
    )


def test_reused_port_starts_a_distinct_connection(tmp_path):
    path = tmp_path / "traffic.pcap"
    write_capture(
        path,
        [
            (True, 100, b"", 2),
            (False, 300, b"", 18),
            (True, 101, b"first", 24),
            (False, 301, b"old", 24),
            (True, 200, b"", 2),
            (False, 400, b"", 18),
            (True, 201, b"second", 24),
            (False, 401, b"new!", 24),
        ],
    )
    capture = tls_capture(path, "10.0.0.1")
    assert len(capture["tcp_flows"]) == 2
    for seq, tx, rx in ((100, 5, 3), (200, 6, 4)):
        assert covered(
            capture,
            {
                "client_tcp_port": 40001,
                "client_initial_sequence": seq,
                "acknowledged": True,
                "tx_tls_bytes": tx,
                "rx_tls_bytes": rx,
            },
        )
