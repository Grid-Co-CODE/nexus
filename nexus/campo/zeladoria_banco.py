"""Publica a Zeladoria no banco para o dashboard do cliente (26/10/2026): `nexus_zeladoria · zeladoria_semana` (a conta
é `zeladoria.visao_do_banco`) e `nexus_zeladoria · atualizacao` (uma linha: quando, a semana corrente e quantas linhas,
para o 5080 conferir que leu a gravação inteira).

Levi, 26/10/2026: "agora faz a mesma tela no dashboard do cliente"; pelo chat do Dashboard Thopen, a decisão dele: o
Nexus publica a visão pronta e o 5080 só mostra. O 5080 não tem como ler o checklist das rondas: ele está no texto da OS
de ronda no Fracttal, que o Nexus lê e guarda (`ronda_checklist`), e não vai ao banco.

**Só a máquina que lê o checklist grava** (regra 12 do `nexus/dados/CLAUDE.md`: o arquivo local `rondas_aprovadas.json`
nunca entra na carga de hora em hora, o conteúdo mudaria conforme a máquina). O PC sobe com `NEXUS_CAMPO_AQUECER=0` e
não relê as OS de ronda aprovadas (o arquivo dele parou em 13/10/2026): ali o laço nem liga. Onde liga, cada volta pede
a releitura das aprovadas (1 a 2 páginas do Fracttal) e só grava com o checklist inteiro e novo:
- as aprovadas relidas por inteiro há menos de `APROVADAS_MAX_H` horas (o Fracttal que recusa segura a gravação);
- a fila da Aprovação (as rondas em verificação, as mais novas) lida há menos de `FILA_MAX_H` horas. Ela é relida pelas
  telas (a Aprovação é aberta o dia inteiro); mais velha que isso, a volta pede a releitura (~55 páginas) e não grava
  nesta hora: no máximo 4 releituras da fila por dia vindas daqui (a cota do Fracttal é da empresa inteira);
- as rondas do banco lidas sem erro e as OS de zeladoria (`nexus_os`) presentes: sem elas a situação sairia "sem dado"
  em tudo e cobriria a última gravação boa.
Recusou = o livro fica como está, e o motivo vai ao `estado()` e ao log. Grava se a última gravação tiver mais de 50 min
(conferido de novo logo antes de gravar); a volta acorda num minuto seu entre :32 e :37, depois das OS de zeladoria
(:10 a :20) e longe da carga de dados (:40). `NEXUS_ZELADORIA_PUBLICAR=0` desliga.
"""
import logging
import random
import threading
import time
from datetime import datetime, timedelta, timezone

from ..dados import livros

LIVRO = "nexus_zeladoria"
ABA = "zeladoria_semana"
NOME_LIVRO = "Nexus · zeladoria: vegetação e sujidade por usina e semana (para o dashboard do cliente)"
CAB_ATUALIZACAO = ("atualizado_em", "semana_corrente", "semanas_qtd", "linhas_qtd", "usinas_qtd", "checklist_ate")
INTERVALO_MIN = 50
PRIMEIRA_S = 900            # a 1ª volta 15 min depois de subir: o boot relê a fila (20 s) e as aprovadas (90 s)
MINUTO_DA_HORA = 32
DESENCONTRO_MAX_S = 300
APROVADAS_MAX_H = 3
FILA_MAX_H = 6
_BRT = timezone(timedelta(hours=-3))
_LACO = {"thread": None, "parar": threading.Event(), "ultimo": None, "quando": None}
log = logging.getLogger("nexus.campo")


def _base(config) -> str:
    from ..cadastro.ligacoes import BASE_API
    return (config.get("GRIDCO_DB_API") or BASE_API).rstrip("/")


def _ultima(base, sessao) -> datetime | None:
    v = livros.atualizado_em(base, sessao, LIVRO)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00")) if v else None
    except ValueError:
        return None
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


def checklist_novo(agora_s: float | None = None) -> str:
    """"" quando o checklist das rondas está inteiro e novo; senão, o motivo (e pede a releitura que falta)."""
    from . import aprovacao, ronda_checklist
    agora_s = agora_s or time.time()
    ronda_checklist.pedir_releitura()
    est = ronda_checklist.estado()
    if not est.get("lidas"):
        return "a leitura das OS de ronda aprovadas ainda não foi completa nesta máquina"
    lida = ronda_checklist.lida_em()
    if not lida or agora_s - lida > APROVADAS_MAX_H * 3600:
        return (f"as OS de ronda aprovadas não são relidas há mais de {APROVADAS_MAX_H} h"
                + (f" (o Fracttal: {est['erro']})" if est.get("erro") else ""))
    fila = aprovacao._lida_em()
    if not fila or agora_s - fila > FILA_MAX_H * 3600:
        aprovacao._pedir_releitura()
        return f"a fila da Aprovação (as rondas em verificação) tem mais de {FILA_MAX_H} h: pedi a releitura"
    return ""


def _dados():
    """O que a tela Zeladoria usa: as rondas (cópia de 2 min do banco), as respostas do checklist, as validações por foto
    e as OS de zeladoria. Sobe o erro da leitura das rondas e diz quando as OS não vieram."""
    from ..dados import fato_tarefa_os as FT
    from . import ronda_checklist, visao
    leitura = visao.rondas()
    if leitura.erro:
        raise RuntimeError(f"as rondas do banco não vieram: {leitura.erro}")
    d = leitura.dados or {}
    return {"todas": d.get("todas") or [], "cobertura": d.get("cobertura") or [], "validacoes": d.get("validacoes") or [],
            "respostas": ronda_checklist.respostas(), "tarefas": visao._livro(FT.LIVRO, FT.ABA),
            "checklist_ate": ronda_checklist.estado().get("ate") or ""}


def publicar(config, sessao=None, *, agora=None, forcar=False, dados=None, conferir_checklist=True) -> dict:
    """Uma volta: confere o checklist e a última gravação, faz a visão e grava as duas abas (conferidas depois,
    `livros.publicar`). Devolve o relatório (só contagens). `dados` e `conferir_checklist` são para os testes."""
    import requests
    from . import zeladoria as ZL
    s = sessao or requests.Session()
    base = _base(config)
    agora = agora or datetime.now(_BRT)

    def gravou_ha_pouco():
        u = None if forcar else _ultima(base, s)
        if u and agora - u < timedelta(minutes=INTERVALO_MIN):
            return f"a última gravação é de {u.astimezone(_BRT).isoformat(timespec='minutes')}"
    if pulou := gravou_ha_pouco():
        return {"pulou": pulou}
    if not config.get("GRIDCO_SQL_TOKEN"):
        return {"erro": "sem GRIDCO_SQL_TOKEN: não grava"}
    if conferir_checklist and (motivo := checklist_novo()):
        return {"recusou": f"{motivo}; o livro fica como está"}
    d = dados if dados is not None else _dados()
    if not d["tarefas"]:
        return {"recusou": "as OS de zeladoria (nexus_os) não vieram do banco: a situação sairia \"sem dado\" em tudo; "
                           "o livro fica como está"}
    hoje = agora.astimezone(_BRT).date()
    linhas, rel = ZL.visao_do_banco(d["todas"], d["cobertura"], d["respostas"], d["validacoes"], d["tarefas"], hoje)
    chaves = [(l[2], l[0]) for l in linhas]
    if len(set(chaves)) != len(chaves):
        return dict(rel, recusou="usina × semana repetida: o grão quebrou; o livro fica como está")
    if not linhas and livros.ler(base, s, LIVRO, ABA):
        return dict(rel, recusou="a visão saiu vazia e o banco tem linhas: o livro fica como está")
    if pulou := gravou_ha_pouco():          # outra volta gravou enquanto esta fazia a conta
        return dict(rel, pulou=pulou)
    atu = [agora.isoformat(timespec="seconds"), ZL.semana_de(hoje), ZL.SEMANAS_NO_BANCO, len(linhas), rel["usinas"],
           d.get("checklist_ate") or ""]
    rel["gravado"] = livros.publicar(LIVRO, NOME_LIVRO, {ABA: (ZL.CAB_BANCO, linhas),
                                                         "atualizacao": (CAB_ATUALIZACAO, [atu])},
                                     base=base, token=config["GRIDCO_SQL_TOKEN"], sessao=s)
    return rel


def estado() -> dict:
    """O resultado da última volta deste processo e quando foi."""
    return {"ultimo": _LACO["ultimo"], "quando": _LACO["quando"]}


def _espera_s(agora=None, desencontro_s: float = 0.0) -> float:
    agora = agora or datetime.now(_BRT)
    alvo = agora.replace(minute=MINUTO_DA_HORA, second=0, microsecond=0) + timedelta(seconds=desencontro_s)
    if alvo <= agora:
        alvo += timedelta(hours=1)
    return (alvo - agora).total_seconds()


def ligar(app):
    """O laço: a 1ª volta 15 min depois de subir, depois a cada hora, no :32 mais o atraso que este processo sorteou. Não
    liga onde `NEXUS_ZELADORIA_PUBLICAR=0` nem onde `NEXUS_CAMPO_AQUECER=0` (o PC: não relê o checklist das rondas).
    Quem chama é o `campo.instalar` (app.py e servir.py), nunca o create_app: teste não fala com a rede."""
    if (_LACO["thread"] is not None or str(app.config.get("NEXUS_ZELADORIA_PUBLICAR", "1")).strip() == "0"
            or str(app.config.get("NEXUS_CAMPO_AQUECER", "1")).strip() == "0"):
        return
    desencontro = random.uniform(0, DESENCONTRO_MAX_S)

    def laco():
        espera = PRIMEIRA_S
        while not _LACO["parar"].wait(espera):
            with app.app_context():
                try:
                    _LACO["ultimo"] = publicar(app.config)
                    log.info("zeladoria no banco: %s", {k: v for k, v in _LACO["ultimo"].items() if k != "gravado"})
                except Exception as e:      # noqa: BLE001 — o laço não morre por uma volta
                    _LACO["ultimo"] = {"erro": f"{type(e).__name__}: {e}"[:300]}
                    log.exception("zeladoria no banco")
                _LACO["quando"] = datetime.now(_BRT).isoformat(timespec="minutes")
            espera = _espera_s(desencontro_s=desencontro)

    _LACO["thread"] = threading.Thread(target=laco, name="nexus-zeladoria-banco", daemon=True)
    _LACO["thread"].start()
