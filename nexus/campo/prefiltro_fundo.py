"""A leitura de fundo do pré-filtro da Aprovação de OS: os fatos das fotos de cada OS em verificação (as regras moram em
`prefiltro.py`). A tela nunca espera por isto: a visita só lê o que este módulo guardou.

Para cada OS da fila ainda não conferida (ou cujas tarefas mudaram), a mais nova primeiro: UM pedido de leitura ao
Fracttal (`work_orders_attachments?folio=`, 100 por página) e as imagens baixadas do S3, que não contam na cota de 200
pedidos por minuto da empresa (o link do anexo é o arquivo no S3). De cada foto ficam o hash sem o carimbo do App, a
hora de anexação (o `Last-Modified` do arquivo: o REST de anexos não dá data, medido em 28/10/2026) e o campo; os
bytes não ficam. A imagem é baixada porque a regra da foto repetida compara a própria imagem (o hash sem o carimbo):
a mesma foto anexada em dois campos ganha nome e carimbo diferentes. Miniatura não se guarda mais (Levi, 05/11/2026: "nem
precisa mostrar a foto de cara não... pode mostrar o nome das fotos"): o cartão mostra o nome, e o clique abre o card da
OS, onde as fotos estão.

- Roda depois de cada releitura da fila (`aprovacao._reler`) e no boot, numa thread declarada de fundo no porteiro do
  Fracttal; uma volta por vez, no máximo `NEXUS_PREFILTRO_POR_VOLTA` OS, com `NEXUS_PREFILTRO_PAUSA_S` entre elas (também
  depois de um erro). O Fracttal recusou (429): a volta espera `ESPERA_RECUSA_S` e segue com a próxima OS; com
  `RECUSAS_POR_VOLTA` recusas seguidas ela para e guarda o que leu (até 05/11/2026 parava na 1ª e só voltava na releitura
  da fila, 10 min depois: 3 OS em 40 min).
- **Só o que muda a coluna** (05/11/2026, "Tem 730 OSs conferindo fotos, veja se travou algo para seguir"): a OS fechada
  inteira fora do App não é lida (as fotos não mudam a coluna dela: já é Em dúvida, e a foto atrasada só se mede contra o
  fechamento no App), e na OS mista só as fotos das tarefas do App são baixadas. Eram 522 OS assim, 2.664 tarefas, uma
  com 66, na frente das 728 feitas pelo App. Quem é do App vem da conta pronta da fila (`aprovacao.tarefas_do_app`); sem
  ela, lê como antes.
- **A OS conferida é relida** (revisão de 05/11/2026): a OS é lida minutos depois de entrar na verificação, e a foto
  anexada "mais de 24 h depois do fechamento" só existe DEPOIS. Relê uma vez quando a janela de `NEXUS_PREFILTRO_HORAS_TARDE`
  desde o fim no Fracttal fecha e, depois, uma vez por dia enquanto a OS espera; só as fotos novas são baixadas (o id é o
  caminho no S3, que não muda). As OS novas passam na frente das relidas.
- Meia leitura nunca vira fato: a foto que não baixou deixa a OS sem fatos ("Ainda conferindo") até a próxima volta, porque
  a OS sem as fotos todas cairia em "Pronta" sem ter sido conferida; três falhas seguidas, e a OS espera 6 h. A foto que
  baixou mas não abre (upload cortado, arquivo que não é imagem) fica "não abriu", sem hash, e a OS segue (em dúvida).
- Fica em memória e em `dados/campo/prefiltro.json.gz` (cópia de trabalho, como a fila), gravada a cada 10 OS: cada push
  na `main` reinicia o servidor. A OS que sai da fila sai daqui e do disco (com as miniaturas de antes de 05/11/2026,
  quando ainda se guardavam); a fila vazia (soluço do
  Fracttal) não apaga nada. `ligado()` diz se a máquina lê (o servidor sim; o PC, com `NEXUS_CAMPO_AQUECER=0`, não).
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
POR_PAGINA = 100
MAX_PAGINAS = 20                  # 2.000 anexos numa OS; a maior da medição de 26/10 tinha 75
RELER_S = 24 * 3600               # a OS conferida é relida uma vez por dia enquanto espera a aprovação
TENTATIVAS, ESPERA_FALHA_S = 3, 6 * 3600
RECUSAS_POR_VOLTA = 5         # recusas seguidas do Fracttal (429) que param a volta
ESPERA_RECUSA_S = 60          # a espera depois de uma recusa, antes da próxima OS
GRAVAR_A_CADA = 10
_FATOS: dict = {}
_FALHAS: dict = {}                # {id_wo: [falhas seguidas, quando foi a última]}: foto que não baixou (passageiro)
_ESTADO = {"lendo": False, "erro": "", "erro_em": 0.0}
_TRAVA = threading.Lock()
_dormir = time.sleep
_agora = time.time


def ligado(config) -> bool:
    """A leitura das fotos roda nesta máquina? `NEXUS_PREFILTRO` decide quando dito ("0" desliga); sem ele, segue o
    `NEXUS_CAMPO_AQUECER`: o servidor aquece e lê, o PC (com 0) não. Revisão de 05/11/2026: ligado em toda máquina, a 1ª
    visita à Aprovação no PC começava a passada de ~2.000 OS fora do porteiro do servidor, na rede do escritório."""
    v = str((config or {}).get("NEXUS_PREFILTRO") or "").strip()
    if v:
        return v != "0"
    return str((config or {}).get("NEXUS_CAMPO_AQUECER") or "1").strip() != "0"


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
    """O que a tela diz da leitura: quantas OS conferidas, se está lendo, o último erro e quantas OS estão esperando
    depois de três downloads que falharam."""
    return {"conferidas": len(_FATOS), "lendo": _ESTADO["lendo"], "erro": _ESTADO["erro"],
            "falhas": sum(1 for n, _ in _FALHAS.values() if n >= TENTATIVAS)}


def _pasta() -> Path | None:
    """`dados/campo` (fora do git). Teste sem pasta própria: só memória."""
    if not has_app_context():
        return None
    from ..cadastro.ligacoes import pasta_dados
    try:
        return pasta_dados(current_app.config) / "campo"
    except RuntimeError:
        return None


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
    _FALHAS.pop(id_wo, None)
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


def _fim(tarefas: list[dict]) -> float | None:
    """O fim mais recente das tarefas no Fracttal (UTC), em segundos: o relógio da janela da releitura."""
    qs = [q for w in tarefas if (q := prefiltro._quando(w.get("final_date")))]
    return max(qs).timestamp() if qs else None


def _devida(f: dict, tarefas: list[dict], agora: float, p: dict) -> bool:
    """A OS já conferida precisa de nova leitura? Uma vez quando a janela da foto anexada depois fecha (lida antes dela,
    relida depois) e, fora isso, uma vez por dia."""
    lido = float(f.get("lido_em") or 0)
    if agora - lido >= RELER_S:
        return True
    fim = _fim(tarefas)
    return bool(fim) and lido < fim + p["horas_tarde"] * 3600 <= agora


def _hash(conteudo: bytes) -> str | None:
    """O hash sem o carimbo, ou None se a imagem não abre (upload cortado, arquivo que não é imagem, imagem gigante): a
    foto fica "não abriu", fora da comparação, e a OS segue. Antes, a exceção prendia a OS em "Ainda conferindo" para
    sempre, relendo tudo a cada volta (revisão de 05/11/2026)."""
    try:
        im = Image.open(io.BytesIO(conteudo))
        im.load()
        return format(prefiltro.dhash(im), "064x")
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return None


def _listar(folio: str) -> list[dict]:
    """Os anexos da OS, de 100 em 100. Para na página repetida e no teto: se o REST ignorar o `start`, a mesma página
    voltaria para sempre (revisão de 05/11/2026)."""
    rest, inicio, anterior = [], 0, None
    for _ in range(MAX_PAGINAS):
        pag = (fracttal.ler(f"work_orders_attachments?folio={quote(folio)}&limit={POR_PAGINA}&start={inicio}")
               or {}).get("data") or []
        marca = [str(a.get("value") or "") for a in pag]
        if not pag or marca == anterior:
            break
        rest += pag
        if len(pag) < POR_PAGINA:
            break
        anterior, inicio = marca, inicio + POR_PAGINA
    return rest


def _ler_os(tarefas: list[dict], p: dict, velho: dict | None = None, do_app: set[str] | None = None) -> dict:
    """Os fatos da OS. `velho` = os da leitura anterior: as fotos já lidas não são baixadas de novo. `do_app` = as tarefas
    da OS fechadas pelo App: só as fotos delas são baixadas (a foto sem tarefa, só se a OS inteira foi pelo App); None =
    todas."""
    folio = str(tarefas[0].get("wo_folio") or "")
    ids_tarefas = {str(w.get("id_work_orders_tasks")) for w in tarefas}
    toda_do_app = do_app is not None and ids_tarefas <= do_app
    conhecidos = {a["id"]: a for a in (velho or {}).get("anexos") or []}
    anexos, urls = [], {}
    for a in _listar(folio):
        url = str(a.get("value") or "")
        caminho = urlsplit(url).path
        tarefa = str(a.get("id_work_order_task") or "")
        if not IMG.search(caminho) or (tarefa and tarefa not in ids_tarefas):
            continue
        if do_app is not None and not (tarefa in do_app if tarefa else toda_do_app):
            continue                              # a foto da tarefa fora do App não é julgada: não é baixada
        id_ = hashlib.sha1(caminho.encode("utf-8")).hexdigest()[:16]
        if id_ in urls:                           # o mesmo arquivo listado duas vezes não vira "p02 é a mesma de p02"
            continue
        urls[id_] = url
        desc, imprime = _desc(a.get("description"))
        if id_ in conhecidos:                     # já lido: o arquivo no S3 não muda (o id é o caminho)
            anexos.append({**conhecidos[id_], "tarefa": tarefa, "desc": desc, "print": imprime})
            continue
        conteudo, anexada = baixar(url)           # falhou: sobe, e a OS fica para a próxima volta (nada pela metade)
        anexos.append({"id": id_, "tarefa": tarefa, "desc": desc, "anexada": anexada, "print": imprime,
                       "hash": _hash(conteudo)})
    pares = prefiltro.pares_repetidos([{**a, "hash": int(a["hash"], 16)} for a in anexos if a.get("hash")],
                                      p["dif"], p["dif_print"])
    return {"chave": _chave(tarefas), "lido_em": _agora(), "anexos": anexos, "pares": pares, "erro": ""}


def conferir(app, linhas: list[dict], cos: dict | None = None, do_app: dict[str, set[str]] | None = None) -> int:
    """Uma volta: as OS do escopo sem fatos (ou com tarefas que mudaram), a mais nova primeiro, e depois as conferidas
    que precisam ser relidas (`_devida`), a lida há mais tempo primeiro, até o teto. Quantas OS ficaram conferidas."""
    p = prefiltro.parametros(app.config if app else {})
    agora = _agora()
    with app.app_context() if app else _nada():
        grupos = _por_os(linhas)
        if not grupos:                # fila vazia é soluço do Fracttal (total 0): apagar tudo faria a próxima reler tudo
            return 0
        for id_wo in [k for k in _FATOS if k not in grupos]:
            _apagar(id_wo)
        for id_wo in [k for k in _FALHAS if k not in grupos]:
            _FALHAS.pop(id_wo, None)
        novas, relidas = [], []
        for k, ts in grupos.items():
            n, quando = _FALHAS.get(k, (0, 0.0))
            if (n >= TENTATIVAS and agora - quando < ESPERA_FALHA_S) or prefiltro.fora_do_escopo(ts, cos):
                continue
            folio = str(ts[0].get("wo_folio") or "")
            if do_app is not None and folio in do_app and not do_app[folio]:
                continue                          # fechada inteira fora do App: as fotos não mudam a coluna
            f = _FATOS.get(k)
            if f is None or f.get("chave") != _chave(ts):
                novas.append((k, ts))
            elif _devida(f, ts, agora, p):
                relidas.append((k, ts))
        novas.sort(key=lambda c: max(str(w.get("final_date") or "") for w in c[1]), reverse=True)
        relidas.sort(key=lambda c: float(_FATOS[c[0]].get("lido_em") or 0))
        lidas, recusas = 0, 0
        for k, ts in (novas + relidas)[:p["por_volta"]]:
            try:
                f = _ler_os(ts, p, _FATOS.get(k), (do_app or {}).get(str(ts[0].get("wo_folio") or "")))
            except fracttal.Recusado as e:
                recusas += 1
                if recusas >= RECUSAS_POR_VOLTA:
                    _ESTADO.update(erro=str(e)[:160], erro_em=time.time())
                    break
                _dormir(ESPERA_RECUSA_S)          # a cota volta em um minuto; a OS recusada fica para a próxima volta
                continue
            except Exception as e:      # noqa: BLE001 — foto que não baixou, S3 fora: passageiro, a OS fica para depois
                falha = _FALHAS.setdefault(k, [0, 0.0])
                falha[0], falha[1] = falha[0] + 1, agora
                logging.warning("pré-filtro: a OS %s não foi conferida (%s: %s)", ts[0].get("wo_folio"),
                                type(e).__name__, str(e)[:120])
                _dormir(p["pausa_s"])     # a pausa vale também depois do erro: com o S3 fora, a volta não queima a fila
                continue
            _FATOS[k] = f
            _FALHAS.pop(k, None)
            lidas, recusas = lidas + 1, 0
            if lidas % GRAVAR_A_CADA == 0:
                _gravar()                 # cada push na main reinicia o servidor: o lido até aqui não se perde
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
        from . import aprovacao
        conferir(app, list(regras_app._FILA_CACHE.get("linhas") or []), cos, aprovacao.tarefas_do_app())
    except Exception:      # noqa: BLE001
        logging.exception("pré-filtro: a volta de fundo falhou")
    finally:
        _ESTADO["lendo"] = False


def pedir_conferencia(app) -> None:
    """Uma volta por trás, se não há outra andando e a máquina lê (`ligado`). Nos testes não roda sozinha (os testes
    chamam `conferir`)."""
    if not ligado(app.config) or app.config.get("TESTING"):
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
    _FALHAS.clear()
    _ESTADO.update(lendo=False, erro="", erro_em=0.0)
