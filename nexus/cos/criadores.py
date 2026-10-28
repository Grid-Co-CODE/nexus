"""Quem criou cada OS, para a tela Normalizações (27/10/2026, Levi: "Coluna de quem criou a OS" e o filtro "Criado
por").

A API das normalizações não manda nome de pessoa (regra da Ronda COS). Quem diz quem criou a OS é o Fracttal: o
`created_by` do REST (`work_orders?wo_folio=N`, a credencial do Nexus, só GET; `nexus/campo/fracttal.py`). O criador de
uma OS não muda: lido uma vez, fica.

O ritmo: a cota do Fracttal é de 200 pedidos por minuto para a EMPRESA inteira, e o App de Campo vive dela. As OS que
faltam entram numa fila e uma linha de fundo lê UMA a cada `PAUSA_S` (30 por minuto, 15% da cota); recusa por excesso
espera 1 minuto. Três meses de normalizações são ~4.500 OS: a 1ª carga leva horas, e a tela mostra "lendo" até lá.

Onde fica: na memória e, para o reinício (todo deploy) não refazer a leitura inteira, num arquivo da pasta de dados do
Nexus CIFRADO pelo Cofre (a chave do cadastro), como o cadastro guarda nome de pessoa. Sem a chave, só na memória.
"""
import json
import logging
import threading
import time
from pathlib import Path

log = logging.getLogger("nexus.cos")

ARQUIVO = "cos_criadores.cifrado"
CONTEXTO = "nexus/cos/criadores"
PAUSA_S = 2.0
ESPERA_RECUSA_S = 60
GRAVA_A_CADA = 20          # grava o arquivo a cada N OS lidas (e quando a fila esvazia)

_nomes: dict[str, str] = {}        # folio -> nome ("" = o Fracttal não disse quem criou)
_fila: list[str] = []
_trava = threading.Lock()
_laco = {"thread": None, "carregado": False}


def limpar() -> None:
    with _trava:
        _nomes.clear()
        _fila.clear()
        _laco["carregado"] = False


def _arquivo(config) -> Path | None:
    try:
        from ..cadastro.ligacoes import pasta_dados
        return pasta_dados(config) / ARQUIVO
    except RuntimeError:            # teste sem pasta própria: só memória
        return None


def _cofre(config):
    chave = config.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        return None
    from ..cadastro.cifra import Cofre
    return Cofre(chave)


def _carregar(config) -> None:
    """Uma vez por processo: o que já foi lido antes do reinício."""
    if _laco["carregado"]:
        return
    _laco["carregado"] = True
    p, cofre = _arquivo(config), _cofre(config)
    if not p or not cofre or not p.exists():
        return
    try:
        lido = json.loads(cofre.decifrar(p.read_text(encoding="utf-8"), CONTEXTO))
        if isinstance(lido, dict):
            _nomes.update({str(k): str(v) for k, v in lido.items()})
    except Exception:               # noqa: BLE001 — arquivo de outra chave ou estragado: lê de novo do Fracttal
        log.warning("Normalizações: o arquivo dos criadores das OS não abriu; lendo de novo do Fracttal")


def _gravar(config) -> None:
    p, cofre = _arquivo(config), _cofre(config)
    if not p or not cofre:
        return
    with _trava:
        texto = cofre.cifrar(json.dumps(_nomes, ensure_ascii=False), CONTEXTO)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".parcial")
    tmp.write_text(texto, encoding="utf-8")
    tmp.replace(p)


def nomes(folios, config, iniciar: bool = True) -> dict[str, str | None]:
    """{folio: nome} das OS pedidas: o nome, "" se o Fracttal não disse, None se ainda não foi lido (e entra na fila)."""
    with _trava:
        _carregar(config)
        out = {}
        # na ordem pedida (a tela manda a mais recente primeiro): a fila lê primeiro o que está no alto da tela
        for f in dict.fromkeys(str(x).strip() for x in folios if str(x or "").strip().isdigit()):
            out[f] = _nomes.get(f)
            if f not in _nomes and f not in _fila:
                _fila.append(f)
        faltam = bool(_fila)
    if faltam and iniciar:
        _iniciar()
    return out


def _nome_da_os(folio: str, ler) -> str:
    r = ler(f"work_orders?wo_folio={folio}&limit=1&start=0")
    linhas = (r.get("data") if isinstance(r, dict) else r) or []
    for l in linhas:
        nome = " ".join(str(l.get("created_by") or "").split())
        if nome:
            return nome
    return ""


def ler_fila(config, ler=None, maximo: int | None = None, pausa: float = 0.0) -> int:
    """Lê as OS da fila (até `maximo`), uma por vez. Devolve quantas leu. Recusa por excesso devolve a OS à fila e
    para (quem chama espera). O teste chama direto, sem a linha de fundo."""
    from ..campo import fracttal
    ler = ler or fracttal.ler
    lidas = 0
    while maximo is None or lidas < maximo:
        with _trava:
            if not _fila:
                break
            folio = _fila.pop(0)
        try:
            nome = _nome_da_os(folio, ler)
        except fracttal.Recusado:
            with _trava:
                _fila.insert(0, folio)
            raise
        except Exception:           # noqa: BLE001 — rede, 5xx: volta para o fim da fila
            with _trava:
                _fila.append(folio)
            raise
        with _trava:
            _nomes[folio] = nome
        lidas += 1
        if lidas % GRAVA_A_CADA == 0:
            _gravar(config)
        if pausa:
            time.sleep(pausa)
    if lidas:
        _gravar(config)
    return lidas


def _iniciar() -> None:
    from flask import current_app
    if current_app.config.get("TESTING"):
        return
    with _trava:
        t = _laco["thread"]
        if t is not None and t.is_alive():
            return
        app = current_app._get_current_object()
        t = threading.Thread(target=_rodar, args=(app,), name="nexus-cos-criadores", daemon=True)
        _laco["thread"] = t
    t.start()


def _rodar(app) -> None:
    from ..campo import fracttal
    with app.app_context():
        if not fracttal.configurado():
            log.info("Normalizações: sem a credencial do Fracttal, quem criou a OS não é lido")
            return
        while True:
            try:
                ler_fila(app.config, pausa=PAUSA_S)
                return
            except fracttal.Recusado:
                time.sleep(ESPERA_RECUSA_S)
            except Exception:       # noqa: BLE001
                log.exception("Normalizações: a leitura de quem criou a OS falhou; tento de novo em 1 minuto")
                time.sleep(ESPERA_RECUSA_S)


def na_fila() -> int:
    with _trava:
        return len(_fila)
