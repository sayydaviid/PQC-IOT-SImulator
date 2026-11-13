# PQC-IoT Simulator

Simulador para comparar o custo da recuperação de sessões em redes IoT com criptografia clássica, híbrida e pós-quântica. Usamos o Mininet-WiFi para montar a rede e executar a comunicação entre o sensor e o servidor.

Os experimentos estão no [Pesquisa_Retomada_Sessoes.ipynb](Pesquisa_Retomada_Sessoes.ipynb). Nele configuramos a topologia, executamos as falhas, analisamos as medições e geramos os gráficos com Matplotlib.

O [Tutorial_Execucao.ipynb](Tutorial_Execucao.ipynb) mostra o uso geral do simulador.

## Preparando o ambiente

Usamos Linux com Docker, Docker Compose e suporte ao módulo `mac80211_hwsim`. O contêiner precisa de privilégios para executar o Mininet-WiFi e o Open vSwitch.

Na pasta do projeto, construímos a imagem:

```bash
docker compose build
```

Depois, iniciamos o Jupyter:

```bash
sudo docker compose run --rm --service-ports notebook \
  jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root
```

Abra o endereço com o token que aparece no terminal. No Jupyter, abra `Pesquisa_Retomada_Sessoes.ipynb` e execute as células em ordem.

No VS Code, também é possível usar a extensão Dev Containers e a opção **Dev Containers: Reopen in Container**. Nesse caso, selecione o Python do contêiner para executar o notebook.

## Configurando a rede

Criamos uma estrela com um sensor, um ponto de acesso e um servidor:

```python
from pqc_iot_simulator import Network, Logger

rede = Network()
rede.set_ready_topology("Star", 1)
rede.draw()
Logger.activate()
rede.recovery.start()
```

O sensor `iot_1` se conecta por Wi-Fi ao ponto de acesso `gateway_1`, que encaminha os dados para `server_1`. O servidor executa o TLS e mantém o banco de leituras.

`start()` inicia uma campanha e apaga os resultados das campanhas anteriores em `results/retomada`. Repetir uma etapa substitui suas medições e remove as análises e figuras que dependem delas.

## Executando os experimentos

Comparamos três configurações de TLS 1.3:

| Perfil | Troca de chaves | Autenticação |
|---|---|---|
| Clássico | X25519 | ECDSA P-256 |
| Híbrido | X25519MLKEM768 | ECDSA P-256 |
| Pós-quântico | X25519MLKEM768 | ML-DSA-44 |

Os modos são autenticação completa, contexto de retomada perdido e contexto preservado. As conexões usam autenticação mútua, AES-256-GCM/SHA-384 e 0-RTT desabilitado.

No notebook, chamamos cada etapa passando seus parâmetros:

```python
rede.recovery.run_prototype(repetitions=10, messages=8, block_size=32)

rede.recovery.run_continuity(
    source="iot_1", destination="server_1", blocks=10, readings=9
)
rede.recovery.analyze_continuity()

rede.recovery.run_chains(source="iot_1", destination="server_1", blocks=10)
rede.recovery.run_amortization(source="iot_1", destination="server_1", blocks=10)
rede.recovery.run_security()
rede.recovery.analyze_context()
```

As etapas avaliam falhas de estado, reinícios do processo servidor, confirmações perdidas, perda de pacotes, transmissão da CA raiz e quantidade de leituras por conexão. O controle com deduplicação verifica se o reenvio de uma leitura repete seu efeito no banco.

## Consultando as medições

As tabelas usam os dados da campanha atual:

```python
rede.recovery.table("tls")
rede.recovery.table("tls_comparisons")
rede.recovery.table("chains")
rede.recovery.table("chain_comparisons")
rede.recovery.table("amortization")
rede.recovery.table("amortization_comparisons")
```

O código dos gráficos fica nas células do notebook, separado por figura e painel. Ali podemos alterar os filtros, as cores, as legendas e os eixos. As figuras são exibidas no notebook e salvas em PNG, PDF e SVG.

## Arquivos gerados

Cada campanha cria uma pasta em `results/retomada`, com os resultados em JSON, as capturas PCAP, as tabelas CSV e as figuras. Os manifestos registram a topologia, os parâmetros, as versões e os hashes do código usado.

Para consultar a pasta da campanha:

```python
rede.recovery.directory
```

## Organização do código

- `control/`: chamadas dos experimentos e cenários de falha;
- `crypto/`: criptografia, sessões e configurações TLS;
- `runtime/`: execução no Mininet-WiFi e módulos TLS nativos;
- `topology/`: rede, nós e enlaces;
- `devices/`: perfis dos dispositivos e cálculo de energia;
- `utils/`: métricas, análise e exportação;
- `config/`: configurações gerais do simulador.

Essas pastas ficam em `pqc_iot_simulator/pqc_iot_sim/`. A configuração geral está em [default.yaml](pqc_iot_simulator/pqc_iot_sim/config/default.yaml), e as dependências Python estão em [requirements.txt](requirements.txt).

## Dispositivo e energia

O perfil de dispositivo usa ESP32-WROOM-32, sensor BME280 e Wi-Fi de 2,4 GHz. As estimativas de energia são calculadas a partir da tensão, da corrente e da duração de cada atividade. Os parâmetros e suas fontes estão em [calibracao/README.md](calibracao/README.md).

Os experimentos de retomada apresentados no notebook medem tráfego e tempo no ambiente emulado.

## Licença

[MIT](LICENSE).
