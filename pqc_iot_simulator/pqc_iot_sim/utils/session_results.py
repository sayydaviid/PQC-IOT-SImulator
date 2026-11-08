"""Audit actual emitted chains, tickets, schedules, captures and durable effects."""

import hashlib, itertools, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
from ..crypto.tls.design import PROFILES
from ..crypto.tls.design import TREATMENTS
from ..crypto.tls.design import check_tls
from ..crypto.tls.design import schedule
from ..crypto.tls.context_capture import capture_client_hellos


class SessionResultsAudit:
    """Audit actual emitted chains, tickets, schedules, captures and durable effects.

    Configure once, then call ``run()`` from a notebook.
    """

    def __init__(self, *, input, kind, output):
        self.input = Path(input) if input is not None else None
        self.kind = kind
        if self.kind not in ["chains", "amortization"]:
            raise ValueError("invalid kind")
        self.output = Path(output) if output is not None else None

    def run(self):
        args = self
        manifest = json.loads((args.input / "manifest.json").read_text())
        data = json.loads((args.input / "results.json").read_text())
        assert (
            data["status"] == "PASS"
            and (not manifest.get("smoke"))
            and (not manifest.get("local_smoke"))
        )
        assert len(data["cases"]) == manifest["planned_cases"]
        for file, value in manifest["source_sha256"].items():
            assert hashlib.sha256((ROOT / file).read_bytes()).hexdigest() == value, file
        blocks = range(
            manifest.get("block_start", 0),
            manifest.get("block_start", 0) + manifest["blocks"],
        )
        if args.kind == "chains":
            expected = set(
                itertools.product(blocks, [0, 0.25, 1], PROFILES, TREATMENTS, [0, 1])
            )
            actual = {
                (
                    c["block"],
                    c["restart_fraction"],
                    c["profile"],
                    c["treatment"],
                    c["include_root"],
                )
                for c in data["cases"]
            }
        else:
            expected = set(
                itertools.product(
                    blocks, PROFILES, TREATMENTS, [1, 10, 100], [False, True]
                )
            )
            actual = {
                (
                    c["block"],
                    c["profile"],
                    c["treatment"],
                    c["batch_size"],
                    c["recovery"],
                )
                for c in data["cases"]
            }
        assert expected == actual and len(actual) == len(data["cases"])
        captures = {}
        hellos_count = 0
        tickets_count = 0
        confirmed = 0
        shares = {
            field: set() for field in ["client_share_sha256", "server_share_sha256"]
        }
        workloads = {}
        digests = {}
        for c in data["cases"]:
            case = args.input / c["case_id"]
            assert json.loads((case / "case.json").read_text()) == c
            assert "0 packets dropped by kernel" in (case / "tcpdump.log").read_text()
            trace = case / "traffic.pcap"
            captures[c["case_id"]] = hashlib.sha256(trace.read_bytes()).hexdigest()
            assert captures[c["case_id"]] == c["capture"]["pcap_sha256"]
            public = capture_client_hellos(trace)
            hellos_count += len(public)
            assert len(public) == len(c["clients"])
            certificates = json.loads(
                (args.input / f"certificates_block{c['block']}.json").read_text()
            )[c["profile"]]
            for client in c["clients"]:
                if "version" not in client:
                    continue
                check_tls(client, c["profile"])
                for field, seen in shares.items():
                    assert client[field] not in seen, (
                        "repeated public key share",
                        field,
                        c["case_id"],
                    )
                    seen.add(client[field])
                hello = [
                    h
                    for h in public
                    if h.get("client_share_sha256") == client["client_share_sha256"]
                ]
                assert len(hello) == 1
                assert (
                    hello[0]["clienthello_handshake_bytes"]
                    == client["clienthello_handshake_bytes"]
                )
                assert (
                    hello[0]["psk_identity_max_bytes"] == client["psk_identity_bytes"]
                )
                if not client["reused"]:
                    expected_tx = [certificates["client"]["der_bytes"]]
                    expected_rx = [certificates["server"]["der_bytes"]]
                    if c["include_root"]:
                        expected_tx.append(certificates["ca"]["der_bytes"])
                        expected_rx.append(certificates["ca"]["der_bytes"])
                    assert client["wire_cert_tx_der_bytes"] == expected_tx
                    assert client["wire_cert_rx_der_bytes"] == expected_rx
            for server in c["servers"]:
                if "version" not in server:
                    continue
                assert (
                    server["verify_result"] == 0
                    and server["dedup_device"] == "iot_1"
                    and (server["verified_peer_name"] == "iot_1")
                )
                for ticket in server["tickets_tx_bytes"]:
                    tickets_count += 1
                    assert ticket == 64 + 16 * (
                        server["ticket_plaintext_session_der_bytes"] // 16 + 1
                    )
                    assert (
                        server["ticket_peer_certificate_der_bytes"]
                        == certificates["client"]["der_bytes"]
                    )
                    assert server["ticket_application_data_bytes"] == 0
            received = (
                [s for s in c["servers"] if s.get("reading_received")]
                if args.kind == "chains"
                else [
                    reading
                    for server in c["servers"]
                    for reading in server.get("readings", [])
                ]
            )
            logical = {r["reading_id"]: r["sha256"] for r in received}
            for identity, digest in logical.items():
                key = (c["block"], identity)
                assert digests.setdefault(key, digest) == digest, (
                    "unmatched payload",
                    c["case_id"],
                )
            if c["delivery_status"] == "complete":
                assert len(logical) == c["readings"]
                assert workloads.setdefault(c["block"], logical) == logical, (
                    "unmatched workload",
                    c["case_id"],
                )
            if args.kind == "chains":
                assert c["fault_schedule"] == schedule(
                    9, c["restart_fraction"], c["ack_fraction"], c["block"]
                )
            else:
                assert c["readings"] == 100 and c["payload_bytes"] == 512
            assert c["duplicate_effects"] == 0
            confirmed += c["confirmed_readings"]
        out = {
            "status": "PASS",
            "kind": args.kind,
            "cases": len(data["cases"]),
            "confirmed_readings": confirmed,
            "clienthellos_verified_against_capture": hellos_count,
            "emitted_ticket_lengths_verified": tickets_count,
            "checks": [
                "exact complete matched design",
                "source hashes unchanged",
                "case files match aggregate",
                "zero kernel capture drops",
                "PCAP and native ClientHello lengths match",
                "both wire chains match their public certificates",
                "ticket lengths match observed serialized state plus CBC padding/name/IV/MAC",
                "server ticket peer certificate matches client leaf",
                "no ticket application data",
                "authenticated dedup device",
                "no duplicate effects",
                "fresh public key shares across all observed connections; traffic secrets not exported",
                "matched reading identifiers and content digests within each block",
            ],
            "pcap_sha256": captures,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(out, indent=2))
        print(
            json.dumps({k: v for (k, v) in out.items() if k != "pcap_sha256"}, indent=2)
        )
        return args.output
