"""A Mesa da Segurança (Levi, 24/10/2026: "Criação de mesa da segurança, como PTs atrasadas, extintores vencidos, usinas
sem luvas"): a primeira tela da torre, do setor Segurança, que só lê. O banco falso do Campo (test_campo_visao.py): a
PT-1 espera há 26 h (parada) e a PT-2 há 30 min (ainda não); os extintores do `com_nao_reconhecido` (2 vencidos, o EXT02
da Altair não reconhecido)."""
import re

from test_campo_visao import _aba, _pt, banco  # noqa: F401  (banco é fixture)
from test_hseq_extintores import _texto, com_nao_reconhecido  # noqa: F401  (fixture)

from nexus.torres.hseq import TORRE


def test_a_mesa_e_a_primeira_tela_e_do_setor_seguranca():
    assert TORRE.telas[0].id == "mesa" and TORRE.telas[0].nome == "Mesa da Segurança"
    assert "Segurança" in (TORRE.telas[0].do_setor if isinstance(TORRE.telas[0].do_setor, (tuple, list))
                           else (TORRE.telas[0].do_setor,))


def test_a_mesa_mostra_o_que_pede_acao_e_leva_a_tela_de_origem(com_nao_reconhecido, logado):
    from nexus.campo import visao
    # as PT na hora fixa dos extintores (09/10/2026 10:00 de Brasília): a PT-1 espera há 26 h, a PT-2 há 30 min
    _aba(com_nao_reconhecido, "pt_app_campo", "PT", [dict(_pt("PT-1", 0), **{"Criada em": "2026-10-08T11:00:00.000Z"}),
                                                    dict(_pt("PT-2", 0), **{"Criada em": "2026-10-09T12:30:00.000Z"})])
    visao.limpar()
    html = logado.get("/t/hseq/mesa").get_data(as_text=True)
    t = _texto(html)
    assert "A mesa da Segurança" in t
    faixa = _texto(html[html.index('class="kb-kpis'):html.index("</section>")])
    assert "PTs paradas 1" in faixa and "Extintores vencidos 2" in faixa and "Não reconhecidos 1" in faixa
    assert "Usinas sem luvas" in faixa
    # a PT parada leva ao detalhe dela; a PT-2 (1 h) ainda não está parada
    assert re.search(r'href="/t/campo/pt/PT-1\?ativo=[^"]+"', html) and "PT-2" not in html
    # os vencidos por usina levam a Extintores na usina, filtrado; o não reconhecido leva à usina dele
    assert 'href="/t/hseq/extintores?cliente=Thopen&amp;usina=Altair&amp;f=atrasado#tabela"' in html
    assert 'href="/t/hseq/extintores?cliente=Thopen&amp;usina=Altair#tabela"' in html and "EXT02 · Altair" in t
    assert 'class="hs-legenda"' in html and "Como ler a mesa" in t
    # só lê: nenhum formulário que grava no conteúdo (o do topo é a troca de tema da casca)
    conteudo = html[html.index('class="campo-nativa"'):]
    assert 'method="post"' not in conteudo.lower()


def test_sem_os_extintores_a_mesa_diz_e_os_outros_paineis_seguem(banco, logado):
    html = logado.get("/t/hseq/mesa").get_data(as_text=True)
    assert "Não consegui ler os extintores agora" in html and "PTs paradas" in html
    assert "Extintores vencidos —" in _texto(html[html.index('class="kb-kpis'):html.index("</section>")])
