"""As contagens do inventário do almoxarifado e o estado de cada uma (Levi, 26/10/2026). Desenho:
`docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md`, seção 4.2.

De onde vem cada parte:
- **as contagens**, do livro que o App de Campo publica (`almoxarifado_contagens_app_campo`, o contrato de 14 colunas em
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
| `peca_tirada` ou `numero_corrigido` | `revisada` |
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

from datetime import datetime, timezone

from ...campo import visao
from ...dados import almoxarifado as A
from ...dados import fato_inventario as F
from ...dados import livros
from ...dados.fato_almoxarifado import LIGADA_DE_PARA
from ...dados.fatos import Ligador
from . import contas
from .estoque import instante

ESTADOS = ("nova", "revisada", "recontagem_pedida", "substituida", "gravando", "gravada", "gravada_com_conflitos")
# os estados de quem já foi aprovado: a gravação começou (ou acabou). Contam como "gravada" para a substituição, que não
# desfaz o que já está no Fracttal
DA_GRAVACAO = ("gravando", "gravada", "gravada_com_conflitos")
# a contagem que já não está viva: não substitui ninguém e ninguém a substitui
MORTAS = ("recontagem_pedida", "substituida")

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


def _do_app() -> dict:
    """O que se lê do banco: as contagens do App, agrupadas, com a usina ligada e o nome do almoxarifado, e o nome de cada
    peça (a contagem só traz o ID e o código). Roda dentro do `visao._ler` (cópia de 5 min, renovada por trás)."""
    abas = visao._ciclo(("_abas", A.LIVRO_CONTAGENS),
                        lambda: livros.abas(visao._base(), visao._sessao(), A.LIVRO_CONTAGENS))
    if A.ABA_CONTAGENS not in abas:
        return {"livro_existe": False, "contagens": [], "itens": {}}
    linhas = visao._livro(A.LIVRO_CONTAGENS, A.ABA_CONTAGENS)
    lig = Ligador(visao._livro("cadastro_nexus", "usinas"), visao._livro("cadastro_nexus", "de_para"), [], {})
    nome_usina = {_id(u.get("usina_id")): _txt(u.get("nome")) for u in visao._livro("cadastro_nexus", "usinas")}
    grupos: dict[str, list[dict]] = {}
    for l in linhas:
        if not _vazio(l.get("ID da contagem")):
            grupos.setdefault(_txt(l.get("ID da contagem")), []).append(l)
    # o nome do almoxarifado e o das peças só enfeitam a tela: sem esses livros a contagem aparece pelo ID
    almox = {}
    for s in _livro_ou_vazio(A.LIVRO_SALDO, A.ABA_SALDO):
        if not _vazio(s.get("ID do almoxarifado")) and not _vazio(s.get("Almoxarifado")):
            almox.setdefault(_id(s.get("ID do almoxarifado")), _txt(s.get("Almoxarifado")))
    itens = {_id(i.get("ID do item")): {"codigo": _txt(i.get("Código")), "nome": _txt(i.get("Nome")),
                                         "unidade": _txt(i.get("Unidade")).lower()}
             for i in _livro_ou_vazio(A.LIVRO_ITENS, A.ABA_ITENS) if not _vazio(i.get("ID do item"))}
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
                          "linhas": ls})
    return {"livro_existe": True, "contagens": contagens, "itens": itens}


def _livro_ou_vazio(livro: str, aba: str) -> list[dict]:
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
    if tipos & {"peca_tirada", "numero_corrigido"}:
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
    {id_item: motivo} e `corrigidos` {id_item: número}, com `motivos_corrigidos` {id_item: motivo}. Vale a última correção
    de cada peça. O motivo só existe cifrado no livro; é aqui que se abre (a tela do PCM o mostra, a auditoria não). `motivos`
    falso não decifra nada (quem não vai mostrar o texto não o abre: os outros setores leem só "tirada do lote")."""
    tiradas, corrigidos, texto = {}, {}, {}
    for e in F.ler(cfg)[F.ABA_EVENTO]:
        if _txt(e.get("contagem_id")) != _txt(contagem_id) or not _txt(e.get("id_item")):
            continue
        item = _id(e.get("id_item"))
        if e.get("tipo") == "peca_tirada":
            tiradas[item] = _txt(F.decifrar(cfg, F.ABA_EVENTO, e).get("motivo")) if motivos else ""
        elif e.get("tipo") == "numero_corrigido":
            valor = A.contado(e.get("para_qtd"))
            if valor is not None:
                corrigidos[item] = valor
                texto[item] = _txt(F.decifrar(cfg, F.ABA_EVENTO, e).get("motivo")) if motivos else ""
    return {"tiradas": tiradas, "corrigidos": corrigidos, "motivos_corrigidos": texto}


# ── as contas de cada contagem ─────────────────────────────────────────────────────────────────────────────────────────
def _conta_as_linhas(linhas: list[dict], curadoria: dict) -> tuple[int, int, int]:
    """(contadas, em branco, na curadoria), pelas linhas depois do dedupe por (ID da contagem, ID da linha), como as contas
    fazem. Uma linha é de peça se o Tipo existe (e, em `item` e `identificar`, tem ID do item). Em branco é a linha sem número
    (o achado em branco inclusive); na curadoria é a linha com número que o PCM ainda precisa decidir (o genérico por
    identificar e o achado fora do catálogo), e as contadas são as outras com número: os três somam as linhas de peça."""
    unicas = contas._unicas(linhas)          # o mesmo dedupe das contas (o mesmo pacote)
    validas = [l for l in unicas
               if _txt(l.get("Tipo")).lower() in A.TIPOS_CONTAGEM
               and (_txt(l.get("Tipo")).lower() == "fora_do_catalogo" or _id(l.get("ID do item")))]
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
    try:
        contada = instante(c["contada_em"])
    except ValueError:
        return "data da contagem ilegível"
    if contas.aprovavel(c["contada_em"], agora):
        return ""
    return "contada no futuro: o relógio do celular" if contada > instante(agora) else f"mais de {contas.APROVAVEL_DIAS} dias"


def _aviso(c: dict) -> str:
    """O contrato do App violado: a contagem não vai à revisão, e a tela diz o quê. Sem o ID da linha as contas não têm como
    reconhecer a peça (o "None" do `sync-xlsx` juntaria duas linhas numa e perderia unidades contadas), e sem o almoxarifado
    não há saldo do sistema para ler."""
    avisos = []
    if any(_vazio(l.get("ID da linha")) for l in c["linhas"]):
        avisos.append("o App mandou linha sem ID da linha")
    if not c["id_almox"]:
        avisos.append("o App mandou contagem sem ID do almoxarifado")
    return "; ".join(avisos)


def _pode_substituir(c: dict, agora: datetime) -> bool:
    """A contagem que pode valer como "a mais nova" de um almoxarifado: dentro do contrato do App e com a data da contagem
    legível e que não passa do relógio adiantado do celular (`contas.RELOGIO_ADIANTADO`). A sem ID da linha, a sem almoxarifado
    e a do futuro não se aprovam, e uma que não se aprova não pode substituir as que se aprovam."""
    if c["aviso"]:
        return False
    try:
        return instante(c["contada_em"]) - instante(agora) <= contas.RELOGIO_ADIANTADO
    except ValueError:
        return False


def ler(cfg, *, com_teste: bool = False, app_agora: bool = False) -> dict:
    """`{"livro_existe", "contagens", "itens"}`: as contagens do App com o estado de cada uma (a lista de `contagens`) e o
    nome de cada peça (`itens`: `{id_item: {codigo, nome, unidade}}`). Levanta `fato_inventario.Recusada` se não leu o
    livro do App ou o do inventário (nunca devolve vazio no lugar do que não leu).

    `com_teste`: com as contagens do almoxarifado de teste (a curadoria, o único lugar em que ele vale; elas só se substituem
    entre si, porque a substituição é por almoxarifado). `app_agora`: o livro do App relido agora, sem a cópia de 5 min (a
    aprovação)."""
    app = _app(agora=app_agora)
    if not app["livro_existe"]:
        return {"livro_existe": False, "contagens": [], "itens": {}}
    teste = set() if com_teste else A.ids_de_teste(cfg)
    do_livro = F.ler(cfg)
    eventos, curadoria = _por_contagem(do_livro[F.ABA_EVENTO]), do_livro[F.ABA_CURADORIA]
    agora = visao._agora()
    # cópias: a lista do App é a de todos (5 min), e quem recebe pode mexer na sua
    cs = [dict(c, linhas=[dict(l) for l in c["linhas"]]) for c in app["contagens"] if c["id_almox"] not in teste]
    for c in cs:
        c["estado"] = estado_dos_eventos(eventos.get(c["contagem_id"], []))
        c["aviso"] = _aviso(c)
    # a substituição olha só as contagens VIVAS (a recontagem pedida, recusada pelo PCM, não tem número para pôr no lugar
    # das boas) e BOAS (sem o contrato violado e com um "Contada em" legível e que não é do futuro): a mais nova que não se
    # aprova não pode tirar do caminho as que se aprovam, senão o almoxarifado fica sem nenhuma contagem para revisar. E deixa
    # em paz as que já gravaram ou estão gravando
    vivas = [c for c in cs if c["estado"] not in MORTAS and _pode_substituir(c, agora)]
    velhas = contas.substituidas(vivas, {c["contagem_id"] for c in cs if c["estado"] in DA_GRAVACAO})
    for c in cs:
        if c["contagem_id"] in velhas:
            c["estado"] = "substituida"
        cur = curadoria_da(cfg, c["contagem_id"], curadoria)
        c["n_contadas"], c["n_em_branco"], c["n_curadoria"] = _conta_as_linhas(c["linhas"], cur)
        c["motivo_nao_aprovavel"] = _motivo_nao_aprovavel(c, agora)
        c["aprovavel"] = not c["motivo_nao_aprovavel"]
    cs.sort(key=lambda c: (_quando(c["contada_em"]), _quando(c["enviada_em"]), c["contagem_id"]), reverse=True)
    return {"livro_existe": True, "contagens": cs, "itens": app["itens"]}


def contagens(cfg) -> list[dict]:
    """Uma por contagem, da mais nova para a mais velha, sem o almoxarifado de teste: `contagem_id`, `id_almox`, `almox` (o
    nome), `usina` (o nome do cadastro, ou o do Fracttal se a usina não liga), `usina_id` (e `usina_ligada_por`),
    `contada_em`, `enviada_em`, `linhas` (as do livro do App), `n_contadas`, `n_em_branco`, `n_curadoria`, `estado` (em
    `ESTADOS`), `aprovavel` e, quando não, `motivo_nao_aprovavel`; `aviso` quando o App violou o contrato."""
    return ler(cfg)["contagens"]


def livro_existe(cfg) -> bool:
    """O App já publicou o livro das contagens? Sem ele, a tela diz que o App ainda não publica (não é "nenhuma contagem")."""
    return ler(cfg)["livro_existe"]
