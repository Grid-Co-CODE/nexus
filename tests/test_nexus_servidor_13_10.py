"""Os 5 pontos do Levi com o Nexus no servidor (13/10/2026): a janela da Meta com "HTTP 500", a assinatura da PT que
"não achou a tarefa", a foto ampliada lenta, as fotos presas no "excesso de pedidos" do Fracttal e o servidor lento depois
de subir. Nenhum teste vai ao Fracttal nem ao banco de verdade."""
import io

import pytest
from test_campo_responsaveis import tela  # noqa: F401  (fixture)
from test_campo_visao import banco  # noqa: F401  (fixture)

from nexus.campo import nota_fracttal, pt_fracttal, ronda_fotos


# ── 1) a janela que quebra ao montar diz o erro dentro dela, e não "HTTP 500" ─────────────────────────────────────────
def test_janela_que_quebra_mostra_o_erro_e_nao_500(tela, logado, monkeypatch):  # noqa: F811
    from nexus.torres import campo as torre
    assert logado.get("/t/campo/responsaveis/usina/1/meta").status_code == 200

    def quebra(*a, **k):
        raise ValueError("valor que só o servidor tem")
    monkeypatch.setattr(torre, "_resp_painel_montar", quebra)
    r = logado.get("/t/campo/responsaveis/usina/1/meta")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Não consegui montar esta janela" in html
    assert "ValueError: valor que só o servidor tem" in html and "Meta do mês" in html
    monkeypatch.undo()
    assert logado.get("/t/campo/responsaveis/usina/999/meta").status_code == 404     # usina que não existe segue 404


# ── 2) a tarefa da PT: o nome vem em `description`; na preventiva, a finalizada primeiro ─────────────────────────────
def _tarefa(tid, codigo, status, desc="[Grid Co.] - MPM - QGBT"):
    return {"id_work_orders_tasks": tid, "code": codigo, "task_status": status, "description": desc,
            "tasks_description": None}


def test_tarefa_da_pt_pela_descricao_com_a_finalizada_primeiro(monkeypatch):
    # a OS 15067 de 13/10/2026: QGBT 1, 2 e 3 com a mesma descrição; só o 3 finalizado (o da PT)
    os_ = [_tarefa(59599049, "THPN-INP100-QGBT1", "NO_STARTED"), _tarefa(59599050, "THPN-INP100-QGBT2", "NO_STARTED"),
           _tarefa(59599051, "THPN-INP100-QGBT3", "DONE"), _tarefa(59599048, "THPN-INP100-PGINVR1", "DONE", "Outra")]
    monkeypatch.setattr(nota_fracttal, "tarefas_da_os", lambda os, ler=None: os_)
    assert pt_fracttal.tarefas_candidatas(15067, "[Grid Co.] - MPM - QGBT") == [59599051, 59599049, 59599050]
    assert pt_fracttal.tarefas_candidatas(15067, "[Grid Co.] - MPM - QGBT", "THPN-INP100-QGBT2") == [59599050]
    assert pt_fracttal.id_tarefa(15067, "[Grid Co.] - MPM - QGBT") is None               # três: o id único não chuta
    monkeypatch.setattr(nota_fracttal, "tarefas_da_os", lambda os, ler=None: os_[:1])
    assert pt_fracttal.tarefas_candidatas(1, "qualquer") == [59599049]                    # a única da OS


def test_a_assinatura_vem_da_primeira_candidata_que_tem(monkeypatch):
    pedidos = []

    def assinatura(numero, i, rpc):
        pedidos.append(i)
        if i == 1:
            raise pt_fracttal.SemArquivo("a APR desta tarefa não tem a assinatura do técnico")
        return f"data:image/png;base64,{i}"
    monkeypatch.setattr(pt_fracttal, "assinatura_do_tecnico", assinatura)
    assert pt_fracttal.assinatura_das_candidatas("PT-1", [1, 2, 3], rpc=None) == "data:image/png;base64,2"
    assert pedidos == [1, 2]
    with pytest.raises(pt_fracttal.SemArquivo):
        pt_fracttal.assinatura_das_candidatas("PT-2", [1], rpc=None)


# ── 3) a foto ampliada: versão de tela, guardada em disco, com cache do navegador ─────────────────────────────────────
def _png(lado=(1280, 1700)):
    """Uma "foto" com textura (a de cor única fica minúscula em PNG e a de tela não sairia menor: aí vai a original)."""
    from PIL import Image
    b = io.BytesIO()
    Image.effect_noise(lado, 48).convert("RGB").save(b, "PNG")
    return b.getvalue()


def test_foto_ampliada_vem_na_versao_de_tela_e_fica_em_disco(banco, logado, monkeypatch, tmp_path):  # noqa: F811
    from PIL import Image
    anexos = [{"description": "Sujidade dos módulos — 4", "value": "https://s3/b.png?assinatura=1"},
              {"description": "Altura da vegetação — 2", "value": "https://s3/c.png?assinatura=1"}]
    baixados = []
    monkeypatch.setattr(nota_fracttal, "anexos_da_os", lambda os_, ler=None: anexos)
    monkeypatch.setattr(ronda_fotos, "_baixar", lambda url: baixados.append(url) or _png())
    ronda_fotos.limpar()
    ronda_fotos.configurar(tmp_path)
    try:
        html = logado.get("/t/campo/rondas/os/500/fotos").get_data(as_text=True)
        v = ronda_fotos._id_arquivo("https://s3/b.png")[:10]
        assert f"/t/campo/rondas/os/500/foto/0?v={v}" in html and f"mini=1&amp;v={v}" in html
        r = logado.get(f"/t/campo/rondas/os/500/foto/0?v={v}")
        assert r.mimetype == "image/jpeg" and max(Image.open(io.BytesIO(r.data)).size) == 1600
        assert "immutable" in r.headers["Cache-Control"] and "max-age=604800" in r.headers["Cache-Control"]
        assert logado.get("/t/campo/rondas/os/500/foto/0?original=1").mimetype == "image/png"   # a inteira, se pedir
        n = len(baixados)
        ronda_fotos.limpar()                              # o reinício do deploy: a memória vai, o disco fica
        r = logado.get(f"/t/campo/rondas/os/500/foto/0?v={v}")
        assert r.status_code == 200 and len(baixados) == n                      # do disco, sem ir ao Fracttal
        nomes = sorted(p.name for p in tmp_path.iterdir())
        assert any(x.endswith("_t.jpg") for x in nomes) and any(x.endswith(".png") for x in nomes)
        # o mesmo arquivo com outro link assinado (a lista lida de novo) é a mesma chave: assinatura não entra
        assert ronda_fotos._id_arquivo("https://s3/b.png?assinatura=2") == ronda_fotos._id_arquivo("https://s3/b.png?x")
    finally:
        ronda_fotos.configurar(None)
        ronda_fotos.limpar()


def test_disco_passou_do_limite_as_mais_antigas_saem(tmp_path, monkeypatch):
    monkeypatch.setattr(ronda_fotos, "ARQUIVOS_MAX", 3)
    for i in range(5):
        (tmp_path / f"{i}.jpg").write_bytes(b"x")
        import os
        import time
        os.utime(tmp_path / f"{i}.jpg", (time.time() - 100 + i, time.time() - 100 + i))
    ronda_fotos._podar(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["2.jpg", "3.jpg", "4.jpg"]


# ── 4) o Fracttal recusou: o pedaço marca o erro, e a página tenta de novo (ao reabrir, sozinha e pelo botão) ─────────
def test_fotos_com_o_fracttal_recusando_marca_o_erro_para_tentar_de_novo(banco, logado, monkeypatch):  # noqa: F811
    def recusa(os_, ler=None):
        raise RuntimeError("HTTP 429 Too Many Requests")
    monkeypatch.setattr(nota_fracttal, "anexos_da_os", recusa)
    ronda_fotos.limpar()
    html = logado.get("/t/campo/rondas/os/501/fotos").get_data(as_text=True)
    assert 'data-erro="1"' in html and "excesso de pedidos" in html and 'class="cn-bt-tentar"' in html
    pag = logado.get("/t/campo/rondas/usina/1").get_data(as_text=True)
    assert "delete linha.dataset.carregada; esperar(b, linha)" in pag and "Tento de novo sozinho em" in pag
    assert ".cn-bt-tentar" in pag and "(new Image()).src = a.href" in pag          # e já pede a ampliada no passar do mouse


# ── 5) o estático com versão e guardado; a pré-carga ao subir ─────────────────────────────────────────────────────────
def test_estatico_com_versao_e_guardado_um_ano(app, logado, monkeypatch):
    from nexus import casca
    monkeypatch.setenv("NEXUS_COMMIT", "abc1234")
    casca._commit.cache_clear()
    try:
        assert "/static/nexus.css?v=" not in logado.get("/").get_data(as_text=True)   # nos testes, desligado
        app.config["NEXUS_ESTATICO_VERSAO"] = "1"
        html = logado.get("/").get_data(as_text=True)
        assert "/static/nexus.css?v=abc1234" in html
        r = logado.get("/static/nexus.css?v=abc1234")
        cc = r.headers["Cache-Control"]
        assert r.status_code == 200 and "max-age=31536000" in cc and "immutable" in cc and "no-cache" not in cc
        assert "max-age=31536000" not in (logado.get("/static/nexus.css").headers.get("Cache-Control") or "")
        app.config["NEXUS_ESTATICO_VERSAO"] = "0"
        assert "/static/nexus.css?v=" not in logado.get("/").get_data(as_text=True)   # a chave desliga
    finally:
        monkeypatch.delenv("NEXUS_COMMIT")
        casca._commit.cache_clear()


def test_pre_carga_ao_subir_aquece_as_telas(app, monkeypatch):
    from nexus.auth import pre_carga
    pedidas = []

    class NaHora:
        def __init__(self, target, **k):
            self.target = target

        def start(self):
            self.target()
    monkeypatch.setattr(pre_carga.threading, "Thread", NaHora)
    monkeypatch.setattr(pre_carga.time, "sleep", lambda s: None)
    monkeypatch.setattr(pre_carga, "lembrar", lambda telas: pedidas.append(list(telas)))
    pre_carga.aquecer_ao_subir(app, espera_s=0)
    assert pedidas == []                                           # nos testes a pré-carga fica desligada
    app.config["NEXUS_PRE_CARGA"] = "1"
    pre_carga.aquecer_ao_subir(app, espera_s=0)
    assert pedidas and pedidas[0] == pre_carga.aqueciveis(app) and "base/fracttal" not in pedidas[0]
    # a máquina que não lê o Fracttal ao subir não dá a volta (ela abriria as telas que pedem a leitura)
    pedidas.clear()
    app.config["NEXUS_CAMPO_AQUECER"] = "0"
    pre_carga.aquecer_ao_subir(app, espera_s=0)
    assert pedidas == []
    # e a espera padrão passa das leituras espaçadas da subida (a última, o Quadro, aos 210 s)
    import inspect
    assert inspect.signature(pre_carga.aquecer_ao_subir).parameters["espera_s"].default > 210
