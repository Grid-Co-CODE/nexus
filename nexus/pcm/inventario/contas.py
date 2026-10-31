"""As contas do inventário do almoxarifado (Levi, 26/10/2026): o que cada peça contada vira antes de gravar no Fracttal.
Puro: dicts entram e dicts saem, sem rede, sem Flask, sem banco, sem arquivo. A leitura do livro, a tela do PCM, a
gravação e a curadoria chamam estas contas, e só estas, para o número não mudar de uma tela para a outra. Desenho:
`docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md`, seções 4.2 e 4.5.

O caso real por trás das regras: o livro das contagens volta da API TODO COMO TEXTO ("3,0", "" e "None" no lugar do vazio),
e a peça que nunca foi ligada ao almoxarifado no Fracttal não vem na leitura de estoque. Daí:

- **Em branco não é zero.** O vazio é "não contei" e a peça não é tocada (`nao_tocada`); só o 0 digitado na linha da
  própria peça é "zerar". Virar o vazio em 0 zeraria o estoque de uma peça que ninguém contou; pelo mesmo motivo, 0
  unidades achadas (ou 0 unidades de genérico confirmadas) que a curadoria atribui a uma peça em branco não a contam.
- **Saldo não informado não é saldo cheio.** A peça ligada com o saldo vazio no Fracttal vale 0 para a conta, mas contar 0
  nela é `sem_alteracao`, não `zerar` (zerar uma peça de saldo desconhecido). O `sistema` do lote continua None para a tela
  dizer "não informado" e para a conferência da gravação comparar igual com igual.
- **A peça fora da leitura de estoque** entra com `sistema` 0 e `ligada` falso: a gravação a liga antes de gravar.
- **O contado substitui o saldo** (inventário, não soma): "é a peça X" e o "cadastrar" somam as unidades achadas fora do
  catálogo ao contado de X NESSA contagem, e o total é o que substitui o saldo; o genérico identificado e confirmado tira
  as unidades do genérico e as põe no específico, para o estoque não ficar em dobro.
- **Contado negativo nunca mexe:** o App não manda, mas o livro é texto; a peça entra como não contada e `invalido`.
- **A avariada (30/10/2026, a aba Avariados do App)** chega aqui já resolvida pela `leitura.ler` (`avariados.resolver`): a
  que achou o `-AV` no catálogo é linha `item` do -AV (com a marca `_avariado_de`), e a que não achou segue `avariado`, pelo
  caminho do achado fora do catálogo (a decisão da curadoria a leva a uma peça). **A mesma contagem com o -AV contado direto
  E pela aba é `dobro`** (com `invalido` junto, o caminho do contado inválido: fora do lote até o PCM corrigir), porque somar
  contaria duas vezes a mesma peça.

A chave de uma linha é o "ID da linha" (a 14ª coluna do contrato, `nexus.dados.almoxarifado.COLUNAS_CONTAGENS`), único
dentro da contagem: a curadoria é `{id_da_linha: {"decisao", "id_item"}}`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ...dados import almoxarifado as A
from .estoque import instante

# As seis situações de uma peça no lote (a ordem dos grupos da confirmação). Só as três primeiras mexem no estoque; a
# `curadoria` é o que o PCM ainda precisa decidir (o genérico por identificar e o achado fora do catálogo) e não grava.
SITUACOES = ("para_cima", "para_baixo", "zerar", "sem_alteracao", "nao_tocada", "curadoria")
MEXEM = ("para_cima", "para_baixo", "zerar")

# Quanto tempo depois do "Contada em" uma contagem ainda se aprova. O desenho (4.2) previa 7 dias "enquanto não houver
# um jeito" de saber o que se moveu depois da contagem: o passo 0 achou esse jeito (o histórico do almoxarifado, o
# `mexidas_desde` do adaptador), e o conflito sai dele na gravação, peça a peça. O limite ficou só como TETO: o histórico
# a ler e a janela do livro do App (os outros livros também guardam 90 dias) crescem com ele. Contagem mais velha que isso
# o App já nem entrega, e o histórico até a data dela custaria muito da cota do Fracttal (200/min, de toda a empresa).
APROVAVEL_DIAS = 90
# Quanto o relógio do celular pode estar adiantado: o "Contada em" é a hora do celular, e a conferência de conflito olha
# o que se moveu DEPOIS dela. Relógio adiantado de dias esconderia todo movimento real do Fracttal.
RELOGIO_ADIANTADO = timedelta(hours=1)

# as decisões da curadoria do achado (o fora do catálogo e a avariada sem o -AV no catálogo, 30/10/2026)
DECISOES_DO_ACHADO = ("cadastrar", "e_a_peca", "descartar")

CASAS = 6               # a soma de decimais (0.1 + 0.2) não sobra como 0.30000000000000004 e vira "ajuste"
_TOLERANCIA = 1e-9
_NUNCA = datetime(1970, 1, 1, tzinfo=timezone.utc)      # a data que não se leu é a mais velha

_id, _txt = A._id, A._txt       # o ID do Fracttal como texto sem o ".0" que a API às vezes põe, e o texto aparado


def _limpo(n: float | None) -> float | None:
    """O número sem ruído de ponto flutuante e sem o -0.0."""
    return None if n is None else round(n, CASAS) + 0.0


def situacao(sistema: float | None, contado: float | None) -> str:
    """A situação de uma peça: o saldo do Fracttal (`sistema`; None é "não informado" e vale 0) contra o contado.
    Contado vazio é `nao_tocada`, nunca 0; `zerar` é o 0 digitado em peça com saldo. Contado negativo também é
    `nao_tocada`: gravar -3 como saldo estragaria o estoque. A `curadoria` não sai daqui (depende da decisão do PCM)."""
    c = A.contado(contado)
    if c is None or c < 0:
        return "nao_tocada"
    s = A.numero(sistema)
    s = 0.0 if s is None or not math.isfinite(s) else s
    if abs(c - s) <= _TOLERANCIA:
        return "sem_alteracao"
    if c > s:
        return "para_cima"
    return "zerar" if c <= _TOLERANCIA else "para_baixo"


# ── o contado efetivo ───────────────────────────────────────────────────────────────────────────────────────────────────
@dataclass
class _Lido:
    """O que as linhas da contagem dizem, peça a peça, já com as decisões da curadoria."""
    total: dict = field(default_factory=dict)       # id_item -> unidades contadas (None: ninguém contou)
    invalidos: set = field(default_factory=set)     # id_item com contado negativo em alguma linha
    pendentes: dict = field(default_factory=dict)   # id_item -> "ID da linha" do genérico ainda por identificar
    codigos: dict = field(default_factory=dict)     # id_item -> código (o da linha, ou o da decisão)
    achados: list = field(default_factory=list)     # (ID da linha, unidades, negativo) do fora do catálogo por decidir
    ordem: list = field(default_factory=list)       # ("peca", id_item) | ("achado", posição em `achados`), na ordem do livro
    dobros: set = field(default_factory=set)        # id_item do -AV contado direto E pela aba Avariados (também em `invalidos`)

    def peca(self, id_item: str, codigo=None) -> None:
        if id_item not in self.total:
            self.total[id_item] = None
            self.ordem.append(("peca", id_item))
        c = _txt(codigo)
        if c and id_item not in self.codigos:
            self.codigos[id_item] = c

    def somar(self, id_item: str, n: float | None, negativo: bool = False) -> None:
        """Soma as unidades à peça. O negativo não soma: contamina a peça (ela fica não contada). O vazio não conta."""
        if negativo:
            self.invalidos.add(id_item)
        elif n is not None:
            self.total[id_item] = (self.total.get(id_item) or 0.0) + n

    def achadas(self, destino: str, n: float | None, codigo=None) -> None:
        """As unidades achadas (de um achado decidido, ou de um genérico confirmado) que o PCM atribui à peça `destino`.
        Só valem se forem MAIS que 0: o 0 do técnico é "zerar" na linha da PRÓPRIA peça, e 0 unidades achadas dizem
        nada dela (caso: a peça 101 em branco, saldo 8, e um achado de 0 unidades decidido "é a peça 101" virava `zerar` e
        apagava 8 peças que ninguém contou). Peça só pela decisão, com 0 unidades, nem entra. O negativo contamina o
        destino, como em qualquer linha."""
        if n is None or n == 0:
            return
        self.peca(destino, codigo)
        self.somar(destino, n, n < 0)

    def efetivo(self) -> dict[str, float | None]:
        return {i: None if i in self.invalidos else _limpo(v) for i, v in self.total.items()}


def _unicas(linhas) -> list[dict]:
    """As linhas sem repetição. A fila offline do App reenvia a contagem quando não vê a resposta do servidor: a mesma
    (ID da contagem, ID da linha) é a MESMA peça contada, não duas (somar as duas dobraria a contagem; um achado
    repetido viraria duas pendências). Vale a última (o reenvio traz o que o técnico deixou na tela), na posição da
    primeira. Linha sem ID da linha não tem como ser reconhecida e nunca se junta a outra."""
    vistas: dict = {}
    for i, l in enumerate(linhas or []):
        if isinstance(l, dict):
            chave = _id(l.get("ID da linha"))
            vistas[(_id(l.get("ID da contagem")), chave) if chave else (None, i)] = l
    return list(vistas.values())


def _ler(linhas, curadoria) -> _Lido:
    """Uma passada pelas linhas da contagem (as do livro do App, como texto), na ordem em que vieram.

    - `item`: a peça vale o "Contado" da linha dela (linhas da mesma peça somam).
    - `identificar` (o genérico com saldo, uma linha por específico): as unidades contam no genérico, a não ser que o PCM
      tenha confirmado (`confirmar`, com o específico da decisão ou, sem ele, o "Identificado como" do técnico): aí saem
      do genérico e entram no específico. Sem a confirmação a peça fica por decidir (`pendentes`), a não ser que a linha
      esteja em branco: unidades que ninguém contou não têm o que decidir.
    - `fora_do_catalogo` (o achado sem peça): `e_a_peca` e `cadastrar` somam as unidades à peça da decisão; `descartar` as
      joga fora; sem decisão ficam por decidir (o achado em branco nem isso: não é pendência). A decisão que não é do tipo
      da linha não resolve nada: a linha segue pendente e nada é gravado por engano.
    - `avariado` (30/10/2026, a aba Avariados): a que a `leitura.ler` levou ao -AV chega como `item` com a marca
      `_avariado_de` e conta como a linha da própria peça; a que não achou o -AV segue o caminho do achado fora do catálogo
      (sem o ID da boa não é de peça nenhuma). A que já tem decisão da curadoria segue a decisão mesmo depois de se resolver
      (o -AV entrou no catálogo do App, criado por outra contagem): o "descartar" do PCM não some em silêncio. O -AV com
      número na linha direta E na da aba é `dobros` (e `invalidos`): somar contaria duas vezes a mesma peça.
    - Linha sem ID do item (nas duas primeiras) ou de um Tipo que não existe não é de peça nenhuma: não entra.
    - A mesma linha reenviada conta uma vez (`_unicas`)."""
    lido = _Lido()
    cur = {_id(k): v for k, v in (curadoria or {}).items() if isinstance(v, dict)}
    diretas, pela_aba = set(), set()            # o -AV com número na linha dele e na da aba Avariados
    for l in _unicas(linhas):
        tipo = _txt(l.get("Tipo")).lower()
        chave = _id(l.get("ID da linha"))
        n = A.contado(l.get("Contado"))
        negativo = n is not None and n < 0
        dec = (cur.get(chave) or {}) if chave else {}
        decisao, alvo = _txt(dec.get("decisao")), _id(dec.get("id_item"))
        da_aba = tipo == "item" and "_avariado_de" in l
        if da_aba and decisao in DECISOES_DO_ACHADO:
            tipo = "avariado"                   # decidida quando o -AV ainda não estava no catálogo: vale a decisão
        if tipo in ("item", "identificar"):
            id_item = _id(l.get("ID do item"))
            if not id_item:
                continue
            lido.peca(id_item, l.get("Código"))
            if tipo == "item":
                lido.somar(id_item, n, negativo)
                if n is not None:
                    (pela_aba if da_aba else diretas).add(id_item)
                continue
            destino = (alvo or _id(l.get("Identificado como"))) if decisao == "confirmar" else ""
            if not destino:
                lido.somar(id_item, n, negativo)
                if n is not None:                           # em branco não há o que decidir: o genérico só não foi contado
                    lido.pendentes.setdefault(id_item, []).append(chave)
            elif n is not None:
                if negativo:                                # unidades que não se sabe quantas são: nenhuma das duas vale
                    lido.somar(id_item, n, True)
                else:
                    lido.somar(id_item, 0.0)                # o genérico foi contado: o que achou menos o que saiu dele
                lido.achadas(destino, n)
        elif tipo in ("fora_do_catalogo", "avariado"):
            if tipo == "avariado" and not _id(l.get("ID do item")):
                continue                                    # a avariada sem o ID da boa não é de peça nenhuma
            if decisao in ("e_a_peca", "cadastrar") and alvo:
                lido.achadas(alvo, n, dec.get("codigo"))
            elif decisao != "descartar" and n is not None:
                lido.ordem.append(("achado", len(lido.achados)))
                lido.achados.append((chave, n, negativo))
    lido.dobros = diretas & pela_aba
    lido.invalidos |= lido.dobros
    return lido


def contado_efetivo(linhas: list[dict], curadoria: dict[str, dict]) -> dict[str, float | None]:
    """O número que cada peça da contagem vale, `{id_item: unidades | None}` (None: não contada ou contado inválido).

    `linhas`: as da contagem, do livro do App. `curadoria`: `{ID da linha: {"decisao": "e_a_peca" | "cadastrar" |
    "descartar" | "confirmar", "id_item": str}}`. Caso real: X contada 3 + 2 unidades achadas fora do catálogo que o PCM
    decidiu que são X = 5 (e X em branco + 2 achadas = 2): o total SUBSTITUI o saldo de X no Fracttal. O genérico com 4
    unidades identificadas e confirmadas como Y fica com 0 e Y ganha 4. Achadas em 0 não contam a peça de destino (X em
    branco continua em branco).

    ATENÇÃO, quem GRAVA não usa este número direto: o genérico com unidades ainda por identificar sai daqui como NÚMERO (as
    unidades dele, sem dono), e gravá-lo seria ajustar o estoque com unidades que talvez sejam de outra peça. A gravação
    parte do `itens_do_lote` e só leva `not tirada and situacao in MEXEM` (a `curadoria`, a `nao_tocada`, a `sem_alteracao`
    e a peça tirada pelo PCM ficam de fora)."""
    return _ler(linhas, curadoria).efetivo()


# ── o lote ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _entrada(*, id_item, codigo, sistema, campo, contado, ligada, sit, corrigido, tirada, invalido, pendentes,
             recontar=False, dobro=False) -> dict:
    return {"id_item": id_item, "codigo": codigo, "sistema": sistema, "contado": contado, "contado_campo": campo,
            "delta": None if contado is None else _limpo(contado - (sistema or 0.0)), "situacao": sit,
            "ligada": ligada, "corrigido": corrigido, "tirada": tirada, "invalido": invalido, "pendentes": pendentes,
            "recontar": recontar, "dobro": dobro}


def itens_do_lote(contagem: list[dict], sistema: dict[str, dict], curadoria: dict, revisao: dict) -> list[dict]:
    """O lote que o PCM revisa: uma entrada por peça da contagem, na ordem do livro.

    `contagem`: as linhas do App. `sistema`: o que o `Estoque.ler` devolveu (`{id_item: {"saldo", "codigo", ...}}`; a peça
    fora dele não está ligada ao almoxarifado). `curadoria`: ver `contado_efetivo`. `revisao`: `{"tiradas": {id_item:
    motivo}, "corrigidos": {id_item: número}, "recontar": {id_item: motivo}}` (a correção ilegível ou negativa não vale; a
    que vale também resolve a peça `invalido`: é o PCM, com o motivo na auditoria, dizendo o número).

    Cada entrada: `id_item`, `codigo`, `sistema` (o saldo do Fracttal; 0 se não ligada; None se o Fracttal não o disse),
    `contado_campo` (o número do campo já com a curadoria), `contado` (o que vai ao Fracttal: o do campo, ou o corrigido
    pelo PCM), `delta`, `situacao`, `ligada`, `corrigido`, `tirada` (fica de fora da gravação, mas guarda a situação que
    teria), `invalido`, `pendentes` (os "ID da linha" do genérico por identificar), `recontar` (a recontagem da peça foi
    pedida nesta contagem, 30/10/2026: ela vem `tirada` também, para todo caminho que já deixa a tirada de fora, a gravação
    e a assinatura do lote inclusive, deixar a recontada de fora sem conhecer a regra nova) e `dobro` (o -AV contado direto
    e pela aba Avariados, 30/10/2026: vem `invalido` também, e segue o caminho do contado inválido: fora do lote, e o número
    corrigido pelo PCM entra).

    A peça com genérico por identificar fica na `curadoria` (não grava: as unidades ainda não têm dono). O achado fora do
    catálogo por decidir é uma entrada à parte, sem `id_item` (""), na `curadoria` também, com a linha em `pendentes`
    (o achado em branco, sem número nenhum, não é pendência e não entra)."""
    lido = _ler(contagem, curadoria)
    efetivo = lido.efetivo()
    estoque = {_id(k): v for k, v in (sistema or {}).items() if isinstance(v, dict)}
    revisao = revisao or {}
    tiradas = {_id(k) for k in (revisao.get("tiradas") or {})}
    recontar = {_id(k) for k in (revisao.get("recontar") or {})}
    corrigidos = {_id(k): v for k, v in (revisao.get("corrigidos") or {}).items()}
    itens = []
    for tipo, ref in lido.ordem:
        if tipo == "achado":
            chave, n, negativo = lido.achados[ref]
            campo = None if negativo else _limpo(n)
            itens.append(_entrada(id_item="", codigo="", sistema=0.0, campo=campo, contado=campo, ligada=False,
                                  sit="curadoria", corrigido=False, tirada=False, invalido=negativo, pendentes=[chave]))
            continue
        id_item, campo = ref, efetivo[ref]
        no_estoque = estoque.get(id_item)
        ligada = no_estoque is not None
        saldo = A.numero(no_estoque.get("saldo")) if ligada else 0.0
        if saldo is not None and not math.isfinite(saldo):
            saldo = None                                    # "nan" e "inf" não são saldo: é "não informado", como o vazio
        contado, corrigido = campo, False
        if id_item in corrigidos:
            novo = A.contado(corrigidos[id_item])
            if novo is not None and novo >= 0:
                contado, corrigido = _limpo(novo), True
        pendentes = list(lido.pendentes.get(id_item, []))
        codigo = lido.codigos.get(id_item) or (_txt(no_estoque.get("codigo")) if ligada else "")
        itens.append(_entrada(id_item=id_item, codigo=codigo, sistema=saldo, campo=campo, contado=contado, ligada=ligada,
                              sit="curadoria" if pendentes else situacao(saldo, contado), corrigido=corrigido,
                              tirada=id_item in tiradas or id_item in recontar, invalido=id_item in lido.invalidos,
                              pendentes=pendentes, recontar=id_item in recontar, dobro=id_item in lido.dobros))
    return itens


# ── a substituição e a janela de aprovação ──────────────────────────────────────────────────────────────────────────────
def _quando(valor) -> datetime:
    try:
        return instante(valor)
    except ValueError:
        return _NUNCA


def substituidas(contagens: list[dict], gravadas: set[str]) -> set[str]:
    """Os `contagem_id` que a contagem mais nova do mesmo almoxarifado substitui. Por almoxarifado vale a mais nova pelo
    "Contada em" (o instante, não o texto: -03:00 e Z se comparam; empate: o "Enviada em", que a fila offline atrasa, e
    por fim o ID, para o resultado não depender da ordem da lista); as mais velhas que ainda não foram gravadas ficam
    substituídas, e não se aprovam mais: aprovar a velha depois da nova desfaria a nova. A velha já gravada (`gravadas`:
    os `contagem_id` com gravação feita ou começada) fica como está. Data ilegível é a mais velha: sem como ordenar, ela
    não pode ser a que vale. Contagem sem `contagem_id` ou sem `id_almox` não entra (sem o almoxarifado não há de quem
    ser a mais nova, e juntar todas num "almoxarifado vazio" faria uma substituir as outras sem motivo). Cada contagem:
    `contagem_id`, `id_almox`, `contada_em`, `enviada_em` e `recontagem_de` (vazio na contagem inteira).

    **A recontagem só das peças marcadas não substitui ninguém** (30/10/2026, item 4 das melhorias): ela traz só as peças
    que o PCM pediu, e como "a mais nova" tiraria do caminho a original inteira, cujas outras peças seguem para aprovar e
    gravar (o desenho chama isso de falha mesmo funcionando). A recontagem (`recontagem_de` preenchido) fica fora da escolha
    da nova, e a original, mais velha, também não a substitui: ela só fica velha quando uma contagem INTEIRA do mesmo
    almoxarifado é mais nova que ela (pela mesma chave), e a já gravada fica como está.

    Quem chama passa só as contagens VIVAS: nem a `recontagem pedida` (recusada pelo PCM) nem a `substituída` entram aqui.
    Uma recontagem pedida que contasse como "a mais nova" substituiria as boas anteriores sem ter número nenhum para
    gravar no lugar delas."""
    gravadas = {_txt(g) for g in (gravadas or ())}
    inteiras: dict[str, list] = {}
    recontagens: dict[str, list] = {}
    for c in contagens or []:
        cid, almox = _txt(c.get("contagem_id")), _id(c.get("id_almox"))
        if cid and almox:
            chave = (_quando(c.get("contada_em")), _quando(c.get("enviada_em")), cid)
            (recontagens if _txt(c.get("recontagem_de")) else inteiras).setdefault(almox, []).append((chave, cid))
    velhas: set[str] = set()
    for almox, lista in inteiras.items():
        nova = max(lista)
        velhas |= {cid for _, cid in lista if cid != nova[1] and cid not in gravadas}
        velhas |= {cid for chave, cid in recontagens.get(almox, []) if chave < nova[0] and cid not in gravadas}
    return velhas


def aprovavel(contada_em: str, agora: datetime, dias: int = APROVAVEL_DIAS) -> bool:
    """A contagem ainda se aprova: o "Contada em" tem no máximo `dias` (90, `APROVAVEL_DIAS`) e não é do futuro (além de
    `RELOGIO_ADIANTADO`). Data ilegível não se aprova: sem a data não há o que olhar depois dela. Sem fuso, é UTC (como o
    App grava), nas duas pontas."""
    try:
        contada, agora_ = instante(contada_em), instante(agora)
    except ValueError:
        return False
    return -RELOGIO_ADIANTADO <= agora_ - contada <= timedelta(days=dias)
