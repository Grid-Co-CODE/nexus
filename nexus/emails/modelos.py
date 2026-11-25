"""Os e-mails criados pela tela (25/11/2026, a fase 4): Base › E-mails automáticos › Novo e-mail.

Levi: "eu também gostaria de poder criar e-mails automáticos"; "Tem e-mails que vão ser mandados só com dados do Nexus".
Um MODELO diz: o nome, o assunto, um texto de abertura, as fontes (`fontes.FONTES`: o que o Nexus já calcula), como sai
(um e-mail só, ou um por Responsável UFV com as usinas dele), para quem e em cópia (papéis do Registro mestre,
`papeis.py`, ou e-mails), a agenda (todo dia, toda semana, todo mês, ou só quando alguém manda) e se pula quem não tem
pendência.

O livro `nexus_email_modelos · fato_email_modelo`: só acréscimo, 1 linha = 1 versão de 1 modelo; vale a mais nova de
cada um. Em claro só o id, a hora, quem mudou (o código HMAC) e se foi excluído; o modelo inteiro vai cifrado (o texto
livre pode citar alguém, e a lista pode ter e-mails: a API lê sem login), na chave da NEXUS_PESSOA_HMAC (a mesma família
da cifra das regras, outro info). O modelo novo NASCE DESLIGADO (uma regra "desligado" no livro das regras do Nexus): só
liga quem viu a prévia.
"""
from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone

from . import fontes as F
from . import modelo as M
from . import papeis as P
from .tipos import Tipo

LIVRO, NOME_LIVRO, ABA = "nexus_email_modelos", "Nexus · e-mails criados pela tela", "fato_email_modelo"
CAB = ("modelo_id", "alterado_em", "alterado_por", "excluido", "dados")
INFO_CIFRA = b"nexus:email:modelo/v1"
ENVIOS = {"um_so": "Um e-mail só, para todos da lista",
          "por_responsavel": "Um por Responsável UFV, com as usinas dele"}
FREQ = {"manual": "Só quando alguém manda (pela tela)", "diaria": "Todo dia", "semanal": "Toda semana",
        "mensal": "Todo mês"}
DIAS_SEMANA = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
BRT = timezone(timedelta(hours=-3))
TTL_S = 60
_CACHE: dict = {}
_TRAVA = threading.Lock()


class Recusado(ValueError):
    """Nada foi gravado; o texto diz por quê."""


# ── a cifra ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _aead(chave_base: str):
    from ..cadastro import cifra
    return cifra.aead_derivada(str(chave_base or "").strip().encode("utf-8"), INFO_CIFRA)


def cifrar(m: dict, chave_base: str) -> str:
    from ..cadastro import cifra
    return cifra.cifrar_com(_aead(chave_base), json.dumps(m, ensure_ascii=False), f"nexus/email-modelo/{m['id']}")


def abrir(linha: dict, chave_base: str) -> dict | None:
    from ..cadastro import cifra
    mid = str(linha.get("modelo_id") or "").strip()
    try:
        m = json.loads(cifra.decifrar_com(_aead(chave_base), str(linha.get("dados") or ""), f"nexus/email-modelo/{mid}"))
    except (cifra.CifraErro, ValueError):
        return None
    return m if isinstance(m, dict) and m.get("id") == mid else None


# ── o livro ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _arquivo(cfg):
    from ..campo.emails_controle import _arquivo_local
    return _arquivo_local(cfg)


def _ler_cru(cfg) -> list[dict]:
    loc = _arquivo(cfg)
    if loc is not None:
        try:
            return [dict(x) for x in json.loads(loc.read_text(encoding="utf-8")).get("modelos:" + ABA) or []]
        except FileNotFoundError:
            return []
    if cfg.get("TESTING"):
        return list(_CACHE.get("teste") or [])
    from ..dados import livros
    from ..dados.conexao import banco_de
    base, sessao = banco_de(cfg)
    a = livros.abas_conferidas(base, sessao, LIVRO, (ABA,))
    return list(livros._linhas(base, sessao, a[ABA])) if ABA in a else []


def _gravar_cru(cfg, linhas: list[dict]) -> None:
    loc = _arquivo(cfg)
    if loc is not None:
        loc.parent.mkdir(parents=True, exist_ok=True)
        try:
            d = json.loads(loc.read_text(encoding="utf-8"))
        except FileNotFoundError:
            d = {}
        d["modelos:" + ABA] = linhas
        tmp = loc.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(loc)
        return
    if cfg.get("TESTING"):
        _CACHE["teste"] = list(linhas)
        return
    token = cfg.get("GRIDCO_SQL_TOKEN")
    if not token:
        raise Recusado("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN): nada foi gravado.")
    from ..dados import livros
    from ..dados.conexao import banco_de
    base, sessao = banco_de(cfg)
    corpo = [[x.get(c) for c in CAB] for x in linhas]
    livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), corpo)}, base=base, token=token, sessao=sessao)


def ler(cfg, forcar: bool = False) -> dict:
    """{"linhas", "erro"}, guardado 1 minuto; a leitura que falha devolve a última boa com o erro."""
    g = _CACHE.get("g")
    if g and not forcar and time.time() - g["t"] < TTL_S and not cfg.get("TESTING"):
        return g
    _CACHE["cfg"] = cfg          # o registro dos tipos, fora de um pedido (o laço), lê com esta
    try:
        g = {"linhas": _ler_cru(cfg), "erro": "", "t": time.time()}
    except Exception as ex:      # noqa: BLE001
        return dict(g, erro=type(ex).__name__) if g else {"linhas": [], "erro": type(ex).__name__, "t": 0}
    _CACHE["g"] = g
    return g


def limpar() -> None:
    _CACHE.pop("g", None)


def vigentes(cfg) -> dict:
    """{id: modelo} dos que valem (a versão mais nova de cada um, sem os excluídos e sem os que não abrem)."""
    chave = cfg.get("NEXUS_PESSOA_HMAC")
    ultima: dict[str, dict] = {}
    for ln in ler(cfg)["linhas"]:
        mid = str(ln.get("modelo_id") or "")
        if mid and (mid not in ultima or str(ln.get("alterado_em") or "") >= str(ultima[mid].get("alterado_em") or "")):
            ultima[mid] = ln
    out = {}
    for mid, ln in ultima.items():
        if str(ln.get("excluido") or "").lower() == "sim":
            continue
        m = abrir(ln, chave)
        if m:
            out[mid] = dict(m, alterado_em=str(ln.get("alterado_em") or ""), alterado_por=str(ln.get("alterado_por") or ""))
    return out


def tipos() -> dict:
    """Os tipos dos modelos, para o registro dos tipos (`tipos.criados`). Fora de um pedido ou do app, nenhum."""
    from flask import current_app, has_app_context
    cfg = current_app.config if has_app_context() else _CACHE.get("cfg")
    if cfg is None:
        return {}
    out = {}
    for mid, m in vigentes(cfg).items():
        out[mid] = Tipo(mid, m["nome"], quando(m), destino(m), criado=True, extra={"modelo": m})
    return out


def quando(m: dict) -> str:
    ag = m.get("agenda") or {}
    f, hora = ag.get("freq") or "manual", ag.get("hora") or "07:00"
    if f == "diaria":
        return f"todo dia{' útil' if ag.get('uteis') else ''} às {hora}"
    if f == "semanal":
        return f"toda {DIAS_SEMANA[int(ag.get('dia') or 0)]} às {hora}"
    if f == "mensal":
        return f"todo dia {int(ag.get('dia') or 1)} do mês às {hora}"
    return "quando alguém manda, pela tela"


def destino(m: dict) -> str:
    nomes = P.nomes()
    partes = [nomes.get(x, "um e-mail da lista") for x in m.get("para") or []]
    if m.get("envio") == "por_responsavel":
        partes = ["o Responsável UFV de cada grupo de usinas"] + [x for x in partes if x != P.DA_USINA["responsavel_ufv"]]
    cc = [nomes.get(x, "um e-mail da lista") for x in m.get("cc") or []]
    txt = " · ".join(dict.fromkeys(partes)) or "ninguém ainda"
    return txt + (f" (cópia: {' · '.join(dict.fromkeys(cc))})" if cc else "")


# ── salvar e excluir ────────────────────────────────────────────────────────────────────────────────────────────────
def _slug(nome: str) -> str:
    s = unicodedata.normalize("NFD", nome).encode("ascii", "ignore").decode("ascii").lower()
    return "_".join(re.findall(r"[a-z0-9]+", s))[:30] or "email"


def _hora_ok(h: str) -> str:
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", h or ""):
        raise Recusado("A hora vai como HH:MM (ex.: 07:00): nada foi gravado.")
    return h


def normalizar(d: dict, conhecidos=(), nomes=()) -> dict:
    """O modelo como a tela o manda, conferido. `Recusado` com o porquê."""
    from ..campo.emails_controle import Recusada, conferir_destinatarios, conferir_motivo
    nome = " ".join(str(d.get("nome") or "").split())[:80]
    assunto = " ".join(str(d.get("assunto") or "").split())[:150]
    if len(nome) < 4 or len(assunto) < 4:
        raise Recusado("Dê um nome e um assunto ao e-mail (ao menos 4 letras cada): nada foi gravado.")
    texto = str(d.get("texto") or "").strip()[:2000]
    fs = [f for f in d.get("fontes") or [] if f in F.FONTES]
    if not fs and not texto:
        raise Recusado("O e-mail precisa de um texto ou de uma fonte (o que ele traz): nada foi gravado.")
    envio = d.get("envio") if d.get("envio") in ENVIOS else "um_so"

    def lista(xs):
        out, emails = [], []
        for x in xs or []:
            x = str(x or "").strip().lower()
            if x in P.nomes():
                out.append(x)
            elif x:
                emails.append(x)
        try:
            emails = conferir_destinatarios(emails, conhecidos)
        except Recusada as ex:
            raise Recusado(str(ex)) from None
        return list(dict.fromkeys(out + emails))
    para, cc = lista(d.get("para")), lista(d.get("cc"))
    if envio == "um_so" and not [x for x in para if x not in P.DA_USINA]:
        raise Recusado("Um e-mail só precisa de quem recebe fora das usinas (um setor ou um e-mail): os papéis da usina "
                       "valem no \"um por Responsável UFV\". Nada foi gravado.")
    ag = d.get("agenda") or {}
    freq = ag.get("freq") if ag.get("freq") in FREQ else "manual"
    agenda = {"freq": freq, "hora": _hora_ok(str(ag.get("hora") or "07:00")) if freq != "manual" else "",
              "uteis": bool(ag.get("uteis")) if freq == "diaria" else False}
    if freq == "semanal":
        agenda["dia"] = min(max(int(ag.get("dia") or 0), 0), 6)
    if freq == "mensal":
        agenda["dia"] = min(max(int(ag.get("dia") or 1), 1), 28)
    try:
        # o texto vai cifrado, mas o nome e o assunto viram a referência e a linha do tipo na tela: sem e-mail neles
        conferir_motivo(nome + " " + assunto, nomes)
    except Recusada:
        raise Recusado("O nome e o assunto do e-mail não podem ter e-mail nem nome de pessoa (eles aparecem no registro "
                       "dos envios): cite o papel. Nada foi gravado.") from None
    return {"nome": nome, "assunto": assunto, "texto": texto, "fontes": fs, "envio": envio, "para": para, "cc": cc,
            "agenda": agenda, "pular_vazio": bool(d.get("pular_vazio"))}


def salvar(cfg, dados: dict, *, quem_hmac: str, modelo_id: str = "", conhecidos=(), nomes=()) -> dict:
    """Grava uma versão do modelo. O novo ganha o id "nx_<nome>" e nasce desligado. {"id", "novo"}."""
    chave = str(cfg.get("NEXUS_PESSOA_HMAC") or "").strip()
    if not chave:
        raise Recusado("Este Nexus não tem a NEXUS_PESSOA_HMAC: o modelo não tem como ir cifrado. Nada foi gravado.")
    m = normalizar(dados, conhecidos, nomes)
    with _TRAVA:
        est = ler(cfg, forcar=True)
        if est["erro"]:
            raise Recusado(f"Não consegui ler o livro dos modelos agora ({est['erro']}): nada foi gravado.")
        linhas = list(est["linhas"])
        existentes = {str(x.get("modelo_id") or "") for x in linhas}
        novo = not modelo_id
        if novo:
            base = "nx_" + _slug(m["nome"])
            modelo_id, n = base, 2
            while modelo_id in existentes or modelo_id in ("nx_teste",):
                modelo_id, n = f"{base}_{n}", n + 1
        elif modelo_id not in existentes:
            raise Recusado("Este e-mail não existe mais: nada foi gravado.")
        m["id"] = modelo_id
        em = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ultimo = max((str(x.get("alterado_em") or "") for x in linhas if x.get("modelo_id") == modelo_id), default="")
        if em <= ultimo:
            em = (datetime.strptime(ultimo, "%Y-%m-%dT%H:%M:%SZ") + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        linhas.append({"modelo_id": modelo_id, "alterado_em": em, "alterado_por": quem_hmac or "", "excluido": "não",
                       "dados": cifrar(m, chave)})
        _gravar_cru(cfg, linhas)
        limpar()
    if novo:
        from ..campo import emails_controle as EC
        EC.limpar()
        EC.publicar(cfg, tipo=modelo_id, ligado=False, modo="normal", destinatarios=[], substitui=False,
                    motivo="E-mail novo nasce desligado, até a prévia ser conferida", quem_hmac=quem_hmac,
                    alvo=EC.NEXUS)
    return {"id": modelo_id, "novo": novo}


def excluir(cfg, modelo_id: str, *, quem_hmac: str) -> None:
    with _TRAVA:
        est = ler(cfg, forcar=True)
        if est["erro"]:
            raise Recusado(f"Não consegui ler o livro dos modelos agora ({est['erro']}): nada foi gravado.")
        atual = vigentes(cfg).get(modelo_id)
        if not atual:
            raise Recusado("Este e-mail não existe mais.")
        m = {k: v for k, v in atual.items() if k not in ("alterado_em", "alterado_por")}
        em = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if em <= atual["alterado_em"]:
            em = (datetime.strptime(atual["alterado_em"], "%Y-%m-%dT%H:%M:%SZ") + timedelta(seconds=1)).strftime(
                "%Y-%m-%dT%H:%M:%SZ")
        _gravar_cru(cfg, list(est["linhas"]) + [{"modelo_id": modelo_id, "alterado_em": em, "alterado_por": quem_hmac,
                                                 "excluido": "sim", "dados": cifrar(m, cfg.get("NEXUS_PESSOA_HMAC"))}])
        limpar()


# ── as mensagens de uma vez ─────────────────────────────────────────────────────────────────────────────────────────
def montar(cfg, m: dict, agora: datetime, *, ctx: P.Contexto | None = None, rodada: str = "",
           usinas: list[dict] | None = None) -> dict:
    """{"mensagens": [...], "avisos": [...], "grupos": n}. `rodada` entra na chave (o dia da agenda, ou a hora do
    "mandar agora"): a mesma rodada não entra duas vezes na fila."""
    from ..dados import fatos as D
    from ..hseq.email_semanal import _no_nexus
    from .tipos import mensagem
    ctx = ctx or P.contexto(cfg)
    avisos = list(ctx.erros)
    fs = [F.FONTES[f] for f in m.get("fontes") or [] if f in F.FONTES]
    precisa = any(f.por_usina for f in fs) or m.get("envio") == "por_responsavel"
    if usinas is None:
        usinas = F.usinas_da_visao(cfg) if precisa else []
    rodada = rodada or agora.astimezone(BRT).strftime("%Y-%m-%d")

    def corpo(us, link):
        partes, tem = [M.paragrafo(m["texto"])] if m.get("texto") else [], not fs
        for f in fs:
            h, t = f.render(us, link)
            partes.append(h)
            tem = tem or t
        partes.append(M.botao("Abrir no Nexus", link))
        return "".join(partes), tem

    out = []
    if m.get("envio") == "por_responsavel":
        grupos: dict = {}
        for u in usinas:
            pid = D._id((ctx.b.por_id.get(u["usina_id"]) or {}).get("responsavel_om_id")) if ctx.b else None
            grupos.setdefault(pid, []).append(u)
        for pid, us in sorted(grupos.items(), key=lambda t: str(t[0])):
            if not pid:
                avisos.append(f"{len(us)} usina(s) sem Responsável UFV na ficha ficaram de fora")
                continue
            nome = ctx.b.nome_da_pessoa(pid, "Responsável") if ctx.b else "Responsável"
            if not P.resolver(ctx, ["responsavel_ufv"], us[0]["usina_id"]):
                # o e-mail é DELE (as usinas dele): sem o e-mail do responsável, não vai só para a cópia
                avisos.append(f"{nome}: sem e-mail no Registro mestre nem no Fracttal, ficou de fora")
                continue
            para = P.resolver(ctx, ["responsavel_ufv"] + list(m.get("para") or []), us[0]["usina_id"])
            for u in us[1:]:          # os papéis da usina valem para cada usina do grupo (o supervisor de cada região)
                para += [x for x in P.resolver(ctx, m.get("para") or [], u["usina_id"]) if x["email"] not in
                         {y["email"] for y in para}]
            cc = [x for x in P.resolver(ctx, m.get("cc") or [], us[0]["usina_id"]) if x["email"] not in
                  {y["email"] for y in para}]
            html, tem = corpo(us, _no_nexus("/t/campo/responsaveis", r=pid, modo="painel"))
            if fs and not tem and m.get("pular_vazio"):
                continue
            out.append(dict(mensagem(tipo=m["id"], referencia=f"{len(us)} usina(s) · responsável {pid}",
                                     chave=f"{m['id']}|{rodada}|{pid}", para=para, cc=cc, assunto=m["assunto"],
                                     html=M.pagina(m["assunto"], html, sobre=m["nome"])), _quem=nome))
    else:
        para = P.resolver(ctx, [x for x in m.get("para") or [] if x not in P.DA_USINA])
        cc = [x for x in P.resolver(ctx, [x for x in m.get("cc") or [] if x not in P.DA_USINA])
              if x["email"] not in {y["email"] for y in para}]
        if not para:
            avisos.append("ninguém da lista tem e-mail: o e-mail não sai")
        else:
            html, tem = corpo(usinas, _no_nexus("/t/campo/responsaveis", modo="painel"))
            if not (fs and not tem and m.get("pular_vazio")):
                out.append(dict(mensagem(tipo=m["id"], referencia=f"{len(usinas)} usina(s)" if usinas else m["nome"],
                                         chave=f"{m['id']}|{rodada}|todos", para=para, cc=cc, assunto=m["assunto"],
                                         html=M.pagina(m["assunto"], html, sobre=m["nome"])), _quem="todos da lista"))
    return {"mensagens": out, "avisos": avisos}


def devido(m: dict, agora: datetime) -> str | None:
    """O dia (AAAA-MM-DD) da rodada que já deveria ter saído hoje, ou None. Só o mesmo dia: o servidor que volta às 9h
    manda o das 7h; o de ontem não sai mais (chegaria velho)."""
    ag = m.get("agenda") or {}
    f = ag.get("freq") or "manual"
    if f == "manual" or not ag.get("hora"):
        return None
    t = agora.astimezone(BRT)
    if t.strftime("%H:%M") < ag["hora"]:
        return None
    if f == "diaria" and ag.get("uteis") and t.weekday() >= 5:
        return None
    if f == "semanal" and t.weekday() != int(ag.get("dia") or 0):
        return None
    if f == "mensal" and t.day != int(ag.get("dia") or 1):
        return None
    return t.strftime("%Y-%m-%d")
