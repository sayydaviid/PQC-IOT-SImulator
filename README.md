# PQC-IoT Simulator

Plataforma de simulação e emulação de rede para comparar criptografia clássica, pós-quântica e híbrida em cenários de Internet das Coisas. O perfil físico principal representa um ESP32-WROOM-32 com sensor BME280, Wi-Fi de 2,4 GHz e bateria Li-ion.

O Mininet-WiFi é o motor de rede obrigatório. Cada ciclo transmite mensagens entre namespaces reais da topologia antes de ser aceito como resultado. A plataforma registra tráfego, PCAP, latência, bytes, operações criptográficas e estimativas de energia do nó IoT.

> **Limite científico:** a energia do ESP32 é estimada com parâmetros de datasheets e literatura. O Mininet-WiFi não mede corrente elétrica e os protocolos de aplicação são traços equivalentes, não implementações interoperáveis completas.

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

A pesquisa de **recuperação de sessões após reinícios e rollback** está em [Pesquisa_Retomada_Sessoes.ipynb](Pesquisa_Retomada_Sessoes.ipynb). O notebook consulta os resultados de referência e permite repetir os experimentos com TLS 1.3 nativo, preservação/perda do contexto de retomada, diferentes cadeias de certificados, várias leituras por conexão e deduplicação persistente. A implementação é chamada por classes do simulador. O notebook mostra a sequência dos experimentos, a análise e o código dos gráficos.

A execução de recuperação parte da mesma API do simulador:

```python
from pqc_iot_simulator import Simulation

simulacao = Simulation()
estudo = simulacao.session_recovery("results/minha_execucao", blocks=10)
estudo.preflight()
estudo.run_all()
```

A geração de gráficos fica nas células do notebook, onde os filtros e comandos de desenho podem ser inspecionados e alterados pelos pesquisadores. O simulador executa os cenários e calcula as métricas. Para somente recalcular as tabelas históricas, use `REPRODUZIR = False` no notebook; as 11 tabelas são comparadas exatamente com as referências.

## Estrutura

```text
.
├── Tutorial_Execucao.ipynb          # uso geral, preservado
├── Pesquisa_Retomada_Sessoes.ipynb  # reprodução da pesquisa atual
├── pqc_iot_simulator/pqc_iot_sim/
│   ├── components/                 # rede, dispositivos, criptografia e estado
│   ├── core/                       # Simulation e protótipo
│   ├── engines/                    # Mininet-WiFi
│   ├── data/                       # observações de referência para reanálise
│   └── validation/                 # verificações dos componentes e cenários
├── calibracao/                     # parâmetros e fontes bibliográficas
├── docker/                         # ambiente TLS da pesquisa
├── Dockerfile
├── docker-compose.yml
├── docker-entrypoint.sh
├── requirements.txt
└── LICENSE
```

Dados produzidos nas execuções são salvos no diretório escolhido no notebook e não são versionados automaticamente. As observações necessárias para recalcular os números do artigo estão em `pqc_iot_simulator/pqc_iot_sim/data/`. O método e a geração das figuras estão no notebook de pesquisa.

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

O tutorial monta a rede e executa a simulação. As verificações adicionais estão disponíveis como classe Python:

```python
from pqc_iot_simulator.pqc_iot_sim.validation.installation import InstallationValidation

InstallationValidation(mode="classical").run()
```

Esse código deve ser executado no ambiente Docker, em uma célula do notebook. Os modos `pqc` e `hybrid` também são aceitos.

## Tutorial

Inicie o JupyterLab:

```bash
sudo docker compose run --rm --service-ports notebook
```

Abra a URL exibida no terminal, selecione o kernel **Python 3 - PQC IoT Simulator** e execute [Tutorial_Execucao.ipynb](Tutorial_Execucao.ipynb) da primeira à última célula.

O Jupyter escuta somente em `127.0.0.1:8888`. Não exponha essa porta à Internet.

## Configuração

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

Execuções criam arquivos em `results/raw/`, incluindo configurações resolvidas, CSV, JSON e PCAP. Esse diretório é ignorado pelo Git. Para compartilhar uma execução, use um repositório de dados separado e registre o commit da plataforma, a configuração, as sementes e a versão da imagem Docker.

## Licença

O código é distribuído conforme [LICENSE](LICENSE).
