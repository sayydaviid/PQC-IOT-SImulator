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
| 0% | Clássico | Folha e raiz | 4.638,33 | 2.699,44 | 2.699,39 |
| 0% | Clássico | Apenas folha | 3.800,28 | 2.606,56 | 2.606,56 |
| 0% | Híbrido | Folha e raiz | 6.906,39 | 5.055,94 | 5.056,06 |
| 0% | Híbrido | Apenas folha | 6.073,50 | 4.963,00 | 4.963,00 |
| 0% | Pós-quântico | Folha e raiz | 30.648,56 | 11.055,44 | 11.057,44 |
| 0% | Pós-quântico | Apenas folha | 22.169,89 | 10.119,22 | 10.117,22 |
| 25% | Clássico | Folha e raiz | 5.579,50 | 3.820,11 | 3.176,94 |
| 25% | Clássico | Apenas folha | 4.543,44 | 3.530,06 | 3.083,89 |
| 25% | Híbrido | Folha e raiz | 8.348,00 | 6.705,39 | 6.059,78 |
| 25% | Híbrido | Apenas folha | 7.324,67 | 6.434,22 | 5.966,72 |
| 25% | Pós-quântico | Folha e raiz | 37.364,56 | 18.838,78 | 12.916,11 |
| 25% | Pós-quântico | Apenas folha | 26.987,44 | 16.008,56 | 11.969,22 |
| 100% | Clássico | Folha e raiz | 8.389,83 | 9.642,11 | 4.609,61 |
| 100% | Clássico | Apenas folha | 6.758,28 | 7.917,39 | 4.516,83 |
| 100% | Híbrido | Folha e raiz | 12.674,94 | 14.105,39 | 9.071,11 |
| 100% | Híbrido | Apenas folha | 11.086,33 | 12.524,89 | 8.978,17 |
| 100% | Pós-quântico | Folha e raiz | 57.467,22 | 65.603,44 | 18.448,78 |
| 100% | Pós-quântico | Apenas folha | 41.463,67 | 49.645,00 | 17.504,78 |

| Frequência das duas falhas | Perfil | Cadeia enviada | Economia: contexto perdido | Economia: contexto preservado |
|---|---|---|---:|---:|
| 0% | Clássico | Folha e raiz | 41,80% [41,75; 41,90] | 41,79% [41,71; 41,89] |
| 0% | Clássico | Apenas folha | 31,47% [31,27; 31,57] | 31,41% [31,25; 31,55] |
| 0% | Híbrido | Folha e raiz | 26,79% [26,66; 26,82] | 26,79% [26,71; 26,84] |
| 0% | Híbrido | Apenas folha | 18,27% [18,22; 18,29] | 18,27% [18,15; 18,34] |
| 0% | Pós-quântico | Folha e raiz | 63,92% [63,90; 63,96] | 63,92% [63,89; 63,95] |
| 0% | Pós-quântico | Apenas folha | 54,35% [54,28; 54,41] | 54,36% [54,28; 54,41] |
| 25% | Clássico | Folha e raiz | 31,49% [26,09; 31,57] | 43,06% [43,00; 43,15] |
| 25% | Clássico | Apenas folha | 22,30% [17,90; 22,36] | 32,14% [32,11; 32,20] |
| 25% | Híbrido | Folha e raiz | 19,67% [16,02; 19,72] | 27,40% [27,33; 27,45] |
| 25% | Híbrido | Apenas folha | 12,20% [9,43; 12,31] | 18,53% [18,49; 18,59] |
| 25% | Pós-quântico | Folha e raiz | 49,56% [41,81; 49,62] | 65,44% [65,39; 65,51] |
| 25% | Pós-quântico | Apenas folha | 40,68% [33,35; 40,71] | 55,65% [55,62; 55,69] |
| 100% | Clássico | Folha e raiz | -14,88% [-15,00; -14,83] | 45,07% [45,04; 45,10] |
| 100% | Clássico | Apenas folha | -17,17% [-17,35; -17,05] | 33,20% [33,08; 33,24] |
| 100% | Híbrido | Folha e raiz | -11,32% [-11,44; -11,26] | 28,42% [28,34; 28,44] |
| 100% | Híbrido | Apenas folha | -12,99% [-13,06; -12,98] | 18,97% [18,92; 19,04] |
| 100% | Pós-quântico | Folha e raiz | -14,18% [-14,20; -14,04] | 67,89% [67,88; 67,94] |
| 100% | Pós-quântico | Apenas folha | -19,70% [-19,78; -19,65] | 57,79% [57,77; 57,82] |

### Tempo de recuperação com ambas as falhas em 100%

O tempo por leitura divide o intervalo até a última confirmação pelo número de leituras da execução. Inclui processos, reinícios previstos e reenvios. Não é uma medição isolada da latência do handshake.

| Perfil | Cadeia enviada | Completo: ms/leitura | Contexto perdido: ms/leitura | Contexto preservado: ms/leitura |
|---|---|---:|---:|---:|
| Clássico | Folha e raiz | 910,25 | 924,13 | 794,48 |
| Clássico | Apenas folha | 920,75 | 919,77 | 798,79 |
| Híbrido | Folha e raiz | 908,22 | 906,98 | 798,01 |
| Híbrido | Apenas folha | 924,68 | 931,24 | 803,49 |
| Pós-quântico | Folha e raiz | 915,57 | 964,57 | 827,88 |
| Pós-quântico | Apenas folha | 913,47 | 933,07 | 826,01 |

## Leituras por conexão

Cada execução transmite 100 leituras lógicas de 512 bytes, usando um único processo cliente. Os limites de 1, 10 ou 100 leituras por conexão se aplicam aos três tratamentos. O primeiro handshake completo é incluído, sem retirar um aquecimento do custo. Apenas os certificados folha são transmitidos; a raiz continua confiável. As conclusões sobre amortização comparam condições dentro deste experimento. Seus custos absolutos não devem ser comparados diretamente aos da matriz de cadeias, que usa outro payload e outro número de processos.

No cenário de recuperação, o gateway reinicia antes da leitura de índice 50, cuja primeira confirmação é suprimida após a gravação. Uma conexão pode ser dividida por essa fronteira. O reenvio conserva o identificador, e as leituras já confirmadas não são repetidas. As condições são detalhadas em `metodo_amortizacao_20261106.md`.

| Cenário | Perfil | Leituras por conexão | Completo: bytes/leitura | Contexto perdido: bytes/leitura | Contexto preservado: bytes/leitura |
|---|---|---:|---:|---:|---:|
| Sem falhas | Clássico | 1 | 4.437,51 | 3.200,60 | 3.200,59 |
| Sem falhas | Clássico | 10 | 1.473,61 | 1.361,72 | 1.361,97 |
| Sem falhas | Clássico | 100 | 1.168,81 | 1.168,80 | 1.168,28 |
| Sem falhas | Híbrido | 1 | 6.753,40 | 5.568,07 | 5.568,07 |
| Sem falhas | Híbrido | 10 | 1.707,36 | 1.599,03 | 1.598,76 |
| Sem falhas | Híbrido | 100 | 1.191,18 | 1.192,22 | 1.190,99 |
| Sem falhas | Pós-quântico | 1 | 22.865,18 | 9.487,69 | 9.488,73 |
| Sem falhas | Pós-quântico | 10 | 3.317,04 | 2.097,17 | 2.096,91 |
| Sem falhas | Pós-quântico | 100 | 1.351,80 | 1.352,58 | 1.352,58 |
| Recuperação | Clássico | 1 | 4.479,02 | 3.267,28 | 3.228,49 |
| Recuperação | Clássico | 10 | 1.514,01 | 1.428,95 | 1.389,34 |
| Recuperação | Clássico | 100 | 1.241,72 | 1.256,28 | 1.216,93 |
| Recuperação | Híbrido | 1 | 6.819,77 | 5.659,25 | 5.619,64 |
| Recuperação | Híbrido | 10 | 1.770,16 | 1.690,33 | 1.648,78 |
| Recuperação | Híbrido | 100 | 1.311,34 | 1.327,03 | 1.287,45 |
| Recuperação | Pós-quântico | 1 | 23.089,88 | 9.938,96 | 9.575,78 |
| Recuperação | Pós-quântico | 10 | 3.540,70 | 2.548,18 | 2.186,04 |
| Recuperação | Pós-quântico | 100 | 1.793,82 | 1.885,86 | 1.523,20 |

| Cenário | Perfil | Leituras por conexão | Economia: contexto perdido | Economia: contexto preservado |
|---|---|---:|---:|---:|
| Sem falhas | Clássico | 1 | 27,87% [27,81; 27,91] | 27,87% [27,83; 27,94] |
| Sem falhas | Clássico | 10 | 7,56% [7,43; 7,67] | 7,58% [7,43; 7,74] |
| Sem falhas | Clássico | 100 | 0,00% [-0,02; 0,04] | 0,04% [0,00; 0,09] |
| Sem falhas | Híbrido | 1 | 17,55% [17,51; 17,59] | 17,53% [17,43; 17,60] |
| Sem falhas | Híbrido | 10 | 6,35% [6,32; 6,41] | 6,37% [6,29; 6,53] |
| Sem falhas | Híbrido | 100 | -0,09% [-0,15; 0,00] | -0,00% [-0,09; 0,04] |
| Sem falhas | Pós-quântico | 1 | 58,50% [58,49; 58,52] | 58,50% [58,50; 58,52] |
| Sem falhas | Pós-quântico | 10 | 36,78% [36,74; 36,84] | 36,79% [36,77; 36,87] |
| Sem falhas | Pós-quântico | 100 | -0,02% [-0,15; 0,02] | 0,00% [-0,12; 0,04] |
| Recuperação | Clássico | 1 | 27,06% [27,01; 27,12] | 27,92% [27,87; 27,96] |
| Recuperação | Clássico | 10 | 5,65% [5,37; 5,76] | 8,27% [7,97; 8,41] |
| Recuperação | Clássico | 100 | -1,17% [-1,24; -1,05] | 1,99% [1,95; 2,10] |
| Recuperação | Híbrido | 1 | 16,94% [16,93; 17,00] | 17,56% [17,52; 17,62] |
| Recuperação | Híbrido | 10 | 4,53% [4,47; 4,62] | 6,84% [6,74; 7,01] |
| Recuperação | Híbrido | 100 | -1,22% [-1,29; -1,11] | 1,86% [1,79; 1,91] |
| Recuperação | Pós-quântico | 1 | 56,96% [56,94; 56,98] | 58,53% [58,52; 58,55] |
| Recuperação | Pós-quântico | 10 | 28,07% [28,00; 28,09] | 38,26% [38,22; 38,30] |
| Recuperação | Pós-quântico | 100 | -5,12% [-5,21; -5,06] | 15,11% [15,03; 15,12] |

### Tempo e número de conexões no perfil pós-quântico

| Cenário | Leituras por conexão | Tratamento | ms/leitura | Handshakes completos | Handshakes retomados |
|---|---:|---|---:|---:|---:|
| Sem falhas | 1 | Completo | 191,38 | 100 | 0 |
| Sem falhas | 1 | Contexto perdido | 74,85 | 1 | 99 |
| Sem falhas | 1 | Contexto preservado | 73,80 | 1 | 99 |
| Sem falhas | 10 | Completo | 75,65 | 10 | 0 |
| Sem falhas | 10 | Contexto perdido | 64,64 | 1 | 9 |
| Sem falhas | 10 | Contexto preservado | 63,80 | 1 | 9 |
| Sem falhas | 100 | Completo | 62,14 | 1 | 0 |
| Sem falhas | 100 | Contexto perdido | 63,53 | 1 | 0 |
| Sem falhas | 100 | Contexto preservado | 61,55 | 1 | 0 |
| Recuperação | 1 | Completo | 201,89 | 101 | 0 |
| Recuperação | 1 | Contexto perdido | 80,46 | 3 | 98 |
| Recuperação | 1 | Contexto preservado | 80,31 | 1 | 100 |
| Recuperação | 10 | Completo | 78,14 | 11 | 0 |
| Recuperação | 10 | Contexto perdido | 68,46 | 3 | 8 |
| Recuperação | 10 | Contexto preservado | 68,86 | 1 | 10 |
| Recuperação | 100 | Completo | 68,34 | 3 | 0 |
| Recuperação | 100 | Contexto perdido | 67,90 | 3 | 0 |
| Recuperação | 100 | Contexto preservado | 66,31 | 1 | 2 |

Os tempos e as contagens de handshakes estão nas tabelas de dados. A redução de bytes não demonstra, por si só, superioridade temporal geral. O custo inclui enquadramento, confirmações, marcador de fim de grupo e encerramentos; não é o tamanho isolado do handshake.

## Verificações complementares

- O tamanho dos tickets e o certificado do cliente incorporado ao estado estão documentados em `diagnostico_tickets_20261106.md`.
- As 100 verificações do componente de persistência, as 30 verificações adicionais do gateway TLS, o nonce do checkpoint e a identificação do dispositivo estão em `verificacoes_persistencia_checkpoint_20261106.md`.
- As auditorias confrontam o ClientHello capturado com o medido na biblioteca e verificam as cadeias em ambos os sentidos, os tickets e os registros de aplicação.

São dez blocos, um sensor emulado e um host compartilhado. Os efeitos avaliados são registros no banco. Não foram medidos sensores físicos, cortes de energia ou execução única de atuadores. O banco mantém identificadores e resumos, não o payload integral. Os resultados anteriores permanecem preservados.
