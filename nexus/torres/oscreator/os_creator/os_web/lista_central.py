# os_creator/os_web/lista_central.py
"""As telas do OS Creator lendo da lista central de OS (31/10/2026, tarefa 3.3 do canto central).

Levi, 30/10/2026: "A ideia é não ter um carregamento novo por atividade e sim um ecossistema onde as coisas se aproveitam e
não precisamos ficar fazendo novas requisições sempre!" (desenho `docs/superpowers/specs/2026-10-30-oscreator-canto-central-
design.md`, "Etapa 3"). A 3.1 e a 3.2 fizeram a lista UMA, de todas as OS (`os_creator/os_central.py`), e quem a enche no
servidor (`os_leitor.py`); daqui saem os atalhos das telas para ela: o Histórico e as visões (pelo `rotas.ler_lista`), o
Garantias (`rotas_acomp._linhas`), a marcação verde dos Ativos (`rotas.os_recentes`), o Investigar ativo (pelo índice por
código), o nº da OS → id (`api._wo_id_por_folio`) e a 1ª pintura do card; e as ações que criam ou mudam OS põem a OS nela
(`mudou`, `criadas`).

A lista é lida pela credencial da EMPRESA e vê TODAS as OS. As guardas (decisões AZ a BF da 3.3, os Rulings BP a BR da rodada 1,
o Ruling BU da rodada 2 e o BX da rodada 4 de correções, que fecharam os vazamentos para a visão restrita que as sondas das
revisões provaram):
- A 1ª BARREIRA É A GOVERNANÇA (Ruling BX): a lista só vale para quem o Nexus liberou (`liberada`: a marca que a ponte põe no
  pedido, `ponte.lista_central`: o administrador e os setores de `ponte.SETORES_COM_LISTA_CENTRAL`, mudados por commit). Sem a
  marca, fechado; quem não foi liberado segue pelo caminho de hoje em toda tela, sem conferência. Provar o conjunto por contagem
  teve buracos raros a cada rodada de sonda: a contagem abaixo é a 2ª barreira.
- A VISIBILIDADE DE CADA TELA NÃO MUDA (AZ, fail-closed). A tela que mostra as OS pela sessão da pessoa (a visão dela no
  Fracttal) só lê da lista depois da conferência DELA (`conferir`), que é UMA por pessoa e período, sem visão, status nem
  etiqueta (Ruling BU): o "Todos" do período da tela (no Garantias, os 365 dias que ele lê). As duas contas param na MARCA
  D'ÁGUA da lista (`os_central.Lista.marca`: toda OS criada antes dela está na lista): a da lista, pelo índice da criação; a da
  pessoa, pelo total que o Fracttal dá a ela no período (1 pedido, na sessão dela) menos as OS dela criadas na marca ou depois,
  que a página desse mesmo pedido traz (`CONFERE_LINHAS`, 200, pelo id da mais nova para trás: o `list_minhas_os_pagina` não
  aceita data e hora no "até", que ganha "T23:59:59"). Como toda OS de antes da marca está na lista, a pessoa só vê um pedaço
  do que a lista tem: as contas iguais (igualdade EXATA, sem folga) dizem que ela vê todas. A regra de uma mão da rodada 1
  comparava números: a sonda mostrou a pessoa com H OS escondidas empatando com X ≥ H OS novas que a lista ainda não lera, ou
  com a mudança de status ou de etiqueta não lida quando a conferência levava o filtro da tela. A visibilidade no Fracttal não
  depende de status nem de etiqueta: passou, a visão, o "criado por", as atribuídas, o status e a etiqueta são filtros DA
  LISTA. Quando a página não dá para saber (mais OS depois da marca do que ela traz, a criação fora da ordem do id, a página
  torta), a tela vai ao vivo; e toda OS da página de antes da marca tem de estar na lista (a criada antes e inserida no Fracttal
  depois da leitura, do App offline ou de uma importação, compensaria uma escondida sem tirar a página da ordem). Quem não
  passa vai ao vivo em TODAS as visões daquele período, e pelo caminho de hoje com a lista DELA, nunca a "Todos" dividida de
  19/10 (`cobre`, Ruling BU parte 2: quem vê tudo lê daqui e não ancora a dividida, e a 1ª restrita a achava vazia e a fazia
  dela; outra restrita com o mesmo total a herdava).
- O QUE A TELA MOSTRA É SÓ O QUE FOI PROVADO (`Prova`): as OS criadas antes da marca da conferência e as da página dela
  depois da marca (mais as que a ação dela leu na sessão dela, `_vistas`). A OS que entrou na lista depois da marca por outro
  caminho (a ação de outra pessoa, as abertas) só aparece a quem a página trouxe. A medida da pessoa fica 30 min por pessoa e
  período (`_MEDIDAS`) e é conferida de novo contra a lista a cada visita (sem pedido); ela é pedida de novo quando a lista
  muda debaixo dela (a conta não bate) ou quando a marca chegou a uma OS que a página dela não trouxe (a faixa das novas leu
  OS novas: quem as vê, vê). Quem divergiu com a lista tendo MAIS que ela (o sinal da visão restrita) não é conferido de novo
  por 30 min (`_DIVERGIU`, Minor 2 da rodada 2); a lista com MENOS (atrasada) não prende ninguém. A sessão sem e-mail ("?")
  nunca passa. A tela que já usava uma lista dividida entre todos (a marcação verde dos Ativos, `("cat", "os_recentes")`)
  segue dividida, sem conferência.
- O Nº → ID E A 1ª PINTURA DO CARD (Ruling BP, e o item 4 do BU): não têm filtro para conferir, e abrem uma OS qualquer pelo
  id. Só para quem passou na conferência do escopo fixo e grande, os 30 dias padrão até hoje, com pelo menos `LIBERA_MIN_OS`
  OS na lista até a marca (`liberado`), e só para a OS criada nesse escopo e ANTES da marca: a mais velha e a mais nova vão ao
  vivo, e o Fracttal decide. A sonda liberou a pessoa restrita por um período invertido, por um dia quieto (0 e 0), por um dia
  em que todas as OS eram dela e pelo Investigar fora dos 30 dias: nenhum desses libera.
- A GUARDA DA LISTA PELA METADE (BA, a decisão AI da 3.1): a mesma conferência. Cada uma que foi ao Fracttal conta no estado da
  lista, por tela (`os_central.anotar_conferencia`: quantas, quantas divergiram, falharam e não deram para saber, e a última
  divergência), e o Raio-X mostra: muitas divergências de quem tem a visão inteira é sinal de lista errada.
- OS CAMPOS QUE O REST NÃO TRAZ (BB, Ruling AT): a tela só lê da lista os campos que a última leitura do período inteiro
  trouxe (os 7 dias ou a noite: `os_central.campos_medidos`; a entrega das abertas não mexe na medida, rodada 3); com 0% (ou
  sem medida nenhuma) num campo que a tela MOSTRA ou FILTRA, ela vai ao vivo, ou
  aquele filtro troca de jeito (a etiqueta por id vira pelo nome). As listas de cada tela estão em `CAMPOS_*`; a nota do
  chamado, rara numa leitura qualquer, o Garantias confere nas OS dele (sem nenhuma nota entre as de etiqueta CHAMADOS, o
  REST não a trouxe), e a nota cortada no teto (`nota_cortada`, Ruling BR) também o leva ao vivo. O card completa ao vivo o
  que a lista não tem (subtarefas, anexos, OS pai, solicitação), como sempre.
- ONDE A LISTA NÃO COBRE (BC), tudo segue como hoje: o período inválido ou fora da janela lida inteira (`Lista.cobre`), a lista
  sem marca d'água, o `filtrar` que dá None (a pessoa que não se identifica, o homônimo), o PC sem leitor (a lista vazia).
  Nenhum caminho de hoje some.
- AS AÇÕES (BD): `mudou(id)` (o card, o Garantias) e `criadas(resultado)` (as telas de criar) põem a OS na lista DEPOIS de o
  Fracttal confirmar, lida pela sessão da pessoa (`os_central.atualizar_os`: as tarefas e o cabeçalho, 1 a 3 pedidos), só com a
  lista em uso, e com prazo (`RELEITURA_MAX_S`): passou dele, a resposta sai e a OS fica pendente para a faixa (a que nem
  começou sai da fila). A falha da lista nunca derruba a ação: vai ao log, e a próxima faixa traz a OS.
Nada daqui vai ao Fracttal além da conferência (e da leitura da OS que a ação mudou). Nunca levanta para a tela: sem a lista,
None, e a tela segue pelo caminho de hoje.
"""
from __future__ import annotations

import concurrent.futures as cf
import contextlib
import contextvars
import datetime as dt
import logging
import re
import threading
import time
import unicodedata
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

import api
import os_central
from flask import has_request_context, request
from os_registro import _s, _seg

from . import historico_store as HS
from . import sessao

log = logging.getLogger("oscreator.lista_central")

# os nomes dos campos medidos pela lista (`os_central._medir_campos`)
NO, CRIACAO, QUEM_CRIOU, COD_CRIADOR, RESP_ID = "nº", "criação", "quem criou", "código de quem criou", "responsável (id)"
TIPO, CODIGO, PROGRAMADA, GATILHO = "tipo da tarefa", "código do ativo", "programada", "gatilho"
ETQ_ID, ETQ, FIM, INICIO = "etiqueta com id", "com etiqueta", "data fim", "início"
DESCRICAO, ATIVO, EQUIPE, ATRIBUIDO, STATUS = "descrição", "ativo", "equipe", "atribuído a", "status"
# O QUE CADA TELA MOSTRA OU FILTRA (decisão BB): com 0% num destes, a tela vai ao vivo. O Histórico mostra o nº, o cliente, a
# usina e o tipo do ativo (pelo código), o ativo escrito, a descrição, o status, a criação (e filtra o período por ela), a data
# do evento (que cai na programada: Minor 4 da rodada 2), a data fim e a etiqueta, e filtra pelo tipo de tarefa (local); o
# Investigar ativo mostra o mesmo; a Visão COS mostra também o início, o gatilho, a equipe e quem criou; o Garantias, o
# responsável (o nome e o id, a cor da equipe) e a descrição; a prévia do card, o nº, o tipo, o status, o ativo, as datas,
# quem criou e com quem está.
CAMPOS_HISTORICO = (NO, CRIACAO, CODIGO, TIPO, ETQ, FIM, PROGRAMADA, DESCRICAO, ATIVO, STATUS)
CAMPOS_COS = CAMPOS_HISTORICO + (INICIO, GATILHO, QUEM_CRIOU, EQUIPE)
CAMPOS_GARANTIAS = (NO, CRIACAO, CODIGO, TIPO, ETQ, FIM, RESP_ID, ATRIBUIDO, DESCRICAO, STATUS)
CAMPOS_ATIVOS = (CRIACAO, CODIGO)
CAMPOS_PREVIA = (NO, CRIACAO, DESCRICAO, ATIVO, STATUS, FIM, ATRIBUIDO, QUEM_CRIOU, TIPO)
ETIQUETA_CHAMADOS = "CHAMADOS"             # o Garantias filtra pelo nome (o id custaria o catálogo de etiquetas, e não é guardado)
TELA_HISTORICO, TELA_GARANTIAS, TELA_INVESTIGAR = "histórico", "garantias", "investigar"   # o rótulo no estado (Raio-X)
CONFERE_LINHAS = 200                       # a página da conferência (as OS da pessoa depois da marca d'água têm de caber nela):
                                           # do tamanho das do `list_minhas_os`; era 50 até a rodada 4 (a sonda Q)
LIBERACAO = "os_web.lista_central"         # a marca que o Nexus põe no pedido: a pessoa foi liberada (`ponte.lista_central`)
ESCOPO_DIAS = 30                           # o escopo que libera o nº → id e a 1ª pintura: os 30 dias padrão do Histórico
LIBERA_MIN_OS = 20                         # ... com pelo menos tantas OS na lista (o período quieto não diz que a pessoa vê tudo)
LIBERA_S = HS.CONFERE_S                    # a medida da pessoa vale isto (o nº → id e a 1ª pintura também)
DIVERGIU_S = HS.CONFERE_S                  # quem divergiu (a lista com mais) não é conferido de novo por isto
GUARDADAS_MAX = 4000                       # as medidas e as divergências guardadas (as mais velhas saem antes)
VISOES_GUARDADAS = 8                       # as visões prontas (as linhas e o HTML), da versão de agora da lista
CRIADAS_NA_HORA = 3                        # as OS criadas lidas dentro do pedido; as outras, a faixa das novas traz (até 3 min)
RELEITURA_MAX_S = 5.0                      # o prazo da releitura da OS depois da ação, além da gravação (Minor 2 da rodada 1)

_TRAVA = threading.Lock()
_LIBERADOS: dict = {}                      # {pessoa: (quando foi medida, de, até, a marca, a conta da lista)} do escopo
_APROVADAS: dict = {}                      # {(pessoa, de, até): quando foi medida a conferência que passou} ("Todos" dividida)
_LIBERADA = contextvars.ContextVar("os_web_lista_central", default=False)   # a marca do pedido, numa thread sem o pedido
_DIVERGIU: dict = {}                       # {(pessoa, de, até): quando a lista teve mais que ela, numa medida pedida agora}
_MEDIDAS: dict = {}                        # {(pessoa, de, até): a `Medida` do lado dela, pedida na sessão dela}
_VISOES: OrderedDict = OrderedDict()       # {chave: (o catálogo da linha, VisaoCentral)}, as mais usadas por último
_RELEITURAS: set = set()                   # as releituras de ações em curso (`esperar_releituras`)
_EXECUTOR: dict = {"ex": None}             # as releituras correm aqui, com o contexto da sessão copiado (nasce no 1º uso)


def limpar() -> None:
    """Esquece quem está liberado, as medidas, as divergências e as visões prontas (os testes; o processo novo começa assim)."""
    with _TRAVA:
        _LIBERADOS.clear()
        _APROVADAS.clear()
        _DIVERGIU.clear()
        _MEDIDAS.clear()
        _VISOES.clear()


# ── a 1ª barreira: a governança (Ruling BX, rodada 4) ──────────────────────────────────────────────────────────────────
def liberada() -> bool:
    """A pessoa do pedido foi liberada para a lista central pelo Nexus: a marca do pedido (`request.environ[LIBERACAO]`, que
    a ponte põe: o administrador e os setores de `ponte.SETORES_COM_LISTA_CENTRAL`) ou, numa thread que não leva o pedido, a
    que quem a abriu passou (`liberacao`). Sem a marca (o OS Creator servido sozinho, o PC, os testes, a ponte que não
    disse): não. Nenhuma tela lê da lista sem ela, nem a 1ª pintura nem o nº → id, mesmo passando na contagem."""
    try:
        if has_request_context():
            return request.environ.get(LIBERACAO) is True
    except Exception:                                                # noqa: BLE001 — sem saber, fecha
        return False
    return _LIBERADA.get() is True


@contextlib.contextmanager
def liberacao(valor: bool):
    """A marca do pedido levada a uma thread que não leva o pedido (a releitura do quadro de Garantias por trás)."""
    token = _LIBERADA.set(bool(valor))
    try:
        yield
    finally:
        _LIBERADA.reset(token)


def _int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError, OverflowError):
        return None


def _norm(v) -> str:
    s = unicodedata.normalize("NFKD", str(v or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def quem() -> str:
    """A pessoa do pedido (ou da thread que leva a sessão dela): o e-mail da conta, senão o do JWT. É a mesma régua do
    `rotas._quem` (o e-mail da conta entra no contexto da sessão em todo pedido do OS Creator)."""
    return sessao.email_atual() or sessao.email_do_jwt(sessao.jwt_atual() or "") or "?"


_DATA = re.compile(r"\d{4}-\d{2}-\d{2}")


def periodo_valido(de, ate) -> bool:
    """O período da tela é de duas datas 'AAAA-MM-DD' com o início até o fim (Ruling BP): o invertido dava 0 OS na lista e 0
    no Fracttal, e a conferência "batia"."""
    if not (de and ate and _DATA.fullmatch(str(de)) and _DATA.fullmatch(str(ate))):
        return False
    try:
        return dt.date.fromisoformat(str(de)) <= dt.date.fromisoformat(str(ate))
    except ValueError:
        return False


def cobre(de, ate) -> bool:
    """A lista central responde por este período (válido e dentro da janela lida inteira, `Lista.cobre`)? Então quem não passou
    na conferência segue pelo caminho de hoje com a lista DELA, nunca com a "Todos" dividida de 19/10 (Ruling BU, parte 2: quem
    vê tudo lê da lista central e não ancora a dividida; a 1ª pessoa restrita a achava vazia, e a lista dela virava a de todos,
    herdada por outra restrita com o mesmo total). Na dúvida (a lista quebrou), sim: a lista dela custa pedidos, a dividida
    pode mostrar o que o Fracttal esconde."""
    try:
        return periodo_valido(de, ate) and os_central.atual().cobre(de, ate)
    except Exception:                                                # noqa: BLE001 — na dúvida, a lista de cada pessoa
        log.exception("lista central de OS: não deu para saber se a lista cobre o período; cada pessoa segue com a dela")
        return True


def em_uso(de=None) -> bool:
    """A lista central está EM USO para um período que começa em `de` ('AAAA-MM-DD'): o servidor já leu uma janela inteira dela
    (pela cópia em disco ou pelas faixas) e essa janela começa no dia `de` ou antes (`janela[0] <= de`, o mesmo teste do
    `Lista.cobre`). Sem `de` (as ações, que não têm período), o começo do período padrão do Histórico, os `ESCOPO_DIAS`
    até hoje. A lista fora de uso é a do PC, a recém-subida sem cópia e a de uma janela que nunca serve o período.

    Antes (revisão final, 31/10/2026) valia QUALQUER janela lida. No dia do deploy a 1ª leitura são os 7 dias, que abrem uma
    janela de 7 dias; o Histórico de 30 dias nunca é servido por ela, e a lista "em uso" mandava cada pessoa que não passou na
    conferência (ninguém passa: o período não é coberto) para a lista DELA, uns 26 pedidos cada, em vez de dividir a "Todos"
    como em 19/10. A ação (`mudou`, `pendente`, `criadas`) também lia a OS (1 a 3 pedidos) para uma lista que nenhuma tela
    padrão lia. Agora o período que a janela não alcança segue a regra de 19/10, e a de cada um com a dela (Ruling BX) vale só
    onde a lista cobre."""
    jde = os_central.atual().janela[0]
    if not jde:
        return False
    if de is None:
        de = (dt.date.today() - dt.timedelta(days=ESCOPO_DIAS)).isoformat()
    return str(de)[:10] >= jde


def _escopo_padrao(de, ate) -> bool:
    """[de, ate] é o escopo fixo que libera (Ruling BP): os 30 dias padrão do Histórico até hoje, as mesmas datas que a rota
    põe quando a pessoa não escolhe outras."""
    hoje = dt.date.today()
    return str(de) == (hoje - dt.timedelta(days=ESCOPO_DIAS)).isoformat() and str(ate) == hoje.isoformat()


# ── as guardas ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _medidos(campos, nomes) -> bool:
    """Todos os `nomes` vieram na última leitura do período inteiro (mais que 0%). Sem medida nenhuma, não: ao vivo."""
    pct = (campos or {}).get("pct") or {}
    return all((pct.get(n) or 0) > 0 for n in nomes)


def _escopo_liberado(pessoa):
    """(de, até, a marca d'água em segundos, a conta da lista no escopo antes dela) do escopo que a conferência liberou para a
    pessoa, medido há menos de `LIBERA_S`, ou None."""
    if not pessoa or pessoa == "?":
        return None
    with _TRAVA:
        v = _LIBERADOS.get(pessoa)
    if v is None or HS._relogio() - v[0] >= LIBERA_S:
        return None
    return v[1], v[2], v[3], v[4]


def liberado(pessoa) -> bool:
    """A pessoa passou na conferência do escopo fixo (Ruling BP) há menos de `LIBERA_S`: ela vê no Fracttal o que a lista vê
    nesses 30 dias até a marca d'água, e o nº → id e a 1ª pintura do card de uma OS criada neles podem vir da lista."""
    return _escopo_liberado(pessoa) is not None


def _no_escopo(pessoa, r, lista=None) -> bool:
    """A OS foi criada dentro do escopo que liberou a pessoa e ANTES da marca d'água da conferência (a data de criação, em UTC,
    como o `filtrar`), e a lista tem no escopo antes da marca a MESMA conta de quando a liberou (a sonda U1: a OS de 3 dias que
    entrou no Fracttal depois, escondida da pessoa, chegou pelos 7 dias e saía na 1ª pintura): a de depois, ou com a lista
    mudada, vai ao vivo, e o Fracttal decide."""
    esc = _escopo_liberado(pessoa)
    if esc is None or r is None or not (esc[0] <= r.data[:10] <= esc[1] and 0 < _s(r) < esc[2]):
        return False
    lista = os_central.atual() if lista is None else lista
    de_s, ate_s = os_central.periodo_em_segundos(esc[0], esc[1])
    return os_central.contar_criadas(lista, de_s, min(ate_s, esc[2] - 1)) == esc[3]


class Medida(NamedTuple):
    """O lado da pessoa na conferência do período (Ruling BU), pedido na sessão dela: `quando` (o relógio do 19/10, antes do
    pedido), `marca` (a marca d'água da lista no pedido, em segundos), `antes` (as OS que o Fracttal dá a ela no período criadas
    antes da marca; None quando a página não deu para saber), `depois` (os ids das dela criadas na marca ou depois, da página,
    mais as que a ação dela leu na sessão dela), `motivo` (por que não deu para saber), `vistas_antes` (os ids da página
    criados antes da marca: a lista tem de ter todos), `id_min` e `inteira` (o menor id da página, e se ela trouxe todas as OS
    da pessoa no período) e `lista_n` (a conta da lista no período antes da marca quando a medida foi pedida: a lista que
    muda depois tira a prova da medida, a sonda S2)."""
    quando: float
    marca: int
    antes: int | None
    depois: frozenset
    motivo: str = ""
    vistas_antes: frozenset = frozenset()
    id_min: int | None = None
    inteira: bool = True
    lista_n: int | None = None


class Prova(NamedTuple):
    """O que a conferência provou que a pessoa vê no período: as OS criadas antes de `marca` (segundos) e as de `depois`."""
    marca: int
    depois: frozenset

    def serve(self, r) -> bool:
        """A OS pode aparecer para ela (só as do período conferido chegam aqui)."""
        return r is not None and (0 < _s(r) < self.marca or r.id in self.depois)

    def chave(self, registros) -> tuple:
        """O que separa a visão pronta de quem tem outra prova: a marca e as OS de depois dela que entraram."""
        return self.marca, tuple(sorted(r.id for r in registros if _s(r) >= self.marca))


def _medir(de, ate, marca: int) -> Medida:
    """O lado da pessoa: 1 pedido na sessão dela, o "Todos" do período sem filtro nenhum, com a página das `CONFERE_LINHAS` mais
    novas pelo id. As da página criadas na marca ou depois saem do total (`depois`); a página tem de vir da criação mais nova
    para trás (o id do Fracttal cresce com a criação: a OS de id alto criada antes, fora dessa ordem, deixa a conta sem prova) e
    tem de chegar a uma OS de antes da marca, ou trazer todas. Senão, `antes` None: não deu para saber. As da página de antes da
    marca ficam em `vistas_antes` (o `_veredito` confere que a lista tem todas). O erro do Fracttal sobe."""
    quando = HS._relogio()
    r = api.list_minhas_os_pagina("criadas", "TODOS", None, de, ate, None, "", 1, CONFERE_LINHAS) or {}
    total = _int(r.get("total")) or 0
    linhas = list(r.get("linhas") or ())
    datas = [_seg(l.get("data")) for l in linhas]
    ids = [_int(l.get("id")) for l in linhas]
    if not all(datas) or None in ids or len(set(ids)) != len(ids) or total < len(linhas):
        return Medida(quando, marca, None, frozenset(), "a página veio sem a criação ou o id de uma OS, ou maior que o total")
    if any(b > a for a, b in zip(datas, datas[1:])):
        return Medida(quando, marca, None, frozenset(), "a página não veio da criação mais nova para trás")
    depois = frozenset(i for i, s in zip(ids, datas) if s >= marca)
    if len(depois) == len(linhas) and total > len(linhas):
        return Medida(quando, marca, None, frozenset(), "mais OS depois da marca d'água do que a página traz")
    return Medida(quando, marca, total - len(depois), depois,
                  vistas_antes=frozenset(i for i, s in zip(ids, datas) if s < marca), id_min=min(ids) if ids else None,
                  inteira=total <= len(linhas))


def _veredito(m: Medida, lista, de_s: int, ate_s: int, marca: int) -> tuple:
    """(passou, as OS da lista no período antes da marca da medida, medir de novo) da medida contra a lista de AGORA, sem
    pedido. Passa com a conta exata (a lista tem tudo de antes da marca; a pessoa, um pedaço: igual, ela vê tudo) e com a lista
    tendo cada OS da página de antes da marca: a OS que entrou no Fracttal depois da leitura com a criação antiga (o App
    offline, a importação) a lista não tem, e ela compensaria uma escondida sem tirar a página da ordem (o teste da OS antiga).
    Mede de novo: a medida sem resposta quando a marca andou; a que não bate (a lista mudou debaixo dela, ou a pessoa); a
    medida de quando a lista tinha outra conta (`lista_n`: a OS que a pessoa via, apagada e tirada pela noite, empatava a conta
    com a escondida dela, a sonda S2); a que bate, quando a marca chegou a uma OS da lista que a página dela não trouxe (a
    faixa leu OS novas: quem as vê, vê). Não dá para saber, e não adianta medir de novo com a mesma marca, quando a página não
    trouxe todas e a lista tem uma OS do período depois da marca com o id abaixo do menor dela (a criação fora da ordem do id:
    a OS do App offline com o relógio adiantado, a sonda R1; a pessoa a conta, e a página não a traz)."""
    if m.marca > marca:
        return False, None, True                                     # a lista voltou atrás (o reinício): a medida não vale
    if m.antes is None:
        return False, None, m.marca != marca
    lc = os_central.contar_criadas(lista, de_s, min(ate_s, m.marca - 1))
    if lc != m.lista_n:
        return False, lc, True
    if lc != m.antes or any(i not in lista.por_id for i in m.vistas_antes):
        return False, lc, True
    if not m.inteira and m.id_min is not None and any(
            r.id < m.id_min for r in os_central.criadas_entre(lista, max(de_s, m.marca), ate_s)):
        return False, lc, m.marca != marca
    novas = any(r.id not in m.depois for r in os_central.criadas_entre(lista, max(de_s, m.marca), min(ate_s, marca)))
    return True, lc, novas


def _guardar(k, m: Medida) -> None:
    with _TRAVA:
        _MEDIDAS[k] = m
        if len(_MEDIDAS) > GUARDADAS_MAX:
            for x in sorted(_MEDIDAS, key=lambda c: _MEDIDAS[c].quando)[:len(_MEDIDAS) - GUARDADAS_MAX]:
                _MEDIDAS.pop(x, None)


def _vistas(pessoa, ids) -> None:
    """As OS que a ação da pessoa acabou de ler NA SESSÃO DELA (o Fracttal as mostrou a ela) entram no `depois` das medidas
    dela: a OS que ela criou aparece no Histórico na hora, sem esperar a faixa nem pedir de novo (decisão BD)."""
    ids = frozenset(i for i in (_int(x) for x in ids or ()) if i is not None)
    if not ids or not pessoa or pessoa == "?":
        return
    with _TRAVA:
        for k, m in list(_MEDIDAS.items()):
            if k[0] == pessoa and m.antes is not None:
                _MEDIDAS[k] = m._replace(depois=m.depois | ids)


def _medir_ou_none(de, ate, marca, tela):
    try:
        return _medir(de, ate, marca)
    except Exception as e:                                           # noqa: BLE001 — sem conferir, a tela segue como hoje
        os_central.anotar_conferencia(tela, None)
        log.info("lista central de OS: a conferência do %s falhou (%s); a tela segue ao vivo", tela, type(e).__name__)
        return None


def _com_a_lista(m, lista, de_s, ate_s):
    """A medida com a conta da lista no período antes da marca dela, de quando foi pedida (`Medida.lista_n`)."""
    if m is None or m.antes is None:
        return m
    return m._replace(lista_n=os_central.contar_criadas(lista, de_s, min(ate_s, m.marca - 1)))


def aprovada(pessoa, de, ate) -> bool:
    """A pessoa passou na conferência deste período, medida há menos de `LIBERA_S` (a "Todos" dividida de 19/10 com a lista
    em uso, `divide_a_todos`)."""
    if not pessoa or pessoa == "?":
        return False
    with _TRAVA:
        q = _APROVADAS.get((pessoa, str(de), str(ate)))
    return q is not None and HS._relogio() - q < LIBERA_S


def divide_a_todos(pessoa, de, ate) -> bool:
    """A "Todos" dividida de 19/10 do caminho de hoje (`rotas.ler_lista`) vale para esta pessoa? Sem a lista central em uso PARA O
    PERÍODO (`em_uso(de)`: o PC, a lista vazia, a janela que começa depois do `de`, como a de 7 dias do dia do deploy): sim, a
    regra de 19/10 como sempre. Com ela em uso, coberta ou VENCIDA, só para quem tem uma conferência aprovada recente do período
    (Ruling BX, a sonda T3): quem vê tudo lê da lista e não a ancora; a lista vencida (a última leitura até o topo passou dos 30
    min) devolvia a dividida vazia à 1ª pessoa restrita, e outra com o mesmo total a herdava. Os outros seguem com a lista deles.
    Na dúvida (a lista quebrou), não."""
    try:
        if not em_uso(de):
            return True
        return aprovada(pessoa, de, ate)
    except Exception:                                                # noqa: BLE001 — na dúvida, a lista de cada pessoa
        log.exception("lista central de OS: não deu para saber se a \"Todos\" dividida vale; cada pessoa segue com a dela")
        return False


def conferir(pessoa, de, ate, tela: str, *, forcar: bool = False, libera: bool = False) -> Prova | None:
    """A conferência da pessoa no período [de, ate] (Ruling BU; ver o topo): a `Prova` do que ela vê, ou None (a tela vai ao
    vivo). A medida dela (`_medir`, 1 pedido) fica 30 min e é conferida contra a lista de agora a cada visita (`_veredito`); o
    ↻ (`forcar`) mede sempre. A que falha (o Fracttal fora, a sessão caída) não passa, e a medida guardada que provava segue
    provando (a lista só mostra menos sem ela). Só a que foi ao Fracttal conta no estado da lista. `libera`: esta é a
    conferência do escopo fixo (`_escopo_padrao`): passou com pelo menos `LIBERA_MIN_OS` OS, libera o nº → id e a 1ª pintura;
    não passou, fecha o atalho."""
    if not pessoa or pessoa == "?":
        return None                                                  # a sessão sem e-mail nunca passa (Minor 6 da rodada 2)
    lista = os_central.atual()
    marca = _seg(lista.marca) if lista.marca else 0
    if not marca:
        return None                                                  # sem leitura até o topo ainda: nada a provar
    de_s, ate_s = os_central.periodo_em_segundos(de, ate)
    k = (pessoa, str(de), str(ate))
    agora = HS._relogio()
    with _TRAVA:
        m = None if forcar else _MEDIDAS.get(k)
        q = _DIVERGIU.get(k)
    if m is not None and agora - m.quando >= LIBERA_S:
        m = None
    divergiu_ha_pouco = not forcar and q is not None and agora - q < DIVERGIU_S
    pedido = False
    if m is None:
        m = _com_a_lista(_medir_ou_none(de, ate, marca, tela), lista, de_s, ate_s)
        if m is None:
            return None
        pedido = True
    ok, lc, de_novo = _veredito(m, lista, de_s, ate_s, marca)
    if de_novo and not pedido and (ok or not divergiu_ha_pouco):
        nova = _com_a_lista(_medir_ou_none(de, ate, marca, tela), lista, de_s, ate_s)
        if nova is not None:
            m, pedido = nova, True
            ok, lc, _ = _veredito(m, lista, de_s, ate_s, marca)
    if pedido:
        _guardar(k, m)
        if m.antes is None:
            os_central.anotar_conferencia(tela, None, incerta=True)
            log.info("lista central de OS: a conferência do %s não deu para saber (%s); a tela segue ao vivo", tela,
                     m.motivo)
        else:
            os_central.anotar_conferencia(tela, ok, fracttal=m.antes, lista=lc)
    with _TRAVA:
        if ok:
            _DIVERGIU.pop(k, None)
            _APROVADAS[k] = m.quando
            if len(_APROVADAS) > GUARDADAS_MAX:
                for x in sorted(_APROVADAS, key=_APROVADAS.get)[:len(_APROVADAS) - GUARDADAS_MAX]:
                    _APROVADAS.pop(x, None)
        else:
            _APROVADAS.pop(k, None)
        if not ok and pedido and lc is not None and m.antes is not None and lc > m.antes:
            _DIVERGIU[k] = agora                                     # a lista com MAIS que ela: a visão restrita
            if len(_DIVERGIU) > GUARDADAS_MAX:
                for x in sorted(_DIVERGIU, key=_DIVERGIU.get)[:len(_DIVERGIU) - GUARDADAS_MAX]:
                    _DIVERGIU.pop(x, None)
        if libera:
            if ok and lc >= LIBERA_MIN_OS:
                _LIBERADOS[pessoa] = (m.quando, str(de), str(ate), m.marca, lc)
                if len(_LIBERADOS) > GUARDADAS_MAX // 2:
                    for x in sorted(_LIBERADOS, key=lambda p: _LIBERADOS[p][0])[:len(_LIBERADOS) - GUARDADAS_MAX // 2]:
                        _LIBERADOS.pop(x, None)
            else:
                _LIBERADOS.pop(pessoa, None)                         # a visão dela mudou: o atalho fecha na hora
    return Prova(m.marca, m.depois) if ok else None


# ── a visão pronta do Histórico ────────────────────────────────────────────────────────────────────────────────────────
class VisaoCentral:
    """Uma visão do Histórico lida da lista central, no feitio da `historico_store.Lista` (as linhas no formato do
    `api.list_minhas_os`, o `info` com o total e o teto, a hora da lista e o HTML das linhas guardado por versão): a rota e o
    template não precisam saber de onde ela veio. As linhas são de quem a montou (dicionários novos, `RegistroOS.linha`), e a
    visão é a mesma para quem pede o mesmo com a mesma prova (as pessoas conferidas de "Todos" dividem a mesma). A hora ("Lista
    das HH:MM") é a da última leitura do Fracttal que a lista teve, enquanto a versão dela for esta: a leitura que não trouxe
    nada não muda a versão, e a visão não é montada de novo por isso (Minor 5 da rodada 1)."""
    central = True

    def __init__(self, linhas, info, lido_em, versao):
        self.linhas, self.info, self.versao = linhas, dict(info), versao
        self._lido_em = float(lido_em or time.time())
        self.html: dict = {}
        self.preparada = False

    @property
    def criada_em(self) -> float:
        agora = os_central.atual()
        return float(agora.lido_em) if agora.versao == self.versao and agora.lido_em else self._lido_em


def _linhas(lista, registros, local) -> list:
    """As linhas da tela, com a marca das "a conferir" (uma faixa deveria tê-las trazido e não trouxe: o status pode ser velho;
    a tela diz e o card lê ao vivo)."""
    out = []
    for r in registros:
        d = r.linha(local)
        if lista.conferir(r.id):
            d["_a_conferir"] = True
        out.append(d)
    return out


def _visao_pronta(lista, chave, registros, local, cap) -> VisaoCentral:
    """A visão desta versão da lista para esta chave, montada uma vez: as `cap` mais novas (o teto do Histórico, o mesmo de
    sempre: a tela não muda) viram linhas; o total diz quantas o período tem (o aviso do teto). Ficam só as visões da versão
    de AGORA (da lista e do catálogo de ativos), no máximo `VISOES_GUARDADAS`: a de uma versão velha nunca mais é pedida, e
    cada uma são até 2.000 linhas e o HTML delas (o servidor anda apertado de memória)."""
    geracao = (lista.versao, id(local))
    k = geracao + tuple(chave)
    with _TRAVA:
        v = _VISOES.get(k)
        if v is not None and v[0] is local:
            _VISOES.move_to_end(k)
            return v[1]
    corte = registros[:cap] if cap else registros
    visao = VisaoCentral(_linhas(lista, corte, local), {"total": len(registros), "cap": cap}, lista.lido_em, lista.versao)
    with _TRAVA:
        for velha in [x for x in _VISOES if x[:2] != geracao]:
            _VISOES.pop(velha, None)
        _VISOES[k] = (local, visao)                                  # o catálogo fica preso à entrada: o id não se repete
        while len(_VISOES) > VISOES_GUARDADAS:
            _VISOES.popitem(last=False)
    return visao


def _pessoa_da_visao(modo_srv, id_account, pessoal, contas):
    """(a visão da lista, a pessoa dela) do filtro do Histórico, ou None quando a lista não sabe quem é. "Criado por: Todos"
    é a visão "todos"; "criadas por mim", a conta, o código no pessoal (pelo id da pessoa) e o nome de quem está logado;
    "Criado por" outra pessoa, a conta e o nome dela (o código pelo nome, só quando um só do pessoal o tem); "atribuídas a mim",
    o id da pessoa. O que casa sem ambiguidade a lista decide (`os_central.filtrar`); a conferência prova o conjunto."""
    if modo_srv == "atribuidas":
        idp = api._current_user_info()[0]
        return ("atribuidas", {"id_personnel": idp}) if idp is not None else None
    if id_account == "TODOS":
        return "todos", None
    if id_account is None:
        idp, ida, nome = api._current_user_info()
        if ida is None and not nome:
            return None
        cod = next((str(p.get("code") or "") for p in (pessoal() if pessoal else ())
                    if idp is not None and p.get("id_personnel") == idp), "")
        return "criadas", {"id_account": ida, "codigo": cod, "nome": nome}
    ida = _int(id_account)
    nome = next((str(c.get("nome") or "") for c in (contas() if contas else ()) if _int(c.get("id_account")) == ida), "")
    mesmos = [p for p in (pessoal() if pessoal and nome else ()) if _norm(p.get("name")) == _norm(nome)]
    cod = str(mesmos[0].get("code") or "") if len(mesmos) == 1 else ""
    return "criadas", {"id_account": ida, "codigo": cod, "nome": nome}


def _etiqueta(id_label, campos, etiquetas):
    """O filtro de etiqueta na lista: o id, quando a leitura grande trouxe o id das etiquetas; senão o nome (do catálogo de
    etiquetas), quando ela trouxe ao menos o nome. (False, ...) quando a lista não sabe filtrar: a tela vai ao vivo."""
    if not id_label:
        return True, None
    if _medidos(campos, (ETQ_ID,)):
        return True, int(id_label)
    if not _medidos(campos, (ETQ,)) or etiquetas is None:
        return False, None
    nome = next((str(e.get("description") or "") for e in (etiquetas() or ()) if _int(e.get("id")) == _int(id_label)), "")
    return (True, nome) if nome.strip() else (False, None)


def historico(modo_srv, id_account, id_label, de, ate, status_ids, *, pessoa, forcar=False, cos=False, pessoal=None,
              contas=None, etiquetas=None, cap=None):
    """A visão do Histórico (e das visões dele) pela lista central, ou None: o caminho de hoje. Os filtros são os da rota (os
    mesmos do `api.list_minhas_os`); `pessoa`, quem está pedindo (`rotas._quem`); `cos`, a Visão COS (mostra mais campos);
    `pessoal`, `contas` e `etiquetas`, os catálogos da rota (guardados lá: sem pedido a mais na maioria das vezes). A ordem:
    o período é válido e a lista o cobre, tem os campos da tela, sabe quem é a pessoa e responde (`filtrar`); só então a
    conferência do período (a mesma para toda visão e filtro: 1 pedido na 1ª vez), e só com ela a lista vale, e só para o que
    ela provou. A dos 30 dias padrão, com pelo menos `LIBERA_MIN_OS` OS, libera o nº → id. Antes de tudo, a pessoa tem de ter
    sido liberada pelo Nexus (`liberada`)."""
    try:
        if not liberada() or not periodo_valido(de, ate):
            return None
        lista = os_central.atual()
        if not lista.cobre(de, ate):
            return None
        campos = os_central.campos_medidos()
        if not _medidos(campos, CAMPOS_COS if cos else CAMPOS_HISTORICO):
            return None
        quem_e = _pessoa_da_visao(modo_srv, id_account, pessoal, contas)
        if quem_e is None:
            return None
        visao, pessoa_lista = quem_e
        if visao == "atribuidas" and not _medidos(campos, (RESP_ID,)):
            return None
        if visao == "criadas" and not (_medidos(campos, (QUEM_CRIOU,)) or _medidos(campos, (COD_CRIADOR,))):
            return None
        sabe, etq = _etiqueta(id_label, campos, etiquetas)
        if not sabe:
            return None
        sel = os_central.filtrar(visao, pessoa_lista, de, ate, etiqueta=etq, status=status_ids)
        if sel is None:
            return None
        prova = conferir(pessoa, de, ate, TELA_HISTORICO, forcar=forcar, libera=_escopo_padrao(de, ate))
        if prova is None:
            return None
        sel = [r for r in sel if prova.serve(r)]
        quem_lista = None if visao == "todos" else tuple(sorted((pessoa_lista or {}).items()))
        return _visao_pronta(lista, (visao, quem_lista, etq, de, ate, tuple(status_ids or ())) + prova.chave(sel), sel,
                             api._code_to_loc(), api.HISTORICO_CAP if cap is None else cap)
    except Exception:                                                # noqa: BLE001 — a tela segue pelo caminho de hoje
        log.exception("lista central de OS: o Histórico não leu da lista (segue ao vivo)")
        return None


def investigar(code, usina_curta, de, ate, conf_de, conf_ate, *, pessoa, forcar=False):
    """As OS do "Investigar ativo" (o ativo e a usina dele, no período [de, ate]) pelo índice por código de ativo da lista
    central (decisão BE), ou None: o caminho de hoje (a lista de "Todos" do Histórico). A conferência é a do período carregado
    (`conf_de`, `conf_ate`: os 30 dias da Visão COS quando o período cabe neles, como hoje; a MESMA medida da Visão COS: quem
    abriu uma não confere de novo na outra), e [de, ate] tem de caber nele; só a dos 30 dias padrão libera o nº → id. Volta uma
    `VisaoCentral` com as OS que têm o código do ativo ou um código da usina (pelo catálogo de ativos), só as que a conferência
    provou: quem chama recorta como sempre (`investigar_web`). Só para quem o Nexus liberou (`liberada`)."""
    try:
        if not (liberada() and periodo_valido(de, ate) and periodo_valido(conf_de, conf_ate)):
            return None
        if not (str(conf_de) <= str(de) and str(ate) <= str(conf_ate)):
            return None                                              # a prova é do período conferido
        lista = os_central.atual()
        if not (lista.cobre(de, ate) and lista.cobre(conf_de, conf_ate)):
            return None
        if not _medidos(os_central.campos_medidos(), CAMPOS_HISTORICO):
            return None
        prova = conferir(pessoa, conf_de, conf_ate, TELA_INVESTIGAR, forcar=forcar,
                         libera=_escopo_padrao(conf_de, conf_ate))
        if prova is None:
            return None
        local = api._code_to_loc()
        codigos = {str(code).strip()} if str(code or "").strip() else set()
        uc = _norm(usina_curta)
        if uc:
            codigos |= {c for c, v in local.items() if v and _norm(v[1]) == uc}
        achadas: dict = {}
        for c in codigos:
            for r in lista.por_codigo_ativo.get(c, ()):
                if de <= r.data[:10] <= ate and prova.serve(r):
                    achadas[r.id] = r
        regs = sorted(achadas.values(), key=lambda r: (r.data, r.id), reverse=True)
        return VisaoCentral(_linhas(lista, regs, local), {"total": len(regs), "cap": 0}, lista.lido_em, lista.versao)
    except Exception:                                                # noqa: BLE001 — a janela segue pelo caminho de hoje
        log.exception("lista central de OS: o Investigar ativo não leu da lista (segue ao vivo)")
        return None


def garantias(de, pessoa, forcar=False) -> dict | None:
    """As OS com a etiqueta CHAMADOS criadas desde `de` (o que o `api.list_chamados` dá ao quadro de Garantias), da lista
    central: {"linhas", "total", "lido_em"}, ou None (o caminho de hoje). A conferência é a do período que o quadro lê (de `de`
    até amanhã: o "até" é a data local e a criação é em UTC, e o quadro lê sem "até"), sem a etiqueta (Ruling BU); o Atualizar
    e a releitura por trás (`forcar`) medem de novo. Vai ao vivo também:
    - sem nenhuma nota do chamado entre as OS da etiqueta: o REST não a trouxe (o cartão do quadro se monta pela nota);
    - com uma OS do quadro "a conferir": a coluna dela sai do status, e o quadro não tem como dizer que ele pode ser velho (o
      Histórico diz, ao lado do nº); a faixa que a traz de volta (as finalizadas, de hora em hora) devolve o quadro à lista;
    - com uma nota cortada no teto (`nota_cortada`, Ruling BR): o "parado há N dias" sai do FIM da nota (o histórico da
      retroativa), e a nota pela metade não vai ao quadro como inteira.
    Só para quem o Nexus liberou (`liberada`)."""
    try:
        ate = (dt.date.today() + dt.timedelta(days=1)).isoformat()
        if not liberada() or not periodo_valido(de, ate):
            return None
        lista = os_central.atual()
        if not lista.cobre(de, ate) or not _medidos(os_central.campos_medidos(), CAMPOS_GARANTIAS):
            return None
        sel = os_central.filtrar("todos", None, de, ate, etiqueta=ETIQUETA_CHAMADOS)
        if (sel is None or (sel and not any(r.note for r in sel)) or any(lista.conferir(r.id) for r in sel)
                or any(r.nota_cortada for r in sel)):
            return None
        prova = conferir(pessoa, de, ate, TELA_GARANTIAS, forcar=forcar)
        if prova is None:
            return None
        sel = [r for r in sel if prova.serve(r)]
        return {"linhas": _linhas(lista, sel, api._code_to_loc()), "total": len(sel), "lido_em": lista.lido_em}
    except Exception:                                                # noqa: BLE001 — o quadro segue pelo caminho de hoje
        log.exception("lista central de OS: o Garantias não leu da lista (segue ao vivo)")
        return None


def codigos_recentes(dias) -> list | None:
    """Os códigos dos ativos com OS criada nos últimos `dias` (a marcação verde dos Ativos, `api.codigos_os_recentes`), da
    lista central, ou None (o caminho de hoje). Sem conferência: a de hoje já é uma só para todos (`("cat", "os_recentes")`,
    lida pela sessão de quem chegou primeiro), e segue dividida (decisão AZ). Só para quem o Nexus liberou (`liberada`)."""
    try:
        if not liberada():
            return None
        de = (datetime.now(timezone.utc) - timedelta(days=max(1, int(dias)))).strftime("%Y-%m-%d")
        lista = os_central.atual()
        if not lista.cobre(de, None) or not _medidos(os_central.campos_medidos(), CAMPOS_ATIVOS):
            return None
        sel = os_central.filtrar("todos", None, de, None)
        return None if sel is None else sorted({c for r in sel for c in r.codigos})
    except Exception:                                                # noqa: BLE001 — a tinta segue pelo caminho de hoje
        log.exception("lista central de OS: a marcação dos Ativos não leu da lista (segue ao vivo)")
        return None


def id_por_folio(folio) -> int | None:
    """O id da OS pelo nº, da lista central (sem pedido), para quem está liberado e só para a OS criada no escopo que o liberou
    (Ruling BP); senão None, e o `api._wo_id_por_folio` lê ao vivo, pela sessão da pessoa, como sempre. É o gancho
    `api.ID_PELA_LISTA`. Só para quem o Nexus liberou (`liberada`)."""
    try:
        pessoa = quem()
        if not liberada() or not liberado(pessoa) or not _medidos(os_central.campos_medidos(), (NO, CRIACAO)):
            return None
        wid = os_central.folio_para_id(folio)
        if wid is None:
            return None
        lista = os_central.atual()
        return wid if _no_escopo(pessoa, lista.por_id.get(wid), lista) else None
    except Exception:                                                # noqa: BLE001 — o nº segue ao vivo
        log.exception("lista central de OS: o nº %s não foi achado pela lista (segue ao vivo)", folio)
        return None


def previa(wid) -> dict | None:
    """A linha da OS para a 1ª pintura do card (o nº, o tipo, o status, o ativo, as datas, quem criou e com quem está), da
    lista central, ou None: o card abre como sempre, só com a leitura ao vivo. Só para quem está liberado, e só da OS criada no
    escopo que o liberou (Ruling BP): o card é aberto pelo id, que pode vir de qualquer tela. Só para quem o Nexus liberou
    (`liberada`)."""
    try:
        pessoa = quem()
        if not liberada() or not liberado(pessoa) or not _medidos(os_central.campos_medidos(), CAMPOS_PREVIA):
            return None
        lista = os_central.atual()
        r = lista.por_id.get(_int(wid))
        return None if not _no_escopo(pessoa, r, lista) else _linhas(lista, [r], api._code_to_loc())[0]
    except Exception:                                                # noqa: BLE001 — o card abre como sempre
        log.exception("lista central de OS: a 1ª pintura do card da OS %s não saiu da lista", wid)
        return None


# ── as ações põem a OS na lista ────────────────────────────────────────────────────────────────────────────────────────
def _executor():
    with _TRAVA:
        if _EXECUTOR["ex"] is None:
            _EXECUTOR["ex"] = api._ExecutorComContexto(max_workers=4, thread_name_prefix="os-web-releitura")
        return _EXECUTOR["ex"]


def _saiu(f) -> None:
    with _TRAVA:
        _RELEITURAS.discard(f)


def esperar_releituras(teto: float = 5.0) -> bool:
    """Espera as releituras de ações em curso (a que passou do prazo da tela segue por trás) terminarem, até `teto` segundos.
    True se não ficou nenhuma (os testes, antes de limpar a lista)."""
    fim = time.monotonic() + max(0.0, float(teto))
    while True:
        with _TRAVA:
            pendentes = [f for f in _RELEITURAS if not f.done()]
        if not pendentes:
            return True
        resta = fim - time.monotonic()
        if resta <= 0:
            return False
        cf.wait(pendentes, timeout=resta)


def _reler(ids) -> dict:
    """{id: o registro na lista} das OS que entraram, lidas JUNTAS pela sessão da pessoa (o contexto vai copiado para as
    threads), esperando no máximo `RELEITURA_MAX_S` no total (Minor 2 da rodada 1: a resposta da ação não fica presa no
    Fracttal lento). O prazo é por fora porque as leituras do card (`api._leitura_da_os`, `api._cabecalho_os`) não recebem um:
    o `_rpc_call` aceita o `timeout`, elas não o passam. A que passou do prazo fica "a conferir" e pendente
    (`os_central.marcar_pendente`): a que já lia segue por trás e, quando termina, põe a OS na lista do mesmo jeito; a que nem
    começou sai da fila. A que falhou vai ao log. As que entraram, a pessoa as viu (`_vistas`)."""
    ex = _executor()
    futuros = {}
    for wid in ids:
        f = ex.submit(os_central.atualizar_os, wid)
        with _TRAVA:
            _RELEITURAS.add(f)
        f.add_done_callback(_saiu)
        futuros[wid] = f
    cf.wait(list(futuros.values()), timeout=RELEITURA_MAX_S)
    entraram = {}
    for wid, f in futuros.items():
        if not f.done():
            # a que ainda não começou (as 4 threads ocupadas) não começa mais: a faixa das pendentes a lê pelo nº (Minor 1 da
            # rodada 2: ela ainda ia ao Fracttal depois da resposta, sem ninguém esperando); a que já lia segue por trás
            f.cancel()
            os_central.marcar_pendente(wid)
            log.info("lista central de OS: a releitura da OS %s passou de %.0f s; fica pendente para a faixa", wid,
                     RELEITURA_MAX_S)
            continue
        e = f.exception()
        if e is not None:
            log.error("lista central de OS: a OS %s não entrou na lista depois da ação (a ação valeu; a próxima faixa a "
                      "traz): %s: %s", wid, type(e).__name__, e, exc_info=e)
        elif f.result():
            r = os_central.atual().por_id.get(_int(wid))
            if r is not None:
                entraram[wid] = r
    _vistas(quem(), entraram)                                        # lidas na sessão dela: o Fracttal as mostrou a ela
    return entraram


def mudou(wid):
    """A OS que a ação acabou de mudar (o Fracttal já confirmou) entra na lista central na hora, lida pela sessão da pessoa
    (`os_central.atualizar_os`, o que o card já lê), com o prazo de `_reler`. O registro como entrou (o `api_finalizar` usa o
    status dele, sem reler o cabeçalho), ou None. A falha da lista nunca derruba a ação: vai ao log, e a próxima faixa a traz.

    Só com a lista EM USO (`em_uso()`: o servidor já leu uma janela inteira, pela cópia em disco ou pelas faixas, e ela cobre
    o período padrão do Histórico, os 30 dias). Sem ela (o PC sem leitor, a máquina recém-subida sem cópia, a janela de 7 dias
    do dia do deploy), nenhuma tela padrão lê da lista, e a leitura da OS seriam 1 a 3 pedidos à toa a cada ação. Caso que
    criou a regra (31/10/2026, na 1ª rodada dos testes da 3.3): sem esta guarda, a ação lia a OS mesmo onde ninguém lê a lista,
    e nos testes antigos do quadro, que não trocam o `_rpc_call`, a leitura saiu da máquina (recusada com 401, o JWT de
    mentira) e a sessão recusada derrubou o login da pessoa no pedido seguinte."""
    try:
        if not em_uso():
            return None
        return _reler([wid]).get(wid)
    except Exception:                                                # noqa: BLE001 — a ação já valeu no Fracttal
        log.exception("lista central de OS: a OS %s não entrou na lista depois da ação (a ação valeu; a próxima faixa a "
                      "traz)", wid)
        return None


def pendente(wid) -> None:
    """A OS que a ação mexeu sem a confirmação do Fracttal (o "fazer a tarefa" sem o registro confirmado, Minor 3 da rodada 2):
    sem reler (2 pedidos que nada provam), ela fica "a conferir" e pendente, e a faixa das pendentes a lê pelo nº. Só com a
    lista em uso (ver `mudou`); nunca derruba a ação."""
    try:
        if em_uso():
            os_central.marcar_pendente(wid)
    except Exception:                                                # noqa: BLE001 — a ação já respondeu
        log.exception("lista central de OS: a OS %s não ficou pendente depois da ação (a próxima faixa a traz)", wid)


def ids_criados(resultado) -> list:
    """Os ids das OS que uma função de criar devolveu, em qualquer dos formatos delas (a lista do "uma por ativo", o dict de
    uma OS, o {"os": {...}}); a que falhou (`ok` False) fica de fora, e a tarefa sem número também."""
    out: list = []

    def ver(x, fundo):
        if fundo > 3:
            return
        if isinstance(x, (list, tuple)):
            for y in x:
                ver(y, fundo + 1)
        elif isinstance(x, dict):
            if x.get("ok") is False:
                return
            wid = _int(x.get("id_work_order"))
            if wid:
                out.append(wid)
            if isinstance(x.get("os"), dict):
                ver(x["os"], fundo + 1)
    ver(resultado, 0)
    return list(dict.fromkeys(out))


def criadas(resultado) -> int:
    """As OS que uma tela de criar acabou de criar entram na lista: as `CRIADAS_NA_HORA` primeiras dentro do pedido, juntas e
    com o prazo de `_reler` (a OS criada não some do Histórico até a próxima volta). As outras, a faixa das novas traz (até 3
    min, 1 ou 2 pedidos): até a rodada 1 da 3.3 elas eram lidas por trás, 2 pedidos cada, sem origem declarada (~94 pedidos
    numa criação de 50 OS do COS). Quantas entraram na hora."""
    try:
        ids = ids_criados(resultado)
        if not ids or not em_uso():                                  # a lista fora de uso: nada a ler (ver `mudou`)
            return 0
        agora, depois = ids[:CRIADAS_NA_HORA], ids[CRIADAS_NA_HORA:]
        if depois:
            log.info("lista central de OS: %d OS criadas além das %d primeiras ficam para a faixa das novas", len(depois),
                     CRIADAS_NA_HORA)
        return len(_reler(agora))
    except Exception:                                                # noqa: BLE001 — a criação já valeu no Fracttal
        log.exception("lista central de OS: as OS criadas não entraram na lista (a criação valeu; a próxima faixa as traz)")
        return 0


# o nº → id do `api` passa por aqui (sem o gancho, o oem e o desktop seguem com a leitura de sempre). Só a cópia que o CLONE importa
# (`os_web.lista_central`) o instala: o mesmo arquivo importado por outro caminho (como pacote do Nexus, `nexus.torres.oscreator.
# os_creator.os_web.lista_central`) é uma 2ª cópia, com o estado dela (os liberados, as medidas), e religava o gancho a ela
if __name__ == "os_web.lista_central":
    api.ID_PELA_LISTA = id_por_folio
