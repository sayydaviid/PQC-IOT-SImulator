# Persistência, proteção do checkpoint e identificação do dispositivo

As verificações deste documento utilizam os componentes do checkpoint `338b021` sem modificar seus fontes. Os novos executores estão em `scripts/verify_context_persistence.py` e `scripts/verify_context_identity_tickets.py`. Seus resultados ficam separados dos experimentos de custo no Mininet-WiFi.

## Fronteiras da gravação

Foram realizadas 100 verificações: cinco pontos de interrupção, dois tipos de encerramento e dez repetições. O processo executa o mesmo `ReadingLedger` utilizado pelo gateway. A instrumentação apenas intercepta a execução das instruções para parar na fronteira escolhida. O registro em `readings` conserva o identificador e o resumo necessários à deduplicação; `effects` representa o efeito da aplicação. Nesse modelo, a própria linha de leitura fornece o registro da deduplicação; não há uma terceira tabela independente. As duas tabelas guardam dispositivo, identificador e resumo criptográfico, sem o payload integral. Portanto, o teste demonstra consistência desses registros e do efeito representado no banco; não demonstra armazenamento persistente do conteúdo completo da telemetria.

| Ponto de interrupção | Leituras após reiniciar | Efeitos após reiniciar | Resultado do reenvio |
|---|---:|---:|---|
| Após inserir a leitura, antes de concluir a transação | 0 | 0 | Registra uma leitura nova |
| Após inserir o efeito, antes de concluir a transação | 0 | 0 | Registra uma leitura nova |
| Imediatamente antes de concluir a transação | 0 | 0 | Registra uma leitura nova |
| Imediatamente após concluir a transação | 1 | 1 | Reconhece repetição sem novo efeito |
| Antes do envio da confirmação | 1 | 1 | Reconhece repetição sem novo efeito |

Os resultados foram iguais no encerramento normal, que fecha a conexão SQLite, e no término abrupto por SIGKILL, que não executa a finalização do processo. Em todas as verificações, o banco passou em `PRAGMA integrity_check`; leitura e efeito apresentaram o mesmo dispositivo, identificador e resumo. Após o reenvio, houve exatamente uma leitura e um efeito. O mesmo identificador com conteúdo diferente foi rejeitado.

O teste exercita o processo que executa a persistência do gateway, sem transmitir TLS nesses 100 casos. A fronteira anterior à confirmação é posterior ao retorno da operação de gravação e anterior à operação de envio. Os testes de rede verificam separadamente o encerramento da conexão após a gravação e antes da confirmação. Não foram realizados cortes físicos de energia, falhas do kernel ou desligamento do dispositivo de armazenamento. Não generalizar esses resultados para atuadores externos.

Dados: `results/raw/context_persistence_20261106_v1/results.json`.

## Fronteiras no gateway TLS

O controle complementar concluiu 30 verificações com o gateway TLS real: cinco fronteiras de gravação, três perfis criptográficos e dois tipos de término. Foram realizadas 60 conexões TLS autenticadas, antes e após os reinícios. O componente SQLite não foi alterado; a instrumentação apenas interrompe sua execução no ponto escolhido.

O SIGTERM foi tratado para encerrar a aplicação e fechar o banco; o SIGKILL terminou o processo sem executar essa finalização. Nas duas condições, as três fronteiras anteriores à conclusão da transação deixaram zero registros e zero efeitos. As fronteiras posteriores à conclusão e anteriores à confirmação deixaram um registro e um efeito. A primeira conexão não recebeu confirmação em nenhum caso. Após reiniciar o gateway e reenviar a mesma leitura em outra conexão autenticada, todos os casos terminaram com exatamente um registro e um efeito. O indicador de repetição correspondeu à presença ou ausência da gravação anterior, e o identificador do dispositivo foi `iot_1`.

O banco passou em sua verificação de integridade após cada interrupção. Os dois handshakes de cada caso utilizaram compartilhamentos públicos distintos. Essas verificações complementam as 100 do componente de persistência; não são novas amostras de custo de rede. O sistema operacional e o armazenamento continuaram ligados. Não representam corte físico de energia nem execução de atuadores.

Dados: `results/raw/context_persistence_tls_20261106_v1/results.json`.

## Nonce do checkpoint

O método `SealedStore.write` gera um nonce novo com `os.urandom(12)` e cifra o conteúdo com AES-GCM. Os 12 bytes do nonce são colocados no início do arquivo cifrado. A chave de proteção vem do provisionamento e permanece fora da restauração do armazenamento do cliente. A associação autenticada inclui a versão do formato e o nome do arquivo, distinguindo `state` de `journal`.

O nonce não é calculado a partir de um contador guardado no checkpoint. Ao iniciar outro processo ou restaurar um arquivo antigo, a próxima gravação solicita novos bytes ao gerador criptográfico do sistema operacional. Restaurar o arquivo não restaura o estado desse gerador no host avaliado. Isso não cobre a restauração de toda uma máquina virtual, o retorno do estado do gerador de aleatoriedade, ou um dispositivo físico sem entropia adequada.

Foram realizadas 1.000 gravações em 20 processos, com a mesma chave. Uma cópia antiga do arquivo foi restaurada antes de dez desses processos. Não foram observados nonces repetidos. Uma alteração no arquivo foi rejeitada; uma cópia antiga autêntica foi aceita, como previsto pelo modelo. Um controle negativo forçou a fonte de nonce a repetir a saída e produziu reutilização, demonstrando que o armazenamento não detecta esse problema por si só.

A ausência de colisões no teste não demonstra unicidade determinística. Assumindo nonces independentes e uniformes de 96 bits, a probabilidade de ao menos uma colisão em `q` cifragens sob a mesma chave é limitada por `q(q-1)/2^97`. O texto do artigo deve declarar essa condição e a dependência da fonte de aleatoriedade, sem afirmar impossibilidade de repetição. Os testes se referem a reinícios de processos e restauração de arquivos, não a reinícios físicos de sensores.

## Identificação do dispositivo

O endpoint TLS anterior não aceita um identificador `d` escolhido livremente no registro da leitura: a mensagem contém apenas `reading_id` e `payload`, e o gateway usa o valor `iot_1`. Esse mesmo nome é exigido no certificado do cliente por `SSL_set1_host`, antes da conclusão da autenticação mútua. Portanto, o valor usado na deduplicação está associado à identidade autorizada pela configuração, dentro de um cenário com um único dispositivo.

A instrumentação adicional conferiu o nome no certificado autenticado, inclusive no certificado recuperado do estado da sessão retomada. Esse cuidado é necessário porque `SSL_get0_peername` pode não devolver um nome na retomada; sua ausência não significa que o certificado recuperado não esteja disponível. O diagnóstico compara o certificado com o nome esperado, sem obter a identidade do payload.

Um cliente com certificado de `iot_2`, assinado por uma CA válida e usando os mesmos parâmetros criptográficos, foi rejeitado. Nenhuma leitura ou efeito foi inserido no banco. As conexões válidas, completas e retomadas, usaram `iot_1` na deduplicação.

Esse vínculo é uma configuração de identidade única. A implementação ainda não representa um cadastro de múltiplos sensores que derive automaticamente `d` de certificados arbitrários. Uma ampliação deverá definir o identificador autorizado de cada certificado e conservar essa associação na retomada.

Dados: `results/raw/context_tickets_identity_20261106_v2/results.json`.
