"""Post-hoc sizes of public ClientHello fields; never export ticket contents.

Reads the Ethernet/IPv4 PCAPs produced by this campaign. Lengths follow TLS 1.3
RFC 8446 sections 4.1.2 and 4.2.11. This is an explanatory analysis, not another
experimental condition or a decoder of encrypted tickets.
"""
import hashlib
import struct


def hello_lengths(message):
    if len(message) < 4 or message[0] != 1:
        raise ValueError("missing ClientHello")
    end = 4 + int.from_bytes(message[1:4], "big")
    if len(message) != end:
        raise ValueError("truncated ClientHello")

    def u16(p):
        if p + 2 > end:
            raise ValueError("truncated length")
        return int.from_bytes(message[p:p+2], "big")

    p = 4+2+32
    if p >= end:
        raise ValueError("truncated random")
    p += 1+message[p]
    p += 2+u16(p)
    if p >= end:
        raise ValueError("truncated cipher suites")
    p += 1+message[p]
    extensions_end = p+2+u16(p)
    p += 2
    if extensions_end != end:
        raise ValueError("invalid extension vector")
    result = dict(clienthello_handshake_bytes=end, psk_extension_bytes=0,
                  psk_identity_count=0, psk_identity_total_bytes=0,
                  psk_identity_max_bytes=0)
    seen = set()
    while p < end:
        kind, size = u16(p), u16(p+2)
        p += 4
        if p+size > end or kind in seen:
            raise ValueError("invalid or repeated extension")
        seen.add(kind)
        if kind == 51:
            result["client_share_sha256"] = hashlib.sha256(message[p:p+size]).hexdigest()
        if kind == 41:
            identity_end = p+2+u16(p)
            q, sizes = p+2, []
            if identity_end+2 > p+size:
                raise ValueError("invalid identity vector")
            while q < identity_end:
                length = u16(q)
                if not length or q+2+length+4 > identity_end:
                    raise ValueError("truncated PSK identity")
                sizes.append(length)
                q += 2+length+4
            if q != identity_end or identity_end+2+u16(identity_end) != p+size:
                raise ValueError("invalid PSK vectors")
            result.update(psk_extension_bytes=size+4, psk_identity_count=len(sizes),
                          psk_identity_total_bytes=sum(sizes), psk_identity_max_bytes=max(sizes, default=0))
        p += size
    return result


def capture_hellos(path, server_port=39911):
    """Reassemble client TCP prefixes by SYN sequence; duplicates count once."""
    raw = path.read_bytes()
    if raw[:4] not in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4"):
        raise ValueError("unsupported PCAP")
    order = "<" if raw[:4] == b"\xd4\xc3\xb2\xa1" else ">"
    if struct.unpack(order+"I", raw[20:24])[0] != 1:
        raise ValueError("requires Ethernet capture")
    flows, p = {}, 24
    while p < len(raw):
        if p+16 > len(raw):
            raise ValueError("truncated capture header")
        size = struct.unpack(order+"IIII", raw[p:p+16])[2]
        packet = raw[p+16:p+16+size]
        p += 16+size
        if len(packet) != size:
            raise ValueError("truncated captured packet")
        if len(packet) < 54 or packet[12:14] != b"\x08\x00":
            continue
        ip = packet[14:]
        if ip[9] != 6:
            continue
        tcp = ip[(ip[0]&15)*4:]
        if int.from_bytes(tcp[2:4], "big") != server_port:
            continue
        port, seq = int.from_bytes(tcp[:2], "big"), int.from_bytes(tcp[4:8], "big")
        if tcp[13]&2:
            flows.setdefault((port, (seq+1)%2**32), [])
        length = int.from_bytes(ip[2:4], "big")-(ip[0]&15)*4
        data = tcp[(tcp[12]>>4)*4:length]
        if not data:
            continue
        matches = [((seq-start)%2**32, key) for key in flows
                   for cp, start in (key,) if cp == port and (seq-start)%2**32 < 262144]
        if not matches:
            raise ValueError("client data without captured SYN")
        offset, key = min(matches)
        flows[key].append((offset, data))
    result = []
    for (port, _), segments in flows.items():
        prefix = bytearray()
        for offset, data in sorted(segments, key=lambda s:s[0]):
            if offset > len(prefix):
                break
            overlap = min(len(prefix)-offset, len(data))
            if prefix[offset:offset+overlap] != data[:overlap]:
                raise ValueError("conflicting TCP overlap")
            prefix.extend(data[overlap:])
        handshake, q = bytearray(), 0
        while q+5 <= len(prefix) and prefix[q] == 22:
            n = int.from_bytes(prefix[q+3:q+5], "big")
            if q+5+n > len(prefix):
                break
            handshake.extend(prefix[q+5:q+5+n])
            q += 5+n
            if len(handshake) >= 4 and len(handshake) >= 4+int.from_bytes(handshake[1:4], "big"):
                n = 4+int.from_bytes(handshake[1:4], "big")
                result.append(dict(client_tcp_port=port, **hello_lengths(handshake[:n])))
                break
    return result
