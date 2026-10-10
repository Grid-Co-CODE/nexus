"""Quadro da equipe de engenharia (06/10/2026): as OS de cada responsável da engenharia, por coluna, com os supercards.
Nomes fictícios (o repositório é público; os de verdade ficam no .env do OS Creator)."""
from datetime import datetime, timedelta, timezone

from nexus.engenharia import os_equipe as E

AGORA = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)
PESSOAS = [{"id_personnel": 1, "name": "Ana  Teste", "full_name": "Ana Teste"},
           {"id_personnel": 2, "name": "Bruno Exemplo", "full_name": "Bruno Exemplo"},
           {"id_personnel": 3, "name": "Bruno Exemplar", "full_name": "Bruno Exemplar"}]


def _w(folio, status, task="NO_STARTED", pid=1, prog_dias=3, fim=None, **kw):
    prog = AGORA + timedelta(days=prog_dias)
    d = {"wo_folio": folio, "id_work_order": 9000 + int(folio), "id_personnel": pid, "id_status_work_order": status,
         "task_status": task, "description": f"Análise {folio}", "items_log_description": "Inversor 1.1 {X-INV1.1}",
         "code": "X-INV1.1", "groups_1_description": "Thopen - Altair 1 - SP", "tasks_log_task_type_main": "Administrativa",
         "date_maintenance": prog.isoformat(), "creation_date": (AGORA - timedelta(days=5)).isoformat(),
         "final_date": fim, "wo_final_date": fim, "initial_date": None,
         "labels": [{"description": "ENGENHARIA", "color": "2f4fe6", "enabled": True}]}
    d.update(kw)
    return d


def test_nome_vira_pessoa_so_quando_e_uma():
    assert E.casar("Ana", PESSOAS)["id_personnel"] == 1             # começa por "Ana" (o Fracttal escreve com 2 espaços)
    assert E.casar("Bruno Exemplo", PESSOAS)["id_personnel"] == 2   # igual
    assert E.casar("Bruno", PESSOAS) is None                        # dois Brunos: não chuta
    assert E.casar("Carla", PESSOAS) is None


def test_coluna_e_prazo_de_cada_os():
    linhas = [_w("1", 1, prog_dias=-2), _w("2", 1, prog_dias=1), _w("3", 1, prog_dias=9),
              _w("4", 1, task="IN_PROGRESS"), _w("5", 2), _w("6", 3, fim=(AGORA - timedelta(days=2)).isoformat()),
              _w("7", 4), _w("8", 1, pid=99)]                      # a 8 é de um homônimo: fora
    oss = {o["os"]: o for o in E.montar(linhas, {"id": 1, "nome": "Ana"}, AGORA)}
    assert set(oss) == {"1", "2", "3", "4", "5", "6", "7"}
    assert [oss[k]["coluna"] for k in "1234567"] == ["fazer", "fazer", "fazer", "execucao", "verificacao", "concluida", "cancelada"]
    assert (oss["1"]["prazo"], oss["2"]["prazo"], oss["3"]["prazo"]) == ("atrasada", "vence", "futura")
    assert oss["1"]["etiquetas"] == [{"nome": "ENGENHARIA", "cor": "#2f4fe6"}]
    assert oss["1"]["url"] == "https://one.fracttal.com/tasks/wo/9001"


def test_uma_os_com_varias_tarefas_vira_um_cartao():
    linhas = [_w("10", 1, description="Tarefa A"), _w("10", 1, description="Tarefa B", task="DONE", initial_date="x")]
    oss = E.montar(linhas, {"id": 1, "nome": "Ana"}, AGORA)
    assert len(oss) == 1 and len(oss[0]["tarefas"]) == 2


def test_supercards_contam_a_carga_e_a_faixa_dos_14_dias():
    from nexus.torres.engenharia import supercards
    linhas = [_w("1", 1, prog_dias=-2), _w("2", 1, prog_dias=0), _w("3", 1, prog_dias=3), _w("4", 2),
              _w("5", 3, fim=(AGORA - timedelta(days=2)).isoformat())]
    oss = E.montar(linhas, {"id": 1, "nome": "Ana"}, AGORA)
    hoje = AGORA.astimezone(E.BRT).date()
    c = supercards(oss, [{"id": 1, "nome": "Ana", "nome_fracttal": "Ana Teste"}], hoje)[0]
    assert (c["carga"], c["atrasadas"], c["vence"], c["fechadas30"]) == (4, 1, 1, 1)
    assert c["faixa"][0]["n"] == 1 and c["faixa"][3]["n"] == 1 and sum(f["n"] for f in c["faixa"]) == 2
    assert c["proxima"]["os"] == "2" and c["iniciais"] == "AT"


def test_tela_do_quadro(app, logado, monkeypatch):
    oss = E.montar([_w("1", 1, prog_dias=-2), _w("2", 2)], {"id": 1, "nome": "Ana"}, AGORA)
    monkeypatch.setattr(E, "pedir_releitura", lambda app=None, esperar=False: None)
    monkeypatch.setattr(E, "dados", lambda: {"os": oss, "equipe": [{"id": 1, "nome": "Ana", "nome_fracttal": "Ana Teste"}],
                                             "faltam": ["Carla"], "lido": 1.0, "lendo": False, "erro": ""})
    html = logado.get("/t/engenharia/equipe").get_data(as_text=True)
    assert "Quem está com o quê" in html and 'class="kb-super"' in html and "Não achei no Fracttal: Carla" in html
    assert 'id="kb-dados"' in html and '"os": "1"' in html.replace("'", '"')


# ── o card da OS do OS Creator no quadro (Levi, 08/10/2026: "Ao clicar na OS quero que abra o mesmo card que aparece
# quando clicamos em uma OS no histórico do OS Creator Web") ─────────────────────────────────────────────────────────
def test_cada_os_leva_o_id_e_o_status_do_card():
    """O REST já traz o id da OS (sem pedido novo ao Fracttal só para isso) e o status vai com o nome do OS Creator."""
    import sys

    from nexus.torres.oscreator import ponte
    if ponte.RAIZ_CLONE not in sys.path:
        sys.path.append(ponte.RAIZ_CLONE)
    import api                                                     # o api.py do clone (WO_STATUS)
    assert E.STATUS_OS == api.WO_STATUS
    oss = {o["os"]: o for o in E.montar([_w("1", 1), _w("5", 2), _w("6", 3), _w("7", 4)], {"id": 1, "nome": "Ana"}, AGORA)}
    assert (oss["1"]["wid"], oss["1"]["status"]) == (9001, "Em Processo")
    assert [oss[k]["status"] for k in "567"] == ["Em Verificação", "Concluída", "Cancelada"]


def test_o_quadro_abre_o_card_do_os_creator(logado, monkeypatch):
    oss = E.montar([_w("1", 1, prog_dias=-2)], {"id": 1, "nome": "Ana"}, AGORA)
    monkeypatch.setattr(E, "pedir_releitura", lambda app=None, esperar=False, forcar=False: None)
    monkeypatch.setattr(E, "dados", lambda: {"os": oss, "equipe": [{"id": 1, "nome": "Ana", "nome_fracttal": "Ana Teste"}],
                                             "faltam": [], "lido": 1.0, "lendo": False, "erro": ""})
    html = logado.get("/t/engenharia/equipe").get_data(as_text=True)
    # o componente que abre o card (oscreator/card_os_abrir.html) e a moldura dele, /os/_nexus/card/<id>
    assert "window.NexusOsCard" in html and "nexusRota('/os/_nexus/card/') + encodeURIComponent(wid)" in html
    assert "NexusOsCard.abrir(o.wid, {status: o.status, folio: o.os" in html
    # o nº da OS é o link da página dela no OS Creator (o mesmo do Histórico: /os/os/<id>?status=...)
    assert "num.href = nexusRota('/os/os/') + encodeURIComponent(o.wid) + '?status=' + encodeURIComponent(o.status || '')" in html
    dados = html.split('id="kb-dados">', 1)[1].split("</script>", 1)[0]
    assert '"wid": 9001' in dados and '"status": "Em Processo"' in dados and '"os": "1"' in dados
    assert "eg-gaveta" not in html                                 # a gaveta própria saiu: o card é o do OS Creator


def test_quem_mudou_a_os_pelo_card_volta_com_o_quadro_relido(logado, monkeypatch):
    pedidos = []
    monkeypatch.setattr(E, "pedir_releitura", lambda app=None, esperar=False, forcar=False: pedidos.append((esperar, forcar)))
    monkeypatch.setattr(E, "dados", lambda: {"os": [], "equipe": [], "faltam": [], "lido": 1.0, "lendo": False, "erro": ""})
    logado.get("/t/engenharia/equipe")
    logado.get("/t/engenharia/equipe?atualizar=1")
    assert pedidos == [(False, False), (True, True)]


def test_a_releitura_forcada_tem_um_piso(monkeypatch):
    """Forçada, relê mesmo com a cópia nova; mas não mais de uma a cada FORCAR_S (cota do Fracttal é da empresa)."""
    import time
    lidas = []
    monkeypatch.setattr(E, "_reler", lambda app: lidas.append(1) or E._EST.update(lendo=False))
    monkeypatch.setitem(E._EST, "ts", time.time())
    monkeypatch.setitem(E._EST, "erro_em", 0.0)
    E.pedir_releitura(app=object(), esperar=True)                   # cópia nova: não relê
    E.pedir_releitura(app=object(), esperar=True, forcar=True)      # forçada, mas a cópia tem menos de FORCAR_S
    assert lidas == []
    monkeypatch.setitem(E._EST, "ts", time.time() - E.FORCAR_S - 1)
    E.pedir_releitura(app=object(), esperar=True, forcar=True)
    assert lidas == [1]


# ── a faixa de números no modelo do Acompanhamento de chamados (Levi, 08/10/2026: "Precisamos padronizar a estética ...
# o card de KPIS eu gostei mais do de chamados"): rótulo em cima, número colorido pela gravidade, explicação ao lado ──
def _quadro_para_a_faixa():
    dias = lambda n: (AGORA + timedelta(days=n)).isoformat()            # noqa: E731
    linhas = [_w("1", 1, prog_dias=-2), _w("2", 1, prog_dias=-5), _w("3", 1, prog_dias=1), _w("4", 1, prog_dias=0),
              _w("5", 1, prog_dias=9), _w("6", 1, task="IN_PROGRESS", prog_dias=3),
              _w("7", 2, prog_dias=-20, fim=dias(-10), task="DONE"), _w("8", 2, prog_dias=-20, fim=dias(-2), task="DONE"),
              _w("9", 3, fim=dias(-3)), _w("10", 3, fim=dias(-1)), _w("11", 3, fim=dias(-40)), _w("12", 4)]
    return E.montar(linhas, {"id": 1, "nome": "Ana"}, AGORA)


def _texto(nota):
    return "".join(t for t, _ in nota)


def test_a_faixa_diz_o_numero_a_gravidade_e_por_onde_comecar():
    from nexus.torres.engenharia import faixa_kpis
    k = {x["rotulo"]: x for x in faixa_kpis(_quadro_para_a_faixa(), AGORA.astimezone(E.BRT).date(), 30)}
    assert list(k) == ["Em aberto", "Atrasadas", "Vencem em 2 dias", "Esperando verificação", "Fechadas em 30 dias"]
    assert (k["Em aberto"]["valor"], k["Em aberto"]["grav"]) == (8, "")
    assert _texto(k["Em aberto"]["nota"]) == "5 a fazer, 1 em execução e 2 em verificação"
    # a mais atrasada é a que passou mais da data (a 2, 5 dias), e o nº da OS vai em negrito
    assert (k["Atrasadas"]["valor"], k["Atrasadas"]["grav"]) == (2, "critico")
    assert k["Atrasadas"]["nota"] == [("a mais atrasada: ", False), ("OS 2", True), (", 5 dias", False)]
    assert (k["Vencem em 2 dias"]["valor"], k["Vencem em 2 dias"]["grav"]) == (2, "alerta")
    assert _texto(k["Vencem em 2 dias"]["nota"]) == "a próxima: OS 4, vence hoje"
    # em verificação conta desde a execução terminada: a 7 espera há 10 dias, mais que os 7 da régua -> âmbar
    assert (k["Esperando verificação"]["valor"], k["Esperando verificação"]["grav"]) == (2, "alerta")
    assert _texto(k["Esperando verificação"]["nota"]) == "a mais antiga: OS 7, feita há 10 dias"
    # a de 40 dias fica fora das 30; a última fechada é a 10
    assert (k["Fechadas em 30 dias"]["valor"], k["Fechadas em 30 dias"]["grav"]) == (2, "ok")
    assert _texto(k["Fechadas em 30 dias"]["nota"]) == "a última: OS 10, em 05/10"


def test_a_faixa_vazia_explica_em_vez_de_inventar():
    from nexus.torres.engenharia import faixa_kpis
    hoje = AGORA.astimezone(E.BRT).date()
    k = faixa_kpis([], hoje, 30)
    assert [x["valor"] for x in k] == [0] * 5 and [x["grav"] for x in k] == [""] * 5
    assert [_texto(x["nota"]) for x in k] == ["nenhuma OS em aberto", "nenhuma passou da data programada",
                                              "nenhuma até 08/10", "nenhuma esperando", "nenhuma nos últimos 30 dias"]
    # verificação recente (2 dias) não pinta; sem a execução terminada, vale a data programada, dita como tal
    oss = E.montar([_w("8", 2, prog_dias=-20, fim=(AGORA - timedelta(days=2)).isoformat(), task="DONE")], {"id": 1, "nome": "Ana"}, AGORA)
    v = faixa_kpis(oss, hoje, 30)[3]
    assert (v["grav"], _texto(v["nota"])) == ("", "a mais antiga: OS 8, feita há 2 dias")
    oss = E.montar([_w("9", 2, prog_dias=-12)], {"id": 1, "nome": "Ana"}, AGORA)
    v = faixa_kpis(oss, hoje, 30)[3]
    assert (v["grav"], _texto(v["nota"])) == ("alerta", "a mais antiga: OS 9, programada 24/09")


def test_a_faixa_da_tela_tem_rotulo_numero_e_explicacao(logado, monkeypatch):
    import re
    oss = _quadro_para_a_faixa()
    monkeypatch.setattr(E, "pedir_releitura", lambda app=None, esperar=False, forcar=False: None)
    monkeypatch.setattr(E, "dados", lambda: {"os": oss, "equipe": [{"id": 1, "nome": "Ana", "nome_fracttal": "Ana Teste"}],
                                             "faltam": [], "lido": 1.0, "lendo": False, "erro": ""})
    html = logado.get("/t/engenharia/equipe").get_data(as_text=True)
    faixa = html.split('<section class="kb-kpis"', 1)[1].split("</section>", 1)[0]
    blocos = faixa.split('<div class="kb-kpi">')[1:]
    assert len(blocos) == 5
    for b in blocos:
        rotulo = re.search(r'<span class="kb-kpi-rot">([^<]+)</span>', b).group(1).strip()
        numero = re.search(r'<b class="kb-kpi-v[^"]*">(\d+)</b>', b).group(1)
        nota = re.sub(r"<[^>]+>", "", b.split('<span class="kb-kpi-nota">', 1)[1]).strip()
        assert rotulo and numero.isdigit() and nota, b
    assert '<b class="kb-kpi-v kb-kpi-v--critico">2</b>' in faixa and "a mais atrasada: <b>OS 2</b>, 5 dias" in faixa
    assert "kb-resumo" not in html                                     # a faixa de antes (número em cima, rótulo embaixo) saiu
