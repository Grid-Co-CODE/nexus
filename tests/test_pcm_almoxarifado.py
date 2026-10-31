"""A tela PCM → Almoxarifado (25/10/2026, Levi: "No fractall temos almoxarifado, gostaria de uma visão para a gestão
desse almoxarifado na parte de PCM"). Lê os livros que o App de Campo publica da varredura diária do inventário do
Fracttal e o histórico do Nexus; as contas são as do `nexus/dados/almoxarifado.py`. Desenho:
docs/superpowers/specs/2026-10-25-almoxarifado-design.md. Aqui o banco é de mentira (o `banco` do Campo)."""
import re
from datetime import datetime
from pathlib import Path

import pytest
from test_campo_visao import BRT, _aba, banco  # noqa: F401  (banco é fixture)
from test_pcm_publicar import _no_setor, _pessoa
from test_setor_telas import ANA, _como, setores  # noqa: F401  (setores é fixture)

from nexus.campo import visao
from nexus.dados import almoxarifado as A

INICIO, FIM = "2026-10-25T03:00:12Z", "2026-10-25T03:29:42Z"
ALT = "// Thopen/ Thopen - Altair 1 - SP/"                 # a de-para do `banco` liga a Altair (usina 1)
SEM = "// Nenhuma/ Nenhuma - Usina Z - MT/"                # fora da de-para: não liga
CFG = {"GRIDCO_DB_API": "http://pg.falso", "GRIDCO_SQL_TOKEN": "t", "NEXUS_ALMOX_GRAVAR": "1"}


def _item(i, cod, nome, un, fam, av="Não", lido="Sim"):
    return {"ID do item": str(i), "Código": cod, "Nome": nome, "Unidade": un, "Família": fam, "Avariado": av,
            "Ferramenta": "Não", "Início do ciclo": INICIO, "Lido": lido}


def _s(i, almox, local, saldo, minimo, inicio=INICIO):
    return {"ID do item": str(i), "Código": f"SP-{i}", "ID do almoxarifado": str(almox),
            "Almoxarifado": f"Almoxarifado {almox}", "Local do almoxarifado": local, "Saldo": saldo, "Mínimo": minimo,
            "Início do ciclo": inicio}


def _p(lid, item, almox, situacao, motivo=""):
    return {"ID do lançamento": lid, "Recebido em": "2026-10-24T13:10:00Z", "Usada em": "2026-10-24T12:58:00Z",
            "OS": "16885", "Tarefa": "[Grid Co.] - MPM - Inversor", "Código do ativo": "ALT100-INV1",
            "ID do item": str(item), "Código": f"SP-{item}", "ID do almoxarifado": str(almox), "Quantidade": 2,
            "Unidade": "UNIDADE", "Situação": situacao, "Motivo da recusa": motivo, "Lançado por (HMAC)": ""}


def _semear(api, saldo_inicio=INICIO, inicio=INICIO, total=10, nao_lidos=(4,), itens_faltando=0, saldo_extra=(),
            novas=None, custo=None, avariados=(), codigos=None, so_colunas=None):
    """Os 4 livros do App coerentes: `total` itens na lista (1 a 4 com nome; os outros sem saldo), os de `nao_lidos`
    com Lido = Não (o 4, por padrão: 9 de 10 lidos, acima dos 90%). `novas` (30/10/2026) é o App com as colunas novas:
    {id do item: (criticidade, curva)} vai para Criticidade e Curva ABC do Itens (o item fora do dicionário leva vazio),
    e `custo` {(id do item, id do almoxarifado): custo} para o Custo unitário do Saldo. Sem `novas`, o livro de hoje,
    SEM as três colunas (coluna ausente não é coluna vazia). `avariados`: os itens com a marca Avariado = Sim; `codigos`:
    {id do item: código} para trocar o código do catálogo (o "-AV" sem marca, o "SP-AVR-001" que não é avariada).
    `so_colunas` (com `novas`): o App que manda só uma das duas colunas do Itens, ("Curva ABC",) ou ("Criticidade",)."""
    nomes = {1: ("SP-1", "Fusível 10A", "UNIDADE", "Proteção", "Não"), 2: ("SP-2", "Cabo 6 mm", "METRO", "Cabos", "Não"),
             3: ("SP-3-AV", "[AVARIADO] Disjuntor", "UNIDADE", "Proteção", "Sim"),
             4: ("SP-4", "Relé de proteção", "UNIDADE", "Proteção", "Não")}
    itens = [_item(i, *nomes.get(i, (f"SP-{i}", f"Peça {i}", "UNIDADE", "Cabos", "Não"))[:4],
                   av=nomes.get(i, ("", "", "", "", "Não"))[4], lido="Não" if i in nao_lidos else "Sim")
             for i in range(1, total + 1)]
    for it in itens:
        it["Início do ciclo"] = inicio
    saldo = [_s(1, 10, ALT, 1, 3, saldo_inicio),          # abaixo: falta 2
             _s(2, 10, ALT, 5, 5, saldo_inicio),          # no limite
             _s(1, 20, SEM, 4, 0, saldo_inicio),          # sem mínimo
             _s(3, 20, SEM, 2, 1, saldo_inicio),          # avariada com saldo
             _s(2, 20, SEM, 0, 0, saldo_inicio)] + list(saldo_extra)        # zerada
    for it in itens:
        if int(it["ID do item"]) in avariados:
            it["Avariado"] = "Sim"
        if int(it["ID do item"]) in (codigos or {}):
            it["Código"] = codigos[int(it["ID do item"])]
    if novas is not None:
        for it in itens:
            it["Criticidade"], it["Curva ABC"] = novas.get(int(it["ID do item"]), ("", ""))
        for sl in saldo:
            sl["Custo unitário"] = (custo or {}).get((int(sl["ID do item"]), int(sl["ID do almoxarifado"])), "")
        if so_colunas is not None:
            for it in itens:
                for col in ("Criticidade", "Curva ABC"):
                    if col not in so_colunas:
                        del it[col]
    _aba(api, A.LIVRO_CICLO, A.ABA_CICLO, [{"Início do ciclo": inicio, "Fim do ciclo": FIM,
                                             "Itens na lista do Fracttal": total,
                                             "Itens lidos": total - len([i for i in nao_lidos if i <= total]),
                                             "Erros": 0, "Origem": "automático", "Linhas de saldo": len(saldo)}])
    _aba(api, A.LIVRO_ITENS, A.ABA_ITENS, itens[:len(itens) - itens_faltando])
    _aba(api, A.LIVRO_SALDO, A.ABA_SALDO, saldo)
    _aba(api, A.LIVRO_PECAS, A.ABA_PECAS, [_p("A", 1, 10, "lançada"),
                                          _p("B", 2, 20, "recusada", "chave recusada pelo Fracttal")])


@pytest.fixture
def almox(banco, monkeypatch):
    monkeypatch.setattr(visao, "_agora", lambda: datetime(2026, 10, 25, 10, 0, tzinfo=BRT))
    _semear(banco)
    visao.limpar()
    return banco


def _abrir(app, monkeypatch, setor="PCM"):
    _no_setor(monkeypatch, setor)
    return _pessoa(app).get("/t/pcm/pecas")


def test_sem_o_livro_do_app(app, banco, monkeypatch):
    r = _abrir(app, monkeypatch)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "O App ainda não publica o almoxarifado" in html
    assert "data-alm-kpi" not in html


def test_kpis_e_reposicao(app, almox, monkeypatch):
    from nexus.pcm import almoxarifado as T
    d = T.montar().dados
    assert d["estado"] == "ok"
    k = d["kpis"]
    assert (k["almoxarifados"], k["com_saldo"], k["abaixo"], k["no_limite"], k["sem_minimo"], k["avariadas"]) == \
        (2, 3, 1, 1, 2, 1)
    assert (k["lancadas"], k["recusadas"]) == (1, 1)
    rep = d["reposicao"]
    assert [(r["codigo"], r["situacao"]) for r in rep] == [("SP-1", "abaixo"), ("SP-2", "no_limite")]
    assert rep[0]["falta"] == 2 and rep[0]["usina"] == "Altair"
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    assert "Reposição" in html and "Fusível 10A" in html and "saldo do Fracttal de 25/10, 00:29" in html


def test_usina_nao_ligada(app, almox, monkeypatch):
    from nexus.pcm import almoxarifado as T
    cards = {c["id"]: c for c in T.montar().dados["por_almoxarifado"]}
    assert cards["10"]["usina"] == "Altair" and cards["20"]["usina"] is None
    assert (cards["20"]["pecas"], cards["20"]["sem_minimo"], cards["20"]["zeradas"]) == (3, 2, 1)
    assert "usina não ligada" in _abrir(app, monkeypatch).get_data(as_text=True)


def test_item_nao_lido(app, almox, monkeypatch):
    from nexus.pcm import almoxarifado as T
    cat = {c["codigo"]: c for c in T.montar().dados["catalogo"]}
    assert cat["SP-4"]["nao_lido"] and cat["SP-1"]["total"] == 5.0
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    assert "não lido neste ciclo" in html


def test_recusadas_em_cadastro_a_corrigir(app, almox, monkeypatch):
    from nexus.pcm import almoxarifado as T
    cad = T.montar().dados["cadastro"]
    assert [r["codigo"] for r in cad["recusadas"]] == ["SP-2"] and "avariadas" not in cad      # a avariada tem aba própria
    assert {(s["almoxarifado"], s["n"]) for s in cad["sem_minimo"]} == {("Almoxarifado 20", 2)}
    assert "corrigir no Fracttal" in _abrir(app, monkeypatch).get_data(as_text=True)


def test_consumo_sem_o_fato_le_o_livro_do_app(app, almox, monkeypatch):
    from nexus.pcm import almoxarifado as T
    d = T.montar().dados
    assert d["consumo_fonte"] == "app" and [c["situacao"] for c in d["consumo"]] == ["lançada", "recusada"]
    assert "o histórico ainda não é gravado: mostrando os 90 dias do App" in _abrir(app, monkeypatch).get_data(as_text=True)


def test_consumo_le_o_fato_do_nexus_quando_ele_existe(app, almox, monkeypatch):
    from nexus.dados import carga
    from nexus.pcm import almoxarifado as T
    carga.gerar_almoxarifado(CFG, almox)
    visao.limpar()
    d = T.montar().dados
    assert d["consumo_fonte"] == "nexus" and len(d["consumo"]) == 2 and d["consumo"][1]["recusa"]


def test_livros_incoerentes_mostram_o_ultimo_aplicado(app, almox, monkeypatch):
    from nexus.dados import carga
    from nexus.pcm import almoxarifado as T
    carga.gerar_almoxarifado(CFG, almox)                                   # o Nexus guardou o ciclo de 25/10
    _semear(almox, saldo_inicio="2026-10-26T03:00:05Z")                    # Saldo de outro ciclo
    visao.limpar()
    d = T.montar().dados
    assert d["estado"] == "ok" and d["aviso"].startswith("Os livros do App chegaram de ciclos diferentes")
    assert "25/10, 00:00" in d["aviso"] and d["kpis"]["abaixo"] == 1


def test_incoerente_sem_ciclo_no_nexus_nao_mostra_numero(app, almox, monkeypatch):
    from nexus.pcm import almoxarifado as T
    _semear(almox, saldo_inicio="2026-10-26T03:00:05Z")
    visao.limpar()
    d = T.montar().dados
    assert d["estado"] == "incoerente" and "kpis" not in d
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    assert "Os livros do App chegaram de ciclos diferentes" in html and "data-alm-kpi" not in html


def test_ciclo_incompleto_tambem_fica_no_ultimo_bom(app, almox, monkeypatch):
    from nexus.pcm import almoxarifado as T
    _semear(almox, nao_lidos=(3, 4, 5, 6, 7, 8, 9, 10))                   # 2 de 10 lidos
    visao.limpar()
    assert T.montar().dados["estado"] == "incoerente"


def test_ciclo_velho_avisa(app, almox, monkeypatch):
    from nexus.pcm import almoxarifado as T
    monkeypatch.setattr(visao, "_agora", lambda: datetime(2026, 10, 27, 10, 0, tzinfo=BRT))
    visao.limpar()
    d = T.montar().dados
    assert d["estado"] == "ok" and "a varredura do App não publicou desde então" in d["aviso"]
    assert d["kpis"]["abaixo"] == 1


def test_tela_so_do_setor_pcm(app, logado, setores):  # noqa: F811
    """O setor dono é o PCM (outros setores, pela marca em Base → Acessos); o endereço é o do placeholder de antes."""
    from nexus.torres.pcm import TORRE
    t = TORRE.tela("pecas")
    assert t.do_setor == "PCM" and t.nome == "Almoxarifado"
    assert _como(app, ANA).get("/t/pcm/pecas").status_code == 403           # a Ana é da Performance


def test_sem_cor_fora_de_token():
    t = (Path(__file__).resolve().parent.parent / "nexus" / "templates" / "pcm" / "almoxarifado.html").read_text("utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", t) and "rgba(" not in t


# ── a revisão final (25/10/2026): cada teste reproduz um achado e falhou antes do conserto ──────────────────────────

def _guardar_ciclo(api):
    """O Nexus guarda o ciclo de 25/10 (a carga do histórico, com a gravação ligada)."""
    from nexus.dados import carga
    carga.gerar_almoxarifado(CFG, api)
    visao.limpar()


def test_rev_i1_livros_incompletos_vao_para_a_reserva(app, almox, monkeypatch):
    from nexus.pcm import almoxarifado as T
    _semear(almox, itens_faltando=1)
    visao.limpar()
    d = T.montar().dados
    assert d["estado"] == "incoerente" and "incompletos" in d["aviso"]


def test_rev_i1_queda_de_itens_avisa(app, almox, monkeypatch):
    from nexus.pcm import almoxarifado as T
    _guardar_ciclo(almox)                                                  # 10 itens na lista
    _semear(almox, inicio="2026-10-25T18:00:00Z", saldo_inicio="2026-10-25T18:00:00Z", total=4, nao_lidos=())
    visao.limpar()
    d = T.montar().dados
    assert d["estado"] == "ok" and "6 a menos" in d["aviso"]


def test_rev_i2_saldo_vazio_nao_entra_na_conta(app, almox, monkeypatch):
    from nexus.pcm import almoxarifado as T
    _semear(almox, saldo_extra=[_s(4, 10, ALT, "", 2)])                   # o Fracttal não deu o saldo
    visao.limpar()
    d = T.montar().dados
    assert [r["codigo"] for r in d["reposicao"]] == ["SP-1", "SP-2"] and d["kpis"]["abaixo"] == 1
    card = {c["id"]: c for c in d["por_almoxarifado"]}["10"]
    assert card["zeradas"] == 0 and card["nao_informado"] == 1
    assert _abrir(app, monkeypatch).status_code == 200


def test_rev_i3_reserva_so_mostra_os_itens_da_foto(app, almox, monkeypatch):
    from nexus.pcm import almoxarifado as T
    _guardar_ciclo(almox)
    _semear(almox, saldo_inicio="2026-10-26T03:00:05Z")                    # o App com livros de ciclos diferentes
    visao.limpar()
    d = T.montar().dados
    assert {c["codigo"] for c in d["catalogo"]} == {"SP-1", "SP-2", "SP-3-AV"} and d["kpis"]["avariadas"] == 1


def test_rev_i5_busca_sem_acento_e_sem_caixa(app, almox, monkeypatch):
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    assert 'data-f-busca="sp-1 fusivel 10a"' in html


def test_rev_i6_ciclo_anulado_sai_da_tela(app, almox, monkeypatch):
    from nexus.dados import carga
    from nexus.pcm import almoxarifado as T
    _guardar_ciclo(almox)
    carga.anular_ciclo_almox(CFG, INICIO, almox, gravar=True)
    visao.limpar()
    d = T.montar().dados
    assert d["estado"] == "incoerente" and "anulado" in d["aviso"]


# ── 30/10/2026, itens 7 e 8: o filtro conta a aba à vista, o saldo unitário e a Reposição por criticidade e curva ─────

def test_saldo_unitario_sai_do_limite(app, almox, monkeypatch):
    """Mínimo 1 e saldo 1 é o ruído do "no limite" (a próxima saída zera, mas não é pedido de compra por si): vai para o
    grupo próprio. O saldo 2 e mínimo 2 segue no limite."""
    from nexus.pcm import almoxarifado as T
    _semear(almox, saldo_extra=[_s(5, 10, ALT, 1, 1), _s(6, 10, ALT, 2, 2)])
    visao.limpar()
    d = T.montar().dados
    sit = {l["codigo"]: l["situacao"] for l in d["linhas"]}
    assert sit["SP-5"] == "saldo_unitario" and sit["SP-6"] == "no_limite"
    assert [r["codigo"] for r in d["reposicao"]] == ["SP-1", "SP-2", "SP-6"]
    assert [r["codigo"] for r in d["saldo_unitario"]] == ["SP-5"]
    k = d["kpis"]
    assert (k["abaixo"], k["no_limite"], k["saldo_unitario"]) == (1, 2, 1)
    assert {c["id"]: c for c in d["por_almoxarifado"]}["10"]["saldo_unitario"] == 1
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    assert "+1 de saldo unitário" in html
    assert "uma peça e mínimo 1: a próxima saída zera, mas não é pedido de compra por si" in html


def test_reposicao_ordena_dentro_do_grupo(app, almox, monkeypatch):
    """O grupo vem antes (abaixo, no limite, saldo unitário); dentro dele a criticidade (1.Crítico primeiro), a curva (A,
    B, C e sem curva por último) e, por fim, a falta. Um crítico no limite não passa à frente de um comum abaixo."""
    from nexus.pcm import almoxarifado as T
    novas = {5: ("1.Crítico", "B"), 6: ("1.Crítico", "A"), 7: ("1.Crítico", ""), 8: ("", "A"), 9: ("1.Crítico", "A"),
             10: ("1.Crítico", "A")}
    extra = [_s(5, 10, ALT, 4, 5),        # abaixo, falta 1: crítico, curva B
             _s(6, 10, ALT, 4, 5),        # abaixo, falta 1: crítico, curva A
             _s(7, 10, ALT, 0, 9),        # abaixo, falta 9: crítico, sem curva
             _s(8, 10, ALT, 0, 5),        # abaixo, falta 5: comum, curva A
             _s(9, 10, ALT, 0, 3),        # abaixo, falta 3: crítico, curva A (a falta desempata com o SP-6)
             _s(10, 10, ALT, 3, 3)]       # no limite: crítico, curva A
    _semear(almox, saldo_extra=extra, novas=novas)
    visao.limpar()
    d = T.montar().dados
    assert [r["codigo"] for r in d["reposicao"]] == ["SP-9", "SP-6", "SP-5", "SP-7", "SP-8", "SP-1", "SP-10", "SP-2"]
    l9 = next(l for l in d["linhas"] if l["codigo"] == "SP-9")
    assert (l9["criticidade"], l9["crit_n"], l9["curva"]) == ("1.Crítico", 1, "A")
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    assert 'class="inv-crit inv-crit--1"' in html           # o quadradinho que a Aprovação do inventário já usa


def test_livro_de_hoje_sem_colunas_novas(app, almox, monkeypatch):
    """O Nexus sobe antes do App: sem as colunas, a ordem é a de hoje, as colunas mostram "–" e nada é inventado (nem
    "C" nem custo 0). Coluna ausente não é coluna vazia: o Cadastro a corrigir não cobra o que o App ainda não traz."""
    from nexus.pcm import almoxarifado as T
    d = T.montar().dados
    assert all(l["criticidade"] == "" and l["curva"] == "" and l["custo"] is None and l["crit_n"] is None
               for l in d["linhas"])
    assert (d["tem_criticidade"], d["tem_curva"], d["tem_custo"]) == (False, False, False)
    assert [r["codigo"] for r in d["reposicao"]] == ["SP-1", "SP-2"]
    assert d["cadastro"]["sem_curva"] is None and d["cadastro"]["sem_criticidade"] is None
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    assert "com saldo sem Curva ABC" not in html and "com saldo sem criticidade" not in html


def test_cadastro_sem_curva_e_sem_criticidade(app, almox, monkeypatch):
    """Com as colunas, a peça COM saldo e sem curva (ou sem criticidade) pede o cadastro no Fracttal: completar é lá."""
    from nexus.pcm import almoxarifado as T
    _semear(almox, novas={1: ("1.Crítico", ""), 3: ("2.Necessário", "A")})      # o 2 não tem nada; o 4 não tem saldo
    visao.limpar()
    d = T.montar().dados
    assert (d["tem_criticidade"], d["tem_curva"], d["tem_custo"]) == (True, True, True)
    assert d["cadastro"]["sem_curva"] == 2 and d["cadastro"]["sem_criticidade"] == 1
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    assert "2 peças com saldo sem Curva ABC no Fracttal" in html
    assert "1 peça com saldo sem criticidade no Fracttal" in html


def test_a_troca_de_aba_refaz_o_filtro(app, almox, monkeypatch):
    """O script das abas disparava `input` no formulário, que o filtro-local.js não escuta (ele ouve o `change` dos select
    e o `input` do campo de texto): os números do filtro ficavam os da aba anterior. A troca chama o `aplicar` e a barra
    some nas abas sem tabela."""
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    assert "FiltroLocal['alm-f'].aplicar" in html and "data-alm-filtro" in html
    assert "dispatchEvent(new Event('input'" not in html
    css = (Path(__file__).resolve().parent.parent / "nexus" / "static" / "pcm.css").read_text("utf-8")
    assert ".alm-filtros[hidden]" in css          # o `.cn-filtros{display:flex}` vence o [hidden] do navegador


def test_reserva_com_e_sem_as_colunas_novas(app, almox, monkeypatch):
    """Na reserva (o último ciclo aplicado no Nexus) a chave da coluna não diz se o App a mandou: a carga grava as colunas
    novas, vazias, mesmo com o livro do App de antes. "Tem" é ao menos uma peça com valor no histórico."""
    from nexus.pcm import almoxarifado as T
    _guardar_ciclo(almox)                                                  # o histórico de hoje, sem as colunas
    _semear(almox, saldo_inicio="2026-10-26T03:00:05Z")                    # o App com livros de ciclos diferentes
    visao.limpar()
    d = T.montar().dados
    assert d["estado"] == "ok" and (d["tem_criticidade"], d["tem_curva"], d["tem_custo"]) == (False, False, False)
    assert all(l["curva"] == "" and l["custo"] is None for l in d["linhas"])
    assert d["cadastro"]["sem_curva"] is None
    nova = "2026-10-25T18:00:00Z"                                          # outro ciclo, agora com as colunas novas
    _semear(almox, inicio=nova, saldo_inicio=nova, novas={3: ("2.Necessário", "A")}, custo={(3, 20): 12.5})
    _guardar_ciclo(almox)
    _semear(almox, inicio=nova, saldo_inicio="2026-10-26T03:00:05Z", novas={3: ("2.Necessário", "A")})
    visao.limpar()
    d = T.montar().dados
    l3 = next(l for l in d["linhas"] if l["codigo"] == "SP-3-AV")
    assert d["estado"] == "ok" and (d["tem_criticidade"], d["tem_curva"], d["tem_custo"]) == (True, True, True)
    assert (l3["criticidade"], l3["crit_n"], l3["curva"], l3["custo"]) == ("2.Necessário", 2, "A", 12.5)
    assert d["cadastro"]["sem_curva"] == 2          # o SP-1 e o SP-2 têm saldo e o Fracttal não deu curva


# ── 30/10/2026, item 6: a aba Avariadas, parada há quanto tempo ──────────────────────────────────────────────────────────

def _historico(api, ciclos, codigo="SP-3-AV", item="3", almox="20", sem_foto=()):
    """O histórico do Nexus montado à mão: `ciclos` = [(início "AAAA-MM-DD", saldo da peça no almoxarifado, anulado)], todos
    aplicados, cada um com a sua foto do Saldo no livro do mês. `saldo` None = a peça não está na foto do ciclo. `sem_foto`:
    os dias cujo ciclo foi aplicado mas o livro do mês NÃO trouxe nenhuma linha dele (o livro que não veio)."""
    from nexus.dados import fato_almoxarifado as F
    cab_ciclo, por_mes = [], {}
    for dia, saldo, anulado in ciclos:
        inicio, data_id = f"{dia}T03:00:00Z", int(dia.replace("-", ""))
        cab_ciclo.append(dict(zip(F.CAB_CICLO, [inicio, data_id, f"{dia}T03:25:00Z", 10, 9, 0, "automático", "aplicado", "",
                                                1 if anulado else 0, f"{dia}T04:00:00Z", 1])))
        foto = [dict(zip(F.CAB_SALDO, [f"s{data_id}{i}", inicio, data_id, str(i), f"SP-{i}", "10", 1, "de-para do Fracttal",
                                       5, 3, ""])) for i in (1, 2)]               # duas peças que nunca saem do lugar
        if dia in sem_foto:
            foto = []
        elif saldo is not None:
            foto.append(dict(zip(F.CAB_SALDO, [f"s{data_id}x", inicio, data_id, item, codigo, almox, None, None, saldo, 0,
                                               ""])))
        por_mes.setdefault(F.livro_do_mes(data_id), []).extend(foto)
    _aba(api, F.LIVRO, F.ABA_CICLO, cab_ciclo)
    for livro, linhas in por_mes.items():
        _aba(api, livro, F.ABA_SALDO, linhas)


def _hoje(monkeypatch, dia):
    monkeypatch.setattr(visao, "_agora", lambda: datetime(2026, 10, dia, 10, 0, tzinfo=BRT))
    visao.limpar()


def _dados():
    from nexus.pcm import almoxarifado as T
    return T.montar().dados


def test_avariada_parada_ha_n_dias(app, almox, monkeypatch):
    """O saldo dela acima de zero sem interrupção, pelos ciclos aplicados: 0 em 01/10, 2 em 15/10 e 2 em 29/10 é parada
    desde 15/10 (a primeira foto com saldo), e hoje, 30/10, são 15 dias."""
    _historico(almox, [("2026-10-01", 0, False), ("2026-10-15", 2, False), ("2026-10-29", 2, False)])
    _hoje(monkeypatch, 30)
    av = _dados()["avariadas"]
    assert [(a["codigo"], a["almox"], a["saldo"], a["dias"], a["desde"], a["pelo_menos"]) for a in av] == \
        [("SP-3-AV", "Almoxarifado 20", 2, 15, "15/10/2026", False)]
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    assert 'data-painel="avariadas"' in html and "há 15 dias" in html and "desde 15/10/2026" in html


def test_avariada_desde_o_inicio_diz_pelo_menos(app, almox, monkeypatch):
    """Com saldo desde o primeiro ciclo do histórico, a data de entrada não se sabe: "há pelo menos N dias" e a data em que
    o histórico começa. Nunca se inventa a entrada."""
    _historico(almox, [("2026-10-01", 3, False), ("2026-10-15", 2, False), ("2026-10-29", 2, False)])
    _hoje(monkeypatch, 30)
    a = _dados()["avariadas"][0]
    assert (a["dias"], a["pelo_menos"], a["desde"], a["inicio"]) == (29, True, "01/10/2026", "01/10/2026")
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    assert "há pelo menos 29 dias" in html and "o histórico começa em 01/10/2026" in html


def test_ciclo_anulado_nao_conta(app, almox, monkeypatch):
    """O ciclo anulado do meio (saldo 0) não interrompe a parada, e o anulado do começo (saldo 5) não a estende nem faz
    parte do histórico: sem ele, o primeiro ciclo é o de 08/10."""
    _historico(almox, [("2026-10-01", 5, True), ("2026-10-08", 2, False), ("2026-10-12", 0, True),
                       ("2026-10-15", 2, False), ("2026-10-29", 2, False)])
    _hoje(monkeypatch, 30)
    a = _dados()["avariadas"][0]
    assert (a["desde"], a["dias"], a["pelo_menos"], a["inicio"]) == ("08/10/2026", 22, True, "08/10/2026")


def test_a_parada_recomeca_depois_do_saldo_zero_ou_fora_da_foto(app, almox, monkeypatch):
    """A peça que saiu da foto (ou voltou a zero) e reapareceu começa de novo: a parada é a do saldo SEM interrupção. E o
    ciclo de setembro está noutro livro de mês, que também é lido."""
    _historico(almox, [("2026-09-20", 2, False), ("2026-09-30", None, False), ("2026-10-10", 2, False),
                       ("2026-10-29", 2, False)])
    _hoje(monkeypatch, 30)
    a = _dados()["avariadas"][0]
    assert (a["desde"], a["dias"], a["pelo_menos"]) == ("10/10/2026", 20, False)


def test_avariada_pela_marca_e_pelo_av(app, almox, monkeypatch):
    """Uma definição só, a do `regua.avariada`: o código com -AV no fim OU a marca Avariado do catálogo. O "AV" no meio de
    outra palavra (SP-AVR-001) não conta."""
    extra = [_s(6, 10, ALT, 4, 2), _s(9, 10, ALT, 1, 2), _s(10, 10, ALT, 3, 2)]
    _semear(almox, saldo_extra=extra, avariados=(9,), codigos={6: "SP-6-AV", 9: "SP-9", 10: "SP-AVR-001"})
    visao.limpar()
    d = _dados()
    assert sorted(a["codigo"] for a in d["avariadas"]) == ["SP-3-AV", "SP-6-AV", "SP-9"]
    assert d["kpis"]["avariadas"] == 3
    assert {l["codigo"]: l["avariada"] for l in d["linhas"] if l["id_item"] in ("3", "6", "9", "10")} == \
        {"SP-3-AV": True, "SP-6-AV": True, "SP-9": True, "SP-AVR-001": False}


def test_avariada_sai_do_cadastro_a_corrigir(app, almox, monkeypatch):
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    cadastro = html[html.index('data-painel="cadastro"'):]
    assert "avariada com saldo" not in cadastro and "SP-3-AV" not in cadastro


def test_kpi_avariadas_conta_com_saldo(app, almox, monkeypatch):
    """O número do alto contava o catálogo inteiro (3 avariadas); passa a contar o que a aba lista: peça × almoxarifado com
    saldo (aqui, 1). O cartão leva à aba."""
    _semear(almox, avariados=(9,), codigos={6: "SP-6-AV", 9: "SP-9"})          # o 6 e o 9 não têm linha de saldo
    visao.limpar()
    d = _dados()
    assert sum(1 for c in d["catalogo"] if c["avariado"]) == 3 and d["kpis"]["avariadas"] == 1
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    assert ">com saldo</span>" in html and "Avariadas (1)" in html
    assert len(re.findall(r'data-aba="avariadas"', html)) == 2                  # o cartão do alto e a aba


def test_sem_historico_avariada_sem_dias(app, almox, monkeypatch):
    """Sem ciclo aplicado no Nexus (o ensaio) não há de onde tirar a data: dias vazio, e a tela diz que não tem histórico."""
    a = _dados()["avariadas"][0]
    assert a["codigo"] == "SP-3-AV" and a["dias"] is None and a["desde"] == "" and a["pelo_menos"] is False
    assert "sem histórico ainda" in _abrir(app, monkeypatch).get_data(as_text=True)


def test_valor_da_avariada_so_com_custo(app, almox, monkeypatch):
    """O valor é saldo × custo unitário quando o livro traz o custo e o Fracttal o deu; sem isso, vazio ("–"), nunca 0."""
    assert _dados()["avariadas"][0]["valor"] is None
    assert '<th class="num">Valor</th>' not in _abrir(app, monkeypatch).get_data(as_text=True)
    _semear(almox, novas={}, custo={(3, 20): 12.5})
    visao.limpar()
    assert _dados()["avariadas"][0]["valor"] == 25.0
    assert "R$ 25,00" in _abrir(app, monkeypatch).get_data(as_text=True)
    _semear(almox, novas={})                                                  # a coluna existe, o Fracttal não deu custo
    visao.limpar()
    a = _dados()["avariadas"][0]
    assert a["valor"] is None and a["custo"] is None
    assert "R$ 0" not in _abrir(app, monkeypatch).get_data(as_text=True)


def test_avariada_parada_ha_um_dia_e_desde_hoje(app, almox, monkeypatch):
    """O plural: "há 1 dia" (não "1 dias"), com e sem o "pelo menos", e o dia 0 é "desde hoje"."""
    _historico(almox, [("2026-10-20", 0, False), ("2026-10-29", 2, False)])
    _hoje(monkeypatch, 30)
    a = _dados()["avariadas"][0]
    assert (a["dias"], a["pelo_menos"], a["desde"]) == (1, False, "29/10/2026")
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    assert "há 1 dia<" in html and "1 dias" not in html and "desde 29/10/2026" in html
    _historico(almox, [("2026-10-29", 2, False)])                      # sem ciclo antes: o "pelo menos"
    visao.limpar()
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    assert "há pelo menos 1 dia<" in html and "1 dias" not in html
    _historico(almox, [("2026-10-20", 0, False), ("2026-10-29", 2, False)])
    _hoje(monkeypatch, 29)                                             # o ciclo é de hoje
    a = _dados()["avariadas"][0]
    assert (a["dias"], a["pelo_menos"]) == (0, False)
    assert "desde hoje" in _abrir(app, monkeypatch).get_data(as_text=True)


def test_ciclo_aplicado_sem_linha_no_livro_do_mes_e_pulado(app, almox, monkeypatch):
    """O ciclo aplicado cujo livro do mês não trouxe nenhuma linha (o livro que não veio) não interrompe a parada nem vale
    como o começo do histórico: o que não foi medido não vira "saldo zero"."""
    _historico(almox, [("2026-10-01", 2, False), ("2026-10-15", 2, False), ("2026-10-29", 2, False)],
               sem_foto=("2026-10-15",))
    _hoje(monkeypatch, 30)
    a = _dados()["avariadas"][0]
    assert (a["desde"], a["dias"], a["pelo_menos"]) == ("01/10/2026", 29, True)          # o 15/10 não interrompeu
    _historico(almox, [("2026-10-01", 2, False), ("2026-10-15", 2, False), ("2026-10-29", 2, False)],
               sem_foto=("2026-10-01",))
    _hoje(monkeypatch, 30)
    a = _dados()["avariadas"][0]
    assert (a["desde"], a["pelo_menos"], a["inicio"]) == ("15/10/2026", True, "15/10/2026")   # o histórico começa no 15/10


def test_saldo_unitario_vem_fechado(app, almox, monkeypatch):
    """O `<details>` do saldo unitário não leva `open`: fechado por padrão (a peça de uma unidade não esconde o resto)."""
    _semear(almox, saldo_extra=[_s(5, 10, ALT, 1, 1)])
    visao.limpar()
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    assert '<details class="alm-unit">' in html and 'class="alm-unit" open' not in html


def _celula(html, rotulo, depois=0):
    """O texto de uma célula `data-r="rotulo"` da Reposição (a `depois`-ésima a partir da 1ª)."""
    achados = re.findall(r'<td data-r="%s"[^>]*><span class="alm-v">(.*?)</span></td>' % re.escape(rotulo), html, re.S)
    return achados[depois]


def test_crit_e_curva_sem_coluna_mostram_traco(app, almox, monkeypatch):
    """O livro de hoje não tem as colunas: "–" nas duas, e o `title` diz que é o App que ainda não traz (não que a peça
    esteja sem no Fracttal)."""
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    crit, curva = _celula(html, "Crit."), _celula(html, "Curva")
    assert "–" in crit and "o App ainda não traz a criticidade" in crit and "inv-crit" not in crit
    assert "–" in curva and "o App ainda não traz a curva" in curva and "alm-curva" not in curva
    # com as colunas e a peça sem valor: a causa é outra, e o `title` diz
    _semear(almox, novas={})
    visao.limpar()
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    assert "sem criticidade no Fracttal" in _celula(html, "Crit.") and "sem curva no Fracttal" in _celula(html, "Curva")


def test_ajuda_da_reposicao_diz_qual_coluna_o_app_nao_traz(app, almox, monkeypatch):
    """Uma linha visível por coluna ausente (e não só no `title` do traço): as duas, só a criticidade ou só a curva."""
    def ajuda():
        return re.search(r'data-painel="reposicao".*?</p>', _abrir(app, monkeypatch).get_data(as_text=True), re.S).group(0)
    assert "O App ainda não traz a criticidade nem a curva" in ajuda()
    _semear(almox, novas={1: ("1.Crítico", "A")}, so_colunas=("Criticidade",))
    visao.limpar()
    h = ajuda()
    assert "O App ainda não traz a curva:" in h and "ainda não traz a criticidade" not in h
    _semear(almox, novas={1: ("1.Crítico", "A")}, so_colunas=("Curva ABC",))
    visao.limpar()
    h = ajuda()
    assert "O App ainda não traz a criticidade:" in h and "ainda não traz a curva" not in h
    _semear(almox, novas={1: ("1.Crítico", "A")})
    visao.limpar()
    assert "O App ainda não traz" not in ajuda()


# ── 30/10/2026, itens 1 e 9: abrir um almoxarifado mostra as peças, a última contagem gravada e o valor por curva ─────────

def _cartao(html, nome):
    """O `<article>` do cartão do almoxarifado `nome` na aba Por almoxarifado."""
    achados = [a.split("</article>")[0] for a in html.split('<article class="alm-card')[1:]
               if f"<h3>{nome}</h3>" in a.split("</article>")[0]]
    assert achados, f"sem cartão de {nome}"
    return achados[0]


def _codigos(html):
    return re.findall(r'<td data-r="Código" class="alm-cod"><span class="alm-v">(.*?)</span>', html)


def _pecas(app, monkeypatch, id_almox="10"):
    _no_setor(monkeypatch, "PCM")
    return _pessoa(app).get(f"/t/pcm/pecas/almox/{id_almox}")


def test_ver_pecas_do_almoxarifado(app, almox, monkeypatch):
    """A rota devolve só as peças daquele almoxarifado, abaixo → no limite → saldo unitário → sem mínimo → ok → sem saldo
    informado e, dentro de cada grupo, a criticidade (1.Crítico primeiro) e a curva. A mesma `montar()` da tela."""
    extra = [_s(5, 10, ALT, 1, 1),            # saldo unitário
             _s(6, 10, ALT, 4, 0),            # sem mínimo
             _s(7, 10, ALT, 9, 2),            # ok
             _s(8, 10, ALT, 0, 2),            # abaixo, falta 2: crítico
             _s(9, 10, ALT, "", 2),           # o Fracttal não deu o saldo
             _s(10, 10, ALT, 3, 3)]           # no limite: crítico
    _semear(almox, saldo_extra=extra, novas={1: ("2.Necessário", "B"), 8: ("1.Crítico", "C"), 10: ("1.Crítico", "A"),
                                             2: ("", "A")})
    visao.limpar()
    r = _pecas(app, monkeypatch)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "<html" not in html                       # o pedaço, não a página
    assert _codigos(html) == ["SP-8", "SP-1", "SP-10", "SP-2", "SP-5", "SP-6", "SP-7", "SP-9"]
    assert "SP-3-AV" not in html                                              # a peça do outro almoxarifado
    for rotulo in ("Código", "Peça", "Crit.", "Curva", "Saldo", "Mínimo", "Situação"):
        assert f'data-r="{rotulo}"' in html                                   # o cartão de 375 px
    assert "saldo não informado" in html and "abaixo do mínimo" in html and "saldo unitário" in html
    assert 'class="inv-crit inv-crit--1"' in html and '<b class="alm-curva">A</b>' in html
    outro = _pecas(app, monkeypatch, "20").get_data(as_text=True)
    assert "SP-3-AV" in outro and "SP-8" not in outro


def test_ver_pecas_almox_desconhecido_404(app, almox, monkeypatch):
    assert _pecas(app, monkeypatch, "999").status_code == 404
    assert _pecas(app, monkeypatch, "10.0").status_code == 200                # o ID como a API às vezes o põe


def test_ver_pecas_sem_livro_e_com_a_fonte_caida(app, banco, monkeypatch):
    """Sem o livro do App a tela nem tem cartão para abrir (404); com a fonte caída agora, o 503 (o `fetch` mostra "não consegui
    abrir as peças agora" nos dois)."""
    from nexus.pcm import almoxarifado as T
    assert _pecas(app, monkeypatch).status_code == 404

    def cair(*a, **k):
        raise ConnectionError("banco fora")
    monkeypatch.setattr(T, "_abas", cair)
    visao.limpar()
    assert _pecas(app, monkeypatch).status_code == 503


def test_ver_pecas_so_do_setor_pcm(app, almox, setores):  # noqa: F811
    assert _como(app, ANA).get("/t/pcm/pecas/almox/10").status_code == 403    # a Ana é da Performance


def test_ver_pecas_usa_a_conta_guardada(app, almox, monkeypatch):
    """A rota desenha o pedaço da MESMA conta de 5 min da tela: aquecida a conta, abrir as peças não relê livro nenhum (a
    página não engorda e o Fracttal nem é tocado)."""
    from nexus.pcm import almoxarifado as T
    T.montar()                                                                # a tela já aqueceu a conta

    def nao_ler(*a, **k):
        raise AssertionError("leu o banco")
    monkeypatch.setattr(visao, "_livro", nao_ler)
    monkeypatch.setattr(T, "_abas", nao_ler)
    assert _pecas(app, monkeypatch).status_code == 200


def test_cartao_tem_o_botao_ver_pecas(app, almox, monkeypatch):
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    cartao = _cartao(html, "Almoxarifado 10")
    assert 'aria-expanded="false"' in cartao and 'aria-controls="alm-pecas-10"' in cartao and "Ver peças" in cartao
    assert 'id="alm-pecas-10"' in cartao and "/t/pcm/pecas/almox/10" in cartao
    assert "lendo…" in html and "não consegui abrir as peças agora" in html and "nexusRota" in html


def test_aria_live_so_na_mensagem_das_pecas(app, almox, monkeypatch):
    """O `aria-live` no painel inteiro faria o leitor de tela ler as centenas de linhas que chegam: ele fica só na mensagem
    ("lendo…" e o erro), um elemento que já existe antes do texto (senão o anúncio se perde)."""
    cartao = _cartao(_abrir(app, monkeypatch).get_data(as_text=True), "Almoxarifado 10")
    painel = re.search(r'<div class="alm-pecas"[^>]*>', cartao).group(0)
    assert "aria-live" not in painel and 'role="region"' in painel
    assert re.search(r'<p class="alm-pecas-msg" data-pecas-msg aria-live="polite"></p>', cartao)
    assert "data-pecas-corpo" in cartao and cartao.count("aria-live") == 1


def _contagens(app, api, *cs):
    """Contagens do inventário no almoxarifado: (id, almoxarifado, "Contada em" UTC, como acabou, "Recontagem de"), com o
    `como` em nova | gravando | gravada | conflito. Cada uma conta as peças 501 e 502, e os eventos são os da gravação."""
    from test_pcm_inventario_leitura import _ev, _gravar, _linha, _publicar
    linhas, eventos = [], []
    for cid, almox, contada, fim, *resto in cs:
        mais = {"Recontagem de": resto[0]} if resto else {}
        linhas += [_linha(cid, f"L{i}", str(i), "3", almox=almox, contada=contada, enviada=contada, **mais)
                   for i in (501, 502)]
        if fim == "nova":
            continue
        eventos += [_ev(cid, "aprovada", i, almox=almox) for i in (501, 502)] + [_ev(cid, "peca_gravada", 501, almox=almox)]
        if fim != "gravando":
            eventos.append(_ev(cid, "peca_gravada" if fim == "gravada" else "conflito", 502, almox=almox))
    _publicar(api, *linhas)
    _gravar(app, *eventos)
    visao.limpar()


@pytest.fixture
def inventario(app, almox, tmp_path):
    """O livro do inventário num arquivo, para os eventos das contagens dos cartões; o relógio segue o do `almox`."""
    from nexus.dados import fato_inventario as F
    app.config.update(NEXUS_ALMOX_INVENTARIO_ARQUIVO=str(tmp_path / "inventario.json"))
    F.limpar()
    yield almox
    F.limpar()


def test_cartao_ultima_contagem_gravada(app, inventario, monkeypatch):
    """A data da contagem gravada mais nova do almoxarifado: a de 25/10 ainda não foi aprovada e não conta."""
    _contagens(app, inventario, ("C-1", "10", "2026-10-05T15:00:00Z", "gravada"),
               ("C-2", "10", "2026-10-20T15:00:00Z", "gravada"), ("C-3", "10", "2026-10-25T11:00:00Z", "nova"))
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    cartao = _cartao(html, "Almoxarifado 10")
    assert "Última contagem gravada" in cartao and "20/10/2026" in cartao and "25/10/2026" not in cartao
    assert "sem contagem gravada na janela lida" in _cartao(html, "Almoxarifado 20")      # o outro, nenhuma gravada no livro


def test_cartao_ultima_contagem_conta_conflito_e_recontagem(app, inventario, monkeypatch):
    """A gravada com conflito também é uma contagem gravada, e a recontagem gravada é uma contagem real daquelas peças
    (vale a mais nova de qualquer tipo); a que ainda está gravando, não."""
    _contagens(app, inventario, ("C-1", "10", "2026-10-05T15:00:00Z", "gravada"),
               ("C-2", "10", "2026-10-20T15:00:00Z", "gravada"),
               ("C-4", "10", "2026-10-22T15:00:00Z", "gravada", "C-2"),
               ("C-5", "10", "2026-10-24T15:00:00Z", "gravando"),
               ("C-6", "20", "2026-10-12T15:00:00Z", "conflito"), ("C-7", "20", "2026-10-23T15:00:00Z", "gravando"))
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    assert "22/10/2026" in _cartao(html, "Almoxarifado 10") and "24/10/2026" not in _cartao(html, "Almoxarifado 10")
    assert "12/10/2026" in _cartao(html, "Almoxarifado 20")


def test_cartao_sem_contagem_gravada_na_janela_lida(app, inventario, monkeypatch):
    """O livro das contagens do App é uma janela que anda: "nunca contado" seria mais do que se sabe. Com o livro lido e nenhuma
    gravada naquele almoxarifado (só uma nova), o cartão diz "sem contagem gravada na janela lida"."""
    _contagens(app, inventario, ("C-3", "10", "2026-10-25T11:00:00Z", "nova"))
    cartao = _cartao(_abrir(app, monkeypatch).get_data(as_text=True), "Almoxarifado 10")
    assert "Última contagem gravada" in cartao and "sem contagem gravada na janela lida" in cartao
    assert "nunca contado" not in cartao


def test_cartao_sem_o_livro_das_contagens_nao_diz_nada(app, almox, monkeypatch):
    """O App que ainda não publica o livro das contagens (`livro_existe` falso) é "não leu": a linha some do cartão, em vez
    de todo almoxarifado dizer que nunca foi contado."""
    from nexus.pcm.inventario import revisao as R
    visao.limpar()
    assert R.resumo(app.config)["ultimas"] is None
    cartao = _cartao(_abrir(app, monkeypatch).get_data(as_text=True), "Almoxarifado 10")
    assert "contagem gravada" not in cartao and "nunca contado" not in cartao


def test_cartao_inventario_nao_leu(app, almox, monkeypatch):
    """O livro do inventário que não abriu não é "nunca contado": a linha some do cartão (e a tela segue)."""
    from nexus.dados import fato_inventario as F
    from nexus.pcm.inventario import leitura as L

    def cair(cfg, **k):
        raise F.Recusada("o livro do inventário não abriu")
    monkeypatch.setattr(L, "ler", cair)
    visao.limpar()
    r = _abrir(app, monkeypatch)
    cartao = _cartao(r.get_data(as_text=True), "Almoxarifado 10")
    assert r.status_code == 200 and "contagem gravada" not in cartao and "nunca contado" not in cartao
    assert "Inventário</a>" in r.get_data(as_text=True)                       # a aba segue, sem o número


def test_a_tela_le_o_inventario_uma_vez_por_abertura(app, inventario, monkeypatch):
    """O número da aba Inventário e a última contagem saem de UMA leitura por abertura (`revisao.resumo`). A falha não fica
    guardada (o `visao._calcular` não guarda erro), então duas leituras por abertura dobrariam o custo justo quando o banco está
    ruim: com o livro falhando, 1 por abertura; com o livro bom, 1 na primeira e nenhuma enquanto a cópia de 5 min vale."""
    from nexus.dados import fato_inventario as F
    from nexus.pcm.inventario import leitura as L
    from nexus.pcm.inventario import revisao as R
    chamadas = []
    original = L.ler

    def cair(cfg, **k):
        chamadas.append(1)
        raise F.Recusada("o livro do inventário não abriu")
    monkeypatch.setattr(L, "ler", cair)
    visao.limpar()
    for aberturas in (1, 2, 3):
        assert _abrir(app, monkeypatch).status_code == 200
        assert len(chamadas) == aberturas
    assert R.a_revisar(app.config) is None and len(chamadas) == 4               # o contrato público do a_revisar segue
    chamadas.clear()

    def contar(cfg, **k):
        chamadas.append(1)
        return original(cfg, **k)
    monkeypatch.setattr(L, "ler", contar)
    visao.limpar()
    _contagens(app, inventario, ("C-1", "10", "2026-10-20T15:00:00Z", "gravada"))
    chamadas.clear()
    for _ in range(3):
        assert _abrir(app, monkeypatch).status_code == 200
    assert len(chamadas) == 1 and R.a_revisar(app.config) == 0


def test_a_data_da_ultima_contagem_e_a_de_brasilia(app, inventario, monkeypatch):
    """"Contada em" é UTC: 01:30Z de 21/10 são 22:30 de 20/10 em Brasília, e o cartão mostra o dia de Brasília."""
    _contagens(app, inventario, ("C-1", "10", "2026-10-21T01:30:00Z", "gravada"))
    cartao = _cartao(_abrir(app, monkeypatch).get_data(as_text=True), "Almoxarifado 10")
    assert "20/10/2026" in cartao and "21/10/2026" not in cartao


def test_o_vao_do_alm_det_e_so_do_cartao():
    """O `.alm-det{margin:2px 0 8px}` do cartão pegava também o "falta N" e o "zerada" da tabela das peças que abre dentro dele."""
    css = (Path(__file__).resolve().parent.parent / "nexus" / "static" / "pcm.css").read_text("utf-8")
    assert ".alm-card > .alm-det{" in css and ".alm-card .alm-det{" not in css


def test_valor_por_curva(app, almox, monkeypatch):
    """Saldo × custo unitário, por curva: A 2 × 10, sem curva 1 × 5 e uma peça com saldo e sem custo (fora da soma, e o
    cartão diz quantas)."""
    from nexus.pcm import almoxarifado as T
    _semear(almox, saldo_extra=[_s(5, 30, ALT, 2, 1), _s(6, 30, ALT, 1, 1), _s(7, 30, ALT, 4, 1), _s(8, 30, ALT, 0, 1)],
            novas={5: ("", "A"), 7: ("", "B")}, custo={(5, 30): 10, (6, 30): 5, (8, 30): 7})
    visao.limpar()
    cards = {c["id"]: c for c in T.montar().dados["por_almoxarifado"]}
    c = cards["30"]
    assert c["valor"] == {"total": 25.0, "A": 20.0, "B": 0.0, "C": 0.0, "sem_curva": 5.0}
    assert c["sem_custo"] == 1                                               # o 7, com saldo 4; o 8 tem saldo 0 e não conta
    cartao = _cartao(_abrir(app, monkeypatch).get_data(as_text=True), "Almoxarifado 30")
    assert "Valor em estoque" in cartao and "R$ 25,00" in cartao and "A R$ 20,00" in cartao
    assert "sem curva R$ 5,00" in cartao and "1 peça sem custo no Fracttal" in cartao
    # o almoxarifado em que o Fracttal não deu custo a nenhuma peça com saldo: nunca "R$ 0,00"
    assert cards["10"]["sem_custo"] == 2 and cards["10"]["valor"]["total"] == 0.0
    cartao = _cartao(_abrir(app, monkeypatch).get_data(as_text=True), "Almoxarifado 10")
    assert "R$ 0,00" not in cartao and "2 peças sem custo no Fracttal" in cartao


def test_sem_coluna_custo_nao_mostra_valor(app, almox, monkeypatch):
    """O App de hoje não traz o custo: sem valor e sem cobrança (a coluna ausente não é a peça sem custo)."""
    from nexus.pcm import almoxarifado as T
    assert all(c["valor"] is None and c["sem_custo"] == 0 for c in T.montar().dados["por_almoxarifado"])
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    assert "Valor em estoque" not in html and "sem custo no Fracttal" not in html
