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
    r = logado.post("/t/pcm/gerar/pc/ligar", data={"nome": "PC do PCM"})
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and P.PREFIXO in html and "não aparece de novo" in html
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
