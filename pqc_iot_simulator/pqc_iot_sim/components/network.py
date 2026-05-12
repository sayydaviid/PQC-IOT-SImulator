from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import random

import networkx as nx

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
        verbose: bool = True,
        log_level: str = "info"
    ):
        valid_log_levels = ["silent", "info", "debug"]

        if log_level not in valid_log_levels:
            raise ValueError(
                f"Nivel de log invalido: {log_level}. "
                f"Use um destes: {valid_log_levels}"
            )

        self.name = name
        self.log_level = log_level

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

        self._log_info(
            f"Rede criada e pronta para configuracao"
        )

    def _crypto_label(self, crypto_mode: str | None):
        labels = {
            "classical": "classica",
            "hybrid": "hibrida",
            "pqc": "pos quantica"
        }

        if crypto_mode is None:
            return "nao definida"

        return labels.get(crypto_mode, crypto_mode)

    def _format_path(self, path: list[str]):
        if not path:
            return "sem caminho"

        return " para ".join(path)

    def _format_count(self, value: int, singular: str, plural: str):
        if value == 1:
            return f"{value} {singular}"

        return f"{value} {plural}"

    def _log_info(
        self,
        message: str,
        data: dict[str, Any] | None = None,
        component: str = "Network"
    ):
        if self.log_level in ["info", "debug"]:
            self.logger.log(
                message,
                data=data or {},
                component=component
            )

    def _log_debug(
        self,
        message: str,
        data: dict[str, Any] | None = None,
        component: str = "Network"
    ):
        if self.log_level == "debug":
            self.logger.log(
                message,
                data=data or {},
                component=component
            )

    def _log_error(
        self,
        message: str,
        data: dict[str, Any] | None = None,
        component: str = "Network"
    ):
        if self.log_level != "silent":
            self.logger.log(
                message,
                data=data or {},
                component=component
            )

    def set_runtime_engine(self, engine: Any):
        self.engine = engine
        self.runtime_engine = engine

        engine_name = getattr(engine, "name", None) or "sem nome"
        engine_type = getattr(engine, "engine_type", None) or "tipo nao informado"

        self._log_info(
            f"Engine de runtime {engine_name} conectada a rede, tipo: {engine_type}"
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

            latency = link_metrics.get("latency_ms") if isinstance(link_metrics, dict) else None
            loss = link_metrics.get("packet_loss_percent") if isinstance(link_metrics, dict) else None

            self._log_debug(
                (
                    f"Metricas reais de link coletadas entre {source} e {destination}, "
                    f"latencia: {latency} ms, perda de pacotes: {loss}%"
                )
            )

            return link_metrics

        except Exception as exc:
            self._log_debug(
                f"Nao foi possivel coletar metricas reais de link entre {source} e {destination}, erro: {exc}"
            )

            return None

    def set_verbose(self, verbose: bool):
        self.logger.set_verbose(verbose)

        self._log_debug(
            f"Modo verbose alterado para {verbose}"
        )

        return self

    def set_ready_topology(self, topology_name: str, *args, **kwargs):
        self._log_debug(
            f"Preparando topologia {topology_name}"
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

        self._log_info(
            (
                f"Topologia {topology_name} criada com sucesso, "
                f"{self._format_count(len(self.topology_data.nodes), 'no', 'nos')} "
                f"e {self._format_count(len(self.topology_data.links), 'link', 'links')}"
            )
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

        self._log_info(
            f"Metricas configuradas: {', '.join(metrics)}"
        )

        return self

    def add_node(self, node_id: str):
        if node_id not in self.topology_data.nodes:
            self.topology_data.nodes.append(node_id)

        self._sync_graph()

        if self.hosts:
            self.hosts[node_id] = self._create_host_from_node(node_id)

        self._log_info(
            f"No {node_id} adicionado a rede"
        )

        return self

    def create_hosts(self):
        if not self.topology_data.nodes:
            raise RuntimeError("Defina uma topologia antes de criar os hosts.")

        self._log_debug(
            f"Criando hosts para {len(self.topology_data.nodes)} nos da topologia"
        )

        self.hosts = {}

        for node_id in self.topology_data.nodes:
            self.hosts[node_id] = self._create_host_from_node(node_id)

        self._log_info(
            f"{len(self.hosts)} hosts criados com sucesso"
        )

        return self

    def get_host(self, host_id: str):
        if not self.hosts:
            self._log_debug(
                "Hosts ainda nao existiam, criando automaticamente"
            )
            self.create_hosts()

        if host_id not in self.hosts:
            raise KeyError(f"Host nao encontrado: {host_id}")

        return self.hosts[host_id]

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

        self._log_info(
            (
                f"Enviando pacote de {source} para {destination}, "
                f"protocolo: {self.config.protocol_name}, "
                f"criptografia: {self._crypto_label(self.config.crypto_mode)}"
            )
        )

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

            packet = host.send_data(
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

            self._log_info(
                f"Pacote entregue localmente em {source}"
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

            self._log_error(
                f"Pacote nao entregue porque nao existe caminho entre {source} e {destination}"
            )

            return {
                "status": "not_delivered",
                "source": source,
                "destination": destination,
                "path": [],
                "packet": None,
                "protocol": self.config.protocol_name,
                "crypto_mode": self.config.crypto_mode,
                "result": {
                    "reason": "no_path"
                },
                "crypto": crypto_result.to_dict(),
                "link_metrics": link_metrics
            }

        self._log_debug(
            f"Caminho calculado para envio: {self._format_path(path)}"
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

                self._log_info(
                    (
                        f"Pacote entregue com sucesso, "
                        f"saltos: {len(path) - 1}, "
                        f"caminho: {self._format_path(path)}"
                    )
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

        self._log_error(
            f"Pacote nao entregue, caminho tentado: {self._format_path(path)}"
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

    def export_metrics_json(self, output_path: str):
        return self.metrics_collector.export_json(output_path)

    def export_metrics_csv(self, output_path: str):
        return self.metrics_collector.export_csv(output_path)

    def build(self):
        self._log_debug(
            "Preparando build da rede"
        )

        self._validate_before_build()

        if not self.hosts:
            self.create_hosts()

        self.is_built = True

        self._log_info(
            (
                f"Rede pronta para execucao, "
                f"engine: {self.config.engine}, "
                f"topologia: {self.config.topology_name}, "
                f"criptografia: {self._crypto_label(self.config.crypto_mode)}, "
                f"protocolo: {self.config.protocol_name}, "
                f"hosts: {len(self.hosts)}"
            )
        )

        return self

    def run(self):
        self._log_debug(
            "Execucao solicitada"
        )

        if not self.is_built:
            self.build()

        self._log_info(
            (
                f"Execucao concluida no modo interno, "
                f"rede: {self.name}, "
                f"nos: {len(self.topology_data.nodes)}, "
                f"links: {len(self.topology_data.links)}, "
                f"hosts: {len(self.hosts)}"
            )
        )

        return self

    def draw(self, output_path: str | None = None, show: bool = True):
        try:
            import warnings

            warnings.filterwarnings(
                "ignore",
                message="Unable to import Axes3D.*"
            )

            import matplotlib.pyplot as plt
        except Exception as exc:
            raise RuntimeError(
                "Matplotlib nao esta disponivel/compativel neste ambiente. "
                "Instale/atualize matplotlib (e numpy) para usar Network.draw()."
            ) from exc

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

            self._log_info(
                f"Imagem da topologia salva em {output_path}"
            )

        self._log_debug(
            "Desenho da topologia finalizado"
        )

        if show:
            plt.show()
        else:
            plt.close()

        return self

    def summary(self):
        return {
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

        self._log_debug(
            (
                f"{host.host_id} encaminhou pacote de {packet.source} "
                f"para {destination}, protocolo: {packet.protocol}, "
                f"criptografia: {self._crypto_label(packet.crypto_mode)}"
            ),
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
            params.setdefault("snake_path", False)

            params["rows"] = self._validate_positive_int(params["rows"], "rows")
            params["cols"] = self._validate_positive_int(params["cols"], "cols")
            params["snake_path"] = self._validate_bool(
                params["snake_path"],
                "snake_path"
            )

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
            params.setdefault("mesh_degree", None)

            if params["mesh_degree"] is not None:
                params["mesh_degree"] = self._validate_positive_int(
                    params["mesh_degree"],
                    "mesh_degree"
                )

                if params["mesh_degree"] >= params["nodes"]:
                    params["mesh_degree"] = params["nodes"] - 1
            else:
                if params["nodes"] > 12:
                    params["mesh_degree"] = min(params["nodes"] - 1, 6)

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
                cols=params["cols"],
                snake_path=params["snake_path"]
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
                nodes=params["nodes"],
                mesh_degree=params.get("mesh_degree")
            )

        raise ValueError(f"Topologia nao suportada: {topology_name}")

    def _build_grade_topology(self, rows: int, cols: int, snake_path: bool):
        self._log_debug(
            f"Gerando topologia em grade com {rows} linhas e {cols} colunas"
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

        if snake_path:
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
        self._log_debug(
            f"Gerando topologia estrela com {nodes} nos IoT"
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
        self._log_debug(
            f"Gerando topologia em arvore com {levels} niveis e {children} filhos por no"
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

    def _build_mesh_topology(self, nodes: int, mesh_degree: int | None = None):
        self._log_debug(
            f"Gerando topologia em malha com {nodes} nos IoT"
        )

        topology_nodes = ["gateway_1", "server_1"]
        links = [("gateway_1", "server_1")]

        for index in range(1, nodes + 1):
            node_id = f"iot_{index}"
            topology_nodes.append(node_id)
            links.append((node_id, "gateway_1"))

        neighbor_limit = nodes - 1 if mesh_degree is None else mesh_degree

        for index in range(1, nodes + 1):
            current = f"iot_{index}"
            max_neighbor = min(nodes, index + neighbor_limit)

            for neighbor_index in range(index + 1, max_neighbor + 1):
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

        self._log_debug(
            (
                f"Grafo interno sincronizado, "
                f"nos: {self.graph.number_of_nodes()}, "
                f"arestas: {self.graph.number_of_edges()}"
            )
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

    def _validate_bool(self, value: Any, param_name: str):
        if not isinstance(value, bool):
            raise ValueError(
                f"Parametro '{param_name}' invalido: {value}. "
                "Use true ou false."
            )

        return value

    def _validate_before_build(self):
        defaults_applied = []

        if not self.config.engine:
            self.config.engine = "mininet_wifi"
            defaults_applied.append(f"engine: {self.config.engine}")

        if not self.config.topology_name:
            raise RuntimeError("Defina uma topologia antes de executar a rede.")

        if not self.config.crypto_mode:
            self.config.crypto_mode = "classical"

            self.crypto_manager.configure(
                mode=self.config.crypto_mode
            )

            defaults_applied.append(f"criptografia: {self._crypto_label(self.config.crypto_mode)}")

        if not self.config.protocol_name:
            self.config.protocol_name = "mqtt"
            defaults_applied.append(f"protocolo: {self.config.protocol_name}")

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

            defaults_applied.append("metricas padrao")

        if defaults_applied:
            self._log_info(
                f"Configuracoes padrao aplicadas: {', '.join(defaults_applied)}"
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