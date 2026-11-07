# Reprodução da campanha ampliada de continuidade

Esta campanha é separada do piloto de 60 condições. Os parâmetros registrados estão em `plano_campanha_continuidade.md` e a leitura integral do antecedente em `comparacao_catoni_completa.md`. As duas políticas usam tickets sem cache por sessão; não comparar os novos custos diretamente com o piloto antigo de cache em RAM.

## Runtime

```bash
docker build -t pqc-iot-continuity:3.5.9-v2 -f experiments/continuity/Dockerfile .
```

Imagem construída nesta execução: `sha256:1b6e54c9f613d3b4b96b7aec5926f21e6554cca7d067cd07dfe8dffaeedb55d0`; base TLS: `sha256:aa8b84fd346c76bad96f76cca9ed8d99a47d296fbffe0ae16e305c9e9a0db804`. OpenSSL 3.5.9, revisão `45e844fa2a14ec92d146bd8f5778ac130b6625fb`. O manifesto registra o hash do módulo nativo compilado, o código C e os demais fontes usados. A tag pode ser movida; para repetir o ambiente, conferir a identidade da imagem e a revisão efetiva, além dos fontes.

O módulo `_continuity_tls` preserva o protocolo e a derivação nativos do OpenSSL. O callback de tickets usa a API EVP documentada em https://docs.openssl.org/3.5/man3/SSL_CTX_set_tlsext_ticket_key_cb/. A comparação altera a persistência da mesma construção de tickets, não um protocolo TLS próprio.

O endpoint é executado diretamente como script para não inicializar módulos de topologia e gráficos em cada processo do sensor. A lógica de banco e checkpoint é carregada dos mesmos arquivos das campanhas anteriores, sem alterá-los. A medição temporal usa relógio monotônico comum entre os namespaces: início no controlador, término no instante da confirmação no cliente. Inclui inicialização do gateway quando prevista; exclui o trabalho do último cliente posterior à confirmação. A sequência inclui naturalmente os encerramentos anteriores necessários antes de enviar a leitura seguinte.

## Detalhes de armazenamento

O cliente serializa a sessão TLS no formato DER e a armazena no campo `der` do checkpoint, junto com `hostname` e `ca_sha256`. O último campo contém o SHA-256 do arquivo do certificado da CA. O checkpoint é cifrado e autenticado com AES-GCM por `SealedStore`, em `pqc_iot_simulator/pqc_iot_sim/components/recovery.py`; sua chave de proteção pertence ao provisionamento e fica fora do rollback do armazenamento do cliente. A autenticação não detecta, por si só, uma cópia antiga válida.

A atualização grava uma cópia temporária no mesmo diretório, sincroniza seu conteúdo com `fsync`, substitui o arquivo com `os.replace` e sincroniza o diretório. O arquivo anterior é substituído somente após a gravação da nova cópia. Essa descrição corresponde ao comportamento de armazenamento utilizado no host, sem medição de energia ou desgaste de flash em sensor físico.

O gateway usa SQLite com `PRAGMA journal_mode=WAL` e `PRAGMA synchronous=FULL`, configurados em `pqc_iot_simulator/pqc_iot_sim/components/reading_ledger.py`. O reconhecimento do identificador e a inserção do efeito ocorrem dentro de uma transação iniciada com `BEGIN IMMEDIATE`. A conclusão dessa transação antecede a confirmação da leitura. O modo de controle mantém essas opções e desativa apenas a supressão de efeitos repetidos. A proteção depende do banco atualizado; restaurar uma versão antiga de todo o banco pode apagar a decisão anterior.

Esses detalhes complementam a descrição de comportamento no artigo e não alteram as configurações ou os dados das execuções concluídas.

## Validações

```bash
python3 -m pytest -q

docker compose -f docker-compose.yml -f experiments/continuity/compose.yml run --rm \
  --entrypoint python3 -e PYTHONDONTWRITEBYTECODE=1 notebook \
  scripts/verify_continuity_security.py --output /workspace/results/raw/continuity_security_reproduction

docker compose -f docker-compose.yml -f experiments/continuity/compose.yml run --rm \
  -e PYTHONDONTWRITEBYTECODE=1 notebook python3 scripts/run_continuity_campaign.py \
  --phase network_smoke --blocks 1 --readings 5 \
  --output /workspace/results/raw/continuity_network_smoke_reproduction
```

A validação de rede tem 18 ensaios: três perfis, três tratamentos e dois modos de deduplicação, com reinício e perda da primeira confirmação em todas as quatro leituras elegíveis. Os 12 controles negativos cobrem, em cada perfil, comprimento inválido da chave dos tickets, CA não confiável, mesmo identificador com outro conteúdo e checkpoint adulterado. Uma sessão adulterada deve levar a autenticação completa, sem aceitar a cópia danificada.

## Campanhas definitivas

Não executar duas campanhas Mininet simultaneamente. Os diretórios de saída devem ser novos. Preparação de credenciais, instalação de topologia e ativação da captura não entram no tempo da sequência. O custo inicial de provisionamento/distribuição da chave dos tickets também não é medido; o carregamento da chave durante o reinício do gateway entra no tempo observado.

```bash
docker compose -f docker-compose.yml -f experiments/continuity/compose.yml run --rm \
  -e PYTHONDONTWRITEBYTECODE=1 notebook python3 scripts/run_continuity_campaign.py \
  --phase core --blocks 10 --readings 9 \
  --output /workspace/results/raw/continuity_core_reproduction

docker compose -f docker-compose.yml -f experiments/continuity/compose.yml run --rm \
  -e PYTHONDONTWRITEBYTECODE=1 notebook python3 scripts/run_continuity_campaign.py \
  --phase loss --blocks 10 --readings 9 \
  --output /workspace/results/raw/continuity_loss_reproduction
```

A campanha principal contém 1.620 ensaios em 0% de perda de pacotes. A fatia de robustez contém 180 ensaios em 1%/5%, com reinício e perda de confirmação em 25% das leituras elegíveis e deduplicação ativa. Cada ensaio tem uma leitura inicial sem falha e oito elegíveis. Os percentuais de falha lógica se aplicam à primeira tentativa das leituras elegíveis, não a todas as retransmissões nem aos pacotes TCP. A repetição após a confirmação perdida não sofre outra interrupção lógica programada.

Cada configuração usa o mesmo conteúdo e agenda do respectivo bloco. Os conjuntos de reinícios e perdas de confirmação podem coincidir e a realização da perda do kernel não é pareada. O comparador completo é executado uma vez por bloco/célula e compartilhado pelos dois contrastes de estado. Banco preservado, efeito dentro da transação SQLite, 0-RTT desabilitado e um sensor são limites da campanha.

O manifesto contém ambiente efetivo de CPU, RAM, SO, kernel, versão do tc, revisão Mininet-WiFi e OpenSSL. Qdiscs e interfaces/MTU são gravados por bloco. PCAP é confrontado com cada conexão TLS por sequência e compartilhamento público; descartes da captura no kernel invalidam o ensaio. Conservar os dados brutos e os metadados em conjunto. Arquivos de chaves, tickets DER e credenciais permanecem privados em diretórios temporários e são removidos ao terminar.

## Análise

```bash
docker compose -f docker-compose.yml -f experiments/continuity/compose.yml run --rm \
  --entrypoint python3 -e PYTHONDONTWRITEBYTECODE=1 notebook \
  scripts/summarize_continuity.py \
  --core /workspace/results/raw/continuity_core_reproduction \
  --loss /workspace/results/raw/continuity_loss_reproduction \
  --output /workspace/docs/resultados_continuidade_reproduction
```

A análise exige os dois `results.json` completos, status PASS e todas as células/blocos previstos, rejeitando comparadores ausentes. Produz dados por ensaio, medianas, contrastes pareados, efeito da preservação e decomposição dos custos de migração. O perfil híbrido/ECDSA mantém a autenticação clássica e altera a troca; PQC/híbrido altera assinatura e certificados. Equivalência é operacional, não uma alegação de igual resistência a adversários quânticos. Cada perfil possui credenciais próprias; nos perfis ECDSA, a codificação DER das assinaturas pode variar poucos bytes mesmo com a mesma estrutura. Os tamanhos e hashes públicos dos certificados foram registrados separadamente na continuação v4. Esses metadados não foram conservados para as credenciais temporárias dos quatro blocos importados; não foram reconstruídos a partir da máquina atual. Os contrastes são entre configurações equivalentes, sem alegar precisão de byte isolado para uma operação criptográfica.

Os intervalos bootstrap (10.000 reamostragens, semente fixa) usam contrastes por bloco. São intervalos exploratórios por célula, não simultâneos para todo o fatorial, e não transformam leituras em repetições independentes. Gráficos são coloridos, seguindo a preferência atual do autor. O arquivo `audit.json` registra hashes dos resultados/manifestos de entrada e do analisador.

### Continuação de 21/10 e análises explicativas

A interrupção da infraestrutura, o descarte detectado na captura e as continuações por blocos completos estão documentados em `continuidade_retomada_execucao_20261021.md`. A campanha principal foi concluída em `results/raw/continuity_core_registered_20261021_v5`, com 1.620 ensaios e código de saída zero; a fase de perdas usa `results/raw/continuity_loss_registered_20261021_v5`. As rodadas v3/v4 permanecem como arquivos de procedência e diagnóstico, sem constituir outras amostras independentes dos blocos incorporados. O manifesto v5 registra o buffer de captura de 16.384 KiB e a cadeia de importação dos blocos.

O analisador também exporta `interacoes_falhas.csv`, com contrastes de quatro cantos dentro de cada bloco, e `clienthello_tamanhos.csv`, com comprimentos públicos do ClientHello e da identidade PSK. Essas análises explicativas foram acrescentadas durante a execução e estão descritas em `continuidade_analise_exploratoria.md`. O parser lê a codificação pública do TLS 1.3 conforme as Seções 4.1.2 e 4.2.11 de https://www.rfc-editor.org/rfc/rfc8446.html; não decifra tickets nem exporta seu conteúdo. Isso é documentação técnica do artefato, sem acrescentar uma RFC à bibliografia do artigo.

Os gráficos são exportados em PNG, SVG e PDF. A existência de arquivos de gráfico não substitui a validação dos dois manifestos e matrizes completos.

### Resultado e diagnóstico de cadeia

As duas matrizes v5 terminaram com status PASS, 1.800 ensaios, 16.200 leituras confirmadas e 21.960 tentativas. A consolidação está em `resultado_continuidade.md` e `resultados_continuidade_20261021_v5/audit.json`. A suíte local passou com 112 testes; o aviso de versões liboqs/liboqs-python preexiste e não corresponde ao backend TLS nativo.

O diagnóstico abaixo confirma a cadeia pública enviada pelo servidor, usando credenciais novas e o mesmo contexto nativo, sem medir outra configuração de custo. O script captura a saída de `s_client` apenas em memória e exporta contagens, tamanhos e hashes públicos de certificados, sem gravar seus diagnósticos de sessão/PSK.

```bash
docker compose -f docker-compose.yml -f experiments/continuity/compose.yml run --rm \
  --entrypoint python3 -e PYTHONDONTWRITEBYTECODE=1 notebook \
  scripts/verify_continuity_chain.py --output /workspace/results/raw/continuity_chain_reproduction
```

Os três perfis da avaliação original enviaram folha e CA raiz. Essa condição deve acompanhar os resultados históricos. Naquela avaliação, a sensibilidade à retirada da raiz ainda não havia sido medida. O controle adicional descrito abaixo compara as duas cadeias em ambos os participantes, mantendo a raiz confiável; seus resultados são separados dos anteriores. Não apresentar os resultados históricos como referentes a uma cadeia sem transmissão da raiz.

## Integridade e rodadas excluídas

A rodada principal `continuity_core_registered_20261018_v1` foi interrompida para corrigir a fronteira temporal e não deve ser agregada à definitiva. Validações `smoke*` não entram nos resultados científicos; diretórios sem `results.json` final não são campanhas completas. Não aproveitar células favoráveis de uma rodada incompleta. Os experimentos antigos de 14/10 e seus fontes permanecem preservados.

## Instrumentação definitiva v3: falhas reais conservadas

A v2 foi interrompida por uma confirmação não observada fora da injeção programada; o gateway havia registrado e enviado a resposta. A v3 conserva falhas desse tipo e aplica no máximo três tentativas por leitura, com watchdog de 95 s por processo. A injeção seleciona o identificador da leitura e suprime uma vez a confirmação após seu primeiro processamento, sem depender da posição da conexão. Não há repetição de ensaio até obter o resultado esperado.

PASS significa integridade da instrumentação, não aprovação da hipótese nem entrega universal. `confirmed_readings`, `unconfirmed_readings`, `delivery_status` e os registros por tentativa permitem identificar leituras cujo orçamento se esgotou. A validação adicional abaixo força todas as confirmações a se perderem: cada perfil/modo de deduplicação deve conservar cinco leituras não confirmadas, com quinze tentativas e efeitos consistentes com os recebimentos reais.

```bash
docker compose -f docker-compose.yml -f experiments/continuity/compose.yml run --rm \
  --entrypoint python3 -e PYTHONDONTWRITEBYTECODE=1 notebook \
  scripts/verify_continuity_outcomes.py --output /workspace/results/raw/continuity_budget_reproduction
```

A análise não remove esses blocos. Custo por confirmação é indefinido se não houver nenhuma confirmação; tempo até entrega completa não recebe estimativa quando o par de comparadores contém uma sequência incompleta. Os dados por tentativa distinguem injeção programada, ausência não programada e censura pelo watchdog. As duplicações esperadas no controle dependem dos recebimentos reais, não apenas da quantidade de falhas injetadas.

A auditoria exige prefixos TCP contíguos até as mensagens cuja entrega é comprovada e limites de emissão dos participantes. Contadores de cabeçalhos TLS de leituras interrompidas podem anunciar bytes ainda não recebidos, por isso não são tratados como recibos de corpo completo. Lacunas de transporte posteriores aos prefixos comprovados são registradas, e falhas de handshake sem metadados não são apresentadas como conexões autenticadas verificadas. Os arquivos brutos de v1/v2 permanecem disponíveis para diagnóstico, fora das estimativas definitivas.

## Verificações adicionais iniciadas em 6 de novembro de 2026

Os novos experimentos preservam os fontes da avaliação anterior e utilizam `experiments/context_costs/`. O protocolo está em `plano_verificacoes_contexto_20261106.md`, com o detalhamento do cliente persistente em `metodo_amortizacao_20261106.md`. A comparação das cadeias e a de amortização devem ser executadas sequencialmente, sem duas topologias Mininet em paralelo. Verificações funcionais em localhost não entram nas amostras de custo.

```bash
docker build -t pqc-iot-context-costs:3.5.9-v1 -f experiments/context_costs/Dockerfile .

docker compose -f docker-compose.yml -f experiments/context_costs/compose.yml run --rm \
  -e PYTHONDONTWRITEBYTECODE=1 notebook python3 scripts/run_context_costs.py \
  --blocks 10 --output /workspace/results/raw/context_chain_reproduction

docker compose -f docker-compose.yml -f experiments/context_costs/compose.yml run --rm \
  -e PYTHONDONTWRITEBYTECODE=1 notebook python3 scripts/run_context_amortization.py \
  --blocks 10 --output /workspace/results/raw/context_amortization_reproduction
```

O primeiro experimento compara folha e raiz contra apenas folha em ambos os sentidos da autenticação mútua. A raiz continua no armazenamento de confiança. O segundo mantém um processo cliente e 100 leituras lógicas de 512 bytes, variando o máximo de leituras por conexão. O custo inclui o primeiro handshake completo e todos os reenvios e encerramentos. As sessões são salvas quando fica disponível um estado utilizável diferente do anterior.

Os diagnósticos e as verificações de persistência são separados das medições:

```bash
docker compose -f docker-compose.yml -f experiments/context_costs/compose.yml run --rm \
  --entrypoint python3 -e PYTHONDONTWRITEBYTECODE=1 notebook \
  scripts/verify_context_identity_tickets.py \
  --output /workspace/results/raw/context_tickets_identity_reproduction

docker compose -f docker-compose.yml -f experiments/context_costs/compose.yml run --rm \
  --entrypoint python3 -e PYTHONDONTWRITEBYTECODE=1 notebook \
  scripts/verify_context_persistence.py \
  --output /workspace/results/raw/context_persistence_reproduction
```

Os comprimentos dos tickets são consultados em callbacks do OpenSSL. O estado é medido no servidor antes da proteção do ticket, sem exportar seu conteúdo. O módulo registra separadamente o certificado do participante remoto incorporado à sessão, a informação adicional da aplicação, os certificados transmitidos, as mensagens de ticket e os comprimentos públicos do ClientHello. A identidade esperada é conferida também no certificado recuperado na retomada; não é obtida de um campo de dispositivo enviado pela aplicação.

Os testes de interrupção usam o mesmo componente SQLite e diferenciam fechamento normal de SIGKILL. O sistema operacional e o armazenamento permanecem em funcionamento. Não representam cortes de energia. O teste do checkpoint verifica `os.urandom(12)` em processos separados e sob restauração de arquivos, incluindo um controle negativo de fonte de nonce repetida. A ausência de colisões observadas não é uma garantia determinística.

Após concluir os dois experimentos, executar as auditorias e a análise:

```bash
docker compose -f docker-compose.yml -f experiments/context_costs/compose.yml run --rm \
  --entrypoint python3 -e PYTHONDONTWRITEBYTECODE=1 notebook \
  scripts/verify_context_results.py --kind chains \
  --input /workspace/results/raw/context_chain_reproduction \
  --output /workspace/docs/resultados_contexto_reproduction/auditoria_cadeias.json

docker compose -f docker-compose.yml -f experiments/context_costs/compose.yml run --rm \
  --entrypoint python3 -e PYTHONDONTWRITEBYTECODE=1 notebook \
  scripts/verify_context_results.py --kind amortization \
  --input /workspace/results/raw/context_amortization_reproduction \
  --output /workspace/docs/resultados_contexto_reproduction/auditoria_amortizacao.json

docker compose -f docker-compose.yml -f experiments/context_costs/compose.yml run --rm \
  --entrypoint python3 -e PYTHONDONTWRITEBYTECODE=1 notebook \
  scripts/summarize_context_costs.py \
  --chains /workspace/results/raw/context_chain_reproduction \
  --amortization /workspace/results/raw/context_amortization_reproduction \
  --output /workspace/docs/analise_contexto_reproduction
```

As auditorias exigem o desenho completo, os hashes dos fontes, as cadeias efetivamente enviadas e a correspondência entre os comprimentos do ClientHello medidos no módulo e na captura. A análise apresenta custos absolutos e reduções calculadas dentro da mesma repetição. Os intervalos bootstrap permanecem exploratórios por configuração.

Para verificar as fronteiras também no gateway TLS real, o controle complementar abaixo autentica o cliente, interrompe o processo no ponto de gravação escolhido e reenvia a mesma leitura após reiniciar. São cinco fronteiras, três perfis e dois términos de processo: SIGTERM tratado com fechamento do banco ou SIGKILL sem finalização. O teste é executado em localhost e fica fora das amostras de custo.

```bash
docker compose -f docker-compose.yml -f experiments/context_costs/compose.yml run --rm \
  --entrypoint python3 -e PYTHONDONTWRITEBYTECODE=1 notebook \
  scripts/verify_context_persistence_tls.py \
  --output /workspace/results/raw/context_persistence_tls_reproduction
```

### Procedência da retomada em 7 de novembro

A execução original das cadeias foi interrompida pela infraestrutura com nove blocos completos e 51 das 54 condições do último bloco concluídas. Os dados originais permanecem em `results/raw/context_chain_registered_20261106_v1`. Todas as condições do bloco 9 foram repetidas, com os mesmos fontes e imagem, em `context_chain_repeated_block9_20261107_v1`; as 51 condições do bloco incompleto foram excluídas em conjunto, sem seleção de células.

O conjunto consolidado fica em `results/raw/context_chain_completed_20261107_v1`, com nove blocos originais e um bloco repetido. Seu manifesto conserva a origem de cada grupo e referencia o manifesto da repetição. Os diretórios das execuções são ligações relativas aos arquivos preservados. Para mover o conjunto bruto, conservar também os dois diretórios de origem ou copiar seguindo as ligações. Os principais componentes do ambiente e o módulo nativo permaneceram iguais; a memória livre do host variou.

O executor `scripts/resume_context_validation.py` verifica os fontes, repete o bloco inteiro e executa sequencialmente a amortização e a consolidação. O contêiner nomeado `context-verifications-20261107` roda desacoplado da sessão de terminal, permitindo acompanhar sua saída com `docker logs`. As tabelas e auditorias finais ficam em `docs/resultados_contexto_20261106`; a interpretação fica em `docs/resultado_contexto_20261106.md`.

### Auditoria e testes concluídos

As duas matrizes concluíram 540 execuções cada, com 4.860 e 54.000 leituras confirmadas, respectivamente. As auditorias passaram em 6.660 e 20.340 ClientHello, verificando a correspondência das capturas com os comprimentos medidos no OpenSSL, a carga dentro dos blocos e os certificados transmitidos nos dois sentidos. Os 30 controles adicionais do gateway TLS também passaram.

O leitor antigo de ClientHello utilizava somente as portas para reconhecer a direção. Uma porta temporária do cliente coincidiu com a porta 39911 do servidor em uma captura, causando interpretação do ServerHello como ClientHello. O adaptador em `scripts/context_capture.py` identifica o IP iniciador pelo SYN sem ACK e seleciona a direção do cliente antes de usar o leitor congelado. Os dados brutos e as contagens de bytes não mudaram: o contador de custos já distinguia os IPs. Dois testes de regressão verificam a coincidência das portas e a rejeição de múltiplos IPs iniciadores ambíguos.

A imagem de medição não contém `pytest`. As auditorias e os controles TLS foram executados nessa imagem; a suíte completa foi executada no host, encerrando com 120 testes aprovados. O aviso de diferença entre versões de `liboqs` e `liboqs-python` nos testes antigos do protótipo está preservado em `resultados_contexto_20261106/testes.txt`; as medições TLS usam o OpenSSL da imagem identificada no manifesto.

Na execução registrada, a consolidação foi retomada com `--resume-postprocessing`, conferindo os hashes dos dados e do analisador já concluído. O comando abaixo completou o registro final com os testes locais, conservando a tentativa anterior sem `pytest` em `testes_container.txt`:

```bash
python3 scripts/complete_context_tests.py --analysis docs/resultados_contexto_20261106
```

O estado final está em `resultados_contexto_20261106/verificacao_final.json`, com resultado `PASS`, hashes dos fontes da análise, ambiente dos testes e caminho do registro da tentativa no contêiner.
