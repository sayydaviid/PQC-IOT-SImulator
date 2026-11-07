# Verificação da organização

Branch: `organizacao-do-codigo`. Base histórica: `b90b89b`, em `investigacao/custos-contexto-2026-11-06`.

A organização foi conferida com o código montado nas imagens de pesquisa disponíveis no host. Não foi repetida a construção completa das dependências a partir de um host vazio. O Compose e os novos caminhos de construção foram verificados.

| Verificação | Resultado |
|---|---|
| Verificações funcionais e de análise | 129 passaram |
| Imports das classes de pesquisa no ambiente TLS | Passaram |
| Novo notebook, executado do início ao fim em modo de consulta | Passou |
| Comparação das tabelas de referência com elas mesmas | Diferença de custo igual a zero |
| Exportação das seis figuras a partir das tabelas de referência | Passou; arquivos de origem preservados |
| Bloco TLS/Mininet-WiFi com três perfis, três tratamentos, três frequências e duas cadeias | 54 casos passaram, com captura |
| Protótipo de falhas de estado | 240 execuções; critérios atendidos |
| Protótipo de interrupções | 330 casos; verificações atendidas |
| Figuras do protótipo geradas com os dados novos | Oito painéis gerados |
| Leituras por conexão, verificação local TLS | Limites 1, 10 e 100, com recuperação e contexto preservado no perfil com ML-DSA-44; três casos passaram |
| Persistência, verificação reduzida | Dez fronteiras/modos e 1.000 gravações de checkpoint passaram |
| Persistência com gateway TLS | Trinta casos, sessenta conexões, passaram |
| Diagnóstico de tickets e identidade | Doze casos passaram, incluindo rejeição de outra identidade |
| Verificações de segurança da continuidade TLS | Doze verificações passaram |
| Sintaxe Python, shell e configuração Compose | Passaram |
| Tutorial original e três fontes C nativos | Iguais byte por byte aos arquivos da base histórica |
| Artigo, tabelas históricas e dados brutos locais | Preservados |

A execução local de verificações Python emitiu o aviso já existente de diferença entre a liboqs do host (0.15.0) e seus bindings Python (0.14.0). As verificações de rede e TLS usaram o contêiner de pesquisa. O Dockerfile fixa versões compatíveis para a construção do ambiente.

Essas execuções validam a organização e seus caminhos de execução. Não representam uma nova medição completa de todos os experimentos com dez blocos e não substituem os resultados de referência. O notebook permite executar esse desenho completo em um diretório novo. A verificação local de amortização não é apresentada como medição de custo no Mininet-WiFi.

Os dados brutos das verificações temporárias foram produzidos em diretórios temporários dos contêineres. Não foram misturados aos dados históricos nem utilizados para atualizar as tabelas do artigo. Os dados brutos históricos locais continuam fora do Git; os resultados de referência versionados e o procedimento de reprodução estão disponíveis no repositório.
