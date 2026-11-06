"""A Nova solicitação para a PERFORMANCE no OS Creator (Levi, 06/11/2026: "adicione mais um em solicitações agora
performance, será a mesma coisa porém com etiqueta de performance!"; para o responsável, "Só a equipe da Performance"; e a
equipe, "Já tem no setor da performance em base > acessos").

É a tela da Engenharia com o setor no endereço (`/os/solicitacao/performance`): a etiqueta PERFORMANCE (só ela), quem está
no setor Performance em Base → Acessos → Pessoas e setores (o gancho `MEMBROS_DO_SETOR`, que a ponte liga) e "Performance"
nas frases. O resto (tipo Administrativa, Classificação 1 Programada, as datas, os anexos, uma OS por ativo ou a agrupada)
é o da Engenharia, provado em `test_oscreator_solic_engenharia.py`, cujo Fracttal falso este usa (Ana Teste Silva 501,
Bruno Souza 502, Carla Dias 504). Nomes e códigos de mentira: o repositório é público."""
import pytest

from test_oscreator_solic_engenharia import ETIQ, _corpo, api, cli, reg  # noqa: F401 — o `cli` é a fixture de lá

from nexus import create_app
from nexus.cadastro import setor_ids
from nexus.torres.oscreator import ponte

SETOR_PERF = setor_ids.PERFORMANCE


@pytest.fixture
def equipe(monkeypatch):
    """O setor Performance do Nexus com a Ana (501) e a Carla (504); a lista se troca no teste."""
    membros = {"ids": {"501", "504"}}
    monkeypatch.setattr(reg, "MEMBROS_DO_SETOR", lambda setor: membros["ids"] if setor == "performance" else None)
    return membros


def test_a_nova_solicitacao_tem_a_porta_da_performance(cli, equipe):
    pcm = cli.get("/os/solicitacao").get_data(as_text=True)
    assert 'href="/os/solicitacao/performance">Performance</a>' in pcm
    r = cli.get("/os/solicitacao/performance")
    assert r.status_code == 200
    h = r.get_data(as_text=True)
    assert '<a class="os-seg-btn on" role="tab" aria-selected="true" href="/os/solicitacao/performance">Performance</a>' in h
    assert '<a class="os-seg-btn" role="tab" aria-selected="false" href="/os/solicitacao/engenharia">Engenharia</a>' in h
    assert "Solicitação à Performance" in h and "Responsável da Performance <i>*</i>" in h and 'data-setor="performance"' in h
    eng = cli.get("/os/solicitacao/engenharia").get_data(as_text=True)          # a da Engenharia segue como era
    assert "Responsável da Engenharia <i>*</i>" in eng and 'data-setor="engenharia"' in eng


def test_os_responsaveis_sao_os_do_setor_performance(cli, equipe):
    j = cli.get("/os/api/solicitacao/performance/responsaveis").get_json()
    assert [p["name"] for p in j["pessoas"]] == ["Ana Teste Silva", "Carla Dias"] and j["configurado"] is True
    eng = cli.get("/os/api/solicitacao/engenharia/responsaveis").get_json()       # a da Engenharia: os nomes do .env
    assert [p["name"] for p in eng["pessoas"]] == ["Ana Teste Silva", "Bruno Souza"]


def test_setor_vazio_ou_fora_a_tela_diz(cli, equipe, monkeypatch):
    equipe["ids"] = set()
    j = cli.get("/os/api/solicitacao/performance/responsaveis").get_json()
    assert j["configurado"] is False and "Ninguém do setor Performance" in j["aviso"]
    monkeypatch.setattr(reg, "MEMBROS_DO_SETOR", lambda setor: None)            # o livro dos setores fora
    j = cli.get("/os/api/solicitacao/performance/responsaveis").get_json()
    assert j["configurado"] is False and j["aviso"].startswith("Não consegui ler os setores do Nexus")
    r = cli.post("/os/api/solicitacao/performance/criar", json=_corpo())
    assert r.status_code == 400 and r.get_json()["erro"] == "Escolha o responsável entre os nomes da Performance."
    assert cli.feito == {}


def test_criar_leva_so_a_etiqueta_performance(cli, equipe):
    r = cli.post("/os/api/solicitacao/performance/criar", json=_corpo())
    assert r.status_code == 200
    f = cli.feito
    assert (f["task_type"], f["subtasks"], f["etiqueta_ids"]) == ("Administrativa", [], [1])   # a PERFORMANCE, só ela
    assert f["tipo"] == {"id_c1": 11, "desc_c1": "Programada"} and f["id_responsible"] == 501
    assert r.get_json()["mensagem"].startswith("2 OS criada(s) para a Performance — Nº 15000, 15001")
    r = cli.post("/os/api/solicitacao/performance/criar", json=_corpo(agrupar=True))
    assert r.status_code == 200 and cli.agrupada["etiqueta_ids"] == [1]
    assert r.get_json()["mensagem"].startswith("1 OS criada para a Performance — Nº 15100, com 2 atividade(s)")


def test_responsavel_de_fora_do_setor_e_recusado(cli, equipe):
    r = cli.post("/os/api/solicitacao/performance/criar", json=_corpo(responsavel={"id_personnel": 502}))   # Bruno: Engenharia
    assert r.status_code == 400 and r.get_json()["erro"] == "Escolha o responsável entre os nomes da Performance."
    assert cli.feito == {}


def test_sem_a_etiqueta_performance_no_fracttal_nenhuma_os_e_criada(cli, equipe, monkeypatch):
    monkeypatch.setattr(api, "get_labels", lambda: [dict(e) for e in ETIQ if e["id"] != 1])
    r = cli.post("/os/api/solicitacao/performance/criar", json=_corpo())
    assert r.status_code == 400
    assert r.get_json()["erro"] == "Não achei no Fracttal a etiqueta PERFORMANCE. Nenhuma OS foi criada."
    assert cli.feito == {}


def test_setor_desconhecido_nao_abre(cli):
    assert cli.get("/os/solicitacao/financeiro").status_code == 404
    assert cli.post("/os/api/solicitacao/financeiro/criar", json=_corpo()).status_code == 404


def test_o_gancho_da_ponte_le_a_ultima_decisao_de_cada_pessoa(monkeypatch, tmp_path):
    """`ponte.membros_do_setor`: quem está HOJE no setor Performance (a última decisão de cada pessoa no livro
    `nexus_setores`), pelo id do Fracttal; quem saiu do setor sai da lista; outro setor da Nova solicitação, None."""
    from nexus.cadastro import setores as S
    from nexus.campo import visao
    decisoes = [
        {"decidida_em": "2026-10-20T10:00:00Z", "fracttal_id": 501, "setor_id": SETOR_PERF},
        {"decidida_em": "2026-10-20T10:00:00Z", "fracttal_id": 502, "setor_id": SETOR_PERF},
        {"decidida_em": "2026-10-25T10:00:00Z", "fracttal_id": 502, "setor_id": setor_ids.ENGENHARIA},   # mudou de setor
        {"decidida_em": "2026-10-21T10:00:00Z", "fracttal_id": 504, "setor_id": SETOR_PERF},
    ]
    monkeypatch.setattr(S, "ler", lambda base, sessao, forcar=False: {"setores": [], "decisoes": list(decisoes), "erro": ""})
    monkeypatch.setattr(visao, "_sessao", lambda: object())
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste-" + "x" * 20, "NEXUS_SENHA_ADMIN": "senha-de-teste-1234",
                      "NEXUS_DADOS": str(tmp_path / "dados")})
    membros = ponte.membros_do_setor(app)
    assert membros("performance") == {"501", "504"} and membros("engenharia") is None
    monkeypatch.setattr(S, "ler", lambda base, sessao, forcar=False: {"setores": [], "decisoes": [], "erro": "fora"})
    assert membros("performance") is None                              # o livro fora e nada guardado: a tela diz
