# PQC-IoT Simulator

Plataforma de simulação e emulação de rede para comparar criptografia clássica, pós-quântica e híbrida em cenários de Internet das Coisas. O perfil físico principal representa um ESP32-WROOM-32 com sensor BME280, Wi-Fi de 2,4 GHz e bateria Li-ion.

O Mininet-WiFi é o motor de rede obrigatório. Cada ciclo transmite mensagens entre namespaces reais da topologia antes de ser aceito como resultado. A plataforma registra tráfego, PCAP, latência, bytes, operações criptográficas e estimativas de energia do nó IoT.
## Recursos

- modos clássico, pós-quântico e híbrido;
- X25519, Ed25519, ML-KEM-512 e ML-DSA-44;
- proteção dos dados com AES-256-GCM e derivação HKDF/HMAC-SHA-256;
- MQTT 3.1.1, CoAP confirmável e HTTP/1.1;
- topologias em grade, estrela, árvore e malha;
- sessões com tempo de vida, limite de mensagens e contador de nonce;
- perfis parametrizados de dispositivo, bateria, rádio e criptografia;
- execução obrigatória no Mininet-WiFi;
- captura PCAP e exportação em JSON e CSV.

## Estrutura

```text
.
├── Tutorial_Execucao.ipynb
├── calibracao/
│   ├── README.md
│   └── *.csv
├── pqc_iot_simulator/
│   └── pqc_iot_sim/
├── scripts/
│   └── verify_installation.py
├── Dockerfile
├── docker-compose.yml
├── docker-entrypoint.sh
├── requirements.txt
└── LICENSE
```

Resultados são criados localmente em `results/` e não são versionados.

## Requisitos

Use um host Linux com:

- Docker Engine;
- Docker Compose;
- suporte a `mac80211_hwsim`;
- privilégios para Mininet-WiFi, Open vSwitch e namespaces de rede.

A primeira construção da imagem compila dependências nativas e pode demorar.

## Instalação

Na raiz do repositório:

```bash
sudo docker compose version
sudo docker compose build notebook
```

Valide os três modos criptográficos:

```bash
sudo docker compose run --rm notebook   python3 scripts/verify_installation.py --mode classical

sudo docker compose run --rm notebook   python3 scripts/verify_installation.py --mode pqc

sudo docker compose run --rm notebook   python3 scripts/verify_installation.py --mode hybrid
```

Cada verificação exige associação Wi-Fi, entrega pelo Mininet e PCAP bidirecional. O comando termina com `"status": "PASS"` quando a instalação está funcional.

## Tutorial

Inicie o JupyterLab:

```bash
sudo docker compose run --rm --service-ports notebook
```

Abra a URL exibida no terminal, selecione o kernel **Python 3 - PQC IoT Simulator** e execute [Tutorial_Execucao.ipynb](Tutorial_Execucao.ipynb) da primeira à última célula.

O Jupyter escuta somente em `127.0.0.1:8888`. Não exponha essa porta à Internet.

## Execução pela linha de comando

Para executar a configuração padrão:

```bash
sudo docker compose run --rm pqc_iot_simulator
```

A configuração principal está em [default.yaml](pqc_iot_simulator/pqc_iot_sim/configs/default.yaml). Os principais blocos configuráveis são:

- `simulation`: duração, semente, captura e diretório de PCAP;
- `devices`: dispositivos e destinos;
- `device_profiles`: bateria, rádio, carga de trabalho e sessão;
- `crypto_timing`: perfil de calibração;
- `network`: topologia, protocolo, criptografia e condições do enlace;
- `engine`: parâmetros do Mininet-WiFi.

## Invariantes de execução

- `simulation.run_engine` deve permanecer `true`;
- `engine.enabled` deve permanecer `true`;
- `engine.type` deve ser `mininet_wifi`;
- ausência de topologia, transporte ou PCAP obrigatório interrompe a execução;
- valores configurados não substituem silenciosamente observações Mininet ausentes.

## Criptografia e sessões

Os modos disponíveis são:

- **clássico:** X25519 e Ed25519;
- **PQC:** ML-KEM-512 e ML-DSA-44;
- **híbrido:** X25519 + ML-KEM-512 e Ed25519 + ML-DSA-44.

O modelo possui duas variantes de estabelecimento: `preprovisioned` e `full_certificate`. As chaves de sessão protegem os dados com AES-256-GCM.

## Energia e calibração

A energia é contabilizada em joules:

```text
E_load = tensão × corrente × duração
E_battery = E_load / eficiência_do_regulador
```

Os eventos podem incluir sensor, CPU, criptografia, associação Wi-Fi, transmissão, recepção, espera, sono e estado RTC. Consulte [calibracao/README.md](calibracao/README.md) para conhecer a origem e as limitações dos parâmetros.

## Limitações

- energia do gateway e do servidor não está calibrada;
- não há medição elétrica em ESP32 real;
- telemetria ambiental é sintética;
- ataques MITM, replay e downgrade não estão implementados.

## Dados gerados

Execuções criam arquivos em `results/raw/`, incluindo configurações resolvidas, CSV, JSON e PCAP. Esse diretório é ignorado pelo Git. Para publicar uma campanha, use um repositório de dados separado e registre o commit da plataforma, a configuração, as sementes e a versão da imagem Docker.

## Licença

O código é distribuído conforme [LICENSE](LICENSE).
