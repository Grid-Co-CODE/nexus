"""Gerar no PC (27/11/2026, `nexus/pcm/geracao_pc.py`): o computador ligado, a rodada no PC, o pacote e a volta.

O caso: a geração da W49 morreu quatro vezes no servidor (o motor dentro do teto de memória do Nexus derrubava o serviço).
Levi, 27/11/2026: rodar a programação "no computador dela e aí salva no Nexus", com as chaves mandadas pelo Nexus (o PC
não tem `.env`) e as OS da FAMA juntas.

O que estes testes seguram: a chave do computador só existe no código (o Nexus guarda o hash) e desligar a corta; a API
inteira pede a chave; a rodada no PC tem os MESMOS insumos da do servidor e fica "no_pc" (nunca "interrompida"); o pacote
leva o motor e o adaptador da FAMA importáveis sem o Nexus; a FAMA vai sem o título; a planilha que volta termina a rodada
pelo MESMO `geracao.concluir` (resumo, conferência, comparação); a rodada de outro computador e a já terminada recusam."""
import io
import json
import subprocess
import sys
import zipfile

import pytest

from nexus.pcm import geracao as G
from nexus.pcm import geracao_pc as P
from test_pcm_geracao import CAB, LINHAS, config, origem, planilha  # noqa: F401 (fixtures)

URL = "https://nexus.exemplo.test"


def _chave(cod: str) -> str:
    import base64
    b = cod[len(P.PREFIXO):]
    return json.loads(base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)))["k"]


def _planilha_bytes(tmp_path) -> bytes:
    p = tmp_path / "volta.xlsx"
    planilha(p)
    return p.read_bytes()


# ── o computador ligado ───────────────────────────────────────────────────────────────────────────────────────────────
def test_ligar_guarda_so_o_hash_e_desligar_corta(config):
    cod = P.ligar(config, "PC do PCM", "pcm.teste@exemplo.test", URL)
    chave = _chave(cod)
    assert cod.startswith(P.PREFIXO)
    assert chave not in P._arquivo(config).read_text(encoding="utf-8")
    comp = P.quem_e(config, chave)
    assert comp["nome"] == "PC do PCM" and comp["ultimo_uso"] and "sha" not in comp
    assert P.quem_e(config, "chave-errada") is None and P.quem_e(config, "") is None
    assert P.desligar(config, comp["id"], "pcm.teste@exemplo.test") is True
    assert P.quem_e(config, chave) is None
    with pytest.raises(P.Recusado):
        P.ligar(config, "   ", "x", URL)


# ── a rodada no PC, ponta a ponta pela API ────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def pc(app, config):
    app.config.update({k: v for k, v in config.items() if k != "TESTING"})
    cod = P.ligar(app.config, "PC do PCM", "pcm.teste@exemplo.test", URL)
    return {"Authorization": "Bearer " + _chave(cod)}


def test_a_api_pede_a_chave(cliente, pc):
    for metodo, rota in (("get", "/t/pcm/pc/ola"), ("post", "/t/pcm/pc/rodada"), ("get", "/t/pcm/pc/credencial"),
                         ("get", "/t/pcm/pc/rodada/x/pacote"), ("post", "/t/pcm/pc/rodada/x/entregar")):
        assert getattr(cliente, metodo)(rota).status_code == 401, rota
        assert getattr(cliente, metodo)(rota, headers={"Authorization": "Bearer outra"}).status_code == 401, rota
    r = cliente.get("/t/pcm/pc/ola", headers=pc).get_json()
    assert r["ok"] and r["computador"] == "PC do PCM" and r["semana"]


def test_rodada_no_pc_de_ponta_a_ponta(app, cliente, pc, tmp_path, origem):
    planilha(origem / "Programação Semana 41.xlsx")               # a semana oficial, para a comparação
    r = cliente.post("/t/pcm/pc/rodada", json={"semana": "2026-W41"}, headers=pc).get_json()
    rid = r["id"]
    st = G.ler_status(app.config, rid)
    assert st["estado"] == P.NO_PC and st["pc"]["nome"] == "PC do PCM"
    assert {i["nome"] for i in st["insumos"]} >= {"Cadastro de usinas (AUXILIAR)"}
    # o pacote: os insumos da rodada, o motor e o adaptador da FAMA, e o rodada.json
    z = zipfile.ZipFile(io.BytesIO(cliente.get(f"/t/pcm/pc/rodada/{rid}/pacote", headers=pc).data))
    nomes = set(z.namelist())
    assert {"rodada.json", "pcm/fama_motor.py", "pcm/fama_base.py", "pcm/semana.py", "pcm/__init__.py",
            "rodada/Observacoes_Semana.txt"} <= nomes
    assert any(n.startswith("pcm/motor/") and n.endswith(".py") for n in nomes)
    # as subpastas vão junto: sem a dos feriados o motor roda a semana sem feriados (a prova no ar de 27/11/2026)
    feriados = [n for n in nomes if n.startswith("rodada/Feriados/")]
    assert feriados and all(n.endswith(".xlsx") for n in feriados), sorted(nomes)
    assert "status.json" not in {n.split("/")[-1] for n in nomes}
    meta = json.loads(z.read("rodada.json"))
    assert meta["semana"] == "2026-W41" and meta["id"] == rid
    # a credencial vem do Nexus e não fica no pacote
    cred = cliente.get("/t/pcm/pc/credencial", headers=pc).get_json()
    assert cred["client_id"] == "id-de-teste" and cred["client_secret"] == "segredo"
    assert not any(b"segredo" in z.read(n) for n in nomes)
    # o andamento aparece na tela, e a rodada no PC nunca é "interrompida"
    cliente.post(f"/t/pcm/pc/rodada/{rid}/andamento", json={"etapa": "rodando o motor"}, headers=pc)
    with cliente.session_transaction() as s:
        s["logado"], s["admin"] = True, True
    html = cliente.get("/t/pcm/gerar?rodada=" + rid).get_data(as_text=True)
    assert "Rodando no computador PC do PCM" in html and "rodando o motor" in html and "foi interrompida" not in html
    # a volta: a planilha termina a rodada pelo mesmo concluir do servidor
    v = cliente.post(f"/t/pcm/pc/rodada/{rid}/entregar", headers=pc, data={
        "planilha": (io.BytesIO(_planilha_bytes(tmp_path)), "sombra.xlsx"),
        "log": (io.BytesIO(b"semana pedida: 2026-W41\nOK\n"), "log.txt"),
        "relato": json.dumps({"codigo": 0, "duracao_s": 754})}).get_json()
    assert v["estado"] == "ok" and v["tela"].endswith(rid)
    st = G.ler_status(app.config, rid)
    assert st["resumo"]["linhas"] == 2 and st["comparacao"]["identicas"] is True and st["duracao_s"] == 754
    assert G.planilha(app.config, rid) is not None and "semana pedida" in G.log(app.config, rid)
    # entregar de novo recusa
    assert cliente.post(f"/t/pcm/pc/rodada/{rid}/entregar", headers=pc,
                       data={"relato": "{}"}).status_code == 409


def test_o_motor_que_falhou_no_pc_vira_falhou_com_o_log(app, cliente, pc):
    rid = cliente.post("/t/pcm/pc/rodada", json={"semana": "2026-W41"}, headers=pc).get_json()["id"]
    v = cliente.post(f"/t/pcm/pc/rodada/{rid}/entregar", headers=pc, data={
        "log": (io.BytesIO(b"Traceback: deu ruim no motor\n"), "log.txt"),
        "relato": json.dumps({"codigo": 1})}).get_json()
    st = G.ler_status(app.config, rid)
    assert v["estado"] == "falhou" and "deu ruim no motor" in st["erro"]


def test_rodada_de_outro_computador_e_arquivo_que_nao_e_planilha(app, cliente, pc, tmp_path):
    rid = cliente.post("/t/pcm/pc/rodada", json={"semana": "2026-W41"}, headers=pc).get_json()["id"]
    outro = {"Authorization": "Bearer " + _chave(P.ligar(app.config, "Outro PC", "x@exemplo.test", URL))}
    assert cliente.get(f"/t/pcm/pc/rodada/{rid}/pacote", headers=outro).status_code == 409
    assert cliente.post(f"/t/pcm/pc/rodada/{rid}/entregar", headers=outro, data={"relato": "{}"}).status_code == 409
    r = cliente.post(f"/t/pcm/pc/rodada/{rid}/entregar", headers=pc, data={
        "planilha": (io.BytesIO(b"nao sou planilha"), "x.xlsx"), "relato": json.dumps({"codigo": 0})})
    assert r.status_code == 409 and G.ler_status(app.config, rid)["estado"] == P.NO_PC
    assert cliente.post("/t/pcm/pc/rodada", json={"semana": "41; rm"}, headers=pc).status_code == 400


# ── a FAMA no pacote ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_fama_vai_sem_o_titulo_so_com_a_sigla():
    fama = {"linhas": [{"fama_os_id": 101, "status": "planned", "tipo": "preventive/predictive", "usina_id": 7,
                        "data_id_prevista": 20261201, "data_id_criacao": 20261120,
                        "titulo": "Manutenção preventiva mensal (MPM) do inversor do cliente X", "descricao": "segredo"}],
            "cadastro": {7: {"nomes": ["Usina Sete"], "equipe": "SP Leste 02", "gestor": "Pessoa Fictícia"}},
            "tirar_preventivas": False}
    r = P._reduzir_fama(fama)
    assert r["linhas"][0]["titulo"] == "MPM" and "descricao" not in r["linhas"][0]
    assert r["cadastro"] == {"7": {"nomes": ["Usina Sete"], "equipe": "SP Leste 02"}}
    assert r["tirar_preventivas"] is False


def test_o_pacote_importa_sem_o_nexus(app, cliente, pc, tmp_path):
    """O adaptador da FAMA do pacote importa numa pasta solta, sem o Nexus no caminho (o que o aplicativo faz)."""
    rid = cliente.post("/t/pcm/pc/rodada", json={"semana": "2026-W41"}, headers=pc).get_json()["id"]
    pasta = tmp_path / "solto"
    zipfile.ZipFile(io.BytesIO(cliente.get(f"/t/pcm/pc/rodada/{rid}/pacote", headers=pc).data)).extractall(pasta)
    r = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, sys.argv[1]); import pcm.fama_motor as f;"
                        " print(f.sigla({'tipo': 'preventive/predictive', 'titulo': 'MPA'}))", str(pasta)],
                       capture_output=True, text=True, cwd=str(pasta), timeout=120)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "MPA"


# ── a tela ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_tela_liga_e_desliga_o_computador(app, logado, config):
    app.config.update({k: v for k, v in config.items() if k != "TESTING"})
    html = logado.get("/t/pcm/gerar").get_data(as_text=True)
    assert "Gerar no PC" in html and "entregue pelo administrador" in html
    app.config["NEXUS_PCM_APP_URL"] = "https://exemplo.test/NexusPCM.exe"
    assert 'href="https://exemplo.test/NexusPCM.exe"' in logado.get("/t/pcm/gerar").get_data(as_text=True)
    # o endereço do código é o de fora (o Origin da tela), e não o de dentro do servidor atrás do proxy (a prova de 27/11)
    r = logado.post("/t/pcm/gerar/pc/ligar", data={"nome": "PC do PCM"}, headers={"Origin": "http://localhost"})
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and P.PREFIXO in html and "não aparece de novo" in html
    import re as _re
    cod = _re.search(r'id="pc-codigo"[^>]*value="([^"]+)"', html).group(1)
    import base64 as _b64
    b = cod[len(P.PREFIXO):]
    assert json.loads(_b64.urlsafe_b64decode(b + "=" * (-len(b) % 4)))["u"] == "http://localhost"
    assert r.headers.get("Cache-Control") == "no-store"
    comp = P.computadores(app.config)[0]
    assert P.PREFIXO not in logado.get("/t/pcm/gerar").get_data(as_text=True)       # o código não aparece de novo
    assert logado.post("/t/pcm/gerar/pc/desligar", data={"id": comp["id"]}).status_code == 303
    assert P.computadores(app.config)[0]["ativo"] is False


# ── o aplicativo (sem a janela): a rodada inteira contra o Nexus de teste ───────────────────────────────────────────────
def _app_pcm():
    import importlib.util
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "ferramentas" / "nexus_pcm_app" / "nexus_pcm.py"
    spec = importlib.util.spec_from_file_location("nexus_pcm_app_teste", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _NexusDeTeste:
    """O `Nexus` do aplicativo falando com o cliente de teste do Flask (as mesmas rotas e a mesma chave)."""

    def __init__(self, cliente, cab):
        self.c, self.cab = cliente, cab

    def rodada(self, semana):
        return self.c.post("/t/pcm/pc/rodada", json={"semana": semana}, headers=self.cab).get_json()

    def pacote(self, rid):
        return self.c.get(f"/t/pcm/pc/rodada/{rid}/pacote", headers=self.cab).data

    def credencial(self):
        return self.c.get("/t/pcm/pc/credencial", headers=self.cab).get_json()

    def andamento(self, rid, etapa):
        self.c.post(f"/t/pcm/pc/rodada/{rid}/andamento", json={"etapa": etapa}, headers=self.cab)

    def entregar(self, rid, planilha, log, relato):
        dados = {"relato": json.dumps(relato), "log": (io.BytesIO(log.read_bytes()), "log.txt")}
        if planilha is not None:
            dados["planilha"] = (io.BytesIO(planilha.read_bytes()), "sombra.xlsx")
        return self.c.post(f"/t/pcm/pc/rodada/{rid}/entregar", headers=self.cab, data=dados).get_json()


def test_o_aplicativo_gera_no_pc_e_devolve(app, cliente, pc, tmp_path, monkeypatch):
    """O `rodar` do aplicativo de verdade: abre a rodada, baixa o pacote, pede as chaves ao Nexus, roda o motor (o falso
    dos testes da geração, que confere os insumos e o ambiente: a chave do Fracttal tem de ter vindo do Nexus) num
    processo à parte e devolve a planilha; o Nexus termina a rodada. Nada fica no disco do PC depois."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "pc"))
    m = _app_pcm()
    avisos = []
    v = m.rodar(_NexusDeTeste(cliente, pc), "2026-W41", lambda t, x: avisos.append((t, x)))
    assert v["estado"] == "ok", G.log(app.config, v["id"])
    st = G.ler_status(app.config, v["id"])
    assert st["resumo"]["linhas"] == 2 and "semana pedida: 2026-W41" in G.log(app.config, v["id"])
    assert [x for t, x in avisos if t == "etapa"][-1] == ("devolver", "ok")
    assert not any((tmp_path / "pc" / "NexusPCM" / "rodadas").iterdir())       # a pasta da rodada saiu do PC


def test_o_codigo_do_aplicativo():
    m = _app_pcm()
    cod = P.codigo(URL, "chave-de-teste")
    assert m.abrir_codigo("  " + cod[:20] + "\n" + cod[20:] + " ") == (URL, "chave-de-teste")     # colado com quebra
    with pytest.raises(ValueError):
        m.abrir_codigo("qualquer coisa")
    with pytest.raises(ValueError):
        m.abrir_codigo(P.PREFIXO + "cortado")


# ── a vigia da memória no servidor ────────────────────────────────────────────────────────────────────────────────────
def test_a_vigia_para_so_o_motor_perto_do_teto(config, tmp_path, monkeypatch):
    """No servidor, perto do teto de memória do serviço, o Nexus para o motor (o servidor não cai) e a rodada diz para
    gerar no PC. O motor falso dorme 30 s: a vigia o para muito antes."""
    from test_pcm_geracao import motor_falso
    config["NEXUS_PCM_MOTOR"] = str(motor_falso(tmp_path, espera=30))
    monkeypatch.setattr(G, "VIGIA_S", 0.05)
    monkeypatch.setattr(G, "_memoria", lambda: (2900, 3072))
    r = G.iniciar(config, "2026-W41")
    st = G.aguardar(config, r["id"], 60)
    assert st["estado"] == "falhou" and st.get("memoria") is True
    assert "Gere no PC" in st["erro"] and st["duracao_s"] < 20
    assert "[memória] o Nexus parou o motor com 2900 MB de 3072 MB" in G.log(config, r["id"])


def test_a_vigia_so_anota_longe_do_teto(config, monkeypatch):
    monkeypatch.setattr(G, "VIGIA_S", 0.05)
    monkeypatch.setattr(G, "ANOTA_S", 0.0)
    monkeypatch.setattr(G, "_memoria", lambda: (1200, 3072))
    r = G.iniciar(config, "2026-W41")
    st = G.aguardar(config, r["id"], 60)
    assert st["estado"] == "ok"


def test_o_endereco_do_codigo_e_o_de_fora(app):
    """Atrás do proxy, o Nexus se vê pelo endereço de dentro (a prova de 27/11/2026: https://10.32.28.19:5070); o código
    leva o Origin da tela, o endereço que a pessoa usa."""
    from nexus.pcm import telas as T
    with app.test_request_context("/t/pcm/gerar/pc/ligar", base_url="https://10.0.0.9:5070",
                                  headers={"Origin": "https://nexus.exemplo.test"}):
        assert T._endereco_publico() == "https://nexus.exemplo.test"
    with app.test_request_context("/t/pcm/gerar/pc/ligar", base_url="https://10.0.0.9:5070"):
        assert T._endereco_publico() == "https://10.0.0.9:5070"


def test_a_preparacao_que_quebra_diz_o_motivo(cliente, pc, monkeypatch):
    """O erro inesperado na preparação volta com o tipo e a mensagem (a prova de 27/11/2026 só via "O Nexus respondeu 500")."""
    def quebra(*a, **k):
        raise KeyError("usina_id")
    monkeypatch.setattr(P, "abrir_rodada", quebra)
    r = cliente.post("/t/pcm/pc/rodada", json={"semana": "2026-W49"}, headers=pc)
    assert r.status_code == 500 and "KeyError" in r.get_json()["erro"] and "usina_id" in r.get_json()["erro"]


# ── a limpeza das rodadas antigas (a cota de disco do servidor, 27/11/2026) ─────────────────────────────────────────────
def test_a_limpeza_tira_so_os_caches_das_rodadas_antigas(config):
    base = G.pasta_trabalho(config) / "geracoes"
    nomes = ["20261101-080000-2026-W45", "20261108-080000-2026-W46", "20261115-080000-2026-W47", "20261122-080000-2026-W48"]
    for n in nomes:
        p = base / n
        (p / "saida").mkdir(parents=True)
        (p / "status.json").write_text(json.dumps({"id": n, "estado": "ok"}), encoding="utf-8")
        (p / "saida" / "sombra.xlsx").write_bytes(b"PK" + b"x" * (3 * 2**20))      # a planilha grande fica
        (p / ".cache_semanal_api.pkl").write_bytes(b"x" * 1000)
        (p / "BD_gerado.xlsx").write_bytes(b"x" * (3 * 2**20))
        (p / "Observacoes_Semana.txt").write_text("pequeno", encoding="utf-8")
    r = G.limpar_rodadas(config)
    assert r["rodadas"] == 2 and r["arquivos"] == 4 and r["mb"] > 5
    for n in nomes[:2]:                                     # as antigas: só os caches saíram
        p = base / n
        assert not (p / ".cache_semanal_api.pkl").exists() and not (p / "BD_gerado.xlsx").exists()
        assert (p / "saida" / "sombra.xlsx").exists() and (p / "status.json").exists() and (p / "Observacoes_Semana.txt").exists()
    for n in nomes[2:]:                                     # as duas mais novas ficam inteiras
        assert (base / n / ".cache_semanal_api.pkl").exists()
    assert G.limpar_rodadas(config)["arquivos"] == 0


def test_cota_de_disco_cheia_avisa_no_aplicativo(cliente, pc, monkeypatch):
    def cheio(*a, **k):
        raise OSError(122, "Disk quota exceeded")
    monkeypatch.setattr(P, "abrir_rodada", cheio)
    r = cliente.post("/t/pcm/pc/rodada", json={"semana": "2026-W49"}, headers=pc).get_json()
    assert "disco do servidor está cheio" in r["erro"]


# ── o histórico das gerações: o "Mostrar tudo" e a pasta sem status (27/11/2026) ────────────────────────────────────────
def _rodadas(config, n):
    base = G.pasta_trabalho(config) / "geracoes"
    ids = []
    for i in range(n):
        rid = f"202611{10 + i:02d}-080000-2026-W{40 + i:02d}"
        (base / rid).mkdir(parents=True)
        (base / rid / "status.json").write_text(json.dumps({"id": rid, "semana": rid[-8:], "estado": "ok",
                                                             "inicio": "2026-11-10T08:00:00-03:00"}), encoding="utf-8")
        ids.append(rid)
    return base, ids


def test_mostrar_tudo_e_a_pasta_sem_status(app, logado, config):
    """Uma pessoa do PCM, 27/11/2026: "deixar o histórico visível? todas as que foram geradas, como um botão de mostrar
    tudo". E as tentativas que morreram antes de gravar o status (a cota de disco cheia) contavam nas 8 e a lista encolhia."""
    app.config.update({k: v for k, v in config.items() if k != "TESTING"})
    base, ids = _rodadas(app.config, 10)
    for i in range(3):                                       # 3 pastas sem status, as mais novas
        (base / f"20261130-08000{i}-2026-W49").mkdir()
    assert len(G.ultimas(app.config)) == 8 and len(G.ultimas(app.config, None)) == 10
    html = logado.get("/t/pcm/gerar").get_data(as_text=True)
    lista = html.split('id="passo-historico"')[1]
    assert lista.count('class="linha"') == 8 and "Mostrar tudo (10)" in lista
    tudo = logado.get("/t/pcm/gerar?historico=tudo").get_data(as_text=True).split('id="passo-historico"')[1]
    assert tudo.count('class="linha"') == 10 and "Mostrar só as últimas" in tudo
    # a limpeza tira a pasta sem status com mais de 1 h
    import os, time
    velha = base / "20261130-080000-2026-W49"
    os.utime(velha, (time.time() - 7200, time.time() - 7200))
    assert G.limpar_rodadas(app.config).get("vazias") == 1 and not velha.exists()
