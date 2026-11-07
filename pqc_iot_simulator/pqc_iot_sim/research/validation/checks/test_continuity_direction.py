"""The continuity analysis must use the client-IP-aware capture reader."""

from pqc_iot_simulator.pqc_iot_sim.research.analysis.continuity import capture_hellos
from pqc_iot_simulator.pqc_iot_sim.research.validation.checks.test_context_capture import (
    pcap,
)


def test_analysis_handles_equal_client_and_server_ports(tmp_path):
    path, hello = pcap(tmp_path)
    rows = capture_hellos(path)
    assert len(rows) == 1
    assert rows[0]["clienthello_handshake_bytes"] == len(hello)
