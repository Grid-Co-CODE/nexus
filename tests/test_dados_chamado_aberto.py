"""Os chamados de garantia em aberto para o App de Campo (08/11/2026): `nexus/dados/fato_chamado_aberto.py` (o fato) e
`nexus/torres/oscreator/chamados_abertos.py` (quem grava). OS, códigos e chaves de mentira: o repositório é público."""
import hashlib
import hmac
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nexus.casca import minutos_ocupados as MO
from nexus.dados import catalogo, explica
from nexus.dados import fato_chamado_aberto as F
from nexus.torres.oscreator import chamados_abertos as CA
from nexus.torres.oscreator import ponte
from tests.pg_falso import ApiPGFalsa

AGORA = datetime(2026, 11, 8, 15, 0, 0, tzinfo=timezone.utc)
CHAVE_TESTE = "chave-hmac-de-teste"
INSP_ETQ = ((2036, "Aguardando Garantia"),)
ADM_ETQ = ((9001, "CHAMADOS"),)


def _insp(folio, status=1, code="TST-UFV100-ETKR1.10", data="2026-11-03T12:00:00", oid=None):
    return {"id": oid or int(folio) * 10, "folio": str(folio), "tipo_tarefa": "Inspeção", "etiquetas": INSP_ETQ,
            "status_id": status, "note": "[CHAMADO] STI · origem: RONDA", "descricao": "Inspeção de garantia",
            "code": code, "data": data}


def _adm(folio, insp_folio, status=1, aguardando=False, code="TST-UFV100-ETKR1.10", oid=None):
    bloco = ("Campos do formulário do fabricante: aguardando a inspeção" if aguardando
             else "Campos do formulário do fabricante (coletados na inspeção):\n  serial: X1")
    nota = ("[CHAMADO] Acompanhamento — STI · Estrutura Trackers\nOS de campo: - · Inspeção: %s · Ativo: %s\n"
            "Data da falha: 03/11/2026 09:00 · Menos de 7 dias: Sim\n\n%s" % (insp_folio, code, bloco))
    return {"id": oid or int(folio) * 10, "folio": str(folio), "tipo_tarefa": "Administrativa", "etiquetas": ADM_ETQ,
            "status_id": status, "note": nota, "descricao": "[Tracker] - Acompanhamento de chamado STI", "code": code,
            "data": "2026-11-03T13:00:00"}


EQUIP = {"TST-UFV100-ETKR1.10": (501, 77)}


def _linhas(regs, tickets=None, anteriores=(), conta=None, agora=AGORA):
    return F.linhas(regs, tickets or {}, EQUIP, list(anteriores), agora, CHAVE_TESTE, conta)


def test_as_constantes_sao_as_do_pacote_e_do_quadro():
    raiz = str(Path(ponte.RAIZ_CLONE).parent)
    for p in (raiz, ponte.RAIZ_CLONE):
        if p not in sys.path:
            sys.path.append(p)
    import chamado_garantia as cg
    from chamado_garantia import regras
    from os_web import acomp_web
    assert (F.TIPO_INSPECAO, F.ETIQUETA_INSPECAO) == (regras.TIPO_TAREFA, regras.ETIQUETA)
    assert (F.TIPO_ADM, F.ETIQUETA_ADM) == (regras.TIPO_TAREFA_ACOMPANHAMENTO, regras.ETIQUETA_ACOMPANHAMENTO)
    assert F.MARCA_NOTA == acomp_web.MARCA_NOTA == cg.acompanhamento.MARCA_NOTA
    assert F.LINHA_AGUARDANDO == cg.acompanhamento.LINHA_AGUARDANDO
    # a nota que o pacote monta é a que o fato lê: a cadeia e o "aguardando"
    d = cg.montar_acompanhamento({"folio": "19234", "code": "TST-UFV100-ETKR1.10", "nome_ativo": "Tracker 10",
                                  "tipo": "Estrutura Trackers", "os_pai": "", "event_date": "2026-11-03T12:00:00+00:00"},
                                 "")
    assert F.cadeia(d["nota"]) == ("19234", "TST-UFV100-ETKR1.10") and F.nota_aguardando(d["nota"])


def test_catalogo_registra_o_fato_e_o_livro_antes_de_existir():
    fato = next(f for f in catalogo.FATOS if f.id == "chamado_aberto")
    assert fato.conformado_em == "%s · %s" % (F.LIVRO, F.ABA) and fato.tipo == F.TIPO
    livro = next(l for l in catalogo.LIVROS if l.nome == F.LIVRO)
    assert set(livro.abas) == {F.ABA, F.ABA_ATU} and livro.no_banco is False and not livro.so_cresce
    assert "chamado_aberto" in explica.RESUMO and "chamado_aberto" in explica.PARA_QUE
    # o livro é só deste laço: o nexus_chamados (o fato_chamado de hora em hora) não ganha a aba nova
    velho = next(l for l in catalogo.LIVROS if l.nome == "nexus_chamados")
    assert F.ABA not in velho.abas


def test_as_colunas_do_quadro():
    regs = [_insp(100, status=1), _adm(101, 100, aguardando=True),                 # Inspeção em processo
            _insp(200, status=2), _adm(201, 200, aguardando=True),                 # nota ainda aguardando
            _insp(300, status=2), _adm(301, 300),                                  # ticket escrito
            _insp(400, status=3), _adm(401, 400),                                  # sem ticket
            _insp(500, status=2), _adm(501, 500),                                  # ticket não lido
            _insp(600, status=1)]                                                  # Inspeção sem administrativa
    conta = {}
    lin = _linhas(regs, tickets={3010: "TK-1", 4010: "", 5010: None}, conta=conta)
    col = {l["inspecao_folio"]: (l["adm_folio"], l["coluna"]) for l in lin}
    assert col == {"100": ("101", "aguardando_inspecao"), "200": ("201", "aguardando_inspecao"),
                   "300": ("301", "ticket_aberto"), "400": ("401", "chegaram"), "500": ("501", ""),
                   "600": ("", "aguardando_inspecao")}
    assert conta["coluna_desconhecida"] == 1 and conta["acompanhamentos"] == 5 and conta["inspecoes"] == 1
    assert [l["inspecao_folio"] for l in lin] == sorted(col)


def test_o_que_nao_esta_em_aberto_fica_fora():
    regs = [_insp(100, status=1), _adm(101, 100, status=2),       # administrativa em verificação: Finalizados no quadro
            _insp(200, status=3),                                  # Inspeção concluída sem administrativa
            _insp(300, status=4),                                  # Inspeção cancelada
            _insp(400, status=1), _adm(401, 400, status=4),        # administrativa cancelada: a Inspeção volta a valer
            dict(_adm(501, 500), etiquetas=()),                    # sem a etiqueta CHAMADOS: não é do quadro
            dict(_insp(600), etiquetas=((1, "Outra"),))]           # Inspeção sem a etiqueta de garantia
    lin = _linhas(regs)
    assert [(l["inspecao_folio"], l["adm_folio"]) for l in lin] == [("400", "")]


def test_retroativa_sem_inspecao_e_duas_administrativas():
    retro = dict(_adm(701, ""), note="[CHAMADO] Acompanhamento — STI · Estrutura Trackers\nAtivo: TST-UFV100-ETKR1.10")
    regs = [retro, _insp(800, status=2), _adm(801, 800), _adm(802, 800)]
    conta = {}
    lin = _linhas(regs, tickets={8010: "", 8020: "TK"}, conta=conta)
    assert [(l["inspecao_folio"], l["adm_folio"]) for l in lin] == [("", "701"), ("800", "801"), ("800", "802")]
    assert conta["sem_inspecao"] == 1 and conta["mais_de_um"] == 1


def test_liga_pelo_codigo_e_nao_chuta():
    regs = [_insp(100, code="tst-ufv100-etkr1.10 "), _insp(200, code="TST-UFV100-ETKR9.99"), _insp(300, code="")]
    conta = {}
    lin = {l["inspecao_folio"]: l for l in _linhas(regs, conta=conta)}
    assert (lin["100"]["equipamento_id"], lin["100"]["usina_id"]) == (501, 77)
    assert (lin["200"]["equipamento_id"], lin["200"]["usina_id"]) == (None, None)
    assert lin["300"]["codigo"] == "" and conta["sem_equipamento"] == 2


def test_dia_de_brasilia_e_nada_de_pessoa():
    lin = _linhas([_insp(100, data="2026-11-04T02:30:00")])[0]      # 02:30 UTC = 23:30 do dia 3 em Brasília
    assert lin["data_id_inspecao"] == 20261103
    assert list(lin) == F.CAB
    assert F.CAB == ["inspecao_folio", "adm_folio", "codigo", "equipamento_id", "usina_id", "coluna",
                     "data_id_inspecao", "atualizado_em", "assinatura", "equipamento_ligado_por", "usina_ligada_por"]
    assert (lin["equipamento_ligado_por"], lin["usina_ligada_por"]) == ("código do ativo", "equipamento")


def test_a_linha_que_nao_mudou_guarda_a_hora():
    regs = [_insp(100, status=1)]
    a = _linhas(regs)[0]
    assert a["atualizado_em"] == "2026-11-08T15:00:00Z"
    # a API pode devolver tudo como texto: a mesma linha relida não muda a hora nem a assinatura
    relida = {k: ("" if v is None else str(v)) for k, v in a.items()}
    b = _linhas(regs, anteriores=[relida], agora=AGORA + timedelta(minutes=10))[0]
    assert (b["atualizado_em"], b["assinatura"]) == (a["atualizado_em"], a["assinatura"])
    c = _linhas([_insp(100, status=2)], anteriores=[relida], agora=AGORA + timedelta(minutes=10))[0]
    assert c["atualizado_em"] == "2026-11-08T15:10:00Z" and c["coluna"] == "" and c["assinatura"] != a["assinatura"]


def _hmac_ref(texto):
    k = hmac.new(CHAVE_TESTE.encode(), b"nexus:oscreator:chamados-app", hashlib.sha256).digest()
    return hmac.new(k, texto.encode(), hashlib.sha256).hexdigest()


# Os vetores que vão para o App (um teste permanente do lado de lá também): a chave "chave-hmac-de-teste"
VETORES = [
    ({"inspecao_folio": "19234", "adm_folio": "19235", "codigo": "TST-UFV100-ETKR1.10", "equipamento_id": 501,
      "usina_id": 77, "coluna": "chegaram", "data_id_inspecao": 20261103, "atualizado_em": "2026-11-08T15:00:00Z"},
     "chamado_aberto|19234|19235|TST-UFV100-ETKR1.10|501|77|chegaram|20261103|2026-11-08T15:00:00Z"),
    ({"inspecao_folio": "19240", "adm_folio": "", "codigo": "TST-UFV100-ETKR1.11", "equipamento_id": None,
      "usina_id": None, "coluna": "aguardando_inspecao", "data_id_inspecao": 20261107,
      "atualizado_em": "2026-11-08T15:10:00Z"},
     "chamado_aberto|19240||TST-UFV100-ETKR1.11|||aguardando_inspecao|20261107|2026-11-08T15:10:00Z"),
    ({"inspecao_folio": "", "adm_folio": "18001", "codigo": "TST-UFV100-ETKR2.3", "equipamento_id": 502,
      "usina_id": 77, "coluna": "", "data_id_inspecao": None, "atualizado_em": "2026-11-08T15:20:00Z"},
     "chamado_aberto||18001|TST-UFV100-ETKR2.3|502|77|||2026-11-08T15:20:00Z"),
]


@pytest.mark.parametrize("linha,texto", VETORES)
def test_vetores_da_assinatura(linha, texto):
    assert F.texto_assinado(linha) == texto
    assert F.assinatura(linha, CHAVE_TESTE) == _hmac_ref(texto)
    # a mesma linha relida como texto (o "501" do banco) assina igual
    assert F.assinatura({k: ("" if v is None else str(v)) for k, v in linha.items()}, CHAVE_TESTE) == _hmac_ref(texto)
    assert F.assinatura(linha, "") == ""


def test_atualizacao_assinada():
    atu = F.atualizacao(3, AGORA, AGORA - timedelta(minutes=2), None, CHAVE_TESTE)
    txt = "atualizacao_chamados|2026-11-08T15:00:00Z|3|2026-11-08T14:58:00Z|"
    assert F.texto_assinado_atualizacao(atu) == txt and atu["assinatura"] == _hmac_ref(txt)
    assert list(atu) == F.CAB_ATU


def test_minutos_e_espera():
    assert all(MO.OCUPADOS[m].startswith("os chamados de garantia em aberto") for m in MO.CHAMADOS_ABERTOS)
    passos = sorted(MO.CHAMADOS_ABERTOS) + [sorted(MO.CHAMADOS_ABERTOS)[0] + 60]
    assert max(b - a for a, b in zip(passos, passos[1:])) < 30          # o App trata a foto de mais de 30 min como velha
    brt = timezone(timedelta(hours=-3))
    assert CA._espera_s(datetime(2026, 11, 8, 10, 4, 30, tzinfo=brt)) == 4 * 60 + 30     # :04:30 → :09
    assert CA._espera_s(datetime(2026, 11, 8, 10, 53, 0, tzinfo=brt)) == 10 * 60          # :53 → :03


# ── quem grava ────────────────────────────────────────────────────────────────────────────────────────────────
CFG = {"NEXUS_PESSOA_HMAC": CHAVE_TESTE, "GRIDCO_SQL_TOKEN": "t", "GRIDCO_DB_API": "http://banco"}


def _publicar(api, regs, fresca=True, tickets=({}, None), cfg=CFG, agora=AGORA):
    lista = (regs, AGORA - timedelta(minutes=3), frozenset(), fresca)
    return CA.publicar(cfg, api, lista=lista, tickets=tickets, equip=EQUIP, agora=agora)


def test_desligado_por_padrao(monkeypatch):
    monkeypatch.delenv("NEXUS_CHAMADOS_ABERTOS", raising=False)
    assert CA.LIGADO_PADRAO is False and CA.ligado({}) is False
    monkeypatch.setenv("NEXUS_CHAMADOS_ABERTOS", "1")
    assert CA.ligado({}) is True


def test_nao_grava_sem_lista_fresca_sem_chave_ou_sem_token():
    api = ApiPGFalsa()
    assert "pulou" in _publicar(api, [_insp(100)], fresca=False)
    assert "erro" in _publicar(api, [_insp(100)], cfg=dict(CFG, NEXUS_PESSOA_HMAC=""))
    assert "erro" in _publicar(api, [_insp(100)], cfg=dict(CFG, GRIDCO_SQL_TOKEN=""))
    assert api.syncs == 0
    # no PC (nenhuma lista central carregada neste processo) a lista nunca é fresca
    assert CA.lista_central()[3] is False or "os_central" in sys.modules


def test_grava_confere_e_regrava_a_foto_que_encolhe():
    api = ApiPGFalsa(como_texto=True)
    rel = _publicar(api, [_insp(100), _insp(200), _adm(201, 200, aguardando=True)])
    assert rel["linhas"] == 2 and rel["gravado"] == {F.ABA: 2, F.ABA_ATU: 1}
    gravadas = api.linhas(F.LIVRO, F.ABA)
    assert len(gravadas) == 2
    # dez minutos depois o chamado 100 fechou: a foto encolhe, e a linha que ficou guarda a hora e a assinatura
    rel2 = _publicar(api, [_insp(100, status=3), _insp(200), _adm(201, 200, aguardando=True)],
                     agora=AGORA + timedelta(minutes=10))
    assert rel2["linhas"] == 1 and rel2["antes"] == 2
    atu = api.linhas(F.LIVRO, F.ABA_ATU)
    assert len(atu) == 1
