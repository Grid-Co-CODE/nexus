"""Os textos reservados (19/11/2026): o que não pode morar num repositório público mora cifrado no banco do Nexus.

Levi, 19/11/2026: "Tirar os dados do repositório e levar para o banco do Nexus" e, no mesmo dia, "Eu não aceito só censurar
e aí quem tiver no Nexus vê as coisas incompletas, não. Tem que estar no banco do Nexus e aí quem tiver um acesso do Nexus
vai ter a informação completa". O arquivo versionado guarda uma FICHA no lugar do texto; o livro
`nexus_textos_reservados · dim_texto_reservado` guarda o texto cifrado; a rota com login devolve o texto no lugar da ficha.

Tudo aqui é inventado: nenhum teste lê o banco de verdade."""
import base64
import json

import pytest
from pg_falso import ApiPGFalsa

from nexus.cadastro.cifra import Cofre
from nexus.dados import catalogo
from nexus.dados import textos_reservados as TR

CHAVE = base64.urlsafe_b64encode(b"t" * 32).decode()
BASE = "http://banco.exemplo.test"
RADAR, CANAL = "zeladoria_radar", "oscreator_canal"


def _pub(api, area, textos):
    return TR.publicar(area, textos, base=BASE, sessao=api, token="tk", cofre=Cofre(CHAVE))


def test_o_livro_esta_no_catalogo_antes_da_1a_gravacao_e_so_cresce():
    l = catalogo.LIVRO_POR_NOME[TR.LIVRO]
    assert TR.LIVRO == "nexus_textos_reservados" and l.abas == (TR.ABA,) == ("dim_texto_reservado",)
    assert l.so_cresce == (TR.ABA,) and catalogo.aba_segue_a_regra(TR.ABA)
    assert set(TR.AREAS) == {RADAR, CANAL}


def test_publica_cifrado_e_le_de_volta_o_texto_inteiro():
    api = ApiPGFalsa()
    r = _pub(api, RADAR, {"Zlfornecedor01": "Fornecedor Alfa", "ZLVALOR01": "R$ 1.234,56 em 3 parcelas"})
    assert r == {"antes": 0, "depois": 2, "novos": ["ZLVALOR01", "Zlfornecedor01"], "mudados": [], "iguais": []}
    linhas = api.linhas(TR.LIVRO, TR.ABA)
    bruto = json.dumps(linhas, ensure_ascii=False)
    # a API do banco tem leitura aberta: em claro só a área e a ficha, nunca o texto
    assert "Alfa" not in bruto and "1.234,56" not in bruto
    assert all(str(l["texto_cifrado"]).startswith("cf1:") and l["texto_id"] == f"{l['area']}/{l['chave']}" for l in linhas)
    assert TR.abrir(linhas, Cofre(CHAVE), RADAR) == {"Zlfornecedor01": "Fornecedor Alfa",
                                                     "ZLVALOR01": "R$ 1.234,56 em 3 parcelas"}
    # a cifra é presa à ficha: copiada para outra linha, não abre
    trocada = [dict(linhas[0], chave="Zloutra01", texto_id=f"{RADAR}/Zloutra01")]
    assert TR.abrir(trocada, Cofre(CHAVE), RADAR) == {}


def test_publicar_de_novo_soma_muda_so_o_que_mudou_e_nao_mexe_na_outra_area():
    api = ApiPGFalsa()
    _pub(api, RADAR, {"Zlfornecedor01": "Fornecedor Alfa", "ZLVALOR01": "R$ 10"})
    _pub(api, CANAL, {"Marca Um": "E-mail suporte@marca-um.exemplo.test"})
    antes = {l["texto_id"]: l["texto_cifrado"] for l in api.linhas(TR.LIVRO, TR.ABA)}
    r = _pub(api, RADAR, {"ZLVALOR01": "R$ 20", "Zlcliente01": "Cliente Beta"})
    assert (r["antes"], r["depois"], r["novos"], r["mudados"], r["iguais"]) == (3, 4, ["Zlcliente01"], ["ZLVALOR01"], [])
    depois = {l["texto_id"]: l["texto_cifrado"] for l in api.linhas(TR.LIVRO, TR.ABA)}
    # a ficha que não veio nesta publicação fica (o livro só cresce), com a MESMA cifra; a outra área, idem
    assert depois[f"{RADAR}/Zlfornecedor01"] == antes[f"{RADAR}/Zlfornecedor01"]
    assert depois[f"{CANAL}/Marca Um"] == antes[f"{CANAL}/Marca Um"]
    linhas = api.linhas(TR.LIVRO, TR.ABA)
    assert TR.abrir(linhas, Cofre(CHAVE), RADAR) == {"Zlfornecedor01": "Fornecedor Alfa", "ZLVALOR01": "R$ 20",
                                                     "Zlcliente01": "Cliente Beta"}
    assert TR.abrir(linhas, Cofre(CHAVE), CANAL) == {"Marca Um": "E-mail suporte@marca-um.exemplo.test"}
    # publicar o mesmo texto de novo não regrava a linha
    assert _pub(api, RADAR, {"ZLVALOR01": "R$ 20"})["iguais"] == ["ZLVALOR01"]


@pytest.mark.parametrize("area, textos", [("outra_area", {"Zlx01": "a"}), (RADAR, {}), (RADAR, {"": "a"}),
                                          (RADAR, {"Zlx01": ""}), (RADAR, {"Zlx01": None})])
def test_publicar_recusa_o_que_nao_faz_sentido_sem_gravar_nada(area, textos):
    api = ApiPGFalsa()
    with pytest.raises(TR.Recusada):
        _pub(api, area, textos)
    assert api.syncs == 0


ORIGINAL = ("var a = 'Fornecedor Alfa'; /* o Fornecedor Alfa cobra R$ 9,99 por módulo */\n"
            "if (/fornecedor ?alfa/i.test(x)) temAlfaco = pago_alfaco + 1; var cor = '#2CAA2C'; // cliente 2C\n")
TERMOS = [{"ficha": "ZLVALOR01", "texto": "R$ 9,99", "vezes": 1},
          {"ficha": "Zlfornecedor01", "texto": "Fornecedor Alfa", "vezes": 2},
          {"ficha": "zlfornecedor02", "texto": "fornecedor ?alfa", "vezes": 1},
          {"ficha": "Zlcliente01", "texto": "Alfaco", "vezes": 1}, {"ficha": "zlcliente01", "texto": "alfaco", "vezes": 1},
          # o texto curto que também aparece onde não é o dado (a cor): só no contexto dito
          {"ficha": "Zlcliente02", "texto": "2C", "onde": ["// cliente 2C"]}]


def test_reservar_poe_a_ficha_e_restaurar_devolve_o_arquivo_identico():
    reservado, fichas = TR.reservar(ORIGINAL, TERMOS)
    assert "Alfa" not in reservado and "9,99" not in reservado and "alfa" not in reservado
    assert "'#2CAA2C'" in reservado and "// cliente Zlcliente02" in reservado      # a cor ficou; o cliente, não
    assert "temZlcliente01 = pago_zlcliente01 + 1" in reservado                    # a ficha vale dentro de um nome do JS
    assert fichas["Zlcliente02"] == "2C" and len(fichas) == 6
    assert TR.restaurar(reservado, fichas) == ORIGINAL
    assert TR.fichas_em(reservado) == sorted(fichas) and TR.fichas_em(ORIGINAL) == []


@pytest.mark.parametrize("termos, motivo", [
    ([{"ficha": "ZLVALOR01", "texto": "R$ 9,99", "vezes": 2}], "vezes"),                       # a contagem não bate
    ([{"ficha": "ZLVALOR01", "texto": "não está no arquivo"}], "não aparece"),
    ([{"ficha": "valor1", "texto": "R$ 9,99"}], "ficha"),                                       # ficha fora do formato
    ([{"ficha": "ZLVALOR01", "texto": "R$ 9,99"}, {"ficha": "ZLVALOR01", "texto": "Fornecedor Alfa"}], "repetida"),
    ([{"ficha": "Zlcliente02", "texto": "2C", "onde": ["// cliente 3C"]}], "contexto"),
])
def test_reservar_para_sem_devolver_nada_quando_um_termo_nao_casa(termos, motivo):
    with pytest.raises(TR.Recusada) as e:
        TR.reservar(ORIGINAL, termos)
    assert motivo in str(e.value)
    assert "Alfa" not in str(e.value) and "9,99" not in str(e.value)       # o motivo nunca traz o texto reservado


def test_reservar_recusa_o_arquivo_que_ja_tem_a_ficha_e_restaurar_troca_a_mais_longa_primeiro():
    with pytest.raises(TR.Recusada):
        TR.reservar("ZLVALOR01 já está aqui e R$ 9,99 também", [{"ficha": "ZLVALOR01", "texto": "R$ 9,99"}])
    assert TR.restaurar("Zlab01 e Zlab01x", {"Zlab01": "curta", "Zlab01x": "longa"}) == "curta e longa"


# ── a leitura dentro do Nexus ────────────────────────────────────────────────────────────────────────────────────────
def test_ler_no_nexus_abre_a_area_guarda_cinco_minutos_e_fica_com_a_ultima_boa(app):
    api = ApiPGFalsa()
    _pub(api, RADAR, {"Zlfornecedor01": "Fornecedor Alfa"})
    app.extensions["nexus_dados_sessao"] = api
    app.config.update(NEXUS_CHAVE_CADASTRO=CHAVE, GRIDCO_DB_API=BASE)
    with app.app_context():
        r = TR.ler(RADAR)
        assert r["textos"] == {"Zlfornecedor01": "Fornecedor Alfa"} and r["erro"] == "" and r["ja_leu"]
        paginas = api.paginas_lidas
        assert TR.ler(RADAR)["textos"] == r["textos"] and api.paginas_lidas == paginas       # a cópia de 5 minutos
        # o banco cai: a leitura forçada devolve a última boa, com o erro
        app.extensions["nexus_dados_sessao"] = None
        r2 = TR.ler(RADAR, forcar=True)
        assert r2["textos"] == {"Zlfornecedor01": "Fornecedor Alfa"} and r2["erro"] and r2["ja_leu"]


def test_ler_sem_banco_ou_sem_a_chave_diz_o_erro_e_nao_inventa_texto(app):
    with app.app_context():
        r = TR.ler(RADAR)                                  # o teste sem sessão do banco
        assert r["textos"] == {} and r["erro"] and not r["ja_leu"]
    api = ApiPGFalsa()
    _pub(api, RADAR, {"Zlfornecedor01": "Fornecedor Alfa"})
    app.extensions["nexus_dados_sessao"] = api
    app.config.update(GRIDCO_DB_API=BASE)
    app.config.pop("NEXUS_CHAVE_CADASTRO", None)
    with app.app_context():
        r = TR.ler(RADAR, forcar=True)
        assert r["textos"] == {} and "NEXUS_CHAVE_CADASTRO" in r["erro"]
