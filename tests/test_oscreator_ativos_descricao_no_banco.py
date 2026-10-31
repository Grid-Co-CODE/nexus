"""A revisão 2 da tarefa 2.2 do canto central do OS Creator (31/10/2026): a descrição que vai ao banco sem o endereço da
usina, em TODA linha da foto dos ativos (Ruling AN).

O que estes testes seguram:
- a linha que saiu do Fracttal (os códigos de junho, os que saírem depois) também perde o endereço: a descrição dela é
  recalculada pelo grafo da noite (os itens lidos hoje e as linhas antigas que não vieram), com a marca e o `foto_em` pelas
  regras do `renovar`; e a 2ª noite não muda nada (idempotente). O teste parte de uma foto com linha que saiu E endereço;
- o detector de endereço, depois do corte do nome no caminho: a usina fora de "Cliente - Usina - UF" com o endereço depois de
  UM espaço, o nível de dentro com o mesmo endereço e o nível com endereço próprio; a linha sem nome vai sem descrição;
- o detector vale SÓ para o banco: o caminho do catálogo (o cliente e a usina da tela) e a paridade com o RPC não mudam;
- a noite conta as descrições que o detector cortou, com até 5 ids de exemplo e nunca o texto, e o estado do leitor mostra;
- a revisão 3 (Ruling AQ): a usina cujo nome fechou no padrão "Cliente - Usina - UF" não passa pelo detector (a usina de
  fazenda), inclusive a que saiu; o nível de dentro e a usina fora do padrão seguem por ele; e a foto servindo de catálogo
  mantém as usinas de fazenda separadas.
Fracttal e banco são dublês: nada vai à rede. Nomes, códigos, usinas e endereços são de mentira (repositório público)."""
import json
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest
from pg_falso import ApiPGFalsa

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
import ativos_central as AC  # noqa: E402
import ativos_foto as AF  # noqa: E402
import ativos_leitor as AL  # noqa: E402

from nexus.dados import equipamento as eq  # noqa: E402
from nexus.dados import foto_ativos as FA  # noqa: E402
from test_oscreator_ativos_leitor import ARVORE, GAMA, RestFalso, _catalogo_de, _it, _rpc  # noqa: E402

BASE = "http://pg.falso"
_BRT = timezone(timedelta(hours=-3))


@pytest.fixture(autouse=True)
def limpo(monkeypatch):
    AC.reiniciar()
    AL.reiniciar()
    monkeypatch.setattr(AL, "_dormir", lambda s: None)
    monkeypatch.setattr(api, "_ASSETS_RENOVA", {"tentou": time.time()})       # a renovação por trás fica de fora
    yield
    AC.reiniciar()
    AL.reiniciar()


@pytest.fixture
def banco(app):
    pg = ApiPGFalsa(como_texto=True)
    app.extensions["nexus_dados_sessao"] = pg
    app.config.update(GRIDCO_SQL_TOKEN="token-de-teste", GRIDCO_DB_API=BASE)
    return pg


def _semear(pg, linhas, colunas=6):
    """A foto já no banco: a carga única de 11/10 (só as 6 colunas de então) ou a renovada (as 9), tudo texto."""
    pg.workbooks[eq.LIVRO_FOTO] = {"key": eq.LIVRO_FOTO, "display_name": eq.NOME_FOTO}
    pg._id(eq.LIVRO_FOTO, eq.ABA_FOTO)["linhas"] = [{"headers": list(eq.CAB_FOTO[:colunas]), "values": l} for l in linhas]


def _por_id(pg) -> dict:
    return {int(l["fracttal_item_id"]): l for l in pg.linhas(eq.LIVRO_FOTO, eq.ABA_FOTO)}


def _hoje_id() -> int:
    return int(datetime.now(_BRT).strftime("%Y%m%d"))


# a carga única de 11/10 com o endereço da usina atrás do nome (como o Fracttal escreve) e linhas que saíram: uma da foto de
# 22/09 que sai hoje e as de junho (a usina que saiu inteira, um inversor dela e dois da usina que segue)
FOTO_DE_11_10 = [
    ["10", "CAL-GAM100", GAMA + "  Zona Rural km 4", "1", "USINA", "2026-09-22"],
    ["20", "CAL-GAM100-CABN1", "Cabine 1 Zona Rural km 4", "10", "CABN", "2026-09-22"],
    ["34", "CAL-GAM100-INVR9.9", "Inversor 9.9  Zona Rural km 4", "21", "INVR", "2026-09-22"],
    ["12", "CAL-VEL300", "Cliente Alfa - Usina Velha 3 - MT  Estrada Vicinal km 9", "1", "USINA", "2026-06-21"],
    ["78", "CAL-VEL300-INVR1.1", "Inversor 1.1  Estrada Vicinal km 9", "12", "INVR", "2026-06-21"],
    ["77", "CAL-GAM100-INVR7.7", "Inversor 7.7  Zona Rural km 4", "10", "INVR", "2026-06-21"],
    ["79", "CAL-GAM100-INVR8.8", "Inversor 8.8 Rua Outra 55", "10", "INVR", "2026-06-21"],
]
ENDERECOS = ("Zona Rural", "km 4", "Estrada Vicinal", "km 9", "Rua Outra", "Rua Sem Padrao")


# ── furo 1: a linha que saiu também perde o endereço, e a 2ª noite não muda nada ────────────────────────────────────────
def test_a_linha_que_saiu_perde_o_endereco_e_a_segunda_noite_nao_muda_nada(app, banco):
    _semear(banco, FOTO_DE_11_10)
    AC.trocar(AC.montar_registros(_rpc()), "rpc", lido_em=time.time() - 7200)
    rel = AL.ler_completo(app, ler=RestFalso(ARVORE))
    assert rel["foto"]["gravou"] and banco.syncs == 1
    por = _por_id(banco)
    for l in por.values():                                              # nenhuma descrição do banco leva endereço
        assert not any(e in (l["descricao"] or "") for e in ENDERECOS), l
    assert (por[34]["descricao"], por[12]["descricao"], por[78]["descricao"], por[77]["descricao"], por[79]["descricao"]) == (
        "Inversor 9.9", "Cliente Alfa - Usina Velha 3 - MT", "Inversor 1.1", "Inversor 7.7", "Inversor 8.8")
    # o corte do nome no caminho tirou a cauda de endereço da usina; o detector só o endereço próprio da 79
    assert rel["foto"]["descricao_cortada"] == 1 and rel["foto"]["descricao_cortada_exemplos"] == [79]
    # a marca e o dia pelas regras do `renovar`: a de 22/09 saiu hoje; as de junho já não estavam na foto de 22/09
    hoje = datetime.now(_BRT).date().isoformat()
    assert int(por[34]["fora_do_fracttal_desde"]) == _hoje_id()
    assert {int(por[i]["fora_do_fracttal_desde"]) for i in (12, 78, 77, 79)} == {20260922}
    assert {por[i]["foto_em"] for i in (34, 12, 78, 77, 79)} == {hoje}
    # a 2ª noite, com o mesmo Fracttal: nenhuma linha muda (nem a que a 1ª limpou), e nada se grava
    antes = _por_id(banco)
    rel = AL.ler_completo(app, ler=RestFalso(ARVORE))
    assert rel["foto"]["gravou"] is False and banco.syncs == 1 and _por_id(banco) == antes
    assert rel["foto"]["descricao_cortada"] == 0 and rel["foto"]["fora_mudaram"] == 0


def test_a_linha_ja_marcada_tambem_perde_o_endereco(app, banco):
    """A foto já renovada (com a marca) que ainda tem uma linha fora do Fracttal com o endereço: a descrição muda, a marca
    fica a de antes e o `foto_em` vai para hoje (a linha mudou)."""
    _semear(banco, [
        ["1", "CAL", "Cliente Alfa", None, None, "2026-10-01", "1", None, None],
        ["10", "CAL-GAM100", GAMA, "1", "USINA", "2026-10-01", "1", "7", None],
        ["66", "CAL-GAM100-INVR6.6", "Inversor 6.6  Zona Rural km 4", "10", "INVR", "2026-10-01", "2", None, "20261001"],
    ], colunas=9)
    AC.trocar(AC.montar_registros(_rpc()), "rpc", lido_em=time.time() - 7200)
    rel = AL.ler_completo(app, ler=RestFalso(ARVORE))
    l = _por_id(banco)[66]
    hoje = datetime.now(_BRT).date().isoformat()
    assert (l["descricao"], l["fora_do_fracttal_desde"], l["foto_em"]) == ("Inversor 6.6", "20261001", hoje)
    assert rel["foto"]["fora_mudaram"] == 1 and rel["foto"]["sairam"] == 0


# ── furo 2: o detector de endereço, só para o banco ─────────────────────────────────────────────────────────────────────
# a usina fora de "Cliente - Usina - UF" com o endereço depois de UM espaço, o nível de dentro com o mesmo endereço, o nível
# com endereço próprio e o item que é só endereço
SEM_PADRAO = [
    _it(40, "CAL-ZET100", "Cliente Alfa - Usina Delta Rua Sem Padrao 12    { CAL-ZET100 }", 1, 1),
    _it(41, "CAL-ZET100-CABN1", "Cabine 1 Rua Sem Padrao 12    { CAL-ZET100-CABN1 }", 40),
    _it(42, "CAL-ZET100-INVR1.2", "Inversor 1.2 Marca X Rua Outra 55    { CAL-ZET100-INVR1.2 }", 41),
    _it(43, "CAL-ZET100-PORT1", "Rua Sem Padrao 12    { CAL-ZET100-PORT1 }", 40),
]


def test_o_detector_corta_o_endereco_fora_do_padrao(app, banco):
    itens = ARVORE + SEM_PADRAO
    _catalogo_de(itens)
    rel = AL.ler_completo(app, ler=RestFalso(itens))
    assert rel["foto"]["gravou"]
    por = _por_id(banco)
    assert (por[40]["descricao"], por[41]["descricao"], por[42]["descricao"]) == (
        "Cliente Alfa - Usina Delta", "Cabine 1", "Inversor 1.2 Marca X")
    assert por[43]["descricao"] is None                                 # só endereço: a linha vai sem descrição
    assert por[10]["descricao"] == GAMA and por[30]["descricao"] == "Inversor 1.1 Marca X"     # o que não tem, não muda


def test_o_caminho_do_catalogo_nao_passa_pelo_detector(app, banco):
    """O detector vale SÓ para a foto: o caminho do catálogo (o que a tela e o `montar_registros` usam) segue o da 2.1, com o
    nome da usina como o caminho o monta, e a paridade com o RPC fica igual."""
    itens = ARVORE + SEM_PADRAO
    _catalogo_de(itens)
    AL.ler_completo(app, ler=RestFalso(itens))
    cat = AC.atual()
    assert cat.fonte == "rest"
    nos = {i["id"]: (i["id_parent"], i["description"]) for i in itens}
    caminhos = AF.caminhos(nos)
    assert {r["id"]: r["parent_description"] for r in cat.lista} == {
        i: c for i, c in caminhos.items() if i in cat.por_id}
    assert cat.por_id[41]["usina"] == "Cliente Alfa - Usina Delta Rua Sem Padrao 12"
    # a paridade com o RPC (o caminho que o Fracttal dá) segue inteira na árvore de sempre: o mesmo caminho, o mesmo cliente
    # e a mesma usina
    rpc = {r["id"]: r["parent_description"] for r in _rpc()}
    assert all(cat.por_id[i]["parent_description"] == c for i, c in rpc.items())
    ref = {r["code"]: r for r in AC.montar_registros(_rpc())}
    vale, _motivo, pct = AL.conferir_paridade([r for r in cat.lista if r["code"] in ref], ref)
    assert vale and pct == 100.0


def test_os_marcadores_do_detector():
    casos = {
        "Cliente Alfa - Usina Delta Rua Sem Padrao 12": "Cliente Alfa - Usina Delta",
        "Cabine 1 Rua Sem Padrao 12": "Cabine 1",
        "Inversor 1.2 Marca X Rua Outra 55": "Inversor 1.2 Marca X",
        "Cabine 2 - Av. Beta, 100": "Cabine 2",
        "Cabine 3, Avenida Beta 100": "Cabine 3",
        "Skid 3 (Rod. Alfa km 12)": "Skid 3",
        "Skid 4 RODOVIA Alfa": "Skid 4",
        "Estação 1 BR-163 km 25": "Estação 1",
        "Estação 2 Estrada Vicinal": "Estação 2",
        "Inversor 3.1 KM 12": "Inversor 3.1",
        "Cabine 4 cep 78000-000": "Cabine 4",
        "Sala de O&M Fazenda Alfa": "Sala de O&M",
        "Sala 2 SÍTIO Beta": "Sala 2",
        "Sala 3 Sitio Beta": "Sala 3",
        "Sala 4 Chácara Gama": "Sala 4",
        "Sala 5 chacara Gama": "Sala 5",
        "Galpão 1 Gleba 7": "Galpão 1",
        "Galpão 2 zona  rural": "Galpão 2",
        # o S/N saiu (item 0 da 3.1+3.2): em equipamento é número de série, e o endereço que o tem já cai pela rua
        "Portaria S/N": "Portaria S/N",
        "Rua Sem Padrao 12": None,                                     # só endereço: sem descrição
        # palavra inteira: o marcador dentro de outra palavra não corta; a sigla de rodovia é em maiúsculas
        "Inversor 2.1 Kmx": "Inversor 2.1 Kmx",
        "Inversor 2.2 Estradas": "Inversor 2.2 Estradas",
        "Inversor SG-1250HX": "Inversor SG-1250HX",
        "Inversor 2.3 br-163": "Inversor 2.3 br-163",
        "Inversor 1.1 Marca X": "Inversor 1.1 Marca X",
        None: None,
    }
    for texto, esperado in casos.items():
        assert FA.sem_endereco(texto)[0] == esperado, texto
        assert FA.sem_endereco(texto)[1] == (esperado != (texto.strip() if texto else None)), texto
    # cortado uma vez, não corta mais (a 2ª noite parte do que a 1ª gravou)
    assert all(FA.sem_endereco(e)[0] == e for e in casos.values() if e)


def test_os_marcadores_do_item_0():
    """Item 0 da 3.1+3.2 (a re-revisão das rodadas 2 e 3 da 2.2): o detector dava falso positivo em código de modelo e em
    número de série, e não conhecia as abreviações que o dado real usa (as do `os_web/ativo_curto.ENDERECO`). Exemplos
    inventados."""
    passam = (
        "Disjuntor DW-125",                          # a sigla de rodovia só com a UF (ou o BR) e 3 dígitos
        "Camera CF-22 PTZ",
        "Inversor 1.2 Marca SG-250 Rev B",
        "Medidor ION 8650 S/N 123456",               # S/N é número de série
        "Inversor 3.3 Lote 2",                       # "Lote" sozinho não é endereço
        "Cabine Zona 1",                             # nem "Zona" sozinha
        "Inversor 4.1 MT-99",                        # a UF com 2 dígitos não é rodovia
        "Inversor 4.2 MT-9999",                      # nem com 4
        "Inversor 4.3 mt-999",                       # nem em minúscula
        "Inversor 4.4 XX-999",                       # nem a sigla que não é UF
        "Relé R.1",                                  # o "R." colado num número é numeração, não rua
        "Inversor 5.1 Brasil 2",
    )
    for texto in passam:
        assert FA.sem_endereco(texto) == (texto, False), texto
    cortados = {
        "Cabine 2 Faz. Ômega": "Cabine 2",
        "Trafo 1 BR 999 km 3": "Trafo 1",
        "Skid 1 MT-999": "Skid 1",
        "Skid 2 BR-999": "Skid 2",
        "Skid 3 SP-123 km 4": "Skid 3",
        "Sala 1 FZ. Alfa Verde": "Sala 1",
        "Sala 2 fz. Alfa": "Sala 2",
        "Sala 3 Estr. Beta": "Sala 3",
        "Sala 4 R. Gama 12": "Sala 4",
        "Sala 5 Povoado Delta": "Sala 5",
        "Sala 6 bairro Delta": "Sala 6",
        "Sala 7 Distrito de Delta": "Sala 7",
        "Sala 8 LOCALIDADE Delta": "Sala 8",
        "Sala 9 Comunidade Delta": "Sala 9",
        "Sala 10 Loteamento Delta": "Sala 10",
        "Galpão 3 Zona Rural": "Galpão 3",            # "Zona Rural" continua
    }
    for texto, esperado in cortados.items():
        assert FA.sem_endereco(texto) == (esperado, True), texto
    assert "S/N" not in FA.MARCADORES_DE_ENDERECO and "Lote" not in FA.MARCADORES_DE_ENDERECO
    assert "Zona" not in FA.MARCADORES_DE_ENDERECO and "Zona Rural" in FA.MARCADORES_DE_ENDERECO


# ── a contagem das descrições cortadas ──────────────────────────────────────────────────────────────────────────────────
def test_a_noite_conta_as_descricoes_cortadas_sem_o_texto(app, banco):
    mais = [_it(44, "CAL-ZET100-PORT2", "Portaria 2 Rua Sem Padrao 12    { x }", 40),
            _it(45, "CAL-ZET100-PORT3", "Portaria 3 Rua Sem Padrao 12    { x }", 40)]
    itens = ARVORE + SEM_PADRAO + mais
    _catalogo_de(itens)
    AC.ligar_leitor(estado=AL.estado)                                  # o Raio-X do catálogo lê o estado do leitor
    rel = AL.ler_completo(app, ler=RestFalso(itens))
    assert rel["foto"]["descricao_cortada"] == 6 and rel["foto"]["descricao_cortada_exemplos"] == [40, 41, 42, 43, 44]
    estado = AL.estado()
    assert {k: estado["descricao_cortada"][k] for k in ("n", "exemplos")} == {"n": 6, "exemplos": [40, 41, 42, 43, 44]}
    texto = json.dumps(estado, ensure_ascii=False, default=str)
    assert not any(e in texto for e in ("Sem Padrao", "Outra 55", "Rua "))          # nunca o texto cortado
    assert AC.estado()["leitor"]["descricao_cortada"]["n"] == 6                     # e o Raio-X do catálogo vê


def test_as_cortadas_sobrevivem_ao_reinicio_e_vao_ao_log(app, banco, tmp_path, caplog):
    """Item 0 da 3.1+3.2 (b): o Levi não tem acesso ao servidor, e a 1ª noite do leitor só se confere pela tela. As cortadas
    vão ao `ativos_estado.json` (sobrevivem ao deploy, que acontece várias vezes por dia) e a uma linha de log no fim da
    noite, só com contagens e ids."""
    pasta = str(tmp_path / "oscreator")
    AC.reiniciar(pasta=pasta)
    itens = ARVORE + SEM_PADRAO
    _catalogo_de(itens)
    with caplog.at_level("INFO", logger="oscreator.ativos_leitor"):
        rel = AL.ler_completo(app, ler=RestFalso(itens))
    assert rel["foto"]["descricao_cortada"] == 4
    linha = [r.getMessage() for r in caplog.records if "a foto da noite" in r.getMessage()]
    assert len(linha) == 1 and "4 descrições cortadas" in linha[0] and "40, 41, 42, 43" in linha[0]
    assert "linhas" in linha[0] and "mudaram" in linha[0] and "saíram" in linha[0]
    assert not any(e in linha[0] for e in ("Sem Padrao", "Outra 55", "Rua ", "Inversor", "Cabine"))
    em = AC.estado()["descricao_cortada"]["em"]
    AC.reiniciar(pasta=pasta)                                          # o reinício (um deploy)
    AL.reiniciar()
    depois = AC.estado()["descricao_cortada"]
    assert depois == {"n": 4, "exemplos": [40, 41, 42, 43], "em": em}
    assert AL.estado()["descricao_cortada"] == depois                  # o estado do leitor também a vê de novo
    with open(tmp_path / "oscreator" / "ativos_estado.json", encoding="utf-8") as f:
        assert not any(e in f.read() for e in ("Sem Padrao", "Outra 55"))


# ── a usina que fechou no padrão não passa pelo detector (Ruling AQ, revisão 3) ─────────────────────────────────────────
# usina rural com "Fazenda", "Sítio" ou "Chácara" no nome é comum na carteira: o corte na sigla do estado já fecha o nome, e o
# detector o cortaria no "Fazenda". O nível de dentro com o nome da fazenda, sob uma usina de outra cauda, segue cortado
FAZENDAS = [
    _it(50, "CAL-FOM100", "CL - UFV Fazenda Ômega - MT  Rodovia MT-010 km 5    { CAL-FOM100 }", 1, 1),
    _it(51, "CAL-FOM100-CABN1", "Cabine 1 Fazenda Ômega    { CAL-FOM100-CABN1 }", 50),
    _it(52, "CAL-FAL100", "CL - UFV Fazenda Alfa - MT  Estrada Vicinal km 3    { CAL-FAL100 }", 1, 1),
    _it(53, "CAL-FAL100-INVR1.1", "Inversor 1.1    { CAL-FAL100-INVR1.1 }", 52),
    _it(54, "CAL-FBE100", "CL - UFV Fazenda Beta - MT  Estrada Vicinal km 7    { CAL-FBE100 }", 1, 1),
    _it(55, "CAL-FBE100-INVR1.1", "Inversor 1.1    { CAL-FBE100-INVR1.1 }", 54),
]


def test_a_usina_que_fechou_no_padrao_nao_passa_pelo_detector(app, banco):
    # a foto de 11/10 (a de 22/09 e os códigos de junho) com uma usina de fazenda que saiu do Fracttal: a isenção vale também
    # para a linha que saiu
    _semear(banco, [FOTO_DE_11_10[0],
                    ["56", "CAL-FVE100", "CL - UFV Fazenda Velha - MT  Estrada Vicinal km 9", "1", "USINA", "2026-06-21"]])
    itens = ARVORE + SEM_PADRAO + FAZENDAS
    _catalogo_de(itens)
    rel = AL.ler_completo(app, ler=RestFalso(itens))
    assert rel["foto"]["gravou"]
    por = _por_id(banco)
    assert (por[50]["descricao"], por[52]["descricao"], por[54]["descricao"]) == (
        "CL - UFV Fazenda Ômega - MT", "CL - UFV Fazenda Alfa - MT", "CL - UFV Fazenda Beta - MT")
    assert por[56]["descricao"] == "CL - UFV Fazenda Velha - MT" and por[56]["fora_do_fracttal_desde"] == "20260922"
    # o resto segue pelo detector: o nível de dentro com o nome da fazenda e a usina fora do padrão
    assert por[51]["descricao"] == "Cabine 1" and por[40]["descricao"] == "Cliente Alfa - Usina Delta"
    assert rel["foto"]["descricao_cortada_exemplos"] == [40, 41, 42, 43, 51] and rel["foto"]["descricao_cortada"] == 5
    # e a 2ª noite não muda nada
    rel = AL.ler_completo(app, ler=RestFalso(itens))
    assert rel["foto"]["gravou"] is False and _por_id(banco)[56]["descricao"] == "CL - UFV Fazenda Velha - MT"


def test_a_foto_como_catalogo_mantem_as_usinas_da_fazenda_separadas(app, banco):
    """A foto servindo de catálogo (a máquina sem cópia nenhuma) monta a usina pelo nome dela na foto: cortado no "Fazenda",
    as duas usinas virariam "CL - UFV" e se juntariam na cascata."""
    itens = ARVORE + FAZENDAS
    _catalogo_de(itens)
    AL.ler_completo(app, ler=RestFalso(itens))
    registros, _ = AC.registros_da_foto(banco.linhas(eq.LIVRO_FOTO, eq.ABA_FOTO))
    usina = {r["code"]: r["usina"] for r in registros}
    assert (usina["CAL-FAL100-INVR1.1"], usina["CAL-FBE100-INVR1.1"]) == ("CL - UFV Fazenda Alfa - MT",
                                                                          "CL - UFV Fazenda Beta - MT")
    assert usina == {r["code"]: r["usina"] for r in AC.atual().lista}
