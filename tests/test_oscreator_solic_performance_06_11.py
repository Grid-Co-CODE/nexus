"""A Nova solicitação para a PERFORMANCE no OS Creator (Levi, 06/11/2026: "adicione mais um em solicitações agora
performance, será a mesma coisa porém com etiqueta de performance!"; e, para o responsável, "Só a equipe da Performance").

É a tela da Engenharia com o setor no endereço (`/os/solicitacao/performance`): a etiqueta PERFORMANCE (só ela), os nomes
da equipe da Performance (`OS_WEB_PERFORMANCE_RESPONSAVEIS`, que a tela Chaves do Nexus também guarda, para não depender da
T.I.) e "Performance" nas frases. O resto (tipo Administrativa, Classificação 1 Programada, as datas, os anexos, uma OS por
ativo ou a agrupada) é o da Engenharia, provado em `test_oscreator_solic_engenharia.py`, cujo Fracttal falso este usa.
Nomes e códigos de mentira: o repositório é público."""
from test_oscreator_solic_engenharia import ETIQ, _corpo, api, cli, reg  # noqa: F401 — o `cli` é a fixture de lá

from conftest import SENHA_TESTE
from nexus import create_app
from nexus.auth import chaves as K

ENV_PERF = "OS_WEB_PERFORMANCE_RESPONSAVEIS"


def test_a_nova_solicitacao_tem_a_porta_da_performance(cli):
    pcm = cli.get("/os/solicitacao").get_data(as_text=True)
    assert 'href="/os/solicitacao/performance">Performance</a>' in pcm
    r = cli.get("/os/solicitacao/performance")
    assert r.status_code == 200
    h = r.get_data(as_text=True)
    assert '<a class="os-seg-btn on" role="tab" aria-selected="true" href="/os/solicitacao/performance">Performance</a>' in h
    assert '<a class="os-seg-btn" role="tab" aria-selected="false" href="/os/solicitacao/engenharia">Engenharia</a>' in h
    assert "Solicitação à Performance" in h and "Responsável da Performance <i>*</i>" in h
    assert 'data-setor="performance"' in h and 'data-setor-env="%s"' % ENV_PERF in h
    eng = cli.get("/os/solicitacao/engenharia").get_data(as_text=True)          # a da Engenharia segue como era
    assert "Responsável da Engenharia <i>*</i>" in eng and 'data-setor="engenharia"' in eng


def test_os_responsaveis_sao_os_da_equipe_da_performance(cli, monkeypatch):
    monkeypatch.setattr(reg, "LER_NOMES", None)
    monkeypatch.setenv(ENV_PERF, "Carla")
    j = cli.get("/os/api/solicitacao/performance/responsaveis").get_json()
    assert [p["name"] for p in j["pessoas"]] == ["Carla Dias"] and j["configurado"] is True
    eng = cli.get("/os/api/solicitacao/engenharia/responsaveis").get_json()       # a lista da Engenharia não muda
    assert [p["name"] for p in eng["pessoas"]] == ["Ana Teste Silva", "Bruno Souza"]
    monkeypatch.delenv(ENV_PERF)
    assert cli.get("/os/api/solicitacao/performance/responsaveis").get_json()["configurado"] is False


def test_criar_leva_so_a_etiqueta_performance(cli, monkeypatch):
    monkeypatch.setattr(reg, "LER_NOMES", None)
    monkeypatch.setenv(ENV_PERF, "Ana Teste")
    r = cli.post("/os/api/solicitacao/performance/criar", json=_corpo())
    assert r.status_code == 200
    f = cli.feito
    assert (f["task_type"], f["subtasks"], f["etiqueta_ids"]) == ("Administrativa", [], [1])   # a PERFORMANCE, só ela
    assert f["tipo"] == {"id_c1": 11, "desc_c1": "Programada"}
    assert r.get_json()["mensagem"].startswith("2 OS criada(s) para a Performance — Nº 15000, 15001")
    r = cli.post("/os/api/solicitacao/performance/criar", json=_corpo(agrupar=True))
    assert r.status_code == 200 and cli.agrupada["etiqueta_ids"] == [1]
    assert r.get_json()["mensagem"].startswith("1 OS criada para a Performance — Nº 15100, com 2 atividade(s)")


def test_responsavel_de_fora_da_equipe_da_performance_e_recusado(cli, monkeypatch):
    monkeypatch.setattr(reg, "LER_NOMES", None)
    monkeypatch.setenv(ENV_PERF, "Carla")                      # a 501 é da Engenharia, não da Performance
    r = cli.post("/os/api/solicitacao/performance/criar", json=_corpo())
    assert r.status_code == 400 and r.get_json()["erro"] == "Escolha o responsável entre os nomes da Performance."
    assert cli.feito == {}


def test_sem_a_etiqueta_performance_no_fracttal_nenhuma_os_e_criada(cli, monkeypatch):
    monkeypatch.setattr(reg, "LER_NOMES", None)
    monkeypatch.setenv(ENV_PERF, "Ana Teste")
    monkeypatch.setattr(api, "get_labels", lambda: [dict(e) for e in ETIQ if e["id"] != 1])
    r = cli.post("/os/api/solicitacao/performance/criar", json=_corpo())
    assert r.status_code == 400
    assert r.get_json()["erro"] == "Não achei no Fracttal a etiqueta PERFORMANCE. Nenhuma OS foi criada."
    assert cli.feito == {}


def test_setor_desconhecido_nao_abre(cli):
    assert cli.get("/os/solicitacao/financeiro").status_code == 404
    assert cli.post("/os/api/solicitacao/financeiro/criar", json=_corpo()).status_code == 404


def test_a_lista_da_tela_chaves_do_nexus_vale_por_cima_do_env(monkeypatch, tmp_path):
    """A equipe colada na tela Chaves do Nexus (cifrada na pasta de dados, sem a T.I.) vale por cima do .env; os espaços de
    dentro dos nomes ficam (numa chave, todo espaço sai). A da Engenharia, que a tela não guarda, segue no .env."""
    monkeypatch.setattr(reg, "LER_NOMES", reg.LER_NOMES)              # a ponte o troca ao criar o app: volta no fim
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste-" + "x" * 20, "NEXUS_SENHA_ADMIN": SENHA_TESTE,
                      "NEXUS_DADOS": str(tmp_path / "dados")})
    app.config.update(TESTING=True)
    from nexus.torres.oscreator import ponte
    ponte.clone(app)                                                  # o clone nasce no 1º uso: é ele que liga o gancho
    K._CACHE.clear()
    monkeypatch.setenv(ENV_PERF, "Zeca")
    monkeypatch.setenv(reg.ENV_RESPONSAVEIS, "Ana Teste")
    aviso = K.gravar(app.config, ENV_PERF, "  Carla   Dias ;Bruno  Souza ", "teste")
    assert "2 nome(s)" in aviso and K.valor(ENV_PERF, app.config) == "Carla Dias ;Bruno Souza"
    assert reg.nomes_configurados(setor="performance") == ["Carla Dias", "Bruno Souza"]
    assert reg.nomes_configurados(setor="engenharia") == ["Ana Teste"]
    for ruim in ("", " ; ", "contato@exemplo.test", "Carla 123"):
        try:
            K.gravar(app.config, ENV_PERF, ruim, "teste")
        except K.Recusada:
            continue
        raise AssertionError("gravou: %r" % ruim)
    K._CACHE.clear()
