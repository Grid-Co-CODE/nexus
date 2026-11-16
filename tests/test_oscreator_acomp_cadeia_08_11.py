"""A Inspeção de garantia realizada ganha a OS de acompanhamento que faltou (08/11/2026): `os_web/acomp_cadeia.py`. Levi:
"quero que a administrativa só nasça quando a de inspeção é realizada!". O Fracttal e a lista central são de mentira; nada
sai da máquina. Ativos, códigos e OS inventados (o repositório é público)."""
import datetime as dt
import sys
import types

import pytest

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402
from chamado_garantia import montar_acompanhamento  # noqa: E402
from os_web import acomp_cadeia as AC  # noqa: E402

INSP_ETQ = ((2036, "Aguardando Garantia"),)
ADM_ETQ = ((9001, "CHAMADOS"),)
ASSET = {"id": 77, "code": "TST-UFV100-ETKR1.10", "description": "Tracker 10 { TST-UFV100-ETKR1.10 }",
         "tipo": "Estrutura Trackers", "id_type_item": 2}
AGORA = dt.datetime(2026, 11, 10, 15, 0, tzinfo=dt.timezone.utc)
HA_1H = "2026-11-10T14:00:00"
HA_10MIN = "2026-11-10T14:50:00"


class Reg(types.SimpleNamespace):
    """O registro da lista central: atributos e `get`."""
    def get(self, k, d=None):
        return getattr(self, k, d)


def _insp(folio, status=2, data_fim=HA_1H, code=ASSET["code"], etiquetas=INSP_ETQ):
    return Reg(id=int(folio) * 10, folio=str(folio), tipo_tarefa="Inspeção", etiquetas=etiquetas, status_id=status,
               note="", descricao="[Tracker 10] - Inspeção para chamado STI", code=code,
               data="2026-11-09T12:00:00", data_fim=data_fim, event_date="2026-11-09T11:00:00")


def _adm(folio, insp_folio, status=1):
    d = montar_acompanhamento({"folio": insp_folio, "code": ASSET["code"], "nome_ativo": "Tracker 10",
                               "tipo": "Estrutura Trackers", "os_pai": "", "event_date": "2026-11-09T11:00:00+00:00"},
                              "STI", [("Número de série", "X1")])
    return Reg(id=int(folio) * 10, folio=str(folio), tipo_tarefa="Administrativa", etiquetas=ADM_ETQ, status_id=status,
               note=d["nota"], descricao=d["titulo"], code=ASSET["code"], data="2026-11-09T12:01:00", data_fim="",
               event_date="2026-11-09T11:00:00")


class Lista:
    def __init__(self, regs, marca="2026-11-10T14:00:00"):
        self.ordem = tuple(regs)
        self.marca = marca


class Fracttal:
    def __init__(self):
        self.criadas, self.etiquetas = [], []
        self.falhar = False
        self.status = {}
        self.vivas = {}             # {id da Inspeção: [nº das administrativas vivas]} lido "ao vivo"; None = a leitura falhou
        self.subtarefas = [{"descricao": "Número de série", "resposta": "SN-1"},
                           {"descricao": "Pergunta fora do modelo", "resposta": "Sim"},
                           {"descricao": "Sem resposta", "resposta": ""},
                           {"descricao": "Verificação sem valor", "resposta": "Não / pendente"}]

    def create_planned_os(self, asset, plan, **kw):
        if self.falhar:
            raise api.FracttalError("O Fracttal não respondeu (Recusado)")
        self.criadas.append((asset, plan, kw))
        n = 555 + len(self.criadas) - 1
        return {"id_work_order": n * 10, "wo_folio": str(n), "id_work_order_task": 1}


@pytest.fixture
def fr(monkeypatch, tmp_path):
    f = Fracttal()
    monkeypatch.setattr(api, "create_planned_os", f.create_planned_os)
    monkeypatch.setattr(api, "label_id_por_nome", lambda n: 9001 if n == "CHAMADOS" else None)
    monkeypatch.setattr(api, "apply_labels", lambda wid, ids: f.etiquetas.append((wid, ids)) or {})
    monkeypatch.setattr(api, "status_da_os", lambda wid: f.status.get(wid, 3))
    monkeypatch.setattr(AC, "_vivas_ao_vivo", lambda wid: f.vivas.get(wid, []))
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: {"subtarefas": f.subtarefas, "os_pai": "90",
                                                             "descricao": "[Tracker 10] - Inspeção para chamado STI",
                                                             "event_date": "2026-11-09T11:00:00"})
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: [ASSET])
    monkeypatch.setattr(api, "_rpc_subtasks", lambda subs: [dict(s, id="x") for s in subs])
    monkeypatch.setenv("OS_WEB_CHAMADO_RESP_ID", "4242")
    monkeypatch.setenv("OS_WEB_CHAMADO_RESP_NOME", "Equipe de Chamados")
    monkeypatch.setenv(AC.ENV, "1")
    monkeypatch.setenv(AC.ENV_DATA, "2026-11-10")
    from os_web import lista_central
    monkeypatch.setattr(lista_central, "criadas", lambda r: 0)
    AC.configurar_pasta(str(tmp_path))
    AC._FEITOS.clear()
    yield f
    AC.configurar_pasta(None)


def _com_lista(monkeypatch, regs):
    lista = Lista(regs) if regs is not None else None
    monkeypatch.setattr(AC, "_lista", lambda: lista)
    return lista


def test_ligado_desde_08_11_e_sem_data_nada_se_cria(monkeypatch):
    """Ligado pelo Levi em 08/11/2026, para as Inspeções realizadas desse dia em diante; o 0 desliga numa máquina, e sem a
    data nada se cria."""
    monkeypatch.delenv(AC.ENV, raising=False)
    monkeypatch.delenv(AC.ENV_DATA, raising=False)
    assert AC.LIGADO_PADRAO is True and AC.ligado() is True
    assert AC.a_partir_de() == dt.date(2026, 11, 8)
    monkeypatch.setenv(AC.ENV, "0")
    assert AC.ligado() is False and AC.criar_as_que_faltam() == {"pulou": "desligado"}
    monkeypatch.setenv(AC.ENV, "1")
    monkeypatch.setattr(AC, "A_PARTIR_DE", "")
    assert "sem a data" in AC.criar_as_que_faltam()["pulou"]


def test_a_inspecao_realizada_sem_administrativa_ganha_a_dela(fr, monkeypatch):
    _com_lista(monkeypatch, [_insp(100)])
    r = AC.criar_as_que_faltam(AGORA)
    assert r == {"criadas": [("100", "555")], "erros": [], "faltam": 1}
    asset, plan, kw = fr.criadas[0]
    assert asset is ASSET and kw["id_parent"] == 1000 and kw["id_responsible"] == 4242
    assert plan["id_task_type_main"] == api.TASK_TYPE_MAIN["Administrativa"] == 45606
    assert plan["description"] == "[Tracker 10] - Acompanhamento de chamado STI" and len(plan["subtasks"]) == 1
    nota = kw["note"]
    assert nota.startswith("[CHAMADO] Acompanhamento — STI · ")
    assert "OS de campo: 90 · Inspeção: 100 · Ativo: TST-UFV100-ETKR1.10" in nota
    assert "aguardando a inspeção" not in nota and "  Pergunta fora do modelo: Sim" in nota
    assert "Sem resposta" not in nota and "Verificação sem valor" not in nota
    assert fr.etiquetas == [(5550, [9001])] and {k: AC.criadas()["100"][k] for k in ("folio", "id")} == {"folio": "555", "id": 5550}
    assert AC.criadas()["100"]["quando"]                    # a hora: o registro segura a 2ª só nas 24 h (16/11/2026)


def test_o_que_nao_ganha(fr, monkeypatch):
    regs = [_insp(100, status=1, data_fim=""),                     # em processo: ainda não realizada
            _insp(200, data_fim=HA_10MIN),                         # realizada há 10 min: a vez é do App
            _insp(300, data_fim="2026-11-09T20:00:00"),            # realizada antes da data de início
            _insp(400, status=4),                                  # cancelada
            _insp(500), _adm(501, "500"),                          # já tem administrativa (a do App)
            _insp(600), _adm(601, "600", status=4),                # a administrativa cancelada não conta: ganha outra
            _insp(700, etiquetas=((1, "Outra"),))]                  # Inspeção que não é de garantia
    _com_lista(monkeypatch, regs)
    r = AC.criar_as_que_faltam(AGORA)
    assert [c[0] for c in r["criadas"]] == ["600"]
    # 30 min depois do fim, a de 10 min ganha a dela; a criada não volta
    r = AC.criar_as_que_faltam(AGORA + dt.timedelta(minutes=25))
    assert [c[0] for c in r["criadas"]] == ["200"] and len(fr.criadas) == 2


def test_dia_de_brasilia_na_data_de_inicio(fr, monkeypatch):
    # 02:30 UTC do dia 10 = 23:30 do dia 9 em Brasília: antes da data de início
    _com_lista(monkeypatch, [_insp(100, data_fim="2026-11-10T02:30:00"), _insp(200, data_fim="2026-11-10T03:30:00")])
    assert [c[0] for c in AC.criar_as_que_faltam(AGORA)["criadas"]] == ["200"]


def test_conferida_ao_vivo_antes_de_criar(fr, monkeypatch):
    _com_lista(monkeypatch, [_insp(100)])
    fr.status[1000] = 1                                   # a lista estava velha: o Fracttal diz que voltou a em processo
    r = AC.criar_as_que_faltam(AGORA)
    assert r["criadas"] == [] and r["erros"] == [] and fr.criadas == [] and AC.pendentes() == {}


def test_falhou_fica_pendente_e_tenta_de_novo(fr, monkeypatch):
    _com_lista(monkeypatch, [_insp(100)])
    fr.falhar = True
    r = AC.criar_as_que_faltam(AGORA)
    assert r["criadas"] == [] and "Recusado" in r["erros"][0]
    p = AC.pendentes()["100"]
    assert "Recusado" in p["motivo"] and p["tentativas"] == 1
    # a mesma não é tentada de novo dentro de 1 h; depois sim, e a pendente sai
    assert AC.criar_as_que_faltam(AGORA)["faltam"] == 0
    AC._FEITOS.clear()
    fr.falhar = False
    assert AC.criar_as_que_faltam(AGORA)["criadas"] == [("100", "555")] and AC.pendentes() == {}


def test_o_registro_das_criadas_evita_a_segunda_mesmo_sem_a_lista_saber(fr, monkeypatch):
    _com_lista(monkeypatch, [_insp(100)])
    AC.criar_as_que_faltam(AGORA)
    AC._FEITOS.clear()
    AC.configurar_pasta(AC._PASTA["pasta"])                # o reinício: o registro vem do arquivo
    assert AC.criar_as_que_faltam(AGORA)["faltam"] == 0 and len(fr.criadas) == 1


def test_no_maximo_tantas_por_volta(fr, monkeypatch):
    _com_lista(monkeypatch, [_insp(100 + n) for n in range(5)])
    r = AC.criar_as_que_faltam(AGORA, limite=2)
    assert len(r["criadas"]) == 2 and r["faltam"] == 5


def test_sem_a_lista_central_nada_se_cria(fr, monkeypatch):
    _com_lista(monkeypatch, None)
    assert "lista central" in AC.criar_as_que_faltam(AGORA)["pulou"] and fr.criadas == []


def test_sem_a_equipe_ou_sem_o_ativo_fica_pendente(fr, monkeypatch):
    _com_lista(monkeypatch, [_insp(100), _insp(200, code="TST-FORA-DO-CATALOGO")])
    monkeypatch.delenv("OS_WEB_CHAMADO_RESP_ID")
    AC.criar_as_que_faltam(AGORA)
    assert "OS_WEB_CHAMADO_RESP_ID" in AC.pendentes()["100"]["motivo"] and fr.criadas == []
    monkeypatch.setenv("OS_WEB_CHAMADO_RESP_ID", "4242")
    AC._FEITOS.clear()
    AC.criar_as_que_faltam(AGORA)
    assert "não está no catálogo" in AC.pendentes()["200"]["motivo"] and "100" not in AC.pendentes()


def test_marca_do_titulo():
    assert AC.marca_do_titulo("[Inversor 1.1] - Inspeção para chamado Huawei") == "Huawei"
    assert AC.marca_do_titulo("Inspeção qualquer") == ""


def test_o_quadro_dispara_por_tras_no_maximo_a_cada_10_min(monkeypatch):
    from os_web import rotas_acomp
    rodou = []
    monkeypatch.setattr(rotas_acomp, "_em_segundo_plano", lambda fn: rodou.append(fn))
    monkeypatch.setattr(rotas_acomp.sessao, "jwt_atual", lambda: "jwt")
    monkeypatch.setattr(rotas_acomp.sessao, "email_atual", lambda: "teste@exemplo.invalid")
    monkeypatch.setitem(rotas_acomp._ANDOU, "em", -1e9)
    monkeypatch.setenv(AC.ENV, "0")
    assert rotas_acomp._andar_junto() is False and rodou == []           # desligado: nada
    monkeypatch.setenv(AC.ENV, "1")
    assert rotas_acomp._andar_junto() is True and len(rodou) == 1
    assert rotas_acomp._andar_junto() is False and len(rodou) == 1        # dentro dos 10 min


# ── 16/11/2026: a administrativa que morreu não segura a nova (Levi: "a OS de inspeção gere uma nova administrativa ao
# finalizar, sem choro!") ──────────────────────────────────────────────────────────────────────────────────────────────
class ListaConf(Lista):
    """A lista central com as OS "a conferir" (a faixa não as trouxe: canceladas, apagadas ou só atrasadas)."""
    def __init__(self, regs, conferir=()):
        super().__init__(regs)
        self._conferir = set(conferir)

    def conferir(self, wid):
        return wid in self._conferir


def test_a_administrativa_a_conferir_nao_segura_e_a_leitura_ao_vivo_decide(fr, monkeypatch):
    """A apagada no Fracttal fica "a conferir" na lista até a noite, e a cancelada até uma faixa trazer o status: nas duas
    a lista não segura mais, e quem decide é a leitura ao vivo das filhas da Inspeção."""
    lista = ListaConf([_insp(100), _adm(101, "100"), _insp(200), _adm(201, "200")], conferir={1010, 2010})
    monkeypatch.setattr(AC, "_lista", lambda: lista)
    fr.vivas[2000] = ["201"]                                  # a 201 segue viva no Fracttal: a faixa só atrasou
    r = AC.criar_as_que_faltam(AGORA)
    assert r == {"criadas": [("100", "555")], "erros": [], "faltam": 2}
    assert len(fr.criadas) == 1 and fr.criadas[0][2]["id_parent"] == 1000 and AC.pendentes() == {}


def test_o_registro_das_criadas_nao_segura_a_que_morreu(fr, monkeypatch):
    """A administrativa que este OS Creator criou e foi cancelada, ou apagada (a noite a tirou da lista), não segura a
    nova; fora da lista, nas 24 h depois de criada, segura (a lista ainda pode não tê-la)."""
    dois_dias, duas_horas = (AGORA - dt.timedelta(days=2)).isoformat(), (AGORA - dt.timedelta(hours=2)).isoformat()
    AC._gravar("criadas", {"100": {"folio": "101", "id": 1010, "quando": dois_dias},     # na lista, cancelada
                           "200": {"folio": "201", "id": 2010, "quando": dois_dias},     # fora da lista: apagada
                           "300": {"folio": "301", "id": 3010},                          # registro de antes de 16/11
                           "400": {"folio": "401", "id": 4010, "quando": duas_horas},    # recém-criada: a lista atrasa
                           "500": {"folio": "501", "id": 5010, "quando": dois_dias}})    # na lista e viva
    _com_lista(monkeypatch, [_insp(100), _adm(101, "100", status=4), _insp(200), _insp(300), _insp(400),
                             _insp(500), _adm(501, "500")])
    r = AC.criar_as_que_faltam(AGORA, limite=10)
    assert [c[0] for c in r["criadas"]] == ["100", "200", "300"] and r["erros"] == []
    assert AC.criadas()["200"]["folio"] in ("555", "556", "557") and AC.criadas()["200"]["quando"]


def test_viva_no_fracttal_nao_cria_e_sem_a_leitura_tenta_depois(fr, monkeypatch):
    """A leitura ao vivo acha a administrativa que a lista ainda não trouxe (a do App, criada no fechamento): não cria.
    A leitura que falha também não cria, e não gasta as tentativas: a volta seguinte tenta."""
    _com_lista(monkeypatch, [_insp(100), _insp(200)])
    fr.vivas[1000] = ["777"]
    fr.vivas[2000] = None
    r = AC.criar_as_que_faltam(AGORA)
    assert r == {"criadas": [], "erros": [], "faltam": 2} and fr.criadas == [] and AC.pendentes() == {}
    AC._FEITOS.clear()
    fr.vivas[2000] = []
    assert AC.criar_as_que_faltam(AGORA)["criadas"] == [("200", "555")]


def test_vivas_ao_vivo_le_as_filhas_da_inspecao(monkeypatch):
    pedidos = []

    def rpc(metodo, params):
        pedidos.append((metodo, params))
        return {"data": [
            {"wo_folio": 11, "id_status_work_order": 1, "labels": [{"id": 9001, "description": "CHAMADOS"}]},
            {"wo_folio": 12, "id_status_work_order": 4, "labels": [{"id": 9001, "description": "CHAMADOS"}]},  # cancelada
            {"wo_folio": 13, "id_status_work_order": 2, "labels": [{"id": 5, "description": "Outra"}]},  # clone, não chamado
            {"wo_folio": 14, "id_status_work_order": 3, "labels": [{"id": 9001, "description": ""}]}]}  # pela id da etiqueta
    monkeypatch.setattr(api, "_rpc_call", rpc)
    monkeypatch.setattr(api, "label_id_por_nome", lambda n: 9001)
    assert AC._vivas_ao_vivo(1000) == ["11", "14"]
    assert pedidos[0][0] == api.RPC_WO_LIST
    assert pedidos[0][1]["filter"] == [{"operator": "=", "property": "id_parent_wo", "value": 1000}]

    def recusa(metodo, params):
        raise api.FracttalError("O Fracttal não respondeu (Recusado)")
    monkeypatch.setattr(api, "_rpc_call", recusa)
    assert AC._vivas_ao_vivo(1000) is None

    def expirou(metodo, params):
        raise api.SessionExpired("expirou")
    monkeypatch.setattr(api, "_rpc_call", expirou)
    with pytest.raises(api.SessionExpired):
        AC._vivas_ao_vivo(1000)
