# os_creator/os_web/rotas_acomp.py
"""Acompanhamento de chamados — a porta do card de Chamados que faltava (Levi, 27/09/2026: "uma espécie de kanban
mostrando OSs que chegam, que a analista de chamados já escreveu número de tickets e OSs finalizadas! Ao clicar na OS abre uma tela
onde ela vê todas as informações do chamado daquele ativo e pode escrever observações").

DE ONDE VEM CADA COISA — nada aqui inventa estado:
- o quadro: as OS com a etiqueta CHAMADOS (`api.list_chamados`) que são OS de acompanhamento, e o nº do ticket de cada
  uma, que é a ÚNICA subtarefa dela (`api.tickets_os3_em_massa`);
- o ticket se grava NA subtarefa, pela mesma função do "fazer a tarefa" do card (`api.salvar_subtarefas`);
- finalizar é o Concluir do card, a mesma função (`api.concluir_os_checado`), com a reconferência da data de fim;
- as observações moram no banco da Gridco (`chamados_obs_store`), uma linha por observação, com a data do servidor.

A regra pura (colunas, tempo parado, a nota lida de volta) está em `acomp_web.py`."""
from __future__ import annotations

import datetime as dt
import io
import threading
import time
import zipfile

import requests
from flask import (Blueprint, has_request_context, jsonify, redirect, render_template, request, send_file, session,
                   url_for)

import api
import chamado_spec as cs
import chamados_obs_store as obs_store
import gridco_abas as ga

from . import acomp_web as aw
from . import historico_store as HS
from . import rotas, sessao
from .rotas import _conta, exige_sessao

bp = Blueprint("os_web_acomp", __name__, url_prefix="/os")

# s: a cópia do quadro (ver `_dono`). Era 3 min até 20/10/2026 (Levi: "quando tento voltar para acompanhamento dá uma
# travada, faz outra pesquisa no fractal? ... só pesquisar caso a singrid clique em atualizar, fora isso fica mostrando o
# que já carregou ou carrega a cada 30 min"): a volta da tela de um chamado ao quadro não vai ao Fracttal, e o que a
# própria tela grava (ticket, finalizar, responsável) ajusta a cópia em vez de apagá-la (`_ajustar`). O Atualizar relê.
TTL_QUADRO = 30 * 60
DIAS_BUSCA = 365          # a primeira OS de acompanhamento é de ago/2026; um ano cobre as abertas com folga
TTL_TICKET_FIM = 1800     # s: o ticket de OS CONCLUÍDA (ver `_tickets`)
# Passados os 30 min, o quadro abre NA HORA com a leitura anterior e relê o Fracttal por trás, com a sessão da pessoa
# (Levi, 09/10/2026: "teria como utilizarmos essas requisições de forma mais inteligente?"): até então, quadro vencido
# era a tela esperando o Fracttal na frente de quem abriu. Mais velha que VELHA_MAX, a tela de um chamado espera a leitura
# como antes; o quadro abre com ela desde 24/10/2026 (a 1ª abertura do dia esperava ~40 s), com a hora à vista, e troca
# sozinho quando a nova chega (`quadro_estado`), só para quem vê o mesmo total no Fracttal (`_mesma_visao_da_velha`).
VELHA_MAX = 2 * 3600      # s

# O que cada leitura guarda, por DONO da cópia (`_dono`). Até 19/10/2026 o dono era sempre a pessoa ("uma pessoa
# nunca vê a cópia de outra": a lista vem com a sessão dela no Fracttal), e cada pessoa com o quadro aberto relia a
# lista e os tickets a cada 3 min, para o mesmo quadro. Desde então (Levi, 19/10/2026: "quebre essa regra"), quem vê no
# Fracttal o MESMO total de OS com a etiqueta CHAMADOS divide a cópia "TODOS": a pessoa confere o total na sessão dela
# (`api.total_chamados`, 2 pedidos pequenos a cada 30 min, `historico_store.mesma_visao`; quem acabou de ler a lista já
# tem o total dela), e quem vê outro total (visão restrita no Fracttal), ou não conseguiu conferir, segue com a cópia
# dela, como antes.
# Levi, 08/10/2026: "O carregamento de Acompanhamento de chamados e a tela que abre quando clica na OS está demorando
# um pouco para carregar". Com o Fracttal falso a 300 ms por pedido (65 tickets lidos, 8 de cada vez):
# - ("acomp_linhas", dono): as OS de acompanhamento (lista + tarefas) e o total do Fracttal, SEM os tickets. É o que a
#   tela de um chamado precisa; antes, abrir um chamado com o quadro vencido relia os 65 tickets só para achar a linha;
# - ("acomp", dono): o quadro inteiro, as linhas acima + o ticket de cada uma;
# - ("acomp_tk", "TODOS"): o ticket das OS CONCLUÍDAS, {id: (quando, ticket)}, um só para todos (o ticket é da OS, e
#   cada pessoa só pede o das OS da lista que ela vê). Concluída não volta e o Fracttal não aceita mais editar (ver
#   `api.editar_nota_os`: ERROR_WO_FINISHED_BY_OTHER_USER), então o ticket dela não muda: vale 30 min. O "Atualizar"
#   relê a lista, as abertas e as em verificação.
# Tudo na memória do rotas (`rotas._MEMO`, com o teto dela): quem limpa a memória limpa tudo.


def _quem() -> tuple:
    c = session.get("conta") or {}
    return (str(c.get("nome") or "").strip(), str(c.get("email") or "").strip())


def _dono(pessoa=None) -> str:
    """De quem é a cópia do quadro que esta pessoa vê (ver o topo): "TODOS" quando o Fracttal dá a ela o mesmo total
    de OS com a etiqueta CHAMADOS da cópia dividida; senão, ela mesma.
    - sem cópia dividida, ou abandonada (mais velha que VELHA_MAX: quem a usa relê a cada 3 min): "TODOS", e a leitura
      desta pessoa vira a de todos;
    - quem leu a lista (`_linhas`) já tem o total dela anotado: não confere de novo.
    Sem a etiqueta CHAMADOS no Fracttal o total é 0, para todos (a etiqueta é da empresa), e o quadro vazio é um só."""
    pessoa = pessoa or rotas._quem()
    idade, v = _guardado_com_idade(("acomp_linhas", "TODOS"))
    if not isinstance(v, dict) or idade >= VELHA_MAX:
        return "TODOS"
    de = (dt.date.today() - dt.timedelta(days=DIAS_BUSCA)).isoformat()
    ok = HS.mesma_visao(pessoa, ("acomp", "TODOS"), lambda: api.total_chamados(de), guardado=v.get("total") or 0)
    return "TODOS" if ok else pessoa


def _quem_le() -> str:
    """Quem está lendo o Fracttal: a pessoa da requisição ou, na releitura por trás, a do contexto da sessão."""
    if has_request_context():
        return rotas._quem()
    return sessao.email_atual() or sessao.email_do_jwt(sessao.jwt_atual()) or "?"


def _guardado(chave, ttl: float = None):
    """O que a memória do rotas tem nesta chave, sem buscar nada. Com `ttl`, só se ainda vale; sem, mesmo vencido (só
    para o que não muda, como o id de um nº de OS). None se nada."""
    with rotas._MEMO_LOCK:
        v = rotas._MEMO.get(chave)
    if not v or (ttl is not None and time.monotonic() - v[0] >= ttl):
        return None
    return v[1]


def _sessao_viva():
    """Leitura feita com a sessão morta NÃO vai para a memória. Os tickets engolem o erro de cada pedido (o `api` devolve
    None; a listagem também engolia até 21/10/2026, `api._lista_pela_metade`), e o quadro vazio ficaria guardado para a
    pessoa, mesmo depois de ela entrar de novo. Até 08/10 quem acusava era a busca da etiqueta, o 1º pedido de toda leitura; com a lista guardada para o
    quadro reaproveitar, o quadro pode nem passar por ela. JWT vencido sem renovação levanta aqui mesmo (sem pedido)."""
    api._rpc_headers()


def _conferir_sessao():
    if sessao.morta():
        raise api.SessionExpired("Sua sessão do Fracttal expirou ou foi encerrada. Faça login de novo.")


def _linhas(forcar: bool = False, pessoa=None) -> dict:
    """{"linhas", "quando", "total"}: as OS de acompanhamento do Fracttal, sem os tickets, na memória por TTL_QUADRO, e
    o total de OS com a etiqueta que o Fracttal deu (o que o `_dono` confere; 0 sem a etiqueta). O total fica anotado
    como a conferência de quem leu (`historico_store.anotar_total`): é a mesma conta do `api.total_chamados`. `pessoa`
    é o dono da cópia: vem de quem chama; sem ele, o de quem está na requisição (`_dono`)."""
    def _buscar():
        inicio = time.monotonic()
        hoje = aw.agora_brt()
        de = (dt.date.today() - dt.timedelta(days=DIAS_BUSCA)).isoformat()
        inf = {}
        linhas = [l for l in (api.list_chamados(de=de, info=inf, meta_ja=_fechadas_ja_lidas(pessoa or _dono())) or [])
                  if aw.eh_os3(l)]
        _conferir_sessao()
        total = int(inf.get("total") or 0)
        HS.anotar_total(_quem_le(), ("acomp", "TODOS"), total)
        return _reaplicar({"linhas": linhas, "quando": hoje.strftime("%d/%m/%Y %H:%M"), "total": total}, inicio)
    return rotas._memo(("acomp_linhas", pessoa or _dono()), TTL_QUADRO, _buscar, forcar)


_META = ("status_id", "tipo_tarefa", "event_date", "data_fim", "note", "inicio", "gatilho")


def _fechadas_ja_lidas(dono) -> dict:
    """{id: o que a leitura anterior trouxe} das OS FECHADAS da cópia deste dono, mesmo vencida: a releitura não relê as
    tarefas delas (`api.list_minhas_os(meta_ja=...)`, 20/10/2026). Concluída não volta e o Fracttal não aceita mais
    editar (a nota e o ticket não mudam); se ela voltou a outro status, a lista diz e as tarefas são relidas."""
    _idade, v = _guardado_com_idade(("acomp_linhas", dono))
    if not isinstance(v, dict):
        return {}
    return {l["id"]: {k: l.get(k) for k in _META} for l in v.get("linhas") or []
            if isinstance(l, dict) and l.get("id") is not None and l.get("status_id") in api.STATUS_FECHADOS}


def _tickets(linhas, hoje) -> dict:
    """{id: ticket} das OS que o quadro mostra (`aw.precisa_ticket`). O das concluídas sai de ("acomp_tk", "TODOS")
    quando lido há menos de 30 min (o ticket é da OS: o mesmo para todos, e cada um só pede o das OS da lista que vê);
    o resto vai ao Fracttal (8 de cada vez, `api.tickets_os3_em_massa`). None = não li: não é guardado."""
    ids = [l.get("id") for l in linhas if aw.precisa_ticket(l, hoje)]
    if not ids:
        return {}
    fechadas = {l.get("id") for l in linhas if l.get("status_id") == 3}
    chave, agora = ("acomp_tk", "TODOS"), time.monotonic()
    with rotas._MEMO_LOCK:
        v = rotas._MEMO.get(chave)
        meus = v[1] if v and isinstance(v[1], dict) else {}
        prontos = {i: meus[i][1] for i in ids if i in fechadas and i in meus and agora - meus[i][0] < TTL_TICKET_FIM}
    faltam = [i for i in ids if i not in prontos]
    lidos = api.tickets_os3_em_massa(faltam) if faltam else {}
    with rotas._MEMO_LOCK:
        v = rotas._MEMO.get(chave)
        meus = {k: x for k, x in (v[1] if v and isinstance(v[1], dict) else {}).items() if agora - x[0] < TTL_TICKET_FIM}
        meus.update({i: (agora, t) for i, t in lidos.items() if i in fechadas and t is not None})
        rotas._MEMO[chave] = (agora, meus)
    out = dict(lidos)
    out.update(prontos)
    return out


def _dados(forcar: bool = False, pessoa=None) -> dict:
    """A lista das OS de acompanhamento + o ticket de cada uma, na memória por TTL_QUADRO, na cópia do dono (`_dono`).
    A lista é a de `_linhas`: se a tela de um chamado acabou de lê-la, o quadro só busca os tickets."""
    pessoa = pessoa or _dono()

    def _buscar():
        inicio = time.monotonic()
        _sessao_viva()
        hoje = aw.agora_brt()
        lv = _linhas(forcar, pessoa)
        tickets = _tickets(lv["linhas"], hoje)
        _conferir_sessao()
        return _reaplicar({"linhas": lv["linhas"], "tickets": tickets, "quando": lv["quando"]}, inicio)
    return rotas._memo(("acomp", pessoa), TTL_QUADRO, _buscar, forcar)


# ── a gravação ajusta o quadro guardado (20/10/2026) ──────────────────────────────────────────────────────────────
# Até então cada gravação desta tela apagava o quadro da memória (`_esquecer`), e a volta ao quadro esperava o Fracttal.
# Agora a gravação põe na cópia o que ELA gravou (e o Fracttal aceitou): o ticket, o status depois de finalizar, o
# responsável. A releitura que começou antes da gravação e termina depois leva a gravação por cima (`_reaplicar`).
_AJUSTES: list = []        # (quando, id da OS, campos da linha, ticket), as últimas AJUSTES_MAX gravações
AJUSTES_MAX = 200
rotas.MEMO_FICA.update({"acomp", "acomp_linhas", "acomp_tk"})      # 30 min: o teto da memória os tira por último


def _com_ajuste(v: dict, wid, campos: dict, ticket):
    """A cópia `v` (o quadro de `_dados` ou a lista de `_linhas`) com a linha da OS `wid` ajustada, numa cópia nova (quem
    está montando a tela com a de antes não a vê mudar no meio); None se a OS não está nela."""
    linhas = v.get("linhas") or []
    alvo = next((l for l in linhas if str(l.get("id")) == str(wid)), None)
    if alvo is None:
        return None
    novo = {k: x for k, x in v.items() if k != "_cartoes"}           # os "outros chamados" montados são refeitos
    novo["linhas"] = [dict(l, **campos) if l is alvo else l for l in linhas]
    if ticket is not None and isinstance(v.get("tickets"), dict):
        novo["tickets"] = dict(v["tickets"])
        novo["tickets"][alvo.get("id")] = ticket
    return novo


def _ajustar(wid, campos=None, ticket=None) -> bool:
    """Põe a gravação na cópia guardada de todo mundo; True se a OS estava em alguma."""
    campos, achou = dict(campos or {}), False
    with rotas._MEMO_LOCK:
        _AJUSTES.append((time.monotonic(), wid, campos, ticket))
        del _AJUSTES[:-AJUSTES_MAX]
        for k, (q, v) in list(rotas._MEMO.items()):
            if not (isinstance(k, tuple) and k and isinstance(v, dict)):
                continue
            if k[0] in ("acomp", "acomp_linhas"):
                novo = _com_ajuste(v, wid, campos, ticket)
                if novo is not None:
                    rotas._MEMO[k] = (q, novo)                       # a idade fica: o ajuste não é uma leitura nova
                    achou = True
            elif k[0] == "acomp_tk":
                v.pop(wid, None)
    rotas._esquecer_preparo(wid)            # o detalhe lido antes da gravação (o mouse parado no cartão) também sai
    return achou


def _reaplicar(r: dict, inicio: float) -> dict:
    """A leitura que começou em `inicio`, com as gravações feitas desde então por cima."""
    with rotas._MEMO_LOCK:
        depois = [a for a in _AJUSTES if a[0] >= inicio]
    for _q, wid, campos, ticket in depois:
        r = _com_ajuste(r, wid, campos, ticket) or r
    return r


def _esquecer(wid=None):
    """Depois de gravar ticket ou finalizar: a próxima leitura do quadro vai ao Fracttal (de todo mundo), e o ticket
    guardado desta OS sai."""
    with rotas._MEMO_LOCK:
        for k in [k for k in rotas._MEMO if isinstance(k, tuple) and k and k[0] in ("acomp", "acomp_linhas")]:
            rotas._MEMO.pop(k, None)
        if wid:
            for k, (_q, v) in rotas._MEMO.items():
                if isinstance(k, tuple) and k and k[0] == "acomp_tk" and isinstance(v, dict):
                    v.pop(wid, None)
        _ESQUECIDO["em"] = time.monotonic()
    if wid:
        rotas._esquecer_preparo(wid)        # o detalhe lido antes da gravação (o mouse parado no cartão) também sai


# ── a releitura por trás (Levi, 09/10/2026) ─────────────────────────────────────────────────────────────────────────
_RENOVANDO: set = set()            # donos (`_dono`) com a releitura da cópia em andamento: uma por cópia
_RENOV_TRAVA = threading.Lock()
_ESQUECIDO = {"em": 0.0}           # quando uma gravação (`_esquecer`) tirou o quadro da memória pela última vez


def _em_segundo_plano(fn):
    """Onde a releitura roda: uma thread solta (os testes trocam para rodar quando querem)."""
    threading.Thread(target=fn, daemon=True, name="os-web-acomp-renovar").start()


def _guardado_com_idade(chave) -> tuple:
    """(idade em s, o que a memória guarda nesta chave), sem buscar nada. (None, None) se nada."""
    with rotas._MEMO_LOCK:
        v = rotas._MEMO.get(chave)
    return (time.monotonic() - v[0], v[1]) if v else (None, None)


def esquecer_se_no_quadro(wid) -> bool:
    """Gravação feita fora desta tela (o responsável trocado no card da OS ou na tela do chamado, 19/10/2026): se a OS
    está num quadro guardado, mesmo vencido, ele é ajustado com o responsável novo (20/10/2026: antes saía da memória, e
    a volta ao quadro relia o Fracttal). Quem chama é a rota do responsável (`rotas_os_acoes.api_responsavel`), cujo corpo
    traz o `id_personnel` e o `name` que o Fracttal acabou de aceitar; sem eles (fora de uma requisição), o quadro sai
    da memória, como antes. OS que não é de acompanhamento não custa a ninguém a releitura do quadro."""
    corpo = (request.get_json(silent=True) or {}) if has_request_context() else {}
    nome = " ".join(str(corpo.get("name") or "").split())
    if nome and corpo.get("id_personnel"):
        return _ajustar(wid, {"atribuido_a": nome, "id_atribuido": corpo.get("id_personnel")})
    with rotas._MEMO_LOCK:
        achou = any(isinstance(k, tuple) and k and k[0] in ("acomp", "acomp_linhas") and isinstance(v[1], dict)
                    and any(str(l.get("id")) == str(wid) for l in v[1].get("linhas") or [])
                    for k, v in rotas._MEMO.items())
    if achou:
        _esquecer(wid)
    return achou


def _esquecer_pessoa(pessoa):
    with rotas._MEMO_LOCK:
        for k in (("acomp", pessoa), ("acomp_linhas", pessoa)):
            rotas._MEMO.pop(k, None)


def _renovar_por_tras(pessoa) -> None:
    """Relê a cópia do quadro deste dono (`_dono`: "TODOS" ou a pessoa) fora da requisição, com a sessão de quem abriu
    no Fracttal: o JWT e o e-mail vão junto, porque a thread nasce sem o contexto da requisição e o `api` cairia no
    arquivo de token do app de mesa (ver `api._ExecutorComContexto`). São os mesmos pedidos que a tela faria na frente
    da pessoa, só que fora do caminho dela: nenhum a mais na cota do Fracttal.
    - erro do Fracttal (429, rede): fica a leitura anterior, e a próxima visita vencida tenta de novo;
    - sessão caída: a cópia sai da memória, e a próxima visita lê na frente (a de quem caiu volta ao login, como
      sempre);
    - gravação no meio (ticket, finalizar): a leitura começou antes dela e mostraria o quadro de antes, então sai."""
    with _RENOV_TRAVA:
        if pessoa in _RENOVANDO:
            return
        _RENOVANDO.add(pessoa)
    jwt, email = sessao.jwt_atual(), sessao.email_atual()

    def rodar():
        inicio = time.monotonic()
        try:
            with sessao.contexto(jwt, email):
                _dados(forcar=True, pessoa=pessoa)
            if _ESQUECIDO["em"] >= inicio:
                _esquecer_pessoa(pessoa)
        except api.SessionExpired:
            _esquecer_pessoa(pessoa)
        except Exception:               # noqa: BLE001 — o quadro segue com a leitura anterior, com a hora dela
            pass
        finally:
            with _RENOV_TRAVA:
                _RENOVANDO.discard(pessoa)
    _em_segundo_plano(rodar)


def _ultimas(forcar: bool = False) -> tuple:
    """({nº: última observação}, {nº: quando foi finalizada}, {nº: status da última troca}, erro)."""
    try:
        if forcar:
            obs_store.listar(forcar=True)
        return obs_store.ultima_por_os(), obs_store.finalizado_por_os(), obs_store.status_por_os(), ""
    except Exception as e:                              # noqa: BLE001 — sem o banco, o quadro sai; só o "dias sem" usa a chegada
        return {}, {}, {}, "Não consegui ler as observações no banco da Gridco (%s)." % str(e)[:120]


def _ler_quadro(forcar: bool = False, dono=None) -> tuple:
    try:
        return _dados(forcar, dono), None
    except api.FracttalError as e:
        if sessao.morta() or isinstance(e, api.SessionExpired):
            raise
        # o Atualizar que o Fracttal não respondeu fica com o quadro que já estava, com a hora dele (21/10/2026): a lista
        # pela metade não é guardada (`api._lista_pela_metade`). Até VELHA_MAX, como a abertura vencida
        idade, v = _guardado_com_idade(("acomp", dono or _dono()))
        if isinstance(v, dict) and idade < VELHA_MAX:
            return v, str(e)
        return {"linhas": [], "tickets": {}, "quando": ""}, str(e)


# Quem é o Responsável UFV de cada chamado (o supervisor da usina; Levi, 28/10/2026: "inclua o filtro Responsável UFV
# que é o supervisor da UFV"). O OS Creator não sabe: quem diz é o Nexus, pelo cadastro dele (o Responsável O&M da ficha
# da usina), e a ponte põe a função aqui ao criar o clone (`nexus/torres/chamados/ufv.py`). fn(cartões) -> {nº: nome}.
# Sozinho (o oem, o supervisório), sem a função: o filtro não aparece e o relatório não diz o supervisor.
RESPONSAVEL_UFV = None


def _com_responsavel_ufv(q: dict) -> None:
    cards = [c for col in q["colunas"].values() for c in col]
    ufv = {}
    if RESPONSAVEL_UFV is not None:
        try:
            ufv = RESPONSAVEL_UFV(cards) or {}
        except Exception:                               # noqa: BLE001 — sem o cadastro, o quadro sai sem o supervisor
            ufv = {}
    for c in cards:
        c["resp_ufv"] = str(ufv.get(c["folio"]) or "")
    q["opcoes"]["ufv"] = (sorted({c["resp_ufv"] for c in cards if c["resp_ufv"]}, key=aw._norm)
                          if RESPONSAVEL_UFV is not None else None)


def _montar(forcar: bool = False) -> dict:
    """O quadro como a tela mostra (o mesmo do Exportar relatório e do Exportar tabela)."""
    # as observações (banco da Gridco) vêm ao mesmo tempo que o Fracttal, e não depois dele (08/10/2026), e a conferência
    # de quem é a cópia (`_dono`) também
    with api._ExecutorComContexto(max_workers=1) as ex:
        f_obs = ex.submit(_ultimas, forcar)
        dono = _dono()
        idade, guardado = (None, None) if forcar else _guardado_com_idade(("acomp", dono))
        # vencido (30 min): abre com a leitura anterior e relê por trás, e a tela troca sozinha quando a nova chega
        # (`quadro_estado`). Mais velho que VELHA_MAX também (24/10/2026, Levi: a 1ª abertura do dia esperava ~40 s o
        # Fracttal), mas só para quem vê no Fracttal o mesmo total da cópia: a de ontem pode ser de outra visão. O
        # Atualizar lê na hora
        por_tras = guardado is not None and idade >= TTL_QUADRO and (idade < VELHA_MAX or _mesma_visao_da_velha(dono))
        if por_tras:
            d, erro = guardado, None
            _renovar_por_tras(dono)
        else:
            d, erro = _ler_quadro(forcar, dono)
        ultimas, fins, status, erro_obs = f_obs.result()
    q = aw.montar_quadro(d["linhas"], d["tickets"], ultimas, aw.agora_brt(), fins, obs_lidas=not erro_obs,
                         status=status)
    _com_responsavel_ufv(q)
    return {"q": q, "d": d, "erro": erro, "erro_obs": erro_obs, "por_tras": por_tras}


@bp.route("/chamados/acompanhamento")
@exige_sessao
def quadro():
    m = _montar(request.args.get("atualizar") == "1")
    return render_template("acomp.html", conta=_conta(), aba="criar", q=m["q"], quando=m["d"].get("quando") or "",
                           erro=m["erro"], erro_obs=m["erro_obs"], equipe=aw.equipe()[1], renovando=m["por_tras"],
                           status_geral=aw.STATUS_GERAL)


def _cartoes_do_quadro(q: dict) -> list:
    return [c for chave in ("chegou", "ticket", "fim") for c in q["colunas"][chave]]


def _ultima_obs() -> dict:
    """{nº: (quando, texto)} da última observação escrita (tipo obs) de cada OS: a "última atualização" do relatório."""
    try:
        lista = obs_store.vigentes(obs_store.listar())  # a editada com o texto novo; a excluída, não
    except Exception:                                   # noqa: BLE001 — sem o banco, o relatório sai sem ela
        return {}
    out = {}
    for x in lista:
        if x.get("tipo") == "obs":
            out[x["os"]] = (x["quando"], x["texto"])
    return out


@bp.route("/chamados/acompanhamento/relatorio", methods=["POST"])
@exige_sessao
def relatorio():
    """O relatório dos chamados de garantia em andamento, para mandar ao cliente (Levi, 28/10/2026: "Incluir um botão de
    Exportar Relatório ... deixe mais polido visualmente e no linguajar para enviar para o cliente, quero conseguir
    exportar por cliente, então tem que ter um checkbox por cliente"): um PDF por cliente marcado; dois ou mais, num
    .zip. É o quadro que a tela mostra (sem ler o Fracttal de novo)."""
    from . import relatorio_chamados as rc
    clientes = list(dict.fromkeys(" ".join(str(x or "").split()) for x in (_corpo().get("clientes") or [])))
    clientes = [x for x in clientes if x]
    if not clientes:
        return _erro("Marque ao menos um cliente.")
    cards = _cartoes_do_quadro(_montar(False)["q"])
    hoje, obs = aw.agora_brt(), _ultima_obs()
    arquivos = [("Chamados de garantia - %s - %s.pdf" % (rc.nome_de_arquivo(cli), hoje.strftime("%d-%m-%Y")),
                 rc.gerar(rc.modelo(cards, cli, hoje, obs))) for cli in clientes]
    if len(arquivos) == 1:
        nome, pdf = arquivos[0]
        return send_file(io.BytesIO(pdf), mimetype="application/pdf", as_attachment=True, download_name=nome)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, pdf in arquivos:
            z.writestr(nome, pdf)
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name="Chamados de garantia - %s.zip" % hoje.strftime("%d-%m-%Y"))


@bp.route("/chamados/acompanhamento/tabela", methods=["POST"])
@exige_sessao
def tabela():
    """A tabela em Excel (Levi, 28/10/2026: "Em tabela, tem que ter a opção de Exportar tabela"): as linhas que a tela
    mostra com os filtros (os nºs vêm do navegador, na ordem dela), com as colunas da tabela e as que ajudam a planilha."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    folios = [str(x).strip() for x in (_corpo().get("folios") or []) if str(x).strip()]
    por = {c["folio"]: c for c in _cartoes_do_quadro(_montar(False)["q"])}
    linhas = [por[f] for f in folios if f in por]
    wb = Workbook()
    ws = wb.active
    ws.title = "Garantias"
    ws.append(["OS", "Ativo", "Cliente", "Usina", "Responsável UFV", "Fornecedor", "Geral", "Status", "Ticket",
               "Situação", "Aberto há (dias)", "Sem atualização (dias)", "Responsável"])
    for c in linhas:
        ws.append([int(c["folio"]) if c["folio"].isdigit() else c["folio"], c["ativo_nome"] or c["code"], c["cliente"],
                   c["usina"], c["resp_ufv"], c["marca"], c["geral"], c["status_ch"], c["ticket"], c["situacao"],
                   c["dias"], c["dias_sem"], c["responsavel"]])
    for x in ws[1]:
        x.font = Font(bold=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for col, larg in zip("ABCDEFGHIJKLM", (9, 34, 18, 26, 24, 14, 11, 34, 26, 26, 12, 14, 24)):
        ws.column_dimensions[col].width = larg
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="Garantias - %s.xlsx" % aw.agora_brt().strftime("%d-%m-%Y"))


@bp.route("/chamados/acompanhamento/estado")
@exige_sessao
def quadro_estado():
    """A tela que abriu com a leitura anterior pergunta, de 5 em 5 s, se a nova já chegou (`acomp.js`): a hora da
    cópia de agora e se ela ainda está sendo relida. Não vai ao Fracttal (a conferência do `_dono` já está guardada)."""
    dono = _dono()
    _, v = _guardado_com_idade(("acomp", dono))
    with _RENOV_TRAVA:
        relendo = dono in _RENOVANDO
    return jsonify({"quando": (v or {}).get("quando") or "", "renovando": relendo})


def _mesma_visao_da_velha(dono) -> bool:
    """Quem abre vê no Fracttal o mesmo total de OS com a etiqueta CHAMADOS da cópia velha (mais de VELHA_MAX)? A cópia
    "TODOS" largada vale para quem chegar (`_dono`), e a de quem tem a visão restrita mostraria a outra pessoa o quadro
    errado (ou a dela, o de quem vê tudo). O total dela fica guardado por pessoa (`HS.mesma_visao`)."""
    _, v = _guardado_com_idade(("acomp_linhas", dono))
    if not isinstance(v, dict):
        return False
    de = (dt.date.today() - dt.timedelta(days=DIAS_BUSCA)).isoformat()
    return HS.mesma_visao(rotas._quem(), ("acomp", dono), lambda: api.total_chamados(de), guardado=v.get("total") or 0)


@bp.route("/em-breve/chamados")
@exige_sessao
def em_breve_antigo():
    """O hub apontava para o "em breve" até 27/09 — quem tiver a página aberta cai no quadro."""
    return redirect(url_for("os_web_acomp.quadro"))


def _linha_de(d: dict, folio: int):
    return next((l for l in d["linhas"] if str(l.get("folio")) == str(folio)), None)


def _nota_da_os(det: dict, linha: dict) -> str:
    for txt in (det.get("notas") or "", (linha or {}).get("note") or ""):
        if aw.MARCA_NOTA in str(txt):
            return str(txt)
    return str(det.get("notas") or (linha or {}).get("note") or "")


def _detalhe_enxuto(wid, pessoa=None) -> dict:
    """O detalhe da OS sem a solicitação, a OS pai e o cancelamento (`api.enxuta`): esta tela não mostra os três. O que
    o mouse parado sobre o cartão do quadro já pediu (`rotas.preparado`, 09/10/2026) vale, uma vez."""
    pronto = rotas.preparado(wid, "chamado", pessoa) if pessoa else None
    if pronto is not None:
        return pronto
    with api.enxuta("vinculos"):
        return api.get_os_detalhes(wid) or {}


def _os_mae(pai_id) -> dict:
    """O nº e o tipo da OS mãe ({folio, tipo}) para a cadeia da OS 3 que não a traz na nota. Fracttal que recusa: {} (a
    cadeia fica "—", a tela abre); a sessão morta sobe, como em qualquer leitura da tela."""
    try:
        with api.enxuta("vinculos"):
            return api.get_os_detalhes(pai_id) or {}
    except api.SessionExpired:
        raise
    except api.FracttalError:
        return {}


def _obs_do_os(folio) -> tuple:
    """(observações desta OS, erro) — do banco da Gridco."""
    try:
        return obs_store.do_os(folio), ""
    except Exception as e:                              # noqa: BLE001
        return [], "Não consegui ler as observações no banco da Gridco (%s)." % str(e)[:120]


def _lista_da_tela(dono) -> dict:
    """As linhas para a tela de um chamado, da cópia do `dono`: o quadro inteiro, se ainda vale; senão só as linhas
    (`_linhas`, sem os tickets). A tela só usa a linha desta OS e os "outros chamados" (nº, marca, ativo, chegada), e
    nada disso vem do ticket: reler os tickets de todas as OS só para abrir uma era o que levava 5,6 s com o quadro
    vencido.

    Vencida (3 min) e não velha demais (VELHA_MAX), a cópia serve NA HORA e se relê por trás, como no quadro (20/10/2026,
    Raio-X das 09:56: a tela de um chamado ficou 39 s relendo a lista, com as tarefas de todas as OS). O que muda na OS
    (a situação, o fim, o responsável) vem do detalhe, lido na hora (`_com_o_detalhe`)."""
    cheio = _guardado(("acomp", dono), TTL_QUADRO)
    if cheio is not None:
        return cheio
    linhas = _guardado(("acomp_linhas", dono), TTL_QUADRO)
    if linhas is not None:
        return linhas
    for chave in (("acomp", dono), ("acomp_linhas", dono)):
        idade, v = _guardado_com_idade(chave)
        if isinstance(v, dict) and idade < VELHA_MAX:
            _renovar_por_tras(dono)
            return v
    try:
        return _linhas(pessoa=dono)
    except api.FracttalError as e:
        if sessao.morta() or isinstance(e, api.SessionExpired):
            raise
        return {"linhas": [], "quando": ""}


def _com_o_detalhe(linha: dict, det: dict) -> dict:
    """A linha da lista (que pode ser da cópia de até VELHA_MAX, `_lista_da_tela`) com o que o detalhe da OS, lido agora,
    diz: a situação, o fim e o responsável. Responsável trocado: o id da lista sai, e a equipe é conferida pelo nome
    (`acomp_web.da_equipe`)."""
    out = dict(linha)
    if det.get("status_id"):
        out["status_id"] = det["status_id"]
        out["status"] = api.WO_STATUS.get(det["status_id"], out.get("status") or "")
    if det.get("data_fim"):
        out["data_fim"] = det["data_fim"]
    resp = " ".join(str(det.get("responsavel") or "").split())
    if resp and resp != " ".join(str(out.get("atribuido_a") or "").split()):
        out["atribuido_a"], out["id_atribuido"] = resp, None
    return out


def _wid_ja_lido(folio, dono):
    """O id da OS deste nº numa leitura anterior da cópia que a pessoa vê (a do `dono`), mesmo vencida (o id de um nº
    não muda). Com ele, o detalhe da OS vai ao Fracttal junto com a lista, e não depois dela."""
    for chave in (("acomp", dono), ("acomp_linhas", dono)):
        v = _guardado(chave)
        linha = _linha_de(v, folio) if v else None
        if linha and linha.get("id"):
            return linha["id"]
    return None


def _cartoes(d: dict, hoje) -> list:
    """Os cartões de todas as OS da leitura, para os "outros chamados" do mesmo ativo e da mesma OS de campo. Montados
    uma vez por leitura e guardados nela: ler de volta as notas de 80 OS custava ~0,2 s a cada chamado aberto, e o
    "outros" não mostra nada que mude de um minuto para o outro."""
    feitos = d.get("_cartoes")
    if feitos is None:
        tickets = d.get("tickets") or {}
        feitos = [aw.cartao(l, tickets.get(l.get("id"), ""), "", hoje) for l in d.get("linhas") or []]
        d["_cartoes"] = feitos
    return feitos


@bp.route("/chamados/acompanhamento/<int:folio>")
@exige_sessao
def detalhe(folio):
    """A tela de um chamado. A lista, o detalhe da OS e as observações vão ao mesmo tempo (Levi, 08/10/2026: "a tela que
    abre quando clica na OS está demorando"); o detalhe vem sem a solicitação e a OS pai, que esta tela não mostra."""
    pessoa = rotas._quem()
    with api._ExecutorComContexto(max_workers=2) as ex:
        f_obs = ex.submit(_obs_do_os, folio)
        dono = _dono(pessoa)
        talvez = _wid_ja_lido(folio, dono)
        f_det = ex.submit(_detalhe_enxuto, talvez, pessoa) if talvez else None
        d = _lista_da_tela(dono)
        linha = _linha_de(d, folio)
        wid = (linha or {}).get("id") or talvez or api._wo_id_por_folio(folio)
        if not wid:
            return render_template("erro.html", conta=_conta(), aba="criar",
                                   mensagem="Não achei a OS %s no Fracttal." % folio), 404
        det = None
        if f_det is not None and wid == talvez:
            det = f_det.result() or {}
            if det.get("folio") and str(det["folio"]) != str(folio):     # não deve acontecer: o id de um nº não muda
                det = None
        if det is None:
            det = _detalhe_enxuto(wid, pessoa)
        obs, erro_obs = f_obs.result()
    nota = _nota_da_os(det, linha)
    item = aw.item_do_ticket(det.get("subtarefas"))
    ticket = str((item or {}).get("resposta") or "").strip()
    if linha is None:                                  # fora da lista (mais velha que DIAS_BUSCA): o mínimo do detalhe
        linha = {"id": wid, "folio": folio, "note": nota, "descricao": det.get("descricao"), "ativo": det.get("ativo"),
                 "status_id": 3 if det.get("data_fim") else 1, "atribuido_a": det.get("responsavel")}
    else:
        linha = _com_o_detalhe(linha, det)
    linha["criado_por"] = det.get("criado_por") or linha.get("criado_por") or ""     # Dados: "Criado por" (27/10/2026)
    hoje = aw.agora_brt()
    fim_tela = max((o["quando"] for o in obs if o["tipo"] == "finalizado"), default="")
    c = aw.cartao(dict(linha, note=nota), ticket, (obs[-1]["quando"] if obs else ""), hoje, fim_tela,
                  status=_status_trocado(obs))
    n = aw.ler_nota(nota)
    # a OS 3 criada à mão sem a cadeia na nota (20/10/2026): a OS mãe do Fracttal entra no lugar. Só nesse caso há um
    # pedido a mais; a do App sempre traz a cadeia, e o id da mãe já vem no detalhe enxuto (`os_pai_id`)
    if not (n["os_campo"] or n["inspecao"]) and det.get("os_pai_id"):
        mae = _os_mae(det["os_pai_id"])
        c.update(aw.cadeia_pela_mae(n, mae.get("folio"), mae.get("tipo")))
    if not c["code"]:
        c["code"] = str(det.get("code") or "").strip()     # o ativo da própria OS, quando a nota não diz
    todos = _cartoes(d, hoje)
    return render_template("acomp_os.html", conta=_conta(), aba="criar", c=c, n=n, wid=wid, item=item,
                           tl=aw.linha_do_tempo(c, obs, n["historico"], _ajustes_hist(folio)), outros=aw.outros(c, todos),
                           canal=cs.CANAL.get(c["marca"], ""),
                           menos7=aw.menos_7d(n["data_falha"], hoje), copiar=aw.copiar_tudo(n["campos"]),
                           erro_obs=erro_obs, pode_gravar=ga.pode_gravar(), equipe=aw.equipe()[1],
                           opcoes_status=aw.STATUS_CHAMADO, pode_obs=_pode_mexer_obs().get("pode", True))


def _status_trocado(obs):
    """O status da última troca entre as observações desta OS (None: nunca trocado)."""
    return next((str((o.get("extra") or {}).get("status") or "").strip() for o in reversed(obs or [])
                 if o.get("tipo") == "status"), None)


@bp.route("/chamados/acompanhamento/<int:folio>/preparar")
@exige_sessao
def preparar_chamado(folio):
    """O mouse parado sobre o cartão do quadro (Levi, 09/10/2026): o detalhe desta OS começa a ser lido por trás
    (`rotas.preparar`, enxuto, com o teto de lá). Só com o id que a cópia do quadro que a pessoa vê já leu (`_dono`):
    sem ele, nada, e o clique lê como sempre. O detalhe preparado segue sendo da pessoa (lido com a sessão dela)."""
    pessoa = rotas._quem()
    wid = _wid_ja_lido(folio, _dono(pessoa))
    return jsonify({"pedido": bool(wid) and rotas.preparar(pessoa, wid, "chamado")}), 202


# ── as três escritas ────────────────────────────────────────────────────────────────────────────────────────
def _corpo() -> dict:
    return request.get_json(silent=True) or {}


def _erro(msg, status=400):
    return jsonify({"erro": str(msg)}), status


def _os_conferida(folio: int, wid) -> tuple:
    """(wid, detalhe) — o id que o navegador mandou tem de ser o DESTA OS. Sem conferir, um id trocado gravaria o ticket
    na OS de outro chamado."""
    try:
        wid = int(wid or 0)
    except (TypeError, ValueError):
        wid = 0
    wid = wid or api._wo_id_por_folio(folio)
    if not wid:
        return None, None
    det = _detalhe_enxuto(wid)                         # a conferência não usa a solicitação nem a OS pai
    if str(det.get("folio") or "") != str(folio):
        return None, None
    return wid, det


def _anotar(folio, texto, tipo, det) -> str:
    """A anotação automática (ticket, finalizado). Falhar aqui NÃO desfaz o que já foi gravado no Fracttal: vira aviso."""
    nome, email = _quem()
    try:
        obs_store.adicionar(folio, texto, tipo, ativo=(det or {}).get("code") or "", quem=nome, email=email)
        return ""
    except Exception as e:                              # noqa: BLE001
        return "A anotação automática não entrou no banco da Gridco: %s" % str(e)[:160]


@bp.route("/api/acomp/<int:folio>/ticket", methods=["POST"])
@exige_sessao
def api_ticket(folio):
    c = _corpo()
    novo = " ".join(str(c.get("ticket") or "").split())
    if not novo:
        return _erro("Escreva o nº do ticket ou do protocolo.")
    if len(novo) > 120:
        return _erro("O nº do ticket passa de 120 caracteres.")
    wid, det = _os_conferida(folio, c.get("wid"))
    if not wid:
        return _erro("Não achei a OS %s no Fracttal." % folio, 404)
    item = aw.item_do_ticket(det.get("subtarefas"))
    if not item or not item.get("id_form_item") or not item.get("id_tarefa"):
        return _erro("A OS %s não tem a subtarefa do nº do ticket — ela não é uma OS de acompanhamento." % folio)
    antigo = str(item.get("resposta") or "").strip()
    if antigo == novo:
        return jsonify({"ok": True, "ticket": novo, "mensagem": "O ticket já era este.", "aviso": ""})
    api.salvar_subtarefas(wid, item["id_tarefa"], [{"id_form_item": item["id_form_item"], "valor": novo,
                                                   "tipo": item.get("tipo_id") or 1}])
    _ajustar(wid, ticket=novo)                  # a volta ao quadro mostra o ticket sem reler o Fracttal (20/10/2026)
    aviso = _anotar(folio, aw.texto_ticket(novo, antigo), "ticket", det)
    return jsonify({"ok": True, "ticket": novo, "mensagem": "Ticket gravado na OS %s." % folio, "aviso": aviso})


@bp.route("/api/acomp/<int:folio>/status", methods=["POST"])
@exige_sessao
def api_status(folio):
    """Troca o status do chamado (27/10/2026, Levi: "Gostaria de poder mudar os status, pode ter essas opções"): uma
    linha no banco da Gridco, como as observações, com quem e quando; não vai ao Fracttal. Só da lista
    (`acomp_web.STATUS_CHAMADO`) ou "" (sem status), e só no chamado aberto: o finalizado fica com o que tinha."""
    c = _corpo()
    novo = " ".join(str(c.get("status") or "").split())
    if novo and novo not in aw.STATUS_CHAMADO:
        return _erro("Status fora da lista: %s." % novo)
    wid, det = _os_conferida(folio, c.get("wid"))
    if not wid:
        return _erro("Não achei a OS %s no Fracttal." % folio, 404)
    if det.get("status_id") in (2, 3, 4):
        return _erro("O chamado da OS %s já foi finalizado: o status fica como estava." % folio)
    obs, erro = _obs_do_os(folio)
    if erro:
        return _erro(erro, 502)
    atual = aw.status_atual(_status_trocado(obs), aw.ler_nota(_nota_da_os(det, None)))
    if novo == atual:
        return jsonify({"ok": True, "status": novo, "mensagem": "O status já era este."})
    nome, email = _quem()
    try:
        obs_store.adicionar(folio, ("Status: %s" % novo) if novo else "Status retirado", "status",
                            ativo=det.get("code") or "", quem=nome, email=email, extra={"status": novo})
    except ga.SemCredencial as e:
        return _erro(e, 403)
    except requests.RequestException as e:
        return _erro("O banco da Gridco não respondeu: %s" % str(e)[:160], 502)
    return jsonify({"ok": True, "status": novo, "mensagem": "Status gravado."})


# Quem pode editar e excluir as observações (29/10/2026, Levi: "qualquer um que é ADM ou do setor de chamados"): o
# Nexus decide e põe no pedido, `request.environ["os_web.obs_chamados"]` = {"pode": bool, "aviso": str}
# (`ponte.obs_chamados`). Sem a chave (o OS Creator sozinho, o oem), fica aberto, como a Área PCM.
OBS_CHAMADOS = "os_web.obs_chamados"
AVISO_OBS = "Editar e excluir observações em Garantias é do setor Chamados e dos administradores do Nexus."


def _pode_mexer_obs() -> dict:
    v = request.environ.get(OBS_CHAMADOS)
    return v if isinstance(v, dict) else {"pode": True, "aviso": ""}


def _obs_em_vigor(folio, id_obs):
    """A observação desta OS como a tela mostra (a excluída não está), ou None."""
    lista = obs_store.vigentes(obs_store.listar())
    return next((x for x in lista if x["id"] == str(id_obs) and x["os"] == str(folio)), None)


def _mexer_obs(folio, id_obs, tipo, texto):
    p = _pode_mexer_obs()
    if not p.get("pode", True):
        return _erro(p.get("aviso") or AVISO_OBS, 403)
    if str(id_obs).startswith("h-"):
        return _mexer_historico(folio, str(id_obs), tipo, texto)
    try:
        x = _obs_em_vigor(folio, id_obs)
    except Exception as e:                              # noqa: BLE001 — sem o banco, nada muda
        return _erro("Não consegui ler as observações no banco da Gridco: %s" % str(e)[:160], 502)
    if x is None:
        return _erro("Não achei esta observação na OS %s (já foi excluída?)." % folio, 404)
    if x["tipo"] not in obs_store.EDITAVEIS:
        return _erro("Só a observação escrita muda; a automática (ticket, status, finalizado) fica como está.")
    nome, email = _quem()
    try:
        obs_store.adicionar(folio, texto, tipo, ativo=x.get("ativo") or "", quem=nome, email=email,
                            extra={"de": x["id"]})
    except ValueError as e:
        return _erro(e)
    except ga.SemCredencial as e:
        return _erro(e, 403)
    except requests.RequestException as e:
        return _erro("O banco da Gridco não respondeu: %s" % str(e)[:160], 502)
    return jsonify({"ok": True})


def _mexer_historico(folio, chave, tipo, texto):
    """Edita ou exclui uma linha do histórico importado na nota da retroativa (29/10/2026, Levi: "não foi viu" no clique
    numa delas): a linha vem da nota da OS no Fracttal, que não muda; o ajuste fica no banco do Nexus, por cima dela
    (`chamados_obs_store.ajustes_do_historico`). A chave tem de estar na nota de agora e a linha não pode estar excluída."""
    try:
        wid = _wid_ja_lido(folio, _dono()) or api._wo_id_por_folio(folio)
        det = _detalhe_enxuto(wid) if wid else {}
    except api.FracttalError as e:
        if isinstance(e, api.SessionExpired):
            raise
        return _erro("Não consegui ler a OS %s no Fracttal: %s" % (folio, str(e)[:160]), 502)
    if not det or str(det.get("folio") or "") != str(folio):
        return _erro("Não achei a OS %s no Fracttal." % folio, 404)
    chaves = {aw.chave_do_historico(h) for h in aw.ler_nota(_nota_da_os(det, None))["historico"]}
    try:
        ajustes = obs_store.ajustes_do_historico(obs_store.listar(), folio)
    except Exception as e:                              # noqa: BLE001 — sem o banco, nada muda
        return _erro("Não consegui ler as observações no banco da Gridco: %s" % str(e)[:160], 502)
    if chave not in chaves or (ajustes.get(chave) or {}).get("tipo") == "exclusao":
        return _erro("Não achei esta linha no histórico da OS %s (já foi excluída?)." % folio, 404)
    nome, email = _quem()
    try:
        obs_store.adicionar(folio, texto, tipo, ativo=det.get("code") or "", quem=nome, email=email, extra={"de": chave})
    except ValueError as e:
        return _erro(e)
    except ga.SemCredencial as e:
        return _erro(e, 403)
    except requests.RequestException as e:
        return _erro("O banco da Gridco não respondeu: %s" % str(e)[:160], 502)
    return jsonify({"ok": True})


def _ajustes_hist(folio) -> dict:
    try:
        return obs_store.ajustes_do_historico(obs_store.listar(), folio)
    except Exception:                                   # noqa: BLE001 — sem o banco, o histórico sai como veio na nota
        return {}


@bp.route("/api/acomp/<int:folio>/obs/<id_obs>/editar", methods=["POST"])
@exige_sessao
def api_obs_editar(folio, id_obs):
    """Edita uma observação escrita: uma linha nova (`edicao`); a original fica no banco."""
    return _mexer_obs(folio, id_obs, "edicao", _corpo().get("texto"))


@bp.route("/api/acomp/<int:folio>/obs/<id_obs>/excluir", methods=["POST"])
@exige_sessao
def api_obs_excluir(folio, id_obs):
    """Exclui uma observação escrita da tela: uma linha nova (`exclusao`); a original fica no banco."""
    return _mexer_obs(folio, id_obs, "exclusao", "Observação excluída")


@bp.route("/api/acomp/<int:folio>/obs", methods=["POST"])
@exige_sessao
def api_obs(folio):
    c = _corpo()
    nome, email = _quem()
    try:
        reg = obs_store.adicionar(folio, c.get("texto"), "obs", ativo=str(c.get("ativo") or ""), quem=nome, email=email)
    except ValueError as e:
        return _erro(e)
    except ga.SemCredencial as e:
        return _erro(e, 403)
    except requests.RequestException as e:
        return _erro("O banco da Gridco não respondeu: %s" % str(e)[:160], 502)
    return jsonify({"ok": True, "entrada": dict(aw.entrada(reg), novo=True)})


def _status_depois_de_concluir(wid):
    """O status da OS no Fracttal (o cabeçalho, 1 pedido); None se não deu para ler."""
    try:
        return int(api._cabecalho_os(wid).get("id_status_work_order") or 0) or None
    except (api.FracttalError, TypeError, ValueError):
        return None


@bp.route("/api/acomp/<int:folio>/finalizar", methods=["POST"])
@exige_sessao
def api_finalizar(folio):
    wid, det = _os_conferida(folio, _corpo().get("wid"))
    if not wid:
        return _erro("Não achei a OS %s no Fracttal." % folio, 404)
    res = api.concluir_os_checado(wid)                           # o Concluir do card (os_detalhe.py:896)
    if isinstance(res, dict) and res.get("ok") is False:
        return _erro(res.get("msg") or "O Fracttal não concluiu a OS.")
    # o quadro guardado leva o status que o Fracttal deu depois de concluir (em verificação ou concluída: 1 pedido, aqui,
    # e não a lista inteira na volta ao quadro); sem ele, o quadro não chuta e sai da memória, como até 20/10/2026
    st = _status_depois_de_concluir(wid)
    if st in (2, 3):
        _ajustar(wid, {"status_id": st, "status": api.WO_STATUS.get(st, "")})
    else:
        _esquecer(wid)
    # O card da OS avisa em vermelho quando a conclusão fica SEM data de fim — lá é defeito (o cronômetro não foi usado
    # numa OS de campo). Aqui é o esperado: ninguém executa a OS administrativa, e a data que vale é a da finalização,
    # que vai para o banco logo abaixo. Dizer isso é melhor que assustar a analista de chamados a cada chamado fechado.
    chk = (res or {}).get("data_fim") if isinstance(res, dict) else None
    sem_fim = bool((chk or {}).get("sem_fim")) if isinstance(chk, dict) else False
    nota = _anotar(folio, "Chamado finalizado", "finalizado", det)
    return jsonify({"ok": True, "mensagem": "Chamado finalizado: a OS %s foi concluída no Fracttal." % folio,
                    "aviso": ("Sem registro de execução, o Fracttal deixa a data de fim vazia; o quadro usa a data "
                              "desta finalização." if sem_fim else ""), "aviso_obs": nota})
