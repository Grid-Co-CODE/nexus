"""A marca do técnico pelo App de Campo (16/10/2026).

Levi, 16/10/2026, perguntado se o técnico marca o motivo da tarefa pelo App: "Sim, e já vale" (marcou no App, vale na
hora como a marca do PCM) e, sobre quais motivos, "Todos do cadastro".

O App ENVIA cada marca ao Nexus, como já envia as fotos dos extintores (`nexus/hseq/fotos.py`): um POST com o corpo em
JSON em `/t/pcm/motivos/app`, com a hora do envio (epoch) no cabeçalho `X-Nexus-Ts` e a assinatura HMAC-SHA256 em
`X-Nexus-Assinatura`, numa chave DERIVADA da NEXUS_PESSOA_HMAC (a que o App e o Nexus já têm: nenhuma configuração
nova; sem ela, a rota recusa). A assinatura é a de "<ts>." seguido do corpo cru, e a hora vale 15 min para cada lado. A
rota é pública só para quem assina (o portão de login a deixa passar: `auth.ROTAS_PUBLICAS`). Repetir o mesmo envio não
grava de novo (marcar o mesmo motivo com a mesma observação não muda nada).

O corpo: {"os", "codigo", "tarefa" (como estão na fila do App: a linha do banco_dados.json ou a OS avulsa do Fracttal),
"motivo" (o id do cadastro; null = tirar o motivo), "obs" (opcional), "tecnico_hmac" (o código do técnico, o mesmo
"Técnico (HMAC)" das rondas), "tecnico_nome"}. O Nexus confere a tarefa (`telas._tarefa_do_app`: na programação
publicada, agenda ou pendentes, ou aberta na Gestão PCM; senão 404), grava a marca como as do Quadro e do painel (origem
"app"; quem marcou pelo código do técnico; o nome e a observação só cifrados) e manda o Fora_da_programacao.json ao
repositório do PCM na hora: o robô tira na rodada seguinte e o App lê do mesmo arquivo.
"""
import hashlib
import hmac
import json
import re
import time

from . import motivos as M

ROTULO_CHAVE = b"nexus:pcm:motivos-app"     # deriva a chave da marca pelo App da NEXUS_PESSOA_HMAC
JANELA_S = 15 * 60
CORPO_MAX = 16 * 1024
_HMAC = re.compile(r"[0-9a-f]{24}")


def chave(config) -> bytes | None:
    base = str(config.get("NEXUS_PESSOA_HMAC") or "").strip()
    return hmac.new(base.encode(), ROTULO_CHAVE, hashlib.sha256).digest() if base else None


def assinatura(k: bytes, ts, corpo: bytes) -> str:
    """HMAC-SHA256 de "<ts>." + o corpo cru (o App calcula igual, com a mesma chave derivada)."""
    return hmac.new(k, f"{int(ts)}.".encode() + corpo, hashlib.sha256).hexdigest()


def conferir(config, ts, assinatura_recebida, corpo: bytes, agora=None) -> tuple[int, dict | str]:
    """(200, o pedido conferido) ou (status HTTP, o porquê). Nada é gravado aqui."""
    k = chave(config)
    if not k:
        return 503, "marca pelo App desligada neste Nexus (sem NEXUS_PESSOA_HMAC)"
    if not corpo or len(corpo) > CORPO_MAX:
        return 400, "corpo vazio ou maior que 16 KB"
    try:
        ts = int(ts)
    except (TypeError, ValueError):
        return 400, "hora do envio (X-Nexus-Ts) fora do formato"
    if abs((agora or time.time()) - ts) > JANELA_S:
        return 401, "hora do envio fora da janela de 15 min"
    if not hmac.compare_digest(assinatura(k, ts, corpo), str(assinatura_recebida or "")):
        return 401, "assinatura não confere"
    try:
        d = json.loads(corpo.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return 400, "o corpo não é JSON"
    if not isinstance(d, dict):
        return 400, "o corpo não é um objeto JSON"
    os_s, tarefa = M.os_de(d.get("os")), str(d.get("tarefa") or "").strip()
    if not os_s.isdigit() or not tarefa:
        return 400, "faltam a OS e a tarefa"
    th = str(d.get("tecnico_hmac") or "").strip().lower()
    if not _HMAC.fullmatch(th):
        return 400, "tecnico_hmac fora do formato (24 caracteres hexadecimais)"
    motivo = d.get("motivo")
    if motivo is not None and not (isinstance(motivo, int) or str(motivo).isdigit()):
        return 400, "motivo = o id do cadastro (número) ou null para tirar"
    return 200, {"os": os_s, "codigo": str(d.get("codigo") or "").strip(), "tarefa": tarefa,
                 "motivo": int(motivo) if motivo is not None else None, "obs": str(d.get("obs") or ""),
                 "tecnico_hmac": th, "tecnico_nome": " ".join(str(d.get("tecnico_nome") or "").split())[:M.PESSOA_MAX]}
