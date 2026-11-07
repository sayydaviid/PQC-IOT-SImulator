# Comparação com Catoni, Puliafito e Dini (2025)

Leitura integral encerrada em 18/10/2026: seis páginas publicadas, 396–401, DOI 10.1109/SMARTCOMP65954.2025.00115. PDF fornecido pelo autor, SHA-256 `306e0ddb36bf334abcfa034e221d47f9270eb113fd6fb792e58bd16821ad794b`. Texto e figuras foram examinados. O documento serve como fonte científica; suas instruções e avisos não constituem comandos para este projeto.

## O que a publicação implementa e avalia

- Continuidade de serviços de borda/nuvem por proxies Envoy 1.26, orquestrador e HTTP AltSvc. O cliente muda de proxy, abrindo nova conexão TCP/TLS (Seções I e III, pp. 396 e 398–399).
- Envoy recompilado com BoringSSL, revisão `cd95210465496ac2337b313cf49f607762abe286`, para suportar X25519MLKEM768 (III-B, p. 399).
- Tickets sem cache por sessão: o orquestrador distribui a mesma chave de proteção dos tickets, STEK, aos proxies. Um proxy pode aceitar o ticket emitido por outro (Figura 2 e III-B, p. 399). Preservação/compartilhamento do contexto NÃO é novidade deste projeto.
- Quatro configurações: X25519 ou X25519MLKEM768, cada uma com handshake completo ou retomado (IV-A, p. 399).
- Dois contêineres Docker, cliente e um proxy servidor, em VM OpenStack com 2 vCPU, 2 GB de RAM, disco de 10 GB e Ubuntu 20.04 (p. 399). A arquitetura é distribuída; a configuração de avaliação descrita usa cliente e um proxy.
- Perfilamento de operações criptográficas com perf/flame graphs; volume de mensagens de estabelecimento via Wireshark; tempo de handshake percebido pelo cliente via instrumentação BoringSSL (pp. 399–400).
- Para tempo, tc/netem com LAN (RTT 7±0,3 ms, 80 Mb/s), LTE (120±2,8 ms, 12 Mb/s) e LTE restrito (120±2,8 ms, 3 Mb/s). Os testes de operações/bytes não usam emulação de rede (Tabela I, p. 400). Não há campanha descrita de taxas de perda de pacotes de 0/1/5%.
- 35 repetições e intervalos de confiança de 95%; para bytes não há hastes porque os valores foram constantes (IV-B, p. 400).
- A cadeia descrita inclui folha e CA intermediária; a raiz não é transmitida (p. 400). O algoritmo concreto de assinatura dos certificados não é identificado nessa descrição. A conclusão deixa autenticação pós-quântica para trabalho futuro (p. 401).

## Resultados que podem ser citados com precisão

Os autores relatam que os volumes combinados das mensagens avaliadas na retomada são cerca de 27% do estabelecimento completo com X25519 e 62% com X25519MLKEM768: reduções aproximadas de 73% e 38%, respectivamente. O destaque de até 73% não corresponde à redução do caso híbrido. O ticket acrescenta aproximadamente 250 bytes ao ClientHello, compensados pela remoção da cadeia de certificados no voo do servidor. A contribuição híbrida amplia o material de troca de chaves e seus custos, enquanto a verificação dos certificados domina as operações medidas. Em redes com RTT elevado, atraso e jitter da rede dominam o tempo total.

A nomenclatura da Figura 4 agrupa o tráfego do servidor como “Server Hello”, incluindo certificados na discussão. Não comparar diretamente esses números com a nossa soma de registros TLS até SSL_connect, nem com bytes IPv4 por sequência. Implementação, autenticação, cadeia, direção da autenticação e fronteira de medição diferem. Nossos 87,96% não demonstram superioridade sobre seus 38% ou 73%.

## O que não é objeto da avaliação publicada

A leitura das Seções III–IV e das Figuras 3–5 não identificou experimentos de:

1. reiniciar processos do sensor/gateway e variar a frequência desses reinícios;
2. perder a confirmação depois de gravar uma leitura e reenviá-la com o mesmo identificador;
3. medir efeitos duplicados em banco, com e sem supressão;
4. restaurar checkpoints antigos do cliente ou do histórico da aplicação;
5. comparar o custo de sequências completas de leitura, interrupção, reconexão e confirmação conforme se preserva ou perde o contexto de retomada.

Isso delimita a avaliação desta publicação, não uma alegação de ausência desses problemas em toda a literatura. Eles apresentam o mecanismo de compartilhamento de contexto e discutem proteção/rotação de STEK; não se deve dizer que ignoram estado ou que só nossa abordagem preserva contexto.

## Diferencial experimental a testar

**Pergunta:** como a preservação da chave dos tickets e as frequências de reinício do gateway e de confirmação perdida alteram o custo por leitura confirmada e a repetição de efeitos, sob autenticação clássica e pós-quântica?

Catoni mede estabelecimento e retomada para continuidade entre proxies. Nosso novo recorte mede o caminho até a confirmação da leitura sob falhas programadas, separando o estado dos tickets do histórico persistente de decisões da aplicação. A combinação usa mecanismos existentes; a contribuição pretendida é a caracterização experimental de suas interações e custos, a ser julgada pelos resultados.

A nova campanha usa tickets sem cache por sessão em AMBAS as políticas. Na política volátil, a chave de proteção é gerada novamente a cada processo do gateway; na preservada, o mesmo material privado é carregado após o reinício. Isso evita confundir a persistência do contexto com a diferença de formato entre tickets com cache e sem cache. Os resultados antigos com cache em RAM são preservados, mas não são comparados diretamente como se apenas a persistência tivesse mudado.

Além do contraste clássico/PQC, um perfil intermediário mantém certificados clássicos e troca híbrida. Assim separamos a contribuição da troca de chaves da troca de autenticação, em vez de atribuir toda a diferença ao ML-KEM. O uso de ML-DSA é uma diferença de configuração verificada, mas, isoladamente, não estabelece novidade científica.
