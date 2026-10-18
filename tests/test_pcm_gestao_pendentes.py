"""Gestão PCM: as tarefas pendentes da célula (Levi, 12/10/2026: "Na versão antiga ao clicar em cima do % do que tem
pendente aparecia as tarefas pendentes, resolva isso por gentileza no Nexus! Faça maior e mais bonito"). A célula da
usina com o que falta (e o número de Pendentes dela) abre um painel lateral com as tarefas por OS; MPA e MPS seguem
abrindo a Fila, como no painel. O número de tarefas da lista é o da célula. Nada vai à rede: a fonte é um arquivo local
no formato do gestao_pcm.json (os mesmos dados do test_pcm_gestao)."""
import json

from test_pcm_gestao import ALTAIR, TUCANO, M, com_fonte, t, tarefas  # noqa: F401  (com_fonte é fixture)

from nexus.pcm import gestao as G


def _base():
    return G.escopo(tarefas())


def test_a_lista_da_celula_bate_com_o_numero_da_celula():
    """Toda célula de usina da matriz: a lista tem exatamente t - f tarefas, e a conta de feitas/total é a mesma."""
    for o in (G.Opcoes(), G.Opcoes(col="mes"), G.Opcoes(tipo="prev"), G.Opcoes(tipo="corr")):
        mx = G.plano(G.base(_base(), M), o, M)
        for g in mx["grupos"]:
            for f in g["filhos"]:
                for c, col in zip(f["tds"], mx["cols"]):
                    if c.get("t"):
                        p = G.pendentes(_base(), o, M, f["nome"], col)
                        assert (p["n_tarefas"], p["feitas"], p["total"]) == (c["t"] - c["f"], c["f"], c["t"]), (o, col)
                tudo = f["tudo"]
                p = G.pendentes(_base(), o, M, f["nome"], "*")
                assert (p["n_tarefas"], p["total"]) == (tudo["t"] - tudo["f"], tudo["t"]), (o, "*")


def test_por_os_com_o_nome_curto_o_status_do_card_e_as_atrasadas_primeiro():
    ts = [t(ALTAIR, "[Grid Co.] - MPM - Estação Solarimétrica", "Não Iniciada", os_="301", dia="20"),
          t(ALTAIR, "[Grid Co.] - MPM - Infraestrutura", "Em progresso", os_="301", dia="20"),
          {**t(ALTAIR, "[Grid Co.] - MPM - Transformador", "Pausada", os_="302", dia="25"), "atrasado": True,
           "osStatus": "Finalizados", "idWO": 99, "url": "https://one.fracttal.com/tasks/wo/99"},
          t(ALTAIR, "[Grid Co.] - MPM - Cabine", "Finalizada", os_="303")]
    ts[0]["osStatus"] = ts[1]["osStatus"] = "Em processo"
    p = G.pendentes(G.escopo(ts), G.Opcoes(), M, ALTAIR, "MPM")
    assert (p["n_tarefas"], p["n_os"], p["feitas"], p["total"], p["pct"], p["atrasadas"]) == (3, 2, 1, 4, 25, 1)
    a, b = p["oss"]
    assert (a["os"], a["atrasada"], a["status"], a["fechada"], a["wid"]) == ("302", True, "Concluída", True, 99)
    assert (b["os"], b["status"]) == ("301", "Em Processo")              # a grafia do card do OS Creator
    # o nome sem o "[Grid Co.] - MPM - ", o inteiro no title; em progresso antes da não iniciada
    assert [x["curto"] for x in b["tarefas"]] == ["Infraestrutura", "Estação Solarimétrica"]
    assert b["tarefas"][0]["tarefa"] == "[Grid Co.] - MPM - Infraestrutura" and b["tarefas"][0]["sig"] == "MPM"
    assert [e for e, _n, _c in p["por_estado"]] == ["Em progresso", "Pausada", "Não Iniciada"]
    # a mesma atividade em vários ativos da OS vira uma linha com quantas são; a conta segue tarefa a tarefa
    ts2 = ts + [t(ALTAIR, "[Grid Co.] - MPM - Infraestrutura", "Em progresso", os_="301", dia="20") for _ in range(2)]
    p2 = G.pendentes(G.escopo(ts2), G.Opcoes(), M, ALTAIR, "MPM")
    infra = next(x for x in p2["oss"][1]["tarefas"] if x["curto"] == "Infraestrutura")
    assert infra["n"] == 3 and p2["n_tarefas"] == 5 and dict((e, n) for e, n, _c in p2["por_estado"])["Em progresso"] == 3


def test_painel_pela_tela(logado, com_fonte):
    html = logado.get("/t/pcm/gestao").get_data(as_text=True)
    corpo = html.split("<tbody>")[1].split("</tbody>")[0]
    # a célula da usina com o que falta é botão (MPM) e a de MPA continua indo à Fila; o número de Pendentes também abre
    assert 'class="pg-cel pg-tom--and pg-cel--pend" data-pend="?pu=' in corpo and "pc=MPM" in corpo
    assert "modo=fila" in corpo and 'class="pg-pend-bt"' in corpo and "pc=%2A" in corpo
    assert 'id="pgp"' in html and "NexusOsCard" in html                  # o painel e o card da OS do Nexus
    frag = logado.get("/t/pcm/gestao", query_string={"pu": ALTAIR, "pc": "MPM"})
    h = frag.get_data(as_text=True)
    assert frag.status_code == 200 and 'class="pgp-cab"' in h and ALTAIR in h
    pend, feitas = h.split('class="pgp-feitas"', 1)
    assert "MPM inversores" in pend and "MPM das cabines" not in pend     # nas pendentes, só a que falta
    assert "MPM das cabines" in feitas and "MPM inversores" not in feitas # a finalizada vai embaixo (18/10/2026)
    assert "<b>1</b> de <b>2</b> finalizadas" in h and "OS 101" in h
    tudo = logado.get("/t/pcm/gestao", query_string={"pu": ALTAIR, "pc": "*"}).get_data(as_text=True)
    assert "MPM inversores" in tudo and "MPA trackers" in tudo and "Disjuntor" not in tudo   # a corretiva fica fora
    corr = logado.get("/t/pcm/gestao", query_string={"pu": ALTAIR, "pc": "CORR"}).get_data(as_text=True)
    pend, feitas = corr.split('class="pgp-feitas"', 1)
    assert "Disjuntor" in pend and "Fusível" not in pend and "Fusível" in feitas
    # coluna que a matriz não tem: 404 (nada de lista inventada)
    assert logado.get("/t/pcm/gestao", query_string={"pu": ALTAIR, "pc": "XYZ"}).status_code == 404


def test_painel_obedece_os_filtros_de_cima_e_o_mes(logado, com_fonte):
    ts = tarefas() + [t(ALTAIR, "MPM do outro mês", "Não Iniciada", os_="401", mes=M[1], resp="Outro")]
    (com_fonte / "gestao_pcm.json").write_text(json.dumps({"geradoEm": "x", "dataHash": "pend-mes", "tarefas": ts}),
                                               encoding="utf-8")
    h = logado.get("/t/pcm/gestao", query_string={"pu": ALTAIR, "pc": "MPM", "mes": M[2]}).get_data(as_text=True)
    assert "MPM inversores" in h and "MPM do outro mês" not in h
    h = logado.get("/t/pcm/gestao", query_string={"pu": ALTAIR, "pc": "MPM", "responsavel": "Outro"}).get_data(as_text=True)
    assert "MPM do outro mês" in h and "MPM inversores" not in h


def test_a_celula_cheia_e_a_fracao_de_mpa_abrem_o_painel_com_as_finalizadas(logado, com_fonte):
    """Levi, 18/10/2026: "Quando clico em uma célula que está 100% vai para essa tela confusa, conseguiria abrir uma
    barra lateral com uma informação mais fácil de ler que nem as células com % abaixo de 100". Toda célula da usina com
    tarefa abre o painel: a de 100% também, e a fração de MPA e MPS, que ia direto à Fila (a Fila fica num link do
    painel). O painel separa as pendentes das finalizadas, com a data em que cada OS terminou."""
    import re
    ts = tarefas()
    ts[6]["dataFinal"] = f"{M[1]}-12"                                   # a MPT do Tucano, a célula de 100%
    (com_fonte / "gestao_pcm.json").write_text(json.dumps({"geradoEm": "x", "dataHash": "feitas", "tarefas": ts}),
                                               encoding="utf-8")
    html = logado.get("/t/pcm/gestao?mes=todos").get_data(as_text=True)
    corpo = html.split("<tbody>")[1].split("</tbody>")[0]
    assert 'class="pg-cel' in corpo and "pg-frac" not in corpo           # nenhuma célula da usina leva direto à Fila
    cheia = re.search(r'<button type="button" class="pg-cel pg-tom--ok pg-cel--pend" data-pend="([^"]*pc=MPT[^"]*)"',
                      corpo)
    assert cheia and "Tucano" in cheia.group(1)
    mpa = re.search(r'<button type="button" class="pg-cel [^"]*" data-pend="[^"]*pc=MPA[^"]*" data-fila="([^"]*)"', corpo)
    assert mpa and "modo=fila" in mpa.group(1) and "dt=MPA" in mpa.group(1)
    h = logado.get("/t/pcm/gestao", query_string={"pu": TUCANO, "pc": "MPT", "mes": "todos"}).get_data(as_text=True)
    assert "Tarefas · MPT" in h and "<b>1</b> de <b>1</b> finalizadas" in h and "Todas as tarefas desta célula" in h
    assert '<details class="pgp-feitas" open>' in h                    # sem pendente, as finalizadas abertas
    feitas = h.split('class="pgp-feitas"', 1)[1]
    assert "MPT da usina" in feitas and "OS 201" in feitas and "Finalizada em " + G.data_curta(f"{M[1]}-12") in feitas
    js = html.split("pgp-veu", 1)[1]
    assert "dataset.fila" in js and "Ver na Fila" in js

