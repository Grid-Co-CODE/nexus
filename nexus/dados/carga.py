"""A carga da camada de dados: lê os livros de origem e o cadastro, grava as dimensões e os fatos com os IDs.

De hora em hora, aos :40 (os livros do App chegam aos :25), dentro do processo do Nexus. Só lê a API do banco e grava
nela: não toca em Fracttal, API PV nem SunOp. Duas máquinas com o Nexus no ar (o PC do Levi e o servidor) não gravam em
dobro: a carga só grava se a última tiver mais de `INTERVALO_MIN` minutos (a hora fica no próprio livro, aba
`atualizacao`); a que chegar depois, pula. `NEXUS_CARGA_DADOS=0` desliga numa máquina.

Livros que esta carga mantém (registrados no catálogo):
- `nexus_dimensoes`: `dim_data` (o calendário), `feriados_locais`, `pessoas_historico` e `usinas_historico` (o
  histórico válido de / até) e `atualizacao`.
- `nexus_fatos`: `fato_fechamento` e `qualidade` (quanto de cada fato ligou a cada dimensão) e `atualizacao`.
"""
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from . import calendario, fatos, historico, livros

LIVRO_DIM, NOME_DIM = "nexus_dimensoes", "Nexus · dimensões (calendário, feriados, histórico de pessoas e usinas)"
LIVRO_FATOS, NOME_FATOS = "nexus_fatos", "Nexus · fatos com os IDs do cadastro e a qualidade da ligação"
ORIGEM_FECHAMENTOS = ("fechamentos_app_campo", "Fechamentos")
CADASTRO = "cadastro_nexus"
INTERVALO_MIN = 50
MINUTO_DA_HORA = 40
CAB_ATUALIZACAO = ["gerado_em", "maquina", "duracao_s", "linhas", "como_ler"]
_BRT = timezone(timedelta(hours=-3))
log = logging.getLogger("nexus.dados")
_LACO = {"thread": None, "parar": threading.Event(), "ultimo": None}


def _agora():
    return datetime.now(_BRT)


def _base(config) -> str:
    from ..cadastro.ligacoes import BASE_API
    return (config.get("GRIDCO_DB_API") or BASE_API).rstrip("/")


def ultima(base, sessao) -> datetime | None:
    for l in livros.ler(base, sessao, LIVRO_FATOS, "atualizacao"):
        try:
            return datetime.fromisoformat(str(l.get("gerado_em")))
        except (TypeError, ValueError):
            return None
    return None


def _feriados(config) -> dict:
    """Os feriados dos insumos do PCM (o mesmo arquivo que o motor lê). Sem o arquivo, calendário sem feriado."""
    try:
        from ..pcm import geracao, insumos
        return insumos.carregar(geracao.pasta_trabalho(config)).get("feriados") or {}
    except Exception:       # noqa: BLE001 — sem insumos nesta máquina
        return {}


def _pessoas_por_codigo(config, sessao) -> dict:
    """{código HMAC do e-mail: pessoa_id}, pelo cadastro decifrado na hora. Sem as duas chaves, vazio."""
    if not (config.get("NEXUS_PESSOA_HMAC") and config.get("NEXUS_CHAVE_CADASTRO")):
        return {}
    from ..campo.ligacao_cadastro import mapas
    return mapas(config, sessao).get("hmac") or {}


def montar(config, sessao, agora: datetime | None = None) -> tuple[dict, dict, dict]:
    """(tabelas de nexus_dimensoes, tabelas de nexus_fatos, relatório). Não grava."""
    agora = agora or _agora()
    base = _base(config)
    hoje, iso = agora.date().isoformat(), agora.isoformat(timespec="seconds")
    cad = {a: livros.ler(base, sessao, CADASTRO, a) for a in ("usinas", "equipes", "pessoas", "de_para")}
    lig = fatos.Ligador(cad["usinas"], cad["de_para"], cad["equipes"], _pessoas_por_codigo(config, sessao))
    origem = livros.ler(base, sessao, *ORIGEM_FECHAMENTOS)
    fato = fatos.fato_fechamento(origem, lig)
    q = fatos.qualidade("fechamento", ORIGEM_FECHAMENTOS[0], fato, fatos.CAB_FECHAMENTO, origem,
                        livros.atualizado_em(base, sessao, ORIGEM_FECHAMENTOS[0]), iso)

    fer = _feriados(config)
    nac, locais = calendario.feriados(fer)
    anteriores = {e: livros.ler(base, sessao, LIVRO_DIM, f"{e}_historico") for e in historico.RASTREADOS}
    hist = {e: historico.atualizar(e, cad[e], anteriores[e], hoje) for e in historico.RASTREADOS}
    dias = calendario.dias(nac)

    maquina = "servidor" if os.name != "nt" else "pc"
    dim = {"dim_data": (calendario.CAB_DIA, dias), "feriados_locais": (calendario.CAB_FERIADO, locais),
           "pessoas_historico": (historico.cabecalho("pessoas"), hist["pessoas"]),
           "usinas_historico": (historico.cabecalho("usinas"), hist["usinas"]),
           "atualizacao": (CAB_ATUALIZACAO, [[iso, maquina, None, len(dias),
                                              "data_id = AAAAMMDD; histórico: vigente = sim, válido de/até"]])}
    fat = {"fato_fechamento": (fatos.CAB_FECHAMENTO, fato), "qualidade": (fatos.CAB_QUALIDADE, [q]),
           "atualizacao": (CAB_ATUALIZACAO, [[iso, maquina, None, len(fato),
                                              "IDs do cadastro_nexus; vazio = não ligou (ver qualidade)"]])}
    rel = {"gerado_em": iso, "fato_fechamento": len(fato), "pct_usina": q[8], "pct_equipe": q[9], "pct_pessoa": q[10],
           "feriados_nacionais": len(nac), "feriados_locais": len(locais),
           "pessoas_historico": len(hist["pessoas"]), "usinas_historico": len(hist["usinas"])}
    return dim, fat, rel


def rodar(config, sessao=None, *, gravar=True, forcar=False, agora=None) -> dict:
    """Uma carga. Devolve o relatório (só contagens). Com `gravar`, grava e confere os dois livros."""
    import requests
    s = sessao or requests.Session()
    base = _base(config)
    t0 = time.time()
    if gravar and not forcar:
        u = ultima(base, s)
        if u and (agora or _agora()) - u < timedelta(minutes=INTERVALO_MIN):
            return {"pulou": f"a última carga é de {u.isoformat(timespec='minutes')} (outra máquina ou a mesma)"}
    dim, fat, rel = montar(config, s, agora)
    if gravar:
        if not config.get("GRIDCO_SQL_TOKEN"):
            return dict(rel, erro="sem GRIDCO_SQL_TOKEN: montado e não gravado")
        dur = round(time.time() - t0, 1)
        for t in (dim, fat):
            t["atualizacao"][1][0][2] = dur
        rel["gravado"] = {LIVRO_DIM: livros.publicar(LIVRO_DIM, NOME_DIM, dim, base=base,
                                                     token=config["GRIDCO_SQL_TOKEN"], sessao=s),
                          LIVRO_FATOS: livros.publicar(LIVRO_FATOS, NOME_FATOS, fat, base=base,
                                                       token=config["GRIDCO_SQL_TOKEN"], sessao=s)}
    rel["duracao_s"] = round(time.time() - t0, 1)
    return rel


def _espera_s(agora=None) -> float:
    agora = agora or _agora()
    alvo = agora.replace(minute=MINUTO_DA_HORA, second=0, microsecond=0)
    if alvo <= agora:
        alvo += timedelta(hours=1)
    return (alvo - agora).total_seconds()


def ligar(app):
    """O laço de hora em hora. Quem chama é o `nexus.dados.instalar` (app.py e servir.py), nunca o create_app."""
    if _LACO["thread"] is not None:
        return

    def laco():
        while not _LACO["parar"].wait(_espera_s()):
            with app.app_context():
                try:
                    _LACO["ultimo"] = rodar(app.config)
                    log.info("carga de dados: %s", _LACO["ultimo"])
                except Exception as e:      # noqa: BLE001 — o laço não morre por uma carga
                    _LACO["ultimo"] = {"erro": f"{type(e).__name__}: {e}"[:300]}
                    log.exception("carga de dados")

    _LACO["thread"] = threading.Thread(target=laco, name="nexus-carga-dados", daemon=True)
    _LACO["thread"].start()
