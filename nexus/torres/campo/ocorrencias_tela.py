"""A tela Ocorrências do Campo · App (18/10/2026): só as rotas. A regra e o livro moram em `nexus/campo/ocorrencias.py`.

Fica num módulo à parte e é importada no fim do `__init__` da torre, porque precisa do `bp` e da `TORRE` definidos lá
(como o Clima e risco na Performance). Decisões do Levi (quiz de 18/10/2026): lista e quadro, criar e editar; o
Responsável O&M (pelo login do Fracttal) e os administradores gravam, os outros só veem. Gravar é sempre POST da própria
página (a régua da moldura: pedido de outro site é 403) e volta pela página da ocorrência (`?ok=`), para o F5 não gravar
de novo; a recusa volta na mesma página, com o porquê e o que a pessoa digitou.
"""
import re
from datetime import timedelta

from flask import abort, redirect, render_template, request, session, url_for

from ...campo import ocorrencias as O
from ...campo import visao
from ...dados import fatos as D
from . import TODOS, TORRE, _responsavel_do_login, _url, bp

OID = re.compile(r"[0-9a-f]{12}")
AVISOS = {"criada": "Ocorrência registrada", "dados": "Ocorrência salva", "acao": "Ação salva",
          "andamento": "Andamento registrado"}
QUADRO_FINALIZADAS = 20           # a coluna das finalizadas mostra as mais novas; o resto, pela lista
# a cor de cada criticidade (o selo da tela; na Visão geral, a etiqueta da usina usa a mesma régua em três cores)
COR_CRITICIDADE = {"muito_alta": "critico", "alta": "alerta", "media": "info", "baixa": "neutro"}
COR_STATUS = {"em_andamento": "info", "pausado": "alerta", "finalizado": "ok"}
COR_SITUACAO = {"a_fazer": "neutro", "em_andamento": "info", "concluida": "ok"}


def _cadastro() -> dict:
    """As usinas do cadastro (as mobilizadas abrem para registrar), o Responsável O&M de cada uma e quem está na tela
    (o Responsável O&M que entrou pelo Fracttal, o mesmo da Visão do responsável). O cadastro que não abre não derruba a
    tela: `erro` diz."""
    try:
        b = visao._Base()
        usinas, por_pessoa = {}, {}
        for uid, u in b.por_id.items():
            resp = b.responsavel_da_usina(uid)
            usinas[uid] = {"usina_id": uid, "nome": str(u.get("nome") or f"Usina {uid}"), "uf": str(u.get("uf") or ""),
                           "responsavel": resp, "mobilizada": uid in b.mobilizadas,
                           "cliente": b.nome_cliente.get(D._id(u.get("cliente_id")), "")}
            pid = D._id(u.get("responsavel_om_id"))
            if pid and uid in b.mobilizadas:
                por_pessoa[pid] = resp
        logado = _responsavel_do_login({"responsaveis_por_pessoa": por_pessoa})
        erro = ""
    except Exception as e:      # noqa: BLE001 — sem o cadastro, a tela diz e mostra o que der
        usinas, logado, erro = {}, "", f"Não consegui ler o cadastro ({type(e).__name__})"
    return {"usinas": usinas, "logado": logado, "erro": erro,
            "mobilizadas": sorted((u for u in usinas.values() if u["mobilizada"]),
                                  key=lambda u: visao._norm_nome(u["nome"]))}


def _quem_esta(cad: dict) -> dict:
    """Quem está na tela: `pode` (administrador ou Responsável O&M) e `grava` (pode e entrou com um login de pessoa: a
    senha de administrador não diz quem é, e o histórico guarda quem fez)."""
    usuario = session.get("usuario") or {}
    pode = O.pode_editar(bool(session.get("admin")), cad["logado"])
    return {"usuario": usuario, "pode": pode, "grava": bool(pode and usuario.get("email"))}


def _usina(cad: dict, uid) -> dict:
    return cad["usinas"].get(uid) or {"usina_id": uid, "nome": f"Usina {uid}" if uid else "—", "uf": "",
                                      "responsavel": visao.SEM_RESPONSAVEL, "cliente": "", "mobilizada": False}


def _comum(**k) -> dict:
    return dict(torre=TORRE, tela=TORRE.tela("ocorrencias"), criticidades=O.CRITICIDADES, status_rot=O.STATUS,
                situacoes=O.SITUACOES, cor_crit=COR_CRITICIDADE, cor_status=COR_STATUS, cor_situacao=COR_SITUACAO,
                piso=O.PISO.isoformat(), hoje=visao._agora().date().isoformat(), **k)


def _proxima(o: dict) -> dict | None:
    """A próxima ação em aberto: a do prazo mais perto; sem prazo em nenhuma, a primeira em aberto."""
    abertas = [a for a in o["acoes"] if a["aberta"]]
    com = sorted((a for a in abertas if a["prazo"]), key=lambda a: a["prazo"])
    return (com or abertas or [None])[0]


@bp.route("/ocorrencias")
def ocorrencias():
    """A lista (na ordem do prazo da próxima ação em aberto; abre nas abertas) ou o quadro (uma coluna por status), com
    os filtros de usina, Responsável O&M, status e criticidade. O Responsável O&M que entrou pelo Fracttal abre nas
    usinas dele; "Todos" vai como "*", como na Visão do responsável."""
    cad = _cadastro()
    quem = _quem_esta(cad)
    lido = O.ler()
    cofre = O.cofre_ou_nada()
    est = O.estado(lido["eventos"], cofre)
    pedido = request.args.get("responsavel")
    responsavel = cad["logado"] if pedido is None else ("" if pedido == TODOS else pedido)
    usina = D._id(request.args.get("usina"))
    ver = "quadro" if request.args.get("ver") == "quadro" else "lista"
    st = request.args.get("status") or "abertas"
    st = st if st in O.STATUS or st in ("abertas", TODOS) else "abertas"
    crit = request.args.get("criticidade", "")
    crit = crit if crit in O.CRITICIDADES else ""
    itens = []
    for o in O.ordenar(list(est.values())):
        u = _usina(cad, o["usina_id"])
        if usina and o["usina_id"] != usina:
            continue
        if responsavel and u["responsavel"] != responsavel:
            continue
        if crit and o["criticidade"] != crit:
            continue
        itens.append({"o": o, "u": u, "proxima": _proxima(o)})
    lista = [i for i in itens if st == TODOS or (st == "abertas" and i["o"]["aberta"]) or i["o"]["status"] == st]
    colunas = [(s, rot, [i for i in itens if i["o"]["status"] == s]) for s, rot in O.STATUS.items()]
    nomes = sorted({u["responsavel"] for u in cad["mobilizadas"]} | ({responsavel} if responsavel else set()),
                   key=lambda n: (n == visao.SEM_RESPONSAVEL, visao._norm_nome(n)))
    abertas = [i for i in itens if i["o"]["aberta"]]
    numeros = {"abertas": len(abertas), "atrasadas": sum(i["o"]["atrasada"] for i in abertas),
               "sem_plano": sum(not i["o"]["acoes_abertas"] for i in abertas)}
    return render_template("campo/ocorrencias.html", **_comum(
        cad=cad, quem=quem, lido=lido, sem_chave=cofre is None, lista=lista, colunas=colunas,
        quadro_max=QUADRO_FINALIZADAS, ver=ver, f={"responsavel": responsavel, "usina": usina, "status": st,
                                                    "criticidade": crit},
        opcoes_responsavel=nomes, numeros=numeros, todos=TODOS, url=_url))


def _form_vazio(usina=None) -> dict:
    return {"usina_id": str(usina or ""), "criticidade": "media", "status": "em_andamento",
            "inicio": visao._agora().date().isoformat()}


@bp.route("/ocorrencias/nova", methods=["GET", "POST"])
def ocorrencia_nova():
    """O formulário de uma ocorrência nova; o POST grava e leva à página dela."""
    cad = _cadastro()
    quem = _quem_esta(cad)
    if request.method == "GET":
        return render_template("campo/ocorrencia_nova.html", **_comum(
            cad=cad, quem=quem, form=_form_vazio(D._id(request.args.get("usina"))), erro=""))
    from ..moldura import _de_outro_site
    if _de_outro_site():
        abort(403)
    form = request.form.to_dict()
    try:
        nova = O.criar(form, quem["usuario"], quem["pode"])
    except O.Recusada as e:
        return render_template("campo/ocorrencia_nova.html", **_comum(cad=cad, quem=quem, form=form, erro=str(e))), \
            (200 if quem["pode"] else 403)
    except Exception as e:      # noqa: BLE001 — banco fora, trava: a tela diz, o que foi digitado não se perde
        return render_template("campo/ocorrencia_nova.html", **_comum(
            cad=cad, quem=quem, form=form,
            erro=f"Não consegui gravar no banco ({type(e).__name__}). Tente de novo em instantes"))
    return redirect(url_for("torre_campo.ocorrencia", oid=nova["ocorrencia_id"], ok="criada"))


def _pagina(oid: str, cad: dict, quem: dict, erro: str = "", form: dict | None = None, qual: str = "",
            status: int = 200):
    """A página de uma ocorrência: os dados, o plano de ação e o andamento; `form`/`qual` devolvem o que a pessoa
    digitou no formulário recusado (`dados`, `acao:<id ou nova>` ou `andamento`)."""
    if not OID.fullmatch(oid or ""):
        abort(404)
    lido = O.ler()
    cofre = O.cofre_ou_nada()
    o = O.estado(lido["eventos"], cofre).get(oid)
    if o is None:
        if lido["erro"]:
            return render_template("campo/ocorrencia.html", **_comum(cad=cad, quem=quem, o=None, lido=lido,
                                                                     sem_chave=cofre is None)), 503
        abort(404)
    try:
        pessoas = O.pessoas_do_cadastro() if quem["grava"] else []
    except Exception:           # noqa: BLE001 — sem o cadastro, a lista do responsável sai vazia e a tela diz
        pessoas = []
    nome_pessoa = {p["id"]: p["nome"] for p in pessoas}
    aviso = AVISOS.get(request.args.get("ok", "")) if not erro else ""
    u = _usina(cad, o["usina_id"])
    # o formulário de editar abre com a ocorrência como está; a usina que saiu das mobilizadas continua escolhível nele
    atual = {"titulo": o["titulo"], "usina_id": o["usina_id"], "codigo_ativo": o["cod"], "criticidade": o["criticidade"],
             "status": o["status"], "inicio": o["inicio"].isoformat() if o["inicio"] else "",
             "fim": o["fim"].isoformat() if o["fim"] else "", "descricao": o["descricao"], "chamado": o["chamado"],
             "os": o["os"]}
    usinas_do_form = cad["mobilizadas"] + ([u] if o["usina_id"] and not u["mobilizada"] else [])
    prazo_max = (visao._agora().date() + timedelta(days=365 * O.PRAZO_ANOS)).isoformat()
    return render_template("campo/ocorrencia.html", **_comum(
        cad=cad, quem=quem, o=o, u=u, lido=lido, sem_chave=cofre is None, pessoas=pessoas, nome_pessoa=nome_pessoa,
        erro=erro, aviso=aviso, form=form or {}, qual=qual, atual=atual, usinas_do_form=usinas_do_form,
        prazo_max=prazo_max)), status


@bp.route("/ocorrencias/<oid>")
def ocorrencia(oid):
    cad = _cadastro()
    return _pagina(oid, cad, _quem_esta(cad))


def _gravar(oid: str, qual: str, fazer):
    """O POST de um formulário da página: grava e volta à página (`?ok=`), ou volta com a recusa e o que foi digitado."""
    from ..moldura import _de_outro_site
    if _de_outro_site():
        abort(403)
    if not OID.fullmatch(oid or ""):
        abort(404)
    cad = _cadastro()
    quem = _quem_esta(cad)
    form = request.form.to_dict()
    chave = f"acao:{form.get('acao_id') or 'nova'}" if qual == "acao" else qual
    try:
        fazer(form, quem)
    except O.Recusada as e:
        return _pagina(oid, cad, quem, erro=str(e), form=form, qual=chave, status=200 if quem["pode"] else 403)
    except Exception as e:      # noqa: BLE001 — banco fora, trava: a tela diz, o que foi digitado não se perde
        return _pagina(oid, cad, quem, form=form, qual=chave,
                       erro=f"Não consegui gravar no banco ({type(e).__name__}). Tente de novo em instantes")
    destino = {"acao": "#plano", "andamento": "#andamento"}.get(qual, "")
    return redirect(url_for("torre_campo.ocorrencia", oid=oid, ok=qual) + destino)


@bp.route("/ocorrencias/<oid>/dados", methods=["POST"])
def ocorrencia_dados(oid):
    return _gravar(oid, "dados", lambda form, quem: O.editar(oid, form, quem["usuario"], quem["pode"]))


@bp.route("/ocorrencias/<oid>/acao", methods=["POST"])
def ocorrencia_acao(oid):
    def fazer(form, quem):
        pessoas = O.pessoas_do_cadastro() if quem["pode"] else []
        O.salvar_acao(oid, form, quem["usuario"], quem["pode"], pessoas)
    return _gravar(oid, "acao", fazer)


@bp.route("/ocorrencias/<oid>/andamento", methods=["POST"])
def ocorrencia_andamento(oid):
    return _gravar(oid, "andamento",
                   lambda form, quem: O.registrar_andamento(oid, form.get("texto"), quem["usuario"], quem["pode"]))
