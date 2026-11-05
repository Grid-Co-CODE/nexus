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


def _fichas(cfg, emails: dict, desligadas=()):
    """O cadastro de pessoas com o e-mail de cada ficha cifrado, como o banco o guarda (e-mails de mentira)."""
    import json
    from nexus.cadastro.cifra import Cofre
    cofre = Cofre(cfg["NEXUS_CHAVE_CADASTRO"])
    return [{"pessoa_id": pid, "excluido": "não", "status": "Desligado" if pid in desligadas else "Ativo",
             "sensivel_cifrado": cofre.cifrar(json.dumps({"nome": f"Pessoa {pid}", "email": e}), f"banco/pessoas/{pid}")}
            for pid, e in emails.items()]


def _setores(monkeypatch, decisoes):
    """As decisões de Pessoas e setores (o usuário do Fracttal ligado à ficha), dubladas: o `S.ler` de mentira."""
    from nexus.cadastro import setores as S
    from nexus.campo import visao
    monkeypatch.setattr(visao, "_base", lambda: "http://banco")
    monkeypatch.setattr(visao, "_sessao", lambda: None)
    if isinstance(decisoes, Exception):
        def fora(base, sessao):
            raise decisoes
        monkeypatch.setattr(S, "ler", fora)
    else:
        monkeypatch.setattr(S, "ler", lambda base, sessao: {"decisoes": decisoes})


def _h(cfg, email):
    from nexus.campo.ligacao_cadastro import codigo_da_pessoa
    return codigo_da_pessoa(cfg["NEXUS_PESSOA_HMAC"], email)


def _lig(fid, pid, codigo, quando):
    return {"fracttal_id": fid, "pessoa_id": pid, "pessoa_hmac": codigo, "decidida_em": quando}


def test_o_codigo_vem_do_email_da_ficha_e_por_cima_dos_setores(cfg, monkeypatch):
    fichas = SimpleNamespace(pessoas=_fichas(cfg, {10: "t10@exemplo.test", 11: "t11@exemplo.test"}))
    _setores(monkeypatch, [_lig(501, 11, cod(11, versao=2), "2026-10-02T00:00:00Z"),
                           _lig(501, 11, cod(11, versao=1), "2026-10-01T00:00:00Z"),
                           _lig(502, None, cod(99), "2026-10-03T00:00:00Z")])
    assert R.codigos(cfg, fichas) == {10: _h(cfg, "t10@exemplo.test"), 11: cod(11, versao=2)}
    _setores(monkeypatch, ConnectionError("fora"))
    assert R.codigos(cfg, fichas) == {10: _h(cfg, "t10@exemplo.test"), 11: _h(cfg, "t11@exemplo.test")}


def test_so_vale_a_ligacao_de_hoje_de_cada_usuario_do_fracttal(cfg, monkeypatch):
    """Revisão de 05/11/2026 (achado 4): o usuário do Fracttal 501 ligado à ficha 11 e, depois, religado à 10. Contando
    toda decisão, a 11 ficava com o código dele pela ligação velha (e a 10 também): o código ia a quem não é mais."""
    fichas = SimpleNamespace(pessoas=_fichas(cfg, {10: "", 11: ""}))
    _setores(monkeypatch, [_lig(501, 11, cod(500), "2026-10-12T12:00:00Z"),
                           _lig(501, 10, cod(500), "2026-10-20T12:00:00Z")])
    codigos, ambiguos = R.codigos_e_ambiguos(cfg, fichas)
    assert codigos == {10: cod(500)} and ambiguos == {}
    # o usuário desligado de toda ficha (setor tirado sem ficha) não deixa o código em ninguém
    _setores(monkeypatch, [_lig(501, 11, cod(500), "2026-10-12T12:00:00Z"),
                           _lig(501, None, cod(500), "2026-10-20T12:00:00Z")])
    assert R.codigos(cfg, fichas) == {}


def test_a_ligacao_do_fracttal_vence_o_email_de_outra_ficha_e_email_com_email_sai_das_duas(cfg, monkeypatch):
    """O código que cai em duas fichas: quando um deles vem da ligação do Fracttal (Pessoas e setores), vence a ligação
    (a ficha ligada fica com ele, a outra perde, com o porquê); o mesmo e-mail em duas fichas não é de nenhuma (o App
    acharia uma pessoa e o Nexus diria outra). Re-revisão de 05/11/2026 (N2)."""
    fichas = SimpleNamespace(pessoas=_fichas(cfg, {10: "t10@exemplo.test", 11: "", 12: "dupla@exemplo.test",
                                                   13: "Dupla@Exemplo.test ", 14: "t14@exemplo.test"}))
    # o usuário do Fracttal com o e-mail da ficha 10 ligado à 11
    _setores(monkeypatch, [_lig(501, 11, _h(cfg, "t10@exemplo.test"), "2026-10-12T12:00:00Z")])
    codigos, por_que = R.codigos_e_ambiguos(cfg, fichas)
    assert codigos == {11: _h(cfg, "t10@exemplo.test"), 14: _h(cfg, "t14@exemplo.test")}
    assert por_que[10] == R.DE_OUTRA and por_que[12] == por_que[13] == R.AMBIGUO and set(por_que) == {10, 12, 13}
    assert R.codigos(cfg, fichas) == codigos
    # o código que cada ficha teria antes do desempate (05/11/2026): a aba dos administradores do App marca com o mesmo
    # porquê quem chega com o código que saiu das fichas (a pessoa de Pessoas e setores sem ficha, o e-mail do avulso)
    c = R.conta_dos_codigos(cfg, fichas)
    assert (c["codigos"], c["por_que"]) == (codigos, por_que)
    assert c["antes"][12] == c["antes"][13] == _h(cfg, "dupla@exemplo.test") and c["antes"][10] == _h(cfg, "t10@exemplo.test")


def test_a_pessoa_recontratada_so_a_ficha_nova_fica_com_o_codigo(cfg, monkeypatch):
    """Re-revisão de 05/11/2026 (N2): a ficha antiga, desligada, e a nova, ativa e ligada ao usuário do Fracttal, com o
    mesmo e-mail. A desligada (ou excluída) não entra na conta pelo e-mail: só a nova fica com o código, sem disputa."""
    email = "recontratada@exemplo.test"
    fichas = SimpleNamespace(pessoas=_fichas(cfg, {20: email, 21: email}, desligadas=(20,)))
    _setores(monkeypatch, [_lig(601, 21, _h(cfg, email), "2026-10-20T12:00:00Z")])
    assert R.codigos_e_ambiguos(cfg, fichas) == ({21: _h(cfg, email)}, {})
    # sem a ligação, a ficha nova fica com o código do e-mail, e a desligada não disputa
    _setores(monkeypatch, [])
    assert R.codigos_e_ambiguos(cfg, fichas) == ({21: _h(cfg, email)}, {})


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
