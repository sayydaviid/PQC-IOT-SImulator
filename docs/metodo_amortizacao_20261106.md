# Condições equivalentes na comparação de leituras por conexão

Este detalhamento foi preparado antes das execuções definitivas de amortização. As verificações anteriores em localhost validaram o protocolo, mas não integram as estimativas de custo.

São dez blocos, três perfis, três tratamentos, três limites por conexão (1, 10 e 100) e dois cenários (sem falhas ou recuperação). Cada execução envia as mesmas 100 leituras lógicas de 512 bytes. O cliente utiliza um único processo durante toda a execução, inclusive quando abre várias conexões. Isso mantém a quantidade de inicializações do cliente constante, permitindo distinguir o compartilhamento da conexão da criação de novos processos.

O controlador prepara os payloads e os identificadores antes da medição. O tempo começa antes de iniciar o gateway e termina na última confirmação. O processo cliente carrega as credenciais e reutiliza o contexto de configuração da biblioteca; cada conexão possui seu próprio handshake e suas próprias chaves. A política `full` não oferece uma sessão anterior. As políticas de retomada oferecem apenas a sessão efetivamente salva e associada ao mesmo contexto de confiança.

A aplicação mantém o mesmo formato de leitura e confirmação nos três limites. Um marcador de fim, com corpo `{"end":true}` e enquadramento de quatro bytes, termina cada grupo antes do fechamento TLS. Esse tráfego está incluído nos custos e ocorre em todos os comparadores. Os 512 bytes se referem ao conteúdo da leitura; os totais incluem também identificadores, Base64, JSON, enquadramento, confirmações, tickets, TLS, TCP/IPv4 e encerramentos observados na captura. Não interpretar a diferença total como tamanho exclusivo do handshake.

A sessão é salva assim que um ticket utilizável fica disponível após uma confirmação. O cliente não regrava o mesmo estado serializado a cada leitura: a gravação ocorre quando há uma sessão utilizável diferente da anterior. Se uma conexão interrompida não fornece outra sessão utilizável, a cópia anterior continua disponível. Essa política é a mesma para todos os limites por conexão.

No cenário de recuperação, o gateway reinicia antes da leitura de índice 50, e a primeira confirmação dessa leitura é suprimida depois da gravação. O controlador encerra o grupo anterior para realizar o reinício. A conexão é restabelecida dentro do mesmo processo cliente; a leitura repetida conserva seu identificador. Leituras já confirmadas não são enviadas de novo. Há até três tentativas por leitura, com os erros e entregas não concluídas preservados nos registros.

Na política com contexto perdido, cada processo gateway cria outra chave de proteção de tickets. Na política com contexto preservado, carrega a mesma chave. O banco é mantido e a deduplicação permanece ativa. A raiz é confiável nos dois lados, mas não é transmitida. Os demais parâmetros de TLS e rede são os mesmos da comparação das cadeias.

O executor é `scripts/run_context_amortization.py`, e o cliente é `experiments/context_costs/amortization_client.py`. A primeira versão das verificações funcionais usou processos separados por conexão e foi substituída antes das medições para manter constante o número de processos. Os diretórios `context_amortization_smoke_*` não são amostras dos resultados definitivos.
