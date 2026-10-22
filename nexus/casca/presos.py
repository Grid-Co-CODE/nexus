"""Pedidos presos: quando o Nexus para de responder, o que cada pedido estava esperando (13/10/2026, Levi: "As vezes o
OS Creator Web fica em um loop infinito, isso é por causa do fractal?").

O caso que criou isto: das 16:50 às 16:53 de 13/10 o Nexus do servidor não respondeu nem o /saude, que não lê nada,
enquanto a plataforma, no mesmo servidor, respondia em 0,2 s; o círculo do OS Creator girava sem fim. Não foi deploy (o
último push do dia foi às 16:02, e o deploy por push entra em 1 a 5 min) nem laço no código: o waitress tem um número
fixo de threads (16 no servidor), e com todas presas esperando alguma coisa o pedido seguinte fica na fila, o /saude
junto. De fora não dá para ver ESPERANDO O QUÊ. Daqui de dentro dá:

- **O registro:** o `ligar` embrulha o `wsgi_app` e anota cada pedido em andamento (método, caminho SEM a query, início,
  thread); a resposta terminada (o `close()` do WSGI) o tira. Os pedidos da pré-carga ficam de fora: ela abre as telas
  pelo `test_client`, numa thread própria, fora das do waitress.
- **A ronda:** uma thread olha a cada PASSO_S. Pedido com mais de LIMITE_S é PRESO: a pilha da thread dele
  (`sys._current_frames`) diz onde ele está, e o rótulo resume em quem (o Fracttal do OS Creator, o do Campo, as fotos,
  ou o arquivo e a função nossos) e como (esperando a rede, outra thread, o banco, em pausa, ou trabalhando). Vai ao log
  (WARNING) quando o pedido prende e quando o rótulo muda.
- **O episódio:** do 1º preso até FIM_S sem nenhum. Guarda o começo (o início do pedido preso mais antigo), o fim, o
  máximo de presos juntos, se a fila encheu (todas as threads ocupadas) e cada pedido preso (caminho, quanto esperou e
  onde). Os últimos GUARDAR ficam na memória e em `dados/casca/pedidos_presos.json`, gravado também DURANTE o episódio:
  o processo reiniciado no meio dele não o perde, e ele volta marcado como "cortado".
- **Quem vê:** o administrador, no cartão "Versão no ar" do Início (`cartao`).

Quem liga é o servir.py e o app.py, nunca o create_app: os testes não ligam thread nenhuma.
"""
import json
import logging
import os
import sys
import threading
import time
import traceback
from collections import Counter
from datetime import datetime, timedelta, timezone
from itertools import count
from pathlib import Path

from werkzeug.wsgi import ClosingIterator

log = logging.getLogger(__name__)

_BRT = timezone(timedelta(hours=-3))
CHAVE = "nexus_presos"
LIMITE_S = 30        # a tela mais pesada do Nexus abre em ~11 s com tudo frio (pre_carga.py): 30 s é preso
PASSO_S = 5
FIM_S = 15           # 15 s sem nenhum preso fecha o episódio
GUARDAR = 30
MAX_PEDIDOS = 40     # por episódio, os que esperaram mais
DIA_S = 24 * 3600
_PRE_CARGA = "HTTP_X_NEXUS_PRE_CARGA"     # o cabeçalho da pré-carga (auth/pre_carga.CABECALHO)
def _norm(caminho: str) -> str:
    return os.path.normcase(caminho).replace("\\", "/")


_RAIZ = _norm(str(Path(__file__).resolve().parents[2])) + "/"

# quem: a linha NOSSA mais de dentro da pilha (o 1º trecho que casar)
_QUEM = (
    ("/os_creator/api.py", "Fracttal (OS Creator)"),
    ("/os_creator/", "OS Creator"),
    ("/nexus/campo/fracttal.py", "Fracttal (Campo)"),
    ("/nexus/campo/ronda_fotos.py", "fotos das rondas"),
    ("/nexus/auth/fracttal.py", "login do Fracttal"),
)


def _arq(f) -> str:
    return _norm(f.filename)


def _nossa(f) -> bool:
    arq = _arq(f)
    # no servidor o .venv mora dentro da pasta do Nexus (/opt/nexus/.venv): os pacotes dele não são linha nossa
    return arq.startswith(_RAIZ) and "/site-packages/" not in arq


def _como(f) -> str:
    """Como a linha mais de dentro da pilha espera: a rede, outra thread, o banco, uma pausa, ou está trabalhando."""
    arq, linha = _arq(f), f.line or ""
    if "sleep(" in linha:
        return "em pausa"
    if (arq.endswith(("/ssl.py", "/socket.py", "/selectors.py", "/http/client.py"))
            or "/urllib3/" in arq or "/requests/" in arq):
        return "esperando a rede"
    if arq.endswith(("/threading.py", "/queue.py")) or "/concurrent/futures/" in arq:
        return "esperando outra thread"
    if "/psycopg" in arq or "/pg8000/" in arq or "/sqlalchemy/" in arq or ".execute(" in linha:
        return "esperando o banco"
    return "trabalhando"


def pilha(quadro) -> traceback.StackSummary:
    """A pilha de `quadro`, de fora para dentro, como o `traceback.extract_stack`, mas SEM ler no disco o código de cada
    linha (22/10/2026): o rótulo só usa o texto da linha de dentro (`_como`), lido quando pedido. Raio-X das 08:57 de 22/10,
    com a máquina em 3,6 GB de swap: a lista de threads ficou 1 min 15 s presa lendo, para cada thread, o código de todas
    as ~40 linhas da pilha (o linecache vai ao disco)."""
    s = traceback.StackSummary.extract(traceback.walk_stack(quadro), lookup_lines=False)
    s.reverse()
    return s


def rotulo(pilha) -> dict:
    """{"quem", "como", "onde"} de uma pilha (`pilha` ou `traceback.extract_stack`, de fora para dentro)."""
    if not pilha:
        return {"quem": "?", "como": "?", "onde": ""}
    nossa = next((f for f in reversed(pilha) if _nossa(f)), None)
    quem, onde = "?", ""
    if nossa is not None:
        rel = _arq(nossa)[len(_RAIZ):]
        onde = f"{rel}:{nossa.lineno} {nossa.name}"
        quem = next((r for trecho, r in _QUEM if trecho in "/" + rel), f"{rel}:{nossa.name}")
    return {"quem": quem, "como": _como(pilha[-1]), "onde": onde}


def _duracao(s: float) -> str:
    s = int(round(max(0.0, s)))
    if s < 60:
        return f"{s} s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} min" + (f" {s} s" if s else "")
    h, m = divmod(m, 60)
    return f"{h} h" + (f" {m} min" if m else "")


class _Estado:
    def __init__(self, threads: int, arquivo: Path | None):
        self.threads, self.arquivo = int(threads or 0), arquivo
        self.trava = threading.Lock()
        self.em_curso: dict = {}           # seq -> pedido
        self.episodio: dict | None = None  # o aberto
        self.historico: list = []          # os fechados, do mais velho ao mais novo
        self._seq = count(1)
        self._ultimo_preso = 0.0           # monotonic
        self._gravado_em = 0.0

    # ── o registro ──────────────────────────────────────────────────────────────────────────────────────────────
    def entrar(self, environ) -> int:
        seq = next(self._seq)
        p = {"metodo": environ.get("REQUEST_METHOD", ""), "caminho": environ.get("PATH_INFO", ""),
             "inicio": time.monotonic(), "inicio_epoca": time.time(), "thread": threading.get_ident()}
        with self.trava:
            self.em_curso[seq] = p
        return seq

    def sair(self, seq: int) -> None:
        with self.trava:
            p = self.em_curso.pop(seq, None)
            if p is not None and p.get("preso") and self.episodio is not None:
                reg = self.episodio["pedidos"].get(seq)
                if reg is not None:
                    reg["espera_s"] = round(time.monotonic() - p["inicio"], 1)
                    reg["terminou"] = True
                self._ultimo_preso = time.monotonic()
                self.episodio["fim_visto"] = time.time()

    # ── a ronda ─────────────────────────────────────────────────────────────────────────────────────────────────
    def olhar(self, agora: float | None = None) -> None:
        agora = time.monotonic() if agora is None else agora
        with self.trava:
            ocupadas = len(self.em_curso)
            presos = [(seq, p) for seq, p in self.em_curso.items() if agora - p["inicio"] >= LIMITE_S]
        avisos, rotulos = [], {}
        if presos:
            pilhas = sys._current_frames()
            for seq, p in presos:
                quadro = pilhas.get(p["thread"])
                rotulos[seq] = rotulo(pilha(quadro) if quadro is not None else [])
        with self.trava:
            for seq, p in presos:
                r = rotulos[seq]
                if (r["quem"], r["como"]) != (p.get("quem"), p.get("como")):
                    avisos.append((p, r, agora - p["inicio"]))
                p.update(r, preso=True)
            ep = self.episodio
            if presos:
                if ep is None:
                    ep = self.episodio = {"inicio": min(p["inicio_epoca"] for _s, p in presos), "fim": None,
                                          "fim_visto": time.time(), "max_presos": 0, "max_ocupadas": 0,
                                          "threads": self.threads, "fila_cheia": False, "pedidos": {}}
                ep["max_presos"] = max(ep["max_presos"], len(presos))
                ep["max_ocupadas"] = max(ep["max_ocupadas"], ocupadas)
                ep["fila_cheia"] = ep["fila_cheia"] or bool(self.threads and ocupadas >= self.threads)
                ep["fim_visto"] = time.time()
                for seq, p in presos:
                    reg = ep["pedidos"].setdefault(seq, {"metodo": p["metodo"], "caminho": p["caminho"],
                                                         "terminou": False})
                    reg.update(quem=p["quem"], como=p["como"], onde=p["onde"],
                               espera_s=round(agora - p["inicio"], 1))
                self._ultimo_preso = agora
            fechar = ep is not None and not presos and agora - self._ultimo_preso >= FIM_S
            if fechar:
                ep["fim"] = ep["fim_visto"]
                self.historico.append(self._congelado(ep))
                del self.historico[:-GUARDAR]
                self.episodio = None
        for p, r, espera in avisos:
            log.warning("Pedido preso há %s: %s %s - %s, %s (%s)", _duracao(espera), p["metodo"], p["caminho"],
                        r["quem"], r["como"], r["onde"] or "sem linha nossa na pilha")
        if fechar:
            log.warning("Fim do travamento: %s", self.resumo(self.historico[-1]))
            self.gravar()
        elif presos and time.time() - self._gravado_em >= 30:
            self.gravar()                  # durante: o restart no meio não perde o episódio

    @staticmethod
    def _congelado(ep: dict) -> dict:
        pedidos = sorted(ep["pedidos"].values(), key=lambda r: -r.get("espera_s", 0))[:MAX_PEDIDOS]
        return {k: v for k, v in ep.items() if k != "pedidos"} | {"pedidos": [dict(r) for r in pedidos]}

    def episodios(self) -> list:
        """Os guardados mais o aberto (com "fim": None), do mais velho ao mais novo."""
        with self.trava:
            eps = [dict(x) for x in self.historico]
            if self.episodio is not None:
                eps.append(self._congelado(self.episodio))
        return eps

    @staticmethod
    def resumo(ep: dict) -> str:
        quem = Counter(f"{r.get('quem')}, {r.get('como')}" for r in ep.get("pedidos") or [])
        fila = (f"; fila cheia ({ep.get('max_ocupadas')} de {ep.get('threads')} threads)" if ep.get("fila_cheia")
                else "")
        mais = "; ".join(f"{n}x {q}" for q, n in quem.most_common(3))
        return (f"{_duracao((ep.get('fim') or time.time()) - ep['inicio'])}, até {ep.get('max_presos')} presos "
                f"juntos{fila}; {mais}")

    # ── o disco ─────────────────────────────────────────────────────────────────────────────────────────────────
    def gravar(self) -> None:
        if self.arquivo is None:
            return
        self._gravado_em = time.time()
        try:
            dados = {"gravado_em": self._gravado_em, "episodios": self.episodios()}
            self.arquivo.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.arquivo.with_name(self.arquivo.name + ".tmp")
            tmp.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.arquivo)
        except OSError as ex:
            log.warning("Pedidos presos: não gravei %s (%s)", self.arquivo, ex)

    def carregar(self) -> None:
        """Os episódios de antes do boot. O que estava aberto quando o processo caiu volta fechado e "cortado"."""
        if self.arquivo is None or not self.arquivo.exists():
            return
        try:
            dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError) as ex:
            log.warning("Pedidos presos: não li %s (%s)", self.arquivo, ex)
            return
        eps = []
        for ep in dados.get("episodios") or []:
            if not isinstance(ep, dict) or not ep.get("inicio"):
                continue
            if ep.get("fim") is None:
                ep = dict(ep, fim=ep.get("fim_visto") or dados.get("gravado_em") or ep["inicio"], cortado=True)
            eps.append(ep)
        with self.trava:
            self.historico = eps[-GUARDAR:]


class _Registro:
    """O middleware: anota o pedido ao entrar e tira quando a resposta termina (o close() do WSGI) ou quebra."""

    def __init__(self, wsgi, estado: _Estado):
        self.wsgi, self.estado = wsgi, estado

    def __call__(self, environ, start_response):
        if environ.get(_PRE_CARGA):
            return self.wsgi(environ, start_response)
        seq = self.estado.entrar(environ)
        try:
            resposta = self.wsgi(environ, start_response)
        except BaseException:
            self.estado.sair(seq)
            raise
        return ClosingIterator(resposta, [lambda: self.estado.sair(seq)])


def _ronda(estado: _Estado) -> None:
    while True:
        time.sleep(PASSO_S)
        try:
            estado.olhar()
        except Exception:       # noqa: BLE001 — a ronda nunca derruba o Nexus
            log.exception("Pedidos presos: a ronda falhou")


def ligar(app, threads: int) -> _Estado:
    """Embrulha o wsgi_app, lê os episódios do disco e liga a ronda. `threads` = as do waitress (16 no servidor)."""
    from ..cadastro.ligacoes import pasta_dados
    try:
        arquivo = pasta_dados(app.config) / "casca" / "pedidos_presos.json"
    except RuntimeError:
        arquivo = None
    estado = _Estado(threads, arquivo)
    estado.carregar()
    app.extensions[CHAVE] = estado
    app.wsgi_app = _Registro(app.wsgi_app, estado)
    threading.Thread(target=_ronda, args=(estado,), daemon=True, name="nexus-presos").start()
    return estado


def _hora(epoca: float, agora: float) -> str:
    d, hoje = datetime.fromtimestamp(epoca, _BRT), datetime.fromtimestamp(agora, _BRT)
    return d.strftime("%H:%M") if d.date() == hoje.date() else d.strftime("%d/%m %H:%M")


def _vezes(n: int) -> str:
    return "1 vez" if n == 1 else f"{n} vezes"


def cartao(app) -> dict | None:
    """O que o cartão "Versão no ar" do Início diz ao administrador sobre as últimas 24 h. TRAVOU = a fila encheu (todas
    as threads ocupadas: ninguém mais era atendido); sem isso, foi um pedido preso, que só a pessoa dele sentiu. None =
    desligado (os testes, a vitrine estática)."""
    estado = app.extensions.get(CHAVE)
    if estado is None:
        return None
    agora = time.time()
    eps = [x for x in estado.episodios() if (x.get("fim") or agora) >= agora - DIA_S]
    if not eps:
        return {"classe": "ok", "rotulo": "Nenhum pedido preso em 24 h", "detalhe": "", "titulo": ""}
    ult = eps[-1]
    if ult.get("fim") is None and all(r.get("terminou") for r in ult.get("pedidos") or []):
        # os presos já soltaram e o episódio só espera os 15 s para fechar: não é "agora"
        ult["fim"] = ult.get("fim_visto") or agora
    aberto, travou = ult.get("fim") is None, ult.get("fila_cheia")
    travamentos = sum(1 for x in eps if x.get("fila_cheia"))
    if aberto:
        rot = "Travado agora" if travou else "Pedido preso agora"
    elif travamentos:
        rot = f"Travou {_vezes(travamentos)} em 24 h"
    else:
        rot = f"Pedido preso {_vezes(len(eps))} em 24 h"
    classe = "critico" if aberto or travamentos else "alerta"
    dur = _duracao((ult.get("fim") or agora) - ult["inicio"])
    if aberto:
        detalhe = f"Começou às {_hora(ult['inicio'], agora)} (há {dur})"
    else:
        detalhe = f"O último começou às {_hora(ult['inicio'], agora)} e durou {dur}"
    n = int(ult.get("max_presos") or 0)
    detalhe += ": 1 pedido preso" if n == 1 else f": até {n} pedidos presos juntos"
    if travou:
        detalhe += f", com as {ult.get('threads')} threads ocupadas"
    pedidos = ult.get("pedidos") or []
    mais = Counter(f"{r.get('quem')}, {r.get('como')}" for r in pedidos).most_common(1)
    if mais:
        onde, qtos = mais[0]
        detalhe += (f"; em {onde}" if len(pedidos) == 1 else
                    f"; {'todos' if qtos == len(pedidos) else f'{qtos} de {len(pedidos)}'} em {onde}")
    if ult.get("cortado"):
        detalhe += "; acabou com o Nexus reiniciando"
    titulo = "; ".join(f"{r.get('metodo')} {r.get('caminho')} ({_duracao(r.get('espera_s', 0))}, "
                       f"{r.get('onde') or r.get('quem')})" for r in pedidos[:6])
    return {"classe": classe, "rotulo": rot, "detalhe": detalhe + ".", "titulo": titulo}
