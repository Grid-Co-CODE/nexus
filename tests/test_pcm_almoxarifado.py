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


def _semear(api, saldo_inicio=INICIO, lidos=4):
    _aba(api, A.LIVRO_CICLO, A.ABA_CICLO, [{"Início do ciclo": INICIO, "Fim do ciclo": FIM,
                                             "Itens na lista do Fracttal": 4, "Itens lidos": lidos, "Erros": 0,
                                             "Origem": "automático"}])
    _aba(api, A.LIVRO_ITENS, A.ABA_ITENS, [
        _item(1, "SP-1", "Fusível 10A", "UNIDADE", "Proteção"), _item(2, "SP-2", "Cabo 6 mm", "METRO", "Cabos"),
        _item(3, "SP-3-AV", "[AVARIADO] Disjuntor", "UNIDADE", "Proteção", av="Sim"),
        _item(4, "SP-4", "Relé de proteção", "UNIDADE", "Proteção", lido="Não")])
    _aba(api, A.LIVRO_SALDO, A.ABA_SALDO, [
        _s(1, 10, ALT, 1, 3, saldo_inicio),          # abaixo: falta 2
        _s(2, 10, ALT, 5, 5, saldo_inicio),          # no limite
        _s(1, 20, SEM, 4, 0, saldo_inicio),          # sem mínimo
        _s(3, 20, SEM, 2, 1, saldo_inicio),          # avariada com saldo
        _s(2, 20, SEM, 0, 0, saldo_inicio)])         # zerada
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
    assert [r["codigo"] for r in cad["recusadas"]] == ["SP-2"] and [a["codigo"] for a in cad["avariadas"]] == ["SP-3-AV"]
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
    _semear(almox, lidos=2)
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
