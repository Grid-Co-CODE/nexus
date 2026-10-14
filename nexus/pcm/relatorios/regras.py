"""Regras, formato e folha comuns aos quatro relatórios do PCM (14/10/2026).

Cópia do `relatorio_diario.py` e do `relatorios_semana.py` do repositório do PCM (a referência: é o Python que gera os
relatórios arquivados e os e-mails; o `js/relatorios.js` do painel é o espelho dele no navegador). Levi, 14/10/2026:
"Quero trazer esses quatro relatórios para a plataforma, com as mesmas métricas e parâmetros e estilos".

O que mudou de propósito, e só isto:
- os números saem no formato brasileiro, como na tela Relatórios do painel (o JS): "66,8 h", "1.469 h", e o meio
  arredonda para cima (82,5% vira 83%). O Python de lá escrevia "66.8 h" e arredondava o meio para o par. A prova de
  que as contas são as mesmas roda com `modo_original()`, que volta o formato do Python, e compara a folha byte a byte
  (`ferramentas/prova_relatorios_pcm.py`);
- o rodapé diz que o Nexus gerou, e as indicações de "no painel" apontam para as telas do Nexus (`TROCAS_DE_TEXTO`).
Os números em CSS (a altura das barras) ficam no formato do Python: é CSS, não texto.
"""
import base64
import html as _html
import math
import re
import unicodedata
from contextlib import contextmanager
from datetime import date, timedelta, timezone
from pathlib import Path

META = 85.0
HH_DIA = 8.8
HORA_CORTE_MANHA = 12           # "manhã" = início programado antes disso (Recuperação da tarde)
LIN_MATINAL = 12                # linhas da lista de prioridade da Recuperação da tarde
TIPOS_NAO_PROG = ("Corretiva", "Corretiva Emergencial", "Religamento", "Religamento Remoto")
DIAS_PT = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
DIAS_KEY = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
# como resolveu o religamento: com maiúscula no diário, minúscula na semana (as duas tabelas do Python)
CAT_DIARIO = {"campo": "Em campo", "remoto": "Remoto (COS)", "queda": "Queda de energia",
              "emergencial": "Emergencial", "programado": "Programado"}
CAT_SEMANA = {"campo": "em campo", "remoto": "remoto (COS)", "queda": "queda de energia", "emergencial": "emergencial",
              "programado": "programado"}
BRT = timezone(timedelta(hours=-3))

# Onde o Nexus diz outra coisa que o Python do PCM (o resto do texto é o mesmo). A prova volta estas trocas antes de
# comparar a folha do Nexus com a do PCM.
ORIGEM = "Relatório gerado pelo Nexus · app.gridco.com.br"
TROCAS_DE_TEXTO = (
    (ORIGEM, "Relatório gerado pela plataforma PCM · pcm.gridco.com.br"),
    (" no Nexus)</span>", " no painel)</span>"),
    ("em Engenharia → Confiabilidade, com ticket", "no módulo Confiabilidade, com ticket"),
    ("no Nexus → PCM → Tarefas e OS, filtro não finalizadas", 'no painel → Semana → filtro "não finalizadas"'),
    ("Assuma tickets e justifique rolagens no Nexus.",
     "Responder este e-mail não registra nada — assuma tickets e justifique rolagens no painel."),
    ("ver ticket em Engenharia → Confiabilidade", "ver ticket no painel"),
)

_MODO = {"original": False}


@contextmanager
def modo_original():
    """Os números no formato do Python do PCM (ponto decimal, meio para o par): só para a prova byte a byte."""
    antes = _MODO["original"]
    _MODO["original"] = True
    try:
        yield
    finally:
        _MODO["original"] = antes


def _meio_acima(v, casas=0) -> float:
    """Arredonda o meio para cima, como o Math.round do painel (o Python arredonda o meio para o par)."""
    f = 10 ** casas
    return math.floor(float(v or 0) * f + 0.5) / f


def _milhar(inteiro: int) -> str:
    return f"{int(inteiro):,}".replace(",", ".")


def n(v) -> str:
    """Contagem: "1.469". O Python truncava; o painel arredondava."""
    if _MODO["original"]:
        return f"{int(v):,}".replace(",", ".")
    return _milhar(_meio_acima(v))


def f0(v) -> str:
    """Horas sem casa decimal: "1.469"."""
    if _MODO["original"]:
        return f"{v:.0f}"
    return _milhar(_meio_acima(v))


def f1(v) -> str:
    """Uma casa decimal: "66,8"."""
    if _MODO["original"]:
        return f"{v:.1f}"
    s = f"{_meio_acima(v, 1):,.1f}"
    return s.replace(",", "\0").replace(".", ",").replace("\0", ".")


def p0(v) -> str:
    """Percentual inteiro, sem o "%": "83"."""
    if _MODO["original"]:
        return f"{v:.0f}"
    return str(int(_meio_acima(v)))


h = lambda s: _html.escape(str(s if s is not None else ""))           # noqa: E731
pct = lambda a, b: (100.0 * a / b) if b else 0.0                      # noqa: E731
cor = lambda p: "ok" if p >= META else "mid" if p >= 70 else "mal"   # noqa: E731
cel = lambda p: f'<span class="cel {cor(p)}">{p0(p)}%</span>'        # noqa: E731
fin = lambda x: x.get("status") == "Finalizados"                      # noqa: E731
andando = lambda x: x.get("status") in ("Em progresso", "pausado")   # noqa: E731
ds = lambda s: date.fromisoformat(s[:10]) if s else None             # noqa: E731
usina_curta = lambda u: re.sub(r"^[^-]+ - ", "", u or "").rsplit(" - ", 1)[0]   # noqa: E731
tarefa_curta = lambda t: re.sub(r"^\[.*?\]\s*-?\s*", "", t or "")              # noqa: E731
janela_ok = lambda x: (x.get("h_fim") or "")[:2].isdigit() and int(x["h_fim"][:2]) < 24   # noqa: E731
hh = lambda x: (x.get("duracao") or 0) + (x.get("desloc") or 0)      # noqa: E731


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def mins(s):
    try:
        a, b = str(s).split(":")
        return int(a) * 60 + int(b)
    except Exception:            # noqa: BLE001 — hora fora do formato: sem minuto
        return None


def semana_key(d: date) -> str:
    return f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"


def semana_seg(week: str) -> date:
    ano, num = week.split("-W")
    return date.fromisocalendar(int(ano), int(num), 1)


def tabela(linhas, cab, cols, vazio="nada encontrado"):
    if not linhas:
        return f'<div class="vazio">{vazio}</div>'
    return ('<table><thead><tr>' + ''.join(f'<th class="{c}">{t}</th>' for t, c in cab) + '</tr></thead><tbody>'
            + ''.join('<tr>' + ''.join(f'<td class="{c}">{v}</td>' for v, c in zip(l, cols)) + '</tr>' for l in linhas)
            + '</tbody></table>')


_LOGO: dict = {}


def logo_html() -> str:
    """A logo da Grid Co. em verde, embutida na folha (a do painel do PCM): a folha arquivada abre sozinha, sem o Nexus."""
    if "html" not in _LOGO:
        arq = Path(__file__).resolve().parents[2] / "static" / "grid-h-verde.png"
        try:
            dado = base64.b64encode(arq.read_bytes()).decode()
            _LOGO["html"] = f'<img class="logo" src="data:image/png;base64,{dado}" alt="Grid Co.">'
        except OSError:
            _LOGO["html"] = '<div class="logo-txt">Grid Co.</div>'
    return _LOGO["html"]


def sufixo_recorte(recorte) -> str:
    """O recorte da emissão sob demanda no subtítulo (" · cliente · cluster"), como o painel; vazio sem recorte."""
    cliente, grupo = recorte or ("", "")
    return h((" · " + cliente if cliente else "") + (" · " + grupo if grupo else ""))


# A folha base do fechamento e do alerta (relatorios_semana.py); o diário e a tarde têm a folha deles.
CSS_BASE = """
*{box-sizing:border-box} body{margin:0;font-family:"Segoe UI",Arial,sans-serif;font-size:9.5pt;color:#191528;line-height:1.3;background:#fff}
.pg{page-break-after:always} .pg:last-child{page-break-after:auto}
.top{display:flex;align-items:flex-start;gap:14px;padding-bottom:8px;margin-bottom:9px;border-bottom:3px solid #191528}
.top .logo{height:20px;width:auto;display:block;margin-top:4px} .logo-txt{font-weight:800;font-size:14pt} .top .t{flex:1}
.top h1{margin:0;font-size:15pt;font-weight:800;white-space:nowrap} .top .s{font-size:9pt;color:#68667d;white-space:nowrap}
.top .d{text-align:right;font-size:9pt;color:#3a3550;white-space:nowrap} .top .d b{display:block;font-size:12pt;color:#191528}
.kpis{display:grid;gap:6px;margin:8px 0 9px} .kpi{border:1px solid #e4e4ef;border-left:3px solid #cbcbdd;border-radius:6px;padding:5px 8px}
.kpi.g{border-left-color:#A9DB21} .kpi.r{border-left-color:#c2410c} .kpi.m{border-left-color:#a04408}
.kpi .v{font-size:14pt;font-weight:800;line-height:1.05} .kpi .n{font-size:7.8pt;color:#68667d;text-transform:uppercase;letter-spacing:.04em;margin-top:2px} .kpi .m{font-size:8pt;color:#68667d}
.sec{margin:8px 0 4px;font-size:8.5pt;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:#68667d;display:flex;align-items:center;gap:8px} .sec::after{content:"";flex:1;height:1px;background:#e4e4ef}
table{width:100%;border-collapse:collapse;font-size:8.4pt} td,th{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:230px} td.quebra{white-space:normal;max-width:none}
th{text-align:left;font-size:7.4pt;text-transform:uppercase;letter-spacing:.04em;color:#68667d;padding:3px 6px;border-bottom:1px solid #cbcbdd;background:#f6f7fa}
td{padding:2.4px 6px;border-bottom:1px solid #eceef4;vertical-align:top} .r{text-align:right} th.r{text-align:right} .mono{font-family:Consolas,monospace;font-size:8.8pt}
.cel{display:inline-block;min-width:38px;text-align:center;padding:1px 5px;border-radius:4px;font-weight:700} .cel.ok{background:#e3f6ea;color:#1f7a4d} .cel.mid{background:#fdf0d5;color:#a04408} .cel.mal{background:#fde2e2;color:#b02525}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:12px} .g3{display:grid;grid-template-columns:1.1fr 1fr 1fr;gap:12px}
.ins{margin:0;padding-left:16px} .ins li{margin:2.5px 0;font-size:9.1pt}
.bars{display:flex;gap:10px;align-items:flex-end;height:80px;padding:4px 6px 0} .bar{flex:1;display:flex;flex-direction:column;align-items:center;gap:3px;height:100%} .bar .col{flex:1;width:100%;display:flex;gap:2px;align-items:flex-end;justify-content:center}
.bar .col i,.bar .col b{display:block;width:14px;border-radius:2px 2px 0 0} .bar .col i{background:#cbcbdd} .bar .col b{background:#191528} .bar span{font-size:8.5pt;font-weight:700} .bar small{display:block;font-weight:400;color:#68667d;font-size:7.5pt}
.nota{background:#fbfbe8;border-left:3px solid #A9DB21;padding:5px 9px;font-size:8.6pt;color:#3a3550;margin-top:5px} .nota.aviso{background:#fdf0d5;border-left-color:#c2410c}
.pe{margin-top:9px;border-top:1px solid #e4e4ef;padding-top:6px;font-size:7.8pt;color:#68667d;display:flex;justify-content:space-between;gap:10px}
.al{color:#b02525;font-weight:700} .cinza{color:#68667d} .vazio{color:#68667d;font-size:8.6pt;padding:3px 2px}
.al-bloco{border:1px solid #e4e4ef;border-radius:6px;padding:5px 9px;margin:5px 0;break-inside:avoid}
.al-cab{display:flex;align-items:center;gap:8px;font-size:9.6pt} .al-txt{font-size:8.3pt;color:#3a3550;margin:1px 0 3px}
.sev{font-size:7.3pt;font-weight:800;text-transform:uppercase;letter-spacing:.05em;padding:1px 6px;border-radius:3px} .sev.mal{background:#fde2e2;color:#b02525} .sev.mid{background:#fdf0d5;color:#a04408} .sev.ok{background:#e3f6ea;color:#1f7a4d}
"""

# Na tela (a prévia da Central e a aba nova), a folha ganha a margem do papel; na impressão, a do @page.
CSS_TELA = "@media screen{body{padding:12mm}}"


def pagina(titulo, css_extra, corpo, margem="11mm 12mm 12mm") -> str:
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>{h(titulo)}</title>'
            f'<style>@page{{size:A4;margin:{margem}}}{CSS_BASE}{css_extra}</style></head><body>{corpo}</body></html>')
