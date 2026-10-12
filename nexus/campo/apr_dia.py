"""As tarefas da APR do dia (11/10/2026, Levi, sobre Segurança > APR e PT: "Por qual motivo algumas tarefas aparece como
'APR do dia'? sendo que está ligado a atividade de um ativo no fractal").

Desde a APR por OS e dia (App v246; para todos desde a v256, 10/10/2026), o técnico preenche UMA APR (e a PT) por OS e
dia, no lugar de uma por tarefa. A PT dessa APR não é de uma tarefa: o App manda no livro de PT a tarefa "APR do dia
AAAA-MM-DD" e o código do ativo vazio (29 das 315 PT em 11/10). As atividades são as tarefas da OS no Fracttal, e o
Nexus já as tem: o `gestao_pcm.json` (as tarefas do Fracttal desde 01/01, que o robô do PCM regrava; o mesmo da Gestão
PCM), com o equipamento entre colchetes no nome da tarefa ("[Cabine 2] - Religamento da Cabine 2"). Medido em 11/10:
as 29 OS estavam lá, e 25 delas fora da programação semanal (religamentos e emergenciais do fim de semana), por isso a
programação não serve de fonte.

Quais tarefas: as da OS feitas no dia da APR (iniciadas ou finalizadas nele, a regra de "realizada" do App); sem
nenhuma, as que estavam abertas no dia; sem nenhuma, todas as da OS. OS que ainda não chegou ao arquivo (o robô do PCM
regrava de tempos em tempos) fica como o App mandou.
"""
import re

PREFIXO = "APR do dia "
_DIA_RE = re.compile(r"^APR do dia (\d{4}-\d{2}-\d{2})\s*$")
_COLCHETE_RE = re.compile(r"^\[([^\]]+)\]\s*[-–]\s*")
_GERAL = "grid co."          # "[Grid Co.] - MPM - Transformador Aéreo": o colchete é a marca, o equipamento vem no fim


def dia_da_apr(tarefa) -> str | None:
    """ "APR do dia 2026-10-11" -> "2026-10-11"; None para a tarefa de verdade."""
    m = _DIA_RE.match(str(tarefa or "").strip())
    return m.group(1) if m else None


def equipamento(tarefa) -> str:
    """O equipamento pelo nome da tarefa do Fracttal: "[Cabine 2] - Religamento da Cabine 2" -> "Cabine 2";
    "[Grid Co.] - MPM - Transformador Aéreo" -> "Transformador Aéreo"; sem colchete, vazio."""
    s = str(tarefa or "").strip()
    m = _COLCHETE_RE.match(s)
    if not m:
        return ""
    if m.group(1).strip().lower() != _GERAL:
        return m.group(1).strip()
    resto = re.split(r"\s[-–]\s", s[m.end():])
    return resto[-1].strip() if len(resto) > 1 else ""


def indice(tarefas) -> dict[str, list[dict]]:
    """{OS: [tarefa do gestao_pcm.json]}, na ordem do arquivo."""
    out: dict[str, list[dict]] = {}
    for t in tarefas or []:
        os_ = str(t.get("os") or "").strip()
        if os_:
            out.setdefault(os_, []).append(t)
    return out


def tarefas_no_dia(ts: list[dict], dia: str) -> list[dict]:
    feitas = [t for t in ts if str(t.get("dataInicio") or "")[:10] == dia or str(t.get("dataFinal") or "")[:10] == dia]
    if feitas:
        return feitas
    abertas = [t for t in ts if str(t.get("dataInicio") or "")[:10] <= dia
               and (not t.get("dataFinal") or str(t.get("dataFinal"))[:10] > dia)]
    return abertas or list(ts)


def completar(pts: list[dict], por_os: dict[str, list[dict]]) -> int:
    """Põe nas PT da APR do dia as tarefas da OS: `tarefa` (a 1ª, e quantas mais), `ativo` (os equipamentos),
    `tarefas_os` (a lista, para o detalhe) e `apr_dia` ("11/10"). Devolve quantas completou."""
    n = 0
    for p in pts:
        dia = dia_da_apr(p.get("tarefa"))
        if not dia:
            continue
        p["apr_dia"] = f"{dia[8:10]}/{dia[5:7]}"
        ts = tarefas_no_dia(por_os.get(str(p.get("os") or "").strip(), []), dia)
        if not ts:
            continue
        lista = [{"tarefa": str(t.get("tarefa") or "").strip(), "equipamento": equipamento(t.get("tarefa")),
                  "estado": str(t.get("estado") or "")} for t in ts]
        p["tarefas_os"] = lista
        p["tarefa"] = lista[0]["tarefa"] + (f" (+{len(lista) - 1})" if len(lista) > 1 else "")
        equips = []
        for x in lista:
            if x["equipamento"] and x["equipamento"] not in equips:
                equips.append(x["equipamento"])
        if equips and not p.get("ativo"):
            p["ativo"] = ", ".join(equips)
        n += 1
    return n
