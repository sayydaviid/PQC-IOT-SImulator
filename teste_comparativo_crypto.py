from pathlib import Path
import json
import time

from pqc_iot_simulator.pqc_iot_sim.components import Network, Logger
from pqc_iot_simulator.pqc_iot_sim.engines import MininetWiFiEngine


Logger.activate()


OUTPUT_DIR = Path("resultados_comparativo_crypto")
TOPOLOGY = ("grade", 3, 3)
SOURCE = "iot_1"
DESTINATION = "server_1"

PAYLOAD = {
    "sensor": "temperatura",
    "valor": 28.5,
    "unidade": "celsius",
    "mensagem": "teste comparativo de criptografia"
}


def criar_rede(crypto_mode: str):
    rede = Network(verbose=True)

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


def salvar_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=4,
            ensure_ascii=False,
            default=str
        )


def executar_teste(crypto_mode: str):
    pasta_resultado = OUTPUT_DIR / crypto_mode
    pasta_resultado.mkdir(parents=True, exist_ok=True)

    rede = criar_rede(crypto_mode)
    engine = criar_engine(rede)

    try:
        print(f"\nIniciando teste com modo: {crypto_mode}")

        engine.build()
        engine.start()

        time.sleep(1)

        link_metrics = engine.collect_link_metrics(
            source=SOURCE,
            destination=DESTINATION
        )

        salvar_json(
            pasta_resultado / "link_metrics.json",
            link_metrics
        )

        send_result = rede.send(
            source=SOURCE,
            destination=DESTINATION,
            payload=PAYLOAD,
            link_metrics=link_metrics
        )

        salvar_json(
            pasta_resultado / "send_result.json",
            send_result
        )

        rede.export_metrics_json(
            str(pasta_resultado / "metrics.json")
        )

        rede.export_metrics_csv(
            str(pasta_resultado / "metrics.csv")
        )

        engine.export_mapping_json(
            str(pasta_resultado / "engine_mapping.json")
        )

        salvar_json(
            pasta_resultado / "summary.json",
            rede.metrics()
        )

        print(f"Teste finalizado com modo: {crypto_mode}")
        print(f"Arquivos salvos em: {pasta_resultado}")

    finally:
        engine.stop()


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    modos = [
        "classical",
        "hybrid",
        "pqc"
    ]

    for modo in modos:
        executar_teste(modo)

    print("\nTodos os testes foram finalizados.")
    print(f"Resultados salvos em: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()