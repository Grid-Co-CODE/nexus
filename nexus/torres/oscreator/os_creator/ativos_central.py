"""ativos_central.py: o catálogo de ativos do OS Creator, UM para todas as telas (etapa 2 do canto central, 31/10/2026).

Levi, 30/10/2026: "para abrir uma solicitação precisamos de ativos, para criar OS é preciso carregar os ativos, para abrir o
histórico acabamos vendo os ativos [...] a ideia é não ter um carregamento novo por atividade e sim um ecossistema onde as
coisas se aproveitam e não precisamos ficar fazendo novas requisições sempre!" (desenho:
`docs/superpowers/specs/2026-10-30-oscreator-canto-central-design.md`).

O QUE HAVIA ANTES: três caminhos sobre o mesmo `assets_cache.json`, cada um com a sua cópia ou o seu índice. O
`load_assets_cached` copiava a lista inteira (~26 mil dicionários, uns 12 MB de lixo) a CADA chamada, para quem pediu poder
mexer à vontade; o `rotas_solic._indice_ativos` tinha o índice e o renovador dele; o `_code_loc` era montado uma vez por
processo e nunca refeito (um ativo novo não aparecia no nome das OS até o próximo reinício); e o `_asset_by_code`
percorria uma cópia nova por código. Cada push na `main` (uns 10 por dia útil) reinicia o serviço e apaga tudo isso.

COMO É AGORA:
- Um `Catalogo` por versão, PRONTO e IMUTÁVEL: a lista (ordenada por cliente, usina e código), os índices por id, por código,
  por cliente e por cliente + usina, o mapa código -> (cliente, usina curta, tipo) e a contagem por tipo, tudo montado UMA vez
  quando a versão chega. Troca-se o objeto inteiro (`trocar`), nunca um pedaço: quem está lendo a versão de antes termina com
  ela, e quem chega depois lê a nova.
- Os registros não aceitam escrita (`Registro` levanta TypeError). Eles são compartilhados por todas as telas e por todas as
  pessoas: um chamador que mexesse num deles mudaria o ativo para todo mundo até a próxima troca, e sem erro nenhum. Quem
  precisa mexer pede a cópia (`registro(codigo)` ou `dict(r)`).
- O boot NUNCA pergunta ao Fracttal. Em ordem: (1) a cópia desta tabela em disco, `<pasta>/ativos.json.gz` (gravada ao lado,
  de uma vez só, com o formato escrito dentro; a ilegível ou de outro formato é ignorada); (2) o `assets_cache.json` antigo,
  lido UMA vez como migração se a cópia nova não existe (e já grava a nova); (3) a foto dos ativos no banco
  (`nexus_ativos_fracttal · foto_ativos`), se o Nexus ligou uma função que a lê (`ligar_fonte_do_banco`; este módulo não
  conhece a configuração do banco). Sem nenhuma das três, o catálogo nasce do primeiro download (`trocar(..., "rpc")`).
- A troca recusa a lista vazia, a que encolhe mais de 5% (`ENCOLHE_MAX`) contra a de agora e a leitura mais velha que o
  catálogo de agora com conteúdo diferente: o download do RPC pelas páginas perde 200 ativos em silêncio quando uma página vem
  sem lista, e "número pela metade não vai para a tela". O motivo da última recusa fica em `estado()`.
- A RECUSA É LEMBRADA (revisão 1 da tarefa 2.1): a leitura completa que o Fracttal deu e o catálogo recusou (a que encolheu)
  também foi uma ida ao Fracttal, de ~110 pedidos. `conferido_em(cat)` é o mais novo entre o `lido_em` do catálogo e essa
  leitura, e é por ele que o `api` decide se o catálogo venceu: sem isso, passadas as 24 h, cada aprovação da Fila baixava tudo
  de novo (minutos na frente de quem aprovava) e o download por trás repetia de 10 em 10 min, com o mesmo resultado.
- Cada versão tem um sha das linhas ordenadas (`versao`), calculado ANTES de montar qualquer coisa: a mesma lista lida de novo
  (o caso comum da renovação diária) não monta nada, só renova o `lido_em`.

O FRESCOR (`lido_em`, quando a lista foi conferida com a fonte) é decidido por quem usa: o `api.load_assets_cached` serve o
que há e renova por trás o que passou de 24 h. Este módulo só guarda e entrega.

A FOTO DO BANCO COMO CATÁLOGO (a 3ª fonte) tem um limite real, medido em 31/10/2026 na foto de 22/09: ela foi carregada do
`assets_cache.json`, que já tinha jogado fora a raiz de cada cliente (o item sem pai, que o `montar_registros` ignora), então
nenhuma linha dela chega à raiz pela cadeia de pais, e o nome do cliente (o 1º trecho do `parent_description`) só existe na
raiz. Tirar o cliente do prefixo do nome da usina acerta 74% dos ativos (128 das 189 usinas com equipamento) e erra 6 dos 16
clientes (a carteira com outro nome); e o "Almoxarifado" e o "TESTE - PA" (`CLIENTES_OCULTOS`) deixariam de ser reconhecidos e
apareceriam nas cascatas com nomes inventados. Por isso `registros_da_foto` RECUSA a foto cujas linhas não chegam à raiz
(`FotoIncompleta`): a fonte fica ligada, o motivo aparece em `estado()["banco"]`, e ela passa a servir sozinha quando a foto
vier com a raiz (a renovação pela leitura do Fracttal, etapa 2.2 do mesmo plano).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
import unicodedata
import zlib
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from types import MappingProxyType

# O pacote `chamado_garantia` mora ao lado desta pasta (é compartilhado com o app de campo). O api.py faz o mesmo: APPEND,
# nunca insert(0), para a raiz não vencer o `app.py` do próprio OS Creator.
_RAIZ_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ_REPO not in sys.path:
    sys.path.append(_RAIZ_REPO)
from chamado_garantia.ativos import tipo_e_sufixo  # noqa: E402

log = logging.getLogger("oscreator.ativos_central")

FORMATO = 1                     # o formato do arquivo em disco; outro número = arquivo de outra versão do código, ignorado
FORMATO_LEGADO = 2              # o "ver" do assets_cache.json antigo (v2 = + id_parent/id_type_item/id_group_task)
NOME_ARQUIVO = "ativos.json.gz"
FONTES = ("banco", "rest", "rpc", "disco")
ENCOLHE_MAX = 5                 # % que a lista nova pode ser menor que a de agora; mais que isto, a troca é recusada
ESPERA_BANCO_S = 600            # a foto do banco que falhou ou veio incompleta só é lida de novo depois disto
REGRAVAR_DISCO_S = 3600         # a mesma lista lida de novo regrava o disco (o `lido_em` dele não fica para trás) a cada hora
ORFAOS_MAX_PCT = 1.0            # % das linhas da foto que podem apontar para um pai ausente (dado torto) sem recusar a foto
_BRT = timezone(timedelta(hours=-3))

# Os campos de texto que se repetem em milhares de registros (17 clientes, ~190 usinas, ~60 tipos): uma string só para cada
# valor, em vez de uma por registro (o JSON decodificado deixa uma por registro; medido: ~7 dos 33 MB do catálogo)
_CAMPOS_REPETIDOS = ("cliente", "usina", "tipo_code", "tipo", "parent_description")


# ── o que é um registro do catálogo (movido do api.py: é a definição do formato) ───────────────────────────────────────
def _tipo_from_code(code: str, eh_usina: bool):
    """→ (tipo_code, tipo_label). Para o item da usina (sem hierarquia abaixo) → ('','Usina')."""
    if eh_usina:
        return "", "Usina"
    return tipo_e_sufixo(code)


def _clean_usina_desc(desc: str) -> str:
    """Nome de usina a partir da descrição do item-usina, sem o '{ CODE }' do final."""
    return (desc.split("{")[0]).strip() or desc


def montar_registros(raw: list) -> list:
    """Deriva cliente/usina/tipo de cada ativo (2 passadas) — evita a usina duplicada.
    - Equipamento (parent com ≥2 níveis): usina = 2º nível do parent (nome LIMPO, sem code); tipo pelo code.
    - Item da própria usina (parent só com o cliente; o code aparece no nome): NÃO vira usina duplicada —
      entra como ATIVO de tipo 'Usina', anexado à usina limpa (mapa code-base→usina dos equipamentos).
    - Raiz da organização (sem parent): ignorado no drill-down.
    Era o `api._build_records` (o api mantém o nome como apelido)."""
    parsed, base2usina = [], {}
    for a in raw:
        code = (a.get("code") or "").strip()
        desc = (a.get("description") or "").strip()
        segs = [s.strip() for s in (a.get("parent_description") or "").split("/") if s.strip()]
        parsed.append((a, code, desc, segs))
        if len(segs) >= 2 and code:                       # equipamento → registra a usina limpa do code-base
            cparts = code.split("-")
            base = cparts[-2] if len(cparts) >= 2 else cparts[0]   # penúltimo seg = code-base (CGH100/TIM200)
            if base and segs[1]:
                base2usina.setdefault(base, segs[1])
    out = []
    for a, code, desc, segs in parsed:
        if len(segs) >= 2:                                # equipamento
            cliente, usina = segs[0], segs[1]
            tipo_code, tipo = _tipo_from_code(code, eh_usina=False)
        elif len(segs) == 1:                              # item da usina (code no nome) → tipo 'Usina'
            cliente = segs[0]
            base = code.split("-")[-1] if "-" in code else code      # ATHN-TIM200 → TIM200
            usina = base2usina.get(base) or _clean_usina_desc(desc)
            tipo_code, tipo = "USINA", "Usina"
        else:                                             # raiz da organização → fora do drill-down
            continue
        out.append({"id": a.get("id"), "code": code, "description": desc,
                    "id_parent": a.get("id_parent"), "id_type_item": a.get("id_type_item"),
                    "id_group_task": a.get("id_group_task"),
                    "parent_description": a.get("parent_description"),
                    "cliente": cliente, "usina": usina, "tipo_code": tipo_code, "tipo": tipo,
                    "label": f"{code} — {desc}" if code else desc})
    out.sort(key=lambda x: (x["cliente"].lower(), x["usina"].lower(), x["code"].lower()))
    return out


def usina_curta(usina_full: str) -> str:
    """'Thopen - Ceilândia 1 - DF' (Cliente - Usina - Estado) → 'Ceilândia 1'. Era o `api._usina_curta`."""
    parts = [p.strip() for p in str(usina_full).split(" - ") if p.strip()]
    if len(parts) <= 1:
        return usina_full
    parts = parts[1:]                                          # tira o cliente (1º)
    if len(parts) > 1 and len(parts[-1]) == 2 and parts[-1].isalpha():
        parts = parts[:-1]                                     # tira a sigla do estado (último)
    return " - ".join(parts)


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def corrigir_itens_usina_estrangeiros(assets: list) -> list:
    """Conserta o item-usina PENDURADO NA PLANTA ERRADA (cadastro do Fracttal, 28/07). Muda os dicionários que recebe: quem
    chama passa cópias (o `trocar` passa).

    Caso real: o item-usina de "Thopen - Ipixuna 1 e 2 - PA" (THPN-IPX100) está registrado como filho da planta "2C - Ipixuna
    do Pará 1 - PA" — então o campo `usina` dele apontava para a planta da 2C e ele aparecia nas cascatas dela (COS/
    Performance/Nova análise), como o Levi reportou. Medido no catálogo inteiro: 7 itens nessa situação (esse + 6 lixos de
    TESTE pendurados em Sarandi), de 16,9 mil.

    Detecção: item tipo "Usina" cuja DESCRIÇÃO não começa com a própria `usina` — a descrição do item-usina legítimo sempre
    embute o rótulo da planta. Correção: realoca para a usina dos IRMÃOS DE CÓDIGO (THPN-IPX100 → usina dos THPN-IPX100-*);
    sem irmão, `usina` fica vazia e o item sai das cascatas (melhor sumir do que aparecer na planta errada). Roda quando a
    versão chega (era a cada leitura do catálogo), então vale para a cópia antiga sem forçar recarga de 26 mil ativos."""
    ruins = [a for a in assets
             if a.get("tipo") == "Usina" and a.get("usina") and a.get("description")
             and not _norm(a["description"]).startswith(_norm(a["usina"]))]
    if not ruins:
        return assets
    for a in ruins:
        code = str(a.get("code") or "")
        irmaos = [x.get("usina") for x in assets
                  if x.get("usina") and str(x.get("code") or "").startswith(code + "-")]
        if irmaos:
            a["usina"] = max(set(irmaos), key=irmaos.count)
            cli = [x.get("cliente") for x in assets
                   if x.get("usina") == a["usina"] and x.get("cliente")]
            if cli:
                a["cliente"] = max(set(cli), key=cli.count)
        else:
            a["usina"] = ""
    return assets


# ── o registro (só leitura) e a versão (imutável) ──────────────────────────────────────────────────────────────────────
class Registro(dict):
    """Um ativo do catálogo. É um dicionário de verdade (isinstance, .get, json, Jinja, `dict(r)` e `{**r}` funcionam), mas
    NÃO aceita escrita: ele é o MESMO objeto para todas as telas e todas as pessoas. A auditoria de 31/10/2026 em todos os
    chamadores (README do OS Creator, "O catálogo de ativos central") não achou nenhum que mexa num registro; este guarda é
    para o próximo que mexer não corromper o ativo de todo mundo em silêncio. A cópia mutável é `registro(codigo)` ou
    `dict(r)`."""
    __slots__ = ()

    def _so_leitura(self, *args, **kwargs):
        raise TypeError("o registro do catálogo de ativos é só de leitura (é o mesmo para todas as telas): "
                        "use ativos_central.registro(codigo) ou dict(r) para uma cópia")

    __setitem__ = __delitem__ = update = pop = popitem = clear = setdefault = __ior__ = _so_leitura

    def copy(self) -> dict:
        return dict(self)

    def __reduce__(self):
        return (dict, (dict(self),))                  # copy.copy, deepcopy e pickle devolvem o dicionário comum


@dataclass(frozen=True, slots=True, eq=False)
class Catalogo:
    """Uma versão do catálogo: pronta, imutável e compartilhada. `lista` é uma tupla de `Registro` (ordenada por cliente,
    usina e código, como o `montar_registros` sempre deixou); os índices guardam os MESMOS registros (nada é copiado):
    `por_id` e `por_codigo` (o 1º de cada), `por_cliente` e `por_cliente_usina` (tuplas na ordem da lista),
    `local_por_codigo` ({código: (cliente, usina curta, tipo)}, o antigo `api._code_loc`) e `tipos` ([(tipo, n)] do mais
    comum ao menos); `n_com_codigo` é quantos registros têm código, os repetidos inclusive (a conta da tela de Ativos e da
    inicial; `len(por_codigo)` são os códigos distintos). `versao` é o sha das linhas ordenadas; `lido_em`, quando a lista foi
    conferida com a fonte dela; `fonte`, de onde veio (banco, rest, rpc ou disco)."""
    lista: tuple
    por_id: Mapping
    por_codigo: Mapping
    por_cliente: Mapping
    por_cliente_usina: Mapping
    local_por_codigo: Mapping
    tipos: tuple
    n_com_codigo: int
    versao: str
    lido_em: float
    fonte: str


def _ordem(r) -> tuple:
    return (str(r.get("cliente") or "").lower(), str(r.get("usina") or "").lower(), str(r.get("code") or "").lower())


def _preparar(registros) -> list:
    """Cópias planas dos registros, com o item-usina da planta errada consertado: é daqui que saem a versão (o sha) e o
    catálogo. O que o chamador passou não é tocado."""
    copias = [dict(r) for r in registros if isinstance(r, dict)]
    corrigir_itens_usina_estrangeiros(copias)
    return copias


def _versao(copias) -> str:
    """O sha das linhas ordenadas: a mesma lista, em qualquer ordem e vinda de qualquer fonte, dá a mesma versão. Cada linha
    entra pelo próprio sha (guardar as ~26 mil linhas em texto para ordená-las eram uns 12 MB só para somar)."""
    h = hashlib.sha256()
    for d in sorted(hashlib.sha256(json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                                              default=str).encode("utf-8")).digest() for r in copias):
        h.update(d)
    return h.hexdigest()


def _indexar(copias, versao: str, fonte: str, lido_em: float) -> Catalogo:
    """O catálogo pronto a partir das cópias já consertadas: na ordem do catálogo, uma string só para cada cliente, usina,
    tipo e caminho, cada registro só de leitura e os índices. CONSOME a lista que recebe (cada cópia vira `Registro` no lugar
    dela, para as duas não existirem juntas)."""
    copias.sort(key=_ordem)
    pool: dict = {}
    for i, r in enumerate(copias):
        for campo in _CAMPOS_REPETIDOS:
            v = r.get(campo)
            if isinstance(v, str):
                r[campo] = pool.setdefault(v, v)
        copias[i] = Registro(r)
    lista = copias
    por_id, por_codigo, local = {}, {}, {}
    por_cliente: dict = {}
    por_cu: dict = {}
    n_tipo: Counter = Counter()
    n_com_codigo = 0
    curta: dict = {}
    for r in lista:
        i = r.get("id")
        if i is not None:
            por_id.setdefault(i, r)
        code = r.get("code")
        cli, usi, tipo = r.get("cliente"), r.get("usina"), r.get("tipo")
        por_cliente.setdefault(cli, []).append(r)
        por_cu.setdefault((cli, usi), []).append(r)
        if tipo:
            n_tipo[tipo] += 1
        if code:
            n_com_codigo += 1
            por_codigo.setdefault(code, r)
            if isinstance(code, str) and code != code.strip():       # o pedido costuma vir aparado
                por_codigo.setdefault(code.strip(), r)
            u = usi or ""
            if u not in curta:
                curta[u] = usina_curta(u)
            local.setdefault(code, (cli or "", curta[u], tipo or ""))
    return Catalogo(
        lista=tuple(lista), por_id=MappingProxyType(por_id), por_codigo=MappingProxyType(por_codigo),
        por_cliente=MappingProxyType({k: tuple(v) for k, v in por_cliente.items()}),
        por_cliente_usina=MappingProxyType({k: tuple(v) for k, v in por_cu.items()}),
        local_por_codigo=MappingProxyType(local), tipos=tuple(n_tipo.most_common()), n_com_codigo=n_com_codigo,
        versao=versao, lido_em=float(lido_em), fonte=fonte)


def _montar(registros, fonte: str, lido_em: float) -> Catalogo:
    copias = _preparar(registros)
    return _indexar(copias, _versao(copias), fonte, lido_em)


VAZIO = _montar([], "disco", 0.0)       # o "catálogo de ninguém": para quem lê sem catálogo e não quer testar None


# ── o estado do processo ───────────────────────────────────────────────────────────────────────────────────────────────
_ATUAL: Catalogo | None = None
_TRAVA = threading.Lock()               # a troca da versão (comparar com a de agora e instalar)
_TRAVA_BOOT = threading.Lock()          # o boot local (disco e arquivo antigo) uma vez só, mesmo com vários pedidos juntos
_TRAVA_BANCO = threading.Lock()         # uma leitura da foto do banco por vez
_TRAVA_DISCO = threading.Lock()         # uma gravação da cópia em disco por vez
_CONFIG: dict = {"pasta": None, "legado": None}
_BOOT = {"local": False}
_FONTE_BANCO: dict = {"func": None}
_BANCO = {"tentou": 0.0}
_ESTADO: dict = {"recusa": None, "recusa_completa": None, "paridade_rest": None, "banco": None,
                 "disco": {"lido": None, "gravado_em": 0.0, "lido_em": 0.0, "erro": None}}


def configurar(pasta: str | None, legado: str | None = None) -> None:
    """Onde mora a cópia em disco (`<pasta>/ativos.json.gz`) e onde está o `assets_cache.json` antigo. Quem chama é a ponte do
    Nexus, ao criar o clone (nos testes ela não chama: sem pasta, o catálogo vive só na memória e nada toca o disco da
    máquina). O boot local (disco e arquivo antigo) acontece na primeira leitura depois disto."""
    with _TRAVA:
        _CONFIG.update(pasta=pasta, legado=legado)
        _BOOT["local"] = False


def ligar_fonte_do_banco(func) -> None:
    """A função que lê as linhas da foto dos ativos no banco (`func() -> list[dict]` com as colunas de `CAB_FOTO`). É o Nexus
    quem a entrega (a ponte): este módulo não conhece a configuração do banco. Pode levantar exceção (banco fora)."""
    _FONTE_BANCO["func"] = func


def reiniciar(pasta: str | None = None, legado: str | None = None) -> None:
    """Volta ao estado de um processo recém-subido (para os testes e para quem reconfigura): sem catálogo, sem recusa, sem a
    fonte do banco, e com a pasta e o arquivo antigo que vierem."""
    global _ATUAL
    with _TRAVA:
        _ATUAL = None
        _CONFIG.update(pasta=pasta, legado=legado)
        _BOOT["local"] = False
        _FONTE_BANCO["func"] = None
        _BANCO["tentou"] = 0.0
        _ESTADO.update(recusa=None, recusa_completa=None, paridade_rest=None, banco=None,
                       disco={"lido": None, "gravado_em": 0.0, "lido_em": 0.0, "erro": None})


# ── a cópia em disco ───────────────────────────────────────────────────────────────────────────────────────────────────
def _caminho() -> str | None:
    return os.path.join(_CONFIG["pasta"], NOME_ARQUIVO) if _CONFIG["pasta"] else None


def _gravar_disco(cat: Catalogo) -> None:
    """Grava a cópia ao lado e troca de uma vez (os.replace): quem reinicia no meio nunca lê um arquivo pela metade. Falha de
    disco vai ao log e a `estado()`, e o catálogo segue na memória."""
    destino = _caminho()
    if destino is None:
        return
    with _TRAVA_DISCO:
        tmp = "%s.%d.%d.tmp" % (destino, os.getpid(), threading.get_ident())
        try:
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            carga = {"formato": FORMATO, "fonte": cat.fonte, "lido_em": cat.lido_em, "versao": cat.versao,
                     "registros": cat.lista}
            with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=5) as f:
                json.dump(carga, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, destino)
            _ESTADO["disco"].update(gravado_em=time.time(), lido_em=cat.lido_em, erro=None)
        except Exception as e:                                       # noqa: BLE001 — o disco não derruba o catálogo
            _ESTADO["disco"]["erro"] = "gravar: %s: %s" % (type(e).__name__, str(e)[:120])
            log.warning("catálogo de ativos: não consegui gravar a cópia em disco (%s)", _ESTADO["disco"]["erro"])
            try:
                os.remove(tmp)
            except OSError:
                pass


def _ler_disco():
    """(registros, lido_em) da cópia em disco, ou None: sem arquivo, ilegível, de outro formato ou com a lista vazia (o
    motivo, se houve, fica em `estado()`). Nunca levanta."""
    caminho = _caminho()
    if caminho is None or not os.path.exists(caminho):
        return None
    try:
        with gzip.open(caminho, "rt", encoding="utf-8") as f:
            carga = json.load(f)
        if not isinstance(carga, dict) or carga.get("formato") != FORMATO:
            raise ValueError("formato %r, o esperado é %d" % (carga.get("formato") if isinstance(carga, dict) else None,
                                                              FORMATO))
        registros = carga.get("registros")
        if not isinstance(registros, list) or not registros or not all(isinstance(r, dict) for r in registros):
            raise ValueError("sem a lista de registros")
        return registros, float(carga.get("lido_em") or 0.0)
    except (OSError, EOFError, ValueError, TypeError, zlib.error) as e:        # UnicodeError e JSONDecodeError são ValueError
        _ESTADO["disco"]["erro"] = "ler: %s: %s" % (type(e).__name__, str(e)[:120])
        log.warning("catálogo de ativos: ignorei a cópia em disco (%s)", _ESTADO["disco"]["erro"])
        return None


def _ler_legado():
    """(registros, ts) do `assets_cache.json` antigo (versão 2), ou None. Lido uma vez só, como migração."""
    caminho = _CONFIG["legado"]
    if not caminho or not os.path.exists(caminho):
        return None
    try:
        with open(caminho, encoding="utf-8") as f:
            c = json.load(f)
        if not isinstance(c, dict) or c.get("ver") != FORMATO_LEGADO:
            raise ValueError("versão %r, a esperada é %d" % (c.get("ver") if isinstance(c, dict) else None, FORMATO_LEGADO))
        ativos = c.get("assets")
        if not isinstance(ativos, list) or not ativos:
            raise ValueError("sem ativos")
        return ativos, float(c.get("ts") or 0.0)
    except (OSError, ValueError, TypeError) as e:
        log.warning("catálogo de ativos: ignorei o assets_cache.json antigo (%s: %s)", type(e).__name__, str(e)[:120])
        return None


# ── a troca ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _hora(ts: float) -> str:
    return datetime.fromtimestamp(ts, _BRT).strftime("%d/%m %H:%M:%S")


def _trocar(registros, fonte: str, lido_em: float | None, gravar: bool) -> bool:
    global _ATUAL
    if fonte not in FONTES:
        raise ValueError("fonte desconhecida: %r (as válidas: %s)" % (fonte, ", ".join(FONTES)))
    lido_em = time.time() if lido_em is None else float(lido_em)
    # a versão ANTES de montar qualquer coisa: a lista igual à de agora (a renovação diária) e a recusada não montam nada
    copias = _preparar(registros or [])
    n_novo = len(copias)
    versao = _versao(copias) if n_novo else ""
    mudou = True
    with _TRAVA:
        atual = _ATUAL
        motivo = tipo = None
        if n_novo == 0:
            tipo, motivo = "vazia", "a lista veio vazia"
        elif atual is not None and n_novo * 100 < len(atual.lista) * (100 - ENCOLHE_MAX):
            tipo, motivo = "encolheu", "a lista encolheu de %d para %d ativos (mais que os %d%% permitidos)" % (
                len(atual.lista), n_novo, ENCOLHE_MAX)
        elif atual is not None and atual.versao != versao and lido_em < atual.lido_em:
            tipo, motivo = "velha", "a leitura de %s é mais velha que o catálogo de agora (de %s) e tem outro conteúdo" % (
                _hora(lido_em), _hora(atual.lido_em))
        if motivo:
            recusa = {"motivo": motivo, "tipo": tipo, "em": time.time(), "lido_em": lido_em, "fonte": fonte,
                      "n_novo": n_novo, "n_atual": len(atual.lista) if atual is not None else 0}
            _ESTADO["recusa"] = recusa
            if tipo == "encolheu" and fonte in ("rest", "rpc"):
                # a leitura completa do Fracttal que não entrou: fica lembrada à parte, para uma lista vazia ou uma leitura
                # mais velha que vier depois (e vira o `motivo` de `estado()`) não apagá-la
                _ESTADO["recusa_completa"] = recusa
            log.warning("catálogo de ativos: troca recusada (fonte %s): %s", fonte, motivo)
            return False
        if atual is not None and atual.versao == versao:
            # a mesma lista, conferida de novo: nada se monta, só a hora (que não volta no tempo) e a fonte da leitura mais nova
            mudou = False
            novo = replace(atual, lido_em=max(atual.lido_em, lido_em),
                           fonte=fonte if lido_em >= atual.lido_em else atual.fonte)
        else:
            novo = _indexar(copias, versao, fonte, lido_em)
        _ATUAL = novo
    if gravar and (mudou or novo.lido_em - _ESTADO["disco"]["lido_em"] >= REGRAVAR_DISCO_S):
        _gravar_disco(novo)
    return True


def trocar(registros: list, fonte: str, *, lido_em: float | None = None) -> bool:
    """Troca o catálogo INTEIRO por `registros` (os dicionários do `montar_registros`: cópias são tiradas, o que o chamador
    passou não é tocado). True se trocou; False se recusou (lista vazia, ou menor que a de agora em mais de 5%): fica a de
    agora e o motivo vai para `estado()["recusa"]`. `fonte` é banco, rest ou rpc (`disco` é do boot). `lido_em`: quando a
    lista foi lida da fonte (padrão: agora). O que veio do Fracttal (rest, rpc) também vai para a cópia em disco."""
    return _trocar(registros, fonte, lido_em, gravar=fonte in ("rest", "rpc"))


# ── a leitura ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def atual() -> Catalogo | None:
    """O catálogo de agora, ou None se esta máquina ainda não tem nenhum. A 1ª chamada do processo faz o boot local (a cópia em
    disco e, se não há, o `assets_cache.json` antigo): sem rede, uns décimos de segundo. Quem precisa do catálogo mesmo sem
    cópia local pede `garantir()`."""
    if _ATUAL is None and not _BOOT["local"]:
        _boot_local()
    return _ATUAL


def _boot_local() -> None:
    """A cópia em disco e, se não há, o arquivo antigo. Quem chega com o boot em curso ESPERA nele (a trava): o "feito" só vale
    depois do boot, senão o pedido que chegasse nos primeiros décimos de segundo depois de subir veria "sem catálogo" e
    baixaria os ~22 mil ativos do Fracttal (achado pelo teste dos 8 pedidos juntos)."""
    with _TRAVA_BOOT:
        if _BOOT["local"] or _ATUAL is not None:
            _BOOT["local"] = True
            return
        try:
            carga = _ler_disco()
            if carga is not None:
                registros, lido_em = carga
                if _trocar(registros, "disco", lido_em, gravar=False):
                    log.info("catálogo de ativos: %d ativos da cópia em disco", len(_ATUAL.lista))
                    _ESTADO["disco"].update(lido="cópia", lido_em=lido_em)
                    return
            legado = _ler_legado()
            if legado is not None:
                registros, ts = legado
                # a migração: o arquivo antigo vira a cópia nova (e o catálogo daqui em diante nasce dela)
                if _trocar(registros, "disco", ts, gravar=True):
                    log.info("catálogo de ativos: %d ativos do assets_cache.json antigo (cópia nova gravada)",
                             len(_ATUAL.lista))
                    _ESTADO["disco"].update(lido="arquivo antigo")
        except Exception as e:                                       # noqa: BLE001 — o boot não derruba quem só quer ler
            _ESTADO["disco"]["erro"] = "boot: %s: %s" % (type(e).__name__, str(e)[:120])
            log.warning("catálogo de ativos: o boot local falhou (%s)", _ESTADO["disco"]["erro"])
        finally:
            _BOOT["local"] = True


def garantir() -> Catalogo | None:
    """O catálogo, de qualquer fonte que NÃO seja o Fracttal: o que está na memória, a cópia em disco, o `assets_cache.json`
    antigo e, por último, a foto do banco (uns 3 s para 22 mil linhas; uma leitura por vez, e a que falhou espera
    `ESPERA_BANCO_S`). None se nenhuma deu: quem chama decide (o `api.load_assets_cached` baixa do Fracttal uma vez)."""
    cat = atual()
    if cat is not None:
        return cat
    return _boot_banco()


def _boot_banco() -> Catalogo | None:
    func = _FONTE_BANCO["func"]
    if func is None:
        return None
    with _TRAVA_BANCO:
        if _ATUAL is not None:                                      # outro pedido já encheu enquanto este esperava
            return _ATUAL
        if time.time() - _BANCO["tentou"] < ESPERA_BANCO_S:
            return None
        _BANCO["tentou"] = time.time()
        try:
            registros, lido_em = registros_da_foto(func())
        except FotoIncompleta as e:
            _ESTADO["banco"] = {"em": time.time(), "motivo": str(e)}
            log.warning("catálogo de ativos: a foto do banco não serve de catálogo (%s)", e)
            return None
        except Exception as e:                                      # noqa: BLE001 — banco fora: o catálogo vem do Fracttal
            _ESTADO["banco"] = {"em": time.time(), "motivo": "%s: %s" % (type(e).__name__, str(e)[:120])}
            log.warning("catálogo de ativos: não consegui ler a foto do banco (%s)", _ESTADO["banco"]["motivo"])
            return None
        if _trocar(registros, "banco", lido_em, gravar=False):
            _ESTADO["banco"] = {"em": time.time(), "motivo": None}
            log.info("catálogo de ativos: %d ativos da foto do banco", len(_ATUAL.lista))
        else:
            motivo = (_ESTADO["recusa"] or {}).get("motivo")
            _ESTADO["banco"] = {"em": time.time(), "motivo": "a troca foi recusada: %s" % motivo}
        return _ATUAL


def registro(codigo) -> dict | None:
    """Uma CÓPIA do registro do ativo pelo código (igualdade exata, como o `_asset_by_code` sempre fez), pelo índice: sem
    percorrer a lista. None se não achar (ou se não há catálogo)."""
    cat = atual()
    if cat is None or not codigo:
        return None
    r = cat.por_codigo.get(codigo)
    return dict(r) if r is not None else None


def recusa_vigente(cat: Catalogo | None = None) -> dict | None:
    """A última leitura COMPLETA que o Fracttal deu (rest, rpc) e o catálogo recusou por ter encolhido, se ela é mais nova que
    o catálogo (nenhuma leitura aceita depois dela); senão None. Uma cópia do registro de `estado()["recusa"]` (que guarda a
    última recusa de qualquer tipo; esta fica à parte). A lista vazia não entra: não é leitura completa (sessão sem permissão,
    Fracttal mudo), a próxima tentativa custa um pedido só, e esperar 24 h por ela deixaria o catálogo velho à toa. A leitura
    mais velha que o catálogo (outra fonte, download atrasado) também não."""
    cat = _ATUAL if cat is None else cat
    r = _ESTADO["recusa_completa"]
    if cat is None or r is None or r["lido_em"] <= cat.lido_em:
        return None
    return dict(r)


def conferido_em(cat: Catalogo) -> float:
    """A última vez que o Fracttal foi lido por inteiro para este catálogo: o `lido_em` dele ou a leitura completa que ele
    recusou depois, a mais nova das duas. O `api` decide por aqui se o catálogo venceu, e se um pedido que esperou a vez já
    tem a leitura de que precisa (alguém leu enquanto ele esperava, a leitura entrando ou não)."""
    r = recusa_vigente(cat)
    return max(cat.lido_em, r["lido_em"]) if r else cat.lido_em


def estado() -> dict:
    """O que se sabe do catálogo, para o Raio-X: a fonte, o `lido_em`, a versão, quantos ativos, a última troca recusada
    (motivo, hora, fonte e tamanhos), a paridade do REST (a leitura que a etapa 2.2 confere contra o RPC) e a situação do disco
    e da foto do banco."""
    cat = _ATUAL
    tem = cat is not None
    return {"fonte": cat.fonte if tem else None, "lido_em": cat.lido_em if tem else None,
            "versao": cat.versao if tem else None, "n": len(cat.lista) if tem else 0,
            "recusa": dict(_ESTADO["recusa"]) if _ESTADO["recusa"] else None,
            "paridade_rest": _ESTADO["paridade_rest"], "disco": dict(_ESTADO["disco"]),
            "banco": dict(_ESTADO["banco"]) if _ESTADO["banco"] else None}


def anotar_paridade_rest(resultado: dict | None) -> None:
    """Guarda o resultado da conferência REST x RPC (quem confere é a leitura da etapa 2.2) para `estado()` mostrar."""
    _ESTADO["paridade_rest"] = dict(resultado) if resultado else None


# ── a foto do banco como catálogo (a 3ª fonte do boot) ─────────────────────────────────────────────────────────────────
# As colunas de `nexus_ativos_fracttal · foto_ativos` (`nexus/dados/equipamento.py:CAB_FOTO`; um teste confere que não mudaram)
CAB_FOTO = ("fracttal_item_id", "codigo", "descricao", "pai_item_id", "tipo_fracttal", "foto_em")
_USINA_NO_NOME = re.compile(r"^(.+? - .+? - [A-Z]{2})(?=\s|$)")


class FotoIncompleta(ValueError):
    """A foto não serve de catálogo: as linhas dela não chegam à raiz (o cliente), então o caminho não se monta."""


def _int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError, OverflowError):
        return None


def _limpa(descricao) -> str:
    return str(descricao or "").split("{")[0].strip()


def _nome_no_caminho(descricao, usina: bool, cauda: str = "") -> str:
    """O nome de um item como o Fracttal o põe no caminho (`parent_description`). A descrição do item traz atrás do nome o
    ENDEREÇO da usina e o "{ CÓDIGO }" (a foto já tirou o código quando ele repete o do item): "2C - Araputanga 1 - MT  Zona
    Rural km 4" é o item, "2C - Araputanga 1 - MT" é o nome no caminho.
    - A usina (o 2º trecho) tem a forma "Cliente - Usina - UF", com o endereço colado depois de UM espaço ou de dois: o corte é
      na sigla do estado (medido nas 189 usinas com equipamento do catálogo de 28/10/2026: acerta as 189).
    - Os outros níveis (Cabine 1, Inversor 1.1) trazem o MESMO endereço da usina atrás do nome (`cauda`, o que sobra da
      descrição da usina depois do nome dela): tira-se a cauda (97% dos 35 mil níveis do catálogo de 28/10) ou, sem ela, corta-se
      no 1º espaço duplo. O que sobrar de endereço só enfeita o texto: o cliente e a usina, que o `montar_registros` lê, são o
      1º e o 2º trechos."""
    d = _limpa(descricao)
    if usina:
        m = _USINA_NO_NOME.match(d)
        if m:
            return m.group(1)
    if cauda and d.endswith(cauda) and len(d) > len(cauda):
        return d[:-len(cauda)].rstrip()
    return re.split(r"\s{2,}", d)[0].strip()


def registros_da_foto(linhas) -> tuple:
    """(registros, lido_em) a partir das linhas da foto (`CAB_FOTO`), no formato que o `montar_registros` entrega: o
    `parent_description` montado pela cadeia de `pai_item_id` ("// Cliente/ Usina/ Cabine 1/ ", a forma do Fracttal), o
    cliente e a usina dele, o tipo pelo código.

    Só a foto mais nova entra (a de 21/06 que a carga única de 11/10 levou junto tem os 719 códigos que o Fracttal já não
    tem). Não vêm da foto, e ficam None: `id_type_item` e `id_group_task` (a etapa 2.2 acrescenta o `id_group_task`).
    ATENÇÃO: a criação de OS usa o registro do catálogo (`api.create_os_rpc` põe `id_type_item or 1`) e só a aprovação da Fila
    espera o catálogo em dia (`em_dia`): antes de a foto valer como catálogo, ela tem de levar os dois campos. A descrição sai
    sem o "{ CÓDIGO }" do fim (a foto o tirou).

    Levanta `FotoIncompleta` se mais de 1% das linhas não chega à raiz (o item sem pai) pela cadeia de pais; a foto de 22/09
    não chega: ver o topo do módulo."""
    rows = [dict(l) for l in (linhas or ()) if isinstance(l, dict) and not l.get("fora_do_fracttal_desde")]
    if not rows:
        raise FotoIncompleta("a foto veio vazia")
    ultima = max(str(r.get("foto_em") or "") for r in rows)
    rows = [r for r in rows if str(r.get("foto_em") or "") == ultima]
    por_id = {}
    for r in rows:
        i = _int(r.get("fracttal_item_id"))
        if i is not None:
            por_id.setdefault(i, r)

    def ancestrais(r):
        """(os pais da linha, da raiz até o pai imediato; se a cadeia chegou à raiz, a linha sem pai). Pai que não está na
        foto, ciclo e cadeia de mais de 30 níveis não chegam."""
        pais, atual_, visto = [], _int(r.get("pai_item_id")), set()
        while atual_ is not None:
            pai = por_id.get(atual_)
            if pai is None or atual_ in visto or len(pais) >= 30:
                return pais, False
            visto.add(atual_)
            pais.append(pai)
            atual_ = _int(pai.get("pai_item_id"))
        pais.reverse()
        return pais, True
    cadeias = [(r,) + ancestrais(r) for r in rows]
    nomes: dict = {}                                                 # o nome no caminho de cada item (um ancestral serve a milhares)
    sem_raiz = sum(1 for _r, _pais, chegou in cadeias if not chegou)
    if sem_raiz * 100 > len(rows) * ORFAOS_MAX_PCT:
        raise FotoIncompleta(
            "%d de %d linhas não chegam à raiz (o cliente) pela cadeia de pais: sem ele o caminho do ativo e o cliente não "
            "se montam, e inventá-los faria o Almoxarifado e o TESTE - PA aparecerem com nomes inventados"
            % (sem_raiz, len(rows)))
    cru = []
    for r, pais, chegou in cadeias:
        if not chegou:
            continue                                                 # o dado torto fica de fora (até 1%)
        cauda = ""
        if len(pais) > 1:                                            # o endereço da usina, que os itens de dentro repetem
            usina, d0 = pais[1], _limpa(pais[1].get("descricao"))
            nome_usina = nomes.setdefault(id(usina), _nome_no_caminho(usina.get("descricao"), usina=True))
            cauda = d0[len(nome_usina):].strip() if d0.startswith(nome_usina) else ""
        caminho = []
        for n, p in enumerate(pais):
            if id(p) not in nomes:
                nomes[id(p)] = _nome_no_caminho(p.get("descricao"), usina=(n == 1), cauda=cauda if n > 1 else "")
            caminho.append(nomes[id(p)])
        cru.append({"id": _int(r.get("fracttal_item_id")), "code": str(r.get("codigo") or ""),
                    "description": str(r.get("descricao") or ""), "id_parent": _int(r.get("pai_item_id")),
                    "id_type_item": None, "id_group_task": _int(r.get("id_group_task")),
                    "parent_description": ("// " + "/ ".join(caminho) + "/ ") if caminho else ""})
    registros = montar_registros(cru)
    try:
        lido_em = datetime.fromisoformat(ultima[:10]).replace(tzinfo=_BRT).timestamp()
    except ValueError:
        lido_em = 0.0
    return registros, lido_em
