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
            novas=None, custo=None, avariados=(), codigos=None):
    """Os 4 livros do App coerentes: `total` itens na lista (1 a 4 com nome; os outros sem saldo), os de `nao_lidos`
    com Lido = Não (o 4, por padrão: 9 de 10 lidos, acima dos 90%). `novas` (30/10/2026) é o App com as colunas novas:
    {id do item: (criticidade, curva)} vai para Criticidade e Curva ABC do Itens (o item fora do dicionário leva vazio),
    e `custo` {(id do item, id do almoxarifado): custo} para o Custo unitário do Saldo. Sem `novas`, o livro de hoje,
    SEM as três colunas (coluna ausente não é coluna vazia). `avariados`: os itens com a marca Avariado = Sim; `codigos`:
    {id do item: código} para trocar o código do catálogo (o "-AV" sem marca, o "SP-AVR-001" que não é avariada)."""
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

def _historico(api, ciclos, codigo="SP-3-AV", item="3", almox="20"):
    """O histórico do Nexus montado à mão: `ciclos` = [(início "AAAA-MM-DD", saldo da peça no almoxarifado, anulado)], todos
    aplicados, cada um com a sua foto do Saldo no livro do mês. `saldo` None = a peça não está na foto do ciclo."""
    from nexus.dados import fato_almoxarifado as F
    cab_ciclo, por_mes = [], {}
    for dia, saldo, anulado in ciclos:
        inicio, data_id = f"{dia}T03:00:00Z", int(dia.replace("-", ""))
        cab_ciclo.append(dict(zip(F.CAB_CICLO, [inicio, data_id, f"{dia}T03:25:00Z", 10, 9, 0, "automático", "aplicado", "",
                                                1 if anulado else 0, f"{dia}T04:00:00Z", 1])))
        foto = [dict(zip(F.CAB_SALDO, [f"s{data_id}{i}", inicio, data_id, str(i), f"SP-{i}", "10", 1, "de-para do Fracttal",
                                       5, 3, ""])) for i in (1, 2)]               # duas peças que nunca saem do lugar
        if saldo is not None:
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
