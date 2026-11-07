# Reprodução: TLS PQC, reinícios e leituras únicas

Runtime adicional isolado: `pqc-iot-tls:3.5.9`, baseado na imagem original `pqc_iot_simulator:latest`. O módulo C apenas expõe o transporte nativo OpenSSL ao Python; não implementa criptografia nem altera a derivação de chaves TLS. A imagem original e as campanhas anteriores foram preservadas.

## Construção e identidade do runtime

```bash
docker build -q -t pqc-iot-tls:3.5.9 -f experiments/tls/Dockerfile .
docker image inspect pqc-iot-tls:3.5.9 --format '{{.Id}}'
```

Versão executada: OpenSSL 3.5.9, tag `openssl-3.5.9`, commit `45e844fa2a14ec92d146bd8f5778ac130b6625fb`. ID local da imagem TLS: `sha256:aa8b84fd346c76bad96f76cca9ed8d99a47d296fbffe0ae16e305c9e9a0db804`; imagem base: `sha256:39565cb7a8727679c79229ecd51f0703c099a03f339a9a25fdb5dee384883001`. Uma reconstrução pode produzir outro ID; registrar seu ID e o commit efetivo. O Dockerfile usa a tag como entrada; para uma reprodução estrita, conferir que ela resolveu para o commit acima.

O manifesto verifica hashes dos fontes, inclusive da cópia C compilada na imagem, antes da execução. Alterar `native.c` exige reconstruir a imagem. Alterar qualquer fonte listado durante a campanha invalida sua conclusão. Instantes de início são registrados em UTC; nomes com `20261014` representam a data local do host usada na execução original.

## Verificações funcionais e negativas

Usar diretórios novos em cada execução:

```bash
docker compose -f docker-compose.yml -f experiments/tls/compose.yml run --rm \
  --entrypoint python3 -e PYTHONDONTWRITEBYTECODE=1 notebook \
  scripts/verify_tls_baseline.py --output /workspace/results/raw/tls_baseline_reproduction

docker compose -f docker-compose.yml -f experiments/tls/compose.yml run --rm \
  --entrypoint python3 -e PYTHONDONTWRITEBYTECODE=1 notebook \
  scripts/verify_tls_security.py --output /workspace/results/raw/tls_security_reproduction

docker compose -f docker-compose.yml -f experiments/tls/compose.yml run --rm \
  --entrypoint bash -e PYTHONDONTWRITEBYTECODE=1 notebook \
  -c 'python3 -m pip install --quiet pytest==9.1.1 && python3 -m pytest -q'
```

O baseline valida quatro processos, retomada efetiva, checkpoint DER autenticado, perda de ACK e restart do gateway preservando o ledger. Os quatro controles negativos cobrem nomes cliente/servidor incorretos, CA incorreta e ID repetido com conteúdo diferente. A suíte tem 82 testes, incluindo rollback transacional, perda de ACK, restauração completa do banco como controle vulnerável e auditoria PCAP com reutilização de portas. Pytest é dependência de desenvolvimento instalada nesse contêiner temporário; a imagem de execução não o inclui.

TLS 1.3 é obrigatório, com `TLS_AES_256_GCM_SHA384`, grupo híbrido `X25519MLKEM768` e autenticação mútua ML-DSA-44 no handshake completo. CA, SAN e CertificateVerify são verificados. Na retomada a identidade decorre da sessão previamente autenticada; não há nova assinatura de certificado em cada handshake retomado. Tickets são stateful, cache em RAM, timeout 3600 s e 0-RTT desabilitado. Credenciais e segredos experimentais são temporários; DER fica cifrado por AES-GCM e vinculado à CA/nome. Os resultados não exportam segredos.

## Piloto em rede

```bash
docker compose -f docker-compose.yml -f experiments/tls/compose.yml run --rm \
  -e PYTHONDONTWRITEBYTECODE=1 notebook python3 scripts/run_tls_network.py \
  --blocks 5 --losses 0 1 5 --output /workspace/results/raw/tls_network_reproduction

docker compose -f docker-compose.yml -f experiments/tls/compose.yml run --rm \
  --entrypoint python3 -e PYTHONDONTWRITEBYTECODE=1 notebook \
  scripts/summarize_tls_pilot.py --input /workspace/results/raw/tls_network_reproduction --figure
```

Executar somente um experimento Mininet por vez: o entrypoint limpa a topologia anterior. `--entrypoint python3` é usado nos comandos sem Mininet para evitar limpeza de outra execução. O ambiente precisa de Linux, Docker privilegiado, OVS e mac80211_hwsim, conforme o README.

São 60 condições: cinco blocos × três perdas × dois modos TLS × dois modos de deduplicação. Cada condição tem cinco leituras e seis tentativas em processos distintos. Boot 2 perde cache TLS do gateway, conservando SQLite; boot 3 perde confirmação depois do commit e repete o mesmo ID; boot 4 restaura o ticket salvo no boot 2, com gateway vivo. Os IDs são repetidos entre comparadores. A ordem rotaciona por bloco. A perda netem não é exatamente pareada: o gerador do kernel não foi sincronizado.

Perdas independentes de 0%, 1% e 5% e atraso de 2 ms são aplicados em ambos os sentidos do enlace AP–servidor. Captura em `h1-eth0`, qdiscs registrados. A cobertura de TCP usa sequência inicial e hash do key_share do ClientHello, tolerando reutilização da porta. Conexões confirmadas exigem igualdade de todos os bytes TLS e cobertura contínua. Na interrupção deliberada, a leitura precisa estar inteiramente capturada; um alerta terminal pode não chegar.

Retransmissões usam o contador Linux `TCP_INFO.tcpi_total_retrans`, offset 100 confirmado com `offsetof` no contêiner. Soma-se o contador dos dois endpoints antes do fechamento; retransmissões posteriores ao instante de amostragem não entram. A duplicação de payload no PCAP é uma medida distinta e um limite inferior. O contador não mede retransmissões Wi-Fi físicas. Capturas no host podem refletir offload; não inferimos quantidade de quadros físicos no ar.

O ledger SQLite usa WAL, `synchronous=FULL` e commit antes do ACK. O efeito medido é uma linha no banco. Deduplicação desativada conserva rastreamento para auditoria, mas permite nova inserção de efeito para o mesmo ID/conteúdo. Não há alegação de execução exatamente uma vez de atuador externo nem proteção contra restaurar todo o banco do gateway. IDs/cargas são entradas sintéticas controladas; o piloto não implementa fila durável de sensor físico.

## Campanhas usadas no texto

- `recovery_security_complete_20261014`: 240 traços e 65 verificações funcionais;
- `recovery_network_complete_20261014`: 30 processos com protocolo experimental;
- `recovery_transitions_complete_20261014`: 330 cenários de interrupção lógica;
- `tls_baseline_complete_20261014`: integração TLS após instrumentação TCP;
- `tls_security_complete_20261014`: controles negativos TLS;
- `tls_network_measured_20261014`: piloto final com contadores TCP.

Todos ficam em `results/raw/`. Pilotos `tls_network_pilot_*` e `tls_network_verified_*` interrompidos são excluídos. `tls_network_final_20261014` e baselines `*_final_*` são rodadas anteriores à instrumentação TCP, substituídas para os números atuais. Não misturar seus manifestos com fontes posteriores.

Os JSON, CSV e PCAP são locais e ignorados pelo Git. Para compartilhar o artigo, arquivar os diretórios válidos junto aos fontes e versões; os links locais não substituem depósito público dos artefatos. Não há energia/flash de ESP32 medida, inferência robusta de P95 ou conclusão sobre gateways simultaneamente restaurados.
