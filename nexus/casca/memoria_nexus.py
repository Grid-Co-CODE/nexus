"""O Nexus por dentro: quanto cada variável dele ocupa (24/10/2026, a seção "Dentro do Nexus" do Raio-X).

Raio-X das 12:05 de 24/10, na máquina nova de 16 GB: o Nexus com 682 MB na memória e 1.917 MB no swap (2,6 GB), e a
página mostrava por dentro o worker e o web da plataforma, mas não o próprio Nexus. A mesma conta da plataforma
(`_tamanho_estimado` do PerformancePainel, medida contra o real no worker do PC em 20/10/2026): cada variável dos módulos
do Nexus (e do clone do OS Creator, que mora dentro dele) e cada extensão do app, por amostra (contêiner com mais de 100
itens tem 10 medidos e o resto pela média), a cada 10 min, numa thread (`nexus-memoria`), com teto de PRAZO_S (no Python
a medida segura as outras threads: o GIL). Só tamanhos e nomes de variável: nenhum dado sai daqui.
"""
import collections
import itertools
import os
import sys
import threading
import time
import types
from datetime import datetime

CHAVE = "nexus_memoria"
PRAZO_S = 3.0
INTERVALO_S = 600
PRIMEIRA_S = 90                 # a 1ª medida depois de subir (a pré-carga ainda está enchendo as cópias)
HISTORICO = 8                   # as últimas medidas, para o "1 h antes" do Raio-X
TETO = 12
RAIZ = os.path.normcase(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_PULAR = (types.ModuleType, types.FunctionType, types.BuiltinFunctionType, type)


def tamanho_estimado(obj, vistos: set, lim: int = 100, amostra: int = 10) -> float:
    """Bytes de `obj` e do que ele guarda, por amostra (a mesma conta do `_tamanho_estimado` da plataforma)."""
    total, pilha = 0.0, [(obj, 1.0)]
    while pilha:
        o, peso = pilha.pop()
        if id(o) in vistos or issubclass(type(o), _PULAR) or _eh_app(o):
            continue
        vistos.add(id(o))
        try:
            total += sys.getsizeof(o) * peso
        except Exception:                               # noqa: BLE001
            continue
        if isinstance(o, dict):
            n = len(o)
            try:
                itens = list(itertools.islice(o.items(), amostra)) if n > lim else list(o.items())
            except RuntimeError:                        # mudou de tamanho no meio (outra thread): fica o que já contou
                continue
            f = peso * n / len(itens) if itens and n > lim else peso
            for k, v in itens:
                pilha.append((k, f))
                pilha.append((v, f))
        elif isinstance(o, (list, tuple, set, frozenset, collections.deque)):
            n = len(o)
            try:
                if n > lim:
                    itens = ([o[j * n // amostra] for j in range(amostra)] if isinstance(o, (list, tuple))
                             else list(itertools.islice(o, amostra)))
                else:
                    itens = list(o)
            except (IndexError, RuntimeError):
                continue
            f = peso * n / len(itens) if itens and n > lim else peso
            for x in itens:
                pilha.append((x, f))
        elif hasattr(o, "__dict__") and not isinstance(o, (threading.Thread,)):
            pilha.append((vars(o), peso))               # objeto nosso (a cópia de uma tela, um serviço): o que ele guarda
    return total


def _eh_app(o) -> bool:
    # o app do Flask tem tudo pendurado nele: medido pelas extensões, uma a uma, e não como um bloco só
    return type(o).__name__ == "Flask" and type(o).__module__.startswith("flask")


def _medivel(v) -> bool:
    # o type() e não o isinstance: o request, a session e o g do Flask importados nos módulos são proxies (LocalProxy),
    # e fora de um pedido o isinstance neles levanta (a medida os pula pelo `except` do `medir`)
    return not issubclass(type(v), _PULAR)


def _status_proprio() -> dict:
    kb = {}
    try:
        with open("/proc/self/status", encoding="ascii", errors="replace") as f:
            for linha in f:
                campo, _, resto = linha.partition(":")
                if campo in ("VmRSS", "VmSwap") and resto.split():
                    kb[campo] = int(resto.split()[0])
    except OSError:
        pass
    return kb


def medir(app=None, teto: int = TETO, prazo_s: float = PRAZO_S) -> dict:
    """{"quando", "rss_mb", "swap_mb", "caches": [{"nome", "mb", "itens"}], "parcial", "segundos"}: as variáveis de
    1 MB ou mais, da maior para a menor. As extensões do app primeiro (é lá que moram as cópias guardadas por app)."""
    t0, parcial, vistos, caches = time.monotonic(), False, set(), []
    candidatos = []
    if app is not None:
        candidatos += [(f"app.extensions[{k!r}]", v) for k, v in list(app.extensions.items()) if k != CHAVE]
    mods = [m for m in list(sys.modules.values()) if m is not None and m.__name__ != "__main__"
            and getattr(m, "__file__", None) and os.path.normcase(os.path.abspath(m.__file__)).startswith(RAIZ)]
    for m in mods:
        if m.__name__ == __name__:
            continue
        try:
            candidatos += [(f"{m.__name__}.{nome}", v) for nome, v in list(vars(m).items())
                           if not nome.startswith("__") and _medivel(v)]
        except RuntimeError:
            continue
    for nome, valor in candidatos:
        if time.monotonic() - t0 > prazo_s:
            parcial = True
            break
        try:
            mb = tamanho_estimado(valor, vistos) / 2**20
        except Exception:                               # noqa: BLE001 — um objeto estranho não derruba a medida
            continue
        if mb >= 1:
            item = {"nome": nome, "mb": round(mb, 1)}
            try:
                item["itens"] = len(valor)
            except TypeError:
                pass
            caches.append(item)
    caches.sort(key=lambda c: -c["mb"])
    kb = _status_proprio()
    return {"quando": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "pid": os.getpid(),
            "rss_mb": round(kb.get("VmRSS", 0) / 1024) if kb else None,
            "swap_mb": round(kb.get("VmSwap", 0) / 1024) if kb else None,
            "caches": caches[:teto], "parcial": parcial, "segundos": round(time.monotonic() - t0, 2)}


def _anotar(app, rel: dict) -> dict:
    e = app.extensions.setdefault(CHAVE, {"historico": [], "rel": None})
    e["historico"].append({"quando": rel["quando"], "rss_mb": rel["rss_mb"], "swap_mb": rel["swap_mb"],
                           "caches": {c["nome"]: c["mb"] for c in rel["caches"]}})
    del e["historico"][:-HISTORICO]
    e["rel"] = dict(rel, historico=list(e["historico"]))
    return e["rel"]


def medir_e_anotar(app) -> dict:
    return _anotar(app, medir(app))


def ultimo(app):
    """A última medida (no formato do relatório da plataforma, com o histórico), ou None antes da 1ª."""
    return (app.extensions.get(CHAVE) or {}).get("rel")


def ligar(app, intervalo_s: float = INTERVALO_S, primeira_s: float = PRIMEIRA_S) -> None:
    """A medida a cada `intervalo_s`, numa thread. Quem chama é o servir.py e o app.py (os testes não ligam nada)."""
    app.extensions.setdefault(CHAVE, {"historico": [], "rel": None})

    def laco():
        time.sleep(primeira_s)
        while True:
            try:
                medir_e_anotar(app)
            except Exception:                           # noqa: BLE001 — medir nunca derruba o Nexus
                pass
            time.sleep(intervalo_s)
    threading.Thread(target=laco, name="nexus-memoria", daemon=True).start()
