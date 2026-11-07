# Retomada de sessões PQC após reinícios e restauração de estado

Título de trabalho: **“Reinício e Rollback de Estado em Sessões Pós-Quânticas para IoT: Segurança e Custo de Retomada”**. Recorte inicial: WQuNets. Este documento preserva o roteiro de seis seções do artigo de referência e as subdivisões de modelagem, estratégia e avaliação. É um protocolo de pesquisa executável, não um manuscrito submetido.

## Abstract

We evaluate post-quantum session recovery under client restarts and state rollback using real cryptographic operations. Six policies are compared in 240 fault traces, complemented by 30 client process starts over Mininet-WiFi. Durable nonce reservation survives crashes but fails when its journal is rolled back. Authenticated resumption with fresh ML-KEM avoids key/nonce reuse in the tested scenarios and reduces framed handshake bytes by 66.14% relative to full authentication. Results assume fresh entropy and a live gateway authority; they do not constitute a formal protocol proof.

## Resumo

Avaliamos a retomada de sessões pós-quânticas diante de reinícios e rollback do cliente, com operações criptográficas reais. Comparamos seis políticas em 240 traços de falha e complementamos a avaliação com 30 inicializações de processos no Mininet-WiFi. A reserva durável de nonces resiste à queda de energia, mas falha quando seu journal é restaurado. A retomada autenticada com ML-KEM novo evita reutilização de chave/nonce nos cenários testados e reduz os bytes de handshake em 66,14% frente à autenticação completa. O resultado pressupõe entropia fresca e autoridade preservada no gateway; não constitui prova formal de segurança.

## 1. Introdução

Sensores podem reiniciar depois de cifrar uma leitura e antes de persistir seu contador. Restaurar um backup autenticado também pode recuperar uma chave de tráfego com um contador antigo. A validade criptográfica do arquivo não demonstra que ele é o estado mais recente.

Pergunta: **quais informações precisam sobreviver ao reinício para retomar uma sessão PQC sem reutilização de nonce, aceitação de replay ou extensão indevida de validade?**

Hipótese operacional: com autoridade de estado preservada no gateway e entropia fresca independente do snapshot, autenticar a retomada por segredo persistente e acrescentar ML-KEM efêmero permite novas chaves de tráfego após rollback do cliente, com menos bytes de handshake que autenticação completa por ML-DSA. Retomada apenas por PSK pode ser menor, mas precisa ser classificada separadamente quanto à divulgação posterior desse segredo.

## 2. Fundamentação Teórica

AES-GCM requer unicidade de nonce sob uma mesma chave; as condições de recuperação após perda de energia precisam preservar essa propriedade ([NIST SP 800-38D](https://csrc.nist.gov/pubs/sp/800/38/d/final)). Nos registros experimentais, o nonce tem prefixo de oito bytes e contador de quatro bytes; a chave e o prefixo são vinculados ao transcript por HKDF-SHA-256. Identidades, versão, época e contador são autenticados como AAD. Esgotamento do contador bloqueia a transmissão.

ML-KEM-512 estabelece o segredo assimétrico; ML-DSA-44 autentica o handshake completo. HKDF usa domínios diferentes para chave de tráfego, prefixo e segredo de retomada. HMAC-SHA-256 confirma as chaves e autentica a retomada. Todas essas operações usam bibliotecas reais; este fluxo não emprega o modo de bytes equivalentes do simulador original.

A distinção entre retomada PSK pura e com segredo assimétrico novo já faz parte do TLS 1.3 ([RFC 9846](https://datatracker.ietf.org/doc/html/rfc9846#section-2.2)). O protocolo aqui é uma bancada experimental com JSON enquadrado sobre TCP. Ele não implementa TLS, OSCORE, negociação de suites, certificados ou prova formal de segurança.

## 3. Trabalhos Relacionados

O OSCORE descreve perda de estado mutável, persistência de sequências e alternativas de recuperação de contexto ([RFC 8613, seção 7.5](https://datatracker.ietf.org/doc/html/rfc8613#section-7.5)). Portanto, persistir contadores, reservar faixas e gerar contexto novo após reboot já são técnicas conhecidas.

Retomada, segredo de sessões anteriores e restrições de IoT também aparecem em [IoT-Friendly AKE: Forward Secrecy and Session Resumption Meet Symmetric-Key Cryptography](https://eprint.iacr.org/2019/911). Retomada em TLS pós-quântico para IoT é discutida em [On TLS for the Internet of Things, in a Post Quantum world](https://eprint.iacr.org/2023/095).

Contribuição candidata: uma avaliação reproduzível de falhas de estado e dos custos de alternativas de retomada PQC, com controle de exposição de estado e testemunhos de falha. A revisão feita até aqui estabelece antecedentes relevantes; ela não estabelece uma lacuna inédita. A versão de publicação precisa confrontar protocolos e implementações existentes, além desta bancada.

## 4. Estratégia Proposta

### 4.1. Modelagem

Um sensor previamente identificado e um gateway. Os dois possuem chaves públicas ML-DSA fixadas por provisionamento confiável. A chave que cifra os arquivos do cliente pertence ao provisionamento e permanece fora do escopo do snapshot. O atacante pode observar mensagens, reproduzi-las, adulterá-las e restaurar arquivos antigos válidos do cliente. Falhas também podem truncar arquivos.

São separados: perda de RAM/queda de energia, com journal durável preservado; rollback de todo o armazenamento mutável do cliente, incluindo journal; corrupção de estado; perda da autoridade de estado do gateway; divulgação tardia somente do PSK. Divulgação de todo o armazenamento com sua chave de proteção e análise forense da memória são ameaças diferentes, fora do experimento atual.

O gateway conserva idade, orçamento de mensagens, época ativa, maior contador aceito e desafios pendentes durante os reinícios do sensor. Um gateway que perde essa autoridade rejeita o contexto anterior e exige autenticação completa. O código não persiste um ledger do gateway nem simula sua proteção por hardware. O tempo de expiração nos testes de falha é lógico; a verificação de rede usa idade lógica zero e temporização do host para observação.

| Política | Estado persistente do cliente | Ação após reinício |
|---|---|---|
| `checkpoint` | Chave de tráfego, prefixo, contador e raiz | Restaura o último checkpoint; controle vulnerável |
| `persist_each` | Mesmo contexto e journal independente | Grava a próxima posição antes de cada cifragem |
| `reserve_blocks` | Mesmo contexto e limite reservado | Grava uma faixa antes do uso; descarta seu restante no boot |
| `psk_resume` | Somente segredo de retomada | Desafios novos e HKDF autenticados por PSK |
| `pqc_resume` | Somente segredo de retomada | PSK, ML-KEM efêmero novo e confirmação das chaves |
| `full_pqc` | Credencial provisionada; checkpoint só da raiz | ML-KEM novo e autenticação mútua ML-DSA |

As identidades provisionadas não são alteradas pelo rollback. As chaves de tráfego não são gravadas nas políticas com chave nova. O modelo assume entropia nova no boot, na cifragem do checkpoint e nas operações assimétricas; restaurar também o estado do gerador aleatório exige outro modelo. Existe um controle negativo para demonstrar o risco de repetir a entropia na retomada PSK.

### 4.2. Estratégia

O bootstrap e o handshake completo usam quatro mensagens: pedido com contexto e nonce do cliente; desafio do servidor com chave pública ML-KEM efêmera e assinatura; ciphertext ML-KEM, assinatura do cliente e confirmação; confirmação do servidor. O estabelecimento e a derivação vinculam as mensagens completas. O provisionamento de identidades fica fora dos bytes e do tempo de handshake, igualmente para os dois comparadores.

Na retomada PQC, o pedido e o desafio são autenticados por HMAC do segredo de retomada. A chave nova depende desse segredo, do ML-KEM novo e do transcript completo. Mensagens da aplicação só são cifradas depois da confirmação do servidor; não há 0-RTT. Desafios têm prazo e uso único. O receptor verifica a idade e o orçamento na sua própria autoridade, mesmo se o cliente apresentar uma raiz restaurada com contagem antiga.

O armazenamento cifra e autentica arquivos com AES-GCM, usa arquivo temporário, fsync, rename e fsync do diretório. A reserva só passa a valer na RAM depois da gravação bem-sucedida. Falha de gravação bloqueia também tentativas repetidas no mesmo processo. Autenticidade do arquivo não é apresentada como prevenção de rollback. Corrupção ou perda de raiz pode causar fallback completo, contado como custo e disponibilidade.

## 5. Avaliação e Resultados

### 5.1. Falhas de persistência e rollback

Campanha padrão: seis políticas × quatro falhas × dez repetições = 240 traços, cada um com oito leituras antes e oito depois do boot. Bloco reservado de 32 posições. Cada repetição usa sessões, entropia e arquivos novos. Identidades são provisionadas uma vez por campanha. As quatro falhas são reinício limpo, queda antes do checkpoint, rollback do armazenamento inteiro e checkpoint truncado.

O observador privilegiado registra pares chave/nonce antes da decisão do receptor, sem exportar segredos. Para plaintexts sintéticos conhecidos e de mesmo comprimento, testa a recuperação do segundo plaintext pela relação entre ciphertexts de AES-GCM. Uma retransmissão do mesmo registro não é tratada como nova cifragem com plaintext diferente. O receptor rejeita replay; não há promessa de entrega exatamente uma vez após ACK perdido ou durabilidade de aplicação no gateway.

### 5.2. Autenticação, validade e exposição de estado

Verificações adicionais: adulteração de ciphertext, identidade, nonce e limites; mudança de modo; replay do desafio e da confirmação; identidade ML-DSA não provisionada; confirmação falsa em ambos os sentidos; expiração durante handshake; limite de mensagens preservado no gateway; crash depois da reserva e antes da cifragem; journal adulterado; contador esgotado; gateway sem contexto anterior; divulgação do PSK depois da sessão.

O teste de exposição revela somente a raiz PSK retida e tenta decifrar um registro passado. A ausência de decifragem na variante ML-KEM verifica dependência de material adicional. Ela não constitui prova de forward secrecy nem de apagamento físico. Comprometimento prévio do PSK continua permitindo impersonação ativa. Python e os arquivos do host não emulam armazenamento confiável de ESP32.

### 5.3. Custo de retomada e critérios de decisão

O Mininet-WiFi inicia dez processos novos por política (`full_pqc`, `psk_resume`, `pqc_resume`), restaura o checkpoint do primeiro boot nas nove reinicializações e mantém o gateway vivo. As mensagens criptográficas reais atravessam Wi-Fi e TCP; o servidor decifra a leitura e o cliente autentica seu ACK. A captura exige todos os bytes únicos de cada sentido de cada conexão, além da associação Wi-Fi.

Critérios registrados antes da execução: controle vulnerável expõe plaintext; políticas de chave nova não repetem chave/nonce e entregam todas as leituras no modelo; journal preservado resolve power loss, mas journal restaurado deve revelar o limite dessa técnica; verificações adicionais passam; retomada ML-KEM tem menos bytes que autenticação completa. Um gate de segurança falho descarta o resultado positivo, independentemente da redução de bytes.

Medidas: bytes das quatro mensagens enquadradas, bytes IPv4 em PCAP, escritas e bytes de arquivos, posições de contador descartadas e tempos observados no host. Escritas de arquivo não equivalem a ciclos de erase de flash. Não há medição ou estimativa de energia neste experimento. Não fazemos inferência de latência de ESP32 com tempos de CPU x86, nem afirmamos melhoria de P95 a partir deste teste de integração sem perdas.

Resultado fechado da execução: [resultado_hipotese_retomada.md](resultado_hipotese_retomada.md).

## 6. Conclusão e Trabalhos Futuros

Os resultados permitem decidir se esta bancada preserva os invariantes testados e quantificar seu custo de mensagens. Para um artigo, o passo seguinte é confrontar recuperação de contexto em uma implementação padronizada, detalhar a diferença entre corrupção e rollback adversarial e avaliar configurações de falha além de um cliente. Aprovação nos gates não equivale a garantia criptográfica formal ou aceitação em evento.

## Reprodução

Usar a imagem Docker do repositório já construída. A campanha de segurança não inicializa Mininet. A verificação de rede precisa dos mesmos privilégios e módulos do simulador original. Executar apenas uma instância de Mininet por vez.

```bash
docker compose run --rm --entrypoint python3 -e PYTHONDONTWRITEBYTECODE=1 notebook \
  scripts/run_recovery_campaign.py --repetitions 10 \
  --output /workspace/results/raw/recovery_security_reproduction

docker compose run --rm -e PYTHONDONTWRITEBYTECODE=1 notebook \
  python3 scripts/verify_recovery_network.py --boots 10 \
  --output /workspace/results/raw/recovery_network_reproduction

docker compose run --rm --entrypoint python3 -e PYTHONDONTWRITEBYTECODE=1 notebook \
  scripts/summarize_recovery.py \
  --security /workspace/results/raw/recovery_security_reproduction \
  --network /workspace/results/raw/recovery_network_reproduction --figure
```

Os diretórios de cada campanha precisam ser novos, para impedir sobrescrita de resultados. Todos os resultados e PCAPs ficam em `results/raw/`, ignorado pelo Git. O relatório, CSV agregado e figura ficam em `docs/`; o gerador verifica o hash dos fontes da campanha antes de produzir a conclusão.

Testes de regressão, em um ambiente com as dependências do projeto e liboqs reais:

```bash
python3 -m pip install -r requirements-dev.txt
PYTHONPYCACHEPREFIX=/tmp/pqc-recovery-pycache python3 -m pytest tests/ -q
```

A ausência de bindings PQC falha os testes completos; não gera aprovação por testes pulados. A campanha funcional também exige liboqs e encerra com erro se algum critério registrado falhar.

A verificação de referência foi feita com Python 3.10.12, liboqs e liboqs-python 0.14.0, cryptography 3.4.8 e pytest 9.1.1 no contêiner: **40 testes aprovados**. Identidade da imagem usada: `sha256:39565cb7a8727679c79229ecd51f0703c099a03f339a9a25fdb5dee384883001`. Essa identidade documenta a execução local, não fixa automaticamente uma reconstrução futura do Dockerfile.

Para rodar a suíte no mesmo runtime PQC da imagem, instalar pytest apenas no contêiner temporário:

```bash
docker compose run --rm --entrypoint bash -e PYTHONDONTWRITEBYTECODE=1 notebook \
  -c 'python3 -m pip install -r requirements-dev.txt && python3 -m pytest tests/ -q'
```
