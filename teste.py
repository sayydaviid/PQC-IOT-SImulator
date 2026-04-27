import json

from pqc_iot_simulator.pqc_iot_sim.components import Network, Logger
from pqc_iot_simulator.pqc_iot_sim.engines import MininetWiFiEngine


Logger.activate()

rede = Network(verbose=True)

rede.set_ready_topology("grade", 3, 3)
rede.set_protocol("mqtt")
rede.set_crypto_mode("classical")
rede.set_metrics([
    "latency",
    "packet_loss",
    "pdr",
    "energy",
    "crypto_time",
    "message_overhead",
    "link_metrics"
])

engine = MininetWiFiEngine(
    network=rede,
    logger=rede.logger,
    default_bw=10,
    default_delay="5ms",
    default_loss=0,
    link_mode="infrastructure"
)

rede.set_runtime_engine(engine)

try:
    engine.build()
    engine.start()

    print("\nMETRICAS REAIS DO LINK")
    link_metrics = engine.collect_link_metrics(
        source="iot_1",
        destination="server_1"
    )
    print(json.dumps(link_metrics, indent=4, ensure_ascii=False))

    print("\nTESTE DE ENVIO LOGICO DA REDE")
    resultado_envio = rede.send(
        source="iot_1",
        destination="server_1",
        payload={
            "temperatura": 28.5,
            "umidade": 70,
            "sensor": "iot_1"
        }
    )
    print(json.dumps(resultado_envio, indent=4, ensure_ascii=False, default=str))

    print("\nRESUMO DAS METRICAS DA NETWORK")
    print(json.dumps(rede.metrics(), indent=4, ensure_ascii=False))

    print("\nULTIMA TRANSMISSAO")
    print(json.dumps(rede.last_transmission(), indent=4, ensure_ascii=False, default=str))

    print("\nRESUMO DA ENGINE")
    print(json.dumps(engine.summary(), indent=4, ensure_ascii=False, default=str))

    print("\nIP iot_1")
    print(engine.run_command("iot_1", "ip addr"))

    print("\nROTA iot_1")
    print(engine.run_command("iot_1", "ip route"))

    print("\nWIRELESS iot_1")
    print(engine.run_command("iot_1", "iw dev"))

    print("\nLINK WIRELESS iot_1")
    print(engine.run_command("iot_1", "iw dev sta1-wlan0 link"))

    print("\nIP server_1")
    print(engine.run_command("server_1", "ip addr"))

    print("\nROTA server_1")
    print(engine.run_command("server_1", "ip route"))

    print("\nARP iot_1 antes")
    print(engine.run_command("iot_1", "arp -n"))

    print("\nOVS ap1")
    print(engine.run_command("gateway_1", "ovs-ofctl show ap1"))

    print("\nFLOWS ap1")
    print(engine.run_command("gateway_1", "ovs-ofctl dump-flows ap1"))

    print("\nPING 1")
    print(engine.ping("iot_1", "server_1"))

    print("\nPING 2")
    print(engine.ping("iot_1", "server_1"))

    rede.export_metrics_json("outputs/metrics/teste_mininet_wifi.json")
    rede.export_metrics_csv("outputs/metrics/teste_mininet_wifi.csv")
    engine.export_mapping_json("outputs/metrics/mapping_mininet_wifi.json")

finally:
    engine.stop()