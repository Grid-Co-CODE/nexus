"""Entrar no Nexus com o login do Fracttal (Levi, 06/10/2026: "Ao invés de uma senha difícil, no início faça a pessoa
logar com fractall").

É o mesmo login do OS Creator Web: e-mail e senha do Fracttal, pelo `api.fracttal_login` do clone (a senha vai
transformada como o web app do Fracttal faz e nunca é guardada; só a conta da Grid Co. entra, pelo id da empresa fixo
no clone). Um login só abre as duas sessões: a do Nexus (quem é a pessoa) e a do OS Creator (o JWT do Fracttal, no
cookie `os_sessao` de /os). Assim o /os/ e a aprovação de PT já abrem sem pedir o login de novo.
"""


class LoginRecusado(Exception):
    """O Fracttal não aceitou: a mensagem é a dele (senha errada, conta bloqueada por tentativas...)."""


def entrar(app, email: str, senha: str) -> dict:
    """{"email", "nome", "perfil", "cookie": (nome, valor, max_age)} da pessoa. LoginRecusado com o motivo."""
    from ..torres.oscreator import ponte
    clone = ponte.clone(app)                     # põe o clone no sys.path e costura a sessão dele no `api`
    import api as os_api                         # noqa: E402 — o `api` do clone do OS Creator
    from os_web import sessao as os_sessao       # noqa: E402
    with clone.test_request_context("/os/login", method="POST"):
        with os_sessao.contexto(""):
            try:
                os_api.fracttal_login(email, senha)
            except os_api.FracttalError as e:
                raise LoginRecusado(str(e)) from None
            jwt = os_sessao.jwt_atual()
            if not jwt:
                raise LoginRecusado("O Fracttal não devolveu a sessão. Tente de novo.")
            try:
                conta = os_api.get_conta_info() or {}
            except Exception:                    # noqa: BLE001 — o perfil é enfeite; o login vale sem ele
                conta = {}
    conta = {"nome": str(conta.get("nome") or email).strip(), "email": str(conta.get("email") or email).strip().lower(),
             "perfil": str(conta.get("perfil") or "").strip()}
    valor = clone.session_interface.get_signing_serializer(clone).dumps({"jwt": jwt, "conta": conta, "_permanent": True})
    return dict(conta, cookie=(clone.config["SESSION_COOKIE_NAME"], valor,
                               int(clone.permanent_session_lifetime.total_seconds())))
