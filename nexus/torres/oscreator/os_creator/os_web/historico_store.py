"""A lista do Histórico guardada e renovada sem repetir o Fracttal (19/10/2026).

Levi, 19/10/2026: "o que causa essa busca de 2.000, todas as buscas são necessárias?" e "tem como atualizar só o dia
somando com o que já carregou ou tem que carregar tudo de novo?". Medido no código e no Raio-X do servidor (17:15): a
Visão COS (e o "Criado por: Todos") pede ao Fracttal as OS de todos os criadores em 30 dias, que passam de 2.000; cada
carga são ~26 pedidos (10 páginas de 200 OS e 16 lotes com as tarefas de 130 OS), e a página de 2.000 linhas levou 43 s
para ser montada no servidor. A mesma lista era buscada de novo para cada pessoa (a memória era por pessoa), a cada
atualização automática de 10 min de cada aba aberta (que passava por cima da memória) e a cada ↻.

Aqui:
- `ler` devolve a lista guardada NA HORA; vencida (`TTL_S`), ela se renova por trás, uma renovação por vez: só as OS
  criadas desde a mais nova guardada (`buscar_novas`, 1 ou 2 pedidos) e, passado `INTEIRA_S`, a lista inteira de novo
  (o status, o responsável e a data fim das antigas: a OS do Fracttal não diz quando foi alterada, conferido no REST em
  19/10/2026, então o que mudou numa OS antiga só aparece na busca inteira);
- sem lista guardada, ou com o ↻ (`forcar`), a busca inteira é feita NA HORA, uma por vez por lista: quem chega no meio
  espera a mesma (até `ESPERA_S`); o ↻ dentro de `REFRESCO_MIN_S` da última inteira só busca as novas;
- quem decide a CHAVE é quem chama (a rota): a lista de "Todos" pode ser uma só para quem vê o mesmo universo no
  Fracttal (`mesma_visao`); a de cada pessoa ("criadas por mim", "atribuídas a mim") segue por pessoa;
- a lista guarda o HTML das linhas por versão (`html_das_linhas`): as 2.000 linhas são montadas uma vez por versão, e
  não a cada pedido.
Erro do Fracttal não apaga a lista guardada: a tela segue com ela, com a hora dela.
"""
import itertools
import threading
import time
from datetime import datetime, timedelta

TTL_S = 180                # passou disso, a tela abre com a lista guardada e ela se renova por trás
INTEIRA_S = 600            # a cada 10 min (e no ↻), a lista inteira de novo no Fracttal
REFRESCO_MIN_S = 60        # o ↻ dentro disso da última inteira só busca as novas
MARGEM_NOVAS_S = 600       # as "novas" vêm desde a mais nova guardada menos isto (o relógio do Fracttal e o atraso)
ESPERA_S = 120             # quem chega com a busca inteira em andamento espera ela, até isto
CONFERE_S = 30 * 60        # a conferência de "mesma visão" de uma pessoa vale isto
TOLERANCIA = 0.01          # a mesma visão: o total que o Fracttal dá à pessoa difere do guardado em até 1% (ou 2 OS:
                           # as criadas entre a lista guardada e a conferência)

_LISTAS: dict = {}         # chave -> Lista
_EM_CURSO: dict = {}       # chave -> {"pronto": Event, "lista": Lista | None, "erro": Exception | None}
_CONFERIDOS: dict = {}     # (pessoa, chave) -> (quando, mesma visão?)
_TRAVA = threading.Lock()
_VERSOES = itertools.count(1)


class Lista:
    """Uma lista do Histórico: as linhas (o formato do `api.list_minhas_os`), o `info` (total e teto), quando veio a
    última busca inteira e a última atualização, e a versão (muda a cada atualização; o HTML guardado é por versão)."""

    def __init__(self, linhas, info, inteira_em, atualizada_em):
        self.linhas, self.info = list(linhas), dict(info or {})
        self.inteira_em, self.atualizada_em = inteira_em, atualizada_em
        self.versao = next(_VERSOES)
        self.html: dict = {}
        self.criada_em = time.time()      # a hora (do relógio) desta versão, que a tela mostra


def limpar() -> None:
    with _TRAVA:
        _LISTAS.clear()
        _EM_CURSO.clear()
        _CONFERIDOS.clear()


def guardada(chave):
    return _LISTAS.get(chave)


def _relogio():
    return time.monotonic()


def ler(chave, buscar_inteira, buscar_novas, *, forcar=False, por_tras=None):
    """(a Lista, como veio): "memoria", "inteira" ou "novas". `buscar_inteira()` e `buscar_novas(desde_iso)` devolvem
    (linhas, info); `por_tras(fn)` roda `fn` fora do pedido (com a sessão do Fracttal de quem pediu); sem ele, a
    renovação não acontece por trás (a próxima visita vencida tenta de novo)."""
    agora = _relogio()
    g = _LISTAS.get(chave)
    if g is None:
        return _inteira(chave, buscar_inteira), "inteira"
    if forcar:
        if agora - g.inteira_em < REFRESCO_MIN_S:
            return _novas(chave, buscar_novas), "novas"
        return _inteira(chave, buscar_inteira), "inteira"
    if agora - g.atualizada_em >= TTL_S and por_tras is not None and chave not in _EM_CURSO:
        if agora - g.inteira_em >= INTEIRA_S:
            por_tras(lambda: _por_tras(_inteira, chave, buscar_inteira))
        else:
            por_tras(lambda: _por_tras(_novas, chave, buscar_novas))
    return g, "memoria"


def _por_tras(fn, chave, buscar):
    try:
        fn(chave, buscar)
    except Exception:           # noqa: BLE001 — por trás: a lista guardada segue, com a hora dela
        pass


def _uma_vez(chave, fazer):
    """`fazer()` -> Lista, uma vez por chave: quem chega enquanto ela roda espera a mesma (até ESPERA_S) e recebe a
    mesma lista, ou o mesmo erro. Passado o prazo, recebe a guardada, se houver."""
    with _TRAVA:
        em = _EM_CURSO.get(chave)
        dono = em is None
        if dono:
            em = _EM_CURSO[chave] = {"pronto": threading.Event(), "lista": None, "erro": None}
    if not dono:
        em["pronto"].wait(ESPERA_S)
        if em["lista"] is not None:
            return em["lista"]
        if em["erro"] is not None and _LISTAS.get(chave) is None:
            raise em["erro"]
        g = _LISTAS.get(chave)
        if g is None:
            raise TimeoutError("a busca do Histórico ainda está em andamento: atualize em instantes")
        return g
    try:
        nova = fazer()
        em["lista"] = nova
        with _TRAVA:
            _LISTAS[chave] = nova
        return nova
    except Exception as e:      # noqa: BLE001 — quem espera recebe o mesmo erro
        em["erro"] = e
        raise
    finally:
        with _TRAVA:
            _EM_CURSO.pop(chave, None)
        em["pronto"].set()


def _inteira(chave, buscar_inteira):
    def fazer():
        linhas, info = buscar_inteira()
        agora = _relogio()
        return Lista(linhas, info, agora, agora)
    return _uma_vez(chave, fazer)


def desde(linhas, margem_s=MARGEM_NOVAS_S) -> str | None:
    """De quando pedir as novas: a data de criação mais nova guardada menos a margem (ISO, como o Fracttal grava)."""
    datas = [str(d.get("data") or "")[:19] for d in linhas if d.get("data")]
    if not datas:
        return None
    try:
        mais_nova = datetime.fromisoformat(max(datas))
    except ValueError:
        return None
    return (mais_nova - timedelta(seconds=margem_s)).isoformat(timespec="seconds")


def juntar(guardadas, novas, cap) -> list:
    """As novas por cima das guardadas (a mesma OS fica com a linha nova), da mais nova para a mais velha, até o teto: a
    lista continua sendo "as `cap` OS mais novas do período"."""
    por_id = {d.get("id"): d for d in guardadas}
    for d in novas:
        por_id[d.get("id")] = d
    out = sorted(por_id.values(), key=lambda d: (str(d.get("data") or ""), d.get("id") or 0), reverse=True)
    return out[:cap] if cap else out


def _novas(chave, buscar_novas):
    def fazer():
        g = _LISTAS.get(chave)
        if g is None:
            raise LookupError("sem lista guardada para somar as novas")
        de = desde(g.linhas)
        if de is None:
            raise LookupError("a lista guardada não tem data de criação")
        novas, info = buscar_novas(de)
        cap = int(g.info.get("cap") or 0)
        ja = {d.get("id") for d in g.linhas}
        # o total do período cresce com as que não estavam (as do teto cortadas continuam contadas, para o aviso)
        total = int(g.info.get("total") or 0) + len({d.get("id") for d in novas} - ja)
        return Lista(juntar(g.linhas, novas, cap), dict(g.info, total=total), g.inteira_em, _relogio())
    return _uma_vez(chave, fazer)


def mesma_visao(pessoa, chave, total_da_pessoa) -> bool:
    """A pessoa vê no Fracttal o mesmo universo da lista guardada em `chave`? `total_da_pessoa()` é o total que o
    Fracttal dá a ela com os mesmos filtros (1 pedido, na sessão dela). Sem lista guardada: sim (a dela vira a de todos).
    O resultado vale CONFERE_S por pessoa e lista; o Fracttal fora conta como "não" (ela fica com a dela)."""
    g = _LISTAS.get(chave)
    if g is None:
        return True
    guardado = int(g.info.get("total") or 0)
    agora = _relogio()
    k = (pessoa, chave)
    c = _CONFERIDOS.get(k)
    if c and agora - c[0] < CONFERE_S:
        return c[1]
    try:
        dela = int(total_da_pessoa())
    except Exception:           # noqa: BLE001 — sem conferir, ela fica com a lista dela
        return False
    ok = abs(dela - guardado) <= max(2, TOLERANCIA * max(dela, guardado))
    with _TRAVA:
        _CONFERIDOS[k] = (agora, ok)
        if len(_CONFERIDOS) > 2000:
            for kk in sorted(_CONFERIDOS, key=lambda x: _CONFERIDOS[x][0])[:len(_CONFERIDOS) - 2000]:
                _CONFERIDOS.pop(kk, None)
    return ok


def html_das_linhas(lista, chave_html, montar) -> str:
    """O HTML das linhas desta versão da lista para `chave_html` (a visão e a busca), montado uma vez."""
    h = lista.html.get(chave_html)
    if h is None:
        h = lista.html[chave_html] = montar()
    return h
