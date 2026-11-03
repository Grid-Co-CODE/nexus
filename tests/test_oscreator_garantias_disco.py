"""O Garantias (o Acompanhamento de chamados) sobrevive ao reinício do servidor (Levi, 03/11/2026: "Nexus > Chamados >
Garantias demora muito para carregar na 1ª vez e ele é 99% Fracttal" e "tem que ser como no OS Creator... pega a informação
de um canto centralizado e mitiga essas perdas por reinício"). O servidor reinicia a cada push na `main`, e a memória
voltava vazia: a 1ª pessoa esperava a leitura inteira (até 94 s no Raio-X de 03/11). Agora a cópia dividida do quadro
("TODOS") e os tickets das OS concluídas moram também no disco, e voltam no 1º uso depois do reinício.

Fracttal FALSO: nenhum pedido vai à rede, cada leitura é contada, e a releitura por trás fica parada numa fila até o teste
mandar rodar. O "reinício" é a memória limpa e o disco ainda não lido, como num processo novo. Nomes e números de mentira:
o repositório é público."""
import datetime as dt
import json
import os
import sys
import threading

import pytest

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
import chamados_obs_store as obs_store  # noqa: E402
from os_web import criar_app, rotas, rotas_acomp  # noqa: E402
from os_web import historico_store as HS  # noqa: E402

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
URL = "/os/chamados/acompanhamento"
PESSOA = ("Pessoa Teste", "teste@exemplo.invalid")


def _cliente():
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": PESSOA[0], "email": PESSOA[1], "perfil": ""}
    return c


def _linha(i, folio, status=1, data_fim=""):
    return {"id": i, "folio": str(folio), "cliente": "Cliente Teste", "usina": "Usina Teste", "ativo": "Inversor 1.1",
            "tipo": "Inversor", "tipo_tarefa": "Administrativa", "note": "",
            "descricao": "[Inversor 1.1] - Acompanhamento de chamado Marca", "status_id": status,
            "status": api.WO_STATUS.get(status), "data": "2026-10-01T12:00:00", "data_fim": data_fim,
            "atribuido_a": "", "id_atribuido": None}


def _limpar():
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    rotas_acomp._RENOVANDO.clear()
    rotas_acomp._ESQUECIDO["em"] = 0.0
    del rotas_acomp._AJUSTES[:]
    HS.limpar()


def _reiniciar():
    """O processo novo: a memória vazia e o disco ainda não lido."""
    _limpar()
    rotas_acomp._DISCO["lido"] = False


@pytest.fixture(autouse=True)
def disco(monkeypatch, tmp_path):
    monkeypatch.setattr(obs_store, "_linhas", lambda: [])              # o banco da Gridco: nenhum teste vai
    obs_store._estado.update(lista=None, lido=0.0)
    _limpar()
    rotas_acomp.configurar_disco(str(tmp_path))
    yield tmp_path
    rotas_acomp.configurar_disco(None)
    _limpar()


@pytest.fixture
def fila(monkeypatch):
    """As releituras por trás, paradas até o teste mandar rodar."""
    jobs = []
    monkeypatch.setattr(rotas_acomp, "_em_segundo_plano", jobs.append)
    return jobs


@pytest.fixture
def fracttal(monkeypatch):
    ontem = (dt.datetime.utcnow() - dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    lido = {"listas": 0, "tickets": [], "total": 2,
            "linhas": [_linha(1, 9103), _linha(2, 9104, status=3, data_fim=ontem)]}

    def listar(**k):
        lido["listas"] += 1
        if isinstance(k.get("info"), dict):
            k["info"]["total"] = lido["total"]
        return [dict(l) for l in lido["linhas"]]

    def tickets(ids):
        lido["tickets"].append(sorted(ids))
        return {i: "TK-%d" % i for i in ids}
    monkeypatch.setattr(api, "list_chamados", listar)
    monkeypatch.setattr(api, "tickets_os3_em_massa", tickets)
    monkeypatch.setattr(api, "total_chamados", lambda de=None: lido["total"])
    return lido


def _envelhecer_o_disco(pasta, segundos):
    for nome in os.listdir(pasta):
        arq = os.path.join(pasta, nome)
        with open(arq, encoding="utf-8") as f:
            carga = json.load(f)
        carga["salvo_em"] -= segundos
        with open(arq, "w", encoding="utf-8") as f:
            json.dump(carga, f)


def _rodar_fora_da_requisicao(job):
    t = threading.Thread(target=job)
    t.start()
    t.join(10)
    assert not t.is_alive()


def test_o_reinicio_abre_com_a_copia_do_disco_sem_ir_ao_fracttal(fracttal, fila, disco):
    cli = _cliente()
    cli.get(URL)
    assert fracttal["listas"] == 1 and sorted(os.listdir(disco)) == ["acomp.json", "acomp_linhas.json", "acomp_tk.json"]
    _reiniciar()
    h = _cliente().get(URL).get_data(as_text=True)
    assert fracttal["listas"] == 1 and len(fracttal["tickets"]) == 1      # nada foi ao Fracttal na frente da pessoa
    assert "TK-1" in h and "TK-2" in h and not fila                       # a cópia é recente: nem relê por trás


def test_a_copia_velha_do_disco_abre_na_hora_e_rele_por_tras(fracttal, fila, disco):
    _cliente().get(URL)
    _reiniciar()
    _envelhecer_o_disco(disco, rotas_acomp.VELHA_MAX + 60)                # a de ontem, depois do deploy da manhã
    h = _cliente().get(URL).get_data(as_text=True)
    assert fracttal["listas"] == 1 and "TK-1" in h and "data-renovando" in h and len(fila) == 1
    _rodar_fora_da_requisicao(fila.pop())
    assert fracttal["listas"] == 2


def test_quem_ve_outro_total_no_fracttal_nao_recebe_a_copia_do_disco(fracttal, fila, disco):
    """A regra de 19/10 segue: a cópia dividida só vale para quem vê no Fracttal o mesmo total de OS da etiqueta."""
    _cliente().get(URL)
    _reiniciar()
    _envelhecer_o_disco(disco, rotas_acomp.VELHA_MAX + 60)
    fracttal["total"] = 5                                                 # a visão de outra pessoa
    h = _cliente().get(URL).get_data(as_text=True)
    assert fracttal["listas"] == 2 and "data-renovando" not in h          # leu na frente, com a sessão dela


def test_o_ticket_da_concluida_e_lido_uma_vez_e_sobrevive_ao_reinicio(fracttal, fila, disco):
    """A OS concluída não volta e o Fracttal não aceita mais editar: o ticket dela não muda, e era relido a cada 30 min."""
    cli = _cliente()
    cli.get(URL)
    assert fracttal["tickets"] == [[1, 2]]
    _reiniciar()
    _cliente().get(URL + "?atualizar=1")                                  # o Atualizar relê a lista e as abertas
    assert fracttal["listas"] == 2 and fracttal["tickets"][-1] == [1]     # a concluída veio do disco


def test_a_concluida_que_reabriu_tem_o_ticket_lido_de_novo(fracttal, fila, disco):
    _cliente().get(URL)
    _reiniciar()
    fracttal["linhas"][1].update(status_id=1, status=api.WO_STATUS.get(1), data_fim="")
    _cliente().get(URL + "?atualizar=1")
    assert fracttal["tickets"][-1] == [1, 2]


def test_a_gravacao_desta_tela_vai_ao_disco(fracttal, fila, disco):
    """O ticket gravado aqui (`_ajustar`) não se perde no reinício seguinte, antes da próxima releitura."""
    _cliente().get(URL)
    rotas_acomp._ajustar(1, {}, "TK-NOVO")
    _reiniciar()
    h = _cliente().get(URL).get_data(as_text=True)
    assert "TK-NOVO" in h and fracttal["listas"] == 1


def test_o_quadro_esquecido_sai_do_disco(fracttal, fila, disco):
    """Gravação feita fora desta tela (`_esquecer`): a próxima leitura vai ao Fracttal, também depois do reinício."""
    _cliente().get(URL)
    rotas_acomp._esquecer(1)
    _reiniciar()
    _cliente().get(URL)
    assert fracttal["listas"] == 2
