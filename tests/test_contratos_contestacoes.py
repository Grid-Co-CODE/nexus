"""Comando → Contestações (Levi, 13/10/2026: "em contratos e clientes no Nexus pode ter um lugar para essas
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
from nexus.cadastro import setor_ids as SID


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
    r = logado.get("/t/comando/contestacoes")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and ">Performance <span class=\"mudo\">2 abertas</span>" in html
    assert ">Zeladoria <span class=\"mudo\">1 aberta</span>" in html
    assert "Ana Souza" in html and "ana@cliente.com.br" in html and "Altair" in html
    z = logado.get("/t/comando/contestacoes?setor=zeladoria").get_data(as_text=True)
    assert "o Teams recusou o aviso" in z and "Altair" not in z


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


# ── O acompanhamento: desde 16/11/2026 o setor inteiro responde, sem dono (Levi: "Tire esse 'Pegar pra mim' qualquer
# um daquele setor pode editar e salvar por tanto que salve quem foi que fez isso!"), com Resolvida e Reabrir ─────────────
from nexus.cadastro.cifra import gerar_chave  # noqa: E402
from nexus.contratos import tratamento as TR  # noqa: E402

ANA = {"email": "ana.lima@gridco.com.br", "nome": "Ana Lima"}
BETO = {"email": "beto.souza@gridco.com.br", "nome": "Beto Souza"}
MESMO_SITE = {"Sec-Fetch-Site": "same-origin"}


@pytest.fixture
def trat(banco, app):
    app.config.update(NEXUS_CHAVE_CADASTRO=gerar_chave(), NEXUS_PESSOA_HMAC="hmac-teste", GRIDCO_SQL_TOKEN="tk")
    return banco


def _como(cli, usuario, admin=False):
    with cli.session_transaction() as s:
        s["logado"], s["admin"], s["usuario"] = True, admin, usuario
    return cli


def test_qualquer_um_do_setor_escreve_e_cada_atualizacao_guarda_quem(trat, app):
    with pytest.raises(TR.Recusada, match="Escreva"):
        TR.atualizar("a1", "performance", ANA, "   ")
    TR.atualizar("a1", "performance", ANA, "Verificando   com a equipe\n\nOS aberta no Fracttal")
    TR.atualizar("a1", "performance", BETO, "Liguei para o cliente")              # outro do setor, sem pegar nada
    t = TR.estado()["a1"]
    assert [(a["nome"], a["texto"]) for a in t["atualizacoes"]] == [
        ("Ana Lima", "Verificando com a equipe\n\nOS aberta no Fracttal"), ("Beto Souza", "Liguei para o cliente")]
    assert t["situacao"] == "em_andamento" and t["ultima"]["nome"] == "Beto Souza" and "às" in t["ultima"]["quando_txt"]
    with pytest.raises(TR.Recusada, match="login"):                                  # a senha de administrador não diz quem
        TR.atualizar("b1", "performance", None, "sem pessoa")
    assert not hasattr(TR, "pegar")
    # a API do banco tem leitura aberta: nem o nome, nem o e-mail, nem o texto em claro; o evento, sim (o aviso lê)
    lin = trat.linhas(TR.LIVRO, TR.ABA)
    assert len(lin) == 2 and list(lin[0]) == list(TR.CAB) and [l["evento"] for l in lin] == ["atualizacao"] * 2
    claro = json.dumps(lin, ensure_ascii=False, default=str).lower()
    assert "ana lima" not in claro and ANA["email"] not in claro and "beto souza" not in claro
    assert "verificando" not in claro and "liguei" not in claro


def test_resolvida_e_reaberta_e_a_situacao_de_cada_uma(trat, app):
    assert TR.estado().get("a1") is None and TR.VAZIO["situacao"] == "sem_resposta"
    TR.resolver("a1", "performance", ANA)                     # resolver sem escrever vale (o setor decide)
    t = TR.estado()["a1"]
    assert t["situacao"] == "resolvida" and t["resolvida"]["nome"] == "Ana Lima"
    with pytest.raises(TR.Recusada, match="já está resolvida"):
        TR.resolver("a1", "performance", BETO)
    TR.reabrir("a1", "performance", BETO)
    assert TR.estado()["a1"]["situacao"] == "sem_resposta"   # reaberta sem atualização volta a esperar resposta
    with pytest.raises(TR.Recusada, match="não está resolvida"):
        TR.reabrir("a1", "performance", BETO)
    TR.atualizar("a1", "performance", BETO, "Respondido por e-mail")
    TR.resolver("a1", "performance", BETO)
    TR.reabrir("a1", "performance", ANA)
    assert TR.estado()["a1"]["situacao"] == "em_andamento"
    assert [e["evento"] for e in TR.estado()["a1"]["eventos"]] == ["resolvida", "reaberta", "atualizacao", "resolvida",
                                                                  "reaberta"]
    # a situação só pelo evento (em claro), sem abrir nada: é o que o aviso do topo lê
    assert TR.situacoes(trat.linhas(TR.LIVRO, TR.ABA)) == {"a1": "em_andamento"}


def test_a_ordem_e_a_da_gravacao_no_mesmo_segundo():
    lin = [{"id": "z9", "registrado_em": "2026-11-16T12:00:00Z", "contestacao_linha_id": "a1", "evento": "resolvida"},
           {"id": "a0", "registrado_em": "2026-11-16T12:00:00Z", "contestacao_linha_id": "a1", "evento": "reaberta"}]
    assert TR.situacoes(lin) == {"a1": "sem_resposta"}         # pelo id, o "a0" viria antes e ficaria resolvida
    assert TR.situacoes(list(reversed(lin))) == {"a1": "resolvida"}


def test_o_setor_so_ve_a_contestacao_dele_e_o_administrador_ve_todas(trat, app, cliente, monkeypatch):
    from nexus.auth import setor_telas as ST
    setor = {"v": {"id": SID.ZELADORIA, "nome": "Zeladoria"}}
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(), "setor": setor["v"], "erro": ""})
    _como(cliente, ANA)
    html = cliente.get("/t/comando/contestacoes").get_data(as_text=True)
    assert "Contestação · Zeladoria" in html and "Performance <span" not in html and "Altair" not in html
    # a de outro setor nem abre (o servidor barra, não só a tela)
    assert cliente.get("/t/comando/contestacoes?setor=performance").get_data(as_text=True).count("Altair") == 0
    assert cliente.get("/t/comando/contestacoes?c=b1").get_data(as_text=True).count("Altair") == 0
    assert cliente.get("/t/comando/contestacoes/a1/card").status_code == 404
    for acao in ("atualizacao", "resolver", "reabrir", "pegar"):
        assert cliente.post(f"/t/comando/contestacoes/a1/{acao}", data={"texto": "x"}, headers=MESMO_SITE).status_code == 404
    assert cliente.get("/t/comando/contestacoes/a2/card").status_code == 200
    setor["v"] = {"id": SID.ENGENHARIA, "nome": "Engenharia"}                              # setor sem contestação: nenhuma
    html = cliente.get("/t/comando/contestacoes").get_data(as_text=True)
    assert "Nenhuma contestação para o seu setor" in html and "o seu setor é Engenharia" in html
    app.config["NEXUS_ADMINS"] = BETO["email"]                              # administrador (a lista de agora): todas
    _como(cliente, BETO, admin=True)
    html = cliente.get("/t/comando/contestacoes").get_data(as_text=True)
    assert ">Performance <span class=\"mudo\">2 abertas</span>" in html and ">Zeladoria <span" in html


def test_a_tela_escreve_resolve_e_reabre_sem_pegar(trat, app, cliente):
    _como(cliente, ANA)
    html = cliente.get("/t/comando/contestacoes").get_data(as_text=True)
    assert "Pegar para mim" not in html and "Assumir" not in html
    assert html.count('class="gc-status gc-status--alerta">Sem resposta<') == 3        # as duas da lista e o card
    assert 'data-ct-card="/t/comando/contestacoes/a1/card"' in html and 'data-ct-card="/t/comando/contestacoes/b1/card"' in html
    assert 'id="ct-detalhe"' in html and "Marcar como resolvida" in html and "Fica registrada como Ana Lima" in html
    assert "comando-contestacoes.js" in html
    # sem JavaScript: grava e volta à contestação com o aviso
    r = cliente.post("/t/comando/contestacoes/a1/atualizacao", data={"texto": "Liguei para o cliente"}, headers=MESMO_SITE)
    assert r.status_code == 303 and r.headers["Location"].endswith("/t/comando/contestacoes?setor=performance&c=a1#ct-detalhe")
    html = cliente.get("/t/comando/contestacoes?setor=performance&c=a1").get_data(as_text=True)
    assert "Atualização salva" in html and "Liguei para o cliente" in html and "Em andamento" in html
    # com o JavaScript (X-Nexus-Parte): JSON, e a recusa diz por quê, sem gravar
    r = cliente.post("/t/comando/contestacoes/a1/atualizacao", data={"texto": "  "},
                     headers=dict(MESMO_SITE, **{"X-Nexus-Parte": "1"}))
    assert r.status_code == 409 and "Escreva" in r.get_json()["erro"]
    # outra pessoa do setor escreve e resolve (sem dono)
    _como(cliente, BETO)
    r = cliente.post("/t/comando/contestacoes/a1/resolver", data={"ver": "abertas"}, headers=dict(MESMO_SITE, **{"X-Nexus-Parte": "1"}))
    assert r.status_code == 200 and r.get_json()["ok"]
    card = cliente.get("/t/comando/contestacoes/a1/card").get_data(as_text=True)
    assert "Liguei para o cliente" in card and "Ana Lima" in card and "Marcou como resolvida" in card and "Reabrir" in card
    abertas = cliente.get("/t/comando/contestacoes?setor=performance").get_data(as_text=True)
    assert 'data-ct-id="a1"' not in abertas and "Resolvidas<i>1</i>" in abertas
    resolv = cliente.get("/t/comando/contestacoes?setor=performance&ver=resolvidas").get_data(as_text=True)
    assert 'data-ct-id="a1"' in resolv and "Resolvida por <b>Beto Souza</b>" in resolv
    # o "Pegar para mim" de uma aba antiga não grava: leva à contestação
    n = len(trat.linhas(TR.LIVRO, TR.ABA))
    r = cliente.post("/t/comando/contestacoes/b1/pegar", headers=MESMO_SITE)
    assert r.status_code == 303 and "c=b1" in r.headers["Location"] and len(trat.linhas(TR.LIVRO, TR.ABA)) == n
    # de outro site, nada grava
    for acao in ("atualizacao", "resolver", "reabrir", "pegar"):
        assert cliente.post(f"/t/comando/contestacoes/b1/{acao}", data={"texto": "x"},
                            headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert len(trat.linhas(TR.LIVRO, TR.ABA)) == n


def test_o_responsavel_de_antes_fica_na_historia(trat, app, cliente):
    # o "Pegar para mim" gravado até 15/11/2026: aparece na história, e a contestação segue sem resposta (e no aviso)
    with app.test_request_context():
        ev = TR._gravar("b1", "performance", "responsavel", ANA)
    trat._id(TR.LIVRO, TR.ABA)["linhas"] = [{"headers": list(TR.CAB), "values": [ev.get(c) for c in TR.CAB]}]
    assert TR.estado()["b1"]["situacao"] == "sem_resposta"
    _como(cliente, BETO)
    card = cliente.get("/t/comando/contestacoes/b1/card").get_data(as_text=True)
    assert "Ficou com a demanda" in card and "Ana Lima" in card and "Ninguém do setor respondeu ainda" not in card


# ── o aviso do topo (16/11/2026, Levi: "as contestações também devem notificar nas notificações lá de cima, a que não é
# do OS Creator!"): a sem resposta do setor, até a 1ª resposta de qualquer um dele ou até resolver ──────────────────────
def _bandeja(html):
    i = html.index('class="sino-topo sino-dem"')
    return html[i:html.index("</details>", i)]


def test_a_bandeja_traz_a_sem_resposta_do_setor_ate_a_primeira_resposta(trat, app, cliente, monkeypatch):
    from nexus.auth import setor_telas as ST
    from nexus.comando import demandas as D
    from nexus.torres.comando import demandas_tela as DT
    monkeypatch.setattr(D, "faltam_chaves", lambda: ["sem as chaves das demandas neste teste"])
    setor = {"v": {"id": SID.PERFORMANCE, "nome": "Performance"}, "telas": {"comando/contestacoes"}}
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": setor["telas"], "setor": setor["v"], "erro": ""})
    monkeypatch.setattr(DT, "_meu_setor", lambda: setor["v"])
    _como(cliente, ANA)
    b = _bandeja(cliente.get("/t/comando/contestacoes").get_data(as_text=True))
    assert "2 contestações sem resposta" in b and "Altair" in b and "Guaratinguetá V" in b
    assert "/t/comando/contestacoes?setor=performance&amp;c=b1#ct-detalhe" in b and "Abrir as contestações" in b
    assert 'aria-label="Demandas e contestações: 2"' in b and "Abrir as demandas" not in b
    # a 1ª resposta de qualquer um do setor tira para todos; resolver também
    cliente.post("/t/comando/contestacoes/a1/atualizacao", data={"texto": "Vendo"}, headers=MESMO_SITE)
    _como(cliente, BETO)
    b = _bandeja(cliente.get("/t/comando/contestacoes").get_data(as_text=True))
    assert "1 contestação sem resposta" in b and "Altair" in b and "Guaratinguetá V" not in b
    cliente.post("/t/comando/contestacoes/b1/resolver", headers=MESMO_SITE)
    b = _bandeja(cliente.get("/t/comando/contestacoes").get_data(as_text=True))
    assert "sem resposta" not in b and "Nenhuma contestação espera o seu setor agora." in b
    # quem é de outro setor de contestação recebe a dele; quem não tem a tela, nenhuma (e sem demandas, sem bandeja)
    setor["v"] = {"id": SID.ZELADORIA, "nome": "Zeladoria"}
    b = _bandeja(cliente.get("/t/comando/contestacoes").get_data(as_text=True))
    assert "1 contestação sem resposta" in b and "Guaratinguetá V" in b
    setor["telas"] = set()
    assert 'class="sino-topo sino-dem"' not in cliente.get("/").get_data(as_text=True)


def test_o_administrador_recebe_so_a_do_setor_dele(trat, app, cliente, monkeypatch):
    from nexus.auth import setor_telas as ST
    from nexus.comando import demandas as D
    from nexus.torres.comando import demandas_tela as DT
    monkeypatch.setattr(D, "faltam_chaves", lambda: ["sem as chaves das demandas neste teste"])
    setor = {"v": {"id": SID.ZELADORIA, "nome": "Zeladoria"}}
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": True, "telas": set(), "setor": setor["v"], "erro": ""})
    monkeypatch.setattr(DT, "_meu_setor", lambda: setor["v"])
    app.config["NEXUS_ADMINS"] = BETO["email"]               # o Nexus recalcula o administrador a cada pedido
    _como(cliente, BETO, admin=True)
    b = _bandeja(cliente.get("/").get_data(as_text=True))
    assert "1 contestação sem resposta" in b and "Guaratinguetá V" in b and "Altair" not in b
    setor["v"] = None                                        # o administrador sem setor de contestação: as três
    b = _bandeja(cliente.get("/").get_data(as_text=True))
    assert "3 contestações sem resposta" in b and "Performance" in b and "Zeladoria" in b
    _como(cliente, None, admin=True)                          # a senha de administrador (sem pessoa): sem bandeja
    assert 'class="sino-topo sino-dem"' not in cliente.get("/").get_data(as_text=True)


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
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(), "setor": {"id": SID.COS, "nome": "COS"}, "erro": ""})
    _como(cliente, ANA)
    html = cliente.get("/t/comando/contestacoes").get_data(as_text=True)
    assert "Contestação · COS" in html and "Mandaguaçu" in html and "Performance <span" not in html
    assert "Zeladoria <span" not in html and "Guaratinguetá" not in html


def test_setor_sem_teams_aparece_so_no_nexus_e_nao_como_recusa(trat, app, cliente, monkeypatch):
    # 19/10/2026 (Levi: "vai direto para contestações do Nexus e a gente resolve lá, esquece teams"): o COS não tem fluxo
    # do Teams; o 5080 grava "sem canal" e a tela diz "só no Nexus", sem o vermelho de "o Teams recusou"
    cab = list(banco_linha := _linha("c8", "cos", "disponibilidade", "2026-10-19T12:00:00Z", usina="Altair",
                                     avisado="sem canal"))
    trat._id(CT.LIVRO, CT.ABA)["linhas"].append({"headers": cab, "values": [banco_linha[c] for c in cab]})
    d = CT.contestacoes()
    assert d["por_setor"]["cos"][0]["avisado"] is None and d["por_setor"]["zeladoria"][0]["avisado"] is False
    from nexus.auth import setor_telas as ST
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(), "setor": {"id": SID.COS, "nome": "COS"}, "erro": ""})
    _como(cliente, ANA)
    html = cliente.get("/t/comando/contestacoes").get_data(as_text=True)
    assert "só no Nexus" in html and "não recebeu" not in html and "recusou" not in html
