"""Os filtros Responsável e Solicitante do Histórico de OS (Levi, 12/11/2026: "Adição de filtros: Responsável (atribuição
da OS), Solicitante (quem fez a abertura da solicitação, quando a OS foi gerada por uma solicitação e não direto de OS)").
Filtros da tabela, como o Cliente: o Responsável é o atribuído da OS; o Solicitante, quem pediu a solicitação que gerou a
OS, das solicitações do Fracttal lidas por trás no Nexus (a leitura de 5 min e o mapa do dia). O Fracttal é de mentira;
nomes e números inventados."""
from test_oscreator_historico_aplicar import USINAS, _pagina, _rodar, cli  # noqa: F401  (fixture)
from test_oscreator_solic_pcm import api  # noqa: F401

from nexus.comando import solicitacoes_fracttal as SF

RESP = ["Técnico Um", "Técnico Dois", "Técnico Um", ""]
SOL = {900: "Pessoa Que Pediu", 902: "Outra Que Pediu"}


def _com_os_dois(monkeypatch):
    from os_web import rotas
    linhas = [{"id": 900 + i, "folio": str(15000 + i), "cliente": u.split(" - ")[0], "usina": u, "tipo": "Inversor",
               "ativo": "Inversor 1.1", "descricao": "Teste %d" % i, "status": "Em Processo", "data": "2026-10-07T10:00:00",
               "atribuido_a": RESP[i]} for i, u in enumerate(USINAS)]
    monkeypatch.setattr(api, "list_minhas_os", lambda *a, **k: [dict(x) for x in linhas])

    def sol(wid):
        return SOL.get(wid, "")
    sol.versao = lambda: 1
    monkeypatch.setattr(rotas, "SOLICITANTE_DA_OS", sol)


def test_as_linhas_e_o_painel_tem_responsavel_e_solicitante(cli, monkeypatch):
    _com_os_dois(monkeypatch)
    html = _pagina(cli)
    assert 'data-filtro="resp"' in html and 'data-filtro="solicitante"' in html
    assert 'data-resp="Técnico Um"' in html and 'data-sol="Pessoa Que Pediu"' in html and 'data-sol=""' in html
    painel = html.split('data-filtro="resp"', 1)[1].split('data-filtro="solicitante"', 1)[0]
    assert 'value="Técnico Dois"' in painel and 'value="Técnico Um"' in painel and 'value=""' not in painel
    assert "Responsável e Solicitante" in html                       # a dica do botão Filtros


def test_os_dois_filtram_a_tabela(cli, monkeypatch):
    _com_os_dois(monkeypatch)
    r = _rodar(_pagina(cli), """(pag) => {
      pag.clicar("#b_filtros"); caixa("resp", "Técnico Um").click(); pag.clicar("#b_aplicar");
      const resp = pag.visiveis(), chips = etiquetas();
      pag.clicar("#b_filtros"); caixa("resp", "Técnico Um").click(); caixa("solicitante", "Outra Que Pediu").click();
      pag.clicar("#b_aplicar");
      return {resp, chips, sol: pag.visiveis(), chips2: etiquetas()};
    }""")
    assert r["resp"] == ["900", "902"] and any("Responsável" in c and "Técnico Um" in c for c in r["chips"])
    assert r["sol"] == ["902"] and any("Solicitante" in c for c in r["chips2"])


def test_quem_pediu_vem_da_leitura_de_5_min_e_do_mapa_do_dia(monkeypatch):
    SF.limpar()
    monkeypatch.setattr(SF, "atuais", lambda app=None: ([{"wid": 1, "nome": "Pessoa Nova"}], {}))
    monkeypatch.setattr(SF, "_ligado", lambda app: False)              # nenhuma leitura sai daqui
    SF._MAPA["por_wid"] = {2: {"wid": 2, "nome": "Pessoa Antiga"}}
    assert (SF.solicitante_da_os(1), SF.solicitante_da_os(2), SF.solicitante_da_os(3)) == ("Pessoa Nova", "Pessoa Antiga", "")
    SF.limpar()


def test_a_leitura_inteira_vai_ate_o_teto_com_a_pausa(monkeypatch):
    pedidos, pausas = [], []

    class Api:
        def _req(self, metodo, ep, params=None, **k):
            pedidos.append(dict(params))
            return {"data": [{"id_code": params["start"] + 1, "id_work_order": params["start"] + 1}] * SF.LIMITE,
                    "total": 5 * SF.LIMITE}
    monkeypatch.setattr(SF, "_clone", lambda nome: Api())
    monkeypatch.setattr(SF.time, "sleep", lambda s: pausas.append(s))
    SF.ler_rest(dias=SF.DIAS_MAPA, teto=3 * SF.LIMITE, pausa=0.3)
    assert len(pedidos) == 3 and pausas == [0.3, 0.3]                  # a pausa entre as páginas, não antes da 1ª
