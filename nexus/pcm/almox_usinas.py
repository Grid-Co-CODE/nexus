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
import re
import unicodedata
from urllib.parse import urlencode

from flask import abort, current_app, redirect, render_template, request, session

from ..dados import almox_usinas as AU
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
    """O 1º nó do local no Fracttal: "Cliente - Usina 2 - PI" é o "Cliente". O "(sem Classificação 1) " da frente (o
    agrupamento do Fracttal para o ativo sem classificação) não é do cliente."""
    return re.sub(r"^\([^)]*\)\s*", "", _txt(local)).split(" - ")[0].strip()


# ── a lista ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def usinas_com_fracttal(b) -> dict:
    """{usina_id: {"id", "nome", "cliente_id", "cliente", "local", "locais"}}: as usinas do cadastro (não excluídas) com o local
    no Fracttal pela de-para. O `local` (o nome que vai ao livro, e por onde o App acha a usina) é o MESMO que os Técnicos por
    usina mandam ao App (`tecnicos_usina._fracttal`, o de `nome_no_fracttal`): nunca o "(sem Classificação 1) …" quando a
    usina tem o nome de verdade (a revisão de 12/11/2026, C1: o 1º em ordem alfabética era ele em 4 usinas reais, e a marcação
    não valeria no App). `locais` são todos, na mesma ordem."""
    from ..dados import fatos as D
    from .tecnicos_usina import _fracttal
    fr = _fracttal(b)
    out = {}
    for uid, ls in fr.items():
        u = b.por_id.get(uid)
        if not u or _txt(u.get("excluido")).lower() == "sim" or not ls:
            continue
        cid = D._id(u.get("cliente_id"))
        out[uid] = {"id": uid, "nome": _txt(u.get("nome")) or ls[0], "cliente_id": cid,
                    "cliente": _txt(b.nome_cliente.get(cid)) if cid else "", "local": ls[0], "locais": list(ls)}
    return out


def fora_da_lista(b, usinas: dict, marcadas: dict) -> list[dict]:
    """As usinas marcadas no livro que saíram da lista (a revisão, I2): excluídas do cadastro, sem o local no Fracttal no de-para
    ou fora do cadastro. Seguem no livro que o App lê, com o nome de antes, e contam na regra sem cadeia: a tela as mostra à
    parte, com o Desmarcar."""
    out = []
    for uid, m in sorted(marcadas.items()):
        if uid in usinas:
            continue
        u = b.por_id.get(uid)
        porque = ("fora do cadastro" if not u else "excluída do cadastro" if _txt(u.get("excluido")).lower() == "sim"
                  else "sem o local no Fracttal no de-para")
        out.append({"id": uid, "nome": _txt((u or {}).get("nome")) or m.get("usina") or f"usina {uid}", "porque": porque,
                    "situacao": m["situacao"], "rotulo": ROTULO.get(m["situacao"], m["situacao"]),
                    "tom": TOM.get(m["situacao"], "neutro"), "usina": _txt(m.get("usina")),
                    "dona": _txt(m.get("usina_dona")), "marcada_em": _quando(m.get("atualizado_em"))})
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


def _nome_de(usinas: dict, marcadas: dict, nomes_cadastro: dict | None, uid) -> str:
    if uid in usinas:
        return usinas[uid]["nome"]
    return _txt((nomes_cadastro or {}).get(uid)) or _txt((marcadas.get(uid) or {}).get("usina")) or f"usina {uid}"


def montar(cfg, args, b=None) -> dict:
    """O que a tela mostra: as usinas (com o Fracttal e a marcação), as marcadas que saíram da lista, os filtros de cliente e
    de situação e o que falta ler. Sem nenhuma leitura boa do livro (`livro_lido` falso), nada de número nem de selo: a
    marcação de cada usina não se sabe (a revisão, M4)."""
    from ..campo import visao
    b = b or visao._Base()
    usinas = usinas_com_fracttal(b)
    almox, almox_lido = almoxarifados_por_usina(b)
    est = AU.ler(cfg)
    marcadas = est["marcadas"]
    nomes_cadastro = {uid: _txt(u.get("nome")) for uid, u in b.por_id.items()}
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
        dona_id = (m or {}).get("usina_dona_id")
        dona = usinas.get(dona_id) if dona_id else None
        donas_de = sorted(_nome_de(usinas, marcadas, nomes_cadastro, x) for x, l in marcadas.items()
                          if l.get("usina_dona_id") == u["id"])
        # o nome que está no livro é o do Fracttal de hoje? (a revisão, I1: o App acha a usina por ele)
        velho = bool(m) and (_txt(m.get("usina")) != u["local"]
                             or bool(dona and _txt(m.get("usina_dona")) != dona["local"]))
        linhas.append({**u, "cliente_txt": cliente, "situacao": sit, "rotulo": ROTULO.get(sit, "Sem marcação"),
                       "tom": TOM.get(sit, "neutro"),
                       "dona": dona["nome"] if dona else (_nome_de(usinas, marcadas, nomes_cadastro, dona_id) if dona_id else ""),
                       "dona_id": dona_id, "marcada_em": _quando((m or {}).get("atualizado_em")), "nome_velho": velho,
                       "almoxarifados": almox.get(u["id"], []), "dona_de": donas_de,
                       "opcoes_dona": _opcoes_de_dona(u, usinas, marcadas)})
    clientes = sorted({u["cliente"] or cliente_do_local(u["local"]) for u in usinas.values()} - {""}, key=_norm)
    contas = {s: sum(1 for uid in usinas if (marcadas.get(uid) or {}).get("situacao") == s) for s in AU.SITUACOES}
    contas[SEM_MARCACAO] = sum(1 for uid in usinas if uid not in marcadas)
    return {"linhas": linhas, "n_usinas": len(usinas), "clientes": clientes, "filtro": {"cliente": f_cliente, "situacao": f_sit},
            "filtro_situacao": FILTRO_SITUACAO, "contas": contas, "almox_lido": almox_lido, "erro_livro": est["erro"],
            "livro_lido": est.get("lido_em") is not None, "fora": fora_da_lista(b, usinas, marcadas), "rotulo": ROTULO}


# ── a marcação ────────────────────────────────────────────────────────────────────────────────────────────────────────
def conferir(usinas: dict, marcadas: dict, uid: int, situacao: str, dona_id: int | None,
             nomes_cadastro: dict | None = None) -> tuple[dict | None, dict]:
    """(a usina, a dona) se a marcação vale; senão `AU.Recusada` com o porquê. `situacao` vazia = desmarcar, que vale também para
    a usina marcada que saiu da lista (a revisão, I2). Todas as linhas do livro contam na regra sem cadeia, as de fora da lista
    também."""
    u = usinas.get(uid)
    if not u:
        if not situacao and uid in marcadas:
            u = {"id": uid, "nome": _nome_de(usinas, marcadas, nomes_cadastro, uid)}
        else:
            raise AU.Recusada("Essa usina não está na lista (sem o local no Fracttal no cadastro): recarregue a página. Nada "
                              "foi gravado.")
    donas_desta = sorted(_nome_de(usinas, marcadas, nomes_cadastro, x) for x, l in marcadas.items()
                         if l.get("usina_dona_id") == uid)
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


def marcar(cfg, usinas: dict, uid: int, situacao: str, dona_id: int | None, pessoa_hmac: str,
           nomes_cadastro: dict | None = None) -> str:
    """Grava a marcação (ou a desmarcação, `situacao` vazia) sob a trava, com as regras conferidas sobre o livro relido, e renova
    o nome do local de todas as linhas (`AU.trocar` com os `local` de agora). A mesma marcação não grava outra decisão (a
    revisão, M2): só renova os nomes, se mudaram, ou diz "Nada mudou". O texto para a tela; `AU.Recusada` com o porquê."""
    feito = {}

    def mudar(marcadas):
        u, dona = conferir(usinas, marcadas, uid, situacao, dona_id, nomes_cadastro)
        feito.update(u=u, dona=dona)
        atual = marcadas.get(uid)
        if not situacao:
            if not atual:
                raise AU.Recusada(f"{u['nome']} já está sem marcação. Nada foi gravado.")
            return None, uid, AU.decisao(uid, AU.DESMARCADA, pessoa_hmac=pessoa_hmac)
        if atual and atual["situacao"] == situacao and atual.get("usina_dona_id") == (dona.get("id") or None):
            feito["igual"] = True
            return atual, uid, None
        nova = AU.linha(uid, u["local"], situacao, dona.get("id"), dona.get("local", ""), pessoa_hmac)
        return nova, uid, AU.decisao(uid, situacao, dona.get("id"), dona.get("cliente_por", ""), pessoa_hmac)
    try:
        AU.trocar(cfg, mudar, nomes={x: v["local"] for x, v in usinas.items()})
    except AU.Recusada as ex:
        if str(ex) == AU.NADA_MUDOU:
            raise AU.Recusada(f"Nada mudou: {feito['u']['nome']} já está marcada assim. Nada foi gravado.") from None
        raise
    u, dona = feito["u"], feito["dona"]
    if feito.get("igual"):
        return f"{u['nome']} já estava marcada assim: os nomes do Fracttal no livro foram atualizados."
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
            pessoa = quem.do_pedido()
            hmac_ = quem.colunas(cfg, pessoa).get("pessoa_hmac", "")
            if pessoa.get("email") and not hmac_:
                # a pessoa com e-mail sem o código: sem a NEXUS_PESSOA_HMAC no servidor, a marcação iria sem quem marcou (a
                # revisão, M6; os Técnicos por usina recusam igual). A senha de administrador não tem e-mail e marca sem pessoa
                raise AU.Recusada("Este Nexus não tem a NEXUS_PESSOA_HMAC: a marcação iria sem quem marcou. Nada foi gravado.")
            b = visao._Base()
            texto = marcar(cfg, usinas_com_fracttal(b), uid, sit, dona if sit == AU.COMPARTILHA else None, hmac_,
                           {x: _txt(u.get("nome")) for x, u in b.por_id.items()})
            session["pcm_almox_usinas_aviso"] = {"texto": texto, "ok": True}
        except (AU.Recusada, ValueError) as ex:
            session["pcm_almox_usinas_aviso"] = {"texto": str(ex), "ok": False}
        filtro = {"cliente": _txt(f.get("cliente")), "situacao": _txt(f.get("filtro_situacao"))}
        query = urlencode({k: v for k, v in filtro.items() if v})
        return redirect(na_raiz(TELA + (f"?{query}" if query else "") + (f"#u-{uid}" if uid else "")), code=303)
