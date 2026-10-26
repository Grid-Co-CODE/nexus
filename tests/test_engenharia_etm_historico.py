"""O histórico do app de ETM trazido uma vez para o Nexus (Levi, 26/10/2026: "Traz 1 vez, para as OSs em aberto bota
esses comentários na nota da OS."). O app guardava uma Issue por OS num repositório privado do GitHub: os comentários
("**Autor:**\\ntexto") e as marcações como labels. GitHub, Fracttal e banco falsos; nomes de mentira."""
from datetime import datetime, timezone

import pytest

from nexus.engenharia import etm_historico as H

REPO = "dono/repositorio-de-teste"


class _Resp:
    def __init__(self, status, dados):
        self.status_code, self._d = status, dados

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class GitHubFalso:
    """As issues do app: a OS 17001 (aberta) com dois comentários e duas labels, a 17004 (fechada) com um comentário, a
    17005 sem nada, um pull request e uma issue que não é de OS."""

    def __init__(self, status=200):
        self.status, self.pedidos = status, []
        self.issues = [
            {"number": 1, "title": "OS 17001", "comments": 2, "updated_at": "2026-10-20T10:00:00Z",
             "labels": [{"name": "Falha de Comunicação"}, {"name": "Stand By"}]},
            {"number": 2, "title": "OS 17004", "comments": 1, "updated_at": "2026-10-10T10:00:00Z", "labels": []},
            {"number": 3, "title": "OS 17005", "comments": 0, "updated_at": "2026-10-09T10:00:00Z", "labels": []},
            {"number": 4, "title": "Ajuste do app", "comments": 3, "labels": [], "pull_request": {}},
            {"number": 5, "title": "Ideias", "comments": 0, "labels": []},
        ]
        self.comentarios = {
            1: [{"id": 901, "body": "**Pessoa Um:**\nSem sinal desde sábado.", "created_at": "2026-10-18T12:00:00Z"},
                {"id": 902, "body": "**Pessoa Dois:**\nChip trocado.\nVoltou a transmitir.", "created_at": "2026-10-19T13:30:00Z"}],
            2: [{"id": 903, "body": "texto sem autor", "created_at": "2026-10-05T09:00:00Z"}]}
        self.eventos = {1: [{"event": "labeled", "label": {"name": "Stand By"}, "created_at": "2026-10-18T15:00:00Z"},
                            {"event": "labeled", "label": {"name": "Falha de Comunicação"}, "created_at": "2026-10-19T14:00:00Z"},
                            {"event": "unlabeled", "label": {"name": "Sujidade"}, "created_at": "2026-10-19T14:00:00Z"}]}

    def get(self, url, headers=None, params=None, timeout=None):
        self.pedidos.append(url)
        assert headers["Authorization"] == "Bearer token-de-teste"
        if self.status != 200:
            return _Resp(self.status, {"message": "Bad credentials"})
        if (params or {}).get("page", 1) > 1:
            return _Resp(200, [])
        if url.endswith(f"/repos/{REPO}/issues"):
            return _Resp(200, self.issues)
        n = int(url.split("/issues/")[1].split("/")[0])
        if url.endswith("/comments"):
            return _Resp(200, self.comentarios.get(n, []))
        if url.endswith("/events"):
            return _Resp(200, self.eventos.get(n, []))
        raise AssertionError(url)


# ── a leitura do GitHub ──────────────────────────────────────────────────────────────────────────────────────────────
def test_o_corpo_do_comentario_do_app_vira_autor_e_texto():
    c = H._comentario({"id": 5, "body": "**Pessoa Um:**\nTexto\nlinha 2", "created_at": "2026-10-18T12:00:00Z"})
    assert c == {"id": "5", "autor": "Pessoa Um", "texto": "Texto\nlinha 2", "data": "2026-10-18T12:00:00Z"}
    assert H._comentario({"id": 6, "body": "solto"})["autor"] == "Desconhecido"


def test_le_as_issues_das_os_com_os_comentarios_e_as_datas_das_labels():
    gh = GitHubFalso()
    d = H.ler_github("token-de-teste", REPO, sessao=gh)
    assert sorted(d) == ["17001", "17004", "17005"]                    # nem o pull request nem a issue solta
    assert [c["autor"] for c in d["17001"]["comentarios"]] == ["Pessoa Um", "Pessoa Dois"]
    assert d["17001"]["labels"] == {"Falha de Comunicação", "Stand By"}
    assert d["17001"]["datas"] == {"Stand By": "2026-10-18T15:00:00Z", "Falha de Comunicação": "2026-10-19T14:00:00Z"}
    # sem comentário, sem pedido dos comentários; sem label, sem pedido dos eventos
    assert not any("/issues/3/" in u for u in gh.pedidos) and not any("/issues/2/events" in u for u in gh.pedidos)


def test_sem_acesso_ao_repositorio_diz():
    with pytest.raises(H.SemAcesso, match="token"):
        H.ler_github("token-de-teste", REPO, sessao=GitHubFalso(status=401))


def test_as_labels_viram_marcacoes_com_a_data_de_la():
    it = {"numero": 7, "labels": {"Sujidade", "Stand By", "Em Acompanhamento", "Finalizado pela Engenharia",
                                  "Chamado de Garantia", "bug"},
          "datas": {"Sujidade": "2026-10-19T14:00:00Z"}, "atualizada": "2026-10-20T10:00:00Z"}
    m = {x["origem_id"]: x for x in H.marcas_do_issue(it)}
    assert set(m) == {"7:Sujidade", "7:Stand By", "7:Em Acompanhamento", "7:Finalizado pela Engenharia",
                      "7:Chamado de Garantia"}                           # a label que o app não usa fica de fora
    assert (m["7:Sujidade"]["evento"], m["7:Sujidade"]["valor_id"]) == ("diagnostico", 3)
    assert m["7:Sujidade"]["quando"] == datetime(2026, 10, 19, 14, 0, tzinfo=timezone.utc)
    assert m["7:Stand By"]["quando"] == datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)   # sem o evento: a da issue
    assert (m["7:Stand By"]["evento"], m["7:Stand By"]["valor_id"], m["7:Stand By"]["ligado"]) == ("etiqueta", 2, True)
    assert (m["7:Chamado de Garantia"]["evento"], m["7:Chamado de Garantia"]["valor_id"]) == ("status_pos", 1)
    assert m["7:Em Acompanhamento"]["evento"] == "acompanhamento" and m["7:Finalizado pela Engenharia"]["ligado"]


def test_o_plano_nao_repete_o_que_ja_veio():
    d = H.ler_github("token-de-teste", REPO, sessao=GitHubFalso())
    p = {x["folio"]: x for x in H.plano(d, ja_comentarios={"901"}, ja_marcas={"1:Stand By"})}
    assert set(p) == {"17001", "17004"}
    assert [c["id"] for c in p["17001"]["comentarios"]] == ["902"]
    assert [m["origem_id"] for m in p["17001"]["marcas"]] == ["1:Falha de Comunicação"]
    pv = H.previa(list(p.values()), abertas={"17001": True, "17004": False})
    assert pv == {"oss": 2, "comentarios": 2, "marcacoes": 1, "notas": 1}


# ── a importação (o banco e o Fracttal falsos) ─────────────────────────────────────────────────────────────────────────
@pytest.fixture
def importacao(app, monkeypatch):
    from pg_falso import ApiPGFalsa

    from nexus.cadastro.cifra import gerar_chave
    from nexus.engenharia import etm_marcas as M
    from nexus.engenharia import os_acompanhamento as O
    from nexus.engenharia import os_equipe
    from nexus.torres import engenharia as torre
    from test_engenharia_etm import w
    api = ApiPGFalsa()
    app.config.update(GRIDCO_DB_API="http://pg.falso", NEXUS_CHAVE_CADASTRO=gerar_chave(),
                      NEXUS_PESSOA_HMAC="hmac-teste", GRIDCO_SQL_TOKEN="tk")
    app.extensions["nexus_dados_sessao"] = api
    linhas = {"17001": [dict(w(17001, "Corretiva"), id_work_order=70001)],
              "17004": [dict(w(17004, "Corretiva", status=3, task="DONE"), id_work_order=70004)]}
    monkeypatch.setattr(os_equipe, "_ler_fracttal", lambda path: {"data": linhas.get(path.split("=", 1)[1].split("&")[0], [])})
    monkeypatch.setattr(torre, "_onde_do_cadastro",
                        lambda: (lambda texto, cod: {"usina_id": 7, "ligada_por": "de-para do Fracttal"}))
    M.limpar(), O.limpar(), H.limpar()
    notas = []

    def escrever(o, linhas_):
        notas.append((o["os"], list(linhas_)))
        return "sim"
    with app.app_context():
        yield {"api": api, "notas": notas, "escrever": escrever}
    M.limpar(), O.limpar(), H.limpar()
    app.extensions.pop("nexus_dados_sessao", None)


def _ler_e_importar(app, escrever):
    j = H.iniciar_leitura(app, "token-de-teste", REPO, sessao=GitHubFalso())
    assert j["fase"] == "lido", j
    return H.iniciar_importacao(app, escrever)


def test_importar_grava_comentarios_e_marcacoes_e_a_nota_so_nas_abertas(importacao, app):
    from nexus.engenharia import etm_marcas as M
    from nexus.engenharia import os_acompanhamento as O
    j = _ler_e_importar(app, importacao["escrever"])
    assert j["fase"] == "feito" and j["resultado"]["comentarios"] == 3 and j["resultado"]["marcacoes"] == 2
    # a nota só da OS aberta, numa escrita, do mais antigo ao mais novo, com a data de Brasília de lá
    assert importacao["notas"] == [("17001", ["[18/10/2026 09:00] Pessoa Um (Engenharia): Sem sinal desde sábado.",
                                              "[19/10/2026 10:30] Pessoa Dois (Engenharia): Chip trocado.\nVoltou a transmitir."])]
    est = O.estado(O.ler(forcar=True)["eventos"])
    a = est["70001"]["eventos"]
    assert [(e["nome"], e["texto"], e["nota"]) for e in a] == [
        ("Pessoa Dois", "Chip trocado.\nVoltou a transmitir.", "sim"), ("Pessoa Um", "Sem sinal desde sábado.", "sim")]
    assert a[1]["quando"] == datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
    fechada = est["70004"]["eventos"][0]
    assert fechada["nome"] == "Desconhecido"
    assert fechada["nota"].startswith("OS fechada no Fracttal")
    linhas = importacao["api"].linhas(O.LIVRO, O.ABA)
    assert {x["origem"] for x in linhas} == {"app_etm"} and {x["origem_id"] for x in linhas} == {"901", "902", "903"}
    m = M.estado(M.ler(forcar=True)["eventos"])["70001"]
    assert (m["diagnostico_id"], m["etiquetas"]) == (2, {2})
    assert {x["origem"] for x in importacao["api"].linhas(M.LIVRO, M.ABA)} == {"app_etm"}


def test_importar_de_novo_nao_repete_nada(importacao, app):
    from nexus.engenharia import os_acompanhamento as O
    _ler_e_importar(app, importacao["escrever"])
    j = _ler_e_importar(app, importacao["escrever"])
    assert j["fase"] == "feito" and j["resultado"]["comentarios"] == 0 and j["resultado"]["marcacoes"] == 0
    assert len(importacao["notas"]) == 1 and len(importacao["api"].linhas(O.LIVRO, O.ABA)) == 3


def test_nota_que_falha_fica_para_a_proxima(importacao, app):
    from nexus.engenharia import etm_marcas as M
    from nexus.engenharia import os_acompanhamento as O

    def cai(o, linhas_):
        raise RuntimeError("o Fracttal não respondeu")
    j = _ler_e_importar(app, cai)
    assert j["fase"] == "feito" and j["resultado"]["adiadas"] == ["17001"]
    ids = {x["origem_id"] for x in importacao["api"].linhas(O.LIVRO, O.ABA)}
    assert ids == {"903"}                                  # os da 17001 voltam na próxima, com a nota
    assert len(importacao["api"].linhas(M.LIVRO, M.ABA)) == 2   # as marcações não dependem da nota


def test_sessao_do_fracttal_vencida_para_tudo(importacao, app):
    from nexus.engenharia import os_acompanhamento as O

    def vencida(o, linhas_):
        raise H.SessaoVencida("a sessão do Fracttal venceu")
    j = _ler_e_importar(app, vencida)
    assert j["fase"] == "erro" and "entre de novo" in j["erro"] and not O.ler(forcar=True)["eventos"]


# ── a ponte e o painel ───────────────────────────────────────────────────────────────────────────────────────────────
URL_H = "/os/_nexus/engenharia/etm/historico"


def _ms(cliente, usuario, admin=False):
    """Quem entrou pela conta Microsoft (sem a sessão do Fracttal no OS Creator; pelo Fracttal, o portão encerraria o
    Nexus junto, e o caso nem chega aqui)."""
    import time
    with cliente.session_transaction() as s:
        s["logado"], s["admin"], s["usuario"] = True, admin, usuario
        s["via"], s["ms_ate"] = "microsoft", time.time() + 3600
    return cliente


def _admin(monkeypatch, email):
    """O administrador agora é o da lista de Base → Acessos, relida a cada pedido (`auth._admin_em_dia`)."""
    from nexus import auth
    monkeypatch.setattr(auth, "_admins", lambda: {email})


def test_so_o_administrador_e_com_o_que_falta_dito(app, cliente, monkeypatch):
    from test_engenharia_acompanhamento import ANA, SAME
    assert _ms(cliente, ANA).get(URL_H).status_code == 403
    _admin(monkeypatch, ANA["email"])
    _ms(cliente, ANA, admin=True)
    r = cliente.post(URL_H, json={"acao": "ler"}, headers=SAME)
    assert r.status_code == 400 and "NEXUS_ETM_GITHUB_TOKEN" in r.get_json()["erro"]
    assert cliente.get(URL_H).get_json()["fase"] == "parado"
    assert cliente.post(URL_H, json={"acao": "ler"}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_importar_sem_a_sessao_do_fracttal_pede_o_login(app, cliente, monkeypatch):
    from test_engenharia_acompanhamento import ANA, SAME
    _admin(monkeypatch, ANA["email"])
    monkeypatch.setitem(H._JOB, "fase", "lido")
    monkeypatch.setitem(H._JOB, "plano", [{"folio": "17001", "comentarios": [], "marcas": []}])
    r = _ms(cliente, ANA, admin=True).post(URL_H, json={"acao": "importar"}, headers=SAME)
    assert r.status_code == 401 and "Fracttal" in r.get_json()["erro"] and r.get_json()["login"]


def test_o_painel_so_para_o_administrador(app, cliente, monkeypatch):
    import time

    from test_engenharia_acompanhamento import ANA, _como

    from nexus.auth import setor_telas as ST
    from nexus.engenharia import etm as E
    from nexus.engenharia import etm_marcas as M
    monkeypatch.setattr(E, "dados", lambda: {"os": [], "lido": time.time(), "lendo": False, "erro": ""})
    monkeypatch.setattr(E, "pedir_releitura", lambda app=None, esperar=False, forcar=False: None)
    monkeypatch.setattr(M, "ler", lambda forcar=False: {"eventos": [], "lido_em": time.time(), "erro": ""})
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(), "setor": {"id": 1, "nome": "Engenharia"},
                                               "erro": ""})
    assert "Trazer o histórico do app de ETM" not in _ms(cliente, ANA).get("/t/engenharia/etm").get_data(as_text=True)
    _admin(monkeypatch, ANA["email"])
    html = _ms(cliente, ANA, admin=True).get("/t/engenharia/etm").get_data(as_text=True)
    assert "Trazer o histórico do app de ETM" in html and "nexusRota('/os/_nexus/engenharia/etm/historico')" in html


def test_a_nota_nao_repete_a_linha_que_ja_esta_la():
    from nexus.torres.oscreator import ponte

    class Api:
        escritas = []

        def get_os_detalhes(self, wid):
            return {"notas": "Antiga\n[18/10/2026 09:00] Pessoa Um (Engenharia): Sem sinal", "tarefas": [{"id": 1}]}

        def editar_nota_os(self, wid, nota):
            self.escritas.append(nota)
            return {"ok": True}

    class Regra:
        def nota_pode_editar(self, status, n):
            return True, ""

        def status_id_de(self, status, d):
            return 1
    api = Api()
    o = {"wid": 1, "status": "Em Processo", "nota": "Antiga"}
    novas = ["[18/10/2026 09:00] Pessoa Um (Engenharia): Sem sinal", "[19/10/2026 10:30] Pessoa Dois (Engenharia): Ok"]
    assert ponte._acrescentar_na_nota(api, Regra(), o, novas) == "sim"
    assert api.escritas == ["Antiga\n[18/10/2026 09:00] Pessoa Um (Engenharia): Sem sinal\n"
                            "[19/10/2026 10:30] Pessoa Dois (Engenharia): Ok"]
    api.escritas.clear()
    assert ponte._acrescentar_na_nota(api, Regra(), o, novas[:1]) == "sim" and api.escritas == []
