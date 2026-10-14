"""Entrar com a conta Microsoft da Grid Co. (Entra ID), 14/10/2026.

Levi, 13/10/2026: "Conseguimos fazer o login do Nexus ser via microsoft só aceitando quem é da grid?". Até aqui a porta
era o login do Fracttal (06/10), que deixa entrar quem tiver conta no Fracttal da empresa, de dentro ou de fora da Grid.

**Desligado** sem as quatro variáveis (`VARIAVEIS`): a porta segue a do Fracttal, como antes. Ligado, a porta é a
Microsoft e o Fracttal SAI da porta (o POST com e-mail e senha do Fracttal é recusado no servidor, não só escondido na
tela). O Fracttal continua sendo o login do OS Creator: a OS nasce no nome de quem a cria, e o Fracttal só aceita a
sessão emitida por ele mesmo (o id_token da Microsoft não vale lá; é a decisão de 09/2026 para a plataforma, "faz
parte!"). Quem entra pela Microsoft abre o OS Creator e ele pede o Fracttal na primeira vez, como já acontecia com a
senha de administrador. A senha de administrador fica como reserva (Microsoft fora, registro com defeito).

**Fluxo:** OpenID Connect, código de autorização com PKCE (S256), sem biblioteca nova (só o `requests`; o servidor
atualiza por push, e dependência nova pede o `pip install` da T.I.). A volta é o próprio `/entrar` (`?code=&state=`):
no servidor, o Caddy só manda ao Nexus a raiz exata e alguns caminhos (`/entrar` exato, `/t/*`, `/os/*`...), e um
`/entrar/microsoft` cairia na plataforma (o "Not Found" da aba Atualizações, 13/10). O `response_mode=query` é de
propósito: com `form_post` a volta seria um POST de outro site, e o cookie da sessão (SameSite=Lax) não iria junto.

**Quem é da Grid** (o Entra já recusa conta de outro diretório, porque o registro é só do diretório da Grid; o Nexus
confere de novo, para não depender de como a T.I. configurou o registro):
1. o diretório (`tid` e `iss`) é o da `NEXUS_MS_TENANT_ID`;
2. não é convidado: conta de fora convidada para o diretório da Grid (B2B) chega com o `idp` da casa dela, ou com
   `#EXT#` no nome de usuário;
3. o e-mail é de um domínio da Grid (`NEXUS_MS_DOMINIOS`, padrão gridco.com.br), comparado inteiro (gridco.com.br.x.com
   e xgridco.com.br não passam).

**Por que o id_token não tem a assinatura conferida:** ele chega direto do endpoint de token da Microsoft, numa conexão
TLS com o certificado conferido, em troca do código + a chave do Nexus + o verificador PKCE. É o caso que a
especificação permite (OpenID Connect Core 1.0, 3.1.3.7, item 6: "the TLS server validation MAY be used to validate
the issuer in place of checking the token signature"). O mesmo desenho do login Microsoft da plataforma (07/2026).
Nada aqui aceita id_token vindo do navegador.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from urllib.parse import urlencode

import requests

VARIAVEIS = ("NEXUS_MS_CLIENT_ID", "NEXUS_MS_TENANT_ID", "NEXUS_MS_CLIENT_SECRET", "NEXUS_MS_VOLTA")
AUTORIDADE = "https://login.microsoftonline.com"
ESCOPO = "openid profile email"
DOMINIOS_PADRAO = ("gridco.com.br",)
PEDIDO_S = 10 * 60               # da ida à volta: a pessoa digita a senha e o código do celular, sem pressa
FOLGA_S = 5 * 60                 # diferença de relógio aceita no prazo do id_token
MAX_PEDIDOS = 3                  # idas guardadas por navegador: duas abas, ou o duplo clique, não se atropelam
_GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_EMAIL = re.compile(r"^[a-z0-9._%+'-]+@([a-z0-9-]+(?:\.[a-z0-9-]+)+)$")
_AADSTS = re.compile(r"AADSTS\d+")
_ERRO_OAUTH = re.compile(r"[a-z_]{1,40}")          # inteiro (fullmatch): o $ do match aceitaria quebra de linha no fim

TEXTO_DE_FORA = "Esta conta não é da Grid Co. O Nexus só aceita a conta Microsoft da Grid Co. ({dominios})."
TEXTO_CONVIDADO = ("Conta de convidado no diretório da Grid Co. não entra no Nexus. Entre com a sua conta da Grid Co. "
                   "({dominios}).")
TEXTO_NAO_CONFERE = "A Microsoft devolveu um login que não confere. Tente de novo; se continuar, avise a T.I."
TEXTO_SEM_PEDIDO = ("O login da Microsoft não começou neste navegador, ou já foi usado. Clique em Entrar com a "
                    "Microsoft de novo.")
TEXTO_PEDIDO_VENCIDO = "O login da Microsoft levou mais de 10 minutos. Clique em Entrar com a Microsoft de novo."
TEXTO_CHAVE = ("A chave do Nexus na Microsoft venceu ou está errada (NEXUS_MS_CLIENT_SECRET, no registro do Nexus no "
               "Entra ID). Avise a T.I.; até lá, só a senha de administrador entra.")
TEXTO_SEM_RESPOSTA = "Sem resposta da Microsoft agora. Tente em instantes; se continuar, avise a T.I."


class Recusado(Exception):
    """A Microsoft ou o Nexus recusaram a entrada. O texto é o da tela; o `detalhe` vai ao journal e nunca leva e-mail,
    nome nem segredo (o código AADSTS e o domínio, sim)."""

    def __init__(self, texto: str, detalhe: str = "", contar: bool = False):
        super().__init__(texto)
        self.detalhe = detalhe or texto
        # conta para o teto por rede do Entrar (auth): só a recusa que custou uma ida ao endpoint de token por causa de
        # quem tentou (código de lixo, conta de fora). Chave vencida e Microsoft fora não contam: com elas TODO mundo
        # falharia, e a rede do escritório trancaria por 15 minutos depois que a T.I. consertasse
        self.contar = contar


class SemResposta(Recusado):
    """A Microsoft não respondeu (rede, DNS, 5xx): não é recusa de quem tentou."""


def _limpo(cfg, nome: str) -> str:
    return str(cfg.get(nome) or "").strip()


def ligado(cfg) -> bool:
    """As quatro variáveis no .env e o diretório como o ID (GUID) que o Entra põe no `tid`. Diretório escrito como
    domínio (gridco.com.br) nunca casaria com o `tid`: fica desligado, e a porta segue a do Fracttal, em vez de abrir
    um botão que recusaria todo mundo."""
    return all(_limpo(cfg, v) for v in VARIAVEIS) and bool(_GUID.match(_limpo(cfg, "NEXUS_MS_TENANT_ID").lower()))


def _diretorio(cfg) -> str:
    return _limpo(cfg, "NEXUS_MS_TENANT_ID").lower()


def dominios(cfg) -> tuple[str, ...]:
    """Os domínios de e-mail da Grid que entram (NEXUS_MS_DOMINIOS, separados por vírgula; padrão gridco.com.br)."""
    lista = tuple(d.strip().lower().lstrip("@") for d in _limpo(cfg, "NEXUS_MS_DOMINIOS").split(",") if d.strip())
    return lista or DOMINIOS_PADRAO


def _b64url(dado: bytes) -> str:
    return base64.urlsafe_b64encode(dado).decode().rstrip("=")


def novo_pedido(destino: str) -> dict:
    """Uma ida à Microsoft: o `state` (a volta é deste navegador), o `nonce` (o id_token é desta ida), o verificador
    do PKCE (o código só vale com ele) e o `next`. Fica na sessão do Nexus (cookie assinado, HttpOnly) até a volta."""
    return {"state": secrets.token_urlsafe(24), "nonce": secrets.token_urlsafe(24),
            "verificador": secrets.token_urlsafe(64), "next": destino, "t": time.time()}


def guardar(pedidos: dict | None, pedido: dict) -> dict:
    """Os pedidos do navegador com este na frente, até `MAX_PEDIDOS` (o mais antigo sai)."""
    atuais = sorted((pedidos or {}).items(), key=lambda kv: float((kv[1] or {}).get("t") or 0), reverse=True)
    return dict([(pedido["state"], pedido)] + atuais[:MAX_PEDIDOS - 1])


def endereco_de_entrada(cfg, pedido: dict) -> str:
    """O endereço da Microsoft para esta ida. `prompt=login`: toda entrada pede a senha da Microsoft, como o Fracttal já
    pedia. Com o `select_account` (a primeira versão), no PC da sala do NOC a conta de quem usou o navegador antes
    aparecia na lista e abria o Nexus para outro com um clique, mesmo depois do Sair (revisão adversarial de 14/10/2026:
    A, administrador, sai; B escolhe a conta de A e entra como A). O Sair do Nexus não sai da Microsoft do navegador
    (sairia também do Outlook e do Teams da pessoa), e com a senha pedida não precisa."""
    q = {"client_id": _limpo(cfg, "NEXUS_MS_CLIENT_ID"), "response_type": "code",
         "redirect_uri": _limpo(cfg, "NEXUS_MS_VOLTA"), "response_mode": "query", "scope": ESCOPO,
         "state": pedido["state"], "nonce": pedido["nonce"],
         "code_challenge": _b64url(hashlib.sha256(pedido["verificador"].encode()).digest()),
         "code_challenge_method": "S256", "prompt": "login", "domain_hint": dominios(cfg)[0]}
    return f"{AUTORIDADE}/{_diretorio(cfg)}/oauth2/v2.0/authorize?{urlencode(q)}"


def _texto_do_erro(cfg, erro: str, aadsts: str = "") -> str:
    if erro == "invalid_client" or aadsts in ("AADSTS7000215", "AADSTS7000222"):
        return TEXTO_CHAVE
    if erro == "access_denied" and aadsts in ("", "AADSTS65004"):
        return "O login foi cancelado na Microsoft."
    if aadsts == "AADSTS50105":
        return "A sua conta não está liberada para o Nexus no Entra ID da Grid Co. Peça à T.I. para liberar."
    if erro in ("consent_required", "interaction_required") or aadsts in ("AADSTS65001", "AADSTS90094"):
        return ("A Microsoft pediu uma autorização que só a T.I. dá (o consentimento do Nexus no Entra ID). Avise a "
                "T.I.")
    if aadsts == "AADSTS50020":
        return TEXTO_DE_FORA.format(dominios=", ".join("@" + d for d in dominios(cfg)))
    return f"A Microsoft recusou o login ({aadsts or erro}). Tente de novo; se continuar, avise a T.I."


def concluir(cfg, args, pedido: dict | None) -> dict:
    """A volta da Microsoft (`/entrar?code=&state=` ou `?error=&state=`) com o pedido que o `state` dela achou na sessão
    (quem chama já o tirou de lá: cada ida vale uma volta só). Devolve a conta {"email", "nome"}; recusa (`Recusado`,
    `SemResposta`) a volta que este navegador não pediu, a que passou do prazo, a que trouxe erro e a conta que não é
    da Grid."""
    if not isinstance(pedido, dict):
        raise Recusado(TEXTO_SEM_PEDIDO, "volta sem pedido neste navegador (state desconhecido ou já usado)")
    if time.time() - float(pedido.get("t") or 0) > PEDIDO_S:
        raise Recusado(TEXTO_PEDIDO_VENCIDO, "pedido com mais de 10 minutos")
    erro = str(args.get("error") or "")
    if erro:
        # o `error` e o `error_description` chegam pelo endereço: quem tem uma ida (qualquer um, pelo /entrar?ms=1)
        # escreve o que quiser ali. Ao journal vão só o código no formato da especificação e o AADSTS (revisão de
        # 14/10/2026: uma quebra de linha no `error` forjava linhas no journal), e a volta com erro conta no teto
        erro = erro if _ERRO_OAUTH.fullmatch(erro) else "desconhecido"
        aadsts = _AADSTS.search(str(args.get("error_description") or ""))
        aadsts = aadsts.group(0) if aadsts else ""
        raise Recusado(_texto_do_erro(cfg, erro, aadsts), f"a Microsoft devolveu {erro} {aadsts}".strip(), contar=True)
    codigo = str(args.get("code") or "")
    if not codigo:
        raise Recusado(TEXTO_NAO_CONFERE, "volta sem code")
    return conferir(cfg, _trocar(cfg, codigo, pedido["verificador"]), pedido["nonce"])


def _pedir_token(url: str, dados: dict):
    """O POST ao endpoint de token (separado para os testes trocarem; o `requests` confere o certificado)."""
    return requests.post(url, data=dados, timeout=15)


def _trocar(cfg, codigo: str, verificador: str) -> dict:
    """Troca o código pelo id_token, servidor a servidor, e devolve o conteúdo dele (as claims)."""
    url = f"{AUTORIDADE}/{_diretorio(cfg)}/oauth2/v2.0/token"
    dados = {"client_id": _limpo(cfg, "NEXUS_MS_CLIENT_ID"), "client_secret": _limpo(cfg, "NEXUS_MS_CLIENT_SECRET"),
             "grant_type": "authorization_code", "code": codigo, "redirect_uri": _limpo(cfg, "NEXUS_MS_VOLTA"),
             "code_verifier": verificador, "scope": ESCOPO}
    try:
        r = _pedir_token(url, dados)
    except requests.RequestException as e:
        raise SemResposta(TEXTO_SEM_RESPOSTA, f"token: {type(e).__name__}") from None
    try:
        corpo = r.json()
    except ValueError:
        corpo = {}
    corpo = corpo if isinstance(corpo, dict) else {}
    if r.status_code >= 500:
        raise SemResposta(TEXTO_SEM_RESPOSTA, f"token: HTTP {r.status_code}")
    if r.status_code != 200 or not corpo.get("id_token"):
        erro = str(corpo.get("error") or f"HTTP {r.status_code}")
        aadsts = _AADSTS.search(str(corpo.get("error_description") or ""))
        aadsts = aadsts.group(0) if aadsts else ""
        raise Recusado(_texto_do_erro(cfg, erro, aadsts), f"token recusado: {erro} {aadsts}".strip(),
                       contar=erro != "invalid_client" and aadsts not in ("AADSTS7000215", "AADSTS7000222"))
    return _claims(str(corpo["id_token"]))


def _claims(id_token: str) -> dict:
    try:
        parte = id_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(parte + "=" * (-len(parte) % 4)))
    except Exception:            # noqa: BLE001 — qualquer coisa fora do formato: não entra
        raise Recusado(TEXTO_NAO_CONFERE, "id_token ilegível", contar=True) from None
    if not isinstance(claims, dict):
        raise Recusado(TEXTO_NAO_CONFERE, "id_token sem claims", contar=True)
    return claims


def _numero(valor) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def conferir(cfg, c: dict, nonce: str) -> dict:
    """Confere o id_token desta ida e diz quem é: {"email", "nome"}. Ver as três conferências no topo do módulo."""
    diretorio, cliente = _diretorio(cfg), _limpo(cfg, "NEXUS_MS_CLIENT_ID")
    emissor = f"{AUTORIDADE}/{diretorio}/v2.0"
    doms = dominios(cfg)
    de_fora = TEXTO_DE_FORA.format(dominios=", ".join("@" + d for d in doms))
    if str(c.get("tid") or "").lower() != diretorio or str(c.get("iss") or "").lower() != emissor:
        raise Recusado(de_fora, "diretório de fora (tid/iss)", contar=True)
    aud = c.get("aud")
    aud = [str(a).lower() for a in aud] if isinstance(aud, list) else [str(aud or "").lower()]
    if aud != [cliente.lower()]:          # o GUID colado em maiúscula no .env não recusa todo mundo
        raise Recusado(TEXTO_NAO_CONFERE, "aud de outro aplicativo", contar=True)
    if not nonce or not hmac.compare_digest(str(c.get("nonce") or ""), nonce):
        raise Recusado(TEXTO_NAO_CONFERE, "nonce diferente do da ida", contar=True)
    agora, exp, iat = time.time(), _numero(c.get("exp")), _numero(c.get("iat"))
    if not exp or agora > exp + FOLGA_S or iat > agora + FOLGA_S:
        raise Recusado(TEXTO_NAO_CONFERE, "id_token fora do prazo", contar=True)
    idp = str(c.get("idp") or "").lower().rstrip("/")
    convidado = TEXTO_CONVIDADO.format(dominios=", ".join("@" + d for d in doms))
    if idp and idp not in (emissor, f"https://sts.windows.net/{diretorio}"):
        raise Recusado(convidado, "convidado (idp de outra casa)", contar=True)
    if "#ext#" in str(c.get("preferred_username") or "").lower() or "#ext#" in str(c.get("upn") or "").lower():
        raise Recusado(convidado, "convidado (#EXT#)", contar=True)
    # `acct` (declaração opcional do ID token, DEPLOY.md 7g): 0 = membro, 1 = convidado. Pega o convidado criado DENTRO do
    # diretório da Grid, que chega sem `idp` e com e-mail @gridco.com.br. Sem a declaração (a T.I. não a ligou), vale o
    # resto das conferências
    if "acct" in c and str(c.get("acct")).strip() != "0":
        raise Recusado(convidado, "convidado (acct)", contar=True)
    email = ""
    for campo in ("email", "preferred_username", "upn"):
        candidato = str(c.get(campo) or "").strip().lower()
        m = _EMAIL.match(candidato)
        if m and m.group(1) in doms:
            email = candidato
            break
    if not email:
        achados = sorted({re.sub(r"[^a-z0-9.-]", "", str(c.get(k) or "").rpartition("@")[2].lower())[:60]
                          for k in ("email", "preferred_username", "upn") if "@" in str(c.get(k) or "")})
        raise Recusado(de_fora, f"e-mail de fora da Grid (domínios: {', '.join(achados) or 'nenhum'})", contar=True)
    nome = " ".join(str(c.get("name") or "").split())[:120] or email.split("@")[0]
    return {"email": email, "nome": nome}
