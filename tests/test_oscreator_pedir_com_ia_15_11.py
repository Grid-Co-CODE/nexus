"""O Pedir com IA do OS Creator (Levi, 15/11/2026): a pessoa escolhe o setor, diz a OS numa frase, e a ficha volta
preenchida (cliente, usina, ativo, tema, subtarefas) para conferir e criar pela rota de sempre do setor; a data programada é
sempre daqui a 6 dias. A IA só propõe: o catálogo decide. O OpenRouter e o Fracttal são de mentira; nomes inventados."""
import datetime as dt
import json

import pytest
from test_oscreator_solic_engenharia import CATALOGO, USINA, _corpo, api, cli, reg  # noqa: F401  (fixture)

from os_web import solic_ia as IA
from os_web import solic_web as sw

TEMAS = [{"chave": "inversor_inspecao", "nome": "Inspeção de inversor", "classif1": "Corretiva", "tipo": "Corretiva",
          "n_subs": 2, "motivo": "", "tipos": ["Inversor"]},
         {"chave": "limpeza_modulos", "nome": "Limpeza de módulos", "classif1": "Preventiva", "tipo": "Preventiva",
          "n_subs": 1, "motivo": "", "tipos": ["Módulo"]}]
SUB_TEMA = [{"description": "Medir a tensão", "id_task_form_item_type": 3, "is_required": True, "attachments_required": False},
            {"description": "Foto do display", "id_task_form_item_type": 1, "is_required": True, "attachments_required": True}]
SUB_BASE = [{"description": "Descreva a atividade realizada", "id_task_form_item_type": 1, "is_required": True,
             "attachments_required": False}]
RESPOSTA = {"cliente": "Cliente X", "usina": "Usina Teste 1", "ativo": "inversor 1.1", "titulo": "Inspecionar o inversor",
            "descricao": "O inversor desliga toda tarde.", "tema": "inversor_inspecao",
            "subtarefas": [{"desc": "Fotografar a placa", "tipo": "foto"}, {"desc": "Medir a tensão", "tipo": "num"}],
            "faltou": ""}


@pytest.fixture
def ia(cli, monkeypatch):
    """A IA de mentira (guarda o que recebeu) e os temas, as subtarefas e a Classificação 1 de mentira."""
    import catalogos
    pedidos = []
    resposta = {"j": dict(RESPOSTA)}

    def chamar(chave, sistema, usuario, post=None):
        pedidos.append({"chave": chave, "sistema": sistema, "usuario": usuario})
        return {"texto": "```json\n%s\n```" % json.dumps(resposta["j"], ensure_ascii=False)}
    monkeypatch.setattr(IA, "CHAVE", lambda: "chave-de-teste")
    monkeypatch.setattr(IA, "chamar", chamar)
    monkeypatch.setattr(sw, "temas_para_tela", lambda: [dict(t) for t in TEMAS])
    monkeypatch.setattr(sw, "subtarefas_do_tema", lambda tema, tipo="": [dict(s) for s in (SUB_TEMA if tema else SUB_BASE)])
    monkeypatch.setattr(catalogos, "tipos_solicitacao", lambda: {"classif1": [{"id": 7, "description": "Corretiva"},
                                                                             {"id": 8, "description": "Programada"}]})
    cli.pedidos, cli.resposta = pedidos, resposta
    return cli


def _seis_dias():
    return (dt.datetime.now(IA.BRT) + dt.timedelta(days=6)).replace(hour=8, minute=0, second=0, microsecond=0)


def test_o_numero_do_ativo_tem_de_ser_o_mesmo():
    assert IA.nota("inversor 2.1", "Inversor 2.3") == 0
    assert IA.escolher("inversor 2.1", ["Inversor 2.3", "Inversor 2.1", "Inversor 1.2"])[0] == "Inversor 2.1"
    melhor, cand = IA.escolher("inversor", ["Inversor 1.1", "Inversor 1.2"])      # empate: a pessoa escolhe
    assert melhor is None and len(cand) == 2
    assert IA.escolher("", ["Inversor 1.1"]) == (None, [])
    # a 1ª prova no ar (15/11/2026): as mesmas palavras em dois ativos; o nome igual vence
    assert IA.escolher("inversor 1.1", ["Disjuntor do Inversor 1.1", "Inversor 1.1"])[0] == "Inversor 1.1"


def test_a_resposta_e_lida_mesmo_com_cerca_e_o_raciocinio_sai():
    assert IA.ler_json('Claro!\n```json\n{"titulo": "x"}\n```') == {"titulo": "x"}
    assert IA.ler_json("sem json nenhum") == {} and IA.ler_json("[1, 2]") == {}

    class R:
        def __init__(self, st, j=None):
            self.status_code, self._j = st, j

        def json(self):
            return self._j
    assert "cota grátis" in IA.chamar("k", "s", "u", post=lambda *a, **k: R(429))["erro"]
    assert "recusou a chave 4" in IA.chamar("k", "s", "u", post=lambda *a, **k: R(401))["erro"]
    ok = IA.chamar("k", "s", "u", post=lambda *a, **k: R(200, {"choices": [{"message": {"content": "<think>hm</think>{}"}}]}))
    assert ok == {"texto": "{}"}


def test_a_ficha_volta_conferida_no_catalogo(ia):
    r = ia.post("/os/api/solic/ia/preencher", json={"setor": "pcm", "texto": "inspeção no inversor 1.1 da usina teste 1"})
    assert r.status_code == 200
    f = r.get_json()
    assert (f["cliente"], f["usina"], f["ativo"]["id"]) == ("Cliente X", USINA, 2)
    assert f["tema"] == "inversor_inspecao" and f["classif1"] == {"id": 7, "txt": "Corretiva"}
    # as do tema e a que a IA pediu a mais; o tipo "foto" não existe no editor e vira Texto; a repetida não entra
    assert [(s["desc"], s["tipo"], s["da_ia"]) for s in f["subtarefas"]] == [
        ("Medir a tensão", "num", False), ("Foto do display", "texto", False), ("Fotografar a placa", "texto", True)]
    assert f["subtarefas"][1]["anexo"] is True
    assert f["programada_iso"] == _seis_dias().strftime("%Y-%m-%d %H:%M") and f["pronta"] and not f["perguntas"]
    # o que foi para a IA: a chave 4, a lista de usinas e de temas, e o pedido
    p = ia.pedidos[-1]
    assert p["chave"] == "chave-de-teste" and USINA in p["sistema"] and "inversor_inspecao" in p["sistema"]
    assert p["usuario"] == "inspeção no inversor 1.1 da usina teste 1"
    # no PCM a IA recebe a lista da Classificação 1 da solicitação; a ficha traz as opções para a pessoa trocar
    assert '"classif1"' in p["sistema"] and "Programada" in p["sistema"]
    assert [o["txt"] for o in f["classif1_opcoes"]] == ["Corretiva", "Programada"]


def test_sem_tema_a_classificacao_e_a_que_a_ia_propos_se_for_da_lista(ia):
    ia.resposta["j"] = dict(RESPOSTA, tema="limpeza_modulos", classif1="programada")
    f = ia.post("/os/api/solic/ia/preencher", json={"setor": "pcm", "texto": "x"}).get_json()
    assert f["tema"] == "" and f["classif1"] == {"id": 8, "txt": "Programada"}
    ia.resposta["j"] = dict(RESPOSTA, tema="", classif1="Inventada")
    assert ia.post("/os/api/solic/ia/preencher", json={"setor": "pcm", "texto": "x"}).get_json()["classif1"] == {}
    # na Engenharia e na Performance não há Classificação 1 na ficha nem no pedido à IA
    ia.post("/os/api/solic/ia/preencher", json={"setor": "engenharia", "texto": "x"})
    assert '"classif1"' not in ia.pedidos[-1]["sistema"]


def test_o_tema_que_nao_e_do_tipo_do_ativo_cai_e_vem_a_base(ia):
    ia.resposta["j"] = dict(RESPOSTA, tema="limpeza_modulos", subtarefas=[])
    f = ia.post("/os/api/solic/ia/preencher", json={"setor": "performance", "texto": "baixa performance no inversor 1.1"}).get_json()
    assert f["tema"] == "" and [s["desc"] for s in f["subtarefas"]] == ["Descreva a atividade realizada"]
    assert [t["chave"] for t in f["temas"]] == ["inversor_inspecao"] and f["responsavel"] is True


def test_o_que_falta_vira_pergunta(ia):
    ia.resposta["j"] = {"cliente": "Cliente X", "titulo": "Trocar o fusível", "descricao": "Queimou."}
    f = ia.post("/os/api/solic/ia/preencher", json={"setor": "engenharia", "texto": "trocar o fusível"}).get_json()
    assert f["cliente"] == "Cliente X" and f["usina"] == "" and f["perguntas"] == ["Em qual usina?"] and not f["pronta"]
    # a resposta da pessoa vai com a ficha de antes
    ia.post("/os/api/solic/ia/preencher", json={"setor": "engenharia", "texto": "na usina teste 1", "anterior": f["anterior"]})
    assert "Trocar o fusível" in ia.pedidos[-1]["usuario"] and "na usina teste 1" in ia.pedidos[-1]["usuario"]


def test_sem_a_chave_a_tela_diz_e_nada_vai_a_ia(ia, monkeypatch):
    monkeypatch.setattr(IA, "CHAVE", None)
    r = ia.post("/os/api/solic/ia/preencher", json={"setor": "pcm", "texto": "qualquer"})
    assert r.status_code == 503 and r.get_json()["sem_chave"] and not ia.pedidos
    h = ia.get("/os/solicitacao").get_data(as_text=True)            # sem a chave, a tela é a de sempre
    assert 'id="sia"' not in h and "data-sia-abrir" not in h and "solic_ia.js" not in h
    assert ia.post("/os/api/solic/ia/preencher", json={"setor": "x", "texto": "a"}).status_code == 400


def test_trocar_na_ficha_vale_a_escolha_e_nao_gasta_ia(ia, monkeypatch):
    monkeypatch.setattr(IA, "chamar", lambda *a, **k: pytest.fail("a ficha refeita não pede à IA"))
    f = ia.post("/os/api/solic/ia/ficha", json={"setor": "pcm", "escolhidos": {"cliente": "Cliente X", "usina": USINA, "ativo_id": 1},
                                                "titulo": "Olhar o nobreak", "descricao": "Apita.", "tema": "inversor_inspecao",
                                                "classif1_atual": "Programada",
                                                "extras": [{"desc": "Anotar o alarme", "tipo": "texto"}]}).get_json()
    assert f["ativo"]["id"] == 1 and f["tema"] == "" and f["classif1"] == {"id": 8, "txt": "Programada"}
    # a que a pessoa marcou na ficha vence a do tema
    g = ia.post("/os/api/solic/ia/ficha", json={"setor": "pcm", "tema": "inversor_inspecao", "classif1_atual": "Corretiva",
                                                "escolhidos": {"cliente": "Cliente X", "usina": USINA, "ativo_id": 2,
                                                               "classif1_id": 8}}).get_json()
    assert g["tema"] == "inversor_inspecao" and g["classif1"] == {"id": 8, "txt": "Programada"}
    assert [s["desc"] for s in f["subtarefas"]] == ["Descreva a atividade realizada", "Anotar o alarme"]


def test_a_os_da_ia_na_engenharia_leva_as_subtarefas_e_6_dias(cli):
    subs = [{"desc": "Medir a isolação", "tipo": "num", "anexo": True}]
    r = cli.post("/os/api/solicitacao/engenharia/criar", json=_corpo(ativos=[2], origem="ia", subtarefas=subs))
    assert r.status_code == 200
    assert cli.feito["subtasks"] == sw.subs_para_api(subs) and cli.feito["prog_date"] == IA.programada(dt.datetime.now(IA.BRT))
    # a tela de sempre segue sem subtarefas e com os 7 dias, mesmo se mandar as subtarefas
    cli.post("/os/api/solicitacao/engenharia/criar", json=_corpo(ativos=[2], subtarefas=subs))
    assert cli.feito["subtasks"] == [] and cli.feito["prog_date"] > IA.programada(dt.datetime.now(IA.BRT))


def test_a_janela_entra_por_cima_das_tres_telas_e_da_para_fazer_manualmente(ia):
    """Levi, 15/11/2026: "um pouco menor em formato de blur, a pessoa pode escolher fazer manualmente se quiser"."""
    for url, setor in (("/os/solicitacao", "pcm"), ("/os/solicitacao/engenharia", "engenharia"),
                       ("/os/solicitacao/performance", "performance")):
        h = ia.get(url).get_data(as_text=True)
        for s in ('id="sia_veu" hidden', 'data-setor-inicial="%s"' % setor, "data-sia-abrir", "data-sia-manual",
                  "Fazer manualmente", "daqui a 6 dias", "solic_ia.js", "solic_ia.css", 'data-setor="pcm"'):
            assert s in h, (url, s)
        assert 'id="cb_cli"' in h or 'id="cb_cliente"' in h or "Cliente" in h          # o formulário de sempre continua
    r = ia.get("/os/solicitacao/ia")                                    # o cartão do Início: a do PCM, com a janela aberta
    assert r.status_code == 302 and r.headers["Location"].endswith("/os/solicitacao?ia=1")


def test_em_teste_so_quem_a_ponte_libera_ve_e_usa(ia):
    """No ar em teste (Levi, 15/11/2026: "uma janela de teste no Nexus pra gente testar"): a ponte marca o pedido; sem a
    liberação, a Nova solicitação é a de sempre e o preencher recusa sem ir à IA."""
    fora = {"os_web.ia_liberada": False}
    h = ia.get("/os/solicitacao", environ_overrides=fora).get_data(as_text=True)
    assert 'id="sia"' not in h and "data-sia-abrir" not in h
    r = ia.post("/os/api/solic/ia/preencher", json={"setor": "pcm", "texto": "x"}, environ_overrides=fora)
    assert r.status_code == 403 and "em teste" in r.get_json()["erro"] and not ia.pedidos
    assert ia.post("/os/api/solic/ia/ficha", json={"setor": "pcm"}, environ_overrides=fora).status_code == 403
    assert 'id="sia"' in ia.get("/os/solicitacao", environ_overrides={"os_web.ia_liberada": True}).get_data(as_text=True)


def test_a_ponte_libera_o_administrador_e_a_variavel_libera_todos(app, monkeypatch):
    from flask import session

    from nexus.torres.oscreator import ponte
    monkeypatch.delenv("NEXUS_PEDIR_COM_IA", raising=False)
    with app.test_request_context("/os/solicitacao"):
        session["admin"] = False
        assert ponte.ia_liberada() is False
        session["admin"] = True
        assert ponte.ia_liberada() is True
        session["admin"] = False
        monkeypatch.setitem(app.config, "NEXUS_PEDIR_COM_IA", "1")
        assert ponte.ia_liberada() is True


def test_o_codigo_da_usina_no_texto_acha_a_usina(ia, monkeypatch):
    """Na prova no ar (15/11/2026) o Levi pediu "o inversor 2.2 de CPP100" e a IA não sabia de que usina era: o código é o
    começo do código dos ativos da usina. A IA recebe o código de cada usina, e o Nexus acha a usina pelo código do texto."""
    novo = dict(CATALOGO[1], id=5, code="CPX100-INVR2.2", label="Inversor 2.2", description="Inversor 2.2 Marca Teste")
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: [dict(x) for x in CATALOGO] + [dict(novo)])
    ia.resposta["j"] = {"cliente": "", "usina": "", "ativo": "inversor 2.2", "titulo": "Inspecionar o ventilador externo",
                        "descricao": "Ventilador externo do inversor.", "tema": "inversor_inspecao"}
    f = ia.post("/os/api/solic/ia/preencher", json={"setor": "pcm", "texto": "o inversor 2.2 de cpx100, ventilador externo"}).get_json()
    assert (f["cliente"], f["usina"], f["ativo"]["id"]) == ("Cliente X", USINA, 5) and f["pronta"]
    assert "%s (CPX100)" % USINA in ia.pedidos[-1]["sistema"]
    assert IA.usina_pelo_codigo("nada aqui", {USINA: "CPX100"}) == ""
