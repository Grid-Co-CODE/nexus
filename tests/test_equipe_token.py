"""O ID token da Microsoft que a página do App de Campo manda ao registrar o celular no Nexus Field (Mapa de equipe,
08/11/2026; `nexus/campo/equipe/token_ms.py`).

A rota é pública e o token vem do navegador: o Nexus confere a ASSINATURA pelas chaves públicas da Microsoft (aqui, pares
RSA gerados no teste e o JWKS montado deles), só RS256 e antes de tocar em chave, e depois quem é da Grid pelas regras do
login (`tid`/`iss` do diretório, `aud` do App de Campo, prazo com 120 s de folga, não convidado, e-mail de um domínio da
Grid comparado inteiro). A página manda o `idToken || accessToken` do MSAL: o token de acesso do Graph é recusado, não
quebra. Microsoft fora do ar não é token inválido (503 na rota, e não o 401, que apagaria a chave da casca). Nada vai à
rede: as chaves são injetadas ou o `_pedir_jwks` é dublado; os GUIDs são de mentira."""
import base64
import hashlib
import hmac
import json

import pytest
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from conftest import SENHA_TESTE
from nexus import create_app
from nexus.auth import chaves as K
from nexus.campo.equipe import token_ms as T

DIRETORIO = "11111111-2222-3333-4444-555555555555"
OUTRO_DIRETORIO = "99999999-8888-7777-6666-555555555555"
CLIENTE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OUTRO_APP = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
GRAPH = "00000003-0000-0000-c000-000000000000"      # o aud do token de acesso do Microsoft Graph
EMISSOR = f"https://login.microsoftonline.com/{DIRETORIO}/v2.0"
JWKS_URL = f"https://login.microsoftonline.com/{DIRETORIO}/discovery/v2.0/keys"
EMAIL = "tecnico@gridco.com.br"
AGORA = 1_794_000_000.0       # um instante parado: o prazo do token não depende do relógio da máquina
KID, KID_NOVO = "kid-de-teste-1", "kid-de-teste-2"
NOMES = ("NEXUS_EQUIPE_MS_CLIENT_ID", "NEXUS_EQUIPE_MS_TENANT_ID")

CHAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)     # a da "Microsoft"
OUTRA = rsa.generate_private_key(public_exponent=65537, key_size=2048)     # a de quem forja
NOVA = rsa.generate_private_key(public_exponent=65537, key_size=2048)      # a que a "Microsoft" girou depois


def _b64(dado: bytes) -> str:
    return base64.urlsafe_b64encode(dado).decode("ascii").rstrip("=")


def _inteiro(n: int) -> str:
    return _b64(n.to_bytes((n.bit_length() + 7) // 8, "big"))


def _jwk(privada, kid: str) -> dict:
    """A chave pública no formato do JWKS da Microsoft (o `n` e o `e` em base64url)."""
    pub = privada.public_key().public_numbers()
    return {"kty": "RSA", "use": "sig", "kid": kid, "n": _inteiro(pub.n), "e": _inteiro(pub.e)}


JWKS = {"keys": [_jwk(CHAVE, KID)]}
JWKS_GIRADO = {"keys": [_jwk(CHAVE, KID), _jwk(NOVA, KID_NOVO)]}


def _claims(em: float = AGORA, **mudar) -> dict:
    """O corpo do ID token do App de Campo, emitido em `em`; `declaracao=None` tira a declaração."""
    c = {"iss": EMISSOR, "aud": CLIENTE, "tid": DIRETORIO, "iat": em - 5, "nbf": em - 5, "exp": em + 3600, "ver": "2.0",
         "name": "Técnico Teste", "preferred_username": "Tecnico@GridCo.com.br", "oid": "oid-de-teste",
         "sub": "sub-de-teste"}
    c.update(mudar)
    return {k: v for k, v in c.items() if v is not None}


def _assinar(cab: dict, corpo, privada=CHAVE) -> str:
    """O JWT compacto (cabeçalho.corpo.assinatura em base64url sem "="), assinado como o `alg` do cabeçalho diz."""
    bruto = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
    entrada = f"{_b64(json.dumps(cab).encode())}.{_b64(bruto)}"
    if cab.get("alg") == "none":
        assinatura = b""
    elif cab.get("alg") == "HS256":
        # a confusão de algoritmo: o HMAC com a chave PÚBLICA (que todo mundo tem) de segredo, que um conferidor que usa
        # o algoritmo dito pelo próprio token aceitaria
        publica = privada.public_key().public_bytes(serialization.Encoding.PEM,
                                                    serialization.PublicFormat.SubjectPublicKeyInfo)
        assinatura = hmac.new(publica, entrada.encode(), hashlib.sha256).digest()
    else:
        assinatura = privada.sign(entrada.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{entrada}.{_b64(assinatura)}"


def _token(privada=CHAVE, cab: dict | None = None, em: float = AGORA, **mudar) -> str:
    cabecalho = {"typ": "JWT", "alg": "RS256", "kid": KID, **(cab or {})}
    return _assinar({k: v for k, v in cabecalho.items() if v is not None}, _claims(em, **mudar), privada)


def _token_de_acesso_do_graph() -> str:
    """Como o token de acesso do Graph, que a página manda quando o MSAL não devolve o ID token: o aud do Graph e um
    `nonce` no cabeçalho, com a assinatura feita sobre o cabeçalho com o hash dele (por isso ninguém fora da Microsoft
    a confere)."""
    nonce = "nonce-de-teste"
    assinado = _assinar({"typ": "JWT", "nonce": hashlib.sha256(nonce.encode()).hexdigest(), "alg": "RS256", "kid": KID},
                        _claims(aud=GRAPH))
    enviado = _b64(json.dumps({"typ": "JWT", "nonce": nonce, "alg": "RS256", "kid": KID}).encode())
    return enviado + assinado[assinado.index("."):]


def _com_outro_corpo(token: str, corpo: dict) -> str:
    """O token com o corpo trocado depois de assinado (fica a assinatura de antes)."""
    cab, _corpo, assinatura = token.split(".")
    return f"{cab}.{_b64(json.dumps(corpo).encode())}.{assinatura}"


def _conferir(token, **kw):
    """Com as chaves injetadas e o relógio parado: nada de Microsoft."""
    return T.conferir(token, **{"cliente": CLIENTE, "diretorio": DIRETORIO, "chaves_jwks": JWKS, "agora": AGORA, **kw})


def _pela_microsoft(token, agora=AGORA):
    """Sem chaves injetadas: o JWKS vem da cópia e, sem ela, do `_pedir_jwks` (o dublê do teste)."""
    return T.conferir(token, cliente=CLIENTE, diretorio=DIRETORIO, agora=agora)


class _Resposta:
    def __init__(self, status=200, corpo=None):
        self.status_code, self._corpo = status, corpo

    def json(self):
        if isinstance(self._corpo, Exception):
            raise self._corpo
        return self._corpo


class Microsoft:
    """O endpoint das chaves de mentira: guarda cada endereço pedido e devolve o que o teste pôs em `resposta`."""

    def __init__(self, monkeypatch):
        self.urls, self.resposta = [], _Resposta(200, JWKS)
        monkeypatch.setattr(T, "_pedir_jwks", self._get)

    def _get(self, url):
        self.urls.append(url)
        if isinstance(self.resposta, Exception):
            raise self.resposta
        return self.resposta


@pytest.fixture(autouse=True)
def _sem_rede_e_sem_copia(monkeypatch):
    """Cada teste começa sem a cópia das chaves, e nenhum vai à Microsoft de verdade (quem precisa dela põe o dublê)."""
    def a_rede(url):
        raise AssertionError(f"pedido de verdade à Microsoft: {url}")
    monkeypatch.setattr(T, "_pedir_jwks", a_rede)
    T._GUARDADAS.clear()
    T._RELEITURA.clear()
    yield
    T._GUARDADAS.clear()
    T._RELEITURA.clear()


@pytest.fixture
def ms(monkeypatch):
    return Microsoft(monkeypatch)


# ── o que passa ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_id_token_do_app_passa_e_devolve_o_email():
    assert _conferir(_token()) == EMAIL           # o preferred_username, em minúscula


@pytest.mark.parametrize("caso, mudar, kw, email", [
    ("venceu há 119 s: a folga do relógio", {"exp": AGORA - 119}, {}, EMAIL),
    ("nbf daqui a 119 s: a folga do relógio", {"nbf": AGORA + 119}, {}, EMAIL),
    ("sem nbf", {"nbf": None}, {}, EMAIL),
    ("aud numa lista", {"aud": [CLIENTE]}, {}, EMAIL),
    ("os GUIDs colados em maiúscula na tela", {}, {"cliente": CLIENTE.upper(), "diretorio": DIRETORIO.upper()}, EMAIL),
    ("membro (acct 0)", {"acct": 0}, {}, EMAIL),
    ("idp do próprio diretório", {"idp": f"https://sts.windows.net/{DIRETORIO}/"}, {}, EMAIL),
    ("sem preferred_username, vale o upn", {"preferred_username": None, "upn": "Tecnico@GridCo.com.br"}, {}, EMAIL),
    ("sem preferred_username nem upn, vale o email", {"preferred_username": None, "email": "TECNICO@gridco.com.br"}, {},
     EMAIL),
    ("outro domínio da Grid (o NEXUS_MS_DOMINIOS)", {"preferred_username": "tecnico@grid.exemplo.test"},
     {"dominios": ("gridco.com.br", "grid.exemplo.test")}, "tecnico@grid.exemplo.test"),
])
def test_tambem_passa(caso, mudar, kw, email):
    assert _conferir(_token(**mudar), **kw) == email, caso


# ── o que não passa ─────────────────────────────────────────────────────────────────────────────────────────────────
RECUSADOS = [
    ("assinatura de outra chave", lambda: _token(privada=OUTRA)),
    ("corpo trocado depois da assinatura",
     lambda: _com_outro_corpo(_token(), _claims(preferred_username="chefe@gridco.com.br"))),
    ("alg none", lambda: _token(cab={"alg": "none"})),
    ("alg HS256 com a chave pública de segredo", lambda: _token(cab={"alg": "HS256"})),
    ("alg RS512", lambda: _token(cab={"alg": "RS512"})),
    ("alg rs256 em minúscula", lambda: _token(cab={"alg": "rs256"})),
    ("sem alg", lambda: _token(cab={"alg": None})),
    ("sem kid", lambda: _token(cab={"kid": None})),
    ("kid que as chaves não têm", lambda: _token(privada=NOVA, cab={"kid": KID_NOVO})),
    ("crit no cabeçalho", lambda: _token(cab={"crit": ["exp"]})),
    ("aud do Graph", lambda: _token(aud=GRAPH)),
    ("token de acesso do Graph (nonce no cabeçalho)", _token_de_acesso_do_graph),
    ("aud de outro aplicativo", lambda: _token(aud=OUTRO_APP)),
    ("aud com outro aplicativo junto", lambda: _token(aud=[CLIENTE, GRAPH])),
    ("sem aud", lambda: _token(aud=None)),
    ("outro diretório (tid e iss)",
     lambda: _token(tid=OUTRO_DIRETORIO, iss=f"https://login.microsoftonline.com/{OUTRO_DIRETORIO}/v2.0")),
    ("iss de outro diretório", lambda: _token(iss=f"https://login.microsoftonline.com/{OUTRO_DIRETORIO}/v2.0")),
    ("tid de outro diretório", lambda: _token(tid=OUTRO_DIRETORIO)),
    ("sem tid", lambda: _token(tid=None)),
    ("emissor v1 (sts.windows.net)", lambda: _token(iss=f"https://sts.windows.net/{DIRETORIO}/")),
    ("vencido há mais de 120 s", lambda: _token(exp=AGORA - 121)),
    ("sem exp", lambda: _token(exp=None)),
    ("exp em texto", lambda: _token(exp=str(AGORA + 3600))),
    ("nbf no futuro além de 120 s", lambda: _token(nbf=AGORA + 121)),
    ("convidado pelo #EXT#", lambda: _token(preferred_username="tecnico_exemplo.test#EXT#@gridcoexemplo.onmicrosoft.com")),
    ("convidado de outro diretório (idp)", lambda: _token(idp=f"https://sts.windows.net/{OUTRO_DIRETORIO}/")),
    ("convidado com conta pessoal (idp)", lambda: _token(idp="live.com")),
    ("convidado criado no diretório (acct)", lambda: _token(acct=1)),
    ("domínio fora da Grid", lambda: _token(preferred_username="tecnico@exemplo.test")),
    ("domínio parecido no fim", lambda: _token(preferred_username="tecnico@gridco.com.br.x.com")),
    ("domínio parecido no começo", lambda: _token(preferred_username="tecnico@xgridco.com.br")),
    # a pessoa é o preferred_username (o mesmo que o servidor do App usa): o email da Grid ao lado não o troca
    ("preferred_username de fora com o email da Grid ao lado",
     lambda: _token(preferred_username="tecnico@exemplo.test", email=EMAIL)),
    ("sem e-mail", lambda: _token(preferred_username=None)),
]


@pytest.mark.parametrize("caso, fazer", RECUSADOS)
def test_recusa(caso, fazer):
    token = fazer()
    with pytest.raises(T.TokenRecusado) as e:
        _conferir(token)
    # o texto da recusa pode ir ao journal: nunca leva pedaço do token nem o e-mail
    texto = str(e.value)
    assert texto and not any(p in texto for p in token.split(".") if len(p) >= 8), caso
    assert "tecnico@" not in texto.lower() and "chefe@" not in texto.lower(), caso


@pytest.mark.parametrize("caso, token", [
    ("vazio", ""),
    ("nada", None),
    ("em bytes", b"abc.def.ghi"),
    ("sem pontos", "abc"),
    ("duas partes", "abc.def"),
    ("quatro partes", "abc.def.ghi.jkl"),
    ("fora do base64url", "ab+c.def.ghi"),
    ("com o = do base64", "abc=.def.ghi"),
    ("com acento", "çãé.def.ghi"),
    ("cabeçalho que não é JSON", f"{_b64(b'nao e json')}.e30.c2ln"),
    ("cabeçalho que é uma lista", f"{_b64(b'[1, 2]')}.e30.c2ln"),
    ("cabeçalho JSON fundo demais", f"{_b64(b'[' * 5000 + b']' * 5000)}.e30.c2ln"),
    ("RS256 sem assinatura", _token().rsplit(".", 1)[0] + "."),
    ("corpo assinado que não é JSON", _assinar({"alg": "RS256", "kid": KID}, b"nao e json")),
    ("grande demais", _token(name="x" * 20_000)),
])
def test_token_ilegivel_e_recusado_sem_quebrar(caso, token):
    with pytest.raises(T.TokenRecusado):
        _conferir(token)


# ── as chaves da Microsoft ──────────────────────────────────────────────────────────────────────────────────────────
def test_o_cabecalho_ruim_e_recusado_antes_de_qualquer_chave(ms):
    """O alg none, o HS256 e o token sem kid caem antes de tocar em chave: nem a cópia das chaves é buscada."""
    for cab in ({"alg": "none"}, {"alg": "HS256"}, {"kid": None}):
        with pytest.raises(T.TokenRecusado):
            _pela_microsoft(_token(cab=cab))
    assert ms.urls == []


def test_as_chaves_vem_do_diretorio_da_grid_e_a_copia_vale_24_h(ms):
    assert _pela_microsoft(_token()) == EMAIL
    assert ms.urls == [JWKS_URL]
    em = AGORA + 24 * 3600 - 1
    assert _pela_microsoft(_token(em=em), agora=em) == EMAIL and len(ms.urls) == 1
    em = AGORA + 24 * 3600
    assert _pela_microsoft(_token(em=em), agora=em) == EMAIL and ms.urls == [JWKS_URL] * 2


@pytest.mark.parametrize("caso, resposta", [
    ("sem rede", requests.ConnectionError("sem rede")),
    ("demorou", requests.Timeout("demorou")),
    ("HTTP 503", _Resposta(503, {"error": "temporarily_unavailable"})),
    ("HTTP 404", _Resposta(404, None)),
    ("página que não é JSON (um proxy no caminho)", _Resposta(200, ValueError("não é JSON"))),
    ("JSON sem a lista de chaves", _Resposta(200, {"erro": "x"})),
    ("lista de chaves vazia", _Resposta(200, {"keys": []})),
])
def test_microsoft_fora_do_ar_nao_e_token_invalido(ms, caso, resposta):
    ms.resposta = resposta
    with pytest.raises(T.MicrosoftForaDoAr) as e:
        _pela_microsoft(_token())
    assert not isinstance(e.value, T.TokenRecusado), caso      # 503 na rota (a casca tenta de novo), nunca 401
    # nada ficou guardado: com a Microsoft de volta, o mesmo token passa
    ms.resposta = _Resposta(200, JWKS)
    assert _pela_microsoft(_token()) == EMAIL and len(ms.urls) == 2, caso


def test_kid_desconhecido_rele_uma_vez_e_recusa(ms):
    _pela_microsoft(_token())                                       # a cópia do dia
    em = AGORA + 3600
    with pytest.raises(T.TokenRecusado):
        _pela_microsoft(_token(privada=OUTRA, cab={"kid": "kid-inventado"}, em=em), agora=em)
    assert ms.urls == [JWKS_URL] * 2                               # uma releitura, e não mais


def test_a_chave_que_a_microsoft_girou_entra_pela_releitura(ms):
    _pela_microsoft(_token())                                       # a cópia do dia, só com a chave de antes
    ms.resposta = _Resposta(200, JWKS_GIRADO)
    em = AGORA + 3600
    girado = _token(privada=NOVA, cab={"kid": KID_NOVO}, em=em)
    assert _pela_microsoft(girado, agora=em) == EMAIL and len(ms.urls) == 2
    assert _pela_microsoft(girado, agora=em + 1) == EMAIL and len(ms.urls) == 2    # a nova ficou na cópia


def test_o_kid_desconhecido_rele_no_maximo_uma_vez_a_cada_5_min(ms):
    """Sem o teto, um token com `kid` inventado faria o Nexus bater na Microsoft a cada pedido."""
    _pela_microsoft(_token())                                       # a cópia chega em AGORA

    def inventado(em):
        with pytest.raises(T.TokenRecusado):
            _pela_microsoft(_token(privada=OUTRA, cab={"kid": "kid-inventado"}, em=em), agora=em)
    for em in (AGORA + 1, AGORA + 299):                             # a cópia tem menos de 5 min: reler traria a mesma
        inventado(em)
    assert len(ms.urls) == 1
    for em in (AGORA + 300, AGORA + 301, AGORA + 599):              # uma releitura, e 5 min sem ir de novo
        inventado(em)
    assert len(ms.urls) == 2
    inventado(AGORA + 600)                                          # 5 min depois da releitura, outra
    assert len(ms.urls) == 3


def test_a_releitura_que_falha_e_microsoft_fora_e_tambem_conta_no_teto(ms):
    _pela_microsoft(_token())                                       # a cópia do dia, só com a chave de antes
    ms.resposta = requests.ConnectionError("sem rede")

    def girado(em):
        return _token(privada=NOVA, cab={"kid": KID_NOVO}, em=em)
    with pytest.raises(T.MicrosoftForaDoAr):                       # não deu para conferir: 503, e não 401
        _pela_microsoft(girado(AGORA + 600), agora=AGORA + 600)
    with pytest.raises(T.MicrosoftForaDoAr):                       # nos 5 min seguintes: sem ir de novo, ainda 503
        _pela_microsoft(girado(AGORA + 899), agora=AGORA + 899)
    assert len(ms.urls) == 2
    assert _pela_microsoft(_token(em=AGORA + 899), agora=AGORA + 899) == EMAIL     # a cópia vale para a chave que tem
    ms.resposta = _Resposta(200, JWKS_GIRADO)                       # a Microsoft de volta, com a chave nova
    assert _pela_microsoft(girado(AGORA + 900), agora=AGORA + 900) == EMAIL and len(ms.urls) == 3


@pytest.mark.parametrize("kw", [{"diretorio": "gridco.com.br"}, {"diretorio": ""}, {"cliente": CLIENTE + "0"},
                                {"cliente": None}])
def test_configuracao_que_nao_e_guid_e_erro_de_configuracao_e_nao_recusa_calada(kw):
    """O diretório escrito como domínio nunca casaria com o `tid`: recusar todo celular calado esconderia o engano."""
    with pytest.raises(ValueError) as e:
        _conferir(_token(), **kw)
    assert not isinstance(e.value, (T.TokenRecusado, T.MicrosoftForaDoAr))


# ── os dois IDs na tela Base → Chaves das fontes → Nexus, sem a T.I. ───────────────────────────────────────────────
@pytest.mark.parametrize("nome", NOMES)
def test_os_dois_ids_entram_pela_tela_so_como_guid(nome):
    d = K.CHAVES[nome]
    assert "Mapa de equipe" in d["nome"] and "App de Campo" in d["para"] and "Nexus Field" in d["para"]
    assert d["dica"] and not d["arquivo"]
    assert d["conferir"](CLIENTE) and d["conferir"](DIRETORIO.upper())       # como o portal do Entra mostra, ou maiúscula
    for ruim in ("gridco.com.br", CLIENTE[:-1], CLIENTE + "0", "{" + CLIENTE + "}", CLIENTE.replace("-", ""), "g" * 36):
        with pytest.raises(K.Recusada) as e:
            d["conferir"](ruim)
        assert ruim not in str(e.value)                                       # a recusa não repete o valor colado


def test_o_id_gravado_pela_tela_vale_na_hora_e_aparece_na_aba_nexus(tmp_path):
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste-" + "x" * 20, "NEXUS_SENHA_ADMIN": SENHA_TESTE,
                      "NEXUS_DADOS": str(tmp_path / "dados")})
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    app.extensions["nexus_dados_sessao"] = object()       # o "banco": a aba das chaves não lê nada dele
    K._CACHE.clear()
    try:
        aviso = K.gravar(app.config, "NEXUS_EQUIPE_MS_TENANT_ID", DIRETORIO, "admin@exemplo.test")
        assert "gravada e já em uso" in aviso
        assert K.valor("NEXUS_EQUIPE_MS_TENANT_ID", app.config) == DIRETORIO
        c = app.test_client()
        assert c.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
        h = c.get("/t/base/chaves-fontes?aba=nexus").get_data(as_text=True)
        assert all(n in h for n in NOMES) and "Mapa de equipe" in h
        assert DIRETORIO not in h                                             # a tela nunca mostra o valor
    finally:
        K._CACHE.clear()
