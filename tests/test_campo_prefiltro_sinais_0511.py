"""As quatro regras novas do pré-filtro da Aprovação de OS (Levi, 05/11/2026: "Tempo curto, resposta vazia, GPS fora da
usina, foto faltando / consegue adicionar"; "pode seguir!"). Os fatos vêm da leitura rápida de fundo (os anexos e as
respostas no Fracttal, sem baixar foto) e do tempo de execução da tarefa na fila. Medido nas 30 OS da medição de 26/10
(15 devolvidas, 15 aprovadas), lidas do Fracttal em 05/11:
- tempo curto (App, menos de 120 s com foto): 2 devolvidas, nenhuma aprovada -> Não OK;
- resposta vazia ("N/A", "ok", "sim", "positivo"...): 6 devolvidas e 2 aprovadas -> Não OK com 2 ou mais NA MESMA tarefa
  (1 devolvida, nenhuma aprovada: a aprovada de 13 tarefas tinha um "N/A" em cada uma de 3), Em dúvida com uma por
  tarefa. O "menos de 12 caracteres" do desenho saiu: pegava resposta boa (número de série, "Motor");
- GPS: comparado com as OUTRAS fotos da OS, não com o ponto do cadastro (que deu 12 a 2.058 km em 7 OS cujas fotos batem
  com a tarefa); a 2 km, uma usina grande aprovada caía (2,02 km): 5 km. Fora do Brasil também. 2 devolvidas e 1 aprovada;
- foto faltando ("mínimo N fotos" na pergunta): 2 devolvidas e 2 aprovadas -> só Em dúvida.
Tudo sintético: nada de pessoa nem de usina real."""
from html import unescape

import pytest

from nexus.campo import fracttal, prefiltro, prefiltro_fundo

P = prefiltro.parametros({})
CAMPO_FOTO = ("Registre o estado dos cabos e das conexões do quadro, com a tampa aberta e a etiqueta visível de cada "
              "circuito. Mínimo 3 fotos.")


def _tarefa(id_wt="11", pelo_app=True, exec_s=900, **k):
    return {"id_wt": id_wt, "pelo_app": pelo_app, "qualidade": 95, "foi_devolvida": False, "foto_divergente": False,
            "ronda": False, "falhas": None, "estouro_causa": None, "exec_s": exec_s, "tarefa": "Inspeção do quadro", **k}


def _os(*tarefas):
    return {"os": "1", "tarefas": list(tarefas)}


FATOS = {"chave": "x", "lido_em": 1.0, "anexos": [], "pares": [], "erro": ""}


def _meta(fotos=(), vazias=(), faltando=()):
    return {"v": prefiltro_fundo.META_V, "chave": "x", "lido_em": 1.0, "fotos": list(fotos), "vazias": list(vazias),
            "faltando": list(faltando)}


def _foto(id_, tarefa="11", gps=(-20.1, -47.6), desc="Quadro"):
    return {"id": id_, "tarefa": tarefa, "desc": desc, "gps": list(gps) if gps else None}


def _sub(tarefa, valor, tipo=1, obrigatoria=True, desc="Descreva a atividade realizada"):
    return {"id_work_order_task": int(tarefa), "id_task_form_item_type": tipo, "is_required": obrigatoria, "value": valor,
            "description": desc}


# ── resposta vazia ──────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("valor", ["N/A", "n/a", "Ok", "ok.", "SIM", "Positivo", "Feito", "-"])
def test_resposta_sem_conteudo_e_vazia(valor):
    r = prefiltro.respostas_vazias([_sub(11, valor)], {"11": "Inspeção do quadro"})
    assert [(x["tarefa"], x["valor"]) for x in r] == [("11", valor.strip())]


@pytest.mark.parametrize("valor", ["Motor", "Inversor 6", "QGBT", "A1910293427", "Sem alarme", "Feito inspeção visual no SPDA"])
def test_resposta_curta_com_conteudo_nao_e_vazia(valor):
    """O "menos de 12 caracteres" do desenho saiu: na medição pegava número de série e nome de equipamento."""
    assert prefiltro.respostas_vazias([_sub(11, valor)], {"11": "Inspeção do quadro"}) == []


def test_resposta_igual_ao_nome_da_tarefa_e_vazia():
    assert len(prefiltro.respostas_vazias([_sub(11, "inspecao do QUADRO")], {"11": "Inspeção do quadro"})) == 1


def test_nao_se_aplica_opcional_e_campo_que_nao_e_texto_ficam_de_fora():
    subs = [_sub(11, "Não se aplica"), _sub(11, "ok", obrigatoria=False), _sub(11, "1", tipo=4), _sub(11, "sim", tipo=2),
            _sub(11, ""), _sub(11, None)]
    assert prefiltro.respostas_vazias(subs, {"11": "Inspeção do quadro"}) == []


# ── foto faltando ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_campo_que_pede_minimo_de_fotos_com_menos_falta():
    """O App grava na foto os 80 primeiros caracteres do campo: é por eles que a foto é do campo."""
    fotos = [_foto("a", desc=CAMPO_FOTO[:80]), _foto("b", desc="Descreva a atividade realizada")]
    r = prefiltro.fotos_faltando([_sub(11, "1", tipo=4, desc=CAMPO_FOTO)], fotos)
    assert r == [{"tarefa": "11", "campo": CAMPO_FOTO[:80], "tem": 1, "pede": 3}]


def test_campo_com_as_fotos_pedidas_ou_nao_se_aplica_nao_falta():
    fotos = [_foto(i, desc=CAMPO_FOTO[:80]) for i in "abc"]
    assert prefiltro.fotos_faltando([_sub(11, "1", tipo=4, desc=CAMPO_FOTO)], fotos) == []
    assert prefiltro.fotos_faltando([_sub(11, "1 · foto: não se aplica", tipo=4, desc=CAMPO_FOTO)], []) == []
    assert prefiltro.fotos_faltando([_sub(11, "1", tipo=4, desc="Verificar o quadro")], []) == []


# ── a coluna com as regras novas ────────────────────────────────────────────────────────────────────────────────────
def test_tempo_curto_com_foto_e_nao_ok():
    m = _meta([_foto(str(i)) for i in range(9)])
    r = prefiltro.classificar(_os(_tarefa(exec_s=10)), FATOS, "", P, m)
    assert r["coluna"] == "nao_ok"
    a = next(x for x in r["avisos"] if x["tipo"] == "tempo")
    assert a["nivel"] == "critico" and a["texto"] == "Tarefa executada em 10 s no App, com 9 fotos"
    assert a["tarefas"] == ["11"]


def test_tempo_curto_sem_foto_zero_ou_fora_do_app_nao_dispara():
    fotos = [_foto("1")]
    assert prefiltro.classificar(_os(_tarefa(exec_s=10)), FATOS, "", P, _meta())["coluna"] == "pronta"
    assert prefiltro.classificar(_os(_tarefa(exec_s=0)), FATOS, "", P, _meta(fotos))["coluna"] == "pronta"
    assert prefiltro.classificar(_os(_tarefa(exec_s=None)), FATOS, "", P, _meta(fotos))["coluna"] == "pronta"
    assert prefiltro.classificar(_os(_tarefa(exec_s=120)), FATOS, "", P, _meta(fotos))["coluna"] == "pronta"
    fora = prefiltro.classificar(_os(_tarefa(pelo_app=False, exec_s=10)), None, "", P, _meta(fotos))
    assert not [a for a in fora["avisos"] if a["tipo"] == "tempo"]


def test_varias_tarefas_curtas_num_aviso_so():
    m = _meta([_foto("1", "11"), _foto("2", "12"), _foto("3", "12")])
    r = prefiltro.classificar(_os(_tarefa("11", exec_s=40), _tarefa("12", exec_s=10)), FATOS, "", P, m)
    a = next(x for x in r["avisos"] if x["tipo"] == "tempo")
    assert a["texto"] == "2 tarefas executadas em menos de 2 min no App, com fotos (a mais curta: 10 s, 2 fotos)"
    assert a["tarefas"] == ["12", "11"]


def test_duas_respostas_vazias_e_nao_ok_uma_e_em_duvida():
    vz = [{"tarefa": "11", "campo": "Descreva", "valor": "N/A"}, {"tarefa": "11", "campo": "Observações", "valor": "ok"}]
    r = prefiltro.classificar(_os(_tarefa()), FATOS, "", P, _meta(vazias=vz))
    a = next(x for x in r["avisos"] if x["tipo"] == "vazia")
    assert r["coluna"] == "nao_ok" and a["nivel"] == "critico"
    assert a["texto"] == 'Resposta vazia em 2 campos obrigatórios da mesma tarefa: "N/A", "ok"'
    r1 = prefiltro.classificar(_os(_tarefa()), FATOS, "", P, _meta(vazias=vz[:1]))
    assert r1["coluna"] == "duvida"
    assert next(x for x in r1["avisos"] if x["tipo"] == "vazia")["texto"] == 'Resposta vazia em 1 campo obrigatório: "N/A"'


def test_uma_resposta_vazia_em_cada_tarefa_e_so_em_duvida():
    """Na medição, a MPM aprovada de 13 tarefas tinha um "N/A" em cada uma de 3 delas; a devolvida, quatro numa só."""
    vz = [{"tarefa": t, "campo": "Descreva", "valor": "N/A"} for t in ("11", "12", "13")]
    r = prefiltro.classificar(_os(_tarefa("11"), _tarefa("12"), _tarefa("13")), FATOS, "", P, _meta(vazias=vz))
    a = next(x for x in r["avisos"] if x["tipo"] == "vazia")
    assert r["coluna"] == "duvida" and a["nivel"] == "alerta"
    assert a["texto"] == 'Resposta vazia em 3 campos obrigatórios, um por tarefa: "N/A"'
    vz.append({"tarefa": "11", "campo": "Observações", "valor": "ok"})
    a = next(x for x in prefiltro.classificar(_os(_tarefa("11"), _tarefa("12"), _tarefa("13")), FATOS, "", P,
                                              _meta(vazias=vz))["avisos"] if x["tipo"] == "vazia")
    assert a["nivel"] == "critico" and a["texto"] == 'Resposta vazia em 4 campos obrigatórios (2 na mesma tarefa): "N/A", "ok"'


def test_resposta_vazia_vale_tambem_fora_do_app():
    """As respostas estão no Fracttal para toda OS: a fechada fora do App também é julgada por elas."""
    vz = [{"tarefa": "11", "campo": "c", "valor": "sim"}] * 2
    r = prefiltro.classificar(_os(_tarefa(pelo_app=False)), None, "", P, _meta(vazias=vz))
    assert r["coluna"] == "nao_ok"


def test_gps_fora_do_brasil_e_em_duvida():
    m = _meta([_foto(str(i), gps=(4.6565, -74.0736)) for i in range(3)])
    r = prefiltro.classificar(_os(_tarefa()), FATOS, "", P, m)
    a = next(x for x in r["avisos"] if x["tipo"] == "gps")
    assert r["coluna"] == "duvida" and a["texto"] == "3 fotos com o GPS fora do Brasil"


def test_foto_longe_das_outras_da_os_e_em_duvida():
    perto = [_foto(str(i), gps=(-21.41, -51.57 + i * 0.001)) for i in range(4)]
    longe = [_foto("x", gps=(-20.25, -50.11))]
    r = prefiltro.classificar(_os(_tarefa()), FATOS, "", P, _meta(perto + longe))
    a = next(x for x in r["avisos"] if x["tipo"] == "gps")
    assert r["coluna"] == "duvida" and a["fotos"] == ["x"]
    assert a["texto"] == "1 foto a 199 km das outras fotos da OS"


def test_usina_grande_ate_5_km_nao_dispara_e_tarefa_fora_do_app_nao_conta():
    m = _meta([_foto("1", gps=(-20.0, -47.0)), _foto("2", gps=(-20.0, -47.04)), _foto("3", gps=(-20.0, -47.02)),
               _foto("4", "99", gps=(-10.0, -40.0))])
    r = prefiltro.classificar(_os(_tarefa(), _tarefa("99", pelo_app=False)), FATOS, "", P, m)
    assert not [a for a in r["avisos"] if a["tipo"] == "gps"]


def test_foto_faltando_e_em_duvida():
    falt = [{"tarefa": "11", "campo": "Registre o estado dos cabos", "tem": 1, "pede": 3}]
    r = prefiltro.classificar(_os(_tarefa()), FATOS, "", P, _meta(faltando=falt))
    a = next(x for x in r["avisos"] if x["tipo"] == "foto_faltando")
    assert r["coluna"] == "duvida" and a["nivel"] == "alerta"
    assert a["texto"] == 'Campo pede 3 fotos e tem 1: "Registre o estado dos cabos"'


def test_sem_a_leitura_rapida_a_os_do_app_nao_fica_pronta():
    """Dado pela metade não vai para Pronta: sem as respostas e o GPS lidos, a OS fica em "Ainda conferindo"."""
    assert prefiltro.classificar(_os(_tarefa()), FATOS, "", P, None)["coluna"] == "conferindo"
    assert prefiltro.classificar(_os(_tarefa()), FATOS, "", P, _meta())["coluna"] == "pronta"


def test_fora_do_app_sem_a_leitura_rapida_diz_que_falta_e_nao_entra_no_lote():
    r = prefiltro.classificar(_os(_tarefa(pelo_app=False)), None, "", P, None)
    assert r["coluna"] == "duvida"
    assert [a["texto"] for a in r["avisos"] if a["tipo"] == "faltam"] == ["Faltam as respostas por ler"]


def test_os_do_app_sem_nada_lido_diz_o_que_falta():
    r = prefiltro.classificar(_os(_tarefa(), _tarefa("12", pelo_app=False)), None, "", P, None)
    assert [a["texto"] for a in r["avisos"] if a["tipo"] == "faltam"] == ["Faltam as fotos, as respostas e o GPS por ler"]


def test_os_motivo_das_regras_novas_e_motivo_da_coluna():
    for t in ("tempo", "vazia", "gps", "foto_faltando"):
        assert t in prefiltro.TIPOS_DO_MOTIVO


def test_limites_pelo_config():
    p = prefiltro.parametros({"NEXUS_PREFILTRO_MIN_EXEC_S": "60", "NEXUS_PREFILTRO_GPS_KM": "2"})
    assert p["min_exec_s"] == 60 and p["gps_km"] == 2.0
    assert P["min_exec_s"] == 120 and P["gps_km"] == 5.0


# ── a leitura rápida de fundo ───────────────────────────────────────────────────────────────────────────────────────
class FracttalMeta:
    """O REST de anexos e o de subtarefas, por OS, em páginas de 100."""

    def __init__(self, anexos, subs):
        self.anexos, self.subs, self.pedidos, self.recusar = anexos, subs, [], set()

    def __call__(self, path):
        self.pedidos.append(path)
        folio = path.split("folio=")[1].split("&")[0]
        if folio in self.recusar:
            raise fracttal.Recusado("429")
        fonte = self.anexos if path.startswith("work_orders_attachments") else self.subs
        assert path.startswith(("work_orders_attachments?folio=", "work_orders_subtasks/?folio="))
        start = int(path.split("start=")[1].split("&")[0]) if "start=" in path else 0
        return {"data": fonte.get(folio, [])[start:start + 100]}


def _linha(folio, n=1, fim="2026-10-20T10:00:00", **k):
    return {"id_work_orders_tasks": int(folio) * 10 + n, "id_work_order": int(folio), "wo_folio": str(folio),
            "final_date": fim, "tasks_log_task_type_main": "Corretiva", "description": "Inspeção do quadro", "labels": [],
            **k}


def _anexo(folio, nome, tarefa, desc):
    return {"description": desc, "value": f"https://s3.falso/{folio}/{nome}.jpg?X-Amz-Signature=abc", "type": "image",
            "id_work_order_task": tarefa, "wo_folio": folio}


@pytest.fixture
def rapida(app, tmp_path, monkeypatch):
    app.config.update(NEXUS_DADOS=str(tmp_path), NEXUS_PREFILTRO_PAUSA_S="0.5")
    dormidas = []
    monkeypatch.setattr(prefiltro_fundo, "_dormir", dormidas.append)
    monkeypatch.setattr(prefiltro_fundo, "baixar", lambda url: pytest.fail("a leitura rápida não baixa foto"))
    prefiltro_fundo.limpar()
    yield {"app": app, "dormidas": dormidas, "dados": tmp_path}
    fracttal.usar_fornecedor(None)
    prefiltro_fundo.limpar()


def test_leitura_rapida_guarda_gps_respostas_vazias_e_fotos_faltando(rapida):
    folio, t = "500", 5001
    fx = FracttalMeta(
        {folio: [_anexo(folio, "a", t, CAMPO_FOTO[:80] + " · GPS -20.5,-47.25 · 2026-10-20T09:00:00Z"),
                 _anexo(folio, "b", t, "Descreva a atividade realizada · 2026-10-20T09:01:00Z"),
                 {"description": "laudo", "value": f"https://s3.falso/{folio}/laudo.pdf", "id_work_order_task": t}]},
        {folio: [_sub(t, "N/A"), _sub(t, "1", tipo=4, desc=CAMPO_FOTO), _sub(9999, "ok")]})
    fracttal.usar_fornecedor(fx)
    n = prefiltro_fundo.conferir_meta(rapida["app"], [_linha(folio)], None, {folio: {str(t)}})
    m = prefiltro_fundo.meta(folio)
    assert n == 1 and m["v"] == prefiltro_fundo.META_V
    assert [(f["desc"], f["gps"]) for f in m["fotos"]] == [(CAMPO_FOTO[:80], [-20.5, -47.25]),
                                                          ("Descreva a atividade realizada", None)]
    assert [x["valor"] for x in m["vazias"]] == ["N/A"]            # a subtarefa de outra OS (9999) não entra
    assert m["faltando"] == [{"tarefa": str(t), "campo": CAMPO_FOTO[:80], "tem": 1, "pede": 3}]
    assert len(fx.pedidos) == 2                                    # um pedido de anexos e um de respostas, sem foto


def test_leitura_rapida_le_tambem_a_os_fora_do_app_sem_fotos_faltando(rapida):
    """A OS fechada fora do App é lida (as respostas valem para ela); a foto faltando, não: a foto anexada pelo Fracttal
    não leva o nome do campo."""
    folio, t = "501", 5011
    fx = FracttalMeta({folio: []}, {folio: [_sub(t, "sim"), _sub(t, "1", tipo=4, desc=CAMPO_FOTO)]})
    fracttal.usar_fornecedor(fx)
    prefiltro_fundo.conferir_meta(rapida["app"], [_linha(folio)], None, {folio: set()})
    m = prefiltro_fundo.meta(folio)
    assert [x["valor"] for x in m["vazias"]] == ["sim"] and m["faltando"] == []


def test_leitura_rapida_pula_o_que_esta_fora_e_o_que_ja_leu(rapida):
    fx = FracttalMeta({}, {})
    fracttal.usar_fornecedor(fx)
    linhas = [_linha("502"), _linha("503", tasks_log_task_type_main="Religamento remoto")]
    assert prefiltro_fundo.conferir_meta(rapida["app"], linhas, None, None) == 1
    assert prefiltro_fundo.meta("502") and prefiltro_fundo.meta("503") is None
    antes = len(fx.pedidos)
    assert prefiltro_fundo.conferir_meta(rapida["app"], linhas, None, None) == 0 and len(fx.pedidos) == antes


def test_leitura_rapida_recusada_espera_e_segue(rapida):
    fx = FracttalMeta({}, {})
    fx.recusar = {"504"}
    fracttal.usar_fornecedor(fx)
    n = prefiltro_fundo.conferir_meta(rapida["app"], [_linha("504", fim="2026-10-21T10:00:00"), _linha("505")], None, None)
    assert n == 1 and prefiltro_fundo.meta("504") is None and prefiltro_fundo.meta("505")
    assert prefiltro_fundo.ESPERA_RECUSA_S in rapida["dormidas"]


def test_leitura_rapida_vai_ao_disco_e_volta(rapida):
    fracttal.usar_fornecedor(FracttalMeta({}, {"506": [_sub(5061, "ok")]}))
    prefiltro_fundo.conferir_meta(rapida["app"], [_linha("506")], None, None)
    assert (rapida["dados"] / "campo" / "prefiltro_meta.json.gz").exists()
    prefiltro_fundo.limpar()
    assert prefiltro_fundo.carregar_do_disco(rapida["app"]) and prefiltro_fundo.meta("506")["vazias"][0]["valor"] == "ok"


def test_meta_de_versao_velha_e_relida(rapida):
    fx = FracttalMeta({}, {})
    fracttal.usar_fornecedor(fx)
    prefiltro_fundo._META["507"] = {"v": 0, "chave": "5071", "lido_em": 1e12, "fotos": [], "vazias": [], "faltando": []}
    assert prefiltro_fundo.conferir_meta(rapida["app"], [_linha("507")], None, None) == 1
    assert prefiltro_fundo.meta("507")["v"] == prefiltro_fundo.META_V


# ── na tela: o cartão, a barra lateral e o "!" ─────────────────────────────────────────────────────────────────────
from test_campo_aprovacao_responsavel import _cartao, _coluna, _folios, fila_resp, quadro  # noqa: E402,F401  (fixtures)
from test_campo_aprovacao_supervisor import fila  # noqa: E402,F401  (fixture)


def _meta_16001(**k):
    prefiltro_fundo._META["16001"] = {**_meta(), **k}


def test_na_tela_a_resposta_vazia_poe_em_nao_ok_e_a_barra_mostra_o_campo(quadro, logado):
    _meta_16001(vazias=[{"tarefa": "160011", "campo": "Descreva a atividade realizada", "valor": "N/A"},
                        {"tarefa": "160011", "campo": "Observações", "valor": "ok"}])
    html = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    assert "16001" in _folios(_coluna(html, "nao_ok"))
    assert 'Resposta vazia em 2 campos obrigatórios da mesma tarefa: "N/A", "ok"' in unescape(_cartao(html, "16001"))
    g = unescape(logado.get("/t/campo/aprovacao/16001/detalhe").get_data(as_text=True))
    assert '<b>"N/A"</b> em Descreva a atividade realizada' in g and "Respostas, GPS e fotos pedidas lidos" in g


def test_na_tela_o_tempo_curto_vem_da_fila(quadro, logado):
    """O `real_duration` da tarefa vem na linha do REST que a fila já lê: nenhum pedido a mais."""
    next(w for w in quadro.linhas if w["wo_folio"] == "16001")["real_duration"] = 15
    _meta_16001(fotos=[_foto(str(i), "160011") for i in range(3)])
    html = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    assert "16001" in _folios(_coluna(html, "nao_ok"))
    assert "Tarefa executada em 15 s no App, com 3 fotos" in _cartao(html, "16001")
    g = logado.get("/t/campo/aprovacao/16001/detalhe").get_data(as_text=True)
    assert "executada em 15 s no App, 3 fotos" in g


def test_na_tela_o_gps_longe_vai_para_em_duvida_com_a_distancia(quadro, logado):
    perto = [_foto(str(i), "160011", gps=(-21.41, -51.57)) for i in range(3)]
    _meta_16001(fotos=perto + [_foto("x", "160011", gps=(-20.25, -50.11), desc="Usina ligada")])
    html = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    assert "16001" in _folios(_coluna(html, "duvida"))
    assert "1 foto a 199 km das outras fotos da OS" in _cartao(html, "16001")
    g = logado.get("/t/campo/aprovacao/16001/detalhe").get_data(as_text=True)
    assert "Usina ligada" in g and "km</b> das outras fotos" in g


def test_na_tela_a_foto_faltando_mostra_quantas_de_quantas(quadro, logado):
    _meta_16001(faltando=[{"tarefa": "160011", "campo": "Registre o estado dos cabos", "tem": 1, "pede": 3}])
    html = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    assert "16001" in _folios(_coluna(html, "duvida"))
    g = logado.get("/t/campo/aprovacao/16001/detalhe").get_data(as_text=True)
    assert "<b>1 de 3 fotos</b> · Registre o estado dos cabos" in g


def test_na_tela_sem_a_leitura_rapida_fica_em_ainda_conferindo(quadro, logado):
    prefiltro_fundo._META.pop("16001")
    html = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    c = _cartao(html, "16001")
    assert "Respostas e GPS ainda não conferidos" in c and "16001" not in _folios(_coluna(html, "pronta"))
    assert "respostas e GPS lidos de" in html
