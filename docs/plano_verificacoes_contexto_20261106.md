# Verificações adicionais do custo de recuperação

Data de início: 6 de novembro de 2026. Branch de trabalho: `investigacao/custos-contexto-2026-11-06`. Checkpoint anterior: `338b021`. Os fontes e resultados anteriores permanecem preservados. Os novos executores e o módulo nativo ficam separados em `experiments/context_costs/`.

## Perguntas

1. Quanto a retirada da CA raiz da cadeia transmitida altera o custo absoluto e a economia da retomada, mantendo a mesma confiança?
2. Qual informação incorporada ao ticket explica as diferenças de tamanho entre os perfis?
3. Como o compartilhamento de uma conexão entre leituras altera o custo por leitura e a recuperação?
4. Leitura, identificação da repetição e efeito permanecem consistentes nas fronteiras da gravação após encerramento normal ou término abrupto do processo?
5. De onde vem o nonce do checkpoint e como o dispositivo é associado à identidade autenticada?

## Comparação das cadeias

Dez blocos completos; três perfis (clássico, híbrido, pós-quântico); três tratamentos (completo, retomada com chave perdida, retomada com chave preservada); duas cadeias transmitidas por ambos os participantes (folha e raiz, ou apenas folha). A raiz permanece carregada como confiável nas duas condições. As mesmas credenciais de cada perfil são usadas nos seis comparadores de um bloco.

Os cenários principais são frequências de reinício/supressão de confirmação de 0%/0%, 25%/25% e 100%/100%. São nove leituras por execução, a primeira sem falha e oito elegíveis. Agendas e conteúdo são mantidos entre os comparadores do bloco; ordem aleatória. Deduplicação ativa. Perda de pacotes configurada em 0%, atraso de 2 ms por direção, fila de 1.000 pacotes, um sensor no Mininet-WiFi. Total previsto: 540 execuções. A grade anterior completa de frequências independentes não será apresentada como repetida aqui.

O payload reproduz o anterior: `synthetic block=000 reading=000`, com os números correspondentes ao bloco e à leitura. Tamanhos efetivos são registrados. O custo inclui todas as tentativas e encerramentos IPv4 observados no servidor; o tempo termina na última confirmação. Capturas exigem zero descartes e cobertura dos prefixos cuja entrega foi comprovada. Ofertas recusadas e falhas de entrega são mantidas. Não aproveitar isoladamente células favoráveis de blocos incompletos.

## Diagnóstico dos tickets e da identidade

A instrumentação nativa registra apenas comprimentos: certificados efetivamente transmitidos em cada direção, mensagens NewSessionTicket e identidades PSK, ClientHello, sessão serializada do cliente e estado serializado pelo servidor antes da proteção do ticket. Também registra o tamanho do certificado do participante remoto incorporado à sessão e da eventual informação adicional da aplicação. Não exporta segredos, conteúdo de tickets, sessões serializadas ou chaves privadas.

O diagnóstico em localhost compara a construção automática anterior com cadeias explícitas, registra certificados e tamanhos de chaves públicas e verifica uma retomada efetiva. Um controle adicional mantém o perfil do servidor pós-quântico e permite ECDSA/ML-DSA, trocando apenas o algoritmo da chave pública do certificado do cliente, assinado pela mesma classe de CA. Esse controle serve para explicar a serialização, não para acrescentar um quarto perfil às estimativas de custo.

O certificado de um dispositivo diferente, assinado por uma CA válida, deve ser rejeitado. A aplicação anterior não recebe `d` livremente do payload: usa `iot_1`, exigido também na verificação do certificado do cliente. A nova instrumentação confere a identidade do certificado recuperado na retomada. Essa configuração contém apenas um dispositivo autorizado; não demonstra um cadastro geral para vários sensores.

## Amortização

Dez blocos; três perfis; três tratamentos; limites de 1, 10 e 100 leituras por conexão; sem falhas e com recuperação. Cada comparador envia exatamente 100 leituras lógicas de 512 bytes, com mesmo conteúdo e identificadores no bloco. Nenhum aquecimento adicional é removido do custo: a primeira conexão completa está incluída.

No cenário de recuperação, o gateway reinicia antes da leitura de índice 50 e a primeira confirmação dessa leitura é suprimida após a gravação. Uma conexão que atenderia essa leitura é encerrada antes do reinício. O reenvio mantém o identificador. A fronteira de falha pode dividir um grupo de leituras. Até três tentativas por leitura. São transmitidos apenas os certificados folha, mantendo a raiz confiável e a autenticação mútua. Demais parâmetros de rede iguais aos da comparação das cadeias. Total previsto: 540 execuções e 54.000 leituras lógicas.

A sessão é salva quando fica disponível após uma confirmação, inclusive dentro de uma conexão com várias leituras. Essa condição é explicitada porque melhora a disponibilidade do ticket antes de uma interrupção. O contraste principal de amortização usa todos os tratamentos sob essa mesma política.

## Persistência e checkpoint

Instrumentação externa do mesmo `ReadingLedger`, sem reescrever as operações da transação: após inserir a leitura; após inserir o efeito; antes de concluir a transação; depois de concluí-la; e antes da confirmação. Dez repetições de encerramento normal e SIGKILL em cada fronteira: 100 verificações. Após reiniciar, verificar integridade SQLite, igualdade entre registro e efeito, reconhecimento do reenvio e rejeição de conflito. Não chamar término de processo de queda física de energia.

O `SealedStore` utiliza `os.urandom(12)` em cada cifragem, com chave fora do rollback. Verificar gravações em 20 processos, restaurando um arquivo antigo antes de dez deles. Registrar colisões observadas sem interpretar sua ausência como prova de impossibilidade. Testar adulteração, aceitação de uma cópia antiga autêntica e um controle negativo com fonte de nonce repetida. Descrever a dependência do CSPRNG do host e o limite probabilístico por chave.

## Análise

Custos absolutos e economias calculadas dentro do mesmo bloco, sempre frente ao completo do mesmo perfil e condição. Comparar também diretamente folha e raiz contra apenas folha. Não calcular economia como razão de medianas quando o estimador é a mediana das reduções de cada bloco. Intervalos bootstrap de 95%, com 10.000 reamostragens e semente fixa, exploratórios por configuração. As leituras não constituem repetições independentes. Diagnósticos de tamanho e verificações de persistência são apresentados separadamente dos experimentos de rede.
