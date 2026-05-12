# PQC-IOT-SImulator

Simulador para avaliar o impacto de criptografia pós‑quântica (PQC) em cenários IoT.

Ele modela uma rede IoT (nós IoT → gateway → servidor), envia mensagens entre origem/destino e coleta métricas como:
latência (estimada e/ou real), perda de pacotes, saltos, consumo de energia, tempo/overhead da criptografia.

O simulador é executado utilizando a engine **Mininet‑WiFi** por padrão. A topologia lógica é construída e roteada no Mininet‑WiFi (com OVS), permitindo coletar métricas reais de link (ex.: via `ping`).

## Estrutura do repositório

- `pqc_iot_simulator/pqc_iot_sim/`: núcleo do simulador (Network, CryptoManager, métricas e engines)
- `pqc_iot_simulator/pqc_iot_sim/configs/default.yaml`: configuração padrão
- `comparativo.py`, `teste_comparativo_crypto.py`: scripts de experimento/comparação
- `grafico.py`: gera gráficos a partir de `comparativo_geral.csv`

## Como executar (Docker Compose — recomendado)

Requisitos:

- Linux com Docker + Docker Compose
- Permissão para rodar containers privilegiados (o Mininet exige permissões elevadas para a rede do host)

O container já está pré-configurado para suportar e executar automaticamente o Mininet-WiFi em modo privilegiado e rede do host.

### 1) Build da imagem

```bash
docker compose build
```

### 2) Rodar o simulador (config padrão)

Executa o simulador usando a configuração padrão. Todos os comandos abaixo já farão uso automático do Mininet-WiFi.

```bash
docker compose run --rm pqc_iot_simulator
```

Alternativa equivalente (mantém logs no terminal):

```bash
docker compose up --build
```

### 3) Rodar scripts de experimento dentro do container

Como o serviço monta o repositório em `/workspace`, os arquivos gerados pelos scripts ficam no host.

```bash
docker compose run --rm pqc_iot_simulator python3 teste_comparativo_crypto.py
```

```bash
docker compose run --rm pqc_iot_simulator python3 comparativo.py
```

Depois, para gerar gráficos a partir do CSV:

```bash
docker compose run --rm pqc_iot_simulator python3 grafico.py
```

Observações:

- Para Mininet/OVS funcionar, a execução precisa ser privilegiada (o `docker-compose.yml` já está configurado com `privileged: true`, `network_mode: host` e `pid: host`).
- Se você interromper execuções e sobrar “lixo” de rede, o entrypoint roda `mn -c` automaticamente.

## Execução local (sem Docker)

Este caminho exige dependências de sistema (Mininet, Mininet‑WiFi, OVS e liboqs). Em geral, para reproduzir o ambiente de forma consistente, prefira Docker.

Dependências Python do simulador:

```bash
python3 -m pip install -r pqc_iot_simulator/pqc_iot_sim/requirements-project.txt
```

Para rodar o simulador com a config padrão (com Mininet-WiFi habilitado):

```bash
sudo python3 -m pqc_iot_simulator.pqc_iot_sim.main
```