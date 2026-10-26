"""A gravação do inventário no Fracttal, em segundo plano (26/10/2026, Levi; Task 7 do plano do inventário).

O Fracttal grava o saldo absoluto numa SESSÃO do almoxarifado (modo 2: abrir, gravar cada peça, fechar com a referência),
e enquanto ela está aberta o almoxarifado fica travado (nem entrada, nem saída, nem pedido de compra; o ATHN-MTS200 ficou
assim em 26/10, em inventário físico). Os testes provam cada caminho que pode deixar o almoxarifado travado, com o
`EstoqueFalso` e um relógio de mentira: nada vai à rede e nada espera de verdade (a espera de 62 s do 429 é injetada).
O livro do inventário é um arquivo local e a pasta de dados é a do `tmp_path`. Dado de mentira, sem nome de gente."""
import json
import re
import threading
import time
from datetime import timedelta, timezone

import pytest
from estoque_falso import EstoqueFalso
from test_campo_visao import CHAVE, banco  # noqa: F401  (banco é fixture)
from test_pcm_inventario_leitura import AGORA, _linha, inv  # noqa: F401  (inv é fixture)
from test_pcm_inventario_telas import EMAIL, LISTA, _cenario, _estoque, _pcm

from nexus.campo.ligacao_cadastro import codigo_da_pessoa
from nexus.dados import fato_inventario as F
from nexus.dados.fato_almoxarifado import LIGADA_DE_PARA
from nexus.pcm.inventario import contas
from nexus.pcm.inventario import estoque as E
from nexus.pcm.inventario import gravacao as G
from nexus.pcm.inventario import leitura as L

PONTE = "/os/_nexus/inventario"
CONTADA = (AGORA.astimezone(timezone.utc) - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
APROVADOR = {"pessoa_hmac": codigo_da_pessoa(CHAVE, EMAIL), "pessoa_id": 92}
OUTRA = {"pessoa_hmac": codigo_da_pessoa(CHAVE, "outra.pessoa@exemplo.test"), "pessoa_id": None}


class Relogio:
    """O relógio de mentira, o mesmo para o Fracttal falso e para a gravação: anda 1 s a cada leitura (o ritmo de 1
    pedido por segundo), a partir de 26/10/2026 12:00 de Brasília."""

    def __init__(self):
        self.t = AGORA.astimezone(timezone.utc)

    def __call__(self):
        self.t += timedelta(seconds=1)
        return self.t


@pytest.fixture
def grav(app, inv, tmp_path):  # noqa: F811
    """A pasta de dados no tmp_path, as esperas anotadas (nunca dormidas) e o relógio de mentira. Ao fim, nenhuma
    gravação fica viva para o teste seguinte."""
    app.config["NEXUS_DADOS"] = str(tmp_path / "dados")
    ctx = {"esperas": [], "relogio": Relogio(), "cfg": app.config}
    yield ctx
    for t in [t for _, t in list(G._ATIVAS.values()) if t is not None]:
        t.join(10)
    G._ATIVAS.clear()


def _falso(saldos=None, **kw):
    return EstoqueFalso({"10": saldos if saldos is not None else {"501": 10, "502": 5, "503": 4}}, **kw)


def _linhas(contados: dict, cid="C-1"):
    return [_linha(cid, f"L{n}", item, str(qtd), contada=CONTADA) for n, (item, qtd) in enumerate(contados.items(), 1)]


def _contagem(linhas, cid="C-1", almox="10"):
    return {"contagem_id": cid, "id_almox": almox, "almox": "Almoxarifado Altair", "usina_id": 1,
            "usina_ligada_por": LIGADA_DE_PARA, "contada_em": CONTADA, "linhas": linhas}


def _iniciar(grav, falso, contados=None, cid="C-1", almox="10", aprovado=None, curadoria=None, linhas=None,
             aprovador=APROVADOR, esperar=True):
    """Aprova a contagem como a tela faz: o lote das contas com o saldo lido na hora (`aprovado` troca o que o PCM viu),
    e a gravação começa. `esperar`: aguarda a thread terminar."""
    linhas = linhas if linhas is not None else _linhas(contados or {"501": 12, "502": 3, "503": 0}, cid)
    sistema = aprovado if aprovado is not None else falso.ler(almox)
    falso.chamadas.clear()                                 # a numeração do `limite_em` começa na gravação
    itens = contas.itens_do_lote(linhas, sistema, curadoria or {}, {})
    d = G.iniciar(grav["cfg"], _contagem(linhas, cid, almox), itens, falso, aprovador, curadoria=curadoria or {},
                  dormir=grav["esperas"].append, agora=grav["relogio"])
    if esperar:
        G.aguardar(cid)
    return d


def _continuar(grav, falso, cid="C-1", pessoa=APROVADOR, esperar=True):
    d = G.continuar(grav["cfg"], cid, falso, pessoa, dormir=grav["esperas"].append, agora=grav["relogio"])
    if esperar:
        G.aguardar(cid)
    return d


def _eventos(app, tipo=None):
    ev = F.ler(app.config, forcar=True)[F.ABA_EVENTO]
    return [e for e in ev if tipo is None or e["tipo"] == tipo]


def _pares(falso):
    """{id_item: [tipos dos movimentos]} do ajuste (os movimentos que a gravação gerou)."""
    out = {}
    for m in falso.movimentos:
        if m["referencia"].startswith("INVENTARIO-"):
            out.setdefault(m["id_item"], []).append(m["tipo"])
    return out


def _saldos(falso, almox="10"):
    return {i: v["saldo"] for i, v in falso.ler(almox).items()}


# ── o caminho feliz ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_grava_e_confirma(app, grav):
    """Uma sessão por lote: confere o modo, lê o que se moveu e o saldo, confere o modo de novo, abre, lê (a leitura que
    vale), grava cada peça, fecha com a referência e relê. Cada peça vira `peca_gravada` com o folio do fechamento."""
    falso = _falso(agora=grav["relogio"])
    d = _iniciar(grav, falso)
    assert d["estado"] == "gravando" and d["total"] == 3
    assert falso.chamadas == ["modo", "mexidas_desde", "ler", "modo", "abrir_ajuste", "ler", "gravar_saldo", "gravar_saldo",
                              "gravar_saldo", "fechar_ajuste", "voltar_ao_normal", "achar_movimento", "ler"]
    assert _saldos(falso) == {"501": 12, "502": 3, "503": 0} and falso.modo("10") == 0
    assert _pares(falso) == {"501": ["saida", "entrada"], "502": ["saida", "entrada"], "503": ["saida", "entrada"]}
    assert {m["referencia"] for m in falso.movimentos} == {"INVENTARIO-C-1-L1"}
    aprovadas = _eventos(app, "aprovada")
    assert sorted(e["id_item"] for e in aprovadas) == ["501", "502", "503"] and {e["lote"] for e in aprovadas} == {1}
    gravadas = {e["id_item"]: e for e in _eventos(app, "peca_gravada")}
    assert set(gravadas) == {"501", "502", "503"}
    e = gravadas["501"]
    # o folio do movimento achado pela referência depois de fechar (MOV-6, o mais novo), e não o `folio_return` ("7", o
    # próximo número): o mesmo que a retomada acha
    assert e["movimento_fracttal"] == "6"
    assert (float(e["de_qtd"]), float(e["para_qtd"]), e["situacao"], e["lote"]) == (10, 12, "para_cima", 1)
    assert e["pessoa_hmac"] == APROVADOR["pessoa_hmac"] and e["usina_ligada_por"] == LIGADA_DE_PARA
    assert gravadas["503"]["situacao"] == "zerar"
    assert L.estado_dos_eventos(_eventos(app)) == "gravada"
    est = G.estado(app.config, "C-1")
    assert (est["estado"], est["gravadas"], est["conflitos"], est["erros"], est["travado"]) == ("concluida", 3, 0, 0, False)
    assert not list((grav_pasta(app)).glob("trava-*"))   # a vez do almoxarifado foi solta
    assert grav["esperas"] == []


def grav_pasta(app):
    from pathlib import Path
    return Path(app.config["NEXUS_DADOS"]) / "almox_inventario"


def test_lotes_de_50(app, grav):
    """120 peças: três lotes (50, 50, 20), uma sessão cada, cada uma com a sua referência. Entre um lote e outro o
    almoxarifado volta ao normal (o técnico lança peça no intervalo)."""
    saldos = {str(600 + i): 1 for i in range(120)}
    falso = _falso(saldos, agora=grav["relogio"])
    _iniciar(grav, falso, {i: 2 for i in saldos})
    assert falso.chamadas.count("abrir_ajuste") == 3 and falso.chamadas.count("fechar_ajuste") == 3
    refs = [m["referencia"] for m in falso.movimentos]
    assert sorted(set(refs)) == ["INVENTARIO-C-1-L1", "INVENTARIO-C-1-L2", "INVENTARIO-C-1-L3"]
    assert [refs.count(f"INVENTARIO-C-1-L{n}") for n in (1, 2, 3)] == [100, 100, 40]       # um par por peça
    por_lote = {}
    for e in _eventos(app, "aprovada"):
        por_lote[e["lote"]] = por_lote.get(e["lote"], 0) + 1
    assert por_lote == {1: 50, 2: 50, 3: 20}
    assert len(_eventos(app, "peca_gravada")) == 120 and set(_saldos(falso).values()) == {2}
    assert G.estado(app.config, "C-1")["estado"] == "concluida"


def test_ligar_antes_de_abrir(app, grav):
    """A peça nunca ligada ao almoxarifado (não vem na leitura) é ligada ANTES de abrir: ligar com o modo 2 não foi provado
    no Fracttal. Ela entra com o saldo 0 da aprovação e grava o contado."""
    falso = _falso(agora=grav["relogio"])
    _iniciar(grav, falso, {"501": 12, "508": 3})
    ch = falso.chamadas
    assert ch.index("ligar") < ch.index("abrir_ajuste") and ch.count("ligar") == 1
    assert _saldos(falso)["508"] == 3
    assert {e["id_item"] for e in _eventos(app, "peca_gravada")} == {"501", "508"}


# ── os conflitos ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_saldo_mudou_vira_conflito(app, grav):
    """O PCM aprovou a 501 com o saldo 8 e o Fracttal, com o modo aberto, diz 10: não grava, vira `conflito` (com a
    situação e o motivo cifrado) e as outras seguem. A contagem fica "gravada com conflitos"."""
    falso = _falso(agora=grav["relogio"])
    aprovado = dict(falso.ler("10"))
    aprovado["501"] = dict(aprovado["501"], saldo=8.0)
    _iniciar(grav, falso, aprovado=aprovado)
    assert _saldos(falso) == {"501": 10, "502": 3, "503": 0}
    conf = _eventos(app, "conflito")
    assert [e["id_item"] for e in conf] == ["501"]
    assert (conf[0]["situacao"], float(conf[0]["de_qtd"]), float(conf[0]["para_qtd"])) == ("para_cima", 8, 12)
    assert "saldo" in F.decifrar(app.config, F.ABA_EVENTO, conf[0])["motivo"]
    assert {e["id_item"] for e in _eventos(app, "peca_gravada")} == {"502", "503"}
    assert L.estado_dos_eventos(_eventos(app)) == "gravada_com_conflitos"
    assert G.estado(app.config, "C-1")["conflitos"] == 1


def test_mexida_depois_da_contagem_vira_conflito(app, grav):
    """A 502 saiu e voltou depois da contagem (o saldo é o mesmo da aprovação, mas o técnico contou antes da saída): o
    histórico do almoxarifado diz que ela se moveu, e ela não é gravada por cima."""
    falso = _falso(agora=grav["relogio"])
    depois = (AGORA - timedelta(hours=1)).isoformat()
    falso.mover("10", "502", "saida", 2, quando=depois, referencia="Consumo da OS 1")
    falso.mover("10", "502", "entrada", 2, quando=depois, referencia="Devolução da OS 1")
    _iniciar(grav, falso)
    assert [e["id_item"] for e in _eventos(app, "conflito")] == ["502"] and _saldos(falso)["502"] == 5
    assert "moveu" in F.decifrar(app.config, F.ABA_EVENTO, _eventos(app, "conflito")[0])["motivo"]
    assert {e["id_item"] for e in _eventos(app, "peca_gravada")} == {"501", "503"}


def test_especifico_com_generico_pendente_vira_conflito(app, grav):
    """O genérico 507 tem uma linha confirmada como a 501 e outra ainda por identificar: a 501 não se grava (as unidades
    pendentes talvez sejam dela também), vira `conflito` logo na aprovação e espera a curadoria; o resto segue."""
    falso = _falso({"501": 10, "502": 5, "507": 6}, agora=grav["relogio"])
    linhas = [_linha("C-1", "L1", "501", "12", contada=CONTADA), _linha("C-1", "L2", "502", "3", contada=CONTADA),
              _linha("C-1", "L3", "507", "2", tipo="identificar", contada=CONTADA, **{"Identificado como": "501"}),
              _linha("C-1", "L4", "507", "1", tipo="identificar", contada=CONTADA, **{"Identificado como": "502"})]
    curadoria = {"L3": {"decisao": "confirmar", "id_item": "501"}}
    _iniciar(grav, falso, linhas=linhas, curadoria=curadoria)
    assert [e["id_item"] for e in _eventos(app, "conflito")] == ["501"]
    assert "curadoria" in F.decifrar(app.config, F.ABA_EVENTO, _eventos(app, "conflito")[0])["motivo"]
    assert _saldos(falso)["501"] == 10 and _saldos(falso)["502"] == 3
    assert {e["id_item"] for e in _eventos(app, "aprovada")} == {"501", "502"}


# ── o modo do almoxarifado ───────────────────────────────────────────────────────────────────────────────────────────────
def test_modo_3_nao_mexe(app, grav):
    """Em inventário físico (modo 3, o ATHN-MTS200 de 26/10) a gravação para sem mexer: nem liga, nem abre."""
    falso = _falso(agora=grav["relogio"])
    falso.definir_modo("10", 3)
    _iniciar(grav, falso)
    est = G.estado(app.config, "C-1")
    assert est["estado"] == "parada" and "Inventário físico" in est["motivo"] and est["travado"] is False
    assert falso.chamadas == ["modo"] and falso.modo("10") == 3 and _eventos(app, "peca_gravada") == []


def test_ajuste_de_outro_nao_mexe(app, grav):
    """O almoxarifado já em ajuste (modo 2) que o controle não diz que é nosso: outra pessoa ou outra tela. Para sem
    mexer, e nunca o volta ao normal (os saldos gravados por ela ficariam sem o par de movimentos)."""
    falso = _falso(agora=grav["relogio"])
    falso.definir_modo("10", 2)
    _iniciar(grav, falso)
    est = G.estado(app.config, "C-1")
    assert est["estado"] == "parada" and "já está em ajuste" in est["motivo"] and not est["travado"]
    assert falso.chamadas == ["modo"] and falso.modo("10") == 2


def test_ajuste_de_outro_aberto_no_meio_nao_mexe(app, grav):
    """Alguém abriu o ajuste no Fracttal entre a 1ª conferência e a abertura: a 2ª conferência, logo antes de abrir, o vê,
    e a gravação não escreve na sessão dos outros."""
    falso = _falso(agora=grav["relogio"])
    aprovado = falso.ler("10")
    ler = falso.ler

    def ler_e_alguem_abre(id_almox):
        r = ler(id_almox)
        falso.definir_modo("10", 2)
        return r
    falso.ler = ler_e_alguem_abre
    _iniciar(grav, falso, aprovado=aprovado)
    assert G.estado(app.config, "C-1")["estado"] == "parada"
    assert falso.chamadas == ["modo", "mexidas_desde", "ler", "modo"] and falso.modo("10") == 2


# ── as respostas que se perdem e o fechamento em dois passos ─────────────────────────────────────────────────────────────
def test_finalizar_perdido_nao_finaliza_duas_vezes(app, grav):
    """O finalizar valeu (os movimentos existem) e a resposta se perdeu: o almoxarifado ficou em modo 2. A gravação
    procura o fechamento pela referência antes de repetir: achou, só volta ao normal. Registra o erro (o tipo, nunca o
    texto) e para; o "Continuar" confere e termina. Um par de movimentos por peça e o almoxarifado em modo 0."""
    falso = _falso(perder_resposta={"finalizar"}, agora=grav["relogio"])
    _iniciar(grav, falso)
    est = G.estado(app.config, "C-1")
    assert est["estado"] == "parada" and "ConnectionError" in est["motivo"] and not est["travado"]
    assert falso.modo("10") == 0 and falso.chamadas.count("fechar_ajuste") == 1
    assert grav["esperas"] == [62]                       # esperou antes de procurar: o histórico pode ainda não mostrar
    erro = _eventos(app, "erro")
    assert len(erro) == 1 and F.decifrar(app.config, F.ABA_EVENTO, erro[0])["motivo"].endswith("ConnectionError")
    _continuar(grav, falso)
    assert G.estado(app.config, "C-1")["estado"] == "concluida"
    assert falso.chamadas.count("fechar_ajuste") == 1                     # nunca um 2º finalizar
    assert _pares(falso) == {i: ["saida", "entrada"] for i in ("501", "502", "503")}
    assert falso.modo("10") == 0 and {e["id_item"] for e in _eventos(app, "peca_gravada")} == {"501", "502", "503"}


def test_modo_0_pendente_so_volta_ao_normal(app, grav):
    """O fechamento valeu e o 2º pedido (o modo 0) levou 429: espera 62 s, acha o fechamento pela referência e só volta ao
    normal (nunca um 2º finalizar), e segue."""
    falso = _falso(limite_em=11, agora=grav["relogio"])      # a 11ª chamada é o voltar_ao_normal de dentro do fechar
    _iniciar(grav, falso)
    assert grav["esperas"] == [62]
    assert falso.chamadas.count("fechar_ajuste") == 1 and falso.chamadas.count("voltar_ao_normal") == 2
    assert "achar_movimento" in falso.chamadas and falso.modo("10") == 0
    assert G.estado(app.config, "C-1")["estado"] == "concluida"
    assert _pares(falso) == {i: ["saida", "entrada"] for i in ("501", "502", "503")}


def test_modo_0_pendente_retomado_por_outro_login(app, grav):
    """O login morreu justo no modo 0: o almoxarifado ficou em "fechamento feito, modo 0 pendente", travado. A tela avisa
    forte; quem aprovou entra de novo e o "Continuar" só volta ao normal."""
    falso = _falso(expirar_em=11, agora=grav["relogio"])
    _iniciar(grav, falso)
    est = G.estado(app.config, "C-1")
    assert est["estado"] == "parada" and "login do Fracttal expirou" in est["motivo"]
    assert est["travado"] and "ficou travado em ajuste" in est["aviso"] and falso._modos["10"] == 2     # o modo 0 ficou pendente
    falso._expira_em = None                                  # quem aprovou entrou de novo (o login novo)
    _continuar(grav, falso)
    assert falso.chamadas.count("fechar_ajuste") == 1 and falso.modo("10") == 0
    assert G.estado(app.config, "C-1")["estado"] == "concluida"
    assert _pares(falso) == {i: ["saida", "entrada"] for i in ("501", "502", "503")}


def test_sessao_sem_escrita_nunca_finaliza_duas_vezes(app, grav):
    """Tudo deu conflito (nada se gravou na sessão) e o modo 0 levou 429 duas vezes: sem movimento com a referência não
    há como saber se o finalizar valeu, e um 2º finalizar seria erro no Fracttal. Sem nada gravado, só volta ao normal."""
    falso = _falso(limite_em=[8, 9], agora=grav["relogio"])   # 8: o modo 0 de dentro do fechar; 9: o modo da retomada
    aprovado = {i: dict(v, saldo=1.0) for i, v in falso.ler("10").items()}   # o saldo de todas mudou
    _iniciar(grav, falso, aprovado=aprovado)
    assert grav["esperas"] == [62, 62] and "achar_movimento" not in falso.chamadas
    assert falso.chamadas.count("fechar_ajuste") == 1 and falso.modo("10") == 0
    assert G.estado(app.config, "C-1")["estado"] == "concluida"
    assert len(_eventos(app, "conflito")) == 3 and falso.movimentos == []


# ── o 429 e o login que expira ───────────────────────────────────────────────────────────────────────────────────────────
def test_limite_espera_e_tenta_uma_vez(app, grav):
    falso = _falso(limite_em=8, agora=grav["relogio"])        # a 8ª chamada é a gravação da 2ª peça
    _iniciar(grav, falso)
    assert grav["esperas"] == [62] and G.estado(app.config, "C-1")["estado"] == "concluida"


def test_limite_fecha_antes_de_parar(app, grav):
    """429 de novo depois da espera: antes de parar, espera mais 62 s e fecha a sessão com o que já gravou (o almoxarifado
    não fica travado). Para como "limite do Fracttal"; o "Continuar" grava o resto numa sessão nova, com outra
    referência (a do 1º fechamento já está no histórico)."""
    falso = _falso(limite_em=[8, 9], agora=grav["relogio"])
    _iniciar(grav, falso)
    est = G.estado(app.config, "C-1")
    assert est["estado"] == "parada" and "limite do Fracttal" in est["motivo"] and not est["travado"] and not est["aviso"]
    assert grav["esperas"] == [62, 62] and falso.modo("10") == 0
    assert _pares(falso) == {"501": ["saida", "entrada"]} and _saldos(falso) == {"501": 12, "502": 5, "503": 4}
    _continuar(grav, falso)
    assert G.estado(app.config, "C-1")["estado"] == "concluida"
    assert _saldos(falso) == {"501": 12, "502": 3, "503": 0}
    assert _pares(falso) == {i: ["saida", "entrada"] for i in ("501", "502", "503")}
    assert {m["referencia"] for m in falso.movimentos} == {"INVENTARIO-C-1-L1", "INVENTARIO-C-1-L1-S2"}
    assert {e["id_item"] for e in _eventos(app, "peca_gravada")} == {"501", "502", "503"}
    assert len(_eventos(app, "peca_gravada")) == 3                        # a 501 não é registrada duas vezes


def test_limite_que_nao_deixa_fechar_avisa_que_ficou_travado(app, grav):
    """Nem o fechamento passou (o login morreu no meio): a gravação para com o aviso forte, e o almoxarifado espera quem
    aprovou continuar."""
    falso = _falso(limite_em=[8, 9], expirar_em=10, agora=grav["relogio"])
    _iniciar(grav, falso)
    est = G.estado(app.config, "C-1")
    assert est["estado"] == "parada" and "limite do Fracttal" in est["motivo"] and est["travado"]
    assert "Almoxarifado Altair ficou travado em ajuste no Fracttal; quem aprovou precisa continuar para destravar" in est["aviso"]
    falso._expira_em = None
    _continuar(grav, falso)
    assert falso.modo("10") == 0 and G.estado(app.config, "C-1")["estado"] == "concluida"
    assert _pares(falso) == {i: ["saida", "entrada"] for i in ("501", "502", "503")}


def test_login_expirado_para_com_aviso_de_travado(app, grav):
    """O login do Fracttal expira no meio do lote (o foco 4 do plano): não dá para fechar sem login. Para como "o login do
    Fracttal expirou", com o aviso forte (a sessão ficou aberta); quem aprovou entra de novo e o "Continuar" regrava o que
    faltava (absoluto: a peça sem resposta não duplica) e fecha."""
    falso = _falso(expirar_em=8, agora=grav["relogio"])
    _iniciar(grav, falso)
    est = G.estado(app.config, "C-1")
    assert est["estado"] == "parada" and est["motivo"] == "o login do Fracttal expirou" and est["travado"]
    assert est["aviso"] and falso._modos["10"] == 2
    falso._expira_em = None
    _continuar(grav, falso)
    assert falso.modo("10") == 0 and G.estado(app.config, "C-1")["estado"] == "concluida"
    assert _saldos(falso) == {"501": 12, "502": 3, "503": 0}
    assert _pares(falso) == {i: ["saida", "entrada"] for i in ("501", "502", "503")}
    assert falso.chamadas.count("fechar_ajuste") == 1


def test_resposta_perdida_na_gravacao_da_peca_nao_duplica(app, grav):
    """A gravação do saldo valeu e a resposta se perdeu: a sessão é fechada com o que já valeu, a peça "sem resposta" é
    conferida pela releitura (gravou: só confirma), e o "Continuar" não a grava de novo."""
    falso = _falso(perder_resposta={"gravar_saldo"}, agora=grav["relogio"])
    _iniciar(grav, falso)
    assert G.estado(app.config, "C-1")["estado"] == "parada" and falso.modo("10") == 0
    _continuar(grav, falso)
    assert G.estado(app.config, "C-1")["estado"] == "concluida"
    assert _pares(falso) == {i: ["saida", "entrada"] for i in ("501", "502", "503")}
    assert _saldos(falso) == {"501": 12, "502": 3, "503": 0}


def test_releitura_que_nao_bate_vira_erro_e_o_continuar_decide(app, grav):
    """A releitura depois de fechar não bateu (alguém lançou a peça no segundo em que o almoxarifado voltou ao normal): a
    peça vira `erro`, e a gravação para pedindo a conferência. O "Continuar" relê sem gravar nada: ainda não bate, vira
    `conflito` (o PCM olha)."""
    falso = _falso(agora=grav["relogio"])
    fechar = falso.fechar_ajuste

    def fechar_e_alguem_lanca(id_almox, referencia):
        folio = fechar(id_almox, referencia)
        falso.mover("10", "502", "saida", 1)
        return folio
    falso.fechar_ajuste = fechar_e_alguem_lanca
    _iniciar(grav, falso)
    est = G.estado(app.config, "C-1")
    assert est["estado"] == "parada" and est["erros"] == 1 and "releitura" in est["motivo"]
    assert [e["id_item"] for e in _eventos(app, "erro")] == ["502"]
    falso.fechar_ajuste = fechar
    _continuar(grav, falso)
    assert G.estado(app.config, "C-1")["estado"] == "concluida"
    assert [e["id_item"] for e in _eventos(app, "conflito")] == ["502"] and falso.chamadas[13:] == ["ler"]   # só relê
    assert L.estado_dos_eventos(_eventos(app)) == "gravada_com_conflitos"


def test_o_livro_que_falha_depois_de_gravar_nao_duplica_a_auditoria(app, grav, monkeypatch):
    """O banco gravou os eventos e a resposta se perdeu: a gravação para dizendo que não registrou (o almoxarifado já está
    normal: o registro é sempre depois de fechar), e o "Continuar" registra de novo SEM duplicar (o `evento_id` sai da
    contagem, do tipo e da peça). Nada vai ao Fracttal de novo."""
    falso = _falso(agora=grav["relogio"])
    acrescentar, vezes = F.acrescentar, []

    def gravou_e_caiu(cfg, aba, linhas):
        acrescentar(cfg, aba, linhas)
        vezes.append(len(linhas))
        if len(vezes) == 2:                                  # a 1ª é a aprovação; a 2ª, as peças gravadas
            raise ConnectionError("a resposta do banco se perdeu (de mentira)")
    monkeypatch.setattr(F, "acrescentar", gravou_e_caiu)
    _iniciar(grav, falso)
    est = G.estado(app.config, "C-1")
    assert est["estado"] == "parada" and "livro do inventário" in est["motivo"] and not est["travado"]
    assert falso.modo("10") == 0 and len(_eventos(app, "peca_gravada")) == 3
    n = len(falso.chamadas)
    _continuar(grav, falso)
    assert G.estado(app.config, "C-1")["estado"] == "concluida"
    assert len(_eventos(app, "peca_gravada")) == 3 and len(_eventos(app, "aprovada")) == 3
    assert falso.chamadas[n:] == []                          # o Fracttal nem foi chamado: só faltava o registro


def test_o_disco_que_falha_nao_deixa_o_almoxarifado_travado(app, grav, monkeypatch):
    """O controle não grava no meio da sessão (disco cheio): a gravação para, mas antes fecha a sessão no Fracttal mesmo sem
    conseguir anotar; o almoxarifado nunca fica travado por causa do disco do Nexus."""
    falso = _falso(agora=grav["relogio"])
    gravar_json, vezes = G._gravar_json, []

    def disco_cheio(p, d):
        if any(it["estado"] == "escrita" for it in d.get("itens", {}).values()):
            vezes.append(1)
            raise OSError("disco cheio (de mentira)")
        gravar_json(p, d)
    monkeypatch.setattr(G, "_gravar_json", disco_cheio)
    _iniciar(grav, falso)
    assert vezes and falso.modo("10") == 0 and falso.chamadas.count("fechar_ajuste") == 1


def test_a_gravacao_nao_conta_as_proprias_sessoes_como_mexidas(app, grav):
    """O que se moveu depois da contagem é lido sem as sessões da própria contagem (`INVENTARIO-<contagem>-`): o movimento
    que o Nexus fez num lote (ou numa sessão anterior do mesmo lote) não é conflito."""
    falso = _falso(agora=grav["relogio"])
    pedidos, mexidas = [], falso.mexidas_desde

    def anotar(*args):
        pedidos.append(args)
        return mexidas(*args)
    falso.mexidas_desde = anotar
    _iniciar(grav, falso)
    assert pedidos == [("10", CONTADA, None, "INVENTARIO-C-1-")]


def test_o_adaptador_e_o_falso_ignoram_o_prefixo():
    """`mexidas_desde(..., ignorar_prefixo=...)`: o de verdade (pelo histórico do passo 0) e o falso tiram os movimentos cuja
    referência começa pelo prefixo; a referência exata segue como era."""
    from test_pcm_inventario_estoque import ALMOX, HIST, HISTORICO, ITEM, Fracttal, em_paginas, estoque
    est = estoque(Fracttal({HISTORICO: em_paginas(HIST)}), pagina=2)
    assert est.mexidas_desde(ALMOX, "2026-10-26T13:00:00Z") == {ITEM, "53248313", "53248314"}
    assert est.mexidas_desde(ALMOX, "2026-10-26T13:00:00Z", ignorar_prefixo="INVENTARIO-") == {"53248313", "53248314"}
    assert est.mexidas_desde(ALMOX, "2026-10-26T13:00:00Z", None, "Consumo") == {ITEM, "53248314"}
    falso = EstoqueFalso({"10": {"501": 1, "502": 1}})
    falso.mover("10", "501", "entrada", 1, quando="2026-10-26T14:00:00Z", referencia="INVENTARIO-C-1-L1")
    falso.mover("10", "502", "entrada", 1, quando="2026-10-26T14:00:00Z", referencia="Compra 9")
    assert falso.mexidas_desde("10", "2026-10-26T13:00:00Z") == {"501", "502"}
    assert falso.mexidas_desde("10", "2026-10-26T13:00:00Z", ignorar_prefixo="INVENTARIO-C-1-") == {"502"}


def test_retomada_com_movimento_de_outro_nao_finaliza_a_sessao_dos_outros(app, grav):
    """A nossa sessão ficou aberta (o login expirou); alguém a finalizou no Fracttal e abriu outra. O controle velho diz
    "aberto", e o modo é 2: o histórico desde que a nossa abriu tem movimento sem a nossa referência, então a sessão saiu
    das nossas mãos. Para sem gravar nem finalizar."""
    falso = _falso(expirar_em=8, agora=grav["relogio"])
    _iniciar(grav, falso)
    falso._expira_em = None
    falso.fechar_ajuste("10", "Ajuste feito na tela do Fracttal")      # outra pessoa finaliza a nossa sessão...
    falso.abrir_ajuste("10")                                          # ...e abre a dela
    n = len(falso.chamadas)
    _continuar(grav, falso)
    est = G.estado(app.config, "C-1")
    assert est["estado"] == "parada" and "ajuste por outra pessoa ou outra tela" in est["motivo"]
    assert falso.chamadas[n:] == ["modo", "mexidas_desde"] and falso.modo("10") == 2


def test_retomada_com_modo_2_procura_antes_de_finalizar(app, grav):
    """A falha dupla: o finalizar valeu, o modo 0 falhou, e o controle não soube que o lote estava "fechando" (o disco que
    falhou enquanto parava). A retomada com o modo 2 procura o fechamento pela referência antes de gravar mais ou de
    finalizar de novo: achou, só volta ao normal."""
    falso = _falso(expirar_em=11, agora=grav["relogio"])     # o login morre no modo 0 de dentro do fechar
    _iniciar(grav, falso)
    caminho = next(grav_pasta(app).glob("C-1*.json"))
    ctrl = json.loads(caminho.read_text("utf-8"))
    assert ctrl["lotes"][0]["estado"] == "fechando"
    ctrl["lotes"][0]["estado"] = "aberto"                    # o "fechando" que o disco engoliu
    caminho.write_text(json.dumps(ctrl), "utf-8")
    falso._expira_em = None
    _continuar(grav, falso)
    assert G.estado(app.config, "C-1")["estado"] == "concluida"
    assert falso.chamadas.count("fechar_ajuste") == 1 and falso.modo("10") == 0
    assert _pares(falso) == {i: ["saida", "entrada"] for i in ("501", "502", "503")}


def test_confirmar_sem_alvo_e_pendente_e_segura_o_especifico(app, grav):
    """Como as contas (`contas._ler`): o "confirmar" sem alvo (nem na decisão, nem no "Identificado como") é linha pendente,
    e o específico que recebeu a outra linha confirmada do mesmo genérico espera a curadoria."""
    falso = _falso({"501": 10, "502": 5, "507": 6}, agora=grav["relogio"])
    linhas = [_linha("C-1", "L1", "501", "12", contada=CONTADA), _linha("C-1", "L2", "502", "3", contada=CONTADA),
              _linha("C-1", "L3", "507", "2", tipo="identificar", contada=CONTADA, **{"Identificado como": "501"}),
              _linha("C-1", "L4", "507", "1", tipo="identificar", contada=CONTADA)]
    curadoria = {"L3": {"decisao": "confirmar", "id_item": "501"}, "L4": {"decisao": "confirmar", "id_item": ""}}
    _iniciar(grav, falso, linhas=linhas, curadoria=curadoria)
    assert [e["id_item"] for e in _eventos(app, "conflito")] == ["501"] and _saldos(falso)["501"] == 10


# ── encerrar (Levi, 26/10/2026) ──────────────────────────────────────────────────────────────────────────────────────────
def _encerrar(grav, falso, pessoa=APROVADOR, motivo="o almoxarifado vai ser recontado", admin=False, horas=0.0):
    agora = (lambda: grav["relogio"].t + timedelta(hours=horas)) if horas else grav["relogio"]
    return G.encerrar(grav["cfg"], "C-1", falso, pessoa, motivo, admin=admin, agora=agora)


def test_encerrar_quem_aprovou(app, grav):
    """Quem aprovou encerra a gravação parada (a qualquer hora), com o motivo e o almoxarifado fora do modo 2: as peças já
    conferidas ficam `peca_gravada`, a que faltava vira `conflito` com o motivo (só cifrado), a contagem sai de "gravando",
    e a vez do almoxarifado é solta (outra contagem grava)."""
    falso = _falso(agora=grav["relogio"])
    fechar = falso.fechar_ajuste

    def fechar_e_alguem_lanca(id_almox, referencia):
        folio = fechar(id_almox, referencia)
        falso.mover("10", "502", "saida", 1)
        return folio
    falso.fechar_ajuste = fechar_e_alguem_lanca
    _iniciar(grav, falso)                                     # a 502 não bate na releitura: parada
    assert G.estado(app.config, "C-1")["estado"] == "parada"
    with pytest.raises(F.Recusada, match="motivo"):
        _encerrar(grav, falso, motivo="   ")
    with pytest.raises(G.Recusada, match="Só quem aprovou"):
        _encerrar(grav, falso, pessoa=OUTRA)
    est = _encerrar(grav, falso)
    assert est["estado"] == "encerrada" and est["gravadas"] == 2 and est["conflitos"] == 1 and not est["travado"]
    conf = _eventos(app, "conflito")
    assert [e["id_item"] for e in conf] == ["502"] and conf[0]["pessoa_hmac"] == APROVADOR["pessoa_hmac"]
    assert "o almoxarifado vai ser recontado" in F.decifrar(app.config, F.ABA_EVENTO, conf[0])["motivo"]
    assert {e["id_item"] for e in _eventos(app, "peca_gravada")} == {"501", "503"}
    assert L.estado_dos_eventos(_eventos(app)) == "gravada_com_conflitos"
    controle = next(grav_pasta(app).glob("C-1*.json")).read_text("utf-8")
    assert "recontado" not in controle and not list(grav_pasta(app).glob("trava-*"))
    with pytest.raises(F.Recusada):
        _continuar(grav, falso)                               # encerrada não volta
    _iniciar(grav, _falso({"501": 12, "502": 2, "503": 0}), {"501": 1}, cid="C-2")
    assert G.estado(app.config, "C-2")["estado"] == "concluida"


def test_encerrar_administrador_so_depois_de_24h(app, grav):
    """O administrador do Nexus encerra a gravação parada de outra pessoa só depois de 24 h parada; o conflito fica no nome
    dele."""
    falso = _falso(agora=grav["relogio"])
    falso.definir_modo("10", 3)
    _iniciar(grav, falso)                                     # parada sem mexer: nada gravado
    with pytest.raises(G.Recusada, match="24 h") as erro:
        _encerrar(grav, falso, pessoa=OUTRA, admin=True, horas=23)
    assert erro.value.status == 403
    assert not G.pode_encerrar(app.config, "C-1", OUTRA, admin=True, agora=lambda: grav["relogio"].t)
    assert G.pode_encerrar(app.config, "C-1", OUTRA, admin=True, agora=lambda: grav["relogio"].t + timedelta(hours=25))
    est = _encerrar(grav, falso, pessoa=OUTRA, admin=True, horas=25)
    assert est["estado"] == "encerrada" and est["conflitos"] == 3 and est["gravadas"] == 0
    assert {e["pessoa_hmac"] for e in _eventos(app, "conflito")} == {OUTRA["pessoa_hmac"]}
    assert falso.modo("10") == 3                              # o modo 3 é de outra pessoa: encerrar não mexe nele


def test_encerrar_com_o_almoxarifado_em_modo_2_e_recusado(app, grav):
    """A sessão ficou aberta (o login expirou): encerrar agora largaria o almoxarifado travado sem dono. Recusado, e nada
    muda; quem aprovou continua (ou fecha o ajuste no Fracttal) antes."""
    falso = _falso(expirar_em=8, agora=grav["relogio"])
    _iniciar(grav, falso)
    falso._expira_em = None
    antes = len(_eventos(app))
    with pytest.raises(G.Recusada, match="modo 2") as erro:
        _encerrar(grav, falso)
    assert erro.value.status == 409 and len(_eventos(app)) == antes
    assert G.estado(app.config, "C-1")["estado"] == "parada" and list(grav_pasta(app).glob("trava-*"))


# ── quem continua e a vez do almoxarifado ────────────────────────────────────────────────────────────────────────────────
def test_so_quem_aprovou_continua(app, grav):
    falso = _falso(agora=grav["relogio"])
    falso.definir_modo("10", 3)
    _iniciar(grav, falso)
    with pytest.raises(G.SoQuemAprovou, match="só quem aprovou continua"):
        _continuar(grav, falso, pessoa=OUTRA)
    with pytest.raises(F.Recusada):
        _continuar(grav, falso, pessoa={"pessoa_hmac": None})         # a senha de administrador: não é uma pessoa
    assert G.e_o_aprovador(app.config, "C-1", {"email": EMAIL})
    assert not G.e_o_aprovador(app.config, "C-1", {"email": "outra.pessoa@exemplo.test"})
    falso.definir_modo("10", 0)
    _continuar(grav, falso)                                              # o aprovador, pelo HMAC (nunca o e-mail guardado)
    assert G.estado(app.config, "C-1")["estado"] == "concluida"


class Lento(EstoqueFalso):
    """O Fracttal que segura a gravação no 1º pedido até o teste soltar: a gravação fica "andando"."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.entrou, self.solta = threading.Event(), threading.Event()

    def modo(self, id_almox):
        self.entrou.set()
        self.solta.wait(10)
        return super().modo(id_almox)


def test_duas_gravacoes_no_mesmo_almoxarifado(app, grav):
    """Duas pessoas (ou duas contagens) no mesmo almoxarifado: a 2ª é recusada enquanto a 1ª anda (o foco 1 do plano), e
    também depois de o Nexus reiniciar com a 1ª parada no meio (o arquivo da vez segura a reinicialização)."""
    falso = Lento({"10": {"501": 10, "502": 5, "503": 4}}, agora=grav["relogio"])
    _iniciar(grav, falso, esperar=False)
    assert falso.entrou.wait(5)
    with pytest.raises(F.Recusada, match="já tem uma gravação em andamento neste almoxarifado"):
        _iniciar(grav, _falso(), cid="C-2", aprovador=OUTRA)
    with pytest.raises(F.Recusada):
        _iniciar(grav, _falso(), cid="C-1")                            # a mesma contagem, de novo
    with pytest.raises(F.Recusada, match="já está andando"):
        _continuar(grav, falso, esperar=False)
    falso.solta.set()
    G.aguardar("C-1")
    assert G.estado(app.config, "C-1")["estado"] == "concluida"
    assert {e["contagem_id"] for e in _eventos(app, "aprovada")} == {"C-1"}
    # a 2ª contagem agora passa; e parada no meio (modo 3) segura o almoxarifado mesmo depois de o Nexus reiniciar
    outro = _falso({"501": 12, "502": 3, "503": 0}, agora=grav["relogio"])
    outro.definir_modo("10", 3)
    _iniciar(grav, outro, {"501": 1}, cid="C-2")
    assert G.estado(app.config, "C-2")["estado"] == "parada"
    G._ATIVAS.clear()                                                     # o Nexus reiniciou
    with pytest.raises(F.Recusada, match="já tem uma gravação em andamento neste almoxarifado"):
        _iniciar(grav, _falso(), {"501": 2}, cid="C-3")


def test_reiniciou_no_meio_aparece_parada(app, grav):
    """O controle diz "gravando" e não há gravação viva neste processo (o Nexus reiniciou): a tela vê "parada", com o aviso
    forte se a sessão ficou aberta, e quem aprovou continua."""
    falso = _falso(expirar_em=8, agora=grav["relogio"])
    _iniciar(grav, falso)
    caminho = next(grav_pasta(app).glob("C-1*.json"))
    ctrl = json.loads(caminho.read_text("utf-8"))
    ctrl.update(estado="gravando", motivo="")
    caminho.write_text(json.dumps(ctrl), "utf-8")
    est = G.estado(app.config, "C-1")
    assert est["estado"] == "parada" and "reiniciou" in est["motivo"] and est["travado"]


def test_nunca_guarda_o_login(app, grav):
    """O controle e o arquivo da vez nunca têm o login: nem o JWT, nem o token, nem o e-mail de quem aprovou. O livro do
    inventário também não (a pessoa vai como HMAC)."""
    class ComLogin(EstoqueFalso):
        jwt, token, email = "eyJ.segredo.jwt", "token-secreto", "aprovador@exemplo.test"
    falso = ComLogin({"10": {"501": 10, "502": 5, "503": 4}}, expirar_em=8, agora=grav["relogio"])
    _iniciar(grav, falso, aprovador=dict(APROVADOR, email=EMAIL))
    arquivos = list(grav_pasta(app).iterdir())
    assert arquivos
    for p in arquivos:
        texto = p.read_text("utf-8").lower()
        for proibido in ("jwt", "token", "eyj", "@", "segredo", "supervisora", "exemplo.test"):
            assert proibido not in texto, (p.name, proibido)
    livro = (grav_pasta(app).parent.parent / "inventario.json").read_text("utf-8")
    assert "@" not in livro and "eyJ" not in livro


def test_contagem_vazia_ou_sem_pessoa_e_recusada(app, grav):
    falso = _falso(agora=grav["relogio"])
    with pytest.raises(F.Recusada, match="Nada a gravar"):
        _iniciar(grav, falso, {"501": 10})                                # sem alteração: nada mexe
    with pytest.raises(F.Recusada):
        _iniciar(grav, falso, aprovador={"pessoa_hmac": None})
    assert _eventos(app) == [] and falso.chamadas == []


# ── as telas e a ponte do Fracttal ───────────────────────────────────────────────────────────────────────────────────────
def _cookie_os(app, cliente, jwt="x.eyJ.y", email=EMAIL):
    """O cookie `os_sessao` do OS Creator como o login do Nexus pelo Fracttal o grava: no caminho /os, que o navegador só
    manda para /os/... `email`: a conta do Fracttal (a ponte confere que é a da sessão do Nexus)."""
    from nexus.torres.oscreator import ponte
    clone = ponte.clone(app)
    valor = clone.session_interface.get_signing_serializer(clone).dumps(
        {"jwt": jwt, "conta": {"email": email, "nome": "Pessoa"}})
    cliente.set_cookie("os_sessao", valor, path="/os")


@pytest.fixture
def ponte_falsa(app, grav, monkeypatch):
    """O `estoque_da_sessao` DE VERDADE (ele lê o cookie do pedido), com o Fracttal de mentira por baixo: só a montagem da
    instância com o login (`_estoque_do_clone`) é trocada, e anota o JWT que recebeu. A gravação não espera de verdade."""
    falso = _estoque(agora=grav["relogio"])
    montados = []

    def montar(app_, jwt, email, **kw):
        montados.append(jwt)
        return falso
    monkeypatch.setattr(E, "_estoque_do_clone", montar)
    monkeypatch.setattr(G, "_dormir", grav["esperas"].append)
    return {"falso": falso, "montados": montados}


def _visto(app, falso, contagem="C-1"):
    """O que a tela mostrou do lote (o N e a assinatura), como a página o calcula: as contas com o saldo lido agora."""
    c = next(x for x in L.contagens(app.config) if x["contagem_id"] == contagem)
    itens = contas.itens_do_lote(c["linhas"], falso.ler(c["id_almox"]), L.curadoria_da(app.config, contagem),
                                 L.revisao_da(app.config, contagem))
    falso.chamadas.clear()                                    # a numeração do `expirar_em` começa no gravar
    return {"n": sum(1 for i in itens if i["id_item"] and not i["tirada"] and i["situacao"] in contas.MEXEM),
            "assinatura": G.assinatura(itens)}


def test_o_login_do_fracttal_so_chega_na_ponte(app, inv, ponte_falsa, monkeypatch):  # noqa: F811
    """O cookie do Fracttal (`os_sessao`) vale só em /os: numa rota /t/pcm/... o `estoque_da_sessao` de verdade não vê o
    login (SemLogin), e na ponte /os/_nexus/inventario/... vê. É por isso que gravar e continuar moram na ponte."""
    _cenario(inv)
    c = _pcm(app, monkeypatch)
    _cookie_os(app, c)
    visto = _visto(app, ponte_falsa["falso"])
    with c:
        c.get(f"{LISTA}/C-1/estado.json")
        with pytest.raises(E.SemLogin):
            E.estoque_da_sessao(app)
    with c:
        r = c.post(f"{PONTE}/C-1/gravar", json=visto)
        assert isinstance(E.estoque_da_sessao(app), EstoqueFalso)
    assert r.status_code == 200 and r.get_json()["ok"] is True, r.get_json()
    assert ponte_falsa["montados"][0] == "x.eyJ.y"
    G.aguardar("C-1")
    assert G.estado(app.config, "C-1")["estado"] == "concluida"


def test_gravar_pela_tela(app, inv, ponte_falsa, monkeypatch):  # noqa: F811
    """A tela: o botão "Gravar 5 alterações" liga, com o N e a assinatura do lote que ela mostra, e chama a ponte; o
    progresso vem do estado.json (a cada 3 s); ao fim a contagem fica "gravada" pelo livro, e o botão some. O botão vem no
    pedaço do lote que a ponte desenha (o Sistema lido com o login do cookie, que só chega em /os), não na página."""
    _cenario(inv)
    c = _pcm(app, monkeypatch)
    _cookie_os(app, c)
    visto = _visto(app, ponte_falsa["falso"])
    pagina = c.get(f"{LISTA}/C-1").get_data(as_text=True)
    assert "data-gravar=" not in pagina and f'data-url="{PONTE}/C-1/lote"' in pagina
    assert "estado.json" not in pagina                                   # sem gravação, sem o bloco do progresso
    html = c.get(f"{PONTE}/C-1/lote").get_data(as_text=True)              # o `estoque_da_sessao` de verdade, pelo cookie
    assert re.search(r'<button[^>]*\bdata-gravar="/os/_nexus/inventario/C-1/gravar"[^>]*>\s*Gravar 5 alterações', html)
    assert 'data-n="5"' in html and f'data-assinatura="{visto["assinatura"]}"' in html and visto["n"] == 5
    assert ponte_falsa["montados"] == ["x.eyJ.y"]
    assert c.get(f"{LISTA}/C-1/estado.json").status_code == 404
    r = c.post(f"{PONTE}/C-1/gravar", json=visto)
    assert r.status_code == 200, r.get_json()
    G.aguardar("C-1")
    j = c.get(f"{LISTA}/C-1/estado.json").get_json()
    assert j["estado"] == "concluida" and j["total"] == 5 and j["gravadas"] == 5 and j["pode_continuar"] is False
    assert j["texto"] and j["pode_encerrar"] is False
    html = c.get(f"{LISTA}/C-1").get_data(as_text=True)
    assert "Gravação no Fracttal" in html and "data-gravar=" not in html and 'data-estado="/t/pcm/pecas/inventario/C-1/estado.json"' in html
    assert ponte_falsa["falso"].ler("10")["508"]["saldo"] == 3            # a nunca ligada foi ligada e gravada
    assert L.contagens(app.config)[0]["estado"] == "gravada"


def test_gravar_pela_ponte_recusa(app, inv, ponte_falsa, monkeypatch):  # noqa: F811
    """Outro setor: 403. Outro site: 403. A senha de administrador (não é uma pessoa): 409. Sem o login do Fracttal: 401
    com o link do login. A conta do Fracttal de outra pessoa: 409. Sem o N ou a assinatura: 400. O lote mudou desde que a
    tela abriu (o N, ou um saldo que mudou sem mudar o N): 409, e nada é gravado."""
    _cenario(inv)
    falso = ponte_falsa["falso"]
    visto = _visto(app, falso)
    outro = _pcm(app, monkeypatch, setor="Performance")
    _cookie_os(app, outro)
    assert outro.post(f"{PONTE}/C-1/gravar", json=visto).status_code == 403
    c = _pcm(app, monkeypatch)
    _cookie_os(app, c)
    assert c.post(f"{PONTE}/C-1/gravar", json=visto, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    admin = app.test_client()
    with admin.session_transaction() as s:
        s["logado"], s["admin"] = True, True
    r = admin.post(f"{PONTE}/C-1/gravar", json=visto)
    assert r.status_code == 409 and "Fracttal" in r.get_json()["erro"]
    # quem entrou pela conta Microsoft e não tem o login do Fracttal: 401 com o link do login, e a volta para a contagem
    sem = _pcm(app, monkeypatch)
    with sem.session_transaction() as s:
        s["via"], s["ms_ate"] = "microsoft", time.time() + 3600
    r = sem.post(f"{PONTE}/C-1/gravar", json=visto)
    assert r.status_code == 401 and "entre pelo Fracttal" in r.get_json()["erro"]
    assert r.get_json()["login"].startswith("/os/login?next=") and "inventario%2FC-1" in r.get_json()["login"]
    # quem entrou pelo Fracttal e já não tem o cookie dele: o portão encerra a sessão do Nexus junto, antes da ponte
    caiu = _pcm(app, monkeypatch, via="fracttal")      # o `_pcm` das telas nasce da Microsoft desde a ponte do lote
    r = caiu.post(f"{PONTE}/C-1/gravar", json=visto)
    assert r.status_code == 401 and r.get_json().get("sessao_encerrada") is True
    # o cookie do Fracttal de outra conta no mesmo navegador: a gravação iria no nome de um e no login de outro
    trocada = _pcm(app, monkeypatch)
    _cookie_os(app, trocada, email="outra.pessoa@exemplo.test")
    r = trocada.post(f"{PONTE}/C-1/gravar", json=visto)
    assert r.status_code == 409 and r.get_json()["erro"] == "A sessão do Fracttal é de outra conta; entre de novo pelo Fracttal."
    assert c.post(f"{PONTE}/C-1/gravar", json={"n": 5}).status_code == 400
    r = c.post(f"{PONTE}/C-1/gravar", json=dict(visto, n=4))
    assert r.status_code == 409 and "a contagem mudou desde que você abriu a tela; recarregue" in r.get_json()["erro"].lower()
    falso.mover("10", "501", "entrada", 1, quando="2026-10-20T12:00:00Z")    # 10 → 11: o N segue 5, a assinatura não
    r = c.post(f"{PONTE}/C-1/gravar", json=visto)
    assert r.status_code == 409 and "recarregue" in r.get_json()["erro"]
    assert c.post(f"{PONTE}/C-9/gravar", json=visto).status_code == 404
    assert _eventos(app) == [] and falso.chamadas.count("abrir_ajuste") == 0
    visto = _visto(app, falso)
    assert c.post(f"{PONTE}/C-1/gravar", json=visto).status_code == 200
    G.aguardar("C-1")
    r = c.post(f"{PONTE}/C-1/gravar", json=visto)                     # a 2ª vez: já não se aprova
    assert r.status_code == 409


def test_continuar_pela_ponte_so_de_quem_aprovou(app, inv, ponte_falsa, monkeypatch):  # noqa: F811
    """Parada (o almoxarifado em inventário físico): a tela mostra o "Continuar" só para quem aprovou; outra pessoa do PCM
    leva 403 na ponte. Quem aprovou continua e a gravação termina."""
    _cenario(inv)
    falso = ponte_falsa["falso"]
    visto = _visto(app, falso)
    falso.definir_modo("10", 3)
    c = _pcm(app, monkeypatch)
    _cookie_os(app, c)
    assert c.post(f"{PONTE}/C-1/gravar", json=visto).status_code == 200
    G.aguardar("C-1")
    html = c.get(f"{LISTA}/C-1").get_data(as_text=True)
    assert re.search(r"<button[^>]*data-grav-continuar(?![^>]*hidden)[^>]*>", html)
    assert re.search(r"<button[^>]*data-grav-encerrar(?![^>]*hidden)[^>]*>", html)     # quem aprovou encerra a qualquer hora
    assert "Inventário físico" in html
    outra = _pcm(app, monkeypatch, email="outra.pessoa@exemplo.test")
    _cookie_os(app, outra, email="outra.pessoa@exemplo.test")
    html = outra.get(f"{LISTA}/C-1").get_data(as_text=True)
    assert re.search(r"<button[^>]*data-grav-continuar[^>]*hidden", html)
    assert re.search(r"<button[^>]*data-grav-encerrar[^>]*hidden", html)
    j = outra.get(f"{LISTA}/C-1/estado.json").get_json()
    assert j["pode_continuar"] is False and j["pode_encerrar"] is False
    r = outra.post(f"{PONTE}/C-1/continuar", json={})
    assert r.status_code == 403 and "só quem aprovou continua" in r.get_json()["erro"]
    r = outra.post(f"{PONTE}/C-1/encerrar", json={"motivo": "x"})
    assert r.status_code == 403 and "Só quem aprovou" in r.get_json()["erro"]
    falso.definir_modo("10", 0)
    r = c.post(f"{PONTE}/C-1/continuar", json={})
    assert r.status_code == 200, r.get_json()
    G.aguardar("C-1")
    assert G.estado(app.config, "C-1")["estado"] == "concluida"
    assert c.post(f"{PONTE}/C-9/continuar", json={}).status_code == 404


def test_o_controle_ilegivel_na_ponte_e_409(app, inv, ponte_falsa, monkeypatch):  # noqa: F811
    """O controle que não se lê: a ponte diz isso (409), e não "só quem aprovou" (ninguém sabe quem aprovou)."""
    _cenario(inv)
    c = _pcm(app, monkeypatch)
    _cookie_os(app, c)
    falso = ponte_falsa["falso"]
    falso.definir_modo("10", 3)
    assert c.post(f"{PONTE}/C-1/gravar", json=_visto(app, falso)).status_code == 200
    G.aguardar("C-1")
    next(grav_pasta(app).glob("C-1*.json")).write_text("{não é json", "utf-8")
    for acao, corpo in (("continuar", {}), ("encerrar", {"motivo": "x"})):
        r = c.post(f"{PONTE}/C-1/{acao}", json=corpo)
        assert r.status_code == 409 and "ilegível" in r.get_json()["erro"], acao


def test_encerrar_pela_ponte(app, inv, ponte_falsa, monkeypatch):  # noqa: F811
    """Quem aprovou encerra pela ponte (o modo lido na hora no Fracttal, por isso na ponte): o motivo é obrigatório, e com o
    almoxarifado em modo 2 é recusado."""
    _cenario(inv)
    falso = ponte_falsa["falso"]
    visto = _visto(app, falso)
    falso._expira_em = 8                                      # para com a sessão aberta (modo 2)
    c = _pcm(app, monkeypatch)
    _cookie_os(app, c)
    assert c.post(f"{PONTE}/C-1/gravar", json=visto).status_code == 200
    G.aguardar("C-1")
    falso._expira_em = None
    assert c.post(f"{PONTE}/C-1/encerrar", json={}).status_code == 400
    r = c.post(f"{PONTE}/C-1/encerrar", json={"motivo": "o almoxarifado vai ser recontado"})
    assert r.status_code == 409 and "modo 2" in r.get_json()["erro"]
    falso.voltar_ao_normal("10")                              # alguém fechou o ajuste no Fracttal
    r = c.post(f"{PONTE}/C-1/encerrar", json={"motivo": "o almoxarifado vai ser recontado"})
    assert r.status_code == 200, r.get_json()
    assert G.estado(app.config, "C-1")["estado"] == "encerrada"
    assert L.contagens(app.config)[0]["estado"] == "gravada_com_conflitos"


def test_a_tela_e_a_lista_mostram_o_aviso_de_travado(app, inv, ponte_falsa, monkeypatch):  # noqa: F811
    """O aviso forte na contagem e também na lista das contagens: quem aprovou talvez nem abra a contagem."""
    _cenario(inv)
    falso = ponte_falsa["falso"]
    visto = _visto(app, falso)
    falso._expira_em = 8
    c = _pcm(app, monkeypatch)
    _cookie_os(app, c)
    assert c.post(f"{PONTE}/C-1/gravar", json=visto).status_code == 200
    G.aguardar("C-1")
    html = c.get(f"{LISTA}/C-1").get_data(as_text=True)
    assert "ficou travado em ajuste no Fracttal; quem aprovou precisa continuar para destravar" in html
    assert "o login do Fracttal expirou" in html
    lista = c.get(LISTA).get_data(as_text=True)
    assert "ficou travado em ajuste no Fracttal; quem aprovou precisa continuar para destravar" in lista
    assert 'data-travada="C-1"' in lista and 'href="/t/pcm/pecas/inventario/C-1"' in lista
