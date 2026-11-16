"""A Sala de controle da Performance (a tela é da plataforma, na moldura) pede ao Nexus o "abaixo dos demais".

A conta dos inversores com 70% ou menos dos outros da usina é a do Conversor (`servico.furos_mural`, a aba Baixa
performance da Coletas), com os BDs do banco e as paradas do COS que explicam o dia. A Sala não a refaz: lê daqui
(16/11/2026, a regra do dono: cada tela lê do dono do dado). Quem abre é quem tem a tela "Sala de controle" (o caminho
fica debaixo dela, `setor_telas.pode`); não depende de ter a Coletas. Nada grava: é só a leitura, e o resultado fica
guardado pela subida dos BDs (o mesmo cofre da Coletas: quem abriu uma já aqueceu a outra).
"""
import datetime as dt

from flask import current_app, request

from ...performance.coletas import servico
from . import bp
from .coletas_tela import _fabrica_do_banco, _json


class _SoOBanco:
    """A "sessão" que o `furos_mural` espera, sem Excel solto: os dois BDs saem do banco."""
    origem_bd, bds, caminhos_bd = {}, {}, {}


@bp.route("/sala-de-controle/abaixo")
def sala_abaixo():
    """?mes=AAAA-MM (padrão, o corrente) → {"linhas", "limiar", "ini", "fim", "paradas", "paradas_erro"} ou {"erro"}."""
    mes = (request.args.get("mes") or dt.date.today().strftime("%Y-%m")).strip()
    try:
        out = servico.furos_mural(_SoOBanco(), _fabrica_do_banco(current_app._get_current_object()), mes)
    except Exception as e:                     # noqa: BLE001 — a tela diz "não consegui ler"; o log guarda o porquê
        current_app.logger.exception("sala de controle: abaixo dos demais")
        return _json({"erro": "%s: %s" % (type(e).__name__, e)}, 502)
    return _json(out, 400 if out.get("erro") == "mês inválido" else 200)


# ── O que o Monitoramento do COS lê (16/11/2026) ────────────────────────────────────────────────────────────────────
# Levi: "A lista de usinas do Monitoramento do COS. você não tem acesso a API? puxe a lista". A lista e os inversores ao
# vivo do Monitoramento do COS vêm da Ronda COS, pelo Andamento, com a chave de máquina que só este servidor tem (Base →
# Chaves). A Sala de controle (tela da plataforma) lê daqui, pela mesma origem, o que o COS já lê: as usinas com logger
# (SCADA Grid) e as do SunOP, e os inversores de cada uma, para conferir a fonte dela no Tempo real (a API PV, por
# exemplo) contra o logger. Só leitura, com as cópias do próprio Andamento; quem abre é quem tem a tela da Sala.
SALA_COS_INVERSORES_TTL_S = 30.0          # a conferência é de olhar, não de operar: 30 s de cópia para todos


@bp.route("/sala-de-controle/cos/usinas")
def sala_cos_usinas():
    """As usinas do Monitoramento do COS, como a tela dele as mostra (`cos.monitoramento._linha`): {"usinas": [{id,
    fonte ("SCADA Grid" | "SunOP"), codigo, nome, sub_usina, cliente, kw, inversores_online, inversores_total, situacao,
    grupo, lido, minutos_atras}], "velha"} ou {"erro"} (503)."""
    from ...cos import andamento as AND
    from ...cos import monitoramento as MON
    g = AND.ler_geracao(current_app.config)
    if not g.dados:
        return _json({"erro": g.erro or "a Ronda COS não respondeu"}, 503)
    agora = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).replace(tzinfo=None)
    linhas = []
    for u in g.dados.get("usinas") or []:
        x = MON._linha(u, None, agora)
        x.pop("curva", None)
        linhas.append(x)
    return _json({"usinas": linhas, "velha": bool(g.velha), "erro_da_ultima": g.erro or ""})


def _corrente(s):
    v = (s or {}).get("corrente")
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


@bp.route("/sala-de-controle/cos/inversores")
def sala_cos_inversores():
    """Os inversores de agora de cada usina com logger (os cartões do SCADA da Ronda COS, o mesmo dado da janela dos
    inversores do Monitoramento), enxutos: {"cartoes": [{pid, kw, situacao, inversores: [{id, nome, modbus_id, kw,
    estado, veredito, strings, com_corrente}]}]} ou {"erro"} (503)."""
    from ...cos import andamento as AND
    dados, erro = AND.ler_ao_vivo(current_app.config, "/api/nexus/geracao/scada", SALA_COS_INVERSORES_TTL_S)
    if dados is None:
        return _json({"erro": erro or "a leitura ao vivo da Ronda COS falhou"}, 503)
    cartoes = []
    for c in dados.get("cartoes") or []:
        invs = []
        for i in c.get("inversores") or []:
            ss = [s for m in (i.get("mppts") or []) for s in (m.get("strings") or [])] + list(i.get("strings_sem_mppt") or [])
            cs = [_corrente(s) for s in ss]
            invs.append({"id": i.get("id"), "nome": i.get("nome"), "modbus_id": i.get("modbus_id"), "kw": i.get("pac"),
                         "estado": i.get("estado"), "veredito": i.get("veredito"), "strings": len(ss),
                         "com_corrente": sum(1 for v in cs if v is not None and v > 0)})
        sit = c.get("situacao")
        cartoes.append({"pid": c.get("pid"), "kw": c.get("pac_total_kw"),
                        "situacao": (sit.get("texto") or sit.get("chave")) if isinstance(sit, dict) else sit, "inversores": invs})
    return _json({"cartoes": cartoes})
