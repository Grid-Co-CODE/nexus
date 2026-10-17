"""Os técnicos por usina do PCM (17/10/2026, nexus/pcm/atribuicoes.py).

Levi, 17/10/2026: "cria uma estrutura que liga usina e técnico e o PCM pode editar a vontade" e "é normal usinas terem
dois técnicos e receberem de vez em quando mais técnicos". O que estes testes seguram: vale a última decisão de cada
usina × pessoa × papel; o apoio com data final (vale no último dia) e com data de início (agendado até lá); o dia de
Brasília; a mesma decisão não grava de novo e tirar quem não está é recusado; datas ruins; a leitura que falha não grava;
nada em claro no livro (a API do banco tem leitura aberta); a assinatura igual à do contrato com o App; e várias decisões
numa gravação só. Nada vai ao banco: o livro é um arquivo (`NEXUS_PCM_ATRIBUICOES_ARQUIVO`)."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from nexus.cadastro.cifra import gerar_chave
from nexus.pcm import atribuicoes as A

PESSOA = {"email": "pessoa.teste@exemplo.com", "nome": "Pessoa Teste"}
U1 = {"usina_id": 1, "usina_fracttal": "Cliente A - Usina 1 - SP"}


@pytest.fixture
def cfg(tmp_path):
    A.limpar()
    return {"TESTING": True, "NEXUS_PCM_ATRIBUICOES_ARQUIVO": str(tmp_path / "atribuicoes.json"),
            "NEXUS_CHAVE_CADASTRO": gerar_chave(), "NEXUS_PESSOA_HMAC": "chave-hmac-de-teste"}


class Relogio:
    """O `_agora` do módulo andando um minuto por chamada: cada decisão com a sua hora (16/10 12:00Z em diante)."""

    def __init__(self, monkeypatch, inicio=datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)):
        self.t = inicio
        monkeypatch.setattr(A, "_agora", self)

    def __call__(self):
        self.t += timedelta(minutes=1)
        return self.t


def _por(cfg, pessoa_id, na_usina=True, **kw):
    return A.decidir(cfg, **U1, pessoa_id=pessoa_id, pessoa_hmac=f"{pessoa_id:024d}", na_usina=na_usina,
                     usuario=PESSOA, **kw)


def _atuais(cfg, hoje=20261017):
    return A.atuais(A.ler(cfg, forcar=True), hoje)


def test_vale_a_ultima_decisao_de_cada_usina_pessoa_papel(cfg, monkeypatch):
    Relogio(monkeypatch)
    _por(cfg, 10)
    _por(cfg, 11)
    _por(cfg, 10, na_usina=False)
    at = _atuais(cfg)
    assert set(at) == {(1, 11, "executa")}
    assert at[(1, 11, "executa")]["status"] == "vale"


def test_apoio_vale_ate_o_ultimo_dia_e_agenda_o_futuro(cfg, monkeypatch):
    Relogio(monkeypatch)
    _por(cfg, 10, ate="2026-10-17")
    _por(cfg, 11, de="2026-10-20")
    _por(cfg, 12, de="2026-10-17", ate="2026-10-31")
    assert _atuais(cfg, 20261017)[(1, 10, "executa")]["status"] == "vale"
    assert (1, 10, "executa") not in _atuais(cfg, 20261018)
    assert _atuais(cfg, 20261017)[(1, 11, "executa")]["status"] == "agendado"
    assert _atuais(cfg, 20261020)[(1, 11, "executa")]["status"] == "vale"
    assert _atuais(cfg, 20261017)[(1, 12, "executa")]["status"] == "vale"


def test_decisao_as_23h30_de_brasilia_e_do_dia_de_brasilia(cfg, monkeypatch):
    monkeypatch.setattr(A, "_agora", lambda: datetime(2026, 10, 18, 2, 30, tzinfo=timezone.utc))
    _por(cfg, 10)
    linha = A.ler(cfg, forcar=True)["decisoes"][0]
    assert int(linha["data_id"]) == 20261017
    assert linha["decidida_em"] == "2026-10-18T02:30:00Z"
    assert A.hoje_id() == 20261017


def test_mesma_decisao_nao_grava_de_novo(cfg, monkeypatch):
    Relogio(monkeypatch)
    assert _por(cfg, 10)["gravou"] is True
    assert _por(cfg, 10)["gravou"] is False
    assert len(A.ler(cfg, forcar=True)["decisoes"]) == 1
    with pytest.raises(A.Recusada):
        _por(cfg, 11, na_usina=False)


def test_ate_antes_de_de_e_data_ruim_sao_recusadas(cfg, monkeypatch):
    Relogio(monkeypatch)
    with pytest.raises(A.Recusada):
        _por(cfg, 10, de="2026-10-20", ate="2026-10-19")
    with pytest.raises(A.Recusada):
        _por(cfg, 10, ate="20/10/2026")
    with pytest.raises(A.Recusada):
        _por(cfg, 10, ate="2026-10-16")           # o apoio que já acabou
    with pytest.raises(A.Recusada):
        _por(cfg, 10, papel="dono")
    assert A.ler(cfg, forcar=True)["decisoes"] == []


def test_leitura_que_falha_nao_grava(cfg, monkeypatch, tmp_path):
    Relogio(monkeypatch)
    _por(cfg, 10)
    antes = (tmp_path / "atribuicoes.json").read_text(encoding="utf-8")

    def cai(_cfg):
        raise ConnectionError("banco fora")
    monkeypatch.setattr(A, "_ler_cru", cai)
    with pytest.raises(A.Recusada):
        _por(cfg, 11)
    assert (tmp_path / "atribuicoes.json").read_text(encoding="utf-8") == antes


def test_nada_em_claro_no_livro(cfg, monkeypatch, tmp_path):
    Relogio(monkeypatch)
    _por(cfg, 10, obs="apoio nas férias do titular")
    txt = (tmp_path / "atribuicoes.json").read_text(encoding="utf-8")
    assert "férias" not in txt and "ferias" not in txt and "Pessoa Teste" not in txt and "@" not in txt
    linha = json.loads(txt)[A.ABA][0]
    assert set(linha) == set(A.CAB)
    h = A.historico(cfg, A.ler(cfg, forcar=True), 1)
    assert h[0]["obs"] == "apoio nas férias do titular"
    assert h[0]["acao"] == "pôs" and h[0]["pessoa_id"] == 10 and h[0]["quem_hmac"]


def test_historico_do_mais_novo_ao_mais_antigo(cfg, monkeypatch):
    Relogio(monkeypatch)
    _por(cfg, 10)
    _por(cfg, 10, na_usina=False)
    h = A.historico(cfg, A.ler(cfg, forcar=True), 1)
    assert [x["acao"] for x in h] == ["tirou", "pôs"]
    assert A.historico(cfg, A.ler(cfg, forcar=True), 2) == []


def test_assinatura_igual_a_do_contrato_com_o_app():
    linha = {"usina_fracttal": "Cliente A - Usina 1 - SP", "pessoa_hmac": "0123456789abcdef01234567",
             "papel": "executa", "na_usina": "sim", "de_data_id": "", "ate_data_id": 20261031,
             "decidida_em": "2026-10-17T17:05:00Z"}
    assert A.assinatura(linha, "chave-hmac-de-teste") == \
        "e00727b720f3fbba3bfed36b8d90ac1e721cefe87908dd016e4f74df9b2ff750"
    assert A.assinatura(linha, "") == ""


def test_cada_linha_gravada_vai_assinada(cfg, monkeypatch):
    Relogio(monkeypatch)
    _por(cfg, 10, ate="2026-10-31")
    linha = A.ler(cfg, forcar=True)["decisoes"][0]
    assert linha["assinatura"] == A.assinatura(linha, cfg["NEXUS_PESSOA_HMAC"])


def test_decidir_varias_grava_uma_vez(cfg, monkeypatch):
    Relogio(monkeypatch)
    chamadas = []
    original = A._gravar_cru
    monkeypatch.setattr(A, "_gravar_cru", lambda c, t: (chamadas.append(1), original(c, t)))
    pedidos = [dict(U1, pessoa_id=p, pessoa_hmac=f"{p:024d}", na_usina=True) for p in (10, 11, 12)]
    assert A.decidir_varias(cfg, pedidos, PESSOA, "carga_inicial") == 3
    assert len(chamadas) == 1
    dec = A.ler(cfg, forcar=True)["decisoes"]
    assert len(dec) == 3 and {d["origem"] for d in dec} == {"carga_inicial"}


def test_novo_nome_no_fracttal_ou_novo_codigo_grava_de_novo(cfg, monkeypatch):
    """A reemissão (a usina mudou de nome no Fracttal) e o e-mail corrigido no cadastro mudam o que o App lê: não é a
    "mesma decisão"."""
    Relogio(monkeypatch)
    _por(cfg, 10)
    r = A.decidir(cfg, usina_id=1, usina_fracttal="Cliente A - Usina 1 - SP (novo)", pessoa_id=10,
                  pessoa_hmac=f"{10:024d}", na_usina=True, usuario=PESSOA, origem="reemissao")
    assert r["gravou"] is True
    assert A.decidir(cfg, usina_id=1, usina_fracttal="Cliente A - Usina 1 - SP (novo)", pessoa_id=10,
                     pessoa_hmac="f" * 24, na_usina=True, usuario=PESSOA)["gravou"] is True
    assert _atuais(cfg)[(1, 10, "executa")]["usina_fracttal"] == "Cliente A - Usina 1 - SP (novo)"
