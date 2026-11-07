# Fase 2: interrupções de retomada e confirmação perdida

Estado: **PASS** nos critérios de segurança e recuperação registrados. Foram executados **330 casos** (10 repetições × 11 cenários × 3 políticas), com ML-KEM/ML-DSA reais e arquivos de estado cifrados. É uma injeção lógica de falhas; não mede perda de pacotes, tempo de ESP32 ou energia.

O critério de recuperar a leitura refere-se a um único evento de falha, seguido de tentativa sem novas falhas. Não garante disponibilidade diante de interrupção contínua. As políticas da fase 1 e seus fontes criptográficos foram mantidos.

| Ponto de falha | Bytes: completo | Bytes: retomada ML-KEM | Economia ML-KEM | Fallbacks completos ML-KEM | Duplicações na aplicação ML-KEM |
|---|---:|---:|---:|---:|---:|
| `no_fault` | 9263 | 3136 | 66.14% | 0 | 0 |
| `after_client_hello` | 9428 | 3441 | 63.50% | 0 | 0 |
| `after_server_hello` | 14018 | 5007 | 64.28% | 0 | 0 |
| `after_client_finished` | 18443 | 6189 | 66.44% | 0 | 0 |
| `after_gateway_commit` | 18526 | 6272 | 66.14% | 0 | 0 |
| `after_key_confirmation` | 18526 | 6272 | 66.14% | 0 | 0 |
| `after_checkpoint` | 18526 | 6272 | 66.14% | 0 | 0 |
| `after_record_encryption` | 18526 | 6272 | 66.14% | 0 | 0 |
| `lost_reading_ack` | 18526 | 6272 | 66.14% | 0 | 10 |
| `torn_checkpoint` | 18526 | 12399 | 33.07% | 10 | 0 |
| `gateway_lost_before_start` | 9263 | 9568 | -3.29% | 10 | 0 |

Os bytes acumulam as mensagens enquadradas do primeiro handshake e das novas tentativas, inclusive confirmação perdida e pedido de retomada rejeitado. O bootstrap, os registros de leitura e cabeçalhos IP ficam fora desta comparação. O pedido rejeitado não inclui mensagem de erro na rede, ausente neste transporte de teste.

**“Retomada ML-KEM sempre usa menos bytes” = False.** Quando a raiz desaparece do gateway, a tentativa de retomada falha e acrescenta custo ao estabelecimento completo. A redução de bytes depende de contexto retomável disponível. O controle de ACK perdido demonstra que proteção contra replay criptográfico não fornece deduplicação da aplicação: a mesma leitura pode ser aceita novamente em uma sessão nova, embora o par chave/nonce seja diferente.

Invariantes verificados: {"fresh_key_security_and_eventual_delivery": true, "lost_ack_duplicates_demonstrated": true, "full_fallbacks_match_faults": true}. A duplicação é um controle negativo esperado da aplicação sem ledger de IDs; não indica reutilização de nonce. Toda leitura final é comparada ao conteúdo decifrado pelo gateway. Os checkpoints das políticas de chave nova persistem somente a raiz de retomada.

Dados: `/workspace/results/raw/recovery_transitions_complete_20261014`; SHA-256 de results.json: `31099d56b22d52ba3c9e416fbfb0414eb590a6aad7aa63d6dc49c5d453f695ca`. Manifesto e CSV agregado ficam no mesmo diretório. Segredos e checkpoints experimentais são temporários e apagados; o resultado não exporta chaves ou plaintexts.

Atualização: o baseline TLS nativo, a identificação persistente de leituras e o piloto de rede foram executados posteriormente. Consulte [resultado_tls_piloto.md](resultado_tls_piloto.md). A matriz de interrupções internas acima continua pertencendo ao protótipo. Esta campanha não estabelece novidade frente a protocolos existentes.
