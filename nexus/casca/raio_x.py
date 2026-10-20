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
- o processador do processo medido em 1 s e a carga da máquina (Linux), e os travamentos das últimas 24 h;
- a máquina pelo /proc do Linux (20/10/2026): o processador dela inteira e o tempo esperando o disco na mesma janela de
  1 s, a memória livre, o swap em uso e se está trocando agora, o quanto o Nexus ocupa e, havendo a PSI do kernel, o
  tempo com algo parado esperando memória ou disco. O caso: no Raio-X das 10:08 de 20/10 o `GET /os/` estava há 18 s
  numa cópia que leva 17 ms, com o Nexus a 13% do processador e a carga em 2,5 a 3,9; a carga do Linux soma quem espera
  o disco, e a página não dizia qual era o gargalo. São só leituras de arquivos do /proc, quando o Raio-X abre.

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


def _ler_proc(nome: str) -> str:
    """O texto de /proc/<nome> (Linux), ou "" onde não há (Windows, permissão, kernel sem a PSI)."""
    try:
        with open("/proc/" + nome, encoding="ascii", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _cpu_da_maquina(texto: str):
    """(total, ocioso, esperando o disco) somados de todos os núcleos, da linha "cpu" do /proc/stat; None sem ela."""
    for linha in texto.splitlines():
        if linha.startswith("cpu "):
            try:
                v = [int(x) for x in linha.split()[1:9]]      # user nice system idle iowait irq softirq steal
            except ValueError:
                return None
            return (sum(v), v[3], v[4]) if len(v) >= 5 else None
    return None


def _kb(texto: str, *campos) -> dict:
    """{campo: kB} das linhas "Campo:   123 kB" (/proc/meminfo, /proc/self/status)."""
    out = {}
    for linha in texto.splitlines():
        nome, _, resto = linha.partition(":")
        if nome in campos:
            try:
                out[nome] = int(resto.split()[0])
            except (IndexError, ValueError):
                pass
    return out


def _vmstat(texto: str) -> dict:
    """As páginas que entraram e saíram do swap desde o boot (/proc/vmstat)."""
    out = {}
    for linha in texto.splitlines():
        par = linha.split()
        if len(par) == 2 and par[0] in ("pswpin", "pswpout") and par[1].isdigit():
            out[par[0]] = int(par[1])
    return out


def _pressao(texto: str):
    """O "some avg10" da PSI: % do tempo, nos últimos 10 s, com algum processo parado esperando aquilo. None sem ela."""
    for linha in texto.splitlines():
        if linha.startswith("some "):
            for campo in linha.split()[1:]:
                k, _, v = campo.partition("=")
                if k == "avg10":
                    try:
                        return float(v)
                    except ValueError:
                        return None
    return None


def _decimal(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def _troca_mb_s(v0: dict, v1: dict, janela_s: float) -> str:
    """O swap trocado na janela, em MB/s (páginas de 4 KB); "0" sem troca."""
    paginas = sum(max(0, v1.get(k, 0) - v0.get(k, 0)) for k in ("pswpin", "pswpout"))
    return _decimal(paginas * 4 / 1024 / max(janela_s, 1e-6)) if paginas else "0"


def _maquina(s0, s1, v0: dict, v1: dict, janela_s: float):
    """A máquina na janela do `_processador`, pelo /proc; None fora do Linux."""
    mem = _kb(_ler_proc("meminfo"), "MemTotal", "MemAvailable", "SwapTotal", "SwapFree")
    if not s0 or not s1 or not mem.get("MemTotal"):
        return None
    total = max(s1[0] - s0[0], 1)
    ocioso, disco = s1[1] - s0[1], s1[2] - s0[2]
    eu = _kb(_ler_proc("self/status"), "VmRSS", "VmSwap")
    gb = 1024 * 1024
    swap_total = mem.get("SwapTotal", 0)
    return {"ocupado": round(100.0 * max(0, total - ocioso - disco) / total), "disco": round(100.0 * disco / total),
            "livre_gb": _decimal(mem.get("MemAvailable", 0) / gb), "total_gb": _decimal(mem["MemTotal"] / gb),
            "tem_swap": swap_total > 0, "swap_gb": _decimal(max(0, swap_total - mem.get("SwapFree", 0)) / gb),
            "trocando_mb_s": _troca_mb_s(v0, v1, janela_s),
            "nexus_mb": round(eu.get("VmRSS", 0) / 1024), "nexus_swap_mb": round(eu.get("VmSwap", 0) / 1024),
            "pressao_mem": _pressao(_ler_proc("pressure/memory")), "pressao_io": _pressao(_ler_proc("pressure/io"))}


def _processador(janela_s: float = 1.0) -> dict:
    """O processador deste processo numa janela curta (100% = um núcleo inteiro), a carga da máquina e, na mesma janela,
    a máquina pelo /proc (`_maquina`; só Linux)."""
    t0, c0 = time.monotonic(), time.process_time()
    s0, v0 = _cpu_da_maquina(_ler_proc("stat")), _vmstat(_ler_proc("vmstat"))
    time.sleep(janela_s)
    s1, v1 = _cpu_da_maquina(_ler_proc("stat")), _vmstat(_ler_proc("vmstat"))
    janela = max(time.monotonic() - t0, 1e-6)
    pct = 100.0 * (time.process_time() - c0) / janela
    carga = os.getloadavg() if hasattr(os, "getloadavg") else None
    return {"pct": round(pct), "nucleos": os.cpu_count(), "carga": [round(x, 2) for x in carga] if carga else None,
            "maquina": _maquina(s0, s1, v0, v1, janela)}


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
