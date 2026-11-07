"""Read measured ticket diagnostics in raw or public-summary format."""


class TicketDiagnostics:
    def __init__(self, data):
        if data.get("status") != "PASS":
            raise ValueError("ticket diagnostics did not pass")
        self.data = data

    def matched_client_controls(self):
        rows = []
        for raw in self.data["diagnostics"]:
            if raw.get("client_identity", "iot_1") != "iot_1":
                continue
            row = dict(raw)
            row["root"] = raw.get("root", raw.get("include_root"))
            if "connections" not in row:
                row["connections"] = raw["server"]["connections"]
            if row["profile"] == "pqc" and row["root"] == 0:
                rows.append(row)
        candidates = [
            (ec, ml)
            for ec in rows
            if ec["client_key"] == "EC"
            for ml in rows
            if ml["client_key"] == "ML-DSA-44"
            if all(
                ec["certificates"][name]["sha256"] == ml["certificates"][name]["sha256"]
                for name in ("server", "ca")
            )
        ]
        if len(candidates) != 1:
            raise ValueError(
                "requires one client-key comparison with the same server and CA"
            )
        return candidates[0]
