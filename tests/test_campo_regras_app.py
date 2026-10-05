"""A cópia das regras do App (nexus/campo/regras_app.py), que Aprovação, Ordens e Triagem usam, e o que o Nexus nunca
toca do App: a biblioteca do Azure, a conexão do Storage e a partição dos tokens do Fracttal.

Central de atenção e PT saíram da cópia em 05/10/2026: são contas do próprio Nexus (tests/test_campo_visao.py).
"""
import re
from pathlib import Path

import pytest

from nexus.campo import pessoas, regras_app, tabelas

FONTE_APP = Path(r"C:\Users\Levi Maia\OneDrive - GRID CO\Área de Trabalho\Grid Co_ - 4. O&M\11.Pré-Operação"
                 r"\6. PCM\09. Programação Semanal\App_Campo\middleware\function_app.py")


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


def test_chave_do_storage_no_ambiente_nao_liga_nada(app):
    """Levi, 04/10: "não quero ligação com Azure". Nem com variáveis de chave no ambiente o Nexus lê o Storage do App."""
    with app.app_context():
        app.config["NEXUS_CAMPO_CONTA"] = "conta"
        app.config["NEXUS_CAMPO_SAS_RONDAS"] = "sv=teste"
        assert not tabelas.configurado(("rondas", "decisoes"))
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


def test_nexus_nao_le_a_particao_dos_tokens_nem_a_das_pt():
    """Da tabela dos tokens do Fracttal o Nexus lê só o cadastro: os tokens ("tok") nunca, e a PT agora vem do livro
    pt_app_campo do banco."""
    dados = {"fracttaltokens": [{"PartitionKey": "tok", "RowKey": "alguem@exemplo.test", "token": "SEGREDO"},
                                {"PartitionKey": "pt", "RowKey": "pt1", "status": "aguardando"}]}
    tabelas.usar_fornecedor(lambda nome: TabelaFalsa(dados.setdefault(nome, [])))
    try:
        tok = pessoas.tabela_dos_tokens()
        for pk in ("tok", "pt"):
            with pytest.raises(PermissionError):
                tok.query_entities(f"PartitionKey eq '{pk}'")
        with pytest.raises(PermissionError):
            tok.get_entity("tok", "alguem@exemplo.test")
        with pytest.raises(PermissionError):
            tok.query_entities("RowKey eq 'x'")          # sem partição fixa também não
    finally:
        tabelas.usar_fornecedor(None)
