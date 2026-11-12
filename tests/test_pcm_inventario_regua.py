"""A régua de mínimo e máximo do inventário do almoxarifado (26/10/2026, Levi: "Sugestão ajustável": o Nexus propõe pela
régua de 14/10 e o PCM muda peça a peça). Desenho: docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md
(seção 4.4). O recomendado (a Grid) e o acordado (o cliente) são registros separados, no livro do Nexus; SÓ o acordado vai
ao Fracttal (`min_stock_level`, que dispara o alarme), e só quando a releitura confirma. O Fracttal aqui é o
`EstoqueFalso`; o livro é o arquivo da cópia de prova; a varredura do App, o banco falso do Campo. Dado de mentira: usina,
códigos e IDs inventados, sem nome de gente."""
import json
import re
from datetime import datetime
from pathlib import Path

import pytest
from estoque_falso import EstoqueFalso
from test_campo_visao import BRT, banco  # noqa: F401  (banco é fixture)
from test_pcm_almoxarifado import _semear
from test_pcm_publicar import _no_setor, _pessoa

from nexus.cadastro.cifra import gerar_chave
from nexus.campo import visao
from nexus.dados import fato_inventario as F
from nexus.pcm.inventario import estoque as E
from nexus.pcm.inventario import regua as R
from test_pcm_inventario_estoque import _jwt, _result, api_do_clone, com_o_fracttal  # noqa: F401  (api_do_clone é fixture)
from nexus.cadastro import setor_ids as SID

ALMOX, LIGADA = "900", "de-para do Fracttal"
HMAC_CHAVE = "chave-de-teste"
PESSOA = {"email": "pessoa.teste@exemplo.com", "nome": "Pessoa Teste"}
RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture
def cfg(tmp_path):
    """A cópia de prova: o livro do inventário é um arquivo, nada vai ao banco."""
    F.limpar()
    return {"TESTING": True, "NEXUS_ALMOX_INVENTARIO_ARQUIVO": str(tmp_path / "inventario.json"),
            "NEXUS_CHAVE_CADASTRO": gerar_chave(), "NEXUS_PESSOA_HMAC": HMAC_CHAVE}


def _v(id_item, codigo, saldo, unidade="unidade", avariado=False, minimo=None, usina_id=7, almox=ALMOX):
    """Uma linha da varredura do App no formato que a tela do Almoxarifado monta (`almoxarifado._partes`)."""
    return {"id_item": str(id_item), "id_almox": almox, "almox": f"Almoxarifado {almox}", "usina_id": usina_id,
            "codigo": codigo, "nome": f"Peça {id_item}", "familia": "Cabos", "unidade": unidade, "avariado": avariado,
            "saldo": saldo, "minimo": minimo}


def _falso(**itens):
    """O Fracttal de mentira com as peças do almoxarifado (o saldo, a régua que ele tem hoje e o código)."""
    return EstoqueFalso({ALMOX: {"5001": {"saldo": 10, "minimo": 1, "maximo": 4, "codigo": "SP-CAB-001"},
                                 "5002": {"saldo": 4, "minimo": 0, "maximo": 0, "codigo": "SP-CAB-002-AV"}, **itens}})


def _livro(cfg, aba):
    return F.ler(cfg, forcar=True)[aba]


# ── a conta: a régua de 14/10 ────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("saldo, avariada, decimal, esperado", [
    (10, False, False, (2, 20)),            # 20% do saldo, e o dobro
    (3, False, False, (1, 6)),              # inteiro: o mínimo arredonda PARA CIMA (3 x 20% = 0,6: mínimo 1, e não 0)
    (7, False, False, (2, 14)),             # 1,4 sobe para 2
    (15, False, False, (3, 30)),            # sem a sobra de ponto flutuante (15 x 0,2 daria 3,0000000000000004)
    (0, False, False, (0, 0)),
    (0, True, True, (0, 0)),                # o saldo 0 vale (0, 0) mesmo avariada: não há de onde tirar a régua
    (4, True, False, (None, 12)),           # avariada: sem mínimo e máximo 3x
    (12.5, False, True, (2.5, 25.0)),       # decimal (METRO, MASSA): duas casas
    (7, False, True, (1.4, 14.0)),
    (4.5, True, True, (None, 13.5)),
    (-3, False, False, (0, 0)),             # saldo negativo (Fracttal com estoque negativo) não gera régua
])
def test_sugestao(saldo, avariada, decimal, esperado):
    assert R.sugestao(saldo, avariada, decimal) == esperado


def test_sugestao_sem_saldo_nao_sugere():
    """Em branco nunca é zero: o saldo que o Fracttal não disse não tem sugestão (e "nan" e "inf" também não)."""
    assert R.sugestao(None, False, False) == (None, None)
    assert R.sugestao(None, True, True) == (None, None)
    assert R.sugestao(float("nan"), False, False) == (None, None)
    assert R.sugestao(float("inf"), False, False) == (None, None)


def test_inteiro_sai_inteiro_e_decimal_sai_com_duas_casas():
    mn, mx = R.sugestao(10, False, False)
    assert isinstance(mn, int) and isinstance(mx, int)
    mn, mx = R.sugestao(0.1 + 0.2, False, True)
    assert (mn, mx) == (0.06, 0.6)                    # a soma de decimais não vira 0.6000000000000001


def test_avariada_pelo_codigo():
    """A peça avariada é a do código com `-AV` no fim (a régua de 14/10; "SP-3-AV" e "[AVARIADO]" no catálogo do App);
    o pedaço "AV" no meio de outra palavra não conta. A marca "Avariado" do catálogo também vale."""
    for codigo in ("SP-PEL-007-AV", "sp-pel-007-av", " SP-PEL-007-AV ", "SP-PEL-007-AV-2"):
        assert R.avariada(codigo), codigo
    for codigo in ("SP-PEL-007", "SP-AVR-001", "SP-PEL-AVARIA", "", None):
        assert not R.avariada(codigo), codigo
    assert R.avariada("SP-PEL-007", marca=True) and not R.avariada("SP-PEL-007", marca=False)


def test_decimal_pela_unidade():
    """A unidade decimal é a METRO e a MASSA (o `units_description` do Fracttal, sem acento nem caixa); a UNIDADE e o que
    não se sabe é inteira: arredondar o que não se conhece para duas casas daria 0,2 de um parafuso."""
    for u in ("METRO", "metro", " Massa ", "MASSA"):
        assert R.decimal(u), u
    for u in ("UNIDADE", "unidade", "", None, "PAR"):
        assert not R.decimal(u), u


# ── o quadro: o que a tela mostra de cada peça ──────────────────────────────────────────────────────────────────────

def test_quadro_traz_a_sugestao_e_o_vigente_de_cada_peca(cfg):
    var = [_v(5001, "SP-CAB-001", 10, minimo=1), _v(5002, "SP-CAB-002-AV", 4, avariado=True),
           _v(5003, "SP-CAB-003", 12.5, unidade="metro"), _v(5004, "SP-CAB-004", None),
           _v(5009, "SP-OUT-009", 3, almox="777")]                    # de outro almoxarifado: não entra
    q = {x["id_item"]: x for x in R.quadro(cfg, ALMOX, varredura=var)}
    assert set(q) == {"5001", "5002", "5003", "5004"}
    assert (q["5001"]["sugestao_min"], q["5001"]["sugestao_max"]) == (2, 20)
    assert (q["5002"]["sugestao_min"], q["5002"]["sugestao_max"]) == (None, 12) and q["5002"]["avariada"]
    assert (q["5003"]["sugestao_min"], q["5003"]["sugestao_max"]) == (2.5, 25.0) and q["5003"]["decimal"]
    assert (q["5004"]["sugestao_min"], q["5004"]["sugestao_max"]) == (None, None) and q["5004"]["saldo"] is None
    assert q["5001"]["no_fracttal_min"] == 1                          # o que o Fracttal tem hoje (da varredura)
    assert q["5001"]["recomendado"] == (None, None) and q["5001"]["acordado"] == (None, None)
    assert q["5001"]["gravado"] is False and q["5001"]["saldo_de"] == "varredura"
    assert [x["codigo"] for x in R.quadro(cfg, ALMOX, varredura=var)] == sorted(x["codigo"] for x in q.values())


def test_quadro_usa_o_saldo_da_ultima_contagem_gravada(cfg):
    """O desenho (4.4): o saldo da última contagem GRAVADA; sem ela, o da varredura. O número da contagem vale mais que o
    da madrugada, e a mais nova das contagens gravadas da peça é a que vale."""
    F.acrescentar(cfg, F.ABA_EVENTO, [
        {"quando": "2026-10-20T10:00:00Z", "tipo": "peca_gravada", "contagem_id": "C-1", "id_almoxarifado": ALMOX,
         "id_item": "5001", "de_qtd": 10, "para_qtd": 6},
        {"quando": "2026-10-25T10:00:00Z", "tipo": "peca_gravada", "contagem_id": "C-2", "id_almoxarifado": ALMOX,
         "id_item": "5001", "de_qtd": 6, "para_qtd": 15},
        {"quando": "2026-10-26T10:00:00Z", "tipo": "conflito", "contagem_id": "C-3", "id_almoxarifado": ALMOX,
         "id_item": "5002", "para_qtd": 99}])                         # conflito não é saldo gravado
    q = {x["id_item"]: x for x in R.quadro(cfg, ALMOX, varredura=[_v(5001, "SP-CAB-001", 10), _v(5002, "SP-CAB-002", 4)])}
    assert q["5001"]["saldo"] == 15 and q["5001"]["saldo_de"] == "contagem gravada"
    assert (q["5001"]["sugestao_min"], q["5001"]["sugestao_max"]) == (3, 30)
    assert q["5002"]["saldo"] == 4 and q["5002"]["saldo_de"] == "varredura"


# ── registrar: o recomendado e o acordado ficam no livro, e o Fracttal não é chamado ─────────────────────────────────

def test_so_o_acordado_vai_ao_fracttal(cfg):
    """O caso do desenho: a Grid recomenda 3 e 30; o cliente acordou 2 e 20. Registrar o recomendado não fala com o
    Fracttal (nem tem como: `decidir` não recebe o estoque); gravar o acordado chama `definir_regua` com o MÍNIMO e o
    MÁXIMO acordados, relê e só então anota. O recomendado fica só no livro."""
    var = [_v(5001, "SP-CAB-001", 10, minimo=1)]
    falso = _falso()
    R.decidir(cfg, ALMOX, "5001", recomendado=(3, 30), pessoa=PESSOA, varredura=var)
    assert falso.chamadas == []
    R.decidir(cfg, ALMOX, "5001", acordado=(2, 20), pessoa=PESSOA, varredura=var)
    assert falso.chamadas == []
    R.gravar_acordado(cfg, ALMOX, "5001", falso, PESSOA)
    assert falso.chamadas == ["ler", "definir_regua", "ler"]
    item = falso.ler(ALMOX)["5001"]
    assert (item["minimo"], item["maximo"]) == (2.0, 20.0)            # o acordado, e não o recomendado (3 e 30)
    assert item["saldo"] == 10.0 and falso.movimentos == []         # a régua não mexe em saldo nem gera movimento
    q = R.quadro(cfg, ALMOX, varredura=var)[0]
    assert q["recomendado"] == (3, 30) and q["acordado"] == (2, 20) and q["gravado"] is True


def test_decidir_guarda_o_retrato_e_quem_decidiu(cfg):
    """Cada linha do livro é o retrato da decisão (a última vale): decidir só o recomendado leva junto o acordado de
    antes, senão a última linha apagaria o que o cliente acordou. A pessoa vai pelo código (HMAC) e nunca pelo e-mail; a
    usina vai com a linhagem; a sugestão do momento fica guardada ao lado da decisão (é o histórico do mínimo)."""
    var = [_v(5001, "SP-CAB-001", 10)]
    R.decidir(cfg, ALMOX, "5001", acordado=(2, 20), pessoa=PESSOA, varredura=var)
    R.decidir(cfg, ALMOX, "5001", recomendado=(3, 30), pessoa=PESSOA, varredura=var)
    linhas = _livro(cfg, F.ABA_REGUA)
    assert len(linhas) == 2
    ultima = linhas[-1]
    assert (ultima["recomendado_min_qtd"], ultima["recomendado_max_qtd"]) == (3, 30)
    assert (ultima["acordado_min_qtd"], ultima["acordado_max_qtd"]) == (2, 20)       # o acordado de antes seguiu junto
    assert (ultima["sugestao_min_qtd"], ultima["sugestao_max_qtd"]) == (2, 20)
    assert ultima["id_almoxarifado"] == ALMOX and ultima["id_item"] == "5001" and ultima["codigo"] == "SP-CAB-001"
    assert ultima["usina_id"] == 7 and ultima["usina_ligada_por"] == LIGADA and int(ultima["gravado_fracttal"] or 0) == 0
    assert re.fullmatch(r"[0-9a-f]{24}", ultima["pessoa_hmac"])
    assert PESSOA["email"] not in json.dumps(linhas) and PESSOA["nome"] not in json.dumps(linhas)


def test_usina_que_nao_liga_vai_sem_usina_e_sem_linhagem(cfg):
    R.decidir(cfg, ALMOX, "5001", acordado=(2, 20), pessoa=PESSOA, varredura=[_v(5001, "SP-CAB-001", 10, usina_id=None)])
    linha = _livro(cfg, F.ABA_REGUA)[0]
    assert not linha["usina_id"] and not linha["usina_ligada_por"]


def test_senha_de_administrador_nao_diz_quem_e(cfg):
    """Quem entra pela senha não tem e-mail: a decisão vale e vai sem o código da pessoa (como a Técnicos por usina)."""
    R.decidir(cfg, ALMOX, "5001", acordado=(2, 20), pessoa={"nome": "administrador (senha)"},
              varredura=[_v(5001, "SP-CAB-001", 10)])
    assert not _livro(cfg, F.ABA_REGUA)[0]["pessoa_hmac"]


def test_decidir_o_acordado_depois_de_gravado_volta_a_nao_gravado(cfg):
    """O acordado novo ainda não está no Fracttal; mexer só no recomendado não desmarca o que já foi gravado."""
    var = [_v(5001, "SP-CAB-001", 10)]
    falso = _falso()
    R.decidir(cfg, ALMOX, "5001", acordado=(2, 20), pessoa=PESSOA, varredura=var)
    R.gravar_acordado(cfg, ALMOX, "5001", falso, PESSOA)
    assert R.quadro(cfg, ALMOX, varredura=var)[0]["gravado"] is True
    R.decidir(cfg, ALMOX, "5001", recomendado=(3, 30), pessoa=PESSOA, varredura=var)
    assert R.quadro(cfg, ALMOX, varredura=var)[0]["gravado"] is True
    R.decidir(cfg, ALMOX, "5001", acordado=(2, 25), pessoa=PESSOA, varredura=var)
    assert R.quadro(cfg, ALMOX, varredura=var)[0]["gravado"] is False


def test_sem_acordado_nao_grava(cfg):
    """Enquanto o PCM não registra o acordado, o Fracttal não muda: nem um pedido (nem a leitura) sai."""
    var = [_v(5001, "SP-CAB-001", 10)]
    falso = _falso()
    with pytest.raises(F.Recusada, match="acordad"):
        R.gravar_acordado(cfg, ALMOX, "5001", falso, PESSOA)
    R.decidir(cfg, ALMOX, "5001", recomendado=(3, 30), pessoa=PESSOA, varredura=var)
    with pytest.raises(F.Recusada, match="acordad"):
        R.gravar_acordado(cfg, ALMOX, "5001", falso, PESSOA)
    assert falso.chamadas == []
    assert [e for e in _livro(cfg, F.ABA_EVENTO) if e["tipo"] == "regua_gravada"] == []


@pytest.mark.parametrize("rec, aco", [
    ((5, 2), None), (None, (5, 2)),               # o mínimo acima do máximo
    ((-1, 2), None), (None, (2, -4)),             # negativo
    ((float("nan"), 2), None), (None, ("abc", 2)),
    (None, (2, None)), (None, (None, 20)),        # o acordado leva os dois (os dois vão ao Fracttal)
    ((None, None), None), (None, None),
])
def test_decidir_recusa_o_que_nao_e_regua_antes_de_escrever(cfg, rec, aco):
    """Erro de quem chama: nada vai ao livro (a tela devolve 400). O mínimo acima do máximo nem chega ao Fracttal."""
    with pytest.raises(ValueError):
        R.decidir(cfg, ALMOX, "5001", recomendado=rec, acordado=aco, pessoa=PESSOA, varredura=[_v(5001, "SP-CAB-001", 10)])
    assert _livro(cfg, F.ABA_REGUA) == []


def test_o_recomendado_aceita_peca_sem_minimo(cfg):
    """A avariada não tem mínimo (a régua de 14/10): o recomendado leva só o máximo."""
    R.decidir(cfg, ALMOX, "5002", recomendado=(None, 12), pessoa=PESSOA, varredura=[_v(5002, "SP-CAB-002-AV", 4)])
    q = R.quadro(cfg, ALMOX, varredura=[_v(5002, "SP-CAB-002-AV", 4)])[0]
    assert q["recomendado"] == (None, 12)


def test_decidir_de_peca_que_nao_esta_no_almoxarifado_e_recusado(cfg):
    """A peça vem do saldo do almoxarifado, nunca de um ID que a página trouxe: ID chutado não vira régua."""
    with pytest.raises(ValueError, match="almoxarifado"):
        R.decidir(cfg, ALMOX, "9999", acordado=(2, 20), pessoa=PESSOA, varredura=[_v(5001, "SP-CAB-001", 10)])
    assert _livro(cfg, F.ABA_REGUA) == []


def test_a_peca_so_vale_no_almoxarifado_dela(cfg):
    """A mesma peça está em dois almoxarifados com saldos diferentes: a decisão de um usa o saldo e a usina DELE. A peça que
    só existe em outro almoxarifado não é do pedido (o ID da página não escolhe o almoxarifado por baixo)."""
    var = [_v(5001, "SP-CAB-001", 99, almox="777", usina_id=8), _v(5001, "SP-CAB-001", 10, almox=ALMOX, usina_id=7),
           _v(6001, "SP-CAB-006", 4, almox="777")]
    R.decidir(cfg, ALMOX, "5001", acordado=(2, 20), pessoa=PESSOA, varredura=var)
    linha = _livro(cfg, F.ABA_REGUA)[0]
    assert (linha["sugestao_min_qtd"], linha["sugestao_max_qtd"], linha["usina_id"]) == (2, 20, 7)
    with pytest.raises(ValueError, match="almoxarifado"):
        R.decidir(cfg, ALMOX, "6001", acordado=(1, 4), pessoa=PESSOA, varredura=var)
    assert len(_livro(cfg, F.ABA_REGUA)) == 1


def test_aceita_o_numero_como_a_pagina_manda(cfg):
    """O formulário manda texto, com a vírgula do Brasil."""
    R.decidir(cfg, ALMOX, "5003", recomendado=("2,5", "25"), acordado=("2,5", " 30,5 "), pessoa=PESSOA,
              varredura=[_v(5003, "SP-CAB-003", 12.5, unidade="METRO")])
    q = R.quadro(cfg, ALMOX, varredura=[_v(5003, "SP-CAB-003", 12.5, unidade="METRO")])[0]
    assert q["recomendado"] == (2.5, 25) and q["acordado"] == (2.5, 30.5)


# ── gravar: a releitura confirma antes de anotar ──────────────────────────────────────────────────────────────────

def test_gravar_anota_o_evento_com_o_de_e_o_para(cfg):
    var = [_v(5001, "SP-CAB-001", 10)]
    falso = _falso()
    R.decidir(cfg, ALMOX, "5001", acordado=(2, 20), pessoa=PESSOA, varredura=var)
    texto = R.gravar_acordado(cfg, ALMOX, "5001", falso, PESSOA)
    assert "2" in texto and "20" in texto
    ev = [e for e in _livro(cfg, F.ABA_EVENTO) if e["tipo"] == "regua_gravada"]
    assert len(ev) == 1
    assert ev[0]["id_almoxarifado"] == ALMOX and ev[0]["id_item"] == "5001" and ev[0]["codigo"] == "SP-CAB-001"
    assert (ev[0]["de_qtd"], ev[0]["para_qtd"]) == (1, 2)             # o mínimo que o Fracttal tinha, e o que ficou
    assert ev[0]["usina_id"] == 7 and ev[0]["usina_ligada_por"] == LIGADA
    assert re.fullmatch(r"[0-9a-f]{24}", ev[0]["pessoa_hmac"])
    ultima = _livro(cfg, F.ABA_REGUA)[-1]
    assert int(ultima["gravado_fracttal"]) == 1 and (ultima["acordado_min_qtd"], ultima["acordado_max_qtd"]) == (2, 20)


class _FalsoQueNaoGrava(EstoqueFalso):
    """O Fracttal que responde bem e não muda a régua (a releitura mostra o número de antes)."""

    def definir_regua(self, id_almox, id_item, minimo, maximo):
        self.chamadas.append("definir_regua")


def test_releitura_que_nao_bate_nao_anota_regua_gravada(cfg):
    """Mostrar, gravar, RELER e só então registrar: se o Fracttal respondeu e o número não mudou, o evento
    `regua_gravada` não sai (o livro diria que o Fracttal tem o que não tem); sai um `erro`, e a peça segue não gravada."""
    var = [_v(5001, "SP-CAB-001", 10)]
    falso = _FalsoQueNaoGrava({ALMOX: {"5001": {"saldo": 10, "minimo": 1, "maximo": 4, "codigo": "SP-CAB-001"}}})
    R.decidir(cfg, ALMOX, "5001", acordado=(2, 20), pessoa=PESSOA, varredura=var)
    with pytest.raises(F.Recusada, match="releitura"):
        R.gravar_acordado(cfg, ALMOX, "5001", falso, PESSOA)
    tipos = [e["tipo"] for e in _livro(cfg, F.ABA_EVENTO)]
    assert "regua_gravada" not in tipos and tipos == ["erro"]
    assert R.quadro(cfg, ALMOX, varredura=var)[0]["gravado"] is False


def test_peca_nao_ligada_ao_almoxarifado_nao_grava(cfg):
    """A régua é do vínculo da peça com o almoxarifado: sem ele o Fracttal não tem onde guardá-la (e a gravação do
    saldo é que liga). Recusa antes de escrever qualquer coisa."""
    var = [_v(7777, "SP-CAB-777", 10)]
    falso = _falso()
    R.decidir(cfg, ALMOX, "7777", acordado=(2, 20), pessoa=PESSOA, varredura=var)
    with pytest.raises(F.Recusada, match="ligada"):
        R.gravar_acordado(cfg, ALMOX, "7777", falso, PESSOA)
    assert "definir_regua" not in falso.chamadas
    assert [e for e in _livro(cfg, F.ABA_EVENTO) if e["tipo"] == "regua_gravada"] == []


def test_limite_e_login_do_fracttal_passam_para_a_tela(cfg):
    """O 429 e o login morto são do Fracttal e sobem como são (a tela diz o que fazer); nada é anotado."""
    var = [_v(5001, "SP-CAB-001", 10)]
    R.decidir(cfg, ALMOX, "5001", acordado=(2, 20), pessoa=PESSOA, varredura=var)
    with pytest.raises(E.Limite):
        R.gravar_acordado(cfg, ALMOX, "5001", _falso_com(limite_em=1), PESSOA)
    with pytest.raises(E.SemLogin):
        R.gravar_acordado(cfg, ALMOX, "5001", _falso_com(expirar_em=1), PESSOA)
    assert [e for e in _livro(cfg, F.ABA_EVENTO) if e["tipo"] == "regua_gravada"] == []


def _falso_com(**defeito):
    return EstoqueFalso({ALMOX: {"5001": {"saldo": 10, "minimo": 1, "maximo": 4, "codigo": "SP-CAB-001"}}}, **defeito)


# ── as telas: só o setor PCM decide e grava ──────────────────────────────────────────────────────────────────────────

@pytest.fixture
def inv(app, banco, tmp_path, monkeypatch):  # noqa: F811
    """A varredura do App (Almoxarifado 10 na Altair, e o 20 que não liga) e o livro do inventário num arquivo."""
    monkeypatch.setattr(visao, "_agora", lambda: datetime(2026, 10, 25, 10, 0, tzinfo=BRT))
    _semear(banco)
    visao.limpar()
    F.limpar()
    app.config.update(NEXUS_ALMOX_INVENTARIO_ARQUIVO=str(tmp_path / "inventario.json"), TESTING=True)
    return app


def _pessoa_ms(app):
    """Quem entrou pela conta Microsoft da Grid: não tem o login do Fracttal, e o portão não encerra a sessão por isso (a de quem
    entrou pelo Fracttal cai se o pedido a /os chega sem o cookie dele). É quem a ponte atende sem o `os_sessao`."""
    import time
    c = _pessoa(app)
    with c.session_transaction() as sessao:
        sessao["via"], sessao["ms_ate"] = "microsoft", time.time() + 3600
    return c


def _estoque_da_sessao(monkeypatch, falso):
    monkeypatch.setattr(E, "estoque_da_sessao", lambda app: falso)


def test_tela_mostra_o_quadro_e_o_formulario_do_pcm(inv, monkeypatch):
    _no_setor(monkeypatch, SID.PCM)
    c = _pessoa_ms(inv)
    html = c.get("/t/pcm/pecas/inventario/regua").get_data(as_text=True)
    assert "Mínimo e máximo" in html and "Almoxarifado 10" in html and "Almoxarifado 20" in html
    r = c.get("/t/pcm/pecas/inventario/regua?almox=10")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "SP-1" in html and "Fusível 10A" in html and "SP-2" in html
    assert "Recomendado" in html and "Acordado" in html and "Registrar" in html and "Gravar no Fracttal" in html
    assert 'name="aco_min"' in html and 'name="rec_max"' in html
    assert "SP-3-AV" not in html                                       # essa é do almoxarifado 20
    html = c.get("/t/pcm/pecas/inventario/regua?almox=20").get_data(as_text=True)
    assert "SP-3-AV" in html and "avariada" in html.lower()


def test_a_regua_lista_o_almoxarifado_sem_saldo_e_nao_quebra(inv, banco, monkeypatch):  # noqa: F811
    """O Por almoxarifado ganhou os almoxarifados que o saldo do ciclo não traz (11/11/2026, item 4: o de uma usina nova que só
    mandou a contagem), e a régua usa a mesma lista: o novo aparece como "sem saldo ainda", e abri-lo não quebra (não há peça
    para a régua)."""
    from test_campo_visao import _aba
    from test_pcm_inventario_leitura import _linha
    from nexus.dados import almoxarifado as A
    _aba(banco, A.LIVRO_CONTAGENS, A.ABA_CONTAGENS, [_linha("C-30", "L1", "501", "3", almox="30",
                                                            contada="2026-10-25T11:00:00Z")])
    visao.limpar()
    _no_setor(monkeypatch, SID.PCM)
    c = _pessoa_ms(inv)
    html = c.get("/t/pcm/pecas/inventario/regua").get_data(as_text=True)
    item = re.search(r'regua\?almox=30"[^>]*>(.*?)</a>', html, re.S).group(1)
    assert "Almoxarifado 30" in item and "sem saldo ainda" in item and "0 peças" not in item
    r = c.get("/t/pcm/pecas/inventario/regua?almox=30")
    assert r.status_code == 200 and "Nenhuma peça com saldo neste almoxarifado" in r.get_data(as_text=True)


def test_so_o_setor_pcm_decide(inv, monkeypatch):
    """Quem não é do PCM nem administrador (outro setor, por exemplo) não decide nem grava: 403, e nada no livro nem no
    Fracttal. O setor dono é o PCM (a tela `pecas`); quem a vê por outro setor só olha (sem formulário)."""
    falso = _falso()
    _estoque_da_sessao(monkeypatch, falso)
    corpo = {"almox": "10", "item": "1", "aco_min": "1", "aco_max": "9"}
    c = _pessoa_ms(inv)
    _no_setor(monkeypatch, SID.PERFORMANCE)
    assert c.post("/t/pcm/pecas/inventario/regua/decidir", data=corpo).status_code == 403
    assert c.post("/os/_nexus/inventario/regua/gravar", data={"almox": "10", "item": "1"}).status_code == 403
    _no_setor(monkeypatch, SID.RESPONSAVEL_UFV)                       # os supervisores veem o Quadro, mas régua é do PCM
    assert c.post("/t/pcm/pecas/inventario/regua/decidir", data=corpo).status_code == 403
    assert falso.chamadas == [] and F.ler(inv.config, forcar=True)[F.ABA_REGUA] == []
    # o PCM decide; e a tela de quem só olha não traz o formulário
    _no_setor(monkeypatch, SID.PCM)
    r = c.post("/t/pcm/pecas/inventario/regua/decidir", data=corpo)
    assert r.status_code == 303
    assert len(F.ler(inv.config, forcar=True)[F.ABA_REGUA]) == 1


def test_tela_de_quem_so_olha_nao_tem_botao(inv, monkeypatch):
    """Quem vê a tela por outro setor lê a régua (os números registrados em texto) e não tem formulário nem botão."""
    from nexus.pcm import telas
    _no_setor(monkeypatch, SID.PCM)
    c = _pessoa_ms(inv)
    assert c.post("/t/pcm/pecas/inventario/regua/decidir",
                  data={"almox": "10", "item": "1", "aco_min": "2", "aco_max": "9", "rec_max": "5"}).status_code == 303
    monkeypatch.setattr(telas, "pode_programar", lambda: False)
    html = c.get("/t/pcm/pecas/inventario/regua?almox=10").get_data(as_text=True)
    assert "SP-1" in html and "mín 2 · máx 9" in html and "sem mínimo · máx 5" in html      # o acordado e o recomendado
    assert "regua/gravar" not in html and "regua/decidir" not in html
    assert 'name="aco_min"' not in html and "Registrar</button>" not in html


def test_decidir_pela_tela_grava_e_volta_para_o_almoxarifado(inv, monkeypatch):
    _no_setor(monkeypatch, SID.PCM)
    c = _pessoa_ms(inv)
    r = c.post("/t/pcm/pecas/inventario/regua/decidir", data={
        "almox": "10", "item": "2", "rec_min": "1", "rec_max": "4", "aco_min": "2,5", "aco_max": "9"})
    assert r.status_code == 303 and r.headers["Location"].endswith("/t/pcm/pecas/inventario/regua?almox=10")
    linha = F.ler(inv.config, forcar=True)[F.ABA_REGUA][0]
    assert (linha["recomendado_min_qtd"], linha["recomendado_max_qtd"]) == (1, 4)
    assert (linha["acordado_min_qtd"], linha["acordado_max_qtd"]) == (2.5, 9)
    assert linha["usina_id"] == 1 and linha["usina_ligada_por"] == LIGADA          # a Altair, pela de-para
    assert re.fullmatch(r"[0-9a-f]{24}", linha["pessoa_hmac"])
    html = c.get(r.headers["Location"]).get_data(as_text=True)
    assert "Registrado" in html and 'value="2,5"' in html
    # o formulário de gravar leva o acordado que a tela mostra (a ponte confere se ele ainda é o registrado)
    assert 'name="aco_min" value="2,5"' in html and 'name="aco_max" value="9"' in html


def test_minimo_acima_do_maximo_e_400_e_nao_grava(inv, monkeypatch):
    _no_setor(monkeypatch, SID.PCM)
    r = _pessoa_ms(inv).post("/t/pcm/pecas/inventario/regua/decidir", data={"almox": "10", "item": "1",
                                                                        "aco_min": "9", "aco_max": "2"})
    assert r.status_code == 400 and "mínimo" in r.get_data(as_text=True).lower()
    assert F.ler(inv.config, forcar=True)[F.ABA_REGUA] == []


def test_peca_de_outro_almoxarifado_e_400(inv, monkeypatch):
    _no_setor(monkeypatch, SID.PCM)
    r = _pessoa_ms(inv).post("/t/pcm/pecas/inventario/regua/decidir", data={"almox": "10", "item": "3",
                                                                        "aco_min": "1", "aco_max": "2"})
    assert r.status_code == 400 and F.ler(inv.config, forcar=True)[F.ABA_REGUA] == []


PONTE = "/os/_nexus/inventario/regua/gravar"
GRAVAR = {"almox": "10", "item": "1", "aco_min": "2", "aco_max": "9"}      # o que o formulário manda: a peça e o acordado que a tela mostrava


def test_gravar_pela_ponte_usa_o_login_de_quem_aprova(inv, monkeypatch):
    """O Fracttal é o da sessão de quem apertou (`estoque_da_sessao`); a ponte só grava o que está no livro, e a página mostra o
    aviso quando recarrega."""
    falso = EstoqueFalso({"10": {"1": {"saldo": 1, "minimo": 3, "maximo": 3, "codigo": "SP-1"}}})
    _estoque_da_sessao(monkeypatch, falso)
    _no_setor(monkeypatch, SID.PCM)
    c = com_o_fracttal(inv, _pessoa_ms(inv))
    corpo = {"almox": "10", "item": "1", "aco_min": "2", "aco_max": "9"}
    assert c.post("/t/pcm/pecas/inventario/regua/decidir", data=corpo).status_code == 303
    assert falso.chamadas == []
    r = c.post(PONTE, data=GRAVAR)
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert r.get_json()["volta"].endswith("/t/pcm/pecas/inventario/regua?almox=10")
    assert falso.chamadas == ["ler", "definir_regua", "ler"]
    assert (falso.ler("10")["1"]["minimo"], falso.ler("10")["1"]["maximo"]) == (2.0, 9.0)
    html = c.get(r.get_json()["volta"]).get_data(as_text=True)
    assert "régua gravada no fracttal: mínimo 2, máximo 9" in html.lower()


def test_a_gravacao_nao_e_mais_uma_rota_de_t_pcm(inv, monkeypatch):
    """O que fala com o Fracttal mora na ponte; em /t/pcm o login do Fracttal nunca chega."""
    _no_setor(monkeypatch, SID.PCM)
    assert _pessoa_ms(inv).post("/t/pcm/pecas/inventario/regua/gravar", data={"almox": "10", "item": "1"}).status_code == 404


def test_gravar_sem_o_acordado_e_409(inv, monkeypatch):
    falso = EstoqueFalso({"10": {"1": {"saldo": 1, "minimo": 3, "maximo": 3, "codigo": "SP-1"}}})
    _estoque_da_sessao(monkeypatch, falso)
    _no_setor(monkeypatch, SID.PCM)
    r = com_o_fracttal(inv, _pessoa_ms(inv)).post(PONTE, data=GRAVAR)
    assert r.status_code == 409 and "acordad" in r.get_json()["erro"].lower() and falso.chamadas == []


def test_quem_entrou_pela_senha_nao_grava_no_fracttal(inv, logado, monkeypatch):
    """A senha de administrador não é uma pessoa (a régua gravada no Fracttal ficaria sem dono), e o `os_sessao` que estiver no
    navegador é o login do Fracttal de OUTRA pessoa (a revisão final de 27/10/2026: a régua e o cadastro não conferiam): 409
    antes de qualquer pedido ao Fracttal. Registrar a decisão no Nexus continua valendo."""
    falso = EstoqueFalso({"10": {"1": {"saldo": 1, "minimo": 3, "maximo": 3, "codigo": "SP-1"}}})
    _estoque_da_sessao(monkeypatch, falso)
    assert logado.post("/t/pcm/pecas/inventario/regua/decidir",
                       data={"almox": "10", "item": "1", "aco_min": "2", "aco_max": "9"}).status_code == 303
    com_o_fracttal(inv, logado, "outra.pessoa@exemplo.test")      # o login do Fracttal de quem usou o navegador antes
    r = logado.post(PONTE, data=GRAVAR)
    assert r.status_code == 409 and "senha de administrador" in r.get_json()["erro"] and falso.chamadas == []
    assert F.ler(inv.config, forcar=True)[F.ABA_EVENTO] == []


def test_a_conta_do_fracttal_de_outra_pessoa_nao_grava(inv, monkeypatch):
    """O cookie do OS Creator sobrevive à troca de pessoa no mesmo navegador: a régua iria no nome de uma pessoa e no login de
    outra. 409 "a sessão do Fracttal é de outra conta" com o link para entrar de novo, como na gravação, e nada vai ao Fracttal."""
    from nexus.pcm.inventario import ponte_os
    falso = EstoqueFalso({"10": {"1": {"saldo": 1, "minimo": 3, "maximo": 3, "codigo": "SP-1"}}})
    _estoque_da_sessao(monkeypatch, falso)
    _no_setor(monkeypatch, SID.PCM)
    c = com_o_fracttal(inv, _pessoa_ms(inv), "outra.pessoa@exemplo.test")
    assert c.post("/t/pcm/pecas/inventario/regua/decidir", data=GRAVAR).status_code == 303
    r = c.post(PONTE, data=GRAVAR)
    assert r.status_code == 409 and r.get_json()["erro"] == ponte_os.OUTRA_CONTA and "/os/login?next=" in r.get_json()["login"]
    assert falso.chamadas == [] and F.ler(inv.config, forcar=True)[F.ABA_EVENTO] == []


def test_limite_do_fracttal_e_429_com_o_que_fazer(inv, monkeypatch):
    falso = EstoqueFalso({"10": {"1": {"saldo": 1, "minimo": 3, "maximo": 3, "codigo": "SP-1"}}}, limite_em=1)
    _estoque_da_sessao(monkeypatch, falso)
    _no_setor(monkeypatch, SID.PCM)
    c = com_o_fracttal(inv, _pessoa_ms(inv))
    c.post("/t/pcm/pecas/inventario/regua/decidir", data={"almox": "10", "item": "1", "aco_min": "2", "aco_max": "9"})
    r = c.post(PONTE, data=GRAVAR)
    assert r.status_code == 429 and "tente de novo" in r.get_json()["erro"].lower()


def test_resposta_perdida_do_fracttal_grava_de_novo_sem_duplicar(inv, monkeypatch):
    """A conexão cai depois de o Fracttal gravar: a tela diz que pode ter gravado e que gravar de novo é seguro (é o mesmo
    número); o evento só sai quando a releitura confere, então a régua é anotada UMA vez."""
    falso = EstoqueFalso({"10": {"1": {"saldo": 1, "minimo": 3, "maximo": 3, "codigo": "SP-1"}}},
                         perder_resposta={"definir_regua"})
    _estoque_da_sessao(monkeypatch, falso)
    _no_setor(monkeypatch, SID.PCM)
    c = com_o_fracttal(inv, _pessoa_ms(inv))
    c.post("/t/pcm/pecas/inventario/regua/decidir", data={"almox": "10", "item": "1", "aco_min": "2", "aco_max": "9"})
    r = c.post(PONTE, data=GRAVAR)
    assert r.status_code == 502 and "grave de novo" in r.get_json()["erro"]
    assert F.ler(inv.config, forcar=True)[F.ABA_EVENTO] == []             # nada anotado como gravado
    r = c.post(PONTE, data=GRAVAR)
    assert r.status_code == 200
    assert [e["tipo"] for e in F.ler(inv.config, forcar=True)[F.ABA_EVENTO]] == ["regua_gravada"]
    assert (falso.ler("10")["1"]["minimo"], falso.ler("10")["1"]["maximo"]) == (2.0, 9.0)


def test_gravar_com_a_regua_que_mudou_desde_que_a_tela_abriu_e_409(inv, monkeypatch):
    """Duas pessoas do PCM com a tela aberta: uma muda o acordado, a outra aperta Gravar com o número que via. O formulário leva
    o acordado que a tela mostrava; a ponte compara com o registrado de agora e, se mudou, não envia nada ao Fracttal."""
    falso = EstoqueFalso({"10": {"1": {"saldo": 1, "minimo": 3, "maximo": 3, "codigo": "SP-1"}}})
    _estoque_da_sessao(monkeypatch, falso)
    _no_setor(monkeypatch, SID.PCM)
    c = com_o_fracttal(inv, _pessoa_ms(inv))
    c.post("/t/pcm/pecas/inventario/regua/decidir", data={"almox": "10", "item": "1", "aco_min": "2", "aco_max": "9"})
    c.post("/t/pcm/pecas/inventario/regua/decidir", data={"almox": "10", "item": "1", "aco_min": "4", "aco_max": "9"})   # a outra pessoa
    r = c.post(PONTE, data=GRAVAR)                         # a tela da 1ª pessoa ainda mostrava 2 e 9
    assert r.status_code == 409 and "a régua mudou desde que você abriu a tela" in r.get_json()["erro"]
    assert "mínimo 4" in r.get_json()["erro"] and falso.chamadas == []
    r = c.post(PONTE, data={**GRAVAR, "aco_min": "4"})     # depois de recarregar, vê 4 e 9
    assert r.status_code == 200 and falso.ler("10")["1"]["minimo"] == 4.0


def test_gravar_sem_o_acordado_que_a_tela_mostrava_e_400(inv, monkeypatch):
    falso = EstoqueFalso({"10": {"1": {"saldo": 1, "minimo": 3, "maximo": 3, "codigo": "SP-1"}}})
    _estoque_da_sessao(monkeypatch, falso)
    _no_setor(monkeypatch, SID.PCM)
    c = com_o_fracttal(inv, _pessoa_ms(inv))
    c.post("/t/pcm/pecas/inventario/regua/decidir", data={"almox": "10", "item": "1", "aco_min": "2", "aco_max": "9"})
    r = c.post(PONTE, data={"almox": "10", "item": "1"})
    assert r.status_code == 400 and "acordado que mostrava" in r.get_json()["erro"]
    r = c.post(PONTE, data={**GRAVAR, "aco_max": "abc"})
    assert r.status_code == 400 and falso.chamadas == []


def test_acordado_decimal_so_em_metro_e_massa(cfg):
    """O Fracttal guarda o que se manda: 2,5 de uma peça contada em unidades seria um estoque que não existe. A unidade que a
    varredura diz vale já ao registrar; a que o Fracttal diz (`ler()["unidade"]`) vale antes do pedido que grava. O que não é
    METRO nem MASSA (inclusive a unidade que ninguém disse) é inteiro."""
    for unidade in ("unidade", "", "par"):
        with pytest.raises(ValueError, match="casa decimal"):
            R.decidir(cfg, ALMOX, "5001", acordado=(2.5, 9), pessoa=PESSOA, varredura=[_v(5001, "SP-CAB-001", 10, unidade=unidade)])
    assert _livro(cfg, F.ABA_REGUA) == []
    R.decidir(cfg, ALMOX, "5001", acordado=(2.5, 9), pessoa=PESSOA, varredura=[_v(5001, "SP-CAB-001", 10, unidade="massa")])
    R.decidir(cfg, ALMOX, "5002", acordado=("2", "9"), pessoa=PESSOA, varredura=[_v(5002, "SP-CAB-002", 10, unidade="unidade")])
    # a varredura dizia metro, o Fracttal diz unidade: a gravação para depois da leitura e antes do `definir_regua`
    R.decidir(cfg, ALMOX, "5001", acordado=(2.5, 9), pessoa=PESSOA, varredura=[_v(5001, "SP-CAB-001", 10, unidade="metro")])
    inteiro = EstoqueFalso({ALMOX: {"5001": {"saldo": 10, "minimo": 1, "maximo": 4, "codigo": "SP-CAB-001", "unidade": "UNIDADE"}}})
    with pytest.raises(ValueError, match="UNIDADE|unidade"):
        R.gravar_acordado(cfg, ALMOX, "5001", inteiro, PESSOA)
    assert inteiro.chamadas == ["ler"] and inteiro.ler(ALMOX)["5001"]["maximo"] == 4.0
    metro = EstoqueFalso({ALMOX: {"5001": {"saldo": 10, "minimo": 1, "maximo": 4, "codigo": "SP-CAB-001", "unidade": "METRO"}}})
    R.gravar_acordado(cfg, ALMOX, "5001", metro, PESSOA)
    assert (metro.ler(ALMOX)["5001"]["minimo"], metro.ler(ALMOX)["5001"]["maximo"]) == (2.5, 9.0)


def test_acordado_decimal_em_unidade_inteira_e_400_pela_tela(inv, monkeypatch):
    _no_setor(monkeypatch, SID.PCM)
    r = _pessoa_ms(inv).post("/t/pcm/pecas/inventario/regua/decidir", data={"almox": "10", "item": "1", "aco_min": "2,5",
                                                                           "aco_max": "9"})
    assert r.status_code == 400 and "casa decimal" in r.get_data(as_text=True)
    assert F.ler(inv.config, forcar=True)[F.ABA_REGUA] == []


def test_acordado_incompleto_no_livro_e_409_e_nao_quebra(cfg):
    """O livro é de quem o escreve (a API aceita linha à mão): um retrato com só o mínimo acordado não chega ao `definir_regua` nem
    quebra na conferência (comparar o máximo vazio). 409 com o que falta, nenhum pedido."""
    F.acrescentar(cfg, F.ABA_REGUA, [{"id_almoxarifado": ALMOX, "id_item": "5001", "codigo": "SP-CAB-001",
                                      "acordado_min_qtd": 2, "pessoa_hmac": "a1b2c3d4e5f60718293a4b5c"}])
    falso = _falso()
    with pytest.raises(F.Recusada, match="incompleto"):
        R.gravar_acordado(cfg, ALMOX, "5001", falso, PESSOA)
    assert falso.chamadas == [] and not any(e["tipo"] == "regua_gravada" for e in _livro(cfg, F.ABA_EVENTO))


class _Lento(EstoqueFalso):
    """O Fracttal que demora no `definir_regua` (a gravação lenta de uma peça) até o teste soltar."""

    def __init__(self, *a, **k):
        import threading
        super().__init__(*a, **k)
        self.entrou, self.soltar = threading.Event(), threading.Event()

    def definir_regua(self, id_almox, id_item, minimo, maximo):
        self.entrou.set()
        self.soltar.wait(10)
        return super().definir_regua(id_almox, id_item, minimo, maximo)


def test_a_trava_e_por_peca_e_a_gravacao_lenta_de_uma_nao_segura_as_outras(cfg):
    """Uma trava do módulo inteiro, segurada enquanto o Fracttal responde, faria todo o PCM esperar uma gravação de uma peça. A
    trava é da peça: enquanto a 5001 espera o Fracttal, registrar a 5002 passa na hora."""
    import threading
    var = [_v(5001, "SP-CAB-001", 10), _v(5002, "SP-CAB-002", 4)]
    R.decidir(cfg, ALMOX, "5001", acordado=(2, 20), pessoa=PESSOA, varredura=var)
    lento = _Lento({ALMOX: {"5001": {"saldo": 10, "minimo": 1, "maximo": 4, "codigo": "SP-CAB-001"}}})
    t = threading.Thread(target=lambda: R.gravar_acordado(cfg, ALMOX, "5001", lento, PESSOA))
    t.start()
    try:
        assert lento.entrou.wait(10)
        feito = threading.Event()
        threading.Thread(target=lambda: (R.decidir(cfg, ALMOX, "5002", acordado=(1, 8), pessoa=PESSOA, varredura=var),
                                         feito.set())).start()
        assert feito.wait(5), "registrar outra peça esperou a gravação lenta no Fracttal"
        # nem a GRAVAÇÃO de outra peça espera: a trava da gravação também é da peça
        outro = EstoqueFalso({ALMOX: {"5002": {"saldo": 4, "minimo": 0, "maximo": 0, "codigo": "SP-CAB-002"}}})
        gravou = threading.Event()
        threading.Thread(target=lambda: (R.gravar_acordado(cfg, ALMOX, "5002", outro, PESSOA), gravou.set())).start()
        assert gravou.wait(5), "gravar outra peça esperou a gravação lenta no Fracttal"
        assert (outro.ler(ALMOX)["5002"]["minimo"], outro.ler(ALMOX)["5002"]["maximo"]) == (1.0, 8.0)
    finally:
        lento.soltar.set()
        t.join(10)
    assert [e["tipo"] for e in _livro(cfg, F.ABA_EVENTO)] == ["regua_gravada", "regua_gravada"]


def test_duas_pessoas_na_mesma_peca_nao_apagam_o_que_a_outra_registrou(cfg, monkeypatch):
    """Ler o retrato de antes e escrever o de agora é uma conta só por peça: a Grid registra o recomendado e o cliente o acordado
    ao mesmo tempo, e as duas ficam no último retrato (sem a trava, o 2º retrato nascia do "antes" vazio e perdia o 1º)."""
    import threading
    import time
    var = [_v(5001, "SP-CAB-001", 10)]
    escrever = F.acrescentar

    def devagar(cfg_, aba, linhas):
        time.sleep(0.3)                  # entre ler o retrato de antes e gravar o de agora, a outra pessoa entra
        return escrever(cfg_, aba, linhas)
    monkeypatch.setattr(F, "acrescentar", devagar)
    ts = [threading.Thread(target=lambda: R.decidir(cfg, ALMOX, "5001", recomendado=(3, 30), pessoa=PESSOA, varredura=var)),
          threading.Thread(target=lambda: R.decidir(cfg, ALMOX, "5001", acordado=(2, 20), pessoa=PESSOA, varredura=var))]
    for t in ts:
        t.start()
    for t in ts:
        t.join(10)
    q = R.quadro(cfg, ALMOX, varredura=var)[0]
    assert q["recomendado"] == (3, 30) and q["acordado"] == (2, 20)


def _jwt_e_cookie(app):
    """O cookie `os_sessao` como o login do Fracttal o grava (a sessão assinada do clone do OS Creator, com o JWT), da mesma
    conta da pessoa da sessão do Nexus (`_pessoa`): a ponte confere."""
    from nexus.torres.oscreator import ponte
    clone = ponte.clone(app)
    jwt = _jwt()
    valor = clone.session_interface.get_signing_serializer(clone).dumps(
        {"jwt": jwt, "conta": {"email": "pessoa.teste@exemplo.com", "nome": "Pessoa"}})
    return jwt, valor


def test_o_login_do_fracttal_so_chega_na_ponte(inv, api_do_clone, monkeypatch):
    """O defeito que a revisão achou: o cookie `os_sessao` (o JWT do Fracttal) é gravado com Path=/os, e o navegador não o manda
    para /t/pcm. Aqui o `estoque_da_sessao` é o DE VERDADE (só a rede do `api` do clone é de mentira), o cookie vai com
    Path=/os como o login o grava, e: a rota da ponte vê o login e grava no Fracttal; uma rota /t/pcm, com o mesmo cliente, não
    vê (a sonda chama o mesmo `estoque_da_sessao` e leva `SemLogin`)."""
    @inv.route("/t/pcm/pecas/inventario/_sonda")
    def sonda():                        # uma rota de /t/pcm: o que o `estoque_da_sessao` veria ali
        try:
            E.estoque_da_sessao(inv)
            return "viu o login"
        except E.SemLogin:
            return "sem login"

    pedidos = []
    nivel = {"min": 1.0, "max": 3.0}

    def post(url, headers=None, json=None, timeout=None):
        metodo = json[0]["method"]
        pedidos.append((metodo, headers["Authorization"]))
        if metodo == "inventories.warehouses_items_stock":
            return _result({"success": True, "total": 1, "data": [{
                "id": 777, "id_item": 1, "code": "SP-1", "stock": 1, "min_stock_level": nivel["min"],
                "max_stock_level": nivel["max"]}]})
        assert metodo == "inventories.warehouses_items_update", metodo
        nivel.update(min=float(json[0]["params"]["min_stock_level"]), max=float(json[0]["params"]["max_stock_level"]))
        return _result({"success": True, "data": None})
    monkeypatch.setattr(api_do_clone.requests, "post", post)
    monkeypatch.setattr(E, "RITMO", E.Ritmo(dormir=lambda s: None))           # sem esperar o 1 pedido por segundo de verdade
    jwt, cookie = _jwt_e_cookie(inv)
    _no_setor(monkeypatch, SID.PCM)
    c = _pessoa(inv)                                                           # a sessão nasceu do login do Fracttal
    c.set_cookie("os_sessao", cookie, path="/os")                              # como o login do Fracttal o grava
    assert c.post("/t/pcm/pecas/inventario/regua/decidir", data={"almox": "10", "item": "1", "aco_min": "2",
                                                                   "aco_max": "9"}).status_code == 303
    assert c.get("/t/pcm/pecas/inventario/_sonda").get_data(as_text=True) == "sem login"
    assert pedidos == []
    r = c.post(PONTE, data=GRAVAR)
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert [m for m, _ in pedidos] == ["inventories.warehouses_items_stock", "inventories.warehouses_items_update",
                                       "inventories.warehouses_items_stock"]
    assert {h for _, h in pedidos} == {f"Bearer {jwt}"}                        # no login de quem apertou
    assert nivel == {"min": 2.0, "max": 9.0}
    assert [e["tipo"] for e in F.ler(inv.config, forcar=True)[F.ABA_EVENTO]] == ["regua_gravada"]
    # sem o cookie (a senha de administrador, ou o login que venceu), a mesma ponte responde 401 com o link do login
    r = _pessoa_ms(inv).post(PONTE, data=GRAVAR)
    assert r.status_code == 401 and "/os/login" in r.get_json()["login"]


def test_pedido_de_outro_site_e_recusado(inv, monkeypatch):
    _no_setor(monkeypatch, SID.PCM)
    r = _pessoa_ms(inv).post("/t/pcm/pecas/inventario/regua/decidir", data={"almox": "10", "item": "1", "aco_min": "1",
                                                                        "aco_max": "2"},
                          headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    r = _pessoa_ms(inv).post(PONTE, data=GRAVAR, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and "erro" in r.get_json()


def test_sem_cor_fora_de_token_nem_endereco_da_raiz():
    """Cor só por token, nos dois temas; endereço nunca a partir da raiz (o Nexus pode rodar debaixo de um prefixo)."""
    t = (RAIZ / "nexus" / "templates" / "pcm" / "inventario_regua.html").read_text("utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,8}", t) and "rgba(" not in t
    assert not re.search(r"""(href|action|src)="/""", t)
    for nome in ("pcm-regua.js", "pcm-ponte-inventario.js"):
        js = (RAIZ / "nexus" / "static" / nome).read_text("utf-8")
        assert not re.search(r"""["']/(t|os)/""", js)                      # o endereço vem do action, por nexusRota()
    assert 'action="{{ raiz }}/os/_nexus/inventario/regua/gravar"' in t and "data-ponte" in t
    css = (RAIZ / "nexus" / "static" / "pcm.css").read_text("utf-8")
    bloco = css[css.index("/* ── Régua de mínimo e máximo"):]
    proximo = bloco.find("/* ── ", 10)
    bloco = bloco if proximo < 0 else bloco[:proximo]
    assert ".rg-almoxes" in bloco and ".rg-n{" in bloco          # o menu próprio (rg-nav) saiu: as abas do Almoxarifado
    assert not re.search(r"#[0-9a-fA-F]{3,8}", bloco) and "rgba(" not in bloco


# ── todos os acordados de um almoxarifado de uma vez (11/11/2026, item 2 da 2ª rodada) ─────────────────────────────────────
# O PCM: "Mínimo e máximo: não está atualizando após a auditoria automaticamente no Fracttal". Decisão do Levi (11/11/2026):
# vai o ACORDADO registrado na régua, a regra de sempre; a peça sem acordado não muda, e o recomendado e a sugestão nunca vão.
# O `gravar_acordados` é o mesmo para o botão da régua e para o fim da gravação de uma contagem.
QUEM = {"pessoa_hmac": "a1b2c3d4e5f60718293a4b5c"}


def _falso_lote(**defeito):
    """O almoxarifado com quatro peças: a 5001 e a 5004 com a régua de antes, a 5003 já com o acordado que vai ser registrado."""
    return EstoqueFalso({ALMOX: {"5001": {"saldo": 10, "minimo": 1, "maximo": 4, "codigo": "SP-CAB-001"},
                                 "5002": {"saldo": 4, "minimo": 0, "maximo": 0, "codigo": "SP-CAB-002"},
                                 "5003": {"saldo": 9, "minimo": 2, "maximo": 20, "codigo": "SP-CAB-003"},
                                 "5004": {"saldo": 7, "minimo": 5, "maximo": 9, "codigo": "SP-CAB-004"}}}, **defeito)


VAR_LOTE = [_v(5001, "SP-CAB-001", 10), _v(5002, "SP-CAB-002", 4), _v(5003, "SP-CAB-003", 9), _v(5004, "SP-CAB-004", 7)]


def _acordar(cfg, *pares):
    for item, aco in pares:
        R.decidir(cfg, ALMOX, item, acordado=aco, pessoa=PESSOA, varredura=VAR_LOTE)


def _eventos(cfg, tipo=None):
    return [e for e in _livro(cfg, F.ABA_EVENTO) if tipo is None or e["tipo"] == tipo]


def test_gravar_acordados_manda_so_o_acordado_diferente(cfg):
    """Só vai a peça com acordado registrado e diferente do que o Fracttal tem: a 5001 (de 1 e 4 para 2 e 20). A 5003 já tem o
    acordado (não gasta pedido, e passa a "gravado no Fracttal": é o que ele tem), a 5004 não tem acordado (só o recomendado,
    que nunca vai) e não muda. Um pedido de leitura, um por peça mandada e a releitura."""
    _acordar(cfg, ("5001", (2, 20)), ("5003", (2, 20)))
    R.decidir(cfg, ALMOX, "5004", recomendado=(3, 30), pessoa=PESSOA, varredura=VAR_LOTE)
    falso = _falso_lote()
    r = R.gravar_acordados(cfg, ALMOX, falso, QUEM)
    assert falso.chamadas == ["ler", "definir_regua", "ler"]
    lido = falso.ler(ALMOX)
    assert (lido["5001"]["minimo"], lido["5001"]["maximo"]) == (2.0, 20.0)
    assert (lido["5004"]["minimo"], lido["5004"]["maximo"]) == (5.0, 9.0)            # sem acordado: não muda
    assert (r["total"], r["gravadas"], r["iguais"], r["falhas"]) == (2, 1, 1, 0)
    ev = _eventos(cfg, "regua_gravada")
    assert [(e["id_item"], e["de_qtd"], e["para_qtd"]) for e in ev] == [("5001", 1, 2)]
    assert ev[0]["pessoa_hmac"] == QUEM["pessoa_hmac"] and ev[0]["usina_id"] == 7 and ev[0]["codigo"] == "SP-CAB-001"
    q = {x["id_item"]: x for x in R.quadro(cfg, ALMOX, varredura=VAR_LOTE)}
    assert q["5001"]["gravado"] and q["5003"]["gravado"] and not q["5004"]["gravado"]
    assert "1 gravado no Fracttal" in r["texto"] and "1 já estava igual" in r["texto"]


def test_gravar_acordados_sem_acordado_nada_sai(cfg):
    """Nenhuma peça do almoxarifado com acordado: nem a leitura vai ao Fracttal (a cota é da empresa)."""
    R.decidir(cfg, ALMOX, "5001", recomendado=(3, 30), pessoa=PESSOA, varredura=VAR_LOTE)
    falso = _falso_lote()
    r = R.gravar_acordados(cfg, ALMOX, falso, QUEM)
    assert falso.chamadas == [] and r["total"] == 0 and "nenhuma peça" in r["texto"].lower()
    assert _eventos(cfg) == []


class _RecusaUma(EstoqueFalso):
    """O Fracttal que recusa (o `success: false`) a régua de uma peça e aceita a das outras."""

    def __init__(self, *a, recusar="5001", **k):
        super().__init__(*a, **k)
        self.recusar = recusar

    def definir_regua(self, id_almox, id_item, minimo, maximo):
        if str(id_item) == self.recusar:
            self.chamadas.append("definir_regua")
            raise E.Recusado("ITEM_LOCKED", "inventories.warehouses_items_update")
        return super().definir_regua(id_almox, id_item, minimo, maximo)


def test_a_falha_de_uma_peca_nao_para_as_outras(cfg):
    """O Fracttal recusa a 5001: ela vira um evento `erro` (com o porquê, cifrado) e segue sem gravar; a 5002 vai e é relida."""
    _acordar(cfg, ("5001", (2, 20)), ("5002", (1, 8)))
    falso = _RecusaUma({ALMOX: {"5001": {"saldo": 10, "minimo": 1, "maximo": 4, "codigo": "SP-CAB-001"},
                                "5002": {"saldo": 4, "minimo": 0, "maximo": 0, "codigo": "SP-CAB-002"}}})
    r = R.gravar_acordados(cfg, ALMOX, falso, QUEM)
    assert (r["gravadas"], r["falhas"]) == (1, 1)
    assert [e["id_item"] for e in _eventos(cfg, "regua_gravada")] == ["5002"]
    erro = _eventos(cfg, "erro")
    assert [e["id_item"] for e in erro] == ["5001"]
    assert "recusou" in F.decifrar(cfg, F.ABA_EVENTO, erro[0])["motivo"]
    q = {x["id_item"]: x for x in R.quadro(cfg, ALMOX, varredura=VAR_LOTE)}
    assert not q["5001"]["gravado"] and q["5002"]["gravado"]
    assert "1 falhou" in r["texto"]


def test_a_resposta_perdida_e_decidida_pela_releitura(cfg):
    """A conexão cai depois de o Fracttal gravar a 5001: a releitura mostra o acordado, e ela é anotada como gravada (uma vez só),
    sem erro."""
    _acordar(cfg, ("5001", (2, 20)))
    falso = _falso_lote(perder_resposta={"definir_regua"})
    r = R.gravar_acordados(cfg, ALMOX, falso, QUEM)
    assert r["gravadas"] == 1 and r["falhas"] == 0
    assert [e["tipo"] for e in _eventos(cfg)] == ["regua_gravada"]


def test_a_releitura_que_nao_bate_vira_erro(cfg):
    """O Fracttal respondeu e a releitura mostra o número de antes: `erro`, e a peça segue não gravada (o livro nunca diz que o
    Fracttal tem o que não tem)."""
    _acordar(cfg, ("5001", (2, 20)))
    falso = _FalsoQueNaoGrava({ALMOX: {"5001": {"saldo": 10, "minimo": 1, "maximo": 4, "codigo": "SP-CAB-001"}}})
    r = R.gravar_acordados(cfg, ALMOX, falso, QUEM)
    assert (r["gravadas"], r["falhas"]) == (0, 1)
    assert [e["tipo"] for e in _eventos(cfg)] == ["erro"]
    assert "releitura" in F.decifrar(cfg, F.ABA_EVENTO, _eventos(cfg)[0])["motivo"]
    assert not R.quadro(cfg, ALMOX, varredura=VAR_LOTE)[0]["gravado"]


def test_o_limite_do_fracttal_espera_e_tenta_de_novo(cfg):
    """O 429 no meio: espera 62 s (a cota é por minuto) e tenta de novo UMA vez; passou, segue. O 429 de novo para o lote: o que
    já foi relido fica anotado, e o resto não é mandado (o texto diz quantas faltaram)."""
    _acordar(cfg, ("5001", (2, 20)), ("5002", (1, 8)))
    esperas = []
    falso = _falso_lote(limite_em=2)                         # a 1ª régua mandada leva 429; a repetição passa
    r = R.gravar_acordados(cfg, ALMOX, falso, QUEM, dormir=esperas.append)
    assert esperas == [R.ESPERA_LIMITE_S] and r["gravadas"] == 2
    _acordar(cfg, ("5001", (3, 30)), ("5002", (2, 9)))
    esperas.clear()
    falso = _falso_lote(limite_em=[2, 3])                    # 429 de novo: para
    r = R.gravar_acordados(cfg, ALMOX, falso, QUEM, dormir=esperas.append)
    assert r["parou"] and r["gravadas"] == 0 and r["nao_enviadas"] == 2 and "limite" in r["texto"].lower()
    assert (falso.ler(ALMOX)["5002"]["minimo"], falso.ler(ALMOX)["5002"]["maximo"]) == (0.0, 0.0)


def test_o_login_que_expira_no_meio_para_e_anota_o_que_foi(cfg):
    """O login do Fracttal que expira no meio: o que já foi mandado não tem como ser relido agora, e nada é anotado como gravado
    sem a releitura; o resto não é mandado."""
    _acordar(cfg, ("5001", (2, 20)), ("5002", (1, 8)))
    falso = _falso_lote(expirar_em=3)                        # ler, a 1ª régua; a 2ª já cai
    r = R.gravar_acordados(cfg, ALMOX, falso, QUEM)
    assert r["parou"] and r["gravadas"] == 0 and "login" in r["texto"].lower()
    assert _eventos(cfg, "regua_gravada") == []


def test_a_releitura_aparece_no_quadro(cfg, monkeypatch):
    """Depois de gravar, o quadro mostra o que o Fracttal tem agora, pela releitura (o mínimo e o máximo, e a hora), sem esperar
    a varredura do App; a varredura que vier depois da releitura volta a valer."""
    from datetime import timezone as tz
    _acordar(cfg, ("5001", (2, 20)))
    cfg["NEXUS_DADOS"] = cfg["NEXUS_ALMOX_INVENTARIO_ARQUIVO"].rsplit("inventario.json", 1)[0] + "dados"
    monkeypatch.setattr(visao, "_agora", lambda: datetime(2026, 10, 25, 15, 0, tzinfo=BRT))
    R.gravar_acordados(cfg, ALMOX, _falso_lote(), QUEM, agora=lambda: datetime(2026, 10, 25, 14, 5, tzinfo=BRT).astimezone(tz.utc))
    q = {x["id_item"]: x for x in R.quadro(cfg, ALMOX, varredura=VAR_LOTE, lida_depois_de="2026-10-25T03:29:42Z")}
    assert (q["5001"]["agora_min"], q["5001"]["agora_max"], q["5001"]["agora_em"]) == (2, 20, "às 14:05")
    assert (q["5004"]["agora_min"], q["5004"]["agora_max"]) == (5, 9)        # a peça que não mudou também foi relida
    depois = {x["id_item"]: x for x in R.quadro(cfg, ALMOX, varredura=VAR_LOTE, lida_depois_de="2026-10-26T03:29:42Z")}
    assert depois["5001"]["agora_em"] == ""                                   # a varredura de 26/10 é mais nova
    monkeypatch.setattr(visao, "_agora", lambda: datetime(2026, 10, 26, 9, 0, tzinfo=BRT))
    q = {x["id_item"]: x for x in R.quadro(cfg, ALMOX, varredura=VAR_LOTE, lida_depois_de="2026-10-25T03:29:42Z")}
    assert q["5001"]["agora_em"] == "em 25/10 às 14:05"                       # de outro dia, com a data


def test_gravar_um_acordado_tambem_guarda_a_releitura(cfg):
    """O botão de uma peça relê o almoxarifado inteiro: o quadro mostra o que o Fracttal tem agora de todas."""
    _acordar(cfg, ("5001", (2, 20)))
    cfg["NEXUS_DADOS"] = cfg["NEXUS_ALMOX_INVENTARIO_ARQUIVO"].rsplit("inventario.json", 1)[0] + "dados"
    R.gravar_acordado(cfg, ALMOX, "5001", _falso_lote(), PESSOA)
    q = {x["id_item"]: x for x in R.quadro(cfg, ALMOX, varredura=VAR_LOTE, lida_depois_de="2000-01-01T00:00:00Z")}
    assert (q["5001"]["agora_min"], q["5001"]["agora_max"]) == (2, 20) and q["5004"]["agora_max"] == 9


def test_o_acordado_mudado_no_meio_nao_vira_gravado(cfg, monkeypatch):
    """Outra pessoa do PCM registra outro acordado da 5001 enquanto o lote está no Fracttal: o evento diz o que foi (e o Fracttal
    tem), mas a peça não passa a "gravado": o acordado de agora ainda não foi."""
    _acordar(cfg, ("5001", (2, 20)))
    falso = _falso_lote()
    original = falso.definir_regua

    def e_no_meio(id_almox, id_item, minimo, maximo):
        original(id_almox, id_item, minimo, maximo)
        # o retrato que o `decidir` da outra pessoa escreve (de outro pedido: aqui, direto no livro)
        F.acrescentar(cfg, F.ABA_REGUA, [{"id_almoxarifado": ALMOX, "id_item": "5001", "codigo": "SP-CAB-001",
                                          "acordado_min_qtd": 3, "acordado_max_qtd": 25, "gravado_fracttal": 0,
                                          "pessoa_hmac": QUEM["pessoa_hmac"]}])
    monkeypatch.setattr(falso, "definir_regua", e_no_meio)
    R.gravar_acordados(cfg, ALMOX, falso, QUEM)
    assert [e["para_qtd"] for e in _eventos(cfg, "regua_gravada")] == [2]
    q = R.quadro(cfg, ALMOX, varredura=VAR_LOTE)[0]
    assert q["acordado"] == (3, 25) and q["gravado"] is False


# ── o botão da régua: pela ponte, com as recusas da ponte ───────────────────────────────────────────────────────────────
TODOS = "/os/_nexus/inventario/regua/gravar_todos"


def _falso_10():
    return EstoqueFalso({"10": {"1": {"saldo": 1, "minimo": 3, "maximo": 3, "codigo": "SP-1"},
                                "2": {"saldo": 5, "minimo": 5, "maximo": 5, "codigo": "SP-2"}}})


def test_gravar_todos_pela_ponte(inv, monkeypatch, tmp_path):
    """O botão "Gravar no Fracttal todos os acordados deste almoxarifado": no login de quem apertou, a mesma regra, e a página
    mostra o resumo ao recarregar e o que o Fracttal tem agora, pela releitura."""
    inv.config["NEXUS_DADOS"] = str(tmp_path / "dados")          # a releitura fica na pasta de dados
    falso = _falso_10()
    _estoque_da_sessao(monkeypatch, falso)
    _no_setor(monkeypatch, SID.PCM)
    c = com_o_fracttal(inv, _pessoa_ms(inv))
    for corpo in ({"almox": "10", "item": "1", "aco_min": "2", "aco_max": "9"},
                  {"almox": "10", "item": "2", "aco_min": "5", "aco_max": "5"}):
        assert c.post("/t/pcm/pecas/inventario/regua/decidir", data=corpo).status_code == 303
    html = c.get("/t/pcm/pecas/inventario/regua?almox=10").get_data(as_text=True)
    assert f'action="{TODOS}"' in html and "Gravar no Fracttal todos os acordados deste almoxarifado" in html
    r = c.post(TODOS, data={"almox": "10"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert r.get_json()["volta"].endswith("/t/pcm/pecas/inventario/regua?almox=10")
    assert falso.chamadas == ["ler", "definir_regua", "ler"]
    html = c.get(r.get_json()["volta"]).get_data(as_text=True)
    assert "1 gravado no Fracttal" in html and "no Fracttal agora" in html and "mín 2, máx 9" in html


def test_gravar_todos_recusas_da_ponte(inv, logado, monkeypatch):
    """As recusas de sempre da ponte, antes de qualquer pedido ao Fracttal: outro setor 403; sem o cookie do Fracttal 401 com o
    link do login; a conta do Fracttal de outra pessoa 409; a senha de administrador 409. E com uma gravação de contagem andando
    no almoxarifado, 409 (ela mesma manda os acordados no fim)."""
    from nexus.pcm.inventario import gravacao as G
    from nexus.pcm.inventario import ponte_os
    falso = _falso_10()
    _estoque_da_sessao(monkeypatch, falso)
    _no_setor(monkeypatch, SID.PERFORMANCE)
    assert _pessoa_ms(inv).post(TODOS, data={"almox": "10"}).status_code == 403
    _no_setor(monkeypatch, SID.PCM)
    r = _pessoa_ms(inv).post(TODOS, data={"almox": "10"})
    assert r.status_code == 401 and "/os/login" in r.get_json()["login"]
    r = com_o_fracttal(inv, _pessoa_ms(inv), "outra.pessoa@exemplo.test").post(TODOS, data={"almox": "10"})
    assert r.status_code == 409 and r.get_json()["erro"] == ponte_os.OUTRA_CONTA
    com_o_fracttal(inv, logado, "outra.pessoa@exemplo.test")
    r = logado.post(TODOS, data={"almox": "10"})
    assert r.status_code == 409 and "senha de administrador" in r.get_json()["erro"]
    monkeypatch.setitem(G._ATIVAS, "10", ("C-1", None))                  # a gravação de uma contagem começando ali
    r = com_o_fracttal(inv, _pessoa_ms(inv)).post(TODOS, data={"almox": "10"})
    assert r.status_code == 409 and "gravação de contagem" in r.get_json()["erro"]
    assert falso.chamadas == []
