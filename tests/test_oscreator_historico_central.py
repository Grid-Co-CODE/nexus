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
import re
import sys
import threading
import time
import types
from collections import defaultdict
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
# o pessoal do Fracttal (`api.ler_pessoal`, o leitor do catálogo de pessoas): o código de cada pessoa; a homônima
# não está nele
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


# a OS que "acabou de ser criada": depois da mais nova do universo (a 60, de ontem) e ainda DENTRO do período padrão da tela. O
# "até" do período é a data local, e a criação é em UTC: a OS de 1 min atrás, depois das 21:00, já é de amanhã em UTC e fica
# fora do período (a conta da lista e a do Fracttal a deixam de fora, as duas). 6 h atrás é hoje em qualquer hora do dia
RECENTE = 0.25


def _universo() -> list:
    """60 OS criadas nos últimos 21 dias, da 1 (a mais velha) à 60 (a mais nova, ontem): o id do Fracttal cresce com a criação,
    e a página da conferência vem pelo id (rodada 2 da 3.3); as ímpares na Usina Alfa, as pares na Usina Beta (a visão
    restrita); as 10 primeiras criadas pela Pessoa Um, a 11 a 14 pela Três (PF03), a 15 e a 16 por um homônimo dela (o mesmo
    nome, código PF33), o resto pela Quatro; as 5 primeiras atribuídas à Pessoa Um; a 51 a 55 são OS de acompanhamento de
    chamado (etiqueta CHAMADOS, com a nota do chamado); a cada 5, uma concluída."""
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
        out.append({"id": i, "folio": str(10000 + i), "criada": _iso(1 + (60 - i) / 3.0), "code": code, "beta": beta,
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
        self.universo = [dict(o) for o in UNIVERSO]      # as OS que o Fracttal tem (o teste soma as que ele criou)
        self.visao = {RESTRITA: {o["id"] for o in UNIVERSO if o["beta"]}}
        self.fora = False
        self.inesperados = []                             # o pedido que o teste não previu (conferido no fim do teste)

    @staticmethod
    def _quem():
        return sessao.email_atual() or "?"

    def _vistas(self):
        ids = self.visao.get(self._quem())
        return [o for o in self.universo if ids is None or o["id"] in ids]

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
        """Uma página do RPC (`api.list_minhas_os_pagina`): o total e as linhas dela, pelo id da mais nova para trás (o RPC
        ordena pelo id, não pela criação)."""
        self._anota("total", modo, id_account, de, ate)
        todas = sorted(self._filtrar(modo, id_account, id_label, de, ate, status_ids), key=lambda o: o["id"], reverse=True)
        ini = (max(1, int(pagina)) - 1) * int(limite)
        linhas = [_viva(o) for o in todas[ini:ini + int(limite)]]
        return {"total": len(todas), "linhas": linhas, "tem_mais": ini + len(linhas) < len(todas)}

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
    f = _Fracttal()

    # o pedido que o teste não previu não vai a lugar nenhum, e fica ANOTADO: o código que o faz costuma engolir a exceção
    # (`except Exception`, a ação que nunca derruba a tela), e o teste o confere no fim (rodada 1 da 3.3, Minor 4)
    def sem_rede(*a, **k):                    # a cota do Fracttal é da empresa: aqui nada sai da máquina
        f.inesperados.append(("rede", str(a[1:3])))
        raise AssertionError("o teste tentou ir à rede")
    monkeypatch.setattr(requests.Session, "request", sem_rede)

    def sem_fracttal(metodo, *a, **k):
        f.inesperados.append(("fracttal", metodo))
        raise AssertionError("um pedido ao Fracttal que o teste não previu: %s" % metodo)
    monkeypatch.setattr(api, "_rpc_call", sem_fracttal)
    monkeypatch.setattr(api, "list_minhas_os", f.list_minhas_os)
    monkeypatch.setattr(api, "list_minhas_os_pagina", f.pagina)
    monkeypatch.setattr(api, "total_chamados", f.total_chamados)
    monkeypatch.setattr(api, "list_chamados", f.list_chamados)
    monkeypatch.setattr(api, "codigos_os_recentes", f.codigos_os_recentes)
    monkeypatch.setattr(api, "os_por_folio", f.os_por_folio)
    monkeypatch.setattr(api, "_current_user_info", lambda: PESSOAS.get(sessao.email_atual(), (None, None, "")))
    monkeypatch.setattr(api, "ler_pessoal", lambda: [dict(p) for p in RESPONSAVEIS])
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
    LC.esperar_releituras(5)                  # a releitura da ação que passou do prazo termina antes da limpeza
    HS.limpar()
    LC.limpar()
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    ativos_central.reiniciar()
    assert not f.inesperados, "pedidos que o teste não previu: %r" % (f.inesperados,)


def _encher(linhas=None) -> None:
    """A lista central de uma noite inteira (a janela de 365 dias lida inteira), com as 60 OS do universo: o que o leitor do
    servidor entrega. No PC e nos outros testes a lista fica vazia."""
    OC.receber(linhas if linhas is not None else [_rest(o) for o in UNIVERSO], OC.NOITE, desde=_iso(400)[:10])


# a marca que a ponte do Nexus põe em todo pedido ao OS Creator (`ponte.lista_central`, rodada 4 da 3.3): a pessoa está
# liberada para a lista central. Os testes do clone a põem por padrão; sem ela (None), o pedido vai sem a marca
LIBERACAO = "os_web.lista_central"


def _cliente(email=TODA, liberada=True):
    c = criar_app(segredo="teste", testing=False).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": email, "perfil": "ADMINISTRATOR"}
    if liberada is not None:
        c.environ_base[LIBERACAO] = liberada
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
    assert fr.n("lista") == 0 and fr.n("total") == 1            # só a conferência dela: 1 pedido (a página das mais novas)
    assert fr.pedidos[0][2:4] == ("criadas", "TODOS")           # na sessão DELA: o "Todos" do período
    assert "Lista das " in h
    # depois da conferência: a mesma visão, o "Criado por: Todos" e a atualização de 10 min (o mesmo período), nada
    _hist(a, "modo=cos")
    _hist(a, "modo=criadas&pessoa=TODOS")
    _hist(a, "modo=cos&nx_auto=1")
    assert fr.n("lista") == 0 and fr.n("total") == 1
    # a outra pessoa que vê tudo: a conferência dela, e a mesma lista
    b = _cliente(OUTRA)
    assert _central(_hist(b, "modo=cos"), 2)
    assert fr.n("lista") == 0 and fr.n("total", OUTRA) == 1
    # a OS nova que a faixa das novas trouxe, emendada (a marca d'água anda até ela): a lista tem uma OS que a página dela não
    # trouxe, e a conferência é pedida de novo (Ruling BU); quem a vê, a vê. Depois, nada
    nova = dict(POR_ID[1], id=61, folio="10061", criada=_iso(RECENTE), descricao="")
    fr.universo.append(nova)
    OC.receber([_rest(nova), _rest(POR_ID[60])], OC.NOVAS, desde=POR_ID[60]["criada"])
    assert OC.atual().marca == nova["criada"]
    assert _central(_hist(a, "modo=cos"), 61) and fr.n("total") == 3 and fr.n("lista") == 0
    _hist(a, "modo=cos")
    assert fr.n("total") == 3                                   # a medida nova dela ficou guardada
    e = OC.estado()["conferencias"]["histórico"]
    assert e["n"] == 3 and e["divergiram"] == 0


def test_visao_restrita_segue_com_a_dela(fr):
    _encher()
    r = _cliente(RESTRITA)
    h = _hist(r, "modo=cos")
    # conferiu (1 pedido na sessão dela) e deu outro total: a lista dela, ao vivo, como hoje
    assert fr.n("total", RESTRITA) == 1 and fr.n("lista", RESTRITA) == 1
    assert _ao_vivo(h, 2) and "OS central" not in h
    assert ">10001</a>" not in h                                # a OS da Usina Alfa, que o Fracttal não mostra a ela
    e = OC.estado()["conferencias"]["histórico"]
    assert e["n"] == 1 and e["divergiram"] == 1
    # as duas contas param na marca d'água (a criação da OS 60, que fica de fora das duas): 29 dela contra 59 da lista
    assert (e["ultima_divergencia"]["fracttal"], e["ultima_divergencia"]["lista"]) == (29, 59)
    # nem pelo nº, nem pela 1ª pintura do card: ela não passou
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
    assert OC.estado()["conferencias"]["histórico"]["falharam"] == 1


def test_criadas_por_mim_pela_lista_central(fr):
    _encher()
    a = _cliente(TODA)
    h = _hist(a, "modo=criadas")                                # o padrão do Histórico Geral: as criadas por mim
    assert all(_central(h, i) for i in range(1, 11)) and not _central(h, 11)
    assert fr.n("lista") == 0 and fr.n("total") == 1
    assert fr.pedidos[-1][2:4] == ("criadas", "TODOS")          # a conferência é o "Todos" do período, na sessão dela
    # "atribuídas a mim", pelo id da pessoa no Fracttal: o mesmo período, a mesma conferência (sem pedido)
    h = _hist(a, "modo=atribuidas")
    assert all(_central(h, i) for i in range(1, 6)) and not _central(h, 6)
    assert fr.n("lista") == 0 and fr.n("total") == 1
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
    assert fr.n("chamados") == 0 and fr.n("total") == 1        # a conferência dos 365 dias do quadro, na sessão dela
    # o total da cópia é o do Fracttal de quem a monta (o `total_chamados` dela, a chave do `_dono`: rodada 4, a sonda V1)
    assert fr.n("total_chamados") == 1
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
    # o nº da OS vira o id sem pedido nenhum, para quem conferiu e vê tudo (e foi liberada: a marca do pedido, aqui fora dele)
    with sessao.contexto(JWT, TODA), LC.liberacao(True):
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
    nova = dict(POR_ID[1], id=62, folio="10062", criada=_iso(RECENTE), descricao="")
    os_[62] = nova
    fr.universo.append(nova)                                    # o Fracttal tem a OS que acabou de criar
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
    assert "2 conferências" in txt and "1 divergiu" in txt and "Fracttal 29 contra 59 da lista" in txt
    assert "marca d'água" in linhas["Janela lida inteira"]
    assert "@" not in txt and "Pessoa" not in txt                # só contagens: nunca quem


# ── rodada 1 de correções da 3.3: a lista central só aparece para quem o Fracttal mostra tudo ──────────────────────────
# Rulings BP e BQ. A sonda da revisão liberou a pessoa de visão restrita por um período estreito (invertido, um dia quieto,
# um dia em que todas as OS são dela, o Investigar fora dos 30 dias) e mostrou a ela, com a folga de 2 OS, uma OS que o
# Fracttal esconde dela ("Criado por" outra pessoa num dia). Os casos da sonda viraram os testes abaixo.
def _liberou(c, email, wid=1) -> bool:
    """A pessoa ficou liberada, ou ganhou a 1ª pintura do card de uma OS (a OS 1 é da Usina Alfa, que a restrita não vê)."""
    return LC.liberado(email) or c.get("/os/api/os/%d/previa" % wid).status_code == 200


def test_periodo_invertido_nao_libera(fr):
    _encher()
    r = _cliente(RESTRITA)
    de, ate = HOJE - dt.timedelta(days=2), HOJE - dt.timedelta(days=5)          # o "de" depois do "até"
    assert r.get("/os/historico?modo=cos&de=%s&ate=%s" % (de, ate)).status_code == 200
    assert not _liberou(r, RESTRITA) and fr.n("total", RESTRITA) == 0     # o período inválido vai ao caminho de hoje, sem conferir
    with sessao.contexto(JWT, RESTRITA):
        assert api._wo_id_por_folio("10001") is None             # o Fracttal decide: ela não vê a OS 1
    assert fr.n("folio", RESTRITA) == 1


def test_dia_quieto_nao_libera(fr):
    _encher()
    r = _cliente(RESTRITA)
    d = HOJE - dt.timedelta(days=25)                             # nenhuma OS: 0 contra 0
    _hist(r, "modo=cos&de=%s&ate=%s" % (d, d))
    assert not _liberou(r, RESTRITA)


def test_dia_com_todas_as_os_dela_nao_libera(fr):
    # um dia só com OS da Usina Beta (a 2 e a 4, criadas há 25 dias, antes de todas as outras)
    for o in fr.universo:
        if o["id"] in (2, 4):
            o["criada"] = _iso(25.5 + (4 - o["id"]) / 100000.0)
    _encher([_rest(o) for o in fr.universo])
    dias = defaultdict(list)
    for o in fr.universo:
        dias[o["criada"][:10]].append(o)
    d = fr.universo[1]["criada"][:10]
    assert len(dias[d]) == 2 and all(o["beta"] for o in dias[d])
    r = _cliente(RESTRITA)
    h = _hist(r, "modo=cos&de=%s&ate=%s" % (d, d))
    # o que ela vê no dia é o que a lista tem (as OS da Usina Beta): a lista pode mostrar; liberar o resto, não
    assert all(">%s</a>" % o["folio"] in h for o in dias[d]) and "OS central" in h
    assert not _liberou(r, RESTRITA)


def test_investigar_fora_dos_30_dias_nao_libera(fr):
    _encher()
    r = _cliente(RESTRITA)
    de, ate = HOJE - dt.timedelta(days=60), HOJE - dt.timedelta(days=40)
    assert r.get("/os/historico/ativo?codigo=CAF-UBE200-INVR1.1&usina=" + BETA.replace(" ", "%20")
                 + "&nome=Inversor%201.1&de=" + str(de) + "&ate=" + str(ate)).status_code == 200
    assert not _liberou(r, RESTRITA)


def test_so_os_30_dias_padrao_liberam(fr):
    """Só a conferência dos 30 dias padrão até hoje libera (Ruling BP), mesmo para quem vê tudo e com muitas OS no período:
    outro período, não. Desde a rodada 2 a conferência é do período, sem visão, status nem etiqueta: a tela com um status nos
    30 dias padrão libera, porque a conferência é a mesma."""
    _encher()
    a = _cliente(TODA)
    assert _central(_hist(a, "modo=cos&de=%s&ate=%s" % (HOJE - dt.timedelta(days=25), HOJE)), 1)   # 60 OS, e bate
    assert not LC.liberado(TODA)
    assert _central(_hist(a, "modo=criadas&pessoa=TODOS&status=Em+Processo"), 1)                     # os 30 dias padrão
    assert LC.liberado(TODA)


def test_escopo_com_menos_de_20_os_nao_libera(fr):
    # 10 OS nos 30 dias padrão e as outras 50 mais velhas (a medida dos campos precisa de uma leitura de 50 OS)
    fr.universo = ([o for o in fr.universo if o["id"] <= 10]
                   + [dict(o, criada=_iso(40 + o["id"] % 30 + o["id"] / 1000.0)) for o in fr.universo if o["id"] > 10])
    _encher([_rest(o) for o in fr.universo])
    a = _cliente(TODA)
    assert _central(_hist(a, "modo=cos"), 1)                     # a lista vale para ela (a conferência bateu: 10 e 10)
    assert not _liberou(a, TODA, wid=2)                                # mas 10 OS não bastam para dizer que ela vê tudo


def test_previa_e_numero_de_os_antiga_vao_ao_vivo_mesmo_liberada(fr):
    _encher()
    antiga = dict(POR_ID[1], id=70, folio="10070", criada=_iso(45), descricao="")
    fr.universo.append(antiga)
    OC.receber([_rest(antiga)], OC.NOVAS)
    a = _cliente(TODA)
    _hist(a, "modo=cos")
    assert LC.liberado(TODA) and a.get("/os/api/os/7/previa").status_code == 200
    # a OS criada antes dos 30 dias conferidos: fora do escopo que liberou, o Fracttal decide
    assert a.get("/os/api/os/70/previa").status_code == 204
    with sessao.contexto(JWT, TODA), LC.liberacao(True):
        assert api._wo_id_por_folio("10070") == 70 and api._wo_id_por_folio("10007") == 7
    assert fr.n("folio", TODA) == 1                              # só a antiga foi ao Fracttal


def test_criado_por_outra_pessoa_nao_mostra_a_os_escondida(fr):
    """A sonda C: "Criado por" a Pessoa Um num dia em que ela criou só a OS 1 (Usina Alfa). A restrita não a vê no Fracttal
    (0), a lista tem 1: a folga de 2 OS a mostrava. A lista nunca tem mais que o Fracttal dá à pessoa."""
    _encher()
    d1 = POR_ID[1]["criada"][:10]
    assert OC.contar("criadas", {"id_account": 4001, "codigo": "PF01", "nome": "Pessoa Fictícia Um"}, d1, d1) >= 1
    r = _cliente(RESTRITA)
    h = _hist(r, "modo=criadas&pessoa=4001&de=%s&ate=%s" % (d1, d1))
    assert "OS central 1</td>" not in h and "OS ao vivo 1</td>" not in h and ">10001</a>" not in h
    assert fr.n("lista", RESTRITA) == 1                          # ao vivo, pela sessão dela


def test_visao_por_pessoa_com_uma_os_a_menos_vai_ao_vivo(fr):
    _encher([_rest(o) for o in UNIVERSO if o["id"] != 7])        # a lista ainda não tem a OS 7 dela
    a = _cliente(TODA)
    h = _hist(a, "modo=criadas")                                 # as criadas por mim: 10 no Fracttal, 9 na lista
    assert _ao_vivo(h, 7) and "OS central" not in h and fr.n("lista", TODA) == 1


def test_atualizar_com_uma_os_a_menos_vai_ao_vivo(fr):
    """A lista sem uma OS de antes da marca d'água (a OS 7) vai ao vivo, com ou sem o ↻: a regra é a igualdade exata em toda
    tela (até a rodada 1, a "Todos" sem o ↻ aceitava 2 OS a menos)."""
    _encher([_rest(o) for o in UNIVERSO if o["id"] != 7])
    a = _cliente(TODA)
    h = _hist(a, "modo=cos")
    assert _ao_vivo(h, 7) and "OS central" not in h and fr.n("lista", TODA) == 1
    h = _hist(a, "modo=cos&atualizar=1")                         # o ↻: a medida de novo, e ao vivo de novo
    assert _ao_vivo(h, 7) and "OS central" not in h and fr.n("total", TODA) == 2


def test_todos_com_o_fracttal_dando_uma_a_mais_passa(fr):
    _encher([_rest(o) for o in UNIVERSO if o["id"] != 60])       # a nova que a faixa ainda não trouxe
    a = _cliente(TODA)
    h = _hist(a, "modo=cos")
    assert _central(h, 1) and not _central(h, 60) and fr.n("lista") == 0


def test_todos_com_a_lista_tendo_uma_a_mais_vai_ao_vivo(fr):
    _encher()
    fr.visao[TODA] = {o["id"] for o in UNIVERSO if o["id"] != 7}   # o Fracttal não mostra a OS 7 a ela
    a = _cliente(TODA)
    h = _hist(a, "modo=cos")
    assert "OS central" not in h and ">10007</a>" not in h and fr.n("lista", TODA) == 1
    assert not LC.liberado(TODA)


def test_campos_mostrados_vem_da_medida(fr):
    """A descrição, o ativo, a equipe, o atribuído e o status também são medidos (Important 1): sem a descrição, o Histórico vai
    ao vivo; sem a equipe e o atribuído, a Visão COS e o Garantias vão, e o Histórico Geral segue da lista."""
    _encher([dict(_rest(o), description=None) for o in UNIVERSO])
    assert OC.campos_medidos()["pct"]["descrição"] == 0
    a = _cliente(TODA)
    assert _ao_vivo(_hist(a, "modo=criadas&pessoa=TODOS"), 1) and fr.n("lista") == 1
    OC.reiniciar()
    HS.limpar()
    _encher([dict(_rest(o), personnel_description=None, user_assigned=None) for o in UNIVERSO])
    pct = OC.campos_medidos()["pct"]
    assert pct["equipe"] == 0 and pct["atribuído a"] == 0 and pct["status"] == 100 and pct["ativo"] == 100
    b = _cliente(OUTRA)
    assert _ao_vivo(_hist(b, "modo=cos"), 1)
    assert _central(_hist(b, "modo=criadas&pessoa=TODOS"), 1)
    n = fr.n("chamados")
    b.get("/os/chamados/acompanhamento")
    assert fr.n("chamados") == n + 1


def _nota_retroativa(linhas_de_historico: int) -> str:
    """A nota de uma OS 3 retroativa com o histórico importado: uma linha por dia, a última de ontem (o "parado há N dias" sai
    dela, do FIM da nota)."""
    abertura = (HOJE - dt.timedelta(days=linhas_de_historico + 10)).strftime("%d/%m/%Y")
    corpo = [aw.MARCA_NOTA + " — Marca Inventada · Inversor",
             "OS de abertura: 10001 · OS de campo: 10002 · Ativo: CAF-UAL100-INVR1.1",
             "Data da ocorrência / abertura do chamado: %s" % abertura, "Histórico (importado da planilha):"]
    for k in range(linhas_de_historico):
        dia = HOJE - dt.timedelta(days=linhas_de_historico - k)
        corpo.append("%s - Conversa com o fornecedor inventado sobre a troca do equipamento, o envio da peça e o prazo "
                     "combinado com a equipe de campo, registro %03d de um texto longo de propósito." % (
                         dia.strftime("%d/%m/%Y"), k))
    return "\n".join(corpo)


def _cartao(h, folio) -> str:
    m = re.search(r'class="card([^"]*)" href="/os/chamados/acompanhamento/%s"' % folio, h)
    assert m, "o cartão da OS %s não está no quadro" % folio
    return m.group(1)


def test_nota_longa_do_chamado_nao_mostra_parado_errado(fr):
    """O "parado há N dias" do Garantias sai das linhas do histórico, no FIM da nota (Important 2, Ruling BR). A nota de ~10 mil
    caracteres passava do teto de 4.000 e era cortada sem marca: o quadro via a última atualização de um mês atrás e pulsava."""
    longa = _nota_retroativa(50)
    assert 4000 < len(longa) < OC.NOTA_MAX
    fr.universo[50] = dict(fr.universo[50], nota=longa)          # a OS 51, de acompanhamento, aberta e sem ticket
    _encher([_rest(o) for o in fr.universo])
    assert not OC.atual().por_id[51].nota_cortada
    a = _cliente(TODA)
    h = a.get("/os/chamados/acompanhamento").get_data(as_text=True)
    assert fr.n("chamados") == 0 and "parada" not in _cartao(h, "10051")
    # a que passa do teto fica marcada, e o quadro vai ao vivo (não mostra a nota pela metade como inteira)
    maior = _nota_retroativa(120)
    assert len(maior) > OC.NOTA_MAX
    fr.universo[51] = dict(fr.universo[51], nota=maior)
    OC.reiniciar()
    _encher([_rest(o) for o in fr.universo])
    assert OC.atual().por_id[52].nota_cortada
    h = a.get("/os/chamados/acompanhamento?atualizar=1").get_data(as_text=True)
    assert fr.n("chamados") == 1 and "parada" not in _cartao(h, "10052")


def test_criadas_alem_das_tres_ficam_para_a_faixa(fr, ao_vivo):
    """As OS criadas além das 3 primeiras não são lidas por trás (Minor 1): a faixa das novas (até 3 min) as traz."""
    os_, lidas = ao_vivo
    _encher()
    novas = [dict(POR_ID[1], id=80 + k, folio=str(10080 + k), criada=_iso(RECENTE), descricao="") for k in range(5)]
    for o in novas:
        os_[o["id"]] = o
    with sessao.contexto(JWT, TODA):
        n = LC.criadas([{"ok": True, "os": {"id_work_order": o["id"]}} for o in novas])
    assert n == 3 and sorted(lidas) == [80, 81, 82]
    assert not [t for t in threading.enumerate() if t.name == "os-web-lista-central"]
    time.sleep(0.3)
    assert sorted(lidas) == [80, 81, 82] and 83 not in OC.atual().por_id


def test_a_releitura_da_acao_tem_prazo(fr, ao_vivo, monkeypatch):
    """A releitura da OS depois da ação tem prazo (Minor 2): passou dele, a resposta sai, a OS fica pendente para a faixa, e a
    leitura que termina depois ainda a põe na lista."""
    os_, lidas = ao_vivo
    _encher()
    a = _cliente(TODA)
    _hist(a, "modo=cos")
    monkeypatch.setattr(LC, "RELEITURA_MAX_S", 0.2)
    solta = threading.Event()
    lenta = api._leitura_da_os

    def demora(metodo, wid, params, usar_guardada=True):
        solta.wait(2)
        return lenta(metodo, wid, params, usar_guardada)
    monkeypatch.setattr(api, "_leitura_da_os", demora)
    monkeypatch.setattr(api, "cancel_os", lambda wid, idm, note="": None)
    os_[2]["status"] = 4
    t0 = time.monotonic()
    r = a.post("/os/api/os/2/cancelar", json={"id_status_custom": 9, "folio": "10002"})
    assert r.get_json()["ok"] and time.monotonic() - t0 < 1.5
    assert 2 in OC.estado()["pendentes_ids"]
    solta.set()
    assert LC.esperar_releituras(5)
    assert OC.atual().por_id[2].status_id == 4 and 2 not in OC.estado()["pendentes_ids"]


def test_quem_diverge_fica_ao_vivo_30_min_sem_reconferir(fr):
    """A pessoa que diverge não é conferida de novo a cada visita (Minor 3): o resultado fica guardado 30 min, e o Raio-X a
    conta uma vez por janela."""
    _encher()
    r = _cliente(RESTRITA)
    for _ in range(3):
        _hist(r, "modo=cos")
        fr.relogio["t"] += 120
    assert fr.n("total", RESTRITA) == 1 and OC.estado()["conferencias"]["histórico"]["divergiram"] == 1
    fr.relogio["t"] += HS.CONFERE_S
    _hist(r, "modo=cos")
    assert fr.n("total", RESTRITA) == 2


def test_a_visao_so_e_refeita_quando_a_versao_muda(fr, monkeypatch):
    """As linhas da visão só são montadas de novo quando a VERSÃO da lista muda (Minor 5); a hora dela ("Lista das HH:MM")
    acompanha a última leitura."""
    montadas = []
    original = HS.html_das_linhas

    def contar(lista, chave, montar):
        return original(lista, chave, lambda: montadas.append(chave) or montar())
    monkeypatch.setattr(HS, "html_das_linhas", contar)
    _encher()
    a = _cliente(TODA)
    _hist(a, "modo=cos")
    depois = time.time() + 180
    OC.receber([], OC.NOVAS, lido_em=depois)                     # a leitura que não trouxe nada: a mesma versão
    h = _hist(a, "modo=cos")
    assert montadas == [("cos", "")]
    assert "Lista das %s" % datetime.fromtimestamp(depois, api._BR_TZ).strftime("%H:%M") in h


def test_finalizar_e_executar_sem_pedido_a_toa(fr, ao_vivo, monkeypatch):
    """O finalizar do Garantias usa o status da releitura que pôs a OS na lista (sem reler o cabeçalho), e o "fazer a tarefa"
    só relê a OS quando o registro de execução foi confirmado (Minor 6)."""
    os_, lidas = ao_vivo
    _encher()
    a = _cliente(TODA)
    _hist(a, "modo=cos")
    cabecalhos = []
    ler_cabecalho = api._cabecalho_os
    monkeypatch.setattr(api, "_cabecalho_os", lambda wid: cabecalhos.append(wid) or ler_cabecalho(wid))
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: {"folio": POR_ID[wid]["folio"], "subtarefas": [], "notas": ""})
    monkeypatch.setattr(api, "concluir_os_checado", lambda wid: {"ok": True, "data_fim": {}})
    monkeypatch.setattr(obs_store, "adicionar", lambda *a, **k: {})
    os_[51]["status"] = 2
    j = a.post("/os/api/acomp/10051/finalizar", json={"wid": 51}).get_json()
    assert j["ok"] and cabecalhos == [51] and OC.atual().por_id[51].status_id == 2
    monkeypatch.setattr(api, "subtarefas_da_tarefa", lambda tid: [])
    monkeypatch.setattr(api, "registrar_execucao", lambda *a, **k: {"ok": True, "confirmado": False})
    lidas.clear()
    corpo = {"valores": {}, "inicio": "2026-10-31T09:00"}
    assert a.post("/os/api/os/5/tarefa/9005/executar", json=corpo).get_json()["ok"]
    assert lidas == []                                           # sem o registro confirmado, nada a reler
    monkeypatch.setattr(api, "registrar_execucao", lambda *a, **k: {"ok": True, "confirmado": True,
                                                                   "inicio": "2026-10-31T12:00:00Z"})
    assert a.post("/os/api/os/5/tarefa/9005/executar", json=corpo).get_json()["ok"]
    assert lidas == [5]


# ── rodada 2 de correções da 3.3: a conferência do período até a marca d'água, e a lista de 19/10 sem herança ─────────────
# Ruling BU. A regra de uma mão comparava NÚMEROS, não conjuntos: a pessoa com H OS escondidas empatava quando o Fracttal dava
# a ela X ≥ H OS que a lista ainda não lera (as novas, que a faixa de 3 em 3 min ainda não trouxe; ou a mudança de status ou de
# etiqueta não lida, com o filtro da tela na conferência). A conferência agora é UMA por pessoa e período, sem visão, status
# nem etiqueta, e os dois lados contam só até a marca d'água da lista, com igualdade exata. E a lista "Todos" dividida de 19/10
# passava de uma pessoa restrita para outra. As sondas da re-revisão viraram os testes abaixo (os nomes são inventados).
R2 = "restrita.dois@exemplo.invalid"       # vê tudo menos algumas OS
R4 = "restrita.quatro@exemplo.invalid"     # só a Usina Alfa: 30 OS, o mesmo total da RESTRITA (a Usina Beta)
JWT_SEM_EMAIL = "aaa.eyJleHAiOjk5OTk5OTk5OTl9.sig"   # de mentira: o payload {"exp": 9999999999}, sem e-mail
CASOS_HX = [(1, 1), (2, 2), (2, 4), (1, 3)]           # (H OS escondidas dela, X OS novas que a lista não leu)


def _nova(i, **mudar) -> dict:
    """Uma OS que o Fracttal acabou de criar e a faixa das novas ainda não trouxe (só no Fracttal de mentira): depois da marca
    d'água da lista (a criação da OS 60), com o id maior que o de todas."""
    o = dict(POR_ID[2], id=i, folio=str(10000 + i), criada=_iso(RECENTE), descricao="")
    o.update(mudar)
    return o


def _mostra(h, ids) -> list:
    return sorted(i for i in ids if ">%d</a>" % (10000 + i) in h)


@pytest.mark.parametrize("escondidas,novas", CASOS_HX)
def test_todos_nao_e_enganada_pelas_novas(fr, escondidas, novas):
    """A "Todos" padrão, a que libera a prévia e o nº: R2 não vê as OS 1..H, e o Fracttal dá a ela X OS novas que a lista ainda
    não leu. Até a marca d'água ela tem 59 - H e a lista 59: ao vivo e ninguém liberado, também no ↻."""
    _encher()
    ocultas = set(range(1, escondidas + 1))
    fr.universo += [_nova(80 + k) for k in range(novas)]
    fr.visao[R2] = {o["id"] for o in fr.universo if o["id"] not in ocultas}
    c = _cliente(R2)
    h = _hist(c, "modo=cos")
    assert _mostra(h, ocultas) == [] and "OS central" not in h and fr.n("lista", R2) == 1
    assert not _liberou(c, R2)
    with sessao.contexto(JWT, R2):
        assert api._wo_id_por_folio("10001") is None             # o Fracttal decide: ela não vê a OS 1
    assert _mostra(_hist(c, "modo=cos&atualizar=1"), ocultas) == []


@pytest.mark.parametrize("escondidas,novas", CASOS_HX)
def test_criado_por_nao_e_enganado_pelas_novas(fr, escondidas, novas):
    """"Criado por" a Pessoa Quatro (a conta 4004) nos 30 dias: R2 não vê H OS dela, e a Quatro acabou de criar X OS, visíveis
    a R2, que a faixa ainda não trouxe. Pela visão, os totais empatavam com H = X."""
    _encher()
    ocultas = set(range(17, 17 + escondidas))
    fr.universo += [_nova(90 + k, acc=4004, cod="PF04", criador="Pessoa Fictícia Quatro") for k in range(novas)]
    fr.visao[R2] = {o["id"] for o in fr.universo if o["id"] not in ocultas}
    c = _cliente(R2)
    h = _hist(c, "modo=criadas&pessoa=4004")
    assert _mostra(h, ocultas) == [] and "OS central" not in h and fr.n("lista", R2) == 1
    assert not LC.liberado(R2)


@pytest.mark.parametrize("escondidas,novas", CASOS_HX)
def test_garantias_nao_e_enganado_pelas_novas(fr, escondidas, novas):
    """O quadro de Garantias (os 365 dias que ele lê): R2 não vê H OS de chamado, e o Fracttal tem X novas de chamado, visíveis
    a ela, que a faixa não trouxe. Nem na 1ª visita, nem no Atualizar."""
    _encher()
    ocultas = set(range(51, 51 + escondidas))
    fr.universo += [_nova(91 + k, labels=((11, "CHAMADOS"),), tipo="Administrativa", nota=NOTA_CHAMADO,
                          descricao="[Inversor 2.1] - Acompanhamento de chamado Marca Inventada") for k in range(novas)]
    fr.visao[R2] = {o["id"] for o in fr.universo if o["id"] not in ocultas}
    c = _cliente(R2)
    h = c.get("/os/chamados/acompanhamento").get_data(as_text=True)
    assert [i for i in ocultas if 'data-folio="%d"' % (10000 + i) in h] == [] and fr.n("chamados", R2) == 1
    h = c.get("/os/chamados/acompanhamento?atualizar=1").get_data(as_text=True)
    assert [i for i in ocultas if 'data-folio="%d"' % (10000 + i) in h] == []
    assert not LC.liberado(R2)


def test_status_e_etiqueta_nao_sao_enganados_pela_mudanca_nao_lida(fr):
    """Sem OS nova nenhuma (as sondas N e O): R2 não vê a OS 5 (concluída) nem a 7 (etiqueta ENGENHARIA); no Fracttal a OS 2,
    que ela vê, foi concluída, e a 4 ganhou a etiqueta, sem a faixa ter lido. Com o filtro da tela na conferência, os totais
    empatavam; a conferência é a "Todos" do período (a visibilidade no Fracttal não depende do status nem da etiqueta)."""
    _encher()
    for o in fr.universo:
        if o["id"] == 2:
            o["status"] = 3
        elif o["id"] == 4:
            o["labels"] = ((12, "ENGENHARIA"),)
    fr.visao[R2] = {o["id"] for o in fr.universo if o["id"] not in (5, 7)}
    c = _cliente(R2)
    for q in ("modo=cos&status=Conclu%C3%ADda", "modo=cos&etiqueta=12", "modo=cos&status=Conclu%C3%ADda&atualizar=1"):
        h = _hist(c, q)
        assert _mostra(h, (5, 7)) == [] and "OS central" not in h, q


def test_quem_ve_tudo_com_novas_depois_da_marca_passa(fr):
    """Quem vê tudo, com 4 OS novas que a lista ainda não leu: elas ficam depois da marca d'água, fora das duas contas, e a
    conferência passa (até a rodada 1, a folga de 2 OS a mandava ao vivo). As novas não aparecem: a lista não as tem."""
    _encher()
    fr.universo += [_nova(80 + k) for k in range(4)]
    a = _cliente(TODA)
    h = _hist(a, "modo=cos")
    assert _central(h, 1) and _central(h, 60) and _mostra(h, range(80, 84)) == []
    assert fr.n("lista") == 0 and fr.n("total") == 1 and LC.liberado(TODA)


def test_mais_os_depois_da_marca_do_que_a_pagina_vai_ao_vivo(fr, monkeypatch):
    """A página da conferência (`CONFERE_LINHAS`) inteira depois da marca d'água, e o Fracttal com mais: não dá para saber
    quantas OS dela são de antes da marca, e a tela vai ao vivo. As 55 novas estão na lista (as ações do OS Creator as
    puseram, sem a marca andar): pela conta, as duas empatavam. (A página de 50, para caber no universo pequeno: a de
    verdade é de 200 desde a rodada 4.)"""
    monkeypatch.setattr(LC, "CONFERE_LINHAS", 50)
    _encher()
    novas = [_nova(100 + k) for k in range(55)]
    fr.universo += novas
    for o in novas:
        OC.atualizar_os(o["id"], [_rest(o)])
    a = _cliente(TODA)
    h = _hist(a, "modo=cos")
    assert "OS central" not in h and fr.n("lista", TODA) == 1 and not LC.liberado(TODA)
    assert 154 in OC.atual().por_id and OC.atual().marca == POR_ID[60]["criada"]
    assert OC.estado()["conferencias"]["histórico"]["incertas"] == 1


def test_pagina_fora_da_ordem_da_criacao_vai_ao_vivo(fr):
    """O RPC ordena pelo id: a OS de id alto criada há 5 dias (a criação que não segue o id) põe a página fora da ordem da
    criação, e a conta das OS depois da marca d'água deixa de ser confiável: ao vivo."""
    _encher()
    torta = dict(POR_ID[2], id=150, folio="10150", criada=_iso(5.2), descricao="")
    fr.universo.append(torta)
    OC.receber([_rest(torta)], OC.NOVAS)                         # a lista também a tem: pela conta, as duas empatavam
    a = _cliente(TODA)
    h = _hist(a, "modo=cos")
    assert "OS central" not in h and fr.n("lista", TODA) == 1
    assert OC.estado()["conferencias"]["histórico"]["incertas"] == 1


def test_os_depois_da_marca_so_aparece_para_quem_a_pagina_trouxe(fr):
    """A OS que entrou na lista depois da marca d'água (a ação de outra pessoa, as abertas) não está nas contas: a lista só a
    mostra a quem a página da conferência a trouxe. R2 não vê a 61 (nova, já na lista pela ação) e vê a 62 (nova, que a
    lista não tem): pela conta da rodada 1, empatavam, e a 61 aparecia."""
    _encher()
    fr.universo += [_nova(61), _nova(62)]
    OC.atualizar_os(61, [_rest(fr.universo[-2])])              # a ação de outra pessoa a pôs na lista
    fr.visao[R2] = {o["id"] for o in fr.universo if o["id"] != 61}
    c = _cliente(R2)
    h = _hist(c, "modo=cos")
    assert _central(h, 60) and ">10061</a>" not in h
    assert _central(_hist(_cliente(TODA), "modo=cos"), 61)       # quem a vê, a vê: a página dela a trouxe


def test_o_liberado_so_serve_a_os_de_antes_da_marca(fr):
    """O nº → id e a 1ª pintura do card servem só a OS criada no escopo E antes da marca d'água (Ruling BU, item 4): a que
    entrou depois (a ação de outra pessoa a trouxe) vai ao vivo, e o Fracttal decide."""
    _encher()
    fr.universo.append(_nova(61))
    OC.atualizar_os(61, [_rest(fr.universo[-1])])              # a ação de outra pessoa a pôs na lista
    a = _cliente(TODA)
    assert _central(_hist(a, "modo=cos"), 61) and LC.liberado(TODA)
    assert a.get("/os/api/os/7/previa").status_code == 200 and a.get("/os/api/os/61/previa").status_code == 204
    with sessao.contexto(JWT, TODA), LC.liberacao(True):
        assert api._wo_id_por_folio("10007") == 7 and api._wo_id_por_folio("10061") == 61
    assert fr.n("folio", TODA) == 1                              # só a 61 foi ao Fracttal


def test_restritas_com_o_mesmo_total_nao_trocam_de_lista(fr):
    """A lista "Todos" dividida de 19/10 (Ruling BU, parte 2): quem vê tudo lê da lista central e não a ancora; a 1ª restrita
    que divergia achava a dividida vazia, e a lista DELA virava a de todos. A 2ª restrita, com o mesmo total e outro conjunto,
    herdava a lista da 1ª (a sonda P: as 30 OS da Usina Beta para quem só vê a Usina Alfa). Com a lista central cobrindo o
    período, quem não passa vai à chave DELA, e o Investigar ativo também."""
    _encher()
    fr.visao[R4] = {o["id"] for o in fr.universo if not o["beta"]}
    _hist(_cliente(TODA), "modo=cos")
    _hist(_cliente(RESTRITA), "modo=cos")
    c = _cliente(R4)
    h = _hist(c, "modo=cos")
    assert [o["id"] for o in UNIVERSO if o["beta"] and ">%s</a>" % o["folio"] in h] == []
    assert all(">%s</a>" % o["folio"] in h for o in UNIVERSO if not o["beta"])
    assert fr.n("lista", R4) == 1 and fr.n("lista", RESTRITA) == 1
    h = c.get("/os/historico/ativo?codigo=CAF-UBE200-INVR1.1&usina=" + BETA.replace(" ", "%20")
              + "&nome=Inversor%201.1").get_data(as_text=True)
    assert [o["id"] for o in UNIVERSO if o["beta"] and ">%s</a>" % o["folio"] in h] == []


def test_releitura_que_passou_do_prazo_sem_comecar_sai_da_fila(fr, ao_vivo, monkeypatch):
    """A fila da releitura (Minor 1 da rodada 2): com as 4 threads lendo devagar, as OS que passaram do prazo da tela sem a
    leitura ter começado saem da fila (`cancel`) e ficam pendentes para a faixa; as que já liam seguem por trás e entram."""
    _os, lidas = ao_vivo
    _encher()
    monkeypatch.setattr(LC, "RELEITURA_MAX_S", 0.2)
    solta = threading.Event()
    lenta = api._leitura_da_os

    def demora(metodo, wid, params, usar_guardada=True):
        solta.wait(3)
        return lenta(metodo, wid, params, usar_guardada)
    monkeypatch.setattr(api, "_leitura_da_os", demora)
    with sessao.contexto(JWT, TODA):
        assert LC._reler([1, 2, 3, 4, 5, 6]) == {}
    solta.set()
    assert LC.esperar_releituras(5)
    assert sorted(lidas) == [1, 2, 3, 4] and sorted(OC.estado()["pendentes_ids"]) == [5, 6]


def test_lista_com_menos_que_a_pessoa_nao_prende_30_min(fr):
    """O `_DIVERGIU` só quando a LISTA tem mais que a pessoa, o sinal da visão restrita (Minor 2 da rodada 2): a lista atrasada
    (sem a OS 7) manda ao vivo, mas a visita seguinte confere de novo; e quando a noite traz a OS, a lista mudou, e a medida
    dela é pedida de novo (desde a rodada 4 a medida guarda a conta da lista de quando foi pedida, a sonda S2): passa."""
    _encher([_rest(o) for o in UNIVERSO if o["id"] != 7])
    a = _cliente(TODA)
    assert _ao_vivo(_hist(a, "modo=criadas"), 7) and fr.n("total", TODA) == 1
    fr.relogio["t"] += 120
    assert _ao_vivo(_hist(a, "modo=criadas"), 7) and fr.n("total", TODA) == 2
    _encher()                                                    # a noite traz a OS 7
    fr.relogio["t"] += 120
    assert _central(_hist(a, "modo=criadas"), 7) and fr.n("total", TODA) == 3


def test_executar_sem_confirmacao_fica_pendente(fr, ao_vivo, monkeypatch):
    """O "fazer a tarefa" sem o registro confirmado (Minor 3 da rodada 2): sem reler a OS (2 pedidos à toa), ela fica "a
    conferir" e pendente para a faixa, que a lê pelo nº."""
    _os, lidas = ao_vivo
    _encher()
    a = _cliente(TODA)
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: {"folio": POR_ID[wid]["folio"], "subtarefas": [], "notas": ""})
    monkeypatch.setattr(api, "subtarefas_da_tarefa", lambda tid: [])
    monkeypatch.setattr(api, "registrar_execucao", lambda *a, **k: {"ok": True, "confirmado": False})
    corpo = {"valores": {}, "inicio": "2026-10-31T09:00"}
    assert a.post("/os/api/os/5/tarefa/9005/executar", json=corpo).get_json()["ok"]
    assert lidas == [] and 5 in OC.estado()["pendentes_ids"] and 5 in OC.atual().a_conferir


def test_data_do_evento_e_a_previa_so_com_os_campos_medidos(fr):
    """Os campos ainda sem medida (Minor 4 da rodada 2): a "Data do Evento" do Histórico Geral e do Investigar cai na
    programada, e sem ela na leitura grande a tela vai ao vivo; a prévia do card mostra a data fim, com quem está, quem criou
    e o tipo da tarefa, e sem um deles o card abre como sempre."""
    _encher([dict(_rest(o), date_maintenance=None) for o in UNIVERSO])
    assert OC.campos_medidos()["pct"]["programada"] == 0
    assert _ao_vivo(_hist(_cliente(TODA), "modo=criadas&pessoa=TODOS"), 1)
    OC.reiniciar()
    HS.limpar()
    LC.limpar()
    _encher([dict(_rest(o), personnel_description=None, user_assigned=None) for o in UNIVERSO])
    assert OC.campos_medidos()["pct"]["atribuído a"] == 0
    b = _cliente(OUTRA)
    assert _central(_hist(b, "modo=criadas&pessoa=TODOS"), 7) and LC.liberado(OUTRA)
    assert b.get("/os/api/os/7/previa").status_code == 204


def test_sessao_sem_email_nunca_passa(fr):
    """A sessão que não diz quem é (`quem() == "?"`: sem o e-mail da conta nem o do JWT) nunca passa na conferência (Minor 6 da
    rodada 2): a medida dela ficaria guardada sob "?", a mesma de toda sessão sem e-mail."""
    _encher()
    c = criar_app(segredo="teste", testing=False).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT_SEM_EMAIL
        s["conta"] = {"nome": "Pessoa Sem E-mail", "email": "", "perfil": "ADMINISTRATOR"}
    h = _hist(c, "modo=cos")
    assert "OS central" not in h and fr.n("total") == 0 and not LC.liberado("?")


def test_a_marca_dagua_da_lista(fr, tmp_path, monkeypatch):
    """A marca d'água (Ruling BU): a criação mais nova que uma leitura até o topo trouxe. Os 7 dias e a noite, sempre; as novas,
    só emendadas com o que a lista já leu (as regras do fim da janela); as abertas e a ação não a mexem; a criação depois do
    começo da leitura (o dado no futuro) não conta; ela nunca anda para trás; e volta com a cópia em disco."""
    monkeypatch.setattr(OC.os_disco, "GRAVAR_A_CADA_S", 0)      # a cópia em disco sem a espera de 30 s entre as escritas
    OC.reiniciar(pasta=str(tmp_path))
    _encher()
    assert OC.atual().marca == POR_ID[60]["criada"]
    abertas = [_rest(o) for o in fr.universo if o["status"] == 1]
    OC.receber(abertas + [_rest(_nova(61))], OC.ABERTAS)                         # as abertas
    OC.receber([_rest(_nova(62))], OC.NOVAS)                                     # as novas sem emendar
    OC.atualizar_os(63, [_rest(_nova(63))])                                      # a ação
    assert {61, 62, 63} <= set(OC.atual().por_id) and OC.atual().marca == POR_ID[60]["criada"]
    emendada = _nova(64, criada=_iso(0.2))
    OC.receber([_rest(emendada), _rest(POR_ID[60])], OC.NOVAS, desde=POR_ID[60]["criada"])
    assert OC.atual().marca == emendada["criada"]
    futura = _nova(65, criada=(datetime.now(_UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"))
    sete = [_rest(o) for o in fr.universo if o["criada"] >= _iso(7)] + [_rest(_nova(i)) for i in (61, 62, 63)]
    OC.receber(sete + [_rest(emendada), _rest(futura)], OC.SETE_DIAS, desde=_iso(7))
    assert 65 in OC.atual().por_id and OC.atual().marca == emendada["criada"]
    OC.receber([_rest(o) for o in fr.universo], OC.NOITE, desde=_iso(400)[:10])  # a noite sem a 64 (apagada): não volta
    assert 64 not in OC.atual().por_id and OC.atual().marca == emendada["criada"]
    assert OC.esperar_gravacao(10)
    OC.reiniciar(pasta=str(tmp_path))
    assert OC.atual().marca == emendada["criada"] and OC.estado()["marca"] == emendada["criada"]


def test_as_22h_de_brasilia_a_tela_le_da_lista(fr, monkeypatch):
    """O relógio congelado às 22:00 de Brasília, quando a data UTC já é a de amanhã. A janela da lista começava pela data UTC
    menos 365 dias, e o `de` do Garantias (a data local menos 365 dias) caía um dia antes dela: das 21:00 à meia-noite o quadro
    ia ao vivo sem precisar, e os testes falhavam nessa hora (três, às 21:19). A janela começa pela data local, a das telas; o
    dia de cada período segue o do caminho ao vivo (o Fracttal toma a data como o dia UTC dela, `api.list_minhas_os_pagina`)."""
    agora = datetime(2026, 10, 30, 22, 0, tzinfo=timezone(timedelta(hours=-3))).timestamp()
    hoje = datetime.fromtimestamp(agora).date()                 # a data local (a do servidor, em Brasília: 30/10)
    monkeypatch.setattr(time, "time", lambda: agora)

    class _Data(dt.date):
        @classmethod
        def today(cls):
            return hoje
    relogio = types.SimpleNamespace(**{k: getattr(dt, k) for k in dir(dt) if not k.startswith("_")})
    relogio.date = _Data
    for modulo in (rotas, rotas_acomp, LC):                       # o "hoje" das telas
        monkeypatch.setattr(modulo, "dt", relogio)

    def iso(dias):
        return datetime.fromtimestamp(agora - dias * 86400, _UTC).strftime("%Y-%m-%dT%H:%M:%S")
    fr.universo = [dict(o, criada=iso(1 + (60 - o["id"]) / 3.0)) for o in UNIVERSO]
    OC.receber([_rest(o) for o in fr.universo], OC.NOITE, desde=iso(400)[:10])
    assert OC.atual().janela[0] <= (hoje - dt.timedelta(days=365)).isoformat()
    a = _cliente(TODA)
    h = _hist(a, "modo=cos")
    assert _central(h, 1) and _central(h, 60) and fr.n("lista") == 0
    h = a.get("/os/chamados/acompanhamento").get_data(as_text=True)
    assert all('data-folio="%d"' % (10000 + i) in h for i in range(51, 56)) and fr.n("chamados") == 0


def test_os_antiga_que_a_lista_nao_tem_nao_compensa(fr):
    """A OS que entrou no Fracttal DEPOIS da leitura com a criação de ANTES da marca d'água (a criação que o App offline ou a
    importação trazem): a lista não a tem, e a pessoa a vê. Com a escondida dela (a 59) e a da marca escondida também (a 60),
    a página fica na ordem e as contas empatam (59 e 59). A página da conferência traz o que a pessoa vê de antes da marca:
    a OS que a lista não tem diz que a conta não prova nada, e a tela vai ao vivo."""
    _encher()
    atrasada = dict(POR_ID[2], id=70, folio="10070", descricao="",
                    criada=_iso(1 + (60 - 58.5) / 3.0))                # entre a 58 e a 59, inserida depois de tudo
    fr.universo.append(atrasada)
    fr.visao[R2] = {o["id"] for o in fr.universo if o["id"] not in (59, 60)}
    c = _cliente(R2)
    h = _hist(c, "modo=cos")
    assert ">10059</a>" not in h and "OS central" not in h and fr.n("lista", R2) == 1
    assert not LC.liberado(R2)


# ── rodada 3 da 3.3: a medida dos campos só pelas leituras do período inteiro ───────────────────────────────────────────────
def test_a_entrega_das_abertas_nao_mexe_na_medida_dos_campos(fr):
    """A medida dos campos é só das leituras que trazem a população inteira do período, os 7 dias e a noite (rodada 3 da 3.3).
    A entrega das abertas, de hora em hora e com 50 OS ou mais, media de novo, e a "data fim" ia a 0% (OS aberta não tem data
    fim): o Histórico, o Investigar, o Garantias e a 1ª pintura iam ao vivo até a próxima leitura dos 7 dias ou das
    finalizadas. As finalizadas (só as concluídas) e as novas também não mexem nela."""
    _encher()
    medida = OC.campos_medidos()
    fr.universo += [_nova(80 + k) for k in range(5)]
    abertas = [_rest(o) for o in fr.universo if o["status"] == 1]
    assert len(abertas) >= OC.CAMPOS_MIN_OS
    OC.receber(abertas, OC.ABERTAS)                              # as abertas, com as 5 novas
    OC.receber([_rest(o) for o in fr.universo], OC.FINALIZADAS, desde=_iso(30))
    assert OC.campos_medidos() == medida
    a = _cliente(TODA)
    h = _hist(a, "modo=cos")
    assert _central(h, 1) and _central(h, 80) and fr.n("lista") == 0
    assert _central(_hist(a, "modo=criadas&pessoa=TODOS"), 1) and fr.n("lista") == 0
    assert a.get("/os/api/os/7/previa").status_code == 200
    h = a.get("/os/chamados/acompanhamento").get_data(as_text=True)
    assert 'data-folio="10051"' in h and fr.n("chamados") == 0
    # os 7 dias, sim: a população inteira do período (a sondagem que a tela confere)
    sete = [dict(_rest(o), trigger_description=None) for o in fr.universo if o["criada"] >= _iso(7)]
    assert len(sete) < OC.CAMPOS_MIN_OS                           # a leitura pequena não mede (o mínimo de 50 OS)
    OC.receber(sete, OC.SETE_DIAS, desde=_iso(7))
    assert OC.campos_medidos() == medida
    OC.receber([dict(_rest(o), trigger_description=None) for o in fr.universo], OC.NOITE, desde=_iso(400)[:10])
    assert OC.campos_medidos()["faixa"] == OC.NOITE and OC.campos_medidos()["pct"]["gatilho"] == 0


# ── rodada 4 da 3.3: a lista central só para quem foi liberado (Ruling BX) ─────────────────────────────────────────────────
# Provar o conjunto por contagem teve buracos raros a cada volta (as sondas das rodadas 2 e 3 acharam vetores novos). A lista
# central passa a valer só para quem o Levi liberou: os administradores do Nexus, sempre, e os setores de
# `ponte.SETORES_COM_LISTA_CENTRAL` (mudados por commit), pela marca que a ponte põe no pedido; sem a marca, fechado. A
# contagem fica como 2ª barreira, sem os buracos achados: a OS antiga além da página (a página de 200), a criação fora da ordem
# do id (o menor id da página), a medida e o liberado que não viam a lista mudar, a lista vencida que devolvia a "Todos"
# dividida, e a cópia TODOS do Garantias com o total da lista. As sondas da re-revisão viraram os testes abaixo (os nomes são
# inventados).
RQ = "restrita.q@exemplo.invalid"          # vê tudo menos UMA OS
RV = "restrita.v@exemplo.invalid"          # não vê 4 das 5 OS de chamado da lista


def _escalado() -> list:
    """O universo de sempre com os ids vezes 10 (a criação segue o id: a 60 é a 600): sobra lugar para um id entre dois."""
    return [dict(o, id=o["id"] * 10) for o in UNIVERSO]


def test_quem_nao_foi_liberado_nunca_le_da_lista(fr, monkeypatch):
    """A pessoa que o Nexus não liberou (a marca do pedido falsa) vê tudo e passaria na contagem, mas nenhuma tela lê da lista:
    o Histórico e as visões, o Garantias, o Investigar, a marcação verde dos Ativos, a 1ª pintura e o nº → id. Nem a
    conferência vai ao Fracttal."""
    _encher()
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: {})
    a = _cliente(TODA, liberada=False)
    h = _hist(a, "modo=cos")
    assert _ao_vivo(h, 1) and "OS central" not in h and fr.n("lista") == 1
    assert _ao_vivo(_hist(a, "modo=criadas"), 1)
    a.get("/os/chamados/acompanhamento")
    assert fr.n("chamados") == 1
    h = a.get("/os/historico/ativo?codigo=CAF-UAL100-INVR1.1&usina=" + ALFA.replace(" ", "%20")
              + "&nome=Inversor%201.1").get_data(as_text=True)
    assert "OS central" not in h and ">10001</a>" in h
    a.get("/os/api/ativos/recentes?dias=30")
    assert fr.n("recentes") == 1
    assert a.get("/os/api/os/7/previa").status_code == 204
    a.get("/os/os/folio/10007")
    assert fr.n("folio") == 1                                    # o nº → id ao vivo, pela sessão dela
    assert fr.n("total") == 0 and not LC.liberado(TODA)


def test_sem_a_marca_no_pedido_a_lista_fica_fechada(fr):
    """O OS Creator servido sozinho, o PC, a ponte que não disse: sem a marca no pedido, ninguém está liberado."""
    _encher()
    a = _cliente(TODA, liberada=None)
    h = _hist(a, "modo=cos")
    assert _ao_vivo(h, 1) and "OS central" not in h and fr.n("total") == 0
    assert a.get("/os/api/os/7/previa").status_code == 204


@pytest.fixture
def setor_de_mentira(app, monkeypatch):
    """O setor da pessoa do login sem ir ao banco: `valor` é o que o cadastro devolveria (ou a exceção da leitura)."""
    from nexus.auth import setor_telas
    app.config["NEXUS_PESSOA_HMAC"] = "chave-de-teste"
    monkeypatch.setattr(setor_telas, "_banco", lambda: (None, None))
    caixa = {"valor": None, "lidos": []}

    def da_pessoa(cfg, email, base, sessao_banco):
        caixa["lidos"].append(email)
        if isinstance(caixa["valor"], Exception):
            raise caixa["valor"]
        return caixa["valor"]
    monkeypatch.setattr(setor_telas, "setor_da_pessoa", da_pessoa)
    return caixa


def test_a_ponte_libera_o_administrador_e_os_setores_da_lista(app, setor_de_mentira, monkeypatch):
    """Quem a ponte libera (`ponte.lista_central`): o administrador do Nexus, sempre, sem ler o setor; quem é de um setor de
    `SETORES_COM_LISTA_CENTRAL` (pelo nome, sem acento nem caixa), que nasce vazia. O resto, o sem setor, o setor que não deu
    para ler e o Nexus sem a NEXUS_PESSOA_HMAC: não."""
    from flask import session

    from nexus.torres.oscreator import ponte as P
    with app.test_request_context("/os/historico"):
        session["logado"], session["admin"] = True, True
        assert P.lista_central() is True and setor_de_mentira["lidos"] == []
        session["admin"] = False
        session["usuario"] = {"email": "Pessoa.Teste@exemplo.test", "nome": "Pessoa Teste", "perfil": ""}
        setor_de_mentira["valor"] = {"id": 3, "nome": "COS"}
        assert P.lista_central() is False                        # a lista de setores nasce vazia
        monkeypatch.setattr(P, "SETORES_COM_LISTA_CENTRAL", frozenset({"cos"}))
        for nome in ("COS", "cos", " Cós "):
            setor_de_mentira["valor"] = {"id": 3, "nome": nome}
            assert P.lista_central() is True, nome
        assert setor_de_mentira["lidos"][-1] == "pessoa.teste@exemplo.test"
        setor_de_mentira["valor"] = {"id": 2, "nome": "Performance"}
        assert P.lista_central() is False
        setor_de_mentira["valor"] = None
        assert P.lista_central() is False
        setor_de_mentira["valor"] = RuntimeError("setores ilegíveis no banco")
        assert P.lista_central() is False
        app.config["NEXUS_PESSOA_HMAC"] = ""
        setor_de_mentira["valor"] = {"id": 3, "nome": "COS"}
        assert P.lista_central() is False


def _pela_ponte(app, email, admin=False):
    """Um login do Nexus e o cookie do OS Creator com o JWT de mentira: o pedido passa pela ponte. O administrador é o da senha
    de administrador (a sessão sem pessoa: o administrador por e-mail o Nexus confere na lista dele a cada pedido); os outros,
    o login pelo Fracttal."""
    from nexus.torres.oscreator import ponte as P
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"], s["admin"] = True, admin
        if not admin:
            s["usuario"] = {"email": email, "nome": "Pessoa Teste", "perfil": ""}
    alvo = P.clone(app)
    valor = alvo.session_interface.get_signing_serializer(alvo).dumps(
        {"jwt": JWT, "conta": {"nome": "Pessoa Teste", "email": email, "perfil": "ADMINISTRATOR"}})
    c.set_cookie("os_sessao", valor, path="/os")
    return c


def test_pela_ponte_so_o_administrador_e_o_setor_liberado_leem_da_lista(app, fr, setor_de_mentira, monkeypatch):
    """De ponta a ponta no Nexus: o setor não liberado vai ao vivo (e nem confere), o setor liberado e o administrador leem da
    lista."""
    from nexus.torres.oscreator import ponte as P
    _encher()
    monkeypatch.setattr(P, "SETORES_COM_LISTA_CENTRAL", frozenset({"cos"}))
    setor_de_mentira["valor"] = {"id": 2, "nome": "Performance"}
    h = _pela_ponte(app, TODA).get("/os/historico?modo=cos").get_data(as_text=True)
    assert _ao_vivo(h, 1) and "OS central" not in h and fr.n("total") == 0
    setor_de_mentira["valor"] = {"id": 3, "nome": "COS"}
    h = _pela_ponte(app, OUTRA).get("/os/historico?modo=cos").get_data(as_text=True)
    assert _central(h, 1) and fr.n("lista", OUTRA) == 0
    monkeypatch.setattr(P, "SETORES_COM_LISTA_CENTRAL", frozenset())
    h = _pela_ponte(app, TODA, admin=True).get("/os/historico?modo=cos").get_data(as_text=True)
    assert _central(h, 1)


def test_os_antiga_alem_da_pagina_nao_compensa_no_historico(fr):
    """A sonda Q1: a OS X, criada há 25 dias (fora dos 7 dias: a noite seguinte a traria), entrou no Fracttal DEPOIS da
    leitura, com o id entre os de outras duas (o App offline, uma importação); RQ a vê e não vê a OS 1. Com a página de 50 pelo
    id, a X ficava fora dela e as contas empatavam (59 e 59): a OS 1 aparecia. A página é de 200 (`CONFERE_LINHAS`), o mesmo
    pedido."""
    uni = _escalado()
    fr.universo = uni
    _encher([_rest(o) for o in uni])
    fr.universo.append(dict(UNIVERSO[1], id=105, folio="10099", criada=_iso(25.0), descricao=""))
    fr.visao[RQ] = {o["id"] for o in fr.universo if o["id"] != 10}
    c = _cliente(RQ)
    h = _hist(c, "modo=cos")
    assert ">10001</a>" not in h and "OS central" not in h and not LC.liberado(RQ)
    assert c.get("/os/api/os/10/previa").status_code == 204


def test_os_antiga_alem_da_pagina_nao_compensa_no_garantias(fr):
    """A sonda Q2: o mesmo no quadro de Garantias (os 365 dias); RQ não vê a OS 51 (de chamado)."""
    uni = _escalado()
    fr.universo = uni
    _encher([_rest(o) for o in uni])
    fr.universo.append(dict(UNIVERSO[1], id=95, folio="10099", criada=_iso(25.0), descricao=""))
    fr.visao[RQ] = {o["id"] for o in fr.universo if o["id"] != 510}
    h = _cliente(RQ).get("/os/chamados/acompanhamento").get_data(as_text=True)
    assert 'data-folio="10051"' not in h and fr.n("chamados", RQ) == 1


def test_os_de_id_baixo_com_a_criacao_depois_da_marca(fr, monkeypatch):
    """A sonda R1, a premissa ao contrário: a F (id 95, entre a 9 e a 10) tem a criação daqui a 2 h (o relógio do celular
    adiantado, no App offline). A lista a tem (a noite a leu), mas a marca não anda por ela (a data no futuro). O total de RQ a
    conta, e a página, pelo id, não a traz: as de antes da marca dela ficavam 1 a mais, e a escondida (a 51) aparecia. A medida
    guarda o menor id da página: com uma OS do período na lista depois da marca e de id abaixo dele, não dá para saber. (A
    página de 50, para caber no universo pequeno.)"""
    monkeypatch.setattr(LC, "CONFERE_LINHAS", 50)
    f = dict(UNIVERSO[1], id=95, folio="10099", descricao="",
             criada=(datetime.now(_UTC) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"))
    fr.universo = _escalado() + [f]
    _encher([_rest(o) for o in fr.universo])
    assert OC.atual().marca == POR_ID[60]["criada"] and 95 in OC.atual().por_id
    fr.visao[RQ] = {o["id"] for o in fr.universo if o["id"] != 510}
    h = _cliente(RQ).get("/os/chamados/acompanhamento").get_data(as_text=True)
    assert 'data-folio="10051"' not in h and fr.n("chamados", RQ) == 1


def test_a_medida_guardada_nao_vale_com_a_lista_mudada(fr, monkeypatch):
    """A sonda S2: RQ não vê a OS 1 e diverge (59 na lista, 58 dela antes da marca). Dentro dos 30 min, a OS 4 (que RQ via, fora
    da página dela) é apagada no Fracttal e a noite a tira da lista: 58 e 58. A medida guardada de RQ, de antes do apagamento,
    "batia", e a OS 1 aparecia. A medida guarda a conta da lista de quando foi pedida: com a lista mudada, ela não prova nada.
    (A página de 50, para a OS 4 ficar fora dela.)"""
    monkeypatch.setattr(LC, "CONFERE_LINHAS", 50)
    _encher()
    fr.visao[RQ] = {o["id"] for o in fr.universo if o["id"] != 1}
    c = _cliente(RQ)
    assert "OS central" not in _hist(c, "modo=cos")
    fr.universo = [o for o in fr.universo if o["id"] != 4]
    _encher([_rest(o) for o in fr.universo])                     # a noite tira a 4
    assert 4 not in OC.atual().por_id
    fr.relogio["t"] += 60
    h = _hist(c, "modo=cos")
    assert ">10001</a>" not in h and "OS central" not in h


def test_o_liberado_nao_vale_com_a_lista_mudada_no_escopo(fr, monkeypatch):
    """A sonda U1: RQ vê tudo menos a Y, criada há 3 dias e inserida agora (o App offline), que a lista ainda não tem. RQ passa
    (a lista não tem a Y) e fica liberada. Os 7 dias trazem a Y: a 1ª pintura e o nº → id da Y saíam da lista. O liberado
    guarda a conta do escopo antes da marca e só serve com a mesma; e o Histórico confere de novo."""
    _encher()
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: {})
    fr.universo.append(dict(UNIVERSO[0], id=70, folio="10070", criada=_iso(3.0), descricao=""))
    fr.visao[RQ] = {o["id"] for o in fr.universo if o["id"] != 70}
    c = _cliente(RQ)
    assert _central(_hist(c, "modo=cos"), 1) and LC.liberado(RQ)
    OC.receber([_rest(o) for o in fr.universo if o["criada"] >= _iso(7)], OC.SETE_DIAS, desde=_iso(7))
    assert 70 in OC.atual().por_id
    assert c.get("/os/api/os/70/previa").status_code == 204
    c.get("/os/os/folio/10070")
    assert fr.n("folio", RQ) == 1                                # o nº → id foi ao vivo: o Fracttal decide
    assert ">10070</a>" not in _hist(c, "modo=cos")


def _vencer(monkeypatch):
    """A lista central vence: o fim da janela (o começo da última leitura até o topo) 4 h atrás, e o FRESCA_S é de 30 min."""
    import dataclasses
    la = OC.atual()
    monkeypatch.setattr(OC, "_ATUAL", dataclasses.replace(la, janela=(la.janela[0], _iso(4 / 24.0))))


def test_a_lista_vencida_nao_devolve_a_todos_dividida(fr, monkeypatch):
    """A sonda T3: TODA lê da lista (não ancora a "Todos" dividida de 19/10); a restrita abre e diverge (a lista dela). A lista
    vence (a última leitura até o topo passou dos 30 min) e o período deixa de ser coberto: a restrita abria de novo, achava a
    dividida vazia, e a lista dela virava a de todos; R4 (só a Usina Alfa, o mesmo total) a herdava. Com a lista em uso, mesmo
    vencida, a dividida é só de quem tem uma medida aprovada recente."""
    _encher()
    fr.visao[R4] = {o["id"] for o in fr.universo if not o["beta"]}
    _hist(_cliente(TODA), "modo=cos")
    r = _cliente(RESTRITA)
    _hist(r, "modo=cos")
    _vencer(monkeypatch)
    assert not LC.cobre(HOJE - dt.timedelta(days=30), HOJE)
    _hist(r, "modo=cos")
    h = _hist(_cliente(R4), "modo=cos")
    assert [o["id"] for o in UNIVERSO if o["beta"] and ">%s</a>" % o["folio"] in h] == []
    assert fr.n("lista", R4) == 1


def test_a_copia_todos_do_garantias_guarda_o_total_do_fracttal(fr):
    """A sonda V1: TODA monta a cópia "TODOS" do quadro pela lista central, com 2 OS de chamado novas no Fracttal que a faixa
    ainda não trouxe. O total guardado era o da lista (5); a restrita RV não vê 4 das 5 da lista e vê as 2 novas (3): |3 - 5|
    = 2, e o `_dono` (a folga de 19/10) a punha na cópia TODOS, com as 4 que o Fracttal esconde dela. A cópia guarda o total do
    Fracttal de quem a montou (7: o `total_chamados` dela, na chave do `_dono`), como antes da 3.3: |3 - 7| = 4, a dela."""
    _encher()
    fr.universo += [dict(POR_ID[52], id=91 + k, folio=str(10091 + k), criada=_iso(RECENTE)) for k in range(2)]
    fr.visao[RV] = {o["id"] for o in fr.universo if o["id"] not in (51, 52, 53, 54)}
    h = _cliente(TODA).get("/os/chamados/acompanhamento").get_data(as_text=True)
    assert 'data-folio="10051"' in h and fr.n("chamados", TODA) == 0
    h = _cliente(RV).get("/os/chamados/acompanhamento").get_data(as_text=True)
    assert [i for i in (51, 52, 53, 54) if 'data-folio="%d"' % (10000 + i) in h] == []


def test_o_numero_que_nao_abre_nao_mostra_o_id(fr, monkeypatch):
    """O /os/os/folio/<nº> resolve o id pela lista (a pessoa liberada) e abre o detalhe ao vivo; o detalhe que não vem (o
    Fracttal não mostra a OS a ela) dizia "Não achei a OS de id X", e o id de uma OS que ela talvez não veja saía na tela.
    Agora diz o nº, que foi o que ela digitou."""
    _encher()
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: {})
    a = _cliente(TODA)
    _hist(a, "modo=cos")                                         # liberada: o nº → id pela lista
    r = a.get("/os/os/folio/10007")
    corpo = r.get_data(as_text=True)
    assert r.status_code == 404 and "10007" in corpo and "de id 7" not in corpo and fr.n("folio") == 0
