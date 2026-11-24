"""O controle dos e-mails automáticos do App pelo Nexus (24/11/2026): a regra no livro `nexus_email_controle`.

Levi, pela sessão do App: "Gostaria de poder controlar esses e-mails automáticos ou ter pelo menos um controle! E
gostaria que estivesse no Nexus". O que se prova aqui:
- a ida e a volta: a linha que o Nexus grava confere pela conta do App da v380 (`_email_regra_confere`,
  `_email_regra_abrir` e a escolha do `_email_regras`), reescrita abaixo como o App a tem, sem usar nada do Nexus;
- a linha que o App gera no teste dele (`test_v380_controle_emails.regra`) abre no Nexus;
- as recusas: teste sem lista, motivo sem texto, com e-mail ou com nome, e-mail de fora, desligar o crítico sem a
  confirmação, sem a chave, a leitura que falha;
- o histórico tirado das próprias linhas, e a tela (só administrador, publicar pela tela, o pedido de outro site).
Nada vai ao banco: o livro é um arquivo da pasta de teste."""
import base64
import hashlib
import hmac
import json
import os

import pytest

from nexus.campo import emails_app as EA
from nexus.campo import emails_controle as EC

CHAVE = "chave-hmac-de-teste"


# ── a conta do App (v380, function_app.py), sem nada do Nexus ──────────────────────────────────────────────────────
def _app_txt(v):
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v if v is not None else "").strip()


def _app_confere(ln, base):
    a = _app_txt(ln.get("assinatura")).lower()
    if not base or not a:
        return False
    chave = hmac.new(base.encode("utf-8"), b"nexus:email:controle", hashlib.sha256).digest()
    texto = "|".join(_app_txt(ln.get(k)) for k in
                     ("tipo", "ligado", "modo", "destinatarios", "substitui_padrao", "alterado_em"))
    return hmac.compare_digest(a.encode("utf-8"),
                               hmac.new(chave, texto.encode("utf-8"), hashlib.sha256).hexdigest().encode("utf-8"))


def _app_abrir(valor, tipo, base):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    v = _app_txt(valor)
    if not v:
        return []
    assert v.startswith("cf1:")
    k = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"nexus:email:controle/v1").derive(base.encode("utf-8"))
    b = v[4:]
    raw = base64.urlsafe_b64decode(b + "=" * (-len(b) % 4))
    txt = AESGCM(k).decrypt(raw[:12], raw[12:], ("nexus/email-controle/%s" % tipo).encode("utf-8"))
    lst = json.loads(txt.decode("utf-8"))
    assert isinstance(lst, list)
    out = []
    for x in lst:
        x = str(x or "").strip().lower()
        if "@" in x and x not in out:
            out.append(x)
    return out


def _app_regras(linhas, base):
    tipos = ("pt_aviso", "luvas_tst", "auditoria_diaria", "seguranca_semanal", "seguranca_relato", "encaminhamento",
             "avulso")
    melhor, inval = {}, 0
    for ln in linhas:
        tipo, ligado = _app_txt(ln.get("tipo")), _app_txt(ln.get("ligado")).lower()
        modo, sub, em = _app_txt(ln.get("modo")).lower(), _app_txt(ln.get("substitui_padrao")).lower(), \
            _app_txt(ln.get("alterado_em"))
        if (tipo not in tipos or ligado not in ("sim", "não", "nao") or modo not in ("normal", "teste")
                or sub not in ("sim", "não", "nao", "") or not em or not _app_confere(ln, base)):
            inval += 1
            continue
        try:
            lista = _app_abrir(ln.get("destinatarios"), tipo, base)
        except Exception:      # noqa: BLE001
            inval += 1
            continue
        if tipo not in melhor or em >= melhor[tipo]["alterado_em"]:
            melhor[tipo] = {"ligado": ligado == "sim", "modo": modo, "destinatarios": lista, "substitui": sub == "sim",
                            "alterado_em": em}
    return melhor, inval


def _regra_do_app(tipo, ligado="sim", modo="normal", lista=None, substitui="não", em="2026-11-24T14:00:00Z"):
    """A linha como o teste do App a monta (`test_v380_controle_emails.regra`)."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    dest = ""
    if lista is not None:
        k = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"nexus:email:controle/v1").derive(CHAVE.encode())
        nonce = os.urandom(12)
        c = AESGCM(k).encrypt(nonce, json.dumps(lista).encode(), ("nexus/email-controle/%s" % tipo).encode())
        dest = "cf1:" + base64.urlsafe_b64encode(nonce + c).decode().rstrip("=")
    ch = hmac.new(CHAVE.encode(), b"nexus:email:controle", hashlib.sha256).digest()
    ass = hmac.new(ch, "|".join([tipo, ligado, modo, dest, substitui, em]).encode(), hashlib.sha256).hexdigest()
    return {"tipo": tipo, "ligado": ligado, "modo": modo, "destinatarios": dest, "substitui_padrao": substitui,
            "alterado_por": "abc123", "alterado_em": em, "motivo": "teste", "assinatura": ass}


def _linha(**kw):
    base = dict(tipo="pt_aviso", ligado=True, modo="normal", destinatarios=[], substitui=False, quem_hmac="q1",
                motivo="ajuste de teste", chave_base=CHAVE, alterado_em="2026-11-24T15:00:00Z")
    base.update(kw)
    return EC.montar_linha(**base)


# ── a ida e a volta ───────────────────────────────────────────────────────────────────────────────────────────
def test_a_linha_do_nexus_confere_pela_conta_do_app():
    lns = [_linha(tipo="pt_aviso", modo="teste", destinatarios=["Cos@GridCo.com.br", "cos@gridco.com.br",
                                                                  "tst@gridco.com.br"]),
           _linha(tipo="luvas_tst", ligado=False, alterado_em="2026-11-24T15:00:01Z"),
           _linha(tipo="encaminhamento", destinatarios=["a@gridco.com.br"], substitui=True,
                  alterado_em="2026-11-24T15:00:02Z")]
    regras, inval = _app_regras(lns, CHAVE)
    assert inval == 0
    assert regras["pt_aviso"] == {"ligado": True, "modo": "teste", "alterado_em": "2026-11-24T15:00:00Z",
                                  "destinatarios": ["cos@gridco.com.br", "tst@gridco.com.br"], "substitui": False}
    assert regras["luvas_tst"]["ligado"] is False and regras["luvas_tst"]["destinatarios"] == []
    assert regras["encaminhamento"]["substitui"] is True
    # o que vai em claro: nada de e-mail em nenhuma coluna
    for ln in lns:
        assert "@" not in json.dumps({k: v for k, v in ln.items()})
        assert ln["ligado"] in ("sim", "não") and ln["substitui_padrao"] in ("sim", "não")
    # o Nexus e o App escolhem a mesma regra
    assert {t: (r["ligado"], r["modo"], r["destinatarios"], r["substitui"]) for t, r in EC.vigentes(lns, CHAVE).items()} \
        == {t: (r["ligado"], r["modo"], r["destinatarios"], r["substitui"]) for t, r in regras.items()}


def test_a_linha_do_teste_do_app_abre_no_nexus_e_a_estragada_nao():
    ln = _regra_do_app("pt_aviso", modo="teste", lista=["x@gridco.com.br"])
    ok, porque, lista = EC.conferir(ln, CHAVE)
    assert (ok, porque, lista) == (True, "", ["x@gridco.com.br"])
    for estraga in ({"assinatura": "0" * 64}, {"modo": "Teste!"}, {"tipo": "outro"}, {"ligado": "talvez"}):
        assert not EC.conferir(dict(ln, **estraga), CHAVE)[0]
    # a cifra de um tipo copiada para outro não abre (o dado associado amarra ao tipo), mesmo reassinada
    copia = dict(_regra_do_app("luvas_tst"), destinatarios=ln["destinatarios"])
    copia["assinatura"] = EC.assinatura(copia, CHAVE)
    assert EC.conferir(copia, CHAVE)[:2] == (False, "a lista cifrada não abre")
    assert not EC.conferir(ln, "outra-chave")[0]


def test_empate_vale_a_de_baixo_como_no_app():
    a = _linha(destinatarios=["a@gridco.com.br"], alterado_em="2026-11-24T15:00:00Z")
    b = _linha(ligado=False, alterado_em="2026-11-24T15:00:00Z")
    assert EC.vigentes([a, b], CHAVE)["pt_aviso"]["ligado"] is False
    assert _app_regras([a, b], CHAVE)[0]["pt_aviso"]["ligado"] is False


# ── publicar (o livro num arquivo) ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def cfg(tmp_path):
    EC.limpar()
    yield {"NEXUS_PESSOA_HMAC": CHAVE, "NEXUS_EMAIL_CONTROLE_ARQUIVO": str(tmp_path / "controle.json"), "TESTING": True}
    EC.limpar()


def _pub(cfg, **kw):
    base = dict(tipo="pt_aviso", ligado=True, modo="normal", destinatarios=[], substitui=False,
                motivo="TST de férias nesta semana", quem_hmac="q1", criticos=EA.CRITICOS)
    base.update(kw)
    return EC.publicar(cfg, **base)


def test_publicar_so_acrescenta_e_o_historico_sai_das_linhas(cfg):
    r1 = _pub(cfg, modo="teste", destinatarios=["tst@gridco.com.br"])
    r2 = _pub(cfg, modo="normal", destinatarios=["tst@gridco.com.br", "cos@gridco.com.br"], substitui=True,
              motivo="volta ao normal com a caixa do COS")
    assert r1["mudou"] and r2["mudou"]
    linhas = EC.ler(cfg, forcar=True)["linhas"]
    assert len(linhas) == 2 and linhas[0]["assinatura"] == r1["linha"]["assinatura"]
    assert linhas[1]["alterado_em"] > linhas[0]["alterado_em"]          # o mesmo segundo vira o seguinte
    regras, inval = _app_regras(linhas, CHAVE)
    assert inval == 0 and regras["pt_aviso"]["destinatarios"] == ["tst@gridco.com.br", "cos@gridco.com.br"]
    h = EC.historico(linhas, CHAVE, "pt_aviso")
    assert h[0]["mudou"] == ["modo teste → normal", "passou a substituir o padrão"]
    assert h[0]["entrou"] == ["cos@gridco.com.br"] and h[0]["saiu"] == []
    assert h[1]["mudou"][0].startswith("1ª regra do Nexus: teste")
    # a mesma regra de novo não grava
    assert _pub(cfg, modo="normal", destinatarios=["cos@gridco.com.br", "tst@gridco.com.br"], substitui=True)[
        "mudou"] is False
    assert len(EC.ler(cfg, forcar=True)["linhas"]) == 2


def test_as_recusas_nao_gravam_nada(cfg):
    casos = [
        dict(modo="teste", destinatarios=[]),                                      # no App, teste sem lista = normal
        dict(motivo="curto"),
        dict(motivo="mandar para fulano@gridco.com.br"),
        dict(motivo="Fulana Prado está de férias", nomes=["Fulana Rodrigues Prado"]),
        dict(destinatarios=["alguem@outra.com"]),
        dict(destinatarios=["sem-arroba"]),
        dict(ligado=False),                                                        # crítico sem a confirmação
        dict(tipo="outro"),
        dict(modo="silencioso"),
    ]
    for kw in casos:
        with pytest.raises(EC.Recusada):
            _pub(cfg, **kw)
    with pytest.raises(EC.Recusada):
        EC.publicar(dict(cfg, NEXUS_PESSOA_HMAC=""), tipo="pt_aviso", ligado=True, modo="normal", destinatarios=[],
                    substitui=False, motivo="motivo suficiente", quem_hmac="")
    assert EC.ler(cfg, forcar=True)["linhas"] == []
    # o e-mail de fora vale quando é de uma pessoa do cadastro; desligar o crítico vale com a confirmação
    assert _pub(cfg, destinatarios=["alguem@outra.com"], conhecidos=["alguem@outra.com"])["mudou"]
    assert _pub(cfg, ligado=False, confirmou_critico=True, motivo="parada da usina inteira")["mudou"]
    # desligar o que não é crítico não pede
    assert _pub(cfg, tipo="luvas_tst", ligado=False)["mudou"]


def test_leitura_que_falha_nao_grava(cfg, monkeypatch):
    def quebra(_cfg):
        raise ConnectionError("fora")
    monkeypatch.setattr(EC, "_ler_cru", quebra)
    with pytest.raises(EC.Recusada, match="Não consegui ler"):
        _pub(cfg)


# ── a tela ────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def tela(app, tmp_path, monkeypatch):
    from nexus.torres.base import emails_tela as ET
    app.config.update(NEXUS_PESSOA_HMAC=CHAVE, NEXUS_EMAIL_CONTROLE_ARQUIVO=str(tmp_path / "controle.json"))
    EC.limpar()
    monkeypatch.setattr(ET, "_livros", lambda: ({p: None for p in ET._PARES}, ""))
    monkeypatch.setattr(ET, "_pessoas", lambda: [{"nome": "Fulana Prado", "email": "fulana@gridco.com.br"}])
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logado=True, admin=True)
    yield c
    EC.limpar()


def _codigo(c):
    html = c.get("/t/base/emails-automaticos/pt_aviso").get_data(as_text=True)
    return html.split('name="codigo" value="', 1)[1].split('"', 1)[0]


def test_a_tela_publica_a_regra_e_mostra_o_historico(tela):
    cab = {"Sec-Fetch-Site": "same-origin"}
    r = tela.post("/t/base/emails-automaticos/pt_aviso/regra", headers=cab, data={
        "codigo": _codigo(tela), "acao": "salvar", "ligado": "sim", "modo": "teste",
        "dest": ["fulana@gridco.com.br", "cos@gridco.com.br"], "substitui": "nao", "motivo": "teste com a TST e o COS"})
    assert r.status_code == 303
    h = tela.get("/t/base/emails-automaticos/pt_aviso").get_data(as_text=True)
    assert "Regra publicada" in h and "teste: só para a lista (2)" in h
    assert "1ª regra do Nexus" in h and "teste com a TST e o COS" in h and "Fulana Prado" in h
    assert "o App ainda não confirmou" in h
    lista = tela.get("/t/base/emails-automaticos").get_data(as_text=True)
    assert "regra nova a confirmar" in lista
    linhas = EC.ler({"NEXUS_EMAIL_CONTROLE_ARQUIVO": tela.application.config["NEXUS_EMAIL_CONTROLE_ARQUIVO"]},
                    forcar=True)["linhas"]
    assert _app_regras(linhas, CHAVE)[0]["pt_aviso"]["destinatarios"] == ["fulana@gridco.com.br", "cos@gridco.com.br"]


def test_a_tela_recusa_o_teste_sem_lista_e_outro_site(tela):
    dados = {"codigo": _codigo(tela), "acao": "salvar", "ligado": "sim", "modo": "teste", "motivo": "motivo do teste"}
    r = tela.post("/t/base/emails-automaticos/pt_aviso/regra", headers={"Sec-Fetch-Site": "same-origin"}, data=dados)
    assert r.status_code == 409 and "precisa da lista" in r.get_data(as_text=True)
    r = tela.post("/t/base/emails-automaticos/pt_aviso/regra", headers={"Sec-Fetch-Site": "cross-site"},
                  data=dict(dados, dest=["cos@gridco.com.br"]))
    assert r.status_code == 403
    r = tela.post("/t/base/emails-automaticos/pt_aviso/regra", headers={"Sec-Fetch-Site": "same-origin"},
                  data=dict(dados, dest=["cos@gridco.com.br"], codigo="velho"))
    assert r.status_code == 403
    assert not os.path.exists(tela.application.config["NEXUS_EMAIL_CONTROLE_ARQUIVO"])


def test_desligar_critico_pede_a_confirmacao_e_diz_quem_deixa_de_saber(tela):
    h = tela.get("/t/base/emails-automaticos/seguranca_relato").get_data(as_text=True)
    assert "A TST deixa de saber" in h
    dados = {"codigo": _codigo(tela), "acao": "salvar", "ligado": "nao", "modo": "normal", "motivo": "parada geral"}
    r = tela.post("/t/base/emails-automaticos/seguranca_relato/regra", headers={"Sec-Fetch-Site": "same-origin"},
                  data=dados)
    assert r.status_code == 409
    r = tela.post("/t/base/emails-automaticos/seguranca_relato/regra", headers={"Sec-Fetch-Site": "same-origin"},
                  data=dict(dados, confirmo="1"))
    assert r.status_code == 303


def test_so_administrador_publica(app, tela):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logado=True, admin=False, usuario={"email": "alguem@gridco.com.br", "nome": "Alguém"})
    assert c.post("/t/base/emails-automaticos/pt_aviso/regra", data={"motivo": "qualquer"}).status_code == 403


def test_o_catalogo_conhece_os_tres_livros():
    from nexus.dados import catalogo as C
    ids = {f.id: f for f in C.FATOS}
    assert ids["envio_email_app"].livro == "email_todos_envios_app_campo · Todos os envios"
    assert ids["regra_email_app"].livro == "nexus_email_controle · fato_email_regra"
    livro = next(lv for lv in C.LIVROS if lv.nome == "nexus_email_controle")
    assert livro.so_cresce == ("fato_email_regra",)
    assert C.conhecida("email_tipos_app_campo", "Tipos")
