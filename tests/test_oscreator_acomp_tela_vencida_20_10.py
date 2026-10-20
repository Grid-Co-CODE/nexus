"""A tela de um chamado não relê a lista inteira na frente de quem abriu (20/10/2026). Raio-X das 09:56: `GET
/os/chamados/acompanhamento/16574` ficou 39 s em `api._meta_tarefa_por_os`, relendo a lista de TODAS as OS de
acompanhamento (com as tarefas de cada uma) porque a cópia do quadro tinha mais de 3 min, para usar só a linha desta OS
e os "outros chamados" do mesmo ativo. O quadro já abria com a cópia vencida e relia por trás (09/10/2026); a tela de um
chamado agora faz o mesmo, e o estado da OS (a situação, o fim, o responsável) vem do detalhe, que é lido na hora.
E a releitura não relê as tarefas das OS que já estavam fechadas (como o Histórico, 19/10/2026).

Fracttal FALSO: nada vai à rede, cada leitura é contada, e a releitura por trás fica parada numa fila até o teste mandar
rodar. Nomes e números de mentira: o repositório é público."""
import sys
import threading

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
import chamados_obs_store as obs_store  # noqa: E402
from os_web import criar_app, rotas, rotas_acomp  # noqa: E402

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
URL = "/os/chamados/acompanhamento"


def _linha(i, folio, status=1, data_fim=""):
    return {"id": i, "folio": str(folio), "cliente": "Cliente Teste", "usina": "Usina Teste", "ativo": "Inversor 1.1",
            "tipo": "Inversor", "tipo_tarefa": "Administrativa", "note": "", "event_date": "", "inicio": "",
            "gatilho": "", "descricao": "[Inversor 1.1] - Acompanhamento de chamado Marca", "status_id": status,
            "status": api.WO_STATUS.get(status), "data": "2026-10-01T12:00:00", "data_fim": data_fim,
            "atribuido_a": "Analista Teste", "id_atribuido": 900001}


@pytest.fixture(autouse=True)
def _memoria_limpa(monkeypatch):
    monkeypatch.setattr(obs_store, "_linhas", lambda: [])              # o banco da Gridco: nenhum teste vai
    obs_store._estado.update(lista=None, lido=0.0)
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    rotas_acomp._RENOVANDO.clear()
    rotas_acomp._ESQUECIDO["em"] = 0.0
    yield
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    rotas_acomp._RENOVANDO.clear()


@pytest.fixture
def fila(monkeypatch):
    jobs = []
    monkeypatch.setattr(rotas_acomp, "_em_segundo_plano", jobs.append)
    return jobs


@pytest.fixture
def fr(monkeypatch):
    f = {"listas": [], "detalhes": [], "det": {}}

    def listar(**k):
        f["listas"].append(k)
        if isinstance(k.get("info"), dict):
            k["info"]["total"] = 3
        return [_linha(1, 9103), _linha(2, 9104), _linha(3, 9105, status=3, data_fim="2026-10-18T12:00:00")]

    def detalhe(wid):
        f["detalhes"].append(wid)
        return dict({"folio": 9100 + wid + 2, "subtarefas": [], "notas": ""}, **f["det"])
    monkeypatch.setattr(api, "list_chamados", listar)
    monkeypatch.setattr(api, "tickets_os3_em_massa", lambda ids: {i: "TK-%d" % i for i in ids})
    monkeypatch.setattr(api, "total_chamados", lambda de=None: 3)
    monkeypatch.setattr(api, "get_os_detalhes", detalhe)
    return f


def _cliente():
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid", "perfil": ""}
    return c


def _envelhecer(segundos):
    with rotas._MEMO_LOCK:
        for k, (t, v) in list(rotas._MEMO.items()):
            rotas._MEMO[k] = (t - segundos, v)


def test_a_tela_de_um_chamado_com_a_copia_vencida_abre_sem_reler_a_lista(fr, fila):
    cli = _cliente()
    cli.get(URL)
    assert len(fr["listas"]) == 1
    _envelhecer(rotas_acomp.TTL_QUADRO + 5)
    r = cli.get(URL + "/9104")
    assert r.status_code == 200 and 'data-folio="9104"' in r.get_data(as_text=True)
    assert len(fr["listas"]) == 1 and fr["detalhes"] == [2]            # a lista não foi relida na frente
    assert len(fila) == 1                                                # e se relê por trás
    t = threading.Thread(target=fila.pop())
    t.start()
    t.join(10)
    assert len(fr["listas"]) == 2


def test_a_copia_velha_demais_e_relida_na_frente(fr, fila):
    cli = _cliente()
    cli.get(URL)
    _envelhecer(rotas_acomp.VELHA_MAX + 5)
    assert cli.get(URL + "/9104").status_code == 200
    assert len(fr["listas"]) == 2 and not fila


def test_o_estado_e_o_responsavel_vem_do_detalhe_lido_agora(fr, fila):
    """A cópia (até 2 h) diz que a 9104 está aberta e com a equipe; o detalhe, lido agora, diz que ela foi concluída e
    passou para outra pessoa: vale o detalhe."""
    cli = _cliente()
    cli.get(URL)
    _envelhecer(rotas_acomp.TTL_QUADRO + 5)
    fr["det"] = {"status_id": 3, "data_fim": "2026-10-20T11:00:00", "responsavel": "Outra Pessoa"}
    h = cli.get(URL + "/9104").get_data(as_text=True)
    assert "Finalizado" in h and 'id="b_finalizar"' not in h
    assert "Outra Pessoa" in h and "Analista Teste" not in h


def test_a_releitura_nao_rele_as_tarefas_das_fechadas(fr, fila):
    cli = _cliente()
    cli.get(URL)
    assert not fr["listas"][0].get("meta_ja")                           # a 1ª leitura não tem o que reaproveitar
    cli.get(URL + "?atualizar=1")
    ja = fr["listas"][1].get("meta_ja") or {}
    assert set(ja) == {3}                                                # só a concluída (3); as abertas relêem
    assert ja[3]["status_id"] == 3 and ja[3]["data_fim"] == "2026-10-18T12:00:00"
