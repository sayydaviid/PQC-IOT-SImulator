# Execução validada do notebook

Resultados de `Pesquisa_Retomada_Sessoes.ipynb`, executado integralmente no contêiner de pesquisa com Mininet-WiFi, sem fallback e com dez repetições por condição.

- 20 células de código executadas, sem erros.
- 2.890 condições de rede e 75.150 leituras confirmadas.
- Segurança, persistência, auditorias e geração dos gráficos concluídas.
- Duração: 10.917,59 segundos, aproximadamente três horas.

O notebook na raiz contém as saídas e os gráficos dessa execução. `validation.json` registra sua verificação e seu SHA-256. `sha256.json` registra os hashes dos arquivos de dados e relatórios deste diretório.

As pastas `continuity_analysis` e `context_analysis` contêm tabelas e auditorias. `article_comparison` contém a comparação com o artigo: os achados foram reproduzidos, mas os números medidos não são todos idênticos aos de referência. Os manifestos preservam os parâmetros e os hashes do código utilizado. Os resultados dos testes de segurança também estão incluídos.

Este conjunto publicado contém tabelas e relatórios. Capturas PCAP, logs e observações brutas por conexão permanecem no diretório local `results/retomada/20261111T040027423734Z/`. Os caminhos absolutos e hashes desses arquivos nos relatórios documentam a execução original; a auditoria completa das capturas exige esses arquivos brutos. A procedência dos gráficos registra o hash do notebook de entrada, anterior ao salvamento das saídas finais.

Para gerar uma nova execução, siga a configuração do contêiner descrita no README da raiz e execute todas as células do notebook. Os novos resultados serão gravados em outro diretório sob `results/retomada/`.
