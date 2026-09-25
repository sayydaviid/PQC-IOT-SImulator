"""Executa topologias da plataforma em uma rede Mininet-WiFi."""

from pathlib import Path
from typing import Any
import base64
import os
import json
import subprocess
import time
import re
import uuid
import signal
import select
import networkx as nx

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
        position_spacing_m: float = 5.0,
        association_wait_seconds: float = 1.0
    ):
        """Inicializa a instância e prepara seu estado interno.

        Parâmetros:
            network: Rede lógica usada pelo motor.
            name: Nome usado para identificar o objeto ou protocolo.
            logger: Registrador usado pelo componente.
            verbose: Indica se a saída detalhada será exibida.
            log_level: Nível mínimo das mensagens de log.
            ip_base: Prefixo-base dos endereços IPv4.
            ip_prefix: Comprimento do prefixo da rede IPv4.
            ssid: Nome da rede Wi-Fi.
            mode: Modo selecionado.
            channel: Canal Wi-Fi utilizado pela rede.
            default_bw: Largura de banda padrão, em megabits por segundo.
            default_delay: Atraso padrão aplicado aos enlaces.
            default_loss: Perda padrão aplicada aos enlaces, em porcentagem.
            auto_set_positions: Indica se as posições serão atribuídas automaticamente.
            open_cli_on_start: Indica se a CLI será aberta ao iniciar.
            link_mode: Modo de criação dos enlaces no Mininet.
            station_range: Alcance configurado das estações, em metros.
            ap_range: Alcance configurado dos pontos de acesso, em metros.
            position_spacing_m: Distância entre posições automáticas, em metros.
            association_wait_seconds: Tempo máximo de espera pela associação Wi-Fi.
        """
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
        if position_spacing_m <= 0:
            raise ValueError("position_spacing_m must be greater than zero")
        self.position_spacing_m = float(position_spacing_m)
        self.association_wait_seconds = association_wait_seconds
        self.last_association_report: dict[str, Any] = {
            "associated": [],
            "failed": [],
        }
        self.last_ap_report: dict[str, Any] = {
            "operational": [],
            "failed": [],
        }

        self.valid_link_modes = [
            "infrastructure",
            "logical_topology",
            "routed_logical_topology",
        ]

        self.net = None
        self.controller = None
        self.mininet_nodes: dict[str, Any] = {}
        self.created_link_objects: list[dict[str, Any]] = []
        self._transport_port_counter = 0

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
            position_spacing_m=self.position_spacing_m,
            association_wait_seconds=self.association_wait_seconds
        )

        self._log_info(
            (
                f"Engine Mininet WiFi criada, "
                f"modo de link: {self.link_mode}, "
                f"SSID: {self.ssid}"
            )
        )

    def _log_info(
        self,
        message: str,
        data: dict[str, Any] | None = None,
        component: str | None = None
    ):
        """Registra uma mensagem informativa quando o nível permite."""
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
        """Registra uma mensagem de depuração quando o nível permite."""
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
        """Registra uma mensagem de erro quando o nível permite."""
        if self.log_level != "silent":
            self.logger.log(
                message,
                data=data or {},
                level="ERROR",
                component=component or self.name
            )

    def build(self):
        """Prepara o componente para execução."""
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
        """Inicia o motor concreto."""
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

        # `OVSKernelAP.start()` starts the OVS bridge.  Depending on the
        # Mininet-WiFi/hostapd version it does not guarantee that the wireless
        # BSS is ready afterwards. Verify the kernel/hostapd state and, if
        # needed, recreate master mode before attempting station association.
        self._ensure_access_points_operational()

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

        try:
            self._post_start_configuration()
        except Exception:
            self.stop()
            raise

        if self.open_cli_on_start:
            self.cli()

        return self

    def stop(self):
        """Encerra o motor concreto."""
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
        """Executa um comando dentro de um nó.

        Parâmetros:
            node_id: Identificador do nó.
            command: Comando que será executado.
        """
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
        """Abre a interface interativa do Mininet-WiFi."""
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
        """Testa a conectividade entre dois nós.

        Parâmetros:
            source: Identificador da origem.
            destination: Identificador do destino.
            count: Quantidade de elementos ou repetições.
        """
        destination_ip = self.get_ip(destination)

        if destination_ip is None:
            raise RuntimeError(f"No de destino sem IP registrado: {destination}")

        command = f"ping -c {count} {destination_ip}"

        return self.run_command(source, command)

    def refresh_connectivity(self, source: str | None = None):
        """Refaz associação e camada 2 após falha no ping.

        Parâmetros:
            source: Identificador do nó de origem.
        """
        if not self.is_running():
            raise RuntimeError(
                "A engine precisa estar em execucao para reconfigurar a conectividade."
            )
        if self.link_mode == "infrastructure":
            self._restart_access_points()
            self._force_wireless_interfaces_up()
            self._associate_stations_to_gateway(
                force_reassociate=True,
                node_ids={source} if source is not None else None,
            )
            self._enable_l2_forwarding_on_access_points()
            self._flush_arp_cache()
        else:
            self._post_start_configuration()
        return self

    def _restart_access_points(self):
        """Reinicia os pontos de acesso sem alterar a topologia."""
        for ap in self._get_access_points():
            ap.start([self.controller] if self.controller is not None else [])
        self._ensure_access_points_operational()

    @staticmethod
    def _wireless_interfaces_for_ap(ap: Any) -> list[str]:
        """Lista as interfaces sem fio associadas a um ponto de acesso."""
        params = getattr(ap, "params", {}) or {}
        configured = params.get("wlan", [])
        if isinstance(configured, str):
            configured = [configured]
        interfaces = [
            str(interface)
            for interface in configured
            if str(interface).startswith(f"{ap.name}-wlan")
        ]
        if interfaces:
            return interfaces
        interface_output = ap.cmd("iw dev").strip()
        return [
            interface
            for interface in re.findall(r"Interface\s+(\S+)", interface_output)
            if interface.startswith(f"{ap.name}-wlan")
        ]

    @staticmethod
    def _wireless_interface_type(iw_info: str) -> str | None:
        """Consulta o tipo operacional de uma interface sem fio."""
        match = re.search(r"^\s*type\s+(\S+)", iw_info, flags=re.MULTILINE)
        return match.group(1) if match else None

    @staticmethod
    def _hostapd_enabled_for_ssid(hostapd_status: str, expected_ssid: str) -> bool:
        """Informa se o hostapd apresenta um BSS ativo para o SSID."""
        fields: dict[str, str] = {}
        for line in str(hostapd_status or "").splitlines():
            key, separator, value = line.partition("=")
            if separator:
                fields[key.strip()] = value.strip()
        advertised_ssids = {
            value
            for key, value in fields.items()
            if key == "ssid" or re.fullmatch(r"ssid\[\d+\]", key)
        }
        return (
            fields.get("state", "").upper() == "ENABLED"
            and expected_ssid in advertised_ssids
        )

    @classmethod
    def _ap_operational_evidence(
        cls,
        diagnostics: dict[str, Any],
        expected_ssid: str,
    ) -> str | None:
        """Reúne evidências de que o ponto de acesso está operacional."""
        if str(diagnostics.get("interface_type") or "").lower() == "ap":
            return "kernel_interface_type_ap"
        if cls._hostapd_enabled_for_ssid(
            str(diagnostics.get("hostapd_status") or ""),
            expected_ssid,
        ):
            return "hostapd_state_enabled_for_expected_ssid"
        return None

    def _access_point_diagnostics(self, ap: Any, interface: str) -> dict[str, Any]:
        """Coleta diagnósticos de um ponto de acesso."""
        iw_info = ap.cmd(f"iw dev {interface} info").strip()
        return {
            "interface": interface,
            "interface_type": self._wireless_interface_type(iw_info),
            "iw_info": iw_info,
            "link": ap.cmd(f"ip -br link show {interface}").strip(),
            "hostapd_binary": ap.cmd("command -v hostapd").strip(),
            "hostapd_version": ap.cmd("hostapd -v 2>&1").strip(),
            "hostapd_processes": ap.cmd("pgrep -af hostapd").strip(),
            "hostapd_status": ap.cmd(
                f"hostapd_cli -i {interface} status 2>&1"
            ).strip(),
            "rfkill": ap.cmd("rfkill list 2>&1").strip(),
        }

    def _ensure_access_points_operational(self) -> dict[str, Any]:
        """Garante um BSS operacional em cada ponto de acesso."""
        operational = []
        failed = []
        for ap in self._get_access_points():
            interfaces = self._wireless_interfaces_for_ap(ap)
            if not interfaces:
                failed.append(
                    {
                        "ap": ap.name,
                        "reason": "wireless_interface_not_found",
                        "iw": ap.cmd("iw dev").strip(),
                    }
                )
                continue
            for interface in interfaces:
                expected_ssid = f"{self.ssid}_{ap.name}"
                before = self._access_point_diagnostics(ap, interface)
                before_evidence = self._ap_operational_evidence(
                    before,
                    expected_ssid,
                )
                reconfiguration_error = None
                if before_evidence is None:
                    try:
                        if not hasattr(ap, "setMasterMode"):
                            raise RuntimeError("access_point_has_no_setMasterMode")
                        ap.setMasterMode(
                            intf=interface,
                            ssid=expected_ssid,
                            mode=self.mode,
                            channel=self.channel,
                        )
                    except Exception as exc:
                        reconfiguration_error = f"{type(exc).__name__}: {exc}"
                    time.sleep(self.association_wait_seconds)
                ap.cmd(f"ip link set {interface} up")
                after = self._access_point_diagnostics(ap, interface)
                after_evidence = self._ap_operational_evidence(
                    after,
                    expected_ssid,
                )
                entry = {
                    "ap": ap.name,
                    "ssid": expected_ssid,
                    "before": before,
                    "after": after,
                    "reconfiguration_error": reconfiguration_error,
                    "operational_evidence": after_evidence,
                }
                if after_evidence is not None:
                    operational.append(entry)
                else:
                    entry["reason"] = "hostapd_did_not_create_ap_interface"
                    failed.append(entry)

        self.last_ap_report = {
            "operational": operational,
            "failed": failed,
        }
        if failed:
            raise RuntimeError(
                "mininet_ap_not_operational: "
                + json.dumps(self.last_ap_report, ensure_ascii=False, default=str)
            )
        return self.last_ap_report

    def collect_connectivity_diagnostics(self, source: str, destination: str):
        """Coleta estado de estações, servidor e OVS após falha no ping.

        Parâmetros:
            source: Identificador do nó de origem.
            destination: Identificador do nó de destino.
        """
        source_node = self.get_mininet_node(source)
        destination_node = self.get_mininet_node(destination)
        source_engine = self.engine_nodes[source]
        wlan = f"{source_engine.mininet_name}-wlan0"
        diagnostics = {
            "source": {
                "iw_link": source_node.cmd(f"iw dev {wlan} link").strip(),
                "iw_info": source_node.cmd(f"iw dev {wlan} info").strip(),
                "addresses": source_node.cmd("ip -br addr").strip(),
                "routes": source_node.cmd("ip route").strip(),
                "neighbors": source_node.cmd("ip neigh").strip(),
            },
            "destination": {
                "addresses": destination_node.cmd("ip -br addr").strip(),
                "routes": destination_node.cmd("ip route").strip(),
                "neighbors": destination_node.cmd("ip neigh").strip(),
            },
            "access_points": {},
            "ovs": {
                "show": subprocess.run(
                    ["ovs-vsctl", "show"], capture_output=True, text=True, check=False
                ).stdout.strip(),
            },
            "last_association_report": self.last_association_report,
            "last_ap_report": self.last_ap_report,
        }
        for ap in self._get_access_points():
            ap_iw = ap.cmd("iw dev").strip()
            ap_interfaces = re.findall(r"Interface\s+(\S+)", ap_iw)
            diagnostics["access_points"][ap.name] = {
                "iw": ap_iw,
                "iw_interfaces": {
                    interface: ap.cmd(f"iw dev {interface} info").strip()
                    for interface in ap_interfaces
                    if interface.startswith(f"{ap.name}-wlan")
                },
                "interfaces": ap.cmd("ip -br link").strip(),
                "ports": subprocess.run(
                    ["ovs-ofctl", "show", ap.name],
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout.strip(),
                "flows": subprocess.run(
                    ["ovs-ofctl", "dump-flows", ap.name],
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout.strip(),
            }
        return diagnostics

    def collect_link_metrics(
        self,
        source: str,
        destination: str,
        count: int = 3
    ):
        """Coleta métricas do enlace entre dois nós.

        Parâmetros:
            source: Identificador da origem.
            destination: Identificador do destino.
            count: Quantidade de elementos ou repetições.
        """
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
            "latency_measurement_source": None,
            "configured_bandwidth_mbps": self.default_bw,
            "bandwidth_measurement_source": "mininet_link_configuration",
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
            # `ping` reports round-trip time. The physical radio model expects
            # one-way latency separately from RTT.
            metrics["latency_ms"] = metrics["rtt_avg_ms"] / 2.0
            metrics["latency_measurement_source"] = "derived_one_way_from_ping_rtt"

        else:
            times = re.findall(r"time[=<]([\d.]+)\s*ms", output)

            if times:
                values = [float(value) for value in times]
                metrics["rtt_min_ms"] = min(values)
                metrics["rtt_avg_ms"] = sum(values) / len(values)
                metrics["rtt_max_ms"] = max(values)
                metrics["latency_ms"] = metrics["rtt_avg_ms"] / 2.0
                metrics["latency_measurement_source"] = "derived_one_way_from_ping_samples"

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

    def iperf(
        self,
        source: str,
        destination: str,
        seconds: int = 5
    ):
        """Mede a vazão entre dois nós.

        Parâmetros:
            source: Identificador da origem.
            destination: Identificador do destino.
            seconds: Valor de tempo, em segundos.
        """
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

    @staticmethod
    def _application_trace_from_wire_messages(
        wire_messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Mantém registros lógicos; o kernel fornece o controle TCP."""
        trace: list[dict[str, Any]] = []
        for message in wire_messages:
            protocol = str(message.get("protocol") or "")
            size = int(message.get("logical_payload_bytes") or 0)
            if protocol == "tcp" or size == 0:
                continue
            direction = str(message.get("direction") or "")
            if direction not in {"iot_to_server", "server_to_iot"}:
                raise ValueError(f"Direcao de mensagem invalida: {direction}")
            trace.append(
                {
                    "sequence": int(message.get("sequence") or len(trace) + 1),
                    "direction": direction,
                    "protocol": protocol,
                    "logical_type": str(message.get("logical_type") or "unknown"),
                    "logical_payload_bytes": size,
                }
            )
        if not trace:
            raise ValueError("O ciclo nao possui payload logico para transmitir.")
        return trace

    @staticmethod
    def _last_json_object(output: str) -> dict[str, Any]:
        """Extrai o último objeto JSON válido da saída de um comando."""
        for line in reversed(str(output or "").splitlines()):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
        return {"delivered": False, "error": "transport_probe_returned_no_json"}

    @staticmethod
    def _wait_for_tcpdump_ready(
        process: subprocess.Popen,
        *,
        timeout_seconds: float = 3.0,
    ) -> tuple[bool, str]:
        """Aguarda a libpcap confirmar o filtro de captura."""
        if process.stderr is None:
            return False, "tcpdump_stderr_pipe_unavailable"
        deadline = time.monotonic() + timeout_seconds
        messages: list[str] = []
        while time.monotonic() < deadline:
            if process.poll() is not None:
                remainder = process.stderr.read()
                if remainder:
                    messages.append(remainder)
                return False, "".join(messages).strip()
            remaining = max(0.0, deadline - time.monotonic())
            readable, _, _ = select.select(
                [process.stderr], [], [], min(0.1, remaining)
            )
            if not readable:
                continue
            line = process.stderr.readline()
            if not line:
                continue
            messages.append(line)
            lowered = line.lower()
            if "listening on" in lowered or "data link type" in lowered:
                # TextIOWrapper can read both tcpdump startup lines into its
                # internal buffer at once. In that case select() no longer
                # reports the fd as readable for the already-buffered
                # ``listening on`` line. ``data link type`` is emitted only
                # after pcap activation, so it is a sufficient readiness
                # marker for this short-lived capture.
                return True, "".join(messages).strip()
        return False, "".join(messages).strip() or "tcpdump_ready_timeout"

    @staticmethod
    def _parse_tcpdump_verbose(
        output: str,
        source_ip: str,
        transport: str = "tcp",
    ) -> dict[str, Any]:
        """Resume bytes e instantes dos pacotes IPv4 informados pelo tcpdump."""
        packets: list[dict[str, Any]] = []
        header_pattern = re.compile(
            # A concrete interface starts directly with ``IP``. Linux ``any``
            # adds interface and In/Out columns. With ``-v``, tcpdump may wrap
            # the source/destination endpoints onto the following line.
            r"^(?P<timestamp>\d+(?:\.\d+)?)\s+"
            r"(?:(?P<interface>\S+)\s+(?P<packet_direction>In|Out)\s+)?IP\s+"
            r"\(.*length\s+(?P<length>\d+)\)\s*(?P<remainder>.*)$"
        )
        endpoint_pattern = re.compile(
            # Non-initial IPv4 fragments have no TCP/UDP port in tcpdump's
            # rendering. Ports are optional so every fragment contributes to
            # the directional byte accounting.
            r"(?P<src>\d+(?:\.\d+){3})(?:\.\d+)?\s+>\s+"
            r"(?P<dst>\d+(?:\.\d+){3})(?:\.\d+)?:"
        )
        pending: dict[str, Any] | None = None

        def append_packet(header: dict[str, Any], endpoint: re.Match[str]) -> None:
            """Acumula estatísticas de um pacote capturado pelo tcpdump.

            Parâmetros:
                header: Parâmetro usado pela operação.
                endpoint: Parâmetro usado pela operação.
            """
            source = endpoint.group("src")
            packets.append({
                "timestamp_seconds": float(header["timestamp"]),
                "ip_packet_bytes": int(header["length"]),
                "direction": (
                    "iot_to_server" if source == source_ip else "server_to_iot"
                ),
                "capture_interface": header.get("interface"),
                "capture_packet_direction": header.get("packet_direction"),
            })

        for line in str(output or "").splitlines():
            stripped = line.strip()
            header_match = header_pattern.search(stripped)
            if header_match:
                pending = header_match.groupdict()
                endpoint_match = endpoint_pattern.search(
                    str(pending.get("remainder") or "")
                )
                if endpoint_match:
                    append_packet(pending, endpoint_match)
                    pending = None
                continue
            if pending is not None:
                endpoint_match = endpoint_pattern.search(stripped)
                if endpoint_match:
                    append_packet(pending, endpoint_match)
                    pending = None
        tx_bytes = sum(
            packet["ip_packet_bytes"] for packet in packets
            if packet["direction"] == "iot_to_server"
        )
        rx_bytes = sum(packet["ip_packet_bytes"] for packet in packets) - tx_bytes
        timestamps = [packet["timestamp_seconds"] for packet in packets]
        return {
            "capture_available": bool(packets),
            "packet_count": len(packets),
            "iot_tx_ip_bytes": tx_bytes,
            "iot_rx_ip_bytes": rx_bytes,
            "capture_duration_seconds": (
                max(timestamps) - min(timestamps) if len(timestamps) > 1 else 0.0
            ),
            "byte_boundary": (
                f"pcap_ipv4_total_length_including_{transport}_ip_headers"
            ),
            "timestamp_boundary": (
                f"first_to_last_captured_{transport}_packet_not_radio_busy_time"
            ),
            "packets": packets,
        }

    def execute_wire_messages(
        self,
        source: str,
        destination: str,
        wire_messages: list[dict[str, Any]],
        *,
        transfer_id: str | None = None,
        timeout_seconds: float = 10.0,
        port: int | None = None,
        capture_packets: bool = False,
        pcap_output_path: str | Path | None = None,
        capture_endpoint: str = "destination",
    ) -> dict[str, Any]:
        """Transmite um traço modelado pelo caminho real do Mininet.

        Parâmetros:
            source: Identificador do nó de origem.
            destination: Identificador do nó de destino.
            wire_messages: Mensagens lógicas que serão transmitidas.
            transfer_id: Identificador único da transferência.
            timeout_seconds: Tempo máximo permitido para a transferência.
            port: Porta de transporte usada pela sonda.
            capture_packets: Indica se o tráfego deve ser capturado.
            pcap_output_path: Caminho onde o arquivo PCAP será salvo.
            capture_endpoint: Extremidade da comunicação onde a captura será feita.

        Retorna:
            Relatório de entrega, duração e captura da transferência.
        """
        if not self.is_running():
            raise RuntimeError("A engine precisa estar em execucao para transmitir dados.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds deve ser maior que zero")
        if capture_endpoint not in {"source", "destination"}:
            raise ValueError("capture_endpoint must be 'source' or 'destination'")
        source_node = self.get_mininet_node(source)
        destination_node = self.get_mininet_node(destination)
        if source_node is None:
            raise KeyError(f"No de origem nao encontrado na engine: {source}")
        if destination_node is None:
            raise KeyError(f"No de destino nao encontrado na engine: {destination}")
        destination_ip = self.get_ip(destination)
        if destination_ip is None:
            raise RuntimeError(f"No de destino sem IP registrado: {destination}")
        source_ip = self.get_ip(source)
        if source_ip is None:
            raise RuntimeError(f"No de origem sem IP registrado: {source}")

        trace = self._application_trace_from_wire_messages(wire_messages)
        application_protocols = {
            str(row.get("protocol") or "").lower() for row in trace
        }
        transport = (
            "udp"
            if any(protocol.startswith("coap") for protocol in application_protocols)
            else "tcp"
        )
        identifier = transfer_id or str(uuid.uuid4())
        if port is None:
            port = 39000 + self._transport_port_counter % 1000
            self._transport_port_counter += 1
        if not 1 <= port <= 65535:
            raise ValueError("porta de transporte fora do intervalo valido")
        encoded_plan = base64.urlsafe_b64encode(
            json.dumps(trace, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ).decode("ascii")
        module = "pqc_iot_simulator.pqc_iot_sim.transport_probe"
        common = [
            "--port", str(port),
            "--plan-base64", encoded_plan,
            "--transfer-id", identifier,
            "--timeout", str(timeout_seconds),
            "--transport", transport,
        ]
        server_command = [
            "python3", "-m", module, "server", "--host", destination_ip, *common
        ]
        udp_ready_path: Path | None = None
        if transport == "udp":
            udp_ready_path = Path("/tmp") / (
                f"pqc-iot-udp-ready-{uuid.uuid4().hex}"
            )
            udp_ready_path.unlink(missing_ok=True)
            server_command.extend(["--ready-file", str(udp_ready_path)])
        client_command = [
            "python3", "-m", module, "client", "--host", destination_ip,
            *common, "--bind-host", source_ip,
        ]
        capture_process = None
        capture_path: Path | None = None
        capture_temporary = False
        # Packet sockets attached to a Mininet-WiFi Station can miss traffic in
        # some mac80211_hwsim/namespace combinations even when the station's
        # application socket is delivered correctly. The server is a regular
        # Mininet Host backed by a veth and provides a reliable capture point.
        # Capture its concrete interface: Linux cooked captures on `any` store
        # a namespace-local ifindex that tcpdump can mislabel when decoded in
        # the container's root namespace.
        capture_node = (
            source_node if capture_endpoint == "source" else destination_node
        )
        capture_namespace = f"{capture_endpoint}_mininet_host"
        capture_intf = capture_node.defaultIntf()
        if capture_intf is None:
            raise RuntimeError(
                f"Mininet capture endpoint has no interface: {capture_endpoint}"
            )
        capture_interface = capture_intf.name
        capture_interface_selection = "endpoint_default_interface"
        endpoint_filter = f"host {source_ip} and host {destination_ip}"
        capture_filter = (
            f"{endpoint_filter} and (udp port {port} or "
            "(ip[6:2] & 0x1fff != 0))"
            if transport == "udp"
            else f"{endpoint_filter} and tcp port {port}"
        )
        capture_error: str | None = None
        capture_startup_stderr = ""
        capture_runtime_stderr = ""
        if capture_packets:
            if pcap_output_path is None:
                capture_path = Path("/tmp") / f"pqc-iot-{identifier}.pcap"
                capture_temporary = True
            else:
                capture_path = Path(pcap_output_path)
                capture_path.parent.mkdir(parents=True, exist_ok=True)
            capture_process = capture_node.popen(
                [
                    "tcpdump", "--immediate-mode", "-U", "-n", "-s", "0",
                    "-i", capture_interface,
                    capture_filter, "-w", str(capture_path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            capture_ready, capture_startup_stderr = self._wait_for_tcpdump_ready(
                capture_process
            )
            if not capture_ready:
                if capture_process.poll() is None:
                    capture_process.kill()
                _, capture_runtime_stderr = capture_process.communicate()
                detail = "\n".join(
                    part for part in (
                        capture_startup_stderr, capture_runtime_stderr
                    ) if part
                ).strip()
                raise RuntimeError(
                    "tcpdump_not_ready_before_transport: "
                    + (detail or "no diagnostic output")
                )
            time.sleep(0.05)
        server_process = destination_node.popen(
            server_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if transport == "udp":
            # Unlike TCP connect(), the first UDP send does not wait for a
            # listener. Synchronize on the bind completing so process startup
            # is never mistaken for packet loss in a zero-loss experiment.
            ready_deadline = time.monotonic() + min(timeout_seconds, 3.0)
            while (
                udp_ready_path is not None
                and not udp_ready_path.exists()
                and server_process.poll() is None
                and time.monotonic() < ready_deadline
            ):
                time.sleep(0.01)
            udp_ready = bool(udp_ready_path and udp_ready_path.exists())
            if udp_ready_path is not None:
                udp_ready_path.unlink(missing_ok=True)
            if not udp_ready:
                if server_process.poll() is None:
                    server_process.kill()
                server_stdout, server_stderr = server_process.communicate()
                if capture_process is not None and capture_process.poll() is None:
                    capture_process.send_signal(signal.SIGINT)
                    capture_process.communicate(timeout=2.0)
                raise RuntimeError(
                    "udp_server_not_ready_before_transport: "
                    + (server_stderr.strip() or server_stdout.strip() or "timeout")
                )
        client_process = None
        client_stdout = client_stderr = server_stdout = server_stderr = ""
        timed_out = False
        try:
            client_process = source_node.popen(
                client_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            client_stdout, client_stderr = client_process.communicate(
                timeout=timeout_seconds + 2.0
            )
            server_stdout, server_stderr = server_process.communicate(
                timeout=timeout_seconds + 2.0
            )
        except subprocess.TimeoutExpired:
            timed_out = True
            if client_process is not None:
                client_process.kill()
                client_stdout, client_stderr = client_process.communicate()
            server_process.kill()
            server_stdout, server_stderr = server_process.communicate()
        finally:
            if capture_process is not None:
                # The application trace is intentionally very short. Give
                # libpcap time to drain packets already queued by the kernel
                # before requesting a clean, flushed shutdown.
                if capture_process.poll() is None:
                    time.sleep(0.1)
                if capture_process.poll() is None:
                    capture_process.send_signal(signal.SIGINT)
                try:
                    _, capture_runtime_stderr = capture_process.communicate(timeout=2.0)
                except subprocess.TimeoutExpired:
                    capture_process.kill()
                    _, capture_runtime_stderr = capture_process.communicate()
                if capture_process.returncode not in {0, 130}:
                    capture_error = capture_runtime_stderr.strip() or (
                        f"tcpdump_returncode_{capture_process.returncode}"
                    )

        client_report = self._last_json_object(client_stdout)
        server_report = self._last_json_object(server_stdout)
        client_returncode = client_process.returncode if client_process is not None else None
        server_returncode = server_process.returncode
        delivered = bool(
            not timed_out
            and client_returncode == 0
            and server_returncode == 0
            and client_report.get("delivered")
            and server_report.get("delivered")
        )
        logical_bytes = sum(int(row["logical_payload_bytes"]) for row in trace)
        tx_bytes = sum(
            int(row["logical_payload_bytes"])
            for row in trace if row["direction"] == "iot_to_server"
        )
        rx_bytes = logical_bytes - tx_bytes
        duration = client_report.get("duration_seconds")
        logical_path = (
            self.get_routed_path(source, destination)
            if self.link_mode == "routed_logical_topology"
            else [source, destination]
        )
        route_lookup = (
            source_node.cmd(f"ip route get {destination_ip}").strip()
            if self.link_mode == "routed_logical_topology"
            else None
        )
        packet_capture: dict[str, Any] = {
            "capture_requested": capture_packets,
            "capture_available": False,
            "capture_interface": capture_interface,
            "capture_interface_selection": capture_interface_selection,
            "capture_filter": capture_filter,
            "capture_namespace": capture_namespace,
            "capture_node": (
                source if capture_endpoint == "source" else destination
            ),
            "tcpdump_startup_stderr": capture_startup_stderr,
            "tcpdump_runtime_stderr": capture_runtime_stderr,
            "pcap_retained": bool(capture_path and not capture_temporary),
            "pcap_path": str(capture_path) if capture_path and not capture_temporary else None,
            "error": capture_error,
        }
        if capture_packets and capture_path and capture_path.is_file() and capture_path.stat().st_size:
            decoded = subprocess.run(
                ["tcpdump", "-n", "-tt", "-v", "-r", str(capture_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            parsed = self._parse_tcpdump_verbose(
                decoded.stdout,
                self.get_ip(source) or "",
                transport=transport,
            )
            packet_capture.update(parsed)
            if decoded.returncode != 0 and not packet_capture.get("error"):
                packet_capture["error"] = decoded.stderr.strip()
            elif not parsed.get("capture_available") and not packet_capture.get("error"):
                packet_capture["error"] = (
                    f"capture_contains_no_decodable_ipv4_{transport}_packets"
                )
        if capture_temporary and capture_path and capture_path.exists():
            capture_path.unlink()
        result = {
            "transfer_id": identifier,
            "delivered": delivered,
            "status": "delivered" if delivered else "not_delivered",
            "transport_kind": (
                f"real_{transport}_socket_between_mininet_namespaces"
            ),
            "payload_semantics": (
                "deterministic_size_equivalent_application_trace_not_"
                "interoperable_application_server"
            ),
            "wire_accounting": (
                "logical_payload_bytes_sent_kernel_headers_not_captured_"
                "probe_framing_reported_separately"
            ),
            "source": source,
            "destination": destination,
            "destination_ip": destination_ip,
            "source_bind_ip": source_ip,
            "destination_port": port,
            "logical_path": logical_path,
            "logical_hop_count": len(logical_path) - 1,
            "multi_hop_forwarding_required": len(logical_path) > 2,
            "link_mode": self.link_mode,
            "source_route_lookup": route_lookup,
            "message_count": len(trace),
            "logical_payload_bytes": logical_bytes,
            "iot_to_server_logical_payload_bytes": tx_bytes,
            "server_to_iot_logical_payload_bytes": rx_bytes,
            "probe_record_framing_bytes": len(trace) * 8 if transport == "tcp" else 0,
            "probe_completion_bytes": 2,
            "duration_seconds": duration,
            "application_goodput_bps": (
                logical_bytes * 8.0 / float(duration)
                if duration is not None and float(duration) > 0 else None
            ),
            "timed_out": timed_out,
            "trace": trace,
            "client": client_report,
            "server": server_report,
            "client_returncode": client_returncode,
            "server_returncode": server_returncode,
            "client_stderr": client_stderr.strip(),
            "server_stderr": server_stderr.strip(),
            "packet_capture": packet_capture,
        }
        self._log_info(
            (
                f"Transmissao {transport.upper()} real entre namespaces "
                f"{source} e {destination}: "
                f"status={result['status']}, mensagens={len(trace)}, "
                f"payload_logico={logical_bytes} bytes"
            )
        )
        return result

    def get_mininet_node(self, node_id: str):
        """Retorna o objeto Mininet associado ao nó lógico.

        Parâmetros:
            node_id: Identificador do nó.
        """
        return self.mininet_nodes.get(node_id)

    def get_ip(self, node_id: str):
        """Retorna o endereço IP atribuído ao nó.

        Parâmetros:
            node_id: Identificador do nó.
        """
        engine_node = self.engine_nodes.get(node_id)

        if engine_node is None:
            return None

        if engine_node.ip is None:
            return None

        return engine_node.ip.split("/")[0]

    def export_mapping_json(self, output_path: str):
        """Exporta o mapeamento lógico para JSON.

        Parâmetros:
            output_path: Caminho do arquivo de saída.
        """
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
        """Mapeia enlaces lógicos para enlaces do motor."""
        if self.link_mode == "infrastructure":
            return self._map_infrastructure_links()

        if self.link_mode in {"logical_topology", "routed_logical_topology"}:
            return self._map_logical_topology_links()

        raise ValueError(f"Modo de link nao suportado: {self.link_mode}")

    def _map_infrastructure_links(self):
        """Mapeia os enlaces do modo de infraestrutura."""
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
        """Mapeia exatamente os enlaces da topologia lógica."""
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
                    "link_mode": self.link_mode,
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
        """Cria no Mininet todos os nós previamente mapeados."""
        if self.net is None:
            raise RuntimeError("Objeto Mininet WiFi nao foi criado.")

        self.mininet_nodes = {}

        for node_id, engine_node in self.engine_nodes.items():
            node_type = engine_node.node_type
            mininet_name = engine_node.mininet_name
            ip = engine_node.ip
            position = engine_node.metadata.get("position")

            if self.link_mode == "routed_logical_topology":
                # Every logical vertex is a Linux namespace with L3
                # forwarding. Roles are retained in metadata, while avoiding
                # hidden AP associations that would create topology shortcuts.
                mininet_node = self._add_host(
                    name=mininet_name,
                    ip=ip,
                )
            elif node_type == "iot":
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
        """Adiciona uma estação IoT ao Mininet-WiFi."""
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
        """Adiciona um ponto de acesso ao Mininet-WiFi."""
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
        """Adiciona um host cabeado ao Mininet."""
        params = {}

        if ip:
            params["ip"] = ip

        return self.net.addHost(
            name,
            **params
        )

    def _configure_wifi_nodes(self):
        """Aplica a configuração sem fio aos nós do Mininet."""
        if self.net is None:
            raise RuntimeError("Objeto Mininet WiFi nao foi criado.")

        self._log_debug(
            "Configurando nos WiFi no Mininet"
        )

        self.net.configureWifiNodes()

    def _create_mininet_links(self):
        """Cria no Mininet os enlaces mapeados."""
        if self.net is None:
            raise RuntimeError("Objeto Mininet WiFi nao foi criado.")

        created_links = []
        self.created_link_objects = []

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

            self.created_link_objects.append({
                "source": link.source,
                "target": link.target,
                "link": created,
            })

            created_links.append(
                {
                    "origem": link.source,
                    "destino": link.target,
                    "origem_mininet": link.source_mininet,
                    "destino_mininet": link.target_mininet,
                    "criado": created is not None
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
        """Cria um enlace e acrescenta contexto quando ocorre uma falha."""
        existing_link_ids = {
            id(link) for link in list(getattr(self.net, "links", []) or [])
        }

        def resolve_created_link(created: Any) -> Any:
            """Localiza as interfaces concretas do enlace recém-criado.

            Parâmetros:
                created: Objeto retornado diretamente por addLink.

            Retorna:
                Enlace criado ou None quando ele não pode ser localizado.
            """
            if created is not None:
                return created
            # Some Mininet-WiFi releases append the link to ``net.links`` but
            # return None from addLink(). Recover that object so routed mode
            # can orient and address its two interfaces.
            links = list(getattr(self.net, "links", []) or [])
            for candidate in reversed(links):
                if id(candidate) not in existing_link_ids:
                    return candidate
            # Last-resort compatibility for network implementations that do
            # not expose a global links list but expose node connections.
            connections_to = getattr(source_node, "connectionsTo", None)
            if callable(connections_to):
                connections = list(connections_to(target_node) or [])
                if connections:
                    intf1, intf2 = connections[-1]
                    return type(
                        "RecoveredMininetLink",
                        (),
                        {"intf1": intf1, "intf2": intf2},
                    )()
            return None

        try:
            return resolve_created_link(
                self.net.addLink(
                    source_node,
                    target_node,
                    **link_params
                )
            )

        except TypeError:
            source_name = getattr(source_node, "name", str(source_node))
            target_name = getattr(target_node, "name", str(target_node))

            self._log_debug(
                (
                    f"Criacao de link com parametros falhou entre {source_name} e {target_name}. "
                    f"Tentando criar o link sem parametros"
                )
            )

            return resolve_created_link(
                self.net.addLink(
                    source_node,
                    target_node
                )
            )

    def _build_link_params(self, link):
        """Monta os parâmetros de banda, atraso e perda de um enlace."""
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
        """Atribui endereços IP aos nós do Mininet."""
        if self.link_mode == "routed_logical_topology":
            for index, node_id in enumerate(self.network.topology_data.nodes, 1):
                if index > 254:
                    raise RuntimeError(
                        "routed_logical_topology supports at most 254 nodes"
                    )
                self.engine_nodes[node_id].ip = f"10.255.0.{index}/32"
            self._log_debug(
                "Enderecos loopback /32 atribuidos para topologia roteada"
            )
            return

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
        """Atribui posições espaciais aos nós sem fio."""
        if not self.auto_set_positions:
            self._log_debug(
                "Atribuicao automatica de posicoes ignorada"
            )

            return

        rows = self.network.config.topology_params.get("rows")
        cols = self.network.config.topology_params.get("cols")

        spacing_x = self.position_spacing_m
        spacing_y = self.position_spacing_m

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
        """Aplica roteamento, associação e ajustes após iniciar a rede."""
        if self.link_mode == "infrastructure":
            self._force_wireless_interfaces_up()
            association = self._associate_stations_to_gateway()
            if association["failed"]:
                raise RuntimeError(
                    "mininet_station_association_failed: "
                    + json.dumps(association["failed"], ensure_ascii=False, default=str)
                )
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

        if self.link_mode == "routed_logical_topology":
            self._configure_routed_logical_topology()
            self._flush_arp_cache()
            self._log_info(
                "Topologia logica configurada com sub-redes por enlace, "
                "enderecos loopback e rotas multi-hop"
            )
            return

        self._log_debug(
            f"Configuracao pos inicio ignorada para o modo de link {self.link_mode}"
        )

    def _configure_routed_logical_topology(self) -> dict[str, Any]:
        """Configura encaminhamento real de camada 3 em cada aresta lógica."""
        if self.link_mode != "routed_logical_topology":
            raise RuntimeError("routed topology configuration requested in wrong mode")
        if len(self.created_link_objects) != len(self.engine_links):
            raise RuntimeError("created Mininet links do not match logical links")

        edge_endpoints: dict[frozenset[str], dict[str, dict[str, str]]] = {}
        for edge_index, record in enumerate(self.created_link_objects):
            if edge_index >= 16_384:
                raise RuntimeError("too many links for routed /30 address plan")
            source = str(record["source"])
            target = str(record["target"])
            link = record["link"]
            if link is None or not hasattr(link, "intf1") or not hasattr(link, "intf2"):
                raise RuntimeError(f"Mininet link object unavailable for {source}-{target}")
            source_node = self.mininet_nodes[source]
            target_node = self.mininet_nodes[target]
            intf1, intf2 = link.intf1, link.intf2
            if getattr(intf1, "node", None) is source_node:
                source_intf, target_intf = intf1, intf2
            elif getattr(intf2, "node", None) is source_node:
                source_intf, target_intf = intf2, intf1
            else:
                raise RuntimeError(f"cannot orient Mininet link {source}-{target}")

            address_number = edge_index * 4
            third = address_number // 256
            fourth = address_number % 256
            source_ip = f"172.16.{third}.{fourth + 1}"
            target_ip = f"172.16.{third}.{fourth + 2}"
            source_node.cmd(f"ip addr flush dev {source_intf.name}")
            target_node.cmd(f"ip addr flush dev {target_intf.name}")
            source_node.cmd(
                f"ip addr add {source_ip}/30 dev {source_intf.name}"
            )
            target_node.cmd(
                f"ip addr add {target_ip}/30 dev {target_intf.name}"
            )
            source_node.cmd(f"ip link set dev {source_intf.name} up")
            target_node.cmd(f"ip link set dev {target_intf.name} up")
            edge_endpoints[frozenset((source, target))] = {
                source: {
                    "interface": source_intf.name,
                    "address": source_ip,
                    "peer_address": target_ip,
                },
                target: {
                    "interface": target_intf.name,
                    "address": target_ip,
                    "peer_address": source_ip,
                },
            }

        for node_id, node in self.mininet_nodes.items():
            loopback = self.get_ip(node_id)
            if loopback is None:
                raise RuntimeError(f"loopback address missing for {node_id}")
            node.cmd("ip link set lo up")
            node.cmd(f"ip addr replace {loopback}/32 dev lo")
            node.cmd("sysctl -q -w net.ipv4.ip_forward=1")
            node.cmd("sysctl -q -w net.ipv4.conf.all.rp_filter=0")
            node.cmd("sysctl -q -w net.ipv4.conf.default.rp_filter=0")

        route_count = 0
        paths: dict[str, list[str]] = {}
        for source in self.network.topology_data.nodes:
            source_node = self.mininet_nodes[source]
            for destination in self.network.topology_data.nodes:
                if source == destination:
                    continue
                path = list(nx.shortest_path(
                    self.network.graph, source=source, target=destination
                ))
                if len(path) < 2:
                    raise RuntimeError(f"invalid routed path {source}->{destination}")
                next_hop = path[1]
                edge = edge_endpoints[frozenset((source, next_hop))]
                endpoint = edge[source]
                destination_ip = self.get_ip(destination)
                source_node.cmd(
                    f"ip route replace {destination_ip}/32 "
                    f"via {endpoint['peer_address']} dev {endpoint['interface']}"
                )
                route_count += 1
                paths[f"{source}->{destination}"] = path

        report = {
            "mode": self.link_mode,
            "nodes": len(self.mininet_nodes),
            "links": len(edge_endpoints),
            "routes": route_count,
            "paths": paths,
            "addressing": "per_link_172_16_0_0_16_slash30_and_10_255_0_0_24_loopbacks",
            "forwarding": "linux_ipv4_static_shortest_path_routes",
        }
        self.set_runtime_object("routed_topology_report", report)
        return report

    def get_routed_path(self, source: str, destination: str) -> list[str]:
        """Retorna o caminho roteado entre origem e destino.

        Parâmetros:
            source: Identificador da origem.
            destination: Identificador do destino.

        Retorna:
            Lista com os elementos produzidos.
        """
        if self.link_mode != "routed_logical_topology":
            raise RuntimeError("routed path is only available in routed mode")
        return list(nx.shortest_path(
            self.network.graph, source=source, target=destination
        ))

    def _force_wireless_interfaces_up(self):
        """Ativa as interfaces sem fio que estiverem inativas."""
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

    def _associate_stations_to_gateway(
        self,
        force_reassociate: bool = False,
        node_ids: set[str] | None = None,
    ):
        """Associa as estações IoT ao ponto de acesso do gateway."""
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
            and (node_ids is None or node_id in node_ids)
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
                ssid=ssid,
                force_reassociate=force_reassociate,
            )

            if association_result["connected"]:
                associated.append(association_result)
            else:
                failed.append(association_result)

        # mac80211_hwsim completes associations asynchronously. In particular,
        # the kernel can report EINPROGRESS immediately after `iw connect` and
        # finish the association a few seconds later. Settle all pending
        # stations together before recording a failure or sending traffic.
        deadline = time.monotonic() + max(8.0, 3.0 * self.association_wait_seconds)
        while failed and time.monotonic() < deadline:
            still_pending = []
            for result in failed:
                station = self.mininet_nodes.get(result["node_id"])
                if station is None:
                    still_pending.append(result)
                    continue
                wlan = result["interface"]
                link_status = station.cmd(f"iw dev {wlan} link").strip()
                result["link_status"] = link_status
                if "Connected to" in link_status:
                    result["connected"] = True
                    result["route_status"] = station.cmd("ip route").strip()
                    result["addr_status"] = station.cmd(
                        f"ip addr show {wlan}"
                    ).strip()
                    associated.append(result)
                else:
                    still_pending.append(result)
            failed = still_pending
            if failed:
                time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))

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
        self.last_association_report = {
            "associated": associated,
            "failed": failed,
            "force_reassociate": force_reassociate,
        }
        return self.last_association_report

    def _force_station_connection_to_ap(
        self,
        node_id: str,
        station: Any,
        ap: Any,
        wlan: str,
        ssid: str,
        force_reassociate: bool = False,
    ):
        """Força a associação de uma estação ao ponto de acesso."""
        outputs = {}

        try:
            if not force_reassociate and hasattr(station, "setAssociation"):
                result = station.setAssociation(ap)
                outputs["setAssociation"] = str(result)

        except Exception as exc:
            outputs["setAssociation_error"] = str(exc)

        time.sleep(self.association_wait_seconds)

        link_status = station.cmd(f"iw dev {wlan} link").strip()
        connected = "Connected to" in link_status

        # Keep the Mininet-WiFi-native association on initial startup. After a
        # failed end-to-end ping, force a kernel-level reassociation; some
        # versions report an association object before the data path works.
        if force_reassociate or not connected:
            if force_reassociate:
                command = f"iw dev {wlan} disconnect"
                output = station.cmd(command)
                outputs[command] = output.strip()
                time.sleep(0.5)
            command = f"ip link set {wlan} up"
            output = station.cmd(command)
            outputs[command] = output.strip()
            time.sleep(0.5)
            scan_output = station.cmd(f"iw dev {wlan} scan").strip()
            outputs["scan_ssid_visible"] = ssid in scan_output
            outputs["scan_output"] = scan_output
            for command in (
                f"iw dev {wlan} connect -w {ssid}",
                f"ip link set {wlan} up",
            ):
                output = station.cmd(command)
                outputs[command] = output.strip()
            time.sleep(self.association_wait_seconds)
            link_status = station.cmd(f"iw dev {wlan} link").strip()
            connected = "Connected to" in link_status

        route_status = station.cmd("ip route").strip()
        addr_status = station.cmd(f"ip addr show {wlan}").strip()

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
        """Limpa a cache ARP dos nós do Mininet."""
        results = {}

        for node_id, node in self.mininet_nodes.items():
            output = node.cmd("ip neigh flush all")
            results[node_id] = output.strip()

        self._log_debug(
            f"Cache ARP apagado nos nos da engine, total: {len(results)}"
        )

    def _enable_l2_forwarding_on_access_points(self):
        """Ativa encaminhamento de camada 2 nos pontos de acesso."""
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
        """Valida o modo usado para criar os enlaces."""
        if self.link_mode not in self.valid_link_modes:
            raise ValueError(
                f"Modo de link invalido: {self.link_mode}. "
                f"Use um destes: {self.valid_link_modes}"
            )

    def _count_nodes_by_type(self, node_type: str):
        """Conta os nós mapeados por tipo."""
        return sum(
            1 for node in self.engine_nodes.values()
            if node.node_type == node_type
        )

    def _get_access_points(self):
        """Retorna os pontos de acesso criados no Mininet."""
        if self.link_mode == "routed_logical_topology":
            return []
        aps = []

        for node_id, engine_node in self.engine_nodes.items():
            if engine_node.node_type == "gateway":
                mininet_node = self.mininet_nodes.get(node_id)

                if mininet_node is not None:
                    aps.append(mininet_node)

        return aps

    def _check_root_permission(self):
        """Confirma que a execução possui privilégios de superusuário."""
        if hasattr(os, "geteuid") and os.geteuid() != 0:
            uid = os.geteuid()
            message = f"Mininet WiFi precisa ser executado com sudo, UID atual: {uid}"

            self._log_error(message)

            raise PermissionError(message)

    def _import_mininet_wifi_modules(self):
        """Importa os módulos exigidos do Mininet-WiFi."""
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
