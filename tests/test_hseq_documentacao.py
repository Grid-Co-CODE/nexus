"""A documentação de segurança de cada colaborador (Segurança · HSEQ, 06/11/2026): a tela Colaboradores registra a
situação de cada item (ASO, NRs, integrações, anuências, documentos) e carrega a planilha da Segurança. O livro é um
arquivo (`NEXUS_HSEQ_DOCUMENTACAO_ARQUIVO`): nada vai ao banco. Nomes fictícios; a planilha é montada na memória."""
import io
import json
import re
from datetime import date, datetime

import pytest
from openpyxl import Workbook
from test_campo_visao import banco  # noqa: F401  (banco é fixture)
from test_hseq_colaboradores import _aba, _ficha

from nexus.campo import visao
from nexus.hseq import documentacao as DOC

HOJE = date(2026, 11, 6)


@pytest.fixture
def livro(app, banco, tmp_path):
    arq = tmp_path / "documentacao.json"
    app.config["NEXUS_HSEQ_DOCUMENTACAO_ARQUIVO"] = str(arq)
    _aba(banco, "cadastro_nexus", "pessoas", [
        _ficha(1, "Bruna Ficticia Lima", "Ativo"),
        _ficha(2, "Ana Exemplo Rocha", "Desligado"),
        _ficha(3, "Caio Teste Prado", "Ativo")])
    visao.limpar()
    DOC.limpar()
    yield arq
    DOC.limpar()


@pytest.fixture
def tst(app, cliente):
    app.config["NEXUS_ADMINS"] = "tst@exemplo.test"
    with cliente.session_transaction() as s:
        s.update(logado=True, admin=True, usuario={"email": "tst@exemplo.test", "nome": "TST de teste"})
    return cliente


def _planilha() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "ATIVOS O&M"
    ws.append(["FUNCIONARIO", "CPF", "Email", "ASO -  Val", "NR 10", "NR 35 ", "ANUENCIA 10", "CPF2", "CNH", "obs"])
    ws.append(["Bruna Ficticia Lima", "000.000.000-00", "bruna@exemplo.test", datetime(2027, 5, 7), datetime(2024, 1, 10),
               "23/07/2025", "assinatura", "OK", "N.A", "texto livre qualquer"])
    ws.append(["CAIO TESTE PRADO", "111.111.111-11", None, "FALTA", "Solicitado (Assinatura)", "SOLICITADO", "OK",
               "FALTA", "Ensino médio", None])
    ws.append(["Zeca Fora do Cadastro", "222.222.222-22", None, "OK", None, None, None, None, None, None])
    ws.append(["Bruna Teste Lima", None, None, None, None, None, None, None, None, None])  # 1º e último: aproximado
    ws.append(["Caio Prado", None, None, "OK", None, None, None, None, None, None])      # só dois nomes: não casa
    ws.append(["Ana Exemplo Rocha- PJ", None, None, None, None, None, None, None, None, None])   # o "- PJ" sai
    ws.append(["ASSINATURA = Enviar para assinar", None, None, None, None, None, None, None, None, None])  # legenda
    ws.append(["LEGENDA:", None, None, None, None, None, None, None, None, None])
    s = wb.create_sheet("SAUDE")
    s.append(["FUNCIONARIO", "FUNÇÃO", "ASO -  Val", "ECG"])
    s.append(["Bruna Ficticia Lima", "Técnica", datetime(2027, 9, 1), "ok"])           # o ASO mais novo vence
    d = wb.create_sheet("DEMITIDOS")
    d.append(["FUNCIONARIO", "STATUS NA PLATAFORMA", "ASO -  Val", "RG", "Coluna1"])
    d.append(["Ana Exemplo Rocha", "DEMITIDO", "10/24/2026", "OK", "FALTA"])
    a = wb.create_sheet("ATIVOS ADM ")
    a.append(["FUNCIONARIO", "MATRICULA", "ASO -  Val"])
    a.append(["Caio Teste Prado", "123", datetime(2030, 1, 1)])                         # o time ADM: fora do painel
    t = wb.create_sheet("TERCEIROS")
    t.append(["FUNCIONARIO", "EMPRESA", "NR 10"])
    t.append(["Terceiro Ficticio", "Empresa X", datetime(2025, 1, 1)])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_o_valor_da_planilha_vira_situacao_e_data():
    assert DOC.ler_valor("OK") == ("valido", None)
    assert DOC.ler_valor(" FALTA ") == ("falta", None) and DOC.ler_valor("Não possui ASO no Servidor") == ("falta", None)
    for v in ("assinatura", "SOLICITADO (ASSINATURA)", "Assinatura (Solicitado)", "Aguardando assinatura D4Sign",
              "SOLICIDADO (ASSINATURA)", "Falta enviar para assinatura", "ASSINAR"):
        assert DOC.ler_valor(v) == ("pendente_assinatura", None), v
    assert DOC.ler_valor("SOLICITADO") == ("solicitado", None)
    assert all(DOC.ler_valor(v) == ("nao_se_aplica", None) for v in ("NA", "N.A", "-"))
    assert DOC.ler_valor(datetime(2025, 3, 6)) == ("valido", date(2025, 3, 6))
    assert DOC.ler_valor(" 23/07/2025") == ("valido", date(2025, 7, 23))                  # sempre dd/mm/aaaa
    assert DOC.ler_valor("10/24/2026") is False                                           # mês 24: não é data brasileira
    assert DOC.ler_valor("Eletrotecnico") is False and DOC.ler_valor(None) is None and DOC.ler_valor("  ") is None


def test_em_andamento_legenda_e_pj():
    """A 1ª conferência com a planilha real (13/11/2026): os textos de curso em andamento, as linhas de legenda lidas
    como nome e o "- PJ" grudado no nome."""
    assert DOC.ler_valor("Em andamento") == ("em_andamento", None)
    assert DOC.ler_valor("Aguardando a finalização dos Cursos") == ("em_andamento", None)
    assert DOC.ler_valor("Aguardando assinatura D4Sign") == ("pendente_assinatura", None)   # a assinatura vence
    assert "em_andamento" in DOC.PENDENCIAS and DOC.ESTADOS["em_andamento"][1] == "alerta"
    assert DOC.linha_de_legenda("ZIP =Está na pasta") and DOC.linha_de_legenda("LEGENDA:")
    assert not DOC.linha_de_legenda("Bruna Ficticia Lima")
    assert DOC.nome_da_pessoa("Fulana Teste Rocha- PJ") == "Fulana Teste Rocha"
    assert DOC.nome_da_pessoa("Fulana Teste Rocha - pj ") == "Fulana Teste Rocha"


def test_validade_pela_norma_e_o_estado():
    nr10, nr35, aso, nr06 = (DOC.POR_ID[i] for i in ("nr10", "nr35", "aso", "nr06"))
    assert DOC.estado(nr10, {"situacao": "valido", "data": date(2024, 1, 10)}, HOJE)["estado"] == "vencido"   # +2 anos
    e = DOC.estado(nr35, {"situacao": "valido", "data": date(2025, 7, 23)}, HOJE)
    assert (e["estado"], e["vence"]) == ("valido", date(2027, 7, 23))
    assert DOC.estado(aso, {"situacao": "valido", "data": date(2026, 11, 26)}, HOJE)["estado"] == "vence_logo"
    assert DOC.estado(nr06, {"situacao": "valido", "data": date(2015, 1, 1)}, HOJE)["estado"] == "valido"  # sem prazo
    assert DOC.estado(nr10, {"situacao": "falta", "data": None}, HOJE)["estado"] == "falta"
    assert DOC.estado(nr10, None, HOJE)["estado"] == "sem_registro"
    assert DOC._somar_meses(date(2024, 2, 29), 24) == date(2026, 2, 28)
    r = DOC.resumo({"nr10": {"situacao": "valido", "data": date(2024, 1, 10)}, "rg": {"situacao": "valido", "data": None}},
                   HOJE)
    assert (r["pior"], r["pendencias"], r["registrados"]) == ("vencido", 1, 2)


def test_a_planilha_casa_pelo_cadastro_e_so_leva_o_pessoa_id(livro):
    from nexus.hseq import colaboradores as COL
    res = DOC.ler_planilha(_planilha(), COL.colaboradores().dados["pessoas"])
    reg = {(p, i): (s, d) for p, i, s, d in res["registros"]}
    assert reg[(1, "aso")] == ("valido", date(2027, 9, 1))                    # a aba de saúde, mais nova, vence
    assert reg[(1, "nr10")] == ("valido", date(2024, 1, 10)) and reg[(1, "nr35")] == ("valido", date(2025, 7, 23))
    assert reg[(1, "anuencia_nr10")] == ("pendente_assinatura", None) and reg[(1, "cnh")] == ("nao_se_aplica", None)
    assert reg[(3, "nr10")] == ("pendente_assinatura", None) and reg[(3, "nr35")] == ("solicitado", None)
    assert reg[(2, "cpf_doc")] == ("falta", None) and (2, "aso") not in reg  # a "Coluna1" dos demitidos; 10/24 não entra
    assert {i for _p, i, _s, _d in res["registros"]} <= set(DOC.POR_ID)      # CPF, e-mail, obs: nunca
    assert res["nao_casou"] == [("Caio Prado", "só dois nomes na planilha: escreva o nome completo"),
                                ("Zeca Fora do Cadastro", "não está no cadastro")]
    assert res["aproximados"] == [("Bruna Teste Lima", "Bruna Ficticia Lima")]
    assert reg[(3, "aso")] == ("falta", None)                                # a aba ADM não trouxe o ASO de 2030
    assert any(a == "ATIVOS ADM" and "administrativo" in m for a, m in res["fora"])
    om = next(a for a in res["abas"] if a["aba"] == "ATIVOS O&M")
    assert (om["pessoas"], om["legendas"]) == (6, 2)                          # as linhas de legenda não são pessoa
    assert ("DEMITIDOS", "ASO", "10/24/2026", 1) in res["desconhecidos"]
    assert ("ATIVOS O&M", "CNH", "Ensino médio", 1) in res["desconhecidos"]
    assert any(a == "TERCEIROS" and "terceiros" in m for a, m in res["fora"])


def test_conferir_nao_grava_e_gravar_so_grava_o_que_muda(livro, tst):
    r = tst.post("/t/hseq/colaboradores/planilha",
                 data={"acao": "conferir", "arquivo": (io.BytesIO(_planilha()), "ativos.xlsx")},
                 content_type="multipart/form-data")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and not livro.exists()                       # conferir não grava
    assert "Zeca Fora do Cadastro" in html and "10/24/2026" in html and "Gravar no Nexus" in html
    assert "000.000.000-00" not in html
    r = tst.post("/t/hseq/colaboradores/planilha",
                 data={"acao": "gravar", "arquivo": (io.BytesIO(_planilha()), "ativos.xlsx")},
                 content_type="multipart/form-data")
    texto = " ".join(re.sub(r"<[^>]+>", " ", r.get_data(as_text=True)).split())
    assert "Planilha gravada" in texto
    bruto = livro.read_text(encoding="utf-8")
    linhas = json.loads(bruto)[DOC.ABA]
    n = len(linhas)
    assert n > 10 and {x["origem"] for x in linhas} == {"planilha"}
    # nada pessoal nem a situação em claro: só o pessoa_id, o item, o dia e o código de quem registrou
    for proibido in ("Bruna", "Caio", "000.000.000-00", "bruna@exemplo.test", "valido", "pendente", "2027-09-01", "TST de teste"):
        assert proibido not in bruto, proibido
    DOC.limpar()
    tst.post("/t/hseq/colaboradores/planilha", data={"acao": "gravar", "arquivo": (io.BytesIO(_planilha()), "a.xlsx")},
             content_type="multipart/form-data")
    assert len(json.loads(livro.read_text(encoding="utf-8"))[DOC.ABA]) == n   # a mesma planilha: nada novo
    # a lista mostra o resumo e o filtro de pendência
    lista = tst.get("/t/hseq/colaboradores?doc=pendencia").get_data(as_text=True)
    assert "Bruna Ficticia Lima" in lista and "vencido" in lista              # a NR-10 de 2024 venceu


def test_a_ficha_registra_um_item_e_o_ultimo_vale(livro, tst):
    r = tst.post("/t/hseq/colaboradores/1/item", data={"item": "nr35", "situacao": "valido", "data": "2026-10-01"})
    assert r.status_code == 303 and "ok=" in r.headers["Location"]
    tst.post("/t/hseq/colaboradores/1/item", data={"item": "nr35", "situacao": "valido", "data": "01/11/2026"})
    html = tst.get("/t/hseq/colaboradores/1").get_data(as_text=True)
    linha = html.split('id="item-nr35"')[1].split("</tr>")[0]
    assert "01/11/2026" in linha and "01/11/2028" in linha and "pela tela" in linha   # +2 anos, o último vale
    assert len(json.loads(livro.read_text(encoding="utf-8"))[DOC.ABA]) == 2
    r = tst.post("/t/hseq/colaboradores/1/item", data={"item": "aso", "situacao": "valido", "data": ""})
    assert "precisa+da+data" in r.headers["Location"] or "precisa%20da%20data" in r.headers["Location"]
    r = tst.post("/t/hseq/colaboradores/1/item", data={"item": "nr35", "situacao": "inventada", "data": ""})
    assert "erro=" in r.headers["Location"]
    assert tst.get("/t/hseq/colaboradores/99").status_code == 404


def test_so_a_seguranca_registra_e_sempre_com_login_de_pessoa(livro, app, cliente):
    with cliente.session_transaction() as s:
        s.update(logado=True, admin=False, usuario={"email": "sup@exemplo.test", "nome": "Sup"})
    r = cliente.post("/t/hseq/colaboradores/1/item", data={"item": "rg", "situacao": "valido", "data": ""})
    assert "erro=" in r.headers["Location"] and not livro.exists()
    assert cliente.post("/t/hseq/colaboradores/planilha", data={"acao": "conferir"}).status_code == 403
    with cliente.session_transaction() as s:      # a senha de administrador não diz quem é
        s.clear()
        s.update(logado=True, admin=True)
    r = cliente.post("/t/hseq/colaboradores/1/item", data={"item": "rg", "situacao": "valido", "data": ""})
    assert "erro=" in r.headers["Location"] and not livro.exists()
