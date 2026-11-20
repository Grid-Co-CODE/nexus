"""Performance › Limitações de potência (19/11/2026): a tela do cadastro. A regra e o livro moram em
`nexus/campo/limitacoes.py`; aqui só o HTTP. Fica num módulo à parte, importado no fim do `__init__` da torre, porque precisa
do `bp` (como o `sala_tela` e o `coletas_tela`).

Levi, 19/11/2026: "crie [...] um campo onde as pessoas consigam colocar limitações de potência dos inversores" e, à noite,
"limitação de potência quero na parte de performance e quero algo bem feito e construído!". A tela abre no parecer e nos
cartões (o que está em andamento agora), depois as usinas com o mapa dos inversores do Fracttal aceso onde há limitação, e
as encerradas fechadas no fim. O formulário mora num painel que o botão abre.

- `GET /t/performance/limitacoes`: o painel. `?usina=<id>` abre o formulário com os inversores daquela usina (e avisa o que
  já está limitado); `?editar=<limitacao_id>` abre o formulário com o registro; `?nova=1` só abre o formulário.
- `POST /t/performance/limitacoes`: `acao` = salvar, encerrar ou excluir. Só da própria página (pedido de outro site é 403).
  Recusa volta à tela com o motivo e o que foi digitado; o que gravou vai para o painel (303), sem reenvio no F5.
"""
import uuid
from datetime import datetime

from flask import abort, redirect, render_template, request, session

from ...campo import limitacoes as L
from ...prefixo import na_raiz
from . import TORRE, bp

CAMPOS = ("usina_id", "potencia_nominal_kw", "limite_pct", "causa", "responsabilidade", "clipagem", "inicio", "fim",
          "comentario_cliente", "comentario_geral", "limitacao_id", "novo_id", "todos")
ENDERECO = "/t/performance/limitacoes"


def _conta() -> dict:
    return session.get("usuario") or {}


def _form_de(v: dict) -> dict:
    """O registro no formato do formulário (datetime-local, os números com vírgula)."""
    def num(x):
        return "" if x is None else (f"{x:g}".replace(".", ","))
    return {"usina_id": str(v["usina_id"]), "inversores": v["inversores"], "todos": "1" if v["todos"] else "",
            "potencia_nominal_kw": num(v["potencia_nominal_kw"]), "limite_pct": num(v["limite_pct"]),
            "causa": v["causa"], "responsabilidade": v["responsabilidade"], "clipagem": v["clipagem"],
            "inicio": v["inicio"].strftime("%Y-%m-%dT%H:%M") if v["inicio"] else "",
            "fim": v["fim"].strftime("%Y-%m-%dT%H:%M") if v["fim"] else "",
            "comentario_cliente": v["comentario_cliente"], "comentario_geral": v["comentario_geral"],
            "limitacao_id": v["limitacao_id"]}


def _grupos(lista: list[dict], fichas: dict) -> list[dict]:
    """As limitações EM ANDAMENTO por usina, com o mapa dos inversores do Fracttal de cada uma; a usina com mais potência
    retida primeiro."""
    por = {}
    for v in lista:
        if v["situacao"] == "em_andamento":
            por.setdefault(v["usina_id"], []).append(v)
    out = []
    for uid, vs in por.items():
        f = fichas.get(uid) or {}
        inv = L.inversores_da_usina(uid)
        out.append({"usina_id": uid, "nome": f.get("nome") or f"usina {uid}", "cliente": f.get("cliente") or "",
                    "lista": vs, "mapa": L.mapa_da_usina(uid, lista, inv["lista"]), "erro_inv": inv["erro"],
                    "kw": sum(v["kw_limitados"] or 0 for v in vs)})
    return sorted(out, key=lambda g: (-g["kw"], g["nome"].lower()))


def _pagina(form: dict | None = None, erro: str = "", status: int = 200):
    lido = L.ler()
    lista = L.vigentes(lido)
    try:
        fichas = L.fichas_usinas()
    except Exception as e:      # noqa: BLE001 — sem o cadastro, a página abre e diz; não dá para escolher a usina
        fichas, erro = {}, erro or f"Não li o cadastro das usinas agora ({type(e).__name__})"
    agora = datetime.now(L._BRT)
    for v in lista:
        v["duracao"] = L.duracao_txt(v, agora)
    form = dict(form or {})
    editar = request.args.get("editar") or form.get("limitacao_id") or ""
    if editar and not form.get("usina_id"):
        v = next((x for x in lista if x["limitacao_id"] == editar), None)
        if v:
            form = _form_de(v)
    uid = L._id(form.get("usina_id") or request.args.get("usina"))
    form.setdefault("usina_id", str(uid or ""))
    form.setdefault("novo_id", uuid.uuid4().hex[:16])
    inv = L.inversores_da_usina(uid) if uid else {"lista": [], "erro": ""}
    mapa_form = L.mapa_da_usina(uid, lista, inv["lista"], menos=form.get("limitacao_id") or "") if uid else []
    abrir = bool(uid or (erro and form) or request.args.get("nova") or editar)
    resp = render_template(
        "performance/limitacoes.html", torre=TORRE, tela=TORRE.tela("limitacoes"), lista=lista,
        grupos=_grupos(lista, fichas), encerradas=[v for v in lista if v["situacao"] == "encerrada"],
        resumo=L.resumo(lista), fichas=fichas,
        usinas=sorted(((u, f["nome"]) for u, f in fichas.items()), key=lambda x: x[1].lower()),
        form=form, mapa_form=mapa_form, erro_inv=inv["erro"], erro=erro, erro_leitura=lido.get("erro") or "",
        pode=bool(_conta().get("email")), clipagem=L.CLIPAGEM, editando=bool(form.get("limitacao_id")),
        abrir=abrir, br=L._br, endereco=ENDERECO)
    return resp, status


@bp.route("/limitacoes", methods=["GET", "POST"])
def limitacoes():
    if request.method == "GET":
        return _pagina()
    from ...auth.origem import de_outro_site as _de_outro_site
    if _de_outro_site():
        abort(403)
    acao = request.form.get("acao") or "salvar"
    form = {k: request.form.get(k, "") for k in CAMPOS}
    form["inversores"] = request.form.getlist("inversores")
    try:
        if acao == "encerrar":
            L.encerrar(request.form.get("limitacao_id") or "", _conta())
        elif acao == "excluir":
            L.excluir(request.form.get("limitacao_id") or "", _conta())
        else:
            L.salvar(form, _conta())
    except L.Recusada as e:
        return _pagina(form if acao == "salvar" else None, erro=str(e), status=400)
    except Exception as e:      # noqa: BLE001 — banco fora: a tela diz, e o que foi digitado não se perde
        return _pagina(form if acao == "salvar" else None,
                       erro=f"Não consegui gravar no banco ({type(e).__name__}). Tente de novo em instantes", status=503)
    return redirect(na_raiz(ENDERECO), code=303)
