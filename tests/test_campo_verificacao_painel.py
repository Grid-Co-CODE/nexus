"""A rodada 6 do Painel do responsável (29/10/2026): as OSs em verificação (o número depois da página, a lista com o
Concluir e o PDF do OS Creator), o relatório em PDF, e a janela da equipe (o ativo limpo, o "e mais" que abre em linhas,
a pontuação do mês com o placar do ciclo e o "−1" explicado). Nomes de pessoas fictícios (o repositório é público)."""
import re
from datetime import datetime, timedelta, timezone

import pytest
from test_campo_responsaveis import _responsavel, banco, tela  # noqa: F401  (fixtures)

from nexus.campo import aprovacao, painel_relatorio, regras_app
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



def test_o_concluir_so_diz_concluida_com_o_ok_do_os_creator(tela, logado, fila, tmp_path):
    """Revisão de 05/11/2026 (achado na Aprovação por fatos, que usa a mesma rota): com a sessão do Nexus vencida (12 h, ou
    o Sair noutra aba), o portão responde 302 para /entrar, o fetch segue e recebe 200 em HTML, e o Concluir dizia "OS X
    concluída." sem nada ter ido ao Fracttal. E o `aviso` da rota é um booleano (fechou sem a data de fim): saía
    "concluída. true". Agora: concluída só com `ok: true` em JSON, sem redirecionamento; a frase é a do OS Creator."""
    import shutil
    import subprocess
    html = logado.get("/t/campo/responsaveis?responsavel=Ciclano+Chefe").get_data(as_text=True)
    js = next(s for s in re.findall(r"<script>(.*?)</script>", html, re.S) if "data-pv-concluir" in s)
    # o pedido diz se foi redirecionado e se a resposta era JSON (o `.catch` do r.json() devolve null, não {})
    assert "r.json().catch(function () { return null; })" in js
    assert "redirected: r.redirected" in js and "json: j !== null" in js
    concluir = js[js.index("if (b.hasAttribute('data-pv-concluir'))"):js.index("nexusRota('/os/api/os/pdf')")]
    assert "if (r.ok && !r.redirected && r.j.ok === true)" in concluir
    assert "r.j.mensagem || ('OS ' + folio + ' concluída.')" in concluir and "r.j.aviso ? 'alerta' : 'ok'" in concluir
    assert "' ' + r.j.aviso" not in js                                           # o "concluída. true" saiu
    # a sessão do Nexus que acabou (redirecionado) tem frase própria; o 401 segue o ENTRAR do Fracttal; a resposta sem
    # JSON sem redirecionar é o servidor que não respondeu (09/11/2026, o PDF da OS 8159 com o chat OS Creator): no
    # Concluir manda conferir no Fracttal, no PDF diz que nada foi gravado
    assert "var SESSAO = 'A sua sessão do Nexus acabou: recarregue a página e entre de novo.';" in js
    assert concluir.index("if (r.redirected)") < concluir.index("r.status === 401") < concluir.index("if (!r.json)")
    assert "if (!r.json) { aviso(SEM_RESPOSTA_CONCLUIR, 'critico'); return; }" in concluir
    pdf = js[js.index("nexusRota('/os/api/os/pdf')"):]
    assert "if (r.ok && !r.redirected && r.j.url)" in pdf and "if (r.redirected || !r.json)" not in pdf
    assert "if (r.redirected) { aviso(SESSAO, 'critico'); return; }" in pdf
    assert "if (!r.json) { aviso(SEM_RESPOSTA_PDF, 'critico'); return; }" in pdf
    if shutil.which("node"):
        arq = tmp_path / "verificacao.js"
        arq.write_text("var nexusRota = function (x) { return x; };" + chr(10) + js, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(arq)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

def test_o_relatorio_em_pdf_e_o_botao_na_linha_dos_filtros(tela, logado, fila):
    html = logado.get("/t/campo/responsaveis?responsavel=Ciclano+Chefe").get_data(as_text=True)
    filtros = html[html.index('<form class="cn-filtros"'):html.index("</form>", html.index('<form class="cn-filtros"'))]
    assert 'class="gc-btn gc-btn--contorno pn-exportar" data-pn-rel' in filtros
    # o botão abre a escolha dos temas (30/10/2026: "a pessoa possa marcar o tema que ela quer levar (...) tem que ter a
    # opção de tirar"): os oito, todos marcados, com os filtros da tela no formulário
    tpl = html[html.index('<template id="pn-rel-temas">'):html.index("</template>", html.index('id="pn-rel-temas"'))]
    acao = re.search(r'<form class="pn-rel" method="get" action="([^"]+)"', tpl).group(1)
    assert re.findall(r'name="tema" value="(\w+)" checked', tpl) == list(painel_relatorio.CHAVES_TEMAS)
    assert '<input type="hidden" name="responsavel" value="Ciclano Chefe">' in tpl and "Tirar todos" in tpl
    for t in ("[data-pn-rel-todos]", "Marque pelo menos um tema"):
        assert t in html
    r = logado.get(acao + "?responsavel=Ciclano+Chefe")                             # sem tema: todos
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data[:5] == b"%PDF-"
    assert "attachment" in r.headers["Content-Disposition"] and "Ciclano%20Chefe" in r.headers["Content-Disposition"]
    so_dois = logado.get(acao + "?responsavel=Ciclano+Chefe&tema=pts&tema=rondas&tema=xx")
    assert so_dois.status_code == 200 and so_dois.data[:5] == b"%PDF-" and len(so_dois.data) < len(r.data)
    # fora do Painel, sem o botão
    assert "pn-exportar" not in logado.get("/t/campo/responsaveis?responsavel=Ciclano+Chefe&modo=geral").get_data(
        as_text=True)


def test_os_temas_escolhidos_tiram_do_resumo_e_das_frases():
    assert painel_relatorio.temas_do_pedido([]) == painel_relatorio.CHAVES_TEMAS
    assert painel_relatorio.temas_do_pedido(["rondas", "perf", "lixo"]) == ("perf", "rondas")    # na ordem do PDF
    assert painel_relatorio.temas_do_pedido(["lixo"]) == painel_relatorio.CHAVES_TEMAS
    p = _painel_falso()
    faixa = [({"usina": "Altair"}, {"escopo": "Inversor 1", "os": "500", "inicio": "28/10 10:00"})]
    verif = V.oss(FILA, USINAS, COS, AGORA)
    temas = ("pts", "rondas")
    assert [n["tema"] for n in painel_relatorio.resumo(p, faixa, verif, temas)] == ["pts", "rondas"]
    fr = painel_relatorio.frases(p, faixa, verif, temas)
    assert len(fr) == 2 and "PT parada" in fr[0] and "sem nenhuma ronda" in fr[1]
    pdf = painel_relatorio.gerar(p, faixa, verif, filtros=[], gerado_em="x", temas=temas)
    assert pdf[:5] == b"%PDF-"
    # um tema só: o resumo com uma caixa (a linha do resumo é completada, a tabela é retangular)
    assert painel_relatorio.gerar(p, [], None, filtros=[], gerado_em="x", temas=("pendencias",))[:5] == b"%PDF-"


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
            # as Pendências de OS no lugar do Ranking das equipes (09/11/2026)
            "pendencias": {"os": 1, "atrasadas": 1, "pausadas": 0, "grupos": [
                {"usina_id": 1, "usina": "Altair", "pior": 40, "itens": [
                    {"os": 702, "wid": None, "situacao": "Atrasada", "dias": 40,
                     "motivo": "programada há 40 dias e não feita"}]}]}}


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
    assert any("1 OS pendente" in f and "OS 702 (Altair, atrasada: programada há 40 dias" in f for f in fr)
    assert nums["OS pendentes"] == 1 and "Equipes (Outubro)" not in nums
    pdf = painel_relatorio.gerar(p, faixa, verif, filtros=["cliente Thopen"], gerado_em="29/10/2026 18:00")
    assert pdf[:5] == b"%PDF-" and len(pdf) > 3000
    # sem a fila lida, o número das OSs fica em branco, sem quebrar
    assert painel_relatorio.gerar(p, [], None, filtros=[], gerado_em="x")[:5] == b"%PDF-"


def test_o_css_do_mais_e_das_perdas():
    from pathlib import Path
    css = Path(__file__).resolve().parents[1].joinpath("nexus", "static", "campo.css").read_text(encoding="utf-8")
    assert ".cr-rk-j-mais[open] > summary{display:none}" in css and ".cr-rk-j-mais-lista{display:grid" in css
    assert ".pv-tab tbody tr:hover .pv-pdf" in css and ".cn-filtros .pn-exportar{margin-left:auto" in css
