"""ativos_leitor.py: os ativos do Fracttal lidos pelo PRÓPRIO servidor, pela credencial da empresa (31/10/2026, etapa 2 do
canto central; desenho `docs/superpowers/specs/2026-10-30-oscreator-canto-central-design.md`, "Etapa 2").

Até aqui o catálogo de ativos do OS Creator só se renovava pelo RPC (`api.get_assets`), com a sessão da 1ª pessoa que o achava
vencido: ~110 pedidos de 200 ativos, e o botão "Atualizar ativos" fazia a pessoa esperar minutos. Agora:
- DE MADRUGADA (02:15 de Brasília, `ler_completo`): o REST `items` inteiro, 100 por página e 1 pedido por segundo (~270
  pedidos, ~5 min, longe do campo e da cota da empresa: 200 por minuto, dividida com o App de Campo). A leitura que não chega ao
  total que o Fracttal informa não troca nada (`LeituraIncompleta`). A que chega é CONFERIDA contra o catálogo de agora
  (`conferir_paridade`: na 1ª noite ele é o do RPC, e a conferência é REST x RPC de verdade; depois, a leitura anterior) e só
  então vai ao catálogo (`ativos_central.trocar`, que ainda recusa a que encolhe) e, aceita, à foto do banco
  (`nexus/dados/foto_ativos.py`; uma guarda só).
- DE DIA, SÓ OS NOVOS (de 30 em 30 min, das 06:08 às 21:38, `ler_novos`): ordenados do maior id para o menor, até uma página
  inteira de ids que o catálogo já tem (1 pedido sem novidade, 2 com). Somam-se ao catálogo (`ativos_central.acrescentar`),
  sem mexer no `lido_em` da lista inteira. Os três botões "Atualizar ativos" e a aprovação da Fila pedem esta leitura
  (`pedir_novos`, `esperar_novos`), por trás.
- A PARIDADE QUE FALHOU (ou que ainda não houve) deixa tudo como era: o REST não troca nem soma nada, o motivo fica no estado,
  o catálogo vence nas 24 h de sempre e a 1ª sessão do dia o renova pelo RPC (o renovador de antes, uma vez por dia, para
  todos). A sondagem que o desenho pedia (o REST dá os mesmos campos do RPC?) não pôde ser feita antes de construir: é esta
  conferência, toda noite, que a faz.

Só o `servir.py` liga (`ligar`); o `app.py` (o PC) e os testes seguem sem ele, como o `nexus/casca/teto_os.py`. Sem a
credencial REST (o PC, a worktree sem `FRACTTAL_CLIENT_ID`) ele não liga, o estado diz por quê, e nada quebra.

O cliente HTTP e o ritmo são os que já existem (`nexus/campo/fracttal.py`, como `nexus/engenharia/os_falhas.py` pagina): 1 s
entre as páginas; o 406/429 o próprio cliente espera (5 s e 10 s) e, se ele desistir, este espera o castigo de 1 min do
Fracttal (medido em 19/08 no robô do PCM) e tenta a mesma página de novo, duas vezes. Os campos do `items` que se guardam
(`CAMPOS_REST`) são os do registro do RPC: o REST não foi sondado antes de construir (31/10/2026), e o que faltar aparece na
conferência da 1ª noite, que então falha e diz o campo.
"""
from __future__ import annotations

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
PAGINAS_NOVOS_MAX = 5            # mais de 400 ativos novos num dia: ficam para a leitura da noite
# os campos do `items` que o catálogo usa (os do registro do RPC, `inventories.items_list`); o resto do item (coordenadas,
# campos livres) sai assim que a página chega: são ~27 mil itens, e o servidor já anda apertado de memória
CAMPOS_REST = ("id", "code", "description", "id_parent", "parent_description", "id_type_item", "id_group_task")
OBRIGATORIOS = ("id", "id_parent", "id_type_item")       # sem eles a criação de OS e o drill-down da tela de Ativos quebram
PARIDADE_MIN_PCT = 99.0          # dos códigos em comum, os que dão o mesmo cliente e usina
CAMPOS_MIN_PCT = 99.0            # dos registros, os que têm os campos obrigatórios
COBERTURA_MIN_PCT = 95.0         # dos códigos de cada lado, os que o outro também tem
HORA_COMPLETO = (2, 15)          # a leitura inteira, em Brasília: longe dos laços de hora em hora (:10 a :50) e do campo
NOVOS_DAS, NOVOS_ATE = 6, 22     # os novos, de 30 em 30 min, das 06h às 22h
NOVOS_MINUTOS = (8, 38)          # fora dos minutos ocupados (tarefas :10 a :20, normalizações :22, App :25, carga :40...)
NOVOS_FRESCO_S = 60              # os novos lidos há menos disto servem a quem pede (botão, aprovação): não se lê de novo
COMPLETO, NOVOS = "completo", "novos"
CHAVE = "oscreator_ativos_leitor"
_BRT_S = -3 * 3600               # Brasília é UTC-3 fixo

_dormir = time.sleep             # os testes trocam (o ritmo e as esperas da recusa sem esperar de verdade)
_TRAVA_LEITURA = threading.Lock()                # uma leitura do Fracttal por vez daqui: a inteira ou a dos novos
_COND = threading.Condition()                    # quem espera os novos (a aprovação, o "?novos=1" das telas)
_NOVOS: dict = {"lendo": False, "fim_em": 0.0}
_APP: dict = {"app": None}


def _estado_limpo() -> dict:
    return {"ligado": False, "motivo": "não ligado (só o servir.py liga o leitor)", "credencial": None,
            "completo": None, "novos": None}


_ESTADO: dict = _estado_limpo()


class LeituraIncompleta(RuntimeError):
    """A leitura inteira não chegou ao total que o Fracttal informou (página curta, itens a menos): não troca nada."""


class ForaDeOrdem(RuntimeError):
    """A página dos novos não veio do maior id para o menor (o `sort` ignorado): não se acrescenta nada."""


class MuitosNovos(RuntimeError):
    """Mais novos do que `PAGINAS_NOVOS_MAX` páginas: ficam para a leitura da noite."""


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


def _pedir(ler, path: str, conta: list):
    """Um pedido, com a 2ª chance depois da recusa: o cliente já esperou 5 s e 10 s no 406/429; aqui, o castigo de 1 min."""
    from nexus.campo import fracttal
    for tentativa in range(len(ESPERAS_RECUSA_S) + 1):
        conta[0] += 1
        try:
            return ler(path)
        except (fracttal.Recusado, requests.RequestException) as e:
            if tentativa >= len(ESPERAS_RECUSA_S):
                raise
            log.warning("leitor de ativos: o Fracttal recusou %s (%s); espero %d s e tento de novo", path.split("?")[0],
                        str(e)[:120], ESPERAS_RECUSA_S[tentativa])
            _dormir(ESPERAS_RECUSA_S[tentativa])


def _ler_padrao(ler):
    if ler is not None:
        return ler
    from nexus.campo import fracttal
    return fracttal.ler


# ── as duas leituras ───────────────────────────────────────────────────────────────────────────────────────────────────
def ler_todos_rest(ler=None, conta: list | None = None) -> list[dict]:
    """Todos os itens do Fracttal pelo REST `items`: 100 por página, 1 pedido por segundo, até o `total` que a 1ª página
    informa (sem total: até a página com menos de 100). Repetido entre páginas conta uma vez (pelo id). Levanta
    `LeituraIncompleta` se uma página vem curta antes do total, se os itens distintos não chegam a ele, ou se não veio nada:
    leitura incompleta não troca o que existe. Só os `CAMPOS_REST` de cada item ficam."""
    ler = _ler_padrao(ler)
    conta = conta if conta is not None else [0]
    por_id: dict = {}
    inicio, total = 0, None
    for n in range(PAGINAS_MAX):
        if n:
            _dormir(PAUSA_S)
        r = _pedir(ler, "items?limit=%d&start=%d" % (POR_PAGINA, inicio), conta)
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
    raise MuitosNovos("mais de %d ativos novos desde o último catálogo: ficam para a leitura da noite"
                      % (PAGINAS_NOVOS_MAX * POR_PAGINA))


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


def conferir_paridade(registros, referencia_por_codigo, *, primeira: bool = False) -> tuple[bool, str, float]:
    """(vale, motivo, % dos códigos em comum com o mesmo cliente e usina). A leitura REST vale contra o catálogo de agora
    (`ativos_central.atual().por_codigo`) se:
    - dos códigos em comum, >= 99% dão o mesmo cliente e a mesma usina;
    - >= 99% dos registros têm os campos obrigatórios (`OBRIGATORIOS`: id, id_parent, id_type_item);
    - >= 95% dos códigos da leitura estão no catálogo (o REST que trouxesse o que o RPC não traz, como os inativos, não vale só
      porque os em comum batem);
    - na `primeira` conferência (o REST ainda não valeu nenhuma vez, ou a última falhou: é a sondagem REST x RPC), também
      >= 95% dos códigos do catálogo na leitura. Depois dela, a leitura que encolhe passa daqui e vai ao `ativos_central.trocar`,
      que a recusa e só a aceita confirmada por duas leituras (o encolhimento de verdade); na primeira, um REST que desse
      sempre um pedaço do Fracttal seria confirmado por ele mesmo na noite seguinte, e a lista pela metade iria para a tela.
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
    n_ref = len({id(r) for r in ref.values()})
    comuns = [c for c in por_codigo if c in ref]
    if not comuns:
        return False, "nenhum código da leitura está no catálogo de agora", 0.0
    iguais = sum(1 for c in comuns if (por_codigo[c].get("cliente"), por_codigo[c].get("usina"))
                 == (ref[c].get("cliente"), ref[c].get("usina")))
    pct = round(100.0 * iguais / len(comuns), 2)
    cob_ref, cob_rest = 100.0 * len(comuns) / max(n_ref, 1), 100.0 * len(comuns) / len(por_codigo)
    problemas = []
    if pct < PARIDADE_MIN_PCT:
        problemas.append("só %.2f%% dos %d códigos em comum dão o mesmo cliente e usina (o mínimo é %.0f%%)"
                         % (pct, len(comuns), PARIDADE_MIN_PCT))
    if pct_campos < CAMPOS_MIN_PCT:
        problemas.append("faltam campos obrigatórios em %d de %d ativos (%s)" % (
            sem, len(registros), ", ".join("%s: %d" % kv for kv in sorted(faltam.items()))))
    if primeira and cob_ref < COBERTURA_MIN_PCT:
        problemas.append("na 1ª conferência, a leitura não tem %d dos %d códigos do catálogo" % (n_ref - len(comuns), n_ref))
    if cob_rest < COBERTURA_MIN_PCT:
        problemas.append("a leitura traz %d códigos que o catálogo não tem, de %d" % (len(por_codigo) - len(comuns),
                                                                                       len(por_codigo)))
    if problemas:
        return False, "; ".join(problemas), pct
    return True, ("%d códigos em comum, %.2f%% com o mesmo cliente e usina; os campos obrigatórios em %.2f%% dos ativos"
                  % (len(comuns), pct, pct_campos)), pct


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


def ler_completo(app, *, ler=None, esperar_s: float = 0) -> dict:
    """A leitura da noite: o Fracttal inteiro pelo REST, a conferência contra o catálogo de agora, a troca do catálogo e, se
    ela entrou, a foto do banco renovada. Cada passo que não dá deixa o de antes e diz no estado (`estado()["completo"]`).
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
            rel["resultado"] = "a leitura não veio inteira (%s: %s): nada mudou" % (type(e).__name__, str(e)[:160])
            log.warning("leitor de ativos: %s", rel["resultado"])
            return rel
        lido_em = time.time()
        rel["itens"] = len(itens)
        banco = _banco(app)
        antigas, de_11_10 = None, False
        if banco is not None:
            try:
                from nexus.dados import foto_ativos
                antigas, de_11_10 = foto_ativos.ler(banco[0], banco[2])
            except Exception as e:                                   # noqa: BLE001 — o catálogo anda; a foto, não
                rel["foto"] = {"erro": "não li a foto do banco (%s: %s)" % (type(e).__name__, str(e)[:160])}
        ref = ativos_central.atual()
        sem_pai: list = []
        cru = para_registro(itens, catalogo=ref, foto=antigas, sem_pai=sem_pai)
        # cada passo larga o que já serviu: tudo junto, o pico da noite media ~72 MB, num servidor já apertado de memória
        del itens
        registros = montar_registros(cru)
        fora_do_catalogo = [c for c in cru if not c["parent_description"]]    # as raízes e os sem pai: a foto os guarda
        del cru
        rel.update(registros=len(registros), sem_pai=len(sem_pai))
        primeira = not (ativos_central.paridade_rest() or {}).get("vale")
        vale, motivo, pct = conferir_paridade(registros, ref.por_codigo if ref is not None else {}, primeira=primeira)
        ativos_central.anotar_paridade_rest({
            "vale": vale, "motivo": motivo, "pct": pct, "em": time.time(), "lido_em": lido_em, "n": len(registros),
            "primeira": primeira,
            "contra": ref.fonte if ref is not None else None, "contra_lido_em": ref.lido_em if ref is not None else None})
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
        # acabou de entrar (os mesmos itens, com o tipo) e das raízes e dos sem pai, que ele não tem
        if banco is None:
            rel["foto"] = {"erro": "teste sem banco"}
        elif antigas is not None:
            from nexus.dados import foto_ativos
            novas = [foto_ativos.linha_do_item(r, r.get("tipo_code")) for r in cat.lista]
            novas += [foto_ativos.linha_do_item(c) for c in fora_do_catalogo]
            try:
                rel["foto"] = foto_ativos.gravar(novas, base=banco[0], token=banco[1], sessao=banco[2],
                                                 maquina="servidor" if os.name != "nt" else "pc", antigas=antigas,
                                                 de_11_10=de_11_10)
            except Exception as e:                                   # noqa: BLE001 — recusada, curta, banco fora: fica a de antes
                rel["foto"] = {"erro": "%s: %s" % (type(e).__name__, str(e)[:200])}
                log.warning("leitor de ativos: a foto do banco não foi renovada (%s)", rel["foto"]["erro"])
        return rel
    finally:
        rel.update(pedidos=conta[0], fim=time.time())
        _ESTADO["completo"] = rel
        _TRAVA_LEITURA.release()


def _rest_conferido() -> bool:
    p = ativos_central.paridade_rest()
    return bool(p and p.get("vale"))


def ler_novos(app=None, *, ler=None) -> dict:
    """Os ativos criados depois do maior id do catálogo, somados a ele (`ativos_central.acrescentar`). Só com a leitura REST
    conferida (a paridade da última noite valeu): sem ela, o REST não acrescenta nada. O novo cujo pai não se acha fica para a
    noite; a página fora de ordem não acrescenta nada. Devolve o relatório (também em `estado()["novos"]`)."""
    rel = {"inicio": time.time(), "pedidos": 0, "novos": 0, "acrescentados": 0, "sem_pai": 0, "resultado": ""}
    conta = [0]
    try:
        if not _rest_conferido():
            rel["resultado"] = "a leitura REST não está conferida (paridade): os novos não entram"
            return rel
        cat = ativos_central.atual()
        ids = [i for i in (cat.por_id if cat is not None else ()) if isinstance(i, int)]
        if not ids:
            rel["resultado"] = "sem catálogo: os novos não têm a que se somar"
            return rel
        if not _TRAVA_LEITURA.acquire(blocking=False):
            rel["resultado"] = "a leitura inteira está em curso: os novos vêm com ela"
            return rel
        try:
            itens = ler_novos_rest(max(ids), ler=ler, conta=conta)
            lido_em = time.time()
            sem_pai: list = []
            registros = montar_registros(para_registro(itens, catalogo=cat, pais_do_catalogo=True, sem_pai=sem_pai))
            n = ativos_central.acrescentar(registros, "rest", lido_em=lido_em)      # sem novos, só a hora da conferência
            rel.update(novos=len(itens), acrescentados=n, sem_pai=len(sem_pai),
                       resultado="%d novo(s), %d somado(s) ao catálogo" % (len(itens), n)
                       + ("; %d sem o pai no catálogo, para a leitura da noite" % len(sem_pai) if sem_pai else ""))
        finally:
            _TRAVA_LEITURA.release()
    except Exception as e:                                           # noqa: BLE001 — fora de ordem, recusa, rede: nada entra
        rel["resultado"] = "nada entrou (%s: %s)" % (type(e).__name__, str(e)[:160])
        log.warning("leitor de ativos: os novos: %s", rel["resultado"])
    finally:
        rel["pedidos"] = conta[0]
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


def esperar_novos(teto: float, so_em_curso: bool = False) -> bool:
    """Espera a leitura dos novos até `teto` segundos: a que está em curso, ou (sem `so_em_curso`) uma nova se a última já não
    é fresca. True se terminou dentro do teto (ou nem precisou); False se estourou (segue com o que há)."""
    fim = time.monotonic() + max(0.0, float(teto))
    if not so_em_curso:
        pedir_novos()
    with _COND:
        while _NOVOS["lendo"]:
            resta = fim - time.monotonic()
            if resta <= 0:
                return False
            _COND.wait(resta)
    return True


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
    leitura inteira e a última dos novos (pedidos, quantos itens, o resultado) e se há uma leitura dos novos em curso."""
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
