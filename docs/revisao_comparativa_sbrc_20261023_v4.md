# Comparação do PDF atualizado com o artigo aprovado de 2025

Revisão de 23/10/2026. Foram examinados o texto integral e as páginas renderizadas dos dois PDFs fornecidos nesta mensagem. Os PDFs não foram modificados e nenhum experimento foi executado. Esta revisão substitui o parecer sobre a versão `(3)` para decisões relativas ao PDF `(4)`; o registro anterior permanece preservado.

## Parecer

**A organização editorial agora corresponde à referência: seis seções, seis figuras, 14 painéis de resultados em grupos de 4 + 4 + 6, uma tabela, quatro trabalhos discutidos individualmente e três contribuições.** Os resultados ampliados foram integrados aos resumos, à introdução, aos trabalhos relacionados, à abordagem, à avaliação e à conclusão.

A diferença relevante passou a ser a natureza da contribuição. O artigo de 2025 apresenta uma política adaptativa de agendamento. O atual caracteriza experimentalmente mecanismos existentes de recuperação e as condições em que seu custo muda. A estrutura pode ser compartilhada pelos dois tipos de artigo, mas a caracterização precisa sustentar sua própria contribuição.

O próximo passo científico mais útil é avaliar cenários representativos sem transmitir a CA raiz. A condição atual é declarada corretamente e permite comparar os tratamentos medidos, mas a sensibilidade da magnitude dos percentuais à cadeia permanece aberta. Na edição, o objetivo é compactar repetições e melhorar transições; a arquitetura das seis seções já está definida.

## Documentos efetivamente comparados

| Documento | Páginas | SHA-256 |
|---|---:|---|
| `sbrc_27_iot_corrigido (4).pdf` | 17 | `7e7aeab5cdc58cdfe1680bcfda7961b304e79dabfc6a2832d0999500bd00a688` |
| `5904_Versao_final_de_artigo_aceito (2).pdf` | 14 | `02136fd741e43030f502a6757d93ae7ffcc3183a5ad6eba8e384065c678ed31a` |

O segundo é a referência aprovada de 2025, conforme informado pelo autor. A versão atual mudou em relação ao PDF `(3)` de 16 páginas; ela foi relida, sem transportar automaticamente as pendências antigas. A chamada de 2027 não foi verificada nesta comparação. As 14 páginas do aprovado não são evidência de um limite normativo aplicável ao novo artigo.

## Correspondência estrutural

| Elemento | Referência de 2025 | Atual para 2027 | Situação |
|---|---:|---:|---|
| Seções principais | 6 | 6 | Coincide |
| Desafios enumerados nos resumos | 3 | 3 | Coincide |
| Contribuições na introdução | 3 | 3 | Coincide |
| Subseções principais na fundamentação | 2 | 2 | Coincide |
| Subsubseções na fundamentação | 2 | 2 | Coincide |
| Diagramas conceituais | 2 | 2 | Coincide |
| Subseções da abordagem | 2 | 2 | Coincide |
| Diagrama da abordagem | 1 | 1 | Coincide |
| Subseções da avaliação | 3 | 3 | Coincide |
| Figuras numeradas de resultados | 3 | 3 | Coincide |
| Painéis de resultados | 4 + 4 + 6 | 4 + 4 + 6 | Coincide |
| Figuras numeradas no artigo | 6 | 6 | Coincide |
| Blocos de legenda de figura | 6 | 6 | Continuações removidas |
| Tabelas | 1 | 1 | Coincide; ambas na fundamentação |
| Trabalhos discutidos individualmente | 4 | 4 | Coincide |
| Referências bibliográficas | 10 | 10 | Coincide |
| Parágrafos da conclusão | 2 | 2 | Coincide |
| Equações numeradas | 8 | 5 | Diferença justificada pelo conteúdo |
| Páginas | 14 | 17 | Atual mais longo |

Não há razão científica para acrescentar três equações apenas para igualar o inventário. A quantidade de imagens, referências ou equações, isoladamente, não é critério de contribuição ou evidência de aceite.

## O que efetivamente melhorou

- **Resumos e introdução, pp. 1–2:** apresentam o mesmo recorte experimental. A introdução já começa na primeira página, e os três itens de contribuição estão juntos na segunda, sem a palavra isolada que ocorria na versão anterior.
- **Trabalhos relacionados, pp. 6–7:** Catoni é descrito como antecedente de retomada com tickets sem cache por sessão. O diferencial atual passa por preservar/perder a chave, variar falhas, usar autenticação pós-quântica e acompanhar a leitura até a confirmação. A comparação antiga entre a política deles e o cache em RAM do piloto foi retirada.
- **Abordagem, pp. 8–10:** distingue restauração de chave/contador no protótipo da negociação TLS nativa. As duas políticas TLS usam a mesma construção de tickets e diferem na preservação da chave. Os três perfis e o comparador completo estão descritos.
- **Avaliação, pp. 10–15:** o estudo principal contém 1.620 execuções e 180 adicionais, com dez blocos. O piloto de 60 condições deixou de fornecer os resultados centrais. Os percentuais, as contagens e os denominadores de duplicação estão atualizados.
- **Figuras 4–6, pp. 11, 12 e 14:** todos os painéis estão agrupados, sem legendas de continuação. A Figura 6 reúne custo, frequência de falhas, tempo, contagens de handshakes, tamanho da identidade de retomada e duplicação. Os gráficos permanecem coloridos e legíveis.
- **Conclusão, pp. 15–16:** usa os resultados novos e deixou de tratar TLS clássico e comparação de preservação como atividades futuras.
- **Coerência das afirmações:** os 67,87% e 14,24% se referem ao cenário especificado de bytes IPv4 por leitura confirmada; a cadeia com CA raiz é explicitada. O texto distingue economia de bytes de evidência temporal sob perda.

## Comparação da escrita

A sequência de exposição é a mesma: contexto, desafios, abordagem, três contribuições; conceitos e figuras; um parágrafo por antecedente; modelagem e funcionamento; três blocos de avaliação; resultados e trabalhos futuros em dois parágrafos.

A introdução já tem extensão próxima da referência. Uma contagem aproximada da extração de PDF, com recomposição de palavras quebradas, encontrou cerca de 474 palavras no atual e 462 no aprovado, incluindo citações. Esses valores são indicativos, não limites de submissão.

O aprovado tem parágrafos mais centrados em ações e mecanismos: estimar, ajustar, agendar e reutilizar. O atual dedica mais espaço a implementação, fronteiras de medição e condições das garantias. Parte desse detalhamento é necessária, pois evita confundir segurança criptográfica, retomada e efeitos da aplicação. A compactação deve concentrar cada condição no lugar adequado, mantendo as qualificações que mudam a interpretação do resultado.

Para aproximar o ritmo de leitura, cada bloco da avaliação pode seguir: condição experimental, observação na figura, explicação do mecanismo e consequência. Não se deve reproduzir expressões como “melhorias significativas” por semelhança estilística quando a análise temporal atual não as sustenta.

## Pendências prioritárias

### 1. Verificar a sensibilidade à cadeia de certificados

O texto informa que os três perfis enviam folha e CA raiz. Isso mantém a condição experimental explícita, mas a raiz pós-quântica amplia o custo do estabelecimento completo. Não se pode prever, a partir desses dados, quanto permanecerá da economia de 67,87% após removê-la, nem assumir que a penalidade de 14,24% terá exatamente a mesma magnitude.

Repetir cenários representativos sem enviar a raiz permitiria separar a dependência da política de estado da sensibilidade à cadeia. A comparação entre tratamentos da configuração atual continua interpretável; a variante adicional fortaleceria a generalização dos percentuais. Esse controle é mais informativo neste momento do que adicionar figuras ou repetir toda a revisão textual.

### 2. Concentrar a contribuição na relação quantitativa observada

O resultado útil é o custo da recuperação condicionado à política de estado e à frequência das falhas, com distinção entre troca de chaves e autenticação. A oferta recusada acrescenta bytes e pode ocorrer junto com autenticação completa na mesma conexão. O tamanho público da identidade de retomada e as contagens de completos/retomados ajudam a explicar o resultado.

Preservar tickets, estabelecer chaves novas e reconhecer leituras repetidas têm antecedentes conhecidos. O número de execuções e a reprodução desses mecanismos não estabelecem, por si sós, um protocolo novo. A redação atual usa adequadamente “avaliamos”; a apresentação oral e a defesa da contribuição devem manter essa delimitação.

### 3. Harmonizar as fronteiras das medidas

Na p. 4, a Equação 1 é apresentada como custo “até a confirmação”; na p. 10, a abordagem repete essa expressão. Na p. 13, a metodologia esclarece que os bytes abrangem a sequência incluindo encerramentos, enquanto o tempo termina na última confirmação.

As duas medidas podem ter fronteiras distintas, desde que os nomes as expressem. Recomenda-se usar consistentemente “bytes da sequência completa de recuperação por leitura confirmada” e “tempo até a última confirmação”. Essa é uma correção de descrição; os dados não precisam ser alterados para eliminar a ambiguidade.

### 4. Compactar e ajustar a paginação do artigo completo

O atual tem três páginas a mais. O ganho de espaço deve vir da edição e da montagem, preservando fonte, margens e legibilidade.

| Local no atual | Observação | Ajuste sugerido |
|---|---|---|
| p. 1 | Introdução começa, mas tem apenas duas linhas antes da virada | Encurtar resumos e rever a quebra dos autores dentro do template |
| p. 2 | Há separações como `proced-imento` e `Recon-hecer` | Conferir o idioma ativo do corpo no Babel; a causa precisa ser verificada no preâmbulo do Overleaf |
| pp. 6–7 | Título e início de relacionados ficam na p. 6; o primeiro parágrafo termina na p. 7 | Compactar a transição para manter o parágrafo de abertura junto |
| p. 9 | Figura 3 é clara, porém alta | Reorganizar espaçamentos e blocos do diagrama, conservando o tamanho do texto |
| pp. 13–15 | O parágrafo sobre a Figura 6(b) começa em uma linha na p. 13, é interrompido pela figura na p. 14 e continua na p. 15 | Evitar o início desse parágrafo antes da página da figura |
| pp. 15–16 | O primeiro parágrafo da conclusão termina com duas linhas na p. 16 | Compactar o fechamento da avaliação e a síntese, verificando novamente o fluxo |
| p. 17 | Referências ocupam apenas parte da última página | A redução do texto e dos espaços anteriores pode absorver parte desse excedente |

Não identifiquei página totalmente vazia, gráficos cortados, sobreposição relevante ou marcadores `??` no PDF atual. Isso é inspeção do PDF, não auditoria de seu log de compilação. A Figura 6 aparece antes da conclusão, uma montagem mais coerente que a referência de 2025, cuja Figura 6 interrompe o segundo parágrafo da conclusão entre as pp. 12–13.

As quebras observadas na p. 2 são inadequadas à divisão silábica em português. Antes de acrescentar exceções manuais de hifenização, deve-se conferir a seleção de idioma após abstract/resumo. O PDF permite identificar o sintoma, mas não confirmar a configuração que o causou sem o arquivo principal atual.

## Encaminhamento

Manter as seis seções e o inventário visual atual. Priorizar o controle da cadeia sem raiz; em seguida, atualizar a interpretação conforme os resultados e fazer uma edição concentrada de extensão, fronteiras das métricas e transições de página. A mesma estrutura do aprovado já foi alcançada. A aceitação depende da contribuição e da evidência submetidas, não pode ser inferida da semelhança estrutural.
