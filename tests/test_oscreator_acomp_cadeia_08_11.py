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


def test_desligado_por_padrao_e_sem_data_nada_se_cria(monkeypatch):
    monkeypatch.delenv(AC.ENV, raising=False)
    monkeypatch.delenv(AC.ENV_DATA, raising=False)
    assert AC.LIGADO_PADRAO is False and AC.A_PARTIR_DE == "" and AC.ligado() is False
    assert AC.criar_as_que_faltam() == {"pulou": "desligado"}
    monkeypatch.setenv(AC.ENV, "1")
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
    assert fr.etiquetas == [(5550, [9001])] and AC.criadas()["100"] == {"folio": "555", "id": 5550}


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
    monkeypatch.delenv(AC.ENV, raising=False)
    assert rotas_acomp._andar_junto() is False and rodou == []           # desligado: nada
    monkeypatch.setenv(AC.ENV, "1")
    assert rotas_acomp._andar_junto() is True and len(rodou) == 1
    assert rotas_acomp._andar_junto() is False and len(rodou) == 1        # dentro dos 10 min
