"""As tarefas das OS do Fracttal no banco (18/10/2026, Levi: "pegando tudo do Fracttal ou Nexus, sem fontes
externas!"): o fato `nexus_os · fato_tarefa_os`, puro, que a Visão do responsável lê no bloco Manutenção. Uma linha por
tarefa (o REST dá uma linha por tarefa e às vezes repete a página), sem pessoa nem texto: o responsável da OS só vira
a marca 1/0 do backoffice, pelo HMAC. Usinas, códigos e pessoas inventados."""
import hashlib

import pytest

from nexus.dados import equipamento
from nexus.dados import fato_tarefa_os as F
from nexus.dados import fatos as D
from nexus.dados.fato_ronda import GraoDuplicado
from nexus.pcm import motivos

USINAS = [{"usina_id": 1, "nome": "Altair", "codigo": "THPN-ALT100"},
          {"usina_id": 3, "nome": "Coração 1", "codigo": "THPN-COR100"}]
DE_PARA = [{"usina_id": 1, "sistema": "Fracttal · Classificação 1", "chave_externa": "Thopen - Altair 1 - SP"}]
DIM = equipamento.indice([{"equipamento_id": 900, "codigo": "THPN-ALT100-INVR1", "na_foto": 1}])
CHAVE = "chave-hmac-de-teste"


def _w(tarefa, folio, st, estado="NO_STARTED", tipo="Corretiva", prog="2026-10-01T10:00:00+00:00",
       criada="2026-09-20T12:00:00+00:00", fim=None, site="Thopen - Altair 1 - SP", code="THPN-ALT100-INVR1",
       desc="Troca de fusível", dur=5400, resp="Fulana Responsável", pessoa="Ciclano Técnico",
       loc="// Thopen/ Thopen - Altair 1 - SP/ Cabine 1/ "):
    """Uma linha do REST `work_orders`, com todos os campos que o fato lê e os que ele NÃO pode levar (pessoa, texto)."""
    return {"id_work_orders_tasks": tarefa, "wo_folio": str(folio), "id_work_order": 50000 + folio,
            "id_status_work_order": str(st), "task_status": estado, "tasks_log_task_type_main": tipo,
            "date_maintenance": prog, "creation_date": criada, "final_date": fim, "wo_final_date": fim,
            "code": code, "groups_1_description": site, "description": desc, "tasks_duration": dur,
            "user_assigned": resp, "personnel_description": pessoa, "task_note": "observação do técnico",
            "parent_description": loc}


def _lig():
    return D.Ligador(USINAS, DE_PARA, [], {})


def _por_tarefa(linhas):
    return {r[0]: dict(zip(F.CAB_TAREFA_OS, r)) for r in linhas}


def test_uma_linha_por_tarefa_com_os_ids_e_sem_pessoa():
    rows = [_w(701, 16001, 1, estado="STARTED"),
            _w(701, 16001, 1, estado="STARTED"),                                   # a página repetida do REST
            _w(702, 16002, 2, estado="DONE", tipo="Preventiva", desc="MPM - Inspeção visual", dur=None),
            _w(703, 16003, 4)]                                                      # cancelada: fica fora
    linhas, rel = F.linhas(rows, _lig(), DIM, set(), CHAVE)
    d = _por_tarefa(linhas)
    assert list(d) == [701, 702]
    assert rel["lidas"] == 4 and rel["repetidas"] == 1
    assert d[701] == {
        "fracttal_tarefa_id": 701, "os": 16001, "fracttal_os_id": 66001,
        "tarefa_chave": hashlib.sha1("troca de fusivel".encode()).hexdigest()[:12],
        "codigo_ativo": "THPN-ALT100-INVR1", "equipamento_id": 900, "equipamento_ligado_por": "foto do Fracttal",
        "usina_id": 1, "usina_ligada_por": "de-para do Fracttal", "site_fracttal": "Thopen - Altair 1 - SP",
        "data_id_criacao": 20260920, "data_id_programada": 20261001, "data_id_fim": None,
        "tipo_tarefa": "corretiva", "status_os": "em_processo", "estado_tarefa": "em_progresso",
        "do_backoffice": 0, "duracao_min": 90}
    assert (d[702]["tipo_tarefa"], d[702]["status_os"], d[702]["estado_tarefa"], d[702]["duracao_min"]) == (
        "preventiva", "em_verificacao", "finalizada", None)
    # nada de pessoa, do nome da tarefa nem da nota (a API do banco tem leitura aberta)
    texto = str(linhas)
    assert "Fulana" not in texto and "Ciclano" not in texto and "fusível" not in texto and "observação" not in texto


def test_os_dominios_e_o_que_fica_fora_deles():
    rows = [_w(711, 16011, 3, estado="DONE", tipo="Zeladoria", fim="2026-10-05T18:00:00+00:00"),
            _w(712, 16012, 1, estado="PAUSED", tipo="Corretiva Emergencial"),
            _w(713, 16013, 1, estado="NOT_STARTED", tipo="Religamento Remoto"),
            _w(714, 16014, 1, estado="IN_PROGRESS", tipo="Inspeção"),
            _w(715, 16015, 1, estado="ALGO_NOVO", tipo="Tipo que não existe")]
    linhas, rel = F.linhas(rows, _lig(), DIM, set(), CHAVE)
    d = _por_tarefa(linhas)
    assert (d[711]["tipo_tarefa"], d[711]["status_os"], d[711]["data_id_fim"]) == ("zeladoria", "finalizada", 20261005)
    assert (d[712]["tipo_tarefa"], d[712]["estado_tarefa"]) == ("corretiva_emergencial", "pausada")
    assert (d[713]["tipo_tarefa"], d[713]["estado_tarefa"]) == ("religamento_remoto", "nao_iniciada")
    assert (d[714]["tipo_tarefa"], d[714]["estado_tarefa"]) == ("inspecao", "em_progresso")
    # fora do domínio vira vazio e conta (regra 4: nunca o texto cru no lugar do domínio)
    assert (d[715]["tipo_tarefa"], d[715]["estado_tarefa"]) == (None, None)
    assert rel["fora_do_dominio"] == {"tipo_tarefa": 1, "estado_tarefa": 1}


def test_dia_de_brasilia():
    rows = [_w(721, 16021, 1, criada="2026-10-10T02:30:00+00:00", prog="2026-10-15T02:00:00+00:00"),
            _w(722, 16022, 1, prog="")]
    d = _por_tarefa(F.linhas(rows, _lig(), DIM, set(), CHAVE)[0])
    assert d[721]["data_id_criacao"] == 20261009          # 02:30Z é o dia 09 em Brasília
    assert d[721]["data_id_programada"] == 20261014
    assert d[722]["data_id_programada"] is None            # sem Data Programada: vazio, nunca um dia inventado


def test_a_ligacao_nao_chuta():
    rows = [_w(731, 16031, 1),                                                     # o site está no de-para
            _w(732, 16032, 1, site="Coração", code="THPN-COR100-INVR2"),            # pelo código de uma usina só
            _w(733, 16033, 1, site="Usina Nova - XX", code="ATIVO SEM CODIGO")]     # nem um nem outro
    linhas, rel = F.linhas(rows, _lig(), DIM, set(), CHAVE)
    d = _por_tarefa(linhas)
    assert (d[731]["usina_id"], d[731]["usina_ligada_por"]) == (1, "de-para do Fracttal")
    assert (d[732]["usina_id"], d[732]["usina_ligada_por"]) == (3, "código do ativo")
    assert (d[733]["usina_id"], d[733]["usina_ligada_por"], d[733]["site_fracttal"]) == (None, None, "Usina Nova - XX")
    # o código válido fora da dimensão liga com o ID e diz isso; o código que não é de equipamento não liga
    assert d[732]["equipamento_id"] and d[732]["equipamento_ligado_por"] == equipamento.FORA_DA_DIMENSAO
    assert (d[733]["equipamento_id"], d[733]["equipamento_ligado_por"]) == (None, None)
    assert rel["sem_usina"] == 1 and rel["sem_equipamento"] == 1


def test_do_backoffice_pelo_hmac():
    rows = [_w(741, 16041, 1, resp="Beltrana do Backoffice"), _w(742, 16042, 1, resp="Outra Pessoa")]
    bo = {motivos.nome_hmac(CHAVE, "beltrana do backoffice")}       # a lista grava o nome normalizado
    linhas, rel = F.linhas(rows, _lig(), DIM, bo, CHAVE)
    d = _por_tarefa(linhas)
    assert (d[741]["do_backoffice"], d[742]["do_backoffice"]) == (1, 0) and rel["backoffice"] == 1
    # sem a chave HMAC ninguém é do backoffice, e o relatório diz que não deu para saber
    linhas, rel = F.linhas(rows, _lig(), DIM, bo, None)
    assert [r[F.CAB_TAREFA_OS.index("do_backoffice")] for r in linhas] == [0, 0] and rel["backoffice"] is None
    assert "Beltrana" not in str(linhas)


def test_conferir_grao_pega_chave_repetida_ou_vazia():
    linhas, _ = F.linhas([_w(751, 16051, 1), _w(752, 16052, 1)], _lig(), DIM, set(), CHAVE)
    F.conferir_grao(linhas)
    with pytest.raises(GraoDuplicado):
        F.conferir_grao(linhas + [list(linhas[0])])
    vazia = list(linhas[0])
    vazia[0] = None
    with pytest.raises(GraoDuplicado):
        F.conferir_grao([vazia])



# ── o radar da usina trocada (20/10/2026) ────────────────────────────────────────────────────────────────────
# O programador do PCM: a OS de "Apolo - Iramaia II - BA" aparecia como Ibipeba no App e no programador. Os ativos ficam
# na localização de Iramaia II, mas a Classificação 1 deles (a "usina" do robô do PCM, do App e do Ligador daqui) diz
# Ibipeba. A mesma linha do REST traz os dois: o radar compara, ligando cada nome ao Registro mestre pelo de-para.
USINAS_RADAR = USINAS + [{"usina_id": 7, "nome": "Usina Sete", "codigo": None},
                         {"usina_id": 8, "nome": "Usina Oito", "codigo": None}]
DE_PARA_RADAR = DE_PARA + [{"usina_id": 7, "sistema": "Fracttal · Classificação 1", "chave_externa": "Cliente X - Sete 2 - BA"},
                           {"usina_id": 7, "sistema": "Fracttal · Classificação 1", "chave_externa": "Cliente X - Sete II - BA"},
                           {"usina_id": 8, "sistema": "Fracttal · Classificação 1", "chave_externa": "Cliente X - Oito - BA"}]
LOC_SETE = "// Cliente X/ Cliente X - Sete II - BA/ Cabine 1/ "


def test_radar_da_classificacao_1_de_outra_usina():
    lig = D.Ligador(USINAS_RADAR, DE_PARA_RADAR, [], {})
    rows = [_w(1, 16341, 1, site="Cliente X - Oito - BA", code="CLX-STE200-NBRK1", loc=LOC_SETE),
            _w(2, 16341, 1, site="Cliente X - Oito - BA", code="CLX-STE200-INFC1-SDRN1",
               loc="// Cliente X/ Cliente X - Sete II - BA/ Infraestrutura Civil/ "),
            _w(3, 16403, 1, site="Cliente X - Oito - BA", code="CLX-STE200-NBRK1", loc=LOC_SETE),   # o mesmo ativo
            # a mesma usina com outro nome (os dois ligam ao 7): não é troca
            _w(4, 16341, 1, site="Cliente X - Sete 2 - BA", code="CLX-STE200-SSEG1", loc=LOC_SETE),
            # o hífen sem espaço é o mesmo nome (o `_norm` das Ligações)
            _w(5, 16400, 1, code="THPN-ALT100-INVR2", loc="// Thopen/ Thopen - Altair 1- SP/ Cabine/ "),
            # um dos nomes não liga: a conferir, não "trocada"
            _w(6, 16401, 1, code="THPN-ALT100-INVR3", loc="// Thopen/ Thopen - Altair 1 - MT/ Cabine/ "),
            _w(7, 16402, 1, site="Usina Teste", code="TESTE100-INFC1", loc="// Teste/ teste1/ "),     # teste fica fora
            _w(8, 16404, 1, code="THPN-ALT100-INVR4", loc="// Thopen/ "),     # só o cliente: não tem usina para comparar
            _w(9, 16405, 2, site="", code="THPN-ALT100-INVR5", loc=LOC_SETE)]        # sem Classificação 1: sem usina, já conta
    _, rel = F.linhas(rows, lig, DIM, set(), CHAVE)
    assert rel["usina_trocada"] == [
        {"classificacao_1": "Cliente X - Oito - BA", "localizacao": "Cliente X - Sete II - BA", "certeza": "trocada",
         "ativos": ["CLX-STE200-INFC1-SDRN1", "CLX-STE200-NBRK1"], "n_ativos": 2, "n_tarefas": 3, "os": [16341, 16403]},
        {"classificacao_1": "Thopen - Altair 1 - SP", "localizacao": "Thopen - Altair 1 - MT", "certeza": "conferir",
         "ativos": ["THPN-ALT100-INVR3"], "n_ativos": 1, "n_tarefas": 1, "os": [16401]}]
    # na qualidade: as contagens (que a tela mostra como as outras) e a lista, no `extra`
    import json
    out, rel = F.linhas(rows, lig, DIM, set(), CHAVE)
    q = dict(zip(D.CAB_QUALIDADE, F.linha_qualidade(out, rel, "2026-10-20T12:00:00", "2026-10-20T12:00:00")))
    ex = json.loads(q["extra"])
    assert ex["usina_trocada_ativos"] == 2 and ex["usina_a_conferir_ativos"] == 1
    assert ex["usina_trocada"] == rel["usina_trocada"]
