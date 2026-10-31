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
- quem ocupa a memória da máquina, somado por programa (`_quem_ocupa`, 20/10/2026). Raio-X das 14:17: 0,2 GB livres de
  7,1 GB e 3,2 GB no swap, com o Nexus em só 690 MB; o PDF das 13:45 ficou 1 min "trabalhando" no desenho do logo, e
  daqui não se via de quem eram os outros ~6 GB.

- o uso do OS Creator nos últimos 7 dias (`montar_uso_os`, 31/10/2026, etapa 0 do canto central): as telas mais pedidas (os
  cliques e o que a tela pede sozinha, separados, com a mediana e o p95), os cliques por hora do dia, os pedidos ao
  Fracttal por hora com o pico por minuto ao lado da cota de 200 e o corte por setor. De ontem para trás vem dos livros
  do mês no banco (a leitura, numa thread à parte e guardada 10 min, `_uso_do_banco`); o que ainda não foi às 03:45 vem do
  pendente no disco do servidor (`uso_os.linhas_pendentes`) e a hora aberta, da memória;
- na mesma seção, o canto central do OS Creator (`_secao_canto_central`, item 0 da 3.1+3.2): o estado dos ativos centrais
  (o catálogo, o leitor do servidor, a paridade do REST, as descrições cortadas da foto, o disco), só com contagens, datas e
  ids, para conferir de fora a 1ª noite do leitor.

Nada é gravado nem vai à rede (a leitura do uso no banco é a exceção, por trás, com prazo); a pilha só sai como rótulo
(arquivo, linha e função), nunca com dados.
"""
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import current_app, render_template, session

from . import presos as P

log = logging.getLogger(__name__)


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
        r = P.rotulo(P.pilha(quadro) if quadro is not None else [])
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
        outras.append({"nome": nome, **P.rotulo(P.pilha(quadro))})
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
            "pressao_mem": _pressao(_ler_proc("pressure/memory")), "pressao_io": _pressao(_ler_proc("pressure/io")),
            "teto": _teto_nexus(), "teto_deploy": _teto_do_deploy()}


def _ler_arquivo(caminho: str):
    """O texto de um arquivo do sistema (o cgroup em /sys), ou None onde não há."""
    try:
        with open(caminho, encoding="ascii", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return None


def _mb_do_teto(v):
    """O valor de um arquivo de teto do cgroup em MB; None = sem teto ("max" no v2, o número gigante do v1)."""
    if v is None or v == "max" or not v.isdigit() or int(v) >= 1 << 60:
        return None
    return round(int(v) / (1024 * 1024))


def _teto_nexus():
    """O teto de memória que o serviço ou o contêiner põe no Nexus (o cgroup do próprio processo); None fora do Linux.

    O caso (29/10/2026): o Nexus ficava SEMPRE com ~700 MB na memória (662, 689, 705, 707 e 710 MB em cinco leituras de
    dois dias) e o resto no swap, 1,5 a 2,2 GB, com 5,7 a 7 GB livres na máquina: o Linux não troca assim com memória
    sobrando, a não ser que o grupo do processo tenha teto (`MemoryHigh`/`MemoryMax` do systemd, o `--memory` do
    Docker). E o Levi não tem acesso ao servidor: o Raio-X diz o teto, quantas vezes o Linux apertou o Nexus por causa
    dele e onde ele está posto. Só leitura de /proc e /sys."""
    grupo = _ler_proc("self/cgroup")
    if not grupo:
        return None
    v2 = next((l[3:] for l in grupo.splitlines() if l.startswith("0::")), None)
    v1 = next((l.split(":", 2)[2] for l in grupo.splitlines() if l.split(":")[1:2] == ["memory"]), None)
    out = {"onde": v2 or v1 or "/", "conteiner": os.path.exists("/.dockerenv"), "max_mb": None, "high_mb": None,
           "swap_max_mb": None, "apertos": None, "no_teto": None, "oom": None}
    if v2 is not None:
        base = next((b for b in (f"/sys/fs/cgroup{v2.rstrip('/')}", "/sys/fs/cgroup")
                     if _ler_arquivo(f"{b}/memory.max") is not None), None)
        if base is None:
            return out
        out.update(max_mb=_mb_do_teto(_ler_arquivo(f"{base}/memory.max")),
                   high_mb=_mb_do_teto(_ler_arquivo(f"{base}/memory.high")),
                   swap_max_mb=_mb_do_teto(_ler_arquivo(f"{base}/memory.swap.max")))
        ev = {}
        for linha in (_ler_arquivo(f"{base}/memory.events") or "").splitlines():
            par = linha.split()
            if len(par) == 2 and par[1].isdigit():
                ev[par[0]] = int(par[1])
        out.update(apertos=ev.get("high"), no_teto=ev.get("max"), oom=ev.get("oom_kill"))
    elif v1 is not None:
        base = next((b for b in (f"/sys/fs/cgroup/memory{v1.rstrip('/')}", "/sys/fs/cgroup/memory")
                     if _ler_arquivo(f"{b}/memory.limit_in_bytes") is not None), None)
        if base is not None:
            out["max_mb"] = _mb_do_teto(_ler_arquivo(f"{base}/memory.limit_in_bytes"))
            sw = _mb_do_teto(_ler_arquivo(f"{base}/memory.memsw.limit_in_bytes"))
            if sw is not None and out["max_mb"] is not None:
                out["swap_max_mb"] = max(0, sw - out["max_mb"])
    return out


# O que o deploy viu e fez com o teto de memória do serviço (30/10/2026): o `deploy/atualizar.sh` grava, a cada rodada, em
# `.git/nexus-teto` (ao lado da marca do commit instalado). A 1ª versão dele (42e506c) tirava o teto só pelo
# set-property, e às 15:13 o Raio-X ainda mostrava 700 MB / 1 GB com o deploy rodando a cada 2 min; o Levi não tem acesso
# ao servidor nem ao journal, e ninguém via se o script tinha tirado, falhado ou se outra coisa punha o teto de volta.
ARQ_TETO_DEPLOY = Path(__file__).resolve().parents[2] / ".git" / "nexus-teto"


def _teto_do_deploy():
    """{"hora", "texto"}: a última conferência do teto pelo deploy, em português; None sem o arquivo (fora do servidor)."""
    try:
        linhas = ARQ_TETO_DEPLOY.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    e = dict(l.split("=", 1) for l in linhas if "=" in l)
    try:
        hora = datetime.fromisoformat(e.get("quando", "")).strftime("%d/%m às %H:%M")
    except ValueError:
        hora = "?"
    fontes, acao, erro = e.get("fontes", ""), e.get("acao", ""), e.get("erro", "")
    if erro:
        detalhe = "; ".join(x for x in (erro, f"está em {fontes}" if fontes else "", f"agora {e.get('depois', '')}") if x)
        texto = f"não conseguiu tirar o teto ({detalhe})"
    elif acao == "tirou":
        texto = "tirou o teto" + (f" (estava em {fontes})" if fontes else "")
    elif acao == "cgroup":
        texto = ("o teto estava só no cgroup, sem estar na unidade do systemd (alguém o escreve direto): escreveu max "
                 "nele")
    else:
        texto = f"sem teto abaixo de {e.get('piso_mb', '?')} MB"
    return {"hora": hora, "texto": texto}


def _pids() -> list[int]:
    """Os processos da máquina (as pastas numéricas do /proc); [] fora do Linux."""
    try:
        return [int(n) for n in os.listdir("/proc") if n.isdigit()]
    except OSError:
        return []


# A lista da memória por programa sai de uma thread à parte, com prazo (Raio-X das 16:16 de 20/10/2026: a máquina
# trocando com o disco e o próprio Raio-X 4 min 18 s parado em `_ler_proc`). Ler a linha de comando de um processo que
# está no swap faz o kernel trazê-la do disco, e com o disco tomado ela não volta; a ferramenta da lentidão não pode
# travar na lentidão. Enquanto a leitura presa não volta, nenhuma outra é aberta, e a página mostra a última lista. O
# nome de cada processo é lido uma vez só: a linha de comando de um pid não muda.
PRAZO_MEMORIA_S = 2.0
_ROTULOS: dict = {}                    # (pid, nome) -> o nome do programa na lista
_MEMORIA = {"thread": None, "ultimo": None, "quando": None}
_MEMORIA_TRAVA = threading.Lock()
# A lista de threads (os pedidos em andamento e as tarefas de fundo) também, desde 22/10/2026: às 08:57 o próprio Raio-X
# ficou 1 min 15 s preso em `_threads`, com a máquina em 3,6 GB de swap (as pilhas já não leem o código de cada linha,
# `presos.pilha`; andar por elas ainda pode esperar a memória voltar do disco).
_THREADS = {"thread": None, "ultimo": None, "quando": None}


def _programa(pid: int, nome: str) -> str:
    """O nome do programa na lista da memória. O do Python leva o script (o Nexus e a plataforma de Performance são
    ambos python): só o arquivo e a pasta dele, nunca a linha de comando inteira, que pode ter senha."""
    if pid == os.getpid():
        return "Nexus (este processo)"
    if not nome.startswith("python"):
        return nome
    rotulo = _ROTULOS.get((pid, nome))
    if rotulo is None:
        rotulo = nome
        args = _ler_proc(f"{pid}/cmdline").split("\0")
        for i, a in enumerate(args[1:], 1):
            if a == "-m" and i + 1 < len(args):
                rotulo = f"{nome} · -m {args[i + 1]}"
                break
            if a.endswith(".py"):
                rotulo = f"{nome} · " + "/".join(a.replace("\\", "/").split("/")[-2:])
                break
        _ROTULOS[(pid, nome)] = rotulo
    return rotulo


def _com_prazo(estado: dict, funcao, prazo_s: float, nome: str):
    """`funcao()` numa thread à parte, esperando no máximo `prazo_s`. Passou do prazo: {"atrasado": True, "anterior": o
    último resultado que voltou (ou None), "anterior_quando"}; com a leitura anterior ainda presa, não abre outra."""
    with _MEMORIA_TRAVA:
        t = estado["thread"]
        if t is None or not t.is_alive():
            def ler():
                r = funcao()
                estado.update(ultimo=r, quando=time.strftime("%H:%M:%S"))
            t = threading.Thread(target=ler, name=nome, daemon=True)
            estado["thread"] = t
            t.start()
    t.join(prazo_s)
    if t.is_alive():
        return {"atrasado": True, "anterior": estado["ultimo"], "anterior_quando": estado["quando"]}
    return estado["ultimo"]


def _memoria_por_programa(prazo_s: float = PRAZO_MEMORIA_S):
    """`_quem_ocupa` com prazo (`_com_prazo`)."""
    return _com_prazo(_MEMORIA, _quem_ocupa, prazo_s, "nexus-raio-x-memoria")


# Dentro do worker da plataforma de Performance (20/10/2026). No servidor o worker foi de 3,7 para 5,0 GB (com o swap) em
# 26 min, entre 16:12 e 16:38, e o Nexus travou esperando o disco; a medição de dentro só dava no PC, que não roda os
# backfills do servidor. A cada 10 min o próprio worker grava em /dev/shm quanto cada variável dele ocupa, por amostra,
# com as últimas 3 h (PerformancePainel, `_relatorio_memoria_worker`); aqui só se lê, com o mesmo prazo (no swap, até a
# memória compartilhada espera o disco). Relatório parado há mais de WORKER_VELHO_MIN = o worker não está anotando.
RELATORIO_WORKER = "/dev/shm/gridco_plataforma_worker.json"
WORKER_VELHO_MIN = 30
_WORKER = {"thread": None, "ultimo": None, "quando": None}


def _ler_relatorio_worker(caminho: str | None = None, agora: datetime | None = None):
    """O relatório do worker e o de ~1 h antes (a passada mais nova com ao menos 50 min de diferença). None sem ele."""
    try:
        with open(caminho or RELATORIO_WORKER, encoding="utf-8") as f:
            rel = json.load(f)
    except (OSError, ValueError, TypeError):
        return None
    return _resumir(rel, agora)


def _resumir(rel, agora: datetime | None = None):
    """O relatório de memória (o do worker, o do web ou o do próprio Nexus) e o de ~1 h antes, para a macro `dentro`."""
    try:
        quando = datetime.fromisoformat(rel["quando"])
    except (ValueError, KeyError, TypeError):
        return None
    antes_q, antes = None, {}
    for h in rel.get("historico") or []:
        try:
            q = datetime.fromisoformat(h["quando"])
        except (KeyError, ValueError, TypeError):
            continue
        if (quando - q).total_seconds() >= 50 * 60:
            antes_q, antes = q, h
    idade = round(((agora or datetime.now()) - quando).total_seconds() / 60)
    ant = antes.get("caches") or {}
    return {"quando": quando.strftime("%H:%M"), "idade_min": idade, "velho": idade > WORKER_VELHO_MIN,
            "rss_mb": rel.get("rss_mb"), "swap_mb": rel.get("swap_mb"), "parcial": bool(rel.get("parcial")),
            "antes_quando": antes_q.strftime("%H:%M") if antes_q else None,
            "rss_antes_mb": antes.get("rss_mb"), "swap_antes_mb": antes.get("swap_mb"),
            "caches": [dict(c, antes_mb=ant.get(c.get("nome"))) for c in (rel.get("caches") or [])[:10]]}


def _worker_plataforma(prazo_s: float = PRAZO_MEMORIA_S):
    """`_ler_relatorio_worker` com prazo (`_com_prazo`)."""
    return _com_prazo(_WORKER, _ler_relatorio_worker, prazo_s, "nexus-raio-x-worker")


# Dentro do web da plataforma (21/10/2026). Raio-X das 14:55 de 21/10: o processo web da plataforma (o `app.py` servido
# pelo waitress) foi de 0,8 GB às 14:36 para 3,1 GB e 0,7 GB no swap, com a máquina sem memória, e o relatório só existia
# no worker. O web grava o mesmo relatório, num arquivo dele (PerformancePainel, `_memoria_web_loop`); aqui, a mesma
# leitura do worker, com o prazo e o estado próprios (um relatório preso não prende o outro).
RELATORIO_WEB = "/dev/shm/gridco_plataforma_web.json"
_WEB = {"thread": None, "ultimo": None, "quando": None}


def _web_plataforma(prazo_s: float = PRAZO_MEMORIA_S):
    """O relatório do web da plataforma com prazo (`_com_prazo`); o caminho é lido na hora (os testes o trocam)."""
    return _com_prazo(_WEB, lambda: _ler_relatorio_worker(RELATORIO_WEB), prazo_s, "nexus-raio-x-web")


def _dentro_do_nexus(app):
    """A última medida do Nexus por dentro (`memoria_nexus`, 24/10/2026: na máquina nova o Nexus tinha 682 MB na memória
    e 1.917 MB no swap, e a página não dizia de quê). Já está pronta na memória: não mede nada ao abrir."""
    from . import memoria_nexus
    rel = memoria_nexus.ultimo(app)
    return _resumir(rel) if rel else None


def _quem_ocupa(teto: int = 6):
    """Os programas que mais ocupam a memória da máquina, somados por programa: a memória própria de cada processo
    (RssAnon), a compartilhada uma vez só por programa (RssShmem: os buffers do PostgreSQL aparecem em todo processo
    dele, e somá-los contaria a mesma memória várias vezes) e o swap (VmSwap). None fora do Linux."""
    grupos = {}
    pids = _pids()
    vivos = set(pids)
    for chave in [k for k in list(_ROTULOS) if k[0] not in vivos]:          # o processo que saiu leva o nome junto
        _ROTULOS.pop(chave, None)
    for pid in pids:
        texto = _ler_proc(f"{pid}/status")
        kb = _kb(texto, "Name", "RssAnon", "RssShmem", "VmSwap")
        if "RssAnon" not in kb:                     # thread do kernel, ou o processo já saiu
            continue
        nome = next((linha.split(":", 1)[1].strip() for linha in texto.splitlines() if linha.startswith("Name:")), "?")
        g = grupos.setdefault(_programa(pid, nome), {"anon": 0, "shmem": 0, "swap": 0, "n": 0})
        g["anon"] += kb["RssAnon"]
        g["shmem"] = max(g["shmem"], kb.get("RssShmem", 0))
        g["swap"] += kb.get("VmSwap", 0)
        g["n"] += 1
    if not grupos:
        return None
    lista = sorted(({"programa": p, "mem_mb": round((g["anon"] + g["shmem"]) / 1024), "swap_mb": round(g["swap"] / 1024),
                     "processos": g["n"]} for p, g in grupos.items()),
                   key=lambda x: (-(x["mem_mb"] + x["swap_mb"]), x["programa"]))
    resto = lista[teto:]
    return {"programas": lista[:teto], "outros": len(resto), "outros_mem_mb": sum(x["mem_mb"] for x in resto),
            "outros_swap_mb": sum(x["swap_mb"] for x in resto)}


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


# ── o uso do OS Creator e os pedidos ao Fracttal (31/10/2026, etapa 0 do canto central do OS Creator) ────────────────────
# Em 13 e 14/10/2026 o OS Creator prendeu as threads do Nexus e ninguém soube dizer quais telas as pessoas abrem, a que hora,
# em quantas, quanto cada uma demora e quanto pede ao Fracttal. O servidor guarda as horas fechadas no disco dele a cada hora
# e as leva ao banco às 03:45 (`uso_os`, `dados/fato_uso_os.py`); esta seção lê o banco (de ontem para trás), junta o pendente
# do disco (o que ainda não foi às 03:45) e a memória (a hora aberta), e mostra o antes e o depois de cada mudança. A página
# nunca espera o banco: a leitura vai por trás e fica guardada 10 min.
DIAS_USO = 7                    # a janela da seção
MAX_ROTAS_USO = 15              # as telas mais pedidas
CACHE_USO_S = 600               # a leitura do banco vale 10 min
PRAZO_USO_S = 2.0               # quanto a página espera por ela (a leitura segue por trás e a próxima abertura a encontra)
ESPERA_APOS_FALHA_S = 60        # depois de uma falha, não insiste a cada abertura da página
PERTO_DA_COTA = 0.8             # pico por minuto a partir de 80% da cota: "perto da cota"
SEMANA = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


def _uso_novo() -> dict:
    """O estado da leitura do banco: a thread, a última cópia boa (`dados`), quando ela foi lida (`lido_em`, relógio
    monotônico; `epoch`, relógio de parede de QUANDO A LEITURA COMEÇOU), a hora dela para a página, quando se tentou por
    último e o tipo do erro da última tentativa."""
    return {"thread": None, "dados": None, "lido_em": None, "epoch": None, "lido_txt": "", "tentou_em": None, "erro": ""}


_USO = _uso_novo()
_USO_TRAVA = threading.Lock()


def _monotonico() -> float:
    """O relógio da cópia de 10 min (os testes o trocam)."""
    return time.monotonic()


def _epoch() -> float:
    """A hora de parede de agora (os testes a trocam): a leitura do banco guarda a de quando COMEÇOU, para saber se a
    gravação das 03:45 (`uso_os.gravou_em`) veio depois dela."""
    return time.time()


def _ler_uso(base: str, sessao, hora_id: str, epoch: float) -> None:
    """A leitura do banco, numa thread à parte: guarda o que leu (ou só o tipo do erro, que a página mostra). Só o uso e o
    total da hora: o detalhe do Fracttal é a aba maior do livro e a seção não o mostra."""
    from ..dados import fato_uso_os
    try:
        dados = fato_uso_os.ler_dias(base, sessao, hora_id, DIAS_USO)
    except Exception as ex:                 # noqa: BLE001 - banco fora, leitura curta, livro estranho: a página diz o motivo
        log.warning("Raio-X: não li o uso do OS Creator no banco (%s)", type(ex).__name__, exc_info=True)
        with _USO_TRAVA:
            _USO["erro"] = type(ex).__name__
        return
    with _USO_TRAVA:
        _USO.update(dados=dados, lido_em=_monotonico(), epoch=epoch, lido_txt=time.strftime("%H:%M"), erro="")


def _uso_do_banco(app, hora_id: str, prazo_s: float | None = None) -> dict:
    """`{"dados", "idade_min", "lido_txt", "erro", "lendo"}`: a leitura dos livros de uso dos últimos 7 dias, guardada 10 min.
    Vencida, uma thread à parte a renova e a página espera no máximo `PRAZO_USO_S` por ela; passou disso, mostra a cópia de
    antes (ou nada) e a próxima abertura encontra a nova. Leitura presa não abre outra; depois de uma falha, só tenta de
    novo passado `ESPERA_APOS_FALHA_S`. Teste sem a sessão do banco (`nexus_dados_sessao`) nunca vai à rede.

    **A gravação das 03:45 vence a cópia:** o que saiu do pendente para o banco não está na cópia de antes dela, e o dia de
    ontem sumiria da seção por até 10 min; a cópia cuja leitura começou antes da última gravação (`uso_os.gravou_em`) é
    velha, mesmo dentro dos 10 min."""
    sessao = app.extensions.get("nexus_dados_sessao")
    if sessao is None and app.config.get("TESTING"):
        return {"dados": None, "idade_min": None, "lido_txt": "", "erro": "", "lendo": False, "sem_banco": True}
    from . import uso_os
    prazo = PRAZO_USO_S if prazo_s is None else prazo_s
    agora, gravou = _monotonico(), uso_os.gravou_em()
    with _USO_TRAVA:
        t = _USO["thread"]
        presa = t is not None and t.is_alive()
        velha = (_USO["lido_em"] is None or agora - _USO["lido_em"] >= CACHE_USO_S
                 or gravou > (_USO["epoch"] or 0.0))
        esperando = bool(_USO["erro"]) and _USO["tentou_em"] is not None and agora - _USO["tentou_em"] < ESPERA_APOS_FALHA_S
        if velha and not presa and not esperando:
            from ..cadastro.ligacoes import BASE_API
            if sessao is None:
                import requests
                sessao = requests.Session()
            base = (app.config.get("GRIDCO_DB_API") or BASE_API).rstrip("/")
            t = threading.Thread(target=_ler_uso, args=(base, sessao, hora_id, _epoch()), name="nexus-raio-x-uso",
                                 daemon=True)
            _USO.update(thread=t, tentou_em=agora)
            t.start()
    if velha and t is not None:
        t.join(prazo)
    with _USO_TRAVA:
        s = dict(_USO)
    idade = None if s["lido_em"] is None else int((_monotonico() - s["lido_em"]) // 60)
    return {"dados": s["dados"], "idade_min": idade, "lido_txt": s["lido_txt"], "erro": s["erro"],
            "lendo": s["thread"] is not None and s["thread"].is_alive(), "sem_banco": False}


def _n(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _hora10(v) -> str:
    """`AAAAMMDDHH` com dez algarismos (o banco devolve o inteiro; a memória, o texto), ou "" se não for isso."""
    try:
        return f"{int(float(v)):010d}"
    except (TypeError, ValueError):
        return ""


def _quantil_ponderado(pares, q: float):
    """O quantil `q` de valores com peso: o primeiro valor, em ordem, em que o peso acumulado chega a `q` do total. None sem
    nenhum valor com peso."""
    pares = sorted(p for p in pares if p[0] is not None and p[1] > 0)
    total = sum(w for _, w in pares)
    if not total:
        return None
    alvo, soma = q * total - 1e-9, 0
    for valor, peso in pares:
        soma += peso
        if soma >= alvo:
            return valor
    return pares[-1][0]


def _tom_do_pico(pico: int, cota: int) -> tuple:
    """(a palavra, o tom) do pico por minuto contra a cota: severidade por palavra e cor, nunca só pela cor."""
    if pico >= cota:
        return "na cota", "critico"
    if pico >= PERTO_DA_COTA * cota:
        return "perto da cota", "alerta"
    return "", ""


def montar_uso_os(hora_id_agora: str, banco: dict | None, vivo: dict) -> dict:
    """A conta da seção, pura: `banco` = `{"uso": [...], "total": [...]}` lido dos livros (ou None); `vivo` = o que o servidor
    guarda fora do banco, `{"uso", "total", "setor"}`: as linhas do pendente do disco (o que ainda não foi às 03:45), as da
    hora aberta (a memória dos contadores) e o corte por setor (que mora só no servidor: o arquivo do disco mais o que entrou
    depois do último salvamento). `total` é a linha de 1 por hora (`hora_id`, os pedidos, as recusas, os erros e o pico por
    minuto): a que o contador entrega como `*` o `fato_uso_os.separar_total` já separou. Janela: os `DIAS_USO` dias de Brasília
    que terminam no de `hora_id_agora`. Na mesma chave (hora × rota × automático, ou a hora do total) vale o mais novo: o
    pendente e a memória vencem o banco, e a linha que está nos dois não conta duas vezes. Devolve `tem` (há alguma linha na
    janela), a `cota`, o `resumo`, os `dias`, as 24 `horas`, as `rotas` mais pedidas e os `setores`.

    Cliques e automáticos nunca se misturam (o `/os/_nexus/sessao` de cada aba aberta seria a "tela mais clicada"). O total
    do Fracttal e o pico por minuto vêm só do total da hora (o detalhe por origem não entra: repetiria a conta). A mediana e
    o p95 de vários dias são aproximados: cada hora guarda só os dela, e juntar é o quantil dos quantis pesado pelos pedidos
    atendidos (os recusados pelo teto não têm duração)."""
    from . import fracttal_conta
    cota = fracttal_conta.COTA_POR_MINUTO
    hoje = datetime.strptime(str(hora_id_agora)[:8], "%Y%m%d")
    datas = [hoje - timedelta(days=i) for i in range(DIAS_USO - 1, -1, -1)]
    ids = [d.strftime("%Y%m%d") for d in datas]
    corte = ids[0] + "00"
    uso, total = {}, {}
    for fonte in (banco or {}, vivo or {}):
        for r in fonte.get("uso") or ():
            h = _hora10(r.get("hora_id"))
            if h >= corte and h[:8] in ids:
                uso[(h, str(r.get("rota")), 1 if _n(r.get("automatico")) else 0)] = r
        for r in fonte.get("total") or ():
            h = _hora10(r.get("hora_id"))
            if h >= corte and h[:8] in ids:
                total[h] = r
    por_dia = {i: {"cliques": 0, "automaticos": 0, "fracttal": 0, "recusas": 0, "pico": 0, "pico_hora": None} for i in ids}
    por_hora = {h: {"cliques": 0, "automaticos": 0, "fracttal": 0, "pico": 0} for h in range(24)}
    por_rota = {}
    for (h, rota, auto), r in uso.items():
        pedidos, ocupado = _n(r.get("pedidos_qtd")), _n(r.get("ocupado_qtd"))
        coluna = "automaticos" if auto else "cliques"
        por_dia[h[:8]][coluna] += pedidos
        por_hora[int(h[8:])][coluna] += pedidos
        p = por_rota.setdefault(rota, {"rota": rota, "cliques": 0, "automaticos": 0, "fracttal": 0, "erros": 0,
                                       "ocupado": 0, "p50": [], "p95": []})
        p[coluna] += pedidos
        p["fracttal"] += _n(r.get("fracttal_qtd"))
        p["erros"] += _n(r.get("erros_qtd"))
        p["ocupado"] += ocupado
        atendidos = max(1, pedidos - ocupado)
        for chave, campo in (("p50", "duracao_p50_ms"), ("p95", "duracao_p95_ms")):
            if r.get(campo) is not None:
                p[chave].append((_n(r.get(campo)), atendidos))
    for h, r in total.items():
        pedidos, pico = _n(r.get("pedidos_qtd")), _n(r.get("pico_minuto_qtd"))
        d = por_dia[h[:8]]
        d["fracttal"] += pedidos
        d["recusas"] += _n(r.get("recusas_qtd"))
        if pico > d["pico"]:
            d["pico"], d["pico_hora"] = pico, int(h[8:])
        hh = por_hora[int(h[8:])]
        hh["fracttal"] += pedidos
        hh["pico"] = max(hh["pico"], pico)

    escala = max((v["cliques"] for v in por_hora.values()), default=0) or 1
    horas = []
    for h, v in sorted(por_hora.items()):
        palavra, tom = _tom_do_pico(v["pico"], cota)
        horas.append(dict(v, hora=h, rotulo=f"{h:02d}h", pct_cliques=round(100 * v["cliques"] / escala),
                          pct_cota=min(100, round(100 * v["pico"] / cota)), situacao=palavra, tom=tom))
    dias = []
    for d, i in zip(datas, ids):
        v = por_dia[i]
        palavra, tom = _tom_do_pico(v["pico"], cota)
        dias.append(dict(v, dia=d.strftime("%d/%m"), semana=SEMANA[d.weekday()], hoje=i == ids[-1], situacao=palavra,
                         tom=tom))
    rotas = []
    for p in sorted(por_rota.values(), key=lambda p: (-(p["cliques"] + p["automaticos"]), p["rota"]))[:MAX_ROTAS_USO]:
        rotas.append({"rota": p["rota"], "cliques": p["cliques"], "automaticos": p["automaticos"],
                      "p50_ms": _quantil_ponderado(p["p50"], 0.5), "p95_ms": _quantil_ponderado(p["p95"], 0.95),
                      "fracttal": p["fracttal"], "erros": p["erros"], "ocupado": p["ocupado"]})
    por_setor = {}
    for dia, setores in ((vivo or {}).get("setor") or {}).items():
        if dia not in por_dia or not isinstance(setores, dict):
            continue
        for setor, telas in setores.items():
            s = por_setor.setdefault(setor, {"setor": setor, "cliques": 0, "automaticos": 0, "rotas": {}})
            for rota, v in (telas or {}).items():
                c, a = _n(v.get("cliques")), _n(v.get("automaticos"))
                s["cliques"] += c
                s["automaticos"] += a
                s["rotas"][rota] = s["rotas"].get(rota, 0) + c
    setores = []
    for s in sorted(por_setor.values(), key=lambda s: (-s["cliques"], -s["automaticos"], s["setor"])):
        top = sorted(((r, c) for r, c in s["rotas"].items() if c), key=lambda rc: (-rc[1], rc[0]))[:3]
        setores.append({"setor": s["setor"], "cliques": s["cliques"], "automaticos": s["automaticos"],
                        "rotas": [{"rota": r, "cliques": c} for r, c in top]})
    pior = max(dias, key=lambda d: (d["pico"], d["dia"]))
    resumo = {"cliques": sum(d["cliques"] for d in dias), "automaticos": sum(d["automaticos"] for d in dias),
              "fracttal": sum(d["fracttal"] for d in dias), "recusas": sum(d["recusas"] for d in dias),
              "pico": pior["pico"], "pico_dia": pior["dia"], "pico_hora": pior["pico_hora"]}
    return {"tem": bool(uso or total), "cota": cota, "resumo": resumo, "dias": dias, "horas": horas, "rotas": rotas,
            "setores": setores}


def _de_onde_vem(lido: dict, espera: dict, tem: bool) -> dict:
    """As frases da seção sobre de onde vêm os números: `banco_txt` e, sem dado nenhum, o `motivo`."""
    erro, hora = lido.get("erro"), lido.get("lido_txt")
    if lido.get("dados") is not None:
        txt = (f"De ontem para trás, do banco, lido às {hora} (a cópia vale 10 min). O que ainda não foi ao banco (ele "
               "recebe tudo uma vez por dia, às 03:45) vem do disco do servidor, e a hora aberta, da memória dele.")
        if erro:
            txt += f" A última tentativa de ler o banco falhou ({erro}); o que está aqui é a cópia das {hora}."
    elif erro:
        txt = (f"O banco não respondeu ({erro}): vale só o que o servidor guarda, no disco dele (o que ainda não foi às "
               "03:45) e na memória (a hora aberta).")
    elif lido.get("lendo"):
        txt = ("Lendo o banco (a página não espera): até a leitura chegar vale só o que o servidor guarda, no disco (o que "
               "ainda não foi às 03:45) e na memória. Leia de novo em instantes.")
    else:
        txt = "Sem o banco nesta máquina: vale só o que este processo guarda, no disco e na memória."
    if espera.get("horas"):
        txt += f" {espera['horas']} hora(s) ainda não foram ao banco (vão às 03:45 e já estão no disco do servidor)."
    if tem:
        return {"banco_txt": txt, "motivo": ""}
    if erro and lido.get("dados") is None:
        motivo = f"O banco não respondeu ({erro}) e o servidor ainda não guarda nada, nem no disco nem na memória."
    elif lido.get("lendo") and lido.get("dados") is None:
        motivo = "Lendo o banco: a página não espera, leia de novo em instantes."
    elif lido.get("dados") is not None:
        motivo = ("Nenhuma hora gravada no banco ainda e nada pendente no disco nem na memória: o servidor guarda a primeira "
                  "hora fechada no :05 da hora seguinte e a leva ao banco às 03:45.")
    else:
        motivo = "Sem o banco nesta máquina e sem o registro do servidor (ele só liga no servidor)."
    return {"banco_txt": txt, "motivo": motivo}


def _secao_uso_os(app) -> dict:
    """A seção inteira para o template. Nunca levanta: a ferramenta da lentidão não pode travar por causa da conta dela."""
    try:
        from ..dados import fato_uso_os
        from . import fracttal_conta, uso_os
        hora = fracttal_conta.hora_id_de()
        lido = _uso_do_banco(app, hora)
        vivo = uso_os.instantaneo()
        espera = uso_os.linhas_pendentes()
        contagem = uso_os.pendentes()
        # o contador entrega o total da hora como a linha `*` no meio do detalhe (o do pendente e o da memória): só o total
        # interessa aqui, e o detalhe por origem não é mostrado
        total_do_disco = fato_uso_os.separar_total(espera["fracttal"])[1]
        total_da_memoria = fato_uso_os.separar_total(fracttal_conta.instantaneo())[1]
        conta = montar_uso_os(hora, lido["dados"], {
            "uso": espera["uso"] + vivo["linhas"], "total": total_do_disco + total_da_memoria, "setor": vivo["setor"]})
        return dict(conta, **_de_onde_vem(lido, contagem, conta["tem"]))
    except Exception:                       # noqa: BLE001
        log.exception("Raio-X: não consegui montar a seção do uso do OS Creator")
        return {"tem": False, "banco_txt": "", "motivo": "Não consegui montar a seção (veja o log do servidor)."}


# ── o canto central do OS Creator (31/10/2026; item 0 da 3.1+3.2 para os ativos, a 3.2 para a lista de OS) ──────────────
# O Levi não tem acesso ao servidor: a 1ª noite do leitor dos ativos (a paridade REST x RPC, as descrições que o detector da
# foto cortou) e a 1ª carga da lista de OS só se conferem por aqui. Cada peça diz o estado dela resumido, em linhas (rótulo,
# frase), só com contagens, datas, ids e motivos: nada de texto de ativo, de OS nem nome de pessoa. O Raio-X NÃO importa os
# módulos do OS Creator (`sys.modules`): no PC, sem ninguém ter aberto o OS Creator, eles nem estão na memória, e importá-los
# aqui faria o boot da cópia em disco só para mostrar o quadro.
def _quando(ts) -> str:
    """"31/10 02:15" (Brasília) de um epoch, ou "" sem ele."""
    if not isinstance(ts, (int, float)) or not ts:
        return ""
    return time.strftime("%d/%m %H:%M", time.gmtime(ts - 3 * 3600))


def _pct(v) -> str:
    return ("%.1f%%" % float(v)).replace(".", ",") if isinstance(v, (int, float)) else "?"


def _linhas_dos_ativos(e: dict) -> list:
    """As linhas do bloco "Ativos centrais", do `ativos_central.estado()`."""
    linhas = []
    if e.get("n"):
        linhas.append(("Catálogo", "%d ativos, fonte %s, lista inteira conferida em %s%s; versão %s" % (
            e["n"], e.get("fonte") or "?", _quando(e.get("lido_em")) or "?",
            ", os novos do dia em %s" % _quando(e["novos_em"]) if e.get("novos_em") else "",
            str(e.get("versao") or "")[:10])))
    else:
        linhas.append(("Catálogo", "sem catálogo nesta máquina (ele nasce da cópia em disco, da foto do banco ou do 1º "
                                   "download pelo RPC)"))
    leitor = e.get("leitor")
    if not leitor:
        txt = "não ligado (só o servir.py liga o leitor; no PC o catálogo segue pelo RPC, com a sessão de quem usa)"
    elif not leitor.get("ligado"):
        txt = "não ligado: %s" % (leitor.get("motivo") or leitor.get("erro") or "?")
    elif e.get("leitor_pronto"):
        txt = "pronto: os botões \"Atualizar ativos\" pedem os novos a ele"
    else:
        txt = ("ligado, mas não está pronto (sem a paridade da noite valendo, ou com uma leitura REST falhando depois da "
               "última boa): os botões seguem pelo RPC")
    linhas.append(("Leitor do servidor", txt))
    p = e.get("paridade_rest")
    if not p:
        linhas.append(("Paridade do REST", "ainda não houve (a 1ª noite do leitor é a conferência REST x RPC)"))
    else:
        linhas.append(("Paridade do REST", "%s em %s, contra o catálogo do %s: a leitura tem %s dos códigos do catálogo e o "
                       "catálogo, %s dos dela%s" % (
                           "valeu" if p.get("vale") else "NÃO valeu", _quando(p.get("em")) or "?", p.get("contra") or "?",
                           _pct(p.get("cob_ref")), _pct(p.get("cob_rest")),
                           "" if p.get("vale") else ". Motivo: %s" % str(p.get("motivo") or "")[:300])))
    r = e.get("rest") or {}
    txt = "a última leitura boa em %s" % (_quando(r.get("bom_em")) or "nenhuma")
    if (r.get("falha_em") or 0) > (r.get("bom_em") or 0):
        txt += "; FALHOU depois dela, em %s: %s" % (_quando(r.get("falha_em")), str(r.get("falha") or "")[:200])
    elif r.get("falha_em"):
        txt += "; a última falha, antes dela, em %s" % _quando(r.get("falha_em"))
    linhas.append(("REST do Fracttal", txt))
    c = e.get("descricao_cortada")
    if c:
        linhas.append(("Descrições cortadas", "%d descrições na foto da noite de %s%s" % (
            c.get("n") or 0, _quando(c.get("em")) or "?",
            ": ids %s" % ", ".join(str(i) for i in c.get("exemplos") or ()) if c.get("exemplos") else "")))
    else:
        linhas.append(("Descrições cortadas", "nenhuma noite com a foto do banco ainda"))
    d = e.get("disco") or {}
    txt = "gravada em %s" % _quando(d.get("gravado_em")) if d.get("gravado_em") else "sem gravação neste processo"
    if d.get("lido"):
        txt += "; o boot leu a %s" % d["lido"]
    if d.get("erro"):
        txt += "; erro: %s" % str(d["erro"])[:200]
    linhas.append(("Cópia em disco", txt))
    return linhas


def _peca(nome_modulo: str, montar) -> dict:
    """Uma peça do canto central: `{"linhas"}`, ou `{"motivo"}` quando o módulo não está carregado ou o estado falhou."""
    mod = sys.modules.get(nome_modulo)
    if mod is None:
        return {"linhas": [], "motivo": "O OS Creator ainda não foi aberto neste processo: a peça não está na memória."}
    try:
        return {"linhas": montar(mod), "motivo": ""}
    except Exception:                       # noqa: BLE001 - o quadro nunca derruba a página
        log.exception("Raio-X: não consegui montar a peça %s do canto central", nome_modulo)
        return {"linhas": [], "motivo": "Não consegui ler o estado desta peça (veja o log do servidor)."}


# as faixas da lista de OS na ordem do dia, com o nome que a tela mostra; a faixa `os` da lista é a leitura das `pendentes`
_FAIXAS_DE_OS = (("novas", "novas", "As novas"), ("sete_dias", "sete_dias", "Os 7 dias"), ("abertas", "abertas", "As abertas"),
                 ("finalizadas", "finalizadas", "As finalizadas"), ("noite", "noite", "A noite"),
                 ("os", "pendentes", "As pendentes (pelo nº)"))


def _dia_e_hora(iso) -> str:
    """"31/10 10:00" (Brasília) de um ISO do Fracttal (UTC, sem o fuso), ou "?"."""
    try:
        return _quando(datetime.fromisoformat(str(iso)[:19]).replace(tzinfo=timezone.utc).timestamp()) or "?"
    except ValueError:
        return "?"


def _pedidos(n) -> str:
    n = int(n or 0)
    return "%d pedido%s" % (n, "" if n == 1 else "s")


def _conferencias_das_telas(conf: dict) -> str:
    """A guarda da lista pela metade das telas que leem da lista central (decisão BA da 3.3): por visão, quantas conferências
    de 19/10 foram ao Fracttal desde o último reinício, quantas divergiram (o total que o Fracttal deu à pessoa e o da lista) e
    quantas falharam. A visão restrita de alguém também diverge (é o que a guarda manda ao vivo); muitas divergências na visão
    "todos" de quem vê tudo é sinal de lista errada. Só contagens e a hora: nunca quem."""
    partes = []
    for visao, c in sorted(conf.items()):
        n, div, fal = int(c.get("n") or 0), int(c.get("divergiram") or 0), int(c.get("falharam") or 0)
        txt = "%s: %d conferência%s, %d %s" % (visao, n, "" if n == 1 else "s", div, "divergiu" if div == 1 else "divergiram")
        if fal:
            txt += ", %d %s (o Fracttal fora ou a sessão caída)" % (fal, "falhou" if fal == 1 else "falharam")
        u = c.get("ultima_divergencia") or {}
        if u:
            txt += "; a última divergência em %s: Fracttal %s contra %s da lista" % (
                _quando(u.get("em")) or "?", u.get("fracttal"), u.get("lista"))
        partes.append(txt)
    return " · ".join(partes)


def _linhas_da_lista_de_os(e: dict) -> list:
    """As linhas da peça "Lista central de OS" (3.2), do `os_central.estado(medir_memoria=True)`: só contagens, datas, ids e
    motivos (nunca o texto de uma OS nem o nome de alguém)."""
    linhas = []
    if e.get("n"):
        linhas.append(("Lista", "%d OS (%d abertas), %d a conferir, %d pendentes de uma ação; versão %s; a última leitura do "
                                "Fracttal em %s" % (e["n"], e.get("abertas") or 0, e.get("a_conferir") or 0,
                                                    e.get("pendentes") or 0, e.get("versao"),
                                                    _quando(e.get("lido_em")) or "?")))
    else:
        linhas.append(("Lista", "vazia nesta máquina: ela nasce da cópia em disco, das faixas do leitor e das ações do OS "
                                "Creator; até lá as telas leem ao vivo"))
    de, ate = (e.get("janela") or (None, None))[:2]
    if de and ate:
        linhas.append(("Janela lida inteira", "as OS criadas de %s/%s/%s até %s; fora dela, as telas leem ao vivo" % (
            de[8:10], de[5:7], de[:4], _dia_e_hora(ate))))
    else:
        linhas.append(("Janela lida inteira", "nenhuma ainda: a 1ª carga é de madrugada (03:21); até lá a lista tem só o que as "
                                              "faixas do dia trouxeram, e as telas leem ao vivo"))
    leitor = e.get("leitor")
    if not leitor:
        linhas.append(("Leitor do servidor", "não ligado (só o servir.py liga o leitor; no PC a lista guarda só o que as ações "
                                             "mudaram)"))
    elif not leitor.get("ligado"):
        linhas.append(("Leitor do servidor", "não ligado: %s" % (leitor.get("motivo") or leitor.get("erro") or "?")))
    else:
        linhas.append(("Leitor do servidor", "ligado%s" % ("; lendo agora" if leitor.get("lendo") else "")))
    feitas = (leitor or {}).get("faixas") or {}
    for chave_lista, chave_leitor, rotulo in _FAIXAS_DE_OS:
        ent = (e.get("faixas") or {}).get(chave_lista)
        run = feitas.get(chave_leitor)
        if not ent and not run:
            continue
        partes = []
        if ent:
            partes.append("entregue em %s%s: %d OS (%d linhas); %d entraram, %d mudaram, %d a conferir, %d saíram" % (
                _quando(ent.get("em")) or "?", " pelo %s" % ent["quem"] if ent.get("quem") else "", ent.get("os") or 0,
                ent.get("linhas") or 0, ent.get("entraram") or 0, ent.get("mudaram") or 0, ent.get("a_conferir") or 0,
                ent.get("sairam") or 0))
        if run:
            if run.get("erro"):
                partes.append("%s em %s, depois de %s: %s" % (
                    "DEFEITO do leitor (a pilha está no log)" if run.get("defeito") else "FALHOU",
                    _quando(run.get("inicio")) or "?", _pedidos(run.get("pedidos")), str(run["erro"])[:200]))
            else:
                partes.append("a última leitura do leitor em %s: %s%s" % (
                    _quando(run.get("inicio")) or "?", _pedidos(run.get("pedidos")),
                    "" if ent and run.get("os") else "; %s" % str(run.get("resultado") or "")[:200]))
        linhas.append((rotulo, "; ".join(partes)))
    # a leitura que a trava de encolhimento recusou (rodada 1 da revisão), até a faixa passar de novo: só contagens
    rotulos = {chave: rotulo for chave, _l, rotulo in _FAIXAS_DE_OS}
    for faixa, rec in sorted((e.get("recusas") or {}).items()):
        linhas.append(("Trava de encolhimento", "%s: a lista recusou a leitura de %s (%s)" % (
            rotulos.get(faixa, faixa), _quando(rec.get("em")) or "?", str(rec.get("motivo") or "")[:300])))
    entregas = (leitor or {}).get("entregas") or {}
    quem = ((e.get("faixas") or {}).get("abertas") or {}).get("quem")
    if quem or any(entregas.values()):
        linhas.append(("Quem entregou as abertas", "a última: %s; do tarefas_os em %s, do próprio leitor em %s" % (
            quem or "?", _quando(entregas.get("tarefas_os")) or "nunca", _quando(entregas.get("os_leitor")) or "nunca")))
    c = e.get("campos")
    if c:
        linhas.append(("Campos que o REST trouxe", "na faixa %s de %s, %d OS: %s" % (
            c.get("faixa"), _quando(c.get("em")) or "?", c.get("n") or 0,
            ", ".join("%s %s" % (k, _pct(v)) for k, v in (c.get("pct") or {}).items()))))
    conf = _conferencias_das_telas(e.get("conferencias") or {})
    if conf:
        linhas.append(("Conferências das telas", conf))
    d = e.get("disco") or {}
    if d.get("gravado_em"):
        txt = "gravada em %s%s" % (_quando(d["gravado_em"]),
                                   ", %s MB" % ("%.1f" % (d["bytes"] / 2**20)).replace(".", ",") if d.get("bytes") else "")
    else:
        txt = "sem gravação neste processo"
    if d.get("lido"):
        txt += "; o boot leu a %s" % d["lido"]
    if d.get("erro"):
        txt += "; erro: %s" % str(d["erro"])[:200]
    linhas.append(("Cópia em disco", txt))
    if e.get("memoria_mb") is not None:
        linhas.append(("Memória", "~%s MB (cada registro e texto contados uma vez; o orçamento é de 30 MB para 36 mil OS)"
                       % ("%.1f" % e["memoria_mb"]).replace(".", ",")))
    return linhas


def _secao_canto_central() -> dict:
    """O bloco do canto central na seção do OS Creator: os ativos (item 0 da 3.1+3.2) e a lista de OS (3.2)."""
    return {"ativos": _peca("ativos_central", lambda m: _linhas_dos_ativos(m.estado())),
            "os": _peca("os_central", lambda m: _linhas_da_lista_de_os(m.estado(medir_memoria=True)))}


def registrar_raio_x(bp) -> None:
    @bp.route("/raio-x")
    def raio_x():
        if not session.get("admin"):
            return render_template("cadastro/sem_permissao.html", titulo="Raio-X do Nexus", eyebrow="Base · Raio-X",
                                   area="O Raio-X do Nexus", email=""), 403
        app = current_app._get_current_object()
        estado = app.extensions.get(P.CHAVE)
        lista = _com_prazo(_THREADS, lambda: _threads(estado), PRAZO_MEMORIA_S, "nexus-raio-x-threads")
        threads_atrasado = isinstance(lista, dict)           # passou do prazo: a última lista, com a hora dela
        pedidos, outras = (lista.get("anterior") or ([], [])) if threads_atrasado else lista
        teto = app.extensions.get("nexus_teto_os")
        teto = teto.estado() if teto is not None else None
        if teto and teto["ultimo_recusado"]:
            teto["ultimo_txt"] = time.strftime("%d/%m %H:%M", time.localtime(teto["ultimo_recusado"]))
        return render_template("raio_x.html", pedidos=pedidos, outras=outras, ligado=estado is not None, teto=teto,
                               threads=getattr(estado, "threads", 0), cpu=_processador(), quem=_memoria_por_programa(),
                               worker=_worker_plataforma(), web=_web_plataforma(), prazo_memoria=PRAZO_MEMORIA_S,
                               nexus=_dentro_do_nexus(app), uso=_secao_uso_os(app), canto=_secao_canto_central(),
                               threads_atrasado=threads_atrasado,
                               threads_quando=lista.get("anterior_quando") if threads_atrasado else None,
                               travamentos=P.cartao(app) if estado is not None else None,
                               quando=time.strftime("%d/%m/%Y %H:%M:%S"))
