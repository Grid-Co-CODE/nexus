"""A conta do bloco Manutenção da Visão do responsável (18/10/2026), pura: as tarefas das OS do Fracttal
(`nexus_os`), os motivos do PCM, as OS de chamado e a programação, por usina. As réguas são as das telas donas e as
decisões do Levi de 18/10: atrasada pela régua do PCM (mais de 10 dias), a semana fechada pela conta do Fechamento (meta
de 85%), o backoffice fora. Dia fixo: quarta, 21/10/2026. Usinas, códigos e pessoas inventados."""
from datetime import date

from nexus.campo import manutencao as M
from nexus.dados import fatos as D

HOJE = date(2026, 10, 21)
FUSIVEL = D.tarefa_chave("troca de fusivel")


def _t(tid, os_, usina=1, prog=20261001, tipo="corretiva", status="em_processo", estado="nao_iniciada", bo=0,
       codigo="THPN-ALT100-INVR1", chave=FUSIVEL, fim=None):
    """Uma linha do fato `fato_tarefa_os`, como a Visão a lê do banco."""
    return {"fracttal_tarefa_id": tid, "os": os_, "fracttal_os_id": 50000 + int(os_), "tarefa_chave": chave,
            "codigo_ativo": codigo, "usina_id": usina, "data_id_programada": prog, "data_id_fim": fim,
            "tipo_tarefa": tipo, "status_os": status, "estado_tarefa": estado, "do_backoffice": bo}


def _m(os_, tarefa="Troca de fusível", codigo="THPN-ALT100-INVR1", motivo="Aguardando material", tira=True,
       origem="nexus", desde="2026-10-15T13:00:00Z"):
    """Uma marca do `motivos.vigentes`, já decifrada."""
    return {"os": str(os_), "codigo": codigo, "tarefa": tarefa, "usina": "Thopen - Altair 1 - SP", "motivo": motivo,
            "tira": tira, "origem_motivo": origem, "desde": desde, "quem_motivo": "Fulana Fictícia"}


def _marcas(*ms):
    return M.marcas_paradas({f"m{i}": m for i, m in enumerate(ms)}, lambda m: 1)


def _usina(tarefas, marcas=(), chamados=()):
    return M.tarefas_por_usina(tarefas, list(marcas), set(chamados), HOJE)[1]


def test_atrasada_e_a_regua_do_pcm():
    r = _usina([_t(1, "100", prog="20261011"),         # há 10 dias: ainda não (o banco pode dar tudo como texto)
                _t(2, 100, prog=20261010),             # há 11 dias: atrasada
                _t(3, 101, prog=20261010)])
    assert (r["os_abertas"], r["atrasadas"], r["atrasadas_os"], r["maior_atraso"]) == (2, 2, 2, 11)
    assert [(x["os"], x["dias"], x["wid"]) for x in r["lista_atrasadas"]] == [(100, 11, 50100), (101, 11, 50101)]


def test_as_exclusoes():
    tarefas = [_t(1, 200, bo=1), _t(2, 201, tipo="zeladoria"), _t(3, 202, tipo="teste"), _t(4, 203),
               _t(5, 204), _t(6, 205), _t(7, 206)]
    marcas = _marcas(_m(204), _m(206, tira=False, origem="nexus"))  # a 206 tem motivo que não tira: segue cobrada
    r = _usina(tarefas, marcas, chamados={203})
    assert (r["os_abertas"], r["atrasadas"]) == (2, 2)            # só a 205 e a 206
    assert {x["os"] for x in r["lista_atrasadas"]} == {205, 206}


def test_marca_sem_codigo_tira_todos_os_ativos_e_casa_sem_acento():
    visual = D.tarefa_chave("inspecao visual")
    tarefas = [_t(1, 300, codigo="THPN-ALT100-INVR1", chave=visual), _t(2, 300, codigo="THPN-ALT100-INVR2", chave=visual)]
    r = _usina(tarefas, _marcas(_m(300, tarefa="Inspeção  Visual", codigo="")))
    assert (r["atrasadas"], r["os_abertas"], r["paradas"]) == (0, 0, 2)


def test_sem_data_programada_nao_atrasa_nem_vence():
    r = _usina([_t(1, 310, prog=None), _t(2, 311, prog="")])
    assert (r["os_abertas"], r["atrasadas"], r["vencem"], r["maior_atraso"]) == (2, 0, 0, None)


def test_vencem_hoje_e_amanha():
    r = _usina([_t(1, 320, prog=20261021), _t(2, 321, prog=20261022), _t(3, 322, prog=20261023)])
    assert (r["vencem"], r["atrasadas"]) == (2, 0)


def test_em_verificacao_conta_como_aberta_e_a_tarefa_finalizada_nao():
    r = _usina([_t(1, 330, status="em_verificacao"), _t(2, 331, estado="finalizada"), _t(3, 332)])
    assert (r["os_abertas"], r["em_verificacao"], r["atrasadas"]) == (2, 1, 2)


def test_paradas_so_com_a_tarefa_viva_e_o_motivo_mais_comum():
    tarefas = [_t(1, 400), _t(2, 401, estado="finalizada"), _t(3, 402), _t(4, 403)]
    marcas = _marcas(_m(400), _m(401), _m(402, motivo="Aguardando cliente"), _m(403, origem="app", tira=False))
    r = _usina(tarefas, marcas)
    assert (r["paradas"], r["motivo_comum"]) == (3, "Aguardando material")
    assert {(x["os"], x["motivo"], x["desde"], x["quem"]) for x in r["lista_paradas"]} == {
        (400, "Aguardando material", date(2026, 10, 15), "Fulana Fictícia"),
        (402, "Aguardando cliente", date(2026, 10, 15), "Fulana Fictícia"),
        (403, "Aguardando material", date(2026, 10, 15), "Fulana Fictícia")}
    # sem o fato no banco não há como saber se a tarefa terminou: toda marca conta, como o painel faz
    assert M.tarefas_por_usina(None, marcas, set(), HOJE)[1]["paradas"] == 4


def test_zeladoria_proxima_vencida_e_ultima():
    z = dict(tipo="zeladoria")
    r = _usina([_t(1, 500, prog=20261025, **z), _t(2, 501, prog=20261018, **z), _t(3, 502, prog=20261030, **z),
                _t(4, 503, status="finalizada", estado="finalizada", fim=20261005, **z),
                _t(5, 504, status="finalizada", estado="finalizada", fim=20261012, **z)])
    assert (r["zeladoria_proxima"], r["zeladoria_vencida"], r["zeladoria_ultima"]) == (
        date(2026, 10, 25), date(2026, 10, 18), date(2026, 10, 12))
    assert r["os_abertas"] == 0                                     # zeladoria tem coluna própria


def _p(usina, semana, dia, status, hora="08:00"):
    return {"usina_id": usina, "data_id_semana": semana, "data_id_programada": dia, "hora_inicio": hora,
            "status_execucao": status}


def test_semana_passada_pela_conta_do_fechamento():
    prog = ([_p(1, 20261012, 20261013, "finalizada")] * 17 + [_p(1, 20261012, 20261014, "nao_iniciada")] * 3
            + [_p(1, 20261005, 20261006, "nao_iniciada")] * 5                        # a semana de antes não entra
            + [_p(1, 20261019, 20261021, "finalizada", "08:00"), _p(1, 20261019, 20261021, "em_progresso", "09:30"),
               _p(1, 20261019, 20261021, "nao_iniciada", "14:00"), _p(1, 20261019, 20261021, "nao_iniciada", "")])
    r = M.semana_por_usina(prog, HOJE, "10:00")[1]
    assert (r["passada"], r["passada_prog"], r["passada_feitas"], r["passada_pct"]) == ("2026-W42", 20, 17, 85.0)
    assert (r["hoje_devidas"], r["hoje_feitas"]) == (2, 1)            # a das 14:00 e a sem hora ainda não contam


def test_usina_sem_programacao_fica_neutra():
    r = M.semana_por_usina([_p(2, 20261019, 20261021, "finalizada")], HOJE, "10:00")
    assert r[2]["passada_pct"] is None and r.get(3) is None
