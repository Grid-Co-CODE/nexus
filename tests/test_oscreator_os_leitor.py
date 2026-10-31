"""O leitor em faixas da lista central de OS (31/10/2026, tarefa 3.2 do canto central do OS Creator; desenho
`docs/superpowers/specs/2026-10-30-oscreator-canto-central-design.md`, "Etapa 3").

O histórico de OS lido pelo próprio servidor, pela credencial da empresa, fora do pico e em faixas (o módulo é
`os_creator/os_leitor.py`; a paginação é UMA, a do `nexus/campo/tarefas_os.py`, que lê as abertas de hora em hora para o
fato `fato_tarefa_os`). O que estes testes seguram, contando cada ida ao Fracttal:
- as novas param na primeira página inteira de OS conhecidas (1 pedido sem novidade, 2 com), sem ler o total;
- os 7 dias são relidos inteiros, até uma página inteira mais velha que o piso;
- as abertas vêm do `tarefas_os` sem pedido a mais; sem entrega em 70 min, o leitor as lê ele mesmo, pela mesma função,
  no máximo uma vez por hora;
- as finalizadas param no piso (a data de fim mais nova menos 2 dias), e a lista vazia espera a carga da noite;
- a leitura que falha no meio não chama o `receber`: a lista fica como estava;
- os horários das faixas, fora dos minutos ocupados (uma lista só, que os ativos também usam);
- o `tarefas_os` segue igual: o mesmo fato e os mesmos pedidos de antes;
- cada faixa conta no contador do Fracttal com o nome dela; só o servidor liga o leitor.
Fracttal, banco e disco são dublês: nada vai à rede. Nomes e textos são inventados (repositório público)."""
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pytest
import requests

from nexus.campo import fracttal
from nexus.campo import tarefas_os as P
from nexus.casca import fracttal_conta as C
from nexus.casca import minutos_ocupados as MO
from nexus.dados import fato_tarefa_os as F
from nexus.torres.oscreator import ponte
from sessao_real_sem_rede import sessao_real
from test_campo_tarefas_os import AGORA, _Fracttal, _tres, _w, banco, rapido  # noqa: F401 — o banco de mentira

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import ativos_leitor as AL  # noqa: E402
import os_central as OC  # noqa: E402
import os_leitor as OL  # noqa: E402

AQUI = Path(__file__).resolve().parent.parent
_UTC = timezone.utc
_BRT = timezone(timedelta(hours=-3))


def _iso(dias_atras: float = 0.0) -> str:
    return (datetime.now(_UTC) - timedelta(days=dias_atras)).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _linha(os_id, *, tarefa=None, status=1, criada=None, fim=None, folio=None):
    """Uma linha do REST `work_orders` (uma tarefa), com nomes inventados."""
    return {"id_work_orders_tasks": tarefa or os_id * 10, "id_work_order": os_id, "wo_folio": str(folio or 20000 + os_id),
            "id_status_work_order": str(status), "description": "Tarefa inventada %d" % os_id,
            "items_log_description": "Inversor 1.1 Marca X  { CAL-GAM100-INVR1.1 }", "code": "CAL-GAM100-INVR1.1",
            "tasks_log_task_type_main": "Corretiva", "creation_date": criada or _iso(1), "date_maintenance": None,
            "final_date": fim, "wo_final_date": fim, "created_by": "Pessoa Fictícia Um", "code_create_by": "PF01",
            "user_assigned": "Pessoa Fictícia Dois", "personnel_description": "Pessoa Fictícia Dois", "id_personnel": 502,
            "labels": []}


class RestOS:
    """O REST `work_orders` de mentira: filtra pelo status, pelo tipo e pelo nº, ordena pelo campo do `sort` (o desempate é a
    tarefa), pagina pelo `start`/`limit`, dá o `total` do filtro e conta cada pedido. `falha_no`: o n-ésimo pedido vem com
    `success: false`; `recusa_no`: o n-ésimo levanta a recusa do Fracttal (406/429), sempre; `erro_no`: a conexão cai."""

    def __init__(self, linhas, falha_no=None, recusa_no=None, erro_no=None):
        self.linhas, self.pedidos = list(linhas), []
        self.falha_no, self.recusa_no, self.erro_no = falha_no, recusa_no, erro_no

    def __call__(self, path):
        self.pedidos.append(path)
        n = len(self.pedidos)
        if self.recusa_no is not None and n >= self.recusa_no:
            raise fracttal.Recusado("o Fracttal recusou por excesso de pedidos (HTTP 429)")
        if self.erro_no is not None and n == self.erro_no:
            raise requests.ConnectionError("a conexão caiu")
        if self.falha_no is not None and n == self.falha_no:
            return {"success": False, "message": "erro do servidor", "data": []}
        q = parse_qs(urlparse("http://x/api/" + path).query)
        rows = self.linhas
        if "id_status_work_order" in q:
            rows = [w for w in rows if str(w["id_status_work_order"]) == q["id_status_work_order"][0]]
        if "tasks_log_task_type_main" in q:
            rows = [w for w in rows if w["tasks_log_task_type_main"] == unquote(q["tasks_log_task_type_main"][0])]
        if "wo_folio" in q:
            rows = [w for w in rows if str(w["wo_folio"]) == q["wo_folio"][0]]
        if "sort" in q:
            campo, sentido = q["sort"][0].split(":")
            rows = sorted(rows, key=lambda w: (str(w.get(campo) or ""), w["id_work_orders_tasks"]),
                          reverse=sentido == "desc")
        limite, inicio = int(q["limit"][0]), int(q.get("start", ["0"])[0])
        pagina = rows[inicio:inicio + limite]
        return {"success": True, "message": "", "total": len(rows), "data": pagina or None}

    def paginas(self):
        return [p for p in self.pedidos if "limit=1&" not in p + "&"]

    def totais(self):
        return [p for p in self.pedidos if "limit=1&" in p + "&"]


@pytest.fixture(autouse=True)
def limpo(monkeypatch):
    """Cada teste começa sem lista e sem leitor; o ritmo (1 s entre páginas) e a espera da recusa não são dormidos; o
    gancho das abertas do `tarefas_os` volta ao que era."""
    OC.reiniciar()
    OL.reiniciar()
    monkeypatch.setattr(P, "PAUSA_S", 0)
    monkeypatch.setattr(P, "ESPERA_RECUSA_S", 0)
    monkeypatch.setattr(P, "_ENTREGA", {"abertas": None})
    yield
    OC.esperar_gravacao(5)
    OC.reiniciar()
    OL.reiniciar()


def _lista_de(linhas, dias=90):
    """A lista central cheia por uma noite de `dias` (o que a faixa da noite deixaria)."""
    OC.receber(linhas, OC.NOITE, desde=(datetime.now(_UTC) - timedelta(days=dias)).strftime("%Y-%m-%d"))
    return OC.atual()


def _base(n=250, dias=30):
    """n OS de uma tarefa, criadas ao longo de `dias` (a mais nova há ~1 h)."""
    return [_linha(1000 + k, criada=_iso(0.05 + dias * k / n)) for k in range(n)]


# ── as novas ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_novas_param_na_pagina_conhecida():
    base = _base()
    antes = _lista_de(base)
    novas = [_linha(5000 + k, criada=_iso(0.001)) for k in range(3)]
    rest = RestOS(base + novas)
    rel = OL.ler_novas(ler=rest)
    assert rel["erro"] == "" and len(rest.pedidos) == 2 and rest.totais() == []           # a 2ª página, toda conhecida, encerra
    assert all("sort=creation_date:desc" in p for p in rest.pedidos)
    lista = OC.atual()
    assert {5000, 5001, 5002} <= set(lista.por_id) and lista.janela[1] >= antes.janela[1]    # o fim da janela andou
    assert OC.entrega(OC.NOVAS)["entraram"] == 3 and rel["pedidos"] == 2
    rest = RestOS(base + novas)                                                               # sem novidade: 1 pedido
    rel = OL.ler_novas(ler=rest)
    assert len(rest.pedidos) == 1 and rel["erro"] == ""
    # mais novas do que a leitura curta lê (o teto de páginas): nada entra, ficam para os 7 dias
    muitas = [_linha(6000 + k, criada=_iso(0.0005)) for k in range(OL.PAGINAS_NOVAS_MAX * 100)]
    versao = OC.atual().versao
    rel = OL.ler_novas(ler=RestOS(base + novas + muitas))
    assert rel["erro"] and OC.atual().versao == versao and 6000 not in OC.atual().por_id
    # a lista sem uma leitura até o topo (a máquina sem cópia): as novas esperam, sem pedido nenhum
    OC.reiniciar()
    rest = RestOS(base + novas)
    rel = OL.ler_novas(ler=rest)
    assert rest.pedidos == [] and "espera" in rel["resultado"]


# ── os 7 dias ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_sete_dias_inteiros():
    base = [_linha(1000 + k, criada=_iso(0.05 + k / 30)) for k in range(600)]                # 30 por dia, 20 dias
    _lista_de(base)
    tres, cinco, quinze = 1000 + 90, 1000 + 150, 1000 + 450                                  # criadas há 3, 5 e 15 dias
    rest = RestOS([dict(w, id_status_work_order="2") if w["id_work_order"] == tres else w
                   for w in base if w["id_work_order"] not in (cinco, quinze)])
    rel = OL.ler_sete_dias(ler=rest)
    assert rel["erro"] == ""
    # 1 total e as páginas até a 1ª INTEIRA mais velha que o piso: 210 OS em 7 dias = 3 páginas com alguma dentro, e a 4ª
    assert len(rest.totais()) == 1 and len(rest.paginas()) == 4
    lista = OC.atual()
    assert lista.por_id[tres].status_id == 2                                                  # a que mudou, em dia
    assert cinco in lista.a_conferir                                                          # a que sumiu, "a conferir"
    assert quinze in lista.por_id and quinze not in lista.a_conferir                          # fora dos 7 dias: intacta
    assert lista.janela[0] == (datetime.now(_UTC) - timedelta(days=90)).strftime("%Y-%m-%d")  # emendou com a da noite


# ── as abertas ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def _liga(app):
    app.config["NEXUS_PCM_FRACTTAL_TESTE"] = {"FRACTTAL_CLIENT_ID": "id-de-mentira", "FRACTTAL_CLIENT_SECRET": "s"}
    OL.ligar(app)


def test_abertas_vem_do_tarefas_os_sem_pedido_a_mais(app, banco):
    _liga(app)
    ler = _tres()
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=ler, agora=AGORA)
    assert rel["gravado"] == {F.ABA: 3, "qualidade": 1} and rel["paginas"] == 6 and len(ler.pedidos) == 6
    e = OC.entrega(OC.ABERTAS)
    assert e["quem"] == "tarefas_os" and e["os"] == 2                                         # status 1 e 2; a zeladoria não
    assert set(OC.atual().por_id) == {50100, 50200} and OC.atual().por_id[50200].status_id == 2
    assert not OL.precisa_das_abertas()
    # 70 min sem entrega (o PC gravou nesta hora, e o tarefas_os do servidor pulou): o leitor lê pela MESMA função
    depois = time.time() + OL.SEM_ENTREGA_S + 60
    assert OL.precisa_das_abertas(depois)
    rest = RestOS([_w(1, 100, 1), _w(2, 200, 2), _w(4, 400, 1)])
    rel = OL.ler_abertas(ler=rest)
    assert rel["erro"] == "" and OC.entrega(OC.ABERTAS)["quem"] == "os_leitor" and 50400 in OC.atual().por_id
    assert len(rest.totais()) == 2 and len(rest.paginas()) == 2                               # um total e uma página por status
    assert all("id_status_work_order=" in p for p in rest.pedidos)
    # no máximo uma vez por hora: logo depois da leitura dele, não precisa
    assert not OL.precisa_das_abertas(time.time() + 60)
    assert OL.precisa_das_abertas(time.time() + OL.SEM_ENTREGA_S + 60)


# ── as finalizadas ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_finalizadas_param_no_piso():
    # a lista: 150 OS concluídas há 10 a 40 dias e 50 abertas; a concluída mais nova terminou há 10 dias
    base = ([_linha(1000 + k, status=3, criada=_iso(40), fim=_iso(10 + k / 5)) for k in range(150)]
            + [_linha(3000 + k, status=1, criada=_iso(20)) for k in range(50)])
    _lista_de(base)
    assert OC.mais_nova_data_fim()[:10] == _iso(10)[:10]
    # no Fracttal, 20 das abertas foram concluídas há 1 a 5 dias (depois do piso, que é a mais nova menos 2 dias)
    agora = [dict(w, id_status_work_order="3", final_date=_iso(1 + (w["id_work_order"] % 20) / 5),
                  wo_final_date=_iso(1 + (w["id_work_order"] % 20) / 5)) if w["id_work_order"] < 3020 else w
             for w in base]
    rest = RestOS(agora)
    rel = OL.ler_finalizadas(ler=rest)
    assert rel["erro"] == "" and rest.totais() == []
    assert all("id_status_work_order=3" in p and "sort=final_date:desc" in p for p in rest.pedidos)
    # 20 novas + as de 10 a 12 dias (o piso) numa página, e a 2ª página toda mais velha que o piso encerra
    assert len(rest.pedidos) == 2
    lista = OC.atual()
    assert all(lista.por_id[3000 + k].status_id == 3 and lista.por_id[3000 + k].data_fim for k in range(20))
    assert lista.por_id[3020].status_id == 1
    # a lista vazia (antes da 1ª carga): a faixa espera a noite, sem pedido nenhum
    OC.reiniciar()
    rest = RestOS(agora)
    rel = OL.ler_finalizadas(ler=rest)
    assert rest.pedidos == [] and "espera" in rel["resultado"]


# ── a leitura que falha no meio não troca nada ──────────────────────────────────────────────────────────────────────────
def test_falha_no_meio_nao_troca(monkeypatch, app, banco):
    base = [_linha(1000 + k, criada=_iso(0.05 + k / 30)) for k in range(600)]
    base.append(_linha(9000, status=3, criada=_iso(5), fim=_iso(1)))            # uma concluída: as finalizadas têm piso
    _lista_de(base)
    novas = [_linha(5000 + k, criada=_iso(0.001)) for k in range(150)]
    chamadas = []
    real = OC.receber
    monkeypatch.setattr(OC, "receber", lambda *a, **k: chamadas.append(a[1]) or real(*a, **k))
    versao = OC.atual().versao
    casos = [
        (OL.ler_novas, RestOS(base + novas, falha_no=2)),                 # a 2ª página com `success: false`
        (OL.ler_sete_dias, RestOS(base, recusa_no=3)),                    # recusada (429) três vezes
        (OL.ler_sete_dias, RestOS(base, erro_no=2)),                      # a conexão caiu
        (OL.ler_noite, RestOS(base, falha_no=4)),
        (OL.ler_finalizadas, RestOS(base, erro_no=1)),
        (OL.ler_abertas, RestOS(base, falha_no=2)),
    ]
    for faixa, rest in casos:
        rel = faixa(ler=rest)
        assert rel["erro"], (faixa.__name__, rel)
        assert "nada mudou" in rel["resultado"]
    assert chamadas == [] and OC.atual().versao == versao
    assert OL.estado()["faixas"]["sete_dias"]["erro"]
    # a leitura das abertas que não veio inteira no `tarefas_os` também não entrega nada
    entregues = []
    P.ligar_entrega_das_abertas(lambda linhas, lido_em=None: entregues.append(linhas))
    with pytest.raises(P.LeituraIncompleta):
        P.ler_abertas(RestOS(base, falha_no=2))
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=_Fracttal({(1, ""): [_w(1, 100, 1)], (2, ""): [_w(2, 200, 2)]},
                                                         falha={(2, 0)}), agora=AGORA)
    assert "LeituraIncompleta" in rel["erro"] and entregues == []


# ── os horários ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _em(dia, h, m):
    return datetime(2026, 10, dia, h, m, tzinfo=_BRT).timestamp()       # 26/10/2026 foi uma segunda; 31/10, um sábado


def test_horarios_das_faixas():
    assert OL.proximo_passo(_em(27, 10, 1)) == (120, OL.NOVAS)                      # dia útil: de 3 em 3 min
    assert OL.proximo_passo(_em(27, 10, 3)) == (180, OL.NOVAS)
    assert OL.proximo_passo(_em(27, 9, 58)) == (120, OL.SETE_DIAS)                  # o :00 é livre: os 7 dias (vencem as novas)
    s, passo = OL.proximo_passo(_em(27, 10, 9))                                     # o :10 é das tarefas: os 7 dias andam
    assert passo == OL.NOVAS and s == 3 * 60                                        # ... e as novas do :12 vêm antes deles
    assert OL.proximo_passo(_em(27, 10, 19)) == (120, OL.SETE_DIAS)                 # o :21, o próximo minuto livre
    assert OL.proximo_passo(_em(27, 10, 43)) == (120, OL.FINALIZADAS)               # :45 (vencem as novas do mesmo minuto)
    assert OL.proximo_passo(_em(27, 10, 54)) == (60, OL.ABERTAS)                    # :55, a conferência das abertas
    assert OL.proximo_passo(_em(31, 10, 1)) == (14 * 60, OL.NOVAS)                  # sábado: de 15 em 15 min
    assert OL.proximo_passo(_em(27, 21, 1)) == (14 * 60, OL.NOVAS)                  # depois das 20h, também
    assert OL.proximo_passo(_em(27, 3, 16)) == (5 * 60, OL.NOITE)                   # 03:20 é das tarefas: 03:21, a noite
    assert OL.proximo_passo(_em(27, 3, 21))[1] != OL.NOITE
    # os minutos fixos fogem dos minutos ocupados (uma lista só), e as novas, de 1 ou 2 pedidos, podem cair em qualquer um
    for m in OL.SETE_DIAS_MINUTOS + (OL.FINALIZADAS_MINUTO, OL.ABERTAS_MINUTO):
        assert MO.livre(m), m
    assert OL.SETE_DIAS_MINUTOS == (0, 21, 30, 41, 51) and MO.proximo_livre(10) == 21 and MO.proximo_livre(30) == 30
    assert MO.livre(OL.NOITE_HORA[1]) and not MO.livre(8) and not MO.livre(38) and not MO.livre(15)
    # a lista é uma só: os ativos tiram os minutos dela, e o `tarefas_os` cabe na faixa que ela reserva
    assert AL.NOVOS_MINUTOS == MO.ATIVOS_NOVOS and AL.HORA_COMPLETO == MO.ATIVOS_COMPLETO
    assert all(not MO.livre(m) for m in range(P.MINUTO_DA_HORA, P.MINUTO_DA_HORA + P.DESENCONTRO_MAX_S // 60 + 1))
    # a noite: a janela inteira no domingo ou sem a janela lida inteira; senão, 90 dias
    assert OL.noite_inteira(_em(25, 3, 20)) and not OL.noite_inteira(_em(31, 3, 20), janela=("2025-11-01", "x"))
    assert OL.noite_inteira(_em(31, 3, 20), janela=(None, None))
    assert OL.noite_inteira(_em(31, 3, 20), janela=("2026-10-20", "x"))           # a janela menor que a de 365 dias


# ── o tarefas_os segue igual ────────────────────────────────────────────────────────────────────────────────────────────
def test_tarefas_os_segue_igual(app, banco):
    """Com o gancho ligado (o servidor), o `tarefas_os` grava o mesmo fato e faz os mesmos pedidos de antes."""
    sem = _tres()
    with app.app_context():
        rel_sem = P.publicar(app.config, banco, ler=sem, agora=AGORA, forcar=True)
    linhas_sem = banco.linhas(F.LIVRO, F.ABA)
    _liga(app)
    com = _tres()
    with app.app_context():
        rel_com = P.publicar(app.config, banco, ler=com, agora=AGORA, forcar=True)
    assert com.pedidos == sem.pedidos and rel_com == rel_sem
    assert banco.linhas(F.LIVRO, F.ABA) == linhas_sem
    assert OC.entrega(OC.ABERTAS)["quem"] == "tarefas_os"
    # e a leitura das abertas do fato é a mesma função que o leitor usa (nada de paginação duplicada)
    assert P.ler_fracttal.__code__.co_names.count("ler_abertas") == 1


# ── cada faixa conta no contador do Fracttal com o nome dela ────────────────────────────────────────────────────────────
def test_cada_faixa_e_contada_com_o_nome_dela(monkeypatch):
    monkeypatch.setattr(requests.sessions.Session, "send", requests.sessions.Session.send)
    C.limpar()
    C.ligar()
    _lista_de(_base(20))
    s, _ad = sessao_real(*[(200, None)] * 4)

    def ler(path):                                     # o REST pela requests.Session de verdade (o adaptador responde {})
        return s.get("https://app.fracttal.com/api/" + path).json()
    OL.ler_novas(ler=ler)
    linhas = [l for l in C.instantaneo() if l["origem"] == "fundo:nexus-os-leitor:novas"]
    assert len(linhas) == 1 and linhas[0]["metodo"] == "work_orders" and linhas[0]["pedidos_qtd"] == 1
    C.limpar()


# ── as pendentes, pelo nº ───────────────────────────────────────────────────────────────────────────────────────────────
def test_pendentes_lidas_pelo_numero():
    base = _base(20)
    _lista_de(base)
    alvo = base[3]["id_work_order"]
    assert not OC.atualizar_os(alvo)                                  # fora de um pedido: pendente e "a conferir"
    assert not OC.atualizar_os(99999)                                 # a que a lista não tem: o nº não se sabe
    rest = RestOS([dict(w, id_status_work_order="2") if w["id_work_order"] == alvo else w for w in base])
    rel = OL.ler_pendentes(ler=rest)
    assert rel["erro"] == "" and len(rest.pedidos) == 1 and "wo_folio=%d" % (20000 + alvo) in rest.pedidos[0]
    assert OC.atual().por_id[alvo].status_id == 2 and alvo not in OC.atual().a_conferir
    assert alvo not in OC.pendentes() and 99999 in OC.pendentes()


# ── só o servidor liga ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_sem_credencial_o_leitor_nao_liga(app):
    OL.ligar(app)
    e = OL.estado()
    assert e["ligado"] is False and "credencial" in e["motivo"] and OC.estado()["leitor"]["motivo"] == e["motivo"]
    assert P._ENTREGA["abertas"] is None


def test_com_credencial_liga_sem_laco_nos_testes(app):
    _liga(app)
    OL.ligar(app)                                                     # de novo: nada
    assert OL.estado()["ligado"] and P._ENTREGA["abertas"] is not None
    import threading
    assert not any(t.name == "nexus-os-leitor" for t in threading.enumerate())


def test_o_servidor_liga_o_leitor_e_o_pc_nao():
    import re
    liga = re.compile(r"(?<![\w])os_leitor\.ligar\(")                 # o `ativos_leitor.ligar(` não conta
    texto = (AQUI / "servir.py").read_text(encoding="utf-8")
    m = liga.search(texto)
    assert m and 'modulo_do_clone("os_leitor")' in texto
    assert texto.index("fracttal_conta.ligar()") < m.start()
    assert texto.index("instalar_campo(app)") < m.start()                      # depois do laço do tarefas_os
    for arquivo in ("app.py", "nexus/__init__.py", "nexus/torres/oscreator/ponte.py"):
        assert not liga.search((AQUI / arquivo).read_text(encoding="utf-8")), arquivo
