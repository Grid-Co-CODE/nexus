"""api.py — acesso à API REST do Fracttal One.

Autenticação: OAuth2 client_credentials (FRACTTAL_CLIENT_ID/SECRET) — mesmo método do
dashboard. Alternativamente, um token Bearer direto via FRACTTAL_TOKEN (expira ~1h).

CRIAÇÃO DE OS: o REST /api/work_orders é baseado em referência de tarefa (não cria OS de texto
livre). A OS completa é criada pelo RPC interno (tasks.tasks_noscheduled_react_insert via
app.fracttal.com/rpc/proxy), igual ao web app — ver create_os_rpc abaixo. Esse RPC é autenticado
pelo JWT do LOGIN (sessão do usuário), colado em fracttal_login.txt (gitignored, expira ~12h).
As leituras (ativos/pessoal) continuam pelo OAuth client_credentials. IDs centralizados em CONFIG.

O QUE FICOU AQUI (etapa 5.3 do canto central, 31/10/2026; o mapa completo está no README desta pasta): o cliente do Fracttal. O
login e a sessão (o JWT, a renovação, `_rpc_headers`), o RPC (`_rpc_call`, `_rpc_chamar`, o cache das leituras de uma OS), a
tarefa que nasce (`create_os_rpc`, `_react_insert_post`), o S3 (`attach_imagem_os`, `s3_get_url`, `baixar_imagem`) e a
configuração. Quem fala com a rede direto fica neste arquivo, porque o Raio-X rotula o pedido preso pelo arquivo
(`nexus/casca/presos.py`: "Fracttal (OS Creator)"). Tudo o mais mora no módulo do assunto (`os_criar`, `os_historico`,
`os_detalhe`, `os_estado`, `os_anexos`, `os_execucao`, `os_planos`, `os_solicitacoes`, `os_chamados`, `perf_alvos`,
`ativos_carga`, `catalogos_rpc`, `os_tempo`, `dash_os`), e este arquivo termina com a FACHADA: os mesmos nomes de sempre
(`api.X`), porque a ponte, as rotas e os testes chamam e TROCAM `api.X` pelo nome.
"""
import os
import re
import sys
import json
import time
import uuid
import base64
import hashlib
import threading
import requests
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import contextlib
import contextvars
from dotenv import load_dotenv

try:                       # cofre do SO (Windows Credential Manager) — opcional
    import keyring
    _HAS_KEYRING = True
except Exception:
    _HAS_KEYRING = False

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# O pacote `chamado_garantia` mora na RAIZ do repositório (é compartilhado com o app de campo),
# então a raiz precisa estar no sys.path para o import dele funcionar. No .exe isto é inócuo: o
# PyInstaller já empacota o pacote via pathex/hiddenimports do .spec.
#
# APPEND, NUNCA insert(0). A raiz tem um `app.py` — o da PLATAFORMA — e este projeto tem outro,
# `os_creator/app.py`. Com a raiz na frente do sys.path, um `import app` feito depois do `import
# api` resolvia para o da plataforma: medido, ele chegou a EXECUTAR o boot dela (carregou tickets
# e ronda) dentro do processo do OS Creator. No append, os_creator continua vencendo para `app` e
# a raiz só é consultada para o que não existe aqui — que é justamente o chamado_garantia.
_RAIZ_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ_REPO not in sys.path:
    sys.path.append(_RAIZ_REPO)

BASE          = os.environ.get("FRACTTAL_BASE_URL", "https://app.fracttal.com").rstrip("/")
CLIENT_ID     = os.environ.get("FRACTTAL_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("FRACTTAL_CLIENT_SECRET", "").strip()
STATIC_TOKEN  = os.environ.get("FRACTTAL_TOKEN", "").strip()

# ── Config do Fracttal (AJUSTAR conforme a conta — ver comentários) ───────────
# Responsáveis permitidos no Step 4 (filtro por nome no /api/personnel).
RESPONSAVEIS = ["Roger Lélis", "Gabriela Dias", "Ana Patrícia", "Levi Maia"]

# Tipo de tarefa (Step 2) → id_task_type_main do Fracttal. Descobertos via GET /api/tasks/types/
# (campos id_task_type_main + tasks_types_main_description). Referência completa da conta 4987.
# Mostramos TODOS os tipos disponíveis (sem filtro) — a ordem aqui é a ordem do dropdown.
TASK_TYPE_MAIN = {
    "Corretiva":             43885,
    "Corretiva Emergencial": 45742,
    "Preventiva":            43886,
    "Preditiva":             43887,
    "Inspeção":              43889,
    "Handover":              43888,
    "Administrativa":        45606,
}
TASK_TYPES = list(TASK_TYPE_MAIN.keys())   # opções do dropdown "Tipo de Tarefa" (Step 2)

# Criticidade → id_priorities (1=Muito alto, 2=Alto, 3=Médio, 4=Baixo, 5=Muito baixo).
# Confirmado pela cURL de criação. O usuário escolhe no dropdown; default = Médio (3).
ID_PRIORITIES = 2                              # fallback p/ chamadas antigas (clone) sem criticidade
CRITICIDADES = [("Muito alto", 1), ("Alto", 2), ("Médio", 3), ("Baixo", 4), ("Muito baixo", 5)]
CRITICIDADE_DEFAULT = 3                         # Médio (wizard / OS única)
CRITICIDADE_MUITO_ALTO = 1                      # F1: default do COS (religamento é ~sempre crítico)

# Listas AO VIVO de Tipo de tarefa + Classificação 1/2 (o dropdown estático não traz Religamento etc.)
RPC_TIPOS_MAIN = "tasks.tasks_types_main_list"   # Tipo de tarefa  → id_task_type_main
RPC_TIPOS_C1   = "tasks.tasks_types_list"        # Classificação 1 → id_task_type
RPC_TIPOS_C2   = "tasks.tasks_types_2_list"      # Classificação 2 → id_task_type_2

# ── Endpoints do RPC interno (criação de OS de verdade, igual ao web app) ──────
# O REST OAuth (client_credentials) NÃO cria OS — só Solicitação. A OS completa
# (subtarefas/tipo/etc.) vem do RPC, autenticado pelo JWT do LOGIN (sessão Fracttal).
RPC_TOKEN_URL  = "https://one.fracttal.com/rpc/token"   # renova o JWT da sessão
RPC_PROXY_URL  = "https://app.fracttal.com/rpc/proxy"   # executa tasks.tasks_noscheduled_react_insert
RPC_METHOD     = "tasks.tasks_noscheduled_react_insert"
def _data_dir() -> str:
    """Pasta de dados GRAVÁVEL do usuário (%APPDATA%/CriarOS-Fracttal). Funciona rodando como
    script OU empacotado em .exe (onde a pasta do app não é gravável)."""
    base = os.environ.get("APPDATA") or os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~")
    d = os.path.join(base, "CriarOS-Fracttal")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


class _ExecutorComContexto(ThreadPoolExecutor):
    """ThreadPoolExecutor que LEVA O CONTEXTO da requisição para dentro das threads.

    O os_web guarda o JWT de quem está logado num `contextvars.ContextVar` — é o que permite duas
    pessoas usarem o serviço ao mesmo tempo sem misturar sessão. E ContextVar NÃO atravessa para
    as threads de um executor: cada worker nasce num contexto vazio, `em_requisicao()` devolve
    False e o `_read_jwt` costurado pelo os_web cai no ARQUIVO de token do app de mesa.

    No servidor esse arquivo não existe, então toda chamada paralela morria em FracttalError — e
    quem chama costuma engolir o erro com `return []`. O sintoma era mudo: escolher a usina no
    card "Inspeção Geral do Inversor" não trazia ativo nenhum, com a tela dizendo que a usina não
    tinha o plano (Levi, 17/09). Pior: onde o arquivo EXISTE, a thread trabalharia com o token de
    outra conta.

    `submit` é o único ponto a consertar: o `map` passa por ele. Uma cópia do contexto POR tarefa
    porque `Context.run` não é reentrante — duas threads no mesmo objeto levantam RuntimeError."""

    def submit(self, fn, /, *args, **kwargs):
        return super().submit(contextvars.copy_context().run, fn, *args, **kwargs)


# Leitura ENXUTA (Levi, 08/10/2026: "o carregamento de: Acompanhamento de chamados e a tela que abre quando clica na
# OS está demorando"): dentro de `with enxuta(...)`, as leituras pulam o que a tela que chamou não mostra.
#   "vinculos": `get_os_detalhes` sem a 2ª leva (solicitação, OS pai e cancelamento saem ''): 2 pedidos a menos;
#   "url":      `get_os_anexos` e `get_os_subtarefa_anexos` sem a URL pré-assinada (um s3_object_get por arquivo).
# Por CONTEXTO, e não por argumento: as rotas da web chamam estas funções com um argumento só, e os testes do oem as
# trocam por `lambda wid: ...` — um argumento novo quebraria todos. As threads do `_ExecutorComContexto` herdam.
_ENXUTA = contextvars.ContextVar("api_leitura_enxuta", default=frozenset())


@contextlib.contextmanager
def enxuta(*cortes):
    tok = _ENXUTA.set(_ENXUTA.get() | frozenset(cortes))
    try:
        yield
    finally:
        _ENXUTA.reset(tok)


def _cortado(nome: str) -> bool:
    return nome in _ENXUTA.get()


# JWT do login: obtido por fracttal_login() (a pessoa digita e-mail+senha). Guardado em
# %APPDATA%/CriarOS-Fracttal/fracttal_login.txt (gravável no .exe). Expira ~12h. A SENHA NUNCA
# é armazenada. Também aceita FRACTTAL_LOGIN_JWT (.env) como override manual.
LOGIN_JWT_FILE = os.path.join(_data_dir(), "fracttal_login.txt")
RPC_LOGIN_URL  = "https://app.fracttal.com/rpc/login_new"   # e-mail + MD5(senha) → JWT de sessão
RPC_PERSONNEL  = "personnel.personnel_list"                 # pessoal (RPC; campo id = id_responsible)
_KEYRING_SVC   = "os_creator_fracttal"
# Dados da empresa no login (NÃO são segredos — vêm do payload do web app).
ID_COMPANY   = int(os.environ.get("FRACTTAL_ID_COMPANY", "4987"))
ID_SERVER    = os.environ.get("FRACTTAL_ID_SERVER", "AMERICAN")
COMPANY_DESC = os.environ.get("FRACTTAL_COMPANY_DESC", "GRID CO. LTDA")


# Os dois erros moram em `fracttal_erro.py` (31/10/2026, etapa 5.3): os módulos que saíram deste arquivo precisam deles e não
# podem importar o `api` ao carregar. `api.FracttalError` e `api.SessionExpired` são os mesmos objetos de sempre.
from fracttal_erro import FracttalError, SessionExpired                              # noqa: E402,F401


# ── Autenticação ──────────────────────────────────────────────────────────────
_tok = {"token": "", "exp": 0.0}
_tok_lock = threading.Lock()


def _get_token() -> str:
    if STATIC_TOKEN:
        return STATIC_TOKEN
    with _tok_lock:
        if _tok["token"] and time.time() < _tok["exp"] - 60:
            return _tok["token"]
        if not (CLIENT_ID and CLIENT_SECRET):
            raise FracttalError("Sem credenciais no .env — defina FRACTTAL_CLIENT_ID e "
                                "FRACTTAL_CLIENT_SECRET (ou FRACTTAL_TOKEN).")
        try:
            r = requests.post(f"{BASE}/oauth/token",
                              data={"grant_type": "client_credentials",
                                    "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET},
                              timeout=20)
            r.raise_for_status()
            j = r.json()
        except requests.RequestException as e:
            raise FracttalError(f"Não foi possível autenticar no Fracttal: {e}")
        _tok["token"] = j.get("access_token", "")
        _tok["exp"]   = time.time() + float(j.get("expires_in", 3600) or 3600)
        if not _tok["token"]:
            raise FracttalError("Autenticação sem access_token na resposta.")
        return _tok["token"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_token()}",
            "Accept": "application/json", "Content-Type": "application/json"}


def _req(method: str, ep: str, **kw):
    url = f"{BASE}/api/{ep.lstrip('/')}"
    timeout = kw.pop("timeout", 30)
    try:
        r = requests.request(method, url, headers=_headers(), timeout=timeout, **kw)
        if r.status_code == 401 and not STATIC_TOKEN:      # token expirou → renova 1x
            _tok["token"] = ""
            r = requests.request(method, url, headers=_headers(), timeout=timeout, **kw)
        if r.status_code in (406, 429):                    # rate limit → espera e tenta 1x
            time.sleep(float(r.headers.get("ratelimit-reset") or 3))
            r = requests.request(method, url, headers=_headers(), timeout=timeout, **kw)
    except requests.RequestException as e:
        raise FracttalError(f"Erro de conexão com o Fracttal: {e}")
    if r.status_code >= 400:
        raise FracttalError(f"HTTP {r.status_code} — {_extract_error(r)}")
    try:
        return r.json()
    except ValueError:
        return {}


def _extract_error(r) -> str:
    """Mensagem amigável a partir do corpo de erro do Fracttal (inclui campos inválidos)."""
    try:
        j = r.json()
    except ValueError:
        return (r.text or "sem detalhes")[:200]
    if isinstance(j, dict):
        d = j.get("data")
        if isinstance(d, list) and d and isinstance(d[0], dict):
            inv = d[0].get("invalid_fields")
            if inv:
                return "campos obrigatórios faltando: " + ", ".join(
                    f"{f.get('field')} ({f.get('field_message')})" for f in inv)
            if d[0].get("ERROR"):
                return str(d[0]["ERROR"])
        return str(j.get("message") or j)[:200]
    return str(j)[:200]


def _to_iso(ddmmyyyy: str) -> str:
    """'18/06/2026' → '2026-06-18T00:00:00+00:00'. Aceita também ISO já pronto."""
    s = (ddmmyyyy or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%dT00:00:00+00:00")
        except ValueError:
            continue
    return datetime.now().strftime("%Y-%m-%dT00:00:00+00:00")


# ── Leituras (estáveis/testadas) ──────────────────────────────────────────────
def ping():
    """Valida credenciais cedo (1 chamada barata). Lança FracttalError se algo estiver errado."""
    _req("GET", "items/?limit=1")
    return True


# Tipo de equipamento a partir do code ({USINA}-{TIPO}{N}). A REGRA mora no `chamado_garantia`
# (03/08): o app de campo precisa classificar o ativo do mesmo jeito para escolher as subtarefas,
# e duas derivações significa dois apps pedindo coisas diferentes ao mesmo fabricante — num ponto
# invisível, porque ninguém percebe até o chamado voltar. Aqui ficou só o repasse.
from chamado_garantia.ativos import TIPO_POR_SUFIXO as TYPE_MAP     # noqa: E402  (nome antigo)
from chamado_garantia.ativos import tipo_e_sufixo


# O formato do registro do catálogo (cliente, usina e tipo derivados do caminho e do código) mora no `ativos_central`, ao lado
# do catálogo (31/10/2026, etapa 2 do canto central). Aqui ficaram os nomes de sempre: o `get_assets` e a leitura da etapa
# 2.2 montam com o `_build_records`, e o Histórico e o título "[Ativo] - ..." cortam o nome da usina com o `_usina_curta`.
import ativos_central                                                               # noqa: E402
from ativos_central import montar_registros as _build_records                       # noqa: E402,F401
from ativos_central import usina_curta as _usina_curta                              # noqa: E402,F401


# O CATÁLOGO: UM, central, em memória (`ativos_central`; 31/10/2026, etapa 2 do canto central). Até então o `assets_cache.json`
# era a fonte e cada `load_assets_cached()` entregava uma cópia da lista inteira (~26 mil dicionários) para quem pedia poder
# mexer à vontade. Agora a lista é UMA, compartilhada (os registros não aceitam escrita), montada com os índices uma vez por
# versão, e o boot vem da cópia em disco dela própria (ou do arquivo antigo, uma vez, ou da foto do banco): reiniciar o Nexus
# não pergunta nada ao Fracttal. A ponte do Nexus diz onde a cópia mora (`ativos_central.configurar`, ao criar o clone). A cola
# com as telas (`load_assets_cached`, a recarga pelo RPC, a renovação por trás) mora em `ativos_carga.py` (etapa 5.3); o caminho
# do arquivo antigo fica aqui porque os testes o trocam no `api`.
ASSETS_CACHE_LEGADO = os.path.join(_data_dir(), "assets_cache.json")      # o arquivo antigo: só migrado, uma vez


# A renovação por trás (o catálogo de ativos, acima, e os catálogos pequenos, `catalogos.renovar_por_tras`) roda numa thread
# com a cópia do contexto de quem pediu, e a cópia leva o MESMO dicionário de estado da sessão web dele: um 401 por trás
# marcava a sessão dela como morta, e o pedido dela, se ainda corria, saía para o login (revisão da 4.1, 31/10/2026). O
# `os_web.sessao.instalar` troca isto pelo `sessao.propria` (a mesma pessoa, com estado próprio); fora da web, nada a separar.
_sessao_propria = contextlib.nullcontext


def _na_sessao_propria(fn, *args):
    with _sessao_propria():
        return fn(*args)


# ── Escrita: OS de verdade via RPC interno (tasks_noscheduled_react_insert) ────
# O REST work_orders é baseado em referência de tarefa (dá 400 em texto livre). A OS completa
# (subtarefas/tipo/etc.) vem do RPC que o web app usa, autenticado pelo JWT do LOGIN (sessão).

def _save_jwt(jwt: str):
    """Guarda SÓ o JWT — no cofre do SO (keyring) ou, sem keyring, no arquivo gitignored."""
    if _HAS_KEYRING:
        try:
            keyring.set_password(_KEYRING_SVC, "login_jwt", jwt)
            return
        except Exception:
            pass
    try:
        with open(LOGIN_JWT_FILE, "w", encoding="utf-8") as f:
            f.write(jwt)
    except OSError:
        pass


def _read_jwt() -> str:
    """Lê o JWT: env override (FRACTTAL_LOGIN_JWT) → keyring → arquivo."""
    jwt = (os.environ.get("FRACTTAL_LOGIN_JWT", "") or "").strip()
    if not jwt and _HAS_KEYRING:
        try:
            jwt = (keyring.get_password(_KEYRING_SVC, "login_jwt") or "").strip()
        except Exception:
            jwt = ""
    if not jwt:
        try:
            with open(LOGIN_JWT_FILE, encoding="utf-8") as f:
                jwt = f.read().strip()
        except OSError:
            jwt = ""
    if jwt.lower().startswith("bearer "):
        jwt = jwt[7:].strip()
    return jwt


def _clear_jwt():
    if _HAS_KEYRING:
        try:
            keyring.delete_password(_KEYRING_SVC, "login_jwt")
        except Exception:
            pass
    try:
        if os.path.exists(LOGIN_JWT_FILE):
            os.remove(LOGIN_JWT_FILE)
    except OSError:
        pass


def _extract_login_jwt(j) -> str:
    """Acha o JWT na resposta do login_new (varre o JSON; formato flexível)."""
    def _scan(o):
        if isinstance(o, str):
            return o.replace("Bearer ", "").strip() if o.count(".") == 2 and len(o) > 60 else ""
        if isinstance(o, dict):
            for k in ("token", "access_token", "jwt", "id_token", "authorization"):
                v = o.get(k)
                if isinstance(v, str) and v.count(".") == 2:
                    return v.replace("Bearer ", "").strip()
            for v in o.values():
                r = _scan(v)
                if r:
                    return r
        if isinstance(o, list):
            for v in o:
                r = _scan(v)
                if r:
                    return r
        return ""
    return _scan(j)


def _encrypt_password(email: str, password: str, double: bool = True) -> str:
    """Replica o Util.encryptPassword do web app (achado no bundle index-*.js do Fracttal):
        inner = MD5(email + ':' + senha)
        final = MD5(email + ':' + inner)   # doubleEncrypt (padrão do web app)
    É por isso que MD5 simples era recusado (USER_OR_INVALID_KEY)."""
    inner = hashlib.md5(f"{email}:{password}".encode("utf-8")).hexdigest()
    if double:
        return hashlib.md5(f"{email}:{inner}".encode("utf-8")).hexdigest()
    return inner


def fracttal_login(email: str, password: str) -> dict:
    """Loga no Fracttal (rpc/login_new). A senha é transformada IGUAL ao web app
    (_encrypt_password = MD5 duplo com o e-mail como sal). Guarda o JWT e devolve {'email','jwt_exp'}.
    A SENHA NUNCA é armazenada — só usada pra obter o token."""
    email = (email or "").strip()
    if not email or not password:
        raise FracttalError("Informe e-mail e senha.")
    pw_enc = _encrypt_password(email, password)
    body = {"email": email, "password": pw_enc, "id_company": ID_COMPANY,
            "id_server": ID_SERVER, "description": COMPANY_DESC, "platform": "Fracttal/5.7.02 web"}
    try:
        r = requests.post(RPC_LOGIN_URL, json=body, timeout=25,
                          headers={"Content-Type": "application/json", "Accept": "*/*",
                                   "Origin": "https://app.fracttal.com"})
    except requests.RequestException as e:
        raise FracttalError(f"Erro de conexão no login: {e}")
    try:
        j = r.json()
    except ValueError:
        j = {}
    jwt = _extract_login_jwt(j)
    if not jwt:
        msg = str((j.get("message") if isinstance(j, dict) else "") or f"HTTP {r.status_code}")
        mu = msg.upper()
        if "BLOCK" in mu or "FAILURE_INTENT" in mu:
            raise FracttalError("Conta temporariamente BLOQUEADA (tentativas demais). Aguarde "
                                "~30 min SEM tentar e tente de novo. NÃO é senha errada.")
        if "USER_OR_INVALID" in mu or "INVALID_KEY" in mu:
            raise FracttalError("E-mail ou senha incorretos.")
        raise FracttalError(f"Login falhou: {msg}")
    _save_jwt(jwt)
    return {"email": email, "jwt_exp": _jwt_exp(jwt)}


def logout():
    _clear_jwt()


def current_user() -> str:
    """E-mail de quem está logado (lido do JWT), ou '' se não houver."""
    jwt = _read_jwt()
    if not jwt or jwt.count(".") != 2:
        return ""
    try:
        p = jwt.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p.encode())).get("email", "") or ""
    except Exception:
        return ""


def get_conta_info() -> dict:
    """Nome + cargo (perfil) do usuário logado, do Fracttal. → {'nome','email','perfil'}. Defensivo:
    tenta companies.load_account_info; se faltar o perfil, procura na lista de contas pelo e-mail."""
    email = current_user()
    nome, perfil = "", ""
    try:
        r = _rpc_call("companies.load_account_info", {"page": 1, "limit": 200, "start": 0, "append": True})
        data = r.get("data") if isinstance(r, dict) else r
        rec = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else {})
        rec = rec if isinstance(rec, dict) else {}
        nome = str(rec.get("name") or (str(rec.get("first_name") or "") + " "
                   + str(rec.get("last_name") or "")).strip()).strip()
        perfil = str(rec.get("profiles_description") or rec.get("profile_description")
                     or rec.get("profile") or "").strip()
    except FracttalError:
        pass
    if (not perfil or not nome) and email:
        try:
            r2 = _rpc_call("companies.accounts_react_list", {"filter": [], "sort": [], "page": 1,
                           "limit": 500, "start": 0, "is_tree": False, "node": None})
            d2 = r2.get("data") if isinstance(r2, dict) else r2
            for a in (d2 if isinstance(d2, list) else []):
                if isinstance(a, dict) and str(a.get("email") or "").lower() == email.lower():
                    perfil = perfil or str(a.get("profiles_description") or "").strip()
                    nome = nome or str(a.get("name") or "").strip()
                    break
        except FracttalError:
            pass
    return {"nome": nome or (email or "Usuário"), "email": email, "perfil": perfil}


def is_logged_in() -> bool:
    """Há um JWT válido (não vencido) E com sessão viva? A sessão pode ter sido morta server-side
    (USER_NOT_LOGIN) mesmo com o exp futuro — por isso faz 1 checagem ao vivo (barata)."""
    jwt = _read_jwt()
    if not jwt or jwt.count(".") != 2:
        return False
    exp = _jwt_exp(jwt)
    if not exp or time.time() >= exp - 30:
        return False
    try:
        _rpc_call(RPC_LABELS_LIST, {"sort": [], "page": 1, "limit": 1, "start": 0, "is_tree": False,
                  "node": None, "id_work_order": 0, "only_enabled": True}, timeout=20)
        return True
    except FracttalError:
        return False


def _login_jwt() -> str:
    """JWT da sessão (de _read_jwt). Lança FracttalError pedindo login se faltar/malformado."""
    jwt = _read_jwt()
    if not jwt or jwt.count(".") != 2:
        raise FracttalError("Você não está logado no Fracttal. Faça login no app (e-mail + senha).")
    return jwt


def jwt_sessao() -> str:
    """O JWT do login, para quem grava POR MEIO da plataforma (tickets_escrita): é a identidade
    que o relay confere no Fracttal antes de gravar. Nome público de propósito — `_login_jwt` é
    detalhe deste módulo, e o de escrita não deve depender de um sublinhado daqui."""
    return _login_jwt()


def _jwt_exp(jwt: str) -> float:
    """exp (epoch) do JWT, lendo o payload base64. 0 se não der pra ler."""
    try:
        p = jwt.split(".")[1]
        p += "=" * (-len(p) % 4)
        return float(json.loads(base64.urlsafe_b64decode(p.encode())).get("exp") or 0)
    except Exception:
        return 0.0


def _rpc_try_refresh(jwt: str) -> str:
    """POST /rpc/token (sem corpo, Bearer) → JWT renovado. Best-effort; persiste no arquivo.
    Devolve '' se não conseguir (aí o chamador pede a recolagem)."""
    try:
        r = requests.post(RPC_TOKEN_URL, timeout=20, headers={
            "Authorization": f"Bearer {jwt}", "Content-Type": "application/json",
            "Origin": "https://app.fracttal.com"})
        if r.status_code != 200:
            return ""
        new = ""
        try:
            j = r.json()
            if isinstance(j, str):
                new = j
            elif isinstance(j, dict):
                d = j.get("data") if isinstance(j.get("data"), dict) else {}
                new = (j.get("token") or j.get("access_token")
                       or d.get("token") or d.get("access_token") or "")
        except ValueError:
            new = (r.text or "").strip().strip('"')
        new = (new or "").strip()
        if new.count(".") == 2:
            try:
                with open(LOGIN_JWT_FILE, "w", encoding="utf-8") as f:
                    f.write(new)
            except OSError:
                pass
            return new
    except requests.RequestException:
        pass
    return ""


def _rpc_headers() -> dict:
    jwt = _login_jwt()
    exp = _jwt_exp(jwt)
    if exp and time.time() > exp - 60:          # perto de vencer → tenta renovar
        novo = _rpc_try_refresh(jwt)
        if novo:
            jwt = novo
        elif time.time() > exp:                 # já venceu e não renovou → recolar
            raise FracttalError("O JWT do login do Fracttal expirou — cole um novo em fracttal_login.txt.")
    return {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://app.fracttal.com", "x-version": "Fracttal/5.7.02 web"}


def _path_node(asset: dict) -> str:
    pid, iid = asset.get("id_parent"), asset.get("id")
    return f"{pid}.{iid}" if pid else str(iid)


# id_task_form_item_type → rótulo. SONDADO AO VIVO na conta 4987 (29/07), varrendo os form items de
# 70 OS e olhando o `value` gravado — não vale confiar na doc REST, que diz 3=Data e 5=Dropdown:
#   1 = Texto        ("Foi feita a coleta completa do período?")
#   2 = Sim/Não      (valores 'false' / 'N/A')
#   3 = Número       ("Quantas strings ativas o inversor possui?" → '13', '23')
#   4 = Verificação  (valores '1'/'2'/'3' → Aprovado/Alerta/Falhou, ver _VERIF_MAP)
#   7 = Lista        (traz `dropdown_options`; valores 'Sim', 'Normalizado')
# Faltavam o 2 e o 3: subtarefa desses tipos aparecia sem tipo ("—") no card da OS.
_FORM_ITEM_TYPE_DESC = {1: "Texto", 2: "Sim/Não", 3: "Número", 4: "Verificação", 7: "Lista"}


def _rpc_subtasks(subtasks: list, respostas: list = None) -> list:
    """Subtarefas no formato do RPC. Cada item pode ser:
      - str  → tipo Texto (id 1) — usado no Criar OS manual.
      - dict {description, id_task_form_item_type, task_form_item_type_description, ...} → PRESERVA
        o tipo original (usado na clonagem, p/ manter Verificação/Texto/etc. como na OS de origem).
    Mínimo 1 (default 'Procedimento'). Campos do tipo são copiados quando vêm no dict.
    `respostas` (opcional, paralelo por ordem) = respostas das subtarefas p/ OS já finalizada →
    injeta `value` em cada item (igual o web ao concluir a tarefa)."""
    norm = []
    for s in (subtasks or []):
        if isinstance(s, dict):
            d = str(s.get("description") or "").strip()
            if d:
                norm.append({**s, "description": d})
        else:
            d = str(s or "").strip()
            if d:
                norm.append({"description": d})
    if not norm:
        norm = [{"description": "Procedimento"}]
    out = []
    for i, s in enumerate(norm):
        tipo_id = s.get("id_task_form_item_type") or 1
        tipo_desc = _FORM_ITEM_TYPE_DESC.get(tipo_id) or s.get("task_form_item_type_description")
        item = {"id": str(uuid.uuid4()), "id_task_form_item_type": tipo_id,
                "id_task_form_item_group": s.get("id_task_form_item_group"),
                "order_number": i + 1, "description": s["description"],
                "task_form_item_type_description": tipo_desc,
                "task_form_item_group_description": s.get("task_form_item_group_description"),
                "is_required": bool(s.get("is_required", False)),
                "attachments_required": bool(s.get("attachments_required", False)),
                "is_new": False, "dropdown_options": s.get("dropdown_options"),
                "phantom": True, "num_attachments": 0}
        resp = None
        if respostas and i < len(respostas):
            resp = respostas[i]
        elif s.get("value") not in (None, ""):           # dict já trazendo a resposta
            resp = s.get("value")
        if resp not in (None, ""):
            item["value"] = resp                          # resposta da subtarefa (OS finalizada)
        out.append(item)
    return out


# Códigos que o RPC do Fracttal devolve em `message` quando recusa. Traduzir aqui é o que separa
# um "RPC recusou: WITHOUT_PERMITS" — que não diz a NINGUÉM o que fazer — de uma instrução. Só
# entram códigos VISTOS de verdade; inventar tradução para código que nunca apareceu é adivinhar.
_RPC_MSG = {
    # 19/08: um colaborador do COS levou isto ao tentar abrir OS de chamado. Não é bug do app —
    # a OS nasce com a conta de QUEM ESTÁ LOGADO, e o perfil dele no Fracttal não pode criar OS.
    "WITHOUT_PERMITS": ("Sua conta do Fracttal não tem permissão para criar OS. "
                        "A OS é criada no seu nome, com as suas permissões — quem libera é o "
                        "administrador do Fracttal (perfil do usuário). Para confirmar: tente "
                        "criar a mesma OS direto no Fracttal web; se lá também recusar, é o perfil."),
    "USER_HAS_EXECUTION_IN_PROGRESS": ("Existe um cronômetro aberto nesta tarefa — e só quem o "
                                       "iniciou pode encerrá-lo."),
    "FOREIGN_KEY_VIOLATION": ("O Fracttal recusou uma referência desta OS (ativo, plano ou "
                              "responsável). Recarregue o catálogo de ativos e tente de novo."),
}


def _msg_rpc(bruto) -> str:
    """Mensagem do RPC → texto acionável. Código desconhecido volta como veio, com o original
    entre parênteses — perder o código atrapalharia o diagnóstico da próxima vez."""
    cod = str(bruto or "").strip()
    amigavel = _RPC_MSG.get(cod.upper())
    return ("%s  (%s)" % (amigavel, cod)) if amigavel else (cod or "sem detalhe")


# O tempo estimado da OS avulsa quando ninguém escolhe outro: o `duration` que o web manda no formulário da tarefa não
# planejada (a captura deste caminho). A Fila do PCM mostra ele no "Tempo estimado:" da decisão (21/10/2026).
DURACAO_OS_AVULSA = 600


def create_os_rpc(asset: dict, description: str, task_type: str, subtasks: list,
                  requested_by: str = "", etiqueta: str = "", note: str = "",
                  event_date: datetime = None, tipo: dict = None, finalizar: dict = None,
                  id_parent=None, falha: dict = None, prog_date: datetime = None,
                  id_request=None, duracao: int = None) -> dict:
    """Cria uma OS (tarefa não-planejada) via RPC interno do Fracttal. asset = registro do
    get_assets() (precisa de id/id_parent/id_type_item/id_group_task). `event_date` = data
    programada (datetime; default = agora). `tipo` = dict opcional com id_main (id_task_type_main),
    id_priorities (criticidade) e Classificação 1/2 (id_c1/desc_c1, id_c2/desc_c2).
    `finalizar` (opcional) = OS JÁ REALIZADA → cria a WO concluída direto, com:
    {to_in_review(bool: True=Verificação, False=Finalizados), final_date(datetime), id_assigned_user
    (=id_personnel do responsável), name(str), respostas(list paralela às subtarefas)}.
    `duracao` = o tempo estimado da tarefa, em segundos (None = DURACAO_OS_AVULSA, como sempre).
    Devolve {'id_work_order','wo_folio','raw'}. Em erro, a mensagem do RPC é propagada (FracttalError)."""
    id_item = asset.get("id")
    if not id_item:
        raise FracttalError(f"Ativo '{asset.get('code')}' sem id_item — recarregue os ativos (cache antigo).")
    tipo = tipo or {}
    main_id = tipo.get("id_main")
    if main_id is None:                                   # chamadas antigas (clone): mapeia pelo nome
        main_id = TASK_TYPE_MAIN.get(task_type)
    if main_id is None:
        # o tipo que a lista fixa não tem, pelo catálogo vivo (29/10/2026: a Fila do PCM oferece os tipos do Fracttal, e
        # aprovar com "Zeladoria" dava "Tipo de tarefa desconhecido: Zeladoria" — a solicitação 4126 não virava OS)
        main_id = tipo_main_ao_vivo(task_type)
    if main_id is None:
        raise FracttalError(f"Tipo de tarefa desconhecido: {task_type}")
    prio = tipo.get("id_priorities")
    if prio is None:
        prio = ID_PRIORITIES
    fin = finalizar or {}
    finalizada = bool(fin)                                # "Esta tarefa já foi realizada?"
    em_verificacao = bool(fin.get("to_in_review"))       # True = Verificação; False = Finalizados
    ev = event_date if event_date is not None else datetime.now(timezone.utc)
    if ev.tzinfo is None:                                 # garante UTC-aware p/ o _iso_z
        ev = ev.replace(tzinfo=timezone.utc)
    # DATA PROGRAMADA separada da do INCIDENTE (Levi, 31/08 — o Tradicional passou a ter as
    # duas, como o Performance já tinha). `event_date` diz quando quebrou; `prog_date` diz
    # quando alguém vai lá. Sem `prog_date`, a programação é o próprio evento — exatamente o
    # comportamento anterior, para nenhum outro caminho (COS, Chamados, PCM, Clonar) mudar.
    prog = prog_date if prog_date is not None else ev
    if prog.tzinfo is None:
        prog = prog.replace(tzinfo=timezone.utc)
    fdt = fin.get("final_date")
    if fdt is not None and getattr(fdt, "tzinfo", None) is None:
        fdt = fdt.replace(tzinfo=timezone.utc)
    # O TEMPO ESTIMADO pode vir da tela (21/10/2026, Levi: "Gostaria que o PCM conseguisse mudar o tempo estimado para
    # cada atividade na fila de PCM"): a OS da Fila nascia sempre com 10 min. Com ele, a duração e o fim da janela da
    # programação saem dele, como no `create_planned_os` (14/09): é a janela que ocupa a agenda do técnico. Sem ele, o
    # pedido de sempre (10 min, a janela de 20), para nenhum outro caminho (COS, Chamados, PCM, Clonar) mudar.
    dur = int(duracao) if duracao else DURACAO_OS_AVULSA
    fim = prog + (timedelta(seconds=dur) if duracao else timedelta(minutes=20))
    final_iso = _iso_z(fdt) if fdt is not None else _iso_z(fim)
    params = {
        "event_date": _iso_z(ev),
        # CONFIRMADO em 07/08, e era mesmo o que eu suspeitava em 30/07 sem conseguir medir.
        # O COS reclamou que a hora do app não batia com a do Fracttal (OS 10794: evento 08:10,
        # início 08:00). Reproduzi na OS 10870 — escolhi evento 14:00 e o Fracttal gravou:
        #     initial_date = 13:50   (evento − 10 min, os mesmos milissegundos: é conta nossa)
        #     date_maintenance = 13:50   ← ELE IGNORA o que mandamos e copia o initial_date
        # Ou seja, toda OS deste caminho (Tradicional/COS/Chamados/PCM/Clonar) nascia começando e
        # programada 10 MINUTOS ANTES do evento que a pessoa escolheu. Os ±10 min nunca foram
        # pedidos por ninguém — eram folga arbitrária de quando eu não sabia que o initial_date
        # mandava. Agora os três são o PRÓPRIO evento: a pessoa escolhe uma hora e é essa que
        # aparece no Fracttal. Mesma regra já aplicada no `create_planned_os`.
        "cal_date_maintenance": _iso_z(prog),
        "date_maintenance": _iso_z(prog),
        "initial_date": _iso_z(prog),
        "final_date": final_iso,
        "type_user": "HUMAN_RESOURCES",
        "id_priorities": prio,
        "id_failure_severity": 0, "id_damage_type": 1,
        "failure_asset": False,
        "to_in_review": em_verificacao,
        "work_done": finalizada and not em_verificacao,  # Finalizados → concluída
        "to_work_order": finalizada,                     # finalizada vira WO direto (sem Fase 2)
        "stop_assets": False,
        "duration": dur, "real_duration": dur,           # o web manda os dois iguais (a captura: 600 e 600)
        "requested_by": (requested_by or "").strip() or "GridCo O&M",
        "edit_mode": False,
        "tasks_types_main_description": task_type,
        "subtasks": _rpc_subtasks(subtasks, fin.get("respostas")),
        "array_resources": [],                       # responsável: pendente de 1 captura p/ mapear
        "id_item": id_item,
        "items_description": asset.get("description") or "",
        # `id_request` amarra a OS à SOLICITAÇÃO que a originou. Ficou fixo em None desde sempre
        # porque nada no app criava OS a partir de solicitação — quem convertia era o PCM, à mão,
        # no Fracttal web. Com a fila do PCM isso passa a ter dono, e o vínculo faz a solicitação
        # virar "Resolvida com OS" sozinha, como já acontece hoje.
        "id_request": id_request or None, "note": (note or "").strip() or None,
        "name": (fin.get("name") or None) if finalizada else None, "available": None,
        "initial_date_out_of_service": None,
        "id_group_task": asset.get("id_group_task"),
        "assigment_date": _iso_z(ev),
        "id_work_order_task_related": None, "date_asset_out_of_service": None,
        "description": (description or "").strip(),
        "id_type_item": asset.get("id_type_item") or 1,
        "path_node": _path_node(asset),
        "msg_availability": "ASSET_OUT_OF_SERVICE",
        "id_task_type_main": main_id,
    }
    params["task_note"] = params["note"]                  # o web manda task_note = note
    params["id_parent"] = id_parent                       # OS pai (opcional) — vincula esta OS a outra
    if tipo.get("id_c1") is not None:                     # Classificação 1
        params["id_task_type"] = tipo["id_c1"]
        params["tasks_types_description"] = tipo.get("desc_c1") or ""
    if tipo.get("id_c2") is not None:                     # Classificação 2
        params["id_task_type_2"] = tipo["id_c2"]
        params["tasks_types_2_description"] = tipo.get("desc_c2") or ""
    if falha:                                             # "O ativo falhou?" (F4) — preenche o bloco de falha
        params["failure_asset"] = True
        params["related_failure"] = True
        if falha.get("id_type") is not None:
            params["id_failure_type"] = falha["id_type"]
            params["types_description"] = falha.get("type_desc") or ""
        if falha.get("id_cause") is not None:
            params["id_failure_cause"] = falha["id_cause"]
            params["causes_description"] = falha.get("cause_desc") or ""
        if falha.get("id_detection") is not None:
            params["id_failure_detection_method"] = falha["id_detection"]
            params["detection_method_description"] = falha.get("detection_desc") or ""
        params["id_failure_severity"] = str(falha.get("id_severity") or 0)   # Fracttal grava como string
        params["severiry_description"] = falha.get("severity_desc") or ""     # (sic — grafia do Fracttal)
        if falha.get("id_damage") is not None:
            params["id_damage_type"] = falha["id_damage"]
            params["damages_types_description"] = falha.get("damage_desc") or ""
        if falha.get("out_of_service"):                   # fora de serviço → "desde" = data do evento DA OS
            params["asset_out_of_service"] = True
            params["date_asset_out_of_service"] = _iso_z(ev)
    if finalizada and fin.get("id_assigned_user") is not None:
        params["id_assigned_user"] = fin["id_assigned_user"]   # responsável da WO concluída
    body = [{"id": str(uuid.uuid4()), "jsonrpc": "2.0", "method": RPC_METHOD, "params": params}]
    try:
        r = requests.post(RPC_PROXY_URL, headers=_rpc_headers(), json=body, timeout=45)
    except requests.RequestException as e:
        raise FracttalError(f"Erro de conexão com o RPC do Fracttal: {e}")
    if r.status_code in (401, 403):
        raise FracttalError("Login recusado (HTTP %d) — o JWT do Fracttal venceu/é inválido. "
                            "Cole um novo em fracttal_login.txt." % r.status_code)
    if r.status_code >= 400:
        raise FracttalError(f"RPC HTTP {r.status_code} — {(r.text or 'sem detalhes')[:240]}")
    try:
        j = r.json()
    except ValueError:
        raise FracttalError(f"RPC devolveu resposta não-JSON: {(r.text or '')[:200]}")
    rec = j[0] if isinstance(j, list) and j else j
    if isinstance(rec, dict) and rec.get("error"):
        err = rec["error"]
        msg = err.get("message") if isinstance(err, dict) else err
        raise FracttalError(f"RPC erro: {str(msg)[:240]}")
    # Resposta: {"success":bool,"message":"ACTION_DONE","data":{id_task,id_work_order,wo_folio,...}}
    result = rec.get("result") if isinstance(rec, dict) else None
    if isinstance(result, list) and result:
        result = result[0]
    if isinstance(result, dict) and result.get("success") is False:
        raise FracttalError(_msg_rpc(result.get("message")))
    data = result.get("data") if isinstance(result, dict) else {}
    data = data if isinstance(data, dict) else {}
    return {"id_task": data.get("id_task"),
            "id_work_order": data.get("id_work_order"),
            "wo_folio": data.get("wo_folio"),
            "duracao": dur,                   # o tempo da tarefa: a OS que junta as tarefas soma este
            "raw": result}


# As leituras de UMA OS que o card e a contagem de anexos fazem uma logo depois da outra (19/10/2026, superplano do
# OS Creator; Levi: "resolva!"): o card lê as tarefas e as subtarefas da OS, e a contagem de anexos, ~1 s depois, lia
# as mesmas de novo (2 pedidos a mais por card aberto). Ficam TTL_LEITURA_OS na memória, por OS; qualquer gravação
# (o que não é leitura) tira as da OS dela, ou todas quando não diz a OS.
TTL_LEITURA_OS = 20
_LEITURAS_OS: dict = {}
_LEITURAS_TRAVA = threading.Lock()


def _eh_leitura(method) -> bool:
    m = str(method or "").split(".", 1)[-1]
    return "_list" in m or "get" in m or "details" in m or m.startswith("load_")    # load_: companies.load_account_info


def _chave_os(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return v


def _esquecer_leituras(params=None) -> None:
    wid = params.get("id_work_order") if isinstance(params, dict) else None
    with _LEITURAS_TRAVA:
        if wid is None:
            _LEITURAS_OS.clear()
        else:
            for k in [k for k in _LEITURAS_OS if k[1] == _chave_os(wid)]:
                _LEITURAS_OS.pop(k, None)


def esquecer_os(wid=None) -> None:
    """Tira da memória as leituras desta OS (ou de todas): quem grava por fora do `_rpc_call` chama."""
    _esquecer_leituras({"id_work_order": wid} if wid is not None else None)


_LEITURAS_DONO = [None]


def _leitura_da_os(metodo, wid, params, usar_guardada: bool = True) -> list:
    """A lista (`data`) de uma leitura de UMA OS, entregue em cópia. O card (`usar_guardada=False`) lê sempre na hora e
    guarda; a contagem de anexos, que vem logo depois, usa a guardada por até TTL_LEITURA_OS. Erro sobe e não fica.
    Trocou o `_rpc_call` (os testes trocam por um Fracttal de mentira), a memória começa vazia."""
    k, agora = (metodo, _chave_os(wid)), time.time()
    with _LEITURAS_TRAVA:
        if _LEITURAS_DONO[0] is not _rpc_call:
            _LEITURAS_OS.clear()
            _LEITURAS_DONO[0] = _rpc_call
        v = _LEITURAS_OS.get(k)
    if not usar_guardada or v is None or agora - v[0] >= TTL_LEITURA_OS:
        r = _rpc_call(metodo, params)
        d = r.get("data") if isinstance(r, dict) else r
        v = (agora, d if isinstance(d, list) else [])
        with _LEITURAS_TRAVA:
            _LEITURAS_OS[k] = v
            if len(_LEITURAS_OS) > 200:
                for kk in sorted(_LEITURAS_OS, key=lambda x: _LEITURAS_OS[x][0])[:len(_LEITURAS_OS) - 200]:
                    _LEITURAS_OS.pop(kk, None)
    return [dict(x) if isinstance(x, dict) else x for x in v[1]]


def _rpc_call(method: str, params: dict, timeout: int = 45):
    """Chamada genérica ao rpc/proxy. Devolve o 'result' (ou levanta FracttalError). Gravação (o que não é leitura)
    tira da memória as leituras da OS dela (`_leitura_da_os`)."""
    if not _eh_leitura(method):
        try:
            return _rpc_chamar(method, params, timeout)
        finally:
            _esquecer_leituras(params)
    return _rpc_chamar(method, params, timeout)


def _rpc_chamar(method: str, params: dict, timeout: int = 45):
    body = [{"id": str(uuid.uuid4()), "jsonrpc": "2.0", "method": method, "params": params}]
    try:
        r = requests.post(RPC_PROXY_URL, headers=_rpc_headers(), json=body, timeout=timeout)
    except requests.RequestException as e:
        raise FracttalError(f"Erro de conexão (RPC {method}): {e}")
    if r.status_code in (401, 403):
        _clear_jwt()
        raise SessionExpired(f"Login recusado (HTTP {r.status_code}) — faça login de novo no app.")
    if r.status_code >= 400:
        raise FracttalError(f"RPC {method} HTTP {r.status_code} — {(r.text or '')[:200]}")
    try:
        j = r.json()
    except ValueError:
        raise FracttalError(f"RPC {method} resposta não-JSON: {(r.text or '')[:160]}")
    rec = j[0] if isinstance(j, list) and j else j
    if isinstance(rec, dict) and rec.get("error"):
        err = rec["error"]
        raise FracttalError(f"RPC {method} erro: {str(err.get('message') if isinstance(err, dict) else err)[:200]}")
    result = rec.get("result") if isinstance(rec, dict) else rec
    # sessão morta server-side (USER_NOT_LOGIN/INVALID_TOKEN…) → vem success:false (HTTP 200).
    # Limpa o token e pede login, em vez de devolver lista vazia silenciosa.
    if isinstance(result, dict) and result.get("success") is False:
        msg = str(result.get("message") or "")
        if any(k in msg.upper() for k in ("NOT_LOGIN", "INVALID_TOKEN", "SESSION",
                                          "TOKEN_EXPIRED", "UNAUTHORIZED", "NOT_AUTH")):
            _clear_jwt()
            raise SessionExpired("Sua sessão do Fracttal expirou ou foi encerrada. Faça login de novo.")
    return result


def _current_user_info():
    """(id_personnel, id_account, nome) do usuário logado — achados no pessoal pelo e-mail. Desde 31/10/2026 (etapa 4 do
    canto central) no catálogo de pessoas (`catalogos.da_pessoa`, pelo HMAC do e-mail): antes, a 1ª tela de cada pessoa em
    cada processo relia o pessoal do Fracttal para achá-la, e o "não achei" ficava até o reinício."""
    email = (current_user() or "").strip().lower()
    if not email:
        return (None, None, "")
    import catalogos
    return catalogos.da_pessoa(email)


def _current_user_ids():
    """(id_personnel, id_account). id_personnel = 'atribuídas a mim' (id_assigned_user);
    id_account = 'criadas por mim' (id_created_by)."""
    idp, idacc, _ = _current_user_info()
    return (idp, idacc)


def current_user_name():
    """Nome de exibição do usuário logado (do personnel), ou o e-mail se não achar."""
    return _current_user_info()[2] or current_user()


_CODE_LOC_TENTOU = [0.0]


def s3_get_url(name):
    """URL pré-assinada de DOWNLOAD de um objeto do S3 do Fracttal (companies.s3_object_get). O
    files_list só devolve o CAMINHO (value=.ot/...), então preciso disso p/ exibir a imagem. Resposta de
    shape variável → procuro qualquer URL http na resposta. None se falhar."""
    if not name:
        return None
    body = [{"id": str(uuid.uuid4()), "jsonrpc": "2.0", "method": "companies.s3_object_get",
             "params": {"name": name}}]
    try:
        r = requests.post(RPC_PROXY_URL, headers=_rpc_headers(), json=body, timeout=30)
        j = r.json()
    except Exception:
        return None

    def _find(o):
        if isinstance(o, str):
            return o if o.startswith("http") else None
        if isinstance(o, dict):
            for v in o.values():
                u = _find(v)
                if u:
                    return u
        if isinstance(o, list):
            for v in o:
                u = _find(v)
                if u:
                    return u
        return None
    return _find(j)


def baixar_imagem(url) -> bytes:
    """Bytes de uma imagem por URL pré-assinada (S3 — sem cabeçalhos de auth)."""
    if not url:
        raise FracttalError("Imagem sem URL para download.")
    try:
        r = requests.get(url, timeout=30)
    except requests.RequestException as e:
        raise FracttalError(f"Erro ao baixar a imagem: {e}")
    if r.status_code >= 400:
        raise FracttalError(f"Falha ao baixar a imagem (HTTP {r.status_code}).")
    return r.content


def _react_insert_post(body: list) -> dict:
    """POST do tasks_noscheduled_react_insert + parse da resposta (id_work_order/wo_folio/id_task)."""
    try:
        r = requests.post(RPC_PROXY_URL, headers=_rpc_headers(), json=body, timeout=45)
    except requests.RequestException as e:
        raise FracttalError(f"Erro de conexão com o RPC do Fracttal: {e}")
    if r.status_code in (401, 403):
        raise SessionExpired("Login recusado — sua sessão do Fracttal venceu. Relogue.")
    if r.status_code >= 400:
        raise FracttalError(f"RPC HTTP {r.status_code} — {(r.text or 'sem detalhes')[:240]}")
    try:
        j = r.json()
    except ValueError:
        raise FracttalError(f"RPC devolveu resposta não-JSON: {(r.text or '')[:200]}")
    rec = j[0] if isinstance(j, list) and j else j
    if isinstance(rec, dict) and rec.get("error"):
        err = rec["error"]
        raise FracttalError(f"RPC erro: {str(err.get('message') if isinstance(err, dict) else err)[:240]}")
    result = rec.get("result") if isinstance(rec, dict) else None
    if isinstance(result, list) and result:
        result = result[0]
    if isinstance(result, dict) and result.get("success") is False:
        raise FracttalError(_msg_rpc(result.get("message")))
    data = result.get("data") if isinstance(result, dict) else {}
    data = data if isinstance(data, dict) else {}
    return {"id_task": data.get("id_task"), "id_work_order": data.get("id_work_order"),
            "wo_folio": data.get("wo_folio"),
            "id_work_order_task": data.get("id_work_order_task") or data.get("id_task"),  # p/ anexar imagem
            "raw": result}


def _find_http_url(o):
    """Primeira URL http encontrada (recursivo) numa resposta de shape variável."""
    if isinstance(o, str):
        return o if o.startswith("http") else None
    if isinstance(o, dict):
        for v in o.values():
            u = _find_http_url(v)
            if u:
                return u
    if isinstance(o, list):
        for v in o:
            u = _find_http_url(v)
            if u:
                return u
    return None


def _find_dict_by_keys(o, nomes):
    """Primeiro dict aninhado sob uma chave em `nomes` (ex.: 'fields'/'form' de um presigned POST)."""
    if isinstance(o, dict):
        for k, v in o.items():
            if str(k).lower() in nomes and isinstance(v, dict):
                return v
        for v in o.values():
            d = _find_dict_by_keys(v, nomes)
            if d:
                return d
    if isinstance(o, list):
        for v in o:
            d = _find_dict_by_keys(v, nomes)
            if d:
                return d
    return None


def _s3_object_post(nome_s3: str, size: int, checksum_hex: str):
    """Pede o upload pré-assinado (companies.s3_object_post). Devolve a resposta JSON CRUA (dict/list)
    pra procurar a URL/fields de forma robusta (o shape varia)."""
    body = [{"id": str(uuid.uuid4()), "jsonrpc": "2.0", "method": "companies.s3_object_post",
             "params": {"name": nome_s3, "size": size, "action": "edit",
                        "checksum": {"hash_algorithm": "SHA256", "hex": checksum_hex}}}]
    r = requests.post(RPC_PROXY_URL, headers=_rpc_headers(), json=body, timeout=45)
    if r.status_code in (401, 403):
        raise SessionExpired("Sessão do Fracttal venceu. Relogue.")
    if r.status_code >= 400:
        raise FracttalError(f"s3_object_post HTTP {r.status_code}: {(r.text or '')[:300]}")
    try:
        return r.json()
    except ValueError:
        raise FracttalError(f"s3_object_post resposta não-JSON: {(r.text or '')[:300]}")


def _s3_post_data(resp) -> dict:
    """Extrai o result.data do s3_object_post (onde vêm bucket/host/key/credential/signature/policy…)."""
    rec = resp[0] if isinstance(resp, list) and resp else resp
    result = rec.get("result") if isinstance(rec, dict) else rec
    data = result.get("data") if isinstance(result, dict) else result
    return data if isinstance(data, dict) else {}


def _s3_upload(data: dict, data_bytes: bytes, filename: str, ct: str):
    """Faz o upload no S3 conforme a forma que a Fracttal devolveu. Confirmado ao vivo: PRESIGNED POST da
    AWS (bucket/host/key/credential/signature/policy/date…) → monta o form AWS4 POST (file por último).
    Fallback: URL direta (PUT) ou url+fields."""
    keys = list(data.keys())
    if data.get("bucket") and data.get("host"):           # presigned POST da AWS (caso da Fracttal)
        bucket, host = data["bucket"], data["host"]
        url = f"https://{bucket}.{host}/" if "." not in bucket else f"https://{host}/{bucket}/"

        def g(*ks):
            return next((data[k] for k in ks if data.get(k)), None)
        form = {
            "key": data.get("key"),
            "X-Amz-Algorithm": g("algorithm", "x_amz_algorithm", "x-amz-algorithm") or "AWS4-HMAC-SHA256",
            "X-Amz-Credential": g("credential", "x_amz_credential", "x-amz-credential"),
            "X-Amz-Date": g("date", "x_amz_date", "x-amz-date", "amz_date"),
            "Policy": g("policy", "Policy"),
            "X-Amz-Signature": g("signature", "x_amz_signature", "x-amz-signature"),
        }
        for src, dst in (("acl", "acl"), ("content_type", "Content-Type"),
                         ("security_token", "X-Amz-Security-Token"),
                         ("x_amz_security_token", "X-Amz-Security-Token"),
                         ("encryption", "x-amz-server-side-encryption")):
            if data.get(src):
                form[dst] = data[src]
        form["success_action_status"] = str(data.get("success_action_status") or "200")   # condição da policy
        import hashlib as _hl
        import base64 as _b64
        # a policy exige x-amz-checksum-sha256 (base64 do SHA256 dos bytes — o S3 confere o conteúdo)
        form["x-amz-checksum-sha256"] = _b64.b64encode(_hl.sha256(data_bytes).digest()).decode()
        falta = [k for k in ("key", "X-Amz-Credential", "X-Amz-Date", "Policy", "X-Amz-Signature")
                 if not form.get(k)]
        if falta:
            raise FracttalError(f"presigned POST incompleto (falta {falta}). CHAVES do data: {keys}")
        form = {k: v for k, v in form.items() if v is not None}
        return requests.post(url, data=form, files={"file": (filename, data_bytes, ct)}, timeout=180)
    # fallback: url direta (PUT) ou url + fields
    url = _find_http_url(data)
    fields = _find_dict_by_keys(data, ("fields", "form", "formdata", "inputs"))
    if not url:
        raise FracttalError(f"s3_object_post sem forma de upload conhecida. CHAVES do data: {keys}")
    if isinstance(fields, dict):
        return requests.post(url, data=fields, files={"file": (filename, data_bytes, ct)}, timeout=180)
    return requests.put(url, data=data_bytes, headers={"Content-Type": ct}, timeout=180)


def attach_imagem_os(id_work_order, id_work_order_task, data_bytes: bytes, filename: str) -> dict:
    """Sobe 1 imagem no S3 do Fracttal e registra na tarefa da OS. Fluxo: s3_object_post (devolve um
    presigned POST da AWS) → POST no S3 → work_orders_tasks_files_insert."""
    import hashlib
    import mimetypes
    if not (id_work_order and id_work_order_task):
        raise FracttalError("OS criada sem id_work_order/_task — não dá p/ anexar.")
    nome_s3 = f".ot/{id_work_order}/{filename}"
    resp = _s3_object_post(nome_s3, len(data_bytes), hashlib.sha256(data_bytes).hexdigest())
    data = _s3_post_data(resp)
    ct = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    try:
        up = _s3_upload(data, data_bytes, filename, ct)
    except requests.RequestException as e:
        raise FracttalError(f"upload S3 falhou ({e}).")
    if up.status_code >= 400:
        raise FracttalError(f"upload S3 HTTP {up.status_code}: {(up.text or '')[:300]}")
    reg = [{"id": str(uuid.uuid4()), "jsonrpc": "2.0", "method": "tasks.work_orders_tasks_files_insert",
            "params": [{"id": str(uuid.uuid4()), "id_personnel": None, "id_third_party": None, "id_task": None,
                        "id_attached": id_work_order_task, "id_item": None, "id_work_order_task": id_work_order_task,
                        "id_work_orders_tasks_files": None, "id_work_orders_tasks_form_items": None, "id_request": None,
                        "link_attachment": False, "value": nome_s3, "description": "", "type": 1, "typeRender": "",
                        "link": "", "can_edit": True}]}]
    esquecer_os(id_work_order)                    # o anexo novo muda o que a contagem do card leria
    r2 = requests.post(RPC_PROXY_URL, headers=_rpc_headers(), json=reg, timeout=45)
    if r2.status_code >= 400:
        raise FracttalError(f"files_insert HTTP {r2.status_code}: {(r2.text or '')[:200]}")
    return {"ok": True, "value": nome_s3}


# O nº da OS → id pela lista central de OS (31/10/2026, tarefa 3.3 do canto central): o id de um nº não muda, e a lista sabe os
# das OS que ela tem, sem pedido nenhum (eram 1 a 5 pedidos a cada nº, no card, no PDF, no Clonar, no COS, no Garantias). Quem
# liga o gancho é o `os_web.lista_central` (o atalho só vale para quem conferiu que vê no Fracttal o mesmo que a lista: a pessoa
# de visão restrita segue lendo pela sessão dela). Sem o gancho, ou sem o nº na lista, a leitura de sempre.
ID_PELA_LISTA = None


# ══ Dashboard O&M — fila de OS sugeridas (trackers parados >36h / recorrentes) ══════════════════
# O dashboard (Flask) calcula a fila em /api/trackers/os-sugeridas (atrás de login DASH_PASSWORD).
# Aqui só LEMOS — o técnico/PCM confirma e cria a OS pelo wizard. Config em %APPDATA%.
DASH_CONFIG_FILE = os.path.join(_data_dir(), "dash_config.json")


# ── A FACHADA (31/10/2026, etapa 5.3 do canto central) ─────────────────────────────────────────────────
# O que saiu deste arquivo para o módulo do assunto segue acessível como `api.X`: a ponte, as rotas e os testes
# chamam e TROCAM `api.X` pelo nome, e o código que mudou de lugar chama tudo o que não é dele pelo `api.`, para
# enxergar a troca. No FIM do arquivo porque cada módulo termina com `import api`.
from os_tempo import (  # noqa: E402,F401
    _BR_TZ, _iso_z, _parse_iso, _segundos, _tempo_da_os, duracao_os, duracao_solar, fmt_data_br, horas_solares)
from os_anexos import (  # noqa: E402,F401
    RPC_REQ_FILES, RPC_WO_FILES, RPC_WO_FORMIT_ATTACH, RPC_WO_IMAGES, RPC_WO_RESOURCES, TIPO_RECURSO,
    _ids_tarefas_da_os, _img_thumb, _img_url, _is_img_b64, get_os_anexos, get_os_imagens, get_os_recursos,
    get_os_subtarefa_anexos, get_solic_anexos)
from os_execucao import (  # noqa: E402,F401
    ACAO_PAUSADA, ACAO_RODANDO, EXEC_ENCERRADA, LABEL_EM_EXECUCAO, RPC_EXEC_FINISH, RPC_EXEC_GET, RPC_EXEC_INSERT,
    RPC_EXEC_LIST, RPC_EXEC_PAUSE, RPC_EXEC_RESUME, RPC_EXEC_TYPES, RPC_WO_EXEC_GET, RPC_WO_EXEC_INSERT,
    RPC_WO_EXEC_LIST, RPC_WO_FORMIT_VALUES, RPC_WO_SEC_VALIDATE, RPC_WO_TASKS_NEW, SIMNAO_OPCOES, TIPO_CAMPO,
    VERIF_OPCOES, _CHECKLIST_SEM_PERMISSAO, _PAUSA_CACHE, _dono_execucao, execucao_atual, execucoes_abertas,
    execucoes_da_tarefa, fechar_execucoes_abertas, finalizar_execucao, finalizar_execucao_os, historico_execucao,
    id_tarefa_da_os, iniciar_execucao, iniciar_execucao_os, marcar_em_execucao, motivos_pausa, pausar_execucao,
    registrar_execucao, retomar_execucao, salvar_subtarefas, subtarefas_da_tarefa, tempo_trabalhado,
    tempo_trabalhado_em_massa, validar_seguranca_tarefa)
from os_planos import (  # noqa: E402,F401
    RPC_TASK_DETAILS, RPC_TASK_EVENTS, RPC_TASK_TEMPLATE_ITEMS, SUBTAREFAS_EXTRA, TIPO_TAREFA_DO_PLANO,
    _DURACAO_PLANO, _MARCA_EXTRA, _PERF_PLANOS, _TIPO_ITEM_DESC, _duracao_do_modelo, _find_subtasks, _norm_txt,
    _plan_family, _subtarefas_de_modelo, atualizar_modelos_subtarefas, com_subtarefas_extra, com_tipo_da_tarefa,
    duracao_do_plano, get_plan_details, get_plans_for_assets, get_subtask_counts, get_subtask_names, get_task_plans,
    get_template_subtarefas, ler_planos_do_ativo, sem_subtarefas_extra, tem_subtarefas_extra)
from perf_alvos import (  # noqa: E402,F401
    CARTEIRA_EQUIP, PERF_TIPOS, PERF_TIPOS_TRACKER_CONJUNTO, _CONECTIVOS, _asset_short_name,
    _eh_tracker_generalizado, _usina_short, get_performance_alvos, perf_os_nome, plano_base_nome)
from os_chamados import (  # noqa: E402,F401
    LABEL_CHAMADOS, LABEL_INSPECAO, TIPO_INSPECAO, _CHAMADO_CAMPOS, _CHAMADO_FIM, _CHAMADO_MK, _CHAMADO_SUB,
    _chave_sub, bloco_chamado, codigos_os_recentes, get_chamado_de_os, list_chamados, list_performance,
    os_dos_ativos, parse_bloco_chamado, perf_spec_nome_etiqueta, respostas_inspecao, status_chamado_em_massa,
    tickets_os3_em_massa, total_chamados, ultimas_os_do_ativo)
from os_estado import (  # noqa: E402,F401
    RPC_WO_CANCEL, RPC_WO_CHANGE_STATUS, RPC_WO_DETAILS, RPC_WO_LIST, RPC_WO_RECALCULATE, RPC_WO_STATUS_CUSTOM,
    RPC_WO_UPDATE, STATUS_FECHADOS, WO_STATUS, _ERRO_WO_FECHADA, _filhos_da_os, _ordem_os, _os_por_folio_leve,
    _wo_id_por_folio, _wo_resumo, cancel_os, cancelamento_da_os, checar_data_fim, concluir_os, concluir_os_checado,
    editar_nota_os, fluxo_da_os, get_cancel_motivos, mudar_responsavel, mudar_status_os, os_por_folio, status_da_os)
from os_detalhe import (  # noqa: E402,F401
    RPC_WO_PARENTS, _ATRIB_NOME_KEYS, _FORM_RESP_KEYS, _VERIF_MAP, _cabecalho_os, _folio_da_os_pai,
    _form_item_resposta, _ids_atribuido, _juntos, _nome_atribuido, _personnel_nome_por_id, _solicitacao_da_os,
    buscar_os_pai, get_os_detalhes, get_os_detalhes_por_folio, get_os_para_clonar)
from os_historico import (  # noqa: E402,F401
    HISTORICO_CAP, RPC_WO_FORMIT, RPC_WO_TASKS, TIPOS_COS, _MetaLida, _Passos, _code_to_loc, _extrai_code,
    _extrai_codigos, _lista_pela_metade, _meta_tarefa_por_os, _primeiro, _shape_wo_row, contar_minhas_analises,
    decodifica_gatilho, get_pessoas_contas, list_minhas_os, list_minhas_os_pagina, listar_periodo_completo,
    meta_tarefas_por_os)
from os_solicitacoes import (  # noqa: E402,F401
    REQ_STATUS, RPC_REQ_INSERT, RPC_REQ_LIST, RPC_REQ_STATUS_INSERT, RPC_REQ_STATUS_LIST, RPC_REQ_TYPES,
    RPC_REQ_TYPES_1, RPC_REQ_TYPES_2, RPC_REQ_UPDATE, STATUS_SOLICITACAO, _cor_de, _req_row_to_d, _req_status_label,
    _req_type_list, _solicitacao_row, _tarefa_da_solicitacao, aprovar_solicitacao, cancelar_solicitacao,
    create_solicitacao, create_solicitacoes_bulk, editar_observacao_solicitacao, get_request_types,
    get_solicitacao_por_os, list_minhas_solicitacoes, mudar_status_solicitacao, status_solicitacao_catalogo)
from os_criar import (  # noqa: E402,F401
    ANALISE_CLASSIF_1, ANALISE_CLASSIF_2, RPC_KANBAN, RPC_LABELS_SYNC, RPC_WO_INSERT, TIPO_ANALISE,
    _WO_TASK_DEFAULTS, _anexa_imagens_bulk, _kanban_records, _work_order_insert, apply_labels, clonar_os,
    concluir_os_analise, create_inspecao_chamado, create_os_analise, create_os_chamado, create_os_sem_plano,
    create_performance_os, create_performance_os_agrupada, create_planned_os, create_planned_os_multi,
    create_planned_os_one_wo, create_work_orders_agrupada, create_work_orders_bulk, create_work_orders_datas,
    nascer_ticket)
from dash_os import (  # noqa: E402,F401
    _dash_url, fetch_os_sugeridas, load_dash_config, save_dash_config)
from ativos_carga import (  # noqa: E402,F401
    ASSETS_ESPERA_TENTATIVA, ASSETS_TTL, ASSETS_TTL_LEITOR, ESPERA_NOVOS_S, RPC_ITEMS, _ASSETS_RECARGA,
    _ASSETS_RENOVA, _ASSETS_RENOVA_TRAVA, _POR_TRAS, _asset_by_code, _baixar_pelo_rpc, _items_page_rpc,
    _items_params, _quando, _read_asset_cache, _renovar_catalogo_por_tras, assets_cache_info, ativos_de,
    ativos_de_titulo, aviso_da_falha, aviso_da_recusa, catalogo_vencido, esperar_os_novos, get_assets,
    load_assets_cached, texto_dos_novos)
from catalogos_rpc import (  # noqa: E402,F401
    FALHA_DANOS, FALHA_SEVERIDADES, RPC_FALHA_CAUSAS, RPC_FALHA_DETEC, RPC_FALHA_TIPOS, RPC_LABELS_LIST,
    _classif_ids, _label_id, _label_performance_id, _lista_tipos, get_classif1, get_classif2, get_falha_listas,
    get_labels, get_responsaveis, get_task_types, get_tipos_classif, label_id_por_nome, ler_pessoal,
    responsaveis_ao_vivo, tipo_main_ao_vivo)
