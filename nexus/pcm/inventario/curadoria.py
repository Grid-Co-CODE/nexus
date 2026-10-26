"""A curadoria do inventário do almoxarifado (PCM → Almoxarifado → Curadoria; 26/10/2026).

Levi, 26/10/2026: a peça que o técnico acha fora do catálogo vira pendência: o campo descreve, fotografa e conta, e quem
decide é o PCM. Desenho: `docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md`, seção 4.5. Duas fontes de
pendência, nas contagens que ainda não foram gravadas:

- `fora_do_catalogo` (a descrição, a foto e a quantidade): o PCM **cadastra** a peça no Fracttal (código `SP-<sigla>-NNN`, o
  próximo livre da sigla, nome e unidade), diz que **é a peça X** (do catálogo) ou **descarta** (com o motivo);
- `identificar` (o genérico com saldo, um por específico): o PCM **confirma** o específico que o técnico escolheu (ou outro).

A decisão vai ao livro do inventário (`fato_curadoria_inventario`, mais o evento `curadoria` da auditoria) e a quantidade
entra no lote pela `contas.contado_efetivo`: "é a peça X" e "cadastrar" somam as achadas ao contado da peça NESSA contagem (o
total substitui o saldo); o genérico confirmado tira as unidades do genérico e as põe no específico. A peça cadastrada é ligada
ao almoxarifado e ajustada na gravação da contagem, não aqui. `decisoes(cfg, contagem)` devolve as decisões no formato que as
contas pedem. Só `pcm.telas.pode_programar()` decide.

Regras com o caso que as criou:

- **A decisão vale só até a contagem ser gravada.** Depois ela não mudaria o que já foi gravado: a tela recusa (409) e manda
  fazer uma nova contagem. Gravada, ou com a gravação começada (aprovada), ou recusada (recontagem pedida), ou substituída pela
  mais nova do almoxarifado: nenhuma pede decisão.
- **Uma linha decidida não se decide de novo** (dois do PCM com a mesma tela aberta não cadastram a mesma peça duas vezes).
- **Cadastrar sem duplicar.** O `criar_peca` pode criar a peça e perder a resposta (a conexão cai depois de o Fracttal gravar).
  Antes de criar, o código escolhido vai para um controle local (`<NEXUS_DADOS>/almox_inventario/curadoria_<contagem>.json`,
  sem login, sem nome): na nova tentativa da mesma linha o código reservado é o da linha; se ele já existe no Fracttal
  (`Estoque.achar_peca`), não cria de novo, acha o ID e só grava a decisão; se não existe, cria com ele. A reserva também vale
  para as outras linhas da mesma sigla (a peça recém-criada pode ainda não aparecer na lista do Fracttal).
- **O próximo código usa o `Estoque.codigos`**, que traz as peças DESATIVADAS também (a lista de Peças e Suprimentos do Fracttal
  mostra "Não" em "Habilitado" e as mantém): o código de peça desativada não é reaproveitado.
- **A sigla `TST` só no almoxarifado de teste** (`almoxarifado.ids_de_teste`): a prova das gravações é lá, e `SP-TST-NNN` não
  pode nascer no catálogo de um cliente.
- **A foto** é a do achado, guardada em `<NEXUS_DADOS>/almox_inventario/fotos/<nome_da_foto(chave)>.jpg` e servida pela rota
  `.../curadoria/foto/<nome>.jpg` (como as dos extintores, que o App envia ao Nexus e ficam em disco: nunca no banco, que a API
  abre a quem quiser). Sem a foto, a tela diz "sem foto". Como a foto chega a essa pasta é o contrato com o App (a chave em
  `Foto` do livro das contagens; ainda não definido), e o nome é o SHA-1 da chave: qualquer chave cabe num nome de arquivo.
- **Grupo, criticidade e Curva ABC não se gravam pela API** (testado pelo PCM em 09/10): a tela lembra de completar na tela do
  Fracttal.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Response, abort, current_app, redirect, render_template, request, session

from ...campo import visao
from ...cadastro.ligacoes import pasta_dados
from ...dados import almoxarifado as A
from ...dados import fato_inventario as F
from ...dados import fatos as D
from ...prefixo import na_raiz
from .. import telas
from . import contas as C
from . import erros, quem
from . import estoque as E
from .erros import Conflito
from .regua import fmt

# as siglas do catálogo de peças (design 3.8); a do teste só no almoxarifado de teste
SIGLAS = ("PEL", "PME", "CAB", "SEN", "CTR", "COM", "INS", "ARM", "EAX", "HSE", "CSM", "GER")
SIGLA_DE_TESTE = "TST"
DECISOES_DO_TIPO = {"fora_do_catalogo": ("cadastrar", "e_a_peca", "descartar"), "identificar": ("confirmar",)}
UNIDADES = ("UNIDADE", "METRO", "MASSA")        # as que o catálogo de peças tem (as opções da tela)
NOME_MAX, MOTIVO_MAX = 120, 300
_FOTO_ID = re.compile(r"[0-9a-f]{24}")
_TRAVA = threading.Lock()           # a decisão é ler, conferir e escrever; a mesma linha decidida por dois ao mesmo tempo
_txt, _id = A._txt, A._id


# ── o código novo ────────────────────────────────────────────────────────────────────────────────────────────────────
def siglas(cfg, id_almox) -> tuple[str, ...]:
    """As siglas que se pode cadastrar neste almoxarifado: as do catálogo, e a do teste só no almoxarifado de teste."""
    return SIGLAS + ((SIGLA_DE_TESTE,) if _id(id_almox) in A.ids_de_teste(cfg) else ())


def proximo_codigo(codigos: list[str], sigla: str) -> str:
    """`SP-<sigla>-NNN`: o número seguinte ao maior que já existe na sigla (três dígitos, e mais quando passa de 999). O
    sufixo do código (`-AV`) não tira o número: SP-CAB-005-AV já gastou o 005. Sem caixa; o que é de outra sigla não conta."""
    sigla = str(sigla or "").strip().upper()
    if not sigla:
        raise ValueError("a sigla não pode ser vazia")
    padrao = re.compile(rf"SP-{re.escape(sigla)}-(\d+)(?:-[A-Z]+)?", re.IGNORECASE)
    maior = 0
    for c in codigos or []:
        m = padrao.fullmatch(str(c or "").strip())
        if m:
            maior = max(maior, int(m.group(1)))
    return f"SP-{sigla}-{maior + 1:03d}"


# ── o que o livro e o catálogo dizem ─────────────────────────────────────────────────────────────────────────────────
def _estados(cfg, forcar: bool = False) -> tuple[dict, dict]:
    """({contagem_id: as linhas do livro das contagens}, {contagem_id: estado}). O estado diz se ainda se decide: `aberta`; ou
    `gravada` (a gravação feita ou começada: um evento `aprovada` ou `peca_gravada`), `recontagem` (recusada) e `substituida`
    (a mais nova do almoxarifado a substituiu, `contas.substituidas`).

    É o ÚNICO ponto que olha o que já foi gravado: a tela da lista de contagens (Task 5) tem a leitura dela, e quem juntar os
    dois troca só esta função."""
    por: dict[str, list[dict]] = {}
    for l in visao._livro(A.LIVRO_CONTAGENS, A.ABA_CONTAGENS):
        cid = _txt(l.get("ID da contagem"))
        if cid:
            por.setdefault(cid, []).append(l)
    eventos = F.ler(cfg, forcar=forcar)[F.ABA_EVENTO]
    gravadas = {_txt(e.get("contagem_id")) for e in eventos if _txt(e.get("tipo")) in ("aprovada", "peca_gravada")}
    recusadas = {_txt(e.get("contagem_id")) for e in eventos if _txt(e.get("tipo")) == "recontagem_pedida"}
    substituidas = {_txt(e.get("contagem_id")) for e in eventos if _txt(e.get("tipo")) == "substituida"}
    vivas = []
    for cid, ls in por.items():
        if cid not in recusadas and cid not in substituidas:
            p = ls[0]
            vivas.append({"contagem_id": cid, "id_almox": _id(p.get("ID do almoxarifado")),
                          "contada_em": _txt(p.get("Contada em")), "enviada_em": _txt(p.get("Enviada em"))})
    velhas = C.substituidas(vivas, gravadas)
    estado = {cid: ("gravada" if cid in gravadas else "recontagem" if cid in recusadas
                    else "substituida" if cid in substituidas or cid in velhas else "aberta") for cid in por}
    return por, estado


def contagens_abertas(cfg) -> dict[str, list[dict]]:
    """`{contagem_id: linhas}` das contagens que ainda não foram gravadas (nem recusadas nem substituídas). A mesma linha
    reenviada pela fila offline do App conta uma vez (`contas._unicas`)."""
    por, estado = _estados(cfg)
    return {cid: C._unicas(ls) for cid, ls in por.items() if estado[cid] == "aberta"}


def _eh_pendencia(l: dict) -> bool:
    """A linha pede decisão: é do campo `fora_do_catalogo` ou `identificar`, tem "ID da linha" e foi CONTADA (em branco, não
    há o que decidir: o achado em branco nem entra no lote)."""
    return _txt(l.get("Tipo")).lower() in DECISOES_DO_TIPO and bool(_id(l.get("ID da linha"))) \
        and A.contado(l.get("Contado")) is not None


def _decisoes_do_livro(linhas: list[dict]) -> dict:
    """{(contagem_id, chave_linha): a última decisão}: vale a mais nova pela hora gravada (a ordem do livro desempata)."""
    ultima: dict = {}
    for i, r in enumerate(linhas):
        k = (_txt(r.get("contagem_id")), _id(r.get("chave_linha")))
        marca = (_txt(r.get("decidida_em")), i)
        if k not in ultima or marca >= ultima[k][0]:
            ultima[k] = (marca, r)
    return {k: r for k, (_, r) in ultima.items()}


def decisoes(cfg, contagem_id: str) -> dict[str, dict]:
    """As decisões de uma contagem no formato da `contas.contado_efetivo` e da `contas.itens_do_lote`:
    `{ID da linha: {"decisao", "id_item", "codigo"}}` (o `codigo` é o da peça cadastrada)."""
    cid = _txt(contagem_id)
    return {chave: {"decisao": _txt(r.get("decisao")), "id_item": _id(r.get("id_item")), "codigo": _txt(r.get("codigo_criado"))}
            for (c, chave), r in _decisoes_do_livro(F.ler(cfg)[F.ABA_CURADORIA]).items() if c == cid}


def _catalogo() -> dict[str, dict] | None:
    """{id_item: {"codigo", "nome"}} do catálogo do App (a varredura diária, a tela do Almoxarifado); None quando o saldo do
    App não chegou inteiro (número pela metade não vai para a tela, nem vira destino de peça)."""
    from .. import almoxarifado
    d = almoxarifado.montar().dados or {}
    if d.get("estado") != "ok":
        return None
    return {_id(c.get("id")): {"codigo": _txt(c.get("codigo")), "nome": _txt(c.get("nome"))} for c in d.get("catalogo", [])}


def _usina_id(nome) -> int | None:
    """A usina do cadastro pelo nome que o Fracttal dá (a de-para; nunca o código). Sem ela, vazio."""
    lig = D.Ligador(visao._livro("cadastro_nexus", "usinas"), visao._livro("cadastro_nexus", "de_para"),
                    visao._livro("cadastro_nexus", "equipes"), {})
    uid = lig.usina_do_fracttal(nome)
    return int(uid) if uid else None


# ── as fotos ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def nome_da_foto(chave) -> str:
    """O nome (sem a extensão) da foto no disco: o SHA-1 da chave que o App pôs no livro. Qualquer chave cabe num nome de
    arquivo, e a chave nunca vira caminho."""
    return hashlib.sha1(_txt(chave).encode("utf-8")).hexdigest()[:24]


def _pasta_fotos(cfg) -> Path | None:
    try:
        return pasta_dados(cfg) / "almox_inventario" / "fotos"
    except RuntimeError:            # teste sem pasta de dados própria: não lê nem grava a de verdade
        return None


def foto(cfg, foto_id: str) -> bytes | None:
    """A foto do achado (JPEG), ou None. O nome tem de ser o de `nome_da_foto`: nada de caminho."""
    pasta = _pasta_fotos(cfg)
    if pasta is None or not _FOTO_ID.fullmatch(str(foto_id or "")):
        return None
    arq = pasta / f"{foto_id}.jpg"
    return arq.read_bytes() if arq.is_file() else None


def _tem_foto(cfg, chave) -> bool:
    pasta = _pasta_fotos(cfg)
    return bool(_txt(chave)) and pasta is not None and (pasta / f"{nome_da_foto(chave)}.jpg").is_file()


# ── as pendências ────────────────────────────────────────────────────────────────────────────────────────────────────
_BRT = timezone(timedelta(hours=-3))


def _quando_txt(iso) -> str:
    """"26/10, 10:00" (hora de Brasília) de uma hora ISO do livro; o que não é hora volta vazio."""
    try:
        d = E.instante(iso)
    except ValueError:
        return ""
    return d.astimezone(_BRT).strftime("%d/%m, %H:%M")


def pendencias(cfg) -> list[dict]:
    """As linhas `fora_do_catalogo` e `identificar` das contagens que não foram gravadas, na ordem em que a contagem as trouxe
    (a mais antiga primeiro), cada uma com a foto e a decisão que já tem (`decisao`: None se pende). `contado` já é número.
    No genérico, o específico que o técnico escolheu vem com o código e o nome do catálogo do App (quando o catálogo veio)."""
    abertas = contagens_abertas(cfg)
    decididas = _decisoes_do_livro(F.ler(cfg)[F.ABA_CURADORIA])
    catalogo = _catalogo() or {}
    out = []
    for cid, linhas in sorted(abertas.items(), key=lambda kv: (_txt(kv[1][0].get("Contada em")), kv[0])):
        for l in linhas:
            if not _eh_pendencia(l):
                continue
            chave = _id(l.get("ID da linha"))
            d = decididas.get((cid, chave))
            como = _id(l.get("Identificado como"))
            out.append({
                "contagem_id": cid, "chave_linha": chave, "tipo": _txt(l.get("Tipo")).lower(),
                "id_almox": _id(l.get("ID do almoxarifado")), "usina": _txt(l.get("Usina")),
                "contada_em": _txt(l.get("Contada em")), "contada_txt": _quando_txt(l.get("Contada em")), "contado": A.contado(l.get("Contado")),
                "descricao": _txt(l.get("Descrição")), "foto": _txt(l.get("Foto")),
                "foto_id": nome_da_foto(l.get("Foto")) if _txt(l.get("Foto")) else "",
                "tem_foto": _tem_foto(cfg, l.get("Foto")),
                "id_item": _id(l.get("ID do item")), "codigo": _txt(l.get("Código")),
                "identificado_como": como, "identificado_codigo": catalogo.get(como, {}).get("codigo", ""),
                "identificado_nome": catalogo.get(como, {}).get("nome", ""),
                "decisao": None if d is None else {
                    "decisao": _txt(d.get("decisao")), "id_item": _id(d.get("id_item")),
                    "codigo_criado": _txt(d.get("codigo_criado")), "quando": _txt(d.get("decidida_em")),
                    "quando_txt": _quando_txt(d.get("decidida_em"))}})
    return out


# ── o controle do cadastro: o código reservado antes de criar ───────────────────────────────────────────────────────
def _pasta_controle(cfg) -> Path:
    try:
        return pasta_dados(cfg) / "almox_inventario"
    except RuntimeError:
        raise F.Recusada("Este Nexus está em teste e sem pasta de dados própria: não cadastro peça, porque o controle do "
                         "código reservado precisa de onde ficar. Nada foi feito.") from None


def _arquivo_reserva(cfg, contagem_id: str) -> Path:
    """Um arquivo por contagem. O ID da contagem é opaco (o App o gera): o que não cabe num nome de arquivo vira o hash dele."""
    cid = _txt(contagem_id)
    seguro = re.sub(r"[^A-Za-z0-9_-]", "_", cid)
    nome = seguro if seguro == cid and len(cid) <= 60 else f"{seguro[:40]}_{hashlib.sha1(cid.encode()).hexdigest()[:10]}"
    return _pasta_controle(cfg) / f"curadoria_{nome}.json"


def _ler_reservas(arq: Path) -> dict:
    """{chave_linha: {"codigo", ...}}. Arquivo que não existe é vazio; o que existe e não se lê PARA tudo: ignorá-lo escolheria
    o código de novo, e a peça que a tentativa anterior criou ficaria duplicada."""
    try:
        d = json.loads(arq.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as ex:
        raise F.Recusada(f"Não consegui ler o controle dos códigos reservados ({arq.name}): nada foi cadastrado, para não "
                         "criar a peça duas vezes.") from ex
    if not isinstance(d, dict):
        raise F.Recusada(f"O controle dos códigos reservados ({arq.name}) está num formato que não conheço: nada foi cadastrado.")
    return d


def _gravar_reservas(arq: Path, dados: dict) -> None:
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(arq)


def _reservados(cfg, sigla: str) -> list[str]:
    """Os códigos da sigla que alguma contagem já reservou (a peça pode ter sido criada e ainda não aparecer na lista)."""
    pasta, prefixo = _pasta_controle(cfg), f"SP-{sigla}-".upper()
    codigos = []
    for arq in sorted(pasta.glob("curadoria_*.json")):
        for r in _ler_reservas(arq).values():
            c = _txt(r.get("codigo") if isinstance(r, dict) else "")
            if c.upper().startswith(prefixo):
                codigos.append(c)
    return codigos


# ── decidir ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def _achar_a_linha(cfg, contagem_id: str, chave_linha: str) -> dict:
    """A linha do livro das contagens que se decide, se ela pede decisão e a contagem ainda está aberta; senão `ValueError`
    (pedido sem sentido) ou `Conflito` (a contagem já foi gravada, recusada ou substituída)."""
    por, estado = _estados(cfg, forcar=True)           # quem decide vai escrever: o que foi gravado agora vale
    cid = _txt(contagem_id)
    if cid not in por:
        raise ValueError(f"A contagem {cid[:30]!r} não está no livro das contagens do App.")
    if estado[cid] != "aberta":
        porque = {"gravada": "já foi gravada no Fracttal (ou a gravação já começou)",
                  "recontagem": "foi recusada (recontagem pedida)",
                  "substituida": "foi substituída por uma contagem mais nova do almoxarifado"}[estado[cid]]
        raise Conflito(f"Esta contagem {porque}: a decisão não muda o que já foi gravado. Faça uma nova contagem.")
    chave = _id(chave_linha)
    for l in C._unicas(por[cid]):
        if _id(l.get("ID da linha")) == chave:
            if not _eh_pendencia(l):
                raise ValueError("Esta linha não pede decisão (é peça da lista, ou ninguém a contou).")
            return l
    raise ValueError(f"A linha {chave[:30]!r} não está na contagem {cid[:30]!r}.")


def _peca_do_catalogo(cfg, id_item, cadastradas: set[str]) -> str:
    """O ID de uma peça que o PCM disse: tem de estar no catálogo do App ou ter sido cadastrada por aqui (a varredura diária
    ainda não a viu). ID chutado não vira peça: as unidades iriam para um item que não existe."""
    alvo = _id(id_item)
    if not alvo:
        raise ValueError("Informe a peça (o código ou o ID dela no Fracttal).")
    if not alvo.isdigit():
        raise ValueError(f"Não achei a peça {alvo[:30]!r} no catálogo do Fracttal: use o código dela (como SP-CAB-004) ou o ID.")
    if alvo in cadastradas:
        return alvo
    catalogo = _catalogo()
    if catalogo is None:
        raise F.Recusada("Não consegui ler o catálogo de peças do App agora (os livros do almoxarifado não estão inteiros): "
                         "não decido para uma peça que não consigo conferir. Tente de novo em instantes.")
    if alvo not in catalogo:
        raise ValueError(f"A peça {alvo} não existe no catálogo do Fracttal.")
    return alvo


def _cadastrar(cfg, contagem_id, chave, almox, sigla, nome, unidade, estoque) -> tuple[str, str, bool]:
    """Cria a peça no Fracttal sem duplicar. Devolve (id do item, código, criou agora)."""
    sigla = _txt(sigla).upper()
    if sigla not in siglas(cfg, almox):
        raise ValueError(f"A sigla {sigla[:10]!r} não é uma das do catálogo ({', '.join(siglas(cfg, almox))}).")
    nome = " ".join(_txt(nome).split())
    if not nome or len(nome) > NOME_MAX:
        raise ValueError(f"Informe o nome da peça (até {NOME_MAX} letras).")
    unidade = _txt(unidade).upper() or "UNIDADE"
    if estoque is None:
        raise ValueError("Cadastrar fala com o Fracttal: é preciso o login do Fracttal de quem decide.")
    arq = _arquivo_reserva(cfg, contagem_id)
    reservas = _ler_reservas(arq)
    reserva = reservas.get(chave)
    if isinstance(reserva, dict) and _txt(reserva.get("codigo")):
        codigo = _txt(reserva["codigo"])             # o código desta linha já foi escolhido numa tentativa anterior
        id_item = estoque.achar_peca(codigo)         # criou e perdeu a resposta? então só falta o ID
    else:
        codigo = proximo_codigo(list(estoque.codigos(sigla)) + _reservados(cfg, sigla), sigla)
        reservas[chave] = {"codigo": codigo, "sigla": sigla, "reservado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        _gravar_reservas(arq, reservas)              # ANTES de criar: se a resposta se perder, a nova tentativa sabe qual era
        id_item = None
    if id_item is not None:
        return id_item, codigo, False
    return str(estoque.criar_peca(codigo, nome, unidade)), codigo, True


def decidir(cfg, contagem_id: str, chave_linha: str, decisao: str, *, id_item: str | None = None, sigla: str | None = None,
            nome: str | None = None, unidade: str | None = None, motivo: str | None = None,
            estoque: E.Estoque | None = None, pessoa: dict | None) -> dict:
    """Registra a decisão do PCM sobre uma linha da contagem e devolve `{"decisao", "id_item", "codigo", "criada", "texto"}`.

    - `cadastrar` (achado fora do catálogo): cria a peça (`estoque.criar_peca`, no login de quem decide) com `sigla`, `nome` e
      `unidade`, e grava a decisão com o ID e o código criados;
    - `e_a_peca` (achado): `id_item` é a peça do catálogo a que as unidades pertencem;
    - `confirmar` (genérico): `id_item` é o específico (sem ele, o que o técnico escolheu);
    - `descartar` (achado): `motivo` obrigatório, cifrado.
    `motivo` também vai (cifrado) nas outras decisões, quando vem.

    `ValueError`: o pedido não faz sentido (nada foi feito). `Conflito`: a linha já foi decidida ou a contagem já não está
    aberta. `Recusada`: o livro (ou o controle do código) não deixou. O Fracttal levanta `Limite`, `SemLogin` e `ErroFracttal`.
    A decisão de uma linha é uma só: a 2ª é recusada, e o Fracttal nem é chamado."""
    if decisao not in F.DECISOES_CURADORIA:
        raise ValueError(f"Decisão que a curadoria não conhece: {str(decisao)[:20]!r}.")
    cid, chave = _txt(contagem_id), _id(chave_linha)
    motivo = " ".join(_txt(motivo).split())
    if len(motivo) > MOTIVO_MAX:
        raise ValueError(f"O motivo passa de {MOTIVO_MAX} letras.")
    with _TRAVA:
        l = _achar_a_linha(cfg, cid, chave)
        tipo = _txt(l.get("Tipo")).lower()
        if decisao not in DECISOES_DO_TIPO[tipo]:
            raise ValueError(f"A decisão {decisao!r} não é para esta linha ({'o genérico a identificar' if tipo == 'identificar' else 'o achado fora do catálogo'}): "
                             f"aqui vale {' ou '.join(DECISOES_DO_TIPO[tipo])}.")
        livro = F.ler(cfg, forcar=True)
        if (cid, chave) in _decisoes_do_livro(livro[F.ABA_CURADORIA]):
            raise Conflito("Nada foi feito: esta linha já foi decidida (por outra pessoa do PCM, ou num clique anterior). "
                           "Uma linha decidida não se decide de novo.")
        if decisao == "descartar" and not motivo:
            raise ValueError("Descartar pede o motivo (fica cifrado, na auditoria).")
        almox = _id(l.get("ID do almoxarifado"))
        cadastradas = {_id(r.get("id_item")) for r in livro[F.ABA_CURADORIA]
                       if _txt(r.get("decisao")) == "cadastrar" and _id(r.get("id_item"))}
        codigo, criada, texto = "", False, ""
        if decisao == "cadastrar":
            id_final, codigo, criada = _cadastrar(cfg, cid, chave, almox, sigla, nome, unidade, estoque)
            texto = (f"Peça cadastrada no Fracttal: {codigo}." if criada else
                     f"A peça {codigo} já estava no Fracttal (a tentativa anterior a criou): usei ela, sem criar outra.")
        elif decisao == "descartar":
            id_final, texto = "", "Achado descartado: não entra na contagem."
        else:
            escolhida = _id(id_item) or (_id(l.get("Identificado como")) if decisao == "confirmar" else "")
            if not escolhida:
                raise ValueError("Informe qual é a peça: o técnico não disse qual era o específico.")
            id_final = _peca_do_catalogo(cfg, escolhida, cadastradas)
            texto = ("As unidades saem do genérico e entram na peça escolhida." if decisao == "confirmar"
                     else "As unidades achadas contam como unidades dessa peça nesta contagem.")
        usina = _usina_id(_txt(l.get("Usina")))
        quem_ = quem.colunas(cfg, pessoa)
        linha = {"contagem_id": cid, "chave_linha": chave, "decisao": decisao, "id_item": id_final or None,
                 "codigo_criado": codigo or None, "id_almoxarifado": almox, "usina_id": usina,
                 "usina_ligada_por": F.USINA_LIGADA_POR[0] if usina else None, **quem_}
        if motivo:
            linha["dados"] = {"motivo": motivo}
        F.acrescentar(cfg, F.ABA_CURADORIA, [linha])
        try:
            F.acrescentar(cfg, F.ABA_EVENTO, [{
                "tipo": "curadoria", "contagem_id": cid, "id_almoxarifado": almox, "id_item": id_final or None,
                "codigo": codigo or None, "usina_id": usina, "usina_ligada_por": F.USINA_LIGADA_POR[0] if usina else None,
                **quem_}])
        except F.Recusada as ex:
            raise F.Recusada(f"A decisão ficou registrada, mas não consegui anotá-la na auditoria ({ex}).") from ex
    return {"decisao": decisao, "id_item": id_final, "codigo": codigo, "criada": criada, "texto": texto}


# ── as telas ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _peca_pelo_codigo_ou_id(texto) -> str:
    """O PCM conhece o código da peça (SP-CAB-004), não o ID: aceita o código (sem caixa) ou o ID, e devolve o ID. O que não
    está no catálogo volta como veio, e o `decidir` o recusa com o motivo."""
    t = _txt(texto)
    catalogo = _catalogo() or {}
    por_codigo = {v["codigo"].upper(): i for i, v in catalogo.items() if v["codigo"]}
    return por_codigo.get(t.upper(), t)


def _pagina(*, erro: str = "", status: int = 200):
    cfg = current_app.config
    erro_livro, lista = "", []
    try:
        lista = pendencias(cfg)
    except F.Recusada as ex:
        erro_livro = str(ex)
    except (visao.SemBanco, OSError) as ex:
        erro_livro = f"Não consegui ler as contagens no banco ({type(ex).__name__}): tente de novo em instantes."
    catalogo = _catalogo() or {}
    aviso = session.pop("pcm_curadoria_aviso", None) if status == 200 else None
    pendentes = [p for p in lista if p["decisao"] is None]
    resp = render_template(
        "pcm/inventario_curadoria.html", pendentes=pendentes, decididas=[p for p in lista if p["decisao"] is not None],
        siglas_de=lambda almox: siglas(cfg, almox), unidades=UNIDADES, fmt=fmt, pode=telas.pode_programar(), ok=aviso or "",
        erro=erro, erro_livro=erro_livro,
        pecas=sorted(((v["codigo"], v["nome"]) for v in catalogo.values() if v["codigo"])))
    return resp, status


def registrar(bp) -> None:
    @bp.route("/pecas/inventario/curadoria", endpoint="inventario_curadoria")
    def curadoria_tela():
        return _pagina()

    @bp.route("/pecas/inventario/curadoria/foto/<foto_id>.jpg", endpoint="inventario_curadoria_foto")
    def curadoria_foto(foto_id):
        """A foto do achado, para quem vê a tela (o portão de login e o da tela valem; não é rota pública)."""
        dados = foto(current_app.config, foto_id)
        if dados is None:
            abort(404)
        return Response(dados, mimetype="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})

    @bp.route("/pecas/inventario/curadoria/decidir", methods=["POST"], endpoint="inventario_curadoria_decidir")
    def curadoria_decidir():
        """Decide uma linha: "é a peça X", confirmar o genérico ou descartar. Só administrador e setor PCM (`pode_programar`).
        São decisões do Nexus, que só gravam no livro. **Cadastrar não passa por aqui**: ele cria a peça no Fracttal com o
        login de quem decide, e esse login (o cookie `os_sessao`) só chega às rotas debaixo de /os: o cadastro roda na ponte
        `/os/_nexus/inventario/curadoria/cadastrar` (`ponte_os.py`)."""
        if not telas.pode_programar() or telas._de_outro_site():
            abort(403)
        f = request.form
        decisao = _txt(f.get("decisao"))
        try:
            if decisao == "cadastrar":
                raise ValueError("Cadastrar fala com o Fracttal e roda pela ponte do login do Fracttal "
                                 "(/os/_nexus/inventario/curadoria/cadastrar), não por esta rota. Nada foi feito.")
            r = decidir(current_app.config, _txt(f.get("contagem")), _txt(f.get("linha")), decisao,
                        id_item=_peca_pelo_codigo_ou_id(f.get("peca")) if f.get("peca") else None, motivo=f.get("motivo"),
                        pessoa=quem.do_pedido())
        except (ValueError, OSError) as ex:
            status, texto = erros.resposta(ex)
            return _pagina(erro=texto, status=status)
        session["pcm_curadoria_aviso"] = r["texto"]
        return redirect(na_raiz("/t/pcm/pecas/inventario/curadoria"), code=303)
