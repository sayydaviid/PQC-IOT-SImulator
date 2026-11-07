"""Validate contiguous TCP prefixes, distinguishing data and closing alerts."""

import hashlib
import struct

from scripts.verify_recovery_network import pcap_counts


def client_share(data):
    """Hash the public key_share extension of the first TLS ClientHello."""
    if len(data) < 9 or data[0] != 22 or data[5] != 1:
        return None
    length = int.from_bytes(data[3:5], "big")
    if len(data) < 5 + length:
        return None
    message = data[5 : 5 + length]
    try:
        position = 4 + 2 + 32
        position += 1 + message[position]
        position += 2 + int.from_bytes(message[position : position + 2], "big")
        position += 1 + message[position]
        end = position + 2 + int.from_bytes(message[position : position + 2], "big")
        position += 2
        while position + 4 <= end:
            kind = int.from_bytes(message[position : position + 2], "big")
            size = int.from_bytes(message[position + 2 : position + 4], "big")
            position += 4
            if position + size > len(message):
                return None
            if kind == 51:
                return hashlib.sha256(message[position : position + size]).hexdigest()
            position += size
    except IndexError:
        return None
    return None


def tls_capture(path, client_ip):
    result = pcap_counts(path, client_ip)
    raw = path.read_bytes()
    order = "<" if raw[:4] == b"\xd4\xc3\xb2\xa1" else ">"
    client = bytes(map(int, client_ip.split(".")))
    flows = {}
    position = 24
    while position < len(raw):
        size = struct.unpack(order + "IIII", raw[position : position + 16])[2]
        position += 16
        packet = raw[position : position + size]
        position += size
        if len(packet) < 54 or packet[12:14] != b"\x08\x00":
            continue
        ip = packet[14:]
        if ip[9] != 6:
            continue
        tx = ip[12:16] == client
        if not tx and ip[16:20] != client:
            continue
        tcp = ip[(ip[0] & 15) * 4 :]
        header = (tcp[12] >> 4) * 4
        length = int.from_bytes(ip[2:4], "big") - (ip[0] & 15) * 4 - header
        port = str(int.from_bytes(tcp[:2] if tx else tcp[2:4], "big"))
        seq = int.from_bytes(tcp[4:8], "big")
        flags = tcp[13]
        if tx and flags & 2:
            key = port + ":" + str(seq)
            flows.setdefault(
                key,
                {
                    "client_tcp_port": int(port),
                    "client_initial_sequence": seq,
                    "tx_start": (seq + 1) % 2**32,
                    "tx_segments": [],
                    "rx_segments": [],
                },
            )
        if not tx and flags & 2:
            acknowledgement = int.from_bytes(tcp[8:12], "big")
            for flow in flows.values():
                if (
                    flow["client_tcp_port"] == int(port)
                    and flow["tx_start"] == acknowledgement
                ):
                    flow["rx_start"] = (seq + 1) % 2**32
        if length:
            direction = "tx" if tx else "rx"
            candidates = [
                ((seq - flow[direction + "_start"]) % 2**32, flow)
                for flow in flows.values()
                if flow["client_tcp_port"] == int(port)
                and direction + "_start" in flow
                and (seq - flow[direction + "_start"]) % 2**32 < 262144
            ]
            if not candidates:
                raise RuntimeError("capture missing initial sequence for TLS data")
            start, flow = min(candidates, key=lambda value: value[0])
            flow[direction + "_segments"].append(
                (start, bytes(tcp[header : header + length]))
            )
    for flow in flows.values():
        for direction in ("tx", "rx"):
            segments = sorted(
                flow.pop(direction + "_segments"), key=lambda value: value[0]
            )
            contiguous, unique, ceiling = 0, 0, 0
            raw_bytes = sum(len(data) for _, data in segments)
            preview = bytearray(8192)
            for start, data in segments:
                end = start + len(data)
                unique += max(0, end - max(start, ceiling))
                ceiling = max(ceiling, end)
                if start <= contiguous:
                    contiguous = max(contiguous, end)
                if direction == "tx" and start < len(preview):
                    preview[start : min(end, len(preview))] = data[
                        : len(preview) - start
                    ]
            flow[direction + "_payload"] = raw_bytes
            flow[direction + "_unique_payload"] = unique
            flow[direction + "_contiguous_payload"] = contiguous
            if direction == "tx":
                flow["client_share_sha256"] = client_share(
                    preview[: min(contiguous, len(preview))]
                )
        flow.pop("tx_start", None)
        flow.pop("rx_start", None)
    result["tcp_flows"] = flows
    return result


def covered(capture, row):
    matches = [
        flow
        for flow in capture["tcp_flows"].values()
        if flow.get("client_tcp_port") == row["client_tcp_port"]
        and (
            not row.get("client_share_sha256")
            or flow.get("client_share_sha256") == row["client_share_sha256"]
        )
        and (
            "client_initial_sequence" not in row
            or flow.get("client_initial_sequence") == row["client_initial_sequence"]
        )
    ]
    if len(matches) != 1:
        return False
    flow = matches[0]
    tx, rx = (
        flow.get("tx_contiguous_payload", -1),
        flow.get("rx_contiguous_payload", -1),
    )
    if tx != flow.get("tx_unique_payload") or rx != flow.get("rx_unique_payload"):
        return False  # An internal gap cannot be masked by an extra alert.
    if row["acknowledged"]:
        return tx == row["tx_tls_bytes"] and rx == row["rx_tls_bytes"]
    return (
        row["tx_data_tls_bytes"] <= tx <= row["tx_tls_bytes"]
        and rx == row["rx_tls_bytes"]
    )
