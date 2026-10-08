"""Os fatos gravados com os IDs das dimensões (o passo 2 da matriz de barramento) e a qualidade da ligação.

O livro de origem chega como o sistema escreve (nome da usina, região em texto, pessoa em código). Aqui cada linha ganha
`data_id`, `usina_id`, `equipe_id` e `pessoa_id`; o que não ligou fica VAZIO (nunca um ID chutado) e entra na conta da
qualidade, com exemplos do que faltou. Também vai a LINHAGEM: por onde a usina ligou.

1º fato (05/10/2026): o fechamento de OS, do livro que o App de Campo grava (`fechamentos_app_campo`).
- usina: o App escreve "Thopen · Thopen - Ipixuna 1 e 2 - PA" = cliente · nome da Classificação 1 do Fracttal, que o
  de-para do cadastro já liga (sistema "Fracttal · Classificação 1"); sem par, vale o código da usina dentro do código
  do ativo ("THPN-PRM200-PGINVR1" → PRM200) contra o código do cadastro, só quando o código é de UMA usina (IPX100
  é da 2C e da Thopen: não liga por código).
- equipe: a "Região" do App é o nome da equipe ("PR Oeste 01"). É a equipe no momento do fechamento.
- pessoa: o código do e-mail (HMAC) contra o e-mail de cada pessoa do cadastro (`ligacao_cadastro.mapas`).
- data: "Registrado em" vem em UTC; o dia é o de Brasília.
Fora do fato, de propósito: nome de pessoa e a observação escrita no App (texto livre pode ter nome; a API do banco tem
leitura aberta). Indicadores (sim/não) vão como 1/0, para somar e tirar média.

08/10/2026 (auditoria Kimball, passos 2 a 6):
- `equipamento_id` + `equipamento_ligado_por`, pelo código do ativo (`equipamento.ligar`): o código estava em 2.896 de
  2.896 fechamentos e nenhum fato tinha o ID.
- `tarefa_chave`: o texto da tarefa vira chave (o texto não entra), a MESMA conta da programação do PCM: programado ×
  executado casa por (OS, código, tarefa_chave) em 715 de 716 pares.
- Medida com a unidade no nome: `nota` → `nota_pts`, `fotos` → `fotos_qtd`, `pecas` → `pecas_qtd`, `xp` → `xp_pts`.
  `vezes_reprogramada` → `vezes_programada_qtd`: o App grava ali o "vezes" da linha do PCM (function_app.py da v241,
  o `vezes` do contexto da tarefa), que é o "Nº vezes programada" e CONTA A 1ª VEZ (as 1.381 linhas do PCM com
  Reprogramada = Não têm todas 1); somado como "reprogramada" contaria a primeira programação como reprogramação.
  0 leitores do `nexus_fatos` fora de `nexus/dados` (auditoria, grep): renomear agora não quebra ninguém.
"""
import hashlib
import json
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone

from ..cadastro.banco import codigo_do_equipamento, sufixo_codigo
from ..campo.ligacao_cadastro import _norm as norm_fracttal
from .calendario import data_id as _data_id

SISTEMA_FRACTTAL = "Fracttal · Classificação 1"
# Foto acumulada, NÃO transação (revisão de 08/10/2026): a linha muda depois de entrar. Medido no livro do App em 08/10:
# a "Revisão" anda de vazia (337 das 340 de até 1 dia) para aprovada, devolvida, cancelada ou "nota 72->100" (280, todas
# com mais de 8 dias), e entre duas cargas seguidas 1 fechamento mudou a devolvida e a revisão com a mesma chave.
# Declarado "transação" (nunca muda), o passo 0 só acrescentaria pela chave e congelaria a 1ª versão de cada linha.
TIPO_FECHAMENTO = "snapshot_acumulado"
_BRT = timezone(timedelta(hours=-3))
CAB_FECHAMENTO = ["fechamento_id", "data_id", "usina_id", "equipe_id", "pessoa_id", "equipamento_id",
                  "equipamento_ligado_por", "os", "id_os_fracttal", "codigo_ativo", "tarefa_chave", "tipo_os",
                  "criticidade", "nota_pts", "pontual", "devolvida", "revisao", "fotos_qtd", "fotos_com_descricao_qtd",
                  "observacao_suficiente", "gps_inicio_fim", "assinou", "obrigatorias_ok", "todas_ok", "pecas_qtd",
                  "xp_pts", "previsto_min", "execucao_min", "reprogramada", "vezes_programada_qtd", "registrado_em",
                  "hora_celular", "usina_ligada_por"]
# Para o catálogo (`catalogo.Medida`): (coluna, unidade, soma). A nota é por tarefa (média, nunca soma); o nº de vezes
# programada é atributo da tarefa no PCM (somar não diz nada).
MEDIDAS_FECHAMENTO = (("nota_pts", "pts", "nao"), ("fotos_qtd", "qtd", "aditiva"),
                      ("fotos_com_descricao_qtd", "qtd", "aditiva"), ("pecas_qtd", "qtd", "aditiva"),
                      ("xp_pts", "pts", "aditiva"), ("previsto_min", "min", "aditiva"),
                      ("execucao_min", "min", "aditiva"), ("vezes_programada_qtd", "qtd", "nao"),
                      *((c, "1/0", "aditiva") for c in ("pontual", "devolvida", "observacao_suficiente",
                                                         "gps_inicio_fim", "assinou", "obrigatorias_ok", "todas_ok",
                                                         "reprogramada")))
# A qualidade é UMA aba para todos os fatos do livro. 08/10/2026: + equipamento, + "acha exatamente 1 versão no
# histórico" (a junção da época: era 25,4% dos fechamentos por pessoa) e `extra` (JSON curto com o que só aquele fato
# tem). Colunas novas no FIM: quem lê pela posição não muda. Percentual com 1 casa (o inteiro escondia 99,7 -> 100).
CAB_QUALIDADE = ["fato", "livro_origem", "linhas", "com_data", "com_usina", "com_equipe", "com_pessoa", "pct_data",
                 "pct_usina", "pct_equipe", "pct_pessoa", "usina_por_de_para", "usina_por_codigo",
                 "sem_usina_exemplos", "sem_equipe_exemplos", "origem_atualizada_em", "gerado_em",
                 "com_equipamento", "pct_equipamento", "pct_usina_versao", "pct_pessoa_versao", "extra"]


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _sim(v) -> int:
    return 1 if _txt(v).lower() in ("sim", "true", "1", "verdadeiro") else 0


def _int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def _id(v):
    i = _int(v)
    return i if i is not None and i > 0 else None


def data_do_registro(iso) -> int | None:
    """"2026-10-01T02:30:00.000Z" (UTC) → 20260930: o dia é o de Brasília."""
    s = _txt(iso).replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return _data_id(d.astimezone(_BRT).date())


def _norm_equipe(s) -> str:
    return " ".join(_txt(s).lower().split())


def tarefa_chave(texto) -> str | None:
    """O texto da tarefa vira chave (sha1 de 12 caracteres): sem acento, sem caixa, espaço único. O texto não vai ao
    fato (pode citar gente; a API do banco tem leitura aberta). É a MESMA conta no fechamento do App e na programação do
    PCM (`programacao.py` importa daqui): programado × executado casou a tarefa em 715 de 716 pares (OS, código) em
    08/10/2026."""
    n = " ".join(unicodedata.normalize("NFKD", _txt(texto)).encode("ascii", "ignore").decode().lower().split())
    return hashlib.sha1(n.encode("utf-8")).hexdigest()[:12] if n else None


def ligar_equipamento(equip, codigo) -> tuple[int | None, str | None]:
    """(equipamento_id, por onde ligou). `equip` = código -> (ID, como) (o `equipamento.ligar` com o índice da carga),
    código -> ID, ou um dicionário. Sem ele (ou sem código), (None, None): nunca o código no lugar do ID."""
    cod = _txt(codigo)
    if not equip or not cod:
        return None, None
    v = equip(cod) if callable(equip) else equip.get(cod)
    if isinstance(v, tuple):
        eid, como = (tuple(v) + (None, None))[:2]
    else:
        eid, como = v, None
    eid = _id(eid)
    return (eid, (como or "código do ativo")) if eid else (None, None)


class Ligador:
    """Traduz o que cada sistema escreve para os IDs do cadastro. Só liga o que é de UM dono."""

    def __init__(self, usinas: list[dict], de_para: list[dict], equipes: list[dict], pessoa_por_codigo: dict):
        self.por_fracttal = {}
        for d in de_para:
            if _txt(d.get("sistema")) == SISTEMA_FRACTTAL and _id(d.get("usina_id")):
                self.por_fracttal[norm_fracttal(d.get("chave_externa"))] = _id(d.get("usina_id"))
        donos = {}
        for u in usinas:
            if _txt(u.get("excluido")).lower() == "sim" or not _txt(u.get("codigo")) or not _id(u.get("usina_id")):
                continue
            donos.setdefault(sufixo_codigo(u.get("codigo")), set()).add(_id(u.get("usina_id")))
        self.por_codigo = {c: next(iter(ids)) for c, ids in donos.items() if len(ids) == 1}
        eq = {}
        for e in equipes:
            if _txt(e.get("excluido")).lower() != "sim" and _id(e.get("equipe_id")) and _txt(e.get("nome")):
                eq.setdefault(_norm_equipe(e.get("nome")), set()).add(_id(e.get("equipe_id")))
        self.equipes = {n: next(iter(ids)) for n, ids in eq.items() if len(ids) == 1}
        self.pessoas = dict(pessoa_por_codigo or {})

    def usina(self, texto, codigo_ativo) -> tuple[int | None, str | None]:
        t = _txt(texto)
        nome = t.split(" · ", 1)[1] if " · " in t else t
        uid = self.por_fracttal.get(norm_fracttal(nome)) if nome else None
        if uid:
            return uid, "de-para do Fracttal"
        cod = codigo_do_equipamento(codigo_ativo)
        uid = self.por_codigo.get(sufixo_codigo(cod)) if cod else None
        return (uid, "código do ativo") if uid else (None, None)

    def equipe(self, texto) -> int | None:
        return self.equipes.get(_norm_equipe(texto)) if _txt(texto) else None

    def pessoa(self, codigo) -> int | None:
        primeiro = _txt(codigo).split(";")[0].strip()
        return self.pessoas.get(primeiro) if primeiro else None


def chave_fechamento(a: dict) -> str:
    """`fechamento_id` = sha1("ID da OS|Tarefa|Registrado em")[:16]. Uma função só: a carga põe a chave no fato e a tela
    do Campo junta o livro cru ao fato por ela (passo 4 do Kimball, 08/10/2026)."""
    chave = f"{_txt(a.get('ID da OS no Fracttal'))}|{_txt(a.get('Tarefa'))}|{_txt(a.get('Registrado em'))}"
    return hashlib.sha1(chave.encode("utf-8")).hexdigest()[:16]


def fato_fechamento(origem: list[dict], lig: Ligador, equip=None) -> list[list]:
    """As linhas do fato (CAB_FECHAMENTO). `equip`: código do ativo -> (equipamento_id, como) (ver `ligar_equipamento`);
    sem ele, `equipamento_id` vazio."""
    out = []
    for a in origem:
        reg = _txt(a.get("Registrado em"))
        uid, como = lig.usina(a.get("Usina"), a.get("Código do ativo"))
        eid, eq_como = ligar_equipamento(equip, a.get("Código do ativo"))
        out.append([
            chave_fechamento(a), data_do_registro(reg), uid,
            lig.equipe(a.get("Região")), lig.pessoa(a.get("Técnico (HMAC)")), eid, eq_como,
            _txt(a.get("OS")) or None, _txt(a.get("ID da OS no Fracttal")) or None,
            _txt(a.get("Código do ativo")) or None, tarefa_chave(a.get("Tarefa")),
            _txt(a.get("Tipo da OS")) or None, _txt(a.get("Criticidade")) or None, _int(a.get("Nota do painel")),
            _sim(a.get("Pontual")), _sim(a.get("Devolvida")), _txt(a.get("Revisão")) or None, _int(a.get("Fotos")),
            _int(a.get("Fotos com descrição")), _sim(a.get("Observação suficiente")),
            _sim(a.get("GPS no início e no fim")), _sim(a.get("Assinou")), _sim(a.get("Obrigatórias respondidas")),
            _sim(a.get("Todas respondidas")), _int(a.get("Peças")), _int(a.get("XP")), _int(a.get("Previsto (min)")),
            _int(a.get("Execução (min)")), _sim(a.get("Reprogramada")), _int(a.get("Vezes reprogramada")), reg or None,
            _txt(a.get("Hora do celular")) or None, como])
    return out


def _pct(n, total) -> float:
    """Percentual com 1 casa (auditoria DR-9, 08/10/2026: o inteiro mostrava 99,7% como 100%)."""
    return round(100.0 * n / total, 1) if total else 0.0


def pct_versao(linhas, cab, col_id, col_data, hist):
    """% das linhas com ID e data que acham EXATAMENTE 1 versão no histórico no dia do fato (a junção da época:
    `valido_de_id <= data_id < valido_ate_id`). `hist` = as linhas do `<entidade>_historico` (listas da carga ou dicts
    do banco); sem histórico, None (não é 0%). Uma regra só: `historico.cobertura`."""
    if hist is None:
        return None
    from . import historico
    n, um = historico.cobertura(linhas, cab, col_id, col_data, hist)
    return _pct(um, n) if n else None          # nenhuma linha com o ID: não há o que medir (0% enganaria)


def _exemplos(c: Counter) -> str | None:
    """Os 6 mais comuns; no empate, pela ordem do texto. O `most_common` desempata pela ordem de chegada, e a ordem
    das linhas da API muda de leitura para leitura: o PC e o servidor gravavam exemplos diferentes para o mesmo banco
    (revisão de 08/10, duas cargas com as entradas embaralhadas)."""
    top = sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0])))[:6]
    return "; ".join(f"{k or '(vazio)'} ({v})" for k, v in top) or None


def qualidade(fato: str, livro: str, linhas: list[list], cab: list, origem: list[dict], origem_em, agora: str, *,
              hist: dict | None = None, extra: dict | None = None) -> list:
    """Uma linha da aba `qualidade` (CAB_QUALIDADE): quanto do fato ligou a cada dimensão, exemplos do que não ligou,
    quantos acham exatamente 1 versão no histórico (`hist` = {"pessoas": linhas, "usinas": linhas}) e o `extra`."""
    i = {c: cab.index(c) for c in cab}
    n = len(linhas)
    com = {c: sum(1 for l in linhas if l[i[c]] is not None) for c in ("data_id", "usina_id", "equipe_id", "pessoa_id")}
    com_eq = sum(1 for l in linhas if l[i["equipamento_id"]] is not None) if "equipamento_id" in i else None
    como = Counter(l[i["usina_ligada_por"]] for l in linhas if "usina_ligada_por" in i)
    sem_u = Counter(_txt(o.get("Usina")) for o, l in zip(origem, linhas) if l[i["usina_id"]] is None)
    sem_e = Counter(_txt(o.get("Região")) for o, l in zip(origem, linhas) if l[i["equipe_id"]] is None)
    hist = hist or {}
    return [fato, livro, n, com["data_id"], com["usina_id"], com["equipe_id"], com["pessoa_id"],
            _pct(com["data_id"], n), _pct(com["usina_id"], n), _pct(com["equipe_id"], n), _pct(com["pessoa_id"], n),
            como.get("de-para do Fracttal", 0), como.get("código do ativo", 0), _exemplos(sem_u), _exemplos(sem_e),
            origem_em, agora, com_eq, _pct(com_eq, n) if com_eq is not None else None,
            pct_versao(linhas, cab, "usina_id", "data_id", hist.get("usinas")),
            pct_versao(linhas, cab, "pessoa_id", "data_id", hist.get("pessoas")),
            json.dumps(extra or {}, ensure_ascii=False, sort_keys=True)]


# ── 2º fato (06/10/2026): o checklist das rondas que ficaram SEM OS ───────────────────────────────────────────────
# Levi, 06/10: "Atualize o banco de dados com essas rondas passadas sem OS, mas não será rotina". A ronda com OS tem as
# respostas no texto da OS do Fracttal (`nexus/campo/ronda_checklist.py`); a ronda sem OS só as tinha no registro da
# ronda no App. Carga ÚNICA (`ferramentas/carregar_checklist_rondas_sem_os.py`), não entra na carga de hora em hora.
# Grão: 1 linha = 1 ronda do App sem OS. Liga ao livro de rondas (`rondas_app_campo`) por usina_id + inicio.
CAB_CHECKLIST_RONDA = ["ronda_id", "data_id", "usina_id", "equipe_id", "pessoa_id", "tipo", "inicio", "fim",
                       "sujidade", "vegetacao", "vala", "ipoa_sujo", "ghi_sujo", "albedo_sujo", "usina_ligada_por"]
VALAS = ("Limpa", "Parcial", "Obstruída")


def _nivel(v):
    i = _int(v)
    return i if i is not None and 1 <= i <= 5 else None


def _sujo(v):
    """Sensor: 1 sujo, 0 limpo; "Não se aplica" ou sem resposta = vazio."""
    t = _txt(v).lower()
    return 1 if t == "sujo" else (0 if t == "limpo" else None)


def fato_checklist_ronda(sem_os: list[dict], registros: dict, lig: Ligador, codigo_do_email) -> tuple[list, list]:
    """(linhas do fato, linhas de origem que casaram). `sem_os`: as linhas do livro de rondas sem OS; `registros`:
    {(dia, início): registro da ronda no App, com "email" e "respostas"}; `codigo_do_email`: e-mail -> código HMAC.
    Ronda que não casa com UM registro fica fora (nunca uma resposta de outra ronda); o e-mail só vira pessoa_id."""
    import json
    out, origem = [], []
    for l in sem_os:
        ini = _txt(l.get("Início"))
        reg = registros.get((_txt(l.get("Data"))[:10], ini))
        if not ini or not reg:
            continue
        try:
            resp = json.loads(reg.get("respostas") or "{}") or {}
        except ValueError:
            resp = {}
        uid, como = lig.usina(l.get("Usina"), l.get("Ativo da usina no Fracttal"))
        email = _txt(reg.get("email")).lower()
        vala = _txt(resp.get("vala"))
        out.append([
            hashlib.sha1(f"{_txt(l.get('Data'))}|{_txt(l.get('Usina'))}|{ini}".encode("utf-8")).hexdigest()[:16],
            data_do_registro(ini), uid, lig.equipe(l.get("Região")),
            lig.pessoa(codigo_do_email(email)) if email else None, _txt(l.get("Tipo")) or None, ini,
            _txt(l.get("Fim")) or None, _nivel(resp.get("sujidade")), _nivel(resp.get("vegetacao")),
            vala if vala in VALAS else None, _sujo(resp.get("pir_ipoa")), _sujo(resp.get("pir_ghi")),
            _sujo(resp.get("pir_albedo")), como])
        origem.append(l)
    return out, origem
