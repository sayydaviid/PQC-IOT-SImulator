# Plano registrado: contexto, falhas e perfis TLS

Registrado antes da campanha principal de 18/10/2026; validações de implementação são separadas. Os fontes e a configuração efetiva serão identificados por hash em cada manifesto. Não há parada antecipada baseada em significância ou escolha das melhores células depois da observação.

## Desenho

- Perfis: clássico (X25519 + ECDSA P-256); híbrido com autenticação clássica (X25519MLKEM768 + ECDSA P-256); pós-quântico (X25519MLKEM768 + ML-DSA-44).
- Todos: TLS 1.3, TLS_AES_256_GCM_SHA384, autenticação mútua, nomes/CA verificados, 0-RTT desativado, tickets válidos por 3.600 s. Mesma estrutura de certificados, identidades, aplicação e carga. O contraste híbrido/clássico isola a troca; PQC/híbrido altera autenticação e certificados.
- Tratamentos: autenticação completa em cada tentativa; retomada com chave de tickets volátil; retomada com chave preservada. O comparador completo é compartilhado pelos dois contrastes de estado, sem contá-lo duas vezes como evidência independente.
- As duas políticas de retomada usam a MESMA construção de tickets sem cache por sessão, via callback EVP nativo OpenSSL. A chave possui nome de 16 bytes, cifragem de 32 bytes e MAC de 32 bytes. Ela permanece em diretório privado temporário e não é exportada nos resultados. Preservação é uma variável experimental, não uma proposta inédita de gerenciamento de chaves. Rotação, comprometimento da chave e atualizações de confiança ficam fora desta campanha.
- Nove leituras por ensaio: uma inicial sem falha e oito elegíveis. Cada leitura inicia processo novo do cliente. Reinícios do gateway ocorrem antes de 0, 2 ou 8 das leituras elegíveis (0%, 25%, 100%). Perda lógica da confirmação após gravação ocorre na primeira tentativa de 0, 2 ou 8 leituras elegíveis, com uma nova tentativa sem essa interrupção. Os dois conjuntos são sorteados independentemente por bloco, podem coincidir e são iguais entre comparadores.
- Deduplicação ativa/desativada; nos dois modos o banco e os identificadores são preservados após reinício. O controle mantém rastreamento e rejeita conflitos, alterando apenas a supressão dos efeitos.
- Dez blocos completos. Cada bloco usa outra agenda de falhas e ordem aleatória reproduzível das configurações; a unidade de repetição é o bloco.
- Campanha principal: perda de pacotes configurada em 0%, 3 frequências de reinício × 3 de confirmação × 3 perfis × 3 tratamentos × 2 deduplicações × 10 blocos = 1.620 ensaios.
- Robustez: perdas de 1% e 5%, frequências de reinício/confirmação em 25%/25%, deduplicação ativa, todos os perfis/tratamentos e 10 blocos = 180 ensaios adicionais. Não generalizar essa fatia para todo o fatorial de perda.
- Mininet-WiFi, um sensor e um gateway, atraso de 2 ms por direção no enlace AP–servidor, fila netem de 1.000 pacotes, sem limite de taxa configurado nesse qdisc. Agendas de falhas são pareadas; realizações aleatórias da perda do kernel não são pareadas.

## Medidas e critérios anteriores aos resultados

Medidas primárias: bytes IPv4 por leitura lógica confirmada durante a sequência inteira; tempo até confirmação incluindo inicialização/reinício do gateway e repetição após confirmação perdida; quantidade de efeitos duplicados. Medidas auxiliares: registros TLS, número de retomadas/completos, retransmissões TCP, tempo após TCP conectado, tempo de inicialização do gateway e duração da sequência. A captura começa antes do processo inicial do gateway; a medição temporal termina na última confirmação e exclui auditoria e encerramento da captura. IPv4 inclui tentativas e encerramentos observados no servidor, não quadros Wi-Fi físicos.

Antes de aceitar um ensaio, verificar parâmetros e assinatura negociados, identidade mútua, compartilhamentos públicos novos, modo efetivo de cada conexão, cobertura dos bytes TLS capturados, zero descartes da captura no kernel e nove leituras confirmadas. O controle deve produzir exatamente um efeito adicional por confirmação perdida; com supressão ativa, deve produzir zero. Não exportar segredos TLS; não alegar prova direta de unicidade de nonce TLS.

Analisar contrastes por bloco e relatar medianas/intervalos bootstrap com semente fixa, preservando todos os comparadores do bloco no reamostramento. Intervalos por célula são exploratórios, sem garantia simultânea para o fatorial. Relatar também resultados negativos, custos que aumentarem e dispersão. Não tratar leituras/processos como repetições independentes; não escolher um número de blocos a partir dos p-valores.

Hipóteses delimitadas: preservar o contexto pode reduzir o custo da recuperação quando reinícios impedem retomadas; esse efeito pode depender do perfil e da frequência. Nova sessão, sozinha, não elimina reaplicação após confirmação perdida. Se os dados apenas reproduzirem essas consequências esperadas sem acrescentar uma caracterização útil, concluir contribuição incremental e não vender a integração como um protocolo novo.

## Limites

Banco atualizado e chave de tickets preservada quando configurada, credenciais e entropia fora de rollback; uma confirmação perdida na primeira tentativa seguida de repetição sem nova interrupção lógica; um sensor; efeitos restritos ao banco. Não há fila persistente de sensor físico, atuação externa, energia, comprometimento de STEK ou resistência a rollback conjunto. As campanhas antigas e seus fontes não serão alterados. A leitura integral do antecedente está registrada em `docs/comparacao_catoni_completa.md`.

## Ajuste de instrumentação antes da rodada definitiva

A primeira rodada principal (`continuity_core_registered_20261018_v1`) foi interrompida e será excluída integralmente: o tempo externo terminava após o encerramento do processo, incluindo trabalho posterior à confirmação. O endpoint agora exporta o instante monotônico da confirmação; o controlador verifica a mesma base de tempo e mede até esse instante, antes da gravação posterior da sessão e do encerramento TLS. O desenho, número de blocos, hipóteses e medidas de bytes/efeitos permanecem iguais. A rodada definitiva será identificada por outro diretório e novos hashes, sem reaproveitar células da rodada interrompida. A seleção não se baseia em significância, magnitude de ganhos ou resultados favoráveis.

Validações de implementação `smoke` são excluídas da inferência. Uma validação local também foi invalidada pelo verificador de hashes após um ajuste de metadados durante sua execução; seus resultados não são uma campanha concluída. Uma validação de rede anterior completou os 18 cenários e os controles negativos completaram 12 verificações. A instrumentação temporal final será verificada novamente antes da campanha definitiva.

## Revisão prospectiva 3: tentativas limitadas e resultados de entrega

A rodada `continuity_core_registered_20261018_v2` foi interrompida ao observar uma confirmação não recebida fora da injeção programada, em netem 0%. O gateway havia gravado a leitura e emitido a resposta; os registros mostram retransmissões TCP. A rotina anterior abortava porque pressupunha confirmação em toda tentativa sem interrupção lógica. Essa pressuposição não é apropriada ao experimento em rede. Nenhum contraste de efeitos ou teste de significância foi usado para decidir o ajuste.

A rodada definitiva v3 repetirá todo o desenho e os dez blocos, sem incorporar células de v1/v2. Fica estabelecido, antes de executá-la:

- Máximo de três tentativas por leitura, sempre com o mesmo identificador. Watchdog externo de 95 segundos por processo; timeouts e confirmações não observadas são registrados, nunca repetidos indefinidamente até obter sucesso.
- A confirmação programada é suprimida uma vez, após o primeiro recebimento e gravação da leitura selecionada. Se o transporte impedir a leitura de chegar, a injeção fica pendente até o primeiro recebimento; não se move por número de conexão. O conjunto de leituras selecionadas continua igual entre comparadores.
- Perdas não programadas são registradas separadamente das injeções; leituras não confirmadas ao esgotar o orçamento permanecem nos resultados. PASS da instrumentação não significa entrega de todas as leituras nem confirmação da hipótese científica.
- São relatadas leituras programadas, processadas, confirmadas e não confirmadas, além do volume de tráfego. O custo por leitura confirmada é indefinido quando nenhuma é confirmada; não substituir por zero. As diferenças de tempo até entrega completa não são estimadas quando algum bloco comparado possui leituras não confirmadas. Não excluir esses blocos para obter ganho de latência.
- O controle sem supressão deve produzir um efeito por recebimento real; com supressão, um efeito por identificador/conteúdo novo. O número de duplicações pode superar o número de injeções se a rede causar perdas adicionais. Não forçar o controle a produzir apenas as duplicações programadas.
- Captura no servidor pode conter uma resposta que não chegou ao cliente. A auditoria usa os bytes efetivamente recebidos como limite inferior e os bytes emitidos como limite superior, preservando a exigência de continuidade do fluxo e zero descartes da captura no kernel. Falhas de handshake sem metadados nativos são registradas separadamente e não são apresentadas como conexões autenticadas verificadas.

Esta revisão substitui a exigência anterior de todas as leituras confirmadas como condição para conservar um ensaio. Os tamanhos do fatorial, perfis, políticas, agendas e unidade de repetição permanecem iguais. A hipótese será reavaliada considerando também as falhas de entrega observadas. Os diretórios interrompidos serão mantidos como diagnóstico, fora da inferência da v3.

Esclarecimento da auditoria da v3: callbacks de cabeçalho TLS contabilizam o comprimento anunciado do registro, mesmo se seu corpo não for completamente recebido em uma tentativa interrompida. Os limites inferiores usam, portanto, etapas comprovadamente concluídas (handshake, leitura processada e confirmação recebida), confrontadas com prefixos TCP contíguos. Uma lacuna antes desses bytes invalida a auditoria; lacunas posteriores em fluxos de transporte não concluídos são registradas como resultado, sem convertê-las em bytes entregues. Mantêm-se zero descartes no kernel da captura e a preservação de todos os PCAPs.
