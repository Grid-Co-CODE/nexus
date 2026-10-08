"""A programação semanal do PCM como fato (`nexus/dados/programacao.py`, passo 6b do desenho Kimball de 08/10/2026).

Tudo com dado inventado e sem rede: a fonte é um arquivo local lido por `nexus.pcm.fonte` e o banco é o `pg_falso`.
"""
import json
from datetime import date, timedelta

import pytest
from pg_falso import ApiPGFalsa

from nexus.dados import fatos, livros
from nexus.dados import programacao as P
from nexus.pcm import fonte

BASE = "http://pg.falso"
USINAS = [{"usina_id": 7, "codigo": "XPT-ALF100", "nome": "Alfa 1"},
          {"usina_id": 8, "codigo": "BET100", "nome": "Beta 1"}, {"usina_id": 9, "codigo": "QWE-BET100"}]
DE_PARA = [{"usina_id": 3, "sistema": "Fracttal · Classificação 1", "chave_externa": "Cliente X - Usina Gama 1 - PA"}]
EQUIPES = [{"equipe_id": 41, "nome": "ZZ Norte 01"}]
PESSOAS = {P.norm_nome("Pessoa Exemplo Um"): 55, P.norm_nome("Pessoa Exemplo Dois"): 56,
           P.norm_nome("Pessoa Homonima"): {60, 61}}
NOMES = ("Pessoa Exemplo Um", "Pessoa Exemplo Dois", "Pessoa Homonima", "Pessoa Sem Ficha")


def _lig():
    return fatos.Ligador(USINAS, DE_PARA, EQUIPES, {})


def _r(**kw):
    """Uma linha planejada como o robô do PCM grava no banco_dados.json."""
    d = {"cliente": "Cliente X", "usina": "Cliente X - Usina Gama 1 - PA", "cluster": "ZZ Norte 01", "tipo": "MPM",
         "dia": "Segunda-feira", "os_id": "15001", "codigo": "XPT-ALF100-INVR1.1", "tarefa": "Inspeção visual",
         "responsavel": "Pessoa Exemplo Dois", "resp_os": "Pessoa Exemplo Um", "criticidade": "18",
         "etiquetas": '["etiqueta"]', "status_bd": "Não Iniciada", "status": "Não Iniciada", "duracao": 1.1,
         "h_ini": "07:30", "h_fim": "08:36", "desloc": 0.5, "reprog": "Não", "vezes": 1, "termo": "Não",
         "paralelo": "Não", "nova_os": "", "solic_orig": "", "rolagem": "", "relatorio": "texto livre com nome",
         "historico": [], "mttr_s": 0, "mttr_h": 0.0, "tempo_total_s": 0, "pausado_s": 0,
         "dataCriacao": "2026-09-15T11:20:32.815891", "dataFinal": "", "dataProgramada": "2026-09-08T07:00:00",
         "statusPai": "Em processo"}
    d.update(kw)
    return d


def _semana(week, linhas, dates=None, gerada="2026-10-02T21:54:41Z"):
    seg = date.fromisocalendar(int(week[:4]), int(week[-2:]), 1)
    dates = dates or {k: (seg + timedelta(days=i)).strftime("%d/%m")
                      for i, k in enumerate(("seg", "ter", "qua", "qui", "sex"))}
    return {"week": week, "num": int(week[-2:]), "dates": dates, "geradaEm": gerada, "rows": linhas,
            "pendentes": [{"os_id": "99999", "tarefa": "não coube"}], "qualidade": []}


def _dados(*semanas):
    return {"geradoEm": "2026-10-08T14:31:09Z", "fonte": "gerar_pcm_json.py (4 semanas)", "semana_ativa": "2026-W41",
            "semanas": list(semanas)}


def _fato(dados, equip=None, pessoas=PESSOAS):
    linhas, rel = P.fato_programacao(dados, _lig(), pessoas, equip, "2026-10-08T12:00:00-03:00")
    return [dict(zip(P.CAB_PROGRAMACAO, l)) for l in linhas], rel, linhas


# ── semana e dia ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_semana_iso_vira_a_segunda_feira():
    assert P.segunda_da_semana("2026-W41") == 20261005
    assert P.segunda_da_semana("2026-W53") == 20261228          # 2026 tem 53 semanas ISO
    assert P.segunda_da_semana("2025-W01") == 20241230          # a semana 1 de 2025 começa em 2024
    assert P.segunda_da_semana("2026-W54") is None and P.segunda_da_semana("semana 41") is None


def test_dia_do_bloco_pelo_dates_com_o_ano_da_semana_e_contradicao_fica_vazia():
    w41 = _semana("2026-W41", [])
    assert P.data_do_bloco(w41, "Segunda-feira") == 20261005
    assert P.data_do_bloco(w41, "Terça-feira (06/10) [NOTURNO]") == 20261006
    # a virada do ano: o dd/mm não tem ano; quem diz o ano é a semana ISO
    w01 = _semana("2025-W01", [])
    assert w01["dates"]["seg"] == "30/12" and P.data_do_bloco(w01, "Segunda-feira") == 20241230
    assert P.data_do_bloco(w01, "Quarta-feira") == 20250101
    # o dates diz outro dia para a segunda: a fonte se contradiz, nenhum dos dois é escolhido
    assert P.data_do_bloco(_semana("2026-W41", [], dates={"seg": "06/10"}), "Segunda-feira") is None
    # semana sem dates (arquivo antigo): a semana ISO e o dia bastam
    assert P.data_do_bloco("2026-W41", "Sexta-feira") == 20261009
    assert P.data_do_bloco(w41, "Feriado") is None and P.data_do_bloco({"week": "x"}, "Segunda-feira") is None


# ── atributos ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_criticidade_vira_duas_colunas():
    assert P.criticidade("Muito alto") == ("Muito alto", None)
    assert P.criticidade(" MÉDIO ") == ("Médio", None) and P.criticidade("medio") == ("Médio", None)
    assert P.criticidade("18") == (None, 18) and P.criticidade(19.0) == (None, 19)
    assert P.criticidade("2,5") == (None, 2.5)
    assert P.criticidade("") == (None, None) and P.criticidade(None) == (None, None)
    assert P.criticidade("urgente") == (None, None) and P.criticidade("-3") == (None, None)


def test_tarefa_chave_igual_no_pcm_e_no_app_e_o_texto_nao_vai():
    """A mesma função vale para o fechamento do App: o texto chega com outra caixa, acento ou espaço."""
    k = P.tarefa_chave("Inspeção  visual do inversor")
    assert k == P.tarefa_chave(" inspecao VISUAL do inversor ") and len(k) == 12
    assert k != P.tarefa_chave("Inspeção visual do tracker")
    assert P.tarefa_chave("") is None and P.tarefa_chave(None) is None


# ── o fato ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_tarefa_partida_em_dois_dias_e_duas_linhas_e_um_primeiro_bloco():
    # o 2º bloco vem ANTES na planilha: o primeiro bloco é o do dia mais cedo, não o da ordem do arquivo
    s = _semana("2026-W41", [_r(dia="Quarta-feira", h_ini="07:30"), _r(dia="Segunda-feira", h_ini="13:00"),
                             _r(os_id="15002", tarefa="Limpeza")])
    f, rel, _ = _fato(_dados(s))
    assert len(f) == 3 and len({x["programacao_id"] for x in f}) == 3
    assert [(x["data_id_programada"], x["primeiro_bloco"]) for x in f[:2]] == [(20261007, 0), (20261005, 1)]
    assert sum(x["primeiro_bloco"] for x in f) == rel["tarefas"] == 2
    assert {x["data_id_semana"] for x in f} == {20261005}


def test_programacao_id_estavel_entre_leituras_e_unico_com_bloco_repetido():
    s = _semana("2026-W41", [_r(), _r(os_id="15002")])
    a, _, _ = _fato(_dados(s))
    b, _, _ = _fato(_dados(_semana("2026-W41", [_r(), _r(os_id="15002")])))
    assert [x["programacao_id"] for x in a] == [x["programacao_id"] for x in b]
    # o mesmo bloco duas vezes na planilha: as duas linhas ficam, com IDs diferentes, e o relatório conta
    f, rel, _ = _fato(_dados(_semana("2026-W41", [_r(), _r()])))
    assert len(f) == 2 and f[0]["programacao_id"] != f[1]["programacao_id"] and rel["blocos_repetidos"] == 1
    assert sum(x["primeiro_bloco"] for x in f) == 1


def test_executada_fora_do_plano_e_pendente_nao_viram_bloco():
    """O robô do PCM põe na semana as tarefas finalizadas que não estavam no plano (foraDoPlano): é execução, outro
    grão. Em 08/10 eram 2.159 de 5.897 linhas; somadas, inflariam as tarefas programadas."""
    fora = _r(os_id="15800", tarefa="Corretiva no campo", foraDoPlano=True, reprog="", vezes=0, status="Finalizados")
    f, rel, _ = _fato(_dados(_semana("2026-W41", [_r(), fora])))
    assert [x["os"] for x in f] == ["15001"] and rel["fora_do_plano"] == 1 and rel["linhas"] == 1
    assert "99999" not in {x["os"] for x in f}                     # a pendente (backlog) também não


def test_usina_pelo_de_para_e_sem_par_pelo_codigo_so_quando_unico():
    s = _semana("2026-W41", [_r(), _r(os_id="2", usina="Cliente X - Nome Novo - PA"),
                             _r(os_id="3", usina="Cliente X - Nome Novo - PA", codigo="BET100-INVR2.4")])
    f, rel, _ = _fato(_dados(s))
    assert [(x["usina_id"], x["usina_ligada_por"]) for x in f] == [
        (3, "de-para do Fracttal"), (7, "código do ativo"), (None, None)]     # BET100 é de duas usinas: não chuta
    assert (rel["usina_por_de_para"], rel["usina_por_codigo"], rel["com"]["usina_id"]) == (1, 1, 2)
    assert "Nome Novo" in rel["sem_usina_exemplos"]


def test_cluster_fora_do_cadastro_fica_vazio_e_aparece():
    f, rel, _ = _fato(_dados(_semana("2026-W41", [_r(), _r(os_id="2", cluster="YY Sul 09")])))
    assert [x["equipe_id"] for x in f] == [41, None] and "YY Sul 09 (1)" in rel["sem_equipe_exemplos"]
    assert rel["pct"]["equipe_id"] == 50.0


def test_pessoa_so_quando_o_nome_e_de_uma_e_nenhum_nome_no_fato():
    s = _semana("2026-W41", [_r(), _r(os_id="2", resp_os="Pessoa Homonima"),
                             _r(os_id="3", resp_os="Pessoa Exemplo Um, Pessoa Exemplo Dois"),
                             _r(os_id="4", resp_os="Pessoa Sem Ficha", responsavel="")])
    f, rel, linhas = _fato(_dados(s))
    assert [x["pessoa_id_tecnico"] for x in f] == [55, None, None, None]
    assert [x["pessoa_id_responsavel"] for x in f] == [56, 56, 56, None]
    assert rel["nomes_tecnico"] == {"distintos": 4, "ligados": 1}
    # varredura: nem o fato nem o relatório levam nome, tarefa, relatório ou etiqueta
    texto = json.dumps(linhas, ensure_ascii=False) + json.dumps(rel, ensure_ascii=False)
    for proibido in NOMES + ("Inspeção visual", "texto livre com nome", "etiqueta"):
        assert proibido.lower() not in texto.lower(), proibido
    assert P.fato_programacao(_dados(s), _lig(), None, None, "t")[0][0][P.CAB_PROGRAMACAO.index("pessoa_id_tecnico")] \
        is None                                                     # sem o cadastro decifrado, ninguém liga


def test_medidas_em_minutos_indicadores_e_dominios():
    s = _semana("2026-W41", [
        _r(),
        _r(os_id="2", duracao=0.17, desloc=-1, reprog="Sim", vezes=3, termo="Sim", paralelo="Sim",
           nova_os="Sim (via Solic #1234)", rolagem="↻ de Segunda-feira (05/10) · 1ª rolagem", status="Finalizados",
           statusPai="Verificação", criticidade="Muito alto", dataFinal="2026-10-06T22:40:46.816068", h_ini="7:05"),
        _r(os_id="3", status="Cancelada?", statusPai="", reprog="", h_ini="25:00")])
    a, b, c = _fato(_dados(s))[0]
    assert (a["duracao_min"], a["deslocamento_min"], b["duracao_min"], b["deslocamento_min"]) == (66, 30, 10, None)
    assert (a["reprogramada"], a["termo"], a["paralelo"], a["nova_os"], a["rolada"]) == (0, 0, 0, 0, 0)
    assert (b["reprogramada"], b["termo"], b["paralelo"], b["nova_os"], b["rolada"]) == (1, 1, 1, 1, 1)
    assert c["reprogramada"] is None                                 # a fonte não disse
    assert (a["vezes_programada_qtd"], b["vezes_programada_qtd"]) == (1, 3)
    assert (a["criticidade_rotulo"], a["criticidade_pts"], b["criticidade_rotulo"], b["criticidade_pts"]) == (
        None, 18, "Muito alto", None)
    assert (a["status_execucao"], a["status_os"], b["status_execucao"], b["status_os"]) == (
        "nao_iniciada", "em_processo", "finalizada", "em_verificacao")
    assert (c["status_execucao"], c["status_os"]) == (None, None)
    assert (a["hora_inicio"], b["hora_inicio"], c["hora_inicio"]) == ("07:30", "07:05", None)
    assert (a["data_id_criacao_os"], a["data_id_fim_execucao"], b["data_id_fim_execucao"]) == (20260915, None, 20261006)
    assert (a["tipo_tarefa"], a["codigo_ativo"], a["os"]) == ("MPM", "XPT-ALF100-INVR1.1", "15001")
    assert (a["semana_gerada_em"], a["lido_em"]) == ("2026-10-02T21:54:41Z", "2026-10-08T12:00:00-03:00")


def test_data_com_fuso_vira_o_dia_de_brasilia():
    s = _semana("2026-W41", [_r(dataCriacao="2026-10-01T02:30:00Z", dataFinal="2026-10-01T02:30:00-03:00")])
    f = _fato(_dados(s))[0][0]
    assert (f["data_id_criacao_os"], f["data_id_fim_execucao"]) == (20260930, 20261001)


def test_arquivo_antigo_sem_rolagem_nem_nova_os_fica_vazio_e_nao_zero():
    r = _r()
    del r["rolagem"], r["nova_os"]
    f = _fato(_dados(_semana("2026-W38", [r])))[0][0]
    assert (f["rolada"], f["nova_os"]) == (None, None)


def test_equipamento_pela_funcao_do_modulo_e_vazio_sem_ela():
    s = _semana("2026-W41", [_r(), _r(os_id="2", codigo="sem código")])
    ids = {"XPT-ALF100-INVR1.1": 2 ** 52 - 1}
    assert [x["equipamento_id"] for x in _fato(_dados(s), equip=ids.get)[0]] == [2 ** 52 - 1, None]
    assert [x["equipamento_id"] for x in _fato(_dados(s), equip=lambda c: (12, "foto"))[0]] == [12, 12]
    assert [x["equipamento_id"] for x in _fato(_dados(s))[0]] == [None, None]
    assert _fato(_dados(s))[0][1]["codigo_ativo"] == "SEMCÓDIGO"                 # canônico: maiúsculo, sem espaço


def test_relatorio_conta_semanas_e_percentuais_com_uma_casa():
    s1 = _semana("2026-W40", [_r(), _r(os_id="2", cluster="YY Sul 09"), _r(os_id="3", cluster="YY Sul 09")])
    s2 = _semana("2026-W41", [_r()])
    _, rel, _ = _fato(_dados(s2, s1))
    assert rel["semanas"] == ["2026-W40", "2026-W41"] and rel["por_semana"] == {"2026-W40": 3, "2026-W41": 1}
    assert rel["pct"]["equipe_id"] == 50.0 and rel["pct"]["data_id_programada"] == 100.0
    assert rel["fonte_gerado_em"] == "2026-10-08T14:31:09Z"
    linhas, vazio = P.fato_programacao(None, _lig(), PESSOAS, None, "t")
    assert linhas == [] and (vazio["linhas"], vazio["semanas"], vazio["pct"]["usina_id"]) == (0, [], 0.0)


def test_linha_de_qualidade_pelo_nome_da_coluna():
    _, rel, _ = _fato(_dados(_semana("2026-W41", [_r(), _r(os_id="2", cluster="YY Sul 09")])))
    q = dict(zip(fatos.CAB_QUALIDADE, P.linha_qualidade(rel, fatos.CAB_QUALIDADE, None, "agora")))
    assert (q["fato"], q["linhas"], q["com_data"], q["com_equipe"], q["pct_equipe"]) == ("programacao", 2, 2, 1, 50.0)
    assert q["origem_atualizada_em"] == "2026-10-08T14:31:09Z" and q["gerado_em"] == "agora"
    # o cabeçalho novo do desenho (equipamento e extra) também se preenche; coluna desconhecida fica vazia
    cab = ["fato", "com_equipamento", "pct_equipamento", "extra", "coluna_que_nao_existe"]
    q2 = dict(zip(cab, P.linha_qualidade(rel, cab, None, "agora")))
    assert q2["com_equipamento"] == 0 and q2["coluna_que_nao_existe"] is None
    assert json.loads(q2["extra"])["tarefas"] == 2


# ── a fonte, sem rede ─────────────────────────────────────────────────────────────────────────────────────────────
def test_le_pela_fonte_do_pcm_de_um_arquivo_local(tmp_path):
    arq = tmp_path / "banco_dados.json"
    arq.write_text(json.dumps(_dados(_semana("2026-W41", [_r()]))), encoding="utf-8")
    leit = fonte.ler({"TESTING": True, "NEXUS_PCM_FONTE": str(arq)})
    f, rel, _ = _fato(leit.dados)
    assert len(f) == 1 and rel["linhas"] == 1
    assert fonte.ler({"TESTING": True}).dados is None               # nos testes, sem a chave, não vai à rede


# ── gravar por semana (só com a decisão do Levi) ──────────────────────────────────────────────────────────────────
def test_mesclar_troca_so_a_semana_da_fonte_e_guarda_as_outras():
    """O que o `pg_falso` devolve depois de gravar (tudo como texto, como_texto=True) volta ao tipo, e a semana que a
    fonte já não tem (a fonte guarda 4) continua no banco."""
    velho, _, l_velho = _fato(_dados(_semana("2026-W38", [_r()]), _semana("2026-W41", [_r(), _r(os_id="2")])))
    api = ApiPGFalsa(como_texto=True)
    livros.publicar(P.LIVRO, P.NOME_LIVRO, {P.ABA: (P.CAB_PROGRAMACAO, l_velho)}, base=BASE, token="t", sessao=api)
    no_banco = livros.ler(BASE, api, P.LIVRO, P.ABA)
    assert no_banco[0]["data_id_semana"] == "20260914"              # o banco devolveu texto
    _, _, l_novo = _fato(_dados(_semana("2026-W41", [_r(os_id="3")])))
    m = [dict(zip(P.CAB_PROGRAMACAO, l)) for l in P.mesclar_semanas(no_banco, l_novo)]
    assert [(x["data_id_semana"], x["os"]) for x in m] == [(20260914, "15001"), (20261005, "3")]
    assert m[0]["usina_id"] == 3 and m[0]["primeiro_bloco"] == 1 and m[0]["duracao_min"] == 66
    assert m[0]["programacao_id"] == velho[0]["programacao_id"]
    # fonte vazia não apaga nada; linha do banco sem semana não é descartada
    assert len(P.mesclar_semanas(no_banco, [])) == 3
    sem = dict(no_banco[0], data_id_semana=None)
    assert len(P.mesclar_semanas([sem], l_novo)) == 2


def test_gravacao_redonda_no_banco_falso_preserva_ids_grandes_e_hora_em_texto():
    """O equipamento_id tem 52 bits: tem de voltar exato do xlsx; a hora '07:30' não pode virar fração de dia."""
    _, _, l = _fato(_dados(_semana("2026-W41", [_r()])), equip=lambda c: 2 ** 52 - 1)
    api = ApiPGFalsa()
    r = livros.publicar(P.LIVRO, P.NOME_LIVRO, {P.ABA: (P.CAB_PROGRAMACAO, l)}, base=BASE, token="t", sessao=api)
    assert r == {P.ABA: 1}
    x = livros.ler(BASE, api, P.LIVRO, P.ABA)[0]
    assert x["equipamento_id"] == 2 ** 52 - 1 and x["hora_inicio"] == "07:30" and x["data_id_programada"] == 20261005
    assert P.LIVRO.startswith("nexus_") and P.ABA.startswith("fato_")


def test_impressao_digital_ignora_a_hora_da_leitura_e_pega_a_mudanca():
    s = lambda **kw: _dados(_semana("2026-W41", [_r(**kw), _r(os_id="2")]))
    a = P.fato_programacao(s(), _lig(), PESSOAS, None, "08:00")[0]
    b = P.fato_programacao(s(), _lig(), PESSOAS, None, "09:00")[0]
    c = P.fato_programacao(s(status="Finalizados"), _lig(), PESSOAS, None, "09:00")[0]
    assert P.sha_linhas(a) == P.sha_linhas(b) == P.sha_linhas(list(reversed(b))) != P.sha_linhas(c)


def test_cabecalho_sem_nome_e_com_unidade_nas_medidas():
    assert len(P.CAB_PROGRAMACAO) == len(set(P.CAB_PROGRAMACAO))
    assert not any(c in P.CAB_PROGRAMACAO for c in ("tarefa", "resp_os", "responsavel", "relatorio", "etiquetas"))
    for c, unidade, soma in P.MEDIDAS:
        assert c in P.CAB_PROGRAMACAO and soma in ("aditiva", "semi", "nao"), c
        assert c.endswith(("_min", "_qtd", "_pts")) or unidade == "1/0", c
    assert P.TIPO == "snapshot_periodico" and P.CHAVE == ("programacao_id",) and P.GRAO.startswith("1 linha")


@pytest.mark.parametrize("v,esperado", [("Sim", 1), ("sim (BD)", 1), ("Não", 0), ("nao", 0), ("", None), (None, None)])
def test_sim_nao(v, esperado):
    assert P._sim_nao(v) == esperado


# ── a mescla por semana e a carga única do histórico (decisão 7, 08/10/2026) ─────────────────────────────────────────
def test_ids_dos_blocos_sao_os_do_fato_e_mudam_com_o_dia():
    """A carga única compara versões do arquivo pelos MESMOS IDs do fato, sem montá-lo."""
    s = _semana("2026-W41", [_r(), _r(os_id="2"), _r(), _r(foraDoPlano=True, os_id="9")])
    f, _rel, _ = _fato(_dados(s))
    assert P.ids_dos_blocos(s) == [x["programacao_id"] for x in f]           # inclusive o bloco repetido
    movido = _semana("2026-W41", [_r(dia="Terça-feira"), _r(os_id="2"), _r()])
    assert P.ids_dos_blocos(movido)[0] not in P.ids_dos_blocos(s) and P.ids_dos_blocos(movido)[1] in P.ids_dos_blocos(s)


def test_resumo_das_linhas_do_fato_mesclado():
    _, rel_fonte, l41 = _fato(_dados(_semana("2026-W41", [_r(), _r(os_id="2", cluster="YY Sul 09")])))
    _, _, l38 = _fato(_dados(_semana("2026-W38", [_r()])))
    m = P.mesclar_semanas([dict(zip(P.CAB_PROGRAMACAO, l)) for l in l38], l41)
    r = P.resumo_das_linhas(m, rel_fonte)
    assert r["semanas"] == ["2026-W38", "2026-W41"] and r["por_semana"] == {"2026-W38": 1, "2026-W41": 2}
    assert (r["linhas"], r["tarefas"], r["ids_repetidos"], r["com"]["equipe_id"]) == (3, 3, 0, 2)
    assert r["sem_equipe_exemplos"] == rel_fonte["sem_equipe_exemplos"]       # só o arquivo sabe o nome
    assert P.resumo_das_linhas(m + [m[0]])["ids_repetidos"] == 1
    assert P.semana_iso(20261005) == "2026-W41" and P.semana_iso("20241230") == "2025-W01"
    assert P.semana_iso(None) is None and P.semana_iso(20261399) is None


def test_formato_antigo_do_painel_vira_o_atual_sem_inventar():
    """De 28/05 a 12/06/2026 o arquivo dizia "Semana 21", a usina com UF vinha em `ativo` e a termografia e a
    prioridade tinham outro nome. O 1º arquivo dizia "18–22 Mai 2025", mas 18/05/2025 foi um domingo: é a de 2026."""
    from ferramentas import carregar_programacao_historica as H
    linha = _r(usina="Cliente X - Usina Gama 1", ativo="Cliente X - Usina Gama 1 - PA", termografia="Sim",
               prioridade="Alto")
    for c in ("criticidade", "termo"):                 # o formato antigo não tinha estas chaves
        linha.pop(c)
    antiga = {"week": "Semana 21", "label": "Semana 21 · 18–22 Mai 2025",
              "dates": {"seg": 18, "ter": 19, "qua": 20, "qui": 21, "sex": 22}, "rows": [linha]}
    s = H.formato_atual(antiga, 2026)
    assert s["week"] == "2026-W21" and s["dates"] is None
    assert antiga["rows"][0]["usina"] == "Cliente X - Usina Gama 1"            # a original não muda
    f, _rel, _ = _fato({"semanas": [s]})
    assert (f[0]["data_id_semana"], f[0]["data_id_programada"], f[0]["usina_id"]) == (20260518, 20260518, 3)
    assert (f[0]["usina_ligada_por"], f[0]["termo"], f[0]["criticidade_rotulo"]) == ("de-para do Fracttal", 1, "Alto")
    s22 = H.formato_atual({"week": "Semana 22", "label": "Semana 22 · 25–29 Mai 2026",
                           "dates": {"seg": 25, "mes": "Mai", "ano": 2026}, "rows": []})
    assert s22["week"] == "2026-W22"
    atual = _semana("2026-W41", [_r()])
    assert H.formato_atual(atual) is atual and H.formato_atual({"week": "outra coisa"}) is None


def test_escolha_da_versao_a_ultima_que_so_perdeu_blocos_depois_de_fechada():
    """A W38 (14 a 20/09) fecha na segunda 21/09, 00:00 de Brasília. Depois disso a semana só pode PERDER bloco (OS
    cancelada); bloco novo ou mudado de dia é regeração (a W25 em 29/06, a W35 em 31/08) e não conta. Regeração que
    se desfaz (a W32 em 14/08) não congela a semana: vale a última versão que só perdeu blocos."""
    from datetime import datetime, timezone
    from ferramentas import carregar_programacao_historica as H
    brt = timezone(timedelta(hours=-3))
    ts = lambda dia, hora=12: int(datetime(2026, 9, dia, hora, tzinfo=brt).timestamp())    # noqa: E731
    e = H.Escolha("2026-W38")
    e.ver(0, ts(10), ["a", "b"])
    e.ver(1, ts(20, 23), ["a", "b", "c"])        # domingo 23h: ainda é o fim da semana
    e.ver(2, ts(25), ["a", "b"])                 # perdeu "c" (OS cancelada): vale
    e.ver(3, ts(27), ["a", "b"])
    assert e.escolhida == 3 and e.regra.startswith("a última versão") and e.fim_i == 1
    e.ver(4, ts(28), ["a", "z"])                 # "z" não existia no fim da semana: regerada, não conta
    e.ver(5, ts(29), ["a", "z"])
    assert (e.escolhida, e.regerou_i, e.regerou, e.ultima) == (3, 4, 1, 5) and e.regra.startswith("mudou depois")
    e.ver(6, ts(30), ["a"])                      # a regeração se desfez: a semana voltou a só ter perdido blocos
    assert e.escolhida == 6 and e.regerou_i == 4 and e.regra.startswith("a última versão")
    so_depois = H.Escolha("2026-W38")
    so_depois.ver(7, ts(28), ["x"])
    so_depois.ver(8, ts(29), ["x", "y"])
    assert so_depois.escolhida == 8 and so_depois.regra.startswith("sem versão de dentro")


def test_carga_historica_pelo_git_de_ponta_a_ponta(tmp_path):
    """Um repositório git de mentira com 5 versões do banco_dados.json: a ferramenta lê o histórico, escolhe a versão
    de cada semana e monta o fato com o mesmo código da carga."""
    import os
    import shutil
    import subprocess
    from datetime import datetime, timezone
    from ferramentas import carregar_programacao_historica as H
    if shutil.which("git") is None:
        pytest.skip("sem git nesta máquina")
    repo = tmp_path / "pcm"
    repo.mkdir()
    brt = timezone(timedelta(hours=-3))

    def git(*a, quando=None):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@t")
        if quando:
            env.update(GIT_AUTHOR_DATE=quando.isoformat(), GIT_COMMITTER_DATE=quando.isoformat())
        subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, env=env)
    git("init", "-q", "-b", "main")
    w38 = lambda *oss: _semana("2026-W38", [_r(os_id=o) for o in oss])         # noqa: E731
    w39 = _semana("2026-W39", [_r(os_id="d")])
    antiga = {"week": "Semana 37", "label": "Semana 37 · 7–11 Set 2026", "dates": {"seg": 7, "ano": 2026},
              "rows": [_r(os_id="v", ativo="Cliente X - Usina Gama 1 - PA")]}
    versoes = [(datetime(2026, 9, 10, 12, tzinfo=brt), [w38("a", "b"), antiga]),
               (datetime(2026, 9, 20, 23, tzinfo=brt), [w38("a", "b", "c")]),
               (datetime(2026, 9, 25, 12, tzinfo=brt), [w38("a", "b"), w39]),          # perdeu "c": vale
               (datetime(2026, 10, 2, 12, tzinfo=brt), [w38("a", "z"), w39]),          # regerada depois de fechada
               (datetime(2026, 10, 3, 12, tzinfo=brt), [w39])]
    for quando, semanas in versoes:
        (repo / H.ARQUIVO).write_text(json.dumps({"geradoEm": quando.isoformat(), "semanas": semanas}),
                                      encoding="utf-8")
        git("add", H.ARQUIVO)
        git("commit", "-q", "-m", "dados", quando=quando)
    vs = H.versoes(repo)
    assert len(vs) == 5 and vs[0]["ts"] < vs[-1]["ts"]
    esc = H.escolhas_por_semana(H.varrer(repo, vs))
    assert set(esc) == {"2026-W37", "2026-W38", "2026-W39"}
    assert esc["2026-W38"].escolhida == 2 and esc["2026-W38"].regerou_i == 3
    assert esc["2026-W39"].escolhida == 4 and esc["2026-W37"].formato == "antigo"
    dados = H.semana_da_versao(repo, vs[2], "2026-W38")
    f, _rel, _ = _fato(dados)
    assert sorted(x["os"] for x in f) == ["a", "b"] and {x["data_id_semana"] for x in f} == {20260914}
    d37 = H.semana_da_versao(repo, vs[0], "2026-W37", "antigo")
    f37, _rel, _ = _fato(d37)
    assert (f37[0]["data_id_semana"], f37[0]["usina_id"]) == (20260907, 3)


def test_linha_que_nao_mudou_guarda_o_lido_em_do_banco():
    """A API guarda o histórico de cada linha que muda: a hora da leitura não pode fazer as ~3,5 mil linhas do arquivo
    mudarem a cada gravação. Só a linha que mudou (aqui, o status da OS 2) ganha o lido_em novo."""
    _, _, antes = _fato(_dados(_semana("2026-W41", [_r(), _r(os_id="2")])))
    no_banco = [dict(zip(P.CAB_PROGRAMACAO, l)) for l in antes]
    agora, _ = P.fato_programacao(_dados(_semana("2026-W41", [_r(), _r(os_id="2", status="Finalizados")])), _lig(),
                                  PESSOAS, None, "13:00")
    m = P.manter_lido_em(P.mesclar_semanas(no_banco, agora), no_banco)
    i_os, i_lido = P.CAB_PROGRAMACAO.index("os"), P.CAB_PROGRAMACAO.index("lido_em")
    assert {l[i_os]: l[i_lido] for l in m} == {"15001": "2026-10-08T12:00:00-03:00", "2": "13:00"}
    assert P.sha_linhas(m) == P.sha_linhas(agora)                              # o lido_em não entra no sha
    assert P.manter_lido_em(agora, []) == agora                                 # sem banco, nada muda
