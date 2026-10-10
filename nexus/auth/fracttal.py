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
    não conta esta (auditoria A2 da porta única, 10/10/2026).

    Leva o porquê (revisão adversarial de 10/10/2026): até então todo "Erro de conexão no login" virava só "Fracttal
    ocupado, tente em instantes", e o erro de verdade (DNS que não resolve, certificado recusado, proxy ou firewall
    barrando a saída do servidor) era descartado, sem log. Se na segunda a saída do servidor para o Fracttal quebrasse,
    todos veriam "tente em instantes" para sempre, e o journal ficaria vazio.
    - `motivo`: curto, para a tela ("o servidor não achou o endereço do Fracttal (DNS)");
    - `limite`: é o limite de pedidos do Fracttal (passa sozinho), e não a rede ou o Fracttal fora;
    - `detalhe`: a classe e a mensagem originais, sem e-mail nem senha, para o journal."""

    def __init__(self, mensagem: str, motivo: str = "sem resposta do Fracttal", limite: bool = False,
                 detalhe: str = ""):
        super().__init__(mensagem)
        self.motivo, self.limite, self.detalhe = motivo, limite, detalhe or mensagem


class SessaoNaoVeio(LoginRecusado):
    """O Fracttal aceitou a senha e o JWT não chegou à sessão do clone (a costura do `os_web/sessao.py` com o
    `api._save_jwt`). Era um FracttalOcupado até 10/10/2026: um sync do clone que mexesse no `_save_jwt` deixaria todos
    vendo "ocupado, tente em instantes", sem rastro. Não conta no limite (não é senha errada), mas é defeito do Nexus: a
    tela diz o que houve e o journal registra (`detalhe`, de onde veio o `_save_jwt` em uso)."""

    def __init__(self, mensagem: str, detalhe: str = ""):
        super().__init__(mensagem)
        self.detalhe = detalhe or mensagem


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


_LIMITE = re.compile(r"\bhttp (?:406|429)\b|too.?many|rate.?limit|limit.?exceeded", re.I)
_FORA = re.compile(r"\bhttp 5\d\d\b|bad gateway|service unavailable|gateway time", re.I)
_DNS = re.compile(r"resolve|getaddrinfo|name or service not known|nodename nor servname|name resolution", re.I)


def motivo_curto(mensagem: str, original: BaseException | None = None) -> tuple[str, bool]:
    """(o motivo para a tela, é o limite do Fracttal?) da recusa que não conferiu a senha. O `original` é o erro do
    `requests` que o clone embrulhou (o `__context__` do FracttalError), quando houve. A ordem importa: o SSLError e o
    ProxyError do requests também são ConnectionError, e a mensagem do DNS vem dentro de um ConnectionError."""
    import requests
    texto = f"{mensagem} {original or ''}"
    if isinstance(original, requests.exceptions.SSLError) or re.search(r"\bssl|certificate", texto, re.I):
        return "o servidor recusou o certificado do Fracttal (SSL)", False
    if isinstance(original, requests.exceptions.ProxyError) or re.search(r"proxy", texto, re.I):
        return "o proxy da rede barrou a saída para o Fracttal", False
    if isinstance(original, requests.exceptions.Timeout) or re.search(r"timed? ?out", texto, re.I):
        return "o Fracttal não respondeu a tempo", False
    if _DNS.search(texto):
        return "o servidor não achou o endereço do Fracttal (DNS)", False
    if isinstance(original, requests.exceptions.ConnectionError) or re.search(r"erro de conex", texto, re.I):
        return "sem conexão do servidor com o Fracttal", False
    if _LIMITE.search(texto):
        return "limite de pedidos da empresa", True
    if _FORA.search(texto):
        return "o Fracttal está fora do ar ou instável", False
    return "sem resposta do Fracttal", False


def _sem_email(texto: str, email: str) -> str:
    """O texto para o journal, sem o e-mail (a mensagem do Fracttal pode repetir o que foi mandado) e curto. A senha não
    precisa de troca: ela sai do Nexus já transformada (`_encrypt_password` do clone) e vai no corpo do POST, que nem o
    `requests` nem o Fracttal repetem na mensagem. Trocá-la aqui seria pior: "<senha>nection" diria qual era."""
    texto = str(texto or "")
    email = str(email or "").strip()
    if email:
        texto = re.sub(re.escape(email), "<e-mail>", texto, flags=re.I)
    return texto[:500]


def entrar(app, email: str, senha: str) -> dict:
    """{"email", "nome", "perfil", "exp", "cookie": (nome, valor, max_age)} da pessoa. LoginRecusado com o motivo;
    FracttalOcupado (que também é um LoginRecusado) quando a senha não chegou a ser conferida; SessaoNaoVeio quando ela
    passou e a sessão do clone não veio."""
    from ..torres.oscreator import ponte
    clone = ponte.clone(app)                     # põe o clone no sys.path e costura a sessão dele no `api`
    import api as os_api                         # noqa: E402 — o `api` do clone do OS Creator
    from os_web import sessao as os_sessao       # noqa: E402
    with clone.test_request_context("/os/login", method="POST"):
        with os_sessao.contexto(""):
            try:
                os_api.fracttal_login(email, senha)
            except os_api.FracttalError as e:
                if not nao_conferiu(str(e)):
                    raise LoginRecusado(str(e)) from None
                # o clone embrulha o erro do requests (DNS, SSL, proxy, tempo) numa frase; o original fica no contexto
                original = e.__context__ if isinstance(e.__context__, Exception) else None
                motivo, limite = motivo_curto(str(e), original)
                bruto = f"{type(original).__name__}: {original}" if original else f"{type(e).__name__}: {e}"
                raise FracttalOcupado(str(e), motivo=motivo, limite=limite,
                                      detalhe=_sem_email(bruto, email)) from None
            jwt = os_sessao.jwt_atual()
            if not jwt:
                # a senha passou e a sessão não veio: não é erro de quem digitou (não conta no limite), é da costura
                gravador = getattr(os_api, "_save_jwt", None)
                origem = f"{getattr(gravador, '__module__', '?')}.{getattr(gravador, '__qualname__', '?')}"
                raise SessaoNaoVeio("O Fracttal aceitou a senha, mas a sessão não chegou ao Nexus.",
                                    detalhe=f"jwt_atual() vazio depois do fracttal_login; o api._save_jwt em uso é "
                                            f"{origem} (o esperado é o da os_web.sessao, a costura do clone)")
            try:
                conta = os_api.get_conta_info() or {}
            except Exception:                    # noqa: BLE001 — o perfil é enfeite; o login vale sem ele
                conta = {}
    conta = {"nome": str(conta.get("nome") or email).strip(), "email": str(conta.get("email") or email).strip().lower(),
             "perfil": str(conta.get("perfil") or "").strip()}
    valor = clone.session_interface.get_signing_serializer(clone).dumps({"jwt": jwt, "conta": conta, "_permanent": True})
    return dict(conta, exp=exp_do_jwt(jwt), cookie=(clone.config["SESSION_COOKIE_NAME"], valor,
                               int(clone.permanent_session_lifetime.total_seconds())))
