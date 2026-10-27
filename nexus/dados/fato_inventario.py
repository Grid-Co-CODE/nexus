"""O livro do inventário do almoxarifado no Nexus (26/10/2026): o rastro de cada mudança, a régua de mínimo e máximo e a
curadoria do que o campo contou fora do catálogo.

Levi, 26/10/2026, com o mockup Spare Parts do PCM: o técnico conta as peças no App, o PCM revisa e aprova no Nexus, e o
Nexus grava o número contado no Fracttal. Desenho: `docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md`
(seção 5). Aqui mora só o LIVRO (governança, PRIORIDADE 0); a contagem em si é o 5º livro do App
(`almoxarifado_contagens_app_campo`, fato `contagem_inventario`), e as telas e a gravação no Fracttal vêm nas tarefas
seguintes (`nexus/pcm/inventario/`), que gravam POR AQUI:

- `fato_evento_inventario`: 1 linha = 1 evento da auditoria (contagem recebida, aprovada, peça gravada, conflito, erro,
  peça tirada do lote, recontagem pedida, número corrigido, contagem substituída, curadoria decidida, régua gravada).
  Transação: nunca muda, só acrescenta, e o estado de cada contagem sai dos eventos na ordem da gravação;
- `fato_regua_minimo`: 1 linha = 1 decisão do PCM sobre o recomendado (a Grid) ou o acordado (o cliente) de uma peça num
  almoxarifado; vale a última de cada almoxarifado e peça. Só o acordado vai ao Fracttal;
- `fato_curadoria_inventario`: 1 linha = 1 decisão sobre 1 linha da contagem que veio fora do catálogo (cadastrar, é a
  peça X, confirmar o genérico, descartar); vale a última de cada contagem e linha.

Os três só crescem (`so_cresce`: o `livros.publicar` recusa a leitura incompleta e a aba que encolheria). A gravação
troca o livro inteiro, então `acrescentar` RELÊ o livro antes (leitura que falha, ou que volta com menos linhas do que a
listagem do banco diz, não grava: `Recusada`) e grava todas as abas, com a `qualidade` e a `atualizacao`. Uma gravação
por vez neste processo (a gravação em segundo plano e a tela do PCM escrevem aqui ao mesmo tempo).

Regra 8 (a API do banco tem leitura aberta): NENHUMA coluna em claro aceita texto livre. A pessoa vai como `pessoa_id`
(quando o cadastro a acha) e `pessoa_hmac` (sempre, nunca o e-mail: 24 hexadecimais, o `codigo_da_pessoa`); a `situacao`,
o `tipo` e a `decisao` são listas fechadas; os IDs do Fracttal são só dígitos; os IDs opacos (evento, contagem, linha)
não levam espaço. O motivo do PCM, que é texto livre, vai só dentro de `dados_cifrados` (o Cofre do cadastro, amarrado à
linha), e a coluna NÃO se passa pronta: quem chama passa `dados={"motivo": ...}` e o módulo cifra (um `dados_cifrados`
com texto em claro foi o furo que a revisão de 26/10/2026 achou). Coluna em claro que o livro não tem, e-mail em
qualquer coluna e valor fora da lista são erro de quem chama (`ValueError`), nunca texto em claro. O estado do trabalho
em andamento (o lote, o ponto de retomada) NÃO mora aqui: é controle, fica na pasta de dados.

Regra 5 (linhagem) e regra 7 (dia de Brasília): o fato com `usina_id` diz por onde a usina ligou (`usina_ligada_por`, o
mesmo texto do `fato_almoxarifado`: a usina do almoxarifado só liga pela de-para do Fracttal, nunca pelo código), e
`quando` / `decidida_em` entram em UTC com "Z" (a hora com outro fuso é convertida; sem fuso é recusada) e o `data_id` é
o dia de Brasília dessa hora.

`NEXUS_ALMOX_INVENTARIO_ARQUIVO` troca o banco por um arquivo (a cópia de prova e os testes, como o `atribuicoes`); teste
sem o arquivo nunca vai à rede (lê vazio e não grava).
"""
import json
import math
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import almoxarifado as A
from . import livros
from .dominios import SITUACAO_INVENTARIO
from .fato_almoxarifado import LIGADA_DE_PARA
from .fatos import CAB_QUALIDADE

LIVRO = "nexus_almoxarifado_inventario"
NOME_LIVRO = "Nexus · inventário do almoxarifado: eventos, régua de mínimo e máximo e curadoria"
ABA_EVENTO, ABA_REGUA, ABA_CURADORIA = "fato_evento_inventario", "fato_regua_minimo", "fato_curadoria_inventario"
ABAS_FATO = (ABA_EVENTO, ABA_REGUA, ABA_CURADORIA)
FATO_DA_ABA = {ABA_EVENTO: "evento_inventario", ABA_REGUA: "regua_minimo", ABA_CURADORIA: "curadoria_inventario"}

# Coluna nova só no FIM (as telas e a gravação leem por nome, mas o livro é lido por posição por quem o abre na planilha).
# A revisão da Task 4 (26/10/2026, antes da 1ª gravação) acrescentou o `usina_ligada_por` ao evento e à régua e quatro
# colunas à curadoria (`data_id`, `id_almoxarifado`, `usina_id`, `usina_ligada_por`): sem elas o fato não cruzava com o
# calendário nem com a usina por ID (regras 3, 5 e 7)
CAB_EVENTO = ["evento_id", "quando", "data_id", "contagem_id", "tipo", "id_almoxarifado", "usina_id", "id_item",
              "codigo", "de_qtd", "para_qtd", "contado_qtd", "movimento_fracttal", "situacao", "lote", "pessoa_id",
              "pessoa_hmac", "dados_cifrados", "usina_ligada_por"]
TIPOS_EVENTO = ("contagem_recebida", "aprovada", "peca_gravada", "conflito", "erro", "peca_tirada",
                "recontagem_pedida", "numero_corrigido", "substituida", "curadoria", "regua_gravada")
CAB_REGUA = ["decidida_em", "data_id", "id_almoxarifado", "usina_id", "id_item", "codigo", "sugestao_min_qtd",
             "sugestao_max_qtd", "recomendado_min_qtd", "recomendado_max_qtd", "acordado_min_qtd", "acordado_max_qtd",
             "gravado_fracttal", "pessoa_id", "pessoa_hmac", "usina_ligada_por"]
CAB_CURADORIA = ["decidida_em", "contagem_id", "chave_linha", "decisao", "id_item", "codigo_criado", "pessoa_id",
                 "pessoa_hmac", "dados_cifrados", "data_id", "id_almoxarifado", "usina_id", "usina_ligada_por"]
# a lista fechada da decisão (regra 4: valor fora do domínio não entra): cadastrar a peça no Fracttal, "é a peça X"
# (o fora do catálogo que é uma peça que já existe), confirmar o que o técnico escolheu no genérico, descartar
DECISOES_CURADORIA = ("cadastrar", "e_a_peca", "confirmar", "descartar")
# por onde a usina do almoxarifado liga: só a de-para do Fracttal (o local "Cliente - Usina - UF"), o mesmo texto do
# `fato_almoxarifado`; o código da usina pode ser de dois clientes e nunca liga
USINA_LIGADA_POR = (LIGADA_DE_PARA,)
CABS = {ABA_EVENTO: CAB_EVENTO, ABA_REGUA: CAB_REGUA, ABA_CURADORIA: CAB_CURADORIA}
CAB_ATUALIZACAO = ["gerado_em", "maquina", "duracao_s", "linhas", "como_ler"]
COMO_LER = ("as três abas de fato só crescem: o estado de cada contagem sai dos eventos na ordem da gravação; a régua vale "
            "a última decisão de cada almoxarifado e peça; a curadoria, a última de cada contagem e linha")
LIVRO_ORIGEM = "o Nexus é a fonte: a revisão, a gravação e a curadoria do inventário (PCM → Almoxarifado)"

TTL_S = 120
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}
_GERACAO = [0]      # sobe a cada gravação (sob a trava): a leitura lenta vê que a cópia dela já nasceu velha

# o jeito de cada coluna entrar: ID do Fracttal e tipo são texto (o 5001 vira "5001", nunca 5001.0 na ida e volta pela
# API), o ID do cadastro é inteiro, a quantidade é número, e o indicador é 1/0
_TEXTOS = frozenset({"evento_id", "contagem_id", "chave_linha", "id_almoxarifado", "id_item", "codigo", "codigo_criado",
                     "movimento_fracttal", "tipo", "decisao", "situacao", "pessoa_hmac", "quando", "decidida_em",
                     "usina_ligada_por"})
_INTEIROS = frozenset({"data_id", "usina_id", "pessoa_id", "lote"})
_INDICADORES = frozenset({"gravado_fracttal"})
_SIM, _NAO = ("1", "true", "sim", "s"), ("0", "false", "nao", "não", "n")
# o que cada coluna de texto aceita (nada que caiba uma frase): o código da pessoa é o `codigo_da_pessoa` (24
# hexadecimais minúsculos), o ID do Fracttal só tem dígitos (o `movimento_fracttal` é o folio que ele devolve), o ID opaco
# (do módulo ou do App) não leva espaço, e o código da peça é o do cadastro do Fracttal (curto)
_RE_HMAC = re.compile(r"[0-9a-f]{24}")
_RE_DIGITOS = re.compile(r"[0-9]{1,20}")
_RE_ID_OPACO = re.compile(r"\S{1,80}")
_IDS_DO_FRACTTAL = frozenset({"id_item", "id_almoxarifado", "movimento_fracttal"})
_IDS_OPACOS = frozenset({"evento_id", "contagem_id", "chave_linha"})
_CODIGOS = frozenset({"codigo", "codigo_criado"})
_CODIGO_MAX = 60


class Recusada(ValueError):
    """Nada foi gravado (ou nada foi lido): o texto diz por quê, para a tela mostrar. As telas e a gravação em segundo
    plano do inventário (nexus/pcm/inventario) importam esta exceção daqui."""


class LeituraIncompleta(RuntimeError):
    """A leitura de uma aba voltou com menos linhas do que a listagem do banco diz que ela tem."""


def _relogio() -> float:
    return time.time()


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _maquina() -> str:
    return "servidor" if os.name != "nt" else "pc"


def _vazio(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _utc(iso, coluna: str) -> datetime:
    """A hora em UTC. O App e o servidor falam UTC e o cadastro, Brasília; hora SEM fuso é ambígua e não entra (a decisão das
    23:30 de Brasília seria o dia seguinte para quem a lesse como UTC)."""
    try:
        d = datetime.fromisoformat(str(iso).strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{coluna} fora do formato (AAAA-MM-DDTHH:MM:SSZ, hora UTC): {str(iso)[:30]}") from None
    if d.tzinfo is None:
        raise ValueError(f"{coluna} sem fuso (use UTC com Z, ou o deslocamento, como -03:00): {str(iso)[:30]}")
    return d.astimezone(timezone.utc)


def _dia_de_brasilia(d: datetime) -> int:
    """O dia de Brasília (AAAAMMDD) de uma hora UTC: 02:30Z ainda é o dia anterior aqui (regra 7)."""
    return int(d.astimezone(_BRT).strftime("%Y%m%d"))


# ── o livro: o banco, ou um arquivo na cópia de prova ─────────────────────────────────────────────────────────
def _arquivo_local(cfg) -> Path | None:
    p = cfg.get("NEXUS_ALMOX_INVENTARIO_ARQUIVO")
    return Path(p) if p else None


def _banco(cfg):
    from ..cadastro.ligacoes import BASE_API
    base = str(cfg.get("GRIDCO_DB_API") or BASE_API).rstrip("/")
    sessao = None
    try:
        from flask import current_app
        sessao = current_app.extensions.get("nexus_dados_sessao")
    except RuntimeError:            # fora de um pedido (a ferramenta da foto): sessão própria
        pass
    if sessao is None:
        import requests
        sessao = requests.Session()
    return base, sessao


def _ler_cru(cfg) -> dict:
    """{aba: [linhas]} das três abas de fato, lidas agora. Livro que ainda não existe = vazio; erro de leitura sobe.
    Teste sem o arquivo nunca vai à rede (vale vazio).

    No banco, cada aba lida é conferida com o `row_count` da listagem (revisão de 26/10/2026): página que volta curta daria
    um livro menor do que o do banco, e a gravação de UMA linha o levaria de volta ao tamanho que o `so_cresce` aceita,
    apagando as últimas (as Tasks 6 a 8 derivam do livro o que já foi gravado no Fracttal). Sem o `row_count`, segue."""
    loc = _arquivo_local(cfg)
    if loc is not None:
        try:
            d = json.loads(loc.read_text(encoding="utf-8"))
        except FileNotFoundError:
            d = {}
        return {a: [dict(x) for x in d.get(a) or []] for a in ABAS_FATO}
    if cfg.get("TESTING"):
        return {a: [] for a in ABAS_FATO}
    base, sessao = _banco(cfg)
    r = sessao.get(f"{base}/api/sheets", timeout=60)
    r.raise_for_status()
    listadas = {x["sheet_name"]: x for x in r.json() if x.get("workbook_key") == LIVRO}
    out = {}
    for a in ABAS_FATO:
        if a not in listadas:
            out[a] = []
            continue
        lidas = list(livros._linhas(base, sessao, listadas[a]["id"]))
        esperadas = livros._int(listadas[a].get("row_count"))
        if esperadas is not None and len(lidas) < esperadas:
            raise LeituraIncompleta(f"{a}: li {len(lidas)} linhas e o banco diz {esperadas}")
        out[a] = lidas
    return out


def _conferir_destino(cfg) -> None:
    """Para onde a gravação iria, conferido ANTES de ler e de montar qualquer linha. Teste sem o arquivo nunca grava no
    banco de verdade."""
    if _arquivo_local(cfg) is not None:
        return
    if cfg.get("TESTING"):
        raise Recusada("Este Nexus está em teste e sem o arquivo do livro do inventário (NEXUS_ALMOX_INVENTARIO_ARQUIVO): "
                       "nada foi gravado.")
    if not cfg.get("GRIDCO_SQL_TOKEN"):
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN): nada foi gravado.")


def _gravar_cru(cfg, cru: dict, q: list, atualizacao: list) -> None:
    """Troca o livro inteiro (as cinco abas) e confere: `livros.publicar` relê cada aba e compara a contagem. Na cópia de
    prova, o arquivo (só as três de fato; a qualidade é do banco)."""
    corpo = {a: [[None if _vazio(x.get(c)) else x.get(c) for c in CABS[a]] for x in cru[a]] for a in ABAS_FATO}
    loc = _arquivo_local(cfg)
    if loc is not None:
        loc.parent.mkdir(parents=True, exist_ok=True)
        tmp = loc.with_suffix(".tmp")
        tmp.write_text(json.dumps({a: [dict(zip(CABS[a], l)) for l in corpo[a]] for a in ABAS_FATO},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(loc)
        return
    tabelas = {a: (list(CABS[a]), corpo[a]) for a in ABAS_FATO}
    tabelas["qualidade"] = (list(CAB_QUALIDADE), q)
    tabelas["atualizacao"] = (list(CAB_ATUALIZACAO), [atualizacao])
    base, sessao = _banco(cfg)
    try:
        livros.publicar(LIVRO, NOME_LIVRO, tabelas, base=base, token=cfg["GRIDCO_SQL_TOKEN"], sessao=sessao)
    except livros.GravacaoRecusada as ex:
        # a trava do livro que só cresce (a listagem do banco veio incompleta ou a aba encolheria): nada foi trocado
        raise Recusada("O banco devolveu a lista do inventário incompleta ou menor do que já tinha: nada foi gravado, "
                       "para não apagar o histórico. Tente de novo em instantes.") from ex


def _copia(abas: dict) -> dict:
    """As linhas copiadas, uma a uma (são dicts planos): quem recebe pode mexer na sua sem estragar a cópia guardada."""
    return {a: [dict(x) for x in l] for a, l in abas.items()}


def ler(cfg, forcar: bool = False) -> dict:
    """{aba: [linhas]} das três abas de fato, na ordem da gravação, guardadas por 2 minutos (a lista das contagens e a
    tela abrem muitas vezes; a gravação renova a cópia). Cada chamada recebe cópias das linhas. Leitura que falha levanta
    `Recusada` (nunca devolve vazio no lugar do que não conseguiu ler: a contagem já gravada apareceria como nova).

    A cópia só é renovada sob a trava e se nenhuma gravação terminou durante a leitura: uma leitura lenta não põe o livro
    velho por cima do que a gravação acabou de guardar (nesse caso devolve o da gravação)."""
    chave = str(_arquivo_local(cfg) or "banco")
    g = _CACHE.get(chave)
    if g and not forcar and _relogio() - g["lido_em"] < TTL_S:
        return _copia(g["abas"])
    antes = _GERACAO[0]
    try:
        abas = _ler_cru(cfg)
    except Exception as ex:      # noqa: BLE001 — banco fora, rede, arquivo ilegível, leitura curta: a tela diz
        raise Recusada(f"Não consegui ler o livro do inventário no banco ({type(ex).__name__}): tente de novo em "
                       "instantes.") from ex
    with _TRAVA:
        if _GERACAO[0] == antes or chave not in _CACHE:
            _CACHE[chave] = {"abas": abas, "lido_em": _relogio()}
        return _copia(_CACHE[chave]["abas"])


def limpar() -> None:
    _CACHE.clear()


# ── o texto livre, cifrado ────────────────────────────────────────────────────────────────────────────────────
def _cofre(cfg):
    chave = cfg.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        return None
    from ..cadastro.cifra import Cofre
    return Cofre(chave)


def _ctx(aba: str, l: dict) -> str:
    """O contexto da cifra: amarra o texto à linha (quem tem o token de escrita da API não move o motivo de uma linha
    para a de outra, porque a decifração falha)."""
    t = lambda c: "" if l.get(c) is None else str(l.get(c)).strip()      # noqa: E731
    if aba == ABA_EVENTO:
        return f"almox/inventario/evento/{t('evento_id')}"
    return f"almox/inventario/curadoria/{t('contagem_id')}/{t('chave_linha')}/{t('decidida_em')}"


def decifrar(cfg, aba: str, linha: dict) -> dict:
    """O `dados` de uma linha do livro (o motivo do PCM), decifrado aqui no Nexus. Sem a chave do cadastro, sem texto na
    linha, com a cifra de outra chave ou de outra linha: {} (a tela mostra a linha sem o motivo)."""
    texto = "" if linha.get("dados_cifrados") is None else str(linha.get("dados_cifrados")).strip()
    if not texto or aba not in (ABA_EVENTO, ABA_CURADORIA):
        return {}
    try:
        cofre = _cofre(cfg)
        return json.loads(cofre.decifrar(texto, _ctx(aba, linha))) if cofre else {}
    except Exception:    # noqa: BLE001 — cifra de outra chave ou linha mexida: sem o texto
        return {}


# ── a linha que entra ─────────────────────────────────────────────────────────────────────────────────────────
def _como_texto(v) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _texto(c: str, t: str) -> str:
    """O texto de uma coluna de texto, conferido pela forma que ela aceita (ver os `_RE_*` acima)."""
    if c == "pessoa_hmac" and not _RE_HMAC.fullmatch(t):
        raise ValueError("pessoa_hmac é o código da pessoa (24 hexadecimais minúsculos, o `codigo_da_pessoa`): nome, "
                         f"e-mail ou outro texto não entra ({t[:12]}...)")
    if c in _IDS_DO_FRACTTAL:
        t = A._id(t)
        if not _RE_DIGITOS.fullmatch(t):
            raise ValueError(f"{c} é um ID do Fracttal (só dígitos): {t[:20]}")
    if c in _IDS_OPACOS and not _RE_ID_OPACO.fullmatch(t):
        raise ValueError(f"{c} é um ID (sem espaço, até 80 caracteres): {t[:20]}")
    if c in _CODIGOS and len(t) > _CODIGO_MAX:
        raise ValueError(f"{c} é o código da peça no Fracttal (até {_CODIGO_MAX} caracteres): {t[:20]}...")
    if c == "situacao" and t not in SITUACAO_INVENTARIO:
        raise ValueError(f"situacao fora da lista ({', '.join(SITUACAO_INVENTARIO)}): {t[:30]}")
    if c == "usina_ligada_por" and t not in USINA_LIGADA_POR:
        raise ValueError(f"usina_ligada_por fora da lista ({', '.join(USINA_LIGADA_POR)}): {t[:30]}")
    return t


def _inteiro(c: str, v) -> int:
    try:
        n = float(str(v).strip().replace(",", "."))
        if isinstance(v, bool) or not math.isfinite(n) or not n.is_integer():
            raise ValueError
        return int(n)
    except ValueError:
        raise ValueError(f"{c} precisa ser um ID inteiro (o nome não liga: não se chuta): {str(v)[:20]}") from None


def _quantidade(c: str, v) -> int | float:
    n = A.contado(v)
    if n is None:
        raise ValueError(f"{c} precisa ser um número (em branco é vazio, o 0 digitado é 0): {str(v)[:20]}")
    return int(n) if n.is_integer() else n


def _indicador(c: str, v) -> int:
    t = str(v).strip().lower()
    if t in _SIM:
        return 1
    if t in _NAO:
        return 0
    raise ValueError(f"{c} é 1 ou 0 (sim ou não): {str(v)[:20]}")


def _preparar(cfg, aba: str, x: dict, agora: datetime) -> dict:
    """A linha do livro a partir do que o chamador trouxe. Põe o que é do módulo (o ID e a hora do evento, o dia de
    Brasília) quando o chamador não trouxe; recusa (`ValueError`, erro de quem chama) a coluna que o livro não tem, o
    `dados_cifrados` pronto, o e-mail, o valor fora da lista ou da forma da coluna, a usina sem a linhagem e o `data_id`
    que não é o dia de Brasília da hora; cifra o `dados`."""
    cab = CABS[aba]
    sobra = sorted(set(x) - set(cab) - {"dados"})
    if sobra:
        raise ValueError(f"coluna que o livro do inventário não tem: {', '.join(sobra)}. Texto livre (o motivo) vai em "
                         "`dados`, que o módulo cifra; pessoa vai como pessoa_id e pessoa_hmac, nunca nome nem e-mail")
    if not _vazio(x.get("dados_cifrados")):
        raise ValueError("dados_cifrados não se passa pronto: o texto livre (o motivo) vai em `dados` e o módulo o cifra; "
                         "texto em claro nessa coluna seria lido por quem abre o banco (a API é aberta)")
    if x.get("dados") and "dados_cifrados" not in cab:
        raise ValueError(f"a aba {aba} não tem onde cifrar texto livre (`dados`): ela é só número")
    linha = {}
    for c in cab:
        v = x.get(c)
        if _vazio(v):
            linha[c] = None
        elif c in _TEXTOS:
            linha[c] = _texto(c, _como_texto(v))
        elif c in _INTEIROS:
            linha[c] = _inteiro(c, v)
        elif c in _INDICADORES:
            linha[c] = _indicador(c, v)
        elif c.endswith("_qtd"):
            linha[c] = _quantidade(c, v)
        else:
            linha[c] = v
    for c, v in linha.items():
        if isinstance(v, str) and "@" in v:
            raise ValueError(f"e-mail em coluna em claro ({c}): a pessoa vai como pessoa_hmac (a API do banco é aberta)")
    # a usina diz por onde ligou (regra 5): os dois juntos ou nenhum, nunca o ID sem a linhagem nem o contrário
    if (linha["usina_id"] is None) != (linha["usina_ligada_por"] is None):
        raise ValueError("usina_id e usina_ligada_por vão juntos: o fato diz por onde ligou a usina (regra 5), e sem "
                         "usina a linhagem fica vazia (nunca se chuta)")
    quando = "quando" if aba == ABA_EVENTO else "decidida_em"
    if aba == ABA_EVENTO:
        if linha["tipo"] not in TIPOS_EVENTO:
            raise ValueError(f"tipo de evento que o inventário não conhece: {str(linha['tipo'])[:30]}")
        linha["evento_id"] = linha["evento_id"] or f"ev-{uuid.uuid4().hex[:16]}"
    elif aba == ABA_REGUA:
        for c in ("id_almoxarifado", "id_item"):
            if not linha[c]:
                raise ValueError(f"{c} faltou: a régua é de uma peça num almoxarifado")
    else:
        for c in ("contagem_id", "chave_linha"):
            if not linha[c]:
                raise ValueError(f"{c} faltou: a decisão é sobre uma linha de uma contagem")
        if linha["decisao"] not in DECISOES_CURADORIA:
            raise ValueError(f"decisao da curadoria que o inventário não conhece: {str(linha['decisao'])[:30]}")
    hora = agora if linha[quando] is None else _utc(linha[quando], quando)
    linha[quando] = _iso(hora)
    dia = _dia_de_brasilia(hora)
    if linha["data_id"] is None:
        linha["data_id"] = dia
    elif linha["data_id"] != dia:
        raise ValueError(f"data_id {linha['data_id']} não é o dia de Brasília de {quando} ({linha[quando]}, dia {dia}): "
                         "deixe o módulo preencher")
    if x.get("dados"):
        cofre = _cofre_ou_recusar(cfg)
        linha["dados_cifrados"] = cofre.cifrar(json.dumps(x["dados"], ensure_ascii=False), _ctx(aba, linha))
    return linha


def _cofre_ou_recusar(cfg):
    from ..cadastro.cifra import CifraErro
    try:
        cofre = _cofre(cfg)
    except CifraErro as ex:
        raise Recusada(f"A chave do cadastro deste Nexus não vale ({ex}): o motivo vai cifrado, e sem ela nada é "
                       "gravado.") from None
    if cofre is None:
        raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): o motivo vai cifrado, e sem ela "
                       "nada é gravado.")
    return cofre


# ── a qualidade ───────────────────────────────────────────────────────────────────────────────────────────────
def _pct(n: int, total: int):
    return round(100.0 * n / total, 1) if total else None


def linha_qualidade(aba: str, linhas: list[dict], agora: str) -> list:
    """A linha da aba `qualidade` no cabeçalho da casa (`fatos.CAB_QUALIDADE`), preenchida pelo nome da coluna: quanto do
    fato liga a data, a usina e a pessoa (a Governança mostra as barras), quantas usinas ligaram pela de-para (a única
    linhagem que o almoxarifado tem) e, no `extra`, quantos de cada tipo de evento ou decisão (só número e texto: a tela
    não mostra o que é lista)."""
    cab, n = CABS[aba], len(linhas)
    com = {c: sum(1 for l in linhas if not _vazio(l.get(c))) for c in ("data_id", "usina_id", "pessoa_id") if c in cab}
    quando = "quando" if aba == ABA_EVENTO else "decidida_em"
    if aba == ABA_EVENTO:
        extra = {f"tipo_{t}": sum(1 for l in linhas if l.get("tipo") == t) for t in TIPOS_EVENTO}
    elif aba == ABA_CURADORIA:
        extra = {f"decisao_{d}": sum(1 for l in linhas if l.get("decisao") == d) for d in DECISOES_CURADORIA}
    else:
        extra = {"gravadas_no_fracttal": sum(1 for l in linhas if str(l.get("gravado_fracttal")).strip() in ("1", "1.0"))}
    por_de_para = sum(1 for l in linhas if l.get("usina_ligada_por") == LIGADA_DE_PARA)
    valores = {"fato": FATO_DA_ABA[aba], "livro_origem": LIVRO_ORIGEM, "linhas": n,
               "com_data": com.get("data_id"), "com_usina": com.get("usina_id"), "com_pessoa": com.get("pessoa_id"),
               "pct_data": _pct(com["data_id"], n) if "data_id" in com else None,
               "pct_usina": _pct(com["usina_id"], n) if "usina_id" in com else None,
               "pct_pessoa": _pct(com["pessoa_id"], n) if "pessoa_id" in com else None,
               "usina_por_de_para": por_de_para, "usina_por_codigo": 0,
               "origem_atualizada_em": max((str(l.get(quando) or "") for l in linhas), default=""), "gerado_em": agora,
               "extra": json.dumps({k: v for k, v in extra.items() if v}, ensure_ascii=False, separators=(",", ":"))}
    return [valores.get(c) for c in CAB_QUALIDADE]


# ── acrescentar ───────────────────────────────────────────────────────────────────────────────────────────────
def acrescentar(cfg, aba: str, linhas: list[dict]) -> None:
    """Acrescenta `linhas` à aba e grava o livro. Relê o livro inteiro agora (a gravação o troca inteiro: sem reler, a
    segunda gravação apagaria a primeira), junta, e grava as cinco abas com a qualidade e a atualização. `Recusada` com o
    motivo quando não dá (o banco não deixa reler, ou a leitura voltou menor do que a listagem diz, o evento já está, falta
    a chave de gravação ou a do cadastro): nada foi gravado. `ValueError` quando quem chama errou a linha (aba ou coluna
    que não existe, `dados_cifrados` pronto, tipo, situação ou decisão fora da lista, ID ou número que não é, código da
    pessoa que não é o código, e-mail, usina sem a linhagem, `data_id` que não é o dia de Brasília da hora): antes de ler ou
    gravar qualquer coisa, o lote inteiro vale ou nada vale.

    Cada linha é um dict pelas colunas do `CAB_*` da aba, mais `dados` (o texto livre, só no evento e na curadoria, que o
    módulo cifra em `dados_cifrados`). O que o módulo põe quando falta: o `evento_id`, a hora (`quando` ou `decidida_em`,
    UTC) e o `data_id` (o dia de Brasília dessa hora)."""
    if aba not in ABAS_FATO:
        raise ValueError(f"aba que o livro do inventário não tem: {str(aba)[:40]}")
    if not linhas:
        return
    _conferir_destino(cfg)
    t0, agora = _relogio(), _agora()
    novas = [_preparar(cfg, aba, x, agora) for x in linhas]
    with _TRAVA:
        try:
            cru = _ler_cru(cfg)
        except Exception as ex:      # noqa: BLE001
            raise Recusada(f"Não consegui ler o livro do inventário no banco ({type(ex).__name__}): nada foi gravado, "
                           "para não apagar o que já está lá.") from ex
        if aba == ABA_EVENTO:
            vistos = {str(x.get("evento_id")) for x in cru[ABA_EVENTO]}
            for n in novas:
                if n["evento_id"] in vistos:
                    raise Recusada(f"O evento {n['evento_id']} já está no livro do inventário: nada foi gravado.")
                vistos.add(n["evento_id"])
        cru[aba] = cru[aba] + novas
        iso = _iso(agora)
        q = [linha_qualidade(a, cru[a], iso) for a in ABAS_FATO]
        total = sum(len(cru[a]) for a in ABAS_FATO)
        _gravar_cru(cfg, cru, q, [iso, _maquina(), round(_relogio() - t0, 1), total, COMO_LER])
        # o que acabou de ser lido (e gravado) vale como a leitura de agora: a tela não volta ao banco em seguida; e a
        # leitura que estava em curso sabe, pela geração, que a dela já nasceu velha
        _GERACAO[0] += 1
        _CACHE[str(_arquivo_local(cfg) or "banco")] = {"abas": cru, "lido_em": _relogio()}
