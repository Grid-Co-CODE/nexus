# -*- coding: utf-8 -*-
"""O BD_Performance e o BD_Thopen lidos do banco (API db_performace) para a tela Coletas, com a MESMA cara do BD lido do
Excel pelo Conversor (`nucleo.BD`): `abas()`, `aba(nome)` -> `AbaBD`, `estilos()`, `lido_em`, `fechar()`.

Levi, 11/11/2026: "a ideia seria criar um campo chamado 'Coletas' que faz a mesma coisa que faz nas coletas só que lá no
nexus, ficaria mais fácil para todo mundo, e leria direto do PG!". O que o banco tem e o que não tem:

- tem: o número da linha no Excel (`row_number`), o cabeçalho, os valores e a hora da última subida (`updated_at`). É o
  que a montagem precisa para dizer "cole na célula C123" e não cobrir dado.
- NÃO tem fórmula nem cor: o `sync_gridco_api.py` da coleta sobe só valores (decisão de 27/08/2026). Sem saber quais
  células são fórmula, o Conversor escreveria por cima do IPOA da Vitesse (= Hortina) e partiria o bloco no lugar errado
  (a Nova Iguaçu tem a Energia digitada até 08/11 e fórmula de tabela a partir de 09/11: a marca é POR CÉLULA). A escolha
  do Levi (11/11/2026, "Aceito também sua recomendação"): a coleta sobe, na MESMA subida, o livro `bd_formulas` com as
  células que são fórmula e a lista de abas do Excel. Sem esse mapa (ou com ele mais velho que o BD), o BD do banco NÃO é
  usado: a tela diz o motivo e aceita o BD em Excel solto junto com os arquivos, como o .exe.
- as abas renomeadas no Excel ficam velhas no banco (o replace=true só troca as abas que sobem: "Vitesse", "Carosa",
  "Salvales", "Hortina" e "SunPower" pararam em 30/09/2026 e hoje são "Quixadá 2 (Vitesse)" etc.). Vale só a aba que
  está na lista de abas da última subida (`abas_<bd>` do `bd_formulas`).
- a cor (o amarelo do valor digitado à mão, o vermelho de falta) não sobe: a planilha de colar sai sem ela. A regra de
  não cobrir dado olha o valor, não a cor.
"""
import datetime as dt
import threading
import time

from . import motor  # noqa: F401 — põe o motor no caminho como `conversor` (ver o __init__)
from conversor.nucleo import BD_PERFORMANCE, BD_THOPEN, AbaBD  # noqa: E402

CHAVE = {BD_PERFORMANCE: "bd_performance", BD_THOPEN: "bd_thopen"}
LIVRO_FORMULAS = "bd_formulas"
CAB_FORMULAS = ("aba", "linha", "coluna", "cabecalho", "formula", "subida_em")
CAB_ABAS = ("aba", "linhas", "colunas", "subida_em")
# o mapa sobe na mesma rodada do BD, minutos depois dele (o BD primeiro): mais velho que isto = é de outra subida
FOLGA_MAPA_S = 30 * 60
PAGINA = 1000
VALE_S = 600                    # a leitura do banco vale 10 min se o updated_at não mudou


def aba_formulas(destino):
    return "formulas_" + CHAVE[destino]


def aba_abas(destino):
    return "abas_" + CHAVE[destino]


class SemMapa(Exception):
    """O BD do banco não pode ser usado: falta o mapa de fórmulas desta subida."""


def _quando(txt):
    """O `updated_at` da API ("2026-11-11T12:45:59.514480-03:00") na hora de Brasília, sem fuso; None se não der."""
    if not txt:
        return None
    try:
        d = dt.datetime.fromisoformat(str(txt).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is not None:
        d = d.astimezone(dt.timezone(dt.timedelta(hours=-3))).replace(tzinfo=None)
    return d


def _data(v):
    """A coluna Data vem do banco como texto ISO; o Conversor espera a data do openpyxl (datetime)."""
    if isinstance(v, str) and len(v) >= 10 and v[4] == "-" and v[7] == "-":
        try:
            return dt.datetime.fromisoformat(v[:19] if "T" in v else v[:10])
        except ValueError:
            return v
    return v


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


class Banco:
    """As leituras cruas da API (uma sessão requests). Separado para o teste dublar a API sem rede."""

    def __init__(self, base, sessao):
        self.base, self.s = base.rstrip("/"), sessao

    def livros(self):
        r = self.s.get(f"{self.base}/api/workbooks", timeout=60)
        r.raise_for_status()
        return {w.get("key"): w for w in r.json()}

    def abas(self):
        r = self.s.get(f"{self.base}/api/sheets", timeout=60)
        r.raise_for_status()
        out = {}
        for x in r.json():
            out.setdefault(x.get("workbook_key"), {})[x["sheet_name"]] = x
        return out

    def linhas(self, sid):
        """[{row_number, headers, values}] da aba inteira, na ordem do banco."""
        out, offset = [], 0
        while True:
            r = self.s.get(f"{self.base}/api/sheets/{sid}/rows", params={"limit": PAGINA, "offset": offset}, timeout=90)
            r.raise_for_status()
            j = r.json()
            rows = j.get("rows", j) if isinstance(j, dict) else j
            out += rows
            if len(rows) < PAGINA:
                return out
            offset += PAGINA


def _dicts(rows):
    return [dict(zip(x.get("headers") or [], x.get("values") or [])) for x in rows]


class BDdoBanco:
    """Um BD (BD_Performance ou BD_Thopen) lido do banco, com as fórmulas do `bd_formulas` por cima dos valores."""

    def __init__(self, destino, banco, livros=None, abas=None):
        self.destino = destino
        self._b = banco
        chave = CHAVE[destino]
        livros = livros if livros is not None else banco.livros()
        abas = abas if abas is not None else banco.abas()
        w = livros.get(chave)
        if not w:
            raise LookupError(f"o banco não tem o livro {chave}")
        self.lido_em = _quando(w.get("updated_at") or w.get("atualizado_em")) or dt.datetime.now()
        self.subida_txt = w.get("updated_at") or w.get("atualizado_em")
        self.caminho = f"banco · {chave}"
        self._sheets = abas.get(chave) or {}
        mapa = abas.get(LIVRO_FORMULAS) or {}
        sf, sa = mapa.get(aba_formulas(destino)), mapa.get(aba_abas(destino))
        if not sf or not sa:
            # o detalhe técnico (o livro bd_formulas e as abas dele) mora no CLAUDE.md: a tela diz o que fazer
            raise SemMapa(f"o banco ainda não tem o mapa de fórmulas do {destino}, que sobe com a coleta. Sem ele, a "
                          f"tela poderia escrever por cima de uma fórmula: solte o {destino} em Excel junto com os "
                          f"arquivos (ou clique no botão do {destino}).")
        lista = _dicts(banco.linhas(sa["id"]))
        quando = max((_quando(x.get("subida_em")) for x in lista if _quando(x.get("subida_em"))), default=None)
        if quando is None or (self.lido_em - quando).total_seconds() > FOLGA_MAPA_S:
            raise SemMapa(f"o mapa de fórmulas do {destino} no banco é de outra subida (mapa: "
                          f"{quando.strftime('%d/%m %H:%M') if quando else 'sem hora'}; BD: "
                          f"{self.lido_em.strftime('%d/%m %H:%M')}). Solte o {destino} em Excel junto com os arquivos.")
        self.mapa_em = quando
        self._lista = [str(x.get("aba") or "").strip() for x in lista if str(x.get("aba") or "").strip()]
        self._formulas = {}
        for x in _dicts(banco.linhas(sf["id"])):
            ln, col, f = _int(x.get("linha")), _int(x.get("coluna")), str(x.get("formula") or "")
            if ln and col and f:
                self._formulas.setdefault(str(x.get("aba") or "").strip(), {})[(ln, col - 1)] = \
                    f if f.startswith("=") else "=" + f
        self._abas = {}
        self.velhas = sorted(a for a in self._sheets if a not in set(self._lista))

    def abas(self):
        """As abas do Excel na última subida (as velhas, que ficaram no banco depois de renomeadas, não contam)."""
        return [a for a in self._lista if a in self._sheets]

    def aba(self, nome):
        if nome in self._abas:
            return self._abas[nome]
        if nome not in self.abas():
            return None
        sh = self._sheets[nome]
        rows = self._b.linhas(sh["id"])
        cab = None
        linhas = {}
        for x in rows:
            if cab is None:
                cab = [str(h).strip() if h is not None else "" for h in (x.get("headers") or [])]
            vals = list(x.get("values") or [])
            n = _int(x.get("row_number"))
            if n is None:
                continue
            linhas[n] = vals
        hr = _int(sh.get("header_row")) or (min(linhas) - 1 if linhas else 1)
        if cab is None or not any(c.lower() == "data" for c in cab):
            self._abas[nome] = None
            return None
        idata = [c.lower() for c in cab].index("data")
        for (ln, j), f in (self._formulas.get(nome) or {}).items():
            if ln not in linhas:
                continue
            v = linhas[ln]
            if j >= len(v):
                v += [None] * (j + 1 - len(v))
            v[j] = f
        final = {}
        for n, v in linhas.items():
            if idata < len(v):
                v[idata] = _data(v[idata])
            final[n] = tuple(v)
        a = AbaBD(nome, hr, cab, final)
        self._abas[nome] = a
        return a

    def estilos(self, nome, r1, r2, c1, c2):
        return {}                                   # a cor não sobe ao banco: a planilha sai sem ela (ver o topo)

    def fechar(self):
        self._abas.clear()


# A leitura do banco é a mesma para todo mundo até a próxima subida: uma por (BD, updated_at), guardada 10 min
_GUARDA = {}
_TRAVA = threading.Lock()


def bd_do_banco(destino, banco):
    """(BDdoBanco ou None, erro em texto ou None). O mesmo objeto serve a todas as sessões enquanto a subida não muda."""
    try:
        livros, abas = banco.livros(), banco.abas()
    except Exception as e:                                   # noqa: BLE001 — banco fora: a tela diz
        return None, f"o banco não respondeu ({type(e).__name__})"
    w = livros.get(CHAVE[destino]) or {}
    marca = (destino, w.get("updated_at"), ((abas.get(LIVRO_FORMULAS) or {}).get(aba_abas(destino)) or {}).get("id"))
    with _TRAVA:
        g = _GUARDA.get(destino)
        if g and g[0] == marca and time.time() - g[1] < VALE_S:
            return g[2], g[3]
    try:
        bd, erro = BDdoBanco(destino, banco, livros, abas), None
    except SemMapa as e:
        bd, erro = None, str(e)
    except LookupError as e:
        bd, erro = None, str(e)
    except Exception as e:                                   # noqa: BLE001
        bd, erro = None, f"não consegui ler o {destino} do banco ({type(e).__name__}: {e})"
    with _TRAVA:
        _GUARDA[destino] = (marca, time.time(), bd, erro)
    return bd, erro
