"""As regras do pré-filtro da Aprovação de OS (Levi, 04/11/2026: "vamos se basear na interpretação dos fatos"; "sem
interpretar fotos e sim fatos"). Medido nas 30 OS da medição de 26/10: foto anexada mais de 24 h depois do fechamento no
App pegou 4 devolvidas e nenhuma aprovada; a foto repetida, comparada sem o carimbo do App, 11 devolvidas e 6 aprovadas;
"menos de 5 min no App" e "subtarefas respondidas" não separaram e ficaram de fora."""
import random

from PIL import Image, ImageDraw

from nexus.campo import prefiltro

P = prefiltro.parametros({})


def _foto(semente, carimbo="", tamanho=(800, 600)):
    """Uma "foto" sintética (retângulos de tons ao acaso) com o carimbo do App no pé: a faixa escura com o texto."""
    rnd = random.Random(semente)
    im = Image.new("RGB", tamanho, (rnd.randint(0, 255),) * 3)
    d = ImageDraw.Draw(im)
    for _ in range(40):
        x, y = rnd.randint(0, tamanho[0]), rnd.randint(0, tamanho[1])
        d.rectangle([x, y, x + rnd.randint(30, 300), y + rnd.randint(30, 200)], fill=tuple(rnd.randint(0, 255) for _ in "rgb"))
    if carimbo:
        h = tamanho[1]
        d.rectangle([0, int(h * 0.8), tamanho[0], h], fill=(10, 10, 10))
        for i in range(4):
            d.text((10, int(h * 0.8) + 8 + 22 * i), f"{carimbo} linha {i}", fill=(250, 250, 250))
    return im


def _anexo(id_, h, imprime=False):
    return {"id": id_, "hash": h, "print": imprime}


def _os(*tarefas):
    return {"os": "1", "tarefas": list(tarefas)}


def _tarefa(pelo_app=True, qualidade=95, **k):
    return {"pelo_app": pelo_app, "qualidade": qualidade, "foi_devolvida": False, "foto_divergente": False,
            "ronda": False, "falhas": None, "estouro_causa": None, **k}


def _fatos(anexos, pares=()):
    return {"chave": "x", "lido_em": 1.0, "anexos": anexos, "pares": [list(p) for p in pares], "erro": ""}


FECHADO = "2026-10-05T16:21:15.362Z"


def _classificar(o, fatos, fechado, p, meta=None):
    """A leitura rápida (as respostas e o GPS, 05/11/2026) dada como feita e sem nada: estes testes são das regras das
    fotos. As regras novas e a OS sem a leitura rápida: test_campo_prefiltro_sinais_0511.py."""
    return prefiltro.classificar(o, fatos, fechado, p, {} if meta is None else meta)


def _anexada(horas_depois):
    from datetime import datetime, timedelta, timezone
    base = datetime(2026, 10, 5, 16, 21, 15, tzinfo=timezone.utc)
    return (base + timedelta(hours=horas_depois)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── a foto repetida, sem o carimbo do App ───────────────────────────────────────────────────────────────────────────
def test_mesma_foto_com_carimbo_diferente_e_repetida():
    a = prefiltro.dhash(_foto(7, "05/10/2026 08:30 · GPS -20.1,-47.6 · campo Inversor"))
    b = prefiltro.dhash(_foto(7, "07/10/2026 14:02 · GPS -20.1,-47.6 · campo Disjuntor"))
    assert bin(a ^ b).count("1") <= P["dif"]
    assert prefiltro.pares_repetidos([_anexo("1", a), _anexo("2", b)], P["dif"], P["dif_print"]) == [["1", "2"]]


def test_fotos_diferentes_nao_sao_repetidas():
    hs = [prefiltro.dhash(_foto(s, "carimbo")) for s in (1, 2, 3)]
    assert prefiltro.pares_repetidos([_anexo(str(i), h) for i, h in enumerate(hs)], P["dif"], P["dif_print"]) == []


def test_print_parecido_nao_e_repetido_mas_foto_de_camera_e():
    """Telas parecidas (os prints de geração do mês) enganam: com 6 pontos de diferença em 256, foto de câmera é a
    mesma, captura de tela não."""
    a, b = 0, 0b111111
    assert prefiltro.pares_repetidos([_anexo("1", a), _anexo("2", b)], P["dif"], P["dif_print"]) == [["1", "2"]]
    assert prefiltro.pares_repetidos([_anexo("1", a, True), _anexo("2", b, True)], P["dif"], P["dif_print"]) == []
    assert prefiltro.pares_repetidos([_anexo("1", a, True), _anexo("2", 0b11, True)], P["dif"], P["dif_print"]) == [["1", "2"]]


def test_cada_foto_repetida_aponta_a_primeira_igual():
    pares = prefiltro.pares_repetidos([_anexo("1", 0), _anexo("2", (1 << 256) - 1), _anexo("3", 1), _anexo("4", 0)],
                                      P["dif"], P["dif_print"])
    assert pares == [["1", "3"], ["1", "4"]]


# ── a coluna da OS ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_anexada_mais_de_24h_depois_e_nao_ok():
    fatos = _fatos([{"id": "1", "anexada": _anexada(25)}, {"id": "2", "anexada": _anexada(1)}])
    r = _classificar(_os(_tarefa()), fatos, FECHADO, P)
    assert r["coluna"] == "nao_ok" and r["tarde"] == 1
    aviso = r["avisos"][0]
    assert aviso["nivel"] == "critico" and aviso["texto"] == "1 foto anexada 1 dia depois do fechamento no App"
    assert aviso["fotos"] == ["1"]


def test_varias_anexadas_dias_depois():
    fatos = _fatos([{"id": str(i), "anexada": _anexada(52)} for i in range(6)])
    r = _classificar(_os(_tarefa()), fatos, FECHADO, P)
    assert r["coluna"] == "nao_ok" and r["avisos"][0]["texto"] == "6 fotos anexadas 2 dias depois do fechamento no App"


def test_23h_depois_nao_dispara():
    r = _classificar(_os(_tarefa()), _fatos([{"id": "1", "anexada": _anexada(23)}]), FECHADO, P)
    assert r["coluna"] == "pronta" and r["tarde"] == 0


def test_repetida_e_em_duvida():
    anexos = [{"id": "a1", "anexada": _anexada(0)}, {"id": "a2", "anexada": _anexada(0)}, {"id": "a3", "anexada": _anexada(0)}]
    r = _classificar(_os(_tarefa()), _fatos(anexos, [("a1", "a3")]), FECHADO, P)
    assert r["coluna"] == "duvida" and r["repetidas"] == 1
    aviso = r["avisos"][0]
    assert aviso["nivel"] == "alerta" and aviso["texto"] == "Foto repetida: p03 é a mesma imagem de p01"
    assert aviso["fotos"] == ["a1", "a3"]


def test_varias_repetidas_num_aviso_so():
    anexos = [{"id": f"a{i}", "anexada": _anexada(0)} for i in range(1, 6)]
    r = _classificar(_os(_tarefa()), _fatos(anexos, [("a1", "a3"), ("a2", "a5")]), FECHADO, P)
    assert r["avisos"][0]["texto"] == "2 fotos repetidas: p03 = p01, p05 = p02"
    assert r["avisos"][0]["fotos"] == ["a1", "a3", "a2", "a5"]


def test_nao_ok_ganha_da_duvida():
    anexos = [{"id": "a1", "anexada": _anexada(30)}, {"id": "a2", "anexada": _anexada(30)}]
    r = _classificar(_os(_tarefa()), _fatos(anexos, [("a1", "a2")]), FECHADO, P)
    assert r["coluna"] == "nao_ok" and [a["nivel"] for a in r["avisos"][:2]] == ["critico", "alerta"]


def test_fora_do_app_e_em_duvida():
    r = _classificar(_os(_tarefa(pelo_app=False, qualidade=None)), _fatos([]), "", P)
    assert r["coluna"] == "duvida"
    assert r["avisos"][0]["texto"] == "1 tarefa fechada fora do App: sem as fotos e os horários do App para conferir"


def test_sem_fatos_e_conferindo():
    assert _classificar(_os(_tarefa()), None, FECHADO, P)["coluna"] == "conferindo"


def test_fato_com_fotos_por_ler_vai_para_a_coluna_pior():
    """A OS mista (uma tarefa fora do App, outra pelo App) com as fotos por ler: Em dúvida já, e as fotos da tarefa do App
    ainda podem pôr Não OK."""
    r = _classificar(_os(_tarefa(pelo_app=False, qualidade=None, id_wt=1), _tarefa(id_wt=2)), None, FECHADO, P)
    assert r["coluna"] == "duvida"
    assert any(a["texto"] == "Faltam fotos por ler" for a in r["avisos"])


def test_os_inteira_fora_do_app_nao_espera_as_fotos():
    """05/11/2026 ("Tem 730 OSs conferindo fotos, veja se travou algo"): 522 OS fechadas inteiras fora do App esperavam
    a leitura das fotos, que não muda a coluna delas (Em dúvida pela tarefa fora do App; a foto atrasada só se mede
    contra o fechamento no App, que elas não têm). Sem "Faltam fotos por ler": entram no lote como as outras."""
    r = _classificar(_os(_tarefa(pelo_app=False, qualidade=None)), None, "", P)
    assert r["coluna"] == "duvida" and [a["tipo"] for a in r["avisos"]] == ["fora_app"]


def test_avisos_da_regra_do_app_nao_mudam_a_coluna():
    # a devolvida (e a foto divergente, a ronda com pendência) é aviso; a coluna é dos fatos
    r = _classificar(_os(_tarefa(qualidade=90, foi_devolvida=True)), _fatos([]), FECHADO, P)
    assert r["coluna"] == "pronta" and any("devolvida" in a["texto"] for a in r["avisos"])
    # a nota do App abaixo de 80 deixou de ser só aviso em 09/11/2026 (o caso da OS 8159, em Pronta com nota 50): é
    # motivo de Em dúvida, com o porquê (test_campo_aprovacao_nota_0911)
    r = _classificar(_os(_tarefa(qualidade=60, foi_devolvida=True)), _fatos([]), FECHADO, P)
    textos = [a["texto"] for a in r["avisos"]]
    assert r["coluna"] == "duvida" and any(t.startswith("Nota do App 60%, abaixo de 80%") for t in textos)
    assert any("devolvida" in t for t in textos)


def test_sem_hora_de_fechamento_nao_julga_a_anexacao():
    r = _classificar(_os(_tarefa()), _fatos([{"id": "1", "anexada": _anexada(99)}]), "", P)
    assert r["coluna"] == "pronta" and r["tarde"] == 0


# ── o escopo ────────────────────────────────────────────────────────────────────────────────────────────────────────
def _crua(**k):
    return {"tasks_log_task_type_main": "Corretiva", "description": "Troca de fusível", "labels": [], **k}


def test_escopo():
    cos = {"codigos": {"C7"}, "nomes": {"PESSOA DO COS"}}
    casos = [
        ([_crua(tasks_log_task_type_main="Religamento")], "Religamento"),
        ([_crua(tasks_log_task_type_main="Religamento Remoto")], "Religamento"),
        ([_crua(description="[Cabine 1] - Religamento da cabine 1")], "Religamento"),
        ([_crua(labels=[{"description": "PERFORMANCE"}])], "PERFORMANCE"),
        ([_crua(labels=[{"description": "Chamados"}])], "CHAMADOS"),
        ([_crua(labels=[{"description": "ENGENHARIA"}])], ""),          # entra (Levi, 05/11/2026)
        ([_crua(code_create_by="c7")], "Criada pelo COS"),
        ([_crua(), _crua(tasks_log_task_type_main="Religamento")], "Religamento"),
        ([_crua(labels=[{"description": "REMOTO"}])], ""),
        ([_crua()], ""),
    ]
    for cruas, esperado in casos:
        assert prefiltro.fora_do_escopo(cruas, cos) == esperado, cruas
    assert prefiltro.fora_do_escopo([_crua(code_create_by="c7")], None) == ""


def test_parametros_do_config():
    p = prefiltro.parametros({"NEXUS_PREFILTRO_HORAS_TARDE": "48", "NEXUS_PREFILTRO_DIF": 9})
    assert p["horas_tarde"] == 48 and p["dif"] == 9 and p["dif_print"] == 4 and p["por_volta"] == 150 and p["pausa_s"] == 2


def test_fechado_app_e_o_ultimo_fechamento_da_os():
    """A hora do fechamento é a da OS: o ÚLTIMO fechamento das tarefas dela no App (a hora do celular, `dev_ts`; sem ela,
    a do servidor), na linha da fila da Aprovação (`fila_toda`). Foto anexada mais de 24 h depois dele é Não OK."""
    from datetime import datetime, timezone

    from test_campo_aprovacao import FracttalFalso, _nota, _os
    from test_campo_regras_app import TabelaFalsa

    from nexus.campo import aprovacao, fracttal, leitura, tabelas
    so_servidor = _nota(15088, 71)
    dados = {"qualidadelog": [
        dict(_nota(15102, 96), RowKey="q1", dev_ts="2026-10-20T12:00:00Z", server_ts="2026-10-20T12:00:00"),
        dict(_nota(15102, 90), RowKey="q2", dev_ts="2026-10-21T08:30:00.000Z",       # a última tarefa fechada da OS
             server_ts="2026-10-21T08:30:00"),                                       # (com sinal: chega na hora)
        so_servidor]}                                                               # sem a hora do celular
    tabelas.usar_fornecedor(lambda nome: TabelaFalsa(dados.setdefault(nome, [])))
    fracttal.usar_fornecedor(FracttalFalso([_os(15002, 33), _os(15088, 8), _os(15102, 4)]))
    leitura.limpar_cache()
    try:
        linhas = aprovacao.fila_toda({"dias": "60"}).dados["linhas"]
    finally:
        tabelas.usar_fornecedor(None)
        fracttal.usar_fornecedor(None)
        leitura.limpar_cache()
    por_os = {x["os"]: x["fechado_app"] for x in linhas}
    assert prefiltro._quando(por_os["15102"]) == datetime(2026, 10, 21, 8, 30, tzinfo=timezone.utc)
    assert prefiltro._quando(por_os["15088"]) == prefiltro._quando(so_servidor["server_ts"])
    assert por_os["15002"] == ""                    # fechada fora do App: sem hora, a anexação não é julgada


def test_sem_o_registro_do_app_a_hora_fica_vazia(monkeypatch):
    """O registro do App que não abre não derruba a fila: a hora do fechamento fica vazia (a anexação não é julgada)."""
    from nexus.campo import aprovacao, regras_app

    def quebra():
        raise ConnectionError("tabela fora")
    monkeypatch.setattr(regras_app, "tabela_qlog", quebra)
    assert aprovacao._ultimo_fechamento_no_app() == {}


def test_cada_aviso_diz_o_tipo_e_a_repetida_traz_os_pares():
    """O cartão do quadro mostra a prova pelo tipo do aviso: o nome das duas fotos da repetida, o número e o campo de cada
    (05/11/2026: o nome no lugar da foto, e o clique abre o card da OS)."""
    anexos = [{"id": f"a{i}", "tarefa": "1", "desc": "Inversor" if i != 3 else "",
               "anexada": _anexada(30 if i == 4 else 0)} for i in range(1, 5)]
    o = _os(_tarefa(qualidade=60, id_wt=1), _tarefa(pelo_app=False, qualidade=None, id_wt=2))     # as fotos da tarefa do App
    r = _classificar(o, _fatos(anexos, [("a1", "a3")]), FECHADO, P)
    # a nota 60 da tarefa do App é o aviso "nota" desde 09/11/2026 (era um "app")
    assert [a["tipo"] for a in r["avisos"]] == ["tarde", "repetida", "fora_app", "nota"]
    assert r["avisos"][1]["pares"] == [{"a": "a1", "b": "a3", "ra": "p01", "rb": "p03", "da": "Inversor", "db": ""}]
    sem_fotos = _classificar(_os(_tarefa(pelo_app=False, qualidade=None, id_wt=1), _tarefa(id_wt=2)), None,
                                      FECHADO, P)
    assert [a["tipo"] for a in sem_fotos["avisos"]] == ["fora_app", "faltam"]


def test_as_variaveis_do_pre_filtro_chegam_ao_config():
    """O config só passa ao app as variáveis declaradas: sem declarar, o NEXUS_PREFILTRO=0 do .env não desligava o laço
    (achado na prova no navegador, 05/11/2026) e os limites ficavam sempre no padrão."""
    from nexus.config import OBRIGATORIAS, carregar_config
    pre = {"NEXUS_PREFILTRO": "0", "NEXUS_PREFILTRO_HORAS_TARDE": "48", "NEXUS_PREFILTRO_DIF": "10",
           "NEXUS_PREFILTRO_DIF_PRINT": "3", "NEXUS_PREFILTRO_POR_VOLTA": "20", "NEXUS_PREFILTRO_PAUSA_S": "5"}
    cfg = carregar_config({k: "x" for k in OBRIGATORIAS} | pre)
    assert {k: cfg.get(k) for k in pre} == pre


# ── a revisão final (05/11/2026) ────────────────────────────────────────────────────────────────────────────────────
def test_foto_de_tarefa_fora_do_app_nao_e_julgada_pela_hora_do_app():
    """OS mista: a tarefa fechada fora do App tem as fotos anexadas no Fracttal na hora dela; julgá-las pela hora do App
    de outra tarefa dava Não OK falso. Só as fotos das tarefas do App (pelo id da tarefa) são julgadas."""
    o = _os(_tarefa(id_wt=1), _tarefa(pelo_app=False, qualidade=None, id_wt=2))
    fatos = _fatos([{"id": "a", "tarefa": "1", "anexada": _anexada(1)}, {"id": "b", "tarefa": "2", "anexada": _anexada(50)}])
    r = _classificar(o, fatos, FECHADO, P)
    assert r["coluna"] == "duvida" and r["tarde"] == 0
    fatos["anexos"].append({"id": "c", "tarefa": "1", "anexada": _anexada(50)})
    assert _classificar(o, fatos, FECHADO, P)["coluna"] == "nao_ok"


def test_foto_que_nao_abriu_pede_o_olho():
    """A foto que o Nexus não conseguiu abrir não foi conferida: a OS não vai para Pronta (nem para o lote) calada."""
    fatos = _fatos([{"id": "a", "anexada": _anexada(1), "hash": None}, {"id": "b", "anexada": _anexada(1)}])
    r = _classificar(_os(_tarefa()), fatos, FECHADO, P)
    assert r["coluna"] == "duvida"
    assert {"tipo": "nao_abriu", "nivel": "alerta", "texto": "1 foto não abriu no Nexus: confira no card da OS",
            "fotos": ["a"]} in r["avisos"]


def test_fechamento_offline_vale_a_chegada_no_servidor(monkeypatch):
    """Celular sem sinal: o fechamento (hora do celular) e as fotos chegam juntos dias depois; julgar pela hora do
    celular dava "anexadas 3 dias depois" falso. Vale a maior entre a hora do celular e a da chegada no servidor."""
    from datetime import datetime, timezone

    from test_campo_regras_app import TabelaFalsa

    from nexus.campo import aprovacao, regras_app
    linhas = [{"PartitionKey": "q", "RowKey": "q1", "os": "15102", "dev_ts": "2026-10-20T12:00:00Z",
               "server_ts": "2026-10-23T09:00:00"}]
    monkeypatch.setattr(regras_app, "tabela_qlog", lambda: TabelaFalsa(linhas))
    fim = prefiltro._quando(aprovacao._ultimo_fechamento_no_app()["15102"])
    assert fim == datetime(2026, 10, 23, 9, tzinfo=timezone.utc)
