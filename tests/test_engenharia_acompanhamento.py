"""Engenharia > Confiabilidade: o acompanhamento dos ativos com sinal (Levi, 18/10/2026: "os membros de engenharia ou
administradores pegar aqueles ativos com sinal para acompanhar ou alguém da engenharia poder encaminhar para a pessoa
ver!"). Desenho em docs/superpowers/specs/2026-10-18-engenharia-acompanhamento-design.md. Banco falso
(tests/pg_falso.py); os nomes são fictícios."""
import json
import re
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


# ── Task 5: a tela (abas, filtros, listas e a gaveta) ────────────────────────────────────────────────────────────────
TRK07 = {"cod": "IBI200-TRK07", "usina_id": 1, "usina_ligada_por": "de-para do Fracttal", "nivel": "monitorar",
         "nFalha": 2, "n7": 1}


@pytest.fixture
def tela(banco, app, monkeypatch):
    """A Confiabilidade com o relógio em 06/10/2026 (as OS de test_engenharia_confiabilidade): sinal em IBI200-INVR1.3
    (crítico), IBI200-TRK07 e IBI200-INV02; no livro, INVR1.3 aberto com Ana Lima e TRK07 encerrado hoje, sem falha
    depois do fim; INV02 livre. Quem entra é do setor Engenharia."""
    from test_engenharia_confiabilidade import AGORA, _onde, _os

    from nexus.auth import setor_telas as ST
    from nexus.engenharia import confiabilidade as C
    from nexus.engenharia import os_falhas
    from nexus.torres import engenharia as torre

    class Relogio(datetime):
        @classmethod
        def now(cls, tz=None):
            return AGORA.astimezone(tz)
    monkeypatch.setattr(C, "datetime", Relogio)
    linhas = ([_os("IBI200-INVR1.3", d) for d in (1, 2, 3, 10)] + [_os("IBI200-TRK07", d) for d in (5, 20)]
              + [_os("IBI200-INV02", d) for d in (1, 4)])
    monkeypatch.setattr(os_falhas, "pedir_releitura", lambda app=None: None)
    monkeypatch.setattr(os_falhas, "linhas", lambda: linhas)
    monkeypatch.setattr(os_falhas, "estado", lambda: {"lendo": False, "erro": "", "completa": True, "n": len(linhas),
                                                       "vivas_em": 1})
    monkeypatch.setattr(torre, "_onde_do_cadastro", lambda: _onde)
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(), "setor": {"id": 1, "nome": "Engenharia"},
                                               "erro": ""})
    monkeypatch.setattr(A, "pessoas_da_engenharia", PESSOAS)
    A.pegar(dict(ATIVO, nFalha=4), ANA, pode=True)
    A.pegar(TRK07, ANA, pode=True)
    hoje = datetime.now(BRT).date().isoformat()
    A.salvar(_aid_de("IBI200-TRK07"), hoje, hoje, "2", ANA, True)
    torre._CACHE.clear()
    yield banco
    torre._CACHE.clear()


def test_tela_tem_as_abas_e_os_numeros(tela, cliente):
    html = _como(cliente, ANA).get("/t/engenharia/confiabilidade").get_data(as_text=True)
    assert "Em acompanhamento <i>1</i>" in html and "Encerrados <i>1</i>" in html and ">Diagnósticos<" in html
    assert "Ativos com sinal <i>1</i>" in html and "Pegar para acompanhar" in html
    assert "IBI200-INV02" in _lista(html) and "IBI200-TRK07" not in _lista(html) and "IBI200-INVR1.3" not in _lista(html)
    assert 'name="quem"' not in html
    ac = cliente.get("/t/engenharia/confiabilidade?aba=acompanhamento").get_data(as_text=True)
    assert "IBI200-INVR1.3" in _lista(ac) and "Com Ana Lima (você) desde" in ac and 'name="quem"' in ac
    assert "Quem acompanha" in ac and "4" in _lista(ac)                         # as falhas quando entrou
    enc = cliente.get("/t/engenharia/confiabilidade?aba=encerrados").get_data(as_text=True)
    assert "IBI200-TRK07" in _lista(enc) and "Quem acompanhava" in enc and "Disjuntor" in _lista(enc)
    assert "sem falha nova desde o fim" in _lista(enc)
    dg = cliente.get("/t/engenharia/confiabilidade?aba=diagnosticos").get_data(as_text=True)
    assert "Comunicação" in dg and "Disjuntor" in dg


def test_filtro_quem_acompanha(tela, cliente):
    _como(cliente, ANA)
    url = "/t/engenharia/confiabilidade?aba=acompanhamento&quem="
    assert "IBI200-INVR1.3" in _lista(cliente.get(url + A.codigo(ANA)).get_data(as_text=True))
    assert "IBI200-INVR1.3" not in _lista(cliente.get(url + A.codigo(BETO)).get_data(as_text=True))
    # os filtros de hoje valem também nesta aba; o nível é o de agora
    assert "IBI200-INVR1.3" not in _lista(cliente.get(
        "/t/engenharia/confiabilidade?aba=acompanhamento&nivel=atencao").get_data(as_text=True))


def test_quem_nao_e_da_engenharia_le_sem_botoes(tela, cliente, monkeypatch):
    from nexus.auth import setor_telas as ST
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(), "setor": {"id": 2, "nome": "Performance"},
                                               "erro": ""})
    html = _como(cliente, BETO).get("/t/engenharia/confiabilidade?aba=acompanhamento").get_data(as_text=True)
    assert "IBI200-INVR1.3" in _lista(html) and "Com Ana Lima desde" in html
    assert "Pegar para acompanhar" not in html and "Salvar comentário" not in html and ">Diagnósticos<" not in html
    assert ">Diagnósticos<" not in cliente.get("/t/engenharia/confiabilidade?aba=diagnosticos").get_data(as_text=True)


def test_gaveta_mostra_o_acompanhamento_e_os_anteriores(tela, cliente):
    A.comentar(_aid_de("IBI200-INVR1.3"), "Datalogger perde o link", BETO, True)
    html = _como(cliente, ANA).get("/t/engenharia/confiabilidade?aba=acompanhamento").get_data(as_text=True)
    assert "Acompanhamento" in html and "Datalogger perde o link" in html and "Salvar comentário" in html
    assert "Início da análise" in html and "Fim da análise" in html and "Beto Souza" in html
    enc = cliente.get("/t/engenharia/confiabilidade?aba=encerrados").get_data(as_text=True)
    assert "Encerrado" in enc and "Salvar comentário" not in enc                     # encerrado fica só para ler


def test_comentario_com_html_sai_escapado(tela, cliente):
    # Review Focus 3
    A.comentar(_aid_de("IBI200-INVR1.3"), "<script>alert(1)</script>", ANA, True)
    html = _como(cliente, ANA).get("/t/engenharia/confiabilidade?aba=acompanhamento").get_data(as_text=True)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "<script>alert(1)" not in html


def test_banco_fora_a_tela_abre_e_avisa(tela, cliente, monkeypatch):
    # Review Focus 4: sem ler o livro, a aba diz que não leu (nunca "nenhum") e a tela abre
    monkeypatch.setattr(tela, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("fora")))
    A.limpar()
    r = _como(cliente, ANA).get("/t/engenharia/confiabilidade?aba=acompanhamento")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Não consegui ler os acompanhamentos" in html
    assert "Nenhum ativo em acompanhamento" not in html


# ── Task 6: as ações na tela (a gaveta grava e responde a gaveta de novo) ────────────────────────────────────────────
SAME = {"Sec-Fetch-Site": "same-origin"}
URL = "/t/engenharia/confiabilidade"


def test_pegar_pela_gaveta_e_comentar(tela, cliente):
    _como(cliente, BETO)
    r = cliente.post(URL + "/acompanhamento/pegar", data={"cod": "IBI200-INV02"}, headers=SAME)
    g = r.get_data(as_text=True)
    assert r.status_code == 200 and "Com <b>Beto Souza</b> (você)" in g and "Salvar comentário" in g
    assert "Em acompanhamento" in g                                          # o aviso diz para onde o ativo foi
    aid = _aid_de("IBI200-INV02")
    r = cliente.post(f"{URL}/acompanhamento/{aid}/comentar", data={"texto": "Trocar cabo"}, headers=SAME)
    g = r.get_data(as_text=True)
    assert "Comentário salvo" in g and "Trocar cabo" in g
    # e a página já mostra o ativo na outra aba
    assert "IBI200-INV02" not in _lista(cliente.get(URL).get_data(as_text=True))
    assert "IBI200-INV02" in _lista(cliente.get(URL + "?aba=acompanhamento").get_data(as_text=True))


def test_encaminhar_lista_so_a_engenharia(tela, cliente):
    g = _como(cliente, ANA).post(URL + "/acompanhamento/encaminhar", data={"cod": "IBI200-INV02", "para": A.codigo(BETO)},
                                 headers=SAME).get_data(as_text=True)
    sel = re.search(r'<select name="para".*?</select>', g, re.S).group(0)
    assert "Com <b>Beto Souza</b>" in g and "Encaminhado para Beto Souza" in g
    assert sel.count("<option") == len(PESSOAS())          # o "Escolha" e quem não está com o ativo agora (Ana)
    g = cliente.post(URL + "/acompanhamento/encaminhar", data={"cod": "IBI200-INV02", "para": "hmac-de-fora"},
                     headers=SAME).get_data(as_text=True)
    assert "Escolha uma pessoa da Engenharia" in g and "Com <b>Beto Souza</b>" in g


def test_salvar_encerra_e_avisa_quando_volta(tela, cliente):
    # INVR1.3 teve falha em 05/10 (1 dia antes de AGORA): encerrar com fim 04/10 faz o ativo voltar
    html = _como(cliente, ANA).get(URL + "?aba=acompanhamento").get_data(as_text=True)
    assert re.search(r'data-falhas="[^"]*2026-10-05', html)
    g = cliente.post(f"{URL}/acompanhamento/{_aid_de('IBI200-INVR1.3')}/salvar",
                     data={"inicio": "2026-10-01", "fim": "2026-10-04", "diagnostico": "1"}, headers=SAME).get_data(as_text=True)
    assert "Encerrado." in g and "volta para Ativos com sinal" in g and "Salvar comentário" not in g
    lista = _lista(cliente.get(URL).get_data(as_text=True))
    assert "IBI200-INVR1.3" in lista and "já acompanhado · Comunicação em 04/10" in lista


def test_salvar_recusado_responde_a_gaveta_com_o_erro(tela, cliente):
    g = _como(cliente, ANA).post(f"{URL}/acompanhamento/{_aid_de('IBI200-INVR1.3')}/salvar",
                                 data={"inicio": "2026-10-01", "fim": "2026-10-04", "diagnostico": ""},
                                 headers=SAME).get_data(as_text=True)
    assert "Para encerrar, escolha o diagnóstico" in g and "Salvar comentário" in g      # nada mudou: segue aberto


def test_acao_de_outro_site_ou_sem_poder_nao_grava(tela, cliente, monkeypatch):
    from nexus.auth import setor_telas as ST
    _como(cliente, ANA)
    assert cliente.post(URL + "/acompanhamento/pegar", data={"cod": "IBI200-INV02"},
                        headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(), "setor": {"id": 2, "nome": "Performance"},
                                               "erro": ""})
    g = cliente.post(URL + "/acompanhamento/pegar", data={"cod": "IBI200-INV02"}, headers=SAME).get_data(as_text=True)
    assert "Só quem é da Engenharia" in g and _aid_de("IBI200-INV02") is None
    r = cliente.post(URL + "/diagnosticos/criar", data={"nome": "Proteção"}, headers=SAME)
    assert r.status_code == 303 and "Proteção" not in [d["nome"] for d in A.diagnosticos(A.ler(forcar=True)["diagnosticos"])]


def test_pegar_ativo_que_nao_esta_na_lista_recusa(tela, cliente):
    # TRK07 foi encerrado e não falhou depois do fim: não está em Ativos com sinal, não se pega de uma página velha
    g = _como(cliente, ANA).post(URL + "/acompanhamento/pegar", data={"cod": "IBI200-TRK07"}, headers=SAME).get_data(as_text=True)
    assert "não está em Ativos com sinal" in g and _aid_de("IBI200-TRK07") is None


def test_cadastro_pela_aba_diagnosticos(tela, cliente):
    r = _como(cliente, ANA).post(URL + "/diagnosticos/criar", data={"nome": "Proteção", "descricao": "Relé atuando"},
                                 headers=SAME)
    assert r.status_code == 303 and r.headers["Location"].endswith("/t/engenharia/confiabilidade?aba=diagnosticos")
    dg = cliente.get(URL + "?aba=diagnosticos").get_data(as_text=True)
    assert 'value="Proteção"' in dg and "Diagnóstico Proteção criado" in dg
    r = cliente.post(URL + "/diagnosticos/3/salvar", data={"nome": "Proteção (relé)", "descricao": ""}, headers=SAME)
    assert r.status_code == 303 and 'value="Proteção (relé)"' in cliente.get(URL + "?aba=diagnosticos").get_data(as_text=True)
    cliente.post(URL + "/diagnosticos/3/excluir", headers=SAME)
    ac = cliente.get(URL + "?aba=acompanhamento").get_data(as_text=True)
    assert "Proteção (relé)</option>" not in ac                              # o excluído sai da escolha
    r = cliente.post(URL + "/diagnosticos/criar", data={"nome": "comunicacao"}, headers=SAME)
    assert "já existe" in cliente.get(URL + "?aba=diagnosticos").get_data(as_text=True)


# ── a revisão final (18/10/2026): cada achado com o teste que o reproduz ─────────────────────────────────────────────
def test_data_antes_do_inicio_do_metodo_recusa(banco):
    # "0202-10-15" (o ano com um dígito a menos) gravava um data_id de 7 dígitos, para sempre no livro, e voltava
    # lido como outra data
    A.pegar(ATIVO, ANA, pode=True)
    n = len(banco.linhas(A.LIVRO, A.ABA_EVENTO))
    for ini, fim in (("0202-10-15", ""), ("1900-01-01", ""), ("2025-10-19", ""), ("2026-10-15", "0202-10-16")):
        with pytest.raises(A.Recusada, match="Data inválida"):
            A.salvar(_aid(), ini, fim, "1", ANA, True, date(2026, 10, 18))
    assert len(banco.linhas(A.LIVRO, A.ABA_EVENTO)) == n
    A.salvar(_aid(), "2025-10-20", "", "1", ANA, True, date(2026, 10, 18))       # o piso vale
    assert _a()["inicio"] == date(2025, 10, 20)


def test_banco_fora_nao_diz_zero_nem_ninguem(tela, cliente, monkeypatch):
    # com o livro ilegível, os números das abas diziam 0, a gaveta "Ninguém acompanha" com o Pegar, e a aba Diagnósticos
    # mostrava o cadastro inicial como se fosse o do banco
    monkeypatch.setattr(tela, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("fora")))
    A.limpar()
    _como(cliente, ANA)
    html = cliente.get(URL).get_data(as_text=True)
    assert "Em acompanhamento <i>—</i>" in html and "Encerrados <i>—</i>" in html
    assert "Ninguém acompanha este ativo" not in html and "Pegar para acompanhar" not in html
    assert "Não consegui ler os acompanhamentos" in html
    dg = cliente.get(URL + "?aba=diagnosticos").get_data(as_text=True)
    assert "Não consegui ler os acompanhamentos" in dg and 'value="Comunicação"' not in dg


def test_copia_velha_avisa_a_hora(tela, cliente, monkeypatch):
    # a leitura que falha depois de uma boa devolve a cópia velha, e a tela não dizia
    _como(cliente, ANA)
    assert "IBI200-INVR1.3" in _lista(cliente.get(URL + "?aba=acompanhamento").get_data(as_text=True))
    A._CACHE["livro"]["lido_em"] -= 3600                                          # a cópia venceu
    monkeypatch.setattr(tela, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("fora")))
    html = cliente.get(URL + "?aba=acompanhamento").get_data(as_text=True)
    assert "IBI200-INVR1.3" in _lista(html) and "última leitura boa" in html


def test_texto_digitado_nao_se_perde(tela, cliente, monkeypatch):
    # a recusa e o banco fora respondiam a gaveta sem o que a pessoa tinha digitado (o comentário de até 2.000 letras)
    from nexus.dados import livros
    _como(cliente, ANA)
    aid = _aid_de("IBI200-INVR1.3")
    g = cliente.post(f"{URL}/acompanhamento/{aid}/salvar", data={"inicio": "2026-10-01", "fim": "2026-10-04",
                                                                  "diagnostico": ""}, headers=SAME).get_data(as_text=True)
    assert "Para encerrar, escolha o diagnóstico" in g and 'value="2026-10-04"' in g and 'value="2026-10-01"' in g
    monkeypatch.setattr(livros, "publicar", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("fora")))
    g = cliente.post(f"{URL}/acompanhamento/{aid}/comentar", data={"texto": "Trocar o cabo de rede"},
                     headers=SAME).get_data(as_text=True)
    assert "Não consegui gravar no banco" in g and ">Trocar o cabo de rede</textarea>" in g


def test_pegar_de_pagina_velha_diz_com_quem_esta(tela, cliente):
    # a regra 1 do desenho ("o segundo recebe 'já está com <pessoa>'") valia no módulo, mas a rota respondia antes que o
    # ativo não estava na lista
    g = _como(cliente, BETO).post(URL + "/acompanhamento/pegar", data={"cod": "IBI200-INVR1.3"},
                                  headers=SAME).get_data(as_text=True)
    assert "já está com Ana Lima" in g


def test_encaminhar_de_pagina_velha_nao_toma_o_acompanhamento_de_outro(tela, cliente):
    # o ativo estava livre quando a página abriu e outra pessoa o pegou depois: o Encaminhar da gaveta velha passava o
    # acompanhamento dela adiante sem ninguém pedir
    html = _como(cliente, BETO).get(URL).get_data(as_text=True)
    assert 'name="livre" value="1"' in html                       # a gaveta do ativo livre diz que o viu livre
    g = cliente.post(URL + "/acompanhamento/encaminhar", data={"cod": "IBI200-INVR1.3", "para": A.codigo(BETO),
                                                               "livre": "1"}, headers=SAME).get_data(as_text=True)
    assert "já está com Ana Lima" in g
    a = next(x for x in A.estado(A.ler(forcar=True)["eventos"]).values() if x["cod"] == "IBI200-INVR1.3")
    assert a["responsavel"]["nome"] == "Ana Lima"


def test_com_quem_desde_conta_do_encaminhamento(tela, cliente):
    # "Com <pessoa> desde" mostrava o começo do acompanhamento, não quando a pessoa o recebeu
    linhas = tela.abas[(A.LIVRO, A.ABA_EVENTO)]["linhas"]
    linhas[0]["values"][linhas[0]["headers"].index("registrado_em")] = "2026-10-10T12:00:00Z"   # o Pegar de INVR1.3
    A.limpar()
    A.encaminhar({"cod": "IBI200-INVR1.3"}, A.codigo(BETO), ANA, True, PESSOAS())
    a = next(x for x in A.estado(A.ler(forcar=True)["eventos"]).values() if x["cod"] == "IBI200-INVR1.3")
    assert a["desde"].strftime("%d/%m") == "10/10" and a["com_desde"].date() == datetime.now(BRT).date()
    ac = _como(cliente, ANA).get(URL + "?aba=acompanhamento").get_data(as_text=True)
    assert "Com Beto Souza desde " + datetime.now(BRT).strftime("%d/%m") in _lista(ac)
