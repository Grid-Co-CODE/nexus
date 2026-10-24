"""O quadro do Acompanhamento de chamados dividido entre quem vê o mesmo no Fracttal (Levi, 19/10/2026: "quebre essa
regra"). Até então cada pessoa tinha a sua cópia ("uma pessoa nunca vê a cópia de outra"), e cada uma com o quadro
aberto relia a lista e os tickets a cada 3 min, para o mesmo quadro. Agora a cópia é de "TODOS" para quem o Fracttal dá
o mesmo total de OS com a etiqueta CHAMADOS (`rotas_acomp._dono`, conferido na sessão da pessoa a cada 30 min); quem vê
outro total segue com a dela.

Fracttal FALSO, por pessoa (a lista e o total dependem de quem pede, pela sessão): nada vai à rede, cada leitura é
contada. Nomes e números de mentira: o repositório é público."""
import sys
import threading

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
import chamados_obs_store as obs_store  # noqa: E402
from os_web import criar_app, rotas, rotas_acomp, sessao  # noqa: E402
from os_web import historico_store as HS  # noqa: E402

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
URL = "/os/chamados/acompanhamento"
TODA = "toda@exemplo.invalid"           # vê todas as OS de acompanhamento (50 com a etiqueta)
OUTRA = "outra@exemplo.invalid"         # a mesma visão
RESTRITA = "restrita@exemplo.invalid"   # visão restrita no Fracttal (40 com a etiqueta): não vê a 9104


def _linha(i, folio):
    return {"id": i, "folio": str(folio), "cliente": "Cliente Teste", "usina": "Usina Teste", "ativo": "Inversor 1.1",
            "tipo": "Inversor", "tipo_tarefa": "Administrativa", "note": "",
            "descricao": "[Inversor 1.1] - Acompanhamento de chamado Marca", "status_id": 1,
            "status": api.WO_STATUS.get(1), "data": "2026-10-01T12:00:00", "data_fim": "",
            "atribuido_a": "", "id_atribuido": None}


_APP = {}


def _cliente(email):
    """Um navegador de cada pessoa no MESMO app, como no servidor (um app novo limparia a memória das conferências)."""
    app = _APP.get("app")
    if app is None:
        app = _APP["app"] = criar_app(segredo="teste", testing=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": email, "perfil": ""}
    return c


@pytest.fixture(autouse=True)
def _memoria_limpa(monkeypatch):
    monkeypatch.setattr(obs_store, "_linhas", lambda: [])              # o banco da Gridco: nenhum teste vai
    obs_store._estado.update(lista=None, lido=0.0)
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    rotas_acomp._RENOVANDO.clear()
    rotas_acomp._ESQUECIDO["em"] = 0.0
    _APP.clear()
    yield
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    rotas_acomp._RENOVANDO.clear()
    _APP.clear()


@pytest.fixture
def fr(monkeypatch):
    """O Fracttal de cada pessoa: a lista, o total da etiqueta e quantas vezes cada coisa foi pedida, e por quem."""
    f = {"listas": [], "tickets": 0, "totais": [], "detalhes": [], "sem_etiqueta": False, "conferir_falha": False,
         "total": {TODA: 50, OUTRA: 50, RESTRITA: 40}}

    def listar(**k):
        quem = sessao.email_atual()
        f["listas"].append(quem)
        if f["sem_etiqueta"]:
            return []                                                   # sem a etiqueta: o `info` fica sem o total
        if isinstance(k.get("info"), dict):
            k["info"]["total"] = f["total"][quem]
        return [_linha(1, 9103)] + ([] if quem == RESTRITA else [_linha(2, 9104)])

    def tickets(ids):
        f["tickets"] += 1
        return {i: "TK-%d" % i for i in ids}

    def total(de=None):
        f["totais"].append(sessao.email_atual())
        if f["conferir_falha"]:
            raise api.FracttalError("o Fracttal recusou (429)")
        return 0 if f["sem_etiqueta"] else f["total"][sessao.email_atual()]

    def detalhe(wid):
        f["detalhes"].append(wid)
        return {"folio": 9100 + wid + 2, "subtarefas": [], "notas": ""}
    monkeypatch.setattr(api, "list_chamados", listar)
    monkeypatch.setattr(api, "tickets_os3_em_massa", tickets)
    monkeypatch.setattr(api, "total_chamados", total)
    monkeypatch.setattr(api, "get_os_detalhes", detalhe)
    return f


def _envelhecer(segundos):
    with rotas._MEMO_LOCK:
        for k, (t, v) in list(rotas._MEMO.items()):
            rotas._MEMO[k] = (t - segundos, v)


def test_quem_leu_a_lista_nao_confere_de_novo(fr):
    """A leitura da lista já diz o total que o Fracttal dá a quem leu (a mesma conta da conferência)."""
    toda = _cliente(TODA)
    toda.get(URL)
    toda.get(URL)
    assert fr["listas"] == [TODA] and fr["totais"] == []


def test_quem_ve_o_mesmo_abre_a_mesma_copia(fr):
    _cliente(TODA).get(URL)
    assert fr["listas"] == [TODA] and fr["tickets"] == 1 and fr["totais"] == []     # a 1ª visita faz a cópia
    outra = _cliente(OUTRA)
    h = outra.get(URL).get_data(as_text=True)
    assert fr["listas"] == [TODA] and fr["tickets"] == 1                            # nada da lista nem dos tickets
    assert fr["totais"] == [OUTRA] and "TK-2" in h and "9104" in h                  # só a conferência, na sessão dela
    outra.get(URL)
    assert fr["totais"] == [OUTRA]                                                  # a conferência vale 30 min


def test_visao_restrita_fica_com_a_dela(fr):
    _cliente(TODA).get(URL)
    h = _cliente(RESTRITA).get(URL).get_data(as_text=True)
    assert fr["listas"] == [TODA, RESTRITA] and "9104" not in h and "9103" in h
    assert "9104" in _cliente(OUTRA).get(URL).get_data(as_text=True)                # a cópia dividida segue a mesma


def test_a_conferencia_e_com_a_copia_de_agora(fr):
    """Quem tem a visão restrita conferiu a cópia que ela mesma fez; um ticket gravado tira a cópia, e a próxima é de
    quem vê tudo. O total dela vale 30 min, mas a comparação é com a cópia de AGORA: ela não vê a 9104."""
    restrita = _cliente(RESTRITA)
    restrita.get(URL)                                                               # a cópia dividida é a dela
    restrita.get(URL)                                                               # o total dela: 40, da leitura
    rotas_acomp._esquecer(1)                                                        # um ticket gravado
    assert "9104" in _cliente(TODA).get(URL).get_data(as_text=True)                 # a nova cópia dividida
    h = restrita.get(URL).get_data(as_text=True)
    assert "9104" not in h and fr["listas"] == [RESTRITA, TODA, RESTRITA]
    assert fr["totais"] == []                                                       # o total dela já estava anotado


def test_sem_a_etiqueta_o_quadro_vazio_e_um_so(fr):
    """Sem a etiqueta CHAMADOS no Fracttal (é da empresa), o total é 0 para todos e o quadro vazio é o mesmo."""
    fr["sem_etiqueta"] = True
    _cliente(TODA).get(URL)
    assert _cliente(OUTRA).get(URL).status_code == 200
    assert fr["listas"] == [TODA] and fr["totais"] == [OUTRA]


def test_sem_conseguir_conferir_fica_com_a_dela(fr):
    _cliente(TODA).get(URL)
    fr["conferir_falha"] = True
    assert _cliente(OUTRA).get(URL).status_code == 200
    assert fr["listas"] == [TODA, OUTRA]


def test_copia_abandonada_vira_a_de_quem_chega(fr):
    """A cópia de quem tem a visão restrita, sem ninguém usando há mais de VELHA_MAX: quem chega faz a nova, e quem vê o
    mesmo que ela divide a nova."""
    _cliente(RESTRITA).get(URL)
    _envelhecer(rotas_acomp.VELHA_MAX + 5)
    assert "9104" in _cliente(TODA).get(URL).get_data(as_text=True)
    # a cópia velha não é da visão dela (24/10/2026: a de ontem só abre na hora para quem vê o mesmo total): leu na frente
    assert fr["listas"] == [RESTRITA, TODA] and fr["totais"] == [TODA]
    _cliente(OUTRA).get(URL)
    assert fr["listas"] == [RESTRITA, TODA] and fr["totais"] == [TODA, OUTRA]


def test_a_copia_de_ontem_de_quem_ve_tudo_nao_abre_para_a_visao_restrita(fr, monkeypatch):
    """A cópia de ontem é de quem vê todas as OS; quem tem a visão restrita não a vê nem por um instante: lê a dela."""
    jobs = []
    monkeypatch.setattr(rotas_acomp, "_em_segundo_plano", jobs.append)
    _cliente(TODA).get(URL)
    _envelhecer(rotas_acomp.VELHA_MAX + 5)
    h = _cliente(RESTRITA).get(URL).get_data(as_text=True)
    assert "9104" not in h and "data-renovando" not in h and not jobs
    assert fr["listas"] == [TODA, RESTRITA]


def test_uma_releitura_por_tras_por_copia(fr, monkeypatch):
    jobs = []
    monkeypatch.setattr(rotas_acomp, "_em_segundo_plano", jobs.append)
    toda, outra = _cliente(TODA), _cliente(OUTRA)
    toda.get(URL)
    outra.get(URL)
    _envelhecer(rotas_acomp.TTL_QUADRO + 5)
    toda.get(URL)
    outra.get(URL)                                                                  # a mesma cópia já está sendo relida
    assert len(jobs) == 1
    t = threading.Thread(target=jobs.pop())
    t.start()
    t.join(10)
    assert fr["listas"] == [TODA, TODA]                                             # com a sessão de quem abriu
    assert HS._CONFERIDOS[(TODA, ("acomp", "TODOS"))][1] == 50                       # e o total anotado é o dela


def test_o_chamado_de_outra_pessoa_usa_a_copia_dividida(fr):
    _cliente(TODA).get(URL)
    r = _cliente(OUTRA).get(URL + "/9104")
    assert r.status_code == 200 and 'data-folio="9104"' in r.get_data(as_text=True)
    assert fr["listas"] == [TODA] and fr["detalhes"] == [2]                         # a linha veio da cópia; o detalhe é dela
