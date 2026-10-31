"""ativos_leitor.py: os ativos do Fracttal lidos pelo PRÓPRIO servidor, pela credencial da empresa (31/10/2026, etapa 2 do
canto central; desenho `docs/superpowers/specs/2026-10-30-oscreator-canto-central-design.md`, "Etapa 2").

Até aqui o catálogo de ativos do OS Creator só se renovava pelo RPC (`api.get_assets`), com a sessão da 1ª pessoa que o achava
vencido: ~110 pedidos de 200 ativos, e o botão "Atualizar ativos" fazia a pessoa esperar minutos. Agora:
- DE MADRUGADA (02:15 de Brasília, `ler_completo`): o REST `items` inteiro, ordenado pelo id, 100 por página e 1 pedido por
  segundo (~270 pedidos, ~5 min, longe do campo e da cota da empresa: 200 por minuto, dividida com o App de Campo). A leitura
  que não chega ao total que o Fracttal informa, ou que ele recusa, não troca nada (`LeituraIncompleta`). A que chega é
  CONFERIDA contra o catálogo de agora (`conferir_paridade`: na 1ª noite ele é o do RPC, e a conferência é REST x RPC de
  verdade; depois, a leitura anterior) e só então vai ao catálogo (`ativos_central.trocar`, que ainda recusa a que encolhe)
  e, aceita, à foto do banco (`nexus/dados/foto_ativos.py`; uma guarda só).
- DE DIA, SÓ OS NOVOS (de 30 em 30 min, das 06:08 às 21:38, `ler_novos`): ordenados do maior id para o menor, até uma página
  inteira de ids que o catálogo já tem (1 pedido sem novidade, 2 com). Somam-se ao catálogo (`ativos_central.acrescentar`),
  sem mexer no `lido_em` da lista inteira. Os três botões "Atualizar ativos" e a aprovação da Fila que não acha o ativo pedem
  esta leitura (`pedir_novos`, `esperar_novos`, que diz o desfecho: terminou, falhou, ficou para a noite), por trás.
- A PARIDADE QUE FALHOU (ou que ainda não houve, ou que passou de 30 h) deixa tudo como era: o REST não troca nem soma nada, o
  motivo fica no estado, o catálogo vence no prazo de sempre e a 1ª sessão do dia o renova pelo RPC (o renovador de antes, uma
  vez por dia, para todos). A leitura REST que FALHA (a da noite ou a dos novos) também tira a prontidão do leitor até a
  próxima boa (`ativos_central.anotar_leitura_rest`): os botões voltam ao RPC (revisão 1 da 2.2). A sondagem que o desenho
  pedia (o REST dá os mesmos campos do RPC?) não pôde ser feita antes de construir: é esta conferência, toda noite, que a faz.

Só o `servir.py` liga (`ligar`); o `app.py` (o PC) e os testes seguem sem ele, como o `nexus/casca/teto_os.py`. Sem a
credencial REST (o PC, a worktree sem `FRACTTAL_CLIENT_ID`) ele não liga, o estado diz por quê, e nada quebra.

O cliente HTTP e o ritmo são os que já existem (`nexus/campo/fracttal.py`, como `nexus/engenharia/os_falhas.py` pagina): 1 s
entre as páginas; o 406/429 o próprio cliente espera (5 s e 10 s) e, se ele desistir, este espera o castigo de 1 min do
Fracttal (medido em 19/08 no robô do PCM) e tenta a mesma página de novo, duas vezes; a conexão que caiu, o tempo esgotado e o
5xx também; o resto (400, 401, 403, 404) falha na hora (`_transitorio`). Os campos do `items` que se guardam
(`CAMPOS_REST`) são os do registro do RPC: o REST não foi sondado antes de construir (31/10/2026), e o que faltar aparece na
conferência da 1ª noite, que então falha e diz o campo.
"""
from __future__ import annotations

import functools
import logging
import os
import threading
import time
from collections import Counter

import requests

import ativos_central
import ativos_foto
from ativos_central import montar_registros

log = logging.getLogger("oscreator.ativos_leitor")

POR_PAGINA = 100                 # o REST do Fracttal dá no máximo 100 por pedido (com mais, corta a paginação)
PAUSA_S = 1.0                    # 1 pedido por segundo, como o robô do PCM no Actions e o `os_falhas`
ESPERAS_RECUSA_S = (62, 62)      # depois que o cliente desiste do 406/429: o castigo de 1 min, e a mesma página de novo
PAGINAS_MAX = 600                # 60 mil itens: um filtro ignorado não vira um laço sem fim
PAGINAS_NOVOS_MAX = 5            # mais de 400 ativos novos num dia (a 5ª página tem de ser toda conhecida): ficam para a noite
# os campos do `items` que o catálogo usa (os do registro do RPC, `inventories.items_list`); o resto do item (coordenadas,
# campos livres) sai assim que a página chega: são ~27 mil itens, e o servidor já anda apertado de memória
CAMPOS_REST = ("id", "code", "description", "id_parent", "parent_description", "id_type_item", "id_group_task")
OBRIGATORIOS = ("id", "id_parent", "id_type_item")       # sem eles a criação de OS e o drill-down da tela de Ativos quebram
PARIDADE_MIN_PCT = 99.0          # dos códigos em comum, os que dão o mesmo cliente e usina
CAMPOS_MIN_PCT = 99.0            # dos registros, os que têm os campos obrigatórios
COBERTURA_MIN_PCT = 95.0         # dos códigos da leitura, os que o catálogo também tem (toda noite)
PRIMEIRA_MIN_PCT = 99.0          # na 1ª conferência (a sondagem REST x RPC), nos dois sentidos
EXEMPLOS = 5                     # quantos códigos que faltam o motivo da paridade mostra
HORA_COMPLETO = (2, 15)          # a leitura inteira, em Brasília: longe dos laços de hora em hora (:10 a :50) e do campo
NOVOS_DAS, NOVOS_ATE = 6, 22     # os novos, de 30 em 30 min, das 06h às 22h
NOVOS_MINUTOS = (8, 38)          # fora dos minutos ocupados (tarefas :10 a :20, normalizações :22, App :25, carga :40...)
NOVOS_FRESCO_S = 60              # os novos lidos há menos disto servem a quem pede (botão, aprovação): não se lê de novo
DESFECHO_VALE_S = 2 * NOVOS_FRESCO_S     # o desfecho de uma leitura mais velha que isto não é o "de agora" (o F5 da Fila)
COMPLETO, NOVOS = "completo", "novos"
CHAVE = "oscreator_ativos_leitor"
_BRT_S = -3 * 3600               # Brasília é UTC-3 fixo

_dormir = time.sleep             # os testes trocam (o ritmo e as esperas da recusa sem esperar de verdade)
_TRAVA_LEITURA = threading.Lock()                # uma leitura do Fracttal por vez daqui: a inteira ou a dos novos
_COND = threading.Condition()                    # quem espera os novos (a aprovação, o "?novos=1" das telas)
_NOVOS: dict = {"lendo": False, "fim_em": 0.0}
_APP: dict = {"app": None}


def _estado_limpo() -> dict:
    # `descricao_cortada`: quantas descrições o detector de endereço cortou na última foto renovada, com até 5 ids (nunca o
    # texto; Ruling AN). É o termômetro do detector: o nome que perde pedaço sem ser endereço aparece aqui
    return {"ligado": False, "motivo": "não ligado (só o servir.py liga o leitor)", "credencial": None,
            "completo": None, "novos": None, "descricao_cortada": None}


_ESTADO: dict = _estado_limpo()


class LeituraIncompleta(RuntimeError):
    """A leitura inteira não chegou ao total que o Fracttal informou (página curta, itens a menos): não troca nada."""


class ForaDeOrdem(RuntimeError):
    """A página dos novos não veio do maior id para o menor (o `sort` ignorado): não se acrescenta nada."""


class MuitosNovos(RuntimeError):
    """Mais novos do que a leitura curta lê: ficam para a leitura da noite. `n` são os novos que ela chegou a ver; `exato`,
    se ela viu todos (a última página já chegava aos ids conhecidos) ou se havia mais além do teto (a última página toda de
    novos: a tela diz "mais de N"). Não é falha do REST (ele respondeu, e em ordem)."""

    def __init__(self, mensagem: str, n: int = 0, exato: bool = False):
        super().__init__(mensagem)
        self.n, self.exato = n, exato


def _int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError, OverflowError):
        return None


def _dados(r) -> list:
    d = (r.get("data") if isinstance(r, dict) else r) or []
    return [i for i in d if isinstance(i, dict)] if isinstance(d, list) else []


def _total(r):
    """O `total` do envelope (vem como número ou como texto, conforme o recurso), ou None."""
    try:
        return int(r.get("total")) if isinstance(r, dict) and r.get("total") not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _enxuto(it: dict) -> dict:
    return {k: it[k] for k in CAMPOS_REST if k in it}


def _transitorio(e: BaseException) -> bool:
    """Vale pedir a mesma página de novo: a recusa por excesso (o cliente já esperou 5 s e 10 s), a conexão que caiu, o tempo
    esgotado e o erro do lado do Fracttal (5xx). O resto (400, 401, 403, 404, a resposta que não é JSON) daria o mesmo na
    próxima vez: falha na hora, em vez de esperar 1 min duas vezes à toa (revisão 1 da 2.2)."""
    from nexus.campo import fracttal
    if isinstance(e, (fracttal.Recusado, requests.ConnectionError, requests.Timeout)):
        return True
    if isinstance(e, requests.HTTPError):
        st = getattr(getattr(e, "response", None), "status_code", None)
        return isinstance(st, int) and st >= 500
    return False


def _pedir(ler, path: str, conta: list):
    """Um pedido, com a 2ª chance só para o erro de passagem (`_transitorio`): o castigo de 1 min do 406/429, e a mesma
    página de novo, duas vezes."""
    for tentativa in range(len(ESPERAS_RECUSA_S) + 1):
        conta[0] += 1
        try:
            return ler(path)
        except Exception as e:
            if not _transitorio(e) or tentativa >= len(ESPERAS_RECUSA_S):
                raise
            log.warning("leitor de ativos: o Fracttal não deu %s (%s); espero %d s e tento de novo", path.split("?")[0],
                        str(e)[:120], ESPERAS_RECUSA_S[tentativa])
            _dormir(ESPERAS_RECUSA_S[tentativa])


def _ler_padrao(ler):
    if ler is not None:
        return ler
    from nexus.campo import fracttal
    return fracttal.ler


# ── as duas leituras ───────────────────────────────────────────────────────────────────────────────────────────────────
def _motivo_da_1a_pagina(st: int) -> str:
    """O 4xx da 1ª página em palavras (revisão 2 da 2.2): só o 400 e o 422 são o REST recusando a ordem (o `sort`); o 401 e o
    403 são a credencial da empresa recusada; o resto, o HTTP. Antes, todo 4xx culpava o `sort`, e quem lia o estado ia
    atrás da coisa errada."""
    if st in (400, 422):
        return "o REST recusou a leitura ordenada pelo id (sort=id:asc, HTTP %d): sem a ordem, as páginas não são estáveis" % st
    if st in (401, 403):
        return "o REST recusou a credencial da empresa (HTTP %d)" % st
    return "o REST respondeu HTTP %d na 1ª página" % st


def ler_todos_rest(ler=None, conta: list | None = None) -> list[dict]:
    """Todos os itens do Fracttal pelo REST `items`, ordenados pelo id (`sort=id:asc`: o deslocamento de cada página só é
    estável sobre uma ordem declarada), 100 por página, 1 pedido por segundo, até o `total` que a 1ª página informa (sem total:
    até a página com menos de 100). Repetido entre páginas conta uma vez (pelo id). Levanta `LeituraIncompleta` se a 1ª página
    vem com 4xx (o motivo diz qual: a ordem, a credencial ou o HTTP, `_motivo_da_1a_pagina`), se uma página vem curta antes do
    total, se os itens distintos não chegam a ele, ou se não veio nada: leitura incompleta não troca o que existe, e tudo
    segue pelo RPC. Só os `CAMPOS_REST` ficam."""
    ler = _ler_padrao(ler)
    conta = conta if conta is not None else [0]
    por_id: dict = {}
    inicio, total = 0, None
    for n in range(PAGINAS_MAX):
        if n:
            _dormir(PAUSA_S)
        try:
            r = _pedir(ler, "items?sort=id:asc&limit=%d&start=%d" % (POR_PAGINA, inicio), conta)
        except requests.HTTPError as e:
            st = getattr(getattr(e, "response", None), "status_code", None)
            if n == 0 and isinstance(st, int) and 400 <= st < 500:
                raise LeituraIncompleta(_motivo_da_1a_pagina(st) + "; o catálogo segue pelo RPC") from e
            raise
        pagina = _dados(r)
        if total is None:
            total = _total(r)
        for it in pagina:
            i = _int(it.get("id"))
            if i is not None:
                por_id[i] = _enxuto(it)
        inicio += POR_PAGINA
        if total is not None and inicio >= total:
            break
        if len(pagina) < POR_PAGINA:
            if total is not None:
                raise LeituraIncompleta("a página que começa em %d veio com %d itens, antes do total de %d"
                                        % (inicio - POR_PAGINA, len(pagina), total))
            break
    else:
        raise LeituraIncompleta("passou de %d páginas sem chegar ao fim" % PAGINAS_MAX)
    if not por_id:
        raise LeituraIncompleta("a leitura veio vazia")
    if total is not None and len(por_id) < total:
        raise LeituraIncompleta("vieram %d itens distintos e o Fracttal informou %d" % (len(por_id), total))
    return list(por_id.values())


def ler_novos_rest(maior_id: int, ler=None, conta: list | None = None) -> list[dict]:
    """Os itens com id maior que `maior_id` (o maior do catálogo), do mais novo para o mais velho (`sort=id:desc`), até uma
    página INTEIRA de ids já conhecidos (1 pedido quando não há novidade, 2 quando há) ou a página curta (o fim). A página que
    não vem em ordem decrescente de id, ou que não continua a anterior, levanta `ForaDeOrdem`: com o `sort` ignorado, "a
    página conhecida" não quer dizer nada. Mais de `PAGINAS_NOVOS_MAX` páginas: `MuitosNovos`."""
    ler = _ler_padrao(ler)
    conta = conta if conta is not None else [0]
    novos: dict = {}
    inicio, anterior = 0, None
    for n in range(PAGINAS_NOVOS_MAX):
        if n:
            _dormir(PAUSA_S)
        pagina = _dados(_pedir(ler, "items?sort=id:desc&limit=%d&start=%d" % (POR_PAGINA, inicio), conta))
        ids = [_int(it.get("id")) for it in pagina]
        if any(i is None for i in ids) or any(a <= b for a, b in zip(ids, ids[1:])) or (
                anterior is not None and ids and ids[0] >= anterior):
            raise ForaDeOrdem("a página que começa em %d não veio do maior id para o menor" % inicio)
        for it, i in zip(pagina, ids):
            if i > maior_id:
                novos.setdefault(i, _enxuto(it))
        if not pagina or len(pagina) < POR_PAGINA or all(i <= maior_id for i in ids):
            return list(novos.values())
        anterior = ids[-1]
        inicio += POR_PAGINA
    # a última página lida ainda trazia novos: só cabem (PAGINAS_NOVOS_MAX - 1) páginas inteiras de novos antes da conhecida.
    # Se ela já tinha ids conhecidos no fim, a conta dos novos é exata; toda de novos, havia mais do que se viu
    raise MuitosNovos("mais de %d ativos novos desde o último catálogo: ficam para a leitura da noite"
                      % ((PAGINAS_NOVOS_MAX - 1) * POR_PAGINA), n=len(novos), exato=any(i <= maior_id for i in ids))


# ── do REST ao registro, e a conferência ───────────────────────────────────────────────────────────────────────────────
def _trechos(parent_description) -> list:
    return [s.strip() for s in str(parent_description or "").split("/") if s.strip()]


def _raizes(cat) -> dict:
    """{id da raiz do cliente: nome dele} tirado do próprio catálogo: o item-usina (um trecho só no caminho) é filho da raiz,
    e o trecho é o nome dela como o Fracttal o escreve. O catálogo não guarda as raízes (o `montar_registros` as tira), e
    são elas que dão o cliente ao ativo novo de uma usina nova de um cliente que já existe."""
    out: dict = {}
    for r in cat.lista:
        t = _trechos(r.get("parent_description"))
        pai = _int(r.get("id_parent"))
        if len(t) == 1 and pai is not None:
            out.setdefault(pai, t[0])
    return out


def para_registro(itens_rest, *, catalogo=None, foto=None, pais_do_catalogo: bool = False,
                  sem_pai: list | None = None) -> list[dict]:
    """Os itens do REST no formato cru do RPC (`inventories.items_list`), o que o `montar_registros` (`api._build_records`)
    recebe: id, code, description, id_parent, id_type_item, id_group_task e parent_description.
    - `parent_description`: o do próprio item, se o REST o der; senão montado pela cadeia de `id_parent` (`ativos_foto.caminhos`,
      as descrições dos ancestrais, a raiz do cliente inclusive), com os próprios itens lidos e, para os novos do dia
      (`pais_do_catalogo`), os do catálogo e as raízes dos clientes tiradas dele. A raiz sai com "" (o `montar_registros` a
      tira). O item cujo pai não se acha sai com None (o `montar_registros` o tira também) e o id vai para `sem_pai`: fica para
      a leitura da noite, e a foto do banco o guarda assim mesmo.
    - `id_group_task`: o do item, se vier; senão o do `catalogo` pelo mesmo id (o de antes, que na 1ª noite veio do RPC);
      senão o da `foto` (as linhas do banco, em dicionários ou nas listas de `foto_ativos.ler`) pelo mesmo id; senão None.
    - `id_type_item`: só o do item (é por ele que a paridade sabe se o REST o dá)."""
    itens = [i for i in (itens_rest or ()) if isinstance(i, dict) and _int(i.get("id")) is not None]
    nos: dict = {}
    if pais_do_catalogo and catalogo is not None:
        for r in catalogo.lista:
            rid = _int(r.get("id"))
            if rid is not None:
                nos[rid] = (_int(r.get("id_parent")), r.get("description") or "")
        for raiz, nome in _raizes(catalogo).items():
            nos.setdefault(raiz, (None, nome))
    for i in itens:
        nos[_int(i["id"])] = (_int(i.get("id_parent")), str(i.get("description") or ""))
    precisam = [_int(i["id"]) for i in itens if not i.get("parent_description")]
    cam = ativos_foto.caminhos(nos, precisam) if precisam else {}
    grupo_cat = catalogo.por_id if catalogo is not None else {}
    grupo_foto: dict = {}
    i_item, i_grupo = ativos_foto.CAB_FOTO.index("fracttal_item_id"), ativos_foto.CAB_FOTO.index("id_group_task")
    for l in foto or ():
        if isinstance(l, dict):
            f, g = _int(l.get("fracttal_item_id")), _int(l.get("id_group_task"))
        else:                                                        # a linha em lista (`foto_ativos.ler`)
            f, g = _int(l[i_item]), (_int(l[i_grupo]) if len(l) > i_grupo else None)
        if g is not None and f is not None:
            grupo_foto.setdefault(f, g)
    out = []
    for i in itens:
        iid = _int(i["id"])
        caminho = i.get("parent_description") or cam.get(iid)
        if caminho is None:
            if sem_pai is not None:
                sem_pai.append(iid)
        grupo = _int(i.get("id_group_task"))
        if grupo is None:
            grupo = _int((grupo_cat.get(iid) or {}).get("id_group_task"))
        if grupo is None:
            grupo = grupo_foto.get(iid)
        out.append({"id": iid, "code": str(i.get("code") or ""), "description": str(i.get("description") or ""),
                    "id_parent": _int(i.get("id_parent")), "id_type_item": _int(i.get("id_type_item")),
                    "id_group_task": grupo, "parent_description": caminho})
    return out


def _exemplos(codigos) -> str:
    """Até `EXEMPLOS` códigos, em ordem, para o motivo dizer QUAIS (o código do ativo não é dado pessoal)."""
    lista = sorted(codigos)
    return ", ".join(lista[:EXEMPLOS]) + (" e mais %d" % (len(lista) - EXEMPLOS) if len(lista) > EXEMPLOS else "")


def conferir_paridade(registros, referencia_por_codigo, *, primeira: bool = False,
                      medidas: dict | None = None) -> tuple[bool, str, float]:
    """(vale, motivo, % dos códigos em comum com o mesmo cliente e usina). A leitura REST vale contra o catálogo de agora
    (`ativos_central.atual().por_codigo`) se:
    - dos códigos em comum, >= 99% dão o mesmo cliente e a mesma usina;
    - >= 99% dos registros têm os campos obrigatórios (`OBRIGATORIOS`: id, id_parent, id_type_item);
    - >= 95% dos códigos da leitura estão no catálogo (o REST que trouxesse o que o RPC não traz, como os inativos, não vale só
      porque os em comum batem);
    - na `primeira` conferência (o REST ainda não valeu, ou a última que valeu passou de 30 h: é a sondagem REST x RPC),
      >= 99% nos DOIS sentidos, e o motivo diz até 5 códigos dos que faltam de cada lado (revisão 1 da 2.2: com 95%, até 5% dos
      códigos do RPC podiam faltar no REST, saíam do catálogo e a foto do banco os marcava "fora do Fracttal" sem estarem).
      Depois dela, a leitura que encolhe passa daqui e vai ao `ativos_central.trocar`, que a recusa e só a aceita confirmada
      por duas leituras (o encolhimento de verdade).
    `medidas` (opcional) recebe as coberturas de toda noite, para o estado: `cob_ref` (% dos códigos do catálogo na leitura),
    `cob_rest` (% dos da leitura no catálogo), `comuns`, `n_ref` e `n_rest`.
    Os 7 itens-usina pendurados na planta errada (`corrigir_itens_usina_estrangeiros`) chegam aqui sem o conserto e contam
    como diferentes: 7 em 27 mil não mexem nos 99%."""
    ref = referencia_por_codigo or {}
    registros = list(registros or ())
    if not registros:
        return False, "a leitura não deu nenhum ativo com caminho (o REST trouxe o pai de cada item?)", 0.0
    if not ref:
        return False, "sem catálogo para conferir a leitura (a 1ª leitura vem pelo RPC, com a sessão da 1ª pessoa)", 0.0
    faltam: Counter = Counter()
    sem = 0
    for r in registros:
        vazios = [c for c in OBRIGATORIOS if r.get(c) is None]
        faltam.update(vazios)
        sem += bool(vazios)
    pct_campos = 100.0 * (len(registros) - sem) / len(registros)
    por_codigo: dict = {}
    for r in registros:
        if r.get("code"):
            por_codigo.setdefault(r["code"], r)
    # o catálogo pode ter o mesmo registro em duas chaves (o código e ele aparado): conta-se o registro, uma vez
    do_ref: dict = {}
    for c, r in ref.items():
        do_ref.setdefault(id(r), c)
    n_ref = len(do_ref)
    comuns = [c for c in por_codigo if c in ref]
    vistos = {id(ref[c]) for c in comuns}
    cob_ref = 100.0 * len(vistos) / max(n_ref, 1)
    cob_rest = 100.0 * len(comuns) / max(len(por_codigo), 1)
    if medidas is not None:
        medidas.update(cob_ref=round(cob_ref, 2), cob_rest=round(cob_rest, 2), comuns=len(comuns), n_ref=n_ref,
                       n_rest=len(por_codigo))
    if not comuns:
        return False, "nenhum código da leitura está no catálogo de agora", 0.0
    iguais = sum(1 for c in comuns if (por_codigo[c].get("cliente"), por_codigo[c].get("usina"))
                 == (ref[c].get("cliente"), ref[c].get("usina")))
    pct = round(100.0 * iguais / len(comuns), 2)
    problemas = []
    if pct < PARIDADE_MIN_PCT:
        problemas.append("só %.2f%% dos %d códigos em comum dão o mesmo cliente e usina (o mínimo é %.0f%%)"
                         % (pct, len(comuns), PARIDADE_MIN_PCT))
    if pct_campos < CAMPOS_MIN_PCT:
        problemas.append("faltam campos obrigatórios em %d de %d ativos (%s)" % (
            sem, len(registros), ", ".join("%s: %d" % kv for kv in sorted(faltam.items()))))
    minimo = PRIMEIRA_MIN_PCT if primeira else COBERTURA_MIN_PCT
    if primeira and cob_ref < PRIMEIRA_MIN_PCT:
        so_ref = [c for i, c in do_ref.items() if i not in vistos]
        problemas.append("na 1ª conferência, a leitura não tem %d dos %d códigos do catálogo (%.2f%%; o mínimo é %.0f%%), "
                         "por exemplo %s" % (len(so_ref), n_ref, cob_ref, PRIMEIRA_MIN_PCT, _exemplos(so_ref)))
    if cob_rest < minimo:
        so_rest = [c for c in por_codigo if c not in ref]
        problemas.append("a leitura traz %d códigos que o catálogo não tem, de %d (%.2f%%; o mínimo é %.0f%%), por exemplo %s"
                         % (len(so_rest), len(por_codigo), cob_rest, minimo, _exemplos(so_rest)))
    if problemas:
        return False, "; ".join(problemas), pct
    return True, ("%d códigos em comum, %.2f%% com o mesmo cliente e usina; os campos obrigatórios em %.2f%% dos ativos; "
                  "a leitura tem %.2f%% dos códigos do catálogo e o catálogo, %.2f%% dos dela"
                  % (len(comuns), pct, pct_campos, cob_ref, cob_rest)), pct


# ── a leitura da noite e a dos novos ───────────────────────────────────────────────────────────────────────────────────
def _hora(ts) -> str:
    return time.strftime("%d/%m %H:%M", time.gmtime(ts + _BRT_S)) if ts else "-"


def _banco(app):
    """(base, token, sessão) do banco, ou None no teste sem a sessão de mentira (teste nunca vai à rede)."""
    from nexus.cadastro.ligacoes import BASE_API
    sessao = app.extensions.get("nexus_dados_sessao") if app is not None else None
    if sessao is None:
        if app is None or app.config.get("TESTING"):
            return None
        sessao = requests.Session()
    return (app.config.get("GRIDCO_DB_API") or BASE_API).rstrip("/"), app.config.get("GRIDCO_SQL_TOKEN") or "", sessao


def _motivo(e: BaseException) -> str:
    return "%s: %s" % (type(e).__name__, str(e)[:160])


def _grafo_de_quem_saiu(nos: dict, antigas, chaves_de_hoje: set) -> dict:
    """O grafo que dá o nome das linhas da foto que NÃO vieram na leitura de hoje (Ruling AN, revisão 2 da 2.2): só a cadeia
    de pais de cada uma, tirada dos itens lidos hoje (`nos`, com a descrição inteira: a cauda de endereço da usina sai igual à
    das linhas novas) e, para o pai que também não veio, da linha antiga dele (id, pai, descrição velha). Pequeno de propósito
    (os 719 de junho e os que saírem): o grafo inteiro ficaria vivo até o fim da gravação, num servidor apertado de memória.
    `antigas`: as linhas de `foto_ativos.ler` (listas na ordem de `CAB_FOTO`) ou dicionários; `chaves_de_hoje`: os pares
    (id, código) das linhas de hoje."""
    i_id, i_cod, i_desc, i_pai = (ativos_foto.CAB_FOTO.index(c)
                                  for c in ("fracttal_item_id", "codigo", "descricao", "pai_item_id"))
    velhas: dict = {}
    pais = []
    for l in antigas or ():
        if isinstance(l, dict):
            i, cod, desc, pai = (_int(l.get("fracttal_item_id")), l.get("codigo"), l.get("descricao"),
                                 _int(l.get("pai_item_id")))
        else:
            i, cod, desc, pai = _int(l[i_id]), l[i_cod], l[i_desc], _int(l[i_pai])
        if i is None:
            continue
        if i not in nos:
            velhas.setdefault(i, (pai, desc or ""))
        if (i, cod) not in chaves_de_hoje:
            pais.append(pai)
    grafo: dict = {}
    for p in pais:
        for _ in range(ativos_foto.NIVEIS_MAX):
            if p is None or p in grafo:
                break
            no = nos.get(p) or velhas.get(p)
            if no is None:
                break
            grafo[p] = no
            p = no[0]
    return grafo


def ler_completo(app, *, ler=None, esperar_s: float = 0) -> dict:
    """A leitura da noite: o Fracttal inteiro pelo REST, a conferência contra o catálogo de agora, a troca do catálogo e, se
    ela entrou, a foto do banco renovada. Cada passo que não dá deixa o de antes e diz no estado (`estado()["completo"]`).
    A leitura que não vem inteira (ou que o Fracttal recusa) é uma falha do REST: tira a prontidão do leitor
    (`ativos_central.anotar_leitura_rest`); a que vem inteira é uma leitura boa, valha a conferência ou não.
    Uma leitura do Fracttal por vez: a dos novos pula enquanto esta corre; esta espera a dos novos até `esperar_s`."""
    rel = {"inicio": time.time(), "fim": None, "pedidos": 0, "itens": 0, "registros": 0, "sem_pai": 0,
           "resultado": "", "foto": None}
    pegou = _TRAVA_LEITURA.acquire(timeout=esperar_s) if esperar_s > 0 else _TRAVA_LEITURA.acquire(blocking=False)
    if not pegou:
        rel["resultado"] = "já havia uma leitura do Fracttal em curso"
        return rel
    conta = [0]
    try:
        try:
            itens = ler_todos_rest(ler=ler, conta=conta)
        except Exception as e:                                       # noqa: BLE001 — incompleta, recusada, rede: nada troca
            rel["resultado"] = "a leitura não veio inteira (%s): nada mudou, e o catálogo segue pelo RPC" % _motivo(e)
            ativos_central.anotar_leitura_rest(False, "a leitura da noite: " + _motivo(e))
            log.warning("leitor de ativos: %s", rel["resultado"])
            return rel
        ativos_central.anotar_leitura_rest(True)
        lido_em = time.time()
        rel["itens"] = len(itens)
        banco = _banco(app)
        antigas, de_11_10 = None, False
        if banco is not None:
            try:
                from nexus.dados import foto_ativos
                antigas, de_11_10 = foto_ativos.ler(banco[0], banco[2])
            except Exception as e:                                   # noqa: BLE001 — o catálogo anda; a foto, não
                rel["foto"] = {"erro": "não li a foto do banco (%s)" % _motivo(e)}
        ref = ativos_central.atual()
        sem_pai: list = []
        cru = para_registro(itens, catalogo=ref, foto=antigas, sem_pai=sem_pai)
        # cada passo larga o que já serviu: tudo junto, o pico da noite media ~72 MB, num servidor já apertado de memória
        del itens
        registros = montar_registros(cru)
        # o que a foto guarda e o catálogo não tem (as raízes dos clientes, os itens sem o pai, o caminho sem trecho): pela
        # diferença de ids, e não por repetir aqui a regra do `montar_registros`
        no_catalogo = {r["id"] for r in registros}
        fora_do_catalogo = [c for c in cru if c["id"] not in no_catalogo]
        del cru, no_catalogo
        rel.update(registros=len(registros), sem_pai=len(sem_pai))
        primeira = ativos_central.paridade_recente() is None
        medidas: dict = {}
        vale, motivo, pct = conferir_paridade(registros, ref.por_codigo if ref is not None else {}, primeira=primeira,
                                              medidas=medidas)
        ativos_central.anotar_paridade_rest(dict(
            medidas, vale=vale, motivo=motivo, pct=pct, em=time.time(), lido_em=lido_em, n=len(registros),
            primeira=primeira, contra=ref.fonte if ref is not None else None,
            contra_lido_em=ref.lido_em if ref is not None else None))
        if not vale:
            rel["resultado"] = ("a leitura não bate com o catálogo de agora (%s, de %s): nada mudou, e o catálogo segue pelo "
                                "RPC" % (ref.fonte if ref is not None else "nenhum", _hora(ref.lido_em if ref else 0))
                                + "; " + motivo)
            log.warning("leitor de ativos: %s", rel["resultado"])
            return rel
        versao_antes = ref.versao if ref is not None else None
        if not ativos_central.trocar(registros, "rest", lido_em=lido_em):
            rel["resultado"] = "o catálogo recusou a leitura: %s" % ((ativos_central.estado()["recusa"] or {}).get("motivo"))
            return rel
        del registros
        cat = ativos_central.atual()
        rel["resultado"] = "a mesma lista de antes (só a hora renovada)" if cat.versao == versao_antes else "trocou"
        # a foto do banco: só depois que o catálogo aceitou (a mesma guarda vale para os dois). As linhas saem do catálogo que
        # acabou de entrar (os mesmos itens, com o tipo) e dos que ele não tem
        if banco is None:
            rel["foto"] = {"erro": "teste sem banco"}
        elif antigas is not None:
            from nexus.dados import foto_ativos
            # a descrição SEM o endereço da usina (Ruling AK): o mesmo corte do nome do item no caminho. A API do banco tem
            # leitura aberta, e o endereço da usina já saiu dela uma vez, no mesmo dia (04/10/2026, a 1ª carga do Campo · App)
            nos = {r["id"]: (r.get("id_parent"), r.get("description") or "") for r in cat.lista}
            for c in fora_do_catalogo:
                nos.setdefault(c["id"], (c.get("id_parent"), c.get("description") or ""))
            # a usina cujo nome fechou no padrão "Cliente - Usina - UF" não passa pelo detector da foto (Ruling AQ): usina de
            # fazenda ("CL - UFV Fazenda X - MT") é comum, e o detector a cortaria no "Fazenda"
            usinas_no_padrao: set = set()
            nomes = ativos_foto.nomes_no_caminho(nos, usinas_no_padrao=usinas_no_padrao)
            novas = [foto_ativos.linha_do_item(r, r.get("tipo_code"), nome=nomes.get(r["id"])) for r in cat.lista]
            novas += [foto_ativos.linha_do_item(c, nome=nomes.get(c["id"])) for c in fora_do_catalogo]
            del nomes
            # e a linha que não veio hoje (Ruling AN): o nome pela própria descrição e pelo próprio pai, com a cadeia tirada
            # do que se leu hoje e das linhas antigas que também não vieram; o detector de endereço é da foto
            grafo = _grafo_de_quem_saiu(nos, antigas, {(l[0], l[1]) for l in novas})
            del nos
            try:
                rel["foto"] = foto_ativos.gravar(novas, base=banco[0], token=banco[1], sessao=banco[2],
                                                 maquina="servidor" if os.name != "nt" else "pc", antigas=antigas,
                                                 de_11_10=de_11_10, usinas_no_padrao=usinas_no_padrao,
                                                 nome_de_quem_saiu=functools.partial(ativos_foto.nome_pelo_pai, grafo,
                                                                                     caudas={}))
                _ESTADO["descricao_cortada"] = {"n": rel["foto"].get("descricao_cortada", 0),
                                                "exemplos": list(rel["foto"].get("descricao_cortada_exemplos") or ())}
            except Exception as e:                                   # noqa: BLE001 — recusada, curta, banco fora: fica a de antes
                rel["foto"] = {"erro": _motivo(e)}
                log.warning("leitor de ativos: a foto do banco não foi renovada (%s)", rel["foto"]["erro"])
        return rel
    finally:
        rel.update(pedidos=conta[0], fim=time.time())
        _ESTADO["completo"] = rel
        _TRAVA_LEITURA.release()


def ler_novos(app=None, *, ler=None) -> dict:
    """Os ativos criados depois do maior id do catálogo, somados a ele (`ativos_central.acrescentar`). Só com a leitura REST
    conferida (a paridade que valeu, de no máximo 30 h): sem ela, o REST não acrescenta nada. O novo cujo pai não se acha fica
    para a noite (`sem_pai`), e os novos demais também (`muitos`: o REST respondeu, não é falha); a página fora de ordem e o
    erro do cliente não acrescentam nada e são falhas do REST (`erro`, e a prontidão cai até a próxima leitura boa). Devolve
    o relatório (também em `estado()["novos"]`): é dele que sai o desfecho que a tela mostra."""
    rel = {"inicio": time.time(), "fim": None, "pedidos": 0, "novos": 0, "acrescentados": 0, "sem_pai": 0, "muitos": 0,
           "muitos_mais": False, "erro": "", "resultado": ""}
    conta = [0]
    try:
        if ativos_central.paridade_recente() is None:
            rel["erro"] = rel["resultado"] = "a leitura REST não está conferida (a paridade da noite): os novos não entram"
            return rel
        cat = ativos_central.atual()
        ids = [i for i in (cat.por_id if cat is not None else ()) if isinstance(i, int)]
        if not ids:
            rel["erro"] = rel["resultado"] = "sem catálogo: os novos não têm a que se somar"
            return rel
        if not _TRAVA_LEITURA.acquire(blocking=False):
            rel["erro"] = rel["resultado"] = "a leitura inteira da noite está em curso: os novos vêm com ela"
            return rel
        try:
            itens = ler_novos_rest(max(ids), ler=ler, conta=conta)
        except MuitosNovos as e:
            ativos_central.anotar_leitura_rest(True)
            rel.update(muitos=e.n, muitos_mais=not e.exato, resultado=str(e))
            return rel
        except Exception as e:                                       # noqa: BLE001 — fora de ordem, recusa, rede: nada entra
            ativos_central.anotar_leitura_rest(False, "os novos: " + _motivo(e))
            rel["erro"] = ("a página não veio do maior id para o menor (o REST ignorou a ordem)"
                           if isinstance(e, ForaDeOrdem) else _motivo(e))
            rel["resultado"] = "nada entrou: " + rel["erro"]
            log.warning("leitor de ativos: os novos: %s", rel["resultado"])
            return rel
        finally:
            _TRAVA_LEITURA.release()
        ativos_central.anotar_leitura_rest(True)
        lido_em = time.time()
        sem_pai: list = []
        registros = montar_registros(para_registro(itens, catalogo=cat, pais_do_catalogo=True, sem_pai=sem_pai))
        n = ativos_central.acrescentar(registros, "rest", lido_em=lido_em)      # sem novos, só a hora da conferência
        rel.update(novos=len(itens), acrescentados=n, sem_pai=len(sem_pai),
                   resultado="%d novo(s), %d somado(s) ao catálogo" % (len(itens), n)
                   + ("; %d sem o pai no catálogo, para a leitura da noite" % len(sem_pai) if sem_pai else ""))
    except Exception as e:                                           # noqa: BLE001 — o que sobrar não derruba ninguém
        rel["erro"] = _motivo(e)
        rel["resultado"] = "nada entrou: " + rel["erro"]
        log.exception("leitor de ativos: os novos quebraram")
    finally:
        rel.update(pedidos=conta[0], fim=time.time())
        _ESTADO["novos"] = rel
    return rel


# ── quem pede os novos: os botões e a aprovação ────────────────────────────────────────────────────────────────────────
def _rodar_novos() -> None:
    try:
        app = _APP["app"]
        if app is None:
            return
        with app.app_context():
            ler_novos(app)
    except Exception:                                               # noqa: BLE001
        log.exception("leitor de ativos: a leitura dos novos quebrou")
    finally:
        with _COND:
            _NOVOS.update(lendo=False, fim_em=time.time())
            _COND.notify_all()


def _comecar_novos() -> bool:
    """Marca a leitura dos novos como em curso, se não há uma e a última não é fresca. True se ESTE chamador deve rodá-la."""
    with _COND:
        if _NOVOS["lendo"] or time.time() - _NOVOS["fim_em"] < NOVOS_FRESCO_S:
            return False
        _NOVOS["lendo"] = True
        return True


def pedir_novos() -> bool:
    """Lê os novos POR TRÁS e volta na hora (os botões "Atualizar ativos"): uma leitura por vez, e a lida há menos de
    `NOVOS_FRESCO_S` serve (dez cliques seguidos são um pedido ao Fracttal, não dez)."""
    if _comecar_novos():
        threading.Thread(target=_rodar_novos, name="nexus-ativos-novos", daemon=True).start()
    return True


def _desfecho(terminou: bool) -> dict | None:
    """O desfecho da última leitura dos novos, para a tela: `terminou` (dentro da espera), `acrescentados`, `sem_pai`,
    `muitos` (ficam para a noite), `muitos_mais` (a leitura parou no teto e havia mais) e `erro` (o motivo curto, ou ""). Sem
    ter terminado, só isso: o resto ainda não se sabe. None se não há leitura de agora: a que terminou há mais de
    `DESFECHO_VALE_S` (revisão 2 da 2.2: o F5 da Fila com `?novos=1` e a espera da que está em curso sem nenhuma em curso
    diziam o desfecho de uma leitura antiga como se fosse de agora) ou nenhuma (o processo recém-subido): a tela não diz nada
    dos novos."""
    if not terminou:
        return {"terminou": False, "acrescentados": 0, "sem_pai": 0, "muitos": 0, "muitos_mais": False, "erro": ""}
    rel = _ESTADO.get("novos")
    if not rel or time.time() - float(rel.get("fim") or 0.0) > DESFECHO_VALE_S:
        return None
    return {"terminou": True, "acrescentados": int(rel.get("acrescentados") or 0), "sem_pai": int(rel.get("sem_pai") or 0),
            "muitos": int(rel.get("muitos") or 0), "muitos_mais": bool(rel.get("muitos_mais")),
            "erro": str(rel.get("erro") or "")}


def esperar_novos(teto: float, so_em_curso: bool = False) -> dict | None:
    """Espera a leitura dos novos até `teto` segundos: a que está em curso, ou (sem `so_em_curso`) uma nova se a última já não
    é fresca, e devolve o desfecho dela (`_desfecho`): `terminou` False se estourou (quem chama segue com o que há e a tela diz
    que a busca ainda não terminou); None se a última terminou há mais de `DESFECHO_VALE_S` (não é a de agora)."""
    fim = time.monotonic() + max(0.0, float(teto))
    if not so_em_curso:
        pedir_novos()
    with _COND:
        while _NOVOS["lendo"]:
            resta = fim - time.monotonic()
            if resta <= 0:
                return _desfecho(False)
            _COND.wait(resta)
    return _desfecho(True)


# ── o laço do servidor ─────────────────────────────────────────────────────────────────────────────────────────────────
def proximo_passo(agora: float) -> tuple:
    """(segundos, passo) do próximo compromisso: a leitura inteira às 02:15 de Brasília (`COMPLETO`) ou a dos novos às :08 e
    :38 das 06h às 22h (`NOVOS`). Estando no instante de um, o próximo é o da vez seguinte."""
    local = agora + _BRT_S                                            # o relógio de Brasília, contado como se fosse UTC
    dia0 = (local // 86400) * 86400
    cands = []
    for d in (0, 1):
        base = dia0 + d * 86400
        cands.append((base + HORA_COMPLETO[0] * 3600 + HORA_COMPLETO[1] * 60, COMPLETO))
        cands += [(base + h * 3600 + m * 60, NOVOS) for h in range(NOVOS_DAS, NOVOS_ATE) for m in NOVOS_MINUTOS]
    t, passo = min((t, p) for t, p in cands if t > local)
    return t - local, passo


def _laco() -> None:
    while True:
        espera, passo = proximo_passo(time.time())
        time.sleep(espera)
        app = _APP["app"]
        try:
            with app.app_context():
                if passo == COMPLETO:
                    rel = ler_completo(app, esperar_s=300)
                    log.info("leitor de ativos: a leitura da noite: %s (%d pedidos)", rel["resultado"], rel["pedidos"])
                elif _comecar_novos():
                    _rodar_novos()
        except Exception:                                           # noqa: BLE001 — o leitor nunca derruba o Nexus
            log.exception("leitor de ativos: o passo %s quebrou", passo)


def ligar(app) -> None:
    """Liga o leitor neste app (SÓ o `servir.py`, o servidor): diz ao catálogo onde mora a cópia dele em disco e de onde ler a
    foto (`ponte.ligar_catalogo_de_ativos`, o mesmo que a criação do clone faz), registra o leitor no catálogo central e abre
    o laço (fora dos testes). Sem a credencial REST do Fracttal, não liga: o estado diz por quê, e o catálogo segue pelo RPC,
    com a sessão de quem usa. Ligar de novo no mesmo app não faz nada."""
    if CHAVE in app.extensions:
        return
    app.extensions[CHAVE] = _ESTADO
    try:
        from nexus.torres.oscreator import ponte
        ponte.ligar_catalogo_de_ativos(app)
    except Exception:                                               # noqa: BLE001 — sem a pasta, o catálogo vive na memória
        log.exception("leitor de ativos: o catálogo não foi ligado à pasta de dados nem ao banco")
    from nexus.pcm.geracao import credencial
    cred = credencial(app.config)
    if not cred.ok:
        _ESTADO.update(ligado=False, motivo="sem a credencial REST do Fracttal (FRACTTAL_CLIENT_ID e FRACTTAL_CLIENT_SECRET): "
                                            "o catálogo de ativos segue pelo RPC, com a sessão de quem usa")
        ativos_central.ligar_leitor(estado=estado)
        log.warning("leitor de ativos: %s", _ESTADO["motivo"])
        return
    _APP["app"] = app
    _ESTADO.update(ligado=True, motivo="", credencial=cred.onde)
    ativos_central.ligar_leitor(pedir_novos=pedir_novos, esperar_novos=esperar_novos, estado=estado)
    if not app.config.get("TESTING"):
        threading.Thread(target=_laco, name="nexus-ativos-leitor", daemon=True).start()


def estado() -> dict:
    """O que o leitor fez, para o Raio-X (`ativos_central.estado()["leitor"]`): se está ligado (e por quê não), a última
    leitura inteira e a última dos novos (pedidos, quantos itens, o resultado), quantas descrições o detector de endereço
    cortou na última foto renovada (`descricao_cortada`: o número e até 5 ids) e se há uma leitura dos novos em curso."""
    with _COND:
        novos = dict(_NOVOS)
    return dict(_ESTADO, lendo_novos=novos["lendo"], novos_fim_em=novos["fim_em"])


def reiniciar() -> None:
    """Volta ao processo recém-subido (os testes): sem app, sem leituras, o estado limpo."""
    _APP["app"] = None
    _ESTADO.clear()
    _ESTADO.update(_estado_limpo())
    with _COND:
        _NOVOS.update(lendo=False, fim_em=0.0)
