# Reprodução da pesquisa de retomada de sessões

Abra [Pesquisa_Retomada_Sessoes.ipynb](../../Pesquisa_Retomada_Sessoes.ipynb). Esse é o ponto de entrada da pesquisa. O [Tutorial_Execucao.ipynb](../../Tutorial_Execucao.ipynb) foi preservado e continua demonstrando o simulador geral.

O notebook permite consultar as tabelas de referência ou repetir os experimentos. A opção `REPRODUZIR = True` executa o desenho completo com dez blocos, grava novos dados e gera as análises e figuras. Uma execução completa pode levar várias horas. Alterar a quantidade de blocos muda a quantidade de repetições; não representa a mesma amostra do artigo. A análise de continuidade exige pelo menos dois blocos para os intervalos; as etapas individuais podem ser conferidas com um bloco.

## Organização

| Parte | Local e responsabilidade |
|---|---|
| Simulação geral | `pqc_iot_simulator/pqc_iot_sim/core/`: `Simulation` e experimentos do protótipo |
| Componentes | `components/`: criptografia, sessão, checkpoint, dispositivo, rede e banco de leituras |
| Rede emulada | `engines/`: execução com Mininet-WiFi |
| Pesquisa | `research/study.py`: classe `RecoveryStudy`, que coordena as etapas |
| Experimentos | `research/experiments/`: classes de recuperação, continuidade, cadeias e amortização |
| Análise e figuras | `research/analysis/`: comparações dentro da repetição, relatórios e exportação |
| Verificações | `research/validation/`: identidade, persistência, cobertura de captura e verificações funcionais |
| TLS | `research/tls/`: perfis, credenciais e leitura das capturas |
| Processos internos | `research/runtime/` e os módulos `*_probe.py`: cliente/servidor usados nos namespaces |
| Construção das imagens | `docker/`: imagens TLS derivadas do ambiente do simulador |
| Resultados de referência | `docs/resultados_contexto_20261106/` e `docs/resultados_continuidade_20261021_v5/` |
| Documentos da pesquisa | `docs/`: método, comparação com trabalhos anteriores, resultados e artigo |

Não há pasta de scripts de execução na raiz. Os experimentos são objetos Python chamados pelo notebook. Os processos cliente/servidor continuam necessários à execução real em namespaces e às interrupções de processos; são detalhes internos da implementação. As verificações foram integradas ao pacote e podem ser executadas por `ValidationSuite().run()`.

## Construir o ambiente de pesquisa

Na raiz do repositório:

```bash
docker compose build notebook
docker build -t pqc-iot-tls:organizacao -f docker/tls/Dockerfile .
docker build -t pqc-iot-continuity:organizacao -f docker/continuity/Dockerfile .
docker compose -f docker-compose.yml -f docker/context_costs/compose.yml build notebook
docker compose -f docker-compose.yml -f docker/context_costs/compose.yml run --rm --service-ports notebook
```

Abra o notebook no kernel **Python 3 - PQC IoT Simulator**. O host precisa ser Linux, permitir a criação de namespaces e disponibilizar `mac80211_hwsim`. O contêiner precisa dos privilégios definidos no Compose. A imagem fixa OpenSSL 3.5.9 e os mesmos fontes C dos experimentos anteriores. `RecoveryStudy.preflight()` verifica ferramentas, módulos nativos e correspondência desses fontes antes da execução.

A primeira construção baixa e compila as dependências. As imagens de pesquisa são construídas em sequência porque uma deriva da anterior.

## Uso das classes

```python
from pqc_iot_simulator import RecoveryStudy

estudo = RecoveryStudy("results/minha_reproducao", blocks=10)
estudo.preflight()
estudo.run_prototype()
estudo.run_continuity()
estudo.run_chains()
estudo.run_amortization()
estudo.run_security()
estudo.analyze_continuity()
estudo.analyze_context()
estudo.export_figures()
```

Também é possível chamar `estudo.run_all()` em um diretório novo. As etapas rejeitam diretórios já existentes para evitar substituir resultados. Para retomar uma reprodução por células, mantenha a mesma instância/diretório e execute somente as etapas ainda não concluídas. Uma etapa incompleta deve ser preservada como registro e repetida em outro diretório; não se deve completar a análise com parte dos comparadores de um bloco.

As classes individuais também estão disponíveis, por exemplo:

```python
from pqc_iot_simulator.pqc_iot_sim.research.experiments.chains import CertificateChainExperiment

CertificateChainExperiment(output="results/cadeias", blocks=10).run()
```

## Experimentos e critérios

| Etapa, com dez blocos onde aplicável | Desenho e arquivos |
|---|---|
| Protótipo de estado | 240 execuções: seis políticas, quatro falhas, dez repetições; `prototype/results.json` |
| Interrupções do protótipo | 330 casos: onze cenários, três modos, dez repetições; `transitions/results.json` |
| Continuidade TLS | 1.620 execuções principais e 180 adicionais sob perdas de 1% e 5%; `core/`, `loss/` |
| Transmissão da raiz | 540 execuções, três frequências, três perfis, três tratamentos e duas cadeias; `chains/` |
| Leituras por conexão | 540 execuções, 100 leituras de 512 bytes, limites de 1/10/100 leituras por conexão, com/sem recuperação; `amortization/` |
| Tickets e identidade | Comprimentos públicos e controles com credencial do cliente alterada; `identity_tickets/` |
| Persistência | Fronteiras da transação, encerramento com limpeza e SIGKILL; `persistence/`, `tls_persistence/` |
| Análises e figuras | `continuity_analysis/`, `context_analysis/`, `figures/` |

A comparação das cadeias usa nove leituras de 31 bytes por execução. O teste de amortização usa 100 leituras de 512 bytes e não inclui aquecimento adicional. Não misture os custos desses dois desenhos como se tivessem a mesma carga.

Os três perfis usam TLS 1.3, autenticação mútua e AES-256-GCM/SHA-384. O clássico combina X25519 e ECDSA P-256; o híbrido, X25519MLKEM768 e ECDSA P-256; o perfil `pqc`, X25519MLKEM768 e ML-DSA-44. As agendas de falhas são conservadas entre comparadores do bloco. As perdas de pacotes do kernel não são exatamente pareadas. Tempos dependem do host e não medem energia de sensores físicos.

O diagnóstico verifica cadeias enviadas nos dois sentidos e preserva a raiz confiável. A investigação dos tickets mede comprimentos e usa controles de identidade; não exporta segredos ou conteúdo privado de sessões. Os testes de persistência interrompem processos com o sistema operacional e o armazenamento em funcionamento. Não representam queda física de energia.

## Referências e dados novos

`ReferenceResults().verify()` verifica os resumos SHA-256 dos arquivos de referência versionados. Essa verificação detecta alteração dessas tabelas, mas não substitui a auditoria dos PCAP das novas execuções.

`ReferenceResults().compare(pasta_da_analise)` aproxima lado a lado as mesmas condições nos dados novos e nos de referência. Diferenças de rede e tempo são esperadas; não se exige igualdade exata de bytes ou tempo para declarar funcionamento. Falhas de autenticação, perda de comparadores e inconsistências da aplicação são erros, não variação de desempenho.

Os dados brutos locais anteriores foram mantidos. `results/`, `analysis_outputs/` e `output/` são saídas ignoradas pelo Git, não partes publicadas automaticamente. Um clone novo contém as tabelas de referência, as figuras e a implementação para gerar novas capturas. Para compartilhar dados brutos de uma execução, envie seu diretório completo, incluindo manifestos, JSON, PCAP e eventuais alvos de links relativos. Não envie credenciais privadas.

Os documentos e manifestos históricos registram os caminhos antigos de `scripts/` e `experiments/`. Eles não foram reescritos para simular uma execução com os novos fontes. Para reproduzir exatamente a implementação histórica, use a branch publicada `investigacao/custos-contexto-2026-11-06`, commit `b90b89b`. Para executar a versão organizada, use o novo notebook. Os novos manifestos registram os caminhos e hashes das classes atuais.

O mapeamento dos arquivos está em [migracao.json](migracao.json). Os dois fontes em `research/history/` são cópias históricas para verificar procedência de execuções interrompidas; não são pontos de entrada do simulador.
