# Comparação da reprodução com o artigo

Dados novos: `/workspace/results/reproducao_artigo_20261107_v2`.

| Resultado | Referência | Novo | Diferença | Mesmo arredondamento do artigo |
|---|---:|---:|---:|---|
| Cadeias: completo PQC sem raiz, falhas 100% | 41463.66667 | 41463.66667 | +0.00000 | Sim |
| Cadeias: contexto perdido PQC sem raiz, falhas 100% | 49645.00000 | 49659.44444 | +14.44444 | Não |
| Cadeias: contexto preservado PQC sem raiz, falhas 100% | 17504.77778 | 17525.00000 | +20.22222 | Não |
| Economia PQC, raiz=0, resume_volatile, falhas 100% | -19.69512 | -19.74967 | -0.05455 | Não |
| Economia PQC, raiz=0, resume_preserved, falhas 100% | 57.78982 | 57.73985 | -0.04997 | Não |
| Economia PQC, raiz=1, resume_volatile, falhas 100% | -14.18137 | -14.23081 | -0.04943 | Não |
| Economia PQC, raiz=1, resume_preserved, falhas 100% | 67.89079 | 67.88925 | -0.00155 | Sim |
| Amortização PQC, recuperação=False, limite=1, resume_preserved | 58.50373 | 58.49762 | -0.00611 | Sim |
| Amortização PQC, recuperação=False, limite=10, resume_preserved | 36.78992 | 36.82948 | +0.03956 | Não |
| Amortização PQC, recuperação=False, limite=100, resume_preserved | 0.00000 | 0.03843 | +0.03843 | Não |
| Amortização PQC, recuperação=True, limite=100, resume_volatile | -5.11867 | -5.13170 | -0.01303 | Não |
| Amortização PQC, recuperação=True, limite=100, resume_preserved | 15.10511 | 15.07611 | -0.02900 | Não |

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
