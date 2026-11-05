"""Gestão PCM: a "Confiabilidade por ativo" e o "Tempo médio de reparo por Equipe Cluster" (Levi, 04/11/2026: os dois
blocos do fim da aba Gestão PCM do painel do PCM; "a conta da Engenharia", decisão dele).

Os números NÃO são calculados aqui: são os da tela Engenharia > Confiabilidade (`nexus/engenharia/confiabilidade.py`,
`calcular` e `indicadores`), na cópia de 5 min que a torre da Engenharia já guarda (`nexus/torres/engenharia`,
`_dados()`): as mesmas OS de falha do Fracttal, o ativo pelo CÓDIGO (com a usina dentro), o lugar pelo cadastro do Nexus.
No painel eles vinham do `confiabilidade.json` do robô do PCM, que casava o ativo pelo nome e somava a frota toda na
disponibilidade do grupo (ver nexus/torres/engenharia/CLAUDE.md, "O que muda em relação ao PCM"). O que é só daqui:
- a árvore Cliente ▸ Usina ▸ Ativo (o `renderConfiab`/`cfUsiHTML` do js/app.js do painel), com os indicadores da
  Engenharia por usina (as medianas dos ativos) e, na tabela da usina, os de cada ativo;
- as OS de cada ativo (as mesmas que entraram na conta, `porAtivo`), com as horas de reparo de cada uma
  (`confiabilidade.reparo_h`, a parcela do MTTR: a média das horas da lista é o MTTR do ativo), pedidas só quando o
  ativo abre (uma usina de verdade tinha 1.090 OS de falha em 282 ativos: tudo no pedaço da usina dava ~1 MB);
- o MTTR por equipe cluster: a média POR FALHA das falhas dos ativos do cluster (cada falha pesa igual, a mesma definição
  do MTTR do ativo; o `mttr_de` do robô do PCM faz igual), com o cluster do cadastro;
- os filtros de cima: cliente, usina e equipe cluster, sem maiúscula. O cliente e o cluster são os do cadastro dos dois
  lados; a usina da Gestão é o texto do Fracttal ("Cliente - Usina - UF", a Classificação 1) e a da Engenharia é o nome
  do cadastro, então a usina casa pelo texto das OS dos ativos dela (em 04/11/2026, 130 das 143 usinas da Gestão tinham
  OS de falha, todas com o texto igual ao da Gestão; as outras 13 não tinham falha).
Só lê: nada grava. O Fracttal não é lido aqui: o `copia()` pede a mesma releitura das OS de falha que a tela da
Engenharia pede ao abrir (`os_falhas.pedir_releitura`: no máximo uma a cada 30 min, por trás e no porteiro do Fracttal),
e a conta usa o que já foi lido. Sem a leitura completa ou sem o cadastro (a conta segue com os nomes do Fracttal, sem
cluster e com a mobilização de 20/10/2025 para todas: número enganoso), o bloco não mostra número e diz por quê.
"""
import hashlib
from datetime import datetime, timedelta, timezone

from ..engenharia import os_falhas
from . import gestao as G

BRT = timezone(timedelta(hours=-3))
INCOMPLETA = "A leitura do Fracttal ainda não terminou: tente em alguns minutos."
SEM_CADASTRO = "O cadastro do Nexus não respondeu: tente em alguns minutos."
# a usina sem cluster no cadastro e a usina que não ligou ao cadastro (sem ela, o cluster vem vazio) caem juntas aqui
SEM_CLUSTER = "Sem cluster no cadastro (ou sem ligação)"
SEM_CLIENTE = "Sem cliente no cadastro"
BASE = ", ".join(t.capitalize() for t in os_falhas.TIPOS)        # Corretiva, Corretiva emergencial, ...
_STATUS = {1: "Em Processo", 2: "Em Verificação", 3: "Concluída"}     # a grafia do card da OS do Nexus
# os filtros de cima que não valem nestes blocos, na ordem da barra (a linha de baixo do título diz quais)
_NAO_VALEM = (("responsavel", "responsável"), ("tipo_tarefa", "tipo"), ("etiqueta", "etiqueta"), ("estado", "estado"),
              ("os", "OS"), ("ss", "solicitação"), ("periodo", "período"), ("atr", "só atrasadas"))
_TETO = 40                  # combinações de cliente, usina e cluster guardadas por cópia da Engenharia
_COPIA: dict = {}


def limpar() -> None:
    _COPIA.clear()


# ── o formato e a cor ────────────────────────────────────────────────────────────────────────────────────────
def horas(x) -> str:
    """As horas como a Engenharia escreve (o `_h` da torre, sem a unidade): 5.737 e 25,9; sem número, "—"."""
    if x is None:
        return "—"
    return f"{x:,.0f}".replace(",", ".") if x >= 100 else f"{x:.1f}".replace(".", ",")


def pct(x) -> str:
    """A disponibilidade como a Engenharia escreve (o `_pct` da torre): 87,3%."""
    return "—" if x is None else f"{100 * x:.1f}".replace(".", ",") + "%"


def inteiro(n) -> str:
    return f"{int(n or 0):,}".replace(",", ".")


def classe_disp(x) -> str:
    """A cor da disponibilidade pela regra da Engenharia: na meta (85%, `META_DISP`) ou acima, verde; abaixo, vermelho."""
    from ..engenharia.confiabilidade import META_DISP
    return "nulo" if x is None else ("ok" if x >= META_DISP else "crit")


def classe_mttr(x) -> str:
    """A cor do MTTR (o `cfMttrCls` do painel): até 24 h verde, até 72 h âmbar, acima disso vermelho."""
    return "nulo" if x is None else ("ok" if x <= 24 else ("and" if x <= 72 else "crit"))


def nao_se_aplicam(f: G.Filtros) -> str:
    """A linha de baixo do título diz quais filtros de cima não valem aqui (só cliente, usina e cluster valem), e só
    quando algum deles está escolhido."""
    nomes = [rot for k, rot in _NAO_VALEM if ((f.pini or f.pfim) if k == "periodo" else getattr(f, k))]
    if not nomes:
        return ""
    if len(nomes) == 1:
        return f"o filtro de {nomes[0]} não se aplica aqui"
    return f"os filtros de {', '.join(nomes[:-1])} e {nomes[-1]} não se aplicam aqui"


# ── a cópia da Engenharia ────────────────────────────────────────────────────────────────────────────────────
def copia() -> tuple[dict | None, str]:
    """(a conta, "") ou (None, o porquê). A conta é a da Engenharia (a cópia de 5 min da torre, `_dados()`, pedida a
    cada vez) mais o índice e os resultados daqui, refeitos só quando a cópia de lá muda. Daqui só se guarda o índice e
    os resultados (números e nomes): a conta de lá não fica presa entre um pedido e outro (~5 MB; a memória do servidor
    é curta). Sem número quando a leitura das OS de falha ainda não terminou (número pela metade não vai para a tela; a
    tela da Engenharia mostra com aviso) ou quando o cadastro não respondeu; e aí nada fica guardado."""
    from ..torres import engenharia
    os_falhas.pedir_releitura()          # carrega o arquivo antes de perguntar (e pede a releitura, como a torre faz)
    if not os_falhas.estado()["completa"]:
        return None, INCOMPLETA
    g = engenharia._dados()
    if g.get("sem_cadastro"):
        return None, SEM_CADASTRO
    marca, d = (g["marca"], g["em"]), g["dados"]
    guardada = _COPIA.get("c")
    if guardada is None or guardada["marca"] != marca:
        guardada = {"marca": marca, "idx": _indice(d), "res": {}, "quando": _quando(g["marca"][1])}
        _COPIA["c"] = guardada
    return {"d": d, "idx": guardada["idx"], "res": guardada["res"], "quando": guardada["quando"],
            "grupos": _grupos(d)}, ""


def _quando(ts) -> str:
    """A hora da leitura das OS de falha (as vivas, relidas a cada passada), em Brasília."""
    try:
        return datetime.fromtimestamp(float(ts), BRT).strftime("%d/%m %H:%M") if ts else ""
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _indice(d: dict) -> dict:
    """Por código do ativo: os textos do Fracttal das OS dele (a Classificação 1, para o filtro de usina) e a soma e a
    contagem das horas de reparo (para o MTTR por cluster, a média por falha)."""
    from ..engenharia.confiabilidade import reparo_h
    por = d.get("porAtivo") or {}
    out = {}
    for a in d.get("ativos") or []:
        rs = por.get(a["cod"]) or []
        hs = [h for h in map(reparo_h, rs) if h is not None]
        textos = {str(r.get("groups_1_description") or "").strip().lower() for r in rs}
        out[a["cod"]] = {"textos": frozenset(textos - {""}), "soma": sum(hs), "nrep": len(hs)}
    return out


def _grupos(d: dict) -> dict:
    """{(cliente, usina): os ativos}, como a Engenharia os mostra (o nome do cadastro; sem ligação, o do Fracttal). O
    ativo sem cliente ou sem usina não vai para um grupo "—" (Levi, 05/11/2026): o cliente vira `SEM_CLIENTE` e a usina
    sem nome é dita pelo prefixo do código dos ativos (o código traz a usina: IPX100-INVR1.1), para o PCM saber qual é."""
    out: dict = {}
    for a in d.get("ativos") or []:
        cli = str(a.get("cliente") or "").strip()
        usi = str(a.get("usina") or "").strip()
        if not usi or usi == "—":
            usi = f"Sem usina (código {str(a.get('cod') or '').split('-')[0] or '?'})"
        out.setdefault((SEM_CLIENTE if not cli or cli == "—" else cli, usi), []).append(a)
    return out


def ordem_cliente(nome: str):
    """A ordem dos clientes na Confiabilidade: a do painel (localeCompare pt-BR), com o `SEM_CLIENTE` por último."""
    return (nome == SEM_CLIENTE, G.ordem_pt(nome))


def _guardado(c: dict, chave, fazer):
    v = c["res"].get(chave)
    if v is None:
        v = fazer()
        if len(c["res"]) > _TETO:
            c["res"].clear()
        c["res"][chave] = v
    return v


def recorte(c: dict, f: G.Filtros) -> list[tuple]:
    """As usinas (cliente, usina) que os filtros de cima deixam, com os ativos de cada uma. A usina entra inteira ou
    fica fora (os três filtros são da usina): os números de cada usina são os da Engenharia, com todos os ativos dela."""
    clis, usis, clus = ({v.lower() for v in getattr(f, n)} for n in ("cliente", "usina", "cluster"))
    out = []
    for (cli, usi), ats in c["grupos"].items():
        if clis and cli.strip().lower() not in clis:
            continue
        if clus and not {(a.get("cluster") or "").strip().lower() for a in ats} & clus:
            continue
        if usis and not any(c["idx"][a["cod"]]["textos"] & usis for a in ats):
            continue
        out.append(((cli, usi), ats))
    return out


# ── a Confiabilidade por ativo ───────────────────────────────────────────────────────────────────────────────
def arvore(c: dict, f: G.Filtros) -> list[dict]:
    """Cliente ▸ Usina, na ordem do localeCompare pt-BR (a do painel): no cliente, quantas usinas e quantas falhas; na
    usina, o MTBF, o MTTR e a disponibilidade da Engenharia (as medianas dos ativos, `indicadores` por usina). A tabela
    de cada usina vem à parte (`tabela_da_usina`), quando ela abre: são ~2,3 mil ativos."""
    from ..engenharia.confiabilidade import indicadores

    def fazer():
        clientes: dict = {}
        for (cli, usi), ats in recorte(c, f):
            ind = indicadores(ats, [], "usina")[0]
            clientes.setdefault(cli, []).append({"nome": usi, "cliente": cli, "mtbf": ind["mtbf"], "mttr": ind["mttr"],
                                                 "disp": ind["disp"], "ativos": len(ats),
                                                 "falhas": sum(a.get("n") or 0 for a in ats)})
        out = []
        for cli in sorted(clientes, key=ordem_cliente):
            us = sorted(clientes[cli], key=lambda u: G.ordem_pt(u["nome"]))
            out.append({"nome": cli, "usinas": us, "n_usinas": len(us), "falhas": sum(u["falhas"] for u in us)})
        return out
    return _guardado(c, ("conf", G.chave(f)[:3]), fazer)


def _data(v) -> str:
    from ..engenharia.confiabilidade import _dt
    d = _dt(v)
    return d.astimezone(BRT).strftime("%d/%m/%Y %H:%M") if d else "—"


def _linha_os(r: dict) -> dict:
    """Uma OS do ativo (o `cfTaskRows` do painel): o número (abre o card da OS no Nexus; o Fracttal no ícone), a tarefa,
    o tipo, o início do trabalho e o fim em Brasília e as horas de reparo (do INCIDENTE ao fim, a conta do MTTR: o início
    do trabalho pode vir depois do incidente, e a tela diz isso na legenda)."""
    from ..engenharia.confiabilidade import OS_URL, reparo_h
    wid = r.get("id_work_order")
    try:
        st = int(r.get("id_status_work_order") or 0)
    except (TypeError, ValueError):
        st = 0
    return {"os": str(r.get("wo_folio") or "").split(".")[0], "wid": wid, "status": _STATUS.get(st, ""),
            "url": OS_URL.format(id=wid) if wid else "", "tarefa": str(r.get("description") or "").strip() or "—",
            "tipo": str(r.get("tasks_log_task_type_main") or "").strip() or "—", "inicio": _data(r.get("initial_date")),
            "fim": _data(r.get("final_date")), "horas": horas(reparo_h(r))}


def tabela_da_usina(c: dict, cliente: str, usina: str) -> dict | None:
    """A tabela de UMA usina: Ativo · MTBF · MTTR · Disp. inerente · Falhas, os de mais falhas primeiro (o painel). As
    OS de cada ativo vêm à parte, quando ele abre (`os_do_ativo`). None = a usina não está na conta."""
    ats = c["grupos"].get((cliente, usina))
    if not ats:
        return None
    linhas = [{"cod": a["cod"], "nome": a.get("nome") or a["cod"], "mtbf": a.get("mtbf"), "mttr": a.get("mttr"),
               "disp": a.get("disp"), "n": a.get("n") or 0}
              for a in sorted(ats, key=lambda a: (-(a.get("n") or 0), G.ordem_pt(a.get("nome") or a["cod"])))]
    uid = "u" + hashlib.sha1(f"{cliente}|{usina}".encode("utf-8")).hexdigest()[:10]
    return {"cliente": cliente, "usina": usina, "id": uid, "ativos": linhas}


def os_do_ativo(c: dict, cod: str) -> list[dict] | None:
    """As OS de UM ativo (as que entraram na conta), a de início mais novo primeiro. None = o ativo não está na conta."""
    from ..engenharia.confiabilidade import _dt
    if cod not in c["idx"]:
        return None
    piso = datetime.min.replace(tzinfo=timezone.utc)
    rs = sorted((c["d"].get("porAtivo") or {}).get(cod) or [], key=lambda r: _dt(r.get("initial_date")) or piso,
                reverse=True)
    return [_linha_os(r) for r in rs]


# ── o Tempo médio de reparo por Equipe Cluster ───────────────────────────────────────────────────────────────
def clusters(c: dict, f: G.Filtros) -> list[dict]:
    """Por equipe cluster (a do cadastro): o MTTR = a soma das horas de reparo das falhas dos ativos do cluster ÷ quantas
    falhas têm o reparo medido (cada falha pesa igual, a mesma definição do MTTR do ativo); as falhas = as da Engenharia
    (desde 20/10/2025, a aberta também). Os piores no topo; dentro, as usinas com o MTTR e as falhas delas, a pior
    primeiro. A usina sem cluster no cadastro (ou que não ligou ao cadastro) vai num grupo próprio, por último (não some
    da conta)."""
    from ..campo.visao import SEM_CLUSTER as SEM_DO_CADASTRO

    def fazer():
        por: dict = {}
        for (cli, usi), ats in recorte(c, f):
            for a in ats:
                clu = (a.get("cluster") or "").strip()
                sem = not clu or clu == SEM_DO_CADASTRO
                g = por.setdefault(SEM_CLUSTER if sem else clu, {"sem": sem, "usinas": {}})
                u = g["usinas"].setdefault((cli, usi), {"soma": 0.0, "nrep": 0, "falhas": 0})
                x = c["idx"][a["cod"]]
                u["soma"] += x["soma"]
                u["nrep"] += x["nrep"]
                u["falhas"] += a.get("n") or 0
        out = []
        for nome, g in por.items():
            us = [{"nome": usi, "cliente": cli, "mttr": u["soma"] / u["nrep"] if u["nrep"] else None,
                   "falhas": u["falhas"], "com_reparo": u["nrep"]} for (cli, usi), u in g["usinas"].items()]
            us.sort(key=lambda u: (u["mttr"] is None, -(u["mttr"] or 0), G.ordem_pt(u["nome"])))
            soma, nrep = sum(u["soma"] for u in g["usinas"].values()), sum(u["nrep"] for u in g["usinas"].values())
            mttr = soma / nrep if nrep else None
            out.append({"nome": nome, "sem": g["sem"], "mttr": mttr, "cls": classe_mttr(mttr),
                        "falhas": sum(u["falhas"] for u in us), "com_reparo": nrep,
                        "clientes": sorted({u["cliente"] for u in us}, key=G.ordem_pt), "usinas": us})
        out.sort(key=lambda x: (x["sem"], x["mttr"] is None, -(x["mttr"] or 0), G.ordem_pt(x["nome"])))
        return out
    return _guardado(c, ("mttr", G.chave(f)[:3]), fazer)
