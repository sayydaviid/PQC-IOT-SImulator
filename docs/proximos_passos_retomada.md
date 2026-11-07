# Próximos passos: da validação funcional ao artigo

Atualização: 14/10/2026. Tema em desenvolvimento para WQuNets: **“Reinício e Rollback em Sessões PQC para IoT: Segurança, Recuperação e Custo de Estado”**. O recorte de publicação é candidato; ainda não demonstramos novidade suficiente para submissão.

**Etapas seguintes executadas:** runtime TLS nativo isolado, sessão restaurada em processo novo, ledger durável, controles negativos e piloto real de rede. O [resultado TLS](resultado_tls_piloto.md), a [reprodução](tls_reproducao.md) e o [manuscrito](artigo_retomada_wqunets.md) registram as evidências. Os itens abaixo conservam os critérios definidos antes da execução; os parágrafos de estado indicam o que foi concluído.

## 1. Contribuição que vamos avaliar

A pergunta agora é: **quando a retomada continua segura e econômica se o reinício acontece durante o protocolo, o contexto do gateway desaparece ou a confirmação da leitura se perde?**

São três propriedades diferentes: unicidade de chave/nonce; recuperação e rejeição de mensagens antigas; contabilização de leituras únicas na aplicação. São também custos diferentes: handshake bem-sucedido, tentativa interrompida e fallback completo. O artigo deve informar qual estado precisa permanecer atual para cada garantia.

O resultado de 66,14% da fase 1 mede o enquadramento do protocolo experimental em um contexto retomável. Não é redução medida em TLS nem evidência de uma nova construção criptográfica. Economizar bytes ao evitar assinaturas completas já tem antecedentes. A contribuição pretendida é a avaliação de condições de falha, controles negativos e custos efetivos, confrontada com uma implementação existente.

## 2. Triagem de trabalhos relacionados

Consulta de fontes primárias, em 14/10/2026. A triagem abaixo foi ampliada com leitura integral da cópia autoral de KEMTLS-PDK e do estudo de tickets, além de seções do texto completo disponibilizado pelo autor de IoT-Friendly AKE. A [revisão dirigida](revisao_retomada.md) distingue versões e escopo da leitura; Scott continua pendente de leitura integral. Esta tabela não é revisão sistemática nem prova de ineditismo.

| Fonte | O que já existe | Consequência para este projeto | Verificação ainda necessária |
|---|---|---|---|
| [OSCORE, RFC 8613, §7.5 e apêndice B](https://datatracker.ietf.org/doc/html/rfc8613#section-7.5) | Recuperação de contexto após perda de sequências e alternativas de persistência/contexto novo | Reserva de contadores e troca de contexto após reboot são baselines conhecidos | Selecionar uma implementação e validar sua configuração real de persistência |
| [TLS 1.3, RFC 9846, §2.2](https://datatracker.ietf.org/doc/html/rfc9846#section-2.2) | Retomada PSK e combinação com segredo assimétrico | Comparar garantias equivalentes e evitar atribuir novidade ao padrão de retomada | Confirmar negociação efetiva, política de tickets e parâmetros PQC no backend escolhido |
| [Avoine, Canard e Ferreira, 2019](https://eprint.iacr.org/2019/911) | AKE de três partes, retomada e forward secrecy com funções simétricas no dispositivo/back-end | A falha de divulgação do PSK retido desta bancada não pode ser generalizada a todos os protocolos simétricos | Ler modelo de comprometimento e comportamento de estado do protocolo completo |
| [Scott, 2023; revisão de 2024](https://eprint.iacr.org/2023/095) | TLS para IoT com implementação e estudo de migração PQC | Redução de custo de TLS PQC para IoT é antecedente relevante | Examinar retomada, armazenamento, reinícios e disponibilidade de código na versão avaliada |
| [Schwabe, Stebila e Wiggers, 2021; revisão de 2024](https://eprint.iacr.org/2021/779) | KEMTLS-PDK e redução de custo com chaves públicas distribuídas previamente | Autenticação completa por assinatura não é o único baseline eficiente | Separar autenticação por KEM, retomada PSK e garantias de exposição de estado |

Critério de novidade: antes de afirmar a lacuna, confrontar texto completo, modelo de ameaça e artefatos dos trabalhos mais próximos. Se um deles já cobrir o mesmo cenário, direcionar a contribuição à reprodução comparativa ou ampliar uma condição ausente, explicitamente verificada.

## 3. Fase 2 — interrupções do protocolo

Esta etapa foi implementada em módulo separado, preservando os fontes criptográficos da fase 1 e a verificabilidade de seus resultados.

Três políticas com chave nova: `full_pqc`, `psk_resume`, `pqc_resume`. Onze cenários: fluxo sem falha; interrupções após ClientHello, ServerHello, ClientFinished, commit do gateway, confirmação de chave, checkpoint e cifragem da leitura; confirmação da leitura perdida; checkpoint truncado; gateway sem raiz antes da tentativa.

Campanha final: dez repetições por cenário/política, **330 casos**. Os critérios são registrados antes da execução e incluem zero reutilização de chave/nonce, rejeição da época antiga, recuperação da leitura após um único evento de falha e contabilização do fallback completo. A aplicação sem ledger de IDs deve demonstrar duplicação quando perde a confirmação: é um controle negativo separado das falhas criptográficas.

O custo inclui mensagens das tentativas interrompidas e pedidos de retomada rejeitados. O transporte é uma injeção lógica de falha, com primitivas e checkpoints reais; não representa perda de pacotes medida no Mininet. Para confirmação perdida, a mensagem do servidor entra no custo de envio mesmo sem confirmação do cliente. Mensagem de erro do gateway não é transmitida neste modelo e fica fora desse custo.

Resultado: [resultado_transicoes_retomada.md](resultado_transicoes_retomada.md).

Verificação concluída: **330 casos aprovados nos critérios registrados e 74 testes de regressão aprovados** na imagem original, com liboqs/liboqs-python 0.14.0 e pytest 9.1.1. A alegação de economia universal de bytes falhou no cenário de raiz perdida; a unicidade de chave/nonce permaneceu válida nos cenários testados. Os controles de confirmação perdida mostraram duplicação da leitura na aplicação sem ledger de IDs. Os hashes dos fontes das duas campanhas da fase 1 também foram rechecados e continuam válidos.

```bash
docker compose run --rm --entrypoint python3 -e PYTHONDONTWRITEBYTECODE=1 notebook \
  scripts/run_recovery_transitions.py --repetitions 10 \
  --output /workspace/results/raw/recovery_transitions_reproduction \
  --report /workspace/docs/resultado_transicoes_retomada.md
```

Usar um diretório de resultados novo. Manifesto, dados detalhados e CSV são exportados antes da conclusão. Os checkpoints e segredos do experimento são temporários e apagados. Se um critério de segurança falhar, o comando retorna erro e registra `FAILED_GATE`.

## 4. Fase 3 — baseline TLS real

**Concluída.** O runtime original OpenSSL 3.0.2 foi preservado; um runtime adicional usa OpenSSL 3.5.9 com TLS 1.3, X25519MLKEM768, ML-DSA-44 e AES-256-GCM. Passaram integração com quatro clientes em processos novos e quatro controles negativos de identidade/conteúdo. O módulo C expõe TLS nativo, com negociação, assinaturas e retomada efetiva verificadas. O checkpoint serializado é autenticado, 0-RTT está desabilitado e o cache do gateway é stateful em RAM.

ML-KEM nativo foi introduzido no OpenSSL 3.5 ([documentação oficial](https://docs.openssl.org/3.5/man7/EVP_KEM-ML-KEM/#history)). A documentação do [oqs-provider](https://github.com/open-quantum-safe/oqs-provider#note-on-openssl-versions) também distingue as limitações de assinaturas TLS em versões anteriores. Preparar um runtime separado, com versão/commit e hash da imagem registrados, mantém os experimentos atuais reproduzíveis.

Condições de entrada da avaliação: conexão TLS real; identidade verificada; sessão serializada e restaurada pelo cliente; prova de que ocorreu retomada, em vez de fallback silencioso; segredo assimétrico novo efetivamente negociado; 0-RTT desabilitado; registro da suíte, grupo KEM, categoria de segurança, assinatura e política de ticket. Não assumir que suporte EVP a ML-KEM implica suporte a todo grupo TLS.

Comparar handshake completo e retomado **dentro do mesmo backend e com parâmetros compatíveis**. Se a implementação exigir ML-KEM-768 ou grupos híbridos, registrar a diferença e preparar configuração equivalente antes de comparar com esta bancada ML-KEM-512. Chaves fixadas e cadeias de certificados também precisam ser contabilizadas separadamente. A redução de 66,14% não será usada como resultado de TLS.

## 5. Fase 4 — piloto em rede e leituras únicas

**Concluída como piloto.** São 60 condições, 360 processos e 300 entregas lógicas, com deduplicação ativa/desativada. Perder o cache do gateway exige handshake completo; restaurar ticket antigo com gateway vivo permite retomada com key_share novo. O controle produz 30 efeitos duplicados, contra zero no ledger durável. TCP_INFO complementa PCAP na medição de retransmissões. Tempos são do host; os cinco blocos não sustentam P95 robusto. Não foi implementada matriz de interrupções internas do TLS: essa matriz permanece limitada ao protótipo da fase 2.

Após o baseline TLS passar pela validação funcional, executar um piloto com contextos retomáveis, raízes perdidas e reinícios em pontos de protocolo controlados. No Mininet, separar perda de pacotes do TCP de interrupção do processo: perder um pacote pode causar retransmissão sem novo handshake.

Configuração inicial proposta, a registrar antes de executar: perdas independentes de 0%, 1% e 5%; cinco blocos independentes; cinco boots por política por bloco; mesma sequência de leituras e falhas lógicas entre comparadores, ordem alternada. A perda aleatória do kernel não será apresentada como exatamente pareada sem controlar seu gerador. É um piloto para custos e falhas de implementação, não uma campanha suficiente para sustentar P95 robusto.

Medir: bytes de handshake, bytes IPv4/retransmissões em PCAP, fallbacks, tentativas até recuperar comunicação, tempo até a primeira leitura autenticada, entrega e leituras únicas. A unidade de repetição para inferência será a execução/bloco, e não cada pacote correlacionado. Definir timeout, tratamento de falhas e intervalos de confiança antes de ampliar as repetições.

Comparar a aplicação atual com uma aplicação que mantém IDs de leitura e persiste sua decisão antes do ACK. Um ID repetido com conteúdo diferente deve ser tratado como conflito. Essa deduplicação é um baseline de aplicação; não será apresentada como novo mecanismo criptográfico. Um ledger restaurável também não prova resistência ao rollback de todo o gateway. Orçamento de criptografia, tentativas e leituras únicas precisam ter contadores separados.

Energia de ESP32 permanece fora das conclusões até haver uma calibração justificável. Escritas de arquivo e tempo de fsync no host não são ciclos de flash ou energia medida no dispositivo.

## 6. Fase 5 — manuscrito e decisão

**Rascunho concluído** em [artigo_retomada_wqunets.md](artigo_retomada_wqunets.md), com a mesma hierarquia do PDF de referência. Decisão: continuar com avaliação condicionada de estado e recuperação, sem alegação de novo mecanismo criptográfico ou economia universal. Para submissão faltam comprovar o diferencial frente ao antecedente próximo, definir autoria e adaptar à chamada/formato vigente.

Manter Abstract, Resumo e as seis seções do artigo de referência: Introdução, Fundamentação Teórica, Trabalhos Relacionados, Estratégia Proposta (4.1 Modelagem / 4.2 Estratégia), Avaliação e Resultados (5.1 Falhas de Estado / 5.2 Garantias de Retomada / 5.3 Custos e Recuperação), Conclusão e Trabalhos Futuros.

Introdução, Fundamentação, Métodos e Resultados incluem agora as fases 3/4. Para uma versão submetível: comparação com antecedente próximo, fontes/dados depositados e alegações limitadas às medidas. O alvo WQuNets é mantido; enquadramento na chamada e formato da próxima edição precisam ser confirmados quando publicados.

Decisões possíveis: continuar como avaliação experimental de segurança; restringir a uma falha/condição com contribuição verificável; ou descartar a alegação de novidade. A perda de uma alegação universal de economia não descarta automaticamente a hipótese condicionada a um gateway com contexto retomável.
