from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any

from ..components.logger import Logger


@dataclass
class EngineStatus:
    name: str
    engine_type: str
    is_built: bool = False
    is_running: bool = False
    started_at: str | None = None
    stopped_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


@dataclass
class EngineNode:
    node_id: str
    node_type: str
    mininet_name: str
    ip: str | None = None
    mac: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EngineLink:
    source: str
    target: str
    source_mininet: str
    target_mininet: str
    bandwidth: float | None = None
    delay: str | None = None
    loss: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseEngine(ABC):
    """
    Classe base para motores de execução do simulador.

    A Network representa a lógica da simulação.

    A Engine representa a execução concreta da rede.

    Exemplo:
        Network cria topologia, hosts, criptografia e métricas.
        MininetWiFiEngine cria stations, access points, hosts e links reais.
    """

    def __init__(
        self,
        network: Any,
        name: str = "base_engine",
        engine_type: str = "base",
        logger: Logger | None = None,
        verbose: bool = True
    ):
        self.network = network
        self.name = name
        self.engine_type = engine_type
        self.logger = logger or Logger(name=name, verbose=verbose)

        self.status = EngineStatus(
            name=self.name,
            engine_type=self.engine_type
        )

        self.engine_nodes: dict[str, EngineNode] = {}
        self.engine_links: list[EngineLink] = []

        self.runtime_objects: dict[str, Any] = {}

        self.logger.log(
            f"Engine {self.name} criada, tipo: {self.engine_type}",
            component=self.name
        )

    def configure(self, **params):
        self.status.metadata.update(params)

        if params:
            configured_params = ", ".join(
                f"{key}: {value}"
                for key, value in params.items()
            )

            self.logger.log(
                f"Engine {self.name} configurada, parametros: {configured_params}",
                component=self.name
            )
        else:
            self.logger.log(
                f"Engine {self.name} configurada sem parametros adicionais",
                component=self.name
            )

        return self

    def validate_network(self):
        if self.network is None:
            raise RuntimeError("Nenhuma Network foi associada a engine.")

        if not hasattr(self.network, "topology_data"):
            raise RuntimeError("Objeto Network invalido. topology_data nao encontrado.")

        if not self.network.topology_data.nodes:
            raise RuntimeError("A Network precisa ter nos antes de iniciar a engine.")

        if not self.network.topology_data.links:
            raise RuntimeError("A Network precisa ter links antes de iniciar a engine.")

        total_nodes = len(self.network.topology_data.nodes)
        total_links = len(self.network.topology_data.links)

        self.logger.log(
            f"Network validada para a engine, nos: {total_nodes}, links: {total_links}",
            component=self.name
        )

        return True

    def prepare(self):
        self.validate_network()
        self._map_nodes()
        self._map_links()

        self.logger.log(
            (
                f"Engine preparada, "
                f"nos mapeados: {len(self.engine_nodes)}, "
                f"links mapeados: {len(self.engine_links)}"
            ),
            component=self.name
        )

        return self

    def _map_nodes(self):
        self.engine_nodes = {}

        for node_id in self.network.topology_data.nodes:
            node_type = self._infer_node_type(node_id)

            engine_node = EngineNode(
                node_id=node_id,
                node_type=node_type,
                mininet_name=self._to_mininet_name(node_id),
                metadata={
                    "original_node_id": node_id
                }
            )

            self.engine_nodes[node_id] = engine_node

        self.logger.log(
            f"{len(self.engine_nodes)} nos mapeados para a engine",
            component=self.name
        )

        return self.engine_nodes

    def _map_links(self):
        self.engine_links = []

        for source, target in self.network.topology_data.links:
            if source not in self.engine_nodes:
                raise RuntimeError(f"No de origem nao mapeado na engine: {source}")

            if target not in self.engine_nodes:
                raise RuntimeError(f"No de destino nao mapeado na engine: {target}")

            source_engine = self.engine_nodes[source]
            target_engine = self.engine_nodes[target]

            engine_link = EngineLink(
                source=source,
                target=target,
                source_mininet=source_engine.mininet_name,
                target_mininet=target_engine.mininet_name,
                metadata={
                    "original_source": source,
                    "original_target": target
                }
            )

            self.engine_links.append(engine_link)

        self.logger.log(
            f"{len(self.engine_links)} links mapeados para a engine",
            component=self.name
        )

        return self.engine_links

    def _infer_node_type(self, node_id: str):
        if node_id.startswith("gateway"):
            return "gateway"

        if node_id.startswith("server"):
            return "server"

        if node_id.startswith("iot"):
            return "iot"

        return "generic"

    def _to_mininet_name(self, node_id: str):
        clean_name = (
            node_id
            .replace("-", "_")
            .replace(".", "_")
            .replace(" ", "_")
        )

        if clean_name.startswith("iot"):
            suffix = clean_name.replace("iot_", "").replace("iot", "")

            if suffix.isdigit():
                return f"sta{suffix}"

            return f"sta_{clean_name}"

        if clean_name.startswith("gateway"):
            suffix = clean_name.replace("gateway_", "").replace("gateway", "")

            if suffix.isdigit():
                return f"ap{suffix}"

            return f"ap_{clean_name}"

        if clean_name.startswith("server"):
            suffix = clean_name.replace("server_", "").replace("server", "")

            if suffix.isdigit():
                return f"h{suffix}"

            return f"h_{clean_name}"

        return clean_name

    def mark_built(self):
        self.status.is_built = True

        self.logger.log(
            f"Engine {self.name} marcada como construida",
            component=self.name
        )

        return self

    def mark_started(self):
        self.status.is_running = True
        self.status.started_at = self._now()

        self.logger.log(
            f"Engine {self.name} iniciada em {self.status.started_at}",
            component=self.name
        )

        return self

    def mark_stopped(self):
        self.status.is_running = False
        self.status.stopped_at = self._now()

        self.logger.log(
            f"Engine {self.name} parada em {self.status.stopped_at}",
            component=self.name
        )

        return self

    def is_built(self):
        return self.status.is_built

    def is_running(self):
        return self.status.is_running

    def get_status(self):
        return self.status.to_dict()

    def get_engine_nodes(self):
        return {
            node_id: asdict(node)
            for node_id, node in self.engine_nodes.items()
        }

    def get_engine_links(self):
        return [
            asdict(link)
            for link in self.engine_links
        ]

    def set_runtime_object(self, key: str, value: Any):
        self.runtime_objects[key] = value

        self.logger.log(
            f"Objeto de runtime registrado, chave: {key}, tipo: {type(value).__name__}",
            component=self.name
        )

        return self

    def summary(self):
        data = {
            "status": self.get_status(),
            "nodes": self.get_engine_nodes(),
            "links": self.get_engine_links(),
            "runtime_objects": list(self.runtime_objects.keys())
        }

        return data

    def _now(self):
        return datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    @abstractmethod
    def build(self):
        """
        Constrói a rede no motor concreto.
        Exemplo: criar objeto Mininet_wifi, stations, APs, hosts e links.
        """
        raise NotImplementedError

    @abstractmethod
    def start(self):
        """
        Inicia a rede no motor concreto.
        Exemplo: net.build(), net.start().
        """
        raise NotImplementedError

    @abstractmethod
    def stop(self):
        """
        Para a rede no motor concreto.
        Exemplo: net.stop().
        """
        raise NotImplementedError

    @abstractmethod
    def run_command(self, node_id: str, command: str):
        """
        Executa um comando dentro de um no da engine.
        Exemplo: sta1.cmd("ping h1").
        """
        raise NotImplementedError