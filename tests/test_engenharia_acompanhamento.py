"""Engenharia > Confiabilidade: o acompanhamento dos ativos com sinal (Levi, 18/10/2026: "os membros de engenharia ou
administradores pegar aqueles ativos com sinal para acompanhar ou alguém da engenharia poder encaminhar para a pessoa
ver!"). Desenho em docs/superpowers/specs/2026-10-18-engenharia-acompanhamento-design.md. Banco falso
(tests/pg_falso.py); os nomes são fictícios."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest
import requests
from pg_falso import ApiPGFalsa

from nexus.cadastro.cifra import gerar_chave
from nexus.dados import catalogo, explica
from nexus.dados.equipamento import canon, equipamento_id
from nexus.engenharia import acompanhamento as A

BRT = timezone(timedelta(hours=-3))
ANA = {"email": "ana.lima@gridco.com.br", "nome": "Ana Lima"}
BETO = {"email": "beto.souza@gridco.com.br", "nome": "Beto Souza"}
ATIVO = {"cod": "IBI200-INVR1.3", "usina_id": 1, "usina_ligada_por": "de-para do Fracttal", "nivel": "critico",
         "nFalha": 5, "n7": 3}


def _no_banco(app, api):
    app.config.update(GRIDCO_DB_API="http://pg.falso", NEXUS_CHAVE_CADASTRO=gerar_chave(),
                      NEXUS_PESSOA_HMAC="hmac-teste", GRIDCO_SQL_TOKEN="tk")
    app.extensions["nexus_dados_sessao"] = api
    A.limpar()
    with app.app_context():
        yield api
    A.limpar()
    app.extensions.pop("nexus_dados_sessao", None)


@pytest.fixture
def banco(app):
    yield from _no_banco(app, ApiPGFalsa())


@pytest.fixture
def banco_texto(app):
    yield from _no_banco(app, ApiPGFalsa(como_texto=True))


def _como(cli, usuario, admin=False):
    with cli.session_transaction() as s:
        s["logado"], s["admin"], s["usuario"] = True, admin, usuario
    return cli


def _a():
    (a,) = A.estado(A.ler(forcar=True)["eventos"]).values()
    return a


def _aid():
    return _a()["id"]


def _aid_de(cod):
    return next((a["id"] for a in A.estado(A.ler(forcar=True)["eventos"]).values()
                 if a["aberto"] and canon(a["cod"]) == canon(cod)), None)


def _lista(html):
    """A lista da aba (os cartões), sem a gaveta nem os filtros."""
    return html.split('<div class="eg-itens">', 1)[1].split("</section>", 1)[0] if 'class="eg-itens"' in html else ""


def _dec(fracttal_id, setor_id, hmac, quando):
    return {"decidida_em": quando, "data_id": int(quando[:10].replace("-", "")), "fracttal_id": fracttal_id,
            "pessoa_id": None, "pessoa_ligada_por": "", "pessoa_hmac": hmac, "setor_id": setor_id,
            "decidida_por_hmac": "", "origem": "tela"}


# ── Task 1: o livro, a leitura, o estado e o Pegar ───────────────────────────────────────────────────────────────────
def test_catalogo_registra_o_livro_e_o_fato():
    l = catalogo.LIVRO_POR_NOME[A.LIVRO]
    assert l.abas == (A.ABA_DIAG, A.ABA_EVENTO) and all(catalogo.aba_segue_a_regra(x) for x in l.abas)
    f = catalogo.POR_ID["acompanhamento_ativo"]
    assert f.area == "engenharia" and f.tipo == "transacao" and f.chave == ("id",)
    assert f.fontes == (f"{A.LIVRO} · {A.ABA_EVENTO}",)
    assert {m.coluna for m in f.medidas} == {"falhas_30d_qtd", "falhas_7d_qtd"}
    assert "acompanhamento_ativo" in explica.RESUMO and "acompanhamento_ativo" in explica.PARA_QUE


def test_pegar_comeca_com_a_pessoa_e_o_inicio_hoje(banco):
    A.pegar(ATIVO, ANA, pode=True)
    (a,) = A.estado(A.ler(forcar=True)["eventos"]).values()
    assert a["aberto"] and a["responsavel"]["nome"] == "Ana Lima" and a["cod"] == "IBI200-INVR1.3"
    assert a["inicio"] == datetime.now(BRT).date() and a["fim"] is None and a["nivel_entrada"] == "critico"
    assert a["falhas30_entrada"] == 5 and a["falhas7_entrada"] == 3
    assert a["equipamento_id"] == equipamento_id("IBI200-INVR1.3") and a["usina_id"] == 1
    assert [d["nome"] for d in A.diagnosticos(banco.linhas(A.LIVRO, A.ABA_DIAG))] == ["Comunicação", "Disjuntor"]
    ev = banco.linhas(A.LIVRO, A.ABA_EVENTO)
    assert len(ev) == 1 and list(ev[0]) == list(A.CAB_EVENTO)
    assert ev[0]["evento"] == "pegou" and ev[0]["pessoa_hmac"] == ev[0]["responsavel_hmac"] == A.codigo(ANA)
    # a API do banco tem leitura aberta: nem o nome nem o e-mail em claro
    claro = json.dumps(ev, ensure_ascii=False, default=str).lower()
    assert "ana lima" not in claro and ANA["email"] not in claro


def test_pegar_recusa_sem_poder_sem_login_e_ativo_ja_acompanhado(banco):
    with pytest.raises(A.Recusada, match="Engenharia"):
        A.pegar(ATIVO, ANA, pode=False)
    with pytest.raises(A.Recusada, match="login"):
        A.pegar(ATIVO, None, pode=True)
    A.pegar(ATIVO, ANA, pode=True)
    # o mesmo ativo escrito de outro jeito (caixa, espaço) é o mesmo ativo
    with pytest.raises(A.Recusada, match="já está com Ana Lima"):
        A.pegar(dict(ATIVO, cod=" ibi200-invr1.3"), BETO, pode=True)
    assert len(banco.linhas(A.LIVRO, A.ABA_EVENTO)) == 1


def test_leitura_como_texto_da_o_mesmo_estado(banco_texto):
    # Review Focus 1: a API devolveu tudo como texto ("5", "20261018", "1")
    A.pegar(ATIVO, ANA, pode=True)
    assert isinstance(banco_texto.linhas(A.LIVRO, A.ABA_EVENTO)[0]["falhas_30d_qtd"], str)
    a = _a()
    assert a["falhas30_entrada"] == 5 and a["falhas7_entrada"] == 3 and a["usina_id"] == 1
    assert a["inicio"] == datetime.now(BRT).date() and a["aberto"]
    assert a["equipamento_id"] == equipamento_id("IBI200-INVR1.3")
    assert [d["id"] for d in A.diagnosticos(banco_texto.linhas(A.LIVRO, A.ABA_DIAG))] == [1, 2]


def test_banco_fora_nao_grava_e_a_leitura_diz(banco, monkeypatch):
    # Review Focus 4: "não consegui ler" não é "nenhum", e sem ler o livro nada se grava (gravaria por cima)
    monkeypatch.setattr(banco, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("fora")))
    lido = A.ler(forcar=True)
    assert lido["erro"] and lido["eventos"] == [] and lido["lido_em"] is None
    with pytest.raises(requests.ConnectionError):
        A.pegar(ATIVO, ANA, pode=True)
    assert banco.syncs == 0


# ── Task 2: encaminhar, salvar (dados e encerrar) e comentar ─────────────────────────────────────────────────────────
def PESSOAS():
    """As pessoas do setor Engenharia, como a tela recebe de `pessoas_da_engenharia` (Task 3)."""
    return [{"hmac": A.codigo(ANA), "nome": "Ana Lima"}, {"hmac": A.codigo(BETO), "nome": "Beto Souza"}]


def test_encaminhar_so_para_a_engenharia_e_troca_quem_acompanha(banco):
    A.encaminhar(ATIVO, A.codigo(BETO), ANA, True, PESSOAS())
    a = _a()
    assert a["responsavel"]["nome"] == "Beto Souza" and a["encaminhado_por"] == "Ana Lima" and a["aberto"]
    assert a["inicio"] == datetime.now(BRT).date() and a["falhas30_entrada"] == 5     # encaminhar também começa
    with pytest.raises(A.Recusada, match="Engenharia"):
        A.encaminhar(ATIVO, "hmac-de-fora", ANA, True, PESSOAS())
    with pytest.raises(A.Recusada, match="já está com Beto Souza"):
        A.encaminhar(ATIVO, A.codigo(BETO), ANA, True, PESSOAS())
    A.encaminhar(ATIVO, A.codigo(ANA), ANA, True, PESSOAS())          # assumir = encaminhar para si mesmo
    a = _a()                                                         # o mesmo acompanhamento, com outra pessoa
    assert a["responsavel"]["nome"] == "Ana Lima" and a["encaminhado_por"] == ""
    with pytest.raises(A.Recusada, match="Engenharia"):
        A.encaminhar(ATIVO, A.codigo(BETO), ANA, False, PESSOAS())


def test_salvar_muda_e_encerra_so_com_fim_e_diagnostico(banco):
    A.pegar(ATIVO, ANA, pode=True)
    aid, hoje = _aid(), date(2026, 10, 18)
    A.salvar(aid, "2026-10-15", "", "1", BETO, True, hoje)            # qualquer um da Engenharia muda
    a = _a()
    assert a["inicio"] == date(2026, 10, 15) and a["diagnostico_id"] == 1 and a["aberto"]
    with pytest.raises(A.Recusada, match="Nada mudou"):
        A.salvar(aid, "2026-10-15", "", "1", ANA, True, hoje)
    for ini, fim, diag, erro in (("2026-10-15", "2026-10-17", "", "diagnóstico"),
                                 ("2026-10-15", "2026-10-14", "1", "antes do início"),
                                 ("2026-10-15", "2026-10-19", "1", "depois de hoje"),
                                 ("2026-10-19", "", "1", "depois de hoje"),
                                 ("2026-10-15", "", "9", "não existe")):
        with pytest.raises(A.Recusada, match=erro):
            A.salvar(aid, ini, fim, diag, ANA, True, hoje)
    A.salvar(aid, "2026-10-15", "2026-10-17", "2", ANA, True, hoje)
    a = _a()
    assert not a["aberto"] and a["fim"] == date(2026, 10, 17) and a["diagnostico_id"] == 2 and a["encerrado_em"]
    with pytest.raises(A.Recusada, match="encerrado"):
        A.comentar(aid, "depois", ANA, True)
    with pytest.raises(A.Recusada, match="encerrado"):
        A.salvar(aid, "2026-10-15", "2026-10-18", "2", ANA, True, hoje)


def test_data_invalida_recusa_e_nao_grava(banco):
    # Review Focus 5: o campo de data manda AAAA-MM-DD; o resto (dia que não existe, outro formato, vazio) não grava
    A.pegar(ATIVO, ANA, pode=True)
    n = len(banco.linhas(A.LIVRO, A.ABA_EVENTO))
    for ini in ("2026-02-31", "18/10/2026", ""):
        with pytest.raises(A.Recusada, match="início"):
            A.salvar(_aid(), ini, "", "1", ANA, True, date(2026, 10, 18))
    with pytest.raises(A.Recusada, match="fim"):
        A.salvar(_aid(), "2026-10-15", "31/10/2026", "1", ANA, True, date(2026, 10, 18))
    assert len(banco.linhas(A.LIVRO, A.ABA_EVENTO)) == n


def test_comentario_cifrado_com_hora_quem_e_limites(banco):
    A.pegar(ATIVO, ANA, pode=True)
    A.comentar(_aid(), "  Datalogger   perde o link\n\nTrocar cabo ", BETO, True)   # não só quem acompanha
    A.comentar(_aid(), "Cabo trocado", ANA, True)
    novo, velho = _a()["comentarios"]                                                 # o mais novo primeiro
    assert velho["texto"] == "Datalogger perde o link\n\nTrocar cabo" and velho["nome"] == "Beto Souza"
    assert novo["texto"] == "Cabo trocado" and " às " in novo["quando_txt"]
    with pytest.raises(A.Recusada, match="Escreva"):
        A.comentar(_aid(), "   ", ANA, True)
    with pytest.raises(A.Recusada, match="2000"):
        A.comentar(_aid(), "x" * 2001, ANA, True)
    with pytest.raises(A.Recusada, match="Engenharia"):
        A.comentar(_aid(), "sem poder", ANA, False)
    assert "datalogger" not in json.dumps(banco.linhas(A.LIVRO, A.ABA_EVENTO), default=str).lower()


# ── Task 3: o cadastro dos diagnósticos e as pessoas da Engenharia ───────────────────────────────────────────────────
def test_cadastro_cria_renomeia_e_exclui_sem_reaproveitar_id(banco):
    A.pegar(ATIVO, ANA, pode=True)
    A.criar_diagnostico("Proteção", "", ANA, True)
    A.mudar_diagnostico(3, "Proteção (relé)", "Relé de proteção atuando", BETO, True)
    A.excluir_diagnostico(3, ANA, True)
    A.criar_diagnostico("Inversor", "", ANA, True)
    ds = A.diagnosticos(A.ler(forcar=True)["diagnosticos"])
    assert [(d["id"], d["nome"], d["excluido"]) for d in ds] == [
        (1, "Comunicação", False), (2, "Disjuntor", False), (3, "Proteção (relé)", True), (4, "Inversor", False)]
    assert ds[2]["descricao"] == "Relé de proteção atuando"
    with pytest.raises(A.Recusada, match="já existe"):
        A.criar_diagnostico("comunicacao", "", ANA, True)               # sem acento nem caixa, o mesmo nome
    with pytest.raises(A.Recusada, match="caracteres"):
        A.criar_diagnostico("A", "", ANA, True)
    with pytest.raises(A.Recusada, match="Engenharia"):
        A.criar_diagnostico("Outro", "", ANA, False)
    with pytest.raises(A.Recusada, match="excluído"):
        A.excluir_diagnostico(3, ANA, True)
    assert len(banco.linhas(A.LIVRO, A.ABA_EVENTO)) == 1                # o cadastro grava sem tocar nos eventos


def test_pessoas_da_engenharia_pelo_setor_e_o_nome_do_fracttal(banco, monkeypatch):
    from nexus.cadastro import fracttal_pessoal as FP
    from nexus.cadastro import setores as S
    setores = [{"setor_id": 1, "nome": "Engenharia", "excluido": False},
               {"setor_id": 2, "nome": "Performance", "excluido": False}]
    decisoes = [_dec(10, 1, "h10", "2026-10-12T10:00:00Z"), _dec(11, 2, "h11", "2026-10-12T10:00:00Z"),
                _dec(12, 1, "h12", "2026-10-12T10:00:00Z"), _dec(12, None, "h12", "2026-10-13T10:00:00Z"),
                _dec(13, 1, "h13", "2026-10-12T10:00:00Z")]
    monkeypatch.setattr(S, "ler", lambda *a, **k: {"setores": setores, "decisoes": decisoes, "lido_em": 1, "erro": ""})
    monkeypatch.setattr(FP, "ler_pessoal", lambda *a, **k: {
        "pessoas": [{"id": 10, "nome": "Ana Lima"}, {"id": 11, "nome": "Beto Souza"}], "erro": ""})
    # 11 é da Performance; 12 saiu do setor no dia seguinte; 13 é da Engenharia sem nome no Fracttal
    assert A.pessoas_da_engenharia() == [{"hmac": "h10", "nome": "Ana Lima"},
                                         {"hmac": "h13", "nome": "(sem nome no Fracttal)"}]     # sem nome no fim


# ── Task 4: a separação das abas (acompanhamentos montados à mão, sem banco) ─────────────────────────────────────────
def _ac(cod, desde, inicio, fim=None, diag=None):
    return {"id": cod, "cod": cod, "desde": desde, "inicio": inicio, "fim": fim, "diagnostico_id": diag,
            "aberto": fim is None, "encerrado_em": desde if fim else None,
            "responsavel": {"hmac": "h-ana", "nome": "Ana Lima"}, "nivel_entrada": "critico"}


def _f(quando):
    return {"quando": quando, "os": "1", "tipo": "Corretiva"}


def D(d, h=8, m=0):
    return datetime(2026, 10, d, h, m, tzinfo=BRT)


def test_separar_tira_o_acompanhado_e_o_encerrado_sem_falha_nova():
    sinais = [{"cod": c, "nivel": "atencao"} for c in ("IBI200-INVR1.3", "IBI200-TRK07", "IBI200-INV02")]
    acomps = {"a1": _ac("IBI200-INVR1.3", D(16), date(2026, 10, 16)),
              "a2": _ac("IBI200-TRK07", D(1), date(2026, 10, 1), fim=date(2026, 10, 10), diag=2)}
    s = A.separar(sinais, acomps, {"IBI200-TRK07": [_f(D(9))]})
    assert [x["cod"] for x in s["sinal"]] == ["IBI200-INV02"] and s["sinal"][0]["ja"] is None
    assert [x["acomp"]["cod"] for x in s["aberto"]] == ["IBI200-INVR1.3"]
    assert [(x["acomp"]["cod"], x["voltou"]) for x in s["encerrado"]] == [("IBI200-TRK07", None)]


def test_encerrado_volta_so_com_falha_do_dia_seguinte_ao_fim():
    sinais = [{"cod": "IBI200-TRK07", "nivel": "atencao"}]
    acomps = {"a2": _ac("IBI200-TRK07", D(1), date(2026, 10, 1), fim=date(2026, 10, 10), diag=2)}
    assert A.separar(sinais, acomps, {"IBI200-TRK07": [_f(D(10, 23))]})["sinal"] == []    # o dia do fim é analisado
    s = A.separar(sinais, acomps, {"IBI200-TRK07": [_f(D(10, 23)), _f(D(11, 0, 30))]})
    assert s["sinal"][0]["ja"] == {"diagnostico_id": 2, "fim": date(2026, 10, 10)}
    assert s["encerrado"][0]["voltou"] == D(11, 0, 30)


def test_falha_nova_conta_da_gravacao_do_inicio_do_acompanhamento():
    acomps = {"a1": _ac("IBI200-INVR1.3", D(16, 14, 20), date(2026, 10, 10))}     # o início é anterior à gravação
    (x,) = A.separar([{"cod": "IBI200-INVR1.3", "nivel": "critico"}], acomps,
                     {"IBI200-INVR1.3": [_f(D(12)), _f(D(17))]})["aberto"]
    assert [f["quando"] for f in x["novas"]] == [D(17)]


def test_aberto_com_falha_nova_vem_primeiro_e_depois_o_nivel():
    sinais = [{"cod": "A1", "nivel": "atencao"}, {"cod": "B2", "nivel": "critico"}, {"cod": "C3", "nivel": "atencao"}]
    acomps = {"a": _ac("A1", D(10), date(2026, 10, 10)), "b": _ac("B2", D(10), date(2026, 10, 10)),
              "c": _ac("C3", D(10), date(2026, 10, 10)), "d": _ac("D4", D(9), date(2026, 10, 9))}    # D4 sem sinal agora
    s = A.separar(sinais, acomps, {"C3": [_f(D(12))]})
    assert [x["acomp"]["cod"] for x in s["aberto"]] == ["C3", "B2", "A1", "D4"]
    assert s["aberto"][3]["ativo"] is None


def test_codigo_casa_sem_caixa_nem_espaco():
    # Review Focus 2: o mesmo ativo escrito de outro jeito no Fracttal e no livro
    s = A.separar([{"cod": " ibi200-invr1.3", "nivel": "critico"}],
                  {"a1": _ac("IBI200-INVR1.3", D(16), date(2026, 10, 16))}, {})
    assert s["sinal"] == [] and s["aberto"][0]["ativo"]["cod"] == " ibi200-invr1.3"
