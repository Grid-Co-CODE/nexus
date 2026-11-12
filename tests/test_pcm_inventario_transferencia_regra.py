"""A regra da transferência entre almoxarifados (`nexus/pcm/inventario/transferencia.py`; 12/11/2026): conferir, os seis passos
do transferir, a resposta que não veio, a releitura que não bate e o histórico. O Fracttal é o `EstoqueFalso`; o livro do
inventário, o arquivo da cópia de prova; a varredura do App, o banco falso dos testes. Dado de mentira ("Cliente Alfa",
"Usina Um", ids e códigos inventados), sem nome de gente."""
import json
from datetime import datetime, timezone

import pytest
from estoque_falso import EstoqueFalso
from test_campo_visao import BRT, banco  # noqa: F401  (banco é fixture)
from test_pcm_almoxarifado import _s, _semear

from nexus.campo import visao
from nexus.dados import fato_inventario as F
from nexus.pcm.inventario import estoque as E
from nexus.pcm.inventario import quem
from nexus.pcm.inventario import requisicoes as RQ
from nexus.pcm.inventario import transferencia as T
from nexus.pcm.inventario.erros import Conflito

PESSOA = {"email": "pessoa.teste@exemplo.com", "nome": "Pessoa Teste"}
RESPONSAVEL = {"id": "501", "descricao": "Pessoa Teste  {P-01}"}
ALFA_UM = "// Cliente Alfa/ Cliente Alfa - Usina Um - SP/"
ALFA_DOIS = "// Cliente Alfa/ Cliente Alfa - Usina Dois - SP/"
BETA = "// Cliente Beta/ Cliente Beta - Usina Cinco - PI/"
SALDOS = {"30": {"1": {"saldo": 5, "codigo": "SP-1", "unidade": "UNIDADE"},
                 "2": {"saldo": 2.5, "codigo": "SP-2", "unidade": "METRO"}},
          "31": {"1": {"saldo": 1, "codigo": "SP-1", "unidade": "UNIDADE"}},
          "40": {"1": {"saldo": 3, "codigo": "SP-1", "unidade": "UNIDADE"}},
          "50": {"1": {"saldo": 1, "codigo": "SP-1", "unidade": "UNIDADE"}}}
# a lista dos almoxarifados do Fracttal (o `location_description` como ele manda): o 60 é o novo, vazio, do mesmo cliente com
# outra caixa e acento; o 50 não tem o local (o desativado do Fracttal: cliente desconhecido)
ALMOXES = {"30": {"nome": "Almoxarifado Usina Um", "local": ALFA_UM + " "},
           "31": {"nome": "Almoxarifado Usina Dois", "local": ALFA_DOIS},
           "40": {"nome": "Almoxarifado Usina Cinco", "local": BETA},
           "50": {"nome": "Almoxarifado Sem Local", "local": ""},
           "60": {"nome": "Almoxarifado Usina Sete", "local": "// CLIENTE ÁLFA/ Cliente Alfa - Usina Sete - BA/ "}}
SALDO_DA_VARREDURA = [_s(1, 30, ALFA_UM, 5, 0), _s(2, 30, ALFA_UM, 2.5, 0), _s(1, 31, ALFA_DOIS, 1, 0), _s(1, 40, BETA, 3, 0)]


@pytest.fixture
def tr(app, banco, tmp_path, monkeypatch):  # noqa: F811
    """O Nexus com a varredura do App (o 60, novo e vazio, não está nela: a lista é a do Fracttal), o livro do inventário
    num arquivo e o servidor (`NEXUS_INVENTARIO_GRAVAR`)."""
    monkeypatch.setattr(visao, "_agora", lambda: datetime(2026, 10, 25, 10, 0, tzinfo=BRT))
    _semear(banco, saldo_extra=SALDO_DA_VARREDURA)
    app.config.update(NEXUS_ALMOX_INVENTARIO_ARQUIVO=str(tmp_path / "inventario.json"), TESTING=True,
                      NEXUS_DADOS=str(tmp_path / "dados"), NEXUS_INVENTARIO_GRAVAR="1")
    visao.limpar()
    F.limpar()
    T.limpar()
    RQ.limpar()
    yield app
    T.limpar()
    RQ.limpar()


def _falso(saldos=None, classe=EstoqueFalso, **kw):
    kw.setdefault("almoxarifados", ALMOXES)
    return classe(json.loads(json.dumps(saldos or SALDOS)),
                  responsaveis=[{"id": 501, "email": PESSOA["email"], "description": RESPONSAVEL["descricao"]}], **kw)


def _ctx(app_, falso):
    return T.contexto(app_.config, falso)


def _tr(app_, falso, origem="30", destino="31", item="1", qtd="2", ref="", **kw):
    args = dict(quem_=quem.colunas(app_.config, PESSOA), responsavel=RESPONSAVEL)
    args.update(kw)
    return T.transferir(app_.config, falso, _ctx(app_, falso), origem, destino, item, qtd, ref, **args)


def _eventos(app_, prefixo="transferencia_"):
    return [e for e in F.ler(app_.config, forcar=True)[F.ABA_EVENTO] if e["tipo"].startswith(prefixo)]


def test_o_codigo_vai_inteiro_no_lote():
    for _ in range(50):
        c = T.novo_codigo()
        assert c.startswith("NX-TR-") and len(c) == 14 and T.codigo_do_lote(T.lote_do_codigo(c)) == c
        assert 0 <= T.lote_do_codigo(c) < 2 ** 31


@pytest.mark.parametrize("local, cliente", [
    ("// Cliente Alfa/ Cliente Alfa - Usina Um - PA/ ", "Cliente Alfa"),        # dois nós: o 1º (181 no Fracttal)
    ("// TESTE - PA/ ", "TESTE - PA"),                                          # um nó só (o de teste): o próprio nó
    ("", ""), ("//  / ", ""), (None, ""),                                       # sem nó (o desativado): desconhecido
])
def test_o_cliente_e_o_primeiro_no_do_caminho(local, cliente):
    assert T.cliente_do_caminho(local) == cliente


def test_os_almoxarifados_saem_do_fracttal_na_hora(tr):
    """O livro Saldo da varredura só tem os almoxarifados com peça: o 60, novo e vazio, só aparece pela lista do Fracttal."""
    falso = _falso(inativos={"40"})
    ctx = _ctx(tr, falso)
    a = ctx["almoxes"]
    assert (a["30"]["cliente"], a["31"]["cliente"], a["40"]["cliente"], a["50"]["cliente"], a["60"]["cliente"]) == (
        "Cliente Alfa", "Cliente Alfa", "Cliente Beta", "", "CLIENTE ÁLFA")
    assert a["30"]["nome"] == "Almoxarifado Usina Um" and falso.chamadas.count("almoxarifados") == 1
    assert [x["id"] for x in T.opcoes(ctx)] == ["31", "60", "30", "50"]         # sem o inativo; o sem cliente por último
    p = T.conferir(tr.config, falso, ctx, "30", "60", "1", "1")                # sem acento e sem caixa: o mesmo cliente
    assert p["vincular"] is True and p["destino"]["antes"] == 0


def test_conferir_mostra_o_antes_e_o_depois_sem_gravar(tr):
    falso = _falso()
    p = T.conferir(tr.config, falso, _ctx(tr, falso), "30", "31", "1", "2", " OS  4521 ")
    assert (p["origem"]["antes"], p["origem"]["depois"], p["destino"]["antes"], p["destino"]["depois"]) == (5, 3, 1, 3)
    assert p["vincular"] is False and p["referencia"] == "OS 4521" and p["qtd"] == 2
    p = T.conferir(tr.config, falso, _ctx(tr, falso), "30", "31", "2", "1,25")
    assert p["vincular"] is True and p["destino"]["antes"] == 0 and p["destino"]["depois"] == 1.25 and p["qtd"] == 1.25
    assert "transferir" not in falso.chamadas and "ligar" not in falso.chamadas


@pytest.mark.parametrize("args, erro, texto", [
    (("30", "30", "1", "1"), ValueError, "mesmo almoxarifado"),
    (("30", "40", "1", "1"), Conflito, "outro cliente"),
    (("50", "31", "1", "1"), Conflito, "Não sei o cliente"),
    (("30", "99", "1", "1"), Conflito, "não está na lista"),
    (("31", "30", "2", "1"), Conflito, "não tem saldo"),
    (("30", "31", "1", "0"), ValueError, "maior que zero"),
    (("30", "31", "1", "6"), ValueError, "tem 5"),
    (("30", "31", "1", "1.5"), ValueError, "inteira"),
    (("30", "31", "2", "1.255"), ValueError, "duas casas"),
    (("30", "31", "1", "x"), ValueError, "em número"),
    (("30", "31", "", "1"), ValueError, "Escolha a peça"),
])
def test_as_recusas_do_conferir(tr, args, erro, texto):
    with pytest.raises(erro, match=texto):
        falso = _falso()
        T.conferir(tr.config, falso, _ctx(tr, falso), *args)


def test_o_almoxarifado_em_ajuste_recusa(tr):
    falso = _falso()
    falso.definir_modo("31", 2)
    with pytest.raises(Conflito, match="modo 2"):
        T.conferir(tr.config, falso, _ctx(tr, falso), "30", "31", "1", "1")


def test_transferir_vincula_transfere_rele_e_anota(tr):
    falso = _falso()
    r = _tr(tr, falso, item="2", qtd="1.5")
    assert r["ok"] and r["confirmada"] and "Transferência NX-TR-" in r["mensagem"] and "mínimo e máximo 0" in r["mensagem"]
    assert falso.ler("30")["2"]["saldo"] == 1.0 and falso.ler("31")["2"]["saldo"] == 1.5
    assert falso.ler("31")["2"]["minimo"] == 0 and falso.ler("31")["2"]["maximo"] == 0
    t = falso.transferencias[0]
    assert t["description"] == "Transferência pelo Nexus " + r["codigo"] and t["document"] == r["codigo"]
    assert t["id_responsible"] == 501
    ev = _eventos(tr)
    assert [e["tipo"] for e in ev] == ["transferencia_vinculo", "transferencia_saida", "transferencia_entrada"]
    assert {T.codigo_do_lote(e["lote"]) for e in ev} == {r["codigo"]}
    v, s, e = ev
    assert (v["id_almoxarifado"], s["id_almoxarifado"], e["id_almoxarifado"]) == ("31", "30", "31")
    assert (s["de_qtd"], s["para_qtd"], s["contado_qtd"], e["de_qtd"], e["para_qtd"]) == (2.5, 1.0, 1.5, 0.0, 1.5)
    # o folio da origem na saída e o do destino na entrada, só os dígitos (a coluna só aceita dígitos); os folios inteiros e o
    # id do movimento no `dados`
    saida, entrada = [m for m in falso.movimentos if m.get("transferencia")]
    assert s["movimento_fracttal"] == saida["folio"].split("-")[1] and e["movimento_fracttal"] == entrada["folio"].split("-")[1]
    assert s["pessoa_hmac"] and s["codigo"] == "SP-2"
    assert F.decifrar(tr.config, F.ABA_EVENTO, s) == {
        "codigo": r["codigo"], "origem": "30", "destino": "31", "origem_nome": "Almoxarifado Usina Um",
        "destino_nome": "Almoxarifado Usina Dois", "id_movimento": t["id"], "folio_origem": saida["folio"],
        "folio_destino": entrada["folio"], "confirmada": True}


def test_a_referencia_do_pcm_vai_no_documento_e_cifrada(tr):
    falso = _falso()
    r = _tr(tr, falso, ref="OS 4521")
    assert falso.transferencias[0]["document"] == "OS 4521"
    # o Fracttal troca o `document` pelo folio do destino: a referência sobrevive na nota, junto do código
    assert falso.transferencias[0]["description"] == "OS 4521 · Transferência pelo Nexus " + r["codigo"]
    s = _eventos(tr, "transferencia_saida")[0]
    assert "4521" not in json.dumps(s) and F.decifrar(tr.config, F.ABA_EVENTO, s)["referencia"] == "OS 4521"


def test_o_destino_que_exige_aprovacao_recusa_antes_de_gravar(tr):
    """Nenhum dos 183 almoxarifados do Fracttal tinha o `transfer_approval` ligado em 12/11/2026: a aprovação no destino não
    tem como ser provada, e o Nexus recusa esse caso (o conferir e o transferir), sem vínculo nem transferência."""
    falso = _falso(aprovacao_transferencia={"31"})
    for fazer in (lambda: T.conferir(tr.config, falso, _ctx(tr, falso), "30", "31", "2", "1"),
                  lambda: _tr(tr, falso, item="2")):
        with pytest.raises(Conflito) as ex:
            fazer()
        assert str(ex.value) == T.EXIGE_APROVACAO
    assert T.EXIGE_APROVACAO == ("O almoxarifado de destino exige aprovação de transferência no Fracttal, e o Transferir do "
                                 "Nexus ainda não cobre esse caso: faça pela tela do Fracttal.")
    assert falso.transferencias == [] and "ligar" not in falso.chamadas and _eventos(tr) == []


@pytest.mark.parametrize("inativo, papel", [("30", "origem"), ("31", "destino")])
def test_o_almoxarifado_inativo_nao_entra(tr, inativo, papel):
    falso = _falso(inativos={inativo})
    with pytest.raises(Conflito, match=f"inativo no Fracttal: não entra como {papel}"):
        _tr(tr, falso)
    assert falso.transferencias == []


def test_sem_o_responsavel_e_fora_do_servidor_nada_vai(tr, monkeypatch):
    falso = _falso()
    with pytest.raises(Conflito, match="responsáveis"):
        _tr(tr, falso, responsavel=None)
    n = len(falso.chamadas)
    monkeypatch.delitem(tr.config, "NEXUS_INVENTARIO_GRAVAR")
    with pytest.raises(Conflito, match="só roda no servidor"):
        _tr(tr, falso)
    # só a lista do contexto do teste: o portão vem antes de qualquer leitura da regra (a ponte o chama antes do contexto)
    assert falso.transferencias == [] and falso.chamadas[n:] == ["almoxarifados"] and "ligar" not in falso.chamadas


class _TransferenciaRecusada(EstoqueFalso):
    def transferir(self, *a, **k):
        raise E.Recusado("ALGUM_MOTIVO", "transferir")


def test_o_nao_do_fracttal_registra_a_falha_e_o_vinculo_fica(tr):
    falso = _falso(classe=_TransferenciaRecusada)
    with pytest.raises(T.Falhou) as ex:
        _tr(tr, falso, item="2", qtd="1")
    assert ex.value.status == 409 and "Nada foi transferido" in ex.value.mensagem and "vinculada" in ex.value.mensagem
    assert [e["tipo"] for e in _eventos(tr)] == ["transferencia_vinculo", "transferencia_falha"]
    assert falso.ler("30")["2"]["saldo"] == 2.5


def test_a_resposta_perdida_que_o_historico_acha_segue(tr):
    falso = _falso(perder_resposta={"transferir"})
    r = _tr(tr, falso)
    assert r["confirmada"] and len(falso.transferencias) == 1 and "achar_transferencia" in falso.chamadas
    assert [e["tipo"] for e in _eventos(tr)] == ["transferencia_saida", "transferencia_entrada"]


class _CaiUmaVez(EstoqueFalso):
    """A rede cai ANTES de o Fracttal gravar, uma vez."""
    caiu = False

    def transferir(self, *a, **k):
        if not self.caiu:
            self.caiu = True
            raise ConnectionError("a rede caiu (de mentira)")
        return super().transferir(*a, **k)


def test_a_resposta_que_nao_veio_trava_e_a_proxima_procura_antes(tr):
    """A rede caiu ANTES de o Fracttal gravar e o histórico não acha o código: a trava. A próxima tentativa procura o código de
    novo, não acha, libera e transfere uma vez só."""
    falso = _falso(classe=_CaiUmaVez)
    with pytest.raises(T.Falhou) as ex:
        _tr(tr, falso)
    assert ex.value.status == 502 and "pode ter sido feita" in ex.value.mensagem
    assert [e["tipo"] for e in _eventos(tr)] == ["transferencia_travada"]
    T.limpar()                                                  # a memória do processo se foi (o restart): o livro segura
    buscas = falso.chamadas.count("achar_transferencia")
    r = _tr(tr, falso)
    assert falso.chamadas.count("achar_transferencia") == buscas + 1          # procurou antes de mandar
    assert r["confirmada"] and len(falso.transferencias) == 1
    assert [e["tipo"] for e in _eventos(tr)][-2:] == ["transferencia_saida", "transferencia_entrada"]
    assert T._travas(_eventos(tr)) == {}


class _BuscaCaiUmaVez(EstoqueFalso):
    buscou = False

    def achar_transferencia(self, *a, **k):
        if not self.buscou:
            self.buscou = True
            raise ConnectionError("a busca caiu (de mentira)")
        return super().achar_transferencia(*a, **k)


def test_a_transferencia_sem_resposta_achada_depois_nao_se_repete(tr):
    """O Fracttal gravou, a resposta se perdeu E a busca falhou: a trava. A próxima tentativa acha o código no histórico,
    registra como feita e não manda outra."""
    falso = _falso(classe=_BuscaCaiUmaVez, perder_resposta={"transferir"})
    with pytest.raises(T.Falhou):
        _tr(tr, falso)
    r = _tr(tr, falso)
    assert r["ok"] and not r["confirmada"] and "não mandou outra" in r["mensagem"] and len(falso.transferencias) == 1
    assert falso.ler("30")["1"]["saldo"] == 3                    # saiu uma vez só
    assert [e["tipo"] for e in _eventos(tr)] == ["transferencia_travada", "transferencia_saida"]
    assert T._travas(_eventos(tr)) == {}
    h = T.historico(tr.config)["linhas"]
    assert len(h) == 1 and "achada depois" in h[0]["situacao"]


class _SemRespostaNunca(EstoqueFalso):
    def transferir(self, *a, **k):
        raise ConnectionError("a rede caiu (de mentira)")

    def achar_transferencia(self, *a, **k):
        return None


def test_a_trava_vale_sem_decifrar(tr, monkeypatch):
    with pytest.raises(T.Falhou):
        _tr(tr, _falso(classe=_SemRespostaNunca))
    eventos = _eventos(tr)

    def sem_chave(*a, **k):
        raise ValueError("sem a chave do cadastro")
    monkeypatch.setattr(F, "decifrar", sem_chave)
    assert set(T._travas(eventos)) == {("30", "1")}
    assert T.historico(tr.config)["linhas"][0]["situacao"] == "Pode ter feito: confira no Fracttal"


class _DestinoNaoMostra(EstoqueFalso):
    def ler(self, id_almox):
        lido = super().ler(id_almox)
        if self.transferencias and id_almox == "31":
            lido["1"]["saldo"] = 1.0                            # o destino relido não mostra a peça
        return lido


def test_a_releitura_que_nao_bate_e_erro_e_diz_o_que_leu(tr):
    r = _tr(tr, _falso(classe=_DestinoNaoMostra))
    assert not r["confirmada"] and "o destino tem 1 (esperado 3)" in r["mensagem"]
    assert [e["tipo"] for e in _eventos(tr)] == ["transferencia_saida", "transferencia_falha"]


def test_duas_transferencias_da_mesma_peca_ao_mesmo_tempo(tr):
    with T._tomar("30", "31", "1"):
        with pytest.raises(Conflito, match="Outra pessoa"):
            _tr(tr, _falso())
        assert _tr(tr, _falso(), item="2", qtd="1")["confirmada"]          # outra peça não espera


def test_a_mesma_peca_num_almoxarifado_em_comum_tambem_espera(tr):
    """A releitura confere o saldo dos dois lados contra o de antes: outra transferência da MESMA peça que toque um dos dois
    almoxarifados (a mesma origem para outro destino, ou a volta) mudaria esse saldo no meio, e a primeira diria "a releitura
    não bate" de uma transferência que deu certo. Por isso a vez é da peça em CADA almoxarifado, e não só do par."""
    with T._tomar("30", "31", "1"):
        with pytest.raises(Conflito, match="Outra pessoa"):
            _tr(tr, _falso(), destino="60")                                # a mesma origem, outro destino
        with pytest.raises(Conflito, match="Outra pessoa"):
            _tr(tr, _falso(), origem="31", destino="30")                   # a volta
    assert _tr(tr, _falso(), destino="60", qtd="1")["confirmada"]          # acabada a primeira, passa


def test_o_historico_do_mais_novo_ao_mais_velho(tr):
    falso = _falso()
    _tr(tr, falso, qtd="1")
    _tr(tr, falso, item="2", qtd="0.5", ref="OS 4522")
    h = T.historico(tr.config, pessoas={})
    assert h["erro"] == "" and [x["peca"] for x in h["linhas"]] == ["SP-2", "SP-1"]
    novo, velho = h["linhas"]
    assert (novo["origem_nome"], novo["destino_nome"], novo["qtd"], novo["vinculo"], novo["situacao"]) == (
        "Almoxarifado Usina Um", "Almoxarifado Usina Dois", 0.5, True, "Feita")
    assert (velho["o_antes"], velho["o_depois"], velho["d_antes"], velho["d_depois"], velho["vinculo"]) == (5, 4, 1, 2, False)


def test_o_historico_nao_mostra_a_transferencia_com_almoxarifado_de_teste(tr):
    """A prova no Fracttal de verdade é nos almoxarifados de teste, e o livro só cresce: a transferência de teste fica no
    livro, mas não nas Últimas transferências do PCM (12/11/2026: as duas da prova no ar apareciam na aba). Vale o teste na
    origem ou no destino."""
    falso = _falso()
    _tr(tr, falso, qtd="1")                                                # 30 → 31: de verdade
    tr.config["NEXUS_ALMOX_TESTE_IDS"] = "60"
    _tr(tr, falso, destino="60", qtd="1")                                  # 30 → 60: o destino é de teste
    _tr(tr, falso, origem="60", destino="31", qtd="1")                     # 60 → 31: a origem é de teste
    h = T.historico(tr.config, pessoas={})
    assert h["erro"] == "" and [(x["origem"], x["destino"]) for x in h["linhas"]] == [("30", "31")]
    assert len({e["lote"] for e in _eventos(tr)}) == 3                     # o livro guarda as três


def test_a_auditoria_mostra_a_transferencia(tr, monkeypatch):
    from nexus.pcm.inventario import revisao as R
    _tr(tr, _falso(), item="2", qtd="1")
    ctx = R.montar_auditoria(tr.config, pode=False)
    rotulos = [x["rotulo"] for x in ctx["eventos"]]
    assert "Transferência: saída" in rotulos and "Peça vinculada para a transferência" in rotulos
    saida = next(x for x in ctx["eventos"] if x["tipo"] == "transferencia_saida")
    assert saida["numeros"] == "saldo 2,5 para 1" or saida["numeros"].startswith("saldo ")
    assert saida["motivo"] is False and saida["lote"].startswith("NX-TR-")


def test_a_peca_com_serie_ou_lote_recusa_antes_de_gravar(tr):
    falso = _falso(com_serie_ou_lote={"2"})
    for fazer in (lambda: T.conferir(tr.config, falso, _ctx(tr, falso), "30", "31", "2", "1"),
                  lambda: _tr(tr, falso, item="2", qtd="1")):
        with pytest.raises(Conflito) as ex:
            fazer()
        assert str(ex.value) == "Esta peça tem controle de série ou de lote no Fracttal: transfira pela tela do Fracttal."
    assert falso.transferencias == [] and "ligar" not in falso.chamadas and _eventos(tr) == []


@pytest.mark.parametrize("folio, digitos", [("MOV-21", "21"), ("MOV-007", "7"), ("", None), ("MOV-", None), ("0", "0")])
def test_o_folio_vai_pelos_digitos(folio, digitos):
    assert T._digitos(folio) == digitos
