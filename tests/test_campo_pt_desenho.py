"""A assinatura desenhada do De acordo da PT (26/11/2026). Levi, depois de saber que um operador do COS "só clica e já
aprova direto": "o certo é ter a assinatura do técnico e a assinatura dele"; "todas as PTs têm que pedir assinatura".

O que estes testes seguram: o De acordo sem o desenho é recusado e nada grava; com ele, grava e a imagem fica cifrada no
disco (nunca no banco); o Não autorizo não pede desenho; com o envio ao App ligado, o App recebe a imagem ANTES da decisão,
com a chave e o código de quem assinou, e o App que recusa ou não responde faz a decisão não ser gravada; o card tem o
quadro e as outras telas levam ao card. App falso, banco falso e nomes de mentira."""
import base64
import io
import json
import time
import urllib.error

import pytest

from nexus.casca import relatos_app as R
from nexus.cadastro.ligacao_campo import codigo_da_pessoa
from nexus.campo import pt_desenho as PDz
from test_campo_pt_assinar import CARD_PT1, RESP, com_responsavel  # noqa: F401 (fixture)
from test_campo_visao import ASSINATURA_PNG, CHAVE, banco  # noqa: F401 (fixture)

FORM = {"codigo": "THPN-ALT100-INVR1", "volta": CARD_PT1, "card": "1"}


@pytest.fixture
def pasta(app, tmp_path):
    app.config["NEXUS_DADOS"] = str(tmp_path / "dados")
    return tmp_path / "dados" / "pt_assinaturas"


def _cliente(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"], s["admin"], s["via"], s["ms_ate"] = True, False, "microsoft", time.time() + 3600
        s["usuario"] = {"email": RESP, "nome": "Responsável Exemplo", "perfil": ""}
    return c


def _decisoes(banco):
    return [(d["pt"], d["decisao"]) for d in banco.linhas("nexus_pt_decisoes", "fato_decisao_pt")] \
        if "nexus_pt_decisoes" in banco.workbooks else []


def test_o_de_acordo_sem_desenho_e_recusado(app, com_responsavel, pasta):
    c = _cliente(app)
    r = c.post("/os/_nexus/pt/PT-1/decidir", data=dict(FORM, decisao="de_acordo"))
    assert r.status_code == 302 and _decisoes(com_responsavel) == []
    assert "Assine no quadro antes de dar o De acordo" in c.get(CARD_PT1).get_data(as_text=True)
    # o que não é PNG também não passa
    c.post("/os/_nexus/pt/PT-1/decidir", data=dict(FORM, decisao="de_acordo", assinatura_png="data:image/png;base64,QUJD"))
    assert _decisoes(com_responsavel) == []


def test_o_de_acordo_com_desenho_grava_e_guarda_a_imagem_cifrada(app, com_responsavel, pasta):
    c = _cliente(app)
    r = c.post("/os/_nexus/pt/PT-1/decidir", data=dict(FORM, decisao="de_acordo", assinatura_png=ASSINATURA_PNG))
    assert r.status_code == 302 and _decisoes(com_responsavel) == [("PT-1", "de_acordo")]
    arquivos = list(pasta.iterdir())
    assert len(arquivos) == 1 and b"PNG" not in arquivos[0].read_bytes()           # cifrada, não o PNG cru
    with app.app_context():
        g = PDz.ler(app.config, "PT-1", "THPN-ALT100-INVR1")
    assert g["png"] == base64.b64decode(ASSINATURA_PNG.split(",", 1)[1])
    assert g["por_hmac"] == codigo_da_pessoa(CHAVE, RESP)
    # a imagem não vai ao banco: o livro da decisão segue com as colunas de sempre
    assert all("png" not in k for k in com_responsavel.linhas("nexus_pt_decisoes", "fato_decisao_pt")[0])


def test_o_nao_autorizo_nao_pede_desenho(app, com_responsavel, pasta):
    _cliente(app).post("/os/_nexus/pt/PT-1/decidir", data=dict(FORM, decisao="negada", motivo="Falta o bloqueio"))
    assert _decisoes(com_responsavel) == [("PT-1", "negada")]


class _AppFalso:
    def __init__(self, status=200, corpo=None):
        self.status, self.corpo, self.pedidos = status, corpo if corpo is not None else {"ok": True}, []

    def __call__(self, req, timeout=None):
        self.pedidos.append({"url": req.full_url, "chave": req.get_header("X-nexus-chave"),
                             "corpo": json.loads(req.data.decode("utf-8"))})
        if self.status != 200:
            raise urllib.error.HTTPError(req.full_url, self.status, "erro", {}, io.BytesIO(b'{"erro": "fora"}'))
        return io.BytesIO(json.dumps(self.corpo).encode("utf-8"))


@pytest.fixture
def envio(app, monkeypatch):
    app.config["NEXUS_PT_ASSINATURA_APP"] = "1"
    app.config["NEXUS_APP_RELATOS_CHAVE"] = "k" * 40
    falso = _AppFalso()
    monkeypatch.setattr(R, "_abrir", falso)
    return falso


def test_com_o_envio_ligado_o_app_recebe_a_assinatura_antes_da_decisao(app, com_responsavel, pasta, envio):
    _cliente(app).post("/os/_nexus/pt/PT-1/decidir", data=dict(FORM, decisao="de_acordo", assinatura_png=ASSINATURA_PNG))
    p = envio.pedidos[0]
    assert p["url"].endswith("/app/nexus/pt/PT-1/assinatura-aprovador") and p["chave"] == "k" * 40
    assert p["corpo"]["versao"] == 1 and p["corpo"]["codigo"] == "THPN-ALT100-INVR1"
    assert p["corpo"]["pessoa_hmac"] == codigo_da_pessoa(CHAVE, RESP)
    assert base64.b64decode(p["corpo"]["png_base64"]).startswith(PDz.PNG)
    assert p["corpo"]["assinatura_id"].startswith("a") and len(p["corpo"]["assinatura_id"]) == 12
    assert _decisoes(com_responsavel) == [("PT-1", "de_acordo")]


def test_o_app_que_recusa_a_assinatura_faz_a_decisao_nao_gravar(app, com_responsavel, pasta, envio):
    envio.status = 503
    c = _cliente(app)
    c.post("/os/_nexus/pt/PT-1/decidir", data=dict(FORM, decisao="de_acordo", assinatura_png=ASSINATURA_PNG))
    assert _decisoes(com_responsavel) == [] and not pasta.exists()
    assert "O App não recebeu a assinatura" in c.get(CARD_PT1).get_data(as_text=True)


def test_o_card_tem_o_quadro_e_as_outras_telas_levam_a_ele(app, com_responsavel, logado):
    card = _cliente(app).get(CARD_PT1).get_data(as_text=True)
    assert "data-pa-quadro" in card and 'name="assinatura_png"' in card and "Sua assinatura" in card
    lista = logado.get("/t/hseq/apr-pt").get_data(as_text=True)
    assert 'value="de_acordo"' not in lista and ">Assinar o De acordo</a>" in lista


def test_o_png_do_formulario():
    with pytest.raises(PDz.Recusada):
        PDz.png_do_formulario("")
    with pytest.raises(PDz.Recusada):
        PDz.png_do_formulario("data:image/jpeg;base64,QUJD")
    with pytest.raises(PDz.Recusada):           # PNG vazio (o quadro sem traço) é pequeno demais
        PDz.png_do_formulario("data:image/png;base64," + base64.b64encode(PDz.PNG + b"0" * 20).decode())
    assert PDz.png_do_formulario(ASSINATURA_PNG).startswith(PDz.PNG)


def test_o_interruptor_do_envio_esta_nas_chaves_do_nexus_e_no_env():
    """Levi, 26/11/2026: "Em vez de precisar mudar o .env, joga lá no chaves do Nexus da base, que eu coloco 1 e salvo". O
    .env segue valendo sem a da tela (só os nomes de `config.OPCIONAIS` entram na configuração)."""
    from nexus import config
    from nexus.auth import chaves
    assert "NEXUS_PT_ASSINATURA_APP" in config.OPCIONAIS
    item = chaves.CHAVES["NEXUS_PT_ASSINATURA_APP"]
    assert [v for v, _r in item["escolha"]] == ["1", "0"]
    assert item["conferir"]("1").startswith("1:") and item["conferir"]("0").startswith("0:")
    with pytest.raises(chaves.Recusada):
        item["conferir"]("sim")
