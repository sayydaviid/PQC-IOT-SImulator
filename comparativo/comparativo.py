from pathlib import Path
import csv
import os
import random
import time
import traceback

from pqc_iot_simulator.pqc_iot_sim.components import Network, Logger
from pqc_iot_simulator.pqc_iot_sim.engines import MininetWiFiEngine


Logger.activate()


OUTPUT_CSV = Path("comparativo_geral.csv")

TOPOLOGY = ("grade", 3, 3)
SOURCE = "iot_1"
DESTINATION = "server_1"

REPETICOES_POR_MODO = 30
TEMPO_ESPERA_APOS_START = 1
TEMPO_ESPERA_ENTRE_TESTES = 1
VERBOSE = False

PAYLOAD = {
    "sensor": "temperatura",
    "valor": 28.5,
    "unidade": "celsius",
    "mensagem": "teste comparativo de criptografia"
}

MODOS = [
    "classical",
    "hybrid",
    "pqc"
]

CAMPOS_CSV = [
    "run",
    "crypto_mode",
    "status",
    "delivered",
    "source",
    "destination",
    "path",
    "hops",
    "protocol",
    "crypto_backend",
    "crypto_algorithm",
    "original_payload_size_bytes",
    "protected_payload_size_bytes",
    "payload_size_bytes",
    "crypto_overhead_bytes",
    "crypto_time_seconds",
    "crypto_energy_cost",
    "duration_seconds",
    "total_energy_consumed",
    "link_latency_ms",
    "link_packet_loss_percent",
    "link_packets_transmitted",
    "link_packets_received",
    "link_rtt_min_ms",
    "link_rtt_avg_ms",
    "link_rtt_max_ms",
    "link_rtt_mdev_ms",
    "erro"
]


def criar_rede(crypto_mode: str):
    rede = Network(verbose=VERBOSE)

    rede.set_ready_topology(*TOPOLOGY)
    rede.set_protocol("mqtt")
    rede.set_crypto_mode(crypto_mode)

    return rede


def criar_engine(rede: Network):
    engine = MininetWiFiEngine(
        network=rede,
        logger=rede.logger,
        default_bw=10,
        default_delay="5ms",
        default_loss=0,
        link_mode="infrastructure",
        open_cli_on_start=False
    )

    return engine


def iniciar_csv():
    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CAMPOS_CSV)
        writer.writeheader()


def adicionar_linha_csv(linha: dict):
    with open(OUTPUT_CSV, "a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CAMPOS_CSV)
        writer.writerow(linha)


def montar_linha_resultado(run: int, crypto_mode: str, metric: dict | None, erro: str = ""):
    if metric is None:
        return {
            "run": run,
            "crypto_mode": crypto_mode,
            "status": "error",
            "delivered": False,
            "source": SOURCE,
            "destination": DESTINATION,
            "path": "",
            "hops": "",
            "protocol": "",
            "crypto_backend": "",
            "crypto_algorithm": "",
            "original_payload_size_bytes": "",
            "protected_payload_size_bytes": "",
            "payload_size_bytes": "",
            "crypto_overhead_bytes": "",
            "crypto_time_seconds": "",
            "crypto_energy_cost": "",
            "duration_seconds": "",
            "total_energy_consumed": "",
            "link_latency_ms": "",
            "link_packet_loss_percent": "",
            "link_packets_transmitted": "",
            "link_packets_received": "",
            "link_rtt_min_ms": "",
            "link_rtt_avg_ms": "",
            "link_rtt_max_ms": "",
            "link_rtt_mdev_ms": "",
            "erro": erro
        }

    path = metric.get("path") or []

    return {
        "run": run,
        "crypto_mode": crypto_mode,
        "status": metric.get("status"),
        "delivered": metric.get("delivered"),
        "source": metric.get("source"),
        "destination": metric.get("destination"),
        "path": " para ".join(path),
        "hops": metric.get("hops"),
        "protocol": metric.get("protocol"),
        "crypto_backend": metric.get("crypto_backend"),
        "crypto_algorithm": metric.get("crypto_algorithm"),
        "original_payload_size_bytes": metric.get("original_payload_size_bytes"),
        "protected_payload_size_bytes": metric.get("protected_payload_size_bytes"),
        "payload_size_bytes": metric.get("payload_size_bytes"),
        "crypto_overhead_bytes": metric.get("crypto_overhead_bytes"),
        "crypto_time_seconds": metric.get("crypto_time_seconds"),
        "crypto_energy_cost": metric.get("crypto_energy_cost"),
        "duration_seconds": metric.get("duration_seconds"),
        "total_energy_consumed": metric.get("total_energy_consumed"),
        "link_latency_ms": metric.get("link_latency_ms"),
        "link_packet_loss_percent": metric.get("link_packet_loss_percent"),
        "link_packets_transmitted": metric.get("link_packets_transmitted"),
        "link_packets_received": metric.get("link_packets_received"),
        "link_rtt_min_ms": metric.get("link_rtt_min_ms"),
        "link_rtt_avg_ms": metric.get("link_rtt_avg_ms"),
        "link_rtt_max_ms": metric.get("link_rtt_max_ms"),
        "link_rtt_mdev_ms": metric.get("link_rtt_mdev_ms"),
        "erro": erro
    }


def executar_teste(crypto_mode: str, run: int):
    rede = None
    engine = None

    try:
        print(f"\nIniciando teste {run:03d} com modo: {crypto_mode}")

        rede = criar_rede(crypto_mode)
        engine = criar_engine(rede)

        engine.build()
        engine.start()

        time.sleep(TEMPO_ESPERA_APOS_START)

        link_metrics = engine.collect_link_metrics(
            source=SOURCE,
            destination=DESTINATION
        )

        rede.send(
            source=SOURCE,
            destination=DESTINATION,
            payload=PAYLOAD,
            link_metrics=link_metrics
        )

        metric = rede.last_transmission()

        linha = montar_linha_resultado(
            run=run,
            crypto_mode=crypto_mode,
            metric=metric
        )

        print(f"Teste finalizado: {crypto_mode} run {run:03d}")

        return linha

    except Exception as erro:
        print(f"[ERRO] Falha no modo {crypto_mode} run {run:03d}: {erro}")
        print(traceback.format_exc())

        return montar_linha_resultado(
            run=run,
            crypto_mode=crypto_mode,
            metric=None,
            erro=str(erro)
        )

    finally:
        if engine is not None:
            try:
                engine.stop()
            except Exception as erro_stop:
                print(f"[AVISO] Erro ao parar engine: {erro_stop}")

        time.sleep(TEMPO_ESPERA_ENTRE_TESTES)


def corrigir_permissao_csv():
    sudo_uid = os.environ.get("SUDO_UID")
    sudo_gid = os.environ.get("SUDO_GID")

    if not sudo_uid or not sudo_gid:
        return

    try:
        os.chown(OUTPUT_CSV, int(sudo_uid), int(sudo_gid))
    except Exception as erro:
        print(f"[AVISO] Não consegui ajustar a permissão do CSV: {erro}")


def main():
    iniciar_csv()

    for run in range(1, REPETICOES_POR_MODO + 1):
        ordem_modos = MODOS.copy()
        random.shuffle(ordem_modos)

        print(f"\nRodada {run:03d}")
        print(f"Ordem desta rodada: {ordem_modos}")

        for modo in ordem_modos:
            linha = executar_teste(
                crypto_mode=modo,
                run=run
            )

            adicionar_linha_csv(linha)

    corrigir_permissao_csv()

    print("\nTodos os testes foram finalizados.")
    print(f"CSV salvo em: {OUTPUT_CSV.resolve()}")


if __name__ == "__main__":
    main()