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
    r = prefiltro.classificar(_os(_tarefa()), fatos, FECHADO, P)
    assert r["coluna"] == "nao_ok" and r["tarde"] == 1
    aviso = r["avisos"][0]
    assert aviso["nivel"] == "critico" and aviso["texto"] == "1 foto anexada 1 dia depois do fechamento no App"
    assert aviso["fotos"] == ["1"]


def test_varias_anexadas_dias_depois():
    fatos = _fatos([{"id": str(i), "anexada": _anexada(52)} for i in range(6)])
    r = prefiltro.classificar(_os(_tarefa()), fatos, FECHADO, P)
    assert r["coluna"] == "nao_ok" and r["avisos"][0]["texto"] == "6 fotos anexadas 2 dias depois do fechamento no App"


def test_23h_depois_nao_dispara():
    r = prefiltro.classificar(_os(_tarefa()), _fatos([{"id": "1", "anexada": _anexada(23)}]), FECHADO, P)
    assert r["coluna"] == "pronta" and r["tarde"] == 0


def test_repetida_e_em_duvida():
    anexos = [{"id": "a1", "anexada": _anexada(0)}, {"id": "a2", "anexada": _anexada(0)}, {"id": "a3", "anexada": _anexada(0)}]
    r = prefiltro.classificar(_os(_tarefa()), _fatos(anexos, [("a1", "a3")]), FECHADO, P)
    assert r["coluna"] == "duvida" and r["repetidas"] == 1
    aviso = r["avisos"][0]
    assert aviso["nivel"] == "alerta" and aviso["texto"] == "Foto repetida: p03 é a mesma imagem de p01"
    assert aviso["fotos"] == ["a1", "a3"]


def test_varias_repetidas_num_aviso_so():
    anexos = [{"id": f"a{i}", "anexada": _anexada(0)} for i in range(1, 6)]
    r = prefiltro.classificar(_os(_tarefa()), _fatos(anexos, [("a1", "a3"), ("a2", "a5")]), FECHADO, P)
    assert r["avisos"][0]["texto"] == "2 fotos repetidas: p03 = p01, p05 = p02"
    assert r["avisos"][0]["fotos"] == ["a1", "a3", "a2", "a5"]


def test_nao_ok_ganha_da_duvida():
    anexos = [{"id": "a1", "anexada": _anexada(30)}, {"id": "a2", "anexada": _anexada(30)}]
    r = prefiltro.classificar(_os(_tarefa()), _fatos(anexos, [("a1", "a2")]), FECHADO, P)
    assert r["coluna"] == "nao_ok" and [a["nivel"] for a in r["avisos"][:2]] == ["critico", "alerta"]


def test_fora_do_app_e_em_duvida():
    r = prefiltro.classificar(_os(_tarefa(pelo_app=False, qualidade=None)), _fatos([]), "", P)
    assert r["coluna"] == "duvida"
    assert r["avisos"][0]["texto"] == "1 tarefa fechada fora do App: sem as fotos e os horários do App para conferir"


def test_sem_fatos_e_conferindo():
    assert prefiltro.classificar(_os(_tarefa()), None, FECHADO, P)["coluna"] == "conferindo"


def test_fato_com_fotos_por_ler_vai_para_a_coluna_pior():
    r = prefiltro.classificar(_os(_tarefa(pelo_app=False, qualidade=None)), None, "", P)
    assert r["coluna"] == "duvida"
    assert any(a["texto"] == "Faltam fotos por ler" for a in r["avisos"])


def test_avisos_da_regra_do_app_nao_mudam_a_coluna():
    r = prefiltro.classificar(_os(_tarefa(qualidade=60, foi_devolvida=True)), _fatos([]), FECHADO, P)
    assert r["coluna"] == "pronta"
    textos = [a["texto"] for a in r["avisos"]]
    assert any("Nota do registro 60%" in t for t in textos) and any("devolvida" in t for t in textos)


def test_sem_hora_de_fechamento_nao_julga_a_anexacao():
    r = prefiltro.classificar(_os(_tarefa()), _fatos([{"id": "1", "anexada": _anexada(99)}]), "", P)
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
        ([_crua(labels=[{"description": "ENGENHARIA"}])], "ENGENHARIA"),
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
