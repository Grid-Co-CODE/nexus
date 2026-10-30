"""Quem assina a PT no Nexus: o login do Fracttal do OS Creator (Levi, 05/10/2026: "utilize o login do fractal do OS
Creator Web que já dá certo!").

O OS Creator roda dentro do Nexus (`nexus/torres/oscreator/ponte.py`) com sessão própria no cookie `os_sessao`, que o
navegador só manda para /os. Por isso estas rotas moram em /os/_nexus/...: o roteador do Flask casa a parte fixa antes
do `/os/<path>` da ponte, e a sessão do OS Creator é aberta aqui com a chave dele, só para ler o e-mail de quem entrou.
O portão do Nexus vale antes (quem não entrou no Nexus não chega aqui).
"""
import base64
import json
import time
from urllib.parse import quote, urlsplit

from flask import Blueprint, current_app, jsonify, redirect, request, session

from ...campo import decisao_pt, pt_fracttal, visao
from ...prefixo import na_raiz, sem_raiz

bp_assinatura = Blueprint("campo_assinatura", __name__)


def _carga(jwt: str) -> dict | None:
    """O que o JWT do Fracttal diz (e-mail, validade), sem pedido ao Fracttal. Token opaco = None."""
    try:
        p = jwt.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p.encode()))
    except Exception:          # noqa: BLE001
        return None


def _jwt_vivo(jwt: str) -> bool:
    """O JWT ainda vale, pelo `exp` dele (a cota do Fracttal é da empresa inteira: nada de pedido só para conferir).
    Token opaco vale enquanto a sessão do OS Creator valer (12 h)."""
    c = _carga(jwt)
    exp = (c or {}).get("exp")
    return bool(jwt) and (not exp or float(exp) > time.time())


def _sessao_os() -> tuple[str, dict]:
    """(JWT, conta) do login do Fracttal pelo OS Creator, ou ("", {}) sem login ou com o token vencido."""
    from ..oscreator import ponte
    clone = ponte.clone(current_app._get_current_object())
    s = clone.session_interface.open_session(clone, request) or {}
    jwt = str(s.get("jwt") or "")
    if not jwt or not _jwt_vivo(jwt):
        return "", {}
    return jwt, s.get("conta") or {}


def quem_assina() -> dict:
    """{"email", "nome"} de quem entrou no Fracttal pelo OS Creator, ou {} (sem login, ou o token venceu)."""
    jwt, conta = _sessao_os()
    if not jwt:
        return {}
    email = str(conta.get("email") or (_carga(jwt) or {}).get("email") or "").strip().lower()
    return {"email": email, "nome": str(conta.get("nome") or email)} if email else {}


def _rpc_de_quem_olha(jwt: str, email: str):
    """O RPC do Fracttal com o login de quem está olhando: o mesmo `_rpc_call` do OS Creator, dentro da sessão dele
    (a costura `os_web.sessao` põe o JWT da pessoa no lugar do da máquina)."""
    import importlib
    api = importlib.import_module("api")
    sessao = importlib.import_module("os_web.sessao")

    def rpc(metodo, params):
        fichas = sessao.abrir(jwt, email)
        try:
            return api._rpc_call(metodo, params)
        finally:
            sessao.fechar(fichas)
    return rpc


def _tela(numero, codigo=None) -> str:
    """A tela da PT; com `codigo` (o código do ativo da linha decidida), a mesma linha (a PT de mais de um ativo tem
    uma decisão por linha, decisão 4 de 11/10/2026)."""
    url = na_raiz(f"/t/campo/pt/{quote(str(numero), safe='')}")
    return url if codigo is None else url + "?ativo=" + quote(str(codigo), safe="")


def _card(numero, codigo=None) -> str:
    """O card de assinar a PT (30/10/2026, o link do e-mail do App), na mesma linha (`codigo`, como em `_tela`)."""
    url = na_raiz(f"/t/campo/pt/{quote(str(numero), safe='')}/assinar")
    return url if codigo is None else url + "?ativo=" + quote(str(codigo), safe="")


def _login(numero, codigo=None, card=False) -> str:
    """O login do Fracttal do OS Creator, voltando à MESMA linha da PT (`codigo`: o código do ativo dela; "" = a linha
    sem ativo; None = quem pediu não disse a linha). Revisão adversarial de 11/10/2026: com só o número no `next`, a
    volta abria a 1ª linha com o código DELA no formulário, e o clique seguinte decidia o outro equipamento da PT. Com
    `card`, a volta cai no card de assinar (30/10/2026: quem veio pelo e-mail, no celular, não sai do card)."""
    # o OS Creator só devolve para /os/...: a volta passa por /os/_nexus/pt/<n>/voltar, com a linha na consulta (o
    # `_destino_local` do clone aceita /os... com consulta). O `next` vai SEM o prefixo (é o caminho que o clone
    # entende); o endereço do login, com ele (é o navegador que o pede)
    volta = f"/os/_nexus/pt/{quote(str(numero), safe='')}/voltar"
    if codigo is not None:
        volta += "?ativo=" + quote(str(codigo), safe="")
    if card:
        volta += ("&" if "?" in volta else "?") + "card=1"
    return na_raiz("/os/login") + "?next=" + quote(volta, safe="")


@bp_assinatura.route("/os/_nexus/quem")
def quem():
    q = quem_assina()
    return jsonify({"email": q.get("email", ""), "nome": q.get("nome", "")})


@bp_assinatura.route("/os/_nexus/pt/<numero>/assinatura-tecnico")
def assinatura_tecnico(numero):
    """A assinatura que o técnico desenhou na APR, para a tela da PT pôr ao lado de "A PT" (Levi, 05/10). JSON:
    {"ok", "img"} ou {"ok": false, "login" | "motivo"}. Primeiro a da APR feita no App, do PDF que ele anexa na OS
    (26/10/2026, Levi: "Gostaria para as APRs que foram feitas via app de campo mostrem sim a assinatura"), que não
    pede login; sem esse PDF, a do formulário do Fracttal, com o login do Fracttal de quem olha. O `?ativo=` (a linha
    de onde se pede) vai no "entre com o seu login do Fracttal", para a volta cair na mesma linha."""
    p = visao.pt(numero)
    if p and p.get("os"):
        try:
            return jsonify({"ok": True, "img": pt_fracttal.assinatura_da_apr_do_app(p["numero"], p["os"], p.get("criada")),
                            "origem": "app"})
        except pt_fracttal.SemArquivo:
            pass                # a APR de antes do App (ou o PDF que ainda não chegou): o caminho do formulário
        except Exception:       # noqa: BLE001 — Fracttal fora: tenta o formulário, que diz o motivo
            pass
    jwt, conta = _sessao_os()
    if not jwt:
        return jsonify({"ok": False, "login": True, "entrar": _login(numero, request.args.get("ativo"))})
    if not p or not p.get("os"):
        return jsonify({"ok": False, "motivo": "a PT não está no livro do App"})
    try:
        ids = pt_fracttal.tarefas_candidatas(p["os"], p.get("tarefa"), p.get("codigo") or "")
        if not ids:
            return jsonify({"ok": False, "motivo": "não achei a tarefa desta PT na OS do Fracttal"})
        email = str(conta.get("email") or (_carga(jwt) or {}).get("email") or "")
        img = pt_fracttal.assinatura_das_candidatas(p["numero"], ids, _rpc_de_quem_olha(jwt, email))
    except pt_fracttal.SemArquivo as e:
        return jsonify({"ok": False, "motivo": str(e)})
    except Exception as e:      # noqa: BLE001 — Fracttal recusou ou o login caiu: a tela diz, a PT abre igual
        if type(e).__name__ == "SessionExpired":
            from ...auth import encerrar, via_fracttal
            if via_fracttal():  # o Fracttal derrubou o token de quem entrou por ele: o Nexus sai junto (09/10/2026)
                return encerrar("caiu", json=True)
        return jsonify({"ok": False, "motivo": f"o Fracttal não respondeu ({type(e).__name__})"})
    return jsonify({"ok": True, "img": img})


@bp_assinatura.route("/os/_nexus/voltar")
def voltar_para():
    """Depois do login do Fracttal (o OS Creator só devolve para /os/...), de volta à tela do Nexus de onde se veio.
    Só endereço da torre Campo: nada de mandar para fora."""
    # o `para` é o location.pathname da tela, que debaixo do prefixo vem com ele (/nexus/t/campo/...)
    para = sem_raiz(request.args.get("para") or "")
    return redirect(na_raiz(para if para.startswith("/t/campo/") and not para.startswith("//") else "/t/campo/aprovacao"))


@bp_assinatura.route("/os/_nexus/pt/<numero>/voltar")
def voltar(numero):
    # a linha que foi ao login (o `?ativo=` do `_login`); sem ela, a tela da PT de mais de uma linha só deixa escolher.
    # Do card de assinar (`card=1`), de volta ao card
    destino = _card if request.args.get("card") == "1" else _tela
    return redirect(destino(numero, request.args.get("ativo")))


def _volta(numero, codigo=None) -> str:
    """De volta à tela de onde se decidiu (a lista de APR e PT do HSEQ, com os filtros dela) ou à da PT. Só endereço do
    próprio Nexus: nada de mandar para fora."""
    # O `volta` do formulário é o request.full_path da tela, SEM o prefixo (e a camada da T.I. pode tê-lo posto):
    # confere sem ele e devolve com ele. Cru, debaixo do /nexus a decisão gravada mandava a pessoa à plataforma de
    # Performance (porta única, 10/10/2026: "o Nexus como link principal")
    para = sem_raiz(request.form.get("volta") or "")
    return (na_raiz(para) if para.startswith(("/t/hseq/", "/t/campo/")) and not para.startswith("//")
            else _tela(numero, codigo))


@bp_assinatura.route("/os/_nexus/pt/<numero>/decidir", methods=["POST"])
def decidir(numero):
    # pedido de outro site não decide PT (o cookie Lax já barra; a origem confere de novo, porque é segurança do campo)
    origem = request.headers.get("Origin")
    if origem and urlsplit(origem).netloc != request.host:
        return "Origem recusada.", 403
    # a linha da PT que se decide: o código do ativo dela (o formulário de cada linha manda; "" = a linha sem ativo).
    # Sem o campo (formulário de antes de 11/10/2026), só a PT de uma linha se decide (`decisao_pt._linha`)
    codigo = request.form.get("codigo")
    q = quem_assina()
    if not q:
        # sem o login do Fracttal: vai ao login e volta para a MESMA linha (revisão adversarial de 11/10/2026); o
        # formulário do card de assinar volta ao card (`card=1`)
        return redirect(_login(numero, codigo, card=request.form.get("card") == "1"))
    volta, tela = _volta(numero, codigo), _tela(numero, codigo)
    try:
        decisao_pt.decidir(numero, request.form.get("decisao", ""), request.form.get("motivo", ""), q["email"],
                           q.get("nome", ""), bool(session.get("admin")), codigo=codigo)
    except decisao_pt.Recusada as e:
        session["pt_aviso"] = f"{numero}: {e}" if volta != tela else str(e)
        return redirect(volta)
    except Exception as e:      # noqa: BLE001 — banco fora do ar: a tela diz, nada é dado como gravado
        session["pt_aviso"] = f"Não consegui gravar a decisão no banco ({type(e).__name__}). Nada foi salvo."
        return redirect(volta)
    if volta != tela:
        session["pt_gravada"] = numero
        return redirect(volta)
    return redirect(tela + ("&" if "?" in tela else "?") + "gravada=1")
