"""Exercise exhausted retry budgets; no failed reading may disappear from results."""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.continuity_credentials import provision
from scripts.continuity_design import PROFILES, schedule
from scripts.run_continuity_campaign import LocalNode, execute_case


class AlwaysDropNode(LocalNode):
    @staticmethod
    def popen(command, **kwargs):
        if "server" in command:
            command = [*command, "--drop-ack", *map(str, range(100))]
        return subprocess.Popen(command, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    results = []
    with tempfile.TemporaryDirectory(prefix="continuity-budget-test-") as tmp:
        private = Path(tmp)
        for profile in PROFILES:
            provision(private/profile, profile)
            for dedup in (False, True):
                name = f"{profile}_dedup{int(dedup)}"
                case = execute_case(LocalNode(), AlwaysDropNode(), "127.0.0.1", "127.0.0.1", "lo",
                    args.output/name, private/name, private/profile, profile, "resume_preserved", dedup,
                    schedule(5, 1, 0, 0), 5, 0, capture_enabled=False)
                if case["confirmed_readings"] != 0 or len(case["unconfirmed_readings"]) != 5:
                    raise RuntimeError("failed readings disappeared from outcomes")
                if len(case["clients"]) != 15 or case["delivery_status"] != "budget_exhausted":
                    raise RuntimeError("retry limit was not respected")
                if case["application_effects"] != (5 if dedup else 15):
                    raise RuntimeError("bank effects do not match actual receptions")
                results.append({"profile":profile, "deduplicate":dedup, "confirmed":0,
                                "unconfirmed":5, "attempts":15, "status":"PASS"})
    (args.output/"results.json").write_text(json.dumps({"status":"PASS", "checks":results},indent=2))
    print(json.dumps({"status":"PASS", "checks":len(results)}),flush=True)


if __name__ == "__main__":
    main()
