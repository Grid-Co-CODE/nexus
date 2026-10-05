"""Central de atenção nativa do Nexus (Levi, 04/10/2026: "pode passar para o Nexus").

As regras são cópia fiel do App (nexus/campo/regras_app.py); aqui as tabelas do App são falsas, no mesmo formato.
"""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from nexus.campo import atencao, regras_app, tabelas

FONTE_APP = Path(r"C:\Users\Levi Maia\OneDrive - GRID CO\Área de Trabalho\Grid Co_ - 4. O&M\11.Pré-Operação"
                 r"\6. PCM\09. Programação Semanal\App_Campo\middleware\function_app.py")


def _dia(atras):
    return (datetime.utcnow().date() - timedelta(days=atras)).isoformat()


class TabelaFalsa:
    """O pedaço do TableClient que as regras do App usam, com os filtros que elas mandam."""

    def __init__(self, linhas):
        self.linhas = linhas

    def query_entities(self, filtro, select=None, **_):     # o App pede colunas com select=; aqui vem tudo
        condicoes = []
        for parte in filtro.split(" and "):
            m = re.fullmatch(r"\s*(\w+) (eq|ge|gt|le|lt) '([^']*)'\s*", parte)
            if not m:   # filtro novo no App: o teste tem de saber, em vez de responder errado
                raise ValueError(f"filtro não suportado pela tabela falsa: {filtro}")
            condicoes.append(m.groups())
        ops = {"eq": lambda a, b: a == b, "ge": lambda a, b: a >= b, "gt": lambda a, b: a > b,
               "le": lambda a, b: a <= b, "lt": lambda a, b: a < b}
        return [dict(e) for e in self.linhas
                if all(ops[op](str(e.get(campo, "")), valor) for campo, op, valor in condicoes)]

    def get_entity(self, pk, rk):
        for e in self.linhas:
            if e["PartitionKey"] == pk and e["RowKey"] == rk:
                return dict(e)
        raise KeyError((pk, rk))

    def list_entities(self):
        return [dict(e) for e in self.linhas]


@pytest.fixture
def app_campo():
    """As tabelas do App, vazias, servidas pela chave do Nexus (falsa)."""
    dados = {}
    tabelas.usar_fornecedor(lambda nome: TabelaFalsa(dados.setdefault(nome, [])))
    atencao.limpar_cache()
    yield dados
    tabelas.usar_fornecedor(None)
    atencao.limpar_cache()


def _ponto_os(tipo, usina, atras, oque, os_="15131"):
    return {"origem": "os", "tipo": tipo, "rotulo": regras_app.ATN_TIPOS.get(tipo, tipo), "usina": usina,
            "cluster": "SP 01", "email": "", "nome": "Técnico 1", "os": os_, "data": _dia(atras),
            "fotos": 2, "peso": 6, "oque": oque, "detalhe": ""}


# ── a cópia ─────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.skipif(not FONTE_APP.exists(), reason="código do App não está nesta máquina")
def test_regras_sao_copia_fiel_do_app():
    """A lógica copiada é a do App: mesma árvore de código, função por função (sem comentários e docstrings, que
    ficam no App). Se o App mudar uma destas funções, este teste acusa: rode ferramentas/extrair_regras_campo.py de
    novo e confira a tela contra o painel do App."""
    import ast
    import hashlib
    from ferramentas.extrair_regras_campo import _definicoes, assinatura, nos_do_app
    no_app, arvore = nos_do_app(FONTE_APP.read_text(encoding="utf-8"))
    na_copia = _definicoes(ast.parse(Path(regras_app.__file__).read_text(encoding="utf-8")))
    assert set(no_app) == set(regras_app.COPIADAS)
    for nome, no in no_app.items():
        assert assinatura(no) == assinatura(na_copia[nome]), f"{nome} mudou no App: rode o extrator"
    defs_app = _definicoes(arvore)
    for nome, ass in regras_app.ASSINATURAS_TROCADAS.items():
        atual = hashlib.sha256(assinatura(defs_app[nome]).encode("utf-8")).hexdigest()[:16]
        assert atual == ass, f"{nome} mudou no App: revise o substituto do Nexus (fim de regras_app.py)"


def test_copia_nao_abre_a_conexao_do_app_nem_a_tabela_dos_tokens():
    copia = Path(regras_app.__file__).read_text(encoding="utf-8")
    assert "from_connection_string" not in copia
    assert "create_table" not in copia
    assert "AzureWebJobsStorage" not in copia
    assert "fracttaltokens" not in copia     # a tabela dos tokens só é tocada por pessoas.tabela_do_cadastro


def test_copia_sem_comentarios_do_app():
    """O repositório do Nexus é público e os comentários do App citam colegas pelo nome: só a lógica vem."""
    import io
    import tokenize
    copia = Path(regras_app.__file__).read_text(encoding="utf-8")
    comentarios = [t.string for t in tokenize.generate_tokens(io.StringIO(copia).readline) if t.type == tokenize.COMMENT]
    permitidos = ("# ruff", "# ──", "# O resto deste arquivo", "# noqa")
    assert all(c.startswith(permitidos) for c in comentarios), [c for c in comentarios if not c.startswith(permitidos)]
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", copia)


# ── as regras, com tabelas falsas ───────────────────────────────────────────────────────────────────────────────


def test_usina_sem_ronda_ha_mais_de_14_dias_e_usina_nunca_rondada(app_campo):
    app_campo["rondaativos"] = [
        {"PartitionKey": "usina", "RowKey": "a", "usina": "Usina A", "cluster": "SP 01", "trk_n": 10, "inv_n": 2},
        {"PartitionKey": "usina", "RowKey": "b", "usina": "Usina B", "cluster": "BA 01", "trk_n": 0, "inv_n": 4},
    ]
    app_campo["rondas"] = [{"PartitionKey": _dia(20), "RowKey": "r1", "usina": "Usina A", "finalizada": True}]
    d = atencao.central(14).dados
    oques = [p["oque"] for p in d["pontos"]]
    assert oques == ["1 usinas nunca receberam ronda", "Sem ronda há 20 dias"]
    assert d["pontos"][1]["dias"] == 20


def test_os_em_revisao_e_invariantes_entram_na_fila_pela_idade(app_campo):
    app_campo["atencaoos"] = [
        {"PartitionKey": "os", "RowKey": "lote", "quando": "2026-10-04T05:00:00",
         "pontos": json.dumps([_ponto_os("os_falha", "Usina A", 2, "Termografia acima do limite")])},
        {"PartitionKey": "inv", "RowKey": "pontos", "quando": "2026-10-04T03:00:00",
         "pontos": json.dumps([_ponto_os("os_exec_presa", "Usina C", 21, "Execução presa", os_="15002")])},
    ]
    d = atencao.central(30).dados
    assert [(p["tipo"], p["dias"]) for p in d["pontos"]] == [("os_exec_presa", 21), ("os_falha", 2)]
    assert d["mais_de_7d"] == 1


def test_encaminhada_vencida_fica_marcada_e_resolvida_sai(app_campo):
    falha = _ponto_os("os_falha", "Usina A", 2, "Termografia acima do limite")
    presa = _ponto_os("os_exec_presa", "Usina C", 21, "Execução presa", os_="15002")
    app_campo["atencaoos"] = [{"PartitionKey": "os", "RowKey": "lote", "quando": "x",
                               "pontos": json.dumps([falha, presa])}]
    app_campo["decisoes"] = [
        {"PartitionKey": "atn", "RowKey": regras_app._chave_atencao(falha, falha["oque"]), "estado": "encaminhada",
         "prazo": _dia(1), "resp_nome": "Supervisor SP"},
        {"PartitionKey": "atn", "RowKey": regras_app._chave_atencao(presa, presa["oque"]), "estado": "resolvida"},
    ]
    pontos = atencao.central(30).dados["pontos"]
    assert [p["tipo"] for p in pontos] == ["os_falha"]
    assert pontos[0]["estado"] == "encaminhada" and pontos[0]["escalada"] is True
    assert pontos[0]["resp_nome"] == "Supervisor SP"


def test_encaminhamentos_como_o_painel_do_app(app_campo):
    app_campo["decisoes"] = [
        {"PartitionKey": "atn", "RowKey": "k1", "estado": "encaminhada", "prazo": _dia(2), "oque": "Limpeza",
         "usina": "Usina C", "resp_nome": "Supervisor MG", "quando": _dia(6)},
        {"PartitionKey": "atn", "RowKey": "k2", "estado": "feita", "prazo": _dia(-3), "oque": "Fusível",
         "usina": "Usina E", "resp_nome": "Supervisor SP", "quando": _dia(2)},
        {"PartitionKey": "atn", "RowKey": "k3", "estado": "resolvida", "prazo": _dia(9), "oque": "Portão",
         "usina": "Usina F", "resp_nome": "COS", "quando": _dia(10), "os_gerada": "15077"},
        {"PartitionKey": "atn", "RowKey": "k4", "estado": "silenciada", "prazo": _dia(-5), "oque": "Ruído"},
    ]
    e = atencao.encaminhamentos().dados
    assert [i["chave"] for i in e["itens"]][0] == "k1"           # o aberto e vencido vem primeiro
    assert {i["chave"] for i in e["itens"]} == {"k1", "k2", "k3"}  # silenciada não é encaminhamento
    # a conta é a do App (_enc_resumo): "feita" já é fechado, e vencido só conta enquanto está aberto
    assert (e["resumo"]["abertos"], e["resumo"]["vencidos"], e["resumo"]["fechados"]) == (1, 1, 2)


def test_erro_de_leitura_vira_aviso_e_nao_quebra(app_campo):
    def quebra(nome):
        raise RuntimeError("Storage fora")
    tabelas.usar_fornecedor(quebra)
    atencao.limpar_cache()
    leitura = atencao.central(14)
    # as regras do App engolem erro de tabela e devolvem a fila vazia; a tela tem de dizer que não leu
    assert leitura.erro


def test_sem_fonte_do_nexus_a_tela_fica_no_painel_do_app(app):
    """Levi, 04/10: "não quero ligação com Azure". Nem com variáveis de chave no ambiente o Nexus lê o Storage do App:
    sem a fonte do banco do Nexus, cada tela segue no painel do App."""
    with app.app_context():
        app.config["NEXUS_CAMPO_CONTA"] = "conta"
        app.config["NEXUS_CAMPO_SAS_RONDAS"] = "sv=teste"
        assert not tabelas.configurado(atencao.TABELAS)
        with pytest.raises(tabelas.SemFonte):
            tabelas.tabela("rondas")


def test_nexus_nao_usa_biblioteca_do_azure():
    """O Nexus vai para um servidor sem Azure: nenhum módulo dele importa o SDK do Azure."""
    raiz = Path(__file__).resolve().parent.parent
    for arq in list((raiz / "nexus").rglob("*.py")) + list((raiz / "ferramentas").rglob("*.py")):
        if "oscreator" in arq.parts:      # o clone do OS Creator é cópia do oem e fica como lá
            continue
        texto = arq.read_text(encoding="utf-8", errors="replace")
        assert not re.search(r"^\s*(from|import)\s+azure\b", texto, re.M), arq


# ── a tela ──────────────────────────────────────────────────────────────────────────────────────────────────────


def test_sem_chave_a_tela_continua_no_painel_do_app(logado):
    html = logado.get("/t/campo/atencao").get_data(as_text=True)
    assert '<iframe class="campo-moldura"' in html


def test_com_chave_a_tela_e_do_nexus(logado, app_campo):
    app_campo["rondaativos"] = [{"PartitionKey": "usina", "RowKey": "a", "usina": "Usina A", "cluster": "SP 01",
                                 "trk_n": 10, "inv_n": 2}]
    app_campo["rondas"] = [{"PartitionKey": _dia(20), "RowKey": "r1", "usina": "Usina A", "finalizada": True}]
    app_campo["atencaoos"] = [{"PartitionKey": "os", "RowKey": "lote", "quando": "x",
                               "pontos": json.dumps([_ponto_os("os_falha", "Usina A", 2, "Termografia")])}]
    html = logado.get("/t/campo/atencao").get_data(as_text=True)
    assert "<iframe" not in html
    assert "Pontos de atenção" in html and "Sem ronda há 20 dias" in html and "Termografia" in html
    assert 'class="campo-nativa"' in html
    # parados há mais de 7 dias: só o de 20 dias fica
    html = logado.get("/t/campo/atencao?f=velhos").get_data(as_text=True)
    assert "Sem ronda há 20 dias" in html and "Termografia" not in html
    # filtro por tipo
    html = logado.get("/t/campo/atencao?tipo=os_falha").get_data(as_text=True)
    assert "Termografia" in html and "Sem ronda há 20 dias" not in html


def test_aba_encaminhamentos_nativa(logado, app_campo):
    app_campo["decisoes"] = [{"PartitionKey": "atn", "RowKey": "k1", "estado": "encaminhada", "prazo": _dia(2),
                              "oque": "Limpeza do eletrocentro", "usina": "Usina C", "resp_nome": "Supervisor MG",
                              "quando": _dia(6)}]
    html = logado.get("/t/campo/atencao?aba=enc").get_data(as_text=True)
    assert "Limpeza do eletrocentro" in html and "Supervisor MG" in html and "Vencido" in html


def test_tela_com_erro_avisa_e_leva_ao_app(logado, app_campo):
    def quebra(nome):
        raise RuntimeError("Storage fora")
    tabelas.usar_fornecedor(quebra)
    atencao.limpar_cache()
    html = logado.get("/t/campo/atencao").get_data(as_text=True)
    assert "Não consegui ler as tabelas do App" in html
    assert "Abrir no App" in html
