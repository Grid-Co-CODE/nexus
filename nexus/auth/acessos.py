"""Acessos do Nexus: os administradores dados pela tela (Base → Acessos) e o registro mínimo de quem entrou.

Pedido de 11/10/2026, do responsável pelo Nexus, na véspera de o Nexus virar a porta principal: "Tem algum canto do
Nexus onde eu posso administrar isso?" (quem é administrador). Até então a lista era só a NEXUS_ADMINS do `.env` do
servidor: pôr ou tirar alguém pedia a T.I. editando o arquivo e reiniciando o serviço. Agora:
- os do servidor (NEXUS_ADMINS) continuam, só leitura, e nunca saem pela tela: são a garantia de que sempre há um
  administrador, mesmo com este arquivo apagado ou corrompido;
- os da tela moram em `acessos.json`, na pasta de dados do Nexus (a mesma do cadastro e do de-para: `NEXUS_DADOS`),
  com quem deu e quando, e um registro (auditoria) de cada mudança;
- `acessos_logins.json`, ao lado, guarda só o e-mail e a hora do último login de cada pessoa, dos últimos 30 dias e com
  teto de tamanho: é para ver quem já usa o Nexus.

NÃO vai ao banco, de propósito: é configuração de acesso deste Nexus (quem administra esta instalação), não dado de
negócio a cruzar com os setores; no banco compartilhado ela seria lida por outros sistemas e dependeria de ele estar
no ar para alguém conseguir administrar. Fica fora do git (a pasta de dados é gitignorada): o repositório é público.

Escrita atômica (arquivo temporário na mesma pasta + `os.replace`) e uma trava para as 8 threads do waitress: duas
pessoas dando acesso ao mesmo tempo não perdem uma a mudança da outra, e um arquivo nunca fica pela metade. Arquivo
que existe e não abre (editado à mão, disco) FECHA: só valem os do servidor, e a tela se recusa a gravar por cima
(gravar apagaria o que estava nele).
"""
import contextlib
import copy
import json
import logging
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

ARQUIVO = "acessos.json"
ARQUIVO_LOGINS = "acessos_logins.json"
# quem entrou pela senha de administrador não tem e-mail: aparece assim no registro de logins e na auditoria
SENHA_DE_ADMIN = "senha de administrador"
JANELA_LOGINS = timedelta(days=30)
# tetos: o registro de logins é escrito a cada entrada (e o e-mail é o que o Fracttal confirmou, não texto livre, mas
# o arquivo não pode crescer sem fim); a auditoria guarda as últimas mudanças, que são poucas por mês
MAX_LOGINS = 500
MAX_AUDITORIA = 1000
# e-mail como o Fracttal o trata: minúsculas, sem espaço; a régua é a prática (nome@dominio.tld), não a RFC inteira
_EMAIL = re.compile(r"[a-z0-9_%+'-]+(?:\.[a-z0-9_%+'-]+)*@[a-z0-9-]+(?:\.[a-z0-9-]+)+")
_MAX_EMAIL = 254
# RLock: a leitura (com cache) roda dentro da escrita, que segura a trava do ler-mudar-gravar inteiro
_TRAVA = threading.RLock()
# {caminho: ((mtime_ns, tamanho), dado)}: o portão consulta a lista a cada pedido; um stat por pedido, e o arquivo só é
# relido quando muda
_CACHE: dict[str, tuple] = {}
# {chave: último aviso registrado}: o erro que persiste vai ao journal uma vez, não a cada pedido (`_avisar_uma_vez`)
_AVISADO: dict[str, str] = {}
_BRT = timezone(timedelta(hours=-3))


class Recusado(ValueError):
    """O pedido da tela não vale (e-mail inválido, um do servidor, o último da tela): o texto vai para a tela."""


class Ilegivel(RuntimeError):
    """O arquivo existe e não abriu. Para a lista de administradores, isto fecha (só os do servidor valem)."""


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _de_iso(texto) -> datetime | None:
    try:
        return datetime.strptime(str(texto), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def hora_br(iso) -> str:
    """'2026-10-11T03:10:00Z' -> '11/10/2026 00:10' (horário de Brasília)."""
    d = _de_iso(iso)
    return d.astimezone(_BRT).strftime("%d/%m/%Y %H:%M") if d else ""


def pasta(config) -> Path | None:
    """A pasta de dados do Nexus (`NEXUS_DADOS`; sem ela, a padrão do cadastro). Em teste sem `NEXUS_DADOS`, None: nada
    é lido nem gravado na pasta de verdade (em 04/10/2026 um teste gravou no arquivo de regras real do de-para)."""
    if config.get("TESTING") and not config.get("NEXUS_DADOS"):
        return None
    from ..cadastro.ligacoes import pasta_dados
    return pasta_dados(config)


def email_normal(texto) -> str:
    """O e-mail validado: sem espaço nas pontas, minúsculas, nenhum espaço no meio, no formato nome@dominio.tld."""
    bruto = str(texto or "").strip().lower()
    if not bruto:
        raise Recusado("Informe o e-mail.")
    if len(bruto) > _MAX_EMAIL or any(c.isspace() for c in bruto) or not _EMAIL.fullmatch(bruto):
        raise Recusado("E-mail inválido: use o e-mail do login do Fracttal (nome@empresa.com.br), sem espaço.")
    return bruto


# ── leitura e escrita ────────────────────────────────────────────────────────────────────────────────────────────


def _forma_acessos(dado) -> dict:
    if not isinstance(dado, dict) or not isinstance(dado.get("admins", []), list) \
            or not isinstance(dado.get("auditoria", []), list):
        raise ValueError("forma inesperada")
    admins = []
    for a in dado.get("admins", []):
        if not isinstance(a, dict) or not isinstance(a.get("email"), str):
            raise ValueError("administrador sem e-mail")
        admins.append({"email": a["email"].strip().lower(), "por": str(a.get("por") or ""),
                       "quando": str(a.get("quando") or "")})
    auditoria = [x for x in dado.get("auditoria", []) if isinstance(x, dict)]
    return {"versao": 1, "admins": admins, "auditoria": auditoria}


def _forma_logins(dado) -> dict:
    if not isinstance(dado, dict) or not isinstance(dado.get("logins", {}), dict):
        raise ValueError("forma inesperada")
    return {"versao": 1, "logins": {str(k): v for k, v in dado.get("logins", {}).items() if isinstance(v, str)}}


def _avisar_uma_vez(chave: str, nivel: int, texto: str, exc_info: bool = False) -> None:
    """Registra no journal só quando o aviso MUDA: o portão lê a lista a cada pedido, e um erro que persiste (a pasta
    sem permissão) encheria o journal com uma linha por clique. `_esquecer_aviso` rearma quando volta a funcionar."""
    if _AVISADO.get(chave) != texto:
        _AVISADO[chave] = texto
        log.log(nivel, "%s", texto, exc_info=exc_info)


def _esquecer_aviso(chave: str) -> None:
    _AVISADO.pop(chave, None)


def _nao_abriu(p: Path, e: OSError) -> Ilegivel:
    """O arquivo não abriu agora, por falha de disco ou de permissão e não de conteúdo: não vai ao cache (o próximo pedido
    tenta de novo) e vai ao journal uma vez."""
    erro = Ilegivel(f"o arquivo {p.name} não abriu agora ({type(e).__name__})")
    _CACHE.pop(str(p), None)
    _avisar_uma_vez(str(p), logging.WARNING, f"Acessos: {erro} ({e}); só os administradores do servidor "
                                             "(NEXUS_ADMINS) valem enquanto isso.")
    return erro


def _ler(p: Path, forma) -> dict | None:
    """O arquivo já na forma certa (cópia do cache: quem recebe pode mexer), ou None se ele não existe.
    Ilegivel se existe e não abre, e NADA além disso sobe daqui: o portão chama isto a cada pedido de toda sessão do
    Fracttal, e um erro que escapasse viraria 500 no Nexus inteiro (revisão de 11/10/2026: a pasta de dados sem
    permissão de busca dava PermissionError no stat, que não é FileNotFoundError, e derrubava até o Início).
    Corrompido fica no cache até o arquivo mudar (o portão lê a cada pedido: nada de reler e registrar o erro a cada
    clique); falha de disco ou de permissão (o Windows recusa a abertura no meio de uma troca por outro processo; a
    pasta sem permissão; a NEXUS_DADOS apontando para um arquivo, NotADirectoryError no Linux) não fica: o próximo
    pedido tenta de novo."""
    with _TRAVA:
        try:
            st = p.stat()
        except FileNotFoundError:
            _CACHE.pop(str(p), None)
            _esquecer_aviso(str(p))
            return None
        except OSError as e:
            raise _nao_abriu(p, e) from None
        chave = (st.st_mtime_ns, st.st_size)
        guardado = _CACHE.get(str(p))
        if guardado and guardado[0] == chave:
            if isinstance(guardado[1], Ilegivel):
                raise guardado[1]
            return copy.deepcopy(guardado[1])
        try:
            bruto = p.read_bytes()
        except OSError as e:
            raise _nao_abriu(p, e) from None
        _esquecer_aviso(str(p))
        try:
            # o decode fica aqui dentro: bytes que não são UTF-8 (disco, ou o arquivo salvo à mão em outra codificação)
            # dão UnicodeDecodeError, que é ValueError e NÃO OSError (com o read_text, escapava pelos dois except); e o
            # json do Python estoura a recursão num arquivo aninhado a fundo (RecursionError, que não é ValueError)
            dado = forma(json.loads(bruto.decode("utf-8")))
        except (ValueError, RecursionError) as e:     # JSONDecodeError e UnicodeDecodeError são ValueError
            erro = Ilegivel(f"o arquivo {p.name} está corrompido ({type(e).__name__})")
            _CACHE[str(p)] = (chave, erro)
            log.error("Acessos: %s; só os administradores do servidor (NEXUS_ADMINS) valem até ele ser corrigido.", erro)
            raise erro from None
        _CACHE[str(p)] = (chave, dado)
        return copy.deepcopy(dado)


def _trocar(tmp: str, p: Path) -> None:
    """`os.replace` com folga para o Windows, que recusa a troca enquanto outro processo (antivírus, cópia de segurança)
    está com o arquivo aberto; dentro do Nexus, a trava já impede que uma leitura nossa esteja no meio."""
    for tentativa in range(5):
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            if tentativa == 4:
                raise
            time.sleep(0.05)


def _gravar_atomico(p: Path, dado: dict) -> None:
    """Grava inteiro ou nada: escreve num temporário da MESMA pasta (o replace só é atômico dentro do mesmo disco),
    força ao disco e troca. Falhou no meio: o temporário sai e o arquivo de antes fica como estava."""
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dado, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        _trocar(tmp, p)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    try:
        st = p.stat()
    except OSError:
        # já gravou: um erro aqui faria a tela dizer "nada mudou" com a mudança no disco; sem a data do arquivo, o cache
        # sai e a próxima leitura vai ao disco
        _CACHE.pop(str(p), None)
        return
    _CACHE[str(p)] = ((st.st_mtime_ns, st.st_size), copy.deepcopy(dado))


def _vazio() -> dict:
    return {"versao": 1, "admins": [], "auditoria": []}


def estado(config) -> dict:
    """O que a tela mostra: {"sem_pasta", "erro", "admins" (com quem deu e quando), "auditoria" (a mais nova primeiro)}."""
    p = pasta(config)
    if p is None:
        return {"sem_pasta": True, "erro": None, "admins": [], "auditoria": []}
    try:
        dado = _ler(p / ARQUIVO, _forma_acessos) or _vazio()
    except Ilegivel as e:
        return {"sem_pasta": False, "erro": str(e), "admins": [], "auditoria": []}
    return {"sem_pasta": False, "erro": None, "admins": dado["admins"], "auditoria": list(reversed(dado["auditoria"]))}


def admins_da_tela(config) -> set[str]:
    """Os e-mails que a tela fez administradores. Nunca levanta: arquivo que não abre = nenhum (fecha).

    É chamada pelo portão a cada pedido de toda sessão do Fracttal (`_admin_em_dia`) e no login: um erro que subisse
    daqui derrubaria o Nexus inteiro, e não só a tela Acessos. O `_ler` já só levanta Ilegivel; o `except Exception` é a
    garantia para o que ninguém previu, e fecha do mesmo jeito (só os do servidor valem), registrando no journal."""
    try:
        p = pasta(config)
        if p is None:
            return set()
        dado = _ler(p / ARQUIVO, _forma_acessos)
        admins = {a["email"] for a in (dado or _vazio())["admins"]}
    except Ilegivel:
        return set()
    except Exception as e:      # noqa: BLE001 — a lista da tela nunca derruba o portão
        _avisar_uma_vez("admins_da_tela", logging.ERROR,
                        f"Acessos: erro inesperado ao ler a lista da tela ({type(e).__name__}: {e}); só os "
                        "administradores do servidor (NEXUS_ADMINS) valem.", exc_info=True)
        return set()
    _esquecer_aviso("admins_da_tela")
    return admins


def _mudar(config, mudanca):
    """Ler, mudar e gravar o acessos.json com a trava segura do começo ao fim. `mudanca(dado)` mexe no dado e devolve
    o resultado; um Recusado dentro dela sai antes de gravar."""
    p = pasta(config)
    if p is None:
        raise Recusado("Este Nexus está sem pasta de dados (NEXUS_DADOS): nada foi gravado.")
    alvo = p / ARQUIVO
    with _TRAVA:
        dado = _ler(alvo, _forma_acessos) or _vazio()     # Ilegivel sobe: nada é gravado por cima do que não abriu
        resultado = mudanca(dado)
        dado["auditoria"] = dado["auditoria"][-MAX_AUDITORIA:]
        _gravar_atomico(alvo, dado)
        return resultado


def adicionar(config, email, quem: str, servidor: set[str]) -> str:
    """Dá administrador a `email` pela tela; devolve o e-mail normalizado."""
    e = email_normal(email)
    if e in servidor:
        raise Recusado(f"{e} já é administrador do servidor (NEXUS_ADMINS): não precisa da tela.")

    def mudanca(dado):
        if any(a["email"] == e for a in dado["admins"]):
            raise Recusado(f"{e} já é administrador pela tela.")
        quando = _iso(_agora())
        dado["admins"].append({"email": e, "por": quem, "quando": quando})
        dado["auditoria"].append({"quando": quando, "quem": quem, "acao": "adicionou", "email": e})
        return e

    return _mudar(config, mudanca)


def remover(config, email, quem: str, servidor: set[str], eu: str | None = None, confirmo: bool = False) -> str:
    """Tira o administrador que a tela deu. Os do servidor não saem por aqui (são a garantia de que sempre há um). Quem
    tira a si mesmo precisa confirmar, e não pode se for o último da tela: um clique errado deixaria a tela sem ninguém
    para desfazer (só a T.I., pelo .env, ou a senha de administrador)."""
    e = email_normal(email)
    if e in servidor:
        raise Recusado(f"{e} é administrador do servidor (NEXUS_ADMINS): só sai pelo .env do servidor, com a T.I.")

    def mudanca(dado):
        if not any(a["email"] == e for a in dado["admins"]):
            raise Recusado(f"{e} não está na lista de administradores da tela.")
        if eu and e == eu:
            if len(dado["admins"]) == 1:
                raise Recusado("Você é o último administrador dado pela tela e não pode tirar o seu próprio acesso. "
                               "Peça a outro administrador.")
            if not confirmo:
                raise Recusado("Para tirar o seu próprio acesso de administrador, marque a confirmação ao lado do botão.")
        dado["admins"] = [a for a in dado["admins"] if a["email"] != e]
        dado["auditoria"].append({"quando": _iso(_agora()), "quem": quem, "acao": "removeu", "email": e})
        return e

    return _mudar(config, mudanca)


# ── quem entrou ──────────────────────────────────────────────────────────────────────────────────────────────────


def registrar_login(config, email: str) -> None:
    """No login certo: guarda o e-mail (ou "senha de administrador") e a hora. Só os últimos 30 dias e no máximo
    MAX_LOGINS pessoas (as mais recentes). Nunca impede a entrada: falhou, fica no journal e a pessoa entra."""
    try:
        p = pasta(config)
        e = str(email or "").strip().lower()[:_MAX_EMAIL]
        if p is None or not e:
            return
        alvo = p / ARQUIVO_LOGINS
        with _TRAVA:
            try:
                logins = (_ler(alvo, _forma_logins) or {"logins": {}})["logins"]
            except Ilegivel:
                logins = {}        # é só o registro de quem entrou, não a lista de acesso: recomeça
            agora = _agora()
            logins[e] = _iso(agora)
            desde = agora - JANELA_LOGINS
            vivos = sorted(((k, v) for k, v in logins.items() if (_de_iso(v) or desde) > desde),
                           key=lambda kv: kv[1], reverse=True)[:MAX_LOGINS]
            _gravar_atomico(alvo, {"versao": 1, "logins": dict(vivos)})
    except Exception as erro:       # noqa: BLE001 — o registro nunca derruba o login
        log.warning("Acessos: não consegui registrar o login (%s).", type(erro).__name__)


def logins_recentes(config) -> list[dict]:
    """[{"email", "quando"}] de quem entrou nos últimos 30 dias, o mais recente primeiro."""
    p = pasta(config)
    if p is None:
        return []
    try:
        logins = (_ler(p / ARQUIVO_LOGINS, _forma_logins) or {"logins": {}})["logins"]
    except Ilegivel:
        return []
    desde = _agora() - JANELA_LOGINS
    vivos = [{"email": k, "quando": v} for k, v in logins.items() if (_de_iso(v) or desde) > desde]
    return sorted(vivos, key=lambda x: x["quando"], reverse=True)
