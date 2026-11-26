"""Os e-mails que o próprio Nexus manda (25/11/2026): `nexus/emails/`.

Levi: "a informação do app de campo tem que chegar para o Nexus e o Nexus passa essa informação para os e-mails"; "Tem
e-mails que vão ser mandados só com dados do Nexus"; "faça todas as fases". O que se prova aqui, sem rede e sem banco
(a fila, o registro, as regras e os modelos moram em arquivos da pasta de teste; o envio é dublado ou vira arquivo):
- a regra da tela sobre a mensagem, a régua do App (desligado, teste com lista, substituir, somar);
- a fila: a mesma chave não entra duas vezes, o envio que falha tenta de novo, depois de 24 h desiste e registra;
- o registro: um por destinatário, com o código HMAC, nunca o e-mail;
- o envio: sem as chaves diz o que falta; na cópia de prova vira arquivo; o erro do Entra ID sem segredo;
- os papéis (o Responsável UFV da usina, a TST pelo setor) e o e-mail que ninguém tem fica de fora;
- os modelos: cifrados no livro, o novo nasce desligado, a agenda, a montagem um por responsável;
- o evento do App: a assinatura, o 202 que tira o envio do App e o 503 que o devolve;
- a tela: a seção do Nexus, o teste, o editor, a prévia e a porta pública do App."""
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone

import pytest

from nexus.campo import emails_controle as EC
from nexus.emails import envio, evento_app, fila, modelos, papeis, registro
from nexus.emails.tipos import mensagem

CHAVE = "chave-hmac-de-teste"
AGORA = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def cfg(tmp_path):
    EC.limpar()
    modelos._CACHE.clear()
    yield {"NEXUS_PESSOA_HMAC": CHAVE, "NEXUS_EMAIL_CONTROLE_ARQUIVO": str(tmp_path / "controle.json"),
           "NEXUS_EMAIL_ENVIOS_ARQUIVO": str(tmp_path / "envios.json"), "TESTING": True}
    EC.limpar()
    modelos._CACHE.clear()


def _msg(chave="k1", para=("a@gridco.com.br",), cc=()):
    return mensagem(tipo="nx_teste", referencia="ref", chave=chave,
                    para=[{"email": e, "papel": "p"} for e in para], cc=[{"email": e, "papel": "c"} for e in cc],
                    assunto="Assunto", html="<p>oi</p>")


# ── a regra sobre a mensagem ──────────────────────────────────────────────────────────────────────────────────────
def test_a_regra_da_tela_vale_como_no_app():
    m = _msg(para=("a@gridco.com.br",), cc=("c@gridco.com.br",))
    assert fila.aplicar(None, m)["para"][0]["email"] == "a@gridco.com.br"
    regra = {"ligado": False, "modo": "normal", "destinatarios": [], "substitui": False}
    assert fila.aplicar(regra, m)["situacao"] == "desligado"
    teste = dict(regra, ligado=True, modo="teste", destinatarios=["t@gridco.com.br"])
    r = fila.aplicar(teste, m)
    assert [x["email"] for x in r["para"]] == ["t@gridco.com.br"] and r["cc"] == [] and r["assunto"] == "[Teste] Assunto"
    sub = dict(regra, ligado=True, destinatarios=["s@gridco.com.br"], substitui=True)
    assert [x["email"] for x in fila.aplicar(sub, m)["para"]] == ["s@gridco.com.br"]
    soma = dict(sub, substitui=False, destinatarios=["s@gridco.com.br", "c@gridco.com.br"])
    r = fila.aplicar(soma, m)
    assert [x["email"] for x in r["para"]] == ["a@gridco.com.br", "s@gridco.com.br"]      # o que já é cópia não repete
    assert [x["email"] for x in r["cc"]] == ["c@gridco.com.br"]


# ── a fila e o registro ─────────────────────────────────────────────────────────────────────────────────────────────
def test_a_fila_manda_registra_sem_email_e_nao_repete_a_chave(cfg):
    assert fila.enfileirar(cfg, _msg(), AGORA) is True
    assert fila.enfileirar(cfg, _msg(), AGORA) is False                 # a mesma chave (o reinício da agenda)
    mandados = []

    def enviar(c, **kw):
        mandados.append(kw)
        return True, "graph", ""
    r = fila.processar(cfg, AGORA, enviar)
    assert r["enviados"] == 1 and fila.pendentes(cfg) == [] and mandados[0]["para"] == ["a@gridco.com.br"]
    ls = registro.linhas(cfg)
    assert len(ls) == 1 and ls[0]["Situação"] == "enviado" and ls[0]["Tipo"] == "nx_teste"
    assert "@" not in json.dumps(ls)                                      # o livro é de leitura aberta
    assert ls[0]["Destinatário (HMAC)"] == registro.codigo(cfg, "a@gridco.com.br")
    assert fila.enfileirar(cfg, _msg(), AGORA + timedelta(days=1)) is False


def test_o_envio_que_falha_tenta_de_novo_e_depois_de_24h_desiste(cfg):
    fila.enfileirar(cfg, _msg(), AGORA)
    falha = lambda c, **kw: (False, "graph", "HTTP 503: fulano@gridco.com.br fora")   # noqa: E731
    r = fila.processar(cfg, AGORA, falha)
    assert r["falhas"] == 1 and r["pendentes"] == 1
    item = fila.pendentes(cfg)[0]
    assert item["tentativas"] == 1 and item["proxima_em"] == "2026-11-25T12:01:00Z" and "@" not in item["erro"]
    assert fila.processar(cfg, AGORA + timedelta(seconds=30), falha)["pendentes"] == 1   # ainda no recuo
    r = fila.processar(cfg, AGORA + timedelta(hours=25), falha)
    assert r["falhas"] == 1 and fila.pendentes(cfg) == []
    ls = registro.linhas(cfg)
    assert ls[-1]["Situação"] == "falhou" and "@" not in ls[-1]["Erro"]


def test_o_desligado_nao_manda_e_registra(cfg):
    EC.publicar(cfg, tipo="nx_teste", ligado=False, modo="normal", destinatarios=[], substitui=False,
                motivo="Teste desligado por enquanto", quem_hmac="", alvo=EC.NEXUS)
    fila.enfileirar(cfg, _msg(), AGORA)
    nada = lambda c, **kw: pytest.fail("não podia mandar")     # noqa: E731
    assert fila.processar(cfg, AGORA, nada)["desligados"] == 1
    assert registro.linhas(cfg)[0]["Situação"] == "desligado"


def test_a_regra_do_nexus_mora_fora_do_livro_do_app(cfg):
    """O App descarta (e conta como inválida) linha de tipo que ele não conhece: a regra dos e-mails do Nexus vai a outro
    livro, e a do App não aceita tipo "nx_"."""
    EC.publicar(cfg, tipo="nx_teste", ligado=True, modo="normal", destinatarios=["x@gridco.com.br"], substitui=False,
                motivo="Mais gente no teste", quem_hmac="", alvo=EC.NEXUS)
    assert EC.ler(cfg, alvo=EC.APP)["linhas"] == []
    assert EC.vigentes(EC.ler(cfg, alvo=EC.NEXUS)["linhas"], CHAVE, EC.NEXUS)["nx_teste"]["destinatarios"]
    with pytest.raises(EC.Recusada):
        EC.publicar(cfg, tipo="nx_teste", ligado=True, modo="normal", destinatarios=[], substitui=False,
                    motivo="Não pode ir ao livro do App", quem_hmac="", alvo=EC.APP)
    assert EC.alvo_do_tipo("nx_app_luvas") is EC.NEXUS and EC.alvo_do_tipo("luvas_tst") is EC.APP


# ── o envio ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_envio_diz_o_que_falta_e_na_prova_vira_arquivo(tmp_path):
    c = {"TESTING": True}
    assert envio.faltam(c) == ["o diretório", "o ID do aplicativo", "o segredo", "a caixa que envia"]
    ok, _via, erro = envio.enviar(c, para=["a@gridco.com.br"], assunto="A", html="<p>x</p>")
    assert not ok and "sem o diretório" in erro and "@" not in erro
    c["NEXUS_EMAIL_SAIDA_PASTA"] = str(tmp_path / "saida")
    assert envio.enviar(c, para=["a@gridco.com.br"], assunto="A", html="<p>x</p>") == (True, "arquivo", "")
    assert len(list((tmp_path / "saida").glob("*.html"))) == 1
    assert not envio.envia_nesta_maquina({"TESTING": True})
    assert envio.envia_nesta_maquina({"TESTING": True, "NEXUS_EMAIL_ENVIAR": "1"})


def test_o_token_recusado_vira_erro_sem_segredo(monkeypatch):
    import requests

    class R:
        status_code = 401

        def json(self):
            return {"error": "invalid_client", "error_description": "AADSTS7000215: Invalid client secret provided.\r\nTrace ID: x"}
    monkeypatch.setattr(requests, "post", lambda *a, **k: R())
    with pytest.raises(envio.EnvioErro) as ex:
        envio.pedir_token("t", "c", "segredo-que-nao-pode-aparecer")
    assert "invalid_client" in str(ex.value) and "segredo" not in str(ex.value) and "Trace" not in str(ex.value)


# ── os papéis ───────────────────────────────────────────────────────────────────────────────────────────────────────
class _Base:
    por_id = {10: {"responsavel_om_id": 7}, 11: {"responsavel_om_id": 7}, 12: {"responsavel_om_id": 8}}

    def nome_da_pessoa(self, pid, reserva):
        return {7: "Fulana Prado", 8: "Ciclano Rocha"}.get(pid, reserva)


def _ctx(monkeypatch):
    from nexus.campo import decisao_pt
    monkeypatch.setattr(decisao_pt, "aprovadores", lambda p, b: {"ids": {
        "responsável UFV": b.por_id[p["usina_id"]]["responsavel_om_id"]}, "cos": set(), "texto": ""})
    return papeis.Contexto(b=_Base(), email_da_pessoa={7: "fulana@gridco.com.br"},
                           email_do_codigo={"c1": "tst@gridco.com.br", "c2": "pcm@gridco.com.br"},
                           setor_do_codigo={"c1": 4, "c2": 9})


def test_os_papeis_acham_a_pessoa_da_usina_e_do_setor(monkeypatch):
    c = _ctx(monkeypatch)
    r = papeis.resolver(c, ["responsavel_ufv", "tst", "x@gridco.com.br", "tst"], 10)
    assert [x["email"] for x in r] == ["fulana@gridco.com.br", "tst@gridco.com.br", "x@gridco.com.br"]
    assert papeis.resolver(c, ["responsavel_ufv"], 12) == []          # sem e-mail: fica de fora, nunca se inventa


# ── os modelos ──────────────────────────────────────────────────────────────────────────────────────────────────────
MODELO = {"nome": "Pendências das usinas", "assunto": "Pendências das suas usinas", "texto": "Bom dia.",
          "fontes": ["pendencias_usinas"], "envio": "por_responsavel", "para": ["tst"], "cc": [],
          "agenda": {"freq": "diaria", "hora": "07:00", "uteis": True}, "pular_vazio": True}


def test_o_modelo_vai_cifrado_e_nasce_desligado(cfg):
    r = modelos.salvar(cfg, MODELO, quem_hmac="q1")
    assert r == {"id": "nx_pendencias_das_usinas", "novo": True}
    bruto = json.loads(open(cfg["NEXUS_EMAIL_CONTROLE_ARQUIVO"], encoding="utf-8").read())["modelos:fato_email_modelo"]
    assert "Bom dia" not in json.dumps(bruto) and bruto[0]["dados"].startswith("cf1:")
    assert modelos.vigentes(cfg)["nx_pendencias_das_usinas"]["texto"] == "Bom dia."
    regra = EC.vigentes(EC.ler(cfg, alvo=EC.NEXUS)["linhas"], CHAVE, EC.NEXUS)["nx_pendencias_das_usinas"]
    assert regra["ligado"] is False
    assert modelos.salvar(cfg, MODELO, quem_hmac="q1")["id"] == "nx_pendencias_das_usinas_2"   # o mesmo nome: outro id
    modelos.excluir(cfg, "nx_pendencias_das_usinas_2", quem_hmac="q1")
    assert list(modelos.vigentes(cfg)) == ["nx_pendencias_das_usinas"]


def test_o_modelo_recusa_nome_com_email_e_o_um_so_sem_ninguem(cfg):
    with pytest.raises(modelos.Recusado):
        modelos.salvar(cfg, dict(MODELO, nome="Para fulana@gridco.com.br"), quem_hmac="")
    with pytest.raises(modelos.Recusado):
        modelos.salvar(cfg, dict(MODELO, envio="um_so", para=["responsavel_ufv"]), quem_hmac="")
    with pytest.raises(modelos.Recusado):
        modelos.salvar(cfg, dict(MODELO, para=["fora@exemplo.com"]), quem_hmac="")


def test_a_agenda_so_no_dia_e_depois_da_hora():
    m = {"agenda": {"freq": "diaria", "hora": "07:00", "uteis": True}}
    quarta = datetime(2026, 11, 25, 10, 30, tzinfo=timezone.utc)          # 07:30 de Brasília
    assert modelos.devido(m, quarta) == "2026-11-25"
    assert modelos.devido(m, quarta - timedelta(hours=1)) is None          # 06:30
    assert modelos.devido(m, datetime(2026, 11, 28, 12, 0, tzinfo=timezone.utc)) is None   # sábado
    assert modelos.devido({"agenda": {"freq": "semanal", "hora": "07:00", "dia": 2}}, quarta) == "2026-11-25"
    assert modelos.devido({"agenda": {"freq": "mensal", "hora": "07:00", "dia": 1}}, quarta) is None
    assert modelos.devido({"agenda": {"freq": "manual"}}, quarta) is None


def test_um_por_responsavel_leva_so_as_usinas_dele(cfg, monkeypatch):
    from nexus.emails import fontes as F
    c = _ctx(monkeypatch)
    monkeypatch.setitem(F.FONTES, "pendencias_usinas", F.Fonte(
        "pendencias_usinas", "x", "x", True, lambda us, link: (f"<p>{len(us)} usinas</p>", len(us) > 1)))
    us = [{"usina_id": 10}, {"usina_id": 11}, {"usina_id": 12}]
    m = dict(MODELO, id="nx_pend")
    r = modelos.montar(cfg, m, AGORA, ctx=c, usinas=us)
    assert len(r["mensagens"]) == 1                                         # o 8 não tem e-mail: fica de fora e avisa
    msg = r["mensagens"][0]
    assert [x["email"] for x in msg["para"]] == ["fulana@gridco.com.br", "tst@gridco.com.br"]
    assert "2 usinas" in msg["html"] and msg["chave"] == "nx_pend|2026-11-25|7"
    assert any("Ciclano Rocha" in a for a in r["avisos"])
    assert "@" not in msg["referencia"] and "Fulana" not in msg["referencia"]


# ── o evento do App ─────────────────────────────────────────────────────────────────────────────────────────────────
def _assinado(corpo: dict, ts=None):
    ts = int(ts or time.time())
    raw = json.dumps(corpo).encode()
    k = hmac.new(CHAVE.encode(), b"nexus:email:evento", hashlib.sha256).digest()
    return raw, {"X-Nexus-Ts": str(ts), "X-Nexus-Assinatura": hmac.new(k, f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()}


EVENTO = {"tipo": "luvas_tst", "id": "luvas-2026-11-25-abc", "usina_id": 10, "referencia": "ronda UFV-010",
          "assunto": "Luvas isolantes com Não", "html": "<p>luvas</p>", "sugeridos": ["tst@gridco.com.br"]}


def test_o_evento_do_app_confere_a_assinatura(cfg):
    raw, h = _assinado(EVENTO)
    st, d = evento_app.conferir(cfg, h["X-Nexus-Ts"], h["X-Nexus-Assinatura"], raw)
    assert st == 200 and d["tipo_app"] == "luvas_tst" and d["usina_id"] == 10
    assert evento_app.conferir(cfg, h["X-Nexus-Ts"], "0" * 64, raw)[0] == 401
    raw2, h2 = _assinado(EVENTO, ts=time.time() - 3600)
    assert evento_app.conferir(cfg, h2["X-Nexus-Ts"], h2["X-Nexus-Assinatura"], raw2)[0] == 401
    raw3, h3 = _assinado(dict(EVENTO, tipo="outro"))
    assert evento_app.conferir(cfg, h3["X-Nexus-Ts"], h3["X-Nexus-Assinatura"], raw3)[0] == 400


def test_o_evento_vai_a_tst_e_ao_responsavel_e_o_app_nao_manda(cfg, monkeypatch):
    c = _ctx(monkeypatch)
    monkeypatch.setattr(papeis, "contexto", lambda cfg: c)
    cfg = dict(cfg, NEXUS_EMAIL_ENVIAR="1", NEXUS_EMAIL_SAIDA_PASTA="x")
    raw, h = _assinado(EVENTO)
    d = evento_app.conferir(cfg, h["X-Nexus-Ts"], h["X-Nexus-Assinatura"], raw)[1]
    st, corpo = evento_app.receber(cfg, d, AGORA)
    assert st == 202 and corpo["tipo"] == "nx_app_luvas" and corpo["para"] == 2
    item = fila.pendentes(cfg)[0]
    assert {x["email"] for x in item["para"]} == {"tst@gridco.com.br", "fulana@gridco.com.br"}
    assert evento_app.receber(cfg, d, AGORA)[1]["repetido"] is True     # o App mandou de novo: não duplica
    st, _ = evento_app.receber(dict(cfg, NEXUS_EMAIL_ENVIAR="0"), d, AGORA)
    assert st == 503                                                     # esta máquina não envia: o App manda


# ── a tela ──────────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def tela(app, tmp_path, monkeypatch):
    from nexus.torres.base import emails_tela as ET
    app.config.update(NEXUS_PESSOA_HMAC=CHAVE, NEXUS_EMAIL_CONTROLE_ARQUIVO=str(tmp_path / "controle.json"),
                      NEXUS_EMAIL_ENVIOS_ARQUIVO=str(tmp_path / "envios.json"),
                      NEXUS_EMAIL_SAIDA_PASTA=str(tmp_path / "saida"))
    EC.limpar()
    modelos._CACHE.clear()
    monkeypatch.setattr(ET, "_livros", lambda: ({p: None for p in ET._PARES}, ""))
    monkeypatch.setattr(ET, "_pessoas", lambda: [{"nome": "Fulana Prado", "email": "fulana@gridco.com.br"}])
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logado=True, admin=True, emails_auto_form="cod")
    yield c
    EC.limpar()
    modelos._CACHE.clear()


def test_a_tela_mostra_os_emails_do_nexus_e_manda_o_teste(tela, app):
    html = tela.get("/t/base/emails-automaticos").get_data(as_text=True)
    assert "Do Nexus" in html and "E-mail de teste do Nexus" in html and "Luvas isolantes com Não na ronda (pelo Nexus)" in html
    assert "/t/base/emails-automaticos/novo" in html
    r = tela.post("/t/base/emails-automaticos/nx_teste/mandar", data={"codigo": "cod", "para": "fulana@gridco.com.br"})
    assert r.status_code == 303
    assert len(fila.pendentes(app.config)) == 1
    assert tela.post("/t/base/emails-automaticos/nx_teste/mandar",
                     data={"codigo": "cod", "para": "fora@exemplo.com"}).status_code == 409


def test_a_tela_cria_o_email_e_mostra_a_previa(tela, app, monkeypatch):
    from nexus.emails import fontes as F
    monkeypatch.setattr(F, "usinas_da_visao", lambda cfg: [])
    monkeypatch.setattr(papeis, "contexto", lambda cfg: papeis.Contexto(b=_Base(), email_do_codigo={"c1": "tst@gridco.com.br"},
                                                                       setor_do_codigo={"c1": 4}))
    r = tela.post("/t/base/emails-automaticos/modelo/salvar", data={
        "codigo": "cod", "nome": "Resumo da TST", "assunto": "Resumo do dia", "texto": "Bom dia.", "envio": "um_so",
        "para_papel": "tst", "freq": "manual"})
    assert r.status_code == 303 and r.headers["Location"].endswith("/t/base/emails-automaticos/nx_resumo_da_tst")
    h = tela.get("/t/base/emails-automaticos/nx_resumo_da_tst").get_data(as_text=True)
    assert "Ver a prévia" in h and "Desligado" in h
    p = tela.get("/t/base/emails-automaticos/nx_resumo_da_tst/previa").get_data(as_text=True)
    assert "Resumo do dia" in p and "srcdoc=" in p and "tst@gridco.com.br" in p


def test_a_porta_do_app_e_publica_mas_so_com_a_assinatura(app, tmp_path, monkeypatch):
    app.config.update(NEXUS_PESSOA_HMAC=CHAVE, NEXUS_EMAIL_ENVIOS_ARQUIVO=str(tmp_path / "envios.json"))
    c = app.test_client()
    raw, h = _assinado(EVENTO)
    r = c.post("/t/base/emails-automaticos/api/evento", data=raw, headers={**h, "Content-Type": "application/json"})
    assert r.status_code == 503                    # este Nexus de teste não envia: o App manda pela reserva
    r = c.post("/t/base/emails-automaticos/api/evento", data=raw,
               headers={"X-Nexus-Ts": h["X-Nexus-Ts"], "X-Nexus-Assinatura": "0" * 64})
    assert r.status_code == 401
