"""O Painel do responsável (Levi, 28/10/2026: "quero uma tela feita mesmo para o responsável que não seja um tabelão (...)
uma tela inicial claro"; e, ao ver a 1ª versão: "não podemos deixar nada de fora"): os cinco quadros sobre o que a Visão
do responsável já calcula, completos, e a tela com o banco falso."""
import re

from test_campo_responsaveis import _responsavel, banco, tela  # noqa: F401  (fixtures)

from nexus.campo import painel_responsavel as P
from nexus.campo import responsaveis as R


def _u(uid, nome, ating=None, pr=None, pr_meta=None, ronda=None, chamados=(), pts=(), equipe="SP Norte 01"):
    lista_ch = [{"os": 100 + i, "situacao": s, "dias": d, "equip": "Inversor 1", "fabricante": "Sungrow", "componente": ""}
                for i, (s, d) in enumerate(chamados)]
    return {"usina_id": uid, "usina": nome, "cliente": "Thopen", "equipe": equipe,
            "meta": {"atingimento": ating, "pr": pr, "pr_meta": pr_meta} if ating is not None else None,
            "disp": {"disp": 99.5}, "ronda": ronda or {},
            "chamados": {"abertos": sum(1 for s, _ in chamados if s == "aberto"),
                         "verificacao": sum(1 for s, _ in chamados if s == "verificacao"), "lista": lista_ch},
            "pt": {**R._pt_vazia(), "aguardando": len(pts), "paradas": sum(1 for x in pts if x["parada"]),
                   "lista": list(pts)}, "perf": {"nivel": "ok"}, "acomp": {"nivel": "ok"},
            "nivel": "ok"}


USINAS = [
    _u(1, "Altair", 85.0, ronda={"tipo": "sem_ronda", "dias": 9, "ultima": "2026-10-19", "os": "500"},
       chamados=[("aberto", 26), ("verificacao", 3)],
       pts=[{"numero": "PT-1", "codigo": "A", "idade_min": 30, "parada": False, "hoje": True}]),
    _u(2, "Brodowski 1", 95.0, pr=70.0, pr_meta=80.0, ronda={"dias": 2, "ultima": "2026-10-26", "os": "501"},
       chamados=[("aberto", 300)],
       pts=[{"numero": "PT-2", "codigo": "B", "idade_min": 400, "parada": True, "hoje": True},
            {"numero": "PT-3", "codigo": "C", "idade_min": 3000, "parada": True, "hoje": False}]),
    _u(3, "Coração 1", 101.0, ronda={"tipo": "nunca", "dias": 999}),
    _u(4, "Sem Meta", None, ronda={"tipo": "longa_pendente", "dias": 1, "ultima": "2026-10-27"}),
    _u(5, "Dourados", 70.0, ronda={"dias": 5, "ultima": "2026-10-23"}),
]


def test_performance_traz_todas_as_usinas_da_pior_para_a_melhor():
    p = P.performance(USINAS)
    assert [x["usina"] for x in p["linhas"]] == ["Dourados", "Altair", "Brodowski 1", "Coração 1", "Sem Meta"]
    assert [x["situacao"] for x in p["linhas"]] == ["critico", "critico", "alerta", "ok", "sem_meta"]
    assert (p["usinas"], p["com_meta"], p["abaixo"], p["criticas"], p["na_meta"], p["sem_meta"]) == (5, 4, 3, 2, 1, 1)
    assert p["linhas"][2]["pr_abaixo"] and not p["linhas"][0]["pr_abaixo"]


def test_chamados_e_pts_completos_na_ordem_de_quem_cobra():
    c = P.chamados(USINAS)
    assert (c["abertos"], c["verificacao"], c["usinas"], c["mais_antigo"]) == (2, 1, 2, 300)
    assert [x["usina"] for x in c["linhas"]] == ["Brodowski 1", "Altair"]        # o mais antigo primeiro
    p = P.pts(USINAS)
    # a parada de hoje (técnico parado agora), depois a parada de outro dia, depois a que espera há menos de 2 h
    assert [x["numero"] for x in p["linhas"]] == ["PT-2", "PT-3", "PT-1"]
    assert (p["aguardando"], p["paradas"], p["agora"]) == (3, 2, 1)


def test_rondas_traz_todas_as_usinas_a_que_mais_pede_primeiro():
    r = P.rondas(USINAS)
    assert [x["usina"] for x in r["linhas"]] == ["Coração 1", "Altair", "Sem Meta", "Dourados", "Brodowski 1"]
    assert [x["situacao"] for x in r["linhas"]] == ["nunca", "sem_ronda", "longa_pendente", "em_dia", "em_dia"]
    assert (r["usinas"], r["em_dia"], r["sem_ronda"], r["nunca"], r["longa"], r["em_dia_pct"]) == (5, 2, 1, 1, 1, 40)
    assert r["linhas"][0]["dias"] is None and r["linhas"][1]["os"] == "500"


def test_ranking_todas_as_equipes_da_maior_nota_para_a_menor_e_sem_equipe_no_fim():
    rk = {"total": 9, "cartoes": [
        {"equipe": "B", "nota": 70, "sem_equipe": False}, {"equipe": "Sem equipe", "nota": None, "sem_equipe": True},
        {"equipe": "A", "nota": 93, "sem_equipe": False}, {"equipe": "C", "nota": None, "sem_equipe": False},
        *({"equipe": f"E{i}", "nota": 50 + i, "sem_equipe": False} for i in range(9))]}
    r = P.ranking(rk)
    nomes = [c["equipe"] for c in r["equipes"]]
    assert nomes[:2] == ["A", "B"] and nomes[-2:] == ["C", "Sem equipe"] and len(nomes) == 13    # nada fica de fora
    assert r["total"] == 9


def test_montar_e_o_cabecalho():
    p = P.montar("Ciclano Chefe", USINAS, {"cartoes": [], "total": 0})
    assert (p["nome"], p["usinas"], p["clientes"], p["equipes"]) == ("Ciclano Chefe", 5, ["Thopen"], ["SP Norte 01"])
    assert all(k in p for k in ("perf", "chamados", "pts", "ranking", "rondas"))


# ── a tela, com o banco falso ───────────────────────────────────────────────────────────────────────────────────────
def test_a_tela_do_painel_do_responsavel(tela, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=Ciclano+Chefe").get_data(as_text=True)
    assert 'aria-current="page">Painel' in html and '<h1 class="cn-titulo">Ciclano Chefe</h1>' in html
    for t in ("Usinas abaixo da performance", "Chamados abertos", "PTs pendentes", "Ranking das equipes",
              "Acompanhamento de rondas"):
        assert t in html
    # todas as usinas do responsável na Performance e nas Rondas (Altair e Brodowski 1), nunca a do outro
    for qual in ("pn-perf-t", "pn-rd-t"):
        i = html.index(f'id="{qual}"')
        sec = html[i:html.index("</section>", i)]
        assert "Altair" in sec and "Brodowski 1" in sec and "Coração 1" not in sec
    secoes = re.findall(r'<section class="pn-q.*?</section>', html, re.S)
    assert len(secoes) == 5 and not any(">e mais " in x for x in secoes)         # nada fica de fora
    # o outro nível: o dia a dia da meta, a PT por cima, a equipe e a Visão geral com o filtro do quadro
    assert "/t/campo/responsaveis/usina/1/meta" in html and "/t/campo/responsaveis/pt/PT-1" in html
    assert "/t/campo/responsaveis/equipe" in html and "filtro=perf.abaixo_meta" in html
    assert "filtro=acomp.chamados" in html and "filtro=acomp.rondas" in html and "modo=ranking" in html
    # as listas rolam por dentro do quadro (a barra de rolagem do Nexus)
    assert html.count('class="pn-lista') == 5


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


def test_o_css_da_rolagem_e_da_altura_do_quadro():
    from pathlib import Path
    css = (Path(__file__).resolve().parent.parent / "nexus" / "static" / "campo.css").read_text(encoding="utf-8")
    lista = re.search(r"\.pn-lista\{([^}]*)\}", css).group(1)
    assert "overflow-y:auto" in lista and "scrollbar-color:var(--rolagem)" in lista
    # 6 linhas por vez (Levi, 28/10/2026: "Limite de 6 em 6 com um scroll"), cada uma com a altura fixa
    assert "max-height:calc(6 * var(--pn-linha)" in lista and re.search(r"\.pn-it,\.pn-rk-it\{[^}]*height:var\(--pn-linha\)", css)
    assert ".pn-lista::-webkit-scrollbar-thumb{background:var(--rolagem)" in css


def test_nenhuma_regua_nova():
    """Cada quadro usa a régua da tela dona: a meta é a da Visão gerencial (97/90), a ronda a da Central."""
    assert P.R is R and R.META_NA_META == 97 and R.META_ATENCAO == 90
