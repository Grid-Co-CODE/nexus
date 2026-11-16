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
