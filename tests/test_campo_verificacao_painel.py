"""A rodada 6 do Painel do responsável (29/10/2026): as OSs em verificação (o número depois da página, a lista com o
Concluir e o PDF do OS Creator), o relatório em PDF, e a janela da equipe (o ativo limpo, o "e mais" que abre em linhas,
a pontuação do mês com o placar do ciclo e o "−1" explicado). Nomes de pessoas fictícios (o repositório é público)."""
import re
from datetime import date, datetime, timedelta, timezone

import pytest
from test_campo_responsaveis import _responsavel, banco, tela  # noqa: F401  (fixtures)

from nexus.campo import aprovacao, painel_relatorio, regras_app
from nexus.campo import ranking_equipes as RK
from nexus.campo import verificacao as V

AGORA = datetime(2026, 10, 29, 18, 0, tzinfo=timezone.utc)
COS = {"nomes": {V._norm("Fulana Prado")}, "codigos": {"CICLANOA"}, "pessoas": 2, "erro": ""}


def _linha(wo, folio, usina_fx, final_h_atras, item, etiquetas=(), criador="Beltrano Souza", codigo="BELTRANOS",
           titulo="Inspeção do inversor"):
    return {"id_work_order": wo, "wo_folio": folio, "groups_1_description": usina_fx, "id_item": item,
            "creation_date": "2026-10-01T12:00:00+00:00", "description": titulo, "personnel_description": "Técnico Silva ",
            "final_date": (AGORA - timedelta(hours=final_h_atras)).isoformat(), "labels": [{"description": e} for e in
                                                                                           etiquetas],
            "created_by": criador, "code_create_by": codigo}


USINAS = {regras_app._norm("Thopen - Altair 1 - SP"): {"usina": "Altair", "cliente": "Thopen"}}
FILA = [_linha(1, "9001", "Thopen - Altair 1 - SP", 30, 11), _linha(1, "9001", "Thopen - Altair 1 - SP", 200, 12),
        _linha(1, "9001", "Thopen - Altair 1 - SP", 5, 12),                     # o mesmo ativo de novo: conta uma vez
        _linha(2, "9002", "Thopen - Altair 1 - SP", 3, 21, etiquetas=("PERFORMANCE",)),
        _linha(3, "9003", "Thopen - Altair 1 - SP", 3, 31, etiquetas=("Engenharia",)),
        _linha(4, "9004", "Thopen - Altair 1 - SP", 3, 41, criador="Fulana  Prado ", codigo=""),   # COS pelo nome
        _linha(5, "9005", "Thopen - Altair 1 - SP", 3, 51, criador="Outro Nome", codigo="ciclanoa"),  # COS pelo código
        _linha(6, "9006", "Thopen - Altair 1 - SP", 900, 61, etiquetas=("Aguardando Garantia",)),   # etiqueta que fica
        _linha(7, "9007", "UFV de outro responsável", 3, 71)]


def test_as_os_da_fila_juntam_as_tarefas_e_tiram_etiqueta_e_cos():
    r = V.oss(FILA, USINAS, COS, AGORA)
    assert [o["os"] for o in r["lista"]] == ["9006", "9001"]          # a que espera há mais tempo primeiro
    o = r["lista"][1]
    # a OS 9001: 3 tarefas, 2 ativos; a espera é a da tarefa terminada há mais tempo (a mesma conta da Aprovação)
    assert o["ativos"] == 2 and o["espera_d"] == 8 and o["espera"] == "8 d 8 h"
    assert (o["titulo"], o["tecnico"], o["usina"], o["cliente"], o["criada_txt"]) == (
        "Inspeção do inversor", "Técnico Silva", "Altair", "Thopen", "01/10/2026")
    # de fora: PERFORMANCE e ENGENHARIA (sem diferença de caixa), e as do COS pelo nome e pelo código
    assert r["fora"] == {"etiqueta": 2, "cos": 2}
    # sem saber quem é do COS, só as etiquetas tiram
    assert [o["os"] for o in V.oss(FILA, USINAS, None, AGORA)["lista"]] == ["9006", "9001", "9004", "9005"]


def test_as_regras_pequenas():
    assert V.etiqueta_fora({"labels": [{"description": "chamados"}]}) == "CHAMADOS"
    assert V.etiqueta_fora({"labels": [{"description": "Aguardando Equipamento"}]}) == ""
    assert V.criada_pelo_cos({"created_by": "FULANA PRADO"}, COS) and not V.criada_pelo_cos({"created_by": "X"}, COS)
    assert (V.espera_txt(0.5), V.espera_txt(5.2), V.espera_txt(50)) == ("30 min", "5 h", "2 d 2 h")


def test_quem_e_do_cos_sai_do_setor_e_do_pessoal(monkeypatch):
    from nexus.cadastro import setores as S
    V.limpar()
    monkeypatch.setattr(S, "ler", lambda base, sessao: {
        "setores": [{"setor_id": 5, "nome": "COS", "excluido": False}, {"setor_id": 2, "nome": "PCM", "excluido": False}],
        "decisoes": [{"fracttal_id": 10, "setor_id": 5, "decidida_em": "2026-10-01"},
                     {"fracttal_id": 11, "setor_id": 5, "decidida_em": "2026-10-01"},
                     {"fracttal_id": 11, "setor_id": 2, "decidida_em": "2026-10-02"},      # saiu do COS depois
                     {"fracttal_id": 12, "setor_id": 2, "decidida_em": "2026-10-01"}], "erro": ""})
    pessoal = {"pessoas": [{"id": 10, "nome": "Fulana Prado"}, {"id": 11, "nome": "Ciclano Araújo"},
                           {"id": 12, "nome": "Beltrano Souza"}], "codigos": {10: "fulanap", 11: "CICLANOA"}, "erro": ""}
    c = V.criadores_cos("http://banco", None, lambda: pessoal)
    assert c["nomes"] == {"FULANA PRADO"} and c["codigos"] == {"FULANAP"} and c["pessoas"] == 1
    V.limpar()


@pytest.fixture
def fila(monkeypatch):
    monkeypatch.setitem(regras_app._FILA_CACHE, "linhas", FILA)
    monkeypatch.setattr(aprovacao, "_pedir_releitura", lambda: None)
    monkeypatch.setattr(aprovacao, "_lida_em", lambda: AGORA.timestamp())
    monkeypatch.setattr(V, "criadores_cos", lambda base, sessao, ler: COS)


def test_o_numero_chega_depois_e_a_lista_abre_na_janela(tela, logado, fila):
    html = logado.get("/t/campo/responsaveis?responsavel=Ciclano+Chefe").get_data(as_text=True)
    topo = html[html.index('<div class="pn-topo">'):html.index('<div class="pn">')]
    # ao lado das PT, o número vazio até a página pedir ("sem pesar todo carregamento")
    assert topo.index("data-pn-pts") < topo.index("data-pn-verif") and "<b data-pn-verif-num>…</b>" in topo
    n_url = re.search(r'data-pn-verif-n="([^"]+)"', topo).group(1).replace("&amp;", "&")
    assert logado.get(n_url).get_json() == {"n": 2, "lida": "29/10 15:00", "pronta": True}
    lista = re.search(r'data-pn-verif data-cr-painel="([^"]+)"', topo).group(1).replace("&amp;", "&")
    jan = logado.get(lista).get_data(as_text=True)
    assert "2 esperando concluir" in jan and "PERFORMANCE, CHAMADOS ou ENGENHARIA (2)" in jan and "COS (2)" in jan
    cab = re.findall(r'<th scope="col">([^<]*)</th>', jan)
    assert cab[:8] == ["OS", "Criação", "Título", "Ativos", "Técnico", "Cliente", "Usina", "Sem conclusão"]
    assert jan.count("data-pv-wo=") == 2 and "data-pv-concluir" in jan and "data-pv-pdf" in jan and "data-pv-os" in jan
    # o script da Visão conclui e baixa pelo OS Creator, e confere a saída da OS na fila da Aprovação
    for t in ("nexusRota('/os/api/os/') + wo + '/concluir'", "nexusRota('/os/api/os/pdf')",
              "'/t/campo/aprovacao/') + wo + '/conferir'",
              "NexusOsCard.abrir(wo, {status: 'Em Verificação'"):
        assert t in html
    # o responsável sem a usina da fila: zero
    assert logado.get(n_url.replace("Ciclano+Chefe", "Outro+Chefe")).get_json()["n"] == 0


def test_o_relatorio_em_pdf_e_o_botao_na_linha_dos_filtros(tela, logado, fila):
    html = logado.get("/t/campo/responsaveis?responsavel=Ciclano+Chefe").get_data(as_text=True)
    filtros = html[html.index('<form class="cn-filtros"'):html.index("</form>", html.index('<form class="cn-filtros"'))]
    url = re.search(r'class="gc-btn gc-btn--contorno pn-exportar" href="([^"]+)"', filtros).group(1).replace("&amp;", "&")
    r = logado.get(url)
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data[:5] == b"%PDF-"
    assert "attachment" in r.headers["Content-Disposition"] and "Ciclano%20Chefe" in r.headers["Content-Disposition"]
    # fora do Painel, sem o botão
    assert "pn-exportar" not in logado.get("/t/campo/responsaveis?responsavel=Ciclano+Chefe&modo=geral").get_data(
        as_text=True)


def _painel_falso():
    return {"nome": "Ciclano Chefe", "usinas": 2, "clientes": ["Thopen"], "equipes": ["SP Norte 01"],
            "perf": {"usinas": 2, "com_meta": 2, "abaixo": 1, "criticas": 1, "na_meta": 1, "sem_meta": 0,
                     "meta_grupo": 88.5, "linhas": [
                         {"usina": "Altair", "cliente": "Thopen", "atingimento": 70.0, "situacao": "critico", "pr": 70.0,
                          "pr_meta": 80.0, "disp": 99.0, "sujidade": 5, "vegetacao": 2},
                         {"usina": "Brodowski 1", "cliente": "Thopen", "atingimento": 99.0, "situacao": "ok"}]},
            "pts": {"aguardando": 1, "paradas": 1, "agora": 1, "linhas": [
                {"numero": "PT-1", "usina": "Altair", "tarefa": "Religamento", "idade_min": 200, "parada": True}]},
            "chamados": {"abertos": 1, "usinas": 1, "mais_antigo": 40, "verificacao": 0, "grupos": [
                {"usina": "Altair", "itens": [{"os": 1600, "ativo": "Inversor 1", "status": "", "dias": 40}]}]},
            "rondas": {"usinas": 2, "em_dia": 1, "nunca": 1, "sem_ronda": 0, "sem_7": 1, "longa": 0, "linhas": [
                {"usina": "Altair", "situacao": "nunca", "dias": None, "ultima": "", "tecnico": ""},
                {"usina": "Brodowski 1", "situacao": "em_dia", "dias": 2, "ultima": "27/10", "tecnico": ""}]},
            "extintores": {"usinas": 1, "vencidos": 2, "a_vencer": 1, "linhas": [
                {"usina": "Altair", "vencidos": 2, "a_vencer": 1, "pior": "recarga venceu", "pior_ext": "EXT1"}]},
            "ranking": {"mes": "Outubro", "n_equipes": 1, "total": 9, "equipes": [
                {"equipe": "SP Norte 01", "posicao": 4, "nota": 80, "qualidade": 75, "cobertura": 90, "n_os": 10,
                 "n_ronda": 3}]}}


def test_o_resumo_e_o_que_cobrar_primeiro_do_pdf():
    p = _painel_falso()
    faixa = [({"usina": "Altair"}, {"escopo": "Inversor 1", "os": "500", "inicio": "28/10 10:00"})]
    verif = V.oss(FILA, USINAS, COS, AGORA)
    nums = {n["rot"]: n["num"] for n in painel_relatorio.resumo(p, faixa, verif)}
    assert nums["Usinas abaixo da meta"] == 1 and nums["OSs em verificação"] == 2 and nums["Parada agora"] == 1
    fr = painel_relatorio.frases(p, faixa, verif)
    # o parado primeiro, depois o vencido, depois o que falta
    assert "1 parada agora" in fr[0] and "Altair (Inversor 1, desde 28/10 10:00)" in fr[0]
    assert "1 PT parada" in fr[1] and "abaixo de 90% da meta" in fr[2] and "sem nenhuma ronda" in fr[3]
    assert any("2 OSs em verificação" in f and "OS 9006" in f for f in fr)
    pdf = painel_relatorio.gerar(p, faixa, verif, filtros=["cliente Thopen"], gerado_em="29/10/2026 18:00")
    assert pdf[:5] == b"%PDF-" and len(pdf) > 3000
    # sem a fila lida, o número das OSs fica em branco, sem quebrar
    assert painel_relatorio.gerar(p, [], None, filtros=[], gerado_em="x")[:5] == b"%PDF-"


def test_o_placar_da_equipe_casa_pelo_nome():
    rk = {"meses": [{"mes": "2026-10", "calculado_em": "2026-10-29T18:25:00Z", "regua": {"piso": 70},
                     "classificacao": [{"tecnico": "Ciclano Araújo", "posicao": 2, "total": 900},
                                       {"tecnico": "Outro Técnico", "posicao": 1, "total": 1000}],
                     "fora": [{"tecnico": "Fulana  Prado", "posicao": None, "total": 10}]}]}
    p = RK.placar_da_equipe(["Ciclano Araujo", "Fulana Prado", "Sem Placar"], rk, date(2026, 10, 29))
    assert [(x["tecnico"], x["fora"]) for x in p["linhas"]] == [("Ciclano Araújo", False), ("Fulana  Prado", True)]
    assert p["sem_placar"] == ["Sem Placar"] and p["total"] == 2 and p["regua"] == {"piso": 70}
    assert RK.placar_da_equipe(["X"], rk, date(2026, 11, 2))["linhas"] == []           # o mês sem placar ainda


def test_o_ativo_limpo_nas_provas_da_equipe():
    us = [{"usina": "Altair", "chamados": {"lista": [
               {"situacao": "aberto", "dias": 59, "os": 1715, "equip": "Inversor 2.1 Fabricante SUN2000-215KTL-H3",
                "ativo": "Inversor 2.1", "fabricante": "Fabricante"},
               {"situacao": "aberto", "dias": 205, "os": 1731, "equip": "Estrutura Trackers BR 226/304, S/N, Zona Rural",
                "fabricante": "STI"}]},
           "ativos": {"lista": [{"nome": "Inversor 2.4 Fabricante SUN2000-215KTL-H3", "cod": "X-INV2.4",
                                 "nivel": "critico", "falhas": 5, "porque": "5 falhas em 30 dias"}]}}]
    _, ps, _ = RK._provas("chamados", us)
    assert [p["txt"] for _o, p in sorted(ps, key=lambda x: x[0])] == ["Altair · Estrutura de Trackers · há 205 d",
                                                                       "Altair · Inversor 2.1 · há 59 d"]
    _, ps, _ = RK._provas("ativos", us)
    assert ps[0][1]["txt"] == "Inversor 2.4 · Altair · 5 falhas em 30 dias"


def test_as_partes_da_nota_dizem_quanto_vale_e_o_que_fazer():
    n = {"nota": 97, "qualidade": 95, "cobertura": 100, "n_notas": 2}
    item = lambda rot, peso, pts: {"rot": rot, "peso": peso, "pts": pts}       # noqa: E731
    det = {"tarefas": [{"nota": 90, "itens": [item("Fotos com descrição", 10, 0), item("Fotos", 20, 20)]},
                       {"nota": 100, "itens": [item("Fotos com descrição", 10, 10), item("Fotos", 20, 20)]}],
           "rondas": []}
    m = RK.motivos(n, det, [{"usina_id": 1, "usina": "Altair"}], {1: {"atual": {"rondada": True}}})
    p = m["qualidade"]["partes"][0]
    assert (p["rot"], p["perde"], p["det"], p["peso"]) == ("Fotos com descrição", 3, "em 1 de 2 tarefas", "10")
    assert p["como"] == "escrever a descrição de cada foto"


def test_a_janela_da_equipe_traz_a_pontuacao_e_o_mais_que_abre(tela, logado):
    from pathlib import Path
    jan = logado.get("/t/campo/responsaveis/equipe?equipe=SP+Norte+01").get_data(as_text=True)
    assert "Pontuação do mês" in jan and jan.index("Pontuação do mês") < jan.index(">Focar ")
    assert re.search(r'class="cr-rk-j-formula"><b class="cn-t-\w+">\d+</b> = 60% da qualidade <b>\d+</b> \+ 40% da '
                     r'cobertura <b>\d+%</b>', jan)
    # o "e mais" com a lista dentro (o <details> não arruma os filhos em grade no Chrome)
    tpl = Path(__file__).resolve().parents[1].joinpath("nexus", "torres", "campo", "templates", "campo",
                                                       "_resp_equipe.html").read_text(encoding="utf-8")
    assert ('<details class="cr-rk-j-mais"><summary>e mais {{ resto|length }}</summary><div class="cr-rk-j-mais-lista">'
            in tpl)


def test_o_css_do_mais_e_das_perdas():
    from pathlib import Path
    css = Path(__file__).resolve().parents[1].joinpath("nexus", "static", "campo.css").read_text(encoding="utf-8")
    assert ".cr-rk-j-mais[open] > summary{display:none}" in css and ".cr-rk-j-mais-lista{display:grid" in css
    assert ".pv-tab tbody tr:hover .pv-pdf" in css and ".cn-filtros .pn-exportar{margin-left:auto" in css
