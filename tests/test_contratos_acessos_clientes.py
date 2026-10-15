"""Contratos e clientes → Acessos dos clientes (14/10/2026, o login por pessoa do Dashboard Thopen). O Nexus grava as
contas no livro nexus_acessos_clientes com o nome e o e-mail só cifrados (selados para a PÚBLICA do 5080 e no Cofre do
Nexus) e o link de definir senha só como sha256. Banco falso (tests/pg_falso.py); a abertura destes testes segue a MESMA
receita do thopen/acessos.py, e com PLATAFORMA_REPO apontando para o clone da plataforma o teste cruzado abre com o
código de lá."""
import base64
import hashlib
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pg_falso import ApiPGFalsa

from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.contratos import acessos_clientes as AC
from nexus.dados import catalogo


def _b64e(b):
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _par():
    k = X25519PrivateKey.generate()
    return (_b64e(k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                  serialization.NoEncryption())),
            _b64e(k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)))


def _abrir(selo, ctx, priv_b64):
    """A receita do 5080 (thopen/acessos.abrir)."""
    bruto = _b64d(selo[len("cx1:"):])
    pub_ef, nonce, corpo = bruto[:32], bruto[32:44], bruto[44:]
    priv = X25519PrivateKey.from_private_bytes(_b64d(priv_b64))
    chave = HKDF(algorithm=hashes.SHA256(), length=32, salt=pub_ef, info=b"thopen-acessos/v1").derive(
        priv.exchange(X25519PublicKey.from_public_bytes(pub_ef)))
    return AESGCM(chave).decrypt(nonce, corpo, ctx.encode("utf-8")).decode("utf-8")


PRIV, PUB = _par()
CHAVE_CAD = gerar_chave()


@pytest.fixture
def banco(app):
    api = ApiPGFalsa()
    app.config.update(GRIDCO_DB_API="http://pg.falso", GRIDCO_SQL_TOKEN="tk", NEXUS_ACESSOS_5080_PUBLICA=PUB,
                      NEXUS_CHAVE_CADASTRO=CHAVE_CAD, NEXUS_PESSOA_HMAC="hmac-teste")
    app.extensions["nexus_dados_sessao"] = api
    with app.app_context():
        yield api
    app.extensions.pop("nexus_dados_sessao", None)


def _token(link):
    m = re.fullmatch(r"https://app\.gridco\.com\.br/performance/convite/([A-Za-z0-9_-]{40,})", link)
    assert m, link
    return m.group(1)


def test_cria_a_conta_cifrada_e_o_link_de_uso_unico(banco):
    conta, link = AC.criar("  Ana   Souza ", "Ana@Thopen.com.br", ["Polaris", "Thopen"], "cliente",
                           {"email": "levi@gridco.com.br"})
    tk = _token(link)
    [l] = banco.linhas(AC.LIVRO, AC.ABA)
    assert list(l) == list(AC.CAB)
    assert (l["carteiras"], l["papel"], l["status"]) == ("Thopen;Polaris", "cliente", "ativa")   # na ordem do painel
    assert l["convite_hash"] == hashlib.sha256(tk.encode()).hexdigest()
    expira = datetime.fromisoformat(l["convite_expira"].replace("Z", "+00:00"))
    assert timedelta(hours=71) < expira - datetime.now(timezone.utc) <= timedelta(hours=72)
    # a API do banco tem leitura aberta: nada da pessoa em claro, nem o token
    tudo = json.dumps(l, ensure_ascii=False, default=str).lower()
    # o nome e o e-mail inteiros: um pedaço curto ("ana") aparece por acaso numa cifra em base64
    assert "ana souza" not in tudo and "ana@thopen.com.br" not in tudo and tk.lower() not in tudo
    cid = l["conta_id"]
    assert json.loads(_abrir(l["dados_5080"], f"nexus_acessos_clientes/{cid}/dados_5080", PRIV)) == \
        {"nome": "Ana Souza", "email": "ana@thopen.com.br"}
    assert json.loads(Cofre(CHAVE_CAD).decifrar(l["dados_nexus"], AC.ctx_nexus(cid)))["email"] == "ana@thopen.com.br"
    assert l["alterada_por_hmac"] and "levi" not in l["alterada_por_hmac"]
    assert conta == {"conta_id": cid, "nome": "Ana Souza", "email": "ana@thopen.com.br"}


def test_selo_preso_a_conta(banco):
    AC.criar("Ana", "ana@thopen.com.br", ["Thopen"], "cliente", None)
    [l] = banco.linhas(AC.LIVRO, AC.ABA)
    with pytest.raises(Exception):
        _abrir(l["dados_5080"], "nexus_acessos_clientes/outra/dados_5080", PRIV)


def test_recusas(banco, app):
    AC.criar("Ana", "ana@thopen.com.br", ["Thopen"], "cliente", None)
    for args, frase in ((("Ana 2", "ANA@thopen.com.br", ["Copel"], "cliente"), "Já existe"),
                        (("", "x@y.com", ["Thopen"], "cliente"), "nome"),
                        (("Bia", "sem-arroba", ["Thopen"], "cliente"), "e-mail"),
                        (("Bia", "bia@y.com", [], "cliente"), "carteira")):
        with pytest.raises(AC.Recusada, match=frase):
            AC.criar(*args, None)
    app.config.pop("NEXUS_ACESSOS_5080_PUBLICA")
    with pytest.raises(AC.Recusada, match="chave pública"):
        AC.criar("Bia", "bia@y.com", ["Thopen"], "cliente", None)
    assert len(banco.linhas(AC.LIVRO, AC.ABA)) == 1


def test_papel_grid_ve_todas_as_carteiras(banco):
    AC.criar("Levi", "levi@gridco.com.br", [], "grid", None)
    [l] = banco.linhas(AC.LIVRO, AC.ABA)
    assert (l["papel"], l["carteiras"]) == ("grid", "Thopen;Copel;Matrix;Polaris")


def test_link_novo_troca_o_anterior_e_sela_de_novo_para_a_publica_atual(banco, app):
    _, link1 = AC.criar("Ana", "ana@thopen.com.br", ["Thopen"], "cliente", None)
    [l] = banco.linhas(AC.LIVRO, AC.ABA)
    priv2, pub2 = _par()                                        # o par do painel foi trocado
    app.config["NEXUS_ACESSOS_5080_PUBLICA"] = pub2
    link2 = AC.gerar_link(l["conta_id"], None)
    [l2] = banco.linhas(AC.LIVRO, AC.ABA)
    assert _token(link2) != _token(link1)
    assert l2["convite_hash"] == hashlib.sha256(_token(link2).encode()).hexdigest()
    assert json.loads(_abrir(l2["dados_5080"], AC.ctx_5080(l["conta_id"]), priv2))["nome"] == "Ana"


def test_desativar_apaga_o_link_e_bloqueia_link_novo(banco):
    AC.criar("Ana", "ana@thopen.com.br", ["Thopen"], "cliente", None)
    cid = banco.linhas(AC.LIVRO, AC.ABA)[0]["conta_id"]
    AC.definir_status(cid, False, None)
    l = banco.linhas(AC.LIVRO, AC.ABA)[0]
    assert l["status"] == "desativada" and not l["convite_hash"]
    with pytest.raises(AC.Recusada, match="Reative"):
        AC.gerar_link(cid, None)
    AC.definir_status(cid, True, None)
    assert banco.linhas(AC.LIVRO, AC.ABA)[0]["status"] == "ativa"
    with pytest.raises(AC.Recusada, match="não encontrada"):
        AC.definir_status("nao-existe", False, None)


def test_lista_com_a_senha_do_livro_do_5080(banco):
    _, link = AC.criar("Ana", "ana@thopen.com.br", ["Thopen"], "cliente", None)
    AC.criar("Bia", "bia@copel.com", ["Copel"], "cliente", None)
    d = AC.contas()
    assert [c["nome"] for c in d["contas"]] == ["Ana", "Bia"] and all(c["link"] == "pendente" for c in d["contas"])
    # a Ana definiu a senha pelo link: o 5080 grava a linha com o hash do link
    ana = next(c for c in d["contas"] if c["nome"] == "Ana")
    h = hashlib.sha256(_token(link).encode()).hexdigest()
    banco.workbooks[AC.LIVRO_SENHAS] = {}
    banco._id(AC.LIVRO_SENHAS, AC.ABA_SENHAS)["linhas"] = [
        {"headers": ["id", "conta_id", "definida_em", "convite_hash", "senha_cifrada"],
         "values": ["s1", ana["conta_id"], "2026-10-14T13:00:00Z", h, "cs1:xx"]}]
    ana = next(c for c in AC.contas()["contas"] if c["nome"] == "Ana")
    assert ana["link"] == "" and ana["senha_em"] == "14/10/2026" and ana["email"] == "ana@thopen.com.br"


def test_banco_fora_diz_e_nao_lista_vazio(app):
    class Fora:
        def get(self, *a, **k):
            raise ConnectionError("fora")
    app.config.update(GRIDCO_DB_API="http://pg.falso")
    app.extensions["nexus_dados_sessao"] = Fora()
    try:
        with app.app_context():
            d = AC.contas()
        assert d["erro"] and d["contas"] == []
    finally:
        app.extensions.pop("nexus_dados_sessao", None)


def _codigo(cli):
    html = cli.get("/t/contratos/acessos").get_data(as_text=True)
    return re.search(r'name="codigo" value="([^"]+)"', html).group(1)


def test_tela_cria_e_mostra_o_link_uma_vez(banco, logado):
    cod = _codigo(logado)
    r = logado.post("/t/contratos/acessos", data={"codigo": cod, "acao": "criar", "nome": "Ana Souza",
                                                  "email": "ana@thopen.com.br", "carteira": ["Thopen"], "papel": "cliente"},
                    headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 303
    html = logado.get("/t/contratos/acessos").get_data(as_text=True)
    assert "/performance/convite/" in html and "Ana Souza" in html and "link pendente" in html
    assert "/performance/convite/" not in logado.get("/t/contratos/acessos").get_data(as_text=True)   # uma vez só


def test_tela_recusa_sem_codigo_de_outro_site_e_quem_nao_e_admin(banco, logado):
    dados = {"acao": "criar", "nome": "X", "email": "x@y.com", "carteira": ["Thopen"]}
    assert logado.post("/t/contratos/acessos", data=dados, headers={"Sec-Fetch-Site": "same-origin"}).status_code == 403
    cod = _codigo(logado)
    assert logado.post("/t/contratos/acessos", data={**dados, "codigo": cod},
                       headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    with logado.session_transaction() as s:
        s["admin"] = False
    r = logado.post("/t/contratos/acessos", data={**dados, "codigo": cod}, headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 403
    assert banco.linhas(AC.LIVRO, AC.ABA) == []


def test_recusa_volta_com_o_que_foi_digitado(banco, logado):
    cod = _codigo(logado)
    r = logado.post("/t/contratos/acessos", data={"codigo": cod, "acao": "criar", "nome": "Bia", "email": "bia@copel.com",
                                                  "papel": "cliente"}, headers={"Sec-Fetch-Site": "same-origin"})
    html = r.get_data(as_text=True)
    assert r.status_code == 400 and "carteira" in html and 'value="bia@copel.com"' in html


def test_catalogo_registra_os_dois_livros():
    l = catalogo.LIVRO_POR_NOME["nexus_acessos_clientes"]
    assert l.abas == (AC.ABA,) and all(catalogo.aba_segue_a_regra(a) for a in l.abas)
    assert any(c.livro == "thopen_acessos" and AC.ABA_SENHAS in c.abas for c in catalogo.CONHECIDAS)
    from nexus.dados import telas
    assert ("igual", "thopen_acessos", "Dashboard Thopen (5080)") in telas.QUEM_GRAVA_ORIGEM


def test_chave_publica_pela_tela_de_chaves():
    from nexus.auth import chaves
    conferir = chaves.CHAVES["NEXUS_ACESSOS_5080_PUBLICA"]["conferir"]
    assert "válida" in conferir(PUB)
    with pytest.raises(chaves.Recusada):
        conferir("isto-nao-e-chave")


def test_teste_cruzado_com_o_codigo_do_5080():
    raiz = os.environ.get("PLATAFORMA_REPO", "")
    arq = os.path.join(raiz, "thopen", "acessos.py")
    if not raiz or not os.path.exists(arq):
        pytest.skip("PLATAFORMA_REPO não aponta para um clone com thopen/acessos.py")
    sys.path.insert(0, os.path.join(raiz, "thopen"))
    try:
        spec = importlib.util.spec_from_file_location("acessos_5080", arq)
        a = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(a)
        assert (a.LIVRO_CONTAS, a.ABA_CONTAS) == (AC.LIVRO, AC.ABA)
        assert (a.LIVRO_SENHAS, a.ABA_SENHAS) == (AC.LIVRO_SENHAS, AC.ABA_SENHAS)
        assert tuple(a.CARTEIRAS) == AC.CARTEIRAS and a.ctx_conta("c9") == AC.ctx_5080("c9")
        priv, pub = a.gerar_par()
        assert a.abrir(AC.selar("Ana", AC.ctx_5080("c9"), pub), a.ctx_conta("c9"), priv) == "Ana"
        assert a._hash_token("tk") == hashlib.sha256(b"tk").hexdigest()
    finally:
        sys.path.remove(os.path.join(raiz, "thopen"))
