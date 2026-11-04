"""A Central da usina (Levi, 04/11/2026: "Como temos uma visão para os supervisores em Central do Responsável podemos ter
como pesquisar a usina e ter uma central de informações daquela usina, performance, disponibilidade, sujidade,
pendências, chamados, PTs etc"; "inclua junto da central dos responsáveis, como aba alternativa"). Decisões dele: a aba
na Visão do responsável, o mês corrente, as quatro pendências (rondas, OS atrasadas e pausadas, ocorrências abertas,
Segurança) e todas as usinas na busca. Banco falso do test_campo_responsaveis (a Altair, a Brodowski 1 e a Coração 1)."""
from datetime import timedelta

from test_campo_responsaveis import HOJE, _chamado, _por_usina, tela  # noqa: F401  (tela é fixture)
from test_campo_visao import _aba, banco  # noqa: F401  (banco é fixture)

from nexus.campo import central_usina as CU
from nexus.campo import responsaveis as R
from nexus.campo import visao
from nexus.dados import fato_chamado as F


def _central(logado, args=""):
    return logado.get("/t/campo/responsaveis?modo=usina" + args).get_data(as_text=True)


def test_a_aba_fica_ao_lado_das_outras_e_busca_todas_as_usinas(tela, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    assert ">Central da usina</a>" in html and "modo=usina" in html
    html = _central(logado, "&responsavel=Ciclano+Chefe")
    # a busca traz TODAS as usinas da Visão, sem o filtro do responsável (decisão do Levi: as 131, para quem abre a tela)
    for uid in (1, 2, 3):
        assert f'id="rd-us-{uid}"' in html
    assert 'name="modo" value="usina"' in html and "Busque a usina pelo nome" in html
    # o responsável, o cliente e a busca da lista não valem na Central
    assert 'id="cr-responsavel"' not in html and 'id="cr-cliente"' not in html


def test_a_usina_escolhida_traz_os_numeros_da_linha_dela_na_visao(tela, logado):
    html = _central(logado, "&usina=1")
    a = _por_usina()["Altair"]
    assert '<h2 class="cu-nome">Altair</h2>' in html
    # os números são os da linha da Altair na Visão (o mesmo do Painel e da Visão geral), e a meta abre o dia a dia
    for txt in (a["perf"]["valores"]["meta"]["txt"], a["perf"]["valores"]["disp"]["txt"]):
        assert txt in html
    assert "/t/campo/responsaveis/usina/1/meta" in html and "Performance do mês" in html
    # as pendências: a ronda longa pendente, e a seção de cada uma
    assert "Ronda longa pendente" in html and "Ocorrências" in html and "Segurança" in html
    # chamados: o aberto (16034) com o card da OS; o concluído sem fim no mês não entra nos finalizados
    assert 'data-folio="16034"' in html and "Finalizados no mês" in html
    # PT: as duas que esperam o De acordo
    assert html.count("/t/campo/responsaveis/pt/") >= 2


def test_sem_o_script_a_busca_acha_pelo_nome(tela, logado):
    assert '<h2 class="cu-nome">Coração 1</h2>' in _central(logado, "&nome=coracao")
    html = _central(logado, "&nome=nao+existe")
    assert 'Nenhuma usina com o nome "nao existe"' in html and "cu-nome" not in html


def test_os_chamados_finalizados_no_mes(tela, banco):
    d = HOJE.replace(day=1)
    fim = d.year * 10000 + d.month * 100 + d.day
    velho = HOJE.replace(day=1) - timedelta(days=1)
    _aba(banco, "nexus_chamados", "fato_chamado", [
        dict(_chamado(17001, 1, "concluido", 30), data_id_fim=fim),
        dict(_chamado(17002, 1, "concluido", 40), data_id_fim=velho.year * 10000 + velho.month * 100 + velho.day),
        dict(_chamado(17003, 2, "concluido", 10), data_id_fim=fim), _chamado(17004, 1, "aberto", 3)])
    visao.limpar()
    fin = R.chamados_finalizados(1, HOJE)
    assert [c["os"] for c in fin] == [17001]                      # o de outro mês e o de outra usina ficam de fora
    assert fin[0]["fim"] == d and fin[0]["dias"] == 30 - (HOJE - d).days
    assert set(F.CAB_CHAMADO) >= {"data_id_fim", "situacao"}


def test_as_pendencias_da_seguranca_sao_as_da_mesa_so_da_usina():
    listas = {"vencidos": [{"usina_id": 1, "ext": "EXT01", "vence": "2026-10-01", "vence_qual": "recarga",
                            "local": "Cabine", "posicao": ""}, {"usina_id": 2, "ext": "EXT09"}],
              "pts": [{"usina_id": 1, "os": "18000", "numero": "PT-1", "codigo": "C1", "tarefa": "Troca de string"}],
              "sem_luvas": [{"usina_id": 1, "desde": "2026-10-28"}]}
    s = CU.seguranca(1, listas)
    assert [g["rot"] for g in s] == ["PT parada", "Extintor vencido", "Sem luvas"]   # a ordem da Mesa
    assert s[1]["itens"] == [{"forte": "Extintor EXT01", "txt": "(Cabine) recarga venceu em 01/10"}]
    assert s[0]["itens"][0]["pt"]["numero"] == "PT-1" and s[2]["itens"][0]["txt"] == "desde 28/10"
    assert CU.seguranca(3, listas) == []


def test_a_visao_conta_os_extintores_como_a_seguranca(tela, monkeypatch):
    """O extintor que a Segurança excluiu ou corrigiu (`decisoes.separar`) sai da conta da Visão também: antes, a Visão
    contava o livro do App cru e a Mesa, o HSEQ e o Comando, sem ele (achado da Central da usina, 04/11/2026)."""
    from nexus.hseq import decisoes as DEC

    def separar(ext, nr, est):
        return ([x for x in ext if x["codigo"] != "ALT100-EXT01"], nr,
                [x for x in ext if x["codigo"] == "ALT100-EXT01"])
    monkeypatch.setattr(DEC, "separar", separar)
    visao.limpar()
    a = _por_usina()["Altair"]
    assert (a["extintores"]["total"], a["extintores"]["vencidos"]) == (1, 0)


def test_as_pt_do_mes_sao_as_pedidas_no_mes_em_brasilia():
    from datetime import datetime, timezone
    hoje = HOJE
    no_mes = datetime(hoje.year, hoje.month, 1, 12, tzinfo=timezone.utc)
    # 1º do mês às 01:30 UTC é o último dia do mês anterior em Brasília
    virada = datetime(hoje.year, hoje.month, 1, 1, 30, tzinfo=timezone.utc)
    hist = [{"usina_id": 1, "numero": "A", "criada": no_mes}, {"usina_id": 1, "numero": "B", "criada": virada},
            {"usina_id": 2, "numero": "C", "criada": no_mes}]
    out = CU.pts_do_mes(1, hist, hoje)
    assert [p["numero"] for p in out] == ["A"] and out[0]["dia_txt"] == f"01/{hoje.month:02d}"
