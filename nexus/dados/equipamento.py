"""A dimensão de equipamento (passo 6a do Kimball, 08/10/2026): `nexus_equipamentos · dim_equipamento` e a tabela de
apelidos `equipamento_apelido`, mais a função que liga um código de ativo ao `equipamento_id` nos fatos.

Por que existe: a auditoria de 08/10 achou o código do ativo do Fracttal em TODOS os fechamentos e em TODAS as PT, e
nenhum fato com `equipamento_id`. Sem a dimensão, chamado × engenharia × perda por equipamento não cruzam (pendência 1
do `nexus/dados/CLAUDE.md`).

Grão: 1 linha = 1 código de ativo do Fracttal, canônico (maiúsculo, sem espaço). É dimensão: sem tipo de fato.

Os dois formatos de código do Fracttal (exemplos inventados): "ABC100-INVR2.4" (só a usina) e "XYZ-ABC100-INVR11.1"
(com o prefixo do cliente). `codigo_do_equipamento` (cadastro) lê os dois.

ID estável SEM registro: `equipamento_id = int(sha1("fracttal:" + código).hexdigest()[:13], 16) >> 3` (49 bits: no
máximo 562.949.953.421.311, 15 dígitos). 49 e não 52 (Levi, 08/10/2026, "conserte da melhor forma"): com 52 bits 77% dos
IDs tinham 16 dígitos e o Excel, que guarda 15, trocava o último por 0 (2150948520386742 virava ...740) — quem cruzasse
pelo Excel ligaria ao equipamento errado. 49 bits é o maior tamanho que sempre cabe em 15 dígitos; medido nos 22.353
códigos das duas fotos: 0 colisões (chance teórica ~4e-7; ~9e-6 com 100 mil códigos), e a colisão que um dia vier
recusa a dimensão (`test_colisao_de_id_recusa_a_dimensao`), nunca liga ao membro errado. Exato também no JSON e no
JavaScript (< 2^53). PC e servidor rodam a carga (41 cargas do PC e 37 do servidor na auditoria): com "maior
+ 1" cada máquina daria o próximo número a um código diferente, o defeito que o cadastro já teve. Derivado do código, as
duas calculam o mesmo número sem conversar, o fato põe o ID sem ler a dimensão e o membro que some e volta volta com o
mesmo ID. Custo medido: o código renomeado no Fracttal vira membro novo (19 itens com outro código entre a foto de
21/06 e a de 22/09); o `fracttal_item_id` liga os dois e a qualidade conta.

Membros: SÓ do que as duas máquinas leem igual, o banco. A foto de ativos do Fracttal que o OS Creator guardou em
arquivo entra UMA vez em `nexus_ativos_fracttal · foto_ativos` (`ferramentas/carregar_ativos_fracttal.py`, quem grava
é o Levi); a carga de hora em hora lê essa aba e os códigos dos livros do banco. Arquivo do PC (as fotos, o
`os_falhas.json`) nunca entra na carga de hora em hora: o servidor tem outro (ou nenhum), e a dimensão trocaria de
conteúdo a cada hora conforme a máquina.

Herda o passo 0 (adiado pelo Levi em 08/10): a carga refaz a dimensão inteira; um membro que só existe num fato de
janela curta (App: 90 dias; PCM: 4 semanas) some da dimensão quando sai da janela, e volta com o mesmo ID. As fotos
seguram quase todos (99,9% dos códigos das fontes estão nelas).

Tudo aqui é PURO (sem rede, sem arquivo): quem lê o banco é a carga; quem lê os arquivos é a ferramenta da carga única.
"""
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from ..cadastro.banco import codigo_do_equipamento, sufixo_codigo

_BRT = timezone(timedelta(hours=-3))

LIVRO_FOTO, ABA_FOTO = "nexus_ativos_fracttal", "foto_ativos"
NOME_FOTO = "Nexus · foto dos ativos do Fracttal (carga única; renovar exige ler o Fracttal)"
LIVRO, NOME = "nexus_equipamentos", "Nexus · dimensão de equipamento (código do ativo do Fracttal) e apelidos"

CAB_FOTO = ["fracttal_item_id", "codigo", "descricao", "pai_item_id", "tipo_fracttal", "foto_em"]
CAB_DIM = ["equipamento_id", "codigo", "descricao", "usina_id", "usina_ligada_por", "motivo_sem_usina", "familia",
           "tipo_fracttal", "pai_id", "fracttal_item_id", "na_foto", "foto_em", "fontes_qtd"]
CAB_APELIDO = ["equipamento_id", "sistema", "chave_externa", "casou_por"]
# Formato longo de propósito: a dimensão mede coisas de natureza diferente (membros, usina, cada fonte, cada sistema de
# apelido) e uma medida nova não muda o cabeçalho de um livro que é para sempre.
CAB_QUALIDADE = ["grupo", "item", "valor", "pct", "detalhe", "gerado_em"]
CAB_ATUALIZACAO = ["gerado_em", "maquina", "duracao_s", "linhas", "sha_linhas", "como_ler"]

SISTEMA_TRACKER = "Supervisório · tracker"
SISTEMA_GEMEO = "Gêmeo · equipamento"
SISTEMA_COLUNA = {"bd_thopen": "BD_Thopen · coluna", "bd_performance": "BD_Performance · coluna"}

# Onde cada livro do banco guarda o código do ativo: (fonte, livro, aba, coluna). A carga lê estas abas e passa os
# códigos a `membros`. O PCM ainda não está no banco (passo 6b): a carga passa os códigos dele à parte.
FONTES_BANCO = (
    ("fechamentos", "fechamentos_app_campo", "Fechamentos", "Código do ativo"),
    ("pt", "pt_app_campo", "PT", "Código do ativo"),
    ("rondas", "rondas_app_campo", "OS de ronda", "Ativo da usina no Fracttal"),
    ("campo_nexus", "campo_nexus", "fechamentos", "codigo"),
    ("de_para_trackers", "de_para_trackers", "De-Para Trackers", "Code Fracttal"),
)

# Por onde o fato ligou (`equipamento_ligado_por`)
NA_FOTO, COM_USINA, FORA_DA_DIMENSAO = "foto do Fracttal", "código com usina", "código com usina (fora da dimensão)"

# Por onde a usina ligou, e por que não ligou
CHEIO, SUFIXO = "código cheio", "sufixo único"
SEM_CODIGO_USINA, FORA_CADASTRO, DUAS_USINAS, PREFIXO_DIFERENTE = (
    "sem código de usina", "código fora do cadastro", "código de 2+ usinas", "prefixo do cliente diferente")


class ColisaoDeId(ValueError):
    """Dois códigos com o mesmo `equipamento_id`. Medido em 08/10: 0 nos 22.356 membros; se um dia acontecer, a carga
    recusa a dimensão inteira em vez de juntar dois equipamentos num ID."""


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _int(v):
    try:
        i = int(round(float(v)))
    except (TypeError, ValueError):
        return None
    return i if i > 0 else None


# ── o código e o ID ───────────────────────────────────────────────────────────────────────────────────────────────

def canon(codigo) -> str:
    """Maiúsculo e sem espaço nenhum: a foto do Fracttal tem "Transformador 2" e os livros do App gravam o mesmo ativo
    como o técnico digitou; sem isto, um ativo vira dois membros."""
    return re.sub(r"\s+", "", _txt(codigo)).upper()


def equipamento_id(codigo) -> int | None:
    """49 bits do sha1 do código canônico (cabe nos 15 dígitos do Excel): o mesmo número em qualquer máquina, em
    qualquer carga, sem registro."""
    c = canon(codigo)
    if not c:
        return None
    return int(hashlib.sha1(f"fracttal:{c}".encode("utf-8")).hexdigest()[:13], 16) >> 3


def valido(codigo, na_foto) -> bool:
    """Código que vira membro e que o fato liga: está numa foto do Fracttal, ou tem um código de usina dentro (o
    código que o App gravou de um ativo criado depois da foto). "GRID" e "Nobreak 1" (o App gravou outra coisa no
    lugar do ativo) não são equipamento: ficam vazios no fato."""
    c = canon(codigo)
    return bool(c) and (c in na_foto or codigo_do_equipamento(c) is not None)


def familia(codigo) -> str | None:
    """O prefixo de letras depois do código da usina: "ABC100-INVR2.4" → "INVR", "XYZ-ABC100-ETKR1.3" → "ETKR";
    "USINA" quando o código é só a usina. Não é o `tipo_fracttal` (o tipo do item no Fracttal): os dois batem em 16.612
    de 20.947 itens com família, porque a família agrupa (uma estação meteorológica ESTM tem piranômetro, sensor...)."""
    c = canon(codigo)
    cu = codigo_do_equipamento(c)
    if not cu or not c.startswith(cu):
        return None
    resto = c[len(cu):]
    if not resto:
        return "USINA"
    m = re.match(r"-([A-Z]+)", resto)
    return m.group(1) if m else None


# ── a usina dentro do código ──────────────────────────────────────────────────────────────────────────────────────

class IndiceUsinas:
    """O código das usinas do cadastro (sem as excluídas), pronto para 22 mil consultas."""

    def __init__(self, usinas):
        self.cheio, self.sufixo, self.codigo = defaultdict(set), defaultdict(set), {}
        for u in usinas or ():
            uid, cod = _int(u.get("usina_id")), canon(u.get("codigo"))
            if not uid or not cod or _txt(u.get("excluido")).lower() == "sim":
                continue
            self.cheio[cod].add(uid)
            self.sufixo[sufixo_codigo(cod)].add(uid)
            self.codigo[uid] = cod


def usina_do_codigo(codigo, usinas) -> tuple[int | None, str]:
    """(usina_id, por onde ligou) ou (None, por que não ligou). Só liga o código que é de UMA usina (regra 4 da casa):
    - prefixado ("XYZ-ABC100-…"): o código cheio igual ao do cadastro;
    - senão, o sufixo ("ABC100") de uma usina só. Simples sem prefixo cujo sufixo é de duas usinas ("XYZ-ABC100" e
      "QQQ-ABC100") não liga: medido em 08/10, 170 códigos assim (um código de usina que é de dois clientes);
    - prefixado com prefixo de outro cliente que o do cadastro ("XYZ-ABC100" contra "QQQ-ABC100" sozinho) não liga: 0
      hoje, mas seria um chute.
    `usinas`: a lista do cadastro ou um `IndiceUsinas` já montado."""
    idx = usinas if isinstance(usinas, IndiceUsinas) else IndiceUsinas(usinas)
    cu = codigo_do_equipamento(canon(codigo))
    if not cu:
        return None, SEM_CODIGO_USINA
    suf = idx.sufixo.get(sufixo_codigo(cu), set())
    cheio = idx.cheio.get(cu, set())
    if len(cheio) == 1 and ("-" in cu or len(suf) == 1):
        return next(iter(cheio)), CHEIO
    if len(suf) == 1:
        uid = next(iter(suf))
        do_cad = idx.codigo[uid]
        if "-" in cu and "-" in do_cad and cu.split("-")[0] != do_cad.split("-")[0]:
            return None, PREFIXO_DIFERENTE
        return uid, SUFIXO
    return None, (DUAS_USINAS if len(suf) > 1 else FORA_CADASTRO)


# ── a foto de ativos do Fracttal (carga única) ───────────────────────────────────────────────────────────────────

def _dia_da_foto(foto) -> str | None:
    try:
        return datetime.fromtimestamp(float(foto.get("ts")), _BRT).date().isoformat()
    except (TypeError, ValueError, OSError, AttributeError):
        return None


def _descricao(desc, codigo) -> str | None:
    """A descrição do Fracttal termina com "    { CÓDIGO }": repete o código (~20 caracteres × 22 mil linhas)."""
    d = _txt(desc)
    m = re.search(r"\s*\{\s*([^{}]*?)\s*\}\s*$", d)
    if m and canon(m.group(1)) == canon(codigo):
        d = d[:m.start()].rstrip()
    return d or None


def foto_linhas(foto_set, foto_jun=None) -> list[list]:
    """As linhas de `foto_ativos` (CAB_FOTO) a partir do cache de ativos do OS Creator ({"ts", "assets"}).
    `foto_set` é a mais nova (a de 22/09/2026: 21.638 itens); da mais velha (21/06) entram só os itens cujo código a
    nova não tem (719: renomeados ou baixados), para o código antigo que um fato ainda carrega continuar sendo membro.
    O item sem código (4) entra: é item do Fracttal e pode ser pai de outro."""
    def linha(a, dia):
        cod = canon(a.get("code"))
        return [_int(a.get("id")), cod or None, _descricao(a.get("description"), cod), _int(a.get("id_parent")),
                _txt(a.get("tipo_code")) or None, dia]
    dia = _dia_da_foto(foto_set)
    novas = sorted((linha(a, dia) for a in foto_set.get("assets") or ()), key=lambda l: (l[0] or 0, l[1] or ""))
    if not foto_jun:
        return novas
    tem = {l[1] for l in novas if l[1]}
    dia_v = _dia_da_foto(foto_jun)
    velhas = [linha(a, dia_v) for a in foto_jun.get("assets") or () if canon(a.get("code")) not in tem]
    return novas + sorted((l for l in velhas if l[1]), key=lambda l: (l[0] or 0, l[1]))


def _como_dict(linhas, cab) -> list[dict]:
    return [l if isinstance(l, dict) else dict(zip(cab, l)) for l in linhas or ()]


# ── os membros ────────────────────────────────────────────────────────────────────────────────────────────────────

def membros(foto, codigos_por_fonte: dict, usinas) -> list[list]:
    """A `dim_equipamento` (CAB_DIM), em ordem de código.
    `foto`: as linhas de `foto_ativos` (como lidas do banco, dicts; ou listas no CAB_FOTO).
    `codigos_por_fonte`: {fonte: [código de cada linha]} dos livros do banco (FONTES_BANCO + PCM).
    `usinas`: o cadastro (lista ou IndiceUsinas). Código de fonte que não é `valido` não vira membro."""
    idx = usinas if isinstance(usinas, IndiceUsinas) else IndiceUsinas(usinas)
    # a foto mais nova primeiro; no empate, o menor item
    fotos = sorted(_como_dict(foto, CAB_FOTO), reverse=True,
                   key=lambda f: (_txt(f.get("foto_em")), -(_int(f.get("fracttal_item_id")) or 0)))
    por_codigo, codigo_do_item = {}, {}
    for f in fotos:
        c, item = canon(f.get("codigo")), _int(f.get("fracttal_item_id"))
        if item and item not in codigo_do_item:
            codigo_do_item[item] = c or None
        if c and c not in por_codigo:
            por_codigo[c] = f
    em = defaultdict(set)
    for fonte, codigos in (codigos_por_fonte or {}).items():
        for c in map(canon, codigos or ()):
            if c:
                em[c].add(fonte)
    todos = set(por_codigo) | {c for c in em if valido(c, por_codigo)}
    dono, out = {}, []
    for c in sorted(todos):
        eid = equipamento_id(c)
        if dono.setdefault(eid, c) != c:
            raise ColisaoDeId(f"{dono[eid]} e {c} dão o mesmo equipamento_id {eid}")
        f = por_codigo.get(c) or {}
        uid, como = usina_do_codigo(c, idx)
        pai = codigo_do_item.get(_int(f.get("pai_item_id")))
        out.append([eid, c, _txt(f.get("descricao")) or None, uid, como if uid else None, None if uid else como,
                    familia(c), _txt(f.get("tipo_fracttal")) or None,
                    equipamento_id(pai) if pai and pai != c else None, _int(f.get("fracttal_item_id")),
                    1 if f else 0, _txt(f.get("foto_em")) or None, len(em.get(c, ()))])
    return out


def indice(dim) -> dict:
    """{código: (equipamento_id, na_foto)} da dimensão (listas no CAB_DIM ou dicts lidos do banco)."""
    out = {}
    for d in _como_dict(dim, CAB_DIM):
        c, eid = canon(d.get("codigo")), _int(d.get("equipamento_id"))
        if c and eid:
            out[c] = (eid, _int(d.get("na_foto")) == 1)
    return out


def ligar(codigo, dim_index: dict) -> tuple[int | None, str | None]:
    """(equipamento_id, por onde ligou) para o fato (fechamento, PT, ronda, programação). Não liga = (None, None).
    O ID não depende da dimensão: o código válido que ainda não é membro (fonte nova que a carga não lê) liga com o
    mesmo ID e vem marcado "fora da dimensão", para a qualidade do fato contar o órfão em vez de escondê-lo."""
    c = canon(codigo)
    if not c:
        return None, None
    m = (dim_index or {}).get(c)
    if m:
        return m[0], (NA_FOTO if m[1] else COM_USINA)
    if codigo_do_equipamento(c):
        return equipamento_id(c), FORA_DA_DIMENSAO
    return None, None


# ── apelidos: o que cada sistema chama de cada equipamento ───────────────────────────────────────────────────────

def _chave(*partes) -> str:
    return "|".join(_txt(p) for p in partes)


def _poe(cand, chave, eid, como):
    """Candidato a apelido. A mesma chave e o mesmo equipamento por dois caminhos: fica o menor `casou_por`, para o
    resultado não depender da ordem em que o banco devolveu as linhas."""
    atual = cand[chave].get(eid)
    cand[chave][eid] = como if atual is None else min(atual, como)


def _n(s) -> str:
    return " ".join(_txt(s).upper().split())


_RE_INVERSOR = re.compile(r"^\s*inversor\s*(\d+(?:\.\d+)*)\s*$", re.I)
_RE_INVR = re.compile(r"^-INVR(\d+(?:\.\d+)*)$")


def _numero(txt) -> tuple:
    return tuple(int(x) for x in txt.split("."))


def colunas_de_geracao(cabecalhos: dict, usina_da_aba: dict) -> list[dict]:
    """As colunas "Inversor n.m" das abas largas de geração, prontas para `apelidos`.
    `cabecalhos`: {(livro, aba): [nomes das colunas]}; `usina_da_aba`: {(livro, aba): usina_id} (a ligação aba →
    usina é da geração, passo 6c; aqui só se usa)."""
    out = []
    for (livro, aba), cols in sorted(cabecalhos.items()):
        for col in cols or ():
            if _RE_INVERSOR.match(_txt(col)):
                out.append({"livro": livro, "aba": aba, "coluna": _txt(col),
                            "usina_id": usina_da_aba.get((livro, aba))})
    return out


def apelidos(de_para_trackers, gemeo_alias, colunas, dim, conta: dict | None = None) -> list[list]:
    """`equipamento_apelido` (CAB_APELIDO). O modelo é o `de_para` das usinas: cada sistema guarda a chave dele e o
    equipamento_id; `casou_por` diz como.
    - Supervisório · tracker: o `de_para_trackers` (fonte | usina no supervisório | tracker → Code Fracttal);
      `casou_por` = o "Como casou" de lá (1.430 de 4.313 dizem "CONFIRMAR": a dúvida vai junto, não some);
    - BD_Thopen · coluna, BD_Performance · coluna: "aba|Inversor n.m" → o membro "<código da usina>-INVRn.m" da usina
      da aba, só se for UM (o número compara como número: "INVR01.1" = "Inversor 1.1");
    - Gêmeo · equipamento: "usina|equipamento" do gêmeo, pelo alias dele: o tracker (sistema bd_trackers) passa pelo
      de-para de trackers; o inversor (bd_performance, bd_thopen), pela coluna acima. O código do gêmeo casa 0% direto.
    Chave externa que aponta para 2 equipamentos não liga. `conta` (opcional) recebe {sistema: {motivo: n}}."""
    idx = indice(dim)
    cand = defaultdict(dict)          # (sistema, chave) -> {equipamento_id: casou_por}
    conta = conta if conta is not None else {}
    c_ = lambda sistema: conta.setdefault(sistema, Counter())     # noqa: E731
    por_tracker = defaultdict(set)
    for r in de_para_trackers or ():
        code = canon(r.get("Code Fracttal"))
        if not code:
            continue
        c_(SISTEMA_TRACKER)["linhas"] += 1
        m = idx.get(code)
        if not m:
            c_(SISTEMA_TRACKER)["código fora da dimensão"] += 1
            continue
        chave = _chave(r.get("Fonte"), r.get("UFV Supervisório"), r.get("Tracker Supervisório"))
        _poe(cand, (SISTEMA_TRACKER, chave), m[0], _txt(r.get("Como casou")) or "sem método")
        por_tracker[(_n(r.get("UFV Supervisório")), _n(r.get("Tracker Supervisório")))].add(m[0])

    # inversor da usina pelo número: (usina_id, (n, m)) -> membros
    inversor = defaultdict(set)
    for d in _como_dict(dim, CAB_DIM):
        c, uid = canon(d.get("codigo")), _int(d.get("usina_id"))
        cu = codigo_do_equipamento(c)
        m = _RE_INVR.match(c[len(cu):]) if uid and cu and c.startswith(cu) else None
        if m:
            inversor[(uid, _numero(m.group(1)))].add(_int(d.get("equipamento_id")))
    por_coluna = defaultdict(set)     # (sistema, aba, coluna) normalizados -> membros, para o alias do gêmeo
    for col in colunas or ():
        sistema = SISTEMA_COLUNA.get(_txt(col.get("livro")))
        m = _RE_INVERSOR.match(_txt(col.get("coluna")))
        if not sistema or not m:
            continue
        c_(sistema)["linhas"] += 1
        uid = _int(col.get("usina_id"))
        if not uid:
            c_(sistema)["aba sem usina"] += 1
            continue
        alvo = inversor.get((uid, _numero(m.group(1))), set())
        if len(alvo) != 1:
            c_(sistema)["sem o código do inversor" if not alvo else "2+ códigos do inversor"] += 1
            continue
        eid = next(iter(alvo))
        _poe(cand, (sistema, _chave(col.get("aba"), col.get("coluna"))), eid, "número do inversor")
        por_coluna[(sistema, _n(col.get("aba")), _n(col.get("coluna")))].add(eid)

    for a in gemeo_alias or ():
        equip, sist = _txt(a.get("equipamento")), _txt(a.get("sistema")).lower()
        if not equip:
            continue                    # alias de usina (sistema fracttal), não de equipamento
        c_(SISTEMA_GEMEO)["linhas"] += 1
        u, _, t = _txt(a.get("valor")).partition("|")
        if sist == "bd_trackers":
            alvo, como = por_tracker.get((_n(u), _n(t)), set()), "alias bd_trackers → de-para de trackers"
        elif sist in SISTEMA_COLUNA:
            alvo, como = por_coluna.get((SISTEMA_COLUNA[sist], _n(u), _n(t)), set()), f"alias {sist} → coluna da aba"
        else:
            alvo, como = set(), None
        if len(alvo) != 1:
            c_(SISTEMA_GEMEO)[f"sem caminho ({sist or 'sem sistema'})" if not alvo else "2+ equipamentos"] += 1
            continue
        _poe(cand, (SISTEMA_GEMEO, _chave(a.get("usina"), equip)), next(iter(alvo)), como)

    out = []
    for (sistema, chave), ids in sorted(cand.items()):
        if len(ids) != 1:
            c_(sistema)["chave de 2+ equipamentos"] += 1
            continue
        (eid, como), = ids.items()
        out.append([eid, sistema, chave, como])
    return out


# ── qualidade, montagem e "só publica quando muda" ──────────────────────────────────────────────────────────────

def _pct(n, total):
    return round(100.0 * n / total, 1) if total else None


def _exemplos(c: Counter) -> str | None:
    """Os 6 mais comuns; no empate, pela ordem do texto. `most_common` desempata pela ordem de inserção, e a ordem de
    um `set` de textos muda a cada processo (semente do hash): PC e servidor dariam sha diferente para o mesmo banco."""
    top = sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0])))[:6]
    return "; ".join(f"{k} ({v})" for k, v in top) or None


def qualidade(dim, apel, conta_apelidos: dict, codigos_por_fonte, agora: str) -> list[list]:
    """As linhas da aba `qualidade` (CAB_QUALIDADE). Por fonte, conta CÓDIGOS DISTINTOS, não linhas: a linha nova de
    um fato a cada hora mudaria o sha e regravaria o livro sem nada novo na dimensão (a ligação por linha é da
    qualidade de cada fato, em `nexus_fatos · qualidade`)."""
    i = {c: k for k, c in enumerate(CAB_DIM)}
    n = len(dim)
    q = [["dimensão", "membros", n, None, None, agora],
         ["dimensão", "na foto do Fracttal", sum(1 for d in dim if d[i["na_foto"]] == 1),
          _pct(sum(1 for d in dim if d[i["na_foto"]] == 1), n), None, agora],
         ["dimensão", "com usina_id", sum(1 for d in dim if d[i["usina_id"]]),
          _pct(sum(1 for d in dim if d[i["usina_id"]]), n), None, agora],
         ["dimensão", "com pai_id", sum(1 for d in dim if d[i["pai_id"]]),
          _pct(sum(1 for d in dim if d[i["pai_id"]]), n), None, agora],
         ["dimensão", "famílias", len({d[i["familia"]] for d in dim if d[i["familia"]]}), None,
          _exemplos(Counter(d[i["familia"]] for d in dim if d[i["familia"]])), agora]]
    for como, v in sorted(Counter(d[i["usina_ligada_por"]] for d in dim if d[i["usina_id"]]).items()):
        q.append(["usina ligada por", como, v, _pct(v, n), None, agora])
    for motivo, v in sorted(Counter(d[i["motivo_sem_usina"]] for d in dim if not d[i["usina_id"]]).items()):
        # o exemplo é o código da usina que faltou; sem código de usina, o formato do código ("TESTE9-ETKR9.9")
        ex = Counter((codigo_do_equipamento(d[i["codigo"]]) or re.sub(r"\d+", "9", d[i["codigo"]])) for d in dim
                     if not d[i["usina_id"]] and d[i["motivo_sem_usina"]] == motivo)
        q.append(["sem usina", motivo, v, _pct(v, n), _exemplos(ex), agora])
    # o mesmo item do Fracttal com dois códigos: renomeado entre as fotos (o custo do ID pelo código)
    itens = Counter(d[i["fracttal_item_id"]] for d in dim if d[i["fracttal_item_id"]])
    q.append(["fracttal", "itens com 2+ códigos", sum(1 for v in itens.values() if v > 1), None, None, agora])
    ix = indice(dim)
    for fonte, codigos in sorted((codigos_por_fonte or {}).items()):
        distintos = sorted({canon(c) for c in codigos or () if canon(c)})
        fora = Counter(c for c in distintos if not ligar(c, ix)[0])
        q.append(["fonte", fonte, len(distintos), _pct(len(distintos) - sum(fora.values()), len(distintos)),
                  _exemplos(fora), agora])
    por_sistema = Counter(a[1] for a in apel)
    for sistema in (SISTEMA_TRACKER, SISTEMA_GEMEO, *SISTEMA_COLUNA.values()):
        c = dict(sorted((conta_apelidos or {}).get(sistema, {}).items()))
        n_ap = por_sistema.get(sistema, 0)
        q.append(["apelido", sistema, n_ap, _pct(n_ap, c.get("linhas", 0)),
                  json.dumps(c, ensure_ascii=False) if c else None, agora])
    return q


def sha_linhas(tabelas: dict) -> str:
    """O sha do conteúdo (sem a hora): igual nas duas máquinas para o mesmo banco, porque tudo sai ordenado."""
    i_ger = CAB_QUALIDADE.index("gerado_em")
    corpo = {"dim": tabelas["dim_equipamento"][1], "apelido": tabelas["equipamento_apelido"][1],
             "qualidade": [[v for k, v in enumerate(l) if k != i_ger] for l in tabelas["qualidade"][1]]}
    return hashlib.sha1(json.dumps(corpo, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def montar(foto, codigos_por_fonte: dict, usinas, de_para_trackers, gemeo_alias, colunas_geracao, *,
           agora: str, maquina: str) -> tuple[dict, dict]:
    """(tabelas de `nexus_equipamentos`, relatório só com contagens). Não lê nada e não grava: a carga passa o que leu
    do banco. Colisão de ID sobe (ColisaoDeId): a carga não publica."""
    idx = IndiceUsinas(usinas)
    dim = membros(foto, codigos_por_fonte, idx)
    conta = {}
    apel = apelidos(de_para_trackers, gemeo_alias, colunas_geracao, dim, conta)
    q = qualidade(dim, apel, conta, codigos_por_fonte, agora)
    tabelas = {"dim_equipamento": (CAB_DIM, dim), "equipamento_apelido": (CAB_APELIDO, apel),
               "qualidade": (CAB_QUALIDADE, q)}
    sha = sha_linhas(tabelas)
    tabelas["atualizacao"] = (CAB_ATUALIZACAO, [[agora, maquina, None, len(dim), sha,
                                                 "equipamento_id = sha1('fracttal:' + código)[:13 hex] >> 3 (49 bits); o fato liga "
                                                 "pelo código; vazio = não ligou (ver qualidade)"]])
    i = {c: k for k, c in enumerate(CAB_DIM)}
    ix = indice(dim)
    por_linha = {}                    # a ligação por LINHA de cada fonte (o número que o fato vai ter); fora do sha
    for fonte, codigos in sorted((codigos_por_fonte or {}).items()):
        linhas = [c for c in map(canon, codigos or ()) if c]
        por_linha[fonte] = [len(linhas), sum(1 for c in linhas if ligar(c, ix)[0])]
    rel = {"membros": len(dim), "na_foto": sum(1 for d in dim if d[i["na_foto"]] == 1),
           "com_usina": sum(1 for d in dim if d[i["usina_id"]]),
           "pct_usina": _pct(sum(1 for d in dim if d[i["usina_id"]]), len(dim)),
           "fontes_linhas_e_ligadas": por_linha,
           "apelidos": len(apel), "apelidos_por_sistema": dict(Counter(a[1] for a in apel)), "sha_linhas": sha}
    if not foto:
        rel["aviso"] = "sem a foto de ativos no banco: a dimensão tem só os códigos das fontes"
    return tabelas, rel


def mudou(tabelas: dict, atualizacao_anterior) -> bool:
    """True se o sha das linhas difere do gravado na `atualizacao` anterior (ou se não há anterior). A dimensão muda
    por semana e tem ~1 MB: regravar a cada hora seria 24 trocas integrais por dia sem nada novo."""
    novo = tabelas["atualizacao"][1][0][CAB_ATUALIZACAO.index("sha_linhas")]
    for a in atualizacao_anterior or ():
        return _txt(a.get("sha_linhas")) != novo
    return True
