"""Telas do cadastro: o que a pessoa vê e o que o clique grava."""
import io
import re

import pytest

from nexus import create_app
from nexus.cadastro.cifra import gerar_chave
from nexus.cadastro.servico import Carga

from conftest import SENHA_TESTE
from test_cadastro_importar import _xlsx


@pytest.fixture
def app_cad(tmp_path):
    app = create_app({
        "NEXUS_SECRET_KEY": "chave-de-teste",
        "NEXUS_SENHA_ADMIN": SENHA_TESTE,
        "NEXUS_CHAVE_CADASTRO": gerar_chave(),
        "NEXUS_ARMAZEM_LOCAL": str(tmp_path / "cadastro.json"),
    })
    app.config["TESTING"] = True
    app.config["SESSION_COOKIE_SECURE"] = False
    from nexus.cadastro.telas import servico
    with app.app_context():
        servico().aplicar_carga(Carga(
            entidades={
                "equipes": [{"id": "E-001", "ordem": 1, "valores": {"nome": "SP Leste 01"}}],
                "pessoas": [{"id": "P-0001", "ordem": 1, "valores": {
                    "nome": "Ana Maria Lima", "cargo": "Técnico O&M", "equipe": "E-001", "status": "Ativo",
                    "vinculo": "Colaborador de campo", "cpf": "52998224725", "telefone_corporativo": "11912345678"}}],
                "clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Thopen"}}],
                "usinas": [{"id": "1", "ordem": 1, "valores": {
                    "nome": "Brodowski", "status": "OPERAÇÃO", "equipe": "E-001", "receita_mensal": 11745.0,
                    "prazo_meses": 60, "cidade": "Brodowski", "uf": "SP", "pais": "Brasil", "cliente": "1",
                    "id_bd": "UFV-001", "latitude": -9.8712, "longitude": -47.123}}],
            },
            listas={"status_usina": ["OPERAÇÃO", "A MOBILIZAR"], "uf": ["SP"], "cargos": ["Técnico O&M"],
                    "status_contratacao": ["Ativo", "Desligado"],
                    "vinculo": ["Colaborador de campo", "Supervisor", "Gestor de contrato"]},
        ))
    return app


@pytest.fixture
def cli(app_cad):
    c = app_cad.test_client()
    assert c.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    return c


def _html(resp):
    return resp.get_data(as_text=True)


def test_cadastro_exige_login(app_cad):
    c = app_cad.test_client()
    for url in ("/t/base/registro-mestre", "/t/base/usina/1", "/t/pessoas/colaboradores", "/t/base/importar"):
        assert c.get(url).status_code == 302, url


def test_lista_de_usinas(cli):
    html = _html(cli.get("/t/base/registro-mestre"))
    assert "Brodowski" in html and "UFV-001" in html and "SP Leste 01" in html and "Thopen" in html


def test_coordenada_aparece_sem_pedir(cli):
    # Levi, 29/09: "deve ter a informação da latitude e longitude". Visível na ficha sem revelar e na lista pelo
    # botão Colunas (no arquivo continua cifrada: a API de destino é compartilhada).
    assert "-9,8712" in _html(cli.get("/t/base/registro-mestre"))
    html = _html(cli.get("/t/base/usina/1"))
    assert 'value="-9,8712"' in html and 'value="-47,123"' in html


def test_coordenada_fica_fora_das_colunas_padrao(cli):
    # Levi, 30/09: "tire latitude e longitude das colunas padrões, fica só na retaguarda".
    html = _html(cli.get("/t/base/registro-mestre"))
    for col in ("latitude", "longitude"):
        assert re.search(rf'<th[^>]*data-col="{col}"[^>]*\bhidden', html), col
        assert re.search(rf'<input[^>]*id="cc-{col}"(?![^>]*\bchecked)[^>]*>', html), col
    html = _html(cli.get("/t/base/registro-mestre?cols=nome,latitude"))
    assert re.search(r'<th[^>]*data-col="latitude"(?![^>]*\bhidden)[^>]*>', html)


def test_clientes_tem_tela_e_a_ficha_mostra_as_usinas(cli):
    assert "Thopen" in _html(cli.get("/t/base/clientes"))
    assert "Brodowski" in _html(cli.get("/t/base/cliente/1"))


def test_filtro_por_cliente(cli):
    assert "Brodowski" in _html(cli.get("/t/base/registro-mestre?cliente=1"))
    assert "Brodowski" not in _html(cli.get("/t/base/registro-mestre?cliente=9"))


def test_busca_filtra(cli):
    assert "Brodowski" not in _html(cli.get("/t/base/registro-mestre?q=franca"))


def test_ficha_mostra_calculado_e_esconde_o_sensivel(cli):
    html = _html(cli.get("/t/base/usina/1"))
    assert "704.700,00" not in html and "11.745" not in html        # receita mascarada
    assert "Ana Lima" in html                                        # técnico automático, pela equipe
    html = _html(cli.get("/t/base/usina/1?sensiveis=1"))
    assert "R$ 704.700,00" in html                                   # receita contratual calculada


def test_ver_sensivel_fica_na_auditoria(cli, app_cad):
    cli.get("/t/pessoas/colaborador/P-0001?sensiveis=1")
    from nexus.cadastro.telas import servico
    with app_cad.app_context():
        assert servico().auditoria()[0]["acao"] == "viu dados sensíveis"


def test_pessoa_cpf_mascarado(cli):
    html = _html(cli.get("/t/pessoas/colaborador/P-0001"))
    assert "529.982.247-25" not in html and "***.***.***-25" in html


def _versao(html):
    return re.search(r'name="_versao" value="(\d+)"', html).group(1)


def test_salvar_pela_tela(cli):
    html = _html(cli.get("/t/base/usina/1"))
    resp = cli.post("/t/base/usina/1", data={"_versao": _versao(html), "nome": "Brodowski 1",
                                                  "status": "OPERAÇÃO"})
    assert resp.status_code == 302
    assert "Brodowski 1" in _html(cli.get("/t/base/usina/1"))


def test_salvar_com_erro_mostra_o_erro_e_nao_grava(cli):
    html = _html(cli.get("/t/base/usina/1"))
    resp = cli.post("/t/base/usina/1", data={"_versao": _versao(html), "status": "EM OBRA"})
    assert resp.status_code == 422 and "não está na lista" in _html(resp)
    assert "OPERAÇÃO" in _html(cli.get("/t/base/usina/1"))


def test_salvar_por_cima_de_outra_pessoa_e_recusado(cli):
    html = _html(cli.get("/t/base/usina/1"))
    v = _versao(html)
    assert cli.post("/t/base/usina/1", data={"_versao": v, "nome": "A"}).status_code == 302
    resp = cli.post("/t/base/usina/1", data={"_versao": v, "nome": "B"})
    assert resp.status_code == 409 and "Outra pessoa salvou" in _html(resp)
    assert ">A<" in _html(cli.get("/t/base/registro-mestre")) or "value=\"A\"" in _html(cli.get("/t/base/usina/1"))


def test_criar_usina_pela_tela(cli):
    resp = cli.post("/t/base/usina/nova", data={"nome": "Franca", "status": "A MOBILIZAR"})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/t/base/usina/2")


def test_importar_mostra_previa_e_so_grava_ao_aplicar(cli):
    resp = cli.post("/t/base/importar", data={"arquivo": (io.BytesIO(_xlsx()), "BD_Operacoes.xlsx")},
                    content_type="multipart/form-data")
    html = _html(resp)
    assert resp.status_code == 200 and "Comparação" in html
    assert "UFV-10" not in _html(cli.get("/t/base/registro-mestre"))      # prévia não grava
    token = re.search(r'name="token" value="([^"]+)"', html).group(1)
    assert cli.post("/t/base/importar/aplicar", data={"token": token}).status_code == 302
    assert "UFV-10" in _html(cli.get("/t/base/registro-mestre"))


def test_importar_arquivo_que_nao_e_xlsx_recusa(cli):
    resp = cli.post("/t/base/importar", data={"arquivo": (io.BytesIO(b"oi"), "BD.csv")},
                    content_type="multipart/form-data")
    assert resp.status_code == 400


def test_qualidade_e_listas_abrem(cli):
    assert cli.get("/t/base/qualidade").status_code == 200
    assert "OPERAÇÃO" in _html(cli.get("/t/base/listas"))


def test_incluir_valor_na_lista(cli):
    assert cli.post("/t/base/listas", data={"lista": "status_usina", "valor": "EM OBRA"}).status_code == 302
    assert "EM OBRA" in _html(cli.get("/t/base/listas"))


def test_equipe_mostra_usinas_e_pessoas(cli):
    html = _html(cli.get("/t/base/equipe/E-001"))
    assert "Brodowski" in html and "Ana Lima" in html


# ── técnicos da equipe e avisos que abrem na linha (pedidos do Levi, 30/09) ──

def _coluna(html, coluna, linha):
    """O texto da célula da `coluna` (pelo cabeçalho) na linha cuja 1ª célula é `linha`."""
    cab, cels = _celulas(html, "ID"), _celulas(html, linha)
    return cels[cab.index(coluna)]


def test_equipes_mostram_os_tecnicos(cli):
    # Levi, 30/09: "em equipes insira os nomes dos técnicos responsáveis".
    assert _coluna(_html(cli.get("/t/base/equipes")), "Técnicos", "E-001") == "Ana Lima"


def test_tecnico_digitado_na_usina_conta_para_a_equipe(app_cad):
    # Ensaio de 30/09: 55 das 145 equipes não têm técnico ativo no cadastro de pessoas, mas as usinas delas têm o
    # técnico digitado por cima da fórmula. Contar só a pessoa da equipe deixaria essas equipes sem técnico.
    # "N/I" (não informado) não é nome.
    from nexus.cadastro.telas import servico
    with app_cad.app_context():
        servico().aplicar_carga(Carga(entidades={
            "equipes": [{"id": "1", "ordem": 1, "valores": {"nome": "PR Oeste 01"}}],
            "pessoas": [{"id": "1", "ordem": 1, "valores": {"nome": "Fulano Beltrano Prado", "cargo": "Técnico O&M",
                                                            "status": "Ativo", "vinculo": "Colaborador de campo"}}],
            "usinas": [{"id": "1", "ordem": 1, "valores": {"nome": "U1", "status": "OPERAÇÃO", "equipe": "1",
                                                           "tecnico_om": "1"}},
                       {"id": "2", "ordem": 2, "valores": {"nome": "U2", "status": "OPERAÇÃO", "equipe": "1",
                                                           "tecnico_om": "N/I"}}]}, listas=None))
    c = app_cad.test_client()
    c.post("/entrar", data={"senha": SENHA_TESTE})
    assert _coluna(_html(c.get("/t/base/equipes")), "Técnicos", "1") == "Fulano Prado"
    ficha = _html(c.get("/t/base/equipe/1"))
    assert "Técnicos" in ficha and "Fulano Prado" in ficha      # ele não é da equipe: só aparece pelo resumo


def _detalhe_do_aviso(html, texto):
    """A linha escondida que abre com o aviso `texto` e o botão que a abre."""
    for tr in re.findall(r"<tr\b[^>]*>.*?</tr>", html, re.S):
        if texto in tr:
            abre = re.match(r"<tr\b([^>]*)>", tr).group(1)
            if 'class="cad-detalhe"' in abre:
                id_ = re.search(r'id="([^"]+)"', abre).group(1)
                botao = re.search(rf'<button\b[^>]*aria-controls="{id_}"[^>]*>', html)
                return abre, botao.group(0) if botao else None
    return None, None


@pytest.mark.parametrize("url,monta,aviso", [
    ("/t/base/registro-mestre", [("usinas", {"nome": "Sem Equipe", "status": "OPERAÇÃO"})], "Usina sem equipe."),
    ("/t/base/equipes", [("equipes", {"nome": "SP Leste 09"}),
                         ("pessoas", {"nome": "Bia Souza Reis", "vinculo": "Colaborador de campo", "equipe": "1",
                                      "status": "Ativo"})], "Tem pessoas e nenhuma usina."),
    ("/t/pessoas/colaboradores", [], "Pessoa ativa sem e-mail."),
])
def test_linha_com_aviso_abre_o_aviso(cli, app_cad, url, monta, aviso):
    # Levi, 30/09: "ao clicar na linha que tivesse avisos expandiria o aviso" (Equipes e Registro mestre; a lista
    # é uma só, então vale também para Colaboradores Operação e Clientes). Fechado até o clique.
    from nexus.cadastro.telas import servico
    with app_cad.app_context():
        for ent, form in monta:
            assert servico().criar(ent, form, quem="teste").ok
    html = _html(cli.get(url))
    linha, botao = _detalhe_do_aviso(html, aviso)
    assert linha is not None and re.search(r"\bhidden\b", linha), "o aviso não veio na linha escondida"
    assert botao is not None and 'aria-expanded="false"' in botao


class _FormularioDoNavegador:
    """Lê o <form> da ficha como o navegador o enviaria: input pelo value, textarea pelo texto, select pela
    opção marcada ou, sem nenhuma marcada, pela PRIMEIRA (é o que o navegador faz, e é onde mora o perigo)."""

    def __init__(self, html):
        from html.parser import HTMLParser

        campos, estado = {}, {"select": None, "opcoes": [], "textarea": None}

        class P(HTMLParser):
            def handle_starttag(self, tag, attrs):
                a = dict(attrs)
                if tag == "input" and a.get("name") and a.get("type") not in ("file", "submit"):
                    campos[a["name"]] = a.get("value") or ""
                elif tag == "select" and a.get("name"):
                    estado["select"], estado["opcoes"] = a["name"], []
                elif tag == "option" and estado["select"]:
                    estado["opcoes"].append((a.get("value", ""), "selected" in a))
                elif tag == "textarea" and a.get("name"):
                    estado["textarea"] = a["name"]
                    campos[a["name"]] = ""

            def handle_data(self, data):
                if estado["textarea"]:
                    campos[estado["textarea"]] += data

            def handle_endtag(self, tag):
                if tag == "select" and estado["select"]:
                    marcada = [v for v, s in estado["opcoes"] if s]
                    campos[estado["select"]] = marcada[0] if marcada else (estado["opcoes"][0][0] if estado["opcoes"] else "")
                    estado["select"] = None
                elif tag == "textarea":
                    estado["textarea"] = None

        P().feed(html)
        self.campos = campos


def test_abrir_e_salvar_sem_mexer_nao_muda_nada(app_cad):
    # 29/09/2026: "N/I" digitado no técnico não estava entre as opções da caixa; o navegador marcava a 1ª
    # ("Automático") e salvar a ficha sem mexer apagava o "N/I". Toda caixa tem de ter o valor atual.
    from nexus.cadastro.telas import servico
    from nexus.cadastro.tipos import Legado
    with app_cad.app_context():
        srv = servico()
        srv.aplicar_carga(Carga(entidades={"usinas": [
            {"id": "1", "ordem": 1, "valores": {"nome": "Brodowski", "status": "OPERAÇÃO", "tecnico_om": "N/I",
                                                    "contrato_assinado": Legado("Talvez"), "uf": "XX",
                                                    "responsavel_om": Legado("Fulano Sem Cadastro"),
                                                    "mantenedor_om": "-", "gestor_contrato": "N/A"}}]},
            listas=None))
        versao = srv.registro("usinas", "1").versao
    c = app_cad.test_client()
    c.post("/entrar", data={"senha": SENHA_TESTE})
    for revelar in ("", "?sensiveis=1"):
        form = _FormularioDoNavegador(_html(c.get("/t/base/usina/1" + revelar))).campos
        assert c.post("/t/base/usina/1", data=form).status_code == 302
    with app_cad.app_context():
        r = servico().registro("usinas", "1")
        assert r.versao == versao, "salvar sem mexer gravou versão nova"
        assert r.valores["tecnico_om"] == "N/I"
        assert r.valores["mantenedor_om"] == "-" and r.valores["gestor_contrato"] == "N/A"


def test_campo_mascarado_nao_muda_sem_revelar(cli, app_cad):
    # Envio forjado: CPF no formulário sem ter revelado. A tela nunca manda isso; o servidor também não aceita.
    html = _html(cli.get("/t/pessoas/colaborador/P-0001"))
    cli.post("/t/pessoas/colaborador/P-0001", data={"_versao": _versao(html), "cpf": "111.444.777-35"})
    from nexus.cadastro.telas import servico
    with app_cad.app_context():
        assert servico().registro("pessoas", "P-0001").valores["cpf"] == "52998224725"


# ── visões somadas, colunas escolhidas e o nome da tela (pedidos do Levi, 29/09 à noite) ──

@pytest.fixture
def cli_visoes(tmp_path):
    app = create_app({"NEXUS_SECRET_KEY": "k", "NEXUS_SENHA_ADMIN": SENHA_TESTE,
                      "NEXUS_CHAVE_CADASTRO": gerar_chave(), "NEXUS_ARMAZEM_LOCAL": str(tmp_path / "v.json")})
    app.config["TESTING"] = True
    app.config["SESSION_COOKIE_SECURE"] = False
    from nexus.cadastro.telas import servico
    with app.app_context():
        servico().aplicar_carga(Carga(entidades={
            "clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Cliente A"}},
                         {"id": "2", "ordem": 2, "valores": {"nome": "Cliente B"}}],
            "equipes": [{"id": "1", "ordem": 1, "valores": {"nome": "SP Leste 01"}},
                        {"id": "2", "ordem": 2, "valores": {"nome": "SP Leste 02"}}],
            "pessoas": [{"id": "1", "ordem": 1, "valores": {"nome": "Carla Souza", "vinculo": "Supervisor"}}],
            "usinas": [
                {"id": "1", "ordem": 1, "valores": {"nome": "U1", "status": "OPERAÇÃO", "cliente": "1", "equipe": "1",
                                                    "responsavel_om": "1", "potencia_contratual": 3.0,
                                                    "receita_mensal": 10000.0, "prazo_meses": 12}},
                {"id": "2", "ordem": 2, "valores": {"nome": "U2", "status": "A MOBILIZAR", "cliente": "1",
                                                    "equipe": "2", "responsavel_om": "1", "potencia_contratual": 2.5,
                                                    "receita_mensal": 2000.0}},
                {"id": "3", "ordem": 3, "valores": {"nome": "U3", "status": "OPERAÇÃO", "cliente": "2", "equipe": "2",
                                                    "potencia_contratual": 1.0, "receita_mensal": 5000.0,
                                                    "prazo_meses": 24}},
            ]}, listas={"status_usina": ["OPERAÇÃO", "A MOBILIZAR"]}))
    c = app.test_client()
    c.post("/entrar", data={"senha": SENHA_TESTE})
    return c


def _celulas(html, rotulo):
    """O texto de cada célula da linha da tabela que tem `rotulo`."""
    for tr in re.findall(r"<tr\b.*?</tr>", html, re.S):
        cels = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
                for c in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tr, re.S)]
        if cels and cels[0] == rotulo:
            return cels
    return None


def _texto(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def _cartao(html, nome):
    """O que o cartão de `nome` mostra: {rótulo: valor} dos dados, o destaque em kWp e a nota de rodapé."""
    for bloco in re.findall(r'<article class="cad-cartao\b.*?</article>', html, re.S):
        titulo = re.search(r"<h2\b[^>]*>(.*?)</h2>", bloco, re.S)
        if titulo and _texto(titulo.group(1)) == nome:
            d = {_texto(dt): _texto(dd) for dt, dd in re.findall(r"<dt\b[^>]*>(.*?)</dt>\s*<dd\b[^>]*>(.*?)</dd>",
                                                                 bloco, re.S)}
            d["kWp"] = _texto(re.search(r'class="cad-cartao-kwp"[^>]*>(.*?)</p>', bloco, re.S).group(1))
            nota = re.search(r'<p class="cad-cartao-nota"[^>]*>(.*?)</p>', bloco, re.S)
            d["_nota"] = _texto(nota.group(1)) if nota else None
            return d
    return None


def _faixa(html):
    """A faixa de números do topo da visão: {rótulo: valor}."""
    return {_texto(r): _texto(v) for r, v in re.findall(
        r'<div class="r">(.*?)</div>\s*<div class="v">(.*?)</div>', html, re.S)}


def test_por_cliente_em_cartoes_com_usinas_e_kwp(cli_visoes):
    # Levi, 30/09: "em 'por clientes' eu imagino cards suspensos, algo bem mais dinâmico e visual".
    html = _html(cli_visoes.get("/t/base/registro-mestre?visao=cliente"))
    a = _cartao(html, "Cliente A")
    assert (a["kWp"], a["Usinas"], a["Em operação"]) == ("5.500 kWp", "2", "1")    # 3 + 2,5 MWp = 5.500 kWp
    assert (_faixa(html)["Usinas"], _faixa(html)["kWp"]) == ("3", "6.500")
    html = _html(cli_visoes.get("/t/base/registro-mestre?visao=cliente&operacao=1"))
    a = _cartao(html, "Cliente A")
    assert (a["kWp"], a["Usinas"]) == ("3.000 kWp", "1")                                # só o que está em operação


def test_por_supervisor_em_cartoes_com_usinas_clusters_e_kwp(cli_visoes):
    # Cluster aqui é a Equipe Cluster, como a Carteira de Usinas do Excel conta. Os cartões valem para as duas
    # visões somadas (a melhoria vale onde a tela suporta).
    html = _html(cli_visoes.get("/t/base/equipes?visao=supervisor"))
    c, s = _cartao(html, "Carla Souza"), _cartao(html, "Sem responsável")
    assert (c["Usinas"], c["Clusters"], c["kWp"]) == ("2", "2", "5.500 kWp")
    assert (s["Usinas"], s["Clusters"], s["kWp"]) == ("1", "1", "1.000 kWp")
    html = _html(cli_visoes.get("/t/base/equipes?visao=supervisor&operacao=1"))
    c = _cartao(html, "Carla Souza")
    assert (c["Usinas"], c["Clusters"], c["kWp"]) == ("1", "1", "3.000 kWp")


def test_valor_contratado_mascarado_ate_pedir_e_pedir_fica_na_auditoria(cli_visoes):
    # A receita é dado sensível: na ficha vem mascarada até "Mostrar"; a soma segue a mesma regra, e nem o valor
    # para ordenar vai escondido no HTML.
    html = _html(cli_visoes.get("/t/base/registro-mestre?visao=cliente"))
    assert "120.000" not in html and "240.000" not in html and "data-valor" not in html
    assert _cartao(html, "Cliente A")["Valor contratado"].startswith("R$ •")
    html = _html(cli_visoes.get("/t/base/registro-mestre?visao=cliente&sensiveis=1"))
    assert _cartao(html, "Cliente B")["Valor contratado"] == "R$ 120.000"             # 5.000 × 24 meses
    assert _faixa(html)["Valor contratado"] == "R$ 240.000"
    from nexus.cadastro.telas import servico
    with cli_visoes.application.app_context():
        assert servico().auditoria()[0]["acao"] == "viu dados sensíveis"


def test_valor_contratado_diz_quantas_usinas_estao_sem_valor(cli_visoes):
    # Ensaio de 30/09: 116 das 258 usinas não têm receita no BD (E1, Faro, Elis, Apolo e Qair, nenhuma). A soma
    # sem dizer isso passaria pelo valor do cliente inteiro.
    html = _html(cli_visoes.get("/t/base/registro-mestre?visao=cliente&sensiveis=1"))
    a = _cartao(html, "Cliente A")
    assert a["Valor contratado"] == "R$ 120.000 sem valor em 1 de 2 usinas"   # 10.000 × 12; U2 tem mensal, não prazo
    assert a["Por mês"] == "R$ 12.000"                                        # 10.000 + 2.000
    assert _cartao(html, "Cliente B")["Por mês"] == "R$ 5.000"
    assert a["_nota"] is None


def test_receita_que_falta_nas_duas_colunas_vem_numa_nota_so(cli_visoes):
    # 5 dos 16 clientes do ensaio não têm receita em usina nenhuma: a mesma frase nas duas colunas só repetia. Sem a
    # mensal não há contratual, então contagens iguais são as mesmas usinas.
    from nexus.cadastro.telas import servico
    with cli_visoes.application.app_context():
        srv = servico()
        c3 = srv.criar("clientes", {"nome": "Cliente C"}, quem="teste").registro.id
        c4 = srv.criar("clientes", {"nome": "Cliente D"}, quem="teste").registro.id
        for nome, cli, extra in (("U4", c3, {}), ("U5", c3, {}), ("U6", c4, {}),
                                 ("U7", c4, {"receita_mensal": "1000", "prazo_meses": "10"})):
            assert srv.criar("usinas", {"nome": nome, "status": "OPERAÇÃO", "cliente": cli, **extra}, quem="teste").ok
    html = _html(cli_visoes.get("/t/base/registro-mestre?visao=cliente&sensiveis=1"))
    c, d = _cartao(html, "Cliente C"), _cartao(html, "Cliente D")
    assert (c["Valor contratado"], c["Por mês"], c["_nota"]) == ("—", "—", "Nenhuma das 2 usinas tem receita no BD.")
    assert (d["Valor contratado"], d["Por mês"], d["_nota"]) == ("R$ 10.000", "R$ 1.000", "Sem receita em 1 de 2 usinas.")


def test_lista_traz_as_outras_colunas_escondidas_e_nunca_o_sensivel(cli):
    html = _html(cli.get("/t/base/registro-mestre"))
    assert re.search(r'<th[^>]*data-col="tipologia"[^>]*\bhidden', html)     # dá para acrescentar
    assert re.search(r'<th[^>]*data-col="nome"(?![^>]*\bhidden)[^>]*>', html)  # a padrão fica à vista
    assert 'data-col="receita_mensal"' not in html and 'data-col="cnpj"' not in html


def test_colunas_escolhidas_valem_ao_filtrar(cli):
    html = _html(cli.get("/t/base/registro-mestre?cols=nome,tipologia"))
    assert re.search(r'<th[^>]*data-col="tipologia"(?![^>]*\bhidden)[^>]*>', html)
    assert re.search(r'<th[^>]*data-col="codigo"[^>]*\bhidden', html)


def test_colaboradores_operacao(cli):
    html = _html(cli.get("/t/pessoas/colaboradores"))
    assert "Colaboradores Operação" in html
    assert 'data-col="cpf"' not in html                                       # CPF nunca vai para a lista


def test_sem_chave_o_cadastro_avisa_e_nao_quebra(logado):
    html = _html(logado.get("/t/base/registro-mestre"))
    assert "NEXUS_CHAVE_CADASTRO" in html


def test_quem_entrou_pelo_fracttal_sem_ser_admin_ve_o_porque_e_o_caminho(app_cad):
    """Levi, 08/10/2026: entrou pelo Fracttal, o e-mail dele não estava em NEXUS_ADMINS e o Cadastro devolvia o
    "Forbidden" cru do Flask. Continua 403 (o Cadastro é só de admin), mas a página diz por quê e leva à senha de admin."""
    c = app_cad.test_client()
    with c.session_transaction() as s:
        s["logado"] = True
        s["usuario"] = {"email": "pessoa@exemplo.test", "nome": "Pessoa Exemplo", "perfil": ""}
        s["admin"] = False
    r = c.get("/t/base/registro-mestre")
    assert r.status_code == 403
    html = r.get_data(as_text=True)
    assert "só para administradores" in html and "pessoa@exemplo.test" in html and "NEXUS_ADMINS" in html
    assert "/entrar?admin=1" in html and "Forbidden" not in html
    with c.session_transaction() as s:
        s["admin"] = True                      # o e-mail em NEXUS_ADMINS vira admin no login pelo Fracttal
    assert c.get("/t/base/registro-mestre").status_code == 200
