# Fontes históricos

Os arquivos `run_campaign_v3.py` e `run_campaign_v4.py` conservam exatamente os bytes dos executores anteriores. São usados para verificar a procedência de blocos interrompidos e não devem ser importados nem executados na versão organizada.

Os arquivos `.py.txt` preservam rotinas pontuais que consolidaram os resultados históricos após interrupções da infraestrutura. Suas funções de execução, análise e verificação são chamadas por classes e células separadas na versão atual.

Para a implementação histórica completa, use a branch `investigacao/custos-contexto-2026-11-06`, commit `b90b89b`. A execução atual utiliza as classes de `research/experiments/` e o notebook `Pesquisa_Retomada_Sessoes.ipynb`.
