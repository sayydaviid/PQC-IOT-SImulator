"""Stop the actual TLS gateway at SQLite boundaries and retry after restart."""

from __future__ import annotations
import argparse, importlib.util, json, os, signal, sqlite3, subprocess, sys, tempfile, time, hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
from pqc_iot_simulator.pqc_iot_sim.crypto.tls.credentials import provision
from pqc_iot_simulator.pqc_iot_sim.crypto.tls.design import PROFILES
from pqc_iot_simulator.pqc_iot_sim.crypto.tls.design import check_tls

PROBE = ROOT / "pqc_iot_simulator/pqc_iot_sim/runtime/endpoints/session.py"


class GracefulStop(BaseException):
    pass


def worker(config):
    conf = json.loads(config.read_text())
    directory = Path(conf["private"])
    spec = importlib.util.spec_from_file_location("_frontier_tls", PROBE)
    endpoint = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = endpoint
    spec.loader.exec_module(endpoint)
    base = endpoint.ReadingLedger

    def barrier():
        (directory / "barrier").write_text(conf["boundary"])
        while True:
            time.sleep(0.01)

    class InstrumentedLedger(base):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            real = self.connection
            boundary = conf["boundary"]

            class Proxy:
                def execute(self, sql, *params):
                    if boundary == "before_commit" and sql == "COMMIT":
                        barrier()
                    result = real.execute(sql, *params)
                    if (
                        (
                            boundary == "after_reading_insert"
                            and sql.startswith("INSERT INTO readings")
                        )
                        or (
                            boundary == "after_effect_insert"
                            and sql.startswith("INSERT INTO effects")
                        )
                        or (boundary == "after_commit" and sql == "COMMIT")
                    ):
                        barrier()
                    return result

                def close(self):
                    return real.close()

            self.connection = Proxy()

        def ingest(self, *a, **kw):
            result = super().ingest(*a, **kw)
            if conf["boundary"] == "before_ack":
                barrier()
            return result

    endpoint.ReadingLedger = InstrumentedLedger

    def graceful(*unused):
        raise GracefulStop()

    signal.signal(signal.SIGTERM, graceful)
    ns = argparse.Namespace(
        credentials=conf["credentials"],
        profile=conf["profile"],
        ticket_key=None,
        ledger=str(directory / "db"),
        deduplicate=True,
        host="127.0.0.1",
        port=39922,
        stop_file=None,
        connections=1,
        drop_reading_id=[],
        drop_ack=[],
        ready=str(directory / "ready"),
        output=str(directory / "server.json"),
    )
    try:
        endpoint.server(ns)
    except GracefulStop:
        pass


def ready(process, path):
    deadline = time.monotonic() + 20
    while not path.exists():
        if process.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError("gateway did not reach expected boundary")
        time.sleep(0.005)


def client_command(directory, credentials, profile, output):
    return [
        sys.executable,
        str(PROBE),
        "client",
        "--host",
        "127.0.0.1",
        "--port",
        "39922",
        "--credentials",
        str(credentials),
        "--profile",
        profile,
        "--mode",
        "full",
        "--state",
        str(directory / "state"),
        "--payload",
        str(directory / "payload"),
        "--reading-id",
        "0123456789abcdef0123456789abcdef",
        "--output",
        str(output),
    ]


class TLSPersistenceScenarios:
    """Stop the actual TLS gateway at SQLite boundaries and retry after restart.

    Configure once, then call ``run()`` from a notebook.
    """

    def __init__(self, *, output):
        self.output = Path(output) if output is not None else None
        self.worker = None

    def run(self):
        args = self
        if args.worker:
            return worker(args.worker)
        args.output.mkdir(parents=True, exist_ok=False)
        rows = []
        env = dict(os.environ, CONTEXT_CHAIN_ROOT="0")
        with tempfile.TemporaryDirectory(prefix="tls-frontiers-private-") as tmp:
            private = Path(tmp)
            for profile in PROFILES:
                credentials = private / profile
                provision(credentials, profile)
                for boundary in [
                    "after_reading_insert",
                    "after_effect_insert",
                    "before_commit",
                    "after_commit",
                    "before_ack",
                ]:
                    for termination in ["sigterm_cleanup", "sigkill"]:
                        directory = private / f"{profile}_{boundary}_{termination}"
                        directory.mkdir()
                        (directory / "payload").write_bytes(
                            b"fixed TLS persistence reading"
                        )
                        config = directory / "config.json"
                        config.write_text(
                            json.dumps(
                                {
                                    "private": str(directory),
                                    "credentials": str(credentials),
                                    "profile": profile,
                                    "boundary": boundary,
                                }
                            )
                        )
                        with (directory / "worker.log").open("w") as log:
                            gateway = subprocess.Popen(
                                [sys.executable, __file__, "--worker", str(config)],
                                env=env,
                                stdout=log,
                                stderr=subprocess.STDOUT,
                            )
                            customer = None
                            try:
                                ready(gateway, directory / "ready")
                                customer = subprocess.Popen(
                                    client_command(
                                        directory,
                                        credentials,
                                        profile,
                                        directory / "client_before.json",
                                    ),
                                    env=env,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    text=True,
                                )
                                ready(gateway, directory / "barrier")
                                (
                                    gateway.terminate
                                    if termination == "sigterm_cleanup"
                                    else gateway.kill
                                )()
                                code = gateway.wait(timeout=10)
                                assert code == (
                                    0
                                    if termination == "sigterm_cleanup"
                                    else -signal.SIGKILL
                                )
                                customer.communicate(timeout=25)
                                assert customer.returncode == 2
                            finally:
                                for process in [gateway, customer]:
                                    if process and process.poll() is None:
                                        process.kill()
                                        process.wait(timeout=5)
                        first = json.loads(
                            (directory / "client_before.json").read_text()
                        )
                        assert not first["acknowledged"]
                        check_tls(first, profile, False)
                        with sqlite3.connect(directory / "db") as db:
                            assert (
                                db.execute("PRAGMA integrity_check").fetchone()[0]
                                == "ok"
                            )
                            records = db.execute(
                                "SELECT device,id,digest FROM readings"
                            ).fetchall()
                            effects = db.execute(
                                "SELECT device,id,digest FROM effects"
                            ).fetchall()
                        committed = boundary in ["after_commit", "before_ack"]
                        assert records == effects and len(records) == int(committed)
                        with (directory / "retry.log").open("w") as log:
                            server = subprocess.Popen(
                                [
                                    sys.executable,
                                    str(PROBE),
                                    "server",
                                    "--host",
                                    "127.0.0.1",
                                    "--port",
                                    "39922",
                                    "--credentials",
                                    str(credentials),
                                    "--profile",
                                    profile,
                                    "--ledger",
                                    str(directory / "db"),
                                    "--ready",
                                    str(directory / "retry_ready"),
                                    "--connections",
                                    "1",
                                    "--deduplicate",
                                    "--output",
                                    str(directory / "server_after.json"),
                                ],
                                env=env,
                                stdout=log,
                                stderr=subprocess.STDOUT,
                            )
                            try:
                                ready(server, directory / "retry_ready")
                                result = subprocess.run(
                                    client_command(
                                        directory,
                                        credentials,
                                        profile,
                                        directory / "client_after.json",
                                    ),
                                    env=env,
                                    capture_output=True,
                                    timeout=30,
                                )
                                assert result.returncode == 0
                                assert server.wait(timeout=20) == 0
                            finally:
                                if server.poll() is None:
                                    server.kill()
                                    server.wait(timeout=5)
                        second = json.loads(
                            (directory / "client_after.json").read_text()
                        )
                        after = json.loads(
                            (directory / "server_after.json").read_text()
                        )
                        check_tls(second, profile, False)
                        assert (
                            second["acknowledged"] and second["duplicate"] == committed
                        )
                        assert (
                            first["client_share_sha256"]
                            != second["client_share_sha256"]
                        )
                        assert (
                            after["unique_readings"]
                            == after["application_effects"]
                            == 1
                            and after["duplicate_effects"] == 0
                        )
                        assert after["connections"][0]["dedup_device"] == "iot_1"
                        rows.append(
                            {
                                "profile": profile,
                                "boundary": boundary,
                                "termination": termination,
                                "gateway_exit_code": code,
                                "initial_acknowledged": False,
                                "rows_after_restart": len(records),
                                "effects_after_restart": len(effects),
                                "retry_acknowledged": True,
                                "retry_duplicate": second["duplicate"],
                                "final_unique_readings": 1,
                                "final_effects": 1,
                                "verified_tls": {
                                    "before": first["verify_result"],
                                    "retry": second["verify_result"],
                                },
                                "dedup_device": "iot_1",
                            }
                        )
                        (args.output / "progress.json").write_text(
                            json.dumps(
                                {"completed": len(rows), "checks": rows}, indent=2
                            )
                        )
                        print(
                            json.dumps(
                                {
                                    "completed": len(rows),
                                    "profile": profile,
                                    "boundary": boundary,
                                    "termination": termination,
                                }
                            ),
                            flush=True,
                        )
        data = {
            "status": "PASS",
            "checks": rows,
            "note": "Actual native TLS gateway and unchanged ledger; SIGTERM executes cleanup, SIGKILL does not. OS and storage stay running; no physical power loss.",
            "sources": {
                f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest()
                for f in [
                    "pqc_iot_simulator/pqc_iot_sim/control/tls_persistence_scenarios.py",
                    "pqc_iot_simulator/pqc_iot_sim/runtime/endpoints/session.py",
                    "pqc_iot_simulator/pqc_iot_sim/runtime/native/context_costs/native.c",
                    "pqc_iot_simulator/pqc_iot_sim/control/reading_ledger.py",
                ]
            },
        }
        (args.output / "results.json").write_text(json.dumps(data, indent=2))
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "checks": len(rows),
                    "TLS_connections": 2 * len(rows),
                }
            )
        )
        return args.output


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--worker", type=Path)
    ap.add_argument("--output", type=Path)
    options = vars(ap.parse_args())
    worker(options["worker"])
