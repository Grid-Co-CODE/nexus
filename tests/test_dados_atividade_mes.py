"""O `fato_atividade_usina_mes` (nexus/dados/fato_atividade_mes.py; 18/11/2026): o que foi feito em cada usina em cada
mês, guardado depois que as fontes esquecem.

Levi, 18/11/2026, sobre o prontuário por mês: "o que foi feito no ativo"; e, à proposta de guardar o fechamento de cada
mês (as rondas, as tarefas, as PT e os chamados concluídos ficam 90 dias nas fontes: outubro sumiria em janeiro): "Ok",
"faça funcionar". O fato conta dos fatos que já existem; o mês é recalculado enquanto cabe inteiro nas fontes e depois
fica como foi gravado; a linha nunca some."""
from datetime import date

from nexus.dados import fato_atividade_mes as AM
from nexus.dados import fatos

AGORA, DEPOIS = "2026-11-18T12:40:00-03:00", "2026-11-18T13:40:00-03:00"
ABERTOS = [202609, 202610, 202611]


def _fech(usina, data_id, tipo, os_, devolvida=0):
    return {"usina_id": usina, "data_id": data_id, "tipo_os": tipo, "os": os_, "devolvida": devolvida}


def _fontes():
    fech = [_fech(1, 20261005, "Corretiva", 100), _fech(1, 20261006, "Corretiva", 100), _fech(1, 20261020, "Corretiva", 101),
            _fech(1, 20261007, "Preventiva", 200), _fech(1, 20261008, "Preventiva", 200, devolvida=1),   # a devolvida não conta
            _fech(1, 20261103, "Corretiva emergencial", 300), _fech(2, 20261010, "MPM", 400),
            _fech(None, 20261010, "Corretiva", 500),                                                    # sem usina: não chuta
            _fech(1, 20260720, "Corretiva", 600)]                                                       # mês fora da janela
    ronda = [{"usina_id": 1, "data_id": 20261007, "tipo_ronda": "curta", "os": 700},
             {"usina_id": 1, "data_id": 20261021, "tipo_ronda": "longa", "os": None},
             {"usina_id": 1, "data_id": 20261028, "tipo_ronda": "curta", "os": 701}]
    pt = [{"usina_id": 1, "data_id_criacao": 20261012, "primeira_linha_da_pt": 1, "os": 100},
          {"usina_id": 1, "data_id_criacao": 20261012, "primeira_linha_da_pt": 0, "os": 100}]            # a 2ª linha da mesma PT
    tarefas = [{"usina_id": 1, "data_id_fim": 20261015, "tipo_tarefa": "zeladoria", "estado_tarefa": "finalizada", "os": 800},
               {"usina_id": 1, "data_id_fim": 20261015, "tipo_tarefa": "zeladoria", "estado_tarefa": "finalizada", "os": 800},
               {"usina_id": 1, "data_id_fim": 20261016, "tipo_tarefa": "zeladoria", "estado_tarefa": "finalizada", "os": 801},
               {"usina_id": 1, "data_id_fim": None, "tipo_tarefa": "zeladoria", "estado_tarefa": "em_progresso", "os": 802},
               {"usina_id": 1, "data_id_fim": 20261016, "tipo_tarefa": "corretiva", "estado_tarefa": "finalizada", "os": 803}]
    chamados = [{"usina_id": 1, "os": 16034, "data_id_abertura": 20261003, "data_id_fim": None, "situacao": "aberto"},
                {"usina_id": 1, "os": 15000, "data_id_abertura": 20260902, "data_id_fim": 20261009, "situacao": "concluido"}]
    return fech, ronda, pt, tarefas, chamados


def _por_chave(linhas):
    i = {c: k for k, c in enumerate(AM.CAB)}
    return {(l[i["usina_id"]], l[i["data_id_mes"]], l[i["atividade"]]): (l[i["eventos_qtd"]], l[i["os_qtd"]]) for l in linhas}


def test_os_meses_abertos_sao_os_que_cabem_inteiros_nas_fontes():
    assert AM.meses_abertos(date(2026, 11, 18)) == ABERTOS
    # outubro sai da conta (e congela) quando o dia 1º dele passa dos 85 dias: 26/12; as fontes ainda o têm até 30/12
    assert AM.meses_abertos(date(2026, 12, 25)) == [202610, 202611, 202612]
    assert AM.meses_abertos(date(2026, 12, 26)) == [202611, 202612]
    assert AM.meses_abertos(date(2027, 1, 5)) == [202611, 202612, 202701]


def test_a_conta_de_cada_atividade_do_mes():
    linhas = AM.montar(*_fontes(), ABERTOS, AGORA)
    assert _por_chave(linhas) == {
        (1, 20261001, "tarefa_corretiva"): (3, 2),            # 3 tarefas em 2 OS
        (1, 20261001, "tarefa_preventiva"): (1, 1),           # a devolvida ficou de fora
        (1, 20261101, "tarefa_corretiva_emergencial"): (1, 1),
        (2, 20261001, "tarefa_mpm"): (1, 1),
        (1, 20261001, "ronda_curta"): (2, 2), (1, 20261001, "ronda_longa"): (1, 0),
        (1, 20261001, "pt"): (1, 1),                          # a PT conta uma vez (a 1ª linha)
        (1, 20261001, "zeladoria"): (2, 2),                   # dois DIAS de zeladoria, em 2 OS
        (1, 20261001, "chamado_aberto"): (1, 1), (1, 20261001, "chamado_finalizado"): (1, 1),
        (1, 20260901, "chamado_aberto"): (1, 1)}              # o chamado aberto em setembro e finalizado em outubro
    i = {c: k for k, c in enumerate(AM.CAB)}
    assert all(l[i["usina_ligada_por"]] == AM.LIGADA_POR and l[i["calculado_em"]] == AGORA for l in linhas)
    assert len({l[i["atividade_id"]] for l in linhas}) == len(linhas)                    # o grão: 1 linha por chave
    # as mesmas fontes como o banco as devolve quando manda tudo em texto, e as abas em memória da carga
    fech, ronda, pt, tarefas, chamados = _fontes()
    texto = [[{k: (None if v is None else str(v)) for k, v in x.items()} for x in f] for f in (fech, ronda, pt, tarefas, chamados)]
    assert _por_chave(AM.montar(*texto, ABERTOS, AGORA)) == _por_chave(linhas)
    cab = ["usina_id", "data_id", "tipo_os", "os", "devolvida"]
    em_memoria = (cab, [[x.get(c) for c in cab] for x in fech])
    assert _por_chave(AM.montar(em_memoria, ronda, pt, tarefas, chamados, ABERTOS, AGORA)) == _por_chave(linhas)
    # nenhuma coluna com nome de pessoa ou texto livre (regra 8), e as medidas com a unidade no nome
    assert not {"nome", "tarefa", "motivo", "observacao", "tecnico"} & set(AM.CAB)
    assert all(c.endswith("_qtd") for c, _u, _s in AM.MEDIDAS) and AM.CHAVE[0] == AM.CAB[0]


def test_o_mes_fechado_fica_como_esta_e_o_aberto_e_recalculado_sem_encolher():
    i = {c: k for k, c in enumerate(AM.CAB)}
    primeira = AM.mesclar([], AM.montar(*_fontes(), ABERTOS, AGORA), ABERTOS, AGORA)
    no_banco = [dict(zip(AM.CAB, [None if v is None else str(v) for v in l])) for l in primeira]      # o banco em texto
    # a carga seguinte, igual: nada muda, e o `calculado_em` é o da 1ª (a API guarda o histórico de cada linha que muda)
    segunda = AM.mesclar(no_banco, AM.montar(*_fontes(), ABERTOS, DEPOIS), ABERTOS, DEPOIS)
    assert segunda == primeira and AM.sha_linhas(segunda) == AM.sha_linhas(primeira)
    # o tempo passa: setembro e outubro saem da janela e as fontes esquecem (só novembro vem, e mudado)
    fech = [_fech(1, 20261103, "Corretiva emergencial", 300), _fech(1, 20261110, "Corretiva emergencial", 301)]
    terceira = AM.mesclar(no_banco, AM.montar(fech, [], [], [], [], [202611, 202612], DEPOIS), [202611, 202612], DEPOIS)
    t = _por_chave(terceira)
    assert t[(1, 20261001, "tarefa_corretiva")] == (3, 2) and t[(1, 20261001, "ronda_curta")] == (2, 2)   # outubro intocado
    assert t[(1, 20260901, "chamado_aberto")] == (1, 1)
    assert t[(1, 20261101, "tarefa_corretiva_emergencial")] == (2, 2)                                       # novembro recalculado
    mudou = next(l for l in terceira if l[i["atividade"]] == "tarefa_corretiva_emergencial")
    ficou = next(l for l in terceira if l[i["atividade"]] == "ronda_longa")
    assert mudou[i["calculado_em"]] == DEPOIS and ficou[i["calculado_em"]] == AGORA
    assert AM.sha_linhas(terceira) != AM.sha_linhas(primeira) and len(terceira) == len(primeira)
    # a linha de mês ABERTO que sumiu da conta fica, com zero: o fato não encolhe (a trava `so_cresce` recusaria)
    quarta = AM.mesclar(no_banco, AM.montar([], [], [], [], [], ABERTOS, DEPOIS), ABERTOS, DEPOIS)
    assert len(quarta) == len(primeira) and set(_por_chave(quarta).values()) == {(0, 0)}
    assert AM.meses_das_linhas(terceira) == [202609, 202610, 202611]


def test_as_tabelas_do_livro_e_a_leitura_do_mes():
    linhas = AM.mesclar([], AM.montar(*_fontes(), ABERTOS, AGORA), ABERTOS, AGORA)
    tab = AM.tabelas(linhas, AGORA, "servidor", ABERTOS, {"fontes": "ok"})
    assert set(tab) == {AM.ABA, "qualidade", "atualizacao"} and tab[AM.ABA] == (AM.CAB, linhas)
    q = dict(zip(fatos.CAB_QUALIDADE, tab["qualidade"][1][0]))
    assert q["fato"] == AM.FATO and q["linhas"] == len(linhas) and q["pct_usina"] == 100.0 and q["pct_data"] == 100.0
    at = dict(zip(AM.CAB_ATUALIZACAO, tab["atualizacao"][1][0]))
    assert at["sha_linhas"] == AM.sha_linhas(linhas) and at["meses_recalculados"] == "202609, 202610, 202611"
    assert AM.CAB_ATUALIZACAO[2] == "duracao_s"                # a carga escreve a duração na 3ª coluna de todo livro
    # a leitura do prontuário: o mês da usina, e vazio (não zero) no que não foi guardado
    lidas = [dict(zip(AM.CAB, [None if v is None else str(v) for v in l])) for l in linhas]
    assert AM.do_mes(lidas, 1, 202610)["tarefa_corretiva"] == (3, 2) and AM.do_mes(lidas, 1, 202610)["zeladoria"] == (2, 2)
    assert AM.do_mes(lidas, 1, 202608) == {} and AM.do_mes(lidas, 99, 202610) == {} and AM.do_mes([], 1, 202610) == {}
