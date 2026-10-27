"""A informação adicional da conferência de extintor (26/10/2026).

Levi: "Em extintores caso na última ronda tenha informações adicionais quero ao clicar na linha que apareça as
informações, caso não tenha que venha uma notificação". O livro do App (`extintores_app_campo · Extintores`) traz só
"Tem informação adicional" (sim/não): o texto do técnico é livre e pode ter nome de pessoa, e a API do banco tem leitura
aberta (regra 8). Por isso o texto vem como a foto (`fotos.py`): o App ENVIA ao Nexus, num POST em
`/t/hseq/extintores/info` com o código do extintor, o dia da conferência, a hora do envio (epoch), o texto e a
assinatura HMAC-SHA256 com uma chave DERIVADA da NEXUS_PESSOA_HMAC (rótulo `nexus:hseq:info-extintor`; sem ela, a rota
recusa). O Nexus confere a assinatura e a hora (15 min para cada lado) e guarda o texto da conferência mais recente de
cada extintor CIFRADO (o Cofre, NEXUS_CHAVE_CADASTRO) em `<dados>/hseq/extintores/info/<código>.json`: nunca no banco,
nunca em claro no disco. Texto de um dia mais velho que o guardado não substitui; texto vazio apaga o guardado daquele
dia em diante (a conferência nova sem informação).
"""
import hashlib
import hmac
import json
import time
from pathlib import Path

from ..cadastro.ligacoes import pasta_dados
from .fotos import CODIGO, DIA         # o mesmo formato do código e do dia da foto

ROTULO_CHAVE = b"nexus:hseq:info-extintor"      # deriva a chave da NEXUS_PESSOA_HMAC
JANELA_S = 15 * 60
TEXTO_MAX = 2000


def pasta(config) -> Path | None:
    """A pasta dos textos; teste sem pasta de dados própria = None (não lê nem grava a pasta de verdade)."""
    try:
        return pasta_dados(config) / "hseq" / "extintores" / "info"
    except RuntimeError:
        return None


def chave(config) -> bytes | None:
    base = str(config.get("NEXUS_PESSOA_HMAC") or "").strip()
    return hmac.new(base.encode(), ROTULO_CHAVE, hashlib.sha256).digest() if base else None


def assinatura(k: bytes, codigo: str, dia: str, ts, texto: str) -> str:
    """HMAC-SHA256 em hex de "código|dia|ts|sha256 do texto em UTF-8" (o App calcula igual com a mesma chave)."""
    msg = f"{codigo}|{dia}|{int(ts)}|{hashlib.sha256(texto.encode('utf-8')).hexdigest()}".encode()
    return hmac.new(k, msg, hashlib.sha256).hexdigest()


def _cofre(config):
    chave_cad = config.get("NEXUS_CHAVE_CADASTRO")
    if not chave_cad:
        return None
    from ..cadastro.cifra import Cofre
    return Cofre(chave_cad)


def _ctx(codigo: str) -> str:
    return f"hseq/info-extintor/{codigo}"


def receber(config, codigo, dia, ts, texto, assinatura_recebida, agora=None) -> tuple[int, str]:
    """(status HTTP, mensagem). Confere tudo antes de gravar; nada é gravado pela metade."""
    k, destino, cofre = chave(config), pasta(config), _cofre(config)
    if not k or destino is None or cofre is None:
        return 503, "recebimento desligado neste Nexus (sem NEXUS_PESSOA_HMAC ou NEXUS_CHAVE_CADASTRO)"
    codigo, dia = str(codigo or "").strip().upper(), str(dia or "").strip()
    if not CODIGO.fullmatch(codigo) or not DIA.fullmatch(dia):
        return 400, "código ou dia fora do formato"
    try:
        ts = int(ts)
    except (TypeError, ValueError):
        return 400, "hora (ts) fora do formato"
    if abs((agora or time.time()) - ts) > JANELA_S:
        return 401, "hora do envio fora da janela de 15 min"
    texto = str(texto or "")
    if len(texto) > TEXTO_MAX:
        return 400, f"texto maior que {TEXTO_MAX} letras"
    if not hmac.compare_digest(assinatura(k, codigo, dia, ts, texto), str(assinatura_recebida or "")):
        return 401, "assinatura não confere"
    destino.mkdir(parents=True, exist_ok=True)
    arq = destino / f"{codigo}.json"
    try:
        antes = json.loads(arq.read_text(encoding="utf-8")).get("dia", "")
    except (OSError, ValueError):
        antes = ""
    if antes and antes > dia:
        return 200, f"guardado o de {antes}, mais novo que o de {dia}"
    texto = texto.strip()
    if not texto:
        arq.unlink(missing_ok=True)
        return 200, "sem informação adicional: nada guardado"
    tmp = destino / f"{codigo}.json.parcial"
    tmp.write_text(json.dumps({"dia": dia, "recebido_em": int(agora or time.time()),
                               "cifrado": cofre.cifrar(texto, _ctx(codigo))}), encoding="utf-8")
    tmp.replace(arq)
    return 200, "guardado"


def ler(config, codigo) -> dict | None:
    """{dia, texto} do extintor, decifrado; None sem texto guardado (ou sem a chave do cadastro)."""
    destino, cofre = pasta(config), _cofre(config)
    codigo = str(codigo or "").strip().upper()
    if destino is None or cofre is None or not CODIGO.fullmatch(codigo):
        return None
    try:
        d = json.loads((destino / f"{codigo}.json").read_text(encoding="utf-8"))
        return {"dia": d.get("dia", ""), "texto": cofre.decifrar(d["cifrado"], _ctx(codigo))}
    except Exception:       # noqa: BLE001 — sem arquivo, arquivo mexido ou cifra de outra chave: sem texto
        return None
