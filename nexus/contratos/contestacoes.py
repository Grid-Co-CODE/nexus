"""Contestações dos clientes (Levi, 13/10/2026: "contestação ligada ao Nexus: em contratos e clientes no Nexus pode ter
um lugar para essas contestações separando setores!"; "ficaria na API do PG, pode aplicar e construir!").

De onde vem: o Dashboard Thopen (5080) grava cada contestação no livro `thopen_contestacoes` · `contestacoes` (o 5080 é a
FONTE; fato `contestacao_cliente` no catálogo, nexus/dados/catalogo.py). Grão: 1 linha = 1 contestação × 1 setor — as
mesmas mensagens do Teams: ronda → Zeladoria; geração, disponibilidade, desligamento, string e tracker → Performance. O
cliente que marca dos dois lados gera duas linhas com o mesmo `contestacao_id`.

A API do banco tem LEITURA ABERTA (nexus/dados/CLAUDE.md, regra 8): nome, contato, mensagem e o que estava na tela do
cliente vêm só CIFRADOS (`dados_cifrados`). A cifra é ASSIMÉTRICA (X25519 + HKDF-SHA256 + AES-256-GCM, chave efêmera por
cifra): o 5080, público, só tem a chave pública e não abre nada; o Nexus abre com a privada
(`NEXUS_CONTESTACAO_CHAVE_PRIVADA`, no .env). A conta é a MESMA do thopen/contestacao_banco.py do repositório da
plataforma (o teste daqui cifra com a mesma receita e confere). Sem a chave, a tela lista as contestações sem os dados
do cliente e diz por quê. O decifrado vive só na memória da tela: nada vai a disco nem a cache.
"""
import base64
import json
from datetime import datetime, timedelta, timezone

from ..dados import fatos as D
from ..dados import livros

LIVRO, ABA = "thopen_contestacoes", "contestacoes"
PREFIXO = "cx1:"
_INFO = b"thopen-contestacao/v1"
CHAVE = "NEXUS_CONTESTACAO_CHAVE_PRIVADA"
SETORES = (("performance", "Performance"), ("zeladoria", "Zeladoria"))
ITENS = {"geracao": "Geração", "disponibilidade": "Disponibilidade", "desligamento": "Desligamento",
         "string": "String", "tracker": "Tracker", "ronda": "Ronda"}
# o que o cliente via naquele dia (o gráfico e as tabelas do Diário), na ordem do cartão do Teams
TELA = (("geracao", "Geração"), ("irradiacao", "Irradiação"), ("disp", "Disp"), ("tracker", "Tracker parado"),
        ("string", "String sem corrente"), ("comentario", "Comentário"), ("ronda", "Ronda"))
_BRT = timezone(timedelta(hours=-3))


class CifraErro(RuntimeError):
    """Chave ausente ou inválida, cifra adulterada ou de outra linha. Nunca traz o dado nem a chave."""


def _b64d(s):
    s = str(s or "").strip()
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def contexto(linha_id) -> str:
    return f"{LIVRO}/{linha_id}/dados"


def decifrar(valor, ctx: str, privada_b64: str) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    if not (isinstance(valor, str) and valor.startswith(PREFIXO)):
        raise CifraErro("valor não está cifrado")
    try:
        bruto = _b64d(valor[len(PREFIXO):])
        pub_ef, nonce, corpo = bruto[:32], bruto[32:44], bruto[44:]
        segredo = X25519PrivateKey.from_private_bytes(_b64d(privada_b64)).exchange(
            X25519PublicKey.from_public_bytes(pub_ef))
        chave = HKDF(algorithm=hashes.SHA256(), length=32, salt=pub_ef, info=_INFO).derive(segredo)
        return AESGCM(chave).decrypt(nonce, corpo, ctx.encode("utf-8")).decode("utf-8")
    except Exception:               # noqa: BLE001 — InvalidTag, chave errada, base64 quebrado: tudo "não confere"
        raise CifraErro("cifra não confere: adulterada, de outra linha ou de outra chave") from None


def _quando(v):
    try:
        return datetime.fromisoformat(str(v or "").replace("Z", "+00:00")).astimezone(_BRT)
    except ValueError:
        return None


def _dia(v):
    v = D._id(v)
    try:
        return datetime.strptime(str(v), "%Y%m%d").date() if v else None
    except ValueError:
        return None


def _linha(l: dict, privada: str | None) -> dict:
    dados, aberto = {}, None
    if privada:
        try:
            dados = json.loads(decifrar(l.get("dados_cifrados"), contexto(l.get("id")), privada))
            aberto = True
        except Exception:           # noqa: BLE001 — cifra de outra chave ou adulterada: a linha aparece sem os dados
            aberto = False
    ini, fim = _dia(l.get("data_id_contestada_ini")), _dia(l.get("data_id_contestada_fim"))
    tela = dados.get("tela") or {}
    return {"id": l.get("id"), "contestacao_id": l.get("contestacao_id"), "quando": _quando(l.get("recebida_em")),
            "usina": str(l.get("usina") or ""), "usina_id": D._id(l.get("usina_id")),
            "setor": str(l.get("setor") or ""), "ini": ini, "fim": fim or ini,
            "itens": [ITENS.get(i, i) for i in str(l.get("itens") or "").split(";") if i],
            "avisado": str(l.get("avisado_teams") or "").strip().lower() == "sim",
            "aberto": aberto, "nome": dados.get("nome") or "", "contato": dados.get("contato") or "",
            "mensagem": dados.get("mensagem") or "",
            "tela": [(rot, tela[k]) for k, rot in TELA if tela.get(k)]}


def contestacoes(linhas: list[dict] | None = None) -> dict:
    """{erro, sem_chave, por_setor: {setor: [linha]}, contagem: {setor: n}} — a mais nova em cima. `linhas` = o livro
    (os testes passam; a tela lê do banco)."""
    out = {"erro": None, "sem_chave": False, "por_setor": {s: [] for s, _ in SETORES}, "contagem": {}}
    if linhas is None:
        from ..campo import visao
        try:
            linhas = livros.ler(visao._base(), visao._sessao(), LIVRO, ABA)
        except Exception as e:      # noqa: BLE001 — banco fora: a tela diz, nunca um "nenhuma contestação" falso
            out["erro"] = f"Não consegui ler as contestações do banco ({type(e).__name__})"
            linhas = []
    # a da tela Base → Chaves do Nexus (14/10/2026) e, sem ela, a do .env
    from ..auth import chaves as K
    privada = K.valor(CHAVE)
    out["sem_chave"] = not privada
    for l in linhas:
        x = _linha(l, privada)
        out["por_setor"].setdefault(x["setor"], []).append(x)
    for s, lst in out["por_setor"].items():
        lst.sort(key=lambda x: x["quando"] or datetime.min.replace(tzinfo=_BRT), reverse=True)
        out["contagem"][s] = len(lst)
    return out
