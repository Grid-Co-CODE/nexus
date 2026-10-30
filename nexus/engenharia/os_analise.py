"""A OS do acompanhamento no Fracttal (Levi, 29/10/2026: "quando eu clico em pegar para acompanhar criar uma OS para a
pessoa que pegou a atividade [...] No título terá como padrão: [Ativo(sem fornecedor e sem cliente, apenas o nome
limpo)] - Análise de recorrência de falhas. Etiqueta: engenharia. Data do evento: desde quando ocorreu a 2° OS de falha
que alarmou na confiabilidade. Na nota da OS deve ter o dia que a pessoa assumiu a tarefa, quem assumiu, quais eram a
quantidade de falhas daquele ativo até aquele momento. Deve ter a subtarefa de diagnóstico, quando o engenheiro
preenche o diagnóstico e salva com o fim da análise o diagnóstico responde a subtask e o fim da análise preenche o fim da
atividade"; "Ao encaminhar gera uma OS no nome daquela pessoa da engenharia").

Decisões do Levi no quiz do mesmo dia: a OS é do tipo Administrativa (a de análise do clone, `TIPO_ANALISE`, com a
classificação Programada / Elétrica, como as de ETM); encerrar responde a subtarefa, lança a execução e CONCLUI a OS
(irreversível); encaminhar um acompanhamento que já tem OS troca o responsável dela, e o ativo livre ganha a OS no nome
de quem recebe; os acompanhamentos abertos antes disto ficam sem OS.

PURO quanto ao Fracttal: recebe a `api` do clone (o `os_creator/api.py`, na sessão do Fracttal da pessoa, que a ponte
abre) e só chama as funções dela; quem grava no Nexus é a ponte, depois do Fracttal. `Falhou` = o Fracttal não fez, e
nada se grava no Nexus.
"""
import unicodedata
from datetime import datetime, time, timedelta, timezone

TITULO = "Análise de recorrência de falhas"
SUBTAREFA = "Diagnóstico"
ETIQUETA = "ENGENHARIA"
JANELA_DIAS = 30                 # a janela do sinal da Confiabilidade (`confiabilidade.JANELA_DIAS`)
INICIO_DO_DIA, FIM_DO_DIA = time(8, 0), time(18, 0)   # a análise tem só as datas: a execução vai das 8h às 18h
_BRT = timezone(timedelta(hours=-3))
NIVEL = {"critico": "Crítico", "atencao": "Atenção", "monitorar": "Monitorar"}
# o erro do Fracttal para a OS já fechada (`api._ERRO_WO_FECHADA`, "ERROR_WO_FINISHED_BY_OTHER_USER"); o
# `registrar_execucao` do clone troca o "_" por espaço na mensagem, e a conta é feita sem os dois (revisão de 29/10/2026)
FECHADA = "WO FINISHED"
# o `id_status_work_order` da OS fechada: 3 concluída, 4 cancelada (`os_web.os_acoes_web.nota_pode_editar`)
CONCLUIDA, CANCELADA = 3, 4


def _fechada_no_erro(e) -> bool:
    return FECHADA in str(e).upper().replace("_", " ")


def situacao(api, os_id) -> str:
    """"concluida", "cancelada" ou "" (aberta ou não sei): lida no Fracttal antes de escrever na OS. A OS que o
    engenheiro concluiu no próprio Fracttal não aceita mais nota, execução nem troca de responsável (revisão de
    29/10/2026: sem isto, o acompanhamento travava: não encerrava, não comentava, não encaminhava)."""
    st = api.status_da_os(os_id)
    return "concluida" if st == CONCLUIDA else "cancelada" if st == CANCELADA else ""


class Falhou(RuntimeError):
    """O Fracttal não fez (o texto diz o quê): o Nexus não grava nada."""


def _norm(s) -> str:
    return " ".join(unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower().split())


def titulo(nome: str, curto) -> str:
    """"[Inversor 1.3] - Análise de recorrência de falhas": o nome curto do ativo (`os_web.ativo_curto.curto`, sem marca,
    modelo nem endereço), entre colchetes como os títulos da casa."""
    nome = " ".join(str(nome or "").split())
    return f"[{(curto(nome) if nome else '') or nome}] - {TITULO}"


def da_janela(falhas: list[dict], agora: datetime) -> list[dict]:
    """As falhas dos 30 dias do sinal, a mais antiga primeiro (`falhas` = o `falhasEm` do ativo)."""
    de = agora - timedelta(days=JANELA_DIAS)
    return sorted((f for f in falhas or [] if f.get("quando") and de <= f["quando"] <= agora), key=lambda f: f["quando"])


def data_do_evento(falhas: list[dict], agora: datetime) -> datetime | None:
    """A 2ª falha da janela, a que acendeu o sinal (são 2 falhas em 30 dias); com uma só, ela; sem nenhuma, None."""
    j = da_janela(falhas, agora)
    return j[1]["quando"] if len(j) > 1 else (j[0]["quando"] if j else None)


def nota_de_entrada(ativo: dict, quem: str, para: str, quando: datetime, falhas: list[dict],
                    desde: datetime | None = None) -> str:
    """A nota da OS na criação (a API do Fracttal não edita a OS depois, só a nota): o dia, quem assumiu (ou quem
    encaminhou para quem) e as falhas do ativo até aquele momento, como a Confiabilidade contava. `desde` = o começo do
    acompanhamento que ganha a OS depois (o "Gerar OS" de 30/10/2026)."""
    q = quando.astimezone(_BRT)
    if desde:
        acao = (f"OS gerada em {q:%d/%m/%Y às %H:%M} por {quem} para a análise que {para} acompanha desde "
                f"{desde.astimezone(_BRT):%d/%m/%Y}.")
    else:
        acao = (f"Assumida em {q:%d/%m/%Y às %H:%M} por {quem}." if quem == para
                else f"Encaminhada em {q:%d/%m/%Y às %H:%M} por {quem} para {para}.")
    n30, n7 = int(ativo.get("nFalha") or 0), int(ativo.get("n7") or 0)
    linhas = [f"[ENGENHARIA] {TITULO}", acao,
              f"Falhas do ativo até agora: {n30} {'falha' if n30 == 1 else 'falhas'} em 30 dias ({n7} em 7 dias)"
              + (f", nível {NIVEL[ativo['nivel']]} na Confiabilidade." if ativo.get("nivel") in NIVEL else ".")]
    j = da_janela(falhas, quando)
    if j:
        linhas.append("OS de falha: " + ", ".join("#" + str(f["os"]) for f in j if f.get("os")))
    return "\n".join(linhas)


def linha_encaminhou(quem: str, para: str, quando: datetime) -> str:
    """A linha na nota da OS quando a análise muda de mãos (o formato do comentário da Engenharia)."""
    return f"[{quando.astimezone(_BRT):%d/%m/%Y %H:%M}] {quem} (Engenharia): encaminhou a análise para {para}."


def _fid(pessoa: dict) -> int:
    try:
        return int(str(pessoa.get("fid") or "").strip())
    except ValueError:
        raise Falhou(f"Não achei {pessoa.get('nome') or 'a pessoa'} entre os responsáveis do Fracttal: sem o id de lá, "
                     "a OS não sai no nome dela (Base → Acessos → Pessoas e setores)") from None


def criar(api, ativo: dict, para: dict, quem: str, agora: datetime, falhas: list[dict], curto,
          desde: datetime | None = None) -> dict:
    """Cria a OS de análise do ativo no nome de `para` ({"fid", "nome"}: quem pegou, ou quem recebeu o encaminhado).
    → {"id", "folio", "aviso"}. A etiqueta que não existe no Fracttal não segura a OS (sai sem ela, com o aviso)."""
    fid = _fid(para)
    lid = api._label_id(ETIQUETA)
    c = api._classif_ids(api.ANALISE_CLASSIF_1, api.ANALISE_CLASSIF_2)
    tipo = {}
    if c.get("id_task_type") is not None:
        tipo.update(id_c1=c["id_task_type"], desc_c1=c.get("tasks_types_description") or "")
    if c.get("id_task_type_2") is not None:
        tipo.update(id_c2=c["id_task_type_2"], desc_c2=c.get("tasks_types_2_description") or "")
    res = api.create_work_orders_bulk(
        [ativo["cod"]], titulo(ativo.get("nome") or ativo["cod"], curto), api.TIPO_ANALISE, [SUBTAREFA],
        etiqueta_ids=[lid] if lid else None, id_responsible=fid, responsible_name=para["nome"],
        note=nota_de_entrada(ativo, quem, para["nome"], agora, falhas, desde=desde), tipo=tipo or None,
        event_date=data_do_evento(falhas, desde or agora))
    r0 = (res or [{}])[0] or {}
    if not r0.get("ok"):
        raise Falhou(f"O Fracttal não criou a OS: {r0.get('erro') or 'sem resposta'}")
    o = r0.get("os") or {}
    if not o.get("id_work_order"):
        raise Falhou("A tarefa foi criada no Fracttal, mas não virou OS (" + str(o.get("aviso") or "sem número")
                     + "): confira lá antes de pegar de novo, para não ficar com duas")
    aviso = str(o.get("aviso") or "")
    if not lid:
        aviso = (aviso + " " if aviso else "") + f"A OS saiu sem a etiqueta {ETIQUETA} (não a achei no Fracttal)."
    return {"id": o["id_work_order"], "folio": str(o.get("wo_folio") or ""), "aviso": aviso}


def _execucao(inicio, fim, agora: datetime) -> tuple[datetime, datetime]:
    """Das datas da análise para o início e o fim da execução: das 8h do início às 18h do fim, nunca adiante de agora
    (encerrar hoje de manhã não lança o fim às 18h)."""
    ini = datetime.combine(inicio, INICIO_DO_DIA, _BRT)
    f = min(datetime.combine(fim, FIM_DO_DIA, _BRT), agora)
    return (min(ini, f - timedelta(minutes=1)), f)


def encerrar(api, os_id, diagnostico: str, inicio, fim, nome: str, agora: datetime | None = None) -> list[str]:
    """Fecha a OS da análise: responde a subtarefa Diagnóstico (a que já tem o mesmo valor não se regrava), lança a
    execução do início ao fim da análise e conclui a OS (IRREVERSÍVEL). → os passos feitos. Cada passo confere antes
    (revisão de 29/10/2026): a OS já concluída ou cancelada no Fracttal não recebe nada ("ja_concluida",
    "ja_cancelada"); sem a subtarefa Diagnóstico, nada é concluído; a tarefa que já tem execução não ganha outra (a
    conclusão que o Fracttal recusou, tentada de novo, lançava uma execução a cada vez)."""
    agora = agora or datetime.now(_BRT)
    sit = situacao(api, os_id)
    if sit:
        return ["ja_concluida" if sit == "concluida" else "ja_cancelada"]
    tid = api.id_tarefa_da_os(os_id)
    if not tid:
        raise Falhou("Não achei a tarefa da OS no Fracttal: nada foi encerrado lá")
    feito = []
    item = next((s for s in api.subtarefas_da_tarefa(tid) or [] if _norm(s.get("descricao")) == _norm(SUBTAREFA)), None)
    if not item:
        raise Falhou(f"A OS não tem a subtarefa {SUBTAREFA} no Fracttal: nada foi concluído (responda o diagnóstico e "
                     "conclua a OS lá; depois encerre aqui)")
    if diagnostico and str(item.get("valor") or "").strip() != diagnostico:
        api.salvar_subtarefas(os_id, tid, [{"id_form_item": item["id_form_item"], "valor": diagnostico,
                                            "tipo": item.get("tipo") or 1}])
        feito.append("subtarefa")
    if not any(x.get("done") for x in api.execucoes_da_tarefa(tid) or []):
        ini, f = _execucao(inicio, fim, agora)
        try:
            api.registrar_execucao(tid, ini, f, nome=nome)
        except Exception as e:  # noqa: BLE001 — a OS que outra tentativa já concluiu: não há o que lançar nem concluir
            if _fechada_no_erro(e):
                return feito + ["ja_concluida"]
            raise
        feito.append("execucao")
    r = api.concluir_os_analise(os_id, tid)
    if not (isinstance(r, dict) and r.get("ok")):
        raise Falhou("O Fracttal não concluiu a OS: " + str((r or {}).get("erro") or "sem resposta"))
    feito.append("concluida")
    return feito


def trocar_responsavel(api, os_id, para_fid) -> None:
    """O encaminhar de um acompanhamento que já tem OS: a OS passa para quem recebe (a nota fica como está)."""
    fid = _fid({"fid": para_fid, "nome": "a pessoa"})
    r = api.mudar_responsavel(os_id, fid)
    if not (isinstance(r, dict) and r.get("ok")):
        raise Falhou("O Fracttal não trocou o responsável da OS: " + str((r or {}).get("erro") or "sem resposta"))
