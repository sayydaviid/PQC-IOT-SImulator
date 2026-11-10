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

A pesquisa de **recuperação de sessões após reinícios e rollback** está em [Pesquisa_Retomada_Sessoes.ipynb](Pesquisa_Retomada_Sessoes.ipynb). O notebook conduz os experimentos com TLS 1.3 nativo, preservação/perda do contexto de retomada, diferentes cadeias de certificados, várias leituras por conexão e deduplicação persistente. A implementação é chamada por classes do simulador. O notebook mostra a sequência dos experimentos, a análise e o código dos gráficos.

O [Proposta_Retomada_Sessoes.ipynb](Proposta_Retomada_Sessoes.ipynb) configura a rede e chama os experimentos passando os parâmetros:

```python
from pqc_iot_simulator import Network, Logger

rede = Network()
rede.set_ready_topology("Star", 1)
rede.draw()
Logger.activate()

resultado = rede.recovery.run_sessions(
    source="iot_1",
    destination="server_1",
    profile="pqc",
    treatment="resume_preserved",
    readings=9,
    restart_fraction=0.25,
    ack_fraction=0.25,
    repetitions=10,
    payload_bytes=31,
    loss_pct=0,
)
```

A origem e o destino são nós da topologia configurada. `profile` seleciona `classical`, `hybrid` ou `pqc`; `treatment` seleciona `full`, `resume_volatile` ou `resume_preserved`. As frequências variam de 0 a 1, e `loss_pct` é a perda de pacotes em porcentagem. Os arquivos de cada execução são organizados pelo simulador. O retorno contém as medições por repetição.

A geração de gráficos fica nas células do notebook, onde os filtros e comandos de desenho podem ser inspecionados e alterados pelos pesquisadores. O simulador executa os cenários e calcula as métricas. As classes não dependem do nome nem da localização do notebook.

## Estrutura

```text
.
├── Tutorial_Execucao.ipynb          # uso geral, preservado
├── Pesquisa_Retomada_Sessoes.ipynb  # reprodução da pesquisa atual
├── Proposta_Retomada_Sessoes.ipynb  # experimentos a partir da rede
├── pqc_iot_simulator/pqc_iot_sim/
│   ├── config/                     # configurações de execução
│   ├── control/                    # controle de sessões e cenários de falha
│   ├── crypto/                     # criptografia e parâmetros TLS
│   ├── devices/                    # dispositivos, energia e carga
│   ├── runtime/                    # execução, Mininet-WiFi e comunicação nativa
│   ├── topology/                   # rede e participantes
│   ├── utils/                      # métricas, registros e exportação
│   ├── data/                       # observações de referência para reanálise
│   └── metadata.py                 # versão e registro automático da execução
├── calibracao/                     # parâmetros e fontes bibliográficas
├── .devcontainer/                  # ambiente do VS Code
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

## Instalação e uso no VS Code

Na raiz do repositório:

```bash
docker compose build
```

No VS Code, com a extensão **Dev Containers** instalada, execute **Dev Containers: Reopen in Container**. O VS Code inicia o serviço `notebook` e instala as extensões Python e Jupyter no contêiner.

Abra [Pesquisa_Retomada_Sessoes.ipynb](Pesquisa_Retomada_Sessoes.ipynb) e selecione o kernel **Python 3 - PQC IoT Simulator**. O ambiente já contém o simulador, o Mininet-WiFi e os três módulos TLS nativos.

O [Tutorial_Execucao.ipynb](Tutorial_Execucao.ipynb) continua disponível para o uso geral do simulador.

## Configuração

A configuração principal está em [default.yaml](pqc_iot_simulator/pqc_iot_sim/config/default.yaml). Os principais blocos configuráveis são:

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

Os cenários de identidade, persistência e interrupção integram as classes de controle. O notebook mostra quais são executados e verifica seus resultados. As dependências Python estão centralizadas em `requirements.txt`.
