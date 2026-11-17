"""O prontuário sai da Visão do responsável (Levi, 16/11/2026: "Tire a opção de prontuário da Visão do Responsável, no
painel na parte de performance vai ter a opção 'ver prontuário' e vai para a parte de UFV"). A aba "Prontuário da usina"
(desde 12/11/2026 a mesma página do Comando > Usinas, numa aba) sai; o endereço antigo leva ao prontuário do Comando; e
cada usina do quadro Performance do Painel ganha o "Ver prontuário", que abre a página da usina no Comando > Usinas.
O endereço é o de hoje, /t/comando/usinas/<id>: o chat do Comando vai mover a tela para /t/campo/usinas, e o antigo
segue valendo (308). No prontuário do Comando, a PT esperando o De acordo levava à aba ("Decidir na Usinas 360°"):
agora leva à página da PT. Banco falso do test_campo_responsaveis (a Altair, a Brodowski 1 e a Coração 1)."""
import re

from test_campo_responsaveis import tela  # noqa: F401  (fixture)
from test_campo_visao import banco  # noqa: F401  (fixture)


def test_a_aba_saiu_e_o_endereco_antigo_leva_ao_prontuario_do_comando(tela, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    assert ">Prontuário da usina</a>" not in html and "modo=usina" not in html
    r = logado.get("/t/campo/responsaveis?modo=usina&usina=1")
    assert r.status_code == 302 and r.headers["Location"].endswith("/t/comando/usinas/1")
    r = logado.get("/t/campo/responsaveis?modo=usina")
    assert r.status_code == 302 and r.headers["Location"].endswith("/t/comando/usinas")


def test_a_performance_do_painel_tem_o_ver_prontuario_em_cada_usina(tela, logado):
    html = logado.get("/t/campo/responsaveis?modo=painel&responsavel=*").get_data(as_text=True)
    depois = html.split('id="pn-perf-t"', 1)[1]
    perf, resto = depois.split("</section>", 1)
    da_linha = re.findall(r'data-cr-painel="/t/campo/responsaveis/usina/(\d+)/meta"', perf)
    links = re.findall(r'<a class="pn-pront" href="/t/comando/usinas/(\d+)"[^>]*>Ver prontuário</a>', perf)
    assert da_linha and links == da_linha                     # um por usina, na ordem do quadro
    # só na Performance
    assert 'class="pn-pront"' not in resto


def test_o_prontuario_do_comando_decide_a_pt_pela_pagina_da_pt(tela, logado):
    html = logado.get("/t/comando/usinas/1").get_data(as_text=True)
    seg = html.split('id="pu-seg"', 1)[1].split("</details>", 1)[0]
    assert "modo=usina" not in seg and "Decidir na Usinas 360°" not in seg
    assert seg.count('href="/t/campo/pt/') == 2 and "Decidir a PT" in seg
