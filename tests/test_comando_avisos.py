"""Os avisos das OS de cada pessoa no sino (04/11/2026): "OS x concluída pelo técnico", pela lista central de OS, e "Sua
solicitação gerou uma OS", gravado quando o PCM aprova no OS Creator; o "Marcar como lida" no livro `nexus_avisos`. Nada vai
ao Fracttal: a lista central é de mentira. Nomes, números e textos inventados."""
import re
import threading
from collections import namedtuple
from datetime import datetime, timedelta, timezone

import pytest
from test_campo_visao import banco  # noqa: F401  (fixture: o banco falso)
from test_comando_insights import PESSOA, limpo  # noqa: F401  (fixtures)

from nexus.comando import avisos as AV
from nexus.dados import catalogo, explica

Reg = namedtuple("Reg", "id folio descricao atribuido_a status_id data_fim")
# o Marcar como lida mora debaixo de /t/ (05/11/2026): nasceu em /avisos/lida, que o Caddy do servidor manda à plataforma
LIDA = "/t/comando/aviso/lida"


def _fim(dias_atras: float) -> str:
    """A data de fim como o Fracttal grava (ISO, UTC)."""
    return (datetime.now(timezone.utc) - timedelta(days=dias_atras)).strftime("%Y-%m-%dT%H:%M:%S")


class _ListaFalsa:
    """A lista central de OS de mentira: `atual()` e `filtrar("criadas", ...)`, como o `os_central` do clone."""

    def __init__(self, linhas):
        self.linhas, self.versao, self.janela, self.pedidos = linhas, 1, ("2026-10-28", "2026-11-04"), []

    def atual(self):
        return self

    def filtrar(self, visao, pessoa, de, ate, status=None, etiqueta=None):
        self.pedidos.append((visao, dict(pessoa), de))
        if pessoa.get("nome") == "Pessoa Homônima":
            return None                                          # o homônimo: a lista central não responde
        return [r for r in self.linhas if r.status_id in (status or ())]


@pytest.fixture
def avisos_limpos():
    AV.limpar()
    yield
    AV.limpar()


@pytest.fixture
def lista(monkeypatch):
    l = _ListaFalsa([Reg(101, "18374", "Recomposição de String", "Técnico Exemplo", 2, _fim(1)),
                     Reg(102, "18375", "Inspeção do inversor", "Técnico Exemplo", 3, _fim(8)),    # fora dos 7 dias
                     Reg(103, "18376", "Troca de fusível", "Fulana de Teste", 3, _fim(1)),        # ela mesma executou
                     Reg(104, "18377", "Concluída sem execução", "Técnico Exemplo", 3, ""),       # sem data de fim
                     Reg(105, "18378", "Em andamento", "Técnico Exemplo", 1, "")])                # ainda em processo
    monkeypatch.setattr(AV, "_os_central", lambda: l)
    return l


def _cliente_de(app, pessoa):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logado=True, admin=False, usuario=dict(pessoa))
    return c


def _sino(html: str) -> str:
    return html.split('class="sino-topo"', 1)[1].split("</details>", 1)[0]


def test_a_os_que_eu_criei_executada_por_outro_vira_aviso(app, lista, avisos_limpos):
    itens = AV.execucoes("Fulana de Teste")
    assert [(a["folio"], a["titulo"], a["wid"]) for a in itens] == [("18374", "OS 18374 concluída pelo técnico", 101)]
    assert "Técnico Exemplo" in itens[0]["detalhe"] and "Em Verificação" in itens[0]["detalhe"]
    assert lista.pedidos[0] == ("criadas", {"nome": "Fulana de Teste"}, "2026-10-28")
    assert AV.execucoes("Pessoa Homônima") == [] and AV.execucoes("") == []


def test_a_solicitacao_aprovada_avisa_quem_pediu_com_os_nomes_cifrados(app, banco, limpo, avisos_limpos):
    with app.app_context():
        AV.registrar_gerou_os({"solicitacao": "3534", "solicitante": "FULANA DE TESTÉ", "folio": "18400",
                               "id_work_order": 555, "aprovador": "Programador Exemplo",
                               "aprovador_email": "pcm@exemplo.test"})
        linhas = banco.linhas(AV.LIVRO, AV.ABA)
        assert [(l["aviso_id"], l["tipo"], l["evento"], l["folio"]) for l in linhas] \
            == [("S:3534", "solicitacao", "gerou_os", "18400")]
        assert "FULANA" not in str(linhas) and "Programador" not in str(linhas)      # os nomes só cifrados
        itens = AV.solicitacoes("Fulana de Teste", linhas)                           # acento e caixa não importam
        assert [(a["titulo"], a["wid"], a["folio"]) for a in itens] == [("Sua solicitação gerou uma OS", 555, "18400")]
        assert AV.solicitacoes("Outra Pessoa", linhas) == []
        assert AV.registrar_gerou_os({"solicitacao": "3535", "solicitante": "", "folio": "1"}) is None   # sem quem pediu


def test_o_sino_mostra_o_aviso_abre_o_card_e_marcar_como_lida_tira(app, banco, limpo, lista, avisos_limpos):
    c = _cliente_de(app, PESSOA)
    html = c.get("/").get_data(as_text=True)
    sino = _sino(html)
    assert "1 aviso das suas OS" in sino and "OS 18374 concluída pelo técnico" in sino and "Marcar como lida" in sino
    assert "/os/_nexus/card/101?status=Em%20Verifica" in sino and "window.NexusOsCard" in html
    botao = sino.split("</summary>", 1)[0]                                # o botão leva o ícone do OS Creator, não o sino
    assert 'class="ph ph-clipboard-text"' in botao and "ph-bell" not in botao
    aid = re.search(r'name="aviso" value="([^"]+)"', sino).group(1)
    assert sino.count(f'action="{LIDA}"') == 2 and "/avisos/lida" not in html       # a lida e a "todas", na rota que existe
    r = c.post(LIDA, data={"aviso": aid, "voltar": "/t/comando/caixa-de-entrada"})
    assert r.status_code in (302, 303) and r.headers["Location"].endswith("/t/comando/caixa-de-entrada")
    assert [(l["aviso_id"], l["evento"]) for l in banco.linhas(AV.LIVRO, AV.ABA)] == [(aid, "leu")]
    assert "concluída pelo técnico" not in c.get("/").get_data(as_text=True)
    c.post(LIDA, data={"aviso": aid, "voltar": "/"})                              # o duplo clique não grava outra
    assert len(banco.linhas(AV.LIVRO, AV.ABA)) == 1


def test_marcar_todas_como_lidas_e_o_id_que_nao_e_de_aviso(app, banco, limpo, lista, avisos_limpos):
    lista.linhas.append(Reg(106, "18379", "Limpeza", "Técnico Exemplo", 3, _fim(2)))
    c = _cliente_de(app, PESSOA)
    assert "2 avisos das suas OS" in _sino(c.get("/").get_data(as_text=True))
    c.post(LIDA, data={"todos": "1", "voltar": "/"})
    assert sorted(l["aviso_id"].split(":")[1] for l in banco.linhas(AV.LIVRO, AV.ABA)) == ["101", "106"]
    c.post(LIDA, data={"aviso": "<script>", "voltar": "https://outro.exemplo"})
    assert len(banco.linhas(AV.LIVRO, AV.ABA)) == 2


def test_o_marcar_como_lida_abre_para_todo_setor_no_portao(app):
    """Debaixo de /t/comando/ o portão por setor abre o caminho a quem tem uma tela da torre, e a Caixa de entrada é de
    todo setor: todo mundo com setor marca como lida. Uma tela do Comando que casasse com o caminho (como /insights/...
    casava com a tela Insights) trancaria quem não a tem: por isso o singular, como insight/acao e pedido/acao."""
    from nexus.auth import setor_telas as ST
    with app.app_context():
        assert ST.pode(LIDA, {"comando/caixa-de-entrada"})


def test_o_gancho_da_aprovacao_grava_por_tras_no_contexto_do_nexus(app, monkeypatch):
    feito, visto = threading.Event(), {}

    def registrar(d):
        from flask import current_app
        visto.update(d=d, app=current_app._get_current_object())
        feito.set()
    monkeypatch.setattr(AV, "registrar_gerou_os", registrar)
    AV.ao_aprovar(app)({"solicitacao": "3534"})
    assert feito.wait(5) and visto == {"d": {"solicitacao": "3534"}, "app": app}


def test_o_livro_esta_no_catalogo_antes_da_1a_gravacao():
    l = catalogo.LIVRO_POR_NOME[AV.LIVRO]
    assert l.abas == (AV.ABA,) and l.so_cresce == (AV.ABA,) and not l.no_banco
    f = catalogo.POR_ID["evento_aviso"]
    assert f.livro == f"{AV.LIVRO} · {AV.ABA}" and f.chave[0] == AV.CAB[0] and "pessoa_hmac" in AV.CAB
    assert "evento_aviso" in explica.RESUMO and "evento_aviso" in explica.PARA_QUE
