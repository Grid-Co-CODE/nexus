"""O de-para do tempo real gravando a estrutura das usinas (20/10/2026). Levi, com o protótipo do "Modo de-para": "Boa,
é isso mesmo. Implementa no tempo real e adapta na base o de-para". A plataforma lê o estado e manda um REMENDO por
chave do supervisório pelas rotas `/t/base/equipamentos/depara/estado` e `/depara/salvar`; o Nexus, dono do livro
`nexus_estrutura_usina`, confere o selo, semeia pela aba a chave que ainda não tem, deriva o `equipamento_id` do código
(conferido na dimensão de equipamento), recalcula o kWp da usina inteira pela regra do Levi e só marca no lugar da aba a
chave que, depois do remendo, difere da aba apenas pela regra do de-para.

Os números são os da frota (banco e aba lidos por GET em 20/10/2026): a Itajá (usina 93, potência real 2,596 MWp, 8
inversores de 19 strings em duas chaves, a UFV e as UG na chave "Itajá"), a Pharma II (usina 108, 0,99 MWp, 6 inversores
de 14 e 13 strings, a árvore nova do Fracttal THPN-PHS100 fora da foto de 22/09, sem usina na dimensão), a Coração 2
(usina 77, nada no Nexus, a "Coração 2 (112)" com 4 inversores na aba), a Assis Chateaubriand Skid 1 (a chave com
espaço DUPLO na aba e na API PV) e a Aquiraz 1 (Salvales, só a potência contratual). Nenhum teste vai à rede: o banco é
o falso."""
import json

import pytest
from pg_falso import ApiPGFalsa
from test_campo_visao import _aba

from conftest import SENHA_TESTE
from nexus import create_app
from nexus.cadastro import estrutura_usina as E
from nexus.cadastro.cifra import gerar_chave
from nexus.cadastro.servico import Carga
from nexus.dados import dominios as DOM
from nexus.dados import equipamento as EQ

BASE = "http://pg.falso"
ESTADO, SALVAR = "/t/base/equipamentos/depara/estado", "/t/base/equipamentos/depara/salvar"
ITAJA, PHARMA, AQUIRAZ, SEM_POT, CORACAO, ASSIS = 93, 108, 21, 5, 77, 212
CH1, CH2, CH_USINA = "Itaja 1 (551)", "Itaja 2 (552)", "Itajá"
CH_COR = "Coração 2 (112)"
ASSIS_ABA, ASSIS_NEXUS = "Assis Chateaubriand  Skid 1 (79)", "Assis Chateaubriand Skid 1 (79)"


def _membro(codigo, usina_id=None, eid=None):
    return {"equipamento_id": eid or EQ.equipamento_id(codigo), "codigo": codigo, "descricao": None,
            "usina_id": usina_id, "familia": EQ.familia(codigo)}


# a dimensão de equipamento como o banco tem: o ID derivado do código; a Pharmas nova (THPN-PHS100) SEM usina
DIM = ([_membro("ITA100-CABN1", ITAJA), _membro("ITA100-CABN2", ITAJA), _membro("ITA100-QGBT1", ITAJA)]
       + [_membro(f"ITA100-INVR{n}.{m}", ITAJA) for n in (1, 2) for m in range(1, 6)]
       + [_membro("THPN-PHS100-CABN2")] + [_membro(f"THPN-PHS100-INVR2.{m}") for m in range(1, 7)]
       + [_membro("SALE-SVL100-CABN1", AQUIRAZ)] + [_membro(f"SALE-SVL100-INVR1.{m}", AQUIRAZ) for m in (1, 2)]
       + [_membro("SEM100-INVR1.1", SEM_POT)]
       + [_membro("THPN-COR100-CABN1", CORACAO)] + [_membro(f"COR100-INVR2.{m}", CORACAO) for m in range(1, 5)]
       + [_membro("THPN-ACB100-CABN1", ASSIS)] + [_membro(f"THPN-ACB100-INVR1.{m}", ASSIS) for m in range(1, 5)]
       + [_membro("ITA100-INVR3.1", ITAJA, eid=123)])          # a dimensão com outro ID: não liga (nunca chutar)

COLS = ("Cliente", "Usina", "Usina Supervisório", "Usina Fractall", "Equipamento", "Equipamento Supervisório",
        "Equipamento Parente", "Potência (kWp)", "N de Inversores", "Strings Ativas", "Full O&M", "String Box")


def _l(**kw):
    """Uma linha da aba Equipamentos com todas as colunas (o `_aba` do banco falso tira o cabeçalho da 1ª linha)."""
    return {c: kw.get(c) for c in COLS}


def _aba_itaja(ufv_kwp=2596.16, ufv_inv=None, **outro):
    """A chave "Itajá" na aba como ela é (GET de 20/10/2026): a UFV com a soma das UG (2.596,16) e sem "N de Inversores",
    e as duas UG de 1.298,08, sem "Usina Supervisório"."""
    comum = dict({"Cliente": "Thopen", "Usina": "Itajá", "Full O&M": "Sim", "String Box": "Não"}, **outro)
    return [_l(**comum, **{"Equipamento": "UFV", "Potência (kWp)": ufv_kwp, "N de Inversores": ufv_inv}),
            _l(**comum, **{"Equipamento": "UG 01", "Equipamento Parente": "UFV", "Potência (kWp)": 1298.08}),
            _l(**comum, **{"Equipamento": "UG 02", "Equipamento Parente": "UFV", "Potência (kWp)": 1298.08})]


def _aba_itaja_inv(**outro):
    """Os 8 inversores da Itajá na aba: "Itaja 1 (551)" e "Itaja 2 (552)", 4 cada, 324,52 kWp e 19 strings."""
    return [_l(**dict({"Cliente": "Thopen", "Usina": "Itajá", "Usina Supervisório": ch, "Equipamento": f"Inversor {n}.{m}",
                       "Equipamento Supervisório": f"INVERSOR0{m}", "Equipamento Parente": f"UG 0{n}",
                       "Potência (kWp)": 324.52, "Strings Ativas": 19, "Full O&M": "Sim", "String Box": "Não"}, **outro))
            for n, ch in ((1, CH1), (2, CH2)) for m in range(1, 5)]


# a Pharma II na aba (GET de 20/10/2026): a UFV e a UG 01 sem kWp, os 6 inversores sem kWp, 14 e 13 strings
ABA_PHARMA = ([_l(Cliente="Thopen", Usina="Pharma II", **{"Usina Supervisório": "Pharma 2", "Equipamento": "UFV",
                                                          "N de Inversores": 6, "Full O&M": "Sim", "String Box": "Não"}),
               _l(Cliente="Thopen", Usina="Pharma II", **{"Usina Supervisório": "Pharma 2", "Equipamento": "UG 01",
                                                          "Equipamento Parente": "UFV", "N de Inversores": 6,
                                                          "Full O&M": "Sim", "String Box": "Não"})]
              + [_l(Cliente="Thopen", Usina="Pharma II", **{"Usina Supervisório": "Pharma 2", "Equipamento": f"Inversor 1.{m}",
                                                            "Equipamento Supervisório": f"INVERSOR0{m}",
                                                            "Equipamento Parente": "UG 01", "Strings Ativas": s,
                                                            "Full O&M": "Sim", "String Box": "Não"})
                 for m, s in zip(range(1, 7), (14, 14, 14, 14, 13, 13))])
# a Aquiraz 1 (Salvales): a UFV e 2 inversores de 10 strings debaixo da "UG 01" (só no Equipamento Parente)
ABA_AQUIRAZ = ([_l(Cliente="Thopen", Usina="Aquiraz 1", **{"Usina Supervisório": "Aquiraz 1", "Equipamento": "UFV",
                                                           "Potência (kWp)": 3260.0, "Full O&M": "Não", "String Box": "Não"})]
               + [_l(Cliente="Thopen", Usina="Aquiraz 1", **{"Usina Supervisório": "Aquiraz 1", "Equipamento": f"Inversor 1.{m}",
                                                             "Equipamento Supervisório": f"INV{m}", "Equipamento Parente": "UG 01",
                                                             "Potência (kWp)": 1600.0, "Strings Ativas": 10,
                                                             "Full O&M": "Não", "String Box": "Não"}) for m in (1, 2)])
# a Coração 2 (GET de 20/10/2026): a UFV e a UG 01 na chave de exibição "Coração 2" e os 4 inversores na "Coração 2
# (112)", com o nome "Inversor 1.x" (o Fracttal tem COR100-INVR2.1 a 2.4), 250 kWp, 20 strings, Full O&M Sim
ABA_CORACAO = ([_l(Cliente="Thopen", Usina="Coração 2", Equipamento="UFV", **{"Potência (kWp)": 1000.0,
                                                                              "N de Inversores": 4, "Full O&M": "Sim",
                                                                              "String Box": "Não"}),
                _l(Cliente="Thopen", Usina="Coração 2", Equipamento="UG 01", **{"Equipamento Parente": "UFV",
                                                                                "Potência (kWp)": 1000.0, "Full O&M": "Sim",
                                                                                "String Box": "Não"})]
               + [_l(Cliente="Thopen", Usina="Coração 2", **{"Usina Supervisório": CH_COR, "Equipamento": f"Inversor 1.{m}",
                                                             "Equipamento Supervisório": f"INVERSOR0{m}",
                                                             "Equipamento Parente": "UG 01", "Potência (kWp)": 250.0,
                                                             "Strings Ativas": 20, "Full O&M": "Sim", "String Box": "Não"})
                  for m in range(1, 5)])
ABA = _aba_itaja() + _aba_itaja_inv() + ABA_PHARMA + ABA_AQUIRAZ + ABA_CORACAO


@pytest.fixture(autouse=True)
def _sem_copias():
    E._CACHE.clear()
    yield
    E._CACHE.clear()


@pytest.fixture
def banco():
    api = ApiPGFalsa()
    _aba(api, "bd_performance", "Equipamentos", ABA)
    _aba(api, "nexus_equipamentos", "dim_equipamento", DIM)
    return api


@pytest.fixture
def cfg():
    return {"GRIDCO_SQL_TOKEN": "token-de-teste", "NEXUS_PESSOA_HMAC": "chave-de-teste"}


def _usina(id_, ordem, nome, codigo, **pot):
    return {"id": str(id_), "ordem": ordem, "valores": {"nome": nome, "codigo": codigo, "cliente": "1",
                                                        "status": "OPERAÇÃO", "uf": "RN", **pot}}


@pytest.fixture
def app_dp(tmp_path, banco):
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA_TESTE,
                      "NEXUS_CHAVE_CADASTRO": gerar_chave(), "NEXUS_ARMAZEM_LOCAL": str(tmp_path / "cadastro.json"),
                      "NEXUS_DADOS": str(tmp_path / "dados")})
    app.config.update({"TESTING": True, "SESSION_COOKIE_SECURE": False, "GRIDCO_DB_API": BASE,
                       "GRIDCO_SQL_TOKEN": "token-de-teste", "NEXUS_PESSOA_HMAC": "chave-de-teste"})
    app.extensions["nexus_dados_sessao"] = banco
    from nexus.cadastro.telas import servico
    with app.app_context():
        # o Registro mestre como o banco tem (aba 450, 20/10/2026): a Aquiraz 1 (Salvales) é uma das 68 sem a real; a
        # Coração 1 e 2 tem a real de 3,25 MWp (é só a Coração 1: a aba soma 4.250; o Levi decidiu "aplica direto")
        servico().aplicar_carga(Carga(
            entidades={"clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Thopen"}}],
                       "usinas": [_usina(ITAJA, 1, "Itajá 1 e 2", "ITA100", potencia_real=2.596, potencia_contratual=2.6),
                                  _usina(PHARMA, 2, "Pharmas 2", "THPN-PHS200", potencia_real=0.99,
                                         potencia_contratual=1.0),
                                  _usina(AQUIRAZ, 3, "Aquiraz 1 (Salvales)", "SALE-SVL100", potencia_contratual=3.26),
                                  _usina(SEM_POT, 4, "Usina sem potência", "SEM100"),
                                  _usina(CORACAO, 5, "Coração 1 e 2", "THPN-COR100", potencia_real=3.25),
                                  _usina(ASSIS, 6, "Assis Chateaubriand", "THPN-ACB100", potencia_contratual=1.2936)]},
            listas={"status_usina": ["OPERAÇÃO"], "uf": ["RN"]}))
    yield app
    app.extensions.pop("nexus_dados_sessao", None)


@pytest.fixture
def cli(app_dp):
    c = app_dp.test_client()
    assert c.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    return c


def _u(cfg, banco, uid):
    return E.da_usina(E.ler(BASE, banco, forcar=True), uid)


def _monta_itaja(cfg, banco, exibicao="Itajá", sem=(), esup_vazio=()):
    """A Itajá como o "Ligar pela aba" de 13/10 deixou no banco: três chaves (a da usina, "Itajá", com as duas UG, e uma
    por planta com 4 inversores de 19 strings), Full O&M Sim, o nome de exibição "Itajá", o kWp da aba (324,52) e
    nenhum código do Fracttal. `sem` = inversores que o Nexus não tem; `esup_vazio` = os que estão sem o nome no
    supervisório (como os 214 da aba de 13/10)."""
    s1 = E.ligar_supervisorio(ITAJA, CH_USINA, cfg, BASE, banco, exibicao_aba=exibicao)["supervisorio_id"]
    s2 = E.ligar_supervisorio(ITAJA, CH1, cfg, BASE, banco, exibicao_aba=exibicao)["supervisorio_id"]
    s3 = E.ligar_supervisorio(ITAJA, CH2, cfg, BASE, banco, exibicao_aba=exibicao)["supervisorio_id"]
    dados = {"chaves": [{"supervisorio_id": s, "full_om": True, "string_box": False, "usina_exibicao": exibicao,
                         "principal": s == s1, "substitui_aba": False} for s in (s1, s2, s3)],
             "cabines": [{"k": "n1", "nome": "UG 01", "potencia_kwp": 1298.08},
                         {"k": "n2", "nome": "UG 02", "potencia_kwp": 1298.08}],
             "inversores": [{"nome": f"Inversor {n}.{m}", "chave": s2 if n == 1 else s3, "cabine": f"n{n}",
                             "equipamento_supervisorio": "" if f"Inversor {n}.{m}" in esup_vazio else f"INVERSOR0{m}",
                             "potencia_kwp": 324.52, "strings_esperadas_qtd": 19}
                            for n in (1, 2) for m in range(1, 5) if f"Inversor {n}.{m}" not in sem]}
    E.salvar_usina(ITAJA, dados, E.selo(_u(cfg, banco, ITAJA)), cfg, BASE, banco)
    return s1, s2, s3


def _monta_pharma(cfg, banco):
    """A Pharma II do banco: uma chave (a da usina, exibição "Pharma II", Full O&M Sim), a UG 01 da aba sem kWp e 6
    inversores de 14, 14, 14, 14, 13 e 13 strings."""
    sid = E.ligar_supervisorio(PHARMA, "Pharma 2", cfg, BASE, banco, exibicao_aba="Pharma II")["supervisorio_id"]
    dados = {"chaves": [{"supervisorio_id": sid, "full_om": True, "string_box": False, "usina_exibicao": "Pharma II",
                         "principal": True, "substitui_aba": False}],
             "cabines": [{"k": "n1", "nome": "UG 01"}],
             "inversores": [{"nome": f"Inversor 1.{m}", "chave": sid, "cabine": "n1",
                             "equipamento_supervisorio": f"INVERSOR0{m}", "strings_esperadas_qtd": s}
                            for m, s in zip(range(1, 7), (14, 14, 14, 14, 13, 13))]}
    E.salvar_usina(PHARMA, dados, E.selo(_u(cfg, banco, PHARMA)), cfg, BASE, banco)
    return sid


def _estado(cli, **q):
    r = cli.get(ESTADO, query_string=q)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _item_itaja(cli, chave=CH1, n=1, conferido=True, quais=range(1, 5), **extra):
    """O que a tela manda pela Itajá: a chave, a usina, o selo do estado e, por inversor, o nome no supervisório, o NOME
    do cadastro (a tela passou a mandar em 20/10/2026), as strings, a CABN e o código do Fracttal."""
    usina = next(u for u in _estado(cli, chaves=chave)["usinas"] if u["usina_id"] == ITAJA)
    return {"usina_supervisorio": chave, "usina_id": ITAJA, "selo": usina["selo"],
            "inversores": [dict({"equipamento_supervisorio": f"INVERSOR0{m}", "nome": f"Inversor {n}.{m}", "strings": 19,
                                 "cabine_codigo_fracttal": f"ITA100-CABN{n}", "codigo_fracttal": f"ITA100-INVR{n}.{m}",
                                 "conferido": conferido}, **extra) for m in quais]}


def _salvar(cli, itens, **headers):
    return cli.post(SALVAR, json={"itens": itens}, headers=headers)


def _livro(banco):
    return {k: banco.linhas(E.LIVRO, a) for k, a in (("sup", E.ABA_SUP), ("cab", E.ABA_CAB), ("inv", E.ABA_INV),
                                                       ("visao", E.ABA_VISAO))}


def _marca(banco):
    return {s["usina_supervisorio"]: s["substitui_aba"] for s in _livro(banco)["sup"]}


def _avisos(j, tipo):
    """Os textos dos avisos de um tipo: o aviso é {usina_id, usina_supervisorio, tipo, texto} (o contrato)."""
    assert all(set(a) == {"usina_id", "usina_supervisorio", "tipo", "texto"} and a["tipo"] in E.TIPOS_AVISO
               for a in j["avisos"]), j["avisos"]
    return [a["texto"] for a in j["avisos"] if a["tipo"] == tipo]


def _poe_aba(banco, linhas):
    """A aba Equipamentos no banco falso com TODAS as colunas das linhas (o `_aba` pega o cabeçalho só da 1ª), e a cópia
    de 10 minutos da aba esquecida (a próxima rota relê)."""
    cab = list(dict.fromkeys(k for linha in linhas for k in linha))
    banco.workbooks["bd_performance"] = {}
    banco._id("bd_performance", "Equipamentos")["linhas"] = [{"headers": cab, "values": [x.get(c) for c in cab]}
                                                              for x in linhas]
    E._CACHE.pop("aba", None)


# ── a regra do kWp (Levi, 20/10/2026) ────────────────────────────────────────────────────────────────────────────────
def test_itaja_o_kwp_da_usina_inteira_mesmo_salvando_uma_chave(cli, cfg, banco):
    """2.596 kWp ÷ 152 strings (as 8 × 19 da usina, não as 76 da Itaja 1) × 19 = 324,5 por inversor; cabine 1.298,0."""
    _monta_itaja(cfg, banco)
    r = _salvar(cli, [_item_itaja(cli, equipamento_id=999)])      # o ID do pedido não vale: é derivado no servidor
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] and j["erros"] == [] and j["visao_mudou"]
    u = j["usinas"][0]
    assert (u["usina_id"], u["kwp"], u["kwp_de"], u["codigo"]) == (ITAJA, 2596.0, "real", "ITA100")
    assert {i["potencia_kwp"] for i in u["inversores"]} == {324.5} and len(u["inversores"]) == 8
    assert {i["potencia_regra"] for i in u["inversores"]} == {"real_por_string"}      # os da Itaja 2 também
    assert sorted(j["kwp"].values()) == [324.5] * 8
    cab = {c["nome"]: c for c in u["cabines"]}
    assert (cab["UG 01"]["potencia_kwp"], cab["UG 01"]["codigo_fracttal"]) == (1298.0, "ITA100-CABN1")
    assert (cab["UG 02"]["potencia_kwp"], cab["UG 02"]["codigo_fracttal"]) == (1298.0, None)   # soma, sem código
    inv = {i["nome"]: i for i in _livro(banco)["inv"]}
    i11 = inv["Inversor 1.1"]
    assert (i11["codigo_fracttal"], i11["equipamento_id"]) == ("ITA100-INVR1.1", EQ.equipamento_id("ITA100-INVR1.1"))
    assert (i11["fracttal_ligado_por"], bool(i11["conferido_em"])) == ("conferido", True)
    assert inv["Inversor 2.1"]["codigo_fracttal"] is None and inv["Inversor 2.1"]["potencia_kwp"] == 324.5
    # a Itaja 1 só difere da aba pela regra (kWp 324,52 → 324,5) e vale no lugar da aba; a "Itajá" (a da UFV e das UG),
    # também: a UFV do Registro mestre (2.596 contra a soma 2.596,16 da aba) e o "N de Inversores" contado (vazio na
    # aba) são da regra. A Itaja 2 não veio no pedido, mas a regra recalculou o kWp dela (a usina inteira) e ela é
    # conferida junto (a usina vale por inteiro ou nada, 2ª revisão final de 21/10): passa e marca
    assert _marca(banco) == {CH_USINA: 1, CH1: 1, CH2: 1}
    assert j["marcacao"] == [
        {"usina_id": ITAJA, "usina_supervisorio": CH1, "principal": False, "marcada": True, "fora_da_regra": []},
        {"usina_id": ITAJA, "usina_supervisorio": CH_USINA, "principal": True, "marcada": True, "fora_da_regra": []},
        {"usina_id": ITAJA, "usina_supervisorio": CH2, "principal": False, "marcada": True, "fora_da_regra": []}]
    assert _avisos(j, "nao_marcada") == []


def test_pharma_ii_14_e_13_strings_e_a_cabine_pela_cabn(cli, cfg, banco):
    """990 kWp ÷ 82 strings = 12,073 por string: 169,02 (14 strings) e 156,95 (13); a CABN2 vira a "UG 02" e a UG 01
    da aba, que ficou sem inversores e não tem código do Fracttal, sai (decisão 2: a cabine é a CABN). Os códigos
    THPN-PHS100 não têm usina na dimensão (fora da foto de 22/09) e ligam assim mesmo: o que se confere é ser membro."""
    sid = _monta_pharma(cfg, banco)
    usina = _estado(cli, usinas=str(PHARMA))["usinas"][0]
    assert (usina["kwp"], usina["kwp_de"]) == (990.0, "real")
    item = {"usina_supervisorio": "Pharma 2", "usina_id": PHARMA, "selo": usina["selo"],
            "inversores": [{"equipamento_supervisorio": f"INVERSOR0{m}", "nome": f"Inversor 1.{m}",
                            "cabine_codigo_fracttal": "thpn-phs100-cabn2",
                            "codigo_fracttal": f"THPN-PHS100-INVR2.{m}", "conferido": False} for m in range(1, 7)]}
    j = _salvar(cli, [item]).get_json()
    assert j["ok"], j
    u = j["usinas"][0]
    kwp = [i["potencia_kwp"] for i in u["inversores"]]
    assert [round(k, 2) for k in kwp] == [169.02] * 4 + [156.95] * 2 and kwp[0] == 169.024
    # a UG 01 vazia sai (exclusão lógica, conta nas mudanças); a UG 02 fica com 990
    assert [(c["nome"], c["codigo_fracttal"], c["potencia_kwp"], c["potencia_regra"]) for c in u["cabines"]] == [
        ("UG 02", "THPN-PHS100-CABN2", 990.0, "real_por_string")]
    ug01 = next(c for c in _livro(banco)["cab"] if c["nome"] == "UG 01")
    assert (ug01["excluido"], j["cabines_excluidas"]) == ("sim", [{"cabine_id": ug01["cabine_id"], "usina_id": PHARMA,
                                                                    "nome": "UG 01"}])
    assert any(t.startswith("A cabine UG 01 (usina 108) ficou sem inversores e saiu") for t in _avisos(j, "cabine_excluida"))
    # a "Pharma 2" é a chave da usina e só difere da aba pela regra: a UFV do Registro (vazia na aba, 990 no Nexus), a
    # UG pela CABN, a cabine dos inversores e o kWp que a regra calculou. Vale no lugar da aba
    assert j["marcacao"] == [{"usina_id": PHARMA, "usina_supervisorio": "Pharma 2", "principal": True, "marcada": True,
                              "fora_da_regra": []}]
    # o nome do inversor (a coluna do BD) não muda; a sugestão sem Conferido fica marcada assim
    assert [i["nome"] for i in u["inversores"]] == [f"Inversor 1.{m}" for m in range(1, 7)]
    assert {(i["fracttal_ligado_por"], i["conferido_em"]) for i in u["inversores"]} == {("sugestao", None)}
    # a chave está no lugar da aba: a visão leva a UFV, as UG e os inversores, com o Código Fracttal
    visao = _livro(banco)["visao"]
    assert list(visao[0]) == list(E.CAB_VISAO) and E.CAB_VISAO[-1] == "Código Fracttal"
    ug2 = next(x for x in visao if x["Equipamento"] == "UG 02")
    assert (ug2["Código Fracttal"], ug2["Potência (kWp)"], ug2["N de Inversores"]) == ("THPN-PHS100-CABN2", 990, 6)
    assert [x["Equipamento"] for x in visao if x["cabine_id"] and not x["inversor_id"]] == ["UG 02"]    # sem a UG 01
    i1 = next(x for x in visao if x["Equipamento"] == "Inversor 1.1")
    assert (i1["Código Fracttal"], i1["Equipamento Parente"], i1["supervisorio_id"]) == (
        "THPN-PHS100-INVR2.1", "UG 02", sid)
    assert next(x for x in visao if x["Equipamento"] == "UFV")["Código Fracttal"] is None


def test_sem_potencia_real_usa_a_contratual(cli, banco):
    """Decisão 3 do Levi (alterada em 20/10/2026): "onde não tem potência real, vai usar potência contratual". A Aquiraz
    1 (Salvales, SALE-SVL100) tem só a contratual, 3,26 MWp. A chave não está no Nexus e nasce semeada pela aba (a UFV
    está nela: é a chave da usina), com os 2 inversores da aba e a cabine "UG 01" do Equipamento Parente, que a CABN1
    adota."""
    est = _estado(cli, usinas=str(AQUIRAZ), chaves="Aquiraz 1")
    assert est["chaves_sem_usina"] == ["Aquiraz 1"]
    u = est["usinas"][0]
    assert (u["kwp"], u["kwp_de"], u["chaves"], u["inversores"]) == (3260.0, "contratual", [], [])
    item = {"usina_supervisorio": "Aquiraz 1", "usina_id": AQUIRAZ, "selo": u["selo"],
            "inversores": [{"equipamento_supervisorio": f"INV{m}", "nome": f"Inversor 1.{m}", "strings": 10,
                            "cabine_codigo_fracttal": "SALE-SVL100-CABN1", "codigo_fracttal": f"SALE-SVL100-INVR1.{m}",
                            "conferido": True} for m in (1, 2)]}
    j = _salvar(cli, [item]).get_json()
    u = j["usinas"][0]
    assert [(i["nome"], i["potencia_kwp"], i["potencia_regra"]) for i in u["inversores"]] == [
        ("Inversor 1.1", 1630.0, "contratual_por_string"), ("Inversor 1.2", 1630.0, "contratual_por_string")]
    assert [(c["nome"], c["potencia_kwp"], c["potencia_regra"], c["codigo_fracttal"]) for c in u["cabines"]] == [
        ("UG 01", 3260.0, "contratual_por_string", "SALE-SVL100-CABN1")]
    ch = _livro(banco)["sup"][0]
    assert (ch["usina_supervisorio"], ch["usina_exibicao"], ch["principal"], ch["full_om"], ch["substitui_aba"]) == (
        "Aquiraz 1", "Aquiraz 1", 1, 0, 1)
    assert len(_avisos(j, "semeada_pela_aba")) == 1


def test_sem_real_e_sem_contratual_o_kwp_fica_como_estava(cli, cfg, banco):
    """Sem as duas potências no Registro mestre, o kWp e a linhagem ficam como estavam, com o aviso (Levi, 20/10/2026:
    "0 NUNCA por cima de dado; valor que vira 0 também é perda"). Até a 2ª revisão o salvar apagava o kWp da usina
    inteira, o digitado à mão inclusive, e este teste confirmava o apagamento."""
    sid = E.ligar_supervisorio(SEM_POT, "Sem 1", cfg, BASE, banco)["supervisorio_id"]
    E.salvar_usina(SEM_POT, {"inversores": [{"nome": "Inversor 1.1", "chave": sid, "equipamento_supervisorio": "I1",
                                             "potencia_kwp": 100, "strings_esperadas_qtd": 10}]},
                   E.selo(_u(cfg, banco, SEM_POT)), cfg, BASE, banco)
    assert _livro(banco)["inv"][0]["potencia_regra"] == "informada"          # o kWp digitado na tela
    u = _estado(cli, chaves="Sem 1")["usinas"][0]
    assert (u["kwp"], u["kwp_de"]) == (None, None)
    j = _salvar(cli, [{"usina_supervisorio": "Sem 1", "usina_id": SEM_POT, "selo": u["selo"],
                       "inversores": [{"equipamento_supervisorio": "I1", "codigo_fracttal": "SEM100-INVR1.1"}]}]).get_json()
    i = j["usinas"][0]["inversores"][0]
    assert (i["potencia_kwp"], i["potencia_regra"], i["codigo_fracttal"]) == (100.0, "informada", "SEM100-INVR1.1")
    assert j["kwp"] == {str(i["inversor_id"]): 100.0}
    assert [a["usina_id"] for a in j["avisos"] if a["tipo"] == "sem_potencia"] == [SEM_POT]
    assert "ficou como estava" in _avisos(j, "sem_potencia")[0]


def test_inversor_sem_strings_guarda_o_kwp_e_ele_sai_do_registro_antes_de_dividir(cfg, banco):
    """O inversor vivo sem strings corretas guarda o kWp de antes, e esse kWp é DESCONTADO do Registro antes de dividir
    pelos que têm strings: a usina continua somando o Registro (a Sapopema, com 2 dos 20 sem strings, ia a 3.515,6 kWp
    contra 3.196, +10%). Itajá com o Inversor 2.4 sem strings: (2.596 − 324,52) ÷ 133 × 19 nos outros 7."""
    _monta_itaja(cfg, banco)
    u = _u(cfg, banco, ITAJA)
    p = {"inversores": [{"id": i["inversor_id"], "nome": i["nome"], "chave": i["supervisorio_id"],
                         "cabine": f"c{i['cabine_id']}", "equipamento_supervisorio": i["equipamento_supervisorio"],
                         "potencia_kwp": i["potencia_kwp"],
                         "strings_esperadas_qtd": None if i["nome"] == "Inversor 2.4" else 19} for i in u["inversores"]],
         "cabines": [{"id": c["cabine_id"], "k": f"c{c['cabine_id']}", "nome": c["nome"],
                      "potencia_kwp": c["potencia_kwp"]} for c in u["cabines"]],
         "chaves": [{k: s[k] for k in ("supervisorio_id", "usina_exibicao", "principal", "full_om", "string_box",
                                       "substitui_aba")} for s in u["supervisorios"]]}
    E.salvar_usina(ITAJA, p, E.selo(u), cfg, BASE, banco)
    info = {ITAJA: {"nome": "Itajá 1 e 2", "kwp": 2596.0, "kwp_de": "real"}}
    r = E.salvar_depara([{"usina_supervisorio": CH1, "usina_id": ITAJA, "selo": E.selo(_u(cfg, banco, ITAJA)),
                          "inversores": []}], cfg, BASE, banco, info=info, por_codigo={})
    kwp = {i["nome"]: (i["potencia_kwp"], i["potencia_regra"]) for i in r["usinas"][0]["inversores"]}
    assert kwp["Inversor 2.4"] == (324.52, "informada")                   # fora da divisão, como estava
    assert kwp["Inversor 1.1"] == (round((2596 - 324.52) / 133 * 19, 3), "real_por_string")      # 7 × 19 = 133 strings
    assert abs(sum(k for k, _r in kwp.values()) - 2596.0) < 0.01           # a usina soma o Registro
    ug2 = next(c for c in r["usinas"][0]["cabines"] if c["nome"] == "UG 02")
    assert ug2["potencia_kwp"] == round(3 * (2596 - 324.52) / 133 * 19 + 324.52, 3)
    texto = next(a for a in r["avisos"] if a["tipo"] == "sem_strings")
    assert texto["usina_id"] == ITAJA and "Inversor 2.4 (324,52 kWp)" in texto["texto"]
    assert "2.596 kWp − 324,52 kWp = 2.271,48 kWp" in texto["texto"]


def test_sem_strings_que_ja_cobrem_o_registro_recusa_a_usina(cli, cfg, banco):
    """Se o kWp guardado dos inversores sem strings já cobre o Registro, não sobra para dividir: a usina é recusada com o
    motivo, nada é gravado, e a recusa diz a culpada (a tela tira a usina do lote)."""
    sid = _monta_pharma(cfg, banco)
    u = _u(cfg, banco, PHARMA)
    p = {"chaves": [{k: s[k] for k in ("supervisorio_id", "usina_exibicao", "principal", "full_om", "string_box",
                                       "substitui_aba")} for s in u["supervisorios"]],
         "cabines": [{"id": c["cabine_id"], "k": f"c{c['cabine_id']}", "nome": c["nome"]} for c in u["cabines"]],
         "inversores": [{"id": i["inversor_id"], "nome": i["nome"], "chave": sid, "cabine": f"c{i['cabine_id']}",
                         "equipamento_supervisorio": i["equipamento_supervisorio"],
                         "potencia_kwp": 600 if i["nome"] in ("Inversor 1.5", "Inversor 1.6") else None,
                         "strings_esperadas_qtd": None if i["nome"] in ("Inversor 1.5", "Inversor 1.6") else 14}
                        for i in u["inversores"]]}
    E.salvar_usina(PHARMA, p, E.selo(u), cfg, BASE, banco)
    antes, syncs = json.dumps(_livro(banco), sort_keys=True, default=str), banco.syncs
    selo = _estado(cli, usinas=str(PHARMA))["usinas"][0]["selo"]
    r = _salvar(cli, [{"usina_supervisorio": "Pharma 2", "usina_id": PHARMA, "selo": selo,
                       "inversores": [{"equipamento_supervisorio": "INVERSOR01", "strings": 14}]}])
    j = r.get_json()
    assert r.status_code == 409 and (j["usina_id"], j["usina_supervisorio"]) == (PHARMA, "Pharma 2"), j
    assert "não sobra kWp" in j["motivo"] and "1.200 kWp" in j["motivo"]
    assert json.dumps(_livro(banco), sort_keys=True, default=str) == antes and banco.syncs == syncs


def test_cabine_fora_do_padrao_fica_fora_da_conta_e_da_visao(cfg, banco):
    """O "Ligar pela aba" trouxe do "Equipamento Parente" da aba uma cabine "UFV" (Aparecida do Taboado, usina 11) e uma
    "PEI" (usina 85). Ela fica fora da conta do kWp (antes ganhava 458 kWp) e não vira linha de UG na visão (a linha
    "UFV" com o kWp dela seria lida pela plataforma como a própria usina); aviso."""
    sid = _monta_pharma(cfg, banco)
    u = _u(cfg, banco, PHARMA)
    p = {"chaves": [{k: s[k] for k in ("supervisorio_id", "usina_exibicao", "principal", "full_om", "string_box",
                                       "substitui_aba")} for s in u["supervisorios"]],
         "cabines": [{"id": c["cabine_id"], "k": f"c{c['cabine_id']}", "nome": c["nome"]} for c in u["cabines"]]
         + [{"k": "nufv", "nome": "UFV"}],
         "inversores": [{"id": i["inversor_id"], "nome": i["nome"], "chave": sid,
                         "cabine": "nufv" if i["nome"] in ("Inversor 1.5", "Inversor 1.6") else f"c{i['cabine_id']}",
                         "equipamento_supervisorio": i["equipamento_supervisorio"],
                         "strings_esperadas_qtd": i["strings_esperadas_qtd"]} for i in u["inversores"]]}
    E.salvar_usina(PHARMA, p, E.selo(u), cfg, BASE, banco)
    info = {PHARMA: {"nome": "Pharmas 2", "kwp": 990.0, "kwp_de": "real"}}
    r = E.salvar_depara([{"usina_supervisorio": "Pharma 2", "usina_id": PHARMA, "selo": E.selo(_u(cfg, banco, PHARMA)),
                          "inversores": []}], cfg, BASE, banco, info=info, por_codigo={})
    cab = {c["nome"]: c for c in r["usinas"][0]["cabines"]}
    assert (cab["UFV"]["potencia_kwp"], cab["UFV"]["potencia_regra"]) == (None, None)        # fora da conta
    assert cab["UG 01"]["potencia_kwp"] == round(990 / 82 * 56, 3)                          # os 4 de 14 strings
    assert [i["potencia_kwp"] for i in r["usinas"][0]["inversores"]][-2:] == [156.951, 156.951]  # o inversor, sim
    linhas = E.visao_da_usina(_u(cfg, banco, PHARMA), info[PHARMA], todas=True)
    assert [x["Equipamento"] for x in linhas if not x.get("inversor_id")] == ["UFV", "UG 01"]   # uma UFV só
    assert next(x for x in linhas if x["Equipamento"] == "UFV")["Potência (kWp)"] == 990.0
    assert [a["texto"] for a in r["avisos"] if a["tipo"] == "cabine_fora_do_padrao"][0].startswith(
        "Pharmas 2: a cabine “UFV” não se chama “UG NN”")


# ── o remendo ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_remendo_nao_exclui_o_que_nao_veio_e_salvar_de_novo_nao_muda_nada(cli, cfg, banco):
    _monta_itaja(cfg, banco)
    j = _salvar(cli, [_item_itaja(cli, quais=(1, 2))]).get_json()        # só 2 dos 4 inversores da Itaja 1
    assert j["ok"]
    vivos = [i for i in _livro(banco)["inv"] if not i["excluido"]]
    assert len(vivos) == 8 and len([c for c in _livro(banco)["cab"] if not c["excluido"]]) == 2
    assert {i["nome"]: i["codigo_fracttal"] for i in vivos if i["codigo_fracttal"]} == {
        "Inversor 1.1": "ITA100-INVR1.1", "Inversor 1.2": "ITA100-INVR1.2"}
    # o selo da volta é o mesmo que o estado dá relendo o banco, e mandar o mesmo de novo não grava nada
    assert j["usinas"][0]["selo"] == _estado(cli, chaves=CH1)["usinas"][0]["selo"]
    antes = banco.syncs
    j2 = _salvar(cli, [_item_itaja(cli, quais=(1, 2))]).get_json()
    assert j2["ok"] and j2["mudancas"] == 0 and not j2["visao_mudou"] and banco.syncs == antes
    # o código vazio, a cabine vazia e as strings vazias não mexem (o remendo não apaga)
    j3 = _salvar(cli, [_item_itaja(cli, quais=(1,), codigo_fracttal="", cabine_codigo_fracttal="", strings=None)]).get_json()
    i11 = next(i for i in j3["usinas"][0]["inversores"] if i["nome"] == "Inversor 1.1")
    assert (i11["codigo_fracttal"], i11["strings_esperadas_qtd"], i11["cabine_id"]) == ("ITA100-INVR1.1", 19, 1)


def test_conferido_guarda_a_data_da_primeira_vez_e_desconferir_volta_a_sugestao(cli, cfg, banco):
    _monta_itaja(cfg, banco)
    _salvar(cli, [_item_itaja(cli, quais=(1,))])
    data = next(i for i in _livro(banco)["inv"] if i["nome"] == "Inversor 1.1")["conferido_em"]
    assert data
    j = _salvar(cli, [_item_itaja(cli, quais=(1,), conferido=False)]).get_json()
    i11 = next(i for i in j["usinas"][0]["inversores"] if i["nome"] == "Inversor 1.1")
    assert (i11["fracttal_ligado_por"], i11["conferido_em"]) == ("sugestao", None)


# ── a chave que o Nexus ainda não tem e o inversor novo (2ª revisão, 20/10/2026) ─────────────────────────────────────
def test_chave_da_aba_fora_do_nexus_nasce_semeada_pela_aba(cli, cfg, banco):
    """A Coração 2 (usina 77, nada no Nexus): a tela manda a "Coração 2 (112)" com os 3 inversores que leram na hora (o
    INVERSOR04 parado não vem) e os códigos COR100-INVR2.x. A chave nasce SEMEADA PELA ABA antes do remendo: Full O&M
    Sim, String Box Não, a exibição "Coração 2", a UG 01 e os QUATRO inversores com o nome da aba ("Inversor 1.x", não o
    "Inversor 2.x" do código: o nome é a coluna do BD) e as strings da aba. Não é a chave da usina (a UFV está na
    "Coração 2" da aba). Antes nascia com Full O&M Não, só os 3 e o nome do código, e marcada: a usina saía de trackers e
    PR e o inversor parado deixava de ser esperado."""
    u = _estado(cli, usinas=str(CORACAO))["usinas"][0]
    assert (u["chaves"], u["inversores"], u["kwp"]) == ([], [], 3250.0)
    item = {"usina_supervisorio": CH_COR, "usina_id": CORACAO, "selo": u["selo"],
            "inversores": [{"equipamento_supervisorio": f"INVERSOR0{m}", "strings": 20,
                            "cabine_codigo_fracttal": "THPN-COR100-CABN1", "codigo_fracttal": f"COR100-INVR2.{m}",
                            "conferido": True} for m in (1, 2, 3)]}
    j = _salvar(cli, [item]).get_json()
    assert j["ok"], j
    sup = _livro(banco)["sup"][0]
    assert (sup["usina_supervisorio"], sup["usina_exibicao"], sup["full_om"], sup["string_box"], sup["principal"]) == (
        CH_COR, "Coração 2", 1, 0, 0)
    u = j["usinas"][0]
    assert [(i["nome"], i["equipamento_supervisorio"], i["strings_esperadas_qtd"], i["codigo_fracttal"])
            for i in u["inversores"]] == [("Inversor 1.1", "INVERSOR01", 20, "COR100-INVR2.1"),
                                          ("Inversor 1.2", "INVERSOR02", 20, "COR100-INVR2.2"),
                                          ("Inversor 1.3", "INVERSOR03", 20, "COR100-INVR2.3"),
                                          ("Inversor 1.4", "INVERSOR04", 20, None)]
    # o kWp é a regra do Levi com o Registro como está (3.250 ÷ 80 strings × 20; a aba tinha 250: o Registro tem só a
    # Coração 1, e o Levi decidiu "aplica direto"); a UG 01 da aba adota a CABN1
    assert {i["potencia_kwp"] for i in u["inversores"]} == {812.5}
    assert [(c["nome"], c["codigo_fracttal"], c["potencia_kwp"]) for c in u["cabines"]] == [
        ("UG 01", "THPN-COR100-CABN1", 3250.0)]
    assert len(_avisos(j, "semeada_pela_aba")) == 1 and "4 inversor(es)" in _avisos(j, "semeada_pela_aba")[0]
    # só difere da aba pela regra (kWp): vale no lugar da aba, e o leitor que sobrepõe a visão à aba segue vendo os 4,
    # o INVERSOR04 parado inclusive, com 20 strings esperadas
    assert j["marcacao"] == [{"usina_id": CORACAO, "usina_supervisorio": CH_COR, "principal": False, "marcada": True,
                              "fora_da_regra": []}]
    lida = [x for x in E.sobrepor(ABA, _livro(banco)["visao"]) if E.chave_efetiva(x) == CH_COR]
    assert [(x["Equipamento"], x["Equipamento Supervisório"], x["Strings Ativas"], x["Full O&M"]) for x in lida] == [
        (f"Inversor 1.{m}", f"INVERSOR0{m}", 20, "Sim") for m in range(1, 5)]


def test_sem_a_aba_lida_a_chave_que_o_nexus_nao_tem_nao_nasce(cli, banco, monkeypatch):
    """Sem a aba não há de onde semear: a chave nova não nasce pela metade (503, com a culpada) e nada é gravado."""
    monkeypatch.setattr(E, "aba_equipamentos", lambda base, sessao: {"chaves": {}, "lido_em": None,
                                                                     "erro": "ConnectionError: banco fora"})
    u = _estado(cli, usinas=str(CORACAO))["usinas"][0]
    r = _salvar(cli, [{"usina_supervisorio": CH_COR, "usina_id": CORACAO, "selo": u["selo"],
                       "inversores": [{"equipamento_supervisorio": "INVERSOR01", "strings": 20}]}])
    assert r.status_code == 503 and r.get_json()["usina_id"] == CORACAO and "semeada" in r.get_json()["motivo"]
    assert _livro(banco)["sup"] == []


@pytest.mark.parametrize("nome_no_pedido, esperado", [
    ("", "Inversor 1.4"),                 # sem o nome do cadastro: o da aba para (chave, nome no supervisório)
    ("Inversor 1.9", "Inversor 1.9"),     # com ele: o do pedido (é o do cadastro da plataforma)
])
def test_inversor_novo_numa_chave_que_existe_leva_o_nome_do_pedido_ou_da_aba(cli, cfg, banco, nome_no_pedido, esperado):
    """O INVERSOR04 da Itaja 1 não está no Nexus. O código que veio (ITA100-INVR2.1, o número da planta 2) daria
    "Inversor 2.1", que já é outro inversor da usina: até a 2ª revisão o Nexus recusava com 409 "mande outro nome", e a
    tela não mandava nome nenhum. Agora o nome é o do pedido, senão o da aba, e só então o do código."""
    _monta_itaja(cfg, banco, sem=("Inversor 1.4",))
    item = _item_itaja(cli, quais=(4,), codigo_fracttal="ITA100-INVR2.1", nome=nome_no_pedido)
    j = _salvar(cli, [item]).get_json()
    assert j["ok"], j
    novo = next(i for i in j["usinas"][0]["inversores"] if i["equipamento_supervisorio"] == "INVERSOR04"
                and i["usina_supervisorio"] == CH1)
    assert (novo["nome"], novo["codigo_fracttal"], novo["strings_esperadas_qtd"]) == (esperado, "ITA100-INVR2.1", 19)
    nomes = [i["nome"] for i in j["usinas"][0]["inversores"]]
    assert len(nomes) == 8 and nomes.count("Inversor 2.1") == 1


def test_inversor_sem_nome_no_supervisorio_casa_pelo_nome_e_ganha_o_da_fonte(cli, cfg, banco):
    """214 inversores da aba (13/10) não têm o "Equipamento Supervisório" (as Ibirapuã, a Aquiraz 1): o pedido traz o
    nome da fonte e não casa. Casa pelo NOME dentro da usina (o do pedido; sem ele, o da aba) e o inversor ganha o nome
    no supervisório, em vez de nascer outro igual (que dava 409 e derrubava o lote)."""
    _monta_itaja(cfg, banco, esup_vazio=("Inversor 1.1", "Inversor 1.2"))
    item = _item_itaja(cli, quais=(1, 2))
    item["inversores"][1]["nome"] = ""                     # o INVERSOR02 sem o nome do cadastro: vale o da aba
    j = _salvar(cli, [item]).get_json()
    assert j["ok"], j
    invs = {i["nome"]: i for i in j["usinas"][0]["inversores"]}
    assert len(invs) == 8
    assert [(invs[n]["equipamento_supervisorio"], invs[n]["codigo_fracttal"]) for n in ("Inversor 1.1", "Inversor 1.2")] == [
        ("INVERSOR01", "ITA100-INVR1.1"), ("INVERSOR02", "ITA100-INVR1.2")]


def test_inversor_de_outra_chave_recusa_so_a_usina_culpada(cli, cfg, banco):
    """A Cambé pela chave "Cambé" (os 20 inversores estão na "Cambé (85)"): o inversor casa pelo nome numa OUTRA chave da
    usina. O de-para dele é por aquela chave: recusa 409 com a usina e a chave culpadas, e o lote inteiro não grava (a
    tela tira a culpada e reenvia o resto)."""
    _monta_itaja(cfg, banco)
    _monta_pharma(cfg, banco)
    pharma = {"usina_supervisorio": "Pharma 2", "usina_id": PHARMA, "selo": _estado(cli, usinas=str(PHARMA))["usinas"][0]["selo"],
              "inversores": [{"equipamento_supervisorio": "INVERSOR01", "strings": 14}]}
    errado = _item_itaja(cli, chave=CH_USINA, quais=(1,))          # o "Inversor 1.1" está na Itaja 1, não na "Itajá"
    syncs = banco.syncs
    r = _salvar(cli, [pharma, errado])
    j = r.get_json()
    assert r.status_code == 409 and (j["usina_id"], j["usina_supervisorio"]) == (ITAJA, CH_USINA), j
    assert f"chega pela chave “{CH1}”" in j["motivo"] and banco.syncs == syncs
    # sem a culpada, o resto grava
    assert _salvar(cli, [pharma]).get_json()["ok"]


# ── marcar no lugar da aba: só o que difere da aba pela regra (2ª revisão, 20/10/2026) ───────────────────────────────
def test_itaja_as_tres_chaves_valem_no_lugar_da_aba(cli, cfg, banco):
    """Itajá com a aba real: as duas chaves dos inversores e a "Itajá" (a UFV e as UG) marcadas, as UG 01 e 02 com
    1.298,0 (a soma) e o código da CABN na visão; o leitor que sobrepõe a visão à aba enxerga UMA UFV e as duas UG do
    Nexus (nenhuma UG da aba sobra)."""
    s1, _s2, _s3 = _monta_itaja(cfg, banco)
    j = _salvar(cli, [_item_itaja(cli), _item_itaja(cli, chave=CH2, n=2)]).get_json()
    assert j["ok"], j
    assert [(m["usina_supervisorio"], m["marcada"]) for m in j["marcacao"]] == [(CH1, True), (CH2, True), (CH_USINA, True)]
    assert _avisos(j, "nao_marcada") == []
    assert _marca(banco) == {CH_USINA: 1, CH1: 1, CH2: 1}
    assert {c["usina_supervisorio"]: c["substitui_aba"] for c in j["usinas"][0]["chaves"]} == {
        CH_USINA: True, CH1: True, CH2: True}
    visao = _livro(banco)["visao"]
    da_ufv = [(x["Usina Supervisório"], x["Usina"], x["Equipamento"], x["Potência (kWp)"], x["N de Inversores"],
               x["Código Fracttal"]) for x in visao if x["supervisorio_id"] == s1]
    assert da_ufv == [(None, "Itajá", "UFV", 2596, 8, None), (None, "Itajá", "UG 01", 1298, 4, "ITA100-CABN1"),
                      (None, "Itajá", "UG 02", 1298, 4, "ITA100-CABN2")]
    lida = E.sobrepor(ABA, visao)
    assert [(x["Equipamento"], x["Potência (kWp)"]) for x in lida if E.chave_efetiva(x) == CH_USINA] == [
        ("UFV", 2596), ("UG 01", 1298), ("UG 02", 1298)]
    # salvar de novo sem mexer: já marcadas, nada muda e nada grava
    antes = banco.syncs
    j2 = _salvar(cli, [_item_itaja(cli), _item_itaja(cli, chave=CH2, n=2)]).get_json()
    assert (j2["mudancas"], j2["marcacao"], banco.syncs) == (0, [], antes)


@pytest.mark.parametrize("aba, nao_marca, fora", [
    # o que não é da regra: a chave da UFV com outro cliente ou outro Full O&M na aba não marca (as dos inversores sim)
    (_aba_itaja(Cliente="Outro cliente") + _aba_itaja_inv(), CH_USINA,
     ["Cliente: “Outro cliente” na aba, “Thopen” no Nexus."]),
    (_aba_itaja(**{"Full O&M": "Não"}) + _aba_itaja_inv(), CH_USINA, ["Full O&M: Não na aba, Sim no Nexus."]),
    # a chave do pedido também: Full O&M diferente na Itaja 1 (sairia de trackers e PR se marcasse)
    (_aba_itaja() + [dict(x, **{"Full O&M": "Não"}) if x["Usina Supervisório"] == CH1 else x for x in _aba_itaja_inv()],
     CH1, ["Full O&M: Não na aba, Sim no Nexus."]),
    # o nome do inversor é a coluna do BD: diferente da aba, não marca
    (_aba_itaja() + [dict(x, Equipamento="Inversor 1.1 A") if x["Equipamento"] == "Inversor 1.1" else x
                     for x in _aba_itaja_inv()],
     CH1, ["INVERSOR01: nome: “Inversor 1.1 A” na aba, “Inversor 1.1” no Nexus."]),
])
def test_diferenca_fora_da_regra_nao_marca_grava_e_avisa(cli, cfg, banco, aba, nao_marca, fora):
    """A chave com diferença fora da regra não marca, e a usina vale por inteiro ou nada (2ª revisão final e 3ª revisão,
    21/10/2026): TODAS as outras ficam seguras junto, sem exceção. A que passa mas não é igual à aba (a "Itajá" com a UFV
    do Registro e as UG da CABN) marcada sozinha misturaria nos leitores a UFV e as UG do Nexus com os inversores da aba
    (a UG 01 sairia com a Itaja 1 ainda apontando para ela). E a chave do pedido IGUAL à aba (o kWp 324,5 contra 324,52
    nos 0,05 da comparação), que até a 3ª revisão marcava sozinha ("com ela os leitores não mudam"), era a porta do estado
    parcial: no salvar seguinte a regra refazia o kWp da usina inteira e ela o levava aos leitores ao lado das UG da aba
    (ver test_a_ja_marcada_cuja_visao_muda_volta_para_a_aba_numa_usina_segura). O aviso diz qual chave segura e quanto
    os leitores somariam com só as outras."""
    _poe_aba(banco, aba + ABA_PHARMA)
    _monta_itaja(cfg, banco)
    j = _salvar(cli, [_item_itaja(cli), _item_itaja(cli, chave=CH2, n=2)]).get_json()
    assert j["ok"], j
    m = {x["usina_supervisorio"]: x for x in j["marcacao"]}
    assert set(m) == {CH1, CH2, CH_USINA}
    assert (m[nao_marca]["marcada"], m[nao_marca]["fora_da_regra"]) == (False, fora)
    segura = [f"“{nao_marca}”, da mesma usina, não vale(m) no lugar da aba, e a usina vale por inteiro ou nada"]
    # as outras duas (a da UFV, e a do pedido igual à aba também) passam, mas ficam seguras pela que não vale
    assert all((m[k]["marcada"], m[k]["fora_da_regra"]) == (False, segura) for k in {CH1, CH2, CH_USINA} - {nao_marca})
    da_usina = next(a["texto"] for a in j["avisos"] if a["tipo"] == "nao_marcada" and not a["usina_supervisorio"])
    assert da_usina.startswith(f"Itajá 1 e 2: a usina não passou a valer no lugar da aba, porque “{nao_marca}” "
                               "não vale(m)") and "contra 2.596 kWp do Registro mestre" in da_usina
    aviso = next(a for a in j["avisos"] if a["tipo"] == "nao_marcada" and a["usina_supervisorio"] == nao_marca)
    assert aviso["usina_id"] == ITAJA
    assert "não vale no lugar da aba porque: " in aviso["texto"] and all(f.rstrip(".") in aviso["texto"] for f in fora)
    assert _marca(banco) == {CH_USINA: 0, CH1: 0, CH2: 0}
    # a estrutura ficou gravada no livro (o kWp, os códigos), só não vai aos leitores por esta chave
    assert {i["codigo_fracttal"] for i in j["usinas"][0]["inversores"]} == {f"ITA100-INVR{n}.{m}" for n in (1, 2)
                                                                            for m in range(1, 5)}
    # salvar de novo: avisa de novo, nada muda e nada grava
    antes = banco.syncs
    j2 = _salvar(cli, [_item_itaja(cli), _item_itaja(cli, chave=CH2, n=2)]).get_json()
    assert (j2["mudancas"], banco.syncs) == (0, antes)
    assert [x["marcada"] for x in j2["marcacao"] if x["usina_supervisorio"] == nao_marca] == [False]


def test_inversor_que_so_o_nexus_tem_nao_marca(cli, cfg, banco):
    """O pedido traz o INVERSOR05, que a aba não tem: ele nasce com o nome do código ("Inversor 1.5"; nem o pedido nem a
    aba dão outro), mas a chave não vale no lugar da aba (inversor de um lado só não é da regra)."""
    _monta_itaja(cfg, banco)
    item = _item_itaja(cli)
    item["inversores"].append({"equipamento_supervisorio": "INVERSOR05", "strings": 19, "codigo_fracttal": "ITA100-INVR1.5",
                               "cabine_codigo_fracttal": "ITA100-CABN1", "conferido": True})
    j = _salvar(cli, [item]).get_json()
    assert j["ok"], j
    assert "Inversor 1.5" in [i["nome"] for i in j["usinas"][0]["inversores"]]
    m = next(x for x in j["marcacao"] if x["usina_supervisorio"] == CH1)
    assert (m["marcada"], m["fora_da_regra"]) == (False, ["INVERSOR05 (Inversor 1.5) está no Nexus e não na aba."])


def test_chave_ja_marcada_continua_marcada(cli, cfg, banco):
    _monta_itaja(cfg, banco)
    assert _salvar(cli, [_item_itaja(cli)]).get_json()["ok"] and _marca(banco)[CH1] == 1
    # a aba muda o Full O&M da Itaja 1 depois: a chave marcada não é mais conferida (o Nexus é a fonte dela)
    _poe_aba(banco, _aba_itaja() + [dict(x, **{"Full O&M": "Não"}) for x in _aba_itaja_inv()])
    j = _salvar(cli, [_item_itaja(cli, strings=20)]).get_json()
    assert j["ok"] and _marca(banco)[CH1] == 1 and CH1 not in [x["usina_supervisorio"] for x in j["marcacao"]]


def test_sem_a_aba_lida_nada_e_marcado(cli, cfg, banco, monkeypatch):
    """A aba Equipamentos que não se leu (o banco fora e nenhuma cópia) vai como None, não como vazia: sem comparação,
    nada marca, e o aviso diz por quê (vazia diria "a chave não está na aba", que é outra coisa)."""
    _monta_itaja(cfg, banco)
    monkeypatch.setattr(E, "aba_equipamentos", lambda base, sessao: {"chaves": {}, "lido_em": None,
                                                                     "erro": "ConnectionError: banco fora"})
    j = _salvar(cli, [_item_itaja(cli)]).get_json()
    assert j["ok"] and [(m["usina_supervisorio"], m["marcada"], m["fora_da_regra"]) for m in j["marcacao"]] == [
        (CH1, False, ["a aba Equipamentos não foi lida, e sem ela não há comparação"]),
        (CH_USINA, False, ["a aba Equipamentos não foi lida, e sem ela não há comparação"]),
        (CH2, False, ["a aba Equipamentos não foi lida, e sem ela não há comparação"])]
    assert _marca(banco) == {CH_USINA: 0, CH1: 0, CH2: 0}
    # a mesma aba lida (a cópia de antes, com o erro da releitura) compara e marca
    monkeypatch.setattr(E, "aba_equipamentos", lambda base, sessao: {
        "chaves": E.agrupar_aba(ABA), "lido_em": 1.0, "erro": "ConnectionError: banco fora"})
    j = _salvar(cli, [_item_itaja(cli), _item_itaja(cli, chave=CH2, n=2)]).get_json()
    assert all(m["marcada"] for m in j["marcacao"]), j


def test_cabine_com_codigo_do_fracttal_nunca_sai(cli, cfg, banco):
    """A UG 01 da Itajá ganha a CABN1 no 1º salvar; no 2º, os inversores da Itaja 1 vão para a CABN2 e ela esvazia: com
    o código do Fracttal ela é uma CABN e fica (só o aviso). Sai só a cabine da aba, sem código."""
    _monta_itaja(cfg, banco)
    _salvar(cli, [_item_itaja(cli)])
    j = _salvar(cli, [_item_itaja(cli, cabine_codigo_fracttal="ITA100-CABN2")]).get_json()
    assert j["ok"] and j["cabines_excluidas"] == []
    assert [(c["nome"], c["codigo_fracttal"]) for c in j["usinas"][0]["cabines"]] == [
        ("UG 01", "ITA100-CABN1"), ("UG 02", "ITA100-CABN2")]
    assert any(t.startswith("A cabine UG 01 (usina 93) ficou sem inversores e fica")
               for t in _avisos(j, "cabine_sem_inversores"))
    assert not any(c["excluido"] for c in _livro(banco)["cab"])


def test_fora_da_regra_pelo_tipo_da_diferenca():
    """Da regra: as strings, o kWp que a regra calculou (a linhagem), a cabine pela CABN (o código), a UG que só a aba
    tem quando todas as UG vivas já são CABN, a UFV vinda do Registro mestre e o "N de Inversores" contado. O resto
    nunca: Full O&M, nome, exibição, Fracttal, cliente, inversor de um lado só, a chave fora da aba."""
    u = {"cabines": [{"cabine_id": 1, "nome": "UG 01", "codigo_fracttal": "X-CABN1", "potencia_regra": "real_por_string"},
                     {"cabine_id": 2, "nome": "UG 02", "codigo_fracttal": "", "potencia_regra": "informada"}],
         "inversores": [{"inversor_id": 7, "potencia_regra": "contratual_por_string"},
                        {"inversor_id": 8, "potencia_regra": ""}]}
    do_registro = {"kwp": 990.0, "kwp_de": "real"}

    def fora(*itens, info_u=do_registro):
        return E.fora_da_regra({"itens": [dict(i, texto=f"d{n}") for n, i in enumerate(itens)]}, u, info_u)
    assert fora({"tipo": "kwp_cabine", "cabine_id": 1}, {"tipo": "kwp_inversor", "inversor_id": 7},
                {"tipo": "cabine_so_no_nexus", "cabine_id": 1}, {"tipo": "cabine_do_inversor", "cabine_id": 1},
                {"tipo": "strings_inversor"}, {"tipo": "kwp_usina"}, {"tipo": "inversores_usina"}) == []
    assert fora({"tipo": "kwp_cabine", "cabine_id": 2}, {"tipo": "kwp_inversor", "inversor_id": 8},
                {"tipo": "cabine_so_no_nexus", "cabine_id": 2}, {"tipo": "cabine_so_na_aba"},
                {"tipo": "full_om"}, {"tipo": "string_box"}, {"tipo": "nome_inversor"}, {"tipo": "exibicao"},
                {"tipo": "fracttal"}, {"tipo": "cliente"}, {"tipo": "inversor_so_na_aba"},
                {"tipo": "inversor_so_no_nexus"}, {"tipo": "fora_da_aba"}, {"tipo": "ufv_em_outra_chave"}) == [
        f"d{n}" for n in range(14)]
    # a potência da UFV só é da regra quando vem do Registro mestre (sem ele a visão soma as cabines)
    assert fora({"tipo": "kwp_usina"}, info_u={"kwp": None, "kwp_de": ""}) == ["d0"]
    u["cabines"].pop()                                       # só a CABN viva: a UG que só a aba tem é o nome da UG
    assert fora({"tipo": "cabine_so_na_aba"}) == []
    u["cabines"].append({"cabine_id": 3, "nome": "PEI", "codigo_fracttal": ""})       # fora do padrão: não conta
    assert fora({"tipo": "cabine_so_na_aba"}) == []


# ── as recusas: nada é gravado, e a culpada vai junto ────────────────────────────────────────────────────────────────
def test_selo_velho_recusa_tudo_com_409_e_diz_a_culpada(cli, cfg, banco):
    _monta_itaja(cfg, banco)
    _monta_pharma(cfg, banco)
    bom = _item_itaja(cli)
    antes, syncs = json.dumps(_livro(banco), sort_keys=True, default=str), banco.syncs
    r = _salvar(cli, [dict(bom, selo="selo-velho")])
    j = r.get_json()
    assert r.status_code == 409 and j == {"ok": False, "motivo": j["motivo"], "usina_id": ITAJA,
                                          "usina_supervisorio": CH1}
    assert "mudou desde que a tela abriu" in j["motivo"]
    # um selo que não confere recusa também o item bom de outra usina, e diz qual foi
    pharma = {"usina_supervisorio": "Pharma 2", "usina_id": PHARMA, "selo": "velho", "inversores": []}
    r = _salvar(cli, [bom, pharma])
    assert r.status_code == 409 and (r.get_json()["usina_id"], r.get_json()["usina_supervisorio"]) == (PHARMA, "Pharma 2")
    assert json.dumps(_livro(banco), sort_keys=True, default=str) == antes and banco.syncs == syncs


def test_recusa_do_pedido_inteiro_nao_aponta_usina(cli):
    r = _salvar(cli, [])
    assert r.status_code == 400 and set(r.get_json()) == {"ok", "motivo"}


def test_codigo_fora_da_dimensao_ou_de_outro_tipo_recusa(cli, cfg, banco):
    _monta_itaja(cfg, banco)
    antes = json.dumps(_livro(banco), sort_keys=True, default=str)
    casos = [({"codigo_fracttal": "ITA100-INVR9.9"}, 400, "ITA100-INVR9.9 não está na dimensão"),
             ({"codigo_fracttal": "ITA100-INVR3.1"}, 409, "com outro ID"),
             ({"codigo_fracttal": "ITA100-QGBT1"}, 400, "não é um código de inversor"),
             ({"cabine_codigo_fracttal": "ITA100-INVR1.1"}, 400, "não é um código de cabine"),
             ({"strings": 0}, 400, "inteiro maior que zero"), ({"strings": 2.5}, 400, "inteiro maior que zero")]
    for extra, status, msg in casos:
        r = _salvar(cli, [_item_itaja(cli, quais=(1,), **extra)])
        j = r.get_json()
        assert r.status_code == status and msg in j["motivo"], (extra, j)
        assert (j["usina_id"], j["usina_supervisorio"]) == (ITAJA, CH1)
    r = _salvar(cli, [dict(_item_itaja(cli), usina_id=999)])
    assert r.status_code == 400 and "fora do Registro mestre" in r.get_json()["motivo"]
    assert json.dumps(_livro(banco), sort_keys=True, default=str) == antes


def test_um_codigo_do_fracttal_num_inversor_so(cli, cfg, banco):
    _monta_itaja(cfg, banco)
    _monta_pharma(cfg, banco)
    # o mesmo código em dois inversores do pedido
    item = _item_itaja(cli, quais=(1, 2))
    item["inversores"][1]["codigo_fracttal"] = "ITA100-INVR1.1"
    r = _salvar(cli, [item])
    assert r.status_code == 400 and "dois inversores do pedido" in r.get_json()["motivo"]
    # o código que já está num inversor vivo de outra usina (o "inversor repetido": a Coração 2 com os da Coração 1):
    # a culpada é a usina que o recebeu
    assert _salvar(cli, [_item_itaja(cli, quais=(1,))]).get_json()["ok"]
    selo = _estado(cli, usinas=str(PHARMA))["usinas"][0]["selo"]
    r = _salvar(cli, [{"usina_supervisorio": "Pharma 2", "usina_id": PHARMA, "selo": selo,
                       "inversores": [{"equipamento_supervisorio": "INVERSOR01", "codigo_fracttal": "ITA100-INVR1.1"}]}])
    assert r.status_code == 409 and "já está no inversor “Inversor 1.1”" in r.get_json()["motivo"]
    assert r.get_json()["usina_id"] == PHARMA
    # a troca entre dois inversores da mesma usina passa (a conferência é depois de aplicar)
    item = _item_itaja(cli, quais=(1, 2))
    item["inversores"][0]["codigo_fracttal"], item["inversores"][1]["codigo_fracttal"] = (
        "ITA100-INVR1.2", "ITA100-INVR1.1")
    _salvar(cli, [_item_itaja(cli, quais=(2,))])
    item["selo"] = _estado(cli, chaves=CH1)["usinas"][0]["selo"]
    j = _salvar(cli, [item]).get_json()
    assert j["ok"] and {i["nome"]: i["codigo_fracttal"] for i in j["usinas"][0]["inversores"]
                        if i["codigo_fracttal"]} == {"Inversor 1.1": "ITA100-INVR1.2", "Inversor 1.2": "ITA100-INVR1.1"}


def test_chave_de_outra_usina_recusa(cli, cfg, banco):
    _monta_itaja(cfg, banco)
    selo = _estado(cli, usinas=str(PHARMA))["usinas"][0]["selo"]
    r = _salvar(cli, [{"usina_supervisorio": CH1, "usina_id": PHARMA, "selo": selo, "inversores": []}])
    assert r.status_code == 409 and "já está ligada a outra usina" in r.get_json()["motivo"]
    assert (r.get_json()["usina_id"], r.get_json()["usina_supervisorio"]) == (PHARMA, CH1)


# ── a visão e a comparação com a aba ─────────────────────────────────────────────────────────────────────────────────
def test_comparar_chave_ignora_o_codigo_fracttal(cli, cfg, banco):
    """A aba Equipamentos não tem o "Código Fracttal": a chave igual à aba continua "igual à aba" com o ativo ligado, e o
    leitor que sobrepõe a visão à aba enxerga o mesmo que enxergava."""
    _monta_pharma(cfg, banco)
    u = _estado(cli, usinas=str(PHARMA))["usinas"][0]
    _salvar(cli, [{"usina_supervisorio": "Pharma 2", "usina_id": PHARMA, "selo": u["selo"],
                   "inversores": [{"equipamento_supervisorio": f"INVERSOR0{m}", "cabine_codigo_fracttal":
                                   "THPN-PHS100-CABN2", "codigo_fracttal": f"THPN-PHS100-INVR2.{m}"} for m in range(1, 7)]}])
    visao = _livro(banco)["visao"]
    assert all(x["Código Fracttal"] for x in visao if x.get("inversor_id"))
    aba = [{k: v for k, v in x.items() if k != "Código Fracttal"} for x in visao]       # a aba, igual, sem a coluna
    g = E.agrupar_aba(aba)["Pharma 2"]
    cmp = E.comparar_chave(g, visao)
    assert cmp["iguais"], cmp
    assert cmp == E.comparar_chave(g, [dict(x, **{"Código Fracttal": None}) for x in visao])
    assert E.agrupar_aba(E.sobrepor(aba, visao)) == E.agrupar_aba(aba)


def _cadastro_da_plataforma(linhas) -> dict:
    """Réplica do miolo do `load_equipamentos` da plataforma (app.py) que a revisão de 20/10 usou: a chave `us` é a
    "Usina Supervisório" (senão a "Usina") só com `strip`, e cada mapa é buscado pela grafia EXATA da fonte."""
    m = {"ESPERADO_INV": {}, "EQUIP_NAMES": {}, "POWER_INV": {}, "FULL_OM": set()}
    for x in linhas:
        us = str(x.get("Usina Supervisório") or "").strip() or str(x.get("Usina") or "").strip()
        if not us:
            continue
        if str(x.get("Full O&M") or "").strip().lower() == "sim":
            m["FULL_OM"].add(us)
        eq, es = str(x.get("Equipamento") or "").strip(), str(x.get("Equipamento Supervisório") or "").strip()
        if not eq.lower().startswith("inversor") or not es:
            continue
        m["EQUIP_NAMES"].setdefault(us, {})[es] = eq
        if x.get("Strings Ativas") is not None:
            m["ESPERADO_INV"].setdefault(us, {})[es] = int(x["Strings Ativas"])
        if x.get("Potência (kWp)") is not None:
            m["POWER_INV"].setdefault(us, {})[es] = float(x["Potência (kWp)"])
    return m


def test_sobrepor_herda_a_grafia_da_aba_assis_skid_1(cli, cfg, banco):
    """A "Assis Chateaubriand  Skid 1 (79)" tem espaço DUPLO na aba e na API PV; o Nexus guarda com espaço único (o
    `texto`). Marcada, a visão entrava com a grafia do Nexus e a plataforma, que busca pela grafia exata da fonte, perdia
    as strings esperadas, os nomes, o kWp e o Full O&M da Skid 1, sem aviso. A linha da visão herda a grafia da aba."""
    aba_assis = [_l(Cliente="Thopen", Usina="Assis", **{"Usina Supervisório": ASSIS_ABA, "Equipamento": f"Inversor 1.{m}",
                                                        "Equipamento Supervisório": f"INVERSOR0{m}",
                                                        "Equipamento Parente": "UG 01", "Potência (kWp)": 323.4,
                                                        "Strings Ativas": 21, "Full O&M": "Sim", "String Box": "Não"})
                 for m in range(1, 5)]
    aba = ABA + aba_assis
    _poe_aba(banco, aba)
    antes = _cadastro_da_plataforma(aba)
    assert antes["ESPERADO_INV"][ASSIS_ABA] == {f"INVERSOR0{m}": 21 for m in range(1, 5)}
    # a tela compara a chave pela forma normalizada e manda a grafia do Nexus
    u = _estado(cli, usinas=str(ASSIS))["usinas"][0]
    j = _salvar(cli, [{"usina_supervisorio": ASSIS_NEXUS, "usina_id": ASSIS, "selo": u["selo"],
                       "inversores": [{"equipamento_supervisorio": f"INVERSOR0{m}", "nome": f"Inversor 1.{m}",
                                       "strings": 21, "cabine_codigo_fracttal": "THPN-ACB100-CABN1",
                                       "codigo_fracttal": f"THPN-ACB100-INVR1.{m}", "conferido": True}
                                      for m in range(1, 5)]}]).get_json()
    assert j["ok"] and [m["marcada"] for m in j["marcacao"]] == [True], j
    visao = _livro(banco)["visao"]
    assert {x["Usina Supervisório"] for x in visao if x.get("inversor_id")} == {ASSIS_NEXUS}     # o livro: espaço único
    lida = E.sobrepor(aba, visao)
    depois = _cadastro_da_plataforma(lida)
    assert depois["ESPERADO_INV"][ASSIS_ABA] == antes["ESPERADO_INV"][ASSIS_ABA]
    assert depois["EQUIP_NAMES"][ASSIS_ABA] == antes["EQUIP_NAMES"][ASSIS_ABA]
    assert depois["POWER_INV"][ASSIS_ABA] == {f"INVERSOR0{m}": 323.4 for m in range(1, 5)}
    assert ASSIS_ABA in depois["FULL_OM"] and ASSIS_NEXUS not in depois["ESPERADO_INV"]
    skid = [x for x in lida if E.chave_efetiva(x) == ASSIS_NEXUS]
    assert len(skid) == 4 and all(x["inversor_id"] for x in skid)          # são as da visão, não sobrou linha da aba
    assert {x["Chave"] for x in skid} == {f"{ASSIS_ABA}INVERSOR0{m}" for m in range(1, 5)}


def test_sobrepor_herda_a_grafia_so_quando_a_chave_bate():
    aba = [{"Usina": "Itajá ", "Usina Supervisório": None, "Equipamento": "UFV"},
           {"Usina": "X", "Usina Supervisório": "Chave  Dupla", "Equipamento": "Inversor 1.1"}]
    visao = [{"Usina": "Itajá", "Usina Supervisório": None, "Equipamento": "UFV", "Chave 2": "UFV"},
             {"Usina": "X", "Usina Supervisório": "Chave Dupla", "Equipamento": "Inversor 1.1", "Chave": "Chave DuplaI1",
              "Chave 2": "Chave DuplaInversor 1.1"},
             {"Usina": "Y", "Usina Supervisório": "Só no Nexus", "Equipamento": "Inversor 1.1"}]
    lida = E.sobrepor(aba, visao)
    assert [(x["Usina"], x["Usina Supervisório"]) for x in lida] == [("Itajá ", None), ("X", "Chave  Dupla"),
                                                                     ("Y", "Só no Nexus")]
    assert (lida[1]["Chave"], lida[1]["Chave 2"]) == ("Chave  DuplaI1", "Chave  DuplaInversor 1.1")
    assert visao[1]["Usina Supervisório"] == "Chave Dupla"         # a visão de entrada não muda


# ── o acerto final (2ª revisão, 21/10/2026): um teste por achado, com o caso real ───────────────────────────────────
POR_CODIGO = {EQ.canon(d["codigo"]): d for d in DIM}


def _liga_pela_aba(cfg, banco, aba, uid, chaves):
    """A usina como o "Ligar pela aba" de 13/10 a deixou no banco (a estrutura da aba, nada no lugar da aba)."""
    _poe_aba(banco, aba)
    return E.ligar_pela_aba({"ligar": {uid: list(chaves)}}, E.agrupar_aba(aba), cfg, BASE, banco)


def _item(cfg, banco, uid, chave, inversores):
    return {"usina_supervisorio": chave, "usina_id": uid, "selo": E.selo(_u(cfg, banco, uid)), "inversores": inversores}


def test_nova_chave_fora_da_aba_e_do_nexus_e_recusada_e_nao_prende_os_codigos(cli, banco):
    """A tela oferecia "Nova chave" (o nome que a fonte manda, fora da aba). Na Pharma 2 (usina 108) vazia, o Salvar da
    "PHARMA 2 API" com os THPN-PHS100-INVR2.x gravava, virava a chave da usina, criava "Inversor 2.1" a "2.6" com os
    códigos e nunca valia no lugar da aba; depois o da "Pharma 2" (a chave da aba) com os mesmos códigos levava 409 para
    sempre. O Nexus recusa a chave que não está na aba nem no livro (409, com a culpada), nada grava, e a da aba passa."""
    ms = list(zip(range(1, 7), (14, 14, 14, 14, 13, 13)))

    def item(chave):
        u = _estado(cli, usinas=str(PHARMA))["usinas"][0]
        return {"usina_supervisorio": chave, "usina_id": PHARMA, "selo": u["selo"],
                "inversores": [{"equipamento_supervisorio": f"INVERSOR0{m}", "nome": f"Inversor 1.{m}", "strings": s,
                                "cabine_codigo_fracttal": "THPN-PHS100-CABN2", "codigo_fracttal": f"THPN-PHS100-INVR2.{m}",
                                "conferido": True} for m, s in ms]}
    syncs = banco.syncs
    r = _salvar(cli, [item("PHARMA 2 API")])
    j = r.get_json()
    assert r.status_code == 409 and (j["usina_id"], j["usina_supervisorio"]) == (PHARMA, "PHARMA 2 API"), j
    assert "não está na aba Equipamentos nem no Nexus" in j["motivo"] and "Base > Equipamentos" in j["motivo"]
    assert _livro(banco)["sup"] == [] and banco.syncs == syncs
    j = _salvar(cli, [item("Pharma 2")]).get_json()
    assert j["ok"], j
    assert j["marcacao"] == [{"usina_id": PHARMA, "usina_supervisorio": "Pharma 2", "principal": True, "marcada": True,
                              "fora_da_regra": []}]
    assert {i["codigo_fracttal"] for i in j["usinas"][0]["inversores"]} == {f"THPN-PHS100-INVR2.{m}" for m in range(1, 7)}


SKIDS = [(1, 79, (21, 21, 21, 21)), (2, 80, (21, 21, 21, 21)), (3, 81, (21, 21, 21, 21)), (4, 82, (21, 21, 21, 21)),
         (5, 2, (22, 21, 22, 20))]


def _chave_skid(n, p):
    return ASSIS_ABA if n == 1 else f"Assis Chateaubriand Skid {n} ({p})"


def _aba_assis(full_om_skid3="Sim"):
    """A Assis Chateaubriand como a aba tem: a "Assis" com a UFV e as UG 01 a 05 (uma por skid), e uma chave por skid
    com 4 inversores de 323,4 kWp (a Skid 1 com espaço DUPLO)."""
    comum = {"Cliente": "Thopen", "Usina": "Assis", "String Box": "Não"}
    out = [_l(**comum, **{"Equipamento": "UFV", "Potência (kWp)": 6468.0, "N de Inversores": 20, "Full O&M": "Sim"})]
    out += [_l(**comum, **{"Equipamento": f"UG 0{n}", "Equipamento Parente": "UFV", "Potência (kWp)": 1293.6,
                           "Full O&M": "Sim"}) for n, _p, _s in SKIDS]
    out += [_l(**comum, **{"Usina Supervisório": _chave_skid(n, p), "Equipamento": f"Inversor {n}.{m}",
                           "Equipamento Supervisório": f"INVERSOR0{m}", "Equipamento Parente": f"UG 0{n}",
                           "Potência (kWp)": 323.4, "Strings Ativas": s,
                           "Full O&M": full_om_skid3 if n == 3 else "Sim"})
            for n, p, ss in SKIDS for m, s in enumerate(ss, 1)]
    return out


INFO_ASSIS = {ASSIS: {"nome": "Assis Chateaubriand", "codigo": "THPN-ACB100", "cliente": "Thopen", "kwp": 6296.0,
                      "kwp_de": "contratual", "fracttal": ""}}


def _skid1(cfg, banco):
    return _item(cfg, banco, ASSIS, ASSIS_NEXUS, [
        {"equipamento_supervisorio": f"INVERSOR0{m}", "nome": f"Inversor 1.{m}", "strings": 21,
         "cabine_codigo_fracttal": "THPN-ACB100-CABN1", "codigo_fracttal": f"THPN-ACB100-INVR1.{m}", "conferido": True}
        for m in range(1, 5)])


def test_salvar_so_a_skid_1_da_assis_confere_a_usina_inteira_e_os_leitores_fecham(cfg, banco):
    """A 2ª revisão (dado-6): salvar só a Skid 1 recalcula o kWp da Assis inteira (6.296 contratual ÷ 421 strings), mas
    só a Skid 1 e a "Assis" marcavam: nos leitores a UFV ficava em 6.296 e a soma dos inversores em 6.446,0 (+2,4%), com
    as UG 02 a 04 em 1.256,2 contra 1.293,6 dos inversores delas (as Skid 2 a 5 seguiam com a aba). Agora as 6 chaves são
    conferidas juntas e marcam juntas: nos leitores a UFV, as UG e os inversores fecham com o Registro."""
    aba = _aba_assis()
    _liga_pela_aba(cfg, banco, aba, ASSIS, ["Assis"] + [E.texto(_chave_skid(n, p)) for n, p, _s in SKIDS])
    r = E.salvar_depara([_skid1(cfg, banco)], cfg, BASE, banco, info=INFO_ASSIS, por_codigo=POR_CODIGO,
                        aba_chaves=E.agrupar_aba(aba))
    assert [(m["usina_supervisorio"], m["marcada"]) for m in r["marcacao"]] == [
        (ASSIS_NEXUS, True), ("Assis", True)] + [(E.texto(_chave_skid(n, p)), True) for n, p, _s in SKIDS[1:]]
    lida = E.sobrepor(aba, _livro(banco)["visao"])
    ufv = [x["Potência (kWp)"] for x in lida if x["Equipamento"] == "UFV"]
    invs = [x for x in lida if str(x["Equipamento"]).startswith("Inversor")]
    assert ufv == [6296] and len(invs) == 20 and abs(sum(x["Potência (kWp)"] for x in invs) - 6296) < 0.01
    for n, _p, _s in SKIDS:                                   # cada UG = a soma dos inversores dela, nos leitores
        ug = next(x["Potência (kWp)"] for x in lida if x["Equipamento"] == f"UG 0{n}")
        assert abs(ug - sum(x["Potência (kWp)"] for x in invs if x["Equipamento Parente"] == f"UG 0{n}")) < 0.01
    # a Skid 1 segue achada pela grafia da aba e da API (espaço duplo): os leitores não perdem o cadastro dela
    assert {x["Usina Supervisório"] for x in invs if x["Equipamento"].startswith("Inversor 1.")} == {ASSIS_ABA}


def test_uma_chave_que_nao_vale_segura_a_usina_inteira_assis(cfg, banco):
    """Mesma Assis, com a Skid 3 de Full O&M "Não" na aba (o Nexus tem Sim): a Skid 3 não vale, e nenhuma outra marca (a
    Skid 1 não é igual à aba: o kWp mudou). Os leitores seguem com a aba inteira, que fecha com ela mesma, e o aviso diz
    quanto somariam com só as outras (o estado misto que a regra evita)."""
    _liga_pela_aba(cfg, banco, _aba_assis(), ASSIS, ["Assis"] + [E.texto(_chave_skid(n, p)) for n, p, _s in SKIDS])
    aba = _aba_assis(full_om_skid3="Não")
    r = E.salvar_depara([_skid1(cfg, banco)], cfg, BASE, banco, info=INFO_ASSIS, por_codigo=POR_CODIGO,
                        aba_chaves=E.agrupar_aba(aba))
    m = {x["usina_supervisorio"]: x for x in r["marcacao"]}
    assert len(m) == 6 and not any(x["marcada"] for x in m.values())
    assert m["Assis Chateaubriand Skid 3 (81)"]["fora_da_regra"] == ["Full O&M: Não na aba, Sim no Nexus."]
    assert m[ASSIS_NEXUS]["fora_da_regra"] == [
        "“Assis Chateaubriand Skid 3 (81)”, da mesma usina, não vale(m) no lugar da aba, e a usina vale por inteiro ou nada"]
    t = next(a["texto"] for a in r["avisos"] if a["tipo"] == "nao_marcada" and not a["usina_supervisorio"])
    assert "a usina não passou a valer no lugar da aba" in t and "contra 6.296 kWp do Registro mestre" in t
    assert _livro(banco)["visao"] == [] and E.sobrepor(aba, []) == aba          # os leitores: a aba, como antes


def test_rodrigues_ii_a_principal_que_nunca_vale_segura_a_2_2_e_a_2_3(cfg, banco):
    """Rodrigues II (usina 118): na aba a UFV e as UG estão na "Rodrigues 2", que o Nexus não tem (dois nomes do
    Fracttal, ficou fora do "Ligar pela aba"); a chave da usina no Nexus é a "Rodrigues 2.1 (233)", que nunca vale (a UFV
    em outra chave). Antes a 2.2 e a 2.3 marcavam e os leitores ficavam com a UFV da aba e o kWp novo em parte dos
    inversores (2.116,8 × 2.339,4 no dado real). Agora nada marca."""
    comum = {"Cliente": "Thopen", "Usina": "Rodrigues II", "Full O&M": "Sim", "String Box": "Não"}
    aba = ([_l(**comum, **{"Equipamento": "UFV", "Potência (kWp)": 1800.0})]
           + [_l(**comum, **{"Equipamento": f"UG 0{n}", "Equipamento Parente": "UFV", "Potência (kWp)": 600.0})
              for n in (1, 2, 3)]
           + [_l(**comum, **{"Usina Supervisório": f"Rodrigues 2.{n} ({232 + n})", "Equipamento": f"Inversor 2.{n}.{m}",
                             "Equipamento Supervisório": f"INVERSOR0{m}", "Equipamento Parente": f"UG 0{n}",
                             "Potência (kWp)": 300.0, "Strings Ativas": 20}) for n in (1, 2, 3) for m in (1, 2)])
    chaves = [f"Rodrigues 2.{n} ({232 + n})" for n in (1, 2, 3)]
    _liga_pela_aba(cfg, banco, aba, 118, chaves)
    info = {118: {"nome": "Rodrigues II", "kwp": 2570.0, "kwp_de": "contratual", "cliente": "Thopen", "fracttal": ""}}
    itens = [_item(cfg, banco, 118, c, [{"equipamento_supervisorio": f"INVERSOR0{m}", "strings": 20} for m in (1, 2)])
             for c in chaves[1:]]
    r = E.salvar_depara(itens, cfg, BASE, banco, info=info, por_codigo={}, aba_chaves=E.agrupar_aba(aba))
    m = {x["usina_supervisorio"]: x for x in r["marcacao"]}
    assert set(m) == set(chaves) and not any(x["marcada"] for x in m.values())
    assert any("a linha da usina fica em outra chave" in f for f in m["Rodrigues 2.1 (233)"]["fora_da_regra"])
    assert _livro(banco)["visao"] == []


def _aba_itaja_full_om_diferente():
    return _aba_itaja() + [dict(x, **{"Full O&M": "Não"}) if x["Usina Supervisório"] == CH1 else x
                           for x in _aba_itaja_inv()] + ABA_PHARMA


def test_a_principal_nao_marca_sem_a_chave_do_pedido_e_os_leitores_nao_ficam_com_cabine_orfa(cli, cfg, banco):
    """A regressão da 2ª revisão (a): a Itajá com o Full O&M da Itaja 1 diferente na aba. Salvar a Itaja 1 levando os
    inversores para a CABN2 marcava a "Itajá" sozinha e excluía a UG 01: nos leitores sobrava só a UG 02, e os 4
    inversores da Itaja 1 (vindos da aba) seguiam apontando para a UG 01, que não existia mais. Agora a "Itajá" não marca
    (a Itaja 1 não vale, e a Itaja 2, fora do pedido, fica segura junto), e os leitores seguem com as duas UG da aba."""
    aba = _aba_itaja_full_om_diferente()
    _poe_aba(banco, aba)
    _monta_itaja(cfg, banco)
    j = _salvar(cli, [_item_itaja(cli, cabine_codigo_fracttal="ITA100-CABN2")]).get_json()
    assert j["ok"], j
    assert {x["usina_supervisorio"]: x["marcada"] for x in j["marcacao"]} == {CH1: False, CH_USINA: False, CH2: False}
    lida = E.sobrepor(aba, _livro(banco)["visao"])
    ugs = sorted(x["Equipamento"] for x in lida if E.chave_efetiva(x) == CH_USINA and x["Equipamento"] != "UFV")
    pais = {x["Equipamento Parente"] for x in lida if str(x["Equipamento"]).startswith("Inversor")}
    assert ugs == ["UG 01", "UG 02"] and pais <= set(ugs)                   # nenhum inversor numa UG que não existe


def _pela_base(cfg, banco, marca=(), cabine=None, kwp_cab=None):
    """O que a Base > Equipamentos das usinas grava na Itajá (`salvar_usina`): a usina como está, com as chaves de `marca`
    também no lugar da aba, os inversores de `cabine` ({nome do inversor: nome da cabine}) em outra cabine e o kWp de
    `kwp_cab` ({nome da cabine: kWp}). Os códigos do Fracttal voltam como estão (a tela devolve o que leu)."""
    u = _u(cfg, banco, ITAJA)
    k_de = {c["nome"]: f"c{c['cabine_id']}" for c in u["cabines"]}
    p = {"chaves": [dict({k: s[k] for k in ("supervisorio_id", "usina_exibicao", "principal", "full_om", "string_box")},
                         substitui_aba=bool(s["substitui_aba"]) or s["usina_supervisorio"] in marca)
                    for s in u["supervisorios"]],
         "cabines": [{"id": c["cabine_id"], "k": f"c{c['cabine_id']}", "nome": c["nome"],
                      "potencia_kwp": (kwp_cab or {}).get(c["nome"], c["potencia_kwp"]),
                      "equipamento_id": c["equipamento_id"], "codigo_fracttal": c["codigo_fracttal"]} for c in u["cabines"]],
         "inversores": [{"id": i["inversor_id"], "nome": i["nome"], "chave": i["supervisorio_id"],
                         "cabine": k_de.get((cabine or {}).get(i["nome"]), f"c{i['cabine_id']}"),
                         "equipamento_supervisorio": i["equipamento_supervisorio"], "potencia_kwp": i["potencia_kwp"],
                         "strings_esperadas_qtd": i["strings_esperadas_qtd"], "equipamento_id": i["equipamento_id"],
                         "codigo_fracttal": i["codigo_fracttal"]} for i in u["inversores"]]}
    E.salvar_usina(ITAJA, p, E.selo(u), cfg, BASE, banco)


def test_com_a_chave_da_ufv_valendo_mover_de_cabine_a_que_segue_com_a_aba_recusa_a_usina(cli, cfg, banco):
    """O guarda da cabine órfã (3ª revisão, 21/10/2026): a "Itajá" (a UFV e as UG) marcada na Base > Equipamentos e a
    Itaja 1 com o Full O&M diferente na aba, seguindo com a aba. Levar a Itaja 1 para a CABN2 passava, não marcava nada
    e só segurava a UG 01 no Nexus: nos leitores a UG 02 ia com 2.596 kWp (os 8 inversores do Nexus) e só os 1.298,08
    da Itaja 2, vindos da aba, apontavam para ela. Agora recusa a usina (409, com a culpada) e nada é gravado; com a
    Itaja 1 acertada na aba, o mesmo salvar passa, as três chaves valem e a UG 01 sai."""
    _poe_aba(banco, _aba_itaja_full_om_diferente())
    _monta_itaja(cfg, banco)
    _pela_base(cfg, banco, marca=(CH_USINA,))
    assert _marca(banco) == {CH_USINA: 1, CH1: 0, CH2: 0}
    antes = (banco.syncs, _livro(banco))
    r = _salvar(cli, [_item_itaja(cli, cabine_codigo_fracttal="ITA100-CABN2")])
    j = r.get_json()
    assert r.status_code == 409 and (j["usina_id"], j["usina_supervisorio"]) == (ITAJA, CH1), j
    assert (f"a chave da UFV vale no lugar da aba e “{CH1}” segue com a aba: mover os inversores de “{CH1}” de cabine "
            f"deixaria a UFV e as UG dos leitores sem fechar; acerte “{CH1}” ou salve as chaves juntas") in j["motivo"]
    assert (banco.syncs, _livro(banco)) == antes                             # nada foi gravado
    # a Itaja 1 acertada na aba: o mesmo salvar marca a usina inteira, e a UG 01 vazia, sem código, sai
    aba_certa = _aba_itaja() + _aba_itaja_inv() + ABA_PHARMA
    _poe_aba(banco, aba_certa)
    j = _salvar(cli, [_item_itaja(cli, cabine_codigo_fracttal="ITA100-CABN2")]).get_json()
    assert j["ok"] and _marca(banco) == {CH_USINA: 1, CH1: 1, CH2: 1}, j
    assert [c["nome"] for c in j["cabines_excluidas"]] == ["UG 01"]
    lida = E.sobrepor(aba_certa, _livro(banco)["visao"])
    assert [x["Equipamento"] for x in lida if E.chave_efetiva(x) == CH_USINA] == ["UFV", "UG 02"]
    assert {x["Equipamento Parente"] for x in lida if E.chave_efetiva(x) in (CH1, CH2)} == {"UG 02"}


def test_a_ug_vazia_sem_codigo_sai_quando_nenhuma_chave_que_segue_com_a_aba_aponta_para_ela(cli, cfg, banco):
    """A UG sem código do Fracttal e sem inversor no Nexus sai a CADA salvar da usina, não só a que ele esvaziou (3ª
    revisão, 21/10/2026). O guarda a segura enquanto a chave da UFV vale e uma chave que segue com a aba aponta para ela
    na aba ("Sai quando essas chaves valerem", dizia o aviso), mas nada a tirava depois: a UG 01 da Itajá (a Itaja 1
    levada para a UG 02 na Base, a "Itajá" marcada) ficava no Nexus para sempre e ia aos leitores vazia, com o kWp antigo,
    ao lado da UG 02 com a usina toda, depois que a Itaja 1 passava a valer."""
    _poe_aba(banco, _aba_itaja_full_om_diferente())
    _monta_itaja(cfg, banco)
    assert _salvar(cli, [_item_itaja(cli, chave=CH2, n=2)]).get_json()["ok"]  # a UG 02 com a CABN2; nada marca
    _pela_base(cfg, banco, marca=(CH_USINA,), cabine={f"Inversor 1.{m}": "UG 02" for m in range(1, 5)},
               kwp_cab={"UG 02": 2596.0})
    # a Itaja 1 segue com a aba e aponta para a UG 01 nela: o salvar (que não muda a visão da "Itajá") a deixa, com o aviso
    j = _salvar(cli, [_item_itaja(cli, chave=CH2, n=2)]).get_json()
    assert j["ok"] and j["cabines_excluidas"] == [] and _marca(banco) == {CH_USINA: 1, CH1: 0, CH2: 0}, j
    assert not next(c for c in _livro(banco)["cab"] if c["nome"] == "UG 01")["excluido"]
    t = _avisos(j, "cabine_sem_inversores")
    assert any(x.startswith("A cabine UG 01 (usina 93) estava sem inversores no Nexus e fica") and "órfãos" in x
               and f"“{CH1}”" in x for x in t), t
    # a Itaja 1 acertada na aba: a usina vale inteira e a UG 01, sem chave que siga com a aba apontando para ela, sai
    aba_certa = _aba_itaja() + _aba_itaja_inv() + ABA_PHARMA
    _poe_aba(banco, aba_certa)
    j = _salvar(cli, [_item_itaja(cli, chave=CH2, n=2)]).get_json()
    assert j["ok"] and _marca(banco) == {CH_USINA: 1, CH1: 1, CH2: 1}, j
    ug01 = next(c for c in _livro(banco)["cab"] if c["nome"] == "UG 01")
    assert ug01["excluido"] and j["cabines_excluidas"] == [{"cabine_id": ug01["cabine_id"], "usina_id": ITAJA,
                                                             "nome": "UG 01"}]
    assert any(x.startswith("A cabine UG 01 (usina 93) estava sem inversores e saiu") for x in _avisos(j, "cabine_excluida"))
    lida = E.sobrepor(aba_certa, _livro(banco)["visao"])
    assert [(x["Equipamento"], x["Potência (kWp)"], x["N de Inversores"]) for x in lida
            if E.chave_efetiva(x) == CH_USINA] == [("UFV", 2596, 8), ("UG 02", 2596, 8)]
    assert {x["Equipamento Parente"] for x in lida if E.chave_efetiva(x) in (CH1, CH2)} == {"UG 02"}


def test_a_ja_marcada_cuja_visao_muda_volta_para_a_aba_numa_usina_segura(cli, cfg, banco):
    """A outra porta do estado parcial (3ª revisão, 21/10/2026): a Itaja 2 já marcada (na Base > Equipamentos, ou pela
    exceção "igual à aba marca sozinha" que havia até a 3ª revisão) e a Itaja 1 com o Full O&M diferente na aba. O
    Salvar da Itaja 1 com 20 strings refaz o kWp da usina inteira: a Itaja 2 levava 316,18 por inversor aos leitores
    (2.596 ÷ 156 × 19) ao lado da UG 02 da aba, 1.298,08. Agora ela volta para a aba, com o aviso, e os leitores seguem
    com a aba na usina inteira; o salvar que NÃO muda a visão dela a deixa como está."""
    aba = _aba_itaja_full_om_diferente()
    _poe_aba(banco, aba)
    _monta_itaja(cfg, banco)
    assert _salvar(cli, [_item_itaja(cli)]).get_json()["ok"]                # a regra põe 324,5 em todos; nada marca
    _pela_base(cfg, banco, marca=(CH2,))
    assert _marca(banco) == {CH_USINA: 0, CH1: 0, CH2: 1}
    j = _salvar(cli, [_item_itaja(cli)]).get_json()                        # o mesmo salvar: a visão da Itaja 2 não muda
    assert j["ok"] and _marca(banco) == {CH_USINA: 0, CH1: 0, CH2: 1}, j
    assert CH2 not in [m["usina_supervisorio"] for m in j["marcacao"]]
    j = _salvar(cli, [_item_itaja(cli, strings=20)]).get_json()
    assert j["ok"] and _marca(banco) == {CH_USINA: 0, CH1: 0, CH2: 0}, j
    m = next(x for x in j["marcacao"] if x["usina_supervisorio"] == CH2)
    assert m["marcada"] is False and m["fora_da_regra"] == [
        f"“{CH1}”, da mesma usina, não vale(m) no lugar da aba, e a usina vale por inteiro ou nada: ela valia, e este "
        "Salvar mudou o que ela leva aos leitores"]
    aviso = next(a["texto"] for a in j["avisos"] if a["tipo"] == "nao_marcada" and a["usina_supervisorio"] == CH2)
    assert aviso.startswith(f"A chave “{CH2}” valia no lugar da aba e voltou para a aba") and f"“{CH1}”" in aviso
    # o Nexus guarda o kWp da regra; os leitores, sem chave da Itajá na visão, leem a aba inteira (324,52 e 1.298,08)
    assert {i["potencia_kwp"] for i in j["usinas"][0]["inversores"] if i["nome"].startswith("Inversor 2.")} == {
        round(2596 / 156 * 19, 3)}
    assert [x for x in _livro(banco)["visao"] if E.chave_efetiva(x) in (CH_USINA, CH1, CH2)] == []


# a Coração 1 e 2 (usina 77): na aba, "Coração 1 (111)" com 13 inversores e "Coração 2 (112)" com 4 (GET de 20/10)
ABA_CORACAO_1 = [_l(Cliente="Thopen", Usina="Coração 1", **{
    "Usina Supervisório": "Coração 1 (111)", "Usina Fractall": "Thopen - Coração 1 e 2 - SC",
    "Equipamento": f"Inversor 1.{m}", "Equipamento Supervisório": f"INVERSOR{m:02d}", "Equipamento Parente": "UG 01",
    "Potência (kWp)": 250.0, "Strings Ativas": 20, "Full O&M": "Sim", "String Box": "Não"}) for m in range(1, 14)]


def test_chave_irma_da_aba_fora_do_nexus_recusa_a_usina_ate_salvar_as_duas(cli, banco, monkeypatch):
    """A 2ª revisão (dado-1): a Coração 2 salva sozinha semeava só a "Coração 2 (112)" e dividia os 3.250 do Registro só
    pelas 80 strings dela (250 → 812,5 kWp por inversor), e a usina somaria 6.500 nos leitores (a Coração 1 pela aba e a
    Coração 2 pelo Nexus). A chave da aba que, pela regra do "Ligar pela aba" (a Usina Fractall nas Ligações), é da MESMA
    usina e não está no Nexus nem no pedido recusa a usina (409, com a culpada); as duas juntas passam e dividem pelas
    340 strings. Na aba real a Usina Fractall da Coração 1 (111) é "Thopen - Coração 1 - SC", que as Ligações não têm: lá
    quem pega é a tela (as duas plantas estão na `pv`, e ela pede para salvar juntas)."""
    from nexus.cadastro import ligacoes as L
    monkeypatch.setattr(L, "ler", lambda cfg: {"linhas": [[CORACAO, L.FRACTTAL, "Thopen - Coração 1 e 2 - SC", "código"]]})
    _poe_aba(banco, ABA + ABA_CORACAO_1)
    u = _estado(cli, usinas=str(CORACAO))["usinas"][0]
    so2 = {"usina_supervisorio": CH_COR, "usina_id": CORACAO, "selo": u["selo"],
           "inversores": [{"equipamento_supervisorio": f"INVERSOR0{m}", "strings": 20} for m in range(1, 5)]}
    r = _salvar(cli, [so2])
    j = r.get_json()
    assert r.status_code == 409 and (j["usina_id"], j["usina_supervisorio"]) == (CORACAO, CH_COR), j
    assert "“Coração 1 (111)”" in j["motivo"] and "Salve as plantas juntas" in j["motivo"]
    assert _livro(banco)["sup"] == []
    so1 = {"usina_supervisorio": "Coração 1 (111)", "usina_id": CORACAO, "selo": u["selo"],
           "inversores": [{"equipamento_supervisorio": f"INVERSOR{m:02d}", "strings": 20} for m in range(1, 14)]}
    j = _salvar(cli, [so2, so1]).get_json()
    assert j["ok"], j
    assert {i["potencia_kwp"] for i in j["usinas"][0]["inversores"]} == {round(3250 / 340 * 20, 3)}     # 191,176


@pytest.mark.parametrize("fr", ["Thopen - Belo Jardim  1 - PE",      # como as Ligações têm (o real)
                                "Thopen - Belo Jardim 1 - PE"])      # com os espaços juntados
def test_belo_jardim_o_nome_do_fracttal_vai_como_o_fracttal_escreve(cfg, banco, fr):
    """A 2ª revisão (dado, alta): a visão escrevia o "Usina Fractall" com os espaços juntados ("Thopen - Belo Jardim 1 -
    PE"), e o índice de code-base da plataforma guarda a description exata do Fracttal, com espaço DUPLO: a Belo Jardim
    (usina 32) marcada ficava "fora do Fracttal" (sem OS abertas, sem a cascata de queda) sem aviso. A visão escreve o
    nome como as Ligações o têm; e, se ele vier com os espaços juntados, o `sobrepor` herda a grafia da aba."""
    bj = "Thopen - Belo Jardim  1 - PE"
    comum = {"Cliente": "Thopen", "Usina": "Belo Jardim", "Usina Supervisório": "Belo Jardim (588)",
             "Usina Fractall": bj, "Full O&M": "Sim", "String Box": "Não"}
    aba = ([_l(**comum, **{"Equipamento": "UFV", "Potência (kWp)": 2664.0, "N de Inversores": 8}),
            _l(**comum, **{"Equipamento": "UG 01", "Equipamento Parente": "UFV", "Potência (kWp)": 2664.0})]
           + [_l(**comum, **{"Equipamento": f"Inversor 1.{m}", "Equipamento Supervisório": f"INVERSOR0{m}",
                             "Equipamento Parente": "UG 01", "Potência (kWp)": 333.0, "Strings Ativas": 21})
              for m in range(1, 9)])
    _liga_pela_aba(cfg, banco, aba, 32, ["Belo Jardim (588)"])
    info = {32: {"nome": "Belo Jardim", "kwp": 2664.0, "kwp_de": "real", "cliente": "Thopen", "fracttal": fr}}
    r = E.salvar_depara([_item(cfg, banco, 32, "Belo Jardim (588)", [
        {"equipamento_supervisorio": f"INVERSOR0{m}", "strings": 21} for m in range(1, 9)])], cfg, BASE, banco,
        info=info, por_codigo={}, aba_chaves=E.agrupar_aba(aba))
    assert [m["marcada"] for m in r["marcacao"]] == [True], r["marcacao"]
    visao = _livro(banco)["visao"]
    assert {x["Usina Fractall"] for x in visao} == {fr}                        # a visão: o nome das Ligações
    assert {x["Usina Fractall"] for x in E.sobrepor(aba, visao)} == {bj}       # os leitores: a grafia do Fracttal
    # acento é outra description no índice do Fracttal: a comparação acusa e a chave não marca; caixa e espaço, não
    g = E.agrupar_aba([dict(x, **{"Usina Fractall": "Thopen - Taguai 1 e 2 - SP"}) for x in aba])["Belo Jardim (588)"]
    assert [i["tipo"] for i in E.comparar_chave(g, [dict(x, **{"Usina Fractall": "Thopen - Taguaí 1 e 2 - SP"})
                                                    for x in visao])["itens"]] == ["fracttal"]
    assert E.comparar_chave(g, [dict(x, **{"Usina Fractall": "THOPEN -  Taguai 1 e 2 - SP"}) for x in visao])["iguais"]


def test_taguai_o_nome_de_exibicao_das_linhas_da_aba_que_diferem_nao_marca(cfg, banco):
    """A 2ª revisão (dado): na Taguaí (usina 136) a 1ª linha da "Taguaí 1 (173)" na aba é uma UFV solta com Usina =
    "Taguaí 1 (173)", e os inversores dizem "Taguaí". O "Ligar pela aba" guardava o da 1ª linha, a visão escrevia "Taguaí 1
    (173)" em todos os inversores e a comparação (só com a 1ª linha) não via: as chaves marcavam e o USINA_GRUPO trocava
    (as duas plantas deixavam de se juntar no macro e na Entrada; nas Falhas, cad_inv('Taguaí','Inversor 1.1') caía em
    'ufv/n'). Agora a aba agrupada guarda o nome dos inversores (o "Ligar pela aba" de agora semeia "Taguaí") e a
    comparação acusa a chave em que as linhas da aba não dizem um nome só."""
    comum = {"Cliente": "Thopen", "Full O&M": "Sim", "String Box": "Não"}
    fr = {"Usina Fractall": "Thopen - Taguai 1 e 2 - SP"}
    aba = ([_l(Cliente="Thopen", Usina=f"Taguaí {n} ({172 + n})", **{"Usina Supervisório": f"Taguaí {n} ({172 + n})",
                                                                     "Equipamento": "UFV", "Full O&M": "Não",
                                                                     "String Box": "Não"}) for n in (1, 2)]
           + [_l(**comum, Usina="Taguaí", **fr, **{"Equipamento": "UFV", "Potência (kWp)": 2049.0,
                                                   "N de Inversores": 6})]
           + [_l(**comum, Usina="Taguaí", **fr, **{"Equipamento": f"UG 0{n}", "Equipamento Parente": "UFV",
                                                   "Potência (kWp)": k}) for n, k in ((1, 1366.0), (2, 683.0))]
           + [_l(**comum, Usina="Taguaí", **fr, **{"Usina Supervisório": f"Taguaí {n} ({172 + n})",
                                                   "Equipamento": f"Inversor {n}.{m}",
                                                   "Equipamento Supervisório": f"INVERSOR0{m}",
                                                   "Equipamento Parente": f"UG 0{n}", "Potência (kWp)": 341.5,
                                                   "Strings Ativas": 20})
              for n, q in ((1, 4), (2, 2)) for m in range(1, q + 1)])
    g = E.agrupar_aba(aba)
    assert (g["Taguaí 1 (173)"]["usina"], g["Taguaí 1 (173)"]["usinas"]) == ("Taguaí", ["Taguaí 1 (173)", "Taguaí"])
    _liga_pela_aba(cfg, banco, aba, 136, ["Taguaí", "Taguaí 1 (173)", "Taguaí 2 (174)"])
    assert {s["usina_supervisorio"]: s["usina_exibicao"] for s in _livro(banco)["sup"]} == {
        "Taguaí": "Taguaí", "Taguaí 1 (173)": "Taguaí", "Taguaí 2 (174)": "Taguaí"}       # o "Ligar pela aba" de agora
    info = {136: {"nome": "Taguaí", "kwp": 2049.0, "kwp_de": "real", "cliente": "Thopen",
                  "fracttal": "Thopen - Taguai 1 e 2 - SP"}}
    itens = [_item(cfg, banco, 136, c, [{"equipamento_supervisorio": f"INVERSOR0{m}", "strings": 20}
                                        for m in range(1, q + 1)]) for c, q in (("Taguaí 1 (173)", 4), ("Taguaí 2 (174)", 2))]
    r = E.salvar_depara(itens, cfg, BASE, banco, info=info, por_codigo={}, aba_chaves=g)
    m = {x["usina_supervisorio"]: x for x in r["marcacao"]}
    assert not any(x["marcada"] for x in m.values())
    assert m["Taguaí 1 (173)"]["fora_da_regra"] == ["Nome de exibição: “Taguaí 1 (173)” na aba, “Taguaí” no Nexus."]
    assert _livro(banco)["visao"] == []                     # o USINA_GRUPO dos leitores segue "Taguaí"


def test_o_estado_diz_gravando_enquanto_o_salvar_roda(app_dp, cli, cfg, banco, monkeypatch):
    """A 2ª revisão (contrato-7): no estouro de 180 s e no 502/504 do proxy, o pedido abandonado continua no servidor
    (o waitress serve em threads) e o estado relido na hora devolvia o selo de antes: a tela concluía "está como antes:
    salve de novo", o Nexus gravava segundos depois e o 2º Salvar levava 409. O estado diz `gravando`."""
    import threading
    _monta_itaja(cfg, banco)
    item = _item_itaja(cli)
    entrou, solta = threading.Event(), threading.Event()
    real = E.livros.publicar

    def devagar(*a, **k):                     # o sync-xlsx do livro inteiro demorando (o Nexus espera até 300 s)
        entrou.set()
        solta.wait(30)
        return real(*a, **k)
    monkeypatch.setattr(E.livros, "publicar", devagar)
    assert _estado(cli, usinas=str(ITAJA))["gravando"] is False
    c2, out = app_dp.test_client(), {}
    assert c2.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    t = threading.Thread(target=lambda: out.setdefault("r", _salvar(c2, [item])))
    t.start()
    assert entrou.wait(30)
    meio = _estado(cli, usinas=str(ITAJA))
    solta.set()
    t.join(30)
    depois = _estado(cli, usinas=str(ITAJA))
    assert (meio["gravando"], meio["usinas"][0]["selo"]) == (True, item["selo"])      # o selo ainda é o de antes
    assert out["r"].status_code == 200 and depois["gravando"] is False and depois["usinas"][0]["selo"] != item["selo"]
    # e ANTES da trava (a leitura da aba e da dimensão, ~5 s na 1ª vez): o pedido já conta como gravação em curso
    entrou.clear(), solta.clear()
    monkeypatch.setattr(E.livros, "publicar", real)
    aba_real = E.aba_equipamentos

    def aba_devagar(base, sessao):
        entrou.set()
        solta.wait(30)
        return aba_real(base, sessao)
    monkeypatch.setattr(E, "aba_equipamentos", aba_devagar)
    item = _item_itaja(cli, strings=20)
    t = threading.Thread(target=lambda: out.update(r=_salvar(c2, [item])))
    t.start()
    assert entrou.wait(30)
    meio = _estado(cli, usinas=str(ITAJA))
    solta.set()
    t.join(30)
    assert meio["gravando"] is True and out["r"].status_code == 200 and _estado(cli, usinas=str(ITAJA))["gravando"] is False


# ── a tela Base > Equipamentos das usinas conhece as colunas novas ───────────────────────────────────────────────────
def test_o_kwp_digitado_na_tela_e_informada_e_o_calculado_segue_a_regra(cli, cfg, banco):
    _monta_itaja(cfg, banco)
    assert {i["potencia_regra"] for i in _livro(banco)["inv"]} == {"informada"}     # o 324,52 digitado
    _salvar(cli, [_item_itaja(cli, quais=(1,))])
    u = _u(cfg, banco, ITAJA)

    def payload(mexe=None):
        invs = []
        for i in u["inversores"]:
            x = {"id": i["inversor_id"], "nome": i["nome"], "chave": i["supervisorio_id"], "cabine": f"c{i['cabine_id']}",
                 **{k: i[k] for k in ("equipamento_supervisorio", "potencia_kwp", "strings_esperadas_qtd",
                                      "equipamento_id", "codigo_fracttal")}}
            if mexe and i["nome"] == "Inversor 1.1":
                x.update(mexe)
            invs.append(x)
        return {"chaves": [{k: s[k] for k in ("supervisorio_id", "usina_exibicao", "principal", "full_om", "string_box",
                                              "substitui_aba")} for s in u["supervisorios"]],
                "cabines": [{"id": c["cabine_id"], "k": f"c{c['cabine_id']}", **{k: c[k] for k in (
                    "nome", "potencia_kwp", "equipamento_id", "codigo_fracttal")}} for c in u["cabines"]],
                "inversores": invs}
    # abrir e salvar sem mexer: nada muda, e o kWp do de-para segue com a regra dele
    assert E.salvar_usina(ITAJA, payload(), E.selo(u), cfg, BASE, banco)["mudancas"] == 0
    # o kWp digitado vira "informada"; o código trocado na tela perde o Conferido (era daquele código)
    E.salvar_usina(ITAJA, payload({"potencia_kwp": 300, "codigo_fracttal": "ITA100-INVR1.4"}), E.selo(u), cfg, BASE,
                   banco)
    i11 = next(i for i in _livro(banco)["inv"] if i["nome"] == "Inversor 1.1")
    assert (i11["potencia_kwp"], i11["potencia_regra"], i11["fracttal_ligado_por"], i11["conferido_em"]) == (
        300, "informada", None, None)
    assert next(i for i in _livro(banco)["inv"] if i["nome"] == "Inversor 1.2")["potencia_regra"] == "real_por_string"


def test_as_colunas_novas_vao_no_fim_e_a_linha_antiga_le_vazio():
    assert E.CAB_CAB[-2:] == ("excluido", "potencia_regra")
    assert E.CAB_INV[-4:] == ("excluido", "potencia_regra", "fracttal_ligado_por", "conferido_em")
    assert E.CAB_VISAO[-2:] == ("inversor_id", "Código Fracttal")
    antiga = {"inversor_id": 1, "usina_id": 93, "nome": "Inversor 1.1", "potencia_kwp": "324,52"}
    i = E._inv(antiga)
    assert (i["potencia_regra"], i["fracttal_ligado_por"], i["conferido_em"]) == ("", "", "")
    # valor fora da lista fechada vira vazio na leitura (nunca o vizinho mais parecido)
    assert E._inv(dict(antiga, potencia_regra="chute", fracttal_ligado_por="Conferido"))["potencia_regra"] == ""
    assert E._inv(dict(antiga, fracttal_ligado_por="Conferido"))["fracttal_ligado_por"] == "conferido"
    assert E._cab({"cabine_id": 1, "nome": "UG 01", "potencia_regra": "informada"})["potencia_regra"] == "informada"
    assert DOM.POTENCIA_REGRA == ("real_por_string", "contratual_por_string", "informada")


def test_nome_da_cabine_e_do_inversor_saem_do_codigo():
    assert E.nome_da_cabine("ITA100-CABN2") == "UG 02" and E.nome_da_cabine("thpn-phs100-cabn10") == "UG 10"
    assert E.nome_da_cabine("ALT100-SKID1") == "" and E.nome_da_cabine("ITA100-INVR1.1") == ""
    assert E.rotulo_do_inversor("THPN-PHS100-INVR2.1") == "Inversor 2.1"
    assert E.rotulo_do_inversor("THPN-SDI100-INVR11.1") == "Inversor 11.1" and E.rotulo_do_inversor("X-CABN1") == ""


# ── quem pode ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_so_administrador_e_so_da_mesma_origem(app_dp, cli, cfg, banco):
    _monta_itaja(cfg, banco)
    item = _item_itaja(cli)
    syncs = banco.syncs
    c = app_dp.test_client()
    with c.session_transaction() as s:
        s["logado"] = True; s["admin"] = False
        s["usuario"] = {"email": "pessoa@exemplo.test", "nome": "Pessoa", "perfil": ""}
    assert c.get(ESTADO, query_string={"chaves": CH1}).status_code == 403
    assert c.post(SALVAR, json={"itens": [item]}).status_code == 403
    assert app_dp.test_client().get(ESTADO, query_string={"chaves": CH1}).status_code in (302, 401)   # sem login
    for h in ({"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"}, {"Origin": "https://outro.exemplo"}):
        assert _salvar(cli, [item], **h).status_code == 403
        assert cli.get(ESTADO, query_string={"chaves": CH1}, headers=h).status_code == 403
    assert banco.syncs == syncs
    # da mesma origem, grava
    assert _salvar(cli, [item], **{"Sec-Fetch-Site": "same-origin"}).get_json()["ok"]


def test_o_estado_pelas_chaves_e_pelas_usinas(cli, cfg, banco):
    s1, s2, s3 = _monta_itaja(cfg, banco)
    j = _estado(cli, chaves=f"{CH1}|{CH2}|Chave que não existe", usinas=f"{PHARMA},777")
    assert [u["usina_id"] for u in j["usinas"]] == [PHARMA, ITAJA]           # a Itajá uma vez só, pelas duas chaves
    assert j["chaves_sem_usina"] == ["Chave que não existe"] and j["usinas_fora_do_registro"] == ["777"]
    it = j["usinas"][1]
    assert [(c["usina_supervisorio"], c["principal"]) for c in it["chaves"]] == [(CH_USINA, True), (CH1, False),
                                                                                 (CH2, False)]
    i = it["inversores"][0]
    assert set(i) == {"inversor_id", "supervisorio_id", "usina_supervisorio", "nome", "equipamento_supervisorio",
                      "cabine_id", "strings_esperadas_qtd", "potencia_kwp", "codigo_fracttal", "equipamento_id",
                      "potencia_regra", "fracttal_ligado_por", "conferido_em"}
    assert (i["usina_supervisorio"], i["supervisorio_id"], i["strings_esperadas_qtd"]) == (CH1, s2, 19)
    assert cli.get(ESTADO).status_code == 400
