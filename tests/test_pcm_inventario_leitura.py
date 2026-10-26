"""As contagens do inventário do almoxarifado e o estado de cada uma (26/10/2026, Levi): o livro das contagens que o App de
Campo publica (14 colunas, a última o "ID da linha") lido pela cópia de 5 min, e o estado de cada contagem tirado dos
eventos do livro do inventário (`nexus_almoxarifado_inventario`). Desenho:
docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md (seção 4.2). Aqui o banco é o falso do Campo e o
livro do inventário é o arquivo local (`NEXUS_ALMOX_INVENTARIO_ARQUIVO`). Dado de mentira: usina, códigos e IDs
inventados, sem nome de gente."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from test_campo_visao import BRT, _aba, banco  # noqa: F401  (banco é fixture)

from nexus.campo import visao
from nexus.dados import almoxarifado as A
from nexus.dados import fato_inventario as F
from nexus.pcm.inventario import contas
from nexus.pcm.inventario import leitura as L

AGORA = datetime(2026, 10, 26, 12, 0, tzinfo=BRT)
USINA = "Thopen - Altair 1 - SP"            # a de-para do `banco` liga a Altair (usina 1)
SEM_LIGACAO = "Cliente Teste - Usina Z - MT"


def _iso(dias_atras=0.0, horas=0.0):
    return (AGORA.astimezone(timezone.utc) - timedelta(days=dias_atras, hours=horas)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _linha(contagem, id_linha, id_item="", contado="", tipo="item", almox="10", contada=None, enviada=None,
           usina=USINA, **mais):
    """Uma linha do livro das contagens do jeito que a API a devolve: as 14 colunas, tudo como texto."""
    l = dict.fromkeys(A.COLUNAS_CONTAGENS, "")
    l.update({"ID da contagem": contagem, "Enviada em": enviada or _iso(horas=2), "Contada em": contada or _iso(horas=3),
              "ID do almoxarifado": str(almox), "Usina": usina, "Tipo": tipo, "ID do item": str(id_item),
              "Código": f"SP-{id_item}" if id_item != "" else "", "Contado": contado, "ID da linha": str(id_linha)})
    l.update(mais)
    return l


def _publicar(api, *linhas):
    _aba(api, A.LIVRO_CONTAGENS, A.ABA_CONTAGENS, list(linhas))
    visao.limpar()


def _por_id(app):
    return {c["contagem_id"]: c for c in L.contagens(app.config)}


def _ev(contagem, tipo, id_item=None, **mais):
    e = {"tipo": tipo, "contagem_id": contagem, "id_almoxarifado": mais.pop("almox", "10")}
    if id_item:
        e["id_item"] = str(id_item)
    e.update(mais)
    return e


def _gravar(app, *eventos):
    F.acrescentar(app.config, F.ABA_EVENTO, list(eventos))


@pytest.fixture
def inv(app, banco, tmp_path, monkeypatch):  # noqa: F811
    """O banco falso do Campo, o livro do inventário num arquivo e o relógio parado em 26/10/2026 12:00 (Brasília)."""
    monkeypatch.setattr(visao, "_agora", lambda: AGORA)
    app.config.update(NEXUS_ALMOX_INVENTARIO_ARQUIVO=str(tmp_path / "inventario.json"))
    F.limpar()
    yield banco
    F.limpar()


# ── o estado de cada contagem, pelos eventos ─────────────────────────────────────────────────────────────────────────────
def test_o_contrato_dos_estados():
    assert L.ESTADOS == ("nova", "revisada", "recontagem_pedida", "substituida", "gravando", "gravada",
                         "gravada_com_conflitos")


def test_estados_pelos_eventos(app, inv):
    """Sem evento a contagem é nova; tirar ou corrigir uma peça a deixa revisada; a recontagem pedida a recusa; aprovada
    e sem o fim, gravando; com a gravação de todas as peças do lote, gravada, e com um conflito, gravada com conflitos.
    Cada contagem num almoxarifado: no mesmo, a mais nova substituiria as outras."""
    linhas = []
    for almox in ("10", "11", "12", "13", "14", "15"):
        linhas += [_linha(f"C-{almox}", "L1", "501", "3", almox=almox), _linha(f"C-{almox}", "L2", "502", "4", almox=almox)]
    _publicar(inv, *linhas)
    _gravar(app,
            _ev("C-11", "peca_tirada", 501, almox="11"),
            _ev("C-12", "recontagem_pedida", almox="12"),
            # a 13 foi aprovada (uma linha `aprovada` por peça do lote) e a gravação ainda não acabou: só a 501 gravou
            _ev("C-13", "aprovada", 501, almox="13"), _ev("C-13", "aprovada", 502, almox="13"),
            _ev("C-13", "peca_gravada", 501, almox="13"),
            # a 14 gravou as duas
            _ev("C-14", "aprovada", 501, almox="14"), _ev("C-14", "aprovada", 502, almox="14"),
            _ev("C-14", "peca_gravada", 501, almox="14"), _ev("C-14", "peca_gravada", 502, almox="14"),
            # a 15 gravou uma e a outra deu conflito
            _ev("C-15", "aprovada", 501, almox="15"), _ev("C-15", "aprovada", 502, almox="15"),
            _ev("C-15", "peca_gravada", 501, almox="15"), _ev("C-15", "conflito", 502, almox="15"))
    estado = {i: c["estado"] for i, c in _por_id(app).items()}
    assert estado == {"C-10": "nova", "C-11": "revisada", "C-12": "recontagem_pedida", "C-13": "gravando",
                      "C-14": "gravada", "C-15": "gravada_com_conflitos"}
    assert set(estado.values()) <= set(L.ESTADOS)


def test_numero_corrigido_tambem_deixa_revisada(app, inv):
    _publicar(inv, _linha("C-1", "L1", "501", "3"))
    _gravar(app, _ev("C-1", "numero_corrigido", 501, de_qtd=3, para_qtd=4))
    assert _por_id(app)["C-1"]["estado"] == "revisada"


def test_aprovada_sem_as_pecas_do_lote_nunca_vira_gravada(app, inv):
    """Sem saber quais peças o lote tinha (o evento `aprovada` sem peça), a leitura não adivinha o fim: segue gravando.
    Dar a contagem por gravada antes da hora deixaria o PCM crer que o estoque já foi acertado."""
    _publicar(inv, _linha("C-1", "L1", "501", "3"), _linha("C-1", "L2", "502", "4"))
    _gravar(app, _ev("C-1", "aprovada"), _ev("C-1", "peca_gravada", 501))
    assert _por_id(app)["C-1"]["estado"] == "gravando"


def test_um_erro_na_peca_deixa_gravando(app, inv):
    """O erro não encerra a peça (ela pode ser retomada): a contagem segue gravando até a peça gravar ou dar conflito."""
    _publicar(inv, _linha("C-1", "L1", "501", "3"))
    _gravar(app, _ev("C-1", "aprovada", 501), _ev("C-1", "erro", 501))
    assert _por_id(app)["C-1"]["estado"] == "gravando"


def test_o_estado_de_uma_contagem_nao_vem_de_outra(app, inv):
    _publicar(inv, _linha("C-1", "L1", "501", "3", almox="10"), _linha("C-2", "L1", "501", "3", almox="11"))
    _gravar(app, _ev("C-2", "recontagem_pedida", almox="11"))
    assert {i: c["estado"] for i, c in _por_id(app).items()} == {"C-1": "nova", "C-2": "recontagem_pedida"}


def test_o_estado_novo_aparece_na_hora_mesmo_com_o_livro_do_app_na_copia(app, inv):
    """O livro do App vem da cópia de 5 min, mas o estado sai dos eventos, que a gravação renova: pedir a recontagem e ver
    "nova" por mais 5 min deixaria o PCM pedir de novo."""
    _publicar(inv, _linha("C-1", "L1", "501", "3"))
    assert _por_id(app)["C-1"]["estado"] == "nova"
    _gravar(app, _ev("C-1", "recontagem_pedida"))
    assert _por_id(app)["C-1"]["estado"] == "recontagem_pedida"


# ── a contagem mais nova substitui a velha ───────────────────────────────────────────────────────────────────────────────
def test_a_mais_nova_substitui_a_velha_nao_gravada(app, inv):
    _publicar(inv,
              _linha("C-VELHA", "L1", "501", "3", contada=_iso(dias_atras=2)),
              _linha("C-NOVA", "L1", "501", "5", contada=_iso(dias_atras=1)),
              _linha("C-OUTRO", "L1", "501", "9", almox="11", contada=_iso(dias_atras=3)))
    por = _por_id(app)
    assert (por["C-VELHA"]["estado"], por["C-NOVA"]["estado"], por["C-OUTRO"]["estado"]) == ("substituida", "nova", "nova")
    assert not por["C-VELHA"]["aprovavel"] and por["C-VELHA"]["motivo_nao_aprovavel"] == "substituída"
    assert por["C-NOVA"]["aprovavel"]
    # a lista vem da mais nova para a mais velha
    assert [c["contagem_id"] for c in L.contagens(app.config)] == ["C-NOVA", "C-VELHA", "C-OUTRO"]


def test_a_velha_ja_gravada_fica_como_esta(app, inv):
    _publicar(inv,
              _linha("C-VELHA", "L1", "501", "3", contada=_iso(dias_atras=2)),
              _linha("C-NOVA", "L1", "501", "5", contada=_iso(dias_atras=1)))
    _gravar(app, _ev("C-VELHA", "aprovada", 501), _ev("C-VELHA", "peca_gravada", 501))
    por = _por_id(app)
    assert (por["C-VELHA"]["estado"], por["C-NOVA"]["estado"]) == ("gravada", "nova")


def test_a_velha_gravando_tambem_fica_como_esta(app, inv):
    """A gravação começada vale como gravada para a substituição (`gravadas` = gravando, gravada e com conflitos)."""
    _publicar(inv,
              _linha("C-VELHA", "L1", "501", "3", contada=_iso(dias_atras=2)),
              _linha("C-NOVA", "L1", "501", "5", contada=_iso(dias_atras=1)))
    _gravar(app, _ev("C-VELHA", "aprovada", 501))
    assert _por_id(app)["C-VELHA"]["estado"] == "gravando"


def test_a_recontagem_pedida_nao_substitui_as_boas(app, inv):
    """Quem chama as `contas.substituidas` passa só as contagens VIVAS: a mais nova, recusada pelo PCM, não tem número
    para gravar no lugar da anterior, e a anterior segue valendo (a regra da Task 3)."""
    _publicar(inv,
              _linha("C-BOA", "L1", "501", "3", contada=_iso(dias_atras=2)),
              _linha("C-RECUSADA", "L1", "501", "5", contada=_iso(dias_atras=1)))
    _gravar(app, _ev("C-RECUSADA", "recontagem_pedida"))
    por = _por_id(app)
    assert (por["C-BOA"]["estado"], por["C-RECUSADA"]["estado"]) == ("nova", "recontagem_pedida")
    assert por["C-BOA"]["aprovavel"]


@pytest.mark.parametrize("quebrada", [
    dict(id_linha="", contada=_iso(dias_atras=1)),                       # o App mandou a linha sem "ID da linha"
    dict(id_linha="None", contada=_iso(dias_atras=1)),
    dict(id_linha="L1", contada=_iso(horas=-5)),                         # o relógio do celular adiantado de horas: "contada no futuro"
])
def test_a_mais_nova_que_nao_se_aprova_nao_substitui_as_boas(app, inv, quebrada):
    """A contagem mais nova que não se aprova (contrato do App violado, ou o relógio do celular adiantado) não pode tirar do
    caminho as que se aprovam: com ela valendo como "a mais nova" o almoxarifado ficava sem nenhuma contagem para revisar."""
    _publicar(inv,
              _linha("C-ANTIGA", "L1", "501", "3", contada=_iso(dias_atras=3)),
              _linha("C-BOA", "L1", "501", "3", contada=_iso(dias_atras=2)),
              _linha("C-QUEBRADA", quebrada["id_linha"], "501", "3", contada=quebrada["contada"]))
    por = _por_id(app)
    assert not por["C-QUEBRADA"]["aprovavel"] and por["C-QUEBRADA"]["estado"] == "nova"
    assert (por["C-BOA"]["estado"], por["C-BOA"]["aprovavel"]) == ("nova", True)         # a boa mais nova segue valendo
    assert por["C-ANTIGA"]["estado"] == "substituida"                                     # e substitui a velha, como sempre


def test_o_relogio_pouco_adiantado_ainda_vale_como_a_mais_nova(app, inv):
    """Meia hora de relógio adiantado está dentro da tolerância (`RELOGIO_ADIANTADO`, 1 h): a contagem se aprova e vale como
    a mais nova. A conta da substituição e a da janela de aprovação usam o mesmo limite."""
    _publicar(inv,
              _linha("C-VELHA", "L1", "501", "3", contada=_iso(dias_atras=1)),
              _linha("C-NOVA", "L1", "501", "3", contada=_iso(horas=-0.5)))
    por = _por_id(app)
    assert (por["C-NOVA"]["estado"], por["C-NOVA"]["aprovavel"], por["C-VELHA"]["estado"]) == ("nova", True, "substituida")


def test_o_evento_substituida_vale_e_a_leitura_nao_escreve(app, inv, tmp_path):
    """O estado `substituida` sai da conta ou do evento (quem aprova a nova pode registrá-lo); a leitura em si nunca
    grava: o arquivo do livro nem nasce."""
    _publicar(inv,
              _linha("C-VELHA", "L1", "501", "3", contada=_iso(dias_atras=2)),
              _linha("C-NOVA", "L1", "501", "5", contada=_iso(dias_atras=1)),
              _linha("C-OUTRA", "L1", "501", "7", almox="11"))
    assert _por_id(app)["C-VELHA"]["estado"] == "substituida"
    assert not (tmp_path / "inventario.json").exists()
    _gravar(app, _ev("C-OUTRA", "substituida", almox="11"))
    assert _por_id(app)["C-OUTRA"]["estado"] == "substituida"


# ── o livro do App ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_livro_do_app_que_nao_existe(app, inv):
    visao.limpar()
    assert L.contagens(app.config) == [] and L.livro_existe(app.config) is False


def test_livro_do_app_que_existe_vazio_nao_e_livro_que_falta(app, inv):
    _publicar(inv)
    assert L.contagens(app.config) == [] and L.livro_existe(app.config) is True


def test_os_campos_de_cada_contagem(app, inv):
    _publicar(inv,
              _linha("C-1", "L1", "501", "3,0", contada=_iso(horas=5), enviada=_iso(horas=1)),
              _linha("C-1", "L2", "502", "", contada=_iso(horas=5), enviada=_iso(horas=1)),
              _linha("C-1", "L3", "503", "0", contada=_iso(horas=5), enviada=_iso(horas=1)))
    _aba_saldo = [{"ID do item": "501", "Código": "SP-501", "ID do almoxarifado": "10", "Almoxarifado": "Almoxarifado Altair",
                   "Local do almoxarifado": "// Thopen/ Thopen - Altair 1 - SP/", "Saldo": "4", "Mínimo": "2",
                   "Início do ciclo": "x"}]
    _aba(inv, A.LIVRO_SALDO, A.ABA_SALDO, _aba_saldo)
    visao.limpar()
    c = L.contagens(app.config)[0]
    assert c["contagem_id"] == "C-1" and c["id_almox"] == "10" and c["almox"] == "Almoxarifado Altair"
    assert c["usina"] == "Altair" and c["usina_id"] == 1                  # a de-para do Fracttal liga a usina do cadastro
    assert c["contada_em"] == _iso(horas=5) and c["enviada_em"] == _iso(horas=1)
    assert [l["ID da linha"] for l in c["linhas"]] == ["L1", "L2", "L3"]
    assert (c["n_contadas"], c["n_em_branco"], c["n_curadoria"]) == (2, 1, 0)      # o 0 digitado é contado
    assert c["estado"] == "nova" and c["aprovavel"] and c["motivo_nao_aprovavel"] == "" and c["aviso"] == ""


def test_usina_sem_ligacao_fica_com_o_nome_do_fracttal(app, inv):
    _publicar(inv, _linha("C-1", "L1", "501", "3", usina=SEM_LIGACAO))
    c = L.contagens(app.config)[0]
    assert c["usina"] == SEM_LIGACAO and c["usina_id"] is None


def test_as_contagens_contam_as_linhas_depois_do_dedupe(app, inv):
    """A fila offline do App reenvia a contagem: a mesma (ID da contagem, ID da linha) é a MESMA peça, e as contas contam
    uma vez. O genérico por identificar e o achado fora do catálogo contam na curadoria; o achado em branco nem entra."""
    _publicar(inv,
              _linha("C-1", "L1", "501", "3"),
              _linha("C-1", "L1", "501", "3"),                                       # o reenvio da fila offline
              _linha("C-1", "L2", "502", ""),
              _linha("C-1", "L3", "503", "4", tipo="identificar", **{"Identificado como": ""}),
              _linha("C-1", "L4", "", "2", tipo="fora_do_catalogo", Descrição="peça sem etiqueta"),
              _linha("C-1", "L5", "", "", tipo="fora_do_catalogo", Descrição="outra, sem número"))
    c = L.contagens(app.config)[0]
    assert (c["n_contadas"], c["n_em_branco"], c["n_curadoria"]) == (1, 2, 2)


def test_a_curadoria_decidida_sai_da_conta_da_curadoria(app, inv):
    """O achado que o PCM já decidiu (é a peça X) deixa de ser pendência da curadoria e passa às contadas."""
    _publicar(inv, _linha("C-1", "L4", "", "2", tipo="fora_do_catalogo", Descrição="peça sem etiqueta"))
    assert L.contagens(app.config)[0]["n_curadoria"] == 1
    F.acrescentar(app.config, F.ABA_CURADORIA, [{"contagem_id": "C-1", "chave_linha": "L4", "decisao": "e_a_peca",
                                                 "id_item": "501"}])
    c = L.contagens(app.config)[0]
    assert (c["n_contadas"], c["n_curadoria"]) == (1, 0)


def test_almoxarifado_de_teste_fica_de_fora(app, inv):
    _publicar(inv, _linha("C-REAL", "L1", "501", "3"), _linha("C-TESTE", "L1", "501", "3", almox="134082"))
    assert {c["contagem_id"] for c in L.contagens(app.config)} == {"C-REAL", "C-TESTE"}
    app.config.update(NEXUS_ALMOX_TESTE_IDS="134082")
    assert {c["contagem_id"] for c in L.contagens(app.config)} == {"C-REAL"}


# ── a janela de aprovação: o porquê quando não se aprova ─────────────────────────────────────────────────────────────────
def test_contagem_de_91_dias_nao_aprova(app, inv):
    _publicar(inv,
              _linha("C-90", "L1", "501", "3", almox="10", contada=_iso(dias_atras=89, horas=23)),
              _linha("C-91", "L1", "501", "3", almox="11", contada=_iso(dias_atras=91)))
    por = _por_id(app)
    assert por["C-90"]["aprovavel"] and por["C-90"]["motivo_nao_aprovavel"] == ""
    assert not por["C-91"]["aprovavel"] and por["C-91"]["motivo_nao_aprovavel"] == "mais de 90 dias"
    assert por["C-91"]["estado"] == "nova"                  # o estado é dos eventos: a janela é outra coisa


def test_contada_no_futuro_diz_que_e_o_relogio_do_celular(app, inv):
    _publicar(inv, _linha("C-1", "L1", "501", "3", contada=_iso(horas=-5)))
    c = L.contagens(app.config)[0]
    assert not c["aprovavel"] and c["motivo_nao_aprovavel"] == "contada no futuro: o relógio do celular"


def test_data_ilegivel_nao_aprova_e_diz_por_que(app, inv):
    _publicar(inv, _linha("C-1", "L1", "501", "3", contada="ontem de manhã"))
    c = L.contagens(app.config)[0]
    assert not c["aprovavel"] and c["motivo_nao_aprovavel"] == "data da contagem ilegível"


def test_o_motivo_de_cada_estado_que_nao_se_aprova(app, inv):
    _publicar(inv, *[_linha(f"C-{a}", "L1", "501", "3", almox=a) for a in ("10", "11", "12", "13")])
    _gravar(app,
            _ev("C-11", "recontagem_pedida", almox="11"),
            _ev("C-12", "aprovada", 501, almox="12"),
            _ev("C-13", "aprovada", 501, almox="13"), _ev("C-13", "peca_gravada", 501, almox="13"))
    por = _por_id(app)
    assert por["C-10"]["aprovavel"]
    assert por["C-11"]["motivo_nao_aprovavel"] == "recontagem pedida"
    assert por["C-12"]["motivo_nao_aprovavel"] == "já gravada" and not por["C-12"]["aprovavel"]
    assert por["C-13"]["motivo_nao_aprovavel"] == "já gravada" and not por["C-13"]["aprovavel"]


def test_revisada_ainda_se_aprova(app, inv):
    _publicar(inv, _linha("C-1", "L1", "501", "3"))
    _gravar(app, _ev("C-1", "peca_tirada", 501))
    c = L.contagens(app.config)[0]
    assert c["estado"] == "revisada" and c["aprovavel"]


# ── o contrato do App violado ────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("vazio", ["", "None", "none", "   "])
def test_linha_sem_id_da_linha_e_contrato_violado(app, inv, vazio):
    """O `sync-xlsx` escreve o vazio como "None" (texto): duas linhas "sem ID" juntariam numa só nas contas (a chave é o ID
    da linha) e perderiam unidades contadas. A contagem ganha o aviso e não se aprova."""
    _publicar(inv, _linha("C-1", vazio, "501", "3"), _linha("C-1", vazio, "502", "4"))
    c = L.contagens(app.config)[0]
    assert c["aviso"] == "o App mandou linha sem ID da linha"
    assert not c["aprovavel"] and c["motivo_nao_aprovavel"] == "linha sem ID da linha"


def test_contagem_sem_almoxarifado_nao_se_aprova(app, inv):
    """Sem o ID do almoxarifado não há saldo do sistema para ler, nem de quem ser a mais nova."""
    _publicar(inv, _linha("C-1", "L1", "501", "3", almox=""), _linha("C-2", "L1", "501", "3", almox="None"))
    por = _por_id(app)
    assert all(c["aviso"] and not c["aprovavel"] for c in por.values())
    assert por["C-1"]["motivo_nao_aprovavel"] == "contagem sem almoxarifado"


def test_linha_sem_id_da_contagem_nao_entra(app, inv):
    _publicar(inv, _linha("", "L1", "501", "3"), _linha("None", "L1", "501", "3"), _linha("C-1", "L1", "501", "3"))
    assert [c["contagem_id"] for c in L.contagens(app.config)] == ["C-1"]


# ── o livro do inventário que não dá para ler ────────────────────────────────────────────────────────────────────────────
def test_livro_do_inventario_ilegivel_nao_vira_contagem_nova(app, inv, tmp_path):
    """O livro que não conseguiu ler NUNCA vira vazio: a contagem já gravada apareceria como `nova` e o PCM a aprovaria de
    novo. A leitura levanta a `Recusada` do livro, e a tela mostra o texto."""
    _publicar(inv, _linha("C-1", "L1", "501", "3"))
    (tmp_path / "inventario.json").write_text("{isso não é json", encoding="utf-8")
    F.limpar()
    with pytest.raises(F.Recusada):
        L.contagens(app.config)


def test_livro_do_app_que_nao_le_levanta(app, inv, monkeypatch):
    """O banco fora do ar não é "nenhuma contagem": a lista diria que não há o que revisar."""
    _publicar(inv, _linha("C-1", "L1", "501", "3"))

    def cair(*a, **k):
        raise ConnectionError("banco fora")
    monkeypatch.setattr(visao, "_livro", cair)
    visao.limpar()
    with pytest.raises(F.Recusada, match="tente de novo"):
        L.contagens(app.config)


# ── a revisão e a curadoria de uma contagem ──────────────────────────────────────────────────────────────────────────────
def test_a_revisao_da_contagem(app, inv):
    """O que o PCM já fez, na forma que as contas pedem: `tiradas` {id_item: motivo} e `corrigidos` {id_item: número}
    (vale o último). O motivo só existe cifrado no livro, e é aqui que se abre."""
    _publicar(inv, _linha("C-1", "L1", "501", "3"), _linha("C-1", "L2", "502", "4"))
    _gravar(app,
            _ev("C-1", "peca_tirada", 501, dados={"motivo": "peça contada de outro almoxarifado"}),
            _ev("C-1", "numero_corrigido", 502, de_qtd=4, para_qtd=5, dados={"motivo": "o técnico errou o dedo"}),
            _ev("C-1", "numero_corrigido", 502, de_qtd=4, para_qtd=6, dados={"motivo": "contei de novo"}),
            _ev("C-9", "peca_tirada", 501, dados={"motivo": "de outra contagem"}))
    r = L.revisao_da(app.config, "C-1")
    assert r["tiradas"] == {"501": "peça contada de outro almoxarifado"}
    assert r["corrigidos"] == {"502": 6.0}
    assert r["motivos_corrigidos"] == {"502": "contei de novo"}
    # as contas leem do mesmo jeito (a chave `tiradas` só importa pelo id)
    lote = contas.itens_do_lote([_linha("C-1", "L1", "501", "3"), _linha("C-1", "L2", "502", "4")], {}, {}, r)
    por = {i["id_item"]: i for i in lote}
    assert por["501"]["tirada"] and por["502"]["corrigido"] and por["502"]["contado"] == 6.0


def test_a_curadoria_da_contagem_vale_a_ultima_decisao_de_cada_linha(app, inv):
    _publicar(inv, _linha("C-1", "L4", "", "2", tipo="fora_do_catalogo"))
    F.acrescentar(app.config, F.ABA_CURADORIA, [
        {"contagem_id": "C-1", "chave_linha": "L4", "decisao": "descartar", "decidida_em": "2026-10-26T10:00:00Z"},
        {"contagem_id": "C-1", "chave_linha": "L4", "decisao": "e_a_peca", "id_item": "501",
         "decidida_em": "2026-10-26T11:00:00Z"},
        {"contagem_id": "C-2", "chave_linha": "L4", "decisao": "descartar", "decidida_em": "2026-10-26T11:30:00Z"}])
    assert L.curadoria_da(app.config, "C-1") == {"L4": {"decisao": "e_a_peca", "id_item": "501", "codigo": ""}}


def test_a_leitura_nao_mexe_na_copia_guardada(app, inv):
    """A lista do App fica guardada por 5 min e é de todos: quem mexe nas linhas de uma contagem não pode estragar a
    próxima leitura."""
    _publicar(inv, _linha("C-1", "L1", "501", "3"))
    c = L.contagens(app.config)[0]
    c["linhas"][0]["Contado"] = "999"
    c["linhas"].append({"x": 1})
    outra = L.contagens(app.config)[0]
    assert [l["Contado"] for l in outra["linhas"]] == ["3"]


def test_o_arquivo_do_livro_guarda_o_que_foi_gravado(app, inv, tmp_path):
    """Sanidade do teste: o livro local é o que o `acrescentar` gravou (o arquivo é a cópia de prova)."""
    _publicar(inv, _linha("C-1", "L1", "501", "3"))
    _gravar(app, _ev("C-1", "recontagem_pedida"))
    d = json.loads((tmp_path / "inventario.json").read_text("utf-8"))
    assert [e["tipo"] for e in d[F.ABA_EVENTO]] == ["recontagem_pedida"]
