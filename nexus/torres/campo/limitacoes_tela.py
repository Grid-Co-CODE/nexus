"""Usinas 360° › Limitações de potência (19/11/2026): a tela do cadastro. A regra e o livro moram em
`nexus/campo/limitacoes.py`; aqui só o HTTP. Fica num módulo à parte, importado no fim do `__init__` da torre, porque precisa
do `bp` (como o `cliente_tela` e o `equipe_tela`).

- `GET /t/campo/limitacoes`: a lista (as em andamento primeiro) e o formulário. `?usina=<id>` traz os inversores do Fracttal
  daquela usina para marcar; `?editar=<limitacao_id>` abre o formulário com o registro.
- `POST /t/campo/limitacoes`: `acao` = salvar, encerrar ou excluir. Só da própria página (pedido de outro site é 403).
  Recusa volta à tela com o motivo e o que foi digitado; o que gravou vai para a lista (303), sem reenvio no F5.
"""
import uuid

from flask import abort, redirect, render_template, request, session

from ...campo import limitacoes as L
from ...prefixo import na_raiz
from . import TORRE, bp

CAMPOS = ("usina_id", "potencia_nominal_kw", "limite_pct", "causa", "responsabilidade", "clipagem", "inicio", "fim",
          "comentario_cliente", "comentario_geral", "limitacao_id", "novo_id", "todos")


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


def _pagina(form: dict | None = None, erro: str = "", status: int = 200):
    lido = L.ler()
    lista = L.vigentes(lido)
    try:
        nomes = L.usinas()
    except Exception as e:      # noqa: BLE001 — sem o cadastro, a página abre e diz; não dá para escolher a usina
        nomes, erro = {}, erro or f"Não li o cadastro das usinas agora ({type(e).__name__})"
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
    resp = render_template(
        "campo/limitacoes.html", torre=TORRE, tela=TORRE.tela("limitacoes"), lista=lista, nomes=nomes,
        usinas=sorted(nomes.items(), key=lambda x: x[1].lower()), form=form, inversores=inv["lista"],
        erro_inv=inv["erro"], erro=erro, erro_leitura=lido.get("erro") or "", pode=bool(_conta().get("email")),
        responsabilidades=L.RESPONSABILIDADES, clipagem=L.CLIPAGEM, editando=bool(form.get("limitacao_id")))
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
    return redirect(na_raiz("/t/campo/limitacoes"), code=303)
