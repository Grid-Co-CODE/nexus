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


def test_o_ativo_que_a_usina_nao_tem_vira_aviso_com_os_do_mesmo_grupo(ia):
    """Levi, 15/11/2026: pediu o "inversor 1.5 de SMP100", que não existe (o grupo 1 de lá vai até o 1.4), e a tela só
    perguntava "Em qual ativo"; "poderia ter um aviso ativo x não encontrado"."""
    ia.resposta["j"] = dict(RESPOSTA, ativo="inversor 1.5")
    f = ia.post("/os/api/solic/ia/preencher", json={"setor": "pcm", "texto": "inversor 1.5 da usina teste 1"}).get_json()
    assert f["ativo"] is None and not f["pronta"] and f["tipo"] == "Inversor"
    assert f["avisos"] == ['Ativo "inversor 1.5" não encontrado na Usina Teste 1.'] and f["usina_curta"] == "Usina Teste 1"
    assert f["perguntas"] == ["Qual destes ativos: Inversor 1.1?"]            # o vizinho do grupo 1 vira a opção
    ia.resposta["j"] = dict(RESPOSTA, ativo="inversor 8.2")                    # grupo que não existe: só o aviso
    g = ia.post("/os/api/solic/ia/preencher", json={"setor": "pcm", "texto": "inversor 8.2 da usina teste 1"}).get_json()
    # a usina pelo nome dela, sem o cliente e o estado (Levi: "deixa citando só usina ou só cliente")
    assert g["avisos"] == ['Ativo "inversor 8.2" não encontrado na Usina Teste 1.']
    assert g["perguntas"] == ["Em qual ativo da Usina Teste 1?"]
    ia.resposta["j"] = dict(RESPOSTA, ativo="")                                # a IA não disse ativo: nada a avisar
    assert ia.post("/os/api/solic/ia/preencher", json={"setor": "pcm", "texto": "inspeção na usina teste 1"}).get_json()["avisos"] == []
    js = ia.get("/os/static/solic_ia.js").get_data(as_text=True)
    assert "f.avisos" in js and "sia-erro" in js and "f.usina_curta" in js


def test_os_vizinhos_sao_do_mesmo_grupo_e_em_ordem():
    nomes = ["Inversor 1.10", "Inversor 1.2", "Inversor 2.1", "Disjuntor do Inversor 1.1", "Inversor 1.1", "Inversor 11.1"]
    so = lambda x: x  # noqa: E731
    # o mesmo grupo (o 11.1 não é do grupo 1), em ordem de número (o 1.10 depois do 1.2)
    assert IA.vizinhos("inversor 1.5", nomes, so) == ["Disjuntor do Inversor 1.1", "Inversor 1.1", "Inversor 1.2",
                                                      "Inversor 1.10"]
    assert [IA._ordem(n) for n in IA.vizinhos("inversor 1.5", nomes, so)] == [[1, 1], [1, 1], [1, 2], [1, 10]]
    assert IA.vizinhos("inversor 5", nomes, so) == [] and IA.vizinhos("inversor 9.1", nomes, so) == []
    assert IA.vizinhos("", nomes, so) == []


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
    ok = IA.chamar("k", "s", "u", post=lambda *a, **k: R(200, {"model": "google/gemma-4-31b-it", "choices": [{"message": {"content": "<think>hm</think>{}"}}]}))
    assert ok["texto"] == "{}" and ok["modelo"] == "google/gemma-4-31b-it" and ok["segundos"] >= 0


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
    f = ia.post("/os/api/solic/ia/preencher", json={"setor": "pcm", "texto": "inspeção no inversor 1.1"}).get_json()
    assert f["tema"] == "" and [s["desc"] for s in f["subtarefas"]] == ["Descreva a atividade realizada"]
    assert [t["chave"] for t in f["temas"]] == ["inversor_inspecao"] and f["com_subtarefas"] is True


def test_na_engenharia_e_na_performance_a_ia_nao_inventa_tema_nem_subtarefa(ia):
    """Levi, 15/11/2026: "quando vou para performance ou engenharia e escrevo um prompt ele abre subtarefa do nada, se não
    tem a opção acho que ele não deveria inventar". A tela delas não tem tema nem subtarefas: a ficha não traz, a IA nem
    recebe a lista de temas, e o criar não manda subtarefa mesmo se vier no corpo."""
    for setor in ("performance", "engenharia"):
        f = ia.post("/os/api/solic/ia/preencher", json={"setor": setor, "texto": "baixa performance no inversor 1.1"}).get_json()
        assert f["ativo"]["id"] == 2 and f["responsavel"] is True
        assert f["tema"] == "" and f["subtarefas"] == [] and f["temas"] == [] and f["com_subtarefas"] is False
        sistema = ia.pedidos[-1]["sistema"]
        assert "inversor_inspecao" not in sistema and '"subtarefas"' not in sistema and '"tema"' not in sistema
    ia.post("/os/api/solic/ia/preencher", json={"setor": "pcm", "texto": "inspeção no inversor 1.1"})
    assert '"subtarefas"' in ia.pedidos[-1]["sistema"] and "inversor_inspecao" in ia.pedidos[-1]["sistema"]
    for url in ("/os/solicitacao/engenharia", "/os/solicitacao/performance"):
        h = ia.get(url).get_data(as_text=True)
        assert "ia_subs" not in h and "Subtarefas" not in h, url
    js = ia.get("/os/static/solic_eng.js").get_data(as_text=True)
    assert "iaSubs" not in js and "dados.subtarefas" not in js


def test_o_que_falta_vira_pergunta(ia):
    ia.resposta["j"] = {"cliente": "Cliente X", "titulo": "Trocar o fusível", "descricao": "Queimou."}
    f = ia.post("/os/api/solic/ia/preencher", json={"setor": "engenharia", "texto": "trocar o fusível"}).get_json()
    assert f["cliente"] == "Cliente X" and f["usina"] == "" and f["perguntas"][0] == "Em qual usina?" and not f["pronta"]
    # a resposta da pessoa vai com a ficha de antes
    ia.post("/os/api/solic/ia/preencher", json={"setor": "engenharia", "texto": "na usina teste 1", "anterior": f["anterior"]})
    assert "Trocar o fusível" in ia.pedidos[-1]["usuario"] and "na usina teste 1" in ia.pedidos[-1]["usuario"]


def test_o_responsavel_e_o_evento_saem_do_pedido_e_o_que_falta_vira_pergunta(ia):
    """Levi, 15/11/2026: "os campos em aberto poderiam ser perguntados lá em cima. Então, assim, quem é o responsável? A
    pessoa vai digitar o nome. Quando foi o evento?"; e "pedir para o Fulano fazer uma inspeção" sem o Fulano marcado."""
    ontem = dt.datetime.now(IA.BRT) - dt.timedelta(days=1)
    ia.resposta["j"] = dict(RESPOSTA, responsavel="a Ana", evento=ontem.strftime("%Y-%m-%d 15:00"))
    f = ia.post("/os/api/solic/ia/preencher", json={"setor": "engenharia", "texto": "pede para a Ana o inversor 1.1"}).get_json()
    assert f["responsavel_escolhido"] == {"id_personnel": 501, "name": "Ana Teste Silva"}
    assert f["evento"] == ontem.strftime("%Y-%m-%dT15:00") and f["pronta"] and f["perguntas"] == []
    # a lista da equipe não vai à IA: só o pedido, com o nome que a pessoa escreveu
    sistema = ia.pedidos[-1]["sistema"]
    assert '"responsavel"' in sistema and '"evento"' in sistema and "Agora é" in sistema
    assert "Ana Teste Silva" not in sistema and "Bruno Souza" not in sistema
    # sem o responsável e sem o evento: as duas perguntas lá em cima, e a ficha não fica pronta
    ia.resposta["j"] = dict(RESPOSTA)
    g = ia.post("/os/api/solic/ia/preencher", json={"setor": "engenharia", "texto": "o inversor 1.1"}).get_json()
    assert g["perguntas"] == ["Quem é o responsável?", "Quando foi o evento? Sem resposta, fica o horário de agora."]
    assert g["responsavel_escolhido"] is None and g["evento"] == "" and not g["pronta"]
    # a resposta vale junto do que a tela já tinha: o responsável escolhido à mão e o evento ficam
    anterior = {"responsavel": "Bruno Souza", "evento": ontem.strftime("%Y-%m-%dT09:30")}
    h = ia.post("/os/api/solic/ia/preencher", json={"setor": "engenharia", "texto": "título mais curto",
                                                     "anterior": anterior}).get_json()
    assert h["responsavel_escolhido"]["id_personnel"] == 502 and h["evento"] == ontem.strftime("%Y-%m-%dT09:30")
    # quem não é da equipe vira aviso; o evento no futuro não vale
    amanha = dt.datetime.now(IA.BRT) + dt.timedelta(days=2)
    ia.resposta["j"] = dict(RESPOSTA, responsavel="Zeca", evento=amanha.strftime("%Y-%m-%d 10:00"))
    k = ia.post("/os/api/solic/ia/preencher", json={"setor": "engenharia", "texto": "para o Zeca"}).get_json()
    assert k["avisos"][0] == '"Zeca" não está na equipe da Engenharia.' and "no futuro" in k["avisos"][1]
    assert k["perguntas"][0] == "Quem é o responsável?" and k["evento"] == ""
    # o PCM não tem responsável nem evento na tela: nada disso vai à IA nem vira pergunta
    ia.resposta["j"] = dict(RESPOSTA)
    m = ia.post("/os/api/solic/ia/preencher", json={"setor": "pcm", "texto": "o inversor 1.1"}).get_json()
    assert m["perguntas"] == [] and m["pronta"] and '"responsavel"' not in ia.pedidos[-1]["sistema"]
    js = ia.get("/os/static/solic_eng.js").get_data(as_text=True)
    assert "f.responsavel_escolhido" in js and "f.evento" in js and "await cargaResp" in js
    # as perguntas viram campos (resposta ao lado, Tab, Enter envia) e cada resposta vai com a pergunta dela
    barra = ia.get("/os/static/solic_ia.js").get_data(as_text=True)
    assert "mostrarPerguntas(f.perguntas" in barra and 'data-pergunta' in barra and "concat(respostas())" in barra


def test_o_nome_da_pessoa_casa_pela_equipe():
    equipe = [{"id_personnel": 1, "name": "Ana Teste Silva"}, {"id_personnel": 2, "name": "Ana Outra Lima"},
              {"id_personnel": 3, "name": "Bruno Souza"}]
    assert IA.responsavel_da_pista("para o Bruno", equipe)[0]["id_personnel"] == 3
    assert IA.responsavel_da_pista("Ana Teste", equipe)[0]["id_personnel"] == 1
    achado, cand = IA.responsavel_da_pista("Ana", equipe)              # duas Anas: a pessoa escolhe
    assert achado is None and {x["id_personnel"] for x in cand} == {1, 2}
    assert IA.responsavel_da_pista("Anna", equipe) == (None, [])       # parecido demais com ninguém: nenhuma opção
    assert IA.responsavel_da_pista("", equipe) == (None, [])
    agora = dt.datetime(2026, 11, 15, 19, 0, tzinfo=IA.BRT)
    assert IA.evento_do_pedido("2026-11-14", agora)[0] == dt.datetime(2026, 11, 14, 8, 0, tzinfo=IA.BRT)
    assert IA.evento_do_pedido("2026-11-15T07:10", agora)[0] == dt.datetime(2026, 11, 15, 7, 10, tzinfo=IA.BRT)
    assert IA.evento_do_pedido("ontem", agora) == (None, "") and IA.evento_do_pedido("", agora) == (None, "")
    assert IA.evento_do_pedido("2026-11-16 08:00", agora)[0] is None


def test_sem_a_chave_a_tela_diz_e_nada_vai_a_ia(ia, monkeypatch):
    monkeypatch.setattr(IA, "CHAVE", None)
    r = ia.post("/os/api/solic/ia/preencher", json={"setor": "pcm", "texto": "qualquer"})
    assert r.status_code == 503 and r.get_json()["sem_chave"] and not ia.pedidos
    h = ia.get("/os/solicitacao").get_data(as_text=True)            # sem a chave, a tela é a de sempre
    assert 'id="sia"' not in h and "data-sia-abrir" not in h and "solic_ia.js" not in h
    assert ia.post("/os/api/solic/ia/preencher", json={"setor": "x", "texto": "a"}).status_code == 400


def test_a_os_da_ia_na_engenharia_vai_com_6_dias_e_sem_subtarefa(cli):
    subs = [{"desc": "Medir a isolação", "tipo": "num", "anexo": True}]
    r = cli.post("/os/api/solicitacao/engenharia/criar", json=_corpo(ativos=[2], origem="ia", subtarefas=subs))
    assert r.status_code == 200
    assert cli.feito["subtasks"] == [] and cli.feito["prog_date"] == IA.programada(dt.datetime.now(IA.BRT))
    # Urgente na tela do Pedir com IA: vale a data da Urgente, não os 6 dias
    cli.post("/os/api/solicitacao/engenharia/criar", json=_corpo(ativos=[2], origem="ia", subtarefas=subs, urgente=True))
    assert cli.feito["subtasks"] == [] and cli.feito["prog_date"] < IA.programada(dt.datetime.now(IA.BRT))
    # a tela de sempre segue sem subtarefas e com os 7 dias, mesmo se mandar as subtarefas
    cli.post("/os/api/solicitacao/engenharia/criar", json=_corpo(ativos=[2], subtarefas=subs))
    assert cli.feito["subtasks"] == [] and cli.feito["prog_date"] > IA.programada(dt.datetime.now(IA.BRT))


def test_a_caixa_de_texto_mora_na_tela_de_sempre_das_tres(ia):
    """Levi, 15/11/2026: "ao clicar Pedir para a IA aparece uma caixa de texto, tudo é preenchido dentro da tela original
    mesmo e caso a pessoa precise adicionar algo ela pode pedir novamente alguma mudança"; "crie um botão Limpar"."""
    for url, setor in (("/os/solicitacao", "pcm"), ("/os/solicitacao/engenharia", "engenharia"),
                       ("/os/solicitacao/performance", "performance")):
        h = ia.get(url).get_data(as_text=True)
        for s in ('id="sia" hidden', 'data-setor="%s"' % setor, "data-sia-abrir", 'id="sia_limpar"', ">Limpar<",
                  "daqui a 6 dias", "solic_ia.js", "solic_ia.css"):
            assert s in h, (url, s)
        # o que falta, uma pergunta por linha com a resposta ao lado (Levi: "apertando tab para passar a linha")
        assert 'id="sia_perguntas"' in h, url
        # a dica diz o que a tela recebe: tema e subtarefas só no PCM
        assert ("com o tema e as subtarefas" in h) == (setor == "pcm") and ("o responsável e a data" in h) == (setor != "pcm")
        # a caixa fica no alto da tela de sempre, antes do 1º campo; a janela e a ficha de antes não existem mais
        assert h.index('id="sia"') < h.index('id="cb_cli') and "sia_veu" not in h and "sia_ficha" not in h
    assert "window.SolicForm" in ia.get("/os/solicitacao").get_data(as_text=True)          # o PCM preenche pela tela
    r = ia.get("/os/solicitacao/ia")                                    # o cartão do Início: a do PCM, com a caixa aberta
    assert r.status_code == 302 and r.headers["Location"].endswith("/os/solicitacao?ia=1")


def test_em_teste_so_quem_a_ponte_libera_ve_e_usa(ia):
    """No ar em teste (Levi, 15/11/2026: "uma janela de teste no Nexus pra gente testar"): a ponte marca o pedido; sem a
    liberação, a Nova solicitação é a de sempre e o preencher recusa sem ir à IA."""
    fora = {"os_web.ia_liberada": False}
    h = ia.get("/os/solicitacao", environ_overrides=fora).get_data(as_text=True)
    assert 'id="sia"' not in h and "data-sia-abrir" not in h
    r = ia.post("/os/api/solic/ia/preencher", json={"setor": "pcm", "texto": "x"}, environ_overrides=fora)
    assert r.status_code == 403 and "em teste" in r.get_json()["erro"] and not ia.pedidos
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


def test_o_tipo_de_equipamento_sai_do_pedido():
    """Levi, 15/11/2026: "Se eu pedi a inspeção de inversor então o tipo de equipamento dos ativos já devem vir filtrado
    como inversor"."""
    tipos = [{"sigla": "INV", "nome": "Inversor"}, {"sigla": "DJ", "nome": "Disjuntor"}, {"sigla": "SB", "nome": "String Box"}]
    assert IA.tipo_da_pista("inversor 2.1", tipos) == "INV"
    assert IA.tipo_da_pista("Inspeção dos inversores", tipos) == "INV"
    assert IA.tipo_da_pista("disjuntor do inversor 1.1", tipos) == "DJ"        # o equipamento é o que vem primeiro
    assert IA.tipo_da_pista("string box 3", tipos) == "SB"
    assert IA.tipo_da_pista("limpeza dos módulos", tipos) == "" and IA.tipo_da_pista("", tipos) == ""
    assert IA.tipo_da_pista("inversor 2", [{"sigla": "IC", "nome": "Inversor Central"}]) == "IC"


def test_o_tipo_do_pedido_vai_para_a_tela(ia):
    f = ia.post("/os/api/solic/ia/preencher", json={"setor": "pcm", "texto": "inspeção no inversor 1.1"}).get_json()
    assert f["tipo"] == "Inversor" and f["tipo_nome"] and f["ativo"]["id"] == 2
    # sem o ativo, o tipo sai do pedido (a IA disse "tipo"), e a tela filtra a tabela por ele
    ia.resposta["j"] = dict(RESPOSTA, ativo="", tipo="inversores")
    g = ia.post("/os/api/solic/ia/preencher", json={"setor": "pcm", "texto": "inspeção nos inversores"}).get_json()
    assert g["ativo"] is None and g["tipo"] == "Inversor" and g["tema"] == "inversor_inspecao"   # o tema vale pelo tipo


def test_a_usina_sem_o_cliente_traz_o_cliente(ia):
    ia.resposta["j"] = {"usina": "usina teste 1", "ativo": "inversor 1.1", "titulo": "Inspecionar o inversor",
                        "descricao": "Desliga à tarde."}
    f = ia.post("/os/api/solic/ia/preencher", json={"setor": "pcm", "texto": "inversor 1.1 da usina teste 1"}).get_json()
    assert (f["cliente"], f["usina"], f["ativo"]["id"], f["tipo"]) == ("Cliente X", USINA, 2, "Inversor") and f["pronta"]


def test_o_modelo_fora_do_ar_nao_prende_o_pedido():
    """Levi, 15/11/2026, na 2ª prova no ar: "demorando que só". O Nemotron grátis estava de pé 13% da meia hora e o pedido
    esperava até 90 s por ele. Agora vão os três modelos ao OpenRouter (ele passa ao seguinte quando um cai), cada tentativa
    espera no máximo TEMPO_S, e o que não respondeu vai para o fim da fila na 2ª tentativa."""
    import requests

    class R:
        status_code = 200

        def json(self):
            return {"model": "nvidia/nemotron-3.5-super-vl", "choices": [{"message": {"content": "{}"}}],
                    "usage": {"prompt_tokens": 2600, "completion_tokens": 310, "completion_tokens_details": {"reasoning_tokens": 0}}}
    enviados = []

    def post(url, json=None, timeout=None, headers=None):
        enviados.append({"model": json["model"], "models": list(json["models"]), "timeout": timeout,
                         "reasoning": json.get("reasoning")})
        if len(enviados) == 1:
            raise requests.Timeout()
        return R()
    r = IA.chamar("k", "s", "u", post=post)
    assert r["texto"] == "{}" and r["modelo"] == "nvidia/nemotron-3.5-super-vl"
    assert r["tokens"] == {"entrada": 2600, "saida": 310, "raciocinio": 0}
    assert enviados[0]["models"] == list(IA.MODELOS) and enviados[0]["model"] == IA.MODELOS[0]
    assert enviados[1]["models"] == list(IA.MODELOS[1:]) + [IA.MODELOS[0]]           # o que não respondeu foi para o fim
    assert all(e["timeout"] == (10, IA.TEMPO_S) for e in enviados) and IA.TEMPO_S * IA.TENTATIVAS <= 90
    # sem raciocínio (Levi: "demorou 26 segundos"; 14,2 dos 14,6 s eram a IA): o pedido é preencher um JSON
    assert all(e["reasoning"] == {"effort": "none"} for e in enviados)
    # nenhum respondeu: a tela diz em quanto tempo desistiu, sem esperar mais

    def nunca(*a, **k):
        raise requests.Timeout()
    assert "não respondeu em %d s" % (IA.TEMPO_S * IA.TENTATIVAS) in IA.chamar("k", "s", "u", post=nunca)["erro"]


def test_a_ficha_diz_qual_modelo_respondeu_e_em_quanto_tempo(ia, monkeypatch):
    monkeypatch.setattr(IA, "chamar", lambda *a, **k: {"texto": json.dumps(RESPOSTA), "modelo": "google/gemma-4-31b-it",
                                                        "segundos": 3.4})
    f = ia.post("/os/api/solic/ia/preencher", json={"setor": "pcm", "texto": "inversor 1.1"}).get_json()
    assert f["ia_info"] == {"modelo": "google/gemma-4-31b-it", "segundos": 3.4, "tokens": {}}
