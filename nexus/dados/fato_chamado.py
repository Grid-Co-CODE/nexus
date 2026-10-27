"""O fato do chamado de garantia (12/10/2026): `nexus_chamados · fato_chamado`, as OS de acompanhamento de chamado do
Fracttal com os IDs do Nexus. Puro: quem lê o Fracttal e grava é `nexus/campo/chamados_acompanhamento.py`.

Levi, 12/10/2026, sobre a Visão do responsável contar chamados pela planilha de tickets: "Não quero informações da
planilha de tickets e sim do acompanhamento de chamados (...) O nexus é um ambiente centralizado e precisamos ter os
dados se conversando!". A planilha tinha mais de 1.000 ocorrências "abertas" (sem fim desde junho); o quadro de chamados,
18 abertas de verdade.

O que é a OS de acompanhamento (a "OS 3" do chamado de garantia; ver `nexus/torres/oscreator/os_creator/os_web/
acomp_web.py`): quando o técnico fecha a inspeção do chamado no App de Campo, o servidor do App cria sozinho a OS
"[Ativo] - Acompanhamento de chamado <marca>", tipo Administrativa, etiqueta CHAMADOS, com a marca
"[CHAMADO] Acompanhamento — <fabricante> · <componente>" na nota e UMA subtarefa: o nº do ticket aberto no fabricante.
O quadro Acompanhamento de chamados do OS Creator mostra Chegaram, Ticket aberto e Finalizados (90 dias) e continua
lendo o Fracttal ao vivo (é nele que a analista de chamados escreve o ticket e finaliza).

Grão: 1 linha = 1 OS de acompanhamento: em processo (`aberto`), em verificação (`verificacao`) e concluída nos últimos
90 dias (`concluido`), as colunas do quadro; cancelada fica fora, como lá. Foto acumulada: a linha muda até a OS fechar.

Limite medido em 12/10/2026: a API REST do Fracttal (a credencial do Nexus) NÃO traz a subtarefa do ticket (os
endpoints de subtarefa dão 400 e o `completed_percentage` fica 0 nas 17 abertas). Então "aguardando ticket" × "com o
fabricante" não está no fato: só no quadro, que lê com a sessão de quem entrou.

Sem pessoa e sem texto livre (a API do banco tem leitura aberta): o fabricante e o componente saem da marca da nota
(categorias, como "STI · Estrutura Trackers"); a nota, o técnico e a analista não vão. A usina liga pelo de-para do
Fracttal (o site da OS) ou pelo código do ativo; o equipamento, pelo código na dimensão de equipamento. Não liga = vazio
(regra 4), com o site e o código para consertar no cadastro.

A OS RETROATIVA (20/10/2026): a analista de chamados cria à mão a OS de acompanhamento de um chamado que já existia na
planilha de gestão de chamados, com a "Data da ocorrência / abertura do chamado" na nota. Levi, no mesmo dia: no banco, o
chamado abre nessa data ("A abertura do chamado"), e não no dia em que a OS entrou no Fracttal; a 1ª, de 21/08, contaria
0 dias. A data da nota vale quando é uma data de verdade e não depois da criação da OS; a duração conta dela (o dia, 00:00
em Brasília: a nota não traz a hora). `abertura_por` diz de onde veio (regra 5, linhagem): `nota` ou `os` (a criação).
A mesma leitura da tela está em `acomp_web.ler_nota` e `acomp_web.abertura_valida` (o OS Creator não importa o Nexus).
"""
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from .calendario import data_id
from .fatos import _id, _int, _txt, ligar_equipamento

LIVRO, ABA = "nexus_chamados", "fato_chamado"
NOME_LIVRO = "Nexus · chamados de garantia (OS de acompanhamento de chamado do Fracttal)"
# CÓPIA no PerformancePainel (`plataforma/diag_tratamento.py`, 27/10/2026): o Diagnóstico da usina lê este livro para dizer
# "aguardando fabricante há N dias". A leitura de lá é por NOME de coluna: coluna nova aqui não quebra, renomear quebra.
CAB_CHAMADO = ["os", "data_id_abertura", "data_id_fim", "usina_id", "usina_ligada_por", "site_fracttal",
               "equipamento_id", "equipamento_ligado_por", "codigo_ativo", "situacao", "fabricante", "componente",
               "duracao_min", "abertura_por"]
TIPO = "snapshot_acumulado"
GRAO = ("1 linha = 1 OS de acompanhamento de chamado do Fracttal (em processo, em verificação ou concluída nos "
        "últimos 90 dias)")
CHAVE = ("os",)
MEDIDAS = (("duracao_min", "min", "aditiva"),)
FONTES = (("Fracttal (API REST)", "work_orders da tarefa Administrativa"),)
JANELA_ORIGEM = "o Fracttal guarda tudo; o fato leva as abertas, as em verificação e as concluídas dos últimos 90 dias"
SITUACAO = {1: "aberto", 2: "verificacao", 3: "concluido"}       # o status da OS no Fracttal (4 = cancelada: fora)
TIPO_TAREFA = "Administrativa"
MARCA = "[CHAMADO] Acompanhamento"
DIAS_CONCLUIDOS = 90                                             # os Finalizados do quadro
_BRT = timezone(timedelta(hours=-3))
_RX_MARCA = re.compile(r"\[CHAMADO\] Acompanhamento\s*[—-]\s*([^·\n]+?)\s*·\s*([^\n]+)")
_RX_ABERTURA = re.compile(r"^\s*(?:Data da ocorrência(?:\s*/\s*abertura do chamado)?|Abertura do chamado)\s*:\s*"
                          r"(\d{2}/\d{2}/\d{4})", re.IGNORECASE | re.MULTILINE)


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def eh_os3(w: dict) -> bool:
    """A OS de acompanhamento, e não as antigas com a etiqueta CHAMADOS (a mesma regra do quadro, `acomp_web.eh_os3`,
    nos campos do REST): a marca na nota é o sinal forte; o título + o tipo Administrativa cobrem a nota vazia."""
    if MARCA in str(w.get("task_note") or "") or MARCA in str(w.get("note") or ""):
        return True
    return ("acompanhamento de chamado" in _norm(w.get("description"))
            and _norm(TIPO_TAREFA) in _norm(w.get("tasks_log_task_type_main")))


def marca(nota) -> tuple[str, str]:
    """("STI", "Estrutura Trackers") da marca "[CHAMADO] Acompanhamento — STI · Estrutura Trackers"; ("", "") sem ela."""
    m = _RX_MARCA.search(str(nota or ""))
    return (m.group(1).strip()[:40], m.group(2).strip()[:40]) if m else ("", "")


def abertura_da_nota(nota, criada: datetime | None) -> datetime | None:
    """A abertura do chamado escrita na nota da retroativa ("Data da ocorrência / abertura do chamado: 21/08/2026"),
    à 00:00 de Brasília. None sem ela, com data que não existe ou com data depois da criação da OS (erro de digitação):
    aí vale a criação, como sempre."""
    m = _RX_ABERTURA.search(str(nota or ""))
    if not m:
        return None
    try:
        a = datetime.strptime(m.group(1), "%d/%m/%Y").replace(tzinfo=_BRT)
    except ValueError:
        return None
    if criada is not None and a.date() > criada.astimezone(_BRT).date():
        return None
    return a


def _dt(v) -> datetime | None:
    s = _txt(v).replace("Z", "+00:00")
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _dia(d: datetime | None) -> int | None:
    """O dia de Brasília (regra 7: o Fracttal grava em UTC; 02:30Z é o dia anterior)."""
    return data_id(d.astimezone(_BRT).date()) if d else None


def linhas(rows, lig, equip=None, hoje=None) -> list[list]:
    """As linhas do fato, na ordem de `CAB_CHAMADO`, pela OS. `rows` = as linhas do REST (uma por tarefa: a OS 3 tem uma
    só; repetida, vale a de criação mais antiga); `lig` = o `Ligador` do cadastro; `equip` = {código: equipamento_id}
    da dimensão de equipamento; `hoje` = o dia de Brasília (a concluída há mais de 90 dias sai, como no quadro)."""
    por_os = {}
    for w in rows or ():
        st = _int(w.get("id_status_work_order"))
        os_ = _id(w.get("wo_folio"))
        if st not in SITUACAO or not os_ or not eh_os3(w):
            continue
        atual = por_os.get(os_)
        if atual is None or _txt(w.get("creation_date")) < _txt(atual.get("creation_date")):
            por_os[os_] = w
    out = []
    for os_, w in por_os.items():
        st = _int(w.get("id_status_work_order"))
        cri = _dt(w.get("creation_date"))
        fim = _dt(w.get("wo_final_date") or w.get("final_date")) if st in (2, 3) else None
        if st == 3 and fim and hoje and (hoje - fim.astimezone(_BRT).date()).days > DIAS_CONCLUIDOS:
            continue
        site, codigo = _txt(w.get("groups_1_description")), _txt(w.get("code"))
        uid, como = lig.usina(site, codigo)
        eid, ecomo = ligar_equipamento(equip, codigo)
        nota = w.get("task_note") or w.get("note")
        fab, comp = marca(nota)
        aberta = abertura_da_nota(nota, cri)
        ini = aberta or cri
        dur = round((fim - ini).total_seconds() / 60) if fim and ini and fim >= ini else None
        out.append([os_, _dia(ini), _dia(fim), uid, como, site or None, eid, ecomo, codigo or None, SITUACAO[st],
                    fab or None, comp or None, dur, "nota" if aberta else ("os" if cri else None)])
    out.sort(key=lambda r: r[0])
    return out
