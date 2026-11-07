# Conferência com o artigo aceito

A revisão usa o artigo aceito como referência de extensão e organização. O PDF entregue tem 14 páginas, seis seções numeradas, seis figuras, 14 subpainéis na avaliação, uma tabela e três itens de contribuição na introdução. As Figuras 4 e 5 conservam os controles do protótipo. A Figura 6 foi substituída por seis painéis dos novos experimentos de cadeias, identidade nos tickets e leituras por conexão. Os gráficos continuam coloridos.

## Caracteres do corpo

| Seção | Aceito | PDF recebido antes desta correção | Versão compacta |
|---|---:|---:|---:|
| Introdução | 3.065 | 3.065 | 3.065 |
| Fundamentação Teórica | 8.700 | 9.694 | 8.700 |
| Trabalhos Relacionados | 3.199 | 3.930 | 3.199 |
| Estratégia / Proposta | 5.932 | 9.821 | 5.932 |
| Avaliação e Resultados | 3.917 | 18.186 | 3.917 |
| Conclusão e Trabalhos Futuros | 1.238 | 2.103 | 1.238 |

O critério é o mesmo nos três PDFs: texto corrido, itens e citações visíveis, com espaços normalizados. Títulos, subtítulos, fórmulas destacadas, células das tabelas, rótulos de subfiguras e texto interno dos gráficos são elementos distintos e ficam fora da contagem do corpo. Símbolos matemáticos em linhas de prosa seguem a representação recuperável do PDF. A contagem não corresponde ao número de bytes dos fontes LaTeX.

As quebras de linha da paginação são normalizadas, e hífens de final de linha são removidos pelo mesmo procedimento. A contagem depende dessa convenção e da extração do PDF; não garante a mesma quantidade de linhas quando outro compilador ou fonte é utilizado. O arquivo `contagem.json` preserva o texto efetivamente contado, e `conferir_contagem.py` permite conferir o procedimento.

## Caracteres das legendas

| Elemento | Aceito | Antes | Versão compacta |
|---|---:|---:|---:|
| Tabela 1 | 75 | 129 | 75 |
| Figura 1 | 51 | 133 | 51 |
| Figura 2 | 57 | 141 | 57 |
| Figura 3 | 49 | 106 | 49 |
| Figura 4 | 182 | 172 | 182 |
| Figura 5 | 180 | 195 | 180 |
| Figura 6 | 153 | 477 | 153 |

Os prefixos automáticos, como “Figura 6.”, ficam fora dessas contagens. As duas tabelas extensas adicionadas anteriormente à avaliação foram retiradas do corpo; os custos completos permanecem na documentação de reprodução.

## Alterações editoriais

- A descrição extensa de CPU, memória, contêiner, versões e parâmetros da rede fica na documentação de reprodução, junto das matrizes completas e verificações complementares.
- As legendas identificam a figura; as condições experimentais relevantes são explicadas no texto. A legenda da nova Figura 6 mantém 153 caracteres.
- A avaliação destaca perda de contexto, cadeia transmitida, representação da identidade no ticket e leituras por conexão.
- Os gráficos identificam os algoritmos nos eixos, títulos ou legendas, sem depender das palavras “Clássico”, “Híbrido” e “PQC”. Os dados da nova Figura 6 são rastreáveis aos CSV e ao diagnóstico incluídos na pasta de reprodução.
- O PDF foi compilado, conferido visualmente e revisado quanto a referências indefinidas e caixas que ultrapassam a margem. Não foram repetidos experimentos de rede.

O abstract e o resumo foram atualizados para destacar os resultados sem transmissão da raiz, mantendo 1.070 e 1.102 caracteres, respectivamente, no mesmo critério de extração do PDF. A avaliação distingue os novos testes dos controles e da matriz anterior de deduplicação. As outras seções preservam a redação compacta já alinhada a esse foco. Os detalhes dos testes ficam em `reproducao/`.

## Posicionamento corrigido das figuras

As Figuras 4 e 5 ficam juntas na página 11, depois da discussão do protótipo e antes da subseção 5.2. A Figura 6 fica na página 13, antes do título da conclusão. Ela não interrompe os parágrafos da conclusão. As Figuras 1, 2 e 3 permanecem nas páginas 5, 6 e 9.

Foram mantidas barreiras de flutuação antes da subseção de TLS e ao final da avaliação. A escala dos painéis foi ajustada para manter 14 páginas. As páginas afetadas foram renderizadas e conferidas visualmente; a compilação não apresenta referências indefinidas nem conteúdo ultrapassando as margens.

## Conteúdo da nova Figura 6

| Painel | Resultado apresentado | Fonte |
|---|---|---|
| (a) | Bytes por leitura sem transmitir a raiz, três configurações e três tratamentos, ambas as falhas em 100% | Comparação de cadeias: 540 execuções |
| (b) | Economia dentro da repetição, com e sem raiz, incluindo acréscimo com contexto perdido | Mesma comparação de cadeias |
| (c) | Certificado, estado serializado e ticket ao mudar a chave do cliente, com exatamente o mesmo servidor e CA | Diagnóstico controlado da implementação |
| (d) | Bytes por leitura com limites de 1, 10 e 100, sem falhas | Amortização: 540 execuções |
| (e) | Economia com reinício antes da 51ª leitura e perda de sua primeira confirmação | Mesma comparação de amortização |
| (f) | Diferença de tempo entre contexto preservado e completo, sem falhas e na recuperação | Mesma comparação de amortização |

Os painéis de rede usam deduplicação ativa e perda de pacotes configurada em 0%. Em (a, b), as leituras têm conteúdo de 31 bytes; em (d--f), são 100 leituras de 512 bytes por execução. O primeiro handshake completo entra na amortização. Em (b, e, f), os intervalos são bootstrap exploratórios de 95%, calculados dentro de cada configuração, com o bloco como unidade de repetição. Em (c), ambos os certificados do cliente continuam assinados pela mesma CA ML-DSA; não se trata da configuração inteiramente clássica.

O gerador e seus dados estão em `reproducao/gerar_figura6.py` e `reproducao/dados_figura6/`. A procedência dos arquivos finais está em `figuras/contexto/artigo/proveniencia.json`. Não foram repetidos experimentos para produzir os gráficos: foram usados os resultados concluídos e auditados.
