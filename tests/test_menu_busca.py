"""A busca do menu lateral (14/11/2026, Levi: "Em Nexus, na barra lateral, onde tem todas as janelas, seria interessante
um campo de busca para a pessoa digitar palavras-chave e aí já aparece tudo. Tudo que tem relação, já aparece expandido").

O que estes testes seguram: o campo no alto do menu de quem é da Grid (o do cliente não tem), sem `name` (não entra em
formulário nenhum); o menu da página igual ao de antes (sem a pergunta e sem as telas de dentro: a 1ª versão as punha no
HTML de toda página, e a suíte de 14/11 pegou cinco telas que conferem o que não mostram); o /menu/busca, que entrega a
pergunta de cada tela (`Tela.pergunta`, a palavra-chave que não está no nome) e as telas que abrem por dentro de outra
(o Relatório semanal, na Central de emissão), só as que a pessoa abre; e as contas do `menu-busca.js`, rodadas no node:
sem acento, todas as palavras, o nome da área traz as telas dela, a pergunta só quando o nome não basta, o destaque no
texto original e o trecho da pergunta longa."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from nexus.torres import descobrir_torres, montar_menu

JS = Path(__file__).resolve().parents[1] / "nexus" / "static" / "menu-busca.js"


def _menu(html: str) -> str:
    return html.split('<nav class="menu"', 1)[1].split("</nav>", 1)[0]


def test_o_campo_no_alto_do_menu_e_o_menu_de_sempre(logado):
    html = logado.get("/t/engenharia/fmea").get_data(as_text=True)
    m = _menu(html)
    assert m.index('id="menu-busca"') < m.index('class="item-inicio"')        # o campo antes do Início
    campo = m[m.index("<input", m.index('class="menu-busca"')):]
    campo = campo[:campo.index(">")]
    assert 'type="search"' in campo and " name=" not in campo                 # fora de qualquer formulário
    assert 'for="menu-busca"' in m                                            # o rótulo do campo, como os outros
    assert "menu-busca.js" in html and '<p class="menu-busca-nada" hidden>' in m
    # nada da busca no HTML da página: nem a pergunta, nem as telas de dentro
    perf = next(t for t in descobrir_torres() if t.id == "performance")
    assert perf.tela("disponibilidade").pergunta not in html and "data-pergunta" not in html
    assert "menu-dentro" not in m and "/t/relatorios/relatorio-semanal" not in m


def test_o_menu_busca_entrega_a_pergunta_e_as_telas_de_dentro(logado):
    r = logado.get("/menu/busca")
    assert r.status_code == 200 and "private" in r.headers["Cache-Control"]
    telas = r.get_json()["telas"]
    torres = {t.id: t for t in descobrir_torres()}
    # a pergunta vem da declaração da tela, e não de uma lista à mão; a chave é o endereço do link no menu
    assert telas["/t/performance/disponibilidade"] == {"pergunta": torres["performance"].tela("disponibilidade").pergunta,
                                                      "dentro": []}
    central = telas["/t/relatorios/central"]
    rel = [s for s in torres["relatorios"].telas if s.dentro_de == "central"]
    assert [d["url"] for d in central["dentro"]] == [f"/t/relatorios/{s.id}" for s in rel]
    assert [d["nome"] for d in central["dentro"]] == [s.nome for s in rel]
    assert all(d["pergunta"] for d in central["dentro"])
    assert "/t/relatorios/relatorio-semanal" not in telas                     # não é item do menu
    assert [d["url"] for d in telas["/t/base/acessos"]["dentro"]] == ["/t/base/acessos-clientes"]


def test_o_menu_busca_pede_login(cliente):
    assert cliente.get("/menu/busca").status_code in (302, 401, 403)


def test_so_as_telas_de_dentro_que_a_pessoa_abre():
    torres = descobrir_torres()
    rel = next(t for t in torres if t.id == "relatorios")
    todas = [s.id for s in rel.telas if s.dentro_de == "central"]
    tudo = next(m for m in montar_menu(torres, None) if m["id"] == "relatorios")
    central = next(s for s in tudo["telas"] if s["id"] == "central")
    assert [d["url"] for d in central["dentro"]] == [f"/t/relatorios/{i}" for i in todas]
    assert all(d["pergunta"] for d in central["dentro"]) and central["pergunta"] == rel.tela("central").pergunta
    # com o setor: só o relatório liberado (a mesma regra do setor_telas.pode, que abre a tela pela marca dela)
    menu = montar_menu(torres, None, liberadas={"relatorios/central", "relatorios/pcm-diario"})
    central = menu[0]["telas"][0]
    assert [d["url"] for d in central["dentro"]] == ["/t/relatorios/pcm-diario"]
    assert central["filhas"] == [f"/t/relatorios/{i}" for i in todas]       # o item que acende segue o mesmo


# ── as contas do menu-busca.js, no node ─────────────────────────────────────────────────────────────────────────────
_NODE = r"""
globalThis.window = globalThis;
globalThis.document = {getElementById() { return null; }};
require(process.argv[1]);
const B = window.NexusMenuBusca, C = JSON.parse(process.argv[2]);
process.stdout.write(JSON.stringify(C.map(([f, args]) => B[f](...args))));
"""


def _js(*chamadas):
    if not shutil.which("node"):
        pytest.skip("sem node nesta máquina")
    r = subprocess.run(["node", "-e", _NODE, str(JS), json.dumps(chamadas)], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_sem_acento_e_sem_caixa():
    assert _js(["sem", ["Relatório Potência Gêmeo SEGURANÇA · HSEQ"]], ["palavras", ["  PCM   semána "]]) == [
        "relatorio potencia gemeo seguranca · hseq", ["pcm", "semana"]]


def test_quando_a_tela_casa_com_a_busca():
    p = "As mesas estão dentro do MTTA e do aviso no prazo?"
    assert _js(
        ["achar", [["disponib"], "Performance", None, "Disponibilidade", "Quanto tempo cada usina ficou disponível?"]],
        ["achar", [["mtta"], "COS", None, "Desempenho da equipe", p]],                  # só pela pergunta: 2
        ["achar", [["pcm", "semana"], "PCM", None, "Quadro da semana", "O que cada equipe faz?"]],
        ["achar", [["pcm", "semana"], "PCM", None, "Almoxarifado", "Que peça está abaixo do mínimo?"]],  # falta uma
        ["achar", [["zeladoria"], "Zeladoria", None, "Lixeira", "O que foi excluído e pode voltar?"]],   # pela área
        ["achar", [["central", "semanal"], "Relatórios", "Central de emissão", "Relatório semanal", ""]],  # a de fora
        ["achar", [[], "Base", None, "Clientes", ""]],
    ) == [1, 2, 1, 0, 1, 1, 0]


def test_o_destaque_fica_no_texto_original():
    assert _js(["faixas", ["Potência Ativa dos Inversores", ["potencia", "inversor"]]],
               ["faixas", ["Relatório semanal", ["relat", "latorio"]]],                 # encostados viram um
               ["faixas", ["Equipes e capacidade", ["e"]]]) == [
        [[0, 8], [19, 27]], [[0, 9]], [[0, 1], [5, 6], [8, 9], [19, 20]]]


def test_a_pergunta_longa_vira_um_trecho_em_volta_do_achado():
    curta = "Que OS esperam a aprovação?"
    longa = ("Que extintor está vencido, perto de vencer ou sem conferência há mais de 30 dias, em que cliente e usina, "
             "e com quem?")
    r = _js(["trecho", [curta, ["aprov"]]], ["trecho", [longa, ["usina"]]], ["trecho", [longa, ["extintor"]]])
    assert r[0] == curta
    assert r[1].startswith("… ") and "usina" in r[1] and len(r[1]) <= 80
    assert r[2].startswith("Que extintor") and r[2].endswith(" …")
