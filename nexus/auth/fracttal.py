"""Entrar no Nexus com o login do Fracttal (Levi, 06/10/2026: "Ao invés de uma senha difícil, no início faça a pessoa
logar com fractall").

É o mesmo login do OS Creator Web: e-mail e senha do Fracttal, pelo `api.fracttal_login` do clone (a senha vai
transformada como o web app do Fracttal faz e nunca é guardada; só a conta da Grid Co. entra, pelo id da empresa fixo
no clone). Um login só abre as duas sessões: a do Nexus (quem é a pessoa) e a do OS Creator (o JWT do Fracttal, no
cookie `os_sessao` de /os). Assim o /os/ e a aprovação de PT já abrem sem pedir o login de novo.

E as duas acabam juntas (Levi, 09/10/2026: "quando deslogar do Fracttal deslogue do Nexus, tem que pedir para logar de
novo"): o `exp` do JWT vai para a sessão do Nexus (`fracttal_exp`), e o portão (`auth/__init__.py`) encerra o Nexus quando
o token vence, quando o Fracttal o recusa ou quando a pessoa sai pelo OS Creator.
"""
import base64
import json
import re


def exp_do_jwt(jwt: str) -> float:
    """O `exp` (epoch) do JWT do Fracttal, lido do próprio token, sem pedido ao Fracttal. 0 quando não dá para ler."""
    try:
        p = str(jwt or "").split(".")[1]
        p += "=" * (-len(p) % 4)
        return float(json.loads(base64.urlsafe_b64decode(p.encode())).get("exp") or 0)
    except Exception:                            # noqa: BLE001 — token opaco: sem prazo conhecido
        return 0.0


class LoginRecusado(Exception):
    """O Fracttal não aceitou: a mensagem é a dele (senha errada, conta bloqueada por tentativas...)."""


class FracttalOcupado(LoginRecusado):
    """O login nem foi conferido: o Fracttal respondeu com o limite (429/406, os 200 pedidos por minuto da EMPRESA,
    divididos com o App de Campo), caiu (5xx) ou a rede não chegou. Não é senha errada: o limite de tentativas do Entrar
    não conta esta (auditoria A2 da porta única, 10/10/2026) e a pessoa vê "Fracttal ocupado, tente em instantes"."""


# O que o `api.fracttal_login` do clone monta quando a senha NÃO foi conferida. Ele não devolve o status HTTP, só a
# mensagem: "Erro de conexão no login: <erro do requests>" (rede, tempo esgotado) ou "Login falhou: <message do Fracttal,
# ou HTTP nnn quando ela não vem>". Um 5xx que traga uma mensagem própria fora desta lista conta como recusa (do lado
# seguro: só se deixa de contar o que se sabe que não conferiu a senha). O clone fica idêntico ao do oem
# (`nexus/torres/oscreator/README.md`), por isso a leitura é aqui, e não lá.
_NAO_CONFERIU = re.compile(r"erro de conex|\bhttp (?:406|408|425|429|5\d\d)\b|too.?many|rate.?limit|limit.?exceeded"
                           r"|bad gateway|service unavailable|gateway time|timed? ?out", re.I)


def nao_conferiu(mensagem: str) -> bool:
    """A recusa do clone é de Fracttal ocupado ou fora (e não de senha errada)?"""
    return bool(_NAO_CONFERIU.search(str(mensagem or "")))


def entrar(app, email: str, senha: str) -> dict:
    """{"email", "nome", "perfil", "exp", "cookie": (nome, valor, max_age)} da pessoa. LoginRecusado com o motivo;
    FracttalOcupado (que também é um LoginRecusado) quando a senha não chegou a ser conferida."""
    from ..torres.oscreator import ponte
    clone = ponte.clone(app)                     # põe o clone no sys.path e costura a sessão dele no `api`
    import api as os_api                         # noqa: E402 — o `api` do clone do OS Creator
    from os_web import sessao as os_sessao       # noqa: E402
    with clone.test_request_context("/os/login", method="POST"):
        with os_sessao.contexto(""):
            try:
                os_api.fracttal_login(email, senha)
            except os_api.FracttalError as e:
                raise (FracttalOcupado if nao_conferiu(str(e)) else LoginRecusado)(str(e)) from None
            jwt = os_sessao.jwt_atual()
            if not jwt:
                # a senha passou e a sessão não veio: não é erro de quem digitou, não conta no limite
                raise FracttalOcupado("O Fracttal não devolveu a sessão. Tente de novo.")
            try:
                conta = os_api.get_conta_info() or {}
            except Exception:                    # noqa: BLE001 — o perfil é enfeite; o login vale sem ele
                conta = {}
    conta = {"nome": str(conta.get("nome") or email).strip(), "email": str(conta.get("email") or email).strip().lower(),
             "perfil": str(conta.get("perfil") or "").strip()}
    valor = clone.session_interface.get_signing_serializer(clone).dumps({"jwt": jwt, "conta": conta, "_permanent": True})
    return dict(conta, exp=exp_do_jwt(jwt), cookie=(clone.config["SESSION_COOKIE_NAME"], valor,
                               int(clone.permanent_session_lifetime.total_seconds())))
