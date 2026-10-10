"""Quadro da semana (Levi, 09/10/2026: "Eles tem essa visão [...] no site de PCM, gostaria que tenhamos uma visão dessa
no Nexus também e consigamos reprogramar tarefas").

O que estes testes seguram: a linha de reprogramação igual à do painel do PCM (e a do JavaScript da página igual à do
Python), a mescla nas observações sem duplicar ordem para a mesma OS, a semana do PCM de sábado 00:00 a sexta ("criadas
após o plano"), as contas do quadro (colunas, cartões em ordem de horário, teto por coluna, filtros, trajetória, as
tarefas de cada OS uma vez só), para onde vai cada reprogramação (semana em curso, semana que o Nexus gera, semana do PC
do PCM, semana que acabou), a fila validada contra a SEMANA (nenhum texto livre chega ao arquivo do motor), o arquivo da
semana em curso que não carrega linha de outra semana, e as telas (só administrador grava; a semana em curso pede
confirmação e confere relendo). Nenhum teste vai ao GitHub: o GitHub falso dos testes da publicação."""
import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from nexus.pcm import geracao as G
from nexus.pcm import insumos as I
from nexus.pcm import observacoes as O
from nexus.pcm import quadro as Q
from test_pcm_geracao import config, origem  # noqa: F401 (fixtures)
from test_pcm_publicar import GitHubFalso, _com_github, _rodada

JS = Path(__file__).resolve().parents[1] / "nexus" / "static" / "pcm-quadro.js"

# (os, dia, turno, tarefa, tipo) -> a linha do painel do PCM (rpLinha do novo.html)
CASOS = [
    (("15269", "não", "", "", ""), "15269; não"),
    (("15269", "não", "tarde", "qualquer", "MPM"), "15269; não"),
    (("15269", "qua", "", "", ""), "15269; qua"),
    (("15269", "qua", "tarde", "", ""), "15269; qua; ; tarde"),
    (("15269", "qua", "manhã", "[Grid Co.] - MPM - Transformador Aéreo", "MPM"),
     "15269; qua; MPM; manhã; só: Transformador Aéreo"),
    (("15269", "qua", "", "[Grid Co.] - MPM - Transformador Aéreo", "MPM-Inversor"),
     "15269; qua; MPM; só: Transformador Aéreo"),
    (("700", "sex", "noite", "[Grid Co.] - MPA - Caixa d'água, reservatório", "MPA"),
     "700; sex; MPA; noite; só: Caixa d'água"),
    (("701", "seg", "", "Handover – Inversores; string box", "Handover"), "701; seg; Handover; só: Inversores"),
    (("15289", "ter", "tarde", "Usina 1: vedação dos postes de CFTV", "Corretiva"),
     "15289; ter; Usina 1: vedação dos postes de CFTV; tarde"),
    (("15290", "seg", "", "Troca de fusível, string 3", "Corretiva"), "15290; seg; Troca de fusível"),
    (("15291", "seg", "", ", sem nome", "Corretiva"), None),
]


# ── a linha ──────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("args,esperada", CASOS)
def test_linha_igual_a_do_painel_do_pcm(args, esperada):
    assert Q.linha(*args) == esperada
    if esperada:
        r = O.ler_linha(esperada)       # o leitor do Nexus (o mesmo critério do motor) entende sem problema
        assert r["problema"] is None and r["tipo"] in ("fora", "fixar") and r["os"] == int(args[0])


@pytest.mark.skipif(not shutil.which("node"), reason="sem node nesta máquina")
def test_linha_do_javascript_igual_a_do_python():
    """A fila mostra na página a linha do pcm-quadro.js; o servidor grava a do quadro.py. Têm de ser a mesma."""
    script = ("require(process.argv[1]); const L = globalThis.QuadroLinha;"
              "const c = JSON.parse(process.argv[2]);"
              "process.stdout.write(JSON.stringify(c.map(a => L.linha(a[0], a[1], a[2], a[3], a[4]))));")
    r = subprocess.run(["node", "-e", script, str(JS), json.dumps([list(a) for a, _ in CASOS])],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [Q.linha(*a) for a, _ in CASOS]


# ── a mescla nas observações ─────────────────────────────────────────────────────────────────────────────────
BASE = "@usina Usina 1 = seg, qua\n# comentário\n15269; seg\n15269; ter; MPM; só: Cabine\n9000; não\n9001; qui\n"


def test_mescla_substitui_o_mesmo_alvo_e_preserva_o_resto():
    novo, res = Q.mesclar(BASE, ["15269; ter; MPM; manhã; só: Cabine"])
    assert novo.splitlines() == ["@usina Usina 1 = seg, qua", "# comentário", "15269; seg", "9000; não", "9001; qui",
                                 "15269; ter; MPM; manhã; só: Cabine"]
    assert res["saem"] == ["15269; ter; MPM; só: Cabine"]


def test_mescla_os_inteira_e_nao():
    # a OS inteira num dia tira as linhas por tarefa dela
    novo, res = Q.mesclar(BASE, ["15269; sex"])
    assert [l for l in novo.splitlines() if l.startswith("15269")] == ["15269; sex"]
    assert res["saem"] == ["15269; seg", "15269; ter; MPM; só: Cabine"]
    # "não" tira todas as linhas da OS
    novo, _ = Q.mesclar(BASE, ["15269; não"])
    assert [l for l in novo.splitlines() if l.startswith("15269")] == ["15269; não"]
    # a OS que estava fora volta com uma tarefa num dia: o "não" sai
    novo, res = Q.mesclar(BASE, ["9000; qua; Troca de fusível"])
    assert "9000; não" not in novo and "9000; qua; Troca de fusível" in novo and res["saem"] == ["9000; não"]
    # a mesma linha de novo não conta como saída; na mesma leva, vale a última
    _, res = Q.mesclar(BASE, ["9001; qui"])
    assert res["saem"] == []
    novo, res = Q.mesclar("", ["42; seg", "42; não"])
    assert novo == "42; não\n" and res["saem"] == []
    with pytest.raises(Q.QuadroErro):
        Q.mesclar(BASE, ["texto livre"])


# ── a semana do PCM ──────────────────────────────────────────────────────────────────────────────────────────
def test_semana_do_pcm_vai_do_sabado_a_sexta():
    j = Q.janela_do_plano("2026-W41")
    assert j == (date(2026, 10, 3), date(2026, 10, 9))
    criada = lambda d: Q.criada_apos_o_plano({"dataCriacao": d}, j)      # noqa: E731
    assert not criada("2026-10-02T23:59:00")       # sexta: a geração da sexta já levou
    assert criada("2026-10-03T00:00:01") and criada("2026-10-09T18:00:00")
    assert not criada("2026-10-10T08:00:00") and not criada("")


def test_turno_estado_e_dia():
    assert [Q.turno(h) for h in ("07:00", "11:59", "12:00", "16:59", "17:00", "06:59", "", None)] == \
        ["Manhã", "Manhã", "Tarde", "Tarde", "Noite", "Noite", "Sem horário", "Sem horário"]
    assert [Q.estado({"status": s}) for s in ("Finalizados", "pausado", "Em progresso", "Não Iniciada", "")] == \
        ["Finalizada", "Pausada", "Em progresso", "Não iniciada", "Não iniciada"]
    assert [Q.dia_de(d) for d in ("Terça-feira (13/10)", "Sábado", "domingo", "Segunda-feira", "x")] == \
        ["ter", "sab", "dom", "seg", ""]


# ── o quadro ─────────────────────────────────────────────────────────────────────────────────────────────────
def _r(os_, dia, h, tarefa="Tarefa", tipo="Corretiva", equipe="SP Leste 02", criada="2026-09-20T10:00:00", **kw):
    return dict({"os_id": str(os_), "dia": dia, "h_ini": h, "h_fim": "", "tarefa": tarefa, "tipo": tipo,
                 "cluster": equipe, "usina": "Cliente A - Usina 1 - SP", "cliente": "Cliente A", "duracao": 1.5,
                 "status": "Não Iniciada", "vezes": 1, "reprog": "Não", "dataCriacao": criada,
                 "responsavel": "Pessoa A"}, **kw)


def _semana_teste():
    rows = [_r(1, "Segunda-feira", "13:00"), _r(2, "Segunda-feira", "07:30", criada="2026-10-03T09:00:00"),
            _r(3, "Terça-feira", "", tarefa="Sem hora"), _r(4, "Terça-feira", "08:00", equipe="RN Sul 01",
                                                               status="Finalizados", tipo="MPA"),
            _r(5, "Quarta-feira", "18:30", tarefa="[Grid Co.] - MPM - Cabine", tipo="MPM", vezes=3, reprog="Sim"),
            _r(5, "Quarta-feira", "19:00", tarefa="[Grid Co.] - MPM - Trafo", tipo="MPM")]
    pend = [{"os_id": "5", "usina": "Cliente A - Usina 1 - SP", "cliente": "Cliente A", "cluster": "SP Leste 02",
             "tarefa": "[Grid Co.] - MPM - SPDA", "tipo": "MPM", "duracao": 1.1, "motivo": "Sem capacidade"},
            {"os_id": "6", "usina": "Cliente B - Usina 2 - RN", "cliente": "Cliente B", "cluster": "RN Sul 01",
             "tarefa": "Troca de fusível", "tipo": "Corretiva", "duracao": 2, "motivo": ""}]
    return {"week": "2026-W41", "label": "Semana 41", "rows": rows, "pendentes": pend,
            "dates": {"seg": "05/10", "ter": "06/10", "qua": "07/10", "qui": "08/10", "sex": "09/10"}}


def test_quadro_colunas_cartoes_e_criadas_apos_o_plano():
    q = Q.montar(_semana_teste(), [], {})
    assert [c["id"] for c in q["colunas"]] == ["seg", "ter", "qua"]          # só os dias que a semana tem
    seg = q["colunas"][0]
    assert (seg["n"], seg["horas"], seg["novas"], seg["data"]) == (2, "3 h", 1, "05/10")
    assert [k["os"] for k in seg["cartoes"]] == ["2", "1"]                  # na ordem do relógio
    ter = q["colunas"][1]
    assert [k["os"] for k in ter["cartoes"]] == ["4", "3"]                  # sem horário vai para o fim
    assert ter["cartoes"][0]["st"] == "Finalizada" and ter["cartoes"][1]["tur"] == "Sem horário"
    qua = q["colunas"][2]
    assert qua["cartoes"][0]["rep"] and qua["cartoes"][0]["rol"] == 3 and qua["cartoes"][0]["tur"] == "Noite"
    assert all(c["carga"] == 100.0 and c["pico"] for c in q["colunas"])     # 2 em cada: todos no pico
    assert q["novas"] == 1 and q["total"] == 6
    # a OS 5 tem três tarefas na semana (duas na agenda e uma pendente): vai UMA vez em `oss`
    assert [x["t"] for x in q["oss"]["5"]] == ["[Grid Co.] - MPM - Cabine", "[Grid Co.] - MPM - Trafo",
                                               "[Grid Co.] - MPM - SPDA"]
    assert q["oss"]["5"][2]["pend"] and "1" not in q["oss"]
    assert all("irmas" not in it for it in q["itens"])
    # as pendentes por usina, cada uma com o seu item da janela
    assert [g["uc"] for g in q["pendentes"]] == ["Usina 1 - SP", "Usina 2 - RN"]
    assert q["itens"][q["pendentes"][0]["itens"][0]["i"]]["pend"] is True


def test_quadro_filtros_teto_e_pendentes_sob_pedido(monkeypatch):
    sem = _semana_teste()
    q = Q.montar(sem, [], {"equipe": "RN Sul 01"})
    assert q["total"] == 1 and [c["n"] for c in q["colunas"]] == [0, 1, 0]     # as colunas ficam; a conta é do filtro
    assert q["pend_sel"] == 1 and q["pendentes"][0]["itens"][0]["os"] == "6"
    assert Q.montar(sem, [], {"estado": "Finalizada"})["total"] == 1
    assert Q.montar(sem, [], {"turno": "Noite"})["total"] == 2
    assert Q.montar(sem, [], {"q": "trafo"})["total"] == 1
    assert Q.montar(sem, [], {"resp": "Ninguém"})["total"] == 0
    # teto de cartões por coluna, com o resto contado; "todos" mostra tudo
    sem2 = dict(sem, rows=[_r(i, "Segunda-feira", f"{7 + i % 10:02d}:00") for i in range(45)])
    c = Q.montar(sem2, [], {})["colunas"][0]
    assert (len(c["cartoes"]), c["ocultos"]) == (40, 5)
    assert len(Q.montar(sem2, [], {}, todos=True)["colunas"][0]["cartoes"]) == 45
    # muitas pendentes: a lista só vem a pedido
    monkeypatch.setattr(Q, "TETO_PENDENTES", 1)
    q = Q.montar(sem, [], {})
    assert not q["pend_mostradas"] and q["pendentes"] == [] and q["pend_sel"] == 2
    assert Q.montar(sem, [], {}, mostrar_pendentes=True)["pend_mostradas"]


def test_trajetoria_pelas_semanas_do_arquivo():
    sem = _semana_teste()
    antes = [{"week": "2026-W39", "rows": [_r(1, "Sexta-feira", "09:00", vezes=1)]},
             {"week": "2026-W40", "rows": [_r(1, "Quinta-feira", "10:00", vezes=2, status="pausado")]},
             {"week": "2026-W42", "rows": [_r(1, "Segunda-feira", "07:00")]}]      # depois da semana: não entra
    q = Q.montar(sem, antes, {})
    it = q["itens"][next(k["i"] for k in q["colunas"][0]["cartoes"] if k["os"] == "1")]
    assert [(e["w"], e["d"], e["st"], e["ativa"]) for e in it["tl"]] == [
        ("S39", "Sex", "Não iniciada", False), ("S40", "Qui", "Pausada", False), ("S41", "Seg", "Não iniciada", True)]
    # tarefa que só aparece nesta semana não leva trajetória
    it2 = q["itens"][next(k["i"] for k in q["colunas"][0]["cartoes"] if k["os"] == "2")]
    assert "tl" not in it2


# ── para onde vai a reprogramação ────────────────────────────────────────────────────────────────────────────
def test_destino_da_reprogramacao():
    w = "2026-W42"                                    # 12/10 (segunda) a 16/10 (sexta)
    assert Q.destino(w, "publicada", False, date(2026, 10, 13))["id"] == "atual"
    assert Q.destino(w, "publicada", False, date(2026, 10, 16))["id"] == "atual"
    assert Q.destino(w, "publicada", False, date(2026, 10, 17))["id"] is None       # acabou
    assert Q.destino(w, "publicada", False, date(2026, 10, 10))["id"] == "copiar"   # do PC do PCM, ainda não começou
    assert Q.destino(w, "publicada", True, date(2026, 10, 10))["id"] == "nexus"     # o Nexus gera
    assert Q.destino(w, "rascunho", False, date(2026, 10, 8))["id"] == "nexus"
    assert Q.destino(w, "rascunho", False, date(2026, 10, 19))["id"] is None


def test_fila_validada_contra_a_semana():
    sem = _semana_teste()
    itens = [{"os": "5", "tarefa": "[Grid Co.] - MPM - Cabine", "dia": "sex", "turno": "manha", "tipo": "MPA"},
             {"os": "6", "tarefa": "Troca de fusível", "dia": "qui", "turno": ""},
             {"os": "1", "tarefa": "", "dia": "não", "turno": "tarde"},
             {"os": "99", "tarefa": "", "dia": "seg"},                          # não está na semana
             {"os": "1", "tarefa": "Tarefa inventada", "dia": "seg"},           # tarefa que a OS não tem
             {"os": "1", "tarefa": "", "dia": "sáb"},                            # o motor não entende sábado
             {"os": "1", "tarefa": "", "dia": "seg", "turno": "madrugada"},
             {"os": "6", "tarefa": "Troca de fusível", "dia": "sex", "turno": "tarde"},   # a mesma de novo: vale esta
             "lixo"]
    linhas, problemas = Q.linhas_da_fila(sem, itens)
    # o tipo vem da semana (MPM), não da página (MPA); "manha" vira "manhã"; o "não" ignora tarefa e turno
    assert linhas == ["5; sex; MPM; manhã; só: Cabine", "1; não", "6; sex; Troca de fusível; tarde"]
    assert len(problemas) == 4 and any("99" in p for p in problemas)


# ── o arquivo da semana em curso ─────────────────────────────────────────────────────────────────────────────
def test_arquivo_da_semana_em_curso_nao_carrega_outra_semana():
    cab41 = "# Semana 2026-W41: reprogramação da semana em curso, gravada pelo Nexus\n"
    novo, res = Q.novo_texto_atual(cab41 + "15000; seg\n", "2026-W42", ["15001; ter"])
    assert novo == "# Semana 2026-W42: reprogramação da semana em curso, gravada pelo Nexus\n15001; ter\n"
    assert res["saem_outra_semana"] == ["15000; seg"] and res["semana_antes"] == "2026-W41"
    # mesma semana: junta
    novo, _ = Q.novo_texto_atual(cab41 + "15000; seg\n", "2026-W41", ["15001; ter"])
    assert novo.splitlines()[1:] == ["15000; seg", "15001; ter"]
    # sem cabeçalho (do painel do PCM): fica, a não ser que peça para apagar
    novo, res = Q.novo_texto_atual("15448; nao\n", "2026-W41", ["15001; ter"])
    assert novo.splitlines()[1:] == ["15448; nao", "15001; ter"] and not res["saem_outra_semana"]
    novo, res = Q.novo_texto_atual("15448; nao\n", "2026-W41", ["15001; ter"], apagar_sem_semana=True)
    assert novo.splitlines()[1:] == ["15001; ter"] and res["saem_outra_semana"] == ["15448; nao"]
    assert Q.semana_do_cabecalho(novo) == "2026-W41"


def test_aplicar_na_semana_em_curso_confere_e_registra(tmp_path):
    cfg = {"TESTING": True, "NEXUS_PCM_TRABALHO": str(tmp_path / "trab")}
    gh = _com_github(cfg, GitHubFalso({"Observacoes_Semana_Atual.txt": b"15448; nao\n"}))
    atual = Q.ler_atual(cfg)
    assert atual["texto"] == "15448; nao\n" and atual["semana"] is None
    # o arquivo mudou depois que a pessoa conferiu: não grava
    with pytest.raises(Q.QuadroErro):
        Q.aplicar_na_semana_em_curso(cfg, "2026-W41", ["15001; ter"], "pessoa.teste@exemplo.com", "sha-velho")
    assert not gh.commits
    res = Q.aplicar_na_semana_em_curso(cfg, "2026-W41", ["15001; ter"], "pessoa.teste@exemplo.com", atual["sha"])
    assert gh.arquivos["Observacoes_Semana_Atual.txt"].decode("utf-8").splitlines() == [
        "# Semana 2026-W41: reprogramação da semana em curso, gravada pelo Nexus", "15448; nao", "15001; ter"]
    assert len(gh.commits) == 1 and "@" not in gh.commits[0]["mensagem"] and res["commit"]
    reg = Q.gravadas(cfg, "2026-W41")
    assert reg[0]["destino"] == "atual" and reg[0]["linhas"] == ["15001; ter"] and reg[0]["quem"] == "pessoa.teste@exemplo.com"
    # o repositório não devolve o que foi gravado: erro, e nada vai para o registro
    cfg2 = {"TESTING": True, "NEXUS_PCM_TRABALHO": str(tmp_path / "trab2")}
    _com_github(cfg2, GitHubFalso({"Observacoes_Semana_Atual.txt": b""}, estragar_leitura=True))
    with pytest.raises(Q.QuadroErro):
        Q.aplicar_na_semana_em_curso(cfg2, "2026-W41", ["15001; ter"], "pessoa.teste@exemplo.com", Q.ler_atual(cfg2)["sha"])
    assert Q.gravadas(cfg2, "2026-W41") == []


# ── as telas ─────────────────────────────────────────────────────────────────────────────────────────────────
def _banco(tmp_path) -> Path:
    s41 = _semana_teste()
    s41.update(num=41, geradaEm="2026-10-02T21:54:41Z")
    s40 = {"week": "2026-W40", "num": 40, "label": "Semana 40", "rows": [_r(1, "Sexta-feira", "09:00")], "pendentes": []}
    p = tmp_path / "banco_dados.json"
    p.write_text(json.dumps({"geradoEm": "2026-10-07T12:00:00Z", "semana_ativa": "2026-W41", "semanas": [s41, s40]}),
                 encoding="utf-8")
    return p


def _nao_admin(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"], s["admin"] = True, False
        s["usuario"] = {"email": "pessoa.teste@exemplo.com", "nome": "Pessoa Teste", "perfil": "PCM"}
    return c


def test_tela_quadro_semana_em_curso(app, logado, tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "hoje", lambda: date(2026, 10, 7))
    app.config.update(NEXUS_PCM_FONTE=str(_banco(tmp_path)), NEXUS_PCM_TRABALHO=str(tmp_path / "trab"))
    r = logado.get("/t/pcm/quadro")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Quadro da semana" in html and "Semana 41 · em curso" in html
    assert html.count("data-cartao=") == 6 and "criada após o plano" in html and "sábado 03/10 00:00" in html
    assert "Aplicar na semana em curso" in html and 'id="q-dados"' in html
    dados = json.loads(html.split('id="q-dados">', 1)[1].split("</script>", 1)[0])
    assert dados["destino"] == "atual" and dados["semana"] == "2026-W41" and "5" in dados["oss"]
    # filtro pela URL e a semana passada (só para ver)
    html = logado.get("/t/pcm/quadro?semana=2026-W41&equipe=RN+Sul+01").get_data(as_text=True)
    assert html.count("data-cartao=") == 1
    html = logado.get("/t/pcm/quadro?semana=2026-W40").get_data(as_text=True)
    assert "A semana já acabou" in html and "data-pend-inserir" not in html
    assert logado.get("/t/pcm/quadro?semana=2026-W30").status_code == 404
    # quem não é administrador monta a fila e copia, mas não grava
    html = _nao_admin(app).get("/t/pcm/quadro").get_data(as_text=True)
    assert "Quem grava é o PCM" in html and "Aplicar na semana em curso" not in html
    assert _nao_admin(app).post("/t/pcm/quadro/reprogramar", data={"semana": "2026-W41", "itens": "[]"}).status_code == 403


def test_tela_quadro_semana_em_curso_confirma_e_grava(app, logado, tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "hoje", lambda: date(2026, 10, 7))
    app.config.update(NEXUS_PCM_FONTE=str(_banco(tmp_path)), NEXUS_PCM_TRABALHO=str(tmp_path / "trab"))
    gh = _com_github(app.config, GitHubFalso({"Observacoes_Semana_Atual.txt": b"15448; nao\n"}))
    itens = json.dumps([{"os": "6", "tarefa": "Troca de fusível", "dia": "qui", "turno": "manhã"}])
    r = logado.post("/t/pcm/quadro/reprogramar", data={"semana": "2026-W41", "itens": itens})
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and not gh.commits                       # primeiro, a confirmação
    assert "6; qui; Troca de fusível; manhã" in html and "15448; nao" in html and 'name="confirmo"' in html
    sha = html.split('name="sha_visto" value="', 1)[1].split('"', 1)[0]
    r = logado.post("/t/pcm/quadro/reprogramar", data={"semana": "2026-W41", "itens": itens, "confirmo": "1",
                                                       "sha_visto": sha})
    assert r.status_code == 303 and "feito=aplicado" in r.headers["Location"] and len(gh.commits) == 1
    assert gh.arquivos["Observacoes_Semana_Atual.txt"].decode("utf-8").splitlines()[1:] == [
        "15448; nao", "6; qui; Troca de fusível; manhã"]
    html = logado.get(r.headers["Location"]).get_data(as_text=True)
    assert "1 linha gravada nos ajustes da semana em curso" in html and "Já gravadas para esta semana" in html
    # com o sha velho (o arquivo mudou depois da confirmação), não grava de novo
    r = logado.post("/t/pcm/quadro/reprogramar", data={"semana": "2026-W41", "itens": itens, "confirmo": "1",
                                                       "sha_visto": sha})
    assert r.status_code == 409 and len(gh.commits) == 1


def test_tela_quadro_rascunho_grava_nas_observacoes_do_nexus(app, logado, config, origem, monkeypatch):
    monkeypatch.setattr(Q, "hoje", lambda: date(2026, 10, 2))        # a W41 ainda vai começar
    app.config.update({k: v for k, v in config.items() if k != "TESTING"})
    rid = _rodada(app.config, origem)
    # a tela Gerar leva ao rascunho no quadro (a revisão de sexta)
    assert f'href="/t/pcm/quadro?rodada={rid}"' in logado.get(f"/t/pcm/gerar?rodada={rid}").get_data(as_text=True)
    html = logado.get("/t/pcm/quadro").get_data(as_text=True)          # sem o arquivo do App: o rascunho
    assert "rascunho do Nexus" in html and html.count("data-cartao=") == 2
    assert "Gravar nas observações da 2026-W41" in html
    trab = G.pasta_trabalho(app.config)
    antes = I.observacoes(trab, "2026-W41")
    itens = json.dumps([{"os": "15021", "tarefa": "MPM cabine", "dia": "sex", "turno": "tarde"},
                        {"os": "15020", "tarefa": "", "dia": "não"}])
    r = logado.post("/t/pcm/quadro/reprogramar", data={"semana": "2026-W41", "rodada": rid, "itens": itens,
                                                       "f_equipe": "SP Leste 02"})
    assert r.status_code == 303 and "feito=salvo" in r.headers["Location"] and "equipe=SP+Leste+02" in r.headers["Location"]
    html = logado.get(r.headers["Location"]).get_data(as_text=True)
    assert "2 linhas gravadas nas observações da 2026-W41" in html and 'href="/t/pcm/gerar?semana=2026-W41"' in html
    depois = I.observacoes(trab, "2026-W41")
    assert depois.splitlines()[-2:] == ["15021; sex; MPM cabine; tarde", "15020; não"]
    assert [l for l in antes.splitlines() if l.strip()] == [l for l in depois.splitlines()[:-2] if l.strip()]
    assert Q.gravadas(app.config, "2026-W41")[0]["destino"] == "nexus"
    # um item que a semana não tem, mesmo junto de um bom: nada é gravado (a pessoa acerta a fila e grava de novo)
    r = logado.post("/t/pcm/quadro/reprogramar", data={"semana": "2026-W41", "rodada": rid, "itens": json.dumps(
        [{"os": "15021", "tarefa": "", "dia": "seg"}, {"os": "1", "tarefa": "", "dia": "seg"}])})
    assert r.status_code == 400 and "Nada foi gravado" in r.get_data(as_text=True)
    assert I.observacoes(trab, "2026-W41") == depois


def test_filtros_do_quadro_em_cascata():
    """Levi, 09/10/2026: "Os filtros tem que se auto filtrar também": escolhida a equipe, Cliente, Tipo, Situação e
    Turno só listam o que existe nela; a equipe continua listando todas (com as contas pelos outros filtros)."""
    sem = _semana_teste()
    op = Q.montar(sem, [], {"equipe": "RN Sul 01"})["opcoes"]
    assert op["tipo"] == [("MPA", 1)] and op["estado"] == [("Finalizada", 1)] and op["turno"] == [("Manhã", 1)]
    assert op["equipe"] == [("RN Sul 01", 1), ("SP Leste 02", 5)]
    op = Q.montar(sem, [], {"tipo": "MPM"})["opcoes"]
    assert op["equipe"] == [("SP Leste 02", 2)] and op["turno"] == [("Noite", 2)]
    # a opção escolhida fica na lista mesmo quando a combinação não tem nada (a tela não esconde o filtro valendo)
    op = Q.montar(sem, [], {"equipe": "RN Sul 01", "tipo": "MPM"})["opcoes"]
    assert ("MPM", 0) in op["tipo"] and ("RN Sul 01", 0) in op["equipe"]
