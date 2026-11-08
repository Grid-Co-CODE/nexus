"""O ID token da Microsoft que a página do App de Campo manda ao registrar o celular no Nexus Field (Mapa de equipe,
08/11/2026), conferido pela ASSINATURA.

Quem usa: a rota pública `POST /t/campo/equipe/aparelho`, chamada pela PÁGINA do App de Campo (a `ORIGEM_APP` do pacote)
dentro da casca Android, com `Authorization: Bearer <token>`: só a página tem o login Microsoft, e o token nunca vai ao
nativo. O token é o `idToken || accessToken` do `acquireTokenSilent` do MSAL: o ID token do registro SPA do App de Campo e,
se o MSAL não devolver o ID token, o token de acesso do Graph (aud `00000003-0000-0000-c000-000000000000`), que aqui é
RECUSADO (401 na rota), nunca um 500.

**Por que aqui a assinatura É conferida** (e no login do Nexus, `nexus/auth/microsoft.py`, não): lá o id_token chega direto
do endpoint de token da Microsoft, numa conexão TLS com o certificado conferido, em troca do código, da chave do Nexus e
do PKCE, e aquele login não aceita token vindo do navegador. Aqui o token VEM do navegador, numa rota pública: qualquer um
manda o texto que quiser, e sem a assinatura um token forjado com o e-mail de um técnico registraria um aparelho no nome
dele e poria posições falsas no mapa. A conferência, nesta ordem:
1. o `alg` do cabeçalho é RS256, e só ele, ANTES de tocar em chave: o `none` e o HS256 "assinado" com a chave pública (a
   confusão de algoritmo) passariam num conferidor que usa o algoritmo que o próprio token diz;
2. a assinatura confere com a chave pública da Microsoft de mesmo `kid` (o JWKS do diretório,
   `https://login.microsoftonline.com/<diretório>/discovery/v2.0/keys`). Nenhuma declaração do corpo é lida antes dela;
3. quem é da Grid, pelas regras do login (o topo de `microsoft.py`): `tid` e `iss` do diretório da Grid (v2.0), `aud` = o
   ID do aplicativo do App de Campo, não convidado (`#EXT#`, `idp` de outra casa, `acct`) e e-mail de um domínio da Grid
   comparado inteiro (gridco.com.br.x.com e xgridco.com.br não passam);
4. o prazo: `exp` obrigatório, `exp` e `nbf` com 120 s de folga de relógio.
A pessoa é o `preferred_username` (sem ele, o `upn`; depois, o `email`), em minúscula: o mesmo que o servidor do App de
Campo usa para saber quem é, para o Nexus e o App nunca discordarem sobre a pessoa.

**Microsoft fora do ar não é token inválido.** Sem o JWKS (rede, prazo, HTTP diferente de 200, resposta que não é a lista
de chaves): `MicrosoftForaDoAr`, que a rota responde com 503, e a casca tenta de novo. O 401 (`TokenRecusado`) faria a
casca apagar a chave dela.

**A cópia das chaves vale 24 h** (a Microsoft gira as chaves em semanas). O `kid` que a cópia não tem pode ser uma chave
recém-girada: relê, no máximo uma vez a cada 5 min por diretório. Sem o teto, um token com `kid` inventado faria o Nexus
bater na Microsoft a cada pedido; o custo é um token com a chave recém-girada esperar até 5 min.

Sem biblioteca nova (o PyJWT pediria o `pip install` da T.I. no servidor): o `cryptography`, que já é dependência, confere
o RS256, e o `requests` busca o JWKS. Nada daqui vai ao log; o texto da recusa (que a rota pode pôr no journal) nunca leva
o token nem o e-mail (o domínio, sim, como no login).
"""
import base64
import json
import math
import re
import threading
import time

import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from ...auth import microsoft as MS

ALGORITMO = "RS256"
FOLGA_S = 120                    # a diferença de relógio aceita no exp e no nbf
GUARDA_S = 24 * 3600             # a cópia das chaves da Microsoft
RELEITURA_S = 5 * 60             # o teto da releitura pelo kid que a cópia não tem
ESPERA_S = 10                    # quanto se espera a Microsoft responder o JWKS
TAMANHO_MAX = 16 * 1024          # um ID token tem de 1 a 3 KB; o que passa disto nem é lido
_QUEM = ("preferred_username", "upn", "email")      # a pessoa, nesta ordem (a do servidor do App de Campo)
_SEGMENTO = re.compile(r"[A-Za-z0-9_-]*")            # base64url sem o "=", a forma compacta do JWT
_ALG_LEGIVEL = re.compile(r"[A-Za-z0-9]{1,16}")      # o alg recusado só vai ao texto se não puder forjar linha no journal

_TRAVA = threading.Lock()
_GUARDADAS: dict[str, tuple[float, dict]] = {}       # diretório -> (quando a cópia chegou, o JWKS)
_RELEITURA: dict[str, tuple[float, bool]] = {}       # diretório -> (a última releitura pelo kid, se deu certo)


class TokenRecusado(Exception):
    """O token não vale: a rota responde 401. O texto diz por quê, sem o token e sem o e-mail."""


class MicrosoftForaDoAr(Exception):
    """As chaves da Microsoft não vieram: não dá para conferir agora. A rota responde 503 e a casca tenta de novo, em vez
    do 401, que apagaria a chave dela."""


def _guid(valor, rotulo: str) -> str:
    """O GUID da configuração, em minúscula (o Entra escreve o token em minúscula; o colado em maiúscula não pode recusar
    todo mundo). Fora do formato é configuração errada, não token ruim: ValueError, para o engano aparecer no log em vez
    de recusar todo celular calado (o diretório escrito como domínio, gridco.com.br, nunca casaria com o `tid`)."""
    v = str(valor or "").strip().lower()
    if not MS._GUID.fullmatch(v):
        raise ValueError(f"{rotulo} não é um GUID do Entra ID: confira em Base → Chaves das fontes → Nexus")
    return v


def _b64d(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def _objeto(texto: str, parte: str) -> dict:
    """O cabeçalho ou o corpo: um objeto JSON em base64url."""
    try:
        valor = json.loads(_b64d(texto))
    except (ValueError, RecursionError):    # base64 ou JSON quebrado; o JSON fundo demais (o teto de tamanho já segura)
        raise TokenRecusado(f"{parte} ilegível") from None
    if not isinstance(valor, dict):
        raise TokenRecusado(f"{parte} não é um objeto JSON")
    return valor


def _instante(valor) -> float | None:
    """Um instante do JWT (segundos desde 1970). Texto, booleano, infinito ou nada: None."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    try:
        v = float(valor)
    except OverflowError:
        return None
    return v if math.isfinite(v) else None


def _ha_menos_de(segundos: float, agora: float, quando: float | None) -> bool:
    # o relógio que voltou (quando no futuro) conta como vencido: no máximo uma ida a mais, nunca a cópia presa
    return quando is not None and 0 <= agora - quando < segundos


def _pedir_jwks(url: str):
    """O GET do JWKS (separado para os testes trocarem; o `requests` confere o certificado)."""
    return requests.get(url, timeout=ESPERA_S)


def _baixar(diretorio: str) -> dict:
    url = f"{MS.AUTORIDADE}/{diretorio}/discovery/v2.0/keys"
    try:
        r = _pedir_jwks(url)
    except requests.RequestException as e:
        raise MicrosoftForaDoAr(f"chaves da Microsoft: {type(e).__name__}") from None
    if r.status_code != 200:
        raise MicrosoftForaDoAr(f"chaves da Microsoft: HTTP {r.status_code}")
    try:
        jwks = r.json()
    except ValueError:
        jwks = None
    # um proxy no caminho que devolve uma página com 200, ou um JWKS vazio: não é a Microsoft respondendo, e não se guarda
    if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list) or not jwks["keys"]:
        raise MicrosoftForaDoAr("chaves da Microsoft: a resposta não é a lista de chaves")
    return jwks


def chaves_da_microsoft(diretorio: str, *, reler: bool = False, agora: float | None = None) -> dict:
    """O JWKS do diretório: a cópia de 24 h e, sem ela, a Microsoft. `reler=True` (o kid que a cópia não tem) vai de novo,
    no máximo uma vez a cada 5 min; a releitura que falhou segue `MicrosoftForaDoAr` até a próxima vez (não deu para
    conferir, e isso não é token ruim). Sem resposta: `MicrosoftForaDoAr`, e nada fica guardado."""
    d = _guid(diretorio, "o diretório (NEXUS_EQUIPE_MS_TENANT_ID)")
    agora = time.time() if agora is None else float(agora)
    with _TRAVA:
        guardada = _GUARDADAS.get(d)
        if not reler:
            if guardada and _ha_menos_de(GUARDA_S, agora, guardada[0]):
                return guardada[1]
        else:
            ultima = _RELEITURA.get(d)
            if ultima and _ha_menos_de(RELEITURA_S, agora, ultima[0]):
                if not ultima[1]:
                    raise MicrosoftForaDoAr("chaves da Microsoft: a releitura de há menos de 5 min não teve resposta")
                return guardada[1] if guardada else {}
            if guardada and _ha_menos_de(RELEITURA_S, agora, guardada[0]):
                return guardada[1]                  # a cópia acabou de chegar: reler agora traria a mesma
            _RELEITURA[d] = (agora, False)          # a vez fica marcada antes da ida: dois pedidos juntos não vão os dois
    jwks = _baixar(d)                               # fora da trava: a Microsoft lenta não segura quem tem a cópia
    with _TRAVA:
        _GUARDADAS[d] = (agora, jwks)
        if reler:
            _RELEITURA[d] = (agora, True)
    return jwks


def _chave(jwks, kid: str):
    """A chave pública RSA de assinatura com este `kid` no JWKS; None se não há, ou se a do JWKS está ilegível."""
    chaves = jwks.get("keys") if isinstance(jwks, dict) else None
    for k in chaves if isinstance(chaves, list) else ():
        if not isinstance(k, dict) or k.get("kid") != kid or k.get("kty") != "RSA":
            continue
        if k.get("use", "sig") != "sig" or k.get("alg", ALGORITMO) != ALGORITMO:
            continue
        try:
            n, e = (int.from_bytes(_b64d(k[x]), "big") for x in ("n", "e"))
            return rsa.RSAPublicNumbers(e, n).public_key()
        except (KeyError, TypeError, ValueError):
            return None
    return None


def conferir(token: str, *, cliente: str, diretorio: str, chaves_jwks=None, agora: float | None = None,
             dominios: tuple[str, ...] = MS.DOMINIOS_PADRAO) -> str:
    """Confere o token que a página do App mandou e devolve o e-mail da pessoa, em minúscula (ver o topo do módulo).
    `TokenRecusado` = 401 na rota; `MicrosoftForaDoAr` = 503. `cliente` e `diretorio` são os GUIDs da configuração
    (`NEXUS_EQUIPE_MS_CLIENT_ID` e `NEXUS_EQUIPE_MS_TENANT_ID`; fora do formato, ValueError); `dominios`, os domínios
    de e-mail da Grid (a rota passa o `microsoft.dominios(cfg)`). `chaves_jwks` e `agora` são do teste: as chaves sem a
    Microsoft e o relógio parado."""
    cliente = _guid(cliente, "o cliente (NEXUS_EQUIPE_MS_CLIENT_ID)")
    diretorio = _guid(diretorio, "o diretório (NEXUS_EQUIPE_MS_TENANT_ID)")
    agora = time.time() if agora is None else float(agora)

    # 1. a forma e o cabeçalho, antes de qualquer chave
    if not isinstance(token, str) or not token or len(token) > TAMANHO_MAX:
        raise TokenRecusado("token vazio ou grande demais")
    partes = token.split(".")
    if len(partes) != 3 or not all(_SEGMENTO.fullmatch(p) for p in partes):
        raise TokenRecusado("não é um JWT (cabeçalho.corpo.assinatura em base64url)")
    cab64, corpo64, assinatura64 = partes
    cab = _objeto(cab64, "cabeçalho")
    alg = cab.get("alg")
    if alg != ALGORITMO:
        visto = alg if isinstance(alg, str) and _ALG_LEGIVEL.fullmatch(alg) else "?"
        raise TokenRecusado(f"algoritmo {visto} recusado: só RS256")
    if "crit" in cab:
        # extensão do cabeçalho que este conferidor não conhece: a especificação manda recusar (RFC 7515, 4.1.11)
        raise TokenRecusado("cabeçalho com crit")
    kid = cab.get("kid")
    if not isinstance(kid, str) or not kid:
        raise TokenRecusado("token sem kid")
    if not corpo64 or not assinatura64:
        raise TokenRecusado("token sem corpo ou sem assinatura")

    # 2. a assinatura, pela chave da Microsoft de mesmo kid
    if chaves_jwks is not None:
        chave = _chave(chaves_jwks, kid)
    else:
        chave = _chave(chaves_da_microsoft(diretorio, agora=agora), kid)
        if chave is None:                           # pode ser a chave que a Microsoft girou depois da cópia
            chave = _chave(chaves_da_microsoft(diretorio, reler=True, agora=agora), kid)
    if chave is None:
        raise TokenRecusado("kid que a Microsoft não publica")
    try:
        chave.verify(_b64d(assinatura64), f"{cab64}.{corpo64}".encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    except (InvalidSignature, ValueError):
        # o token de acesso do Graph leva um nonce no cabeçalho e é assinado sobre o hash dele: ninguém fora da Microsoft
        # confere essa assinatura. É o que chega quando o MSAL da página não devolve o ID token (o `|| accessToken`)
        graph = " (nonce no cabeçalho: é o token de acesso do Graph, não o ID token do App)" if "nonce" in cab else ""
        raise TokenRecusado(f"assinatura não confere{graph}") from None

    # 3. o corpo, só agora: quem é da Grid
    c = _objeto(corpo64, "corpo")
    emissor = f"{MS.AUTORIDADE}/{diretorio}/v2.0"
    if str(c.get("tid") or "").lower() != diretorio or str(c.get("iss") or "").lower() != emissor:
        raise TokenRecusado("diretório de fora (tid/iss)")
    aud = c.get("aud")
    aud = [str(a).lower() for a in aud] if isinstance(aud, list) else [str(aud or "").lower()]
    if aud != [cliente]:
        raise TokenRecusado("aud de outro aplicativo: não é o ID token do App de Campo")

    # 4. o prazo
    exp = _instante(c.get("exp"))
    if exp is None:
        raise TokenRecusado("token sem exp")
    if agora > exp + FOLGA_S:
        raise TokenRecusado("token vencido")
    if "nbf" in c:
        nbf = _instante(c.get("nbf"))
        if nbf is None or nbf > agora + FOLGA_S:
            raise TokenRecusado("token que ainda não vale (nbf)")

    # convidado (B2B): a conta de fora chega com o idp da casa dela, ou com #EXT# no nome de usuário; o `acct` (declaração
    # opcional: 0 = membro) pega o convidado criado dentro do diretório da Grid. As regras de `microsoft.conferir`
    idp = str(c.get("idp") or "").lower().rstrip("/")
    if idp and idp not in (emissor, f"https://sts.windows.net/{diretorio}"):
        raise TokenRecusado("convidado (idp de outra casa)")
    if any("#ext#" in str(c.get(k) or "").lower() for k in _QUEM):
        raise TokenRecusado("convidado (#EXT#)")
    if "acct" in c and str(c.get("acct")).strip() != "0":
        raise TokenRecusado("convidado (acct)")

    email = next((v for v in (str(c.get(k) or "").strip().lower() for k in _QUEM) if v), "")
    doms = {str(d).strip().lower().lstrip("@") for d in dominios}
    m = MS._EMAIL.fullmatch(email)
    if not m or m.group(1) not in doms:
        dominio = re.sub(r"[^a-z0-9.-]", "", email.rpartition("@")[2])[:60]
        raise TokenRecusado(f"e-mail de fora da Grid (domínio: {dominio or 'nenhum'})")
    return email
