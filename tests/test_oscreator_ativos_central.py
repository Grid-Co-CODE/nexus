"""O catálogo de ativos central do OS Creator: UM para todas as telas (31/10/2026, etapa 2 do canto central; Levi, 30/10:
"a ideia é não ter um carregamento novo por atividade e sim um ecossistema onde as coisas se aproveitam e não precisamos
ficar fazendo novas requisições sempre!").

O que estes testes seguram (o módulo é `os_creator/ativos_central.py`):
- as telas leem o catálogo SEM pedir nada ao Fracttal (um Fracttal falso que conta), inclusive depois de um reinício;
- o boot vem, em ordem, da cópia em disco, do `assets_cache.json` antigo (migrado uma vez) e da foto do banco; a cópia ilegível
  é ignorada; a foto sem a raiz de cada cliente (a de verdade, de 22/09) é recusada, e a que a tem monta o MESMO cliente, usina
  e caminho que o RPC dá (a comparação é com os registros no formato do RPC, de caminho conhecido);
- o registro é só de leitura (TypeError), a cópia é `registro(codigo)`, e a busca por código usa o índice (sem varrer);
- a troca recusa a lista vazia e a que encolhe mais de 5%, e a mesma lista lida de novo só renova a hora.
Fracttal, banco e disco são dublês ou pastas de teste: nada vai à rede. Nomes, códigos e usinas são de mentira (repositório
público)."""
import json
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
import ativos_central as AC  # noqa: E402
from os_web import criar_app, rotas_solic as rs  # noqa: E402
from os_web import tradicional_web as trad  # noqa: E402

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira


def _reg(i, code, cliente="Cliente Alfa", usina="Cliente Alfa - Usina Gama 1 - PA", tipo="Inversor", **mais):
    r = {"id": i, "code": code, "description": "%s %d" % (tipo, i), "id_parent": 1, "id_type_item": 2, "id_group_task": None,
         "parent_description": "// %s/ %s/ " % (cliente, usina), "cliente": cliente, "usina": usina, "tipo_code": "INVR",
         "tipo": tipo, "label": "%s — %s %d" % (code, tipo, i)}
    r.update(mais)
    return r


def _lote(n, **kw):
    """n registros de mentira, com ids e códigos diferentes."""
    return [_reg(1000 + i, "CAL-GAM100-INVR%d.%d" % (i // 10, i % 10), **kw) for i in range(n)]


@pytest.fixture(autouse=True)
def _limpo():
    AC.reiniciar()
    yield
    AC.reiniciar()


class FracttalFalso:
    """Conta cada ida ao Fracttal, por qualquer porta (RPC, REST e o download dos ativos), e derruba o teste que a fizer."""

    def __init__(self, monkeypatch):
        import requests
        self.pedidos = []

        def conta(nome):
            def f(*a, **k):
                self.pedidos.append(nome)
                raise AssertionError("o teste pediu ao Fracttal: " + nome)
            return f
        for nome in ("post", "get", "request"):
            monkeypatch.setattr(requests, nome, conta("requests." + nome))
        monkeypatch.setattr(requests.Session, "request", conta("Session.request"))
        for nome in ("_rpc_call", "_rpc_chamar", "_req", "get_assets"):
            monkeypatch.setattr(api, nome, conta("api." + nome))


@pytest.fixture
def fracttal(monkeypatch):
    return FracttalFalso(monkeypatch)


# ── as telas leem sem pedir nada ao Fracttal ────────────────────────────────────────────────────────────────────────────
def test_telas_leem_sem_pedir_ao_fracttal(fracttal, tmp_path):
    pasta = str(tmp_path / "oscreator")
    AC.reiniciar(pasta=pasta)
    assert AC.trocar(_lote(12) + [_reg(2000, "CBE-DEL100-INVR1.1", cliente="Cliente Beta",
                                       usina="Cliente Beta - Usina Delta 2 - BA")], "rpc")
    AC.reiniciar(pasta=pasta)            # o REINÍCIO (cada push na main): só a cópia em disco e a memória, nenhum pedido

    lista = api.load_assets_cached()
    assert len(lista) == 13 and lista is api.load_assets_cached()
    assert api._asset_by_code("CBE-DEL100-INVR1.1")["usina"] == "Cliente Beta - Usina Delta 2 - BA"
    assert api._code_to_loc()["CBE-DEL100-INVR1.1"] == ("Cliente Beta", "Usina Delta 2", "Inversor")
    assert api.assets_cache_info()["n"] == 13 and api._read_asset_cache() is lista
    # a cascata do Criar OS e da Nova solicitação
    ativos = trad.ativos_do_cliente(lista, "Cliente Alfa")
    assert len(ativos) == 12 and {a["usina"] for a in ativos} == {"Cliente Alfa - Usina Gama 1 - PA"}
    assert trad.usinas_de(lista, "Cliente Beta") == ["Cliente Beta - Usina Delta 2 - BA"]
    assert trad.tipos_de(lista, "Cliente Beta", "Cliente Beta - Usina Delta 2 - BA") == ["Inversor"]
    assert [a["code"] for a in trad.ativos_de(lista, "Cliente Beta", "Cliente Beta - Usina Delta 2 - BA")] == [
        "CBE-DEL100-INVR1.1"]
    # o índice da Solicitação (as páginas do PCM)
    cat = rs._indice_ativos()
    assert rs._tipo_do_ativo({"id_item": 2000}, cat) == "Inversor"
    assert rs._tipo_do_ativo({"code": " CAL-GAM100-INVR0.1 "}, cat) == "Inversor"
    assert rs._tipo_do_ativo({"code": "NAO-EXISTE"}, cat) is None and cat.tipos == (("Inversor", 13),)
    assert fracttal.pedidos == []


def test_a_tela_da_cascata_le_o_catalogo_sem_pedir_ao_fracttal(fracttal):
    AC.trocar(_lote(5) + [_reg(2000, "CBE-DEL100-INVR1.1", cliente="Cliente Beta", usina="Cliente Beta - Usina Delta 2 - BA")],
              "rpc")
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid", "perfil": "ADMINISTRATOR"}
    r = c.get("/os/api/tradicional/catalogo?cliente=Cliente%20Alfa&ativos=1")
    assert r.status_code == 200
    j = r.get_json()
    assert j["usinas"] == ["Cliente Alfa - Usina Gama 1 - PA"] and len(j["ativos"]) == 5
    assert fracttal.pedidos == []


def test_sem_catalogo_nenhum_o_indice_da_solicitacao_e_vazio_e_nao_pede_nada(fracttal):
    cat = rs._indice_ativos()
    assert cat is AC.VAZIO and rs._tipo_do_ativo({"code": "X"}, cat) is None and cat.tipos == ()
    assert fracttal.pedidos == []


# ── o boot: disco, arquivo antigo, banco ────────────────────────────────────────────────────────────────────────────────
def test_boot_pelo_disco_e_pelo_banco(tmp_path):
    pasta, legado = str(tmp_path / "oscreator"), tmp_path / "assets_cache.json"
    chamadas = []
    AC.reiniciar(pasta=pasta, legado=str(legado))
    AC.ligar_fonte_do_banco(lambda: chamadas.append(1) or FOTO)

    # 1) sem nada em lugar nenhum e com a foto de verdade (sem a raiz): o catálogo fica por conta do Fracttal
    assert AC.atual() is None and AC.garantir() is None and AC.estado()["n"] == 0
    assert chamadas == [1] and "raiz" in AC.estado()["banco"]["motivo"]

    # 2) o arquivo antigo: lido uma vez, e já vira a cópia nova
    legado.write_text(json.dumps({"ts": 1790000000.0, "ver": 2, "assets": _lote(10)}), encoding="utf-8")
    AC.reiniciar(pasta=pasta, legado=str(legado))
    AC.ligar_fonte_do_banco(lambda: chamadas.append(2) or FOTO_COM_RAIZ)
    cat = AC.atual()
    assert cat is not None and cat.fonte == "disco" and len(cat.lista) == 10 and cat.lido_em == 1790000000.0
    assert (tmp_path / "oscreator" / AC.NOME_ARQUIVO).exists() and chamadas == [1]

    # 3) o reinício seguinte vem da cópia nova, mesmo sem o arquivo antigo, e NÃO lê o banco
    legado.unlink()
    AC.reiniciar(pasta=pasta, legado=str(legado))
    AC.ligar_fonte_do_banco(lambda: chamadas.append(3) or FOTO_COM_RAIZ)
    de_novo = AC.garantir()
    assert de_novo.fonte == "disco" and de_novo.versao == cat.versao and de_novo.lido_em == cat.lido_em
    assert chamadas == [1]

    # 4) sem a cópia e sem o arquivo antigo, a foto do banco (a que tem a raiz) enche o catálogo
    (tmp_path / "oscreator" / AC.NOME_ARQUIVO).unlink()
    AC.reiniciar(pasta=pasta, legado=str(legado))
    AC.ligar_fonte_do_banco(lambda: chamadas.append(4) or FOTO_COM_RAIZ)
    assert AC.atual() is None                                     # `atual()` nunca vai ao banco
    banco = AC.garantir()
    assert banco.fonte == "banco" and chamadas == [1, 4] and {r["cliente"] for r in banco.lista} == {
        "Cliente Alfa", "Grupo Beta"}
    assert banco.lido_em == FOTO_EM                               # a data da foto (22/09), e não a de agora: já nasce vencido
    assert not (tmp_path / "oscreator" / AC.NOME_ARQUIVO).exists()  # a foto aproximada não vira a cópia em disco


def test_o_disco_vale_mais_que_o_arquivo_antigo(tmp_path):
    pasta = str(tmp_path / "oscreator")
    AC.reiniciar(pasta=pasta)
    AC.trocar(_lote(10), "rpc", lido_em=1791000000.0)
    legado = tmp_path / "assets_cache.json"
    legado.write_text(json.dumps({"ts": 1.0, "ver": 2, "assets": _lote(3)}), encoding="utf-8")
    AC.reiniciar(pasta=pasta, legado=str(legado))
    assert len(AC.atual().lista) == 10 and AC.atual().lido_em == 1791000000.0


def test_boot_com_varios_pedidos_juntos_le_o_disco_uma_vez(tmp_path, monkeypatch):
    pasta = str(tmp_path / "oscreator")
    AC.reiniciar(pasta=pasta)
    AC.trocar(_lote(50), "rpc")
    AC.reiniciar(pasta=pasta)
    lidos = []
    original = json.load
    monkeypatch.setattr(AC.json, "load", lambda f: lidos.append(1) or original(f))
    saidas = []
    ts = [threading.Thread(target=lambda: saidas.append(AC.atual())) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert lidos == [1] and len({id(s) for s in saidas}) == 1 and saidas[0] is not None


def test_disco_corrompido_ignorado(tmp_path):
    pasta = tmp_path / "oscreator"
    pasta.mkdir()
    arq = pasta / AC.NOME_ARQUIVO
    AC.reiniciar(pasta=str(pasta))
    AC.trocar(_lote(10), "rpc")
    bom = arq.read_bytes()
    import gzip
    estragos = {
        "lixo": b"isto nao e um gzip",
        "gzip cortado no meio": bom[: len(bom) // 2],
        "json cortado": gzip.compress(b'{"formato": 1, "registros": [{"id": 1'),
        "outro formato": gzip.compress(json.dumps({"formato": 99, "registros": _lote(3), "lido_em": 1.0}).encode()),
        "sem registros": gzip.compress(json.dumps({"formato": 1, "registros": [], "lido_em": 1.0}).encode()),
        "registros que nao sao registros": gzip.compress(json.dumps({"formato": 1, "registros": [1, 2], "lido_em": 1.0}).encode()),
        "vazio": b"",
    }
    for nome, conteudo in estragos.items():
        arq.write_bytes(conteudo)
        AC.reiniciar(pasta=str(pasta))
        assert AC.atual() is None, nome                          # ignorada: sem exceção e sem catálogo
        assert AC.estado()["disco"]["erro"], nome                # e o motivo fica à vista
    # a ilegível não impede o catálogo de nascer do que vier depois (o download), e a cópia nova a substitui
    AC.reiniciar(pasta=str(pasta))
    assert AC.trocar(_lote(10), "rpc") and arq.read_bytes()[:2] == b"\x1f\x8b"
    AC.reiniciar(pasta=str(pasta))
    assert len(AC.atual().lista) == 10


def test_a_copia_em_disco_e_gravada_de_uma_vez_e_sem_sobra(tmp_path):
    pasta = tmp_path / "oscreator"
    AC.reiniciar(pasta=str(pasta))
    AC.trocar(_lote(10), "rpc")
    AC.trocar(_lote(11), "rpc")
    assert sorted(p.name for p in pasta.iterdir()) == [AC.NOME_ARQUIVO]          # nenhum .tmp esquecido
    # pasta que não dá para criar: o catálogo segue na memória e o motivo vai para o estado
    arquivo = tmp_path / "e_um_arquivo"
    arquivo.write_text("x")
    AC.reiniciar(pasta=str(arquivo / "oscreator"))
    assert AC.trocar(_lote(10), "rpc") and len(AC.atual().lista) == 10 and "gravar" in AC.estado()["disco"]["erro"]


def test_so_o_que_veio_do_fracttal_vai_para_o_disco(tmp_path):
    pasta = tmp_path / "oscreator"
    AC.reiniciar(pasta=str(pasta))
    assert AC.trocar(_lote(10), "banco") and not (pasta / AC.NOME_ARQUIVO).exists()
    assert AC.trocar(_lote(10), "rest") and (pasta / AC.NOME_ARQUIVO).exists()
    with pytest.raises(ValueError):
        AC.trocar(_lote(10), "planilha")


# ── o registro (só leitura), a cópia e o índice ─────────────────────────────────────────────────────────────────────────
def test_registro_e_copia():
    AC.trocar(_lote(10), "rpc")
    cat = AC.atual()
    r = AC.registro("CAL-GAM100-INVR0.3")
    assert r == dict(cat.por_codigo["CAL-GAM100-INVR0.3"]) and type(r) is dict and r is not cat.por_codigo["CAL-GAM100-INVR0.3"]
    r["usina"] = "MEXIDO"
    r["novo"] = 1
    assert AC.registro("CAL-GAM100-INVR0.3")["usina"] == "Cliente Alfa - Usina Gama 1 - PA"
    assert "novo" not in AC.atual().por_codigo["CAL-GAM100-INVR0.3"]
    assert AC.registro("NAO-EXISTE") is None and AC.registro("") is None and AC.registro(None) is None


def test_asset_by_code_e_copia_do_catalogo_e_honra_a_lista_que_o_load_devolve(monkeypatch):
    AC.trocar(_lote(10), "rpc")
    a = api._asset_by_code("CAL-GAM100-INVR0.2")
    assert type(a) is dict and a["id"] == 1002
    a["usina"] = "MEXIDO"                                        # quem pede o ativo para mexer nele mexe na cópia dele
    assert api._asset_by_code("CAL-GAM100-INVR0.2")["usina"] == "Cliente Alfa - Usina Gama 1 - PA"
    assert api._asset_by_code("NAO-EXISTE") is None
    outro = [{"id": 1, "code": "OUTRO-1", "usina": "U"}]                      # uma lista de outra origem (um dublê, um recorte)
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: outro)
    achado = api._asset_by_code("OUTRO-1")
    assert achado == outro[0] and achado is not outro[0] and api._asset_by_code("CAL-GAM100-INVR0.2") is None


def test_o_catalogo_nao_aceita_escrita():
    AC.trocar(_lote(10), "rpc")
    cat = AC.atual()
    a = cat.lista[0]
    for mexe in (lambda: a.__setitem__("x", 1), lambda: a.update(x=1), lambda: a.pop("code"), lambda: a.setdefault("y", 2),
                 lambda: a.__delitem__("code"), lambda: a.clear(), lambda: a.popitem(), lambda: a.__ior__({"z": 1})):
        with pytest.raises(TypeError):
            mexe()
    assert isinstance(cat.lista, tuple)
    with pytest.raises(AttributeError):
        cat.lista.append(a)
    with pytest.raises(TypeError):
        cat.por_codigo["X"] = a
    with pytest.raises(TypeError):
        cat.por_cliente["X"] = ()
    with pytest.raises(Exception):                                # a versão inteira é imutável
        cat.fonte = "banco"
    # e ainda é um dicionário de verdade para quem só lê
    import copy
    assert isinstance(a, dict) and json.loads(json.dumps(a)) == dict(a) and {**a} == dict(a) and a.get("code")
    assert type(copy.copy(a)) is dict and type(copy.deepcopy(a)) is dict and type(a.copy()) is dict


def test_busca_por_codigo_sem_varrer(monkeypatch):
    AC.trocar(_lote(3000), "rpc")
    cat = AC.atual()
    lidos = []
    original = AC.Registro.get
    monkeypatch.setattr(AC.Registro, "get", lambda self, *a: lidos.append(1) or original(self, *a))
    assert AC.registro("CAL-GAM100-INVR299.9")["id"] == 1000 + 2999
    assert cat.por_id[1000 + 2999]["code"] == "CAL-GAM100-INVR299.9"
    assert cat.local_por_codigo["CAL-GAM100-INVR299.9"][2] == "Inversor"
    assert lidos == []                                           # nenhum registro foi consultado para achar este


def test_a_cascata_usa_o_indice_quando_a_lista_e_a_do_catalogo(monkeypatch):
    AC.trocar(_lote(3000) + [_reg(9000, "CBE-DEL100-INVR1.1", cliente="Cliente Beta", usina="Cliente Beta - Usina Delta 2 - BA")],
              "rpc")
    cat = AC.atual()
    lidos = []
    original = AC.Registro.get
    monkeypatch.setattr(AC.Registro, "get", lambda self, *a: lidos.append(1) or original(self, *a))
    out = trad.ativos_do_cliente(cat.lista, "Cliente Beta")
    assert [a["code"] for a in out] == ["CBE-DEL100-INVR1.1"] and len(lidos) < 100      # os 3.000 do outro cliente não são tocados
    assert trad.usinas_de(cat.lista, "Cliente Beta") == ["Cliente Beta - Usina Delta 2 - BA"]
    lidos.clear()
    # a mesma conta com uma lista que não é a do catálogo (um teste, um recorte): varre, e dá o mesmo resultado
    copia = [dict(r) for r in cat.lista]
    assert trad.ativos_do_cliente(copia, "Cliente Beta") == out
    assert trad.ativos_de(copia, "Cliente Beta", "Cliente Beta - Usina Delta 2 - BA") == trad.ativos_de(
        cat.lista, "Cliente Beta", "Cliente Beta - Usina Delta 2 - BA")


def test_ordem_e_indices():
    desordenada = [_reg(3, "B-1", cliente="Zeta", usina="Zeta - Usina 1"), _reg(1, "A-2", cliente="alfa", usina="Alfa - U 1"),
                   _reg(2, "A-1", cliente="alfa", usina="Alfa - U 1"), _reg(4, "", cliente="alfa", usina="Alfa - U 1"),
                   _reg(5, "A-1", cliente="alfa", usina="Alfa - U 2"), _reg(6, "A-3", cliente="alfa", usina="Alfa - U 2",
                                                                          tipo="")]
    assert AC.trocar(desordenada, "rpc")
    cat = AC.atual()
    assert [r["id"] for r in cat.lista] == [4, 2, 1, 5, 6, 3]                  # cliente, usina e código, sem caixa
    assert cat.por_id[2]["code"] == "A-1" and cat.por_codigo["A-1"]["id"] == 2  # o 1º de cada código
    assert [r["id"] for r in cat.por_cliente["alfa"]] == [4, 2, 1, 5, 6]
    assert [r["id"] for r in cat.por_cliente_usina[("alfa", "Alfa - U 1")]] == [4, 2, 1]
    assert cat.local_por_codigo["B-1"] == ("Zeta", "Usina 1", "Inversor") and "" not in cat.local_por_codigo
    assert cat.tipos == (("Inversor", 5),)                                      # a conta por tipo ignora o sem tipo
    assert desordenada[0]["id"] == 3                                           # a lista do chamador não foi tocada


def test_o_item_usina_da_planta_errada_e_consertado_ao_entrar():
    """O caso de 28/07 (README do OS Creator): o item-usina de uma usina registrado como filho da planta de OUTRA."""
    certos = [_reg(10 + i, "XYZ-ABC100-INVR1.%d" % i, cliente="Cliente X", usina="Cliente X - Usina Certa - PA")
              for i in range(3)]
    torto = _reg(99, "XYZ-ABC100", cliente="Cliente Y", usina="Cliente Y - Outra Planta - MT", tipo="Usina",
                 description="Cliente X - Usina Certa - PA  Zona Rural")
    assert AC.trocar(certos + [torto], "rpc")
    r = AC.registro("XYZ-ABC100")
    assert (r["cliente"], r["usina"]) == ("Cliente X", "Cliente X - Usina Certa - PA")
    assert torto["usina"] == "Cliente Y - Outra Planta - MT"                   # o dicionário do chamador segue como estava


# ── a troca ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_troca_recusa_vazia_e_encolhida():
    assert AC.trocar([], "rpc") is False and AC.atual() is None               # vazia, sem catálogo: nada nasce
    assert AC.estado()["recusa"]["motivo"] == "a lista veio vazia"
    assert AC.trocar(_lote(100), "rpc") is True
    versao = AC.atual().versao
    assert AC.trocar([], "rpc") is False
    assert AC.trocar(_lote(94), "rpc") is False                                # 6% menor: recusada
    r = AC.estado()["recusa"]
    assert "100 para 94" in r["motivo"] and (r["fonte"], r["n_novo"], r["n_atual"]) == ("rpc", 94, 100)
    assert len(AC.atual().lista) == 100 and AC.atual().versao == versao        # o catálogo de antes ficou
    assert AC.trocar(_lote(95), "rpc") is True and len(AC.atual().lista) == 95   # exatamente 5%: passa
    assert AC.trocar(_lote(300), "rest") is True and AC.estado()["fonte"] == "rest"   # crescer sempre pode


def test_a_recusa_nao_derruba_a_copia_em_disco(tmp_path):
    pasta = tmp_path / "oscreator"
    AC.reiniciar(pasta=str(pasta))
    AC.trocar(_lote(100), "rpc")
    antes = (pasta / AC.NOME_ARQUIVO).read_bytes()
    assert AC.trocar(_lote(10), "rpc") is False
    assert (pasta / AC.NOME_ARQUIVO).read_bytes() == antes


def test_a_mesma_lista_nao_troca_so_renova_a_hora(tmp_path, monkeypatch):
    pasta = tmp_path / "oscreator"
    AC.reiniciar(pasta=str(pasta))
    gravadas = []
    original = AC._gravar_disco
    monkeypatch.setattr(AC, "_gravar_disco", lambda cat: gravadas.append(cat.versao) or original(cat))
    t0 = time.time()
    assert AC.trocar(_lote(20), "rpc", lido_em=t0 - 7200)
    um = AC.atual()
    assert AC.trocar(list(reversed(_lote(20))), "rest", lido_em=t0 - 1000)      # a mesma lista em outra ordem, outra fonte
    dois = AC.atual()
    assert dois.versao == um.versao and dois.lista is um.lista and dois.por_codigo is um.por_codigo
    assert dois.lido_em == t0 - 1000 and dois.fonte == "rest"
    assert len(gravadas) == 2                                    # passou de 1 h do que está no disco: regrava a hora
    assert AC.trocar(_lote(20), "rest", lido_em=t0 - 990)
    assert len(gravadas) == 2                                    # 10 s depois: não regrava
    assert AC.trocar(_lote(20), "rest", lido_em=t0 - 9000) and AC.atual().lido_em == t0 - 990   # nunca volta no tempo
    assert AC.trocar(_lote(21), "rest", lido_em=t0) and len(gravadas) == 3 and AC.atual().versao != um.versao


def test_quem_esta_lendo_termina_com_a_versao_que_pegou():
    AC.trocar(_lote(10), "rpc")
    velho = AC.atual()
    lista_velha = api.load_assets_cached()
    assert AC.trocar(_lote(11), "rpc")
    assert len(velho.lista) == 10 and len(lista_velha) == 10 and len(AC.atual().lista) == 11   # troca inteira, de uma vez
    assert api.load_assets_cached() is AC.atual().lista


def test_a_versao_e_o_sha_das_linhas_e_muda_com_o_conteudo():
    a = AC._montar(_lote(5), "rpc", 1.0).versao
    assert a == AC._montar(list(reversed(_lote(5))), "banco", 99.0).versao and len(a) == 64
    assert a != AC._montar(_lote(5, tipo="Tracker"), "rpc", 1.0).versao


def test_estado_e_a_paridade_do_rest():
    assert AC.estado() == {"fonte": None, "lido_em": None, "versao": None, "n": 0, "recusa": None, "paridade_rest": None,
                           "disco": {"lido": None, "gravado_em": 0.0, "lido_em": 0.0, "erro": None}, "banco": None}
    AC.trocar(_lote(10), "rpc", lido_em=123.0)
    AC.anotar_paridade_rest({"vale": False, "motivo": "faltou o tipo", "pct": 91.0})
    e = AC.estado()
    assert (e["fonte"], e["lido_em"], e["n"]) == ("rpc", 123.0, 10) and e["versao"] == AC.atual().versao
    assert e["paridade_rest"]["motivo"] == "faltou o tipo"


# ── o api: a recarga entra no catálogo central ──────────────────────────────────────────────────────────────────────────
def test_a_recarga_do_rpc_entra_no_catalogo_e_na_copia_em_disco(tmp_path, monkeypatch):
    pasta = tmp_path / "oscreator"
    AC.reiniciar(pasta=str(pasta))
    baixou = []
    monkeypatch.setattr(api, "get_assets", lambda: baixou.append(1) or _lote(20))
    lista = api.load_assets_cached()                              # sem catálogo nenhum: baixa uma vez
    assert len(lista) == 20 and baixou == [1] and AC.estado()["fonte"] == "rpc"
    assert (pasta / AC.NOME_ARQUIVO).exists() and api.load_assets_cached() is lista and baixou == [1]
    # o botão Atualizar (force) baixa de novo e troca o catálogo de todos
    monkeypatch.setattr(api, "get_assets", lambda: baixou.append(2) or _lote(24))
    assert len(api.load_assets_cached(True)) == 24 and baixou == [1, 2] and len(AC.atual().lista) == 24


def test_a_recarga_que_encolhe_demais_deixa_o_catalogo_de_antes(monkeypatch):
    AC.trocar(_lote(100), "rpc")
    monkeypatch.setattr(api, "get_assets", lambda: _lote(80))     # o RPC que perdeu páginas em silêncio
    lista = api.load_assets_cached(True)
    assert len(lista) == 100 and AC.estado()["recusa"]["n_novo"] == 80
    monkeypatch.setattr(api, "get_assets", lambda: [])
    assert len(api.load_assets_cached(True)) == 100


def test_sem_catalogo_e_com_a_recarga_vazia_devolve_nada_e_guarda_nada(monkeypatch):
    monkeypatch.setattr(api, "get_assets", lambda: [])
    assert api.load_assets_cached() == () and AC.atual() is None


def test_vencido_e_pelas_24_horas_do_lido_em():
    AC.trocar(_lote(10), "rpc", lido_em=time.time() - api.ASSETS_TTL - 5)
    assert api.catalogo_vencido(AC.atual()) and api.assets_cache_info()["expirado"]
    AC.reiniciar()
    AC.trocar(_lote(10), "rpc", lido_em=time.time() - 60)
    assert not api.catalogo_vencido(AC.atual()) and not api.assets_cache_info()["expirado"]


# ── a foto do banco como catálogo ───────────────────────────────────────────────────────────────────────────────────────
def _linha_foto(i, codigo, descricao, pai, tipo, dia="2026-09-22", **mais):
    r = {"fracttal_item_id": i, "codigo": codigo, "descricao": descricao, "pai_item_id": pai, "tipo_fracttal": tipo,
         "foto_em": dia}
    r.update(mais)
    return r


# a árvore do Fracttal (nomes de mentira): a raiz de cada cliente, a usina, a cabine e os inversores. A descrição do item traz
# o ENDEREÇO da usina atrás do nome ("Zona Rural km 4"), com um espaço ou com dois, e a foto já tirou o "{ CÓDIGO }" do fim.
ARVORE = [
    _linha_foto(1, "CAL", "Cliente Alfa", None, None),
    _linha_foto(10, "CAL-GAM100", "Cliente Alfa - Usina Gama 1 - PA  Zona Rural km 4", 1, "USINA"),
    _linha_foto(20, "CAL-GAM100-CABN1", "Cabine 1 Zona Rural km 4", 10, "CABN"),               # o endereço depois de UM espaço
    _linha_foto(21, "CAL-GAM100-CABN2", "Cabine 2  Zona Rural km 4", 10, "CABN"),              # e depois de dois
    _linha_foto(25, "CAL-GAM100-SKID1", "Skid 1 Zona Rural km 4", 20, "SKID"),                 # um nível mais fundo
    _linha_foto(30, "CAL-GAM100-INVR1.1", "Inversor 1.1 Marca X", 25, "INVR"),
    _linha_foto(31, "CAL-GAM100-INVR1.2", "Inversor 1.2 Marca X", 10, "INVR"),
    _linha_foto(33, "CAL-GAM100-INVR2.1", "Inversor 2.1 Marca X", 21, "INVR"),
    _linha_foto(2, "GBE", "Grupo Beta", None, None),
    # o cliente (Grupo Beta) não é o começo do nome da usina (Beta Solar): a carteira com outro nome, 6 dos 16 clientes reais
    _linha_foto(11, "BET-DEL100", "Beta Solar - Usina Delta 2 - BA Zona Rural km 9", 2, "USINA"),
    _linha_foto(32, "BET-DEL100-INVR2.1", "Inversor 2.1", 11, "INVR"),
    # o que a carga única de 11/10 levou da foto de junho: o Fracttal já não tem este código
    _linha_foto(77, "CAL-VELHO100-INVR1.1", "Inversor velho", 10, "INVR", dia="2026-06-21"),
]
FOTO_COM_RAIZ = ARVORE
FOTO_EM = datetime(2026, 9, 22, tzinfo=timezone(timedelta(hours=-3))).timestamp()      # 22/09/2026, meia-noite de Brasília
FOTO = [l for l in ARVORE if l["pai_item_id"] is not None]        # a foto de verdade: sem a raiz de cada cliente

# os mesmos ativos como o RPC (`inventories.items_list`) os dá: o caminho vem pronto, e a descrição com o "{ CÓDIGO }"
_RAIZ_ALFA, _GAMA = "Cliente Alfa", "Cliente Alfa - Usina Gama 1 - PA"
RPC = [
    {"id": 10, "code": "CAL-GAM100", "description": _GAMA + "  Zona Rural km 4    { CAL-GAM100 }", "id_parent": 1,
     "parent_description": "// Cliente Alfa/ "},
    {"id": 20, "code": "CAL-GAM100-CABN1", "description": "Cabine 1 Zona Rural km 4    { CAL-GAM100-CABN1 }", "id_parent": 10,
     "parent_description": "// Cliente Alfa/ %s/ " % _GAMA},
    {"id": 21, "code": "CAL-GAM100-CABN2", "description": "Cabine 2  Zona Rural km 4    { CAL-GAM100-CABN2 }", "id_parent": 10,
     "parent_description": "// Cliente Alfa/ %s/ " % _GAMA},
    {"id": 25, "code": "CAL-GAM100-SKID1", "description": "Skid 1 Zona Rural km 4    { CAL-GAM100-SKID1 }", "id_parent": 20,
     "parent_description": "// Cliente Alfa/ %s/ Cabine 1/ " % _GAMA},
    {"id": 30, "code": "CAL-GAM100-INVR1.1", "description": "Inversor 1.1 Marca X    { CAL-GAM100-INVR1.1 }", "id_parent": 25,
     "parent_description": "// Cliente Alfa/ %s/ Cabine 1/ Skid 1/ " % _GAMA},
    {"id": 31, "code": "CAL-GAM100-INVR1.2", "description": "Inversor 1.2 Marca X    { CAL-GAM100-INVR1.2 }", "id_parent": 10,
     "parent_description": "// Cliente Alfa/ %s/ " % _GAMA},
    {"id": 33, "code": "CAL-GAM100-INVR2.1", "description": "Inversor 2.1 Marca X    { CAL-GAM100-INVR2.1 }", "id_parent": 21,
     "parent_description": "// Cliente Alfa/ %s/ Cabine 2/ " % _GAMA},
    {"id": 11, "code": "BET-DEL100", "description": "Beta Solar - Usina Delta 2 - BA Zona Rural km 9    { BET-DEL100 }",
     "id_parent": 2, "parent_description": "// Grupo Beta/ "},
    {"id": 32, "code": "BET-DEL100-INVR2.1", "description": "Inversor 2.1    { BET-DEL100-INVR2.1 }", "id_parent": 11,
     "parent_description": "// Grupo Beta/ Beta Solar - Usina Delta 2 - BA/ "},
]


def test_a_foto_remonta_o_caminho_igual_ao_do_rpc():
    """A comparação é com o que o RPC dá para os mesmos ativos (o caminho conhecido): cliente, usina, tipo e caminho iguais."""
    esperado = {r["code"]: r for r in AC.montar_registros([dict(x) for x in RPC])}
    registros, lido_em = AC.registros_da_foto(FOTO_COM_RAIZ)
    obtido = {r["code"]: r for r in registros}
    assert set(obtido) == set(esperado) and len(obtido) == 9                    # a raiz e o código de junho não entram
    for code, rpc in esperado.items():
        foto = obtido[code]
        for campo in ("id", "code", "id_parent", "cliente", "usina", "tipo_code", "tipo", "parent_description"):
            assert foto[campo] == rpc[campo], (code, campo)
        assert rpc["label"].split("{")[0].rstrip() == foto["label"]             # a foto vem sem o "{ CÓDIGO }" do fim
    # o que a foto não tem fica sem valor, e o resto do OS Creator lê o ativo do RPC onde precisa dele (criar OS)
    assert all(r["id_type_item"] is None and r["id_group_task"] is None for r in registros)
    gama = obtido["CAL-GAM100-INVR1.1"]
    assert (gama["cliente"], gama["usina"], gama["tipo"]) == ("Cliente Alfa", _GAMA, "Inversor")
    beta = obtido["BET-DEL100-INVR2.1"]
    assert (beta["cliente"], beta["usina"]) == ("Grupo Beta", "Beta Solar - Usina Delta 2 - BA")     # o nome da RAIZ
    assert obtido["CAL-GAM100"]["tipo"] == "Usina" and obtido["CAL-GAM100"]["usina"] == _GAMA        # o item-usina
    assert lido_em == FOTO_EM


def test_a_foto_usa_a_coluna_do_grupo_de_tarefas_quando_ela_vier():
    """A etapa 2.2 acrescenta o `id_group_task` à foto; e o código que saiu do Fracttal fica marcado, fora do catálogo."""
    linhas = [dict(l) for l in ARVORE]
    por_codigo = {l["codigo"]: l for l in linhas}
    por_codigo["CAL-GAM100-INVR1.1"]["id_group_task"] = "55"
    por_codigo["CAL-GAM100-INVR1.2"]["fora_do_fracttal_desde"] = "2026-10-01"
    registros, _ = AC.registros_da_foto(linhas)
    por = {r["code"]: r for r in registros}
    assert por["CAL-GAM100-INVR1.1"]["id_group_task"] == 55 and "CAL-GAM100-INVR1.2" not in por


def test_a_foto_de_verdade_sem_a_raiz_e_recusada_com_o_motivo():
    with pytest.raises(AC.FotoIncompleta, match="raiz"):
        AC.registros_da_foto(FOTO)
    with pytest.raises(AC.FotoIncompleta):
        AC.registros_da_foto([])
    # um dado torto (1 órfão em 200) não derruba a foto; ele só fica de fora
    muitas = [_linha_foto(1, "CAL", "Cliente Alfa", None, None), _linha_foto(10, "CAL-U100", "Cliente Alfa - U 1 - PA", 1, "USINA")]
    muitas += [_linha_foto(100 + i, "CAL-U100-INVR%d.1" % i, "Inversor %d.1" % i, 10, "INVR") for i in range(198)]
    muitas.append(_linha_foto(999, "CAL-SOLTO", "Solto", 12345, "INVR"))
    registros, _ = AC.registros_da_foto(muitas)
    assert len(registros) == 199 and "CAL-SOLTO" not in {r["code"] for r in registros}


def test_a_cadeia_quebrada_la_em_cima_tambem_e_recusada():
    """O pai imediato existe, mas o avô (a raiz) não: com a conta só pelo pai imediato, o cliente sairia como a usina."""
    foto = [l for l in ARVORE if l["fracttal_item_id"] != 1]             # só a raiz do Cliente Alfa sai
    foto = [l for l in foto if l["fracttal_item_id"] not in (2, 11, 32)] + [dict(l) for l in ()]
    assert sum(1 for l in foto if l["pai_item_id"] == 10) >= 4          # as linhas de dentro da usina têm o pai (a usina)
    with pytest.raises(AC.FotoIncompleta, match="raiz"):
        AC.registros_da_foto(foto)
    ciclo = [_linha_foto(1, "A", "A", 2, None), _linha_foto(2, "B", "B", 1, None)]
    with pytest.raises(AC.FotoIncompleta):
        AC.registros_da_foto(ciclo)


def test_a_foto_que_nao_serve_deixa_o_catalogo_para_o_fracttal_e_nao_e_lida_de_novo_logo():
    chamadas = []
    AC.ligar_fonte_do_banco(lambda: chamadas.append(1) or FOTO)
    assert AC.garantir() is None and AC.garantir() is None and AC.garantir() is None
    assert chamadas == [1]                                       # a falha espera 10 min antes de ler o banco de novo
    assert "raiz" in AC.estado()["banco"]["motivo"]
    AC.reiniciar()
    AC.ligar_fonte_do_banco(lambda: (_ for _ in ()).throw(RuntimeError("banco fora")))
    assert AC.garantir() is None and "RuntimeError" in AC.estado()["banco"]["motivo"]


def test_uma_leitura_da_foto_por_vez_para_pedidos_juntos():
    chamadas = []

    def lenta():
        chamadas.append(1)
        time.sleep(0.2)
        return FOTO_COM_RAIZ
    AC.ligar_fonte_do_banco(lenta)
    saidas = []
    ts = [threading.Thread(target=lambda: saidas.append(AC.garantir())) for _ in range(5)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert chamadas == [1] and all(s is not None and s.fonte == "banco" for s in saidas)


def test_o_load_assets_cached_usa_a_foto_do_banco_antes_do_fracttal(fracttal, monkeypatch):
    monkeypatch.setattr(api, "_ASSETS_RENOVA", {"tentou": time.time()})      # a renovação por trás (de quem vencido pede) fica de fora
    AC.ligar_fonte_do_banco(lambda: FOTO_COM_RAIZ)
    lista = api.load_assets_cached()
    assert len(lista) == 9 and AC.estado()["fonte"] == "banco" and fracttal.pedidos == []
    # a foto é de 22/09: ela já nasce vencida, serve na hora e é a primeira visita que a renova por trás com o Fracttal
    assert api.catalogo_vencido(AC.atual())


def test_as_colunas_da_foto_sao_as_do_banco():
    from nexus.dados import equipamento
    assert AC.CAB_FOTO == tuple(equipamento.CAB_FOTO)


# ── a ponte do Nexus liga o catálogo ────────────────────────────────────────────────────────────────────────────────────
def test_a_ponte_diz_onde_mora_a_copia_e_de_onde_ler_a_foto(tmp_path, monkeypatch):
    from nexus.torres.oscreator import ativos_banco
    from pg_falso import ApiPGFalsa

    class Fake:
        def __init__(self, testing):
            self.config, self.extensions = {"TESTING": testing}, {}
    monkeypatch.setattr(api, "_data_dir", lambda: str(tmp_path / "dados_do_clone"))
    monkeypatch.setattr(api, "ASSETS_CACHE_LEGADO", str(tmp_path / "dados_do_clone" / "assets_cache.json"))

    # nos testes o disco da máquina não é tocado
    app = Fake(True)
    ponte.ligar_catalogo_de_ativos(app)
    assert AC._CONFIG["pasta"] is None and AC._FONTE_BANCO["func"] is not None
    # no servidor e no PC: a cópia mora na pasta de dados do clone, ao lado do arquivo antigo
    app = Fake(False)
    ponte.ligar_catalogo_de_ativos(app)
    assert AC._CONFIG["pasta"] == str(tmp_path / "dados_do_clone" / "oscreator")
    assert AC._CONFIG["legado"] == str(tmp_path / "dados_do_clone" / "assets_cache.json")

    # a função do banco: as linhas da foto, pela sessão do app; teste sem sessão nunca vai à rede
    with pytest.raises(RuntimeError, match="teste sem banco"):
        ativos_banco.leitor(Fake(True))()
    pg = ApiPGFalsa()
    pg._id("nexus_ativos_fracttal", "foto_ativos")["linhas"] = [
        {"headers": list(AC.CAB_FOTO), "values": [l[c] for c in AC.CAB_FOTO]} for l in FOTO_COM_RAIZ]
    app = Fake(True)
    app.extensions["nexus_dados_sessao"] = pg
    linhas = ativos_banco.leitor(app)()
    assert len(linhas) == len(FOTO_COM_RAIZ) and linhas[1]["codigo"] == "CAL-GAM100" and linhas[1]["pai_item_id"] == 1
    AC.reiniciar()
    AC.ligar_fonte_do_banco(ativos_banco.leitor(app))
    assert AC.garantir().fonte == "banco"
