"""O e-mail semanal das pendências da Segurança (24/10/2026).

A TST: "Receber report semanal das pendências por email, pra mim e pro supervisor responsável". Levi escolheu mandar
pelo App de Campo, que já manda e-mail (o Não das luvas vai à TST): o Nexus monta o resumo de cada destinatário toda
segunda de manhã e publica no livro `nexus_hseq_email` (registrado no catálogo antes da 1ª gravação); o App lê, manda e
diz o que mandou.

Quem recebe:
- a TST: todas as pessoas do setor Segurança (Base → Integração Fracttal), pelo código do e-mail delas (`pessoa_hmac`),
  com as pendências de todas as usinas;
- cada Responsável UFV (o Responsável O&M da ficha da usina, o mesmo dos cartões da Mesa), só com as usinas dele, pelo
  código do e-mail: o da Integração Fracttal (a pessoa ligada ao usuário do Fracttal) ou, sem ele, o do e-mail da ficha.
  Quem não tem código fica sem e-mail e a prévia diz.

O que vai no livro (a API é compartilhada, regra 8): o código da pessoa (HMAC) e o número dela no cadastro, nunca o nome
nem o e-mail; o corpo leva só usinas, clientes, números e o link para a Mesa filtrada pelo número da pessoa (`?r=`),
sem o nome. Cada linha vai assinada (HMAC com a chave derivada da NEXUS_PESSOA_HMAC, rótulo `nexus:hseq:email`).

Ligado por `NEXUS_HSEQ_EMAIL_AUTO=1` (desligado sem ela: o livro só nasce quando o App estiver pronto para ler), a
segunda depois das 07:00 de Brasília, uma vez por semana (a semana que já está no livro não é publicada de novo).
"""
import hashlib
import hmac
import logging
import threading
from datetime import datetime, timedelta, timezone

from flask import current_app

from ..dados import fatos as D
from ..dados import livros

log = logging.getLogger(__name__)

LIVRO, NOME_LIVRO, ABA = "nexus_hseq_email", "Nexus · e-mail semanal das pendências da Segurança", "fato_email_pendencias"
CAB = ("semana", "gerado_em", "data_id", "papel", "pessoa_id", "destinatario_hmac", "assunto", "corpo_texto", "corpo_html",
       "assinatura")
ROTULO_CHAVE = b"nexus:hseq:email"
ENDERECO = "https://app.gridco.com.br"       # o Nexus no servidor (na raiz desde a fase 4): o link do e-mail
HORA = 7                                     # segunda, 07:00 de Brasília
POR_USINA_MAX = 25                           # as usinas no corpo; a planilha leva todas
_BRT = timezone(timedelta(hours=-3))
_LACO = {"thread": None, "parar": threading.Event(), "ultimo": None}


def _agora() -> datetime:
    return datetime.now(_BRT)


def semana(d) -> str:
    """A semana ISO do dia ('2026-W44')."""
    a, s, _ = d.isocalendar()
    return f"{a}-W{s:02d}"


def assinatura(linha: dict, chave_base: str) -> str:
    """HMAC-SHA256 em hex minúsculo de "email|semana|destinatario_hmac|assunto|corpo_texto", com a chave derivada da
    NEXUS_PESSOA_HMAC (`ROTULO_CHAVE`). Sem chave: "" (o App não manda a linha)."""
    base = (chave_base or "").strip()
    if not base:
        return ""
    chave = hmac.new(base.encode("utf-8"), ROTULO_CHAVE, hashlib.sha256).digest()
    partes = ("email", linha.get("semana"), linha.get("destinatario_hmac"), linha.get("assunto"), linha.get("corpo_texto"))
    return hmac.new(chave, "|".join(D._txt(p) for p in partes).encode("utf-8"), hashlib.sha256).hexdigest()


# ── quem recebe ─────────────────────────────────────────────────────────────────────────────────────────────────────
def destinatarios(cfg) -> dict:
    """{"tst": [{pessoa_id, hmac}], "responsaveis": {nome: {pessoa_id, hmac}}, "erro"}. O nome fica só aqui dentro (os
    cartões da Mesa agrupam pelo nome); no livro vão o número e o código."""
    from ..auth.setor_telas import setor_de_cada_codigo
    from ..cadastro import setores as S
    from ..campo import visao
    from ..campo.ligacao_cadastro import mapas_de
    out = {"tst": [], "responsaveis": {}, "erro": ""}
    b = visao._Base()
    try:
        st = S.ler(visao._base(), visao._sessao())
    except Exception as e:      # noqa: BLE001 — sem os setores, a TST fica sem e-mail e a prévia diz
        st = {"decisoes": [], "setores": [], "erro": type(e).__name__}
    out["erro"] = st.get("erro") or ""
    decisoes = st.get("decisoes") or []
    seg = {s["setor_id"] for s in S.ativos(st.get("setores") or []) if S._norm(s.get("nome")) == "seguranca"}
    por_codigo = setor_de_cada_codigo(decisoes)
    pid_do_codigo = {d["pessoa_hmac"]: d.get("pessoa_id") for d in sorted(decisoes, key=lambda x: x["decidida_em"])
                     if d.get("pessoa_hmac")}
    out["tst"] = [{"pessoa_id": pid_do_codigo.get(c), "hmac": c} for c, sid in sorted(por_codigo.items()) if sid in seg]
    # o código de cada pessoa: o do usuário do Fracttal ligado a ela e, sem ele, o do e-mail da ficha
    codigo_da = {}
    for c, pid in mapas_de(cfg, [], b.pessoas)["hmac"].items():
        codigo_da.setdefault(pid, c)
    for d in sorted(decisoes, key=lambda x: x["decidida_em"]):
        if d.get("pessoa_id") and d.get("pessoa_hmac"):
            codigo_da[d["pessoa_id"]] = d["pessoa_hmac"]
    for u in b.usinas:
        pid = D._id(u.get("responsavel_om_id"))
        if pid:
            nome = b.nome_da_pessoa(pid, "Responsável")
            out["responsaveis"].setdefault(nome, {"pessoa_id": pid, "hmac": codigo_da.get(pid, "")})
    return out


# ── o que vai no e-mail ─────────────────────────────────────────────────────────────────────────────────────────────
def _plural(n, um, varios):
    return f"{n} {um if n == 1 else varios}"


ROT_AGIR = {"pts": ("PT parada", "PTs paradas"), "vencidos": ("extintor vencido", "extintores vencidos"),
            "nr": ("extintor não reconhecido", "extintores não reconhecidos"),
            "sem_luvas": ("usina sem luvas", "usinas sem luvas")}
ROT_ATENCAO = {"perto": ("extintor perto de vencer", "extintores perto de vencer"),
               "sem_atual": ("extintor sem atualização", "extintores sem atualização"),
               "luvas_semv": ("usina sem verificar as luvas", "usinas sem verificar as luvas"),
               "ronda": ("nova ronda pedida", "novas rondas pedidas")}


def _por_usina(L) -> list[dict]:
    """As usinas com o que pede ação agora, a que tem mais primeiro: {usina, cliente, n: {chave: número}, total}."""
    from . import extintores as EXT
    g = {}
    for k in ROT_AGIR:
        for x in L[k]:
            u = g.setdefault((EXT.valor_do_filtro(x, "cliente"), x.get("usina") or ""),
                             {"usina": x.get("usina") or "", "cliente": EXT.valor_do_filtro(x, "cliente"), "n": {}})
            u["n"][k] = u["n"].get(k, 0) + 1
    for u in g.values():
        u["total"] = sum(u["n"].values())
    return sorted(g.values(), key=lambda u: (-u["total"], u["usina"].lower()))


def montar(L: dict, *, papel: str, hoje, link: str) -> dict:
    """{assunto, corpo_texto, corpo_html} do e-mail de um destinatário (`L` = as listas da Mesa já filtradas)."""
    from html import escape
    agir = {k: len(L[k]) for k in ROT_AGIR}
    atencao = {k: len(L[k]) for k in ROT_ATENCAO}
    total = sum(agir.values())
    quem = "nas suas usinas" if papel == "responsavel" else "de todas as usinas"
    assunto = (f"Pendências da Segurança {quem} · semana de {hoje:%d/%m}: "
               + (_plural(total, "para agir", "para agir") if total else "nada para agir agora"))
    usinas = _por_usina(L)
    t = [f"Pendências da Segurança {quem}, {hoje:%d/%m/%Y}.", "", "Para agir agora"]
    t += [f"- {_plural(agir[k], *ROT_AGIR[k])}" for k in ROT_AGIR]
    t += ["", "Atenção"] + [f"- {_plural(atencao[k], *ROT_ATENCAO[k])}" for k in ROT_ATENCAO]
    linhas_u = []
    for u in usinas[:POR_USINA_MAX]:
        partes = " · ".join(_plural(n, *ROT_AGIR[k]) for k, n in u["n"].items())
        linhas_u.append((f"{u['usina']} ({u['cliente']})", partes))
    if linhas_u:
        t += ["", "Por usina"] + [f"- {a}: {b}" for a, b in linhas_u]
        if len(usinas) > POR_USINA_MAX:
            t.append(f"- e mais {len(usinas) - POR_USINA_MAX} usinas: veja no Nexus")
    planilha = link.replace("/t/hseq/mesa", "/t/hseq/mesa/pendencias.xlsx", 1)
    t += ["", f"Ver no Nexus: {link}", f"Planilha com caso a caso: {planilha}", "",
          "E-mail automático do Nexus (Segurança · HSEQ), toda segunda de manhã."]
    h = [f"<p><b>Pendências da Segurança {escape(quem)}</b>, {hoje:%d/%m/%Y}.</p>", "<p><b>Para agir agora</b></p><ul>"]
    h += [f"<li>{escape(_plural(agir[k], *ROT_AGIR[k]))}</li>" for k in ROT_AGIR] + ["</ul><p><b>Atenção</b></p><ul>"]
    h += [f"<li>{escape(_plural(atencao[k], *ROT_ATENCAO[k]))}</li>" for k in ROT_ATENCAO] + ["</ul>"]
    if linhas_u:
        h += ["<p><b>Por usina</b></p><ul>"] + [f"<li><b>{escape(a)}</b>: {escape(b)}</li>" for a, b in linhas_u]
        if len(usinas) > POR_USINA_MAX:
            h.append(f"<li>e mais {len(usinas) - POR_USINA_MAX} usinas: veja no Nexus</li>")
        h.append("</ul>")
    h += [f'<p><a href="{escape(link)}">Ver no Nexus</a> · <a href="{escape(planilha)}">Planilha com caso a caso</a></p>',
          "<p><small>E-mail automático do Nexus (Segurança · HSEQ), toda segunda de manhã.</small></p>"]
    return {"assunto": assunto, "corpo_texto": "\n".join(t), "corpo_html": "\n".join(h)}


def _link(**args) -> str:
    from urllib.parse import urlencode

    from ..prefixo import na_raiz
    q = urlencode({k: v for k, v in args.items() if v})
    return ENDERECO + na_raiz("/t/hseq/mesa") + (f"?{q}" if q else "")


def da_semana(cfg, hoje=None) -> dict:
    """{linhas: as linhas do livro desta semana, sem_codigo: [nomes dos responsáveis sem código], erros}: o e-mail de
    cada destinatário, com as mesmas contas da Mesa. Quem não tem pendência nenhuma não recebe."""
    from ..torres.hseq import _pendencias
    agora = _agora()
    hoje = hoje or agora.date()
    sem = semana(hoje)
    try:
        dest = destinatarios(cfg)
    except Exception as e:      # noqa: BLE001 — sem o cadastro, ninguém recebe e a prévia diz
        dest = {"tst": [], "responsaveis": {}, "erro": "", "falhou": type(e).__name__}
    linhas, sem_codigo = [], []
    base = {"semana": sem, "gerado_em": agora.isoformat(timespec="seconds"), "data_id": int(hoje.strftime("%Y%m%d"))}
    geral = _pendencias({})
    erros = dict(geral["erros"], **({"cadastro": dest["falhou"]} if dest.get("falhou") else {}))
    if not erros:
        corpo = montar(geral["listas"], papel="tst", hoje=hoje, link=_link())
        for p in dest["tst"]:
            linhas.append(dict(base, papel="tst", pessoa_id=p["pessoa_id"] or "", destinatario_hmac=p["hmac"], **corpo))
        for nome, p in sorted(dest["responsaveis"].items()):
            L = _pendencias({"responsavel": nome})["listas"]
            if not any(L.values()):
                continue
            if not p["hmac"]:
                sem_codigo.append(nome)
                continue
            linhas.append(dict(base, papel="responsavel", pessoa_id=p["pessoa_id"], destinatario_hmac=p["hmac"],
                               **montar(L, papel="responsavel", hoje=hoje, link=_link(r=p["pessoa_id"]))))
    chave = cfg.get("NEXUS_PESSOA_HMAC")
    for x in linhas:
        x["assinatura"] = assinatura(x, chave)
    return {"linhas": linhas, "sem_codigo": sem_codigo, "erros": erros, "semana": sem,
            "tst_sem_setor": dest["erro"], "n_tst": len(dest["tst"]),
            # só para a prévia (o nome nunca vai ao livro)
            "nomes": {p["pessoa_id"]: nome for nome, p in dest["responsaveis"].items()}}


# ── o livro ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _banco(cfg):
    from ..pcm.motivos import _banco as banco
    return banco(cfg)


def ler(cfg) -> list[dict]:
    base, sessao = _banco(cfg)
    a = livros.abas(base, sessao, LIVRO)
    return list(livros._linhas(base, sessao, a[ABA])) if ABA in a else []


def publicar(cfg, hoje=None) -> dict:
    """Publica as linhas da semana (uma vez: a semana que já está no livro não volta). {publicadas, semana, ...}."""
    if not str(cfg.get("NEXUS_PESSOA_HMAC") or "").strip():
        return {"publicadas": 0, "erro": "sem a NEXUS_PESSOA_HMAC: o App não mandaria linha sem assinatura"}
    token = cfg.get("GRIDCO_SQL_TOKEN")
    if not token:
        return {"publicadas": 0, "erro": "sem a GRIDCO_SQL_TOKEN"}
    d = da_semana(cfg, hoje)
    if d["erros"]:
        return {"publicadas": 0, "semana": d["semana"], "erro": f"fonte sem leitura: {', '.join(d['erros'])}"}
    velhas = ler(cfg)
    if any(D._txt(x.get("semana")) == d["semana"] for x in velhas):
        return {"publicadas": 0, "semana": d["semana"], "erro": ""}
    vazio = (lambda v: None if v in ("", None) else v)      # noqa: E731
    corpo = [[vazio(x.get(c)) for c in CAB] for x in velhas + d["linhas"]]
    base, sessao = _banco(cfg)
    livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), corpo)}, base=base, token=token, sessao=sessao)
    return {"publicadas": len(d["linhas"]), "semana": d["semana"], "sem_codigo": len(d["sem_codigo"]), "erro": ""}


def devido(agora: datetime) -> bool:
    return agora.weekday() == 0 and agora.hour >= HORA


def ligar(app):
    """O laço: a cada 10 min, na segunda depois das 07:00, publica a semana (uma vez). Só com NEXUS_HSEQ_EMAIL_AUTO=1."""
    if _LACO["thread"] is not None or str(app.config.get("NEXUS_HSEQ_EMAIL_AUTO") or "0").strip() != "1":
        return

    def laco():
        espera = 120
        while not _LACO["parar"].wait(espera):
            espera = 600
            if not devido(_agora()):
                continue
            with app.app_context():
                try:
                    _LACO["ultimo"] = publicar(current_app.config)
                    if _LACO["ultimo"].get("publicadas") or _LACO["ultimo"].get("erro"):
                        log.info("e-mail semanal da Segurança: %s", _LACO["ultimo"])
                except Exception as e:      # noqa: BLE001 — o laço não morre por uma volta
                    _LACO["ultimo"] = {"erro": f"{type(e).__name__}: {e}"[:300]}
                    log.exception("e-mail semanal da Segurança")

    _LACO["thread"] = threading.Thread(target=laco, name="nexus-hseq-email", daemon=True)
    _LACO["thread"].start()
