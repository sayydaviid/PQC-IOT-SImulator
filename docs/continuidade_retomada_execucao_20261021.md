# Continuação administrativa da campanha em 21/10/2026

A execução `continuity_core_registered_20261018_v3` terminou sem `results.json`, com 705 casos concluídos. Os blocos 0–3 contêm as 162 configurações previstas cada (648 ensaios); o bloco 4 ficou incompleto. O último caso contém falhas de conexão `No route to host`. O processo e o contêiner já não existiam na retomada. Não há registro suficiente para atribuir a causa a suspensão, reinício do host ou outra interrupção da infraestrutura.

O desenho não mudou. O novo diretório `continuity_core_registered_20261021_v4` incorpora os quatro blocos completos e executa novamente o bloco 4 inteiro, seguido dos blocos restantes. Todos os comparadores de um bloco vêm da mesma rodada. O bloco parcial permanece no arquivo original como diagnóstico, sem contribuir para a inferência. A decisão de conservar blocos completos foi tomada antes de analisar contrastes, sem selecionar configurações pelo resultado, tempo ou sucesso de entrega.

O arquivo `experiments/continuity/run_campaign_v3.py` conserva o executor original. O executor atual acrescenta somente a opção administrativa `--resume-from`: valida desenho, hashes dos fontes experimentais e cópia do executor antigo; importa apenas blocos completos; copia os artefatos; registra manifesto original, hashes dos casos e blocos incorporados. O fluxo TLS, a aplicação, as agendas, os limites de tentativas, as medidas e os critérios permanecem iguais. Casos com orçamento de entrega esgotado também são conservados quando pertencem a um bloco completo.

A infraestrutura e as credenciais são recriadas para os blocos restantes. Há, portanto, duas sessões de execução e dois conjuntos de credenciais públicas; os contrastes continuam internos a cada bloco. Essa separação deve acompanhar a interpretação temporal. A v4 não é uma repetição independente dos 648 casos incorporados, e não deve ser somada à v3.

Comando de continuação:

```bash
docker compose -f docker-compose.yml -f experiments/continuity/compose.yml run -d \
  --name continuity-core-v4 -e PYTHONDONTWRITEBYTECODE=1 notebook \
  python3 scripts/run_continuity_campaign.py --phase core --blocks 10 --readings 9 \
  --resume-from /workspace/results/raw/continuity_core_registered_20261018_v3 \
  --output /workspace/results/raw/continuity_core_registered_20261021_v4
```

O modo desacoplado conserva o contêiner e seu código de saída para diagnosticar eventual interrupção. A campanha de perdas deve iniciar somente depois do término desta, pois compartilham a infraestrutura Mininet. O plano experimental original permanece preservado com seu hash.

## Interrupção por descarte na captura e continuação v5

A v4 terminou com código 1 após 1.453 casos concluídos. No caso `l0_b8_r0.25_a1_pqc_full_d1`, o log informa 642 pacotes capturados, 646 recebidos pelo filtro e **4 descartados pelo kernel da captura**. Esses descartes impedem tratar o PCAP como medição completa. O caso e o bloco parcial 8 ficam arquivados na v4, fora da inferência. Não se tratou de uma rejeição da hipótese nem se selecionaram resultados pelo ganho observado.

Antes de repetir o bloco, o buffer de `tcpdump` foi ampliado explicitamente para 16.384 KiB (`-B 16384`). O filtro, o modo imediato, a captura integral e o critério de zero descartes permanecem iguais. O executor v4 foi preservado em `experiments/continuity/run_campaign_v4.py`; a importação passa a aceitar os snapshots v3 e v4, verificando o hash original correspondente. Os endpoints, o módulo TLS, os limites de tentativas e as agendas não mudaram.

A v5, em `results/raw/continuity_core_registered_20261021_v5`, incorpora os oito blocos completos 0–7 (1.296 ensaios), refaz o bloco 8 por inteiro e executa o bloco 9. Os primeiros quatro blocos procedem da v3; os quatro seguintes, da v4. O manifesto guarda a cadeia de procedência e hashes de cada caso importado. Não somar as rodadas como amostras independentes. A configuração de buffer da captura difere nos dois últimos blocos; todas as capturas incluídas precisam satisfazer o mesmo critério de zero descartes.

```bash
docker compose -f docker-compose.yml -f experiments/continuity/compose.yml run -d \
  --name continuity-core-v5 -e PYTHONDONTWRITEBYTECODE=1 notebook \
  python3 scripts/run_continuity_campaign.py --phase core --blocks 10 --readings 9 \
  --resume-from /workspace/results/raw/continuity_core_registered_20261021_v4 \
  --output /workspace/results/raw/continuity_core_registered_20261021_v5
```

A fase de perdas usará o buffer ampliado e o diretório `continuity_loss_registered_20261021_v5`.
