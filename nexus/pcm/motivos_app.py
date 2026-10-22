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

O pedido do App não segura o Nexus (22/10/2026). Das 13:51 às 14:08, com o servidor no swap, cada gravação no livro
levava minutos; o servidor do App desiste em 20 s e manda de novo, e 7 justificativas viraram 46 envios, cada um numa
das 8 threads do Nexus esperando a vez de gravar (o Raio-X das 14:02: 6 de 8 threads nesta rota), e o Nexus parou para
todo mundo. Agora (`entregar`) a justificativa entra numa FILA na 1ª tentativa e quem grava é um gravador por trás, que
leva as que estão na fila juntas, numa leitura e numa gravação do livro (`motivos.marcar_lote`). O pedido espera a
resposta até APP_ESPERA_S (o App desiste em 20 s) e, com APP_ESPERANDO_MAX esperando, responde 503 na hora; a
justificativa é gravada assim mesmo, e o reenvio (o mesmo envio de novo) não entra de novo na fila: espera a mesma ou
recebe a resposta guardada dela. A resposta guardada e o `repetida` do `motivos.marcar` (o que vale depois de um
reinício) fazem o reenvio voltar "gravou: true": naquele dia as 7 foram gravadas pelo envio que o App já tinha dado
por perdido, os reenvios voltaram "sem mudança", e o App, que só escreve a nota e a etiqueta no Fracttal com "gravou:
true", não escreveu nenhuma (a linha que já está na nota, ele não repete).
"""
import hashlib
import hmac
import json
import logging
import re
import threading
import time

from . import motivos as M

ROTULO_CHAVE = b"nexus:pcm:motivos-app"     # deriva a chave da marca pelo App da NEXUS_PESSOA_HMAC
JANELA_S = 15 * 60
CORPO_MAX = 16 * 1024
_HMAC = re.compile(r"[0-9a-f]{24}")
APP_ESPERA_S = 15            # o servidor do App desiste em 20 s (`requests.post(..., timeout=20)`): responde antes
APP_ESPERANDO_MAX = 2        # pedidos esperando a resposta: das 8 threads do Nexus, o App nunca segura mais que duas
LOTE_MAX = 50
FILA_MAX = 500
GUARDA_S = 30 * 60           # a resposta que não chegou ao App fica guardada para o reenvio
NA_FILA = {"ok": False, "erro": "a justificativa está na fila do Nexus (o banco está lento) e vai ser gravada; o App "
                                "tenta de novo"}
_COND = threading.Condition()
_FILA: list = []             # os pedidos esperando o gravador, na ordem de chegada
_POR_CHAVE: dict = {}        # a justificativa -> o pedido dela (na fila, gravando, ou gravado e a resposta não entregue)
_ESTADO = {"esperando": 0, "gravando": 0, "thread": None}
log = logging.getLogger(__name__)


class _Pedido:
    def __init__(self, app, d: dict, processar):
        self.app, self.d, self.processar = app, d, processar
        self.pronto = threading.Event()
        self.resposta: tuple | None = None      # (corpo, status)
        self.fim = 0.0


def _chave(d: dict) -> tuple:
    """A mesma justificativa: OS, ativo, tarefa, motivo, observação e técnico (o reenvio do App manda o corpo igual)."""
    return d["os"], M.canon(d["codigo"]), M.norm(d["tarefa"]), d["motivo"], d["obs"], d["tecnico_hmac"]


def entregar(app, d: dict, processar) -> tuple[dict, int]:
    """(corpo, status) da justificativa `d` (o pedido já conferido): entra na fila do gravador, ou junta-se à mesma
    que já está lá, e este pedido espera a resposta até APP_ESPERA_S quando há vaga para esperar; senão, ou passado
    o prazo, 503 (`NA_FILA`), e ela é gravada assim mesmo. `processar(cfg, [d, ...]) -> [(corpo, status), ...]` grava
    um lote: a rota (`telas._motivos_do_app`)."""
    k = _chave(d)
    with _COND:
        _esquecer(time.monotonic())
        p = _POR_CHAVE.get(k)
        if p is not None and p.app is app and p.pronto.is_set():
            del _POR_CHAVE[k]                   # a resposta que não chegou ao App: vai agora
            return p.resposta
        if p is None or p.app is not app:
            if len(_FILA) >= FILA_MAX:
                return {"ok": False, "erro": "a fila de justificativas do Nexus está cheia; o App tenta de novo"}, 503
            p = _Pedido(app, d, processar)
            _FILA.append(p)
            _POR_CHAVE[k] = p
            _ligar_gravador()
            _COND.notify_all()
        if _ESTADO["esperando"] >= APP_ESPERANDO_MAX:
            return NA_FILA, 503
        _ESTADO["esperando"] += 1
    try:
        pronto = p.pronto.wait(APP_ESPERA_S)
    finally:
        with _COND:
            _ESTADO["esperando"] -= 1
    if not pronto:
        return NA_FILA, 503
    with _COND:
        if _POR_CHAVE.get(k) is p:
            del _POR_CHAVE[k]                   # entregue
    return p.resposta


def _esquecer(agora: float) -> None:
    for k, p in list(_POR_CHAVE.items()):
        if p.pronto.is_set() and agora - p.fim > GUARDA_S:
            del _POR_CHAVE[k]


def _ligar_gravador() -> None:
    t = _ESTADO["thread"]
    if t is None or not t.is_alive():
        t = threading.Thread(target=_gravador, name="nexus-motivos-do-app", daemon=True)
        _ESTADO["thread"] = t
        t.start()


def _gravador() -> None:
    """Grava a fila em lotes: as que esperam juntas, numa leitura e numa gravação do livro."""
    while True:
        with _COND:
            while not _FILA:
                _COND.wait()
            p0 = _FILA[0]
            lote = [p for p in _FILA if p.app is p0.app and p.processar is p0.processar][:LOTE_MAX]
            for p in lote:
                _FILA.remove(p)
            _ESTADO["gravando"] += 1
        try:
            with p0.app.app_context():
                respostas = p0.processar(p0.app.config, [p.d for p in lote])
        except Exception as ex:      # noqa: BLE001 — o gravador não para; o App tenta de novo
            log.exception("Motivos do App: o lote de %d não foi gravado", len(lote))
            respostas = [({"ok": False, "erro": f"o Nexus não gravou ({type(ex).__name__}); o App tenta de novo"}, 503)
                         for _ in lote]
        sem = {"ok": False, "erro": "o Nexus não gravou (o lote voltou sem esta); o App tenta de novo"}, 503
        respostas = list(respostas)[:len(lote)]
        respostas += [sem] * (len(lote) - len(respostas))       # sem resposta, ela ficaria "em voo" para sempre
        with _COND:
            fim = time.monotonic()
            for p, r in zip(lote, respostas):
                p.resposta, p.fim = r, fim
                if r[1] != 200 and _POR_CHAVE.get(_chave(p.d)) is p:
                    del _POR_CHAVE[_chave(p.d)]          # só a resposta boa fica guardada: o resto, o reenvio refaz
                p.pronto.set()
            _ESTADO["gravando"] -= 1
            _COND.notify_all()


def na_fila() -> int:
    """Quantas esperam o gravador ou estão sendo gravadas agora."""
    with _COND:
        return len(_FILA) + _ESTADO["gravando"]


def esperando() -> int:
    return _ESTADO["esperando"]


def esperar_a_fila(prazo: float = 10) -> bool:
    """Até a fila esvaziar (os testes e a cópia de prova)."""
    fim = time.monotonic() + prazo
    with _COND:
        while _FILA or _ESTADO["gravando"]:
            resta = fim - time.monotonic()
            if resta <= 0:
                return False
            _COND.wait(resta)
    return True


def esquecer() -> None:
    """Esquece as respostas guardadas (os testes: cada um com o seu app)."""
    with _COND:
        for k, p in list(_POR_CHAVE.items()):
            if p.pronto.is_set():
                del _POR_CHAVE[k]


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
