"""As fotos dos extintores no Nexus (Segurança · HSEQ, 09/10/2026).

Levi, 09/10: "Quando tiver foto (ronda de extintor feita no app) ao expandir a usina e aparecer os extintores deve ter a
opção de visualizar foto de extintor"; e a TST, sobre o relatório: "o padrão será as fotos ao lado de cada extintor".

A foto mora no App, e o Nexus não lê o Azure: é o App que ENVIA ao Nexus a foto de cada conferência (`receber`), num
POST em `/t/hseq/extintores/foto` com o código do extintor, o dia da conferência, a hora do envio (epoch) e a
assinatura HMAC-SHA256 (`assinatura`) com uma chave DERIVADA da NEXUS_PESSOA_HMAC, a chave que o App e o Nexus já têm
(nenhuma configuração nova; sem ela, a rota recusa). O Nexus confere a assinatura e a hora (15 min para cada lado), abre
a imagem, regrava em JPEG de até 1600 px e guarda a mais recente de cada extintor em `<dados>/hseq/extintores/fotos/`
(`<código>.jpg` e `<código>.json` com o dia). Foto de um dia mais velho que a guardada não substitui. A rota é pública só
para quem assina (o portão de login a deixa passar: `auth.ROTAS_PUBLICAS`). A foto não vai ao banco (a API tem leitura
aberta e foto não é tabela).
"""
import hashlib
import hmac
import io
import json
import re
import time
from collections import OrderedDict
from pathlib import Path

from ..cadastro.ligacoes import pasta_dados

ROTULO_CHAVE = b"nexus:hseq:fotos-extintor"     # deriva a chave das fotos da NEXUS_PESSOA_HMAC
JANELA_S = 15 * 60
LADO_MAX, QUALIDADE = 1600, 82
TAMANHO_MAX = 8 * 1024 * 1024
MINI_PX = 160                                  # a miniatura da tabela (a tela mostra 32 px; 160 fica nítido)
CODIGO = re.compile(r"[A-Z0-9][A-Z0-9.\-]{2,60}")
DIA = re.compile(r"\d{4}-\d{2}-\d{2}")
_MINIS: OrderedDict = OrderedDict()            # (código, dia) -> JPEG da miniatura; as últimas 600 na memória


def pasta(config) -> Path | None:
    """A pasta das fotos; teste sem pasta de dados própria = None (não lê nem grava a pasta de verdade)."""
    try:
        return pasta_dados(config) / "hseq" / "extintores" / "fotos"
    except RuntimeError:
        return None


def chave(config) -> bytes | None:
    base = str(config.get("NEXUS_PESSOA_HMAC") or "").strip()
    return hmac.new(base.encode(), ROTULO_CHAVE, hashlib.sha256).digest() if base else None


def assinatura(k: bytes, codigo: str, dia: str, ts, dados: bytes) -> str:
    """HMAC-SHA256 de "código|dia|ts|sha256 da foto" (o App calcula igual com a mesma chave derivada)."""
    msg = f"{codigo}|{dia}|{int(ts)}|{hashlib.sha256(dados).hexdigest()}".encode()
    return hmac.new(k, msg, hashlib.sha256).hexdigest()


def receber(config, codigo, dia, ts, assinatura_recebida, dados: bytes, agora=None) -> tuple[int, str]:
    """(status HTTP, mensagem). Confere tudo antes de gravar; nada é gravado pela metade."""
    k = chave(config)
    destino = pasta(config)
    if not k or destino is None:
        return 503, "recebimento de fotos desligado neste Nexus (sem NEXUS_PESSOA_HMAC)"
    codigo, dia = str(codigo or "").strip().upper(), str(dia or "").strip()
    if not CODIGO.fullmatch(codigo) or not DIA.fullmatch(dia):
        return 400, "código ou dia fora do formato"
    try:
        ts = int(ts)
    except (TypeError, ValueError):
        return 400, "hora (ts) fora do formato"
    if abs((agora or time.time()) - ts) > JANELA_S:
        return 401, "hora do envio fora da janela de 15 min"
    if not dados or len(dados) > TAMANHO_MAX:
        return 400, "foto vazia ou maior que 8 MB"
    if not hmac.compare_digest(assinatura(k, codigo, dia, ts, dados), str(assinatura_recebida or "")):
        return 401, "assinatura não confere"
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(dados))
        im = im.convert("RGB")
        im.thumbnail((LADO_MAX, LADO_MAX))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=QUALIDADE, optimize=True)
    except Exception:       # noqa: BLE001 — não é imagem
        return 400, "o arquivo não é uma imagem"
    destino.mkdir(parents=True, exist_ok=True)
    meta = destino / f"{codigo}.json"
    try:
        antes = json.loads(meta.read_text(encoding="utf-8")).get("dia", "")
    except (OSError, ValueError):
        antes = ""
    if antes and antes > dia:
        return 200, f"guardada a de {antes}, mais nova que a de {dia}"
    tmp = destino / f"{codigo}.jpg.parcial"
    tmp.write_bytes(out.getvalue())
    tmp.replace(destino / f"{codigo}.jpg")
    meta.write_text(json.dumps({"dia": dia, "recebida_em": int(agora or time.time())}), encoding="utf-8")
    return 200, "foto guardada"


def foto(config, codigo) -> bytes | None:
    """A foto guardada do extintor, ou None."""
    p = pasta(config)
    codigo = str(codigo or "")
    if p is None or not CODIGO.fullmatch(codigo):
        return None
    arq = p / f"{codigo}.jpg"
    return arq.read_bytes() if arq.is_file() else None


def mini(config, codigo) -> bytes | None:
    """A miniatura (160 px) da foto, feita na hora e guardada na memória (pelo código e o dia da foto)."""
    dados = foto(config, codigo)
    if not dados:
        return None
    k = (codigo, disponiveis(config).get(codigo, ""))
    if k in _MINIS:
        _MINIS.move_to_end(k)
        return _MINIS[k]
    from PIL import Image
    im = Image.open(io.BytesIO(dados))
    im.thumbnail((MINI_PX, MINI_PX))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=75)
    _MINIS[k] = out.getvalue()
    while len(_MINIS) > 600:
        _MINIS.popitem(last=False)
    return _MINIS[k]


def disponiveis(config) -> dict:
    """{código: dia da foto} das fotos guardadas (uma leitura da pasta por chamada)."""
    p = pasta(config)
    if p is None or not p.is_dir():
        return {}
    out = {}
    for arq in p.glob("*.jpg"):
        try:
            out[arq.stem] = json.loads((p / f"{arq.stem}.json").read_text(encoding="utf-8")).get("dia", "")
        except (OSError, ValueError):
            out[arq.stem] = ""
    return out
