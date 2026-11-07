# Foco da contribuição após as verificações adicionais

O artigo deve destacar a avaliação do custo da recuperação e a explicação das diferenças entre os perfis. Checkpoints autenticados, chaves de tráfego novas e deduplicação persistente sustentam a implementação e seus critérios de segurança. A questão experimental é como a representação da identidade no ticket, a preservação do contexto e a quantidade de leituras por conexão alteram o custo por leitura confirmada.

## Relação já verificada no diagnóstico

O ticket de 4.240 bytes está relacionado ao certificado folha do cliente incorporado ao estado da sessão no servidor. A observação foi confirmada pela API nativa e por um controle que mantém exatamente o servidor e a CA, alterando a chave do certificado do cliente. O certificado passou de 4.018 para 2.775 bytes, o estado serializado de 4.170 para 2.927 bytes e o ticket de 4.240 para 2.992 bytes. A diferença do ticket inclui o preenchimento CBC.

Isso fornece uma explicação para o material que acompanha uma oferta recusada de retomada. A perda da chave impede aproveitar o ticket, mas o cliente já o enviou no ClientHello. O acréscimo precisa ser medido em valores absolutos e em relação ao custo completo do mesmo perfil. O maior ticket não implica automaticamente o maior aumento percentual, pois o custo completo também muda.

A troca assimétrica nova permanece presente tanto no completo como na retomada. Assim, no perfil híbrido, a retomada conserva o custo da contribuição X25519MLKEM768, embora evite repetir a autenticação por certificados ECDSA. No perfil pós-quântico, os certificados e a autenticação completos também são maiores, mas o certificado do cliente amplia o ticket oferecido. As diferenças entre os perfis devem ser interpretadas por esses componentes e pelo número de conexões necessárias, sem atribuir toda a variação a uma única assinatura ou operação.

A raiz transmitida influencia esse denominador. Retirá-la da transmissão preserva a confiança e não retira o certificado folha do cliente do estado incorporado ao ticket. A comparação controlada das cadeias permite quantificar essa sensibilidade. O custo de um handshake deve ainda ser relacionado ao número de leituras que compartilham a conexão, incluindo a primeira autenticação completa e as novas tentativas.

Os diagnósticos não demonstram que todo servidor TLS com ML-DSA produz um ticket desse tamanho. O resultado corresponde ao OpenSSL, à autenticação mútua, às credenciais e à representação de sessão avaliados. Implementações que conservam uma referência ou representam a identidade de outra forma podem apresentar outros custos.

## Contribuições para a revisão do texto

1. Caracterização experimental do custo de perder o contexto de retomada, comparando custos absolutos e economias em configurações clássica, híbrida e pós-quântica, com e sem a raiz transmitida.
2. Explicação das diferenças de tamanho dos tickets por meio de medições dos certificados, das sessões serializadas e do ClientHello, incluindo o controle com servidor e CA mantidos.
3. Avaliação do compartilhamento da conexão por várias leituras, mantendo a mesma carga e distinguindo a recuperação do canal do reconhecimento de efeitos já registrados.

As verificações da persistência e do checkpoint sustentam as condições dessas comparações. Os testes de processo não representam queda de energia. O nonce do checkpoint depende do gerador criptográfico do sistema operacional e possui garantia probabilística. O identificador de dispositivo corresponde à identidade TLS única autorizada; o modelo ainda não contém um cadastro geral de vários sensores. O banco mantém identificadores e resumos, sem persistir o payload integral.

## Consolidação dos custos

A comparação das cadeias concluiu os dez blocos: 540 execuções e 4.860 leituras confirmadas, sem efeitos duplicados. No cenário com reinício e supressão da confirmação em todas as oito leituras elegíveis, os custos pós-quânticos foram:

| Cadeia enviada por ambos os participantes | Completo: bytes/leitura | Contexto perdido: bytes/leitura | Contexto preservado: bytes/leitura | Economia com preservação | Acréscimo com perda |
|---|---:|---:|---:|---:|---:|
| Folha e raiz | 57.467,22 | 65.603,44 | 18.448,78 | 67,89% | 14,18% |
| Apenas folha | 41.463,67 | 49.645,00 | 17.504,78 | 57,79% | 19,70% |

Os custos absolutos são medianas por leitura confirmada; os percentuais são medianas das comparações realizadas dentro da mesma repetição. Não foram calculados como razão entre as medianas da tabela. A retirada da raiz diminui o custo completo mais do que o custo com retomada preservada e aumenta a importância relativa da oferta recusada. O benefício da preservação permanece na condição sem transmissão da raiz, mas sua magnitude muda. Os valores valem para esta implementação, credenciais, frequência de falhas e carga.

No mesmo cenário, o acréscimo com contexto perdido passa de 14,88% para 17,17% no clássico e de 11,32% para 12,99% no híbrido ao retirar a raiz. Com a raiz transmitida, o acréscimo percentual clássico supera o pós-quântico; sem transmiti-la, ocorre o contrário. Portanto, a ordenação por percentuais também depende da cadeia, além da representação do ticket. Isso reforça a necessidade de apresentar os custos absolutos e de restringir a conclusão às condições medidas.

A interrupção da infraestrutura deixou o último bloco original incompleto. Foram preservados os nove blocos completos e repetidas todas as 54 condições do último bloco, conservando as execuções incompletas fora das estimativas. O manifesto consolidado registra essa procedência em `results/raw/context_chain_completed_20261107_v1/manifest.json`.

A comparação de amortização também concluiu os dez blocos: 540 execuções e 54.000 leituras confirmadas, sem efeitos duplicados. Todas as condições enviam as mesmas 100 leituras de 512 bytes em um processo cliente, incluindo a primeira autenticação completa. A raiz permanece confiável, sem ser transmitida. No perfil pós-quântico:

| Cenário | Limite de leituras por conexão | Completo: bytes/leitura | Contexto perdido: bytes/leitura | Contexto preservado: bytes/leitura | Economia com preservação |
|---|---:|---:|---:|---:|---:|
| Sem falhas | 1 | 22.865,18 | 9.487,69 | 9.488,73 | 58,50% |
| Sem falhas | 10 | 3.317,04 | 2.097,17 | 2.096,91 | 36,79% |
| Sem falhas | 100 | 1.351,80 | 1.352,58 | 1.352,58 | 0,00% |
| Recuperação | 1 | 23.089,88 | 9.938,96 | 9.575,78 | 58,53% |
| Recuperação | 10 | 3.540,70 | 2.548,18 | 2.186,04 | 38,26% |
| Recuperação | 100 | 1.793,82 | 1.885,86 | 1.523,20 | 15,11% |

Sem falhas e com limite de 100 leituras, todos os tratamentos executam um único handshake completo e nenhuma retomada. Portanto, as pequenas diferenças de tráfego TCP observadas não representam ganho de retomada. Na recuperação, o reinício antes da leitura de índice 50 e a confirmação suprimida dividem o trabalho em três conexões: o completo e a política com contexto perdido realizam três handshakes completos; a preservação realiza um completo e dois retomados. Nesse limite, perder o contexto produz acréscimo de 5,12% frente ao completo, enquanto preservá-lo reduz o custo em 15,11%.

A economia relativa da retomada diminui quando a conexão já compartilha seu custo entre várias leituras. Ao mesmo tempo, o custo absoluto por leitura cai em todos os tratamentos. Isso impede generalizar a economia obtida com uma conexão por leitura para aplicações que mantêm a conexão aberta. As comparações de amortização valem dentro dessa carga de 512 bytes e um processo cliente; não devem ser comparadas diretamente aos custos da matriz de cadeias, que utiliza payload de 31 bytes e novos processos por tentativa.

As auditorias passaram nas duas matrizes: 6.660 ClientHello na comparação das cadeias e 20.340 na amortização foram confrontados com as capturas. Foram conferidos os certificados transmitidos nos dois sentidos, as identidades, os comprimentos dos tickets, os compartilhamentos públicos novos e a correspondência da carga dentro de cada bloco. Os intervalos e tempos estão em `resultado_contexto_20261106.md` e nas tabelas em `resultados_contexto_20261106/`. São resultados de dez blocos, um sensor emulado e um host compartilhado. As verificações funcionais em localhost ficam separadas dessa inferência.

## Centro do artigo

A contribuição experimental passa a ser a relação entre preservação do contexto, representação da identidade nos tickets e quantidade de leituras por conexão. A retirada da raiz confirma que a transmissão da cadeia altera tanto a magnitude quanto a ordenação dos percentuais entre perfis. O controle do certificado do cliente explica parte concreta do tamanho do ticket. A amortização delimita quando o ganho observado com conexões curtas continua relevante. Esses resultados sustentam uma avaliação de custos condicionada à implementação e à carga, sem apresentar os mecanismos conhecidos como um novo protocolo ou uma nova garantia criptográfica.

A amortização e a inclusão do certificado no estado de sessão são comportamentos explicados por mecanismos conhecidos. O diferencial precisa ser defendido pela quantificação controlada de suas consequências na recuperação com autenticação mútua e pelo efeito conjunto das políticas de estado, dos perfis e do uso da conexão. Os experimentos fornecem essa evidência dentro do recorte avaliado; a comparação com os antecedentes continua necessária para defender sua relevância científica.
