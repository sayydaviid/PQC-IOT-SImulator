from pathlib import Path
from typing import Any
import os
import json
import subprocess
import time
import re

from .base_engine import BaseEngine, EngineLink
from ..components.logger import Logger


class MininetWiFiEngine(BaseEngine):
    """
    Engine concreta para executar a topologia logica da Network no Mininet WiFi.

    A Network continua sendo responsavel por:
        topologia logica
        hosts
        criptografia
        metricas
        logs

    Esta engine fica responsavel por:
        criar stations para IoT
        criar access points para gateways
        criar hosts para servidores
        criar links no Mininet WiFi
        iniciar, parar e executar comandos na rede

    Modos de link:
        infrastructure:
            os IoTs se associam ao gateway via wireless.
            o servidor se conecta ao gateway por link cabeado.
            esse modo e ideal para validar conectividade rapidamente.

        logical_topology:
            usa exatamente os links da topologia logica.
            esse modo precisa de roteamento adicional para alguns cenarios.
    """

    def __init__(
        self,
        network: Any,
        name: str = "mininet_wifi_engine",
        logger: Logger | None = None,
        verbose: bool = True,
        log_level: str = "info",
        ip_base: str = "10.0.0.",
        ip_prefix: int = 24,
        ssid: str = "pqc_iot_sim",
        mode: str = "g",
        channel: str = "1",
        default_bw: float | None = None,
        default_delay: str | None = None,
        default_loss: float | None = None,
        auto_set_positions: bool = True,
        open_cli_on_start: bool = False,
        link_mode: str = "infrastructure",
        station_range: int = 200,
        ap_range: int = 200,
        association_wait_seconds: float = 1.0
    ):
        super().__init__(
            network=network,
            name=name,
            engine_type="mininet_wifi",
            logger=logger,
            verbose=verbose
        )

        valid_log_levels = ["silent", "info", "debug"]

        if log_level not in valid_log_levels:
            raise ValueError(
                f"Nivel de log invalido: {log_level}. "
                f"Use um destes: {valid_log_levels}"
            )

        self.log_level = log_level

        self.ip_base = ip_base
        self.ip_prefix = ip_prefix
        self.ssid = ssid
        self.mode = mode
        self.channel = channel
        self.default_bw = default_bw
        self.default_delay = default_delay
        self.default_loss = default_loss
        self.auto_set_positions = auto_set_positions
        self.open_cli_on_start = open_cli_on_start
        self.link_mode = link_mode
        self.station_range = station_range
        self.ap_range = ap_range
        self.association_wait_seconds = association_wait_seconds

        self.valid_link_modes = [
            "infrastructure",
            "logical_topology"
        ]

        self.net = None
        self.controller = None
        self.mininet_nodes: dict[str, Any] = {}

        self._validate_link_mode()

        self.configure(
            ip_base=self.ip_base,
            ip_prefix=self.ip_prefix,
            ssid=self.ssid,
            mode=self.mode,
            channel=self.channel,
            default_bw=self.default_bw,
            default_delay=self.default_delay,
            default_loss=self.default_loss,
            auto_set_positions=self.auto_set_positions,
            open_cli_on_start=self.open_cli_on_start,
            link_mode=self.link_mode,
            station_range=self.station_range,
            ap_range=self.ap_range,
            association_wait_seconds=self.association_wait_seconds
        )

        self._log_info(
            (
                f"Engine Mininet WiFi criada, "
                f"modo de link: {self.link_mode}, "
                f"SSID: {self.ssid}"
            )
        )

    def set_log_level(self, level: str):
        valid_levels = ["silent", "info", "debug"]

        if level not in valid_levels:
            raise ValueError(
                f"Nivel de log invalido: {level}. "
                f"Use um destes: {valid_levels}"
            )

        self.log_level = level
        return self

    def _log_info(
        self,
        message: str,
        data: dict[str, Any] | None = None,
        component: str | None = None
    ):
        if self.log_level in ["info", "debug"]:
            self.logger.log(
                message,
                data=data or {},
                component=component or self.name
            )

    def _log_debug(
        self,
        message: str,
        data: dict[str, Any] | None = None,
        component: str | None = None
    ):
        if self.log_level == "debug":
            self.logger.log(
                message,
                data=data or {},
                component=component or self.name
            )

    def _log_error(
        self,
        message: str,
        data: dict[str, Any] | None = None,
        component: str | None = None
    ):
        if self.log_level != "silent":
            self.logger.log(
                message,
                data=data or {},
                level="ERROR",
                component=component or self.name
            )

    def set_link_mode(self, link_mode: str):
        self.link_mode = link_mode
        self._validate_link_mode()

        self.status.metadata["link_mode"] = self.link_mode

        self._log_info(
            f"Modo de link alterado para {self.link_mode}"
        )

        return self

    def build(self):
        if self.is_built():
            self._log_debug(
                "Build ignorado porque a engine ja estava construida"
            )

            return self

        self._check_root_permission()
        self.prepare()

        modules = self._import_mininet_wifi_modules()

        Mininet_wifi = modules["Mininet_wifi"]
        Controller = modules["Controller"]
        OVSKernelAP = modules["OVSKernelAP"]
        TCLink = modules["TCLink"]
        setLogLevel = modules["setLogLevel"]

        setLogLevel("info")

        self._log_info(
            (
                f"Construindo rede no Mininet WiFi, "
                f"nos: {len(self.engine_nodes)}, "
                f"links: {len(self.engine_links)}, "
                f"modo de link: {self.link_mode}"
            )
        )

        self.net = Mininet_wifi(
            controller=Controller,
            accessPoint=OVSKernelAP,
            link=TCLink
        )

        self.controller = self.net.addController("c0")

        self.set_runtime_object("net", self.net)
        self.set_runtime_object("controller", self.controller)

        self._assign_ips()
        self._assign_positions()
        self._create_mininet_nodes()
        self._configure_wifi_nodes()
        self._create_mininet_links()

        self.mark_built()

        self._log_info(
            (
                f"Build do Mininet WiFi concluido, "
                f"stations: {self._count_nodes_by_type('iot')}, "
                f"gateways: {self._count_nodes_by_type('gateway')}, "
                f"servidores: {self._count_nodes_by_type('server')}, "
                f"links: {len(self.engine_links)}, "
                f"modo de link: {self.link_mode}"
            )
        )

        return self

    def start(self):
        if self.is_running():
            self._log_debug(
                "Start ignorado porque a engine ja estava em execucao"
            )

            return self

        if not self.is_built():
            self.build()

        if self.net is None:
            raise RuntimeError("Objeto Mininet WiFi nao foi criado.")

        self._log_info(
            "Iniciando rede Mininet WiFi"
        )

        self.net.build()

        if self.controller is not None:
            self.controller.start()

        access_points = self._get_access_points()

        for ap in access_points:
            ap.start([self.controller])

        self.mark_started()

        ap_names = [
            ap.name
            for ap in access_points
        ]

        self._log_info(
            (
                f"Mininet WiFi iniciado com sucesso, "
                f"access points ativos: {', '.join(ap_names) if ap_names else 'nenhum'}"
            )
        )

        self._post_start_configuration()

        if self.open_cli_on_start:
            self.cli()

        return self

    def stop(self):
        if self.net is None:
            self._log_debug(
                "Stop ignorado porque nao existe rede Mininet criada"
            )

            self.mark_stopped()

            return self

        self._log_info(
            "Parando rede Mininet WiFi"
        )

        try:
            self.net.stop()

        finally:
            self.mark_stopped()

            self._log_info(
                "Mininet WiFi parado com sucesso"
            )

        return self

    def run_command(self, node_id: str, command: str):
        if not self.is_running():
            raise RuntimeError("A engine precisa estar em execucao para executar comandos.")

        node = self.get_mininet_node(node_id)

        if node is None:
            raise KeyError(f"No nao encontrado na engine: {node_id}")

        self._log_debug(
            f"Executando comando no no {node_id}, mininet: {node.name}, comando: {command}"
        )

        output = node.cmd(command)

        self._log_debug(
            f"Comando executado no no {node_id}, comando: {command}, saida: {output.strip()}"
        )

        return output

    def cli(self):
        if self.net is None:
            raise RuntimeError("A rede Mininet WiFi ainda nao foi criada.")

        modules = self._import_mininet_wifi_modules()
        CLI_wifi = modules["CLI_wifi"]

        if CLI_wifi is None:
            raise RuntimeError(
                "CLI do Mininet WiFi nao encontrada nesta versao instalada."
            )

        self._log_info(
            "Abrindo CLI do Mininet WiFi"
        )

        CLI_wifi(self.net)

        return self

    def ping(self, source: str, destination: str, count: int = 3):
        destination_ip = self.get_ip(destination)

        if destination_ip is None:
            raise RuntimeError(f"No de destino sem IP registrado: {destination}")

        command = f"ping -c {count} {destination_ip}"

        return self.run_command(source, command)

    def collect_link_metrics(
        self,
        source: str,
        destination: str,
        count: int = 3
    ):
        output = self.ping(
            source=source,
            destination=destination,
            count=count
        )

        destination_ip = self.get_ip(destination)

        metrics = {
            "source": source,
            "destination": destination,
            "destination_ip": destination_ip,
            "packet_loss_percent": None,
            "packets_transmitted": None,
            "packets_received": None,
            "rtt_min_ms": None,
            "rtt_avg_ms": None,
            "rtt_max_ms": None,
            "rtt_mdev_ms": None,
            "latency_ms": None,
            "raw_output": output
        }

        packet_patterns = [
            r"(\d+)\s+packets transmitted,\s+(\d+)\s+received.*?(\d+(?:\.\d+)?)%\s+packet loss",
            r"(\d+)\s+packets transmitted,\s+(\d+)\s+packets received,\s+(\d+(?:\.\d+)?)%\s+packet loss"
        ]

        packets_match = None

        for pattern in packet_patterns:
            packets_match = re.search(pattern, output)

            if packets_match:
                break

        if packets_match:
            metrics["packets_transmitted"] = int(packets_match.group(1))
            metrics["packets_received"] = int(packets_match.group(2))
            metrics["packet_loss_percent"] = float(packets_match.group(3))

        rtt_patterns = [
            r"rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)",
            r"round-trip min/avg/max/(?:mdev|stddev) = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)"
        ]

        rtt_match = None

        for pattern in rtt_patterns:
            rtt_match = re.search(pattern, output)

            if rtt_match:
                break

        if rtt_match:
            metrics["rtt_min_ms"] = float(rtt_match.group(1))
            metrics["rtt_avg_ms"] = float(rtt_match.group(2))
            metrics["rtt_max_ms"] = float(rtt_match.group(3))
            metrics["rtt_mdev_ms"] = float(rtt_match.group(4))
            metrics["latency_ms"] = metrics["rtt_avg_ms"]

        else:
            times = re.findall(r"time[=<]([\d.]+)\s*ms", output)

            if times:
                values = [float(value) for value in times]
                metrics["rtt_min_ms"] = min(values)
                metrics["rtt_avg_ms"] = sum(values) / len(values)
                metrics["rtt_max_ms"] = max(values)
                metrics["latency_ms"] = metrics["rtt_avg_ms"]

        self._log_info(
            (
                f"Metricas reais de link coletadas entre {source} e {destination}, "
                f"IP destino: {destination_ip}, "
                f"latencia: {metrics['latency_ms']} ms, "
                f"perda de pacotes: {metrics['packet_loss_percent']}%, "
                f"pacotes enviados: {metrics['packets_transmitted']}, "
                f"pacotes recebidos: {metrics['packets_received']}"
            )
        )

        self._log_debug(
            f"Saida bruta do ping entre {source} e {destination}: {output.strip()}"
        )

        return metrics

    def ping_all(self):
        if not self.is_running():
            raise RuntimeError("A engine precisa estar em execucao para executar ping_all.")

        if self.net is None:
            raise RuntimeError("A rede Mininet WiFi ainda nao foi criada.")

        self._log_info(
            "Executando teste geral de conectividade com pingAll"
        )

        result = self.net.pingAll()

        self._log_info(
            f"Teste geral de conectividade concluido, perda de pacotes: {result}%"
        )

        return result

    def iperf(
        self,
        source: str,
        destination: str,
        seconds: int = 5
    ):
        if not self.is_running():
            raise RuntimeError("A engine precisa estar em execucao para executar iperf.")

        if self.net is None:
            raise RuntimeError("A rede Mininet WiFi ainda nao foi criada.")

        source_node = self.get_mininet_node(source)
        destination_node = self.get_mininet_node(destination)

        if source_node is None:
            raise KeyError(f"No de origem nao encontrado na engine: {source}")

        if destination_node is None:
            raise KeyError(f"No de destino nao encontrado na engine: {destination}")

        self._log_info(
            f"Executando teste de throughput com iperf entre {source} e {destination}, duracao: {seconds}s"
        )

        result = self.net.iperf(
            [source_node, destination_node],
            seconds=seconds
        )

        self._log_info(
            f"Teste iperf concluido entre {source} e {destination}, resultado: {result}"
        )

        return result

    def get_mininet_node(self, node_id: str):
        return self.mininet_nodes.get(node_id)

    def get_ip(self, node_id: str):
        engine_node = self.engine_nodes.get(node_id)

        if engine_node is None:
            return None

        if engine_node.ip is None:
            return None

        return engine_node.ip.split("/")[0]

    def get_mininet_name(self, node_id: str):
        engine_node = self.engine_nodes.get(node_id)

        if engine_node is None:
            return None

        return engine_node.mininet_name

    def export_mapping_json(self, output_path: str):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "engine": self.summary(),
            "node_mapping": self.get_engine_nodes(),
            "link_mapping": self.get_engine_links()
        }

        with open(path, "w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                indent=4,
                ensure_ascii=False,
                default=str
            )

        self._log_info(
            f"Mapeamento da engine exportado em {output_path}"
        )

        return self

    def _map_links(self):
        if self.link_mode == "infrastructure":
            return self._map_infrastructure_links()

        if self.link_mode == "logical_topology":
            return self._map_logical_topology_links()

        raise ValueError(f"Modo de link nao suportado: {self.link_mode}")

    def _map_infrastructure_links(self):
        self.engine_links = []

        gateway_nodes = [
            node_id
            for node_id, node in self.engine_nodes.items()
            if node.node_type == "gateway"
        ]

        server_nodes = [
            node_id
            for node_id, node in self.engine_nodes.items()
            if node.node_type == "server"
        ]

        if not gateway_nodes:
            raise RuntimeError(
                "Modo infrastructure exige pelo menos um gateway na topologia."
            )

        if not server_nodes:
            raise RuntimeError(
                "Modo infrastructure exige pelo menos um servidor na topologia."
            )

        for gateway_id in gateway_nodes:
            gateway_engine = self.engine_nodes[gateway_id]

            for server_id in server_nodes:
                server_engine = self.engine_nodes[server_id]

                engine_link = EngineLink(
                    source=gateway_id,
                    target=server_id,
                    source_mininet=gateway_engine.mininet_name,
                    target_mininet=server_engine.mininet_name,
                    metadata={
                        "link_mode": "infrastructure",
                        "original_source": gateway_id,
                        "original_target": server_id,
                        "note": "stations se associam ao AP via wireless"
                    }
                )

                self.engine_links.append(engine_link)

        self._log_debug(
            (
                f"Links de infraestrutura mapeados, "
                f"gateways: {len(gateway_nodes)}, "
                f"servidores: {len(server_nodes)}, "
                f"links: {len(self.engine_links)}"
            )
        )

        return self.engine_links

    def _map_logical_topology_links(self):
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
                    "link_mode": "logical_topology",
                    "original_source": source,
                    "original_target": target
                }
            )

            self.engine_links.append(engine_link)

        self._log_debug(
            f"Links logicos mapeados para a engine, total: {len(self.engine_links)}"
        )

        return self.engine_links

    def _create_mininet_nodes(self):
        if self.net is None:
            raise RuntimeError("Objeto Mininet WiFi nao foi criado.")

        self.mininet_nodes = {}

        for node_id, engine_node in self.engine_nodes.items():
            node_type = engine_node.node_type
            mininet_name = engine_node.mininet_name
            ip = engine_node.ip
            position = engine_node.metadata.get("position")

            if node_type == "iot":
                mininet_node = self._add_station(
                    name=mininet_name,
                    ip=ip,
                    position=position
                )

            elif node_type == "gateway":
                mininet_node = self._add_access_point(
                    name=mininet_name,
                    ip=ip,
                    position=position
                )

            elif node_type == "server":
                mininet_node = self._add_host(
                    name=mininet_name,
                    ip=ip
                )

            else:
                mininet_node = self._add_host(
                    name=mininet_name,
                    ip=ip
                )

            self.mininet_nodes[node_id] = mininet_node
            self.set_runtime_object(node_id, mininet_node)

        self._log_info(
            (
                f"Nos criados no Mininet WiFi, "
                f"total: {len(self.mininet_nodes)}, "
                f"stations: {self._count_nodes_by_type('iot')}, "
                f"gateways: {self._count_nodes_by_type('gateway')}, "
                f"servidores: {self._count_nodes_by_type('server')}"
            )
        )

    def _add_station(
        self,
        name: str,
        ip: str | None,
        position: str | None
    ):
        params = {
            "range": self.station_range
        }

        if ip:
            params["ip"] = ip

        if position:
            params["position"] = position

        return self.net.addStation(
            name,
            **params
        )

    def _add_access_point(
        self,
        name: str,
        ip: str | None,
        position: str | None
    ):
        params = {
            "ssid": f"{self.ssid}_{name}",
            "mode": self.mode,
            "channel": self.channel,
            "range": self.ap_range,
            "failMode": "standalone",
        }

        if ip:
            params["ip"] = ip

        if position:
            params["position"] = position

        return self.net.addAccessPoint(
            name,
            **params
        )

    def _add_host(
        self,
        name: str,
        ip: str | None
    ):
        params = {}

        if ip:
            params["ip"] = ip

        return self.net.addHost(
            name,
            **params
        )

    def _configure_wifi_nodes(self):
        if self.net is None:
            raise RuntimeError("Objeto Mininet WiFi nao foi criado.")

        self._log_debug(
            "Configurando nos WiFi no Mininet"
        )

        self.net.configureWifiNodes()

    def _create_mininet_links(self):
        if self.net is None:
            raise RuntimeError("Objeto Mininet WiFi nao foi criado.")

        created_links = []

        for link in self.engine_links:
            source_node = self.mininet_nodes.get(link.source)
            target_node = self.mininet_nodes.get(link.target)

            if source_node is None:
                raise RuntimeError(f"No de origem sem objeto Mininet: {link.source}")

            if target_node is None:
                raise RuntimeError(f"No de destino sem objeto Mininet: {link.target}")

            link_params = self._build_link_params(link)

            self._log_debug(
                (
                    f"Criando link no Mininet WiFi entre {link.source} e {link.target}, "
                    f"modo de link: {self.link_mode}, "
                    f"parametros: {link_params}"
                )
            )

            created = self._safe_add_link(
                source_node=source_node,
                target_node=target_node,
                link_params=link_params
            )

            created_links.append(
                {
                    "origem": link.source,
                    "destino": link.target,
                    "origem_mininet": link.source_mininet,
                    "destino_mininet": link.target_mininet,
                    "criado": created
                }
            )

        self._log_info(
            f"{len(created_links)} links criados no Mininet WiFi"
        )

    def _safe_add_link(
        self,
        source_node: Any,
        target_node: Any,
        link_params: dict[str, Any]
    ):
        try:
            self.net.addLink(
                source_node,
                target_node,
                **link_params
            )

            return True

        except TypeError:
            source_name = getattr(source_node, "name", str(source_node))
            target_name = getattr(target_node, "name", str(target_node))

            self._log_debug(
                (
                    f"Criacao de link com parametros falhou entre {source_name} e {target_name}. "
                    f"Tentando criar o link sem parametros"
                )
            )

            self.net.addLink(
                source_node,
                target_node
            )

            return True

    def _build_link_params(self, link):
        params = {}

        bandwidth = link.bandwidth if link.bandwidth is not None else self.default_bw
        delay = link.delay if link.delay is not None else self.default_delay
        loss = link.loss if link.loss is not None else self.default_loss

        if bandwidth is not None:
            params["bw"] = bandwidth

        if delay is not None:
            params["delay"] = delay

        if loss is not None:
            params["loss"] = loss

        return params

    def _assign_ips(self):
        iot_counter = 1
        server_counter = 200
        gateway_counter = 250
        generic_counter = 100

        for node_id, engine_node in self.engine_nodes.items():
            if engine_node.node_type == "iot":
                ip_number = iot_counter
                iot_counter += 1

            elif engine_node.node_type == "server":
                ip_number = server_counter
                server_counter += 1

            elif engine_node.node_type == "gateway":
                ip_number = gateway_counter
                gateway_counter += 1

            else:
                ip_number = generic_counter
                generic_counter += 1

            if ip_number > 254:
                raise RuntimeError(
                    f"Limite de IP excedido para a rede {self.ip_base}0/{self.ip_prefix}."
                )

            engine_node.ip = f"{self.ip_base}{ip_number}/{self.ip_prefix}"

        self._log_debug(
            f"IPs atribuidos aos nos da engine, total: {len(self.engine_nodes)}"
        )

    def _assign_positions(self):
        if not self.auto_set_positions:
            self._log_debug(
                "Atribuicao automatica de posicoes ignorada"
            )

            return

        rows = self.network.config.topology_params.get("rows")
        cols = self.network.config.topology_params.get("cols")

        spacing_x = 35
        spacing_y = 35

        for index, node_id in enumerate(self.network.topology_data.nodes):
            engine_node = self.engine_nodes[node_id]

            if isinstance(rows, int) and isinstance(cols, int):
                row = index // cols
                col = index % cols

                x = 20 + col * spacing_x
                y = 20 + row * spacing_y

            else:
                x = 20 + index * 15
                y = 50

            z = 0

            engine_node.metadata["position"] = f"{x},{y},{z}"

        self._log_debug(
            f"Posicoes atribuidas aos nos da engine, total: {len(self.engine_nodes)}"
        )

    def _post_start_configuration(self):
        if self.link_mode == "infrastructure":
            self._force_wireless_interfaces_up()
            self._associate_stations_to_gateway()
            self._enable_l2_forwarding_on_access_points()
            self._flush_arp_cache()

            self._log_info(
                (
                    f"Configuracao de conectividade aplicada, "
                    f"modo de link: {self.link_mode}, "
                    f"stations associadas aos APs, interfaces WiFi ativadas e encaminhamento L2 configurado"
                )
            )

            return

        self._log_debug(
            f"Configuracao pos inicio ignorada para o modo de link {self.link_mode}"
        )

    def _force_wireless_interfaces_up(self):
        actions = []

        for node_id, engine_node in self.engine_nodes.items():
            if engine_node.node_type != "iot":
                continue

            station = self.mininet_nodes.get(node_id)

            if station is None:
                continue

            wlan = f"{station.name}-wlan0"
            output = station.cmd(f"ip link set {wlan} up")

            actions.append(
                {
                    "no": node_id,
                    "station": station.name,
                    "interface": wlan,
                    "saida": output.strip()
                }
            )

        self._log_debug(
            f"Interfaces WiFi das stations ativadas, total: {len(actions)}"
        )

    def _associate_stations_to_gateway(self):
        access_points = self._get_access_points()

        if not access_points:
            self._log_error(
                "Associacao wireless nao foi aplicada porque nenhum access point foi encontrado"
            )

            return

        associated = []
        failed = []

        iot_nodes = [
            node_id
            for node_id, engine_node in self.engine_nodes.items()
            if engine_node.node_type == "iot"
        ]

        ap_count = len(access_points)

        for index, node_id in enumerate(iot_nodes):
            ap = access_points[index % ap_count]
            ssid = f"{self.ssid}_{ap.name}"

            station = self.mininet_nodes.get(node_id)

            if station is None:
                failed.append(
                    {
                        "no": node_id,
                        "ap": ap.name,
                        "ssid": ssid,
                        "motivo": "station_not_found"
                    }
                )

                continue

            wlan = f"{station.name}-wlan0"

            association_result = self._force_station_connection_to_ap(
                node_id=node_id,
                station=station,
                ap=ap,
                wlan=wlan,
                ssid=ssid
            )

            if association_result["connected"]:
                associated.append(association_result)
            else:
                failed.append(association_result)

        if failed:
            self._log_error(
                (
                    f"Algumas stations nao conseguiram associar ao AP, "
                    f"associadas: {len(associated)}, "
                    f"falhas: {len(failed)}"
                )
            )

        else:
            ap_names = [
                ap.name
                for ap in access_points
            ]

            self._log_info(
                (
                    f"Stations associadas aos access points, "
                    f"stations: {len(associated)}, "
                    f"APs: {', '.join(ap_names)}, "
                    f"estrategia: round robin"
                )
            )

        self._log_debug(
            (
                f"Associacao wireless finalizada, "
                f"associadas: {len(associated)}, "
                f"falhas: {len(failed)}"
            )
        )

    def _force_station_connection_to_ap(
        self,
        node_id: str,
        station: Any,
        ap: Any,
        wlan: str,
        ssid: str
    ):
        outputs = {}

        try:
            if hasattr(station, "setAssociation"):
                result = station.setAssociation(ap)
                outputs["setAssociation"] = str(result)

        except Exception as exc:
            outputs["setAssociation_error"] = str(exc)

        commands = [
            f"ip link set {wlan} up",
            f"iw dev {wlan} disconnect",
            f"iw dev {wlan} connect {ssid}",
            f"ip link set {wlan} up"
        ]

        for command in commands:
            output = station.cmd(command)
            outputs[command] = output.strip()

        time.sleep(self.association_wait_seconds)

        link_status = station.cmd(f"iw dev {wlan} link").strip()
        route_status = station.cmd("ip route").strip()
        addr_status = station.cmd(f"ip addr show {wlan}").strip()

        connected = "Connected to" in link_status

        result = {
            "node_id": node_id,
            "station": station.name,
            "ap": ap.name,
            "interface": wlan,
            "ssid": ssid,
            "connected": connected,
            "link_status": link_status,
            "route_status": route_status,
            "addr_status": addr_status,
            "outputs": outputs
        }

        self._log_debug(
            (
                f"Tentativa de associacao wireless executada para {node_id}, "
                f"station: {station.name}, "
                f"AP: {ap.name}, "
                f"SSID: {ssid}, "
                f"conectado: {connected}"
            )
        )

        return result

    def _flush_arp_cache(self):
        results = {}

        for node_id, node in self.mininet_nodes.items():
            output = node.cmd("ip neigh flush all")
            results[node_id] = output.strip()

        self._log_debug(
            f"Cache ARP apagado nos nos da engine, total: {len(results)}"
        )

    def _enable_l2_forwarding_on_access_points(self):
        access_points = self._get_access_points()
        command_results = []

        for ap in access_points:
            ap_name = ap.name

            commands = [
                ["ovs-vsctl", "set-fail-mode", ap_name, "standalone"],
                ["ovs-ofctl", "del-flows", ap_name],
                ["ovs-ofctl", "add-flow", ap_name, "priority=0,actions=NORMAL"]
            ]

            for command in commands:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True
                )

                command_results.append(
                    {
                        "ap": ap_name,
                        "comando": " ".join(command),
                        "codigo_retorno": result.returncode,
                        "stdout": result.stdout.strip(),
                        "stderr": result.stderr.strip()
                    }
                )

        time.sleep(1)

        self._log_debug(
            (
                f"Encaminhamento L2 configurado nos access points, "
                f"APs: {len(access_points)}, "
                f"comandos executados: {len(command_results)}"
            )
        )

    def _validate_link_mode(self):
        if self.link_mode not in self.valid_link_modes:
            raise ValueError(
                f"Modo de link invalido: {self.link_mode}. "
                f"Use um destes: {self.valid_link_modes}"
            )

    def _count_nodes_by_type(self, node_type: str):
        return sum(
            1 for node in self.engine_nodes.values()
            if node.node_type == node_type
        )

    def _get_access_points(self):
        aps = []

        for node_id, engine_node in self.engine_nodes.items():
            if engine_node.node_type == "gateway":
                mininet_node = self.mininet_nodes.get(node_id)

                if mininet_node is not None:
                    aps.append(mininet_node)

        return aps

    def _check_root_permission(self):
        if hasattr(os, "geteuid") and os.geteuid() != 0:
            uid = os.geteuid()
            message = f"Mininet WiFi precisa ser executado com sudo, UID atual: {uid}"

            self._log_error(message)

            raise PermissionError(message)

    def _import_mininet_wifi_modules(self):
        try:
            from mn_wifi.net import Mininet_wifi
            from mn_wifi.node import OVSKernelAP

            from mininet.node import Controller
            from mininet.link import TCLink
            from mininet.log import setLogLevel

        except ImportError as exc:
            raise RuntimeError(
                "Falha ao importar os modulos principais do Mininet WiFi. "
                f"Erro original: {exc}"
            ) from exc

        CLI_wifi = None

        try:
            from mn_wifi.cli import CLI
            CLI_wifi = CLI

        except ImportError:
            try:
                from mn_wifi.cli import CLI_wifi
                CLI_wifi = CLI_wifi

            except ImportError:
                CLI_wifi = None

        return {
            "Mininet_wifi": Mininet_wifi,
            "OVSKernelAP": OVSKernelAP,
            "CLI_wifi": CLI_wifi,
            "Controller": Controller,
            "TCLink": TCLink,
            "setLogLevel": setLogLevel
        }