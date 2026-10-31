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
        return True

    def ligar(self):
        AC.ligar_leitor(pedir_novos=self.pedir, esperar_novos=self.esperar, estado=lambda: {"ligado": True})
        AC.anotar_paridade_rest({"vale": True, "motivo": "conferida"})
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
    h = cli.get("/os/solicitacao/fila?recusa=A%20leitura%20do%20Fracttal%20de%2031/10%2002:20%20n%C3%A3o%20entrou").get_data(
        as_text=True)
    assert esperado in h and "A leitura do Fracttal de 31/10 02:20 não entrou" in h       # a Fila mostra o motivo da volta

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
