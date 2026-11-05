"""Gestão PCM: os filtros de cima completos, os números do alto, as árvores e o Só atrasadas (Levi, 04/11/2026: trazer
da aba Gestão PCM do painel do PCM o que ela tem além do "Manutenções — Plano & Fila"). Contas em nexus/pcm/gestao.py,
transcritas do js/app.js do painel (`gpFilteredTarefas`, `gpMsOptions`, `gpNaoFin`, `renderGestao`, `gpTreeHTML`,
`gpTableHTML`, `gpFlatHTML`) e provadas contra ele (`python -m nexus.pcm.prova_gestao`).

Nada vai à rede: a fonte é um arquivo local no formato do gestao_pcm.json; os nomes são fictícios.
"""
import json

import pytest
from werkzeug.datastructures import MultiDict

from nexus.pcm import gestao as G

H = G.hoje()
M = G.meses(H)          # [mês retrasado, mês passado, mês corrente]

A1, A2, B1 = "Cliente A - Usina Norte 1 - SP", "Cliente A - Usina Sul 2 - BA", "Cliente B - Usina Leste 1 - CE"


def t(usina, tarefa, estado="Não Iniciada", tipo="Preventiva", os_="100", cluster="SP Leste 01", resp="Responsável A",
      etiquetas=(), ss="", prog="2026-10-10", ini="", fim="", dias=None, atrasado=False, os_status="Em processo",
      obs="", wid=1, criacao="2026-10-01"):
    aberta = estado != "Finalizada"
    return {"os": os_, "idWO": wid, "url": f"https://one.fracttal.com/tasks/wo/{wid}", "cliente": usina.split(" - ")[0],
            "usina": usina, "cluster": cluster, "responsavel": resp, "tipo": tipo, "tarefa": tarefa, "estado": estado,
            "aberta": aberta, "osStatus": os_status, "etiquetas": list(etiquetas), "ss": ss, "obs": obs,
            "dataProg": prog, "dataInicio": ini, "dataFinal": fim, "criacao": criacao,
            "dias": dias if aberta else None, "atrasado": atrasado}


def tarefas():
    return [
        t(A1, "[Grid Co.] - MPM - Inversores", "Finalizada", os_="1001", etiquetas=["PERFORMANCE"], prog="2026-10-05",
          ini="2026-10-05", fim="2026-10-06", wid=11),
        t(A1, "[Grid Co.] - MPM - Cabine", os_="1001", dias=12, atrasado=True, prog="2026-10-05", wid=11),
        t(A1, "Troca de fusível", "Em progresso", tipo="Corretiva", os_="1002", cluster="sp leste 01", ss="2950",
          dias=3, prog="2026-09-20", ini="2026-09-21", wid=12),
        t(A2, "Limpeza do quadro", "Pausada", tipo="Corretiva", os_="2001", cluster="BA Sul 01", resp="Responsável B",
          etiquetas=["Aguardando Peça", "ENGENHARIA", "Garantia", "PERFORMANCE"], dias=7, atrasado=True,
          prog="2026-08-30", wid=21, obs="aguardando a peça"),
        # OS finalizada no Fracttal com a tarefa em aberto: "Não Finalizadas no Período", fora da árvore principal
        t(A2, "Inspeção visual", tipo="Inspeção", os_="2002", cluster="BA Sul 01", resp="Responsável B",
          os_status="Finalizados", dias=40, atrasado=True, prog="2026-07-01", wid=22),
        t(B1, "[Grid Co.] - MPA - Geral", "Finalizada", os_="3001", cluster="CE Norte 01", resp="Responsável B",
          ss="2946", prog="2026-10-20", fim="2026-10-21", wid=31),
        t(B1, "[Grid Co.] - MPA - Trackers", os_="3001", cluster="CE Norte 01", resp="Responsável B", dias=-2,
          prog="2026-11-20", wid=31),
    ]


def _os(ts):
    return [x["os"] + ":" + x["tarefa"].split()[-1] for x in ts]


# ── os filtros pela URL ──────────────────────────────────────────────────────────────────────────────────────
def test_filtros_pela_url_com_varias_escolhas_e_o_endereco_de_hoje():
    f = G.filtros(MultiDict([("cliente", "Cliente A"), ("cliente", "cliente b"), ("cliente", "CLIENTE A"),
                             ("cliente", " "), ("tipo_tarefa", "Corretiva"), ("os", "  12 "), ("ss", " 29"),
                             ("pini", "2026-10-01"), ("pfim", "2026-13-01"), ("pmodo", "xyz"), ("atr", "1")]))
    assert f.cliente == ("Cliente A", "cliente b")             # a repetida só na maiúscula conta uma vez; a vazia sai
    assert f.tipo_tarefa == ("Corretiva",) and (f.os, f.ss) == ("12", "29")
    assert (f.pini, f.pfim, f.pmodo, f.atr) == ("2026-10-01", "", "qq", True)   # data inválida e modo de fora caem
    assert G.filtros({"cliente": "Cliente A"}).cliente == ("Cliente A",)        # o valor único de hoje vale
    assert G.filtros({}) == G.Filtros() and not G.Filtros().ativos() and f.ativos()
    assert G.filtros({"atr": "1"}).ativos() and G.filtros({"pmodo": "fim"}).pmodo == "fim"
    muitos = G.filtros(MultiDict([("usina", f"U{i:02d}" + "x" * 300) for i in range(80)]))
    assert len(muitos.usina) == 50 and all(len(v) == 160 for v in muitos.usina)   # 50 valores de 160 letras


def test_cada_lista_e_uma_escolha_ou_outra_e_as_listas_se_somam():
    esc = G.escopo(tarefas())

    def ver(**args):
        return _os(G.recortar(esc, G.filtros(MultiDict([(k, x) for k, v in args.items()
                                                         for x in (v if isinstance(v, list) else [v])]))).todas)
    assert ver(cliente=["Cliente B", "cliente a"]) == _os(esc)                     # várias escolhas: uma OU outra
    assert ver(cluster="SP LESTE 01") == ["1001:Inversores", "1001:Cabine", "1002:fusível"]   # sem maiúscula
    assert ver(etiqueta="engenharia") == ["2001:quadro"]                           # qualquer das etiquetas
    assert ver(tipo_tarefa="corretiva", responsavel="Responsável B") == ["2001:quadro"]   # uma lista E a outra
    assert ver(estado=["pausada", "Em progresso"]) == ["1002:fusível", "2001:quadro"]
    assert ver(os="00") == _os(esc) and ver(os="100") == ["1001:Inversores", "1001:Cabine", "1002:fusível"]
    assert ver(ss="29") == ["1002:fusível", "3001:Geral"]                          # a Solicitação por "contém"
    assert ver(usina=A1.upper(), cliente="Cliente B") == []                         # nada: a lista fica vazia


def test_periodo_em_cada_considerar():
    """O período pega a tarefa se QUALQUER das três datas (programada, início, final) cair na faixa; o "considerar" fica
    numa delas (painel: "o que FINALIZEI em julho")."""
    esc = G.escopo(tarefas())

    def oss(**a):
        return [x["os"] + x["tarefa"][-3:] for x in G.recortar(esc, G.filtros(a)).todas]
    out = {"pini": "2026-09-21", "pfim": "2026-10-06"}
    assert oss(**out) == ["1001res", "1001ine", "1002vel"]                     # a programada OU o início OU o final
    assert oss(**out, pmodo="prog") == ["1001res", "1001ine"]                  # 1002 é programada em 20/09
    assert oss(**out, pmodo="ini") == ["1001res", "1002vel"]                   # sem início, a tarefa não entra
    assert oss(**out, pmodo="fim") == ["1001res"]
    assert oss(pini="2026-11-01") == ["3001ers"] and oss(pfim="2026-07-01") == ["2002ual"]   # só um dos lados


def test_listas_em_cascata_com_a_grafia_mais_frequente_e_o_escolhido_sempre_na_lista():
    """Cada lista com os OUTROS filtros aplicados (o filtro não restringe a si mesmo), a grafia mais frequente entre as
    que só mudam na maiúscula e, como o painel, a ordem do localeCompare pt-BR; o escolhido fica na lista mesmo sem
    tarefa (a tela não esconde o filtro que está valendo)."""
    esc = G.escopo(tarefas())
    e = G.recortar(esc, G.Filtros()).escolhas
    assert list(e) == [n for n, *_ in G.LISTAS] == ["cliente", "usina", "cluster", "responsavel", "tipo_tarefa",
                                                     "etiqueta", "estado"]
    assert e["cliente"] == ["Cliente A", "Cliente B"] and e["cluster"] == ["BA Sul 01", "CE Norte 01", "SP Leste 01"]
    assert e["etiqueta"] == ["Aguardando Peça", "ENGENHARIA", "Garantia", "PERFORMANCE"]
    assert e["estado"] == ["Em progresso", "Finalizada", "Não Iniciada", "Pausada"]
    assert e["tipo_tarefa"] == ["Corretiva", "Inspeção", "Preventiva"]
    e = G.recortar(esc, G.filtros({"cliente": "cliente b"})).escolhas
    assert e["cliente"] == ["Cliente A", "Cliente B"] and e["usina"] == [B1] and e["cluster"] == ["CE Norte 01"]
    assert e["etiqueta"] == [] and e["estado"] == ["Finalizada", "Não Iniciada"]
    e = G.recortar(esc, G.filtros(MultiDict([("cliente", "Cliente B"), ("usina", A1), ("os", "999")]))).escolhas
    assert e["usina"] == [A1] and e["cliente"] == ["Cliente B"]              # nada com OS 999: só os escolhidos
    assert G.recortar(esc, G.filtros({"cluster": "sp leste 01"})).escolhas["cluster"] == [
        "BA Sul 01", "CE Norte 01", "SP Leste 01"]                           # a escolhida em minúscula não duplica


def test_a_ordem_das_listas_e_das_arvores_e_a_do_localecompare_do_painel():
    """A ordem do `localeCompare(…, 'pt-BR')` do navegador (ICU): espaço e pontuação antes dos dígitos, dígitos antes
    das letras; a letra sem acento e sem maiúscula decide, depois o acento, por último a maiúscula (a minúscula antes).
    A lista esperada saiu do node (ICU 78) com os mesmos nomes."""
    icu = ["2C", "acao", "Acao", "Açao", "Ação", "E1", "Greenyellow", "Grid Co.", "Inspecao",
           "Inspeção", "Ínspeção", "pa leste 01", "PA Leste 01", "PA LESTE 01", "Usína",
           "Úsina", "Usina  Norte", "Usina - Norte", "Usina – Norte", "Usina (Norte)", "Usina 10", "Usina 2",
           "usina norte", "Usina Norte", "USINA NORTE", "Usina_Norte", "Usina.Norte", "Usina/Norte", "Usina1",
           "Zeladoria"]
    for embaralhada in (list(reversed(icu)), icu[1::2] + icu[::2]):
        assert sorted(embaralhada, key=G.ordem_pt) == icu


# ── os números do alto, as árvores e o Só atrasadas ──────────────────────────────────────────────────────────
def test_os_numeros_do_alto_deixam_fora_as_nao_finalizadas_no_periodo():
    """Visíveis = Finalizadas + Em aberto, sem as "Não Finalizadas no Período" (OS Finalizados com a tarefa aberta), que
    vão numa lista à parte; Atrasadas = as abertas e atrasadas da visão principal (renderGestao do painel)."""
    a = G.aba(G.escopo(tarefas()), 10)
    assert a["numeros"] == {"todas": 7, "visiveis": 6, "finalizadas": 2, "em_aberto": 4, "atrasadas": 2, "nf": 1,
                            "pct_finalizadas": 33}
    assert [x["os"] for x in a["nf"]] == ["2002"] and len(a["arr"]) == 6
    vazio = G.aba([], 10)["numeros"]
    assert (vazio["visiveis"], vazio["pct_finalizadas"]) == (0, 0)


def test_as_arvores_cliente_usina_tipo_com_as_contagens_e_as_atrasadas():
    a = G.aba(G.escopo(tarefas()), 10)
    arv = a["arvores"]
    assert (arv["todas"]["n"], arv["nf"]["n"], arv["todas"]["aberta"]) == (6, 1, True)   # até 60 tarefas, aberta
    cli = arv["todas"]["clientes"]
    assert [(c["nome"], c["n"]) for c in cli] == [("Cliente A", 4), ("Cliente B", 2)]
    assert [(u["nome"], u["n"]) for u in cli[0]["usinas"]] == [(A1, 3), (A2, 1)]
    assert [(x["nome"], x["n"], x["atrasadas"], x["classe"]) for x in cli[0]["usinas"][0]["tipos"]] == [
        ("Corretiva", 1, 0, "corretiva"), ("Preventiva", 2, 1, "preventiva")]
    nf = arv["nf"]["clientes"]
    assert [(c["nome"], c["n"], c["usinas"][0]["tipos"][0]["nome"], c["usinas"][0]["tipos"][0]["atrasadas"])
            for c in nf] == [("Cliente A", 1, "Inspeção", 1)]
    assert "linhas" not in nf[0]["usinas"][0]["tipos"][0]             # a de fora abre fechada (painel)
    # aberta, a árvore leva as linhas de cada tipo (o painel abre e enche as tabelas); acima de 60, só as contagens
    assert [x["os"] for x in cli[0]["usinas"][0]["tipos"][1]["linhas"]] == ["1001", "1001"]
    grande = G.aba(G.escopo([t(A1, f"Tarefa {i}", os_=str(5000 + i)) for i in range(61)]), 10)["arvores"]["todas"]
    assert not grande["aberta"] and "linhas" not in grande["clientes"][0]["usinas"][0]["tipos"][0]


def test_a_tabela_de_um_tipo_na_ordem_do_painel_e_com_os_dias_em_cor():
    """As abertas pelos dias, as mais velhas primeiro; as outras (finalizadas e sem dias) depois, na ordem do arquivo.
    Dias: acima do diasAlerta (10) vermelho, de 5 a 10 âmbar; sem dias, negativa ou finalizada, "—"."""
    ts = [t(A1, "a", "Finalizada", os_="1", fim="2026-10-02", prog="2026-10-01"), t(A1, "b", os_="2", dias=4),
          t(A1, "c", os_="3", dias=11, etiquetas=["E1", "E2", "E3", "E4", "E5"]), t(A1, "d", os_="4", dias=-3),
          t(A1, "e", os_="5", dias=5), t(A1, "f", os_="6")]
    linhas = G.tarefas_do_no(G.escopo(ts), "Cliente A", A1, "Preventiva", 10)
    assert [x["os"] for x in linhas] == ["3", "5", "2", "4", "1", "6"]
    assert [(x["dias"], x["dias_cls"]) for x in linhas] == [("11d", "crit"), ("5d", "and"), ("4d", "ok"), ("—", "ok"),
                                                            ("—", "ok"), ("—", "ok")]
    c, _, _, _, a, _ = linhas
    assert (c["etiquetas"], c["etiquetas_mais"]) == (["E1", "E2", "E3"], 2)
    assert (a["prog"], a["fim"], a["estado"], a["estado_cls"], a["os"]) == ("01/10/2026", "02/10/2026", "Finalizada",
                                                                           "ok", "1")
    assert (c["wid"], c["status"], c["url"]) == (1, "Em Processo", "https://one.fracttal.com/tasks/wo/1")
    assert [G.estado_cls(e) for e in ("Em progresso", "Pausada", "Não Iniciada", "Finalizada")] == [
        "info", "nulo", "and", "ok"]
    assert G.tarefas_do_no(G.escopo(ts), "Cliente A", A1, "Corretiva", 10) is None       # nó que não existe


def test_so_atrasadas_a_lista_plana_das_mais_velhas_sem_as_nao_finalizadas():
    a = G.aba(G.escopo(tarefas()), 10, so_atrasadas=True)
    lista = a["so_atrasadas"]
    assert [(x["os"], x["dias"], x["dias_cls"]) for x in lista] == [("1001", "12d", "crit"), ("2001", "7d", "and")]
    x = lista[1]
    assert (x["cliente"], x["usina"], x["tipo"], x["estado"], x["prog"], x["obs"]) == (
        "Cliente A", A2, "Corretiva", "Pausada", "30/08/2026", "aguardando a peça")
    assert x["etiquetas"] == ["Aguardando Peça", "ENGENHARIA", "Garantia", "PERFORMANCE"]   # todas, como no painel
    assert G.aba(G.escopo(tarefas()), 10)["so_atrasadas"] is None             # sem o modo, nada montado


def test_atualizado_em_brasilia_com_o_corte():
    """O robô grava o geradoEm em UTC sem fuso e o painel o mostra como hora local (20:50 lá é 17:50 aqui): o Nexus
    mostra a hora de Brasília, no mesmo formato do toLocaleString('pt-BR') do painel."""
    d = {"geradoEm": "2026-11-04T20:50:31", "corteData": "2026-01-01"}
    assert G.atualizado(d) == "Atualizado: 04/11/2026, 17:50:31 · corte 01/01/2026 · fonte: API Fracttal"
    assert G.atualizado({"geradoEm": "2026-11-04T20:50:31Z"}).startswith("Atualizado: 04/11/2026, 17:50:31 · corte —")
    assert G.data_br("2026-01-01") == "01/01/2026" and G.data_br("") == "—" and G.data_br("2026") == "2026"


# ── o Plano & Fila com os filtros de cima ────────────────────────────────────────────────────────────────────
def _plano_ts():
    return [t(A1, "[Grid Co.] - MPM - Inversores", "Finalizada", prog=f"{M[2]}-05", os_="10"),
            t(A1, "[Grid Co.] - MPM - Cabine", prog=f"{M[2]}-05", os_="10", dias=12, atrasado=True),
            t(A1, "Troca de fusível", tipo="Corretiva", prog=f"{M[2]}-06", criacao=f"{M[2]}-01", os_="11", dias=2)]


def test_o_tipo_do_plano_sobrepoe_o_tipo_de_cima_e_o_so_atrasadas_vale_no_plano():
    """preventivas.js (gpvTarefasTop): com um Tipo próprio no Plano, o Tipo de cima sai (compor os dois daria matriz
    vazia: Corretiva em cima e Preventivas no Plano); com o Todos, o de cima vale. O Só atrasadas deixa no Plano só as
    abertas e atrasadas."""
    rec = G.recortar(G.escopo(_plano_ts()), G.filtros({"tipo_tarefa": "Corretiva"}))
    assert [x["os"] for x in rec.todas] == ["11"] and [x["os"] for x in rec.sem_tipo] == ["10", "10", "11"]
    f = G.filtros({"tipo_tarefa": "Corretiva"})
    assert G.tipo_local(G.opcoes({"tipo": "prev"}, M), f) and not G.tipo_local(G.opcoes({}, M), f)
    assert not G.tipo_local(G.opcoes({"tipo": "prev"}, M), G.Filtros())
    prev = G.tarefas_do_plano(rec, f, True)
    assert [x["os"] for x in prev] == ["10", "10", "11"]
    assert [x["os"] for x in G.tarefas_do_plano(rec, f, False)] == ["11"]
    atr = G.filtros({"atr": "1"})
    so = G.tarefas_do_plano(G.recortar(G.escopo(_plano_ts()), atr), atr, False)
    assert [x["tarefa"][-6:] for x in so] == ["Cabine"]


def test_a_fila_da_gerencial_com_os_filtros_novos():
    """gpvFilaTopOk: Cliente, Usina e Cluster pelo nome frouxo (qualquer das escolhas), a OS por "contém", o período
    pela Prevista OU pela Programada (sem o "considerar") e o Só atrasadas; Responsável, Tipo, Etiqueta, Estado e
    Solicitação não existem na Gerencial."""
    x = {"cli": "Cliente A", "usinaFull": "Cliente A – Usina Norte 1", "nome": "Cliente A – Usina Norte 1",
         "clu": "SP LESTE 01", "os": "1001 / 1002", "prev": "2026-09-10", "prog": "2026-10-02",
         "sit": {"k": "Atrasada"}}
    ok = lambda **a: G.fila_topo_ok(x, G.filtros(MultiDict([(k, v) for k, vs in a.items()          # noqa: E731
                                                             for v in (vs if isinstance(vs, list) else [vs])])))
    assert ok() and ok(cliente=["Cliente B", "cliente a"]) and not ok(cliente="Cliente B")
    assert ok(usina=A1) and ok(cluster="sp leste 01") and ok(responsavel="Ninguém", estado="Pausada", ss="77")
    assert ok(os="1002") and not ok(os="9")
    assert ok(pini="2026-10-01") and ok(pfim="2026-09-10") and not ok(pini="2026-09-11", pfim="2026-10-01")
    assert ok(pini="2026-10-01", pmodo="fim")                       # o "considerar" não vale na Gerencial
    assert ok(atr="1") and not G.fila_topo_ok(dict(x, sit={"k": "Concluída"}), G.filtros({"atr": "1"}))


# ── a tela ───────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def fonte_filtros(app, tmp_path, request):
    p = tmp_path / "gestao_pcm.json"
    p.write_text(json.dumps({"geradoEm": "2026-11-04T20:50:31", "corteData": "2026-01-01", "diasAlerta": 10,
                             "dataHash": "filtros-" + request.node.name, "tarefas": tarefas()}), encoding="utf-8")
    app.config["NEXUS_PCM_GESTAO_FONTE"] = str(p)
    return p


def _ctx(app, pares):
    from nexus.pcm import telas
    with app.test_request_context("/t/pcm/gestao"):
        return telas._ctx_gestao(app.config, MultiDict(pares))


def test_o_contexto_da_tela_leva_os_numeros_as_listas_e_as_arvores(app, fonte_filtros):
    c = _ctx(app, [("cliente", "Cliente A"), ("cliente", "Cliente B"), ("estado", "não iniciada")])
    assert c["numeros"]["visiveis"] == 2 and c["numeros"]["nf"] == 1 and c["numeros"]["em_aberto"] == 2
    assert c["filtros"].cliente == ("Cliente A", "Cliente B") and c["escolhidos"]["estado"] == ["não iniciada"]
    assert set(c["escolhas"]) == {n for n, *_ in G.LISTAS} and c["listas"] == G.LISTAS and c["pmodos"] == G.PMODOS
    assert c["atualizado"].startswith("Atualizado: 04/11/2026, 17:50:31 · corte 01/01/2026")
    assert c["arvores"]["todas"]["n"] == 2 and c["arvores"]["nf"]["n"] == 1 and c["so_atrasadas"] is None
    assert c["tem_topo"] and c["dias_alerta"] == 10
    # os links da tela guardam as várias escolhas (antes o url() levava só a primeira de cada filtro)
    assert "cliente=Cliente+A&cliente=Cliente+B" in c["url"](modo="fila")
    limpar = c["url"](**c["limpar"])
    assert "cliente" not in limpar and "estado" not in limpar
    c = _ctx(app, [("atr", "1")])
    assert [x["os"] for x in c["so_atrasadas"]] == ["1001", "2001"] and c["numeros"]["atrasadas"] == 2


def test_a_tela_abre_com_varias_escolhas_e_com_os_filtros_novos(logado, fonte_filtros):
    for q in ("?cliente=Cliente+A&cliente=Cliente+B&tipo_tarefa=Corretiva", "?etiqueta=PERFORMANCE&atr=1",
              "?pini=2026-09-01&pfim=2026-09-30&pmodo=ini", "?os=100&ss=29", "?modo=fila&estado=Pausada",
              "?cliente=Cliente+A"):
        r = logado.get("/t/pcm/gestao" + q)
        assert r.status_code == 200, q
    html = logado.get("/t/pcm/gestao?cliente=Cliente+A&cliente=Cliente+B&tipo_tarefa=Corretiva").get_data(as_text=True)
    # o formulário de cima leva os filtros que ele não mostra, com todas as escolhas
    assert '<input type="hidden" name="tipo_tarefa" value="Corretiva">' in html
    assert "Limpar filtros" in html


def test_a_rota_da_tabela_de_um_tipo(logado, fonte_filtros):
    """As tarefas de um tipo vêm numa rota à parte (31 mil tarefas não vão na página): o pedaço HTML da tabela, com a
    OS que abre o card dela no Nexus e o Fracttal no ícone. Nó que não existe = 404."""
    r = logado.get("/t/pcm/gestao", query_string={"arv": "todas", "ac": "Cliente A", "au": A1, "at": "Preventiva"})
    h = r.get_data(as_text=True)
    assert r.status_code == 200 and h.index("Cabine") < h.index("Inversores")       # a aberta mais velha primeiro
    assert 'data-wid="11"' in h and 'data-folio="1001"' in h and "https://one.fracttal.com/tasks/wo/11" in h
    assert "#1001" not in h and "12d" in h and "05/10/2026" in h
    r = logado.get("/t/pcm/gestao", query_string={"arv": "nf", "ac": "Cliente A", "au": A2, "at": "Inspeção"})
    assert r.status_code == 200 and "Inspeção visual" in r.get_data(as_text=True)
    # a visão principal não tem a Inspeção (ela é das não finalizadas no período), e os filtros valem na rota
    assert logado.get("/t/pcm/gestao", query_string={"arv": "todas", "ac": "Cliente A", "au": A2,
                                                     "at": "Inspeção"}).status_code == 404
    assert logado.get("/t/pcm/gestao", query_string={"arv": "todas", "ac": "Cliente A", "au": A1, "at": "Preventiva",
                                                     "estado": "Finalizada"}).get_data(as_text=True).count("<tr") == 2
    assert logado.get("/t/pcm/gestao", query_string={"arv": "xyz", "ac": "Cliente A", "au": A1,
                                                     "at": "Preventiva"}).status_code == 404


def test_a_rota_da_tabela_usa_a_mesma_copia_da_tela(logado, fonte_filtros, monkeypatch):
    """Nada de refazer as 31 mil tarefas a cada clique: a tela e a rota da tabela usam o mesmo recorte guardado."""
    contas = []
    original = G.recortar
    monkeypatch.setattr(G, "recortar", lambda *a, **k: contas.append(1) or original(*a, **k))
    assert logado.get("/t/pcm/gestao?cliente=Cliente+A").status_code == 200
    assert logado.get("/t/pcm/gestao", query_string={"cliente": "Cliente A", "arv": "todas", "ac": "Cliente A",
                                                     "au": A1, "at": "Corretiva"}).status_code == 200
    assert logado.get("/t/pcm/gestao?cliente=Cliente+A&modo=fila").status_code == 200
    assert len(contas) == 1


def test_as_pendentes_da_celula_obedecem_os_filtros_novos(logado, app, tmp_path):
    """O número da célula e a lista do painel lateral saem das mesmas tarefas, agora com os filtros novos."""
    p = tmp_path / "gestao_pcm.json"
    p.write_text(json.dumps({"geradoEm": "x", "dataHash": "pend-filtros", "tarefas": _plano_ts()}), encoding="utf-8")
    app.config["NEXUS_PCM_GESTAO_FONTE"] = str(p)
    h = logado.get("/t/pcm/gestao", query_string={"pu": A1, "pc": "MPM", "estado": "Não Iniciada"}).get_data(
        as_text=True)
    assert "Cabine" in h and "Inversores" not in h
    h = logado.get("/t/pcm/gestao", query_string={"pu": A1, "pc": "MPM", "atr": "1"}).get_data(as_text=True)
    assert "Cabine" in h and "Inversores" not in h and "<b>0</b> de <b>1</b> finalizadas" in h
