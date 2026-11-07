# Revisão comparativa do manuscrito de retomada e do artigo aprovado

Data: 18/10/2026. Esta é uma revisão editorial e científica dos PDFs fornecidos, com confronto dos números com o relatório local do piloto. Não houve alteração dos experimentos, dos dados ou das seções LaTeX nesta revisão.

## Parecer

A organização do manuscrito atual segue a do artigo aprovado. Manteria as seis seções, as subseções de modelagem e estratégia, as duas figuras conceituais e a figura do fluxo. O principal trabalho pendente é explicar a contribuição científica com mais precisão e aproximar a discussão dos antecedentes mais próximos. O texto atual apresenta uma avaliação experimental de uma integração de mecanismos conhecidos; seus resultados não demonstram, por si, uma nova construção criptográfica ou uma nova política de recuperação superior às existentes.

Eu não consideraria a versão atual pronta para submissão à trilha principal. Isso não implica descartar o tema: há implementação, controles e resultados aproveitáveis. A decisão sobre sua força científica depende de estabelecer o conhecimento acrescentado pela avaliação, em relação à literatura, e de sustentar as conclusões no recorte efetivamente testado.

Documentos examinados integralmente, incluindo inspeção visual:

- Atual: `/home/tavares/Downloads/sbrc_27_iot_corrigido.pdf`, 17 páginas.
- Referência: `/home/tavares/Downloads/5904_Versao_final_de_artigo_aceito (1).pdf`, 14 páginas.
- Conferência interna: `docs/resultado_tls_piloto.md`, `docs/revisao_retomada.md` e fontes das seções.

As páginas indicadas abaixo são as posições no PDF. A comparação usa o artigo aprovado como referência de organização; não é uma auditoria independente das alegações científicas daquele artigo. A diferença de extensão não estabelece descumprimento de limite de páginas: a chamada da edição pretendida ainda precisa ser conferida.

## 1. A mesma fórmula de organização está presente

| Elemento | Artigo aprovado | Manuscrito atual | Parecer |
|---|---|---|---|
| Resumo e introdução | Contexto, três desafios, resposta, avaliação e contribuições | Mesma sequência, com três desafios de recuperação | Preservar |
| Fundamentação | Duas subseções principais, oito equações, uma tabela e duas figuras | Mesma distribuição geral | Preservar a organização; não é necessário preservar a quantidade de equações |
| Relacionados | Quatro antecedentes, diferenças e posicionamento final | Quatro antecedentes, diferenças e posicionamento final | Preservar o formato e atualizar a proximidade temática |
| Proposta | Modelagem, estratégia e Figura 3 | Modelagem, estratégia e Figura 3 | Preservar; explicitar o que a integração acrescenta |
| Avaliação | Três subseções ligadas aos problemas e à estratégia | Três campanhas: estado, interrupções e TLS | Preservar; ligar cada campanha a uma pergunta e conclusão |
| Conclusão | Resultados e trabalhos futuros | Mesma sequência | Preservar; destacar o resultado da recuperação completa |

No artigo aprovado, os verbos que caracterizam a proposta — ajustar rodadas, acrescentar recursos e reaproveitar pares — aparecem na introdução, na estratégia e na análise dos cenários. Essa ligação facilita identificar o que está sendo proposto e avaliado.

No atual, renovar chaves, retomar TLS e reconhecer leituras repetidas são mecanismos já conhecidos. A ligação a reforçar é: quais falhas foram estudadas conjuntamente, quais consequências foram medidas e que decisão de implantação os resultados permitem tomar. Copiar a organização não exige apresentar uma avaliação de mecanismos existentes como se fosse um protocolo novo.

## 2. Achados de maior prioridade

### 2.1. A contribuição precisa ser mais específica — pp. 2, 8–11

As três contribuições da introdução descrevem atividades válidas — modelar, implementar e avaliar —, mas ainda não tornam evidente o conhecimento produzido. Um avaliador pode interpretar os resultados como confirmação do funcionamento esperado de TLS e de transações no banco.

O recorte mais defensável com o que já existe é a avaliação conjunta de três estados diferentes: a sessão conservada pelo cliente, o contexto de retomada do gateway e o histórico de leituras processadas. O texto pode destacar como a perda de cada estado altera a recuperação e seu custo, sem atribuir novidade aos componentes isolados.

Formulação candidata, dependente do fechamento da comparação com a literatura:

> Este trabalho caracteriza experimentalmente a recuperação de telemetria IoT com TLS pós-quântico sob falhas de estado do cliente e do gateway. A avaliação relaciona o estado preservado à disponibilidade da retomada, ao tráfego da recuperação e à repetição de efeitos na aplicação, utilizando controles que separam essas propriedades.

Essa frase descreve o que foi feito; não estabelece ineditismo mundial. Apenas trocar a redação das contribuições não resolve uma eventual sobreposição com trabalhos anteriores.

### 2.2. Falta discutir antecedentes mais próximos — pp. 7–8

As referências atuais são pertinentes, mas cobrem principalmente construção de protocolos, segurança de tickets e consistência distribuída. Falta confrontar a avaliação com trabalhos diretamente sobre retomada TLS em IoT e sobre retomada com troca híbrida pós-quântica.

Na busca dirigida desta revisão, foram identificados:

- **Catoni, Puliafito e Dini (2025), Fast and Secure Service Continuity in the Edge-Cloud Continuum: A Study of TLS 1.3 Resumption and Post-Quantum Key Exchange.** O [registro institucional](https://arpi.unipi.it/handle/11568/1337427) apresenta o artigo e seu resumo. A [versão curta dos próprios autores](https://icities25.unicas.it/papers/22.pdf), lida integralmente, compara estabelecimento completo/retomado com X25519/X25519MLKEM768 e descreve retomada sem cache por sessão, com chave de proteção de tickets compartilhada entre proxies. Esse é um antecedente próximo para o componente TLS e para a escolha do estado mantido pelo servidor. A versão curta não basta para afirmar tudo o que o artigo completo deixa de avaliar.
- **rTLS: Secure and Efficient TLS Session Resumption for the Internet of Things (Sensors, 2021).** O [resumo do artigo publicado](https://www.mdpi.com/1424-8220/21/19/6524) trata retomada, custos e replay em IoT, com foco em 0-RTT. É um candidato para discussão, mantendo clara a diferença para nosso 0-RTT desativado. Nesta revisão foi possível consultar o resumo indexado, não o texto completo; o acesso direto ao editor falhou. Não atribuir ao trabalho ausências que não foram verificadas.

Esses achados não demonstram que nosso recorte já foi resolvido. Demonstram que a seção atual precisa de uma comparação mais próxima antes de sustentar o diferencial da avaliação. Não incorporar preprints automaticamente ao BibTeX, respeitando a preferência por artigos publicados e livros.

Também é necessário ajustar a precisão da citação da introdução: [KEMTLS-PDK](https://kemtls.org/publication/kemtlspdk/kemtlspdk.pdf) é uma variante com autenticação por KEM e chaves previamente distribuídas. Pode contextualizar alternativas pós-quânticas para IoT, mas não deve parecer uma validação direta da configuração nativa com certificados ML-DSA utilizada na bancada.

### 2.3. O recorte pós-quântico precisa ser distinguido das propriedades gerais de recuperação

O piloto efetivamente usa PQC: X25519MLKEM768 e autenticação ML-DSA-44 nos handshakes completos. Entretanto, a deduplicação da aplicação e a dependência do cache do servidor não são propriedades exclusivas de PQC.

O desenho já contém uma comparação útil de dois fatores: completo/retomado e deduplicação ativa/desativada. Não falta um comparador completo, nem uma ablação da deduplicação.

Se a alegação pretendida for quantificar o efeito específico da migração pós-quântica, falta um comparador TLS clássico equivalente, com os mesmos cenários, autenticação e critérios de medição. Esse seria um novo experimento, não uma correção de texto. Sem ele, manter a alegação mais estreita: avaliação de recuperação em uma configuração pós-quântica determinada, sem atribuir todo o benefício à PQC.

### 2.4. A pergunta de pesquisa deve aparecer antes da resposta — p. 13

A frase “A hipótese de economia universal foi, portanto, refutada” aparece nos resultados, mas o manuscrito não estabelece claramente essa hipótese antes. A comparação fica mais forte com uma pergunta condicionada ao estado preservado, evitando usar uma promessa excessiva como alvo de refutação.

Pergunta candidata:

> Como a preservação ou perda do estado do cliente, do contexto TLS do gateway e do histórico de leituras altera o custo de recuperação e a repetição de efeitos da telemetria pós-quântica?

Substituição sugerida para a frase dos resultados:

> A tentativa de retomada seguida de autenticação completa acrescentou 3,29% de bytes nesse cenário do protótipo. Assim, a redução observada com contexto disponível não se estende a todos os caminhos de recuperação.

Não apresentar os 3,29% do protótipo como resultado de TLS. Para uma análise futura de custo esperado em função da frequência de perda do contexto, será preciso especificar essa frequência e validar o modelo; os ensaios atuais não estimam sua ocorrência em uma implantação.

## 3. Resultados: números coerentes, destaque a ajustar

Os números principais do PDF são coerentes com o relatório local consultado. A redação já separa os dois backends, o que deve ser mantido.

| Resultado | Escopo correto | Interpretação |
|---|---|---|
| 9.263 → 3.136 bytes; redução de 66,14% | Protocolo experimental, sem falha | Não é medida de TLS |
| 9.263 → 9.568 bytes; acréscimo de 3,29% | Protocolo experimental, perda da raiz de retomada | Há custo adicional no caminho de fallback |
| 23.859 → 2.873 bytes; redução de 87,96% | Handshake TLS no segundo boot, com contexto disponível, até o retorno de SSL_connect | Exclui tickets posteriores e outras conexões do ensaio |
| 30 → 0 efeitos duplicados | Piloto TLS, controle sem supressão versus banco atualizado com supressão | Resultado na aplicação, não garantia de execução única de atuadores |

O tráfego da sequência inteira é especialmente relevante para um artigo de redes. Com deduplicação ativa, a razão entre as medianas publicadas fornece:

| Perda configurada por direção | Completo: bytes IPv4 por ensaio | Retomada: bytes IPv4 por ensaio | Redução descritiva entre as medianas |
|---|---:|---:|---:|
| 0% | 157.895 | 70.250 | 55,51% |
| 1% | 157.895 | 70.158 | 55,57% |
| 5% | 158.287 | 70.550 | 55,43% |

Cálculo: 100 × (1 − mediana retomada / mediana completo). Trata-se de uma comparação descritiva entre medianas, não da mediana das reduções por bloco, de um intervalo de confiança ou de um estimador pareado.

Recomendo destacar também esse resultado no resumo e na conclusão: ele inclui a sequência executada com fallback e repetição da leitura. Os 87,96% podem continuar como resultado do handshake específico; não devem representar a economia de toda a recuperação.

O tamanho amostral deve continuar transparente: 60 condições não equivalem a 60 repetições independentes de cada configuração. São cinco blocos por combinação; os 360 processos e as 300 entregas lógicas não aumentam automaticamente a independência das observações. Os tempos permanecem resultados descritivos de piloto. Se a alegação passar a ser superioridade geral de latência, será necessário ampliar o desenho e analisar a incerteza com a unidade experimental adequada.

## 4. Validade e reprodutibilidade

### O que está bem delimitado e deve ser preservado

- O protótipo permite observar reutilizações; a instrumentação TLS verifica negociação e compartilhamentos públicos, sem exportar chaves de tráfego ou IVs. Não confundir as evidências.
- Entropia nova, credenciais e chave que protege o checkpoint ficam fora da restauração do armazenamento do cliente. Essa condição é essencial ao modelo.
- A aplicação depende do histórico atualizado no banco. Restaurar todo o banco elimina informações de deduplicação; isso foi tratado como controle separado.
- O controlador mantém o identificador da leitura entre processos. Não foi implementada uma fila persistente de leituras pendentes no sensor.
- Reiniciar o cache em RAM do servidor é uma escolha da implementação; não representa toda política de tickets TLS.
- Criptografia real e rede emulada sustentam esse recorte. Tempos do host, contadores de escrita e uma linha no SQLite não medem boot, energia, desgaste de flash ou efeito físico de um ESP32.

### O que falta apresentar de forma mais fácil de reproduzir

Adicionar uma tabela compacta na abertura da Seção 5, sem criar outra seção principal. Reunir host/CPU/RAM/SO, versão do Mininet-WiFi, banda/MTU, carga de leitura, algoritmos por backend, política e duração do cache, pontos de injeção, número de blocos e fronteiras de medição. Preencher esses campos a partir dos manifestos; não estimar valores ausentes.

O link do artefato no PDF atual aponta para o repositório de PQC-IoT. Melhorar a disponibilidade registrando também uma versão imutável dos fontes, os manifestos correspondentes e os comandos de reprodução. Um link para a versão corrente do repositório não fixa a versão usada nos resultados.

## 5. Redação, figuras e paginação

O PDF atual não apresenta as grandes páginas vazias dos exemplos anteriores. Entretanto, permanecem problemas locais:

1. **Figura 5, continuação, p. 14:** os painéis (c–d), do protótipo, aparecem depois do início da Subseção 5.3, sobre TLS. A numeração de continuação funciona; a associação visual ao experimento fica prejudicada. Reorganizar a posição dos blocos para concluir a figura antes da mudança de assunto. Se necessário, usar uma barreira apenas nessa transição, com inspeção da página resultante; não espalhar barreiras por toda subseção.
2. **Gráficos de resultados, pp. 12–15:** continuam coloridos, embora as Figuras 1–3 estejam em preto e branco. Usar tons de cinza, padrões de preenchimento, tipos de linha e marcadores. Uma conversão simples para cinza pode deixar séries indistinguíveis. Reexportar em PDF vetorial e conferir legendas e eixos no tamanho final.
3. **Figura 3, p. 11:** é legível e segue o estilo solicitado, mas ocupa uma parcela grande da página. Reduzir espaços internos antes de diminuir as letras.
4. **Conclusão, pp. 15–16:** o título e uma frase ficam separados do restante. Reequilibrar os gráficos e o texto para manter o começo da conclusão com conteúdo suficiente.
5. **Vocabulário:** journal, ledger, commit e ACK reaparecem principalmente na avaliação e na conclusão. Preferir “registro dos contadores”, “banco de leituras já processadas”, “gravação concluída” e “confirmação”; manter nomes técnicos de eventos de implementação apenas quando necessários e explicados.
6. **Comentários sobre a produção das figuras:** retirar “sem a notação matemática” e “com linguagem simplificada”. As figuras devem explicar diretamente o procedimento, sem narrar sua adaptação editorial.
7. **Repetição:** teoria, proposta, resultados e conclusão reiteram cache em RAM, ausência de energia/ESP32 e limites para atuadores. Manter condições essenciais junto às alegações, mas centralizar a descrição completa do modelo na Seção 4 e as limitações experimentais na Seção 5.

A fundamentação ocupa aproximadamente cinco páginas e a proposta, cerca de três. As equações de KEM, assinatura e derivação genérica podem ser condensadas se for preciso abrir espaço para a metodologia e a análise. As equações de unicidade, reserva de contadores, deduplicação e custo estão mais diretamente ligadas ao problema. O número de equações não precisa ser igual ao do artigo aprovado.

## 6. Ordem recomendada para a revisão, mantendo a estrutura

| Seção | Ajuste |
|---|---|
| 1. Introdução | Explicitar pergunta de pesquisa, contribuição experimental e por que o estado preservado é relevante ao custo da recuperação |
| 2. Fundamentação | Condensar definições genéricas, manter Figuras 1–2 e separar conceito de configuração da bancada |
| 3. Relacionados | Ler antecedentes próximos, atualizar comparação de escopo e delimitar o diferencial sem alegar ausências não verificadas |
| 4. Estratégia | Manter 4.1/4.2 e Figura 3; evidenciar estado, decisões e condições de cada garantia |
| 5. Avaliação | Inserir tabela de configuração; ligar as três campanhas à pergunta; destacar tráfego por sequência; revisar gráficos e linguagem |
| 6. Conclusão | Responder à pergunta com os limites dos dados e priorizar resultado da recuperação inteira, além do handshake |

Primeiro devem ser resolvidos posicionamento e comparação com a literatura. Depois vêm redação e compactação. Experimentos novos devem responder a uma alegação definida — por exemplo, efeito específico de PQC ou robustez a outra política de estado do servidor —, sem ampliar a matriz apenas para aumentar o número de casos.

Nenhuma conclusão desta revisão exige abandonar a organização do artigo aprovado. O ponto a fortalecer é a relação entre contribuição própria, antecedente próximo e evidência experimental.
