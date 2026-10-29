"""A Nova solicitação carrega os ativos do cliente UMA vez, e a da Engenharia mostra a tabela de 10 em 10 (Levi,
28/10/2026: "Em solicitação > PCM, quando pesquisa o cliente carrega, quando pesquiso a usina carrega novamente. na minha
cabeça os ativos devem carregar apenas 1 vez e depois é mais fluido"; "em solicitação > engenharia: tá mostrando todos os
ativos de uma vez, o certo é de 10 em 10").

O clone com o Fracttal e o banco falsos (o `cli` dos testes da Área PCM): nada vai à rede. Nomes de mentira."""
from test_oscreator_solic_pcm import ATIVOS, USINA, WEB, api, cli  # noqa: F401

from os_web import tradicional_web as trad  # noqa: E402

SOLIC = (WEB / "templates" / "solic.html").read_text(encoding="utf-8")
ENG = (WEB / "static" / "solic_eng.js").read_text(encoding="utf-8")
OUTRA = "Cliente X - Usina Teste 2 - UF"


def test_um_pedido_traz_as_usinas_e_os_ativos_do_cliente(cli, monkeypatch):
    cat = [dict(a) for a in ATIVOS] + [{"id": 21, "code": "TST2-INV1", "description": "Inversor 2.1 Marca Teste",
                                         "tipo": "Inversor", "usina": OUTRA, "cliente": "Cliente X"},
                                        {"id": 31, "code": "OUT-INV1", "description": "Inversor 9.1", "tipo": "Inversor",
                                         "usina": "Outro - Usina - UF", "cliente": "Outro"}]
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: [dict(x) for x in cat])
    j = cli.get("/os/api/tradicional/catalogo?cliente=Cliente%20X&ativos=1").get_json()
    assert j["usinas"] == [USINA, OUTRA]
    assert [(a["code"], a["usina"]) for a in j["ativos"]] == [("TST-INV11", USINA), ("TST-TRK1", USINA), ("TST2-INV1", OUTRA)]
    # cada ativo com os mesmos campos do pedido por usina (a tabela e a prévia do título não mudam)
    por_usina = cli.get("/os/api/tradicional/catalogo?cliente=Cliente%20X&usina=" + USINA.replace(" ", "%20")).get_json()
    assert [dict(a, usina=USINA) for a in por_usina["ativos"]] == [a for a in j["ativos"] if a["usina"] == USINA]
    assert trad.ativos_do_cliente(cat, "") == []


def test_a_nova_solicitacao_pede_os_ativos_uma_vez_por_cliente():
    cascata = SOLIC.split("// as duas etapas da cascata", 1)[1].split("cbCli.addEventListener", 1)[0]
    assert "&ativos=1" in cascata and "&usina=" not in cascata          # a usina filtra o que já veio, sem pedido
    assert "porCliente" in cascata                                      # o cliente que já veio não é pedido de novo


def test_a_engenharia_mostra_os_ativos_de_10_em_10():
    assert "const PAGINA = 10" in ENG and "function rodapeMais(" in ENG
    pintar = ENG.split("function pintar()", 1)[1].split("\n  }\n", 1)[0]
    assert "vs.slice(0, limite)" in pintar and "rodapeMais(" in pintar
    assert "data-mais" in ENG and "limite = PAGINA" in ENG.split("async function trocarUsina()", 1)[1]


def test_o_criar_os_tambem_pede_os_ativos_uma_vez_por_cliente():
    """Levi, 28/10/2026: "Aplique o mesmo carregamento único dos ativos no Criar OS". O cliente traz as usinas e os ativos
    de todas elas; a usina só filtra; o ↻ (que relê o catálogo do Fracttal) esquece o que já veio."""
    js = (WEB / "static" / "tradicional.js").read_text(encoding="utf-8")
    cascata = js.split("async function onCliente()", 1)[1].split("function refreshAtivos()", 1)[0]
    assert "&ativos=1" in js and "&usina=" not in cascata and "porCliente" in js
    assert "a.usina === usi" in cascata
    assert "porCliente.clear();" in js.split("$('b_reload').onclick", 1)[1].split("\n  };\n", 1)[0]
