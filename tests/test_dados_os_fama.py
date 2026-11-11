"""As OS do cliente pela FAMA (11/11/2026, fase 1: sombra): o fato `nexus_os_fama · fato_os_fama`, a dimensão
`dim_projeto_fama`, o leitor da FAMA e a carga de hora em hora. Uma FAMA de mentira e a `ApiPGFalsa` no lugar do banco:
nenhum teste vai à rede. Projetos, usinas, textos e pessoas inventados."""
import json
import logging
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pg_falso import ApiPGFalsa

from nexus.cadastro.cifra import CifraErro, Cofre, gerar_chave
from nexus.dados import carga, catalogo, explica, fama, radar
from nexus.dados import fato_os_fama as F
from nexus.dados.fato_ronda import GraoDuplicado
from nexus.dados.fatos import CAB_QUALIDADE

BASE = "http://pg.falso"
BRT = timezone(timedelta(hours=-3))
AGORA = datetime(2026, 11, 11, 15, 40, tzinfo=BRT)
CHAVE_FAMA = "chave-da-fama-de-teste-XYZ123"
# o que NUNCA pode aparecer em linha nenhuma do banco (texto livre do cliente e pessoa)
TITULO, DESCRICAO = "Troca do fusível da string 3", "O cliente viu a string parada no portal e pediu urgência"
PESSOAS = ("Fulana Criadora", "fulana.criadora@exemplo.com", "Beltrano Responsável", "beltrano@exemplo.com",
           "Sicrana Aprovadora", "sicrana@exemplo.com", "Parceira Fictícia Ltda")


def _os(i, projeto=10, nome="Lagoa Fictícia II", status=("executed", 7), tipo=("Corrective", 1), sev=("Routine", 3),
        esp=("Elétrica", 2), equipe=("Operação e manutenção", 1), criada="2026-10-01T13:00:00",
        prevista="2026-10-05", fim="2026-10-06T18:30:00", titulo=TITULO, descricao=DESCRICAO):
    """Um item da lista da FAMA, com todos os campos medidos em 11/11/2026, inclusive os que NÃO podem ir ao banco."""
    return {"id": i, "title": titulo, "description": descricao, "status_id": status[1], "contract_id": 77,
            "creation_date": criada, "finish_date": fim, "expected_execution_date": prevista,
            "start_execution_date": None,
            "status": {"id": status[1], "service_status": status[0]},
            "type": {"id": tipo[1], "service_type": tipo[0]},
            "severity": {"id": sev[1], "service_severity": sev[0]},
            "specialty": {"id": esp[1], "specialty": esp[0]} if esp else None,
            "management_team_type": {"id": equipe[1], "name": equipe[0]},
            "project": {"id": projeto, "name": nome} if projeto is not None else None,
            "creator": {"name": PESSOAS[0], "email": PESSOAS[1]},
            "responsible": {"name": PESSOAS[2], "email": PESSOAS[3]},
            "approver": {"name": PESSOAS[4], "email": PESSOAS[5]},
            "partner_company": {"id": 3, "name": PESSOAS[6]}}


def _cofre():
    return Cofre(gerar_chave())


def _por_os(linhas):
    return {l[0]: dict(zip(F.CAB_OS_FAMA, l)) for l in linhas}


def _montar(itens, ligacao=None, cofre=None, anteriores=None):
    por_os, rel = F.validas(itens)
    linhas, rl = F.linhas(por_os, ligacao or {}, cofre or _cofre(), anteriores)
    return linhas, dict(rel, **rl), por_os


# ── o fato, puro ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_uma_linha_por_os_com_os_ids_as_datas_de_brasilia_e_o_catalogo_da_fama():
    itens = [_os(501), _os(501),                                            # a mesma OS duas vezes na lista
             _os(502, projeto=11, nome="Morro Inventado IV", status=("under execution", 4), tipo=("Modules cleaning", 4),
                 sev=("Critical", 1), esp=None, criada="2026-11-02T01:30:00Z", prevista=None, fim=None),
             {"title": "sem id"}, "não é objeto"]
    linhas, rel, _ = _montar(itens, ligacao={10: 37})
    d = _por_os(linhas)
    assert list(d) == [501, 502]
    assert (rel["lidas"], rel["repetidas"], rel["sem_id"]) == (5, 1, 2)
    um = d[501]
    assert {k: um[k] for k in F.CAB_OS_FAMA if not k.endswith(("_cifrado", "_cifrada"))} == {
        "fama_os_id": 501, "fama_projeto_id": 10, "usina_id": 37, "usina_ligada_por": F.LIGADA_POR,
        "data_id_criacao": 20261001, "data_id_prevista": 20261005, "data_id_fim": 20261006,
        "fama_status_id": 7, "status": "executed", "fama_tipo_id": 1, "tipo": "Corrective",
        "fama_severidade_id": 3, "severidade": "Routine", "fama_especialidade_id": 2, "especialidade": "Elétrica",
        "fama_tipo_equipe_id": 1, "tipo_equipe": "Operação e manutenção", "contract_id": 77, "dias_ate_fim_qtd": 5}
    dois = d[502]
    # 01:30Z de 02/11 é 22:30 de 01/11 em Brasília (regra 7: o dia é o de Brasília); sem projeto ligado, sem usina
    assert (dois["data_id_criacao"], dois["data_id_prevista"], dois["data_id_fim"], dois["dias_ate_fim_qtd"]) == (
        20261101, None, None, None)
    assert (dois["usina_id"], dois["usina_ligada_por"], dois["status"], dois["especialidade"]) == (
        None, None, "under execution", None)
    F.conferir_grao(linhas)


def test_as_datas_sem_fuso_a_meia_noite_e_o_dia_so():
    """A FAMA pode mandar a data com fuso, sem fuso ou só o dia (medido só em contagens): com fuso, o dia de Brasília;
    sem fuso, UTC como o resto do Nexus; a meia-noite exata sem fuso é o dia escolhido num calendário (não vira o dia
    anterior); o dia só, ele mesmo. A qualidade conta cada jeito."""
    itens = [_os(1, criada="2026-10-01T02:00:00", prevista="2026-10-05T00:00:00", fim="2026-10-06"),
             _os(2, criada="2026-10-01T02:00:00-03:00", prevista="não é data", fim="2026-10-06T00:00:00+00:00")]
    linhas, rel, _ = _montar(itens)
    d = _por_os(linhas)
    assert (d[1]["data_id_criacao"], d[1]["data_id_prevista"], d[1]["data_id_fim"]) == (20260930, 20261005, 20261006)
    assert (d[2]["data_id_criacao"], d[2]["data_id_prevista"], d[2]["data_id_fim"]) == (20261001, None, 20261005)
    assert rel["datas"] == {"sem_fuso": 1, "meia_noite": 1, "dia": 1, "com_fuso": 2, "invalida": 1}
    # o fim antes da criação não vira medida negativa: fica vazio e conta
    linhas, rel, _ = _montar([_os(3, criada="2026-10-09T12:00:00", fim="2026-10-02T12:00:00")])
    assert _por_os(linhas)[3]["dias_ate_fim_qtd"] is None and rel["fim_antes_da_criacao"] == 1


def test_o_dominio_da_fama_e_o_que_fica_fora_dele():
    itens = [_os(1, status=("Under  Execution", 4)), _os(2, status=("arquivada", 99), tipo=("Tipo novo", 9),
                                                          sev=("Altíssima", 8))]
    linhas, rel, _ = _montar(itens)
    d = _por_os(linhas)
    assert d[1]["status"] == "under execution"                      # caixa e espaço não fazem outro valor
    # fora do domínio medido em 11/11/2026: o nome fica vazio e conta (regra 4); o id da FAMA fica
    assert (d[2]["fama_status_id"], d[2]["status"], d[2]["tipo"], d[2]["severidade"]) == (99, None, None, None)
    assert rel["fora_do_dominio"] == {"status": 1, "tipo": 1, "severidade": 1}


def test_nenhum_texto_livre_nem_pessoa_em_claro_em_linha_nenhuma():
    linhas, _rel, por_os = _montar([_os(1), _os(2, projeto=11, nome="Morro Inventado IV")], ligacao={10: 37})
    dim = F.dim_projetos(por_os, [])
    texto = json.dumps([linhas, dim], ensure_ascii=False, default=str)
    for proibido in (TITULO, DESCRICAO, "fusível", "portal", *PESSOAS, "exemplo.com"):
        assert proibido not in texto, proibido
    # o nome da usina (o projeto) pode ir em claro: é o que a dimensão guarda
    assert dim == [[10, "Lagoa Fictícia II", 1], [11, "Morro Inventado IV", 1]]
    # o cabeçalho também não tem coluna de pessoa nem de texto em claro
    assert not [c for c in F.CAB_OS_FAMA if c.split("_")[0] in ("creator", "responsible", "approver", "partner",
                                                                 "title", "description", "nome", "email")]


def test_titulo_e_descricao_so_cifrados_amarrados_a_linha_e_a_cifra_fica_se_o_texto_nao_mudou():
    cofre = _cofre()
    linhas, rel, _ = _montar([_os(1), _os(2, titulo="", descricao=None)], cofre=cofre)
    d = _por_os(linhas)
    assert Cofre.eh_cifrado(d[1]["titulo_cifrado"]) and Cofre.eh_cifrado(d[1]["descricao_cifrada"])
    assert F.textos(cofre, d[1]) == {"titulo": TITULO, "descricao": DESCRICAO}
    assert (d[2]["titulo_cifrado"], d[2]["descricao_cifrada"]) == (None, None)
    # amarrada à linha: a cifra da OS 1 posta na linha da OS 2 não abre
    with pytest.raises(CifraErro):
        cofre.decifrar(d[1]["titulo_cifrado"], F.contexto(2, "titulo"))
    # a carga seguinte com o mesmo texto reaproveita a cifra (o nonce é aleatório e a API guarda o histórico de cada
    # linha que muda: sem isso, toda hora as 4.749 linhas mudariam); texto novo, cifra nova
    anteriores = {1: d[1]}
    de_novo, rel2, _ = _montar([_os(1), _os(2)], cofre=cofre, anteriores=anteriores)
    assert _por_os(de_novo)[1]["titulo_cifrado"] == d[1]["titulo_cifrado"]
    assert rel2["cifras"]["mantidas"] == 2 and rel2["cifras"]["novas"] == 2
    mudou, _r, _ = _montar([_os(1, titulo="Outro título")], cofre=cofre, anteriores=anteriores)
    assert _por_os(mudou)[1]["titulo_cifrado"] != d[1]["titulo_cifrado"]
    assert F.textos(cofre, _por_os(mudou)[1])["titulo"] == "Outro título"


def test_a_usina_so_pela_ligacao_decidida_na_tela():
    de_para = [
        {"usina_id": "37", "sistema": F.SISTEMA, "chave_externa": "10", "casou_por": "manual (11/11)"},
        {"usina_id": 38, "sistema": F.SISTEMA, "chave_externa": 11.0, "casou_por": "nome"},          # não decidida
        {"usina_id": None, "sistema": F.SISTEMA, "chave_externa": "12", "casou_por": "a decidir na tela"},
        {"usina_id": 40, "sistema": "Fracttal · Classificação 1", "chave_externa": "13", "casou_por": "manual"},
        {"usina_id": 41, "sistema": F.SISTEMA, "chave_externa": "14", "casou_por": "manual (10/11)"},
        {"usina_id": 42, "sistema": F.SISTEMA, "chave_externa": "14", "casou_por": "manual (11/11)"},  # duas usinas
    ]
    lig, rel = F.ligacao_decidida(de_para)
    assert lig == {10: 37} and rel == {"decididas": 1, "ambiguas": 1}


def test_a_dimensao_guarda_o_projeto_que_sumiu_da_leitura():
    _l, _r, por_os = _montar([_os(1, projeto=10, nome="Lagoa Fictícia II"), _os(2, projeto=10, nome="Lagoa Fictícia II"),
                              _os(3, projeto=11, nome="Morro  Inventado IV")])
    anteriores = [{"fama_projeto_id": "12.0", "nome": "Vale Sumido", "os_qtd": 4},
                  {"fama_projeto_id": 10, "nome": "Nome Antigo", "os_qtd": 1}]
    # o projeto 12 não veio: fica (a ligação decidida dele não se perde), com 0 OS; o 10 leva o nome de agora
    assert F.dim_projetos(por_os, anteriores) == [[10, "Lagoa Fictícia II", 2], [11, "Morro Inventado IV", 1],
                                                  [12, "Vale Sumido", 0]]


def test_o_id_da_fama_aceita_numero_e_texto_de_codigo():
    assert [F.id_fama(v) for v in (10, "10", 10.0, "10.0", " 7 ", 0, -3, None, "", True)] == [
        10, 10, 10, 10, 7, None, None, None, None, None]
    assert F.id_fama("a1b2-c3d4") == "a1b2-c3d4" and F.id_fama("tem espaço") is None


def test_a_qualidade_mede_a_parte_das_os_com_usina():
    itens = [_os(1), _os(2), _os(3, projeto=11, nome="Morro Inventado IV"), _os(4, projeto=None)]
    linhas, rel, por_os = _montar(itens, ligacao={10: 37})
    dim = F.dim_projetos(por_os, [])
    q = dict(zip(CAB_QUALIDADE, F.linha_qualidade(linhas, dim, rel, "2026-11-11T15:40:30-03:00",
                                                  "2026-11-11T15:41:00-03:00", 3)))
    assert (q["fato"], q["linhas"], q["com_usina"], q["pct_usina"], q["com_data"], q["pct_data"]) == (
        "os_fama", 4, 2, 50.0, 4, 100.0)
    assert q["usina_por_de_para"] == 2 and q["origem_atualizada_em"] == "2026-11-11T15:40:30-03:00"
    assert q["sem_usina_exemplos"] == "(sem projeto) (1); Morro Inventado IV (1)"
    ex = json.loads(q["extra"])
    assert (ex["projetos"], ex["projetos_ligados"], ex["sem_projeto"], ex["linhas_na_carga_anterior"]) == (2, 1, 1, 3)


def test_o_grao_quebrado_nao_grava():
    linhas, _r, _ = _montar([_os(1), _os(2)])
    with pytest.raises(GraoDuplicado):
        F.conferir_grao(linhas + [linhas[0]])


# ── o catálogo, o livro e o radar ─────────────────────────────────────────────────────────────────────────────────
def test_o_catalogo_registra_o_fato_e_o_livro_antes_da_1a_gravacao():
    f = catalogo.POR_ID["os_fama"]
    assert (f.estado, f.area, f.tipo, f.chave, f.conformado_em) == (
        "conformado", "pcm", "snapshot_acumulado", ("fama_os_id",), "nexus_os_fama · fato_os_fama")
    assert f.grao == F.GRAO and f.grao.startswith("1 linha = 1 OS da FAMA")
    assert [f.dims[d][0] for d in ("data", "usina", "os", "pessoa")] == ["id", "id", "cod", "nao"]
    lv = catalogo.LIVRO_POR_NOME[F.LIVRO]
    assert lv.abas == (F.ABA, F.ABA_DIM, "qualidade", "atualizacao") and not lv.no_banco
    assert lv.so_cresce == (F.ABA_DIM,)                 # o projeto não some da dimensão; o fato segue a FAMA (95%)
    assert 15 <= len(explica.RESUMO["os_fama"]) <= 70 and explica.PARA_QUE["os_fama"].endswith(".")


def test_o_radar_da_governanca_ve_o_livro_como_fato():
    abas = {(F.LIVRO, a): {"id": 900 + i, "row_count": 3, "visibility": "visible"}
            for i, a in enumerate((F.ABA, F.ABA_DIM, "qualidade", "atualizacao"))}
    c = radar.classificar(abas)
    assert sorted(t["aba"] for t in c["fato"]) == sorted(a for _l, a in abas) and not c["nova"]


# ── o leitor da FAMA e a carga de hora em hora ────────────────────────────────────────────────────────────────────
class RespostaFama:
    def __init__(self, status, corpo):
        self.status_code, self._corpo = status, corpo

    def json(self):
        if isinstance(self._corpo, Exception):
            raise self._corpo
        return self._corpo


class FamaFalsa:
    """A FAMA de mentira: guarda cada pedido (método, endereço, cabeçalhos, timeout) e responde o que o teste mandar."""

    def __init__(self, corpo=None, status=200, erro=None):
        self.corpo, self.status, self.erro, self.pedidos = corpo, status, erro, []

    def get(self, url, headers=None, timeout=None, params=None):
        self.pedidos.append({"metodo": "GET", "url": url, "headers": dict(headers or {}), "timeout": timeout,
                             "params": params})
        if self.erro is not None:
            raise self.erro
        return RespostaFama(self.status, self.corpo)

    def __getattr__(self, nome):                 # post, put, patch, delete: o leitor nunca chama
        raise AssertionError(f"o leitor da FAMA chamou {nome}")


class NadaDeRede:
    """Sessão que falha se alguém a usar: a carga sem as três chaves não fala com o banco nem com a FAMA."""

    def __getattr__(self, nome):
        raise AssertionError(f"chamou {nome} sem as três chaves")


CHAVE_CADASTRO = gerar_chave()          # a mesma em todas as voltas de um teste: a cifra de antes abre


def _config(**k):
    c = {"NEXUS_FAMA_CHAVE": CHAVE_FAMA, "GRIDCO_SQL_TOKEN": "token-de-teste", "NEXUS_CHAVE_CADASTRO": CHAVE_CADASTRO,
         "GRIDCO_DB_API": BASE}
    c.update(k)
    return c


def _semear(api, livro, aba, linhas):
    api.workbooks.setdefault(livro, {"key": livro})
    cab = list(linhas[0]) if linhas else []
    api._id(livro, aba)["linhas"] = [{"headers": cab, "values": [l.get(c) for c in cab]} for l in linhas]


DE_PARA = [{"usina_id": 37, "sistema": F.SISTEMA, "chave_externa": "10", "casou_por": "manual (11/11)"},
           {"usina_id": 5, "sistema": "Fracttal · Classificação 1", "chave_externa": "Cliente Alfa - Outra 1 - RN",
            "casou_por": "nome"}]


@pytest.fixture
def banco():
    api = ApiPGFalsa()
    _semear(api, "cadastro_nexus", "de_para", DE_PARA)
    return api


def _gerar(api, fama_falsa, config=None, **k):
    return fama.gerar_fama(config or _config(), api, fama=fama_falsa, agora=k.pop("agora", AGORA), **k)


def test_o_leitor_so_faz_get_na_rota_com_a_chave_no_cabecalho_e_timeout_de_90_s():
    f = FamaFalsa([_os(1)])
    assert fama.ler(CHAVE_FAMA, f) == [_os(1)]
    assert f.pedidos == [{"metodo": "GET", "url": "https://api.fama.energy/v2/contractor/service-orders/",
                          "headers": {"X-Contractor-Key": CHAVE_FAMA, "Accept": "application/json"}, "timeout": 90,
                          "params": None}]


def test_a_carga_grava_o_livro_inteiro_e_confere(banco):
    f = FamaFalsa([_os(1), _os(2), _os(3, projeto=11, nome="Morro Inventado IV")])
    r = _gerar(banco, f)
    assert r["gravado"] == {F.ABA: 3, F.ABA_DIM: 2, "qualidade": 1, "atualizacao": 1} and r["mudou"] is True
    assert len(f.pedidos) == 1                             # uma leitura só, sem repetir
    fato = {int(l["fama_os_id"]): l for l in banco.linhas(F.LIVRO, F.ABA)}
    assert (fato[1]["usina_id"], fato[3]["usina_id"]) == (37, None)
    q = banco.linhas(F.LIVRO, "qualidade")[0]
    assert (q["fato"], q["linhas"], q["pct_usina"]) == ("os_fama", 3, 66.7)
    at = banco.linhas(F.LIVRO, "atualizacao")[0]
    assert at["linhas"] == 3 and at["sha_linhas"] == r["sha_linhas"]


@pytest.mark.parametrize("fama_falsa", [
    FamaFalsa(status=401, corpo={"detail": "Could not validate credentials"}),
    FamaFalsa(status=500, corpo={"detail": "erro interno"}),
    FamaFalsa(corpo={"rows": [_os(1)]}),                       # resposta que não é lista
    FamaFalsa(corpo=ValueError("não é JSON")),
    FamaFalsa(erro=requests.Timeout("passou de 90 s")),
    FamaFalsa(erro=requests.ConnectionError("sem rede")),
], ids=["401", "500", "objeto", "nao_json", "timeout", "sem_rede"])
def test_erro_401_ou_resposta_que_nao_e_lista_vira_nao_li_e_nada_se_grava(banco, fama_falsa):
    r = _gerar(banco, fama_falsa)
    assert "nao_li" in r and "gravado" not in r
    assert banco.syncs == 0 and F.LIVRO not in banco.workbooks
    assert len(fama_falsa.pedidos) == 1                    # sem repetir em laço: a hora seguinte tenta de novo


def test_a_chave_fica_fora_de_toda_saida(banco, caplog):
    """A chave nunca vai ao relatório, ao log nem à mensagem de erro, nem quando o erro (ou a FAMA) a repete."""
    caplog.set_level(logging.DEBUG)
    # 1ª camada: a mensagem do "não li" é montada no leitor, sem o texto do erro (que pode trazer o pedido)
    with pytest.raises(fama.NaoLi) as e:
        fama.ler(CHAVE_FAMA, FamaFalsa(erro=requests.ConnectionError(f"X-Contractor-Key: {CHAVE_FAMA}")))
    assert CHAVE_FAMA not in str(e.value) and e.value.__cause__ is None and e.value.__suppress_context__
    saidas = []
    for f in (FamaFalsa(erro=requests.ConnectionError(f"falhou com o cabeçalho X-Contractor-Key: {CHAVE_FAMA}")),
              FamaFalsa(status=401, corpo={"detail": f"chave {CHAVE_FAMA} recusada"}),
              FamaFalsa([_os(1), _os(2)])):
        saidas.append(json.dumps(_gerar(banco, f), ensure_ascii=False, default=str))
    # a falha que sobe do meio da carga (o banco que caiu) vai ao log da volta sem a chave
    app = type("App", (), {"config": _config(), "app_context": lambda self: _Contexto()})()
    erro = RuntimeError(f"o banco caiu levando {CHAVE_FAMA}")
    original = fama.gerar_fama
    try:
        fama.gerar_fama = lambda *a, **k: (_ for _ in ()).throw(erro)
        carga._volta_fama(app)
    finally:
        fama.gerar_fama = original
    saidas.append(json.dumps(carga._LACO["fama"], ensure_ascii=False))
    gravado = json.dumps({a: banco.linhas(F.LIVRO, a) for a in (F.ABA, F.ABA_DIM, "qualidade", "atualizacao")},
                         ensure_ascii=False, default=str)
    for texto in (*saidas, caplog.text, gravado):
        assert CHAVE_FAMA not in texto
    # a frase da FAMA e o erro que subiu ficam, com a chave trocada por [chave]
    assert "[chave]" in saidas[1] and "[chave]" in saidas[-1] and "[chave]" in caplog.text


class _Contexto:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_a_trava_contra_encolher_recusa_a_leitura_com_menos_de_95_por_cento(banco):
    _gerar(banco, FamaFalsa([_os(i) for i in range(1, 101)]))
    assert banco.syncs == 1
    # 94 de 100: leitura incompleta, nada se grava (a lista da FAMA só cresce)
    r = _gerar(banco, FamaFalsa([_os(i) for i in range(1, 95)]), agora=AGORA + timedelta(hours=1))
    assert "leitura incompleta" in r["nao_grava"] and banco.syncs == 1
    assert len(banco.linhas(F.LIVRO, F.ABA)) == 100
    # 95 de 100 passa (a OS que a FAMA tirou da Grid sai do fato)
    r = _gerar(banco, FamaFalsa([_os(i) for i in range(1, 96)]), agora=AGORA + timedelta(hours=2))
    assert r["gravado"][F.ABA] == 95 and banco.syncs == 2


def test_a_leitura_do_banco_que_nao_vem_inteira_nao_grava(banco):
    _gerar(banco, FamaFalsa([_os(1), _os(2)]))
    banco.omitir.add(F.LIVRO)                    # a listagem deixa as abas de fora por um instante
    r = _gerar(banco, FamaFalsa([_os(1), _os(2), _os(3)]), agora=AGORA + timedelta(hours=1))
    assert "nao_grava" in r and banco.syncs == 1


def test_so_grava_quando_a_fama_ou_a_ligacao_muda(banco):
    itens = [_os(1), _os(2, projeto=11, nome="Morro Inventado IV")]
    _gerar(banco, FamaFalsa(itens))
    r = _gerar(banco, FamaFalsa(itens), agora=AGORA + timedelta(hours=1))
    assert r["mudou"] is False and "gravado" not in r and banco.syncs == 1
    # a OS andou de status na FAMA: grava
    r = _gerar(banco, FamaFalsa([_os(1, status=("closed", 9)), itens[1]]), agora=AGORA + timedelta(hours=2))
    assert r["mudou"] is True and banco.syncs == 2
    # o Levi decidiu a ligação do projeto 11 na tela e publicou o de-para: a OS ganha a usina na hora seguinte
    _semear(banco, "cadastro_nexus", "de_para",
            DE_PARA + [{"usina_id": 52, "sistema": F.SISTEMA, "chave_externa": "11", "casou_por": "manual (11/11)"}])
    r = _gerar(banco, FamaFalsa([_os(1, status=("closed", 9)), itens[1]]), agora=AGORA + timedelta(hours=3))
    assert r["mudou"] is True and {int(l["fama_os_id"]): l["usina_id"] for l in banco.linhas(F.LIVRO, F.ABA)} == {
        1: 37, 2: 52}


def test_a_outra_maquina_que_gravou_ha_pouco_segura_a_volta(banco):
    _gerar(banco, FamaFalsa([_os(1)]))
    f = FamaFalsa([_os(1), _os(2)])
    r = _gerar(banco, f, agora=AGORA + timedelta(minutes=20))
    assert "pulou" in r and not f.pedidos and banco.syncs == 1          # nem lê a FAMA


def test_sem_o_de_para_ou_com_a_chave_do_cadastro_quebrada_nada_se_grava(banco):
    vazio = ApiPGFalsa()
    f = FamaFalsa([_os(1)])
    assert "de-para" in _gerar(vazio, f)["nao_grava"] and not f.pedidos and vazio.syncs == 0
    r = _gerar(banco, FamaFalsa([_os(1)]), config=_config(NEXUS_CHAVE_CADASTRO="não-é-chave"))
    assert "NEXUS_CHAVE_CADASTRO" in r["nao_grava"] and banco.syncs == 0


@pytest.mark.parametrize("falta", fama.CHAVES)
def test_a_carga_so_liga_com_as_tres_chaves(falta):
    f = FamaFalsa([_os(1)])
    r = fama.gerar_fama(_config(**{falta: "  "}), NadaDeRede(), fama=f, agora=AGORA)
    assert falta in r["pulou"] and not f.pedidos


def test_teste_e_copia_de_prova_nunca_leem_a_fama_de_verdade():
    r = fama.gerar_fama(_config(TESTING=True), NadaDeRede(), agora=AGORA)
    assert "pulou" in r


def test_a_falha_da_fama_nao_derruba_a_volta(monkeypatch):
    """A FAMA é a última peça da volta de hora em hora, e o que ela levanta fica no estado e no log, nunca sobe."""
    app = type("App", (), {"config": _config(), "app_context": lambda self: _Contexto()})()
    monkeypatch.setattr(fama, "gerar_fama", lambda config: (_ for _ in ()).throw(RuntimeError("banco fora")))
    carga._volta_fama(app)
    assert carga._LACO["fama"]["erro"].startswith("RuntimeError")
    monkeypatch.setattr(fama, "gerar_fama", lambda config: {"pulou": "sem as três chaves"})
    carga._volta_fama(app)
    assert carga._LACO["fama"] == {"pulou": "sem as três chaves"}
    # nem o módulo da FAMA que não carrega derruba o laço
    import sys
    import nexus.dados
    monkeypatch.delattr(nexus.dados, "fama")
    monkeypatch.setitem(sys.modules, "nexus.dados.fama", None)
    carga._volta_fama(app)
    assert carga._LACO["fama"]["erro"].startswith(("ImportError", "ModuleNotFoundError"))


def test_o_laco_de_hora_em_hora_chama_a_fama_depois_das_outras_cargas():
    import inspect
    corpo = inspect.getsource(carga.ligar)
    assert corpo.index("gerar_almoxarifado(") < corpo.index("_volta_fama(app)")
