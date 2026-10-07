"""A irradiação diária da NASA POWER na página da usina (07/10/2026): a série dos últimos 30 dias, o mês até agora e a geometria do
gráfico, tudo puro (sem Flask, sem rede). Quem busca a série é `fontes.nasa_power` (pelo cache de `leitura.irradiacao`); quem
escreve os textos é o `visao.montar_usina`.

Regras que custaram a medir (ao vivo, 07/10/2026): a NASA atrasa uns 5 dias (o último dia publicado era 02/10), e o que ainda não
saiu vem como -999, que aqui é `None`, NUNCA zero. Também vem um -999 isolado no meio da série (07/09): é buraco, e fica buraco
(a linha do gráfico se parte, e a soma do mês diz quantos dias faltaram). O mês até agora soma só os dias publicados, dizendo até
que dia a NASA já publicou.

Gráfico: o desenho aprovado (Irradiacao.dc.html), um SVG de 620 x 270 com as grades em 0, 2, 4, 6... kWh/m², feito no servidor. O
eixo vai até o múltiplo de 2 acima do maior valor (no mínimo 6), e o dia que a NASA ainda não publicou aparece como uma faixa, não
como queda a zero.
"""
import math
from datetime import date, timedelta

DIAS_DO_GRAFICO = 30
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")

# a caixa do desenho: o zero em y=230, o topo (a última grade) em y=20, os dias de x=40 a x=610 num viewBox de 620 x 270
LARGURA, ALTURA = 620, 270
X0, X1, Y0, Y1 = 40.0, 610.0, 230.0, 20.0
TOPO_MINIMO = 6
PASSO_DA_GRADE = 2


def nome_do_mes(d: date) -> str:
    return f"{MESES[d.month - 1]}/{d.year}"


def dd_mm(d: date) -> str:
    return d.strftime("%d/%m")


def ultimos_dias(dias: dict, hoje: date, n: int = DIAS_DO_GRAFICO) -> list:
    """[(data, valor ou None)] dos `n` dias que terminam em `hoje`, do mais antigo para o mais novo. Dia que a série não tem vem
    como None (não publicado ou fora da janela lida)."""
    return [(d, dias.get(d)) for d in (hoje - timedelta(days=n - 1 - i) for i in range(n))]


def mes_ate_agora(dias: dict, hoje: date) -> dict:
    """O mês de `hoje` até o último dia que a NASA publicou: {"mes": "outubro/2026", "soma": kWh/m² ou None, "n": dias somados,
    "ate": última data publicada no mês ou None, "buracos": [datas sem valor ANTES do último publicado]}. A soma é só dos dias
    publicados (dia sem valor nunca entra como zero); os buracos dizem o que a soma não tem. Sem nenhum dia do mês publicado,
    `soma` e `ate` são None."""
    primeiro = hoje.replace(day=1)
    do_mes = [(primeiro + timedelta(days=i), None) for i in range((hoje - primeiro).days + 1)]
    do_mes = [(d, dias.get(d)) for d, _ in do_mes]
    publicados = [(d, v) for d, v in do_mes if v is not None]
    ate = publicados[-1][0] if publicados else None
    return {"mes": nome_do_mes(hoje), "soma": sum(v for _, v in publicados) if publicados else None, "n": len(publicados),
            "ate": ate, "buracos": [d for d, v in do_mes if v is None and ate is not None and d < ate]}


# O passo e a escala primeiro, e só depois a multiplicação: é a ordem da conta do desenho aprovado (x = 40 + i * 19, y = 230 - v * 35),
# e a outra ordem muda a casa decimal nos valores que caem bem no meio.
def _x(i: int, n: int) -> float:
    return round(X0 + i * ((X1 - X0) / (n - 1)), 1)


def _y(v: float, topo: int) -> float:
    return round(Y0 - v * ((Y0 - Y1) / topo), 1)


def _corridas(serie: list, n: int, topo: int) -> tuple:
    """Os trechos de dias seguidos com valor, como ([[(x, y), ...], ...] com 2 ou mais pontos, [(x, y), ...] dos dias isolados)."""
    trechos, isolados, atual = [], [], []

    def fecha():
        if len(atual) >= 2:
            trechos.append(list(atual))
        elif len(atual) == 1:
            isolados.append(atual[0])
        atual.clear()

    for i, (_, v) in enumerate(serie):
        if v is None:
            fecha()
        else:
            atual.append((_x(i, n), _y(v, topo)))
    fecha()
    return trechos, isolados


def grafico(serie: list, publicado_ate, *, etm: list | None = None) -> dict:
    """A geometria do SVG (só números e textos curtos; o template os escreve sem conta nenhuma). `serie`: o `ultimos_dias` da NASA;
    `publicado_ate`: o último dia que ela publicou (ou None); `etm`: uma série igual com o GHI medido da usina, se houver (a linha
    da ETM vai por cima). Devolve {"viewbox", "grades": [{"y", "rotulo"}], "rotulos_x": [{"x", "texto", "ancora"}], "nasa": {"trechos":
    ["x,y x,y ..."], "isolados": [(x, y)]}, "etm": o mesmo ou None, "faixa": {"x", "largura", "y", "altura"} ou None, "topo",
    "descricao"}."""
    n = len(serie)
    if n < 2:
        raise ValueError("o gráfico precisa de pelo menos dois dias")
    maior = max([v for _, v in serie if v is not None] + [v for _, v in (etm or []) if v is not None] + [0.0])
    topo = max(TOPO_MINIMO, math.ceil(maior / PASSO_DA_GRADE) * PASSO_DA_GRADE)
    grades = [{"y": _y(g, topo), "rotulo": str(g)} for g in range(0, topo + 1, PASSO_DA_GRADE)]
    meio = (n - 1) // 2
    rotulos_x = [{"x": _x(i, n), "texto": dd_mm(serie[i][0]), "ancora": a}
                 for i, a in ((0, "start"), (meio, "middle"), (n - 1, "end"))]

    def desenho(s):
        trechos, isolados = _corridas(s, n, topo)
        return {"trechos": [" ".join(f"{x},{y}" for x, y in t) for t in trechos], "isolados": isolados}

    passo = (X1 - X0) / (n - 1)
    primeiro_sem = next((i for i, (d, _) in enumerate(serie) if publicado_ate is None or d > publicado_ate), None)
    faixa = None
    if primeiro_sem is not None:
        x = max(X0, round(X0 + primeiro_sem * passo - passo / 2, 1))
        faixa = {"x": x, "largura": round(LARGURA - 10 - x, 1), "y": Y1, "altura": Y0 - Y1}
    primeiro, ultimo = serie[0][0], serie[-1][0]
    descricao = (f"GHI diário de {dd_mm(primeiro)} a {dd_mm(ultimo)}, NASA POWER, em kWh/m²; " +
                 (f"publicado até {dd_mm(publicado_ate)}" if publicado_ate is not None else "nenhum dia publicado nesta janela"))
    return {"viewbox": f"0 0 {LARGURA} {ALTURA}", "grades": grades, "rotulos_x": rotulos_x, "nasa": desenho(serie),
            "etm": desenho(etm) if etm else None, "faixa": faixa, "topo": topo, "descricao": descricao}
