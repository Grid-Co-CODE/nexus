"""Ronda avulsa (Levi, 07/10/2026): "tem que ser possível inserir rondas avulsas, a pessoa loga pelo fractal dela ... não
terá imagens, só informações da tabela, salva nome da pessoa, data e hora e diz que foi avulso, quando passa o mouse em
cima de avulso explica o que é ronda avulsa". Conta na cobertura; comentário livre opcional. No banco, nada pessoal em
claro: nome e comentário cifrados, pessoa como pessoa_id e código do e-mail. Banco falso, datas relativas a hoje."""
import json

import pytest
from test_campo_visao import CHAVE, CHAVE_CADASTRO, _dia, banco  # noqa: F401 (o banco é fixture)

from nexus.cadastro.cifra import Cofre
from nexus.campo import ronda_avulsa as RA
from nexus.campo import visao
from nexus.campo.ligacao_cadastro import codigo_da_pessoa

EMAIL = "tec1@exemplo.test"


@pytest.fixture
def tecnico(app, banco):  # noqa: F811
    """Quem entrou pelo login do Fracttal: a sessão traz e-mail e nome."""
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"] = True
        s["admin"] = False
        s["usuario"] = {"email": EMAIL, "nome": "Técnico Um da Silva", "perfil": "Técnico"}
    return c


def _form(**kw):
    f = {"usina_id": "3", "data": _dia(1), "inicio": "08:00", "fim": "09:10", "tipo": "curta", "sujidade": "4",
         "vegetacao": "2", "vala": "Parcial", "sombreamento": "não", "sensores": ["IPOA"],
         "comentario": "Portão com cadeado novo; chamei o João no 11 99999-1234"}
    f.update(kw)
    return f


def _linhas(api):
    return RA.ler_todas()


def test_lanca_grava_no_banco_com_ids_e_nada_pessoal_em_claro(tecnico, banco):  # noqa: F811
    r = tecnico.post("/t/campo/rondas/avulsa", data=_form())
    assert r.status_code == 303
    linhas = _linhas(banco)
    assert len(linhas) == 1
    x = linhas[0]
    assert (x["usina_id"], x["equipe_id"], x["duracao_min"], x["tipo"]) == (3, 20, 70, "curta")
    assert x["data_id"] == int(_dia(1).replace("-", "")) and x["origem"] == "avulsa"
    assert (x["sujidade"], x["vegetacao"], x["vala"], x["sombreamento"], x["ipoa_sujo"], x["ghi_sujo"]) == (4, 2, "Parcial", "não", 1, 0)
    assert x["pessoa_hmac"] == codigo_da_pessoa(CHAVE, EMAIL)
    texto = json.dumps(x, ensure_ascii=False)
    assert "Técnico" not in texto and EMAIL not in texto and "Portão" not in texto and "99999" not in texto
    cofre = Cofre(CHAVE_CADASTRO)
    quem = json.loads(cofre.decifrar(x["quem_cifrado"], f"banco/rondas_avulsas/{x['id']}/quem"))
    assert quem["nome"] == "Técnico Um da Silva" and quem["email"] == EMAIL
    assert "Portão com cadeado" in cofre.decifrar(x["comentario_cifrado"], f"banco/rondas_avulsas/{x['id']}/comentario")


def test_avulsa_entra_nas_rondas_conta_na_cobertura_e_explica_no_mouse(tecnico, banco, logado):  # noqa: F811
    antes = {c["usina"]: c["dias"] for c in visao.rondas().dados["cobertura"]}
    assert antes["Coração 1"] == 999                                     # nunca teve ronda
    tecnico.post("/t/campo/rondas/avulsa", data=_form())
    d = visao.rondas().dados
    assert {c["usina"]: c["dias"] for c in d["cobertura"]}["Coração 1"] == 1     # a avulsa conta na cobertura
    a = next(r for r in d["todas"] if r.get("avulsa"))
    assert (a["tecnico"], a["usina"], a["ini_hm"], a["fim_hm"], a["dur_min"]) == ("Técnico Silva", "Coração 1", "08:00", "09:10", 70)
    assert a["nota"] is None and a["veredito"][1] == "—" and not a["sem_os"] and a["pendencia"] == ""
    html = tecnico.get("/t/campo/rondas").get_data(as_text=True)
    assert "Avulsa" in html and RA.EXPLICACAO in html                   # o title do selo explica o que é
    assert "Ronda avulsa" in html                                        # o botão para lançar
    hist = tecnico.get("/t/campo/rondas/usina/3").get_data(as_text=True)
    assert "Avulsa" in hist and "Portão com cadeado" in hist             # o comentário aparece decifrado na tela
    suj = visao.sujidade_vegetacao(d["todas"], d["cobertura"], {}, 14, d["hoje"])
    assert next(x for x in suj["linhas"] if x["usina"] == "Coração 1")["sujidade"] == 4


@pytest.mark.parametrize("muda, erro", [
    ({"fim": "07:30"}, "O fim tem de ser depois do início"),
    ({"data": _dia(-1)}, "não pode ser no futuro"),
    ({"data": _dia(40)}, "até 30 dias"),
    ({"sujidade": "7"}, "Sujidade"),
    ({"usina_id": "4"}, "usina mobilizada"),
    ({"tipo": "media"}, "curta ou longa"),
])
def test_recusa_com_o_motivo_e_nao_grava(tecnico, banco, muda, erro):  # noqa: F811
    r = tecnico.post("/t/campo/rondas/avulsa", data=_form(**muda))
    assert r.status_code == 400 and erro in r.get_data(as_text=True)
    assert _linhas(banco) == []


def test_a_tela_de_lancar_abre_e_lista_as_minhas(tecnico, banco):  # noqa: F811
    r = tecnico.get("/t/campo/rondas/avulsa")
    assert r.status_code == 200 and 'name="usina_id"' in r.get_data(as_text=True)
    tecnico.post("/t/campo/rondas/avulsa", data=_form())
    html = tecnico.get("/t/campo/rondas/avulsa").get_data(as_text=True)
    assert "Ronda avulsa lançada" in html and "/anular" in html             # o aviso e a minha, com o Anular


def test_sem_login_do_fracttal_nao_lanca(logado, banco):  # noqa: F811
    r = logado.post("/t/campo/rondas/avulsa", data=_form())
    assert r.status_code == 400 and "login do Fracttal" in r.get_data(as_text=True)
    assert _linhas(banco) == []


def test_a_mesma_ronda_duas_vezes_e_recusada(tecnico, banco):  # noqa: F811
    assert tecnico.post("/t/campo/rondas/avulsa", data=_form()).status_code == 303
    r = tecnico.post("/t/campo/rondas/avulsa", data=_form())
    assert r.status_code == 400 and "já lançou" in r.get_data(as_text=True)
    assert len(_linhas(banco)) == 1


def test_quem_lancou_anula_e_ela_sai_da_tela_mas_fica_no_banco(app, tecnico, banco):  # noqa: F811
    tecnico.post("/t/campo/rondas/avulsa", data=_form())
    rid = _linhas(banco)[0]["id"]
    outro = app.test_client()
    with outro.session_transaction() as s:
        s.update(logado=True, admin=False, usuario={"email": "outro@exemplo.test", "nome": "Outro", "perfil": ""})
    assert outro.post(f"/t/campo/rondas/avulsa/{rid}/anular").status_code == 400     # só quem lançou anula
    assert tecnico.post(f"/t/campo/rondas/avulsa/{rid}/anular").status_code == 303
    linhas = _linhas(banco)
    assert len(linhas) == 2 and linhas[1]["anula_id"] == rid           # o banco não apaga: a anulação é outra linha
    assert not any(r.get("avulsa") for r in visao.rondas().dados["todas"])


def test_catalogo_registra_o_fato_com_os_ids():
    from nexus.dados import catalogo
    f = next(x for x in catalogo.FATOS if x.id == "ronda_avulsa")
    assert f.livro.startswith(RA.LIVRO) and f.estado == "conformado"
    assert {k for k, (estado, _c) in f.dims.items() if estado == "id"} >= {"data", "usina", "equipe", "pessoa"}
