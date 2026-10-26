"""A nota da OS no Fracttal quando o motivo é escolhido (20/10/2026, Levi: "quando selecionar o motivo vai preencher na
nota da OS a data, o nome da tarefa, o ativo e o motivo de não fazer a tarefa").

O Nexus escreve nas marcas feitas nele (a janela do Quadro e o Painel do Fora da programação), com o login do Fracttal de
quem marcou (a sessão do OS Creator da pessoa); a justificativa do técnico, o App escreve com o login dele. A linha vai
no FIM da nota (o que já existe fica). Nada aqui vai ao Fracttal: o `api` é de mentira."""
from datetime import datetime, timezone

import pytest

from nexus.pcm import motivos as M
from nexus.pcm import nota_os as NO
from test_pcm_motivos import _mid, tela  # noqa: F401 (fixture)
from test_pcm_publicar import _no_setor, _pessoa


def test_a_linha_da_nota():
    """O formato do Levi (25/10/2026): "[Data e hora] - [Nome da atividade] - Motivo - [Justificativa, se tiver]". Os
    mesmos exemplos do teste do App (`test_v294_fora_nota_etiqueta.py`): os dois escrevem a mesma linha."""
    q = datetime(2026, 10, 21, 17, 32, tzinfo=timezone.utc)                      # 14:32 de Brasília
    assert NO.linha(q, "Aguardando material", "[Grid Co.] - MPM - Inversor", "UFV1-INV1", "sem o fusível") == (
        "[21/10/2026 14:32] - [[Grid Co.] - MPM - Inversor] - Aguardando material - [sem o fusível]")
    # sem texto, a linha termina no motivo; o ativo não entra
    assert NO.linha(q, "Aguardando cliente", "[Grid Co.] - MPM - Inversor", "", "") == (
        "[21/10/2026 14:32] - [[Grid Co.] - MPM - Inversor] - Aguardando cliente")
    # o dia de Brasília (02:10 UTC de 22/10 é 21/10), e quebra de linha e espaço repetido viram um espaço só
    q2 = datetime(2026, 10, 22, 2, 10, tzinfo=timezone.utc)
    assert NO.linha(q2, "M", "T", "X1", None) == "[21/10/2026 23:10] - [T] - M"
    assert NO.linha(q2, " Motivo  X ", "T  1", "X1", "linha 1\n linha 2 ") == (
        "[21/10/2026 23:10] - [T 1] - Motivo X - [linha 1 linha 2]")


def test_a_linha_vai_no_fim_da_nota():
    assert NO.juntar("Nota antiga da OS", "linha nova") == "Nota antiga da OS\nlinha nova"     # sem linha em branco
    assert NO.juntar("  ", "linha nova") == "linha nova" and NO.juntar(None, "linha nova") == "linha nova"
    assert NO.juntar("None", "linha nova") == "linha nova"                      # o RPC às vezes manda o texto "None"


class ApiFalsa:
    """O `api` do OS Creator de mentira: a OS 4321 (id 99) com a nota "Nota antiga"."""
    RPC_WO_TASKS = "tasks.work_orders_tasks_new_list"

    class SessionExpired(Exception):
        pass

    def __init__(self, nota="Nota antiga", recusa=None):
        self.nota, self.recusa, self.gravadas = nota, recusa, []

    def _wo_id_por_folio(self, folio):
        return 99 if str(folio) == "4321" else None

    def _rpc_call(self, metodo, params):
        assert metodo == self.RPC_WO_TASKS and params["id_work_order"] == 99
        return {"data": [{"id": 1, "note": self.nota, "id_assigned_user": 7}]}

    def editar_nota_os(self, wid, nota):
        if self.recusa:
            return {"ok": False, "erro": self.recusa}
        self.gravadas.append((wid, nota))
        self.nota = nota                         # como o Fracttal: a próxima leitura já traz a nota gravada
        return {"ok": True, "nota": nota}


def test_escrever_le_a_nota_e_acrescenta():
    api = ApiFalsa()
    assert NO.gravar(api, "4321", "linha nova") == {"ok": True}
    assert api.gravadas == [(99, "Nota antiga\nlinha nova")]
    assert NO.gravar(api, "555", "linha nova") == {"ok": False, "erro": "não achei a OS 555 no Fracttal"}
    r = NO.gravar(ApiFalsa(recusa="Esta OS já está concluída"), "4321", "x")
    assert r == {"ok": False, "erro": "Esta OS já está concluída"}


def test_a_linha_que_ja_esta_na_nota_nao_volta():
    """A tela pode mandar o mesmo pedido duas vezes (o clique repetido, a volta depois de "o Fracttal não respondeu"
    com a nota já gravada): a linha que já está na nota não se repete."""
    api = ApiFalsa(nota="Nota antiga\n[20/10/2026 14:32] - [T] - M")
    assert NO.gravar(api, "4321", "[20/10/2026 14:32] - [T] - M") == {"ok": True} and api.gravadas == []


USUARIO = {"email": "pessoa.teste@exemplo.com", "nome": "Pessoa Teste"}      # o de `test_pcm_publicar._pessoa`


def test_o_pedido_da_nota_e_assinado_e_de_quem_marcou(app, monkeypatch):
    import time
    p = NO.pedido(app, "5", "linha", USUARIO)
    assert NO.abrir_pedido(app, p, USUARIO) == {"os": "5", "texto": "linha"}
    assert NO.abrir_pedido(app, p, {"email": "outra.pessoa@exemplo.com"}) is None       # outro login
    assert NO.abrir_pedido(app, p[:-2] + "xx", USUARIO) is None                       # mexido na página
    assert NO.abrir_pedido(app, None, USUARIO) is None
    agora = time.time()
    monkeypatch.setattr(time, "time", lambda: agora + NO.PRAZO_DO_PEDIDO_S + 5)       # venceu
    assert NO.abrir_pedido(app, p, USUARIO) is None


@pytest.fixture
def notas(monkeypatch):
    """O relógio das marcas parado em 20/10/2026 14:32 de Brasília."""
    monkeypatch.setattr(M, "_agora", lambda: datetime(2026, 10, 20, 17, 32, tzinfo=timezone.utc))


def _texto(app, pedido):
    p = NO.abrir_pedido(app, pedido, USUARIO)
    return (p["os"], p["texto"]) if p else None


def test_a_janela_do_quadro_pede_a_nota_ao_escolher_o_motivo(app, tela, notas, monkeypatch):
    c = _pessoa(app)
    _no_setor(monkeypatch, "pcm")
    am, pr = _mid(app.config, "Aguardando material"), _mid(app.config, "Prioridade")
    marca = {"semana": "2026-W41", "os": "5", "tarefa": "[Grid Co.] - MPM - Trafo", "codigo": "UFV1-TR01",
             "motivo_id": am, "obs": "sem o fusível"}
    r = c.post("/t/pcm/quadro/motivo", json=marca).get_json()
    assert r["ok"] and _texto(app, r["nota_pedido"]) == (
        "5", "[20/10/2026 14:32] - [[Grid Co.] - MPM - Trafo] - Aguardando material - [sem o fusível]")
    # só a observação mudou: não é escolher o motivo, a nota não ganha linha
    r = c.post("/t/pcm/quadro/motivo", json=dict(marca, obs="sem o fusível, pedido feito")).get_json()
    assert r["ok"] and r["nota_pedido"] is None
    # trocar o motivo pede de novo; tirar, não
    r = c.post("/t/pcm/quadro/motivo", json=dict(marca, motivo_id=pr)).get_json()
    assert _texto(app, r["nota_pedido"])[1].startswith("[20/10/2026 14:32] - [[Grid Co.] - MPM - Trafo] - Prioridade")
    assert c.post("/t/pcm/quadro/motivo", json=dict(marca, tirar=True)).get_json()["nota_pedido"] is None
    # a página do Quadro sabe para onde mandar o pedido
    assert "/os/_nexus/pcm/nota" in c.get("/t/pcm/quadro?semana=2026-W41").get_data(as_text=True)


def test_o_painel_pede_a_nota_ao_trocar_o_motivo(app, tela, notas, monkeypatch):
    import html as H
    import re
    c = _pessoa(app)
    _no_setor(monkeypatch, "pcm")
    am, cl = _mid(app.config, "Aguardando material"), _mid(app.config, "Aguardando cliente")
    c.post("/t/pcm/quadro/motivo", json={"semana": "2026-W41", "os": "6", "tarefa": "Troca de fusível", "codigo": "",
                                         "motivo_id": am})
    item = next(k for k, m in M.vigentes(app.config, M.ler(app.config, forcar=True)).items() if m["os"] == "6")
    c.post("/t/pcm/fora-da-programacao/marcar", data={"item": item, "obs": "só a observação"})
    assert "data-nota-pedido" not in c.get("/t/pcm/fora-da-programacao").get_data(as_text=True)   # a observação não
    c.post("/t/pcm/fora-da-programacao/marcar", data={"item": item, "motivo_id": cl})
    html = c.get("/t/pcm/fora-da-programacao").get_data(as_text=True)
    pedido = H.unescape(re.search(r'data-nota-pedido="([^"]+)"', html).group(1))
    assert _texto(app, pedido)[1].startswith("[20/10/2026 14:32] - [Troca de fusível] - Aguardando cliente")
    assert 'data-url="/os/_nexus/pcm/nota"' in html and "Escrevendo a nota da OS no Fracttal" in html
    # o aviso aparece uma vez: recarregar não manda de novo
    assert "data-nota-pedido" not in c.get("/t/pcm/fora-da-programacao").get_data(as_text=True)


# ── a ponte /os/_nexus/pcm/nota, com o cookie do Fracttal como o navegador o guarda (Path=/os) ───────────────────────
NOTA = "/os/_nexus/pcm/nota"
SAME = {"Sec-Fetch-Site": "same-origin"}


def _login_do_fracttal(app, cliente):
    """O cookie do OS Creator como o login pelo Fracttal o deixa: assinado pelo clone e em Path=/os (JWT de mentira)."""
    from nexus.torres.oscreator import ponte
    clone = ponte.clone(app)
    jwt = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"
    cliente.set_cookie("os_sessao", clone.session_interface.get_signing_serializer(clone).dumps(
        {"jwt": jwt, "conta": {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid"}}), path="/os")


@pytest.fixture
def fracttal(app, monkeypatch):
    """O `api` do clone com a OS 6 (id 99) e a nota antiga; o que iria ao Fracttal fica em `gravadas`."""
    pytest.importorskip("PyQt6")
    from nexus.torres.oscreator import ponte
    ponte.clone(app)
    import api as os_api
    falsa = ApiFalsa()
    monkeypatch.setattr(os_api, "_wo_id_por_folio", lambda folio: 99 if str(folio) == "6" else None)
    monkeypatch.setattr(os_api, "_rpc_call", lambda metodo, params: {"data": [{"id": 1, "note": falsa.nota}]})
    monkeypatch.setattr(os_api, "editar_nota_os", falsa.editar_nota_os)
    return falsa


def test_a_ponte_ve_o_login_do_fracttal_e_a_marca_nao(app, tela, notas, fracttal, monkeypatch):
    """O defeito de 20 a 26/10/2026: o cookie os_sessao mora em Path=/os e o navegador não o manda a /t/pcm. Com o
    `sessao_do_os` de verdade, a marca (em /t/pcm) não vê o login; a ponte (em /os) vê e escreve a nota."""
    from nexus.torres.oscreator import ponte
    c = _pessoa(app)
    _no_setor(monkeypatch, "pcm")
    _login_do_fracttal(app, c)
    viu, pedido = [], NO.pedido
    monkeypatch.setattr(NO, "pedido", lambda *a: viu.append(bool(ponte.sessao_do_os(app).get("jwt"))) or pedido(*a))
    am = _mid(app.config, "Aguardando material")
    r = c.post("/t/pcm/quadro/motivo", json={"semana": "2026-W41", "os": "6", "tarefa": "Troca de fusível",
                                             "codigo": "", "motivo_id": am, "obs": "sem o fusível"}).get_json()
    assert r["gravou"] and viu == [False]                    # em /t/pcm o login do Fracttal não chega
    assert fracttal.gravadas == []                           # e a marca não escreve nada no Fracttal
    j = c.post(NOTA, json={"pedido": r["nota_pedido"], "tela": "quadro"}, headers=SAME)
    assert j.status_code == 200 and j.get_json() == {"nota": {"ok": True}, "nota_txt": "Nota da OS escrita no Fracttal."}
    assert fracttal.gravadas == [(99, "Nota antiga\n[20/10/2026 14:32] - [Troca de fusível] - Aguardando material - "
                                      "[sem o fusível]")]
    # o mesmo pedido de novo (o clique repetido) não repete a linha
    assert c.post(NOTA, json={"pedido": r["nota_pedido"]}, headers=SAME).get_json()["nota"] == {"ok": True}
    assert len(fracttal.gravadas) == 1


def test_a_ponte_sem_o_login_do_fracttal_pede_o_login_e_nao_escreve(app, tela, notas, fracttal):
    """O administrador pela senha (e a conta Microsoft) não tem a sessão do Fracttal: a marca grava, a ponte responde 401
    com o login do OS Creator de volta à tela, e nada vai ao Fracttal."""
    from conftest import SENHA_TESTE
    c = app.test_client()
    c.post("/entrar", data={"senha": SENHA_TESTE})
    am = _mid(app.config, "Aguardando material")
    r = c.post("/t/pcm/quadro/motivo", json={"semana": "2026-W41", "os": "6", "tarefa": "Troca de fusível",
                                             "codigo": "", "motivo_id": am}).get_json()
    assert r["ok"] and r["gravou"] and r["nota_pedido"]
    j = c.post(NOTA, json={"pedido": r["nota_pedido"], "tela": "fora"}, headers=SAME)
    d = j.get_json()
    assert j.status_code == 401 and d["nota"]["ok"] is False and "entre pelo Fracttal" in d["nota_txt"]
    assert d["login"].startswith("/os/login?next=") and "%2Ft%2Fpcm%2Ffora-da-programacao" in d["login"]
    assert fracttal.gravadas == []


def test_a_ponte_recusa_pedido_de_outro_login_de_outro_site_ou_de_quem_nao_marca(app, tela, notas, fracttal,
                                                                                 monkeypatch):
    c = _pessoa(app)
    _no_setor(monkeypatch, "pcm")
    _login_do_fracttal(app, c)
    alheio = NO.pedido(app, "6", "linha de outro login", {"email": "outra.pessoa@exemplo.com"})
    j = c.post(NOTA, json={"pedido": alheio}, headers=SAME)
    assert j.status_code == 400 and "outro login" in j.get_json()["nota_txt"]
    meu = NO.pedido(app, "6", "linha", USUARIO)
    assert c.post(NOTA, json={"pedido": meu}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    _no_setor(monkeypatch, "Performance")
    assert c.post(NOTA, json={"pedido": meu}, headers=SAME).status_code == 403
    assert fracttal.gravadas == []
