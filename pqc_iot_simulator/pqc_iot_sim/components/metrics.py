from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any
import csv
import json
import time

from .logger import Logger


@dataclass
class TransmissionMetric:
    transmission_id: int
    source: str
    destination: str
    status: str
    delivered: bool
    path: list[str]
    hops: int
    protocol: str | None
    crypto_mode: str | None

    payload_size_bytes: int
    original_payload_size_bytes: int
    protected_payload_size_bytes: int

    crypto_backend: str | None = None
    crypto_algorithm: str | None = None
    crypto_original_size_bytes: int = 0
    crypto_protected_size_bytes: int = 0
    crypto_overhead_bytes: int = 0
    crypto_time_seconds: float = 0.0
    crypto_energy_cost: float = 0.0
    crypto_metadata: dict[str, Any] = field(default_factory=dict)

    link_latency_ms: float | None = None
    link_packet_loss_percent: float | None = None
    link_packets_transmitted: int | None = None
    link_packets_received: int | None = None
    link_rtt_min_ms: float | None = None
    link_rtt_avg_ms: float | None = None
    link_rtt_max_ms: float | None = None
    link_rtt_mdev_ms: float | None = None
    link_metrics: dict[str, Any] = field(default_factory=dict)

    started_at: str = ""
    finished_at: str = ""
    duration_seconds: float = 0.0

    energy_consumed_by_host: dict[str, float] = field(default_factory=dict)
    total_energy_consumed: float = 0.0

    result: dict[str, Any] | None = None


class MetricsCollector:
    def __init__(
        self,
        logger: Logger | None = None,
        verbose: bool = True
    ):
        self.logger = logger or Logger(name="MetricsCollector", verbose=verbose)
        self.transmissions: list[TransmissionMetric] = []
        self._transmission_counter = 0

        self.logger.log(
            "MetricsCollector criado",
            component="MetricsCollector"
        )

    def next_transmission_id(self):
        self._transmission_counter += 1
        return self._transmission_counter

    def now(self):
        return datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    def snapshot_energy(self, hosts: dict[str, Any]):
        snapshot = {}

        for host_id, host in hosts.items():
            snapshot[host_id] = float(host.energy)

        self.logger.log(
            "Snapshot de energia criado",
            data={
                "hosts": list(snapshot.keys())
            },
            component="MetricsCollector"
        )

        return snapshot

    def estimate_payload_size(self, payload: Any):
        try:
            serialized = json.dumps(
                payload,
                ensure_ascii=False,
                default=str
            )

            return len(serialized.encode("utf-8"))

        except TypeError:
            return len(str(payload).encode("utf-8"))

    def safe_int(self, value: Any, default: int | None = None):
        try:
            if value is None:
                return default

            return int(value)

        except (TypeError, ValueError):
            return default

    def safe_float(self, value: Any, default: float | None = None):
        try:
            if value is None:
                return default

            return float(value)

        except (TypeError, ValueError):
            return default

    def extract_crypto_data(self, crypto: dict[str, Any] | None):
        if not crypto:
            return {
                "crypto_backend": None,
                "crypto_algorithm": None,
                "crypto_original_size_bytes": 0,
                "crypto_protected_size_bytes": 0,
                "crypto_overhead_bytes": 0,
                "crypto_time_seconds": 0.0,
                "crypto_energy_cost": 0.0,
                "crypto_metadata": {}
            }

        return {
            "crypto_backend": crypto.get("backend"),
            "crypto_algorithm": crypto.get("algorithm"),
            "crypto_original_size_bytes": int(
                crypto.get("original_size_bytes") or 0
            ),
            "crypto_protected_size_bytes": int(
                crypto.get("protected_size_bytes") or 0
            ),
            "crypto_overhead_bytes": int(
                crypto.get("overhead_bytes") or 0
            ),
            "crypto_time_seconds": float(
                crypto.get("operation_time_seconds") or 0.0
            ),
            "crypto_energy_cost": float(
                crypto.get("energy_cost") or 0.0
            ),
            "crypto_metadata": crypto.get("metadata") or {}
        }

    def extract_link_data(self, link_metrics: dict[str, Any] | None):
        if not link_metrics:
            return {
                "link_latency_ms": None,
                "link_packet_loss_percent": None,
                "link_packets_transmitted": None,
                "link_packets_received": None,
                "link_rtt_min_ms": None,
                "link_rtt_avg_ms": None,
                "link_rtt_max_ms": None,
                "link_rtt_mdev_ms": None,
                "link_metrics": {}
            }

        latency_ms = self.safe_float(
            link_metrics.get("latency_ms"),
            default=None
        )

        rtt_avg_ms = self.safe_float(
            link_metrics.get("rtt_avg_ms"),
            default=None
        )

        if latency_ms is None:
            latency_ms = rtt_avg_ms

        return {
            "link_latency_ms": latency_ms,
            "link_packet_loss_percent": self.safe_float(
                link_metrics.get("packet_loss_percent"),
                default=None
            ),
            "link_packets_transmitted": self.safe_int(
                link_metrics.get("packets_transmitted"),
                default=None
            ),
            "link_packets_received": self.safe_int(
                link_metrics.get("packets_received"),
                default=None
            ),
            "link_rtt_min_ms": self.safe_float(
                link_metrics.get("rtt_min_ms"),
                default=None
            ),
            "link_rtt_avg_ms": rtt_avg_ms,
            "link_rtt_max_ms": self.safe_float(
                link_metrics.get("rtt_max_ms"),
                default=None
            ),
            "link_rtt_mdev_ms": self.safe_float(
                link_metrics.get("rtt_mdev_ms"),
                default=None
            ),
            "link_metrics": link_metrics
        }

    def calculate_energy_consumed(
        self,
        hosts: dict[str, Any],
        baseline_energy: dict[str, float] | None = None
    ):
        energy_by_host = {}

        for host_id, host in hosts.items():
            if baseline_energy and host_id in baseline_energy:
                consumed = baseline_energy[host_id] - float(host.energy)
            else:
                consumed = float(host.initial_energy) - float(host.energy)

            energy_by_host[host_id] = round(consumed, 6)

        total_energy = round(sum(energy_by_host.values()), 6)

        return energy_by_host, total_energy

    def record_transmission(
        self,
        source: str,
        destination: str,
        status: str,
        path: list[str],
        protocol: str | None,
        crypto_mode: str | None,
        payload: Any,
        hosts: dict[str, Any],
        baseline_energy: dict[str, float] | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        duration_seconds: float | None = None,
        result: dict[str, Any] | None = None,
        crypto: dict[str, Any] | None = None,
        link_metrics: dict[str, Any] | None = None
    ):
        transmission_id = self.next_transmission_id()

        energy_by_host, total_energy = self.calculate_energy_consumed(
            hosts=hosts,
            baseline_energy=baseline_energy
        )

        crypto_data = self.extract_crypto_data(crypto)
        link_data = self.extract_link_data(link_metrics)

        measured_payload_size = self.estimate_payload_size(payload)

        original_payload_size = crypto_data["crypto_original_size_bytes"]
        protected_payload_size = crypto_data["crypto_protected_size_bytes"]

        if original_payload_size <= 0:
            original_payload_size = measured_payload_size

        if protected_payload_size <= 0:
            protected_payload_size = measured_payload_size

        metric = TransmissionMetric(
            transmission_id=transmission_id,
            source=source,
            destination=destination,
            status=status,
            delivered=status == "delivered",
            path=path,
            hops=max(len(path) - 1, 0),
            protocol=protocol,
            crypto_mode=crypto_mode,

            payload_size_bytes=protected_payload_size,
            original_payload_size_bytes=original_payload_size,
            protected_payload_size_bytes=protected_payload_size,

            crypto_backend=crypto_data["crypto_backend"],
            crypto_algorithm=crypto_data["crypto_algorithm"],
            crypto_original_size_bytes=crypto_data["crypto_original_size_bytes"],
            crypto_protected_size_bytes=crypto_data["crypto_protected_size_bytes"],
            crypto_overhead_bytes=crypto_data["crypto_overhead_bytes"],
            crypto_time_seconds=round(crypto_data["crypto_time_seconds"], 6),
            crypto_energy_cost=round(crypto_data["crypto_energy_cost"], 6),
            crypto_metadata=crypto_data["crypto_metadata"],

            link_latency_ms=link_data["link_latency_ms"],
            link_packet_loss_percent=link_data["link_packet_loss_percent"],
            link_packets_transmitted=link_data["link_packets_transmitted"],
            link_packets_received=link_data["link_packets_received"],
            link_rtt_min_ms=link_data["link_rtt_min_ms"],
            link_rtt_avg_ms=link_data["link_rtt_avg_ms"],
            link_rtt_max_ms=link_data["link_rtt_max_ms"],
            link_rtt_mdev_ms=link_data["link_rtt_mdev_ms"],
            link_metrics=link_data["link_metrics"],

            started_at=started_at or self.now(),
            finished_at=finished_at or self.now(),
            duration_seconds=round(duration_seconds or 0.0, 6),

            energy_consumed_by_host=energy_by_host,
            total_energy_consumed=total_energy,

            result=result
        )

        self.transmissions.append(metric)

        self.logger.log(
            "Metrica de transmissao registrada",
            data={
                "transmission_id": metric.transmission_id,
                "source": metric.source,
                "destination": metric.destination,
                "status": metric.status,
                "hops": metric.hops,
                "total_energy_consumed": metric.total_energy_consumed,
                "payload_size_bytes": metric.payload_size_bytes,
                "crypto_overhead_bytes": metric.crypto_overhead_bytes,
                "crypto_time_seconds": metric.crypto_time_seconds,
                "crypto_energy_cost": metric.crypto_energy_cost,
                "link_latency_ms": metric.link_latency_ms,
                "link_packet_loss_percent": metric.link_packet_loss_percent,
                "duration_seconds": metric.duration_seconds
            },
            component="MetricsCollector"
        )

        return metric

    def record_from_send_result(
        self,
        send_result: dict[str, Any],
        hosts: dict[str, Any],
        payload: Any,
        baseline_energy: dict[str, float] | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        duration_seconds: float | None = None,
        link_metrics: dict[str, Any] | None = None
    ):
        packet = send_result.get("packet")

        protocol = None
        crypto_mode = None

        if packet is not None:
            protocol = getattr(packet, "protocol", None)
            crypto_mode = getattr(packet, "crypto_mode", None)

        crypto = send_result.get("crypto")
        # Prioriza o link_metrics do parâmetro; caso contrário, tira do send_result
        if link_metrics is None:
            link_metrics = send_result.get("link_metrics")

        return self.record_transmission(
            source=send_result.get("source"),
            destination=send_result.get("destination"),
            status=send_result.get("status"),
            path=send_result.get("path", []),
            protocol=protocol,
            crypto_mode=crypto_mode,
            payload=payload,
            hosts=hosts,
            baseline_energy=baseline_energy,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration_seconds,
            crypto=crypto,
            link_metrics=link_metrics,
            result={
                "status": send_result.get("status"),
                "path": send_result.get("path", []),
                "crypto": crypto,
                "link_metrics": link_metrics
            }
        )

    def record_link_metrics(
        self,
        source: str,
        destination: str,
        link_metrics: dict[str, Any]
    ):
        data = self.extract_link_data(link_metrics)

        self.logger.log(
            "Metricas reais de link registradas",
            data={
                "source": source,
                "destination": destination,
                "latency_ms": data["link_latency_ms"],
                "packet_loss_percent": data["link_packet_loss_percent"],
                "packets_transmitted": data["link_packets_transmitted"],
                "packets_received": data["link_packets_received"]
            },
            component="MetricsCollector"
        )

        return data

    def start_timer(self):
        return time.perf_counter(), self.now()

    def finish_timer(self, start_time: float):
        duration = time.perf_counter() - start_time

        return round(duration, 6), self.now()

    def get_transmissions(self):
        return [
            asdict(metric)
            for metric in self.transmissions
        ]

    def get_last_transmission(self):
        if not self.transmissions:
            return None

        return asdict(self.transmissions[-1])

    def get_summary(self):
        total_transmissions = len(self.transmissions)

        delivered = sum(
            1 for metric in self.transmissions
            if metric.delivered
        )

        failed = total_transmissions - delivered

        total_energy = round(
            sum(metric.total_energy_consumed for metric in self.transmissions),
            6
        )

        total_payload_bytes = sum(
            metric.payload_size_bytes for metric in self.transmissions
        )

        total_original_payload_bytes = sum(
            metric.original_payload_size_bytes for metric in self.transmissions
        )

        total_protected_payload_bytes = sum(
            metric.protected_payload_size_bytes for metric in self.transmissions
        )

        total_crypto_overhead_bytes = sum(
            metric.crypto_overhead_bytes for metric in self.transmissions
        )

        total_crypto_time = round(
            sum(metric.crypto_time_seconds for metric in self.transmissions),
            6
        )

        total_crypto_energy = round(
            sum(metric.crypto_energy_cost for metric in self.transmissions),
            6
        )

        link_latency_values = [
            metric.link_latency_ms
            for metric in self.transmissions
            if metric.link_latency_ms is not None
        ]

        link_packet_loss_values = [
            metric.link_packet_loss_percent
            for metric in self.transmissions
            if metric.link_packet_loss_percent is not None
        ]

        total_link_packets_transmitted = sum(
            metric.link_packets_transmitted or 0
            for metric in self.transmissions
        )

        total_link_packets_received = sum(
            metric.link_packets_received or 0
            for metric in self.transmissions
        )

        average_hops = 0.0
        average_energy = 0.0
        average_duration = 0.0
        average_crypto_overhead = 0.0
        average_crypto_time = 0.0
        average_crypto_energy = 0.0
        average_link_latency_ms = None
        average_link_packet_loss_percent = None
        link_delivery_rate = None

        if total_transmissions > 0:
            average_hops = round(
                sum(metric.hops for metric in self.transmissions) / total_transmissions,
                6
            )

            average_energy = round(
                total_energy / total_transmissions,
                6
            )

            average_duration = round(
                sum(metric.duration_seconds for metric in self.transmissions) / total_transmissions,
                6
            )

            average_crypto_overhead = round(
                total_crypto_overhead_bytes / total_transmissions,
                6
            )

            average_crypto_time = round(
                total_crypto_time / total_transmissions,
                6
            )

            average_crypto_energy = round(
                total_crypto_energy / total_transmissions,
                6
            )

        if link_latency_values:
            average_link_latency_ms = round(
                sum(link_latency_values) / len(link_latency_values),
                6
            )

        if link_packet_loss_values:
            average_link_packet_loss_percent = round(
                sum(link_packet_loss_values) / len(link_packet_loss_values),
                6
            )

        if total_link_packets_transmitted > 0:
            link_delivery_rate = round(
                total_link_packets_received / total_link_packets_transmitted,
                6
            )

        delivery_rate = 0.0

        if total_transmissions > 0:
            delivery_rate = round(delivered / total_transmissions, 6)

        summary = {
            "total_transmissions": total_transmissions,
            "delivered": delivered,
            "failed": failed,
            "delivery_rate": delivery_rate,

            "total_energy_consumed": total_energy,
            "average_energy_consumed": average_energy,

            "average_hops": average_hops,
            "average_duration_seconds": average_duration,

            "total_payload_bytes": total_payload_bytes,
            "total_original_payload_bytes": total_original_payload_bytes,
            "total_protected_payload_bytes": total_protected_payload_bytes,

            "total_crypto_overhead_bytes": total_crypto_overhead_bytes,
            "average_crypto_overhead_bytes": average_crypto_overhead,
            "total_crypto_time_seconds": total_crypto_time,
            "average_crypto_time_seconds": average_crypto_time,
            "total_crypto_energy_cost": total_crypto_energy,
            "average_crypto_energy_cost": average_crypto_energy,

            "average_link_latency_ms": average_link_latency_ms,
            "average_link_packet_loss_percent": average_link_packet_loss_percent,
            "total_link_packets_transmitted": total_link_packets_transmitted,
            "total_link_packets_received": total_link_packets_received,
            "link_delivery_rate": link_delivery_rate
        }

        self.logger.log(
            "Resumo de metricas solicitado",
            data=summary,
            component="MetricsCollector"
        )

        return summary

    def get_energy_by_host(self):
        energy_by_host = {}

        for metric in self.transmissions:
            for host_id, consumed in metric.energy_consumed_by_host.items():
                energy_by_host.setdefault(host_id, 0.0)
                energy_by_host[host_id] += consumed

        return {
            host_id: round(value, 6)
            for host_id, value in energy_by_host.items()
        }

    def get_delivery_summary(self):
        summary = {}

        for metric in self.transmissions:
            key = f"{metric.source} para {metric.destination}"

            if key not in summary:
                summary[key] = {
                    "total": 0,
                    "delivered": 0,
                    "failed": 0
                }

            summary[key]["total"] += 1

            if metric.delivered:
                summary[key]["delivered"] += 1
            else:
                summary[key]["failed"] += 1

        for item in summary.values():
            if item["total"] > 0:
                item["delivery_rate"] = round(
                    item["delivered"] / item["total"],
                    6
                )
            else:
                item["delivery_rate"] = 0.0

        return summary

    def get_crypto_summary(self):
        summary = {}

        for metric in self.transmissions:
            mode = metric.crypto_mode or "unknown"

            if mode not in summary:
                summary[mode] = {
                    "total": 0,
                    "total_crypto_overhead_bytes": 0,
                    "total_crypto_time_seconds": 0.0,
                    "total_crypto_energy_cost": 0.0,
                    "total_protected_payload_bytes": 0
                }

            summary[mode]["total"] += 1
            summary[mode]["total_crypto_overhead_bytes"] += metric.crypto_overhead_bytes
            summary[mode]["total_crypto_time_seconds"] += metric.crypto_time_seconds
            summary[mode]["total_crypto_energy_cost"] += metric.crypto_energy_cost
            summary[mode]["total_protected_payload_bytes"] += metric.protected_payload_size_bytes

        for item in summary.values():
            total = item["total"]

            if total > 0:
                item["average_crypto_overhead_bytes"] = round(
                    item["total_crypto_overhead_bytes"] / total,
                    6
                )
                item["average_crypto_time_seconds"] = round(
                    item["total_crypto_time_seconds"] / total,
                    6
                )
                item["average_crypto_energy_cost"] = round(
                    item["total_crypto_energy_cost"] / total,
                    6
                )
                item["average_protected_payload_bytes"] = round(
                    item["total_protected_payload_bytes"] / total,
                    6
                )

            item["total_crypto_time_seconds"] = round(
                item["total_crypto_time_seconds"],
                6
            )
            item["total_crypto_energy_cost"] = round(
                item["total_crypto_energy_cost"],
                6
            )

        return summary

    def get_link_summary(self):
        summary = {}

        for metric in self.transmissions:
            key = f"{metric.source} para {metric.destination}"

            if key not in summary:
                summary[key] = {
                    "total": 0,
                    "latencies_ms": [],
                    "packet_losses_percent": [],
                    "packets_transmitted": 0,
                    "packets_received": 0
                }

            summary[key]["total"] += 1

            if metric.link_latency_ms is not None:
                summary[key]["latencies_ms"].append(metric.link_latency_ms)

            if metric.link_packet_loss_percent is not None:
                summary[key]["packet_losses_percent"].append(
                    metric.link_packet_loss_percent
                )

            summary[key]["packets_transmitted"] += metric.link_packets_transmitted or 0
            summary[key]["packets_received"] += metric.link_packets_received or 0

        for item in summary.values():
            latencies = item.pop("latencies_ms")
            losses = item.pop("packet_losses_percent")

            if latencies:
                item["average_latency_ms"] = round(
                    sum(latencies) / len(latencies),
                    6
                )
                item["min_latency_ms"] = round(min(latencies), 6)
                item["max_latency_ms"] = round(max(latencies), 6)
            else:
                item["average_latency_ms"] = None
                item["min_latency_ms"] = None
                item["max_latency_ms"] = None

            if losses:
                item["average_packet_loss_percent"] = round(
                    sum(losses) / len(losses),
                    6
                )
            else:
                item["average_packet_loss_percent"] = None

            if item["packets_transmitted"] > 0:
                item["delivery_rate"] = round(
                    item["packets_received"] / item["packets_transmitted"],
                    6
                )
            else:
                item["delivery_rate"] = None

        return summary

    def clear(self):
        self.transmissions.clear()
        self._transmission_counter = 0

        self.logger.log(
            "Metricas apagadas",
            component="MetricsCollector"
        )

    def export_json(self, output_path: str):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "summary": self.get_summary(),
            "energy_by_host": self.get_energy_by_host(),
            "delivery_summary": self.get_delivery_summary(),
            "crypto_summary": self.get_crypto_summary(),
            "link_summary": self.get_link_summary(),
            "transmissions": self.get_transmissions()
        }

        with open(path, "w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                indent=4,
                ensure_ascii=False,
                default=str
            )

        self.logger.log(
            "Metricas exportadas em JSON",
            data={"output_path": output_path},
            component="MetricsCollector"
        )

        return self

    def export_csv(self, output_path: str):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        rows = []

        for metric in self.transmissions:
            rows.append({
                "transmission_id": metric.transmission_id,
                "source": metric.source,
                "destination": metric.destination,
                "status": metric.status,
                "delivered": metric.delivered,
                "path": " para ".join(metric.path),
                "hops": metric.hops,
                "protocol": metric.protocol,
                "crypto_mode": metric.crypto_mode,
                "crypto_backend": metric.crypto_backend,
                "crypto_algorithm": metric.crypto_algorithm,

                "payload_size_bytes": metric.payload_size_bytes,
                "original_payload_size_bytes": metric.original_payload_size_bytes,
                "protected_payload_size_bytes": metric.protected_payload_size_bytes,

                "crypto_original_size_bytes": metric.crypto_original_size_bytes,
                "crypto_protected_size_bytes": metric.crypto_protected_size_bytes,
                "crypto_overhead_bytes": metric.crypto_overhead_bytes,
                "crypto_time_seconds": metric.crypto_time_seconds,
                "crypto_energy_cost": metric.crypto_energy_cost,

                "link_latency_ms": metric.link_latency_ms,
                "link_packet_loss_percent": metric.link_packet_loss_percent,
                "link_packets_transmitted": metric.link_packets_transmitted,
                "link_packets_received": metric.link_packets_received,
                "link_rtt_min_ms": metric.link_rtt_min_ms,
                "link_rtt_avg_ms": metric.link_rtt_avg_ms,
                "link_rtt_max_ms": metric.link_rtt_max_ms,
                "link_rtt_mdev_ms": metric.link_rtt_mdev_ms,

                "started_at": metric.started_at,
                "finished_at": metric.finished_at,
                "duration_seconds": metric.duration_seconds,
                "total_energy_consumed": metric.total_energy_consumed
            })

        fieldnames = [
            "transmission_id",
            "source",
            "destination",
            "status",
            "delivered",
            "path",
            "hops",
            "protocol",
            "crypto_mode",
            "crypto_backend",
            "crypto_algorithm",

            "payload_size_bytes",
            "original_payload_size_bytes",
            "protected_payload_size_bytes",

            "crypto_original_size_bytes",
            "crypto_protected_size_bytes",
            "crypto_overhead_bytes",
            "crypto_time_seconds",
            "crypto_energy_cost",

            "link_latency_ms",
            "link_packet_loss_percent",
            "link_packets_transmitted",
            "link_packets_received",
            "link_rtt_min_ms",
            "link_rtt_avg_ms",
            "link_rtt_max_ms",
            "link_rtt_mdev_ms",

            "started_at",
            "finished_at",
            "duration_seconds",
            "total_energy_consumed"
        ]

        with open(path, "w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        self.logger.log(
            "Metricas exportadas em CSV",
            data={"output_path": output_path},
            component="MetricsCollector"
        )

        return self