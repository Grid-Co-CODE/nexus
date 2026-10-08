"""A programação semanal do PCM como fato (`fato_programacao`, passo 6b do desenho Kimball de 08/10/2026). PURO: não lê
rede, não lê arquivo, não grava. Quem lê a fonte é `nexus.pcm.fonte.ler(config).dados` (o `banco_dados.json` que o
App de Campo e o painel do PCM leem); quem grava é a carga, e só depois da decisão do Levi (abaixo).

Até 08/10/2026 a programação só existia fora do banco: o Nexus a lia ao vivo e o histórico estava no git do PCM.

**Grão: 1 linha = 1 bloco de agenda de uma tarefa planejada na semana** (semana × OS × código × tarefa × dia × hora de
início). Medido em 08/10 nas 3.738 linhas planejadas: 0 repetições nessa chave. A mesma tarefa pode ter 2 blocos
(partida em dois dias ou horários: 37 casos); `primeiro_bloco` = 1 só no primeiro, e `SUM(primeiro_bloco)` dá o número
de tarefas programadas. Tipo: snapshot periódico semanal (o plano publicado + o estado da tarefa na última leitura).

**O que NÃO entra, e por quê:**
- As linhas `foraDoPlano` (2.159 de 5.897 em 08/10, 37%): o robô do PCM acrescenta à semana as tarefas FINALIZADAS no
  Fracttal que não estavam no plano, no dia em que acabaram e com a duração real. Não são bloco de agenda: são
  execução, outro grão (regra da casa: fonte que mistura grãos são dois fatos). Somadas à programação, inflariam as
  "tarefas programadas" em 58% e a aderência. Ficam fora e contam no relatório (`fora_do_plano`).
- As `pendentes` (o que não coube na semana): backlog, outro grão.
- `relatorio` (texto livre), `etiquetas` (JSON), `historico` (sempre vazio), `mttr_*` (sempre 0): a API do banco é de
  leitura aberta e texto livre pode ter nome. `dataProgramada` também fica fora: é a data programada da OS no Fracttal,
  não a do bloco (bate com o dia do bloco em só 362 de 3.738 linhas).
- Nenhum nome de pessoa: técnico (`resp_os`) e responsável O&M (`responsavel`) viram `pessoa_id` só quando o nome é
  de UMA pessoa do cadastro; o resto fica vazio (nunca um ID chutado).

**Usina, equipe e responsável são os ATUAIS do ativo, não os do dia do plano:** o robô do PCM reescreve `usina`,
`cluster` e `responsavel` pelo cadastro de hoje (`usinaAtual`, `clusterAtual`, `responsavelAtual`) a cada rodada.
Enquanto a semana está na fonte, a usina que muda de equipe muda a equipe das semanas passadas também. A equipe "da
época" sai do `usinas_historico`, não deste fato.

**Datas.** `data_id_semana` = a segunda-feira da semana ISO. `data_id_programada` = a segunda + o dia da semana do
bloco, conferido com o `dates` (dd/mm) da própria semana: discordou, fica vazio (dado contraditório não vira dia). O
ano sai da semana ISO, não do dd/mm: a 2025-W01 começa em 30/12/2024. `dataCriacao` e `dataFinal` já vêm no horário
de Brasília sem fuso (o robô do PCM converte de America/Sao_Paulo e tira o fuso); com fuso, converte-se.

**Medidas.** `duracao` e `desloc` chegam em HORAS e viram minutos. `vezes_programada_qtd` é o "Nº vezes programada"
da planilha do PCM, que conta a 1ª vez: em 08/10, as 1.381 linhas com Reprogramada = "Não" têm todas 1. Chamá-lo de
"vezes reprogramada" faria a soma contar como reprogramação a primeira programação. A criticidade mistura dois
atributos na mesma coluna: rótulo (Baixo, Médio, Alto, Muito alto: 262 linhas planejadas) e RPN em pontos (3.476):
vira `criticidade_rotulo` e `criticidade_pts`.

**A chave da tarefa.** `tarefa_chave` = sha1 do texto da tarefa sem acento, sem caixa e com espaço único: o texto não
entra no fato e a chave casa programado × executado. Medido em 08/10 contra os fechamentos do App: dos 716 pares (OS,
código) que estão nos dois, 715 casam também a tarefa.

**Herda do passo 0 (o pior caso dos cinco fatos).** A fonte guarda só as 4 semanas mais recentes. Com a troca integral
do livro a cada hora, o fato nunca passa de 4 semanas e cada semana some 4 semanas depois. Por isso a gravação NÃO
liga sem a decisão do Levi: o passo 0 ou o `mesclar_semanas` (a semana da fonte substitui a mesma semana no banco; as
outras ficam). A semana regerada troca as próprias linhas (o bloco que mudou de dia ou hora ganha outro
`programacao_id`): é snapshot, de propósito.
"""
import hashlib
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from ..campo.ligacao_cadastro import _norm as norm_nome
from .calendario import data_id as _data_id
from .fatos import ligar_equipamento
from .fatos import tarefa_chave as _tarefa_chave_unica

LIVRO = "nexus_programacao"
NOME_LIVRO = "Nexus · programação semanal do PCM (1 linha = 1 bloco de agenda) e a qualidade da ligação"
ABA = "fato_programacao"
# Para o catálogo (o mesmo molde de fato_ronda.py e fato_pt.py)
FATO, TIPO = "programacao", "snapshot_periodico"
GRAO = "1 linha = 1 bloco de agenda de uma tarefa planejada na semana (semana × OS × código × tarefa × dia × hora)"
CHAVE = ("programacao_id",)
FONTES = (("pcm · banco_dados.json", "semanas[].rows sem foraDoPlano"),)
LIVRO_ORIGEM = "pcm · banco_dados.json"
JANELA_ORIGEM = "4 semanas (PCM)"
# (coluna, unidade, soma). Os minutos somam entre tarefas e semanas (cada semana é o seu plano); o nº de vezes e o RPN
# são atributo da tarefa, não se somam (média, máximo). Indicador 1/0 soma: SUM(primeiro_bloco) = tarefas.
MEDIDAS = (("duracao_min", "min", "aditiva"), ("deslocamento_min", "min", "aditiva"),
           ("vezes_programada_qtd", "qtd", "nao"), ("criticidade_pts", "pts", "nao"),
           *((c, "1/0", "aditiva") for c in ("primeiro_bloco", "reprogramada", "termo", "paralelo", "nova_os",
                                              "rolada")))

CAB_PROGRAMACAO = [
    "programacao_id", "data_id_semana", "data_id_programada", "data_id_criacao_os", "data_id_fim_execucao",
    "usina_id", "usina_ligada_por", "equipe_id", "pessoa_id_tecnico", "pessoa_id_responsavel", "equipamento_id",
    "equipamento_ligado_por", "codigo_ativo", "os", "tarefa_chave", "tipo_tarefa", "criticidade_rotulo", "criticidade_pts", "primeiro_bloco",
    "duracao_min", "deslocamento_min", "hora_inicio", "reprogramada", "vezes_programada_qtd", "termo", "paralelo",
    "nova_os", "rolada", "status_execucao", "status_os", "semana_gerada_em", "lido_em"]

_BRT = timezone(timedelta(hours=-3))
DIAS_CURTOS = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")
ROTULOS_CRITICIDADE = ("Baixo", "Médio", "Alto", "Muito alto")
# Estado da TAREFA no Fracttal, como o robô do PCM escreve (normaliza IN_PROGRESS, STARTED... para estes quatro)
STATUS_EXECUCAO = {"finalizados": "finalizada", "finalizada": "finalizada", "nao iniciada": "nao_iniciada",
                   "em progresso": "em_progresso", "pausado": "pausada", "pausada": "pausada"}
# Status da OS (o "pai" da tarefa) no Fracttal
STATUS_OS = {"em processo": "em_processo", "verificacao": "em_verificacao", "em verificacao": "em_verificacao",
             "finalizados": "finalizada", "finalizada": "finalizada"}
# Colunas que vão como número; o resto, texto. Usado para devolver ao tipo o que o banco devolve como texto.
_INTEIRAS = {"data_id_semana", "data_id_programada", "data_id_criacao_os", "data_id_fim_execucao", "usina_id",
             "equipe_id", "pessoa_id_tecnico", "pessoa_id_responsavel", "equipamento_id", "primeiro_bloco",
             "duracao_min", "deslocamento_min", "reprogramada", "vezes_programada_qtd", "termo", "paralelo", "nova_os",
             "rolada"}


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _sem_acento(v) -> str:
    return " ".join(unicodedata.normalize("NFKD", _txt(v)).encode("ascii", "ignore").decode().lower().split())


def _num(v):
    """Número da fonte (12, 12.0, "12", "1,5"); int quando é inteiro. Texto que não é número = None."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int):
        return v                       # sem passar por float: o equipamento_id tem 52 bits
    if isinstance(v, float):
        x = v
    else:
        t = _txt(v).replace(",", ".")
        if re.fullmatch(r"-?\d+", t):
            return int(t)
        try:
            x = float(t)
        except ValueError:
            return None
    if x != x or x in (float("inf"), float("-inf")):
        return None
    return int(x) if x.is_integer() else x


def _id(v):
    x = _num(v)
    return int(x) if isinstance(x, (int, float)) and float(x).is_integer() and x > 0 else None


def _qtd(v):
    """Contagem: inteiro >= 0; o resto = None."""
    x = _num(v)
    return int(x) if isinstance(x, (int, float)) and float(x).is_integer() and x >= 0 else None


# ── as funções da semana e do dia ─────────────────────────────────────────────────────────────────────────────────
def _segunda(week) -> date | None:
    m = re.fullmatch(r"(\d{4})-W(\d{1,2})", _txt(week).upper())
    if not m:
        return None
    try:
        return date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)
    except ValueError:
        return None


def segunda_da_semana(week) -> int | None:
    """'2026-W41' -> 20261005 (a segunda-feira da semana ISO). Semana inválida = None."""
    d = _segunda(week)
    return _data_id(d) if d else None


def dia_da_semana(dia) -> int | None:
    """'Terça-feira', 'Terça-feira (29/09) [NOTURNO]', 'ter' -> 1 (segunda = 0). Fora da semana = None."""
    n = _sem_acento(dia)
    return next((i for i, p in enumerate(DIAS_CURTOS) if n.startswith(p)), None)


def data_do_bloco(semana, dia) -> int | None:
    """O dia do bloco: a segunda da semana ISO + o dia da semana, conferido com o `dates` (dd/mm) da semana.

    `semana` é o dicionário da semana do banco_dados.json ({"week": "2026-W41", "dates": {"seg": "05/10", ...}}) ou só o
    texto da semana. O ano vem da semana ISO (o dd/mm não tem ano; a 2025-W01 começa em 30/12/2024). Se o `dates` diz
    outro dia para aquele dia da semana, a fonte se contradiz: vazio, nunca um dos dois escolhido."""
    s = semana if isinstance(semana, dict) else {"week": semana}
    seg, i = _segunda(s.get("week")), dia_da_semana(dia)
    if seg is None or i is None:
        return None
    d = seg + timedelta(days=i)
    ddmm = _txt((s.get("dates") or {}).get(DIAS_CURTOS[i]))
    if ddmm and ddmm != d.strftime("%d/%m"):
        return None
    return _data_id(d)


def _dia_de_brasilia(v) -> int | None:
    """'2026-09-15T11:20:32.815891' (já em Brasília, sem fuso: o robô do PCM converte e tira o fuso) -> 20260915.
    Com fuso ('...Z', '-03:00'), converte para Brasília antes de pegar o dia."""
    s = _txt(v)
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is not None:
        d = d.astimezone(_BRT)
    return _data_id(d.date())


def _hora(v) -> str | None:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", _txt(v))
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def _minutos(horas) -> int | None:
    """A fonte guarda horas (1.1 = 66 min). Negativo ou texto = None."""
    h = _num(horas)
    return int(round(h * 60)) if h is not None and h >= 0 else None


# ── os atributos ──────────────────────────────────────────────────────────────────────────────────────────────────
def criticidade(v) -> tuple[str | None, int | float | None]:
    """A coluna "RPN/Prioridade" do PCM traz o RPN em pontos ("18") ou, quando a tarefa não tem RPN, o rótulo da
    criticidade ("Muito alto"). São dois atributos: (rótulo, None) ou (None, pontos). Outro texto = (None, None)."""
    t = _sem_acento(v)
    if not t:
        return None, None
    rot = next((r for r in ROTULOS_CRITICIDADE if _sem_acento(r) == t), None)
    if rot:
        return rot, None
    n = _num(v)
    return (None, n) if n is not None and n >= 0 else (None, None)


def tarefa_chave(texto) -> str | None:
    """O texto da tarefa vira chave (sha1 de 12): sem acento, sem caixa, espaço único. O texto não vai ao fato, e a
    MESMA conta (`fatos.tarefa_chave`, uma função só) no fechamento do App casa programado × executado (715 de 716 pares
    OS + código em 08/10)."""
    return _tarefa_chave_unica(texto)


def _sim_nao(v) -> int | None:
    """'Sim' = 1, 'Não' = 0, vazio = None (a fonte não disse)."""
    t = _sem_acento(v)
    return 1 if t.startswith("sim") else (0 if t in ("nao", "não") else None)


def _nova_os(r: dict) -> int | None:
    """Na planilha do PCM a coluna "Nova OS" vem em branco quando a OS não é nova e "Sim (BD)" / "Sim (via Solic
    #NNNN)" quando é. Sem a chave no arquivo (semana antiga) = None."""
    if "nova_os" not in r:
        return None
    return 1 if _sem_acento(r.get("nova_os")).startswith("sim") else 0


def _rolada(r: dict) -> int | None:
    """'↻ de Segunda-feira (05/10) · 3ª rolagem' = 1; vazio = 0; sem a chave (semana antiga) = None."""
    if "rolagem" not in r:
        return None
    return 1 if _txt(r.get("rolagem")) and _txt(r.get("rolagem")).lower() != "none" else 0


def _dominio(v, mapa) -> str | None:
    return mapa.get(_sem_acento(v)) if _txt(v) else None


def _os(v) -> str | None:
    t = _txt(v)
    m = re.fullmatch(r"(\d+)\.0+", t)
    return m.group(1) if m else (t or None)


def _codigo(v) -> str | None:
    """O código do ativo do Fracttal, canônico: maiúsculo e sem espaço (a espinha da dimensão de equipamento)."""
    return re.sub(r"\s+", "", _txt(v)).upper() or None


def _pessoa(pessoa_por_nome: dict, nome) -> int | None:
    """pessoa_id só quando o nome é de UMA pessoa do cadastro. Aceita o mapa de `ligacao_cadastro.mapas()["pessoa"]`
    ({nome normalizado: id}, que já tira os homônimos) ou {nome: {ids}}: com 2 ids, não liga. Campo com dois nomes
    (vírgula, ponto e vírgula, barra) também não liga: seria escolher um dos dois."""
    t = _txt(nome)
    if not t or not pessoa_por_nome or re.search(r"[,;/]", t):
        return None
    v = pessoa_por_nome.get(norm_nome(t))
    if isinstance(v, (set, frozenset, list, tuple)):
        v = next(iter(v)) if len(set(v)) == 1 else None
    return _id(v)


def _equipamento(equip, codigo) -> tuple:
    """(equipamento_id, por onde ligou). `equip`: o `equipamento.ligar` com o índice da carga (código -> (ID, como)),
    uma função código -> ID ou um dicionário. Sem ele, (None, None)."""
    return ligar_equipamento(equip, codigo)


def _pct(n, total) -> float:
    return round(100.0 * n / total, 1) if total else 0.0


# ── o fato ────────────────────────────────────────────────────────────────────────────────────────────────────────
def fato_programacao(dados: dict | None, lig, pessoa_por_nome: dict | None, equip, lido_em) -> tuple[list, dict]:
    """(linhas no formato de CAB_PROGRAMACAO, relatório só com contagens).

    `dados` = `nexus.pcm.fonte.ler(config).dados`; `lig` = `nexus.dados.fatos.Ligador`; `pessoa_por_nome` =
    `ligacao_cadastro.mapas()["pessoa"]`; `equip` = código -> equipamento_id (ou o par de `equipamento.ligar`; None =
    coluna vazia); `lido_em` = quando o Nexus leu a fonte.

    O relatório nunca leva nome de pessoa: só quantos nomes ligaram."""
    semanas = [s for s in (dados or {}).get("semanas") or [] if isinstance(s, dict) and s.get("week")]
    lido = _txt(lido_em) or None
    out, chaves = [], []
    fora_do_plano, por_semana = 0, Counter()
    sem_u, sem_e, como = Counter(), Counter(), Counter()
    nomes = {"tecnico": {}, "responsavel": {}}
    crit = Counter()
    fora_dom = Counter()
    vistos, repetidos = Counter(), 0
    for s in semanas:
        week = _txt(s.get("week")).upper()
        seg = segunda_da_semana(week)
        gerada = _txt(s.get("geradaEm")) or None
        for r in s.get("rows") or []:
            if not isinstance(r, dict):
                continue
            if r.get("foraDoPlano"):
                fora_do_plano += 1
                continue
            codigo = _codigo(r.get("codigo"))
            os_ = _os(r.get("os_id"))
            tch = tarefa_chave(r.get("tarefa"))
            i_dia = dia_da_semana(r.get("dia"))
            h_ini = _hora(r.get("h_ini"))
            dia_prog = data_do_bloco(s, r.get("dia"))
            if dia_prog is None:
                fora_dom["dia"] += 1
            uid, por = lig.usina(r.get("usina"), codigo)
            eq_id, eq_como = _equipamento(equip, codigo)
            eid = lig.equipe(r.get("cluster"))
            tec = _pessoa(pessoa_por_nome, r.get("resp_os"))
            resp = _pessoa(pessoa_por_nome, r.get("responsavel"))
            for papel, nome, pid in (("tecnico", r.get("resp_os"), tec), ("responsavel", r.get("responsavel"), resp)):
                if _txt(nome):
                    nomes[papel][norm_nome(nome)] = pid is not None
            rot, pts = criticidade(r.get("criticidade"))
            crit["rotulo" if rot else ("pts" if pts is not None else ("vazia" if not _txt(r.get("criticidade"))
                                                                     else "fora"))] += 1
            st_exec = _dominio(r.get("status") or r.get("status_bd"), STATUS_EXECUCAO)
            st_os = _dominio(r.get("statusPai"), STATUS_OS)
            if st_exec is None and _txt(r.get("status") or r.get("status_bd")):
                fora_dom["status_execucao"] += 1
            if st_os is None and _txt(r.get("statusPai")):
                fora_dom["status_os"] += 1
            dia_chave = DIAS_CURTOS[i_dia] if i_dia is not None else _sem_acento(r.get("dia"))
            base = f"{week}|{os_ or ''}|{codigo or ''}|{tch or ''}|{dia_chave}|{h_ini or _txt(r.get('h_ini'))}"
            vistos[base] += 1
            if vistos[base] > 1:
                # o mesmo bloco duas vezes na planilha (0 em 08/10): as duas linhas ficam, com IDs distintos e
                # estáveis pela ordem, e a conta aparece no relatório; sumir com uma seria perder dado calado
                repetidos += 1
                base += f"|{vistos[base]}"
            if uid is None:
                sem_u[_txt(r.get("usina"))] += 1
            if eid is None:
                sem_e[_txt(r.get("cluster"))] += 1
            como[por] += 1
            por_semana[week] += 1
            out.append([
                hashlib.sha1(base.encode("utf-8")).hexdigest()[:16], seg, dia_prog,
                _dia_de_brasilia(r.get("dataCriacao")), _dia_de_brasilia(r.get("dataFinal")), uid, por, eid, tec, resp,
                eq_id, eq_como, codigo, os_, tch, _txt(r.get("tipo")) or None, rot, pts, 0,
                _minutos(r.get("duracao")), _minutos(r.get("desloc")), h_ini, _sim_nao(r.get("reprog")),
                _qtd(r.get("vezes")), _sim_nao(r.get("termo")), _sim_nao(r.get("paralelo")), _nova_os(r), _rolada(r),
                st_exec, st_os, gerada, lido])
            chaves.append((week, os_, codigo, tch))
    _marcar_primeiro_bloco(out, chaves)
    return out, _relatorio(dados, out, por_semana, fora_do_plano, como, sem_u, sem_e, nomes, crit, fora_dom,
                           repetidos)


def codigos(dados: dict | None) -> list:
    """Os códigos de ativo das linhas PLANEJADAS (as mesmas do fato; sem `foraDoPlano`), canônicos: o que a carga
    passa à dimensão de equipamento como fonte "pcm" (a coluna `codigo_ativo` do fato_programacao, quando ele estiver
    no banco). Sem a fonte lida, lista vazia."""
    out = []
    for s in (dados or {}).get("semanas") or []:
        if not isinstance(s, dict):
            continue
        for r in s.get("rows") or []:
            if isinstance(r, dict) and not r.get("foraDoPlano") and _codigo(r.get("codigo")):
                out.append(_codigo(r.get("codigo")))
    return out


def _marcar_primeiro_bloco(linhas: list, chaves: list) -> None:
    """1 no primeiro bloco (pelo dia e pela hora) de cada tarefa da semana; a tarefa partida em dois dias conta 1."""
    i_dia, i_h, i_pb = (CAB_PROGRAMACAO.index(c) for c in ("data_id_programada", "hora_inicio", "primeiro_bloco"))
    grupos = defaultdict(list)
    for n, k in enumerate(chaves):
        grupos[k].append(n)
    for idx in grupos.values():
        primeiro = min(idx, key=lambda n: (linhas[n][i_dia] or 99999999, linhas[n][i_h] or "99:99", n))
        linhas[primeiro][i_pb] = 1


def _relatorio(dados, linhas, por_semana, fora_do_plano, como, sem_u, sem_e, nomes, crit, fora_dom, repetidos):
    ix = {c: CAB_PROGRAMACAO.index(c) for c in CAB_PROGRAMACAO}
    n = len(linhas)
    cols = ("data_id_semana", "data_id_programada", "usina_id", "equipe_id", "pessoa_id_tecnico",
            "pessoa_id_responsavel", "equipamento_id")
    com = {c: sum(1 for l in linhas if l[ix[c]] is not None) for c in cols}
    ex = lambda c: "; ".join(f"{k or '(vazio)'} ({v})" for k, v in c.most_common(6)) or None
    return {
        "fonte_gerado_em": _txt((dados or {}).get("geradoEm")) or None,
        "semanas": sorted(por_semana), "linhas": n, "por_semana": dict(sorted(por_semana.items())),
        "tarefas": sum(l[ix["primeiro_bloco"]] for l in linhas),
        "fora_do_plano": fora_do_plano,
        "com": com, "pct": {c: _pct(v, n) for c, v in com.items()},
        "usina_por_de_para": como.get("de-para do Fracttal", 0), "usina_por_codigo": como.get("código do ativo", 0),
        "sem_usina_exemplos": ex(sem_u), "sem_equipe_exemplos": ex(sem_e),
        # só contagens: o nome da pessoa não sai daqui (a API do banco tem leitura aberta)
        "nomes_tecnico": {"distintos": len(nomes["tecnico"]), "ligados": sum(nomes["tecnico"].values())},
        "nomes_responsavel": {"distintos": len(nomes["responsavel"]), "ligados": sum(nomes["responsavel"].values())},
        "criticidade": dict(crit), "fora_do_dominio": dict(fora_dom), "blocos_repetidos": repetidos,
    }


def linha_qualidade(rel: dict, cab: list, origem_em, agora: str) -> list:
    """A linha da aba `qualidade` no cabeçalho que a carga usar (`fatos.CAB_QUALIDADE`, que está mudando no passo 2 do
    desenho): preenche pelo NOME da coluna e deixa vazia a que não conhece. A data é a do bloco; a pessoa, o técnico;
    o responsável O&M, a criticidade e o que ficou fora do plano vão no `extra`."""
    import json
    com, pct = rel.get("com") or {}, rel.get("pct") or {}
    extra = {"tarefas": rel.get("tarefas"), "fora_do_plano": rel.get("fora_do_plano"), "semanas": rel.get("semanas"),
             "com_responsavel": com.get("pessoa_id_responsavel"), "criticidade": rel.get("criticidade"),
             "fora_do_dominio": rel.get("fora_do_dominio"), "blocos_repetidos": rel.get("blocos_repetidos")}
    valores = {
        "fato": "programacao", "livro_origem": LIVRO_ORIGEM, "linhas": rel.get("linhas"),
        "com_data": com.get("data_id_programada"), "com_usina": com.get("usina_id"),
        "com_equipe": com.get("equipe_id"), "com_pessoa": com.get("pessoa_id_tecnico"),
        "com_equipamento": com.get("equipamento_id"), "pct_data": pct.get("data_id_programada"),
        "pct_usina": pct.get("usina_id"), "pct_equipe": pct.get("equipe_id"),
        "pct_pessoa": pct.get("pessoa_id_tecnico"), "pct_equipamento": pct.get("equipamento_id"),
        "usina_por_de_para": rel.get("usina_por_de_para"), "usina_por_codigo": rel.get("usina_por_codigo"),
        "sem_usina_exemplos": rel.get("sem_usina_exemplos"), "sem_equipe_exemplos": rel.get("sem_equipe_exemplos"),
        "origem_atualizada_em": origem_em or rel.get("fonte_gerado_em"), "gerado_em": agora,
        "extra": json.dumps(extra, ensure_ascii=False, separators=(",", ":")),
    }
    return [valores.get(c) for c in cab]


def sha_linhas(linhas: list) -> str:
    """A impressão digital do fato sem o `lido_em`. O `geradoEm` do arquivo muda a cada rodada do robô (~30 min),
    mesmo sem nada mudar na agenda: gravar "se o geradoEm mudou" gravaria toda hora. Com esta conta, a carga grava
    só quando um bloco, um status ou uma ligação mudou (noite e fim de semana, nada)."""
    i = CAB_PROGRAMACAO.index("lido_em")
    h = hashlib.sha1()
    for l in sorted(l[:i] + l[i + 1:] for l in ([str(v) for v in x] for x in linhas)):
        h.update("\x1f".join(l).encode("utf-8"))
        h.update(b"\x1e")
    return h.hexdigest()


# ── a gravação por semana (só com a decisão do Levi) ──────────────────────────────────────────────────────────────
def _no_tipo(c, v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if c in _INTEIRAS:
        x = _num(v)
        return int(x) if isinstance(x, (int, float)) and float(x).is_integer() else None
    if c == "criticidade_pts":
        return _num(v)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        # coluna de texto que o banco devolveu como número (a OS 15377 volta 15377 ou 15377.0): volta a texto, para a
        # semana do banco e a da fonte não terem a mesma OS em dois tipos
        return str(int(v)) if float(v).is_integer() else str(v)
    return v


def mesclar_semanas(no_banco: list, da_fonte: list) -> list:
    """A semana que está na fonte substitui a MESMA semana do banco; as outras semanas do banco ficam.

    NÃO está ligado: só entra se o Levi aprovar gravar a programação antes do passo 0 (desenho de 08/10, decisão 7).
    Sem isto, a troca integral deixa no banco só as 4 semanas que a fonte guarda. `no_banco`: as linhas lidas do
    banco (dicionários, valores às vezes como texto); `da_fonte`: as linhas de `fato_programacao`. Linha do banco sem
    semana não é descartada (não se sabe a que semana pertence). Não protege contra a fonte que publica uma semana
    pela metade: recusar carga encolhida é o passo 1, adiado."""
    i_sem = CAB_PROGRAMACAO.index("data_id_semana")
    semanas_fonte = {_no_tipo("data_id_semana", l[i_sem]) for l in da_fonte}
    ficam = []
    for l in no_banco or []:
        lin = [l.get(c) for c in CAB_PROGRAMACAO] if isinstance(l, dict) else list(l)
        lin = [_no_tipo(c, v) for c, v in zip(CAB_PROGRAMACAO, lin)]
        if lin[i_sem] is None or lin[i_sem] not in semanas_fonte:
            ficam.append(lin)
    return ficam + [list(l) for l in da_fonte]
