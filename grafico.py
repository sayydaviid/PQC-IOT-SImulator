from pathlib import Path
import csv
import html


CSV_ENTRADA = Path("comparativo_geral.csv")
PASTA_SAIDA = Path("graficos_linha")

MODOS = [
    "pqc",
    "hybrid",
    "classical"
]

CORES = {
    "pqc": "#2563eb",
    "hybrid": "#f97316",
    "classical": "#16a34a"
}

METRICAS = [
    {
        "coluna": "crypto_time_seconds",
        "titulo": "Tempo criptografico",
        "unidade": "s"
    },
    {
        "coluna": "duration_seconds",
        "titulo": "Duracao total da transmissao",
        "unidade": "s"
    },
    {
        "coluna": "crypto_energy_cost",
        "titulo": "Energia da criptografia",
        "unidade": "energia"
    },
    {
        "coluna": "total_energy_consumed",
        "titulo": "Energia total consumida",
        "unidade": "energia"
    },
    {
        "coluna": "protected_payload_size_bytes",
        "titulo": "Tamanho do payload protegido",
        "unidade": "bytes"
    },
    {
        "coluna": "crypto_overhead_bytes",
        "titulo": "Overhead criptografico",
        "unidade": "bytes"
    },
    {
        "coluna": "link_latency_ms",
        "titulo": "Latencia do link",
        "unidade": "ms"
    },
    {
        "coluna": "link_rtt_avg_ms",
        "titulo": "RTT medio",
        "unidade": "ms"
    }
]


def numero(valor):
    if valor is None:
        return None

    texto = str(valor).strip()

    if texto == "":
        return None

    try:
        return float(texto)
    except ValueError:
        return None


def ler_csv(caminho):
    if not caminho.exists():
        raise FileNotFoundError(f"CSV nao encontrado: {caminho}")

    linhas = []

    with open(caminho, "r", encoding="utf-8", newline="") as arquivo:
        leitor = csv.DictReader(arquivo)

        for linha in leitor:
            linhas.append(linha)

    if not linhas:
        raise RuntimeError("CSV vazio.")

    return linhas


def agrupar_por_modo(linhas, coluna_metrica):
    dados = {
        modo: []
        for modo in MODOS
    }

    for linha in linhas:
        modo = str(linha.get("crypto_mode", "")).strip()

        if modo not in dados:
            continue

        run = numero(linha.get("run"))
        valor = numero(linha.get(coluna_metrica))

        if run is None or valor is None:
            continue

        dados[modo].append((run, valor))

    for modo in dados:
        dados[modo].sort(key=lambda item: item[0])

    return dados


def escala(valor, entrada_min, entrada_max, saida_min, saida_max):
    if entrada_max == entrada_min:
        return (saida_min + saida_max) / 2

    proporcao = (valor - entrada_min) / (entrada_max - entrada_min)

    return saida_min + proporcao * (saida_max - saida_min)


def formatar_valor(valor):
    if valor is None:
        return ""

    if abs(valor) >= 1000:
        return f"{valor:.0f}"

    if abs(valor) >= 10:
        return f"{valor:.3f}"

    if abs(valor) >= 1:
        return f"{valor:.4f}"

    return f"{valor:.6f}"


def gerar_grafico_svg(dados, titulo, unidade, caminho_saida, largura=1100, altura=620):
    margem_esquerda = 90
    margem_direita = 40
    margem_topo = 80
    margem_baixo = 90

    grafico_x1 = margem_esquerda
    grafico_y1 = margem_topo
    grafico_x2 = largura - margem_direita
    grafico_y2 = altura - margem_baixo

    todos_pontos = []

    for pontos in dados.values():
        todos_pontos.extend(pontos)

    if not todos_pontos:
        print(f"[AVISO] Sem dados para: {titulo}")
        return

    xs = [ponto[0] for ponto in todos_pontos]
    ys = [ponto[1] for ponto in todos_pontos]

    x_min = min(xs)
    x_max = max(xs)
    y_min = min(ys)
    y_max = max(ys)

    if y_min == y_max:
        margem_y = abs(y_min) * 0.1 if y_min != 0 else 1
        y_min = y_min - margem_y
        y_max = y_max + margem_y
    else:
        margem_y = (y_max - y_min) * 0.12
        y_min = y_min - margem_y
        y_max = y_max + margem_y

    partes = []

    partes.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{largura}" height="{altura}" viewBox="0 0 {largura} {altura}">')
    partes.append('<rect width="100%" height="100%" fill="#ffffff"/>')

    partes.append(f'<text x="{largura / 2}" y="38" text-anchor="middle" font-family="Arial" font-size="24" font-weight="700" fill="#111827">{html.escape(titulo)}</text>')
    partes.append(f'<text x="{largura / 2}" y="62" text-anchor="middle" font-family="Arial" font-size="14" fill="#4b5563">Comparacao por execucao</text>')

    for i in range(6):
        y = grafico_y1 + i * ((grafico_y2 - grafico_y1) / 5)
        valor_y = escala(y, grafico_y2, grafico_y1, y_min, y_max)

        partes.append(f'<line x1="{grafico_x1}" y1="{y}" x2="{grafico_x2}" y2="{y}" stroke="#e5e7eb" stroke-width="1"/>')
        partes.append(f'<text x="{grafico_x1 - 12}" y="{y + 4}" text-anchor="end" font-family="Arial" font-size="12" fill="#374151">{formatar_valor(valor_y)}</text>')

    total_ticks_x = 6

    for i in range(total_ticks_x):
        if total_ticks_x == 1:
            valor_x = x_min
        else:
            valor_x = x_min + i * ((x_max - x_min) / (total_ticks_x - 1))

        x = escala(valor_x, x_min, x_max, grafico_x1, grafico_x2)

        partes.append(f'<line x1="{x}" y1="{grafico_y1}" x2="{x}" y2="{grafico_y2}" stroke="#f3f4f6" stroke-width="1"/>')
        partes.append(f'<text x="{x}" y="{grafico_y2 + 24}" text-anchor="middle" font-family="Arial" font-size="12" fill="#374151">{int(round(valor_x))}</text>')

    partes.append(f'<line x1="{grafico_x1}" y1="{grafico_y2}" x2="{grafico_x2}" y2="{grafico_y2}" stroke="#111827" stroke-width="1.5"/>')
    partes.append(f'<line x1="{grafico_x1}" y1="{grafico_y1}" x2="{grafico_x1}" y2="{grafico_y2}" stroke="#111827" stroke-width="1.5"/>')

    partes.append(f'<text x="{(grafico_x1 + grafico_x2) / 2}" y="{altura - 30}" text-anchor="middle" font-family="Arial" font-size="14" fill="#111827">Run</text>')
    partes.append(f'<text x="24" y="{(grafico_y1 + grafico_y2) / 2}" text-anchor="middle" font-family="Arial" font-size="14" fill="#111827" transform="rotate(-90 24 {(grafico_y1 + grafico_y2) / 2})">{html.escape(unidade)}</text>')

    for modo in MODOS:
        pontos = dados.get(modo, [])

        if not pontos:
            continue

        coordenadas = []

        for run, valor in pontos:
            x = escala(run, x_min, x_max, grafico_x1, grafico_x2)
            y = escala(valor, y_min, y_max, grafico_y2, grafico_y1)
            coordenadas.append((x, y, run, valor))

        pontos_polyline = " ".join(
            f"{x:.2f},{y:.2f}"
            for x, y, _, _ in coordenadas
        )

        cor = CORES.get(modo, "#000000")

        partes.append(f'<polyline points="{pontos_polyline}" fill="none" stroke="{cor}" stroke-width="3"/>')

        for x, y, run, valor in coordenadas:
            partes.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="{cor}">')
            partes.append(f'<title>{html.escape(modo)} run {int(run)}: {formatar_valor(valor)}</title>')
            partes.append('</circle>')

    legenda_x = grafico_x1
    legenda_y = altura - 62

    for indice, modo in enumerate(MODOS):
        x = legenda_x + indice * 180
        y = legenda_y
        cor = CORES.get(modo, "#000000")

        partes.append(f'<line x1="{x}" y1="{y}" x2="{x + 32}" y2="{y}" stroke="{cor}" stroke-width="4"/>')
        partes.append(f'<circle cx="{x + 16}" cy="{y}" r="4" fill="{cor}"/>')
        partes.append(f'<text x="{x + 42}" y="{y + 5}" font-family="Arial" font-size="14" fill="#111827">{html.escape(modo)}</text>')

    partes.append('</svg>')

    caminho_saida.parent.mkdir(parents=True, exist_ok=True)

    with open(caminho_saida, "w", encoding="utf-8") as arquivo:
        arquivo.write("\n".join(partes))

    print(f"[OK] Grafico gerado: {caminho_saida}")


def gerar_dashboard_svg(linhas):
    largura_total = 1600
    altura_total = 2100

    colunas = 2
    largura_card = 760
    altura_card = 460
    espaco_x = 50
    espaco_y = 60
    margem_x = 35
    margem_y = 90

    partes = []
    partes.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{largura_total}" height="{altura_total}" viewBox="0 0 {largura_total} {altura_total}">')
    partes.append('<rect width="100%" height="100%" fill="#ffffff"/>')
    partes.append(f'<text x="{largura_total / 2}" y="45" text-anchor="middle" font-family="Arial" font-size="30" font-weight="700" fill="#111827">Dashboard comparativo de criptografia</text>')
    partes.append(f'<text x="{largura_total / 2}" y="74" text-anchor="middle" font-family="Arial" font-size="15" fill="#4b5563">PQC, hibrido e classico em graficos de linha</text>')

    for indice, metrica in enumerate(METRICAS):
        coluna = indice % colunas
        linha_grid = indice // colunas

        offset_x = margem_x + coluna * (largura_card + espaco_x)
        offset_y = margem_y + linha_grid * (altura_card + espaco_y)

        caminho_temp = PASTA_SAIDA / "_temp.svg"

        dados = agrupar_por_modo(linhas, metrica["coluna"])

        gerar_grafico_svg(
            dados=dados,
            titulo=metrica["titulo"],
            unidade=metrica["unidade"],
            caminho_saida=caminho_temp,
            largura=largura_card,
            altura=altura_card
        )

        with open(caminho_temp, "r", encoding="utf-8") as arquivo:
            svg = arquivo.read()

        inicio = svg.find(">") + 1
        fim = svg.rfind("</svg>")
        conteudo = svg[inicio:fim]

        partes.append(f'<g transform="translate({offset_x},{offset_y})">')
        partes.append(f'<rect x="0" y="0" width="{largura_card}" height="{altura_card}" fill="#ffffff" stroke="#d1d5db" rx="18"/>')
        partes.append(conteudo)
        partes.append('</g>')

    partes.append('</svg>')

    caminho_dashboard = PASTA_SAIDA / "dashboard_comparativo_linhas.svg"

    with open(caminho_dashboard, "w", encoding="utf-8") as arquivo:
        arquivo.write("\n".join(partes))

    caminho_temp = PASTA_SAIDA / "_temp.svg"

    if caminho_temp.exists():
        caminho_temp.unlink()

    print(f"[OK] Dashboard gerado: {caminho_dashboard}")


def main():
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)

    linhas = ler_csv(CSV_ENTRADA)

    for metrica in METRICAS:
        dados = agrupar_por_modo(linhas, metrica["coluna"])

        gerar_grafico_svg(
            dados=dados,
            titulo=metrica["titulo"],
            unidade=metrica["unidade"],
            caminho_saida=PASTA_SAIDA / f"{metrica['coluna']}.svg"
        )

    gerar_dashboard_svg(linhas)

    print()
    print(f"Graficos salvos em: {PASTA_SAIDA.resolve()}")


if __name__ == "__main__":
    main()