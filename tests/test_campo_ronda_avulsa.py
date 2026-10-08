"""Ronda avulsa (Levi, 07/10/2026): "tem que ser possível inserir rondas avulsas, a pessoa loga pelo fractal dela ... não
terá imagens, só informações da tabela, salva nome da pessoa, data e hora e diz que foi avulso, quando passa o mouse em
cima de avulso explica o que é ronda avulsa". Conta na cobertura; comentário livre opcional. No banco, nada pessoal em
claro: nome e comentário cifrados, pessoa como pessoa_id e código do e-mail. Banco falso, datas relativas a hoje.

08/10/2026 (decisão 3 do Levi, antes da 1ª gravação do livro): vala no domínio do App (sai o "Suja"), sensor em três
estados (vazio = não verificado, nunca 0 por não marcado) e a linha de anulação sem data_id e usina_id."""
import json

import pytest
from test_campo_visao import CHAVE, CHAVE_CADASTRO, _dia, banco  # noqa: F401 (o banco é fixture)

from nexus.cadastro.cifra import Cofre
from nexus.campo import ronda_avulsa as RA
from nexus.campo import visao
from nexus.campo.ligacao_cadastro import codigo_da_pessoa
from nexus.dados import dominios as DOM
from nexus.dados import fato_ronda as FR
from nexus.dados import fatos

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
    # GHI fica de fora de propósito: é o "Não verifiquei" (o rádio que o formulário já traz marcado não manda valor)
    f = {"usina_id": "3", "data": _dia(1), "inicio": "08:00", "fim": "09:10", "tipo": "curta", "sujidade": "4",
         "vegetacao": "2", "vala": "Parcial", "sombreamento": "não", "ipoa_sujo": "Sujo", "albedo_sujo": "Limpo",
         "comentario": "Portão com cadeado novo; chamei o João no 11 99999-1234"}
    f.update(kw)
    return f


def _linhas(api):
    return RA.ler_todas()


def _fato(linhas):
    """A avulsa do livro passada pelo fato único de ronda (a mesma leitura da carga e das telas)."""
    lig = fatos.Ligador([], [], [], {})
    out, _ = FR.fato_ronda([], [], linhas, lig, {})
    return [dict(zip(FR.CAB_RONDA, l)) for l in out]


def test_lanca_grava_no_banco_com_ids_e_nada_pessoal_em_claro(tecnico, banco):  # noqa: F811
    r = tecnico.post("/t/campo/rondas/avulsa", data=_form())
    assert r.status_code == 303
    linhas = _linhas(banco)
    assert len(linhas) == 1
    x = linhas[0]
    assert (x["usina_id"], x["equipe_id"], x["duracao_min"], x["tipo"]) == (3, 20, 70, "curta")
    assert x["data_id"] == int(_dia(1).replace("-", "")) and x["origem"] == "avulsa"
    assert (x["sujidade"], x["vegetacao"], x["vala"], x["sombreamento"]) == (4, 2, "Parcial", "não")
    assert (x["ipoa_sujo"], x["albedo_sujo"], x["ghi_sujo"]) == ("Sujo", "Limpo", None)     # o não verificado é VAZIO
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
    linha = next(x for x in suj["linhas"] if x["usina"] == "Coração 1")
    assert linha["sujidade"] == 4 and linha["sensores_sujos"] == ["IPOA"]    # o "Limpo" e o não verificado não acusam


@pytest.mark.parametrize("muda, erro", [
    ({"fim": "07:30"}, "O fim tem de ser depois do início"),
    ({"data": _dia(-1)}, "não pode ser no futuro"),
    ({"data": _dia(40)}, "até 30 dias"),
    ({"sujidade": "7"}, "Sujidade"),
    ({"usina_id": "4"}, "usina mobilizada"),
    ({"tipo": "media"}, "curta ou longa"),
    ({"vala": "Suja"}, "Vala: Limpa, Parcial, Obstruída, Não se aplica"),     # o "Suja" de 07/10 não existe no App
    ({"ghi_sujo": "talvez"}, "GHI: limpo, sujo ou não verifiquei"),
])
def test_recusa_com_o_motivo_e_nao_grava(tecnico, banco, muda, erro):  # noqa: F811
    r = tecnico.post("/t/campo/rondas/avulsa", data=_form(**muda))
    assert r.status_code == 400 and erro in r.get_data(as_text=True)
    assert _linhas(banco) == []


def test_vala_tem_as_opcoes_do_app_e_entra_no_fato_como_nivel(tecnico, banco):  # noqa: F811
    assert RA.VALAS == DOM.VALA_OPCOES == ("Limpa", "Parcial", "Obstruída", "Não se aplica")
    html = tecnico.get("/t/campo/rondas/avulsa").get_data(as_text=True)
    assert "Obstruída" in html and "Suja" not in html
    assert '<option value="">escolha</option>' in html          # nenhuma opção vai marcada de saída (era o "Limpa")
    # o texto vem como o App escreve, mesmo digitado sem acento; no fato, o nível 3 (o mesmo do App e do checklist)
    assert tecnico.post("/t/campo/rondas/avulsa", data=_form(vala="obstruida")).status_code == 303
    assert tecnico.post("/t/campo/rondas/avulsa", data=_form(vala="Não se aplica", inicio="10:00",
                                                             fim="10:30")).status_code == 303
    linhas = _linhas(banco)
    assert [x["vala"] for x in linhas] == ["Obstruída", "Não se aplica"]
    assert [r["vala_nivel"] for r in _fato(linhas)] == [3, None]
    for rotulo, nivel in DOM.MAPA_ANTIGO["vala"]["avulsa"].items():
        assert DOM.vala(rotulo) == nivel, rotulo


def test_sensor_em_tres_estados_e_o_nao_verificado_fica_vazio(tecnico, banco):  # noqa: F811
    html = tecnico.get("/t/campo/rondas/avulsa").get_data(as_text=True)
    for col, _nome in RA.SENSORES:                                   # de saída, "Não verifiquei" marcado em cada um
        assert f'name="{col}" value="" checked' in html
        assert f'name="{col}" value="Limpo">' in html and f'name="{col}" value="Sujo">' in html
    # nenhum sensor respondido: nada de 0 no banco (o formulário de 07/10 gravava 0 = "limpo" sem ninguém olhar)
    sem = {k: v for k, v in _form().items() if k not in ("ipoa_sujo", "albedo_sujo")}
    assert tecnico.post("/t/campo/rondas/avulsa", data=sem).status_code == 303
    assert tecnico.post("/t/campo/rondas/avulsa", data=_form(inicio="10:00", fim="10:30", ghi_sujo="limpo")).status_code == 303
    a, b = _linhas(banco)
    assert (a["ipoa_sujo"], a["albedo_sujo"], a["ghi_sujo"]) == (None, None, None)
    assert (b["ipoa_sujo"], b["albedo_sujo"], b["ghi_sujo"]) == ("Sujo", "Limpo", "Limpo")
    fa, fb = _fato([a, b])
    assert (fa["ipoa_sujo"], fa["albedo_sujo"], fa["ghi_sujo"]) == (None, None, None)
    assert (fb["ipoa_sujo"], fb["albedo_sujo"], fb["ghi_sujo"]) == (1, 0, 0)       # sujo 1, VERIFICADO limpo 0
    for valor, novo in DOM.MAPA_ANTIGO["sensor"]["avulsa"].items():
        assert DOM.sensor_avulsa(valor) == novo, valor
    # o 0 do formulário de 07/10 (um Nexus com o código velho na memória) continua sendo "não verificado"
    assert DOM.sensor_avulsa(0) is None and DOM.sensor_avulsa("0") is None


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


def test_a_linha_de_anulacao_so_aponta_a_anulada(tecnico, banco):  # noqa: F811
    """Spec 9.3 (GR-7): com o dia e a usina, um COUNT por usina e dia no livro aberto contava 2 para uma ronda anulada."""
    tecnico.post("/t/campo/rondas/avulsa", data=_form())
    rid = _linhas(banco)[0]["id"]
    tecnico.post(f"/t/campo/rondas/avulsa/{rid}/anular")
    anul = _linhas(banco)[1]
    assert (anul["anula_id"], anul["origem"], anul["pessoa_hmac"]) == (rid, "anulação", codigo_da_pessoa(CHAVE, EMAIL))
    assert anul["lancada_em"] and anul["id"] != rid
    assert all(anul[c] is None for c in ("data_id", "data", "usina_id", "equipe_id", "inicio", "sujidade", "vala"))
    assert _fato(_linhas(banco)) == []                       # nem a anulada nem a anulação são ronda


def test_acrescentar_preserva_o_livro_e_pula_a_repetida(tecnico, banco):  # noqa: F811
    """O caminho de gravação da importação (`montar_linha` + `acrescentar`): o livro é trocado inteiro, então o que já
    está lá vai junto; a repetida não entra."""
    tecnico.post("/t/campo/rondas/avulsa", data=_form())
    cofre = Cofre(CHAVE_CADASTRO)
    from datetime import date
    nova = RA.montar_linha(cofre, origem="validacao_foto", dia=date.fromisoformat(_dia(2)), usina_id=1, equipe_id=10,
                           pessoa_id=90, codigo="cod", nome="Pessoa Inventada", email="p@exemplo.test",
                           inicio=f"{_dia(2)}T00:00:00-03:00", sujidade=3, vegetacao=None,
                           comentario="importado de teste")
    igual = lambda n, vistas: any(str(v.get("origem")) == n["origem"] and str(v.get("usina_id")) == str(n["usina_id"])
                                  for v in vistas)
    entraram, puladas = RA.acrescentar([nova, dict(nova, id="outra")], igual)
    assert [n["id"] for n in entraram] == [nova["id"]] and [n["id"] for n in puladas] == ["outra"]
    linhas = _linhas(banco)
    assert [x["origem"] for x in linhas] == ["avulsa", "validacao_foto"]        # a da tela ficou
    assert linhas[1]["vegetacao"] is None and linhas[1]["tipo"] is None and linhas[1]["ipoa_sujo"] is None
    assert RA.acrescentar([nova], igual) == ([], [nova]) and len(_linhas(banco)) == 2


def test_catalogo_registra_o_fato_com_os_ids():
    from nexus.dados import catalogo
    f = next(x for x in catalogo.FATOS if x.id == "ronda_avulsa")
    # 08/10/2026 (auditoria Kimball, GR-1): o livro da avulsa é FONTE do fato único de ronda (nexus_fatos · fato_ronda)
    assert f.livro.startswith(RA.LIVRO) and f.estado == "parte" and f.parte_de == ("ronda",)
    assert f"{RA.LIVRO} · {RA.ABA}" in catalogo.POR_ID["ronda"].fontes
    assert {k for k, (estado, _c) in f.dims.items() if estado == "id"} >= {"data", "usina", "equipe", "pessoa"}
