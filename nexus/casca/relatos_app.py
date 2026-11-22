"""Os relatos do App de Campo nas Sugestões do Início (21/11/2026).

Levi, pelo chat do App de Campo: "os relatos do pessoal de campo, que é muito importante. Podia até ficar ali no início do
Nexus". No chat do Nexus, no mesmo dia: o caminho A ("1 - Caminho A"), "2 - Administradores" e, por fim, "na verdade pode
ir para sugestões no início com uma tag de App de campo!".

O caminho A: o App continua a FONTE do relato e do ciclo dele (a tabela `appfeedback` do servidor do App: aberto →
respondido → resolvido, que só o autor encerra, ou reaberto). O Nexus NÃO guarda o relato no banco: a API do banco tem
leitura aberta e o relato é texto livre com o nome do técnico (regra 8 de nexus/dados/CLAUDE.md). O Nexus lê a lista no
servidor do App, de servidor para servidor, com uma chave própria, e responde pela rota do App, que grava a resposta como
a do Admin/Supervisor de lá: o técnico lê em "Meus relatos", no App, sem nada mudar do lado dele.

O contrato (versão 1; o App é quem serve, o Nexus é quem lê; mudou aqui, muda lá no mesmo trabalho):
- `GET <URL>` com o cabeçalho `X-Nexus-Chave: <chave>` → 200 com
  `{"versao": 1, "relatos": [{"id", "tipo" (problema|melhoria|pontos), "texto", "tela", "status" (aberto|respondido|
  resolvido|reaberto), "criado_em" e "atualizado_em" (ISO 8601 com fuso), "autor": {"nome", "email", "papel", "funcao"},
  "versao_app", "aparelho", "mensagens": [{"id", "texto", "lado" (grid|campo), "por": {"nome"}, "em"}]}]}`. As
  mensagens são as respostas da Grid e o que o técnico escreveu depois (ao reabrir), na ordem em que aconteceram.
- `POST <URL>/<id>/responder` com a mesma chave e `{"resposta_id": "r" + 11 hexadecimais, "texto", "por": {"nome",
  "email"}}` → 200 `{"relato": {...}}`. O `resposta_id` segura o 2º envio (o App não grava outra). Recusa com
  `{"erro": "o motivo em palavras"}`, que a tela mostra como veio: 404 relato que não existe, 400 `resposta_id` fora da
  forma ou texto com menos de 5 caracteres (aqui ele nem sai), 401 chave errada e 503 o App ainda sem a chave dele (a
  v367 do App, 21/11/2026, que não tem 409: responder relato resolvido também vale lá).
- `<URL>` padrão: `https://gridco-campo-mw.azurewebsites.net/api/app/nexus/relatos`; o `.env` troca
  (`NEXUS_APP_RELATOS_URL`; fora da tela de chaves desde 22/11/2026). A chave (`NEXUS_APP_RELATOS_CHAVE`, 32 caracteres ou mais) é a mesma nos dois lados; sem ela
  o Nexus nem chama o App e o administrador lê o porquê nas Sugestões.

Quem lê e responde: o administrador do Nexus, o mesmo que lê as Sugestões recebidas. Responder pede o login (Microsoft ou
Fracttal): a resposta vai ao técnico com o nome de quem respondeu, e a senha de administrador não diz quem é.

Nada daqui grava no banco nem no disco: a lista fica numa cópia de 1 minuto, na memória."""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from flask import current_app

URL_PADRAO = "https://gridco-campo-mw.azurewebsites.net/api/app/nexus/relatos"
NOME_URL, NOME_CHAVE = "NEXUS_APP_RELATOS_URL", "NEXUS_APP_RELATOS_CHAVE"
VERSAO_DO_CONTRATO = 1
TTL_S = 60
TIMEOUT_S = 6
AREA, AREA_NOME = "_app", "App de campo"
ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
TIPOS = {"problema": "Problema", "melhoria": "Melhoria", "pontos": "Pontos"}
# o código do App -> (o rótulo, o tom do semáforo da casa). O que espera a Grid: aberto e reaberto
STATUS = {"aberto": ("Aberto", "info"), "respondido": ("Respondido", "neutro"), "reaberto": ("Reaberto", "alerta"),
          "resolvido": ("Resolvido", "ok")}
ESPERAM_A_GRID = ("aberto", "reaberto")
TITULO_MAX = 100
MINIMO = 5           # o App recusa (400) a resposta com menos de 5 caracteres (v367, 21/11/2026): aqui ela nem sai
_BRT = timezone(timedelta(hours=-3))
_CACHE: dict = {}
_RELENDO = {"thread": None}


class Recusada(ValueError):
    """Nada foi enviado ao App: o texto diz por quê, para a tela mostrar."""


class FonteErro(RuntimeError):
    """O App não deu a lista ou recusou o pedido; o texto é para a tela (nunca leva a chave)."""


def limpar() -> None:
    _CACHE.clear()


def envelhecer() -> None:
    """Faz a cópia vencer sem perdê-la (a próxima leitura vai ao App; se falhar, a última boa segue com o aviso)."""
    g = _CACHE.get("lista")
    if g and g.get("lido_em"):
        g["lido_em"] -= TTL_S + 1


def _abrir(req, timeout=None):
    """A chamada HTTP de verdade (os testes trocam esta função por um App falso)."""
    return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 — endereço da tela de chaves ou o padrão do App


def _conf(nome: str) -> str:
    from ..auth import chaves
    return (chaves.valor(nome) or "").strip()


def ligado() -> bool:
    return bool(_conf(NOME_CHAVE))


def _url() -> str:
    """O padrão do App ou o NEXUS_APP_RELATOS_URL do .env. Não mora em Base › Chaves do Nexus desde 22/11/2026 (Levi: "se
    o 'Relatos do App de Campo (endereço)' não é para usar então tira da tela!"): se o App mudar de endereço, troca aqui."""
    return (str(current_app.config.get(NOME_URL) or "").strip() or URL_PADRAO).rstrip("/")


def _pedido(caminho: str = "", corpo: dict | None = None) -> urllib.request.Request:
    dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8") if corpo is not None else None
    cab = {"X-Nexus-Chave": _conf(NOME_CHAVE), "User-Agent": "Nexus-GridCo/1 (relatos)", "Accept": "application/json"}
    if dados is not None:
        cab["Content-Type"] = "application/json; charset=utf-8"
    return urllib.request.Request(_url() + caminho, data=dados, headers=cab, method="POST" if dados is not None else "GET")


def _chamar(req) -> dict:
    """O JSON da resposta do App. O erro diz o que aconteceu em palavras, nunca a chave."""
    try:
        with _abrir(req, timeout=TIMEOUT_S) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as ex:
        motivo = ""
        try:
            motivo = str((json.loads(ex.read().decode("utf-8")) or {}).get("erro") or "").strip()[:200]
        except Exception:        # noqa: BLE001 — corpo que não é JSON: fica o código
            motivo = ""
        if ex.code == 401:
            raise FonteErro("o App recusou a chave do Nexus") from None
        if motivo:              # o App diz o motivo em palavras (4xx; e o 503 da chave que falta lá, na v367)
            raise FonteErro(motivo) from None
        if ex.code == 404:
            raise FonteErro("o App não tem a rota dos relatos para o Nexus, ou não achou o relato") from None
        raise FonteErro(f"o App respondeu {ex.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as ex:
        raise FonteErro(f"o App não respondeu ({type(ex).__name__})") from None
    except ValueError:
        raise FonteErro("o App respondeu algo que não é JSON") from None


# ── a lista ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _quando(v):
    try:
        d = datetime.fromisoformat(_txt(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(_BRT)


def _titulo(tipo_rotulo: str, texto: str) -> str:
    linha = texto.splitlines()[0].strip() if texto else ""
    if len(linha) > TITULO_MAX:
        linha = linha[:TITULO_MAX - 1].rstrip() + "…"
    return f"{tipo_rotulo}: {linha}" if linha else tipo_rotulo


def normalizar(r) -> dict | None:
    """O relato do App no formato da linha das Sugestões recebidas; None se faltar o essencial (o id, o texto) ou se o
    id não for um id (ele vai ao endereço do POST e ao `id` do HTML)."""
    if not isinstance(r, dict):
        return None
    rid, texto = _txt(r.get("id")), _txt(r.get("texto"))
    if not ID_RE.fullmatch(rid) or not texto:
        return None
    tipo = _txt(r.get("tipo")).lower()
    tipo_rotulo = TIPOS.get(tipo) or (tipo.capitalize() if tipo else "Relato")
    status = _txt(r.get("status")).lower() or "aberto"
    rotulo, tom = STATUS.get(status) or (status.capitalize(), "neutro")
    autor = r.get("autor") if isinstance(r.get("autor"), dict) else {}
    quando = _quando(r.get("criado_em"))
    mensagens = []
    for m in r.get("mensagens") or []:
        if not isinstance(m, dict) or not _txt(m.get("texto")):
            continue
        em = _quando(m.get("em"))
        por = m.get("por") if isinstance(m.get("por"), dict) else {}
        mensagens.append({"texto": _txt(m.get("texto")), "lado": "campo" if _txt(m.get("lado")) == "campo" else "grid",
                          "nome": _txt(por.get("nome")), "quando": em,
                          "quando_txt": em.strftime("%d/%m/%Y às %H:%M") if em else ""})
    mensagens.sort(key=lambda m: m["quando"] or datetime.min.replace(tzinfo=_BRT))
    return {"id": f"app-{rid}", "rid": rid, "origem": "app", "quando": quando,
            "quando_txt": quando.strftime("%d/%m/%Y às %H:%M") if quando else "—",
            "area": AREA, "area_nome": AREA_NOME, "tipo": tipo, "tipo_rotulo": tipo_rotulo,
            "titulo": _titulo(tipo_rotulo, texto), "descricao": texto, "nome": _txt(autor.get("nome")),
            "email": _txt(autor.get("email")), "papel": _txt(autor.get("papel")), "funcao": _txt(autor.get("funcao")),
            "tela": _txt(r.get("tela")), "versao_app": _txt(r.get("versao_app")), "aparelho": _txt(r.get("aparelho")),
            "anexos": [], "legivel": True, "pessoa_hmac": "", "mensagens": mensagens,
            "respostas": [m for m in mensagens if m["lado"] == "grid"],
            "status": status, "status_rotulo": rotulo, "status_tom": tom, "concluido": status == "resolvido",
            "espera_a_grid": status in ESPERAM_A_GRID, "status_em_txt": "", "status_por": ""}


def _validar(d) -> list:
    if not isinstance(d, dict):
        raise FonteErro("a resposta do App não é um objeto")
    if d.get("versao") != VERSAO_DO_CONTRATO:
        raise FonteErro(f"o App fala a versão {d.get('versao')!r} do contrato, e o Nexus entende a {VERSAO_DO_CONTRATO}")
    if not isinstance(d.get("relatos"), list):
        raise FonteErro("a resposta do App não tem a lista de relatos")
    return d["relatos"]


def ler(forcar: bool = False) -> dict:
    """{"relatos", "erro", "lido_em", "ligado"}, da cópia de 1 minuto. Sem a chave, nem chama o App. Leitura que falha
    devolve a última lista boa com o erro."""
    if not ligado():
        return {"relatos": [], "erro": "", "lido_em": None, "ligado": False}
    agora = time.time()
    g = _CACHE.get("lista")
    if g and not forcar and g.get("lido_em") and agora - g["lido_em"] < TTL_S:
        return g
    try:
        brutos = _validar(_chamar(_pedido()))
    except FonteErro as ex:
        base = g or {"relatos": [], "lido_em": None, "ligado": True}
        _CACHE["lista"] = dict(base, erro=str(ex), lido_em=agora if g else None)
        return _CACHE["lista"]
    relatos = [n for n in (normalizar(r) for r in brutos) if n]
    relatos.sort(key=lambda x: x["quando"] or datetime.min.replace(tzinfo=_BRT), reverse=True)
    _CACHE["lista"] = {"relatos": relatos, "erro": "", "lido_em": agora, "ligado": True}
    return _CACHE["lista"]


def esperando() -> int | None:
    """Quantos relatos esperam a Grid (aberto ou reaberto), para o número da aba Sugestões do administrador. O Início é a
    primeira página de todos: sai da cópia; velha ou ausente, a releitura vai por trás (None = ainda não sei)."""
    if not ligado():
        return 0
    g = _CACHE.get("lista")
    velho = not g or not g.get("lido_em") or time.time() - g["lido_em"] >= TTL_S
    if velho:
        if current_app.config.get("TESTING"):
            g = ler()
        else:
            _reler_por_tras()
    if not g or g.get("lido_em") is None:
        return None
    return sum(1 for r in g["relatos"] if r["espera_a_grid"])


def _reler_por_tras() -> None:
    t = _RELENDO["thread"]
    if t is not None and t.is_alive():
        return
    app = current_app._get_current_object()

    def rodar():
        with app.app_context():
            try:
                ler(forcar=True)
            except Exception:    # noqa: BLE001 — o número só não aparece
                pass
    t = threading.Thread(target=rodar, name="nexus-relatos-app", daemon=True)
    _RELENDO["thread"] = t
    t.start()


# ── a resposta ──────────────────────────────────────────────────────────────────────────────────────────────────────
def responder(rid, texto, usuario, resposta_id, maximo: int) -> dict:
    """Manda a resposta ao App, que a grava como a do Admin/Supervisor de lá. Recusada = nada saiu daqui; FonteErro = o
    App não aceitou (ou não respondeu). Deu certo: a cópia vence, e a próxima abertura relê a lista."""
    rid, texto = _txt(rid), _txt(texto)
    usuario = usuario if isinstance(usuario, dict) else {}
    email = _txt(usuario.get("email"))
    if not ligado():
        raise Recusada("Os relatos do App de Campo ainda não estão ligados neste Nexus")
    if not email:
        raise Recusada("Entre com o seu login (Microsoft ou Fracttal) para responder: a resposta vai ao técnico com o "
                       "seu nome")
    if not ID_RE.fullmatch(rid):
        raise Recusada("Relato desconhecido")
    if not re.fullmatch(r"r[0-9a-f]{11}", _txt(resposta_id)):
        raise Recusada("O formulário venceu: abra a aba de novo")
    if not texto:
        raise Recusada("Escreva a resposta")
    if len(texto) < MINIMO:
        raise Recusada(f"A resposta precisa de {MINIMO} caracteres ou mais")
    if len(texto) > maximo:
        raise Recusada(f"A resposta passa de {maximo} caracteres")
    corpo = {"resposta_id": _txt(resposta_id), "texto": texto,
             "por": {"nome": _txt(usuario.get("nome")), "email": email}}
    d = _chamar(_pedido("/" + urllib.parse.quote(rid, safe="") + "/responder", corpo))
    envelhecer()
    return d if isinstance(d, dict) else {}
