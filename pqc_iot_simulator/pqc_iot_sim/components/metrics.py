"""Coleta, resume e exporta métricas da plataforma."""

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
    """Armazena as métricas de uma transmissão lógica."""
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
    """Coleta e resume métricas das transmissões de rede."""
    def __init__(
        self,
        logger: Logger | None = None,
        verbose: bool = True
    ):
        """Inicializa a instância e prepara seu estado interno.

        Parâmetros:
            logger: Registrador usado pelo componente.
            verbose: Indica se a saída detalhada será exibida.
        """
        self.logger = logger or Logger(name="MetricsCollector", verbose=verbose)
        self.transmissions: list[TransmissionMetric] = []
        self._transmission_counter = 0

        self.logger.log(
            "Coletor de metricas criado e pronto para registrar transmissoes",
            component="MetricsCollector"
        )

    def _status_label(self, status: str | None):
        """Converte o estado da transmissão em um rótulo legível."""
        labels = {
            "delivered": "entregue",
            "not_delivered": "nao entregue",
            "failed": "falhou"
        }

        if status is None:
            return "nao informado"

        return labels.get(status, status)

    def _crypto_label(self, crypto_mode: str | None):
        """Converte o modo criptográfico em um rótulo legível."""
        labels = {
            "classical": "classica",
            "hybrid": "hibrida",
            "pqc": "pos quantica"
        }

        if crypto_mode is None:
            return "nao informado"

        return labels.get(crypto_mode, crypto_mode)

    def _format_number(self, value: Any):
        """Formata um número para exibição nos logs."""
        if value is None:
            return "nao informado"

        if isinstance(value, float):
            value = round(value, 6)

            if value.is_integer():
                return int(value)

        return value

    def _format_path(self, path: list[str]):
        """Formata uma sequência de nós como caminho de rede."""
        if not path:
            return "sem caminho"

        return " -> ".join(path)

    def next_transmission_id(self):
        """Gera o próximo identificador de transmissão."""
        self._transmission_counter += 1
        return self._transmission_counter

    def now(self):
        """Retorna o instante atual em formato textual."""
        return datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    def snapshot_energy(self, hosts: dict[str, Any]):
        """Captura o consumo energético atual dos hosts.

        Parâmetros:
            hosts: Hosts envolvidos na medição.
        """
        snapshot = {}

        for host_id, host in hosts.items():
            snapshot[host_id] = float(host.energy)

        self.logger.log(
            f"Snapshot de energia criado para {len(snapshot)} hosts",
            component="MetricsCollector"
        )

        return snapshot

    def estimate_payload_size(self, payload: Any):
        """Estima o tamanho serializado de um conteúdo.

        Parâmetros:
            payload: Conteúdo útil da mensagem.
        """
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
        """Converte um valor para inteiro com um padrão seguro.

        Parâmetros:
            value: Valor processado pela operação.
            default: Valor usado quando a conversão não é possível.
        """
        try:
            if value is None:
                return default

            return int(value)

        except (TypeError, ValueError):
            return default

    def safe_float(self, value: Any, default: float | None = None):
        """Converte um valor para número real com um padrão seguro.

        Parâmetros:
            value: Valor processado pela operação.
            default: Valor usado quando a conversão não é possível.
        """
        try:
            if value is None:
                return default

            return float(value)

        except (TypeError, ValueError):
            return default

    def extract_crypto_data(self, crypto: dict[str, Any] | None):
        """Extrai os campos relacionados à criptografia.

        Parâmetros:
            crypto: Resultado ou configuração criptográfica.
        """
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
        """Extrai os campos relacionados ao enlace.

        Parâmetros:
            link_metrics: Métricas observadas no enlace.
        """
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
        """Calcula a energia consumida entre duas capturas.

        Parâmetros:
            hosts: Hosts envolvidos na medição.
            baseline_energy: Captura de energia anterior à operação.
        """
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
        """Registra as métricas de uma transmissão.

        Parâmetros:
            source: Identificador da origem.
            destination: Identificador do destino.
            status: Estado da transmissão.
            path: Sequência de nós que forma o caminho.
            protocol: Protocolo de aplicação utilizado.
            crypto_mode: Modo criptográfico clássico, PQC ou híbrido.
            payload: Conteúdo útil da mensagem.
            hosts: Hosts envolvidos na medição.
            baseline_energy: Captura de energia anterior à operação.
            started_at: Instante em que a operação começou.
            finished_at: Instante em que a operação terminou.
            duration_seconds: Duração da operação, em segundos.
            result: Resultado produzido pela operação anterior.
            crypto: Resultado ou configuração criptográfica.
            link_metrics: Métricas observadas no enlace.
        """
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
            (
                f"Transmissao {metric.transmission_id} registrada, "
                f"status: {self._status_label(metric.status)}, "
                f"origem: {metric.source}, "
                f"destino: {metric.destination}, "
                f"saltos: {metric.hops}, "
                f"protocolo: {metric.protocol or 'nao informado'}, "
                f"criptografia: {self._crypto_label(metric.crypto_mode)}, "
                f"energia consumida: {self._format_number(metric.total_energy_consumed)} J (campo legado), "
                f"overhead criptografico: {metric.crypto_overhead_bytes} bytes, "
                f"tempo de criptografia: {self._format_number(metric.crypto_time_seconds)}s, "
                f"latencia: {self._format_number(metric.link_latency_ms)} ms, "
                f"perda de pacotes: {self._format_number(metric.link_packet_loss_percent)}%, "
                f"duracao: {self._format_number(metric.duration_seconds)}s"
            ),
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
        """Registra métricas a partir do resultado de um envio.

        Parâmetros:
            send_result: Resultado retornado pela operação de envio.
            hosts: Hosts envolvidos na medição.
            payload: Conteúdo útil da mensagem.
            baseline_energy: Captura de energia anterior à operação.
            started_at: Instante em que a operação começou.
            finished_at: Instante em que a operação terminou.
            duration_seconds: Duração da operação, em segundos.
            link_metrics: Métricas observadas no enlace.
        """
        packet = send_result.get("packet")

        protocol = None
        crypto_mode = None

        if packet is not None:
            protocol = getattr(packet, "protocol", None)
            crypto_mode = getattr(packet, "crypto_mode", None)

        if protocol is None:
            protocol = send_result.get("protocol")

        if crypto_mode is None:
            crypto_mode = send_result.get("crypto_mode")

        if crypto_mode is None and isinstance(send_result.get("crypto"), dict):
            crypto_mode = send_result.get("crypto", {}).get("mode")

        crypto = send_result.get("crypto")

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

    def start_timer(self):
        """Inicia a medição de duração de uma operação."""
        return time.perf_counter(), self.now()

    def finish_timer(self, start_time: float):
        """Finaliza uma medição e retorna sua duração.

        Parâmetros:
            start_time: Instante inicial usado no cálculo da duração.
        """
        duration = time.perf_counter() - start_time

        return round(duration, 6), self.now()

    def get_transmissions(self):
        """Retorna as transmissões registradas."""
        return [
            asdict(metric)
            for metric in self.transmissions
        ]

    def get_last_transmission(self):
        """Retorna a transmissão mais recente."""
        if not self.transmissions:
            return None

        return asdict(self.transmissions[-1])

    def get_summary(self):
        """Calcula e retorna o resumo das métricas."""
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

        summary["energy_unit"] = "J"
        summary["legacy_energy_fields_deprecated"] = True

        return summary

    def get_energy_by_host(self):
        """Soma o consumo energético por host."""
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
        """Resume tentativas, entregas e perdas."""
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
        """Resume os custos e modos criptográficos."""
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
        """Resume as métricas observadas nos enlaces."""
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
        """Remove os registros acumulados pelo componente."""
        self.transmissions.clear()
        self._transmission_counter = 0

        self.logger.log(
            "Metricas apagadas e contador de transmissoes reiniciado",
            component="MetricsCollector"
        )

    def export_json(self, output_path: str):
        """Exporta os dados coletados para JSON.

        Parâmetros:
            output_path: Caminho do arquivo de saída.
        """
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
            f"Metricas exportadas em JSON no arquivo {output_path}",
            component="MetricsCollector"
        )

        return self

    def export_csv(self, output_path: str):
        """Exporta os dados coletados para CSV.

        Parâmetros:
            output_path: Caminho do arquivo de saída.
        """
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
                "total_energy_consumed": metric.total_energy_consumed,
                "energy_unit": "J",
                "legacy_energy_fields_deprecated": True
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
            "total_energy_consumed",
            "energy_unit",
            "legacy_energy_fields_deprecated"
        ]

        with open(path, "w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        self.logger.log(
            f"Metricas exportadas em CSV no arquivo {output_path}",
            component="MetricsCollector"
        )

        return self


class PhysicalMetricsCollector:
    """Coleta e exporta métricas com unidades explícitas dos ciclos físicos."""

    REQUIRED_FIELDS = [
        "energy_sensor_j",
        "energy_cpu_j",
        "energy_crypto_j",
        "energy_wifi_reconnect_initialization_proxy_j",
        "energy_wifi_association_j",
        "energy_tx_j",
        "energy_rx_j",
        "energy_sleep_j",
        "energy_rtc_state_j",
        "energy_total_iot_j",
        "energy_iot_node_j",
        "energy_gateway_j",
        "energy_server_j",
        "energy_network_total_j",
        "battery_remaining_j",
        "battery_remaining_wh",
        "battery_soc_percent",
        "estimated_battery_lifetime_hours",
        "estimated_battery_lifetime_days",
        "application_payload_bytes",
        "protected_message_bytes",
        "handshake_bytes",
        "handshake_protocol_overhead_bytes",
        "mqtt_connect_bytes",
        "mqtt_connack_bytes",
        "mqtt_publish_bytes",
        "mqtt_ack_bytes",
        "mqtt_bytes",
        "tcp_control_bytes",
        "tcp_header_bytes",
        "ip_header_bytes",
        "wifi_link_overhead_bytes",
        "total_wire_bytes",
        "retransmitted_bytes",
        "handshake_count",
        "messages_in_session",
        "deadline_missed",
        "energy_confidence",
        "handshake_energy_in_measurement_j",
        "regulator_efficiency",
    ]

    def __init__(self) -> None:
        """Inicializa a instância e prepara seu estado interno."""
        self.cycles: list[dict[str, Any]] = []

    def record_cycle(self, cycle: Any) -> dict[str, Any]:
        """Registra as métricas de um ciclo físico.

        Parâmetros:
            cycle: Ciclo físico cujas métricas serão processadas.

        Retorna:
            Dicionário com os dados produzidos.
        """
        if hasattr(cycle, "to_dict"):
            row = cycle.to_dict()
        elif isinstance(cycle, dict):
            row = dict(cycle)
        else:
            raise TypeError("cycle must be a dataclass-like object or dictionary")
        missing = [field_name for field_name in self.REQUIRED_FIELDS if field_name not in row]
        if missing:
            raise ValueError(f"physical cycle is missing metrics: {missing}")
        self.cycles.append(row)
        return row

    def clear(self) -> None:
        """Remove os registros acumulados pelo componente."""
        self.cycles.clear()

    def get_cycles(self) -> list[dict[str, Any]]:
        """Retorna os ciclos físicos registrados.

        Retorna:
            Dicionário com os dados produzidos.
        """
        return [dict(cycle) for cycle in self.cycles]

    def get_summary(self) -> dict[str, Any]:
        """Calcula e retorna o resumo das métricas.

        Retorna:
            Dicionário com os dados produzidos.
        """
        attempted = len(self.cycles)
        delivered = sum(bool(row.get("delivered")) for row in self.cycles)
        total_iot_j = sum(float(row.get("energy_total_iot_j") or 0.0) for row in self.cycles)
        useful_bytes = sum(
            int(row.get("application_payload_bytes") or 0)
            for row in self.cycles
            if row.get("delivered")
        )
        last = self.cycles[-1] if self.cycles else {}
        return {
            "cycles": attempted,
            "messages_attempted": attempted,
            "messages_delivered": delivered,
            "messages_lost": attempted - delivered,
            "delivery_rate": delivered / attempted if attempted else 0.0,
            "energy_total_iot_j": total_iot_j,
            "average_energy_iot_per_cycle_j": total_iot_j / attempted if attempted else 0.0,
            "energy_per_message_delivered_j": total_iot_j / delivered if delivered else None,
            "energy_per_application_byte_j": total_iot_j / useful_bytes if useful_bytes else None,
            "handshake_count": max((int(row.get("handshake_count") or 0) for row in self.cycles), default=0),
            "deadline_missed_count": sum(bool(row.get("deadline_missed")) for row in self.cycles),
            "battery_remaining_j": last.get("battery_remaining_j"),
            "battery_remaining_wh": last.get("battery_remaining_wh"),
            "battery_soc_percent": last.get("battery_soc_percent"),
            "estimated_battery_lifetime_hours": last.get("estimated_battery_lifetime_hours"),
            "estimated_battery_lifetime_days": last.get("estimated_battery_lifetime_days"),
            "energy_gateway_j": None,
            "energy_server_j": None,
            "energy_network_total_j": None,
            "infrastructure_energy_status": "not_calibrated_excluded_from_iot_autonomy",
        }

    def export_json(self, output_path: str | Path, *, metadata: dict[str, Any] | None = None) -> "PhysicalMetricsCollector":
        """Exporta os dados coletados para JSON.

        Parâmetros:
            output_path: Caminho do arquivo de saída.
            metadata: Metadados adicionais associados ao objeto.

        Retorna:
            A própria instância, permitindo encadear operações.
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(
                {
                    "metadata": metadata or {},
                    "summary": self.get_summary(),
                    "cycles": self.cycles,
                },
                handle,
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        return self

    def export_csv(self, output_path: str | Path) -> "PhysicalMetricsCollector":
        """Exporta os dados coletados para CSV.

        Parâmetros:
            output_path: Caminho do arquivo de saída.

        Retorna:
            A própria instância, permitindo encadear operações.
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        preferred = [
            "device_id",
            "crypto_mode",
            "sequence",
            "simulation_time_seconds",
            "cycle_duration_seconds",
            "active_cycle_duration_seconds",
            "sleep_duration_seconds",
            "wallclock_execution_time_seconds",
            "status",
            "delivered",
            *self.REQUIRED_FIELDS,
            "energy_per_delivered_message_j",
            "energy_per_application_byte_j",
            "handshake_energy_in_measurement_j",
            "amortized_handshake_energy_j",
            "crypto_energy_percent",
            "communication_energy_percent",
            "radio_energy_percent",
            "mqtt_publish_bytes",
            "mqtt_ack_bytes",
            "transport_overhead_bytes",
            "link_overhead_bytes",
            "link_latency_ms",
            "link_rtt_ms",
            "link_packet_loss_percent",
            "effective_bitrate_bps",
            "battery_nominal_voltage_v",
            "battery_capacity_mah",
            "battery_usable_fraction",
            "regulator_efficiency",
            "publication_interval_seconds",
            "regulator_quiescent_current_ua",
            "calibration_status",
            "messages_attempted",
            "messages_delivered",
            "messages_lost",
            "legacy_energy_fields_deprecated",
            "crypto_energy_cost",
            "total_energy_consumed",
            "payload",
            "energy_events",
            "crypto_operations",
        ]
        all_fields = set().union(*(row.keys() for row in self.cycles)) if self.cycles else set(preferred)
        fieldnames = list(dict.fromkeys(preferred + sorted(all_fields.difference(preferred))))
        rows: list[dict[str, Any]] = []
        for cycle in self.cycles:
            row = dict(cycle)
            for nested in ("payload", "energy_events", "crypto_operations"):
                if nested in row:
                    row[nested] = json.dumps(row[nested], ensure_ascii=False, separators=(",", ":"), default=str)
            rows.append(row)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return self
