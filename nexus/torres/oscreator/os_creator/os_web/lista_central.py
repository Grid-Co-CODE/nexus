# os_creator/os_web/lista_central.py
"""As telas do OS Creator lendo da lista central de OS (31/10/2026, tarefa 3.3 do canto central).

Levi, 30/10/2026: "A ideia é não ter um carregamento novo por atividade e sim um ecossistema onde as coisas se aproveitam e
não precisamos ficar fazendo novas requisições sempre!" (desenho `docs/superpowers/specs/2026-10-30-oscreator-canto-central-
design.md`, "Etapa 3"). A 3.1 e a 3.2 fizeram a lista UMA, de todas as OS (`os_creator/os_central.py`), e quem a enche no
servidor (`os_leitor.py`); daqui saem os atalhos das telas para ela: o Histórico e as visões (pelo `rotas.ler_lista`), o
Garantias (`rotas_acomp._linhas`), a marcação verde dos Ativos (`rotas.os_recentes`), o Investigar ativo (pelo índice por
código), o nº da OS → id (`api._wo_id_por_folio`) e a 1ª pintura do card; e as ações que criam ou mudam OS põem a OS nela
(`mudou`, `criadas`).

A lista é lida pela credencial da EMPRESA e vê TODAS as OS. As guardas (decisões AZ a BF da 3.3):
- A VISIBILIDADE DE CADA TELA NÃO MUDA (AZ, fail-closed). A tela que mostra as OS pela sessão da pessoa (a visão dela no
  Fracttal) só lê da lista depois da conferência de 19/10 DELA (`conferir`): 1 pedido de 1 linha na sessão dela, com os
  mesmos filtros da tela, e o total dela batendo com o `contar` da lista (±1%, ou 2 OS: `historico_store.bate`). O total dela
  fica guardado 30 min por pessoa e filtros, na MESMA chave da conferência de 19/10 do Histórico (`historico_store.
  total_conferido`): quem conferiu numa não paga o pedido de novo na outra. Quem dá outro total (a visão restrita), ou cuja
  conferência falhou (o Fracttal fora, a sessão caída), segue pelo caminho de hoje, com a lista dela. A tela que já usava uma
  lista dividida entre todos (a marcação verde dos Ativos, `("cat", "os_recentes")`) segue dividida, sem conferência. O nº →
  id e a 1ª pintura do card não têm filtro para conferir: só para quem conferiu a visão INTEIRA ("Todos", sem etiqueta nem
  status) há menos de 30 min (`liberado`); os outros seguem ao vivo, pela sessão deles, como hoje.
- A GUARDA DA LISTA PELA METADE (BA, a decisão AI da 3.1): a mesma conferência. Cada conferência que foi ao Fracttal conta no
  estado da lista (`os_central.anotar_conferencia`: quantas, quantas divergiram, quantas falharam e a última), e o Raio-X
  mostra: muitas divergências de quem tem a visão inteira é sinal de lista errada.
- OS CAMPOS QUE O REST NÃO TRAZ (BB, Ruling AT): a tela só lê da lista os campos que a última leitura grande trouxe
  (`os_central.campos_medidos`); com 0% (ou sem medida nenhuma) num campo que a tela MOSTRA ou FILTRA, ela vai ao vivo, ou
  aquele filtro troca de jeito (a etiqueta por id vira pelo nome). As listas de cada tela estão em `CAMPOS_*`; a nota do
  chamado, rara numa leitura qualquer, o Garantias confere nas OS dele (sem nenhuma nota entre as de etiqueta CHAMADOS, o
  REST não a trouxe). O card completa ao vivo o que a lista não tem (subtarefas, anexos, OS pai, solicitação), como sempre.
- ONDE A LISTA NÃO COBRE (BC), tudo segue como hoje: o período fora da janela lida inteira (`Lista.cobre`), o `filtrar` que dá
  None (a pessoa que não se identifica, o homônimo), o PC sem leitor (a lista vazia). Nenhum caminho de hoje some.
- AS AÇÕES (BD): `mudou(id)` (o card, o Garantias) e `criadas(resultado)` (as telas de criar) põem a OS na lista DEPOIS de o
  Fracttal confirmar, lida pela sessão da pessoa (`os_central.atualizar_os`: as tarefas e o cabeçalho, 1 a 3 pedidos), só com a
  lista em uso (o PC sem leitor não gasta a leitura). A falha da lista nunca derruba a ação: vai ao log, e a próxima faixa traz
  a OS.
Nada daqui vai ao Fracttal além da conferência (e da leitura da OS que a ação mudou). Nunca levanta para a tela: sem a lista,
None, e a tela segue pelo caminho de hoje.
"""
from __future__ import annotations

import logging
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
# O QUE CADA TELA MOSTRA OU FILTRA (decisão BB): com 0% num destes, a tela vai ao vivo. O Histórico mostra o nº, o cliente, a
# usina e o tipo do ativo (pelo código), a criação (e filtra o período por ela), a data fim e a etiqueta, e filtra pelo tipo de
# tarefa (local); a Visão COS mostra também a programação, o início, o gatilho e quem criou. A descrição, o status, o ativo
# escrito e a equipe vêm das mesmas colunas do REST que o nº e o código (não são medidos); a data do evento cai na programada.
CAMPOS_HISTORICO = (NO, CRIACAO, CODIGO, TIPO, ETQ, FIM)
CAMPOS_COS = CAMPOS_HISTORICO + (PROGRAMADA, INICIO, GATILHO, QUEM_CRIOU)
CAMPOS_GARANTIAS = (NO, CRIACAO, CODIGO, TIPO, ETQ, FIM, RESP_ID)
CAMPOS_ATIVOS = (CRIACAO, CODIGO)
CAMPOS_PREVIA = (NO, CRIACAO)
ETIQUETA_CHAMADOS = "CHAMADOS"             # o Garantias filtra pelo nome (o id custaria o catálogo de etiquetas, e não é guardado)
RECONFERE_S = 60                           # o total guardado há mais que isto e que não bate é pedido de novo (as OS novas)
LIBERA_S = HS.CONFERE_S                    # a conferência da visão inteira que bateu vale isto para o nº → id e a 1ª pintura
VISOES_GUARDADAS = 8                       # as visões prontas (as linhas e o HTML), por versão da lista
CRIADAS_NA_HORA = 3                        # as OS criadas lidas dentro do pedido; as outras, por trás, uma por segundo

_TRAVA = threading.Lock()
_LIBERADOS: dict = {}                      # {pessoa: quando a conferência da visão inteira bateu (o relógio do `historico_store`)}
_VISOES: OrderedDict = OrderedDict()       # {chave: (o catálogo da linha, VisaoCentral)}, as mais usadas por último


def limpar() -> None:
    """Esquece quem está liberado e as visões prontas (os testes; o processo novo começa assim)."""
    with _TRAVA:
        _LIBERADOS.clear()
        _VISOES.clear()


def _em_segundo_plano(fn) -> None:
    """Onde as OS criadas além das `CRIADAS_NA_HORA` são lidas: uma thread solta (os testes trocam)."""
    threading.Thread(target=fn, daemon=True, name="os-web-lista-central").start()


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


# ── as guardas ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _medidos(campos, nomes) -> bool:
    """Todos os `nomes` vieram na última leitura grande (mais que 0%). Sem medida nenhuma, não: a tela vai ao vivo."""
    pct = (campos or {}).get("pct") or {}
    return all((pct.get(n) or 0) > 0 for n in nomes)


def liberado(pessoa) -> bool:
    """A pessoa conferiu a visão INTEIRA (o total dela de "Todos", sem etiqueta nem status, batendo com a lista) há menos de
    `LIBERA_S`: ela vê no Fracttal o que a lista vê, e o nº → id e a 1ª pintura do card podem vir da lista."""
    if not pessoa or pessoa == "?":
        return False
    with _TRAVA:
        q = _LIBERADOS.get(pessoa)
    return q is not None and HS._relogio() - q < LIBERA_S


def conferir(pessoa, chave, total_da_pessoa, conta: int, visao: str, *, forcar: bool = False,
             libera: bool = False) -> bool:
    """A conferência de 19/10 da pessoa contra a lista central (AZ e BA): o total que o Fracttal dá a ELA com os filtros da
    tela (`total_da_pessoa()`, 1 pedido de 1 linha na sessão dela, guardado 30 min pela chave) bate com `conta` (o `contar`
    da lista)? O total guardado há mais de `RECONFERE_S` que não bate é pedido de novo (as OS criadas desde então); `forcar`
    (o ↻) pede sempre. A que falha (o Fracttal fora, a sessão caída) devolve False e não libera nada. Cada conferência que foi
    ao Fracttal conta no estado da lista. `libera`: a visão inteira (marca a pessoa em `liberado`)."""
    try:
        dela, idade, pedido = HS.total_conferido(pessoa, chave, total_da_pessoa, 0 if forcar else HS.CONFERE_S)
        if not HS.bate(dela, conta) and idade > RECONFERE_S:
            dela, idade, pedido = HS.total_conferido(pessoa, chave, total_da_pessoa, 0)
    except Exception as e:                                           # noqa: BLE001 — sem conferir, a tela segue como hoje
        os_central.anotar_conferencia(visao, None)
        log.info("lista central de OS: a conferência da visão %s falhou (%s); a tela segue ao vivo", visao,
                 type(e).__name__)
        return False
    ok = HS.bate(dela, conta)
    if pedido:                                                       # só a que foi ao Fracttal conta (a guardada já contou)
        os_central.anotar_conferencia(visao, ok, fracttal=dela, lista=conta)
    if libera and pessoa and pessoa != "?":
        with _TRAVA:
            if ok:
                _LIBERADOS[pessoa] = HS._relogio()
                if len(_LIBERADOS) > 2000:
                    for k in sorted(_LIBERADOS, key=_LIBERADOS.get)[:len(_LIBERADOS) - 2000]:
                        _LIBERADOS.pop(k, None)
            else:
                _LIBERADOS.pop(pessoa, None)                         # a visão dela mudou: o atalho fecha na hora
    return ok


# ── a visão pronta do Histórico ────────────────────────────────────────────────────────────────────────────────────────
class VisaoCentral:
    """Uma visão do Histórico lida da lista central, no feitio da `historico_store.Lista` (as linhas no formato do
    `api.list_minhas_os`, o `info` com o total e o teto, a hora da lista e o HTML das linhas guardado por versão): a rota e o
    template não precisam saber de onde ela veio. As linhas são de quem a montou (dicionários novos, `RegistroOS.linha`), e a
    visão é a mesma para quem pede o mesmo (as pessoas conferidas de "Todos" dividem a mesma)."""
    central = True

    def __init__(self, linhas, info, criada_em, versao):
        self.linhas, self.info, self.criada_em, self.versao = linhas, dict(info), float(criada_em or time.time()), versao
        self.html: dict = {}
        self.preparada = False


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
    de AGORA (a lista e o catálogo de ativos; a hora da última leitura, pelo minuto, é a "Lista das HH:MM"), no máximo
    `VISOES_GUARDADAS`: a de uma versão velha nunca mais é pedida, e cada uma são até 2.000 linhas e o HTML delas (o servidor
    anda apertado de memória)."""
    geracao = (lista.versao, int(lista.lido_em // 60), id(local))
    k = geracao + tuple(chave)
    with _TRAVA:
        v = _VISOES.get(k)
        if v is not None and v[0] is local:
            _VISOES.move_to_end(k)
            return v[1]
    corte = registros[:cap] if cap else registros
    visao = VisaoCentral(_linhas(lista, corte, local), {"total": len(registros), "cap": cap}, lista.lido_em, lista.versao)
    with _TRAVA:
        for velha in [x for x in _VISOES if x[:3] != geracao]:
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
    a lista cobre o período, tem os campos da tela, sabe quem é a pessoa e responde (`filtrar`); só então a conferência (1
    pedido na 1ª vez), e só com ela a lista vale."""
    try:
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

        def total_da_pessoa():
            return (api.list_minhas_os_pagina(modo_srv, id_account, id_label, de, ate, status_ids, "", 1, 1)
                    or {}).get("total") or 0
        if not conferir(pessoa, chave, total_da_pessoa, len(sel), visao, forcar=forcar,
                        libera=visao == "todos" and not id_label and not status_ids):
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
    da conferência da Visão COS: quem abriu uma não confere de novo na outra). Volta uma `VisaoCentral` com as OS que têm o
    código do ativo ou um código da usina (pelo catálogo de ativos): quem chama recorta como sempre (`investigar_web`)."""
    try:
        lista = os_central.atual()
        if not (lista.cobre(de, ate) and lista.cobre(conf_de, conf_ate)):
            return None
        if not _medidos(os_central.campos_medidos(), CAMPOS_HISTORICO):
            return None
        n = os_central.contar("todos", None, conf_de, conf_ate)
        if n is None:
            return None
        chave = ("hist", "TODOS", "criadas", "TODOS", None, conf_de, conf_ate, ())

        def total_da_pessoa():
            return (api.list_minhas_os_pagina("criadas", "TODOS", None, conf_de, conf_ate, None, "", 1, 1)
                    or {}).get("total") or 0
        if not conferir(pessoa, chave, total_da_pessoa, n, "todos", forcar=forcar, libera=True):
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


def garantias(de, pessoa) -> dict | None:
    """As OS com a etiqueta CHAMADOS criadas desde `de` (o que o `api.list_chamados` dá ao quadro de Garantias), da lista
    central: {"linhas", "total", "lido_em"}, ou None (o caminho de hoje). A conferência é a do quadro (`api.total_chamados`,
    a MESMA chave do `rotas_acomp._dono`): quem monta a cópia do quadro tem de ver no Fracttal o mesmo total. Sem nenhuma nota
    do chamado entre as OS da etiqueta, o REST não a trouxe (o cartão do quadro se monta pela nota): ao vivo. E com uma OS do
    quadro "a conferir" também: a coluna dela sai do status, e o quadro não tem como dizer que ele pode ser velho (o Histórico
    diz, ao lado do nº); a faixa que a traz de volta (as finalizadas, de hora em hora) devolve o quadro à lista."""
    try:
        lista = os_central.atual()
        if not lista.cobre(de, None) or not _medidos(os_central.campos_medidos(), CAMPOS_GARANTIAS):
            return None
        sel = os_central.filtrar("todos", None, de, None, etiqueta=ETIQUETA_CHAMADOS)
        if sel is None or (sel and not any(r.note for r in sel)) or any(lista.conferir(r.id) for r in sel):
            return None
        if not conferir(pessoa, ("acomp", "TODOS"), lambda: api.total_chamados(de), len(sel), "garantias"):
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
    """O id da OS pelo nº, da lista central (sem pedido), para quem conferiu a visão inteira (`liberado`); senão None, e o
    `api._wo_id_por_folio` lê ao vivo, pela sessão da pessoa, como sempre. É o gancho `api.ID_PELA_LISTA`."""
    try:
        if not liberado(quem()) or not _medidos(os_central.campos_medidos(), (NO,)):
            return None
        return os_central.folio_para_id(folio)
    except Exception:                                                # noqa: BLE001 — o nº segue ao vivo
        log.exception("lista central de OS: o nº %s não foi achado pela lista (segue ao vivo)", folio)
        return None


def previa(wid) -> dict | None:
    """A linha da OS para a 1ª pintura do card (o nº, o tipo, o status, o ativo, as datas, quem criou e com quem está), da
    lista central, ou None: o card abre como sempre, só com a leitura ao vivo. Só para quem conferiu a visão inteira
    (`liberado`): o card é aberto pelo id, que pode vir de qualquer tela."""
    try:
        if not liberado(quem()) or not _medidos(os_central.campos_medidos(), CAMPOS_PREVIA):
            return None
        lista = os_central.atual()
        r = lista.por_id.get(_int(wid))
        return None if r is None else _linhas(lista, [r], api._code_to_loc())[0]
    except Exception:                                                # noqa: BLE001 — o card abre como sempre
        log.exception("lista central de OS: a 1ª pintura do card da OS %s não saiu da lista", wid)
        return None


# ── as ações põem a OS na lista ────────────────────────────────────────────────────────────────────────────────────────
def mudou(wid) -> bool:
    """A OS que a ação acabou de criar ou mudar (o Fracttal já confirmou) entra na lista central na hora, lida pela sessão da
    pessoa (`os_central.atualizar_os`, o que o card já lê). A falha da lista nunca derruba a ação: vai ao log, e a próxima
    faixa a traz. True se entrou.

    Só com a lista EM USO (uma leitura do leitor já disse a janela que ela cobre: o servidor, pela cópia em disco ou pelas
    faixas). Sem ela (o PC sem leitor, a máquina recém-subida sem cópia), nenhuma tela lê da lista, e a leitura da OS seriam 1
    a 3 pedidos à toa a cada ação. Caso que criou a regra (31/10/2026, na 1ª rodada dos testes da 3.3): sem esta guarda, a
    ação lia a OS mesmo onde ninguém lê a lista, e nos testes antigos do quadro, que não trocam o `_rpc_call`, a leitura saiu
    da máquina (recusada com 401, o JWT de mentira) e a sessão recusada derrubou o login da pessoa no pedido seguinte."""
    try:
        if not os_central.atual().janela[0]:
            return False
        return bool(os_central.atualizar_os(wid))
    except Exception:                                                # noqa: BLE001 — a ação já valeu no Fracttal
        log.exception("lista central de OS: a OS %s não entrou na lista depois da ação (a ação valeu; a próxima faixa a "
                      "traz)", wid)
        return False


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
    """As OS que uma tela de criar acabou de criar entram na lista: as `CRIADAS_NA_HORA` primeiras dentro do pedido (juntas, na
    sessão da pessoa: a OS criada não some do Histórico até a próxima volta), as outras por trás, uma por segundo (a criação de
    muitas de uma vez não vira uma rajada na cota da empresa, e a resposta à pessoa não espera por elas). Quantas entraram na
    hora."""
    try:
        ids = ids_criados(resultado)
        if not ids or not os_central.atual().janela[0]:              # a lista fora de uso: nada a ler (ver `mudou`)
            return 0
        agora, depois = ids[:CRIADAS_NA_HORA], ids[CRIADAS_NA_HORA:]
        if len(agora) == 1:
            n = int(mudou(agora[0]))
        else:
            with api._ExecutorComContexto(max_workers=len(agora)) as ex:
                n = sum(1 for ok in ex.map(mudou, agora) if ok)
        if depois:
            jwt, email = sessao.jwt_atual(), sessao.email_atual()

            def ler_as_outras():
                with sessao.contexto(jwt, email):
                    for wid in depois:
                        time.sleep(1.0)
                        mudou(wid)
            _em_segundo_plano(ler_as_outras)
        return n
    except Exception:                                                # noqa: BLE001 — a criação já valeu no Fracttal
        log.exception("lista central de OS: as OS criadas não entraram na lista (a criação valeu; a próxima faixa as traz)")
        return 0


# o nº → id do `api` passa por aqui (sem o gancho, o oem e o desktop seguem com a leitura de sempre)
api.ID_PELA_LISTA = id_por_folio
