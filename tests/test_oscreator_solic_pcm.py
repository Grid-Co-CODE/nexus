"""A Área PCM do OS Creator Web como a do app de mesa (Levi, 13/10/2026: "Fila do PCM não está levando para a fila do PCM,
referência é a fila do app desktop, nem painel do PCM nem histórico nem temas. Também está demorando demais para
carregar!").

O que estes testes seguram:
- as quatro páginas da `SolicPcmTab` (Painel, Fila do PCM, Histórico, Temas), a barra delas e as portas do setor PCM;
- a régua do app: o Painel com as três colunas (até 40 cartões cada), a Fila só com as pendentes (a de outra coluna entra
  só para ler), o título no padrão do tema, as subtarefas do bloco [PCM] com o anexo, o técnico e a data sugeridos;
- as gravações: aprovar (com o anexo obrigatório, que a web perdia), mudar status / devolver (motivo obrigatório), a
  observação com o bloco de volta (linha em branco, como o app), cancelar, e os temas (salvar, arquivar);
- a VELOCIDADE: a lista é pedida UMA vez para Painel, Fila e Histórico; os catálogos, uma vez; quem grava esquece a
  lista; a carga fria é paralela; e o catálogo de ativos vencido não segura a página (é renovado por trás).
O api e o banco são dublês: nada vai à rede, nada é criado no Fracttal. Nomes e usinas são de mentira (repositório público)."""
import json
import re
import threading
import time
from pathlib import Path

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
import sys  # noqa: E402
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
import solic_spec as sp  # noqa: E402
import temas_store as ts  # noqa: E402
from os_web import criar_app, lancador, rotas  # noqa: E402
from os_web import rotas_solic as rs  # noqa: E402
from os_web import solic_web as sw  # noqa: E402

WEB = Path(ponte.RAIZ_CLONE, "os_web")
JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
USINA = "Cliente X - Usina Teste 1 - UF"
ATIVOS = [{"id": 11, "code": "TST-INV11", "description": "Inversor 1.1 Marca Teste", "tipo": "Inversor", "usina": USINA,
           "cliente": "Cliente X"},
          {"id": 12, "code": "TST-TRK1", "description": "Estrutura Trackers 1", "tipo": "Estrutura Trackers",
           "usina": USINA, "cliente": "Cliente X"}]
OBS = sp.observacao_com_bloco("Inversor desligando à tarde.", {
    "tema": "inversor_inspecao", "tecnico": "Ana Teste Silva", "data": "15/10/2026",
    "subtarefas": [{"tipo": "texto", "desc": "Medir isolação", "anexo": True}, {"tipo": "simnao", "desc": "Religou?"}]})


def _linha(n, status="Aberta", os_=None, obs="", ativo="Inversor 1.1 Marca Teste", item=11, code="TST-INV11",
           data="2026-10-13T11:00:00", quem="Pessoa Um"):
    return {"id_code": n, "cliente": "Cliente X", "usina": "Usina Teste 1", "ativo": ativo, "id_item": item, "code": code,
            "cor_status": "#F0B341", "tipo": "Inversor", "descricao": "Pedido %d" % n, "descricao_full": "Pedido %d inteiro" % n,
            "observacao": obs, "criado_por": quem, "data": data, "status_id": 1, "status": status,
            "os_folio": os_, "id_work_order": (9000 + n) if os_ else None}


LINHAS = [_linha(5001, obs=OBS), _linha(5002, "OS em processo", os_=777, ativo="Estrutura Trackers 1", item=12,
                                        code="TST-TRK1", quem="Pessoa Dois", data="2026-10-01T12:00:00"),
          _linha(5003, "Reaberta (refazer)"), _linha(5004, "Cancelada"), _linha(5005, "Aberta", item=None, code="SEM-CAT")]


def _cru(x):
    return {"id_code": x["id_code"], "items_description": x["ativo"] + " { %s }" % x["code"], "code_item": x["code"],
            "id_item": x["id_item"], "requests_x_status_description": x["status"], "description": x["descricao_full"],
            "observation": x["observacao"], "requested_by": x["criado_por"], "date": x["data"], "id_status": 1,
            "wo_folio": x["os_folio"], "id_work_order": x["id_work_order"]}


@pytest.fixture
def cli(monkeypatch, tmp_path):
    """O clone com o Fracttal e o banco FALSOS, a memória zerada e a rede proibida: um pedido que escapasse dos dublês
    derrubaria o teste em vez de ir ao Fracttal."""
    import requests

    def sem_rede(*a, **k):
        raise AssertionError("o teste tentou ir à rede")
    monkeypatch.setattr(requests.Session, "request", sem_rede)
    rotas._MEMO.clear()
    monkeypatch.setattr(rs, "_DISCO", {"mtime": None, "idx": None, "vence": 0.0})
    monkeypatch.setattr(rs, "_TENTOU", {"quando": 0.0})
    monkeypatch.setattr(api, "_code_loc", {})
    cat = tmp_path / "assets_cache.json"
    cat.write_text(json.dumps({"ts": time.time(), "ver": api._CACHE_VER, "assets": ATIVOS}), encoding="utf-8")
    monkeypatch.setattr(api, "ASSETS_CACHE", str(cat))
    chamadas, gravado = [], []

    def conta(nome, valor):
        def f(*a, **k):
            chamadas.append(nome)
            return valor() if callable(valor) else valor
        return f
    monkeypatch.setattr(api, "list_minhas_solicitacoes", conta("lista", lambda: [dict(x) for x in LINHAS]))
    monkeypatch.setattr(api, "get_responsaveis", conta("pessoas", [{"name": "Bruno Souza", "id_personnel": 2},
                                                                    {"name": "Ana Teste Silva", "id_personnel": 1},
                                                                    {"name": "Sem Id", "id_personnel": None}]))
    monkeypatch.setattr(api, "get_labels", conta("etiquetas", [{"id": 7, "description": "PERFORMANCE"},
                                                               {"id": 8, "description": "GARANTIA"}]))
    monkeypatch.setattr(api, "get_tipos_classif", conta("tipos", {"tipos": [{"description": "Corretiva"}],
                                                                 "c1": [{"description": "Programada"}],
                                                                 "c2": [{"description": "Elétrica"}]}))
    monkeypatch.setattr(api, "status_solicitacao_catalogo", conta("status", list(api.STATUS_SOLICITACAO)))
    monkeypatch.setattr(api, "get_conta_info", lambda: {"nome": "Pessoa Teste", "perfil": ""})
    monkeypatch.setattr(api, "_solicitacao_row", lambda idc: next((_cru(x) for x in LINHAS if str(x["id_code"]) == str(idc)), None))
    monkeypatch.setattr(api, "_code_to_loc", lambda: {a["code"]: ("Cliente X", "Usina Teste 1", a["tipo"]) for a in ATIVOS})
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: [dict(x) for x in ATIVOS])

    def aprovar(asset, titulo, subs, idc, idr, nome, **k):
        gravado.append(("aprovar", asset["code"], titulo, subs, idc, idr, nome, k))
        return {"ok": True, "os": {"wo_folio": 4321, "id_work_order": 99}}
    monkeypatch.setattr(api, "aprovar_solicitacao", aprovar)
    monkeypatch.setattr(api, "mudar_status_solicitacao", lambda *a: gravado.append(("status",) + a) or {"ok": True})
    monkeypatch.setattr(api, "editar_observacao_solicitacao", lambda *a: gravado.append(("obs",) + a) or {"ok": True})
    monkeypatch.setattr(api, "cancelar_solicitacao", lambda *a: gravado.append(("cancelar",) + a) or {"ok": True})
    monkeypatch.setattr(api, "get_solic_anexos", lambda idr: [{"nome": "foto.jpg", "url": "https://exemplo.invalid/f.jpg",
                                                               "is_image": True}, {"nome": "laudo.pdf", "url": "", "is_image": False}])
    monkeypatch.setattr(ts, "garantir", lambda: None)
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid", "perfil": ""}
    c.chamadas, c.gravado = chamadas, gravado
    return c


def _dados(html, id_):
    return json.loads(html.split('id="%s">' % id_, 1)[1].split("</script>", 1)[0])


# ── a navegação: a barra da SolicPcmTab e as portas do setor ─────────────────────────────────────────────────────────
def test_as_portas_do_setor_pcm_sao_as_da_area_pcm_do_app():
    portas = lancador.PORTAS_SETOR["pcm"]["portas"]
    assert [p["titulo"] for p in portas] == ["Painel", "Fila do PCM", "Histórico de solicitações", "Temas",
                                            "Clonagem de planos"]
    assert [p.get("href") for p in portas[:4]] == ["/os/solicitacao/painel", "/os/solicitacao/fila",
                                                   "/os/solicitacao/historico", "/os/solicitacao/temas"]
    assert [p["rodape"] for p in portas[:4]] == ["Acompanhar", "Aprovar", "Consultar", "Padronizar"]   # os selos do app
    for p in portas:
        assert p["icone"] in lancador.ICONES, p["icone"]
    secoes = dict(lancador.ABAS_SECOES)
    assert all(secoes[u] == "pcm" for u in ("/os/solicitacao/painel", "/os/solicitacao/fila", "/os/solicitacao/historico",
                                           "/os/solicitacao/temas"))
    card = next(s for s in lancador.SETORES if s["chave"] == "pcm")
    assert [p["rotulo"] for p in card["portas"]][1:] == ["Painel", "Fila do PCM", "Histórico de solicitações", "Temas"]


def test_a_barra_de_cima_e_a_do_app_e_marca_a_pagina(cli):
    for url, marcada in (("/os/solicitacao/painel", "Painel"), ("/os/solicitacao/fila", "Fila do PCM"),
                         ("/os/solicitacao/historico", "Histórico"), ("/os/solicitacao/temas", "Temas")):
        h = cli.get(url).get_data(as_text=True)
        nav = h.split('<nav class="spc-nav"', 1)[1].split("</nav>", 1)[0]
        assert re.findall(r">([^<>]+)</a>", nav) == ["&lsaquo; PCM", "Nova solicitação", "Painel", "Fila do PCM",
                                                     "Histórico", "Temas"], url
        assert re.search(r'class="on" aria-current="page">%s</a>' % marcada, nav), url
        assert 'href="/os/setor/pcm"' in nav


def test_o_setor_pcm_aquece_a_lista_e_os_outros_nao(cli):
    assert '"/os/api/solic/aquecer"' in cli.get("/os/setor/pcm").get_data(as_text=True)
    assert cli.post("/os/api/solic/aquecer").status_code == 204
    assert sorted(cli.chamadas) == ["etiquetas", "lista", "pessoas", "status", "tipos"]
    # a porta escolhida abre com tudo na memória: nenhum pedido a mais
    for url in ("/os/solicitacao/painel", "/os/solicitacao/fila", "/os/solicitacao/historico"):
        assert cli.get(url).status_code == 200
    assert len(cli.chamadas) == 5


# ── a memória: uma lista para as três páginas, quem grava a esquece ──────────────────────────────────────────────────
def test_a_lista_e_pedida_uma_vez_para_painel_fila_e_historico(cli):
    for url in ("/os/solicitacao/painel", "/os/solicitacao/fila", "/os/solicitacao/historico",
                "/os/solicitacao/fila?sel=5002"):
        assert cli.get(url).status_code == 200, url
    assert cli.chamadas.count("lista") == 1
    assert sorted(set(cli.chamadas)) == ["etiquetas", "lista", "pessoas", "status", "tipos"]
    assert all(cli.chamadas.count(n) == 1 for n in ("pessoas", "etiquetas", "status", "tipos"))
    cli.get("/os/solicitacao/painel?atualizar=1")                     # o "Atualizar" vai ao Fracttal de novo
    assert cli.chamadas.count("lista") == 2


@pytest.mark.parametrize("pedido", [
    ("/os/api/solic/5001/aprovar", {"id_responsible": 1, "responsavel": "Ana Teste Silva", "titulo": "T", "subtarefas": []}),
    ("/os/api/solic/5001/status", {"codigo": "REJECTED", "motivo": "duplicada"}),
    ("/os/api/solic/5001/observacao", {"relato": "novo"}),
    ("/os/api/solic/5001/cancelar", {"nota": ""}),
])
def test_quem_grava_esquece_a_lista(cli, pedido):
    cli.get("/os/solicitacao/fila")
    url, corpo = pedido
    assert cli.post(url, json=corpo).status_code == 200, url
    cli.get("/os/solicitacao/painel")
    assert cli.chamadas.count("lista") == 2, url


def test_a_carga_fria_e_paralela(cli, monkeypatch):
    """Cinco leituras de 0,3 s cada: em fila custariam 1,5 s; juntas, a mais lenta."""
    def lento(nome, valor):
        def f(*a, **k):
            time.sleep(0.3)
            return valor
        return f
    monkeypatch.setattr(api, "list_minhas_solicitacoes", lento("lista", [dict(x) for x in LINHAS]))
    # catálogos com conteúdo: o vazio não fica guardado (20/10/2026) e seria lido de novo
    monkeypatch.setattr(api, "get_responsaveis", lento("pessoas", [{"id": 1, "name": "Ana Teste Silva"}]))
    monkeypatch.setattr(api, "get_labels", lento("etiquetas", [{"id": 7, "description": "Etiqueta Teste"}]))
    monkeypatch.setattr(api, "get_tipos_classif", lento("tipos", {"tipos": [{"id": 1, "description": "Corretiva"}]}))
    monkeypatch.setattr(api, "status_solicitacao_catalogo", lento("status", list(api.STATUS_SOLICITACAO)))
    t0 = time.perf_counter()
    assert cli.get("/os/solicitacao/fila").status_code == 200
    fria = time.perf_counter() - t0
    t0 = time.perf_counter()
    assert cli.get("/os/solicitacao/fila").status_code == 200
    quente = time.perf_counter() - t0
    assert fria < 1.0 and quente < 0.3, (fria, quente)


def test_catalogo_vencido_nao_segura_a_pagina_e_renova_por_tras(cli, monkeypatch, tmp_path):
    """O catálogo de ativos de ontem dá nome às solicitações NA HORA; o download dos ~22 mil ativos vai para uma thread."""
    vencido = tmp_path / "vencido.json"
    vencido.write_text(json.dumps({"ts": time.time() - 2 * api.ASSETS_TTL, "ver": api._CACHE_VER, "assets": ATIVOS}),
                       encoding="utf-8")
    monkeypatch.setattr(api, "ASSETS_CACHE", str(vencido))
    baixou = threading.Event()

    def baixar(force=False):          # o download de verdade leva minutos; aqui 1,5 s já denuncia quem esperar por ele
        assert force is True
        time.sleep(1.5)
        baixou.set()
        return ATIVOS
    monkeypatch.setattr(api, "load_assets_cached", baixar)
    t0 = time.perf_counter()
    h = cli.get("/os/solicitacao/fila").get_data(as_text=True)
    assert time.perf_counter() - t0 < 1.0
    assert api._code_loc["TST-INV11"] == ("Cliente X", api._usina_curta(USINA), "Inversor")
    assert _dados(h, "fl_dados")["fichas"][0]["tipo_ativo"] == "Inversor"
    assert baixou.wait(5), "o catálogo vencido não foi renovado por trás"
    rs._RENOVANDO.acquire(timeout=5)
    rs._RENOVANDO.release()


# ── Painel ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_painel_tres_colunas_como_no_app(cli):
    h = cli.get("/os/solicitacao/painel").get_data(as_text=True)
    cols = {c: h.split('data-col="%s"' % c, 1)[1].split("</section>", 1)[0] for c in ("pendente", "andamento", "finalizada")}
    assert [len(re.findall(r'class="spc-card(?: spc-escondido)?"', cols[c])) for c in ("pendente", "andamento", "finalizada")]         == [2, 1, 1]
    # a devolvida fica fora do quadro e só conta em cima
    assert "· 1 devolvidas para refazer, fora do quadro" in h and "Nº 5003" not in h
    # o cartão abre a Fila nele: Analisar nas pendentes, Ver detalhes nas outras
    assert 'href="/os/solicitacao/fila?sel=5001"' in cols["pendente"] and "Analisar" in cols["pendente"]
    assert "Ver detalhes" in cols["andamento"] and "OS 777" in cols["andamento"]
    assert "Inversor — inspeção e medição" in cols["pendente"]               # a linha do tema
    assert 'class="spc-pill" style="color:#F0B341"' in cols["pendente"]      # a cor do status é a do Fracttal


def test_painel_mostra_no_maximo_40_por_coluna(cli, monkeypatch):
    muitas = [_linha(6000 + i) for i in range(45)]
    monkeypatch.setattr(api, "list_minhas_solicitacoes", lambda *a, **k: [dict(x) for x in muitas])
    h = cli.get("/os/solicitacao/painel").get_data(as_text=True)
    col = h.split('data-col="pendente"', 1)[1].split("</section>", 1)[0]
    assert col.count('class="spc-card"') == 40 and col.count('class="spc-card spc-escondido"') == 5
    assert '<span class="spc-col-n" data-n>45</span>' in col


# ── Fila do PCM ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_fila_so_com_as_pendentes_e_a_ficha_lida(cli):
    d = _dados(cli.get("/os/solicitacao/fila").get_data(as_text=True), "fl_dados")
    assert [f["id"] for f in d["fichas"]] == [5001, 5005] and d["leitura"] == ""
    f = d["fichas"][0]
    assert f["titulo"] == sp.titulo("Usina Teste 1", "Inversor 1.1 Marca Teste", "inversor_inspecao")
    assert f["titulo_orig"] == "Pedido 5001 inteiro" and f["tema"] == "inversor_inspecao"
    assert f["relato"] == "Inversor desligando à tarde." and f["bloco"].startswith(sp.MARCADOR)
    assert (f["tecnico"], f["data_sug"], f["data_sug_iso"]) == ("Ana Teste Silva", "15/10/2026", "2026-10-15T08:00")
    assert f["subs"] == [{"tipo": "texto", "desc": "Medir isolação", "anexo": True},
                         {"tipo": "simnao", "desc": "Religou?", "anexo": False}] and f["subs_do_bloco"]
    assert f["ativo_ok"] and f["tipo_ativo"] == "Inversor"
    # sem o ativo no catálogo: a ficha avisa, e a aprovação não acontece
    assert d["fichas"][1]["ativo_ok"] is False
    # o responsável é o id_personnel; quem não tem id não entra
    assert d["pessoas"] == [{"id": 1, "nome": "Ana Teste Silva"}, {"id": 2, "nome": "Bruno Souza"}]   # pelo nome
    assert [s["cod"] for s in d["status"]] == [c for _i, c, _r in api.STATUS_SOLICITACAO
                                               if c not in ("OPEN_STATUS", "REQUEST_TODO")]
    tema = next(t for t in d["temas"] if t["chave"] == "inversor_inspecao")
    assert tema["disciplina"] == sp.classificacao("inversor_inspecao")["tipo"] and tema["motivo"]
    assert next(t for t in d["temas"] if t["chave"].startswith("tracker"))["perf_tema"] is True
    assert (d["tipo_padrao"], d["classif1_padrao"], d["nenhuma"]) == ("Corretiva", "Programada", "— nenhuma —")


def test_fila_aberta_numa_de_outra_coluna_e_so_para_ler(cli):
    d = _dados(cli.get("/os/solicitacao/fila?sel=5002").get_data(as_text=True), "fl_dados")
    assert [f["id"] for f in d["fichas"]] == [5001, 5005, 5002] and d["leitura"] == "5002" and d["sel"] == "5002"
    assert d["fichas"][2]["os_folio"] == 777
    assert d["n_hoje"] == sum(sw.de_hoje(x["data"]) for x in LINHAS if x["id_code"] in (5001, 5005))
    # nº que não existe: abre na primeira, sem inventar
    d = _dados(cli.get("/os/solicitacao/fila?sel=999").get_data(as_text=True), "fl_dados")
    assert d["sel"] == "" and d["leitura"] == ""


def test_aprovar_leva_o_que_esta_na_ficha_com_o_anexo(cli):
    corpo = {"id_responsible": 1, "responsavel": "Ana Teste Silva", "titulo": "[Usina Teste 1][Inversor 1.1] - Medir",
             "subtarefas": [{"desc": "Medir isolação", "tipo": "texto", "anexo": True}, {"desc": "  ", "tipo": "texto"}],
             "tipo": "Corretiva", "classif1": "Programada", "classif2": "", "etiquetas": [7], "id_parent": 880001}
    r = cli.post("/os/api/solic/5001/aprovar", json=corpo)
    assert r.status_code == 200 and r.get_json()["folio"] == 4321
    _, code, titulo, subs, idc, idr, nome, k = cli.gravado[-1]
    assert (code, titulo, idc, idr, nome) == ("TST-INV11", corpo["titulo"], 5001, 1, "Ana Teste Silva")
    assert [(s["description"], s["attachments_required"]) for s in subs] == [("Medir isolação", True)]
    assert k["classif"] == ("Programada", "") and k["etiqueta_ids"] == [7] and k["id_parent"] == 880001
    assert k["tipo"] == "Corretiva" and k["note"] == OBS
    # a OS nasce programada na data sugerida da solicitação (15/10/2026; o bloco diz só "15/10/2026": 08:00, como o app)
    import datetime as _dt
    assert k["prog_date"] == _dt.datetime(2026, 10, 15, 8, 0, tzinfo=_dt.timezone(_dt.timedelta(hours=-3)))
    assert r.get_json()["programada"] == "15/10/2026 08:00"
    # a ficha que esvaziou a lista leva a BASE, como o app; sem a chave, as do tema
    cli.post("/os/api/solic/5001/aprovar", json=dict(corpo, subtarefas=[]))
    assert len(cli.gravado[-1][3]) == len(sp.subtarefas_base())
    cli.post("/os/api/solic/5001/aprovar", json={"id_responsible": 1})
    assert cli.gravado[-1][3] == sw.subtarefas_do_tema("inversor_inspecao", "Inversor")


def test_aprovar_recusa_sem_responsavel_sem_ativo_e_com_os_pai_ruim(cli):
    assert cli.post("/os/api/solic/5001/aprovar", json={"titulo": "x"}).status_code == 400
    assert "ativo" in cli.post("/os/api/solic/5005/aprovar", json={"id_responsible": 1}).get_json()["erro"]
    r = cli.post("/os/api/solic/5001/aprovar", json={"id_responsible": 1, "id_parent": "12a"})
    assert r.status_code == 400 and "OS pai" in r.get_json()["erro"]
    assert not [g for g in cli.gravado if g[0] == "aprovar"]


def test_status_e_devolver_pedem_o_motivo(cli):
    assert cli.post("/os/api/solic/5001/status", json={"codigo": "AGAIN_REQUEST_TODO"}).status_code == 400
    assert cli.post("/os/api/solic/5001/status", json={"codigo": "XYZ", "motivo": "m"}).status_code == 400
    r = cli.post("/os/api/solic/5001/status", json={"codigo": "AGAIN_REQUEST_TODO", "motivo": "faltou a foto"})
    assert r.status_code == 200 and r.get_json()["status"] == "Reaberta (refazer)"
    assert cli.gravado[-1] == ("status", "5001", 10, "AGAIN_REQUEST_TODO", "faltou a foto")


def test_observacao_volta_com_o_bloco_e_a_linha_em_branco(cli):
    assert cli.post("/os/api/solic/5001/observacao", json={"relato": " Relato novo "}).status_code == 200
    _, idc, inteiro = cli.gravado[-1]
    assert inteiro == "Relato novo\n\n" + sp.so_bloco(OBS)
    assert sp.parse(inteiro)["tema"] == "inversor_inspecao" and sp.relato(inteiro) == "Relato novo"
    cli.post("/os/api/solic/5002/observacao", json={"relato": "Sem bloco"})
    assert cli.gravado[-1][2] == "Sem bloco"


def test_o_js_da_fila_tem_a_mesma_regua_de_coluna(cli):
    """A Fila tira da lista a que saiu dela depois de mudar o status; a régua do JS é a do `coluna_de`."""
    js = (WEB / "static" / "solic_fila.js").read_text(encoding="utf-8")
    for trecho in ("st.indexOf('cancelada') >= 0 || st.indexOf('rejeitada') >= 0) return 'finalizada'",
                   "st.indexOf('reaberta') >= 0 && !f.id_work_order) return 'fora'", "if (!f.id_work_order) return 'pendente'",
                   "(st.indexOf('conclu') >= 0 || st.indexOf('resolvid') >= 0) ? 'finalizada' : 'andamento'"):
        assert trecho in js, trecho
    for s, esperado in (("Cancelada", "finalizada"), ("Rejeitada", "finalizada"), ("Reaberta (refazer)", "fora"),
                        ("Aberta", "pendente"), ("Resolvida sem OS", "pendente")):
        assert sw.coluna_de({"status": s}) == esperado


# ── Histórico ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_historico_com_as_linhas_do_app(cli):
    h = cli.get("/os/solicitacao/historico?busca=5002").get_data(as_text=True)
    linhas = _dados(h, "hs_dados")["linhas"]
    assert [l["id"] for l in linhas] == [5001, 5002, 5003, 5004, 5005]     # inclusive a devolvida, que o painel esconde
    a = linhas[0]
    assert (a["data"], a["dia"], a["cor"], a["cancelavel"]) == ("13/10/2026 08:00", "2026-10-13", "#F5A623", True)
    assert linhas[3]["cancelavel"] is False and linhas[1]["os_folio"] == 777 and linhas[1]["id_work_order"] == 14002
    assert 'value="5002"' in h                                              # a busca que veio no endereço
    for rot in ("Criado por", "Buscar solicitação pelo nº — ignora filtros", "Atualiza a cada 15 min", "Exportar",
                "Limpar filtros", "Todos os clientes", "Todas as usinas", "Todos os tipos", "Todos os status", "Período",
                "ANEXOS DA SOLICITAÇÃO", "Cancelar solicitação", "Abrir OS ligada", "OS LIGADA"):
        assert rot in h, rot
    j = cli.get("/os/api/solic/historico").get_json()                       # o ↻ e os 15 min: força a lista de novo
    assert len(j["linhas"]) == 5 and cli.chamadas.count("lista") == 2


def test_anexos_e_cancelar_da_ficha(cli):
    j = cli.get("/os/api/solic/5001/anexos").get_json()
    assert j == {"anexos": [{"nome": "foto.jpg", "url": "https://exemplo.invalid/f.jpg", "imagem": True},
                            {"nome": "laudo.pdf", "url": "", "imagem": False}]}
    r = cli.post("/os/api/solic/5001/cancelar", json={"nota": " pedido em duplicidade "})
    assert r.status_code == 200 and cli.gravado[-1] == ("cancelar", "5001", "pedido em duplicidade")


def test_buscar_pelo_numero_fora_da_lista(cli):
    j = cli.get("/os/api/solic/5002").get_json()
    assert j["id_code"] == 5002 and j["os_folio"] == 777 and j["cancelavel"] is True and j["ativo_ok"] is True
    assert cli.get("/os/api/solic/999").status_code == 404


# ── Temas ───────────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def banco(monkeypatch):
    """O livro dos temas num dicionário: ler devolve o que está nele, salvar grava nele (nunca o banco de verdade)."""
    loja = {t["chave"]: dict(t, solicitacoes=t.get("solicitacoes", 0)) for t in ts.da_semente()[:3]}
    loja["inversor_inspecao"]["etiquetas"] = ["PERFORMANCE"]
    monkeypatch.setattr(ts, "do_banco", lambda buscar=None: [dict(v) for v in loja.values()])
    monkeypatch.setattr(ts, "pode_gravar", lambda: True)

    def salvar(tema, enviar=None):
        loja[tema["chave"]] = dict(tema)
        return {}
    monkeypatch.setattr(ts, "salvar", salvar)

    def arquivar(chave, on=True, **kw):
        if chave not in loja:
            raise KeyError(chave)
        loja[chave]["arquivado"] = bool(on)
        return {}
    monkeypatch.setattr(ts, "arquivar", arquivar)
    aplicados = []
    monkeypatch.setattr(ts, "aplicar_no_spec", lambda itens=None: aplicados.append(itens) or True)
    return loja, aplicados


def test_temas_lista_o_banco_com_as_etiquetas_efetivas(cli, banco):
    h = cli.get("/os/solicitacao/temas").get_data(as_text=True)
    d = _dados(h, "tm_dados")
    assert [t["chave"] for t in d["temas"]] == list(banco[0])
    assert next(t for t in d["temas"] if t["chave"] == "inversor_inspecao")["etiquetas"] == ["PERFORMANCE"]
    # tema que nunca foi salvo pela tela nova: a regra antiga da PERFORMANCE aparece (e quem salvar a leva)
    trk = next((t for t in d["temas"] if t["chave"].startswith("tracker")), None)
    if trk:
        assert trk["etiquetas"] == ["PERFORMANCE"]
    assert d["tipos"] == [["Inversor", 1], ["Estrutura Trackers", 1]] and d["pode_gravar"] is True
    assert d["tipos_os"] == ["", "Elétrica", "Mecânica", "Civil", "Preditiva", "Outros"] and d["etiquetas"] == ["GARANTIA", "PERFORMANCE"]
    for rot in ("+ novo tema", "Buscar tema…", "Nome do tema", "Tipo de equipamento", "Tipo de OS",
                "Motivo (vira o título da OS)", "Classificação 1", "Etiquetas que a OS vai levar", "Salvar tema",
                "Descartar alterações", "Arquivar"):
        assert rot in h, rot


def test_temas_com_o_banco_fora_mostra_os_do_app_e_avisa(cli, monkeypatch):
    def fora(buscar=None):
        raise ConnectionError("sem rede")
    monkeypatch.setattr(ts, "do_banco", fora)
    h = cli.get("/os/solicitacao/temas").get_data(as_text=True)
    assert "Erro ao carregar do banco" in h and len(_dados(h, "tm_dados")["temas"]) == len(ts.da_semente())


def test_salvar_tema_novo_e_editar_sem_trocar_a_chave(cli, banco):
    loja, aplicados = banco
    r = cli.post("/os/api/solic/temas/salvar", json={"nome": "Câmera — limpeza das lentes", "motivo": "Limpar câmera",
                                                     "tipo_os": "Outros", "tipo_equipamento": "Inversor",
                                                     "subtarefas": [{"desc": "Limpar", "tipo": "texto", "anexo": True},
                                                                    {"desc": "", "tipo": "texto"}],
                                                     "etiquetas": ["GARANTIA", "garantia", ""]})
    assert r.status_code == 200, r.get_json()
    novo = loja["camera_limpeza_das_lentes"]
    assert (novo["nome"], novo["solicitacoes"], novo["arquivado"]) == ("Câmera — limpeza das lentes", 0, False)
    assert novo["subtarefas"] == [{"desc": "Limpar", "tipo": "texto", "anexo": True}] and novo["etiquetas"] == ["GARANTIA"]
    assert aplicados and r.get_json()["chave"] == "camera_limpeza_das_lentes"
    assert any(t["chave"] == "camera_limpeza_das_lentes" for t in r.get_json()["temas"])
    # nome repetido não entra; renomear um que existe mantém a chave e as solicitações
    assert cli.post("/os/api/solic/temas/salvar", json={"nome": "Câmera: limpeza das lentes"}).status_code == 400
    chave = next(iter(loja))
    usos = loja[chave]["solicitacoes"]
    assert cli.post("/os/api/solic/temas/salvar", json={"chave": chave, "nome": "Nome novo", "solicitacoes": 0}).status_code == 200
    assert loja[chave]["nome"] == "Nome novo" and loja[chave]["solicitacoes"] == usos
    assert cli.post("/os/api/solic/temas/salvar", json={"nome": "  "}).get_json()["erro"] == "O tema precisa de um nome."


def test_salvar_sem_token_e_arquivar(cli, banco, monkeypatch):
    loja, _ = banco

    def sem_token(tema, enviar=None):
        raise PermissionError("Sem o GRIDCO_SQL_TOKEN nesta máquina")
    monkeypatch.setattr(ts, "salvar", sem_token)
    r = cli.post("/os/api/solic/temas/salvar", json={"nome": "Outro tema"})
    assert r.status_code == 403 and "GRIDCO_SQL_TOKEN" in r.get_json()["erro"]
    chave = next(iter(loja))
    assert cli.post("/os/api/solic/temas/%s/arquivar" % chave, json={"arquivar": True}).status_code == 200
    assert loja[chave]["arquivado"] is True
    assert cli.post("/os/api/solic/temas/%s/arquivar" % chave, json={"arquivar": False}).get_json()["mensagem"] == "desarquivado"
    assert cli.post("/os/api/solic/temas/nao_existe/arquivar", json={}).status_code == 404


# ── as regras puras ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_datas_em_brasilia_e_o_ha_quanto_do_app():
    import datetime as dt
    agora = dt.datetime(2026, 10, 13, 15, 0, tzinfo=dt.timezone.utc)
    assert sw.data_br("2026-10-13T11:20:03") == "13/10/2026 08:20" and sw.data_br("") == "—"
    assert [sw.ha_quanto(x, agora) for x in ("2026-10-13T14:30:00", "2026-10-13T10:00:00", "2026-10-12T10:00:00",
                                             "2026-10-10T10:00:00", "2026-09-01T10:00:00")] == \
        ["agora", "há 5 h", "ontem", "há 3 dias", "01/09"]
    assert sw.de_hoje("2026-10-13T04:00:00", agora) and not sw.de_hoje("2026-10-13T02:00:00", agora)   # 23 h de ontem em Brasília


def test_chave_do_tema_e_subtarefas_com_anexo():
    assert sw.chave_de("Inversor — Inspeção & medição!") == "inversor_inspecao_medicao"
    assert sw.chave_de("x" * 60) == "x" * 48 and sw.chave_de("—") == ""
    api_ = sw.subs_para_api([{"desc": "Foto", "tipo": "texto", "anexo": True}, {"desc": "Sim?", "tipo": "simnao"}, {"desc": ""}])
    assert [(s["description"], s["attachments_required"], s["is_required"]) for s in api_] == [("Foto", True, True),
                                                                                              ("Sim?", False, True)]
    assert api_[1]["id_task_form_item_type"] == sp.TIPO_ID["simnao"]


def test_o_css_novo_entra_nas_paginas_e_o_js_existe():
    for t in ("solic_painel", "solic_fila", "solic_hist", "solic_temas"):
        h = (WEB / "templates" / f"{t}.html").read_text(encoding="utf-8")
        assert '<link rel="stylesheet" href="/os/static/solic_pcm.css">' in h and '{% include "_solic_nav.html" %}' in h, t
    for js in ("solic_pcm.js", "solic_fila.js", "solic_hist.js", "solic_temas.js"):
        assert (WEB / "static" / js).exists(), js


# ── a Área PCM: só o setor PCM ou administrador (Levi, 13/10/2026) ──────────────────────────────────────────────────
# "Só o setor PCM ou administrador! Quem não é nenhum dos dois recebe a notificação!" O Nexus decide (`ponte.area_pcm`) e
# põe a decisão no pedido; o clone mostra o aviso no lugar da Fila e dos Temas e recusa as gravações deles.
NEGA = {"pode": False, "aviso": "A Fila do PCM e os Temas são do setor PCM. Você está no setor Engenharia."}


def test_fora_da_area_pcm_a_fila_e_os_temas_dao_o_aviso(cli):
    for url, titulo in (("/os/solicitacao/fila", "Fila do PCM"), ("/os/solicitacao/fila?sel=5002", "Fila do PCM"),
                        ("/os/solicitacao/temas", "Temas"), ("/os/solicitacao/atualizar", "Fila do PCM")):
        r = cli.get(url, environ_overrides={rs.AREA_PCM: NEGA})
        h = r.get_data(as_text=True)
        assert r.status_code == 403 and NEGA["aviso"] in h and "%s: só para a área do PCM" % titulo in h, url
        assert 'class="on" aria-current="page">%s</a>' % titulo in h and 'role="alert"' in h        # a barra fica
        assert 'href="/os/solicitacao/painel">Painel</a> e o' in h                                  # e o caminho de volta
    assert cli.chamadas == []                                   # nem chega a pedir a lista ou os catálogos ao Fracttal


def test_fora_da_area_pcm_as_gravacoes_voltam_403_e_nada_grava(cli, banco):
    loja, aplicados = banco
    antes = {k: dict(v) for k, v in loja.items()}
    chave = next(iter(loja))
    for url, corpo in (("/os/api/solic/5001/aprovar", {"id_responsible": 1, "titulo": "T", "subtarefas": []}),
                       ("/os/api/solic/5001/status", {"codigo": "REJECTED", "motivo": "m"}),
                       ("/os/api/solic/5001/observacao", {"relato": "novo"}),
                       ("/os/api/solic/temas/salvar", {"nome": "Tema de quem não pode"}),
                       ("/os/api/solic/temas/%s/arquivar" % chave, {"arquivar": True})):
        r = cli.post(url, json=corpo, environ_overrides={rs.AREA_PCM: NEGA})
        assert r.status_code == 403 and r.get_json() == {"erro": NEGA["aviso"], "area_pcm": False}, url
    assert cli.gravado == [] and loja == antes and aplicados == []


def test_fora_da_area_pcm_o_painel_e_o_historico_seguem(cli):
    """O Painel, o Histórico e a Nova solicitação são a Área do Solicitante do app: abertos. O cartão do Painel abre a
    ficha da solicitação no Histórico (`?ficha=`), e não a Fila; cancelar a própria solicitação continua."""
    h = cli.get("/os/solicitacao/painel", environ_overrides={rs.AREA_PCM: NEGA}).get_data(as_text=True)
    assert 'href="/os/solicitacao/historico?ficha=5001"' in h and "fila?sel=" not in h and ">Analisar<" not in h
    assert cli.get("/os/solicitacao/historico?ficha=5001", environ_overrides={rs.AREA_PCM: NEGA}).status_code == 200
    assert cli.post("/os/api/solic/5001/cancelar", json={"nota": ""}, environ_overrides={rs.AREA_PCM: NEGA}).status_code == 200
    js = (WEB / "static" / "solic_hist.js").read_text(encoding="utf-8")
    assert "new URLSearchParams(location.search).get('ficha')" in js
    # liberada, ou sem ninguém para decidir (o OS Creator sozinho, o 5090): como antes
    for extra in ({rs.AREA_PCM: {"pode": True, "aviso": ""}}, {}):
        h = cli.get("/os/solicitacao/painel?atualizar=1", environ_overrides=extra).get_data(as_text=True)
        assert 'href="/os/solicitacao/fila?sel=5001"' in h and ">Analisar<" in h
        assert cli.get("/os/solicitacao/fila", environ_overrides=extra).status_code == 200


@pytest.fixture
def setor_de_mentira(app, monkeypatch):
    """O setor da pessoa do login sem ir ao banco: `valor` é o que o cadastro devolveria (ou a exceção da leitura)."""
    from nexus.auth import setor_telas
    app.config["NEXUS_PESSOA_HMAC"] = "chave-de-teste"
    monkeypatch.setattr(setor_telas, "_banco", lambda: (None, None))
    caixa = {"valor": None, "lidos": []}

    def da_pessoa(cfg, email, base, sessao):
        caixa["lidos"].append(email)
        if isinstance(caixa["valor"], Exception):
            raise caixa["valor"]
        return caixa["valor"]
    monkeypatch.setattr(setor_telas, "setor_da_pessoa", da_pessoa)
    return caixa


def test_a_regra_do_nexus_setor_pcm_ou_administrador(app, setor_de_mentira):
    from flask import session
    with app.test_request_context("/os/solicitacao/fila"):
        session["logado"], session["admin"] = True, True
        assert ponte.area_pcm() == {"pode": True, "aviso": ""} and setor_de_mentira["lidos"] == []   # nem lê o setor
        session["admin"] = False
        session["usuario"] = {"email": "Pessoa.Teste@exemplo.test", "nome": "Pessoa Teste", "perfil": ""}
        for nome in ("PCM", "pcm", " Pcm "):
            setor_de_mentira["valor"] = {"id": 9, "nome": nome}
            assert ponte.area_pcm() == {"pode": True, "aviso": ""}, nome
        assert setor_de_mentira["lidos"][-1] == "pessoa.teste@exemplo.test"
        setor_de_mentira["valor"] = {"id": 2, "nome": "Performance"}
        a = ponte.area_pcm()
        assert a["pode"] is False and "Você está no setor Performance." in a["aviso"]
        assert "setor PCM e dos administradores" in a["aviso"] and "Base → Integração Fracttal" in a["aviso"]
        setor_de_mentira["valor"] = None
        assert "Você está sem setor no Nexus." in ponte.area_pcm()["aviso"]
        setor_de_mentira["valor"] = RuntimeError("setores ilegíveis no banco")
        a = ponte.area_pcm()
        assert a["pode"] is False and "Não consegui ler o seu setor agora" in a["aviso"]
        app.config["NEXUS_PESSOA_HMAC"] = ""
        a = ponte.area_pcm()
        assert a["pode"] is False and "NEXUS_PESSOA_HMAC" in a["aviso"]


def _sessao_do_fracttal(app, c, email="pessoa.teste@exemplo.test"):
    """Um login do Nexus pelo Fracttal (não administrador) e o cookie do OS Creator com o JWT de mentira."""
    with c.session_transaction() as s:
        s["logado"], s["admin"] = True, False
        s["usuario"] = {"email": email, "nome": "Pessoa Teste", "perfil": ""}
    clone = ponte.clone(app)
    valor = clone.session_interface.get_signing_serializer(clone).dumps(
        {"jwt": JWT, "conta": {"nome": "Pessoa Teste", "email": email, "perfil": ""}})
    c.set_cookie("os_sessao", valor, path="/os")


def test_pela_ponte_quem_nao_e_do_pcm_recebe_o_aviso(app, cli, setor_de_mentira):
    """De ponta a ponta no Nexus: a sessão do Fracttal de quem é da Engenharia leva o aviso na Fila e o 403 ao aprovar;
    a do PCM passa. (O `cli` só põe os dublês do Fracttal no lugar.)"""
    c = app.test_client()
    _sessao_do_fracttal(app, c)
    setor_de_mentira["valor"] = {"id": 1, "nome": "Engenharia"}
    r = c.get("/os/solicitacao/fila")
    h = r.get_data(as_text=True)
    assert r.status_code == 403 and "Você está no setor Engenharia." in h and "Fila do PCM: só para a área do PCM" in h
    r = c.post("/os/api/solic/5001/aprovar", json={"id_responsible": 1, "titulo": "T", "subtarefas": []})
    assert r.status_code == 403 and "setor PCM" in r.get_json()["erro"] and cli.gravado == []
    assert c.get("/os/solicitacao/painel").status_code == 200 and c.get("/os/solicitacao/historico").status_code == 200
    setor_de_mentira["valor"] = {"id": 9, "nome": "PCM"}
    r = c.get("/os/solicitacao/fila")
    assert r.status_code == 200 and 'id="fl_dados"' in r.get_data(as_text=True)
    r = c.post("/os/api/solic/5001/aprovar", json={"id_responsible": 1, "titulo": "T", "subtarefas": []})
    assert r.status_code == 200 and cli.gravado[-1][0] == "aprovar"


def test_a_data_sugerida_vira_a_data_programada_da_os(monkeypatch):
    """15/10/2026, Levi: "No OS Creator em fila a OS programada do PCM tem que ser a data sugerida da solicitação!": a
    leitura da data (com hora, só o dia = 08:00, ilegível = nenhuma) e o caminho até o Fracttal (clonar_os manda a data
    PROGRAMADA ao create_os_rpc; o evento segue sendo agora)."""
    import datetime as _dt
    brt = _dt.timezone(_dt.timedelta(hours=-3))
    assert sw.data_sugerida_dt("16/10/2026 14:30") == _dt.datetime(2026, 10, 16, 14, 30, tzinfo=brt)
    assert sw.data_sugerida_dt("16/10/2026") == _dt.datetime(2026, 10, 16, 8, 0, tzinfo=brt)
    assert sw.data_sugerida_dt("") is None and sw.data_sugerida_dt("amanhã") is None
    chamadas = []

    def criar(asset, desc, task_type, subs, **k):
        chamadas.append(k)
        return {"id_task": 501}
    monkeypatch.setattr(api, "create_os_rpc", criar)
    monkeypatch.setattr(api, "_classif_ids", lambda *a: {})
    monkeypatch.setattr(api, "_solicitacao_row", lambda idc: {})
    monkeypatch.setattr(api, "_tarefa_da_solicitacao", lambda idc: None)
    monkeypatch.setattr(api, "_work_order_insert", lambda recs, idr, nome: {"id_work_order": 9, "wo_folio": 1234})
    monkeypatch.setattr(api, "apply_labels", lambda *a: None)
    quando = _dt.datetime(2026, 10, 16, 8, 0, tzinfo=brt)
    api.aprovar_solicitacao({"id": 11, "code": "TST-INV11"}, "T", [], 5001, 1, "Ana", prog_date=quando)
    assert chamadas[-1]["prog_date"] == quando and chamadas[-1]["event_date"] is None
    api.aprovar_solicitacao({"id": 11, "code": "TST-INV11"}, "T", [], 5001, 1, "Ana")       # sem data: como antes
    assert chamadas[-1]["prog_date"] is None


def test_a_data_sugerida_da_solicitacao_web_tambem_vale(monkeypatch):
    """19/10/2026, Levi: "A data sugerida que dão na solicitação tem que ser a data programada, a data programada tá
    sendo a data do evento" (SS 3944 → OS 16784: sugerida 21/10 08:00, programada 19/10 na hora da aprovação). A Nova
    solicitação do OS Creator web gravava "2026-10-21 08:00" (o valor do campo de data) e a leitura só entendia
    "21/10/2026 08:00" (o app): ficava sem data e a OS nascia programada agora, enquanto a confirmação mostrava o texto
    cru. A leitura entende os dois (as solicitações já na fila também); a Nova solicitação grava como o app."""
    import datetime as _dt
    brt = _dt.timezone(_dt.timedelta(hours=-3))
    alvo = _dt.datetime(2026, 10, 21, 8, 0, tzinfo=brt)
    for texto in ("2026-10-21 08:00", "2026-10-21T08:00", "21/10/2026 08:00", "2026-10-21", "21/10/2026"):
        assert sw.data_sugerida_dt(texto) == alvo, texto
        assert sw._data_sugerida_iso(texto) == "2026-10-21T08:00", texto
    assert sw.data_sugerida_dt("2026-13-40 08:00") is None
    # a Nova solicitação grava a data como o app ("21/10/2026 08:00"), legível na observação no Fracttal web
    obs = sw.observacao("Relato", tema="", tecnico="", data="2026-10-21 08:00")
    assert "Data sugerida: 21/10/2026 08:00" in obs and "2026-10-21" not in obs
    # a ficha manda à tela a data já lida, e a confirmação só promete a data que o servidor entendeu
    f = sw.ficha({"_data_sug": "2026-10-21 08:00", "_subs": []})
    assert f["data_sug_iso"] == "2026-10-21T08:00"
    js = (Path(sw.__file__).parent / "static" / "solic_fila.js").read_text(encoding="utf-8")
    assert "f.data_sug_iso" in js.split("var quando", 1)[1].split(";", 1)[0]



def test_o_pcm_troca_a_data_programada_na_decisao(cli):
    """20/10/2026, o programador do PCM: "não consigo alterar a data, o campo não abre mais". No app, o "Data:" da
    decisão é um campo que abre o calendário com a data sugerida, e o PCM troca; na web ele era só texto. A data do
    campo (o valor do <input type=datetime-local>) vai no pedido e vale no lugar da sugerida; vazia, a sugerida."""
    import datetime as _dt
    brt = _dt.timezone(_dt.timedelta(hours=-3))
    assert 'type="datetime-local" id="fl_data"' in cli.get("/os/solicitacao/fila").get_data(as_text=True)
    corpo = {"id_responsible": 1, "responsavel": "Ana Teste Silva"}
    r = cli.post("/os/api/solic/5001/aprovar", json=dict(corpo, data_programada="2026-10-22T13:30"))
    assert r.status_code == 200 and r.get_json()["programada"] == "22/10/2026 13:30"
    assert cli.gravado[-1][-1]["prog_date"] == _dt.datetime(2026, 10, 22, 13, 30, tzinfo=brt)
    cli.post("/os/api/solic/5001/aprovar", json=dict(corpo, data_programada=""))       # vazia: a sugerida
    assert cli.gravado[-1][-1]["prog_date"] == _dt.datetime(2026, 10, 15, 8, 0, tzinfo=brt)
    n = len(cli.gravado)
    for ruim in ("amanhã", "22/10/2026", "2026-13-40T08:00", "2031-10-22T08:00"):        # não é a do campo, ou longe
        r = cli.post("/os/api/solic/5001/aprovar", json=dict(corpo, data_programada=ruim))
        assert r.status_code == 400 and "Data" in r.get_json()["erro"], ruim
    assert len(cli.gravado) == n                                                            # nada foi criado


def test_o_pcm_troca_o_tempo_estimado_na_decisao(cli):
    """21/10/2026, Levi: "Gostaria que o PCM conseguisse mudar o tempo estimado para cada atividade na fila de PCM". A OS
    da Fila nascia sempre com 10 min (o `duration: 600` do `create_os_rpc`). O "Tempo estimado:" da decisão (HH:mm, como o
    tempo da linha na tela PCM) vai no pedido em segundos e vale na tarefa; sem ele (o PCM não mexeu), como antes."""
    html = cli.get("/os/solicitacao/fila").get_data(as_text=True)
    assert 'id="fl_tempo"' in html and _dados(html, "fl_dados")["tempo_padrao"] == 600
    corpo = {"id_responsible": 1, "responsavel": "Ana Teste Silva"}
    r = cli.post("/os/api/solic/5001/aprovar", json=dict(corpo, duracao=5400))
    assert r.status_code == 200 and cli.gravado[-1][-1]["duracao"] == 5400
    assert r.get_json()["tempo"] == "01:30"
    for sem in (dict(corpo, duracao=None), dict(corpo, duracao=""), corpo):                 # o PCM não mexeu
        cli.post("/os/api/solic/5001/aprovar", json=sem)
        assert cli.gravado[-1][-1]["duracao"] is None
    n = len(cli.gravado)
    for ruim in (0, 30, -600, 24 * 3600, "1:30", "abc", True, 5400.5):
        r = cli.post("/os/api/solic/5001/aprovar", json=dict(corpo, duracao=ruim))
        assert r.status_code == 400 and "Tempo estimado" in r.get_json()["erro"], ruim
    assert len(cli.gravado) == n                                                            # nada foi criado


def test_o_tempo_estimado_vai_na_tarefa_da_os(monkeypatch):
    """O caminho até o Fracttal: aprovar_solicitacao → clonar_os → create_os_rpc(duracao=). No pedido ao Fracttal, a
    duração e a janela da programação (o fim = o início + o tempo), como o `create_planned_os` da tela PCM (14/09); sem o
    tempo, o pedido de sempre (10 min, a janela de 20)."""
    import datetime as _dt
    chamadas = []

    def criar(asset, desc, task_type, subs, **k):
        chamadas.append(k)
        return {"id_task": 501}
    monkeypatch.setattr(api, "create_os_rpc", criar)
    monkeypatch.setattr(api, "_classif_ids", lambda *a: {})
    monkeypatch.setattr(api, "_solicitacao_row", lambda idc: {})
    monkeypatch.setattr(api, "_tarefa_da_solicitacao", lambda idc: None)
    monkeypatch.setattr(api, "_work_order_insert", lambda recs, idr, nome: {"id_work_order": 9, "wo_folio": 1234})
    monkeypatch.setattr(api, "apply_labels", lambda *a: None)
    api.aprovar_solicitacao({"id": 11, "code": "TST-INV11"}, "T", [], 5001, 1, "Ana", duracao=5400)
    assert chamadas[-1]["duracao"] == 5400
    api.aprovar_solicitacao({"id": 11, "code": "TST-INV11"}, "T", [], 5001, 1, "Ana")
    assert chamadas[-1]["duracao"] is None

    monkeypatch.undo()
    enviados = []

    class Resp:
        status_code, text = 200, ""

        def json(self):
            return [{"result": {"success": True, "data": {"id_task": 77}}}]
    monkeypatch.setattr(api, "_rpc_headers", lambda: {})
    monkeypatch.setattr(api.requests, "post", lambda url, headers=None, json=None, timeout=None:
                        enviados.append(json[0]["params"]) or Resp())
    prog = _dt.datetime(2026, 10, 22, 11, 0, tzinfo=_dt.timezone.utc)
    ativo = {"id": 11, "code": "TST-INV11", "id_type_item": 1}
    assert api.create_os_rpc(ativo, "T", "Corretiva", [], prog_date=prog, duracao=5400)["id_task"] == 77
    p = enviados[-1]
    assert p["duration"] == 5400 and p["initial_date"] == "2026-10-22T11:00:00.000Z"
    assert p["final_date"] == "2026-10-22T12:30:00.000Z"
    api.create_os_rpc(ativo, "T", "Corretiva", [], prog_date=prog)                         # sem o tempo: como sempre
    p = enviados[-1]
    assert p["duration"] == 600 and p["real_duration"] == 600 and p["final_date"] == "2026-10-22T11:20:00.000Z"


# ── Nova solicitação: o título é só o motivo, e a OS pai vai até a Fila (24/10/2026) ───────────────────────────────────
# Levi: "o título está com um subtexto de "[Ativo] - Motivo": O certo seria só motivo pois o ativo já tem que ir no
# título automático!" e "ao lado de buscar ativo deixe um espaço do lado direito para "OS Pai" quando preenchido e o PCM
# for criar a OS na fila do PCM já vai vincular aquela OS como OS pai!"
INV = {"code": "TST-INV15", "description": "Inversor 1.5 Marca X { TST-INV15 }", "tipo": "Inversor"}


@pytest.mark.parametrize("escrito,esperado", [
    ("Troca do cabo", "[Inversor 1.5] - Troca do cabo"),             # só o motivo: o ativo entra sozinho na frente
    ("  Troca do cabo  ", "[Inversor 1.5] - Troca do cabo"),
    ("[Ativo] - Troca do cabo", "[Inversor 1.5] - Troca do cabo"),   # o jeito de antes (uma tela aberta antes do deploy)
    ("[Inversor 1.5] - Troca do cabo", "[Inversor 1.5] - Troca do cabo"),   # já com o ativo: não repete
    ("[inversor 1.5] Troca", "[inversor 1.5] Troca"),
])
def test_o_titulo_e_o_motivo_com_o_ativo_na_frente(escrito, esperado):
    assert sw.titulo_do_ativo(escrito, INV) == esperado


def _criar(cli, monkeypatch, **corpo):
    ativos = [dict(INV), {"code": "TST-INV16", "description": "Inversor 1.6 Marca X", "tipo": "Inversor"}]
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: [dict(x) for x in ativos])
    monkeypatch.setattr(api, "_read_asset_cache", lambda: [dict(x) for x in ativos])
    feitas = []
    monkeypatch.setattr(api, "create_solicitacoes_bulk", lambda assets, desc, c1, **k: feitas.append(
        ([a["code"] for a in assets], desc, k.get("observation"))) or [{"code": a["code"], "ok": True, "id_code": 1}
                                                                       for a in assets])
    r = cli.post("/os/api/solic/criar", json=dict({"ativos": ["TST-INV15", "TST-INV16"], "descricao": "Troca de ventilador",
                                                    "classif1": 7, "observacao": "Parou de tarde."}, **corpo))
    return r, feitas


def test_criar_poe_o_nome_de_cada_ativo_no_titulo(cli, monkeypatch):
    r, feitas = _criar(cli, monkeypatch)
    assert r.status_code == 200
    assert [(c, d) for c, d, _o in feitas] == [(["TST-INV15"], "[Inversor 1.5] - Troca de ventilador"),
                                               (["TST-INV16"], "[Inversor 1.6] - Troca de ventilador")]


def test_a_os_pai_vai_no_bloco_pcm_de_cada_solicitacao(cli, monkeypatch):
    r, feitas = _criar(cli, monkeypatch, os_pai={"id": 555, "folio": "16784"})
    assert r.status_code == 200 and len(feitas) == 2
    for _c, _d, obs in feitas:
        assert obs.startswith("Parou de tarde.") and "OS pai: 16784 (id 555)" in sp.so_bloco(obs)
    _r, feitas = _criar(cli, monkeypatch, os_pai=None)                    # sem OS pai: o bloco de sempre
    assert all("OS pai" not in o for _c, _d, o in feitas)


@pytest.mark.parametrize("ruim", [{"id": "abc", "folio": "16784"}, {"id": 555, "folio": "x1"}, {"folio": "16784"},
                                  {"id": 0, "folio": "16784"}, {"id": True, "folio": "16784"}, "16784"])
def test_a_os_pai_torta_nao_cria_nada(cli, monkeypatch, ruim):
    r, feitas = _criar(cli, monkeypatch, os_pai=ruim)
    assert r.status_code == 400 and "OS pai" in r.get_json()["erro"] and feitas == []


def test_o_bloco_le_a_os_pai_de_volta():
    obs = sw.observacao("Relato.", "inversor_inspecao", "", "2026-10-25 08:00", [], os_pai=("16784", 555))
    assert sp.parse(obs)["os_pai"] == "16784 (id 555)" and sp.parse(obs)["data"] == "25/10/2026 08:00"
    assert sw.os_pai_do_bloco("16784 (id 555)") == ("16784", 555)
    assert sw.os_pai_do_bloco("16784") == ("16784", None)        # escrito à mão no Fracttal web: o PCM escolhe na lista
    assert sw.os_pai_do_bloco("") == ("", None) and sw.os_pai_do_bloco("veja a outra") == ("", None)


def test_a_fila_ja_traz_a_os_pai_da_solicitacao(cli, monkeypatch):
    obs = sw.observacao("Inversor desligando.", "", "", "", [], os_pai=("16784", 555))
    monkeypatch.setitem(LINHAS[0], "observacao", obs)
    d = _dados(cli.get("/os/solicitacao/fila").get_data(as_text=True), "fl_dados")
    f = next(x for x in d["fichas"] if x["id"] == 5001)
    assert f["os_pai"] == "16784" and f["os_pai_id"] == 555 and "OS pai" not in f["relato"]
    outra = next(x for x in d["fichas"] if x["id"] == 5005)
    assert outra["os_pai"] == "" and outra["os_pai_id"] is None
    r = cli.post("/os/api/solic/5001/aprovar", json={"id_responsible": 1, "responsavel": "Ana Teste Silva",
                                                     "id_parent": f["os_pai_id"]})
    assert r.status_code == 200 and cli.gravado[-1][-1]["id_parent"] == 555
    js = (WEB / "static" / "solic_fila.js").read_text(encoding="utf-8")
    assert "paiSel = f.os_pai_id || null" in js                       # a ficha abre com a OS pai escolhida


def test_a_tela_da_nova_solicitacao_pede_o_motivo_e_a_os_pai(cli, monkeypatch):
    monkeypatch.setattr(api, "get_request_types", lambda: {"classif1": [{"id": 7, "description": "Corretiva"}]})
    h = cli.get("/os/solicitacao").get_data(as_text=True)
    assert 'placeholder="Motivo"' in h and '"[Ativo] - "' not in h
    busca, pai = h.index('id="busca"'), h.index('id="ed_pai"')
    assert busca < pai < h.index('id="tbody"')                         # no bloco 1, à direita do Buscar ativo
    assert "/os/api/pcm/os-pai?termo=" in h and "os_pai:" in h


# ── a sugestão pelo endereço (24/10/2026): o "Solicitar OS" da OS do Quadro da equipe da Engenharia ──────────────────
def _sugestao(h):
    return dict(re.findall(r'data-sug-([a-z-]+)="([^"]*)"', h.split('id="sug"', 1)[1].split(">", 1)[0]))


def test_solicitacao_com_sugestao_traz_o_ativo_e_a_os_pai(cli, monkeypatch):
    # Levi: "um botão de 'Solicitar OS' que já vai preencher o ativo pelo o da OS original, a pessoa pode até mudar o
    # ativo mas sai como aquela OS como OS pai"
    monkeypatch.setattr(api, "get_request_types", lambda: {"classif1": [{"id": 7, "description": "Corretiva"}]})
    h = cli.get("/os/solicitacao?ativo=TST-INV11&os_pai=555&os_pai_folio=16784").get_data(as_text=True)
    assert _sugestao(h) == {"cliente": "Cliente X", "usina": USINA, "ativo": "TST-INV11", "os-pai": "555",
                            "os-pai-folio": "16784"}
    assert "sugerir()" in h                                               # a página aplica a sugestão ao abrir
    # o ativo que o catálogo não tem fica de fora; a OS pai torta também (o criar recusa a torta de qualquer jeito)
    h = cli.get("/os/solicitacao?ativo=NAO-EXISTE&os_pai=abc&os_pai_folio=16784").get_data(as_text=True)
    assert _sugestao(h) == {"cliente": "", "usina": "", "ativo": "", "os-pai": "", "os-pai-folio": ""}


def test_solicitacao_sem_sugestao_segue_igual(cli, monkeypatch):
    monkeypatch.setattr(api, "get_request_types", lambda: {"classif1": [{"id": 7, "description": "Corretiva"}]})
    h = cli.get("/os/solicitacao").get_data(as_text=True)
    assert _sugestao(h) == {"cliente": "", "usina": "", "ativo": "", "os-pai": "", "os-pai-folio": ""}



def test_solicitacao_com_a_data_do_incidente_da_os_pai(cli, monkeypatch):
    # Levi, 24/10/2026: "Ao clicar em criar Solicitar OS a data do incidente deve ser a mesma da OS pai"
    monkeypatch.setattr(api, "get_request_types", lambda: {"classif1": [{"id": 7, "description": "Corretiva"}]})
    h = cli.get("/os/solicitacao?ativo=TST-INV11&os_pai=555&os_pai_folio=16784&data=2026-10-08T06:00").get_data(as_text=True)
    assert 'id="dt_inc" value="2026-10-08T06:00"' in h
    # data torta ou no futuro fica de fora: o campo começa em agora, como sempre
    for ruim in ("amanha", "2999-01-01T00:00"):
        h = cli.get("/os/solicitacao?data=" + ruim).get_data(as_text=True)
        assert 'id="dt_inc" value="' + ruim not in h
