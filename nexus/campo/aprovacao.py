"""Aprovação de OS do Nexus: a fila de verificação do painel do App (Levi aprovou a proposta em 04/10/2026).

Quem calcula é a cópia das regras do App (regras_app.py): o mesmo `_fila_supervisao` da rota gestao/supervisao/fila,
com os mesmos grupos ("Evidência completa", "Precisa do seu olho", "Fechadas fora do App") e os mesmos números. A fila
crua vem do Fracttal (OS em revisão), lida pelo Nexus só com GET e um pedido por vez (fracttal.py); a nota do
registro é a do livro que o App grava no banco (fonte_pg.py). Aprovar, aprovar em lote e devolver continuam no App.

**A tela nunca espera o Fracttal** (Levi, 05/10/2026: "Quando clico no botão 'Aprovação de OS' fica carregando
infinito"). Medido no log: a fila tem 55 páginas (5.495 tarefas), lida uma página por vez leva 1 min ou mais, e à
noite o Fracttal recusava (429) de 4 a 26 páginas; a leitura incompleta não ficava guardada e cada visita recomeçava
do zero. Agora a fila é relida EM SEGUNDO PLANO, uma leitura por vez, quando a última tem mais de 10 min; a tela mostra
a última fila boa e quando ela foi lida. Depois de uma recusa, 5 min sem tentar (a cota é da empresa inteira).
"""
import contextlib
import threading
import time
from datetime import datetime, timedelta, timezone

from flask import current_app, has_app_context

from . import fracttal, leitura, regras_app, tabelas
from .leitura import Leitura

# as tabelas do App que esta tela lê (a dos tokens só na linha do cadastro, por pessoas.py)
TABELAS = ("qualidadelog", "rondas", "rondaativos", "rondaos", ("fracttaltokens", "cadastro"))
# a que ela EXIGE para sair do painel do App: sem o registro dos fechamentos, todo mundo cairia em "fora do App"
EXIGIDAS = ("qualidadelog",)
# os parâmetros que a rota do App entende; o resto da URL não chega às regras
PARAMETROS = ("de", "ate", "dias", "sup", "funcao", "colab", "regiao", "os", "balde", "nome", "pag", "tam")
# escopo de Admin: vê a fila inteira (no Nexus só entra quem tem a senha de admin)
ESCOPO_ADMIN = {"clusters": None, "papel": "Admin"}
VALIDADE_S = 600              # fila com mais de 10 min pede releitura (o mesmo tempo da cópia do App)
ESPERA_APOS_RECUSA_S = 300    # o Fracttal recusou: 5 min sem pedir de novo
_SEMPRE = 10 ** 9             # a cópia do App nunca relê a fila na hora da tela: quem relê é este módulo
_BRT = timezone(timedelta(hours=-3))
_ESTADO = {"lendo": False, "erro": "", "erro_em": 0.0}
_TRAVA = threading.Lock()


class _Usinas(list):
    """O escopo "estas usinas" que a cópia do App entende (`_area_ok`: `clusters.usinas`, comparado com a usina do
    Fracttal, `groups_1_description`). É assim que o filtro de equipe e de supervisor entra na conta do App."""

    def __init__(self, nomes):
        super().__init__(sorted(nomes))
        self.usinas = {regras_app._norm(n) for n in nomes}


class _Pedido:
    """O pedaço do HttpRequest que as regras do App leem: só .params.get."""

    def __init__(self, params):
        self.params = dict(params)


def em_segundo_plano(fn):
    """Onde a releitura roda: numa thread, para a tela não esperar. Nos testes, na hora (o teste que prova que a tela
    não espera troca esta função)."""
    if not has_app_context() or current_app.config.get("TESTING"):
        fn()
        return
    threading.Thread(target=fn, daemon=True, name="nexus-fila-fracttal").start()


def configurado() -> bool:
    return tabelas.configurado(EXIGIDAS) and fracttal.configurado()


def _lida_em():
    return regras_app._FILA_CACHE.get("ts")         # UTC sem fuso, como a cópia do App grava


def _reler(app):
    """Relê a fila inteira e só troca a guardada se veio completa. Falha = anota e espera para tentar de novo."""
    try:
        with app.app_context() if app else contextlib.nullcontext():
            linhas = regras_app._fx_wo_paralelo(2, "final_date", regras_app.SUP_CAP_BACKLOG)
        regras_app._FILA_CACHE.update(ts=datetime.utcnow(), linhas=linhas)
        _ESTADO.update(erro="", erro_em=0.0)
        if app:
            # a conta da tela (a fila inteira pela regra do App) fica pronta para o período padrão: a 1ª visita depois
            # da releitura não espera os ~4 s dela (medido em 05/10)
            try:
                with app.test_request_context():
                    _ESTADO["lendo"] = True          # para o fila_toda daqui não pedir outra releitura
                    fila_toda({"dias": "30"})
            except Exception:      # noqa: BLE001 — aquecer é conforto; a tela calcula na hora se precisar
                pass
    except Exception as e:      # noqa: BLE001 — 429, página faltando, rede: a tela segue com a última fila boa
        _ESTADO.update(erro=str(getattr(e, "msg", "") or e)[:160], erro_em=time.time())
    finally:
        _ESTADO["lendo"] = False


def _pedir_releitura():
    lida = _lida_em()
    if lida and (datetime.utcnow() - lida).total_seconds() < VALIDADE_S:
        return
    with _TRAVA:
        if _ESTADO["lendo"] or time.time() - _ESTADO["erro_em"] < ESPERA_APOS_RECUSA_S:
            return
        _ESTADO["lendo"] = True
    app = current_app._get_current_object() if has_app_context() else None
    em_segundo_plano(lambda: _reler(app))


def estado() -> dict:
    """Para a tela: se está lendo, quando a fila foi lida (horário de Brasília) e o erro da última tentativa."""
    lida = _lida_em()
    return {"lendo": _ESTADO["lendo"], "erro": _ESTADO["erro"],
            "lida_em": lida.replace(tzinfo=timezone.utc).astimezone(_BRT).strftime("%d/%m %H:%M") if lida else ""}


def aquecer(app):
    """Lê a fila ao subir o Nexus, em segundo plano: a 1ª visita depois de um reinício não espera (05/10: "fila ainda
    não lida" logo depois de cada reinício)."""
    with _TRAVA:
        if _ESTADO["lendo"]:
            return
        _ESTADO["lendo"] = True
    threading.Thread(target=lambda: _reler(app), daemon=True, name="nexus-fila-fracttal").start()


def fila(params: dict, usinas=None) -> Leitura:
    """`usinas` = os nomes do Fracttal (Classificação 1) das usinas da equipe ou do supervisor escolhido; None = todas."""
    p = {k: str(v) for k, v in params.items() if k in PARAMETROS and v not in (None, "")}
    regras_app.FILA_TTL_S = _SEMPRE        # a cópia é recarregada nos testes: reafirma a cada visita
    _pedir_releitura()
    lida = _lida_em()
    if regras_app._FILA_CACHE.get("linhas") is None:
        return Leitura({}, time.time(), "")      # 1ª leitura em andamento (ou recusada): a tela diz qual

    escopo = ESCOPO_ADMIN if usinas is None else {**ESCOPO_ADMIN, "clusters": _Usinas(usinas)}

    def calcular():
        return regras_app._fila_supervisao(_Pedido(p), escopo)
    # a fila relida entra na conta na hora: a data da fila faz parte da chave da cópia de 5 min
    filtro = tuple(sorted(usinas)) if usinas is not None else None
    return leitura.ler(("fila", str(lida), filtro) + tuple(sorted(p.items())), calcular)


def fila_toda(params: dict, usinas=None) -> Leitura:
    """A fila inteira, tarefa a tarefa, pela conta do App (`_fila_supervisao`), para os insights da tela (Levi, 05/10:
    "refaça essa parte de aprovação de OS para retirada de bons insights"). A cópia do App devolve no máximo 200 linhas
    por chamada; aqui as páginas são juntadas (medido em 05/10: 24 páginas, 0,1 s cada depois da 1ª, que leva ~3,5 s
    para carregar o registro das notas) e a soma fica na cópia de 5 min, que muda quando a fila é relida. Cada tarefa
    ganha a usina do Fracttal (`groups_1_description`), que a cópia do App não devolve: vem da fila crua."""
    p = {k: str(v) for k, v in params.items() if k in ("de", "ate", "dias") and v not in (None, "")}
    regras_app.FILA_TTL_S = _SEMPRE
    _pedir_releitura()
    lida = _lida_em()
    if regras_app._FILA_CACHE.get("linhas") is None:
        return Leitura({}, time.time(), "")
    escopo = ESCOPO_ADMIN if usinas is None else {**ESCOPO_ADMIN, "clusters": _Usinas(usinas)}

    def calcular():
        pag, todas, primeira = 1, [], None
        while True:
            d = regras_app._fila_supervisao(_Pedido({**p, "pag": str(pag), "tam": "200"}), escopo)
            primeira = primeira or d
            todas += d.get("linhas") or []
            if pag >= int((d.get("pagina") or {}).get("paginas") or 1):
                break
            pag += 1
        grupo = {w.get("id_work_orders_tasks") or w.get("id_work_order"): w.get("groups_1_description") or ""
                 for w in regras_app._FILA_CACHE.get("linhas") or []}
        for x in todas:
            x["usina_fx"] = grupo.get(x.get("id_wt"), "")
        return {"janela": primeira.get("janela"), "resumo": primeira.get("resumo"), "baldes": primeira.get("baldes"),
                "sem_cadastro": primeira.get("sem_cadastro"), "linhas": todas}
    filtro = tuple(sorted(usinas)) if usinas is not None else None
    return leitura.ler(("fila_toda", str(lida), filtro) + tuple(sorted(p.items())), calcular)


def limpar():
    _ESTADO.update(lendo=False, erro="", erro_em=0.0)
    regras_app._FILA_CACHE.update(ts=None, linhas=None)
