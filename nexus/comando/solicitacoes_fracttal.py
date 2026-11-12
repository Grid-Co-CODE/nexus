"""As solicitações do Fracttal que viraram OS, para os avisos de quem pediu no sino (11/11/2026).

Levi: "As notificações do fracttal também deve mostrar quando uma solicitação feita gera OS e deve chegar todas as
notificações dessa OS!". Até aqui o "Sua solicitação gerou uma OS" só nascia na aprovação feita pela Fila do PCM do OS
Creator (o evento `gerou_os`, `avisos.registrar_gerou_os`); a aprovada direto no Fracttal não avisava, porque saber dela
"custaria ler no Fracttal as solicitações de cada pessoa" (04/11/2026). O REST do Fracttal (a credencial do servidor, a mesma
da lista central de OS) tem a lista inteira: `GET /api/work_requests?since=` (sondado em 11/11/2026: 4.324 solicitações, 59 na
última semana), cada uma com quem pediu (`id_account`, `email_requested_by`, `requested_by`), a OS gerada (`id_work_order`,
`wo_folio`) e quem mudou o status por último (`requests_x_status_accounts_name`, quem aprovou).

POR TRÁS, NUNCA NA FRENTE DO SINO: o sino está em toda página. Uma thread lê as solicitações dos últimos `DIAS` a cada `TTL_S`
(1 a 3 páginas de `LIMITE`), guarda só as que têm OS, enxutas, na memória, e lê o motivo de cada OS delas que a lista central
de OS diz cancelada (o REST da OS pelo número, ~0,2 s, uma vez por OS: o cancelamento não muda). O sino só consulta a
memória: sem leitura ainda (a 1ª depois de subir), sai sem estes avisos e pede a leitura; a leitura que falha fica com a de
antes. Nada vai ao banco: o aviso nasce da leitura, como o de execução nasce da lista central, e só o "leu" é gravado.

A DATA DO CANCELAMENTO não existe no Fracttal (nem no REST da OS: só o motivo, `work_orders_status_custom_description`): o
aviso leva a hora em que este leitor viu a OS cancelada pela primeira vez (na memória; depois de reiniciar, a hora da nova
vista, com o mesmo aviso, que segue lido se já foi)."""
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

TTL_S = 300                 # a cada 5 min (a lista central de OS lê as novas no mesmo ritmo)
DIAS = 30                   # as solicitações feitas nos últimos 30 dias (a pedida antes e aprovada agora fica de fora)
LIMITE = 100                # por página do REST
MAX_LINHAS = 1000           # teto de páginas por leitura
MAX_MOTIVOS = 20            # motivos de cancelamento lidos por rodada
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_ESTADO = {"linhas": None, "lido": 0.0, "lendo": False}
_CANCEL: dict = {}          # id da OS -> {"motivo", "visto" (datetime de Brasília)}


def limpar() -> None:
    with _TRAVA:
        _ESTADO.update(linhas=None, lido=0.0, lendo=False)
        _CANCEL.clear()
        _MAPA.update(por_wid=None, lido=0.0, lendo=False)


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _int(v):
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _clone(nome):
    from ..torres.oscreator import ponte
    return ponte.modulo_do_clone(nome)


def enxuta(r: dict) -> dict | None:
    """A solicitação que virou OS, só com o que o sino usa. None sem OS."""
    wid = _int(r.get("id_work_order"))
    if wid is None:
        return None
    return {"codigo": _txt(r.get("id_code")), "id_account": _int(r.get("id_account")),
            "email": _txt(r.get("email_requested_by") or r.get("accounts_email")).lower(),
            "nome": _txt(r.get("requested_by") or r.get("accounts_name")), "wid": wid, "folio": _txt(r.get("wo_folio")),
            "aprovador": _txt(r.get("requests_x_status_accounts_name"))}


def ler_rest(agora: datetime | None = None, dias: int = DIAS, teto: int = MAX_LINHAS, pausa: float = 0.0) -> list[dict]:
    """As solicitações com OS feitas nos últimos `dias`, pelo REST (erro sobe: quem chama fica com a leitura de antes). O
    REST entrega no máximo 100 por página (sondado em 12/11/2026: o limit de 500 e 1000 devolve 99)."""
    api = _clone("api")
    agora = agora or datetime.now(_BRT)
    since = (agora - timedelta(days=dias)).strftime("%Y-%m-%dT00:00:00")
    out, start = [], 0
    while start < teto:
        if start and pausa:
            time.sleep(pausa)                       # a leitura inteira não gasta a cota da empresa de uma vez
        r = api._req("GET", "work_requests", params={"since": since, "limit": LIMITE, "start": start})
        d = (r.get("data") if isinstance(r, dict) else r) or []
        out += [x for x in (enxuta(l) for l in d if isinstance(l, dict)) if x]
        start += len(d)
        total = _int(r.get("total")) if isinstance(r, dict) else None
        if not d or total is None or start >= total:
            break
    return out


def _motivos(linhas: list[dict]) -> None:
    """O motivo de cada OS das solicitações que a lista central diz cancelada e que ainda não tem (uma vez por OS)."""
    try:
        lista = _clone("os_central").atual()
        api = _clone("api")
    except Exception:            # noqa: BLE001 — sem a lista central: os cancelamentos esperam a próxima rodada
        return
    feitas = 0
    for l in linhas:
        rec = lista.por_id.get(l["wid"]) if lista is not None else None
        if rec is None or rec.status_id != 4 or l["wid"] in _CANCEL or feitas >= MAX_MOTIVOS:
            continue
        feitas += 1
        try:
            motivo = _txt((api.cancelamento_da_os(l["folio"] or rec.folio) or {}).get("motivo"))
        except Exception:        # noqa: BLE001 — sem o motivo, o aviso sai sem ele
            motivo = ""
        with _TRAVA:
            _CANCEL.setdefault(l["wid"], {"motivo": motivo, "visto": datetime.now(_BRT)})


def _renovar(app) -> None:
    try:
        if app is not None:
            with app.app_context():
                linhas = ler_rest()
        else:
            linhas = ler_rest()
        with _TRAVA:
            _ESTADO.update(linhas=linhas, lido=time.monotonic())
        _motivos(linhas)
    except Exception as e:       # noqa: BLE001 — fica a leitura de antes; a próxima visita tenta
        log.warning("Solicitações do Fracttal: não consegui ler o REST (%s)", type(e).__name__)
    finally:
        with _TRAVA:
            _ESTADO["lendo"] = False


def _em_segundo_plano(fn):
    """Onde a leitura roda: uma thread solta (os testes trocam para rodar quando querem)."""
    threading.Thread(target=fn, daemon=True, name="nexus-solicitacoes-fracttal").start()


def preparar(app=None) -> None:
    """Pede a leitura por trás, se não há uma em vigor nem uma em andamento."""
    with _TRAVA:
        vencida = _ESTADO["linhas"] is None or time.monotonic() - _ESTADO["lido"] >= TTL_S
        if not vencida or _ESTADO["lendo"]:
            return
        _ESTADO["lendo"] = True
    _em_segundo_plano(lambda: _renovar(app))


def _ligado(app) -> bool:
    """`NEXUS_SOLICITACOES_FRACTTAL` = 1 liga e 0 desliga; sem ela, ligado fora dos testes (o teste nunca vai ao Fracttal; a
    cópia de prova liga com a variável)."""
    if app is None:
        return True
    v = str(app.config.get("NEXUS_SOLICITACOES_FRACTTAL") or "").strip()
    return v == "1" if v else not app.config.get("TESTING")


def atuais(app=None) -> tuple:
    """(as solicitações com OS, {id da OS: cancelamento}) da última leitura; ([], {}) sem leitura ainda. Nunca espera."""
    if _ligado(app):
        preparar(app)
    with _TRAVA:
        return list(_ESTADO["linhas"] or []), dict(_CANCEL)


# O MAPA OS → QUEM PEDIU, para o filtro Solicitante do Histórico de OS (Levi, 12/11/2026: "Solicitante (quem fez a abertura
# da solicitação, quando a OS foi gerada por uma solicitação e não direto de OS)"). O Histórico vai até 1 ano, e a leitura
# de 5 min cobre 30 dias: uma vez por dia, POR TRÁS, a leitura inteira (DIAS_MAPA, ~4.300 solicitações em 12/11/2026, umas
# 44 páginas com uma pausa entre elas); a leitura de 5 min soma as novas. Só na memória: o nome de quem pediu não vai ao
# banco por aqui
DIAS_MAPA = 400
TTL_MAPA_S = 24 * 3600
MAX_MAPA = 20000
PAUSA_MAPA_S = 0.3
_MAPA = {"por_wid": None, "lido": 0.0, "lendo": False, "versao": 0}


def _renovar_mapa(app) -> None:
    try:
        if app is not None:
            with app.app_context():
                linhas = ler_rest(dias=DIAS_MAPA, teto=MAX_MAPA, pausa=PAUSA_MAPA_S)
        else:
            linhas = ler_rest(dias=DIAS_MAPA, teto=MAX_MAPA, pausa=PAUSA_MAPA_S)
        with _TRAVA:
            _MAPA.update(por_wid={l["wid"]: l for l in linhas}, lido=time.monotonic(), versao=_MAPA["versao"] + 1)
    except Exception as e:       # noqa: BLE001 — fica o mapa de antes; amanhã tenta de novo
        log.warning("Solicitações do Fracttal: a leitura inteira não veio (%s)", type(e).__name__)
        with _TRAVA:
            _MAPA["lido"] = time.monotonic() - TTL_MAPA_S + 600      # a que falhou tenta de novo em 10 min, não a cada pedido
    finally:
        with _TRAVA:
            _MAPA["lendo"] = False


def preparar_mapa(app=None) -> None:
    with _TRAVA:
        vencido = _MAPA["por_wid"] is None and not _MAPA["lido"] or time.monotonic() - _MAPA["lido"] >= TTL_MAPA_S
        if not vencido or _MAPA["lendo"]:
            return
        _MAPA["lendo"] = True
    _em_segundo_plano(lambda: _renovar_mapa(app))


def solicitante_da_os(wid, app=None) -> str:
    """Quem pediu a solicitação que gerou a OS `wid`, "" quando ela não nasceu de uma (ou ainda não se sabe). Nunca espera:
    a leitura de 5 min (as novas) e o mapa do dia."""
    w = _int(wid)
    if w is None:
        return ""
    linhas, _c = atuais(app)
    if _ligado(app):
        preparar_mapa(app)
    l = next((x for x in linhas if x["wid"] == w), None) or (_MAPA["por_wid"] or {}).get(w)
    return (l or {}).get("nome") or ""


def versao_do_mapa() -> tuple:
    """Muda quando o mapa ou a leitura de 5 min mudam (o Histórico refaz as linhas guardadas com o Solicitante novo)."""
    with _TRAVA:
        return _MAPA["versao"], _ESTADO["lido"]


def ligar_historico(app):
    """O gancho que a ponte põe no Histórico do OS Creator (`rotas.SOLICITANTE_DA_OS`): o nome de quem pediu, por OS."""
    def fn(wid):
        return solicitante_da_os(wid, app)
    fn.versao = versao_do_mapa
    return fn


def da_os(wid, app=None) -> dict | None:
    """A solicitação que gerou a OS `wid` (o id do Fracttal), da última leitura (as feitas nos últimos DIAS); None sem ela.
    O Raio X da OS mostra quem pediu por aqui sem pedido a mais; a OS mais velha pergunta ao Fracttal depois que a página
    abre (`/os/api/os/<id>/solicitacao`, na sessão da pessoa)."""
    w = _int(wid)
    if w is None:
        return None
    linhas, _cancel = atuais(app)
    return next((l for l in linhas if l["wid"] == w), None)
