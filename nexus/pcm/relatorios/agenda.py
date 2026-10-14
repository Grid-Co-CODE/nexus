"""A emissão automática, nos horários do PCM (o `main` do relatorio_diario.py, que o robô de lá rodava a cada 15 min):
- diário: a 1ª volta depois das 06:00 (Brasília), sobre ontem, todo dia;
- tarde: a 1ª volta depois das 13:00 de dia útil (seg a sex), sobre hoje; feriado não pula, como lá;
- fechamento: na sexta a partir das 17:00, sobre a semana ativa, uma vez por semana; perdeu a sexta, não recupera;
- alerta: quando o banco_dados.json traz uma semana mais nova que a ativa (publicada pelo Publicar no App do Nexus ou
  pelo PC do PCM) e de novo quando ela é republicada (o `geradaEm` dela muda).
"Já emitido" é a folha guardada (`arquivo.existe`): o servidor que reinicia no meio do dia (todo push reinicia) emite o
que faltou na volta seguinte, e não emite duas vezes.

Uma thread por processo, que liga em `app.py` e `servir.py` (nunca no create_app: teste não liga laço). Uma volta a
cada 5 min; só baixa a Gestão PCM (14 MB, cópia de 5 min) quando há o que emitir. `NEXUS_PCM_RELATORIOS_AUTO=0` desliga
numa máquina. Não lê o Fracttal (a cota é da empresa toda).
"""
import logging
import threading
from datetime import datetime, timedelta

from .. import fonte
from . import arquivo, dados, emitir
from .alerta import semana_nova
from .regras import BRT, semana_key

log = logging.getLogger(__name__)
HORA_DIARIO = 6
HORA_TARDE = 13
HORA_SEMANAL = 17
DIA_SEMANAL = 4                 # 0 = segunda … 4 = sexta
PRIMEIRA_S = 90
INTERVALO_S = 300
_LACO = {"thread": None, "parar": threading.Event(), "ultimo": None}


def devidos(config, agora: datetime, bd: dict) -> list[tuple[str, str, dict]]:
    """[(tipo, ref, marcas extras)] do que está devido agora e ainda não foi emitido."""
    out = []
    ontem = (agora.date() - timedelta(days=1)).isoformat()
    if agora.hour >= HORA_DIARIO and arquivo.existe(config, "diario", ontem) is None:
        out.append(("diario", ontem, {}))
    hoje = agora.date().isoformat()
    if agora.weekday() < 5 and agora.hour >= HORA_TARDE and arquivo.existe(config, "tarde", hoje) is None:
        out.append(("tarde", hoje, {}))
    if agora.weekday() == DIA_SEMANAL and agora.hour >= HORA_SEMANAL:
        week = bd.get("semana_ativa") or semana_key(agora.date())
        if arquivo.existe(config, "semanal", week) is None:
            out.append(("semanal", week, {}))
    week, gerada = semana_nova(bd)
    if week:
        marcas = arquivo.existe(config, "alerta", week)
        if marcas is None or marcas.get("geradaem", "") != gerada:
            out.append(("alerta", week, {"geradaem": gerada}))
    return out


def volta(config, agora: datetime | None = None) -> dict:
    """Uma rodada: emite e guarda o que está devido. Devolve o que fez (para o log e o Raio-X)."""
    agora = agora or datetime.now(BRT)
    rel = {"quando": agora.isoformat(timespec="minutes"), "emitidos": [], "erro": ""}
    leitura = fonte.ler(config)
    if leitura.dados is None:
        rel["erro"] = f"banco_dados.json: {leitura.erro}"
        return rel
    pend = devidos(config, agora, leitura.dados)
    if not pend:
        return rel
    entradas, lidos = dados.carregar(config)
    if entradas is None:
        rel["erro"] = "; ".join(f"{k}: {v.erro}" for k, v in lidos.items() if v.dados is None and k in ("bd", "gestao"))
        return rel
    for tipo, ref, extra in pend:
        folha = emitir(entradas, tipo, ref, agora)
        if folha is None:
            log.warning("relatórios do PCM: %s %s sem a semana no banco_dados", tipo, ref)
            continue
        arquivo.gravar(config, tipo, ref, folha["html"], agora, extra)
        rel["emitidos"].append(f"{tipo} {ref}")
    arquivo.limpar(config, agora.date())
    return rel


def ligar(app):
    """O laço: 1ª volta 90 s depois de subir, depois a cada 5 min."""
    if _LACO["thread"] is not None or str(app.config.get("NEXUS_PCM_RELATORIOS_AUTO", "1")).strip() == "0":
        return

    def laco():
        espera = PRIMEIRA_S
        while not _LACO["parar"].wait(espera):
            with app.app_context():
                try:
                    _LACO["ultimo"] = volta(app.config)
                    if _LACO["ultimo"]["emitidos"] or _LACO["ultimo"]["erro"]:
                        log.info("relatórios do PCM: %s", _LACO["ultimo"])
                except Exception as e:      # noqa: BLE001 — o laço não morre por uma volta
                    _LACO["ultimo"] = {"erro": f"{type(e).__name__}: {e}"[:300]}
                    log.exception("relatórios do PCM")
            espera = INTERVALO_S

    _LACO["thread"] = threading.Thread(target=laco, name="nexus-pcm-relatorios", daemon=True)
    _LACO["thread"].start()
