"""os_leitor.py: o histórico de OS lido pelo PRÓPRIO servidor, em faixas fora do pico (31/10/2026, etapa 3 do canto central
do OS Creator; desenho `docs/superpowers/specs/2026-10-30-oscreator-canto-central-design.md`, "Etapa 3").

Enche a lista central de OS (`os_central.py`) pela credencial da empresa (o REST `work_orders`), 1 pedido por segundo, pelas
MESMAS funções e pela mesma paginação do `nexus/campo/tarefas_os.py` (o leitor de OS do Nexus; não nasce outro). As faixas
(os números são o ponto de partida do desenho; os minutos fixos fogem dos minutos ocupados do Nexus, que moram num lugar só,
`nexus/casca/minutos_ocupados.py`):
- AS NOVAS (`ler_novas`): da criação mais nova para trás até a 1ª página inteira de OS que a lista já tem (1 pedido sem
  novidade, 2 com; sem o pedido do total), a cada 3 min das 06:00 às 20:00 de segunda a sexta e a cada 15 min fora disso (em
  qualquer minuto: são 1 ou 2 pedidos). Mais de 4 páginas de novas: nada entra, ficam para os 7 dias. A lista sem uma leitura
  até o topo (a máquina sem cópia) espera os 7 dias ou a noite;
- OS 7 DIAS (`ler_sete_dias`): as criadas nos últimos 7 dias relidas inteiras (até uma página INTEIRA mais velha que o piso;
  sem o pedido do total, que no `work_orders` sem filtro é o de todas as OS), a cada 10 min das 06:00 às 20:00 (:00, :21, :30,
  :41 e :51: o :10, o :20, o :40 e o :50 têm dono);
- AS ABERTAS (status 1 e 2): ENTREGUES pela volta de hora em hora do `tarefas_os`, que já as lê para o fato (`entregar_abertas`,
  sem pedido a mais). Ela só lê na máquina que vai gravar (pula se a outra gravou há menos de 50 min): sem entrega em 70 min,
  este leitor as lê ele mesmo pela mesma função (`tarefas_os.ler_abertas`), no máximo uma vez por hora (:55). Custo: ~98
  pedidos na escala do AC (~99 OS por dia) numa hora em que o PC gravou;
- AS FINALIZADAS (`ler_finalizadas`, :46 de toda hora: o :45 é do `uso_os` às 03:45): status 3 pela data de fim, desde a mais
  nova que a lista conhece (nunca depois de agora: a data fim no futuro, dado ruim, não trava a faixa) menos 2 dias, parando
  quando uma página INTEIRA passa do piso (a leitura do desenho do PCM de 27/10; o fato `fato_tarefa_finalizada` não é
  publicado aqui). A lista sem nenhuma concluída espera a noite;
- A NOITE (`ler_noite`, 03:21: o :20 é das tarefas): os últimos 90 dias inteiros; no domingo, ou sem a janela lida inteira (a
  1ª carga, a cópia com janela menor), a janela toda (365 dias). As antigas mudam sem data de alteração: é a noite que as põe
  em dia e tira o que sumiu;
- AS PENDENTES (`ler_pendentes`, depois das novas e dos 7 dias): a OS que uma ação do OS Creator mexeu fora de um pedido, pelo
  nº, até 5 por vez (1 pedido cada, cada um depois da pausa de 1 s). A apagada no Fracttal sai da fila; a que derruba a
  leitura sai depois de 5 falhas, e as de menos falhas vêm antes (rodada 1 da revisão).
Leitura que falha no meio (a página recusada três vezes, sem a lista, repetida; a conexão que cai) não chama o `receber`: a
lista fica como estava, e o estado diz qual faixa falhou e por quê. A exceção que não é falha de leitura é DEFEITO do leitor:
vai ao log com a pilha, e o estado diz `defeito`. Cada faixa conta no contador de pedidos do Fracttal com o nome dela
(`fundo:nexus-os-leitor:<faixa>`, `nexus/casca/fracttal_conta.py`).
AS GUARDAS (Rulings AU e AV, rodada 1 da revisão da 3.1+3.2): as três faixas pela criação conferem a ordem do REST
(`tarefas_os.ler_criadas`, com o topo: a criação mais nova que a lista conhece menos 3 dias); a noite e os 7 dias que
encolheriam a lista são recusados por ela (`os_central`, a trava de encolhimento), e a faixa diz por quê; e cada página
chega cortada no que a lista lê (`os_registro.enxuta`), as abertas entregues pelo `tarefas_os` também: a noite de 365 dias não
junta 90 mil linhas inteiras na memória.

Só o `servir.py` liga (`ligar`); o `app.py` (o PC) e os testes seguem sem ele, como o `nexus/casca/teto_os.py`. Sem a
credencial REST (o PC, a worktree sem `FRACTTAL_CLIENT_ID`) ele não liga, o estado diz por quê, e as telas seguem ao vivo.
"""
from __future__ import annotations

import contextlib
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

import os_central
import os_registro
from nexus.campo import fracttal, tarefas_os
from nexus.casca import minutos_ocupados as MO

log = logging.getLogger("oscreator.os_leitor")

NOVAS, SETE_DIAS, ABERTAS, FINALIZADAS, NOITE, PENDENTES = (
    "novas", "sete_dias", "abertas", "finalizadas", "noite", "pendentes")
PRIORIDADE = {NOITE: 0, SETE_DIAS: 1, ABERTAS: 2, FINALIZADAS: 3, NOVAS: 4}      # no mesmo minuto, a de cima vence
DIA_UTIL_DAS, DIA_UTIL_ATE = 6, 20            # o horário de trabalho: as novas de 3 em 3 min, de segunda a sexta
NOVAS_DIA_MIN, NOVAS_FORA_MIN = 3, 15
SETE_DIAS_DAS, SETE_DIAS_ATE = 6, 20          # os 7 dias, de 10 em 10 min, todos os dias
# os minutos fixos moram na lista única dos minutos ocupados (Minor 1 da rodada 1): os 7 dias nos minutos livres de 10 em 10, as
# finalizadas no :46 (o :45 é do `uso_os` às 03:45), a conferência das abertas no :55 e a noite às 03:21 (o :20 é das tarefas)
SETE_DIAS_MINUTOS = MO.OS_SETE_DIAS
FINALIZADAS_MINUTO = MO.OS_FINALIZADAS
ABERTAS_MINUTO = MO.OS_ABERTAS
NOITE_HORA = MO.OS_NOITE
DIAS_SETE = 7
DIAS_NOITE = 90
MARGEM_FINALIZADAS_DIAS = 2
SEM_ENTREGA_S = 70 * 60                       # sem entrega do `tarefas_os` nesse tempo, as abertas são lidas aqui
ABERTAS_PROPRIAS_MIN_S = 50 * 60              # e no máximo uma vez por hora (a conferência é no :55 de toda hora)
PAGINAS_NOVAS_MAX = 5                         # mais de 400 OS novas desde a última leitura: ficam para os 7 dias
PAGINAS_SETE_MAX = 150
PAGINAS_NOITE_MAX = 1500                      # a janela inteira (~900 páginas no desenho) com folga; o teto não corta calado
PAGINAS_FINALIZADAS_MAX = 50
PENDENTES_MAX = 5
MARGEM_TOPO_DIAS = 3                          # a 1ª página pela criação chega à mais nova que a lista conhece menos isto
CHAVE = "oscreator_os_leitor"
_BRT_S = -3 * 3600                            # Brasília é UTC-3 fixo

_dormir = time.sleep                          # o laço e a pausa das pendentes (os testes trocam)
_TRAVA = threading.Lock()                     # uma leitura da lista por vez
_APP: dict = {"app": None}


def _estado_limpo() -> dict:
    # `faixas`: a última leitura de cada faixa (início, fim, pedidos, OS, o resultado e o erro); `entregas`: quando chegaram
    # as abertas por último, do `tarefas_os` e deste leitor (a regra das 70 min)
    return {"ligado": False, "motivo": "não ligado (só o servir.py liga o leitor)", "credencial": None, "faixas": {},
            "entregas": {"tarefas_os": 0.0, "os_leitor": 0.0}}


_ESTADO: dict = _estado_limpo()


def _int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError, OverflowError):
        return None


def _iso_utc(epoca: float) -> str:
    return datetime.fromtimestamp(epoca, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _motivo(e: BaseException) -> str:
    return "%s: %s" % (type(e).__name__, str(e)[:200])


class ListaRecusou(RuntimeError):
    """A lista recusou a leitura (a trava de encolhimento do `os_central.receber`, Ruling AU): nada mudou."""


# as falhas de LEITURA (Minor 2 da rodada 1): a incompleta (e a fora de ordem), a recusa do Fracttal e a rede (o `requests`
# levanta `OSError`). Qualquer outra exceção é defeito do leitor, e vai ao log com a pilha
_FALHAS_DE_LEITURA = (tarefas_os.LeituraIncompleta, fracttal.Recusado, OSError)


def _ler_padrao(ler):
    return ler if ler is not None else fracttal.ler


@contextlib.contextmanager
def _origem(faixa: str):
    """Cada faixa conta no contador do Fracttal com o nome dela (`fundo:nexus-os-leitor:<faixa>`): o Raio-X e o livro do uso
    dizem quanto cada uma gasta da cota da empresa."""
    try:
        from nexus.casca import fracttal_conta
    except Exception:                                                # noqa: BLE001 — sem o contador, a leitura segue
        yield
        return
    with fracttal_conta.origem("fundo:nexus-os-leitor:" + faixa):
        yield


def _rodar(faixa: str, ler, fazer) -> dict:
    """Uma faixa: `fazer(ler, rel)` lê (contando cada pedido) e entrega ao `os_central.receber`. A falha no meio da leitura (a
    incompleta, a fora de ordem, a recusa, a conexão) não deixa o `receber` acontecer, e a lista que recusa a leitura não troca
    nada: a lista fica como estava, e o relatório diz. Outra exceção é defeito do leitor: log com a pilha e `defeito` no
    relatório (Minor 2 da rodada 1)."""
    rel = {"faixa": faixa, "inicio": time.time(), "fim": None, "pedidos": 0, "os": 0, "linhas": 0, "resultado": "",
           "erro": ""}
    if not _TRAVA.acquire(blocking=False):
        rel.update(fim=time.time(), resultado="já havia uma leitura da lista em curso: esta fica para a próxima vez")
        return rel
    conta = [0]
    base = _ler_padrao(ler)

    def contando(path):
        conta[0] += 1
        return base(path)
    try:
        with _origem(faixa):
            fazer(contando, rel)
    except ListaRecusou as e:
        rel["erro"] = str(e)
        rel["resultado"] = "a lista recusou a leitura (%s): nada mudou" % rel["erro"]
        log.warning("leitor de OS: %s: %s", faixa, rel["resultado"])
    except tarefas_os.ForaDeOrdem as e:
        rel["erro"] = _motivo(e)
        rel["resultado"] = "o REST não devolveu as OS pela criação (%s): nada mudou" % rel["erro"]
        log.warning("leitor de OS: %s: %s", faixa, rel["resultado"])
    except _FALHAS_DE_LEITURA as e:
        rel["erro"] = _motivo(e)
        rel["resultado"] = "a leitura não veio inteira (%s): nada mudou" % rel["erro"]
        log.warning("leitor de OS: %s: %s", faixa, rel["resultado"])
    except Exception as e:                                           # noqa: BLE001 — o defeito não derruba o laço
        rel.update(erro=_motivo(e), defeito=True,
                   resultado="defeito do leitor (%s): a faixa parou no meio; a pilha está no log" % _motivo(e))
        log.exception("leitor de OS: %s: defeito do leitor", faixa)
    finally:
        rel.update(pedidos=conta[0], fim=time.time())
        _ESTADO["faixas"][faixa] = rel
        _TRAVA.release()
    return rel


def _receber(rel: dict, linhas, faixa: str, **kw) -> dict:
    r = os_central.receber(linhas, faixa, quem="os_leitor", **kw)
    if r.get("recusa"):
        raise ListaRecusou(r["recusa"])
    rel.update(os=r["os"], linhas=r["linhas"],
               resultado="%d OS: %d entraram, %d mudaram, %d a conferir, %d saíram" % (
                   r["os"], r["entraram"], r["mudaram"], r["a_conferir"], r["sairam"]))
    return r


def _topo_minimo(inicio: float) -> str:
    """Até onde a 1ª página da leitura pela criação tem de chegar (Ruling AU): a criação mais nova que a lista conhece (nunca
    depois do começo da leitura: a data no futuro, dado ruim, não trava as faixas) menos `MARGEM_TOPO_DIAS`; com a lista vazia
    (a 1ª carga), o próprio começo menos a margem (o Fracttal da empresa cria ~99 OS por dia: 3 dias sem nenhuma na 1ª página
    é o REST devolvendo da mais velha para a mais nova). A margem cobre a OS mais nova apagada no Fracttal."""
    mais_nova = os_central.mais_nova_criacao()
    topo = min(mais_nova, inicio) if mais_nova else inicio
    return _iso_utc(topo - MARGEM_TOPO_DIAS * 86400)


# ── as faixas ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def ler_novas(ler=None) -> dict:
    """As OS criadas desde a página conhecida: só somam (`os_central.NOVAS`), e o fim da janela anda quando a leitura emenda
    com o que a lista já leu inteiro."""
    def fazer(ler, rel):
        lista = os_central.atual()
        if not lista.por_id or not lista.janela[1]:
            rel["resultado"] = "a lista ainda não tem uma leitura até o topo (os 7 dias ou a noite): as novas esperam"
            return
        conhecidas = lista.por_id

        def conhecida(pagina):
            ids = {_int(w.get("id_work_order")) for w in pagina}
            return bool(ids) and all(i in conhecidas for i in ids)
        inicio = time.time()
        linhas = tarefas_os.ler_criadas(ler, conhecida=conhecida, topo_minimo=_topo_minimo(inicio),
                                        paginas_max=PAGINAS_NOVAS_MAX, com_total=False, projetar=os_registro.enxuta)
        datas = [str(w.get("creation_date"))[:19] for w in linhas if w.get("creation_date")]
        _receber(rel, linhas, os_central.NOVAS, desde=min(datas) if datas else None, lido_em=inicio)
    return _rodar(NOVAS, ler, fazer)


def ler_sete_dias(ler=None) -> dict:
    """As OS criadas nos últimos 7 dias, relidas inteiras: o status, o responsável e as datas das recentes em dia."""
    def fazer(ler, rel):
        inicio = time.time()
        piso = _iso_utc(inicio - DIAS_SETE * 86400)
        linhas = tarefas_os.ler_criadas(ler, piso=piso, topo_minimo=_topo_minimo(inicio), paginas_max=PAGINAS_SETE_MAX,
                                        com_total=False, projetar=os_registro.enxuta)
        _receber(rel, linhas, os_central.SETE_DIAS, desde=piso, lido_em=inicio)
    return _rodar(SETE_DIAS, ler, fazer)


def noite_inteira(agora: float, janela: tuple | None = None) -> bool:
    """A noite lê a janela INTEIRA: no domingo, ou quando a lista não leu inteira a janela toda (a 1ª carga, sem cópia em disco,
    ou a cópia de uma janela menor: decisão AG). Nos outros dias, os últimos 90."""
    if int(((agora + _BRT_S) // 86400 + 3) % 7) == 6:              # 01/01/1970 foi uma quinta; 6 = domingo
        return True
    de = (os_central.atual().janela if janela is None else janela)[0]
    if not de:
        return True
    piso = (datetime.fromtimestamp(agora, timezone.utc) - timedelta(days=os_central.JANELA_DIAS - 1)).strftime("%Y-%m-%d")
    return de > piso


def ler_noite(ler=None, inteira: bool | None = None) -> dict:
    """A reconciliação da madrugada: os últimos 90 dias (ou a janela inteira) relidos; o que não voltou sai de vez."""
    def fazer(ler, rel):
        inicio = time.time()
        toda = noite_inteira(inicio) if inteira is None else inteira
        desde = (datetime.fromtimestamp(inicio, timezone.utc)
                 - timedelta(days=os_central.JANELA_DIAS if toda else DIAS_NOITE)).strftime("%Y-%m-%d")
        rel["janela_inteira"] = toda
        linhas = tarefas_os.ler_criadas(ler, piso=desde, topo_minimo=_topo_minimo(inicio), paginas_max=PAGINAS_NOITE_MAX,
                                        com_total=False, projetar=os_registro.enxuta)
        _receber(rel, linhas, os_central.NOITE, desde=desde, lido_em=inicio)
    return _rodar(NOITE, ler, fazer)


def entregar_abertas(linhas, lido_em: float | None = None) -> dict:
    """O gancho do `tarefas_os` (`ligar_entrega_das_abertas`): as tarefas de status 1 e 2 que a volta de hora em hora acabou
    de ler inteiras entram na lista, sem pedido a mais, cortadas no que a lista lê antes de tudo (Ruling AV)."""
    linhas = [os_registro.enxuta(w) for w in linhas or ()]
    r = os_central.receber(linhas, os_central.ABERTAS, lido_em=lido_em, quem="tarefas_os")
    _ESTADO["entregas"]["tarefas_os"] = float(lido_em or time.time())
    return r


def precisa_das_abertas(agora: float | None = None) -> bool:
    """Sem entrega do `tarefas_os` em 70 min (a volta desta máquina pulou: a outra gravou), e sem leitura própria na última
    hora: as abertas são lidas aqui."""
    agora = time.time() if agora is None else agora
    e = _ESTADO["entregas"]
    return agora - e["tarefas_os"] > SEM_ENTREGA_S and agora - e["os_leitor"] > ABERTAS_PROPRIAS_MIN_S


def ler_abertas(ler=None) -> dict:
    """As abertas lidas por este leitor, pela MESMA função do `tarefas_os` (`ler_abertas`: nada de paginação duplicada)."""
    def fazer(ler, rel):
        inicio = time.time()
        linhas = tarefas_os.ler_abertas(ler, projetar=os_registro.enxuta)
        _receber(rel, linhas, os_central.ABERTAS, lido_em=inicio)
        _ESTADO["entregas"]["os_leitor"] = inicio
    return _rodar(ABERTAS, ler, fazer)


def ler_finalizadas(ler=None) -> dict:
    """As finalizadas desde a data de fim mais nova que a lista conhece (nunca depois de agora) menos 2 dias: o status 3 e a
    data fim das OS que a lista já tem (o que mudou numa OS antiga sem data de alteração). A data fim no futuro (dado ruim)
    viraria um piso no futuro, e as concluídas de hoje ficariam de fora até ela passar (Minor 8 da rodada 1)."""
    def fazer(ler, rel):
        mais_nova = os_central.mais_nova_data_fim()
        if not os_central.atual().por_id or not mais_nova:
            rel["resultado"] = "a lista ainda não tem OS concluída (a carga da noite traz): as finalizadas esperam"
            return
        inicio = time.time()
        fim = min(datetime.fromisoformat(mais_nova).replace(tzinfo=timezone.utc),
                  datetime.fromtimestamp(inicio, timezone.utc))
        piso = (fim - timedelta(days=MARGEM_FINALIZADAS_DIAS)).strftime("%Y-%m-%dT%H:%M:%S")
        linhas = tarefas_os.ler_finalizadas(ler, piso, paginas_max=PAGINAS_FINALIZADAS_MAX, projetar=os_registro.enxuta)
        _receber(rel, linhas, os_central.FINALIZADAS, desde=piso, lido_em=inicio)
    return _rodar(FINALIZADAS, ler, fazer)


def ler_pendentes(ler=None) -> dict | None:
    """As OS que uma ação do OS Creator mexeu fora de um pedido (`os_central.atualizar_os` sem a sessão), relidas pelo nº, até
    `PENDENTES_MAX` por vez, as de menos falhas primeiro (`os_central.fila_de_pendentes`). Cada pedido vem depois da pausa de
    1 s, o 1º também: as pendentes vêm logo depois das novas e dos 7 dias, e nunca há 2 pedidos colados (Minor 6 da rodada 1).
    A que o nº não traz mais (apagada no Fracttal) sai da fila e segue "a conferir" até a noite; a leitura que falha conta uma
    falha para aquela OS (na `os_central.PENDENTE_FALHAS_MAX`-ésima ela sai da fila) e encerra a volta, e as outras ficam para
    a próxima sem falha contada (a rede caída ou a recusa do Fracttal não vira cinco esperas seguidas). Assim as pendentes
    mortas não travam a fila (Minor 5). A que a lista não tem (o nº não se sabe) vem com as novas. None sem nenhuma."""
    alvos = os_central.fila_de_pendentes(PENDENTES_MAX)
    if not alvos:
        return None

    def fazer(ler, rel):
        inicio = time.time()
        linhas, lidas, falha = [], [], ""
        for wid, folio in alvos:
            _dormir(tarefas_os.PAUSA_S)
            try:
                linhas += tarefas_os.ler_os(ler, folio, projetar=os_registro.enxuta)
            except Exception as e:                                   # noqa: BLE001 — a OS que falha conta, e a volta para
                if not isinstance(e, _FALHAS_DE_LEITURA):
                    rel["defeito"] = True
                    log.exception("leitor de OS: pendentes: defeito ao ler a OS %s pelo nº", wid)
                saiu = os_central.falhou_pendente(wid)
                falha = "a leitura da OS %s pelo nº falhou (%s)%s" % (
                    wid, _motivo(e), "; ela saiu da fila depois de %d falhas" % os_central.PENDENTE_FALHAS_MAX if saiu
                    else "")
                break
            lidas.append(wid)
        if lidas:
            _receber(rel, linhas, os_central.UMA_OS, ids=lidas, lido_em=inicio)
        if falha:
            rel["erro"] = falha
            rel["resultado"] = "; ".join(x for x in (rel["resultado"], falha) if x)
            log.warning("leitor de OS: pendentes: %s", falha)
    return _rodar(PENDENTES, ler, fazer)


# ── os horários e o laço ───────────────────────────────────────────────────────────────────────────────────────────────
def proximo_passo(agora: float) -> tuple:
    """(segundos, passo) do próximo compromisso, em Brasília: a noite às 03:21; os 7 dias aos `SETE_DIAS_MINUTOS` das 06h às
    20h; as finalizadas no :46 e a conferência das abertas no :55 de toda hora; as novas de 3 em 3 min das 06h às 20h de segunda
    a sexta e de 15 em 15 fora disso. No mesmo minuto vence a de cima (`PRIORIDADE`; as novas cabem nos 7 dias). Estando no
    instante de um, o próximo é o da vez seguinte."""
    local = agora + _BRT_S
    dia0 = (local // 86400) * 86400
    cands = []
    for d in (0, 1):
        base = dia0 + d * 86400
        util = int((base // 86400 + 3) % 7) < 5
        cands.append((base + NOITE_HORA[0] * 3600 + NOITE_HORA[1] * 60, NOITE))
        for h in range(24):
            hora = base + h * 3600
            cands.append((hora + FINALIZADAS_MINUTO * 60, FINALIZADAS))
            cands.append((hora + ABERTAS_MINUTO * 60, ABERTAS))
            if SETE_DIAS_DAS <= h < SETE_DIAS_ATE:
                cands += [(hora + m * 60, SETE_DIAS) for m in SETE_DIAS_MINUTOS]
            passo = NOVAS_DIA_MIN if util and DIA_UTIL_DAS <= h < DIA_UTIL_ATE else NOVAS_FORA_MIN
            cands += [(hora + m * 60, NOVAS) for m in range(0, 60, passo)]
    t, passo = min(((t, p) for t, p in cands if t > local), key=lambda tp: (tp[0], PRIORIDADE[tp[1]]))
    return t - local, passo


def rodar_passo(passo: str, ler=None) -> dict | None:
    """Um compromisso do laço. As pendentes vão junto das novas e dos 7 dias; a conferência das abertas só lê sem entrega."""
    if passo == NOITE:
        return ler_noite(ler)
    if passo == SETE_DIAS:
        rel = ler_sete_dias(ler)
        ler_pendentes(ler)
        return rel
    if passo == ABERTAS:
        return ler_abertas(ler) if precisa_das_abertas() else None
    if passo == FINALIZADAS:
        return ler_finalizadas(ler)
    rel = ler_novas(ler)
    ler_pendentes(ler)
    return rel


def _laco() -> None:
    while True:
        espera, passo = proximo_passo(time.time())
        _dormir(espera)
        app = _APP["app"]
        try:
            with app.app_context():
                rel = rodar_passo(passo)
            if rel is not None and passo in (NOITE, ABERTAS):
                log.info("leitor de OS: %s: %s (%d pedidos)", passo, rel["resultado"], rel["pedidos"])
        except Exception:                                            # noqa: BLE001 — o leitor nunca derruba o Nexus
            log.exception("leitor de OS: o passo %s quebrou", passo)


def ligar(app) -> None:
    """Liga o leitor neste app (SÓ o `servir.py`, o servidor): diz à lista onde mora a cópia dela em disco
    (`ponte.ligar_lista_de_os`), registra a entrega das abertas no `tarefas_os` e o estado na lista, e abre o laço (fora dos
    testes). Sem a credencial REST do Fracttal, não liga: o estado diz por quê, e a lista só se enche pelas ações. Ligar de
    novo no mesmo app não faz nada."""
    if CHAVE in app.extensions:
        return
    app.extensions[CHAVE] = _ESTADO
    try:
        from nexus.torres.oscreator import ponte
        ponte.ligar_lista_de_os(app)
    except Exception:                                                # noqa: BLE001 — sem a pasta, a lista vive na memória
        log.exception("leitor de OS: a lista central não foi ligada à pasta de dados")
    from nexus.pcm.geracao import credencial
    cred = credencial(app.config)
    if not cred.ok:
        _ESTADO.update(ligado=False, motivo="sem a credencial REST do Fracttal (FRACTTAL_CLIENT_ID e FRACTTAL_CLIENT_SECRET): "
                                            "a lista central de OS só se enche pelas ações do OS Creator, e as telas seguem "
                                            "ao vivo")
        os_central.ligar_leitor(estado=estado)
        log.warning("leitor de OS: %s", _ESTADO["motivo"])
        return
    _APP["app"] = app
    _ESTADO.update(ligado=True, motivo="", credencial=cred.onde)
    e = os_central.entrega(os_central.ABERTAS)                      # a última entrega antes do reinício (a cópia em disco)
    if e and e.get("quem") in _ESTADO["entregas"]:
        _ESTADO["entregas"][e["quem"]] = float(e.get("inicio") or e.get("em") or 0.0)
    tarefas_os.ligar_entrega_das_abertas(entregar_abertas)
    os_central.ligar_leitor(estado=estado)
    if not app.config.get("TESTING"):
        threading.Thread(target=_laco, name="nexus-os-leitor", daemon=True).start()


def estado() -> dict:
    """O que o leitor fez, para o Raio-X (`os_central.estado()["leitor"]`): se está ligado (e por quê não), a última leitura de
    cada faixa (pedidos, OS, o resultado e o erro), quando chegaram as abertas por último (do `tarefas_os` e daqui) e se há uma
    leitura em curso. Só contagens, datas e motivos."""
    return {"ligado": _ESTADO["ligado"], "motivo": _ESTADO["motivo"], "credencial": _ESTADO["credencial"],
            "faixas": {k: dict(v) for k, v in list(_ESTADO["faixas"].items())}, "entregas": dict(_ESTADO["entregas"]),
            "lendo": _TRAVA.locked()}


def reiniciar() -> None:
    """Volta ao processo recém-subido (os testes): sem app, sem leituras, o estado limpo, a entrega das abertas desligada."""
    _APP["app"] = None
    _ESTADO.clear()
    _ESTADO.update(_estado_limpo())
    tarefas_os.ligar_entrega_das_abertas(None)
