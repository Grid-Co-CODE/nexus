"""Engenharia > Mesa do engenheiro (Levi, 18/10/2026): a primeira tela da Engenharia, a mesa de quem entrou (o
administrador escolhe de quem ver), com "Encaminhados para você" (até a pessoa mexer no ativo), "Com você" e "Críticos
sem dono", e a faixa com os três números. O clique abre a gaveta da Confiabilidade. Banco falso; nomes fictícios."""
import re

import pytest
import requests
from test_engenharia_acompanhamento import (ANA, ATIVO, BETO, PESSOAS, _a, _aid, _aid_de, _como,  # noqa: F401
                                            banco, tela)

from nexus.engenharia import acompanhamento as A

URL = "/t/engenharia/mesa"
CAIO = {"email": "caio.prado@gridco.com.br", "nome": "Caio Prado"}      # administrador fora da Engenharia
INV02 = {"cod": "IBI200-INV02", "usina_id": 1, "usina_ligada_por": "de-para do Fracttal", "nivel": "atencao",
         "nFalha": 2, "n7": 1}


@pytest.fixture
def mesa(tela, monkeypatch):
    """A tela da Confiabilidade de test_engenharia_acompanhamento mais um crítico livre: IBI200-INV05 (4 falhas)."""
    from test_engenharia_confiabilidade import _os

    from nexus.engenharia import os_falhas
    from nexus.torres import engenharia as torre
    linhas = ([_os("IBI200-INVR1.3", d) for d in (1, 2, 3, 10)] + [_os("IBI200-TRK07", d) for d in (5, 20)]
              + [_os("IBI200-INV02", d) for d in (1, 4)] + [_os("IBI200-INV05", d) for d in (1, 2, 3, 4)])
    monkeypatch.setattr(os_falhas, "linhas", lambda: linhas)
    torre._CACHE.clear()
    return tela


def _secao(html, titulo):
    """O trecho de uma seção da Mesa, do título até o fim dela."""
    marca = f">{titulo}</h2>"
    return html.split(marca, 1)[1].split("</section>", 1)[0] if marca in html else ""


def test_respondeu_marca_quem_mexeu_depois_de_receber(banco):
    A.pegar(ATIVO, ANA, pode=True)
    assert _a()["respondeu"] is True                                  # quem pega já está mexendo
    A.encaminhar(ATIVO, A.codigo(BETO), ANA, True, PESSOAS())
    assert _a()["respondeu"] is False
    A.comentar(_aid(), "passei para você", ANA, True)                 # quem encaminhou comentar não é resposta
    assert _a()["respondeu"] is False
    A.comentar(_aid(), "vou ver amanhã", BETO, True)
    assert _a()["respondeu"] is True


def test_a_mesa_e_a_primeira_tela_da_engenharia_e_e_do_setor():
    from nexus.auth import pre_carga
    from nexus.torres import engenharia as torre
    t = torre.TORRE.telas[0]
    assert t.id == "mesa" and t.do_setor == "Engenharia"
    assert "engenharia/mesa" in pre_carga.FORA                        # lê as OS de falha do Fracttal ao abrir


def test_mesa_mostra_o_que_e_meu_e_os_criticos_sem_dono(mesa, cliente):
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    assert "IBI200-INVR1.3" in _secao(html, "Com você")
    sem_dono = _secao(html, "Críticos sem dono")
    assert "IBI200-INV05" in sem_dono and "Pegar para acompanhar" in sem_dono
    assert "IBI200-INV02" not in sem_dono and "IBI200-INVR1.3" not in sem_dono      # atenção; e o que tem dono
    assert 'class="eg-gaveta"' in html and 'data-gaveta="g' in html                # o clique abre a gaveta


def test_cada_um_ve_a_sua_mesa(mesa, cliente):
    html = _como(cliente, BETO).get(URL).get_data(as_text=True)
    assert "A sua mesa" in html and ">Com você</h2>" in html
    assert "IBI200-INVR1.3" not in _secao(html, "Com você") and 'name="pessoa"' not in html
    # quem não é administrador não vê a mesa de outra pessoa pelo endereço
    html = cliente.get(URL + "?pessoa=" + A.codigo(ANA)).get_data(as_text=True)
    assert "IBI200-INVR1.3" not in _secao(html, "Com você")


def test_encaminhado_fica_ate_eu_mexer(mesa, cliente):
    A.encaminhar(INV02, A.codigo(ANA), BETO, True, PESSOAS())
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    caixa = _secao(html, "Encaminhados para você")
    assert "IBI200-INV02" in caixa and "Encaminhado por Beto Souza" in caixa
    assert "IBI200-INV02" not in _secao(html, "Com você")                       # sem repetir
    A.comentar(_aid_de("IBI200-INV02"), "Vou olhar amanhã", ANA, True)
    html = cliente.get(URL).get_data(as_text=True)
    assert "IBI200-INV02" not in _secao(html, "Encaminhados para você")
    assert "IBI200-INV02" in _secao(html, "Com você")


def test_os_numeros_do_topo(mesa, cliente):
    A.encaminhar(INV02, A.codigo(ANA), BETO, True, PESSOAS())
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    faixa = html.split('<section class="kb-kpis', 1)[1].split("</section>", 1)[0]
    rotulos = re.findall(r'<span class="kb-kpi-rot">([^<]+)</span>', faixa)
    valores = re.findall(r'<b class="kb-kpi-v[^"]*">([^<]+)</b>', faixa)
    assert rotulos == ["Encaminhados para você", "Com você", "Críticos sem dono"]
    assert valores == ["1", "1", "1"]                       # INV02; INVR1.3 (o da lista Com você); INV05
    assert 'kb-kpi-v--alerta">1<' in faixa and 'kb-kpi-v--critico">1<' in faixa
    assert "chegou <b>hoje</b>" in faixa and "há 0 dias" not in faixa                # encaminhado agora


def test_administrador_escolhe_de_quem_ver(mesa, cliente, app):
    app.config["NEXUS_ADMINS"] = BETO["email"]                       # administrador é o da lista de agora
    html = _como(cliente, BETO, admin=True).get(URL + "?pessoa=" + A.codigo(ANA)).get_data(as_text=True)
    assert 'name="pessoa"' in html and "IBI200-INVR1.3" in _secao(html, "Com Ana Lima")
    assert "A mesa de Ana Lima" in html
    # a senha de administrador não diz quem é: a Mesa pede para escolher a pessoa
    html = _como(cliente, None, admin=True).get(URL).get_data(as_text=True)
    assert "Escolha de quem ver a mesa" in html and 'name="pessoa"' in html


def test_mesa_com_o_banco_fora(mesa, cliente, monkeypatch):
    monkeypatch.setattr(mesa, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("fora")))
    A.limpar()
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    assert "Não consegui ler os acompanhamentos" in html
    assert re.findall(r'<b class="kb-kpi-v[^"]*">([^<]+)</b>', html) == ["—", "—", "—"]
    assert "Pegar para acompanhar" not in html


def test_comentario_com_html_sai_escapado_na_mesa(mesa, cliente):
    A.comentar(_aid_de("IBI200-INVR1.3"), "<script>alert(1)</script>", ANA, True)
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    assert "&lt;script&gt;alert(1)" in html and "<script>alert(1)" not in html


def _escolhidas(html):
    sel = html.split('name="pessoa"', 1)[1].split("</select>", 1)[0]
    return sel, re.findall(r"<option[^>]*selected[^>]*>([^<]*)<", sel)


def test_administrador_fora_da_engenharia_escolhe_e_volta_para_a_sua_mesa(mesa, cliente, app, monkeypatch):
    # revisão final: o administrador da Performance não está na lista da Engenharia; o seletor marcava a 1ª pessoa
    # como escolhida (a mesa dela não abria pelo seletor) e não havia como voltar à sua
    from nexus.auth import setor_telas as ST
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(), "setor": {"id": 2, "nome": "Performance"},
                                               "erro": ""})
    app.config["NEXUS_ADMINS"] = CAIO["email"]
    html = _como(cliente, CAIO, admin=True).get(URL).get_data(as_text=True)
    assert "A sua mesa" in html and _escolhidas(html)[1] == ["A sua mesa"]
    html = cliente.get(URL + "?pessoa=" + A.codigo(ANA)).get_data(as_text=True)
    sel, escolhidas = _escolhidas(html)
    assert escolhidas == ["Ana Lima"] and '<option value="">A sua mesa</option>' in sel
    # a mesa de outra pessoa diz de quem é, nos títulos e nos números
    assert "IBI200-INVR1.3" in _secao(html, "Com Ana Lima") and _secao(html, "Com você") == ""
    assert ">Encaminhados para Ana Lima</h2>" in html and ">Encaminhados para você</h2>" not in html
    faixa = html.split('<section class="kb-kpis', 1)[1].split("</section>", 1)[0]
    assert re.findall(r'<span class="kb-kpi-rot">([^<]+)</span>', faixa) == [
        "Encaminhados para Ana Lima", "Com Ana Lima", "Críticos sem dono"]


def test_sem_pessoa_escolhida_os_numeros_dela_sao_traco(mesa, cliente, app):
    # a senha de administrador não diz quem é: "0 · nada esperando você" era um número de ninguém
    app.config["NEXUS_ADMINS"] = BETO["email"]
    html = _como(cliente, None, admin=True).get(URL).get_data(as_text=True)
    faixa = html.split('<section class="kb-kpis', 1)[1].split("</section>", 1)[0]
    assert re.findall(r'<b class="kb-kpi-v[^"]*">([^<]+)</b>', faixa) == ["—", "—", "1"]
    assert _escolhidas(html)[1] == ["Escolha a pessoa"]


def test_leitura_das_os_pela_metade_nao_vira_numero(mesa, cliente, monkeypatch):
    # revisão final: na 1ª leitura das OS a Mesa dizia "todo crítico tem dono" com 0 no número (a Confiabilidade avisa)
    from nexus.engenharia import os_falhas
    monkeypatch.setattr(os_falhas, "estado", lambda: {"lendo": True, "erro": "", "completa": False, "n": 3,
                                                       "vivas_em": None})
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    assert "Lendo as OS de falha no Fracttal pela primeira vez" in html
    faixa = html.split('<section class="kb-kpis', 1)[1].split("</section>", 1)[0]
    assert re.findall(r'<b class="kb-kpi-v[^"]*">([^<]+)</b>', faixa)[2] == "—"


def test_numeros_da_mesa_empilham_sem_recuo_no_celular():
    # revisão final: a 900 px a faixa vira uma coluna, mas o .kb-kpi:nth-child(even) ainda recuava o 2º número
    from pathlib import Path
    css = Path("nexus/static/engenharia.css").read_text(encoding="utf-8")
    regra = re.search(r"@media \(max-width:900px\)\{\.eg-mesa-kpis\{[^}]*\}(.*?)\}\s*$", css, re.M | re.S)
    assert regra and ".eg-mesa-kpis .kb-kpi{padding:0;border-left:0}" in regra.group(1)


def test_a_engenharia_age_pela_mesa_sem_marcar_a_confiabilidade(app, monkeypatch):
    # revisão final: a Mesa é do setor Engenharia, mas as ações da gaveta vão para as rotas da Confiabilidade, e o portão
    # do setor pede a marca dela; sem a marca, o Pegar da Mesa voltava "O Nexus não gravou (HTTP 403)"
    from nexus.auth import setor_telas as ST
    monkeypatch.setattr(ST, "escolhas_de_dono", lambda: {})          # sem escolha na Central: vale o do código
    with app.app_context():
        telas = ST.das_do_setor({"id": 1, "nome": "Engenharia"})
        assert ST.pode("/t/engenharia/mesa", telas)
        for acao in ("pegar", "encaminhar", "a1b2c3/salvar", "a1b2c3/comentar"):
            assert ST.pode(f"/t/engenharia/confiabilidade/acompanhamento/{acao}", telas)


def test_etiqueta_longa_quebra_dentro_do_cartao_no_celular():
    # prova a 375 px (18/10/2026): "já acompanhado · Comunicação em 14/10" (sem quebra) alargava a coluna do corpo do
    # cartão e passava da borda; a coluna encolhe e, no celular, a etiqueta quebra a linha
    from pathlib import Path
    css = Path("nexus/static/engenharia.css").read_text(encoding="utf-8")
    assert re.search(r"\.eg-item-corpo\{[^}]*grid-template-columns:minmax\(0,1fr\)", css)
    assert re.search(r"@media \(max-width:480px\)\{[^@]*\.eg-item-tags \.eg-tag\{white-space:normal\}", css)
