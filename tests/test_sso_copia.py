"""A cópia do SSO da zeladoria para o banco do Nexus (12/11/2026): as partes da exportação viram um livro por módulo,
com o dado pessoal cifrado, e voltam iguais na leitura. Banco falso; pessoas e empresas fictícias."""
from datetime import datetime, timezone

import pytest

from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.dados import catalogo
from nexus.sso import copia, leitura
from nexus.sso import tabelas as T
from tests.pg_falso import ApiPGFalsa

AGORA = datetime(2026, 11, 12, 13, 0, tzinfo=timezone.utc)
CHAVE = gerar_chave()
ASSINATURA = "data:image/png;base64," + "A" * 70000          # maior que uma célula do xlsx: vai partida


def _partes():
    tipos = {
        "integracao_video.sessoes_video": [["id", "uuid"], ["titulo", "text"], ["perguntas_quiz", "jsonb"], ["ativo", "boolean"]],
        "integracao_video.visualizacoes": [["id", "uuid"], ["sessao_id", "uuid"], ["concluido", "boolean"]],
        "integracao_video.presencas": [["id", "uuid"], ["nome_completo", "text"], ["cpf", "text"], ["email", "text"],
                                       ["telefone", "text"], ["usina", "text"], ["status_aprovacao", "text"],
                                       ["assinatura_base64", "text"], ["nota_quiz", "integer"],
                                       ["criado_em", "timestamp with time zone"]],
        "integracao_video.perfis": [["user_id", "uuid"], ["email", "text"], ["status", "text"]],
        "apr.submissoes": [["id", "uuid"], ["usina", "text"], ["empresa_contratada", "text"], ["assinaturas", "jsonb"],
                           ["data_liberacao", "date"]],
        "epi.checklists": [["id", "uuid"], ["servico", "text"], ["colaborador", "text"], ["itens", "jsonb"]],
        "public.checklists": [["id", "uuid"], ["fase", "text"], ["fornecedor_nome", "text"], ["dados", "jsonb"]],
        "diario.registros": [["id", "uuid"], ["usina", "text"], ["data", "date"], ["responsavel", "text"], ["fotos", "jsonb"]],
        "diario.usinas": [["nome", "text"]],
        "cronograma.periodos": [["id", "uuid"], ["usina", "text"], ["fornecedor", "text"], ["servicos", "text[]"]],
        "cronograma.periodos_historico": [["id", "uuid"], ["periodo_id", "uuid"], ["acao", "text"], ["alterado_por", "text"]],
        "cronograma.fornecedores": [["nome", "text"]],
    }
    chaves = {t: "id" for t in tipos} | {"integracao_video.perfis": "user_id", "diario.usinas": "nome",
                                         "cronograma.fornecedores": "nome"}
    tabelas = {
        "integracao_video.sessoes_video": [{"id": "s1", "titulo": "Integração", "perguntas_quiz": [{"pergunta": "?", "correta": 0}], "ativo": True}],
        "integracao_video.visualizacoes": [{"id": "v1", "sessao_id": "s1", "concluido": False}],
        "integracao_video.presencas": [{"id": "p1", "nome_completo": "Fulano de Tal", "cpf": "000.000.000-00",
                                        "email": "fulano@exemplo.test", "telefone": "(00) 0000-0000", "usina": "Usina Teste",
                                        "status_aprovacao": "pendente", "assinatura_base64": ASSINATURA, "nota_quiz": 4,
                                        "criado_em": "2026-11-10T12:00:00+00:00"}],
        "integracao_video.perfis": [{"user_id": "u1", "email": "gestor@exemplo.test", "status": "aprovado"}],
        "apr.submissoes": [{"id": "a1", "usina": "Usina Teste", "empresa_contratada": "Empresa X",
                            "assinaturas": [{"nome": "Beltrano", "assinatura_base64": ASSINATURA}],
                            "data_liberacao": "2026-11-09"}],
        "epi.checklists": [{"id": "e1", "servico": "rocagem", "colaborador": "Ciclano", "itens": [{"item": "Luva", "status": "ok"}]}],
        "public.checklists": [{"id": "c1", "fase": "antes", "fornecedor_nome": "Fulano", "dados": {"usina": "Usina Teste"}}],
        "diario.registros": [{"id": "d1", "usina": "Usina Teste", "data": "2026-11-08", "responsavel": "Beltrano", "fotos": []}],
        "diario.usinas": [{"nome": "Usina Teste"}],
        "cronograma.periodos": [{"id": "c1", "usina": "Usina Teste", "fornecedor": "Fornecedor MEI", "servicos": ["rocagem"]}],
        "cronograma.periodos_historico": [{"id": "h1", "periodo_id": "c1", "acao": "criado", "alterado_por": "gestor@exemplo.test"}],
        "cronograma.fornecedores": [{"nome": "Fornecedor MEI"}],
    }
    arquivos = [{"bucket": "epi-fotos", "caminho": "e1/item-1-luva.jpg", "bytes": 1234, "tipo": "image/jpeg",
                 "criado_em": "2026-11-08T10:00:00+00:00"}]
    um = {"parte": "apr", "gerado_em": "2026-11-12T12:32:00+00:00",
          "tabelas": {"apr.submissoes": tabelas.pop("apr.submissoes")}}
    resto = {"parte": "resto", "gerado_em": "2026-11-12T12:40:00+00:00", "tipos": tipos, "chaves": chaves,
             "arquivos": arquivos, "tabelas": tabelas}
    return [um, resto]


def _gravar(api):
    return copia.copiar(_partes(), cofre=Cofre(CHAVE), base="http://pg.falso", token="t", sessao=api, gravar=True,
                        agora=AGORA)


def test_um_livro_por_modulo_e_volta_igual():
    api = ApiPGFalsa(como_texto=True)
    rel = _gravar(api)
    assert rel["gravou"] and all(a["origem"] == a["nexus"] for a in rel["abas"].values())
    assert rel["exportado_em"] == "2026-11-12T12:32:00+00:00"            # a parte mais antiga
    est = leitura.ler_banco("http://pg.falso", api, Cofre(CHAVE))
    p = est["abas"]["iv_presencas"][0]
    assert (p["cpf"], p["email"], p["nota_quiz"], p["assinatura_base64"]) == ("000.000.000-00", "fulano@exemplo.test", 4,
                                                                              ASSINATURA)
    assert est["abas"]["apr_submissoes"][0]["assinaturas"][0]["assinatura_base64"] == ASSINATURA
    assert est["abas"]["iv_sessoes_video"][0]["ativo"] is True
    assert est["abas"]["cronograma_periodos"][0]["servicos"] == ["rocagem"]
    assert est["abas"]["arquivos"][0]["chave"] == "epi-fotos/e1/item-1-luva.jpg"
    assert est["abas"]["vistoria_checklists"][0]["dados"] == {"usina": "Usina Teste"}


def test_o_pessoal_vai_cifrado_e_o_que_liga_fica_em_claro():
    api = ApiPGFalsa()
    _gravar(api)
    bruto = api.linhas(T.LIVRO_INTEGRACAO, "iv_presencas")[0]
    for c in ("nome_completo", "cpf", "email", "telefone", "assinatura_base64"):
        assert Cofre.eh_cifrado(bruto[c]), c
    assert bruto["status_aprovacao"] == "pendente"
    assert Cofre.eh_cifrado(api.linhas(T.LIVRO_CRONOGRAMA, "cronograma_fornecedores")[0]["nome"])   # o MEI é pessoa
    # a usina é texto que o fornecedor digita (já veio nome de pessoa nela): cifrada, na linha e na lista do diário
    assert Cofre.eh_cifrado(bruto["usina"])
    assert Cofre.eh_cifrado(api.linhas(T.LIVRO_DIARIO, "diario_usinas")[0]["nome"])
    texto = repr(api.linhas(T.LIVRO_APR, "apr_submissoes"))
    assert "Beltrano" not in texto and "Empresa X" not in texto


def test_exportacao_incompleta_nao_grava_e_a_copia_nao_passa_por_cima():
    partes = _partes()
    del partes[1]["tabelas"]["diario.registros"]
    api = ApiPGFalsa()
    with pytest.raises(copia.ExportacaoIncompleta, match="diario.registros"):
        copia.copiar(partes, cofre=Cofre(CHAVE), base="http://pg.falso", token="t", sessao=api, gravar=True, agora=AGORA)
    assert not api.linhas(T.LIVRO_DIARIO, "diario_registros")
    _gravar(api)
    for x in api.abas[(T.LIVRO_APR, "atualizacao")]["linhas"]:             # o Nexus já gravou uma mudança
        x["values"][x["headers"].index("versao")] = 1
    with pytest.raises(copia.CopiaRecusada):
        _gravar(api)


def test_os_livros_estao_no_catalogo():
    nomes = {lv.nome: lv for lv in catalogo.LIVROS}
    for livro in T.LIVROS:
        assert livro in nomes and "atualizacao" in nomes[livro].abas
    assert nomes[T.LIVRO_CRONOGRAMA].so_cresce == ("cronograma_historico",)
    for aba in T.TABELAS:
        assert aba in catalogo.ABAS_FORA_DA_REGRA or aba in T.HISTORICO
