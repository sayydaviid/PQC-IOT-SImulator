from scripts.continuity_capture import covered_attempt


def capture(tx=100, rx=130):
    return {"tcp_flows": {"one": dict(client_tcp_port=5, client_share_sha256="share",
        tx_contiguous_payload=tx, tx_unique_payload=tx, rx_contiguous_payload=rx, rx_unique_payload=rx)}}


def test_real_lost_ack_can_be_captured_but_not_delivered():
    client = dict(version="TLSv1.3", client_tcp_port=5, client_share_sha256="share",
                  acknowledged=False, tx_tls_bytes=124, rx_tls_bytes=90)
    server = dict(client_share_sha256="share", rx_tls_bytes=100, tx_tls_bytes=130)
    assert covered_attempt(capture(), client, [server])
    assert not covered_attempt(capture(tx=99), client, [server])
    assert not covered_attempt(capture(rx=89), client, [server])


def test_capture_holes_are_not_excused_by_network_failure():
    client = dict(version="TLSv1.3", client_tcp_port=5, client_share_sha256="share",
                  acknowledged=False, tx_tls_bytes=124, rx_tls_bytes=90)
    value = capture()
    value["tcp_flows"]["one"]["rx_contiguous_payload"] = 80
    assert not covered_attempt(value, client, [])


def test_acknowledged_reading_requires_server_handshake_evidence():
    client = dict(version="TLSv1.3", client_tcp_port=5, client_share_sha256="share",
                  acknowledged=True, tx_tls_bytes=100, rx_tls_bytes=130)
    assert not covered_attempt(capture(), client, [])
