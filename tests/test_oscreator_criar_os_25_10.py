"""O "Criar OS" da OS do Quadro da equipe da Engenharia e as subtarefas padrão do Criar OS do zero (Levi, 25/10/2026):
"ao lado do botão de solicitação quero um botão de 'Criar OS'. Fará os mesmos preenchimentos automáticos que já faz na
solicitação e já vai deixar uma sub tarefa pronta de 'Descreva a atividade realizada' e 'Ficou alguma pendência? Se sim,
descreva'" e "quero que essas subtarefas já fiquem como padrão na parte de criação de OS do zero!".

O clone com o Fracttal e o banco falsos (o `cli` dos testes da Área PCM): nada vai à rede, nada é criado no Fracttal."""
import html as H
import json
import re

from test_oscreator_solic_pcm import USINA, WEB, cli  # noqa: F401 — `cli` é a fixture do clone com os dublês

import solic_spec as sp  # noqa: E402 — o do clone (o import acima pôs o clone no caminho)

from nexus.engenharia import os_equipe

PADRAO = ["Descreva a atividade realizada", "Ficou alguma pendência? Se sim, descreva"]
JS = (WEB / "static" / "tradicional.js").read_text(encoding="utf-8")


def _sugestao(h):
    return dict(re.findall(r'data-sug-([a-z-]+)="([^"]*)"', h.split('id="sug"', 1)[1].split(">", 1)[0]))


def test_criar_os_do_zero_abre_com_as_duas_subtarefas(cli):
    h = cli.get("/os/tradicional").get_data(as_text=True)
    padrao = re.search(r"data-subs-padrao='([^']*)'", h)
    assert padrao and json.loads(H.unescape(padrao.group(1))) == PADRAO
    # na abertura e depois de gerar (o "nova OS" que volta pronto para outra), as duas; a pessoa edita, tira ou põe mais
    nova = JS.split("function novaOs()", 1)[1].split("\n  }\n", 1)[0]
    assert "subtarefasPadrao();" in nova and "subtarefasPadrao();" in JS.split("// arranque", 1)[1]


def test_as_subtarefas_padrao_sao_as_da_solicitacao_e_a_engenharia_le_a_atividade():
    # as mesmas palavras da BASE da solicitação: a OS de campo que nasce do Criar OS tem a "Descreva a atividade
    # realizada" que a página da OS da Engenharia lê nas filhas (Demais respostas do técnico)
    base = [s["desc"] for s in sp.BASE]
    assert all(p in base for p in PADRAO)
    assert os_equipe._norm(PADRAO[0]) == os_equipe.ATIVIDADE


def test_criar_os_com_sugestao_traz_o_ativo_a_os_pai_e_a_data(cli):
    h = cli.get("/os/tradicional?ativo=TST-INV11&os_pai=555&os_pai_folio=16784&data=2026-10-08T06:00").get_data(as_text=True)
    assert _sugestao(h) == {"cliente": "Cliente X", "usina": USINA, "ativo": "TST-INV11", "os-pai": "555",
                            "os-pai-folio": "16784"}
    assert 'id="dt_prog" type="datetime-local" value="2026-10-08T06:00"' in h
    # a página aplica a sugestão ao abrir; a OS pai vem escolhida no campo do Passo 1 (ao lado das datas desde 26/10/2026)
    # e não passa para a OS seguinte
    assert "sugerir();" in JS.split("// arranque", 1)[1]
    sug = JS.split("async function sugerir()", 1)[1].split("\n  }\n", 1)[0]
    assert "ospaiSel = {id: Number(s.sugOsPai), folio: s.sugOsPaiFolio}; ospaiIn.value = s.sugOsPaiFolio;" in sug
    assert "ospaiSel = null; ospaiIn.value = '';" in JS.split("function novaOs()", 1)[1].split("\n  }\n", 1)[0]
    card1 = h.split('id="card1"', 1)[1].split('id="card2"', 1)[0]
    assert 'id="dt_exec"' in card1 and 'id="ospai_in"' in card1


def test_criar_os_sem_sugestao_ou_com_ela_torta_abre_como_sempre(cli):
    vazia = {"cliente": "", "usina": "", "ativo": "", "os-pai": "", "os-pai-folio": ""}
    assert _sugestao(cli.get("/os/tradicional").get_data(as_text=True)) == vazia
    h = cli.get("/os/tradicional?ativo=NAO-EXISTE&os_pai=abc&os_pai_folio=16784&data=2999-01-01T00:00").get_data(as_text=True)
    assert _sugestao(h) == vazia and 'value="2999-01-01T00:00"' not in h


def test_a_solicitacao_segue_com_a_mesma_sugestao(cli, monkeypatch):
    # a sugestão pelo endereço é uma regra só, para as duas telas (`tradicional_web.sugestao`)
    import api
    monkeypatch.setattr(api, "get_request_types", lambda: {"classif1": [{"id": 7, "description": "Corretiva"}]})
    h = cli.get("/os/solicitacao?ativo=TST-INV11&os_pai=555&os_pai_folio=16784&data=2026-10-08T06:00").get_data(as_text=True)
    assert _sugestao(h) == {"cliente": "Cliente X", "usina": USINA, "ativo": "TST-INV11", "os-pai": "555",
                            "os-pai-folio": "16784"}
    assert 'id="dt_inc" value="2026-10-08T06:00"' in h
