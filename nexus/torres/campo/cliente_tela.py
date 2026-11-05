"""A tela Visão do cliente da Usinas 360° (fase 1, 05/11/2026): só a rota. A conta mora em `nexus/campo/visao_cliente.py`.

Fica num módulo à parte, importado no fim do `__init__` da torre, porque precisa do `bp` e da `TORRE` (como as
Ocorrências). A fase 1 é para a Grid, com o login de hoje: escolhe-se o cliente e a tela mostra a síntese das usinas
dele. Cada fonte que não responde fica "sem leitura" na tela, com o aviso, e o resto vale.
"""
import logging
from datetime import timedelta

from flask import current_app, render_template, request

from ...campo import responsaveis as campo_resp
from ...campo import visao
from ...campo import visao_cliente as VC
from ...dados import fatos as D
from . import TORRE, bp

_log = logging.getLogger("nexus.campo")


def _fontes(b, uids: set, hoje) -> tuple[dict, dict]:
    """As quatro fontes da síntese, cada uma por conta própria: {nome: dado por usina, ou None} e {nome: o erro}."""
    cfg = current_app.config
    fontes, erros = {}, {}
    # o tempo real (a ponte só de leitura)
    tr = VC.ler_tempo_real(cfg)
    if tr["erro"]:
        fontes["tempo_real"], erros["tempo_real"] = None, tr["erro"]
    else:
        todas = VC.juntar_tempo_real(tr["usinas"], campo_resp.Nomes(b))
        fontes["tempo_real"] = {uid: r for uid, r in todas.items() if uid in uids}
    fontes["tempo_real_ts"] = tr.get("cache_ts") or ""
    # os chamados à distribuidora (o Andamento da Ronda COS, como a tela Acionamentos)
    try:
        from ...cos import andamento as AND
        if not AND.fonte(cfg).ligada:
            raise RuntimeError("o Andamento da Ronda COS não está ligado neste servidor")
        clientes, erro_cli = AND.clientes(cfg)
        if erro_cli and not clientes:
            raise RuntimeError(erro_cli)
        ch = VC.chamados_por_usina(b, [AND.ler_distribuidoras(cfg, c) for c in clientes])
        fontes["chamados"] = {uid: v for uid, v in ch.items() if uid in uids}
    except Exception as e:      # noqa: BLE001 — sem a distribuidora, o resto vale
        fontes["chamados"], erros["chamados"] = None, str(e)[:160]
    # as OS abertas (as tarefas das OS do Fracttal no banco)
    try:
        from ...dados import fato_tarefa_os as FT
        tarefas = visao._livro(FT.LIVRO, FT.ABA)
        if not tarefas:
            raise RuntimeError("as OS do Fracttal ainda não chegaram ao banco")
        os_chamado = {D._id(r.get("os")) for r in visao._livro(campo_resp.LIVRO_CHAMADOS, campo_resp.ABA_CHAMADOS)}
        fontes["os"] = VC.os_por_usina([t for t in tarefas if D._id(t.get("usina_id")) in uids],
                                       os_chamado - {None}, hoje)
    except Exception as e:      # noqa: BLE001
        fontes["os"], erros["os"] = None, str(e)[:160]
    # a próxima visita (a programação do PCM, a semana corrente e a próxima)
    try:
        from ...dados.calendario import data_id
        segunda = hoje - timedelta(days=hoje.weekday())
        prog = campo_resp._programacao_recente({data_id(segunda), data_id(segunda + timedelta(days=7))})
        agora = visao._agora()           # já em Brasília
        fontes["visitas"] = {uid: v for uid, v in VC.visitas_por_usina(prog, hoje, f"{agora:%H:%M}").items()
                             if uid in uids}
    except Exception as e:      # noqa: BLE001
        fontes["visitas"], erros["visitas"] = None, str(e)[:160]
    return fontes, erros


@bp.route("/cliente")
def cliente():
    """A Visão do cliente: a escolha do cliente e, com um escolhido, os 5 números e a tabela das usinas dele."""
    leitura = campo_resp.visao_responsaveis()
    d = leitura.dados or {}
    erro_visao = leitura.erro
    try:
        b = visao._Base()
    except Exception as e:      # noqa: BLE001 — sem o cadastro, a tela abre com o aviso, como as outras do Campo
        _log.warning("Visão do cliente: não consegui ler o cadastro (%s)", type(e).__name__)
        b, erro_visao = None, f"Não consegui ler o cadastro do Nexus ({type(e).__name__})"
    grupos = VC.por_cliente(d.get("usinas") or [], b) if b else {}
    opcoes = VC.opcoes_de_cliente(grupos, b.nome_cliente) if b else []
    cid = D._id(request.args.get("cliente"))
    if cid not in grupos:
        cid = None
    sintese, erros, ts = None, {}, ""
    if cid:
        hoje = visao._agora().date()
        usinas = grupos[cid]
        fontes, erros = _fontes(b, {u["usina_id"] for u in usinas}, hoje)
        ts = fontes.get("tempo_real_ts") or ""
        sintese = VC.montar(usinas, fontes["tempo_real"], fontes["chamados"], fontes["os"], fontes["visitas"], hoje)
    return render_template("campo/cliente.html", torre=TORRE, tela=TORRE.tela("cliente"), opcoes=opcoes, cid=cid,
                           nome=(b.nome_cliente.get(cid) or "") if cid else "", sintese=sintese, erros=erros,
                           erro_visao=erro_visao, lido_tr=ts, fontes_nome=FONTES_NOME)


FONTES_NOME = {"tempo_real": "o status do tempo real", "chamados": "os chamados na distribuidora",
               "os": "as OS do Fracttal", "visitas": "a programação do PCM"}
