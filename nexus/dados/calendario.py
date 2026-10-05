"""A dimensão de data (o calendário) e os feriados locais.

Antes de 05/10/2026 cada tela calculava a semana ISO, o dia útil e o mês por conta própria, e os feriados moravam só nos
insumos do PCM. Aqui o dia vira uma linha com ID (`data_id` = AAAAMMDD, inteiro): todo fato aponta para ele e herda
semana, mês e feriado sem conta nova.

- Feriado NACIONAL entra na própria linha do dia (vale para todo mundo: tira o dia útil).
- Estadual e municipal valem só para a usina daquele lugar: vão para `feriados_locais` (data_id, tipo, UF, município),
  que se cruza com a usina pela UF e pela cidade do cadastro. Não tiram o dia útil da linha do dia.
- Fonte dos feriados: os insumos da programação do PCM (o mesmo arquivo que o motor lê), que o PCM mantém. O PCM só
  tem o ano corrente (2026, em 05/10/2026): nos outros anos os nacionais saem da MESMA lista, calculada (os móveis pela
  Páscoa), e a coluna `feriado_fonte` diz qual valeu. Estaduais e municipais de outro ano não existem: o PCM tem de
  cadastrar.
"""
from datetime import date, timedelta

DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
CAB_DIA = ["data_id", "data", "ano", "mes", "dia", "dia_semana", "nome_dia", "semana_iso", "ano_mes", "trimestre",
           "fim_de_semana", "feriado_nacional", "feriado_fonte", "dia_util"]
CAB_FERIADO = ["data_id", "data", "tipo", "uf", "municipio", "nome"]
INICIO, FIM = date(2025, 1, 1), date(2027, 12, 31)


def data_id(d: date) -> int:
    return d.year * 10000 + d.month * 100 + d.day


def _data(v) -> date | None:
    if isinstance(v, dict):
        v = v.get("$dt")
    try:
        return date.fromisoformat(str(v or "")[:10])
    except ValueError:
        return None


def _pascoa(ano: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher, calendário gregoriano)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * l) // 433
    mes = (h + l - 7 * m + 90) // 25
    return date(ano, mes, (h + l - 7 * m + 33 * mes + 19) % 32)


def nacionais_calculados(ano: int) -> dict:
    """A lista de nacionais que o PCM usa (12 em 2026), para os anos que ele ainda não cadastrou."""
    p = _pascoa(ano)
    return {date(ano, 1, 1): "Confraternização Universal", p - timedelta(days=47): "Carnaval",
            p - timedelta(days=2): "Paixão de Cristo", date(ano, 4, 21): "Tiradentes", date(ano, 5, 1): "Dia do Trabalho",
            p + timedelta(days=60): "Corpus Christi (ponto facultativo)", date(ano, 9, 7): "Independência do Brasil",
            date(ano, 10, 12): "Nossa Senhora Aparecida", date(ano, 11, 2): "Finados",
            date(ano, 11, 15): "Proclamação da República", date(ano, 11, 20): "Dia da Consciência Negra",
            date(ano, 12, 25): "Natal"}


def feriados(insumos_feriados: dict | None) -> tuple[dict, list]:
    """({data: nome} dos NACIONAIS, [linhas de feriados_locais]) a partir dos feriados dos insumos do PCM."""
    nac, locais = {}, []
    f = insumos_feriados or {}
    for r in list(f.get("gerais") or []) + list(f.get("municipais") or []):
        d = _data(r.get("data"))
        if not d:
            continue
        tipo = str(r.get("tipo") or "").strip().upper()
        nome = str(r.get("feriado") or "").strip()
        if tipo == "NACIONAL":
            nac.setdefault(d, nome)
            continue                       # o nacional vai na linha do dia, não aqui
        locais.append([data_id(d), d.isoformat(), tipo or None, str(r.get("estado") or "").strip().upper() or None,
                       str(r.get("municipio") or "").strip() or None, nome or None])
    locais.sort(key=lambda l: (l[0], l[2] or "", l[3] or "", l[4] or ""))
    return nac, locais


def dias(nacionais: dict | None = None, inicio: date = INICIO, fim: date = FIM) -> list[list]:
    """Uma linha por dia. Ano que o PCM cadastrou vale a lista dele; o resto, a calculada."""
    nacionais = nacionais or {}
    anos_pcm = {d.year for d in nacionais}
    calc = {}
    for ano in range(inicio.year, fim.year + 1):
        if ano not in anos_pcm:
            calc.update(nacionais_calculados(ano))
    out, d = [], inicio
    while d <= fim:
        ano_iso, sem, dsem = d.isocalendar()
        fer = nacionais.get(d) if d.year in anos_pcm else calc.get(d)
        fonte = None if not fer else ("PCM" if d.year in anos_pcm else "calculado")
        fds = dsem >= 6
        out.append([data_id(d), d.isoformat(), d.year, d.month, d.day, dsem, DIAS[dsem - 1], f"{ano_iso}-W{sem:02d}",
                    f"{d.year}-{d.month:02d}", (d.month - 1) // 3 + 1, "sim" if fds else "não", fer, fonte,
                    "sim" if not fds and not fer else "não"])
        d += timedelta(days=1)
    return out
