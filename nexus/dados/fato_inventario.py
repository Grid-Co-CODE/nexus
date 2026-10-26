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
troca o livro inteiro, então `acrescentar` RELÊ o livro antes (leitura que falha não grava: `Recusada`) e grava todas as
abas, com a `qualidade` e a `atualizacao`. Uma gravação por vez neste processo (a gravação em segundo plano e a tela do
PCM escrevem aqui ao mesmo tempo).

Regra 8 (a API do banco tem leitura aberta): nada de nome nem de e-mail em coluna; a pessoa vai como `pessoa_id` (quando o
cadastro a acha) e `pessoa_hmac` (sempre, nunca o e-mail), e o motivo do PCM, que é texto livre, vai só dentro de
`dados_cifrados` (o Cofre do cadastro, amarrado à linha). Quem chama passa `dados={"motivo": ...}` e o módulo cifra; coluna
em claro que o livro não tem, ou e-mail em qualquer coluna, é erro de quem chama (`ValueError`), nunca texto em claro.
O estado do trabalho em andamento (o lote, o ponto de retomada) NÃO mora aqui: é controle, fica na pasta de dados.

`NEXUS_ALMOX_INVENTARIO_ARQUIVO` troca o banco por um arquivo (a cópia de prova e os testes, como o `atribuicoes`); teste
sem o arquivo nunca vai à rede (lê vazio e não grava).
"""
import json
import math
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import almoxarifado as A
from . import livros
from .fatos import CAB_QUALIDADE

LIVRO = "nexus_almoxarifado_inventario"
NOME_LIVRO = "Nexus · inventário do almoxarifado: eventos, régua de mínimo e máximo e curadoria"
ABA_EVENTO, ABA_REGUA, ABA_CURADORIA = "fato_evento_inventario", "fato_regua_minimo", "fato_curadoria_inventario"
ABAS_FATO = (ABA_EVENTO, ABA_REGUA, ABA_CURADORIA)
FATO_DA_ABA = {ABA_EVENTO: "evento_inventario", ABA_REGUA: "regua_minimo", ABA_CURADORIA: "curadoria_inventario"}

CAB_EVENTO = ["evento_id", "quando", "data_id", "contagem_id", "tipo", "id_almoxarifado", "usina_id", "id_item",
              "codigo", "de_qtd", "para_qtd", "contado_qtd", "movimento_fracttal", "situacao", "lote", "pessoa_id",
              "pessoa_hmac", "dados_cifrados"]
TIPOS_EVENTO = ("contagem_recebida", "aprovada", "peca_gravada", "conflito", "erro", "peca_tirada",
                "recontagem_pedida", "numero_corrigido", "substituida", "curadoria", "regua_gravada")
CAB_REGUA = ["decidida_em", "data_id", "id_almoxarifado", "usina_id", "id_item", "codigo", "sugestao_min_qtd",
             "sugestao_max_qtd", "recomendado_min_qtd", "recomendado_max_qtd", "acordado_min_qtd", "acordado_max_qtd",
             "gravado_fracttal", "pessoa_id", "pessoa_hmac"]
CAB_CURADORIA = ["decidida_em", "contagem_id", "chave_linha", "decisao", "id_item", "codigo_criado", "pessoa_id",
                 "pessoa_hmac", "dados_cifrados"]
# a lista fechada da decisão (regra 4: valor fora do domínio não entra): cadastrar a peça no Fracttal, "é a peça X"
# (o fora do catálogo que é uma peça que já existe), confirmar o que o técnico escolheu no genérico, descartar
DECISOES_CURADORIA = ("cadastrar", "e_a_peca", "confirmar", "descartar")
CABS = {ABA_EVENTO: CAB_EVENTO, ABA_REGUA: CAB_REGUA, ABA_CURADORIA: CAB_CURADORIA}
CAB_ATUALIZACAO = ["gerado_em", "maquina", "duracao_s", "linhas", "como_ler"]
COMO_LER = ("as três abas de fato só crescem: o estado de cada contagem sai dos eventos na ordem da gravação; a régua vale "
            "a última decisão de cada almoxarifado e peça; a curadoria, a última de cada contagem e linha")
LIVRO_ORIGEM = "o Nexus é a fonte: a revisão, a gravação e a curadoria do inventário (PCM → Almoxarifado)"

TTL_S = 120
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}

# o jeito de cada coluna entrar: ID do Fracttal e tipo são texto (o 5001 vira "5001", nunca 5001.0 na ida e volta pela
# API), o ID do cadastro é inteiro, a quantidade é número, e o indicador é 1/0
_TEXTOS = frozenset({"evento_id", "contagem_id", "chave_linha", "id_almoxarifado", "id_item", "codigo", "codigo_criado",
                     "movimento_fracttal", "tipo", "decisao", "situacao", "pessoa_hmac", "quando", "decidida_em"})
_INTEIROS = frozenset({"data_id", "usina_id", "pessoa_id", "lote"})
_INDICADORES = frozenset({"gravado_fracttal"})
_SIM, _NAO = ("1", "true", "sim", "s"), ("0", "false", "nao", "não", "n")


class Recusada(ValueError):
    """Nada foi gravado (ou nada foi lido): o texto diz por quê, para a tela mostrar. As telas e a gravação em segundo
    plano do inventário (nexus/pcm/inventario) importam esta exceção daqui."""


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


def _dia_de_brasilia(iso, coluna: str) -> int:
    """O dia de Brasília (AAAAMMDD) de uma hora UTC: o App e o servidor falam UTC, e 02:30Z ainda é o dia anterior aqui
    (regra 7)."""
    try:
        d = datetime.fromisoformat(str(iso).strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{coluna} fora do formato (AAAA-MM-DDTHH:MM:SSZ, hora UTC): {str(iso)[:30]}") from None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
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
    Teste sem o arquivo nunca vai à rede (vale vazio)."""
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
    abas = livros.abas(base, sessao, LIVRO)
    return {a: (list(livros._linhas(base, sessao, abas[a])) if a in abas else []) for a in ABAS_FATO}


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
    return {a: list(l) for a, l in abas.items()}


def ler(cfg, forcar: bool = False) -> dict:
    """{aba: [linhas]} das três abas de fato, na ordem da gravação, guardadas por 2 minutos (a lista das contagens e a
    tela abrem muitas vezes; a gravação renova a cópia). Quem recebe não deve alterar as linhas. Leitura que falha
    levanta `Recusada` (nunca devolve vazio no lugar do que não conseguiu ler: a contagem já gravada apareceria como
    nova)."""
    chave = str(_arquivo_local(cfg) or "banco")
    g = _CACHE.get(chave)
    if g and not forcar and _relogio() - g["lido_em"] < TTL_S:
        return _copia(g["abas"])
    try:
        abas = _ler_cru(cfg)
    except Exception as ex:      # noqa: BLE001 — banco fora, rede, arquivo ilegível: a tela diz
        raise Recusada(f"Não consegui ler o livro do inventário no banco ({type(ex).__name__}): tente de novo em "
                       "instantes.") from ex
    _CACHE[chave] = {"abas": abas, "lido_em": _relogio()}
    return _copia(abas)


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
    e-mail, o valor fora da lista fechada e o ID ou número que não é; cifra o `dados`."""
    cab = CABS[aba]
    sobra = sorted(set(x) - set(cab) - {"dados"})
    if sobra:
        raise ValueError(f"coluna que o livro do inventário não tem: {', '.join(sobra)}. Texto livre (o motivo) vai em "
                         "`dados`, que o módulo cifra; pessoa vai como pessoa_id e pessoa_hmac, nunca nome nem e-mail")
    if x.get("dados") and "dados_cifrados" not in cab:
        raise ValueError(f"a aba {aba} não tem onde cifrar texto livre (`dados`): ela é só número")
    linha = {}
    for c in cab:
        v = x.get(c)
        if _vazio(v):
            linha[c] = None
        elif c in _TEXTOS:
            linha[c] = _como_texto(v)
        elif c in _INTEIROS:
            linha[c] = _inteiro(c, v)
        elif c in _INDICADORES:
            linha[c] = _indicador(c, v)
        elif c.endswith("_qtd"):
            linha[c] = _quantidade(c, v)
        else:
            linha[c] = v
    for c, v in linha.items():
        if c != "dados_cifrados" and isinstance(v, str) and "@" in v:
            raise ValueError(f"e-mail em coluna em claro ({c}): a pessoa vai como pessoa_hmac (a API do banco é aberta)")
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
    linha[quando] = linha[quando] or _iso(agora)
    dia = _dia_de_brasilia(linha[quando], quando)
    if "data_id" in linha and linha["data_id"] is None:
        linha["data_id"] = dia
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
    fato liga a data, a usina e a pessoa (a Governança mostra as barras) e, no `extra`, quantos de cada tipo de evento ou
    decisão (só número e texto: a tela não mostra o que é lista)."""
    cab, n = CABS[aba], len(linhas)
    com = {c: sum(1 for l in linhas if not _vazio(l.get(c))) for c in ("data_id", "usina_id", "pessoa_id") if c in cab}
    quando = "quando" if aba == ABA_EVENTO else "decidida_em"
    extra = {}
    if aba == ABA_EVENTO:
        extra = {f"tipo_{t}": sum(1 for l in linhas if l.get("tipo") == t) for t in TIPOS_EVENTO}
    elif aba == ABA_CURADORIA:
        extra = {f"decisao_{d}": sum(1 for l in linhas if l.get("decisao") == d) for d in DECISOES_CURADORIA}
    else:
        extra = {"gravadas_no_fracttal": sum(1 for l in linhas if str(l.get("gravado_fracttal")).strip() in ("1", "1.0"))}
    valores = {"fato": FATO_DA_ABA[aba], "livro_origem": LIVRO_ORIGEM, "linhas": n,
               "com_data": com.get("data_id"), "com_usina": com.get("usina_id"), "com_pessoa": com.get("pessoa_id"),
               "pct_data": _pct(com["data_id"], n) if "data_id" in com else None,
               "pct_usina": _pct(com["usina_id"], n) if "usina_id" in com else None,
               "pct_pessoa": _pct(com["pessoa_id"], n) if "pessoa_id" in com else None,
               "origem_atualizada_em": max((str(l.get(quando) or "") for l in linhas), default=""), "gerado_em": agora,
               "extra": json.dumps({k: v for k, v in extra.items() if v}, ensure_ascii=False, separators=(",", ":"))}
    return [valores.get(c) for c in CAB_QUALIDADE]


# ── acrescentar ───────────────────────────────────────────────────────────────────────────────────────────────
def acrescentar(cfg, aba: str, linhas: list[dict]) -> None:
    """Acrescenta `linhas` à aba e grava o livro. Relê o livro inteiro agora (a gravação o troca inteiro: sem reler, a
    segunda gravação apagaria a primeira), junta, e grava as cinco abas com a qualidade e a atualização. `Recusada` com o
    motivo quando não dá (o banco não deixa reler, o evento já está, falta a chave de gravação ou a do cadastro): nada
    foi gravado. `ValueError` quando quem chama errou a linha (aba ou coluna que não existe, tipo fora da lista, ID ou
    número que não é, e-mail): antes de ler ou gravar qualquer coisa, o lote inteiro vale ou nada vale.

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
        # o que acabou de ser lido (e gravado) vale como a leitura de agora: a tela não volta ao banco em seguida
        _CACHE[str(_arquivo_local(cfg) or "banco")] = {"abas": cru, "lido_em": _relogio()}
