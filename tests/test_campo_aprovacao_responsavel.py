"""A Aprovação de OS em quadro por fatos (Levi, 04/11/2026: "No nexus, em campo app crie uma aba de aprovação de OS. Pode
fazer por cima da aba Aprovação de OS, refaça com essas regras e deixe algo bem fácil e dinâmico para os supervisores!").

As decisões dele no quiz: todos os supervisores veem; "uma a uma pelo card, tem que ter um botão de aprovar logo após
todo o score e avisos, deve ser possível também aprovar mais que uma de uma vez!"; o quadro com três colunas (Pronta, Em
dúvida, Não OK); "religamento remoto ou religamento real não entra, nem OSs com etiqueta de performance!". As regras moram
em nexus/campo/prefiltro.py; os fatos das fotos, na leitura de fundo (prefiltro_fundo.py), postos aqui direto na memória.

Fracttal e banco falsos (o `fila` da Aprovação), com o Responsável O&M de cada usina na ficha: a Usina A (SP 01) é do
Ciclano Chefe (91), a Usina C (SC 01) do Beltrano Supervisor (90). No quadro: 16001 Pronta; 15088 Em dúvida (foto
repetida); 15002 Em dúvida (fechada fora do App); 15102 Não OK (foto anexada 2 dias depois do fechamento); 17001 fora do
pré-filtro (religamento)."""
import io
import re
import shutil
import subprocess
from datetime import datetime, timedelta

import pytest
from PIL import Image
from test_campo_aprovacao_supervisor import _sessao_nexus, _tarefa, fila  # noqa: F401  (fila é fixture)
from test_campo_visao import _aba

from nexus.campo import aprovacao, prefiltro_fundo, regras_app, verificacao, visao

ID = {"p1": "0123456789abcdef", "p2": "1123456789abcdef", "p3": "2123456789abcdef", "tarde": "3123456789abcdef",
      "ok": "4123456789abcdef"}


def _jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (24, 16), (90, 120, 150)).save(buf, "JPEG")
    return buf.getvalue()


def _hora(horas):
    """Agora + `horas`, em ISO UTC (a hora de anexação que a leitura de fundo guarda)."""
    return (datetime.utcnow() + timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fatos(id_wo, anexos, pares=()):
    """O que a leitura de fundo teria guardado da OS: as fotos (id, hora de anexação) e os pares repetidos."""
    prefiltro_fundo._FATOS[str(id_wo)] = {
        "chave": "x", "lido_em": 1.0, "erro": "", "pares": [list(p) for p in pares],
        "anexos": [{"id": i, "tarefa": "", "desc": "Inversor", "anexada": q, "print": False, "hash": "0" * 64}
                   for i, q in anexos]}


@pytest.fixture
def fila_resp(fila):  # noqa: F811
    _aba(fila.api, "cadastro_nexus", "usinas", [
        {"usina_id": 1, "nome": "Usina A", "status": "OPERAÇÃO", "equipe_id": 10, "data_mobilizacao": "2025-01-01",
         "uf": "SP", "gestor_contrato_id": 90, "responsavel_om_id": 91, "cliente_id": 1},
        {"usina_id": 3, "nome": "Usina C", "status": "OPERAÇÃO", "equipe_id": 20, "data_mobilizacao": "2025-01-01",
         "uf": "SC", "gestor_contrato_id": 91, "responsavel_om_id": 90, "cliente_id": 1}])
    _aba(fila.api, "cadastro_nexus", "clientes", [{"cliente_id": 1, "nome": "Thopen"}])
    visao.limpar()
    return fila


@pytest.fixture
def quadro(fila_resp, app, tmp_path):
    """A fila com os fatos das fotos já lidos. O fechamento no App de 15088, 15102 e 16001 foi há 24 h (o `server_ts` da
    nota); as fotos "no prazo" foram anexadas 4 h depois dele, a de 15102 48 h depois."""
    app.config.update(NEXUS_DADOS=str(tmp_path))
    aprovacao.limpar()
    prefiltro_fundo.limpar()
    verificacao.limpar()
    fila_resp.linhas.append({**_tarefa(17001, 2, "SP 01"), "tasks_log_task_type_main": "Religamento Remoto"})
    _fatos(15088, [(ID["p1"], _hora(-20)), (ID["p2"], _hora(-20)), (ID["p3"], _hora(-20))], [(ID["p1"], ID["p3"])])
    _fatos(15102, [(ID["tarde"], _hora(24))])
    _fatos(16001, [(ID["ok"], _hora(-20))])
    # a leitura rápida (as respostas e o GPS, 05/11/2026) feita e sem nada em toda OS da fila: estes testes são das
    # regras das fotos; as regras novas têm o teste delas (test_campo_prefiltro_sinais_0511.py)
    for w in fila_resp.linhas:
        prefiltro_fundo._META[str(w["id_work_order"])] = {"v": prefiltro_fundo.META_V, "chave": "x", "lido_em": 1.0,
                                                           "fotos": [], "vazias": [], "faltando": []}
    fotos = tmp_path / "campo" / "prefiltro_fotos"
    fotos.mkdir(parents=True)
    for i in (ID["p1"], ID["p3"]):
        (fotos / f"{i}.jpg").write_bytes(_jpeg())
    yield fila_resp
    prefiltro_fundo.limpar()
    aprovacao.limpar()


def _coluna(html, coluna):
    m = re.search(rf'<section class="apq-coluna"[^>]*data-coluna="{coluna}".*?</section>', html, re.S)
    return m.group(0) if m else ""


def _folios(trecho):
    return re.findall(r'<article class="apq-cartao"[^>]*data-folio="(\d+)"', trecho)


def _cartao(html, folio):
    m = re.search(rf'<article class="apq-cartao"[^>]*data-folio="{folio}".*?</article>', html, re.S)
    return m.group(0) if m else ""


def _bloco(html, id_):
    m = re.search(rf'<details[^>]*id="{id_}".*?</details>', html, re.S)
    return m.group(0) if m else ""


def test_o_quadro_tem_as_tres_colunas_com_o_numero(quadro, logado):
    html = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    assert re.findall(r'<section class="apq-coluna"[^>]*data-coluna="(\w+)"', html) == ["pronta", "duvida", "nao_ok"]
    assert _folios(_coluna(html, "pronta")) == ["16001"]
    assert _folios(_coluna(html, "duvida")) == ["15002", "15088"]          # a que espera há mais tempo primeiro
    assert _folios(_coluna(html, "nao_ok")) == ["15102"]
    for coluna, n in (("pronta", 1), ("duvida", 2), ("nao_ok", 1)):
        assert re.search(rf'data-apq-n>{n}<', _coluna(html, coluna)), coluna
    for folio, coluna in (("16001", "pronta"), ("15088", "duvida"), ("15102", "nao_ok")):
        assert f'data-coluna="{coluna}"' in _cartao(html, folio).split(">")[0]
    # a tela de antes saiu inteira: a lista por usina, os indicadores e a barra da idade
    for velho in ('class="ap-usinas"', 'class="cn-idades"', "?balde=", "?idade=", "Usinas com OS esperando aprovação"):
        assert velho not in html, velho


def test_o_cartao_traz_o_score_os_avisos_e_logo_depois_o_aprovar(quadro, logado):
    html = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    c = _cartao(html, "15088")
    assert 'data-wo="15088"' in c and "Usina A" in c and "Thopen" in c and "2 tarefas" in c
    assert c.index('class="apq-score') < c.index('class="apq-avisos"') < c.index("data-apq-aprovar")
    score = c[c.index('class="apq-score'):c.index('class="apq-avisos"')]
    assert "Nota do App" in score and ">71<" in score
    avisos = c[c.index('class="apq-avisos"'):c.index("data-apq-aprovar")]
    assert "Já foi devolvida" in avisos
    # o fato que decide a coluna fica no motivo em destaque, no topo (2ª rodada, 05/11/2026); o nome das fotos fica na
    # barra lateral da OS (3ª rodada: "poupa informação inicial e vai aprofundando"). A nota do App abaixo de 80 é um
    # desses motivos desde 09/11/2026 (o caso da OS 8159), com o porquê, e não se repete nos avisos
    motivo = c[c.index('class="apq-motivo"'):c.index('class="apq-score')]
    assert "Foto repetida: p03 é a mesma imagem de p01" in motivo and "Nota do App 71%, abaixo de 80%" in motivo
    assert "Nota do App 71%" not in avisos
    assert "<img" not in c and "/t/campo/aprovacao/foto/" not in c and 'class="apq-foto"' not in c
    nao_ok = _cartao(html, "15102")
    assert "1 foto anexada 2 dias depois do fechamento no App" in nao_ok and "data-apq-aprovar" in nao_ok
    fora_do_app = _cartao(html, "15002")
    # fechada inteira fora do App: as fotos não mudam a coluna e não são esperadas (05/11/2026)
    assert "1 tarefa fechada fora do App" in fora_do_app and "Faltam fotos por ler" not in fora_do_app
    assert "Fora do App" in fora_do_app[fora_do_app.index('class="apq-score'):]


def test_marcar_para_o_lote_so_em_pronta_e_em_duvida(quadro, logado):
    html = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    for folio in ("16001", "15088"):
        assert "data-apq-marcar" in _cartao(html, folio), folio
    assert "data-apq-marcar" not in _cartao(html, "15102")
    # a 15002 (fechada inteira fora do App) não espera foto desde 05/11/2026: entra no lote como as outras
    assert "data-apq-marcar" in _cartao(html, "15002")
    assert "data-apq-lote" in html and "Aprovar as marcadas" in html
    for coluna in ("pronta", "duvida"):
        assert "data-apq-todas" in _coluna(html, coluna)
    assert "data-apq-todas" not in _coluna(html, "nao_ok")


def test_fora_do_pre_filtro_aparece_com_o_motivo_e_aprova_pelo_cartao(quadro, logado):
    html = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    fora = _bloco(html, "apq-fora")
    assert _folios(fora) == ["17001"] and "Religamento" in fora
    c = _cartao(fora, "17001")
    assert "data-apq-aprovar" in c and "data-apq-marcar" not in c
    assert all("17001" not in _folios(_coluna(html, k)) for k in ("pronta", "duvida", "nao_ok"))


def test_ainda_conferindo_as_fotos(quadro, logado):
    prefiltro_fundo._FATOS.pop("16001")
    html = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    conferindo = _bloco(html, "apq-conferindo")
    assert _folios(conferindo) == ["16001"] and _folios(_coluna(html, "pronta")) == []
    c = _cartao(conferindo, "16001")
    assert "data-apq-aprovar" in c and "data-apq-marcar" not in c


def test_o_filtro_e_o_responsavel_da_usina(quadro, logado):
    html = logado.get("/t/campo/aprovacao?responsavel=Beltrano+Supervisor").get_data(as_text=True)
    assert _folios(html) == ["16001"] and '<option value="Beltrano Supervisor" selected>' in html
    todos = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    assert sorted(_folios(todos)) == ["15002", "15088", "15102", "16001", "17001"]


def test_o_responsavel_do_login_ja_vem_no_filtro(quadro, cliente):
    # quem entrou pelo Fracttal e é Responsável O&M (a pessoa 91 na ficha da Usina A) abre nas usinas dele
    _sessao_nexus(cliente, papel={"pessoa_id": 91, "nome": "Ciclano Chefe", "papel": "gestor", "gestor": "Ciclano Chefe"})
    cliente.get("/t/campo/aprovacao?responsavel=*")               # nos testes a releitura roda na hora
    html = cliente.get("/t/campo/aprovacao").get_data(as_text=True)
    assert '<option value="Ciclano Chefe" selected>' in html and "16001" not in _folios(html)
    assert "15088" in _folios(html)


def test_cliente_e_busca_respondem_na_pagina(quadro, logado):
    html = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    assert re.search(r'<select[^>]*data-apq-cliente[^>]*>.*?<option value="Thopen">Thopen</option>', html, re.S)
    assert re.search(r'<input[^>]*data-apq-busca', html)
    c = _cartao(html, "15088").split(">")[0]
    assert 'data-cliente="Thopen"' in c and re.search(r'data-busca="[^"]*15088[^"]*usina a', c)


def test_o_script_aprova_pelo_concluir_do_os_creator(quadro, logado):
    html = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    js = next(s for s in re.findall(r"<script>(.*?)</script>", html, re.S) if "data-apq-aprovar" in s)
    assert "nexusRota('/os/api/os/')" in js and "'/concluir'" in js and "folio: folio" in js
    assert "nexusRota('/t/campo/aprovacao/')" in js and "'/conferir'" in js
    assert "status === 401" in js and "confirm(" in js
    assert "NexusOsCard.abrir(" in js and "'Em Verificação'" in js         # a OS também abre o card do OS Creator


@pytest.mark.skipif(not shutil.which("node"), reason="sem node nesta máquina")
def test_o_script_da_tela_e_javascript_valido(quadro, logado, tmp_path):
    """Até 08/10 o confirm() do Aprovar tinha uma quebra de linha DENTRO da string: o script inteiro não rodava."""
    html = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    js = next(s for s in re.findall(r"<script>(.*?)</script>", html, re.S) if "data-apq-aprovar" in s)
    arq = tmp_path / "aprovacao.js"
    arq.write_text(js, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(arq)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_a_rota_da_miniatura_saiu(quadro, logado):
    """Sem miniatura guardada (05/11/2026), a rota que a servia saiu: o nome da foto abre o card da OS."""
    assert logado.get(f"/t/campo/aprovacao/foto/{ID['p1']}").status_code == 404


def test_o_csv_tem_a_coluna_e_os_motivos(quadro, logado):
    texto = logado.get("/t/campo/aprovacao?responsavel=Ciclano+Chefe&csv=1").get_data(as_text=True)
    cab = texto.splitlines()[0].lstrip("﻿").split(";")
    assert cab[:8] == ["OS", "Dias esperando", "Criação da OS", "Data fim", "Responsável O&M", "Usina", "Cliente",
                       "Técnicos"]
    assert cab[-2:] == ["Coluna", "Motivos"]
    linhas = {l.split(";")[0]: l for l in texto.splitlines()[1:]}
    assert linhas["15088"].startswith("15088;8;31/08/26;") and ";Ciclano Chefe;Usina A;Thopen;" in linhas["15088"]
    assert ";Em dúvida;" in linhas["15088"] and "Foto repetida: p03 é a mesma imagem de p01" in linhas["15088"]
    assert ";Não OK;" in linhas["15102"] and "1 foto anexada 2 dias depois do fechamento no App" in linhas["15102"]
    assert ";Fora do pré-filtro (Religamento);" in linhas["17001"]
    assert "16001" not in linhas                                            # é do outro responsável


def test_conferir_tira_da_fila_so_o_que_o_fracttal_confirma(quadro, logado):
    """Depois do Aprovar (o Concluir do OS Creator), a tela pede ao Nexus para conferir: só sai da fila guardada a OS que
    o Fracttal já não tem em verificação (1 pedido de leitura). Ninguém esconde OS da fila (o porquê de a rota /tirar ter
    saído em 08/10)."""
    logado.get("/t/campo/aprovacao")
    r = logado.post("/t/campo/aprovacao/15102/conferir")
    assert r.status_code == 200 and r.get_json() == {"saiu": False}       # o Fracttal ainda tem a OS em verificação
    assert aprovacao.os_na_fila(15102)
    quadro.linhas = [w for w in quadro.linhas if w["id_work_order"] != 15102]    # o Aprovar concluiu
    r = logado.post("/t/campo/aprovacao/15102/conferir")
    assert r.get_json() == {"saiu": True} and aprovacao.os_na_fila(15102) is None
    assert 'data-wo="15102"' not in logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    assert logado.post("/t/campo/aprovacao/15088/conferir", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert logado.post("/t/campo/aprovacao/77777/conferir").get_json() == {"saiu": True}      # já não está na fila


def test_a_visita_nao_refaz_a_conta_nem_le_o_fracttal_ou_o_s3(quadro, logado, monkeypatch):
    """"Está demorando muito para carregar": a conta das regras do App é feita uma vez por fila lida, e os fatos das fotos
    vêm da memória da leitura de fundo; a visita não lê o Fracttal nem baixa foto."""
    from nexus.campo import leitura
    logado.get("/t/campo/aprovacao")
    contas, baixadas = [], []
    original = regras_app._fila_supervisao
    monkeypatch.setattr(regras_app, "_fila_supervisao", lambda *a, **k: contas.append(1) or original(*a, **k))
    monkeypatch.setattr(leitura, "TTL_S", 0)
    monkeypatch.setattr(prefiltro_fundo, "baixar", lambda url: baixadas.append(url))
    pedidos = len(quadro.pedidos)
    for q in ("", "?responsavel=Beltrano+Supervisor", "?responsavel=Ciclano+Chefe", "?responsavel=*",
              "?responsavel=*&csv=1"):
        assert logado.get("/t/campo/aprovacao" + q).status_code == 200
    assert contas == [] and baixadas == [] and len(quadro.pedidos) == pedidos


def test_a_rota_antiga_do_aprovar_saiu(quadro, logado):
    """Levi, 18/10/2026: "pode tirar a rota antiga!". Aprovar é o Concluir do OS Creator; o portão do Aprovar do Nexus
    (`/os/_nexus/aprovacao/<id>/aprovar`) não volta."""
    logado.get("/t/campo/aprovacao")
    assert logado.post("/os/_nexus/aprovacao/15088/aprovar", json={}).status_code == 404
    assert aprovacao.os_na_fila(15088)                        # nada foi aprovado nem tirado da fila


def test_criada_pelo_cos_fica_fora_pela_ultima_conta_do_cos(quadro, logado):
    """A OS criada pelo COS fica fora (a regra das OSs em verificação do Painel), por quem é do COS na última conta (a da
    leitura de fundo): a visita não lê o banco nem o Fracttal para saber."""
    import time
    quadro.linhas.append({**_tarefa(17002, 1, "SP 01"), "code_create_by": "c7"})
    verificacao._COS.update(t=time.time(), v={"codigos": {"C7"}, "nomes": set(), "pessoas": 1, "erro": ""})
    html = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    fora = _bloco(html, "apq-fora")
    assert "17002" in _folios(fora) and "Criada pelo COS" in _cartao(fora, "17002")


# ── a revisão final (05/11/2026) ────────────────────────────────────────────────────────────────────────────────────
def test_ainda_conferindo_diz_que_as_fotos_nao_foram_conferidas(quadro, logado):
    """Nas primeiras horas, a maior parte da fila está em "Ainda conferindo": o cartão diz o que falta, não "Nenhum fato
    contra" em verde (dado pela metade não vai para a tela como se estivesse inteiro)."""
    prefiltro_fundo._FATOS.pop("16001")
    c = _cartao(_bloco(logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True), "apq-conferindo"), "16001")
    assert "Fotos ainda não conferidas" in c and "Nenhum fato contra" not in c


def test_o_cartao_diz_quando_as_fotos_foram_conferidas(quadro, logado):
    html = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    assert "fotos conferidas em" in _cartao(html, "15088") and "fotos conferidas em" not in _cartao(html, "15002")


def test_com_fotos_por_ler_nao_entra_no_lote(quadro, logado):
    """A OS em dúvida com fotos ainda por ler pode virar Não OK depois da leitura: aprova pelo cartão, não no lote. A OS
    fechada inteira fora do App não espera foto (elas não mudam a coluna): entra no lote (05/11/2026)."""
    c = _cartao(logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True), "15002")
    assert "Faltam fotos por ler" not in c and "data-apq-marcar" in c and "data-apq-aprovar" in c


def test_o_lote_tem_ritmo_e_para_no_que_se_repetiria(quadro, logado):
    """Cada aprovação custa 5 a 7 pedidos ao Fracttal (a cota de 200/min é da empresa): uma OS a cada 4 s. O lote para
    no que se repetiria em todas: o login do Fracttal (401), o acesso (403), o Fracttal recusando (429, 5xx), a sessão do
    Nexus que acabou (o fetch segue o 302 para /entrar e recebe 200 em HTML: isso NÃO é "aprovada") e 3 erros seguidos."""
    html = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    js = next(s for s in re.findall(r"<script>(.*?)</script>", html, re.S) if "data-apq-aprovar" in s)
    assert "PAUSA_LOTE_MS = 4000" in js and "setTimeout(proxima, PAUSA_LOTE_MS)" in js
    assert "r.ok && !r.redirected && r.j.ok === true" in js
    assert "r.status === 401" in js and "r.status === 403 || r.status === 429 || r.status >= 500" in js
    assert "seguidos >= 3" in js and "A sua sessão do Nexus acabou" in js
    assert "r.j.mensagem" in js                                  # a frase do OS Creator, não "true" do aviso
    assert "loteMsg.innerHTML" not in js                         # o número da OS entra como texto


def test_aprovar_varias_regrava_a_fila_uma_vez_por_vez(quadro, logado, monkeypatch, app):
    """Cada OS aprovada sai da fila guardada e a cópia em disco é regravada (~1,5 s com a fila real). No lote, as
    gravações se sobrepunham no mesmo .tmp: agora uma por vez, e a que chega durante outra só marca que falta gravar."""
    logado.get("/t/campo/aprovacao")
    gravadas = []
    monkeypatch.setattr(aprovacao, "_gravar_no_disco", lambda: gravadas.append(1))
    aprovacao._GRAVA.update(rodando=True, sujo=False)                    # uma gravação andando
    try:
        with app.app_context():                      # como na conferência (a rota): a regravação precisa do app
            aprovacao.tirar_da_fila(15102)
            aprovacao.tirar_da_fila(15088)
        assert gravadas == [] and aprovacao._GRAVA["sujo"] is True
    finally:
        aprovacao._GRAVA.update(rodando=False, sujo=False)
    with app.app_context():
        aprovacao.tirar_da_fila(16001)
    assert gravadas == [1] and aprovacao._GRAVA == {"rodando": False, "sujo": False}
