# Por que o ticket pós-quântico ocupa 4.240 bytes

O diagnóstico adicional registrou os comprimentos observados em sessões completas e retomadas, usando OpenSSL 3.5.9 e a mesma construção de tickets do experimento anterior. O transporte foi localhost; esses resultados explicam a implementação e não são novas amostras de custo de rede.

## Informação incorporada ao ticket

O servidor serializa o estado `SSL_SESSION`, que inclui o certificado folha do cliente autenticado. A instrumentação consultou esse certificado pela API nativa e mediu o estado serializado no callback de proteção do ticket. Não houve informação adicional da aplicação no ticket: o comprimento retornado por `SSL_SESSION_get0_ticket_appdata` foi zero.

A codificação ASN.1 do OpenSSL inclui um campo `peer` do tipo X.509. O estado também contém informações do protocolo, da cifra, da sessão e da verificação. A implementação experimental protege esse estado usando AES-256-CBC e HMAC-SHA-256, com nome de chave de 16 bytes, IV de 16 bytes e autenticação de 32 bytes. O ticket não é uma assinatura ML-DSA acrescentada ao ClientHello.

Para um estado serializado de `n` bytes, o comprimento esperado nesta construção é `64 + 16 * (floor(n / 16) + 1)`: 64 bytes de nome, IV e autenticação, mais o estado com preenchimento CBC. Os tamanhos registrados permitem verificar essa relação sem decifrar ou publicar tickets.

Referências técnicas da implementação: [serialização de sessão do OpenSSL 3.5.9](https://github.com/openssl/openssl/blob/openssl-3.5.9/ssl/ssl_asn1.c) e [API de informação adicional de tickets](https://docs.openssl.org/3.5/man3/SSL_CTX_set_session_ticket_cb/). São fontes do artefato, não novas referências bibliográficas do artigo.

## Comprimentos observados

Os valores abaixo são do diagnóstico com apenas o certificado folha transmitido. A CA permaneceu confiável em ambos os participantes. Certificados ECDSA e campos de sessão podem variar poucos bytes entre credenciais e conexões.

| Perfil | Certificado do cliente | Estado serializado pelo servidor | Ticket emitido | Sessão salva pelo cliente | ClientHello inicial / retomado |
|---|---:|---:|---:|---:|---:|
| Clássico | 423 bytes | 575 bytes | 640 bytes | 1.227 bytes | 194 / 897 bytes |
| Híbrido | 421 bytes | 574 bytes | 640 bytes | 1.228 bytes | 1.370 / 2.073 bytes |
| Pós-quântico | 4.018 bytes | 4.170 bytes | 4.240 bytes | 8.423 bytes | 1.370 / 5.673 bytes |

A lista de algoritmos de assinatura deste diagnóstico aceita ECDSA e ML-DSA para permitir o controle com certificado misto. Por isso, seu ClientHello não deve ser confundido com aquele da configuração que oferece apenas o algoritmo do perfil. Os experimentos de custo mantêm a lista específica de cada perfil e registram seus próprios comprimentos.

No conjunto das configurações deste diagnóstico, tickets ECDSA ficaram em 640 ou 656 bytes. Pequenas diferenças de tamanho do estado podem atravessar uma fronteira de bloco do CBC e produzir uma diferença de 16 bytes no ticket. O grupo negociado e a codificação do certificado também afetam o estado. Não atribuir cada byte exclusivamente a uma operação criptográfica.

O primeiro handshake de cada sequência emitiu um ticket, recebido pelo cliente. As duas retomadas seguintes não emitiram outro ticket nessa configuração de callback. Essa contagem é medida por mensagem NewSessionTicket, e não inferida do número configurado em `SSL_CTX_set_num_tickets`. Os registros distinguem emissão pelo servidor, recebimento pelo cliente e disponibilidade de uma sessão utilizável. Uma mensagem emitida não garante que uma conexão interrompida tenha deixado uma sessão salva no cliente.

A cadeia completa automática anterior e a cadeia explícita com raiz enviaram dois certificados por participante; a condição sem raiz enviou um. Retirar a raiz da transmissão não retira o certificado folha do cliente do estado da sessão.

## Controle com o mesmo servidor e a mesma CA

Um controle adicional conservou exatamente o certificado e a chave do servidor pós-quântico, a mesma CA e o mesmo grupo híbrido, alterando apenas a chave do certificado do cliente. Ambos os certificados do cliente continuaram assinados pela mesma CA ML-DSA. As conexões foram autenticadas e retomadas.

| Chave pública do cliente | Certificado do cliente | Estado serializado pelo servidor | Ticket |
|---|---:|---:|---:|
| ECDSA P-256 | 2.775 bytes | 2.927 bytes | 2.992 bytes |
| ML-DSA-44 | 4.018 bytes | 4.170 bytes | 4.240 bytes |

A chave pública codificada passou de 1.334 para 91 bytes. A troca reduziu em 1.243 bytes o certificado do cliente e o estado serializado. O ticket diminuiu 1.248 bytes, considerando o preenchimento CBC. Isso associa o aumento ao certificado do cliente incorporado à sessão. O certificado ECDSA desse controle ainda é grande porque sua assinatura foi produzida pela CA ML-DSA; não equivale ao certificado do perfil inteiramente clássico.

A explicação experimental é, portanto, a representação do participante autenticado dentro do ticket. Quando o contexto é perdido, o cliente oferece esse ticket maior e ainda realiza autenticação completa. A interpretação dos custos precisa considerar também o tamanho das cadeias transmitidas e quantas leituras compartilham cada conexão. As comparações realizadas dentro da mesma repetição no Mininet-WiFi estão consolidadas em `resultado_contexto_20261106.md`.

Dados completos de comprimentos e contagens: `diagnostico_tickets_20261106.json`. Dados brutos: `results/raw/context_tickets_identity_20261106_v2/results.json`. Nenhuma chave privada, segredo de sessão, conteúdo de ticket ou sessão serializada foi exportado.

## Material acrescentado ao ClientHello

Nesta configuração, a extensão `pre_shared_key` acrescenta 63 bytes além do próprio ticket: cabeçalho da extensão, comprimentos das listas, comprimento da identidade, idade ofuscada e binder de 48 bytes, correspondente ao SHA-384 da cifra TLS selecionada. Assim, um ticket de 640 bytes acrescenta 703 bytes ao ClientHello; um ticket de 4.240 bytes acrescenta 4.303 bytes. Esse material é enviado antes de o servidor decidir se aceita a retomada. Quando a chave de proteção foi perdida, ele acompanha a negociação que terá de realizar autenticação completa.

O custo percentual dessa oferta recusada também depende do denominador. Retirar a raiz reduz o handshake completo, mas não elimina o certificado folha do cliente incorporado ao ticket. A comparação das cadeias deve, portanto, mostrar valores absolutos e percentuais por perfil. Um acréscimo absoluto maior no PQC não implica necessariamente o maior acréscimo percentual entre os perfis.
