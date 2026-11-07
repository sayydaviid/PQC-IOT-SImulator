"""Capture bounds distinguish delivered TLS bytes from attempted transmissions."""


def covered_attempt(capture, client, servers):
    """A real lost ACK may be visible at the server but absent at the client.

    Use each receiver's byte count as lower bound, sender's count as upper
    bound. This does not hide capture holes or count missing data as received.
    Failed handshakes without native metadata are retained separately.
    """
    if "version" not in client:
        return True
    matches = [f for f in capture["tcp_flows"].values()
               if f["client_tcp_port"] == client["client_tcp_port"]
               and f.get("client_share_sha256") == client["client_share_sha256"]]
    if len(matches) != 1:
        return False
    f = matches[0]
    peers = [s for s in servers if s.get("client_share_sha256") == client["client_share_sha256"]]
    if len(peers) > 1:
        return False
    server = peers[0] if peers else {}
    if client["acknowledged"] and not server:
        return False
    # A record-header callback counts the announced record length even if its
    # body is never completely delivered. Lower bounds therefore use completed
    # handshake/application milestones, not a failed read's final header count.
    tx_floor = server.get("handshake_rx_tls_bytes", server.get("rx_tls_bytes", 0))
    if server.get("reading_received"):
        tx_floor = max(tx_floor, client.get("tx_data_tls_bytes", 0))
    rx_floor = client.get("handshake_rx_tls_bytes", client["rx_tls_bytes"])
    if client["acknowledged"]:
        rx_floor = client.get("rx_confirmed_tls_bytes", client["rx_tls_bytes"])
    # Failed transport can leave later bytes beyond an actual TCP hole. Retain
    # that outcome, but never excuse a hole before bytes known to be delivered.
    return (tx_floor <= f["tx_contiguous_payload"]
            and f["tx_unique_payload"] <= client["tx_tls_bytes"]
            and rx_floor <= f["rx_contiguous_payload"]
            and f["rx_unique_payload"] <= server.get("tx_tls_bytes", f["rx_unique_payload"]))
