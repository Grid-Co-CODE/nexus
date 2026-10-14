"""Raio-X do Nexus: o que o processo está fazendo AGORA (14/10/2026, só administrador, fora do menu).

Levi, 14/10/2026 às 09:20: "O nexus está muito lento, carregando bem devagar". Medido de fora no mesmo minuto: o /saude
(que não lê nada) levou de 0,5 a 17 s e chegou a estourar 60 s, enquanto a plataforma, no mesmo servidor, respondia em
0,2 s e a API do banco em 0,2 a 0,9 s: o gargalo era o processo do Nexus, e de fora não dá para ver esperando o quê. O
cartão dos pedidos presos saiu do Início a pedido do Levi (13/10); o log do servidor é da T.I. Esta página junta, num
clique do administrador:

- os pedidos em andamento (das threads do waitress, pelo registro do `casca/presos.py`): caminho, há quanto tempo e onde
  cada um está (o mesmo rótulo dos pedidos presos: Fracttal, banco, fotos, ou o arquivo e a função nossos);
- as outras threads do processo (pré-carga, laços de dados, Campo) e o que cada uma faz: "trabalhando" é processador,
  que no Python segura as outras (o GIL);
- o processador do processo medido em 1 s e a carga da máquina (Linux), e os travamentos das últimas 24 h.

Nada é gravado nem vai à rede; a pilha só sai como rótulo (arquivo, linha e função), nunca com dados.
"""
import os
import sys
import threading
import time
import traceback

from flask import current_app, render_template, session

from . import presos as P


def _threads(estado) -> tuple[list, list]:
    """(pedidos em andamento, outras threads), cada um com o rótulo de onde está agora."""
    pilhas = sys._current_frames()
    nomes = {t.ident: t.name for t in threading.enumerate()}
    agora = time.monotonic()
    em_curso = {}
    if estado is not None:
        with estado.trava:
            em_curso = {seq: dict(p) for seq, p in estado.em_curso.items()}
    pedidos, das_requisicoes = [], set()
    for p in sorted(em_curso.values(), key=lambda p: p["inicio"]):
        das_requisicoes.add(p["thread"])
        quadro = pilhas.get(p["thread"])
        r = P.rotulo(traceback.extract_stack(quadro) if quadro is not None else [])
        pedidos.append({"metodo": p["metodo"], "caminho": p["caminho"], "ha": P._duracao(agora - p["inicio"]),
                        "ha_s": agora - p["inicio"], **r})
    eu = threading.get_ident()
    outras = []
    for ident, quadro in pilhas.items():
        if ident in das_requisicoes or ident == eu:
            continue
        nome = nomes.get(ident, f"thread {ident}")
        # as do waitress com pedido já estão na lista de cima; as outras dele estão livres; a principal só escuta a porta
        if nome.startswith("waitress-") or nome == "MainThread":
            continue
        outras.append({"nome": nome, **P.rotulo(traceback.extract_stack(quadro))})
    outras.sort(key=lambda x: (x["como"] != "trabalhando", x["nome"]))
    return pedidos, outras


def _processador(janela_s: float = 1.0) -> dict:
    """O processador deste processo numa janela curta (100% = um núcleo inteiro) e a carga da máquina (só Linux)."""
    t0, c0 = time.monotonic(), time.process_time()
    time.sleep(janela_s)
    pct = 100.0 * (time.process_time() - c0) / max(time.monotonic() - t0, 1e-6)
    carga = os.getloadavg() if hasattr(os, "getloadavg") else None
    return {"pct": round(pct), "nucleos": os.cpu_count(), "carga": [round(x, 2) for x in carga] if carga else None}


def registrar_raio_x(bp) -> None:
    @bp.route("/raio-x")
    def raio_x():
        if not session.get("admin"):
            return render_template("cadastro/sem_permissao.html", titulo="Raio-X do Nexus", eyebrow="Base · Raio-X",
                                   area="O Raio-X do Nexus", email=""), 403
        app = current_app._get_current_object()
        estado = app.extensions.get(P.CHAVE)
        pedidos, outras = _threads(estado)
        teto = app.extensions.get("nexus_teto_os")
        teto = teto.estado() if teto is not None else None
        if teto and teto["ultimo_recusado"]:
            teto["ultimo_txt"] = time.strftime("%d/%m %H:%M", time.localtime(teto["ultimo_recusado"]))
        return render_template("raio_x.html", pedidos=pedidos, outras=outras, ligado=estado is not None, teto=teto,
                               threads=getattr(estado, "threads", 0), cpu=_processador(),
                               travamentos=P.cartao(app) if estado is not None else None,
                               quando=time.strftime("%d/%m/%Y %H:%M:%S"))
