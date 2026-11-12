"""Transferir peça entre almoxarifados do mesmo cliente (12/11/2026, PCM → Almoxarifado → Transferir). Desenho aprovado:
`docs/superpowers/specs/2026-11-12-transferir-entre-almoxarifados-design.md`.

Por quê (o pedido do PCM de 04/11/2026): desde 04/11 toda usina tem almoxarifado no Fracttal, e os novos nasceram vazios; a peça
passou a circular entre usinas do mesmo cliente. O Fracttal só transfere para o almoxarifado onde a peça já está vinculada, e o
campo improvisava com uma saída "Geral" e um ajuste de inventário, que tiram a peça de um almoxarifado sem entrada em nenhum outro.
Esta tela é para a peça GUARDADA em outra usina (mudou de lugar e segue em estoque); a peça INSTALADA é baixa na OS, pelo App.

O caminho (`transferir`, com um clique; o `conferir` antes mostra o que vai acontecer sem gravar):
1. relê os dois almoxarifados no Fracttal e valida de novo (`conferir`);
2. vincula a peça no destino se faltar (`estoque.ligar`, com 0 e 0: só o acordado vai ao Fracttal, a decisão de 26/10/2026);
3. lança a transferência (o corpo capturado na tela do Fracttal e provado em 12/11/2026: vale na hora, o saldo da origem cai e o
   do destino sobe no mesmo pedido) com a nota "<referência do PCM> · Transferência pelo Nexus NX-TR-xxxxxxxx" (sem a
   referência, só a segunda parte): o Fracttal TROCA o `document` pelo folio do destino ("MOV-1"), e a referência que o PCM
   digita só sobrevive na nota. O `document` vai com a referência ou, sem ela, o código (a tela o exige);
4. relê os dois; 5. anota os eventos no livro do inventário.
O destino que exige aprovação da entrada (o `transfer_approval` do almoxarifado no Fracttal) o Nexus NÃO cobre: medido em
12/11/2026, nenhum dos 183 almoxarifados o tem ligado, e a aprovação não teria como ser provada. O conferir e o transferir
recusam antes de qualquer gravação (`EXIGE_APROVACAO`), e o PCM faz esse caso pela tela do Fracttal.

As regras, com o caso que as criou:
- **Os almoxarifados são os do Fracttal, lidos na hora** (`estoque.almoxarifados`), e não os da varredura do App: o livro Saldo
  só tem os almoxarifados com peça, e o destino típico é o novo, vazio (medido em 12/11/2026).
- **Mesmo cliente**, conhecido dos dois lados: o 1º nó do caminho do local do almoxarifado no Fracttal (`cliente_do_caminho`),
  sem acento e sem caixa. Outro cliente é empréstimo e passa pela coordenação.
- **A peça com controle de série ou de lote** (o `is_serial_control` ou o `is_lot_control` da linha do saldo) recusa antes de
  gravar: a tela do Fracttal pede os números de série ou o lote, e isso não foi provado.
- **A quantidade**: maior que zero, no máximo o saldo lido NA HORA, inteira na unidade inteira e com até duas casas em METRO e
  MASSA (`regua.decimal`).
- **Nenhum dos dois em sessão de ajuste** (o modo fora do 0) nem com a vez presa por uma gravação de contagem, nem **inativo** no
  Fracttal (o `active` falso: há almoxarifado assim). O modo, o ativo e a aprovação saem de uma leitura só da lista dos
  almoxarifados por lado (`estoque.almoxarifado`).
- **A resposta incerta não se repete** (o C2 das requisições): a rede (ou o Fracttal sem o id) no passo 3 faz o Nexus procurar o
  código no histórico da origem (`achar_transferencia`). Achou: segue da releitura. Não achou: a trava (o evento
  `transferencia_travada`, e a memória do processo) e a tela diz "pode ter feito: confira no Fracttal". A próxima tentativa da
  mesma peça na mesma origem procura o código de novo ANTES de mandar outra: achou, registra como feita e não manda; não achou,
  libera e segue.
- **A releitura que não bate** (o saldo não mudou como devia) é o evento `transferencia_falha`, e a tela diz o que leu. A entrada
  só vai ao livro quando o destino relido mostra a peça: o livro nunca diz que o Fracttal tem o que não tem.
- **Uma de cada vez** por peça em cada um dos dois almoxarifados (a trava em memória, `_tomar`; o Nexus roda num processo
  só): a outra transferência da mesma peça que toque a origem ou o destino espera, senão a releitura da primeira não
  bateria. E **só no servidor**
  (`requisicoes.so_no_servidor`, o mesmo portão do aceite das requisições).
- **Nome de gente** só passa pela memória e pela tela do PCM; o livro guarda a pessoa como `pessoa_hmac`/`pessoa_id`, e a
  referência do PCM e o outro almoxarifado só cifrados (`dados`).
"""
from __future__ import annotations

import logging
import math
import secrets
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from ...dados import almoxarifado as A
from ...dados import fato_inventario as F
from ...dados import fatos as D
from . import estoque as E
from . import regua
from .erros import Conflito
from .requisicoes import Falhou, _certo, _motivo, _quando_txt, _status, so_no_servidor  # noqa: F401  (Falhou: a ponte o usa)

PREFIXO = "NX-TR-"
TELA = "/t/pcm/pecas/transferir"
TIPOS = ("transferencia_vinculo", "transferencia_saida", "transferencia_entrada", "transferencia_falha",
         "transferencia_travada")
REFERENCIA_MAX = 60
HISTORICO_N = 30
FOLGA_MIN = 10              # a busca do código começa 10 min antes da tentativa (o relógio do Fracttal não é o nosso)
BUSCA_DIAS = 7              # a trava de antes que se confere na próxima tentativa: até 7 dias
SEM_RESPONSAVEL = ("Não achei você como responsável no Fracttal: pelo seu e-mail, no pessoal (o e-mail da conta de login, ou "
                   "o e-mail de uma pessoa só), e então na lista de responsáveis. A transferência precisa de um responsável, e "
                   "o Nexus não grava sem dono. Peça ao administrador do Fracttal para conferir o seu cadastro de pessoal. Nada "
                   "foi enviado.")
SERIE_OU_LOTE = "Esta peça tem controle de série ou de lote no Fracttal: transfira pela tela do Fracttal."
EXIGE_APROVACAO = ("O almoxarifado de destino exige aprovação de transferência no Fracttal, e o Transferir do Nexus ainda não "
                   "cobre esse caso: faça pela tela do Fracttal.")
EM_CURSO = ("Outra pessoa está transferindo esta peça entre estes almoxarifados agora: espere e recarregue a página. Nada foi "
            "enviado.")
SEM_LIVRO = ("Não consegui ler o livro do inventário agora: sem ele não sei se uma transferência desta peça ficou sem resposta. "
             "Nada foi enviado; tente de novo em instantes.")
_EPS = 1e-6
log = logging.getLogger(__name__)


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _g(n) -> str:
    """O número na frase da tela, em pt-BR ("1,5")."""
    return "?" if n is None else f"{n:g}".replace(".", ",")


# ── o código do Nexus e o lote ──────────────────────────────────────────────────────────────────────────────────────────
def novo_codigo() -> str:
    """`NX-TR-` + 8 hexadecimais. O número é menor que 2³¹: o mesmo código vai inteiro no `lote` do livro (uma coluna de
    inteiro, a do lote da gravação), e todas as linhas de uma transferência levam o mesmo."""
    return f"{PREFIXO}{secrets.randbelow(2 ** 31):08x}"


def lote_do_codigo(codigo: str) -> int:
    return int(str(codigo)[len(PREFIXO):], 16)


def codigo_do_lote(lote) -> str:
    return f"{PREFIXO}{int(lote):08x}"


# ── os almoxarifados (a lista do Fracttal, lida na hora) ────────────────────────────────────────────────────────────────
def cliente_do_caminho(local) -> str:
    """O cliente do almoxarifado: o 1º nó do CAMINHO do local no Fracttal (o `location_description`, "// Cliente Alfa/ Cliente
    Alfa - Usina Um - PA/ "): divide por "/", tira os espaços e fica com o primeiro pedaço não vazio. Medido em 12/11/2026: 181
    almoxarifados com dois nós, 1 com um nó só (o de teste: o cliente é o próprio nó) e 1 sem nó (o desativado: vazio, cliente
    desconhecido, e a transferência recusa). Não é o `almox_usinas.cliente_do_local`, que corta por " - " o nome da usina."""
    return next((p.strip() for p in str(local or "").split("/") if p.strip()), "")


def _mesmo(a: str, b: str) -> bool:
    """O mesmo cliente, sem acento e sem caixa."""
    from ..almox_usinas import _norm
    return bool(a) and bool(b) and _norm(a) == _norm(b)


def almoxarifados(lista: list[dict], usinas: dict, teste: set) -> dict:
    """{id: {"id", "nome", "codigo", "local", "cliente", "ativo", "modo", "exige_aprovacao", "usina_id", "teste"}}: a lista do
    Fracttal (`estoque.almoxarifados`) com o cliente pelo caminho do local (`cliente_do_caminho`). `usinas`: {id: usina_id} pela
    de-para do Almoxarifado (só para o livro). Os de teste ficam, marcados: a prova no Fracttal de verdade é neles."""
    out = {}
    for a in lista:
        aid = A._id(a.get("id"))
        if not aid.isdigit() or aid in out:
            continue
        out[aid] = {**a, "id": aid, "nome": A._txt(a.get("nome")) or f"Almoxarifado {aid}",
                    "cliente": cliente_do_caminho(a.get("local")), "usina_id": usinas.get(aid), "teste": aid in teste}
    return out


def nomes_do_app() -> dict:
    """{"itens": {id: {codigo, nome}}, "almox": {id: nome}}: o catálogo do App (o nome da peça) e os nomes dos almoxarifados da
    varredura, pela cópia de 5 min da Auditoria. Só enfeitam: sem eles, o código e o ID."""
    from .revisao import _nomes_para_auditoria
    return _nomes_para_auditoria()


def contexto(cfg, estoque) -> dict:
    """O que as listas, o conferir e o transferir precisam: os almoxarifados lidos AGORA no Fracttal (`estoque.almoxarifados`,
    com o login de quem está na ponte; um pedido só para os dois lados: o modo, o ativo e a aprovação de cada um saem dele), a
    usina de cada um pela de-para do Almoxarifado (a cópia de 5 min) e o nome das peças pelo catálogo do App."""
    from .. import almoxarifado
    try:
        d = almoxarifado.montar().dados or {}
    except Exception:       # noqa: BLE001 — a usina só completa o livro
        d = {}
    usinas = {}
    for l in d.get("linhas", []):
        if l.get("usina_id") and A._id(l.get("id_almox")) not in usinas:
            usinas[A._id(l.get("id_almox"))] = int(l["usina_id"])
    teste = set(A.ids_de_teste(cfg))
    return {"almoxes": almoxarifados(estoque.almoxarifados(), usinas, teste), "teste": teste,
            "itens": nomes_do_app().get("itens", {})}


def opcoes(ctx: dict) -> list[dict]:
    """Os almoxarifados para as listas da tela: só os ativos, em ordem de cliente e nome (o de cliente desconhecido por
    último, e a tela não o deixa escolher)."""
    from ..almox_usinas import _norm
    return sorted((a for a in ctx["almoxes"].values() if a["ativo"]),
                  key=lambda a: (not a["cliente"], _norm(a["cliente"]), _norm(a["nome"])))


def pecas_com_saldo(estoque, ctx: dict, origem) -> list[dict]:
    """As peças com saldo na origem, lidas no Fracttal NA HORA (`estoque.ler`), com o nome pelo catálogo do App."""
    o = _id_almox(origem)
    out = []
    for item, p in estoque.ler(o).items():
        if p.get("saldo") is None or p["saldo"] <= _EPS:
            continue
        nome = (ctx.get("itens") or {}).get(item, {})
        out.append({"id": item, "codigo": p.get("codigo") or nome.get("codigo", "") or item, "nome": nome.get("nome", ""),
                    "unidade": (p.get("unidade") or "").lower(), "saldo": p["saldo"], "decimal": regua.decimal(p.get("unidade"))})
    return sorted(out, key=lambda x: (x["codigo"], x["id"]))


# ── as validações ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _id_almox(v) -> str:
    t = A._id(v)
    if not t.isdigit():
        raise ValueError("Escolha o almoxarifado (origem e destino): recarregue a página se a lista sumiu. Nada foi enviado.")
    return t


def _id_item(v) -> str:
    t = A._id(v)
    if not t.isdigit():
        raise ValueError("Escolha a peça. Nada foi enviado.")
    return t


def _referencia(v) -> str:
    t = " ".join(str(v or "").split())
    if len(t) > REFERENCIA_MAX:
        raise ValueError(f"A OS ou referência passa de {REFERENCIA_MAX} letras. Nada foi enviado.")
    return t


def quantidade(texto, unidade: str, saldo: float) -> float:
    """A quantidade pedida: número maior que zero, no máximo o `saldo` lido na hora, inteira na unidade inteira e com até duas
    casas em METRO e MASSA. ValueError com a frase da recusa."""
    t = str(texto if texto is not None else "").strip().replace(",", ".")
    try:
        n = float(t)
    except ValueError:
        raise ValueError("Diga a quantidade em número. Nada foi enviado.") from None
    if not math.isfinite(n) or n <= 0:
        raise ValueError("A quantidade precisa ser maior que zero. Nada foi enviado.")
    if regua.decimal(unidade):
        if abs(round(n, 2) - n) > _EPS:
            raise ValueError(f"Em {unidade.lower()} a quantidade vai com até duas casas decimais. Nada foi enviado.")
        n = round(n, 2)
    elif abs(round(n) - n) > _EPS:
        raise ValueError(f"A peça é contada em {(unidade or 'unidade').lower()}: a quantidade é inteira. Nada foi enviado.")
    else:
        n = float(round(n))
    if n > saldo + _EPS:
        raise ValueError(f"A origem tem {_g(saldo)} desta peça agora: a quantidade não pode passar disso. Nada foi enviado.")
    return n


def _almox(ctx: dict, aid: str, papel: str) -> dict:
    a = ctx["almoxes"].get(aid)
    if a is None:
        raise Conflito(f"O almoxarifado de {papel} ({aid}) não está na lista do Fracttal: recarregue a página. Nada foi "
                       "enviado.")
    return a


def _livre(cfg, a: dict, papel: str) -> dict:
    """O almoxarifado (a linha da lista do Fracttal lida neste pedido), se ele pode entrar na transferência: ativo, no modo 0
    e sem a vez presa por uma gravação de contagem. `Conflito` com o porquê."""
    from . import gravacao
    presa = gravacao.vez_presa(cfg, a["id"])
    if presa:
        raise Conflito(f"Nada foi enviado: {a['nome']}: {presa.rstrip('.')}.")
    x = a
    if not x["ativo"]:
        raise Conflito(f"{a['nome']} está inativo no Fracttal: não entra como {papel}. Nada foi enviado.")
    if x["modo"] is None:
        raise Conflito(f"Nada foi enviado: {a['nome']} veio do Fracttal sem o modo, e sem ele não sei se está em ajuste.")
    if x["modo"] != 0:
        raise Conflito(f"Nada foi enviado: {a['nome']} está no modo {x['modo']} no Fracttal (ajuste ou inventário aberto), e a "
                       "transferência não passa. Tente depois de fechado.")
    return x


def conferir(cfg, estoque, ctx: dict, origem, destino, id_item, qtd, referencia="") -> dict:
    """O que vai acontecer, sem gravar: relê os dois almoxarifados no Fracttal e valida (a origem diferente do destino, o mesmo
    cliente conhecido dos dois lados, a peça com saldo na origem, a quantidade, nenhum dos dois inativo ou em ajuste, e o destino
    sem a aprovação de transferência). `{"origem": {id, nome, antes, depois}, "destino": {...}, "peca": {id, codigo, nome,
    unidade}, "qtd", "vincular", "referencia", "cliente"}`. ValueError (400) o pedido sem sentido; `Conflito` (409) o que o estado de agora não deixa."""
    o, d, item = _id_almox(origem), _id_almox(destino), _id_item(id_item)
    ref = _referencia(referencia)
    if o == d:
        raise ValueError("A origem e o destino são o mesmo almoxarifado: escolha outro destino. Nada foi enviado.")
    ao, ad = _almox(ctx, o, "origem"), _almox(ctx, d, "destino")
    for a in (ao, ad):
        if not a["cliente"]:
            raise Conflito(f"Não sei o cliente de {a['nome']} (o almoxarifado não tem o local no Fracttal): a transferência "
                           "pede o mesmo cliente dos dois lados. Nada foi enviado.")
    if not _mesmo(ao["cliente"], ad["cliente"]):
        raise Conflito(f"{ad['nome']} é de outro cliente ({ad['cliente']}; a origem é de {ao['cliente']}): entre clientes "
                       "diferentes é empréstimo e passa pela coordenação. Nada foi enviado.")
    lido_o = estoque.ler(o)
    p = lido_o.get(item)
    if p is None or p.get("saldo") is None or p["saldo"] <= _EPS:
        raise Conflito(f"A peça não tem saldo em {ao['nome']} agora (lido no Fracttal): escolha outra. Nada foi enviado.")
    if estoque.serie_ou_lote(o, item):
        raise Conflito(SERIE_OU_LOTE)
    n = quantidade(qtd, p.get("unidade") or "", p["saldo"])
    _livre(cfg, ao, "origem")
    if _livre(cfg, ad, "destino")["exige_aprovacao"]:
        raise Conflito(EXIGE_APROVACAO)
    lido_d = estoque.ler(d)
    vincular = item not in lido_d
    antes_d = 0.0 if vincular else lido_d[item].get("saldo")
    nome = (ctx.get("itens") or {}).get(item, {})
    return {"origem": {"id": o, "nome": ao["nome"], "antes": p["saldo"], "depois": p["saldo"] - n},
            "destino": {"id": d, "nome": ad["nome"], "antes": antes_d, "depois": None if antes_d is None else antes_d + n},
            "peca": {"id": item, "codigo": p.get("codigo") or nome.get("codigo", "") or item, "nome": nome.get("nome", ""),
                     "unidade": (p.get("unidade") or "").lower()},
            "qtd": n, "vincular": vincular, "referencia": ref, "cliente": ao["cliente"]}


# ── o que o livro diz: as travas (a resposta que não veio) e o histórico ────────────────────────────────────────────────
_INCERTAS: dict[tuple, dict] = {}       # (origem, peça) -> a trava, para o livro que não gravou (a memória do processo)
_TRAVA_INCERTAS = threading.Lock()


def _travas(eventos: list[dict]) -> dict[tuple, dict]:
    """{(origem, peça): {"codigo", "quando", "qtd"}}: a última transferência de cada peça em cada origem cuja resposta não veio
    e que ninguém resolveu. Pelas colunas em claro (o tipo, o almoxarifado, a peça, o lote), nunca pelo `dados`: a trava vale
    sem a chave do cadastro (a lição da re-revisão das requisições, N3). Na ordem da gravação: o evento seguinte da mesma peça
    na mesma origem (a saída ou a falha de uma tentativa nova) a resolve."""
    out: dict[tuple, dict] = {}
    for e in eventos:
        t = A._txt(e.get("tipo"))
        if t not in ("transferencia_saida", "transferencia_falha", "transferencia_travada"):
            continue
        chave = (A._id(e.get("id_almoxarifado")), A._id(e.get("id_item")))
        if t == "transferencia_travada" and D._id(e.get("lote")):
            out[chave] = {"codigo": codigo_do_lote(D._id(e.get("lote"))), "quando": A._txt(e.get("quando")),
                          "qtd": A.numero(e.get("contado_qtd"))}
        else:
            out.pop(chave, None)
    return out


def _trava_de(cfg, chave: tuple) -> dict | None:
    with _TRAVA_INCERTAS:
        if chave in _INCERTAS:
            return dict(_INCERTAS[chave])
    try:
        eventos = F.ler(cfg)[F.ABA_EVENTO]
    except F.Recusada as ex:
        raise Conflito(SEM_LIVRO) from ex
    return _travas([e for e in eventos if A._txt(e.get("tipo")).startswith("transferencia_")]).get(chave)


def historico(cfg, nomes: dict | None = None, pessoas=None, n: int = HISTORICO_N) -> dict:
    """As últimas transferências (`{"linhas", "erro"}`), do livro do inventário, da mais nova à mais velha: uma por código (o
    `lote`), com quando, quem (o `pessoa_id`; o nome, só por `pessoas`), a peça, de onde para onde, a quantidade, os saldos
    antes e depois de cada lado, se o vínculo foi criado e a situação. Não fala com o Fracttal: o nome de cada almoxarifado vem
    do `dados` cifrado do evento (o da hora da transferência) e, sem ele, da varredura (`nomes`, o `nomes_do_app`); o da peça,
    do catálogo do App. O livro que não se lê vira o erro, nunca "nenhuma"."""
    try:
        eventos = F.ler(cfg)[F.ABA_EVENTO]
    except F.Recusada as ex:
        return {"linhas": [], "erro": str(ex)}
    grupos: dict[str, dict] = {}
    for i, e in enumerate(eventos):
        t = A._txt(e.get("tipo"))
        if not t.startswith("transferencia_") or not D._id(e.get("lote")):
            continue
        cod = codigo_do_lote(D._id(e.get("lote")))
        g = grupos.setdefault(cod, {"codigo": cod, "quando": "", "i": i, "tipos": set(), "origem": "", "destino": "",
                                    "id_item": A._id(e.get("id_item")), "peca": A._txt(e.get("codigo")), "qtd": None,
                                    "o_antes": None, "o_depois": None, "d_antes": None, "d_depois": None, "pessoa_id": None,
                                    "motivo": "", "_dados": None})
        g["tipos"].add(t)
        g["quando"] = max(g["quando"], A._txt(e.get("quando")))
        g["i"] = max(g["i"], i)
        g["peca"] = g["peca"] or A._txt(e.get("codigo"))
        g["qtd"] = g["qtd"] if g["qtd"] is not None else A.numero(e.get("contado_qtd"))
        g["pessoa_id"] = g["pessoa_id"] or D._id(e.get("pessoa_id"))
        almox = A._id(e.get("id_almoxarifado"))
        if t in ("transferencia_saida", "transferencia_falha", "transferencia_travada"):
            g["origem"] = g["origem"] or almox
        if t in ("transferencia_entrada", "transferencia_vinculo"):
            g["destino"] = almox
        if t == "transferencia_saida":
            g["o_antes"], g["o_depois"] = A.numero(e.get("de_qtd")), A.numero(e.get("para_qtd"))
        if t == "transferencia_entrada":
            g["d_antes"], g["d_depois"] = A.numero(e.get("de_qtd")), A.numero(e.get("para_qtd"))
        if t in ("transferencia_falha", "transferencia_travada") or g["_dados"] is None:
            try:
                dados = F.decifrar(cfg, F.ABA_EVENTO, e)
            except Exception:      # noqa: BLE001 — sem a chave do cadastro, o que é cifrado não se lê; o resto da linha vale
                dados = {}
            if t in ("transferencia_falha", "transferencia_travada"):
                g["motivo"] = A._txt(dados.get("motivo")) or "o motivo não se lê agora"
            g["_dados"] = g["_dados"] or dados
    nomes = nomes or {}
    almox_nomes, itens = nomes.get("almox") or {}, nomes.get("itens") or {}
    linhas = []
    for g in sorted(grupos.values(), key=lambda g: (g["quando"], g["i"]), reverse=True)[:n]:
        dados = g.pop("_dados") or {}
        g["destino"] = g["destino"] or A._id(dados.get("destino"))
        ts = g.pop("tipos")
        g["vinculo"] = "transferencia_vinculo" in ts
        if "transferencia_saida" in ts and "transferencia_entrada" in ts and "transferencia_falha" not in ts:
            g["situacao"], g["tom"] = "Feita", "ok"
        elif "transferencia_saida" in ts and "transferencia_travada" in ts:
            g["situacao"], g["tom"] = "Feita, achada depois no histórico do Fracttal: confira os saldos", "alerta"
        elif "transferencia_saida" in ts:
            g["situacao"], g["tom"] = f"Lançada, sem confirmar: {g['motivo']}" if g["motivo"] else "Lançada, sem confirmar", "alerta"
        elif "transferencia_travada" in ts:
            g["situacao"], g["tom"] = "Pode ter feito: confira no Fracttal", "alerta"
        else:
            g["situacao"], g["tom"] = f"Não feita: {g['motivo']}" if g["motivo"] else "Não feita", "critico"
        g["quando_txt"] = _quando_txt(g["quando"])
        g["origem_nome"] = (A._txt(dados.get("origem_nome")) or almox_nomes.get(g["origem"])
                            or (f"Almoxarifado {g['origem']}" if g["origem"] else "origem não lida"))
        g["destino_nome"] = (A._txt(dados.get("destino_nome")) or almox_nomes.get(g["destino"])
                             or (f"Almoxarifado {g['destino']}" if g["destino"] else "destino não lido"))
        g["peca_nome"] = (itens.get(g["id_item"]) or {}).get("nome", "")
        g["quem"] = (pessoas or {}).get(g["pessoa_id"], "") if g["pessoa_id"] else ""
        linhas.append(g)
    return {"linhas": linhas, "erro": ""}


# ── transferir ──────────────────────────────────────────────────────────────────────────────────────────────────────────
_EM_CURSO: set = set()
_TRAVA_CURSO = threading.Lock()


@contextmanager
def _tomar(origem: str, destino: str, item: str):
    """Uma transferência de cada vez por PEÇA em cada um dos dois almoxarifados, no processo: a segunda que toque a mesma peça
    na origem ou no destino (o mesmo par, a mesma origem para outro destino, a volta), enquanto a primeira anda, leva 409. A
    vez era só do par (origem, destino, peça), e a releitura da primeira, que confere o saldo dos dois lados contra o de antes,
    diria "a releitura não bate" de uma transferência que deu certo (a revisão de 12/11/2026)."""
    chaves = {(origem, item), (destino, item)}
    with _TRAVA_CURSO:
        if chaves & _EM_CURSO:
            raise Conflito(EM_CURSO)
        _EM_CURSO.update(chaves)
    try:
        yield
    finally:
        with _TRAVA_CURSO:
            _EM_CURSO.difference_update(chaves)


def limpar() -> None:
    with _TRAVA_INCERTAS:
        _INCERTAS.clear()
    with _TRAVA_CURSO:
        _EM_CURSO.clear()


def _cols(ctx: dict, quem_: dict, aid: str) -> dict:
    """O almoxarifado com a usina pela de-para (e a linhagem) e a pessoa como código: as colunas comuns dos eventos."""
    uid = (ctx["almoxes"].get(aid) or {}).get("usina_id")
    return {"id_almoxarifado": aid, "usina_id": uid, "usina_ligada_por": F.USINA_LIGADA_POR[0] if uid else None,
            **(quem_ or {})}


def nota_do_movimento(referencia: str, codigo: str) -> str:
    """A `description` do movimento: "<referência do PCM> · Transferência pelo Nexus NX-TR-xxxxxxxx", ou só a segunda parte. É
    o único lugar do movimento onde a referência sobrevive (o `document` o Fracttal troca) e onde o código se procura."""
    return f"{referencia} · Transferência pelo Nexus {codigo}" if referencia else f"Transferência pelo Nexus {codigo}"


def _digitos(folio) -> str | None:
    """O número do folio ("MOV-21" é o 21) para o `movimento_fracttal`, que só aceita dígitos (a regra da coluna no livro). O
    folio inteiro, com o id do movimento, vai no `dados`. Sem dígito, nada."""
    t = "".join(ch for ch in str(folio or "") if ch.isdigit())
    return t.lstrip("0") or ("0" if t else None)


def _anotar(cfg, eventos: list[dict]) -> str:
    """Grava os eventos de uma vez; o livro que não grava agora não esconde o que o Fracttal fez: volta o texto do aviso."""
    try:
        F.acrescentar(cfg, F.ABA_EVENTO, eventos)
        return ""
    except (F.Recusada, ValueError) as ex:
        log.warning("transferência: os eventos não foram ao livro (%s)", type(ex).__name__)
        return f" Não consegui anotar no livro do Nexus ({ex})."


def transferir(cfg, estoque, ctx: dict, origem, destino, id_item, qtd, referencia="", *, quem_: dict,
               responsavel: dict | None, agora: datetime | None = None) -> dict:
    """Transfere uma peça (os passos do módulo), uma de cada vez por peça em cada um dos dois almoxarifados. `{"ok", "confirmada",
    "mensagem", "codigo"}`. Recusa antes de qualquer gravação: `so_no_servidor`, as validações do `conferir` (relidas; o
    destino que exige aprovação inclusive), a transferência de antes da mesma peça que ficou sem resposta e se acha agora
    (registrada como feita, sem mandar outra) e a sem responsável. `Falhou` (com o status da ponte) o passo que o Fracttal não
    fez ou cuja resposta não veio."""
    so_no_servidor(cfg)
    o, d, item = _id_almox(origem), _id_almox(destino), _id_item(id_item)
    with _tomar(o, d, item):
        return _transferir(cfg, estoque, ctx, o, d, item, qtd, referencia, quem_, responsavel, agora)


def _transferir(cfg, estoque, ctx, o, d, item, qtd, referencia, quem_, responsavel, agora) -> dict:
    inicio = agora or _agora()
    chave = (o, item)
    # a transferência de antes que ficou sem resposta: procura o código ANTES de mandar outra (o C2 das requisições)
    trava = _trava_de(cfg, chave)
    if trava:
        try:
            desde = E.instante(trava["quando"]) - timedelta(minutes=FOLGA_MIN)
        except ValueError:
            desde = inicio - timedelta(days=BUSCA_DIAS)
        try:
            achada = estoque.achar_transferencia(o, trava["codigo"], desde.isoformat())
        except Exception as ex:      # noqa: BLE001 — sem a busca, não se sabe: nada vai
            raise Conflito(f"A transferência {trava['codigo']} desta peça ficou sem resposta, e não consegui conferir no "
                           f"Fracttal agora ({_motivo(ex)}): nada foi enviado. Tente de novo em instantes.") from ex
        if achada:
            base = _cols(ctx, quem_, o)
            aviso = _anotar(cfg, [{"tipo": "transferencia_saida", **base, "id_item": item, "contado_qtd": trava["qtd"],
                                   "movimento_fracttal": _digitos(achada.get("folio")),
                                   "lote": lote_do_codigo(trava["codigo"]),
                                   "dados": {"codigo": trava["codigo"], "achada_depois": True, "confirmada": False}}])
            with _TRAVA_INCERTAS:
                _INCERTAS.pop(chave, None)
            return {"ok": True, "confirmada": False, "codigo": trava["codigo"],
                    "mensagem": (f"A transferência {trava['codigo']}, que ficou sem resposta em {_quando_txt(trava['quando'])}, "
                                 "foi feita no Fracttal (achada no histórico da origem): o Nexus não mandou outra. Confira os "
                                 "saldos e transfira de novo só se ainda faltar." + aviso)}
        # não achou: libera e segue (a saída ou a falha desta tentativa resolve a trava no livro)
        with _TRAVA_INCERTAS:
            _INCERTAS.pop(chave, None)
    plano = conferir(cfg, estoque, ctx, o, d, item, qtd, referencia)
    if not responsavel:
        raise Conflito(SEM_RESPONSAVEL)
    n, ref = plano["qtd"], plano["referencia"]
    codigo = novo_codigo()
    lote = lote_do_codigo(codigo)
    peca = plano["peca"]
    base_o, base_d = _cols(ctx, quem_, o), _cols(ctx, quem_, d)
    comum = {"id_item": item, "codigo": (peca["codigo"] or "")[:60] or None, "lote": lote}
    dados = {"codigo": codigo, "origem": o, "destino": d, "origem_nome": plano["origem"]["nome"],
             "destino_nome": plano["destino"]["nome"], **({"referencia": ref} if ref else {})}
    eventos: list[dict] = []

    def falha(motivo: str, passo: str, travada: bool = False) -> None:
        eventos.append({"tipo": "transferencia_travada" if travada else "transferencia_falha", **base_o, **comum,
                        "contado_qtd": n, "dados": {**dados, "motivo": motivo, "passo": passo}})

    # 2. o vínculo no destino, com 0 e 0
    if plano["vincular"]:
        try:
            estoque.ligar(d, item)
        except Exception as ex:      # noqa: BLE001 — o "não" do Fracttal, a pausa, o login ou a resposta que não veio
            if not isinstance(ex, (E.Limite, E.SemLogin)):
                falha(f"o vínculo no destino não foi criado ({_motivo(ex)})", "vincular")
                _anotar(cfg, eventos)
            raise Falhou((f"Nada foi transferido: o Fracttal não vinculou a peça a {plano['destino']['nome']} ({_motivo(ex)})."
                          if _certo(ex) else
                          f"Nada foi transferido: a resposta do vínculo da peça a {plano['destino']['nome']} não veio "
                          f"({_motivo(ex)}), e ele pode ter sido criado. Tente de novo: o Nexus relê o destino antes."),
                         _status(ex), ex) from ex
        eventos.append({"tipo": "transferencia_vinculo", **base_d, **comum, "de_qtd": None, "para_qtd": 0,
                        "dados": dict(dados)})
    vinculo_txt = f" A peça ficou vinculada a {plano['destino']['nome']}, com mínimo e máximo 0." if plano["vincular"] else ""
    # 3. a transferência, com o código do Nexus na nota
    nota = nota_do_movimento(ref, codigo)
    try:
        mov = estoque.transferir(o, d, plano["destino"]["nome"], item, n, responsavel, ref or codigo, nota, agora)
    except Exception as ex:          # noqa: BLE001 — fora o "não", a pausa e o login, a transferência pode ter sido feita
        log.warning("transferência: %s parou ao transferir (%s)", codigo, type(ex).__name__)
        if _certo(ex):
            if not isinstance(ex, (E.Limite, E.SemLogin)):
                falha(f"o Fracttal não transferiu ({_motivo(ex)})", "transferir")
            aviso = _anotar(cfg, eventos) if eventos else ""
            raise Falhou(f"Nada foi transferido: o Fracttal não aceitou ({_motivo(ex)}).{vinculo_txt}{aviso}", _status(ex),
                         ex) from ex
        try:
            achada = estoque.achar_transferencia(o, codigo, (inicio - timedelta(minutes=FOLGA_MIN)).isoformat())
        except Exception:            # noqa: BLE001 — a busca que falha não diz nada: trava
            achada = None
        if not achada:
            motivo = f"a resposta da transferência não veio ({_motivo(ex)}): ela pode ter sido feita"
            falha(motivo, "transferir", travada=True)
            with _TRAVA_INCERTAS:
                _INCERTAS[(o, item)] = {"codigo": codigo, "quando": inicio.isoformat(), "qtd": n}
            aviso = _anotar(cfg, eventos)
            raise Falhou(f"A resposta do Fracttal não veio ({_motivo(ex)}): a transferência {codigo} pode ter sido feita. "
                         "Confira no Fracttal; a próxima tentativa desta peça nesta origem procura o código antes de mandar "
                         f"outra.{vinculo_txt}{aviso}", 502, ex) from ex
        mov = {"id": achada["id"], "folio_origem": achada.get("folio") or "", "folio_destino": achada.get("documento") or ""}
    # 4. reler os dois (cada um à parte: a releitura que falha não impede o livro de gravar o que o Fracttal fez)
    lidos = {}
    for aid in (o, d):
        try:
            lidos[aid] = (estoque.ler(aid).get(item) or {}).get("saldo")
        except Exception:            # noqa: BLE001
            lidos[aid] = None
    antes_o, antes_d = plano["origem"]["antes"], plano["destino"]["antes"]
    esperado_o, esperado_d = antes_o - n, (antes_d or 0.0) + n
    ok_o = lidos[o] is not None and abs(lidos[o] - esperado_o) < _EPS
    ok_d = lidos[d] is not None and abs(lidos[d] - esperado_d) < _EPS
    folios = {"id_movimento": A._id(mov.get("id")), "folio_origem": mov.get("folio_origem") or "",
              "folio_destino": mov.get("folio_destino") or ""}
    # 5. o livro: a saída sempre (o Fracttal aceitou), a entrada só com o destino relido mostrando a peça
    eventos.append({"tipo": "transferencia_saida", **base_o, **comum, "de_qtd": antes_o, "para_qtd": lidos[o],
                    "contado_qtd": n, "movimento_fracttal": _digitos(folios["folio_origem"]),
                    "dados": {**dados, **folios, "confirmada": ok_o}})
    if ok_d:
        eventos.append({"tipo": "transferencia_entrada", **base_d, **comum, "de_qtd": antes_d, "para_qtd": lidos[d],
                        "contado_qtd": n, "movimento_fracttal": _digitos(folios["folio_destino"]),
                        "dados": {**dados, **folios, "confirmada": True}})
    confirmada = ok_o and ok_d
    un = f" {peca['unidade']}" if peca["unidade"] and peca["unidade"] != "unidade" else ""
    if confirmada:
        mensagem = (f"Transferência {codigo} feita: {_g(n)}{un} de {peca['codigo']} de {plano['origem']['nome']} para "
                    f"{plano['destino']['nome']}. Relido no Fracttal: a origem ficou com {_g(lidos[o])} e o destino com "
                    f"{_g(lidos[d])}.{vinculo_txt}")
    else:
        partes = []
        if not ok_o:
            partes.append(f"a origem tem {_g(lidos[o])} (esperado {_g(esperado_o)})")
        if not ok_d:
            partes.append(f"o destino tem {_g(lidos[d])} (esperado {_g(esperado_d)})")
        motivo = "a releitura não bate: " + " e ".join(partes)
        falha(motivo, "releitura")
        mensagem = (f"A transferência {codigo} foi lançada no Fracttal, mas {motivo}."
                    + (" A peça pode ter saído da origem sem entrar no destino: confira na tela do Fracttal."
                       if not ok_d else " Confira na tela do Fracttal.") + vinculo_txt)
    mensagem += _anotar(cfg, eventos)
    return {"ok": True, "confirmada": confirmada, "mensagem": mensagem, "codigo": codigo}


# ── a página (em /t/pcm: não fala com o Fracttal) ───────────────────────────────────────────────────────────────────────
def registrar(bp) -> None:
    from flask import current_app, render_template, session

    @bp.route("/pecas/transferir", endpoint="transferir")
    def transferir_tela():
        """A aba Transferir do Almoxarifado: a casca do formulário (as listas, o Conferir e o Transferir vêm da ponte do login
        do Fracttal, por `fetch`) e as Últimas transferências, do livro. Quem entrou pela senha de administrador não é uma
        pessoa e não tem o login: a página diz isso e nem pede. O nome de quem transferiu, só para o PCM (`pode`)."""
        from .. import telas
        from . import quem
        from .revisao import _nomes_das_pessoas
        cfg = current_app.config
        pode = telas.pode_programar()
        h = historico(cfg, nomes_do_app())
        if pode and h["linhas"]:
            pessoas = _nomes_das_pessoas({x["pessoa_id"] for x in h["linhas"]} - {None})
            for x in h["linhas"]:
                if x["pessoa_id"]:
                    x["quem"] = pessoas.get(x["pessoa_id"]) or f"ficha {x['pessoa_id']} do cadastro"
        return render_template("pcm/transferir.html", pode=pode, com_pessoa=bool(quem.do_pedido().get("email")),
                               historico=h, aviso=session.pop("pcm_transferir_aviso", None))
