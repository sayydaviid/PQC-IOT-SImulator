"""Executa um ciclo real para validar uma instalação Docker nova."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pqc_iot_simulator.pqc_iot_sim.core.simulation import Simulation


class InstallationValidation:
    """Executa um ciclo real para validar uma instalação Docker nova.

    Configure once, then call ``run()`` from a notebook.
    """

    def __init__(self, *, mode="classical"):
        self.mode = mode
        if self.mode not in ("classical", "pqc", "hybrid"):
            raise ValueError("invalid mode")

    def run(self):
        args = self
        "Executa o fluxo principal deste módulo."
        config_path = ROOT / "pqc_iot_simulator/pqc_iot_sim/configs/default.yaml"
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        pcap_dir = (
            ROOT
            / "results/raw/installation_smoke"
            / args.mode
            / f"{run_id}_{uuid4().hex[:8]}"
        )
        simulation = Simulation(config_path)
        simulation.config["network"]["crypto"]["mode"] = args.mode
        simulation.config["simulation"]["duration_seconds"] = 60
        simulation.config["simulation"]["pcap_directory"] = str(pcap_dir)
        simulation.config["simulation"]["capture_packets"] = True
        simulation.config["simulation"]["require_packet_capture"] = True
        result = simulation.run()
        association = simulation.engine.last_association_report
        expected_stations = sum(
            (
                node.node_type == "iot"
                for node in simulation.engine.engine_nodes.values()
            )
        )
        if association["failed"] or len(association["associated"]) != expected_stations:
            raise RuntimeError(f"Wi-Fi association incomplete: {association}")
        cycles = result["cycles"]
        if len(cycles) != 1 or not cycles[0]["delivered"]:
            raise RuntimeError(f"one delivered Mininet cycle expected, got {cycles}")
        capture = cycles[0]["pcap_capture"]
        pcap_path = Path(str(capture.get("pcap_path") or ""))
        if (
            not capture.get("capture_available")
            or capture.get("capture_namespace") != "destination_mininet_host"
            or capture.get("capture_interface") != "h1-eth0"
            or (int(capture.get("iot_tx_ip_bytes") or 0) <= 0)
            or (int(capture.get("iot_rx_ip_bytes") or 0) <= 0)
            or (not pcap_path.is_file())
        ):
            raise RuntimeError(f"Mininet packet capture invalid: {capture}")
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "crypto_mode": args.mode,
                    "stations_associated": len(association["associated"]),
                    "mininet_delivered": cycles[0]["delivered"],
                    "pcap_interface": capture["capture_interface"],
                    "pcap_iot_tx_ip_bytes": capture["iot_tx_ip_bytes"],
                    "pcap_iot_rx_ip_bytes": capture["iot_rx_ip_bytes"],
                    "pcap_path": str(pcap_path),
                },
                indent=2,
            )
        )
