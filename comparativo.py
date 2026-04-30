from pathlib import Path
import csv
import os
import time
import traceback
import random
import string

from pqc_iot_simulator.pqc_iot_sim.components import Network, Logger
from pqc_iot_simulator.pqc_iot_sim.engines import MininetWiFiEngine


Logger.activate()


OUTPUT_CSV = Path("comparativo_geral.csv")

TOPOLOGY = ("grade", 3, 3)
SOURCE = "iot_1"
DESTINATION = "server_1"

REPETICOES_POR_MODO = 30
AQUECIMENTOS_POR_MODO = 1

TEMPO_ESPERA_APOS_START = 1
TEMPO_ESPERA_ENTRE_TESTES = 1
VERBOSE = False

SEED = 42

MODOS = [
    "pqc",
    "hybrid",
    "classical"
]

CAMPOS_CSV = [
    "execucao_global",
    "cenario_id",
    "run",
    "crypto_mode",

    "network_bw_mbps",
    "network_delay_ms",
    "network_loss_percent",
    "payload_extra_bytes",
    "payload_sensor",
    "payload_valor",

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


def gerar_texto_aleatorio(tamanho: int):
    alfabeto = string.ascii_letters + string.digits

    return "".join(
        random.choice(alfabeto)
        for _ in range(tamanho)
    )


def gerar_cenarios(total: int):
    random.seed(SEED)

    sensores = [
        "temperatura",
        "umidade",
        "pressao",
        "luminosidade",
        "movimento",
        "co2",
        "vibracao"
    ]

    cenarios = []

    for cenario_id in range(1, total + 1):
        bw_mbps = random.choice([1, 2, 5, 10, 20])

        delay_ms = random.randint(5, 80)

        loss_percent = random.choice([
            0,
            0,
            0,
            0.1,
            0.2,
            0.5,
            1.0,
            2.0
        ])

        payload_extra_bytes = random.randint(50, 2000)

        sensor = random.choice(sensores)

        valor = round(random.uniform(10.0, 90.0), 3)

        payload = {
            "sensor": sensor,
            "valor": valor,
            "unidade": "medida_iot",
            "mensagem": "teste comparativo com parametros aleatorios",
            "amostra": gerar_texto_aleatorio(payload_extra_bytes)
        }

        cenarios.append({
            "cenario_id": cenario_id,
            "bw_mbps": bw_mbps,
            "delay_ms": delay_ms,
            "loss_percent": loss_percent,
            "payload_extra_bytes": payload_extra_bytes,
            "sensor": sensor,
            "valor": valor,
            "payload": payload
        })

    return cenarios


def criar_rede(crypto_mode: str):
    rede = Network(verbose=VERBOSE)

    rede.set_ready_topology(*TOPOLOGY)
    rede.set_protocol("mqtt")
    rede.set_crypto_mode(crypto_mode)

    return rede


def criar_engine(rede: Network, cenario: dict):
    engine = MininetWiFiEngine(
        network=rede,
        logger=rede.logger,
        default_bw=cenario["bw_mbps"],
        default_delay=f"{cenario['delay_ms']}ms",
        default_loss=cenario["loss_percent"],
        link_mode="infrastructure",
        open_cli_on_start=False
    )

    return engine


def iniciar_csv():
    if OUTPUT_CSV.exists():
        OUTPUT_CSV.unlink()

    with open(OUTPUT_CSV, "w", encoding="utf8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CAMPOS_CSV)
        writer.writeheader()


def adicionar_linha_csv(linha: dict):
    with open(OUTPUT_CSV, "a", encoding="utf8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CAMPOS_CSV)
        writer.writerow(linha)


def montar_linha_resultado(
    execucao_global: int,
    run: int,
    crypto_mode: str,
    cenario: dict,
    metric: dict | None,
    erro: str = ""
):
    base = {
        "execucao_global": execucao_global,
        "cenario_id": cenario["cenario_id"],
        "run": run,
        "crypto_mode": crypto_mode,

        "network_bw_mbps": cenario["bw_mbps"],
        "network_delay_ms": cenario["delay_ms"],
        "network_loss_percent": cenario["loss_percent"],
        "payload_extra_bytes": cenario["payload_extra_bytes"],
        "payload_sensor": cenario["sensor"],
        "payload_valor": cenario["valor"],
    }

    if metric is None:
        base.update({
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
        })

        return base

    path = metric.get("path") or []

    base.update({
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
    })

    return base


def executar_envio(crypto_mode: str, cenario: dict):
    rede = None
    engine = None

    try:
        rede = criar_rede(crypto_mode)
        engine = criar_engine(rede, cenario)

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
            payload=cenario["payload"],
            link_metrics=link_metrics
        )

        return rede.last_transmission()

    finally:
        if engine is not None:
            try:
                engine.stop()
            except Exception as erro_stop:
                print(f"[AVISO] Erro ao parar engine: {erro_stop}")

        time.sleep(TEMPO_ESPERA_ENTRE_TESTES)


def executar_aquecimento(crypto_mode: str, cenario: dict):
    for indice in range(1, AQUECIMENTOS_POR_MODO + 1):
        print()
        print(f"Aquecimento {indice:03d} do modo: {crypto_mode}")
        print("Essa execução não será salva no CSV.")

        try:
            executar_envio(
                crypto_mode=crypto_mode,
                cenario=cenario
            )

            print(f"Aquecimento finalizado: {crypto_mode}")

        except Exception as erro:
            print(f"[AVISO] Falha no aquecimento do modo {crypto_mode}: {erro}")
            print(traceback.format_exc())


def executar_teste(crypto_mode: str, run: int, execucao_global: int, cenario: dict):
    try:
        print()
        print(f"Iniciando execução {execucao_global:03d}")
        print(f"Modo: {crypto_mode}")
        print(f"Run: {run:03d}")
        print(f"Cenário: {cenario['cenario_id']:03d}")
        print(f"BW: {cenario['bw_mbps']} Mbps")
        print(f"Delay: {cenario['delay_ms']} ms")
        print(f"Loss: {cenario['loss_percent']}%")
        print(f"Payload extra: {cenario['payload_extra_bytes']} bytes")

        metric = executar_envio(
            crypto_mode=crypto_mode,
            cenario=cenario
        )

        linha = montar_linha_resultado(
            execucao_global=execucao_global,
            run=run,
            crypto_mode=crypto_mode,
            cenario=cenario,
            metric=metric
        )

        print(f"Teste finalizado: {crypto_mode} run {run:03d}")

        return linha

    except Exception as erro:
        print(f"[ERRO] Falha no modo {crypto_mode} run {run:03d}: {erro}")
        print(traceback.format_exc())

        return montar_linha_resultado(
            execucao_global=execucao_global,
            run=run,
            crypto_mode=crypto_mode,
            cenario=cenario,
            metric=None,
            erro=str(erro)
        )


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

    cenarios = gerar_cenarios(REPETICOES_POR_MODO)

    execucao_global = 0

    for modo in MODOS:
        print()
        print(f"Começando bloco do modo: {modo}")

        executar_aquecimento(
            crypto_mode=modo,
            cenario=cenarios[0]
        )

        for run, cenario in enumerate(cenarios, start=1):
            execucao_global += 1

            linha = executar_teste(
                crypto_mode=modo,
                run=run,
                execucao_global=execucao_global,
                cenario=cenario
            )

            adicionar_linha_csv(linha)

        print()
        print(f"Bloco finalizado: {modo}")

    corrigir_permissao_csv()

    print()
    print("Todos os testes foram finalizados.")
    print(f"Total de execuções salvas: {execucao_global}")
    print(f"CSV salvo em: {OUTPUT_CSV.resolve()}")


if __name__ == "__main__":
    main()