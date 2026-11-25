"""As cópias do PCM no Nexus conferidas com o PCM de AGORA (Levi, 24/11/2026: "Todas as mudanças que a gente fizer na
programação semanal e tudo mais, tem que se refletir nos relatórios do PCM também. A gente tem que garantir que isso seja
feito.").

O caso que criou: o Relatório Executivo do Nexus é uma cópia do JS do painel do PCM, de 14/10. O PCM mudou o relatório em
09/11 (o backoffice fora) e em 16/11 (a preventiva sempre no plano), e o Nexus seguiu com a cópia velha até 24/11 sem
ninguém saber: na W47 a Athon dava 55% num lado e 57% no outro (PA Leste 01). O teste do hash (`COPIAS`, o README do
motor) só prova que a cópia não foi mexida AQUI; não diz se o PCM mudou LÁ.

Esta conferência lê os arquivos do PCM de agora (o repositório é público, o mesmo de onde o `fonte` lê o banco), compara
com cada cópia e põe o aviso nas telas que usam a cópia (o Relatório Executivo e o Gerar a semana), até alguém atualizar
(o caminho está no CLAUDE.md de cada pasta). Roda por trás, numa thread, a cada `VALIDADE_S`: a tela nunca espera a
rede, e sem resultado ainda (ou com a rede fora) ela não avisa nada, porque aviso sem conferência seria chute.
"""
from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

RAIZ_PCM = "https://raw.githubusercontent.com/fillipefigueiro-source/gridco-pcm-data/main/"
AQUI = Path(__file__).resolve().parent
VALIDADE_S = 6 * 3600

# a cópia no Nexus (relativa a nexus/pcm) e o arquivo do PCM de onde ela vem, inteiro; a parte diz qual tela avisa
INTEIROS = {
    "relatorio_exec/relatorio_exec.js": "js/relatorio_exec.js",
    "relatorio_exec/relatorio_exec.css": "css/relatorio_exec.css",
    "motor/programacao_v7.py": "programacao_v7.py",
    "motor/fonte_bd_api.py": "fonte_bd_api.py",
    "motor/fora_da_programacao.py": "fora_da_programacao.py",
    "motor/gerar_bd_via_api.py": "gerar_bd_via_api.py",
}
# as cópias feitas de trechos: o gpv_cel.css (linhas 86 a 92 do css/preventivas.css) e o painel_pcm.js (as faixas do
# ferramentas/copiar_painel_pcm.py, refeitas aqui com os arquivos do PCM de agora)
GPV = ("relatorio_exec/gpv_cel.css", "css/preventivas.css", 86, 92)
PAINEL = "relatorio_exec/painel_pcm.js"

_estado: dict = {"r": None, "em": 0.0, "rodando": False}
_trava = threading.Lock()


def _texto(b) -> str:
    s = b.decode("utf-8") if isinstance(b, bytes) else str(b)
    return s.replace("\r\n", "\n")


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _baixar(caminho: str) -> str:
    import requests
    r = requests.get(RAIZ_PCM + caminho, timeout=20)
    r.raise_for_status()
    return _texto(r.content)


def _painel_de_agora(baixar) -> str:
    """O painel_pcm.js que o ferramentas/copiar_painel_pcm.py daria hoje (com o mesmo commit no cabeçalho da cópia)."""
    spec = importlib.util.spec_from_file_location(
        "copiar_painel_pcm", AQUI.parent.parent / "ferramentas" / "copiar_painel_pcm.py")
    cp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cp)
    cab = _texto((AQUI / PAINEL).read_bytes()).split("\n", 1)[0]
    commit = cab.split(", main ", 1)[1].split(")", 1)[0] if ", main " in cab else ""
    with tempfile.TemporaryDirectory() as tmp:
        for arq in sorted({t[0] for t in cp.TRECHOS}):
            destino = Path(tmp) / arq
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(baixar(arq), encoding="utf-8", newline="\n")
        return cp.gerar(Path(tmp), commit)


def conferir(baixar=_baixar) -> dict:
    """{"em", "diferentes": [{"copia", "do_pcm", "parte"}], "erro"}: cada cópia contra o arquivo do PCM de agora."""
    from .relatorio_exec import para_a_copia     # a troca do nome pelo papel que a cópia do executivo tem em disco
    dif, erro = [], ""
    try:
        for copia, do_pcm in INTEIROS.items():
            do_pcm_agora = baixar(do_pcm)
            if copia.startswith("relatorio_exec/"):
                do_pcm_agora = para_a_copia(do_pcm_agora)
            if _hash(_texto((AQUI / copia).read_bytes())) != _hash(do_pcm_agora):
                dif.append({"copia": copia, "do_pcm": do_pcm})
        copia, do_pcm, de, ate = GPV
        trecho = "\n".join(baixar(do_pcm).split("\n")[de - 1:ate])
        if _texto((AQUI / copia).read_bytes()).strip("\n") != trecho.strip("\n"):
            dif.append({"copia": copia, "do_pcm": f"{do_pcm} (linhas {de} a {ate})"})
        if _texto((AQUI / PAINEL).read_bytes()) != _painel_de_agora(baixar):
            dif.append({"copia": PAINEL, "do_pcm": "js/app.js e js/preventivas.js (os trechos)"})
    except Exception as e:                   # noqa: BLE001 — rede fora, 404, arquivo renomeado: sem conferência
        return {"em": datetime.now().isoformat(timespec="seconds"), "diferentes": [], "erro": f"{type(e).__name__}: {e}"}
    for d in dif:
        d["parte"] = d["copia"].split("/", 1)[0]
    return {"em": datetime.now().isoformat(timespec="seconds"), "diferentes": dif, "erro": erro}


def _renovar() -> None:
    try:
        r = conferir()
    finally:
        with _trava:
            _estado["rodando"] = False
    with _trava:
        _estado.update(r=r, em=time.time())


def estado(config) -> dict | None:
    """A última conferência; velha (ou nenhuma), pede outra por trás e devolve a que tem. Nos testes, a de
    `NEXUS_PCM_COPIAS_TESTE` (nunca a rede)."""
    if config.get("TESTING"):
        return config.get("NEXUS_PCM_COPIAS_TESTE")
    with _trava:
        velha = time.time() - _estado["em"] > VALIDADE_S
        if velha and not _estado["rodando"]:
            _estado["rodando"] = True
            threading.Thread(target=_renovar, name="conferir-copias-pcm", daemon=True).start()
        return _estado["r"]


def diferentes(config, parte: str) -> list[dict]:
    """As cópias de uma parte ("relatorio_exec" ou "motor") que ficaram atrás do PCM; vazio sem conferência."""
    r = estado(config) or {}
    return [d for d in r.get("diferentes") or [] if d.get("parte") == parte]
