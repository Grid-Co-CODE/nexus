"""A curadoria do PCM no Acompanhamento (14/10/2026): o que a reunião de PCM decide sobre cada MPA e MPS acompanhada e
que não existe em nenhum sistema. No painel do PCM ela era um arquivo no computador de quem o mantinha
(`scripts/curadoria.json`); no Nexus é um livro do banco, para todo mundo ler a mesma.

O que cada item diz (o `_leia` do arquivo do painel): o grupo (1 Engenharia, relatório ou revisão; 2 poucas pendências,
auxílio da Manutenção; 3 atrasadas com mais pendências; 0 fora do ranking), o prazo do relatório da Engenharia, se o
relatório sai sem a análise de óleo, a cadeia de OS de uma MPA dividida, o que falta em campo, a classificação do
bloqueio, a observação, a OS que acha a linha certa na Gerencial (`hint`) e o `manual`, que trava os números. As
pendências, o total e o progresso NÃO vêm daqui: o Nexus recalcula pelo Fracttal a cada leitura (`dados._pendencias`).

O dado: livro `nexus_pcm_curadoria · fato_decisao_curadoria` (catálogo: fato `decisao_curadoria_pcm`). Grão: 1 linha = 1
decisão sobre 1 MPA/MPS acompanhada (`item_id`), ou sobre a regra do responsável da Manutenção (`item_id` "manutencao":
quem cuida do Norte e Nordeste e quem cuida do resto). Só acrescenta; vale a última de cada item; `ativo` "não" tira o
item do painel. O conteúdo vai CIFRADO com a chave do cadastro (`dados_cifrados`, o Cofre, como a observação do
responsável): a API do banco tem leitura aberta e ali há nome de gente. Em claro só o item, o tipo e o grupo.

Fora do servidor (cópia de prova), `NEXUS_PCM_CURADORIA_ARQUIVO` aponta um arquivo no formato do painel e vale por cima
do banco.
"""
import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ...dados import fatos as D
from ...dados import livros
from .dados import norm

log = logging.getLogger(__name__)

LIVRO, NOME_LIVRO = "nexus_pcm_curadoria", "Nexus · curadoria do PCM (acompanhamento)"
ABA = "fato_decisao_curadoria"
CAB = ("item_id", "decidida_em", "data_id", "tipo", "grupo", "ativo", "dados_cifrados", "origem")
ITEM_MANUTENCAO = "manutencao"
# os campos que a curadoria guarda (os números do Fracttal, pend/tot/prog, entram como a última foto do painel e são
# recalculados a cada leitura; o `flag` marca a MPA dada como concluída em campo)
CAMPOS = ("grupo", "os", "usina", "tipo", "fim", "resp", "prazo", "obs", "bl", "hint", "sem_oleo", "pend", "tot", "falta",
          "manual", "flag", "cadeia", "prog")
TTL_S = 120
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê."""


def item_id(it: dict) -> str:
    """O item é a MPA/MPS de uma usina numa OS: o mesmo tipo, usina e OS dão o mesmo item em qualquer máquina."""
    chave = f"{it.get('tipo')}|{norm(it.get('usina'))}|{str(it.get('os') or '').strip()}"
    return hashlib.sha1(chave.encode("utf-8")).hexdigest()[:12]


def _cofre(cfg):
    chave = cfg.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): a curadoria vai cifrada")
    from ...cadastro.cifra import Cofre
    return Cofre(chave)


def _ctx(iid: str) -> str:
    return f"pcm/curadoria/{iid}"


def de_arquivo(caminho) -> tuple[list[dict], dict]:
    """(itens, manutencao) de um arquivo no formato do painel (`{"itens": [...]}`; a regra da Manutenção, se houver, em
    `"manutencao": {"nne", "outros"}`)."""
    bruto = json.loads(Path(caminho).read_text(encoding="utf-8"))
    itens = [{k: v for k, v in it.items() if k in CAMPOS} for it in bruto.get("itens") or [] if isinstance(it, dict)]
    return itens, dict(bruto.get("manutencao") or {})


def _linhas_banco(base: str, sessao) -> list[dict]:
    a = livros.abas(base, sessao, LIVRO)
    return list(livros._linhas(base, sessao, a[ABA])) if ABA in a else []


def vigentes(linhas: list[dict], cofre) -> tuple[list[dict], dict, int]:
    """(itens ativos, regra da Manutenção, ilegíveis) pela última decisão de cada item (pela hora; empate fica na ordem
    do livro). Linha que não abre com a chave conta como ilegível e não entra."""
    ultima = {}
    for x in sorted(linhas or [], key=lambda x: D._txt(x.get("decidida_em"))):
        iid = D._txt(x.get("item_id"))
        if iid:
            ultima[iid] = x
    itens, manutencao, ilegiveis = [], {}, 0
    for iid, x in ultima.items():
        if D._txt(x.get("ativo")).lower() in ("não", "nao", "n"):
            continue
        try:
            corpo = json.loads(cofre.decifrar(D._txt(x.get("dados_cifrados")), _ctx(iid)))
        except Exception:        # noqa: BLE001 — cifra de outra chave ou linha mexida: não entra, e é contada
            ilegiveis += 1
            continue
        if iid == ITEM_MANUTENCAO:
            manutencao = {k: str(v) for k, v in corpo.items() if k in ("nne", "outros")}
        else:
            itens.append(dict(corpo, id=iid))
    return itens, manutencao, ilegiveis


def ler(cfg, base: str, sessao, forcar: bool = False) -> dict:
    """{"itens", "manutencao", "erro", "ilegiveis", "fonte"}: o arquivo da cópia de prova, senão o livro do banco,
    guardado por 2 minutos; a leitura que falha devolve a última boa com o erro (sem nenhuma, vazio com o erro)."""
    arquivo = cfg.get("NEXUS_PCM_CURADORIA_ARQUIVO")
    if arquivo:
        itens, man = de_arquivo(arquivo)
        return {"itens": [dict(it, id=item_id(it)) for it in itens], "manutencao": man, "erro": "", "ilegiveis": 0,
                "fonte": "arquivo"}
    c = _CACHE.get("livro")
    if c and not forcar and time.time() - c["lido_em"] < TTL_S:
        return c
    if not base:                     # sem o endereço do banco (a `sessao` traz o motivo)
        return {"itens": [], "manutencao": {}, "erro": f"sem o banco ({sessao})", "ilegiveis": 0, "fonte": "banco",
                "lido_em": None}
    try:
        itens, man, ilegiveis = vigentes(_linhas_banco(base, sessao), _cofre(cfg))
    except Exception as ex:      # noqa: BLE001 — banco fora, rede, sem a chave
        erro = str(ex) if isinstance(ex, Recusada) else f"{type(ex).__name__}: {str(ex)[:160]}"
        if c:
            return dict(c, erro=erro, velha=True)
        return {"itens": [], "manutencao": {}, "erro": erro, "ilegiveis": 0, "fonte": "banco", "lido_em": None}
    c = {"itens": itens, "manutencao": man, "erro": "", "ilegiveis": ilegiveis, "fonte": "banco", "lido_em": time.time()}
    _CACHE["livro"] = c
    return c


def limpar() -> None:
    _CACHE.clear()


def gravar(itens: list[dict], manutencao: dict, cfg, base: str, sessao, origem: str) -> dict:
    """Grava a curadoria inteira de uma vez (a carga do arquivo do painel, `ferramentas/carregar_curadoria_pcm.py`): uma
    decisão por item, mais a regra da Manutenção, e "ativo: não" para o item que estava no banco e saiu. O livro é
    trocado inteiro (`livros.publicar`) com as decisões antigas mais as novas. {"gravadas", "tiradas"}."""
    token = cfg.get("GRIDCO_SQL_TOKEN")
    if not token:
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN): nada foi gravado.")
    cofre = _cofre(cfg)
    with _TRAVA:
        try:
            antigas = _linhas_banco(base, sessao)
        except Exception as ex:  # noqa: BLE001
            raise Recusada(f"Não consegui ler a curadoria no banco ({type(ex).__name__}): nada foi gravado, para não "
                           "apagar o que já está lá.") from ex
        agora = datetime.now(timezone.utc)
        quando, data_id = agora.strftime("%Y-%m-%dT%H:%M:%SZ"), int(agora.astimezone(_BRT).strftime("%Y%m%d"))
        novas, vistos = [], set()
        for it in itens:
            corpo = {k: it[k] for k in CAMPOS if k in it}
            iid = item_id(corpo)
            vistos.add(iid)
            novas.append([iid, quando, data_id, corpo.get("tipo") or "", corpo.get("grupo"), "sim",
                          cofre.cifrar(json.dumps(corpo, ensure_ascii=False), _ctx(iid)), origem])
        if manutencao:
            vistos.add(ITEM_MANUTENCAO)
            novas.append([ITEM_MANUTENCAO, quando, data_id, "", None, "sim",
                          cofre.cifrar(json.dumps(manutencao, ensure_ascii=False), _ctx(ITEM_MANUTENCAO)), origem])
        ativos_antes = {D._txt(x.get("item_id")) for x in antigas if D._txt(x.get("ativo")).lower() == "sim"}
        tiradas = sorted(ativos_antes - vistos)
        for iid in tiradas:
            novas.append([iid, quando, data_id, "", None, "não", "", origem])
        vazio = (lambda v: None if v in ("", None) else v)    # noqa: E731
        linhas = [[vazio(x.get(c)) for c in CAB] for x in antigas] + [[vazio(v) for v in n] for n in novas]
        livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), linhas)}, base=base, token=token, sessao=sessao)
        _CACHE.clear()
    log.info("Curadoria do PCM: %s decisão(ões) gravada(s), %s item(ns) tirado(s), origem %s.", len(novas) - len(tiradas),
             len(tiradas), origem)
    return {"gravadas": len(novas) - len(tiradas), "tiradas": len(tiradas)}
