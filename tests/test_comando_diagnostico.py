"""O diagnóstico do dia da IA no prontuário (nexus/comando/diagnostico.py; 14/11/2026, Levi: "Sempre que a pessoa for
abrir o prontuário da usina, abrir o diagnóstico da IA [...] uma pessoa diferente abrir também no mesmo dia, usar o mesmo
diagnóstico [...] Para não ficar gastando token à toa")."""
import json
import os
import time

from test_campo_responsaveis import tela  # noqa: F401  (tela é fixture)
from test_campo_visao import banco  # noqa: F401  (banco é fixture)
from test_comando_ia import DOSSIE

from nexus.comando import diagnostico as DG
from nexus.comando import ia as IA

RESPOSTA = """<diagnostico>{"situacao": "A usina caiu 17 vezes no mês pela oscilação da rede (§4), com a 27 atuando.",
"tem_que_fazer": [{"acao": "Programar a ronda atrasada há 11 dias", "os": null},
                  {"acao": "Cobrar a análise da recorrência da 27", "os": 99999}],
"pode_fazer": ["Pedir à concessionária o registro das oscilações"],
"pendente": [{"item": "Chamado da Brametal sem retorno há 22 dias", "os": null}, {"x": 1}, 7]}</diagnostico>"""


def test_le_o_json_limpa_as_secoes_e_tira_a_os_que_nao_esta_no_dossie():
    d = DG.ler(RESPOSTA, DOSSIE)
    assert d["situacao"] == "A usina caiu 17 vezes no mês pela oscilação da rede, com a 27 atuando."
    assert [x["texto"] for x in d["tem_que_fazer"]] == ["Programar a ronda atrasada há 11 dias",
                                                        "Cobrar a análise da recorrência da 27"]
    assert d["tem_que_fazer"][1]["os"] == ""                       # 99999 não está no dossiê: não vira link
    assert d["pode_fazer"] == [{"texto": "Pedir à concessionária o registro das oscilações", "os": "", "os_tipo": "",
                                "destino": None, "ver": "", "pedido": ""}]
    assert [x["texto"] for x in d["pendente"]] == ["Chamado da Brametal sem retorno há 22 dias"]
    # sem o JSON: None (a tela mostra o texto); o bloco cortado no fim ainda serve
    assert DG.ler("A usina está bem.", DOSSIE) is None and DG.ler('<diagnostico>{"situacao": ""}', DOSSIE) is None
    assert DG.ler('‹diagnostico>{"situacao": "Ok."}', DOSSIE)["situacao"] == "Ok."


def test_um_por_usina_por_dia_e_o_erro_espera_20_minutos(tmp_path, monkeypatch):
    cfg = {"NEXUS_DADOS": str(tmp_path), "OPENROUTER_API_KEY": "k"}
    chamadas = []

    def perguntar(c, ids, dossie, pergunta, *a, **k):
        chamadas.append(ids)
        return [{"id": "nemotron", "rotulo": "Nemotron", "ok": True, "texto": RESPOSTA, "custo_usd": 0}]
    monkeypatch.setattr(IA, "perguntar", perguntar)
    assert DG.disponivel(cfg) and not DG.disponivel({})
    assert DG.guardado(cfg, 54, "2026-11-14") is None and DG.travar(cfg, 54, "2026-11-14")
    assert not DG.travar(cfg, 54, "2026-11-14") and DG.em_andamento(cfg, 54, "2026-11-14")   # o 2º pedido espera
    d = DG.gerar(cfg, 54, DOSSIE, 100, "2026-11-14")
    assert d["ok"] and chamadas == [["nemotron"]] and not DG.em_andamento(cfg, 54, "2026-11-14")
    assert DG.guardado(cfg, 54, "2026-11-14")["diag"]["situacao"].startswith("A usina caiu 17 vezes")
    assert DG.guardado(cfg, 54, "2026-11-15") is None                                         # o dia seguinte é outro
    tela = DG.para_tela(DG.guardado(cfg, 54, "2026-11-14"))
    assert tela["estado"] == "pronto" and tela["rotulo"] == "Nemotron" and tela["data"] == d["gerado_em"][8:10] + "/" + d["gerado_em"][5:7]
    # o erro fica 20 minutos; depois a próxima abertura tenta de novo
    monkeypatch.setattr(IA, "perguntar", lambda *a, **k: [{"id": "nemotron", "ok": False, "erro": "limite de uso"}])
    DG.gerar(cfg, 55, DOSSIE, 0, "2026-11-14")
    assert DG.para_tela(DG.guardado(cfg, 55, "2026-11-14")) == {"estado": "erro", "erro": "limite de uso"}
    arq = tmp_path / "ia" / "diagnosticos" / "2026-11-14" / "55.json"
    velho = json.loads(arq.read_text(encoding="utf-8"))
    velho["ts"] = time.time() - DG.ESPERA_ERRO_S - 1
    arq.write_text(json.dumps(velho), encoding="utf-8")
    assert DG.guardado(cfg, 55, "2026-11-14") is None
    # a trava de um pedido que morreu (o servidor reiniciou) não segura para sempre
    trava = tmp_path / "ia" / "diagnosticos" / "2026-11-14" / "56.andamento"
    trava.write_text("")
    os.utime(trava, (time.time() - DG.TRAVA_MORTA_S - 1,) * 2)
    assert not DG.em_andamento(cfg, 56, "2026-11-14") and DG.travar(cfg, 56, "2026-11-14")


def test_a_rota_faz_uma_vez_e_todos_leem_o_mesmo(tela, logado, monkeypatch, tmp_path):
    logado.application.config.update(NEXUS_DADOS=str(tmp_path), OPENROUTER_API_KEY="k")
    chamadas = []

    def perguntar(c, ids, dossie, pergunta, *a, **k):
        chamadas.append(pergunta)
        assert dossie.startswith("# Dossiê da usina Altair")
        return [{"id": "nemotron", "rotulo": "Nemotron", "ok": True, "texto": RESPOSTA, "custo_usd": 0}]
    monkeypatch.setattr(IA, "perguntar", perguntar)
    # o prontuário traz o lugar do diagnóstico, no lugar da frase do parecer
    h = logado.get("/t/campo/usinas/1").get_data(as_text=True)
    assert 'data-pu-diag="/t/campo/usinas/1/ia/diagnostico"' in h and "data-pu-diag-frase" in h
    assert "<span data-pu-diag-selo>" in h            # o JS troca o título do parecer por "Nexus IA Insights"
    j = logado.get("/t/campo/usinas/1/ia/diagnostico").get_json()
    assert j["estado"] == "pronto" and j["diag"]["tem_que_fazer"][0]["texto"].startswith("Programar a ronda")
    assert chamadas == [DG.PEDIDO]
    # a segunda abertura (a mesma pessoa ou outra) lê o guardado: a IA não é chamada de novo
    assert logado.get("/t/campo/usinas/1/ia/diagnostico").get_json()["estado"] == "pronto" and len(chamadas) == 1
    # a usina que não existe
    assert logado.get("/t/campo/usinas/987654/ia/diagnostico").status_code == 404
    # sem chave de IA nenhuma: fica o parecer
    for k in ("OPENROUTER_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY"):
        logado.application.config.pop(k, None)
    for p in IA.PROVEDORES.values():
        monkeypatch.delenv(p["chave"], raising=False)
    (tmp_path / "ia" / "diagnosticos").rename(tmp_path / "ia" / "antes")
    assert logado.get("/t/campo/usinas/1/ia/diagnostico").get_json() == {"estado": "sem_ia"}


def test_garantia_e_da_performance_e_a_rede_do_cos():
    """14/11/2026, Levi: "Fiquem chamados garantias [...] não existe o setor em si. Ele está dentro da performance"; e
    16/11/2026: "quem cobra é o time de chamados" (no chat também), "se for vincular alguma coisa relacionada a chamados,
    também tem que solicitar o time de chamados"."""
    assert "Os chamados de garantia" in DG.PEDIDO and 'peça a "Chamados"' in DG.PEDIDO and "pedido ao COS" in DG.PEDIDO
    assert 'use o setor "Chamados" quando estiver na lista' in IA.INSTRUCOES
    assert "juntar uma OS a um chamado" in IA.INSTRUCOES and "sem afirmar que não estão" in IA.INSTRUCOES
    assert '"pedir": "Chamados"' in DG.PEDIDO and "Vincular OS ao chamado de garantia" in DG.PEDIDO


def test_os_e_do_tecnico_a_pausa_nao_se_libera_e_a_no_prazo_nao_se_cobra():
    """16/11/2026, Levi, na Marabá 200: o técnico "não usa o Nexus, ele usa o app de campo" (executar OS não é pedido à
    Manutenção); "esse lance da engenharia liberar a tarefa pausada tem que entender o motivo por que foi pausada [...] O
    supervisor realmente tem esse poder de liberar?"; "tarefa não iniciada e que não está atrasada também não entra nesse
    meio do que está parado ou atrasado"."""
    for txt in (IA.INSTRUCOES, DG.PEDIDO):
        assert "é do técnico de campo, que o supervisor coordena" in txt and "nem " in txt
        assert "não libera a pausa" in txt
    assert 'as "no prazo" não são atraso nem pendência' in IA.INSTRUCOES
    assert 'as "no prazo" não entram em lista nenhuma' in DG.PEDIDO


def test_o_pedido_pronto_so_vem_com_o_pedir():
    """16/11/2026, Levi: "solicitar o time de chamados, cobrança de fabricante, STI [...] Tudo isso já pronto": o texto do
    pedido vai na janela da demanda; sem "pedir", nada."""
    setores = [{"setor_id": "2:Chamados", "nome": "Chamados", "temas": [{"tema_id": "t9", "nome": "Cobrança ao fabricante"}]}]
    r = DG.ler('<diagnostico>{"situacao": "Ok.", "pode_fazer": [{"acao": "Cobrar a STI", "destino": {"pedir": "Chamados", '
               '"tema": "Cobrança ao fabricante"}, "pedido": "Cobrar da STI o retorno dos 4 chamados abertos há 87 dias."}, '
               '{"acao": "Ver a lista", "destino": {"ver": "os"}, "pedido": "não vale"}]}</diagnostico>', DOSSIE, setores)
    a, b = r["pode_fazer"]
    assert (a["destino"]["setor_id"], a["destino"]["tema_id"], a["pedido"]) == (
        "2:Chamados", "t9", "Cobrar da STI o retorno dos 4 chamados abertos há 87 dias.")
    assert b["pedido"] == ""


def test_o_texto_do_dossie_nao_abre_um_bloco_de_diagnostico():
    assert IA.neutro("<diagnostico>{}</diagnostico>") == "‹diagnostico>{}‹/diagnostico>"


def test_a_variavel_do_modelo_chega_ao_config():
    from nexus import create_app
    app = create_app({"NEXUS_SECRET_KEY": "x", "NEXUS_SENHA_ADMIN": "y", "NEXUS_IA_DIAGNOSTICO_MODELO": "gemini-lite"})
    assert DG.modelo(app.config) == "gemini-lite" and DG.modelo({}) == "nemotron"


def test_cada_item_tem_o_destino_validado():
    """14/11/2026, Levi: "todos esses tem que ter um botão para dar o destino [...] fazer [...] visualizar [...] solicitar
    ao COS". Só setor da lista e lugar da lista viram botão."""
    setores = [{"setor_id": 3, "nome": "Engenharia"}, {"setor_id": 7, "nome": "COS"}]
    resp = ('<diagnostico>{"situacao": "Ok.", "tem_que_fazer": [], "pode_fazer": ['
            '{"acao": "Solicitar à Engenharia a revisão dos ajustes", "os": null, "destino": {"pedir": "engenharia"}},'
            '{"acao": "Aprovar as 65 OS em verificação", "os": null, "destino": {"ver": "aprovacao"}},'
            '{"acao": "Pedir ao Marketing", "os": null, "destino": {"pedir": "Marketing"}},'
            '{"acao": "Ver o site", "os": null, "destino": {"ver": "http://x"}}],'
            '"pendente": [{"item": "Estabilidade da rede", "os": null, "destino": {"pedir": "COS"}},'
            '{"item": "Análise da Engenharia", "os": null, "destino": {"ver": "Engenharia"}}]}</diagnostico>')
    d = DG.ler(resp, DOSSIE, setores)
    # o setor que não está na lista (Marketing) não vira botão; o 4º item passa do limite de 3
    sem_tema = {"tema_id": "", "tema": ""}
    assert [x["destino"] for x in d["pode_fazer"]] == [dict({"tipo": "pedir", "setor_id": 3, "setor": "Engenharia"}, **sem_tema),
                                                       {"tipo": "ver", "onde": "aprovacao"}, None]
    assert [x["destino"] for x in d["pendente"]] == [dict({"tipo": "pedir", "setor_id": 7, "setor": "COS"}, **sem_tema),
                                                     {"tipo": "ver", "onde": "engenharia"}]
    # o tema do pedir (15/11/2026, Levi: "já preenche PCM porém não preenche o tema"): só tema DO setor; o de outro, não
    com_temas = [{"setor_id": 9, "nome": "PCM", "temas": [{"tema_id": "m00000000001", "nome": "Programação de ronda"}]},
                 {"setor_id": 3, "nome": "Engenharia", "temas": [{"tema_id": "m00000000002", "nome": "Parecer técnico"}]}]
    t = DG.ler('<diagnostico>{"situacao": "Ok.", "tem_que_fazer": ['
               '{"acao": "Programar a ronda", "destino": {"pedir": "PCM", "tema": "programacao de ronda"}},'
               '{"acao": "Pedir o parecer ao PCM", "destino": {"pedir": "PCM", "tema": "Parecer técnico"}}]}</diagnostico>',
               DOSSIE, com_temas)
    assert [(x["destino"]["tema_id"], x["destino"]["tema"]) for x in t["tem_que_fazer"]] == [
        ("m00000000001", "Programação de ronda"), ("", "")]
    assert "TEMAS de cada setor" in DG.lista_de_temas(com_temas) and "- PCM: Programação de ronda" in DG.lista_de_temas(com_temas)
    assert DG.lista_de_temas([{"setor_id": 1, "nome": "COS", "temas": []}]) == ""
    # o "ver" junto do "pedir" (15/11/2026: "além da pessoa clicar em fazer, também poder clicar em ver")
    junto = DG.ler('<diagnostico>{"situacao": "Ok.", "tem_que_fazer": [{"acao": "Conferir os 13 extintores", "os": null, '
                   '"destino": {"pedir": "Engenharia", "ver": "extintores"}}]}</diagnostico>', DOSSIE, setores)
    assert junto["tem_que_fazer"][0]["destino"]["setor"] == "Engenharia" and junto["tem_que_fazer"][0]["ver"] == "extintores"
    assert "Cada assunto numa lista só" in DG.PEDIDO


def test_o_pedido_preenchido_recusa_o_que_nao_e_numero(tela, logado):
    """O setor e a OS do "Fazer" só entram como número (o preenchido de verdade: test_comando_demandas)."""
    h = logado.get("/t/comando/conversa/usina/1/janela?aba=pedir&setor=x&os=1;2").get_data(as_text=True)
    assert "data-pre-setor" not in h and "data-pre-os" not in h


def test_a_frase_traz_as_os_dela_com_o_tipo():
    """15/11/2026, Levi, na Ceilândia 2: "Desligamento ativo [...] a OS não é clicável". A frase leva as OS que o dossiê
    tem, com o tipo (o card no religamento); a OS que não está no dossiê não vira link."""
    dossie = ("## 4. COS\n\n| Início | Tipo | OS |\n| --- | --- | --- |\n| 14/11 | Usina desligada | 19568 |\n\n"
              "## 5. OS e manutenção\n\n- Abertas: OS 17460 (comunicação)\n")
    d = DG.ler('<diagnostico>{"situacao": "Desligamento ativo há 7h (OS 19568), comunicação caída (OS 17460) e OS 99999."}'
               '</diagnostico>', dossie)
    assert d["situacao_os"] == {"19568": "religamento", "17460": "os"}
