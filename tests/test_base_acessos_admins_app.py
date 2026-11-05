"""Base → Acessos, aba Administradores do App de Campo (05/11/2026; nexus/auth/telas_admins_app.py e o dado em
nexus/pcm/admins_app.py).

Levi, 05/11/2026: "os administradores do App de Campo e os técnicos por usina têm de ser escolhidos no Nexus". O que
estes testes seguram: só o administrador do Nexus vê e grava (a trava de Base → Acessos); pôr, tirar e o histórico,
com quem decidiu; a pessoa sem código recusada com 409 e a frase do pedido; o código pelo usuário do Fracttal ligado à
pessoa (Pessoas e setores) quando a ficha não tem e-mail; só as fichas não desligadas e não excluídas para escolher; o
POST de outro site ou sem o código do formulário não grava; sem a NEXUS_PESSOA_HMAC nada grava; e nenhum e-mail das
fichas na página. Fichas, e-mails e códigos de mentira; o livro é um arquivo, o cadastro um banco de mentira."""
import json
import re

import pytest
from pg_falso import ApiPGFalsa

from conftest import SENHA_TESTE
from nexus import create_app
from nexus.cadastro import setores as S
from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.campo import visao
from nexus.campo.ligacao_cadastro import codigo_da_pessoa
from nexus.pcm import admins_app as AA
from nexus.pcm import atribuicoes as A

URL = "/t/base/acessos"
ABA = URL + "?aba=admins_app"
SERVIDOR = "servidor@exemplo.com"
HMAC = "chave-hmac-de-teste"
CHAVE = gerar_chave()
EMAILS = {10: "t10@exemplo.test", 13: "t13@exemplo.test", 14: "t14@exemplo.test"}
EMAIL_FRACTTAL_11 = "s11@exemplo.test"           # a ficha 11 não tem e-mail; o usuário do Fracttal ligado a ela tem


def _h(email):
    return codigo_da_pessoa(HMAC, email)


def _pessoas():
    cofre = Cofre(CHAVE)

    def p(pid, nome, status="Ativo", excluido="não", vinculo="Colaborador de campo", cargo="Técnico O&M"):
        segredo = {"nome": nome, "nome_padrao": nome, "email": EMAILS.get(pid)}
        return {"pessoa_id": pid, "vinculo": vinculo, "cargo": cargo, "equipe_id": 1, "status": status,
                "excluido": excluido, "sensivel_cifrado": cofre.cifrar(json.dumps(segredo), f"banco/pessoas/{pid}")}
    return [p(10, "Técnico Dez"), p(11, "Supervisora Onze", vinculo="Supervisor", cargo="Supervisor de Campo"),
            p(12, "Técnico Doze"), p(13, "Técnico Treze", status="Desligado"), p(14, "Técnico Catorze", excluido="sim")]


def _aba(api, livro, aba, linhas):
    api.workbooks[livro] = {"key": livro}
    cab = list(linhas[0]) if linhas else ["vazio"]
    api._id(livro, aba)["linhas"] = [{"headers": cab, "values": [l.get(c) for c in cab]} for l in linhas]


@pytest.fixture
def app(tmp_path):
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA_TESTE,
                      "NEXUS_ADMINS": SERVIDOR, "NEXUS_DADOS": str(tmp_path / "dados")})
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False, GRIDCO_DB_API="http://pg.falso",
                      NEXUS_PESSOA_HMAC=HMAC, NEXUS_CHAVE_CADASTRO=CHAVE,
                      NEXUS_ADMINS_APP_ARQUIVO=str(tmp_path / "admins_app.json"))
    api = ApiPGFalsa()
    _aba(api, "cadastro_nexus", "pessoas", _pessoas())
    # o usuário do Fracttal 501 ligado à ficha 11 em Base → Acessos → Pessoas e setores (o setor dele)
    _aba(api, S.LIVRO, S.ABA_SETOR, [{"setor_id": 1, "nome": "Supervisão", "criado_em": "2026-10-12T12:00:00Z"}])
    _aba(api, S.LIVRO, S.ABA_DECISAO, [{"decidida_em": "2026-10-12T12:00:00Z", "data_id": 20261012, "fracttal_id": 501,
                                        "pessoa_id": 11, "pessoa_ligada_por": "nome",
                                        "pessoa_hmac": _h(EMAIL_FRACTTAL_11), "setor_id": 1}])
    app.extensions["nexus_dados_sessao"] = api
    visao.limpar()
    S._CACHE.clear()
    A.limpar()
    AA.limpar()
    yield app
    app.extensions.pop("nexus_dados_sessao", None)
    visao.limpar()
    S._CACHE.clear()


@pytest.fixture
def admin(app):
    c = app.test_client()
    assert c.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    return c


@pytest.fixture
def fracttal_falso(monkeypatch):
    from nexus.auth import fracttal
    monkeypatch.setattr(fracttal, "entrar", lambda app, e, s: {"email": e.strip().lower(), "nome": "Pessoa Teste",
                                                                  "perfil": "", "cookie": ("os_sessao", "v", 3600)})


def _codigo(c) -> str:
    """O código do formulário desta sessão: o da página quando ela tem formulário; na que só mostra (sem a chave, sem o
    cadastro), o que a sessão guardou ao abrir a aba (o pedido feito à mão tem de ser recusado igual)."""
    m = re.search(r'name="codigo" value="([^"]+)"', c.get(ABA).get_data(as_text=True))
    if m:
        return m.group(1)
    with c.session_transaction() as s:
        return s["acessos_codigo"]


def _post(c, acao, codigo=None, **dados):
    return c.post(URL, data={"codigo": codigo if codigo is not None else _codigo(c), "acao": acao, **dados})


def _linhas(app):
    return AA.ler(app.config, forcar=True)["decisoes"]


def _vigentes(app):
    return AA.atuais(AA.ler(app.config, forcar=True), A.hoje_id())


# ── quem vê ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_administrador_ve_a_aba_com_a_nota_do_app(admin):
    r = admin.get(ABA)
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'aria-current="page">Administradores do App de Campo</a>' in html
    assert ">Telas e administradores</a>" in html and ">Pessoas e setores</a>" in html
    assert "O App de Campo lê esta lista de 5 em 5 min; com a lista vazia ele não tira ninguém (não tranca o App)" in html
    assert "Nenhum administrador do App ainda" in html
    # a aba de telas segue sem a seção nova, e o menu das abas está nas três
    t = admin.get(URL).get_data(as_text=True)
    assert ">Administradores do App de Campo</a>" in t and "Pôr administrador" not in t


def test_quem_nao_e_administrador_do_nexus_nao_ve_nem_grava(app, fracttal_falso):
    c = app.test_client()
    assert c.post("/entrar", data={"email": "pessoa@exemplo.com", "senha": "x"}).status_code == 302
    r = c.get(ABA)
    assert r.status_code == 403 and "A tela Acessos é só para administradores" in r.get_data(as_text=True)
    assert c.post(URL, data={"acao": "admin_app_por", "pessoa_id": "10", "codigo": "qualquer"}).status_code == 403
    assert _linhas(app) == []


# ── pôr, tirar e o histórico ────────────────────────────────────────────────────────────────────────────────────
def test_por_tirar_e_o_historico(app, admin):
    r = _post(admin, "admin_app_por", pessoa_id="10", obs="cobre as férias do supervisor")
    assert r.status_code == 303 and r.headers["Location"].endswith(ABA)
    linha = _linhas(app)[0]
    assert (linha["pessoa_id"], linha["pessoa_hmac"], linha["ativo"], linha["papel"], linha["origem"]) == (
        10, _h(EMAILS[10]), "sim", "admin", "tela")
    assert linha["assinatura"] == AA.assinatura(linha, HMAC) and "férias" not in json.dumps(linha)
    html = admin.get(ABA).get_data(as_text=True)
    assert "Técnico Dez agora é administrador do App de Campo" in html
    vig = html.split('id="aa-vigentes"', 1)[1].split("</table>", 1)[0]
    assert "Técnico Dez" in vig and "administrador (senha)" in vig and _h(EMAILS[10]) in vig     # o Tirar leva o código
    escolher = html.split('id="aa-lista"', 1)[1].split("</fieldset>", 1)[0]
    assert 'value="10"' not in escolher                                    # quem já é não aparece para pôr
    r = _post(admin, "admin_app_tirar", pessoa_hmac=_h(EMAILS[10]))
    assert r.status_code == 303 and _vigentes(app) == {}
    assert [x["ativo"] for x in _linhas(app)] == ["sim", "nao"]
    html = admin.get(ABA).get_data(as_text=True)
    assert "Técnico Dez deixou de ser administrador do App de Campo" in html
    hist = html.split('id="aa-historico"', 1)[1].split("</table>", 1)[0]
    assert hist.index("tirou") < hist.index("pôs") and "cobre as férias do supervisor" in hist
    # tirar de novo (a página velha) é recusado, e nada grava
    r = _post(admin, "admin_app_tirar", pessoa_hmac=_h(EMAILS[10]))
    assert r.status_code == 409 and "já não é administradora" in r.get_data(as_text=True) and len(_linhas(app)) == 2


def test_a_pessoa_sem_codigo_e_recusada_com_409(app, admin):
    r = _post(admin, "admin_app_por", pessoa_id="12")
    html = r.get_data(as_text=True)
    assert r.status_code == 409
    assert ("Técnico Doze: sem e-mail na ficha nem usuário do Fracttal ligado: o App não a reconheceria; corrija o "
            "cadastro antes.") in html
    assert _linhas(app) == []
    # a lista já avisa antes de escolher
    escolher = html.split('id="aa-lista"', 1)[1].split("</fieldset>", 1)[0]
    doze = escolher.split('value="12"', 1)[1].split("</label>", 1)[0]
    assert "sem código" in doze


def test_o_codigo_vem_do_usuario_do_fracttal_ligado_quando_a_ficha_nao_tem_email(app, admin):
    assert _post(admin, "admin_app_por", pessoa_id="11").status_code == 303
    assert _linhas(app)[0]["pessoa_hmac"] == _h(EMAIL_FRACTTAL_11)


def test_so_as_fichas_ativas_para_escolher_e_nenhum_email_na_pagina(app, admin):
    html = admin.get(ABA).get_data(as_text=True)
    escolher = html.split('id="aa-lista"', 1)[1].split("</fieldset>", 1)[0]
    assert all(f'value="{p}"' in escolher for p in (10, 11, 12))
    assert 'value="13"' not in escolher and 'value="14"' not in escolher        # a desligada e a excluída
    for pid in (13, 14):
        r = _post(admin, "admin_app_por", pessoa_id=str(pid))
        assert r.status_code == 409 and "não está entre as fichas ativas" in r.get_data(as_text=True)
    assert _linhas(app) == []
    _post(admin, "admin_app_por", pessoa_id="10")
    html = admin.get(ABA).get_data(as_text=True)
    assert "exemplo.test" not in html


def test_quem_decidiu_pelo_email_do_administrador(app, fracttal_falso):
    """Quem decidiu é o código do e-mail do login; a tela o diz pela ficha ou, sem ficha (o administrador do escritório),
    pelo e-mail que o Nexus conhece (os administradores e quem entrou)."""
    c = app.test_client()
    assert c.post("/entrar", data={"email": SERVIDOR, "senha": "x"}).status_code == 302
    assert _post(c, "admin_app_por", pessoa_id="10").status_code == 303
    assert _linhas(app)[0]["decidida_por_hmac"] == _h(SERVIDOR)
    vig = c.get(ABA).get_data(as_text=True).split('id="aa-vigentes"', 1)[1].split("</table>", 1)[0]
    assert SERVIDOR in vig


# ── o que não grava ─────────────────────────────────────────────────────────────────────────────────────────────
def test_pedido_de_outro_site_ou_sem_o_codigo_do_formulario_nao_grava(app, admin):
    r = admin.post(URL, data={"codigo": _codigo(admin), "acao": "admin_app_por", "pessoa_id": "10"},
                   headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and "Administradores do App de Campo" in r.get_data(as_text=True)
    assert _post(admin, "admin_app_por", codigo="outro", pessoa_id="10").status_code == 403
    assert _post(admin, "admin_app_por", pessoa_id="").status_code == 400
    assert _linhas(app) == []


def test_sem_a_chave_hmac_a_aba_so_mostra(app, admin):
    app.config.pop("NEXUS_PESSOA_HMAC")
    html = admin.get(ABA).get_data(as_text=True)
    assert "NEXUS_PESSOA_HMAC" in html and 'value="admin_app_por"' not in html
    r = _post(admin, "admin_app_por", pessoa_id="10")
    assert r.status_code == 409 and "NEXUS_PESSOA_HMAC" in r.get_data(as_text=True)
    assert _linhas(app) == []


def test_sem_o_banco_a_aba_abre_e_diz(app, admin):
    app.extensions.pop("nexus_dados_sessao")
    visao.limpar()
    S._CACHE.clear()
    r = admin.get(ABA)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Não consegui ler o cadastro de pessoas" in html
    r = _post(admin, "admin_app_por", pessoa_id="10")
    assert r.status_code == 409 and _linhas(app) == []


# ── o código da pessoa (revisão de 05/11/2026, achado 4) ─────────────────────────────────────────────────────────
def _religar(app, *decisoes):
    """Troca as decisões de Pessoas e setores: (fracttal_id, pessoa_id, e-mail do usuário do Fracttal, quando)."""
    _aba(app.extensions["nexus_dados_sessao"], S.LIVRO, S.ABA_DECISAO, [
        {"decidida_em": q, "data_id": 20261012, "fracttal_id": f, "pessoa_id": p, "pessoa_ligada_por": "nome",
         "pessoa_hmac": _h(e), "setor_id": 1} for f, p, e, q in decisoes])
    visao.limpar()
    S._CACHE.clear()


def test_o_religado_da_ficha_11_para_a_10_e_recusado_com_o_nome_da_outra(app, admin):
    """O usuário do Fracttal 501 estava ligado à ficha 11, que virou administradora do App pelo código dele; depois foi
    religado à ficha 10. Pela ligação de hoje o código é da 10 (a 11 fica sem), e pôr a 10 com o código que já vale na
    lista pela 11 é recusado, dizendo qual; a linha da 11 avisa que o código dela já não é o da ficha."""
    assert _post(admin, "admin_app_por", pessoa_id="11").status_code == 303
    _religar(app, (501, 11, EMAIL_FRACTTAL_11, "2026-10-12T12:00:00Z"), (501, 10, EMAIL_FRACTTAL_11, "2026-10-20T12:00:00Z"))
    # a 10 segue na lista para escolher (ela não é administradora), com o porquê de não poder entrar ainda
    escolher = admin.get(ABA).get_data(as_text=True).split('id="aa-lista"', 1)[1].split("</fieldset>", 1)[0]
    dez = escolher.split('value="10"', 1)[1].split("</label>", 1)[0]
    assert "o código dela já está na lista com outra ficha (Supervisora Onze)" in dez
    r = _post(admin, "admin_app_por", pessoa_id="10")
    html = r.get_data(as_text=True)
    assert r.status_code == 409
    assert "Técnico Dez: o código dela já está na lista de administradores do App com outra ficha (Supervisora Onze)" in html
    assert len(_linhas(app)) == 1
    vig = html.split('id="aa-vigentes"', 1)[1].split("</table>", 1)[0]
    assert "Supervisora Onze" in vig and "já não é o desta ficha" in vig


def test_o_codigo_de_duas_fichas_fica_sem_e_a_tela_diz_por_que(app, admin):
    """O usuário do Fracttal com o e-mail da ficha 10 ligado à ficha 12: o código cai nas duas e sai das duas; a lista
    diz por quê, e o Pôr recusa com 409."""
    _religar(app, (502, 12, EMAILS[10], "2026-10-12T12:00:00Z"))
    html = admin.get(ABA).get_data(as_text=True)
    escolher = html.split('id="aa-lista"', 1)[1].split("</fieldset>", 1)[0]
    dez = escolher.split('value="10"', 1)[1].split("</label>", 1)[0]
    assert "o mesmo código está em mais de uma ficha" in dez
    r = _post(admin, "admin_app_por", pessoa_id="10")
    assert r.status_code == 409 and "o mesmo código está em mais de uma ficha" in r.get_data(as_text=True)
    assert _linhas(app) == []


# ── o nome antes da gravação (revisão de 05/11/2026, achado 8) ───────────────────────────────────────────────────
def test_o_nome_sai_antes_da_gravacao_no_por_e_no_tirar(app, admin, monkeypatch):
    """Uma leitura do cadastro que falhasse DEPOIS de gravar viraria "Não consegui gravar" (ou "nada mudou") com a linha
    já no livro. O nome sai antes; depois da gravação, nada mais lê o cadastro."""
    from nexus.auth import telas_admins_app as TAA
    gravou = {"sim": False}
    decidir, cadastro = AA.decidir, TAA._cadastro

    def decidir_e_marcar(*a, **k):
        r = decidir(*a, **k)
        gravou["sim"] = True
        return r

    def cadastro_so_antes(cfg):
        if gravou["sim"]:
            raise RuntimeError("o cadastro lido depois da gravação")
        return cadastro(cfg)
    monkeypatch.setattr(AA, "decidir", decidir_e_marcar)
    monkeypatch.setattr(TAA, "_cadastro", cadastro_so_antes)
    codigo = _codigo(admin)
    assert _post(admin, "admin_app_por", codigo, pessoa_id="10").status_code == 303
    gravou["sim"] = False
    assert _post(admin, "admin_app_tirar", codigo, pessoa_hmac=_h(EMAILS[10])).status_code == 303
    assert [x["ativo"] for x in _linhas(app)] == ["sim", "nao"]
    gravou["sim"] = False
    assert "Técnico Dez deixou de ser administrador do App de Campo" in admin.get(ABA).get_data(as_text=True)
