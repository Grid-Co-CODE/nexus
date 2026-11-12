"""PCM → Almoxarifado → Usinas e almoxarifados (12/11/2026): o PCM marca, por usina, "sem almoxarifado", "compartilha" (usa o
almoxarifado da usina X) ou "próprio", e o App de Campo segue a marcação (o livro e o contrato em `nexus/dados/almox_usinas.py`).

O PCM: "Algumas usinas não tem almoxarifado ou compartilham os almoxarifados [...] poderia ter uma aba desse tipo no Nexus
pra gente ter essa noção"; o Levi: "Passa para o cadastro do nexus".

A lista: as usinas do cadastro que têm o local no Fracttal (o de-para `Fracttal · Classificação 1`), com o cliente do cadastro,
os almoxarifados que o Fracttal liga a cada uma (pela mesma de-para do Almoxarifado, `almoxarifado.montar`) e a marcação de
hoje, a do livro. A App Setting `ALMOX_COMPARTILHADOS` do App o Nexus não lê: a tela diz, no "!", que o par antigo dela segue
valendo para a usina não marcada.

As regras da marcação (`conferir`), relidas sob a trava da gravação:
- "compartilha" pede a dona, que não é a própria usina, nem uma usina "compartilha" (sem cadeia: a dona de uma não usa o de
  outra), nem uma "sem almoxarifado"; e a usina que é dona de outra não passa a compartilhar nem a "sem almoxarifado";
- a dona é do MESMO CLIENTE: pelo cliente do cadastro das duas usinas (`cliente_id`, a dimensão) e, quando uma delas não o
  tem, pelo 1º nó do local no Fracttal ("Cliente - Usina - UF"); a decisão guarda qual foi (`cliente_por`) e a tela diz;
- desmarcar tira a linha (a usina volta ao que o Fracttal e a App Setting dizem).
Quem pode programar (`telas.pode_programar`: administrador e setor PCM) marca e desmarca; quem só olha vê a lista. O POST de
outro site é recusado (`_de_outro_site`, a regra da casa).
"""
import unicodedata
from urllib.parse import urlencode

from flask import abort, current_app, redirect, render_template, request, session

from ..dados import almox_usinas as AU
from ..dados.fatos import SISTEMA_FRACTTAL
from ..prefixo import na_raiz

TELA = "/t/pcm/pecas/usinas"
ROTULO = {"sem_almoxarifado": "Sem almoxarifado", "compartilha": "Compartilha", "proprio": "Próprio"}
TOM = {"sem_almoxarifado": "alerta", "compartilha": "info", "proprio": "ok"}
SEM_MARCACAO = "sem_marcacao"
FILTRO_SITUACAO = {SEM_MARCACAO: "Sem marcação", **ROTULO}


def _txt(v) -> str:
    return "" if v is None else " ".join(str(v).split())


def _norm(v) -> str:
    t = unicodedata.normalize("NFKD", _txt(v)).encode("ascii", "ignore").decode().lower()
    return " ".join(t.split())


def cliente_do_local(local) -> str:
    """O 1º nó do local no Fracttal: "Cliente - Usina 2 - PI" é o "Cliente"."""
    return _txt(local).split(" - ")[0].strip()


# ── a lista ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def usinas_com_fracttal(b) -> dict:
    """{usina_id: {"id", "nome", "cliente_id", "cliente", "local", "locais"}}: as usinas do cadastro (não excluídas) com o local
    no Fracttal pela de-para. A que tem mais de um local fica com o 1º em ordem alfabética (o nome que vai ao livro), e a tela
    mostra todos."""
    from ..dados import fatos as D
    locais: dict[int, list] = {}
    for d in b.de_para:
        uid = D._id(d.get("usina_id"))
        if uid and _txt(d.get("sistema")) == SISTEMA_FRACTTAL and _txt(d.get("chave_externa")):
            locais.setdefault(uid, []).append(_txt(d.get("chave_externa")))
    out = {}
    for uid, ls in locais.items():
        u = b.por_id.get(uid)
        if not u or _txt(u.get("excluido")).lower() == "sim":
            continue
        cid = D._id(u.get("cliente_id"))
        ls = sorted(set(ls))
        out[uid] = {"id": uid, "nome": _txt(u.get("nome")) or ls[0], "cliente_id": cid,
                    "cliente": _txt(b.nome_cliente.get(cid)) if cid else "", "local": ls[0], "locais": ls}
    return out


def almoxarifados_por_usina(b) -> tuple[dict, bool]:
    """({usina_id: [nomes dos almoxarifados]}, lido): o que o Fracttal liga a cada usina, pela mesma conta da tela do
    Almoxarifado (a de-para do local do almoxarifado). Sem o ciclo do App lido agora, ({}, False): a tela diz que não leu."""
    from . import almoxarifado
    try:
        d = almoxarifado.montar().dados or {}
    except Exception:       # noqa: BLE001 — só enfeita a lista: sem ele, "não lido agora"
        return {}, False
    if d.get("estado") != "ok":
        return {}, False
    por: dict[int, dict] = {}
    vistos = set()
    for l in d.get("linhas", []):
        if l.get("usina_id"):
            por.setdefault(int(l["usina_id"]), {})[str(l["id_almox"])] = _txt(l.get("almox"))
            vistos.add(str(l["id_almox"]))
    por_nome: dict[str, list] = {}
    for uid, u in b.por_id.items():
        por_nome.setdefault(_norm(u.get("nome")), []).append(uid)
    for c in d.get("por_almoxarifado", []):
        donos = por_nome.get(_norm(c.get("usina"))) or []
        if str(c.get("id")) not in vistos and len(donos) == 1:      # o cartão sem saldo, pelo nome da usina (só o único)
            por.setdefault(donos[0], {})[str(c["id"])] = _txt(c.get("nome"))
    return {uid: sorted(set(a.values())) for uid, a in por.items()}, True


def _quando(iso) -> str:
    from datetime import datetime, timedelta, timezone
    try:
        d = datetime.fromisoformat(_txt(iso).replace("Z", "+00:00"))
    except ValueError:
        return ""
    return d.astimezone(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y às %H:%M")


def mesmo_cliente(u: dict, dona: dict) -> tuple[bool, str]:
    """(é do mesmo cliente, por onde): pelo cliente do cadastro quando as duas o têm; senão, pelo 1º nó do local no Fracttal."""
    if u.get("cliente_id") and dona.get("cliente_id"):
        return u["cliente_id"] == dona["cliente_id"], AU.CLIENTE_POR[0]
    return _norm(cliente_do_local(u["local"])) == _norm(cliente_do_local(dona["local"])), AU.CLIENTE_POR[1]


def _opcoes_de_dona(u: dict, usinas: dict, marcadas: dict) -> list[dict]:
    """As usinas que podem ser a dona desta: do mesmo cliente, outra, nem "compartilha" nem "sem almoxarifado"."""
    out = []
    for d in usinas.values():
        if d["id"] == u["id"] or (marcadas.get(d["id"]) or {}).get("situacao") in (AU.COMPARTILHA, "sem_almoxarifado"):
            continue
        if mesmo_cliente(u, d)[0]:
            out.append({"id": d["id"], "nome": d["nome"]})
    return sorted(out, key=lambda x: _norm(x["nome"]))


def montar(cfg, args, b=None) -> dict:
    """O que a tela mostra: as usinas (com o Fracttal e a marcação), os filtros de cliente e de situação e o que falta ler."""
    from ..campo import visao
    b = b or visao._Base()
    usinas = usinas_com_fracttal(b)
    almox, almox_lido = almoxarifados_por_usina(b)
    est = AU.ler(cfg)
    marcadas = est["marcadas"]
    f_cliente, f_sit = _txt(args.get("cliente")), _txt(args.get("situacao"))
    linhas = []
    for u in sorted(usinas.values(), key=lambda x: (_norm(x["cliente"] or cliente_do_local(x["local"])), _norm(x["nome"]))):
        m = marcadas.get(u["id"])
        sit = m["situacao"] if m else SEM_MARCACAO
        cliente = u["cliente"] or cliente_do_local(u["local"])
        if f_cliente and cliente != f_cliente:
            continue
        if f_sit and sit != f_sit:
            continue
        dona = usinas.get(m["usina_dona_id"]) if m and m.get("usina_dona_id") else None
        donas_de = sorted(usinas[x]["nome"] for x, l in marcadas.items() if l.get("usina_dona_id") == u["id"] and x in usinas)
        linhas.append({**u, "cliente_txt": cliente, "situacao": sit, "rotulo": ROTULO.get(sit, "Sem marcação"),
                       "tom": TOM.get(sit, "neutro"), "dona": dona["nome"] if dona else _txt((m or {}).get("usina_dona")),
                       "dona_id": (m or {}).get("usina_dona_id"), "marcada_em": _quando((m or {}).get("atualizado_em")),
                       "almoxarifados": almox.get(u["id"], []), "dona_de": donas_de,
                       "opcoes_dona": _opcoes_de_dona(u, usinas, marcadas)})
    clientes = sorted({u["cliente"] or cliente_do_local(u["local"]) for u in usinas.values()} - {""}, key=_norm)
    contas = {s: sum(1 for uid in usinas if (marcadas.get(uid) or {}).get("situacao") == s) for s in AU.SITUACOES}
    contas[SEM_MARCACAO] = sum(1 for uid in usinas if uid not in marcadas)
    return {"linhas": linhas, "n_usinas": len(usinas), "clientes": clientes, "filtro": {"cliente": f_cliente, "situacao": f_sit},
            "filtro_situacao": FILTRO_SITUACAO, "contas": contas, "almox_lido": almox_lido, "erro_livro": est["erro"],
            "rotulo": ROTULO}


# ── a marcação ────────────────────────────────────────────────────────────────────────────────────────────────────────
def conferir(usinas: dict, marcadas: dict, uid: int, situacao: str, dona_id: int | None) -> tuple[dict | None, dict]:
    """(a usina, a dona) se a marcação vale; senão `AU.Recusada` com o porquê. `situacao` vazia = desmarcar."""
    u = usinas.get(uid)
    if not u:
        raise AU.Recusada("Essa usina não está na lista (sem o local no Fracttal no cadastro): recarregue a página. Nada foi "
                          "gravado.")
    donas_desta = sorted(usinas[x]["nome"] for x, l in marcadas.items() if l.get("usina_dona_id") == uid and x in usinas)
    if not situacao:
        return u, {}
    if situacao not in AU.SITUACOES:
        raise AU.Recusada("Situação que não existe: recarregue a página. Nada foi gravado.")
    if situacao in (AU.COMPARTILHA, "sem_almoxarifado") and donas_desta:
        raise AU.Recusada(f"{u['nome']} é a dona do almoxarifado de {', '.join(donas_desta)}: ela não pode "
                          f"{'compartilhar o de outra' if situacao == AU.COMPARTILHA else 'ficar sem almoxarifado'}. Mude "
                          "aquelas antes. Nada foi gravado.")
    if situacao != AU.COMPARTILHA:
        if dona_id:
            raise AU.Recusada("A usina dona só vale em Compartilha: escolha Compartilha ou tire a dona. Nada foi gravado.")
        return u, {}
    if not dona_id:
        raise AU.Recusada("Compartilha pede a usina dona do almoxarifado. Nada foi gravado.")
    if dona_id == uid:
        raise AU.Recusada("A usina não compartilha o próprio almoxarifado: escolha outra usina, ou Próprio. Nada foi gravado.")
    dona = usinas.get(dona_id)
    if not dona:
        raise AU.Recusada("A usina dona não está na lista (sem o local no Fracttal no cadastro). Nada foi gravado.")
    sit_dona = (marcadas.get(dona_id) or {}).get("situacao")
    if sit_dona == AU.COMPARTILHA:
        raise AU.Recusada(f"{dona['nome']} já usa o almoxarifado de outra usina: sem cadeia, escolha a dona dela. Nada foi "
                          "gravado.")
    if sit_dona == "sem_almoxarifado":
        raise AU.Recusada(f"{dona['nome']} está marcada sem almoxarifado: não pode ser a dona. Nada foi gravado.")
    igual, por = mesmo_cliente(u, dona)
    if not igual:
        raise AU.Recusada(f"{dona['nome']} é de outro cliente (conferido pelo {por}): a dona tem de ser do mesmo cliente. "
                          "Nada foi gravado.")
    return u, {**dona, "cliente_por": por}


def marcar(cfg, usinas: dict, uid: int, situacao: str, dona_id: int | None, pessoa_hmac: str) -> str:
    """Grava a marcação (ou a desmarcação, `situacao` vazia) sob a trava, com as regras conferidas sobre o livro relido. O texto
    para a tela; `AU.Recusada` com o porquê (nada foi gravado)."""
    feito = {}

    def mudar(marcadas):
        u, dona = conferir(usinas, marcadas, uid, situacao, dona_id)
        feito.update(u=u, dona=dona)
        if not situacao:
            if uid not in marcadas:
                raise AU.Recusada(f"{u['nome']} já está sem marcação. Nada foi gravado.")
            return None, uid, AU.decisao(uid, AU.DESMARCADA, pessoa_hmac=pessoa_hmac)
        nova = AU.linha(uid, u["local"], situacao, dona.get("id"), dona.get("local", ""), pessoa_hmac)
        return nova, uid, AU.decisao(uid, situacao, dona.get("id"), dona.get("cliente_por", ""), pessoa_hmac)
    AU.trocar(cfg, mudar)
    u, dona = feito["u"], feito["dona"]
    if not situacao:
        return f"{u['nome']} ficou sem marcação: o App segue o Fracttal e a App Setting para ela."
    if situacao == AU.COMPARTILHA:
        return (f"{u['nome']} marcada: usa o almoxarifado de {dona['nome']} (o mesmo cliente, conferido pelo "
                f"{dona['cliente_por']}).")
    return f"{u['nome']} marcada: {ROTULO[situacao].lower()}."


def registrar(bp) -> None:
    from . import telas
    from .inventario import quem

    @bp.route("/pecas/usinas", endpoint="almox_usinas")
    def almox_usinas():
        """A aba Usinas e almoxarifados: a lista (todos que veem o Almoxarifado) e a marcação (quem pode programar)."""
        cfg = current_app.config
        return render_template("pcm/almox_usinas.html", d=montar(cfg, request.args), pode=telas.pode_programar(),
                               aviso=session.pop("pcm_almox_usinas_aviso", None))

    @bp.route("/pecas/usinas/marcar", methods=["POST"], endpoint="almox_usinas_marcar")
    def almox_usinas_marcar():
        if telas._de_outro_site():
            abort(403)
        if not telas.pode_programar():
            abort(403)
        cfg, f = current_app.config, request.form
        from ..campo import visao
        try:
            uid, dona = AU._int(f.get("usina")), AU._int(f.get("dona"))
            sit = _txt(f.get("situacao"))
            sit = "" if sit == SEM_MARCACAO else sit
            if not uid:
                raise AU.Recusada("Diga a usina. Nada foi gravado.")
            texto = marcar(cfg, usinas_com_fracttal(visao._Base()), uid, sit, dona if sit == AU.COMPARTILHA else None,
                           quem.colunas(cfg, quem.do_pedido()).get("pessoa_hmac", ""))
            session["pcm_almox_usinas_aviso"] = {"texto": texto, "ok": True}
        except (AU.Recusada, ValueError) as ex:
            session["pcm_almox_usinas_aviso"] = {"texto": str(ex), "ok": False}
        filtro = {"cliente": _txt(f.get("cliente")), "situacao": _txt(f.get("filtro_situacao"))}
        query = urlencode({k: v for k, v in filtro.items() if v})
        return redirect(na_raiz(TELA + (f"?{query}" if query else "") + (f"#u-{uid}" if uid else "")), code=303)
