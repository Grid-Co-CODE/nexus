# os_creator/os_web/lista_central.py
"""As telas do OS Creator lendo da lista central de OS (31/10/2026, tarefa 3.3 do canto central).

Levi, 30/10/2026: "A ideia é não ter um carregamento novo por atividade e sim um ecossistema onde as coisas se aproveitam e
não precisamos ficar fazendo novas requisições sempre!" (desenho `docs/superpowers/specs/2026-10-30-oscreator-canto-central-
design.md`, "Etapa 3"). A 3.1 e a 3.2 fizeram a lista UMA, de todas as OS (`os_creator/os_central.py`), e quem a enche no
servidor (`os_leitor.py`); daqui saem os atalhos das telas para ela: o Histórico e as visões (pelo `rotas.ler_lista`), o
Garantias (`rotas_acomp._linhas`), a marcação verde dos Ativos (`rotas.os_recentes`), o Investigar ativo (pelo índice por
código), o nº da OS → id (`api._wo_id_por_folio`) e a 1ª pintura do card; e as ações que criam ou mudam OS põem a OS nela
(`mudou`, `criadas`).

A lista é lida pela credencial da EMPRESA e vê TODAS as OS. As guardas (decisões AZ a BF da 3.3 e os Rulings BP a BR da rodada
1 de correções, que fecharam dois vazamentos para a visão restrita que uma sonda da revisão provou):
- A VISIBILIDADE DE CADA TELA NÃO MUDA (AZ, fail-closed). A tela que mostra as OS pela sessão da pessoa (a visão dela no
  Fracttal) só lê da lista depois da conferência de 19/10 DELA (`conferir`): 1 pedido de 1 linha na sessão dela, com os
  mesmos filtros da tela. O total dela fica guardado 30 min por pessoa e filtros, na MESMA chave da conferência de 19/10 do
  Histórico (`historico_store.total_conferido`): quem conferiu numa não paga o pedido de novo na outra. A conferência é DE UMA
  MÃO SÓ (Ruling BQ): a lista nunca pode ter mais OS que o total que o Fracttal dá à pessoa (diferença com a lista maior é OS
  escondida aparecendo: a sonda mostrou, com a folga de 2 OS da regra de 19/10, uma OS que o Fracttal esconde da pessoa, num
  "Criado por" outra pessoa de um dia só). Nas visões por pessoa e no ↻, igual; na "Todos" sem o ↻, a lista pode ter menos
  até o atraso das OS novas (`max(2, 1%)`). Quem não passa, ou cuja conferência falhou (o Fracttal fora, a sessão caída), segue
  pelo caminho de hoje, com a lista dela; quem divergiu não é conferido de novo por 30 min (`_DIVERGIU`). A tela que já usava
  uma lista dividida entre todos (a marcação verde dos Ativos, `("cat", "os_recentes")`) segue dividida, sem conferência.
- O Nº → ID E A 1ª PINTURA DO CARD (Ruling BP): não têm filtro para conferir, e abrem uma OS qualquer pelo id. Só para quem
  conferiu a visão INTEIRA num escopo fixo e grande: "Todos", sem etiqueta nem status, nos 30 dias padrão até hoje, com pelo
  menos `LIBERA_MIN_OS` OS na lista, pela regra de uma mão (`liberado`). E só para a OS criada dentro desse escopo: a mais
  velha vai ao vivo, e o Fracttal decide. A sonda liberou a pessoa restrita por um período invertido, por um dia quieto (0 e
  0), por um dia em que todas as OS eram dela e pelo Investigar fora dos 30 dias: nenhum desses libera mais.
- A GUARDA DA LISTA PELA METADE (BA, a decisão AI da 3.1): a mesma conferência. Cada conferência que foi ao Fracttal conta no
  estado da lista (`os_central.anotar_conferencia`: quantas, quantas divergiram, quantas falharam e a última), e o Raio-X
  mostra: muitas divergências de quem tem a visão inteira é sinal de lista errada.
- OS CAMPOS QUE O REST NÃO TRAZ (BB, Ruling AT): a tela só lê da lista os campos que a última leitura grande trouxe
  (`os_central.campos_medidos`); com 0% (ou sem medida nenhuma) num campo que a tela MOSTRA ou FILTRA, ela vai ao vivo, ou
  aquele filtro troca de jeito (a etiqueta por id vira pelo nome). As listas de cada tela estão em `CAMPOS_*`; a nota do
  chamado, rara numa leitura qualquer, o Garantias confere nas OS dele (sem nenhuma nota entre as de etiqueta CHAMADOS, o
  REST não a trouxe), e a nota cortada no teto (`nota_cortada`, Ruling BR) também o leva ao vivo. O card completa ao vivo o
  que a lista não tem (subtarefas, anexos, OS pai, solicitação), como sempre.
- ONDE A LISTA NÃO COBRE (BC), tudo segue como hoje: o período inválido ou fora da janela lida inteira (`Lista.cobre`), o
  `filtrar` que dá None (a pessoa que não se identifica, o homônimo), o PC sem leitor (a lista vazia). Nenhum caminho de hoje
  some.
- AS AÇÕES (BD): `mudou(id)` (o card, o Garantias) e `criadas(resultado)` (as telas de criar) põem a OS na lista DEPOIS de o
  Fracttal confirmar, lida pela sessão da pessoa (`os_central.atualizar_os`: as tarefas e o cabeçalho, 1 a 3 pedidos), só com a
  lista em uso, e com prazo (`RELEITURA_MAX_S`): passou dele, a resposta sai e a OS fica pendente para a faixa. A falha da
  lista nunca derruba a ação: vai ao log, e a próxima faixa traz a OS.
Nada daqui vai ao Fracttal além da conferência (e da leitura da OS que a ação mudou). Nunca levanta para a tela: sem a lista,
None, e a tela segue pelo caminho de hoje.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import logging
import re
import threading
import time
import unicodedata
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

import api
import os_central

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
# fim e a etiqueta, e filtra pelo tipo de tarefa (local); a Visão COS mostra também a programação, o início, o gatilho, a
# equipe e quem criou; o Garantias, o responsável (o nome e o id, a cor da equipe) e a descrição. A data do evento cai na
# programada (não é medida).
CAMPOS_HISTORICO = (NO, CRIACAO, CODIGO, TIPO, ETQ, FIM, DESCRICAO, ATIVO, STATUS)
CAMPOS_COS = CAMPOS_HISTORICO + (PROGRAMADA, INICIO, GATILHO, QUEM_CRIOU, EQUIPE)
CAMPOS_GARANTIAS = (NO, CRIACAO, CODIGO, TIPO, ETQ, FIM, RESP_ID, ATRIBUIDO, DESCRICAO, STATUS)
CAMPOS_ATIVOS = (CRIACAO, CODIGO)
CAMPOS_PREVIA = (NO, CRIACAO, DESCRICAO, ATIVO, STATUS)
ETIQUETA_CHAMADOS = "CHAMADOS"             # o Garantias filtra pelo nome (o id custaria o catálogo de etiquetas, e não é guardado)
EXATA, TODOS = "exata", "todos"            # as regras da conferência (ver `_bate`)
ESCOPO_DIAS = 30                           # o escopo que libera o nº → id e a 1ª pintura: os 30 dias padrão do Histórico
LIBERA_MIN_OS = 20                         # ... com pelo menos tantas OS na lista (o período quieto não diz que a pessoa vê tudo)
LIBERA_S = HS.CONFERE_S                    # a conferência da visão inteira que bateu vale isto para o nº → id e a 1ª pintura
DIVERGIU_S = HS.CONFERE_S                  # quem divergiu não é conferido de novo por isto (o Raio-X a conta uma vez)
VISOES_GUARDADAS = 8                       # as visões prontas (as linhas e o HTML), da versão de agora da lista
CRIADAS_NA_HORA = 3                        # as OS criadas lidas dentro do pedido; as outras, a faixa das novas traz (até 3 min)
RELEITURA_MAX_S = 5.0                      # o prazo da releitura da OS depois da ação, além da gravação (Minor 2 da rodada 1)

_TRAVA = threading.Lock()
_LIBERADOS: dict = {}                      # {pessoa: (quando, de, até) do escopo que a conferência liberou}
_DIVERGIU: dict = {}                       # {(pessoa, chave): quando a conferência dela divergiu, com o total pedido agora}
_VISOES: OrderedDict = OrderedDict()       # {chave: (o catálogo da linha, VisaoCentral)}, as mais usadas por último
_RELEITURAS: set = set()                   # as releituras de ações em curso (`esperar_releituras`)
_EXECUTOR: dict = {"ex": None}             # as releituras correm aqui, com o contexto da sessão copiado (nasce no 1º uso)


def limpar() -> None:
    """Esquece quem está liberado, as divergências e as visões prontas (os testes; o processo novo começa assim)."""
    with _TRAVA:
        _LIBERADOS.clear()
        _DIVERGIU.clear()
        _VISOES.clear()


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


def _escopo_padrao(de, ate) -> bool:
    """[de, ate] é o escopo fixo que libera (Ruling BP): os 30 dias padrão do Histórico até hoje, as mesmas datas que a rota
    põe quando a pessoa não escolhe outras."""
    hoje = dt.date.today()
    return str(de) == (hoje - dt.timedelta(days=ESCOPO_DIAS)).isoformat() and str(ate) == hoje.isoformat()


# ── as guardas ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _medidos(campos, nomes) -> bool:
    """Todos os `nomes` vieram na última leitura grande (mais que 0%). Sem medida nenhuma, não: a tela vai ao vivo."""
    pct = (campos or {}).get("pct") or {}
    return all((pct.get(n) or 0) > 0 for n in nomes)


def _bate(dela, conta, regra) -> bool:
    """A conferência de uma mão (Ruling BQ): a lista (`conta`) nunca tem mais OS que o total que o Fracttal dá à pessoa
    (`dela`). EXATA (as visões por pessoa e o ↻): o mesmo número. TODOS ("Todos" sem o ↻): a lista pode ter menos até o atraso
    das OS novas, `max(2, 1%)` (as criadas desde a última leitura do servidor, de 3 em 3 min)."""
    dela, conta = int(dela or 0), int(conta or 0)
    if conta > dela:
        return False
    if regra == EXATA:
        return conta == dela
    return dela - conta <= max(2, HS.TOLERANCIA * dela)


def _escopo_liberado(pessoa):
    """(de, até) do escopo que a conferência da visão inteira liberou para a pessoa há menos de `LIBERA_S`, ou None."""
    if not pessoa or pessoa == "?":
        return None
    with _TRAVA:
        v = _LIBERADOS.get(pessoa)
    if v is None or HS._relogio() - v[0] >= LIBERA_S:
        return None
    return v[1], v[2]


def liberado(pessoa) -> bool:
    """A pessoa conferiu a visão INTEIRA no escopo fixo (Ruling BP) há menos de `LIBERA_S`: ela vê no Fracttal o que a lista vê
    nesses 30 dias, e o nº → id e a 1ª pintura do card de uma OS criada neles podem vir da lista."""
    return _escopo_liberado(pessoa) is not None


def _no_escopo(pessoa, r) -> bool:
    """A OS foi criada dentro do escopo que liberou a pessoa (a data de criação, em UTC, como o `filtrar`)."""
    esc = _escopo_liberado(pessoa)
    return esc is not None and r is not None and esc[0] <= r.data[:10] <= esc[1]


def conferir(pessoa, chave, total_da_pessoa, conta: int, visao: str, *, regra: str = EXATA, forcar: bool = False,
             libera=None) -> bool:
    """A conferência de 19/10 da pessoa contra a lista central (AZ, BA e a regra de uma mão do Ruling BQ): o total que o
    Fracttal dá a ELA com os filtros da tela (`total_da_pessoa()`, 1 pedido de 1 linha na sessão dela, guardado 30 min pela
    chave) contra `conta` (o `contar` da lista), pela `regra` (`_bate`; o ↻, `forcar`, é sempre EXATA e pede sempre).
    - O total guardado que não passa é pedido de novo uma vez (a lista ganhou as OS novas desde então), salvo quando a pessoa
      divergiu há menos de `DIVERGIU_S`: a visão restrita diverge sempre, e não paga um pedido a cada visita (Minor 3).
    - A que falha (o Fracttal fora, a sessão caída) devolve False e não libera nada.
    - Só a conferência que foi ao Fracttal conta no estado da lista.
    - `libera`: (de, até) quando esta é a conferência do escopo fixo que libera (`liberado`); a que não passa fecha o atalho."""
    if forcar:
        regra = EXATA
    k = (pessoa, chave)
    agora = HS._relogio()
    with _TRAVA:
        q = _DIVERGIU.get(k)
    divergiu_ha_pouco = not forcar and q is not None and agora - q < DIVERGIU_S
    try:
        dela, _idade, pedido = HS.total_conferido(pessoa, chave, total_da_pessoa, 0 if forcar else HS.CONFERE_S)
        if not _bate(dela, conta, regra) and not pedido and not divergiu_ha_pouco:
            dela, _idade, pedido = HS.total_conferido(pessoa, chave, total_da_pessoa, 0)
    except Exception as e:                                           # noqa: BLE001 — sem conferir, a tela segue como hoje
        os_central.anotar_conferencia(visao, None)
        log.info("lista central de OS: a conferência da visão %s falhou (%s); a tela segue ao vivo", visao,
                 type(e).__name__)
        return False
    ok = _bate(dela, conta, regra)
    if pedido:                                                       # só a que foi ao Fracttal conta (a guardada já contou)
        os_central.anotar_conferencia(visao, ok, fracttal=dela, lista=conta)
    with _TRAVA:
        if ok:
            _DIVERGIU.pop(k, None)
        elif pedido:                                                 # o total pedido agora: o que ela vê é outro
            _DIVERGIU[k] = agora
            if len(_DIVERGIU) > 4000:
                for x in sorted(_DIVERGIU, key=_DIVERGIU.get)[:len(_DIVERGIU) - 4000]:
                    _DIVERGIU.pop(x, None)
        if libera is not None and pessoa and pessoa != "?":
            if ok:
                _LIBERADOS[pessoa] = (agora, str(libera[0]), str(libera[1]))
                if len(_LIBERADOS) > 2000:
                    for x in sorted(_LIBERADOS, key=lambda p: _LIBERADOS[p][0])[:len(_LIBERADOS) - 2000]:
                        _LIBERADOS.pop(x, None)
            else:
                _LIBERADOS.pop(pessoa, None)                         # a visão dela mudou: o atalho fecha na hora
    return ok


# ── a visão pronta do Histórico ────────────────────────────────────────────────────────────────────────────────────────
class VisaoCentral:
    """Uma visão do Histórico lida da lista central, no feitio da `historico_store.Lista` (as linhas no formato do
    `api.list_minhas_os`, o `info` com o total e o teto, a hora da lista e o HTML das linhas guardado por versão): a rota e o
    template não precisam saber de onde ela veio. As linhas são de quem a montou (dicionários novos, `RegistroOS.linha`), e a
    visão é a mesma para quem pede o mesmo (as pessoas conferidas de "Todos" dividem a mesma). A hora ("Lista das HH:MM") é a
    da última leitura do Fracttal que a lista teve, enquanto a versão dela for esta: a leitura que não trouxe nada não muda a
    versão, e a visão não é montada de novo por isso (Minor 5 da rodada 1)."""
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
    o id da pessoa. O que casa sem ambiguidade a lista decide (`os_central.filtrar`); a conferência confere."""
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
    conferência (1 pedido na 1ª vez; "Todos" pela regra TODOS, as visões por pessoa e o ↻ pela EXATA), e só com ela a lista
    vale. Só a "Todos" sem etiqueta nem status nos 30 dias padrão, com pelo menos `LIBERA_MIN_OS` OS, libera o nº → id."""
    try:
        if not periodo_valido(de, ate):
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
        filtros = (modo_srv, id_account, id_label, de, ate, tuple(status_ids or ()))
        # "Todos" usa a MESMA chave da conferência de 19/10 do caminho de hoje (`rotas.ler_lista`): o total é o mesmo
        chave = (("hist", "TODOS") if visao == "todos" else ("hist", "central")) + filtros
        libera = ((de, ate) if visao == "todos" and not id_label and not status_ids and _escopo_padrao(de, ate)
                  and len(sel) >= LIBERA_MIN_OS else None)

        def total_da_pessoa():
            return (api.list_minhas_os_pagina(modo_srv, id_account, id_label, de, ate, status_ids, "", 1, 1)
                    or {}).get("total") or 0
        if not conferir(pessoa, chave, total_da_pessoa, len(sel), visao, regra=TODOS if visao == "todos" else EXATA,
                        forcar=forcar, libera=libera):
            return None
        quem_lista = None if visao == "todos" else tuple(sorted((pessoa_lista or {}).items()))
        return _visao_pronta(lista, (visao, quem_lista, etq, de, ate, tuple(status_ids or ())), sel, api._code_to_loc(),
                             api.HISTORICO_CAP if cap is None else cap)
    except Exception:                                                # noqa: BLE001 — a tela segue pelo caminho de hoje
        log.exception("lista central de OS: o Histórico não leu da lista (segue ao vivo)")
        return None


def investigar(code, usina_curta, de, ate, conf_de, conf_ate, *, pessoa, forcar=False):
    """As OS do "Investigar ativo" (o ativo e a usina dele, no período [de, ate]) pelo índice por código de ativo da lista
    central (decisão BE), ou None: o caminho de hoje (a lista de "Todos" do Histórico). A conferência é a da visão inteira no
    período carregado (`conf_de`, `conf_ate`: os 30 dias da Visão COS quando o período cabe neles, como hoje; a MESMA chave
    da conferência da Visão COS: quem abriu uma não confere de novo na outra), pela regra TODOS (EXATA no ↻); só a dos 30 dias
    padrão libera o nº → id. Volta uma `VisaoCentral` com as OS que têm o código do ativo ou um código da usina (pelo catálogo
    de ativos): quem chama recorta como sempre (`investigar_web`)."""
    try:
        if not (periodo_valido(de, ate) and periodo_valido(conf_de, conf_ate)):
            return None
        lista = os_central.atual()
        if not (lista.cobre(de, ate) and lista.cobre(conf_de, conf_ate)):
            return None
        if not _medidos(os_central.campos_medidos(), CAMPOS_HISTORICO):
            return None
        n = os_central.contar("todos", None, conf_de, conf_ate)
        if n is None:
            return None
        chave = ("hist", "TODOS", "criadas", "TODOS", None, conf_de, conf_ate, ())
        libera = (conf_de, conf_ate) if _escopo_padrao(conf_de, conf_ate) and n >= LIBERA_MIN_OS else None

        def total_da_pessoa():
            return (api.list_minhas_os_pagina("criadas", "TODOS", None, conf_de, conf_ate, None, "", 1, 1)
                    or {}).get("total") or 0
        if not conferir(pessoa, chave, total_da_pessoa, n, "todos", regra=TODOS, forcar=forcar, libera=libera):
            return None
        local = api._code_to_loc()
        codigos = {str(code).strip()} if str(code or "").strip() else set()
        uc = _norm(usina_curta)
        if uc:
            codigos |= {c for c, v in local.items() if v and _norm(v[1]) == uc}
        achadas: dict = {}
        for c in codigos:
            for r in lista.por_codigo_ativo.get(c, ()):
                if de <= r.data[:10] <= ate:
                    achadas[r.id] = r
        regs = sorted(achadas.values(), key=lambda r: (r.data, r.id), reverse=True)
        return VisaoCentral(_linhas(lista, regs, local), {"total": len(regs), "cap": 0}, lista.lido_em, lista.versao)
    except Exception:                                                # noqa: BLE001 — a janela segue pelo caminho de hoje
        log.exception("lista central de OS: o Investigar ativo não leu da lista (segue ao vivo)")
        return None


def garantias(de, pessoa, forcar=False) -> dict | None:
    """As OS com a etiqueta CHAMADOS criadas desde `de` (o que o `api.list_chamados` dá ao quadro de Garantias), da lista
    central: {"linhas", "total", "lido_em"}, ou None (o caminho de hoje). A conferência é a do quadro (`api.total_chamados`,
    a MESMA chave do `rotas_acomp._dono`), pela regra TODOS (EXATA no Atualizar e na releitura por trás, `forcar`): quem monta
    a cópia do quadro tem de ver no Fracttal ao menos as OS que a lista tem. Vai ao vivo também:
    - sem nenhuma nota do chamado entre as OS da etiqueta: o REST não a trouxe (o cartão do quadro se monta pela nota);
    - com uma OS do quadro "a conferir": a coluna dela sai do status, e o quadro não tem como dizer que ele pode ser velho (o
      Histórico diz, ao lado do nº); a faixa que a traz de volta (as finalizadas, de hora em hora) devolve o quadro à lista;
    - com uma nota cortada no teto (`nota_cortada`, Ruling BR): o "parado há N dias" sai do FIM da nota (o histórico da
      retroativa), e a nota pela metade não vai ao quadro como inteira."""
    try:
        lista = os_central.atual()
        if not lista.cobre(de, None) or not _medidos(os_central.campos_medidos(), CAMPOS_GARANTIAS):
            return None
        sel = os_central.filtrar("todos", None, de, None, etiqueta=ETIQUETA_CHAMADOS)
        if (sel is None or (sel and not any(r.note for r in sel)) or any(lista.conferir(r.id) for r in sel)
                or any(r.nota_cortada for r in sel)):
            return None
        if not conferir(pessoa, ("acomp", "TODOS"), lambda: api.total_chamados(de), len(sel), "garantias", regra=TODOS,
                        forcar=forcar):
            return None
        return {"linhas": _linhas(lista, sel, api._code_to_loc()), "total": len(sel), "lido_em": lista.lido_em}
    except Exception:                                                # noqa: BLE001 — o quadro segue pelo caminho de hoje
        log.exception("lista central de OS: o Garantias não leu da lista (segue ao vivo)")
        return None


def codigos_recentes(dias) -> list | None:
    """Os códigos dos ativos com OS criada nos últimos `dias` (a marcação verde dos Ativos, `api.codigos_os_recentes`), da
    lista central, ou None (o caminho de hoje). Sem conferência: a de hoje já é uma só para todos (`("cat", "os_recentes")`,
    lida pela sessão de quem chegou primeiro), e segue dividida (decisão AZ)."""
    try:
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
    `api.ID_PELA_LISTA`."""
    try:
        pessoa = quem()
        if not liberado(pessoa) or not _medidos(os_central.campos_medidos(), (NO, CRIACAO)):
            return None
        wid = os_central.folio_para_id(folio)
        if wid is None:
            return None
        return wid if _no_escopo(pessoa, os_central.atual().por_id.get(wid)) else None
    except Exception:                                                # noqa: BLE001 — o nº segue ao vivo
        log.exception("lista central de OS: o nº %s não foi achado pela lista (segue ao vivo)", folio)
        return None


def previa(wid) -> dict | None:
    """A linha da OS para a 1ª pintura do card (o nº, o tipo, o status, o ativo, as datas, quem criou e com quem está), da
    lista central, ou None: o card abre como sempre, só com a leitura ao vivo. Só para quem está liberado, e só da OS criada no
    escopo que o liberou (Ruling BP): o card é aberto pelo id, que pode vir de qualquer tela."""
    try:
        pessoa = quem()
        if not liberado(pessoa) or not _medidos(os_central.campos_medidos(), CAMPOS_PREVIA):
            return None
        lista = os_central.atual()
        r = lista.por_id.get(_int(wid))
        return None if not _no_escopo(pessoa, r) else _linhas(lista, [r], api._code_to_loc())[0]
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
    (`os_central.marcar_pendente`), e segue por trás: quando termina, põe a OS na lista do mesmo jeito. A que falhou vai ao
    log."""
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
    return entraram


def mudou(wid):
    """A OS que a ação acabou de mudar (o Fracttal já confirmou) entra na lista central na hora, lida pela sessão da pessoa
    (`os_central.atualizar_os`, o que o card já lê), com o prazo de `_reler`. O registro como entrou (o `api_finalizar` usa o
    status dele, sem reler o cabeçalho), ou None. A falha da lista nunca derruba a ação: vai ao log, e a próxima faixa a traz.

    Só com a lista EM USO (uma leitura do leitor já disse a janela que ela cobre: o servidor, pela cópia em disco ou pelas
    faixas). Sem ela (o PC sem leitor, a máquina recém-subida sem cópia), nenhuma tela lê da lista, e a leitura da OS seriam 1
    a 3 pedidos à toa a cada ação. Caso que criou a regra (31/10/2026, na 1ª rodada dos testes da 3.3): sem esta guarda, a
    ação lia a OS mesmo onde ninguém lê a lista, e nos testes antigos do quadro, que não trocam o `_rpc_call`, a leitura saiu
    da máquina (recusada com 401, o JWT de mentira) e a sessão recusada derrubou o login da pessoa no pedido seguinte."""
    try:
        if not os_central.atual().janela[0]:
            return None
        return _reler([wid]).get(wid)
    except Exception:                                                # noqa: BLE001 — a ação já valeu no Fracttal
        log.exception("lista central de OS: a OS %s não entrou na lista depois da ação (a ação valeu; a próxima faixa a "
                      "traz)", wid)
        return None


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
        if not ids or not os_central.atual().janela[0]:              # a lista fora de uso: nada a ler (ver `mudou`)
            return 0
        agora, depois = ids[:CRIADAS_NA_HORA], ids[CRIADAS_NA_HORA:]
        if depois:
            log.info("lista central de OS: %d OS criadas além das %d primeiras ficam para a faixa das novas", len(depois),
                     CRIADAS_NA_HORA)
        return len(_reler(agora))
    except Exception:                                                # noqa: BLE001 — a criação já valeu no Fracttal
        log.exception("lista central de OS: as OS criadas não entraram na lista (a criação valeu; a próxima faixa as traz)")
        return 0


# o nº → id do `api` passa por aqui (sem o gancho, o oem e o desktop seguem com a leitura de sempre)
api.ID_PELA_LISTA = id_por_folio
