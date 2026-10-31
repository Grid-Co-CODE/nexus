"""As telas do OS Creator lendo da lista central de OS (31/10/2026, tarefa 3.3 do canto central; desenho
`docs/superpowers/specs/2026-10-30-oscreator-canto-central-design.md`, "Etapa 3"; decisões AZ a BG da 3.3).

A lista central vê TUDO (a credencial da empresa), e ninguém pode ver por ela uma OS que o Fracttal não mostra a essa pessoa.
O que estes testes seguram (o módulo é `os_web/lista_central.py`):
- depois da conferência de 19/10 da pessoa (1 pedido de 1 linha na sessão DELA, o total dela batendo com o `contar` da lista),
  o Histórico não faz pedido nenhum ao Fracttal; quem vê outro total segue com a lista dela, ao vivo, e a divergência conta no
  estado da lista (e no Raio-X); a conferência que falha nunca libera a lista central;
- "criadas por mim" e "atribuídas a mim" pela lista, e quem não casa sem ambiguidade segue ao vivo;
- o Garantias, a marcação verde dos Ativos e o Investigar ativo da mesma lista; o nº da OS vira id sem pedido só para quem
  conferiu e vê tudo; a 1ª pintura do card;
- a ação do card e a OS criada entram na lista, e o Histórico as mostra sem reler (o card não força mais o atualizar=1); a
  falha da lista nunca derruba a ação;
- o campo que o REST não trouxe leva a tela (ou o filtro) ao vivo;
- no PC (sem leitor, a lista vazia) tudo segue ao vivo, como hoje; a virada do dia não relê tudo.
O Fracttal é de mentira e conta cada ida; nada sai da máquina. Nomes, códigos, clientes e usinas são inventados (o
repositório é público)."""
import datetime as dt
import logging
import sys
from datetime import datetime, timedelta, timezone

import pytest

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
import ativos_central  # noqa: E402
import chamados_obs_store as obs_store  # noqa: E402
import os_central as OC  # noqa: E402
from os_web import acomp_web as aw  # noqa: E402
from os_web import criar_app, rotas, rotas_acomp, sessao  # noqa: E402
from os_web import historico_store as HS  # noqa: E402
from os_web import lista_central as LC  # noqa: E402
from os_web import tradicional_web as trad  # noqa: E402

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
_UTC = timezone.utc
HOJE = dt.date.today()
TODA = "toda@exemplo.invalid"              # vê no Fracttal todas as OS: a mesma visão da lista central
OUTRA = "outra@exemplo.invalid"            # também vê todas
RESTRITA = "restrita@exemplo.invalid"      # visão restrita no Fracttal: só as OS da Usina Beta (as de id par)
HOMONIMA = "homonima@exemplo.invalid"      # o nome dela é o de duas pessoas que criaram OS (dois códigos), e ela não tem código
# (id_personnel, id_account, nome) de cada pessoa no Fracttal (o `api._current_user_info`)
PESSOAS = {TODA: (601, 4001, "Pessoa Fictícia Um"), RESTRITA: (602, 4002, "Pessoa Fictícia Dois"),
           HOMONIMA: (603, 4003, "Pessoa Fictícia Três"), OUTRA: (604, 4004, "Pessoa Fictícia Quatro")}
# o pessoal do Fracttal (`api.get_responsaveis`): o código de cada pessoa; a homônima não está nele
RESPONSAVEIS = [{"code": "PF01", "name": "Pessoa Fictícia Um", "id_personnel": 601},
                {"code": "PF02", "name": "Pessoa Fictícia Dois", "id_personnel": 602},
                {"code": "PF04", "name": "Pessoa Fictícia Quatro", "id_personnel": 604}]
ALFA, BETA = "Cliente Alfa - Usina Alfa - ZZ", "Cliente Alfa - Usina Beta - ZZ"
CATALOGO = [
    {"id": 701, "code": "CAF-UAL100-INVR1.1", "description": "Inversor 1.1 { CAF-UAL100-INVR1.1 }", "cliente": "Cliente Alfa",
     "usina": ALFA, "tipo_code": "INVR", "tipo": "Inversor"},
    {"id": 702, "code": "CAF-UAL100-INVR1.2", "description": "Inversor 1.2 { CAF-UAL100-INVR1.2 }", "cliente": "Cliente Alfa",
     "usina": ALFA, "tipo_code": "INVR", "tipo": "Inversor"},
    {"id": 703, "code": "CAF-UBE200-INVR1.1", "description": "Inversor 1.1 { CAF-UBE200-INVR1.1 }", "cliente": "Cliente Alfa",
     "usina": BETA, "tipo_code": "INVR", "tipo": "Inversor"},
    {"id": 704, "code": "CAF-UBE200-INVR2.1", "description": "Inversor 2.1 { CAF-UBE200-INVR2.1 }", "cliente": "Cliente Alfa",
     "usina": BETA, "tipo_code": "INVR", "tipo": "Inversor"},
]
NOTA_CHAMADO = (aw.MARCA_NOTA + " — Marca Inventada · Inversor\n"
                "OS de campo: 10001 · Inspeção: 10002 · Ativo: CAF-UAL100-INVR1.1\n"
                "Data da falha: 10/10/2026 13:28 · Menos de 7 dias: Sim")


def _iso(dias_atras: float) -> str:
    return (datetime.now(_UTC) - timedelta(days=dias_atras)).strftime("%Y-%m-%dT%H:%M:%S")


def _universo() -> list:
    """60 OS criadas nos últimos 20 dias: as ímpares na Usina Alfa, as pares na Usina Beta (a visão restrita); as 10 primeiras
    criadas pela Pessoa Um, a 11 a 14 pela Três (PF03), a 15 e a 16 por um homônimo dela (o mesmo nome, código PF33), o resto
    pela Quatro; as 5 primeiras atribuídas à Pessoa Um; a 51 a 55 são OS de acompanhamento de chamado (etiqueta CHAMADOS, com a
    nota do chamado); a cada 5, uma concluída."""
    out = []
    for i in range(1, 61):
        beta = i % 2 == 0
        code = (("CAF-UBE200-INVR1.1" if i % 4 == 0 else "CAF-UBE200-INVR2.1") if beta
                else ("CAF-UAL100-INVR1.1" if i % 3 else "CAF-UAL100-INVR1.2"))
        if i <= 10:
            acc, cod, nome = 4001, "PF01", "Pessoa Fictícia Um"
        elif i <= 14:
            acc, cod, nome = 4003, "PF03", "Pessoa Fictícia Três"
        elif i <= 16:
            acc, cod, nome = 4033, "PF33", "Pessoa Fictícia Três"
        else:
            acc, cod, nome = 4004, "PF04", "Pessoa Fictícia Quatro"
        chamado = 51 <= i <= 55
        out.append({"id": i, "folio": str(10000 + i), "criada": _iso(1 + i % 20 + i / 1000.0), "code": code, "beta": beta,
                    "acc": acc, "cod": cod, "criador": nome, "resp": 601 if i <= 5 else 605,
                    "status": 3 if i % 5 == 0 else 1,
                    "tipo": "Administrativa" if chamado else ("Corretiva" if i % 3 else "Preventiva"),
                    "labels": ((11, "CHAMADOS"),) if chamado else (((12, "ENGENHARIA"),) if i % 7 == 0 else ()),
                    "nota": NOTA_CHAMADO if chamado else None,
                    "descricao": ("[Inversor 1.1] - Acompanhamento de chamado Marca Inventada" if chamado else "")})
    return out


UNIVERSO = _universo()
POR_ID = {o["id"]: o for o in UNIVERSO}


def _rest(o: dict, **mudar) -> dict:
    """A linha do REST `work_orders` (uma tarefa) desta OS: o que o leitor do servidor entrega à lista central."""
    o = dict(o, **mudar)
    fim = _iso(0.5) if o["status"] == 3 else None
    return {"id_work_orders_tasks": 9000 + o["id"], "id_work_order": o["id"], "wo_folio": o["folio"],
            "id_status_work_order": str(o["status"]), "description": o["descricao"] or "OS central %d" % o["id"],
            "items_log_description": "Inversor %s { %s }" % (o["code"][-3:], o["code"]), "code": o["code"],
            "tasks_log_task_type_main": o["tipo"], "creation_date": o["criada"], "date_maintenance": o["criada"],
            "initial_date": o["criada"] if o["id"] % 4 == 0 else None, "event_date": o["criada"], "final_date": fim,
            "wo_final_date": fim, "created_by": o["criador"], "code_create_by": o["cod"], "user_assigned": "Pessoa Resp",
            "personnel_description": "Pessoa Resp", "id_personnel": o["resp"], "trigger_description": "NO_SCHEDULE_TASK",
            "labels": [{"id": i, "description": n} for i, n in o["labels"]], "task_note": o["nota"]}


def _viva(o: dict) -> dict:
    """A linha que o caminho de hoje (`api.list_minhas_os`, pela sessão da pessoa) dá: a descrição diz "ao vivo", para o
    teste saber de onde a tela leu."""
    st = o["status"]
    return {"id": o["id"], "folio": o["folio"], "cliente": "Cliente Alfa", "usina": "Usina Beta" if o["beta"] else "Usina Alfa",
            "tipo": "Inversor", "ativo": "Inversor", "descricao": o["descricao"] or "OS ao vivo %d" % o["id"],
            "code": o["code"], "codigos": [o["code"]], "criado_por": o["criador"],
            "etiquetas": [{"id": i, "nome": n} for i, n in o["labels"]], "atribuido_a": "Pessoa Resp",
            "id_atribuido": o["resp"], "data": o["criada"], "event_date": o["criada"], "data_fim": "",
            "programada": o["criada"], "inicio": "", "equipe": "Pessoa Resp", "gatilho": "Tarefa não agendada",
            "status_id": st, "status": api.WO_STATUS[st], "tipo_tarefa": o["tipo"], "note": o["nota"] or ""}


class _Fracttal:
    """O Fracttal de mentira, por pessoa (a sessão diz quem pede): a lista, os totais da conferência, o quadro, os códigos
    recentes e o nº da OS. Cada pedido fica anotado com o tipo e quem pediu."""

    def __init__(self):
        self.pedidos = []
        self.visao = {RESTRITA: {o["id"] for o in UNIVERSO if o["beta"]}}
        self.fora = False

    @staticmethod
    def _quem():
        return sessao.email_atual() or "?"

    def _vistas(self):
        ids = self.visao.get(self._quem())
        return [o for o in UNIVERSO if ids is None or o["id"] in ids]

    def _filtrar(self, modo, id_account, id_label, de, ate, status_ids):
        idp, idacc, _nome = PESSOAS.get(self._quem(), (None, None, ""))
        out = []
        for o in self._vistas():
            if de and o["criada"][:len(str(de))] < str(de):
                continue
            if ate and o["criada"][:10] > str(ate)[:10]:
                continue
            if modo == "atribuidas":
                if o["resp"] != idp:
                    continue
            elif id_account != "TODOS" and o["acc"] != (idacc if id_account is None else int(id_account)):
                continue
            if id_label and id_label not in [i for i, _n in o["labels"]]:
                continue
            if status_ids and o["status"] not in status_ids:
                continue
            out.append(o)
        return out

    def _anota(self, tipo, *extra):
        self.pedidos.append((tipo, self._quem()) + extra)
        if self.fora:
            raise api.FracttalError("O Fracttal não respondeu a tempo (HTTP 429)")

    def list_minhas_os(self, modo="criadas", id_account=None, id_label=None, de=None, ate=None, status_ids=None,
                       cap=api.HISTORICO_CAP, info=None, progresso=None, meta_ja=None):
        self._anota("lista", modo, id_account, de, ate)
        out = [_viva(o) for o in self._filtrar(modo, id_account, id_label, de, ate, status_ids)]
        out.sort(key=lambda d: d["data"], reverse=True)
        if isinstance(info, dict):
            info.update({"total": len(out), "cap": api.HISTORICO_CAP})
        return out

    def pagina(self, modo="criadas", id_account=None, id_label=None, de=None, ate=None, status_ids=None, busca="",
               pagina=1, limite=60, com_meta=False):
        self._anota("total", modo, id_account, de, ate)
        return {"total": len(self._filtrar(modo, id_account, id_label, de, ate, status_ids)), "linhas": [], "tem_mais": False}

    def _chamados(self, de):
        return [o for o in self._vistas() if 11 in [i for i, _n in o["labels"]] and o["criada"][:10] >= str(de or "")[:10]]

    def total_chamados(self, de=None):
        self._anota("total_chamados", de)
        return len(self._chamados(de))

    def list_chamados(self, de=None, ate=None, status_ids=None, info=None, meta_ja=None):
        self._anota("chamados", de)
        out = [_viva(o) for o in self._chamados(de)]
        if isinstance(info, dict):
            info.update({"total": len(out), "cap": api.HISTORICO_CAP})
        return out

    def codigos_os_recentes(self, dias=30):
        self._anota("recentes", dias)
        return sorted({o["code"] for o in self._vistas() if o["criada"] >= _iso(dias)})

    def os_por_folio(self, folio):
        self._anota("folio", folio)
        o = next((o for o in self._vistas() if o["folio"] == str(folio).strip()), None)
        return {"id": o["id"], "wo_folio": o["folio"]} if o else None

    def n(self, tipo, quem=None) -> int:
        return sum(1 for p in self.pedidos if p[0] == tipo and (quem is None or p[1] == quem))


@pytest.fixture
def fr(monkeypatch):
    import requests

    def sem_rede(*a, **k):                    # a cota do Fracttal é da empresa: aqui nada sai da máquina
        raise AssertionError("o teste tentou ir à rede")
    monkeypatch.setattr(requests.Session, "request", sem_rede)

    def sem_fracttal(metodo, *a, **k):        # o que o teste não previu não vai a lugar nenhum
        raise AssertionError("um pedido ao Fracttal que o teste não previu: %s" % metodo)
    monkeypatch.setattr(api, "_rpc_call", sem_fracttal)
    f = _Fracttal()
    monkeypatch.setattr(api, "list_minhas_os", f.list_minhas_os)
    monkeypatch.setattr(api, "list_minhas_os_pagina", f.pagina)
    monkeypatch.setattr(api, "total_chamados", f.total_chamados)
    monkeypatch.setattr(api, "list_chamados", f.list_chamados)
    monkeypatch.setattr(api, "codigos_os_recentes", f.codigos_os_recentes)
    monkeypatch.setattr(api, "os_por_folio", f.os_por_folio)
    monkeypatch.setattr(api, "_current_user_info", lambda: PESSOAS.get(sessao.email_atual(), (None, None, "")))
    monkeypatch.setattr(api, "get_responsaveis", lambda: [dict(p) for p in RESPONSAVEIS])
    monkeypatch.setattr(api, "get_labels", lambda: [{"id": 11, "description": "CHAMADOS"},
                                                    {"id": 12, "description": "ENGENHARIA"}])
    monkeypatch.setattr(api, "get_pessoas_contas", lambda: {
        "pessoas": [{"id_account": acc, "nome": nome} for _p, acc, nome in PESSOAS.values()],
        "eu": PESSOAS.get(sessao.email_atual(), (None, None, ""))[1]})
    monkeypatch.setattr(api, "_read_asset_cache", lambda *a, **k: [])
    monkeypatch.setattr(api, "tickets_os3_em_massa", lambda ids: {})
    monkeypatch.setattr(obs_store, "_linhas", lambda: [])              # o banco da Gridco: nenhum teste vai
    obs_store._estado.update(lista=None, lido=0.0)
    monkeypatch.setattr(rotas, "_em_segundo_plano", lambda fn: None)   # sem renovação por trás: só o que a tela faz
    monkeypatch.setattr(rotas_acomp, "_em_segundo_plano", lambda fn: None)
    relogio = {"t": 1000.0}
    monkeypatch.setattr(HS, "_relogio", lambda: relogio["t"])
    f.relogio = relogio
    ativos_central.reiniciar()
    ativos_central.trocar([dict(a) for a in CATALOGO], "rpc")
    HS.limpar()
    LC.limpar()
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    yield f
    HS.limpar()
    LC.limpar()
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    ativos_central.reiniciar()


def _encher(linhas=None) -> None:
    """A lista central de uma noite inteira (a janela de 365 dias lida inteira), com as 60 OS do universo: o que o leitor do
    servidor entrega. No PC e nos outros testes a lista fica vazia."""
    OC.receber(linhas if linhas is not None else [_rest(o) for o in UNIVERSO], OC.NOITE, desde=_iso(400)[:10])


def _cliente(email=TODA):
    c = criar_app(segredo="teste", testing=False).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": email, "perfil": "ADMINISTRATOR"}
    return c


def _hist(c, q="modo=cos"):
    r = c.get("/os/historico?" + q)
    assert r.status_code == 200, r.status_code
    return r.get_data(as_text=True)


def _linha(html, folio):
    i = html.index(">%s</a>" % folio)
    return html[html.rindex("<tr ", 0, i):html.index("</tr>", i)]


def _central(html, i) -> bool:
    return "OS central %d</td>" % i in html


def _ao_vivo(html, i) -> bool:
    return "OS ao vivo %d</td>" % i in html


# ── o Histórico ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_historico_sem_pedido_ao_fracttal(fr):
    _encher()
    a = _cliente(TODA)
    h = _hist(a, "modo=cos")
    assert _central(h, 1) and _central(h, 60) and not _ao_vivo(h, 1)
    assert fr.n("lista") == 0 and fr.n("total") == 1            # só a conferência de 19/10 dela: 1 pedido de 1 linha
    assert fr.pedidos[0][2:4] == ("criadas", "TODOS")           # na sessão DELA, com os filtros da visão
    assert "Lista das " in h
    # depois da conferência: a mesma visão, o "Criado por: Todos" (os mesmos filtros) e a atualização de 10 min, nada
    _hist(a, "modo=cos")
    _hist(a, "modo=criadas&pessoa=TODOS")
    _hist(a, "modo=cos&nx_auto=1")
    assert fr.n("lista") == 0 and fr.n("total") == 1
    # a outra pessoa que vê tudo: a conferência dela, e a mesma lista
    b = _cliente(OUTRA)
    assert _central(_hist(b, "modo=cos"), 2)
    assert fr.n("lista") == 0 and fr.n("total", OUTRA) == 1
    # a OS nova que o leitor trouxe aparece sem pedido nenhum (a conferência guardada ainda bate: 61 contra 60)
    nova = dict(POR_ID[1], id=61, folio="10061", criada=_iso(0.01), descricao="")
    OC.receber([_rest(nova)], OC.NOVAS)
    assert _central(_hist(a, "modo=cos"), 61) and fr.n("total") == 2 and fr.n("lista") == 0
    e = OC.estado()["conferencias"]["todos"]
    assert e["n"] == 2 and e["divergiram"] == 0


def test_visao_restrita_segue_com_a_dela(fr):
    _encher()
    r = _cliente(RESTRITA)
    h = _hist(r, "modo=cos")
    # conferiu (1 pedido na sessão dela) e deu outro total: a lista dela, ao vivo, como hoje
    assert fr.n("total", RESTRITA) == 1 and fr.n("lista", RESTRITA) == 1
    assert _ao_vivo(h, 2) and "OS central" not in h
    assert ">10001</a>" not in h                                # a OS da Usina Alfa, que o Fracttal não mostra a ela
    e = OC.estado()["conferencias"]["todos"]
    assert e["n"] == 1 and e["divergiram"] == 1
    assert (e["ultima_divergencia"]["fracttal"], e["ultima_divergencia"]["lista"]) == (30, 60)
    # nem pelo nº, nem pela 1ª pintura do card: ela não conferiu a visão inteira
    assert r.get("/os/api/os/1/previa").status_code == 204
    with sessao.contexto(JWT, RESTRITA):
        assert api._wo_id_por_folio("10008") == 8
    assert fr.n("folio", RESTRITA) == 1
    # quem vê tudo, depois dela, lê da lista central (a dela não vira a de todos)
    t = _cliente(TODA)
    assert _central(_hist(t, "modo=cos"), 1) and fr.n("lista", TODA) == 0
    # a conferência que falha (o Fracttal fora) nunca libera a lista central: a tela segue como hoje
    fr.fora = True
    h = _hist(_cliente(OUTRA), "modo=cos")
    assert "OS central" not in h
    assert OC.estado()["conferencias"]["todos"]["falharam"] == 1


def test_criadas_por_mim_pela_lista_central(fr):
    _encher()
    a = _cliente(TODA)
    h = _hist(a, "modo=criadas")                                # o padrão do Histórico Geral: as criadas por mim
    assert all(_central(h, i) for i in range(1, 11)) and not _central(h, 11)
    assert fr.n("lista") == 0 and fr.n("total") == 1
    assert fr.pedidos[-1][2:4] == ("criadas", None)             # a conferência é a de "criadas por mim", na sessão dela
    # "atribuídas a mim", pelo id da pessoa no Fracttal
    h = _hist(a, "modo=atribuidas")
    assert all(_central(h, i) for i in range(1, 6)) and not _central(h, 6)
    assert fr.n("lista") == 0 and fr.n("total") == 2
    # "Criado por" outra pessoa (o id da conta): o nome dela no pessoal dá o código, e a lista responde
    h = _hist(a, "modo=criadas&pessoa=4004")
    assert _central(h, 17) and not _central(h, 1) and fr.n("lista") == 0
    # a homônima: o nome casa com OS de duas pessoas (dois códigos) e ela não tem código no pessoal: ao vivo, sem conferir
    x = _cliente(HOMONIMA)
    h = _hist(x, "modo=criadas")
    assert fr.n("lista", HOMONIMA) == 1 and fr.n("total", HOMONIMA) == 0
    assert _ao_vivo(h, 11) and "OS central" not in h


def test_virada_do_dia_nao_rele_tudo(fr):
    _encher()
    d1 = "de=%s&ate=%s" % (HOJE - dt.timedelta(days=30), HOJE)
    d2 = "de=%s&ate=%s" % (HOJE - dt.timedelta(days=29), HOJE + dt.timedelta(days=1))
    a = _cliente(TODA)
    _hist(a, "modo=cos&" + d1)
    _hist(a, "modo=cos&" + d2)
    assert fr.n("lista", TODA) == 0 and fr.n("total", TODA) == 2     # o dia novo: só a conferência dele, 1 pedido de 1 linha
    # o caminho de hoje (a visão restrita, ao vivo): a chave da lista muda com o período, e a lista inteira vem de novo
    r = _cliente(RESTRITA)
    _hist(r, "modo=cos&" + d1)
    _hist(r, "modo=cos&" + d2)
    assert fr.n("lista", RESTRITA) == 2


def test_campo_que_o_rest_nao_trouxe_vai_ao_vivo(fr):
    linhas = [_rest(o) for o in UNIVERSO]
    for x in linhas:
        x["trigger_description"] = None                         # o REST sem o gatilho (a 1ª noite diz quanto veio)
    _encher(linhas)
    assert OC.estado()["campos"]["pct"]["gatilho"] == 0
    a = _cliente(TODA)
    assert _ao_vivo(_hist(a, "modo=cos"), 1) and fr.n("lista") == 1          # a Visão COS mostra o gatilho: ao vivo
    assert _central(_hist(a, "modo=criadas&pessoa=TODOS"), 1)                 # o Histórico Geral não mostra: da lista
    assert fr.n("lista") == 1
    # o Garantias lê a nota do chamado: sem ela na lista (o REST não a trouxe), o quadro vai ao vivo
    OC.reiniciar()
    _encher([_rest(o, nota=None) for o in UNIVERSO])
    a.get("/os/chamados/acompanhamento")
    assert fr.n("chamados") == 1


# ── as outras telas da mesma lista ─────────────────────────────────────────────────────────────────────────────────────
def test_garantias_e_ativos_e_investigar_da_mesma_lista(fr):
    _encher()
    a = _cliente(TODA)
    h = a.get("/os/chamados/acompanhamento").get_data(as_text=True)
    assert all('data-folio="%d"' % (10000 + i) in h for i in range(51, 56))       # as 5 OS de acompanhamento, da lista
    assert 'data-folio="10050"' not in h                                           # a que não é de chamado não entra
    assert fr.n("chamados") == 0 and fr.n("total_chamados") == 1   # a conferência do quadro, na sessão dela (a de 19/10)
    # a OS do quadro que a lista sabe velha ("a conferir": as abertas não a trouxeram) leva o quadro ao vivo no Atualizar
    OC.receber([_rest(o) for o in UNIVERSO if o["status"] == 1 and o["id"] != 51], OC.ABERTAS)
    assert 51 in OC.atual().a_conferir
    a.get("/os/chamados/acompanhamento?atualizar=1")
    assert fr.n("chamados") == 1
    # a marcação verde dos Ativos: os códigos das OS dos últimos 30 dias, da lista (a de hoje já era uma para todos)
    j = a.get("/os/api/ativos/recentes?dias=30").get_json()
    assert set(j["codes"]) == {o["code"] for o in UNIVERSO} and fr.n("recentes") == 0
    # o Investigar ativo: as OS do inversor e da usina pelo índice por código, com a conferência da janela de 30 dias (a
    # mesma da Visão COS: quem abriu uma não confere de novo na outra)
    _hist(a, "modo=cos")
    n = fr.n("total")
    h = a.get("/os/historico/ativo?codigo=CAF-UAL100-INVR1.1&usina=" + ALFA.replace(" ", "%20")
              + "&nome=Inversor%201.1").get_data(as_text=True)
    meus = [o["id"] for o in UNIVERSO if o["code"] == "CAF-UAL100-INVR1.1"]
    da_usina = [o["id"] for o in UNIVERSO if not o["beta"]]
    assert all(">%d</a>" % (10000 + i) in h for i in da_usina) and ">10002</a>" not in h
    assert "Este ativo <b>%d</b>" % len(meus) in h and "A usina inteira <b>%d</b>" % len(da_usina) in h
    assert fr.n("lista") == 0 and fr.n("total") == n
    # o nº da OS vira o id sem pedido nenhum, para quem conferiu e vê tudo
    with sessao.contexto(JWT, TODA):
        assert api._wo_id_por_folio("10007") == 7 and api._wo_id_por_folio("99999") is None
    assert fr.n("folio", TODA) == 1                             # o nº que a lista não conhece vai ao vivo


def test_a_primeira_pintura_do_card_vem_da_lista(fr):
    _encher()
    a = _cliente(TODA)
    assert a.get("/os/api/os/7/previa").status_code == 204          # antes da conferência, nada (fail-closed)
    _hist(a, "modo=cos")
    r = a.get("/os/api/os/7/previa")
    h = r.get_data(as_text=True)
    assert r.status_code == 200 and "OS 10007" in h and "OS central 7" in h and "Carregando" in h
    assert a.get("/os/api/os/999/previa").status_code == 204        # a OS que a lista não conhece: o card ao vivo, como hoje
    assert fr.n("lista") == 0 and fr.n("total") == 1


# ── as ações entram na lista ───────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def ao_vivo(monkeypatch):
    """O que o card lê de UMA OS (as tarefas e o cabeçalho), pela sessão da pessoa: o `atualizar_os` da ação lê por aqui."""
    os_ = {o["id"]: dict(o) for o in UNIVERSO}
    lidas = []

    def tarefas(metodo, wid, params, usar_guardada=True):
        lidas.append(wid)
        o = os_[wid]
        return [{"id": 9000 + wid, "id_work_order": wid, "wo_folio": o["folio"],
                 "tasks_description": o["descricao"] or "OS central %d" % wid,
                 "items_description": "Inversor { %s }" % o["code"], "code_item": o["code"],
                 "tasks_types_main_description": o["tipo"], "date_maintenance": o["criada"],
                 "id_status_work_order": o["status"], "personnel_description": o.get("resp_nome", "Pessoa Resp"),
                 "id_assigned_user": o["resp"], "creation_date": o["criada"]}]

    def cabecalho(wid):
        o = os_[wid]
        return {"wo_folio": o["folio"], "id_status_work_order": o["status"], "created_by": o["criador"],
                "code_create_by": o["cod"], "creation_date": o["criada"],
                "labels": [{"id": i, "description": n} for i, n in o["labels"]]}
    monkeypatch.setattr(api, "_leitura_da_os", tarefas)
    monkeypatch.setattr(api, "_cabecalho_os", cabecalho)
    return os_, lidas


def test_card_alterado_aparece_sem_releitura(fr, ao_vivo, monkeypatch):
    os_, lidas = ao_vivo
    _encher()
    a = _cliente(TODA)
    assert "Em Processo" in _linha(_hist(a, "modo=cos"), "10001")
    # o Concluir do card: o Fracttal confirma, e a ação põe a OS na lista central na hora (lida pela sessão dela)
    monkeypatch.setattr(api, "concluir_os_checado", lambda wid: {"ok": True, "data_fim": None})
    os_[1]["status"] = 3
    r = a.post("/os/api/os/1/concluir", json={"folio": "10001"})
    assert r.status_code == 200 and r.get_json()["ok"] and lidas == [1]
    assert OC.atual().por_id[1].status_id == 3
    # ao fechar o card a tela volta SEM o atualizar=1 (só diz que a OS mudou): a linha já vem da lista central
    h = _hist(a, "modo=cos&mudou=1")
    assert "Concluída" in _linha(h, "10001")
    assert fr.n("lista") == 0 and fr.n("total") == 1
    fechar = h[h.index("function fechar()"):]
    fechar = fechar[:fechar.index("\n  }\n")]
    assert "enviar(true)" not in fechar and "enviar(false);" in fechar and 'mu.name = "mudou"' in fechar


def test_as_acoes_entram_na_lista_e_a_falha_nao_derruba(fr, ao_vivo, monkeypatch, caplog):
    os_, lidas = ao_vivo
    _encher()
    a = _cliente(TODA)
    _hist(a, "modo=cos")
    # cancelar e trocar o responsável: depois de o Fracttal confirmar, a OS entra na lista como ficou
    monkeypatch.setattr(api, "cancel_os", lambda wid, idm, note="": None)
    os_[2]["status"] = 4
    assert a.post("/os/api/os/2/cancelar", json={"id_status_custom": 9, "folio": "10002"}).get_json()["ok"]
    assert OC.atual().por_id[2].status_id == 4
    monkeypatch.setattr(api, "mudar_responsavel", lambda wid, idp, nota=None: {"ok": True})
    os_[3].update(resp=777, resp_nome="Pessoa Fictícia Sete")
    assert a.post("/os/api/os/3/responsavel", json={"id_personnel": 777, "name": "Pessoa Fictícia Sete"}).get_json()["ok"]
    assert OC.atual().por_id[3].id_atribuido == 777
    # a OS criada (Criar OS do zero, uma por ativo) entra na hora, e a Visão COS a mostra sem reler o Fracttal
    nova = dict(POR_ID[1], id=62, folio="10062", criada=_iso(0.001), descricao="")
    os_[62] = nova
    monkeypatch.setattr(trad, "montar_payload", lambda corpo, assets, imagens, frases: ("bulk", ([],), {}, None))
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: [])
    monkeypatch.setattr(api, "create_work_orders_bulk", lambda *a, **k: [
        {"code": "CAF-UAL100-INVR1.1", "ok": True, "os": {"id_task": 5, "id_work_order": 62, "wo_folio": "10062"}},
        {"code": "CAF-UAL100-INVR1.2", "ok": False, "erro": "o Fracttal recusou"}])
    assert a.post("/os/api/tradicional/criar", json={"x": 1}).status_code == 200
    assert OC.atual().por_id[62].folio == "10062"
    assert ">10062</a>" in _hist(a, "modo=cos") and fr.n("lista") == 0
    # a falha da lista nunca derruba a ação: a resposta à pessoa não depende dela (vai ao log)
    def quebra(*a, **k):
        raise RuntimeError("a lista quebrou")
    monkeypatch.setattr(OC, "atualizar_os", quebra)
    os_[4]["status"] = 4
    with caplog.at_level(logging.ERROR, logger="oscreator.lista_central"):
        r = a.post("/os/api/os/4/cancelar", json={"id_status_custom": 9, "folio": "10004"})
    assert r.status_code == 200 and r.get_json()["ok"]
    assert any("a lista quebrou" in (x.exc_text or "") or "a lista quebrou" in x.getMessage() for x in caplog.records)
    # os ids que a criação devolve, em qualquer dos formatos das funções de criar
    assert LC.ids_criados([{"ok": True, "os": {"id_work_order": 1}}, {"ok": False, "os": {"id_work_order": 2}}]) == [1]
    assert LC.ids_criados({"ok": True, "folio": "9", "id_work_order": 3}) == [3]
    assert LC.ids_criados({"ok": True, "os": {"id_tasks": [1, 2], "wo_folio": None}}) == []
    assert LC.ids_criados([{"ok": True, "asset": "x", "folio": "1", "id_work_order": 4}, None, "x"]) == [4]


# ── o PC e o Raio-X ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_pc_segue_ao_vivo(fr, ao_vivo, monkeypatch):
    """Sem o leitor (o PC, e os testes de antes), a lista central fica vazia: toda tela segue pelo caminho de hoje, sem uma
    conferência à toa, e a ação não lê a OS para uma lista que ninguém lê."""
    _os, lidas = ao_vivo
    a = _cliente(TODA)
    h = _hist(a, "modo=cos")
    assert _ao_vivo(h, 1) and fr.n("lista") == 1 and fr.n("total") == 0    # como hoje: a 1ª pessoa nem confere
    _hist(a, "modo=cos&mudou=1")                                # o card mudou a OS: no caminho de hoje, a lista vem de novo
    assert fr.n("lista") == 2
    assert fr.n("chamados") == 0
    a.get("/os/chamados/acompanhamento")
    assert fr.n("chamados") == 1
    a.get("/os/api/ativos/recentes?dias=30")
    assert fr.n("recentes") == 1
    with sessao.contexto(JWT, TODA):
        assert api._wo_id_por_folio("10007") == 7
    assert fr.n("folio") == 1
    assert a.get("/os/api/os/1/previa").status_code == 204
    assert OC.estado()["conferencias"] == {}
    # a ação do card: o Fracttal confirma, e nada mais vai a ele (a lista fora de uso não gasta a leitura da OS)
    monkeypatch.setattr(api, "cancel_os", lambda wid, idm, note="": None)
    assert a.post("/os/api/os/2/cancelar", json={"id_status_custom": 9, "folio": "10002"}).get_json()["ok"]
    assert lidas == [] and not OC.atual().por_id


def test_a_medida_dos_campos_volta_com_a_copia_em_disco(tmp_path):
    """A medida dos campos vai na cópia em disco (`campos_rest`): sem ela, depois de cada deploy as telas iriam ao vivo até a
    próxima leitura grande (de noite, só às 03:21)."""
    OC.reiniciar(pasta=str(tmp_path))
    _encher()
    assert OC.esperar_gravacao(10)
    medida = OC.campos_medidos()
    assert medida and medida["pct"]["nº"] == 100
    OC.reiniciar(pasta=str(tmp_path))                          # o reinício: só o disco, nenhum pedido
    assert OC.campos_medidos() == medida and OC.atual().janela[0]


def test_as_conferencias_no_raio_x(fr):
    from nexus.casca import raio_x
    _encher()
    _hist(_cliente(TODA), "modo=cos")
    _hist(_cliente(RESTRITA), "modo=cos")
    linhas = dict(raio_x._linhas_da_lista_de_os(OC.estado()))
    txt = linhas["Conferências das telas"]
    assert "2 conferências" in txt and "1 divergiu" in txt and "Fracttal 30 contra 60 da lista" in txt
    assert "@" not in txt and "Pessoa" not in txt                # só contagens: nunca quem
