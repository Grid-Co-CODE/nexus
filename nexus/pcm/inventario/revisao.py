"""A revisão de uma contagem pelo PCM (Levi, 26/10/2026; desenho, seção 4.2): o que a aba Inventário mostra (a lista das
contagens e a contagem aberta, com o Sistema × Contado × Δ × Situação e os seis grupos da confirmação) e o que o PCM faz nela
(tirar uma peça do lote, corrigir o número, pedir a recontagem). Sem Flask: quem chama (as rotas, em `__init__`) passa a
configuração, a função que lê o saldo do Fracttal e a pessoa do pedido; os testes passam as suas.

Três regras que a tela segue:

- **O Sistema é lido na hora** (`ler_sistema`, uma leitura do almoxarifado inteiro pelo adaptador), não o saldo da varredura
  da madrugada: o saldo muda durante o dia. Sem o login do Fracttal (quem entrou pela senha de administrador), com a cota
  esgotada (429) ou com o Fracttal fora do ar, a tela mostra o que o técnico contou, SEM Sistema nem Δ, e diz por quê: a
  situação de cada peça depende do saldo, e uma conta com saldo 0 chutado mandaria "subir" o estoque inteiro. Nunca 500. A
  contagem que já não se aprova (velha, substituída, gravada, recontagem pedida) também não lê o Fracttal: gastaria a cota da
  empresa à toa.
- **Revisar não fala com o Fracttal.** Tirar, corrigir e pedir a recontagem só gravam um evento no livro do inventário, no
  nome de quem revisou (`pessoa_hmac`, sempre; o `pessoa_id` quando o cadastro a acha), com o motivo SÓ cifrado (a API do banco
  tem leitura aberta). Quem entrou pela senha não é uma pessoa: a revisão ficaria sem dono na auditoria, e é recusada.
- **Curadoria aberta avisa e não bloqueia** (o desenho 4.2 põe a curadoria como um dos seis grupos, que não mexe no estoque):
  decidir depois SOMA ao contado da peça escolhida, e a tela diz isso, para o PCM não aprovar achando que o número é final.
"""
from __future__ import annotations

import re

from ...campo import visao
from ...campo.ligacao_cadastro import codigo_da_pessoa, mapas_de
from ...dados import almoxarifado as A
from ...dados import fato_inventario as F
from . import contas, leitura
from .estoque import ErroFracttal, Limite, SemLogin

ROTULO_ESTADO = {"nova": "Nova", "revisada": "Revisada", "recontagem_pedida": "Recontagem pedida", "substituida": "Substituída",
                 "gravando": "Gravando", "gravada": "Gravada", "gravada_com_conflitos": "Gravada com conflitos"}
ROTULO_SITUACAO = {"para_cima": "Para cima", "para_baixo": "Para baixo", "zerar": "Zerar", "sem_alteracao": "Sem alteração",
                   "nao_tocada": "Não será tocada", "curadoria": "Curadoria"}
# os seis grupos da confirmação, na ordem das `contas.SITUACOES`: (título, o que acontece com a peça nele)
GRUPOS = {
    "para_cima": ("Ajuste para cima", "O contado é maior que o saldo do sistema: o saldo sobe no Fracttal."),
    "para_baixo": ("Ajuste para baixo", "O contado é menor que o saldo do sistema: o saldo cai no Fracttal."),
    "zerar": ("Zerar o estoque", "O técnico digitou 0 em peça com saldo: o estoque dela vai a zero no Fracttal. Confira peça "
                                  "a peça antes de gravar."),
    "sem_alteracao": ("Sem alteração", "O contado é igual ao saldo do sistema: nada é gravado."),
    "nao_tocada": ("Não será tocada", "Em branco, com contado inválido ou tirada do lote: nada é gravado, e o saldo do "
                                      "Fracttal fica como está."),
    "curadoria": ("Curadoria", "O que o PCM ainda decide (o genérico por identificar e a peça fora do catálogo): nada é "
                               "gravado até decidir."),
}
SEM_DELTA = ("nao_tocada", "curadoria")
MOTIVO_MAX = 1000

SEM_LOGIN = ("Sem o login do Fracttal nesta sessão: entre pelo Fracttal para ver o saldo do sistema e gravar. Aqui está o "
             "que o técnico contou.")
PAUSA = "Não li o saldo do sistema: o Fracttal pediu uma pausa; tente de novo em 1 minuto."
SO_PCM = "Só o setor PCM revisa o lote e pede a recontagem."

_NUMERO = re.compile(r"\d+(?:[.,]\d+)?")


class Recusa(Exception):
    """O pedido de revisão que não vale: `status` HTTP e o texto para a tela. Nada foi gravado."""

    def __init__(self, status: int, mensagem: str):
        super().__init__(mensagem)
        self.status, self.mensagem = status, mensagem


def _num(n, sinal: bool = False) -> str:
    """O número como o brasileiro o lê: vírgula decimal, sem o ".0" nem a notação científica ("1e+06"); com `sinal`, o
    "+" nos positivos (o Δ)."""
    if n is None:
        return "—"
    if n == 0:
        return "0"
    texto = f"{n:.6f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"+{texto}" if sinal and n > 0 else texto


def _hora(iso) -> str:
    d = visao._dt(iso)
    return d.strftime("%d/%m/%Y %H:%M") if d else "data ilegível"


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
               rotulo=ROTULO_ESTADO[c["estado"]]) for c in d["contagens"]]
    return {"erro": "", "livro_existe": d["livro_existe"], "contagens": cs,
            "a_revisar": sum(1 for c in cs if c["aprovavel"])}


def a_revisar(cfg) -> int | None:
    """Quantas contagens esperam o PCM (o número da aba Inventário na tela principal do Almoxarifado); None se não deu para
    ler: a aba segue sem número. Pela cópia de 5 min do `visao._ler`, renovada por trás: o número é só um enfeite, e a leitura do
    livro do inventário (2 min, no pedido) não pode segurar a tela principal quando o banco está lento (a lista do Inventário,
    essa sim, mostra o estado de agora)."""
    g = visao._ler(("pcm_inventario_a_revisar",),
                   lambda: {"n": sum(1 for c in leitura.contagens(cfg) if c["aprovavel"])})
    return None if g.erro or not g.dados else g.dados["n"]


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


def _enriquecer(i: dict, c: dict, nomes: dict, revisao: dict, achados: dict, com_sistema: bool, pode: bool) -> dict:
    """O item das contas com o que a tela mostra: o nome, os números como texto, o porquê de a peça não ser gravada e as ações."""
    meta = nomes.get(i["id_item"], {})
    tirada, notas = i["tirada"], []
    motivo_tirada = revisao["tiradas"].get(i["id_item"], "") if tirada else ""
    sit = i["situacao"]
    grupo = "nao_tocada" if tirada else sit
    if tirada:
        notas.append("tirada do lote" + (f": {motivo_tirada}" if motivo_tirada else ""))
    elif i["invalido"] and sit != "curadoria":
        notas.append("contado inválido (negativo): a peça não será gravada")
    elif sit == "nao_tocada":
        notas.append("em branco: o técnico não contou")
    if i["corrigido"]:
        notas.append(f"o técnico contou {_num(i['contado_campo'])}; o PCM corrigiu"
                     + (f" ({revisao['motivos_corrigidos'][i['id_item']]})" if revisao["motivos_corrigidos"].get(i["id_item"]) else ""))
    if com_sistema and i["id_item"] and i["contado"] is not None and not tirada:
        if not i["ligada"]:
            notas.append("não ligada ao almoxarifado: será ligada ao gravar")
        elif i["sistema"] is None:
            notas.append("saldo não informado pelo Fracttal (vale 0 na conta)")
    if sit == "curadoria" and i["id_item"]:
        notas.append("genérico por identificar: o PCM decide na curadoria")
    nome, descricao = meta.get("nome", ""), ""
    if sit == "curadoria" and not i["id_item"]:
        linha = achados.get(i["pendentes"][0] if i["pendentes"] else "", {})
        descricao = A._txt(linha.get("Descrição"))
        nome = "Fora do catálogo" + (f": {descricao}" if descricao else "")
    mexe = sit in contas.MEXEM and not tirada
    return dict(i, nome=nome, unidade=meta.get("unidade", ""), grupo=grupo, rotulo="Tirada do lote" if tirada else ROTULO_SITUACAO[sit],
                notas=notas, mexe=mexe, descricao=descricao,
                sistema_txt=("—" if not i["id_item"] else "não informado" if i["sistema"] is None and i["ligada"]
                             else _num(i["sistema"])),
                contado_txt=_num(i["contado"]), campo_txt=_num(i["contado_campo"]),
                # sem Δ onde não há conta a fazer: a peça que não se toca e a da curadoria, cujas unidades ainda não têm dono
                # (o Δ de um genérico com 4 unidades por identificar contra o saldo 20 diria "-16", e não é isso)
                delta_txt="—" if i["delta"] is None or sit in SEM_DELTA else _num(i["delta"], sinal=True),
                delta_sinal="" if not i["delta"] or sit in SEM_DELTA else "mais" if i["delta"] > 0 else "menos",
                # as ações são da peça com número que entra ou entraria no lote (a curadoria, sem ID, e a tirada não têm)
                acoes=bool(pode and c["aprovavel"] and i["id_item"] and not tirada and sit != "curadoria"
                           and (sit in contas.MEXEM or i["invalido"])))


def montar(cfg, contagem_id: str, ler_sistema, pode: bool = False) -> dict | None:
    """A contagem aberta, ou None se ela não existe. `ler_sistema(id_almox)`: o saldo do Fracttal lido na hora (o `ler` do
    adaptador, com o login de quem está no pedido). `pode`: quem abre pode revisar (aparecem as ações). Levanta
    `fato_inventario.Recusada` se não leu o livro do App ou o do inventário (a tela diz)."""
    todas = leitura.ler(cfg)
    c = next((x for x in todas["contagens"] if x["contagem_id"] == contagem_id), None)
    if c is None:
        return None
    ctx = {"c": c, "rotulo": ROTULO_ESTADO[c["estado"]], "contada_txt": _hora(c["contada_em"]),
           "enviada_txt": _hora(c["enviada_em"]), "itens": [], "grupos": [], "n_gravar": 0, "avisos_curadoria": [],
           "sistema": "nao_lido", "aviso_sistema": "", "com_sistema": False, "pode": pode, "so_pcm": SO_PCM}
    if c["aviso"]:
        return ctx           # o App fora do contrato: nenhum número, que seria pela metade
    revisao, curadoria = leitura.revisao_da(cfg, contagem_id), leitura.curadoria_da(cfg, contagem_id)
    sistema = None
    if c["aprovavel"]:
        sistema, ctx["sistema"], ctx["aviso_sistema"] = _do_sistema(ler_sistema, c["id_almox"])
    ctx["com_sistema"] = sistema is not None
    lote = contas.itens_do_lote(c["linhas"], sistema or {}, curadoria, revisao)
    achados = {A._id(l.get("ID da linha")): l for l in c["linhas"]}
    itens = [_enriquecer(i, c, todas["itens"], revisao, achados, ctx["com_sistema"], pode) for i in lote]
    ctx["itens"] = itens
    ctx["avisos_curadoria"] = _avisos_da_curadoria(lote)
    if ctx["com_sistema"]:
        ctx["n_gravar"] = sum(1 for i in itens if i["mexe"])
        for sit in contas.SITUACOES:
            membros = sorted((i for i in itens if i["grupo"] == sit), key=lambda i: (i["codigo"], i["id_item"]))
            ctx["grupos"].append({"id": sit, "titulo": GRUPOS[sit][0], "ajuda": GRUPOS[sit][1], "itens": membros,
                                  "n": len(membros), "aberto": sit == "zerar" and bool(membros), "destaque": sit == "zerar"})
    return ctx


# ── revisar ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _valor(bruto) -> float:
    """O número certo que o PCM digitou: zero ou mais, com vírgula ou ponto. 400 com a mensagem se não for."""
    if isinstance(bruto, (int, float)) and not isinstance(bruto, bool):
        n = float(bruto)
    elif isinstance(bruto, str) and _NUMERO.fullmatch(bruto.strip()):
        n = float(bruto.strip().replace(",", "."))
    else:
        n = None
    if n is None or n != n or n in (float("inf"), float("-inf")) or n < 0:
        raise Recusa(400, "Informe o número certo: zero ou mais, com vírgula ou ponto (por exemplo 12 ou 2,5).")
    return n


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
    """Tira uma peça do lote, corrige o número contado ou pede a recontagem. `pedido`: `{"acao": "tirar" | "corrigir" |
    "recontagem", "id_item"?, "valor"?, "motivo"}`. Levanta `Recusa` (nada foi gravado) com o status e o texto.

    O motivo é obrigatório nas três (o desenho: "cada um com o motivo, na auditoria") e só vai cifrado. Peça tirada não grava no
    Fracttal e mantém a situação; corrigir troca o número que vai ao Fracttal (a auditoria guarda o do campo, o corrigido, quem
    corrigiu e o motivo); a recontagem recusa a contagem inteira (nada é gravado e o App pode contar de novo)."""
    if not isinstance(pedido, dict):
        raise Recusa(400, "Pedido sem corpo: mande a ação e o motivo em JSON.")
    acao = A._txt(pedido.get("acao"))
    if acao not in ("tirar", "corrigir", "recontagem"):
        raise Recusa(400, "Ação desconhecida: tirar, corrigir ou recontagem.")
    if quem is None:
        raise Recusa(409, "Não sei quem está revisando: entre com o seu login do Fracttal (a revisão fica no nome de quem a "
                          "faz, e a senha de administrador não é uma pessoa).")
    motivo = A._txt(pedido.get("motivo")) if isinstance(pedido.get("motivo"), str) else ""
    if not motivo:
        raise Recusa(400, "Escreva o motivo: ele fica na auditoria.")
    if len(motivo) > MOTIVO_MAX:
        raise Recusa(400, f"O motivo passa de {MOTIVO_MAX} caracteres: resuma.")
    try:
        F.ler(cfg, forcar=True)         # o estado de agora: dois PCMs revisando a mesma contagem não se atropelam
        todas = leitura.ler(cfg)
    except F.Recusada as ex:
        raise Recusa(503, str(ex)) from None
    c = next((x for x in todas["contagens"] if x["contagem_id"] == contagem_id), None)
    if c is None:
        raise Recusa(404, "Contagem não encontrada: atualize a página.")
    if not c["aprovavel"]:
        raise Recusa(409, f"Esta contagem não se revisa: {c['motivo_nao_aprovavel']}.")
    item, extra = None, {}
    if acao != "recontagem":
        id_item = A._id(pedido.get("id_item")) if isinstance(pedido.get("id_item"), (str, int)) else ""
        if not id_item.isdigit():
            raise Recusa(400, "Diga a peça (o ID do item).")
        revisao, curadoria = leitura.revisao_da(cfg, contagem_id), leitura.curadoria_da(cfg, contagem_id)
        item = next((i for i in contas.itens_do_lote(c["linhas"], {}, curadoria, revisao) if i["id_item"] == id_item), None)
        if item is None:
            raise Recusa(400, "Essa peça não está nesta contagem.")
        if item["tirada"]:
            raise Recusa(409, "A peça já está fora do lote.")
        if acao == "corrigir":
            if item["situacao"] == "curadoria":
                raise Recusa(409, "A peça tem unidades por identificar: decida a curadoria antes de corrigir o número.")
            extra = {"de_qtd": item["contado_campo"], "para_qtd": _valor(pedido.get("valor"))}
    tipo = {"tirar": "peca_tirada", "corrigir": "numero_corrigido", "recontagem": "recontagem_pedida"}[acao]
    try:
        F.acrescentar(cfg, F.ABA_EVENTO, [_evento(c, quem, tipo, item, dados={"motivo": motivo}, **extra)])
    except F.Recusada as ex:
        raise Recusa(503, str(ex)) from None
    except ValueError as ex:        # o livro não aceita a linha (um ID que não cabe na coluna): nada foi gravado
        raise Recusa(400, f"O livro do inventário não aceitou: {ex}") from None
    novo = next((x for x in leitura.contagens(cfg) if x["contagem_id"] == contagem_id), c)
    texto = {"tirar": "Peça tirada do lote.", "corrigir": "Número corrigido.",
             "recontagem": "Recontagem pedida: nada será gravado desta contagem."}[acao]
    return {"ok": True, "mensagem": texto, "estado": novo["estado"]}
