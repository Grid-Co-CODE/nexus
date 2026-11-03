"""Os catálogos pequenos do OS Creator num lugar só (31/10/2026, etapa 4 do canto central; tarefa 4.1).

Levi, 30/10/2026: "a ideia é não ter um carregamento novo por atividade e sim um ecossistema onde as coisas se aproveitam e
não precisamos ficar fazendo novas requisições sempre!". Até aqui o pessoal era lido por 7 caminhos (cada tela com a sua
cópia, a pessoa logada achada por e-mail a cada processo), as etiquetas por 4, os tipos e as classificações por 3 (duas cópias
que nunca venciam), as falhas do COS numa cópia que nunca vencia, e os planos da Performance relidos inversor por inversor a
cada usina escolhida. E só na memória: cada push na `main` reinicia o serviço.

O que estes testes seguram (o Fracttal é de mentira, no nível do `api._rpc_call`, contando cada pedido por método; a rede fica
proibida; nomes e e-mails são inventados):
- `test_um_pedido_para_todas_as_telas`, por catálogo: todos os caminhos que usam o catálogo, de três pessoas, pedem UMA leitura;
- `test_reinicio_sem_pedido`: o reinício sobe pela cópia em disco e não pede nada, nem com a cópia vencida (menos a 1ª tela
  de quem não está no pessoal, que relê o pessoal uma vez, como a conta nova);
- `test_disco_corrompido`: a cópia ilegível é ignorada, o motivo vai ao estado e o catálogo é lido de novo, uma vez;
- `test_performance_segunda_vez_sem_pedido`: a 2ª escolha da mesma usina na Performance não pede nada;
- `test_prazo_vencido_renova_por_tras`: o vencido volta na hora e é renovado por trás, uma vez para todos, com a sessão de quem
  o achou vencido;
- e o resto do contrato: o erro e a lista vazia não ficam guardados, as pessoas pelo REST da empresa (com os campos que a tela
  usa, ou o RPC), o laço só no servidor e no seu minuto, o e-mail fora do disco e o Raio-X com uma linha por catálogo.

A rodada 1 da revisão (31/10/2026) segura o que o catálogo NÃO faz: a leitura das falhas pela metade não troca a completa; a
criação da Engenharia confere a pessoa e a etiqueta ao vivo (a regra de 19/10); o "Criado por" do Histórico segue por pessoa;
o REST que dá outra conta ou outro e-mail às mesmas pessoas não entra; a renovação por trás tem estado de sessão próprio, ritmo
(1 por segundo, a cota, a sessão que caiu); a conta nova é achada mesmo com o REST valendo; o nome que é um e-mail não vai ao
disco; o status vazio não guarda a lista local; e a cópia dos planos em disco não volta atrás."""
import base64
import json
import os
import sys
import threading
import time

import pytest

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
import ativos_central  # noqa: E402
import temas_store as ts  # noqa: E402
from os_web import criar_app, rotas, sessao  # noqa: E402
from os_web import rotas_cos, rotas_solic  # noqa: E402
from os_web import solic_eng_web as reg  # noqa: E402

USINA = "Cliente X - Usina Teste 1 - UF"
ATIVOS = [{"id": 600 + i, "code": "TST-INV%d" % i, "description": "Inversor 1.%d" % i, "tipo": "Inversor", "tipo_code": "INVR",
           "usina": USINA, "cliente": "Cliente X", "id_group_task": 77, "label": "TST-INV%d — Inversor 1.%d" % (i, i)}
          for i in range(1, 4)]
FRASE = "recomposicao de string"

# o personnel.personnel_list do RPC (o campo `id` é o id_personnel); pessoas e e-mails inventados
PESSOAL = [
    {"id": 501, "code": "A1", "full_name": "Ana Teste Silva", "active": True, "id_account": 11,
     "account_email": "ana@exemplo.invalid"},
    {"id": 502, "code": "B2", "full_name": "Bruno Exemplo", "active": True, "id_account": 12,
     "account_email": "bruno@exemplo.invalid"},
    {"id": 503, "code": "C3", "full_name": "Carla Desligada", "active": False, "id_account": 13,
     "account_email": "carla@exemplo.invalid"},
]
EMAILS = ("ana@exemplo.invalid", "bruno@exemplo.invalid", "dora@exemplo.invalid")    # a 3ª não está no pessoal

M_PESSOAS = (api.RPC_PERSONNEL,)
M_ETIQUETAS = (api.RPC_LABELS_LIST,)
M_TIPOS = (api.RPC_TIPOS_MAIN, api.RPC_TIPOS_C1, api.RPC_TIPOS_C2)
M_FALHAS = (api.RPC_FALHA_TIPOS, api.RPC_FALHA_CAUSAS, api.RPC_FALHA_DETEC)
M_STATUS = (api.RPC_REQ_STATUS_LIST,)
M_TIPOS_SOLIC = (api.RPC_REQ_TYPES, api.RPC_REQ_TYPES_1, api.RPC_REQ_TYPES_2)
M_MOTIVOS = (api.RPC_WO_STATUS_CUSTOM,)
M_PLANOS = (api.RPC_TASK_EVENTS, api.RPC_TASK_DETAILS)


def _jwt(email: str) -> str:
    corpo = base64.urlsafe_b64encode(json.dumps({"email": email, "exp": 9999999999}).encode()).decode().rstrip("=")
    return "aaa.%s.sig" % corpo                                          # de mentira


class Fracttal:
    """O Fracttal de mentira no nível do `api._rpc_call`: responde cada catálogo e conta cada pedido (método e parâmetros).
    O que o teste não previu não vai a lugar nenhum."""

    def __init__(self):
        self.pedidos, self.trava = [], threading.Lock()
        self.pessoal = [dict(p) for p in PESSOAL]
        self.etiquetas = [{"id": 7, "description": "PERFORMANCE"}, {"id": 8, "description": "CHAMADOS"},
                          {"id": 900, "description": "ENGENHARIA"}]
        self.tipos = {api.RPC_TIPOS_MAIN: [{"id": 1, "description": "Corretiva"}, {"id": 2, "description": "Preventiva"}],
                      api.RPC_TIPOS_C1: [{"id": 11, "description": "Programada"}],
                      api.RPC_TIPOS_C2: [{"id": 22, "description": "Elétrica"}]}
        self.falhas = {api.RPC_FALHA_TIPOS: [{"id": 31, "description": "Falha elétrica"}],
                       api.RPC_FALHA_CAUSAS: [{"id": 32, "description": "Sobrecarga"}],
                       api.RPC_FALHA_DETEC: [{"id": 33, "description": "Inspeção"}]}
        self.status = [{"id": i} for i in (1, 2, 4, 5, 7, 10, 12)]
        self.tipos_solic = {api.RPC_REQ_TYPES: [{"id": 41, "description": "Grupo Teste"}],
                            api.RPC_REQ_TYPES_1: [{"id": 42, "description": "Classe Teste"}],
                            api.RPC_REQ_TYPES_2: [{"id": 43, "description": "Subclasse Teste"}]}
        self.motivos = [{"id": 51, "description": "Duplicada"}]
        self.erro = None
        # o "Criado por" do Histórico (P2) lê o pessoal POR PESSOA, com a sessão dela, e não é caminho do catálogo: os pedidos
        # dele contam aqui, à parte (`fr` marca quem está dentro dele)
        self.pedidos_p2, self.p2 = [], threading.local()
        self.sem_permissao = set()               # os e-mails cuja sessão não tem a permissão de pessoal: o RPC dá a lista vazia

    def rpc(self, metodo, params, timeout=45):
        with self.trava:
            (self.pedidos_p2 if getattr(self.p2, "dentro", False) else self.pedidos).append((metodo, dict(params or {})))
        if self.erro is not None:
            raise self.erro
        if metodo == api.RPC_PERSONNEL:
            if sessao.email_do_jwt(sessao.jwt_atual()) in self.sem_permissao:
                return {"data": []}
            ini = int(params.get("start") or 0)
            return {"data": [dict(p) for p in self.pessoal[ini:ini + 100]]}
        if metodo == api.RPC_LABELS_LIST:
            return {"data": [dict(e) for e in self.etiquetas]}
        if metodo in self.tipos:
            return {"data": [dict(x) for x in self.tipos[metodo]]}
        if metodo in self.falhas:
            return {"data": [dict(x) for x in self.falhas[metodo]]}
        if metodo == api.RPC_REQ_STATUS_LIST:
            return {"data": [dict(x) for x in self.status]}
        if metodo in self.tipos_solic:
            return {"data": [dict(x) for x in self.tipos_solic[metodo]]}
        if metodo == api.RPC_WO_STATUS_CUSTOM:
            return {"data": [dict(x) for x in self.motivos]}
        if metodo == api.RPC_TASK_EVENTS:
            i = int(params.get("id_item")) - 600
            return {"data": [{"id_task": 700 + i, "task_description": "[Grid Co.] - Recomposição de String"},
                             {"id_task": 800 + i, "task_description": "[Grid Co.] - MPS - Inversor"}]}
        if metodo == api.RPC_TASK_DETAILS:
            return {"data": [{"description": "[Grid Co.] - Recomposição de String", "tasks_types_main_description": "Corretiva",
                              "duration": 1800, "task_form_items": [{"id_task_form_item_type": 1, "description": "Medir"}]}]}
        raise AssertionError("um pedido ao Fracttal que o teste não previu: %s" % metodo)

    def n(self, *metodos) -> int:
        with self.trava:
            return sum(1 for m, _p in self.pedidos if m in metodos)


def _catalogos():
    import catalogos
    return catalogos


def _leitor():
    """O laço das pessoas pelo REST da empresa (`catalogos_leitor.py`, o par do `catalogos.py`; só o servidor liga)."""
    import catalogos_leitor
    return catalogos_leitor


@pytest.fixture
def fr(monkeypatch):
    import requests

    def sem_rede(*a, **k):                    # a cota do Fracttal é da empresa: aqui nada sai da máquina
        raise AssertionError("o teste tentou ir à rede")
    monkeypatch.setattr(requests.Session, "request", sem_rede)
    f = Fracttal()
    monkeypatch.setattr(api, "_rpc_call", f.rpc)
    monkeypatch.setattr(api, "list_minhas_os", lambda *a, **k: [])
    monkeypatch.setattr(api, "list_minhas_os_pagina", lambda *a, **k: {"total": 0, "linhas": [], "tem_mais": False})
    monkeypatch.setattr(api, "list_minhas_solicitacoes", lambda *a, **k: [])
    monkeypatch.setattr(rotas, "_em_segundo_plano", lambda fn: None)     # a renovação do Histórico: fora daqui
    monkeypatch.setattr(ts, "garantir", lambda: None)                    # os temas do banco: nenhum teste vai
    monkeypatch.setenv(reg.ENV_RESPONSAVEIS, "Ana Teste")
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    ativos_central.reiniciar()
    ativos_central.trocar([dict(a) for a in ATIVOS], "rpc")
    try:                                         # o dono dos catálogos (a etapa 4): a renovação por trás, na mão do teste
        ct = _catalogos()
        f.por_tras, f.dormiu = [], []
        monkeypatch.setattr(ct, "_em_segundo_plano", lambda fn: f.por_tras.append(fn))
        monkeypatch.setattr(ct, "_dormir", lambda s: f.dormiu.append(s))  # as pausas do trabalho por trás: anotadas
    except ImportError:
        pass
    contas = api.get_pessoas_contas

    def contas_da_pessoa():                      # o "Criado por" (P2): os pedidos dele vão ao `pedidos_p2`
        f.p2.dentro = True
        try:
            return contas()
        finally:
            f.p2.dentro = False
    monkeypatch.setattr(api, "get_pessoas_contas", contas_da_pessoa)
    yield f
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    ativos_central.reiniciar()


_APP: dict = {}


def _cliente(email: str):
    """O navegador de uma pessoa no MESMO app (como no servidor: um processo, várias pessoas)."""
    app = _APP.get("app")
    if app is None:
        app = _APP["app"] = criar_app(segredo="teste", testing=True)
    c = app.test_client()
    c.jwt, c.email = _jwt(email), email
    with c.session_transaction() as s:
        s["jwt"] = c.jwt
        s["conta"] = {"nome": "Pessoa Teste", "email": email, "perfil": "ADMINISTRATOR"}
    return c


@pytest.fixture(autouse=True)
def _um_app():
    _APP.clear()
    yield
    _APP.clear()


def _no_pedido(c, fn):
    """Uma função do api ou de uma rota rodando dentro de um pedido da pessoa (a sessão dela no contexto)."""
    with c.application.test_request_context(), sessao.contexto(c.jwt, c.email):
        return fn()


def _ok(r, *codigos):
    assert r.status_code in (codigos or (200,)), (r.status_code, r.get_data(as_text=True)[:300])
    return r


# cada catálogo: os métodos do RPC dele, os pedidos de UMA leitura e os caminhos que o usam
def _caminhos_pessoas(c):
    _ok(c.get("/os/api/responsaveis"))                                   # 1. rotas.responsaveis_fracttal
    _ok(c.get("/os/historico?modo=criadas"))                             # 2. o Histórico das criadas por mim
    _ok(c.get("/os/solicitacao"))                                        # 3. o técnico sugerido (rotas_solic._pessoas)
    _no_pedido(c, api._current_user_info)                                # 4. "criadas por mim" e "atribuídas a mim"
    _no_pedido(c, api._personnel_nome_por_id)                            # 5. o nome do responsável no card
    _ok(c.get("/os/api/cos/listas?so=responsaveis"))                     # 6. o Requerido por do COS
    _ok(c.get("/os/clonar"))                                             # (o mesmo do 1, na Clonagem)
    # o "Criado por" do 2 lê por pessoa (os pedidos dele contam à parte, `pedidos_p2`), e a criação da Engenharia (o 7 de
    # antes) confere ao vivo: nenhum dos dois é do catálogo (`test_o_criado_por_e_de_cada_pessoa`, `test_a_criacao_da_...`)


def _caminhos_etiquetas(c):
    _ok(c.get("/os/api/tradicional/etiquetas"))                          # rotas.etiquetas_fracttal (Criar OS)
    _ok(c.get("/os/historico?modo=cos"))                                 # o filtro de etiqueta do Histórico
    _ok(c.get("/os/solicitacao/fila"))                                   # rotas_solic._etiquetas (a Fila)
    _no_pedido(c, lambda: api._label_id("CHAMADOS"))                     # o id pelo nome (Garantias, Performance)
    _no_pedido(c, lambda: api.label_id_por_nome("performance"))          # o id por trecho (a criação da Performance)
    _ok(c.get("/os/api/os/123/etiquetas?atuais=7"))                      # o diálogo de etiquetas do card


def _caminhos_tipos(c):
    _ok(c.get("/os/api/cos/listas?so=classif"))                          # o COS
    _ok(c.get("/os/api/tradicional/tipos"))                              # o Criar OS
    _ok(c.get("/os/solicitacao/fila"))                                   # a Fila (rotas_solic._tipos)
    _no_pedido(c, lambda: api._classif_ids("Programada", "Elétrica"))    # a Classificação pelo nome (análise, Engenharia)
    _no_pedido(c, lambda: api.tipo_main_ao_vivo("Corretiva"))            # o tipo pelo nome (a Zeladoria da Fila)
    _no_pedido(c, rotas_cos._classif_para_criar)                         # a criação do COS


def _caminhos_falhas(c):
    _ok(c.get("/os/api/cos/listas?so=falhas"))
    _no_pedido(c, rotas_cos._falhas_para_criar)


def _caminhos_status(c):
    _ok(c.get("/os/solicitacao/fila"))
    _no_pedido(c, rotas_solic._status_cat)


def _caminhos_tipos_solic(c):
    _ok(c.get("/os/solicitacao"))


def _caminhos_motivos(c):
    _ok(c.get("/os/api/os/123/cancel-motivos"))


CATALOGOS = {
    "pessoas": (M_PESSOAS, 1, _caminhos_pessoas),
    "etiquetas": (M_ETIQUETAS, 1, _caminhos_etiquetas),
    "tipos": (M_TIPOS, 3, _caminhos_tipos),
    "falhas": (M_FALHAS, 3, _caminhos_falhas),
    "status": (M_STATUS, 1, _caminhos_status),
    "tipos_solicitacao": (M_TIPOS_SOLIC, 3, _caminhos_tipos_solic),
    "motivos": (M_MOTIVOS, 1, _caminhos_motivos),
}


def _tudo(c):
    for _m, _n, caminhos in CATALOGOS.values():
        caminhos(c)


# ── um pedido para todas as telas ───────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("nome", sorted(CATALOGOS))
def test_um_pedido_para_todas_as_telas(fr, nome):
    metodos, uma_leitura, caminhos = CATALOGOS[nome]
    for email in EMAILS:                                                 # três pessoas, cada uma por todos os caminhos
        caminhos(_cliente(email))
    assert fr.n(*metodos) == uma_leitura, (nome, [m for m, _p in fr.pedidos if m in metodos])


def test_as_telas_veem_o_mesmo_de_antes(fr):
    """A mesma forma de hoje: o pessoal ativo por nome, a conta e o "eu" do Histórico, a pessoa logada, o nome pelo id, as
    etiquetas, os tipos, as falhas e o status."""
    c = _cliente("ana@exemplo.invalid")
    pessoas = c.get("/os/api/responsaveis").get_json()["pessoas"]
    assert pessoas == [{"code": "A1", "name": "Ana Teste Silva", "id_personnel": 501},
                       {"code": "B2", "name": "Bruno Exemplo", "id_personnel": 502}]            # sem a desligada
    assert _no_pedido(c, api._current_user_info) == (501, 11, "Ana Teste Silva")
    assert _no_pedido(c, api.get_pessoas_contas) == {
        "pessoas": [{"id_account": 11, "nome": "Ana Teste Silva"}, {"id_account": 12, "nome": "Bruno Exemplo"},
                    {"id_account": 13, "nome": "Carla Desligada"}], "eu": 11}                   # a desligada criou OS
    assert _no_pedido(c, api._personnel_nome_por_id) == {501: "Ana Teste Silva", 502: "Bruno Exemplo"}
    assert _no_pedido(_cliente("dora@exemplo.invalid"), api._current_user_info) == (None, None, "")
    assert _no_pedido(c, lambda: api._label_id("chamados")) == 8
    assert _no_pedido(c, lambda: api._classif_ids("Programada", "Elétrica")) == {
        "id_task_type": 11, "tasks_types_description": "Programada", "id_task_type_2": 22,
        "tasks_types_2_description": "Elétrica"}
    j = c.get("/os/api/cos/listas").get_json()
    assert j["classif"]["tipos"][0] == {"id": 1, "description": "Corretiva"} and j["falhas"]["tipos"][0]["id"] == 31
    assert [p["name"] for p in j["responsaveis"]] == ["Ana Teste Silva", "Bruno Exemplo"] and j["erros"] == {}
    assert [t[0] for t in _no_pedido(c, rotas_solic._status_cat)] == [2, 4, 10, 12, 5]


# ── a Performance ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _escolher_usina(c):
    j = _ok(c.get("/os/api/performance/alvos", query_string={"usina": USINA, "frase": FRASE})).get_json()
    a = j["ativos"][0]
    r = _ok(c.get("/os/api/performance/plano", query_string={"id_task": a["plano_id_task"], "id_item": a["plano_id_item"]}))
    return j, r.get_json()


def test_performance_segunda_vez_sem_pedido(fr):
    a, b = _cliente("ana@exemplo.invalid"), _cliente("bruno@exemplo.invalid")
    j1, p1 = _escolher_usina(a)
    assert [x["plano_id_task"] for x in j1["ativos"]] == [701, 702, 703]
    assert fr.n(api.RPC_TASK_EVENTS) == 3 and fr.n(api.RPC_TASK_DETAILS) == 1          # um por inversor, e o plano
    antes = len(fr.pedidos)
    j2, p2 = _escolher_usina(a)                                          # a 2ª escolha da mesma usina
    j3, p3 = _escolher_usina(b)                                          # e a de outra pessoa
    assert len(fr.pedidos) == antes, fr.pedidos[antes:]
    assert j1 == j2 == j3 and p1 == p2 == p3 and "Tipo: Corretiva" in p1["resumo"]


def test_performance_vencida_volta_na_hora_e_renova_por_tras(fr, monkeypatch):
    ct = _catalogos()
    agora = {"t": time.time()}
    monkeypatch.setattr(ct, "_relogio", lambda: agora["t"])
    a = _cliente("ana@exemplo.invalid")
    j1, p1 = _escolher_usina(a)
    agora["t"] += ct.PRAZO_S["planos"] + 1                               # o dia seguinte
    fr.pedidos.clear()
    assert _escolher_usina(a) == (j1, p1)                                # os de ontem, na hora
    _escolher_usina(_cliente("bruno@exemplo.invalid"))                   # e a de outra pessoa, com a renovação em curso
    assert fr.pedidos == [] and len(fr.por_tras) == 2                    # UMA renovação dos planos (os 3 inversores) e uma do plano
    for fn in fr.por_tras:
        fn()
    assert fr.n(api.RPC_TASK_EVENTS) == 3 and fr.n(api.RPC_TASK_DETAILS) == 1
    fr.pedidos.clear()
    fr.por_tras.clear()
    assert _escolher_usina(a) == (j1, p1) and fr.pedidos == [] and fr.por_tras == []


# ── o disco ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
CHAVE = b"chave-de-teste-dos-catalogos"


def test_a_ponte_liga_a_pasta_e_a_chave(app, tmp_path, monkeypatch):
    """A ponte diz onde mora a cópia (`<pasta de dados do clone>/oscreator/catalogos/`) e a chave do e-mail (derivada da do
    Nexus, mas não a do cookie do clone), e aquece por trás; nos testes, nada (a pasta seria a do usuário da máquina)."""
    ct = _catalogos()
    monkeypatch.setattr(api, "_data_dir", lambda: str(tmp_path))
    aqueceu = []
    monkeypatch.setattr(ct, "aquecer", lambda esperar=False: aqueceu.append(1))
    ponte.ligar_catalogos(app)
    assert ct.arquivo("pessoas") is None and aqueceu == []
    app.config["TESTING"] = False
    try:
        ponte.ligar_catalogos(app)
    finally:
        app.config["TESTING"] = True
    assert ct.arquivo("pessoas") == os.path.join(str(tmp_path), "oscreator", "catalogos", "pessoas.json") and aqueceu == [1]
    assert ct._CHAVE_EMAIL["v"] == ponte.chave_dos_catalogos(app) and ct._CHAVE_EMAIL["v"] != ponte._segredo(app).encode()


def test_reinicio_sem_pedido(fr, tmp_path):
    ct = _catalogos()
    pasta = str(tmp_path / "catalogos")
    ct.reiniciar(pasta=pasta, chave=CHAVE)
    c = _cliente("ana@exemplo.invalid")
    _tudo(c)
    _escolher_usina(c)
    assert fr.n(*M_PESSOAS) == 1 and fr.n(*M_PLANOS) == 4
    nomes = sorted(os.listdir(pasta))
    for nome in CATALOGOS:
        assert "%s.json" % nome in nomes, nomes
    assert "planos.json" in nomes and "planos_detalhe.json" in nomes
    # o processo sobe de novo (cada push na `main`), com a cópia já vencida: o boot só lê o disco, e nada vai ao Fracttal
    fr.pedidos.clear()
    ct.reiniciar(pasta=pasta, chave=CHAVE)
    _APP.clear()
    monkey_relogio = time.time() + 30 * 3600
    ct._relogio = lambda: monkey_relogio
    try:
        ct.aquecer(esperar=True)                                         # o aquecimento do boot: o disco, por trás
        for email in EMAILS[:2]:                                         # as duas pessoas que estão no pessoal
            c = _cliente(email)
            _tudo(c)
            _escolher_usina(c)
        assert fr.pedidos == []                                          # nem um pedido: as telas leem a cópia
        # menos para quem NÃO está no pessoal (a 3ª): a 1ª tela dela depois de cada reinício relê o pessoal, como a conta
        # nova (`catalogos.da_pessoa`). Uma leitura: 1 pedido aqui, 2 com as ~150 pessoas de verdade (duas páginas de 100)
        _no_pedido(_cliente(EMAILS[2]), api._current_user_info)
        assert [m for m, _p in fr.pedidos] == [api.RPC_PERSONNEL]
        # vencida, ela é renovada por trás (a regra do prazo), e não no boot
        assert fr.por_tras, "o vencido não pediu a renovação por trás"
        assert _no_pedido(_cliente("ana@exemplo.invalid"), api._current_user_info) == (501, 11, "Ana Teste Silva")
        e = {x["nome"]: x for x in ct.estado()["assuntos"]}
        assert e["pessoas"]["disco"]["lido"] and e["pessoas"]["fonte"] == "rpc" and e["pessoas"]["n"] == 3
    finally:
        ct._relogio = time.time


def test_o_email_nao_vai_ao_disco(fr, tmp_path):
    """O pessoal em disco leva quem é cada pessoa (o id, o código, o nome), mas não o e-mail: a pessoa logada é achada pelo
    HMAC do e-mail (com a chave do Nexus). A cópia feita com outra chave (a NEXUS_SECRET_KEY trocou) não acharia ninguém:
    ela é ignorada, com o motivo no estado, e o pessoal é relido uma vez."""
    ct = _catalogos()
    pasta = str(tmp_path / "catalogos")
    ct.reiniciar(pasta=pasta, chave=CHAVE)
    c = _cliente("ana@exemplo.invalid")
    assert _no_pedido(c, api._current_user_info) == (501, 11, "Ana Teste Silva")
    texto = open(os.path.join(pasta, "pessoas.json"), encoding="utf-8").read()
    assert "@" not in texto and "exemplo.invalid" not in texto and "Ana Teste Silva" in texto
    ct.reiniciar(pasta=pasta, chave=CHAVE)                               # o reinício com a mesma chave: acha pela cópia
    assert _no_pedido(c, api._current_user_info) == (501, 11, "Ana Teste Silva") and fr.n(*M_PESSOAS) == 1
    ct.reiniciar(pasta=pasta, chave=b"outra-chave")
    e = {x["nome"]: x for x in ct.estado()["assuntos"]}["pessoas"]
    assert e["n"] == 0 and "outra chave" in (e["disco"]["erro"] or "")
    assert _no_pedido(c, api._current_user_info) == (501, 11, "Ana Teste Silva") and fr.n(*M_PESSOAS) == 2


@pytest.mark.parametrize("nome", sorted(CATALOGOS))
def test_disco_corrompido(fr, tmp_path, nome):
    ct = _catalogos()
    pasta = str(tmp_path / "catalogos")
    ct.reiniciar(pasta=pasta, chave=CHAVE)
    metodos, uma_leitura, caminhos = CATALOGOS[nome]
    caminhos(_cliente("ana@exemplo.invalid"))
    arq = os.path.join(pasta, "%s.json" % nome)
    with open(arq, "w", encoding="utf-8") as f:
        f.write('{"formato": 1, "nome": "%s", "valor": [cortad' % nome)          # gravação cortada no meio
    fr.pedidos.clear()
    ct.reiniciar(pasta=pasta, chave=CHAVE)
    _APP.clear()
    e = {x["nome"]: x for x in ct.estado()["assuntos"]}
    assert e[nome]["n"] == 0 and "ler" in (e[nome]["disco"]["erro"] or ""), e[nome]
    for email in EMAILS:
        caminhos(_cliente(email))
    assert fr.n(*metodos) == uma_leitura                                 # lido de novo, uma vez, e regravado
    json.load(open(arq, encoding="utf-8"))
    # a cópia de outro formato também não entra
    with open(arq, "w", encoding="utf-8") as f:
        json.dump({"formato": 999, "nome": nome, "lido_em": time.time(), "fonte": "rpc", "valor": []}, f)
    ct.reiniciar(pasta=pasta, chave=CHAVE)
    e = {x["nome"]: x for x in ct.estado()["assuntos"]}
    assert e[nome]["n"] == 0 and "formato" in (e[nome]["disco"]["erro"] or "")


def test_planos_corrompidos_nao_derrubam_a_performance(fr, tmp_path):
    ct = _catalogos()
    pasta = str(tmp_path / "catalogos")
    ct.reiniciar(pasta=pasta, chave=CHAVE)
    c = _cliente("ana@exemplo.invalid")
    _escolher_usina(c)
    for arq in ("planos.json", "planos_detalhe.json"):
        with open(os.path.join(pasta, arq), "wb") as f:
            f.write(b"\x00\x01 lixo")
    ct.reiniciar(pasta=pasta, chave=CHAVE)
    e = ct.estado()
    assert e["planos"]["n"] == 0 and "ler" in (e["planos"]["disco"]["erro"] or "")
    assert e["detalhes"]["n"] == 0 and "ler" in (e["detalhes"]["disco"]["erro"] or "")
    fr.pedidos.clear()
    j, p = _escolher_usina(c)
    assert len(j["ativos"]) == 3 and fr.n(*M_PLANOS) == 4 and "Tipo: Corretiva" in p["resumo"]
    assert ct.estado()["planos"]["disco"]["erro"] is None                # regravada: o disco voltou


# ── o prazo ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_prazo_vencido_renova_por_tras(fr, monkeypatch):
    ct = _catalogos()
    agora = {"t": time.time()}
    monkeypatch.setattr(ct, "_relogio", lambda: agora["t"])
    a, b = _cliente("ana@exemplo.invalid"), _cliente("bruno@exemplo.invalid")
    assert [p["name"] for p in a.get("/os/api/responsaveis").get_json()["pessoas"]] == ["Ana Teste Silva", "Bruno Exemplo"]
    assert fr.n(*M_PESSOAS) == 1
    fr.pessoal.append({"id": 504, "code": "E5", "full_name": "Eva Nova", "active": True, "id_account": 15,
                       "account_email": "eva@exemplo.invalid"})            # alguém entrou no Fracttal
    agora["t"] += ct.PRAZO_S["pessoas"] - 60
    a.get("/os/api/responsaveis")
    assert fr.por_tras == [] and fr.n(*M_PESSOAS) == 1                   # dentro do prazo: nada
    agora["t"] += 120                                                    # venceu
    for c in (a, b, a):                                                  # três telas de duas pessoas, com o vencido
        nomes = [p["name"] for p in c.get("/os/api/responsaveis").get_json()["pessoas"]]
        assert nomes == ["Ana Teste Silva", "Bruno Exemplo"]             # a cópia de antes, na hora
    assert len(fr.por_tras) == 1 and fr.n(*M_PESSOAS) == 1               # UMA renovação, ainda não rodou
    fr.pedidos.clear()
    fr.por_tras.pop()()                                                  # a renovação roda por trás
    assert fr.n(*M_PESSOAS) == 1
    # com a sessão de quem achou o catálogo vencido (a cópia do contexto leva o JWT)
    assert [m for m, _p in fr.pedidos] == [api.RPC_PERSONNEL]
    nomes = [p["name"] for p in b.get("/os/api/responsaveis").get_json()["pessoas"]]
    assert nomes == ["Ana Teste Silva", "Bruno Exemplo", "Eva Nova"] and fr.por_tras == []


def test_a_renovacao_por_tras_leva_a_sessao_de_quem_pediu(fr, monkeypatch):
    ct = _catalogos()
    agora = {"t": time.time()}
    monkeypatch.setattr(ct, "_relogio", lambda: agora["t"])
    a = _cliente("ana@exemplo.invalid")
    a.get("/os/api/tradicional/etiquetas")
    agora["t"] += ct.PRAZO_S["etiquetas"] + 1
    _cliente("bruno@exemplo.invalid").get("/os/api/tradicional/etiquetas")
    quem = []
    original = fr.rpc

    def rpc(metodo, params, timeout=45):
        quem.append(sessao.jwt_atual())
        return original(metodo, params, timeout)
    monkeypatch.setattr(api, "_rpc_call", rpc)
    t = threading.Thread(target=fr.por_tras.pop())                      # numa thread de verdade, fora do pedido
    t.start()
    t.join(5)
    assert quem == [_jwt("bruno@exemplo.invalid")]


def test_o_erro_e_o_vazio_nao_ficam_guardados(fr):
    c = _cliente("ana@exemplo.invalid")
    fr.erro = api.FracttalError("HTTP 429")
    assert c.get("/os/api/cos/listas?so=classif").get_json()["erros"]["classif"] == "HTTP 429"
    fr.erro = None
    fr.etiquetas = []                                                    # a sessão de alguém sem a permissão
    assert c.get("/os/api/tradicional/etiquetas").get_json()["etiquetas"] == []
    fr.etiquetas = [{"id": 7, "description": "PERFORMANCE"}]
    assert c.get("/os/api/tradicional/etiquetas").get_json()["etiquetas"][0]["id"] == 7
    assert c.get("/os/api/cos/listas?so=classif").get_json()["classif"]["c1"][0]["id"] == 11
    assert fr.n(*M_ETIQUETAS) == 2 and fr.n(*M_TIPOS) == 4               # o erro (1) e o vazio não seguraram ninguém
    c.get("/os/api/tradicional/etiquetas")
    assert fr.n(*M_ETIQUETAS) == 2
    e = {x["nome"]: x for x in _catalogos().estado()["assuntos"]}
    assert e["etiquetas"]["n"] == 1 and e["tipos"]["erro"] is None


def test_o_status_sem_o_fracttal_e_a_lista_local_e_nao_fica(fr, monkeypatch):
    ct = _catalogos()
    agora = {"t": time.time()}
    monkeypatch.setattr(ct, "_relogio", lambda: agora["t"])
    c = _cliente("ana@exemplo.invalid")
    fr.erro = api.FracttalError("fora do ar")
    local = [t for t in api.STATUS_SOLICITACAO if t[1] not in ("OPEN_STATUS", "REQUEST_TODO")]
    assert _no_pedido(c, rotas_solic._status_cat) == local
    fr.erro = None
    fr.status = [{"id": 5}]
    agora["t"] += 60
    assert _no_pedido(c, rotas_solic._status_cat) == local and fr.n(*M_STATUS) == 1   # a Fila logo depois: sem tentar
    agora["t"] += ct.ESPERA_TENTATIVA_S
    assert [t[0] for t in _no_pedido(c, rotas_solic._status_cat)] == [5]  # a lista local não ficou guardada
    assert fr.n(*M_STATUS) == 2


def test_quem_chega_junto_na_primeira_leitura_espera_a_mesma(fr, monkeypatch):
    lento = fr.rpc

    def rpc(metodo, params, timeout=45):
        time.sleep(0.2)
        return lento(metodo, params, timeout)
    monkeypatch.setattr(api, "_rpc_call", rpc)
    saidas = []

    def tela(email):
        c = _cliente(email)
        saidas.append(len(c.get("/os/api/responsaveis").get_json()["pessoas"]))
    _cliente("ana@exemplo.invalid")                                      # o app, antes das threads
    ts_ = [threading.Thread(target=tela, args=(e,)) for e in EMAILS * 2]
    for t in ts_:
        t.start()
    for t in ts_:
        t.join(10)
    assert saidas == [2] * 6 and fr.n(*M_PESSOAS) == 1


# ── a criação da Engenharia confere ao vivo ─────────────────────────────────────────────────────────────────────────────
def _corpo_eng(pid=501):
    return {"ativos": [ATIVOS[0]["id"]], "descricao": "Avaliar", "problema": "Desarma", "responsavel": {"id_personnel": pid}}


def test_a_criacao_da_engenharia_confere_ao_vivo(fr, monkeypatch):
    """A regra de 19/10/2026: faltando no Fracttal a pessoa ou a etiqueta ENGENHARIA, nenhuma OS sai. A criação confere as duas
    AO VIVO, uma leitura de cada por gravação, com a sessão de quem cria: o catálogo serve à TELA, e a pessoa desligada ou a
    etiqueta apagada nas últimas horas seguiriam nele até a renovação (revisão da 4.1, Important 2). A sessão morta é acusada
    antes da gravação (401 e o login), e não com um "Relogue" por ativo."""
    criadas = []
    monkeypatch.setattr(api, "create_work_orders_bulk", lambda assets, *a, **k: criadas.append(k) or [
        {"code": x["code"], "ok": True, "os": {"wo_folio": 15000, "id_work_order": 9000}} for x in assets])
    monkeypatch.setenv(reg.ENV_RESPONSAVEIS, "Ana Teste;Eva Nova")
    c = _cliente("ana@exemplo.invalid")
    _ok(c.get("/os/api/solicitacao/engenharia/responsaveis"))            # a tela: o catálogo
    _ok(c.get("/os/api/tradicional/tipos"))                              # (a Classificação 1 vem do catálogo dos tipos)
    antes = (fr.n(*M_PESSOAS), fr.n(*M_ETIQUETAS))
    assert _ok(c.post("/os/api/solicitacao/engenharia/criar", json=_corpo_eng(501))).get_json()["ok"]
    assert criadas[-1]["etiqueta_ids"] == [900]
    assert (fr.n(*M_PESSOAS), fr.n(*M_ETIQUETAS)) == (antes[0] + 1, antes[1] + 1)    # uma leitura de cada, ao vivo
    # a pessoa que entrou no Fracttal agora sai na hora, sem esperar o catálogo
    fr.pessoal.append({"id": 504, "code": "E5", "full_name": "Eva Nova", "active": True, "id_account": 15,
                       "account_email": "eva@exemplo.invalid"})
    assert _ok(c.post("/os/api/solicitacao/engenharia/criar", json=_corpo_eng(504))).get_json()["ok"]
    assert criadas[-1]["id_responsible"] == 504
    n = len(criadas)
    # a etiqueta ENGENHARIA apagada no Fracttal: nenhuma OS sai, mesmo com ela no catálogo
    fr.etiquetas = [e for e in fr.etiquetas if e["description"] != "ENGENHARIA"]
    r = _ok(c.post("/os/api/solicitacao/engenharia/criar", json=_corpo_eng(501)), 400)
    assert "ENGENHARIA" in r.get_json()["erro"] and len(criadas) == n
    # a pessoa desligada no Fracttal: idem
    fr.etiquetas.append({"id": 900, "description": "ENGENHARIA"})
    for p in fr.pessoal:
        if p["id"] == 501:
            p["active"] = False
    r = _ok(c.post("/os/api/solicitacao/engenharia/criar", json=_corpo_eng(501)), 400)
    assert "Engenharia" in r.get_json()["erro"] and len(criadas) == n
    # a sessão morta: 401 com o login, antes de gravar
    monkeypatch.setattr(api, "_rpc_call", _morre)
    r = _ok(c.post("/os/api/solicitacao/engenharia/criar", json=_corpo_eng(504)), 401)
    assert r.get_json().get("login") and len(criadas) == n


# ── o que o catálogo não faz (a rodada 1 da revisão da 4.1) ─────────────────────────────────────────────────────────────
def _morre(metodo, params, timeout=45):
    """O 401 do Fracttal como o `_rpc_chamar` o trata: limpa a sessão (a do contexto) e levanta."""
    api._clear_jwt()
    raise api.SessionExpired("RPC %s HTTP 401 — a sessão do Fracttal expirou" % metodo)


def test_as_falhas_pela_metade_nao_trocam_as_completas(fr, monkeypatch):
    """Important 1: o `get_falha_listas` engolia o erro de cada lista, e o catálogo guardava a leitura que só tinha os tipos.
    Um 429 nas causas trocava as listas completas por `{"causas": []}` por 24 h, e o COS recusava toda OS de falha."""
    ct = _catalogos()
    agora = {"t": time.time()}
    monkeypatch.setattr(ct, "_relogio", lambda: agora["t"])
    c = _cliente("ana@exemplo.invalid")
    completas = _no_pedido(c, rotas_cos._falhas_para_criar)
    assert all(completas[k] for k in ("tipos", "causas", "metodos"))
    original = fr.rpc

    def cota_nas_causas(metodo, params, timeout=45):
        r = original(metodo, params, timeout)
        if metodo == api.RPC_FALHA_CAUSAS:
            raise api.FracttalError("RPC %s HTTP 429 — muitas requisições" % metodo)
        return r
    monkeypatch.setattr(api, "_rpc_call", cota_nas_causas)
    agora["t"] += ct.PRAZO_S["falhas"] + 1
    assert _no_pedido(c, rotas_cos._falhas_para_criar) == completas      # vencidas: as de antes, e a renovação por trás
    fr.por_tras.pop()()
    assert _no_pedido(c, rotas_cos._falhas_para_criar) == completas      # a leitura pela metade não trocou nada
    assert "429" in ({x["nome"]: x for x in ct.estado()["assuntos"]}["falhas"]["erro"] or "")
    # sem cópia nenhuma: a leitura pela metade não fica, e a tela diz o erro
    ct.reiniciar()
    j = c.get("/os/api/cos/listas?so=falhas").get_json()
    assert "429" in (j["erros"].get("falhas") or "")
    assert {x["nome"]: x for x in ct.estado()["assuntos"]}["falhas"]["n"] == 0


def test_o_criado_por_e_de_cada_pessoa(fr):
    """Important 3: o "Criado por" do Histórico (as contas e o "eu") é lido POR PESSOA, com a sessão dela, e guardado 10 min
    para ela, como até 31/10. Quem não tem a permissão de pessoal no Fracttal recebe a lista vazia, e não as contas da empresa
    que o catálogo comum tem (o catálogo segue para a lista de responsáveis e a pessoa logada)."""
    fr.sem_permissao.add("dora@exemplo.invalid")
    a, d = _cliente("ana@exemplo.invalid"), _cliente("dora@exemplo.invalid")
    a.get("/os/api/responsaveis")                                        # o catálogo comum, pela sessão da Ana
    assert _no_pedido(d, api.get_pessoas_contas) == {"pessoas": [], "eu": None}
    assert [p["id_account"] for p in _no_pedido(a, api.get_pessoas_contas)["pessoas"]] == [11, 12, 13]

    def criado_por(c):
        html = _ok(c.get("/os/historico?modo=criadas")).get_data(as_text=True)
        ini = html.index('<select name="pessoa">')
        return html[ini:html.index("</select>", ini)]
    assert "Ana Teste Silva" in criado_por(a) and "Ana Teste Silva" not in criado_por(d)
    n = len(fr.pedidos_p2)
    for c in (a, d, a, d):                                               # guardado 10 min para cada uma
        criado_por(c)
    assert len(fr.pedidos_p2) == n


def test_o_rest_com_a_conta_ou_o_email_trocados_nao_troca(fr):
    """Important 4: a conferência REST x RPC olhava só os ids da lista de responsáveis. O mesmo id com outra conta
    (`id_account`: o "criadas por mim") ou outro e-mail (a pessoa logada) passava, e mudava o dono das OS sem ninguém ver."""
    ct, cl = _catalogos(), _leitor()
    c = _cliente("ana@exemplo.invalid")
    c.get("/os/api/responsaveis")                                        # o catálogo pelo RPC
    rel = cl.ler_pessoas_rest(ler=_rest([_rest_completo(dict(p, id_account=p["id_account"] + 1000)) for p in PESSOAL]))
    assert "id_account" in rel["erro"]
    rel = cl.ler_pessoas_rest(ler=_rest([_rest_completo(dict(p, account_email="x" + p["account_email"])) for p in PESSOAL]))
    assert "e-mail" in rel["erro"]
    assert {x["nome"]: x for x in ct.estado()["assuntos"]}["pessoas"]["fonte"] == "rpc"
    assert _no_pedido(c, api._current_user_info) == (501, 11, "Ana Teste Silva")


def test_a_renovacao_por_tras_nao_derruba_a_sessao_de_quem_pediu(fr, monkeypatch):
    """Minor 1: a thread da renovação levava a cópia do contexto de quem pediu, e a cópia leva o MESMO estado da sessão. Um 401
    lá marcava a sessão dela como morta, e o pedido dela, se ainda corria, saía para o login."""
    ct = _catalogos()
    agora = {"t": time.time()}
    monkeypatch.setattr(ct, "_relogio", lambda: agora["t"])
    _cliente("ana@exemplo.invalid").get("/os/api/tradicional/etiquetas")
    agora["t"] += ct.PRAZO_S["etiquetas"] + 1
    b = _cliente("bruno@exemplo.invalid")
    with b.application.test_request_context(), sessao.contexto(b.jwt, b.email):
        assert ct.etiquetas()                                            # a vencida, na hora; a renovação fica com o teste
        monkeypatch.setattr(api, "_rpc_call", _morre)
        t = threading.Thread(target=fr.por_tras.pop())
        t.start()
        t.join(5)
        assert sessao.morta() is False


def test_a_renovacao_dos_ativos_por_tras_nao_derruba_a_sessao(monkeypatch):
    """Minor 1, o mesmo no catálogo de ativos (`api._renovar_catalogo_por_tras`)."""
    criar_app(segredo="teste", testing=True)                             # a sessão por pessoa instalada no `api`
    monkeypatch.setitem(api._ASSETS_RENOVA, "tentou", 0.0)
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: _morre("inventories.items_list", {}))
    with sessao.contexto(_jwt("bruno@exemplo.invalid"), "bruno@exemplo.invalid"):
        api._renovar_catalogo_por_tras()
        for t in [t for t in threading.enumerate() if t.name == "os-catalogo-por-tras"]:
            t.join(5)
        assert sessao.morta() is False


def test_a_conta_nova_com_o_rest_valendo_e_achada_pelo_rpc(fr, monkeypatch):
    """Minor 2: com o REST valendo, a renovação das pessoas é do laço do servidor (05h, 11h, 17h e 23h), e a conta nova no
    Fracttal ficava até 6 h sem "criadas por mim". Quem não está no catálogo relê pelo RPC, com a sessão DELA, uma vez por
    pessoa a cada 10 min (e não com o catálogo recém-lido)."""
    ct, cl = _catalogos(), _leitor()
    agora = {"t": time.time()}
    monkeypatch.setattr(ct, "_relogio", lambda: agora["t"])
    ct.ligar_leitor(ligado=True)                                         # o laço do servidor
    c = _cliente("ana@exemplo.invalid")
    c.get("/os/api/responsaveis")
    assert cl.ler_pessoas_rest(ler=_rest([_rest_completo(p) for p in PESSOAL]))["erro"] == ""
    fr.pessoal.append({"id": 504, "code": "E5", "full_name": "Eva Nova", "active": True, "id_account": 15,
                       "account_email": "eva@exemplo.invalid"})            # a conta nova no Fracttal
    agora["t"] += 2 * 3600
    assert _no_pedido(_cliente("eva@exemplo.invalid"), api._current_user_info) == (504, 15, "Eva Nova")
    assert fr.n(*M_PESSOAS) == 2 and fr.por_tras == []
    agora["t"] += 120
    d = _cliente("dora@exemplo.invalid")                                 # quem não está nem assim: uma vez a cada 10 min
    for _ in range(3):
        assert _no_pedido(d, api._current_user_info) == (None, None, "")
    assert fr.n(*M_PESSOAS) == 3
    agora["t"] += ct.ESPERA_TENTATIVA_S
    _no_pedido(d, api._current_user_info)
    assert fr.n(*M_PESSOAS) == 4


def test_a_conta_nova_em_duas_telas_juntas_espera_a_mesma_leitura(fr, monkeypatch):
    """Re-revisão da 4.1 (Minor a): duas telas da conta nova ao mesmo tempo (a lista e o card, duas abas). A 1ª relia o
    pessoal, e a 2ª, que chegava com a releitura em curso, saía com `(None, None, "")`: "criadas por mim" vazio naquela tela.
    A 2ª espera a mesma leitura, e o pessoal é lido uma vez só."""
    ct = _catalogos()
    agora = {"t": time.time()}
    monkeypatch.setattr(ct, "_relogio", lambda: agora["t"])
    _cliente("ana@exemplo.invalid").get("/os/api/responsaveis")          # o catálogo, ainda sem a conta nova
    fr.pessoal.append({"id": 504, "code": "E5", "full_name": "Eva Nova", "active": True, "id_account": 15,
                       "account_email": "eva@exemplo.invalid"})
    agora["t"] += 120
    original = fr.rpc

    def lento(metodo, params, timeout=45):
        if metodo == api.RPC_PERSONNEL:
            time.sleep(0.3)                                              # a releitura demora: a 2ª tela chega no meio
        return original(metodo, params, timeout)
    monkeypatch.setattr(api, "_rpc_call", lento)
    eva, saidas = _cliente("eva@exemplo.invalid"), []

    def tela():
        saidas.append(_no_pedido(eva, api._current_user_info))
    telas = [threading.Thread(target=tela) for _ in range(2)]
    for t in telas:
        t.start()
        time.sleep(0.05)
    for t in telas:
        t.join(5)
    assert saidas == [(504, 15, "Eva Nova")] * 2 and fr.n(*M_PESSOAS) == 2


def test_o_nome_que_e_um_email_nao_vai_ao_disco(fr, tmp_path):
    """Minor 3: a pessoa sem nome no Fracttal aparece pelo e-mail (o `full_name` dela é o e-mail). A tela mostra como sempre
    mostrou, e o disco não guarda o e-mail em claro."""
    ct = _catalogos()
    pasta = str(tmp_path / "catalogos")
    ct.reiniciar(pasta=pasta, chave=CHAVE)
    fr.pessoal.append({"id": 505, "code": "F6", "full_name": "integracao@exemplo.invalid", "active": True, "id_account": 16,
                       "account_email": "integracao@exemplo.invalid"})
    c = _cliente("ana@exemplo.invalid")
    assert "integracao@exemplo.invalid" in [p["name"] for p in c.get("/os/api/responsaveis").get_json()["pessoas"]]
    with open(os.path.join(pasta, "pessoas.json"), encoding="utf-8") as f:
        texto = f.read()
    assert "@" not in texto and "exemplo.invalid" not in texto


def test_a_renovacao_dos_planos_por_tras_tem_ritmo(fr, monkeypatch):
    """Minor 4: a renovação dos planos vencidos relia os inversores um atrás do outro, sem pausa, e seguia depois da cota e da
    sessão que caiu. Agora: 1 pedido por segundo, o 406/429 espera (5 s e 10 s) e tenta o mesmo ativo de novo, e a sessão que
    caiu para a renovação; o ativo que faltou fica para a próxima sessão, já."""
    ct = _catalogos()
    agora = {"t": time.time()}
    monkeypatch.setattr(ct, "_relogio", lambda: agora["t"])
    a = _cliente("ana@exemplo.invalid")
    _escolher_usina(a)
    agora["t"] += ct.PRAZO_S["planos"] + 1
    original, vez = fr.rpc, {"n": 0}

    def rpc(metodo, params, timeout=45):
        if metodo == api.RPC_TASK_EVENTS:
            vez["n"] += 1
            if vez["n"] == 2:                                            # o 2º inversor: a cota, uma vez
                raise api.FracttalError("RPC %s HTTP 429 — muitas requisições" % metodo)
            if vez["n"] == 4:                                            # o 3º: a sessão caiu
                raise api.SessionExpired("RPC %s HTTP 401 — a sessão do Fracttal expirou" % metodo)
        return original(metodo, params, timeout)
    monkeypatch.setattr(api, "_rpc_call", rpc)
    _escolher_usina(a)                                                   # os de ontem, e a renovação por trás
    renovar = fr.por_tras[0]                                             # (a dos planos; a 2ª é a do detalhe)
    fr.por_tras.clear()
    fr.dormiu.clear()
    renovar()
    # os números do contrato, e não as constantes do módulo (que mudariam junto com o erro): 1 s entre os inversores, e a cota
    # espera 5 s e depois 10 s
    assert ct.ESPERAS_COTA_S == (5, 10)
    assert vez["n"] == 4 and fr.dormiu == [1.0, 5, 1.0]
    _escolher_usina(_cliente("bruno@exemplo.invalid"))                   # o 3º volta a ser de quem chegar, sem os 10 min
    assert len(fr.por_tras) == 1
    fr.por_tras.pop()()
    assert vez["n"] == 5


def test_o_status_com_o_rpc_vazio_e_a_lista_local_e_nao_fica(fr, monkeypatch):
    """Minor 5: o Fracttal que respondeu a lista de status VAZIA fazia o `status_solicitacao_catalogo` devolver a lista local,
    e o catálogo a guardava 24 h como se fosse o que o Fracttal aceita."""
    ct = _catalogos()
    agora = {"t": time.time()}
    monkeypatch.setattr(ct, "_relogio", lambda: agora["t"])
    c = _cliente("ana@exemplo.invalid")
    fr.status = []
    local = [t for t in api.STATUS_SOLICITACAO if t[1] not in ("OPEN_STATUS", "REQUEST_TODO")]
    assert _no_pedido(c, rotas_solic._status_cat) == local
    fr.status = [{"id": 5}]
    agora["t"] += ct.ESPERA_TENTATIVA_S + 1
    assert [t[0] for t in _no_pedido(c, rotas_solic._status_cat)] == [5]  # a lista local não ficou guardada


def test_a_copia_dos_planos_em_disco_nao_volta_atras(fr, tmp_path, monkeypatch):
    """Minor 6: duas gravações dos planos juntas (a 1ª escolha de duas usinas, ou uma escolha e a renovação por trás) montavam
    a cópia dentro da trava e escreviam fora dela: a montada antes podia escrever depois, e cobrir a nova."""
    import catalogos_planos as cp
    ct = _catalogos()
    pasta = str(tmp_path / "catalogos")
    ct.reiniciar(pasta=pasta, chave=CHAVE)
    escrever, solta, primeira = ct.escrever_json, threading.Event(), [True]

    def lenta(destino, carga):
        if primeira[0] and destino.endswith("planos.json"):
            primeira[0] = False
            solta.wait(5)                                                # a 1ª gravação demora (o disco, o antivírus)
        escrever(destino, carga)
    monkeypatch.setattr(ct, "escrever_json", lenta)
    agora = time.time()
    cp._PLANOS["itens"]["601:77"] = {"lido_em": agora, "planos": [{"id_task": 701, "description": "a"}]}
    t1 = threading.Thread(target=cp._gravar_por_chave, args=(cp._PLANOS, "planos", cp.PLANOS_MAX))
    t1.start()
    time.sleep(0.1)                                                      # a 1ª montou a cópia e espera no disco
    cp._PLANOS["itens"]["602:77"] = {"lido_em": agora, "planos": [{"id_task": 702, "description": "b"}]}
    t2 = threading.Thread(target=cp._gravar_por_chave, args=(cp._PLANOS, "planos", cp.PLANOS_MAX))
    t2.start()
    t2.join(0.3)                                                         # a 2ª, com o ativo novo, escreve antes se puder
    solta.set()
    t1.join(5)
    t2.join(5)
    with open(os.path.join(pasta, "planos.json"), encoding="utf-8") as f:
        assert sorted(json.load(f)["itens"]) == ["601:77", "602:77"]


# ── as pessoas pelo REST da empresa (só o servidor) ─────────────────────────────────────────────────────────────────────
def _rest(linhas, por_pagina=100):
    """O REST `personnel` de mentira (o do cadastro, `fracttal_pessoal`): pagina de 100 em 100 e guarda os caminhos e a origem
    com que cada pedido saiu (o contador do Fracttal)."""
    from nexus.casca import fracttal_conta
    pedidos = []

    def ler(path):
        marca = fracttal_conta._marca_atual.get()
        pedidos.append((path, marca.nome if marca is not None else None, time.monotonic()))
        ini = int(path.split("start=")[1].split("&")[0])
        return {"data": [dict(p) for p in linhas[ini:ini + por_pagina]]}
    ler.pedidos = pedidos
    return ler


def _rest_completo(p):
    """Uma pessoa do RPC como o REST a escreveria, com todos os campos que as telas usam (o REST não foi sondado antes de
    construir: a 1ª leitura do servidor confere)."""
    return {"id_personnel": p["id"], "code": p["code"], "full_name": p["full_name"], "active": p["active"],
            "id_account": p["id_account"], "email": p["account_email"]}


def test_pessoas_pelo_rest_com_os_campos_da_tela(fr, monkeypatch):
    ct = _catalogos()
    dormiu = []
    monkeypatch.setattr(ct, "_dormir", lambda s: dormiu.append(s))
    fr.pessoal += [{"id": 600 + i, "code": "X%d" % i, "full_name": "Pessoa %03d" % i, "active": True, "id_account": 700 + i,
                    "account_email": "p%d@exemplo.invalid" % i} for i in range(120)]
    # a 1ª leitura REST só vale conferida contra um catálogo do RPC (a 1ª noite dos ativos, REST x RPC): sem ele, espera
    assert "RPC" in _leitor().ler_pessoas_rest(ler=_rest([_rest_completo(p) for p in fr.pessoal]))["erro"]
    c = _cliente("ana@exemplo.invalid")
    assert len(c.get("/os/api/responsaveis").get_json()["pessoas"]) == 122 and fr.n(*M_PESSOAS) == 2   # a 1ª tela, pelo RPC
    dormiu.clear()
    ler = _rest([_rest_completo(p) for p in fr.pessoal])
    rel = _leitor().ler_pessoas_rest(ler=ler)
    assert rel["erro"] == "" and rel["pedidos"] == 2 and dormiu == [ct.PAUSA_S]           # 1 por segundo
    assert {o for _p, o, _t in ler.pedidos} == {"fundo:nexus-catalogos:pessoas"}         # a origem no contador
    assert len(c.get("/os/api/responsaveis").get_json()["pessoas"]) == 122
    assert _no_pedido(c, api._current_user_info) == (501, 11, "Ana Teste Silva")
    assert fr.n(*M_PESSOAS) == 2                                         # nada mais pelo RPC
    e = ct.estado()
    assert {x["nome"]: x for x in e["assuntos"]}["pessoas"]["fonte"] == "rest" and e["rest"]["bom_em"]


def test_pessoas_pelo_rest_sem_os_campos_seguem_pelo_rpc(fr, monkeypatch):
    """O cadastro conhece do REST `personnel` o id, o código, o nome, o e-mail, o acesso e a conta ativa
    (`fracttal_pessoal.da_api`). Sem o `active` (o pessoal ativo) e o `id_account` (quem criou a OS) o REST não serve às
    telas: a leitura é recusada, o estado diz o campo, e o catálogo segue pelo RPC, pela sessão de quem usa."""
    ct = _catalogos()
    monkeypatch.setattr(ct, "_dormir", lambda s: None)
    linhas = [{"id_personnel": p["id"], "code": p["code"], "full_name": p["full_name"], "email": p["account_email"],
               "groups_permissions_description": "Leitura", "account_active": True} for p in PESSOAL]
    rel = _leitor().ler_pessoas_rest(ler=_rest(linhas))
    assert "active" in rel["erro"] and "id_account" in rel["erro"]
    e = ct.estado()
    assert e["rest"]["falha"] and "id_account" in e["rest"]["falha"] and not e["rest"]["bom_em"]
    c = _cliente("ana@exemplo.invalid")
    assert len(c.get("/os/api/responsaveis").get_json()["pessoas"]) == 2 and fr.n(*M_PESSOAS) == 1


def test_o_rest_que_nao_bate_com_o_rpc_nao_troca(fr, monkeypatch):
    ct = _catalogos()
    monkeypatch.setattr(ct, "_dormir", lambda s: None)
    c = _cliente("ana@exemplo.invalid")
    c.get("/os/api/responsaveis")                                        # o catálogo pelo RPC
    linhas = [_rest_completo(dict(p, active=not p["active"])) for p in PESSOAL]   # o `active` com outro sentido
    rel = _leitor().ler_pessoas_rest(ler=_rest(linhas))
    assert rel["erro"] and "RPC" in rel["erro"]
    assert [p["name"] for p in c.get("/os/api/responsaveis").get_json()["pessoas"]] == ["Ana Teste Silva", "Bruno Exemplo"]
    rel = _leitor().ler_pessoas_rest(ler=_rest([_rest_completo(p) for p in PESSOAL]))        # o que bate entra
    assert rel["erro"] == "" and {x["nome"]: x for x in ct.estado()["assuntos"]}["pessoas"]["fonte"] == "rest"


def test_com_o_rest_valendo_o_rpc_nao_renova_as_pessoas(fr, monkeypatch):
    ct = _catalogos()
    agora = {"t": time.time()}
    monkeypatch.setattr(ct, "_relogio", lambda: agora["t"])
    monkeypatch.setattr(ct, "_dormir", lambda s: None)
    ct.ligar_leitor(ligado=True)                                         # o laço do servidor
    c = _cliente("ana@exemplo.invalid")
    c.get("/os/api/responsaveis")                                        # o catálogo do RPC, que confere a 1ª leitura REST
    assert _leitor().ler_pessoas_rest(ler=_rest([_rest_completo(p) for p in PESSOAL]))["erro"] == ""
    agora["t"] += ct.PRAZO_S["pessoas"] + 600                            # o laço das :04 atrasou: ainda vale (a folga)
    c.get("/os/api/responsaveis")
    assert fr.por_tras == [] and fr.n(*M_PESSOAS) == 1
    agora["t"] += ct.FOLGA_REST_S                                        # o laço parou: o socorro é o RPC, por trás
    c.get("/os/api/responsaveis")
    assert len(fr.por_tras) == 1


def test_so_o_servidor_liga_o_laco(app, monkeypatch):
    ct = _catalogos()
    ligou = []
    cl = _leitor()
    monkeypatch.setattr(cl, "_laco", lambda: ligou.append(1))            # o laço, se abrisse, diria
    cl.ligar(app)                                                        # sem a credencial REST: não liga
    assert not ct.estado()["rest"]["ligado"] and "credencial" in ct.estado()["rest"]["motivo"]
    app.extensions.pop(cl.CHAVE, None)
    app.config["NEXUS_PCM_FRACTTAL_TESTE"] = {"FRACTTAL_CLIENT_ID": "id-de-mentira", "FRACTTAL_CLIENT_SECRET": "s"}
    cl.ligar(app)
    time.sleep(0.05)
    assert ct.estado()["rest"]["ligado"] and ligou == []                 # nos testes, o laço não abre
    cl.ligar(app)                                                        # ligar de novo no mesmo app não faz nada
    assert ligou == []
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    servir = open(os.path.join(raiz, "servir.py"), encoding="utf-8").read()
    pc = open(os.path.join(raiz, "app.py"), encoding="utf-8").read()
    assert 'ligar_leitor_do_clone(app, "catalogos_leitor")' in servir and "catalogos_leitor.ligar(" not in servir
    assert "catalogos" not in pc


def test_o_minuto_das_pessoas_mora_na_lista_unica():
    from datetime import datetime, timedelta, timezone

    from nexus.casca import minutos_ocupados as MO
    cl = _leitor()
    assert cl.MINUTO == MO.CATALOGOS_PESSOAS and "catálogos" in MO.OCUPADOS[MO.CATALOGOS_PESSOAS]
    brt = timezone(timedelta(hours=-3))
    vistos = []
    t = datetime(2026, 11, 2, 0, 0, tzinfo=brt).timestamp()
    for _ in range(5):
        espera = cl.proximo_passo(t)
        t += espera
        vistos.append(datetime.fromtimestamp(t, brt).strftime("%H:%M"))
    m = "%02d" % MO.CATALOGOS_PESSOAS
    assert vistos == ["05:" + m, "11:" + m, "17:" + m, "23:" + m, "05:" + m]
    for h in cl.HORAS:
        assert MO.livre(MO.CATALOGOS_PESSOAS, hora=h) is False


# ── o Raio-X ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_os_catalogos_no_raio_x(fr, logado, monkeypatch):
    from nexus.casca import raio_x as R
    monkeypatch.setattr(R, "_processador", lambda janela_s=1.0: {"pct": 10, "nucleos": 4, "carga": None})
    monkeypatch.setattr(R, "_memoria_por_programa", lambda prazo_s=R.PRAZO_MEMORIA_S: None)
    monkeypatch.setattr(R, "RELATORIO_WEB", "/nao/existe/web.json")
    monkeypatch.setattr(R, "RELATORIO_WORKER", "/nao/existe/worker.json")
    for nome in ("_WORKER", "_WEB", "_MEMORIA", "_THREADS"):
        monkeypatch.setattr(R, nome, {"thread": None, "ultimo": None, "quando": None}, raising=False)
    monkeypatch.setattr(R, "_secao_uso_os", lambda app: {"tem": False, "banco_txt": "", "motivo": "teste"})
    ct = _catalogos()
    c = _cliente("ana@exemplo.invalid")
    _tudo(c)
    _escolher_usina(c)
    html = logado.get("/t/base/raio-x").get_data(as_text=True)
    ini = html.index('id="canto-central"')
    bloco = html[ini:html.index("</section>", ini)]
    assert "Catálogos pequenos" in bloco
    for a in ct.estado()["assuntos"]:
        assert ">%s</td>" % a["rotulo"] in bloco, a["rotulo"]
    assert "Planos da Performance" in bloco and "Pessoas pelo REST" in bloco
    for proibido in ("Ana Teste", "Bruno", "@", "exemplo.invalid"):                 # nem nome nem e-mail
        assert proibido not in bloco, proibido
