"""O Responsável UFV de cada usina no livro de técnicos por usina (30/10/2026, nexus/pcm/responsaveis.py).

Levi, 30/10/2026: "PT aguardando assinatura você manda para os responsáveis das UFVs do Nexus" (e o responsável também
assina). O que estes testes seguram: o responsável da ficha entra no livro no papel `responsavel`, assinado, com o 1º
nome do Fracttal e o código do e-mail; a volta sem mudança não grava; a ficha que troca de responsável tira o antigo; a
usina excluída ou sem responsável na ficha tira; sem código ou sem nome no Fracttal não entra, e a mesma pessoa que já
estava fica; o nome novo no Fracttal e o código novo vão de novo; o cadastro sem nenhum responsável, o livro ilegível, o
cadastro ilegível e a falta das chaves não gravam nada; o código vem do e-mail da ficha e, por cima, dos setores; e os
leitores do livro no Nexus (a tela, a Visão do responsável, os Extintores) seguem contando só o `executa`. Nada vai ao
banco: o livro é um arquivo (`NEXUS_PCM_ATRIBUICOES_ARQUIVO`)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from nexus.cadastro.cifra import gerar_chave
from nexus.pcm import atribuicoes as A
from nexus.pcm import responsaveis as R
from nexus.pcm import tecnicos_usina as TU


@pytest.fixture
def cfg(tmp_path):
    A.limpar()
    return {"TESTING": True, "NEXUS_PCM_ATRIBUICOES_ARQUIVO": str(tmp_path / "atribuicoes.json"),
            "NEXUS_CHAVE_CADASTRO": gerar_chave(), "NEXUS_PESSOA_HMAC": "chave-hmac-de-teste"}


@pytest.fixture(autouse=True)
def relogio(monkeypatch):
    """O `_agora` do livro andando um minuto por chamada (30/10 12:00Z em diante): cada decisão com a sua hora."""
    t = {"t": datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)}

    def agora():
        t["t"] += timedelta(minutes=1)
        return t["t"]
    monkeypatch.setattr(A, "_agora", agora)


def cod(pid, versao=0):
    return f"{pid + 1000 * versao:024x}"


def base(usinas, fracttal=None):
    """O cadastro como o `visao._Base`: `por_id` (as usinas) e `de_para` (os nomes no Fracttal)."""
    fracttal = {1: ["Cliente A - Usina 1 - SP"], 2: ["Cliente B - Usina 2 - MG", "Cliente B - Usina 2 (antiga)"],
                3: ["Cliente C - Usina 3 - BA"]} if fracttal is None else fracttal
    dp = [{"usina_id": uid, "sistema": TU.SISTEMA_FRACTTAL, "chave_externa": n} for uid, ns in fracttal.items()
          for n in ns]
    return SimpleNamespace(por_id={u["usina_id"]: u for u in usinas}, de_para=dp, pessoas=[])


def usina(uid, resp=None, **kw):
    return dict({"usina_id": uid, "nome": f"Usina {uid}", "responsavel_om_id": resp, "excluido": "nao"}, **kw)


def resp(cfg):
    """{usina_id: (pessoa_id, usina_fracttal, pessoa_hmac)} dos responsáveis que valem hoje no livro."""
    est = A.ler(cfg, forcar=True)
    return {uid: (pid, x["usina_fracttal"], x["pessoa_hmac"])
            for (uid, pid, _p), x in A.atuais(est, A.hoje_id(), papel=R.PAPEL).items()}


def linhas(cfg):
    return A.ler(cfg, forcar=True)["decisoes"]


CODIGOS = {10: cod(10), 11: cod(11), 12: cod(12)}


def test_o_responsavel_da_ficha_entra_assinado_com_o_nome_do_fracttal_e_o_codigo(cfg):
    r = R.sincronizar(cfg, base=base([usina(1, 10), usina(2, 11), usina(3)]), codigo_da=CODIGOS)
    assert r["gravadas"] == 2 and r["por"] == 2 and r["tirar"] == 0
    assert r["usinas"] == 3 and r["com_responsavel"] == 2
    # o 1º nome do Fracttal em ordem alfabética, o mesmo que vai ao App no `executa`
    assert resp(cfg) == {1: (10, "Cliente A - Usina 1 - SP", cod(10)), 2: (11, "Cliente B - Usina 2 (antiga)", cod(11))}
    for x in linhas(cfg):
        assert x["papel"] == "responsavel" and x["origem"] == "cadastro" and x["na_usina"] == "sim"
        assert not x["de_data_id"] and not x["ate_data_id"] and not x["dados_cifrados"]      # o livro guarda vazio
        assert x["assinatura"] == A.assinatura(x, cfg["NEXUS_PESSOA_HMAC"])


def test_a_volta_sem_mudanca_nao_grava(cfg):
    b = base([usina(1, 10), usina(2, 11)])
    R.sincronizar(cfg, base=b, codigo_da=CODIGOS)
    n = len(linhas(cfg))
    r = R.sincronizar(cfg, base=b, codigo_da=CODIGOS)
    assert r["gravadas"] == 0 and r["por"] == 2 and r["tirar"] == 0
    assert len(linhas(cfg)) == n


def test_a_ficha_que_troca_de_responsavel_tira_o_antigo_e_poe_o_novo(cfg):
    R.sincronizar(cfg, base=base([usina(1, 10), usina(2, 11)]), codigo_da=CODIGOS)
    r = R.sincronizar(cfg, base=base([usina(1, 12), usina(2, 11)]), codigo_da=CODIGOS)
    assert r["tirar"] == 1 and r["gravadas"] == 2
    assert resp(cfg) == {1: (12, "Cliente A - Usina 1 - SP", cod(12)), 2: (11, "Cliente B - Usina 2 (antiga)", cod(11))}
    # o tirar leva o nome e o código da linha que pôs (é o par que o App confere)
    tirou = [x for x in linhas(cfg) if x["na_usina"] == "nao"]
    assert [(x["usina_id"], x["pessoa_id"], x["usina_fracttal"], x["pessoa_hmac"]) for x in tirou] == [
        (1, 10, "Cliente A - Usina 1 - SP", cod(10))]


def test_a_usina_sem_responsavel_na_ficha_ou_excluida_tira(cfg):
    R.sincronizar(cfg, base=base([usina(1, 10), usina(2, 11), usina(3, 12)]), codigo_da=CODIGOS)
    r = R.sincronizar(cfg, base=base([usina(1), usina(2, 11, excluido="sim"), usina(3, 12)]), codigo_da=CODIGOS)
    assert r["tirar"] == 2
    assert set(resp(cfg)) == {3}


def test_sem_codigo_ou_sem_fracttal_nao_entra_e_a_mesma_pessoa_fica(cfg):
    R.sincronizar(cfg, base=base([usina(1, 10), usina(2, 11)]), codigo_da=CODIGOS)
    # a leitura do código falhou para a 10 e a usina 2 perdeu o de-para: as duas ficam como estavam
    r = R.sincronizar(cfg, base=base([usina(1, 10), usina(2, 11), usina(3, 12)], fracttal={1: ["Cliente A - Usina 1 - SP"],
                                                                                          3: ["Cliente C - Usina 3 - BA"]}),
                      codigo_da={11: cod(11)})
    assert r["sem_codigo"] == 2 and r["sem_fracttal"] == 1 and r["tirar"] == 0 and r["gravadas"] == 0
    assert set(resp(cfg)) == {1, 2}


def test_a_ficha_troca_para_quem_nao_tem_codigo_o_antigo_sai_mesmo_assim(cfg):
    R.sincronizar(cfg, base=base([usina(1, 10)]), codigo_da=CODIGOS)
    r = R.sincronizar(cfg, base=base([usina(1, 13)]), codigo_da=CODIGOS)
    assert r["tirar"] == 1 and r["sem_codigo"] == 1 and r["por"] == 0
    assert resp(cfg) == {}


def test_o_nome_novo_no_fracttal_e_o_codigo_novo_vao_de_novo(cfg):
    R.sincronizar(cfg, base=base([usina(1, 10), usina(2, 11)]), codigo_da=CODIGOS)
    r = R.sincronizar(cfg, base=base([usina(1, 10), usina(2, 11)], fracttal={1: ["Cliente A - Usina 1 - SP (nova)"],
                                                                             2: ["Cliente B - Usina 2 - MG"]}),
                      codigo_da={10: cod(10), 11: cod(11, versao=1)})
    assert r["gravadas"] == 2 and r["tirar"] == 0
    assert resp(cfg) == {1: (10, "Cliente A - Usina 1 - SP (nova)", cod(10)),
                         2: (11, "Cliente B - Usina 2 - MG", cod(11, versao=1))}


def test_o_cadastro_sem_nenhum_responsavel_nao_grava(cfg):
    R.sincronizar(cfg, base=base([usina(1, 10), usina(2, 11)]), codigo_da=CODIGOS)
    n = len(linhas(cfg))
    r = R.sincronizar(cfg, base=base([usina(1), usina(2)]), codigo_da=CODIGOS)
    assert "recusou" in r and "gravadas" not in r
    assert len(linhas(cfg)) == n and set(resp(cfg)) == {1, 2}
    assert "recusou" in R.sincronizar(cfg, base=base([]), codigo_da=CODIGOS)


def test_o_livro_ilegivel_nao_grava(cfg, monkeypatch):
    monkeypatch.setattr(A, "ler", lambda cfg, forcar=False: {"decisoes": [], "erro": "ConnectionError: fora"})
    r = R.sincronizar(cfg, base=base([usina(1, 10)]), codigo_da=CODIGOS)
    assert "recusou" in r and "gravadas" not in r


def test_o_cadastro_ilegivel_nao_grava(cfg, monkeypatch):
    def falha():
        raise TU.SemCadastro("ConnectionError")
    monkeypatch.setattr(TU, "ler_base", falha)
    r = R.sincronizar(cfg, codigo_da=CODIGOS)
    assert "recusou" in r and "ConnectionError" in r["recusou"]
    assert linhas(cfg) == []


def test_sem_as_chaves_nao_grava(cfg):
    sem_hmac = dict(cfg, NEXUS_PESSOA_HMAC="")
    assert "recusou" in R.sincronizar(sem_hmac, base=base([usina(1, 10)]), codigo_da=CODIGOS)
    sem_cadastro = dict(cfg, NEXUS_CHAVE_CADASTRO="")
    assert "recusou" in R.sincronizar(sem_cadastro, base=base([usina(1, 10)]))
    assert linhas(cfg) == []


def test_o_codigo_vem_do_email_da_ficha_e_por_cima_dos_setores(cfg, monkeypatch):
    from nexus.cadastro import setores as S
    from nexus.campo import ligacao_cadastro, visao
    monkeypatch.setattr(ligacao_cadastro, "mapas_de", lambda cfg, de_para, pessoas: {"hmac": {cod(10): 10, cod(11): 11}})
    monkeypatch.setattr(visao, "_base", lambda: "http://banco")
    monkeypatch.setattr(visao, "_sessao", lambda: None)
    monkeypatch.setattr(S, "ler", lambda base, sessao: {"decisoes": [
        {"pessoa_id": 11, "pessoa_hmac": cod(11, versao=2), "decidida_em": "2026-10-02T00:00:00Z"},
        {"pessoa_id": 11, "pessoa_hmac": cod(11, versao=1), "decidida_em": "2026-10-01T00:00:00Z"},
        {"pessoa_id": None, "pessoa_hmac": cod(99), "decidida_em": "2026-10-03T00:00:00Z"}]})
    assert R.codigos(cfg, base([])) == {10: cod(10), 11: cod(11, versao=2)}

    def fora(base, sessao):
        raise ConnectionError("fora")
    monkeypatch.setattr(S, "ler", fora)
    assert R.codigos(cfg, base([])) == {10: cod(10), 11: cod(11)}


def test_os_leitores_do_nexus_seguem_contando_so_o_executa(cfg):
    A.decidir(cfg, usina_id=1, usina_fracttal="Cliente A - Usina 1 - SP", pessoa_id=10, pessoa_hmac=cod(10),
              na_usina=True, usuario=None)
    R.sincronizar(cfg, base=base([usina(1, 10), usina(2, 11)]), codigo_da=CODIGOS)
    est, hoje = A.ler(cfg, forcar=True), A.hoje_id()
    assert set(A.atuais(est, hoje)) == {(1, 10, "executa")}
    assert set(A.atuais(est, hoje, papel=None)) == {(1, 10, "executa"), (1, 10, "responsavel"), (2, 11, "responsavel")}
    assert [h["acao"] for h in A.historico(cfg, est, 1)] == ["pôs"]
    assert len(A.historico(cfg, est, 1, papel=None)) == 2
    # tirar o responsável não mexe no técnico da mesma usina
    R.sincronizar(cfg, base=base([usina(1, 12), usina(2, 11)]), codigo_da=CODIGOS)
    assert set(A.atuais(A.ler(cfg, forcar=True), hoje)) == {(1, 10, "executa")}


def test_o_papel_e_a_origem_novos_sao_os_unicos_aceitos(cfg):
    with pytest.raises(A.Recusada):
        A.decidir_varias(cfg, [{"usina_id": 1, "usina_fracttal": "X", "pessoa_id": 10, "pessoa_hmac": cod(10),
                                "na_usina": True, "papel": "supervisor"}], None, R.ORIGEM)
    with pytest.raises(A.Recusada):
        A.decidir_varias(cfg, [{"usina_id": 1, "usina_fracttal": "X", "pessoa_id": 10, "pessoa_hmac": cod(10),
                                "na_usina": True, "papel": R.PAPEL}], None, "robo")


def test_desligado_numa_maquina_nao_sobe_o_laco(monkeypatch):
    monkeypatch.setitem(R._LACO, "thread", None)
    R.ligar(SimpleNamespace(config={"NEXUS_RESPONSAVEIS": "0"}))
    assert R._LACO["thread"] is None
