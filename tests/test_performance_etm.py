"""As ETMs na Performance (24/11/2026, Levi: "a parte de ETM agora vem para performance [...] Não está salvando na tela as
ETMs que carregaram. Então, toda vez que sai e volta, lê o fractal tudo de novo e dá uma recusa de leitura do fractal [...]
Eu queria que sempre começasse com estações em aberto, e aí a gente consiga também até comentar nas ETMs daquela usina"; e
"clima e risco vai para usinas 360. Mapa de risco pode tirar"). A cópia em disco, a OS relida sozinha, os endereços antigos,
o menu e o chat da usina nas Estações em Aberto. Fracttal falso; nomes de mentira (repositório público)."""
import gzip
import json
import time

import pytest

from nexus.cadastro import setor_ids as SID
from nexus.engenharia import etm as E

from test_engenharia_etm import SET, U, w

SAME = {"Sec-Fetch-Site": "same-origin"}


@pytest.fixture
def disco(app, tmp_path, monkeypatch):
    """O Fracttal falso das ETMs (uma ETM, as OS 1 e 3) e a pasta de dados num diretório do teste."""
    app.config["NEXUS_DADOS"] = str(tmp_path)
    pedidos = []

    def ler(path):
        pedidos.append(path)
        if path.startswith("items?field_1="):
            return {"data": [{"code": "ALF100-ESTM1", "description": "Estação Meteorológica Alfa", "groups_1_description": U}]}
        if path.startswith("work_orders?items_log_description="):
            return {"data": [w(1, "Corretiva"), w(3, "Corretiva")]}
        raise AssertionError(f"a tela não lê {path}")
    monkeypatch.setattr(E, "_ler_fracttal", ler)
    monkeypatch.setattr(E, "_setores", lambda app: (SET, ""))
    E.limpar()
    yield pedidos
    E.limpar()


def _arquivo(tmp_path):
    return tmp_path / "performance" / "etm.json.gz"


def test_a_leitura_vai_para_o_disco_e_o_reinicio_le_o_disco_sem_pedir_nada(app, disco, tmp_path):
    with app.app_context():
        E.pedir_releitura(app, esperar=True)
    assert len(disco) == 2 and _arquivo(tmp_path).exists()
    d = json.loads(gzip.decompress(_arquivo(tmp_path).read_bytes()))
    assert d["formato"] == E.FORMATO and [o["os"] for o in d["os"]] == ["1", "3"] and d["etms"] == {"ALF100-ESTM1": U}
    ts = d["ts"]
    E.limpar()                                  # o reinício do deploy: a memória vazia
    with app.app_context():
        E.pedir_releitura(app, esperar=True)    # a cópia de agora há pouco: nada vai ao Fracttal
        dd = E.dados()
    assert len(disco) == 2
    assert dd["lido"] == ts and [o["os"] for o in dd["os"]] == ["1", "3"] and dd["disco"] == "lida do disco"
    with app.app_context():
        assert E.eh_etm("ALF100-ESTM1") is True


def test_a_copia_velha_do_disco_aparece_e_e_relida(app, disco, tmp_path):
    with app.app_context():
        E.pedir_releitura(app, esperar=True)
    d = json.loads(gzip.decompress(_arquivo(tmp_path).read_bytes()))
    d["ts"] = time.time() - 3600                # gravada há 1 h
    _arquivo(tmp_path).write_bytes(gzip.compress(json.dumps(d).encode("utf-8")))
    E.limpar()
    with app.app_context():
        assert E.dados()["lido"] == d["ts"]     # a tela mostra a cópia velha com a hora dela
        E.pedir_releitura(app)                  # e relê (no teste, na hora; no servidor, por trás)
    assert len(disco) == 4 and E.dados()["lido"] > d["ts"]


@pytest.mark.parametrize("corpo", [b"isto nao e gzip", gzip.compress(b'{"formato": 99, "os": []}'),
                                   gzip.compress(b'{"formato": 1, "os": "torto"}')])
def test_a_copia_ilegivel_ou_de_outro_formato_e_ignorada(app, disco, tmp_path, corpo):
    _arquivo(tmp_path).parent.mkdir(parents=True)
    _arquivo(tmp_path).write_bytes(corpo)
    with app.app_context():
        d = E.dados()
    assert not d["lido"] and d["os"] == [] and "ignorada" in d["disco"]


def test_a_releitura_que_falha_guarda_a_copia(app, disco, tmp_path, monkeypatch):
    with app.app_context():
        E.pedir_releitura(app, esperar=True)
    antes = _arquivo(tmp_path).read_bytes()

    def recusa(path):
        raise RuntimeError("o Fracttal recusou por excesso de pedidos (HTTP 429)")
    monkeypatch.setattr(E, "_ler_fracttal", recusa)
    E._EST["ts"] -= 600                         # a cópia de 10 min atrás
    with app.app_context():
        E.pedir_releitura(app)
    d = E.dados()
    assert "HTTP 429" in d["erro"] and [o["os"] for o in d["os"]] == ["1", "3"] and d["erro_em"]
    assert _arquivo(tmp_path).read_bytes() == antes


def test_a_os_mexida_e_relida_sozinha_num_pedido(app, disco, tmp_path, monkeypatch):
    from nexus.engenharia import os_equipe
    with app.app_context():
        E.pedir_releitura(app, esperar=True)
    pedidos = []

    def uma(path):
        pedidos.append(path)
        return {"data": [w(3, "Corretiva", resp="Ana Lima", pid=1, task="IN_PROGRESS")]}
    monkeypatch.setattr(os_equipe, "_ler_fracttal", uma)
    with app.app_context():
        assert E.reler_os("3") is True
    assert len(pedidos) == 1 and pedidos[0].startswith("work_orders?wo_folio=3")
    o3 = next(o for o in E.dados()["os"] if o["os"] == "3")
    assert o3["responsavel"] == "Ana Lima" and o3["trabalho"] == "engenharia" and o3["coluna_etm"] == "em_andamento"
    assert [o["os"] for o in E.dados()["os"]] == ["1", "3"]                 # no mesmo lugar, sem repetir
    d = json.loads(gzip.decompress(_arquivo(tmp_path).read_bytes()))
    assert next(o for o in d["os"] if o["os"] == "3")["responsavel"] == "Ana Lima"


def test_sem_copia_a_os_mexida_nao_inventa_a_tela(app, disco):
    with app.app_context():
        assert E.reler_os("3") is False


# ── a tela na Performance ────────────────────────────────────────────────────────────────────────────────────────────
def test_o_endereco_antigo_das_etms_responde_308_para_a_performance(cliente):
    from test_engenharia_acompanhamento import ANA, _como
    c = _como(cliente, ANA, admin=True)
    r = c.get("/t/engenharia/etm?atualizar=1")
    assert r.status_code == 308 and r.headers["Location"].endswith("/t/performance/etm?atualizar=1")
    r = c.post("/t/engenharia/etm/finalizar", json={}, headers=SAME)
    assert r.status_code == 308 and r.headers["Location"].endswith("/t/performance/etm/finalizar")
    assert c.get("/t/engenharia/etm/os/17003").headers["Location"].endswith("/t/performance/etm/os/17003")


def test_o_menu_tem_as_etms_na_performance_e_o_clima_na_usinas_360(app):
    from nexus.auth import setor_telas as ST
    torres = {t.id: t for t in app.extensions["nexus_torres"]}
    perf = [s.id for s in torres["performance"].telas]
    assert "etm" in perf and "clima" not in perf and "clima/mapa" not in perf
    assert perf.index("etm") == perf.index("strings-trackers") + 1
    assert torres["performance"].tela("etm").do_setor == SID.PERFORMANCE and torres["engenharia"].tela("etm") is None
    campo = [s.id for s in torres["campo"].telas]
    assert campo.index("clima") == campo.index("equipe") + 1
    assert ST.RENOMEADAS["engenharia/etm"] == "performance/etm" and ST.RENOMEADAS["performance/clima"] == "campo/clima"


def test_os_enderecos_antigos_do_clima_e_do_mapa_de_risco(cliente):
    from test_engenharia_acompanhamento import ANA, _como
    c = _como(cliente, ANA, admin=True)
    r = c.get("/t/performance/clima?cliente=X")
    assert r.status_code == 308 and r.headers["Location"].endswith("/t/campo/clima?cliente=X")
    r = c.get("/t/performance/clima/usina/7")
    assert r.status_code == 308 and r.headers["Location"].endswith("/t/campo/clima/usina/7")
    for url in ("/t/performance/clima/mapa", "/t/performance/clima/mapa?tv=1"):
        r = c.get(url)
        assert r.status_code == 302 and r.headers["Location"].endswith("/t/campo/equipe?ver=usinas&clima=1")


@pytest.fixture
def tela_perf(app, monkeypatch):
    from nexus.auth import setor_telas as ST
    oss = E.montar([w(1, "Corretiva"), w(3, "Corretiva", status=3, task="DONE")], {"ALF100-ESTM1"}, SET,
                   __import__("datetime").date.today())
    pedidos = []
    monkeypatch.setattr(E, "dados", lambda: {"os": oss, "lido": time.time() - 7200, "lendo": False, "erro": "HTTP 429",
                                             "erro_em": time.time()})
    monkeypatch.setattr(E, "pedir_releitura", lambda app=None, esperar=False, forcar=False: pedidos.append((esperar, forcar)))
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": {"performance/etm", "performance/equipe"},
                                               "setor": {"id": SID.PERFORMANCE, "nome": "Performance"}, "erro": ""})
    return pedidos


def test_a_tela_abre_nas_estacoes_em_aberto_com_o_chat_e_a_caixa_de_comentar(tela_perf, cliente):
    from test_engenharia_acompanhamento import ANA, _como
    html = _como(cliente, ANA).get("/t/performance/etm").get_data(as_text=True)
    d = json.loads(html.split('<script type="application/json" id="etm-dados">', 1)[1].split("</script>", 1)[0])
    assert all(o["wid"] for o in d["oss"]) and d["pode"] is True
    # as duas visões (ETMs e OS) e a gaveta da usina com a linha do tempo, a caixa de comentar e a Nova demanda
    assert 'data-modo="etms"' in html and 'data-modo="os"' in html and 'id="etm-ab-os"' in html
    assert 'id="etm-us"' in html and 'id="etm-tl"' in html and 'id="etm-chat-novo"' in html and 'id="etm-chat-os"' in html
    assert 'id="etm-us-dem"' in html and 'id="etm-dm-form"' in html and "lista-sugestoes.js" in html
    # os textos de ajuda saíram (Levi: "ninguém vai ler essa porcaria")
    assert "etm-lado-nota" not in html and "O tempo em aberto é o da OS mais antiga" not in html and "kb-rodape" not in html
    assert "nexusRota('/os/_nexus/engenharia/os/' + encodeURIComponent(o.wid) + '/comentar')" in html
    assert "Finalizar pela Performance" in html and "Finalizar pela Engenharia" not in html
    # a cópia de 2 h atrás com a releitura recusada: a tela mostra a cópia e diz, sem o aviso grande de "sem leitura"
    assert "recusada pelo Fracttal; mostrando a cópia guardada" in html and "Ainda sem nenhuma leitura" not in html


def test_quem_nao_comenta_na_os_nao_ve_a_caixa(tela_perf, cliente, monkeypatch):
    from test_engenharia_acompanhamento import BETO, _como

    from nexus.auth import setor_telas as ST
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": {"campo/usinas"},
                                               "setor": {"id": SID.COS, "nome": "COS"}, "erro": ""})
    html = _como(cliente, BETO).get("/t/performance/etm").get_data(as_text=True)
    assert 'id="etm-chat-novo"' not in html and 'id="etm-tl"' in html            # a linha do tempo se lê; comentar, não


def test_a_volta_da_os_rele_so_ela(tela_perf, cliente, monkeypatch):
    from test_engenharia_acompanhamento import ANA, _como
    relidas = []
    monkeypatch.setattr(E, "reler_os", lambda f: relidas.append(f) or True)
    _como(cliente, ANA).get("/t/performance/etm?releia=3")
    assert relidas == ["3"] and tela_perf[-1] == (False, False)

    def cai(f):
        raise RuntimeError("HTTP 429")
    monkeypatch.setattr(E, "reler_os", cai)
    html = _como(cliente, ANA).get("/t/performance/etm?releia=3").get_data(as_text=True)
    assert "Não consegui reler a OS 3 no Fracttal agora (RuntimeError)" in html


def test_os_scripts_da_tela_compilam_no_node(tela_perf, cliente, tmp_path):
    """O JS da tela (as abas, o chat com a caixa de comentar) passa pelo node sem erro de sintaxe; sem o node, pula."""
    import re
    import shutil
    import subprocess

    from test_engenharia_acompanhamento import ANA, _como
    node = shutil.which("node")
    if not node:
        pytest.skip("sem o node nesta máquina")
    html = _como(cliente, ANA, admin=True).get("/t/performance/etm").get_data(as_text=True)
    scripts = [s for s in re.findall(r"<script>(.*?)</script>", html, flags=re.S) if "etm-dados" in s or "abrirChat" in s]
    assert scripts, "o script da tela não veio"
    for i, s in enumerate(scripts):
        arq = tmp_path / f"etm{i}.js"
        arq.write_text(s, encoding="utf-8")
        r = subprocess.run([node, "--check", str(arq)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


# ── a Nova demanda da usina (25/11/2026) ─────────────────────────────────────────────────────────────────────────────
def test_a_nova_demanda_da_usina_traz_a_performance_o_tema_e_a_os_do_retrato(tela_perf, cliente, monkeypatch):
    from test_engenharia_acompanhamento import ANA, _como

    from nexus.comando import demandas as D
    from nexus.torres import comando as TC
    from nexus.torres.performance import etm_tela
    monkeypatch.setattr(D, "faltam_chaves", lambda: [])
    monkeypatch.setattr(TC, "_meu_hmac", lambda: "h-ana")
    monkeypatch.setattr(TC, "_codigo", lambda: "cod-1")
    monkeypatch.setattr(D, "temas", lambda sid=None, so_ativos=True: [
        {"tema_id": "t1", "nome": "Verificação de ativo", "prazo_dias_uteis": 3, "setor_id": SID.PERFORMANCE, "area": ""},
        {"tema_id": "t2", "nome": "Acompanhamento de chamado", "prazo_dias_uteis": 2, "setor_id": SID.PERFORMANCE,
         "area": "Chamados"}])
    monkeypatch.setattr(D, "pessoas_com_setor", lambda: [
        {"hmac": "h-ana", "nome": "Ana Lima", "setor_id": SID.PERFORMANCE},
        {"hmac": "h-caio", "nome": "Caio Reis", "setor_id": SID.PERFORMANCE},
        {"hmac": "h-dora", "nome": "Dora Melo", "setor_id": SID.COS}])
    monkeypatch.setattr(etm_tela, "_usina_no_retrato", lambda folios: (42, {1}))
    j = _como(cliente, ANA).get("/t/performance/etm/usina/demanda", query_string={"usina": U}).get_json()
    assert j["setor_id"] == str(SID.PERFORMANCE) and j["usina"][0] == 42 and j["acao"].endswith("/demandas/nova?etm=1")
    assert [p["nome"] for p in j["pessoas"]] == ["Caio Reis"]                     # só a Performance, sem quem pede
    assert [t["tema_id"] for t in j["temas"]] == ["t1"] and j["tema_padrao"] == "t1"   # sem os temas da área Chamados
    assert [o["os"] for o in j["oss"]] == ["1"]                                    # só a aberta que o retrato tem


def test_a_nova_demanda_sem_login_da_pessoa_diz(tela_perf, cliente, monkeypatch):
    from test_engenharia_acompanhamento import ANA, _como

    from nexus.comando import demandas as D
    from nexus.torres import comando as TC
    monkeypatch.setattr(D, "faltam_chaves", lambda: [])
    monkeypatch.setattr(TC, "_meu_hmac", lambda: "")
    r = _como(cliente, ANA).get("/t/performance/etm/usina/demanda", query_string={"usina": U})
    assert r.status_code == 403 and "conta da Grid" in r.get_json()["erro"]


def test_a_demanda_da_etm_volta_para_a_tela_com_o_aviso(app):
    from nexus.torres.comando import demandas_tela as DT
    with app.test_request_context("/"):
        u = DT._no_chamado("etm", "ok", "Demanda enviada.")
    assert u.startswith("/t/performance/etm?") and "ok=Demanda+enviada." in u and u.endswith("#abertas")


# ── as demandas na linha do tempo (25/11/2026) ───────────────────────────────────────────────────────────────────────
def _demanda(did, oss, usinas=(), titulo="Conferir o piranômetro"):
    return {"demanda_id": did, "titulo": titulo, "de_nome": "Ana Lima", "para_nome": "Caio Reis", "tema_nome": "Verificação de ativo",
            "estado": {"rotulo": "Aberta", "tom": "alerta", "aberta": True}, "registrado_em": "2026-11-25T10:00:00+00:00",
            "aberta_txt": "25/11 07:00", "oss": list(oss), "usinas": [(u, "Usina") for u in usinas],
            "passos": [{"nome": "Caio Reis", "rotulo": "respondeu", "texto": "vou ver amanhã", "quando_txt": "25/11 08:00"}]}


def test_as_demandas_que_citam_a_os_ou_a_usina_entram_na_linha_do_tempo(app, monkeypatch):
    from nexus.comando import demandas as D
    from nexus.torres.performance import etm_tela
    monkeypatch.setattr(D, "faltam_chaves", lambda: [])
    monkeypatch.setattr(D, "ler", lambda: {})
    monkeypatch.setattr(D, "lista", lambda hoje, lido: [_demanda("d1", [3]), _demanda("d2", [], usinas=[42]),
                                                        _demanda("d3", [99]), _demanda("d4", [], usinas=[7])])
    with app.test_request_context("/"):
        ds = etm_tela.demandas_das({"1", "3"}, 42)
    assert [d["id"] for d in ds] == ["d1", "d2"] and ds[0]["os"] == "3" and ds[1]["os"] == ""
    assert ds[0]["ultimo"] == "Caio Reis respondeu: vou ver amanhã · 25/11 08:00" and ds[0]["caixa"].endswith("?d=d1#demandas")


def test_o_chat_da_usina_traz_as_demandas(tela_perf, cliente, monkeypatch):
    from test_engenharia_acompanhamento import ANA, _como

    from nexus.engenharia import os_acompanhamento as O
    from nexus.torres.performance import etm_tela
    monkeypatch.setattr(O, "ler", lambda: {"lido_em": "agora", "eventos": []})
    monkeypatch.setattr(etm_tela, "_usina_no_retrato", lambda folios: (42, set()))
    monkeypatch.setattr(etm_tela, "demandas_das", lambda folios, uid: [{"id": "d1", "titulo": "x", "iso": ""}] if uid == 42 else [])
    j = _como(cliente, ANA).get("/t/performance/etm/usina/comentarios", query_string={"usina": U}).get_json()
    assert j["demandas"] == [{"id": "d1", "titulo": "x", "iso": ""}] and j["erro_demandas"] == ""
    html = _como(cliente, ANA).get("/t/performance/etm").get_data(as_text=True)
    assert "demandas = x.j.demandas || []" in html and "'Demanda · '" in html



def test_a_linha_do_tempo_diz_o_status_de_cada_os_e_o_finalizar_diz_que_nada_muda_no_fracttal(tela_perf, cliente):
    # Levi, 25/11/2026: "do lado do número da OS, poderia ter um traço e o status daquela OS" e "quando eu venho finalizar
    # pela performance, finalizar 2 OS, eu estou concluindo 2 OS?"
    from test_engenharia_acompanhamento import ANA, _como
    html = _como(cliente, ANA).get("/t/performance/etm").get_data(as_text=True)
    assert "'— ' + o.status" in html and "'Criada no Fracttal: '" in html and "'Concluída no Fracttal: '" in html
    assert "nada muda no Fracttal (nem o status, nem a data fim)" in html and 'id="etm-us-fim-lista"' in html and 'id="etm-us-conc"' in html


# ── concluir no Fracttal, tarefa por tarefa, antes de finalizar (25/11/2026) ─────────────────────────────────────────
class _ApiFalsa:
    """O `api` do clone do OS Creator dublado: as tarefas da OS, o checklist, o registro de execução e a conclusão."""
    class SessionExpired(Exception):
        pass

    def __init__(self, tarefas, faltam=None, recusa=None):
        self.tarefas, self.faltam, self.recusa = tarefas, faltam or {}, recusa
        self.feito, self.concluida = [], False

    def get_os_detalhes(self, wid):
        return {"tarefas": [dict(t) for t in self.tarefas]}

    def subtarefas_da_tarefa(self, tid):
        return [{"id_form_item": 1, "obrigatorio": True, "descricao": d, "valor": ""} for d in self.faltam.get(tid, [])]

    def registrar_execucao(self, tid, ini, fim, note=""):
        if self.recusa == tid:
            raise RuntimeError("recusado pelo Fracttal")
        self.feito.append((tid, ini, fim))
        for t in self.tarefas:
            if t["id"] == tid:
                t["inicio"], t["fim"] = ini.isoformat(), fim.isoformat()
        return {"ok": True, "confirmado": True}

    def concluir_os_checado(self, wid):
        self.concluida = True
        return {"ok": True, "data_fim": {}}


class _Regra:
    @staticmethod
    def rotulos_tarefas(ts):
        return {t["id"]: t.get("titulo") or "Tarefa" for t in ts}

    @staticmethod
    def faltando_obrigatorias(campos, valores):
        return [c["descricao"] for c in campos if c.get("obrigatorio") and not c.get("valor")]

    @staticmethod
    def tarefas_sem_fim(ts):
        return [t.get("titulo") for t in ts or [] if not str(t.get("fim") or "").strip()]


@pytest.fixture
def concluir(app, monkeypatch):
    """A rota com o REST, a sessão do Fracttal e o clone do OS Creator dublados; a OS 7 aberta, criada em 20/11 15:00 UTC."""
    import contextlib
    import sys
    import types

    from nexus.auth import setor_telas as ST
    from nexus.engenharia import etm_marcas as M
    from nexus.engenharia import os_acompanhamento as O
    from nexus.engenharia import os_equipe
    from nexus.torres import engenharia as TE
    from nexus.torres.oscreator import etm_concluir as EC
    estado = {"status": "Em Processo", "marcas": [], "comentarios": []}
    monkeypatch.setattr(os_equipe, "ler_os", lambda f: {"wid": 777, "os": str(f), "status": estado["status"],
                                                        "codigo": "ALF100-ESTM1", "criada_iso": "2026-11-20T15:00:00+00:00",
                                                        "ativos": [], "usina": U})
    monkeypatch.setattr(EC, "sessao_do_os", lambda app: {"jwt": "j", "conta": {"email": "ana.lima@gridco.com.br"}})
    monkeypatch.setattr(EC, "clone", lambda app: None)
    monkeypatch.setattr(EC, "_primeiro_comentario", lambda wid: None)
    monkeypatch.setattr(E, "reler_os", lambda f: True)
    monkeypatch.setattr(M, "marcar", lambda *a, **k: estado["marcas"].append(a[1]) or {"aviso": "ok"})
    monkeypatch.setattr(O, "registrar_comentario", lambda os_, texto, *a, **k: estado["comentarios"].append(texto))
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": {"performance/etm"},
                                               "setor": {"id": SID.PERFORMANCE, "nome": "Performance"}, "erro": ""})
    monkeypatch.setattr(TE, "_na_etm", lambda o: o)
    monkeypatch.setattr(TE, "_os_para_gravar", lambda o: {"wid": 777, "folio": o["os"], "codigo": "ALF100-ESTM1"})

    def instalar(api):
        sessao = types.SimpleNamespace(contexto=lambda jwt, email: contextlib.nullcontext())
        monkeypatch.setitem(sys.modules, "api", api)
        monkeypatch.setitem(sys.modules, "os_web", types.SimpleNamespace(os_acoes_web=_Regra, sessao=sessao))
        monkeypatch.setitem(sys.modules, "os_web.os_acoes_web", _Regra)
        monkeypatch.setitem(sys.modules, "os_web.sessao", sessao)
        return api
    estado["instalar"] = instalar
    return estado


URL_CONC = "/os/_nexus/etm/os/777/concluir"
PRONTO = {"comentario": "x", "folio": "7"}


def test_concluir_le_as_tarefas_com_o_inicio_sugerido_e_o_checklist(concluir, cliente):
    from test_engenharia_acompanhamento import ANA, _como
    concluir["instalar"](_ApiFalsa([{"id": 1, "titulo": "Limpar o piranômetro", "inicio": "", "fim": ""},
                                     {"id": 2, "titulo": "Trocar o cabo", "inicio": "2026-11-21T13:00:00Z", "fim": ""},
                                     {"id": 3, "titulo": "Conferir", "inicio": "2026-11-21T13:00:00Z",
                                      "fim": "2026-11-21T14:00:00Z"}], faltam={2: ["Foto do cabo"]}))
    j = _como(cliente, ANA).get(URL_CONC, query_string={"folio": "7"}).get_json()
    t = {x["id"]: x for x in j["tarefas"]}
    # sem início na tarefa e sem comentário: a criação da OS (20/11 15:00 UTC = 12:00 em Brasília)
    assert t[1]["sugerido"] == "2026-11-20T12:00" and t[1]["inicio"] == "" and j["origem_inicio"] == "a criação da OS"
    assert t[2]["inicio"] == "2026-11-21T10:00" and t[2]["faltam"] == ["Foto do cabo"]
    assert t[3]["feita"] is True and t[3]["fim"] == "21/11/2026 11:00"


def test_concluir_fecha_cada_tarefa_e_so_depois_conclui_e_finaliza(concluir, cliente):
    from test_engenharia_acompanhamento import ANA, SAME, _como
    api = concluir["instalar"](_ApiFalsa([{"id": 1, "titulo": "Limpar", "inicio": "", "fim": ""},
                                          {"id": 2, "titulo": "Cabo", "inicio": "2026-11-21T13:00:00Z", "fim": ""}]))
    corpo = {"folio": "7", "comentario": "Piranômetro limpo e cabo trocado",
             "tarefas": [{"id": 1, "inicio": "2026-11-21T08:00", "fim": "2026-11-21T09:30"}, {"id": 2, "fim": "2026-11-21T11:00"}]}
    r = _como(cliente, ANA).post(URL_CONC, json=corpo, headers=SAME)
    assert r.status_code == 200 and r.get_json()["ok"] is True and "concluída no Fracttal" in r.get_json()["mensagem"]
    assert [x[0] for x in api.feito] == [1, 2] and api.concluida is True
    assert api.feito[1][1].isoformat().startswith("2026-11-21T13:00")             # o início que a tarefa já tinha fica
    assert concluir["marcas"] == ["finalizado"]
    assert concluir["comentarios"] == ["Finalizado pela Performance: Piranômetro limpo e cabo trocado"]


@pytest.mark.parametrize("corpo, trecho", [
    ({"comentario": "", "tarefas": [{"id": 1, "inicio": "2026-11-21T08:00", "fim": "2026-11-21T09:00"}]}, "obrigatório"),
    ({"comentario": "x", "tarefas": [{"id": 1, "inicio": "2026-11-21T08:00"}]}, "falta a data fim"),
    ({"comentario": "x", "tarefas": [{"id": 1, "inicio": "2026-11-21T08:00", "fim": "2026-11-21T07:00"}]}, "anterior ao início"),
    ({"comentario": "x", "tarefas": [{"id": 1, "inicio": "2026-11-21T08:00", "fim": "2099-01-01T07:00"}]}, "no futuro"),
    ({"comentario": "x", "tarefas": [{"id": 1, "inicio": "2026-10-01T08:00", "fim": "2026-11-21T09:00"}]}, "anterior à criação"),
])
def test_concluir_confere_tudo_antes_de_escrever(concluir, cliente, corpo, trecho):
    from test_engenharia_acompanhamento import ANA, SAME, _como
    api = concluir["instalar"](_ApiFalsa([{"id": 1, "titulo": "Limpar", "inicio": "", "fim": ""}]))
    r = _como(cliente, ANA).post(URL_CONC, json=dict(corpo, folio="7"), headers=SAME)
    assert r.status_code == 400 and trecho in r.get_json()["erro"]
    assert api.feito == [] and api.concluida is False and concluir["marcas"] == []


def test_concluir_nao_conclui_com_checklist_obrigatorio_em_branco(concluir, cliente):
    from test_engenharia_acompanhamento import ANA, SAME, _como
    api = concluir["instalar"](_ApiFalsa([{"id": 1, "titulo": "Limpar", "inicio": "", "fim": ""}], faltam={1: ["Foto"]}))
    r = _como(cliente, ANA).post(URL_CONC, json=dict(PRONTO, tarefas=[{"id": 1, "inicio": "2026-11-21T08:00",
                                                                       "fim": "2026-11-21T09:00"}]), headers=SAME)
    assert r.status_code == 400 and "checklist" in r.get_json()["erro"] and api.feito == [] and not api.concluida


def test_a_tarefa_recusada_para_tudo_e_a_os_nao_e_concluida(concluir, cliente):
    from test_engenharia_acompanhamento import ANA, SAME, _como
    api = concluir["instalar"](_ApiFalsa([{"id": 1, "titulo": "Limpar", "inicio": "", "fim": ""},
                                          {"id": 2, "titulo": "Cabo", "inicio": "", "fim": ""}], recusa=2))
    datas = {"inicio": "2026-11-21T08:00", "fim": "2026-11-21T09:00"}
    r = _como(cliente, ANA).post(URL_CONC, json=dict(PRONTO, tarefas=[dict(datas, id=1), dict(datas, id=2)]), headers=SAME)
    j = r.get_json()
    assert r.status_code == 502 and "Cabo" in j["erro"] and "NÃO foi concluída" in j["erro"]
    assert [x[0] for x in api.feito] == [1] and api.concluida is False and concluir["marcas"] == []


def test_concluir_recusa_a_os_ja_concluida_e_quem_nao_e_da_performance(concluir, cliente, monkeypatch):
    from test_engenharia_acompanhamento import ANA, BETO, SAME, _como

    from nexus.auth import setor_telas as ST
    concluir["instalar"](_ApiFalsa([{"id": 1, "titulo": "Limpar", "inicio": "", "fim": ""}]))
    concluir["status"] = "Concluída"
    r = _como(cliente, ANA).get(URL_CONC, query_string={"folio": "7"})
    assert r.status_code == 409 and "já está concluída" in r.get_json()["erro"]
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": {"performance/etm"},
                                               "setor": {"id": SID.ENGENHARIA, "nome": "Engenharia"}, "erro": ""})
    r = _como(cliente, BETO).post(URL_CONC, json=dict(PRONTO, tarefas=[]), headers=SAME)
    assert r.status_code == 403
