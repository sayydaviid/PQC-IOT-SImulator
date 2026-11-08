"""Root-chain sensitivity in matched blocks; original campaign remains frozen."""

from __future__ import annotations
import hashlib, itertools, json, os, random, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
import pqc_iot_simulator.pqc_iot_sim.engines.tls_continuity as original
from pqc_iot_simulator.pqc_iot_sim.components.tls.credentials import provision
from pqc_iot_simulator.pqc_iot_sim.components.tls.design import PROFILES
from pqc_iot_simulator.pqc_iot_sim.components.tls.design import TREATMENTS
from pqc_iot_simulator.pqc_iot_sim.components.tls.design import schedule

PROBE = str(ROOT / "pqc_iot_simulator/pqc_iot_sim/engines/endpoints/session.py")
SOURCE_NAMES = [
    "Pesquisa_Retomada_Sessoes.ipynb",
    "pqc_iot_simulator/pqc_iot_sim/engines/native/context_costs/native.c",
    "pqc_iot_simulator/pqc_iot_sim/engines/endpoints/session.py",
    "docker/context_costs/Dockerfile",
    "docker/context_costs/compose.yml",
    "pqc_iot_simulator/pqc_iot_sim/engines/tls_chains.py",
    *original.SOURCES,
]


def hashes():
    return {
        f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in SOURCE_NAMES
    }


class EnvNode:
    def __init__(self, node, include_root):
        self.node, self.include_root = node, include_root

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


def assert_chains(case, include_root):
    expected = 2 if include_root else 1
    fulls = [r for r in case["clients"] if "version" in r and not r["reused"]]
    for r in fulls:
        if (
            len(r["wire_cert_tx_der_bytes"]) != expected
            or len(r["wire_cert_rx_der_bytes"]) != expected
        ):
            raise RuntimeError("client/server wire chain mismatch")
    for s in case["servers"]:
        if "version" in s and s["verified_peer_name"] != "iot_1":
            raise RuntimeError("client identity mismatch")


def topology(loss=0):
    from pqc_iot_simulator.pqc_iot_sim.components.network import Network
    from pqc_iot_simulator.pqc_iot_sim.engines.mininet_wifi_engine import (
        MininetWiFiEngine,
    )

    network = Network(verbose=False, log_level="silent")
    network.set_ready_topology("star", nodes=1)
    network.create_hosts()
    engine = MininetWiFiEngine(
        network,
        verbose=False,
        log_level="silent",
        default_delay="2ms",
        default_loss=0,
        association_wait_seconds=5,
    )
    try:
        engine.build()
        engine.start()
        if (
            engine.last_association_report["failed"]
            or len(engine.last_association_report["associated"]) != 1
        ):
            raise RuntimeError("association failed")
        sta, dst = engine.get_mininet_node("iot_1"), engine.get_mininet_node("server_1")
        intf = dst.defaultIntf()
        other = intf.link.intf1 if intf.link.intf2 is intf else intf.link.intf2
        details = []
        for endpoint in (intf, other):
            err = endpoint.node.cmd(
                f"tc qdisc replace dev {endpoint.name} root netem limit 1000 delay 2ms loss {loss}%"
            )
            if err.strip():
                raise RuntimeError(err)
            q = endpoint.node.cmd(f"tc -s qdisc show dev {endpoint.name}")
            if "netem" not in q or "delay 2ms" not in q:
                raise RuntimeError("qdisc not configured")
            details.append(q)
        return (
            engine,
            sta,
            dst,
            engine.get_ip("iot_1"),
            engine.get_ip("server_1"),
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

    def __init__(self, *, output, blocks=10, local_smoke=False, block_start=0):
        self.output = Path(output) if output is not None else None
        self.blocks = blocks
        if self.blocks < 1:
            raise ValueError("blocks must be positive")
        self.local_smoke = local_smoke
        self.block_start = block_start

    def run(self):
        args = self
        args.output.mkdir(parents=True, exist_ok=False)
        before = hashes()
        if (
            hashlib.sha256(
                Path("/opt/pqc-tls/context_costs/native.c").read_bytes()
            ).hexdigest()
            != before[
                "pqc_iot_simulator/pqc_iot_sim/engines/native/context_costs/native.c"
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
                    provision(cred, profile)
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
                        (engine, sta, dst, cip, sip, interface, qdiscs) = topology()
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
                        )
                        assert_chains(case, include_root)
                        case.update(
                            case_id=cid,
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
        if before != hashes():
            raise RuntimeError("sources changed during experiment")
        (args.output / "results.json").write_text(
            json.dumps({"status": "PASS", "cases": results}, indent=2)
        )
        print(json.dumps({"status": "PASS", "cases": len(results)}), flush=True)
        return args.output
