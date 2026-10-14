"""Chaves do Nexus pela tela (Base → Chaves do Nexus, 14/10/2026).

Levi, 14/10/2026, sobre pôr a chave das contestações no servidor pela T.I.: "Se precisa de TI então vou ter que mandar um
arquivo novo de deploy para a TI ué!". Escolheu a tela: o administrador cola a chave uma vez no Nexus do servidor, sem a
T.I. e sem reiniciar.

As regras:
- Só as chaves da lista CHAVES, cada uma com a conferência dela antes de gravar (a das contestações: uma chave privada
  X25519 válida e, havendo contestação no banco, que ela abra pelo menos uma). A tela nunca vira um editor do .env.
- Mora em `chaves.json`, na pasta de dados do Nexus (`acessos.pasta`, a mesma do acessos.json; fora do git, que é
  público), CIFRADA com AES-256-GCM numa chave derivada da NEXUS_SECRET_KEY (HKDF-SHA256, info própria) e presa ao nome
  da chave (dado associado): a cópia da pasta, sozinha, não abre nada. NEXUS_SECRET_KEY trocada = a gravada não abre: a
  tela diz isso e pede para colar de novo.
- A da tela vale na hora (o arquivo é relido a cada 30 s e logo depois de gravar) e VENCE a do .env; "Apagar" volta à do
  .env, se houver.
- A tela nunca mostra o valor, nem um pedaço dele: diz se está posta, de onde (tela ou .env), quando e por quem. O log
  diz quem gravou ou apagou qual chave, nunca o valor. Nada vai ao banco.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
from datetime import datetime, timezone

from flask import current_app, redirect, render_template, request, session, url_for

from . import acessos as A

log = logging.getLogger(__name__)

ARQUIVO = "chaves.json"
TTL_S = 30
TAMANHO_MAX = 4096
_INFO = b"nexus-chaves/v1"
_TRAVA = threading.Lock()
_CACHE: dict = {}
_CHAVE_CODIGO = "chaves_codigo"
_CHAVE_AVISO = "chaves_aviso"


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê (nunca com o valor colado)."""


def _b64d(s: str) -> bytes:
    s = str(s or "").strip()
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _conferir_contestacao(valor: str) -> str:
    """A privada das contestações: 32 bytes em base64 (o formato do par de 13/10/2026) que viram uma chave X25519 e, havendo
    contestação no banco, abrem pelo menos uma. Devolve a frase da conferência para o aviso."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

    from ..contratos import contestacoes as CT
    try:
        bruto = _b64d(valor)
        if len(bruto) != 32:
            raise ValueError
        X25519PrivateKey.from_private_bytes(bruto)
    except Exception:            # noqa: BLE001 — base64 quebrado, tamanho errado: a mensagem não repete o valor
        raise Recusada("Isto não é a chave privada das contestações: cole a linha inteira do arquivo "
                       "nexus_contestacao_privada.segredo.") from None
    try:
        from ..campo import visao
        linhas = [l for l in CT.livros.ler(visao._base(), visao._sessao(), CT.LIVRO, CT.ABA) if l.get("dados_cifrados")]
    except Exception as e:       # noqa: BLE001 — banco fora: grava, e diz que não deu para conferir
        return f"não consegui conferir com as contestações do banco ({type(e).__name__}); confira na tela Contestações"
    if not linhas:
        return "ainda não há contestação no banco para conferir"
    abertas = 0
    for l in linhas:
        try:
            CT.decifrar(l.get("dados_cifrados"), CT.contexto(l.get("id")), valor)
            abertas += 1
        except CT.CifraErro:
            pass
    if not abertas:
        raise Recusada(f"Esta chave não abre nenhuma das {len(linhas)} contestações gravadas no banco: é de outro par? "
                       "Nada foi gravado.")
    return f"ela abre {abertas} de {len(linhas)} contestações gravadas no banco"


# nome da variável → o que é, para que serve, e a conferência antes de gravar
CHAVES = {
    "NEXUS_CONTESTACAO_CHAVE_PRIVADA": {
        "nome": "Contestações dos clientes (chave privada)",
        "para": "abrir o nome, o contato e a mensagem do cliente em Contratos e clientes → Contestações",
        "arquivo": "nexus_contestacao_privada.segredo",
        "conferir": _conferir_contestacao,
    },
}


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _caminho(config):
    p = A.pasta(config)
    return (p / ARQUIVO) if p else None


def _aead(config):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    segredo = str(config.get("NEXUS_SECRET_KEY") or config.get("SECRET_KEY") or "").encode("utf-8")
    if not segredo:
        raise Recusada("Este Nexus está sem a NEXUS_SECRET_KEY: não há como guardar a chave cifrada.")
    return AESGCM(HKDF(algorithm=hashes.SHA256(), length=32, salt=hashlib.sha256(_INFO).digest(),
                       info=_INFO).derive(segredo))


def _cifrar(config, nome: str, valor: str) -> str:
    nonce = os.urandom(12)
    return base64.urlsafe_b64encode(nonce + _aead(config).encrypt(nonce, valor.encode("utf-8"),
                                                                  nome.encode("utf-8"))).decode("ascii")


def _decifrar(config, nome: str, cifra: str) -> str:
    bruto = base64.urlsafe_b64decode(str(cifra))
    return _aead(config).decrypt(bruto[:12], bruto[12:], nome.encode("utf-8")).decode("utf-8")


def _ler(config) -> dict:
    """{nome: {cifra, quando, por}} do arquivo, com cópia de TTL_S. Sem pasta ou sem arquivo: vazio."""
    caminho = _caminho(config)
    if caminho is None:
        return {}
    c = _CACHE.get(str(caminho))
    if c and time.time() - c[0] < TTL_S:
        return c[1]
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}
    except Exception as e:       # noqa: BLE001 — arquivo estragado: nenhuma chave da tela, e o log diz
        log.error("Chaves do Nexus: não consegui ler %s (%s); vale o .env.", caminho, type(e).__name__)
        dados = {}
    dados = {k: v for k, v in dados.items() if k in CHAVES and isinstance(v, dict) and v.get("cifra")}
    _CACHE[str(caminho)] = (time.time(), dados)
    return dados


def _gravar_arquivo(config, dados: dict) -> None:
    caminho = _caminho(config)
    if caminho is None:
        raise Recusada("Este Nexus está sem pasta de dados (NEXUS_DADOS): nada foi gravado.")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)     # no servidor (Linux), só o dono lê; no Windows não muda nada
    except OSError:
        pass
    os.replace(tmp, caminho)
    _CACHE.pop(str(caminho), None)


def valor(nome: str, config=None) -> str | None:
    """A chave em uso: a da tela (decifrada) e, sem ela, a do .env. A da tela que não abre (NEXUS_SECRET_KEY trocada)
    não vale: fica a do .env, e a tela diz."""
    cfg = current_app.config if config is None else config
    item = _ler(cfg).get(nome)
    if item:
        try:
            return _decifrar(cfg, nome, item["cifra"])
        except Exception:        # noqa: BLE001 — chave de cifra trocada ou arquivo mexido
            log.error("Chaves do Nexus: a %s gravada pela tela não abre (a NEXUS_SECRET_KEY mudou?); vale a do .env.",
                      nome)
    return str(cfg.get(nome) or "").strip() or None


def estado(config) -> list[dict]:
    """Cada chave da lista: {id, nome, para, arquivo, origem ("tela" | "env" | None), quando, por, nao_abre, env_tambem}."""
    dados = _ler(config)
    out = []
    for nome, d in CHAVES.items():
        item, nao_abre = dados.get(nome), False
        if item:
            try:
                _decifrar(config, nome, item["cifra"])
            except Exception:    # noqa: BLE001
                nao_abre = True
        env = bool(str(config.get(nome) or "").strip())
        origem = "tela" if item and not nao_abre else ("env" if env else None)
        out.append({"id": nome, "nome": d["nome"], "para": d["para"], "arquivo": d["arquivo"], "origem": origem,
                    "quando": A.hora_br(item.get("quando")) if item else "", "por": (item or {}).get("por", ""),
                    "nao_abre": nao_abre, "env_tambem": env and bool(item)})
    return out


def gravar(config, nome: str, texto: str, quem: str) -> str:
    """Confere e grava a chave colada; devolve o aviso. Recusada = nada mudou."""
    if nome not in CHAVES:
        raise Recusada("Chave desconhecida: nada foi gravado.")
    v = "".join(str(texto or "").split())             # a linha do arquivo, sem espaço nem quebra colados junto
    if not v:
        raise Recusada("Cole a chave antes de gravar.")
    if len(v) > TAMANHO_MAX:
        raise Recusada("O texto colado é grande demais para ser esta chave: nada foi gravado.")
    conferencia = CHAVES[nome]["conferir"](v)
    with _TRAVA:
        _CACHE.pop(str(_caminho(config)), None)
        dados = dict(_ler(config))                     # relida do disco, nunca a cópia de 30 s
        dados[nome] = {"cifra": _cifrar(config, nome, v), "quando": _agora().strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "por": quem}
        _gravar_arquivo(config, dados)
    log.info("Chaves do Nexus: %s gravada pela tela por %s.", nome, quem)
    return f"{CHAVES[nome]['nome']}: gravada e já em uso ({conferencia})."


def apagar(config, nome: str, quem: str) -> str:
    if nome not in CHAVES:
        raise Recusada("Chave desconhecida: nada foi apagado.")
    with _TRAVA:
        _CACHE.pop(str(_caminho(config)), None)
        dados = dict(_ler(config))
        if nome not in dados:
            raise Recusada("Esta chave não está gravada pela tela: nada foi apagado.")
        dados.pop(nome)
        _gravar_arquivo(config, dados)
    log.info("Chaves do Nexus: %s apagada da tela por %s.", nome, quem)
    resto = "vale a do .env do servidor" if str(config.get(nome) or "").strip() else "o Nexus fica sem ela"
    return f"{CHAVES[nome]['nome']}: apagada da tela; {resto}."


# ── a tela ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _codigo() -> str:
    if not session.get(_CHAVE_CODIGO):
        session[_CHAVE_CODIGO] = secrets.token_urlsafe(24)
    return session[_CHAVE_CODIGO]


def _quem() -> str:
    u = session.get("usuario")
    e = str(u.get("email") or "").strip().lower() if isinstance(u, dict) else ""
    return e or A.SENHA_DE_ADMIN


def _pagina(erro: str | None = None, status: int = 200):
    from ..torres.base import TORRE
    resp = current_app.make_response((render_template(
        "acessos/chaves.html", torre=TORRE, tela=TORRE.tela("chaves-nexus"), chaves=estado(current_app.config),
        sem_pasta=_caminho(current_app.config) is None, codigo=_codigo(), erro=erro,
        aviso=session.pop(_CHAVE_AVISO, None)), status))
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _post():
    from .telas_acessos import _de_outro_site
    if _de_outro_site():
        return _pagina(erro="Pedido de outro site: nada foi gravado.", status=403)
    certo, enviado = session.get(_CHAVE_CODIGO) or "", request.form.get("codigo") or ""
    if not certo or not hmac.compare_digest(enviado.encode(), certo.encode()):
        return _pagina(erro="O formulário venceu (a sessão mudou desde que a tela abriu): abra a tela de novo. Nada foi "
                            "gravado.", status=403)
    nome, acao = request.form.get("chave") or "", request.form.get("acao")
    try:
        if acao == "gravar":
            aviso = gravar(current_app.config, nome, request.form.get("valor"), _quem())
        elif acao == "apagar":
            aviso = apagar(current_app.config, nome, _quem())
        else:
            raise Recusada("Ação desconhecida: nada mudou.")
    except Recusada as ex:
        return _pagina(erro=str(ex), status=400)
    session[_CHAVE_AVISO] = aviso
    return redirect(url_for("torre_base.chaves_nexus"), code=303)


def registrar_chaves(bp) -> None:
    """Pendura a tela na torre Base (`/t/base/chaves-nexus`), vencendo o placeholder. Só administrador."""
    @bp.route("/chaves-nexus", methods=["GET", "POST"])
    def chaves_nexus():
        if not session.get("admin"):
            from .telas_acessos import _meu_email
            return render_template("cadastro/sem_permissao.html", titulo="Chaves do Nexus", eyebrow="Base · Chaves do Nexus",
                                   area="A tela Chaves do Nexus", email=_meu_email()), 403
        if request.method == "POST":
            return _post()
        return _pagina()
