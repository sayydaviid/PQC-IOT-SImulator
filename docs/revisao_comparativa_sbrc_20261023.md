# Comparação estrutural e editorial: referência de 2025 e artigo para 2027

Revisão de 23/10/2026, usando os dois PDFs fornecidos nesta mensagem. O segundo documento é tratado como o artigo aprovado na trilha principal de 2025, conforme informado pelo autor. As páginas citadas são posições nos arquivos. Foram examinados o texto e as páginas renderizadas de ambos os documentos; os PDFs não foram modificados e nenhum experimento novo foi executado nesta revisão.

## Parecer direto

**A estrutura já segue a referência. Não faltam gráficos: ambos têm 14 painéis de resultados.** Para igualar o inventário visual, o artigo de 2027 precisa reorganizar os painéis em seis figuras numeradas e reduzir duas tabelas a uma. A pendência principal é científica/editorial: o PDF ainda apresenta o piloto de 60 condições, enquanto a campanha ampliada de 1.800 ensaios já foi concluída no repositório.

Manter a fórmula de escrita é viável: contexto, desafios, abordagem, três contribuições, fundamentação, antecedentes, modelagem, funcionamento, três blocos de avaliação e conclusão em dois parágrafos. Essa organização não dispensa explicitar a contribuição experimental. O aprovado apresenta uma estratégia adaptativa própria; o atual avalia mecanismos conhecidos sob falhas. A evidência e a pergunta adicional precisam sustentar essa diferença.

## Documentos conferidos

| Documento | Páginas | SHA-256 |
|---|---:|---|
| Atual, `sbrc_27_iot_corrigido (3).pdf` | 16 | `74216891ad03e4312c797fb099d81a546aefbf78eb4a7ebe9fc0a8b4a455f63c` |
| Aprovado, `5904_Versao_final_de_artigo_aceito (2).pdf` | 14 | `02136fd741e43030f502a6757d93ae7ffcc3183a5ad6eba8e384065c678ed31a` |

O arquivo aprovado tem o mesmo hash da referência examinada anteriormente, embora o nome termine agora em `(2)`. O PDF atual tem hash diferente do anterior: foi relido nesta revisão, sem presumir que o parecer antigo se aplicava integralmente.

## Inventário: o que já coincide e o que difere

| Item | Aprovado de 2025 | Atual para 2027 | Ajuste para seguir a referência |
|---|---:|---:|---|
| Seções principais numeradas | 6 | 6 | Manter |
| Desafios enumerados no abstract/resumo | 3 | 3 | Manter, atualizando o recorte experimental |
| Contribuições na introdução | 3 | 3 | Atualizar o conteúdo, mantendo três itens |
| Subseções principais da fundamentação | 2 | 2 | Manter |
| Subsubseções da fundamentação | 2 | 2 | Manter |
| Diagramas na fundamentação | 2 | 2 | Manter Figuras 1 e 2 |
| Subseções da abordagem | 2 | 2 | Manter modelagem e funcionamento |
| Diagrama da abordagem | 1 | 1 | Manter Figura 3 |
| Subseções de avaliação | 3 | 3 | Manter |
| Figuras numeradas de resultados | 3 | 4 | Reunir as atuais Figuras 6 e 7 |
| Painéis de resultados | 14 | 14 | Manter o total; atualizar o conteúdo TLS |
| Figuras numeradas no artigo inteiro | 6 | 7 | Passar a seis |
| Blocos de legenda de figura, incluindo continuações | 6 | 10 | Reduzir repetições quando os painéis couberem juntos |
| Tabelas | 1 | 2 | Priorizar uma tabela de configuração experimental |
| Equações numeradas | 8 | 5 | Diferença real; acrescentar somente formalizações necessárias |
| Trabalhos discutidos individualmente em relacionados | 4 | 5 | É possível voltar a quatro parágrafos principais sem perder citações |
| Entradas bibliográficas | 10 | 10 | Quantidade já coincide |
| Parágrafos da conclusão | 2 | 2 | Manter resultados e futuros separados |
| Disponibilidade de artefatos, agradecimentos e referências | Presentes | Presentes | Estrutura já coincide |

Os números distinguem **figura numerada**, **painel de gráfico** e **bloco de legenda**. Uma continuação com o mesmo número não é outra figura científica. O inventário verificável, com páginas e legendas, está em [inventario_artigos_sbrc_20261023.json](inventario_artigos_sbrc_20261023.json).

## Correspondência exata das imagens e resultados

| Papel | Referência de 2025 | Artigo atual | Organização a manter |
|---|---|---|---|
| Primeiro conceito da fundamentação | Figura 1: purificação simétrica | Figura 1: reserva de contadores | Uma figura conceitual |
| Segundo conceito da fundamentação | Figura 2: pumping | Figura 2: reconhecimento de leitura repetida | Uma figura conceitual |
| Funcionamento da abordagem | Figura 3: estratégia híbrida | Figura 3: recuperação da sessão e confirmação | Um fluxo da abordagem |
| Primeiro bloco de avaliação | Figura 4: quatro painéis | Figura 4: quatro painéis em dois blocos | Figura 4, painéis (a)–(d) |
| Segundo bloco de avaliação | Figura 5: quatro painéis | Figura 5: quatro painéis em dois blocos | Figura 5, painéis (a)–(d) |
| Terceiro bloco de avaliação | Figura 6: seis painéis | Figura 6: quatro; Figura 7: dois | Figura 6, painéis (a)–(f) |

Para o PDF existente, bastaria renumerar retransmissões e duplicações como Figura 6(e) e 6(f), atualizando referências e legendas. Para a versão científica atualizada, **não recomendo apenas conservar os seis gráficos antigos**: a campanha ampliada deve ocupar o bloco principal de TLS.

Uma distribuição de seis painéis que aproveita os novos resultados é:

1. **6(a):** bytes por leitura confirmada, comparando completo, contexto perdido e preservado nos três perfis.
2. **6(b):** economia versus frequência de reinícios, distinguindo políticas e frequências de confirmação perdida; curvas somente nos pontos medidos.
3. **6(c):** tempo de recuperação sob perdas de 0%, 1% e 5%, com a fronteira temporal e os intervalos explicitados.
4. **6(d):** contagens de completos e retomados que explicam o cenário de falhas frequentes.
5. **6(e):** tamanhos públicos da identidade de retomada nos perfis clássico, intermediário e PQC.
6. **6(f):** efeitos duplicados com e sem supressão na matriz principal, com denominadores comparáveis.

Isso mantém os 14 painéis do artigo inteiro e a organização 4+4+6, enquanto concentra a última figura na pergunta nova. Os dados antigos de handshake e retransmissões podem permanecer no artefato ou ser citados brevemente se necessários; não é preciso acrescentar uma Figura 7 para preservá-los. Os dois PDFs de gráficos já exportados em `docs/figuras/continuidade` são insumos; sua montagem atual contém oito eixos no total e não constitui, por si só, a Figura 6 de seis painéis proposta aqui.

Manter as cores dos resultados, conforme a preferência atual do autor. Os diagramas conceituais podem continuar em preto e branco. Os gráficos da referência também são coloridos; não há razão estrutural para convertê-los.

## O que falta em cada seção

### Abstract e resumo

A fórmula está preservada: contexto, três desafios, abordagem, avaliação e resultados. O aprovado tem aproximadamente 151 palavras no abstract e 170 no resumo; o atual, 166 e 194, pela extração automática. São medidas indicativas, sujeitas à hifenização do PDF, não contagens normativas da chamada.

É necessário substituir o destaque do piloto pela campanha escolhida como principal. Os números 60 condições, cinco blocos, 30 duplicações e 87,96% de redução no handshake pertencem ao piloto, não à campanha ampliada. Não trocar apenas o número de ensaios e manter o restante da descrição antiga. Compactar os dois textos ajudará a aproximar a primeira página do modelo aprovado.

### 1. Introdução

Os dois artigos já seguem cinco parágrafos de desenvolvimento, três contribuições e o parágrafo de organização. A introdução atual ocupa aproximadamente 614 palavras, contra 475 na referência: cerca de **29% a mais**, sem necessidade de mudar sua estrutura.

O ajuste é encurtar definições que voltam na fundamentação, preservar os três desafios e conduzir mais diretamente à pergunta experimental. As três contribuições podem continuar organizadas como:

- caracterização dos estados necessários à recuperação;
- avaliação controlada de políticas e falhas com perfis clássico, intermediário e PQC;
- quantificação das condições de economia/penalidade e da independência entre retomada e deduplicação.

A redação precisa dizer que o protótipo observa restauração de chaves/contadores, enquanto TLS serializado negocia outra conexão. Essa distinção já existe e deve ser preservada.

### 2. Fundamentação Teórica

A estrutura coincide: duas subseções principais, duas subsubseções e duas figuras. Não falta uma figura. A tabela de modalidades de sessão pode virar um parágrafo curto, permitindo manter somente a tabela experimental, se o objetivo é igualar também a quantidade de tabelas.

As cinco equações atuais devem permanecer apenas se ajudam a definir as propriedades ou medidas usadas. A referência tem oito, mas isso não torna necessárias três fórmulas decorativas. Definições de custo por leitura confirmada e economia pareada podem ser acrescentadas na metodologia se forem usadas na avaliação. A contagem observada de handshakes, se formalizada, deve ser apresentada como explicação das condições testadas, sem transformá-la em teorema de segurança.

### 3. Trabalhos Relacionados

A forma de parágrafo por antecedente está próxima da referência. O atual discute cinco trabalhos individualmente; o aprovado, quatro. Para aproximar o comprimento e manter quatro parágrafos principais, KEMTLS-PDK pode ser citado no contexto/fundamentação e os parágrafos de relacionados podem concentrar-se em Avoine, Catoni, Hebrok e Lee. As dez referências não precisam diminuir.

O parágrafo de Catoni, na página 7, ainda contrapõe a política sem cache deles ao cache em RAM do piloto. A nova campanha usa tickets sem cache por sessão nas duas políticas, variando a persistência da chave. Esse diferencial precisa ser atualizado. A preservação de tickets já é antecedente conhecido; o recorte adicional está em frequências de falha, autenticação mútua PQC, custo até confirmação e efeitos no banco. A leitura integral já está registrada em [comparacao_catoni_completa.md](comparacao_catoni_completa.md).

### 4. Estratégia de Recuperação de Sessões Pós-Quânticas

Modelagem, funcionamento e Figura 3 já correspondem à fórmula da referência. Não é necessário acrescentar pseudocódigo ou outra figura apenas para imitar um tipo de contribuição diferente.

A descrição da página 8 precisa deixar de apresentar cache em RAM como a única política TLS avaliada. Deve descrever os três tratamentos e os três perfis da campanha principal, separando-os dos controles do protótipo. A Figura 3 pode conservar seu papel de visão geral; detalhes de nomes da biblioteca e opções do banco devem aparecer uma vez no lugar apropriado, evitando repetição em fundamentação, proposta e avaliação.

Empregar “avaliamos” e “implementamos” onde o trabalho integra mecanismos conhecidos. A forma assertiva do aprovado pode ser reproduzida com afirmações sustentadas, sem trocar avaliação experimental por alegação de protocolo inédito.

### 5. Avaliação e Resultados

Manter três subseções, na mesma progressão lógica de controles e resultado principal:

1. **5.1:** riscos da restauração de estado e controles de chave/nonce, Figura 4 com quatro painéis.
2. **5.2:** interrupções e caminhos de recuperação no protótipo, Figura 5 com quatro painéis.
3. **5.3:** recuperação TLS sob políticas de estado e frequências variáveis, Figura 6 com seis painéis.

Os experimentos das duas primeiras subseções não devem ser renomeados ou ter seus parâmetros alterados para parecerem parte da campanha TLS. O ajuste prioritário é **substituir a apresentação principal do piloto em 5.3**, em vez de anexar uma quarta campanha longa ao texto. O piloto pode permanecer identificado no artefato como etapa anterior.

| Item de 5.3 | Está no PDF | Já está no repositório, pendente de integração |
|---|---|---|
| Escopo TLS | 60 condições, cinco blocos | 1.620 ensaios principais + 180 de robustez, dez blocos por configuração |
| Perfis | Híbrido com ML-DSA | Clássico/ECDSA, híbrido/ECDSA e híbrido/ML-DSA |
| Estado de retomada | Cache em RAM perdido no reinício | Mesma construção de tickets com chave volátil ou preservada |
| Falhas lógicas | Uma sequência fixa | Frequências de 0%, 25% e 100% nas leituras elegíveis |
| Leituras/tentativas | Cinco leituras e seis processos por ensaio | Nove leituras; tentativas variam com as falhas, com orçamento limitado |
| Efeito principal | Economia condicionada à sequência antiga | Economia muda de sinal conforme política e falhas |
| Estatística | Razões entre medianas; cinco blocos | Contrastes pareados por bloco e intervalos exploratórios |
| Duplicações no controle | 30 no piloto | 2.700 na matriz principal ampliada |

A campanha nova já demonstra, no PQC com falhas em todas as leituras elegíveis, economia pareada de 67,87% com preservação e aumento de 14,24% com chave volátil. Esses números são de bytes IPv4 por leitura confirmada e não substituem diretamente os 87,96% do handshake isolado. São populações, configurações e fronteiras diferentes. A síntese e os arquivos verificáveis estão em [resultado_continuidade.md](resultado_continuidade.md).

Há uma pendência experimental delimitada: o controle posterior confirmou envio da CA raiz na cadeia do servidor nos três perfis. A comparação sem esse certificado ainda precisa ser medida antes de generalizar a magnitude da economia a uma cadeia otimizada. Pode-se descrever a condição atual com precisão, mas não apresentá-la como uma configuração já otimizada.

O texto da avaliação deve aproximar-se do encadeamento da referência: cenário/comparadores, observação na figura, explicação do mecanismo e conclusão local. Consolidar limites comuns no modelo e na metodologia; manter as ressalvas que mudam a interpretação de um resultado junto desse resultado. A economia de bytes sob perda não sustenta superioridade temporal geral, pois os intervalos de tempo relevantes incluem zero.

### 6. Conclusão e Trabalhos Futuros

Os dois parágrafos já coincidem com o modelo: resultados no primeiro, próximos passos no segundo. O conteúdo está desatualizado em relação ao repositório. Na página 15, comparar políticas de preservação e adicionar TLS clássico ainda aparecem como futuros, embora a campanha de 21/10 já tenha realizado essas comparações.

O primeiro parágrafo deve sintetizar o resultado principal escolhido, distinguindo economia condicional e supressão de efeitos repetidos. O segundo deve retirar as etapas concluídas e priorizar a sensibilidade à cadeia de certificados, além das extensões que realmente permanecem abertas: sensor físico, concorrência, fila persistente do cliente e efeitos externos. Não reaproveitar automaticamente “melhorias significativas” da referência quando a análise atual não sustenta essa afirmação.

## Paginação e acabamento visual

- **Primeira página:** no aprovado a introdução já começa na página 1; no atual ela só começa na página 2. Compactar resumos e rever a disposição dos autores pode recuperar espaço, respeitando o template.
- **Páginas 2–3:** a lista de contribuições quebra no meio do segundo item; a página 3 começa somente com “confirmação.”. Os três itens devem ficar juntos ou ao menos não deixar essa palavra isolada.
- **Página 6:** o título de relacionados e o primeiro parágrafo ficam separados da maior parte da discussão na página 7. A compactação pode melhorar a transição; não é necessário forçar uma nova página.
- **Página 11:** a Figura 4 aparece em dois blocos, cada um com uma legenda, apesar de ambos caberem na mesma página. Unificar os quatro painéis reduz repetição.
- **Página 12:** há uma linha de texto (“fronteiras distintas das medidas TLS.”) entre as duas partes da Figura 5. Reunir o parágrafo e a figura evita esse corte visual.
- **Páginas 13–14:** a Figura 6 é continuada e a Figura 7 completa os mesmos resultados TLS. Usar numeração única 6(a)–(f). Não forçar seis painéis em um bloco alto sem recompilar: conferir legibilidade e espaços após a montagem.
- **Página 15:** a conclusão atual mantém seus dois parágrafos juntos, aspecto que convém preservar.
- O aprovado também tem uma flutuação editorial que não convém reproduzir: sua Figura 6 aparece na página 13, depois do início da conclusão na página 12. Repetir a estrutura não exige repetir essa colocação.
- Não identifiquei página totalmente vazia, sobreposição relevante ou referência `??` no PDF atual examinado. Isso não equivale à auditoria de seu log de compilação.

O atual tem duas páginas a mais. A revisão deve buscar aproximadamente o mesmo espaço da referência por edição e montagem, **substituindo** os resultados antigos pelos novos quando necessário. Não há base nesta comparação para afirmar que 14 páginas é o limite da chamada de 2027; essa regra precisa ser verificada na chamada aplicável. Não reduzir fonte ou margens para simular a referência.

## Ordem de ajuste recomendada

1. **Fixar a avaliação principal:** campanha ampliada como conteúdo de 5.3; resolver o controle de cadeia ou declarar a condição da configuração medida.
2. **Sincronizar o argumento:** resumos, introdução, relacionados, modelagem e conclusão devem descrever o mesmo experimento e a mesma contribuição.
3. **Fechar o inventário visual:** seis figuras, 14 painéis e uma tabela; três contribuições e três blocos de avaliação.
4. **Compactar a escrita:** introdução, resumos, repetições de implementação e legendas continuadas; preservar condições que delimitam os resultados.
5. **Recompilar o artigo inteiro:** conferir os itens órfãos, a Figura 5, o agrupamento da Figura 6, a conclusão e as referências. Só então avaliar a contagem final de páginas e as exigências da chamada.

**Não falta uma seção, uma imagem conceitual ou uma quantidade maior de gráficos. Faltam integração dos resultados já produzidos, coerência entre as seções e uma montagem visual mais compacta.** A apresentação pode seguir a mesma fórmula do aprovado; a contribuição empírica precisa ser defendida pelos resultados e por suas condições.
