"""Performance › ETMs: o comentário avulso da usina, sem OS (Levi, 26/11/2026: "Na parte de ETMs, deve ser possível uma
pessoa adicionar um comentário. Daí tem daquela usina, ele já vai para o usuário e o comentário. Não precisa ser OS alguma,
mas é bom ter esse comentário avulso, certo? Para a gente ter um acompanhamento"). Banco e Fracttal falsos; nomes de
mentira."""
import hashlib
import time

import pytest

from nexus.cadastro import setor_ids as SID
from nexus.engenharia import etm as E
from test_engenharia_acompanhamento import ANA, _como
from test_engenharia_etm import SET, U, banco, w  # noqa: F401 (a fixture do banco falso)


@pytest.fixture
def tela(app, monkeypatch):
    from nexus.auth import setor_telas as ST
    from nexus.performance import etm_comentarios as EC
    from nexus.torres.performance import etm_tela
    oss = E.montar([w(1, "Corretiva"), w(3, "Corretiva", status=3, task="DONE")], {"ALF100-ESTM1"}, SET,
                   __import__("datetime").date.today())
    monkeypatch.setattr(E, "dados", lambda: {"os": oss, "lido": time.time() - 60, "lendo": False, "erro": "", "erro_em": None})
    monkeypatch.setattr(E, "pedir_releitura", lambda app=None, esperar=False, forcar=False: None)
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": {"performance/etm"},
                                               "setor": {"id": SID.PERFORMANCE, "nome": "Performance"}, "erro": ""})
    monkeypatch.setattr(etm_tela, "_usina_no_retrato", lambda folios: (42, set(folios)))
    EC.limpar()
    yield
    EC.limpar()


def _comentar(cli, texto, usina=U):
    return _como(cli, ANA).post("/t/performance/etm/usina/comentar", json={"usina": usina, "texto": texto})


def test_o_comentario_avulso_grava_com_quem_e_aparece_na_linha_do_tempo_sem_os(banco, tela, cliente):
    from nexus.performance import etm_comentarios as EC
    r = _comentar(cliente, "Estação sem sinal desde ontem; cliente avisado")
    assert r.status_code == 200 and r.get_json()["ok"] is True
    j = _como(cliente, ANA).get("/t/performance/etm/usina/comentarios", query_string={"usina": U}).get_json()
    av = [c for c in j["comentarios"] if c.get("usina")]
    assert len(av) == 1 and av[0]["os"] == "" and av[0]["nome"] == "Ana Lima"
    assert av[0]["texto"] == "Estação sem sinal desde ontem; cliente avisado" and av[0]["quando"] and j["erro_avulsos"] == ""
    # no banco (leitura aberta): a usina pela chave e pelo id, quem e o texto só cifrados
    (l,) = banco.linhas(EC.LIVRO, EC.ABA)
    assert l["usina_chave"] == hashlib.sha1(" ".join(U.split()).casefold().encode()).hexdigest()
    assert int(float(l["usina_id"])) == 42 and l["usina_ligada_por"] == "OS de ETM da usina" and l["pessoa_hmac"]
    assert "Ana" not in str(l) and "sem sinal" not in str(l) and "ana.lima" not in str(l)


def test_o_comentario_de_outra_usina_nao_aparece(banco, tela, cliente):
    from nexus.performance import etm_comentarios as EC
    assert _comentar(cliente, "da Alfa").status_code == 200
    lu = EC.ler(forcar=True)
    assert EC.da_usina(lu["eventos"], "Outra usina")[0] == []
    assert [c["texto"] for c in EC.da_usina(lu["eventos"], "  " + U.upper() + " ")[0]] == ["da Alfa"]   # caixa e espaço não mudam a chave


def test_recusas(banco, tela, cliente, monkeypatch):
    assert _comentar(cliente, "   ").status_code == 400                                   # sem texto
    assert _comentar(cliente, "x" * 2001).status_code == 400                              # passou do teto
    assert _comentar(cliente, "oi", usina="Usina que não é das ETMs").status_code == 400
    assert _como(cliente, ANA).post("/t/performance/etm/usina/comentar", json=["x"]).status_code == 400
    from nexus.auth import setor_telas as ST
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(), "setor": {"id": 999, "nome": "Outro"}, "erro": ""})
    r = _comentar(cliente, "oi")
    assert r.status_code == 403 and "Performance" in r.get_json()["erro"]


def test_o_banco_fora_nao_tira_os_comentarios_das_os_da_gaveta(banco, tela, cliente, monkeypatch):
    from nexus.engenharia import os_acompanhamento as O
    from nexus.performance import etm_comentarios as EC
    monkeypatch.setattr(O, "ler", lambda: {"lido_em": "agora", "eventos": []})
    monkeypatch.setattr(EC, "ler", lambda forcar=False: {"eventos": [], "lido_em": None, "erro": "ConnectionError: fora"})
    j = _como(cliente, ANA).get("/t/performance/etm/usina/comentarios", query_string={"usina": U}).get_json()
    assert j["erro_avulsos"] == "ConnectionError" and j["comentarios"] == []


def test_catalogo_registra_o_livro():
    from nexus.dados import catalogo, explica
    from nexus.performance import etm_comentarios as EC
    l = catalogo.LIVRO_POR_NOME[EC.LIVRO]
    assert set(l.abas) == {EC.ABA} and set(l.so_cresce) == {EC.ABA} and catalogo.aba_segue_a_regra(EC.ABA)
    f = next(x for x in catalogo.FATOS if x.id == "comentario_etm_usina")
    assert "1 linha = 1 comentário avulso" in f.grao and {"data", "usina", "pessoa"} <= set(f.dims)
    assert 15 <= len(explica.RESUMO["comentario_etm_usina"]) <= 70 and explica.PARA_QUE["comentario_etm_usina"].endswith(".")


def test_a_gaveta_tem_a_opcao_da_usina_e_a_etiqueta(tela, cliente):
    html = _como(cliente, ANA).get("/t/performance/etm").get_data(as_text=True)
    assert "'A usina (sem OS)'" in html and "nexusRota('/t/performance/etm/usina/comentar')" in html
    assert "'Comentário da usina'" in html and 'id="etm-chat-dica"' in html and ">Comentar em<" in html
    assert "novo.hidden = false;" in html                       # a usina sem OS também comenta
