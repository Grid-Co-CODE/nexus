"""A OS do acompanhamento no Fracttal (Levi, 29/10/2026: "quando eu clico em pegar para acompanhar criar uma OS para a
pessoa que pegou a atividade"; "Ao encaminhar gera uma OS no nome daquela pessoa da engenharia"; o diagnóstico salvo
com o fim da análise responde a subtarefa e o fim preenche o fim da atividade). O Fracttal aqui é falso: o módulo
recebe a api do clone e só chama as funções dela."""
from datetime import date, datetime, timedelta, timezone

import pytest

from nexus.engenharia import os_analise as OA

BRT = timezone(timedelta(hours=-3))
AGORA = datetime(2026, 10, 29, 14, 5, tzinfo=BRT)
ATIVO = {"cod": "ALF100-INVR1.3", "nome": "Inversor 1.3 Sofar 250KTL-HV-PRO", "nivel": "critico", "nFalha": 4, "n7": 2}
FALHAS = [{"quando": AGORA - timedelta(days=d), "os": str(n), "tipo": "Corretiva"}
          for n, d in ((18000, 40), (18001, 12), (18002, 6), (18003, 3), (18004, 1))]


class ApiFalsa:
    TIPO_ANALISE, ANALISE_CLASSIF_1, ANALISE_CLASSIF_2 = "Administrativa", "Programada", "Elétrica"

    class FracttalError(Exception):
        pass

    def __init__(self, etiqueta=True, criada=None, subs=None, conclui=None, status=2, execucoes=None, erro_exec=None):
        self.chamadas, self._etiqueta = [], etiqueta
        self._status, self._execucoes, self._erro_exec = status, execucoes or [], erro_exec
        self._criada = criada if criada is not None else {"ok": True, "code": ATIVO["cod"],
                                                           "os": {"id_work_order": 39001, "wo_folio": 12345}}
        self._subs = subs if subs is not None else [{"id_form_item": 71, "descricao": "Diagnóstico", "tipo": 1,
                                                    "valor": ""}]
        self._conclui = conclui or {"ok": True}

    def _label_id(self, nome):
        self.chamadas.append(("_label_id", nome))
        return 7 if self._etiqueta else None

    def _classif_ids(self, c1, c2):
        return {"id_task_type": 5, "tasks_types_description": c1, "id_task_type_2": 6, "tasks_types_2_description": c2}

    def create_work_orders_bulk(self, assets, description, task_type, subtasks, **k):
        self.chamadas.append(("criar", assets, description, task_type, subtasks, k))
        return [self._criada]

    def id_tarefa_da_os(self, wid):
        self.chamadas.append(("tarefa", wid))
        return 555

    def subtarefas_da_tarefa(self, tid):
        return self._subs

    def salvar_subtarefas(self, wid, tid, valores):
        self.chamadas.append(("subtarefa", wid, tid, valores))
        return {"ok": True}

    def registrar_execucao(self, tid, inicio, fim=None, note="", nome="", validar=True):
        if self._erro_exec:
            raise self.FracttalError(self._erro_exec)
        self.chamadas.append(("execucao", tid, inicio, fim, nome))
        return {"ok": True}

    def status_da_os(self, wid):
        self.chamadas.append(("status", wid))
        return self._status

    def execucoes_da_tarefa(self, tid):
        return self._execucoes

    def concluir_os_analise(self, wid, tid=None, observacao=""):
        self.chamadas.append(("concluir", wid, tid))
        return self._conclui

    def mudar_responsavel(self, wid, idp, nota=None):
        self.chamadas.append(("responsavel", wid, idp, nota))
        return {"ok": True}


def _curto(nome):
    return " ".join(nome.split()[:2])


def test_criar_a_os_de_analise_no_nome_de_quem_pegou():
    api = ApiFalsa()
    os_ = OA.criar(api, ATIVO, {"fid": "11", "nome": "Ana Lima"}, "Ana Lima", AGORA, FALHAS, curto=_curto)
    assert os_ == {"id": 39001, "folio": "12345", "aviso": ""}
    (_, assets, titulo, tipo, subs, k), = [c for c in api.chamadas if c[0] == "criar"]
    assert assets == ["ALF100-INVR1.3"] and titulo == "[Inversor 1.3] - Análise de recorrência de falhas"
    assert tipo == "Administrativa" and subs == ["Diagnóstico"] and k["etiqueta_ids"] == [7]
    assert k["id_responsible"] == 11 and k["responsible_name"] == "Ana Lima"
    assert k["tipo"] == {"id_c1": 5, "desc_c1": "Programada", "id_c2": 6, "desc_c2": "Elétrica"}
    # a data do evento é a da 2ª falha dos 30 dias (a que acendeu o sinal); a de 40 dias atrás fica fora da janela
    assert k["event_date"] == FALHAS[2]["quando"]
    nota = k["note"]
    assert "Assumida em 29/10/2026 às 14:05 por Ana Lima" in nota and "4 falhas em 30 dias" in nota
    assert "2 em 7 dias" in nota and "#18001" in nota and "#18000" not in nota


def test_encaminhar_um_ativo_livre_cria_a_os_no_nome_de_quem_recebe():
    api = ApiFalsa()
    OA.criar(api, ATIVO, {"fid": "12", "nome": "Beto Souza"}, "Ana Lima", AGORA, FALHAS, curto=_curto)
    (_, _a, _t, _tp, _s, k), = [c for c in api.chamadas if c[0] == "criar"]
    assert k["id_responsible"] == 12 and k["responsible_name"] == "Beto Souza"
    assert "Encaminhada em 29/10/2026 às 14:05 por Ana Lima para Beto Souza" in k["note"]


def test_sem_a_etiqueta_cria_e_avisa():
    os_ = OA.criar(ApiFalsa(etiqueta=False), ATIVO, {"fid": "11", "nome": "Ana Lima"}, "Ana Lima", AGORA, FALHAS,
                   curto=_curto)
    assert os_["id"] == 39001 and "ENGENHARIA" in os_["aviso"]


@pytest.mark.parametrize("criada, msg", [
    ({"ok": False, "code": "X", "erro": "ativo não encontrado no cache."}, "ativo não encontrado"),
    ({"ok": True, "code": "X", "os": {"id_task": 9, "aviso": "tarefa criada, mas falhou virar WO: x"}}, "não virou OS"),
])
def test_o_fracttal_que_nao_cria_a_os_e_falha(criada, msg):
    with pytest.raises(OA.Falhou, match=msg):
        OA.criar(ApiFalsa(criada=criada), ATIVO, {"fid": "11", "nome": "Ana Lima"}, "Ana Lima", AGORA, FALHAS,
                 curto=_curto)


def test_quem_nao_tem_o_id_do_fracttal_nao_cria():
    with pytest.raises(OA.Falhou, match="Fracttal"):
        OA.criar(ApiFalsa(), ATIVO, {"fid": "", "nome": "Ana Lima"}, "Ana Lima", AGORA, FALHAS, curto=_curto)


def test_encerrar_responde_a_subtarefa_lanca_o_fim_e_conclui():
    api = ApiFalsa()
    feito = OA.encerrar(api, 39001, "Disjuntor", date(2026, 10, 20), date(2026, 10, 28), "Ana Lima", agora=AGORA)
    assert [c[0] for c in api.chamadas] == ["status", "tarefa", "subtarefa", "execucao", "concluir"]
    (_, wid, tid, valores), = [c for c in api.chamadas if c[0] == "subtarefa"]
    assert (wid, tid, valores) == (39001, 555, [{"id_form_item": 71, "valor": "Disjuntor", "tipo": 1}])
    (_, _tid, ini, fim, nome), = [c for c in api.chamadas if c[0] == "execucao"]
    assert ini == datetime(2026, 10, 20, 8, 0, tzinfo=BRT) and fim == datetime(2026, 10, 28, 18, 0, tzinfo=BRT)
    assert nome == "Ana Lima" and feito == ["subtarefa", "execucao", "concluida"]


def test_encerrar_hoje_nao_lanca_o_fim_no_futuro():
    api = ApiFalsa()
    OA.encerrar(api, 39001, "Disjuntor", date(2026, 10, 29), date(2026, 10, 29), "Ana Lima", agora=AGORA)
    (_, _tid, ini, fim, _n), = [c for c in api.chamadas if c[0] == "execucao"]
    assert ini == datetime(2026, 10, 29, 8, 0, tzinfo=BRT) and fim == AGORA


def test_subtarefa_ja_respondida_com_o_mesmo_diagnostico_nao_se_regrava():
    api = ApiFalsa(subs=[{"id_form_item": 71, "descricao": "Diagnóstico", "tipo": 1, "valor": "Disjuntor"}])
    feito = OA.encerrar(api, 39001, "Disjuntor", date(2026, 10, 20), date(2026, 10, 28), "Ana Lima", agora=AGORA)
    assert "subtarefa" not in [c[0] for c in api.chamadas] and feito == ["execucao", "concluida"]


def test_os_que_nao_conclui_falha_com_o_motivo():
    with pytest.raises(OA.Falhou, match="cronômetro"):
        OA.encerrar(ApiFalsa(conclui={"ok": False, "erro": "cronômetro ainda aberto."}), 39001, "Disjuntor",
                    date(2026, 10, 20), date(2026, 10, 28), "Ana Lima", agora=AGORA)


def test_trocar_o_responsavel_da_os():
    api = ApiFalsa()
    OA.trocar_responsavel(api, 39001, "12")
    assert ("responsavel", 39001, 12, None) in api.chamadas
    with pytest.raises(OA.Falhou, match="Fracttal"):
        OA.trocar_responsavel(api, 39001, "")


def test_linha_da_nota_do_encaminhar():
    assert OA.linha_encaminhou("Ana Lima", "Beto Souza", AGORA) == \
        "[29/10/2026 14:05] Ana Lima (Engenharia): encaminhou a análise para Beto Souza."


# ── o livro do acompanhamento guarda a OS (os_id, os_folio no fim do cabeçalho) ─────────────────────────────────────
from pg_falso import ApiPGFalsa  # noqa: E402

from nexus.cadastro.cifra import gerar_chave  # noqa: E402
from nexus.engenharia import acompanhamento as AC  # noqa: E402

ANA = {"email": "ana.lima@gridco.com.br", "nome": "Ana Lima"}
BETO = {"email": "beto.souza@gridco.com.br", "nome": "Beto Souza"}
SINAL = {"cod": "ALF100-INVR1.3", "usina_id": 7, "usina_ligada_por": "de-para do Fracttal", "nivel": "critico",
         "nFalha": 4, "n7": 2}


@pytest.fixture
def banco(app):
    app.config.update(GRIDCO_DB_API="http://pg.falso", NEXUS_CHAVE_CADASTRO=gerar_chave(),
                      NEXUS_PESSOA_HMAC="hmac-teste", GRIDCO_SQL_TOKEN="tk")
    api = ApiPGFalsa()
    app.extensions["nexus_dados_sessao"] = api
    AC.limpar()
    with app.app_context():
        yield api
    AC.limpar()
    app.extensions.pop("nexus_dados_sessao", None)


def _um():
    (a,) = AC.estado(AC.ler(forcar=True)["eventos"]).values()
    return a


def test_as_colunas_da_os_entram_no_fim_do_cabecalho():
    assert AC.CAB_EVENTO[-3:-1] == ("os_id", "os_folio") and AC.CAB_EVENTO[:18][-1] == "dados_cifrados"


def test_pegar_com_a_os_guarda_o_id_e_o_numero(banco):
    AC.pegar(SINAL, ANA, True, os={"id": 39001, "folio": "12345"})
    (l,) = banco.linhas(AC.LIVRO, AC.ABA_EVENTO)
    assert (l["os_id"], l["os_folio"]) == (39001, "12345")
    a = _um()
    assert a["os_id"] == 39001 and a["os_folio"] == "12345"


def test_acompanhamento_sem_os_segue_sem_ela(banco):
    AC.pegar(SINAL, ANA, True)
    a = _um()
    assert a["os_id"] is None and a["os_folio"] == ""


def test_encaminhar_o_ativo_livre_com_a_os_nova(banco):
    pessoas = [{"hmac": AC.codigo(BETO), "nome": "Beto Souza", "fid": "12"}]
    AC.encaminhar(SINAL, AC.codigo(BETO), ANA, True, pessoas, os={"id": 39002, "folio": "12346"})
    a = _um()
    assert a["responsavel"]["nome"] == "Beto Souza" and a["os_folio"] == "12346"


# ── a ponte: o Pegar, o Encaminhar, o Encerrar e o comentário pela sessão do Fracttal da pessoa ─────────────────────
# a Confiabilidade de prova do acompanhamento (IBI200-INVR1.3 aberto com Ana Lima, de antes, SEM OS; IBI200-INV02 livre
# com sinal; IBI200-TRK07 encerrado) e o login de mentira do Fracttal do Quadro da equipe; o api do clone é falso
from test_engenharia_acompanhamento import SAME, _aid_de, _como, tela  # noqa: E402,F401
from test_engenharia_os_quadro import _login_do_fracttal  # noqa: E402

PONTE = "/os/_nexus/engenharia/acompanhamento"


@pytest.fixture
def fracttal(tela, app, monkeypatch):
    pytest.importorskip("PyQt6")
    from nexus.torres.oscreator import ponte
    ponte.clone(app)
    import api as os_api
    monkeypatch.setattr(AC, "pessoas_da_engenharia", lambda: [
        {"hmac": AC.codigo(ANA), "nome": "Ana Lima", "fid": "11"},
        {"hmac": AC.codigo(BETO), "nome": "Beto Souza", "fid": "12"}])
    falso = ApiFalsa()
    for nome in ("_label_id", "_classif_ids", "create_work_orders_bulk", "id_tarefa_da_os", "subtarefas_da_tarefa",
                 "salvar_subtarefas", "registrar_execucao", "concluir_os_analise", "mudar_responsavel", "status_da_os",
                 "execucoes_da_tarefa"):
        monkeypatch.setattr(os_api, nome, getattr(falso, nome))
    notas = []
    monkeypatch.setattr(os_api, "get_os_detalhes", lambda wid: {"notas": "Nota antiga", "tarefas": [{"id": 1}],
                                                               "cancel_motivo": "", "cancel_nota": ""})
    from nexus.torres.oscreator import ponte as P

    def editar(wid, nota):
        # a nota da OS é escrita sob a trava das notas: um comentário junto não apaga o outro (revisão de 29/10/2026)
        falso.sob_trava.append(P._trava_nota.locked())
        notas.append((wid, nota))
        return {"ok": True}
    monkeypatch.setattr(os_api, "editar_nota_os", editar)
    falso.notas, falso.sob_trava = notas, []
    P._OS_SEM_LIVRO.clear()
    yield falso
    P._OS_SEM_LIVRO.clear()


def _pela_microsoft(cliente, usuario):
    """Quem entrou pela conta Microsoft: a sessão do Nexus não depende da do Fracttal (quem entrou pelo Fracttal sempre
    tem o cookie do OS Creator; sem ele, o portão já o tira do Nexus)."""
    import time
    with cliente.session_transaction() as s:
        s["logado"], s["admin"], s["usuario"] = True, False, usuario
        s["via"], s["ms_ate"] = "microsoft", time.time() + 6 * 3600
    return cliente


def _feitas(falso, tipo):
    return [c for c in falso.chamadas if c[0] == tipo]


def _post(cliente, caminho, **dados):
    return cliente.post(PONTE + caminho, data=dados, headers=SAME)


def test_pegar_pela_ponte_cria_a_os_e_o_acompanhamento(fracttal, tela, cliente, app):
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    r = _post(cliente, "/pegar", cod="IBI200-INV02")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "OS 12345" in html and "agora este ativo está com você" in html.lower()
    (_, assets, titulo, _t, subs, k), = _feitas(fracttal, "criar")
    assert assets == ["IBI200-INV02"] and titulo.endswith("] - Análise de recorrência de falhas")
    assert subs == ["Diagnóstico"] and k["id_responsible"] == 11
    a = next(a for a in AC.estado(AC.ler(forcar=True)["eventos"]).values() if a["cod"] == "IBI200-INV02")
    assert a["aberto"] and a["os_folio"] == "12345" and a["responsavel"]["nome"] == "Ana Lima"


def test_pegar_sem_o_login_do_fracttal_nao_cria_nada(fracttal, tela, cliente):
    _pela_microsoft(cliente, ANA)
    html = _post(cliente, "/pegar", cod="IBI200-INV02").get_data(as_text=True)
    assert "Entrar pelo Fracttal" in html and "/os/login?next=" in html
    assert _feitas(fracttal, "criar") == [] and _aid_de("IBI200-INV02") is None


def test_o_fracttal_que_nao_cria_a_os_nao_grava_no_nexus(fracttal, tela, cliente, app):
    fracttal._criada = {"ok": False, "code": "IBI200-INV02", "erro": "ativo não encontrado no cache."}
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    html = _post(cliente, "/pegar", cod="IBI200-INV02").get_data(as_text=True)
    assert "O Fracttal não criou a OS" in html and _aid_de("IBI200-INV02") is None


def test_encaminhar_o_ativo_livre_cria_a_os_de_quem_recebe(fracttal, tela, cliente, app):
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    html = _post(cliente, "/encaminhar", cod="IBI200-INV02", para=AC.codigo(BETO), livre="1").get_data(as_text=True)
    assert "Encaminhado para Beto Souza" in html
    (_, _a, _t, _tp, _s, k), = _feitas(fracttal, "criar")
    assert k["id_responsible"] == 12 and "por Ana Lima para Beto Souza" in k["note"]


def test_encaminhar_com_a_os_troca_o_responsavel_e_escreve_na_nota(fracttal, tela, cliente, app):
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    _post(cliente, "/pegar", cod="IBI200-INV02")
    html = _post(cliente, "/encaminhar", cod="IBI200-INV02", para=AC.codigo(BETO)).get_data(as_text=True)
    assert "Encaminhado para Beto Souza" in html and len(_feitas(fracttal, "criar")) == 1
    assert ("responsavel", 39001, 12, None) in fracttal.chamadas
    (wid, nota), = fracttal.notas
    assert wid == 39001 and nota.startswith("Nota antiga\n") and "encaminhou a análise para Beto Souza" in nota


def test_encerrar_com_a_os_responde_lanca_o_fim_e_conclui(fracttal, tela, cliente, app):
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    _post(cliente, "/pegar", cod="IBI200-INV02")
    aid = _aid_de("IBI200-INV02")
    hoje = datetime.now(BRT).date().isoformat()
    html = _post(cliente, f"/{aid}/salvar", cod="IBI200-INV02", inicio=hoje, fim=hoje, diagnostico="2")         .get_data(as_text=True)
    assert "Encerrado" in html and "concluída no Fracttal" in html
    assert [c[0] for c in fracttal.chamadas if c[0] in ("subtarefa", "execucao", "concluir")] ==         ["subtarefa", "execucao", "concluir"]
    (_, _w, _tid, valores), = _feitas(fracttal, "subtarefa")
    assert valores[0]["valor"] == "Disjuntor"
    assert not AC.estado(AC.ler(forcar=True)["eventos"])[aid]["aberto"]


def test_encerrar_que_o_nexus_recusaria_nao_vai_ao_fracttal(fracttal, tela, cliente, app):
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    _post(cliente, "/pegar", cod="IBI200-INV02")
    aid = _aid_de("IBI200-INV02")
    hoje = datetime.now(BRT).date().isoformat()
    html = _post(cliente, f"/{aid}/salvar", cod="IBI200-INV02", inicio=hoje, fim=hoje, diagnostico="0")         .get_data(as_text=True)
    assert "escolha o diagnóstico" in html and _feitas(fracttal, "concluir") == []
    assert AC.estado(AC.ler(forcar=True)["eventos"])[aid]["aberto"]


def test_comentario_com_a_os_vai_para_a_nota(fracttal, tela, cliente, app):
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    _post(cliente, "/pegar", cod="IBI200-INV02")
    aid = _aid_de("IBI200-INV02")
    html = _post(cliente, f"/{aid}/comentar", cod="IBI200-INV02", texto="Medir o isolamento").get_data(as_text=True)
    assert "nota da OS 12345" in html and "Medir o isolamento" in html
    (wid, nota), = fracttal.notas
    assert wid == 39001 and "Ana Lima (Engenharia): Medir o isolamento" in nota


def test_acompanhamento_de_antes_sem_os_segue_so_no_nexus(fracttal, tela, cliente):
    _pela_microsoft(cliente, ANA)
    aid = _aid_de("IBI200-INVR1.3")
    html = _post(cliente, f"/{aid}/comentar", cod="IBI200-INVR1.3", texto="Sem OS ainda").get_data(as_text=True)
    # desde 30/10/2026 o comentário só vai com a OS (Levi: "só pode comentar com OS criada!"): a gaveta oferece o Gerar OS
    assert "gere a OS" in html and "Gerar OS" in html and fracttal.notas == []


def test_de_outro_site_a_ponte_nao_faz_nada(fracttal, tela, cliente, app):
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    r = cliente.post(PONTE + "/pegar", data={"cod": "IBI200-INV02"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and _feitas(fracttal, "criar") == []


def test_a_gaveta_manda_as_acoes_para_a_ponte(fracttal, tela, cliente):
    html = _como(cliente, ANA).get("/t/engenharia/confiabilidade").get_data(as_text=True)
    assert f'action="{PONTE}/pegar"' in html and f'action="{PONTE}/encaminhar"' in html


# ── a revisão independente de 29/10/2026 ────────────────────────────────────────────────────────────────────────────
def test_encerrar_a_os_ja_concluida_no_fracttal_nao_escreve_la():
    """O engenheiro concluiu a OS no próprio Fracttal (ou a tentativa de antes concluiu e o livro falhou): o encerrar
    segue para o Nexus sem escrever lá."""
    api = ApiFalsa(status=3)
    feito = OA.encerrar(api, 39001, "Disjuntor", date(2026, 10, 20), date(2026, 10, 28), "Ana Lima", agora=AGORA)
    assert feito == ["ja_concluida"] and [c[0] for c in api.chamadas] == ["status"]
    assert OA.encerrar(ApiFalsa(status=4), 39001, "Disjuntor", date(2026, 10, 20), date(2026, 10, 28), "Ana Lima",
                       agora=AGORA) == ["ja_cancelada"]


def test_encerrar_sem_a_subtarefa_diagnostico_falha_antes_de_concluir():
    api = ApiFalsa(subs=[])
    with pytest.raises(OA.Falhou, match="Diagnóstico"):
        OA.encerrar(api, 39001, "Disjuntor", date(2026, 10, 20), date(2026, 10, 28), "Ana Lima", agora=AGORA)
    assert not [c for c in api.chamadas if c[0] in ("execucao", "concluir")]


def test_encerrar_de_novo_nao_lanca_outra_execucao():
    """A conclusão que o Fracttal recusou (perfil sem permissão, cronômetro de outra pessoa aberto): tentar de novo não
    lança uma execução a cada vez."""
    api = ApiFalsa(execucoes=[{"id": 1, "done": True}])
    feito = OA.encerrar(api, 39001, "Disjuntor", date(2026, 10, 20), date(2026, 10, 28), "Ana Lima", agora=AGORA)
    assert "execucao" not in [c[0] for c in api.chamadas] and feito == ["subtarefa", "concluida"]


def test_o_erro_de_os_fechada_com_espacos_tambem_vale():
    # o `registrar_execucao` do clone troca o "_" por espaço na mensagem do Fracttal
    api = ApiFalsa(erro_exec="O Fracttal recusou o registro: ERROR WO FINISHED BY OTHER USER")
    feito = OA.encerrar(api, 39001, "Disjuntor", date(2026, 10, 20), date(2026, 10, 28), "Ana Lima", agora=AGORA)
    assert feito[-1] == "ja_concluida" and "concluir" not in [c[0] for c in api.chamadas]


def test_encaminhar_com_a_os_nova_recusa_se_o_ativo_ganhou_dono(banco):
    AC.pegar(SINAL, ANA, True)
    pessoas = [{"hmac": AC.codigo(BETO), "nome": "Beto Souza", "fid": "12"}]
    with pytest.raises(AC.Recusada, match="dono"):
        AC.encaminhar(SINAL, AC.codigo(BETO), ANA, True, pessoas, os={"id": 39002, "folio": "12346"})


def _livro_fora(forcar=False):
    return {"eventos": [], "diagnosticos": [], "lido_em": None, "erro": "ConnectionError: fora"}


def test_pegar_com_o_livro_ilegivel_nao_vai_ao_fracttal(fracttal, tela, cliente, app, monkeypatch):
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    monkeypatch.setattr(AC, "ler", _livro_fora)
    html = _post(cliente, "/pegar", cod="IBI200-INV02").get_data(as_text=True)
    assert "Não consegui ler os acompanhamentos" in html and _feitas(fracttal, "criar") == []


def test_o_livro_que_falha_depois_do_fracttal_nao_cria_outra_os_na_tentativa_seguinte(fracttal, tela, cliente, app,
                                                                                      monkeypatch):
    import requests
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    original, vezes = AC.pegar, []

    def pegar(*a, **k):
        vezes.append(1)
        if len(vezes) == 1:
            raise requests.ConnectionError("banco fora")
        return original(*a, **k)
    monkeypatch.setattr(AC, "pegar", pegar)
    html = _post(cliente, "/pegar", cod="IBI200-INV02").get_data(as_text=True)
    assert "A OS 12345 já está no Fracttal" in html and "a mesma OS" in html
    html = _post(cliente, "/pegar", cod="IBI200-INV02").get_data(as_text=True)
    assert "OS 12345" in html and len(_feitas(fracttal, "criar")) == 1
    a = next(a for a in AC.estado(AC.ler(forcar=True)["eventos"]).values() if a["cod"] == "IBI200-INV02")
    assert a["os_folio"] == "12345"


def test_dois_pegando_o_mesmo_ativo_ao_mesmo_tempo(fracttal, tela, cliente, app):
    from nexus.torres.oscreator import ponte as P
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    with P._trava_do_ativo("IBI200-INV02"):
        html = _post(cliente, "/pegar", cod="IBI200-INV02").get_data(as_text=True)
    assert "agora mesmo" in html and _feitas(fracttal, "criar") == []


def test_comentario_e_encaminhar_em_os_concluida_ficam_so_no_nexus(fracttal, tela, cliente, app):
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    _post(cliente, "/pegar", cod="IBI200-INV02")
    aid = _aid_de("IBI200-INV02")
    fracttal._status = 3
    html = _post(cliente, f"/{aid}/comentar", cod="IBI200-INV02", texto="Depois de concluída").get_data(as_text=True)
    assert "só no Nexus" in html and "concluída no Fracttal" in html and fracttal.notas == []
    html = _post(cliente, "/encaminhar", cod="IBI200-INV02", para=AC.codigo(BETO)).get_data(as_text=True)
    assert "Encaminhado para Beto Souza" in html and "concluída no Fracttal" in html
    assert not _feitas(fracttal, "responsavel")


def test_a_linha_do_encaminhar_vai_a_nota_sob_a_trava(fracttal, tela, cliente, app):
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    _post(cliente, "/pegar", cod="IBI200-INV02")
    _post(cliente, "/encaminhar", cod="IBI200-INV02", para=AC.codigo(BETO))
    assert fracttal.sob_trava == [True]


def test_encerrar_com_o_livro_ilegivel_e_recusado(fracttal, tela, cliente, app, monkeypatch):
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    _post(cliente, "/pegar", cod="IBI200-INV02")
    aid = _aid_de("IBI200-INV02")
    monkeypatch.setattr(AC, "ler", _livro_fora)
    hoje = datetime.now(BRT).date().isoformat()
    html = _post(cliente, f"/{aid}/salvar", cod="IBI200-INV02", inicio=hoje, fim=hoje, diagnostico="2") \
        .get_data(as_text=True)
    assert "Não consegui ler os acompanhamentos" in html and _feitas(fracttal, "concluir") == []


def test_a_rota_antiga_nao_mexe_no_acompanhamento_com_os(fracttal, tela, cliente, app):
    """A página aberta antes do deploy posta nas rotas antigas: com a OS, encerrar, comentar e encaminhar por elas
    deixariam o Fracttal para trás."""
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    _post(cliente, "/pegar", cod="IBI200-INV02")
    aid = _aid_de("IBI200-INV02")
    hoje = datetime.now(BRT).date().isoformat()
    antiga = "/t/engenharia/confiabilidade/acompanhamento"
    for caminho, dados in ((f"/{aid}/salvar", {"inicio": hoje, "fim": hoje, "diagnostico": "2"}),
                           (f"/{aid}/comentar", {"texto": "Pela rota antiga"}),
                           ("/encaminhar", {"para": AC.codigo(BETO)})):
        html = cliente.post(antiga + caminho, data=dict(dados, cod="IBI200-INV02"), headers=SAME).get_data(as_text=True)
        assert "recarregue a página" in html, caminho
    a = AC.estado(AC.ler(forcar=True)["eventos"])[aid]
    assert a["aberto"] and a["comentarios"] == [] and a["responsavel"]["nome"] == "Ana Lima"
    # mudar só o início ou o diagnóstico pela rota antiga segue (não mexe no Fracttal)
    html = cliente.post(antiga + f"/{aid}/salvar", data={"cod": "IBI200-INV02", "inicio": hoje, "diagnostico": "1"},
                        headers=SAME).get_data(as_text=True)
    assert "Salvo." in html


def test_salvar_diagnostico_nao_e_botao_de_enviar_o_formulario(fracttal, tela, cliente, app):
    """Enter num campo de data, ou um navegador sem o `submitter`, mandariam o formulário pelo 1º botão de enviar: o
    "Salvar diagnóstico" vinha antes do Salvar (e o Salvar com o fim conclui a OS)."""
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    html = _post(cliente, "/pegar", cod="IBI200-INV02").get_data(as_text=True)
    assert "formaction=" not in html and 'type="button" class="gc-btn gc-btn--contorno eg-btn-peq" data-eg-acao=' in html
