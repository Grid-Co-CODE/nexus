"""os_disco.py: a cópia em disco da lista central de OS (31/10/2026, etapa 3 do canto central do OS Creator).

Saiu do `os_central.py` na rodada 1 da revisão da 3.1+3.2 (Ruling AY: só mudança de lugar; o arquivo passava de 1.200 linhas), no
molde do `ativos_disco.py`: a lista guarda e entrega; daqui saem a gravação (agendada) e a leitura do disco. A pasta, a versão
vigente, o estado do disco e o que vai no cabeçalho quem dá é o `os_central`, a cada chamada (os testes trocam a pasta por
`os_central.reiniciar(pasta=...)`, e a lista continua uma só por processo).

O arquivo (decisão AH): `<pasta>/os_central.json.gz`, em linhas JSON: o cabeçalho na 1ª (o formato, a versão, a janela, a marca
d'água, as "a conferir", as pendentes, a última entrega de cada faixa e os nomes dos campos do registro), uma OS por linha (os
campos na ordem do registro; as datas, os cinco inteiros) e o fecho na última, com a conta. A escrita e a leitura vão em fluxo:
nunca o arquivo inteiro na memória. A troca é de uma vez (`canto_disco.trocar_de_uma_vez`, a mesma da cópia dos ativos). A cópia
sem o fecho, com outra conta, de outro formato ou com outros campos foi cortada no meio ou é de outra versão do código: é
ignorada, e o motivo vai ao estado do disco.

A AGENDA: no máximo uma escrita a cada `GRAVAR_A_CADA_S`, numa thread à parte (`nexus-os-central-disco`). A gravação agendada
escreve a versão do momento em que ela roda: as mudanças seguidas viram uma escrita só, e a última chega ao disco em até 30 s
(o deploy logo depois de uma ação não a apaga).
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import struct
import threading
import time
import zlib

# a troca de uma vez (rascunho ao lado + `os.replace`), a mesma da cópia dos ativos; pelo nome do módulo, para o teste contar
from canto_disco import trocar_de_uma_vez as _trocar_de_uma_vez
from os_registro import _PACOTE, RegistroOS, _p

log = logging.getLogger("oscreator.os_central")

FORMATO = 1                     # o formato da cópia em disco; outro número = arquivo de outra versão do código, ignorado
NOME_ARQUIVO = "os_central.json.gz"
GRAVAR_A_CADA_S = 30            # no máximo uma escrita da cópia a cada 30 s: as ações seguidas viram uma (decisão AH)
TRAVA = threading.Lock()        # uma gravação por vez
# `escrevendo` CONTA as gravações em curso (rodada 1 da revisão): a agendada durante uma lenta espera a trava dela, e com uma
# bandeira só a 1ª, ao terminar, dizia "nenhuma escrevendo" com a 2ª ainda na fila (o `esperar_gravacao` voltava cedo)
_AGENDA = {"pendente": False, "escrevendo": 0, "ultima": 0.0, "timer": None}
_AGENDA_COND = threading.Condition()
_I_DATAS = RegistroOS._fields.index("datas")


def caminho(pasta: str | None) -> str | None:
    return os.path.join(pasta, NOME_ARQUIVO) if pasta else None


# ── o registro, de e para a linha do arquivo ───────────────────────────────────────────────────────────────────────────
def _para_disco(r: RegistroOS) -> list:
    v = list(r)
    v[_I_DATAS] = list(_PACOTE.unpack(r.datas))
    return v


def _do_disco(v: list, j) -> RegistroOS:
    """Uma linha da cópia em disco (os campos na ordem do registro; as datas, os cinco inteiros) de volta ao registro, com as
    tuplas e os textos repetidos num objeto só."""
    if not isinstance(v, list) or len(v) != len(RegistroOS._fields):
        raise ValueError("linha da cópia com %r campos, o registro tem %d" % (
            len(v) if isinstance(v, list) else None, len(RegistroOS._fields)))
    d = dict(zip(RegistroOS._fields, v))
    if not isinstance(d["id"], int):
        raise ValueError("linha da cópia sem o id da OS")
    d["datas"] = _PACOTE.pack(*d["datas"])
    d["codigos"] = j(tuple(j(c) for c in d["codigos"] or ()))
    d["etiquetas"] = _p(tuple(_p((_p(e[0]), _p(e[1]))) for e in d["etiquetas"] or ()))
    d["ativo"], d["descricao"] = j(d["ativo"]), j(d["descricao"])
    for k in ("criado_por", "cod_criador", "id_criador", "atribuido_a", "id_atribuido", "equipe", "gatilho", "tipo_tarefa"):
        d[k] = _p(d[k])
    return RegistroOS(**d)


# ── a agenda ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def agendar(pasta: str | None, gravar) -> None:
    """Agenda `gravar()` (a gravação da versão do momento) para no máximo uma vez a cada `GRAVAR_A_CADA_S`, numa thread à
    parte. Com uma já agendada, nada: ela escreverá a versão de quando rodar. Sem pasta (os testes), nada."""
    if not pasta:
        return
    with _AGENDA_COND:
        if _AGENDA["pendente"]:
            return
        espera = max(0.0, _AGENDA["ultima"] + GRAVAR_A_CADA_S - time.time())
        t = threading.Timer(espera, _gravar_agendada, args=(gravar,))
        t.daemon = True
        t.name = "nexus-os-central-disco"
        _AGENDA.update(pendente=True, timer=t)
        t.start()


def _gravar_agendada(gravar) -> None:
    with _AGENDA_COND:
        if not _AGENDA["pendente"]:
            return                                                   # cancelada (o reinício dos testes)
        _AGENDA.update(pendente=False, ultima=time.time(), timer=None)
        _AGENDA["escrevendo"] += 1
    try:
        gravar()
    except Exception:                                                # noqa: BLE001 — o disco nunca derruba a lista
        log.exception("lista central de OS: a gravação em disco quebrou")
    finally:
        with _AGENDA_COND:
            _AGENDA["escrevendo"] = max(0, _AGENDA["escrevendo"] - 1)
            _AGENDA_COND.notify_all()


def esperar_gravacao(teto: float = 60.0) -> bool:
    """Espera a gravação agendada (e TODAS as que estão escrevendo) terminar, até `teto` segundos. True se não ficou
    nenhuma."""
    fim = time.monotonic() + max(0.0, float(teto))
    with _AGENDA_COND:
        while _AGENDA["pendente"] or _AGENDA["escrevendo"]:
            resta = fim - time.monotonic()
            if resta <= 0:
                return False
            _AGENDA_COND.wait(resta)
    return True


def cancelar() -> None:
    """Cancela a gravação agendada e esquece a última (o processo recém-subido dos testes). A que já está escrevendo termina
    e sai da conta sozinha."""
    with _AGENDA_COND:
        t = _AGENDA["timer"]
        if t is not None:
            t.cancel()
        _AGENDA.update(pendente=False, ultima=0.0, timer=None)
        _AGENDA_COND.notify_all()


# ── a gravação e a leitura ─────────────────────────────────────────────────────────────────────────────────────────────
def gravar_lista(pasta: str | None, vigente, estado_disco: dict, extras) -> bool:
    """A cópia da versão VIGENTE (`vigente()`, lida dentro da trava do disco), em fluxo: o cabeçalho (com `extras()`, as
    pendentes e as faixas, copiadas de uma vez por quem chama), uma linha JSON por OS e o fecho com a conta. Pula se o disco já
    tem esta versão e nada do cabeçalho mudou (`estado_disco["sujo"]`: a fila das pendentes anda sem a versão mudar, e a
    pendente que saiu da fila não volta no reinício; Minor 5 da rodada 1). Falha de disco vai ao log e a `estado_disco`; a
    lista segue na memória. True se gravou."""
    destino = caminho(pasta)
    if destino is None:
        return False
    with TRAVA:
        lista = vigente()
        if lista is None or (estado_disco.get("versao") == lista.versao and not estado_disco.get("sujo")):
            return False
        estado_disco["sujo"] = False                                 # o que mudar daqui em diante pede outra gravação
        # a marca d'água vai com a janela (rodada 2 da 3.3): sem ela, depois de cada deploy as telas iriam ao vivo até a
        # próxima leitura até o topo
        cab = dict({"formato": FORMATO, "versao": lista.versao, "lido_em": lista.lido_em, "janela": list(lista.janela),
                    "marca": getattr(lista, "marca", ""), "a_conferir": sorted(lista.a_conferir)}, **extras(),
                   n=len(lista.ordem), gravado_em=time.time(), campos=list(RegistroOS._fields))

        def escrever(tmp):
            with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=5, newline="\n") as f:
                f.write(json.dumps(cab, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")
                for r in lista.ordem:
                    f.write(json.dumps(_para_disco(r), ensure_ascii=False, separators=(",", ":")) + "\n")
                f.write(json.dumps({"fim": len(lista.ordem)}) + "\n")
        try:
            _trocar_de_uma_vez(destino, escrever)
        except Exception as e:                                       # noqa: BLE001 — o disco não derruba a lista
            estado_disco.update(erro="gravar: %s: %s" % (type(e).__name__, str(e)[:120]), sujo=True)
            log.warning("lista central de OS: não gravei a cópia em disco (%s)", estado_disco["erro"])
            return False
        try:
            tamanho = os.path.getsize(destino)
        except OSError:
            tamanho = None
        estado_disco.update(gravado_em=cab["gravado_em"], versao=lista.versao, bytes=tamanho, erro=None)
        return True


def ler_lista(pasta: str | None, estado_disco: dict, juntar):
    """(cabeçalho, {id: registro}) da cópia em disco, ou None: sem arquivo, ilegível, de outro formato, cortada no meio (o
    motivo fica em `estado_disco`). Lida linha a linha: nunca o arquivo inteiro na memória. `juntar`: o `_Juntar` da leitura
    (os textos repetidos num objeto só). Nunca levanta."""
    arq = caminho(pasta)
    if arq is None or not os.path.exists(arq):
        return None
    try:
        with gzip.open(arq, "rt", encoding="utf-8") as f:
            cab = json.loads(f.readline() or "null")
            if not isinstance(cab, dict) or cab.get("formato") != FORMATO:
                raise ValueError("formato %r, o esperado é %d" % (cab.get("formato") if isinstance(cab, dict) else None,
                                                                  FORMATO))
            if cab.get("campos") != list(RegistroOS._fields):
                raise ValueError("os campos do registro mudaram desde a gravação")
            n = int(cab.get("n"))
            por_id: dict = {}
            for _ in range(n):
                linha = f.readline()
                if not linha:
                    raise ValueError("a cópia acabou antes das %d OS que o cabeçalho diz" % n)
                r = _do_disco(json.loads(linha), juntar)
                por_id[r.id] = r
            if json.loads(f.readline() or "null") != {"fim": n}:
                raise ValueError("a cópia não tem o fecho (foi cortada no meio)")
        return cab, por_id
    except (OSError, EOFError, ValueError, TypeError, KeyError, IndexError, struct.error, zlib.error) as e:
        estado_disco["erro"] = "ler: %s: %s" % (type(e).__name__, str(e)[:120])
        log.warning("lista central de OS: ignorei a cópia em disco (%s)", estado_disco["erro"])
        return None
