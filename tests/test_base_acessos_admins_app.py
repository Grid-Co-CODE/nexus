"""Base → Acessos, aba Administradores do App de Campo (05/11/2026; nexus/auth/telas_admins_app.py e o dado em
nexus/pcm/admins_app.py).

Levi, 05/11/2026: "os administradores do App de Campo e os técnicos por usina têm de ser escolhidos no Nexus". O que
estes testes seguram: só o administrador do Nexus vê e grava (a trava de Base → Acessos); pôr, tirar e o histórico,
com quem decidiu; a pessoa sem código recusada com 409 e a frase do pedido; o código pelo usuário do Fracttal ligado à
pessoa (Pessoas e setores) quando a ficha não tem e-mail; só as fichas não desligadas e não excluídas para escolher; o
POST de outro site ou sem o código do formulário não grava; sem a NEXUS_PESSOA_HMAC nada grava; e nenhum e-mail das
fichas na página.

E, desde a 2ª volta de 05/11/2026 ("Só tá aparecendo os técnicos, tem que aparecer todos do pessoas e setores! e tem que
ter como fazer avulso também so digitando o e-mail"): a lista une as pessoas de Pessoas e setores e as fichas sem
repetir ninguém, com o setor (ou "ficha de campo") e a busca pelo nome e pelo setor; quem não tem ficha vai sem
`pessoa_id`; o avulso pelo e-mail (só @gridco.com.br) põe e tira pelo código, vai para a pessoa da lista quando o código
é dela, recusa o código de duas fichas, e o e-mail nunca vai em claro ao livro. Fichas, e-mails, códigos e o Fracttal de
mentira; o livro é um arquivo, o cadastro um banco de mentira."""
import json
import re
import time

import pytest
from pg_falso import ApiPGFalsa

from conftest import SENHA_TESTE
from nexus import create_app
from nexus.cadastro import fracttal_pessoal as FP
from nexus.cadastro import setores as S
from nexus.cadastro import telas_fracttal as TF
from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.campo import fracttal, visao
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


def _pessoas(emails=None, extra=()):
    """As fichas de mentira; `extra` = (pessoa_id, nome) de mais fichas ativas (o recontratado, por exemplo)."""
    cofre = Cofre(CHAVE)
    emails = EMAILS if emails is None else emails

    def p(pid, nome, status="Ativo", excluido="não", vinculo="Colaborador de campo", cargo="Técnico O&M"):
        segredo = {"nome": nome, "nome_padrao": nome, "email": emails.get(pid)}
        return {"pessoa_id": pid, "vinculo": vinculo, "cargo": cargo, "equipe_id": 1, "status": status,
                "excluido": excluido, "sensivel_cifrado": cofre.cifrar(json.dumps(segredo), f"banco/pessoas/{pid}")}
    return [p(10, "Técnico Dez"), p(11, "Supervisora Onze", vinculo="Supervisor", cargo="Supervisor de Campo"),
            p(12, "Técnico Doze"), p(13, "Técnico Treze", status="Desligado"), p(14, "Técnico Catorze", excluido="sim"),
            *(p(pid, nome) for pid, nome in extra)]


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
    # a aba lê o pessoal do Fracttal pela cópia de Pessoas e setores (sem o fornecedor de mentira, o Fracttal não abre)
    FP._CACHE.clear()
    TF.esquecer()
    yield app
    app.extensions.pop("nexus_dados_sessao", None)
    visao.limpar()
    S._CACHE.clear()
    fracttal.usar_fornecedor(None)
    FP._CACHE.clear()
    TF.esquecer()


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
    assert c.post(URL, data={"acao": "admin_app_por", "pessoa": "10", "codigo": "qualquer"}).status_code == 403
    assert _linhas(app) == []


# ── pôr, tirar e o histórico ────────────────────────────────────────────────────────────────────────────────────
def test_por_tirar_e_o_historico(app, admin):
    r = _post(admin, "admin_app_por", pessoa="10", obs="cobre as férias do supervisor")
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
    r = _post(admin, "admin_app_por", pessoa="12")
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
    assert _post(admin, "admin_app_por", pessoa="11").status_code == 303
    assert _linhas(app)[0]["pessoa_hmac"] == _h(EMAIL_FRACTTAL_11)


def test_so_as_fichas_ativas_para_escolher_e_nenhum_email_na_pagina(app, admin):
    html = admin.get(ABA).get_data(as_text=True)
    escolher = html.split('id="aa-lista"', 1)[1].split("</fieldset>", 1)[0]
    assert all(f'value="{p}"' in escolher for p in (10, 11, 12))
    assert 'value="13"' not in escolher and 'value="14"' not in escolher        # a desligada e a excluída
    for pid in (13, 14):
        r = _post(admin, "admin_app_por", pessoa=str(pid))
        assert r.status_code == 409 and "não está entre as fichas ativas" in r.get_data(as_text=True)
    assert _linhas(app) == []
    _post(admin, "admin_app_por", pessoa="10")
    html = admin.get(ABA).get_data(as_text=True)
    assert "exemplo.test" not in html


def test_quem_decidiu_pelo_email_do_administrador(app, fracttal_falso):
    """Quem decidiu é o código do e-mail do login; a tela o diz pela ficha ou, sem ficha (o administrador do escritório),
    pelo e-mail que o Nexus conhece (os administradores e quem entrou)."""
    c = app.test_client()
    assert c.post("/entrar", data={"email": SERVIDOR, "senha": "x"}).status_code == 302
    assert _post(c, "admin_app_por", pessoa="10").status_code == 303
    assert _linhas(app)[0]["decidida_por_hmac"] == _h(SERVIDOR)
    vig = c.get(ABA).get_data(as_text=True).split('id="aa-vigentes"', 1)[1].split("</table>", 1)[0]
    assert SERVIDOR in vig


# ── o que não grava ─────────────────────────────────────────────────────────────────────────────────────────────
def test_pedido_de_outro_site_ou_sem_o_codigo_do_formulario_nao_grava(app, admin):
    r = admin.post(URL, data={"codigo": _codigo(admin), "acao": "admin_app_por", "pessoa": "10"},
                   headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and "Administradores do App de Campo" in r.get_data(as_text=True)
    assert _post(admin, "admin_app_por", codigo="outro", pessoa="10").status_code == 403
    assert _post(admin, "admin_app_por", pessoa="").status_code == 400
    assert _linhas(app) == []


def test_sem_a_chave_hmac_a_aba_so_mostra(app, admin):
    app.config.pop("NEXUS_PESSOA_HMAC")
    html = admin.get(ABA).get_data(as_text=True)
    assert "NEXUS_PESSOA_HMAC" in html and 'value="admin_app_por"' not in html
    r = _post(admin, "admin_app_por", pessoa="10")
    assert r.status_code == 409 and "NEXUS_PESSOA_HMAC" in r.get_data(as_text=True)
    assert _linhas(app) == []


def test_sem_o_banco_a_aba_abre_e_diz(app, admin):
    app.extensions.pop("nexus_dados_sessao")
    visao.limpar()
    S._CACHE.clear()
    r = admin.get(ABA)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Não consegui ler o cadastro de pessoas" in html
    r = _post(admin, "admin_app_por", pessoa="10")
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
    lista pela 11 é recusado, dizendo qual."""
    assert _post(admin, "admin_app_por", pessoa="11").status_code == 303
    _religar(app, (501, 11, EMAIL_FRACTTAL_11, "2026-10-12T12:00:00Z"), (501, 10, EMAIL_FRACTTAL_11, "2026-10-20T12:00:00Z"))
    # a 10 segue na lista para escolher (ela não é administradora), com o porquê de não poder entrar ainda
    escolher = admin.get(ABA).get_data(as_text=True).split('id="aa-lista"', 1)[1].split("</fieldset>", 1)[0]
    dez = escolher.split('value="10"', 1)[1].split("</label>", 1)[0]
    assert "o código dela já está na lista com outra ficha (Supervisora Onze)" in dez
    r = _post(admin, "admin_app_por", pessoa="10")
    html = r.get_data(as_text=True)
    assert r.status_code == 409
    assert "Técnico Dez: o código dela já está na lista de administradores do App com outra ficha (Supervisora Onze)" in html
    assert len(_linhas(app)) == 1


def test_a_ligacao_do_fracttal_vence_e_a_outra_ficha_fica_sem_com_o_porque(app, admin):
    """O usuário do Fracttal com o e-mail da ficha 10 ligado à ficha 12 (re-revisão de 05/11/2026, N2): vence a ligação,
    a 12 fica com o código, e a 10 fica sem, com o porquê na lista e na recusa do Pôr."""
    _religar(app, (502, 12, EMAILS[10], "2026-10-12T12:00:00Z"))
    html = admin.get(ABA).get_data(as_text=True)
    escolher = html.split('id="aa-lista"', 1)[1].split("</fieldset>", 1)[0]
    dez = escolher.split('value="10"', 1)[1].split("</label>", 1)[0]
    doze = escolher.split('value="12"', 1)[1].split("</label>", 1)[0]
    assert "sem código: o e-mail dela é o do usuário do Fracttal ligado a outra ficha" in dez and "sem código" not in doze
    r = _post(admin, "admin_app_por", pessoa="10")
    assert r.status_code == 409 and "o e-mail dela é o do usuário do Fracttal ligado a outra ficha" in r.get_data(
        as_text=True)
    assert _linhas(app) == []
    assert _post(admin, "admin_app_por", pessoa="12").status_code == 303
    assert _linhas(app)[0]["pessoa_hmac"] == _h(EMAILS[10])


def test_o_aviso_do_codigo_so_quando_o_de_hoje_e_outro_ou_a_ficha_perdeu_e_sem_a_chave_nenhum(app, admin):
    """Re-revisão de 05/11/2026 (N1): sem a chave do cadastro o Nexus não lê o e-mail das fichas, e toda linha posta pelo
    e-mail mostrava "tire e ponha de novo". O aviso da linha só vale quando o código de hoje da ficha existe e é outro,
    ou quando a ficha perdeu o código (entre as sem código, com o porquê); sem a chave, nenhuma linha o leva, e a tela diz
    que o Nexus não confere os códigos."""
    api = app.extensions["nexus_dados_sessao"]

    def aviso():
        html = admin.get(ABA).get_data(as_text=True)
        return "já não é o desta ficha" in html.split('id="aa-vigentes"', 1)[1].split("</table>", 1)[0], html
    assert _post(admin, "admin_app_por", pessoa="10").status_code == 303
    assert aviso()[0] is False                                      # o código de hoje é o da linha
    _aba(api, "cadastro_nexus", "pessoas", _pessoas({**EMAILS, 10: "t10.novo@exemplo.test"}))
    visao.limpar()
    assert aviso()[0] is True                                       # o e-mail da ficha mudou: o código de hoje é outro
    _aba(api, "cadastro_nexus", "pessoas", _pessoas())
    _religar(app, (502, 12, EMAILS[10], "2026-10-12T12:00:00Z"))
    assert aviso()[0] is True                                       # a 10 perdeu o código para a ligação da 12
    app.config.pop("NEXUS_CHAVE_CADASTRO")
    visao.limpar()
    S._CACHE.clear()
    tem, html = aviso()
    assert tem is False and "o Nexus não confere os códigos" in html


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
    assert _post(admin, "admin_app_por", codigo, pessoa="10").status_code == 303
    gravou["sim"] = False
    assert _post(admin, "admin_app_tirar", codigo, pessoa_hmac=_h(EMAILS[10])).status_code == 303
    assert [x["ativo"] for x in _linhas(app)] == ["sim", "nao"]
    gravou["sim"] = False
    assert "Técnico Dez deixou de ser administrador do App de Campo" in admin.get(ABA).get_data(as_text=True)


# ── todas as pessoas de Pessoas e setores e o avulso pelo e-mail (2ª volta de 05/11/2026) ─────────────────────────
# Levi, olhando a aba no ar: "Só tá aparecendo os técnicos, tem que aparecer todos do pessoas e setores! e tem que ter
# como fazer avulso também so digitando o e-mail". A maioria dos administradores do App é do escritório, sem ficha.
ANALISTA, GERENTE, AVULSO = "analista.vinte@gridco.com.br", "gerente.trinta@gridco.com.br", "pessoa.avulsa@gridco.com.br"


def _usuario(fid, nome, email):
    return {"id_personnel": fid, "full_name": nome, "email": email, "code": "",
            "groups_permissions_description": "Administrator", "account_active": True}


# o pessoal do Fracttal de mentira: a 501 ligada à ficha 11 (a ligação do fixture), a 510 ligada sem ficha no setor PCM,
# a 511 sem ligação nem ficha, a 512 com o e-mail da ficha 10 (a tela de Pessoas e setores a liga pela ficha) e a 513 sem
# e-mail
PESSOAL = [_usuario(501, "Supervisora Onze", EMAIL_FRACTTAL_11), _usuario(510, "Analista Vinte", ANALISTA),
           _usuario(511, "Gerente Trinta", GERENTE), _usuario(512, "Técnico Dez", EMAILS[10]),
           _usuario(513, "Pessoa Sem Email", "")]


def _ligacoes(api, *extra):
    _aba(api, S.LIVRO, S.ABA_SETOR, [{"setor_id": 1, "nome": "Supervisão", "criado_em": "2026-10-12T12:00:00Z"},
                                     {"setor_id": 2, "nome": "PCM", "criado_em": "2026-10-12T12:00:00Z"}])
    _aba(api, S.LIVRO, S.ABA_DECISAO, [
        {"decidida_em": "2026-10-12T12:00:00Z", "data_id": 20261012, "fracttal_id": 501, "pessoa_id": 11,
         "pessoa_ligada_por": "nome", "pessoa_hmac": _h(EMAIL_FRACTTAL_11), "setor_id": 1},
        {"decidida_em": "2026-10-13T12:00:00Z", "data_id": 20261013, "fracttal_id": 510, "pessoa_id": None,
         "pessoa_ligada_por": "", "pessoa_hmac": _h(ANALISTA), "setor_id": 2}, *extra])
    visao.limpar()
    S._CACHE.clear()


def _com_o_fracttal(app, pessoal):
    """O pessoal do Fracttal de mentira e a cópia de Pessoas e setores já lida: a aba dos administradores do App só lê a
    cópia, e a leitura nova vai por trás (2ª revisão de 05/11/2026)."""
    fracttal.usar_fornecedor(lambda path: {"data": pessoal if path.startswith("personnel") else []})
    FP._CACHE.clear()
    TF.esquecer()
    with app.app_context():
        TF._ler_agora(app.config, False)


@pytest.fixture
def pessoas_e_setores(app):
    _ligacoes(app.extensions["nexus_dados_sessao"])
    _com_o_fracttal(app, PESSOAL)
    return PESSOAL


def _lista(html) -> str:
    return html.split('id="aa-lista"', 1)[1].split("</fieldset>", 1)[0]


def _itens(lista) -> list[str]:
    """As linhas da lista, cada uma inteira: a que se escolhe é um <label> com o rádio; a que não se escolhe, um <div>."""
    return re.findall(r'<label class="aa-pessoa.*?</label>|<div class="aa-pessoa.*?</div>', lista, flags=re.S)


def _item(lista, nome) -> str:
    """A (primeira) linha da lista com este nome."""
    return next(x for x in _itens(lista) if f'<span class="aa-nome">{nome}</span>' in x)


def _item_com(lista, trecho) -> str:
    return next(x for x in _itens(lista) if trecho in x)


def _cifrado(linha) -> dict:
    return json.loads(Cofre(CHAVE).decifrar(linha["dados_cifrados"],
                                            AA._ctx(linha["pessoa_id"], linha["decidida_em"], linha["pessoa_hmac"])))


def test_a_lista_une_pessoas_e_setores_e_as_fichas_sem_repetir(app, admin, pessoas_e_setores):
    html = admin.get(ABA).get_data(as_text=True)
    lista = _lista(html)
    nomes = re.findall(r'<span class="aa-nome">([^<]+)</span>', lista)
    # as três fichas ativas e as três de Pessoas e setores que não são ficha: cada pessoa uma vez só (a 501 é a ficha
    # 11 pela ligação; a 512 é a ficha 10 pelo e-mail)
    assert sorted(nomes) == ["Analista Vinte", "Gerente Trinta", "Pessoa Sem Email", "Supervisora Onze", "Técnico Dez",
                             "Técnico Doze"]
    assert "Supervisão" in _item(lista, "Supervisora Onze") and 'value="11"' in _item(lista, "Supervisora Onze")
    assert "ficha de campo" in _item(lista, "Técnico Dez") and 'value="10"' in _item(lista, "Técnico Dez")
    assert "PCM" in _item(lista, "Analista Vinte") and f'value="codigo:{_h(ANALISTA)}"' in _item(lista, "Analista Vinte")
    assert "sem setor" in _item(lista, "Gerente Trinta") and f'value="codigo:{_h(GERENTE)}"' in _item(lista, "Gerente Trinta")
    sem_email = _item(lista, "Pessoa Sem Email")
    assert "sem código: o App não a reconheceria" in sem_email and 'value="fracttal:513"' in sem_email
    assert "6 pessoas" in html
    # nenhum e-mail, nem das fichas nem do Fracttal, na página (o "@gridco.com.br" do exemplo do campo do avulso não é
    # de ninguém)
    assert "exemplo.test" not in html and ANALISTA not in html and GERENTE not in html


def test_o_palpite_pelo_nome_nao_junta_a_ficha_e_o_codigo_junta(app, admin, pessoas_e_setores):
    """2ª revisão de 05/11/2026: a aba de Pessoas e setores liga pelo nome quando não acha o e-mail, e o analista do
    escritório com o primeiro e último nome de um técnico seria a ficha do técnico (o Pôr faria o técnico administrador).
    Sem ligação no banco, só o palpite pelo e-mail junta à ficha; pelo nome, a pessoa entra sem ficha, com o código do
    e-mail do Fracttal. Pelo código, junta: a ligação sem ficha cujo código hoje é o do e-mail de uma ficha é essa ficha, e
    duas contas do Fracttal com o mesmo e-mail são uma pessoa só (para o App, o mesmo código)."""
    api = app.extensions["nexus_dados_sessao"]
    _aba(api, "cadastro_nexus", "pessoas", _pessoas({**EMAILS, 12: ANALISTA}))     # a ficha 12 com o e-mail da 510
    visao.limpar()
    doze_fracttal = "doze.fracttal@exemplo.test"
    _com_o_fracttal(app, PESSOAL + [_usuario(520, "Técnico Doze", doze_fracttal), _usuario(521, "Gerente Trinta", GERENTE)])
    lista = _lista(admin.get(ABA).get_data(as_text=True))
    nomes = re.findall(r'<span class="aa-nome">([^<]+)</span>', lista)
    assert sorted(nomes) == ["Gerente Trinta", "Pessoa Sem Email", "Supervisora Onze", "Técnico Dez", "Técnico Doze",
                             "Técnico Doze"]
    assert "PCM" in _item_com(lista, 'value="12"')                    # a ficha, com o setor da ligação da 510
    pelo_nome = _item_com(lista, f'value="codigo:{_h(doze_fracttal)}"')
    assert "Técnico Doze" in pelo_nome and "sem setor" in pelo_nome
    assert f'value="codigo:{_h(GERENTE)}"' in _item(lista, "Gerente Trinta")
    # o Pôr da pessoa ligada só pelo nome não faz a ficha administradora: vai sem ficha, com o código dela
    assert _post(admin, "admin_app_por", pessoa=f"codigo:{_h(doze_fracttal)}").status_code == 303
    assert [(x["pessoa_id"], x["pessoa_hmac"]) for x in _linhas(app)] == [(None, _h(doze_fracttal))]


def test_a_busca_vale_para_o_nome_e_o_setor(app, admin, pessoas_e_setores):
    lista = _lista(admin.get(ABA).get_data(as_text=True))

    def busca(nome):
        return re.search(r'data-aa-texto="([^"]*)"', _item(lista, nome)).group(1)
    assert busca("Analista Vinte").startswith("analista vinte") and "pcm" in busca("Analista Vinte")
    assert "supervisao" in busca("Supervisora Onze") and "sem setor" in busca("Gerente Trinta")
    assert "ficha de campo" in busca("Técnico Dez") and "tecnico o&amp;m" in busca("Técnico Dez")


def test_por_e_tirar_quem_e_de_pessoas_e_setores_sem_ficha(app, admin, pessoas_e_setores):
    """Sem ficha, a linha vai sem `pessoa_id` e com o código da ligação de hoje (a 510) ou, sem ligação, o do e-mail do
    Fracttal (a 511, a mesma conta que a ligação gravaria). Nenhum e-mail vai à linha: o nome vem de Pessoas e setores."""
    assert _post(admin, "admin_app_por", pessoa=f"codigo:{_h(ANALISTA)}").status_code == 303
    assert _post(admin, "admin_app_por", pessoa=f"codigo:{_h(GERENTE)}").status_code == 303
    linhas = _linhas(app)
    assert [(x["pessoa_id"], x["pessoa_hmac"], x["dados_cifrados"]) for x in linhas] == [
        (None, _h(ANALISTA), None), (None, _h(GERENTE), None)]
    assert all(x["assinatura"] == AA.assinatura(x, HMAC) for x in linhas)
    html = admin.get(ABA).get_data(as_text=True)
    assert "Gerente Trinta agora é administrador do App de Campo" in html
    vig = html.split('id="aa-vigentes"', 1)[1].split("</table>", 1)[0]
    assert "Analista Vinte" in vig and "PCM" in vig and "Gerente Trinta" in vig and "avulso" not in vig
    assert "Analista Vinte" not in _lista(html)                        # quem já é não aparece para pôr
    assert _post(admin, "admin_app_tirar", pessoa_hmac=_h(ANALISTA)).status_code == 303
    assert set(_vigentes(app)) == {(_h(GERENTE), "admin")}
    assert "Analista Vinte deixou de ser administrador do App de Campo" in admin.get(ABA).get_data(as_text=True)


def test_o_avulso_por_e_tirar_pelo_email(app, admin, pessoas_e_setores):
    r = _post(admin, "admin_app_por_email", email="  Pessoa.Avulsa@GRIDCO.com.br ", obs="cobre a gerência")
    assert r.status_code == 303 and r.headers["Location"].endswith(ABA)
    linha = _linhas(app)[0]
    assert (linha["pessoa_id"], linha["pessoa_hmac"], linha["origem"], linha["ativo"]) == (None, _h(AVULSO), "tela", "sim")
    assert linha["assinatura"] == AA.assinatura(linha, HMAC)
    assert _cifrado(linha) == {"obs": "cobre a gerência", "email": AVULSO}
    html = admin.get(ABA).get_data(as_text=True)
    assert f"{AVULSO} agora é administrador do App de Campo" in html
    vig = html.split('id="aa-vigentes"', 1)[1].split("</table>", 1)[0]
    assert AVULSO in vig and "avulso (sem ficha)" in vig and _h(AVULSO) in vig        # o Tirar leva o código
    assert _post(admin, "admin_app_tirar", pessoa_hmac=_h(AVULSO)).status_code == 303
    assert _vigentes(app) == {} and [x["ativo"] for x in _linhas(app)] == ["sim", "nao"]
    html = admin.get(ABA).get_data(as_text=True)
    assert f"{AVULSO} deixou de ser administrador do App de Campo" in html
    hist = html.split('id="aa-historico"', 1)[1].split("</table>", 1)[0]
    # as duas linhas pelo e-mail decifrado (a do tirar não leva o e-mail: vem pelo código da que pôs)
    assert hist.count(AVULSO) == 2 and hist.count("avulso (sem ficha)") == 2 and "cobre a gerência" in hist


def test_o_avulso_de_outro_dominio_ou_fora_do_formato_e_recusado(app, admin, pessoas_e_setores):
    r = _post(admin, "admin_app_por_email", email="pessoa@exemplo.com")
    html = r.get_data(as_text=True)
    assert r.status_code == 409
    assert "Só e-mail @gridco.com.br: o administrador do App entra pela conta Microsoft da Grid" in html
    assert 'value="pessoa@exemplo.com"' in html                         # o digitado volta ao campo para corrigir
    r = _post(admin, "admin_app_por_email", email="nao e email")
    assert r.status_code == 409 and "E-mail inválido" in r.get_data(as_text=True)
    assert _post(admin, "admin_app_por_email", email="  ").status_code == 400
    assert _linhas(app) == []


def test_o_avulso_com_o_codigo_de_uma_pessoa_da_lista_vai_para_ela(app, admin, pessoas_e_setores):
    """O e-mail de quem já está na lista não vira avulso: a linha vai para a pessoa (com o `pessoa_id` quando ela tem
    ficha), sem o e-mail, e a mesma pessoa não aparece duas vezes."""
    api = app.extensions["nexus_dados_sessao"]
    _aba(api, "cadastro_nexus", "pessoas", _pessoas({**EMAILS, 12: "tecnico.doze@gridco.com.br"}))
    visao.limpar()
    assert _post(admin, "admin_app_por_email", email="Tecnico.Doze@gridco.com.br").status_code == 303
    assert _post(admin, "admin_app_por_email", email=ANALISTA).status_code == 303
    linhas = _linhas(app)
    assert [(x["pessoa_id"], x["pessoa_hmac"], x["dados_cifrados"]) for x in linhas] == [
        (12, _h("tecnico.doze@gridco.com.br"), None), (None, _h(ANALISTA), None)]
    html = admin.get(ABA).get_data(as_text=True)
    vig = html.split('id="aa-vigentes"', 1)[1].split("</table>", 1)[0]
    assert "Técnico Doze" in vig and "Analista Vinte" in vig and "avulso" not in vig
    nomes = re.findall(r'<span class="aa-nome">([^<]+)</span>', _lista(html))
    assert "Técnico Doze" not in nomes and "Analista Vinte" not in nomes
    # o mesmo e-mail de novo: nada muda, e nada grava
    r = _post(admin, "admin_app_por_email", email=ANALISTA)
    assert r.status_code == 303 and len(_linhas(app)) == 2
    assert "Nada mudou: Analista Vinte já é administrador do App de Campo" in admin.get(ABA).get_data(as_text=True)


def test_o_avulso_com_o_codigo_de_duas_fichas_e_recusado(app, admin, pessoas_e_setores):
    """O mesmo e-mail em duas fichas (sem ligação a desempatar) não é de nenhuma: pelo avulso também não entra."""
    api = app.extensions["nexus_dados_sessao"]
    _aba(api, "cadastro_nexus", "pessoas", _pessoas({**EMAILS, 10: "dupla@gridco.com.br", 12: "dupla@gridco.com.br"}))
    visao.limpar()
    r = _post(admin, "admin_app_por_email", email="dupla@gridco.com.br")
    assert r.status_code == 409 and "o mesmo código está em mais de uma ficha" in r.get_data(as_text=True)
    assert _linhas(app) == []


def test_nenhum_email_em_claro_na_linha_gravada(app, admin, pessoas_e_setores):
    assert _post(admin, "admin_app_por_email", email=AVULSO, obs="cobre a gerência").status_code == 303
    assert _post(admin, "admin_app_por", pessoa=f"codigo:{_h(GERENTE)}").status_code == 303
    assert _post(admin, "admin_app_tirar", pessoa_hmac=_h(AVULSO)).status_code == 303
    txt = open(app.config["NEXUS_ADMINS_APP_ARQUIVO"], encoding="utf-8").read()
    assert len(_linhas(app)) == 3
    assert "@" not in txt and "gridco" not in txt and "avulsa" not in txt and "gerente" not in txt.lower()
    assert "gerência" not in txt and "gerencia" not in txt


def test_sem_o_fracttal_quem_nao_tem_ficha_fica_sem_radio(app, admin):
    """O Fracttal fora (aqui, o teste sem fornecedor e sem cópia): quem tem a ligação de hoje no banco segue na lista,
    pelo número do usuário do Fracttal, mas sem rádio: sem o nome, não dá para conferir quem é, e nunca se dá acesso a um
    usuário sem nome. A ficha que a ligação aponta segue escolhível (o nome é o da ficha)."""
    _ligacoes(app.extensions["nexus_dados_sessao"])
    html = admin.get(ABA).get_data(as_text=True)
    assert "Sem o pessoal do Fracttal" in html
    item = _item(_lista(html), "Usuário do Fracttal 510")
    assert "PCM" in item and "<input" not in item
    assert "o Fracttal não respondeu: sem o nome, não dá para conferir quem é" in item
    assert 'value="11"' in _item(_lista(html), "Supervisora Onze")
    r = _post(admin, "admin_app_por", pessoa=f"codigo:{_h(ANALISTA)}")
    assert r.status_code == 409 and "o Fracttal não respondeu" in r.get_data(as_text=True)
    r = _post(admin, "admin_app_por_email", email=ANALISTA)                 # nem pela porta do avulso
    assert r.status_code == 409 and "o Fracttal não respondeu" in r.get_data(as_text=True)
    assert _linhas(app) == []


def test_a_aba_nunca_le_o_fracttal_na_hora_e_mostra_a_idade_da_copia(app, admin, monkeypatch):
    """2ª revisão de 05/11/2026 (o custo): a aba lê só a cópia de Pessoas e setores e pede a leitura nova por trás, num GET
    ou num POST; sem cópia, vale o caminho fechado (sem rádio para quem não tem ficha). A cópia velha mostra a idade."""
    _ligacoes(app.extensions["nexus_dados_sessao"])
    pedidos, renovar = [], []
    fracttal.usar_fornecedor(lambda path: pedidos.append(path) or {"data": PESSOAL})
    monkeypatch.setattr(TF, "_renovar", lambda a: (renovar.append(1), TF._TELA.update(renovando=False)))

    def pediu(n):
        """A leitura por trás é uma thread: espera ela ser pedida n vezes (e acabar)."""
        fim = time.monotonic() + 5
        while len(renovar) < n or TF._TELA["renovando"]:
            assert time.monotonic() < fim, renovar
            time.sleep(0.01)
        return len(renovar)
    codigo = _codigo(admin)                                            # um GET
    assert pediu(1) == 1
    html = admin.get(ABA).get_data(as_text=True)
    assert pediu(2) == 2 and pedidos == [] and "<input" not in _item(_lista(html), "Usuário do Fracttal 510")
    assert _post(admin, "admin_app_por", codigo, pessoa="10").status_code == 303
    assert pediu(3) == 3 and pedidos == []
    _com_o_fracttal(app, PESSOAL)
    pedidos.clear()
    TF._TELA["g"]["t"] -= TF.RELACAO_S + 12 * 60                      # a cópia de 14 minutos atrás
    html = admin.get(ABA).get_data(as_text=True)
    assert pediu(4) == 4 and pedidos == []
    assert "lido há 14 min" in html and 'value="codigo:' in _item(_lista(html), "Analista Vinte")


def test_a_ligacao_para_a_ficha_desligada_fica_sem_radio_e_o_recontratado_entra_pela_ficha_nova(app, admin):
    """A ligação de Pessoas e setores feita antes do desligamento aponta para a ficha 13, desligada. O usuário do Fracttal
    fica na lista sem rádio, com o porquê e o aviso para refazer a ligação; a ficha nova (15), ativa, com o mesmo e-mail,
    fica com o código e é escolhível (a ligação velha não dá código à desligada)."""
    api = app.extensions["nexus_dados_sessao"]
    _aba(api, "cadastro_nexus", "pessoas", _pessoas({**EMAILS, 15: EMAILS[13]}, extra=[(15, "Técnico Quinze")]))
    _ligacoes(api, {"decidida_em": "2026-10-14T12:00:00Z", "data_id": 20261014, "fracttal_id": 530, "pessoa_id": 13,
                    "pessoa_ligada_por": "e-mail", "pessoa_hmac": _h(EMAILS[13]), "setor_id": 1})
    _com_o_fracttal(app, PESSOAL + [_usuario(530, "Técnico Treze", EMAILS[13])])
    lista = _lista(admin.get(ABA).get_data(as_text=True))
    velho = _item(lista, "Técnico Treze")
    assert "<input" not in velho and "a ficha está desligada ou excluída no cadastro" in velho
    assert "a ligação em Pessoas e setores aponta para uma ficha desligada: refaça a ligação" in velho
    assert 'value="15"' in _item(lista, "Técnico Quinze") and "sem código" not in _item(lista, "Técnico Quinze")
    r = _post(admin, "admin_app_por", pessoa="fracttal:530")
    assert r.status_code == 409 and "a ficha está desligada ou excluída no cadastro" in r.get_data(as_text=True)
    assert _post(admin, "admin_app_por", pessoa="15").status_code == 303
    assert [(x["pessoa_id"], x["pessoa_hmac"]) for x in _linhas(app)] == [(15, _h(EMAILS[13]))]


def test_o_palpite_pelo_email_para_a_ficha_desligada_fica_sem_radio(app, admin, pessoas_e_setores):
    """Sem ligação, a aba de Pessoas e setores liga pelo e-mail o usuário do Fracttal à ficha 13, desligada: ele fica na
    lista sem rádio, com o porquê (sem o aviso de refazer a ligação, que não existe)."""
    _com_o_fracttal(app, PESSOAL + [_usuario(531, "Técnico Treze", EMAILS[13])])
    item = _item(_lista(admin.get(ABA).get_data(as_text=True)), "Técnico Treze")
    assert "<input" not in item and "a ficha está desligada ou excluída no cadastro" in item
    assert "refaça a ligação" not in item
    r = _post(admin, "admin_app_por", pessoa=f"codigo:{_h(EMAILS[13])}")
    assert r.status_code == 409 and _linhas(app) == []


def test_a_conta_do_fracttal_desativada_so_ganha_etiqueta(app, admin, pessoas_e_setores):
    """O login do App é pela Microsoft: a conta do Fracttal desativada não impede, só avisa."""
    inativa = dict(_usuario(511, "Gerente Trinta", GERENTE), account_active=False)
    _com_o_fracttal(app, [inativa if p["id_personnel"] == 511 else p for p in PESSOAL])
    item = _item(_lista(admin.get(ABA).get_data(as_text=True)), "Gerente Trinta")
    assert "conta do Fracttal desativada" in item and f'value="codigo:{_h(GERENTE)}"' in item
    assert _post(admin, "admin_app_por", pessoa=f"codigo:{_h(GERENTE)}").status_code == 303


def test_sem_a_chave_do_cadastro_quem_nao_tem_ficha_fica_travado(app, admin, pessoas_e_setores):
    """Sem a chave do cadastro o Nexus não lê o e-mail das fichas: a ficha e a conta do Fracttal com o mesmo e-mail
    apareceriam duas vezes, e a linha iria sem `pessoa_id`. Quem não tem ficha fica sem rádio, com o aviso geral."""
    app.config.pop("NEXUS_CHAVE_CADASTRO")
    visao.limpar()
    _com_o_fracttal(app, PESSOAL)
    html = admin.get(ABA).get_data(as_text=True)
    assert "Sem a chave do cadastro, o Nexus não confere os códigos" in html
    item = _item(_lista(html), "Analista Vinte")
    assert "<input" not in item and "sem a chave do cadastro" in item
    assert _post(admin, "admin_app_por", pessoa=f"codigo:{_h(ANALISTA)}").status_code == 409
    assert _linhas(app) == []


def test_o_codigo_forjado_e_o_fracttal_sem_email_dao_409(app, admin, pessoas_e_setores):
    r = _post(admin, "admin_app_por", pessoa="codigo:" + "ab" * 12)          # fora da lista
    assert r.status_code == 409 and "nem em Pessoas e setores" in r.get_data(as_text=True)
    r = _post(admin, "admin_app_por", pessoa="fracttal:513")                 # a conta do Fracttal sem e-mail
    assert r.status_code == 409 and "sem e-mail no usuário do Fracttal" in r.get_data(as_text=True)
    assert _linhas(app) == []


def test_o_marcador_de_outro_dominio_e_quem_continua_escolhivel(app, admin, pessoas_e_setores):
    """Levi, 05/11/2026: "Deixar aparecer". Quem tem o e-mail de outro domínio fica na lista, escolhível, com o marcador
    (comparado exato com @gridco.com.br: o gridco.com sem o .br também é outro)."""
    _com_o_fracttal(app, PESSOAL + [_usuario(540, "Consultora Externa", "consultora@gridco.com")])
    html = admin.get(ABA).get_data(as_text=True)
    lista = _lista(html)
    marca = "outro domínio: o App não o reconhece como administrador"
    for nome in ("Supervisora Onze", "Técnico Dez", "Consultora Externa"):
        assert marca in _item(lista, nome) and "<input" in _item(lista, nome)
    for nome in ("Analista Vinte", "Gerente Trinta", "Pessoa Sem Email", "Técnico Doze"):
        assert marca not in _item(lista, nome)
    assert _post(admin, "admin_app_por", pessoa="10").status_code == 303
    vig = admin.get(ABA).get_data(as_text=True).split('id="aa-vigentes"', 1)[1].split("</table>", 1)[0]
    assert "Técnico Dez" in vig and marca in vig


def test_a_explicacao_mora_no_explica_do_titulo(app, admin):
    """O padrão de 05/11/2026 (DESIGN.md): o "Como vale." e a regra do domínio no "!" amarelo ao lado do título."""
    html = admin.get(ABA).get_data(as_text=True)
    caixa = html.split('<details class="gc-explica">', 1)[1].split("</details>", 1)[0]
    assert "<b>Como vale.</b>" in caixa and "com a lista vazia ele não tira ninguém" in caixa
    assert "outro domínio" in caixa and "@gridco.com.br" in caixa
    assert "<strong>Como vale.</strong>" not in html


def test_quem_vale_sem_ficha_e_hoje_tem_ficha_ganha_o_aviso(app, admin, pessoas_e_setores):
    """O inverso da regra do "Nada mudou": a linha posta sem ficha segue sem `pessoa_id` quando a pessoa ganha ficha; a
    linha dos que valem avisa para tirar e pôr de novo."""
    assert _post(admin, "admin_app_por", pessoa=f"codigo:{_h(GERENTE)}").status_code == 303
    api = app.extensions["nexus_dados_sessao"]
    _aba(api, "cadastro_nexus", "pessoas", _pessoas({**EMAILS, 12: GERENTE}))     # a ficha 12 com o e-mail dela
    visao.limpar()
    vig = admin.get(ABA).get_data(as_text=True).split('id="aa-vigentes"', 1)[1].split("</table>", 1)[0]
    assert "esta pessoa tem ficha agora: tire e ponha de novo para ligar à ficha" in vig


def test_a_pagina_aberta_antes_da_troca_ainda_poe_pelo_campo_de_antes(app, admin):
    """O rádio se chamava `pessoa_id` até a 2ª volta de 05/11/2026: a página aberta antes do deploy segue gravando."""
    assert _post(admin, "admin_app_por", pessoa_id="10").status_code == 303
    assert _linhas(app)[0]["pessoa_id"] == 10
