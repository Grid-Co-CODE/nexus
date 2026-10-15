"""PCM → Acompanhamento (14/10/2026, Levi, com o pacote do painel de acompanhamento do PCM O&M: "Quero que libere na
seção de PCM essa visão de acompanhamento. O design quero alá Nexus, não quero que copie o design, mas as estruturas
quero sim que mantenha!"). O que se prova aqui: as contas do painel sobre as fontes do Nexus (o Fracttal pela Gestão PCM,
a programação, a Gerencial e a curadoria), a curadoria cifrada no banco (ida e volta), o mapa sem coordenada no
navegador, as rotas e a porta do setor PCM. Tudo de mentira: usinas, OS e pessoas inventadas."""
import gzip
import json
import shutil
import subprocess
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from test_campo_visao import banco  # noqa: F401  (fixture)
from test_setor_telas import ANA, _como, _sem_copias, setores  # noqa: F401  (fixtures)

from nexus.pcm.acompanhamento import curadoria as CUR
from nexus.pcm.acompanhamento import dados as D
from nexus.pcm.acompanhamento.mapa import Geo

HOJE = date(2026, 10, 14)
URL = "/t/pcm/acompanhamento"


@pytest.fixture(autouse=True)
def _tarde_de_hoje(monkeypatch):
    """A Gestão PCM conta os dias do meio-dia da data (a regra do painel): antes do meio-dia sai um a menos. A hora dos
    testes fica parada às 15h de HOJE, para o número não depender da hora em que o teste roda."""
    from nexus.pcm import gestao
    monkeypatch.setattr(gestao, "agora", lambda: datetime(2026, 10, 14, 15, 0, tzinfo=timezone(timedelta(hours=-3))))


def _t(os_, tarefa, estado="Não Iniciada", st="Em processo", cri="2026-08-01", prog="2026-09-01", tipo="Corretiva",
       usina="Cliente A - Usina X - SP", cluster="SP Leste 01", resp="Pessoa Um"):
    return {"os": os_, "tarefa": tarefa, "estado": estado, "osStatus": st, "criacao": cri, "dataProg": prog, "tipo": tipo,
            "usina": usina, "cluster": cluster, "responsavel": resp}


TAREFAS = [
    _t("100", "Trocar fusível"), _t("100", "Trocar fusível"), _t("100", "Limpar quadro", estado="Finalizada"),
    _t("200", "[Grid Co.] - MPA - Termografia", tipo="Preventiva", usina="Cliente B - Usina Y - BA", cluster="BA Norte 01"),
    _t("300", "Tarefa nova", cri="2026-10-10", prog="2026-10-12"),                    # aberta há 4 dias: fora do Radar
    _t("400", "Já feita", estado="Finalizada"),                                         # sem tarefa aberta: fora
    _t("500", "Em revisão", st="Verificação"),                                          # em revisão: fora
    _t("600", "Usina de teste", usina="Usina Teste - Teste 1 - SP"),
]
CURADORIA = [
    {"grupo": 2, "os": "100", "usina": "Usina X", "tipo": "MPA", "tot": 10, "pend": 9, "falta": "trocar fusível", "bl": ["Equipamento"]},
    {"grupo": 1, "os": "700", "usina": "Usina Z", "tipo": "MPA", "fim": "2026-09-14", "prazo": "2026-10-16", "bl": ["Laudo de óleo"]},
    {"grupo": 3, "os": "200", "usina": "Usina Y", "tipo": "MPS", "tot": 5, "pend": 5, "manual": True, "bl": []},
]
MP = {"geradoEm": "2026-10-14T12:00:00Z",
      "manut": [{"tipo": "MPA", "os": "100", "cliente": "Cliente A", "usina": "Cliente A - Usina X - SP", "cluster": "SP Leste 01",
                 "prevista": "2026-09-14", "status": "Em Execução", "relatorio": "", "ciclo": "2026", "supervisor": "Pessoa Sup",
                 "inicio": "", "termino": ""},
                {"tipo": "MPS", "os": "200", "cliente": "Cliente B", "usina": "Cliente B - Usina Y - BA", "cluster": "BA Norte 01",
                 "prevista": "2026-11-30", "status": "Programar", "equipe": "Supervisor(a): Pessoa Dois\nTécnico: X"}],
      "bd": {"100": {"fin": 1, "total": 3, "tasks": [{"prog": "2026-09-01"}]}}}
BD = {"semana_ativa": "2026-W42", "semanas": [
    {"week": "2026-W41", "num": 41, "geradaEm": "2026-10-02T21:54:41Z", "rows": [
        {"os_id": "100", "cluster": "SP Leste 01", "dia": "Segunda-feira", "usina": "Cliente A - Usina X - SP", "tipo": "Corretiva",
         "responsavel": "Pessoa Sup", "status": "Finalizados", "vezes": 2},
        {"os_id": "200", "cluster": "BA Norte 01", "dia": "Terça-feira NOTURNO", "usina": "Cliente B - Usina Y - BA", "tipo": "MPA",
         "responsavel": "", "status": "Não Iniciada", "vezes": 1},
        {"os_id": "999", "cluster": "SP Leste 01", "dia": "Quarta-feira", "usina": "x", "tipo": "Corretiva", "foraDoPlano": True}]},
    {"week": "2026-W42", "num": 42, "rows": [
        {"os_id": "100", "cluster": "SP Leste 01", "dia": "Segunda-feira", "usina": "Cliente A - Usina X - SP", "tipo": "Corretiva",
         "responsavel": "Pessoa Sup", "status": "", "vezes": 3}]}]}


# ── o Fracttal, pela Gestão PCM ─────────────────────────────────────────────────────────────────────────────────────
def test_os_em_processo_com_tarefa_aberta_e_o_radar_de_backlog():
    ab = {o["os"]: o for o in D.abertas(TAREFAS, HOJE)}
    assert set(ab) == {"100", "200", "300", "600"}                # 400 sem tarefa aberta, 500 em revisão
    assert (ab["100"]["open"], ab["100"]["tot"], ab["100"]["dias"]) == (2, 3, 43)
    assert D.totais(TAREFAS)["100"] == {"tot": 3, "open": 2}
    bkl = {b["os"]: b for b in D.backlog(TAREFAS, list(ab.values()), HOJE)}
    assert set(bkl) == {"100", "200"}                              # 300 tem 4 dias; 600 é usina de teste
    assert bkl["100"]["tit"] == ["Trocar fusível (×2)"] and bkl["100"]["pct"] == 33 and bkl["100"]["u"] == "Usina X"
    assert bkl["200"]["tipo"] == "Preventiva (MPA)" and bkl["200"]["cli"] == "Cliente B"


def test_a_programacao_executada_pela_regua_do_fechamento_e_as_rolagens():
    w = D.semanas(BD, {})
    assert set(w) == {"41", "42"} and w["41"]["ini"] == "2026-10-05" and w["41"]["fim"] == "2026-10-09"
    t41 = w["41"]["tasks"]
    assert len(t41) == 2                                            # a linha fora do plano não entra
    assert t41[0][1] == 0 and t41[0][6] == 1 and t41[0][5] == "Corretivas"      # finalizada = executada
    assert t41[1][7] is True and t41[1][4] == "TBD" and t41[1][5] == "MPA"     # noturna, sem responsável
    ab = D.abertas(TAREFAS, HOJE)
    assert D.rolagens(BD, ab) == {"100": 3}                          # a 200 entrou uma vez só: não rolou
    assert D.semana_atual(BD) == "42"


# ── a Gerencial e a curadoria ───────────────────────────────────────────────────────────────────────────────────────
def test_as_mpas_e_mpss_da_curadoria_com_a_gerencial_e_o_fracttal():
    linhas, painel = D.gerencial(MP, HOJE)
    assert [l["sup"] for l in linhas] == ["Pessoa Sup", "Pessoa Dois"]          # o supervisor da Equipe, na falta do campo
    assert painel[1]["atrasada"] is True and painel[1]["dias"] == 30 and painel[2]["atrasada"] is False
    tot = D.totais(TAREFAS)
    man = {"nne": "Pessoa NNE", "outros": "Pessoa Sul"}
    mpa = {r["os"]: r for r in D.mpa_mps(CURADORIA, linhas, tot, HOJE, man, "MPA")}
    x = mpa["100"]
    assert (x["pend"], x["tot"], x["prog"]) == (2, 3, 33)            # recalculado pelo Fracttal, não o 9 de 10 da curadoria
    assert x["linha"] == 1 and x["cli"] == "Cliente A" and x["atraso"] == 30 and x["manut"] == "Pessoa Sul"
    z = mpa["700"]                                                  # sem linha na Gerencial: fica com o nome da curadoria
    assert z["linha"] is None and z["u"] == "Usina Z" and z["parado"] == 30 and z["manut"] == ""
    mps = D.mpa_mps(CURADORIA, linhas, tot, HOJE, man, "MPS")[0]
    assert (mps["pend"], mps["tot"]) == (5, 5) and mps["manut"] == "Pessoa NNE"   # manual trava os números; BA é Nordeste
    esp = D.espelho(linhas, painel, list(mpa.values()), [mps])
    assert [(e["linha"], e["g"]) for e in esp] == [(1, 2), (2, 3)]


def test_sem_a_gerencial_o_atraso_vem_da_data_programada_do_fracttal():
    """15/10/2026 ("A dispersão não está funcionando direito"): o servidor sem a senha da Gerencial deixava toda MPA sem
    atraso, e o ponto ia para fora da escala. Sem a linha da Gerencial, vale a regra da Fila da Gestão PCM sem a planilha."""
    tar = [_t("800", "[Grid Co.] - MPA - Inspeção", tipo="Preventiva", prog="2026-09-04"),
           _t("800", "[Grid Co.] - MPA - Limpeza", tipo="Preventiva", prog="2026-10-20")]
    cur = [{"grupo": 2, "os": "800", "usina": "Usina W", "tipo": "MPA", "tot": 2, "pend": 2},
           {"grupo": 3, "os": "801", "usina": "Usina V", "tipo": "MPA", "tot": 2, "pend": 2}]      # OS sem tarefa: sem data
    r = {x["os"]: x for x in D.mpa_mps(cur, [], D.totais(tar), HOJE, {}, "MPA", D.atraso_fracttal(tar, HOJE))}
    assert r["800"]["atraso"] == 40 and r["800"]["atraso_fonte"] == "Fracttal"
    assert "atraso" not in r["801"]                                 # fica fora do gráfico, e a tela diz quantas
    linhas, _ = D.gerencial(MP, HOJE)                               # com a linha da Gerencial, vale a Data Prevista
    x = D.mpa_mps(CURADORIA, linhas, D.totais(TAREFAS), HOJE, {}, "MPA", D.atraso_fracttal(TAREFAS, HOJE))[0]
    assert x["atraso_fonte"] == "Gerencial" and x["atraso"] == 30


def test_a_cadeia_de_os_soma_as_pendencias_das_duas():
    it = {"grupo": 3, "os": "100", "usina": "U", "tipo": "MPA", "tot": 20, "cadeia": "100 (5 de 12) + 200 (5 de 8)"}
    x = D._pendencias(it, {"100": {"tot": 3, "open": 2}, "200": {"tot": 8, "open": 1}})
    assert (x["pend"], x["tot"], x["cadeia"]) == (3, 11, "100 (2 de 3) + 200 (1 de 8)")


@pytest.mark.parametrize("texto,cats", [
    ("Aguardando laudo de óleo do trafo", ["Laudo de óleo"]),
    ("Relatório retornado pela engenharia para correção", ["Correção da engenharia"]),
    ("Falta curva IV e equipe reduzida", ["Equipamento", "Equipe"]),
    ("Choveu a semana toda", ["Outros"]),
])
def test_categorias_do_bloqueio(texto, cats):
    assert D.classifica(texto) == cats


def test_supervisor_do_cluster_cadastro_vence_programacao_que_vence_gerencial():
    linhas, _ = D.gerencial(MP, HOJE)
    s = D.supervisores(BD, linhas, {})
    assert s["SP LESTE 01"] == "Pessoa Sup" and s["BA NORTE 01"] == "Pessoa Dois"
    assert D.supervisores(BD, linhas, {"SP Leste 01": "Pessoa do Cadastro"})["SP LESTE 01"] == "Pessoa do Cadastro"


# ── o mapa: a coordenada não sai do servidor ────────────────────────────────────────────────────────────────────────
def _geo():
    us = [SimpleNamespace(id="1", nome="Usina X", cliente="Cliente A", lat=-23.12345, lon=-46.54321),
          SimpleNamespace(id="2", nome="Usina Y", cliente="Cliente B", lat=-12.98765, lon=-38.45678)]
    return Geo(us, {D.norm("Cliente A - Usina X - SP"): "1"}, {"1": "Cliente A - Usina X - SP"})


def test_o_mapa_entrega_o_ponto_e_a_distancia_nunca_a_coordenada():
    geo = _geo()
    p = geo.ponto("Cliente A - Usina X - SP")
    assert isinstance(p, list) and len(p) == 2 and 0 <= p[0] <= 1000
    assert geo.ponto("Cliente B - Usina Y - BA") is not None        # sem de-para, pelo nome sem a UF
    assert geo.ponto("Cliente C - Usina Sem Lugar - MG") is None
    km = geo.km("Cliente A - Usina X - SP", "Cliente B - Usina Y - BA")
    assert 1400 < km < 1500                                         # São Paulo a Salvador, em linha reta
    assert geo.perto("Cliente A - Usina X - SP", ["Cliente B - Usina Y - BA"]) == [{"usina": "Cliente B - Usina Y - BA", "km": km}]
    assert sorted(geo.nomes()) == ["Cliente A - Usina X - SP", "Cliente B - Usina Y"]
    r = D.montar({"tarefas": TAREFAS}, BD, MP, CURADORIA, {}, HOJE, geo=geo)
    texto = json.dumps(r, ensure_ascii=False)
    for numero in ("23.12345", "46.54321", "12.98765", "38.45678", "-23.1", "-46.5"):
        assert numero not in texto                                  # nenhum número de coordenada vai para a tela
    assert len(r["EXTRA"]["mapa"]["ufs"]) == 27 and r["EXTRA"]["mapa"]["viewbox"].startswith("0 0 1000 ")


# ── a curadoria no banco ────────────────────────────────────────────────────────────────────────────────────────────
def test_a_curadoria_vai_cifrada_e_volta_igual(app, banco):  # noqa: F811
    from nexus.auth import setor_telas
    base, sessao = setor_telas._banco()
    r = CUR.gravar(CURADORIA, {"nne": "Pessoa NNE", "outros": "Pessoa Sul"}, app.config, base, sessao, origem="teste")
    assert r == {"gravadas": 4, "tiradas": 0}
    linhas = banco.linhas(CUR.LIVRO, CUR.ABA)
    assert len(linhas) == 4 and all(str(l["dados_cifrados"]).startswith("cofre:") or "cofre" in str(l["dados_cifrados"])[:12]
                                    or not any(n in str(l["dados_cifrados"]) for n in ("Usina", "fusível", "Pessoa"))
                                    for l in linhas)
    assert not any("fusível" in json.dumps(l, ensure_ascii=False) or "Pessoa" in json.dumps(l, ensure_ascii=False)
                   for l in linhas)                                 # o conteúdo não sai em claro
    lido = CUR.ler(app.config, base, sessao, forcar=True)
    assert lido["erro"] == "" and lido["ilegiveis"] == 0 and lido["manutencao"] == {"nne": "Pessoa NNE", "outros": "Pessoa Sul"}
    por_os = {it["os"]: it for it in lido["itens"]}
    assert por_os["100"]["falta"] == "trocar fusível" and por_os["200"]["manual"] is True
    # a 2ª carga sem um item: ele é tirado (ativo "não"), e o livro guarda a história
    r = CUR.gravar(CURADORIA[:2], {}, app.config, base, sessao, origem="teste")
    assert r == {"gravadas": 2, "tiradas": 2}                        # a MPS 200 e a regra da Manutenção saíram
    lido = CUR.ler(app.config, base, sessao, forcar=True)
    assert {it["os"] for it in lido["itens"]} == {"100", "700"} and lido["manutencao"] == {}
    assert len(banco.linhas(CUR.LIVRO, CUR.ABA)) == 8


def test_o_item_e_o_mesmo_em_qualquer_maquina():
    assert CUR.item_id({"tipo": "MPA", "usina": "Marabá 100", "os": "11019"}) == CUR.item_id(
        {"tipo": "MPA", "usina": "maraba 100", "os": " 11019 "})


# ── a tela ──────────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def fontes(app, tmp_path):
    (tmp_path / "g.json").write_text(json.dumps({"geradoEm": "2026-10-14T12:00:00", "tarefas": TAREFAS}), encoding="utf-8")
    (tmp_path / "bd.json").write_text(json.dumps(BD), encoding="utf-8")
    (tmp_path / "cur.json").write_text(json.dumps({"itens": CURADORIA, "manutencao": {"nne": "N", "outros": "S"}}), encoding="utf-8")
    app.config.update(NEXUS_PCM_GESTAO_FONTE=str(tmp_path / "g.json"), NEXUS_PCM_FONTE=str(tmp_path / "bd.json"),
                      NEXUS_PCM_CURADORIA_ARQUIVO=str(tmp_path / "cur.json"))
    from nexus.pcm import acompanhamento
    acompanhamento._CACHE.clear()
    yield
    acompanhamento._CACHE.clear()


def test_a_tela_e_os_dados_dela(logado, fontes):
    html = logado.get(URL).get_data(as_text=True)
    assert 'id="pa"' in html and "pcm-acomp.js" in html and 'data-tab="bkl"' in html and "Radar de Backlog" in html
    assert 'data-dados="/t/pcm/acompanhamento/dados.json"' in html
    r = logado.get(URL + "/dados.json", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200 and r.headers["Content-Encoding"] == "gzip" and r.headers["Cache-Control"] == "no-store"
    j = json.loads(gzip.decompress(r.get_data()))
    assert {x["os"] for x in j["DATA"]["mpa"]} == {"100", "700"} and len(j["DATA"]["backlog"]) == 2
    assert j["FONTES"]["curadoria"] == "arquivo" and j["AVISOS"]["gerencial"] == "sem_chave"
    assert j["EXTRA"]["mapa"] is None and j["AVISOS"]["mapa"]                    # nos testes, sem o cadastro
    assert logado.get(URL + "/rota?o=Cliente+A+-+Usina+X+-+SP").get_json() == {"km": None, "perto": []}
    assert logado.get(URL + "?aba=map").status_code == 200


def test_e_do_setor_pcm(app, logado, setores):  # noqa: F811
    from nexus.torres.pcm import TORRE
    assert TORRE.tela("acompanhamento").do_setor == "PCM"
    ana = _como(app, ANA)                                          # a Ana é da Performance
    assert ana.get(URL).status_code == 403 and ana.get(URL + "/dados.json").status_code == 403


def test_o_javascript_da_tela_abre():
    node = shutil.which("node")
    if not node:
        pytest.skip("node não instalado")
    r = subprocess.run([node, "--check", "nexus/static/pcm-acomp.js"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
