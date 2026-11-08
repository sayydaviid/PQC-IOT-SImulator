# Verificação do notebook com os resultados do artigo

A execução completa reproduziu as conclusões e as contagens dos experimentos. As medições de rede não repetiram todos os números com o mesmo arredondamento. A reanálise dos dados históricos recalculou exatamente as 11 tabelas verificadas.

## O que foi executado novamente

| Parte | Execuções | Resultado |
|---|---:|---|
| Protótipo: falhas de estado | 240 | Campos não temporais exatamente iguais aos históricos |
| Protótipo: interrupções | 330 | Todos os campos comparados exatamente iguais aos históricos |
| TLS: matriz principal | 1.620 | 14.580 leituras confirmadas; zero duplicações com deduplicação e 2.700 sem supressão |
| TLS: perdas de 1% e 5% | 180 | 1.620 leituras confirmadas |
| Cadeias com e sem raiz | 540 | 4.860 leituras confirmadas; zero duplicações |
| Leituras por conexão | 540 | 54.000 leituras confirmadas; zero duplicações |

As etapas TLS usaram dez blocos, totalizando 2.880 execuções e 75.060 leituras confirmadas. A matriz principal e os casos sob perdas produziram 21.960 tentativas, todas confrontadas com ClientHello públicos nas capturas. Os testes adicionais de identidade, tickets, checkpoint e persistência também passaram.

## Comparação dos números

Os valores abaixo vêm da nova coleta, sem substituir as referências. Os percentuais são medianas das comparações dentro da mesma repetição.

| Resultado em X25519MLKEM768 com ML-DSA-44 | Artigo | Nova execução |
|---|---:|---:|
| Economia com contexto preservado, sem transmitir raiz, ambas as falhas em 100% | 57,79% | 57,74% |
| Acréscimo com contexto perdido, mesma condição | 19,70% | 19,75% |
| Economia com contexto preservado, transmitindo raiz, ambas as falhas em 100% | 67,89% | 67,89% |
| Economia com preservação, dez leituras por conexão, sem falhas | 36,79% | 36,83% |
| Economia com preservação, cem leituras por conexão, com recuperação | 15,11% | 15,08% |

Sem transmitir a raiz, com ambas as falhas em 100%, os custos novos por leitura confirmada foram 41.463,67 bytes no completo, 49.659,44 com contexto perdido e 17.525,00 com preservação. As referências eram 41.463,67, 49.645,00 e 17.504,78 bytes. A ordenação completo/contexto perdido/preservado foi reproduzida nas três configurações, com e sem transmissão da raiz.

A nova coleta também conservou a redução do custo por leitura ao compartilhar a conexão e os números de handshakes na recuperação. Cem leituras sem falhas requereram um handshake completo em todos os tratamentos; a pequena diferença medida de tráfego entre eles não demonstra uma economia de handshake nessa condição. No cenário de recuperação, foram três handshakes completos sem preservação, contra um completo e dois retomados com preservação.

No controle que mantém servidor e CA iguais e altera a credencial do cliente, os certificados mediram 2.775 e 4.018 bytes, os estados de sessão 2.928 e 4.171 bytes, e os tickets 3.008 e 4.240 bytes, respectivamente. Estes são os novos comprimentos observados; não se forçaram os tamanhos históricos de 2.927/4.170 e 2.992/4.240 bytes.

Não foi fixada uma tolerância depois da coleta para declarar igualdade numérica. As diferenças completas, incluindo tempos, estão em [comparacao_completa.csv](comparacao_completa.csv); os resultados selecionados estão em [COMPARACAO.md](COMPARACAO.md). As referências do artigo foram preservadas.

## Recalcular exatamente os resultados históricos

A classe `ArticleNumericalReanalysis`, chamada no começo de `Pesquisa_Retomada_Sessoes.ipynb`, usa as observações por execução em `../dados_numericos_artigo.json.gz`. Não lê as tabelas prontas para produzir os resultados: recalcula custos, medianas, comparações e intervalos com as classes de análise e depois compara as tabelas geradas com as referências.

As 11 tabelas ficaram exatamente iguais, incluindo custos de cadeias, amortização, continuidade, preservação, migração e interação das falhas. O resultado está em [reanalise_exata.json](reanalise_exata.json). O arquivo de entrada acompanha o repositório; não depende das pastas locais `results/` e `output/`. Contém somente os campos necessários aos cálculos, com procedência nos arquivos históricos; não inclui credenciais nem PCAP. Essa reanálise não é uma nova coleta ou uma nova auditoria das capturas históricas.

## Correção necessária durante a análise

A execução original terminou as medições e os testes adicionais, mas falhou ao analisar duas capturas em que cliente e servidor usaram o mesmo número de porta. O leitor confundia a direção do tráfego. A análise foi corrigida para identificar o cliente pelo endereço IP do SYN inicial, com testes das duas capturas e uma regressão específica.

A falha original foi conservada em [execucao_notebook_original.json](execucao_notebook_original.json). Apenas o processamento posterior foi executado em outro kernel, concluindo análises, figuras e comparação: [execucao_pos_processamento.json](execucao_pos_processamento.json). Os hashes dos dez arquivos de resultados foram conferidos antes e depois desse processamento; nenhum caso foi descartado ou medido novamente para contornar a falha. A correção está registrada em [../correcao_analise_portas_20261107.json](../correcao_analise_portas_20261107.json).

As medições e capturas completas permanecem localmente em `results/reproducao_artigo_20261107_v2/`, e os notebooks executados em `output/reproducao_artigo_20261107_v2/`. Esses diretórios são ignorados pelo Git. Esta pasta versiona os relatórios, tabelas, figuras e registros de execução; os dados numéricos históricos necessários à reanálise são distribuídos separadamente do conjunto de PCAP.
