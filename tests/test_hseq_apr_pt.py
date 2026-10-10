"""APR e PT em Segurança · HSEQ (Levi, 09/10/2026): a tela das PT veio do Campo · App com o título "Permissões de
trabalho e Análise Preliminar de Risco", as colunas PT e APR (cada uma com o seu PDF), o detalhe com a assinatura e a
decisão ali mesmo, e quem pode dar o De acordo: o Supervisor de Campo, o gestor de contrato, alguém do COS ou um
administrador. Banco falso do Campo (test_campo_visao.py): a PT-1 é de Altair (Sudeste 03, supervisora de campo 92;
gestor de contrato 90, Beltrano)."""
import base64
import json
import time
from datetime import datetime

import pytest
from test_campo_visao import CHAVE_CADASTRO, _aba, _pessoas, banco  # noqa: F401  (banco é fixture)

from nexus.cadastro.cifra import Cofre
from nexus.campo import decisao_pt, nota_fracttal, pt_fracttal, visao


def _jwt(email, exp_s=3600):
    corpo = base64.urlsafe_b64encode(json.dumps({"email": email, "exp": time.time() + exp_s}).encode())
    return "x." + corpo.decode().rstrip("=") + ".y"


def _fracttal(app, cliente, email, nome):
    """O cookie do OS Creator, como o login do Fracttal dele grava."""
    from nexus.torres.oscreator import ponte
    clone = ponte.clone(app)
    valor = clone.session_interface.get_signing_serializer(clone).dumps(
        {"jwt": _jwt(email), "conta": {"email": email, "nome": nome}})
    cliente.set_cookie("os_sessao", valor, path="/os")


def _nexus(cliente, admin=False):
    with cliente.session_transaction() as s:
        s.clear()
        s.update(logado=True, admin=admin, usuario={"email": "x@exemplo.test", "nome": "X", "perfil": "Supervisor"})


def _com_cos(banco):
    """Uma pessoa do COS no cadastro (o vínculo é o campo da relação)."""
    cofre = Cofre(CHAVE_CADASTRO)
    _aba(banco, "cadastro_nexus", "pessoas", _pessoas() + [
        {"pessoa_id": 95, "vinculo": "COS", "cargo": None, "equipe_id": None, "status": "Ativo", "supervisor_id": None,
         "excluido": "não", "sensivel_cifrado": cofre.cifrar(json.dumps(
             {"nome": "Operadora Cos", "nome_padrao": "Operadora Cos", "email": "cos@exemplo.test"}), "banco/pessoas/95")}])
    visao.limpar()


def test_a_tela_mora_em_seguranca_com_o_titulo_novo_e_as_colunas_pt_e_apr(banco, logado):
    html = logado.get("/t/hseq/apr-pt?modo=tabela").get_data(as_text=True)
    assert "<h1 class=\"cn-titulo\">Permissões de trabalho e Análise Preliminar de Risco</h1>" in html
    assert "<th>PT</th><th>APR</th>" in html and 'href="/t/campo/pt/PT-1/apr.pdf"' in html
    hist = logado.get("/t/hseq/apr-pt?aba=historico").get_data(as_text=True)
    assert 'href="/t/campo/pt/PT-3/pdf"' in hist and 'href="/t/campo/pt/PT-3/apr.pdf"' in hist
    assert hist.count(">Baixar</a>") == 2                                   # a PT-3 decidida: PT e APR


def test_o_detalhe_traz_a_assinatura_quem_assina_e_a_decisao_que_volta_para_a_lista(banco, logado):
    html = logado.get("/t/hseq/apr-pt?modo=tabela").get_data(as_text=True)
    assert 'data-url="/os/_nexus/pt/PT-1/assinatura-tecnico"' in html and "Executante · assinatura da APR" in html
    assert 'action="/os/_nexus/pt/PT-1/decidir"' in html and '<input type="hidden" name="volta" value="/t/hseq/apr-pt?modo=tabela">' in html
    assert ("Quem assina</dt><dd>O Supervisor de Campo da Sudeste 03 (Supervisora Campo), o gestor de contrato "
            "(Beltrano Supervisor), alguém do COS (ninguém com o vínculo COS no cadastro ainda) ou um administrador") in html
    assert "O App ainda não lê a\n          decisão do Nexus" in html or "O App ainda não lê a" in html


def test_quem_pode_dar_o_de_acordo(banco, app):
    p = visao.pt("PT-1")
    assert decisao_pt.pode_decidir(p, "beltrano@exemplo.test")[0] is True              # o gestor de contrato
    assert decisao_pt.pode_decidir(p, "supervisora@exemplo.test")[0] is True           # o Supervisor de Campo
    ok, porque = decisao_pt.pode_decidir(p, "sup@exemplo.test")                        # fora do cadastro
    assert ok is False and porque.startswith("Quem pode dar o De acordo nesta PT: o Supervisor de Campo da Sudeste 03")
    assert decisao_pt.pode_decidir(p, "sup@exemplo.test", admin=True) == (True, "administrador")
    # o coordenador só aprova com a vaga de supervisor aberta (a Sudeste 03 tem supervisora)
    assert decisao_pt.pode_decidir(p, "coordenador@exemplo.test")[0] is False
    _com_cos(banco)
    assert decisao_pt.pode_decidir(visao.pt("PT-1"), "cos@exemplo.test") == (True, "COS")
    assert "alguém do COS ou um administrador" in decisao_pt.aprovadores(visao.pt("PT-1"))["texto"]


def test_quem_nao_pode_e_recusado_e_quem_pode_decide_pela_lista(banco, app, cliente):
    _nexus(cliente)
    _fracttal(app, cliente, "sup@exemplo.test", "Fulano Sem Papel")
    r = cliente.post("/os/_nexus/pt/PT-1/decidir", data={"decisao": "de_acordo", "volta": "/t/hseq/apr-pt?modo=tabela"})
    assert r.status_code == 302 and r.headers["Location"] == "/t/hseq/apr-pt?modo=tabela"
    html = cliente.get("/t/hseq/apr-pt?modo=tabela").get_data(as_text=True)
    assert "PT-1: Quem pode dar o De acordo nesta PT" in html and "nexus_pt_decisoes" not in banco.workbooks
    _fracttal(app, cliente, "beltrano@exemplo.test", "Beltrano Supervisor")
    r = cliente.post("/os/_nexus/pt/PT-1/decidir", data={"decisao": "de_acordo", "volta": "/t/hseq/apr-pt?modo=tabela"})
    assert r.headers["Location"] == "/t/hseq/apr-pt?modo=tabela"
    assert "Decisão da PT-1 salva no banco" in cliente.get("/t/hseq/apr-pt?modo=tabela").get_data(as_text=True)
    assert decisao_pt.da_pt("PT-1")["decisao"] == "de_acordo"
    # a volta só vale para o próprio Nexus
    _fracttal(app, cliente, "beltrano@exemplo.test", "Beltrano Supervisor")
    r = cliente.post("/os/_nexus/pt/PT-2/decidir", data={"decisao": "de_acordo", "volta": "https://outro.site/x"})
    assert r.headers["Location"].endswith("/t/campo/pt/PT-2?gravada=1")


def test_o_pdf_da_apr_e_o_anexo_mais_perto_da_pt(banco, logado, monkeypatch):
    p = visao.pt("PT-1")
    criada = p["criada"].astimezone(pt_fracttal._BRT)
    perto, longe = criada.strftime("%d-%m-%Y %Hh%M"), "01-01-2026 08h00"
    anexos = [{"description": f"APR OS 700 {longe}", "value": "https://s3/longe.pdf"},
              {"description": f"APR OS 700 {perto}", "value": "https://s3/perto.pdf"},
              {"description": "Permissão de Trabalho PT-1", "value": "https://s3/pt.pdf"},
              {"description": "APR OS 7001 01-01-2026 08h00", "value": "https://s3/outra-os.pdf"}]
    pedidos = []
    monkeypatch.setattr(nota_fracttal, "anexos_da_os", lambda os_, ler=None: anexos)
    monkeypatch.setattr(pt_fracttal, "_baixar", lambda url, limite: pedidos.append(url) or b"%PDF-1.4 apr")
    r = logado.get("/t/campo/pt/PT-1/apr.pdf")
    assert r.status_code == 200 and r.data.startswith(b"%PDF") and pedidos == ["https://s3/perto.pdf"]
    assert r.headers["Content-Disposition"].startswith("attachment;") and "APR-OS-700" in r.headers["Content-Disposition"]
    # sem APR anexada: volta para a tela e diz
    monkeypatch.setattr(nota_fracttal, "anexos_da_os", lambda os_, ler=None: anexos[2:3])
    r = logado.get("/t/campo/pt/PT-1/apr.pdf")
    assert r.status_code == 302 and r.headers["Location"].endswith("/t/hseq/apr-pt")
    assert "ainda não está nos anexos do Fracttal" in logado.get("/t/hseq/apr-pt").get_data(as_text=True)


def test_o_vinculo_cos_e_o_campo_da_relacao_no_cadastro():
    from nexus.cadastro.esquema import VINCULOS, VINCULO_COS
    assert VINCULO_COS == "COS" and VINCULO_COS in VINCULOS
    assert pt_fracttal._quando_apr("APR OS 15223 09-10-2026 07h42 v2") == datetime(2026, 10, 9, 7, 42)
    assert pt_fracttal._quando_apr("APR OS 15223") is None
