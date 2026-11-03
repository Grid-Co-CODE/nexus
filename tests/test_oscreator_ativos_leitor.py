"""O leitor dos ativos do servidor (31/10/2026, tarefa 2.2 do canto central do OS Creator): o Fracttal inteiro de madrugada pela
credencial da empresa (REST `items`), só os novos de dia, a conferência contra o catálogo e a foto do banco renovada.

O que estes testes seguram (os módulos são `os_creator/ativos_leitor.py`, `os_creator/ativos_central.py` e
`nexus/dados/foto_ativos.py`):
- a leitura inteira pagina de 100 em 100, com 1 s entre os pedidos, e para no total que o Fracttal informa; a incompleta não
  troca nada; a recusa (406/429) espera e tenta a mesma página de novo;
- os novos param na primeira página inteira de ids conhecidos (1 pedido sem novidade, 2 com), e a página fora de ordem não
  acrescenta nada; os novos não mexem no `lido_em` da lista inteira;
- o caminho do ativo sai da cadeia de pais igual ao do RPC, e o grupo de tarefas cai no catálogo e na foto;
- a paridade REST x catálogo passa e falha, e a que falha deixa o catálogo pelo RPC (uma vez por dia, para todos);
- a foto guarda o código que saiu do Fracttal, marcado, e só grava quando muda; só depois que o catálogo aceitou;
- o encolhimento confirmado por duas leituras, que sobrevive ao reinício;
- só o servidor liga o leitor, e sem a credencial ele não liga.
Fracttal, banco e disco são dublês ou pastas de teste: nada vai à rede. Nomes, códigos e usinas são de mentira (repositório
público)."""
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from pg_falso import ApiPGFalsa

from nexus.campo import fracttal
from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone (o mesmo módulo que as rotas usam)
import ativos_central as AC  # noqa: E402
import ativos_foto as AF  # noqa: E402
import ativos_leitor as AL  # noqa: E402

from nexus.dados import equipamento as eq  # noqa: E402
from nexus.dados import foto_ativos as FA  # noqa: E402
from nexus.dados import livros  # noqa: E402

AQUI = Path(__file__).resolve().parent.parent
BASE = "http://pg.falso"
_BRT = timezone(timedelta(hours=-3))


@pytest.fixture(autouse=True)
def dormidas(monkeypatch):
    """Cada teste começa sem catálogo e sem leitor; o ritmo (1 s entre páginas) e as esperas da recusa são anotados, não
    dormidos."""
    AC.reiniciar()
    AL.reiniciar()
    feitas = []
    monkeypatch.setattr(AL, "_dormir", feitas.append)
    monkeypatch.setattr(api, "_ASSETS_RENOVA", {"tentou": 0.0})
    yield feitas
    AC.reiniciar()
    AL.reiniciar()


@pytest.fixture
def banco(app):
    """O app do Nexus com o banco de mentira (devolve tudo como texto, como a API pode fazer) e o token."""
    pg = ApiPGFalsa(como_texto=True)
    app.extensions["nexus_dados_sessao"] = pg
    app.config.update(GRIDCO_SQL_TOKEN="token-de-teste", GRIDCO_DB_API=BASE)
    return pg


# ── o Fracttal de mentira ───────────────────────────────────────────────────────────────────────────────────────────────
GAMA = "Cliente Alfa - Usina Gama 1 - PA"


def _it(i, code, desc, pai, tipo=2, grupo=None, **mais):
    """Um item como o REST `items` o dá (com campos que o catálogo não usa, que o leitor tem de jogar fora)."""
    d = {"id": i, "code": code, "description": desc, "id_parent": pai, "id_type_item": tipo, "latitude": None,
         "groups_1_description": "Classificação de mentira", "field_3": "Cidade de mentira"}
    if grupo is not None:
        d["id_group_task"] = grupo
    d.update(mais)
    return d


# a árvore (nomes de mentira): a raiz de cada cliente, a usina, a cabine e os inversores; a descrição traz o endereço da usina
# atrás do nome e o "{ CÓDIGO }" no fim, como o Fracttal escreve
ARVORE = [
    _it(1, "CAL", "Cliente Alfa", None, 1),
    _it(10, "CAL-GAM100", GAMA + "  Zona Rural km 4    { CAL-GAM100 }", 1, 1, grupo=7),
    _it(20, "CAL-GAM100-CABN1", "Cabine 1 Zona Rural km 4    { CAL-GAM100-CABN1 }", 10),
    _it(21, "CAL-GAM100-CABN2", "Cabine 2  Zona Rural km 4    { CAL-GAM100-CABN2 }", 10),
    _it(25, "CAL-GAM100-SKID1", "Skid 1 Zona Rural km 4    { CAL-GAM100-SKID1 }", 20),
    _it(30, "CAL-GAM100-INVR1.1", "Inversor 1.1 Marca X    { CAL-GAM100-INVR1.1 }", 25, grupo=55),
    _it(31, "CAL-GAM100-INVR1.2", "Inversor 1.2 Marca X    { CAL-GAM100-INVR1.2 }", 10),
    _it(33, "CAL-GAM100-INVR2.1", "Inversor 2.1 Marca X    { CAL-GAM100-INVR2.1 }", 21),
    _it(2, "GBE", "Grupo Beta", None, 1),
    # o cliente (Grupo Beta) não é o começo do nome da usina (Beta Solar): a carteira com outro nome
    _it(11, "BET-DEL100", "Beta Solar - Usina Delta 2 - BA Zona Rural km 9    { BET-DEL100 }", 2, 1),
    _it(32, "BET-DEL100-INVR2.1", "Inversor 2.1    { BET-DEL100-INVR2.1 }", 11),
]


def _rpc():
    """Os mesmos ativos como o RPC (`inventories.items_list`) os dá: o caminho vem pronto, e o tipo e o grupo também."""
    cam = {10: "// Cliente Alfa/ ", 20: "// Cliente Alfa/ %s/ " % GAMA, 21: "// Cliente Alfa/ %s/ " % GAMA,
           25: "// Cliente Alfa/ %s/ Cabine 1/ " % GAMA, 30: "// Cliente Alfa/ %s/ Cabine 1/ Skid 1/ " % GAMA,
           31: "// Cliente Alfa/ %s/ " % GAMA, 33: "// Cliente Alfa/ %s/ Cabine 2/ " % GAMA, 11: "// Grupo Beta/ ",
           32: "// Grupo Beta/ Beta Solar - Usina Delta 2 - BA/ "}
    return [{"id": i["id"], "code": i["code"], "description": i["description"], "id_parent": i["id_parent"],
             "id_type_item": i["id_type_item"], "id_group_task": i.get("id_group_task"), "parent_description": cam[i["id"]]}
            for i in ARVORE if i["id"] in cam]


def _muitos(n, primeiro=1000):
    """n itens de mentira: a raiz, a usina e n-2 inversores com ids e códigos diferentes."""
    out = [_it(1, "CAL", "Cliente Alfa", None, 1), _it(10, "CAL-GAM100", GAMA + "  Zona Rural    { CAL-GAM100 }", 1, 1)]
    out += [_it(primeiro + k, "CAL-GAM100-INVR%d.%d" % (k // 10, k % 10), "Inversor %d    { x }" % k, 10)
            for k in range(n - 2)]
    return out


def _catalogo_de(itens, fonte="rpc", lido_em=None):
    """O catálogo montado destes itens (o mesmo caminho que o RPC daria)."""
    assert AC.trocar(AC.montar_registros(AL.para_registro(itens)), fonte, lido_em=lido_em)
    return AC.atual()


class RestFalso:
    """O REST `items` do Fracttal: pagina pelo `start`/`limit` do caminho, ordena pelo id (desc com `sort=id:desc`, a não ser
    que `ignora_sort`), e conta os pedidos. `curta_em`: a página que começa ali vem com 40 itens a menos; `recusas`: {start:
    quantas vezes o Fracttal recusa aquela página antes de dar}; `sem_total`: o envelope sem o `total`."""

    def __init__(self, itens, curta_em=None, recusas=None, sem_total=False, ignora_sort=False, total=None):
        self.itens, self.paths = list(itens), []
        self.curta_em, self.recusas = curta_em, dict(recusas or {})
        self.sem_total, self.ignora_sort, self.total = sem_total, ignora_sort, total

    def __call__(self, path):
        self.paths.append(path)
        q = parse_qs(urlparse("http://x/api/" + path).query)
        inicio, limite = int(q["start"][0]), int(q["limit"][0])
        if self.recusas.get(inicio):
            self.recusas[inicio] -= 1
            raise fracttal.Recusado("o Fracttal recusou por excesso de pedidos (HTTP 429); a fila não foi lida")
        desc = q.get("sort") == ["id:desc"] and not self.ignora_sort
        lista = sorted(self.itens, key=lambda i: i["id"], reverse=desc)
        pagina = [dict(i) for i in lista[inicio:inicio + limite]]
        if self.curta_em == inicio:
            pagina = pagina[:-40]
        corpo = {"data": pagina}
        if not self.sem_total:
            corpo["total"] = str(self.total if self.total is not None else len(self.itens))     # o REST manda texto às vezes
        return corpo


# ── a leitura inteira ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_completo_pagina_e_para_no_total(dormidas):
    rest = RestFalso(_muitos(250))
    itens = AL.ler_todos_rest(ler=rest)
    assert len(itens) == 250 and len({i["id"] for i in itens}) == 250
    assert len(rest.paths) == 3 and all("limit=100" in p for p in rest.paths)        # 100 + 100 + 50: não pede a 4ª
    assert [p.split("start=")[1] for p in rest.paths] == ["0", "100", "200"]
    assert dormidas == [AL.PAUSA_S, AL.PAUSA_S] and AL.PAUSA_S >= 1.0                 # 1 pedido por segundo
    assert set(itens[0]) <= set(AL.CAMPOS_REST) and "latitude" not in itens[0]        # o resto do item não fica na memória
    # exatamente no múltiplo de 100: 2 páginas, sem pedir a 3ª vazia
    rest = RestFalso(_muitos(200))
    assert len(AL.ler_todos_rest(ler=rest)) == 200 and len(rest.paths) == 2
    # sem o total no envelope: até a página com menos de 100
    rest = RestFalso(_muitos(150), sem_total=True)
    assert len(AL.ler_todos_rest(ler=rest)) == 150 and len(rest.paths) == 2


def test_incompleto_nao_troca(banco, app):
    antes = _catalogo_de(_muitos(250))
    # a página do meio veio curta (antes do total): a leitura levanta e não troca nada
    with pytest.raises(AL.LeituraIncompleta, match="antes do total"):
        AL.ler_todos_rest(ler=RestFalso(_muitos(250), curta_em=100))
    # o total diz 300 e vieram 250 distintos (repetidos entre páginas)
    with pytest.raises(AL.LeituraIncompleta):
        AL.ler_todos_rest(ler=RestFalso(_muitos(250), total=300))
    with pytest.raises(AL.LeituraIncompleta, match="vazia"):
        AL.ler_todos_rest(ler=RestFalso([]))
    # a leitura da noite com a página curta: o catálogo, a paridade e a foto ficam como estavam, e o estado diz
    rel = AL.ler_completo(app, ler=RestFalso(_muitos(250), curta_em=100))
    assert AC.atual() is antes and AC.paridade_rest() is None and banco.syncs == 0
    assert "não veio inteira" in rel["resultado"] and AL.estado()["completo"]["resultado"] == rel["resultado"]
    assert AC.estado()["leitor"] is None                                          # o leitor não foi ligado neste teste


def test_429_espera_e_tenta(dormidas):
    rest = RestFalso(_muitos(250), recusas={100: 1})              # o Fracttal recusa a 2ª página uma vez
    itens = AL.ler_todos_rest(ler=rest)
    assert len(itens) == 250 and len(rest.paths) == 4                              # a mesma página pedida de novo
    assert AL.ESPERAS_RECUSA_S[0] in dormidas and AL.ESPERAS_RECUSA_S[0] >= 60     # o castigo de 1 min do Fracttal
    # recusada mais vezes do que as tentativas: a leitura falha (e, na da noite, não troca nada)
    with pytest.raises(fracttal.Recusado):
        AL.ler_todos_rest(ler=RestFalso(_muitos(250), recusas={100: 3}))


# ── os novos do dia ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_novos_param_na_pagina_conhecida(dormidas):
    base = _muitos(250)
    cat = _catalogo_de(base, lido_em=time.time() - 3600)
    maior = max(cat.por_id)
    novos = [_it(5000 + k, "CAL-GAM100-INVR9%d.1" % k, "Inversor 9%d.1    { x }" % k, 10) for k in range(3)]
    rest = RestFalso(base + novos)
    lidos = AL.ler_novos_rest(maior, ler=rest)
    assert sorted(i["id"] for i in lidos) == [5000, 5001, 5002]
    assert len(rest.paths) == 2 and all("sort=id:desc" in p for p in rest.paths)   # a 2ª página, inteira conhecida, encerra
    rest = RestFalso(base)                                                            # sem novidade: 1 pedido
    assert AL.ler_novos_rest(maior, ler=rest) == [] and len(rest.paths) == 1
    # o `sort` ignorado (a página vem do menor para o maior): "a página conhecida" não quer dizer nada
    with pytest.raises(AL.ForaDeOrdem):
        AL.ler_novos_rest(maior, ler=RestFalso(base + novos, ignora_sort=True))

    # quem soma ao catálogo: sem a leitura REST conferida (paridade), nada entra
    rel = AL.ler_novos(ler=RestFalso(base + novos))
    assert rel["acrescentados"] == 0 and "paridade" in rel["resultado"] and len(AC.atual().lista) == len(cat.lista)
    AC.anotar_paridade_rest({"vale": True, "motivo": "conferida", "em": time.time()})
    rel = AL.ler_novos(ler=RestFalso(base + novos, ignora_sort=True))                # fora de ordem: nada entra
    assert rel["acrescentados"] == 0 and "maior id para o menor" in rel["erro"] and AC.atual() is cat
    rel = AL.ler_novos(ler=RestFalso(base + novos))
    agora = AC.atual()
    assert rel["acrescentados"] == 3 and len(agora.lista) == len(cat.lista) + 3 and rel["pedidos"] == 2
    assert agora.lido_em == cat.lido_em and agora.fonte == cat.fonte                  # a lista inteira não foi conferida
    assert agora.novos_em > cat.lido_em and AC.visto_em(agora) == agora.novos_em
    assert agora.por_codigo["CAL-GAM100-INVR90.1"]["usina"] == GAMA                  # o caminho veio do pai no catálogo
    assert not api.catalogo_vencido(agora)


def test_novos_sem_pai_ficam_para_a_noite_e_vao_ao_disco(tmp_path):
    pasta = tmp_path / "oscreator"
    AC.reiniciar(pasta=str(pasta))
    cat = _catalogo_de(_muitos(120))
    AC.anotar_paridade_rest({"vale": True, "em": time.time()})
    novos = [_it(5000, "CAL-GAM100-INVR90.1", "Inversor 90.1    { x }", 10),
             _it(5001, "CAL-XYZ-INVR1.1", "Inversor solto    { x }", 4242)]           # o pai não está em lugar nenhum
    rel = AL.ler_novos(ler=RestFalso(_muitos(120) + novos))
    assert rel["acrescentados"] == 1 and rel["sem_pai"] == 1 and "leitura da noite" in rel["resultado"]
    novos_em = AC.atual().novos_em
    AC.reiniciar(pasta=str(pasta))                                                   # o reinício (um deploy)
    depois = AC.atual()
    assert len(depois.lista) == len(cat.lista) + 1 and depois.novos_em == novos_em and depois.lido_em == cat.lido_em
    assert AC.paridade_rest()["vale"]                                                # a paridade também volta do disco


# ── do REST ao registro ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_caminho_montado_pelos_pais():
    esperado = {r["code"]: r for r in AC.montar_registros(_rpc())}
    sem_pai = []
    cru = AL.para_registro(ARVORE, sem_pai=sem_pai)
    obtido = {r["code"]: r for r in AC.montar_registros(cru)}
    assert set(obtido) == set(esperado) and len(obtido) == 9 and sem_pai == []      # as raízes não entram no catálogo
    for code, rpc in esperado.items():
        for campo in ("id", "code", "description", "id_parent", "id_type_item", "cliente", "usina", "tipo_code", "tipo",
                      "parent_description", "label"):
            assert obtido[code][campo] == rpc[campo], (code, campo)
    caminho = {c["id"]: c["parent_description"] for c in cru}
    assert caminho[1] == "" and caminho[2] == ""                                     # a raiz fica no cru (a foto a guarda)
    assert obtido["BET-DEL100-INVR2.1"]["cliente"] == "Grupo Beta"                   # o nome da RAIZ, não o prefixo da usina

    # o caminho que o REST der vem como está
    com = [dict(i, parent_description="// Cliente Alfa/ Outro Nome/ ") if i["id"] == 31 else i for i in ARVORE]
    assert {c["id"]: c for c in AL.para_registro(com)}[31]["parent_description"] == "// Cliente Alfa/ Outro Nome/ "

    # o grupo de tarefas: o do item; senão o do catálogo pelo mesmo id; senão o da foto; senão None
    sem_grupo = [{k: v for k, v in i.items() if k != "id_group_task"} for i in ARVORE]
    AC.trocar(AC.montar_registros(_rpc()), "rpc")                                    # o catálogo de antes (o RPC) tem o 55
    foto = [{"fracttal_item_id": "10", "id_group_task": "7"}, {"fracttal_item_id": "30", "id_group_task": "99"}]
    grupo = {c["id"]: c["id_group_task"] for c in AL.para_registro(sem_grupo, catalogo=AC.atual(), foto=foto)}
    assert (grupo[30], grupo[10], grupo[31]) == (55, 7, None)
    grupo = {c["id"]: c["id_group_task"] for c in AL.para_registro(ARVORE, catalogo=None, foto=foto)}
    assert grupo[30] == 55                                                           # o do item vence o da foto

    # os novos do dia: o pai está no catálogo (não na página), e a raiz do cliente vem do próprio catálogo
    cat = AC.atual()
    novo = _it(40, "CAL-GAM100-INVR3.1", "Inversor 3.1 Marca X    { CAL-GAM100-INVR3.1 }", 21)
    orfao = _it(41, "CAL-SOLTO-INVR1.1", "Inversor solto", 999)
    usina_nova = _it(50, "CAL-NOV100", "Cliente Alfa - Usina Nova 3 - GO  Fazenda    { CAL-NOV100 }", 1, 1)
    inv_nova = _it(51, "CAL-NOV100-INVR1.1", "Inversor 1.1 Fazenda    { CAL-NOV100-INVR1.1 }", 50)
    sem_pai = []
    reg = {r["code"]: r for r in AC.montar_registros(AL.para_registro(
        [novo, orfao, usina_nova, inv_nova], catalogo=cat, pais_do_catalogo=True, sem_pai=sem_pai))}
    assert set(reg) == {"CAL-GAM100-INVR3.1", "CAL-NOV100", "CAL-NOV100-INVR1.1"} and sem_pai == [41]
    assert reg["CAL-GAM100-INVR3.1"]["parent_description"] == "// Cliente Alfa/ %s/ Cabine 2/ " % GAMA
    assert {c: (r["cliente"], r["usina"]) for c, r in reg.items() if c.startswith("CAL-NOV")} == {
        "CAL-NOV100": ("Cliente Alfa", "Cliente Alfa - Usina Nova 3 - GO"),
        "CAL-NOV100-INVR1.1": ("Cliente Alfa", "Cliente Alfa - Usina Nova 3 - GO")}


# ── a paridade ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_paridade_passa_e_falha(banco, app, monkeypatch):
    rpc = AC.montar_registros(_rpc())
    AC.trocar(rpc, "rpc", lido_em=time.time() - api.ASSETS_TTL - 3600)              # o catálogo do RPC, de ontem
    antes = AC.atual()
    reg = AC.montar_registros(AL.para_registro(ARVORE))
    vale, motivo, pct = AL.conferir_paridade(reg, antes.por_codigo)
    assert vale and pct == 100.0 and "9 códigos em comum" in motivo
    # outro cliente e usina em mais de 1% dos códigos
    torto = [dict(r, cliente="Outro") if r["code"] == "CAL-GAM100-INVR1.1" else r for r in reg]
    vale, motivo, pct = AL.conferir_paridade(torto, antes.por_codigo)
    assert not vale and pct < 99 and "mesmo cliente e usina" in motivo
    # o REST que não dá o tipo do item (a criação de OS precisa dele)
    vale, motivo, _ = AL.conferir_paridade([dict(r, id_type_item=None) for r in reg], antes.por_codigo)
    assert not vale and "id_type_item" in motivo
    # a que traz o dobro dos códigos (o que o catálogo não tem): os poucos em comum batendo não bastam
    dobro = reg + [dict(r, code=r["code"] + "-X", id=r["id"] + 900) for r in reg]
    assert not AL.conferir_paridade(dobro, antes.por_codigo)[0]
    # a que traz metade do catálogo: na 1ª conferência (a sondagem REST x RPC) não vale; depois dela, passa daqui e quem
    # decide é o catálogo, que recusa o encolhimento até duas leituras o confirmarem
    vale, motivo, _ = AL.conferir_paridade(reg[:4], antes.por_codigo, primeira=True)
    assert not vale and "1ª conferência" in motivo
    assert AL.conferir_paridade(reg[:4], antes.por_codigo)[0]
    assert not AL.conferir_paridade(reg, {})[0] and not AL.conferir_paridade([], antes.por_codigo)[0]

    # A NOITE EM QUE A PARIDADE FALHA (o REST sem o tipo do item): nada troca, a foto não é gravada, o estado diz
    sem_tipo = [{k: v for k, v in i.items() if k != "id_type_item"} for i in ARVORE]
    rel = AL.ler_completo(app, ler=RestFalso(sem_tipo))
    assert AC.atual() is antes and banco.syncs == 0
    assert AC.paridade_rest()["vale"] is False and "id_type_item" in AC.paridade_rest()["motivo"]
    assert AC.paridade_rest()["contra"] == "rpc" and "segue pelo RPC" in rel["resultado"]
    # ... e o catálogo segue pelo RPC: o leitor ligado não está pronto, e o vencido é renovado por trás, uma vez
    pediu = []
    AC.ligar_leitor(pedir_novos=lambda: pediu.append(1) or True, esperar_novos=lambda t, s: True, estado=AL.estado)
    assert not AC.leitor_pronto()
    baixou = []
    monkeypatch.setattr(api, "get_assets", lambda: baixou.append(1) or AC.montar_registros(_rpc()))
    assert api.load_assets_cached() is antes.lista                                  # o de ontem na hora
    fim = time.monotonic() + 5
    while api._ASSETS_RECARGA.locked() or any(t.name == "os-catalogo-por-tras" for t in threading.enumerate()):
        assert time.monotonic() < fim
        time.sleep(0.02)
    assert baixou == [1] and pediu == [] and not api.catalogo_vencido(AC.atual())
    api.load_assets_cached()
    assert baixou == [1]                                                            # renovado: o próximo, só em 24 h


def test_a_noite_que_vale_troca_o_catalogo_e_renova_a_foto(banco, app):
    AC.trocar(AC.montar_registros(_rpc()), "rpc", lido_em=time.time() - 7200)
    rel = AL.ler_completo(app, ler=RestFalso(ARVORE))
    assert rel["resultado"].startswith("a mesma lista") and rel["pedidos"] == 1 and rel["itens"] == len(ARVORE)
    assert AC.paridade_rest()["vale"] and AC.atual().fonte == "rest" and time.time() - AC.atual().lido_em < 60
    assert rel["foto"]["gravou"] and banco.syncs == 1
    linhas = banco.linhas(eq.LIVRO_FOTO, eq.ABA_FOTO)
    assert len(linhas) == len(ARVORE) and sum(1 for l in linhas if l["pai_item_id"] is None) == 2     # as raízes
    por_id = {int(l["fracttal_item_id"]): l for l in linhas}
    assert (por_id[30]["tipo_fracttal"], por_id[30]["id_group_task"], por_id[30]["id_type_item"]) == ("INVR", "55", "2")
    assert por_id[30]["descricao"] == "Inversor 1.1 Marca X"                         # sem o "{ CÓDIGO }" repetido
    # a foto renovada serve de catálogo (a máquina sem cópia nenhuma): o mesmo cliente e usina, e nasce vencida
    registros, _ = AF.registros_da_foto(linhas)
    assert {r["code"]: (r["cliente"], r["usina"]) for r in registros} == {
        r["code"]: (r["cliente"], r["usina"]) for r in AC.atual().lista}
    assert all(r["id_type_item"] is not None for r in registros)
    AC.reiniciar()
    AC.ligar_fonte_do_banco(lambda: linhas)
    assert AC.garantir().fonte == "banco" and api.catalogo_vencido(AC.atual())
    # a noite seguinte, com o mesmo Fracttal: nada muda na foto, nada se grava
    AC.trocar(AC.montar_registros(_rpc()), "rpc")
    rel = AL.ler_completo(app, ler=RestFalso(ARVORE))
    assert rel["foto"]["gravou"] is False and banco.syncs == 1


def test_a_foto_so_grava_depois_que_o_catalogo_aceita(banco, app):
    _catalogo_de(_muitos(300))
    AC.anotar_paridade_rest({"vale": True, "em": time.time()})
    # a leitura que encolhe mais de 5% (inteira e coerente, mas com 40 ativos a menos): a paridade passa e o catálogo recusa
    rel = AL.ler_completo(app, ler=RestFalso(_muitos(260)))
    assert "recusou" in rel["resultado"] and "encolheu" in rel["resultado"] and AC.paridade_rest()["vale"]
    assert len(AC.atual().lista) == 299 and banco.syncs == 0 and rel["foto"] is None
    assert AC.recusa_vigente()["fonte"] == "rest"                    # lembrada: a próxima leitura igual a confirma
    # na 1ª conferência (o REST ainda não valeu), a mesma leitura nem chega ao catálogo: a paridade não deixa
    AC.anotar_paridade_rest(None)
    rel = AL.ler_completo(app, ler=RestFalso(_muitos(260)))
    assert "1ª conferência" in rel["resultado"] and banco.syncs == 0


# ── a foto do banco ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _antigas():
    """A foto da carga única de 11/10 como o banco a devolve (só as 6 colunas, tudo texto): a de 22/09 e um código de junho."""
    linhas = [["10", "CAL-GAM100", "Cliente Alfa - Usina Gama 1 - PA  Zona Rural km 4", "1", "USINA", "2026-09-22"],
              ["30", "CAL-GAM100-INVR1.1", "Inversor 1.1 Marca X", "25", "INVR", "2026-09-22"],
              ["31", "CAL-GAM100-INVR1.2", "Inversor 1.2 Marca X", "10", "INVR", "2026-09-22"],
              ["34", "CAL-GAM100-INVR9.9", "Inversor 9.9 baixado", "21", "INVR", "2026-09-22"],
              ["77", "CAL-VELHO100-INVR1.1", "Inversor velho", "10", "INVR", "2026-06-21"]]
    return [dict(zip(eq.CAB_FOTO[:6], l)) for l in linhas]


def _novas(itens=ARVORE):
    cru = AL.para_registro(itens)
    tipo = {r["id"]: r["tipo_code"] for r in AC.montar_registros(cru)}
    return [FA.linha_do_item(c, tipo.get(c["id"])) for c in cru]


def test_foto_guarda_o_codigo_que_saiu():
    hoje = date(2026, 10, 31)
    linhas, rel = FA.renovar(_antigas(), _novas(), hoje)
    d = {(l[0], l[1]): dict(zip(FA.CAB_FOTO, l)) for l in linhas}
    assert len(linhas) == len(ARVORE) + 2                         # nada sai: os dois que o Fracttal não tem ficam
    assert d[(34, "CAL-GAM100-INVR9.9")]["fora_do_fracttal_desde"] == 20261031      # saiu agora
    assert d[(77, "CAL-VELHO100-INVR1.1")]["fora_do_fracttal_desde"] == 20260922    # já não estava na foto de 22/09
    assert d[(30, "CAL-GAM100-INVR1.1")]["fora_do_fracttal_desde"] is None
    assert d[(1, "CAL")]["pai_item_id"] is None and d[(1, "CAL")]["descricao"] == "Cliente Alfa"   # a raiz entra
    assert rel["sairam"] == 2 and rel["fora_do_fracttal"] == 2 and rel["entraram"] == len(ARVORE) - 3
    assert {l[eq.CAB_FOTO.index("foto_em")] for l in linhas} == {"2026-10-31"}       # as colunas novas mudaram todas as linhas

    # o código que voltou ao Fracttal perde a marca; o que segue fora fica como estava (a mesma linha, o mesmo dia)
    antigas = [dict(zip(FA.CAB_FOTO, l)) for l in linhas]
    volta = ARVORE + [_it(34, "CAL-GAM100-INVR9.9", "Inversor 9.9 baixado    { CAL-GAM100-INVR9.9 }", 21)]
    linhas2, rel2 = FA.renovar(antigas, _novas(volta), date(2026, 11, 5))
    d2 = {(l[0], l[1]): dict(zip(FA.CAB_FOTO, l)) for l in linhas2}
    assert d2[(34, "CAL-GAM100-INVR9.9")]["fora_do_fracttal_desde"] is None and rel2["voltaram"] == 1
    assert d2[(34, "CAL-GAM100-INVR9.9")]["foto_em"] == "2026-11-05"
    assert d2[(77, "CAL-VELHO100-INVR1.1")] == d[(77, "CAL-VELHO100-INVR1.1")]
    assert d2[(30, "CAL-GAM100-INVR1.1")]["foto_em"] == "2026-10-31"                  # não mudou: o dia de antes
    # o item renomeado: o código velho fica (marcado), o novo entra, com o mesmo item
    renomeado = [dict(i, code="CAL-GAM100-INVR1.9") if i["id"] == 31 else i for i in ARVORE]
    d3 = {(l[0], l[1]): dict(zip(FA.CAB_FOTO, l)) for l in FA.renovar(antigas, _novas(renomeado), date(2026, 11, 6))[0]}
    assert d3[(31, "CAL-GAM100-INVR1.2")]["fora_do_fracttal_desde"] == 20261106
    assert d3[(31, "CAL-GAM100-INVR1.9")]["fora_do_fracttal_desde"] is None
    # e a dimensão de equipamento: o código que saiu segue membro (os fatos antigos ligam por ele), a raiz não
    dim = {m[1] for m in eq.membros([dict(zip(FA.CAB_FOTO, l)) for l in linhas], {}, [])}
    assert {"CAL-GAM100-INVR9.9", "CAL-VELHO100-INVR1.1"} <= dim and "CAL" not in dim and "GBE" not in dim


def test_foto_so_grava_quando_muda():
    pg = ApiPGFalsa(como_texto=True)
    rel = FA.gravar(_novas(), base=BASE, token="t", sessao=pg, maquina="servidor", hoje=date(2026, 10, 31))
    assert rel["gravou"] and pg.syncs == 1 and rel["conferido"][eq.ABA_FOTO] == len(ARVORE)
    atualizacao = pg.linhas(eq.LIVRO_FOTO, "atualizacao")
    assert len(atualizacao) == 1 and atualizacao[0]["sha_linhas"] == rel["sha_linhas"]
    # a mesma leitura no dia seguinte (o banco devolve tudo como texto): o mesmo sha, nada se grava
    rel = FA.gravar(_novas(), base=BASE, token="t", sessao=pg, maquina="servidor", hoje=date(2026, 11, 1))
    assert rel["gravou"] is False and pg.syncs == 1 and rel["iguais"] == len(ARVORE)
    # uma descrição mudou: grava, e só aquela linha ganha o dia
    mudou = [dict(i, description="Inversor 1.1 Marca Y    { x }") if i["id"] == 30 else i for i in ARVORE]
    rel = FA.gravar(_novas(mudou), base=BASE, token="t", sessao=pg, maquina="servidor", hoje=date(2026, 11, 2))
    assert rel["gravou"] and rel["mudaram"] == 1 and pg.syncs == 2
    dias = {int(l["fracttal_item_id"]): l["foto_em"] for l in pg.linhas(eq.LIVRO_FOTO, eq.ABA_FOTO)}
    assert dias[30] == "2026-11-02" and dias[31] == "2026-10-31"
    # a leitura do banco que não veio inteira não grava por cima (apagaria os códigos que saíram do Fracttal)
    pg.omitir.add(eq.LIVRO_FOTO)
    with pytest.raises(FA.LeituraCurta):
        FA.gravar(_novas(), base=BASE, token="t", sessao=pg, maquina="servidor", hoje=date(2026, 11, 3))
    pg.omitir.clear()
    pg._id(eq.LIVRO_FOTO, eq.ABA_FOTO)["linhas"].append(
        {"headers": list(eq.CAB_FOTO), "values": ["999", "CAL-X", "x", "10", None, "2026-01-01", None, None, None]})
    real = livros._linhas
    with pytest.MonkeyPatch.context() as m:                     # o banco diz N linhas e a leitura traz N-1
        m.setattr(livros, "_linhas", lambda b, s, sid: real(b, s, sid)[:-1])
        with pytest.raises(FA.LeituraCurta):
            FA.gravar(_novas(), base=BASE, token="t", sessao=pg, maquina="servidor", hoje=date(2026, 11, 3))
    assert pg.syncs == 2
    with pytest.raises(RuntimeError, match="GRIDCO_SQL_TOKEN"):
        FA.gravar(_novas(), base=BASE, token="", sessao=pg, maquina="servidor")


def test_a_foto_tem_as_colunas_novas_no_fim_e_o_livro_so_cresce():
    from nexus.dados import catalogo
    assert eq.CAB_FOTO[:6] == ["fracttal_item_id", "codigo", "descricao", "pai_item_id", "tipo_fracttal", "foto_em"]
    assert eq.CAB_FOTO[6:] == ["id_type_item", "id_group_task", "fora_do_fracttal_desde"]
    assert tuple(eq.CAB_FOTO) == AF.CAB_FOTO == AC.CAB_FOTO
    livro = catalogo.LIVRO_POR_NOME[eq.LIVRO_FOTO]
    assert livro.so_cresce == livro.abas and "ativos_leitor" in livro.quem_grava and "02:15" in livro.cadencia
    assert "fora_do_fracttal_desde" in catalogo.ABAS_FORA_DA_REGRA["foto_ativos"]


def test_a_ferramenta_so_mede():
    texto = (AQUI / "ferramentas" / "carregar_ativos_fracttal.py").read_text(encoding="utf-8")
    assert "livros.publicar" not in texto and "foto_ativos" in texto and "uma máquina grava" in texto


# ── o encolhimento confirmado ───────────────────────────────────────────────────────────────────────────────────────────
def _lote(n, primeiro=1000):
    """n registros do catálogo (a usina e n-1 inversores: a raiz do cliente não entra no catálogo)."""
    return AC.montar_registros(AL.para_registro(_muitos(n + 1, primeiro)))


def test_encolhimento_confirmado_por_duas_leituras(tmp_path):
    pasta = str(tmp_path / "oscreator")
    AC.reiniciar(pasta=pasta)
    t0 = time.time()
    assert AC.trocar(_lote(100), "rpc", lido_em=t0 - 90000)
    assert not AC.trocar(_lote(80), "rest", lido_em=t0 - 80000)               # 1ª: recusada e lembrada
    assert not AC.trocar(_lote(80), "rest", lido_em=t0 - 76400)               # o mesmo caminho 1 h depois: ainda não
    AC.reiniciar(pasta=pasta)                                                  # o reinício (um deploy) não a esquece
    assert AC.recusa_vigente()["n_novo"] == 80 and len(AC.atual().lista) == 100
    assert AC.trocar(_lote(80), "rpc", lido_em=t0 - 70000)                     # o outro caminho, os mesmos que saem: entra
    assert len(AC.atual().lista) == 80 and "encolhimento confirmado" in AC.estado()["encolhimento"]["motivo"]

    # outros ativos saindo não confirmam
    AC.reiniciar(pasta=str(tmp_path / "outra"))
    assert AC.trocar(_lote(100), "rpc", lido_em=t0 - 90000)
    assert not AC.trocar(_lote(80), "rest", lido_em=t0 - 80000)
    assert not AC.trocar(_lote(80, primeiro=1020), "rpc", lido_em=t0 - 70000)
    assert len(AC.atual().lista) == 100 and AC.estado()["encolhimento"] is None

    # o mesmo caminho com 20 h ou mais entre as duas, e com os novos do dia entrando no meio
    AC.reiniciar(pasta=str(tmp_path / "terceira"))
    assert AC.trocar(_lote(100), "rpc", lido_em=t0 - 200000)
    assert not AC.trocar(_lote(80), "rest", lido_em=t0 - 100000)
    novo = AC.montar_registros(AL.para_registro(_muitos(2) + [_it(9000, "CAL-GAM100-INVR99.9", "Inversor novo", 10)]))
    assert AC.acrescentar([r for r in novo if r["id"] == 9000], "rest") == 1
    lido = AC.montar_registros(AL.para_registro(_muitos(81) + [_it(9000, "CAL-GAM100-INVR99.9", "Inversor novo", 10)]))
    assert AC.trocar(lido, "rest", lido_em=t0 - 100000 + AC.CONFIRMA_MESMO_CAMINHO_S)
    assert len(AC.atual().lista) == 81 and AC.estado()["encolhimento"]["para"] == 81


def test_a_leitura_feita_agora_nunca_e_velha():
    """A recusa "velha" depende do relógio de parede: só vale para a data escrita (a foto do banco, o disco)."""
    t0 = time.time()
    assert AC.trocar(_lote(20), "rpc", lido_em=t0)
    assert AC.trocar(_lote(21), "rest", lido_em=t0 - 5)                       # o REST que terminou antes: entra
    assert len(AC.atual().lista) == 21
    assert not AC.trocar(_lote(22), "banco", lido_em=t0 - 3600)               # a foto de ontem: velha
    assert "mais velha" in AC.estado()["recusa"]["motivo"]


# ── a falha do download e quem esperava a vez ───────────────────────────────────────────────────────────────────────────
def test_a_falha_do_download_vale_para_quem_esperava_a_vez(monkeypatch):
    AC.trocar(_lote(50), "rpc", lido_em=time.time() - api.ASSETS_TTL - 3600)     # vencido
    tentou = []

    def get_assets():
        tentou.append(1)
        time.sleep(0.3)
        raise api.FracttalError("HTTP 429")
    monkeypatch.setattr(api, "get_assets", get_assets)
    largada = threading.Barrier(4)
    saidas, erros = [], []

    def pedido():
        largada.wait(5)
        try:
            saidas.append(api.load_assets_cached(em_dia=True))
        except api.FracttalError as e:
            erros.append(e)
    ts = [threading.Thread(target=pedido) for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert tentou == [1] and len(erros) == 1 and len(saidas) == 3 and all(len(s) == 50 for s in saidas)
    assert AC.estado()["falha"]["fonte"] == "rpc" and "429" in AC.estado()["falha"]["erro"]
    assert len(api.load_assets_cached(True)) == 50 and tentou == [1]             # o botão na janela: não tenta de novo
    AC.reiniciar()                                                             # sem catálogo nenhum: o erro, sem tentar
    AC.anotar_falha("rpc", api.FracttalError("HTTP 429"))
    with pytest.raises(api.FracttalError, match="há pouco"):
        api.load_assets_cached(em_dia=True)
    assert tentou == [1]


# ── só o servidor liga, e sem a credencial não liga ─────────────────────────────────────────────────────────────────────
def test_sem_credencial_o_leitor_nao_liga(app):
    AL.ligar(app)
    e = AL.estado()
    assert e["ligado"] is False and "credencial" in e["motivo"] and AC.estado()["leitor"]["motivo"] == e["motivo"]
    assert not AC.leitor_pronto() and not AC.pedir_novos()
    assert not any(t.name == "nexus-ativos-leitor" for t in threading.enumerate())


def test_com_credencial_liga_sem_laco_nos_testes(app):
    app.config["NEXUS_PCM_FRACTTAL_TESTE"] = {"FRACTTAL_CLIENT_ID": "id-de-mentira", "FRACTTAL_CLIENT_SECRET": "s"}
    AL.ligar(app)
    AL.ligar(app)                                                              # de novo: nada
    assert AL.estado()["ligado"] and AL.estado()["credencial"] == "teste"
    assert not AC.leitor_pronto()                                              # sem a paridade da 1ª noite, não está pronto
    AC.anotar_paridade_rest({"vale": True, "em": time.time()})
    assert AC.leitor_pronto()
    assert not any(t.name == "nexus-ativos-leitor" for t in threading.enumerate())


def test_o_servidor_liga_o_leitor_e_o_pc_nao():
    texto = (AQUI / "servir.py").read_text(encoding="utf-8")
    assert 'ligar_leitor_do_clone(app, "ativos_leitor")' in texto and "ativos_leitor.ligar(" not in texto
    assert texto.index("fracttal_conta.ligar()") < texto.index('ligar_leitor_do_clone(app, "ativos_leitor")')   # o contador vê os pedidos
    for arquivo in ("app.py", "nexus/__init__.py", "nexus/torres/oscreator/ponte.py"):
        assert "ativos_leitor.ligar(" not in (AQUI / arquivo).read_text(encoding="utf-8"), arquivo


def test_proximo_passo_noite_e_dia():
    def em(h, m):
        return datetime(2026, 10, 31, h, m, tzinfo=_BRT).timestamp()
    assert AL.proximo_passo(em(1, 0)) == (75 * 60, AL.COMPLETO)                 # 02:15
    assert AL.proximo_passo(em(2, 15)) == (3 * 3600 + 53 * 60, AL.NOVOS)        # depois dele, 06:08
    assert AL.proximo_passo(em(6, 8)) == (30 * 60, AL.NOVOS)                    # 06:38
    assert AL.proximo_passo(em(21, 38)) == (4 * 3600 + 37 * 60, AL.COMPLETO)    # depois das 21:38, as 02:15 do outro dia


def test_o_resultado_da_noite_sobrevive_ao_reinicio(banco, app, tmp_path):
    """Revisão final: o relatório da leitura inteira (`estado()["completo"]`) só vive na memória do leitor, e o deploy de várias
    vezes por dia o apagava antes de o Levi, que não tem acesso ao servidor, olhar o Raio-X. O resultado (a hora, se o catálogo
    trocou, os pedidos, a foto do banco) vai ao `ativos_estado.json`; só contagens, horas e motivos."""
    pasta = str(tmp_path / "oscreator")
    AC.reiniciar(pasta=pasta)
    AC.trocar(AC.montar_registros(_rpc()), "rpc", lido_em=time.time() - 7200)
    rel = AL.ler_completo(app, ler=RestFalso(ARVORE))
    noite = AC.estado()["noite"]
    assert noite["ok"] and noite["pedidos"] == 1 and noite["itens"] == len(ARVORE) and noite["registros"] == len(AC.atual().lista)
    assert noite["inicio"] == rel["inicio"] and noite["fim"] == rel["fim"] and noite["resultado"].startswith("a mesma lista")
    assert noite["foto"]["gravou"] is True and noite["foto"]["linhas"] == len(ARVORE) and "erro" not in noite["foto"]
    # o reinício (um deploy): a memória do leitor se vai, o resultado volta do disco
    AC.reiniciar(pasta=pasta)
    AL.reiniciar()
    assert AL.estado()["completo"] is None
    assert AC.estado()["noite"] == noite
    # a noite que não trocou nada (a paridade falha) também fica, com o motivo
    sem_tipo = [{k: v for k, v in i.items() if k != "id_type_item"} for i in ARVORE]
    AC.trocar(AC.montar_registros(_rpc()), "rpc", lido_em=time.time() - 7200)
    AL.ler_completo(app, ler=RestFalso(sem_tipo))
    AC.reiniciar(pasta=pasta)
    AL.reiniciar()
    falhou = AC.estado()["noite"]
    assert not falhou["ok"] and "id_type_item" in falhou["resultado"] and falhou["foto"] is None
    # a leitura que não veio inteira: nada mudou, e o motivo fica
    AC.trocar(AC.montar_registros(_rpc()), "rpc", lido_em=time.time() - 7200)
    AL.ler_completo(app, ler=RestFalso(_muitos(250), curta_em=100))
    AC.reiniciar(pasta=pasta)
    assert not AC.estado()["noite"]["ok"] and "não veio inteira" in AC.estado()["noite"]["resultado"]
    # nada de texto de ativo no arquivo
    import json
    texto = (tmp_path / "oscreator" / "ativos_estado.json").read_text(encoding="utf-8")
    assert "noite" in json.loads(texto) and "Inversor 1.1" not in texto and "Cliente Alfa" not in texto
