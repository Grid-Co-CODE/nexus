"""A leitura de fundo do pré-filtro (nexus/campo/prefiltro_fundo.py): para cada OS da fila de verificação ainda não
conferida, UM pedido de leitura ao Fracttal (a lista de anexos) e as fotos pelo S3 (fora da cota da empresa), o hash
sem o carimbo e a hora de anexação; tudo guardado em memória e em disco, com a miniatura só das fotos repetidas.
Fracttal e S3 falsos do começo ao fim."""
import io
import random

import pytest
from PIL import Image, ImageDraw

from nexus.campo import fracttal, prefiltro_fundo


def _jpeg(semente, carimbo="carimbo"):
    rnd = random.Random(semente)
    im = Image.new("RGB", (640, 480), (rnd.randint(0, 255),) * 3)
    d = ImageDraw.Draw(im)
    for _ in range(30):
        x, y = rnd.randint(0, 640), rnd.randint(0, 480)
        d.rectangle([x, y, x + rnd.randint(20, 200), y + rnd.randint(20, 150)], fill=tuple(rnd.randint(0, 255) for _ in "rgb"))
    d.rectangle([0, 390, 640, 480], fill=(0, 0, 0))
    d.text((8, 400), carimbo, fill=(255, 255, 255))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def _tarefa(folio, n=1, fim="2026-10-20T10:00:00", **k):
    return {"id_work_orders_tasks": int(folio) * 10 + n, "id_work_order": int(folio), "wo_folio": str(folio),
            "final_date": fim, "tasks_log_task_type_main": "Corretiva", "description": "Troca de fusível", "labels": [],
            **k}


class S3Falso:
    """Cada URL é uma foto: a semente decide a imagem (mesma semente = mesma foto), a hora vem junto."""

    def __init__(self):
        self.pedidos, self.falhar = [], set()

    def __call__(self, url):
        self.pedidos.append(url)
        if url in self.falhar:
            raise OSError("S3 fora")
        semente, hora = url.split("/")[-1].split(".")[0].split("_")[:2]
        return _jpeg(int(semente), carimbo=f"carimbo {url}"), hora.replace("h", ":")


class FracttalAnexos:
    """O REST de anexos: `work_orders_attachments?folio=` em páginas de 100 (`start=`)."""

    def __init__(self, anexos_por_os):
        self.anexos, self.pedidos, self.recusar_em = anexos_por_os, [], None

    def __call__(self, path):
        self.pedidos.append(path)
        if self.recusar_em is not None and len(self.pedidos) > self.recusar_em:
            raise fracttal.Recusado("429")
        assert path.startswith("work_orders_attachments?folio=")
        folio = path.split("folio=")[1].split("&")[0]
        start = int(path.split("start=")[1].split("&")[0]) if "start=" in path else 0
        return {"data": self.anexos.get(folio, [])[start:start + 100]}


def _anexo(folio, semente, hora="2026-10-20T12h00h00Z", tarefa=None, desc="Inversor · GPS -20.1,-47.6 · 2026-10-20T09:00:00Z",
           n=0):
    """Cada anexo é um arquivo no S3 (o caminho é a identidade dele); `n` faz arquivos diferentes da mesma foto."""
    return {"description": desc, "value": f"https://s3.falso/{folio}/{semente}_{hora}_{n}.jpg?X-Amz-Signature=abc",
            "type": "image", "id_work_order_task": tarefa or int(folio) * 10 + 1, "wo_folio": folio}


@pytest.fixture
def fundo(app, tmp_path, monkeypatch):
    app.config.update(NEXUS_DADOS=str(tmp_path), NEXUS_PREFILTRO_PAUSA_S="0.5")
    s3 = S3Falso()
    monkeypatch.setattr(prefiltro_fundo, "baixar", s3)
    dormidas = []
    monkeypatch.setattr(prefiltro_fundo, "_dormir", dormidas.append)
    prefiltro_fundo.limpar()
    yield {"app": app, "s3": s3, "dormidas": dormidas, "dados": tmp_path}
    fracttal.usar_fornecedor(None)
    prefiltro_fundo.limpar()


def _usar(anexos):
    fx = FracttalAnexos(anexos)
    fracttal.usar_fornecedor(fx)
    return fx


def test_le_os_nova_uma_vez(fundo):
    fx = _usar({"15001": [_anexo("15001", 1), _anexo("15001", 2, "2026-10-23T08h00h00Z")]})
    linhas = [_tarefa(15001)]
    assert prefiltro_fundo.conferir(fundo["app"], linhas) == 1
    f = prefiltro_fundo.fatos(15001)
    assert [a["anexada"] for a in f["anexos"]] == ["2026-10-20T12:00:00Z", "2026-10-23T08:00:00Z"]
    assert f["pares"] == [] and f["erro"] == "" and all(len(a["id"]) == 16 for a in f["anexos"])
    assert f["anexos"][0]["desc"] == "Inversor" and f["anexos"][0]["print"] is False
    assert len(fx.pedidos) == 1 and len(fundo["s3"].pedidos) == 2
    assert prefiltro_fundo.conferir(fundo["app"], linhas) == 0 and len(fx.pedidos) == 1     # já conferida
    assert fundo["dormidas"] == [0.5]


def test_chave_mudou_rele(fundo):
    fx = _usar({"15001": [_anexo("15001", 1)]})
    prefiltro_fundo.conferir(fundo["app"], [_tarefa(15001)])
    assert prefiltro_fundo.conferir(fundo["app"], [_tarefa(15001), _tarefa(15001, 2)]) == 1     # tarefa nova na OS
    assert len(fx.pedidos) == 2


def test_teto_por_volta_e_a_mais_nova_primeiro(fundo):
    fundo["app"].config["NEXUS_PREFILTRO_POR_VOLTA"] = "2"
    _usar({})
    linhas = [_tarefa(15001, fim="2026-10-01T10:00:00"), _tarefa(15002, fim="2026-10-20T10:00:00"),
              _tarefa(15003, fim="2026-10-10T10:00:00")]
    assert prefiltro_fundo.conferir(fundo["app"], linhas) == 2
    assert prefiltro_fundo.fatos(15002) and prefiltro_fundo.fatos(15003) and prefiltro_fundo.fatos(15001) is None
    assert prefiltro_fundo.conferir(fundo["app"], linhas) == 1 and prefiltro_fundo.fatos(15001)


def test_recusa_para_a_volta_e_guarda_o_lido(fundo):
    fx = _usar({})
    fx.recusar_em = 1
    linhas = [_tarefa(15001, fim="2026-10-20T10:00:00"), _tarefa(15002, fim="2026-10-10T10:00:00")]
    assert prefiltro_fundo.conferir(fundo["app"], linhas) == 1
    assert prefiltro_fundo.fatos(15001) and prefiltro_fundo.fatos(15002) is None
    assert "429" in prefiltro_fundo.estado()["erro"]


def test_falha_no_s3_nao_guarda_a_os(fundo):
    _usar({"15001": [_anexo("15001", 1), _anexo("15001", 2)]})
    fundo["s3"].falhar.add(_anexo("15001", 2)["value"])
    assert prefiltro_fundo.conferir(fundo["app"], [_tarefa(15001)]) == 0
    assert prefiltro_fundo.fatos(15001) is None                    # meia leitura nunca vira "Pronta"


def test_pagina_os_com_mais_de_100_anexos(fundo):
    fx = _usar({"15001": [_anexo("15001", i % 50 + 1, n=i) for i in range(130)]})
    prefiltro_fundo.conferir(fundo["app"], [_tarefa(15001)])
    assert len(prefiltro_fundo.fatos(15001)["anexos"]) == 130
    assert [p.split("start=")[1] for p in fx.pedidos] == ["0", "100"]


def test_repetida_vira_par_e_ganha_miniatura(fundo):
    _usar({"15001": [_anexo("15001", 7), _anexo("15001", 8), _anexo("15001", 7, "2026-10-21T12h00h00Z")]})
    prefiltro_fundo.conferir(fundo["app"], [_tarefa(15001)])
    f = prefiltro_fundo.fatos(15001)
    ids = [a["id"] for a in f["anexos"]]
    assert f["pares"] == [[ids[0], ids[2]]]
    with fundo["app"].app_context():                               # a rota da foto chama dentro do pedido
        assert prefiltro_fundo.miniatura(ids[0]).exists() and prefiltro_fundo.miniatura(ids[2]).exists()
        assert prefiltro_fundo.miniatura(ids[1]) is None          # só das repetidas
        assert prefiltro_fundo.miniatura("../../.env") is None


def test_so_imagens_e_so_as_tarefas_da_fila(fundo):
    pdf = {**_anexo("15001", 1), "value": "https://s3.falso/15001/relatorio.pdf?x=1"}
    outra = _anexo("15001", 2, tarefa=999)
    _usar({"15001": [pdf, outra, _anexo("15001", 3)]})
    prefiltro_fundo.conferir(fundo["app"], [_tarefa(15001)])
    assert len(prefiltro_fundo.fatos(15001)["anexos"]) == 1


def test_captura_de_tela_e_marcada(fundo):
    _usar({"15001": [_anexo("15001", 1, desc="Coleta de geração")]})
    prefiltro_fundo.conferir(fundo["app"], [_tarefa(15001)])
    assert prefiltro_fundo.fatos(15001)["anexos"][0]["print"] is True


def test_fora_do_escopo_nao_e_lido(fundo):
    fx = _usar({})
    linhas = [_tarefa(15001, tasks_log_task_type_main="Religamento"),
              _tarefa(15002, labels=[{"description": "PERFORMANCE"}]), _tarefa(15003)]
    assert prefiltro_fundo.conferir(fundo["app"], linhas) == 1
    assert [p.split("folio=")[1].split("&")[0] for p in fx.pedidos] == ["15003"]


def test_os_que_saiu_da_fila_some_do_disco(fundo):
    _usar({"15001": [_anexo("15001", 7), _anexo("15001", 7, "2026-10-21T12h00h00Z")]})
    prefiltro_fundo.conferir(fundo["app"], [_tarefa(15001)])
    with fundo["app"].app_context():
        mini = prefiltro_fundo.miniatura(prefiltro_fundo.fatos(15001)["pares"][0][0])
    assert mini.exists()
    prefiltro_fundo.conferir(fundo["app"], [_tarefa(15002)])
    assert prefiltro_fundo.fatos(15001) is None and not mini.exists()


def test_ida_e_volta_do_disco(fundo):
    _usar({"15001": [_anexo("15001", 1)]})
    prefiltro_fundo.conferir(fundo["app"], [_tarefa(15001)])
    antes = prefiltro_fundo.fatos(15001)
    prefiltro_fundo.limpar()
    assert prefiltro_fundo.fatos(15001) is None
    assert prefiltro_fundo.carregar_do_disco(fundo["app"]) is True
    assert prefiltro_fundo.fatos(15001) == antes


def test_a_volta_roda_numa_thread_de_fundo_e_desliga(fundo, monkeypatch):
    """Fora dos testes, uma thread `nexus-prefiltro` por vez; `NEXUS_PREFILTRO=0` desliga."""
    import threading
    criadas = []

    class Thread:
        def __init__(self, target=None, daemon=None, name=None):
            self.name = name
            criadas.append(self)

        def start(self):
            pass
    monkeypatch.setattr(threading, "Thread", Thread)
    app = fundo["app"]
    app.config.update(TESTING=False, NEXUS_PREFILTRO="0")
    try:
        prefiltro_fundo.pedir_conferencia(app)
        assert criadas == []
        app.config["NEXUS_PREFILTRO"] = "1"
        prefiltro_fundo.pedir_conferencia(app)
        prefiltro_fundo.pedir_conferencia(app)             # já há uma andando: não abre outra
        assert [t.name for t in criadas] == ["nexus-prefiltro"]
    finally:
        app.config["TESTING"] = True


def test_a_releitura_da_fila_pede_a_conferencia(app, tmp_path, monkeypatch):
    """Depois de cada fila boa relida por trás, a volta do pré-filtro (as OS novas da fila)."""
    from test_campo_aprovacao import FracttalFalso

    from nexus.campo import aprovacao
    app.config.update(NEXUS_DADOS=str(tmp_path))
    fracttal.usar_fornecedor(FracttalFalso([_tarefa(15001)]))
    pedidos = []
    monkeypatch.setattr(prefiltro_fundo, "pedir_conferencia", pedidos.append)
    try:
        aprovacao._reler(app)
        assert pedidos == [app]
        aprovacao._preparar(app)                  # o boot com a fila do disco ainda nova também pede
        assert pedidos == [app, app]
    finally:
        fracttal.usar_fornecedor(None)
        aprovacao.limpar()


def test_a_volta_le_o_disco_antes_do_fracttal(fundo, monkeypatch):
    """Ao subir, a volta pode sair antes da carga do disco (a thread do boot): ela mesma carrega a cópia antes de ler, e
    as OS já conferidas não voltam ao Fracttal (sem isso, cada deploy relia a fila inteira)."""
    from nexus.campo import regras_app
    _usar({"15001": [_anexo("15001", 1)]})
    prefiltro_fundo.conferir(fundo["app"], [_tarefa(15001)])
    prefiltro_fundo.limpar()
    fx = _usar({"15001": [_anexo("15001", 1)]})
    monkeypatch.setitem(regras_app._FILA_CACHE, "linhas", [_tarefa(15001)])
    prefiltro_fundo._volta(fundo["app"])
    assert not [p for p in fx.pedidos if p.startswith("work_orders_attachments")]
    assert prefiltro_fundo.fatos(15001) is not None
