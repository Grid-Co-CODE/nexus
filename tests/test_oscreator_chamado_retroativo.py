"""A OS de acompanhamento RETROATIVA (Nexus > Chamados > Garantias, 20/10/2026). A analista de chamados criou à mão no
Fracttal a OS de acompanhamento de um chamado que já existia na planilha de gestão de chamados, com a nota no jeito dela, e
a tela do chamado mostrou a cadeia e o ativo vazios, a chegada como "hoje" ("nasceu sozinha no fechamento da inspeção") e
nada do histórico. A tela só entendia a nota escrita pelo App ("ninguém cria na mão").

Levi, 20/10/2026, sobre a cadeia: "Nota dela + OS mãe" (a nota como ela escreve; sem cadeia na nota, a OS mãe do
Fracttal); sobre a data no banco: "A abertura do chamado" (a da nota, quando ela traz).

Fracttal FALSO (nada vai à rede). Nomes e números de mentira: o repositório é público."""
import datetime as dt
import sys

import pytest

from nexus.dados import fato_chamado as F
from nexus.dados import fatos as D
from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

from os_web import acomp_web as aw  # noqa: E402

# a nota no jeito em que a analista escreveu a 1ª retroativa (os números, a usina e as pessoas são de mentira)
NOTA_RETRO = (
    "[CHAMADO] Acompanhamento — Huawei · Inversor\n"
    "OS de abertura: 11001 · OS de campo: 12002 · Solicitação: 3003 · Ativo: TESTE-INVR3.3\n"
    "UFV: Usina Teste 100 · Supervisor: Pessoa Exemplo\n"
    "Ticket: SR 90000001 · S/N: XX00000000\n"
    "Data da ocorrência / abertura do chamado: 21/08/2026\n"
    "Status atual: Testes em campo\n"
    "Título do e-mail: SR NO. 90000001 - [Teste][INVERTER] - SN:XX00000000\n"
    "\n"
    "Histórico (importado da Gestão de Chamados V02):\n"
    "21/08 - Chamado aberto\n"
    "22/08 - Fabricante solicitou verificações no equipamento\n"
    "31/08 - Abertura de solicitação 3003 / OS 12002\n"
    "14/10 - Solicitado previsão ao supervisor e ao técnico para darmos seguimento ao chamado")

# a nota que o servidor do App escreve (o formato de sempre, que não pode mudar de leitura)
NOTA_APP = (
    "[CHAMADO] Acompanhamento — Sungrow · Inversor\n"
    "OS de campo: 13001 · Inspeção: 16001 · Ativo: TESTE-INVR1.1\n"
    "Data da falha: 09/09/2026 20:52 · Menos de 7 dias: Não\n"
    "\n"
    "Campos do formulário do fabricante (coletados na inspeção):\n"
    "  problema: não atualiza\n"
    "  serial: 0000TESTE\n"
    "Demais respostas:\n"
    "  Causa da falha: Outra")

HOJE = dt.datetime(2026, 10, 20, 12, 0)


def _linha(nota, data="2026-10-20T14:35:03", folio="16001", **kw):
    d = {"id": 9301, "folio": folio, "cliente": "Cliente Teste", "usina": "Usina Teste", "ativo": "Inversor 3.3",
         "tipo": "Inversor", "tipo_tarefa": "Administrativa", "note": nota,
         "descricao": "[Inversor 3.3] - Acompanhamento de chamado Huawei", "status_id": 1, "status": "Em processo",
         "data": data, "data_fim": "", "atribuido_a": "Analista Teste", "id_atribuido": None}
    d.update(kw)
    return d


# ── a leitura da nota ────────────────────────────────────────────────────────────────────────────────────────────
def test_a_cadeia_da_nota_retroativa_e_lida_mesmo_sem_comecar_por_os_de_campo():
    n = aw.ler_nota(NOTA_RETRO)
    # "OS de abertura" é a OS de campo do App; o "OS de campo" dela, com uma OS de abertura na linha, é a inspeção
    assert (n["os_campo"], n["inspecao"], n["ativo"]) == ("11001", "12002", "TESTE-INVR3.3")
    assert (n["marca"], n["tipo"]) == ("Huawei", "Inversor")


def test_a_data_de_abertura_do_chamado_vem_da_nota_retroativa():
    n = aw.ler_nota(NOTA_RETRO)
    assert n["abertura"] == "21/08/2026"
    # ela escreveu "ocorrência / abertura": vale também como a data da falha, que a nota do App chama assim
    assert n["data_falha"] == "21/08/2026"


def test_o_resto_da_nota_retroativa_aparece_e_nao_e_descartado():
    n = aw.ler_nota(NOTA_RETRO)
    info = {x["rotulo"]: x["valor"] for x in n["info"]}
    assert info["Status atual"] == "Testes em campo"
    assert info["Ticket"] == "SR 90000001" and info["S/N"] == "XX00000000"
    assert info["Título do e-mail"].startswith("SR NO. 90000001")
    assert info["Solicitação"] == "3003" and info["UFV"] == "Usina Teste 100"
    # a cadeia e a data não repetem no bloco: já têm lugar próprio na tela
    assert not {"OS de abertura", "OS de campo", "Ativo", "Data da ocorrência / abertura do chamado"} & set(info)
    assert [(h["data"], h["texto"]) for h in n["historico"]] == [
        ("21/08/2026", "Chamado aberto"),
        ("22/08/2026", "Fabricante solicitou verificações no equipamento"),
        ("31/08/2026", "Abertura de solicitação 3003 / OS 12002"),
        ("14/10/2026", "Solicitado previsão ao supervisor e ao técnico para darmos seguimento ao chamado")]


def test_o_historico_que_vira_o_ano_ganha_o_ano_seguinte():
    nota = ("[CHAMADO] Acompanhamento — Huawei · Inversor\nData da ocorrência / abertura do chamado: 20/12/2025\n"
            "Histórico (importado da Gestão de Chamados V02):\n20/12 - Chamado aberto\n05/01 - Fabricante respondeu")
    assert [h["data"] for h in aw.ler_nota(nota)["historico"]] == ["20/12/2025", "05/01/2026"]


def test_a_nota_do_app_continua_lida_como_antes():
    n = aw.ler_nota(NOTA_APP)
    assert (n["os_campo"], n["inspecao"], n["ativo"]) == ("13001", "16001", "TESTE-INVR1.1")
    assert n["data_falha"] == "09/09/2026 20:52" and n["menos7_nota"] is False
    assert n["abertura"] == "" and n["info"] == [] and n["historico"] == []
    assert [x["chave"] for x in n["campos"]] == ["problema", "serial"]
    assert n["demais"] == [{"pergunta": "Causa da falha", "resposta": "Outra"}]


# ── o cartão e a linha do tempo ──────────────────────────────────────────────────────────────────────────────────
def test_o_chamado_retroativo_conta_a_idade_da_abertura_e_nao_da_criacao_da_os():
    c = aw.cartao(_linha(NOTA_RETRO), "", "", HOJE)
    assert c["retroativa"] is True
    assert c["chegou"] == "21/08/2026" and c["dias"] == 60
    assert c["criada"] == "20/10/2026 11:35"          # 14:35 UTC = 11:35 em Brasília
    assert (c["os_campo"], c["inspecao"], c["code"]) == ("11001", "12002", "TESTE-INVR3.3")


def test_o_chamado_do_app_nao_muda_de_idade():
    c = aw.cartao(_linha(NOTA_APP, data="2026-10-19T14:16:24"), "", "", HOJE)
    assert c["retroativa"] is False and c["chegou"] == "19/10/2026 11:16" and c["dias"] == 1


def test_a_linha_do_tempo_da_retroativa_traz_o_historico_e_nao_diz_que_nasceu_sozinha():
    c = aw.cartao(_linha(NOTA_RETRO), "", "", HOJE)
    obs = [{"quando": "2026-10-20T15:00:00-03:00", "texto": "Cobrado o fabricante", "quem": "Analista Teste",
            "tipo": "obs"}]
    tl = aw.linha_do_tempo(c, obs, aw.ler_nota(NOTA_RETRO)["historico"])
    assert [(e["d"], e["a"]) for e in tl] == [("20/10", "2026"), ("20/10", "2026"), ("14/10", "2026"),
                                              ("31/08", "2026"), ("22/08", "2026"), ("21/08", "2026")]
    assert tl[0]["texto"] == "Cobrado o fabricante" and tl[0]["novo"] is True
    assert "nasceu sozinha" not in " ".join(e["texto"] for e in tl)
    assert "à mão" in tl[1]["texto"] and "21/08/2026" in tl[1]["texto"]
    assert tl[-1]["texto"] == "Chamado aberto" and "importado" in tl[-1]["autor"].lower()
    assert sum(1 for e in tl if e["novo"]) == 1


def test_a_linha_do_tempo_do_app_segue_igual():
    c = aw.cartao(_linha(NOTA_APP, data="2026-10-19T14:16:24"), "", "", HOJE)
    tl = aw.linha_do_tempo(c, [])
    assert len(tl) == 1 and tl[0]["texto"] == "Chegou: a OS 16001 nasceu sozinha no fechamento da inspeção 16001."


def test_sem_cadeia_na_nota_a_os_mae_do_fracttal_entra_pelo_tipo_dela():
    n = aw.ler_nota("[CHAMADO] Acompanhamento — Huawei · Inversor\nStatus atual: aguardando")
    assert aw.cadeia_pela_mae(n, "11001", "Corretiva Emergencial") == {"os_campo": "11001", "inspecao": ""}
    assert aw.cadeia_pela_mae(n, "12002", "Inspeção") == {"os_campo": "", "inspecao": "12002"}
    assert aw.cadeia_pela_mae(n, "", "") == {"os_campo": "", "inspecao": ""}
    # com a cadeia na nota, a nota vale e a OS mãe nem é usada
    assert aw.cadeia_pela_mae(aw.ler_nota(NOTA_APP), "99", "Corretiva") == {"os_campo": "13001", "inspecao": "16001"}


# ── o fato no banco ──────────────────────────────────────────────────────────────────────────────────────────────
def _w(folio, nota, criada, st=1, fim=None):
    return {"wo_folio": str(folio), "id_status_work_order": str(st), "creation_date": criada, "final_date": fim,
            "wo_final_date": fim, "task_note": nota, "groups_1_description": "Usina Teste - XX",
            "code": "TESTE-INVR3.3", "description": "[Inversor 3.3] - Acompanhamento de chamado Huawei",
            "tasks_log_task_type_main": "Administrativa"}


def test_no_banco_o_chamado_retroativo_abre_na_data_da_nota_e_diz_de_onde_veio():
    lig = D.Ligador([], [], [], {})
    out = F.linhas([_w(16858, NOTA_RETRO, "2026-10-20T14:35:03+00:00", st=3, fim="2026-10-21T15:00:00+00:00"),
                    _w(16762, NOTA_APP, "2026-10-19T14:16:24+00:00")], lig, {}, dt.date(2026, 10, 21))
    d = {r[0]: dict(zip(F.CAB_CHAMADO, r)) for r in out}
    assert (d[16858]["data_id_abertura"], d[16858]["abertura_por"]) == (20260821, "nota")
    # a duração conta da abertura (o dia da nota, 00:00 em Brasília) até o fim: 61 dias e 12 h
    assert d[16858]["duracao_min"] == (61 * 24 + 12) * 60
    assert (d[16762]["data_id_abertura"], d[16762]["abertura_por"]) == (20261019, "os")
    # nada da nota vai ao banco além das categorias (a API tem leitura aberta)
    assert "Pessoa Exemplo" not in str(out) and "Testes em campo" not in str(out)


def test_data_da_nota_depois_da_criacao_nao_vale():
    # erro de digitação (abertura "no futuro" da OS): fica a criação, como sempre foi
    nota = NOTA_RETRO.replace("21/08/2026", "21/12/2026")
    out = F.linhas([_w(16858, nota, "2026-10-20T14:35:03+00:00")], D.Ligador([], [], [], {}), {}, dt.date(2026, 10, 21))
    r = dict(zip(F.CAB_CHAMADO, out[0]))
    assert (r["data_id_abertura"], r["abertura_por"]) == (20261020, "os")


@pytest.mark.parametrize("nota", [NOTA_RETRO.replace("21/08/2026", "31/02/2026"), NOTA_RETRO.replace("21/08/2026", "")])
def test_data_estragada_na_nota_nao_quebra(nota):
    assert aw.ler_nota(nota)["abertura"] in ("", "31/02/2026")
    c = aw.cartao(_linha(nota), "", "", HOJE)
    assert c["retroativa"] is False and c["chegou"] == "20/10/2026 11:35"


# ── a tela do chamado ────────────────────────────────────────────────────────────────────────────────────────────
JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
WID, FOLIO, WID_MAE = 9301, 9302, 9303


@pytest.fixture
def tela(monkeypatch):
    """O clone com o Fracttal falso; devolve (cliente, lidos): `lidos` anota cada OS cujo detalhe foi pedido."""
    pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
    import api
    import chamados_obs_store as obs_store
    from os_web import criar_app, rotas
    estado = {"nota": NOTA_RETRO, "mae": {"folio": 11001, "tipo": "Corretiva Emergencial"}, "lidos": []}

    def detalhe(wid):
        estado["lidos"].append(wid)
        if wid == WID_MAE:
            if isinstance(estado["mae"], Exception):
                raise estado["mae"]
            return estado["mae"]
        return {"folio": FOLIO, "subtarefas": [], "notas": estado["nota"], "code": "TESTE-INVR9.9",
                "os_pai_id": WID_MAE}

    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    monkeypatch.setattr(api, "_code_to_loc", lambda: {})
    monkeypatch.setattr(api, "list_chamados", lambda **k: [_linha(estado["nota"], folio=str(FOLIO), id=WID)])
    monkeypatch.setattr(api, "tickets_os3_em_massa", lambda ids: {i: "" for i in ids})
    monkeypatch.setattr(api, "get_os_detalhes", detalhe)
    monkeypatch.setattr(obs_store, "do_os", lambda folio: [])
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Analista Teste", "email": "teste@exemplo.invalid", "perfil": ""}
    yield c, estado
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()


def _pagina(cli):
    r = cli.get("/os/chamados/acompanhamento/%d" % FOLIO)
    assert r.status_code == 200
    return r.get_data(as_text=True)


def test_a_tela_da_retroativa_mostra_a_cadeia_o_ativo_e_o_que_veio_na_nota(tela):
    cli, estado = tela
    h = _pagina(cli)
    cadeia = h.split('<ol class="cadeia">', 1)[1].split("</ol>", 1)[0]
    assert 'href="/os/os/folio/11001"' in cadeia and 'href="/os/os/folio/12002"' in cadeia
    assert '<dt>Ativo</dt><dd class="mono">TESTE-INVR3.3</dd>' in h
    assert "Aberto em" in h and "21/08/2026" in h and "criada em 20/10<" in h
    assert "Testes em campo" in h and "SR NO. 90000001" in h and "Chamado aberto" in h
    assert "nasceu sozinha" not in h
    # a cadeia veio da nota: a OS mãe não foi lida (nenhum pedido a mais ao Fracttal)
    assert WID_MAE not in estado["lidos"]


def test_sem_cadeia_na_nota_a_tela_le_a_os_mae_e_o_ativo_do_fracttal(tela):
    cli, estado = tela
    estado["nota"] = "[CHAMADO] Acompanhamento — Huawei · Inversor\nStatus atual: aguardando o fabricante"
    h = _pagina(cli)
    cadeia = h.split('<ol class="cadeia">', 1)[1].split("</ol>", 1)[0]
    assert 'href="/os/os/folio/11001"' in cadeia.split("</li>", 1)[0]          # a mãe Corretiva é a OS de campo
    assert '<dt>Ativo</dt><dd class="mono">TESTE-INVR9.9</dd>' in h             # o código da própria OS no Fracttal
    assert estado["lidos"].count(WID_MAE) == 1


def test_a_os_mae_que_nao_vem_nao_derruba_a_tela(tela):
    import api
    cli, estado = tela
    estado["nota"] = "[CHAMADO] Acompanhamento — Huawei · Inversor"
    estado["mae"] = api.FracttalError("recusado")
    h = _pagina(cli)
    assert 'href="/os/os/folio/' not in h.split('<ol class="cadeia">', 1)[1].split("</ol>", 1)[0].split('class="aqui"')[0]
