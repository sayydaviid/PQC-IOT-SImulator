"""Root-chain sensitivity in matched blocks; original campaign remains frozen."""

from __future__ import annotations
from ..metadata import RunMetadata
import hashlib, itertools, json, os, random, subprocess, tempfile
from copy import deepcopy
import math
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
import pqc_iot_simulator.pqc_iot_sim.runtime.tls_continuity as original
from ..crypto.tls.credentials import provision
from ..crypto.tls.design import PROFILES
from ..crypto.tls.design import TREATMENTS
from ..crypto.tls.design import schedule

PROBE = str(ROOT / "pqc_iot_simulator/pqc_iot_sim/runtime/endpoints/session.py")


class EnvNode:
    def __init__(self, node, include_root):
        (self.node, self.include_root) = (node, include_root)

    def popen(self, *a, **kw):
        env = dict(os.environ)
        env["CONTEXT_CHAIN_ROOT"] = str(self.include_root)
        kw["env"] = env
        return self.node.popen(*a, **kw)


def certificate_sizes(directory):
    out = {}
    for name in ["ca", "client", "server"]:
        der = subprocess.check_output(
            [
                "/opt/pqc-tls/bin/openssl",
                "x509",
                "-in",
                str(directory / (name + ".crt")),
                "-outform",
                "DER",
            ]
        )
        out[name] = {"der_bytes": len(der), "sha256": hashlib.sha256(der).hexdigest()}
    return out


def assert_chains(case, include_root, device_id="iot_1"):
    expected = 2 if include_root else 1
    fulls = [r for r in case["clients"] if "version" in r and (not r["reused"])]
    for r in fulls:
        if (
            len(r["wire_cert_tx_der_bytes"]) != expected
            or len(r["wire_cert_rx_der_bytes"]) != expected
        ):
            raise RuntimeError("client/server wire chain mismatch")
    for s in case["servers"]:
        if "version" in s and s["verified_peer_name"] != device_id:
            raise RuntimeError("client identity mismatch")


def topology(loss=0, network=None, source="iot_1", destination="server_1", delay_ms=2):
    from ..topology.network import Network
    from .mininet_wifi_engine import MininetWiFiEngine

    for value, maximum in ((loss, 100), (delay_ms, None)):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
            or (maximum is not None and value > maximum)
        ):
            raise ValueError("perda ou atraso de rede inválido")
    template = network
    network = Network(verbose=False, log_level="silent")
    if template is None:
        network.set_ready_topology("star", nodes=1)
    else:
        network.config = deepcopy(template.config)
        network.topology_data = deepcopy(template.topology_data)
        network._sync_graph()
    if (
        source not in network.topology_data.nodes
        or destination not in network.topology_data.nodes
    ):
        raise ValueError("origem ou destino não existe na topologia")
    if not source.startswith("iot_") or not destination.startswith("server_"):
        raise ValueError("selecione um sensor e um servidor TLS")
    network.create_hosts()
    delay = f"{delay_ms:g}ms"
    expected_stations = sum(n.startswith("iot_") for n in network.topology_data.nodes)
    engine = MininetWiFiEngine(
        network,
        verbose=False,
        log_level="silent",
        default_delay=delay,
        default_loss=0,
        association_wait_seconds=5,
    )
    try:
        engine.build()
        engine.start()
        if (
            engine.last_association_report["failed"]
            or len(engine.last_association_report["associated"]) != expected_stations
        ):
            raise RuntimeError("association failed")
        (sta, dst) = (
            engine.get_mininet_node(source),
            engine.get_mininet_node(destination),
        )
        intf = dst.defaultIntf()
        other = intf.link.intf1 if intf.link.intf2 is intf else intf.link.intf2
        details = []
        for endpoint in (intf, other):
            err = endpoint.node.cmd(
                f"tc qdisc replace dev {endpoint.name} root netem limit 1000 delay {delay} loss {loss}%"
            )
            if err.strip():
                raise RuntimeError(err)
            q = endpoint.node.cmd(f"tc -s qdisc show dev {endpoint.name}")
            match = re.search(r"delay ([0-9.]+)(us|ms|s)", q)
            observed_delay = (
                float(match[1]) * {"us": 0.001, "ms": 1, "s": 1000}[match[2]]
                if match
                else 0
            )
            if "netem" not in q or not math.isclose(
                observed_delay, delay_ms, abs_tol=0.001
            ):
                raise RuntimeError("qdisc not configured")
            details.append(q)
        return (
            engine,
            sta,
            dst,
            engine.get_ip(source),
            engine.get_ip(destination),
            intf.name,
            details,
        )
    except BaseException:
        engine.stop()
        raise


class CertificateChainEngine:
    """Root-chain sensitivity in matched blocks; original campaign remains frozen.

    Configure once, then call ``run()`` from a notebook.
    """

    def __init__(
        self,
        *,
        output,
        blocks=10,
        local_smoke=False,
        block_start=0,
        network=None,
        source="iot_1",
        destination="server_1",
    ):
        self.output = Path(output) if output is not None else None
        self.blocks = blocks
        if (
            isinstance(self.blocks, bool)
            or not isinstance(self.blocks, int)
            or self.blocks < 1
        ):
            raise ValueError("blocks must be positive")
        self.local_smoke = local_smoke
        self.block_start = block_start
        self.network = network
        self.source = source
        self.destination = destination

    def run(self):
        args = self
        args.output.mkdir(parents=True, exist_ok=False)
        before = RunMetadata.source_hashes()
        if (
            hashlib.sha256(
                Path("/opt/pqc-tls/context_costs/native.c").read_bytes()
            ).hexdigest()
            != before[
                "pqc_iot_simulator/pqc_iot_sim/runtime/native/context_costs/native.c"
            ]
        ):
            raise RuntimeError("native runtime differs from diagnostic sources")
        matrix = list(itertools.product((0, 0.25, 1), PROFILES, TREATMENTS, (0, 1)))
        manifest = {
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "source_sha256": before,
            "environment": {
                **original.environment(),
                "context_module_sha256": hashlib.sha256(
                    Path(__import__("_context_tls").__file__).read_bytes()
                ).hexdigest(),
            },
            "source": args.source,
            "destination": args.destination,
            "blocks": args.blocks,
            "block_start": args.block_start,
            "planned_cases": args.blocks * len(matrix),
            "scenarios": [[0, 0], [0.25, 0.25], [1, 1]],
            "readings": 9,
            "deduplicate": True,
            "packet_loss_pct": 0,
            "wire_chain": "both endpoints: leaf only versus leaf plus trusted root; same trust store and credentials within block",
            "measurement": "all server-observed IPv4 attempts and closures; time through last ACK; matched block contrasts",
            "local_smoke": args.local_smoke,
        }
        (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2))
        results = []
        with tempfile.TemporaryDirectory(prefix="context-costs-private-") as tmp:
            private = Path(tmp)
            for block in range(args.block_start, args.block_start + args.blocks):
                credentials = {}
                for profile in PROFILES:
                    cred = private / f"b{block}_{profile}"
                    provision(cred, profile, device_id=args.source)
                    credentials[profile] = cred
                (args.output / f"certificates_block{block}.json").write_text(
                    json.dumps(
                        {p: certificate_sizes(d) for (p, d) in credentials.items()},
                        indent=2,
                    )
                )
                engine = None
                try:
                    if args.local_smoke:
                        sta = dst = original.LocalNode()
                        cip = sip = "127.0.0.1"
                        interface = "lo"
                        qdiscs = []
                    else:
                        (engine, sta, dst, cip, sip, interface, qdiscs) = topology(
                            network=args.network,
                            source=args.source,
                            destination=args.destination,
                        )
                    (args.output / f"network_block{block}.json").write_text(
                        json.dumps(qdiscs)
                    )
                    order = matrix[:]
                    random.Random(20261106 + block).shuffle(order)
                    for fraction, profile, treatment, include_root in order:
                        cid = f"b{block}_r{fraction:g}_a{fraction:g}_{profile}_{treatment}_root{include_root}"
                        case = original.execute_case(
                            EnvNode(sta, include_root),
                            EnvNode(dst, include_root),
                            cip,
                            sip,
                            interface,
                            args.output / cid,
                            private / cid,
                            credentials[profile],
                            profile,
                            treatment,
                            True,
                            schedule(9, fraction, fraction, block),
                            9,
                            block,
                            capture_enabled=not args.local_smoke,
                            probe=PROBE,
                            device_id=args.source,
                        )
                        assert_chains(case, include_root, args.source)
                        case.update(
                            case_id=cid,
                            source=args.source,
                            destination=args.destination,
                            include_root=include_root,
                            restart_fraction=fraction,
                            ack_fraction=fraction,
                            loss_pct=0,
                            payload_bytes=len(
                                f"synthetic block={block:03} reading={0:03}".encode()
                            ),
                        )
                        (args.output / cid / "case.json").write_text(
                            json.dumps(case, indent=2)
                        )
                        results.append(case)
                        with (args.output / "progress.jsonl").open("a") as f:
                            f.write(
                                json.dumps({"completed": len(results), "case": cid})
                                + "\n"
                            )
                        print(
                            json.dumps(
                                {
                                    "completed": len(results),
                                    "planned": manifest["planned_cases"],
                                    "case": cid,
                                }
                            ),
                            flush=True,
                        )
                finally:
                    if engine:
                        engine.stop()
        if before != RunMetadata.source_hashes():
            raise RuntimeError("sources changed during experiment")
        (args.output / "results.json").write_text(
            json.dumps({"status": "PASS", "cases": results}, indent=2)
        )
        print(json.dumps({"status": "PASS", "cases": len(results)}), flush=True)
        return args.output
