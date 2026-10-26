"""O Criar OS (Tradicional) com o nome de cada ativo no título e o aviso das usinas (Levi, 26/10/2026).

O caso: a OS 16995 (um inversor de uma usina) e a 16996 (um tracker de OUTRA usina) nasceram no mesmo minuto, da mesma
pessoa, com tudo igual e o título "[<código da 1ª usina>] - Inspeção do Inversor com alarme de Ventoinha" nas duas. No
Criar OS o ativo marcado continua marcado quando se troca de usina (como no app de mesa), e a descrição digitada ia igual
para cada OS: o tracker marcado na outra usina levou o título do inversor. Levi escolheu: o ativo entra sozinho no
título de cada OS ("[Ativo] - descrição", como a Nova solicitação, a Performance e o COS) e a tela avisa quando os
marcados são de mais de uma usina.

O clone com o Fracttal e o banco falsos (o `cli` dos testes da Área PCM): nada vai à rede, nada é criado no Fracttal.
Nomes, usinas e códigos de mentira."""
import json

import pytest

from test_oscreator_solic_pcm import WEB, api, cli  # noqa: F401 — `cli` é a fixture do clone com os dublês

from os_web import tradicional_web as trad  # noqa: E402 — o do clone (o import acima pôs o clone no caminho)

INV = {"id": 31, "code": "UTA100-INVR5.1", "description": "Inversor 5.1 Marca X { UTA100-INVR5.1 }",
       "label": "UTA100-INVR5.1 — Inversor 5.1 Marca X", "tipo": "Inversor", "cliente": "Cliente A",
       "usina": "Cliente A - Usina A - UF", "id_parent": 5, "id_type_item": 1, "id_group_task": 9}
TRK = {"id": 41, "code": "UTB100-TRK4.100", "description": "Tracker 4.100 Marca Y { UTB100-TRK4.100 }",
       "label": "UTB100-TRK4.100 — Tracker 4.100 Marca Y", "tipo": "Estrutura Trackers", "cliente": "Cliente B",
       "usina": "Cliente B - Usina B - UF", "id_parent": 7, "id_type_item": 1, "id_group_task": 9}
CORPO = {"ativos": [31, 41], "desc": "Inspeção com alarme de ventoinha", "obs": "",
         "tipo": {"id_main": 5, "desc_main": "Corretiva", "id_priorities": 2, "id_c1": None, "desc_c1": "", "id_c2": None,
                  "desc_c2": ""},
         "etiquetas": [], "subs": ["Descreva a atividade realizada"], "event": "2026-10-21T17:40", "prog": "2026-10-26T08:00",
         "responsavel": {"id_personnel": 77, "name": "Técnico Teste", "code": "T1"}, "os_pai": None, "agrupar": False,
         "finalizar": None}
JS = (WEB / "static" / "tradicional.js").read_text(encoding="utf-8")
HTML = (WEB / "templates" / "tradicional.html").read_text(encoding="utf-8")


@pytest.fixture
def criou(cli, monkeypatch):
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: [dict(INV), dict(TRK)])
    monkeypatch.setattr(api, "_read_asset_cache", lambda: [dict(INV), dict(TRK)])
    visto = []

    def bulk(assets, desc, *a, **k):
        visto.append(("bulk", desc, k))
        return [{"code": x["code"], "ok": True, "os": {"id_task": 1, "id_work_order": 9, "wo_folio": 16995 + i}}
                for i, x in enumerate(assets)]

    def agrupada(assets, desc, *a, **k):
        visto.append(("agrupada", desc, k))
        return {"ok": True, "os": {"id_tasks": [1, 2], "id_work_order": 9, "wo_folio": 16995}, "n_tarefas": 2,
                "n_criadas": 2, "erros": []}
    monkeypatch.setattr(api, "create_work_orders_bulk", bulk)
    monkeypatch.setattr(api, "create_work_orders_agrupada", agrupada)

    def post(**corpo):
        r = cli.post("/os/api/tradicional/criar", data=json.dumps(dict(CORPO, **corpo)), content_type="application/json")
        return r, visto
    return post


@pytest.mark.parametrize("agrupar,caminho", [(False, "bulk"), (True, "agrupada")])
def test_cada_os_leva_o_nome_do_seu_ativo_no_titulo(criou, agrupar, caminho):
    r, visto = criou(agrupar=agrupar)
    assert r.status_code == 200 and r.get_json()["ok"]
    nome, _desc, k = visto[-1]
    assert nome == caminho
    assert k["por_ativo"] == {"UTA100-INVR5.1": {"description": "[Inversor 5.1] - Inspeção com alarme de ventoinha"},
                              "UTB100-TRK4.100": {"description": "[Tracker 4.100] - Inspeção com alarme de ventoinha"}}


def test_o_titulo_escrito_com_o_ativo_nao_repete_e_a_marca_vale(criou):
    _r, visto = criou(ativos=[31], desc="[Inversor 5.1] - Troca da ventoinha")
    assert visto[-1][2]["por_ativo"]["UTA100-INVR5.1"]["description"] == "[Inversor 5.1] - Troca da ventoinha"
    _r, visto = criou(ativos=[31], desc="[Ativo] - Troca da ventoinha")
    assert visto[-1][2]["por_ativo"]["UTA100-INVR5.1"]["description"] == "[Inversor 5.1] - Troca da ventoinha"


def test_o_titulo_de_cada_ativo_e_montado_puro():
    _modo, _args, k, erro = trad.montar_payload(dict(CORPO, ativos=[41]), [INV, TRK])
    assert not erro and k["por_ativo"] == {"UTB100-TRK4.100": {"description": "[Tracker 4.100] - Inspeção com alarme de ventoinha"}}


def test_a_tela_mostra_o_titulo_e_avisa_as_usinas():
    assert 'id="hint_desc"' in HTML and 'id="resp_usinas"' in HTML
    assert "function usinasMarcadas" in JS and "usina: cbUsi.value" in JS        # o marcado guarda a usina dele
    assert "usinas diferentes" in JS                                              # o aviso do Passo 4 e da confirmação


# ── a segunda rodada de 26/10/2026: "Criar OS do zero" ──────────────────────────────────────────────────────────────────
# Levi: "1 - Tirar esses botões de Próximo"; "2 - Ao lado de data do incidente e data programada inclua OS pai";
# "3 - Em etiquetas não precisa ficar mostrando as opções ... o ideal é quando a pessoa for pesquisar aparece a lista";
# "4 - ... troque por Título da tarefa ... [Ativo(APENAS NOME DO ATIVO ... SE FOR O ATIVO DA USINA ENTÃO FICARÁ Usina se
# for inversor ficará Inversor 1.1 ...)] - Título"; "5 - Abaixo de classificação adicione a parte de adicionar o técnico."
USI = {"id": 51, "code": "UTA100", "description": "Cliente A - Usina A - UF  Rodovia de Mentira Km 1", "label":
       "UTA100 — Cliente A - Usina A - UF", "tipo": "Usina", "tipo_code": "USINA", "cliente": "Cliente A",
       "usina": "Cliente A - Usina A - UF", "id_parent": None, "id_type_item": 1, "id_group_task": 9}


def test_o_ativo_da_usina_vira_usina_no_titulo():
    assert trad.nome_no_titulo(USI) == "Usina" and trad.nome_no_titulo(INV) == "Inversor 5.1"
    assert trad.titulo_da_os("Limpeza da subestação", USI) == "[Usina] - Limpeza da subestação"
    _m, _a, k, _e = trad.montar_payload(dict(CORPO, ativos=[51, 31]), [INV, TRK, USI])
    assert k["por_ativo"]["UTA100"] == {"description": "[Usina] - Inspeção com alarme de ventoinha"}
    # a cascata manda o mesmo nome para a prévia da tela
    linhas = {x["code"]: x for x in trad.ativos_de([INV, USI], "Cliente A", "Cliente A - Usina A - UF")}
    assert linhas["UTA100"]["nome_titulo"] == "Usina" and linhas["UTA100-INVR5.1"]["nome_titulo"] == "Inversor 5.1"


def test_a_tela_do_zero_como_o_levi_pediu(cli, monkeypatch):
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: [dict(INV), dict(TRK)])
    h = cli.get("/os/tradicional").get_data(as_text=True)
    assert 'id="b_next1"' not in h and 'id="b_next2"' not in h and "Próximo" not in h and "bNext" not in JS   # 1
    card1 = h.split('id="card1"', 1)[1].split('id="card2"', 1)[0]
    datas = card1.split('class="trad-linha3"', 1)[1]
    assert datas.index('id="dt_prog"') < datas.index('id="dt_exec"') < datas.index('id="ospai_in"')         # 2
    assert 'id="ospai_in"' not in h.split('id="modal_resp"', 1)[1]
    assert '<div class="trad-lista" id="etiq_lista" hidden></div>' in h and "etiqLista.hidden = !txt;" in JS  # 3
    card2 = h.split('id="card2"', 1)[1].split('id="card3"', 1)[0]
    assert "Título da tarefa" in card2 and "Descrição da tarefa" not in h                                    # 4
    assert card2.index('id="cb_c2"') < card2.index('id="resp_busca"') < card2.index('id="resp_lista"')       # 5
    assert 'id="resp_busca"' not in h.split('id="modal_resp"', 1)[1]
    assert "carregarPessoas();" in JS.split("// arranque", 1)[1]
    gerar = JS.split("bDone.onclick = () => {", 1)[1].split("\n  };\n", 1)[0]
    assert "if (!pessoaSel)" in gerar and "ospaiIn.value.trim() && !ospaiSel" in gerar
    assert trad.ERRO_SEM_DESC == "Preencha o Título da tarefa no Passo 2."
