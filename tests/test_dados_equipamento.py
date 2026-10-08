"""A dimensão de equipamento (passo 6a do Kimball, 08/10/2026): o ID derivado do código, a usina dentro do código, a
foto do Fracttal, os membros montados só do banco, os apelidos e a ligação dos fatos. Códigos e nomes inventados."""
import hashlib
import inspect
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest
from pg_falso import ApiPGFalsa

from nexus.dados import equipamento as eq
from nexus.dados import livros

BASE = "http://pg.falso"

USINAS = [{"usina_id": 1, "codigo": "XYZ-DEF100"}, {"usina_id": 2, "codigo": "ABC100"},
          {"usina_id": 3, "codigo": "XYZ-GHI100"}, {"usina_id": 4, "codigo": "QQQ-GHI100"},
          {"usina_id": 5, "codigo": "QQQ-JKL100"}, {"usina_id": 6, "codigo": "MNO100", "excluido": "sim"},
          {"usina_id": 7, "codigo": "STU100"}, {"usina_id": 8, "codigo": "XYZ-STU100"}, {"usina_id": 9, "codigo": None}]

# 22/09/2026 09:28 em Brasília; 21/06/2026 23:08 em Brasília (02:08 do dia 22 em UTC)
TS_SET, TS_JUN = 1790080133.0, 1782094111.0


def _a(i, code, pai=0, tipo=None, desc=None):
    return {"id": i, "code": code, "id_parent": pai, "tipo_code": tipo,
            "description": desc if desc is not None else f"Item {i}    {{ {code} }}"}


FOTO_SET = {"ts": TS_SET, "assets": [
    _a(10, "XYZ-DEF100", tipo="USINA"), _a(11, "XYZ-DEF100-INVR11.1", 10, "INVR"),
    _a(12, "ABC100-INVR2.4", 13, "INVR"), _a(13, "ABC100-SKID2", tipo="SKID"), _a(14, "Transformador 2", tipo="TRFR"),
    _a(15, "340", tipo="USINA"), _a(16, "", desc="sem código"), _a(17, "GHI100-ETKR1.1", tipo="ETKR"),
    _a(18, "XYZ-JKL100-ETKR1.1", tipo="ETKR")]}
FOTO_JUN = {"ts": TS_JUN, "assets": [
    _a(12, "ABC100-INVR2.4", 13, "INVR"),                 # a mesma na nova: não repete
    _a(11, "XYZ-DEF100-INV11.1", 10, "INVR"),             # renomeado depois: o código velho continua membro
    _a(20, "ABC100-INVR2.9", 13, "INVR")]}                # baixado depois de junho

FONTES = {"fechamentos": ["ABC100-INVR2.4", "abc100-invr 2.4", "GRID", "ABC100-INVR3.1", None, ""],
          # o que o App gravou no lugar do ativo: não é equipamento (e, empatados, testam a ordem dos exemplos)
          "pt": ["XYZ-DEF100-INVR11.1", "Nobreak 1", "SPDA", "Sem ativo", "Cabine X"]}
TRACKERS = [
    {"Fonte": "API PV", "UFV Supervisório": "Usina Exemplo", "Tracker Supervisório": "TRK1",
     "Code Fracttal": "GHI100-ETKR1.1", "Como casou": "direto"},
    {"Fonte": "API PV", "UFV Supervisório": "Usina Exemplo", "Tracker Supervisório": "TRK2", "Code Fracttal": None},
    # a mesma chave apontando para dois equipamentos: não liga nenhum
    {"Fonte": "Outra", "UFV Supervisório": "Dupla", "Tracker Supervisório": "T1", "Code Fracttal": "ABC100-SKID2"},
    {"Fonte": "Outra", "UFV Supervisório": "Dupla", "Tracker Supervisório": "T1", "Code Fracttal": "ABC100-INVR2.4"}]
GEMEO = [{"usina": "GEM1", "equipamento": "TRK_1", "sistema": "bd_trackers", "valor": "usina exemplo|trk1"},
         {"usina": "GEM1", "equipamento": "Inversor 2.4", "sistema": "bd_performance", "valor": "ABC100|Inversor 2.4"},
         {"usina": "GEM1", "equipamento": None, "sistema": "fracttal", "valor": "Cliente - Usina - UF"},
         {"usina": "GEM1", "equipamento": "TRK9", "sistema": "bd_trackers", "valor": "Outra|TRK9"}]
COLUNAS = [{"livro": "bd_performance", "aba": "ABC100", "coluna": "Inversor 2.4", "usina_id": 2},
           {"livro": "bd_thopen", "aba": "Usina DEF", "coluna": "Inversor 11.1", "usina_id": 1},
           {"livro": "bd_thopen", "aba": "Usina DEF", "coluna": "Inversor 99.1", "usina_id": 1},
           {"livro": "bd_thopen", "aba": "Sem de-para", "coluna": "Inversor 1.1", "usina_id": None}]


def _foto():
    return [dict(zip(eq.CAB_FOTO, l)) for l in eq.foto_linhas(FOTO_SET, FOTO_JUN)]


def _dim():
    return {d[1]: dict(zip(eq.CAB_DIM, d)) for d in eq.membros(_foto(), FONTES, USINAS)}


# ── o código e o ID ───────────────────────────────────────────────────────────────────────────────────────────────
def test_id_derivado_do_codigo_canonico_cabe_nos_15_digitos_do_excel():
    assert eq.canon(" abc100-invr 2.4 ") == "ABC100-INVR2.4" and eq.canon(None) == ""
    esperado = int(hashlib.sha1(b"fracttal:ABC100-INVR2.4").hexdigest()[:13], 16) >> 3
    assert eq.equipamento_id("abc100-invr 2.4") == eq.equipamento_id("ABC100-INVR2.4") == esperado
    assert 0 < esperado < 2 ** 49
    # o maior ID possível cabe nos 15 dígitos do Excel (com 52 bits, 77% tinham 16 e o Excel trocava o último por 0)
    assert len(str(2 ** 49 - 1)) == 15
    assert eq.equipamento_id("") is None and eq.equipamento_id(None) is None


def _em_outro_processo(codigo: str, semente: str) -> str:
    raiz = Path(__file__).resolve().parent.parent
    env = dict(os.environ, PYTHONHASHSEED=semente, PYTHONPATH=str(raiz / "tests"))
    return subprocess.run([sys.executable, "-c", codigo], cwd=raiz, capture_output=True, text=True, check=True,
                          env=env).stdout.strip()


def test_id_igual_em_outra_execucao_do_python():
    """PC e servidor calculam o mesmo número sem conversar: outro processo, outra semente de hash, o mesmo ID."""
    cod = "from nexus.dados.equipamento import equipamento_id as f; print(f('XYZ-DEF100-INVR11.1'))"
    assert int(_em_outro_processo(cod, "12345")) == eq.equipamento_id("XYZ-DEF100-INVR11.1")


def test_sha_igual_em_processos_com_outra_semente_de_hash():
    """A ordem de um set de textos muda a cada processo; o sha das linhas não pode mudar com ela, senão as duas
    máquinas regravariam o livro uma depois da outra sem nada novo."""
    cod = ("import test_dados_equipamento as t; from nexus.dados import equipamento as eq; "
           "print(eq.montar(t._foto(), t.FONTES, t.USINAS, t.TRACKERS, t.GEMEO, t.COLUNAS, agora='x', "
           "maquina='y')[1]['sha_linhas'])")
    aqui = eq.montar(_foto(), FONTES, USINAS, TRACKERS, GEMEO, COLUNAS, agora="z", maquina="w")[1]["sha_linhas"]
    assert _em_outro_processo(cod, "1") == _em_outro_processo(cod, "2") == aqui


def test_os_dois_formatos_a_familia_e_o_valido():
    assert eq.familia("ABC100-INVR2.4") == "INVR" and eq.familia("XYZ-DEF100-INVR11.1") == "INVR"
    assert eq.familia("XYZ-DEF100") == "USINA" and eq.familia("ABC100-SKID2") == "SKID"
    assert eq.familia("340") is None and eq.familia("Transformador 2") is None
    assert eq.valido("340", {"340"}) and not eq.valido("340", set())          # só vale porque está na foto
    assert eq.valido("ABC100-INVR3.1", set())                                 # tem código de usina dentro
    assert not eq.valido("GRID", set()) and not eq.valido("Nobreak 1", set()) and not eq.valido("", {""})


# ── a usina dentro do código ──────────────────────────────────────────────────────────────────────────────────────
def test_usina_pelo_codigo_so_quando_e_de_uma_usina():
    u = eq.IndiceUsinas(USINAS)
    assert eq.usina_do_codigo("XYZ-DEF100-INVR11.1", u) == (1, "código cheio")
    assert eq.usina_do_codigo("ABC100-INVR2.4", u) == (2, "código cheio")
    assert eq.usina_do_codigo("XYZ-ABC100-INVR1", u) == (2, "sufixo único")      # o cadastro tem sem prefixo
    assert eq.usina_do_codigo("DEF100-INVR1", u) == (1, "sufixo único")          # o Fracttal grava sem prefixo
    assert eq.usina_do_codigo("GHI100-ETKR1.1", u) == (None, "código de 2+ usinas")
    assert eq.usina_do_codigo("XYZ-GHI100-ETKR1.1", u) == (3, "código cheio")    # com o prefixo, é de uma
    assert eq.usina_do_codigo("STU100-INVR1", u) == (None, "código de 2+ usinas")  # STU100 e XYZ-STU100: não chuta
    assert eq.usina_do_codigo("XYZ-STU100-INVR1", u) == (8, "código cheio")
    assert eq.usina_do_codigo("XYZ-JKL100-ETKR1.1", u) == (None, "prefixo do cliente diferente")
    assert eq.usina_do_codigo("MNO100-INVR1", u) == (None, "código fora do cadastro")   # usina excluída
    assert eq.usina_do_codigo("340", u) == (None, "sem código de usina")
    assert eq.usina_do_codigo("XYZ-DEF100-INVR11.1", USINAS) == (1, "código cheio")    # aceita a lista também


# ── a foto do Fracttal (carga única) ─────────────────────────────────────────────────────────────────────────────
def test_foto_nova_inteira_mais_os_codigos_que_so_a_velha_tem():
    linhas = eq.foto_linhas(FOTO_SET, FOTO_JUN)
    d = {(l[0], l[1]): dict(zip(eq.CAB_FOTO, l)) for l in linhas}
    assert len(linhas) == len(FOTO_SET["assets"]) + 2
    assert {l[1] for l in linhas if l[5] == "2026-06-21"} == {"XYZ-DEF100-INV11.1", "ABC100-INVR2.9"}
    assert {l[5] for l in linhas} == {"2026-09-22", "2026-06-21"}              # o dia é o de Brasília
    assert d[(11, "XYZ-DEF100-INVR11.1")]["descricao"] == "Item 11"          # sem o "{ código }" repetido
    assert d[(14, "TRANSFORMADOR2")]["tipo_fracttal"] == "TRFR"
    assert d[(16, None)]["descricao"] == "sem código"                        # item sem código entra (pode ser pai)
    assert d[(11, "XYZ-DEF100-INVR11.1")]["pai_item_id"] == 10
    assert len(eq.foto_linhas(FOTO_SET)) == len(FOTO_SET["assets"])


# ── os membros ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_membros_pai_familia_e_o_codigo_so_das_fontes():
    d = _dim()
    assert "GRID" not in d and "" not in d                                    # não é equipamento
    assert set(d) == {eq.canon(a["code"]) for f in (FOTO_SET, FOTO_JUN) for a in f["assets"] if a["code"]} | {
        "ABC100-INVR3.1"}
    inv = d["XYZ-DEF100-INVR11.1"]
    assert (inv["usina_id"], inv["usina_ligada_por"], inv["motivo_sem_usina"]) == (1, "código cheio", None)
    assert (inv["familia"], inv["tipo_fracttal"], inv["fracttal_item_id"]) == ("INVR", "INVR", 11)
    assert inv["pai_id"] == eq.equipamento_id("XYZ-DEF100") and inv["na_foto"] == 1 and inv["fontes_qtd"] == 1
    assert (inv["foto_em"], inv["descricao"]) == ("2026-09-22", "Item 11")
    novo = d["ABC100-INVR3.1"]                                                # o App gravou um ativo depois da foto
    assert (novo["na_foto"], novo["foto_em"], novo["usina_id"], novo["fontes_qtd"]) == (0, None, 2, 1)
    assert d["ABC100-INVR2.4"]["fontes_qtd"] == 1                             # 2 linhas, 1 fonte
    velho = d["XYZ-DEF100-INV11.1"]                                           # o mesmo item com o código antigo
    assert (velho["fracttal_item_id"], velho["foto_em"], velho["pai_id"]) == (
        11, "2026-06-21", eq.equipamento_id("XYZ-DEF100"))
    assert (d["GHI100-ETKR1.1"]["usina_id"], d["GHI100-ETKR1.1"]["motivo_sem_usina"]) == (None, "código de 2+ usinas")
    assert d["340"]["pai_id"] is None and d["340"]["familia"] is None


def test_membros_sem_a_foto_no_banco_ficam_so_os_codigos_das_fontes():
    tab, rel = eq.montar([], FONTES, USINAS, [], [], [], agora="t", maquina="pc")
    assert {l[1] for l in tab["dim_equipamento"][1]} == {"ABC100-INVR2.4", "ABC100-INVR3.1", "XYZ-DEF100-INVR11.1"}
    assert "aviso" in rel


def test_colisao_de_id_recusa_a_dimensao(monkeypatch):
    monkeypatch.setattr(eq, "equipamento_id", lambda c: 7 if eq.canon(c) else None)
    with pytest.raises(eq.ColisaoDeId):
        eq.membros(_foto(), FONTES, USINAS)
    with pytest.raises(eq.ColisaoDeId):
        eq.montar(_foto(), FONTES, USINAS, [], [], [], agora="t", maquina="pc")


# ── apelidos ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_apelidos_por_sistema_e_a_chave_de_dois_equipamentos_nao_liga():
    dim = eq.membros(_foto(), FONTES, USINAS)
    conta = {}
    ap = {(a[1], a[2]): (a[0], a[3]) for a in eq.apelidos(TRACKERS, GEMEO, COLUNAS, dim, conta)}
    trk, inv24 = eq.equipamento_id("GHI100-ETKR1.1"), eq.equipamento_id("ABC100-INVR2.4")
    assert ap[("Supervisório · tracker", "API PV|Usina Exemplo|TRK1")] == (trk, "direto")
    assert not any(k[1].startswith("Outra|Dupla") for k in ap)               # a mesma chave, dois códigos
    assert conta["Supervisório · tracker"]["chave de 2+ equipamentos"] == 1
    assert ap[("BD_Performance · coluna", "ABC100|Inversor 2.4")] == (inv24, "número do inversor")
    assert ap[("BD_Thopen · coluna", "Usina DEF|Inversor 11.1")][0] == eq.equipamento_id("XYZ-DEF100-INVR11.1")
    assert not any("99.1" in k[1] or "Sem de-para" in k[1] for k in ap)      # sem o código; aba sem usina
    assert ap[("Gêmeo · equipamento", "GEM1|TRK_1")] == (trk, "alias bd_trackers → de-para de trackers")
    assert ap[("Gêmeo · equipamento", "GEM1|Inversor 2.4")][0] == inv24       # pelo alias da coluna
    assert ("Gêmeo · equipamento", "GEM1|TRK9") not in ap
    assert conta["Gêmeo · equipamento"]["linhas"] == 3                        # o alias de usina não conta
    assert conta["BD_Thopen · coluna"]["aba sem usina"] == 1


def test_inversor_com_dois_codigos_na_usina_nao_liga_a_coluna():
    """"INVR02.4" e "INVR2.4" na mesma usina: o número é o mesmo; a coluna "Inversor 2.4" não escolhe."""
    foto = _foto() + [dict(zip(eq.CAB_FOTO, [21, "ABC100-INVR02.4", None, 13, "INVR", "2026-09-22"]))]
    conta = {}
    ap = eq.apelidos([], [], COLUNAS[:1], eq.membros(foto, {}, USINAS), conta)
    assert ap == [] and conta["BD_Performance · coluna"]["2+ códigos do inversor"] == 1


def test_colunas_de_geracao_so_os_inversores():
    cab = {("bd_thopen", "Usina DEF"): ["Data", "Energia Produzida (kWh)", "Inversor 11.1", " inversor 3 ", "SKID 1"]}
    cols = eq.colunas_de_geracao(cab, {("bd_thopen", "Usina DEF"): 1})
    assert [(c["coluna"], c["usina_id"]) for c in cols] == [("Inversor 11.1", 1), ("inversor 3", 1)]


# ── o fato liga pelo código ──────────────────────────────────────────────────────────────────────────────────────
def test_ligar_o_codigo_do_fato():
    ix = eq.indice(eq.membros(_foto(), FONTES, USINAS))
    assert eq.ligar("abc100-invr 2.4", ix) == (eq.equipamento_id("ABC100-INVR2.4"), "foto do Fracttal")
    assert eq.ligar("340", ix) == (eq.equipamento_id("340"), "foto do Fracttal")
    assert eq.ligar("ABC100-INVR3.1", ix) == (eq.equipamento_id("ABC100-INVR3.1"), "código com usina")
    # fonte que a carga ainda não lê: o mesmo ID, marcado, para a qualidade do fato contar o órfão
    assert eq.ligar("ABC100-INVR7.7", ix) == (eq.equipamento_id("ABC100-INVR7.7"),
                                              "código com usina (fora da dimensão)")
    for invalido in ("GRID", "Nobreak 1", "", None, "XYZ-TESTE100"):
        assert eq.ligar(invalido, ix) == (None, None)


# ── montado só do banco; publica só quando muda ─────────────────────────────────────────────────────────────────
def _aba(api, livro, aba, linhas):
    cab = list(linhas[0])
    api._id(livro, aba)["linhas"] = [{"headers": cab, "values": [l.get(c) for c in cab]} for l in linhas]


def test_dimensao_montada_so_do_banco_e_o_id_sobrevive_ao_xlsx():
    """O membro não depende da máquina: tudo sai do banco (aqui o falso, devolvendo TEXTO), e o ID de 49 bits volta
    exato depois do xlsx da gravação."""
    api = ApiPGFalsa(como_texto=True)
    livros.publicar(eq.LIVRO_FOTO, eq.NOME_FOTO, {eq.ABA_FOTO: (eq.CAB_FOTO, eq.foto_linhas(FOTO_SET, FOTO_JUN))},
                    base=BASE, token="t", sessao=api)
    _aba(api, "cadastro_nexus", "usinas", USINAS)
    _aba(api, "fechamentos_app_campo", "Fechamentos", [{"Código do ativo": c} for c in FONTES["fechamentos"]])
    _aba(api, "pt_app_campo", "PT", [{"Código do ativo": c} for c in FONTES["pt"]])
    ler = lambda livro, aba: livros.ler(BASE, api, livro, aba)                   # noqa: E731
    cod = {nome: [r.get(col) for r in ler(livro, aba)] for nome, livro, aba, col in eq.FONTES_BANCO}
    tab, _ = eq.montar(ler(eq.LIVRO_FOTO, eq.ABA_FOTO), cod, ler("cadastro_nexus", "usinas"), [], [], [],
                       agora="t", maquina="servidor")
    em_memoria = eq.membros(_foto(), FONTES, USINAS)
    assert tab["dim_equipamento"][1] == em_memoria
    livros.publicar(eq.LIVRO, eq.NOME, tab, base=BASE, token="t", sessao=api)
    assert eq.indice(ler(eq.LIVRO, "dim_equipamento")) == eq.indice(em_memoria)
    assert not eq.mudou(tab, ler(eq.LIVRO, "atualizacao"))


def test_so_publica_quando_o_conteudo_muda():
    args = (_foto(), FONTES, USINAS, TRACKERS, GEMEO, COLUNAS)
    tab, rel = eq.montar(*args, agora="2026-10-08T10:40:00-03:00", maquina="pc")
    assert eq.mudou(tab, []) and not eq.mudou(tab, [{"sha_linhas": rel["sha_linhas"]}])
    # outra máquina, outra hora, tudo em outra ordem: o mesmo conteúdo
    emb = [list(x) if not isinstance(x, dict) else {k: list(v) for k, v in x.items()} for x in args]
    random.Random(3).shuffle(emb[0])
    for k in emb[1]:
        random.Random(4).shuffle(emb[1][k])
    for x in emb[2:]:
        random.Random(5).shuffle(x)
    tab2, rel2 = eq.montar(*emb, agora="2026-10-08T11:40:00-03:00", maquina="servidor")
    assert rel2["sha_linhas"] == rel["sha_linhas"] and not eq.mudou(tab2, [{"sha_linhas": rel["sha_linhas"]}])
    # linha nova de um fato com código já conhecido: a dimensão é a mesma, não regrava
    mais = dict(FONTES, fechamentos=FONTES["fechamentos"] + ["ABC100-INVR2.4"])
    assert eq.montar(_foto(), mais, USINAS, TRACKERS, GEMEO, COLUNAS, agora="x", maquina="pc")[1]["sha_linhas"] == \
        rel["sha_linhas"]
    # código novo: muda
    novo = dict(FONTES, pt=FONTES["pt"] + ["ABC100-INVR4.4"])
    tab3, _ = eq.montar(_foto(), novo, USINAS, TRACKERS, GEMEO, COLUNAS, agora="x", maquina="pc")
    assert eq.mudou(tab3, [{"sha_linhas": rel["sha_linhas"]}])


def test_qualidade_da_dimensao():
    tab, rel = eq.montar(_foto(), FONTES, USINAS, TRACKERS, GEMEO, COLUNAS, agora="t", maquina="pc")
    q = {(l[0], l[1]): dict(zip(eq.CAB_QUALIDADE, l)) for l in tab["qualidade"][1]}
    assert q[("dimensão", "membros")]["valor"] == rel["membros"] == len(tab["dim_equipamento"][1])
    assert q[("fracttal", "itens com 2+ códigos")]["valor"] == 1               # o item 11 renomeado
    assert q[("fonte", "fechamentos")]["valor"] == 3 and "GRID (1)" in q[("fonte", "fechamentos")]["detalhe"]
    assert q[("sem usina", "código de 2+ usinas")]["detalhe"] == "GHI100 (1)"
    assert rel["fontes_linhas_e_ligadas"]["fechamentos"] == [4, 3]             # por linha: GRID fica vazio
    assert q[("apelido", "Supervisório · tracker")]["valor"] == 1
    assert tab["atualizacao"][1][0][eq.CAB_ATUALIZACAO.index("sha_linhas")] == rel["sha_linhas"]


def test_modulo_e_puro_sem_rede_nem_arquivo():
    """As fotos e o os_falhas.json são arquivos do PC: a carga de hora em hora nunca os lê (o servidor tem outros)."""
    fonte = inspect.getsource(eq)
    for proibido in ("import requests", "urllib", "open(", "Path(", "import os"):
        assert proibido not in fonte, proibido
