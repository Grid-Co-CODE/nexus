"""Trocar o responsável da OS na tela do chamado (Nexus > Chamados > Garantias, o Acompanhamento de chamados do OS Creator
Web). Levi, 19/10/2026: "Também quero que ao clicar na OS em responsável dê para alterar o responsável da OS que nem
fazemos no card da OS no histórico de OS Creator!" E, no mesmo dia, "também não está sendo possível digitar observações":
o clone não recebia o token de escrita do banco que o Nexus já tem (ver o fim do arquivo).

O diálogo é o MESMO do card (templates/_dlg_responsavel.html, incluído nas duas telas) e as ações são as do os_acoes.js;
na tela do chamado o nome muda ali mesmo, e o quadro que mostrava a OS sai da memória.

Fracttal FALSO (nada vai à rede). Nomes e números de mentira: o repositório é público."""
import os
import sys
from pathlib import Path

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
import chamados_obs_store as obs_store  # noqa: E402
import gridco_abas as ga  # noqa: E402
from os_web import criar_app, rotas, rotas_acomp  # noqa: E402

WEB = Path(ponte.RAIZ_CLONE) / "os_web"
JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
WID, FOLIO = 9201, 9103
EQUIPE_ID, EQUIPE_NOME = 900001, "Analista Teste"


def _quadro():
    return [k for k in rotas._MEMO if isinstance(k, tuple) and k and k[0] in ("acomp", "acomp_linhas")]


@pytest.fixture(autouse=True)
def _limpo(monkeypatch):
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    monkeypatch.setenv("OS_WEB_CHAMADO_RESP_ID", str(EQUIPE_ID))
    monkeypatch.setenv("OS_WEB_CHAMADO_RESP_NOME", EQUIPE_NOME)
    monkeypatch.setattr(api, "_code_to_loc", lambda: {})
    monkeypatch.setattr(api, "list_chamados", lambda **k: [
        {"id": WID, "folio": str(FOLIO), "cliente": "Cliente Teste", "usina": "Usina Teste", "ativo": "Inversor 1.1",
         "tipo": "Inversor", "tipo_tarefa": "Administrativa", "note": "",
         "descricao": "[Inversor 1.1] - Acompanhamento de chamado Marca", "status_id": 1,
         "status": api.WO_STATUS.get(1), "data": "2026-10-01T12:00:00", "data_fim": "",
         "atribuido_a": "Técnico Teste", "id_atribuido": 900002}])
    monkeypatch.setattr(api, "tickets_os3_em_massa", lambda ids: {i: "" for i in ids})
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: {"folio": FOLIO, "subtarefas": [], "notas": ""})
    monkeypatch.setattr(obs_store, "do_os", lambda folio: [])
    yield
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()


@pytest.fixture
def cli():
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": EQUIPE_NOME, "email": "teste@exemplo.invalid", "perfil": ""}
    return c


def test_a_tela_do_chamado_tem_o_trocar_ao_lado_do_responsavel(cli):
    r = cli.get("/os/chamados/acompanhamento/%d" % FOLIO)
    h = r.get_data(as_text=True)
    assert r.status_code == 200
    # a caixa dos Dados recebe as ações do card (data-os-acoes) e troca o nome no lugar (data-no-lugar)
    assert '<section class="bloco" data-os-acoes data-no-lugar data-wid="%d" data-folio="%d">' % (WID, FOLIO) in h
    caixa = h.split("data-os-acoes", 1)[1].split("</section>", 1)[0]
    # no nome de outra pessoa (não é a equipe de chamados): a cor de aviso, como antes
    assert '<dd class="resp a"><span data-resp-nome>Técnico Teste</span>' in caixa
    assert ('<button type="button" class="det-mini" data-acao="responsavel" title="Atribuir esta OS a outra pessoa">'
            'trocar</button>') in caixa
    # o diálogo do card, com o nº e quem está hoje
    assert 'data-dlg="responsavel"' in caixa and "Trocar o responsável da OS %d" % FOLIO in caixa
    assert "Hoje está com <b>Técnico Teste</b>." in caixa and "carregando o pessoal…" in caixa and ">Atribuir<" in caixa
    assert '<div class="msg ok" data-msg hidden></div>' in caixa
    # o script e o estilo das ações do card, nesta tela também, com a versão no endereço (29/10/2026: o navegador seguia
    # com a cópia de antes até o Ctrl+Shift+R; `estatico()` do os_web)
    import re
    assert re.search(r'<script src="/os/static/os_acoes\.js\?v=\d+"></script>', h)
    assert re.search(r'<link rel="stylesheet" href="/os/static/os_acoes\.css\?v=\d+">', h)


def test_o_dialogo_e_um_so_nas_duas_telas():
    """O card do Histórico e a tela do chamado incluem o mesmo arquivo: mudou o diálogo, muda nos dois."""
    dlg = (WEB / "templates" / "_dlg_responsavel.html").read_text(encoding="utf-8")
    assert '<template data-dlg="responsavel">' in dlg and 'data-conf="responsavel"' in dlg
    for t in ("os_detalhe_conteudo.html", "acomp_os.html"):
        html = (WEB / "templates" / t).read_text(encoding="utf-8")
        assert '{% include "_dlg_responsavel.html" %}' in html, t
        assert '<template data-dlg="responsavel">' not in html, t


def test_trocar_grava_no_fracttal_e_ajusta_o_quadro_guardado(cli, monkeypatch):
    pedidos = []
    monkeypatch.setattr(api, "mudar_responsavel", lambda wid, idp, nota=None: pedidos.append((wid, idp, nota)) or {"ok": True})
    cli.get("/os/chamados/acompanhamento")                               # o quadro, guardado na memória
    assert _quadro()
    r = cli.post("/os/api/os/%d/responsavel" % WID, json={"id_personnel": EQUIPE_ID, "name": EQUIPE_NOME,
                                                           "folio": str(FOLIO)})
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] is True
    assert j["mensagem"] == "OS %d agora está com %s." % (FOLIO, EQUIPE_NOME)
    assert j["da_equipe"] is True                                         # a cor do nome na tela do chamado
    assert pedidos == [(WID, EQUIPE_ID, None)]                            # sem nota: a observação da OS não muda
    # o quadro guardado fica, com o responsável novo (20/10/2026: antes saía da memória, e a volta ao quadro relia o
    # Fracttal na frente de quem voltou; ver test_oscreator_acomp_30min_20_10.py)
    assert _quadro()
    with rotas._MEMO_LOCK:
        linhas = [l for k in _quadro() for l in rotas._MEMO[k][1]["linhas"]]
    assert {(l["atribuido_a"], l["id_atribuido"]) for l in linhas} == {(EQUIPE_NOME, EQUIPE_ID)}
    # para outra pessoa, a cor de aviso
    j = cli.post("/os/api/os/%d/responsavel" % WID, json={"id_personnel": 900003, "name": "Pessoa Teste"}).get_json()
    assert j["da_equipe"] is False


def test_os_que_nao_esta_no_quadro_nao_tira_o_quadro_de_ninguem(cli, monkeypatch):
    """A troca pelo card do Histórico, numa OS que não é de acompanhamento: o quadro guardado fica (relê-lo custaria a
    espera do Fracttal na frente da equipe de chamados, à toa)."""
    monkeypatch.setattr(api, "mudar_responsavel", lambda wid, idp, nota=None: {"ok": True})
    cli.get("/os/chamados/acompanhamento")
    antes = _quadro()
    assert cli.post("/os/api/os/777/responsavel", json={"id_personnel": 900003, "name": "Pessoa Teste"}).get_json()["ok"]
    assert _quadro() == antes and rotas_acomp.esquecer_se_no_quadro(777) is False
    assert rotas_acomp.esquecer_se_no_quadro(WID) is True and _quadro() == []


def test_o_fracttal_recusa_e_nada_muda(cli, monkeypatch):
    monkeypatch.setattr(api, "mudar_responsavel", lambda wid, idp, nota=None: {"ok": False, "erro": "sem permissão"})
    cli.get("/os/chamados/acompanhamento")
    r = cli.post("/os/api/os/%d/responsavel" % WID, json={"id_personnel": 900003, "name": "Pessoa Teste"})
    assert r.status_code == 400 and r.get_json()["erro"] == "sem permissão"
    assert _quadro()                                                      # nada gravado: o quadro guardado continua certo


def test_o_navegador_troca_no_lugar_na_tela_do_chamado():
    """O os_acoes.js acha a caixa da tela do chamado como acha o card, e com data-no-lugar escreve ali o que mudou (o
    nome, a cor pela regra do servidor, o "Hoje está com" do diálogo e a mensagem) em vez de recarregar o card."""
    js = (WEB / "static" / "os_acoes.js").read_text(encoding="utf-8")
    assert "const card = (el) => el.closest('.det, [data-os-acoes]');" in js
    assert "if (d.hasAttribute('data-no-lugar')) { trocouNoLugar(d, opt.textContent, j); return; }" in js
    assert js.index("trocouNoLugar(d, opt.textContent, j)") < js.index("await recarregar(d, urlCard(d), j.mensagem)")
    corpo = js.split("function trocouNoLugar(d, nome, j) {", 1)[1].split("\n  }\n", 1)[0]
    for trecho in ("[data-resp-nome]", "dd.classList.toggle('a', !j.da_equipe)", 'template[data-dlg="responsavel"]',
                   "Hoje está com <b></b>.", "mensagem(d, j.mensagem)"):
        assert trecho in corpo, trecho
    css = (WEB / "static" / "chamados.css").read_text(encoding="utf-8")
    assert "dl.dados dd.resp{" in css and ".msg.ruim{color:var(--rd-t)}" in css


# ── as observações (Levi, 19/10/2026: "também não está sendo possível digitar observações") ──────────────────────────
def test_o_nexus_repassa_ao_clone_o_token_do_banco():
    """O Nexus lê o .env para o app.config e não mexe no ambiente; o clone procura o token no ambiente. No servidor (sem
    cofre do Windows nem pasta do usuário) as observações, os modelos de fornecedor e os temas abriam só para ler."""
    amb = {}
    assert ponte.token_do_banco_para_o_clone({"GRIDCO_SQL_TOKEN": " tk-teste "}, amb) is True
    assert amb == {"GRIDCO_SQL_TOKEN": "tk-teste"}
    amb = {"GRIDCO_SQL_TOKEN": "do-ambiente"}                                     # o do ambiente vale mais
    assert ponte.token_do_banco_para_o_clone({"GRIDCO_SQL_TOKEN": "tk-teste"}, amb) is False
    assert amb == {"GRIDCO_SQL_TOKEN": "do-ambiente"}
    amb = {}
    assert ponte.token_do_banco_para_o_clone({}, amb) is False and amb == {}     # o Nexus sem token: nada


def test_o_clone_criado_fora_dos_testes_leva_o_token(monkeypatch):
    """Na criação do clone (o 1º /os/ do processo). Nos testes, não: o ambiente é do processo inteiro."""
    from types import SimpleNamespace
    monkeypatch.setenv("GRIDCO_SQL_TOKEN", "")                  # vazio; o monkeypatch apaga no fim do teste
    base = {"SECRET_KEY": "teste", "SESSION_COOKIE_SECURE": False, "GRIDCO_SQL_TOKEN": "tk-teste"}
    ponte._criar_clone(SimpleNamespace(config=dict(base, TESTING=True)))
    assert os.environ["GRIDCO_SQL_TOKEN"] == ""
    ponte._criar_clone(SimpleNamespace(config=dict(base, TESTING=False)))
    assert os.environ["GRIDCO_SQL_TOKEN"] == "tk-teste" and ga.pode_gravar() is True


def test_com_o_token_a_observacao_abre_para_escrever(cli, monkeypatch):
    monkeypatch.setenv("GRIDCO_SQL_TOKEN", "tk-teste")
    h = cli.get("/os/chamados/acompanhamento/%d" % FOLIO).get_data(as_text=True)
    caixa = h.split('<textarea class="obs" id="obs"', 1)[1].split("</textarea>", 1)[0]
    assert "disabled" not in caixa
    assert "não tem a credencial de escrita" not in h and "Fica com o seu nome e a data" in h

