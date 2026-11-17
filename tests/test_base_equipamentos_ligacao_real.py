"""A ligação de verdade na tabela dos inversores de Base > Equipamentos das usinas (17/11/2026).

Levi, numa usina do scadaGridco com duas plantas: "esse ligar aí só aparece que não está ligado no tempo real e não deixa
a pessoa fazer uma ligação real"; "esse na fonte é a mesma coisa que equipamento supervisório [...] o na fonte eu acho que
seria a leitura da fonte em si"; "esse usina supervisório já deve preencher automaticamente".

O caso, com nomes de mentira (o repositório é público) e a forma do dado real: a fonte numera os 20 inversores por planta
(1.1 a 1.10 e 2.1 a 2.10, ids 1 a 21, o 15 sem nome), o cadastro por skid (1.1 a 1.5, 2.1 a 2.5, 3.1 a 3.5, 4.1 a 4.5). A
plataforma liga 1 a 5 e os 2.x da fonte pela tela; os 1.6 a 1.10 ficam com o nome do equipamento, que o cadastro não tem
(as esperadas não vêm: "18 / —" no tempo real). Escolher na coluna gravava só o Equipamento Supervisório do Nexus, que a
plataforma não lê nessa fonte. Agora a escolha vira a decisão do `/api/admin/de-para/decidir` (o livro da plataforma, o
mesmo do editor De-para dela), gravada pelo navegador com o passe da porta única.

A conta (`nexus/static/eq-ligacao.js`) roda no node; a rota do passe e os alvos dos cartões, no Flask."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from nexus.cadastro import depara_fontes as DF
from test_base_equipamentos import JSON_, app_eq, banco, cli, cfg  # noqa: F401 — os fixtures

JS = Path(__file__).resolve().parents[1] / "nexus" / "static" / "eq-ligacao.js"
CHAVE_SSO = "c" * 40
pede_node = pytest.mark.skipif(not shutil.which("node"), reason="sem node nesta máquina")


def _usina_da_fonte():
    """A usina como o `/api/admin/de-para/usina` da plataforma responde numa fonte do scadaGridco."""
    invs = [{"id": str(i), "nome": f"Inversor 1.{i}", "origem": "tela", "na_fonte_hoje": True} for i in range(1, 6)]
    invs += [{"id": str(i), "nome": f"Inversor 1.{i}", "origem": "codigo", "na_fonte_hoje": True} for i in range(6, 11)]
    invs += [{"id": str(10 + k), "nome": f"Inversor 2.{k}", "origem": "tela", "na_fonte_hoje": True} for k in (1, 2, 3, 4)]
    invs += [{"id": "15", "nome": None, "origem": "ordem", "na_fonte_hoje": True},
             {"id": "16", "nome": "Inversor 2.5", "origem": "tela", "na_fonte_hoje": True}]
    invs += [{"id": str(11 + k), "nome": f"Inversor 2.{k}", "origem": "codigo", "na_fonte_hoje": k < 10}
             for k in range(6, 11)]
    alvos = [{"nome": f"Inversor {c}.{n}", "exibicao": None, "esp": 20 if n <= 3 else 18}
             for c in (1, 2, 3, 4) for n in range(1, 6)]
    return {"fonte": "fonte_sg", "id": "usina_exemplo", "edita_inversor": True, "inversores": invs, "alvos": alvos}


def _cartao(sid=7):
    p = DF.pares(_usina_da_fonte(), [])
    return {"fonte": "fonte_sg", "fonte_nome": "Supervisório Exemplo", "plant_id": "usina_exemplo",
            "supervisorio_id": sid, "edita_inversor": True, "erro": "", **p}


def rodar(cena: dict):
    """Roda o eq-ligacao.js no node com a cena e devolve o que a cena pede."""
    prog = r"""
const L = require(process.argv[1]);
const c = JSON.parse(process.argv[2]);
const fs = L.fontesPorChave(c.cartoes);
const f = (fs[c.sid] || [])[0];
const out = {chaves: Object.keys(fs), f: f ? {chave: f.chave, linhas: f.linhas.length, alvos: f.alvos.length} : null};
if (f) {
  out.alvos = (c.inversores || []).map(x => { const a = L.alvoDo(x, f); return a ? a.nome : null; });
  out.efetiva = L.efetiva(f, c.rascunho || {});
  out.decisoes = L.decisoes(f, c.rascunho || {});
}
process.stdout.write(JSON.stringify(out));
"""
    r = subprocess.run(["node", "-e", prog, str(JS), json.dumps(cena)], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# ── os cartões levam o cadastro que a plataforma lê ──────────────────────────────────────────────────────────────────
def test_os_pares_levam_o_cadastro_da_plataforma_na_ordem_dela():
    p = DF.pares(_usina_da_fonte(), [])
    assert [a["nome"] for a in p["alvos"]][:6] == ["Inversor 1.1", "Inversor 1.2", "Inversor 1.3", "Inversor 1.4",
                                                     "Inversor 1.5", "Inversor 2.1"]
    assert len(p["alvos"]) == 20 and p["alvos"][0] == {"nome": "Inversor 1.1", "exibicao": None, "esp": 20}
    # o da fonte com o nome do equipamento que o cadastro não tem fica sem par, e o 15, sem nome, também
    sem = [x["fonte"] for x in p["linhas"] if x["modo"] == "sem"]
    assert sem == ["Inversor 1.6", "Inversor 1.7", "Inversor 1.8", "Inversor 1.9", "Inversor 1.10", "15",
                   "Inversor 2.6", "Inversor 2.7", "Inversor 2.8", "Inversor 2.9", "Inversor 2.10"]


def test_o_lado_da_fonte_e_o_nome_que_a_fonte_da_e_nao_o_decidido():
    """Depois de ligado, a plataforma devolve no `nome` o inversor do CADASTRO ("Inversor 3.1") e no `codigo` o nome do
    equipamento na fonte ("Inversor 2.1"): a coluna mostra o da fonte. Na API PV, o `nome_api` vence os dois."""
    det = {"inversores": [{"id": "11", "nome": "Inversor 3.1", "codigo": "Inversor 2.1", "origem": "tela"},
                          {"id": "15", "nome": None, "codigo": None, "origem": "ordem"},
                          {"id": "48400", "nome": "INVERSOR02", "nome_api": "INVERSOR05", "codigo": None, "origem": "tela"}],
           "alvos": [{"nome": "Inversor 3.1"}, {"nome": "INVERSOR02"}]}
    p = DF.pares(det, [])
    assert [(x["fonte"], (x["alvo"] or {}).get("nome")) for x in p["linhas"]] == [
        ("Inversor 2.1", "Inversor 3.1"), ("15", None), ("INVERSOR05", "INVERSOR02")]


# ── a conta no node ──────────────────────────────────────────────────────────────────────────────────────────────────
@pede_node
def test_so_a_fonte_que_liga_inversor_a_inversor_e_que_foi_lida_entra_na_coluna():
    pelo_nome = {"fonte": "athon", "plant_id": "X", "supervisorio_id": 8, "edita_inversor": False, "linhas": [],
                 "alvos": []}
    sem_leitura = dict(_cartao(9), sem_leitura=True)
    com_erro = dict(_cartao(10), erro="a plataforma não respondeu")
    r = rodar({"cartoes": [_cartao(7), pelo_nome, sem_leitura, com_erro], "sid": 7})
    assert r["chaves"] == ["7"] and r["f"] == {"chave": "fonte_sg|usina_exemplo", "linhas": 21, "alvos": 20}


@pede_node
def test_o_inversor_do_nexus_e_o_do_cadastro_da_plataforma_pelo_supervisorio_e_sem_ele_pelo_nome():
    invs = [{"nome": "Inversor 3.1", "equipamento_supervisorio": ""},
            {"nome": "Qualquer", "equipamento_supervisorio": "inversor  2.2"},     # caixa e espaços não contam
            {"nome": "Inversor 9.9", "equipamento_supervisorio": ""}]             # a plataforma não o conhece
    assert rodar({"cartoes": [_cartao()], "sid": 7, "inversores": invs})["alvos"] == ["Inversor 3.1", "Inversor 2.2", None]


@pede_node
def test_ligar_os_da_fonte_aos_do_cadastro_grava_so_o_que_muda():
    """O par certo pelas strings: a fonte 1.6 a 1.10 (ids 6 a 10) é o 2.1 a 2.5 do cadastro, e a 2.1 a 2.5 (11 a 14 e
    16) é o 3.1 a 3.5. O 2.1 do cadastro, ligado hoje ao id 11, passa ao 6; o 11 vai para o 3.1."""
    rasc = {"Inversor 2.1": "6", "Inversor 3.1": "11"}
    r = rodar({"cartoes": [_cartao()], "sid": 7, "rascunho": rasc})
    assert r["decisoes"] == {"6": "Inversor 2.1", "11": "Inversor 3.1"}
    assert r["efetiva"]["porAlvo"]["Inversor 2.1"] == ["6"] and r["efetiva"]["porAlvo"]["Inversor 3.1"] == ["11"]
    # sem rascunho, nada a gravar
    assert rodar({"cartoes": [_cartao()], "sid": 7})["decisoes"] == {}


@pede_node
def test_o_que_perde_a_ligacao_decidida_na_tela_e_desfeito_e_a_do_codigo_fica():
    # o 2.2 do cadastro (hoje o id 12, decidido na tela) passa ao id 7: o 12 fica sem par e se desfaz ("")
    r = rodar({"cartoes": [_cartao()], "sid": 7, "rascunho": {"Inversor 2.2": "7"}})
    assert r["decisoes"] == {"7": "Inversor 2.2", "12": ""}
    # "sem ligação" no 1.1 (id 1, decidido na tela): desfaz; num alvo que só o código ligaria, nada a mandar
    assert rodar({"cartoes": [_cartao()], "sid": 7, "rascunho": {"Inversor 1.1": ""}})["decisoes"] == {"1": ""}
    assert rodar({"cartoes": [_cartao()], "sid": 7, "rascunho": {"Inversor 4.5": ""}})["decisoes"] == {}


@pede_node
def test_a_ligacao_pelo_nome_que_perde_o_par_nao_manda_desfazer():
    """Na API PV o inversor que casa pelo nome (modo "ok") não tem decisão a desfazer: mandar "" só sujaria o livro."""
    c = {"fonte": "pv", "fonte_nome": "API PV", "plant_id": 1, "supervisorio_id": 7, "edita_inversor": True, "erro": "",
         "linhas": [{"fonte": "INVERSOR01", "id": "101", "modo": "ok", "alvo": {"nome": "INVERSOR01"}},
                    {"fonte": "INVERSOR09", "id": "109", "modo": "sem", "alvo": None}],
         "alvos": [{"nome": "INVERSOR01", "exibicao": "Inversor 1.1", "esp": 20}]}
    r = rodar({"cartoes": [c], "sid": 7, "rascunho": {"INVERSOR01": "109"},
               "inversores": [{"nome": "Inversor 1.1", "equipamento_supervisorio": ""}]})
    assert r["decisoes"] == {"109": "INVERSOR01"} and r["alvos"] == ["INVERSOR01"]


@pede_node
def test_um_inversor_da_fonte_e_um_do_cadastro_o_ultimo_escolhido_vale():
    r = rodar({"cartoes": [_cartao()], "sid": 7, "rascunho": {"Inversor 2.1": "6", "Inversor 2.2": "6"}})
    assert r["efetiva"]["porId"]["6"] == "Inversor 2.2" and "Inversor 2.1" not in r["efetiva"]["porAlvo"]
    # o 2.1 perdeu o 11 (decidido na tela) para ninguém: desfaz
    assert r["decisoes"] == {"6": "Inversor 2.2", "11": "", "12": ""}


# ── a rota do passe ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_passe_para_gravar_a_ligacao_vai_ao_de_para_da_plataforma(app_eq, cli):
    r = cli.post("/t/base/equipamentos/fontes/passe", headers=JSON_)
    assert r.status_code == 409 and "não abre neste servidor" in r.get_json()["motivo"]      # porta desligada
    app_eq.config.update(NEXUS_SSO_CHAVE=CHAVE_SSO)
    r = cli.post("/t/base/equipamentos/fontes/passe", headers=JSON_)
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] and r.headers["Cache-Control"] == "no-store"
    assert j["entrar"] == "/painel/nexus/entrar" and j["decidir"] == "/api/admin/de-para/decidir"
    from test_porta_mapa import _decodificar
    corpo = _decodificar(j["passe"])[0]
    assert corpo["destino"] == "/admin/de-para" and corpo["admin"] is True
    # de outro site, nada
    assert cli.post("/t/base/equipamentos/fontes/passe", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_a_tabela_dos_inversores_tem_o_equipamento_supervisorio_pela_fonte(app_eq, cli):
    cli.post("/t/base/equipamentos/chave", data={"usina": 1, "acao": "ligar", "chave": "Brodowski 1 (90)"})
    html = cli.get("/t/base/equipamentos?usina=1").get_data(as_text=True)
    assert html.index("/static/eq-ligacao.js") < html.index("/static/cadastro-equipamentos.js")
    d = json.loads(html.split('id="eq-dados">')[1].split("</script>")[0])
    assert d["passe_url"] == "/t/base/equipamentos/fontes/passe"
    js = (Path(__file__).resolve().parents[1] / "nexus" / "static" / "cadastro-equipamentos.js").read_text(encoding="utf-8")
    assert "data-na-fonte" not in js and ">Na fonte<" not in js           # a coluna "Na fonte" saiu
    assert "'/api/admin/de-para/decidir'" not in js and '"/api/admin/de-para/decidir"' not in js   # vem do servidor
    assert "redirect: 'manual'" in js and "eq-fontes-reler" in js
