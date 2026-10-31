"""ativos_foto.py: o caminho do ativo montado pela cadeia de pais, e a foto do banco como catálogo (31/10/2026, etapa 2 do canto
central).

Saiu do `ativos_central.py` na tarefa 2.2 (o arquivo passava de 660 linhas, e esta parte cresce aqui): o catálogo guarda e
entrega; daqui sai o `parent_description` ("// Cliente/ Usina/ Cabine 1/ ", a forma do Fracttal) de quem não o traz pronto. São
dois os que não trazem: a foto dos ativos no banco (`nexus_ativos_fracttal · foto_ativos`, que guarda só o pai de cada item) e
a leitura REST do Fracttal (`ativos_leitor.para_registro`), se o `items` do REST não der o caminho. Os dois montam pela MESMA
função (`caminhos`), a que a 2.1 conferiu contra o RPC: sobre o catálogo de 28/10 reconstruído com as raízes, cliente 100%,
usina 99,98%, tipo 100% e o caminho igual ao do RPC em 97,7% dos ativos.

A FOTO DO BANCO COMO CATÁLOGO tem um limite real, medido em 31/10/2026 na foto de 22/09: ela foi carregada do `assets_cache.json`,
que já tinha jogado fora a raiz de cada cliente (o item sem pai, que o `montar_registros` ignora), então nenhuma linha dela chega
à raiz pela cadeia de pais, e o nome do cliente (o 1º trecho do `parent_description`) só existe na raiz. Tirar o cliente do
prefixo do nome da usina acerta 74% dos ativos (128 das 189 usinas com equipamento) e erra 6 dos 16 clientes (a carteira com
outro nome); e o "Almoxarifado" e o "TESTE - PA" (`CLIENTES_OCULTOS`) deixariam de ser reconhecidos e apareceriam nas cascatas
com nomes inventados. Por isso `registros_da_foto` RECUSA a foto cujas linhas não chegam à raiz (`FotoIncompleta`). A foto
renovada toda noite pelo leitor do servidor (2.2) leva as raízes e as colunas novas no fim (`id_type_item`, `id_group_task`,
`fora_do_fracttal_desde`), e passa a servir.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_BRT = timezone(timedelta(hours=-3))
ORFAOS_MAX_PCT = 1.0            # % das linhas da foto que podem apontar para um pai ausente (dado torto) sem recusar a foto
NIVEIS_MAX = 30                 # cadeia mais funda que isto é dado torto (um ciclo que escapou), não um ativo

# As colunas de `nexus_ativos_fracttal · foto_ativos` (`nexus/dados/equipamento.py:CAB_FOTO`; um teste confere que são as
# mesmas). As três últimas entraram em 31/10/2026, NO FIM (o livro é para sempre e quem o lê pelo nome não muda): o tipo do
# item e o grupo de tarefas do Fracttal, que a criação de OS usa, e o dia (data_id) em que o código deixou de vir do Fracttal.
CAB_FOTO = ("fracttal_item_id", "codigo", "descricao", "pai_item_id", "tipo_fracttal", "foto_em",
            "id_type_item", "id_group_task", "fora_do_fracttal_desde")
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
    ENDEREÇO da usina e o "{ CÓDIGO }" (a foto já tirou o código quando ele repete o do item): "CL - Usina Alfa 1 - MT  Estrada
    Vicinal km 9" (exemplo inventado) é o item, "CL - Usina Alfa 1 - MT" é o nome no caminho.
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


def _ancestrais(i, nos) -> tuple:
    """(os pais de `i`, da raiz até o pai imediato; se a cadeia chegou à raiz, o item sem pai). Pai que não está em `nos`,
    ciclo e cadeia de mais de `NIVEIS_MAX` níveis não chegam."""
    pais, atual, visto = [], nos[i][0], set()
    while atual is not None:
        no = nos.get(atual)
        if no is None or atual in visto or len(pais) >= NIVEIS_MAX:
            return pais, False
        visto.add(atual)
        pais.append(atual)
        atual = no[0]
    pais.reverse()
    return pais, True


def caminhos(nos, alvos=None) -> dict:
    """{id: parent_description} de cada item de `alvos` (padrão: todos de `nos`) que chega à raiz pela cadeia de pais, no
    formato do Fracttal ("// Cliente/ Usina/ Cabine 1/ "); a raiz (o item sem pai) tem caminho "". Quem não chega (pai fora de
    `nos`, ciclo, cadeia funda demais) fica de FORA: quem chama decide (a foto recusa acima de 1%; o leitor deixa o item para a
    leitura da noite). `nos`: {id: (id do pai ou None, descrição)}. O nome de cada nível é calculado uma vez (um ancestral serve
    a milhares de itens)."""
    nomes: dict = {}
    out: dict = {}
    for i in (nos if alvos is None else alvos):
        if i not in nos:
            continue
        pais, chegou = _ancestrais(i, nos)
        if not chegou:
            continue
        if not pais:
            out[i] = ""
            continue
        cauda = ""
        if len(pais) > 1:                                            # o endereço da usina, que os itens de dentro repetem
            u = pais[1]
            if u not in nomes:
                nomes[u] = _nome_no_caminho(nos[u][1], usina=True)
            d0 = _limpa(nos[u][1])
            cauda = d0[len(nomes[u]):].strip() if d0.startswith(nomes[u]) else ""
        trechos = []
        for n, p in enumerate(pais):
            if p not in nomes:
                nomes[p] = _nome_no_caminho(nos[p][1], usina=(n == 1), cauda=cauda if n > 1 else "")
            trechos.append(nomes[p])
        out[i] = "// " + "/ ".join(trechos) + "/ "
    return out


def nomes_no_caminho(nos, alvos=None) -> dict:
    """{id: o nome do item como o Fracttal o põe no caminho} de cada item de `alvos` (padrão: todos de `nos`): a descrição SEM
    o endereço da usina e sem o "{ CÓDIGO }" (`_nome_no_caminho`: na usina, o corte na sigla do estado; nos níveis de dentro,
    sem a cauda de endereço da usina deles; senão, no 1º espaço duplo). É a `descricao` que a foto do banco grava (Ruling AK,
    revisão 1 da 2.2): a API do banco tem leitura aberta, e o endereço da usina já saiu dela uma vez, no mesmo dia em que entrou
    (04/10/2026, a 1ª carga do Campo · App). O item cuja cadeia não chega à raiz leva o corte no 1º espaço duplo.
    `nos`: {id: (id do pai ou None, descrição)}, como em `caminhos`."""
    caudas: dict = {}
    out: dict = {}
    for i in (nos if alvos is None else alvos):
        if i not in nos:
            continue
        descricao = nos[i][1]
        pais, chegou = _ancestrais(i, nos)
        if not chegou or len(pais) <= 1:                             # a raiz (0), a usina (1) ou o item solto
            out[i] = _nome_no_caminho(descricao, usina=chegou and len(pais) == 1)
            continue
        u = pais[1]
        if u not in caudas:
            nome_u, d0 = _nome_no_caminho(nos[u][1], usina=True), _limpa(nos[u][1])
            caudas[u] = d0[len(nome_u):].strip() if d0.startswith(nome_u) else ""
        out[i] = _nome_no_caminho(descricao, usina=False, cauda=caudas[u])
    return out


def registros_da_foto(linhas) -> tuple:
    """(registros, lido_em) a partir das linhas da foto (`CAB_FOTO`), no formato que o `montar_registros` entrega: o
    `parent_description` montado pela cadeia de `pai_item_id` (`caminhos`), o cliente e a usina dele, o tipo pelo código.

    Quais linhas entram:
    - a linha com `fora_do_fracttal_desde` (o código que saiu do Fracttal e a foto guarda para os fatos antigos) NUNCA;
    - na foto renovada pelo leitor (2.2; a coluna `fora_do_fracttal_desde` existe), todas as outras: o `foto_em` dela é o dia
      em que a LINHA mudou pela última vez, e não o dia de uma foto;
    - na foto da carga única de 11/10 (sem a coluna), só a foto mais nova (a de 21/06 que ela levou junto tem os 719 códigos
      que o Fracttal já não tem).
    `id_type_item` e `id_group_task` vêm das colunas novas quando há (a foto de 11/10 não as tem: ficam None). A descrição sai
    sem o "{ CÓDIGO }" do fim (a foto o tirou). O `lido_em` é a meia-noite do `foto_em` mais novo: o catálogo vindo da foto
    conta como vencido de qualquer jeito (`api.catalogo_vencido`), é o socorro da máquina nova.

    Levanta `FotoIncompleta` se mais de 1% das linhas não chega à raiz (o item sem pai) pela cadeia de pais; a foto de 22/09 não
    chega: ver o topo do módulo."""
    from ativos_central import montar_registros                    # aqui dentro: o ativos_central importa este módulo
    todas = [dict(l) for l in (linhas or ()) if isinstance(l, dict)]
    renovada = any("fora_do_fracttal_desde" in l for l in todas)
    rows = [r for r in todas if not r.get("fora_do_fracttal_desde")]
    if not rows:
        raise FotoIncompleta("a foto veio vazia")
    ultima = max(str(r.get("foto_em") or "") for r in rows)
    if not renovada:
        rows = [r for r in rows if str(r.get("foto_em") or "") == ultima]
    nos: dict = {}
    for r in rows:
        i = _int(r.get("fracttal_item_id"))
        if i is not None:
            nos.setdefault(i, (_int(r.get("pai_item_id")), r.get("descricao")))
    cam = caminhos(nos)
    sem_raiz = sum(1 for r in rows if _int(r.get("fracttal_item_id")) not in cam)
    if sem_raiz * 100 > len(rows) * ORFAOS_MAX_PCT:
        raise FotoIncompleta(
            "%d de %d linhas não chegam à raiz (o cliente) pela cadeia de pais: sem ele o caminho do ativo e o cliente não "
            "se montam, e inventá-los faria o Almoxarifado e o TESTE - PA aparecerem com nomes inventados"
            % (sem_raiz, len(rows)))
    cru = []
    for r in rows:
        i = _int(r.get("fracttal_item_id"))
        caminho = cam.get(i)
        if caminho is None:
            continue                                                 # o dado torto fica de fora (até 1%)
        cru.append({"id": i, "code": str(r.get("codigo") or ""), "description": str(r.get("descricao") or ""),
                    "id_parent": _int(r.get("pai_item_id")), "id_type_item": _int(r.get("id_type_item")),
                    "id_group_task": _int(r.get("id_group_task")), "parent_description": caminho})
    registros = montar_registros(cru)
    try:
        lido_em = datetime.fromisoformat(ultima[:10]).replace(tzinfo=_BRT).timestamp()
    except ValueError:
        lido_em = 0.0
    return registros, lido_em
