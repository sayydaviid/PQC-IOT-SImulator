"""Combina observações do Mininet com métricas dos ciclos IoT."""

from __future__ import annotations

from typing import Any, Mapping


def apply_mininet_transport_observation(
    row: dict[str, Any],
    observation: Mapping[str, Any],
    *,
    communication_correction_factor: float = 1.0,
) -> None:
    """Usa a entrega do Mininet como referência e adiciona energia acoplada ao PCAP.

    Parâmetros:
        row: Dicionário de métricas do ciclo modelado.
        observation: Observação de transporte produzida pelo Mininet.
        communication_correction_factor: Fator aplicado à energia de comunicação estimada.
    """
    if communication_correction_factor <= 0:
        raise ValueError("communication_correction_factor must be greater than zero")

    modeled_delivered = bool(row.get("delivered"))
    observed_delivered = bool(observation.get("delivered"))
    row.update(
        {
            "modeled_delivered": modeled_delivered,
            "mininet_delivered": observed_delivered,
            "delivered": observed_delivered,
            "status": "delivered" if observed_delivered else "not_delivered_mininet",
            "mininet_required": True,
            "mininet_executed": True,
            "mininet_payload_transmission_executed": True,
            "mininet_transport_kind": observation.get("transport_kind"),
            "mininet_payload_semantics": observation.get("payload_semantics"),
            "mininet_transport_duration_seconds": observation.get("duration_seconds"),
            "mininet_application_goodput_bps": observation.get(
                "application_goodput_bps"
            ),
            "mininet_logical_path": observation.get("logical_path"),
            "mininet_logical_hop_count": observation.get("logical_hop_count"),
            "mininet_observed_logical_payload_bytes": observation.get(
                "logical_payload_bytes"
            ),
            "mininet_message_count": observation.get("message_count"),
            "mininet_observation": dict(observation),
            "network_execution_interpretation": (
                "observed_mininet_network_execution_with_literature_"
                "parameterized_device_energy"
            ),
        }
    )
    if not observed_delivered:
        row["energy_per_delivered_message_j"] = None

    capture = dict(observation.get("packet_capture") or {})
    row["pcap_capture_requested"] = bool(capture.get("capture_requested"))
    row["pcap_capture_available"] = bool(capture.get("capture_available"))
    row["pcap_capture"] = capture
    row["communication_correction_factor"] = communication_correction_factor
    if not capture.get("capture_available"):
        row["capture_coupled_energy_status"] = (
            "unavailable_original_model_energy_preserved"
        )
        row["energy_total_capture_coupled_j"] = None
        return

    bitrate = float(row.get("effective_bitrate_bps") or 0.0)
    efficiency = float(row.get("regulator_efficiency") or 0.0)
    if bitrate <= 0 or not 0 < efficiency <= 1:
        row["capture_coupled_energy_status"] = (
            "invalid_bitrate_or_regulator_efficiency"
        )
        row["energy_total_capture_coupled_j"] = None
        return

    events = list(row.get("energy_events") or [])

    def wire_events(component: str) -> list[Mapping[str, Any]]:
        """Transforma mensagens lógicas em eventos observados no PCAP.

        Parâmetros:
            component: Direção energética procurada, como tx ou rx.

        Retorna:
            Eventos de transmissão ou recepção associados ao tráfego real.
        """
        return [
            event
            for event in events
            if event.get("component") == component
            and str(event.get("reason") or "").startswith("wire_message:")
        ]

    tx_events = wire_events("tx")
    rx_events = wire_events("rx")
    if not tx_events or not rx_events:
        row["capture_coupled_energy_status"] = (
            "missing_directional_power_state_events"
        )
        row["energy_total_capture_coupled_j"] = None
        return

    tx_bytes = int(capture.get("iot_tx_ip_bytes") or 0)
    rx_bytes = int(capture.get("iot_rx_ip_bytes") or 0)
    tx_seconds = tx_bytes * 8.0 / bitrate
    rx_seconds = rx_bytes * 8.0 / bitrate
    tx_event, rx_event = tx_events[0], rx_events[0]
    captured_tx_j = (
        float(tx_event["voltage_v"])
        * float(tx_event["current_ma"])
        / 1000.0
        * tx_seconds
        / efficiency
        * communication_correction_factor
    )
    captured_rx_j = (
        float(rx_event["voltage_v"])
        * float(rx_event["current_ma"])
        / 1000.0
        * rx_seconds
        / efficiency
        * communication_correction_factor
    )
    modeled_wire_tx_j = sum(float(event["battery_energy_j"]) for event in tx_events)
    modeled_wire_rx_j = sum(float(event["battery_energy_j"]) for event in rx_events)
    response_wait_events = [
        event
        for event in events
        if str(event.get("reason") or "").endswith("_response_wait")
    ]
    modeled_response_wait_j = sum(
        float(event["battery_energy_j"]) for event in response_wait_events
    )
    original_total = float(row["energy_total_iot_j"])
    airtime_only_total = (
        original_total
        - modeled_wire_tx_j
        - modeled_wire_rx_j
        + captured_tx_j
        + captured_rx_j
    )

    try:
        observed_duration = float(capture.get("capture_duration_seconds") or 0.0)
    except (TypeError, ValueError):
        observed_duration = 0.0
    duration_source = "pcap_first_to_last_transport_packet"
    if observed_duration <= 0:
        try:
            observed_duration = float(observation.get("duration_seconds") or 0.0)
        except (TypeError, ValueError):
            observed_duration = 0.0
        duration_source = "mininet_transport_probe_client_duration_fallback"

    residual_listen_seconds = max(
        observed_duration - tx_seconds - rx_seconds,
        0.0,
    )
    observed_listen_j = (
        float(rx_event["voltage_v"])
        * float(rx_event["current_ma"])
        / 1000.0
        * residual_listen_seconds
        / efficiency
        * communication_correction_factor
    )
    observed_window_total = (
        original_total
        - modeled_wire_tx_j
        - modeled_wire_rx_j
        - modeled_response_wait_j
        + captured_tx_j
        + captured_rx_j
        + observed_listen_j
    )
    row.update(
        {
            "capture_coupled_energy_status": (
                "available_pcap_bytes_and_observed_active_window_proxy"
                if observed_duration > 0
                else "unavailable_observed_duration_airtime_only_available"
            ),
            "pcap_iot_tx_ip_bytes": tx_bytes,
            "pcap_iot_rx_ip_bytes": rx_bytes,
            "pcap_packet_count": int(capture.get("packet_count") or 0),
            "pcap_capture_duration_seconds": capture.get(
                "capture_duration_seconds"
            ),
            "observed_network_active_window_seconds": observed_duration,
            "observed_network_active_window_source": duration_source,
            "capture_coupled_tx_airtime_seconds": tx_seconds,
            "capture_coupled_rx_airtime_seconds": rx_seconds,
            "capture_coupled_residual_listen_seconds": residual_listen_seconds,
            "modeled_wire_tx_energy_replaced_j": modeled_wire_tx_j,
            "modeled_wire_rx_energy_replaced_j": modeled_wire_rx_j,
            "modeled_response_wait_energy_replaced_j": modeled_response_wait_j,
            "energy_tx_capture_coupled_j": captured_tx_j,
            "energy_rx_capture_coupled_j": captured_rx_j,
            "energy_residual_listen_capture_coupled_j": observed_listen_j,
            "energy_network_capture_coupled_j": (
                captured_tx_j + captured_rx_j + observed_listen_j
            ),
            "energy_total_capture_airtime_only_j": airtime_only_total,
            "energy_total_capture_coupled_j": (
                observed_window_total if observed_duration > 0 else None
            ),
            "capture_energy_interpretation": (
                "pcap_directional_ipv4_bytes_plus_observed_packet_window;"
                "configured_phy_rate_and_power_states;model_response_waits_replaced;"
                "active_interface_window_proxy_not_hardware_power_measurement"
            ),
        }
    )
