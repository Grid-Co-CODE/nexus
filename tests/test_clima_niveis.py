"""Os quatro níveis do Clima e risco (Levi, 10/10/2026, olhando o Mapa de risco: "está tudo vermelho ou amarelo, tudo está em risco,
quando tudo está em risco nada está em risco"). A Atenção é o que acontece PERTO da usina (o fogo); a condição da região (tempo seco,
calor, aviso leve do INMET, risco de fogo sem fogo perto) é Acompanhar, num azul calmo. Sem rede."""
import re
from datetime import datetime, timedelta

from nexus.performance.clima import alertas as A
from nexus.performance.clima import leitura as L
from nexus.performance.clima import visao as V

from clima_mapa_mundo import ALFA, BETA, DELTA, instalar_leituras  # noqa: F401
from test_clima_visao import (GRANDE, REF, UTC, aviso, cadastro, dias, faixa, foco_a, fogo_nasa, lei_avisos, lei_firms,  # noqa: F401
                              lei_focos, lei_risco, leituras, usina)


def test_o_caso_de_10_10_a_regiao_inteira_nao_pinta_tudo_de_amarelo(leituras):
    """O dia que criou o quarto nível, em miniatura: dez usinas debaixo de baixa umidade e de risco de fogo crítico (a condição da
    região), duas com fogo da NASA a até 5 km, uma com fogo a 8 km e risco crítico hoje, e uma com tempestade em Perigo. Antes,
    13 de 14 eram Atenção; agora a Atenção são as 3 com fogo perto."""
    # usinas a 0,2 grau (~22 km) uma da outra: o raio de 10 km de uma não pega o fogo da vizinha
    usinas = [usina(str(i), f"U{i:02d}", -3.0 - i * 0.2, -45.0) for i in range(1, 15)]
    fogos = [fogo_nasa(-3.0 - 11 * 0.2, -45.0 + 2.0 / 111.195), fogo_nasa(-3.0 - 12 * 0.2, -45.0 + 3.0 / 111.195),
             fogo_nasa(-3.0 - 13 * 0.2, -45.0 + 8.0 / 111.195)]
    tempestade = aviso(2, evento="Tempestade", geo={"type": "Polygon", "coordinates": [[[-45.1, -5.85], [-44.9, -5.85], [-44.9, -5.75],
                                                                                         [-45.1, -5.75], [-45.1, -5.85]]]})
    regiao_seca = {"type": "Polygon", "coordinates": [[[-46, -6.5], [-44, -6.5], [-44, -3], [-46, -3], [-46, -6.5]]]}
    leituras(avisos=lei_avisos(aviso(1, evento="Baixa Umidade", geo=regiao_seca), tempestade), focos=lei_focos(),
             risco=lei_risco({u.id: dias(0.99, 0.99, 0.5, 0.5) for u in usinas}), firms=lei_firms(*fogos))
    v = V.montar({}, cadastro=cadastro(*usinas), ref=REF)
    assert {f["id"]: f["valor"] for f in v["faixa"]} == {"agir": "1", "atencao": "3", "regiao": "10", "sem": "0", "cobertura": "14"}
    assert [c["nome"] for c in v["atencao"]] == ["U11", "U12", "U13"]                  # o fogo mais perto primeiro
    assert v["atencao"][2]["por_que"].startswith("Fogo a 8,0 km há 6 h, com risco de fogo crítico")
    assert v["atencao"][2]["fogo24"]["texto"] == "a 8,0 km há 6 h"
    # a grade por estado só conta os alertas: a condição da região não pinta o estado
    assert sum(t["n"] for t in v["ufs"]) == 4


def test_hoje_ou_amanha_pelo_rotulo_do_dia_e_o_arquivo_de_ontem():
    hoje = ["Hoje", "D+1", "D+2", "D+3"]
    ontem = ["Ontem", "Hoje", "D+1", "D+2"]

    def cels(valores, rotulos):
        return [V.celula_de_risco(i, a, rotulos) for i, a in enumerate(dias(*valores))]
    assert A.critico_hoje_ou_amanha(cels((0.99, 0.1, 0.1, 0.1), hoje)) is True
    assert A.critico_hoje_ou_amanha(cels((0.1, 0.99, 0.1, 0.1), hoje)) is True
    assert A.critico_hoje_ou_amanha(cels((0.1, 0.1, 0.99, 0.1), hoje)) is False          # D+2 é depois de amanhã
    assert A.critico_hoje_ou_amanha(cels((0.9, 0.9, 0.9, 0.9), hoje)) is False           # alto não é crítico
    assert A.critico_hoje_ou_amanha(cels((0.99, 0.1, 0.1, 0.1), ontem)) is False         # o crítico era o de ontem
    assert A.critico_hoje_ou_amanha(cels((0.1, 0.1, 0.99, 0.1), ontem)) is True          # com o arquivo de ontem, o T2 é amanhã
    assert A.critico_hoje_ou_amanha(None) is False


def test_o_foco_do_inpe_a_8_km_com_risco_critico_diz_agora(leituras):
    leituras(avisos=lei_avisos(), focos=lei_focos(foco_a(8.0)), risco=lei_risco({"1": dias(0.99, 0.1, 0.1, 0.1)}))
    c = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["atencao"][0]
    assert c["por_que"].startswith("Fogo a 8,0 km agora, com risco de fogo crítico")
    assert c["fogo24"]["detalhe"] == "fogo a 8,0 km agora (satélite GOES-19), com risco de fogo crítico hoje ou amanhã"


def test_o_resumo_do_acompanhar_conta_o_que_pesa(leituras):
    usinas = [usina("1", "A", -4.2, -45.0), usina("2", "B", -4.3, -45.0), usina("3", "C", -8.0, -41.0)]
    leituras(avisos=lei_avisos(aviso(1, evento="Baixa Umidade", geo=GRANDE)), focos=lei_focos(),
             risco=lei_risco({"1": dias(0.9, 0.1, 0.1, 0.1), "2": dias(0.1, 0.1, 0.1, 0.1), "3": dias(0.8, 0.1, 0.1, 0.1)}))
    v = V.montar({}, cadastro=cadastro(*usinas), ref=REF)
    assert v["n_regiao"] == 3 and v["regiao_resumo"] == [{"nome": "Baixa umidade (Perigo Potencial)", "n": 2},
                                                         {"nome": "Risco de fogo alto ou crítico", "n": 2}]


def test_a_lista_tem_a_secao_acompanhar_com_o_resumo_e_a_lista_recolhida(tmp_path, monkeypatch):
    import clima_mundo as CM
    c, _sessao, _app = CM._mundo(tmp_path, monkeypatch, CM.carga(), CM.arquivos_do_mundo())
    try:
        html = CM.pagina(c)
    finally:
        L.usar_sessao(None)
    t = CM.texto(html)
    assert "Acompanhar · 3 usinas, condição da região: nada perto da usina pede ação" in t
    assert '<span class="cl-pill cl-pill--regiao">Risco de fogo alto ou crítico · 2</span>' in html
    assert '<span class="cl-pill cl-pill--regiao">Baixa umidade (Perigo Potencial) · 1</span>' in html
    assert re.search(r'<details class="cl-mais-eventos cl-regiao-lista">\s*<summary>Ver as 3 usinas</summary>', html)
    assert html.count('<tr class="cl-lin cl-lin--regiao">') == 3
    assert "O que fazer: nada agora; manter a rotina de roçagem, aceiro e limpeza dos módulos." in t
    # a faixa tem cinco números e o Acompanhar diz o que fazer
    assert re.search(r'<div class="cl-cel cl-regiao[^"]*" data-id="regiao">\s*<span class="cl-rotulo">Acompanhar</span>', html)
    assert "Nada a fazer agora; manter a rotina de roçagem, aceiro e limpeza." in t


def test_o_mapa_pinta_o_acompanhar_de_azul_e_a_legenda_explica(tmp_path, monkeypatch):
    from pathlib import Path

    import clima_mapa_mundo as MM
    from test_torre_performance_mapa import nova_app
    _, c = nova_app(tmp_path)
    monkeypatch.setattr(V, "agora", lambda: MM.REF)
    instalar = instalar_leituras(monkeypatch)
    MM.mundo_completo(instalar, firms=MM.lei_firms(MM.nasa_a(3.0, BETA)))           # a Beta com fogo perto: atenção
    html = c.get("/t/performance/clima/mapa").get_data(as_text=True)
    assert 'class="mp-ponto mp-n-regiao"' in html and 'class="mp-ponto mp-n-atencao"' in html
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    # desde 27/10/2026 (a tela enxuta) o número fica na faixa em cima do mapa e a explicação no "!" do título
    assert re.search(r"Acompanhar 2\b", t) and re.search(r"Atenção 1\b", t)
    assert re.search(r"Acompanhar Condição da região, nada perto da usina", t) and re.search(r"Atenção Fogo perto", t)
    css = (Path(V.__file__).resolve().parents[2] / "static" / "clima-mapa.css").read_text(encoding="utf-8")
    assert ".mp-ponto.mp-n-regiao{fill:var(--cl-regiao)}" in css
    assert ".mp-oculta-regiao .mp-usinas a:has(.mp-n-regiao),.mp-oculta-regiao .mp-tab--regiao," in css
    clima_css = (Path(V.__file__).resolve().parents[2] / "static" / "clima.css").read_text(encoding="utf-8")
    assert "--cl-regiao:var(--info)" in clima_css                                      # um azul de informação, nos dois temas
