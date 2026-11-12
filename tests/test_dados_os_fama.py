"""As OS do cliente pela FAMA (11/11/2026, fase 1: sombra): o fato `nexus_os_fama · fato_os_fama`, a dimensão
`dim_projeto_fama`, o leitor da FAMA e a volta de 10 em 10 minutos. Uma FAMA de mentira e a `ApiPGFalsa` no lugar do banco:
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
    sem fuso, UTC como o resto do Nexus; a meia-noite exata (sem fuso, ou em UTC: "Z" e "+00:00") é o dia escolhido num
    calendário e vale o dia ESCRITO (em Brasília viraria o dia anterior); o dia só, ele mesmo. A qualidade conta cada
    jeito por campo (criação, prevista, fim), para a 1ª leitura do servidor confirmar qual a FAMA usa."""
    itens = [_os(1, criada="2026-10-01T02:00:00", prevista="2026-10-05T00:00:00", fim="2026-10-06"),
             _os(2, criada="2026-10-01T02:00:00-03:00", prevista="não é data", fim="2026-10-06T00:00:00+00:00"),
             _os(3, criada="2026-10-03T01:00:00Z", prevista="2026-10-05T00:00:00Z", fim="2026-10-07T00:00:00.000+00:00")]
    linhas, rel, _ = _montar(itens)
    d = _por_os(linhas)
    assert (d[1]["data_id_criacao"], d[1]["data_id_prevista"], d[1]["data_id_fim"]) == (20260930, 20261005, 20261006)
    assert (d[2]["data_id_criacao"], d[2]["data_id_prevista"], d[2]["data_id_fim"]) == (20261001, None, 20261006)
    # 01:00Z é 22:00 do dia anterior em Brasília; a meia-noite UTC, o dia escrito
    assert (d[3]["data_id_criacao"], d[3]["data_id_prevista"], d[3]["data_id_fim"]) == (20261002, 20261005, 20261007)
    assert rel["datas"] == {"criacao": {"sem_fuso": 1, "com_fuso": 2},
                            "prevista": {"meia_noite": 1, "invalida": 1, "com_fuso_meia_noite": 1},
                            "fim": {"dia": 1, "com_fuso_meia_noite": 2}}
    # meia-noite com outro fuso não é a meia-noite UTC: vira o dia de Brasília, como qualquer hora com fuso
    assert F.dia("2026-10-05T00:00:00+02:00") == (datetime(2026, 10, 4).date(), "com_fuso")
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


def test_nenhum_texto_livre_nem_pessoa_em_claro_em_linha_nenhuma(banco):
    itens = [_os(1), _os(2, projeto=11, nome="Morro Inventado IV")]
    linhas, _rel, por_os = _montar(itens, ligacao={10: 37})
    dim = F.dim_projetos(por_os, [])
    # o que vai ao banco: as QUATRO abas que a carga grava, lidas de volta do banco de mentira
    r = _gerar(banco, FamaFalsa(itens))
    assert set(r["gravado"]) == {F.ABA, F.ABA_DIM, "qualidade", "atualizacao"}
    no_banco = {a: banco.linhas(F.LIVRO, a) for a in r["gravado"]}
    assert all(no_banco.values())
    for texto in (json.dumps([linhas, dim], ensure_ascii=False, default=str),
                  *(json.dumps(ls, ensure_ascii=False, default=str) for ls in no_banco.values())):
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


# ── o leitor da FAMA e a volta de 10 em 10 minutos ────────────────────────────────────────────────────────────────────
class Relogio:
    """O relógio monotônico de mentira: a FAMA de mentira o anda a cada bloco que manda."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class CorpoFalso:
    """O `raw` (urllib3) de mentira: `read1` entrega um bloco por vez, como chega, e anda o relógio `passo_s`; `shutdown`
    corta a leitura (o que o vigia do prazo chama); `ao_ler(n)` roda antes da n-ésima leitura."""

    def __init__(self, blocos, relogio=None, passo_s=0.0, ao_ler=None):
        self.blocos, self.relogio, self.passo_s, self.ao_ler = list(blocos), relogio, passo_s, ao_ler
        self.leituras, self.cortado = 0, False

    def read1(self, amt=None, decode_content=None):
        self.leituras += 1
        if self.ao_ler:
            self.ao_ler(self.leituras)
        if self.relogio is not None:
            self.relogio.t += self.passo_s
        if self.cortado or not self.blocos:
            return b""
        b = self.blocos.pop(0)
        if amt and len(b) > amt:
            self.blocos.insert(0, b[amt:])
            b = b[:amt]
        return b

    def shutdown(self):
        self.cortado = True


class RespostaFama:
    def __init__(self, status, corpo, relogio=None, passo_s=0.0, bloco=None, ao_ler=None):
        self.status_code, self.fechada = status, False
        dados = bytes(corpo) if isinstance(corpo, (bytes, bytearray)) else json.dumps(corpo).encode("utf-8")
        tam = bloco or max(1, len(dados))
        self.raw = CorpoFalso([dados[i:i + tam] for i in range(0, len(dados), tam)], relogio, passo_s, ao_ler)

    def close(self):
        self.fechada = True


class FamaFalsa:
    """A FAMA de mentira: guarda cada pedido e responde o que o teste mandar. Exige `stream=True` e
    `allow_redirects=False` (revisão de 11/11/2026): sem eles o teste FALHA, e não vira um "não li" calado."""

    def __init__(self, corpo=None, status=200, erro=None, relogio=None, passo_s=0.0, bloco=None, ao_ler=None):
        self.corpo, self.status, self.erro, self.pedidos, self.respostas = corpo, status, erro, [], []
        self.relogio, self.passo_s, self.bloco, self.ao_ler = relogio, passo_s, bloco, ao_ler

    def get(self, url, headers=None, timeout=None, params=None, stream=None, allow_redirects=True):
        self.pedidos.append({"metodo": "GET", "url": url, "headers": dict(headers or {}), "timeout": timeout,
                             "params": params, "stream": stream, "allow_redirects": allow_redirects})
        if stream is not True or allow_redirects is not False:
            pytest.fail("o leitor da FAMA tem de pedir stream=True e allow_redirects=False")
        if self.erro is not None:
            raise self.erro
        r = RespostaFama(self.status, self.corpo, self.relogio, self.passo_s, self.bloco, self.ao_ler)
        self.respostas.append(r)
        return r

    def __getattr__(self, nome):                 # post, put, patch, delete: o leitor nunca chama
        pytest.fail(f"o leitor da FAMA chamou {nome}")


class NadaDeRede:
    """Sessão que falha se alguém a usar: a carga sem as três chaves (ou fora do servidor) não fala com o banco nem com a
    FAMA."""

    def __getattr__(self, nome):
        pytest.fail(f"chamou {nome} sem poder")


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


@pytest.fixture(autouse=True)
def no_servidor(monkeypatch):
    """A carga só roda no servidor (revisão de 11/11/2026, uma máquina só): estes testes fazem de conta que são ele."""
    monkeypatch.setattr(fama, "_maquina", lambda: "servidor")


@pytest.fixture
def banco():
    api = ApiPGFalsa()
    _semear(api, "cadastro_nexus", "de_para", DE_PARA)
    return api


def _gerar(api, fama_falsa, config=None, **k):
    return fama.gerar_fama(config or _config(), api, fama=fama_falsa, agora=k.pop("agora", AGORA), **k)


class _Contexto:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _App:
    def __init__(self, config=None):
        self.config = config or _config()

    def app_context(self):
        return _Contexto()


def test_o_leitor_so_faz_get_na_rota_com_a_chave_no_cabecalho_em_blocos_e_sem_redirecionar():
    f = FamaFalsa([_os(1)])
    assert fama.ler(CHAVE_FAMA, f) == [_os(1)]
    assert f.pedidos == [{"metodo": "GET", "url": "https://api.fama.energy/v2/contractor/service-orders/",
                          "headers": {"X-Contractor-Key": CHAVE_FAMA, "Accept": "application/json"},
                          "timeout": (fama.CONEXAO_S, fama.PRAZO_S), "params": None, "stream": True,
                          "allow_redirects": False}]
    assert fama.PRAZO_S == 90 and fama.TETO_BYTES == 50 * 2 ** 20 and f.respostas[0].fechada


def test_a_resposta_que_pinga_devagar_passa_do_prazo_inteiro_e_nada_se_grava(banco, monkeypatch):
    """O timeout do requests vale por leitura do socket: a resposta que pinga um bloco a cada 10 s nunca fica 90 s
    parada e seguraria a volta sem limite. O prazo é da resposta INTEIRA (relógio monotônico): passou, "não li"."""
    rel = Relogio()
    monkeypatch.setattr(fama, "RELOGIO", rel)
    itens = [_os(i) for i in range(1, 40)]
    f = FamaFalsa(itens, relogio=rel, passo_s=10.0, bloco=200)
    r = _gerar(banco, f)
    assert "nao_li" in r and "90 s" in r["nao_li"] and banco.syncs == 0
    assert f.respostas[0].fechada and f.respostas[0].raw.leituras == 10      # parou no bloco que passou dos 90 s
    # a mesma resposta, mais depressa, cabe no prazo
    rel.t = 1000.0
    assert len(fama.ler(CHAVE_FAMA, FamaFalsa(itens, relogio=rel, passo_s=1.0, bloco=2000))) == 39


def test_o_vigia_corta_a_leitura_no_prazo_e_o_corpo_pela_metade_nao_passa(monkeypatch):
    """O bloco que não chega nunca (a leitura parada no socket) não é visto pelo laço: um vigia corta a resposta no prazo
    (`raw.shutdown`), e o corpo que chegou até ali vira "não li", nunca uma lista pela metade."""
    vigias = []

    class TimerFalso:
        def __init__(self, intervalo, funcao):
            self.intervalo, self.funcao, self.cancelado, self.daemon = intervalo, funcao, False, False
            vigias.append(self)

        def start(self):
            pass

        def cancel(self):
            self.cancelado = True
    monkeypatch.setattr(fama, "_Timer", TimerFalso)
    rel = Relogio()
    monkeypatch.setattr(fama, "RELOGIO", rel)
    # o vigia dispara antes da 3ª leitura (o prazo venceu com o socket parado); o relógio de mentira não andou
    f = FamaFalsa([_os(1), _os(2), _os(3)], bloco=50, ao_ler=lambda n: n == 3 and vigias[0].funcao())
    with pytest.raises(fama.NaoLi, match="90 s"):
        fama.ler(CHAVE_FAMA, f)
    assert vigias[0].intervalo == fama.PRAZO_S and vigias[0].cancelado and f.respostas[0].fechada


def test_a_resposta_maior_que_o_teto_nao_se_le(banco, monkeypatch):
    monkeypatch.setattr(fama, "TETO_BYTES", 3000)
    f = FamaFalsa([_os(i) for i in range(1, 20)], bloco=500)
    r = _gerar(banco, f)
    assert "nao_li" in r and "teto" in r["nao_li"] and banco.syncs == 0 and f.respostas[0].fechada
    assert f.respostas[0].raw.leituras == 7          # parou no bloco que passou do teto, sem ler o resto


def test_o_redirecionamento_nao_e_seguido_e_a_chave_nao_sai_para_outro_endereco(banco):
    f = FamaFalsa(status=302, corpo=b"")
    r = _gerar(banco, f)
    assert "nao_li" in r and "302" in r["nao_li"] and "redireciona" in r["nao_li"] and banco.syncs == 0
    assert [p["url"] for p in f.pedidos] == [fama.URL] and fama.URL.startswith("https://")


def test_a_carga_grava_o_livro_inteiro_e_confere(banco):
    f = FamaFalsa([_os(1), _os(2), _os(3, projeto=11, nome="Morro Inventado IV")])
    r = _gerar(banco, f)
    assert r["gravado"] == {F.ABA: 3, F.ABA_DIM: 2, "qualidade": 1, "atualizacao": 1} and r["mudou"] is True
    assert len(f.pedidos) == 1                             # uma leitura só, sem repetir
    fato = {int(l["fama_os_id"]): l for l in banco.linhas(F.LIVRO, F.ABA)}
    assert (fato[1]["usina_id"], fato[3]["usina_id"]) == (37, None)
    q = banco.linhas(F.LIVRO, "qualidade")[0]
    assert (q["fato"], q["linhas"], q["pct_usina"]) == ("os_fama", 3, 66.7)
    assert json.loads(q["extra"])["datas"]["prevista"] == {"dia": 3}           # o formato de cada campo, contado
    at = banco.linhas(F.LIVRO, "atualizacao")[0]
    assert (at["linhas"], at["sha_linhas"], at["situacao"]) == (3, r["sha_linhas"], "mudou")


@pytest.mark.parametrize("fama_falsa", [
    FamaFalsa(status=401, corpo={"detail": "Could not validate credentials"}),
    FamaFalsa(status=500, corpo={"detail": "erro interno"}),
    FamaFalsa(status=302, corpo=b""),
    FamaFalsa(corpo={"rows": [_os(1)]}),                       # resposta que não é lista
    FamaFalsa(corpo=b"<html>nao e JSON</html>"),
    FamaFalsa(erro=requests.Timeout("passou de 90 s")),
    FamaFalsa(erro=requests.ConnectionError("sem rede")),
], ids=["401", "500", "302", "objeto", "nao_json", "timeout", "sem_rede"])
def test_erro_401_ou_resposta_que_nao_e_lista_vira_nao_li_e_nada_se_grava(banco, fama_falsa):
    r = _gerar(banco, fama_falsa)
    assert "nao_li" in r and "gravado" not in r
    assert banco.syncs == 0 and F.LIVRO not in banco.workbooks
    assert len(fama_falsa.pedidos) == 1                    # sem repetir em laço: a hora seguinte tenta de novo
    assert all(x.fechada for x in fama_falsa.respostas)


def test_a_chave_fica_fora_de_toda_saida(banco, caplog, monkeypatch):
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
    erro = RuntimeError(f"o banco caiu levando {CHAVE_FAMA}")
    monkeypatch.setattr(fama, "gerar_fama", lambda *a, **k: (_ for _ in ()).throw(erro))
    carga._volta_fama(_App())
    saidas.append(json.dumps(carga._LACO["fama"], ensure_ascii=False))
    gravado = json.dumps({a: banco.linhas(F.LIVRO, a) for a in (F.ABA, F.ABA_DIM, "qualidade", "atualizacao")},
                         ensure_ascii=False, default=str)
    for texto in (*saidas, caplog.text, gravado):
        assert CHAVE_FAMA not in texto
    # a frase da FAMA e o erro que subiu ficam, com a chave trocada por [chave]
    assert "[chave]" in saidas[1] and "[chave]" in saidas[-1] and "[chave]" in caplog.text


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


def test_de_10_em_10_minutos_sem_mudanca_a_fama_e_lida_e_o_livro_nao_regrava(banco):
    """A volta de 10 em 10 min (12/11/2026) lê a FAMA a cada volta, e o livro só é regravado quando a FAMA ou a ligação
    muda (ou uma vez por dia, o batimento): seis voltas por hora não viram seis gravações."""
    itens = [_os(1), _os(2, projeto=11, nome="Morro Inventado IV")]
    _gerar(banco, FamaFalsa(itens))
    assert banco.syncs == 1
    for m in (10, 20, 30, 40, 50):
        f = FamaFalsa(itens)
        r = _gerar(banco, f, agora=AGORA + timedelta(minutes=m))
        assert len(f.pedidos) == 1 and r["mudou"] is False and "gravado" not in r, m      # leu, e não gravou
    assert banco.syncs == 1
    # a OS que anda na FAMA chega ao banco na volta seguinte (em até 10 min), e não na hora seguinte
    r = _gerar(banco, FamaFalsa([_os(1, status=("closed", 9)), itens[1]]), agora=AGORA + timedelta(minutes=60))
    assert r["mudou"] is True and banco.syncs == 2


def test_o_batimento_grava_uma_vez_por_dia_mesmo_sem_mudanca(banco):
    """Sem o batimento, "sem novidade na FAMA" e "a leitura quebrada há dias" eram o mesmo `gerado_em` velho: a
    `atualizacao` é regravada uma vez por dia, mesmo sem mudança ("li, nada mudou")."""
    itens = [_os(1)]
    _gerar(banco, FamaFalsa(itens))
    r = _gerar(banco, FamaFalsa(itens), agora=AGORA + timedelta(hours=1))
    assert r["mudou"] is False and "gravado" not in r and banco.syncs == 1
    amanha = AGORA + timedelta(days=1)
    r = _gerar(banco, FamaFalsa(itens), agora=amanha)
    assert r["mudou"] is False and r["gravado"][F.ABA] == 1 and banco.syncs == 2
    at = banco.linhas(F.LIVRO, "atualizacao")[0]
    assert at["situacao"] == "li, nada mudou" and str(at["gerado_em"]).startswith("2026-11-12")
    r = _gerar(banco, FamaFalsa(itens), agora=amanha + timedelta(hours=1))
    assert "gravado" not in r and banco.syncs == 2                      # um batimento por dia, não por hora


def test_a_outra_maquina_que_gravou_ha_pouco_segura_a_volta(banco):
    """Duas voltas no mesmo intervalo (dois processos no servidor, a troca do deploy) não gravam em dobro. O portão é
    menor que a volta de 10 min (`INTERVALO_MIN`): a gravação da volta anterior nunca barra a seguinte."""
    assert fama.INTERVALO_MIN < carga.FAMA_INTERVALO_S / 60
    _gerar(banco, FamaFalsa([_os(1)]))
    f = FamaFalsa([_os(1), _os(2)])
    r = _gerar(banco, f, agora=AGORA + timedelta(minutes=5))
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


def test_so_o_servidor_le_a_fama(monkeypatch):
    """Uma máquina só: o PC com a chave no .env nunca dá o segundo GET da volta (o critério do Nexus: o servidor é o
    Linux, `_maquina`)."""
    monkeypatch.setattr(fama, "_maquina", lambda: "pc")
    f = FamaFalsa([_os(1)])
    r = fama.gerar_fama(_config(), NadaDeRede(), fama=f, agora=AGORA)
    assert "servidor" in r["pulou"] and not f.pedidos


def test_teste_nunca_le_a_fama_de_verdade():
    """Sem a FAMA de mentira, o teste (TESTING) não lê: pula antes de qualquer pedido."""
    r = fama.gerar_fama(_config(TESTING=True), NadaDeRede(), agora=AGORA)
    assert "teste" in r["pulou"]


def test_a_copia_de_prova_nunca_liga_a_fama(monkeypatch):
    """A cópia de prova (`ferramentas/subir_copia_de_prova.py`) não é TESTING: quem a protege é o ambiente que ela monta,
    a carga de dados desligada (NEXUS_CARGA_DADOS=0) e a NEXUS_FAMA_CHAVE vazia, que vence o .env e some da
    configuração. Exercido aqui: o ambiente, a configuração que sai dele, a carga que não liga e a FAMA que pula."""
    import importlib.util
    import os
    from pathlib import Path

    from nexus import dados
    from nexus.config import OBRIGATORIAS, carregar_config
    caminho = Path(__file__).resolve().parent.parent / "ferramentas" / "subir_copia_de_prova.py"
    spec = importlib.util.spec_from_file_location("copia_de_prova_teste", caminho)
    copia = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(copia)
    monkeypatch.setattr(os, "environ", dict(os.environ, NEXUS_FAMA_CHAVE=CHAVE_FAMA, NEXUS_CARGA_DADOS="1"))
    copia.preparar_ambiente()
    assert os.environ["NEXUS_FAMA_CHAVE"] == "" and os.environ["NEXUS_CARGA_DADOS"] == "0"
    env = {**{k: "valor-de-teste" for k in OBRIGATORIAS}, "NEXUS_FAMA_CHAVE": CHAVE_FAMA,
           "GRIDCO_SQL_TOKEN": "token-de-teste", "NEXUS_CHAVE_CADASTRO": CHAVE_CADASTRO}
    env.update({k: v for k, v in os.environ.items() if k.startswith("NEXUS_")})     # o ambiente vence o .env
    cfg = carregar_config(env)
    assert "NEXUS_FAMA_CHAVE" not in cfg and cfg["NEXUS_CARGA_DADOS"] == "0"
    monkeypatch.setattr(carga, "ligar", lambda app: pytest.fail("a cópia de prova ligou a carga de dados"))
    monkeypatch.setattr(carga, "ligar_fama", lambda app: pytest.fail("a cópia de prova ligou a volta da FAMA"))
    dados.instalar(_App(dict(cfg, GRIDCO_SQL_TOKEN="token-de-teste")))
    f = FamaFalsa([_os(1)])
    assert "NEXUS_FAMA_CHAVE" in fama.gerar_fama(cfg, NadaDeRede(), fama=f, agora=AGORA)["pulou"] and not f.pedidos


def test_a_sessao_da_fama_fecha(banco, monkeypatch):
    """Sem a sessão de mentira, o leitor abre a dele e a fecha (`with`), mesmo quando lê."""
    abertas = []

    class SessaoFalsa(FamaFalsa):
        def __init__(self, corpo):
            super().__init__(corpo)
            self.fechada = False

        def __enter__(self):
            abertas.append(self)
            return self

        def __exit__(self, *a):
            self.fechada = True
            return False
    monkeypatch.setattr(requests, "Session", lambda: SessaoFalsa([_os(1)]))
    r = fama.gerar_fama(_config(), banco, agora=AGORA)
    assert r["mudou"] is True and len(abertas) == 1 and abertas[0].fechada and len(abertas[0].pedidos) == 1


def test_a_falha_da_fama_nao_derruba_a_volta(monkeypatch):
    """O que a volta da FAMA levanta fica no estado e no log, nunca sobe."""
    app = _App()
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


def test_o_laco_de_hora_em_hora_nao_roda_mais_a_fama(monkeypatch):
    """O laço de verdade (`carga.ligar`), duas voltas: a carga, a geração, o almoxarifado e a conferência das ligações (de
    mentira: nenhum pedido de rede). A FAMA saiu dele (12/11/2026): tem a volta dela, de 10 em 10 min, que não atrasa a
    carga da hora nem é atrasada por ela."""
    import threading
    ordem = []
    monkeypatch.setitem(carga._LACO, "thread", None)
    monkeypatch.setitem(carga._LACO, "parar", threading.Event())
    monkeypatch.setattr(carga, "_espera_s", lambda agora=None: 0)
    monkeypatch.setattr(carga, "rodar", lambda config: ordem.append("carga") or {})
    monkeypatch.setattr(carga, "gerar_geracao", lambda config: ordem.append("geracao") or {})

    monkeypatch.setattr(carga, "gerar_almoxarifado", lambda config: ordem.append("almoxarifado") or {})

    def conferencia(app):
        ordem.append("conferencia")
        if ordem.count("conferencia") == 2:
            carga._LACO["parar"].set()
    monkeypatch.setattr(carga, "_volta_conferencia", conferencia)
    monkeypatch.setattr(fama, "gerar_fama", lambda config: ordem.append("fama") or {})
    carga.ligar(_App())
    try:
        carga._LACO["thread"].join(10)
    finally:
        # com a espera zerada, a thread seguiria girando depois do monkeypatch desfeito: parar e esperar sempre
        carga._LACO["parar"].set()
        carga._LACO["thread"].join(10)
    assert not carga._LACO["thread"].is_alive()
    assert ordem == ["carga", "geracao", "almoxarifado", "conferencia"] * 2


@pytest.fixture
def volta_fama(monkeypatch):
    """O estado da volta da FAMA limpo para o teste, e a thread parada e esperada no fim (com a espera zerada, ela
    giraria depois do monkeypatch desfeito, já chamando a FAMA de verdade)."""
    import threading
    monkeypatch.setitem(carga._FAMA, "thread", None)
    monkeypatch.setitem(carga._FAMA, "parar", threading.Event())
    monkeypatch.setitem(carga._FAMA, "lendo", threading.Lock())
    yield carga._FAMA
    carga._FAMA["parar"].set()
    if carga._FAMA["thread"] is not None:
        carga._FAMA["thread"].join(10)


def test_a_fama_tem_a_volta_dela_de_10_em_10_minutos(volta_fama):
    """De 10 em 10 min, numa grade fixa (aos :05, :15, ..., :55): o deploy que reinicia o Nexus não lê a FAMA a mais,
    e a volta fica longe dos :40 da carga da hora."""
    assert carga.FAMA_INTERVALO_S == 600
    h = datetime(2026, 11, 12, 10, 0, tzinfo=BRT)
    assert carga._espera_fama_s(h + timedelta(minutes=4, seconds=30)) == 30
    assert carga._espera_fama_s(h + timedelta(minutes=5)) == 600
    assert carga._espera_fama_s(h + timedelta(minutes=13, seconds=20)) == 100
    assert carga._espera_fama_s(h + timedelta(minutes=59, seconds=59)) == 301
    assert all(1 <= carga._espera_fama_s(h + timedelta(seconds=x)) <= 601 for x in range(0, 3600, 7))
    # a espera que acordou um triz antes da hora não emenda outra volta no mesmo horário
    assert carga._espera_fama_s(h + timedelta(minutes=4, seconds=59, microseconds=998000)) > 600


def test_a_volta_da_fama_roda_na_thread_dela_e_segue_depois_da_queda(volta_fama, monkeypatch):
    """A volta própria (`carga.ligar_fama`): a FAMA que cai fica no estado, sem a chave, e a volta continua; a carga da
    hora nunca roda nela."""
    chamadas = []
    monkeypatch.setattr(carga, "_espera_fama_s", lambda agora=None: 0)
    monkeypatch.setattr(carga, "rodar", lambda config: pytest.fail("a volta da FAMA rodou a carga da hora"))

    def fama_que_cai(config):
        chamadas.append(1)
        if len(chamadas) == 2:
            carga._FAMA["parar"].set()
        raise RuntimeError(f"caiu levando {CHAVE_FAMA}")
    monkeypatch.setattr(fama, "gerar_fama", fama_que_cai)
    carga.ligar_fama(_App())
    assert carga._FAMA["thread"].name == "nexus-fama"
    carga._FAMA["thread"].join(10)
    assert not carga._FAMA["thread"].is_alive() and len(chamadas) == 2
    assert carga._LACO["fama"]["erro"].startswith("RuntimeError") and CHAVE_FAMA not in carga._LACO["fama"]["erro"]


def test_uma_volta_da_fama_de_cada_vez(volta_fama, monkeypatch):
    """A leitura que demora (o prazo é de 90 s) não é sobreposta: a volta que chega no meio dela pula, sem ler."""
    import threading
    entrou, solta, chamadas = threading.Event(), threading.Event(), []

    def fama_lenta(config):
        chamadas.append(1)
        entrou.set()
        solta.wait(10)
        return {"pulou": "nada mudou"}
    monkeypatch.setattr(fama, "gerar_fama", fama_lenta)
    t = threading.Thread(target=carga._volta_fama, args=(_App(),))
    t.start()
    try:
        assert entrou.wait(10)
        assert carga._volta_fama(_App()) is False and len(chamadas) == 1        # a segunda nem chama a FAMA
    finally:
        solta.set()
        t.join(10)
    assert carga._volta_fama(_App()) is True and len(chamadas) == 2              # acabada a primeira, a próxima lê


def test_ligar_a_volta_da_fama_duas_vezes_faz_uma_thread_so(volta_fama, monkeypatch):
    import threading
    monkeypatch.setattr(carga, "_espera_fama_s", lambda agora=None: 3600)        # a thread espera; ninguém lê
    monkeypatch.setattr(fama, "gerar_fama", lambda config: pytest.fail("leu a FAMA"))
    carga.ligar_fama(_App())
    primeira = carga._FAMA["thread"]
    carga.ligar_fama(_App())
    assert carga._FAMA["thread"] is primeira
    assert [t for t in threading.enumerate() if t.name == "nexus-fama"] == [primeira]


def test_a_conferencia_espera_a_leitura_da_fama_e_a_segura_enquanto_rele(volta_fama, monkeypatch):
    """A volta da FAMA regravando o `nexus_os_fama` no meio da conferência das ligações daria uma contagem falsa naquele
    dia (revisão de 12/11/2026): a conferência espera a FAMA acabar e segura a trava enquanto relê."""
    import threading
    from nexus.dados import conferencia
    durante = []
    monkeypatch.setattr(conferencia, "rodar", lambda config: durante.append(carga._FAMA["lendo"].locked()) or {})
    monkeypatch.setattr(fama, "gerar_fama", lambda config: {"pulou": "FAMA de mentira"})
    carga._FAMA["lendo"].acquire()                                   # a FAMA lendo
    t = threading.Thread(target=carga._volta_conferencia, args=(_App(),))
    t.start()
    try:
        t.join(0.3)
        assert t.is_alive() and durante == []                        # esperando a FAMA
    finally:
        carga._FAMA["lendo"].release()
        t.join(10)
    assert durante == [True] and not carga._FAMA["lendo"].locked()    # segurou enquanto relia, e soltou
    assert carga._volta_fama(_App()) is True                         # a FAMA volta a ler
    # a leitura da FAMA que passa da espera não segura a conferência para sempre
    monkeypatch.setattr(carga, "CONFERENCIA_ESPERA_FAMA_S", 0.1)
    carga._FAMA["lendo"].acquire()
    try:
        carga._volta_conferencia(_App())
    finally:
        carga._FAMA["lendo"].release()
    assert len(durante) == 2


@pytest.mark.parametrize("falta", fama.CHAVES)
def test_sem_as_tres_chaves_a_volta_da_fama_nem_liga(volta_fama, falta):
    carga.ligar_fama(_App(_config(**{falta: ""})))
    assert carga._FAMA["thread"] is None and falta in carga._LACO["fama"]["pulou"]


def test_fora_do_servidor_a_volta_da_fama_nem_liga(volta_fama, monkeypatch):
    monkeypatch.setattr(fama, "_maquina", lambda: "pc")
    carga.ligar_fama(_App())
    assert carga._FAMA["thread"] is None and "servidor" in carga._LACO["fama"]["pulou"]


def test_instalar_liga_a_carga_da_hora_e_a_volta_da_fama(monkeypatch):
    from nexus import dados
    ligadas = []
    monkeypatch.setattr(carga, "ligar", lambda app: ligadas.append("carga"))
    monkeypatch.setattr(carga, "ligar_fama", lambda app: ligadas.append("fama"))
    dados.instalar(_App(_config()))
    assert ligadas == ["carga", "fama"]
    ligadas.clear()
    dados.instalar(_App(_config(NEXUS_CARGA_DADOS="0")))             # desligada nesta máquina: nenhuma das duas
    assert ligadas == []
