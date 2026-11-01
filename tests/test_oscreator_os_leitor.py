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
Rodada 1 da revisão (Rulings AU e AV): o REST que ignora o `sort` (em ordem crescente ou qualquer) não mexe na lista, e o
estado diz por quê; a leitura que encolheria a lista vira erro da faixa; cada página chega ao leitor cortada no que a lista lê;
as pendentes mortas saem da fila; a pausa vem antes de cada OS lida pelo nº; a data fim no futuro não trava as finalizadas;
o defeito do leitor vai ao log com a pilha; e os minutos das faixas moram na lista única, cruzados com os laços de verdade.
Fracttal, banco e disco são dublês: nada vai à rede. Nomes e textos são inventados (repositório público)."""
import logging
import random
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
import os_disco as OD  # noqa: E402
import os_leitor as OL  # noqa: E402
import os_registro as OR  # noqa: E402

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
    `success: false`; `recusa_no`: o n-ésimo levanta a recusa do Fracttal (406/429), sempre; `erro_no`: a conexão cai.
    `ordem` (Ruling AU): o REST que ignora o `sort` ("crescente": da mais velha para a mais nova; "embaralhada": numa ordem
    qualquer, a mesma a cada pedido). `falha_folio`: o nº cuja leitura pela OS (`wo_folio`) derruba a conexão, sempre.
    `corta_em` (rodada 2): o REST com um teto no `start`, que devolve as linhas só até a de índice `corta_em` e depois a
    página curta ou vazia com `success: true` (o Fracttal já devolveu 0 registros calado); o total segue o de verdade."""

    def __init__(self, linhas, falha_no=None, recusa_no=None, erro_no=None, ordem=None, falha_folio=None, corta_em=None):
        self.linhas, self.pedidos = list(linhas), []
        self.falha_no, self.recusa_no, self.erro_no = falha_no, recusa_no, erro_no
        self.ordem, self.falha_folio, self.corta_em = ordem, falha_folio, corta_em

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
            if self.falha_folio is not None and q["wo_folio"][0] == str(self.falha_folio):
                raise requests.ConnectionError("a conexão caiu")
            rows = [w for w in rows if str(w["wo_folio"]) == q["wo_folio"][0]]
        if "sort" in q:
            campo, sentido = q["sort"][0].split(":")
            if self.ordem == "embaralhada":
                rows = sorted(rows, key=lambda w: w["id_work_orders_tasks"])
                random.Random(7).shuffle(rows)
            else:
                rows = sorted(rows, key=lambda w: (str(w.get(campo) or ""), w["id_work_orders_tasks"]),
                              reverse=sentido == "desc" and self.ordem != "crescente")
        limite, inicio = int(q["limit"][0]), int(q.get("start", ["0"])[0])
        fim = inicio + limite if self.corta_em is None or limite == 1 else min(inicio + limite, self.corta_em)
        pagina = rows[inicio:max(inicio, fim)]
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
    # sem o total (Ruling AU: o total do `work_orders` sem filtro é o de todas as OS, e a leitura para no piso) e as páginas até
    # a 1ª INTEIRA mais velha que o piso: 210 OS em 7 dias = 3 páginas com alguma dentro, e a 4ª
    assert rest.totais() == [] and len(rest.paginas()) == 4
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
    assert OL.proximo_passo(_em(27, 10, 45)) == (60, OL.FINALIZADAS)                # :46 (o :45 é do uso_os às 04:45)
    assert OL.proximo_passo(_em(31, 10, 44)) == (60, OL.NOVAS)                      # sábado: as novas do :45 vêm antes
    assert OL.proximo_passo(_em(27, 10, 54)) == (60, OL.ABERTAS)                    # :55, a conferência das abertas
    assert OL.proximo_passo(_em(31, 10, 1)) == (14 * 60, OL.NOVAS)                  # sábado: de 15 em 15 min
    assert OL.proximo_passo(_em(27, 21, 1)) == (14 * 60, OL.NOVAS)                  # depois das 20h, também
    assert OL.proximo_passo(_em(27, 3, 16)) == (5 * 60, OL.NOITE)                   # 03:20 é das tarefas: 03:21, a noite
    assert OL.proximo_passo(_em(27, 3, 21))[1] != OL.NOITE
    # os minutos fixos são da lista de OS na lista única (Minor 1 da rodada 1: o laço novo que pedir um minuto não cai neles), e
    # as novas, de 1 ou 2 pedidos, podem cair em qualquer um
    for m in OL.SETE_DIAS_MINUTOS + (OL.FINALIZADAS_MINUTO, OL.ABERTAS_MINUTO):
        assert "lista central de OS" in MO.OCUPADOS[m], m
    assert OL.SETE_DIAS_MINUTOS == (0, 21, 30, 41, 51) and OL.NOITE_HORA == (3, 21)
    assert MO.proximo_livre(10) == 23 and MO.proximo_livre(30) == 31                 # o :21 e o :30 têm dono agora
    assert not MO.livre(8) and not MO.livre(38) and not MO.livre(15) and MO.livre(45)
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
    m = re.search(r'ligar_leitor_do_clone\(app, "os_leitor"\)', texto)       # o servir.py liga pelo try (`ponte.ligar_leitor_do_clone`)
    assert m and not liga.search(texto)
    assert texto.index("fracttal_conta.ligar()") < m.start()
    assert texto.index("instalar_campo(app)") < m.start()                      # depois do laço do tarefas_os
    for arquivo in ("app.py", "nexus/__init__.py", "nexus/torres/oscreator/ponte.py"):
        assert not liga.search((AQUI / arquivo).read_text(encoding="utf-8")), arquivo


# ── rodada 1 da revisão: o REST que ignora o `sort` (Ruling AU) ─────────────────────────────────────────────────────────────
def _base_com_lote():
    """600 OS: 100 concluídas criadas no mesmo minuto há 200 dias (um lote importado: fora dos 90 dias da noite e dentro da
    janela de 365) e 500 ao longo dos últimos 17 dias (a mais nova há ~1 h)."""
    lote = [_linha(1000 + k, status=3, criada=_iso(200 + k / 100000), fim=_iso(199)) for k in range(100)]
    return lote + [_linha(2000 + k, criada=_iso(0.05 + 17 * k / 500)) for k in range(500)]


def test_a_ordem_errada_nao_mexe_na_lista():
    """Com o `sort` ignorado, a leitura que para no piso ou na página conhecida não quer dizer nada: em ordem crescente a noite
    tiraria de vez as OS dos 90 dias, os 7 dias marcariam a semana inteira "a conferir" e as novas (a 1ª página toda conhecida,
    o lote velho) levariam o fim da janela até agora sem as OS novas. Nada muda, e o estado diz por quê."""
    base = _base_com_lote()
    _lista_de(base, dias=OC.JANELA_DIAS)
    antes = OC.atual()
    assert len(antes.por_id) == 600 and antes.a_conferir == frozenset()
    novas = [_linha(5000 + k, criada=_iso(0.001)) for k in range(3)]
    for faixa, nome in ((OL.ler_noite, "noite"), (OL.ler_sete_dias, "sete_dias"), (OL.ler_novas, "novas")):
        for ordem in ("crescente", "embaralhada"):
            kw = {"inteira": False} if faixa is OL.ler_noite else {}
            rel = faixa(ler=RestOS(base + novas, ordem=ordem), **kw)
            assert "pela criação" in rel["erro"] and "nada mudou" in rel["resultado"], (nome, ordem, rel)
            lista = OC.atual()
            assert (lista.versao, lista.janela, lista.a_conferir, set(lista.por_id)) == (
                antes.versao, antes.janela, antes.a_conferir, set(antes.por_id)), (nome, ordem)
            assert "pela criação" in OL.estado()["faixas"][nome]["erro"]


def test_poucas_linhas_fora_do_lugar_passam():
    """A ordem do REST pode ser só aproximada (o `sort` é da OS e a linha é da tarefa): duas linhas dias mais novas que as
    vizinhas não derrubam a leitura. A ordem qualquer derruba (o teste acima)."""
    base = [_linha(1000 + k, criada=_iso(0.05 + 20 * k / 600)) for k in range(600)]
    _lista_de(base)
    rest = RestOS(base)
    fora = {base[150]["id_work_orders_tasks"], base[420]["id_work_orders_tasks"]}

    def ler(path):
        r = rest(path)
        if r.get("data"):
            r = dict(r, data=[dict(w, creation_date=_iso(0.01)) if w["id_work_orders_tasks"] in fora else w
                              for w in r["data"]])
        return r
    rel = OL.ler_noite(ler=ler, inteira=False)
    assert rel["erro"] == "" and rel["os"] == 600


def test_a_leitura_que_encolheria_a_lista_vira_erro_da_faixa():
    """A trava de encolhimento (Ruling AU): o REST em ordem, mas sem 150 das 250 OS (páginas perdidas em silêncio). A lista
    recusa, nada muda, e a faixa diz por quê (não é defeito do leitor)."""
    base = _base(250, dias=30)
    _lista_de(base)
    versao = OC.atual().versao
    rel = OL.ler_noite(ler=RestOS(base[:100]), inteira=False)
    assert "encolher" in rel["erro"] and "nada mudou" in rel["resultado"] and not rel.get("defeito"), rel
    assert OC.atual().versao == versao and len(OC.atual().por_id) == 250
    assert OC.estado()["recusas"]["noite"]["motivo"] in rel["erro"]


# ── rodada 1 da revisão: a projeção por página (Ruling AV) ──────────────────────────────────────────────────────────────
# os campos que o REST `work_orders` traz além dos que a lista lê (os nomes, os vistos no código do Nexus; os valores,
# inventados): a linha da largura real
_DO_REST_A_MAIS = {
    "cal_date_maintenance": "2026-10-01T10:00:00+00:00", "code_wo_related": None, "completed_percentage": 100,
    "costs_center_description": "Centro de custo inventado", "dependencies": None, "duration": 3600,
    "execution_type": "INTERNAL", "group_task_description": "Grupo de tarefas inventado",
    "groups_1_description": "Cliente Alfa - Usina Inventada - SP", "groups_2_description": "Região inventada",
    "id_item": 880001, "id_parent_wo": None, "id_request": None, "id_status_work_order_task": 3, "id_task": 70001,
    "id_type_item": 12, "out_of_service_sec": 0, "parent_description": "// Cliente Alfa/ Usina Inventada/ Inversores/ ",
    "percentage_completed": 100, "priorities_description": "Média", "rating": 3, "real_duration": 3500,
    "related_items": None, "requested_by": "Pessoa Fictícia Três", "reschedule_causes": None, "review_date": None,
    "severiry_description": "Baixa", "stop_assets": False, "stop_assets_sec": 0, "task_status": "DONE",
    "tasks_duration": 3600, "tasks_log_types_2_description": "Subtipo inventado",
    "tasks_log_types_description": "Tipo inventado", "wo_folio_parent": None, "costs_materials": 0.0,
    "costs_services": 0.0, "costs_labor": 120.5, "costs_total": 120.5, "latitude": -23.55, "longitude": -46.63,
}


def _larga(os_id, *, nota=None, **kw):
    """Uma linha do REST na largura real: a de `_linha` mais os campos que a lista joga fora, a nota da tarefa e a etiqueta
    com cor e estado."""
    w = dict(_linha(os_id, **kw), **_DO_REST_A_MAIS)
    w.update(task_note=nota if nota is not None else "Observação inventada da tarefa %d: feito, sem pendência." % os_id,
             note=None, labels=[{"id": 11, "description": "ROTINA", "color": "8892a6", "enabled": True}],
             initial_date=w["creation_date"], event_date=w["creation_date"])
    return w


def test_a_projecao_corta_cada_pagina(monkeypatch):
    permitidos = set(OR.CAMPOS_REST)
    largas = [_larga(1000 + k, criada=_iso(0.05 + 20 * k / 250)) for k in range(250)]
    # 1) no `tarefas_os`: cada página é cortada ao chegar, antes do pedido da seguinte, e o que volta só tem o que a lista lê
    rest = RestOS(largas)
    eventos = []

    def ler(path):
        eventos.append("pedido")
        return rest(path)

    def corta(w):
        eventos.append("corta")
        return OR.enxuta(w)
    linhas = P.ler_criadas(ler, piso=_iso(30)[:19], topo_minimo=_iso(3)[:19], com_total=False, projetar=corta)
    assert [e for i, e in enumerate(eventos) if i == 0 or e != eventos[i - 1]] == ["pedido", "corta"] * 3
    assert len(linhas) == 250 and all(set(w) <= permitidos for w in linhas)
    # sem a projeção (o fato do `tarefas_os`), a linha inteira, como sempre
    assert all(set(w) == set(largas[0])
               for w in P.ler_criadas(RestOS(largas), piso=_iso(30)[:19], topo_minimo=_iso(3)[:19], com_total=False))
    # 2) no leitor: a noite, os 7 dias e as abertas chegam à lista cortados; a nota só fica com o bloco do chamado
    _lista_de(largas)
    recebidas = []
    real = OC.receber
    monkeypatch.setattr(OC, "receber", lambda linhas, *a, **k: recebidas.append(list(linhas)) or real(linhas, *a, **k))
    marcada = _larga(4000, criada=_iso(0.02), nota="Antes\n" + OR.MARCAS_DA_NOTA[1] + "\nMarca: Inventada")
    # 100 OS de 4 meses atrás: a noite de 90 dias chega ao piso, como em produção, e não pede o total (Ruling AU; rodada 2: a
    # que acaba antes do piso pede, `test_a_leitura_que_acaba_antes_do_piso_nao_passa_calada`)
    velhas = [_larga(8000 + k, criada=_iso(120 + k / 100)) for k in range(100)]
    rest = RestOS(largas + [marcada] + velhas)
    rel = OL.ler_noite(ler=rest, inteira=False)
    assert rel["erro"] == "" and rest.totais() == []
    (noite,) = recebidas
    assert len(noite) == 351 and all(set(w) <= permitidos for w in noite)
    por_id = {w["id_work_order"]: w for w in noite}
    assert OR.MARCAS_DA_NOTA[1] in por_id[4000]["task_note"] and OR.MARCAS_DA_NOTA[1] in OC.atual().por_id[4000].note
    assert "task_note" not in por_id[1000] and "costs_total" not in por_id[1000] and "groups_1_description" not in por_id[1000]
    assert por_id[1000]["labels"] == [{"id": 11, "description": "ROTINA"}]
    recebidas.clear()
    assert OL.ler_sete_dias(ler=RestOS(largas))["erro"] == ""
    OL.entregar_abertas([_larga(5000, criada=_iso(0.01))], time.time())               # o gancho do `tarefas_os`
    assert len(recebidas) == 2 and all(set(w) <= permitidos for linhas in recebidas for w in linhas)


# ── rodada 1 da revisão: as pendentes (Minors 5 e 6) ────────────────────────────────────────────────────────────────────
def test_pendentes_mortas_saem_da_fila(tmp_path, monkeypatch):
    """A OS que o nº não traz mais (apagada no Fracttal) sai da fila e do disco; a que derruba a leitura sai depois de
    `OC.PENDENTE_FALHAS_MAX` tentativas e nunca segura as outras (as de menos falhas vêm antes)."""
    monkeypatch.setattr(OD, "GRAVAR_A_CADA_S", 0)
    OC.reiniciar(pasta=str(tmp_path))
    base = _base(20)
    _lista_de(base)
    apagada, morta, viva = (base[k]["id_work_order"] for k in (2, 3, 4))
    for wid in (apagada, morta, viva):
        assert not OC.atualizar_os(wid)                                  # fora de um pedido: pendentes, nessa ordem
    rest = RestOS([dict(w, id_status_work_order="2") if w["id_work_order"] == viva else w
                   for w in base if w["id_work_order"] != apagada], falha_folio=20000 + morta)
    rel = OL.ler_pendentes(ler=rest)
    # 1ª volta: a apagada sai da fila (e fica "a conferir" até a noite); a morta derruba a leitura, e a volta para nela
    assert apagada not in OC.pendentes() and apagada in OC.atual().a_conferir
    assert morta in OC.pendentes() and viva in OC.pendentes() and "falhou" in rel["resultado"]
    # 2ª volta: a viva, sem falha, vem antes da morta (mais velha na fila)
    OL.ler_pendentes(ler=rest)
    assert viva not in OC.pendentes() and OC.atual().por_id[viva].status_id == 2
    for _ in range(OC.PENDENTE_FALHAS_MAX - 2):
        assert morta in OC.pendentes()
        OL.ler_pendentes(ler=rest)
    assert morta not in OC.pendentes() and morta in OC.atual().a_conferir           # a próxima faixa a traz
    assert OL.ler_pendentes(ler=rest) is None                                       # a fila andou
    # e saíram do disco: o processo que sobe de novo não as traz de volta
    assert OC.esperar_gravacao(5)
    OC.reiniciar(pasta=str(tmp_path))
    assert not set(OC.pendentes()) & {apagada, morta, viva}


def test_a_noite_que_falhou_deixa_rastro_depois_do_reinicio(tmp_path, monkeypatch):
    """Revisão final: o relatório do leitor vive na memória dele, e a `faixas` do `os_central` só guarda a entrega que deu certo. A
    noite que FALHOU (o REST que não veio inteiro) deixava a lista como estava e, depois de um deploy, nenhum rastro: o Levi não tem
    acesso ao servidor e confere a 1ª noite pelo Raio-X. Agora a última leitura de cada faixa, ok ou falha, vai ao cabeçalho da
    cópia em disco (`leituras`), e a noite seguinte que deu certo apaga a falha do disco também."""
    monkeypatch.setattr(OD, "GRAVAR_A_CADA_S", 0)
    OC.reiniciar(pasta=str(tmp_path))
    base = _base()
    _lista_de(base)
    rel = OL.ler_noite(ler=RestOS(base, falha_no=2))
    assert rel["erro"] and "nada mudou" in rel["resultado"]
    assert OC.esperar_gravacao(5)
    OC.reiniciar(pasta=str(tmp_path))                                    # o reinício (um deploy): o leitor perde a memória
    OL.reiniciar()
    assert OL.estado()["faixas"] == {}
    guardada = OC.estado()["leituras"]["noite"]
    assert guardada["erro"] == rel["erro"] and guardada["pedidos"] == rel["pedidos"] and guardada["inicio"] == rel["inicio"]
    assert "nada mudou" in guardada["resultado"] and guardada["defeito"] is False and set(guardada) == {
        "inicio", "fim", "pedidos", "os", "linhas", "resultado", "erro", "defeito"}                  # só contagens, horas e motivos
    # a noite seguinte, boa, vira a guardada (e sem erro)
    rel = OL.ler_noite(ler=RestOS(base))
    assert not rel["erro"]
    assert OC.esperar_gravacao(5)
    OC.reiniciar(pasta=str(tmp_path))
    OL.reiniciar()
    assert not OC.estado()["leituras"]["noite"]["erro"] and OC.estado()["leituras"]["noite"]["os"] == len(base)
    # a leitura de rotina que deu certo não pede regravar o arquivo inteiro (as novas, de 3 em 3 min): fica na memória
    OC.esperar_gravacao(5)
    gravado = OC.estado()["disco"]["gravado_em"]
    OL.ler_novas(ler=RestOS(base))
    assert OC.esperar_gravacao(5) and OC.estado()["disco"]["gravado_em"] == gravado and "novas" in OC.estado()["leituras"]
    # a 1ª falha de uma faixa regrava o cabeçalho; a que se repete (o Fracttal fora, de 3 em 3 min) não regrava
    time.sleep(0.05)
    rel = OL.ler_novas(ler=RestOS(base, falha_no=1))
    assert rel["erro"] and OC.esperar_gravacao(5)
    com_falha = OC.estado()["disco"]["gravado_em"]
    assert com_falha > gravado and OC.estado()["leituras"]["novas"]["erro"]
    time.sleep(0.05)
    OL.ler_novas(ler=RestOS(base, falha_no=1))
    assert OC.esperar_gravacao(5) and OC.estado()["disco"]["gravado_em"] == com_falha
    time.sleep(0.05)
    OL.ler_novas(ler=RestOS(base))                                       # a 1ª boa depois da falha regrava: a falha sai do disco
    assert OC.esperar_gravacao(5) and OC.estado()["disco"]["gravado_em"] > com_falha
    assert not OC.estado()["leituras"]["novas"]["erro"]


def test_a_pausa_vem_antes_de_cada_os_pelo_numero(monkeypatch):
    """As pendentes vêm logo depois das novas e dos 7 dias: a pausa de 1 s vem antes de CADA pedido pelo nº, o 1º também
    (nunca 2 pedidos colados)."""
    base = _base(20)
    _lista_de(base)
    for k in (1, 2, 3):
        OC.atualizar_os(base[k]["id_work_order"])
    eventos = []
    monkeypatch.setattr(P, "PAUSA_S", 1.0)
    monkeypatch.setattr(OL, "_dormir", lambda s: eventos.append(("pausa", s)))
    rest = RestOS(base)
    rel = OL.ler_pendentes(ler=lambda path: eventos.append(("pedido",)) or rest(path))
    assert rel["erro"] == "" and eventos == [("pausa", 1.0), ("pedido",)] * 3


# ── rodada 1 da revisão: o piso das finalizadas (Minor 8) ───────────────────────────────────────────────────────────────
def test_finalizadas_com_data_fim_no_futuro():
    """Uma data fim no futuro (dado ruim) não vira o piso: o piso é a mais nova que a lista conhece, nunca depois de agora,
    menos 2 dias. Sem isso, as concluídas de hoje ficariam de fora até a data ruim passar."""
    base = ([_linha(900, status=3, criada=_iso(40), fim=_iso(-30))]
            + [_linha(3000 + k, status=1, criada=_iso(20)) for k in range(50)])
    _lista_de(base)
    assert OC.mais_nova_data_fim()[:10] == _iso(-30)[:10]
    agora = [dict(w, id_status_work_order="3", final_date=_iso(0.1 + (w["id_work_order"] - 3000) / 20),
                  wo_final_date=_iso(0.1 + (w["id_work_order"] - 3000) / 20))
             if 3000 <= w["id_work_order"] < 3020 else w for w in base]
    rel = OL.ler_finalizadas(ler=RestOS(agora))
    assert rel["erro"] == ""
    lista = OC.atual()
    assert all(lista.por_id[3000 + k].status_id == 3 for k in range(20)) and lista.por_id[3020].status_id == 1


# ── rodada 1 da revisão: o defeito do leitor (Minor 2) ──────────────────────────────────────────────────────────────────
def test_rodar_separa_o_defeito(monkeypatch, caplog):
    """A leitura incompleta, a recusa e a rede são "a leitura não veio inteira"; qualquer outra exceção é defeito do leitor:
    vai ao log com a pilha, e o estado diz que foi defeito."""
    base = _base(20)
    _lista_de(base)
    for rest in (RestOS(base, falha_no=1), RestOS(base, recusa_no=1), RestOS(base, erro_no=1)):
        rel = OL.ler_sete_dias(ler=rest)
        assert rel["erro"] and not rel.get("defeito") and "não veio inteira" in rel["resultado"], rel
    monkeypatch.setattr(OC, "receber", lambda *a, **k: {}["campo que não existe"])
    with caplog.at_level(logging.WARNING, logger="oscreator.os_leitor"):
        rel = OL.ler_sete_dias(ler=RestOS(base))
    assert rel["defeito"] is True and "KeyError" in rel["erro"] and "defeito" in rel["resultado"]
    assert OL.estado()["faixas"]["sete_dias"]["defeito"] is True
    assert any(r.exc_info and r.levelno >= logging.ERROR for r in caplog.records)


# ── rodada 1 da revisão: os minutos na lista única (Minor 1) ────────────────────────────────────────────────────────────
def test_os_minutos_moram_na_lista_unica():
    """Os minutos fixos da lista de OS moram em `minutos_ocupados` (como os dos ativos), e a lista bate com os laços de
    verdade: cada `MINUTO_DA_HORA` tem o dono certo, e o diário do uso do OS Creator (04:45) também está lá."""
    from nexus.campo import chamados_acompanhamento, zeladoria_banco
    from nexus.casca import uso_os
    from nexus.cos import normalizacoes_banco
    from nexus.dados import carga
    for mod, dono in ((chamados_acompanhamento, "chamados"), (zeladoria_banco, "zeladoria"),
                      (normalizacoes_banco, "normalizações"), (carga, "carga")):
        assert dono in MO.OCUPADOS[mod.MINUTO_DA_HORA], mod.__name__
    for m in range(P.MINUTO_DA_HORA, P.MINUTO_DA_HORA + P.DESENCONTRO_MAX_S // 60 + 1):
        assert "tarefas" in MO.OCUPADOS[m], m
    # a lista de OS lê os minutos de lá, e eles são dela
    assert (OL.SETE_DIAS_MINUTOS, OL.FINALIZADAS_MINUTO, OL.ABERTAS_MINUTO, OL.NOITE_HORA) == (
        MO.OS_SETE_DIAS, MO.OS_FINALIZADAS, MO.OS_ABERTAS, MO.OS_NOITE)
    for m in MO.OS_SETE_DIAS + (MO.OS_FINALIZADAS, MO.OS_ABERTAS, MO.OS_NOITE[1]):
        assert "lista central de OS" in MO.OCUPADOS[m], m
    # os diários: o uso do OS Creator às 04:45 (as finalizadas do :46 fogem dele), a noite da lista e os ativos inteiros
    assert (uso_os.GRAVAR_NA_HORA, uso_os.GRAVAR_NO_MINUTO) == MO.USO_OS_BANCO and "uso" in MO.DIARIOS[MO.USO_OS_BANCO]
    assert "lista central de OS" in MO.DIARIOS[MO.OS_NOITE] and "ativos" in MO.DIARIOS[MO.ATIVOS_COMPLETO]
    assert not MO.livre(45, hora=4) and MO.livre(45, hora=3) and MO.livre(45) and (4, MO.OS_FINALIZADAS) not in MO.DIARIOS
    # dois donos no mesmo minuto não passam: a lista acusa ao montar
    with pytest.raises(ValueError, match="já é de"):
        MO._ocupar(dict(MO.OCUPADOS), (MO.OS_FINALIZADAS,), "outro laço")


def test_a_noite_de_domingo_acaba_antes_da_gravacao_do_uso_no_banco():
    """Revisão final: a noite de domingo da lista de OS começa às 03:21 e lê os 365 dias, ~830 páginas a ~1 por segundo (1,35 s
    cada no ensaio de 18/10/2026 do `tarefas_os`): de 19 a 29 min, até depois das 03:45, onde estava a gravação diária do uso do
    OS Creator no banco (~7 s de processador). Mesmo no pior caso (29 min) a noite acaba antes da gravação."""
    noite = MO.OS_NOITE[0] * 60 + MO.OS_NOITE[1]
    gravacao = MO.USO_OS_BANCO[0] * 60 + MO.USO_OS_BANCO[1]
    assert noite + 29 < gravacao


# ── rodada 2 da revisão: a leitura que acaba antes do piso ──────────────────────────────────────────────────────────────
def test_a_leitura_que_acaba_antes_do_piso_nao_passa_calada():
    """Sem o total no começo (o do `work_orders` sem filtro é o de todas as OS), a leitura pela criação que acabava ANTES do
    piso (a página vazia com `success: true`, ou a curta, de um REST com teto no `start`) não conferia nada: na 1ª carga, com a
    lista vazia, a noite instalava o pedaço lido e declarava os 365 dias lidos inteiros. Agora ela pede o total no fim e confere
    ("vieram X de N"); a leitura que chega ao piso, a de produção, não pede nada a mais."""
    base = [_linha(1000 + k, criada=_iso(0.05 + 20 * k / 600)) for k in range(600)]      # 600 OS em 20 dias
    for corta_em in (200, 250):                                                          # a página vazia; a curta
        OC.reiniciar()
        rest = RestOS(base, corta_em=corta_em)
        rel = OL.ler_noite(ler=rest, inteira=True)
        assert "vieram %d de 600" % corta_em in rel["erro"] and "nada mudou" in rel["resultado"], (corta_em, rel)
        assert len(rest.totais()) == 1                                                    # o total, só no fim
        lista = OC.atual()
        assert len(lista.por_id) == 0 and lista.janela == (None, None)
    # os 7 dias também, com a lista cheia: as 210 OS da semana cortadas em 150
    _lista_de(base)
    antes = OC.atual()
    rel = OL.ler_sete_dias(ler=RestOS(base, corta_em=150))
    assert "vieram 150 de 600" in rel["erro"]
    assert (OC.atual().versao, OC.atual().a_conferir, OC.atual().janela) == (antes.versao, antes.a_conferir, antes.janela)
    # a leitura que chega ao piso não pede o total
    rest = RestOS(base)
    assert OL.ler_sete_dias(ler=rest)["erro"] == "" and rest.totais() == []


def test_topo_minimo_e_obrigatorio_com_piso_ou_conhecida():
    """Sem o topo, a guarda da ordem perdia a 1ª regra calada (o REST em ordem crescente passaria): quem lê pelo piso ou pela
    página conhecida tem de dar o `topo_minimo`, e esquecê-lo é erro de quem chama, antes de qualquer pedido (rodada 2)."""
    rest = RestOS([_linha(1000, criada=_iso(1))])
    for kw in ({"piso": _iso(7)[:19]}, {"conhecida": lambda pagina: True}):
        with pytest.raises(ValueError, match="topo_minimo"):
            P.ler_criadas(rest, com_total=False, **kw)
    assert rest.pedidos == []
    assert len(P.ler_criadas(rest, piso=_iso(7)[:19], topo_minimo=_iso(3)[:19], com_total=False)) == 1
