# Custo da perda de contexto, cadeias e leituras por conexão

Os novos experimentos separam o custo dos mecanismos conhecidos das condições em que eles são utilizados. A comparação principal investiga o efeito de retirar a raiz da transmissão, mantendo-a confiável. A comparação de amortização mantém o mesmo trabalho da aplicação e varia quantas leituras compartilham uma conexão.

O perfil clássico usa X25519 e ECDSA P-256; o híbrido usa X25519MLKEM768 e ECDSA P-256; o pós-quântico usa X25519MLKEM768 e ML-DSA-44. Todos mantêm TLS 1.3, autenticação mútua, AES-256-GCM/SHA-384 e 0-RTT desabilitado. Dentro de cada experimento, aplicação, payload e agenda de falhas são mantidos entre os comparadores do bloco.

Foram concluídas 540 execuções na comparação das cadeias, com 4860 leituras lógicas e 4860 confirmações. A comparação de amortização concluiu 540 execuções, 54000 leituras e 54000 confirmações. Efeitos duplicados com deduplicação ativa: 0 e 0, respectivamente.

Cada comparação utiliza dez blocos. As tabelas apresentam medianas dos custos absolutos e medianas das reduções calculadas dentro da mesma repetição, frente ao completo do mesmo perfil e condição. Valores negativos de economia representam aumento de custo. Intervalos de 95% são bootstrap exploratórios por configuração; as leituras não são repetições independentes.

## Cadeias transmitidas

Os dois participantes mantêm a CA raiz no armazenamento de confiança. A transmissão varia entre folha e raiz ou apenas folha, com as mesmas credenciais no bloco e autenticação mútua verificada. O payload tem 31 bytes. Há nove leituras por execução, das quais oito são elegíveis às falhas. As frequências de reinício e de supressão da primeira confirmação são iguais nos três cenários apresentados: 0%, 25% e 100%. Não se trata da repetição de toda a grade anterior de frequências independentes. Nas tabelas, contexto perdido e contexto preservado nomeiam as políticas da chave dos tickets após reinício; quando não há reinício, ambas conservam o contexto durante a execução.

Bytes incluem todas as tentativas e encerramentos IPv4 observados no servidor. A captura não representa todos os quadros Wi-Fi. A perda de pacotes configurada é 0%, com atraso de 2 ms por direção.

| Frequência das duas falhas | Perfil | Cadeia enviada | Completo: bytes/leitura | Contexto perdido: bytes/leitura | Contexto preservado: bytes/leitura |
|---|---|---|---:|---:|---:|
| 0% | Clássico | Folha e raiz | 4.492,39 | 2.682,28 | 2.682,28 |
| 0% | Clássico | Apenas folha | 3.707,89 | 2.595,11 | 2.595,00 |
| 0% | Híbrido | Folha e raiz | 6.756,78 | 5.038,67 | 5.038,67 |
| 0% | Híbrido | Apenas folha | 5.921,11 | 4.945,83 | 4.945,67 |
| 0% | Pós-quântico | Folha e raiz | 30.520,33 | 11.056,33 | 11.062,11 |
| 0% | Pós-quântico | Apenas folha | 22.033,00 | 10.103,67 | 10.112,33 |
| 25% | Clássico | Folha e raiz | 5.422,61 | 3.768,17 | 3.159,78 |
| 25% | Clássico | Apenas folha | 4.452,11 | 3.495,72 | 3.072,61 |
| 25% | Híbrido | Folha e raiz | 8.200,56 | 6.657,61 | 6.042,44 |
| 25% | Híbrido | Apenas folha | 7.167,22 | 6.385,00 | 5.949,50 |
| 25% | Pós-quântico | Folha e raiz | 37.232,56 | 18.806,56 | 12.906,33 |
| 25% | Pós-quântico | Apenas folha | 26.861,00 | 15.968,78 | 11.965,22 |
| 100% | Clássico | Folha e raiz | 8.211,11 | 9.461,94 | 4.592,33 |
| 100% | Clássico | Apenas folha | 6.684,78 | 7.841,72 | 4.505,28 |
| 100% | Híbrido | Folha e raiz | 12.492,67 | 13.923,83 | 9.053,78 |
| 100% | Híbrido | Apenas folha | 10.914,67 | 12.346,89 | 8.960,78 |
| 100% | Pós-quântico | Folha e raiz | 57.372,78 | 65.571,44 | 18.453,44 |
| 100% | Pós-quântico | Apenas folha | 41.342,11 | 49.535,00 | 17.509,44 |

| Frequência das duas falhas | Perfil | Cadeia enviada | Economia: contexto perdido | Economia: contexto preservado |
|---|---|---|---:|---:|
| 0% | Clássico | Folha e raiz | 40,28% [40,27; 40,32] | 40,29% [40,27; 40,36] |
| 0% | Clássico | Apenas folha | 30,01% [30,01; 30,07] | 30,01% [30,01; 30,07] |
| 0% | Híbrido | Folha e raiz | 25,42% [25,41; 25,47] | 25,42% [25,41; 25,49] |
| 0% | Híbrido | Apenas folha | 16,44% [16,43; 16,54] | 16,45% [16,43; 16,55] |
| 0% | Pós-quântico | Folha e raiz | 63,77% [63,75; 63,79] | 63,76% [63,74; 63,80] |
| 0% | Pós-quântico | Apenas folha | 54,16% [54,12; 54,20] | 54,12% [54,09; 54,18] |
| 25% | Clássico | Folha e raiz | 30,48% [25,12; 30,52] | 41,73% [41,71; 41,83] |
| 25% | Clássico | Apenas folha | 21,48% [16,88; 21,49] | 30,98% [30,97; 30,99] |
| 25% | Híbrido | Folha e raiz | 18,79% [15,22; 18,89] | 26,32% [26,22; 26,39] |
| 25% | Híbrido | Apenas folha | 11,04% [8,14; 11,10] | 16,98% [16,91; 17,04] |
| 25% | Pós-quântico | Folha e raiz | 49,49% [41,64; 49,53] | 65,32% [65,30; 65,36] |
| 25% | Pós-quântico | Apenas folha | 40,55% [33,16; 40,57] | 55,46% [55,44; 55,50] |
| 100% | Clássico | Folha e raiz | -15,22% [-15,23; -15,21] | 44,07% [44,06; 44,10] |
| 100% | Clássico | Apenas folha | -17,31% [-17,33; -17,23] | 32,60% [32,59; 32,63] |
| 100% | Híbrido | Folha e raiz | -11,49% [-11,51; -11,41] | 27,50% [27,49; 27,59] |
| 100% | Híbrido | Apenas folha | -13,15% [-13,21; -13,04] | 17,90% [17,84; 18,04] |
| 100% | Pós-quântico | Folha e raiz | -14,29% [-14,31; -14,25] | 67,84% [67,83; 67,85] |
| 100% | Pós-quântico | Apenas folha | -19,82% [-19,85; -19,79] | 57,65% [57,62; 57,67] |

### Tempo de recuperação com ambas as falhas em 100%

O tempo por leitura divide o intervalo até a última confirmação pelo número de leituras da execução. Inclui processos, reinícios previstos e reenvios. Não é uma medição isolada da latência do handshake.

| Perfil | Cadeia enviada | Completo: ms/leitura | Contexto perdido: ms/leitura | Contexto preservado: ms/leitura |
|---|---|---:|---:|---:|
| Clássico | Folha e raiz | 620,26 | 625,61 | 614,60 |
| Clássico | Apenas folha | 619,69 | 620,62 | 613,80 |
| Híbrido | Folha e raiz | 628,43 | 625,23 | 618,85 |
| Híbrido | Apenas folha | 621,98 | 624,74 | 622,75 |
| Pós-quântico | Folha e raiz | 643,45 | 655,16 | 637,03 |
| Pós-quântico | Apenas folha | 637,77 | 647,09 | 632,40 |

## Leituras por conexão

Cada execução transmite 100 leituras lógicas de 512 bytes, usando um único processo cliente. Os limites de 1, 10 ou 100 leituras por conexão se aplicam aos três tratamentos. O primeiro handshake completo é incluído, sem retirar um aquecimento do custo. Apenas os certificados folha são transmitidos; a raiz continua confiável. As conclusões sobre amortização comparam condições dentro deste experimento. Seus custos absolutos não devem ser comparados diretamente aos da matriz de cadeias, que usa outro payload e outro número de processos.

No cenário de recuperação, o gateway reinicia antes da leitura de índice 50, cuja primeira confirmação é suprimida após a gravação. Uma conexão pode ser dividida por essa fronteira. O reenvio conserva o identificador, e as leituras já confirmadas não são repetidas. As condições são detalhadas em `metodo_amortizacao_20261106.md`.

| Cenário | Perfil | Leituras por conexão | Completo: bytes/leitura | Contexto perdido: bytes/leitura | Contexto preservado: bytes/leitura |
|---|---|---:|---:|---:|---:|
| Sem falhas | Clássico | 1 | 4.389,80 | 3.200,09 | 3.201,11 |
| Sem falhas | Clássico | 10 | 1.413,43 | 1.305,83 | 1.305,30 |
| Sem falhas | Clássico | 100 | 1.116,01 | 1.116,01 | 1.116,02 |
| Sem falhas | Híbrido | 1 | 6.706,12 | 5.569,10 | 5.568,07 |
| Sem falhas | Híbrido | 10 | 1.645,30 | 1.541,58 | 1.542,09 |
| Sem falhas | Híbrido | 100 | 1.139,17 | 1.139,66 | 1.139,18 |
| Sem falhas | Pós-quântico | 1 | 22.767,42 | 9.493,15 | 9.493,15 |
| Sem falhas | Pós-quântico | 10 | 3.251,00 | 2.044,91 | 2.044,91 |
| Sem falhas | Pós-quântico | 100 | 1.299,80 | 1.299,80 | 1.299,80 |
| Recuperação | Clássico | 1 | 4.428,07 | 3.266,76 | 3.228,76 |
| Recuperação | Clássico | 10 | 1.453,05 | 1.370,71 | 1.333,20 |
| Recuperação | Clássico | 100 | 1.188,43 | 1.202,46 | 1.164,95 |
| Recuperação | Híbrido | 1 | 6.770,53 | 5.659,18 | 5.620,15 |
| Recuperação | Híbrido | 10 | 1.708,18 | 1.632,03 | 1.593,93 |
| Recuperação | Híbrido | 100 | 1.258,14 | 1.274,26 | 1.235,46 |
| Recuperação | Pós-quântico | 1 | 22.990,04 | 9.942,34 | 9.582,02 |
| Recuperação | Pós-quântico | 10 | 3.474,66 | 2.495,14 | 2.134,04 |
| Recuperação | Pós-quântico | 100 | 1.740,26 | 1.832,56 | 1.472,24 |

| Cenário | Perfil | Leituras por conexão | Economia: contexto perdido | Economia: contexto preservado |
|---|---|---:|---:|---:|
| Sem falhas | Clássico | 1 | 27,10% [27,03; 27,11] | 27,09% [27,05; 27,10] |
| Sem falhas | Clássico | 10 | 7,61% [7,58; 7,63] | 7,64% [7,61; 7,66] |
| Sem falhas | Clássico | 100 | 0,00% [-0,00; 0,05] | 0,00% [-0,05; 0,05] |
| Sem falhas | Híbrido | 1 | 16,93% [16,89; 16,99] | 16,95% [16,86; 16,98] |
| Sem falhas | Híbrido | 10 | 6,30% [6,26; 6,33] | 6,29% [6,23; 6,31] |
| Sem falhas | Híbrido | 100 | -0,02% [-0,05; 0,01] | 0,00% [-0,01; 0,01] |
| Sem falhas | Pós-quântico | 1 | 58,31% [58,29; 58,32] | 58,30% [58,30; 58,32] |
| Sem falhas | Pós-quântico | 10 | 37,10% [37,09; 37,12] | 37,10% [37,08; 37,12] |
| Sem falhas | Pós-quântico | 100 | 0,00% [0,00; 0,04] | 0,00% [0,00; 0,02] |
| Recuperação | Clássico | 1 | 26,24% [26,19; 26,25] | 27,08% [27,05; 27,11] |
| Recuperação | Clássico | 10 | 5,66% [5,63; 5,69] | 8,22% [8,21; 8,27] |
| Recuperação | Clássico | 100 | -1,18% [-1,21; -1,14] | 1,97% [1,93; 2,00] |
| Recuperação | Híbrido | 1 | 16,40% [16,37; 16,42] | 16,96% [16,92; 17,04] |
| Recuperação | Híbrido | 10 | 4,45% [4,41; 4,49] | 6,66% [6,63; 6,73] |
| Recuperação | Híbrido | 100 | -1,30% [-1,37; -1,20] | 1,80% [1,77; 1,84] |
| Recuperação | Pós-quântico | 1 | 56,76% [56,75; 56,76] | 58,32% [58,31; 58,33] |
| Recuperação | Pós-quântico | 10 | 28,20% [28,18; 28,23] | 38,58% [38,55; 38,59] |
| Recuperação | Pós-quântico | 100 | -5,30% [-5,30; -5,24] | 15,40% [15,38; 15,43] |

### Tempo e número de conexões no perfil pós-quântico

| Cenário | Leituras por conexão | Tratamento | ms/leitura | Handshakes completos | Handshakes retomados |
|---|---:|---|---:|---:|---:|
| Sem falhas | 1 | Completo | 46,46 | 100 | 0 |
| Sem falhas | 1 | Contexto perdido | 39,44 | 1 | 99 |
| Sem falhas | 1 | Contexto preservado | 39,36 | 1 | 99 |
| Sem falhas | 10 | Completo | 16,84 | 10 | 0 |
| Sem falhas | 10 | Contexto perdido | 16,29 | 1 | 9 |
| Sem falhas | 10 | Contexto preservado | 16,10 | 1 | 9 |
| Sem falhas | 100 | Completo | 13,58 | 1 | 0 |
| Sem falhas | 100 | Contexto perdido | 13,79 | 1 | 0 |
| Sem falhas | 100 | Contexto preservado | 13,45 | 1 | 0 |
| Recuperação | 1 | Completo | 50,33 | 101 | 0 |
| Recuperação | 1 | Contexto perdido | 43,98 | 3 | 98 |
| Recuperação | 1 | Contexto preservado | 42,88 | 1 | 100 |
| Recuperação | 10 | Completo | 20,10 | 11 | 0 |
| Recuperação | 10 | Contexto perdido | 19,74 | 3 | 8 |
| Recuperação | 10 | Contexto preservado | 19,63 | 1 | 10 |
| Recuperação | 100 | Completo | 17,44 | 3 | 0 |
| Recuperação | 100 | Contexto perdido | 17,81 | 3 | 0 |
| Recuperação | 100 | Contexto preservado | 17,60 | 1 | 2 |

Os tempos e as contagens de handshakes estão nas tabelas de dados. A redução de bytes não demonstra, por si só, superioridade temporal geral. O custo inclui enquadramento, confirmações, marcador de fim de grupo e encerramentos; não é o tamanho isolado do handshake.

## Verificações complementares

- O tamanho dos tickets e o certificado do cliente incorporado ao estado estão documentados em `diagnostico_tickets_20261106.md`.
- As 100 verificações do componente de persistência, as 30 verificações adicionais do gateway TLS, o nonce do checkpoint e a identificação do dispositivo estão em `verificacoes_persistencia_checkpoint_20261106.md`.
- As auditorias confrontam o ClientHello capturado com o medido na biblioteca e verificam as cadeias em ambos os sentidos, os tickets e os registros de aplicação.

São dez blocos, um sensor emulado e um host compartilhado. Os efeitos avaliados são registros no banco. Não foram medidos sensores físicos, cortes de energia ou execução única de atuadores. O banco mantém identificadores e resumos, não o payload integral. Os resultados anteriores permanecem preservados.
