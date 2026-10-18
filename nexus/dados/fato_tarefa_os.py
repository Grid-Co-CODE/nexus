"""O fato das tarefas das OS do Fracttal (18/10/2026): `nexus_os · fato_tarefa_os`, com os IDs do Nexus. Puro: quem
lê o Fracttal e grava é `nexus/campo/tarefas_os.py`.

Levi, 18/10/2026, ao trazer para a Visão do responsável o que um supervisor tinha no painel próprio (OS abertas,
atrasadas, zeladoria): "pegando tudo do Fracttal ou Nexus, sem fontes externas!". Até aqui as telas do PCM liam as
tarefas do `gestao_pcm.json`, que o robô do PCM regrava no GitHub dele; este fato é a mesma informação lida pelo
próprio Nexus e guardada no banco, para qualquer tela ligar por ID.

Grão: 1 linha = 1 tarefa de OS (o REST `work_orders` dá uma linha por tarefa: OS × ativo × tarefa). Entram as tarefas
das OS em processo e em verificação (tudo o que está aberto agora) e as do tipo Zeladoria finalizadas nos últimos 90
dias (para a "última zeladoria feita"). A chave é o id da tarefa no Fracttal: o REST às vezes devolve a mesma página
duas vezes (o motor do PCM deduplica pelo mesmo id), e duas tarefas irmãs de mesmo nome no mesmo ativo existem.

Sem pessoa e sem texto (regra 8: a API do banco tem leitura aberta): o nome da tarefa vira `tarefa_chave` (a mesma
conta da programação e dos motivos, para casar as três fontes); o responsável da OS (`user_assigned`) só vira a marca
1/0 do backoffice, comparando o HMAC dele com a lista do PCM (o mesmo `motivos.nome_hmac`), sem nunca ir ao banco.
"""
import unicodedata
from collections import Counter

from . import equipamento as E
from .fato_ronda import conferir_grao as _conferir_grao
from .fatos import _id, _int, _txt, data_do_registro, tarefa_chave

LIVRO, ABA = "nexus_os", "fato_tarefa_os"
NOME_LIVRO = "Nexus · tarefas das OS do Fracttal (em processo, em verificação e zeladoria feita)"
CAB_TAREFA_OS = ["fracttal_tarefa_id", "os", "fracttal_os_id", "tarefa_chave", "codigo_ativo", "equipamento_id",
                 "equipamento_ligado_por", "usina_id", "usina_ligada_por", "site_fracttal", "data_id_criacao",
                 "data_id_programada", "data_id_fim", "tipo_tarefa", "status_os", "estado_tarefa", "do_backoffice",
                 "duracao_min"]
TIPO = "snapshot_periodico"
GRAO = ("1 linha = 1 tarefa de OS do Fracttal (em processo ou em verificação, e a zeladoria finalizada nos últimos "
        "90 dias)")
CHAVE = ("fracttal_tarefa_id",)
MEDIDAS = (("duracao_min", "min", "aditiva"),)
FONTES = (("Fracttal (API REST)", "work_orders: status 1 e 2 inteiros; status 3 do tipo Zeladoria"),)
JANELA_ORIGEM = "o que está aberto agora (status 1 e 2); a zeladoria finalizada, 90 dias pelo fim da tarefa"

# o status da OS (`id_status_work_order`): 4 (cancelada) fica fora. Os mesmos valores do `fato_programacao`
STATUS_OS = {1: "em_processo", 2: "em_verificacao", 3: "finalizada"}
# o estado da TAREFA (`task_status`): o REST manda o código; o robô do PCM também aceita o rótulo em português
# (`_ESTADO_CANON` do gerar_gestao_pcm_json.py). Fora da lista = vazio e conta (regra 4), nunca "Não iniciada" por padrão
ESTADO_TAREFA = {"NO_STARTED": "nao_iniciada", "NOT_STARTED": "nao_iniciada", "NOT_INITIATED": "nao_iniciada",
                 "NAO INICIADA": "nao_iniciada", "STARTED": "em_progresso", "IN_PROGRESS": "em_progresso",
                 "EM PROGRESSO": "em_progresso", "PAUSED": "pausada", "PAUSADO": "pausada", "PAUSADA": "pausada",
                 "DONE": "finalizada", "FINISHED": "finalizada", "COMPLETED": "finalizada",
                 "FINALIZADOS": "finalizada", "FINALIZADA": "finalizada"}
# o tipo da tarefa (`tasks_log_task_type_main`), sem acento e sem caixa: os que o código do PCM já cita
# (`pcm/gestao.py`). É ele que separa a Zeladoria (pelo nome, "roça" casava com "troca": 15/10/2026)
TIPOS_TAREFA = {"preventiva": "preventiva", "corretiva": "corretiva", "corretiva emergencial": "corretiva_emergencial",
                "religamento": "religamento", "religamento remoto": "religamento_remoto", "inspecao": "inspecao",
                "preditiva": "preditiva", "administrativa": "administrativa", "zeladoria": "zeladoria",
                "handover": "handover", "teste": "teste"}


def _sem_acento(v) -> str:
    return " ".join(unicodedata.normalize("NFKD", _txt(v)).encode("ascii", "ignore").decode().split())


def linhas(rows, lig, equip_idx, backoffice_hmac, chave_hmac) -> tuple[list[list], dict]:
    """As linhas do fato, na ordem de `CAB_TAREFA_OS`, pela tarefa, e um relatório só de contagens. `rows` = as linhas
    do REST; `lig` = o `Ligador` do cadastro; `equip_idx` = o `equipamento.indice` da dimensão; `backoffice_hmac` = os
    `nome_hmac` da lista vigente do backoffice do PCM; `chave_hmac` = a `NEXUS_PESSOA_HMAC` (sem ela não dá para saber
    quem é do backoffice: todas ficam 0 e o relatório diz `None`)."""
    from nexus.pcm import motivos          # tardio: a camada de dados não puxa o PCM no topo

    por_tarefa, lidas, repetidas, sem_chave = {}, 0, 0, 0
    for w in rows or ():
        lidas += 1
        tid = _id(w.get("id_work_orders_tasks") or w.get("id_task"))
        if _int(w.get("id_status_work_order")) not in STATUS_OS:
            continue
        if not tid:
            sem_chave += 1
            continue
        if tid in por_tarefa:
            repetidas += 1
            continue
        por_tarefa[tid] = w
    fora, out = Counter(), []
    for tid in sorted(por_tarefa):
        w = por_tarefa[tid]
        site, codigo = _txt(w.get("groups_1_description")), _txt(w.get("code"))
        uid, como = lig.usina(site, codigo)
        eid, ecomo = E.ligar(codigo, equip_idx)
        tipo_txt = _sem_acento(w.get("tasks_log_task_type_main")).lower()
        tipo = TIPOS_TAREFA.get(tipo_txt)
        if tipo_txt and not tipo:
            fora["tipo_tarefa"] += 1
        est_txt = _sem_acento(w.get("task_status")).upper()
        estado = ESTADO_TAREFA.get(est_txt)
        if est_txt and not estado:
            fora["estado_tarefa"] += 1
        bo = 0
        if chave_hmac:
            h = motivos.nome_hmac(chave_hmac, w.get("user_assigned"))
            bo = 1 if h and h in backoffice_hmac else 0
        dur_s = _int(w.get("tasks_duration"))          # "Total de Horas" da tarefa; o `duration` é o da OS repetido
        out.append([tid, _id(w.get("wo_folio")), _id(w.get("id_work_order")), tarefa_chave(w.get("description")),
                    codigo or None, eid, ecomo, uid, como, site or None, data_do_registro(w.get("creation_date")),
                    data_do_registro(w.get("date_maintenance")), data_do_registro(w.get("final_date")), tipo,
                    STATUS_OS[_int(w.get("id_status_work_order"))], estado, bo,
                    round(dur_s / 60) if dur_s else None])
    i_u, i_e, i_b = (CAB_TAREFA_OS.index(c) for c in ("usina_id", "equipamento_id", "do_backoffice"))
    rel = {"lidas": lidas, "repetidas": repetidas, "sem_chave": sem_chave, "fora_do_dominio": dict(fora),
           "sem_usina": sum(1 for r in out if not r[i_u]), "sem_equipamento": sum(1 for r in out if not r[i_e]),
           "backoffice": sum(r[i_b] for r in out) if chave_hmac else None}
    return out, rel


def conferir_grao(linhas: list[list]) -> None:
    """Sobe `GraoDuplicado` se o id da tarefa repete ou vem vazio: o fato não grava contando em dobro."""
    _conferir_grao(linhas, CAB_TAREFA_OS, "fracttal_tarefa_id")
