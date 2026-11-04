"""As contagens do inventário do almoxarifado e o estado de cada uma (Levi, 26/10/2026). Desenho:
`docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md`, seção 4.2.

De onde vem cada parte:
- **as contagens**, do livro que o App de Campo publica (`almoxarifado_contagens_app_campo`, o contrato de 19 colunas em
  `nexus/dados/almoxarifado.py`): uma linha por peça contada, agrupadas pelo "ID da contagem". Vêm pela cópia de 5 min do
  `visao._ler`, como os outros livros do App (lê o banco e liga a usina pela de-para do Fracttal uma vez, não a cada abertura
  da tela);
- **o estado de cada contagem**, dos eventos do livro do inventário (`fato_inventario`, a auditoria do Nexus), calculado a
  CADA chamada e nunca guardado junto da cópia do App: o livro do inventário se renova a cada gravação, e pedir a recontagem
  e continuar vendo "nova" por mais 5 min faria o PCM pedir de novo. A leitura NUNCA escreve: o estado `substituida` sai da
  conta (`contas.substituidas`), e ninguém grava o evento por ela.

O que a leitura pede dos eventos que a gravação (Task 7) escreve, e o que ela faz com eles (a ordem do livro é a da gravação):

| Eventos da contagem | Estado |
|---|---|
| nenhum que mude o estado | `nova` |
| `peca_tirada`, `numero_corrigido` ou `recontagem_item_pedida` (a recontagem só de algumas peças) | `revisada` |
| `recontagem_pedida` | `recontagem_pedida` (nunca se aprova) |
| `substituida` (ou a conta das `contas.substituidas`) | `substituida` |
| `aprovada`, e o lote ainda sem o fim | `gravando` |
| `aprovada` e `peca_gravada` de todas as peças do lote | `gravada` |
| o mesmo, com algum `conflito` no lugar da gravada | `gravada_com_conflitos` |

**O lote é o conjunto de `id_item` dos eventos `aprovada`: a gravação grava UM `aprovada` por peça do lote** (no começo, junto
de uma vez). Sem as peças a leitura não sabe o que falta e fica em `gravando`: dar a contagem por gravada na primeira
`peca_gravada` deixaria o PCM crer que o estoque já foi acertado quando só uma peça foi. O `erro` não encerra a peça (ela
pode ser retomada). O `gravando` daqui é "aprovada e sem o fim nos eventos": o que é parada ou andamento a Task 7 refina com o
controle dela (`gravacao.estado`).

Falha de leitura nunca vira lista vazia nem contagem `nova`: a contagem já gravada apareceria como a aprovar. `Recusada`
(a exceção da camada, `fato_inventario.Recusada`) com o texto para a tela.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ...campo import visao
from ...dados import almoxarifado as A
from ...dados import fato_inventario as F
from ...dados import livros
from ...dados.fato_almoxarifado import LIGADA_DE_PARA
from ...dados.fatos import Ligador
from . import avariados, contas
from .estoque import instante

ESTADOS = ("nova", "revisada", "recontagem_pedida", "substituida", "gravando", "gravada", "gravada_com_conflitos")
# os estados de quem já foi aprovado: a gravação começou (ou acabou). Contam como "gravada" para a substituição, que não
# desfaz o que já está no Fracttal
DA_GRAVACAO = ("gravando", "gravada", "gravada_com_conflitos")
# a contagem que já não está viva: não substitui ninguém e ninguém a substitui
MORTAS = ("recontagem_pedida", "substituida")
# a contagem que o PCM ainda revisa (e aprova): as outras não têm o que revisar
REVISAVEIS = ("nova", "revisada")

CHAVE_APP = ("pcm_inventario_contagens",)
_NUNCA = datetime(1970, 1, 1, tzinfo=timezone.utc)      # a data que não se leu é a mais velha

_txt, _id = A._txt, A._id


def _vazio(valor) -> bool:
    """Vazio no livro do App: "" ou o "None" que o `sync-xlsx` escreve no lugar do vazio."""
    return _txt(valor).lower() in ("", "none")


def _quando(valor) -> datetime:
    try:
        return instante(valor)
    except ValueError:
        return _NUNCA


# ── o livro do App, pela cópia de 5 min ────────────────────────────────────────────────────────────────────────────────
def _primeiro(linhas: list[dict], coluna: str) -> str:
    """O valor da coluna na 1ª linha que a tem. As linhas de uma contagem trazem o mesmo, e se um dia divergirem vale a 1ª
    (a contagem não muda de almoxarifado nem de hora no meio)."""
    return next((_txt(l.get(coluna)) for l in linhas if not _vazio(l.get(coluna))), "")


def _o_que_o_app_faz(linhas: list[dict]) -> dict:
    """O que o App que publicou o livro faz, pelas colunas dele (04/11/2026). O App que monta a revisão de 30/10/2026 publica as
    cinco colunas novas juntas (a 15ª à 19ª): com o "Recontagem de" ele lê os pedidos de recontagem do PCM (o da peça e o da
    contagem inteira) e os mostra ao técnico; com as "Fotos dos dados" ele manda as fotos ao Nexus. O de hoje (v321) não faz
    nem um nem outro, e a tela que prometia ("volta ao técnico no App", "foto ainda não chegou") deixava o PCM esperando o que
    não vinha (caso real: uma pessoa do PCM pediu a recontagem de uma peça e perguntou "não sei pra onde foi essa
    informação"). Coluna ausente, ou livro sem linha nenhuma, é falso. Nenhuma chave de configuração vira isso à mão: o App
    novo publica, e os textos passam a dizer o que ele faz."""
    return {"app_com_recontagem": any("Recontagem de" in l for l in linhas),
            "app_com_fotos": any("Fotos dos dados" in l for l in linhas)}


def _do_app() -> dict:
    """O que se lê do banco: as contagens do App, agrupadas, com a usina ligada e o nome do almoxarifado, e o catálogo do App
    (`itens`: o nome de cada peça, e o que leva a avariada ao -AV), com `itens_lido` (falso: o livro Itens NÃO se leu agora; o
    lido e vazio é verdadeiro), e o que o App faz pela versão do livro (`_o_que_o_app_faz`). Roda dentro do `visao._ler` (cópia
    de 5 min, renovada por trás)."""
    abas = visao._ciclo(("_abas", A.LIVRO_CONTAGENS),
                        lambda: livros.abas(visao._base(), visao._sessao(), A.LIVRO_CONTAGENS))
    if A.ABA_CONTAGENS not in abas:
        return {"livro_existe": False, "contagens": [], "itens": {}, "itens_lido": True, **_o_que_o_app_faz([])}
    linhas = visao._livro(A.LIVRO_CONTAGENS, A.ABA_CONTAGENS)
    lig = Ligador(visao._livro("cadastro_nexus", "usinas"), visao._livro("cadastro_nexus", "de_para"), [], {})
    nome_usina = {_id(u.get("usina_id")): _txt(u.get("nome")) for u in visao._livro("cadastro_nexus", "usinas")}
    grupos: dict[str, list[dict]] = {}
    for l in linhas:
        if not _vazio(l.get("ID da contagem")):
            grupos.setdefault(_txt(l.get("ID da contagem")), []).append(l)
    # o nome do almoxarifado só enfeita a tela: sem o livro do saldo a contagem aparece pelo ID
    almox = {}
    for s in _livro_ou_vazio(A.LIVRO_SALDO, A.ABA_SALDO):
        if not _vazio(s.get("ID do almoxarifado")) and not _vazio(s.get("Almoxarifado")):
            almox.setdefault(_id(s.get("ID do almoxarifado")), _txt(s.get("Almoxarifado")))
    # o catálogo do App NÃO só enfeita desde 30/10/2026: é ele que leva a avariada ao -AV (`avariados.resolver`). A falha não
    # vira catálogo vazio (ficaria 5 min nesta cópia, e cada avariada que acha o -AV viraria "sem cadastro", com a linha direta
    # do -AV contando sozinha, sem a trava do dobro): `itens_lido` falso, e a `ler` põe o aviso nas contagens com avariada que
    # ainda se revisam
    try:
        do_livro, itens_lido = visao._livro(A.LIVRO_ITENS, A.ABA_ITENS), True
    except Exception:       # noqa: BLE001 — o banco que caiu só neste livro: as contagens sem avariada seguem
        do_livro, itens_lido = [], False
    itens = {_id(i.get("ID do item")): {"codigo": _txt(i.get("Código")), "nome": _txt(i.get("Nome")),
                                         "unidade": _txt(i.get("Unidade")).lower()}
             for i in do_livro if not _vazio(i.get("ID do item"))}
    contagens = []
    for cid, ls in grupos.items():
        id_almox = "" if _vazio(_primeiro(ls, "ID do almoxarifado")) else _id(_primeiro(ls, "ID do almoxarifado"))
        fracttal = _primeiro(ls, "Usina")
        uid = lig.usina_do_fracttal(fracttal) if fracttal else None
        contagens.append({"contagem_id": cid, "id_almox": id_almox, "almox": almox.get(id_almox) or
                          (f"Almoxarifado {id_almox}" if id_almox else ""),
                          "usina": (nome_usina.get(_id(uid)) or fracttal) if uid else fracttal,
                          "usina_id": int(uid) if uid else None, "usina_ligada_por": LIGADA_DE_PARA if uid else None,
                          "contada_em": _primeiro(ls, "Contada em"), "enviada_em": _primeiro(ls, "Enviada em"),
                          # a contagem que o App manda quando o PCM pede a recontagem de algumas peças (30/10/2026): o ID
                          # da contagem em que o pedido foi feito. O livro de hoje não tem a coluna: vazio, contagem inteira
                          "recontagem_de": _primeiro(ls, "Recontagem de"),
                          "linhas": ls})
    return {"livro_existe": True, "contagens": contagens, "itens": itens, "itens_lido": itens_lido,
            **_o_que_o_app_faz(linhas)}


def _livro_ou_vazio(livro: str, aba: str) -> list[dict]:
    """O livro, ou vazio se não se leu. Só para o que enfeita a tela (o nome do almoxarifado): o catálogo do App, de que a
    avariada depende, não passa por aqui."""
    try:
        return visao._livro(livro, aba)
    except Exception:       # noqa: BLE001 — só enfeita: a contagem não depende do nome
        return []


def _app(agora: bool = False) -> dict:
    """As contagens do App pela cópia de 5 min; `agora`: relidas do banco neste pedido (sem a cópia de 5 min nem a do livro, de
    2 min), e a cópia renovada com elas. É o que a aprovação pede: a contagem mais nova do almoxarifado que acabou de chegar
    tem de substituir a velha ANTES de a velha ir ao Fracttal (a revisão final de 27/10/2026)."""
    if agora:
        visao._LIVROS.pop((A.LIVRO_CONTAGENS, A.ABA_CONTAGENS), None)
        visao._LIVROS.pop(("_abas", A.LIVRO_CONTAGENS), None)
        g = visao._calcular(CHAVE_APP, _do_app)       # deu certo: vira a cópia que a tela lê
    else:
        g = visao._ler(CHAVE_APP, _do_app)
    if g.erro or not g.dados:
        raise F.Recusada(f"{g.erro or 'Não consegui ler as contagens do App'}: tente de novo em instantes.")
    return g.dados


# ── o estado, pelos eventos ────────────────────────────────────────────────────────────────────────────────────────────
def _por_contagem(eventos: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for e in eventos:
        if _txt(e.get("contagem_id")):
            out.setdefault(_txt(e.get("contagem_id")), []).append(e)
    return out


def _estado_da_gravacao(eventos: list[dict]) -> str:
    lote = {_id(e.get("id_item")) for e in eventos if e.get("tipo") == "aprovada" and _txt(e.get("id_item"))}
    if not lote:
        return "gravando"
    gravadas = {_id(e.get("id_item")) for e in eventos if e.get("tipo") == "peca_gravada"}
    conflitos = {_id(e.get("id_item")) for e in eventos if e.get("tipo") == "conflito"} - gravadas
    if lote - gravadas - conflitos:
        return "gravando"
    return "gravada_com_conflitos" if conflitos & lote else "gravada"


def estado_dos_eventos(eventos: list[dict]) -> str:
    """O estado de UMA contagem pelos eventos dela, na ordem da gravação (sem a conta da substituição, que olha as outras
    contagens: ver `ler`)."""
    tipos = {e.get("tipo") for e in eventos}
    if tipos & {"aprovada", "peca_gravada", "conflito"}:
        return _estado_da_gravacao(eventos)
    if "recontagem_pedida" in tipos:
        return "recontagem_pedida"
    if "substituida" in tipos:
        return "substituida"
    # a recontagem só de algumas peças (30/10/2026) não mata a contagem: o resto dela segue para aprovar e gravar
    if tipos & {"peca_tirada", "numero_corrigido", "recontagem_item_pedida"}:
        return "revisada"
    return "nova"


def curadoria_da(cfg, contagem_id: str, linhas_da_curadoria: list[dict] | None = None) -> dict[str, dict]:
    """As decisões da curadoria desta contagem no formato das contas: `{ID da linha: {"decisao", "id_item", "codigo"}}`. Vale
    a última de cada linha (a hora da decisão; a ordem do livro desempata)."""
    linhas = F.ler(cfg)[F.ABA_CURADORIA] if linhas_da_curadoria is None else linhas_da_curadoria
    ultima: dict[str, tuple] = {}
    for i, l in enumerate(linhas):
        chave_linha = _txt(l.get("chave_linha"))
        if _txt(l.get("contagem_id")) != _txt(contagem_id) or not chave_linha:
            continue
        quando = (_txt(l.get("decidida_em")), i)         # UTC com Z: o texto ordena como a hora
        if chave_linha not in ultima or quando >= ultima[chave_linha][0]:
            ultima[chave_linha] = (quando, l)
    return {k: {"decisao": _txt(l.get("decisao")), "id_item": _id(l.get("id_item")), "codigo": _txt(l.get("codigo_criado"))}
            for k, (_, l) in ultima.items()}


def revisao_da(cfg, contagem_id: str, motivos: bool = True) -> dict:
    """O que o PCM já fez na revisão desta contagem, na forma que as contas pedem (`contas.itens_do_lote`): `tiradas`
    {id_item: motivo}, `corrigidos` {id_item: número}, com `motivos_corrigidos` {id_item: motivo}, e `recontar` {id_item:
    motivo}, as peças com a recontagem pedida nesta contagem (30/10/2026), com `recontar_em` {id_item: a hora do pedido, UTC}
    para a nota "recontagem pedida em dd/mm". Vale a última correção de cada peça e o primeiro pedido de recontagem (a peça
    sai do lote nele; pedir de novo é recusado). O motivo só existe cifrado no livro; é aqui que se abre (a tela do PCM o
    mostra, a auditoria não). `motivos` falso não decifra nada (quem não vai mostrar o texto não o abre: os outros setores
    leem só "tirada do lote")."""
    tiradas, corrigidos, texto, recontar, recontar_em = {}, {}, {}, {}, {}

    def motivo(e) -> str:
        return _txt(F.decifrar(cfg, F.ABA_EVENTO, e).get("motivo")) if motivos else ""
    for e in F.ler(cfg)[F.ABA_EVENTO]:
        if _txt(e.get("contagem_id")) != _txt(contagem_id) or not _txt(e.get("id_item")):
            continue
        item = _id(e.get("id_item"))
        if e.get("tipo") == "peca_tirada":
            tiradas[item] = motivo(e)
        elif e.get("tipo") == "numero_corrigido":
            valor = A.contado(e.get("para_qtd"))
            if valor is not None:
                corrigidos[item] = valor
                texto[item] = motivo(e)
        elif e.get("tipo") == "recontagem_item_pedida" and item not in recontar:
            recontar[item], recontar_em[item] = motivo(e), _txt(e.get("quando"))
    return {"tiradas": tiradas, "corrigidos": corrigidos, "motivos_corrigidos": texto, "recontar": recontar,
            "recontar_em": recontar_em}


# ── as contas de cada contagem ─────────────────────────────────────────────────────────────────────────────────────────
def _conta_as_linhas(linhas: list[dict], curadoria: dict) -> tuple[int, int, int]:
    """(contadas, em branco, na curadoria), pelas linhas depois do dedupe por (ID da contagem, ID da linha), como as contas
    fazem. Uma linha é de peça se o Tipo existe (e, menos no `fora_do_catalogo`, tem ID do item; a avariada sem o ID vale pelo
    Código da boa, como nas contas). Em branco é a linha sem
    número (o achado em branco inclusive); na curadoria é a linha com número que o PCM ainda precisa decidir (o genérico por
    identificar, o achado fora do catálogo e a avariada sem o -AV no catálogo), e as contadas são as outras com número: os
    três somam as linhas de peça. As linhas já vêm resolvidas (`avariados.resolver`, na `ler`): a avariada que achou o -AV
    é uma linha `item` dele."""
    unicas = contas._unicas(linhas)          # o mesmo dedupe das contas (o mesmo pacote)
    validas = [l for l in unicas
               if _txt(l.get("Tipo")).lower() in A.TIPOS_CONTAGEM
               and (_txt(l.get("Tipo")).lower() == "fora_do_catalogo" or A.id_ou_vazio(l.get("ID do item"))
                    or (_txt(l.get("Tipo")).lower() == "avariado" and avariados.codigo_da_linha(l)))]
    em_branco = sum(1 for l in validas if A.contado(l.get("Contado")) is None)
    na_curadoria = sum(len(i["pendentes"]) for i in contas.itens_do_lote(unicas, {}, curadoria, {})
                       if i["situacao"] == "curadoria")
    return len(validas) - em_branco - na_curadoria, em_branco, na_curadoria


def _motivo_nao_aprovavel(c: dict, agora: datetime) -> str:
    """Por que a contagem não se aprova (vazio se se aprova). A ordem: o que já aconteceu com ela, o que o App mandou de
    errado, e por fim a janela do "Contada em"."""
    if c["estado"] in DA_GRAVACAO:
        return "já gravada"
    if c["estado"] == "substituida":
        return "substituída"
    if c["estado"] == "recontagem_pedida":
        return "recontagem pedida"
    if not c["id_almox"]:
        return "contagem sem almoxarifado"
    if any(_vazio(l.get("ID da linha")) for l in c["linhas"]):
        return "linha sem ID da linha"
    if any(_peca_sem_id(l) for l in c["linhas"]):
        return "linha de peça sem o ID do item"
    if any(_avariada_sem_peca(l) for l in c["linhas"]):
        return "avariada sem o ID nem o Código da peça boa"
    if any(l.get("_sem_catalogo") for l in c["linhas"]):
        return SEM_CATALOGO
    try:
        contada = instante(c["contada_em"])
    except ValueError:
        return "data da contagem ilegível"
    if contas.aprovavel(c["contada_em"], agora):
        return ""
    return "contada no futuro: o relógio do celular" if contada > instante(agora) else f"mais de {contas.APROVAVEL_DIAS} dias"


# a contagem com avariada quando o catálogo do App não se leu agora (`avariados.resolver` com o catálogo None, 31/10/2026)
SEM_CATALOGO = "o catálogo do App não foi lido agora: as avariadas não se resolvem; tente de novo em alguns minutos"


def _avariada_sem_peca(l: dict) -> bool:
    """A avariada sem o ID E sem o Código da peça boa: não há de que peça ela é (o contrato do App violado). Sem só o ID, o
    Código basta (`avariados.resolver`)."""
    return _txt(l.get("Tipo")).lower() == "avariado" and not A.id_ou_vazio(l.get("ID do item")) \
        and not avariados.codigo_da_linha(l)


def _peca_sem_id(l: dict) -> bool:
    """A linha de peça (`item` ou `identificar`) COM número e SEM o ID do item (o vazio, ou o "None" que o `sync-xlsx` escreve):
    não é de peça nenhuma. As contas a pulavam caladas (`contas._ler`), e as unidades contadas sumiam do lote sem ninguém
    saber (a revisão final de 04/11/2026). Em branco, nada se perde: a linha segue fora, sem aviso."""
    return _txt(l.get("Tipo")).lower() in ("item", "identificar") and A.contado(l.get("Contado")) is not None \
        and not A.id_ou_vazio(l.get("ID do item"))


def _avisos_do_app(c: dict) -> list[str]:
    """O contrato do App violado. Sem o ID da linha as contas não têm como reconhecer a peça (o "None" do `sync-xlsx` juntaria
    duas linhas numa e perderia unidades contadas); sem o almoxarifado não há saldo do sistema para ler; a linha de peça com
    número e sem o ID do item (`_peca_sem_id`) e a avariada sem o ID e sem o Código da boa não são de peça nenhuma, e sumir com
    elas esconderia unidades contadas."""
    avisos = []
    if any(_vazio(l.get("ID da linha")) for l in c["linhas"]):
        avisos.append("o App mandou linha sem ID da linha")
    if not c["id_almox"]:
        avisos.append("o App mandou contagem sem ID do almoxarifado")
    if any(_peca_sem_id(l) for l in c["linhas"]):
        avisos.append("o App mandou linha de peça sem o ID do item")
    if any(_avariada_sem_peca(l) for l in c["linhas"]):
        avisos.append("o App mandou avariada sem o ID nem o Código da peça boa")
    return avisos


def _aviso(c: dict) -> str:
    """Por que a contagem não vai à revisão, e a tela diz o quê: o contrato do App violado (`_avisos_do_app`) e, sem culpa do
    App, a avariada com o catálogo do App que não se leu agora (`SEM_CATALOGO`: passa quando o catálogo for lido). O
    `SEM_CATALOGO` só na contagem que ainda se revisa (`REVISAVEIS`, com o estado já depois da substituição): a aprovada, a
    gravada, a recusada e a substituída não têm o que revisar, e o aviso escondia a etapa Gravação (o Continuar e o Encerrar
    da gravação parada com o almoxarifado travado no Fracttal) e a Auditoria por até 5 min (a revisão final de 31/10/2026)."""
    avisos = _avisos_do_app(c)
    if c["estado"] in REVISAVEIS and any(l.get("_sem_catalogo") for l in c["linhas"]):
        avisos.append(SEM_CATALOGO)
    return "; ".join(avisos)


def _pode_substituir(c: dict, agora: datetime) -> bool:
    """A contagem que pode valer como "a mais nova" de um almoxarifado: dentro do contrato do App e com a data da contagem
    legível e que não passa do relógio adiantado do celular (`contas.RELOGIO_ADIANTADO`). A sem ID da linha, a sem almoxarifado
    e a do futuro não se aprovam, e uma que não se aprova não pode substituir as que se aprovam. O catálogo que não se leu
    agora NÃO tira dela o lugar de mais nova (31/10/2026): é uma falha de leitura que passa, e a velha viraria aprovável por
    alguns minutos."""
    if c["aviso_do_app"]:
        return False
    try:
        return instante(c["contada_em"]) - instante(agora) <= contas.RELOGIO_ADIANTADO
    except ValueError:
        return False


def ler(cfg, *, com_teste: bool = False, app_agora: bool = False) -> dict:
    """`{"livro_existe", "contagens", "itens", "app_com_recontagem", "app_com_fotos"}`: as contagens do App com o estado de cada
    uma (a lista de `contagens`), o nome de cada peça (`itens`: `{id_item: {codigo, nome, unidade}}`) e o que o App que publicou
    o livro faz, pelas colunas dele (`_o_que_o_app_faz`: lê os pedidos de recontagem, manda as fotos; os textos das telas dizem
    isso sozinhos). As `linhas` de cada contagem saem com as avariadas
    já levadas ao -AV pelo catálogo (`avariados.resolver`): é a única porta das linhas para o lote, a curadoria e a gravação.
    Levanta `fato_inventario.Recusada` se não leu o livro do App ou o do inventário (nunca devolve vazio no lugar do que não
    leu).

    `com_teste`: com as contagens do almoxarifado de teste (a curadoria, o único lugar em que ele vale; elas só se substituem
    entre si, porque a substituição é por almoxarifado). `app_agora`: o livro do App relido agora, sem a cópia de 5 min (a
    aprovação)."""
    app = _app(agora=app_agora)
    versao = {k: bool(app.get(k)) for k in ("app_com_recontagem", "app_com_fotos")}      # `_o_que_o_app_faz`
    if not app["livro_existe"]:
        return {"livro_existe": False, "contagens": [], "itens": {}, **versao}
    teste = set() if com_teste else A.ids_de_teste(cfg)
    do_livro = F.ler(cfg)
    eventos, curadoria = _por_contagem(do_livro[F.ABA_EVENTO]), do_livro[F.ABA_CURADORIA]
    agora = visao._agora()
    # cópias: a lista do App é a de todos (5 min), e quem recebe pode mexer na sua. As avariadas da aba Avariados (30/10/2026)
    # vão ao -AV AQUI, uma vez (`avariados.resolver`, que devolve cópias): o lote, a curadoria, a gravação e as contas da lista
    # veem as mesmas linhas resolvidas
    catalogo = app["itens"] if app.get("itens_lido", True) else None        # None: não se leu agora (não é vazio)
    cs = [dict(c, linhas=avariados.resolver(c["linhas"], catalogo)) for c in app["contagens"]
          if c["id_almox"] not in teste]
    for c in cs:
        c["estado"] = estado_dos_eventos(eventos.get(c["contagem_id"], []))
        c["aviso_do_app"] = bool(_avisos_do_app(c))
    # a substituição olha só as contagens VIVAS (a recontagem pedida, recusada pelo PCM, não tem número para pôr no lugar
    # das boas) e BOAS (sem o contrato violado e com um "Contada em" legível e que não é do futuro): a mais nova que não se
    # aprova não pode tirar do caminho as que se aprovam, senão o almoxarifado fica sem nenhuma contagem para revisar. E deixa
    # em paz as que já gravaram ou estão gravando. A contagem de recontagem (o `recontagem_de` de cada uma, 30/10/2026) não
    # substitui ninguém: a conta é das `contas.substituidas`
    vivas = [c for c in cs if c["estado"] not in MORTAS and _pode_substituir(c, agora)]
    velhas = contas.substituidas(vivas, {c["contagem_id"] for c in cs if c["estado"] in DA_GRAVACAO})
    for c in cs:
        if c["contagem_id"] in velhas:
            c["estado"] = "substituida"
        c["aviso"] = _aviso(c)                  # com o estado final: o do catálogo só na que ainda se revisa
        cur = curadoria_da(cfg, c["contagem_id"], curadoria)
        c["n_contadas"], c["n_em_branco"], c["n_curadoria"] = _conta_as_linhas(c["linhas"], cur)
        c["motivo_nao_aprovavel"] = _motivo_nao_aprovavel(c, agora)
        c["aprovavel"] = not c["motivo_nao_aprovavel"]
    cs.sort(key=lambda c: (_quando(c["contada_em"]), _quando(c["enviada_em"]), c["contagem_id"]), reverse=True)
    return {"livro_existe": True, "contagens": cs, "itens": app["itens"], **versao}


def contagens(cfg) -> list[dict]:
    """Uma por contagem, da mais nova para a mais velha, sem o almoxarifado de teste: `contagem_id`, `id_almox`, `almox` (o
    nome), `usina` (o nome do cadastro, ou o do Fracttal se a usina não liga), `usina_id` (e `usina_ligada_por`),
    `contada_em`, `enviada_em`, `recontagem_de` (o ID da contagem cuja recontagem esta atende; vazio na inteira), `linhas`
    (as do livro do App, com as avariadas resolvidas), `n_contadas`, `n_em_branco`, `n_curadoria`, `estado` (em `ESTADOS`), `aprovavel` e, quando não,
    `motivo_nao_aprovavel`; `aviso` quando o App violou o contrato ou, na contagem que ainda se revisa (`REVISAVEIS`), com
    avariada e o catálogo do App que não se leu agora (`SEM_CATALOGO`)."""
    return ler(cfg)["contagens"]


def livro_existe(cfg) -> bool:
    """O App já publicou o livro das contagens? Sem ele, a tela diz que o App ainda não publica (não é "nenhuma contagem")."""
    return ler(cfg)["livro_existe"]


def catalogo_lido() -> bool:
    """O catálogo do App (o livro Itens) se leu na cópia de agora? A curadoria diz na tela por que as avariadas sumiram dela
    enquanto ele não se lê (31/10/2026). Levanta `fato_inventario.Recusada` como a `ler`, se o livro do App não se leu."""
    return bool(_app().get("itens_lido", True))


def app_com_fotos() -> bool:
    """O App que publicou o livro das contagens manda as fotos ao Nexus (`_o_que_o_app_faz`)? A curadoria diz, na foto que falta,
    se ela "ainda não chegou" ou se o App ainda não as envia (04/11/2026). Pela cópia de agora, como o `catalogo_lido`, e levanta
    como ele."""
    return bool(_app().get("app_com_fotos"))


# ── as recontagens pedidas e para onde foi cada uma (04/11/2026) ───────────────────────────────────────────────────────────
ATENDIDAS_DIAS = 30         # as atendidas que o cartão "Recontagens pedidas" ainda mostra (o <details> da lista do Inventário)
_PEDIDOS = {"recontagem_item_pedida": "peca", "recontagem_pedida": "inteira"}


def _contou(c: dict, id_item: str) -> bool:
    """A contagem contou a peça: uma linha de peça (`item` ou `identificar`) com o ID do item dela e o "Contado" não vazio,
    depois do dedupe da fila offline (`contas._unicas`). As linhas já vêm resolvidas (`avariados.resolver`, na `ler`): a avariada
    da boa que achou o -AV é linha `item` dele e atende o pedido do -AV (o técnico reconta o -AV na aba Avariados, pela boa); a
    que não achou continua `avariado`, com o ID da BOA, e não atende o pedido da boa (ela conta as avariadas, não a boa). Com o
    catálogo do App que não se leu agora (`_sem_catalogo`) a avariada também continua `avariado`: o pedido do -AV espera a
    próxima leitura, nunca é dado por atendido sem a linha."""
    return any(_txt(l.get("Tipo")).lower() in ("item", "identificar") and A.id_ou_vazio(l.get("ID do item")) == id_item
               and A.contado(l.get("Contado")) is not None for l in contas._unicas(c.get("linhas")))


def pedidos_de_recontagem(contagens: list[dict], eventos: list[dict], agora, teste=()) -> dict:
    """Os pedidos de recontagem do PCM e para onde foi cada um: o cartão "Recontagens pedidas" da lista do Inventário (04/11/2026;
    caso real: uma pessoa do PCM pediu a recontagem de uma peça e perguntou "não sei pra onde foi essa informação"). Puro.

    `contagens`: as da `ler` (as linhas com as avariadas já levadas ao -AV, sem o almoxarifado de teste); `eventos`: os do livro do
    inventário, na ordem dele; `teste`: os IDs do almoxarifado de teste (o pedido dele fica de fora, como no resto).

    Um pedido por `recontagem_item_pedida` (a peça; o mesmo par contagem e peça vale o primeiro, como na `revisao_da`) e por
    `recontagem_pedida` (a contagem inteira). **Atendido** (a mesma regra nas duas versões do App, a seção 4 da proposta das
    contagens do App): uma contagem do MESMO almoxarifado, outra que não a do pedido, com o "Contada em" DEPOIS do pedido, que
    contou a peça (`_contou`); na inteira, qualquer contagem do almoxarifado depois do pedido. Vale a mais antiga que atende. A
    recontagem que o App novo manda (com o "Recontagem de") atende por esta regra, e a contagem nova inteira de hoje também.

    `{"esperando": [...], "atendidas": [...]}`: os esperando dos últimos `contas.APROVAVEL_DIAS` (a janela do livro do App), o mais
    velho primeiro; os atendidos dos últimos `ATENDIDAS_DIAS`, pelo dia da contagem que atendeu, o mais novo primeiro. Cada pedido:
    `tipo` ("peca" ou "inteira"), `contagem_id`, `id_almox`, `id_item` e `codigo` (vazios na inteira), `quando` (a hora do
    pedido, UTC) e `atendida_por` (`{"contagem_id", "contada_em"}` da que atendeu, ou None). O motivo, nunca: é texto livre, e a
    auditoria o mostra a quem pode."""
    teste = {_id(t) for t in teste}
    agora_ = instante(agora)
    da_contagem = {c["contagem_id"]: c for c in contagens}
    vistos, esperando, atendidas = set(), [], []
    for e in eventos:
        tipo, cid = _PEDIDOS.get(_txt(e.get("tipo"))), _txt(e.get("contagem_id"))
        if not tipo or not cid:
            continue
        almox = A.id_ou_vazio(e.get("id_almoxarifado")) or (da_contagem.get(cid) or {}).get("id_almox", "")
        item = A.id_ou_vazio(e.get("id_item")) if tipo == "peca" else ""
        if not almox or almox in teste or (tipo == "peca" and not item) or (tipo, cid, item) in vistos:
            continue
        try:
            quando = instante(e.get("quando"))
        except ValueError:
            continue                        # sem a hora não há "depois do pedido" (o livro sempre a põe)
        vistos.add((tipo, cid, item))
        quem = [c for c in contagens if c["id_almox"] == almox and c["contagem_id"] != cid
                and _quando(c["contada_em"]) > quando and (tipo == "inteira" or _contou(c, item))]
        a = min(quem, key=lambda c: (_quando(c["contada_em"]), _quando(c["enviada_em"]), c["contagem_id"]), default=None)
        p = {"tipo": tipo, "contagem_id": cid, "id_almox": almox, "id_item": item,
             "codigo": _txt(e.get("codigo")) if tipo == "peca" else "", "quando": _txt(e.get("quando")),
             "atendida_por": None if a is None else {"contagem_id": a["contagem_id"], "contada_em": a["contada_em"]}}
        if a is None:
            if agora_ - quando <= timedelta(days=contas.APROVAVEL_DIAS):
                esperando.append((quando, p))
        elif agora_ - _quando(a["contada_em"]) <= timedelta(days=ATENDIDAS_DIAS):
            atendidas.append((_quando(a["contada_em"]), p))
    esperando.sort(key=lambda x: (x[0], x[1]["contagem_id"], x[1]["id_item"]))
    atendidas.sort(key=lambda x: (x[0], x[1]["contagem_id"], x[1]["id_item"]), reverse=True)
    return {"esperando": [p for _, p in esperando], "atendidas": [p for _, p in atendidas]}


def recontagens(cfg, lidas: dict | None = None) -> dict:
    """A conta do cartão "Recontagens pedidas" (`pedidos_de_recontagem`) sobre o que se lê agora: as contagens (`lidas`, o que a
    `ler` já devolveu na mesma tela, ou lidas aqui) e os eventos do livro do inventário (a cópia de 2 min do `fato_inventario.ler`,
    a mesma que a `ler` usou). Levanta `fato_inventario.Recusada` como a `ler`."""
    lidas = ler(cfg) if lidas is None else lidas
    return pedidos_de_recontagem(lidas["contagens"], F.ler(cfg)[F.ABA_EVENTO], visao._agora(), A.ids_de_teste(cfg))
