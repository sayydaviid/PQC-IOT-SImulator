from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import random
import warnings

warnings.filterwarnings(
    "ignore",
    message="Unable to import Axes3D.*"
)

import networkx as nx
import matplotlib.pyplot as plt

from .logger import Logger
from .host import Host, IoTNode, GatewayNode, ApplicationServer, Packet
from .metrics import MetricsCollector
from .crypto import CryptoManager


@dataclass
class NetworkConfig:
    engine: str | None = None
    topology_name: str | None = None
    topology_params: dict[str, Any] = field(default_factory=dict)
    crypto_mode: str | None = None
    crypto_params: dict[str, Any] = field(default_factory=dict)
    protocol_name: str | None = None
    protocol_params: dict[str, Any] = field(default_factory=dict)
    metrics: list[str] = field(default_factory=list)


@dataclass
class TopologyData:
    nodes: list[str] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)


class Network:
    def __init__(
        self,
        name: str = "default_network",
        logger: Logger | None = None,
        verbose: bool = True
    ):
        self.name = name
        self.config = NetworkConfig()
        self.topology_data = TopologyData()
        self.graph = nx.Graph()
        self.is_built = False
        self.hosts: dict[str, Host] = {}

        self.engine = None
        self.runtime_engine = None

        self.logger = logger or Logger(name="Network", verbose=verbose)
        self.metrics_collector = MetricsCollector(logger=self.logger)
        self.crypto_manager = CryptoManager(
            mode="classical",
            logger=self.logger
        )

        self.logger.log(
            "Rede criada",
            data={"name": self.name},
            component="Network"
        )

    def set_runtime_engine(self, engine: Any):
        self.engine = engine
        self.runtime_engine = engine

        self.logger.log(
            "Engine de runtime conectada a Network",
            data={
                "engine": getattr(engine, "name", None),
                "engine_type": getattr(engine, "engine_type", None),
                "is_running": engine.is_running() if hasattr(engine, "is_running") else None
            },
            component="Network"
        )

        return self

    def collect_link_metrics(
        self,
        source: str,
        destination: str
    ):
        return self._collect_link_metrics_if_available(
            source=source,
            destination=destination
        )

    def _collect_link_metrics_if_available(
        self,
        source: str,
        destination: str
    ):
        engine = self.runtime_engine or self.engine

        if engine is None:
            return None

        if not hasattr(engine, "collect_link_metrics"):
            return None

        if hasattr(engine, "is_running") and not engine.is_running():
            return None

        try:
            try:
                link_metrics = engine.collect_link_metrics(
                    source=source,
                    destination=destination
                )

            except TypeError:
                link_metrics = engine.collect_link_metrics(
                    source,
                    destination
                )

            self.logger.log(
                "Metricas reais de link coletadas",
                data={
                    "source": source,
                    "destination": destination,
                    "link_metrics": link_metrics
                },
                component="Network"
            )

            return link_metrics

        except Exception as exc:
            self.logger.log(
                "Falha ao coletar metricas reais de link",
                data={
                    "source": source,
                    "destination": destination,
                    "error": str(exc)
                },
                component="Network"
            )

            return None

    def set_verbose(self, verbose: bool):
        self.logger.set_verbose(verbose)

        self.logger.log(
            "Modo verbose alterado",
            data={"verbose": verbose},
            component="Network"
        )

        return self

    def set_engine(self, engine_name: str):
        valid_engines = ["mininet", "mininet_wifi"]

        if engine_name not in valid_engines:
            raise ValueError(
                f"Engine invalida: {engine_name}. "
                f"Use uma destas: {valid_engines}"
            )

        self.config.engine = engine_name

        self.logger.log(
            "Engine definida",
            data={"engine": engine_name},
            component="Network"
        )

        return self

    def set_ready_topology(self, topology_name: str, *args, **kwargs):
        self.logger.log(
            "Iniciando criacao da topologia",
            data={
                "topology": topology_name,
                "args": args,
                "kwargs": kwargs
            },
            component="Network"
        )

        self.config.topology_name = topology_name

        params = self._normalize_topology_params(
            topology_name=topology_name,
            args=args,
            kwargs=kwargs
        )

        self.config.topology_params = params

        self.topology_data = self._build_ready_topology(
            topology_name=topology_name,
            params=params
        )

        self.hosts = {}
        self.is_built = False
        self.metrics_collector.clear()

        self._sync_graph()

        self.logger.log(
            "Topologia criada com sucesso",
            data={
                "topology": topology_name,
                "params": params,
                "nodes": len(self.topology_data.nodes),
                "links": len(self.topology_data.links)
            },
            component="Network"
        )

        return self

    def set_crypto_mode(self, mode: str, **params):
        valid_modes = ["classical", "hybrid", "pqc"]

        if mode not in valid_modes:
            raise ValueError(
                f"Modo criptografico invalido: {mode}. "
                f"Use um destes: {valid_modes}"
            )

        self.config.crypto_mode = mode
        self.config.crypto_params = params

        self.crypto_manager.configure(
            mode=mode,
            kem=params.get("kem"),
            signature=params.get("signature"),
            pqc_signature=params.get("pqc_signature"),
            classical_signature=params.get("classical_signature"),
            use_classical_signature=params.get("use_classical_signature"),
            use_pqc_signature=params.get("use_pqc_signature")
        )

        for host in self.hosts.values():
            host.set_crypto_mode(mode)

        self.logger.log(
            "Modo criptografico definido",
            data={
                "mode": mode,
                "params": params,
                "crypto_config": self.crypto_manager.get_config(),
                "hosts_updated": len(self.hosts)
            },
            component="Network"
        )

        return self

    def set_crypto_algorithm(self, **params):
        self.config.crypto_params.update(params)

        self.crypto_manager.configure(
            kem=params.get("kem"),
            signature=params.get("signature"),
            pqc_signature=params.get("pqc_signature"),
            classical_signature=params.get("classical_signature"),
            use_classical_signature=params.get("use_classical_signature"),
            use_pqc_signature=params.get("use_pqc_signature")
        )

        self.logger.log(
            "Parametros criptograficos atualizados",
            data={
                "params": params,
                "crypto_config": self.crypto_manager.get_config()
            },
            component="Network"
        )

        return self

    def set_protocol(self, protocol_name: str, **params):
        valid_protocols = ["mqtt", "coap", "http"]

        if protocol_name not in valid_protocols:
            raise ValueError(
                f"Protocolo invalido: {protocol_name}. "
                f"Use um destes: {valid_protocols}"
            )

        self.config.protocol_name = protocol_name
        self.config.protocol_params = params

        for host in self.hosts.values():
            host.set_protocol(protocol_name)

        self.logger.log(
            "Protocolo definido",
            data={
                "protocol": protocol_name,
                "params": params,
                "hosts_updated": len(self.hosts)
            },
            component="Network"
        )

        return self

    def set_metrics(self, metrics: list[str]):
        valid_metrics = [
            "latency",
            "jitter",
            "packet_loss",
            "throughput",
            "pdr",
            "energy",
            "crypto_time",
            "message_overhead",
            "link_metrics",
            "rtt",
            "real_latency"
        ]

        invalid_metrics = [
            metric for metric in metrics
            if metric not in valid_metrics
        ]

        if invalid_metrics:
            raise ValueError(
                f"Metricas invalidas: {invalid_metrics}. "
                f"Use apenas estas: {valid_metrics}"
            )

        self.config.metrics = metrics

        self.logger.log(
            "Metricas definidas",
            data={"metrics": metrics},
            component="Network"
        )

        return self

    def add_node(self, node_id: str):
        if node_id not in self.topology_data.nodes:
            self.topology_data.nodes.append(node_id)

        self._sync_graph()

        if self.hosts:
            self.hosts[node_id] = self._create_host_from_node(node_id)

        self.logger.log(
            "No adicionado",
            data={"node_id": node_id},
            component="Network"
        )

        return self

    def add_link(self, source: str, target: str):
        if source not in self.topology_data.nodes:
            self.topology_data.nodes.append(source)

        if target not in self.topology_data.nodes:
            self.topology_data.nodes.append(target)

        link = self._normalize_link(source, target)

        if link not in self.topology_data.links:
            self.topology_data.links.append(link)

        self._sync_graph()

        if self.hosts:
            if source not in self.hosts:
                self.hosts[source] = self._create_host_from_node(source)

            if target not in self.hosts:
                self.hosts[target] = self._create_host_from_node(target)

        self.logger.log(
            "Link adicionado",
            data={
                "source": source,
                "target": target
            },
            component="Network"
        )

        return self

    def create_hosts(self):
        if not self.topology_data.nodes:
            raise RuntimeError("Defina uma topologia antes de criar os hosts.")

        self.logger.log(
            "Iniciando criacao dos hosts",
            data={
                "total_nodes": len(self.topology_data.nodes),
                "protocol": self.config.protocol_name,
                "crypto_mode": self.config.crypto_mode
            },
            component="Network"
        )

        self.hosts = {}

        for node_id in self.topology_data.nodes:
            self.hosts[node_id] = self._create_host_from_node(node_id)

        self.logger.log(
            "Hosts criados com sucesso",
            data={
                "hosts": list(self.hosts.keys()),
                "total_hosts": len(self.hosts)
            },
            component="Network"
        )

        return self

    def get_host(self, host_id: str):
        if not self.hosts:
            self.create_hosts()

        if host_id not in self.hosts:
            raise KeyError(f"Host nao encontrado: {host_id}")

        return self.hosts[host_id]

    def show_hosts(self):
        if not self.hosts:
            self.logger.log(
                "Nenhum host criado ainda. Criando hosts automaticamente.",
                component="Network"
            )

            self.create_hosts()

        summary = {
            host_id: host.get_status()
            for host_id, host in self.hosts.items()
        }

        self.logger.log(
            "Resumo dos hosts solicitado",
            data={
                "total_hosts": len(summary)
            },
            component="Network"
        )

        return summary

    def send(
        self,
        source: str,
        destination: str,
        payload: dict[str, Any],
        link_metrics: dict[str, Any] | None = None
    ):
        if not self.hosts:
            self.create_hosts()

        if source not in self.hosts:
            raise KeyError(f"Host de origem nao encontrado: {source}")

        if destination not in self.hosts:
            raise KeyError(f"Host de destino nao encontrado: {destination}")

        if source not in self.graph.nodes:
            raise KeyError(f"No de origem nao existe no grafo: {source}")

        if destination not in self.graph.nodes:
            raise KeyError(f"No de destino nao existe no grafo: {destination}")

        baseline_energy = self.metrics_collector.snapshot_energy(self.hosts)
        timer_start, started_at = self.metrics_collector.start_timer()

        source_host = self.get_host(source)

        crypto_result = self.crypto_manager.protect(payload)

        source_host.consume_energy(
            amount=crypto_result.energy_cost,
            reason="crypto_protect"
        )

        protected_payload = crypto_result.payload

        if source == destination:
            host = self.get_host(source)

            packet = Packet(
                source=source,
                destination=destination,
                payload=protected_payload,
                protocol=self.config.protocol_name,
                crypto_mode=self.config.crypto_mode
            )

            result = self._deliver_to_destination(
                host=host,
                packet=packet
            )

            duration_seconds, finished_at = self.metrics_collector.finish_timer(
                timer_start
            )

            if link_metrics is None:
                link_metrics = self._collect_link_metrics_if_available(
                    source=source,
                    destination=destination
                )

            send_result = {
                "status": "delivered",
                "source": source,
                "destination": destination,
                "path": [source],
                "packet": packet,
                "result": result,
                "crypto": crypto_result.to_dict(),
                "link_metrics": link_metrics
            }

            self.metrics_collector.record_from_send_result(
                send_result=send_result,
                hosts=self.hosts,
                payload=protected_payload,
                baseline_energy=baseline_energy,
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=duration_seconds,
                link_metrics=link_metrics
            )

            self.logger.log(
                "Envio local concluido",
                data={
                    "source": source,
                    "destination": destination,
                    "path": [source],
                    "crypto_mode": crypto_result.mode,
                    "crypto_backend": crypto_result.backend,
                    "crypto_overhead_bytes": crypto_result.overhead_bytes,
                    "crypto_time_seconds": crypto_result.operation_time_seconds,
                    "crypto_energy_cost": crypto_result.energy_cost,
                    "link_metrics": link_metrics
                },
                component="Network"
            )

            return send_result

        try:
            path = nx.shortest_path(
                self.graph,
                source=source,
                target=destination
            )

        except nx.NetworkXNoPath:
            duration_seconds, finished_at = self.metrics_collector.finish_timer(
                timer_start
            )

            if link_metrics is None:
                link_metrics = self._collect_link_metrics_if_available(
                    source=source,
                    destination=destination
                )

            self.metrics_collector.record_transmission(
                source=source,
                destination=destination,
                status="not_delivered",
                path=[],
                protocol=self.config.protocol_name,
                crypto_mode=self.config.crypto_mode,
                payload=protected_payload,
                hosts=self.hosts,
                baseline_energy=baseline_energy,
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=duration_seconds,
                crypto=crypto_result.to_dict(),
                result={
                    "reason": "no_path",
                    "crypto": crypto_result.to_dict(),
                    "link_metrics": link_metrics
                }
            )

            self.logger.log(
                "Envio nao concluido. Caminho inexistente.",
                data={
                    "source": source,
                    "destination": destination,
                    "crypto_mode": crypto_result.mode,
                    "crypto_backend": crypto_result.backend,
                    "link_metrics": link_metrics
                },
                component="Network"
            )

            return {
                "status": "not_delivered",
                "source": source,
                "destination": destination,
                "path": [],
                "packet": None,
                "result": {
                    "reason": "no_path"
                },
                "crypto": crypto_result.to_dict(),
                "link_metrics": link_metrics
            }

        self.logger.log(
            "Caminho calculado para envio",
            data={
                "source": source,
                "destination": destination,
                "path": path,
                "hops": len(path) - 1
            },
            component="Network"
        )

        packet = source_host.send_data(
            destination=destination,
            payload=protected_payload,
            protocol=self.config.protocol_name,
            crypto_mode=self.config.crypto_mode
        )

        for current_node in path[1:]:
            current_host = self.get_host(current_node)
            is_destination = current_node == destination

            if is_destination:
                result = self._deliver_to_destination(
                    host=current_host,
                    packet=packet
                )

                duration_seconds, finished_at = self.metrics_collector.finish_timer(
                    timer_start
                )

                if link_metrics is None:
                    link_metrics = self._collect_link_metrics_if_available(
                        source=source,
                        destination=destination
                    )

                send_result = {
                    "status": "delivered",
                    "source": source,
                    "destination": destination,
                    "path": path,
                    "packet": packet,
                    "result": result,
                    "crypto": crypto_result.to_dict(),
                    "link_metrics": link_metrics
                }

                self.metrics_collector.record_from_send_result(
                    send_result=send_result,
                    hosts=self.hosts,
                    payload=protected_payload,
                    baseline_energy=baseline_energy,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_seconds=duration_seconds,
                    link_metrics=link_metrics
                )

                self.logger.log(
                    "Envio concluido",
                    data={
                        "source": source,
                        "destination": destination,
                        "path": path,
                        "hops": len(path) - 1,
                        "crypto_mode": crypto_result.mode,
                        "crypto_backend": crypto_result.backend,
                        "crypto_overhead_bytes": crypto_result.overhead_bytes,
                        "crypto_time_seconds": crypto_result.operation_time_seconds,
                        "crypto_energy_cost": crypto_result.energy_cost,
                        "link_metrics": link_metrics
                    },
                    component="Network"
                )

                return send_result

            current_host.receive_data(packet)

            packet = self._forward_packet(
                host=current_host,
                packet=packet,
                destination=destination
            )

        duration_seconds, finished_at = self.metrics_collector.finish_timer(
            timer_start
        )

        if link_metrics is None:
            link_metrics = self._collect_link_metrics_if_available(
                source=source,
                destination=destination
            )

        send_result = {
            "status": "not_delivered",
            "source": source,
            "destination": destination,
            "path": path,
            "packet": packet,
            "result": None,
            "crypto": crypto_result.to_dict(),
            "link_metrics": link_metrics
        }

        self.metrics_collector.record_from_send_result(
            send_result=send_result,
            hosts=self.hosts,
            payload=protected_payload,
            baseline_energy=baseline_energy,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration_seconds,
            link_metrics=link_metrics
        )

        self.logger.log(
            "Envio nao concluido",
            data={
                "source": source,
                "destination": destination,
                "path": path,
                "crypto_mode": crypto_result.mode,
                "crypto_backend": crypto_result.backend,
                "link_metrics": link_metrics
            },
            component="Network"
        )

        return send_result

    def metrics(self):
        return self.metrics_collector.get_summary()

    def transmissions(self):
        return self.metrics_collector.get_transmissions()

    def last_transmission(self):
        return self.metrics_collector.get_last_transmission()

    def energy_by_host(self):
        return self.metrics_collector.get_energy_by_host()

    def delivery_summary(self):
        return self.metrics_collector.get_delivery_summary()

    def export_metrics_json(self, output_path: str):
        return self.metrics_collector.export_json(output_path)

    def export_metrics_csv(self, output_path: str):
        return self.metrics_collector.export_csv(output_path)

    def build(self):
        self.logger.log(
            "Iniciando build da rede",
            component="Network"
        )

        self._validate_before_build()

        if not self.hosts:
            self.create_hosts()

        self.is_built = True

        self.logger.log(
            "Build da rede concluido",
            data={
                "engine": self.config.engine,
                "topology": self.config.topology_name,
                "crypto": self.config.crypto_mode,
                "protocol": self.config.protocol_name,
                "hosts": len(self.hosts)
            },
            component="Network"
        )

        return self

    def run(self):
        self.logger.log(
            "Execucao solicitada",
            component="Network"
        )

        if not self.is_built:
            self.build()

        self.logger.log(
            "Simulacao iniciada",
            data={
                "network": self.name,
                "nodes": len(self.topology_data.nodes),
                "links": len(self.topology_data.links),
                "hosts": len(self.hosts)
            },
            component="Network"
        )

        self.logger.log(
            "Simulacao finalizada",
            data={"status": "finished"},
            component="Network"
        )

        return self

    def draw(self, output_path: str | None = None, show: bool = True):
        self.logger.log(
            "Iniciando desenho da topologia",
            component="Network"
        )

        if not self.topology_data.nodes:
            raise RuntimeError("Nenhuma topologia foi definida.")

        self._sync_graph()

        plt.figure(figsize=(10, 7))

        pos = None
        rows = self.config.topology_params.get("rows")
        cols = self.config.topology_params.get("cols")

        layout_graph = self.graph.copy()

        for source, target in layout_graph.edges():
            layout_graph[source][target]["layout_weight"] = 1.0

        iot_nodes = self._ordered_iot_nodes()

        for current, neighbor in zip(iot_nodes, iot_nodes[1:]):
            if layout_graph.has_edge(current, neighbor):
                layout_graph[current][neighbor]["layout_weight"] = 1.6
            else:
                layout_graph.add_edge(
                    current,
                    neighbor,
                    layout_weight=0.25
                )

        if self.config.topology_name == "grade" and isinstance(rows, int) and isinstance(cols, int):
            expected_nodes = rows * cols

            if expected_nodes == len(self.topology_data.nodes):
                initial_pos = {}
                jitter = 0.18

                for index, node in enumerate(self.topology_data.nodes):
                    row = index // cols
                    col = index % cols

                    initial_pos[node] = (
                        float(col) + random.uniform(-jitter, jitter),
                        float(-row) + random.uniform(-jitter, jitter)
                    )

                pos = nx.spring_layout(
                    layout_graph,
                    pos=initial_pos,
                    weight="layout_weight",
                    iterations=50
                )

        if pos is None:
            pos = nx.spring_layout(
                layout_graph,
                weight="layout_weight"
            )

        node_colors = []

        for node in self.graph.nodes():
            if node.startswith("gateway"):
                node_colors.append("#f59e0b")
            elif node.startswith("server"):
                node_colors.append("#ef4444")
            else:
                node_colors.append("#3b82f6")

        nx.draw(
            self.graph,
            pos,
            with_labels=True,
            node_size=1300,
            font_size=8,
            node_color=node_colors
        )

        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(path, bbox_inches="tight")

            self.logger.log(
                "Imagem da topologia salva",
                data={"output_path": output_path},
                component="Network"
            )

        self.logger.log(
            "Desenho OK",
            data={"output_path": output_path},
            component="Network"
        )

        if show:
            plt.show()
        else:
            plt.close()

        return self

    def summary(self):
        data = {
            "name": self.name,
            "engine": self.config.engine,
            "runtime_engine": getattr(self.runtime_engine, "name", None),
            "runtime_engine_type": getattr(self.runtime_engine, "engine_type", None),
            "topology": self.config.topology_name,
            "topology_params": self.config.topology_params,
            "crypto_mode": self.config.crypto_mode,
            "crypto_params": self.config.crypto_params,
            "crypto_config": self.crypto_manager.get_config(),
            "protocol": self.config.protocol_name,
            "protocol_params": self.config.protocol_params,
            "metrics": self.config.metrics,
            "nodes": self.topology_data.nodes,
            "links": self.topology_data.links,
            "hosts": list(self.hosts.keys()),
            "total_nodes": len(self.topology_data.nodes),
            "total_links": len(self.topology_data.links),
            "total_hosts": len(self.hosts)
        }

        self.logger.log(
            "Resumo da rede solicitado",
            data={
                "total_nodes": data["total_nodes"],
                "total_links": data["total_links"],
                "total_hosts": data["total_hosts"],
                "runtime_engine": data["runtime_engine"]
            },
            component="Network"
        )

        return data

    def get_logs(self):
        return self.logger.get_events()

    def _deliver_to_destination(
        self,
        host: Host,
        packet: Packet
    ):
        if isinstance(host, ApplicationServer):
            return host.process_data(packet)

        return host.receive_data(packet)

    def _forward_packet(
        self,
        host: Host,
        packet: Packet,
        destination: str
    ):
        if isinstance(host, GatewayNode):
            return host.forward_data(
                packet=packet,
                destination=destination
            )

        host.forwarded_packets.append(packet)

        host.consume_energy(
            amount=0.08,
            reason="forward_data"
        )

        self.logger.log(
            "Pacote encaminhado por no intermediario",
            data={
                "host_id": host.host_id,
                "source": packet.source,
                "destination": destination,
                "protocol": packet.protocol,
                "crypto_mode": packet.crypto_mode
            },
            component=host.host_id
        )

        return Packet(
            source=packet.source,
            destination=destination,
            payload=packet.payload,
            protocol=packet.protocol,
            crypto_mode=packet.crypto_mode
        )

    def _create_host_from_node(self, node_id: str):
        if node_id.startswith("gateway"):
            return GatewayNode(
                host_id=node_id,
                logger=self.logger,
                protocol=self.config.protocol_name,
                crypto_mode=self.config.crypto_mode
            )

        if node_id.startswith("server"):
            return ApplicationServer(
                host_id=node_id,
                logger=self.logger,
                protocol=self.config.protocol_name,
                crypto_mode=self.config.crypto_mode
            )

        return IoTNode(
            host_id=node_id,
            logger=self.logger,
            sensor_type="generic",
            protocol=self.config.protocol_name,
            crypto_mode=self.config.crypto_mode
        )

    def _normalize_topology_params(
        self,
        topology_name: str,
        args: tuple,
        kwargs: dict[str, Any]
    ):
        params = dict(kwargs)

        if topology_name == "grade":
            if len(args) == 2:
                params["rows"] = args[0]
                params["cols"] = args[1]

            params.setdefault("rows", 3)
            params.setdefault("cols", 3)

            params["rows"] = self._validate_positive_int(params["rows"], "rows")
            params["cols"] = self._validate_positive_int(params["cols"], "cols")

        elif topology_name == "star":
            if len(args) == 1:
                params["nodes"] = args[0]

            params.setdefault("nodes", 5)
            params["nodes"] = self._validate_positive_int(params["nodes"], "nodes")

        elif topology_name == "tree":
            if len(args) == 2:
                params["levels"] = args[0]
                params["children"] = args[1]

            params.setdefault("levels", 2)
            params.setdefault("children", 2)

            params["levels"] = self._validate_positive_int(
                params["levels"],
                "levels"
            )

            params["children"] = self._validate_positive_int(
                params["children"],
                "children"
            )

        elif topology_name == "mesh":
            if len(args) == 1:
                params["nodes"] = args[0]

            params.setdefault("nodes", 5)
            params["nodes"] = self._validate_positive_int(params["nodes"], "nodes")

        else:
            raise ValueError(f"Topologia nao suportada: {topology_name}")

        return params

    def _build_ready_topology(
        self,
        topology_name: str,
        params: dict[str, Any]
    ):
        if topology_name == "grade":
            return self._build_grade_topology(
                rows=params["rows"],
                cols=params["cols"]
            )

        if topology_name == "star":
            return self._build_star_topology(
                nodes=params["nodes"]
            )

        if topology_name == "tree":
            return self._build_tree_topology(
                levels=params["levels"],
                children=params["children"]
            )

        if topology_name == "mesh":
            return self._build_mesh_topology(
                nodes=params["nodes"]
            )

        raise ValueError(f"Topologia nao suportada: {topology_name}")

    def _build_grade_topology(self, rows: int, cols: int):
        self.logger.log(
            "Gerando topologia em grade",
            data={
                "rows": rows,
                "cols": cols
            },
            component="Network"
        )

        total_slots = rows * cols

        if total_slots < 3:
            raise ValueError(
                "Topologia grade precisa de pelo menos 3 nos "
                "para incluir gateway, server e um IoT."
            )

        nodes = []

        gateway = "gateway_1"
        server = "server_1"

        iot_count = total_slots - 2
        sequence = [f"iot_{index}" for index in range(1, iot_count + 1)]
        sequence.extend([gateway, server])

        snake_slots = []

        for row in range(rows):
            if row % 2 == 0:
                cols_order = range(cols)
            else:
                cols_order = range(cols - 1, -1, -1)

            for col in cols_order:
                snake_slots.append((row, col))

        grid = [["" for _ in range(cols)] for _ in range(rows)]

        for index, (row, col) in enumerate(snake_slots):
            grid[row][col] = sequence[index]

        for row in range(rows):
            for col in range(cols):
                nodes.append(grid[row][col])

        links_set = set()

        def add_grid_link(source: str, target: str):
            if source == target:
                return

            links_set.add(tuple(sorted((source, target))))

        for current, neighbor in zip(sequence, sequence[1:]):
            add_grid_link(current, neighbor)

        for row in range(rows):
            for col in range(cols):
                current = grid[row][col]

                if col + 1 < cols:
                    add_grid_link(current, grid[row][col + 1])

                if row + 1 < rows:
                    add_grid_link(current, grid[row + 1][col])

        links = list(links_set)

        return TopologyData(
            nodes=nodes,
            links=links
        )

    def _build_star_topology(self, nodes: int):
        self.logger.log(
            "Gerando topologia estrela",
            data={"nodes": nodes},
            component="Network"
        )

        topology_nodes = []
        links = []

        gateway = "gateway_1"
        server = "server_1"

        topology_nodes.append(gateway)
        topology_nodes.append(server)

        links.append((gateway, server))

        for index in range(1, nodes + 1):
            node_id = f"iot_{index}"
            topology_nodes.append(node_id)
            links.append((node_id, gateway))

        return TopologyData(
            nodes=topology_nodes,
            links=links
        )

    def _build_tree_topology(self, levels: int, children: int):
        self.logger.log(
            "Gerando topologia arvore",
            data={
                "levels": levels,
                "children": children
            },
            component="Network"
        )

        nodes = ["server_1", "gateway_1"]
        links = [("server_1", "gateway_1")]

        current_level = ["gateway_1"]
        counter = 1

        for level in range(levels):
            next_level = []

            for parent in current_level:
                for _ in range(children):
                    node_id = f"iot_{counter}"
                    counter += 1

                    nodes.append(node_id)
                    links.append((parent, node_id))
                    next_level.append(node_id)

            current_level = next_level

        return TopologyData(
            nodes=nodes,
            links=links
        )

    def _build_mesh_topology(self, nodes: int):
        self.logger.log(
            "Gerando topologia malha",
            data={"nodes": nodes},
            component="Network"
        )

        topology_nodes = ["gateway_1", "server_1"]
        links = [("gateway_1", "server_1")]

        for index in range(1, nodes + 1):
            node_id = f"iot_{index}"
            topology_nodes.append(node_id)
            links.append((node_id, "gateway_1"))

        for index in range(1, nodes + 1):
            current = f"iot_{index}"

            for neighbor_index in range(index + 1, nodes + 1):
                neighbor = f"iot_{neighbor_index}"
                links.append((current, neighbor))

        return TopologyData(
            nodes=topology_nodes,
            links=links
        )

    def _sync_graph(self):
        self.graph.clear()

        normalized_links = []
        seen_links = set()

        for source, target in self.topology_data.links:
            normalized = self._normalize_link(source, target)

            if normalized not in seen_links:
                seen_links.add(normalized)
                normalized_links.append(normalized)

        self.topology_data.links = normalized_links

        for node in self.topology_data.nodes:
            self.graph.add_node(node)

        for source, target in self.topology_data.links:
            self.graph.add_edge(source, target)

        self.logger.log(
            "Grafo sincronizado",
            data={
                "nodes": self.graph.number_of_nodes(),
                "edges": self.graph.number_of_edges()
            },
            component="Network"
        )

    def _normalize_link(self, source: str, target: str):
        if source == target:
            raise ValueError("Nao e permitido criar link com o mesmo no de origem e destino.")

        return tuple(sorted((source, target)))

    def _validate_positive_int(self, value: Any, param_name: str):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(
                f"Parametro '{param_name}' invalido: {value}. "
                "Use um inteiro maior que zero."
            )

        return value

    def _validate_before_build(self):
        if not self.config.engine:
            self.config.engine = "mininet_wifi"

            self.logger.log(
                "Engine padrao aplicada",
                data={"engine": self.config.engine},
                component="Network"
            )

        if not self.config.topology_name:
            raise RuntimeError("Defina uma topologia antes de executar a rede.")

        if not self.config.crypto_mode:
            self.config.crypto_mode = "classical"

            self.crypto_manager.configure(
                mode=self.config.crypto_mode
            )

            self.logger.log(
                "Modo criptografico padrao aplicado",
                data={"crypto": self.config.crypto_mode},
                component="Network"
            )

        if not self.config.protocol_name:
            self.config.protocol_name = "mqtt"

            self.logger.log(
                "Protocolo padrao aplicado",
                data={"protocol": self.config.protocol_name},
                component="Network"
            )

        if not self.config.metrics:
            self.config.metrics = [
                "latency",
                "packet_loss",
                "pdr",
                "energy",
                "crypto_time",
                "message_overhead",
                "link_metrics"
            ]

            self.logger.log(
                "Metricas padrao aplicadas",
                data={"metrics": self.config.metrics},
                component="Network"
            )

    def _ordered_iot_nodes(self):
        def sort_key(node_name: str):
            if not node_name.startswith("iot_"):
                return float("inf")

            suffix = node_name.split("iot_", maxsplit=1)[1]

            if suffix.isdigit():
                return int(suffix)

            return float("inf")

        return sorted(
            [node for node in self.graph.nodes() if node.startswith("iot_")],
            key=sort_key
        )