"""Select the client direction before applying the frozen public TLS parser."""

import struct
from .ticket_sizes import capture_hellos


class ClientPackets:
    def __init__(self, raw):
        self.raw = raw

    def read_bytes(self):
        return self.raw


def capture_client_hellos(path, server_port=39911):
    raw = path.read_bytes()
    if len(raw) < 24 or raw[:4] not in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4"):
        raise ValueError("unsupported PCAP")
    order = "<" if raw[:4] == b"\xd4\xc3\xb2\xa1" else ">"
    if struct.unpack(order + "I", raw[20:24])[0] != 1:
        raise ValueError("requires Ethernet capture")
    packets = []
    clients = set()
    offset = 24
    while offset < len(raw):
        if offset + 16 > len(raw):
            raise ValueError("truncated capture header")
        size = struct.unpack(order + "IIII", raw[offset : offset + 16])[2]
        end = offset + 16 + size
        if end > len(raw):
            raise ValueError("truncated captured packet")
        packet = raw[offset + 16 : end]
        if len(packet) >= 54 and packet[12:14] == b"\x08\x00":
            ip = packet[14:]
            ihl = (ip[0] & 15) * 4
            if ip[9] == 6 and ihl >= 20 and len(ip) >= ihl + 20:
                tcp = ip[ihl:]
                if int.from_bytes(tcp[2:4], "big") == server_port:
                    source = ip[12:16]
                    packets.append((source, raw[offset:end]))
                    # A SYN without ACK identifies the initiating endpoint even
                    # when the ephemeral port happens to equal the server port.
                    if tcp[13] & 0x12 == 0x02:
                        clients.add(source)
        offset = end
    if len(clients) != 1:
        raise ValueError("expected exactly one client IP from initial SYNs")
    client = next(iter(clients))
    selected = raw[:24] + b"".join(
        frame for source, frame in packets if source == client
    )
    return capture_hellos(ClientPackets(selected), server_port)
