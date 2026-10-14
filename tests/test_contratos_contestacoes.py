"""Contratos e clientes → Contestações (Levi, 13/10/2026: "em contratos e clientes no Nexus pode ter um lugar para essas
contestações separando setores!"). O Dashboard Thopen grava o livro thopen_contestacoes com o que é do cliente cifrado
pela chave PÚBLICA; aqui só a privada abre. Banco falso (tests/pg_falso.py); a cifra destes testes segue a MESMA receita
do thopen/contestacao_banco.py, e com PLATAFORMA_REPO apontando para o clone da plataforma o teste cruzado cifra com o
código de lá."""
import base64
import importlib.util
import json
import os
import sys

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pg_falso import ApiPGFalsa

from nexus.contratos import contestacoes as CT


def _b64e(b):
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _par():
    k = X25519PrivateKey.generate()
    return (_b64e(k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                  serialization.NoEncryption())),
            _b64e(k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)))


def _cifrar(texto, ctx, pub_b64):
    """A receita do 5080 (thopen/contestacao_banco.cifrar): X25519 efêmera + HKDF-SHA256 (sal = a pública efêmera) +
    AES-256-GCM com o contexto como dado associado."""
    pub = X25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(pub_b64 + "=" * (-len(pub_b64) % 4)))
    ef = X25519PrivateKey.generate()
    pub_ef = ef.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    chave = HKDF(algorithm=hashes.SHA256(), length=32, salt=pub_ef, info=b"thopen-contestacao/v1").derive(ef.exchange(pub))
    nonce = os.urandom(12)
    return "cx1:" + _b64e(pub_ef + nonce + AESGCM(chave).encrypt(nonce, texto.encode("utf-8"), ctx.encode("utf-8")))


PRIV, PUB = _par()


def _linha(lid, setor, itens, quando, usina="Guaratinguetá V", avisado="sim", dados=None, cid="c1"):
    dados = dados or {"nome": "Ana Souza", "contato": "ana@cliente.com.br", "mensagem": "A geração do dia 06 parece baixa.",
                      "tela": {"geracao": "4.429 kWh", "disp": "100,0%"}, "itens": itens.split(";")}
    return {"id": lid, "contestacao_id": cid, "recebida_em": quando, "data_id_recebida": 20261013,
            "data_id_contestada_ini": 20261006, "data_id_contestada_fim": 20261006, "usina": usina, "usina_id": 86,
            "setor": setor, "itens": itens, "avisado_teams": avisado, "origem": "dashboard_thopen",
            "dados_cifrados": _cifrar(json.dumps(dados, ensure_ascii=False), CT.contexto(lid), PUB)}


@pytest.fixture
def banco(app):
    api = ApiPGFalsa()
    linhas = [_linha("a1", "performance", "geracao;disponibilidade", "2026-10-13T12:00:00Z"),
              _linha("a2", "zeladoria", "ronda", "2026-10-13T12:00:00Z", avisado="não"),
              _linha("b1", "performance", "string", "2026-10-13T15:30:00Z", usina="Altair", cid="c2")]
    cab = list(linhas[0])
    api.workbooks[CT.LIVRO] = {}
    api._id(CT.LIVRO, CT.ABA)["linhas"] = [{"headers": cab, "values": [l[c] for c in cab]} for l in linhas]
    app.config.update(GRIDCO_DB_API="http://pg.falso", NEXUS_CONTESTACAO_CHAVE_PRIVADA=PRIV)
    app.extensions["nexus_dados_sessao"] = api
    with app.app_context():
        yield api
    app.extensions.pop("nexus_dados_sessao", None)


def test_separa_por_setor_e_abre_so_com_a_privada(banco, app):
    d = CT.contestacoes()
    assert d["contagem"] == {"performance": 2, "zeladoria": 1} and d["erro"] is None and not d["sem_chave"]
    perf = d["por_setor"]["performance"]
    assert [x["id"] for x in perf] == ["b1", "a1"]                               # a mais nova em cima
    a1 = perf[1]
    assert (a1["nome"], a1["contato"], a1["aberto"]) == ("Ana Souza", "ana@cliente.com.br", True)
    assert a1["itens"] == ["Geração", "Disponibilidade"] and ("Geração", "4.429 kWh") in a1["tela"]
    assert a1["quando"].strftime("%d/%m %H:%M") == "13/10 09:00"                  # recebida em UTC, mostrada em Brasília
    assert d["por_setor"]["zeladoria"][0]["avisado"] is False


def test_sem_a_chave_lista_sem_os_dados_do_cliente(banco, app):
    app.config["NEXUS_CONTESTACAO_CHAVE_PRIVADA"] = None
    d = CT.contestacoes()
    assert d["sem_chave"] and d["contagem"]["performance"] == 2
    assert all(x["nome"] == "" and x["aberto"] is None for x in d["por_setor"]["performance"])


def test_cifra_copiada_para_outra_linha_nao_abre(banco, app):
    aba = banco._id(CT.LIVRO, CT.ABA)["linhas"]
    i = aba[0]["headers"].index("dados_cifrados")
    aba[2]["values"][i] = aba[0]["values"][i]                                     # a cifra da a1 na linha da b1
    b1 = CT.contestacoes()["por_setor"]["performance"][0]
    assert b1["id"] == "b1" and b1["aberto"] is False and b1["nome"] == ""


def test_tela_tem_uma_aba_por_setor(banco, logado):
    r = logado.get("/t/contratos/contestacoes")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Performance<i>2</i>" in html and "Zeladoria<i>1</i>" in html
    assert "Ana Souza" in html and "ana@cliente.com.br" in html and "Altair" in html
    z = logado.get("/t/contratos/contestacoes?setor=zeladoria").get_data(as_text=True)
    assert "não recebeu" in z and "Altair" not in z


def test_teste_cruzado_com_o_codigo_do_5080():
    raiz = os.environ.get("PLATAFORMA_REPO", "")
    arq = os.path.join(raiz, "thopen", "contestacao_banco.py")
    if not raiz or not os.path.exists(arq):
        pytest.skip("PLATAFORMA_REPO não aponta para um clone com thopen/contestacao_banco.py")
    sys.path.insert(0, os.path.join(raiz, "thopen"))
    try:
        spec = importlib.util.spec_from_file_location("contestacao_banco_5080", arq)
        cb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cb)
        priv, pub = cb.gerar_par()
        assert cb.LIVRO == CT.LIVRO and cb.ABA == CT.ABA and cb.PREFIXO == CT.PREFIXO
        c = cb.cifrar("Ana", cb.contexto("x1"), pub)
        assert CT.decifrar(c, CT.contexto("x1"), priv) == "Ana"
    finally:
        sys.path.remove(os.path.join(raiz, "thopen"))
