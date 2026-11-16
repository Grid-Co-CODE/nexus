# -*- coding: utf-8 -*-
"""De onde o motor dos furos (`furos_r01.py`) tira cada coisa no servidor, e a conta em segundo plano.

- **BDs, Info Geral e Base UFV: do banco** (db_performace, a subida da coleta), não do Excel (Levi, 16/11/2026: "Faça
  ler pelo PG mesmo, pelos dados que estão no Postgre. Que em tese, no dia a dia, para um ser igual ao outro"). Prova de
  16/11: outubro do banco = Excel nas 74.927 células; novembro difere só no que entrou no Excel depois da última subida.
  A leitura inteira leva ~30 s e é guardada até a próxima subida (o `updated_at` dos dois livros); a aba velha que o
  banco não apaga sai pela régua de `furos_r01.velhas`.
- **Paradas do COS: as mesmas linhas do "Exportar CSV" da tela Ocorrências** (as normalizadas guardadas pelo
  `nexus/cos/normalizacoes.py` mais as em andamento), montadas pela MESMA função do CSV (`csv_linhas`): é o arquivo que a
  analista baixava (`ocorrencias-2026-11*.csv`), sem baixar. O COS só está ligado no servidor; sem ele, a tela avisa e
  novembro sai sem as paradas (fica mais furo, nunca menos).
- **Outubro (e os tickets que entram em novembro): congelados do HTML R01** (`furos_conf.Congeladas`).

A conta (sem o banco, ~1 s) é refeita a cada 10 min, na virada do dia e a cada subida nova; o último resultado fica em
`furos_calculo.json` para o reinício do Nexus não deixar a tela vazia.

A 1ª conta (sem resultado nenhum ainda) é a única que faz a tela esperar (Levi, 16/11/2026, na 1ª abertura: "demora para
ler hein"). Por isso: as abas do banco são lidas de 8 em 8 ao mesmo tempo (medido do PC: 28,8 s uma a uma, 12,3 s de 8
em 8, mesmo resultado), o COS é lido junto com o banco e não depois, e abrir a Coletas já dispara a conta, antes de a
pessoa clicar na aba (`coletas_tela.coletas`).
"""
import concurrent.futures as cf
import csv
import datetime as dt
import json
import os
import threading
import time
import types

from . import furos_r01 as R
from .furos_conf import Congeladas

LIVROS = (("BD_Performance", "bd_performance"), ("BD_Thopen", "bd_thopen"))
REFAZER_S = 600
TENTAR_DE_NOVO_S = 60
ARQ_CALCULO = "furos_calculo.json"
LEITURAS_JUNTAS = 8             # abas do banco lidas ao mesmo tempo (ver o topo)


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _quando(txt):
    """O `updated_at` da API em Brasília, sem fuso."""
    if not txt:
        return None
    try:
        d = dt.datetime.fromisoformat(str(txt).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is not None:
        d = d.astimezone(dt.timezone(dt.timedelta(hours=-3))).replace(tzinfo=None)
    return d


def marca_do_banco(livros):
    return tuple((k, (livros.get(k) or {}).get("updated_at")) for _s, k in LIVROS)


def _reduzir(src, nome, rows):
    """Uma aba do banco reduzida ao que o motor usa: ("info"|"base", linhas) ou ("bd", planilhas, último dia) ou None."""
    rows = sorted(rows, key=lambda x: _int(x.get("row_number")) or 0)
    if not rows:
        return None
    vals = [list(r.get("values") or []) for r in rows]
    if src == "BD_Performance" and nome == "Info Geral":
        return "info", [v for r, v in zip(rows, vals) if (_int(r.get("row_number")) or 0) >= 3]
    if src == "BD_Performance" and nome == "Base UFV":
        return "base", [v for r, v in zip(rows, vals) if (_int(r.get("row_number")) or 0) >= 2]
    p, _log = R.ler_abas(src, [(nome, list(rows[0].get("headers") or []), vals)])
    return ("bd", p, R.ultima_data(vals)) if p else None


def ler_banco(banco, juntas=LEITURAS_JUNTAS):
    """Os dois BDs do banco, aba por aba (cada uma já reduzida ao que o motor usa, para não segurar o banco inteiro na
    memória), `juntas` abas ao mesmo tempo; o resultado sai na ordem do banco, igual ao de uma por vez.
    -> dict(planilhas, cad, marca, subidas, velhas)."""
    livros, abas = banco.livros(), banco.abas()
    pedidos = [(src, nome, sh) for src, chave in LIVROS for nome, sh in (abas.get(chave) or {}).items()]
    with cf.ThreadPoolExecutor(max(1, juntas), thread_name_prefix="nexus-furos-banco") as ex:
        # cada leitura já reduz a sua aba: no máximo `juntas` abas cruas na memória ao mesmo tempo
        reduzidas = list(ex.map(lambda q: _reduzir(q[0], q[1], banco.linhas(q[2]["id"])), pedidos))
    planilhas, info, base, velhas, subidas = [], [], [], {}, {}
    for src, chave in LIVROS:
        subidas[src] = _quando((livros.get(chave) or {}).get("updated_at"))
        lidas, fins = [], {}
        for (s2, nome, _sh), r in zip(pedidos, reduzidas):
            if s2 != src or r is None:
                continue
            if r[0] == "info":
                info = r[1]
            elif r[0] == "base":
                base = r[1]
            else:
                fins[nome] = r[2]
                lidas += r[1]
        v = R.velhas(fins)
        velhas[src] = sorted([n, d.date().isoformat()] for n, d in v.items())
        planilhas += [p for p in lidas if p["sheet"] not in v]
    return dict(planilhas=planilhas, cad=R.cadastro(info, base), marca=marca_do_banco(livros), subidas=subidas,
                velhas=velhas)


def linhas_cos(cfg, agora):
    """As linhas do "Exportar CSV" da tela Ocorrências, de todos os meses guardados: as em andamento e as normalizadas
    (sem as desfeitas), como dicts pelas colunas do CSV. -> (linhas ou None, aviso)."""
    from ...cos import normalizacoes as NO
    lt = NO.ler(cfg, agora)
    if not lt.dados:
        return None, lt.erro or "o COS não respondeu"
    itens = [NO._item(n, agora) for n in lt.dados.get("itens") or []]
    normalizadas = sorted([i for i in itens if i["normalizada"]], key=lambda i: i["data"] or agora, reverse=True)
    ja = {i["registro"] for i in normalizadas}
    aviso = "a 1ª leitura do COS ainda está pela metade" if lt.dados.get("carregando") else ""
    try:
        from ...torres.cos import _andamento_cos
        andamento, _l, erros = _andamento_cos(cfg, agora)
        if erros:
            aviso = "; ".join(x for x in [aviso, "em andamento: " + "; ".join(erros)] if x)
    except Exception as e:                                   # noqa: BLE001 — sem as abertas, o resto segue
        andamento, aviso = [], "; ".join(x for x in [aviso, f"as em andamento não vieram ({type(e).__name__})"] if x)
    andamento = [i for i in andamento if i["registro"] not in ja]
    rows = NO.csv_linhas(types.SimpleNamespace(itens=andamento + normalizadas))
    return [dict(zip(NO.CSV_COLUNAS, r)) for r in rows], aviso


def linhas_cos_csv(caminho):
    """O CSV exportado da tela Ocorrências (bancada no PC, onde o COS não está ligado)."""
    with open(caminho, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


class Servico:
    """A conta dos furos, uma por Nexus. `fabrica_banco()` -> pg.Banco; `ler_cos(agora)` -> (linhas, aviso);
    `relogio()` -> o agora em Brasília (sem fuso)."""

    def __init__(self, pasta, fabrica_banco, ler_cos, relogio):
        self.pasta = pasta
        self._fab, self._ler_cos, self._relogio = fabrica_banco, ler_cos, relogio
        self._trava = threading.Lock()
        self._rodando = False
        self._bd = None
        self.erro = ""
        self._falhou = 0
        self._res = self._do_disco()

    def _do_disco(self):
        try:
            with open(os.path.join(self.pasta, ARQ_CALCULO), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def _precisa(self, agora):
        r = self._res
        if not r:
            return time.time() - self._falhou >= TENTAR_DE_NOVO_S     # sem conta e o banco fora: não a cada clique
        if r.get("_dia") != agora.date().isoformat():
            return True
        return time.time() - (r.get("_feito") or 0) >= REFAZER_S

    def resultado(self, esperar=False):
        """O último resultado (ou None) e se há conta rodando; dispara a conta quando venceu. `esperar` segura o
        pedido só enquanto não existe conta nenhuma (a 1ª leitura do banco, ~30 s)."""
        agora = self._relogio()
        with self._trava:
            if not self._rodando and self._precisa(agora):
                self._rodando = True
                th = threading.Thread(target=self._rodar, name="nexus-furos-r01", daemon=True)
                th.start()
            else:
                th = None
        if esperar and th is not None and self._res is None:      # só a 1ª conta segura o pedido; depois, a de antes
            th.join()
        return self._res, self._rodando

    def refazer(self):
        """Na importação: a conta de novo agora (as congeladas mudaram)."""
        with self._trava:
            if self._res:
                self._res["_feito"] = 0
        return self.resultado()

    def _rodar(self):
        try:
            agora = self._relogio()
            lido = {}

            def le_cos():                                    # junto com o banco, não depois (ver o topo)
                try:
                    lido["cos"] = self._ler_cos(agora)
                except Exception as e:                       # noqa: BLE001
                    lido["cos"] = (None, f"não consegui ler o COS ({type(e).__name__})")
            tc = threading.Thread(target=le_cos, name="nexus-furos-cos", daemon=True)
            tc.start()
            try:
                banco = self._fab()
                livros = banco.livros()
                if not self._bd or self._bd["marca"] != marca_do_banco(livros):
                    self._bd = ler_banco(banco)
            finally:
                tc.join()
            cos, aviso = lido["cos"]
            cong = Congeladas(self.pasta)
            res = R.gerar_de(self._bd["planilhas"], self._bd["cad"], cos, cong.meses(), agora.date(), agora)
            info_cong = {m: {k: x.get(k) for k in ("gen", "origem", "importado_em", "quem")} | {"usinas": len(x["usinas"])}
                         for m, x in (cong.ler().get("meses") or {}).items()}
            d1 = R.d1_de(agora.date())
            subidas = {s: (d.strftime("%d/%m/%Y %H:%M") if d else None) for s, d in self._bd["subidas"].items()}
            # a subida da noite traz até a véspera: sem a subida de d-1, o dia d-2 pode estar no Excel e não no banco
            atrasado = [s for s, d in self._bd["subidas"].items() if not d or d.date() < d1 + dt.timedelta(days=1)]
            res["fontes"] = dict(bd=subidas, bd_atrasado=atrasado, velhas=self._bd["velhas"],
                                 cos=dict(ligado=cos is not None, linhas=len(cos or []), aviso=aviso),
                                 congelado=info_cong)
            res["_dia"], res["_feito"] = agora.date().isoformat(), time.time()
            tmp = os.path.join(self.pasta, ARQ_CALCULO + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False)
            os.replace(tmp, os.path.join(self.pasta, ARQ_CALCULO))
            self._res, self.erro = res, ""
        except Exception as e:                               # noqa: BLE001 — a tela mostra o último e o motivo
            self.erro = f"não consegui refazer a conta ({type(e).__name__}: {e})"
            self._falhou = time.time()
            if self._res:
                self._res["_feito"] = time.time()            # tenta de novo em 10 min, não a cada clique
        finally:
            with self._trava:
                self._rodando = False
