"""Garantias, os pedidos do Levi de 27/10/2026:
1 - "Gostaria de poder mudar os status, pode ter essas opções" (a lista que a analista de chamados mandou: Testes em
    campo, Aguardando retorno do Cliente, do Supervisor, do Fabricante, Pré - Operação, Aguardando Abertura de OS,
    Standby e Aguardando coleta do equipamento defeituoso, e a linha em branco);
2 - "Em garantias quero uma visão de tabela o mais enxuta e direta possível";
3 - "não quero as OSs quebrando para os lados, pode quebrar o texto" (o ticket longo no cartão fazia a coluna rolar para
    o lado);
4 - "Em dados inclua um 'Criado por' na parte de acompanhamento e data da criação da OS tbm".

O status mora no banco da Gridco, como as observações (`chamados_obs_store`, tipo "status": uma linha por troca, com
quem e quando); o atual é o da última troca, e sem troca nenhuma vale o "Status atual" escrito na nota da retroativa.

Fracttal e banco FALSOS (nada vai à rede). Nomes e números de mentira: o repositório é público."""
import sys
from pathlib import Path

import pytest

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

from os_web import acomp_web as aw  # noqa: E402

CSS = Path(ponte.RAIZ_CLONE) / "os_web" / "static" / "chamados.css"
JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
OPCOES = ["Testes em campo", "Aguardando retorno do Cliente", "Aguardando retorno do Supervisor",
          "Aguardando retorno do Fabricante", "Aguardando retorno Pré - Operação", "Aguardando Abertura de OS",
          "Standby", "Aguardando coleta do equipamento defeituoso"]
NOTA_RETRO = ("[CHAMADO] Acompanhamento — Huawei · Inversor\nOS de abertura: 11001 · OS de campo: 12002\n"
              "Status atual: Testes em campo\nData da ocorrência / abertura do chamado: 21/08/2026")


# ── 1: as opções e o status atual ───────────────────────────────────────────────────────────────────────────────
def test_as_opcoes_sao_as_da_analista_de_chamados():
    assert list(aw.STATUS_CHAMADO) == OPCOES


def test_o_status_atual_e_o_da_ultima_troca_e_sem_troca_o_da_nota():
    n = aw.ler_nota(NOTA_RETRO)
    assert aw.status_atual("Standby", n) == "Standby"
    assert aw.status_atual(None, n) == "Testes em campo"                 # nunca trocado: o da nota da retroativa
    assert aw.status_atual("", n) == ""                                  # trocado para "sem status": vale a troca
    assert aw.status_atual(None, aw.ler_nota("")) == ""


def test_o_banco_guarda_o_status_e_diz_o_ultimo_de_cada_os(monkeypatch):
    import chamados_obs_store as obs_store
    assert "status" in obs_store.TIPOS
    linhas = [{"id": "a", "quando": "2026-10-20T10:00:00-03:00", "os": "9103", "tipo": "status",
               "texto": "Status: Standby", "extra": {"status": "Standby"}},
              {"id": "b", "quando": "2026-10-21T10:00:00-03:00", "os": "9103", "tipo": "obs", "texto": "x", "extra": {}},
              {"id": "c", "quando": "2026-10-22T10:00:00-03:00", "os": "9104", "tipo": "status",
               "texto": "Status retirado", "extra": {"status": ""}}]
    monkeypatch.setattr(obs_store, "listar", lambda forcar=False: linhas)
    assert obs_store.status_por_os() == {"9103": "Standby", "9104": ""}


# ── a tela e a gravação ─────────────────────────────────────────────────────────────────────────────────────────
def _linha(i, folio, nota="", status=1, criada="2026-10-20T13:00:00"):
    return {"id": i, "folio": str(folio), "cliente": "Cliente Teste", "usina": "Usina Teste", "ativo": "Inversor 1.1",
            "tipo": "Inversor", "tipo_tarefa": "Administrativa", "note": nota,
            "descricao": "[Inversor 1.1] - Acompanhamento de chamado Huawei", "status_id": status, "status": "",
            "data": criada, "data_fim": "", "atribuido_a": "Analista Teste", "id_atribuido": None,
            "criado_por": "Pessoa Que Criou"}


@pytest.fixture
def tela(monkeypatch):
    pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
    import api
    import chamados_obs_store as obs_store
    from os_web import criar_app, rotas
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    linhas = [_linha(1, 9103, NOTA_RETRO), _linha(2, 9104), _linha(3, 9105, status=3)]
    banco = []
    monkeypatch.setattr(api, "_code_to_loc", lambda: {})
    monkeypatch.setattr(api, "list_chamados", lambda **k: [dict(l) for l in linhas])
    monkeypatch.setattr(api, "total_chamados", lambda de=None: 3)
    monkeypatch.setattr(api, "tickets_os3_em_massa",
                        lambda ids: {i: ("TCU com problema na bateria - TCU 80 / Tracker 17.107 (MAC ZM0013A0000000)"
                                         if i == 2 else "") for i in ids})
    monkeypatch.setattr(api, "get_os_detalhes",
                        lambda wid: {"folio": 9100 + 2 + wid, "notas": linhas[wid - 1]["note"], "code": "TESTE-INVR1.1",
                                     "subtarefas": [], "criado_por": "Pessoa Que Criou", "status_id": linhas[wid - 1]["status_id"]})
    monkeypatch.setattr(obs_store, "listar", lambda forcar=False: list(banco))

    def adicionar(folio, texto, tipo="obs", **k):
        reg = {"id": "r%d" % len(banco), "quando": "2026-10-27T10:00:00-03:00", "os": str(folio), "tipo": tipo,
               "texto": texto, "quem": k.get("quem", ""), "email": "", "ativo": k.get("ativo", ""),
               "extra": dict(k.get("extra") or {})}
        banco.append(reg)
        return reg
    monkeypatch.setattr(obs_store, "adicionar", adicionar)
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Analista Teste", "email": "teste@exemplo.invalid", "perfil": ""}
    yield c, banco
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()


def test_a_tela_do_chamado_tem_o_status_com_as_opcoes_e_o_atual_marcado(tela):
    c, _ = tela
    h = c.get("/os/chamados/acompanhamento/9103").get_data(as_text=True)
    caixa = h.split('data-status-caixa', 1)[1].split("</section>", 1)[0]
    assert '<option value="">Sem status</option>' in caixa
    for o in OPCOES:
        assert ">%s</option>" % o in caixa
    assert '<option value="Testes em campo" selected>Testes em campo</option>' in caixa   # o da nota
    assert 'id="b_status"' in caixa


def test_trocar_o_status_grava_no_banco_e_aparece_no_quadro_e_na_linha_do_tempo(tela):
    c, banco = tela
    r = c.post("/os/api/acomp/9104/status", json={"status": "Aguardando retorno do Fabricante", "wid": 2})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert [(b["os"], b["tipo"], b["texto"], b["extra"]) for b in banco] == \
        [("9104", "status", "Status: Aguardando retorno do Fabricante", {"status": "Aguardando retorno do Fabricante"})]
    h = c.get("/os/chamados/acompanhamento/9104").get_data(as_text=True)
    assert '<option value="Aguardando retorno do Fabricante" selected>' in h
    assert "Status: Aguardando retorno do Fabricante" in h.split('id="tl"', 1)[1]
    q = c.get("/os/chamados/acompanhamento").get_data(as_text=True)
    cartao = q.split('href="/os/chamados/acompanhamento/9104"', 1)[1].split("</a>", 1)[0]
    assert '<span class="k-chip k-st">Aguardando retorno do Fabricante</span>' in cartao


def test_status_que_nao_e_da_lista_nao_grava(tela):
    c, banco = tela
    r = c.post("/os/api/acomp/9104/status", json={"status": "Inventado", "wid": 2})
    assert r.status_code == 400 and banco == []


def test_o_mesmo_status_nao_grava_de_novo_e_sem_status_limpa(tela):
    c, banco = tela
    c.post("/os/api/acomp/9104/status", json={"status": "Standby", "wid": 2})
    assert c.post("/os/api/acomp/9104/status", json={"status": "Standby", "wid": 2}).get_json()["ok"] is True
    assert len(banco) == 1
    c.post("/os/api/acomp/9104/status", json={"status": "", "wid": 2})
    assert banco[-1]["texto"] == "Status retirado" and banco[-1]["extra"] == {"status": ""}


def test_chamado_finalizado_nao_troca_o_status(tela):
    c, banco = tela
    r = c.post("/os/api/acomp/9105/status", json={"status": "Standby", "wid": 3})
    assert r.status_code == 400 and banco == []
    h = c.get("/os/chamados/acompanhamento/9105").get_data(as_text=True)
    assert 'id="status_ch" data-osb="nativo" disabled' in h


# ── 4: criado por e quando ──────────────────────────────────────────────────────────────────────────────────────
def test_os_dados_dizem_quem_criou_e_quando(tela):
    c, _ = tela
    h = c.get("/os/chamados/acompanhamento/9104").get_data(as_text=True)
    dados = h.split("<h2>Dados</h2>", 1)[1].split("</dl>", 1)[0]
    assert "<dt>Criado por</dt><dd>Pessoa Que Criou</dd>" in dados
    assert "<dt>Criada em</dt><dd>20/10/2026 10:00</dd>" in dados                # 13:00 UTC = 10:00 em Brasília


# ── 2: a tabela ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_tabela_tem_uma_linha_por_chamado_com_as_colunas_enxutas(tela):
    c, _ = tela
    c.post("/os/api/acomp/9104/status", json={"status": "Standby", "wid": 2})
    h = c.get("/os/chamados/acompanhamento").get_data(as_text=True)
    assert 'data-vista="quadro"' in h and 'data-vista="tabela"' in h          # a troca entre quadro e tabela
    tab = h.split('<table class="tq">', 1)[1].split("</table>", 1)[0]
    assert [x.strip() for x in tab.split("<thead>", 1)[1].split("</thead>", 1)[0].replace("</th>", "|").replace(
        "<tr>", "").replace("</tr>", "").replace("<th>", "").split("|") if x.strip()] == \
        ["OS", "Ativo", "Usina", "Fornecedor", "Geral", "Status", "Ticket", "Situação", "Responsável"]
    linhas = tab.split("<tbody>", 1)[1].split("<tr ")[1:]
    assert [l.split('data-href="/os/chamados/acompanhamento/', 1)[1].split('"', 1)[0] for l in linhas] == \
        ["9103", "9104", "9105"]
    assert all('data-marca="Huawei"' in l and "data-busca=" in l for l in linhas)  # os mesmos filtros do quadro
    l9104 = linhas[1]
    assert ">Standby<" in l9104 and "Com o fornecedor" in l9104 and "TCU com problema na bateria" in l9104
    assert ">Testes em campo<" in linhas[0]                                       # o status da nota


# ── 3: o cartão não rola para o lado ────────────────────────────────────────────────────────────────────────────
def test_o_texto_do_cartao_quebra_e_a_coluna_nao_rola_para_o_lado():
    css = CSS.read_text(encoding="utf-8")
    import re
    chip = re.search(r"\.k-chip\{([^}]*)\}", css).group(1)
    assert "white-space:normal" in chip and "overflow-wrap:anywhere" in chip and "max-width:100%" in chip
    assert "white-space:nowrap" not in chip
    cards = re.search(r"\n\.cards\{([^}]*)\}", css).group(1)
    assert "overflow-x:hidden" in cards
