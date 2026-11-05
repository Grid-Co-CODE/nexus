"""A leitura de fundo do pré-filtro da Aprovação de OS: os fatos das fotos de cada OS em verificação (as regras moram em
`prefiltro.py`). A tela nunca espera por isto: a visita só lê o que este módulo guardou.

Para cada OS da fila ainda não conferida (ou cujas tarefas mudaram), a mais nova primeiro: UM pedido de leitura ao
Fracttal (`work_orders_attachments?folio=`, 100 por página) e as imagens baixadas do S3, que não contam na cota de 200
pedidos por minuto da empresa (o link do anexo é o arquivo no S3). De cada foto ficam o hash sem o carimbo do App, a
hora de anexação (o `Last-Modified` do arquivo: o REST de anexos não dá data, medido em 28/10/2026) e o campo; os
bytes não ficam. A miniatura (240 px) só das fotos repetidas, para o supervisor ver as duas lado a lado.

- Roda depois de cada releitura da fila (`aprovacao._reler`) e no boot, numa thread declarada de fundo no porteiro do
  Fracttal; uma volta por vez, no máximo `NEXUS_PREFILTRO_POR_VOLTA` OS, com `NEXUS_PREFILTRO_PAUSA_S` entre elas.
  O Fracttal recusou (429): a volta para e guarda o que leu; a próxima continua.
- Meia leitura nunca vira fato: uma foto que não baixou deixa a OS sem fatos ("Ainda conferindo") até a próxima volta,
  porque a OS sem as fotos todas cairia em "Pronta" sem ter sido conferida.
- Fica em memória e em `dados/campo/prefiltro.json.gz` (cópia de trabalho, como a fila); a OS que sai da fila sai daqui
  e do disco, com as miniaturas. `NEXUS_PREFILTRO=0` desliga o laço.
"""
import gzip
import hashlib
import io
import json
import logging
import os
import re
import threading
import time
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

from flask import current_app, has_app_context
from PIL import Image

from . import fracttal, prefiltro, regras_app

IMG = re.compile(r"\.(jpe?g|png|webp)$", re.I)
_ID = re.compile(r"^[0-9a-f]{16}$")
MINI_LADO = 240
POR_PAGINA = 100
_FATOS: dict = {}
_ESTADO = {"lendo": False, "erro": "", "erro_em": 0.0}
_TRAVA = threading.Lock()
_dormir = time.sleep


def baixar(url: str) -> tuple[bytes, str]:
    """A foto do S3 e a hora de anexação (o `Last-Modified`, em UTC). Trocada nos testes."""
    import requests
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    lm = r.headers.get("Last-Modified")
    return r.content, (parsedate_to_datetime(lm).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if lm else "")


def fatos(id_wo) -> dict | None:
    return _FATOS.get(str(id_wo))


def estado() -> dict:
    return {"conferidas": len(_FATOS), "lendo": _ESTADO["lendo"], "erro": _ESTADO["erro"]}


def _pasta() -> Path | None:
    """`dados/campo` (fora do git). Teste sem pasta própria: só memória."""
    if not has_app_context():
        return None
    from ..cadastro.ligacoes import pasta_dados
    try:
        return pasta_dados(current_app.config) / "campo"
    except RuntimeError:
        return None


def miniatura(id_anexo: str) -> Path | None:
    """O arquivo da miniatura da foto repetida, ou None (id que não é nosso, ou foto sem miniatura)."""
    pasta = _pasta()
    if pasta is None or not _ID.match(str(id_anexo or "")):
        return None
    arq = pasta / "prefiltro_fotos" / f"{id_anexo}.jpg"
    return arq if arq.exists() else None


def _gravar() -> None:
    pasta = _pasta()
    if pasta is None:
        return
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        arq = pasta / "prefiltro.json.gz"
        tmp = arq.with_name(arq.name + ".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump({"v": 1, "fatos": _FATOS}, f, ensure_ascii=False)
        os.replace(tmp, arq)
    except OSError as e:
        logging.warning("pré-filtro: não gravei a cópia em disco (%s)", e)


def carregar_do_disco(app) -> bool:
    """Os fatos guardados para a memória (o boot), se a memória ainda não tem nenhum."""
    with app.app_context():
        pasta = _pasta()
        arq = pasta / "prefiltro.json.gz" if pasta else None
        if arq is None or not arq.exists() or _FATOS:
            return False
        try:
            with gzip.open(arq, "rt", encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError, EOFError) as e:
            logging.warning("pré-filtro: cópia em disco ilegível (%s)", e)
            return False
    with _TRAVA:
        if not _FATOS:
            _FATOS.update(d.get("fatos") or {})
    return True


def _apagar(id_wo: str) -> None:
    f = _FATOS.pop(id_wo, None) or {}
    pasta = _pasta()
    if pasta is None:
        return
    for i in {x for par in f.get("pares") or [] for x in par}:
        try:
            (pasta / "prefiltro_fotos" / f"{i}.jpg").unlink(missing_ok=True)
        except OSError:
            pass


def _por_os(linhas: list[dict]) -> dict[str, list[dict]]:
    g: dict = {}
    for w in linhas or ():
        if w.get("id_work_order"):
            g.setdefault(str(w["id_work_order"]), []).append(w)
    return g


def _chave(tarefas: list[dict]) -> str:
    """As tarefas da OS em verificação: OS que ganhou ou perdeu tarefa é relida (a devolvida volta com outra foto)."""
    return ",".join(sorted(str(w.get("id_work_orders_tasks") or "") for w in tarefas))


def _desc(texto) -> tuple[str, bool]:
    """O campo da foto (sem o GPS e a hora que o App põe na descrição) e se é captura de tela (sem GPS)."""
    partes = [p.strip() for p in str(texto or "").split(" · ")]
    return " · ".join(p for p in partes[:1] if p), not any(p.startswith("GPS ") for p in partes)


def _ler_os(tarefas: list[dict], p: dict) -> dict:
    folio = str(tarefas[0].get("wo_folio") or "")
    rest, inicio = [], 0
    while True:
        pag = (fracttal.ler(f"work_orders_attachments?folio={quote(folio)}&limit={POR_PAGINA}&start={inicio}")
               or {}).get("data") or []
        rest += pag
        if len(pag) < POR_PAGINA:
            break
        inicio += POR_PAGINA
    ids_tarefas = {str(w.get("id_work_orders_tasks")) for w in tarefas}
    anexos, minis = [], {}
    for a in rest:
        url = str(a.get("value") or "")
        caminho = urlsplit(url).path
        tarefa = str(a.get("id_work_order_task") or "")
        if not IMG.search(caminho) or (tarefa and tarefa not in ids_tarefas):
            continue
        conteudo, anexada = baixar(url)          # falhou: sobe, e a OS fica para a próxima volta (nada pela metade)
        im = Image.open(io.BytesIO(conteudo))
        im.load()
        id_ = hashlib.sha1(caminho.encode("utf-8")).hexdigest()[:16]
        desc, imprime = _desc(a.get("description"))
        anexos.append({"id": id_, "tarefa": tarefa, "desc": desc, "anexada": anexada, "print": imprime,
                       "hash": format(prefiltro.dhash(im), "064x")})
        mini = im.convert("RGB")
        mini.thumbnail((MINI_LADO, MINI_LADO))
        buf = io.BytesIO()
        mini.save(buf, "JPEG", quality=80)
        minis[id_] = buf.getvalue()
    pares = prefiltro.pares_repetidos([{**a, "hash": int(a["hash"], 16)} for a in anexos], p["dif"], p["dif_print"])
    pasta = _pasta()
    if pasta is not None and pares:
        (pasta / "prefiltro_fotos").mkdir(parents=True, exist_ok=True)
        for i in {x for par in pares for x in par}:
            (pasta / "prefiltro_fotos" / f"{i}.jpg").write_bytes(minis[i])
    return {"chave": _chave(tarefas), "lido_em": time.time(), "anexos": anexos, "pares": pares, "erro": ""}


def conferir(app, linhas: list[dict], cos: dict | None = None) -> int:
    """Uma volta: confere as OS do escopo ainda sem fatos (ou com tarefas que mudaram), a mais nova primeiro, até o teto.
    Quantas OS ficaram conferidas."""
    p = prefiltro.parametros(app.config if app else {})
    with app.app_context() if app else _nada():
        grupos = _por_os(linhas)
        for id_wo in [k for k in _FATOS if k not in grupos]:
            _apagar(id_wo)
        candidatas = [(k, ts) for k, ts in grupos.items()
                      if (_FATOS.get(k) or {}).get("chave") != _chave(ts) and not prefiltro.fora_do_escopo(ts, cos)]
        candidatas.sort(key=lambda c: max(str(w.get("final_date") or "") for w in c[1]), reverse=True)
        lidas = 0
        for k, ts in candidatas[:p["por_volta"]]:
            try:
                f = _ler_os(ts, p)
            except fracttal.Recusado as e:
                _ESTADO.update(erro=str(e)[:160], erro_em=time.time())
                break
            except Exception as e:      # noqa: BLE001 — foto que não baixou, imagem ruim: a OS fica para a próxima volta
                logging.warning("pré-filtro: a OS %s não foi conferida (%s: %s)", ts[0].get("wo_folio"),
                                type(e).__name__, str(e)[:120])
                continue
            _FATOS[k] = f
            lidas += 1
            _dormir(p["pausa_s"])
        else:
            _ESTADO.update(erro="", erro_em=0.0)
        _gravar()
    return lidas


class _nada:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _volta(app) -> None:
    """A volta que a thread de fundo roda: a fila guardada e quem é do COS (para não ler à toa o que fica fora)."""
    try:
        # a cópia do disco antes de tudo: a volta do boot pode sair antes da thread que carrega o disco, e com a memória
        # vazia relia no Fracttal todas as OS já conferidas (a cada deploy)
        carregar_do_disco(app)
        with app.app_context():
            cos = None
            try:
                from ..cadastro import fracttal_pessoal
                from . import verificacao, visao
                cos = verificacao.criadores_cos(visao._base(), visao._sessao(), fracttal_pessoal.ler_pessoal)
            except Exception:      # noqa: BLE001 — sem o setor COS agora: lê também as do COS (só custa pedidos)
                cos = None
        conferir(app, list(regras_app._FILA_CACHE.get("linhas") or []), cos)
    except Exception:      # noqa: BLE001
        logging.exception("pré-filtro: a volta de fundo falhou")
    finally:
        _ESTADO["lendo"] = False


def pedir_conferencia(app) -> None:
    """Uma volta por trás, se não há outra andando. Nos testes não roda sozinha (os testes chamam `conferir`)."""
    if str(app.config.get("NEXUS_PREFILTRO", "1")) == "0" or app.config.get("TESTING"):
        return
    with _TRAVA:
        if _ESTADO["lendo"]:
            return
        _ESTADO["lendo"] = True
    from ..casca import fracttal_conta
    threading.Thread(target=fracttal_conta.de_fundo("fundo:nexus-prefiltro", lambda: _volta(app)), daemon=True,
                     name="nexus-prefiltro").start()


def limpar() -> None:
    _FATOS.clear()
    _ESTADO.update(lendo=False, erro="", erro_em=0.0)
