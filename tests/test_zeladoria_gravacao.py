"""A gravação da Zeladoria pelo Nexus (etapa 4, 03/11/2026; Levi: "Salvo em 1 s, banco logo depois").

A mudança entra na hora no estado do servidor e num diário CIFRADO no disco, e o "Salvo" do app acende. O Nexus grava no
banco em lote (`persistir`), conferindo como sempre; o diário só esvazia depois do banco conferido, e é relido ao
subir: reiniciar o servidor não perde mudança. Banco falso: tests/pg_falso.py. Nomes e e-mails fictícios.
"""
import json
from datetime import datetime, timezone

import pytest

from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.dados import livros
from nexus.zeladoria import copia, gravacao, guardar, leitura
from nexus.zeladoria import tabelas as T
from tests.pg_falso import ApiPGFalsa
from tests.test_zeladoria_copia import DE_PARA, _exportacao

COFRE = Cofre(gerar_chave())
BASE = "http://pg.falso"
AGORA = datetime(2026, 11, 3, 18, 0, tzinfo=timezone.utc)
HEAD = {"id": "u-head", "email": "head@exemplo.com", "papel": "HEAD", "status": "aprovado"}
ANALISTA = {"id": "u-an", "email": "fulano@exemplo.com", "papel": "Analista", "status": "aprovado"}
PENDENTE = {"id": "nexus:abc", "email": "novo@exemplo.com", "papel": None, "status": "pendente"}


def _exp():
    exp = _exportacao()
    exp["tipos"]["cotacoes"] = [["id", "text"], ["valor", "numeric"], ["obs", "text"], ["criado_em", "timestamp with time zone"]]
    exp["tabelas"]["cotacoes"] = [{"id": "COT-1", "valor": 100, "obs": "a", "criado_em": None},
                                  {"id": "COT-2", "valor": 200, "obs": "b", "criado_em": None}]
    exp["tipos"]["log"] = [["id", "bigint"], ["em", "date"], ["quem", "text"], ["acao", "text"], ["alvo", "text"],
                           ["cotacao_id", "text"], ["obs", "text"], ["criado_em", "timestamp with time zone"]]
    exp["tabelas"]["log"] = [{"id": 7, "em": "2026-11-01", "quem": "head@exemplo.com", "acao": "criar", "alvo": "COT-1",
                              "cotacao_id": "COT-1", "obs": None, "criado_em": None}]
    exp["tipos"]["perfis"] = [["user_id", "uuid"], ["email", "text"], ["papel", "text"], ["status", "text"],
                              ["solicitado_em", "timestamp with time zone"]]
    exp["chaves"]["perfis"] = "user_id"
    exp["tabelas"]["perfis"] = [{"user_id": "u-head", "email": "head@exemplo.com", "papel": "HEAD", "status": "aprovado",
                                 "solicitado_em": None}]
    return exp


@pytest.fixture
def banco():
    api = ApiPGFalsa()
    copia.copiar(_exp(), de_para=DE_PARA, cofre=COFRE, base=BASE, token="t", sessao=api, gravar=True, agora=AGORA)
    return api


def _gravador(banco, tmp_path, sessao=None):
    g = gravacao.Gravador(base=BASE, token="t", sessao=sessao or banco, cofre=COFRE, diario=tmp_path / "diario.jsonl")
    g.carregar(leitura.ler_banco(BASE, banco, COFRE))
    return g


def _linhas(banco, aba):
    est = leitura.ler_banco(BASE, banco, COFRE)
    return {str(l.get(est["chaves"][aba])): l for l in est["abas"][aba]}


def test_mudanca_entra_na_hora_e_no_diario_cifrado(banco, tmp_path):
    g = _gravador(banco, tmp_path)
    r = g.aplicar([{"op": "upsert", "view": "rf_cotacoes", "linhas": [{"id": "COT-1", "valor": 150, "obs": "nota do fulano"}]}],
                  ANALISTA, base_versao=0)
    assert r["versao"] == 1 and r["outros_salvaram"] is False
    assert {l["id"]: l["valor"] for l in g.estado["abas"]["cotacoes"]}["COT-1"] == 150
    diario = (tmp_path / "diario.jsonl").read_text(encoding="utf-8")
    assert "fulano" not in diario and "COT-1" not in diario and diario.count("\n") == 1      # cifrado, uma linha
    assert _linhas(banco, "cotacoes")["COT-1"]["valor"] == 100                                # o banco ainda não
    assert g.situacao()["pendente"] is True


def test_persistir_grava_confere_e_esvazia_o_diario(banco, tmp_path):
    g = _gravador(banco, tmp_path)
    g.aplicar([{"op": "upsert", "view": "rf_cotacoes", "linhas": [{"id": "COT-1", "valor": 150}]}], ANALISTA, 0)
    g.persistir()
    assert _linhas(banco, "cotacoes")["COT-1"]["valor"] == 150
    assert _linhas(banco, "cotacoes")["COT-1"]["obs"] == "a"                 # o upsert mescla, não apaga coluna
    assert leitura.ler_banco(BASE, banco, COFRE)["versao"] == 1
    assert (tmp_path / "diario.jsonl").read_text(encoding="utf-8") == ""
    assert g.situacao() == {"pendente": False, "erro": None, "versao": 1, "versao_banco": 1}


def test_exclusao_deixa_rastro_no_registro(banco, tmp_path):
    g = _gravador(banco, tmp_path)
    g.aplicar([{"op": "delete", "view": "rf_cotacoes", "filtros": [["eq", "id", "COT-2"]]}], HEAD, 0)
    g.persistir()
    assert "COT-2" not in _linhas(banco, "cotacoes")
    rastro = [l for l in _linhas(banco, "log").values() if l["acao"] == "excluir-definitivo"]
    assert len(rastro) == 1 and rastro[0]["alvo"] == "cotacoes:COT-2" and rastro[0]["quem"] == "head@exemplo.com"
    assert rastro[0]["id"] == 8                                                # o id novo é o maior + 1


def test_insert_sem_id_ganha_o_proximo(banco, tmp_path):
    g = _gravador(banco, tmp_path)
    g.aplicar([{"op": "insert", "view": "rf_log", "linhas": [{"acao": "editar", "alvo": "COT-1", "quem": "fulano@exemplo.com"}]}],
              ANALISTA, 0)
    novo = [l for l in g.estado["abas"]["log"] if l["acao"] == "editar"][0]
    assert novo["id"] == 8 and novo["criado_em"] and novo["em"]               # o padrão que o banco do Radar dava


def test_outra_pessoa_salvou_antes_e_nada_se_perde(banco, tmp_path):
    g = _gravador(banco, tmp_path)
    g.aplicar([{"op": "upsert", "view": "rf_cotacoes", "linhas": [{"id": "COT-1", "valor": 111}]}], HEAD, 0)
    r = g.aplicar([{"op": "upsert", "view": "rf_cotacoes", "linhas": [{"id": "COT-2", "valor": 222}]}], ANALISTA, 0)
    assert r["outros_salvaram"] is True and r["sobrepostas"] == []
    r = g.aplicar([{"op": "upsert", "view": "rf_cotacoes", "linhas": [{"id": "COT-2", "valor": 223}]}], ANALISTA, 0)
    assert r["sobrepostas"] == []                                             # a mudança dele mesmo não avisa
    r = g.aplicar([{"op": "upsert", "view": "rf_cotacoes", "linhas": [{"id": "COT-1", "valor": 333}]}], ANALISTA, 0)
    assert r["sobrepostas"] == ["cotacoes:COT-1"]                             # os dois mexeram: vale a última, com aviso
    r = g.aplicar([{"op": "upsert", "view": "rf_cotacoes", "linhas": [{"id": "COT-2", "valor": 224}]}], HEAD, 4)
    assert r["outros_salvaram"] is False and r["sobrepostas"] == []           # quem recarregou já viu tudo
    valores = {l["id"]: l["valor"] for l in g.estado["abas"]["cotacoes"]}
    assert valores == {"COT-1": 333, "COT-2": 224}


def test_reiniciar_reaplica_o_diario(banco, tmp_path):
    g = _gravador(banco, tmp_path)
    g.aplicar([{"op": "upsert", "view": "rf_cotacoes", "linhas": [{"id": "COT-1", "valor": 150}]}], ANALISTA, 0)
    novo = _gravador(banco, tmp_path)                                         # o servidor reiniciou antes de gravar
    assert {l["id"]: l["valor"] for l in novo.estado["abas"]["cotacoes"]}["COT-1"] == 150
    assert novo.estado["versao"] == 1 and novo.situacao()["pendente"] is True
    novo.persistir()
    assert _linhas(banco, "cotacoes")["COT-1"]["valor"] == 150


class _BancoFora(ApiPGFalsa):
    def __init__(self, dentro):
        self.__dict__.update(dentro.__dict__)
        self.fora = True

    def post(self, *a, **k):
        if self.fora:
            raise ConnectionError("banco fora do ar")
        return super().post(*a, **k)


def test_banco_fora_do_ar_nao_perde_nada(banco, tmp_path):
    fora = _BancoFora(banco)
    g = _gravador(banco, tmp_path, sessao=fora)
    g.aplicar([{"op": "upsert", "view": "rf_cotacoes", "linhas": [{"id": "COT-1", "valor": 150}]}], ANALISTA, 0)
    with pytest.raises(Exception):
        g.persistir()
    s = g.situacao()
    assert s["pendente"] is True and s["erro"] and "fora" not in (tmp_path / "diario.jsonl").read_text()
    assert (tmp_path / "diario.jsonl").read_text(encoding="utf-8").count("\n") == 1
    fora.fora = False
    g.persistir()
    assert g.situacao()["erro"] is None and fora.linhas(T.LIVRO_APP, "cotacoes")


def test_so_aprovado_grava_e_perfis_so_o_head(banco, tmp_path):
    g = _gravador(banco, tmp_path)
    with pytest.raises(gravacao.Recusa):
        g.aplicar([{"op": "upsert", "view": "rf_cotacoes", "linhas": [{"id": "COT-1", "valor": 1}]}], PENDENTE, 0)
    with pytest.raises(gravacao.Recusa):
        g.aplicar([{"op": "update", "view": "rf_perfis", "patch": {"papel": "HEAD"},
                    "filtros": [["eq", "user_id", "u-head"]]}], ANALISTA, 0)
    assert g.estado["versao"] == 0                                            # nada entrou


def test_pessoa_nova_ganha_a_linha_pendente(banco, tmp_path):
    g = _gravador(banco, tmp_path)
    g.garantir_perfil(PENDENTE)
    g.garantir_perfil(PENDENTE)                                               # uma vez só
    novos = [p for p in g.estado["abas"]["perfis"] if p["user_id"] == "nexus:abc"]
    assert len(novos) == 1 and novos[0]["status"] == "pendente" and novos[0]["email"] == "novo@exemplo.com"


def test_a_copia_nao_passa_por_cima_do_que_o_nexus_gravou(banco, tmp_path):
    g = _gravador(banco, tmp_path)
    g.aplicar([{"op": "upsert", "view": "rf_cotacoes", "linhas": [{"id": "COT-1", "valor": 150}]}], ANALISTA, 0)
    g.persistir()
    with pytest.raises(copia.CopiaRecusada):
        copia.copiar(_exp(), de_para=DE_PARA, cofre=COFRE, base=BASE, token="t", sessao=banco, gravar=True, agora=AGORA)
    assert _linhas(banco, "cotacoes")["COT-1"]["valor"] == 150


class _CaiNoHistorico(ApiPGFalsa):
    """O banco grava o livro do app e cai antes do livro do histórico."""
    def __init__(self, dentro):
        self.__dict__.update(dentro.__dict__)
        self.cair = True

    def post(self, url, *a, **k):
        if self.cair and f"/{T.LIVRO_HISTORICO}/" in url:
            raise ConnectionError("caiu no meio")
        return super().post(url, *a, **k)


def test_banco_que_cai_entre_dois_livros_nao_perde_o_segundo(banco, tmp_path):
    cai = _CaiNoHistorico(banco)
    g = _gravador(banco, tmp_path, sessao=cai)
    g.aplicar([{"op": "upsert", "view": "rf_cotacoes", "linhas": [{"id": "COT-1", "valor": 150}]},
               {"op": "delete", "view": "rf_cotacoes", "filtros": [["eq", "id", "COT-2"]]}], HEAD, 0)
    with pytest.raises(Exception):
        g.persistir()
    est = leitura.ler_banco(BASE, banco, COFRE)
    assert est["versoes"][T.LIVRO_APP] == 1 and est["versoes"][T.LIVRO_HISTORICO] == 0     # gravou um, caiu no outro
    novo = _gravador(banco, tmp_path)                     # o servidor reiniciou: o rastro do histórico volta do diário
    assert [l["alvo"] for l in novo.estado["abas"]["log"] if l["acao"] == "excluir-definitivo"] == ["cotacoes:COT-2"]
    novo.persistir()
    assert [l["alvo"] for l in _linhas(banco, "log").values() if l["acao"] == "excluir-definitivo"] == ["cotacoes:COT-2"]


def test_o_historico_so_cresce(banco, tmp_path):
    g = _gravador(banco, tmp_path)
    with pytest.raises(gravacao.Recusa, match="só cresce"):
        g.aplicar([{"op": "delete", "view": "rf_log", "filtros": [["eq", "id", 7]]}], HEAD, 0)
    assert g.estado["versao"] == 0
