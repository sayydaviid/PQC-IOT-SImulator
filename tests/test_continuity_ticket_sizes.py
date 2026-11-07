import pytest

from scripts.continuity_ticket_sizes import hello_lengths


def hello(ticket=None):
    u16 = lambda n:n.to_bytes(2, "big")
    extensions = u16(51)+u16(6)+b"shares"
    if ticket is not None:
        identity = u16(len(ticket))+ticket+b"\0"*4
        binders = bytes([48])+b"b"*48
        psk = u16(len(identity))+identity+u16(len(binders))+binders
        extensions += u16(41)+u16(len(psk))+psk
    body = b"\x03\x03"+b"r"*32+b"\0"+u16(2)+b"\x13\x02"+b"\x01\0"+u16(len(extensions))+extensions
    return b"\x01"+len(body).to_bytes(3,"big")+body


def test_counts_ticket_length_without_returning_ticket_contents():
    ticket = b"opaque-ticket-for-test"*200
    r = hello_lengths(hello(ticket))
    assert r["psk_identity_count"] == 1
    assert r["psk_identity_total_bytes"] == len(ticket)
    assert r["psk_extension_bytes"] == len(ticket)+63
    assert ticket.decode() not in str(r)


def test_no_psk_is_distinct_from_missing_or_truncated_message():
    assert hello_lengths(hello())["psk_identity_count"] == 0
    with pytest.raises(ValueError):
        hello_lengths(hello()[:-1])


def test_invalid_identity_vector_is_rejected():
    message = bytearray(hello(b"ticket"))
    offset = message.index(b"ticket")
    message[offset-2:offset] = b"\xff\xff"
    with pytest.raises(ValueError, match="truncated PSK identity"):
        hello_lengths(message)
