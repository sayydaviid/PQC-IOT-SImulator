"""Write tables from completed matched-block analyses, without manual numbers."""

import csv, json
from pathlib import Path


class ContextReport:
    """Write tables from completed matched-block analyses, without manual numbers.

    Configure once, then call ``run()`` from a notebook.
    """

    @staticmethod
    def read(path):
        return list(csv.DictReader(path.open()))

    @staticmethod
    def num(value, digits=2):
        if value in (None, "", "None"):
            return "indefinido"
        return (
            f"{float(value):,.{digits}f}".replace(",", "@")
            .replace(".", ",")
            .replace("@", ".")
        )

    @staticmethod
    def percent(row):
        v = row["median_savings_pct"]
        lo = row["savings_ci_low"]
        hi = row["savings_ci_high"]
        return f"{ContextReport.num(v)}% [{ContextReport.num(lo)}; {ContextReport.num(hi)}]"

    def __init__(self, *, analysis, output):
        self.analysis = Path(analysis) if analysis is not None else None
        self.output = Path(output) if output is not None else None

    def run(self):
        args = self
        data = args.analysis
        audit = json.loads((data / "audit.json").read_text())
        if audit["status"] != "PASS" or not audit.get("amortization_cases"):
            raise ValueError("requires both completed experiments")
        chain = ContextReport.read(data / "cadeias_custos_absolutos.csv")
        cp = ContextReport.read(data / "cadeias_comparacoes_mesma_repeticao.csv")
        amort = ContextReport.read(data / "amortizacao_custos_absolutos.csv")
        amp = ContextReport.read(data / "amortizacao_comparacoes_mesma_repeticao.csv")
        names = {"classical": "Clássico", "hybrid": "Híbrido", "pqc": "Pós-quântico"}
        cl = {
            (r["restart_fraction"], r["profile"], r["include_root"], r["treatment"]): r
            for r in chain
        }
        cc = {
            (r["restart_fraction"], r["profile"], r["include_root"], r["treatment"]): r
            for r in cp
        }
        al = {
            (r["recovery"], r["batch_size"], r["profile"], r["treatment"]): r
            for r in amort
        }
        ac = {
            (r["recovery"], r["batch_size"], r["profile"], r["treatment"]): r
            for r in amp
        }
        lines = [
            "# Custo da perda de contexto, cadeias e leituras por conexão",
            "",
            "Os novos experimentos separam o custo dos mecanismos conhecidos das condições em que eles são utilizados. A comparação principal investiga o efeito de retirar a raiz da transmissão, mantendo-a confiável. A comparação de amortização mantém o mesmo trabalho da aplicação e varia quantas leituras compartilham uma conexão.",
            "",
            "O perfil clássico usa X25519 e ECDSA P-256; o híbrido usa X25519MLKEM768 e ECDSA P-256; o pós-quântico usa X25519MLKEM768 e ML-DSA-44. Todos mantêm TLS 1.3, autenticação mútua, AES-256-GCM/SHA-384 e 0-RTT desabilitado. Dentro de cada experimento, aplicação, payload e agenda de falhas são mantidos entre os comparadores do bloco.",
            "",
            f"Foram concluídas {audit['chain_cases']} execuções na comparação das cadeias, com {audit['chain_readings']} leituras lógicas e {audit['chain_confirmed']} confirmações. A comparação de amortização concluiu {audit['amortization_cases']} execuções, {audit['amortization_readings']} leituras e {audit['amortization_confirmed']} confirmações. Efeitos duplicados com deduplicação ativa: {audit['chain_duplicate_effects']} e {audit['amortization_duplicate_effects']}, respectivamente.",
            "",
            "Cada comparação utiliza dez blocos. As tabelas apresentam medianas dos custos absolutos e medianas das reduções calculadas dentro da mesma repetição, frente ao completo do mesmo perfil e condição. Valores negativos de economia representam aumento de custo. Intervalos de 95% são bootstrap exploratórios por configuração; as leituras não são repetições independentes.",
            "",
            "## Cadeias transmitidas",
            "",
            "Os dois participantes mantêm a CA raiz no armazenamento de confiança. A transmissão varia entre folha e raiz ou apenas folha, com as mesmas credenciais no bloco e autenticação mútua verificada. O payload tem 31 bytes. Há nove leituras por execução, das quais oito são elegíveis às falhas. As frequências de reinício e de supressão da primeira confirmação são iguais nos três cenários apresentados: 0%, 25% e 100%. Não se trata da repetição de toda a grade anterior de frequências independentes. Nas tabelas, contexto perdido e contexto preservado nomeiam as políticas da chave dos tickets após reinício; quando não há reinício, ambas conservam o contexto durante a execução.",
            "",
            "Bytes incluem todas as tentativas e encerramentos IPv4 observados no servidor. A captura não representa todos os quadros Wi-Fi. A perda de pacotes configurada é 0%, com atraso de 2 ms por direção.",
            "",
            "| Frequência das duas falhas | Perfil | Cadeia enviada | Completo: bytes/leitura | Contexto perdido: bytes/leitura | Contexto preservado: bytes/leitura |",
            "|---|---|---|---:|---:|---:|",
        ]
        for fraction in ["0", "0.25", "1"]:
            for p in names:
                for root in ["1", "0"]:
                    key = (fraction, p, root)
                    (full, lost, kept) = [
                        cl[key + (t,)]
                        for t in ["full", "resume_volatile", "resume_preserved"]
                    ]
                    lines.append(
                        f"| {ContextReport.num(float(fraction) * 100, 0)}% | {names[p]} | {('Folha e raiz' if root == '1' else 'Apenas folha')} | {ContextReport.num(full['median_ipv4_bytes_per_confirmed_reading'])} | {ContextReport.num(lost['median_ipv4_bytes_per_confirmed_reading'])} | {ContextReport.num(kept['median_ipv4_bytes_per_confirmed_reading'])} |"
                    )
        lines += [
            "",
            "| Frequência das duas falhas | Perfil | Cadeia enviada | Economia: contexto perdido | Economia: contexto preservado |",
            "|---|---|---|---:|---:|",
        ]
        for fraction in ["0", "0.25", "1"]:
            for p in names:
                for root in ["1", "0"]:
                    k = (fraction, p, root)
                    lines.append(
                        f"| {ContextReport.num(float(fraction) * 100, 0)}% | {names[p]} | {('Folha e raiz' if root == '1' else 'Apenas folha')} | {ContextReport.percent(cc[k + ('resume_volatile',)])} | {ContextReport.percent(cc[k + ('resume_preserved',)])} |"
                    )
        lines += [
            "",
            "### Tempo de recuperação com ambas as falhas em 100%",
            "",
            "O tempo por leitura divide o intervalo até a última confirmação pelo número de leituras da execução. Inclui processos, reinícios previstos e reenvios. Não é uma medição isolada da latência do handshake.",
            "",
            "| Perfil | Cadeia enviada | Completo: ms/leitura | Contexto perdido: ms/leitura | Contexto preservado: ms/leitura |",
            "|---|---|---:|---:|---:|",
        ]
        for p in names:
            for root in ["1", "0"]:
                rows = [
                    cl["1", p, root, t]
                    for t in ["full", "resume_volatile", "resume_preserved"]
                ]
                lines.append(
                    f"| {names[p]} | {('Folha e raiz' if root == '1' else 'Apenas folha')} | "
                    + " | ".join(
                        (ContextReport.num(r["median_ms_per_reading"]) for r in rows)
                    )
                    + " |"
                )
        lines += [
            "",
            "## Leituras por conexão",
            "",
            "Cada execução transmite 100 leituras lógicas de 512 bytes, usando um único processo cliente. Os limites de 1, 10 ou 100 leituras por conexão se aplicam aos três tratamentos. O primeiro handshake completo é incluído, sem retirar um aquecimento do custo. Apenas os certificados folha são transmitidos; a raiz continua confiável. As conclusões sobre amortização comparam condições dentro deste experimento. Seus custos absolutos não devem ser comparados diretamente aos da matriz de cadeias, que usa outro payload e outro número de processos.",
            "",
            "No cenário de recuperação, o gateway reinicia antes da leitura de índice 50, cuja primeira confirmação é suprimida após a gravação. Uma conexão pode ser dividida por essa fronteira. O reenvio conserva o identificador, e as leituras já confirmadas não são repetidas. As condições são detalhadas em `metodo_amortizacao_20261106.md`.",
            "",
            "| Cenário | Perfil | Leituras por conexão | Completo: bytes/leitura | Contexto perdido: bytes/leitura | Contexto preservado: bytes/leitura |",
            "|---|---|---:|---:|---:|---:|",
        ]
        for recovery in ["False", "True"]:
            for p in names:
                for batch in ["1", "10", "100"]:
                    k = (recovery, batch, p)
                    (full, lost, kept) = [
                        al[k + (t,)]
                        for t in ["full", "resume_volatile", "resume_preserved"]
                    ]
                    lines.append(
                        f"| {('Recuperação' if recovery == 'True' else 'Sem falhas')} | {names[p]} | {batch} | {ContextReport.num(full['median_ipv4_bytes_per_confirmed_reading'])} | {ContextReport.num(lost['median_ipv4_bytes_per_confirmed_reading'])} | {ContextReport.num(kept['median_ipv4_bytes_per_confirmed_reading'])} |"
                    )
        lines += [
            "",
            "| Cenário | Perfil | Leituras por conexão | Economia: contexto perdido | Economia: contexto preservado |",
            "|---|---|---:|---:|---:|",
        ]
        for recovery in ["False", "True"]:
            for p in names:
                for batch in ["1", "10", "100"]:
                    k = (recovery, batch, p)
                    lines.append(
                        f"| {('Recuperação' if recovery == 'True' else 'Sem falhas')} | {names[p]} | {batch} | {ContextReport.percent(ac[k + ('resume_volatile',)])} | {ContextReport.percent(ac[k + ('resume_preserved',)])} |"
                    )
        lines += [
            "",
            "### Tempo e número de conexões no perfil pós-quântico",
            "",
            "| Cenário | Leituras por conexão | Tratamento | ms/leitura | Handshakes completos | Handshakes retomados |",
            "|---|---:|---|---:|---:|---:|",
        ]
        treatment_names = {
            "full": "Completo",
            "resume_volatile": "Contexto perdido",
            "resume_preserved": "Contexto preservado",
        }
        for recovery in ["False", "True"]:
            for batch in ["1", "10", "100"]:
                for t in treatment_names:
                    r = al[recovery, batch, "pqc", t]
                    lines.append(
                        f"| {('Recuperação' if recovery == 'True' else 'Sem falhas')} | {batch} | {treatment_names[t]} | {ContextReport.num(r['median_ms_per_reading'])} | {ContextReport.num(r['median_full_handshakes'], 0)} | {ContextReport.num(r['median_resumed_handshakes'], 0)} |"
                    )
        lines += [
            "",
            "Os tempos e as contagens de handshakes estão nas tabelas de dados. A redução de bytes não demonstra, por si só, superioridade temporal geral. O custo inclui enquadramento, confirmações, marcador de fim de grupo e encerramentos; não é o tamanho isolado do handshake.",
            "",
            "## Verificações complementares",
            "",
            "- O tamanho dos tickets e o certificado do cliente incorporado ao estado estão documentados em `diagnostico_tickets_20261106.md`.",
            "- As 100 verificações do componente de persistência, as 30 verificações adicionais do gateway TLS, o nonce do checkpoint e a identificação do dispositivo estão em `verificacoes_persistencia_checkpoint_20261106.md`.",
            "- As auditorias confrontam o ClientHello capturado com o medido na biblioteca e verificam as cadeias em ambos os sentidos, os tickets e os registros de aplicação.",
            "",
            "São dez blocos, um sensor emulado e um host compartilhado. Os efeitos avaliados são registros no banco. Não foram medidos sensores físicos, cortes de energia ou execução única de atuadores. O banco mantém identificadores e resumos, não o payload integral. Os resultados anteriores permanecem preservados.",
        ]
        args.output.write_text("\n".join(lines) + "\n")
        print(args.output)
        return args.output
