"""A faxina do /tmp do usuário do serviço (28/11/2026).

O caso: a geração da semana do PCM pelo aplicativo do PC esbarrou duas vezes em "OSError: [Errno 122] Disk quota exceeded"
(a cota de disco do usuário do serviço no servidor, com 61 GB livres no disco). O "Disco do Nexus" do Raio-X mediu 17 GB
desse usuário, 6 GB deles em 2.543 arquivos soltos no /tmp que ninguém apagava (o Nexus e o PerformancePainel rodam com o
mesmo usuário, e arquivo temporário que um processo morto deixa fica para sempre).

A regra: de 6 em 6 horas, sai do /tmp só o ARQUIVO comum, direto no /tmp (não entra em pasta), deste usuário e parado há
mais de `DIAS` dias (o `/tmp` do sistema costuma limpar com 10; o temporário de verdade vive minutos). Link, pasta e
arquivo de outro usuário ficam. O resumo (`estado`) vai ao Raio-X: o que saiu na última faxina e o /tmp agrupado pelo
começo do nome, para achar quem cria o lixo.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
import time
from pathlib import Path

DIAS = 3
CADA_S = 6 * 3600
ESPERA_INICIAL_S = 300               # depois de subir: o boot já é pesado
log = logging.getLogger(__name__)
_ESTADO: dict = {"ultima": None, "ligada": False}
_TRAVA = threading.Lock()


def _pasta() -> Path:
    return Path(tempfile.gettempdir())


def _meus(pasta: Path):
    uid = os.getuid() if hasattr(os, "getuid") else None
    try:
        with os.scandir(pasta) as it:
            for e in it:
                try:
                    if not e.is_file(follow_symlinks=False):
                        continue
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                if uid is not None and st.st_uid != uid:
                    continue
                yield e, st
    except OSError:
        return


def faxinar(pasta: Path | None = None, agora: float | None = None, dias: float = DIAS) -> dict:
    """Apaga os arquivos parados há mais de `dias` (os deste usuário, direto na pasta). → {arquivos, mb, erros}."""
    pasta = pasta or _pasta()
    agora = time.time() if agora is None else agora
    out = {"arquivos": 0, "mb": 0.0, "erros": 0, "quando": time.strftime("%d/%m %H:%M")}
    for e, st in list(_meus(pasta)):
        if agora - st.st_mtime <= dias * 86400:
            continue
        try:
            os.unlink(e.path)
            out["arquivos"] += 1
            out["mb"] += st.st_size / 2**20
        except OSError:
            out["erros"] += 1
    out["mb"] = round(out["mb"], 1)
    with _TRAVA:
        _ESTADO["ultima"] = out
    if out["arquivos"]:
        log.info("faxina do /tmp: %s arquivos, %s MB", out["arquivos"], out["mb"])
    return out


def _grupo(nome: str) -> str:
    """O nome sem a parte que muda: o "tmpk3j2_xab.xlsx" do `tempfile` vira "tmp*.xlsx", e os números viram "#"."""
    base, ext = os.path.splitext(nome)
    if base.startswith("tmp") and len(base) >= 9:
        return "tmp*" + ext
    return re.sub(r"\d+", "#", base) + ext


def resumo(pasta: Path | None = None, agora: float | None = None) -> dict:
    """O /tmp deste usuário agrupado pelo começo do nome: os 8 grupos maiores, com quantos passam de `DIAS` dias."""
    pasta = pasta or _pasta()
    agora = time.time() if agora is None else agora
    grupos: dict = {}
    for e, st in _meus(pasta):
        g = grupos.setdefault(_grupo(e.name), {"grupo": _grupo(e.name), "arquivos": 0, "mb": 0.0, "velhos": 0})
        g["arquivos"] += 1
        g["mb"] += st.st_size / 2**20
        g["velhos"] += int(agora - st.st_mtime > DIAS * 86400)
    lista = sorted(grupos.values(), key=lambda g: -g["mb"])[:8]
    for g in lista:
        g["mb"] = round(g["mb"], 1)
    with _TRAVA:
        ultima = _ESTADO["ultima"]
    return {"pasta": str(pasta), "grupos": lista, "ultima": ultima, "dias": DIAS}


def ligar(app) -> None:
    """A faxina de 6 em 6 horas, a 1ª cinco minutos depois de subir. Só no servidor (fora dos testes)."""
    if app.config.get("TESTING") or _ESTADO["ligada"]:
        return
    _ESTADO["ligada"] = True

    def laco():
        time.sleep(ESPERA_INICIAL_S)
        while True:
            try:
                faxinar()
            except Exception:      # noqa: BLE001 — a faxina nunca derruba o Nexus
                log.exception("faxina do /tmp falhou")
            time.sleep(CADA_S)
    threading.Thread(target=laco, name="nexus-faxina-tmp", daemon=True).start()
