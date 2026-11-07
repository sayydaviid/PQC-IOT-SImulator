# Revisão comparativa — PDF atualizado (2)

Data: 18/10/2026.

## Parecer

A estrutura do artigo aprovado foi preservada e funciona para o manuscrito atual. Manter as seis seções é uma escolha adequada. Isso não permite prever aceite: o trabalho atual precisa sustentar sua contribuição experimental diante dos antecedentes, independentemente da organização usada anteriormente. Sem os pareceres do trabalho aprovado, não é possível atribuir sua aceitação à estrutura.

Minha avaliação é de um estudo experimental promissor, com apresentação mais consistente, mas ainda com risco de objeção por contribuição incremental e alcance experimental restrito. Não atribuo probabilidade de aceite nem considero que apenas ajustes de redação resolvam essas questões.

## Material e procedimento

Foram examinados o texto extraído e as páginas renderizadas dos dois documentos. As páginas abaixo são posições no arquivo. Os resultados principais foram confrontados com `docs/resultado_tls_piloto.csv`. Não houve novos experimentos, edição dos PDFs ou mudanças nos dados.

| Documento | Páginas | SHA-256 |
|---|---:|---|
| `sbrc_27_iot_corrigido (2).pdf` | 16 | `940d5ad0a50e30599d6c4750f554c33c83246fe576f9e22bc2e2e19b1f487386` |
| `5904_Versao_final_de_artigo_aceito (1).pdf` | 14 | `02136fd741e43030f502a6757d93ae7ffcc3183a5ad6eba8e384065c678ed31a` |

## Comparação da fórmula

| Elemento | Artigo aprovado | Atual | Parecer |
|---|---|---|---|
| Resumos | Contexto, três desafios, proposta, avaliação e resultados | Mesma sequência, com resultados quantitativos e condições | Preservado |
| Introdução | Motivação, desafios e três contribuições | Mesma sequência, com pergunta explícita e distinção protótipo/TLS | Adequado |
| Fundamentação | Duas subseções principais, equações e duas figuras | Mesma organização, com conceitos ligados às falhas avaliadas | Adequado |
| Relacionados | Antecedentes e diferenças da proposta | Cinco antecedentes, incluindo retomada híbrida próxima | Comparação científica ainda merece aprofundamento |
| Proposta | Modelagem e estratégia com Figura 3 | Mesmo desenho, separando três estados da recuperação | Adequado como descrição da abordagem avaliada |
| Avaliação | Três subseções, comparadores e cenários | Três campanhas, controles negativos e TLS nativo | Alinhada à pergunta; alcance limitado |
| Conclusão | Resultados e futuros | Mesmo formato, resultados delimitados | Adequado |

Não é necessário igualar o número de figuras, equações, referências ou caracteres. A diferença científica principal é que o artigo aprovado apresenta uma política própria de agendamento, com ajuste de rodadas, compensação de falhas e reaproveitamento de pares. O atual avalia a integração de mecanismos conhecidos sob falhas. Estudos experimentais podem contribuir, mas precisam explicitar qual conhecimento adicional suas medições permitem estabelecer.

## Melhorias confirmadas nesta versão

- O documento passou de 18 para 16 páginas em relação ao PDF anterior revisado.
- Abstract e resumo incluem os 55,43–55,57% de redução entre medianas do tráfego IPv4 da sequência completa, além dos 87,96% no handshake com contexto disponível.
- A introdução distingue explicitamente os controles que restauram chaves/contadores da sessão TLS serializada usada para negociar outra conexão.
- A Figura 2 permanece na fundamentação, antes da Seção 3, na página 6.
- As continuações das Figuras 4–6 mantêm a numeração e não atravessam as transições problemáticas observadas anteriormente.
- A conclusão começa na página 15 com seus dois parágrafos completos; o título não ficou isolado com apenas duas linhas.
- A Tabela 2 registra a revisão do OpenSSL e a fila netem de 1.000 pacotes, sem inventar banda configurada.
- Não identifiquei páginas vazias, sobreposições ou referências `??` no PDF examinado. O log de compilação não foi auditado.
- Os gráficos de resultados permanecem coloridos, conforme a preferência atual do autor. Não recomendo sua conversão para preto e branco.

Ainda há ajustes editoriais menores: a lista de contribuições divide-se entre as páginas 2 e 3; na página 12, uma linha final de parágrafo aparece entre as duas partes da Figura 5. Esses pontos têm prioridade menor que a contribuição e a avaliação. A Figura 3 é legível, embora ocupe bastante altura.

## Questões que podem pesar na avaliação

### 1. Conhecimento novo frente aos antecedentes

Retomada reduzir certificados e bytes, deduplicação reconhecer identificadores e perda de cache impedir retomada são comportamentos esperados dos mecanismos utilizados. Os percentuais observados são resultados concretos, mas sua magnitude isolada não estabelece novidade.

O diferencial deve estar na caracterização conjunta de três estados — sessão salva no cliente, contexto no gateway e histórico da aplicação — e nas consequências medidas de sua perda/restauração. Atualização após este parecer: a leitura integral de Catoni et al. foi concluída a partir do PDF fornecido pelo autor; o registro está em `docs/comparacao_catoni_completa.md`. A publicação mede estabelecimento e retomada, mas sua avaliação não inclui a campanha de reinícios, confirmação perdida após gravação e efeitos duplicados proposta neste projeto. A política de tickets compartilhados já é antecedente conhecido; a contribuição depende da caracterização experimental, não da invenção desse mecanismo.

### 2. Alcance da sequência experimental

O piloto usa um sensor, uma implementação TLS, uma política de cache e cinco blocos por configuração. As 60 condições não equivalem a 60 repetições independentes de cada comparação. Cada ensaio de retomada tem dois handshakes completos e quatro retomados, contra seis completos no comparador; a economia medida está condicionada a essa sequência e à frequência fixa de falhas.

O texto informa essas condições corretamente. Para ampliar o alcance científico, o experimento prioritário seria variar disponibilidade/preservação do contexto e frequência de reinícios ou confirmações perdidas, observando custo total e entrega. Uma alternativa relevante é comparar a política atual com uma configuração que preserve o contexto de retomada após reiniciar. Isso pode fortalecer o trabalho sem exigir mudança da estrutura ou um algoritmo novo.

### 3. Papel específico de PQC

O piloto utiliza PQC real, mas disponibilidade de contexto e reconhecimento de duplicações também importam em TLS clássico. Uma configuração clássica equivalente permitiria medir o custo adicional e o benefício relativo na migração pós-quântica. Sem esse comparador, manter a alegação de avaliação de uma configuração PQC, sem atribuir os mecanismos de recuperação exclusivamente a PQC. O texto atual já evita essa generalização.

### 4. Precisão das garantias

A ausência de reutilização de chave/nonce foi observada diretamente no protótipo. No TLS, verificaram-se parâmetros, identidades e compartilhamentos públicos, sem exportar os segredos internos. O identificador pendente é conservado pelo controlador dos ensaios, sem fila persistente implementada em sensor físico. A deduplicação protege efeitos registrados na transação do banco, com histórico atualizado; não estabelece execução única de atuadores ou resistência a rollback conjunto. Essas delimitações estão presentes e devem ser mantidas.

A ausência de hardware físico não invalida o recorte emulado. Entretanto, resultados de memória, energia ou tempo em sensores físicos exigiriam outra avaliação.

## Conferência dos números

| Perda | Completo: mediana IPv4 | Retomada: mediana IPv4 | Redução entre medianas |
|---|---:|---:|---:|
| 0% | 157.895 | 70.250 | 55,51% |
| 1% | 157.895 | 70.158 | 55,57% |
| 5% | 158.287 | 70.550 | 55,43% |

Os valores correspondem ao CSV, com deduplicação ativa. Os 87,96% referem-se ao handshake com contexto disponível, de 23.859 para 2.873 bytes TLS, com outra fronteira de medição. O CSV também confirma 30 efeitos duplicados sem supressão e zero com supressão.

Em 1% de perda, a mediana de recuperação é maior na retomada: 506,8 ms contra 482,0 ms. A versão reconhece isso, evitando alegação geral de redução de tempo. Os controles do protótipo e os bytes TLS não são comparados como protocolos de parâmetros equivalentes.

## Reprodutibilidade e chamada

O PDF ainda não informa todos os metadados históricos de CPU/RAM/SO e revisão do Mininet-WiFi. Completar apenas o que os registros da campanha permitem confirmar. A máquina atual não substitui automaticamente o ambiente histórico. Uma referência imutável do artefato, além do link para o repositório, favorece a reprodução.

A versão atual tem 16 páginas, contra 14 da referência. Isso não demonstra conformidade ou violação da chamada pretendida. Foram tentados os endereços oficiais da trilha principal de 2027 e da edição de 2026; o conteúdo da chamada não pôde ser recuperado nesta consulta. Não foram confirmados limite de páginas, anonimização ou critérios específicos da edição pretendida. Não se aplicaram regras de workshops ou de outras conferências por analogia.

## Prioridades

1. Fechar a leitura do antecedente mais próximo e explicitar a contribuição experimental verificável.
2. Ampliar a avaliação de disponibilidade do contexto e frequência de falhas, em vez de apenas repetir a sequência fixa.
3. Incluir TLS clássico equivalente caso se pretenda quantificar o efeito específico da migração para PQC.
4. Completar os metadados históricos disponíveis e conferir a chamada oficial.
5. Fazer o acabamento local de paginação, preservando as seis seções e as cores atuais.

Eu manteria a organização e o tema. A redação está mais consistente e os resultados têm escopo claro; o reforço de maior valor agora está na contribuição e na avaliação experimental.

## Atualização experimental de 21/10/2026

Esta atualização diz respeito ao repositório e à campanha nova, não a uma nova versão do PDF de 16 páginas examinado acima. A leitura integral de Catoni foi encerrada e a avaliação ampliada foi executada: 1.620 ensaios principais e 180 de perdas, com dez blocos, três perfis TLS, três tratamentos e frequências de falhas variáveis. Todos os 16.200 identificadores lógicos foram confirmados em 21.960 tentativas. Ver o parecer e os dados em [resultado_continuidade.md](resultado_continuidade.md).

A principal evidência acrescentada é a mudança de sinal da economia conforme o estado. Com reinício e confirmação perdida em todas as leituras elegíveis, o perfil PQC apresentou economia pareada de 67,87% com preservação, mas aumento de 14,24% com chave de tickets volátil, frente ao completo direto. A análise pública dos ClientHello encontrou identidades PSK de 4.240 bytes no PQC, 640 no clássico e 640–656 no intermediário. A deduplicação teve zero efeitos duplicados, contra 2.700 nos controles da matriz principal. Não há sustentação para vantagem temporal geral sob perda.

A ampliação resolve a sequência única e acrescenta uma explicação quantitativa do custo, mas não torna inéditos os mecanismos. As contagens reproduzem exatamente o comportamento esperado da disponibilidade de tickets e das interrupções. Além disso, um controle posterior confirmou envio da CA raiz na cadeia do servidor nos três perfis; a magnitude dos percentuais depende dessa configuração. Antes de uma alegação forte para submissão, é necessário avaliar a sensibilidade à cadeia otimizada e aprofundar o papel da representação/persistência da identidade retomável. A estrutura de seis seções continua adequada; o parecer não é uma previsão de aceite.
