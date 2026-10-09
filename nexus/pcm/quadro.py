"""Quadro da semana: a programação em colunas por dia e a reprogramação de tarefas (09/10/2026, Levi: "Eles tem essa
visão [...] no site de PCM, gostaria que tenhamos uma visão dessa no Nexus também e consigamos reprogramar tarefas").

É o quadro da aba Semana do painel do PCM (`novo.html` do gridco-pcm-data: `vSemana`, `cardHTML`, `abrirDet`, a fila
`rp*`), com as mesmas contas: colunas pelos dias que têm tarefa, cartões em ordem de horário (40 por coluna, os demais
contados), turno pela hora de início (manhã 07–12, tarde 12–17, noite 17–07), trajetória da tarefa pelas semanas do
arquivo (OS + os 60 primeiros caracteres da tarefa).

O processo do PCM (Levi com o programador do PCM, 09/10/2026): a programação nasce na quinta; o supervisor e o gestor de
contrato a olham e passam ao PCM; o PCM faz as alterações; no fim da sexta ela é gerada de novo e substitui a de
quinta. "O ideal é que inicie da meia-noite de sábado e finalize na sexta": **criadas após o plano** conta as OS criadas
do sábado 00:00 antes da segunda até a sexta da semana. O painel cortava na DATA da geração (ou na sexta anterior): a OS
criada na sexta, que a geração da sexta já levou, contava como depois do plano (W41: 685 pelo painel, 533 pelo sábado).

Reprogramar não mexe na semana na hora: vira linha de observação, na gramática do motor (a do `rpLinha` do painel, que
o robô do PCM também lê), e vai para onde a semana ainda muda (`destino`):
- **semana em curso** (de segunda a sexta dela): o `Observacoes_Semana_Atual.txt` do repositório do PCM, que o robô do
  PCM aplica na rodada seguinte (reposiciona e empurra as conflitantes, tira a OS, puxa das pendentes);
- **semana que o Nexus gera** e ainda não começou (rascunho do Nexus ou publicada por ele): as observações da semana no
  Nexus (bloco 2 da tela Gerar), que valem na próxima geração;
- **semana gerada no PC do PCM** que ainda não começou (a W42, a última antes do full Nexus): só "Copiar tudo", para
  colar no painel do PCM, como hoje.
"""
import json
import re
import threading
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from . import comparar as C, geracao, historico_banco as HB, insumos as I, observacoes as O, publicar as PB
from .semana import _norm

_BRT = timezone(timedelta(hours=-3))
_trava = threading.Lock()

TETO_CARTOES = 40            # por coluna, como o painel: o resto é contado ("+N não exibidas")
DIAS = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")
NOMES_DIA = {"seg": "Segunda", "ter": "Terça", "qua": "Quarta", "qui": "Quinta", "sex": "Sexta", "sab": "Sábado",
             "dom": "Domingo"}
CURTO_DIA = {"seg": "Seg", "ter": "Ter", "qua": "Qua", "qui": "Qui", "sex": "Sex", "sab": "Sáb", "dom": "Dom"}
# Reprogramar só para dia útil: o motor e o robô do PCM só entendem seg a sex. O painel do PCM oferece "sáb", e a
# linha volta "dia não reconhecido" (programacao_v7 `_carregar_pins`, atualizacao_semanal `_parse_observacoes_atual`).
DIAS_REPROGRAMAR = O.DIAS
TURNOS = O.TURNOS
# Preventiva por sigla vai no "modo A" do motor: a sigla no campo de tarefas e o nome do equipamento no "só:"
SIGLAS = ("MPA", "MPS", "MPT", "MPM", "MPQ", "HANDOVER")
ESTADOS = ("Não iniciada", "Em progresso", "Pausada", "Finalizada")
TURNOS_CARTAO = ("Manhã", "Tarde", "Noite", "Sem horário")
FILTROS = ("equipe", "resp", "cliente", "tipo", "estado", "turno", "q")
REGISTRO = "reprogramacoes.jsonl"
CAB_ATUAL = "# Semana {semana}: reprogramação da semana em curso, gravada pelo Nexus"
_CAB_RE = re.compile(r"^#\s*Semana\s+(\d{4}-W\d{2})\b")
_RODADA_RE = re.compile(r"^\d{8}-\d{6}-\d{4}-W\d{2}(-[a-z0-9-]{1,60})?$")


class QuadroErro(RuntimeError):
    pass


def hoje() -> date:
    return datetime.now(_BRT).date()


# ── o que cada linha é ──────────────────────────────────────────────────────────────────────────────────────
def estado(r) -> str:
    """O estado da TAREFA em quatro, como o `_estado` do painel (o arquivo traz "Finalizados", "pausado"...)."""
    s = str(r.get("status_bd") or r.get("status") or "").lower()
    if "finaliz" in s or "conclu" in s:
        return "Finalizada"
    if "pausad" in s:
        return "Pausada"
    if "progress" in s or "execu" in s or "andamento" in s:
        return "Em progresso"
    return "Não iniciada"


def _minutos(h) -> int | None:
    m = re.match(r"^(\d{1,2}):(\d{2})", str(h or ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def turno(h) -> str:
    """Manhã 07–12, tarde 12–17, noite 17–07 (a noite atravessa a meia-noite: é o resto)."""
    m = _minutos(h)
    if m is None:
        return "Sem horário"
    if 420 <= m < 720:
        return "Manhã"
    if 720 <= m < 1020:
        return "Tarde"
    return "Noite"


def dia_de(valor) -> str:
    """ "Terça-feira (13/10)" -> "ter"; sábado e domingo também (o painel ganhou coluna para eles)."""
    n = _norm(valor)
    return next((d for d in DIAS if n.startswith(d)), "")


def usina_curta(u) -> str:
    """ "Thopen - Inhapi 1 - AL" -> "Inhapi 1 - AL": o cliente sai da frente, como no painel."""
    p = str(u or "").split(" - ")
    return " - ".join(p[1:]) if len(p) > 1 else str(u or "")


def classe_tipo(tipo) -> str:
    """A cor do tipo no cartão (classe CSS `q-t--<classe>`)."""
    t = _norm(tipo)
    if t.startswith("corretiva"):
        return "corretiva"
    if t.startswith("religamento"):
        return "religamento"
    if t.startswith("mpa"):
        return "mpa"
    if t.startswith("mps"):
        return "mps"
    if t.startswith(("mpm", "mpq", "mpt", "mpw", "preventiva")):
        return "preventiva"
    if t.startswith("inspe"):
        return "inspecao"
    if t.startswith("handover"):
        return "handover"
    if t.startswith("zeladoria"):
        return "zeladoria"
    return "outro"


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _horas(v) -> str:
    v = round(_num(v), 1)
    return (("%d" % v) if v == int(v) else ("%.1f" % v).replace(".", ",")) + " h"


# ── a semana do PCM: sábado 00:00 a sexta ───────────────────────────────────────────────────────────────────
def janela_do_plano(semana: str) -> tuple[date, date]:
    """(o sábado antes da segunda, a sexta). O plano fecha no fim da sexta anterior; o que nasce do sábado em diante
    chegou depois dele."""
    seg = HB.segunda(semana)
    return seg - timedelta(days=2), seg + timedelta(days=4)


def criada_apos_o_plano(r, janela: tuple[date, date]) -> bool:
    """A `dataCriacao` do arquivo é a hora de Brasília sem fuso (as criações se concentram das 8h às 17h, com o vale
    do almoço ao meio-dia): a data dela basta."""
    d = str(r.get("dataCriacao") or "")[:10]
    return bool(d) and janela[0].isoformat() <= d <= janela[1].isoformat()


# ── a linha de observação (contrato com o motor e com o robô do PCM) ────────────────────────────────────────
def sigla(tipo) -> str | None:
    t = re.sub(r"-.*$", "", str(tipo or "").upper()).strip()
    return ("Handover" if t == "HANDOVER" else t) if t in SIGLAS else None


def chave_da_tarefa(tarefa) -> str:
    """ "[Grid Co.] - MPA - Caixa d'água" -> "Caixa d'água" (o que vai no "só:"). Vírgula e ";" quebrariam a linha."""
    s = re.split(r"\s[-–]\s", str(tarefa or ""))[-1].strip()
    return s.split(",")[0].split(";")[0].strip()


def nome_da_tarefa(tarefa) -> str:
    return str(tarefa or "").split(",")[0].split(";")[0].strip()


def linha(os_id, dia: str, turno_: str = "", tarefa: str = "", tipo: str = "") -> str | None:
    """A linha que reprograma, a mesma do `rpLinha` do painel do PCM (e do `linha` de `static/pcm-quadro.js`):

        15269; não                                   a OS sai da semana (sempre a OS inteira)
        15269; qua  /  15269; qua; ; tarde           a OS inteira no dia (e no turno)
        15269; qua; MPM; tarde; só: Transformador    preventiva por sigla: só a tarefa daquele equipamento
        15289; ter; Inhapi: vedação dos postes       as outras: o nome da tarefa (até a 1ª vírgula)

    None quando a tarefa não tem nome que o motor reconheça (a linha viraria a OS inteira)."""
    os_s = str(os_id).strip()
    if dia == "não":
        return f"{os_s}; não"
    if not tarefa:
        return f"{os_s}; {dia}; ; {turno_}" if turno_ else f"{os_s}; {dia}"
    sig = sigla(tipo)
    if sig:
        ch = chave_da_tarefa(tarefa)
        partes = [os_s, dia, sig, turno_, f"só: {ch}" if ch else ""]
    else:
        nome = nome_da_tarefa(tarefa)
        if not nome:
            return None
        partes = [os_s, dia, nome, turno_]
    return "; ".join(v for i, v in enumerate(partes) if i < 3 or v)


def _alvo(regra: dict):
    if regra.get("tipo") == "fora":
        return (regra["os"], "fora")
    if regra.get("tipo") == "fixar":
        return (regra["os"], tuple(_norm(t) for t in regra.get("tarefas") or []),
                tuple(_norm(s) for s in regra.get("so") or []))
    return None


def mesclar(texto: str, novas: list[str]) -> tuple[str, dict]:
    """Junta as linhas novas ao texto das observações, sem duplicar ordem para a mesma OS:
    - a linha nova substitui a que já havia para o MESMO alvo (a OS, as tarefas e o "só:");
    - "OS; não" tira todas as linhas daquela OS (a OS sai inteira);
    - a OS inteira num dia tira as linhas por tarefa dela e o "não" (mudou de ideia);
    - uma linha por tarefa tira o "não" da OS.
    O resto (usinas, comentários, outras OS) fica igual e na mesma ordem. Devolve (texto, {novas, saem})."""
    linhas = (texto or "").replace("\r\n", "\n").split("\n")
    while linhas and not linhas[-1].strip():
        linhas.pop()
    originais = set(linhas)
    saem = []
    for nova in novas:
        r = O.ler_linha(nova)
        alvo = _alvo(r)
        if alvo is None:
            raise QuadroErro(f"linha que o motor não entende: {nova}")
        inteira = r["tipo"] == "fora" or not (r.get("tarefas") or r.get("so"))

        def conflita(l: str) -> bool:
            x = O.ler_linha(l)
            if x.get("os") != r["os"] or x.get("tipo") not in ("fora", "fixar"):
                return False
            return inteira or x["tipo"] == "fora" or _alvo(x) == alvo

        fica = []
        for l in linhas:
            if conflita(l):
                if l in originais and l not in saem and l.strip() != nova.strip():
                    saem.append(l)
            else:
                fica.append(l)
        linhas = fica + [nova]
    return "\n".join(linhas).strip("\n") + "\n", {"novas": list(novas), "saem": saem}


# ── a semana que o quadro mostra ────────────────────────────────────────────────────────────────────────────
def _os(v) -> str:
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return str(v or "").strip()


def _hora(v) -> str:
    if v in (None, ""):
        return ""
    if isinstance(v, (time, datetime)):
        return v.strftime("%H:%M")
    return str(v).strip()[:5]


def _cliente(ativo) -> str:
    """O `_extrair_cliente` do robô do PCM: "Cliente - Usina - UF" -> "Cliente"."""
    s = str(ativo or "").strip()
    if not s or "{" in s or "}" in s or " - " not in s:
        return ""
    return s.split(" - ", 1)[0].strip()


_CACHE_RASCUNHO: dict = {}


def semana_do_rascunho(caminho: Path, semana: str) -> dict:
    """A `saida/sombra.xlsx` de uma rodada como semana do quadro, nas chaves do `banco_dados.json` (as do
    `gerar_pcm_json.py` do robô). A planilha não traz o que o robô busca no Fracttal depois (criação, relatório,
    status da OS): o cartão sai sem isso. Guardada pela data do arquivo (ler ~1 MB leva ~1 s)."""
    chave = (str(caminho), caminho.stat().st_mtime_ns)
    feito = _CACHE_RASCUNHO.get(chave)
    if feito is not None:
        return feito
    blocos, pend = C.linhas_da_planilha(caminho)
    rows = [{"cliente": _cliente(b.get("Ativo (Usina)")), "usina": str(b.get("Ativo (Usina)") or "").strip(),
             "cluster": str(b.get("Equipe") or "").strip(), "tipo": str(b.get("Tipo") or "").strip(),
             "dia": str(b.get("Dia") or "").split("(")[0].strip(), "os_id": _os(b.get("OSs ID")),
             "codigo": str(b.get("Código Equipamento") or "").strip(), "tarefa": str(b.get("Tarefa") or ""),
             "responsavel": str(b.get("Responsável") or "").strip(),
             "criticidade": str(b.get("RPN/Prioridade") if b.get("RPN/Prioridade") is not None else ""),
             "etiquetas": str(b.get("Etiquetas") or ""), "status": str(b.get("Estado Tarefa (antes)") or ""),
             "duracao": _num(b.get("Duração (h)")), "h_ini": _hora(b.get("Hora Início")), "h_fim": _hora(b.get("Hora Fim")),
             "desloc": _num(b.get("Desloc (h)")), "reprog": str(b.get("Reprogramada") or ""),
             "vezes": int(_num(b.get("Nº vezes programada")) or 1), "termo": str(b.get("Termografia") or ""),
             "paralelo": str(b.get("Paralelo (terceirizada)") or "")} for b in blocos]
    pendentes = [{"os_id": _os(p.get("OSs ID")), "usina": str(p.get("Ativo") or "").strip(),
                  "cliente": _cliente(p.get("Ativo")), "cluster": str(p.get("Equipe") or "").strip(),
                  "tarefa": str(p.get("Tarefa") or ""), "tipo": str(p.get("Tipo") or "").strip(),
                  "duracao": _num(p.get("Duração (h)")), "motivo": str(p.get("Motivo") or "")} for p in pend]
    seg = HB.segunda(semana)
    out = {"week": semana, "num": seg.isocalendar()[1], "rows": rows, "pendentes": pendentes,
           "dates": {d: (seg + timedelta(days=i)).strftime("%d/%m") for i, d in enumerate(DIAS[:5])},
           "label": f"Semana {seg.isocalendar()[1]} · {seg.strftime('%d/%m')} a {(seg + timedelta(days=4)).strftime('%d/%m/%Y')}"}
    if len(_CACHE_RASCUNHO) > 8:
        _CACHE_RASCUNHO.clear()
    _CACHE_RASCUNHO[chave] = out
    return out


def pasta_da_rodada(config, rid: str) -> Path | None:
    """A pasta de uma rodada pelo id, também as de prova ("-foto..."), que a lista da tela Gerar não mostra."""
    if not _RODADA_RE.match(rid or ""):
        return None
    p = geracao.pasta_trabalho(config) / "geracoes" / rid
    return p if (p / "status.json").is_file() and (p / "saida" / "sombra.xlsx").is_file() else None


def rodada_ok(config, rid: str) -> dict | None:
    """O status de uma rodada que terminou bem (também as de prova), com a semana dela; None se não serve ao quadro."""
    p = pasta_da_rodada(config, rid)
    if not p:
        return None
    try:
        st = json.loads((p / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if st.get("estado") != "ok" or not geracao.SEMANA_RE.match(st.get("semana") or ""):
        return None
    return dict(st, id=rid)


def rascunhos(config, dia: date | None = None) -> list[dict]:
    """A geração mais recente de cada semana que ainda não começou (rodada terminada, sem as de prova). A da semana em
    curso fica de fora: em 09/10, a sombra da W41 de 02/10 aparecia como rascunho da semana que o campo já fazia."""
    dia = dia or hoje()
    out = {}
    for st in geracao.ultimas(config, 40):
        w = st.get("semana") or ""
        if st.get("estado") != "ok" or not geracao.SEMANA_RE.match(w) or HB.segunda(w) <= dia:
            continue
        if w not in out and pasta_da_rodada(config, st["id"]):
            out[w] = {"semana": w, "rodada": st["id"], "quando": st.get("fim") or st.get("inicio") or "",
                      "publicada": bool(st.get("publicacao"))}
    return sorted(out.values(), key=lambda r: r["semana"])


def nexus_gera(config, semana: str) -> bool:
    """O Nexus gerou (rodada terminada) ou publicou esta semana: as observações dela no Nexus valem."""
    return any(st.get("semana") == semana and st.get("estado") == "ok" for st in geracao.ultimas(config, 40))


def destino(semana: str, fonte: str, gera_no_nexus: bool, dia: date | None = None) -> dict:
    """Para onde vai a reprogramação desta semana: {"id": atual | nexus | copiar | None, "texto": o porquê}."""
    dia = dia or hoje()
    seg = HB.segunda(semana)
    sex = seg + timedelta(days=4)
    if dia > sex:
        return {"id": None, "texto": "A semana já acabou: reprogramar vale para a semana em curso e as próximas."}
    if fonte == "publicada" and seg <= dia:
        return {"id": "atual", "texto": "Semana em curso: as linhas vão para os ajustes da semana em curso no repositório "
                                        "do PCM, que o robô do PCM aplica na rodada seguinte (até 15 minutos)."}
    if fonte == "rascunho" or gera_no_nexus:
        return {"id": "nexus", "texto": f"As linhas vão para as observações da {semana} no Nexus (bloco 2 da tela "
                                        "Gerar) e valem na próxima geração da semana."}
    return {"id": "copiar", "texto": "Esta semana foi gerada no PC do PCM: copie as linhas e cole no painel do PCM, "
                                     "como hoje. A partir da semana que o Nexus gerar, elas ficam gravadas aqui."}


# ── o quadro ────────────────────────────────────────────────────────────────────────────────────────────────
def opcoes(rows: list[dict]) -> dict:
    def _v(campo):
        return sorted({str(r.get(campo) or "").strip() for r in rows} - {""}, key=_norm)
    return {"equipe": _v("cluster"), "resp": _v("responsavel"), "cliente": _v("cliente"), "tipo": _v("tipo"),
            "estado": list(ESTADOS), "turno": list(TURNOS_CARTAO)}


def filtrar(rows: list[dict], f: dict) -> list[dict]:
    termo = _norm(f.get("q"))
    out = []
    for r in rows:
        if f.get("equipe") and str(r.get("cluster") or "").strip() != f["equipe"]:
            continue
        if f.get("resp") and str(r.get("responsavel") or "").strip() != f["resp"]:
            continue
        if f.get("cliente") and str(r.get("cliente") or "").strip() != f["cliente"]:
            continue
        if f.get("tipo") and str(r.get("tipo") or "").strip() != f["tipo"]:
            continue
        if f.get("estado") and estado(r) != f["estado"]:
            continue
        if f.get("turno") and turno(r.get("h_ini")) != f["turno"]:
            continue
        if termo and termo not in _norm(" ".join(str(r.get(c) or "") for c in ("os_id", "usina", "tarefa", "cluster",
                                                                                "codigo"))):
            continue
        out.append(r)
    return out


def filtrar_pendentes(pend: list[dict], f: dict) -> list[dict]:
    """As pendentes têm cliente, usina, equipe e tipo; responsável, situação e turno não existem nelas."""
    termo = _norm(f.get("q"))
    out = []
    for p in pend:
        if f.get("equipe") and str(p.get("cluster") or "").strip() != f["equipe"]:
            continue
        if f.get("cliente") and str(p.get("cliente") or "").strip() != f["cliente"]:
            continue
        if f.get("tipo") and str(p.get("tipo") or "").strip() != f["tipo"]:
            continue
        if termo and termo not in _norm(" ".join(str(p.get(c) or "") for c in ("os_id", "usina", "tarefa", "cluster"))):
            continue
        out.append(p)
    return out


def _chave(r) -> str:
    return f"{r.get('os_id') or ''}\u0000{str(r.get('tarefa') or '')[:60]}"


def _indices(semanas: list[tuple[str, list[dict]]]) -> list[tuple[str, dict]]:
    """[(semana, {chave: linha})], do mais antigo para o mais novo; a mesma chave duas vezes na semana: vale a última,
    como o `Map.set` do painel."""
    out = []
    for wk, rows in sorted(semanas, key=lambda x: x[0]):
        idx = {}
        for r in rows:
            idx[_chave(r)] = r
        out.append((wk, idx))
    return out


def trajetoria(r, indices, atual: str) -> list[dict]:
    k = _chave(r)
    tl = []
    for wk, idx in indices:
        o = idx.get(k)
        if o is None:
            continue
        tl.append({"w": "S" + wk.split("-W")[-1] if "-W" in wk else wk, "d": CURTO_DIA.get(dia_de(o.get("dia")), ""),
                   "ini": o.get("h_ini") or "", "fim": o.get("h_fim") or "", "st": estado(o),
                   "v": int(_num(o.get("vezes"))), "ativa": wk == atual})
    return tl


def _d(v) -> str:
    x = str(v or "")
    return f"{x[8:10]}/{x[5:7]}/{x[:4]}" if len(x) >= 10 and x[4] == "-" else ""


def _item(r, pend: bool, tl: list[dict], dia_data: dict) -> dict:
    """O que a janela da OS mostra (chaves curtas, como o `_linha` do painel: vai uma por cartão na página). Campo
    vazio não vai: a janela pula a linha sem valor, e as 1.697 pendentes da W41 pesavam 1 MB com as chaves vazias."""
    d = dia_de(r.get("dia"))
    x = {"os": str(r.get("os_id") or ""), "ss": str(r.get("solic_orig") or ""), "t": str(r.get("tarefa") or ""),
            "uc": usina_curta(r.get("usina")), "cli": str(r.get("cliente") or ""),
            "cl": str(r.get("cluster") or ""), "resp": str(r.get("responsavel") or ""),
            "ros": str(r.get("resp_os") or ""), "tp": str(r.get("tipo") or ""), "tc": classe_tipo(r.get("tipo")),
            "etq": _etiquetas(r.get("etiquetas")), "st": estado(r) if not pend else "",
            "d": NOMES_DIA.get(d, ""), "data": dia_data.get(d, ""), "ini": str(r.get("h_ini") or ""),
            "fim": str(r.get("h_fim") or ""), "h": _horas(r.get("duracao")), "desl": _num(r.get("desloc")),
            "rol": int(_num(r.get("vezes"))), "rep": _norm(r.get("reprog")) == "sim", "cod": str(r.get("codigo") or ""),
            "cri": str(r.get("criticidade") or ""), "dcri": _d(r.get("dataCriacao")), "dprog": _d(r.get("dataProgramada")),
            "dfim": _d(r.get("dataFinal")), "sp": str(r.get("statusPai") or ""), "nova": str(r.get("nova_os") or ""),
            "par": str(r.get("paralelo") or ""), "termo": str(r.get("termo") or ""),
            "rol_txt": str(r.get("rolagem") or ""), "rel": str(r.get("relatorio") or "")[:600],
            "mot": str(r.get("motivo") or ""), "pend": pend, "tl": tl if len(tl) > 1 else []}
    return {k: v for k, v in x.items() if k in ("os", "t") or v not in ("", None, [], False, 0)}


def _etiquetas(v) -> str:
    """O campo vem como JSON do Fracttal ('[{"description": ...}]'); o painel mostra só as descrições."""
    t = str(v or "").strip()
    if not t or t == "nan":
        return ""
    try:
        j = json.loads(t)
    except ValueError:
        return t
    if isinstance(j, list):
        return " | ".join(str((o or {}).get("description") or "") for o in j if isinstance(o, dict) and o.get("description"))
    return ""


TETO_PENDENTES = 150         # acima disso a lista de pendentes só abre a pedido (a W41 tinha 1.697: 3 MB de página)


def montar(sem: dict, publicadas: list[dict], filtros: dict, todos: bool = False,
           mostrar_pendentes: bool | None = None) -> dict:
    """O quadro de uma semana. `sem`: {week, rows, pendentes, dates, ...}; `publicadas`: as semanas do arquivo do App
    (para a trajetória). As contas do cabeçalho de cada dia saem do conjunto FILTRADO, como no painel (senão o
    cabeçalho diria 289 com 4 cartões na coluna); as colunas, dos dias que a semana inteira tem. As pendentes vão
    linha a linha só até TETO_PENDENTES ou a pedido (`mostrar_pendentes=True`); as tarefas de cada OS (o "a OS inteira
    (N tarefas)" da janela) vão uma vez por OS, em `oss`, e não em cada cartão."""
    rows = sem.get("rows") or []
    week = sem["week"]
    janela = janela_do_plano(week)
    tem_criacao = any(r.get("dataCriacao") for r in rows)
    sel = filtrar(rows, filtros)
    pend = filtrar_pendentes(sem.get("pendentes") or [], filtros)
    seg = HB.segunda(week)
    dia_data = {d: (sem.get("dates") or {}).get(d) or (seg + timedelta(days=i)).strftime("%d/%m")
                for i, d in enumerate(DIAS)}

    # trajetória: as semanas publicadas até esta (um rascunho entra por cima da publicada da mesma semana)
    sems = [(s["week"], s.get("rows") or []) for s in publicadas if s.get("week") and s["week"] < week]
    sems.append((week, rows))
    indices = _indices(sems)
    # as tarefas de cada OS na semana (agenda e pendentes): o "OS inteira (N tarefas)" da janela
    por_os: dict[str, list[dict]] = {}
    for r, eh_pend in [(r, False) for r in rows] + [(p, True) for p in sem.get("pendentes") or []]:
        lst = por_os.setdefault(str(r.get("os_id") or ""), [])
        t = str(r.get("tarefa") or "")
        if not any(x["t"] == t for x in lst):
            lst.append({"t": t, "tp": str(r.get("tipo") or ""), "pend": eh_pend})

    itens: list[dict] = []
    oss: dict[str, list[dict]] = {}

    def _novo_item(r, pend_):
        os_s = str(r.get("os_id") or "")
        if len(por_os.get(os_s, [])) > 1:
            oss[os_s] = por_os[os_s]
        itens.append(_item(r, pend_, trajetoria(r, indices, week) if not pend_ else [], dia_data))
        return len(itens) - 1

    presentes = {dia_de(r.get("dia")) for r in rows}
    por_dia: dict[str, list[dict]] = {}
    for r in sel:
        por_dia.setdefault(dia_de(r.get("dia")), []).append(r)
    mx = max([len(por_dia.get(d, [])) for d in DIAS if d in presentes] or [0]) or 1
    colunas = []
    for d in DIAS:
        if d not in presentes:
            continue
        todos_d = sorted(por_dia.get(d, []), key=lambda r: (_minutos(r.get("h_ini")) is None,
                                                             _minutos(r.get("h_ini")) or 0))
        mostra = todos_d if todos else todos_d[:TETO_CARTOES]
        cartoes = []
        for r in mostra:
            cartoes.append({"i": _novo_item(r, False), "os": str(r.get("os_id") or ""), "t": str(r.get("tarefa") or ""),
                            "uc": usina_curta(r.get("usina")), "tp": str(r.get("tipo") or ""),
                            "tc": classe_tipo(r.get("tipo")), "st": estado(r), "ini": str(r.get("h_ini") or ""),
                            "tur": turno(r.get("h_ini")), "h": _horas(r.get("duracao")),
                            "rep": _norm(r.get("reprog")) == "sim", "rol": int(_num(r.get("vezes")))})
        n = len(todos_d)
        colunas.append({"id": d, "nome": NOMES_DIA[d], "data": dia_data[d], "n": n,
                        "horas": _horas(sum(_num(r.get("duracao")) for r in todos_d)),
                        "novas": sum(1 for r in todos_d if criada_apos_o_plano(r, janela)) if tem_criacao else None,
                        "carga": round(100.0 * n / mx, 1), "pico": n == mx and n > 0, "cartoes": cartoes,
                        "ocultos": n - len(mostra)})

    mostra_pend = (len(pend) <= TETO_PENDENTES) if mostrar_pendentes is None else mostrar_pendentes
    grupos: dict[str, list[dict]] = {}
    for p in (pend if mostra_pend else []):
        grupos.setdefault(str(p.get("usina") or "Sem usina"), []).append(p)
    pendentes = []
    for u in sorted(grupos, key=_norm):
        lst = [{"i": _novo_item(p, True), "os": str(p.get("os_id") or ""), "t": str(p.get("tarefa") or ""),
                "tp": str(p.get("tipo") or ""), "h": _horas(p.get("duracao")), "mot": str(p.get("motivo") or "")}
               for p in grupos[u]]
        pendentes.append({"usina": u, "uc": usina_curta(u), "itens": lst})

    return {"colunas": colunas, "itens": itens, "oss": oss, "pendentes": pendentes, "pend_mostradas": mostra_pend,
            "total": len(sel), "total_semana": len(rows),
            "sem_dia": sum(1 for r in sel if not dia_de(r.get("dia"))),
            "pend_total": len(sem.get("pendentes") or []), "pend_sel": len(pend),
            "horas": _horas(sum(_num(r.get("duracao")) for r in sel)), "tem_criacao": tem_criacao,
            "novas": sum(1 for r in sel if criada_apos_o_plano(r, janela)) if tem_criacao else None,
            "janela": janela, "opcoes": opcoes(rows)}


# ── a fila que volta da página ──────────────────────────────────────────────────────────────────────────────
def linhas_da_fila(sem: dict, itens: list) -> tuple[list[str], list[str]]:
    """(linhas, problemas) dos itens da fila que a página mandou: {os, tarefa, dia, turno}. O tipo e a tarefa vêm da
    SEMANA, não da página: só entra OS e tarefa que a semana tem (agenda ou pendentes), e nenhum texto livre chega ao
    arquivo que o motor e o robô do PCM leem."""
    tarefas: dict[str, dict[str, str]] = {}
    for r in (sem.get("rows") or []) + (sem.get("pendentes") or []):
        tarefas.setdefault(str(r.get("os_id") or "").strip(), {}).setdefault(str(r.get("tarefa") or ""),
                                                                            str(r.get("tipo") or ""))
    linhas, problemas, vistos = [], [], {}
    for it in itens if isinstance(itens, list) else []:
        if not isinstance(it, dict):
            continue
        os_s = str(it.get("os") or "").strip()
        dia = str(it.get("dia") or "").strip()
        tur = str(it.get("turno") or "").strip()
        tarefa = str(it.get("tarefa") or "")
        if not os_s.isdigit() or os_s not in tarefas:
            problemas.append(f"OS {os_s[:12] or '(vazia)'}: não está nesta semana")
            continue
        if dia not in DIAS_REPROGRAMAR and dia != "não":
            problemas.append(f"OS {os_s}: dia inválido ({dia[:12] or 'vazio'}); use segunda a sexta")
            continue
        if tur and tur not in TURNOS:
            tur = {"manha": "manhã"}.get(tur, "")
            if not tur:
                problemas.append(f"OS {os_s}: turno inválido")
                continue
        if dia == "não":
            tarefa, tur = "", ""
        elif tarefa and tarefa not in tarefas[os_s]:
            problemas.append(f"OS {os_s}: a tarefa não está nesta semana")
            continue
        l = linha(os_s, dia, tur, tarefa, tarefas[os_s].get(tarefa, ""))
        if l is None:
            problemas.append(f"OS {os_s}: a tarefa não tem nome que o motor reconheça; reprograme a OS inteira")
            continue
        alvo = (os_s, tarefa)
        if alvo in vistos:                 # a mesma tarefa duas vezes na fila: vale a última
            linhas.remove(vistos[alvo])
        vistos[alvo] = l
        linhas.append(l)
    return linhas, problemas


# ── gravar ──────────────────────────────────────────────────────────────────────────────────────────────────
def registrar(config, item: dict) -> None:
    """O registro de quem reprogramou o quê (um JSON por linha, na pasta de trabalho do PCM)."""
    p = geracao.pasta_trabalho(config) / REGISTRO
    with _trava:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def gravadas(config, semana: str, n: int = 12) -> list[dict]:
    p = geracao.pasta_trabalho(config) / REGISTRO
    try:
        linhas = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for l in reversed(linhas):
        try:
            x = json.loads(l)
        except ValueError:
            continue
        if x.get("semana") == semana:
            out.append(x)
            if len(out) >= n:
                break
    return out


def salvar_no_nexus(config, semana: str, linhas: list[str], quem: str) -> dict:
    """As linhas entram nas observações da semana no Nexus (o texto que a tela Gerar mostra e o motor recebe)."""
    trab = geracao.pasta_trabalho(config)
    texto, herdada = I.observacoes_efetivas(trab, semana)
    novo, res = mesclar(texto, linhas)
    I.salvar_observacoes(trab, semana, novo, autor=f"quadro da semana · {quem}")
    registrar(config, {"quando": datetime.now(_BRT).isoformat(timespec="seconds"), "quem": quem, "semana": semana,
                       "destino": "nexus", "linhas": linhas, "saem": res["saem"]})
    return dict(res, herdada_de=herdada)


def semana_do_cabecalho(texto: str) -> str | None:
    for l in (texto or "").splitlines():
        if l.strip():
            m = _CAB_RE.match(l.strip())
            return m.group(1) if m else None
    return None


def novo_texto_atual(texto: str, semana: str, linhas: list[str], apagar_sem_semana: bool = False) -> tuple[str, dict]:
    """O `Observacoes_Semana_Atual.txt` depois de juntar as linhas. O arquivo vale para qualquer semana que estiver em
    curso: linha que ficou da semana passada se aplicaria à nova. Por isso o Nexus escreve a semana no cabeçalho e,
    quando o cabeçalho é de outra semana, o que estava lá sai. Sem cabeçalho (gravado pelo painel do PCM), fica, a não
    ser que a pessoa peça para apagar."""
    sem_cab = semana_do_cabecalho(texto)
    corpo = (texto or "").replace("\r\n", "\n").split("\n")
    if sem_cab:
        i = next(i for i, l in enumerate(corpo) if l.strip())
        corpo = corpo[:i] + corpo[i + 1:]
    saem_semana = []
    if (sem_cab and sem_cab != semana) or (not sem_cab and apagar_sem_semana):
        saem_semana = [l for l in corpo if l.strip()]
        corpo = []
    mesclado, res = mesclar("\n".join(corpo), linhas)
    final = CAB_ATUAL.format(semana=semana) + "\n" + mesclado.lstrip("\n")
    return final, dict(res, saem_outra_semana=saem_semana, semana_antes=sem_cab)


def ler_atual(config) -> dict:
    """O `Observacoes_Semana_Atual.txt` do repositório do PCM agora: {texto, sha, existe, semana, erro, repo}."""
    tok, de_onde = PB.token(config)
    repo, ramo = PB.repositorio(config)
    out = {"repo": repo, "ramo": ramo, "token": de_onde, "texto": "", "sha": "", "existe": False, "semana": None,
           "erro": ""}
    if not tok:
        out["erro"] = "sem token do GitHub (NEXUS_PCM_GITHUB_TOKEN)"
        return out
    try:
        lido = PB._ler(PB._sessao(config), tok, repo, ramo, PB.OBS_ATUAL)
    except Exception as ex:      # noqa: BLE001 — rede, GitHub fora: a tela diz
        out["erro"] = f"não consegui ler o repositório do PCM ({type(ex).__name__})"
        return out
    if lido:
        out.update(existe=True, sha=lido.get("sha") or "", texto=lido["bytes"].decode("utf-8", errors="replace"))
        out["semana"] = semana_do_cabecalho(out["texto"])
    return out


def aplicar_na_semana_em_curso(config, semana: str, linhas: list[str], quem: str, sha_visto: str,
                               apagar_sem_semana: bool = False) -> dict:
    """Grava as linhas no `Observacoes_Semana_Atual.txt` do repositório do PCM (o PUT do `publicar.py`) e confere
    relendo. `sha_visto` é o do arquivo que a pessoa conferiu na tela: se o arquivo mudou desde então (o painel do PCM
    grava no mesmo arquivo), não grava."""
    if not linhas:
        raise QuadroErro("nenhuma linha para gravar")
    with PB._trava:
        tok, de_onde = PB.token(config)
        if not tok:
            raise QuadroErro("sem token do GitHub: ponha NEXUS_PCM_GITHUB_TOKEN no .env do Nexus")
        repo, ramo = PB.repositorio(config)
        s = PB._sessao(config)
        atual = PB._ler(s, tok, repo, ramo, PB.OBS_ATUAL)
        if ((atual or {}).get("sha") or "") != (sha_visto or ""):
            raise QuadroErro("o arquivo de ajustes da semana em curso mudou desde que você abriu a confirmação; "
                             "confira de novo")
        texto = atual["bytes"].decode("utf-8", errors="replace") if atual else ""
        novo, res = novo_texto_atual(texto, semana, linhas, apagar_sem_semana)
        dados = novo.encode("utf-8")
        commit = PB._gravar(s, tok, repo, ramo, PB.OBS_ATUAL, dados,
                            f"chore: Nexus reprograma a semana em curso ({semana}, {len(linhas)} "
                            f"{'linha' if len(linhas) == 1 else 'linhas'})")
        lido = PB._ler(s, tok, repo, ramo, PB.OBS_ATUAL)
        if not lido or PB._sha256(lido["bytes"]) != PB._sha256(dados):
            raise QuadroErro(f"o repositório não tem o arquivo enviado (commit {commit}); confira no GitHub")
    registrar(config, {"quando": datetime.now(_BRT).isoformat(timespec="seconds"), "quem": quem, "semana": semana,
                       "destino": "atual", "linhas": linhas, "saem": res["saem"],
                       "saem_outra_semana": res["saem_outra_semana"], "commit": commit, "token": de_onde})
    return dict(res, commit=commit, texto=novo)
