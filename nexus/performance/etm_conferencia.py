# -*- coding: utf-8 -*-
"""A conferência automática das OS de ETM pelos dados diários do PG (25/11/2026).

Levi: "Bata com os dados que a gente tem, os dados diários, no PG, tanto na BD Thopen quanto BD Performance [...] se o PR
não está abaixo de 50 ou se o PR não está acima de 100. E se o IPOA não está abaixo do GHI. Aí se passar por todos esses
parâmetros aí, dá como finalizado pela performance. E aí a gente vai ter a visão só das ETMs com problema mesmo." E, nas
escolhas: "Se os 5 dias estiverem ok, já tá tudo certo"; a regra vale no período; o IPOA pode ficar "até 8%" abaixo do GHI;
a OS sem dado "fica na lista como sem dado".

A regra (`conferir`, pura):
- conta a OS de ETM CONCLUÍDA no Fracttal (a da coluna Finalizadas) que ainda está aberta para a Performance (sem o
  finalizado nem o diagnóstico);
- os dias: os 5 mais recentes COM DADO (PR publicado, IPOA e GHI acima de zero) depois do dia da conclusão e antes de
  hoje (o dia de hoje está pela metade), olhando até 30 dias para trás;
- passa quando o PR médio desses 5 dias fica entre 50% e 100% e o IPOA somado é pelo menos 92% do GHI somado;
- com menos de 5 dias com dado: "aguardando" enquanto a conclusão é recente (5 dias e mais 2 de atraso da coleta, que
  grava o dia de ontem às 22:30), e "sem dado" depois disso, com o que falta.

De onde vem cada número (`ler_dias`, só leitura):
- PR: o PR diário que a plataforma publica (`nexus_performance · fato_desempenho_usina_dia`, o do Painel NOC), ligado à
  usina do cadastro pelo nome (`campo.responsaveis.Nomes`: o de-para das abas e o nome do cadastro);
- IPOA e GHI: as abas da usina no `bd_thopen` e no `bd_performance` (o de-para `BD_Thopen · aba` e `BD_Performance · aba`),
  o IPOA do SENSOR ("IPOA (kWh/m²) ETM"; sem ela, "IPOA (kWh/m²)"): o "DEF" do bd_performance é o escolhido para a conta e
  pode não ser o da ETM, então não confere a ETM.

O que é ok vira "Finalizado pela Performance" sozinho (`finalizar`), com o comentário que diz os números, pelo mesmo livro
do botão (`nexus_engenharia_etm`) e dos comentários (`nexus_engenharia_os`); no Fracttal nada muda. Quem fica nas
Estações em Aberto é o que tem problema: a OS ainda aberta no Fracttal, a que reprovou, a sem dado e a que espera os dias.
"""
import json
import logging
import os
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

log = logging.getLogger("nexus.performance.etm_conferencia")
_BRT = timezone(timedelta(hours=-3))

JANELA_DIAS = 5            # "Se os 5 dias estiverem ok, já tá tudo certo"
PR_MIN, PR_MAX = 50.0, 100.0
FOLGA_GHI = 0.08           # o IPOA "até 8%" abaixo do GHI
ATRASO_DADO = 2            # a coleta grava o dia de ontem às 22:30: dois dias de folga antes de dizer "sem dado"
BUSCA_DIAS = 30            # até onde olhar para trás atrás dos 5 dias
A_CADA_S = 30 * 60         # a conferência roda por trás de meia em meia hora
QUEM = {"email": "", "nome": "Nexus (conferência automática)", "hmac": None}
SISTEMAS_ABA = {"BD_Thopen · aba": "bd_thopen", "BD_Performance · aba": "bd_performance"}
COL_IPOA = ("IPOA (kWh/m²) ETM", "IPOA (kWh/m²)")
COL_GHI = ("GHI (kWh/m²)",)
LIVRO_PR, ABA_PR = "nexus_performance", "fato_desempenho_usina_dia"
REGRA = (f"os {JANELA_DIAS} dias mais recentes com dado depois da conclusão: PR médio entre {PR_MIN:.0f}% e "
         f"{PR_MAX:.0f}% e IPOA somado de pelo menos {100 - FOLGA_GHI * 100:.0f}% do GHI somado")


def _num(v):
    if v is None or isinstance(v, bool) or v == "":
        return None
    try:
        x = float(str(v).strip().replace(",", ".")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _dia(v) -> date | None:
    """'2026-11-24', '2026-11-24T…', 20261124 -> date."""
    s = str(v or "").strip()
    try:
        if s.isdigit() and len(s) == 8:
            return date(int(s[:4]), int(s[4:6]), int(s[6:]))
        return date.fromisoformat(s[:10]) if len(s) >= 10 else None
    except ValueError:
        return None


def _br(x, casas=1) -> str:
    return f"{x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ── a regra ────────────────────────────────────────────────────────────────────────────────────────────────────────
def conferir(conclusao: date | None, dias: dict, hoje: date, *, sem_ligacao: str = "") -> dict:
    """A conferência de uma OS concluída em `conclusao`, com os `dias` da usina ({date: {"pr", "ipoa", "ghi"}}).
    {"estado": "ok" | "falha" | "aguardando" | "sem_dado", "texto", "curto", "dias", "pr", "ipoa_ghi", "motivos"}."""
    if sem_ligacao:
        return {"estado": "sem_dado", "texto": f"Sem dado no PG: {sem_ligacao}", "curto": "sem dado no PG",
                "dias": [], "motivos": [sem_ligacao]}
    if not conclusao:
        return {"estado": "sem_dado", "texto": "Sem dado: a OS não tem a data de conclusão no Fracttal",
                "curto": "sem data de conclusão", "dias": [], "motivos": ["sem a data de conclusão"]}
    janela = [d for d in sorted(dias) if conclusao < d < hoje and (hoje - d).days <= BUSCA_DIAS]
    validos = [d for d in janela if dias[d].get("pr") is not None and (dias[d].get("ipoa") or 0) > 0
               and (dias[d].get("ghi") or 0) > 0]
    if len(validos) >= JANELA_DIAS:
        usa = validos[-JANELA_DIAS:]
        pr = sum(dias[d]["pr"] for d in usa) / len(usa)
        ipoa, ghi = sum(dias[d]["ipoa"] for d in usa), sum(dias[d]["ghi"] for d in usa)
        razao = ipoa / ghi
        motivos = []
        if pr < PR_MIN:
            motivos.append(f"PR médio {_br(pr)}% (abaixo de {PR_MIN:.0f}%)")
        elif pr > PR_MAX:
            motivos.append(f"PR médio {_br(pr)}% (acima de {PR_MAX:.0f}%)")
        if razao < 1 - FOLGA_GHI:
            motivos.append(f"IPOA {_br(razao * 100, 0)}% do GHI (abaixo de {100 - FOLGA_GHI * 100:.0f}%)")
        periodo = f"{usa[0]:%d/%m} a {usa[-1]:%d/%m}"
        numeros = f"PR médio {_br(pr)}% e IPOA {_br(razao * 100, 0)}% do GHI em {JANELA_DIAS} dias ({periodo})"
        base = {"dias": [d.isoformat() for d in usa], "pr": round(pr, 1), "ipoa_ghi": round(razao * 100, 1),
                "motivos": motivos}
        if motivos:
            return dict(base, estado="falha", texto=f"Dados reprovados: {'; '.join(motivos)} ({periodo})",
                        curto="; ".join(motivos))
        return dict(base, estado="ok", texto=f"Dados ok: {numeros}", curto=numeros)
    corridos = (hoje - conclusao).days - 1          # dias inteiros depois da conclusão, sem o de hoje
    if corridos < JANELA_DIAS + ATRASO_DADO:
        n = len(validos)
        return {"estado": "aguardando", "texto": f"Aguardando os dados: {n} de {JANELA_DIAS} dias depois da conclusão",
                "curto": f"aguardando {n} de {JANELA_DIAS} dias", "dias": [d.isoformat() for d in validos], "motivos": []}
    faltas = []
    for chave, rot in (("pr", "PR publicado"), ("ipoa", "IPOA"), ("ghi", "GHI")):
        sem = sum(1 for d in janela if not (dias[d].get(chave) if chave != "pr" else dias[d].get("pr") is not None))
        if sem:
            faltas.append(f"sem {rot} em {sem} de {len(janela)} dias")
    if not janela:
        faltas = [f"nenhum dia no PG depois da conclusão (até {BUSCA_DIAS} dias)"]
    return {"estado": "sem_dado", "texto": f"Sem dado no PG: só {len(validos)} de {JANELA_DIAS} dias com PR, IPOA e GHI"
            + (f" ({'; '.join(faltas)})" if faltas else ""), "curto": "sem dado no PG", "dias": [d.isoformat() for d in validos],
            "motivos": faltas}


# ── os dados (só leitura) ──────────────────────────────────────────────────────────────────────────────────────────
def abas_da_usina(de_para: list[dict]) -> dict:
    """{usina_id: [(livro, aba)]} do de-para das abas do BD_Thopen e do BD_Performance."""
    from ..dados import fatos as D
    out = defaultdict(list)
    for x in de_para or []:
        livro = SISTEMAS_ABA.get(str(x.get("sistema") or "").strip())
        uid = D._id(x.get("usina_id"))
        aba = str(x.get("chave_externa") or "").strip()
        if livro and uid and aba and (livro, aba) not in out[uid]:
            out[uid].append((livro, aba))
    return dict(out)


def dias_das_abas(linhas_por_aba: list[list[dict]], desde: date, ate: date) -> dict:
    """{date: {"ipoa", "ghi"}} das abas de uma usina (a média quando há mais de uma aba com o número no dia)."""
    soma = defaultdict(lambda: {"ipoa": [], "ghi": []})
    for linhas in linhas_por_aba:
        if not linhas:
            continue
        cols = set(linhas[0].keys())
        c_ipoa = next((c for c in COL_IPOA if c in cols), None)
        c_ghi = next((c for c in COL_GHI if c in cols), None)
        for x in linhas:
            d = _dia(x.get("Data"))
            if not d or not desde <= d <= ate:
                continue
            for k, c in (("ipoa", c_ipoa), ("ghi", c_ghi)):
                v = _num(x.get(c)) if c else None
                if v is not None and v > 0:
                    soma[d][k].append(v)
    return {d: {k: (sum(v) / len(v) if v else None) for k, v in s.items()} for d, s in soma.items()}


def pr_por_usina(linhas: list[dict], usina_de, desde: date, ate: date) -> dict:
    """{usina_id: {date: pr}} do PR diário publicado; `usina_de(nome)` -> usina_id. Dois nomes da mesma usina no mesmo
    dia (as partes "X 1" e "X 2"): a média."""
    acc = defaultdict(lambda: defaultdict(list))
    for x in linhas or []:
        d, pr = _dia(x.get("data_id")), _num(x.get("pr_pct"))
        if not d or pr is None or not desde <= d <= ate:
            continue
        uid = usina_de(x.get("usina"))
        if uid:
            acc[uid][d].append(pr)
    return {u: {d: sum(v) / len(v) for d, v in m.items()} for u, m in acc.items()}


def ler_dias(uids: set, base, sessao, b, hoje: date) -> tuple[dict, dict]:
    """({usina_id: {date: {"pr", "ipoa", "ghi"}}}, {usina_id: o que falta na ligação}) das usinas pedidas."""
    from ..campo.responsaveis import Nomes
    from ..dados import livros
    desde, ate = hoje - timedelta(days=BUSCA_DIAS + 1), hoje
    nomes = Nomes(b)
    a = livros.abas(base, sessao, LIVRO_PR)
    prs = pr_por_usina(livros._linhas(base, sessao, a[ABA_PR]) if ABA_PR in a else [],
                       lambda n: nomes.usina(n)[0], desde, ate)
    abas = abas_da_usina(b.de_para)
    ids = {}
    falta, out = {}, {}
    for uid in uids:
        if not abas.get(uid):
            falta[uid] = "a usina não tem aba no BD_Thopen nem no BD_Performance (de-para das abas)"
            continue
        linhas = []
        for livro, aba in abas[uid]:
            if livro not in ids:
                ids[livro] = livros.abas(base, sessao, livro)
            if aba in ids[livro]:
                linhas.append(livros._linhas(base, sessao, ids[livro][aba]))
        if not linhas:
            falta[uid] = "a aba da usina não está no banco"
            continue
        dias = dias_das_abas(linhas, desde, ate)
        for d, pr in (prs.get(uid) or {}).items():
            dias.setdefault(d, {"ipoa": None, "ghi": None})["pr"] = pr
        out[uid] = dias
    return out, falta


# ── a rodada: confere, guarda e finaliza o que passou ─────────────────────────────────────────────────────────────
_ESTADO = {"em": 0.0, "rodando": False, "os": {}, "erro": "", "regra": REGRA, "finalizadas": 0}
_TRAVA = threading.Lock()


def _arquivo(cfg) -> str | None:
    try:
        from ..cadastro.ligacoes import pasta_dados
        p = os.path.join(pasta_dados(cfg), "performance")
    except RuntimeError:
        return None
    os.makedirs(p, exist_ok=True)
    return os.path.join(p, "etm_conferencia.json")


def resultado(wid) -> dict | None:
    """A última conferência da OS (pelo id do Fracttal), ou None."""
    return (_ESTADO["os"] or {}).get(str(wid or ""))


def carregar(cfg) -> None:
    """A conferência guardada em disco (a tela mostra o resultado logo depois de subir, antes da 1ª rodada)."""
    caminho = _arquivo(cfg)
    if not caminho or not os.path.exists(caminho):
        return
    try:
        with open(caminho, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("os"), dict):
            _ESTADO.update(os=d["os"], em=float(d.get("em") or 0), finalizadas=int(d.get("finalizadas") or 0))
    except (OSError, ValueError, TypeError):
        log.warning("ETMs: a conferência guardada não abriu; a próxima rodada refaz")


def _guardar(cfg) -> None:
    caminho = _arquivo(cfg)
    if not caminho:
        return
    with open(caminho + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"em": _ESTADO["em"], "os": _ESTADO["os"], "finalizadas": _ESTADO["finalizadas"], "regra": REGRA},
                  f, ensure_ascii=False)
    os.replace(caminho + ".tmp", caminho)


def candidatas(oss: list[dict], est: dict) -> list[dict]:
    """As OS que a conferência olha: concluídas no Fracttal (coluna Finalizadas), com o id, e ainda abertas para a
    Performance (sem o finalizado nem o diagnóstico)."""
    out = []
    for o in oss:
        m = est.get(str(o.get("wid"))) or {}
        if o.get("wid") and o.get("coluna_etm") == "finalizada" and not m.get("finalizado") and not m.get("diagnostico_id"):
            out.append(o)
    return out


def finalizar(itens: list[tuple[dict, dict]]) -> list[str]:
    """Marca "finalizado" (quem = a conferência automática) nas OS `itens` = [(a OS no formato do livro, o resultado)],
    numa gravação só, e põe o comentário com os números em cada uma (o mesmo começo do botão, `COMENTARIO_FIM`). Só as
    que o livro relido agora ainda tem abertas. Devolve os números das OS finalizadas."""
    from ..engenharia import acompanhamento as AC
    from ..engenharia import etm_marcas as M
    from ..engenharia import os_acompanhamento as O
    from ..torres.performance.etm_tela import COMENTARIO_FIM, NOTA_FIM
    cofre = AC._cofre()
    feitas, novos = [], []
    with M._TRAVA:
        lido = M._reler()
        est = M.estado(lido["eventos"])
        for os_, _r in itens:
            atual = est.get(str(M._int(os_.get("wid")))) or {}
            if atual.get("finalizado") or atual.get("diagnostico_id"):
                continue
            novos.append(M._evento(cofre, "finalizado", QUEM, os_, ligado=True, origem="conferencia"))
            feitas.append(str(os_.get("folio")))
        if novos:
            M._publicar(lido["eventos"] + novos)
    if feitas:
        alvo = set(feitas)
        try:
            with O._TRAVA:
                lido = O._reler()
                coment = [O._evento(cofre, "comentario", QUEM, os_, nota=NOTA_FIM,
                                    texto=O.texto_do_comentario(f"{COMENTARIO_FIM}conferência automática pelos dados "
                                                                f"diários do PG. {r['texto']}."))
                          for os_, r in itens if str(os_.get("folio")) in alvo]
                O._publicar(lido["eventos"] + coment)
        except Exception:       # noqa: BLE001 — a marcação já foi: o comentário fica faltando e o log diz
            log.exception("ETMs: o comentário da finalização automática não gravou (%s)", ", ".join(feitas))
    return feitas


def rodar(app, *, gravar: bool = True) -> dict:
    """Uma rodada: confere as candidatas na cópia das OS de ETM e finaliza as ok. Devolve {"conferidas", "finalizadas",
    "por_estado"}. Sem a cópia do Fracttal ou sem o livro das marcações, não faz nada (não dá para saber o que está aberto)."""
    from ..campo import visao
    from ..dados.conexao import banco
    from ..engenharia import etm as ETM
    from ..engenharia import etm_marcas as M
    from ..torres import engenharia as TE
    with app.app_context():
        d = ETM.dados()
        if not d.get("lido"):
            return {"conferidas": 0, "finalizadas": 0, "por_estado": {}, "erro": "sem a cópia das OS de ETM"}
        lido = M.ler(forcar=True)
        if not lido.get("lido_em"):
            return {"conferidas": 0, "finalizadas": 0, "por_estado": {}, "erro": "sem o livro das marcações"}
        cand = candidatas(d["os"], M.estado(lido["eventos"]))
        hoje = datetime.now(_BRT).date()
        # a OS no formato do livro (o `_os_para_gravar` da Engenharia), com a ligação ao cadastro lida UMA vez por rodada
        onde = TE._onde_do_cadastro()
        livro = []
        for o in cand:
            e = TE._na_etm(o)
            lig = onde(e.get("usina") or "", e.get("codigo") or "")
            livro.append((o, {"wid": e.get("wid"), "folio": e.get("os"), "codigo": e.get("codigo"),
                              "usina_id": lig.get("usina_id"), "usina_ligada_por": lig.get("ligada_por")}))
        base, sessao = banco()
        b = visao._Base()
        dias, falta = ler_dias({g["usina_id"] for _o, g in livro if g.get("usina_id")}, base, sessao, b, hoje)
        res, ok = {}, []
        for o, g in livro:
            uid = g.get("usina_id")
            sem = "a usina da OS não liga ao cadastro" if not uid else falta.get(uid, "")
            r = conferir(_dia(o.get("fim_iso")), dias.get(uid) or {}, hoje, sem_ligacao=sem)
            r["usina_id"] = uid
            res[str(o["wid"])] = r
            if r["estado"] == "ok":
                ok.append((g, r))
        feitas = finalizar(ok) if gravar and ok and app.config.get("GRIDCO_SQL_TOKEN") else []
        por = defaultdict(int)
        for r in res.values():
            por[r["estado"]] += 1
        _ESTADO.update(os=res, em=time.time(), erro="", finalizadas=_ESTADO["finalizadas"] + len(feitas))
        _guardar(app.config)
        if feitas:
            log.info("ETMs: a conferência automática finalizou %s OS (%s)", len(feitas), ", ".join(feitas[:30]))
        return {"conferidas": len(res), "finalizadas": len(feitas), "por_estado": dict(por)}


def pedir(app) -> None:
    """A rodada por trás, se a última tem mais de meia hora (a tela chama a cada visita; a subida, uma vez)."""
    with _TRAVA:
        if _ESTADO["rodando"] or time.time() - _ESTADO["em"] < A_CADA_S:
            return
        _ESTADO["rodando"] = True

    def ir():
        try:
            r = rodar(app)
            log.info("ETMs: conferência automática: %s", r)
        except Exception as ex:  # noqa: BLE001 — a próxima visita tenta de novo
            _ESTADO["erro"] = f"{type(ex).__name__}: {str(ex)[:160]}"
            _ESTADO["em"] = time.time() - A_CADA_S + 300          # tenta de novo em 5 min
            log.exception("ETMs: a conferência automática falhou")
        finally:
            _ESTADO["rodando"] = False
    threading.Thread(target=ir, daemon=True, name="nexus-etm-conferencia").start()


def ligar(app) -> None:
    """Na subida: carrega a conferência guardada e põe a rodada para andar de meia em meia hora (fora dos testes)."""
    try:
        with app.app_context():
            carregar(app.config)
    except Exception:            # noqa: BLE001
        log.warning("ETMs: a conferência guardada não carregou")
    if os.environ.get("PYTEST_CURRENT_TEST") or not app.config.get("NEXUS_ETM_CONFERENCIA", not app.config.get("TESTING")):
        return

    def laco():
        time.sleep(180)          # deixa a subida ler a cópia das OS de ETM primeiro
        while True:
            pedir(app)
            time.sleep(A_CADA_S)
    threading.Thread(target=laco, daemon=True, name="nexus-etm-conferencia-laco").start()
