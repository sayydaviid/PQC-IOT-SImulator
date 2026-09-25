# Perfil bibliográfico composto do ESP32-WROOM-32

Estes arquivos permitem estimar a campanha quando não há um ESP32 disponível. Eles **não são medições do dispositivo do experimento**. O simulador deve classificá-los como `configured/provisional`, nunca como `calibrated/measured`.

## Cenários

| Cenário | CPU a 80 MHz | CPU a 240 MHz | Interpretação |
|---|---:|---:|---|
| `inferior` | 20 mA | 30 mA | limite inferior da faixa oficial |
| `central` | 25,5 mA | 49 mA | ponto médio aritmético da faixa, não valor típico medido |
| `superior` | 31 mA | 68 mA | limite superior da faixa oficial |

As faixas vêm da ficha técnica ESP32 v5.3, a 3,3 V e 25 °C. As linhas `v_i_t` usam `E_trilho = 3,3 × I × t`. A linha Wi-Fi `direct_event` usa diretamente a energia agregada derivada do estudo. O simulador converte depois para energia retirada da bateria dividindo pela eficiência do regulador configurada (0,90 no perfil atual).

No cenário central, os estados de CPU não criptográficos do `default.yaml` também usam 25,5 mA, o ponto médio de 20–31 mA a 80 MHz. Ao selecionar `inferior` ou `superior`, o notebook aplica respectivamente 20 mA ou 31 mA a despertar, processamento, estado criptográfico de base e idle; no estado de leitura, acrescenta a carga efetiva derivada do BME280. Assim, o cenário escolhido não altera somente as linhas criptográficas do CSV. Os três pontos são extremos e ponto médio da faixa oficial, não percentis nem valores “típicos” medidos.

## Conjuntos de benchmark para sensibilidade de implementação

O notebook de artigo não trata um único tempo bibliográfico como verdade. Ele executa dois conjuntos completos:

| Conjunto | X25519 / Ed25519 | ML-KEM | ML-DSA | Finalidade |
|---|---|---|---|---|
| alias `selected` | CycloneCRYPTO `-O3` / ACNS-RIOT | Kyber512 AICCSA 2024 | Dilithium ACNS 2022 | perfil `cyclone_oryx_aiccsa_acns_composite`; exploratório, não referência controlada |
| alias `alternative` | wolfSSL/ESP-IDF a 240 MHz | Kyber512 round 1 no ESP32-PICO-KIT | mesmo proxy ACNS | perfil `wolfssl_asia_ccs_acns_composite_sensitivity`; sensibilidade, não comparação controlada |

Os arquivos alternativos são `esp32_literatura_alternativa_{inferior,central,superior}.csv`. Cada conjunto continua sendo um perfil bibliográfico **composto**, e não a imagem de um firmware único. Eles não são combinados por média: o notebook apresenta o envelope mínimo–máximo entre conjuntos e cenários.

No conjunto alternativo, wolfSSL publica 426,333 ms para geração Curve25519, 425,250 ms para acordo e 38,808 ms para verificação Ed25519 em ESP32 a 240 MHz. O estudo ASIA CCS 2020 publica 16 ms para a operação de encapsulação/encriptação Kyber512 no ESP32-PICO-KIT a 240 MHz. Esse Kyber é round 1 e, portanto, permanece um proxy mais distante de ML-KEM-512; sua função aqui é análise de sensibilidade, não substituição silenciosa do perfil-base.

## Evidência usada por operação

| Operação no ESP32 | Tempo usado | Evidência e hipótese |
|---|---:|---|
| `x25519_keygen` | 17 ms | ESP32 a 240 MHz, CycloneCRYPTO 2.5.0, GCC `-O3` |
| `x25519_exchange` | 16 ms | mesmo benchmark |
| `ed25519_verify` | 60 ms | ESP32-WROOM-32 a 80 MHz, RIOT/Monocypher |
| `ml_kem_encaps` | 6,352 ms | Kyber512 no ESP-WROOM-32 a 240 MHz, ESP-IDF 5.2.1, GCC 11.4 sem otimização |
| `ml_dsa_verify` | 43 ms | Dilithium nível 2 dinâmico no ESP32-WROOM-32 a 80 MHz, RIOT/PQClean |
| `hkdf_extract` | `B / 27,777 MB/s` | extrapolação inferior de throughput SHA-256; duração varia com segredos codificados por comprimento |
| `hkdf_expand` | `B / 27,777 MB/s` | extrapolação inferior de throughput SHA-256; inclui hash do transcript no `info` |
| `aes_gcm_encrypt` | `B / 1,773 MB/s` | extrapolação inferior; varia com o payload real, com custo fixo configurável atualmente zero |

O Dilithium do estudo ACNS 2022 é a versão de nível 2 anterior à publicação final do FIPS 204. Os tamanhos usados no estudo (chave pública de 1.312 B e assinatura de 2.420 B) coincidem com ML-DSA-44, mas o tempo continua sendo um *proxy* da versão de rodada 3, não uma medição do ML-DSA-44 final. Da mesma forma, o tempo de Kyber512 é um *proxy* pré-padronização para ML-KEM-512.

O código executa HKDF-Extract e HKDF-Expand com HMAC-SHA-256. Segredos são codificados com prefixos de comprimento; o `info` contém `pqc-iot-session-v1`, hash do transcript e contexto da sessão. As duas fases e seus bytes processados são registrados separadamente.

As durações de SHA-256 e AES-GCM foram derivadas de throughput em fluxo contínuo. Chamadas curtas têm custo fixo e, portanto, esses valores são limites inferiores otimistas (`throughput_extrapolation_lower_bound`), não latências medidas de chamadas curtas; seu impacto energético é muito pequeno diante do rádio e das operações assimétricas.

Os valores não foram obtidos por média entre artigos. Foram escolhidas operações publicadas no ESP32 e toda mistura de implementação ficou explícita. Isso é importante porque a incerteza de software supera a faixa de corrente: o benchmark oficial wolfSSL/Espressif publica cerca de 426 ms para Curve25519, enquanto o CycloneCRYPTO `-O3` usado aqui publica 17/16 ms. Da mesma forma, outro estudo revisado por pares publica 16 ms para encapsulação Kyber512 de rodada 1 no ESP32-PICO-KIT, enquanto o perfil usa os 6,352 ms mais recentes do ESP-WROOM-32. Esses números alternativos não foram silenciosamente combinados.

## Contabilidade de bytes e overhead

O notebook exporta, para cada publicação, uma decomposição fechada por esta identidade:

`bytes no meio = payload da aplicação + overhead criptográfico total + overhead não criptográfico de protocolo + retransmissões`

O overhead criptográfico total é a soma de `protected_message_bytes − application_payload_bytes` com os bytes do handshake. O overhead não criptográfico soma controle MQTT, TCP/IPv4 e enlace Wi-Fi. As retransmissões são a diferença entre os bytes-base e os bytes esperados após a aplicação da perda configurada ou medida. O fator de amplificação é `bytes no meio / payload da aplicação`.

Esses valores têm proveniência `configured`: são calculados pelos tamanhos de algoritmos e pelo modelo MQTT/TCP/IPv4/Wi-Fi. Eles não são captura de pacotes, medição de tráfego do ESP32 ou medição Mininet. O notebook valida que o erro da identidade contábil é inferior a `1e-8 B` e apresenta separadamente payload, expansão criptográfica da mensagem, handshake, camadas de protocolo e retransmissões.

## Reconexão Wi-Fi

O estudo HotNets 2019 mediu, no trilho limpo de 3,3 V de um ESP32 a 80 MHz:

- 238,2 mJ para acordar de deep sleep, inicializar, associar/WPA2, obter rede por DHCP/ARP e transmitir uma mensagem;
- 19,8 mJ para transmitir já associado em Wi-Fi power-save.

O valor usado como sobrecusto de reconexão é a diferença derivada:

`238,2 mJ − 19,8 mJ = 218,4 mJ`.

O evento `wifi_reconnect_initialization_proxy` aplica 218,4 mJ como hipótese incremental no trilho de 3,3 V. A duração de 1,6 s é estimativa visual separada. O escopo agrega inicialização, associação/WPA2, DHCP/ARP e mensagem, podendo sobrepor estados detalhados. Sua proveniência é `literature_derived_proxy`; não é energia medida isoladamente da associação. Modelos `state_based_vit` e `disabled_for_sensitivity`, além de multiplicadores configurados 0,5×/1,0×/1,5×, permanecem separados de qualquer intervalo empírico.

As esperas de resposta não usam mais um piso arbitrário de 50 ms. Quando o Mininet-WiFi produz respostas, o notebook usa RTT e perda com proveniência `measured`; a banda definida pelo `tc` permanece `configured`. A falha observada tinha perda reconhecida, mas nenhum RTT, padrão compatível com zero respostas ao ping. Como `default_loss` já era 0%, não foi inventada outra taxa de perda. A geometria anterior colocava `iot_1` a aproximadamente 78,3 m do AP, incompatível com o cenário declarado como laboratório; o perfil agora configura grade de 5 m, alcance de 30 m e distância `iot_1`–AP de aproximadamente 11,2 m. Esses valores geométricos são `configured`, não medidos. A espera de associação passou de 1 s para 2 s e, antes de nova tentativa, AP, associação Wi-Fi e encaminhamento L2 são reaplicados. O notebook tenta até três vezes e, por padrão, interrompe a campanha se continuar sem RTT, exibindo scan, comandos de associação e saída bruta. Só quando o pesquisador desativa explicitamente `REQUIRE_MININET_MEASUREMENT` os valores do YAML são usados, todos com proveniência `configured`. Isso não inclui tempo adicional de processamento do broker, pois não há medição para sustentá-lo.

## Fontes primárias

- [Espressif, ESP32 Series Datasheet v5.3](https://documentation.espressif.com/esp32_datasheet_en.pdf): faixas de corrente da CPU, TX/RX e modos de sono.
- [Bosch Sensortec, BME280 Datasheet](https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bme280-ds002.pdf): corrente média a 1 Hz, corrente em sleep e fórmula do tempo máximo de medição em modo forçado.
- [Abedi, Abari e Brecht, Wi-LE: Can WiFi Replace Bluetooth?, ACM HotNets 2019](https://web.cs.ucla.edu/~omid/Papers/Hotnets19.pdf): energia Wi-Fi medida por mensagem e metodologia elétrica.
- [Banegas et al., Quantum-Resistant Software Update Security on Low-Power Networked Embedded Devices, ACNS 2022](https://doi.org/10.1007/978-3-031-09234-3_43) e [manuscrito aberto](https://eprint.iacr.org/2021/781.pdf): Ed25519 e Dilithium no mesmo ESP32-WROOM-32 a 80 MHz.
- [Mighri, Benfarah e Meddeb, Performance Evaluation and Benchmarking of PQC CRYSTALS-Kyber on Embedded Devices, AICCSA 2024](https://doi.org/10.1109/AICCSA63423.2024.10912602): Kyber512 no ESP-WROOM-32.
- [Oryx Embedded, Crypto Benchmark on ESP32 MCU](https://www.oryx-embedded.com/benchmark/espressif/crypto-esp32.html): X25519, Ed25519, AES-GCM e SHA-256 no ESP32 a 240 MHz.
- [Espressif Component Registry, wolfSSL benchmark](https://components.espressif.com/components/wolfssl/wolfssl/versions/5.8.0/examples/wolfssl_benchmark?language=en): referência alternativa que evidencia a forte dependência da biblioteca.
- [Bürstinghaus-Steinbach et al., Post-Quantum TLS on Embedded Systems, ASIA CCS 2020](https://eprint.iacr.org/2020/308.pdf): referência alternativa de Kyber512 de rodada 1 no ESP32-PICO-KIT.
- [NIST FIPS 203, ML-KEM](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf) e [NIST FIPS 204, ML-DSA](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf): especificações finais usadas para delimitar as diferenças dos *proxies* pré-padronização.

## Limites que permanecem

- Implementação, compilador, frequência, temperatura, ponto de acesso e qualidade RF alteram os resultados.
- O perfil combina implementações heterogêneas: X25519 otimizado (`-O3`), Kyber512 sem otimização e Ed25519/Dilithium em RIOT a outra frequência. Ele não é um benchmark controlado dos algoritmos no mesmo firmware.
- A tabela AICCSA informa 1.640.163 ciclos e 6,352 ms para encapsulação. A 240 MHz, esses ciclos corresponderiam a aproximadamente 6,834 ms; o perfil preserva o tempo publicado, mas registra essa inconsistência como motivo adicional para tratá-lo como *proxy* provisório.
- Os cenários `inferior/central/superior` cobrem somente a faixa oficial de corrente, não toda a incerteza causada pela escolha da biblioteca e do compilador.
- O estudo Wi-Fi não usa exatamente o payload MQTT QoS 1 deste projeto.
- A campanha assume a política WiFi-DC: deep sleep e reconexão a cada publicação. O próprio estudo coloca a região de transição entre permanecer associado e reconectar perto de um minuto; portanto, a política de energia escolhida domina a autonomia. Modelar WiFi-PS exigiria outro perfil (aproximadamente 4,5 mA ocioso no estudo), não apenas desligar a reconexão enquanto se mantém deep sleep.
- Após deep sleep, a reconexão TCP e o MQTT `CONNECT/CONNACK` ainda não têm uma medição isolada neste perfil; a energia direta do estudo Wi-Fi agrega várias etapas de inicialização e rede.
- O BME280 de 3,6 µA a 1 Hz é uma corrente média de ciclo, e o datasheet também informa 0,1 µA em sono. Em modo forçado, com oversampling `×1` para temperatura, pressão e umidade, a fórmula de tempo máximo do próprio datasheet resulta em `1,25 + 2,3 + (2,3 + 0,575) + (2,3 + 0,575) = 9,3 ms`; o perfil arredonda conservadoramente para 10 ms. Nesse estado, 0,35 mA equivalentes são derivados de `(3,6 − 0,1) µA × 1 s / 10 ms`; com uma amostra a cada 60 s, a média estimada do sensor é 0,1583 µA. É conservação de carga por amostra, não alegação de corrente ativa instantânea medida.
- Os 5 ms de despertar e 3 ms de serialização/processamento ainda são hipóteses configuráveis, identificadas como `user_configured_estimate_not_hardware_measurement`; não foram apresentados como valores medidos ou bibliográficos. Como são curtos diante da janela de reconexão Wi-Fi, têm impacto pequeno no perfil atual, mas devem entrar na análise de sensibilidade.
- Temperatura, umidade, pressão, amplitudes diárias e ruídos sintéticos descrevem apenas o workload escolhido para exercitar o simulador. Eles não representam uma distribuição ambiental validada para o laboratório do usuário e não tornam a campanha uma medição meteorológica.
- Capacidade de 2.000 mAh, fração utilizável de 80% e eficiência de 90% são hipóteses do perfil, não medições bibliográficas desta bateria específica.
- Não existe evidência para inventar distribuições. Cada célula contém 100 `paired_deterministic_workload_instances`, não amostras independentes de hardware. Cold start inclui handshake. `preexisting_session_state` exclui criação, escrita, restauração e validação por falta de parâmetros e é limite inferior, não amortização observada. Não são gerados ICs, p-valores ou testes de hipótese.

Para substituir por medições futuras, use um CSV próprio via `PQC_IOT_CALIBRATION_CSV` e mantenha em cada linha a implementação, firmware, compilador e método de medição.
# Perfis para validação cruzada com a literatura

Além dos envelopes ESP32 já existentes, a validação externa usa os seguintes
perfis nomeados:

- `perfil_esp32_atual`: alias imutável de `esp32_literatura_central.csv`.
- `perfil_cortex_m4_literatura`: mantém a linha de base ESP32 e substitui
  somente `ml_kem_encaps` pela medição Kyber512 do Cortex-M4 (3,26194 mJ e
  1.486.610,12 ciclos a 38,4 MHz). Não é um perfil Cortex-M4 completo.
- `perfil_hysecure_fpga`: usa os tempos da Tabela 3 e `E = 0,53 W × t` para
  X25519, Kyber512, EdDSA e Dilithium2. O tempo/energia ECDH é dividido entre
  `x25519_keygen` e `x25519_exchange` para não ser contado duas vezes.
- `perfil_wpan`: usa a computação ESP32 atual e aplica `gamma_comm` de
  1,10/1,15/1,20 somente à comunicação derivada do PCAP.

Os perfis externos são estudos de sensibilidade entre plataformas. Energia
FPGA, Cortex-M4 e ESP32 não deve ser apresentada como medição do mesmo hardware.
