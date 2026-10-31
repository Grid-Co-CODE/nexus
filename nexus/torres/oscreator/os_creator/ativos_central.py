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
  de uma vez só, com o formato escrito dentro, e só se o catálogo ainda for o vigente; a ilegível ou de outro formato é
  ignorada; as gravações e as leituras do disco moram em `ativos_disco.py`); (2) o `assets_cache.json` antigo,
  lido UMA vez como migração se a cópia nova não existe (e já grava a nova); (3) a foto dos ativos no banco
  (`nexus_ativos_fracttal · foto_ativos`), se o Nexus ligou uma função que a lê (`ligar_fonte_do_banco`; este módulo não
  conhece a configuração do banco). Sem nenhuma das três, o catálogo nasce do primeiro download (`trocar(..., "rpc")`).
- A troca recusa a lista vazia, a que encolhe mais de 5% (`ENCOLHE_MAX`) contra a de agora e, só da foto do banco e do disco
  (o `lido_em` veio escrito), a leitura mais velha que o catálogo de agora com conteúdo diferente: o download do RPC pelas
  páginas perde 200 ativos em silêncio quando uma página vem sem lista, e "número pela metade não vai para a tela". O motivo da
  última recusa fica em `estado()`.
- A RECUSA É LEMBRADA (revisão 1 da tarefa 2.1): a leitura completa que o Fracttal deu e o catálogo recusou (a que encolheu)
  também foi uma ida ao Fracttal, de ~110 a ~270 pedidos. `conferido_em(cat)` é o mais novo entre o `lido_em` do catálogo e
  essa leitura, e é por ele que o `api` decide se o catálogo venceu: sem isso, passadas as 24 h, cada aprovação da Fila baixava
  tudo de novo (minutos na frente de quem aprovava) e o download por trás repetia de 10 em 10 min, com o mesmo resultado. Desde
  a 2.2 ela sobrevive ao reinício (`ativos_estado.json`, ao lado da cópia em disco, com a última paridade do REST): o servidor
  reinicia ~10 vezes por dia e, só na memória, cada deploy releria o Fracttal uma vez e a confirmação abaixo nunca chegaria.
- O ENCOLHIMENTO CONFIRMADO (2.2): o Fracttal que perdeu ativos de verdade (uma usina que saiu da carteira) seria recusado para
  sempre. A troca que encolhe passa quando o MESMO conjunto de ativos sai do catálogo em duas leituras completas de caminhos
  diferentes (REST e RPC) ou do mesmo caminho com 20 h ou mais entre elas, sem leitura aceita no meio (o conjunto é o que SAI,
  e não a lista inteira: os novos do dia entrariam entre as duas e a confirmação nunca viria); `estado()["encolhimento"]` diz.
  No servidor fecha sozinho: a leitura REST da noite seguinte (24 h depois) é o mesmo caminho com mais de 20 h; com o leitor
  desligado ou recusado, o catálogo vence em 24 h e a 1ª sessão do dia lê pelo RPC (o outro caminho).
- Cada versão tem um sha das linhas ordenadas (`versao`), calculado ANTES de montar qualquer coisa: a mesma lista lida de novo
  (o caso comum da renovação diária) não monta nada, só renova o `lido_em`.
- OS NOVOS DO DIA (`acrescentar`, 2.2): o leitor do servidor lê de 30 em 30 min só os ativos criados depois do maior id do
  catálogo e os soma ao catálogo de agora, trocado inteiro como sempre. O `lido_em` NÃO anda com eles (não é a lista inteira
  conferida: o que saiu ou mudou só a leitura da noite vê); anda o `novos_em`, e a tela diz "ativos de HH:MM" pelo mais novo dos
  dois (`visto_em`).

O FRESCOR (`lido_em`, quando a lista foi conferida com a fonte) é decidido por quem usa: o `api.load_assets_cached` serve o
que há e renova por trás o que passou de 24 h. Este módulo só guarda e entrega. O leitor do servidor (`ativos_leitor.py`, que só
o `servir.py` liga) se registra aqui (`ligar_leitor`), e o `api` o chama sem importá-lo: o PC e os testes seguem sem ele.

A FOTO DO BANCO COMO CATÁLOGO (a 3ª fonte) e o caminho montado pela cadeia de pais moram em `ativos_foto.py` (o limite medido
da foto de 22/09, sem a raiz de cada cliente, está no topo de lá); daqui só se lê `registros_da_foto` e `FotoIncompleta`.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import threading
import time
import unicodedata
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
from ativos_foto import CAB_FOTO, FotoIncompleta, registros_da_foto  # noqa: E402,F401 — a foto como catálogo (o api e os testes)
import ativos_disco  # noqa: E402 — a cópia em disco e o estado que sobrevive ao reinício
from ativos_disco import FORMATO, FORMATO_LEGADO, NOME_ARQUIVO, NOME_ESTADO  # noqa: E402,F401 — os nomes de sempre

log = logging.getLogger("oscreator.ativos_central")

FONTES = ("banco", "rest", "rpc", "disco")
ENCOLHE_MAX = 5                 # % que a lista nova pode ser menor que a de agora; mais que isto, a troca é recusada
CONFIRMA_MESMO_CAMINHO_S = 20 * 3600   # o encolhimento lido duas vezes pelo MESMO caminho só vale com isto entre as leituras
ESPERA_BANCO_S = 600            # a foto do banco que falhou ou veio incompleta só é lida de novo depois disto
REGRAVAR_DISCO_S = 3600         # a mesma lista lida de novo regrava o disco (o `lido_em` dele não fica para trás) a cada hora
# o leitor do servidor só está pronto (os botões pedem os novos a ele) com a conferência da leitura REST de no máximo 30 h:
# a da noite de ontem com folga para a de hoje atrasar; passou disso, a última noite boa ficou para trás e o socorro é o RPC
PARIDADE_VALE_S = 30 * 3600
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
    inicial; `len(por_codigo)` são os códigos distintos). `versao` é o sha das linhas ordenadas; `lido_em`, quando a lista
    INTEIRA foi conferida com a fonte dela; `fonte`, de onde veio (banco, rest, rpc ou disco); `novos_em`, a última leitura dos
    ativos novos do dia (`acrescentar`; 0 = nenhuma desde a lista inteira)."""
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
    novos_em: float = 0.0


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


def _indexar(copias, versao: str, fonte: str, lido_em: float, novos_em: float = 0.0) -> Catalogo:
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
        versao=versao, lido_em=float(lido_em), fonte=fonte, novos_em=float(novos_em))


def _montar(registros, fonte: str, lido_em: float) -> Catalogo:
    copias = _preparar(registros)
    return _indexar(copias, _versao(copias), fonte, lido_em)


VAZIO = _montar([], "disco", 0.0)       # o "catálogo de ninguém": para quem lê sem catálogo e não quer testar None


# ── o estado do processo ───────────────────────────────────────────────────────────────────────────────────────────────
_ATUAL: Catalogo | None = None
_TRAVA = threading.Lock()               # a troca da versão (comparar com a de agora e instalar)
_TRAVA_BOOT = threading.Lock()          # o boot local (disco e arquivo antigo) uma vez só, mesmo com vários pedidos juntos
_TRAVA_BANCO = threading.Lock()         # uma leitura da foto do banco por vez
_CONFIG: dict = {"pasta": None, "legado": None}
_BOOT = {"local": False}
_FONTE_BANCO: dict = {"func": None}
_BANCO = {"tentou": 0.0}
# o leitor do servidor (`ativos_leitor.ligar`, só pelo servir.py): as funções dele, que o `api` chama por aqui sem importá-lo
_LEITOR: dict = {"pedir_novos": None, "esperar_novos": None, "estado": None}


def _estado_limpo() -> dict:
    # `rest`: a última leitura REST que deu certo e a última que falhou (a dos novos ou a da noite): a falha mais nova que a
    # boa tira a prontidão do leitor, e a próxima boa a devolve (revisão 1 da 2.2)
    return {"recusa": None, "recusa_completa": None, "paridade_rest": None, "banco": None, "encolhimento": None,
            "falha": None, "rest": {"bom_em": 0.0, "falha_em": 0.0, "falha": None},
            "disco": {"lido": None, "gravado_em": 0.0, "lido_em": 0.0, "erro": None}}


_ESTADO: dict = _estado_limpo()


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
    fonte do banco, sem o leitor, e com a pasta e o arquivo antigo que vierem."""
    global _ATUAL
    with _TRAVA:
        _ATUAL = None
        _CONFIG.update(pasta=pasta, legado=legado)
        _BOOT["local"] = False
        _FONTE_BANCO["func"] = None
        _BANCO["tentou"] = 0.0
        _LEITOR.update(pedir_novos=None, esperar_novos=None, estado=None)
        _ESTADO.clear()
        _ESTADO.update(_estado_limpo())


# ── o leitor do servidor ───────────────────────────────────────────────────────────────────────────────────────────────
def ligar_leitor(*, pedir_novos=None, esperar_novos=None, estado=None) -> None:
    """O leitor dos ativos do servidor (`ativos_leitor.ligar`) se registra aqui: `pedir_novos()` lê os ativos novos por trás e
    volta na hora; `esperar_novos(teto, so_em_curso)` espera a leitura deles até `teto` segundos e diz o desfecho; `estado()`
    diz o que ele fez. Sem a credencial do Fracttal ele registra só o `estado` (para o motivo aparecer) e as telas seguem pelo
    RPC."""
    _LEITOR.update(pedir_novos=pedir_novos, esperar_novos=esperar_novos, estado=estado)


def paridade_recente(agora: float | None = None) -> dict | None:
    """A última conferência da leitura REST, se ela VALEU e tem no máximo `PARIDADE_VALE_S` (30 h); senão None. A noite que
    falha (o REST fora, a credencial, o `sort` recusado) não renova a conferência: passadas as 30 h da última boa, o REST deixa de
    somar os novos e os botões voltam ao RPC, até uma noite boa."""
    atual()                                                         # o boot local traz a de antes do reinício
    p = _ESTADO["paridade_rest"]
    em = p.get("em") if p else None
    if not p or not p.get("vale") or not isinstance(em, (int, float)):
        return None
    if (time.time() if agora is None else agora) - em > PARIDADE_VALE_S:
        return None
    return dict(p)


def anotar_leitura_rest(ok: bool, motivo: str | None = None) -> None:
    """Uma leitura REST do Fracttal (a dos novos ou a da noite) que deu certo (`ok`) ou que falhou (a exceção do cliente, a
    leitura incompleta, a página fora de ordem; os novos demais NÃO são falha: o REST respondeu, e eles ficam para a noite). A
    falha mais nova que a última boa tira a prontidão do leitor; a próxima boa a devolve. Vai ao `ativos_estado.json`: o
    reinício não esquece que o REST está falhando."""
    agora = time.time()
    if ok:
        _ESTADO["rest"].update(bom_em=agora)
    else:
        _ESTADO["rest"].update(falha_em=agora, falha=str(motivo or "")[:200])
    _gravar_estado()


def _rest_falhando() -> bool:
    r = _ESTADO["rest"]
    return float(r.get("falha_em") or 0.0) > float(r.get("bom_em") or 0.0)


def leitor_pronto() -> bool:
    """O leitor está ligado, a última conferência da leitura REST valeu e tem no máximo 30 h (`paridade_recente`), e nenhuma
    leitura REST falhou depois da última que deu certo (revisão 1 da 2.2: a prontidão que nunca expirava deixava os botões no
    REST mesmo com toda leitura falhando, sem o socorro do RPC, e a Fila sem o ativo de hoje por um dia). Fora da prontidão, o
    REST não acrescenta nada e as telas seguem pelo RPC, com a sessão da pessoa, como antes do leitor."""
    if _LEITOR["pedir_novos"] is None:
        return False
    return paridade_recente() is not None and not _rest_falhando()


def pedir_novos() -> bool:
    """Pede ao leitor os ativos novos, por trás (quem chama não espera). False se o leitor não está pronto."""
    if not leitor_pronto():
        return False
    try:
        return bool(_LEITOR["pedir_novos"]())
    except Exception:                                               # noqa: BLE001 — o pedido nunca derruba a tela
        log.exception("catálogo de ativos: o pedido dos ativos novos falhou")
        return False


def esperar_novos(teto: float, so_em_curso: bool = False) -> dict | None:
    """Espera a leitura dos ativos novos até `teto` segundos (`so_em_curso`: só a que já está em curso, a que o botão pediu;
    senão, uma nova se a última já tem mais de um minuto) e devolve o DESFECHO dela: `terminou` (dentro do teto),
    `acrescentados`, `sem_pai`, `muitos` (mais novos do que a leitura curta lê) e `erro` (o motivo curto, ou ""). None sem o
    leitor (ou, para uma leitura nova, com ele fora da prontidão). A espera da que está em curso vale mesmo com a prontidão
    caída: é por ela que a tela sabe que a leitura que o botão pediu falhou."""
    if _LEITOR["esperar_novos"] is None or (not so_em_curso and not leitor_pronto()):
        return None
    try:
        return _LEITOR["esperar_novos"](teto, so_em_curso)
    except Exception:                                               # noqa: BLE001
        log.exception("catálogo de ativos: a espera dos ativos novos falhou")
        return None


# ── a cópia em disco e o estado que sobrevive ao reinício: em `ativos_disco.py` (Ruling AM); aqui, só quem passa a pasta ────
def _caminho() -> str | None:
    return ativos_disco.caminho(_CONFIG["pasta"])


def _gravar_disco(cat: Catalogo) -> None:
    """A cópia em disco deste catálogo, só se ele ainda for o vigente quando a trava do disco chegar (a versão mais nova grava
    a dela: uma troca e os novos do dia terminando em ordem trocada não deixam a velha no disco)."""
    ativos_disco.gravar_catalogo(_CONFIG["pasta"], cat, _ESTADO["disco"], lambda: cat is _ATUAL)


def _ler_disco():
    return ativos_disco.ler_catalogo(_CONFIG["pasta"], _ESTADO["disco"])


def _gravar_estado() -> None:
    ativos_disco.gravar_estado(_CONFIG["pasta"], {"recusa_completa": _ESTADO["recusa_completa"],
                                                  "paridade_rest": _ESTADO["paridade_rest"], "rest": _ESTADO["rest"]})


def _ler_estado() -> None:
    """O `ativos_estado.json` de antes do reinício: a recusa lembrada, a paridade e a prontidão do REST voltam à memória."""
    d = ativos_disco.ler_estado(_CONFIG["pasta"])
    if not d:
        return
    r, p, rest = d.get("recusa_completa"), d.get("paridade_rest"), d.get("rest")
    if isinstance(r, dict) and isinstance(r.get("lido_em"), (int, float)):
        _ESTADO["recusa_completa"] = r
    if isinstance(p, dict):
        _ESTADO["paridade_rest"] = p
    if isinstance(rest, dict):
        _ESTADO["rest"].update({k: rest.get(k) for k in ("bom_em", "falha_em", "falha") if k in rest})


def _ler_legado():
    return ativos_disco.ler_legado(_CONFIG["legado"])


# ── a troca ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _hora(ts: float) -> str:
    return datetime.fromtimestamp(ts, _BRT).strftime("%d/%m %H:%M:%S")


def _chave_do_ativo(r) -> str:
    return "i:%s" % r.get("id") if r.get("id") is not None else "c:%s" % (r.get("code") or "")


def _conjunto(atual: Catalogo, copias) -> str:
    """O sha do CONJUNTO de ativos que a leitura tira do catálogo (os ids que ele tem e ela não; sem id, o código): é por ele
    que duas leituras completas que encolheram igual se reconhecem, mesmo vindas de caminhos (REST e RPC) que escrevem o caminho
    ou o grupo diferente. É o conjunto que SAIU, e não a lista inteira, porque os ativos novos do dia (que o catálogo ganha de
    30 em 30 min) mudariam a lista entre a 1ª e a 2ª leitura, e a confirmação nunca chegaria."""
    vem = {_chave_do_ativo(r) for r in copias}
    saiu = sorted({_chave_do_ativo(r) for r in atual.lista} - vem)
    return hashlib.sha256("\n".join(saiu).encode("utf-8")).hexdigest()


def _confirma(anterior: dict | None, conjunto: str, fonte: str, lido_em: float) -> bool:
    """A leitura que encolheu confirma a recusa lembrada: o mesmo conjunto, de outro caminho (rest x rpc) ou do mesmo com
    `CONFIRMA_MESMO_CAMINHO_S` entre as duas. Uma leitura só que encolhe pode ser página perdida; duas, por caminhos ou dias
    diferentes, são o Fracttal de verdade."""
    if not anterior or anterior.get("conjunto") != conjunto:
        return False
    if anterior.get("fonte") != fonte:
        return True
    return lido_em - float(anterior.get("lido_em") or 0.0) >= CONFIRMA_MESMO_CAMINHO_S


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
    lembrar = False
    with _TRAVA:
        atual = _ATUAL
        motivo = tipo = conjunto = None
        confirmado = None
        if n_novo == 0:
            tipo, motivo = "vazia", "a lista veio vazia"
        elif atual is not None and n_novo * 100 < len(atual.lista) * (100 - ENCOLHE_MAX):
            conjunto = _conjunto(atual, copias)
            anterior = recusa_vigente(atual)
            if fonte in ("rest", "rpc") and _confirma(anterior, conjunto, fonte, lido_em):
                confirmado = {"motivo": "encolhimento confirmado: os mesmos ativos saíram na leitura %s de %s e na %s de %s "
                                        "(eram %d, ficaram %d)" % (anterior["fonte"], _hora(anterior["lido_em"]), fonte,
                                                                   _hora(lido_em), len(atual.lista), n_novo),
                              "em": time.time(), "de": len(atual.lista), "para": n_novo,
                              "leituras": [{"fonte": anterior["fonte"], "lido_em": anterior["lido_em"]},
                                           {"fonte": fonte, "lido_em": lido_em}]}
            else:
                tipo, motivo = "encolheu", "a lista encolheu de %d para %d ativos (mais que os %d%% permitidos)" % (
                    len(atual.lista), n_novo, ENCOLHE_MAX)
        elif (fonte in ("banco", "disco") and atual is not None and atual.versao != versao
              and lido_em < atual.lido_em):
            # só a leitura com a data escrita (a foto do banco, o disco): a rest e a rpc são feitas agora e nunca são
            # "velhas" (com o relógio de parede, um download que terminou um segundo depois de outro perderia dele)
            tipo, motivo = "velha", "a leitura de %s é mais velha que o catálogo de agora (de %s) e tem outro conteúdo" % (
                _hora(lido_em), _hora(atual.lido_em))
        if motivo:
            recusa = {"motivo": motivo, "tipo": tipo, "em": time.time(), "lido_em": lido_em, "fonte": fonte,
                      "n_novo": n_novo, "n_atual": len(atual.lista) if atual is not None else 0, "conjunto": conjunto}
            _ESTADO["recusa"] = recusa
            if tipo == "encolheu" and fonte in ("rest", "rpc"):
                # a leitura completa do Fracttal que não entrou: fica lembrada à parte (e no disco, para o reinício), para uma
                # lista vazia ou uma leitura mais velha que vier depois (e vira o `motivo` de `estado()`) não apagá-la
                _ESTADO["recusa_completa"] = recusa
                lembrar = True
            log.warning("catálogo de ativos: troca recusada (fonte %s): %s", fonte, motivo)
        else:
            if atual is not None and atual.versao == versao:
                # a mesma lista, conferida de novo: nada se monta, só a hora (que não volta no tempo) e a fonte da mais nova
                mudou = False
                novo = replace(atual, lido_em=max(atual.lido_em, lido_em),
                               fonte=fonte if lido_em >= atual.lido_em else atual.fonte)
            else:
                novo = _indexar(copias, versao, fonte, lido_em)
            _ATUAL = novo
            if confirmado:
                _ESTADO["encolhimento"] = confirmado
                log.warning("catálogo de ativos: %s", confirmado["motivo"])
    if lembrar:
        _gravar_estado()
    if motivo:
        return False
    if gravar and (mudou or novo.lido_em - _ESTADO["disco"]["lido_em"] >= REGRAVAR_DISCO_S):
        _gravar_disco(novo)
    return True


def trocar(registros: list, fonte: str, *, lido_em: float | None = None) -> bool:
    """Troca o catálogo INTEIRO por `registros` (os dicionários do `montar_registros`: cópias são tiradas, o que o chamador
    passou não é tocado). True se trocou; False se recusou, e então fica a de agora e o motivo vai para `estado()["recusa"]`.
    As três recusas:
    1. a lista vazia (sessão sem permissão, Fracttal mudo: não é leitura completa, e não fica lembrada);
    2. a que encolhe mais de `ENCOLHE_MAX` (5%) contra a de agora (o RPC que perde páginas em silêncio). A de rest e rpc fica
       lembrada (`recusa_vigente`, e no disco); a leitura seguinte que tira o MESMO conjunto de ativos, por outro caminho ou
       pelo mesmo com 20 h entre as duas, passa ("encolhimento confirmado", em `estado()["encolhimento"]`);
    3. só da foto do banco e do disco (a data veio escrita), a leitura mais velha que o catálogo de agora com outro conteúdo.
    `fonte` é banco, rest ou rpc (`disco` é do boot). `lido_em`: quando a lista foi lida da fonte (padrão: agora; o leitor REST
    passa o FIM da leitura, e é por ele que quem esperou a vez sabe que a leitura veio depois do pedido). O que veio do
    Fracttal (rest, rpc) também vai para a cópia em disco."""
    return _trocar(registros, fonte, lido_em, gravar=fonte in ("rest", "rpc"))


def acrescentar(registros, fonte: str = "rest", *, lido_em: float | None = None) -> int:
    """Soma ao catálogo de agora os registros (do `montar_registros`) cujo id ele ainda não tem: os ativos novos do dia, que o
    leitor do servidor lê de 30 em 30 min (`ativos_leitor.ler_novos`). O catálogo é trocado inteiro, como sempre (quem está
    lendo a versão de antes termina com ela), e vai para o disco. O `lido_em` e a `fonte` NÃO mudam: os novos não conferem a
    lista inteira (o que saiu ou mudou só a leitura da noite vê), então o catálogo vence pelas 24 h da última lista inteira e a
    renovação de sempre continua valendo; muda o `novos_em` (`lido_em` desta leitura; padrão: agora), que a tela usa no
    "ativos de HH:MM". Sem catálogo nenhum, não há a que somar: 0. Devolve quantos entraram."""
    global _ATUAL
    if fonte not in ("rest", "rpc"):
        raise ValueError("os novos vêm do Fracttal (rest ou rpc), não de %r" % (fonte,))
    quando = time.time() if lido_em is None else float(lido_em)
    gravar = None
    with _TRAVA:
        atual = _ATUAL
        if atual is None:
            return 0
        vistos: set = set()
        novos = []
        for r in registros or ():
            i = r.get("id") if isinstance(r, dict) else None
            if i is None or i in atual.por_id or i in vistos:
                continue
            vistos.add(i)
            novos.append(r)
        if not novos:
            _ATUAL = replace(atual, novos_em=max(atual.novos_em, quando))
            return 0
        copias = _preparar(list(atual.lista) + novos)
        gravar = _ATUAL = _indexar(copias, _versao(copias), atual.fonte, atual.lido_em,
                                   novos_em=max(atual.novos_em, quando))
    log.info("catálogo de ativos: %d ativo(s) novo(s) do Fracttal somados ao catálogo", len(novos))
    _gravar_disco(gravar)
    return len(novos)


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
    global _ATUAL
    with _TRAVA_BOOT:
        if _BOOT["local"] or _ATUAL is not None:
            _BOOT["local"] = True
            return
        try:
            _ler_estado()                                           # a recusa lembrada e a paridade de antes do reinício
            carga = _ler_disco()
            if carga is not None:
                registros, lido_em, novos_em = carga
                if _trocar(registros, "disco", lido_em, gravar=False):
                    if novos_em:
                        with _TRAVA:
                            _ATUAL = replace(_ATUAL, novos_em=novos_em)
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
    cat = atual() if cat is None else cat                           # o boot local traz a recusa de antes do reinício
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


def visto_em(cat: Catalogo) -> float:
    """A última vez que esta lista foi comparada com o Fracttal, de qualquer jeito: a lista inteira (`lido_em`) ou a leitura dos
    ativos novos do dia (`novos_em`), a mais nova das duas. É a hora do "ativos de HH:MM" das telas; quem decide se o catálogo
    venceu continua sendo o `conferido_em` (a lista inteira)."""
    return max(cat.lido_em, cat.novos_em)


def estado() -> dict:
    """O que se sabe do catálogo, para o Raio-X: a fonte, o `lido_em`, o `novos_em`, a versão, quantos ativos, a última troca
    recusada (motivo, hora, fonte e tamanhos), o último encolhimento confirmado, a última falha do download pelo RPC, a paridade
    do REST (a leitura da noite conferida contra o catálogo de antes, com as coberturas dos dois lados), a última leitura REST
    boa e a última que falhou, se o leitor está pronto, a situação do disco e da foto do banco e, com o leitor do servidor
    ligado, o que ele fez (ou por que não ligou)."""
    cat = _ATUAL
    tem = cat is not None
    leitor = None
    if _LEITOR["estado"] is not None:
        try:
            leitor = _LEITOR["estado"]()
        except Exception as e:                                      # noqa: BLE001 — o estado nunca derruba quem o lê
            leitor = {"erro": "%s: %s" % (type(e).__name__, str(e)[:120])}
    return {"fonte": cat.fonte if tem else None, "lido_em": cat.lido_em if tem else None,
            "novos_em": cat.novos_em if tem else None,
            "versao": cat.versao if tem else None, "n": len(cat.lista) if tem else 0,
            "recusa": dict(_ESTADO["recusa"]) if _ESTADO["recusa"] else None,
            "encolhimento": dict(_ESTADO["encolhimento"]) if _ESTADO["encolhimento"] else None,
            "falha": dict(_ESTADO["falha"]) if _ESTADO["falha"] else None,
            "paridade_rest": _ESTADO["paridade_rest"], "rest": dict(_ESTADO["rest"]), "leitor_pronto": leitor_pronto(),
            "disco": dict(_ESTADO["disco"]), "banco": dict(_ESTADO["banco"]) if _ESTADO["banco"] else None,
            "leitor": leitor}


def anotar_paridade_rest(resultado: dict | None) -> None:
    """Guarda o resultado da conferência da leitura REST contra o catálogo (quem confere é o leitor da noite,
    `ativos_leitor.conferir_paridade`) para `estado()` mostrar e para `leitor_pronto()` decidir. Vai ao disco junto da recusa
    lembrada: sem isso, cada reinício (~10 por dia) desligaria os ativos novos do dia até a noite seguinte."""
    _ESTADO["paridade_rest"] = dict(resultado) if resultado else None
    _gravar_estado()


def paridade_rest() -> dict | None:
    """A última conferência da leitura REST (`anotar_paridade_rest`), ou None se ainda não houve nenhuma."""
    atual()                                                         # o boot local traz a de antes do reinício
    return dict(_ESTADO["paridade_rest"]) if _ESTADO["paridade_rest"] else None


def anotar_falha(fonte: str, erro) -> None:
    """A leitura do Fracttal que FALHOU (exceção: Fracttal fora, cota estourada), para quem esperava a vez não tentar de novo em
    fila (`api.load_assets_cached`) e para o Raio-X. `erro` None apaga (a leitura seguinte deu certo)."""
    _ESTADO["falha"] = None if erro is None else {"fonte": fonte, "em": time.time(),
                                                  "erro": ("%s: %s" % (type(erro).__name__, str(erro)[:160])
                                                           if isinstance(erro, BaseException) else str(erro)[:200])}


def falha() -> dict | None:
    """A última falha anotada (`anotar_falha`), ou None."""
    return dict(_ESTADO["falha"]) if _ESTADO["falha"] else None
