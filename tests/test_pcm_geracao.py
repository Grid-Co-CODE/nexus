"""Etapa 2: o Nexus gera a semana em SOMBRA, com o motor do PCM copiado sem mudança (nexus/pcm/motor), e compara
com a semana oficial do PCM. Nada é publicado.

Os testes usam um MOTOR FALSO (um script que escreve uma planilha no formato do gerador): nenhum teste vai ao Fracttal.
"""
import json
import sys
import textwrap
from datetime import date

import openpyxl
import pytest

from nexus.pcm import auxiliar as A
from nexus.pcm import comparar as C
from nexus.pcm import geracao as G
from nexus.pcm import insumos as I
from test_pcm_auxiliar import cadastro_de_teste
from test_pcm_insumos import criar_pasta_pcm

CAB = ["Equipe", "Dia", "OSs ID", "Ativo (Usina)", "Código Equipamento", "Tipo", "Tarefa", "Reprogramada",
       "Nº vezes programada", "Hora Início", "Hora Fim", "Duração (h)", "RPN/Prioridade"]
LINHAS = [
    ["SP Leste 02", "Segunda-feira (05/10)", 15020, "Thopen - Altair 1 - SP", "ALT1-INV01", "Corretiva",
     "Fusível queimado", "Não", 1, "07:30", "09:00", 1.5, 12],
    ["SP Leste 02", "Terça-feira (06/10)", 15021, "Thopen - Altair 1 - SP", "ALT1-CAB01", "Preventiva",
     "MPM cabine", "Sim", 3, "07:30", "08:36", 1.1, 20],
]


def planilha(caminho, linhas=LINHAS, pendentes=()):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SP Leste 02"
    ws.append(CAB)
    for l in linhas:
        ws.append(l)
    wp = wb.create_sheet("_Pendentes")
    wp.append(["Equipe", "OSs ID", "Código Equipamento", "Tarefa", "Motivo"])
    for p in pendentes:
        wp.append(p)
    wb.save(caminho)


def historico(caminho, linhas):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["task_key", "first_week", "last_week", "count", "weeks"])
    for l in linhas:
        ws.append(l)
    wb.save(caminho)


@pytest.fixture
def origem(tmp_path):
    """A pasta do PCM de mentira, com tudo o que o motor lê, no formato dos arquivos de verdade."""
    o = criar_pasta_pcm(tmp_path / "pcm")
    return o


def motor_falso(tmp_path, codigo_saida=0, espera=0.0):
    """Faz o papel do programacao_v7.py: confere os insumos na PCM_PROG_DIR e o ambiente que o Nexus passa, e escreve
    em PCM_OUTPUT a mesma planilha das LINHAS (sem pendentes)."""
    m = tmp_path / f"motor_falso_{codigo_saida}_{int(espera * 10)}.py"
    m.write_text(textwrap.dedent(f"""
        import json, os, sys, time
        import openpyxl
        base = os.environ["PCM_PROG_DIR"]
        for nome in ("{A.NOME}", "Historico_Programacoes.xlsx", "Observacoes_Semana.txt"):
            assert os.path.exists(os.path.join(base, nome)), nome
        assert os.environ.get("FRACTTAL_CLIENT_ID") == "id-de-teste"
        assert os.environ.get("FRACTTAL_BASE_URL", "").endswith("/api/")
        assert not any(k.startswith("NEXUS_") for k in os.environ)
        print("semana pedida:", sys.argv[sys.argv.index("--semana") + 1])
        time.sleep({espera})
        if {codigo_saida}:
            print("Traceback: deu ruim no motor falso")
            sys.exit({codigo_saida})
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "SP Leste 02"
        ws.append(json.loads({json.dumps(json.dumps(CAB))}))
        for l in json.loads({json.dumps(json.dumps(LINHAS))}):
            ws.append(l)
        wp = wb.create_sheet("_Pendentes")
        wp.append(["Equipe", "OSs ID", "Código Equipamento", "Tarefa", "Motivo"])
        wb.save(os.environ["PCM_OUTPUT"])
        print("OK")
    """), encoding="utf-8")
    return m


@pytest.fixture
def config(tmp_path, origem):
    # na sombra, o Nexus importa os arquivos da pasta do PCM antes de gerar (insumos.importar)
    I.importar(tmp_path / "trabalho", origem, "2026-W41")
    return {"TESTING": True, "NEXUS_PCM_ORIGEM": str(origem), "NEXUS_PCM_TRABALHO": str(tmp_path / "trabalho"),
            "NEXUS_PCM_MOTOR": str(motor_falso(tmp_path)),
            "NEXUS_PCM_CADASTRO_TESTE": cadastro_de_teste(tmp_path / "cadastro.json"),
            "NEXUS_PCM_FRACTTAL_TESTE": {"FRACTTAL_CLIENT_ID": "id-de-teste", "FRACTTAL_CLIENT_SECRET": "segredo"}}


# ── regras ───────────────────────────────────────────────────────────────────────────────────────────────

def test_semana_padrao_e_a_proxima_segunda():
    assert G.semana_padrao(date(2026, 9, 30)) == "2026-W41"      # quarta -> semana de 05/10
    assert G.semana_padrao(date(2026, 10, 1)) == "2026-W41"      # quinta, dia de gerar
    assert G.semana_padrao(date(2026, 10, 5)) == "2026-W42"      # segunda -> a próxima


def test_historico_volta_para_antes_da_semana_gerada(tmp_path):
    """Gerar a semana de novo marcava tudo como reprogramado (medido na semana 40: 415 tarefas). O Nexus gera a partir do
    histórico de ANTES da semana, então tanto faz rodar antes ou depois do PCM."""
    src, dst = tmp_path / "h.xlsx", tmp_path / "h2.xlsx"
    historico(src, [["A|1", "2026-W39", "2026-W41", 3, "2026-W39,2026-W40,2026-W41"],
                    ["B|2", "2026-W41", "2026-W41", 1, "2026-W41"],
                    ["C|3", "2026-W38", "2026-W38", 1, "2026-W38"]])
    G.preparar_historico(src, dst, "2026-W41")
    ws = openpyxl.load_workbook(dst).active
    linhas = {r[0]: r for r in ws.iter_rows(min_row=2, values_only=True)}
    assert set(linhas) == {"A|1", "C|3"}                 # a B só existia por causa da W41
    assert linhas["A|1"][1:] == ("2026-W39", "2026-W40", 2, "2026-W39,2026-W40")
    assert linhas["C|3"][4] == "2026-W38"


def test_credencial_vem_do_ambiente_antes_dos_arquivos(config):
    c = G.credencial(config)
    assert c.ok and c.onde == "teste"
    assert "id-de-teste" not in repr(c) and "segredo" not in repr(c)   # o valor nunca aparece
    sem = dict(config, NEXUS_PCM_FRACTTAL_TESTE={})
    assert not G.credencial(sem).ok


def test_conferir_lista_o_que_falta(config, origem, tmp_path):
    ok = G.conferir(config)
    assert ok["pronto"], ok
    # o histórico mora no Nexus: apagar o arquivo da pasta não faz falta à geração
    (origem / "Historico_Programacoes.xlsx").unlink()
    assert G.conferir(config)["pronto"]
    # a AUXILIAR sai do cadastro do Nexus: a planilha da pasta não faz falta, o cadastro faz
    sem_cadastro = {k: v for k, v in config.items() if k != "NEXUS_PCM_CADASTRO_TESTE"}
    falta = G.conferir(sem_cadastro)
    assert [i["nome"] for i in falta["itens"] if not i["ok"]] == ["Cadastro de usinas (AUXILIAR)"]
    # Nexus sem os insumos importados: cada um aparece como falta
    vazio = dict(config, NEXUS_PCM_TRABALHO=str(tmp_path / "outro"))
    nomes = [i["nome"] for i in G.conferir(vazio)["itens"] if not i["ok"]]
    assert nomes == [I.NOMES[k] for k in ("prioridades", "confiabilidade", "historico", "feriados")]


def test_servidor_sem_a_pasta_do_pcm_gera_mesmo_assim(config, tmp_path):
    """No servidor não existe o OneDrive do PCM. Desde 02/10 a AUXILIAR sai do cadastro e os insumos moram no Nexus:
    a pasta só serve para comparar com a oficial e trazer as durações (sombra). Ela era obrigatória e travava a
    geração no servidor."""
    cfg = dict(config, NEXUS_PCM_ORIGEM=str(tmp_path / "nao-existe"))
    conf = G.conferir(cfg)
    assert conf["pronto"], [i for i in conf["itens"] if not i["ok"]]
    st = G.aguardar(cfg, G.iniciar(cfg, "2026-W41")["id"], 60)
    assert st["estado"] == "ok", st
    assert "comparacao" not in st                     # sem a oficial, não há com o que comparar


def test_gerar_em_sombra_e_comparar_com_a_oficial(config, origem):
    planilha(origem / "Programação Semana 41.xlsx")               # a semana oficial (a do PCM)
    r = G.iniciar(config, "2026-W41")
    st = G.aguardar(config, r["id"], 60)
    assert st["estado"] == "ok", st
    assert st["resumo"]["linhas"] == 2
    assert st["comparacao"]["identicas"] is True
    assert "semana pedida: 2026-W41" in G.log(config, r["id"])
    # os insumos são carimbados: de onde veio cada um e de quando é o dado
    assert {i["nome"] for i in st["insumos"]} >= {"Cadastro de usinas (AUXILIAR)", I.NOMES["historico"], I.NOMES["feriados"]}


def test_diferenca_com_a_oficial_aparece_por_campo(config, origem):
    outra = [list(LINHAS[0]), list(LINHAS[1])]
    outra[1][9] = "13:12"                                          # a oficial saiu às 13:12
    planilha(origem / "Programação Semana 41.xlsx", outra)
    r = G.iniciar(config, "2026-W41")
    st = G.aguardar(config, r["id"], 60)
    cmp = st["comparacao"]
    assert cmp["identicas"] is False and cmp["diferencas"].get("Hora Início") == 1


def test_motor_que_falha_vira_estado_falhou_com_o_motivo(config, tmp_path):
    cfg = dict(config, NEXUS_PCM_MOTOR=str(motor_falso(tmp_path, codigo_saida=1)))
    st = G.aguardar(cfg, G.iniciar(cfg, "2026-W41")["id"], 60)
    assert st["estado"] == "falhou" and "deu ruim" in st["erro"]


def test_uma_geracao_por_vez(config, tmp_path):
    cfg = dict(config, NEXUS_PCM_MOTOR=str(motor_falso(tmp_path, espera=2.0)))
    r = G.iniciar(cfg, "2026-W41")
    with pytest.raises(G.Ocupado):
        G.iniciar(cfg, "2026-W41")
    G.aguardar(cfg, r["id"], 60)


def test_comparar_planilhas(tmp_path):
    a, b = tmp_path / "a.xlsx", tmp_path / "b.xlsx"
    planilha(a)
    planilha(b)
    assert C.comparar(a, b)["identicas"] is True
    planilha(b, LINHAS[:1], pendentes=[["SP Leste 02", 15021, "ALT1-CAB01", "MPM cabine", "não coube"]])
    r = C.comparar(a, b)
    assert r["identicas"] is False and r["so_a"] == 1 and r["pendentes_b"] == 1


# ── telas ────────────────────────────────────────────────────────────────────────────────────────────────

def test_tela_gerar_mostra_o_que_falta(app, logado, config):
    app.config.update({k: v for k, v in config.items() if k != "TESTING"})
    html = logado.get("/t/pcm/gerar").get_data(as_text=True)
    assert "Gerar a semana" in html and "2026-W" in html
    assert "Credencial do Fracttal" in html and "Em construção" not in html


def test_tela_gerar_roda_e_mostra_o_resultado(app, logado, config, origem):
    app.config.update({k: v for k, v in config.items() if k != "TESTING"})
    planilha(origem / "Programação Semana 41.xlsx")
    resp = logado.post("/t/pcm/gerar", data={"semana": "2026-W41", "confirmo": "1"})
    assert resp.status_code == 303
    rodada = resp.headers["Location"].split("rodada=")[1]
    G.aguardar(app.config, rodada, 60)
    html = logado.get("/t/pcm/gerar?rodada=" + rodada).get_data(as_text=True)
    assert "Idênticas" in html
    estado = json.loads(logado.get("/t/pcm/gerar/estado?rodada=" + rodada).get_data(as_text=True))
    assert estado["estado"] == "ok"


def test_tela_gerar_sem_credencial_nao_roda(app, logado, config):
    app.config.update({k: v for k, v in config.items() if k != "TESTING"})
    app.config["NEXUS_PCM_FRACTTAL_TESTE"] = {}
    resp = logado.post("/t/pcm/gerar", data={"semana": "2026-W41", "confirmo": "1"})
    assert resp.status_code == 400
    assert "Credencial do Fracttal" in resp.get_data(as_text=True)


def test_semana_invalida_nao_roda(app, logado, config):
    app.config.update({k: v for k, v in config.items() if k != "TESTING"})
    assert logado.post("/t/pcm/gerar", data={"semana": "41; rm -rf", "confirmo": "1"}).status_code == 400


def test_fuso_do_motor_so_vai_pelo_tz_fora_do_windows(monkeypatch, tmp_path):
    # S41 de teste (02/10/2026): no Windows o TZ=America/Sao_Paulo deixava o relógio do motor 4 h adiantado
    cred = G.Credencial(True, "teste", "id", "seg")
    monkeypatch.setenv("TZ", "UTC")
    monkeypatch.setattr(G.os, "name", "nt")
    assert "TZ" not in G._ambiente(cred, tmp_path, tmp_path / "s.xlsx")
    monkeypatch.setattr(G.os, "name", "posix")
    assert G._ambiente(cred, tmp_path, tmp_path / "s.xlsx")["TZ"] == "America/Sao_Paulo"