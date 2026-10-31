"""A foto dos ativos do Fracttal no banco, `nexus_ativos_fracttal · foto_ativos`, renovada toda noite (31/10/2026, etapa 2 do
canto central do OS Creator; desenho `docs/superpowers/specs/2026-10-30-oscreator-canto-central-design.md`).

Até aqui ela era a carga única de 11/10/2026 (as fotos que o OS Creator guardou em arquivo, `ferramentas/carregar_ativos_
fracttal.py --gravar`, quem gravava era o Levi): 22.357 linhas que só envelheciam, e a dimensão de equipamento
(`equipamento.py`), que a lê de hora em hora, envelhecia junto. Agora o leitor dos ativos do servidor
(`nexus/torres/oscreator/os_creator/ativos_leitor.py`) lê o Fracttal inteiro de madrugada e, DEPOIS que o catálogo do OS
Creator aceitou a leitura (a guarda é uma só: a leitura incompleta, a que encolhe mais de 5% e a que não bate com o catálogo
não chegam aqui), entrega os itens a `gravar`. A ferramenta ficou só com a medição: uma máquina grava (regra 11 do
`nexus/dados/CLAUDE.md`), e é o servidor.

O GRÃO: 1 linha = 1 item do Fracttal com 1 código (o par `fracttal_item_id` + `codigo`; a raiz de cada cliente, sem
`pai_item_id`, inclusive: é dela que sai o nome do cliente no caminho do ativo). As colunas são as de `equipamento.CAB_FOTO`,
com três no fim desde 31/10: `id_type_item`, `id_group_task` e `fora_do_fracttal_desde` (data_id).
- O CÓDIGO QUE SAI DO FRACTTAL FICA (os fatos antigos ligam por ele, como os 719 códigos de junho que a carga única levou),
  marcado com o dia em que deixou de vir; voltou, a marca sai. Na 1ª renovação, os códigos da foto mais velha que a de 22/09
  já não estavam nela: ganham a marca desse dia (20260922), e não o da renovação.
- `foto_em` é o dia (de Brasília) em que a LINHA mudou pela última vez. Por isso a mesma leitura amanhã dá o mesmo sha e o
  livro não é trocado (são 22 mil linhas: trocar todo dia sem nada novo regravaria a dimensão de equipamento junto).
- A leitura do banco é CONFERIDA (`ler`): a aba que a listagem não traz, ou que vem com menos linhas que o `row_count` dela,
  não grava (gravar por cima de uma leitura curta apagaria os códigos que saíram do Fracttal, que só existem aqui). E o livro
  é `so_cresce` no catálogo: a trava do `livros.publicar` confere de novo antes de trocar.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import date, datetime, timedelta, timezone

from . import equipamento as eq
from . import livros

_BRT = timezone(timedelta(hours=-3))
CAB_FOTO = eq.CAB_FOTO
_I = {c: i for i, c in enumerate(CAB_FOTO)}
CAB_ATUALIZACAO = ["gerado_em", "maquina", "duracao_s", "linhas", "como_ler", "sha_linhas", "fora_do_fracttal"]
COMO_LER = ("1 linha = 1 item do Fracttal com 1 código (fracttal_item_id + codigo; a raiz do cliente é a linha sem "
            "pai_item_id); foto_em = o dia em que a linha mudou pela última vez; fora_do_fracttal_desde = o dia (data_id) "
            "em que o código deixou de vir na leitura do Fracttal, vazio = está no Fracttal")


class LeituraCurta(RuntimeError):
    """A foto do banco não veio inteira (a listagem não traz a aba, ou ela veio com menos linhas que o banco diz ter): nada
    se grava por cima."""


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _int(v):
    try:
        i = int(round(float(v)))
    except (TypeError, ValueError, OverflowError):
        return None
    return i if i > 0 else None


def _canon_linha(d) -> list:
    """A linha no formato de comparação (`CAB_FOTO`), venha do banco (a API pode devolver tudo como texto) ou da leitura."""
    if not isinstance(d, dict):
        d = dict(zip(CAB_FOTO, d))
    return [_int(d.get("fracttal_item_id")), eq.canon(d.get("codigo")) or None, _txt(d.get("descricao")) or None,
            _int(d.get("pai_item_id")), _txt(d.get("tipo_fracttal")) or None, _txt(d.get("foto_em"))[:10] or None,
            _int(d.get("id_type_item")), _int(d.get("id_group_task")), _int(d.get("fora_do_fracttal_desde"))]


def _chave(l) -> tuple:
    return (l[_I["fracttal_item_id"]], l[_I["codigo"]])


def _conteudo(l) -> list:
    """A linha sem o `foto_em`: é o que diz se ela mudou."""
    return [v for i, v in enumerate(l) if i != _I["foto_em"]]


def _ordem(l) -> tuple:
    """Em ordem de item e código; no empate (a mesma chave duas vezes, que não devia haver), pela linha inteira: a ordem não
    pode depender de como o banco devolveu, senão o sha muda sem o conteúdo mudar."""
    return (l[0] or 0, l[1] or "", json.dumps(l, ensure_ascii=False, default=str))


def linha_do_item(item: dict, tipo_code=None) -> list:
    """A linha de um item lido do Fracttal (o formato cru do RPC que o leitor monta: id, code, description, id_parent,
    id_type_item, id_group_task) com o `tipo_code` do registro do catálogo (o mesmo `tipo_fracttal` da carga de 11/10; a raiz
    do cliente não tem). O `foto_em` e a marca de fora são da `renovar`."""
    cod = eq.canon(item.get("code"))
    return [_int(item.get("id")), cod or None, eq._descricao(item.get("description"), cod), _int(item.get("id_parent")),
            _txt(tipo_code) or None, None, _int(item.get("id_type_item")), _int(item.get("id_group_task")), None]


def _data_id(dia: date) -> int:
    return int(dia.strftime("%Y%m%d"))


def _de_11_10(linhas) -> bool:
    """A foto da carga única (lida do banco sem a coluna da marca, que entrou em 31/10)."""
    ricas = [d for d in linhas or () if isinstance(d, dict)]
    return bool(ricas) and not any("fora_do_fracttal_desde" in d for d in ricas)


def renovar(antigas, novas, hoje: date, *, de_11_10: bool | None = None) -> tuple[list, dict]:
    """(as linhas da foto renovada, em ordem; o relatório só com contagens). PURA: `antigas` são as linhas lidas do banco
    (dicionários, ou as listas de `ler`, com `de_11_10` dito), `novas` as do Fracttal de agora (`linha_do_item`). Ver o topo
    do módulo: o código que saiu fica marcado, o que voltou perde a marca, e o `foto_em` só muda na linha que mudou."""
    hoje_iso, hoje_id = hoje.isoformat(), _data_id(hoje)
    # a foto da carga única (sem a coluna da marca): a linha de uma foto mais velha que a última já tinha saído do Fracttal
    # no dia da última
    de_11_10 = _de_11_10(antigas) if de_11_10 is None else de_11_10
    velhas = [_canon_linha(d) for d in (antigas or ())]
    ultima = max((l[_I["foto_em"]] or "" for l in velhas), default="")
    try:
        saiu_antes = _data_id(date.fromisoformat(ultima)) if de_11_10 and ultima else None
    except ValueError:
        saiu_antes = None
    por_chave: dict = {}
    sobras = []                                                     # a mesma chave duas vezes no banco: nenhuma se perde
    for l in velhas:
        if _chave(l) in por_chave:
            sobras.append(l)
        else:
            por_chave[_chave(l)] = l
    rel = {"lidas_do_fracttal": 0, "iguais": 0, "mudaram": 0, "entraram": 0, "voltaram": 0, "sairam": 0,
           "fora_do_fracttal": 0}
    out, vistas = [], set()
    for nova in novas:
        nova = list(nova)
        if _chave(nova) in vistas:
            continue
        vistas.add(_chave(nova))
        rel["lidas_do_fracttal"] += 1
        velha = por_chave.get(_chave(nova))
        if velha is not None and _conteudo(velha) == _conteudo(nova):
            nova[_I["foto_em"]] = velha[_I["foto_em"]] or hoje_iso
            rel["iguais"] += 1
        else:
            nova[_I["foto_em"]] = hoje_iso
            if velha is None:
                rel["entraram"] += 1
            elif velha[_I["fora_do_fracttal_desde"]]:
                rel["voltaram"] += 1
            else:
                rel["mudaram"] += 1
        out.append(nova)
    for chave, velha in por_chave.items():
        if chave in vistas:
            continue
        velha = list(velha)
        if not velha[_I["fora_do_fracttal_desde"]]:
            antiga = saiu_antes is not None and (velha[_I["foto_em"]] or "") < ultima
            velha[_I["fora_do_fracttal_desde"]] = saiu_antes if antiga else hoje_id
            velha[_I["foto_em"]] = hoje_iso
            rel["sairam"] += 1
        out.append(velha)
    out.extend(sobras)
    out.sort(key=_ordem)
    rel["fora_do_fracttal"] = sum(1 for l in out if l[_I["fora_do_fracttal_desde"]])
    rel["linhas"] = len(out)
    return out, rel


def sha(linhas) -> str:
    """O sha do conteúdo (as linhas já no formato de comparação, em ordem): o mesmo em qualquer máquina."""
    corpo = json.dumps(sorted(linhas, key=_ordem), ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha1(corpo.encode("utf-8")).hexdigest()


def contar(linhas) -> dict:
    """As contagens de uma foto (a medição da ferramenta e o relatório): linhas, sem código, raízes, fora do Fracttal e
    quantas linhas de cada `foto_em`."""
    ls = [_canon_linha(l) for l in linhas or ()]
    por_dia: dict = {}
    for l in ls:
        if l[_I["foto_em"]]:
            por_dia[l[_I["foto_em"]]] = por_dia.get(l[_I["foto_em"]], 0) + 1
    return {"foto_ativos": len(ls), "sem_codigo": sum(1 for l in ls if not l[_I["codigo"]]),
            "raizes": sum(1 for l in ls if not l[_I["pai_item_id"]]),
            "fora_do_fracttal": sum(1 for l in ls if l[_I["fora_do_fracttal_desde"]]),
            "por_foto": dict(sorted(por_dia.items()))}


def ler(base: str, sessao) -> tuple[list, bool]:
    """(as linhas da foto no banco, já no formato de comparação; se é a foto da carga única de 11/10), CONFERIDAS: o livro que
    ainda não existe é a 1ª gravação ([]); o que existe tem de trazer a aba e, nela, as linhas que a listagem diz
    (`row_count`). Senão, `LeituraCurta` e nada se grava. As linhas saem em listas, e não nos dicionários que a API dá: são
    ~27 mil, lidas de madrugada ao lado da leitura do Fracttal, num servidor que já anda apertado de memória."""
    r = sessao.get(f"{base}/api/workbooks", timeout=60)
    r.raise_for_status()
    w = next((x for x in r.json() if x.get("key") == eq.LIVRO_FOTO), None)
    r = sessao.get(f"{base}/api/sheets", timeout=60)
    r.raise_for_status()
    listadas = {x["sheet_name"]: x for x in r.json() if x.get("workbook_key") == eq.LIVRO_FOTO}
    if w is None and not listadas:
        return [], False
    n = livros._int((w or {}).get("sheet_count"))
    if eq.ABA_FOTO not in listadas or (n is not None and len(listadas) < n):
        raise LeituraCurta(f"{eq.LIVRO_FOTO}: a listagem do banco não trouxe a aba {eq.ABA_FOTO} inteira (o livro diz "
                           f"{n} abas e vieram {len(listadas)}); não gravo por cima")
    aba = listadas[eq.ABA_FOTO]
    esperado = livros._int(aba.get("row_count"))
    linhas = livros._linhas(base, sessao, aba["id"])
    if esperado is None or len(linhas) != esperado:
        raise LeituraCurta(f"{eq.LIVRO_FOTO}.{eq.ABA_FOTO}: li {len(linhas)} linhas e o banco diz {esperado}; não gravo "
                           "por cima")
    de_11_10 = _de_11_10(linhas)
    return [_canon_linha(d) for d in linhas], de_11_10


def gravar(novas, *, base: str, token: str, sessao, maquina: str, antigas=None, de_11_10: bool = False,
           hoje: date | None = None) -> dict:
    """Renova a foto com as linhas do Fracttal de agora (`linha_do_item`): lê a do banco (conferida; `antigas` e `de_11_10` se
    quem chama já leu, pela mesma `ler`), junta (`renovar`) e grava SÓ se o sha das linhas mudou, pelo `livros.publicar` (que
    confere a trava `so_cresce` antes e cada aba depois). Devolve o relatório (contagens, `gravou`, o sha). Levanta
    `LeituraCurta`, `livros.GravacaoRecusada` e o erro do banco: quem chama (o leitor da noite) os guarda no estado."""
    t0 = time.time()
    if not token:
        raise RuntimeError("sem o GRIDCO_SQL_TOKEN: a foto dos ativos não é gravada")
    hoje = hoje or datetime.now(_BRT).date()
    if antigas is None:
        antigas, de_11_10 = ler(base, sessao)
    linhas, rel = renovar(antigas, novas, hoje, de_11_10=de_11_10)
    novo, velho = sha(linhas), sha([_canon_linha(d) for d in antigas])
    rel["sha_linhas"] = novo
    if novo == velho:
        return dict(rel, gravou=False, motivo="nada mudou desde a última renovação")
    agora = datetime.now(_BRT).isoformat(timespec="seconds")
    tabelas = {eq.ABA_FOTO: (CAB_FOTO, linhas),
               "atualizacao": (CAB_ATUALIZACAO, [[agora, maquina, round(time.time() - t0, 1), len(linhas), COMO_LER, novo,
                                                  rel["fora_do_fracttal"]]])}
    rel["conferido"] = livros.publicar(eq.LIVRO_FOTO, eq.NOME_FOTO, tabelas, base=base, token=token, sessao=sessao)
    return dict(rel, gravou=True)
