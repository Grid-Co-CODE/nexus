"""O "Retornar para responsável" no card da OS (Levi, 10/11/2026: "Esses proxys servem para tirar uma OS de verificação e
devolver para OSs em processo, tem que ter essa opção no card da OS no Histórico de OSs"; "Só quem criou ou o
supervisor/responsável/gestor de contrato"). A OS Em Verificação volta para Em Processo pelo
`tasks.work_orders_change_status` com `verify_triggers` False, como a tela do Fracttal manda; quem criou (o `id_created_by`
do cabeçalho), o administrador e os papéis da usina no cadastro do Nexus (os da assinatura da PT) podem. O Fracttal e o
cadastro são de mentira; pessoas, usinas e números inventados."""
import pytest

from test_oscreator_anexo_incluir import WID, _cliente
from test_oscreator_card_tarefas import Fracttal, _card, _item, _tarefa  # noqa: F401
from test_oscreator_solic_pcm import WEB, api  # noqa: F401

from nexus.torres.oscreator import ponte, retornar_os

from os_web import rotas_os_acoes  # noqa: E402

EU_CONTA, OUTRA_CONTA = 501, 777


class Os:
    """A OS no Fracttal de mentira: o status, quem criou e o ativo; `calado` = o Fracttal aceita e não muda."""

    def __init__(self, st=2, criador=EU_CONTA, calado=False):
        self.st, self.criador, self.calado, self.pedidos = st, criador, calado, []

    def cab(self, wid):
        return {"id_status_work_order": self.st, "id_created_by": self.criador, "wo_folio": "15900"}

    def mudar(self, wid, st, verificar_gatilhos=True):
        self.pedidos.append((wid, st, verificar_gatilhos))
        if not self.calado:
            self.st = st
        return {"ok": True, "status": "Em Processo"}


@pytest.fixture
def os_(monkeypatch):
    from os_web import rotas_acomp
    o = Os()
    monkeypatch.setattr(api, "_cabecalho_os", o.cab)
    monkeypatch.setattr(api, "_current_user_ids", lambda: (9001, EU_CONTA))
    monkeypatch.setattr(api, "_leitura_da_os", lambda metodo, wid, params, usar_guardada=True:
                        [{"code_item": "ABC100-INV1"}, {"code_item": "ABC100-INV1"}])
    monkeypatch.setattr(api, "mudar_status_os", o.mudar)
    monkeypatch.setattr(api, "status_da_os", lambda wid: o.st)
    monkeypatch.setattr(rotas_acomp, "_ajustar", lambda wid, campos=None, ticket=None: None)
    return o


def _nexus(resposta, admin=False, vistos=None):
    """O gancho que a ponte põe no pedido: diz o papel de quem pede nas usinas dos códigos."""
    def decidir(codigos):
        if vistos is not None:
            vistos.append(list(codigos))
        return resposta
    decidir.admin = admin
    return decidir


def _post(gancho=None):
    env = {rotas_os_acoes.RETORNAR: gancho} if gancho else {}
    return _cliente().post(f"/os/api/os/{WID}/retornar", json={"folio": "15900"}, environ_base=env)


def test_quem_criou_retorna_e_vai_sem_os_gatilhos(os_):
    r = _post()
    assert r.status_code == 200 and "OS 15900 retornou para o responsável" in r.get_json()["mensagem"]
    assert os_.pedidos == [(WID, 1, False)] and os_.st == 1


def test_quem_nao_criou_fora_do_nexus_nao_retorna(os_):
    os_.criador = OUTRA_CONTA
    r = _post()
    assert r.status_code == 403 and "Só quem criou" in r.get_json()["erro"] and not os_.pedidos


def test_o_papel_na_usina_retorna_com_os_codigos_dos_ativos(os_):
    os_.criador, vistos = OUTRA_CONTA, []
    r = _post(_nexus({"pode": True, "papel": "supervisor de campo"}, vistos=vistos))
    assert r.status_code == 200 and os_.pedidos == [(WID, 1, False)]
    assert vistos == [["ABC100-INV1"]]                                  # o código uma vez, mesmo em duas tarefas


def test_sem_papel_diz_quem_pode(os_):
    os_.criador = OUTRA_CONTA
    r = _post(_nexus({"pode": False, "texto": "o responsável UFV (Pessoa Um) ou o gestor de contrato (Pessoa Dois)"}))
    erro = r.get_json()["erro"]
    assert r.status_code == 403 and not os_.pedidos
    assert erro == ("Quem retorna esta OS para o responsável: quem a criou, o responsável UFV (Pessoa Um) ou o gestor de "
                    "contrato (Pessoa Dois).")


def test_o_administrador_passa_sem_ler_o_cadastro(os_):
    os_.criador, vistos = OUTRA_CONTA, []
    r = _post(_nexus({"pode": False}, admin=True, vistos=vistos))
    assert r.status_code == 200 and not vistos


def test_o_cadastro_fora_fecha_e_diz(os_):
    os_.criador = OUTRA_CONTA
    r = _post(_nexus({"pode": False, "erro": "Não consegui ler o cadastro das usinas agora"}))
    assert r.status_code == 403 and "Não consegui ler o cadastro" in r.get_json()["erro"]


def test_so_a_os_em_verificacao_volta(os_):
    os_.st = 3
    r = _post()
    assert r.status_code == 400 and "concluída" in r.get_json()["erro"] and not os_.pedidos


def test_o_fracttal_que_aceita_calado_e_dito(os_):
    os_.calado = True
    r = _post()
    assert r.status_code == 502 and "seguiu em verificação" in r.get_json()["erro"]


def test_o_card_pergunta_antes_de_mostrar(os_):
    c = _cliente()
    assert c.get(f"/os/api/os/{WID}/retornar").get_json()["pode"] is True
    os_.st = 1                                                           # em processo: não há o que retornar
    assert c.get(f"/os/api/os/{WID}/retornar").get_json()["pode"] is False
    os_.st, os_.criador = 2, OUTRA_CONTA                                 # quem não pode: o botão segue escondido
    assert c.get(f"/os/api/os/{WID}/retornar").get_json()["pode"] is False
    assert not os_.pedidos


def test_a_troca_de_status_manda_o_que_a_tela_do_fracttal_manda(monkeypatch):
    import os_estado
    vistos = []
    monkeypatch.setattr(api, "_rpc_call", lambda metodo, params: vistos.append((metodo, params)) or {"success": True})
    assert os_estado.mudar_status_os(40000001, 1, verificar_gatilhos=False)["ok"]
    assert vistos == [("tasks.work_orders_change_status", {"id_work_order": 40000001, "id_status_work_order": 1,
                                                           "verify_triggers": False, "update_readings_after": False})]
    os_estado.mudar_status_os(40000001, 2)                               # o Enviar para verificação segue como era
    assert vistos[-1][1]["verify_triggers"] is True


# ── o cadastro: os papéis da usina do ativo (os mesmos da assinatura da PT) ──
class Lig:
    def usina(self, texto, codigo):
        return (10, "código do ativo") if str(codigo).startswith("ABC100") else (None, None)


class Base:
    """O `visao._Base` de mentira: uma usina (10) na região 1, com Responsável UFV 21, Supervisor 22 e gestor 23."""

    def __init__(self, quem=None):
        self.lig, self.quem = Lig(), quem
        self.regiao = {1: {"nome": "Região Teste", "supervisor_id": 22, "coordenador_id": 24}}
        self.por_id = {10: {"usina_id": 10, "responsavel_om_id": 21, "gestor_contrato_id": 23}}
        self.pessoas = []

    def regiao_da_usina(self, uid):
        return 1 if uid == 10 else None

    def pessoa_do_login(self, email, nome=""):
        return self.quem

    def nome_da_pessoa(self, pid, papel="Pessoa"):
        return {21: "Pessoa Um", 22: "Pessoa Dois", 23: "Pessoa Tres"}.get(pid, f"{papel} {pid}")


@pytest.mark.parametrize("quem,papel", [(21, "responsável UFV"), (22, "supervisor de campo"), (23, "gestor de contrato")])
def test_cada_papel_da_usina_pode(quem, papel):
    assert retornar_os.papel_nas_usinas(["ABC100-INV1"], "x@exemplo.invalid", b=Base(quem)) == {"pode": True,
                                                                                                "papel": papel}


def test_quem_nao_tem_papel_ve_quem_pode():
    r = retornar_os.papel_nas_usinas(["ABC100-INV1"], "x@exemplo.invalid", b=Base(99))
    assert r == {"pode": False, "texto": "o responsável UFV (Pessoa Um), o supervisor de campo (Pessoa Dois) ou o gestor "
                                         "de contrato (Pessoa Tres)"}
    # o coordenador só entra com a vaga de supervisor aberta (a regra da PT)
    assert retornar_os.papel_nas_usinas(["ABC100-INV1"], "x@exemplo.invalid", b=Base(24))["pode"] is False


def test_o_ativo_que_nao_liga_a_usina_diz_por_que():
    r = retornar_os.papel_nas_usinas(["XYZ9-INV1"], "x@exemplo.invalid", b=Base(21))
    assert r["pode"] is False and "não liga a uma usina do cadastro" in r["texto"]


def test_a_ponte_liga_o_gancho_so_na_rota_de_retornar():
    assert retornar_os.CHAVE == rotas_os_acoes.RETORNAR
    assert ponte._ROTA_RETORNAR.fullmatch("api/os/40466589/retornar")
    assert not ponte._ROTA_RETORNAR.fullmatch("api/os/40466589/verificacao")
    fonte = open(ponte.__file__, encoding="utf-8").read()
    assert "environ[retornar_os.CHAVE] = retornar_os.no_pedido(app)" in fonte


def test_o_botao_so_na_os_em_verificacao_e_escondido_ate_a_rota_dizer(monkeypatch):
    monkeypatch.setattr(api, "_rpc_call", Fracttal([_tarefa(1)], [_item(1, 1)]).rpc)
    h = _card("Em Verificação")
    rodape = h[h.index('<footer class="det-foot">'):h.index("</footer>")]
    assert ('data-acao="retornar" data-retornar-pode="/os/api/os/%d/retornar" hidden' % WID) in rodape
    assert ">Retornar para responsável</button>" in rodape and 'data-acao="verificacao"' not in rodape
    assert 'data-dlg="retornar"' in h
    assert 'data-acao="retornar"' not in _card("Em Processo")
    js = (WEB / "static" / "os_acoes.js").read_text(encoding="utf-8")
    assert "retornarPode(d);" in js and "'/os/api/os/' + d.dataset.wid + '/retornar'" in js
