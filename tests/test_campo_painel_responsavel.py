"""O Painel do responsável (Levi, 28/10/2026: "quero uma tela feita mesmo para o responsável que não seja um tabelão (...)
uma tela inicial claro"; e, ao ver a 1ª versão: "não podemos deixar nada de fora"): os quadros sobre o que a Visão do
responsável já calcula, completos, e a tela com o banco falso. A 2ª rodada (no mesmo dia, ao ver no ar): os chamados por
usina com o ativo sem a marca e o status do chamado, a tela do chamado por cima, o número das Rondas, o texto das PT, o
Ranking do mês e o 6º quadro, os extintores vencidos."""
import re
from datetime import date

from test_campo_responsaveis import _responsavel, banco, tela  # noqa: F401  (fixtures)

from nexus.campo import painel_responsavel as P
from nexus.campo import responsaveis as R


def _u(uid, nome, ating=None, pr=None, pr_meta=None, ronda=None, chamados=(), pts=(), equipe="SP Norte 01", ext=None):
    lista_ch = [{"os": 100 + i, "situacao": s, "dias": d, "equip": "Inversor 1 Sungrow SG125HV", "ativo": "Inversor 1",
                 "status": st, "fabricante": "Sungrow", "componente": ""}
                for i, (s, d, st) in enumerate(chamados)]
    return {"usina_id": uid, "usina": nome, "cliente": "Thopen", "equipe": equipe,
            "meta": {"atingimento": ating, "pr": pr, "pr_meta": pr_meta} if ating is not None else None,
            "disp": {"disp": 99.5}, "ronda": ronda or {},
            "chamados": {"abertos": sum(1 for s, _, _ in chamados if s == "aberto"),
                         "verificacao": sum(1 for s, _, _ in chamados if s == "verificacao"), "lista": lista_ch},
            "pt": {**R._pt_vazia(), "aguardando": len(pts), "paradas": sum(1 for x in pts if x["parada"]),
                   "lista": list(pts)}, "perf": {"nivel": "ok"}, "acomp": {"nivel": "ok"},
            "extintores": ext or {}, "nivel": "ok"}


USINAS = [
    _u(1, "Altair", 85.0, ronda={"tipo": "sem_ronda", "dias": 9, "ultima": "2026-10-19", "os": "500"},
       chamados=[("aberto", 26, "Testes em campo"), ("verificacao", 3, ""), ("aberto", 40, "")],
       pts=[{"numero": "PT-1", "codigo": "A", "idade_min": 30, "parada": False, "hoje": True}],
       ext={"total": 4, "vencidos": 1, "a_vencer": 2, "lista": [{"ext": "EXT-02", "onde": "Cabine", "txt":
            "recarga venceu em 12/10", "ordem": 0}, {"ext": "EXT-03", "onde": "", "txt": "recarga vence em 9 dias",
                                                     "ordem": 1}]}),
    _u(2, "Brodowski 1", 95.0, pr=70.0, pr_meta=80.0, ronda={"dias": 2, "ultima": "2026-10-26", "os": "501"},
       chamados=[("aberto", 300, "Aguardando retorno do Fabricante")],
       pts=[{"numero": "PT-2", "codigo": "B", "idade_min": 400, "parada": True, "hoje": True},
            {"numero": "PT-3", "codigo": "C", "idade_min": 3000, "parada": True, "hoje": False}],
       ext={"total": 6, "vencidos": 3, "a_vencer": 0, "lista": [{"ext": "EXT-01", "onde": "", "txt":
            "teste hidrostático venceu em 01/10", "ordem": 0}]}),
    _u(3, "Coração 1", 101.0, ronda={"tipo": "nunca", "dias": 999}, ext={"total": 2, "vencidos": 0, "a_vencer": 1}),
    _u(4, "Sem Meta", None, ronda={"tipo": "longa_pendente", "dias": 1, "ultima": "2026-10-27"}),
    _u(5, "Dourados", 70.0, ronda={"dias": 5, "ultima": "2026-10-23"}),
]


def test_performance_traz_todas_as_usinas_da_pior_para_a_melhor():
    p = P.performance(USINAS)
    assert [x["usina"] for x in p["linhas"]] == ["Dourados", "Altair", "Brodowski 1", "Coração 1", "Sem Meta"]
    assert [x["situacao"] for x in p["linhas"]] == ["critico", "critico", "alerta", "ok", "sem_meta"]
    assert (p["usinas"], p["com_meta"], p["abaixo"], p["criticas"], p["na_meta"], p["sem_meta"]) == (5, 4, 3, 2, 1, 1)
    assert p["linhas"][2]["pr_abaixo"] and not p["linhas"][0]["pr_abaixo"]
    # o PR e a disponibilidade com a cor que a Visão já dá na linha (`linha_performance`); sem ela, neutro
    assert (p["linhas"][0]["pr_cls"], p["linhas"][0]["disp_cls"]) == ("neutro", "neutro")
    com_valores = dict(USINAS[1], perf={"nivel": "ok", "valores": {"pr": {"cls": "alerta"}, "disp": {"cls": "ok"}}})
    linha = P.performance([com_valores])["linhas"][0]
    assert (linha["pr_cls"], linha["disp_cls"]) == ("alerta", "ok")


def test_chamados_por_usina_o_mais_antigo_primeiro_com_o_ativo_e_o_status():
    """Levi, 28/10/2026: "pode só botar o nome da UFV uma vez e dizer qual os ativos daquela UFV"; sem a marca; com o
    status do chamado; os concluídos e os em verificação fora da lista."""
    c = P.chamados(USINAS)
    assert (c["abertos"], c["verificacao"], c["usinas"], c["mais_antigo"]) == (3, 1, 2, 300)
    assert [g["usina"] for g in c["grupos"]] == ["Brodowski 1", "Altair"]           # a do chamado mais antigo primeiro
    altair = c["grupos"][1]
    assert [x["dias"] for x in altair["itens"]] == [40, 26] and altair["mais_antigo"] == 40
    assert altair["itens"][1] == {"os": 100, "ativo": "Inversor 1", "status": "Testes em campo", "dias": 26}
    assert altair["itens"][0]["status"] == ""                                         # sem status: a tela diz
    assert all(x["dias"] != 3 for g in c["grupos"] for x in g["itens"])               # o em verificação não entra


def test_pts_completas_na_ordem_de_quem_cobra():
    p = P.pts(USINAS)
    # a parada de hoje (técnico parado agora), depois a parada de outro dia, depois a que espera há menos de 2 h
    assert [x["numero"] for x in p["linhas"]] == ["PT-2", "PT-3", "PT-1"]
    assert (p["aguardando"], p["paradas"], p["agora"]) == (3, 2, 1)


def test_rondas_traz_todas_as_usinas_e_o_numero_soma_as_que_nunca_tiveram():
    r = P.rondas(USINAS)
    assert [x["usina"] for x in r["linhas"]] == ["Coração 1", "Altair", "Sem Meta", "Dourados", "Brodowski 1"]
    assert [x["situacao"] for x in r["linhas"]] == ["nunca", "sem_ronda", "longa_pendente", "em_dia", "em_dia"]
    assert (r["usinas"], r["em_dia"], r["sem_ronda"], r["nunca"], r["longa"], r["em_dia_pct"]) == (5, 2, 1, 1, 1, 40)
    # Levi, 28/10/2026: "o número do KPI deve falar quantas usinas estão sem ronda a 7 dias ou mais"; "Somar as que
    # nunca tiveram"
    assert r["sem_7"] == 2
    assert r["linhas"][0]["dias"] is None and r["linhas"][1]["os"] == "500"


def test_extintores_so_as_usinas_com_vencido_a_com_mais_primeiro():
    e = P.extintores(USINAS)
    assert [x["usina"] for x in e["linhas"]] == ["Brodowski 1", "Altair"]            # Coração 1 só tem a vencer
    assert (e["usinas"], e["vencidos"], e["com_extintor"], e["a_vencer"]) == (2, 4, 3, 3)
    assert e["linhas"][1]["pior"] == "recarga venceu em 12/10" and e["linhas"][1]["pior_ext"] == "EXT-02"


def test_ranking_todas_as_equipes_pela_posicao_e_o_mes():
    rk = {"total": 12, "cartoes": [
        {"equipe": "B", "nota": 70, "posicao": 11, "sem_equipe": False},
        {"equipe": "Sem equipe", "nota": None, "posicao": None, "sem_equipe": True},
        {"equipe": "A", "nota": 93, "posicao": 1, "sem_equipe": False},
        {"equipe": "C", "nota": None, "posicao": None, "sem_equipe": False},
        *({"equipe": f"E{i}", "nota": 50 + i, "posicao": 12 - i if i else 12, "sem_equipe": False} for i in range(9))]}
    r = P.ranking(rk, date(2026, 10, 28))
    nomes = [c["equipe"] for c in r["equipes"]]
    assert nomes[:2] == ["A", "E8"] and nomes[-2:] == ["C", "Sem equipe"] and len(nomes) == 13    # nada fica de fora
    # "Ranking das Equipes - Outubro, sempre o mês vigente"; o número do quadro, as equipes (29/10/2026: "quero a
    # quantidade de equipes"), sem contar as usinas sem equipe
    assert (r["total"], r["mes"], r["desde"], r["n_equipes"]) == (12, "Outubro", date(2026, 10, 1), 12)


def test_ranking_no_empate_da_nota_vale_a_posicao():
    """Levi, 28/10/2026: "O ranking também tem que ordenar por posição aqui o 4° lugar está acima do 2°, não faz
    sentido!" (CE Leste 01 e MG Centro 01 com 98: o desempate do ranking pôs a MG em 2º, e o nome punha a CE em cima)."""
    rk = {"total": 53, "cartoes": [{"equipe": "CE Leste 01", "nota": 98, "posicao": 4, "sem_equipe": False},
                                   {"equipe": "MG Centro 01", "nota": 98, "posicao": 2, "sem_equipe": False},
                                   {"equipe": "CE Leste 02", "nota": 97, "posicao": 5, "sem_equipe": False}]}
    assert [c["posicao"] for c in P.ranking(rk, date(2026, 10, 28))["equipes"]] == [2, 4, 5]


def test_montar_e_o_cabecalho():
    p = P.montar("Ciclano Chefe", USINAS, {"cartoes": [], "total": 0}, date(2026, 10, 28))
    assert (p["nome"], p["usinas"], p["clientes"], p["equipes"]) == ("Ciclano Chefe", 5, ["Thopen"], ["SP Norte 01"])
    assert all(k in p for k in ("perf", "chamados", "pts", "ranking", "rondas", "extintores"))


def test_o_nome_do_ativo_sem_a_marca():
    """Levi, 28/10/2026: "Não precisa mostrar a marca do ativo"."""
    assert R.nome_do_ativo("Inversor 1.7 Sungrow SG125HV") == "Inversor 1.7"
    assert R.nome_do_ativo("Tracker 5.100 STI STI-H250 Bi-linha") == "Tracker 5.100"
    assert R.nome_do_ativo("Tracker 24.300 Trina Solar Vanguard 1P") == "Tracker 24.300"
    assert R.nome_do_ativo("RSU 1") == "RSU 1"
    assert R.nome_do_ativo("Disjuntor do Inversor 1") == "Disjuntor do Inversor 1"
    assert R.nome_do_ativo("SKID 1 Sítio Serrote s/n - Setor C Zona Rural") == "SKID 1"
    # a estrutura inteira de trackers vem com o endereço da usina depois (com e sem número de rodovia)
    assert R.nome_do_ativo("Estrutura Trackers  Aparecida do Taboado  Mato Grosso do Sul Brasil") == "Estrutura de Trackers"
    assert R.nome_do_ativo("Estrutura Trackers BR 226 S/N Zona Rural") == "Estrutura de Trackers"
    assert R.nome_do_ativo("Estrutura de Trackers") == "Estrutura de Trackers"
    # o ativo que é a própria usina; o tipo sem número, com o endereço depois
    assert R.nome_do_ativo("Thopen - Usina Teste 1 - DF BR 070 km 5") == "Usina inteira"
    assert R.nome_do_ativo("Estação Meteorológica Rodovia BR 365 KM 2") == "Estação Meteorológica"
    assert R.nome_do_ativo("Preventiva Grupo de Inversores") == "Preventiva Grupo de Inversores"
    assert R.nome_do_ativo("", "THPN-FZL100-ETKR14.101") == "THPN-FZL100-ETKR14.101"
    assert R.nome_do_ativo(None, None) == "equipamento"


# ── a tela, com o banco falso ───────────────────────────────────────────────────────────────────────────────────────
def test_a_tela_do_painel_do_responsavel(tela, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=Ciclano+Chefe").get_data(as_text=True)
    assert 'aria-current="page">Painel' in html and '<h1 class="cn-titulo">Ciclano Chefe</h1>' in html
    assert '<div class="campo-nativa pn-pagina">' in html                     # a página 20% menor (29/10/2026)
    for t in ("Usinas abaixo da performance", "Chamados abertos", "PTs pendentes", "Ranking das Equipes - ",
              "Acompanhamento de rondas", "Extintores vencidos"):
        assert t in html
    # todas as usinas do responsável na Performance e nas Rondas (Altair e Brodowski 1), nunca a do outro
    for qual in ("pn-perf-t", "pn-rd-t"):
        i = html.index(f'id="{qual}"')
        sec = html[i:html.index("</section>", i)]
        assert "Altair" in sec and "Brodowski 1" in sec and "Coração 1" not in sec
    secoes = re.findall(r'<section class="pn-q.*?</section>', html, re.S)
    assert len(secoes) == 5 and not any(">e mais " in x for x in secoes)         # nada fica de fora
    # 29/10/2026: as PT no número do cabeçalho, que abre a lista na janela ("um KPI que quando o supervisor clicasse
    # ele veria quais são as PTs"); a Performance com duas colunas de largura
    assert 'data-pn-pts' in html and 'id="pn-pts-lista"' in html and 'id="pn-pt-t"' not in html
    # o botão com o ícone, o rótulo, o número e a seta (29/10/2026: "que botão escroto é esse? melhore o design")
    assert re.search(r'data-pn-pts.*?class="pn-kpi-ico".*?PTs pendentes</small><span><b>\d+</b> esperando o De acordo'
                     r'.*?pn-kpi-seta', html, re.S)
    # à esquerda da faixa "Parada agora", na mesma linha ("faça caber ao lado esquerdo de parado agora")
    topo = html[html.index('<div class="pn-topo">'):html.index('<div class="pn">')]
    assert "data-pn-pts" in topo and html.index("data-pn-pts") < html.index('<div class="pn">')
    assert 'class="pn-q pn-q--largo" aria-labelledby="pn-perf-t"' in html and "PR × previsto" in html
    # os números da Performance numa linha só, no card largo ("dá para fazer o texto caber melhor")
    i = html.index('id="pn-perf-t"')
    perf = html[i:html.index("</section>", i)]
    assert 'class="pn-num pn-num--linha"' in perf and "meta do grupo no mês</span>" in perf and "na meta</span>" in perf
    # sem a barra das rondas e sem o aviso do ranking; os números diretos ("só a quantidade de chamados em aberto",
    # "a quantidade de equipes", "6 extintores vencidos e 2 a vencer")
    assert 'class="pn-seg"' not in html and 'class="pn-nota"' not in html
    i = html.index('id="pn-ch-t"')
    assert re.search(r'</b>\s*<span>chamados? em aberto</span>', html[i:html.index("</section>", i)])
    i = html.index('id="pn-rk-t"')
    assert re.search(r'<div class="pn-num"><b>\d+</b><span>equipes?</span>', html[i:html.index("</section>", i)])
    i = html.index('id="pn-ex-t"')
    assert re.search(r'</b>\s*<span>extintor(es)? vencidos?( e \d+ a vencer)?</span>', html[i:html.index("</section>", i)])
    # o outro nível: o dia a dia da meta, a PT por cima, a equipe e a Visão geral com o filtro do quadro
    assert "/t/campo/responsaveis/usina/1/meta" in html and "/t/campo/responsaveis/pt/PT-1" in html
    assert "/t/campo/responsaveis/equipe" in html and "filtro=perf.abaixo_meta" in html
    assert "filtro=acomp.chamados" in html and "filtro=acomp.rondas" in html and "modo=ranking" in html
    assert "filtro=acomp.ext" in html
    # o chamado abre a tela dele de Garantias por cima (a moldura da ponte), sem sair do Painel
    assert 'id="cr-chamado"' in html and "nexusRota('/os/_nexus/chamado/')" in html
    # o "← Acompanhamento" da tela do chamado abre o quadro no supervisor do Painel (28/10/2026): o filtro guardado
    # na aba, que o quadro do OS Creator relê
    assert 'data-ufv="Ciclano Chefe"' in html and "sessionStorage.setItem('acomp.filtros'" in html
    i = html.index('id="pn-ch-t"')
    ch = html[i:html.index("</section>", i)]
    assert 'data-cr-chamado="' in ch and 'class="pn-grupo"' in ch
    # as listas rolam por dentro do quadro (a barra de rolagem do Nexus); a das PT, na janela, vai inteira
    assert html.count('class="pn-lista') == 6 and 'class="pn-lista pn-lista--jan"' in html


def test_todos_sem_responsavel_segue_nos_cartoes_e_o_painel_de_todos_abre(tela, logado):
    html = logado.get("/t/campo/responsaveis").get_data(as_text=True)
    assert 'class="cn-equipes"' in html and 'class="pn"' not in html             # quem não é responsável: os cartões
    html = logado.get("/t/campo/responsaveis?modo=painel&responsavel=*").get_data(as_text=True)
    assert 'class="pn"' in html and "Todos os responsáveis</h1>" in html


def test_o_responsavel_logado_entra_no_painel_dele(tela, cliente):
    html = _responsavel(cliente).get("/t/campo/responsaveis").get_data(as_text=True)
    assert '<h1 class="cn-titulo">Beltrano Supervisor</h1>' in html and 'aria-current="page">Painel' in html
    assert ">Por responsável</a>" not in html
    # com "Todos" ele fica na Visão geral de todas, como antes
    html = cliente.get("/t/campo/responsaveis?responsavel=*").get_data(as_text=True)
    assert 'aria-current="page">Visão geral' in html and 'class="pn"' not in html


def test_a_janela_dos_extintores_da_usina(tela, logado):
    h = logado.get("/t/campo/responsaveis/usina/1/extintores").get_data(as_text=True)
    assert "Extintores vencidos" in h and ("<th>Extintor</th>" in h or "Nenhum extintor desta usina" in h)
    assert logado.get("/t/campo/responsaveis/usina/1/qualquer").status_code == 404
    # 28/10/2026: a última ronda de extintores ao lado do nome e o relatório da Segurança (PDF e Excel) da usina
    assert 'class="cr-jan-ronda"' in h and ("última ronda de extintores em" in h
                                             or "nenhuma ronda de extintores registrada" in h)
    if 'class="cr-jan-acoes"' in h:
        assert "/t/hseq/extintores/relatorio.pdf?usina=" in h and "/t/hseq/extintores/relatorio.xlsx?usina=" in h


def test_o_relatorio_dos_extintores_da_janela_e_o_da_seguranca(tela, logado):
    """O link da janela leva o PDF e o Excel da usina, os mesmos do Segurança · HSEQ (Levi, 28/10/2026: "que nem
    acontece na parte de segurança")."""
    h = logado.get("/t/campo/responsaveis/usina/1/extintores").get_data(as_text=True)
    for href in re.findall(r'href="(/t/hseq/extintores/relatorio\.(?:pdf|xlsx)\?[^"]+)"', h):
        r = logado.get(href.replace("&amp;", "&"))
        assert r.status_code in (200, 302), href


def test_o_css_da_rolagem_e_da_altura_do_quadro():
    from pathlib import Path
    css = (Path(__file__).resolve().parent.parent / "nexus" / "static" / "campo.css").read_text(encoding="utf-8")
    lista = re.search(r"\.pn-lista\{([^}]*)\}", css).group(1)
    assert "overflow-y:auto" in lista and "scrollbar-color:var(--rolagem)" in lista
    # 6 linhas por vez (Levi, 28/10/2026: "Limite de 6 em 6 com um scroll"), cada uma com a altura fixa
    assert "max-height:calc(6 * var(--pn-linha)" in lista and re.search(r"\.pn-it,\.pn-rk-it\{[^}]*height:var\(--pn-linha\)", css)
    assert ".pn-lista::-webkit-scrollbar-thumb{background:var(--rolagem)" in css
    # o nome da usina preso no alto dos chamados; a janela do chamado só com display quando aberta
    assert re.search(r"\.pn-grupo-cab\{[^}]*position:sticky", css)
    assert ".cr-modal--chamado[open]{display:flex" in css and not re.search(r"\.cr-modal--chamado\{[^}]*display:", css)
    # 29/10/2026: "Padronize o tamanho do card para todas as modalidades": a mesma altura em todos os quadros, a lista
    # que encolhe e rola, e a Performance com duas colunas de largura
    assert re.search(r"\.pn-q\{[^}]*height:var\(--pn-card\)", css) and re.search(r"\.pn\{[^}]*--pn-card:\d+px", css)
    assert ".pn-q--largo{grid-column:span 2}" in css and "min-height:0" in lista
    # a página do Painel 20% menor ("reduza a fonte de toda a página em 20%"), sem mexer nas janelas por cima
    assert ".pn-pagina > :not(dialog):not(template){zoom:.8}" in css


def test_nenhuma_regua_nova():
    """Cada quadro usa a régua da tela dona: a meta é a da Visão gerencial (97/90), a ronda a da Central."""
    assert P.R is R and R.META_NA_META == 97 and R.META_ATENCAO == 90
