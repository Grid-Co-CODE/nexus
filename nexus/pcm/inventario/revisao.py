"""A revisão de uma contagem pelo PCM (Levi, 26/10/2026; desenho, seção 4.2): o que a aba Inventário mostra (a lista das
contagens e a contagem aberta, com o Sistema × Contado × Δ × Situação e os seis grupos da confirmação) e o que o PCM faz nela
(tirar uma peça do lote, corrigir o número, pedir a recontagem só das peças marcadas ou a da contagem inteira). Sem Flask:
quem chama (as rotas, em `__init__`) passa a configuração, a função que lê o saldo do Fracttal e a pessoa do pedido; os
testes passam as suas.

Quatro regras que a tela segue:

- **O Fracttal só se fala numa rota de `/os`** (revisão das Tasks 5 e 6): o login dele mora no cookie `os_sessao`, que o navegador
  só manda para `/os/...`; numa rota `/t/pcm/...` o `estoque_da_sessao` dava `SemLogin` SEMPRE (os testes trocavam a função ou
  mandavam o cookie à mão, e não pegaram). Por isso a PÁGINA (`montar`) não lê o Fracttal, e o que depende dele (`montar_lote`: o
  Sistema, o Δ, a situação, os seis grupos e o botão de gravar) a página busca depois, por `fetch`, na ponte
  (`ponte_os.py`, `/os/_nexus/inventario/<id>/lote`), que devolve o pedaço de HTML.
- **O Sistema é lido na hora** (`ler_sistema`, uma leitura do almoxarifado inteiro pelo adaptador), não o saldo da varredura da
  madrugada: o saldo muda durante o dia. Sem o login do Fracttal (quem entrou pela senha de administrador), com a cota esgotada
  (429) ou com o Fracttal fora do ar, a tela fica com o que o técnico contou, SEM Sistema nem Δ, e diz por quê: a situação de cada
  peça depende do saldo, e uma conta com saldo 0 chutado mandaria "subir" o estoque inteiro. Nunca 500. A contagem que já não se
  aprova (velha, substituída, gravada, recontagem pedida) também não lê o Fracttal: gastaria a cota da empresa à toa.
- **Revisar não fala com o Fracttal.** Tirar, corrigir e pedir a recontagem só gravam um evento no livro do inventário, no
  nome de quem revisou (`pessoa_hmac`, sempre; o `pessoa_id` quando o cadastro a acha), com o motivo SÓ cifrado (a API do banco
  tem leitura aberta). Quem entrou pela senha não é uma pessoa: a revisão ficaria sem dono na auditoria, e é recusada.
- **Curadoria aberta avisa e não bloqueia** (o desenho 4.2 põe a curadoria como um dos seis grupos, que não mexe no estoque):
  decidir depois SOMA ao contado da peça escolhida, e a tela diz isso, para o PCM não aprovar achando que o número é final.
"""
from __future__ import annotations

import re
from datetime import timedelta, timezone

from ...campo import visao
from ...campo.ligacao_cadastro import codigo_da_pessoa, mapas_de
from ...dados import almoxarifado as A
from ...dados import fato_inventario as F
from ...dados import fatos as D
from ...dados.dominios import norm
from . import contas, leitura, travas
from .estoque import ErroFracttal, Limite, SemLogin, instante
from .gravacao import TAMANHO_LOTE

ROTULO_ESTADO = {"nova": "Nova", "revisada": "Revisada", "recontagem_pedida": "Recontagem pedida", "substituida": "Substituída",
                 "gravando": "Gravando", "gravada": "Gravada", "gravada_com_conflitos": "Gravada com conflitos"}
# o selo do estado da contagem (a lista e a contagem aberta): espera o PCM em azul, gravando em âmbar, gravada em verde, com
# conflito em vermelho; a recusada e a substituída, neutras (não há o que fazer nelas)
TOM_ESTADO = {"nova": "info", "revisada": "info", "recontagem_pedida": "neutro", "substituida": "neutro", "gravando": "alerta",
              "gravada": "ok", "gravada_com_conflitos": "critico"}
ROTULO_SITUACAO = {"para_cima": "Para cima", "para_baixo": "Para baixo", "zerar": "Zerar", "sem_alteracao": "Sem alteração",
                   "nao_tocada": "Não será tocada", "curadoria": "Curadoria"}
# os seis grupos da confirmação, na ordem das `contas.SITUACOES`: (título, o que acontece com a peça nele)
GRUPOS = {
    "para_cima": ("Ajuste para cima", "O contado é maior que o saldo do sistema: o saldo sobe no Fracttal."),
    "para_baixo": ("Ajuste para baixo", "O contado é menor que o saldo do sistema: o saldo cai no Fracttal."),
    "zerar": ("Zerar o estoque", "O técnico digitou 0 em peça com saldo: o estoque dela vai a zero no Fracttal. Confira peça "
                                  "a peça antes de gravar."),
    "sem_alteracao": ("Sem alteração", "O contado é igual ao saldo do sistema: nada é gravado."),
    "nao_tocada": ("Não será tocada", "Em branco, com contado inválido, tirada do lote ou em recontagem: nada é gravado, e "
                                      "o saldo do Fracttal fica como está."),
    "curadoria": ("Curadoria", "O que o PCM ainda decide (o genérico por identificar e a peça fora do catálogo): nada é "
                               "gravado até decidir."),
}
# a cor de cada situação (o tom do selo, do número do alto e da barra; a palavra vem sempre junto) e o selo do grupo na
# confirmação (o que acontece no Fracttal). O desenho é o do mockup do Spare Parts (Levi, 27/10/2026): para cima verde, para
# baixo vermelho, zerar âmbar ("grava · atenção": é a única que apaga estoque), a curadoria azul e o que não mexe, neutro
TOM_SITUACAO = {"para_cima": "ok", "para_baixo": "critico", "zerar": "alerta", "sem_alteracao": "neutro",
                "nao_tocada": "neutro", "curadoria": "info"}
SELO_GRUPO = {"para_cima": "grava", "para_baixo": "grava", "zerar": "grava · atenção", "sem_alteracao": "não grava",
              "nao_tocada": "não grava", "curadoria": "não grava"}
# os que abrem já abertos na confirmação: o zerar (a única ação que apaga estoque) e o "não será tocada" (o que fica como está
# no Fracttal: a peça em branco, a tirada e a de contado inválido; é o que o PCM confere para não achar que zerou)
ABERTOS = ("zerar", "nao_tocada")
DIVERGENCIAS_MAX = 8          # as maiores Δ na etapa Contagem (a lista inteira está na Aprovação)
SEM_DELTA = ("nao_tocada", "curadoria")
MOTIVO_MAX = 1000
LIMITE_VEZES, LIMITE_MINIMO = 10, 1000        # o número corrigido além disto pede confirmação (`_conferir_exagero`)
_BRT = timezone(timedelta(hours=-3))

SEM_LOGIN = ("Sem o login do Fracttal nesta sessão: entre pelo Fracttal para ver o saldo do sistema e gravar. Aqui está o "
             "que o técnico contou.")
PAUSA = "Não li o saldo do sistema: o Fracttal pediu uma pausa; tente de novo em 1 minuto."
SO_PCM = "Só o setor PCM lê o saldo do sistema no Fracttal, revisa o lote e pede a recontagem."

_NUMERO = re.compile(r"\d+(?:[.,]\d+)?")


_CRITICIDADE = re.compile(r"(\d{1,2})\s*[.)\-]?\s*(.*)")


def _criticidade(texto) -> tuple[int | None, str]:
    """(o nível, o nome) da criticidade da peça no Fracttal (o `groups_1_description` que o `Estoque.ler` devolve: "1.Crítico",
    "2.Necessário", "3.Importante", ...). Sem número, (None, o texto): a tela mostra "–" e nunca chuta um nível."""
    t = A._txt(texto)
    m = _CRITICIDADE.fullmatch(t)
    if not m:
        return None, t
    return int(m.group(1)), m.group(2).strip() or t


class Recusa(Exception):
    """O pedido que não vale: `status` HTTP e o texto para a tela (e `extra`, campos a mais na resposta JSON, como o
    `confirmar` que pede ao navegador para mandar o `confirmo`). Nada foi gravado."""

    def __init__(self, status: int, mensagem: str, **extra):
        super().__init__(mensagem)
        self.status, self.mensagem, self.extra = status, mensagem, extra


def _num(n, sinal: bool = False) -> str:
    """O número como o brasileiro o lê: vírgula decimal, sem o ".0" nem a notação científica ("1e+06"); com `sinal`, o
    "+" nos positivos (o Δ)."""
    if n is None:
        return "—"
    if n == 0:
        return "0"
    texto = f"{n:.6f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"+{texto}" if sinal and n > 0 else texto


def _hora(iso, com_as: bool = False) -> str:
    """A hora de Brasília de um "Contada em" ou "Enviada em". Pelo `instante` das contas, o mesmo que decide a janela de
    aprovação: um texto SEM fuso é UTC (o App grava assim). O `visao._dt` o lia como Brasília, e a tela mostrava 12:00 onde a
    janela contava 09:00."""
    try:
        d = instante(iso).astimezone(_BRT)
    except ValueError:
        return "data ilegível"
    return d.strftime("%d/%m/%Y às %H:%M" if com_as else "%d/%m/%Y %H:%M")


def _dia(iso) -> str:
    """O dia e o mês de Brasília de uma hora do livro (UTC com Z), para a nota "recontagem pedida em 30/10"; vazio se a hora
    não se lê (a nota sai sem a data, nunca com uma inventada)."""
    try:
        return instante(iso).astimezone(_BRT).strftime("%d/%m")
    except ValueError:
        return ""


# ── a pessoa que revisa ──────────────────────────────────────────────────────────────────────────────────────────────────
def pessoa(cfg, email) -> dict | None:
    """Quem revisa, como o livro a guarda: `pessoa_hmac` (o código do e-mail, nunca o e-mail) e `pessoa_id` (quando a ficha do
    cadastro a acha; sem ela a revisão vale do mesmo jeito). None para quem não tem e-mail (a senha de administrador) ou
    quando falta a chave do código (`NEXUS_PESSOA_HMAC`)."""
    cod = codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), email)
    if not cod:
        return None
    try:
        mapa = visao._ciclo(("inventario_pessoas",),
                            lambda: mapas_de(cfg, [], visao._livro("cadastro_nexus", "pessoas"))["hmac"])
        pid = mapa.get(cod)
    except Exception:       # noqa: BLE001 — o pessoa_id só liga a linha à ficha; sem ele o código identifica do mesmo jeito
        pid = None
    return {"pessoa_hmac": cod, "pessoa_id": pid}


# ── a lista ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
def montar_lista(cfg) -> dict:
    """O que a lista das contagens mostra. `erro` quando não deu para ler (a tela diz, e não mostra "nenhuma contagem")."""
    try:
        d = leitura.ler(cfg)
    except F.Recusada as ex:
        return {"erro": str(ex), "livro_existe": False, "contagens": [], "a_revisar": 0}
    cs = [dict(c, contada_txt=_hora(c["contada_em"]), enviada_txt=_hora(c["enviada_em"]),
               rotulo=ROTULO_ESTADO[c["estado"]], tom=TOM_ESTADO[c["estado"]],
               recontagem_txt=_recontagem_de(c, d["contagens"])) for c in d["contagens"]]
    return {"erro": "", "livro_existe": d["livro_existe"], "contagens": cs,
            "a_revisar": sum(1 for c in cs if c["aprovavel"])}


def _original(c: dict, contagens: list[dict]) -> dict | None:
    """A contagem em que o PCM pediu a recontagem que `c` atende (o "Recontagem de" do App), se a lista a tem."""
    de = A._txt(c.get("recontagem_de"))
    return next((x for x in contagens if x["contagem_id"] == de), None) if de else None


def _recontagem_de(c: dict, contagens: list[dict]) -> str:
    """O rótulo da contagem de recontagem na lista (30/10/2026): de qual contagem ela é, pela hora da original ("recontagem
    da contagem de 26/10/2026 09:00"; o ID do App é opaco). A original que a lista não tem (fora da janela de 90 dias, ou do
    almoxarifado de teste) aparece pelo ID. Vazio na contagem inteira."""
    de = A._txt(c.get("recontagem_de"))
    if not de:
        return ""
    o = _original(c, contagens)
    return f"recontagem da contagem de {_hora(o['contada_em'])}" if o else f"recontagem da contagem {de}"


def _resumo(cfg) -> dict | None:
    """Os dois números que a tela principal do Almoxarifado pede ao inventário, de UMA leitura das contagens (30/10/2026): quantas
    esperam o PCM (`n`, o número da aba Inventário) e a data da última contagem gravada de cada almoxarifado (`ultimas`,
    no cartão da aba Por almoxarifado). Pela cópia de 5 min do `visao._ler`, renovada por trás: os dois são só enfeite, e a leitura do
    livro do inventário (2 min, no pedido) não pode segurar a tela principal quando o banco está lento (a lista do Inventário,
    essa sim, mostra o estado de agora). Duas contas guardadas leriam as contagens duas vezes a cada 5 min. None se não deu para
    ler: nenhum dos dois aparece (nunca "0 a revisar" nem "nunca contado" no lugar do que não se leu)."""
    def contar() -> dict:
        cs = leitura.contagens(cfg)
        ultimas: dict[str, tuple] = {}
        for c in cs:
            # a recontagem gravada também conta (é uma contagem real daquelas peças); a que ainda está gravando, não
            if c["estado"] not in ("gravada", "gravada_com_conflitos") or not c["id_almox"]:
                continue
            try:
                quando = instante(c["contada_em"])
            except ValueError:
                continue                  # sem data legível não há o que mostrar (e a que não se lê nem se aprova)
            if c["id_almox"] not in ultimas or quando > ultimas[c["id_almox"]][0]:
                ultimas[c["id_almox"]] = (quando, quando.astimezone(_BRT).strftime("%d/%m/%Y"))
        return {"n": sum(1 for c in cs if c["aprovavel"]), "ultimas": {a: dia for a, (_, dia) in ultimas.items()}}
    g = visao._ler(("pcm_inventario_resumo",), contar)
    return None if g.erro or not g.dados else g.dados


def a_revisar(cfg) -> int | None:
    """Quantas contagens esperam o PCM (o número da aba Inventário na tela principal do Almoxarifado); None se não deu para
    ler: a aba segue sem número. Ver `_resumo`."""
    r = _resumo(cfg)
    return None if r is None else r["n"]


def ultimas_gravadas(cfg) -> dict[str, str] | None:
    """`{id do almoxarifado: "dd/mm/aaaa"}`: o dia (Brasília) da contagem gravada mais nova de cada almoxarifado, em estado
    `gravada` ou `gravada_com_conflitos`; o almoxarifado que nunca teve uma fica fora (a tela diz "nunca contado pelo
    inventário"). None se não deu para ler o inventário: aí a tela não diz nada, e "nunca contado" seria falso. Ver `_resumo`."""
    r = _resumo(cfg)
    return None if r is None else r["ultimas"]


# ── a auditoria ──────────────────────────────────────────────────────────────────────────────────────────────────────────
# o nome de cada tipo de evento na tela (um para cada `fato_inventario.TIPOS_EVENTO`; o teste confere que não falta nenhum)
ROTULO_EVENTO = {"contagem_recebida": "Contagem recebida", "aprovada": "Aprovada para gravar", "peca_gravada": "Peça gravada",
                 "conflito": "Conflito", "erro": "Erro", "peca_tirada": "Peça tirada do lote",
                 "recontagem_pedida": "Recontagem pedida", "numero_corrigido": "Número corrigido",
                 "substituida": "Contagem substituída", "curadoria": "Curadoria decidida", "regua_gravada": "Régua gravada",
                 "recontagem_item_pedida": "Recontagem da peça pedida"}
# o selo de cada evento, pelas quatro famílias do mockup do Spare Parts (Levi, 27/10/2026): a gravação no Fracttal em verde, a
# curadoria em âmbar, a aprovação e a revisão em azul, o conflito e o erro em vermelho. A cor só reforça a palavra (o rótulo)
SELO_EVENTO = {"peca_gravada": "ok", "regua_gravada": "ok", "curadoria": "alerta", "conflito": "critico", "erro": "critico"}


def _retorno(tipo: str, movimento: str, codigo: str) -> str:
    """O que o Fracttal devolveu, na coluna "Retorno do Fracttal": o movimento do ajuste da peça gravada, a régua gravada, a
    peça cadastrada pela curadoria, a peça que não foi gravada. O resto do livro é do Nexus (revisar, aprovar): o Fracttal nem
    foi tocado, e a coluna diz "—". O motivo do conflito e do erro é texto livre cifrado: aqui, nunca."""
    if tipo == "peca_gravada":
        return f"movimento {movimento}" if movimento else "gravada"
    if tipo == "regua_gravada":
        return "gravada no Fracttal"
    if tipo == "curadoria" and codigo:            # o evento da curadoria só leva o código quando a peça foi criada
        return f"peça {codigo} cadastrada"
    if tipo == "conflito":
        return "não gravada"
    if tipo == "erro":
        return "não confirmada"
    return ""


def _qtd(v) -> float | None:
    """A quantidade do livro como número (a API devolve texto, "3,0" ou "None"; o arquivo, número); vazio é None."""
    t = str(v if v is not None else "").strip().replace(",", ".")
    if t.lower() in ("", "none", "nan"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _nomes_para_auditoria() -> dict:
    """{"almox": {id: nome}, "itens": {id: {codigo, nome}}}: só enfeitam a tela (o evento traz os IDs e o código), pela cópia de
    5 min do `visao._ler`. Sem os livros do App, a linha aparece pelo ID."""
    def ler():
        almox = {}
        for s in leitura._livro_ou_vazio(A.LIVRO_SALDO, A.ABA_SALDO):
            if A._txt(s.get("ID do almoxarifado")) and A._txt(s.get("Almoxarifado")):
                almox.setdefault(A._id(s.get("ID do almoxarifado")), A._txt(s.get("Almoxarifado")))
        itens = {A._id(i.get("ID do item")): {"codigo": A._txt(i.get("Código")), "nome": A._txt(i.get("Nome"))}
                 for i in leitura._livro_ou_vazio(A.LIVRO_ITENS, A.ABA_ITENS) if A._txt(i.get("ID do item"))}
        return {"almox": almox, "itens": itens}
    g = visao._ler(("pcm_inventario_auditoria_nomes",), ler)
    return g.dados if g.dados and not g.erro else {"almox": {}, "itens": {}}


def _nomes_das_pessoas(ids: set) -> dict:
    """{pessoa_id: "Nome padrão"} pela ficha do cadastro (cifrada; a mesma conta das telas do Campo). O livro só guarda o
    `pessoa_id` e o código do e-mail: o nome é atributo da pessoa e sai da ficha, na hora. Sem o cadastro, vazio (a tela
    mostra o número da ficha)."""
    if not ids:
        return {}
    try:
        return visao._Base._nomes(ids, visao._livro("cadastro_nexus", "pessoas"))
    except Exception:       # noqa: BLE001 — o nome só enfeita a auditoria: sem o cadastro, o número da ficha
        return {}


def montar_auditoria(cfg, pode: bool, tipo: str = "", busca: str = "", contagem_id: str | None = None) -> dict:
    """A aba Auditoria (desenho 4.6): uma linha por evento do `fato_evento_inventario`, do mais novo ao mais velho, sem o
    almoxarifado de teste (como as outras telas). Nunca o motivo: ele é texto livre, mora só cifrado no livro, e quem revisa o
    lê na contagem aberta; aqui a linha só diz que ele existe. O nome de quem fez só para quem `pode` revisar (o PCM): os outros
    setores que veem a tela leem o que aconteceu, não quem. `tipo` e `busca` são os filtros do endereço: a página aberta já
    filtrada chega com as outras linhas escondidas, e o `filtro-local.js` segue dali sem voltar ao servidor. `contagem_id`: só os
    eventos dessa contagem (a etapa Auditoria da contagem aberta). Não fala com o Fracttal; `erro` quando o livro não se lê (a
    tela diz, e não mostra "nenhum evento")."""
    tipo = tipo if tipo in F.TIPOS_EVENTO else ""
    busca_n = norm(busca)
    ctx = {"erro": "", "eventos": [], "tipos": [], "tipo": tipo, "busca": str(busca or "").strip()[:100], "pode": pode,
           "n_visiveis": 0}
    try:
        eventos = F.ler(cfg)[F.ABA_EVENTO]
    except F.Recusada as ex:
        ctx["erro"] = str(ex)
        return ctx
    teste = A.ids_de_teste(cfg)
    eventos = [e for e in eventos if A._id(e.get("id_almoxarifado")) not in teste
               and (contagem_id is None or A._txt(e.get("contagem_id")) == A._txt(contagem_id))]
    nomes = _nomes_para_auditoria() if eventos else {"almox": {}, "itens": {}}
    pessoas = _nomes_das_pessoas({D._id(e.get("pessoa_id")) for e in eventos} - {None}) if pode else {}
    linhas = []
    for n, e in enumerate(eventos):
        t = A._txt(e.get("tipo"))
        almox, item, cid = A._id(e.get("id_almoxarifado")), A._id(e.get("id_item")), A._txt(e.get("contagem_id"))
        peca = nomes["itens"].get(item, {})
        codigo = A._txt(e.get("codigo")) or peca.get("codigo", "")
        de, para, contado = _qtd(e.get("de_qtd")), _qtd(e.get("para_qtd")), _qtd(e.get("contado_qtd"))
        numeros = (f"{'mínimo ' if t == 'regua_gravada' else ''}{_num(de)} para {_num(para)}" if de is not None or para is not None
                   else f"contado {_num(contado)}" if contado is not None else "")
        situacao = ROTULO_SITUACAO.get(A._txt(e.get("situacao")), "")
        movimento, lote = A._id(e.get("movimento_fracttal")), D._id(e.get("lote"))
        pid = D._id(e.get("pessoa_id"))
        quem = (pessoas.get(pid) or f"ficha {pid} do cadastro") if pid else ("sem ficha no cadastro" if e.get("pessoa_hmac") else "")
        rotulo = ROTULO_EVENTO.get(t, t)
        nome_almox = nomes["almox"].get(almox) or (f"Almoxarifado {almox}" if almox else "")
        procura = norm(" ".join(x for x in (rotulo, nome_almox, almox, codigo, peca.get("nome", ""), item, cid,
                                            A._id(e.get("movimento_fracttal")), quem if pode else "") if x))
        linhas.append({"n": n, "quando": _quando_do_evento(e.get("quando")), "hora": _hora(e.get("quando")), "tipo": t,
                       "rotulo": rotulo, "selo": SELO_EVENTO.get(t, "info"), "almox": nome_almox, "id_item": item,
                       "codigo": codigo, "peca": peca.get("nome", ""), "contagem_id": cid, "numeros": numeros,
                       "situacao": situacao, "lote": str(lote) if lote is not None else "", "movimento": movimento,
                       "retorno": _retorno(t, movimento, A._txt(e.get("codigo"))), "quem": quem if pode else "",
                       "motivo": bool(A._txt(e.get("dados_cifrados"))), "busca": procura,
                       "_achou": not busca_n or busca_n in procura})
    linhas.sort(key=lambda x: (x["quando"], x["n"]), reverse=True)
    for x in linhas:
        x["oculta"] = not x["_achou"] or bool(tipo and x["tipo"] != tipo)
    # as opções do tipo: os que aparecem, na ordem do livro, cada um com a conta sob a busca (a mesma cascata do filtro-local)
    conta = {}
    for x in linhas:
        if x["_achou"]:
            conta[x["tipo"]] = conta.get(x["tipo"], 0) + 1
    presentes = {x["tipo"] for x in linhas} | ({tipo} if tipo else set())
    ctx["tipos"] = [{"valor": t, "rotulo": ROTULO_EVENTO[t], "n": conta.get(t, 0)} for t in F.TIPOS_EVENTO if t in presentes]
    ctx["eventos"], ctx["n_visiveis"] = linhas, sum(1 for x in linhas if not x["oculta"])
    return ctx


def _quando_do_evento(iso):
    """O instante do evento para ordenar (o livro tem a hora em UTC com Z); a hora ilegível vai para o fim."""
    try:
        return instante(iso)
    except ValueError:
        return instante("2000-01-01T00:00:00Z")


# ── a contagem aberta ────────────────────────────────────────────────────────────────────────────────────────────────────
def _do_sistema(ler_sistema, id_almox: str) -> tuple[dict | None, str, str]:
    """(saldos, estado, mensagem). `estado`: "ok", "sem_login", "pausa" ou "erro". Nunca levanta: a tela diz o que houve."""
    try:
        return ler_sistema(id_almox), "ok", ""
    except SemLogin:
        return None, "sem_login", SEM_LOGIN
    except Limite:
        return None, "pausa", PAUSA
    except ErroFracttal as ex:
        return None, "erro", f"O Fracttal recusou a leitura do saldo ({ex.mensagem}): tente de novo em instantes."
    except Exception as ex:      # noqa: BLE001 — rede fora, resposta ilegível: a tela diz, não cai
        return None, "erro", f"Não consegui ler o saldo do Fracttal agora ({type(ex).__name__}): tente de novo em instantes."


def _avisos_da_curadoria(itens: list[dict]) -> list[str]:
    """Os avisos da curadoria aberta: o achado fora do catálogo por decidir e o genérico (inteiro ou em parte) por
    identificar. Decidir depois soma ao contado da peça escolhida, e é o que o PCM precisa saber antes de aprovar."""
    avisos = []
    achados = sum(len(i["pendentes"]) for i in itens if i["situacao"] == "curadoria" and not i["id_item"])
    if achados:
        avisos.append(f"{achados} {'achado' if achados == 1 else 'achados'} por decidir na curadoria; decidir depois soma ao "
                      "contado da peça escolhida")
    for i in itens:
        if i["situacao"] == "curadoria" and i["id_item"]:
            n = len(i["pendentes"])
            avisos.append(f"{n} {'linha' if n == 1 else 'linhas'} do genérico {i['codigo'] or i['id_item']} por identificar na "
                          "curadoria; decidir depois soma ao contado da peça escolhida")
    return avisos


def _enriquecer(i: dict, c: dict, nomes: dict, revisao: dict, achados: dict, sistema: dict | None, pode: bool) -> dict:
    """O item das contas com o que a tela mostra: o nome, os números como texto, o porquê de a peça não ser gravada e as ações.
    O MOTIVO do PCM (da peça tirada, do número corrigido e da recontagem pedida) só vai a quem pode revisar: os outros setores
    leem "tirada do lote", "corrigida pelo PCM" e "recontagem pedida em dd/mm", sem o texto (ele é livre, e pode citar gente)."""
    meta = nomes.get(i["id_item"], {})
    tirada, recontar, notas = i["tirada"], i.get("recontar", False), []
    sit = i["situacao"]
    grupo = "nao_tocada" if tirada else sit
    motivo_tirada = revisao["tiradas"].get(i["id_item"], "") if tirada and pode else ""
    motivo_correcao = revisao["motivos_corrigidos"].get(i["id_item"], "") if i["corrigido"] and pode else ""
    if recontar:
        # a recontagem só das marcadas (30/10/2026): a peça sai deste lote e o técnico a reconta no App; a contagem nova é
        # que a traz. A data é a do pedido, para o PCM saber há quanto tempo espera
        dia = _dia((revisao.get("recontar_em") or {}).get(i["id_item"]))
        motivo_recontar = (revisao.get("recontar") or {}).get(i["id_item"], "") if pode else ""
        notas.append("recontagem pedida" + (f" em {dia}" if dia else "") + (f": {motivo_recontar}" if motivo_recontar else ""))
    elif tirada:
        notas.append("tirada do lote" + (f": {motivo_tirada}" if motivo_tirada else ""))
    elif i["invalido"] and not i["corrigido"] and sit != "curadoria":
        notas.append("contado inválido (negativo): a peça não será gravada")
    elif sit == "nao_tocada":
        notas.append("em branco: o técnico não contou")
    if i["corrigido"]:
        # a peça de contado inválido que o PCM corrigiu entra no lote como qualquer outra: a nota de "não será gravada" sai,
        # e o que o técnico contou (um valor que o livro não aceita, não um número) não se repete
        if not pode:
            notas.append("corrigida pelo PCM")
        else:
            agora = _num(i["contado"])
            texto = (f"o técnico contou um valor inválido; o PCM corrigiu para {agora}" if i["invalido"]
                     else f"o técnico deixou em branco; o PCM informou {agora}" if i["contado_campo"] is None
                     else f"o técnico contou {_num(i['contado_campo'])}; o PCM corrigiu para {agora}")
            notas.append(texto + (f" ({motivo_correcao})" if motivo_correcao else ""))
    sem_saldo = i["ligada"] and i["sistema"] is None
    com_sistema = sistema is not None
    if com_sistema and i["id_item"] and i["contado"] is not None and not tirada:
        if not i["ligada"]:
            notas.append("não ligada ao almoxarifado: será ligada ao gravar")
        elif sem_saldo:
            notas.append("saldo não informado pelo Fracttal (vale 0 na conta)")
    if sit == "curadoria" and i["id_item"]:
        notas.append("genérico por identificar: o PCM decide na curadoria")
    nome, descricao = meta.get("nome", ""), ""
    if sit == "curadoria" and not i["id_item"]:
        linha = achados.get(i["pendentes"][0] if i["pendentes"] else "", {})
        descricao = A._txt(linha.get("Descrição"))
        nome = "Fora do catálogo" + (f": {descricao}" if descricao else "")
    mexe = sit in contas.MEXEM and not tirada
    # sem Δ onde não há conta a fazer: a peça que não se toca, a da curadoria (as unidades ainda não têm dono: o Δ de um
    # genérico com 4 unidades por identificar contra o saldo 20 diria "-16", e não é isso) e a de saldo não informado (o Δ
    # contra um 0 que o Fracttal não disse seria um "+5" que ninguém viu; a nota diz que vale 0 na conta)
    sem_delta = i["delta"] is None or sit in SEM_DELTA or sem_saldo
    crit_n, crit_nome = _criticidade(((sistema or {}).get(i["id_item"]) or {}).get("criticidade")) if i["id_item"] else (None, "")
    rotulo = "Em recontagem" if recontar else "Tirada do lote" if tirada else ROTULO_SITUACAO[sit]
    return dict(i, nome=nome, unidade=meta.get("unidade", ""), grupo=grupo, rotulo=rotulo, notas=notas, mexe=mexe,
                descricao=descricao, tom="neutro" if tirada else TOM_SITUACAO[sit],
                crit=crit_n, crit_nivel=min(crit_n, 4) if crit_n else None, crit_nome=crit_nome,
                # o que a busca da tabela da Aprovação olha (o filtro-local compara sem acento nem caixa)
                busca=norm(" ".join(x for x in (i["codigo"], nome, rotulo, crit_nome) if x)),
                sistema_txt=("—" if not i["id_item"] else "não informado" if sem_saldo
                             else "não ligada (0)" if not i["ligada"] else _num(i["sistema"])),
                sistema_num="" if i["sistema"] is None or not i["ligada"] else _num(i["sistema"]),
                contado_txt=_num(i["contado"]), campo_txt=_num(i["contado_campo"]),
                delta_txt="—" if sem_delta else _num(i["delta"], sinal=True),
                delta_sinal="" if sem_delta or not i["delta"] else "mais" if i["delta"] > 0 else "menos",
                # as ações são da peça com número que entra ou entraria no lote (a curadoria, sem ID, e a tirada não têm)
                acoes=bool(pode and c["aprovavel"] and i["id_item"] and not tirada and sit != "curadoria"
                           and (sit in contas.MEXEM or i["invalido"])),
                # a caixa da recontagem só das marcadas (30/10/2026): o que o servidor aceita, a peça com o ID do item fora da
                # curadoria e ainda no lote (o achado e o genérico por identificar seguem na curadoria). A em branco e a que
                # bate também: recontar o duvidoso inclui o que ninguém contou
                marcavel=bool(pode and c["aprovavel"] and i["id_item"] and not tirada and sit != "curadoria"))


def _contagem(cfg, contagem_id: str):
    """(todas, c): as contagens lidas e a pedida (None se não existe)."""
    todas = leitura.ler(cfg)
    return todas, next((x for x in todas["contagens"] if x["contagem_id"] == contagem_id), None)


def _itens(cfg, c: dict, todas: dict, sistema: dict | None, pode: bool) -> tuple[list[dict], list[dict]]:
    """(os itens da tela, o lote das contas). `sistema` None: o saldo não foi lido (o que as contas dizem da situação não vale,
    menos a curadoria, o em branco e o inválido, que não dependem dele)."""
    revisao = leitura.revisao_da(cfg, c["contagem_id"], motivos=pode)
    curadoria = leitura.curadoria_da(cfg, c["contagem_id"])
    lote = contas.itens_do_lote(c["linhas"], sistema or {}, curadoria, revisao)
    achados = {A._id(l.get("ID da linha")): l for l in c["linhas"]}
    return [_enriquecer(i, c, todas["itens"], revisao, achados, sistema, pode) for i in lote], lote


def montar(cfg, contagem_id: str, pode: bool = False) -> dict | None:
    """A PÁGINA da contagem aberta (`/t/pcm/pecas/inventario/<id>`), ou None se ela não existe: o que o técnico contou, o
    estado, os avisos e a revisão. **Não lê o Fracttal**: o login dele só chega nas rotas de `/os` (o cookie `os_sessao` vale só
    ali), então o Sistema, o Δ, a situação e os seis grupos vêm do `montar_lote`, que a página busca depois pela ponte
    (`ponte_os.py`). `vai_ler`: a página deve buscá-lo (quem pode revisar, contagem que se aprova e dentro do contrato).
    Levanta `fato_inventario.Recusada` se não leu o livro do App ou o do inventário (a tela diz)."""
    todas, c = _contagem(cfg, contagem_id)
    if c is None:
        return None
    ctx = {"c": c, "rotulo": ROTULO_ESTADO[c["estado"]], "tom_estado": TOM_ESTADO[c["estado"]],
           "contada_txt": _hora(c["contada_em"], com_as=True),
           "enviada_txt": _hora(c["enviada_em"], com_as=True), "itens": [], "avisos_curadoria": [], "pode": pode,
           "so_pcm": SO_PCM, "vai_ler": False, "sem_login": SEM_LOGIN, "pausa": PAUSA, "original": None}
    o = _original(c, todas["contagens"])
    if o:                    # a contagem de recontagem diz de qual é, com o link (a que a lista não tem, pelo ID: o template)
        ctx["original"] = {"contagem_id": o["contagem_id"], "contada_txt": _hora(o["contada_em"], com_as=True)}
    if c["aviso"]:
        return ctx           # o App fora do contrato: nenhum número, que seria pela metade
    ctx["itens"], lote = _itens(cfg, c, todas, None, pode)
    ctx["avisos_curadoria"] = _avisos_da_curadoria(lote)
    ctx["vai_ler"] = bool(pode and c["aprovavel"])
    return ctx


class SemSistema(Exception):
    """O saldo do sistema não veio: `estado` ("sem_login", "pausa" ou "erro") e o texto para a tela."""

    def __init__(self, estado: str, mensagem: str):
        super().__init__(mensagem)
        self.estado, self.mensagem = estado, mensagem


def montar_lote(cfg, contagem_id: str, ler_sistema, pode: bool = False) -> dict:
    """O pedaço da tela que depende do Fracttal (o Sistema × Contado × Δ × Situação, os seis grupos da confirmação e o botão de
    gravar), para a ponte devolver como HTML (`ponte_os.py`). `ler_sistema(id_almox)`: o saldo do Fracttal lido na hora (o `ler`
    do adaptador, com o login de quem está no pedido). Levanta `Recusa` (404 contagem que não existe, 409 contagem que não se
    aprova ou fora do contrato: nada a ler, e a cota do Fracttal é de toda a empresa) e `SemSistema` (sem o login, a pausa do 429
    ou o Fracttal que falhou); `fato_inventario.Recusada` se não leu os livros."""
    todas, c = _contagem(cfg, contagem_id)
    if c is None:
        raise Recusa(404, "Contagem não encontrada: atualize a página.")
    if c["aviso"]:
        raise Recusa(409, f"O App mandou esta contagem fora do contrato ({c['aviso']}): nada a comparar.")
    if not c["aprovavel"]:
        raise Recusa(409, f"Esta contagem não se aprova: {c['motivo_nao_aprovavel']}.")
    sistema, estado, mensagem = _do_sistema(ler_sistema, c["id_almox"])
    if sistema is None:
        raise SemSistema(estado, mensagem)
    itens, lote = _itens(cfg, c, todas, sistema, pode)
    grupos = []
    for sit in contas.SITUACOES:
        membros = sorted((i for i in itens if i["grupo"] == sit), key=lambda i: (i["codigo"], i["id_item"]))
        grupos.append({"id": sit, "titulo": GRUPOS[sit][0], "ajuda": GRUPOS[sit][1], "itens": membros, "n": len(membros),
                       "aberto": sit in ABERTOS and bool(membros), "destaque": sit == "zerar", "tom": TOM_SITUACAO[sit],
                       "selo": SELO_GRUPO[sit], "grava": sit in contas.MEXEM})
    n_gravar = sum(1 for i in itens if i["mexe"])
    por = {g["id"]: g["n"] for g in grupos}
    return {"c": c, "itens": itens, "grupos": grupos, "n_gravar": n_gravar, "pode": pode,
            "n_lotes": -(-n_gravar // TAMANHO_LOTE), "cobertura": _cobertura(por, len(itens)),
            # as maiores Δ primeiro; a de saldo não informado (sem Δ na tela: um "+6" contra um 0 que o Fracttal não disse) no fim
            "divergencias": sorted((i for i in itens if i["mexe"]),
                                   key=lambda i: (i["delta_txt"] == "—", -abs(i["delta"] or 0), i["codigo"]))[:DIVERGENCIAS_MAX]}


def _cobertura(por: dict, total: int) -> dict:
    """A barra "Cobertura do inventário" da etapa Contagem: das peças da contagem, as que batem com o Sistema, as que divergem
    (as três que gravam), as da curadoria e as que ficam fora do lote (em branco, contado inválido, tirada). Depende do Sistema:
    vem no pedaço da ponte, nunca da página."""
    mexem = sum(por.get(s, 0) for s in contas.MEXEM)
    partes = {"bate": por.get("sem_alteracao", 0), "diverge": mexem, "curadoria": por.get("curadoria", 0),
              "fora": por.get("nao_tocada", 0)}
    pct = {k: (round(100 * v / total, 1) if total else 0) for k, v in partes.items()}
    contadas = partes["bate"] + partes["diverge"] + partes["curadoria"]
    return dict(partes, total=total, pct=pct, pct_contado=round(100 * contadas / total) if total else 0)


# ── revisar ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _numero(bruto) -> float | None:
    """Um número de zero para cima, com vírgula ou ponto (texto ou número do JSON); None se não for."""
    if isinstance(bruto, bool):
        return None
    if isinstance(bruto, (int, float)):
        n = float(bruto)
    elif isinstance(bruto, str) and _NUMERO.fullmatch(bruto.strip()):
        n = float(bruto.strip().replace(",", "."))
    else:
        return None
    return n if n == n and n not in (float("inf"), float("-inf")) and n >= 0 else None


def _valor(bruto) -> float:
    """O número certo que o PCM digitou: zero ou mais, com vírgula ou ponto. 400 com a mensagem se não for."""
    n = _numero(bruto)
    if n is None:
        raise Recusa(400, "Informe o número certo: zero ou mais, com vírgula ou ponto (por exemplo 12 ou 2,5).")
    return n


def _conferir_exagero(valor: float, campo: float | None, sistema_da_pagina, confirmo: bool) -> None:
    """O número corrigido que passa de 10 vezes o maior entre o contado e o saldo do sistema (e de 1000) provavelmente tem um
    zero a mais, e iria ao estoque da empresa: 400 pedindo para confirmar (`"confirmo": true` aceita). O saldo do sistema é o
    que a página mostrou (revisar não lê o Fracttal): a trava é contra o erro de digitação, não uma defesa (quem manda o
    `confirmo` e o `sistema` é o mesmo navegador)."""
    sistema = _numero(sistema_da_pagina)
    maior = max(campo or 0.0, sistema or 0.0)
    limite = max(LIMITE_MINIMO, LIMITE_VEZES * maior)
    if valor > limite and not confirmo:
        raise Recusa(400, f"{_num(valor)} é mais de {LIMITE_VEZES} vezes o maior entre o contado "
                          f"({_num(campo) if campo is not None else 'em branco'}) e o saldo do sistema "
                          f"({_num(sistema) if sistema is not None else 'não lido'}), e passa de {_num(float(LIMITE_MINIMO))}: "
                          "confirme que é isso mesmo.", confirmar=True)


def _evento(c: dict, quem: dict, tipo: str, item: dict | None = None, **mais) -> dict:
    e = {"tipo": tipo, "contagem_id": c["contagem_id"], "id_almoxarifado": c["id_almox"], "pessoa_hmac": quem["pessoa_hmac"]}
    if quem.get("pessoa_id") is not None:
        e["pessoa_id"] = quem["pessoa_id"]
    if c.get("usina_id"):                       # a usina vai com a linhagem (de-para do Fracttal), ou nenhuma das duas
        e["usina_id"], e["usina_ligada_por"] = c["usina_id"], c["usina_ligada_por"]
    if item:
        e["id_item"], e["codigo"], e["contado_qtd"] = item["id_item"], item["codigo"], item["contado_campo"]
    e.update(mais)
    return e


def revisar(cfg, contagem_id: str, pedido, quem: dict | None) -> dict:
    """Tira uma peça do lote, corrige o número contado, pede a recontagem só das peças marcadas ou a da contagem inteira.
    `pedido`: `{"acao": "tirar" | "corrigir" | "recontagem_itens" | "recontagem", "id_item"?, "itens"?, "valor"?, "motivo",
    "sistema"?, "confirmo"?}`. Levanta `Recusa` (nada foi gravado) com o status e o texto; devolve `{"ok", "n", "mensagem",
    "estado"}` (`n`: quantos eventos foram gravados).

    O motivo é obrigatório em todas (o desenho: "cada um com o motivo, na auditoria") e só vai cifrado. Peça tirada não grava no
    Fracttal e mantém a situação; corrigir troca o número que vai ao Fracttal (a auditoria guarda o do campo, o corrigido, quem
    corrigiu e o motivo); a recontagem das marcadas (`itens`, 30/10/2026) tira só aquelas peças deste lote, um evento por peça,
    e o resto da contagem segue para aprovar e gravar; a recontagem inteira recusa a contagem (nada é gravado e o App pode
    contar de novo)."""
    if not isinstance(pedido, dict):
        raise Recusa(400, "Pedido sem corpo: mande a ação e o motivo em JSON.")
    acao = A._txt(pedido.get("acao"))
    if acao not in ("tirar", "corrigir", "recontagem_itens", "recontagem"):
        raise Recusa(400, "Ação desconhecida: tirar, corrigir, recontagem_itens ou recontagem.")
    if quem is None:
        if not cfg.get("NEXUS_PESSOA_HMAC"):
            raise Recusa(409, "O servidor não está configurado para registrar quem revisa (falta a NEXUS_PESSOA_HMAC); avise a T.I.")
        raise Recusa(409, "Não sei quem está revisando: entre com o seu login do Fracttal (a revisão fica no nome de quem a "
                          "faz, e a senha de administrador não é uma pessoa).")
    motivo = A._txt(pedido.get("motivo")) if isinstance(pedido.get("motivo"), str) else ""
    if not motivo:
        raise Recusa(400, "Escreva o motivo: ele fica na auditoria.")
    if len(motivo) > MOTIVO_MAX:
        raise Recusa(400, f"O motivo passa de {MOTIVO_MAX} caracteres: resuma.")
    # da conferência do estado até a escrita, a vez da contagem (`travas.CONTAGEM`): a aprovação que está lendo o lote termina
    # antes (e então a contagem já não se revisa), em vez de montar o lote sem esta revisão
    with travas.CONTAGEM.de(A._txt(contagem_id)):
        c, n = _revisar(cfg, contagem_id, pedido, quem, acao, motivo)
    novo = next((x for x in leitura.contagens(cfg) if x["contagem_id"] == contagem_id), c)
    texto = {"tirar": "Peça tirada do lote.", "corrigir": "Número corrigido.",
             "recontagem_itens": (f"Recontagem pedida de {n} {'peça' if n == 1 else 'peças'}: "
                                  f"{'ela sai' if n == 1 else 'elas saem'} deste lote, e o resto da contagem segue."),
             "recontagem": "Recontagem pedida: nada será gravado desta contagem."}[acao]
    return {"ok": True, "n": n, "mensagem": texto, "estado": novo["estado"]}


FOI_GRAVAR = "A contagem já foi para a gravação: o lote foi congelado na aprovação, e nenhuma revisão entra depois dele."


def _foi_para_a_gravacao(cfg, contagem_id: str) -> bool:
    """A contagem já tem o controle da gravação (`gravacao.existe`)? O `iniciar` cria o controle ANTES de registrar a aprovação
    no livro: se o registro falhou no meio (o banco que não confirmou), os eventos ainda dizem "nova" com o lote já congelado,
    e a revisão que entrasse ali seria ignorada pela gravação. O controle ilegível conta como existente (na dúvida, nada
    entra)."""
    from . import gravacao
    try:
        return gravacao.existe(cfg, contagem_id)
    except F.Recusada:
        return True


EM_RECONTAGEM = "a recontagem dela foi pedida nesta contagem: ela saiu deste lote, e a contagem nova do App é que a traz"


def _lote_sem_sistema(cfg, contagem_id: str, c: dict) -> dict[str, dict]:
    """{id_item: entrada das contas} do lote da contagem com a revisão e a curadoria de agora (sem o saldo: revisar não lê o
    Fracttal, e o que se confere aqui não depende dele)."""
    revisao, curadoria = leitura.revisao_da(cfg, contagem_id, motivos=False), leitura.curadoria_da(cfg, contagem_id)
    return {i["id_item"]: i for i in contas.itens_do_lote(c["linhas"], {}, curadoria, revisao) if i["id_item"]}


def _a_recontar(cfg, contagem_id: str, c: dict, bruto) -> list[dict]:
    """As peças marcadas para a recontagem (30/10/2026), TODAS conferidas antes de gravar qualquer uma: tudo ou nada, para o
    PCM não ficar com metade das marcadas fora do lote sem saber quais. Só se marca o que aceita ação (a peça com o ID do item,
    ainda no lote e fora da curadoria): o achado fora do catálogo não tem ID, e o genérico por identificar decide a curadoria.
    A peça repetida na lista vale uma vez. A que já tem a recontagem pedida nesta contagem já está fora do lote: 409 (quem a
    traz é a contagem nova do App)."""
    if not isinstance(bruto, list) or not bruto:
        raise Recusa(400, "Marque ao menos uma peça para recontar.")
    ids: list[str] = []
    for x in bruto:
        i = A._id(x) if isinstance(x, (str, int)) and not isinstance(x, bool) else ""
        if not i.isdigit():
            raise Recusa(400, "Diga as peças pelo ID do item (o achado fora do catálogo não tem: ele segue na curadoria).")
        if i not in ids:
            ids.append(i)
    lote = _lote_sem_sistema(cfg, contagem_id, c)
    escolhidas = []
    for i in ids:
        item = lote.get(i)
        if item is None:
            raise Recusa(400, f"A peça {i} não está nesta contagem.")
        peca = item["codigo"] or i
        if item["recontar"]:
            raise Recusa(409, f"A peça {peca} já foi pedida para recontar: {EM_RECONTAGEM}.")
        if item["tirada"]:
            raise Recusa(409, f"A peça {peca} já está fora do lote.")
        if item["situacao"] == "curadoria":
            raise Recusa(409, f"A peça {peca} tem unidades por identificar: decida a curadoria antes de pedir a recontagem.")
        escolhidas.append(item)
    return escolhidas


def _revisar(cfg, contagem_id: str, pedido: dict, quem: dict, acao: str, motivo: str):
    """Confere o estado de agora e grava os eventos (chamar com a trava da contagem), todos de uma vez (`acrescentar` com a
    lista: a recontagem das marcadas grava um por peça, e o livro não fica com só uma parte). Devolve (a contagem conferida,
    quantos eventos)."""
    try:
        F.ler(cfg, forcar=True)         # o estado de agora: dois PCMs revisando a mesma contagem não se atropelam
        _, c = _contagem(cfg, contagem_id)
    except F.Recusada as ex:
        raise Recusa(503, str(ex)) from None
    if c is None:
        raise Recusa(404, "Contagem não encontrada: atualize a página.")
    if not c["aprovavel"]:
        raise Recusa(409, f"Esta contagem não se revisa: {c['motivo_nao_aprovavel']}.")
    if _foi_para_a_gravacao(cfg, contagem_id):
        raise Recusa(409, FOI_GRAVAR)
    if acao == "recontagem_itens":
        eventos = [_evento(c, quem, "recontagem_item_pedida", i, dados={"motivo": motivo})
                   for i in _a_recontar(cfg, contagem_id, c, pedido.get("itens"))]
    else:
        item, extra = None, {}
        if acao != "recontagem":
            id_item = A._id(pedido.get("id_item")) if isinstance(pedido.get("id_item"), (str, int)) else ""
            if not id_item.isdigit():
                raise Recusa(400, "Diga a peça (o ID do item).")
            item = _lote_sem_sistema(cfg, contagem_id, c).get(id_item)
            if item is None:
                raise Recusa(400, "Essa peça não está nesta contagem.")
            if item["recontar"]:
                raise Recusa(409, f"A peça está em recontagem: {EM_RECONTAGEM}.")
            if item["tirada"]:
                raise Recusa(409, "A peça já está fora do lote.")
            if acao == "corrigir":
                if item["situacao"] == "curadoria":
                    raise Recusa(409, "A peça tem unidades por identificar: decida a curadoria antes de corrigir o número.")
                valor = _valor(pedido.get("valor"))
                _conferir_exagero(valor, item["contado_campo"], pedido.get("sistema"), pedido.get("confirmo") is True)
                extra = {"de_qtd": item["contado_campo"], "para_qtd": valor}
        tipo = {"tirar": "peca_tirada", "corrigir": "numero_corrigido", "recontagem": "recontagem_pedida"}[acao]
        eventos = [_evento(c, quem, tipo, item, dados={"motivo": motivo}, **extra)]
    try:
        F.acrescentar(cfg, F.ABA_EVENTO, eventos)
    except F.Recusada as ex:
        raise Recusa(503, str(ex)) from None
    except ValueError as ex:        # o livro não aceita a linha (um ID que não cabe na coluna): nada foi gravado
        raise Recusa(400, f"O livro do inventário não aceitou: {ex}") from None
    return c, len(eventos)
