# Comparação da reprodução com o artigo

Dados novos: `/workspace/results/retomada/20261111T040027423734Z`.

| Resultado | Referência | Novo | Diferença | Mesmo arredondamento do artigo |
|---|---:|---:|---:|---|
| Cadeias: completo PQC sem raiz, falhas 100% | 41463.66667 | 41342.11111 | -121.55556 | Não |
| Cadeias: contexto perdido PQC sem raiz, falhas 100% | 49645.00000 | 49535.00000 | -110.00000 | Não |
| Cadeias: contexto preservado PQC sem raiz, falhas 100% | 17504.77778 | 17509.44444 | +4.66667 | Não |
| Economia PQC, raiz=0, resume_volatile, falhas 100% | -19.69512 | -19.82145 | -0.12634 | Não |
| Economia PQC, raiz=0, resume_preserved, falhas 100% | 57.78982 | 57.64850 | -0.14131 | Não |
| Economia PQC, raiz=1, resume_volatile, falhas 100% | -14.18137 | -14.28945 | -0.10808 | Não |
| Economia PQC, raiz=1, resume_preserved, falhas 100% | 67.89079 | 67.83913 | -0.05167 | Não |
| Amortização PQC, recuperação=False, limite=1, resume_preserved | 58.50373 | 58.30456 | -0.19918 | Não |
| Amortização PQC, recuperação=False, limite=10, resume_preserved | 36.78992 | 37.10408 | +0.31416 | Não |
| Amortização PQC, recuperação=False, limite=100, resume_preserved | 0.00000 | 0.00000 | +0.00000 | Sim |
| Amortização PQC, recuperação=True, limite=100, resume_volatile | -5.11867 | -5.30301 | -0.18434 | Não |
| Amortização PQC, recuperação=True, limite=100, resume_preserved | 15.10511 | 15.40115 | +0.29604 | Não |

| Propriedade observada | Reproduzida |
|---|---|
| chain_order_classical_root0 | Sim |
| chain_order_classical_root1 | Sim |
| chain_order_hybrid_root0 | Sim |
| chain_order_hybrid_root1 | Sim |
| chain_order_pqc_root0 | Sim |
| chain_order_pqc_root1 | Sim |
| pqc_full_cost_decreases_with_connection_sharing | Sim |
| no_failure_100_readings_one_full_full | Sim |
| recovery_100_readings_handshakes_full | Sim |
| no_failure_100_readings_one_full_resume_volatile | Sim |
| recovery_100_readings_handshakes_resume_volatile | Sim |
| no_failure_100_readings_one_full_resume_preserved | Sim |
| recovery_100_readings_handshakes_resume_preserved | Sim |
| zero_duplicate_effects_with_deduplication | Sim |
| 2700_duplicate_effects_without_suppression | Sim |
| 16200_confirmed_main_readings | Sim |
| 58860_confirmed_complementary_readings | Sim |
| zero_duplicates_complementary_readings | Sim |
| ml_dsa_client_increases_certificate_state_and_ticket | Sim |

Numerical differences are reported without a post-hoc acceptance tolerance; timing and IPv4 traffic are measurements, not fixed constants.

As diferenças de todas as condições e métricas estão em `comparacao_completa.csv`. Os dados históricos não foram substituídos.
