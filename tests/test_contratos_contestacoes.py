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
    assert d["contagem"] == {"performance": 2, "cos": 0, "zeladoria": 1} and d["erro"] is None and not d["sem_chave"]
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
        # os setores do 5080 (o canal de cada item) são os das abas daqui (15/10/2026: o COS entrou dos dois lados)
        import contestacao as c5080
        assert set(c5080.CANAL) == {s for s, _ in CT.SETORES} and set(c5080.ITENS.values()) <= set(c5080.CANAL)
    finally:
        sys.path.remove(os.path.join(raiz, "thopen"))


# ── O acompanhamento (Levi, 15/10/2026): "Pegar para mim", o card das atualizações e o setor que só vê o seu ──────────
from nexus.cadastro.cifra import gerar_chave  # noqa: E402
from nexus.contratos import tratamento as TR  # noqa: E402

ANA = {"email": "ana.lima@gridco.com.br", "nome": "Ana Lima"}
BETO = {"email": "beto.souza@gridco.com.br", "nome": "Beto Souza"}


@pytest.fixture
def trat(banco, app):
    app.config.update(NEXUS_CHAVE_CADASTRO=gerar_chave(), NEXUS_PESSOA_HMAC="hmac-teste", GRIDCO_SQL_TOKEN="tk")
    return banco


def _como(cli, usuario, admin=False):
    with cli.session_transaction() as s:
        s["logado"], s["admin"], s["usuario"] = True, admin, usuario
    return cli


def test_pegar_para_mim_e_so_o_administrador_assume(trat, app):
    TR.pegar("a1", "performance", ANA, admin=False)
    r = TR.estado()["a1"]["responsavel"]
    assert r["nome"] == "Ana Lima" and r["hmac"] == TR.codigo(ANA)
    with pytest.raises(TR.Recusada, match="já é sua"):
        TR.pegar("a1", "performance", ANA, admin=False)
    with pytest.raises(TR.Recusada, match="já tem responsável"):
        TR.pegar("a1", "performance", BETO, admin=False)
    TR.pegar("a1", "performance", BETO, admin=True)                     # o administrador assume
    assert TR.estado()["a1"]["responsavel"]["nome"] == "Beto Souza"
    with pytest.raises(TR.Recusada, match="login"):                       # a senha de administrador não diz quem é
        TR.pegar("b1", "performance", None, admin=True)
    # a API do banco tem leitura aberta: nem o nome nem o e-mail em claro
    lin = trat.linhas(TR.LIVRO, TR.ABA)
    assert len(lin) == 2 and list(lin[0]) == list(TR.CAB)
    # o nome e o e-mail inteiros: um pedaço curto ("ana") aparece por acaso numa cifra em base64 (~1 em 150 rodadas)
    claro = json.dumps(lin, ensure_ascii=False, default=str).lower()
    assert "ana lima" not in claro and ANA["email"] not in claro and "beto souza" not in claro


def test_so_o_responsavel_escreve_e_a_atualizacao_fica_com_a_hora(trat, app):
    with pytest.raises(TR.Recusada, match="Pegar para mim"):
        TR.atualizar("a1", "performance", ANA, "Verificando com a equipe")
    TR.pegar("a1", "performance", ANA, admin=False)
    with pytest.raises(TR.Recusada, match="Escreva"):
        TR.atualizar("a1", "performance", ANA, "   ")
    TR.atualizar("a1", "performance", ANA, "Verificando   com a equipe\n\nOS aberta no Fracttal")
    with pytest.raises(TR.Recusada, match="Só o responsável"):
        TR.atualizar("a1", "performance", BETO, "outro")
    (a,) = TR.estado()["a1"]["atualizacoes"]
    assert a["texto"] == "Verificando com a equipe\n\nOS aberta no Fracttal" and a["nome"] == "Ana Lima"
    assert a["quando"] is not None and "às" in a["quando_txt"]
    assert "verificando" not in json.dumps(trat.linhas(TR.LIVRO, TR.ABA), default=str).lower()


def test_o_setor_so_ve_a_contestacao_dele_e_o_administrador_ve_todas(trat, app, cliente, monkeypatch):
    from nexus.auth import setor_telas as ST
    setor = {"v": {"id": 3, "nome": "Zeladoria"}}
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(), "setor": setor["v"], "erro": ""})
    _como(cliente, ANA)
    html = cliente.get("/t/contratos/contestacoes").get_data(as_text=True)
    assert "Zeladoria<i>1</i>" in html and "Performance<i>" not in html and "Altair" not in html
    # a de outro setor nem abre (o servidor barra, não só a tela)
    assert cliente.get("/t/contratos/contestacoes?setor=performance").get_data(as_text=True).count("Altair") == 0
    assert cliente.get("/t/contratos/contestacoes/a1/card").status_code == 404
    assert cliente.post("/t/contratos/contestacoes/a1/pegar", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 404
    assert cliente.get("/t/contratos/contestacoes/a2/card").status_code == 200
    setor["v"] = {"id": 1, "nome": "Engenharia"}                              # setor sem contestação: nenhuma
    html = cliente.get("/t/contratos/contestacoes").get_data(as_text=True)
    assert "Nenhuma contestação para o seu setor" in html and "o seu setor é Engenharia" in html
    app.config["NEXUS_ADMINS"] = BETO["email"]                              # administrador (a lista de agora): todas
    _como(cliente, BETO, admin=True)
    html = cliente.get("/t/contratos/contestacoes").get_data(as_text=True)
    assert "Performance<i>2</i>" in html and "Zeladoria<i>1</i>" in html


def test_tela_pegar_abrir_o_card_e_escrever(trat, app, cliente):
    _como(cliente, ANA)
    html = cliente.get("/t/contratos/contestacoes").get_data(as_text=True)
    assert html.count(">Pegar para mim</button>") == 2 and 'data-ct-card="/t/contratos/contestacoes/a1/card"' in html
    r = cliente.post("/t/contratos/contestacoes/a1/pegar", headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 303 and r.headers["Location"].endswith("/t/contratos/contestacoes?setor=performance")
    html = cliente.get("/t/contratos/contestacoes").get_data(as_text=True)
    assert "agora é sua" in html and "Ana Lima (você)" in html and "0 atualizações" in html
    card = cliente.get("/t/contratos/contestacoes/a1/card").get_data(as_text=True)
    assert "data-ct-atualizar" in card and "Nenhuma atualização ainda" in card and "Ana Souza" in card
    r = cliente.post("/t/contratos/contestacoes/a1/atualizacao", data={"texto": "Liguei para o cliente"},
                     headers={"Sec-Fetch-Site": "same-origin"})
    card = r.get_data(as_text=True)
    assert r.status_code == 200 and "Atualização salva" in card and "Liguei para o cliente" in card
    # outra pessoa do setor lê o card, mas não escreve; de outro site, nada grava
    _como(cliente, BETO)
    card = cliente.get("/t/contratos/contestacoes/a1/card").get_data(as_text=True)
    assert "Liguei para o cliente" in card and "data-ct-atualizar" not in card and "Só Ana Lima escreve" in card
    assert cliente.post("/t/contratos/contestacoes/b1/pegar", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_catalogo_registra_o_acompanhamento():
    from nexus.dados import catalogo
    l = catalogo.LIVRO_POR_NOME[TR.LIVRO]
    assert l.abas == (TR.ABA,) and catalogo.aba_segue_a_regra(TR.ABA)
    assert catalogo.POR_ID["tratamento_contestacao"].fontes == (f"{TR.LIVRO} · {TR.ABA}",)


def test_disponibilidade_e_desligamento_sao_do_cos(trat, app, cliente, monkeypatch):
    # Levi, 15/10/2026: "Disponibilidade e desligamento vão para o setor de COS" — o 5080 grava a linha com setor "cos";
    # quem é do setor COS vê só a aba dele
    cab = list(banco_linha := _linha("c9", "cos", "disponibilidade;desligamento", "2026-10-15T12:00:00Z", usina="Mandaguaçu"))
    trat._id(CT.LIVRO, CT.ABA)["linhas"].append({"headers": cab, "values": [banco_linha[c] for c in cab]})
    d = CT.contestacoes()
    assert d["contagem"]["cos"] == 1 and d["por_setor"]["cos"][0]["itens"] == ["Disponibilidade", "Desligamento"]
    from nexus.auth import setor_telas as ST
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(), "setor": {"id": 5, "nome": "COS"}, "erro": ""})
    _como(cliente, ANA)
    html = cliente.get("/t/contratos/contestacoes").get_data(as_text=True)
    assert "COS<i>1</i>" in html and "Mandaguaçu" in html and "Performance<i>" not in html and "Zeladoria<i>" not in html


def test_setor_sem_teams_aparece_so_no_nexus_e_nao_como_recusa(trat, app, cliente, monkeypatch):
    # 19/10/2026 (Levi: "vai direto para contestações do Nexus e a gente resolve lá, esquece teams"): o COS não tem fluxo
    # do Teams; o 5080 grava "sem canal" e a tela diz "só no Nexus", sem o vermelho de "o Teams recusou"
    cab = list(banco_linha := _linha("c8", "cos", "disponibilidade", "2026-10-19T12:00:00Z", usina="Altair",
                                     avisado="sem canal"))
    trat._id(CT.LIVRO, CT.ABA)["linhas"].append({"headers": cab, "values": [banco_linha[c] for c in cab]})
    d = CT.contestacoes()
    assert d["por_setor"]["cos"][0]["avisado"] is None and d["por_setor"]["zeladoria"][0]["avisado"] is False
    from nexus.auth import setor_telas as ST
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(), "setor": {"id": 5, "nome": "COS"}, "erro": ""})
    _como(cliente, ANA)
    html = cliente.get("/t/contratos/contestacoes").get_data(as_text=True)
    assert "só no Nexus" in html and "não recebeu" not in html and "recusou" not in html
