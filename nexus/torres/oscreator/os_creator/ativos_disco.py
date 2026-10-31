"""ativos_disco.py: a cópia em disco do catálogo de ativos e o estado que sobrevive ao reinício (31/10/2026, etapa 2 do canto
central do OS Creator).

Saiu do `ativos_central.py` na rodada 1 da revisão da tarefa 2.2 (Ruling AM: mecânico; o arquivo passava de 850 linhas). O
catálogo guarda e entrega; daqui saem só as gravações e as leituras do disco, sem estado próprio além da trava: a pasta, o
estado do disco e o catálogo vigente quem dá é o `ativos_central`, a cada chamada (os testes trocam a pasta por
`ativos_central.reiniciar(pasta=...)`, e o catálogo continua um só por processo).

O que mora na pasta (`<pasta de dados do clone>/oscreator/`):
- `ativos.json.gz`: a cópia do catálogo (gravada ao lado e trocada de uma vez, com o formato escrito dentro). Lida no boot:
  reiniciar o Nexus (~10 vezes por dia útil, a cada push na `main`) não pergunta nada ao Fracttal.
- `ativos_estado.json`: a leitura completa que o catálogo recusou por encolher (a recusa lembrada, ver `ativos_central.trocar`),
  a última conferência da leitura REST (a paridade) e a última leitura REST boa e a última que falhou (a prontidão do leitor):
  só na memória, cada reinício esqueceria a recusa (e o Fracttal seria relido) e desligaria os ativos novos até a noite.
- o `assets_cache.json` antigo, ao lado: lido UMA vez, como migração, se a cópia nova não existe.

A ordem das gravações (revisão 1 da 2.2): quem grava a cópia passa a pergunta "este catálogo ainda é o vigente?", feita
DENTRO da trava do disco. Uma troca pelo RPC e os novos do dia (`acrescentar`) instalam versões em sequência, mas gravam
depois de soltar a trava do catálogo: sem a pergunta, a versão mais velha podia chegar ao disco por último e voltar no reinício.
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import threading
import time
import zlib

log = logging.getLogger("oscreator.ativos_central")

FORMATO = 1                     # o formato dos arquivos; outro número = arquivo de outra versão do código, ignorado
FORMATO_LEGADO = 2              # o "ver" do assets_cache.json antigo (v2 = + id_parent/id_type_item/id_group_task)
NOME_ARQUIVO = "ativos.json.gz"
NOME_ESTADO = "ativos_estado.json"
TRAVA = threading.Lock()        # uma gravação por vez (a cópia e o estado)


def caminho(pasta: str | None) -> str | None:
    return os.path.join(pasta, NOME_ARQUIVO) if pasta else None


def caminho_estado(pasta: str | None) -> str | None:
    return os.path.join(pasta, NOME_ESTADO) if pasta else None


def _trocar_de_uma_vez(destino: str, escrever) -> None:
    """Escreve num rascunho ao lado e troca de uma vez (os.replace): quem reinicia no meio nunca lê um arquivo pela metade.
    O rascunho que sobrar de uma falha é apagado. Levanta o erro do disco para quem chama dizer onde."""
    tmp = "%s.%d.%d.tmp" % (destino, os.getpid(), threading.get_ident())
    try:
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        escrever(tmp)
        os.replace(tmp, destino)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def gravar_catalogo(pasta: str | None, cat, estado_disco: dict, ainda_vale) -> bool:
    """Grava a cópia do catálogo `cat`. `ainda_vale()` é perguntado DENTRO da trava: o catálogo que já não é o vigente não é
    gravado (a versão mais nova grava a dela). Falha de disco vai ao log e a `estado_disco` (o `estado()["disco"]` do
    catálogo), e o catálogo segue na memória. True se gravou."""
    destino = caminho(pasta)
    if destino is None:
        return False
    with TRAVA:
        if not ainda_vale():
            return False

        def escrever(tmp):
            carga = {"formato": FORMATO, "fonte": cat.fonte, "lido_em": cat.lido_em, "versao": cat.versao,
                     "novos_em": cat.novos_em, "registros": cat.lista}
            with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=5) as f:
                json.dump(carga, f, ensure_ascii=False, separators=(",", ":"))
        try:
            _trocar_de_uma_vez(destino, escrever)
            estado_disco.update(gravado_em=time.time(), lido_em=cat.lido_em, erro=None)
            return True
        except Exception as e:                                       # noqa: BLE001 — o disco não derruba o catálogo
            estado_disco["erro"] = "gravar: %s: %s" % (type(e).__name__, str(e)[:120])
            log.warning("catálogo de ativos: não consegui gravar a cópia em disco (%s)", estado_disco["erro"])
            return False


def ler_catalogo(pasta: str | None, estado_disco: dict):
    """(registros, lido_em, novos_em) da cópia em disco, ou None: sem arquivo, ilegível, de outro formato ou com a lista vazia
    (o motivo, se houve, fica em `estado_disco`). Nunca levanta."""
    arq = caminho(pasta)
    if arq is None or not os.path.exists(arq):
        return None
    try:
        with gzip.open(arq, "rt", encoding="utf-8") as f:
            carga = json.load(f)
        if not isinstance(carga, dict) or carga.get("formato") != FORMATO:
            raise ValueError("formato %r, o esperado é %d" % (carga.get("formato") if isinstance(carga, dict) else None,
                                                              FORMATO))
        registros = carga.get("registros")
        if not isinstance(registros, list) or not registros or not all(isinstance(r, dict) for r in registros):
            raise ValueError("sem a lista de registros")
        return registros, float(carga.get("lido_em") or 0.0), float(carga.get("novos_em") or 0.0)
    except (OSError, EOFError, ValueError, TypeError, zlib.error) as e:        # UnicodeError e JSONDecodeError são ValueError
        estado_disco["erro"] = "ler: %s: %s" % (type(e).__name__, str(e)[:120])
        log.warning("catálogo de ativos: ignorei a cópia em disco (%s)", estado_disco["erro"])
        return None


def gravar_estado(pasta: str | None, dados: dict) -> None:
    """O `ativos_estado.json` (a recusa lembrada, a paridade, a prontidão do REST), gravado de uma vez, como a cópia. Sem pasta
    (os testes), nada; falha de disco vai ao log e o estado segue na memória."""
    destino = caminho_estado(pasta)
    if destino is None:
        return
    with TRAVA:
        def escrever(tmp):
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(dict(dados, formato=FORMATO), f, ensure_ascii=False)
        try:
            _trocar_de_uma_vez(destino, escrever)
        except (OSError, TypeError, ValueError) as e:
            log.warning("catálogo de ativos: não gravei o %s (%s: %s)", NOME_ESTADO, type(e).__name__, str(e)[:120])


def ler_estado(pasta: str | None) -> dict | None:
    """O `ativos_estado.json` de antes do reinício, ou None (sem arquivo, ilegível ou de outro formato: ignorado)."""
    arq = caminho_estado(pasta)
    if arq is None or not os.path.exists(arq):
        return None
    try:
        with open(arq, encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict) or d.get("formato") != FORMATO:
            raise ValueError("formato %r" % (d.get("formato") if isinstance(d, dict) else None))
        return d
    except (OSError, ValueError, TypeError) as e:
        log.warning("catálogo de ativos: ignorei o %s (%s: %s)", NOME_ESTADO, type(e).__name__, str(e)[:120])
        return None


def ler_legado(arq: str | None):
    """(registros, ts) do `assets_cache.json` antigo (versão 2), ou None. Lido uma vez só, como migração."""
    if not arq or not os.path.exists(arq):
        return None
    try:
        with open(arq, encoding="utf-8") as f:
            c = json.load(f)
        if not isinstance(c, dict) or c.get("ver") != FORMATO_LEGADO:
            raise ValueError("versão %r, a esperada é %d" % (c.get("ver") if isinstance(c, dict) else None, FORMATO_LEGADO))
        ativos = c.get("assets")
        if not isinstance(ativos, list) or not ativos:
            raise ValueError("sem ativos")
        return ativos, float(c.get("ts") or 0.0)
    except (OSError, ValueError, TypeError) as e:
        log.warning("catálogo de ativos: ignorei o assets_cache.json antigo (%s: %s)", type(e).__name__, str(e)[:120])
        return None
