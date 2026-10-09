"""O Acompanhamento de chamados abre NA HORA com a leitura anterior e relê o Fracttal por trás (Levi, 09/10/2026:
"teria como utilizarmos essas requisições de forma mais inteligente? talvez um carregamento periódico que carregue em
segundo plano e deixe todos prontos"). Antes, passados os 3 min da cópia, a tela esperava o Fracttal na frente de quem
abriu.

Fracttal FALSO: nenhum pedido vai à rede, cada leitura é contada, e a releitura por trás fica parada numa fila até o
teste mandar rodar. Nomes e números de mentira: o repositório é público."""
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
PESSOA = ("Pessoa Teste", "teste@exemplo.invalid")


def _cliente():
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": PESSOA[0], "email": PESSOA[1], "perfil": ""}
    return c


def _linha(i, folio):
    return {"id": i, "folio": str(folio), "cliente": "Cliente Teste", "usina": "Usina Teste", "ativo": "Inversor 1.1",
            "tipo": "Inversor", "tipo_tarefa": "Administrativa", "note": "",
            "descricao": "[Inversor 1.1] - Acompanhamento de chamado Marca", "status_id": 1,
            "status": api.WO_STATUS.get(1), "data": "2026-10-01T12:00:00", "data_fim": "",
            "atribuido_a": "", "id_atribuido": None}


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
    """As releituras por trás, paradas até o teste mandar rodar."""
    jobs = []
    monkeypatch.setattr(rotas_acomp, "_em_segundo_plano", jobs.append)
    return jobs


@pytest.fixture
def fracttal(monkeypatch):
    lido = {"listas": 0, "tickets": 0, "jwt": []}

    def listar(**k):
        lido["listas"] += 1
        lido["jwt"].append(api._read_jwt())          # com a sessão de quem? (a da pessoa, mesmo fora da requisição)
        return [_linha(1, 9103), _linha(2, 9104)]

    def tickets(ids):
        lido["tickets"] += 1
        return {i: "TK-%d" % i for i in ids}
    monkeypatch.setattr(api, "list_chamados", listar)
    monkeypatch.setattr(api, "tickets_os3_em_massa", tickets)
    return lido


def _envelhecer(segundos):
    with rotas._MEMO_LOCK:
        for k, (t, v) in list(rotas._MEMO.items()):
            rotas._MEMO[k] = (t - segundos, v)


def _rodar_fora_da_requisicao(job):
    """Como no servidor: numa thread que nasce sem o contexto da requisição."""
    t = threading.Thread(target=job)
    t.start()
    t.join(10)
    assert not t.is_alive()


def _tem_quadro_na_memoria() -> bool:
    return any(k in rotas._MEMO for k in (("acomp", PESSOA[1]), ("acomp_linhas", PESSOA[1])))


def test_quadro_vencido_abre_na_hora_e_rele_por_tras(fracttal, fila):
    cli = _cliente()
    cli.get(URL)                                                          # a 1ª visita lê na frente, como sempre
    assert fracttal["listas"] == 1 and not fila
    _envelhecer(rotas_acomp.TTL_QUADRO + 5)
    h = cli.get(URL).get_data(as_text=True)
    assert fracttal["listas"] == 1 and fracttal["tickets"] == 1           # nada foi ao Fracttal na frente da pessoa
    assert "TK-1" in h and "data-renovando" in h and "· atualizando" in h  # o quadro anterior, dizendo que relê
    assert len(fila) == 1
    _rodar_fora_da_requisicao(fila.pop())
    assert fracttal["listas"] == 2 and fracttal["tickets"] == 2
    assert fracttal["jwt"][-1] == JWT                                     # com a sessão DELA no Fracttal
    h = cli.get(URL).get_data(as_text=True)                               # a próxima visita já tem a leitura nova
    assert "data-renovando" not in h and fracttal["listas"] == 2 and not fila


def test_quadro_velho_demais_espera_a_leitura(fracttal, fila):
    """Um quadro de horas atrás engana mesmo com a hora na tela: passa de VELHA_MAX, a tela espera, como antes."""
    cli = _cliente()
    cli.get(URL)
    _envelhecer(rotas_acomp.VELHA_MAX + 5)
    h = cli.get(URL).get_data(as_text=True)
    assert fracttal["listas"] == 2 and not fila and "data-renovando" not in h


def test_atualizar_le_na_hora(fracttal, fila):
    cli = _cliente()
    cli.get(URL)
    _envelhecer(rotas_acomp.TTL_QUADRO + 5)
    h = cli.get(URL + "?atualizar=1").get_data(as_text=True)
    assert fracttal["listas"] == 2 and not fila and "data-renovando" not in h


def test_quadro_novo_nao_rele(fracttal, fila):
    cli = _cliente()
    cli.get(URL)
    cli.get(URL)
    assert fracttal["listas"] == 1 and not fila


def test_uma_releitura_por_pessoa(fracttal, fila):
    cli = _cliente()
    cli.get(URL)
    _envelhecer(rotas_acomp.TTL_QUADRO + 5)
    cli.get(URL)
    cli.get(URL)                                                          # a 1ª releitura ainda não terminou
    assert len(fila) == 1
    _rodar_fora_da_requisicao(fila.pop())
    _envelhecer(rotas_acomp.TTL_QUADRO + 5)
    cli.get(URL)                                                          # terminou: a próxima vencida pede outra
    assert len(fila) == 1


def test_erro_do_fracttal_na_releitura_fica_a_leitura_anterior(fracttal, fila, monkeypatch):
    cli = _cliente()
    cli.get(URL)
    _envelhecer(rotas_acomp.TTL_QUADRO + 5)
    cli.get(URL)

    def recusa(**k):
        raise api.FracttalError("o Fracttal recusou (429)")
    monkeypatch.setattr(api, "list_chamados", recusa)
    _rodar_fora_da_requisicao(fila.pop())                                 # o erro não escapa da thread
    h = cli.get(URL).get_data(as_text=True)
    assert "TK-1" in h and "data-renovando" in h and len(fila) == 1       # a leitura anterior, e uma nova tentativa


def test_sessao_caida_na_releitura_tira_a_copia_e_a_proxima_volta_ao_login(fracttal, fila, monkeypatch):
    cli = _cliente()
    cli.get(URL)
    _envelhecer(rotas_acomp.TTL_QUADRO + 5)
    cli.get(URL)

    def caiu(**k):
        api._clear_jwt()                                                  # o Fracttal disse USER_NOT_LOGIN
        return []
    monkeypatch.setattr(api, "list_chamados", caiu)
    _rodar_fora_da_requisicao(fila.pop())
    assert not _tem_quadro_na_memoria()
    r = cli.get(URL)
    assert r.status_code == 302 and "/os/login" in r.headers["Location"]


def test_gravacao_no_meio_da_releitura_nao_traz_o_quadro_de_antes(fracttal, fila, monkeypatch):
    """O ticket gravado (ou a OS finalizada) durante a releitura: ela começou antes, então mostraria o quadro de antes da
    gravação por 3 min. A cópia dela sai, e a próxima visita lê na frente."""
    cli = _cliente()
    cli.get(URL)
    _envelhecer(rotas_acomp.TTL_QUADRO + 5)
    cli.get(URL)

    def gravou_no_meio(**k):
        rotas_acomp._esquecer(1)
        return [_linha(1, 9103), _linha(2, 9104)]
    monkeypatch.setattr(api, "list_chamados", gravou_no_meio)
    _rodar_fora_da_requisicao(fila.pop())
    assert not _tem_quadro_na_memoria()
