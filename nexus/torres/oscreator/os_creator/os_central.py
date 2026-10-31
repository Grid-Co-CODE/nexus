"""os_central.py: a lista de OS do OS Creator, UMA para todas as telas (31/10/2026, etapa 3 do canto central).

Levi, 30/10/2026: "o histórico de OS pega só os mais recentes, atualizando os mais antigos 1 vez por dia pela noite [...] a
ideia é não ter um carregamento novo por atividade e sim um ecossistema onde as coisas se aproveitam" (desenho:
`docs/superpowers/specs/2026-10-30-oscreator-canto-central-design.md`, "Etapa 3"). Até aqui cada visão do Histórico era uma
lista no `historico_store` (a de "Todos" por quem vê o mesmo; "criadas por mim" e "atribuídas a mim" por pessoa), o Garantias
tinha a dele (365 dias), a marcação verde dos Ativos relia a janela de 30 dias, e o nº da OS virava id com 1 a 5 pedidos a
cada vez. As telas passam a ler daqui na 3.3; esta peça é a lista e quem a enche (o leitor em faixas, `os_leitor.py`).

O QUE A LISTA GUARDA (decisão AC): as OS CRIADAS nos últimos `JANELA_DIAS` (365: o Garantias lê 365, e o REST não filtra pela
etiqueta) mais toda OS aberta (status 1 e 2) de qualquer idade. Um registro enxuto por OS (`RegistroOS`, uma tupla com nome,
só leitura), com os campos que o Histórico, o Garantias e o card mostram, montado das linhas do REST `work_orders` (uma por
TAREFA, juntadas pelo `id_work_order`) ou da leitura que a ação do OS Creator faz pela sessão da pessoa. A descrição vai
cortada em 90 caracteres e o ativo em 60, como o `api._shape_wo_row` sempre entregou ao Histórico; a nota só da OS que traz o
bloco do chamado (o Garantias lê a OS de acompanhamento por ela). O cliente, a usina e o tipo do ativo NÃO são guardados: saem
do catálogo de ativos na hora (`RegistroOS.linha`), sempre em dia com ele. A MEMÓRIA (medida com 36 mil OS sintéticas da forma
real, tracemalloc; README do OS Creator): as cinco datas de cada OS vão juntas em 20 bytes (`datas`, segundos desde 2000; o
registro as devolve em ISO, como o Fracttal grava), os textos de pouca variedade (pessoas, tipos, gatilhos, etiquetas) são um
objeto só para todas as OS (`_TEXTOS`), e os que se repetem numa mesma leitura (o código e o nome do ativo, a descrição do
plano) também, sem tabela guardada.

UMA VERSÃO IMUTÁVEL (`Lista`), como o catálogo de ativos: os índices por id, por nº (`por_folio`) e por código de ativo, a
ordem pela data de criação, a janela lida inteira e as OS "a conferir". Troca-se o objeto inteiro: quem está lendo a de antes
termina com ela. Poucas OS mudadas (a ação, as novas) refazem só os pedaços delas nos índices (`_aplicar`); muitas (a noite),
tudo (`_indexar`). O registro não aceita escrita (é o mesmo para todas as telas); quem quer mexer pede a linha
(`RegistroOS.linha()`, um dicionário novo) e recebe uma lista nova de `filtrar`.

CADA LEITURA DIZ O QUE COBRE (`receber(linhas, faixa)`; a "faixa que sai" das decisões): a OS que a lista tinha dentro do que
a faixa cobre e que não veio nela mudou (de status, ou sumiu). Ela fica "a conferir" (a tela diz e o card lê ao vivo; nunca
se mostra como certo um status que a lista sabe velho) até uma faixa trazê-la de novo; a noite tira de vez o que não voltou.
O que cada faixa cobre e o que ela troca:
- `novas`: só SOMA as OS que a lista não tem (a leitura para numa página inteira de OS conhecidas, e as conhecidas dessa
  página podem vir pela metade: uma OS de várias tarefas atravessa a borda da página);
- `sete_dias` e `noite`: trocam as OS criadas desde o `desde` (a leitura vai até uma página INTEIRA mais velha que ele); a
  linha mais velha que o piso, da página que encerra a leitura, não entra (pode estar pela metade). A noite tira de vez a que
  não voltou e as fechadas que saíram da janela;
- `abertas` (status 1 e 2 inteiros, a leitura que o `tarefas_os` já faz de hora em hora): troca as que vieram; a que a lista
  tinha aberta e não veio fica "a conferir";
- `finalizadas` (status 3, pela data de fim): só ANOTA o status e a data fim nas OS que a lista já tem (a leitura é pela data
  de fim de cada TAREFA, então uma OS pode vir com parte das tarefas);
- `os`: as OS lidas uma a uma (as pendentes, pelo nº): todas saem da fila, e a que não veio (apagada no Fracttal) segue "a
  conferir" até a noite a tirar.
Leitura que falha no meio não chega aqui (quem lê não chama `receber`): a lista fica como estava. A TRAVA DE ENCOLHIMENTO
(Ruling AU, rodada 1 da revisão; o `ENCOLHE_MAX` dos ativos): a noite que tiraria, ou os 7 dias que marcariam "a conferir",
mais que `ENCOLHE_MAX`% das OS que a leitura cobre, e mais que `ENCOLHE_MIN_OS`, não trocam NADA: o motivo vai ao estado
(`recusas`), ao log e ao Raio-X (páginas perdidas em silêncio, o REST que devolve só uma parte). Os 5% são dos ativos; o
mínimo de 10 OS é porque os 7 dias cobrem ~700 OS na escala do AC (5% = 35) e, na lista pequena, 5% seriam uma ou duas OS
apagadas de verdade. O apagamento de verdade maior que isso passa na faixa mais larga: a noite de 90 dias cobre ~9 mil
(o limite é ~450), a de domingo, a janela inteira (~1.800); a 1ª carga (a lista vazia) não tem o que encolher. E a leitura
só julga o que existia quando ELA começou (`lido_em` é o começo): a noite inteira leva minutos, e a ação do OS Creator e a
entrega das abertas (outra thread) não esperam por ela. A OS que uma ação mexeu depois do começo da leitura não é trocada
pelo que a leitura leu (o status velho voltaria) nem julgada por ela; a OS criada depois do começo (com `MARGEM_RELOGIO_S`
de folga para o relógio do Fracttal) não sai nem fica "a conferir" por não ter vindo.

A AÇÃO DO OS CREATOR ENTRA NA HORA (`atualizar_os`): com o registro na mão, na hora; sem ele, dentro de um pedido do OS Creator,
lê a OS ao vivo pela sessão da pessoa (as tarefas e o cabeçalho, o que o card já lê: 1 a 3 pedidos); fora de um pedido (ou
com o Fracttal recusando), a OS fica "a conferir" e pendente para a próxima faixa. A OS criada pelo OS Creator não some do
Histórico até a próxima volta, e o reinício logo depois não a apaga (a cópia em disco chega em até 30 s).

A JANELA (`Lista.janela`, decisão AC): as datas de criação que a lista leu INTEIRAS, (de, até): `de` é o dia mais velho de uma
leitura de cima para baixo (os 7 dias, a noite) emendada com a seguinte, e `até` é o começo da última leitura que chegou ao
topo (as novas que pararam numa página conhecida também). A tela que pede um período fora dela vai ao vivo (`cobre`).

O DISCO (decisão AH; `os_disco.py`): `<pasta>/os_central.json.gz`, escrita em fluxo (uma linha JSON por OS, com o cabeçalho
na 1ª e o fecho na última: nem a escrita nem a leitura montam o arquivo inteiro na memória), trocada de uma vez (`canto_disco`),
no máximo uma escrita a cada `os_disco.GRAVAR_A_CADA_S` (as ações seguidas viram uma). O boot só lê o disco: nenhum pedido ao
Fracttal (meta 3). A cópia ilegível, cortada ou de outro formato é ignorada, a lista começa vazia e o estado diz por quê. É
cache do Fracttal, com texto de OS e nomes: não vai ao banco nem ao git (decisão AE).

ONDE MORA CADA PARTE (Ruling AY, rodada 1 da revisão): o registro e quem o monta em `os_registro.py`, a cópia em disco em
`os_disco.py`; aqui, a lista, as faixas, a ação, os filtros e o estado.

Só o `servir.py` liga o leitor (`os_leitor.ligar`); no PC e nos testes a lista só se enche pelo disco e pelas ações, e as
telas seguem ao vivo, como hoje.
"""
from __future__ import annotations

import bisect
import logging
import sys
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from types import MappingProxyType

import os_disco
from os_disco import FORMATO, NOME_ARQUIVO, esperar_gravacao  # noqa: F401 — os nomes de sempre (os testes, o conftest)
from os_registro import (  # noqa: F401 — o registro e os montadores, pelos nomes de sempre
    _EPOCA0, _PACOTE, _TEXTOS, ATIVO_MAX, DESCRICAO_MAX, MARCAS_DA_NOTA, NOTA_MAX, STATUS, RegistroOS, _cod, _int,
    _iso_seg, _Juntar, _norm, _s, _seg, _txt, registro_da_linha, registro_do_card, registros_do_rest)

log = logging.getLogger("oscreator.os_central")

JANELA_DIAS = 365               # as OS criadas nesta janela ficam (o Garantias lê 365 dias); as abertas, de qualquer idade
FRESCA_S = 30 * 60              # o período que chega a hoje só vale com a última leitura até o topo de no máximo 30 min
CAMPOS_MIN_OS = 50              # a medida dos campos do REST só vale numa leitura de pelo menos tantas OS
POR_PARTES_MIN = 50             # até tantas OS mudadas (ou 1/10 da lista), os índices se refazem só nelas
MARGEM_RELOGIO_S = 120          # a OS criada perto do começo de uma leitura (o relógio do Fracttal e o nosso) não é julgada por ela
TOCADAS_GUARDA_S = 86400        # quanto tempo a lista lembra que uma ação mexeu numa OS (uma leitura nunca dura isso)
ENCOLHE_MAX = 5                 # % das OS que a noite (os 7 dias) cobre que ela pode tirar (marcar "a conferir") de uma vez
ENCOLHE_MIN_OS = 10             # ... e sempre pode até tantas (a lista pequena; ver o topo)
PENDENTE_FALHAS_MAX = 5         # leituras pelo nº que falham até a pendente sair da fila (segue "a conferir")
ABERTOS = frozenset({1, 2})
NOVAS, SETE_DIAS, ABERTAS, FINALIZADAS, NOITE, UMA_OS = "novas", "sete_dias", "abertas", "finalizadas", "noite", "os"
FAIXAS = (NOVAS, SETE_DIAS, ABERTAS, FINALIZADAS, NOITE, UMA_OS)
VISOES = ("todos", "criadas", "atribuidas")
# ── a lista (imutável por versão) ──────────────────────────────────────────────────────────────────────────────────────
def _epoca(iso) -> float:
    try:
        return datetime.fromisoformat(str(iso)[:19]).replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return 0.0


def _iso(epoca: float) -> str:
    return datetime.fromtimestamp(epoca, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


@dataclass(frozen=True, slots=True, eq=False)
class Lista:
    """Uma versão da lista: pronta, imutável e compartilhada. `por_id` ({id: registro}), `por_folio` ({nº: registro}) e
    `por_codigo_ativo` ({código: (registros, da criação mais nova para a mais velha)}) guardam os MESMOS registros (nada é
    copiado); `ordem` são os registros pela criação, da mais nova para a mais velha; `nomes_criadores` é {nome normalizado de
    quem criou: os códigos de pessoa vistos com ele} (o homônimo de `filtrar`). `lido_em` é a última leitura do Fracttal que
    chegou aqui (qualquer faixa); `janela` = (de, até) das datas de criação lidas INTEIRAS (ver o topo); `a_conferir`, as OS
    que uma faixa deveria ter trazido e não trouxe; `versao` muda a cada troca de conteúdo."""
    por_id: Mapping
    por_folio: Mapping
    por_codigo_ativo: Mapping
    ordem: tuple
    nomes_criadores: Mapping
    lido_em: float
    janela: tuple
    versao: int
    a_conferir: frozenset

    def cobre(self, de=None, ate=None, agora: float | None = None) -> bool:
        """A lista responde por este período de criação (`de` e `ate` em 'AAAA-MM-DD', como as telas pedem)? Só se ele está
        dentro da janela lida inteira; o período que chega ao fim da janela (hoje) só com a última leitura até o topo de no
        máximo `FRESCA_S`. Fora disso a tela vai ao vivo."""
        jde, jate = self.janela
        if not jde or not jate or not de or str(de)[:10] < jde:
            return False
        if ate is None or str(ate)[:10] >= jate[:10]:
            return ((time.time() if agora is None else agora) - _epoca(jate)) <= FRESCA_S
        return True

    def conferir(self, wid) -> bool:
        """A OS está "a conferir" (uma faixa deveria tê-la trazido e não trouxe: o status dela pode ter mudado)."""
        return wid in self.a_conferir


def _chave(r: RegistroOS) -> tuple:
    """A ordem da lista ao contrário (a criação mais nova primeiro), para o `bisect`, que só sabe a ordem crescente."""
    return (-_s(r), -r.id)


def _indexar(por_id: dict, *, lido_em: float, janela: tuple, versao: int, a_conferir) -> Lista:
    """A versão pronta, com todos os índices montados de novo: CONSOME o dicionário `por_id` (ele vira o índice, sem cópia)."""
    ordem = sorted(por_id.values(), key=_chave)
    por_folio: dict = {}
    por_cod: dict = {}
    nomes: dict = {}
    for r in ordem:
        if r.folio:
            por_folio.setdefault(r.folio, r)
        for c in r.codigos:
            por_cod.setdefault(c, []).append(r)
        if r.criado_por:
            nomes.setdefault(_norm(r.criado_por), set()).add(_cod(r.cod_criador))
    return Lista(por_id=MappingProxyType(por_id), por_folio=MappingProxyType(por_folio),
                 por_codigo_ativo=MappingProxyType({c: tuple(v) for c, v in por_cod.items()}), ordem=tuple(ordem),
                 nomes_criadores=MappingProxyType({n: frozenset(c) for n, c in nomes.items()}), lido_em=float(lido_em),
                 janela=tuple(janela), versao=int(versao), a_conferir=frozenset(a_conferir))


def _aplicar(base: Lista, mudancas: dict, *, lido_em: float, janela: tuple, versao: int, a_conferir) -> Lista:
    """A versão nova com POUCAS OS mudadas (`mudancas`: {id: o registro novo, ou None para tirar}), refazendo nos índices só
    os pedaços delas: a ação do OS Creator, que roda dentro do pedido de alguém, não espera a lista inteira ser montada de novo
    (medido com 36 mil OS: ~0,25 s inteira). O resultado é o mesmo do `_indexar` (um teste confere), menos os
    `nomes_criadores`, que só ganham códigos aqui (o código de quem saiu fica até a noite refazer tudo: só pode deixar um nome
    "ambíguo" a mais, e a tela vai ao vivo, nunca o contrário)."""
    por_id = dict(base.por_id)
    por_folio = dict(base.por_folio)
    por_cod = dict(base.por_codigo_ativo)
    nomes = dict(base.nomes_criadores)
    saem = [base.por_id[w] for w in mudancas if w in base.por_id]
    ordem = list(base.ordem)
    if saem:
        fora = {id(r) for r in saem}
        ordem = [r for r in ordem if id(r) not in fora]
        for velho in saem:
            if por_folio.get(velho.folio) is velho:
                del por_folio[velho.folio]
            for c in velho.codigos:
                resto = tuple(x for x in por_cod.get(c, ()) if x is not velho)
                if resto:
                    por_cod[c] = resto
                else:
                    por_cod.pop(c, None)
            del por_id[velho.id]
    for wid, r in mudancas.items():
        if r is None:
            continue
        por_id[wid] = r
        bisect.insort(ordem, r, key=_chave)
        if r.folio:
            por_folio.setdefault(r.folio, r)
        for c in r.codigos:
            t = list(por_cod.get(c, ()))
            bisect.insort(t, r, key=_chave)
            por_cod[c] = tuple(t)
        if r.criado_por:
            n = _norm(r.criado_por)
            nomes[n] = nomes.get(n, frozenset()) | {_cod(r.cod_criador)}
    return Lista(por_id=MappingProxyType(por_id), por_folio=MappingProxyType(por_folio),
                 por_codigo_ativo=MappingProxyType(por_cod), ordem=tuple(ordem), nomes_criadores=MappingProxyType(nomes),
                 lido_em=float(lido_em), janela=tuple(janela), versao=int(versao), a_conferir=frozenset(a_conferir))


def _vazia() -> Lista:
    return _indexar({}, lido_em=0.0, janela=(None, None), versao=0, a_conferir=())


# ── o estado do processo ───────────────────────────────────────────────────────────────────────────────────────────────
_ATUAL: Lista | None = None
_TRAVA = threading.Lock()               # a troca da versão
_TRAVA_BOOT = threading.Lock()          # o boot pelo disco uma vez só, mesmo com vários pedidos juntos
_CONFIG: dict = {"pasta": None}
_BOOT = {"feito": False}
_SEQ = {"versao": 0}
_LEITOR: dict = {"estado": None}
_TOCADAS: dict = {}                     # {id da OS: quando a ação do OS Creator a pôs na lista} (a leitura não a desfaz)
_MEMORIA: dict = {"versao": None, "mb": None}   # a medida da memória da última versão medida (o Raio-X mede uma vez por versão)


def _estado_limpo() -> dict:
    # `faixas`: a última entrega de cada faixa (quando, quem, quantas OS e linhas, o que entrou, mudou, ficou a conferir e
    # saiu); `pendentes`: {id da OS: desde quando} que a ação deixou para a próxima faixa, e `falhas`: {id: quantas leituras
    # pelo nº falharam}; `recusas`: {faixa: a última leitura que a trava de encolhimento recusou}, até a faixa passar de novo;
    # `campos`: a medida dos campos que o REST trouxe na última leitura grande (a sondagem da 1ª noite, que não pôde ser feita
    # antes de construir); `disco["sujo"]`: a fila das pendentes mudou sem a versão mudar (a cópia em disco é regravada);
    # `conferencias`: {visão: as conferências de 19/10 das telas contra o `contar` (decisão BA da 3.3), só contagens}
    return {"faixas": {}, "pendentes": {}, "falhas": {}, "recusas": {}, "campos": None, "conferencias": {},
            "disco": {"lido": None, "gravado_em": 0.0, "versao": None, "bytes": None, "erro": None, "sujo": False}}


_ESTADO: dict = _estado_limpo()


def configurar(pasta: str | None) -> None:
    """Onde mora a cópia em disco (`<pasta>/os_central.json.gz`). Quem chama é a ponte do Nexus (`ponte.ligar_lista_de_os`);
    nos testes ela não chama: sem pasta, a lista vive só na memória. O boot acontece na primeira leitura depois disto."""
    with _TRAVA:
        if _CONFIG["pasta"] != pasta:
            _CONFIG["pasta"] = pasta
            _BOOT["feito"] = _ATUAL is not None and bool(_ATUAL.por_id)    # a lista que já tem OS não volta ao disco


def reiniciar(pasta: str | None = None) -> None:
    """Volta ao processo recém-subido (os testes): sem lista, sem leitor, sem gravação agendada, com a pasta que vier."""
    global _ATUAL
    os_disco.cancelar()
    with _TRAVA:
        _ATUAL = None
        _CONFIG["pasta"] = pasta
        _BOOT["feito"] = False
        _SEQ["versao"] = 0
        _LEITOR["estado"] = None
        _TOCADAS.clear()
        _ESTADO.clear()
        _ESTADO.update(_estado_limpo())
        _TEXTOS.clear()
        _MEMORIA.update(versao=None, mb=None)


def ligar_leitor(estado=None) -> None:
    """O leitor em faixas do servidor (`os_leitor.ligar`) se registra aqui, para o `estado()` mostrar o que ele fez."""
    _LEITOR["estado"] = estado


def atual() -> Lista:
    """A versão de agora (vazia, sem janela, se esta máquina ainda não tem nada). A 1ª chamada do processo faz o boot pela
    cópia em disco: sem rede, nenhum pedido ao Fracttal."""
    if not _BOOT["feito"]:
        _boot()
    return _ATUAL if _ATUAL is not None else _vazia()


def _instalar(base: Lista, mudancas: dict, *, lido_em: float, janela: tuple, a_conferir, mudou: bool) -> Lista:
    """Põe a versão nova no lugar (dentro da `_TRAVA`). Sem mudança de conteúdo: a mesma versão com a hora e o fim da janela
    trocados, sem índice nenhum montado e sem regravar o disco (eles vão junto da próxima mudança). Só o "a conferir" mudou:
    os mesmos índices. Poucas OS mudadas: os pedaços delas (`_aplicar`); muitas: tudo (`_indexar`)."""
    global _ATUAL
    lido_em = max(base.lido_em, lido_em)
    if not mudou:
        _ATUAL = replace(base, lido_em=lido_em, janela=janela)
        return _ATUAL
    _SEQ["versao"] += 1
    versao = _SEQ["versao"]
    if not mudancas:
        _ATUAL = replace(base, lido_em=lido_em, janela=janela, versao=versao, a_conferir=frozenset(a_conferir))
    elif len(mudancas) <= max(POR_PARTES_MIN, len(base.por_id) // 10):
        _ATUAL = _aplicar(base, mudancas, lido_em=lido_em, janela=janela, versao=versao, a_conferir=a_conferir)
    else:
        por_id = dict(base.por_id)
        for wid, r in mudancas.items():
            if r is None:
                por_id.pop(wid, None)
            else:
                por_id[wid] = r
        _ATUAL = _indexar(por_id, lido_em=lido_em, janela=janela, versao=versao, a_conferir=a_conferir)
    return _ATUAL


def _piso_da_janela(agora: float) -> str:
    return (datetime.fromtimestamp(agora, timezone.utc) - timedelta(days=JANELA_DIAS)).strftime("%Y-%m-%d")


def _dia_inteiro(desde) -> str:
    """O 1º dia lido INTEIRO por uma leitura que foi até `desde`: o próprio dia se ele começa à meia-noite (ou veio só a
    data), senão o seguinte."""
    s = _txt(desde)
    if len(s) <= 10 or s[11:19] in ("", "00:00:00"):
        return s[:10]
    return (datetime.fromisoformat(s[:10]) + timedelta(days=1)).strftime("%Y-%m-%d")


def _janela_nova(janela: tuple, faixa: str, desde, inicio: float, agora: float) -> tuple:
    """A janela depois de uma leitura (ver o topo): os 7 dias e a noite cobrem [desde, começo da leitura] e emendam com a de
    antes quando chegam até ela; as novas só avançam o fim, e só emendadas (`desde` é a criação mais velha da página conhecida
    em que pararam). As outras faixas não mexem na janela."""
    jde, jate = janela
    ate = _iso(inicio)
    if faixa in (SETE_DIAS, NOITE) and desde:
        de = _dia_inteiro(desde)
        if jde and jate and _txt(desde)[:19] <= jate and jde < de:
            de = jde
        return max(de, _piso_da_janela(agora)), max(ate, jate or "")
    if faixa == NOVAS and desde and jde and jate and _txt(desde)[:19] <= jate:
        return jde, max(ate, jate)
    return janela


def _fica(r: RegistroOS, piso_s: int, a_conferir) -> bool:
    """A OS fica na lista: criada dentro da janela, ou aberta (de qualquer idade) e não "a conferir"."""
    return _s(r) >= piso_s or (r.status_id in ABERTOS and r.id not in a_conferir)


def _medir_campos(novos: dict, faixa: str, agora: float) -> None:
    """Quantas OS da leitura trouxeram cada campo que as telas usam (só contagens): é a sondagem do REST que não pôde ser
    feita antes de construir; o Raio-X mostra."""
    if len(novos) < CAMPOS_MIN_OS:
        return
    n = len(novos)
    rs = novos.values()
    # a data fim, o início e a nota do chamado entraram na 3.3 (as telas que os mostram vão ao vivo quando a leitura grande
    # não os trouxe; a nota do chamado é rara numa leitura qualquer, e o Garantias a confere nas OS dele, `lista_central`)
    conta = {"nº": sum(1 for r in rs if r.folio), "criação": sum(1 for r in rs if _s(r)),
             "quem criou": sum(1 for r in rs if r.criado_por),
             "código de quem criou": sum(1 for r in rs if r.cod_criador),
             "responsável (id)": sum(1 for r in rs if r.id_atribuido is not None),
             "tipo da tarefa": sum(1 for r in rs if r.tipo_tarefa), "código do ativo": sum(1 for r in rs if r.codigos),
             "programada": sum(1 for r in rs if _s(r, 3)), "gatilho": sum(1 for r in rs if r.gatilho),
             "etiqueta com id": sum(1 for r in rs if any(i is not None for i, _ in r.etiquetas)),
             "com etiqueta": sum(1 for r in rs if r.etiquetas), "data fim": sum(1 for r in rs if _s(r, 2)),
             "início": sum(1 for r in rs if _s(r, 4)), "nota do chamado": sum(1 for r in rs if r.note)}
    _ESTADO["campos"] = {"faixa": faixa, "em": agora, "n": n,
                         "pct": {k: round(100.0 * v / n, 1) for k, v in conta.items()}}


def receber(linhas_rest, faixa: str, *, desde=None, lido_em: float | None = None, quem: str | None = None,
            ids=None) -> dict:
    """Uma leitura do REST `work_orders` (as linhas, uma por tarefa) entra na lista pela regra da `faixa` (ver o topo):
    `desde` é o piso da leitura (a criação, nas novas, nos 7 dias e na noite; a data de fim, nas finalizadas), `lido_em` o
    COMEÇO dela (padrão: agora; é o fim da janela), `quem` quem leu (as abertas vêm do `tarefas_os` ou do próprio leitor), e
    `ids` as OS que a faixa `os` pediu. Devolve o relatório (só contagens), que também fica em `estado()["faixas"]`."""
    if faixa not in FAIXAS:
        raise ValueError("faixa desconhecida: %r (as válidas: %s)" % (faixa, ", ".join(FAIXAS)))
    agora = time.time()
    inicio = agora if lido_em is None else float(lido_em)
    atual()                                                          # o boot pelo disco antes (sem ele, a cópia se perderia)
    if faixa == NOITE:
        _TEXTOS.clear()                                              # a noite refaz a tabela dos textos repetidos
    novos = registros_do_rest(linhas_rest)
    _medir_campos(novos, faixa, agora)
    piso_s = _seg(_piso_da_janela(agora))
    desde_s = _seg(desde) if desde else None
    rel = {"faixa": faixa, "em": agora, "inicio": inicio, "quem": quem or "", "linhas": len(linhas_rest or ()),
           "os": len(novos), "entraram": 0, "mudaram": 0, "a_conferir": 0, "sairam": 0, "fora": 0}
    # o que mudou depois do começo da leitura não é julgado por ela (ver o topo): a OS que a ação mexeu, e a criada no meio
    limite_s = int(inicio) - _EPOCA0 - MARGEM_RELOGIO_S

    def mexida_depois(wid) -> bool:
        return _TOCADAS.get(wid, 0.0) >= inicio
    with _TRAVA:
        # os dicionários que outras threads mexem são percorridos só dentro da trava, ou pela cópia (`list`, de uma vez só)
        for wid in [w for w, quando in list(_TOCADAS.items()) if agora - quando > TOCADAS_GUARDA_S]:
            _TOCADAS.pop(wid, None)
        base = _ATUAL if _ATUAL is not None else _vazia()
        conferir = set(base.a_conferir)
        sai_da_fila: set = set()                                     # as pendentes que a leitura aceita tira da fila
        if faixa in (SETE_DIAS, NOITE):
            cobre = (lambda r: desde_s <= _s(r) < limite_s) if desde_s is not None else (lambda r: False)
        elif faixa == ABERTAS:
            cobre = lambda r: r.status_id in ABERTOS and _s(r) < limite_s                 # noqa: E731
        elif faixa == UMA_OS:
            pedidos = {_int(i) for i in (ids or ())} | set(novos)
            cobre = lambda r: r.id in pedidos                                               # noqa: E731
            sai_da_fila |= pedidos                                   # a que não veio (apagada) também sai: fica "a conferir"
        else:
            cobre = None
        mudancas: dict = {}
        for wid, r in novos.items():
            velho = base.por_id.get(wid)
            if mexida_depois(wid):
                rel["fora"] += 1                                     # a ação mexeu nela depois: o que a leitura leu é velho
                continue
            if faixa == NOVAS:
                if velho is not None or not _fica(r, piso_s, ()):
                    continue
            elif faixa == FINALIZADAS:
                if velho is None:
                    rel["fora"] += 1                                 # a lista não tem: a OS pode ter vindo pela metade
                    continue
                r = velho._replace(status_id=r.status_id, datas=_PACOTE.pack(
                    *(max(a, b) if i == 2 else a for i, (a, b) in enumerate(zip(_PACOTE.unpack(velho.datas),
                                                                                _PACOTE.unpack(r.datas))))))
            elif faixa in (SETE_DIAS, NOITE) and (desde_s is None or _s(r) < desde_s):
                rel["fora"] += 1                                     # mais velha que o piso: a página da borda
                continue
            elif faixa == ABERTAS and velho is None and r.status_id not in ABERTOS:
                continue
            conferir.discard(wid)
            sai_da_fila.add(wid)
            if velho is None:
                if _fica(r, piso_s, conferir):
                    mudancas[wid] = r
                    rel["entraram"] += 1
            elif r != velho:
                mudancas[wid] = r
                rel["mudaram"] += 1
        cobertas = 0
        if cobre is not None:
            for wid, r in base.por_id.items():
                if not cobre(r):
                    continue
                cobertas += 1
                if wid in novos or mexida_depois(wid):
                    continue
                if faixa == NOITE:
                    mudancas[wid] = None                             # a noite tira de vez o que não voltou
                    conferir.discard(wid)
                    rel["sairam"] += 1
                elif wid not in conferir:
                    conferir.add(wid)
                    rel["a_conferir"] += 1
        recusa = _encolheria(faixa, base, cobertas, rel)
        if recusa is not None:
            _ESTADO["recusas"][faixa] = recusa
            rel.update(recusa=recusa["motivo"], entraram=0, mudaram=0, a_conferir=0, sairam=0)
            lista, mudou, fila_mudou = base, False, False
        else:
            if faixa == NOITE:
                for wid, r in base.por_id.items():
                    r = mudancas.get(wid, r)
                    if r is not None and not _fica(r, piso_s, conferir):
                        mudancas[wid] = None                         # as fechadas que saíram da janela
                        conferir.discard(wid)
                        rel["sairam"] += 1
            janela = _janela_nova(base.janela, faixa, desde, inicio, agora)
            mudou = bool(mudancas) or conferir != base.a_conferir or janela[0] != base.janela[0]
            lista = _instalar(base, mudancas, lido_em=inicio, janela=janela, a_conferir=conferir, mudou=mudou)
            _ESTADO["faixas"][faixa] = rel
            _ESTADO["recusas"].pop(faixa, None)
            fila_mudou = _tirar_da_fila(sai_da_fila)
    if recusa is not None:
        log.warning("lista central de OS: faixa %s (%s) recusada pela trava de encolhimento: %s", faixa, quem or "-",
                    recusa["motivo"])
        return rel
    if mudou or fila_mudou:
        _agendar_gravacao()
    log.info("lista central de OS: faixa %s (%s): %d OS em %d linhas; %d entraram, %d mudaram, %d a conferir, %d saíram; "
             "a lista tem %d", faixa, quem or "-", rel["os"], rel["linhas"], rel["entraram"], rel["mudaram"],
             rel["a_conferir"], rel["sairam"], len(lista.por_id))
    return rel


def _encolheria(faixa: str, base: Lista, cobertas: int, rel: dict) -> dict | None:
    """A recusa da trava de encolhimento (ver o topo), ou None: a noite que tiraria (os 7 dias que marcariam "a conferir")
    mais que `ENCOLHE_MAX`% das `cobertas` (as OS da lista que a leitura cobre) e mais que `ENCOLHE_MIN_OS`. Só a noite e os
    7 dias; a lista vazia (a 1ª carga) não tem o que encolher. Só contagens no motivo."""
    if faixa not in (SETE_DIAS, NOITE) or not base.por_id:
        return None
    saem = rel["sairam"] if faixa == NOITE else rel["a_conferir"]
    limite = max(ENCOLHE_MIN_OS, cobertas * ENCOLHE_MAX // 100)
    if saem <= limite:
        return None
    if faixa == NOITE:
        motivo = "a noite encolheria a lista: tiraria %d das %d OS que ela cobre" % (saem, cobertas)
    else:
        motivo = "os 7 dias encolheriam a lista: marcariam %d das %d OS que eles cobrem como \"a conferir\"" % (saem, cobertas)
    motivo += " (o limite é %d: %d%% delas, no mínimo %d OS); nada foi trocado" % (limite, ENCOLHE_MAX, ENCOLHE_MIN_OS)
    return {"faixa": faixa, "em": time.time(), "inicio": rel["inicio"], "de": cobertas, "sairiam": saem, "limite": limite,
            "motivo": motivo}


def _tirar_da_fila(ids) -> bool:
    """Tira as OS da fila das pendentes (dentro da `_TRAVA`), com as falhas delas; True se alguma estava lá (a cópia em disco
    é regravada mesmo sem a versão mudar)."""
    pend, falhas = _ESTADO["pendentes"], _ESTADO["falhas"]
    tirou = False
    for wid in ids:
        tirou = pend.pop(wid, None) is not None or tirou
        falhas.pop(wid, None)
    if tirou:
        _ESTADO["disco"]["sujo"] = True
    return tirou


# ── a ação do OS Creator ───────────────────────────────────────────────────────────────────────────────────────────────
def _em_pedido() -> bool:
    """Dentro de um pedido do OS Creator, com a sessão do Fracttal da pessoa (o JWT no contexto)."""
    try:
        from os_web import sessao
    except Exception:                                                # noqa: BLE001 — sem o clone, não há sessão
        return False
    return bool(sessao.jwt_atual())


def _ler_ao_vivo(wid: int) -> RegistroOS | None:
    """A OS lida agora pela sessão da pessoa, com o que o card já lê: as tarefas (`_leitura_da_os`, que reaproveita a leitura
    que o card acabou de fazer e é esquecida por toda gravação na OS) e o cabeçalho. 1 a 3 pedidos."""
    import api
    tarefas = api._leitura_da_os(api.RPC_WO_TASKS, wid, {"id_work_order": wid, "sort": []})
    cab = api._cabecalho_os(wid)
    return registro_do_card(wid, tarefas, cab)


def _como_registro(wid: int, registro) -> RegistroOS | None:
    if isinstance(registro, RegistroOS):
        return registro
    if isinstance(registro, (list, tuple)):
        return registros_do_rest(registro).get(wid)                  # as linhas do REST (uma por tarefa)
    if isinstance(registro, dict):
        if "wo_folio" in registro and "folio" not in registro:       # a linha crua do RPC: o formato do Histórico primeiro
            import api
            return registro_da_linha(api._shape_wo_row(registro))
        return registro_da_linha(dict(registro, id=registro.get("id", wid)))
    return None


def _marcar_pendente(wid: int) -> None:
    with _TRAVA:
        base = _ATUAL if _ATUAL is not None else _vazia()
        _ESTADO["pendentes"][wid] = time.time()
        _ESTADO["falhas"].pop(wid, None)                             # a ação nova vale uma fila nova
        _ESTADO["disco"]["sujo"] = True
        if wid in base.por_id and wid not in base.a_conferir:
            _instalar(base, {}, lido_em=base.lido_em, janela=base.janela, a_conferir=set(base.a_conferir) | {wid},
                      mudou=True)
    _agendar_gravacao()


def atualizar_os(id_work_order, registro=None) -> bool:
    """A OS que o OS Creator acabou de criar ou mudar entra na lista NA HORA. `registro`: o registro pronto, as linhas do REST
    da OS, a linha do Histórico (`api.list_minhas_os`) ou a linha crua do RPC. Sem ele, dentro de um pedido do OS Creator, a
    OS é lida ao vivo pela sessão da pessoa (o que o card já lê, 1 a 3 pedidos); fora de um pedido, ou com a leitura falhando,
    ela fica "a conferir" e pendente para a próxima faixa (nada vai ao Fracttal daqui). True se entrou."""
    wid = _int(id_work_order)
    if wid is None:
        return False
    atual()                                                          # o boot pelo disco antes de mexer
    if registro is None:
        if not _em_pedido():
            _marcar_pendente(wid)
            return False
        try:
            reg = _ler_ao_vivo(wid)
        except Exception as e:                                       # noqa: BLE001 — a ação já deu certo; a lista espera a faixa
            log.warning("lista central de OS: não li a OS %s ao vivo (%s: %s); fica para a próxima faixa", wid,
                        type(e).__name__, str(e)[:120])
            reg = None
    else:
        reg = _como_registro(wid, registro)
    if reg is None or reg.id != wid:
        _marcar_pendente(wid)
        return False
    with _TRAVA:
        base = _ATUAL if _ATUAL is not None else _vazia()
        velho = base.por_id.get(wid)
        if not _s(reg):                                              # a criação que a leitura não trouxe: a de antes, ou agora
            reg = reg.com(data=velho.data if velho is not None else _iso(time.time()))
        _tirar_da_fila((wid,))
        _TOCADAS[wid] = time.time()                                  # a leitura que começou antes não a desfaz
        _instalar(base, {wid: reg}, lido_em=base.lido_em, janela=base.janela,
                  a_conferir=set(base.a_conferir) - {wid}, mudou=True)
    _agendar_gravacao()
    return True


# ── as visões viram filtros ────────────────────────────────────────────────────────────────────────────────────────────
def _quem_casa(lista: Lista, visao: str, pessoa):
    """(casa(registro) -> (casou, só pelo nome), o nome é ambíguo) da visão, ou None quando a pessoa não se identifica para
    ela. "criadas por mim": pelo id da conta (o que o RPC traz) quando os dois lados o têm; senão pelo código da pessoa no
    Fracttal (o `code_create_by` do REST); senão pelo nome, que só vale sem homônimo. "atribuídas a mim": pelo id da pessoa."""
    p = pessoa if isinstance(pessoa, dict) else {}
    if visao == "todos":
        return (lambda r: (True, False)), False
    if visao == "atribuidas":
        idp = _int(p.get("id_personnel"))
        if idp is None:
            return None
        return (lambda r: (r.id_atribuido == idp, False)), False
    ida, cod, nome = _int(p.get("id_account")), _cod(p.get("codigo")), _norm(p.get("nome"))
    if ida is None and not cod and not nome:
        return None
    codigos = set(lista.nomes_criadores.get(nome, ())) - {""} if nome else set()
    ambiguo = bool(codigos - {cod}) if cod else len(codigos) > 1

    def casa(r):
        if ida is not None and r.id_criador is not None:
            return r.id_criador == ida, False
        if cod and r.cod_criador:
            return _cod(r.cod_criador) == cod, False
        if nome and r.criado_por:
            return _norm(r.criado_por) == nome, True
        return False, False
    return casa, ambiguo


def _selecionar(visao, pessoa, de, ate, etiqueta, status):
    lista = atual()
    if visao not in VISOES or not lista.cobre(de, ate):
        return None
    q = _quem_casa(lista, visao, pessoa)
    if q is None:
        return None
    casa, ambiguo = q
    de_s = _seg(str(de)[:10])
    ate_s = _seg(str(ate)[:10] + "T23:59:59") if ate else None
    st = {_int(s) for s in status} if status else None
    etq = None if etiqueta is None else (_int(etiqueta) if _int(etiqueta) is not None else _norm(etiqueta))
    out, pelo_nome = [], False
    for r in lista.ordem:                                            # da criação mais nova para a mais velha
        criada = _s(r)
        if criada < de_s:
            break
        if ate_s is not None and criada > ate_s:
            continue
        casou, so_nome = casa(r)
        if not casou:
            continue
        if st is not None and (r.status_id not in st or r.id in lista.a_conferir):
            continue                                                 # "a conferir": o status dela é velho
        if etq is not None and not any((i == etq) if isinstance(etq, int) else (_norm(n) == etq)
                                       for i, n in r.etiquetas):
            continue
        pelo_nome = pelo_nome or so_nome
        out.append(r)
    if visao == "criadas":
        if pelo_nome and ambiguo:
            return None                                              # o homônimo: só a leitura ao vivo diz qual
        p = pessoa if isinstance(pessoa, dict) else {}
        if not out and _int(p.get("id_account")) is None and not _cod(p.get("codigo")):
            return None                                              # pelo nome, zero pode ser o nome escrito de outro jeito
    return out


def filtrar(visao: str = "todos", pessoa=None, de=None, ate=None, *, etiqueta=None, status=None) -> list | None:
    """As OS da visão ("todos", "criadas", "atribuidas") criadas no período [de, ate] ('AAAA-MM-DD'), da mais nova para a mais
    velha: uma lista NOVA, de quem pediu, com os registros da lista central (só leitura; `linha()` dá a cópia mutável).
    `pessoa`: {"id_account", "codigo", "nome"} para "criadas", {"id_personnel"} para "atribuidas". `etiqueta`: o id (ou o
    nome); `status`: os ids aceitos (a OS "a conferir" fica de fora, o status dela é velho). None quando a lista não responde
    por isso e a tela tem de ir ao vivo: o período fora da janela lida inteira (`Lista.cobre`), a pessoa que não se identifica
    para a visão, o nome com homônimo, ou o nome que não casou com nenhuma OS."""
    return _selecionar(visao, pessoa, de, ate, etiqueta, status)


def contar(visao: str = "todos", pessoa=None, de=None, ate=None, *, etiqueta=None, status=None) -> int | None:
    """Quantas OS `filtrar` daria (a guarda da lista pela metade, decisão AI: a 3.3 compara com o total que o Fracttal dá à
    pessoa). None nos mesmos casos de `filtrar`."""
    sel = _selecionar(visao, pessoa, de, ate, etiqueta, status)
    return None if sel is None else len(sel)


def folio_para_id(folio) -> int | None:
    """O id da OS pelo nº (wo_folio), pelo índice: sem pedido nenhum ao Fracttal. None se a lista não tem esse nº (a tela
    segue com a leitura ao vivo para o resto)."""
    f = _txt(folio)
    if not f:
        return None
    lista = atual()
    r = lista.por_folio.get(f)
    if r is None and f.isdigit():
        r = lista.por_folio.get(str(int(f)))
    return r.id if r is not None else None


def campos_medidos() -> dict | None:
    """A medida dos campos que o REST trouxe na última leitura grande (`_medir_campos`: {"faixa", "em", "n", "pct"}), ou None
    se nenhuma leitura grande mediu ainda. É o que a tela confere antes de ler um campo da lista (Ruling AT, decisão BB da
    3.3); leve, ao contrário do `estado()`, que percorre a lista."""
    atual()
    c = _ESTADO["campos"]
    return dict(c) if c else None


def anotar_conferencia(visao: str, bateu, *, fracttal=None, lista=None) -> None:
    """Uma conferência de 19/10 de uma tela que lê da lista (decisão BA da 3.3): o total que o Fracttal dá à pessoa (1 pedido
    na sessão dela) contra o `contar` da lista. `bateu` None = a conferência falhou (o Fracttal fora, a sessão caída): não
    libera nada e conta à parte. Muitas divergências de quem tem a visão inteira é sinal de lista errada: o Raio-X mostra. Só
    contagens e a hora, nunca quem (o estado vai ao Raio-X)."""
    agora = time.time()
    with _TRAVA:
        c = _ESTADO["conferencias"].setdefault(str(visao), {"n": 0, "divergiram": 0, "falharam": 0, "ultima": None,
                                                            "ultima_divergencia": None})
        c["ultima"] = agora
        if bateu is None:
            c["falharam"] += 1
            return
        c["n"] += 1
        if not bateu:
            c["divergiram"] += 1
            c["ultima_divergencia"] = {"em": agora, "fracttal": _int(fracttal), "lista": _int(lista)}


def mais_nova_data_fim() -> str:
    """A data de fim mais nova que a lista conhece entre as concluídas (o piso das finalizadas é ela menos 2 dias), ou ""."""
    return _iso_seg(max((_s(r, 2) for r in atual().ordem if r.status_id == 3), default=0))


def entrega(faixa: str) -> dict | None:
    """A última entrega desta faixa (`estado()["faixas"]`), ou None."""
    atual()
    e = _ESTADO["faixas"].get(faixa)
    return dict(e) if e else None


def pendentes() -> dict:
    """{id da OS: desde quando} das OS que a ação deixou para a próxima faixa."""
    atual()
    return dict(_ESTADO["pendentes"])


def fila_de_pendentes(n: int) -> list:
    """[(id, nº)] das pendentes que a lista conhece pelo nº, até `n`, para a leitura pelo nº (`os_leitor.ler_pendentes`): as
    de menos falhas primeiro, depois as mais velhas na fila (a que derruba a leitura vai para o fim e não segura as outras).
    A que a lista não conhece (o nº não se sabe) espera a faixa que a traga."""
    lista = atual()
    with _TRAVA:
        pend, falhas = dict(_ESTADO["pendentes"]), dict(_ESTADO["falhas"])
    alvos = sorted((falhas.get(w, 0), quando, w) for w, quando in pend.items()
                   if w in lista.por_id and lista.por_id[w].folio)
    return [(w, lista.por_id[w].folio) for _f, _q, w in alvos[:max(0, int(n))]]


def falhou_pendente(id_work_order) -> bool:
    """Mais uma leitura pelo nº que falhou nesta pendente; na `PENDENTE_FALHAS_MAX`-ésima ela sai da fila (Minor 5 da rodada 1:
    5 pendentes mortas travavam a fila) e segue "a conferir": a próxima faixa que a cobre a traz. True se saiu."""
    wid = _int(id_work_order)
    with _TRAVA:
        if wid not in _ESTADO["pendentes"]:
            return False
        n = _ESTADO["falhas"].get(wid, 0) + 1
        saiu = n >= PENDENTE_FALHAS_MAX
        if saiu:
            _tirar_da_fila((wid,))
        else:
            _ESTADO["falhas"][wid] = n
            _ESTADO["disco"]["sujo"] = True
    if saiu:
        log.warning("lista central de OS: a OS %s saiu da fila das pendentes depois de %d leituras pelo nº que falharam; "
                    "segue \"a conferir\" até a próxima faixa", wid, n)
    _agendar_gravacao()
    return saiu


def mais_nova_criacao() -> float | None:
    """A criação mais nova que a lista conhece (segundos), ou None (a lista vazia): o topo que a leitura pela criação tem de
    alcançar (`os_leitor`, Ruling AU)."""
    lista = atual()
    s = _s(lista.ordem[0]) if lista.ordem else 0
    return float(s + _EPOCA0) if s else None


# ── a cópia em disco (os_disco.py): daqui, a pasta, a versão vigente e o estado ──────────────────────────────────────────
def _caminho() -> str | None:
    return os_disco.caminho(_CONFIG["pasta"])


def _agendar_gravacao() -> None:
    os_disco.agendar(_CONFIG["pasta"], _gravar_agora)


def _extras_do_disco() -> dict:
    # copiados de uma vez (`list`): a faixa e a ação mexem nesses dicionários em outras threads. A medida dos campos vai junto
    # (3.3): as telas só leem da lista o campo que a última leitura grande trouxe, e sem ela, depois de cada deploy, iriam ao
    # vivo até a próxima leitura grande (os 7 dias, de 10 em 10 min de dia; de noite, só às 03:21). "campos" já é o nome dos
    # campos do registro no cabeçalho: a medida vai em "campos_rest"
    c = _ESTADO["campos"]
    return {"pendentes": {str(k): v for k, v in list(_ESTADO["pendentes"].items())},
            "falhas_pendentes": {str(k): v for k, v in list(_ESTADO["falhas"].items())},
            "faixas": {k: dict(v) for k, v in list(_ESTADO["faixas"].items())},
            "campos_rest": dict(c) if c else None}


def _gravar_agora() -> bool:
    return os_disco.gravar_lista(_CONFIG["pasta"], lambda: _ATUAL, _ESTADO["disco"], _extras_do_disco)


def _ler_disco():
    return os_disco.ler_lista(_CONFIG["pasta"], _ESTADO["disco"], _Juntar())


def _boot() -> None:
    """A cópia em disco, uma vez só (quem chega com o boot em curso espera nele). Sem cópia, a lista nasce vazia e sem
    janela: as telas vão ao vivo até as faixas a encherem."""
    global _ATUAL
    with _TRAVA_BOOT:
        if _BOOT["feito"]:
            return
        try:
            carga = _ler_disco()
            if carga is not None:
                cab, por_id = carga
                versao = int(cab.get("versao") or 0)
                ids = set(por_id)
                lista = _indexar(por_id, lido_em=float(cab.get("lido_em") or 0.0),
                                 janela=tuple((cab.get("janela") or [None, None])[:2]), versao=versao,
                                 a_conferir={i for i in (cab.get("a_conferir") or ()) if i in ids})
                with _TRAVA:
                    if _ATUAL is None or not _ATUAL.por_id:
                        _ATUAL = lista
                        _SEQ["versao"] = max(_SEQ["versao"], versao)
                        _ESTADO["pendentes"].update({int(k): float(v) for k, v in (cab.get("pendentes") or {}).items()})
                        _ESTADO["falhas"].update({int(k): int(v) for k, v in (cab.get("falhas_pendentes") or {}).items()
                                                  if int(k) in _ESTADO["pendentes"]})
                        if isinstance(cab.get("faixas"), dict):
                            _ESTADO["faixas"].update(cab["faixas"])
                        if isinstance(cab.get("campos_rest"), dict) and not _ESTADO["campos"]:
                            _ESTADO["campos"] = cab["campos_rest"]
                        _ESTADO["disco"].update(lido="cópia gravada em %s" % _hora(cab.get("gravado_em")),
                                                versao=versao, gravado_em=float(cab.get("gravado_em") or 0.0))
                log.info("lista central de OS: %d OS da cópia em disco", len(lista.por_id))
        except Exception as e:                                       # noqa: BLE001 — o boot não derruba quem só quer ler
            _ESTADO["disco"]["erro"] = "boot: %s: %s" % (type(e).__name__, str(e)[:120])
            log.warning("lista central de OS: o boot pelo disco falhou (%s)", _ESTADO["disco"]["erro"])
        finally:
            with _TRAVA:
                if _ATUAL is None:
                    _ATUAL = _vazia()
            _BOOT["feito"] = True


def _hora(ts) -> str:
    try:
        return datetime.fromtimestamp(float(ts), timezone(timedelta(hours=-3))).strftime("%d/%m %H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return "?"


# ── o estado, para o Raio-X ────────────────────────────────────────────────────────────────────────────────────────────
def memoria_estimada(lista: Lista | None = None) -> float:
    """Os MB da lista: cada registro, texto e tupla contados UMA vez (os índices guardam os mesmos registros, e os textos que se
    repetem são um objeto só), mais o esqueleto dos índices. A amostra do "Dentro do Nexus" contaria os mesmos registros em
    cada índice e os textos repetidos em cada registro (o dobro, ou mais). Percorre a lista inteira: ~0,4 s com 36 mil OS; só o
    Raio-X chama, e o `estado()` guarda a medida da versão (uma vez por versão: Minor 3 da rodada 1). Perto do tracemalloc
    (medido com 36 mil OS sintéticas: 25,8 MB aqui, 23,9 MB nele; os índices copiados para medir saem um pouco maiores que os
    de verdade)."""
    lista = atual() if lista is None else lista
    vistos: set = set()
    total = 0

    def conta(o):
        nonlocal total
        if o is None or isinstance(o, bool) or id(o) in vistos or (isinstance(o, int) and -5 <= o <= 256):
            return
        vistos.add(id(o))
        total += sys.getsizeof(o)
        if isinstance(o, tuple):
            for x in o:
                conta(x)
    for r in lista.ordem:
        conta(r)
    for t in lista.por_codigo_ativo.values():
        conta(t)
    for indice in (lista.por_id, lista.por_folio, lista.por_codigo_ativo, lista.nomes_criadores):
        total += sys.getsizeof(dict(indice))
    total += sys.getsizeof(lista.ordem) + sys.getsizeof(lista.a_conferir)
    return round(total / 2**20, 1)


def estado(medir_memoria: bool = False) -> dict:
    """O que se sabe da lista, só com contagens, datas e ids (nunca o texto de uma OS nem o nome de alguém): quantas OS, quantas
    abertas (fora as "a conferir", cujo status é velho), "a conferir" e pendentes; a versão, a última leitura e a janela lida
    inteira; a última entrega de cada faixa e a leitura que a trava de encolhimento recusou (`recusas`); a medida dos campos que
    o REST trouxe; o disco; com `medir_memoria`, a memória da lista (`memoria_estimada`, uma vez por versão); e, com o leitor
    do servidor ligado, o que ele fez."""
    lista = atual()
    leitor = None
    if _LEITOR["estado"] is not None:
        try:
            leitor = _LEITOR["estado"]()
        except Exception as e:                                       # noqa: BLE001 — o estado nunca derruba quem o lê
            leitor = {"erro": "%s: %s" % (type(e).__name__, str(e)[:120])}
    memoria = None
    if medir_memoria:
        if _MEMORIA["versao"] != lista.versao:                       # percorre a lista inteira: uma vez por versão (Minor 3)
            try:
                mb = memoria_estimada(lista)
            except Exception:                                        # noqa: BLE001 — a medida nunca derruba o estado
                log.exception("lista central de OS: a medida da memória falhou (versão %s)", lista.versao)
                mb = None
            _MEMORIA.update(versao=lista.versao, mb=mb)
        memoria = _MEMORIA["mb"]
    pend = dict(_ESTADO["pendentes"])
    return {"n": len(lista.por_id),
            "abertas": sum(1 for r in lista.ordem if r.status_id in ABERTOS and r.id not in lista.a_conferir),
            "a_conferir": len(lista.a_conferir), "a_conferir_ids": sorted(lista.a_conferir)[:20],
            "pendentes": len(pend), "pendentes_ids": sorted(pend)[:20], "versao": lista.versao,
            "lido_em": lista.lido_em or None, "janela": lista.janela,
            "faixas": {k: dict(v) for k, v in list(_ESTADO["faixas"].items())},
            "recusas": {k: dict(v) for k, v in list(_ESTADO["recusas"].items())},
            "campos": dict(_ESTADO["campos"]) if _ESTADO["campos"] else None, "disco": dict(_ESTADO["disco"]),
            "conferencias": {k: dict(v) for k, v in list(_ESTADO["conferencias"].items())},
            "memoria_mb": memoria, "leitor": leitor}
