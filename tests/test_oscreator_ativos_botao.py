"""Os três botões "Atualizar ativos" sem esperar o Fracttal (31/10/2026, tarefa 2.3 do canto central do OS Creator).

Antes, os três (OS Creator -> Ativos, o ↻ do Criar OS e o "Recarregar o catálogo de ativos" da Fila do PCM) baixavam os ~22 mil
ativos pelo RPC NA FRENTE de quem clicou (~110 pedidos, minutos). Com o leitor do servidor pronto (`ativos_leitor.py`, a leitura
REST conferida), o botão pede os ativos NOVOS por trás e responde na hora com "ativos de HH:MM"; a tela que vem depois espera a
leitura em curso (`?novos=1`, poucos segundos) e já mostra os novos. Sem o leitor (o PC, os testes, a paridade que falhou), o
botão segue pelo RPC com a sessão da pessoa, como sempre.
Fracttal e banco são dublês: nada vai à rede. Nomes, códigos e usinas são de mentira (repositório público)."""
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
import ativos_central as AC  # noqa: E402
from os_web import criar_app, sessao  # noqa: E402

WEB = Path(ponte.RAIZ_CLONE) / "os_web"
JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
_BRT = timezone(timedelta(hours=-3))
USINA = "Cliente Alfa - Usina Gama 1 - PA"


def _reg(i, code, usina=USINA, cliente="Cliente Alfa"):
    return {"id": i, "code": code, "description": "Inversor %d" % i, "id_parent": 10, "id_type_item": 2,
            "id_group_task": None, "parent_description": "// %s/ %s/ " % (cliente, usina), "cliente": cliente,
            "usina": usina, "tipo_code": "INVR", "tipo": "Inversor", "label": "%s — Inversor %d" % (code, i)}


LOTE = [_reg(1000 + k, "CAL-GAM100-INVR%d.1" % k) for k in range(20)]
NOVO = _reg(5000, "CAL-GAM100-INVR99.1")


@pytest.fixture(autouse=True)
def _limpo(monkeypatch):
    AC.reiniciar()
    monkeypatch.setattr(api, "_ASSETS_RENOVA", {"tentou": time.time()})       # a renovação por trás fica de fora
    yield
    AC.reiniciar()


@pytest.fixture
def cli():
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid", "perfil": "ADMINISTRATOR"}
    return c


class LeitorFalso:
    """O leitor do servidor, de mentira: `pedir_novos` começa a leitura dos novos numa thread (que leva `demora` s e soma o
    ativo novo ao catálogo) e volta na hora; `esperar_novos` espera a que está em curso."""

    def __init__(self, demora=1.5):
        self.pedidos, self.demora, self.thread = 0, demora, None

    def pedir(self):
        self.pedidos += 1
        if self.thread is None or not self.thread.is_alive():
            def ler():
                time.sleep(self.demora)
                AC.acrescentar([NOVO], "rest")
            self.thread = threading.Thread(target=ler, name="leitor-falso")
            self.thread.start()
        return True

    def esperar(self, teto, so_em_curso=False):
        if self.thread is not None:
            self.thread.join(teto)
        terminou = self.thread is None or not self.thread.is_alive()
        return {"terminou": terminou, "acrescentados": 1 if terminou else 0, "sem_pai": 0, "muitos": 0, "erro": ""}

    def ligar(self):
        AC.ligar_leitor(pedir_novos=self.pedir, esperar_novos=self.esperar, estado=lambda: {"ligado": True})
        AC.anotar_paridade_rest({"vale": True, "motivo": "conferida", "em": time.time()})
        return self


def _sem_rpc(monkeypatch):
    baixou = []
    monkeypatch.setattr(api, "get_assets", lambda: baixou.append(1) or [dict(r) for r in LOTE])
    return baixou


def test_botao_pede_os_novos_por_tras(cli, monkeypatch):
    AC.trocar(LOTE, "rpc", lido_em=time.time() - 3600)
    leitor = LeitorFalso().ligar()
    baixou = _sem_rpc(monkeypatch)

    # OS Creator -> Ativos: volta na hora (antes da leitura dos novos acabar), sem o RPC, dizendo de quando é a lista
    t0 = time.perf_counter()
    r = cli.post("/os/api/ativos/atualizar")
    assert time.perf_counter() - t0 < leitor.demora and r.status_code == 200 and leitor.thread.is_alive()
    j = r.get_json()
    assert j["novos"] is True and j["ativos_de"].startswith("ativos de ") and j["n"] == len(LOTE)
    assert leitor.pedidos == 1 and baixou == []
    # a lista que a tela pede logo depois (`?novos=1`) espera a leitura em curso e já vem com o ativo novo
    lista = cli.get("/os/api/ativos/catalogo?novos=1").get_json()
    assert "CAL-GAM100-INVR99.1" in {a["code"] for a in lista["ativos"]} and baixou == []

    # o ↻ do Criar OS: o mesmo
    t0 = time.perf_counter()
    j = cli.get("/os/api/tradicional/catalogo?recarregar=1").get_json()
    assert time.perf_counter() - t0 < leitor.demora and leitor.thread.is_alive()
    assert j["novos"] is True and j["recarregado"] is True
    assert j["ativos_de"].startswith("ativos de ") and leitor.pedidos == 2 and baixou == []
    assert cli.get("/os/api/tradicional/catalogo?novos=1").get_json()["clientes"] == ["Cliente Alfa"]

    # o link da Fila do PCM: volta na hora à Fila, que espera a leitura em curso (`novos=1`)
    t0 = time.perf_counter()
    r = cli.get("/os/solicitacao/atualizar?sel=5001")
    assert time.perf_counter() - t0 < leitor.demora and leitor.thread.is_alive() and r.status_code == 302
    assert "novos=1" in r.headers["Location"] and "sel=5001" in r.headers["Location"] and leitor.pedidos == 3
    assert baixou == []
    leitor.thread.join(5)                                         # a leitura de mentira não passa para o teste seguinte


def test_tela_diz_ativos_de_hhmm(cli, monkeypatch):
    hoje = datetime(2026, 10, 31, 14, 30, tzinfo=_BRT).timestamp()
    AC.trocar(LOTE, "rpc", lido_em=datetime(2026, 10, 31, 2, 20, tzinfo=_BRT).timestamp())
    cat = AC.atual()
    assert api.ativos_de(cat, agora=hoje) == "ativos de 02:20"
    # os novos do dia contam (a lista foi comparada com o Fracttal de novo): a hora deles
    AC.acrescentar([NOVO], "rest", lido_em=datetime(2026, 10, 31, 14, 8, tzinfo=_BRT).timestamp())
    assert api.ativos_de(AC.atual(), agora=hoje) == "ativos de 14:08" and AC.atual().lido_em == cat.lido_em
    # de outro dia: com a data (à 01:00, "de 02:20" seria lido como a de hoje)
    assert api.ativos_de(AC.atual(), agora=datetime(2026, 11, 1, 1, 0, tzinfo=_BRT).timestamp()) == "ativos de 31/10 14:08"
    assert api.ativos_de(AC.VAZIO) == "" and api.assets_cache_info()["ativos_de"].startswith("ativos de ")

    # as três telas mostram (sem o leitor, como no PC: o botão baixa pelo RPC, e a hora passa a ser a do download)
    _sem_rpc(monkeypatch)
    j = cli.post("/os/api/ativos/atualizar").get_json()
    assert j["ativos_de"] == api.ativos_de() and j["ativos_de"].startswith("ativos de ")
    assert cli.get("/os/api/ativos/catalogo").get_json()["info"]["ativos_de"] == api.ativos_de()
    j = cli.get("/os/api/tradicional/catalogo?recarregar=1").get_json()
    assert j["ativos_de"] == api.ativos_de()
    esperado = api.ativos_de()
    assert esperado in cli.get("/os/tradicional").get_data(as_text=True)
    monkeypatch.setattr(api, "list_minhas_solicitacoes", lambda *a, **k: [])
    for nome in ("get_responsaveis", "get_labels"):
        monkeypatch.setattr(api, nome, lambda *a, **k: [{"id": 1, "name": "Pessoa Teste", "description": "Etiqueta"}])
    monkeypatch.setattr(api, "get_tipos_classif", lambda *a, **k: {"tipos": [{"id": 1, "description": "Corretiva"}]})
    monkeypatch.setattr(api, "status_solicitacao_catalogo", lambda *a, **k: list(api.STATUS_SOLICITACAO))
    h = cli.get("/os/solicitacao/fila").get_data(as_text=True)
    assert esperado in h and 'title="%s"' % api.ativos_de_titulo() in h

    # o JavaScript das duas telas usa o que o servidor diz (sem montar a hora no navegador), e pede `?novos=1` depois do botão
    ativos_js = (WEB / "static" / "ativos.js").read_text(encoding="utf-8")
    assert "info.ativos_de" in ativos_js and "?novos=1" in ativos_js and "j.recusa" in ativos_js
    trad_js = (WEB / "static" / "tradicional.js").read_text(encoding="utf-8")
    assert "j.ativos_de" in trad_js and "?novos=1" in trad_js and "j.recusa" in trad_js
    # sem emoji na interface (o ↻ do Criar OS dizia o erro com um sinal de alerta), e sem cor fixa nas linhas novas
    recarregar = trad_js.split("$('b_reload').onclick", 1)[1].split("\n  };", 1)[0]
    assert "⚠" not in ativos_js and "⚠" not in recarregar and "Não consegui recarregar" in recarregar
    for arq in ("tradicional.html", "solic_fila.html"):                  # a de Ativos mostra pelo JavaScript, acima
        t = (WEB / "templates" / arq).read_text(encoding="utf-8")
        assert "ativos_de" in t and not re.search(r"ativos_de[^\n]*(#[0-9a-fA-F]{3,6}\b|rgba?\()", t), arq


def test_pc_usa_a_sessao_da_pessoa(cli, monkeypatch):
    """Sem o leitor (o PC, `app.py`), o botão baixa pelo RPC com a sessão de quem clicou, como sempre, para o catálogo central."""
    AC.trocar(LOTE, "rpc", lido_em=time.time() - 3600)
    quem = []

    def get_assets():
        quem.append(sessao.jwt_atual())
        return [dict(r) for r in LOTE] + [dict(NOVO)]
    monkeypatch.setattr(api, "get_assets", get_assets)
    assert not AC.leitor_pronto()
    j = cli.post("/os/api/ativos/atualizar").get_json()
    assert quem == [JWT] and j["novos"] is False and j["n"] == len(LOTE) + 1 and j["delta"] == 1
    assert AC.atual().fonte == "rpc" and "CAL-GAM100-INVR99.1" in AC.atual().por_codigo
    # o leitor ligado mas com a paridade que falhou: também pelo RPC
    pediu = []
    AC.ligar_leitor(pedir_novos=lambda: pediu.append(1), esperar_novos=lambda t, s: True, estado=lambda: {})
    AC.anotar_paridade_rest({"vale": False, "motivo": "faltou o tipo"})
    j = cli.get("/os/api/tradicional/catalogo?recarregar=1").get_json()
    assert j["novos"] is False and quem == [JWT, JWT] and pediu == []
    r = cli.get("/os/solicitacao/atualizar")
    assert r.status_code == 302 and "novos=1" not in r.headers["Location"] and quem == [JWT, JWT, JWT]


# ── a revisão 1 da 2.2+2.3 ──────────────────────────────────────────────────────────────────────────────────────────────
def _fila_sem_fracttal(monkeypatch):
    """A Fila do PCM sem pedir nada ao Fracttal: a lista de solicitações vazia e os catálogos de mentira."""
    monkeypatch.setattr(api, "list_minhas_solicitacoes", lambda *a, **k: [])
    for nome in ("get_responsaveis", "get_labels"):
        monkeypatch.setattr(api, nome, lambda *a, **k: [{"id": 1, "name": "Pessoa Teste", "description": "Etiqueta"}])
    monkeypatch.setattr(api, "get_tipos_classif", lambda *a, **k: {"tipos": [{"id": 1, "description": "Corretiva"}]})
    monkeypatch.setattr(api, "status_solicitacao_catalogo", lambda *a, **k: list(api.STATUS_SOLICITACAO))


def test_o_desfecho_dos_novos_na_tela(cli, app, monkeypatch):
    """Important 1: "nenhum ativo novo no Fracttal" só quando a busca terminou bem sem nada; a que não terminou, a que falhou
    e a que deixou ativos para a noite dizem o que houve. Com o leitor de verdade (as funções do `ativos_leitor`) e o REST de
    mentira no `fracttal.ler`."""
    import ativos_leitor as AL
    from nexus.campo import fracttal
    from test_oscreator_ativos_leitor import RestFalso, _catalogo_de, _it, _muitos
    AL.reiniciar()
    monkeypatch.setattr(AL, "_dormir", lambda s: None)
    base = _muitos(60)
    _catalogo_de(base)
    AC.anotar_paridade_rest({"vale": True, "motivo": "conferida", "em": time.time()})
    app.config["NEXUS_PCM_FRACTTAL_TESTE"] = {"FRACTTAL_CLIENT_ID": "id-de-mentira", "FRACTTAL_CLIENT_SECRET": "s"}
    AL.ligar(app)
    fonte = {"ler": RestFalso(base)}
    monkeypatch.setattr(fracttal, "ler", lambda path: fonte["ler"](path))

    def apertar(url="/os/api/ativos/catalogo?novos=1"):
        AL._NOVOS["fim_em"] = 0.0                                       # cada caso, uma leitura nova (sem o frescor de 60 s)
        assert cli.post("/os/api/ativos/atualizar").get_json()["novos"] is True
        return cli.get(url).get_json()["novos_desfecho"]

    def novo(i, pai=10):
        return _it(i, "CAL-GAM100-INVR9%d.1" % (i - 5000), "Inversor novo %d    { x }" % i, pai)
    try:
        d = apertar()                                                   # terminou bem, sem nada
        assert d["terminou"] and d["ok"] and d["texto"] == "nenhum ativo novo no Fracttal"
        fonte["ler"] = RestFalso(base + [novo(5000), novo(5001)])       # terminou bem, com 2
        d = apertar("/os/api/tradicional/catalogo?novos=1")
        assert d["ok"] and d["acrescentados"] == 2 and d["texto"] == "2 ativos novos do Fracttal na lista"
        fonte["ler"] = RestFalso(base + [novo(5000), novo(5001), novo(5002, pai=4242)])     # um sem o pai no catálogo
        d = apertar()
        assert not d["ok"] and d["sem_pai"] == 1 and d["texto"] == "1 ativo novo fica para a leitura da noite"
        solta = threading.Event()                                        # não terminou dentro da espera

        def lento(path):
            solta.wait(5)
            return RestFalso(base + [novo(5000), novo(5001)])(path)
        fonte["ler"] = lento
        monkeypatch.setattr(api, "ESPERA_NOVOS_S", 0.2)
        d = apertar()
        assert not d["terminou"] and d["texto"].startswith("a busca no Fracttal ainda não terminou")
        solta.set()
        AL.esperar_novos(5, so_em_curso=True)
        monkeypatch.setattr(api, "ESPERA_NOVOS_S", 6)
        fonte["ler"] = RestFalso(base + [novo(5003)], ignora_sort=True)  # falhou (o REST ignorou a ordem)
        d = apertar()
        assert not d["ok"] and d["texto"].startswith("não consegui buscar os ativos novos no Fracttal: a página não veio")
        assert not AC.leitor_pronto()                                   # e o botão seguinte já vai pelo RPC
        monkeypatch.setattr(api, "get_assets", lambda: [dict(r) for r in AC.atual().lista])
        assert cli.post("/os/api/ativos/atualizar").get_json()["novos"] is False
    finally:
        AL.reiniciar()
    js = (WEB / "static" / "ativos.js").read_text(encoding="utf-8")
    assert "d.novos_desfecho" in js and "dn.ok && delta" in js and "dn.texto" in js
    assert "j.novos_desfecho" in (WEB / "static" / "tradicional.js").read_text(encoding="utf-8")


def test_a_fila_mostra_o_desfecho_dos_novos(cli, monkeypatch):
    _fila_sem_fracttal(monkeypatch)
    AC.trocar(LOTE, "rpc", lido_em=time.time() - 3600)
    AC.ligar_leitor(pedir_novos=lambda: True, estado=lambda: {},
                    esperar_novos=lambda teto, so: {"terminou": True, "acrescentados": 0, "sem_pai": 0, "muitos": 0, "erro": ""})
    AC.anotar_paridade_rest({"vale": True, "em": time.time()})
    r = cli.get("/os/solicitacao/atualizar?sel=5001")
    assert "novos=1" in r.headers["Location"]
    h = cli.get(r.headers["Location"]).get_data(as_text=True)
    assert 'id="fl_novos">nenhum ativo novo no Fracttal</p>' in h


def test_a_falha_lembrada_vai_aos_botoes_e_a_sessao_de_uma_pessoa_nao(cli, monkeypatch):
    """Minor 4: dentro da janela da falha, os botões devolvem a lista de antes e dizem por quê; a sessão recusada de UMA pessoa
    (401/403) não segura o download de mais ninguém."""
    _fila_sem_fracttal(monkeypatch)
    AC.trocar(LOTE, "rpc", lido_em=time.time() - api.ASSETS_TTL - 60)     # vencido, sem o leitor
    tentou = []

    def fora():
        tentou.append("fora")
        raise api.FracttalError("RPC inventories.items_list HTTP 503 (indisponível)")
    monkeypatch.setattr(api, "get_assets", fora)
    with pytest.raises(api.FracttalError):
        api.load_assets_cached(True)                                    # a 1ª: falha (a tela já mostrava o erro)
    j = cli.post("/os/api/ativos/atualizar").get_json()
    assert tentou == ["fora"] and j["n"] == len(LOTE) and "O Fracttal não deu os ativos" in j["falha"] and "503" in j["falha"]
    assert "503" in cli.get("/os/api/tradicional/catalogo?recarregar=1").get_json()["falha"] and tentou == ["fora"]
    r = cli.get("/os/solicitacao/atualizar?sel=5001")
    assert "falha=1" in r.headers["Location"] and "indispon" not in r.headers["Location"]
    assert "HTTP 503" in cli.get(r.headers["Location"]).get_data(as_text=True)
    # a sessão de uma pessoa que caiu: não vira falha de todos, e o próximo tenta
    AC.anotar_falha("rpc", None)

    def expirou():
        tentou.append("sessao")
        raise api.SessionExpired("Login recusado (HTTP 401): faça login de novo no app.")
    monkeypatch.setattr(api, "get_assets", expirou)
    with pytest.raises(api.SessionExpired):
        api.load_assets_cached(True)
    assert AC.falha() is None and api.aviso_da_falha() == ""
    monkeypatch.setattr(api, "get_assets", lambda: tentou.append("ok") or [dict(r) for r in LOTE])
    api.load_assets_cached(True)
    assert tentou == ["fora", "sessao", "ok"]


def test_a_fila_nao_ecoa_texto_da_url(cli, monkeypatch):
    """Minor 11: a URL só traz o sinal (`?recusa=1`, `?falha=1`); o texto é o do servidor, e nada escrito na URL vai à tela."""
    _fila_sem_fracttal(monkeypatch)
    AC.trocar(LOTE, "rpc", lido_em=time.time() - 3600)
    h = cli.get("/os/solicitacao/fila?recusa=Clique%20aqui%20para%20ganhar&falha=Outro%20texto%20de%20fora").get_data(
        as_text=True)
    assert "Clique aqui para ganhar" not in h and "Outro texto de fora" not in h and 'id="fl_recusa"' not in h
    assert not AC.trocar(LOTE[:5], "rpc")                               # uma leitura recusada de verdade (encolheu)
    AC.anotar_falha("rpc", api.FracttalError("HTTP 502"))
    h = cli.get("/os/solicitacao/fila?recusa=1&falha=1").get_data(as_text=True)
    assert api.aviso_da_recusa() in h and "encolheu de 20 para 5" in h and "HTTP 502" in h


def test_a_aprovacao_espera_os_novos_so_sem_o_ativo():
    """Minor 13: a aprovação que acha o ativo no catálogo não espera nada; a que não acha espera os novos e procura de novo."""
    from os_web import rotas_solic as rs
    AC.trocar(LOTE, "rpc", lido_em=time.time() - 3600)
    esperas = []

    def esperar(teto, so_em_curso):
        esperas.append(so_em_curso)
        AC.acrescentar([NOVO], "rest")
        return {"terminou": True, "acrescentados": 1, "sem_pai": 0, "muitos": 0, "erro": ""}
    AC.ligar_leitor(pedir_novos=lambda: True, esperar_novos=esperar, estado=lambda: {})
    AC.anotar_paridade_rest({"vale": True, "em": time.time()})
    assert rs._ativo_para_aprovar({"id_item": 1003, "code": LOTE[3]["code"]})["id"] == 1003 and esperas == []
    assert rs._ativo_para_aprovar({"id_item": 5000, "code": NOVO["code"]})["id"] == 5000 and esperas == [False]
    # sem o leitor pronto, como sempre: não espera nada (e quem não acha, não acha)
    AC.anotar_paridade_rest(None)
    assert rs._ativo_para_aprovar({"id_item": 7777, "code": "NAO-EXISTE"}) is None and esperas == [False]


def test_o_titulo_diz_as_duas_horas(cli):
    """Ruling AL: "ativos de HH:MM" segue pela mais nova das duas horas; o `title` diz as duas."""
    hoje = datetime(2026, 10, 31, 14, 30, tzinfo=_BRT).timestamp()
    AC.trocar(LOTE, "rpc", lido_em=datetime(2026, 10, 31, 2, 20, tzinfo=_BRT).timestamp())
    assert api.ativos_de_titulo(agora=hoje) == "lista completa de 31/10 02:20"
    AC.acrescentar([NOVO], "rest", lido_em=datetime(2026, 10, 31, 14, 8, tzinfo=_BRT).timestamp())
    assert api.ativos_de_titulo(agora=hoje) == "lista completa de 31/10 02:20; novos até 14:08"
    assert api.ativos_de(agora=hoje) == "ativos de 14:08"
    assert api.ativos_de_titulo(agora=datetime(2026, 11, 1, 9, 0, tzinfo=_BRT).timestamp()) == (
        "lista completa de 31/10 02:20; novos até 31/10 14:08")
    titulo = api.ativos_de_titulo()
    assert cli.get("/os/api/ativos/catalogo").get_json()["info"]["ativos_de_titulo"] == titulo
    assert 'title="%s"' % titulo in cli.get("/os/tradicional").get_data(as_text=True)
    assert "info.ativos_de_titulo" in (WEB / "static" / "ativos.js").read_text(encoding="utf-8")


def test_o_cabecalho_de_ativos_no_celular():
    """A bancada a 375 px: o cabeçalho espremia o subtítulo em 4 linhas e a busca cortava em "códi". Abaixo de 480 px a busca
    desce para a linha de baixo, inteira; só CSS, sem cor nova."""
    css = (WEB / "static" / "ativos.css").read_text(encoding="utf-8")
    bloco = css.split("@media (max-width:480px){", 1)[1].split("\n}", 1)[0]
    assert ".at-cab{flex-wrap:wrap" in bloco and ".at-busca{flex:1 1 100%;width:100%}" in bloco
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b|rgba?\(", bloco)
