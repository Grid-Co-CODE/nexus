"""O Tipo e as duas Classificações da peça nova na curadoria (12/11/2026, item 3 da 2ª rodada do Almoxarifado). O PCM: "se você
conseguisse que eu colocasse pelo Nexus ou com base nos que já existem e são parecidos ele indicasse e colocasse automaticamente
como sugestão". A prova de 12/11/2026 no Fracttal de verdade: o `item_insert` grava o `id_group` (Tipo), o `id_group_1`
(Classificação 1, a criticidade) e o `id_group_2` (Classificação 2, o Rank), e as opções saem das próprias peças.

Aqui: a letra do Rank e a chave que casa o catálogo do App com a opção do Fracttal, as opções e a conferência do id
(`classificacao.py`), a sugestão pelas parecidas e pela Família (`curadoria.sugerir_classificacao`) e a da avariada pela peça
boa, o adaptador (`estoque.classificacoes` e o `criar_peca` com os grupos) e o falso, o cadastrar com os três ids (a recusa do id
fora das opções, a reserva, o que a decisão guarda e o lembrete do que ficou "sem"), a rota da ponte com as recusas de sempre e
a tela com e sem a ponte. Dado de mentira: códigos, ids e nomes inventados, sem nome de gente."""
import json
import re

import pytest
from estoque_falso import EstoqueFalso
from test_campo_visao import banco  # noqa: F401  (banco é fixture)
from test_pcm_almoxarifado import _semear
from test_pcm_inventario_curadoria import (ACHADO_COM_DADOS, CABO, CADASTRAR, PECA_DA_LISTA, PESSOA, URL,
                                           _cartao, _o_bom_sem_av, _pessoa_ms, _so, cur)  # noqa: F401  (cur é fixture)
from test_pcm_inventario_estoque import PECAS, Fracttal, em_paginas, estoque, ok
from test_pcm_publicar import _no_setor

from nexus.dados import fato_inventario as F
from nexus.pcm.inventario import classificacao as CL
from nexus.pcm.inventario import curadoria as CU
from nexus.pcm.inventario import estoque as E
from nexus.cadastro import setor_ids as SID

CRIAR, UNIDADES = "inventories.item_insert", "companies.units_list"
OPCOES = "/os/_nexus/inventario/classificacoes"


def _peca(i, codigo, tipo=None, c1=None, c2=None):
    """Uma linha da lista de peças do Fracttal com o Tipo e as Classificações (o par id e descrição de cada um)."""
    linha = {"id": i, "code": codigo, "field_1": f"Peça {i}"}
    for campo, par in (("tipo", tipo), ("classificacao_1", c1), ("classificacao_2", c2)):
        if par:
            linha[E.GRUPOS[campo][0]], linha[E.GRUPOS[campo][1]] = par
    return linha


CABOS, PROTECAO, INSTALACAO = (318452, "Cabos"), (318444, "Proteção Elétrica"), (318460, "Instalação")
ESSENCIAL, NECESSARIO, OPCIONAL = (289061, "1.Essencial"), (289062, "2.Necessário"), (289064, "4.Opcional")
RANK_A, RANK_B, AVARIADO = (364873, "2. Rank A"), (364874, "3. Rank B"), (364870, "1.Avariado")
PECAS_DO_FRACTTAL = [_peca(1, "SP-CAB-001", CABOS, NECESSARIO, RANK_B), _peca(2, "SP-CAB-002", CABOS, NECESSARIO, RANK_A),
                     _peca(3, "SP-PEL-001", PROTECAO, ESSENCIAL, RANK_A), _peca(4, "SP-INS-001", INSTALACAO, OPCIONAL),
                     _peca(5, "SP-PEL-001-AV", PROTECAO, ESSENCIAL, AVARIADO), _peca(6, "SP-SEM-001")]


@pytest.fixture(autouse=True)
def _sem_copia():
    """A cópia de 1 h das opções é do processo: cada teste começa sem ela."""
    CL.limpar()
    yield
    CL.limpar()


def _falso(**kw):
    return EstoqueFalso({"10": {"5": {"saldo": 1, "codigo": "SP-CAB-001"}, "6": {"saldo": 1, "codigo": "SP-CAB-012"}}},
                        pecas_do_catalogo=PECAS_DO_FRACTTAL, **kw)


# ── a letra, a chave, as opções e a conferência (puras) ─────────────────────────────────────────────────────────────

def test_a_letra_do_rank():
    """A opção do Fracttal é a descrição ("2. Rank A"); a Curva do livro do App é a letra ("A"). O "1.Avariado" não é curva."""
    for texto, letra in (("2. Rank A", "A"), ("3. Rank B", "B"), ("4. Rank C", "C"), ("3.Rank B", "B"), ("rank c", "C"),
                         ("A", "A"), ("b", "B"), ("Curva C", "C"), ("1.Avariado", ""), ("Rank D", ""), ("", ""), (None, ""),
                         ("2. Rank AB", ""), ("Avariado A", "")):
        assert CL.letra_do_rank(texto) == letra, texto


def test_a_chave_casa_o_catalogo_do_app_com_a_opcao_do_fracttal():
    assert CL.chave("tipo", "Proteção Elétrica") == CL.chave("tipo", " protecao  ELETRICA") == "protecao eletrica"
    assert CL.chave("classificacao_1", "1.Essencial") == CL.chave("classificacao_1", "1. Crítico") == "1"
    assert CL.chave("classificacao_1", "Essencial") == "essencial"                       # sem número, pelo texto
    assert CL.chave("classificacao_2", "2. Rank A") == CL.chave("classificacao_2", "A") == "A"
    assert CL.chave("classificacao_2", "1.Avariado") == ""


def test_as_opcoes_tem_a_chave_e_a_repetida_fica_sem():
    """Duas opções do mesmo campo com a mesma chave: a sugestão não escolhe sozinha entre elas."""
    ops = CL.opcoes({"tipo": [("1", "Cabos")], "classificacao_1": [("7", "1.Essencial"), ("8", "1. Crítico"),
                                                                    ("9", "2.Necessário")],
                     "classificacao_2": [("3", "2. Rank A"), ("4", "1.Avariado")]})
    assert ops["tipo"] == [{"id": "1", "descricao": "Cabos", "chave": "cabos"}]
    assert [o["chave"] for o in ops["classificacao_1"]] == ["", "", "2"]
    assert [o["chave"] for o in ops["classificacao_2"]] == ["A", ""]
    assert CL.opcoes({}) == {"tipo": [], "classificacao_1": [], "classificacao_2": []}


def test_conferir_recusa_o_id_fora_das_opcoes_e_sem_id_nem_le():
    ops = CL.opcoes({"tipo": [("318452", "Cabos")], "classificacao_2": [("364873", "2. Rank A")]})
    lidas = []

    def ler():
        lidas.append(1)
        return ops
    assert CL.conferir({"tipo": "", "classificacao_1": " ", "classificacao_2": None}, ler) == {} and lidas == []
    assert CL.conferir(None, ler) == {} and lidas == []
    assert CL.conferir({"tipo": " 318452 ", "classificacao_2": "364873"}, ler) == {
        "tipo": {"id": "318452", "descricao": "Cabos"}, "classificacao_2": {"id": "364873", "descricao": "2. Rank A"}}
    for ruim in ({"tipo": "999"}, {"classificacao_1": "318452"}, {"cor": "1"}):
        with pytest.raises(ValueError):
            CL.conferir(ruim, ops)
    with pytest.raises(ValueError):
        CL.conferir({"tipo": "318452"}, None)                     # sem as opções, nenhum id passa


def test_faltam_o_que_ficou_sem():
    assert CL.faltam({"tipo": "Cabos", "classificacao_2": "2. Rank A"}) == ["Classificação 1"]
    assert CL.faltam(None) == CL.faltam({}) == ["Tipo", "Classificação 1", "Classificação 2"]
    assert CL.faltam({"tipo": "Cabos", "classificacao_1": "1.Essencial", "classificacao_2": "2. Rank A"}) == []


# ── as opções no adaptador e no falso ────────────────────────────────────────────────────────────────────────────────

def test_as_opcoes_saem_das_pecas_sem_os_vazios():
    linhas = PECAS_DO_FRACTTAL + [{"id": 9, "id_group": 318452, "groups_description": "Outro nome"},     # o 1º nome vale
                                  {"id": 10, "id_group": "abc", "groups_description": "Ruim"},           # id que não é número
                                  {"id": 11, "id_group": 318499, "groups_description": "  "}, "lixo"]    # sem descrição
    pares = E.classificacoes_das_pecas(linhas)
    assert pares["tipo"] == [("318452", "Cabos"), ("318460", "Instalação"), ("318444", "Proteção Elétrica")]
    assert pares["classificacao_1"] == [("289061", "1.Essencial"), ("289062", "2.Necessário"), ("289064", "4.Opcional")]
    assert pares["classificacao_2"] == [("364870", "1.Avariado"), ("364873", "2. Rank A"), ("364874", "3. Rank B")]


def test_o_adaptador_le_as_opcoes_em_todas_as_paginas():
    fr = Fracttal({PECAS: em_paginas(PECAS_DO_FRACTTAL)})
    pares = estoque(fr, pagina=2).classificacoes()
    assert fr.metodos == [PECAS] * 3 and pares == E.classificacoes_das_pecas(PECAS_DO_FRACTTAL)
    assert fr.pedidos[0] == (PECAS, {"filter": [], "sort": [], "page": 1, "limit": 2, "start": 0, "is_tree": False,
                                     "node": 0, "id_type_item": 4})
    assert EstoqueFalso({}, pecas_do_catalogo=PECAS_DO_FRACTTAL).classificacoes() == pares
    assert EstoqueFalso({}).classificacoes() == {"tipo": [], "classificacao_1": [], "classificacao_2": []}


def test_criar_peca_manda_so_os_grupos_que_vieram():
    """O MESMO corpo do `item_insert` mais `id_group`, `id_group_1` e `id_group_2` (o que a prova de 12/11/2026 gravou), só os
    que vieram e como número; o vazio não vai, e sem grupos o corpo é o de antes."""
    fr = Fracttal({UNIDADES: ok([{"id": 362334, "description": "UNIDADE"}]), CRIAR: ok({"id": 53750352})})
    est = estoque(fr)
    est.criar_peca("SP-TST-001", "Peça", grupos={"tipo": "318452", "classificacao_1": 289062, "classificacao_2": "364873"})
    est.criar_peca("SP-TST-002", "Peça", grupos={"tipo": "", "classificacao_1": None, "classificacao_2": "364873"})
    est.criar_peca("SP-TST-003", "Peça")
    corpos = [p[1] for p in fr.pedidos if p[0] == CRIAR]
    assert {k: corpos[0][k] for k in ("id_group", "id_group_1", "id_group_2")} == {
        "id_group": 318452, "id_group_1": 289062, "id_group_2": 364873}
    assert "id_group" not in corpos[1] and "id_group_1" not in corpos[1] and corpos[1]["id_group_2"] == 364873
    assert not any(k.startswith("id_group") for k in corpos[2])
    assert {k: v for k, v in corpos[0].items() if not k.startswith("id_group")} == {**corpos[2], "code": "SP-TST-001"}
    n = len(fr.pedidos)
    for ruim in ({"cor": "1"}, {"tipo": "Cabos"}):
        with pytest.raises(ValueError):
            est.criar_peca("SP-TST-004", "Peça", grupos=ruim)
    assert len(fr.pedidos) == n                                                     # o id ruim nem vai ao Fracttal
    f = EstoqueFalso({})
    novo = f.criar_peca("SP-TST-009", "Peça nova", grupos={"tipo": "318452", "classificacao_2": ""})
    assert f._catalogo[novo]["grupos"] == {"id_group": 318452}
    assert "grupos" not in f._catalogo[f.criar_peca("SP-TST-010", "Outra")]


def test_a_copia_das_opcoes_vale_1_hora():
    falso, agora = _falso(), [1000.0]
    a = CL.guardadas(falso, relogio=lambda: agora[0])
    agora[0] += CL.TTL_S - 1
    assert CL.guardadas(falso, relogio=lambda: agora[0]) is a and falso.chamadas == ["pecas_com_grupos"]
    agora[0] += 2
    CL.guardadas(falso, relogio=lambda: agora[0])
    assert falso.chamadas == ["pecas_com_grupos", "pecas_com_grupos"]
    assert [o["chave"] for o in a["classificacao_2"]] == ["", "A", "B"]


def test_o_erro_do_fracttal_nao_fica_na_copia():
    falso = _falso(limite_em=1)
    with pytest.raises(E.Limite):
        CL.guardadas(falso)
    assert CL.guardadas(falso)["tipo"]                                              # a 2ª lê de novo, e vale


# ── a sugestão ───────────────────────────────────────────────────────────────────────────────────────────────────────
CATALOGO = {
    "1": {"codigo": "SP-CAB-001", "nome": "Cabo solar 6 mm preto", "familia": "Cabos", "criticidade": "2.Necessário",
          "curva": "B"},
    "2": {"codigo": "SP-CAB-002", "nome": "Cabo solar 6 mm vermelho", "familia": "Cabos", "criticidade": "2.Necessário",
          "curva": "B"},
    "3": {"codigo": "SP-CAB-003", "nome": "Cabo de comunicação RS485", "familia": "Cabos", "criticidade": "3.Importante",
          "curva": "C"},
    "4": {"codigo": "SP-PEL-001", "nome": "Fusível 10A gPV", "familia": "Proteção Elétrica", "criticidade": "1.Essencial",
          "curva": "A"},
    "5": {"codigo": "SP-PEL-001-AV", "nome": "[AVARIADO] Fusível 10A gPV", "familia": "Proteção Elétrica",
          "criticidade": "4.Opcional", "curva": "C", "avariado": True},
    "6": {"codigo": "SP-INS-001", "nome": "Conector MC4 macho", "familia": "Instalação", "criticidade": "", "curva": ""},
    "7": {"codigo": "SP-INS-002", "nome": "Conector MC4 fêmea", "familia": "Instalação", "criticidade": "", "curva": ""},
    "8": {"codigo": "SP-INS-003", "nome": "Abraçadeira de nylon", "familia": "Instalação", "criticidade": "4.Opcional",
          "curva": "C"},
    "9": {"codigo": "SP-INS-004", "nome": "Fita isolante", "familia": "Instalação", "criticidade": "4.Opcional", "curva": "B"},
    "10": {"codigo": "SP-INS-005", "nome": "Terminal tubular", "familia": "Instalação", "criticidade": "4.Opcional",
           "curva": "C"},
}


def _sug(nome, catalogo=CATALOGO):
    return CU.sugerir_classificacao(nome, CU.indice(catalogo))


def test_a_classificacao_mais_votada_das_parecidas():
    """As mesmas parecidas da sigla votam, com o quanto se parecem, no Tipo (a Família), na Classificação 1 (a Criticidade) e na
    Classificação 2 (a letra da Curva): as duas de cabo solar 6 mm vencem a de comunicação."""
    s = _sug("Cabo solar 6 mm azul")
    assert s["familia"] == "Cabos"
    assert s["campos"] == {"tipo": {"valor": "Cabos", "chave": "cabos", "por": "parecidas"},
                           "classificacao_1": {"valor": "2.Necessário", "chave": "2", "por": "parecidas"},
                           "classificacao_2": {"valor": "B", "chave": "B", "por": "parecidas"}}


def test_sem_voto_a_classificacao_vem_da_mais_comum_da_familia():
    """As parecidas (os conectores MC4) não têm criticidade nem curva: a Classificação 1 e a 2 vêm da mais comum na Família
    sugerida (Instalação: 4.Opcional nas três; a curva C em duas, a B em uma)."""
    s = _sug("Conector MC4")
    assert s["campos"]["tipo"] == {"valor": "Instalação", "chave": "instalacao", "por": "parecidas"}
    assert s["campos"]["classificacao_1"] == {"valor": "4.Opcional", "chave": "4", "por": "familia"}
    assert s["campos"]["classificacao_2"] == {"valor": "C", "chave": "C", "por": "familia"}


def test_sem_parecida_nada_e_sugerido_e_a_avariada_nao_vota():
    assert _sug("Xyzw qwerty") == {"campos": {}, "familia": ""}
    assert _sug("") == {"campos": {}, "familia": ""}
    # a avariada do fusível (4.Opcional, C) não vota: a sugestão é a do fusível bom
    s = _sug("Fusível 10A")
    assert s["campos"]["classificacao_1"]["valor"] == "1.Essencial" and s["campos"]["classificacao_2"]["valor"] == "A"
    # sem a Família na parecida, o Tipo não se sugere, e sem o Tipo a Família não completa nada
    sem_familia = {"1": dict(CATALOGO["6"], familia=""), "2": dict(CATALOGO["7"], familia="")}
    assert _sug("Conector MC4", sem_familia) == {"campos": {}, "familia": ""}


def test_a_curva_que_nao_e_letra_nao_e_sugerida():
    """A curva do livro que não é uma letra (o "1.Avariado", se viesse) não tem chave e não vota: nunca escolheria sozinha."""
    cat = {"1": dict(CATALOGO["6"], curva="1.Avariado", criticidade="2.Necessário"), "2": CATALOGO["4"]}
    s = _sug("Conector MC4", cat)
    assert "classificacao_2" not in s["campos"] and s["campos"]["classificacao_1"]["chave"] == "2"


def test_a_avariada_leva_o_tipo_e_a_criticidade_da_peca_boa():
    """O -AV é a mesma peça, avariada: o Tipo e a Classificação 1 da boa (pelo ID; sem ele, pelo Código). O Rank não: o da boa
    não é o da avariada."""
    pelo_id = CU.classificacao_da_boa({"ID do item": "4", "Código": "SP-PEL-001"}, CATALOGO)
    assert pelo_id == {"campos": {"tipo": {"valor": "Proteção Elétrica", "chave": "protecao eletrica", "por": "boa"},
                                  "classificacao_1": {"valor": "1.Essencial", "chave": "1", "por": "boa"}},
                       "familia": "Proteção Elétrica"}
    assert CU.classificacao_da_boa({"ID do item": "None", "Código": " sp-pel-001 "}, CATALOGO) == pelo_id
    assert CU.classificacao_da_boa({"ID do item": "999"}, CATALOGO) == {"campos": {}, "familia": ""}


# ── o cadastrar com o Tipo e as Classificações ──────────────────────────────────────────────────────────────────────

def _opcoes(falso):
    return CL.opcoes(falso.classificacoes())


def test_o_cadastrar_manda_os_ids_e_a_decisao_guarda_as_descricoes(cur):
    """Os ids conferidos vão ao `criar_peca` (só os que vieram); a decisão guarda as DESCRIÇÕES (cifradas, com a unidade); o
    texto e "Já decididas" lembram de completar no Fracttal só o que ficou "sem"."""
    falso = _falso()
    r = CU.decidir(cur.config, "C-1", "L-2", "cadastrar", sigla="CAB", nome="Cabo azul 6 mm", unidade="METRO", estoque=falso,
                   pessoa=PESSOA, grupos={"tipo": "318452", "classificacao_1": "", "classificacao_2": "364873"},
                   opcoes_grupos=lambda: _opcoes(falso))
    assert falso._catalogo[r["id_item"]]["grupos"] == {"id_group": 318452, "id_group_2": 364873}
    assert r["texto"] == "Peça cadastrada no Fracttal: SP-CAB-013. Complete no Fracttal: Classificação 1."
    d = F.ler(cur.config, forcar=True)[F.ABA_CURADORIA][0]
    assert F.decifrar(cur.config, F.ABA_CURADORIA, d) == {"unidade": "METRO",
                                                           "grupos": {"tipo": "Cabos", "classificacao_2": "2. Rank A"}}
    assert "Cabos" not in json.dumps(d) and "Rank" not in json.dumps(d)            # só cifrado
    p = {x["chave_linha"]: x for x in CU.pendencias(cur.config)}["L-2"]
    assert p["decisao"]["grupos"] == {"tipo": "Cabos", "classificacao_2": "2. Rank A"}
    assert p["completar_no_fracttal"] == "Complete no Fracttal: Classificação 1"
    # os três: nada a lembrar dos grupos
    r = CU.decidir(cur.config, "C-1", "L-3", "cadastrar", sigla="CAB", nome="Conector", unidade="UNIDADE", estoque=falso,
                   pessoa=PESSOA, grupos={"tipo": "318460", "classificacao_1": "289064", "classificacao_2": "364874"},
                   opcoes_grupos=_opcoes(falso))
    assert r["texto"] == "Peça cadastrada no Fracttal: SP-CAB-014."
    p = {x["chave_linha"]: x for x in CU.pendencias(cur.config)}["L-3"]
    assert p["completar_no_fracttal"] == ""


def test_o_id_fora_das_opcoes_e_recusado_antes_do_fracttal(cur):
    falso = _falso()
    with pytest.raises(ValueError, match="não está nas opções do Fracttal"):
        CU.decidir(cur.config, "C-1", "L-2", "cadastrar", sigla="CAB", nome="Cabo azul 6 mm", unidade="METRO",
                   estoque=falso, pessoa=PESSOA, grupos={"tipo": "999999"}, opcoes_grupos=lambda: _opcoes(falso))
    assert falso.chamadas == ["classificacoes"] and falso._catalogo == {}
    assert F.ler(cur.config, forcar=True)[F.ABA_CURADORIA] == []
    with pytest.raises(ValueError):                         # sem as opções, o id não passa
        CU.decidir(cur.config, "C-1", "L-2", "cadastrar", sigla="CAB", nome="Cabo azul 6 mm", unidade="METRO",
                   estoque=falso, pessoa=PESSOA, grupos={"tipo": "318452"})
    assert falso._catalogo == {}


def test_a_reserva_guarda_os_grupos_e_a_nova_tentativa_tem_de_repetir(cur):
    """O `criar_peca` criou e perdeu a resposta: a peça no Fracttal tem os grupos da 1ª tentativa. A nova tentativa com outro
    Tipo é `Conflito` (a decisão registraria o que não está lá); com os mesmos, acha a peça pelo código e não cria outra."""
    from nexus.pcm.inventario.erros import Conflito
    falso = _falso(perder_resposta={"criar_peca"})
    base = dict(sigla="CAB", nome="Cabo azul 6 mm", unidade="METRO", estoque=falso, pessoa=PESSOA,
                opcoes_grupos=lambda: _opcoes(falso))
    with pytest.raises(ConnectionError):
        CU.decidir(cur.config, "C-1", "L-2", "cadastrar", grupos={"tipo": "318452"}, **base)
    reserva = {x["chave_linha"]: x for x in CU.pendencias(cur.config)}["L-2"]["reserva"]
    assert reserva["grupos"] == {"tipo": "318452"}
    with pytest.raises(Conflito, match="o Tipo ou a Classificação"):
        CU.decidir(cur.config, "C-1", "L-2", "cadastrar", grupos={"tipo": "318460"}, **base)
    with pytest.raises(Conflito):
        CU.decidir(cur.config, "C-1", "L-2", "cadastrar", **base)                   # "sem" também é outro dado
    r = CU.decidir(cur.config, "C-1", "L-2", "cadastrar", grupos={"tipo": "318452"}, **base)
    assert r["criada"] is False and r["codigo"] == "SP-CAB-013" and len(falso._catalogo) == 1


def test_a_avariada_cadastrada_leva_os_grupos(cur):
    _o_bom_sem_av(cur)
    falso = _falso()
    r = CU.decidir(cur.config, "C-1", "L-6", "cadastrar", estoque=falso, pessoa=PESSOA,
                   grupos={"tipo": "318452", "classificacao_2": "364870"}, opcoes_grupos=lambda: _opcoes(falso))
    assert r["codigo"] == "SP-3-AV" and falso._catalogo[r["id_item"]]["grupos"] == {"id_group": 318452, "id_group_2": 364870}
    assert r["texto"].endswith("Complete no Fracttal: Classificação 1.")
    p = {x["chave_linha"]: x for x in CU.pendencias(cur.config)}
    assert p["L-7"]["classificacao"]["campos"]["tipo"]["por"] == "boa"             # a outra avariada: o Tipo da SP-2 boa


def test_a_pendencia_traz_a_classificacao_sugerida(cur):
    """O achado traz a sugestão pelas parecidas (o CABO, "Cabo azul 6 mm", parece o "Cabo 6 mm" do catálogo do App); o genérico
    não cadastra e não traz."""
    _semear(cur.extensions["nexus_dados_sessao"], novas={2: ("2.Necessário", "B")})
    _so(cur, PECA_DA_LISTA, CABO)
    p = {x["chave_linha"]: x for x in CU.pendencias(cur.config)}
    assert p["L-2"]["classificacao"]["campos"] == {
        "tipo": {"valor": "Cabos", "chave": "cabos", "por": "parecidas"},
        "classificacao_1": {"valor": "2.Necessário", "chave": "2", "por": "parecidas"},
        "classificacao_2": {"valor": "B", "chave": "B", "por": "parecidas"}}


# ── a ponte: as opções e o cadastrar com os ids ──────────────────────────────────────────────────────────────────────

def _pcm_com_fracttal(cur, monkeypatch, falso, email="pessoa.teste@exemplo.com"):
    from test_pcm_inventario_estoque import com_o_fracttal
    monkeypatch.setattr(E, "estoque_da_sessao", lambda app: falso)
    _no_setor(monkeypatch, SID.PCM)
    return com_o_fracttal(cur, _pessoa_ms(cur), email)


def test_a_ponte_serve_as_opcoes_com_a_chave(cur, monkeypatch):
    falso = _falso()
    c = _pcm_com_fracttal(cur, monkeypatch, falso)
    r = c.get(OPCOES)
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store" and r.get_json()["ok"] is True
    ops = r.get_json()["opcoes"]
    assert ops["tipo"][0] == {"id": "318452", "descricao": "Cabos", "chave": "cabos"}
    assert [(o["descricao"], o["chave"]) for o in ops["classificacao_2"]] == [("1.Avariado", ""), ("2. Rank A", "A"),
                                                                              ("3. Rank B", "B")]
    assert c.get(OPCOES).status_code == 200 and falso.chamadas == ["pecas_com_grupos"]     # a cópia de 1 h


def test_a_ponte_das_opcoes_recusa_como_as_outras(cur, monkeypatch, logado):
    """A senha de administrador não é uma pessoa (409), sem o login do Fracttal é 401 com o link, a conta do Fracttal de outra
    pessoa é 409, outro setor é 403 e sem login no Nexus nem chega; e o 429 do Fracttal é 429."""
    from test_pcm_inventario_estoque import com_o_fracttal
    falso = _falso()
    monkeypatch.setattr(E, "estoque_da_sessao", lambda app: falso)
    com_o_fracttal(cur, logado, "outra.pessoa@exemplo.test")
    r = logado.get(OPCOES)
    assert r.status_code == 409 and "senha de administrador" in r.get_json()["erro"]
    _no_setor(monkeypatch, SID.PCM)
    r = _pessoa_ms(cur).get(OPCOES)
    assert r.status_code == 401 and "/os/login?next=" in r.get_json()["login"]
    r = com_o_fracttal(cur, _pessoa_ms(cur), "outra.pessoa@exemplo.test").get(OPCOES)
    assert r.status_code == 409 and "outra conta" in r.get_json()["erro"]
    _no_setor(monkeypatch, SID.PERFORMANCE)
    assert com_o_fracttal(cur, _pessoa_ms(cur)).get(OPCOES).status_code == 403
    assert cur.test_client().get(OPCOES).status_code in (302, 401)
    assert falso.chamadas == []
    monkeypatch.setattr(E, "estoque_da_sessao", lambda app: _falso(limite_em=1))
    _no_setor(monkeypatch, SID.PCM)
    assert com_o_fracttal(cur, _pessoa_ms(cur)).get(OPCOES).status_code == 429


def test_a_ponte_cadastra_com_os_ids_e_recusa_o_de_fora(cur, monkeypatch):
    falso = _falso()
    c = _pcm_com_fracttal(cur, monkeypatch, falso)
    corpo = {"contagem": "C-1", "linha": "L-2", "sigla": "CAB", "nome": "Cabo azul 6 mm", "unidade": "METRO"}
    r = c.post(CADASTRAR, data={**corpo, "tipo": "318452", "classificacao_1": "777"})
    assert r.status_code == 400 and "não está nas opções" in r.get_json()["erro"] and falso._catalogo == {}
    r = c.post(CADASTRAR, data={**corpo, "tipo": "318452", "classificacao_1": "289062", "classificacao_2": ""})
    assert r.status_code == 200 and "Complete no Fracttal: Classificação 2." in r.get_json()["mensagem"]
    (criada,) = falso._catalogo.values()
    assert criada["grupos"] == {"id_group": 318452, "id_group_1": 289062}
    assert falso.chamadas.count("pecas_com_grupos") == 1                    # a conferência usa a mesma cópia de 1 h


# ── a tela ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_tela_tem_as_tres_selecoes_com_a_sugestao(cur, monkeypatch):
    """A pessoa do PCM: as três seleções no cadastrar (escondidas e desligadas até a ponte mandar as opções), a chave da sugerida
    em `data-sug-*`, de onde ela veio, o script, e o endereço da ponte pela raiz. Os dados da peça não falam mais do grupo."""
    _semear(cur.extensions["nexus_dados_sessao"], novas={2: ("2.Necessário", "B")})
    _so(cur, PECA_DA_LISTA, CABO, ACHADO_COM_DADOS)
    _no_setor(monkeypatch, SID.PCM)
    html = _pessoa_ms(cur).get(URL).get_data(as_text=True)
    card = _cartao(html, "Cabo azul 6 mm")
    caixa = re.search(r"<fieldset[^>]*data-cu-grupos[^>]*>", card).group(0)
    assert "hidden" in caixa and 'data-sug-tipo="cabos"' in caixa and 'data-sug-classificacao_1="2"' in caixa
    assert 'data-sug-classificacao_2="B"' in caixa and "data-reserva" not in caixa
    for campo in ("tipo", "classificacao_1", "classificacao_2"):
        assert re.search(rf'<select[^>]*name="{campo}"[^>]*disabled', card), campo
    assert "Sugeridos: Tipo <b>Cabos</b> (pelas peças parecidas)" in card and "<b>Rank B</b>" in card
    assert "data-cu-grupos-sem" in card
    assert 'data-cu-classificacoes="/os/_nexus/inventario/classificacoes"' in html and "pcm-curadoria-grupos.js" in html
    # o achado sem parecida com classificação diz que não há sugestão
    assert "Nenhuma sugestão" in _cartao(html, "Disjuntor sem etiqueta")


def test_sem_a_ponte_a_tela_diz_que_fica_para_o_fracttal(cur, logado):
    """Quem entrou pela senha de administrador não tem o login do Fracttal (e não cadastra): sem as seleções nem o script, e a
    tela diz que o Tipo e a Classificação ficam para o Fracttal."""
    html = logado.get(URL).get_data(as_text=True)
    card = _cartao(html, "Cabo azul 6 mm")
    assert "data-cu-grupos" not in card and 'name="tipo"' not in card
    assert "O Tipo e a Classificação ficam para a tela do Fracttal" in card
    assert "pcm-curadoria-grupos.js" not in html


def test_a_reserva_vem_escolhida_na_tela(cur, monkeypatch):
    falso = _falso(perder_resposta={"criar_peca"})
    with pytest.raises(ConnectionError):
        CU.decidir(cur.config, "C-1", "L-2", "cadastrar", sigla="CAB", nome="Cabo azul 6 mm", unidade="METRO", estoque=falso,
                   pessoa=PESSOA, grupos={"classificacao_2": "364873"}, opcoes_grupos=lambda: _opcoes(falso))
    _no_setor(monkeypatch, SID.PCM)
    card = _cartao(_pessoa_ms(cur).get(URL).get_data(as_text=True), "Cabo azul 6 mm")
    caixa = re.search(r"<fieldset[^>]*data-cu-grupos[^>]*>", card).group(0)
    assert 'data-reserva="1"' in caixa and 'data-res-classificacao_2="364873"' in caixa and 'data-res-tipo=""' in caixa
    assert "Vêm escolhidos os da tentativa anterior" in card


def test_o_script_das_selecoes_usa_a_raiz_e_os_atributos():
    """O script lê o endereço do atributo (posto pela raiz) e o passa pelo `nexusRota`; desliga e esconde sem as opções."""
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "nexus/static/pcm-curadoria-grupos.js").read_text(encoding="utf-8")
    assert 'window.nexusRota(fonte.getAttribute("data-cu-classificacoes"))' in js
    assert "'/os" not in js and '"/os' not in js
    for attr in ("data-reserva", "data-res-", "data-sug-", "data-cu-grupos-sem", "(sugerida)"):
        assert attr in js, attr
