"""Acessos dos clientes ao Dashboard Thopen (Levi, 14/10/2026: "É possível implementarmos uma visão de login e senha
para o dashboard thopen?" — contas por pessoa, ligada a um cliente, administradas no Nexus, em Contratos e clientes; o
painel sobe no servidor da T.I. em https://app.gridco.com.br/performance/). Spec no repositório da plataforma:
docs/superpowers/specs/2026-10-14-thopen-login-por-pessoa-design.md.

O Nexus é a FONTE das contas: livro `nexus_acessos_clientes` · `dim_conta_cliente` (registrado em `catalogo.LIVROS`
antes da 1ª gravação). Grão: 1 linha = 1 conta, o estado atual (o livro é trocado inteiro a cada ação, sob a trava, relido antes e
conferido depois pelo `livros.publicar`). Quem decidiu vai em `alterada_por_hmac` e no log.

A API do banco tem LEITURA ABERTA (nexus/dados/CLAUDE.md, regra 8): nome e e-mail vão só cifrados, duas vezes —
`dados_5080`, selados para a chave PÚBLICA do 5080 (X25519 + HKDF-SHA256 + AES-256-GCM, a mesma receita de
thopen/acessos.py; `NEXUS_ACESSOS_5080_PUBLICA`, pela tela Base → Chaves do Nexus), e `dados_nexus`, no Cofre do Nexus
(a chave do cadastro), para esta tela. Nenhum segredo é compartilhado: a privada do 5080 só existe no servidor dele.

O link de definir senha é de uso único e vale 72 h: o token só aparece uma vez, na tela, para a Grid mandar pelo Teams
ou WhatsApp (o e-mail do servidor está barrado no tenant); no banco vai o sha256 dele. Quem define a senha é o 5080,
no livro `thopen_acessos` · `senhas` — o Nexus só lê de lá QUANDO cada conta definiu a senha (nunca a senha).
"""
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import threading
import uuid
from datetime import datetime, timedelta, timezone

from flask import current_app

from ..dados import livros

log = logging.getLogger(__name__)

LIVRO, NOME_LIVRO, ABA = "nexus_acessos_clientes", "Nexus · acessos dos clientes ao Dashboard Thopen", "dim_conta_cliente"
CAB = ("conta_id", "carteiras", "papel", "status", "convite_hash", "convite_expira", "criada_em", "alterada_em",
       "alterada_por_hmac", "dados_5080", "dados_nexus")
LIVRO_SENHAS, ABA_SENHAS = "thopen_acessos", "senhas"
# as carteiras do Dashboard Thopen (thopen/acessos.CARTEIRAS e dashboard_thopen.CARTEIRA_ORDEM, no repositório da
# plataforma): o papel "grid" vê todas
CARTEIRAS = ("Thopen", "Copel", "Matrix", "Polaris")
PAPEIS = {"cliente": "Cliente", "grid": "Grid Co."}
CHAVE_PUBLICA = "NEXUS_ACESSOS_5080_PUBLICA"
URL_PADRAO = "https://app.gridco.com.br/performance"
CONVITE_HORAS = 72
PREFIXO = "cx1:"
_INFO = b"thopen-acessos/v1"
_TRAVA = threading.Lock()
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_BRT = timezone(timedelta(hours=-3))


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê, para a tela."""


def _b64e(b):
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _b64d(s):
    s = str(s or "").strip()
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def ctx_5080(conta_id) -> str:
    return f"{LIVRO}/{conta_id}/dados_5080"


def ctx_nexus(conta_id) -> str:
    return f"banco/acessos_clientes/{conta_id}"


def selar(texto: str, ctx: str, publica_b64: str) -> str:
    """Para o 5080 abrir com a privada dele (thopen/acessos.abrir). Chave efêmera por selo; o contexto vai como dado
    associado (copiado para outra conta, não abre)."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    try:
        destino = X25519PublicKey.from_public_bytes(_b64d(publica_b64))
    except Exception:             # noqa: BLE001
        raise Recusada(f"A chave pública do painel ({CHAVE_PUBLICA}) não está posta ou não vale: cole-a em Base → "
                       "Chaves do Nexus") from None
    ef = X25519PrivateKey.generate()
    pub_ef = ef.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    chave = HKDF(algorithm=hashes.SHA256(), length=32, salt=pub_ef, info=_INFO).derive(ef.exchange(destino))
    nonce = os.urandom(12)
    return PREFIXO + _b64e(pub_ef + nonce + AESGCM(chave).encrypt(nonce, texto.encode("utf-8"), ctx.encode("utf-8")))


def _cofre():
    chave = current_app.config.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO)")
    from ..cadastro.cifra import Cofre
    return Cofre(chave)


def _publica() -> str | None:
    from ..auth import chaves
    return chaves.valor(CHAVE_PUBLICA)


def _url_painel() -> str:
    return str(current_app.config.get("NEXUS_THOPEN_URL") or URL_PADRAO).rstrip("/")


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def _quando(v):
    try:
        d = datetime.fromisoformat(str(v or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _br(d, fmt) -> str:
    return d.astimezone(_BRT).strftime(fmt) if d else ""


def _base_sessao():
    from ..campo import visao
    return visao._base(), visao._sessao()


def _ler(aba_livro=(LIVRO, ABA)) -> list[dict]:
    base, sessao = _base_sessao()
    return livros.ler(base, sessao, *aba_livro)


def _quem(usuario) -> str:
    from ..campo.ligacao_cadastro import codigo_da_pessoa
    email = str((usuario or {}).get("email") or "").strip().lower()
    return codigo_da_pessoa(current_app.config.get("NEXUS_PESSOA_HMAC"), email) or ("admin" if not email else "")


def contas() -> dict:
    """{erro, sem_chave, contas: [conta]} — a conta com nome e e-mail abertos (Cofre do Nexus) e quando definiu a senha
    (o livro do 5080). A mais nova em cima."""
    out = {"erro": None, "sem_chave": not _publica(), "contas": []}
    try:
        linhas = _ler()
    except Exception as e:        # noqa: BLE001 — banco fora: a tela diz, nunca "nenhuma conta" falso
        out["erro"] = f"Não consegui ler as contas do banco ({type(e).__name__})"
        return out
    try:
        senhas = _ler((LIVRO_SENHAS, ABA_SENHAS))
    except Exception:             # noqa: BLE001 — sem o livro do 5080: as contas aparecem sem a data da senha
        senhas = []
    definida, usados = {}, set()
    for s in senhas:
        cid, q = str(s.get("conta_id") or ""), _quando(s.get("definida_em"))
        if s.get("convite_hash"):
            usados.add(str(s.get("convite_hash")))        # a regra do 5080: link cujo hash já definiu senha está usado
        if q and (cid not in definida or q > definida[cid]):
            definida[cid] = q
    try:
        cofre = _cofre()
    except Recusada:
        cofre = None
    agora = _agora()
    for l in linhas:
        cid = str(l.get("conta_id") or "")
        dados = {}
        if cofre:
            try:
                dados = json.loads(cofre.decifrar(l.get("dados_nexus") or "", ctx_nexus(cid)))
            except Exception:     # noqa: BLE001 — cifra de outra chave: a linha aparece sem nome
                dados = {}
        expira, h = _quando(l.get("convite_expira")), str(l.get("convite_hash") or "")
        out["contas"].append({
            "conta_id": cid, "nome": dados.get("nome") or "", "email": dados.get("email") or "",
            "carteiras": [c for c in str(l.get("carteiras") or "").split(";") if c],
            "papel": l.get("papel") or "cliente", "ativa": str(l.get("status") or "") == "ativa",
            "senha_em": _br(definida.get(cid), "%d/%m/%Y"),
            "link": ("pendente" if h and h not in usados and expira and expira > agora else
                     "vencido" if h and h not in usados and expira else ""),
            "link_ate": _br(expira, "%d/%m %H:%M"), "criada_em": _br(_quando(l.get("criada_em")), "%d/%m/%Y"),
            "abre": bool(dados) or cofre is None})
    out["contas"].sort(key=lambda c: (c["nome"] or c["email"]).lower())
    return out


def _gravar(linhas: list[dict]) -> None:
    cfg = current_app.config
    if not cfg.get("GRIDCO_SQL_TOKEN"):
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN)")
    base, sessao = _base_sessao()
    livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), [[l.get(c) for c in CAB] for l in linhas])},
                    base=base, token=cfg["GRIDCO_SQL_TOKEN"], sessao=sessao)


def _novo_link(linha: dict) -> str:
    token = secrets.token_urlsafe(32)
    linha["convite_hash"] = hashlib.sha256(token.encode("utf-8")).hexdigest()
    linha["convite_expira"] = _iso(_agora() + timedelta(hours=CONVITE_HORAS))
    return f"{_url_painel()}/convite/{token}"


def criar(nome: str, email: str, carteiras, papel: str, usuario) -> tuple[dict, str]:
    """Cria a conta e já devolve o link de definir senha (aparece uma vez). Recusada: o texto diz por quê."""
    nome = " ".join(str(nome or "").split())
    email = str(email or "").strip().lower()
    papel = papel if papel in PAPEIS else "cliente"
    carteiras = [c for c in CARTEIRAS if c in set(carteiras or [])]
    if not nome:
        raise Recusada("Escreva o nome da pessoa")
    if not _EMAIL.match(email):
        raise Recusada("O e-mail não parece válido")
    if papel == "cliente" and not carteiras:
        raise Recusada("Marque ao menos uma carteira que a pessoa vai ver")
    publica = _publica()
    cofre = _cofre()
    with _TRAVA:
        linhas = _ler()
        for l in linhas:
            try:
                if json.loads(cofre.decifrar(l.get("dados_nexus") or "", ctx_nexus(l.get("conta_id")))).get("email") == email:
                    raise Recusada("Já existe uma conta com este e-mail: gere um link novo para ela")
            except Recusada:
                raise
            except Exception:     # noqa: BLE001 — linha que não abre: não é a mesma pessoa que dá para saber
                continue
        cid = uuid.uuid4().hex[:12]
        agora = _iso(_agora())
        dados = json.dumps({"nome": nome, "email": email}, ensure_ascii=False)
        nova = {"conta_id": cid, "carteiras": ";".join(CARTEIRAS if papel == "grid" else carteiras), "papel": papel,
                "status": "ativa", "criada_em": agora, "alterada_em": agora, "alterada_por_hmac": _quem(usuario),
                "dados_5080": selar(dados, ctx_5080(cid), publica), "dados_nexus": cofre.cifrar(dados, ctx_nexus(cid))}
        link = _novo_link(nova)
        _gravar(linhas + [nova])
    log.info("Acessos dos clientes: conta %s criada por %s", cid, nova["alterada_por_hmac"])
    return {"conta_id": cid, "nome": nome, "email": email}, link


def _alterar(conta_id: str, usuario, mudar) -> dict:
    with _TRAVA:
        linhas = _ler()
        alvo = next((l for l in linhas if str(l.get("conta_id")) == str(conta_id)), None)
        if not alvo:
            raise Recusada("Conta não encontrada")
        extra = mudar(alvo)
        alvo["alterada_em"], alvo["alterada_por_hmac"] = _iso(_agora()), _quem(usuario)
        _gravar(linhas)
    return extra


def gerar_link(conta_id: str, usuario) -> str:
    """Um link novo (senha nova ou esquecida): o anterior deixa de valer. O nome e o e-mail vão selados de novo para a
    pública em uso: se o par do painel foi trocado, é assim que a conta volta a abrir lá."""
    publica, cofre = _publica(), _cofre()

    def mudar(l):
        if str(l.get("status")) != "ativa":
            raise Recusada("Reative a conta antes de gerar o link")
        cid = l.get("conta_id")
        try:
            dados = cofre.decifrar(l.get("dados_nexus") or "", ctx_nexus(cid))
        except Exception:         # noqa: BLE001
            raise Recusada("O nome e o e-mail desta conta não abrem com a chave do cadastro deste Nexus") from None
        l["dados_5080"] = selar(dados, ctx_5080(cid), publica)
        return _novo_link(l)
    link = _alterar(conta_id, usuario, mudar)
    log.info("Acessos dos clientes: link novo para a conta %s", conta_id)
    return link


def definir_status(conta_id: str, ativa: bool, usuario) -> None:
    def mudar(l):
        l["status"] = "ativa" if ativa else "desativada"
        if not ativa:
            l["convite_hash"], l["convite_expira"] = "", ""      # link pendente de conta desativada não vale mais
    _alterar(conta_id, usuario, mudar)
    log.info("Acessos dos clientes: conta %s %s", conta_id, "reativada" if ativa else "desativada")
