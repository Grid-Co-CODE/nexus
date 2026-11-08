"""As três rotas do contrato do Mapa de equipe com o Nexus Field (08/11/2026; `nexus/torres/campo/equipe_tela.py` e o
estado do processo em `nexus/campo/equipe/servico.py`).

O contrato (seção 8 do desenho, confirmado pela casca): a PÁGINA do App de Campo registra o aparelho com o ID token da
Microsoft (CORS só para a origem do App) e recebe a chave; o NATIVO manda as posições e revoga a chave com ela. 401 só
quando a chave ou o token não valem (a casca apaga a chave); 503 quando o servidor não tem como decidir agora (a
Microsoft ou o banco fora, a configuração faltando): a casca guarda a fila e a chave e tenta de novo.

Nada vai à rede: o token é trocado por um falso (`token_ms.conferir`), salvo nos testes que provam a configuração com o
conferidor de verdade; o banco é o `ApiPGFalsa`; o relógio é parado (`servico._agora`). Pessoas, e-mails e GUIDs de
mentira."""
import hashlib
import json
import logging
from datetime import date, datetime, timedelta, timezone

import pytest
import requests
from pg_falso import ApiPGFalsa
from test_campo_visao import _aba

from nexus.auth import ROTAS_PUBLICAS
from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.campo import visao
from nexus.campo.equipe import (ABA_APARELHOS, ABA_PILOTO, CAB_APARELHOS, LIVRO_APARELHOS, LIVRO_PILOTO, MAX_PONTOS,
                                ORIGEM_APP)
from nexus.campo.equipe import servico as S
from nexus.campo.equipe import token_ms as T

DIRETORIO = "11111111-2222-3333-4444-555555555555"
CLIENTE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
CHAVE_CADASTRO = gerar_chave()
AGORA = datetime(2026, 11, 8, 15, 0, tzinfo=timezone.utc)          # 12:00 em Brasília: dentro da janela das 6h às 22h
URL_APARELHO = "/t/campo/equipe/aparelho"
URL_POSICOES = "/t/campo/equipe/posicoes"
URL_REVOGAR = "/t/campo/equipe/aparelho/revogar"
OUTRA_ORIGEM = "https://outro-site.exemplo.test"
LAT, LON = -23.5505, -46.6333                                       # a coordenada de mentira dos pontos

# as pessoas do cadastro: o técnico do piloto, um técnico fora dele, uma supervisora (no piloto, mas não é técnica de
# campo) e um técnico desligado (no piloto)
TECNICO, FORA_DO_PILOTO, SUPERVISORA, DESLIGADO = 1, 2, 3, 4
EMAIL = {TECNICO: "tecnico.um@gridco.com.br", FORA_DO_PILOTO: "tecnico.dois@gridco.com.br",
         SUPERVISORA: "supervisora.campo@gridco.com.br", DESLIGADO: "tecnico.saiu@gridco.com.br"}


def _pessoas(desligar=()):
    cofre = Cofre(CHAVE_CADASTRO)

    def p(pid, vinculo, status, nome):
        if pid in desligar:
            status = "Desligado"
        sensivel = json.dumps({"nome": nome, "nome_padrao": nome, "email": EMAIL[pid]})
        return {"pessoa_id": pid, "vinculo": vinculo, "cargo": "Técnico O&M", "equipe_id": 10, "status": status,
                "excluido": "não", "sensivel_cifrado": cofre.cifrar(sensivel, f"banco/pessoas/{pid}")}
    return [p(TECNICO, "Colaborador de campo", "Ativo", "Técnico Um Teste"),
            p(FORA_DO_PILOTO, "Colaborador de campo", "Ativo", "Técnico Dois Teste"),
            p(SUPERVISORA, "Supervisor de Campo", "Ativo", "Supervisora Campo Teste"),
            p(DESLIGADO, "Colaborador de campo", "Desligado", "Técnico Saiu Teste")]


def _decisao(pid, no_piloto, instante="2026-11-07T12:00:00Z"):
    return {"decisao_id": f"D{pid}{instante[11:13]}", "instante": instante, "data_id": 20261107, "pessoa_id": pid,
            "no_piloto": no_piloto, "decidida_por_hmac": "hmac-de-teste"}


PILOTO = [_decisao(TECNICO, "sim"), _decisao(SUPERVISORA, "sim"), _decisao(DESLIGADO, "sim")]


class Relogio:
    def __init__(self):
        self.agora = AGORA

    def andar(self, **kw):
        self.agora += timedelta(**kw)


class MicrosoftFalsa:
    """O `token_ms.conferir` de mentira: "token:<e-mail>" é o ID token do App de Campo daquela pessoa; o resto é
    recusado. Guarda cada chamada (a ida à Microsoft, para o teto) com o que a rota passou."""

    def __init__(self):
        self.chamadas, self.fora = [], False

    def conferir(self, token, *, cliente, diretorio, dominios=("gridco.com.br",), chaves_jwks=None, agora=None):
        self.chamadas.append({"cliente": cliente, "diretorio": diretorio, "dominios": tuple(dominios), "agora": agora})
        if self.fora:
            raise T.MicrosoftForaDoAr("chaves da Microsoft: ConnectionError")
        if not token.startswith("token:"):
            raise T.TokenRecusado("assinatura não confere")
        return token.removeprefix("token:")


class SessaoFora:
    """O banco fora do ar: todo pedido levanta, como a rede caída."""

    def get(self, *a, **k):
        raise requests.ConnectionError("banco fora (teste)")

    post = get


@pytest.fixture
def relogio(monkeypatch):
    r = Relogio()
    monkeypatch.setattr(S, "_agora", lambda: r.agora)
    return r


@pytest.fixture
def banco(app, tmp_path, monkeypatch, relogio):
    api = ApiPGFalsa()
    _aba(api, "cadastro_nexus", "pessoas", _pessoas())
    _aba(api, LIVRO_PILOTO, ABA_PILOTO, PILOTO)
    app.config.update(GRIDCO_DB_API="http://pg.falso", NEXUS_CHAVE_CADASTRO=CHAVE_CADASTRO,
                      NEXUS_DADOS=str(tmp_path / "dados"), NEXUS_EQUIPE_MS_CLIENT_ID=CLIENTE,
                      NEXUS_EQUIPE_MS_TENANT_ID=DIRETORIO)
    app.extensions["nexus_dados_sessao"] = api

    def a_rede(url):
        raise AssertionError(f"pedido de verdade à Microsoft: {url}")
    monkeypatch.setattr(T, "_pedir_jwks", a_rede)
    visao.limpar()
    T._GUARDADAS.clear()
    T._RELEITURA.clear()
    yield api
    visao.limpar()
    T._GUARDADAS.clear()
    T._RELEITURA.clear()


@pytest.fixture
def ms(monkeypatch):
    m = MicrosoftFalsa()
    monkeypatch.setattr(T, "conferir", m.conferir)
    return m


def _registrar(cliente, pid=TECNICO, aparelho="aparelho-1", origem=ORIGEM_APP, token=None, app="NexusField/1.2.0"):
    h = {"Authorization": f"Bearer {token or 'token:' + EMAIL[pid]}"}
    if origem:
        h["Origin"] = origem
    return cliente.post(URL_APARELHO, json={"aparelho": aparelho, "app": app}, headers=h)


def _chave(cliente, pid=TECNICO, aparelho="aparelho-1") -> str:
    r = _registrar(cliente, pid, aparelho)
    assert r.status_code == 200 and r.get_json()["coleta"] is True, r.get_data(as_text=True)
    return r.get_json()["chave"]


def _ponto(minutos_atras=0, mov=False):
    t = int((AGORA - timedelta(minutes=minutos_atras)).timestamp() * 1000)
    return {"t": t, "lat": LAT, "lon": LON, "prec": 8.0, "vel": 1.5 if mov else 0.0, "mov": mov}


def _posicoes(cliente, chave, pontos=(), aparelho="aparelho-1", **extra):
    corpo = {"aparelho": aparelho, "fuso": -180, "pontos": list(pontos), **extra}
    return cliente.post(URL_POSICOES, json=corpo, headers={"Authorization": f"Bearer {chave}"})


def _revogar(cliente, chave, aparelho="aparelho-1"):
    h = {"Authorization": f"Bearer {chave}"} if chave else {}
    return cliente.post(URL_REVOGAR, json={"aparelho": aparelho}, headers=h)


def _reiniciar(app, api):
    """O Nexus reinicia: o que a gravação em lote (Task 6) teria publicado dos aparelhos vai ao livro do banco falso, e
    o serviço sai da memória (o próximo pedido o cria de novo, do diário em disco e do livro)."""
    srv = app.extensions.pop("nexus_equipe")
    novas = [dict(zip(CAB_APARELHOS, x)) for x in srv.chaveiro.eventos_novos()]
    _aba(api, LIVRO_APARELHOS, ABA_APARELHOS, api.linhas(LIVRO_APARELHOS, ABA_APARELHOS) + novas)


# ── CORS: só a página do App ──────────────────────────────────────────────────────────────────────────────────────────
def test_o_preflight_so_abre_para_a_origem_do_app(cliente, banco):
    pede = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization, content-type"}
    r = cliente.options(URL_APARELHO, headers={"Origin": ORIGEM_APP, **pede})
    assert r.status_code == 204
    assert r.headers["Access-Control-Allow-Origin"] == ORIGEM_APP
    cab = {x.strip().lower() for x in r.headers["Access-Control-Allow-Headers"].split(",")}
    assert {"authorization", "content-type"} <= cab
    assert "POST" in r.headers["Access-Control-Allow-Methods"]
    assert "Origin" in r.headers.get("Vary", "")
    assert "Access-Control-Allow-Credentials" not in r.headers          # o token vai no cabeçalho; cookie nenhum
    # outra origem, a que só começa igual e o pedido sem origem: sem o cabeçalho, o navegador barra
    for origem in (OUTRA_ORIGEM, ORIGEM_APP + ".exemplo.test", "null", None):
        h = {**pede, **({"Origin": origem} if origem else {})}
        r = cliente.options(URL_APARELHO, headers=h)
        assert "Access-Control-Allow-Origin" not in r.headers, origem
    # as rotas do nativo não abrem CORS para ninguém, nem para a página do App
    for url in (URL_POSICOES, URL_REVOGAR):
        r = cliente.options(url, headers={"Origin": ORIGEM_APP, **pede})
        assert "Access-Control-Allow-Origin" not in r.headers, url


def test_o_post_leva_o_cors_da_origem_do_app_em_toda_resposta(cliente, banco, ms):
    """A página só lê o código da resposta com o cabeçalho: sem ele no 401, ela não saberia que tem de pedir de novo."""
    for r in (_registrar(cliente), _registrar(cliente, token="token-forjado")):
        assert r.status_code in (200, 401)
        assert r.headers["Access-Control-Allow-Origin"] == ORIGEM_APP and "Origin" in r.headers["Vary"]
    r = _registrar(cliente, origem=OUTRA_ORIGEM)
    assert r.status_code == 200 and "Access-Control-Allow-Origin" not in r.headers
    assert "Origin" in r.headers["Vary"]                                  # a cópia de um proxy não serve à outra origem


# ── o registro do aparelho ───────────────────────────────────────────────────────────────────────────────────────────
def test_registro_do_tecnico_do_piloto_devolve_a_chave(app, cliente, banco, ms):
    r = _registrar(cliente)
    assert r.status_code == 200
    corpo = r.get_json()
    assert set(corpo) == {"coleta", "chave"} and corpo["coleta"] is True
    chave = corpo["chave"]
    assert len(chave) == 43 and "=" not in chave
    assert "no-store" in r.headers["Cache-Control"]                       # a chave não fica em cache nenhum
    # a rota passou a configuração e os domínios da Grid ao conferidor
    assert ms.chamadas[-1]["cliente"] == CLIENTE and ms.chamadas[-1]["diretorio"] == DIRETORIO
    assert ms.chamadas[-1]["dominios"] == ("gridco.com.br",)
    # o banco só verá o hash; a chave em claro não está no evento
    ev = [dict(zip(CAB_APARELHOS, x)) for x in S.do_app(app).chaveiro.eventos_novos()]
    assert [(e["evento"], e["pessoa_id"], e["aparelho"], e["app"]) for e in ev] == [
        ("emitida", TECNICO, "aparelho-1", "NexusField/1.2.0")]
    assert ev[0]["chave_hash"] == hashlib.sha256(chave.encode()).hexdigest() and chave not in str(ev)


def test_registro_fora_do_piloto_devolve_coleta_false(app, cliente, banco, ms):
    # fora do piloto; no piloto mas não é técnico de campo; no piloto mas desligado; e-mail que o cadastro não conhece
    for token in ("token:" + EMAIL[FORA_DO_PILOTO], "token:" + EMAIL[SUPERVISORA], "token:" + EMAIL[DESLIGADO],
                  "token:ninguem.aqui@gridco.com.br"):
        r = _registrar(cliente, token=token)
        assert r.status_code == 200 and r.get_json() == {"coleta": False}, token
    assert S.do_app(app).chaveiro.eventos_novos() == []                    # ninguém recebeu chave


def test_token_invalido_e_401_e_microsoft_fora_e_503(cliente, banco, ms):
    assert _registrar(cliente, token="token-forjado").status_code == 401
    sem = cliente.post(URL_APARELHO, json={"aparelho": "aparelho-1", "app": "NexusField/1.2.0"},
                       headers={"Origin": ORIGEM_APP})
    assert sem.status_code == 401 and sem.headers["Access-Control-Allow-Origin"] == ORIGEM_APP
    ms.fora = True
    r = _registrar(cliente)
    assert r.status_code == 503 and "erro" in r.get_json()                  # 503, nunca 401: a casca não apaga a chave
    assert r.headers["Access-Control-Allow-Origin"] == ORIGEM_APP


def test_microsoft_fora_tem_teto_de_1_min(cliente, banco, ms, relogio):
    """Sem a cópia das chaves e com a Microsoft fora, cada registro esperaria 10 s pela Microsoft: depois de uma falha,
    o próximo minuto responde 503 na hora, sem ir a ela."""
    ms.fora = True
    assert _registrar(cliente).status_code == 503 and len(ms.chamadas) == 1
    assert _registrar(cliente).status_code == 503 and len(ms.chamadas) == 1
    relogio.andar(seconds=59)
    assert _registrar(cliente).status_code == 503 and len(ms.chamadas) == 1
    relogio.andar(seconds=2)                                               # 61 s depois da falha: tenta de novo
    assert _registrar(cliente).status_code == 503 and len(ms.chamadas) == 2
    ms.fora = False
    relogio.andar(seconds=61)
    assert _registrar(cliente).status_code == 200 and len(ms.chamadas) == 3


def test_id_da_configuracao_que_nao_e_guid_e_503_e_nao_vai_a_microsoft(app, cliente, banco):
    """Com o conferidor de verdade: o GUID errado na configuração é erro do servidor (503, com o nome da chave), não
    token ruim (401 apagaria a chave da casca). O `_pedir_jwks` do fixture quebra o teste se for à Microsoft."""
    for nome in ("NEXUS_EQUIPE_MS_CLIENT_ID", "NEXUS_EQUIPE_MS_TENANT_ID"):
        app.config.update(NEXUS_EQUIPE_MS_CLIENT_ID=CLIENTE, NEXUS_EQUIPE_MS_TENANT_ID=DIRETORIO)
        app.config[nome] = "gridco.com.br"
        r = _registrar(cliente, token="a.b.c")
        assert r.status_code == 503 and nome in r.get_json()["erro"], nome
        assert "gridco.com.br" not in r.get_json()["erro"]                  # o valor colado não volta na resposta


@pytest.mark.parametrize("falta", ["NEXUS_CHAVE_CADASTRO", "NEXUS_EQUIPE_MS_CLIENT_ID", "NEXUS_EQUIPE_MS_TENANT_ID"])
def test_sem_configuracao_as_tres_rotas_respondem_503_com_o_que_falta(app, cliente, banco, ms, falta):
    chave = _chave(cliente)
    app.extensions.pop("nexus_equipe")
    app.config[falta] = ""
    respostas = [_registrar(cliente), _posicoes(cliente, chave, [_ponto()]), _revogar(cliente, chave)]
    for r in respostas:
        assert r.status_code == 503 and falta in r.get_json()["erro"], (falta, r.request.path)
    assert respostas[0].headers["Access-Control-Allow-Origin"] == ORIGEM_APP


@pytest.mark.parametrize("corpo", [
    "isto não é JSON", "[1, 2]", "[" * 30000,                               # o JSON fundo demais não vira 500
    {"app": "NexusField/1.2.0"}, {"aparelho": "", "app": "NexusField/1.2.0"},
    {"aparelho": "a" * 65, "app": "NexusField/1.2.0"}, {"aparelho": "aparelho 1", "app": "NexusField/1.2.0"},
    {"aparelho": 123, "app": "NexusField/1.2.0"}, {"aparelho": "aparelho-1", "app": "N" * 41},
    {"aparelho": "aparelho-1", "app": "=HYPERLINK(\"x\")"}, {"aparelho": "aparelho-1", "app": "NexusField\n1.2"},
    {"aparelho": "aparelho-1", "app": 12}])
def test_corpo_ruim_no_registro_e_400(cliente, banco, ms, corpo):
    h = {"Authorization": "Bearer token:" + EMAIL[TECNICO], "Origin": ORIGEM_APP}
    if isinstance(corpo, str):
        r = cliente.post(URL_APARELHO, data=corpo, content_type="application/json", headers=h)
    else:
        r = cliente.post(URL_APARELHO, json=corpo, headers=h)
    assert r.status_code == 400 and "erro" in r.get_json()
    assert r.headers["Access-Control-Allow-Origin"] == ORIGEM_APP
    assert ms.chamadas == []                                               # nem chegou a conferir o token


# ── as posições ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_posicoes_com_a_chave_gravam_e_respondem_aceitos(app, cliente, banco, ms, tmp_path):
    chave = _chave(cliente)
    fora_da_janela = _ponto(7 * 60)                                        # 05:00 em Brasília
    velho = _ponto(7 * 24 * 60 + 10)                                       # mais de 7 dias
    r = _posicoes(cliente, chave, [_ponto(10), _ponto(5, mov=True), fora_da_janela, velho])
    assert r.status_code == 200 and r.get_json() == {"aceitos": 2, "coleta": True}
    assert "no-store" in r.headers["Cache-Control"]
    srv = S.do_app(app)
    dia = srv.diario.do_dia(date(2026, 11, 8))
    assert [p["instante"] for p in dia] == ["2026-11-08T14:50:00Z", "2026-11-08T14:55:00Z"]
    # no disco, nada da coordenada em claro
    texto = "".join(a.read_text(encoding="utf-8") for a in (tmp_path / "dados" / "equipe").glob("*.jsonl"))
    assert texto and str(LAT) not in texto and str(LON) not in texto
    e = srv.estado_de(TECNICO)
    assert e["ultimo"]["instante"] == "2026-11-08T14:55:00Z" and e["ultimo"]["mov"] is True
    assert e["permissao"] == "ok" and e["desde"] == AGORA
    # o lote repetido (a casca reenvia sem sinal) não duplica o diário
    assert _posicoes(cliente, chave, [_ponto(10), _ponto(5, mov=True)]).get_json() == {"aceitos": 2, "coleta": True}
    assert len(srv.diario.do_dia(date(2026, 11, 8))) == 2


def test_chave_revogada_ou_desconhecida_e_401(cliente, banco, ms):
    assert _posicoes(cliente, "x" * 43, [_ponto()]).status_code == 401
    sem = cliente.post(URL_POSICOES, json={"aparelho": "aparelho-1", "fuso": -180, "pontos": []})
    assert sem.status_code == 401
    velha = _chave(cliente)
    nova = _chave(cliente)                                                 # o mesmo par pede de novo: a velha cai
    assert _posicoes(cliente, velha, [_ponto()]).status_code == 401
    assert _posicoes(cliente, nova, [_ponto()]).status_code == 200
    assert _revogar(cliente, nova).status_code == 204
    r = _posicoes(cliente, nova, [_ponto()])
    assert r.status_code == 401 and "erro" in r.get_json()


def test_chave_de_outro_aparelho_e_401(cliente, banco, ms):
    chave = _chave(cliente, aparelho="aparelho-1")
    assert _posicoes(cliente, chave, [_ponto()], aparelho="aparelho-2").status_code == 401
    assert _posicoes(cliente, chave, [_ponto()], aparelho="aparelho-1").status_code == 200


def test_tecnico_que_saiu_do_piloto_recebe_coleta_false(app, cliente, banco, ms, relogio):
    chave = _chave(cliente)
    assert _posicoes(cliente, chave, [_ponto(1)]).get_json() == {"aceitos": 1, "coleta": True}
    # o administrador tira o técnico do piloto (a decisão nova, mais recente, no livro)
    _aba(banco, LIVRO_PILOTO, ABA_PILOTO, PILOTO + [_decisao(TECNICO, "não", "2026-11-08T15:00:00Z")])
    relogio.andar(seconds=30)                                              # a cópia do piloto vale 1 min
    assert _posicoes(cliente, chave, []).get_json() == {"aceitos": 0, "coleta": True}
    relogio.andar(seconds=31)
    r = _posicoes(cliente, chave, [_ponto(0)])
    assert r.status_code == 200 and r.get_json() == {"aceitos": 0, "coleta": False}
    assert len(S.do_app(app).diario.do_dia(date(2026, 11, 8))) == 1        # o ponto de quem saiu não entra
    # e quem não é mais técnico de campo ativo (desligado no cadastro) também para, na cópia de 5 min
    _aba(banco, LIVRO_PILOTO, ABA_PILOTO, PILOTO)
    relogio.andar(seconds=61)
    assert _posicoes(cliente, chave, [_ponto(0)]).get_json()["coleta"] is True
    _aba(banco, "cadastro_nexus", "pessoas", _pessoas(desligar={TECNICO}))
    visao.limpar()
    relogio.andar(minutes=5)
    assert _posicoes(cliente, chave, [_ponto(0)]).get_json() == {"aceitos": 0, "coleta": False}


def test_lote_grande_ou_corpo_acima_de_64_kb_e_413(cliente, banco, ms):
    chave = _chave(cliente)
    r = _posicoes(cliente, chave, [_ponto(i) for i in range(MAX_PONTOS)])
    assert r.status_code == 200 and r.get_json() == {"aceitos": MAX_PONTOS, "coleta": True}
    assert _posicoes(cliente, chave, [_ponto(i) for i in range(MAX_PONTOS + 1)]).status_code == 413
    lixo = "x" * (64 * 1024)
    assert _posicoes(cliente, chave, [], lixo=lixo).status_code == 413
    r = cliente.post(URL_APARELHO, json={"aparelho": "aparelho-1", "app": "NexusField/1.2.0", "lixo": lixo},
                     headers={"Authorization": "Bearer token:" + EMAIL[TECNICO], "Origin": ORIGEM_APP})
    assert r.status_code == 413 and r.headers["Access-Control-Allow-Origin"] == ORIGEM_APP
    r = cliente.post(URL_REVOGAR, json={"aparelho": "aparelho-1", "lixo": lixo},
                     headers={"Authorization": f"Bearer {chave}"})
    assert r.status_code == 413
    assert _posicoes(cliente, chave, [_ponto()]).status_code == 200        # a chave segue valendo


@pytest.mark.parametrize("corpo", ["não é JSON", "[]", "[" * 30000, {"fuso": -180, "pontos": []},
                                   {"aparelho": 7, "fuso": -180, "pontos": []},
                                   {"aparelho": "aparelho-1", "fuso": -180, "pontos": {"t": 1}},
                                   {"aparelho": "aparelho-1", "pontos": [_ponto()]},              # sem o fuso
                                   {"aparelho": "aparelho-1", "fuso": "Brasília", "pontos": [_ponto()]},
                                   {"aparelho": "aparelho-1", "fuso": 15 * 60, "pontos": [_ponto()]}])
def test_corpo_ruim_nas_posicoes_e_400(cliente, banco, ms, corpo):
    chave = _chave(cliente)
    h = {"Authorization": f"Bearer {chave}"}
    if isinstance(corpo, str):
        r = cliente.post(URL_POSICOES, data=corpo, content_type="application/json", headers=h)
    else:
        r = cliente.post(URL_POSICOES, json=corpo, headers=h)
    assert r.status_code == 400 and "erro" in r.get_json()


def test_permissao_sem_fica_no_estado(app, cliente, banco, ms, relogio):
    chave = _chave(cliente)
    r = _posicoes(cliente, chave, [], permissao="sem")
    assert r.status_code == 200 and r.get_json() == {"aceitos": 0, "coleta": True}
    srv = S.do_app(app)
    assert srv.estado_de(TECNICO) == {"ultimo": None, "permissao": "sem", "desde": AGORA}
    relogio.andar(minutes=30)                                              # a casca repete o aviso a cada 30 min
    _posicoes(cliente, chave, [], permissao="sem")
    assert srv.estado_de(TECNICO)["desde"] == AGORA                        # "sem permissão desde" a 1ª vez
    relogio.andar(minutes=10)
    _posicoes(cliente, chave, [_ponto(0)])                                 # a permissão voltou: chegam pontos
    e = srv.estado_de(TECNICO)
    assert e["permissao"] == "ok" and e["desde"] == AGORA + timedelta(minutes=40) and e["ultimo"] is not None
    # quem nunca mandou nada
    assert srv.estado_de(FORA_DO_PILOTO) == {"ultimo": None, "permissao": "ok", "desde": None}


def test_o_ultimo_ponto_com_mais_de_7_dias_nao_e_usado(app, cliente, banco, ms):
    chave = _chave(cliente)
    _posicoes(cliente, chave, [_ponto(0)])
    srv = S.do_app(app)
    assert srv.estado_de(TECNICO, AGORA + timedelta(days=6))["ultimo"] is not None
    assert srv.estado_de(TECNICO, AGORA + timedelta(days=7, minutes=1))["ultimo"] is None


# ── a revogação ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_revogar_e_204_sempre(app, cliente, banco, ms):
    chave = _chave(cliente)
    # chave desconhecida, sem chave, chave de outro aparelho: 204, e nada muda (sem oráculo)
    for r in (_revogar(cliente, "x" * 43), _revogar(cliente, None), _revogar(cliente, chave, "aparelho-2")):
        assert r.status_code == 204 and r.get_data() == b""
    assert _posicoes(cliente, chave, [_ponto()]).status_code == 200
    srv = S.do_app(app)
    srv.chaveiro.eventos_novos()
    assert _revogar(cliente, chave).status_code == 204
    assert _posicoes(cliente, chave, [_ponto()]).status_code == 401
    assert _revogar(cliente, chave).status_code == 204                     # de novo: 204
    ev = [dict(zip(CAB_APARELHOS, x)) for x in srv.chaveiro.eventos_novos()]
    assert [(e["evento"], e["pessoa_id"], e["aparelho"]) for e in ev] == [("revogada", TECNICO, "aparelho-1")]


# ── as rotas públicas ────────────────────────────────────────────────────────────────────────────────────────────────
def test_as_rotas_publicas_nao_pedem_login_e_as_outras_sim(app, cliente, banco):
    nomes = {"torre_campo.equipe_aparelho": URL_APARELHO, "torre_campo.equipe_posicoes": URL_POSICOES,
             "torre_campo.equipe_revogar": URL_REVOGAR}
    assert set(nomes) <= ROTAS_PUBLICAS
    regras = {r.endpoint: r for r in app.url_map.iter_rules() if r.endpoint in nomes}
    assert {e: r.rule for e, r in regras.items()} == nomes
    assert all("GET" not in r.methods and "POST" in r.methods for r in regras.values())
    # sem sessão: responde a rota (sem token, 401; a revogação, 204), nunca o Entrar
    r = cliente.post(URL_APARELHO, json={"aparelho": "aparelho-1", "app": "NexusField/1.2.0"})
    assert r.status_code == 401
    r = cliente.post(URL_POSICOES, json={"aparelho": "aparelho-1", "fuso": -180, "pontos": []})
    assert r.status_code == 401
    assert cliente.post(URL_REVOGAR, json={"aparelho": "aparelho-1"}).status_code == 204
    # as outras telas do Campo seguem atrás do login
    r = cliente.get("/t/campo/atencao")
    assert r.status_code == 302 and "/entrar" in r.headers["Location"]
    r = cliente.post("/t/campo/responsaveis/usina/1/observacao")
    assert r.status_code == 302 and "/entrar" in r.headers["Location"]


# ── o reinício e o banco fora ────────────────────────────────────────────────────────────────────────────────────────
def test_o_reinicio_le_as_chaves_do_banco_e_o_diario_do_disco(app, cliente, banco, ms):
    chave = _chave(cliente)
    assert _posicoes(cliente, chave, [_ponto(20), _ponto(3)]).get_json()["aceitos"] == 2
    _reiniciar(app, banco)
    srv = S.do_app(app)
    assert srv.estado_de(TECNICO)["ultimo"]["instante"] == "2026-11-08T14:57:00Z"     # do diário, antes de chegar ponto
    assert _posicoes(cliente, chave, [_ponto(1)]).get_json() == {"aceitos": 1, "coleta": True}
    assert len(srv.diario.do_dia(date(2026, 11, 8))) == 3


def test_banco_fora_no_reinicio_nao_e_chave_invalida(app, cliente, banco, ms, relogio):
    """Sem ler o livro das chaves, o Nexus não sabe se a chave vale: 503 (a casca guarda a fila e a chave), nunca o 401
    que a faria apagar a chave e parar até a próxima abertura. O livro é relido no máximo uma vez por minuto."""
    chave = _chave(cliente)
    _reiniciar(app, banco)
    app.extensions["nexus_dados_sessao"] = SessaoFora()
    assert _posicoes(cliente, chave, [_ponto()]).status_code == 503
    assert _registrar(cliente).status_code == 503                         # nem chave nova antes de ler as velhas
    app.extensions["nexus_dados_sessao"] = banco
    assert _posicoes(cliente, chave, [_ponto()]).status_code == 503        # o teto: só tenta de novo depois de 1 min
    relogio.andar(seconds=61)
    assert _posicoes(cliente, chave, [_ponto()]).get_json() == {"aceitos": 1, "coleta": True}


def test_a_listagem_que_omite_o_livro_das_chaves_nao_e_livro_vazio(app, cliente, banco, ms, relogio):
    """A listagem do banco omite um livro por um instante (achado 6 da revisão de 05/11/2026): lida como livro vazio,
    toda chave daria 401. O `sheet_count` do /api/workbooks pega a falta."""
    chave = _chave(cliente)
    _reiniciar(app, banco)
    banco.omitir.add(LIVRO_APARELHOS)
    assert _posicoes(cliente, chave, [_ponto()]).status_code == 503
    banco.omitir.clear()
    relogio.andar(seconds=61)
    assert _posicoes(cliente, chave, [_ponto()]).status_code == 200


def test_piloto_que_nao_se_le_e_ninguem_sem_copia_e_a_copia_boa_com_ela(app, cliente, banco, ms, relogio):
    # sem nenhuma leitura boa do piloto: ninguém é coletado (o registro diz coleta false, nunca 500)
    banco.omitir.add(LIVRO_PILOTO)
    r = _registrar(cliente)
    assert r.status_code == 200 and r.get_json() == {"coleta": False}
    banco.omitir.clear()
    relogio.andar(seconds=61)
    chave = _chave(cliente)
    # com a cópia boa, a falha seguinte não tira ninguém do piloto (o banco fora não é "fora do piloto")
    banco.omitir.add(LIVRO_PILOTO)
    relogio.andar(seconds=61)
    assert _posicoes(cliente, chave, [_ponto(0)]).get_json() == {"aceitos": 1, "coleta": True}


def test_o_cadastro_que_volta_sem_tecnico_nenhum_e_falha_e_nao_a_equipe_que_sumiu(app, cliente, banco, ms, relogio):
    chave = _chave(cliente)
    banco.omitir.add("cadastro_nexus")                 # a listagem omite o cadastro: todas as abas dele leem vazio
    visao.limpar()
    relogio.andar(minutes=5, seconds=1)
    assert _posicoes(cliente, chave, [_ponto(0)]).get_json() == {"aceitos": 1, "coleta": True}


def test_o_log_nao_leva_token_chave_email_nem_coordenada(app, cliente, banco, ms, relogio, caplog):
    caplog.set_level(logging.DEBUG)
    chave = _chave(cliente)
    _posicoes(cliente, chave, [_ponto(1)])
    _registrar(cliente, token="token-forjado")
    ms.fora = True
    _registrar(cliente)
    _reiniciar(app, banco)
    app.extensions["nexus_dados_sessao"] = SessaoFora()
    _posicoes(cliente, chave, [_ponto(0)])
    texto = caplog.text
    assert texto                                                           # as falhas foram ao log...
    for segredo in (chave, "token-forjado", EMAIL[TECNICO], str(LAT), str(LON)):
        assert segredo not in texto, segredo                               # ...sem nada disto
