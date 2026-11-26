"""Performance › ETMs (24/11/2026): as OS das Estações Meteorológicas, a tela que veio da Engenharia (Levi, 24/11/2026: "a
parte de ETM agora vem para performance. Então, toda a parte de engenharia ETMs, eu quero que você traga para dentro da
performance"). Só o HTTP; fica num módulo à parte, importado no fim do `__init__` da torre, porque precisa do `bp` (como o
`limitacoes_tela` e o `sala_tela`).

- `GET /t/performance/etm`: as quatro abas, abrindo nas Estações em Aberto. `?releia=<nº>` (a volta da OS depois de trocar
  o responsável) relê só aquela OS; `?atualizar=1` (o histórico do app trazido) relê tudo por trás.
- `GET /t/performance/etm/os/<nº>`: a página da OS de ETM (a mesma da Engenharia, `_pagina_da_os`, com as marcações).
- `POST /t/performance/etm/os/<nº>/marcar`, `POST /t/performance/etm/finalizar`, `GET /t/performance/etm/usina/comentarios`.

Quem age (as marcações, o Finalizar em lote): o setor Performance e o administrador (`_quem_pode_etm`). A regra (a leitura do
Fracttal com a cópia em disco, as marcações, o histórico do app) segue em `nexus/engenharia/etm*.py`, e a página da OS em
`nexus/torres/engenharia` (é uma só para o Quadro da equipe, o Garantias e as ETMs). O endereço antigo /t/engenharia/etm/...
responde 308 para cá (`torre_engenharia.etm_mudou`), e a marca que o setor tinha em "engenharia/etm" vale para
"performance/etm" (`setor_telas.RENOMEADAS`).
"""
import collections
import logging
from datetime import datetime, timedelta, timezone

from flask import abort, jsonify, redirect, render_template, request, session, url_for

from ..engenharia import (BRT, FALHOU_BANCO, JANELA_CONCLUIDAS, _na_etm, _os_para_gravar, _pagina_da_os,
                          _quem_pode_etm, _quem_pode_na_os)
from . import TORRE, bp


def _os_do_planner(o: dict, m: dict | None, n_coment: int | None = None) -> dict:
    """A OS de ETM como as abas a desenham: o cartão do Fracttal enxuto, as marcações da Performance e quantos comentários
    ela tem (None sem ler o livro). A usina vai inteira (a chave do filtro: duas usinas de clientes diferentes podem ter
    o mesmo nome curto) e curta (o que a tela mostra)."""
    from ...engenharia import etm as ETM
    from ...engenharia import etm_marcas as M
    m = m or {}
    criada = o.get("criada") or ""
    enc = M.encerrada_em(m)         # o dia da semana dos Fechamentos pela Performance (Brasília)
    return {"os": o["os"], "wid": o.get("wid"), "titulo": o["titulo"], "cliente": o["cliente"], "usina": o["usina"],
            "eng_fim_dia": enc.astimezone(BRT).date().isoformat() if enc else "",
            "usina_nome": ETM.usina_curta(o["usina"]), "codigo": o["codigo"], "n_coment": n_coment,
            "ativo": o["ativo"], "responsavel": o["responsavel"], "solicitante": o["solicitante"],
            "criado_por": o["criado_por"], "trabalho": o["trabalho"], "coluna": o["coluna_etm"], "tipo": o["tipo"],
            "status": o["status"], "criada": criada[:10],
            # a fase da OS em andamento (09/11/2026): o filtro da coluna separa a que espera a verificação da outra
            "fase": ("verificacao" if o.get("coluna") == "verificacao" else "andamento")
                    if o["coluna_etm"] == "em_andamento" else "",
            # o dia de Brasília da criação e o do fim: o "OS ativa entre" do app compara dias
            "criada_dia": "-".join(reversed(criada[:10].split("/"))) if criada else "", "fim_dia": o.get("fim_iso") or "",
            # a hora da criação, para a linha do tempo da usina (25/11/2026)
            "criada_iso": o.get("criada_iso") or "",
            # quem encerrou pela Performance (o finalizado ou o diagnóstico mais novo), para a linha do tempo
            "eng_por": next((e.get("nome") or "" for e in (m.get("eventos") or [])
                             if e.get("evento") in ("finalizado", "diagnostico")), ""),
            "etiquetas": o["etiquetas"], "n_tarefas": len(o.get("tarefas") or []),
            "diagnostico": M.nome(M.DIAGNOSTICOS, m.get("diagnostico_id")) or None,
            "status_pos": M.nome(M.STATUS_POS, m.get("status_pos_id")) or None,
            "etiquetas_eng": [M.nome(M.ETIQUETAS, i) for i in sorted(m.get("etiquetas") or ())],
            "acompanhamento": bool(m.get("acompanhamento")), "finalizado": bool(m.get("finalizado")),
            # a conferência automática pelos dados diários do PG (25/11/2026, `performance/etm_conferencia.py`): o que
            # reprovou, o sem dado e o que espera os 5 dias (a ok vira finalizada sozinha e sai das abertas)
            "conf": _conf(o, m)}


def _conf(o: dict, m: dict) -> dict | None:
    from ...performance import etm_conferencia as C
    r = C.resultado(o.get("wid"))
    if not r or m.get("finalizado") or m.get("diagnostico_id") or o.get("coluna_etm") != "finalizada":
        return None
    return {"estado": r.get("estado"), "curto": r.get("curto") or "", "texto": r.get("texto") or ""}


def faixa_etm(oss: list[dict], hoje, sem_marcas: bool = False, sem_leitura: bool = False) -> list[dict]:
    """Os quatro números da tela ETMs. "Abertas para a Performance" é a regra das Estações em Aberto do app: a OS só sai
    quando a Engenharia encerra (o diagnóstico ou o finalizado), não quando o Fracttal fecha a tarefa. Sem leitura
    nenhuma do Fracttal ainda, os quatro são "—" (número pela metade não vai para a tela)."""
    if sem_leitura:
        nota = [("lendo o Fracttal", False)]
        return [{"rotulo": r, "valor": "—", "grav": "", "nota": nota} for r in
                ("Abertas no Fracttal", "Abertas para a Performance", "Em acompanhamento",
                 f"Finalizadas em {JANELA_CONCLUIDAS} dias")]
    abertas = [o for o in oss if o["coluna"] in ("nao_iniciada", "em_andamento")]
    por = collections.Counter(o["trabalho"] for o in abertas)
    para_eng = [o for o in oss if o["coluna"] != "cancelada" and not o["diagnostico"] and not o["finalizado"]]
    usinas = len({o["usina"] for o in para_eng})
    piso = (hoje - timedelta(days=JANELA_CONCLUIDAS)).isoformat()
    fechadas = sum(1 for o in oss if o["coluna"] == "finalizada" and (o["fim_dia"] or "") >= piso)
    return [
        {"rotulo": "Abertas no Fracttal", "valor": len(abertas), "grav": "",
         "nota": [(str(por["engenharia"]), True), (" com a engenharia, ", False), (str(por["chamados"]), True),
                  (" com chamados, ", False), (str(por["campo"]), True), (" em campo", False)]},
        {"rotulo": "Abertas para a Performance", "valor": "—" if sem_marcas else len(para_eng),
         "grav": "" if sem_marcas or not para_eng else "alerta",
         "nota": [("sem as marcações agora", False)] if sem_marcas else
                 [("em ", False), (str(usinas), True), (" usina" + ("s" if usinas != 1 else ""), False),
                  (", sem diagnóstico nem o finalizado", False)]},
        {"rotulo": "Em acompanhamento", "valor": "—" if sem_marcas else sum(1 for o in oss if o["acompanhamento"]),
         "grav": "", "nota": [("seguidas mesmo depois de fechadas no Fracttal", False)]},
        {"rotulo": f"Finalizadas em {JANELA_CONCLUIDAS} dias", "valor": fechadas, "grav": "",
         "nota": [("no Fracttal", False)]},
    ]


# o comentário obrigatório do Finalizar pela Performance (25/11/2026, Levi: "deve ser obrigatório, eu coloco um comentário
# [...] na linha do tempo [...] vai ter lá, finalizado por tal pessoa, e aí o comentário [...] caso aquela ETM venha dar
# falha de novo, quando eu for clicar vai aparecer a linha do tempo inteira dela"): vai para o livro dos comentários da OS
# (`nexus_engenharia_os`, o mesmo do Chat da usina, que não se apaga com a OS fechada) com este começo, e a linha do tempo
# o mostra como "Finalizada pela Performance", com quem e o texto. Fica no Nexus: a OS fechada no Fracttal não aceita nota
COMENTARIO_FIM = "Finalizado pela Performance: "
NOTA_FIM = "o comentário do Finalizar fica no Nexus"


def texto_do_fim(texto) -> str:
    """O comentário do Finalizar, conferido ANTES de marcar (nada se marca sem ele)."""
    from ...engenharia import os_acompanhamento as O
    if not str(texto or "").strip():
        raise O.Recusada("O comentário é obrigatório para finalizar: escreva o que foi feito ou visto na ETM")
    return O.texto_do_comentario(texto)


def comentar_fim(oss: list[dict], texto: str, pode: bool) -> list[str]:
    """O comentário do Finalizar em cada OS finalizada; devolve as OS em que não gravou (o resto gravou)."""
    from ...engenharia import os_acompanhamento as O
    falhas = []
    for o in oss:
        try:
            O.registrar_comentario(o, COMENTARIO_FIM + texto, session.get("usuario"), pode, NOTA_FIM)
        except Exception:       # noqa: BLE001 — a marcação já foi: diz quais ficaram sem o comentário
            logging.exception("ETMs: o comentário do Finalizar da OS %s não gravou", o.get("folio"))
            falhas.append(str(o.get("folio")))
    return falhas


LOTE_MAX = 500          # OS num Finalizar em lote (a usina com mais OS de ETM tinha dezenas em 26/10/2026)
LENDO_ETM = "Lendo as OS de ETM no Fracttal agora; tente de novo em instantes"


def _usinas_da_etm(d: dict, oss: list[dict]) -> list[dict]:
    """As usinas do Histórico: as das ETMs (com quantas ETMs cada uma tem; a usina sem OS também entra, como no app) e
    as das OS, por cliente e nome curto."""
    from ...engenharia import etm as ETM
    from ...engenharia import os_equipe
    etms = d.get("usinas") or {}
    nomes = set(etms) | {o["usina"] for o in oss if o.get("usina")}
    us = [{"nome": n, "curta": ETM.usina_curta(n), "cliente": ETM.cliente_de(n), "etms": etms.get(n, 0)} for n in nomes]
    return sorted(us, key=lambda u: (os_equipe._norm(u["cliente"]), os_equipe._norm(u["curta"]), u["nome"]))


@bp.route("/etm")
def etm():
    """As OS das Estações Meteorológicas (o app de ETM da Engenharia) nas três abas do app: o Planner (as colunas e os
    filtros dele no navegador), o Histórico (cliente → usina → OS, com o chat da usina) e as Estações em Aberto (as
    usinas com OS aberta para a Performance e as em acompanhamento). Quem volta com ?atualizar=1 relê o Fracttal na hora."""
    from ...engenharia import etm as ETM
    from ...engenharia import etm_marcas as M
    from ...engenharia import os_acompanhamento as O
    import logging
    ETM.marcar_uso()                # relida por trás nas próximas 2 h (`etm.manter_quente`)
    from flask import current_app
    from ...performance import etm_conferencia as C
    C.pedir(current_app._get_current_object())       # a conferência pelos dados do PG, por trás (meia em meia hora)
    # a volta da OS depois de trocar o responsável relê só aquela OS, num pedido (24/11/2026: a tela inteira são 15, e a
    # volta de cada OS relia tudo na hora e esbarrava na cota); o Fracttal que recusa deixa a cópia como estava, e a tela diz
    releia, aviso_releia = str(request.args.get("releia") or ""), ""
    if releia.isdigit():
        try:
            ETM.reler_os(releia)
        except Exception as e:      # noqa: BLE001 — 429 ou rede: a cópia fica como estava
            logging.warning("ETMs: a OS %s não foi relida (%s: %s)", releia, type(e).__name__, str(e)[:160])
            aviso_releia = (f"Não consegui reler a OS {releia} no Fracttal agora ({type(e).__name__}): ela aparece como "
                            "estava na cópia; recarregue em instantes.")
    # com cópia (a da memória ou a do disco), a leitura vai sempre por trás; sem nenhuma, a 1ª pessoa espera a leitura
    ETM.pedir_releitura(esperar=not ETM.dados()["lido"], forcar=request.args.get("atualizar") == "1")
    d = ETM.dados()
    lido = M.ler()
    erro_marcas = "" if lido.get("lido_em") else (lido.get("erro") or "").split(":")[0]
    est = M.estado(lido["eventos"]) if not erro_marcas else {}
    # quantos comentários cada OS tem (a lista do Histórico); sem o livro, a lista não diz
    lc = O.ler()
    n_coment = O.comentarios_por_os(lc["eventos"]) if lc.get("lido_em") else None
    oss = [_os_do_planner(o, est.get(str(o.get("wid"))),
                          None if n_coment is None else n_coment.get(O.chave_da_os(o.get("wid")), 0))
           for o in d["os"]]
    hoje = datetime.now(BRT).date()
    pode, _meu = _quem_pode_etm()
    from ...engenharia import os_equipe
    agora = datetime.now(BRT)

    def hora(ts):
        if not ts:
            return "—"
        q = datetime.fromtimestamp(ts, BRT)
        return q.strftime("às %H:%M") if q.date() == agora.date() else q.strftime("em %d/%m às %H:%M")
    return render_template(
        "performance/etm.html", torre=TORRE, tela=TORRE.tela("etm"), oss=oss, colunas=ETM.COLUNAS,
        usinas=_usinas_da_etm(d, oss), pode=pode,
        kpis=faixa_etm(oss, hoje, sem_marcas=bool(erro_marcas), sem_leitura=not d["lido"]), erro=d["erro"],
        erro_marcas=erro_marcas, nunca_lido=not d["lido"], lendo=d["lendo"], erro_setores=d.get("erro_setores") or "",
        # os status da OS no Fracttal, na ordem dele (o filtro "Status da OS", 26/10/2026)
        status=list(os_equipe.STATUS_OS.values()), hoje=hoje.isoformat(),
        admin=bool(session.get("admin")),           # o painel do histórico do app de ETM (uma vez, só o administrador)
        lido=hora(d["lido"]), erro_hora=hora(d.get("erro_em")).replace("às ", "").replace("em ", ""),
        aviso_releia=aviso_releia, pode_comentar=_quem_pode_na_os()[0], comentario_fim=COMENTARIO_FIM,
        # a volta da Nova demanda (`demandas_tela.demanda_nova`, ?etm=1): o aviso dela na tela
        aviso_ok=(request.args.get("ok") or "")[:300], aviso_erro=(request.args.get("erro") or "")[:300])


@bp.route("/etm/finalizar", methods=["POST"])
def etm_finalizar():
    """O "Finalizar pela Performance" em lote do quadro da usina nas Estações em Aberto (como no app): as OS que a pessoa
    viu na coluna Finalizadas, conferidas aqui na última leitura do Fracttal (da usina pedida e finalizadas nele) e no
    livro (sem diagnóstico nem o finalizado), numa gravação só. As outras voltam em "fora" (não são da usina, não estão
    finalizadas no Fracttal) ou em "ja" (a Engenharia já encerrou)."""
    import logging

    from ...engenharia import etm as ETM
    from ...engenharia import etm_marcas as M
    from ...auth.origem import de_outro_site as _de_outro_site
    if _de_outro_site():
        abort(403)
    pode, _meu = _quem_pode_etm()
    corpo = request.get_json(silent=True)
    # o pedido torto não vira OS chutada: "35" era lido letra a letra (as OS 3 e 5) e a lista no lugar do objeto dava 500
    if not (isinstance(corpo, dict) and isinstance(corpo.get("usina"), str) and corpo["usina"]
            and isinstance(corpo.get("os"), list) and len(corpo["os"]) <= LOTE_MAX):
        return jsonify({"erro": "Pedido sem a usina ou a lista das OS"}), 400
    d = ETM.dados()
    if not d["lido"]:               # a cópia vazia depois de subir: "fora" diria que nenhuma está mais finalizada
        ETM.pedir_releitura()
        return jsonify({"erro": LENDO_ETM}), 503
    from ...engenharia import os_acompanhamento as O
    if not pode:                    # quem não finaliza ouve isso antes do "falta o comentário"
        return jsonify({"erro": "Só quem é da Performance ou administrador finaliza as OS de ETM"}), 403
    try:
        texto = texto_do_fim(corpo.get("comentario"))
    except O.Recusada as e:
        return jsonify({"erro": str(e)}), 400
    usina = corpo["usina"]
    pedidas = list(dict.fromkeys(str(x).strip() for x in corpo["os"] if str(x).strip()))
    alvo = {str(o["os"]): o for o in d["os"]
            if o.get("usina") == usina and o.get("coluna_etm") == "finalizada" and o.get("wid")}
    fora = [f for f in pedidas if f not in alvo]
    gravar = [_os_para_gravar(_na_etm(alvo[f])) for f in pedidas if f in alvo]
    try:
        r = M.finalizar_lote(gravar, session.get("usuario"), pode)
    except M.Recusada as e:
        return jsonify({"erro": str(e)}), 403
    except Exception as e:      # noqa: BLE001 — banco fora: nada mudou (a trava recusa antes de gravar)
        logging.exception("ETMs: o finalizar em lote da usina não gravou")
        return jsonify({"erro": FALHOU_BANCO.format(type(e).__name__)}), 502
    sem = comentar_fim([g for g in gravar if str(g.get("folio")) in set(r["feitas"])], texto, pode) if r["feitas"] else []
    return jsonify({"feitas": r["feitas"], "ja": r["ja"], "fora": fora, "sem_comentario": sem})


@bp.route("/etm/usina/comentarios")
def etm_usina_comentarios():
    """O "Chat da usina" do Histórico (como no app): os comentários em todas as OS de ETM da usina, o mais
    novo primeiro, com o número e o título da OS. A cifra abre aqui, no clique, só para as OS da usina."""
    from ...engenharia import etm as ETM
    from ...engenharia import os_acompanhamento as O
    usina = request.args.get("usina") or ""
    d = ETM.dados()
    if not d["lido"]:               # a cópia vazia depois de subir: "nenhum comentário" seria mentira
        ETM.pedir_releitura()
        return jsonify({"erro": LENDO_ETM}), 503
    oss = {O.chave_da_os(o.get("wid")): o for o in d["os"] if o.get("usina") == usina and o.get("wid")}
    lido = O.ler()
    if not lido.get("lido_em"):
        motivo = (lido.get("erro") or "sem leitura").split(":")[0]
        return jsonify({"erro": f"Não consegui ler os comentários ({motivo}); tente de novo em instantes"}), 503
    est = O.estado([l for l in lido["eventos"] if O.chave_da_os(l.get("os_id")) in oss])
    out, ilegiveis = [], 0
    for wid, e in est.items():
        o = oss[wid]
        for ev in e["eventos"]:
            if ev["evento"] != "comentario":
                continue
            if not ev["texto"]:     # a cifra de outra chave (ou sem a chave): conta, para a gaveta dizer
                ilegiveis += 1
                continue
            out.append((ev["quando"] or datetime.min.replace(tzinfo=timezone.utc),
                        {"os": str(o["os"]), "titulo": o.get("titulo") or "", "nome": ev["nome"] or "alguém",
                         "quando": ev["quando_txt"], "texto": ev["texto"],
                         "iso": ev["quando"].isoformat() if ev["quando"] else ""}))
    out.sort(key=lambda x: x[0], reverse=True)
    # as demandas da usina (25/11/2026): as que citam uma OS de ETM dela ou a usina do Nexus (pelo retrato das OS)
    dem, erro_dem = [], ""
    try:
        folios = {int(o["os"]) for o in oss.values() if str(o.get("os")).isdigit()}
        uid, _ = _usina_no_retrato(folios)
        dem = demandas_das(folios, uid)
    except Exception as e:      # noqa: BLE001 — o banco das demandas fora: a gaveta diz, os comentários seguem
        import logging
        logging.exception("ETMs: as demandas da usina %s não vieram", usina)
        erro_dem = type(e).__name__
    return jsonify({"usina": usina, "comentarios": [c for _, c in out], "ilegiveis": ilegiveis, "demandas": dem,
                    "erro_demandas": erro_dem})


@bp.route("/etm/os/<int:folio>")
def etm_os(folio: int):
    """A OS de ETM (26/10/2026): a página da OS da Engenharia com as marcações do app de ETM no lugar do status e da
    prioridade, o checklist da OS e as marcações na linha do tempo. OS que não é de ETM abre a página comum."""
    return _pagina_da_os(folio, "etm")


@bp.route("/etm/os/<int:folio>/marcar", methods=["POST"])
def etm_os_marcar(folio: int):
    """As marcações da OS de ETM: o diagnóstico e o status pós-OS num formulário só (um evento por mudança), e a
    etiqueta, o acompanhamento e o finalizado um botão cada (liga ou desliga)."""
    import logging
    from urllib.parse import urlencode

    from ...engenharia import etm_marcas as M
    from ...engenharia import os_equipe
    from ...auth.origem import de_outro_site as _de_outro_site
    if _de_outro_site():
        abort(403)
    pode, _meu = _quem_pode_etm()
    volta = url_for("torre_performance.etm_os", folio=folio)
    try:
        o = os_equipe.ler_os(folio)                     # a OS conferida agora no Fracttal, não o que o formulário diz
        if not o:
            raise M.Recusada(f"Não achei a OS {folio} no Fracttal")
        osg, quem, f = _os_para_gravar(_na_etm(o)), session.get("usuario"), request.form
        ev = f.get("evento")
        if ev == "finalizado" and f.get("ligado") == "sim":
            from ...engenharia import os_acompanhamento as O
            try:
                texto = texto_do_fim(f.get("comentario"))
            except O.Recusada as e:
                raise M.Recusada(str(e))
            aviso = M.marcar(osg, ev, True, quem, pode)["aviso"]
            sem = comentar_fim([osg], texto, pode)
            q = {"ok": "Salvo: " + aviso + ("." if not sem else "; o comentário não gravou, comente de novo na OS.")}
            return redirect(volta + "?" + urlencode(q), 303)
        if ev in ("etiqueta", "acompanhamento", "finalizado"):
            lig = f.get("ligado") == "sim"
            avisos = [M.marcar(osg, ev, (f.get("valor"), lig) if ev == "etiqueta" else lig, quem, pode)["aviso"]]
            return redirect(volta + "?" + urlencode({"ok": "Salvo: " + "; ".join(avisos) + "."}), 303)
        # o diagnóstico e o status pós-OS são duas gravações: a que entrou e a que falhou são ditas as duas (revisão
        # final de 26/10/2026: o diagnóstico salvo aparecia como "Nada mudou")
        avisos, falha = [], ""
        for campo in ("diagnostico", "status_pos"):
            if f.get(campo) is None:
                continue
            try:
                avisos.append(M.marcar(osg, campo, f.get(campo), quem, pode)["aviso"])
            except M.Recusada as e:
                if str(e) != "Nada mudou":
                    falha = str(e)
                    break
            except Exception as e:      # noqa: BLE001 — o banco fora no meio: o que já entrou é dito
                logging.exception("ETMs: a marcação %s da OS %s não gravou", campo, folio)
                falha = f"Não consegui gravar no banco ({type(e).__name__}); tente de novo em instantes"
                break
        if not avisos and not falha:
            falha = "Nada mudou"
        q = {}
        if avisos:
            q["ok"] = "Salvo: " + "; ".join(avisos) + "."
        if falha:
            q["erro"] = falha
        return redirect(volta + "?" + urlencode(q), 303)
    except M.Recusada as e:
        return redirect(volta + "?" + urlencode({"erro": str(e)}), 303)
    except Exception as e:      # noqa: BLE001 — banco ou Fracttal fora: nada mudou (a trava recusa antes de gravar)
        logging.exception("ETMs: a marcação da OS %s não gravou", folio)
        return redirect(volta + "?" + urlencode({"erro": FALHOU_BANCO.format(type(e).__name__)}), 303)


# ── a Nova demanda da ETM (25/11/2026) ───────────────────────────────────────────────────────────────────────────────
# Levi, 25/11/2026: "poder criar demanda [...] alguém da performance poder passar para outra pessoa da performance". É a
# demanda da Caixa de entrada (o mesmo livro, os mesmos passos, o sininho), como a do chamado de Garantias
# (`demandas_tela.contexto_do_chamado`): o setor Performance fixo, o tema "Verificação de ativo" já escolhido, a usina pela
# OS aberta de ETM no retrato das OS (`fato_tarefa_os`) e só as OS que o retrato tem (a Caixa recusa a OS fora da usina).
# A janela pede isto no clique, para a tela não pagar a leitura do retrato a cada abertura.
TEMA_DA_ETM = "Verificação de ativo"


def _usina_no_retrato(folios: set) -> tuple:
    """(usina_id do Nexus, {nº das OS que o retrato tem}) das OS de ETM abertas de uma usina; (None, set()) fora dele."""
    from ...campo import visao
    from ...dados import fato_tarefa_os as FT
    uid, achadas = None, set()
    for t in visao._livro(FT.LIVRO, FT.ABA):
        try:
            n, u = int(t.get("os") or 0), int(t.get("usina_id") or 0)
        except (TypeError, ValueError):
            continue
        if n in folios and u:
            uid = uid or u
            if u == uid:
                achadas.add(n)
    return uid, achadas


@bp.route("/etm/usina/demanda")
def etm_usina_demanda():
    """O que a janela da Nova demanda da usina precisa: a chave do formulário, as pessoas do setor Performance (menos quem
    pede), os temas da Performance (sem os da área Chamados), a usina do Nexus e as OS abertas que dá para vincular."""
    from ...cadastro import setor_ids as SID
    from ...comando import demandas as D
    from ...engenharia import etm as ETM
    from ...prefixo import na_raiz
    from ..comando import _codigo, _meu_hmac
    usina = request.args.get("usina") or ""
    falta = D.faltam_chaves()
    if falta:
        return jsonify({"erro": "As demandas não gravam neste servidor (falta " + ", ".join(falta) + ")."}), 503
    meu = _meu_hmac()
    if not meu:
        return jsonify({"erro": "Para pedir, entre com a sua conta da Grid (Microsoft ou Fracttal)."}), 403
    d = ETM.dados()
    abertas = sorted((o for o in d["os"] if o.get("usina") == usina and o.get("coluna_etm") in ("nao_iniciada", "em_andamento")),
                     key=lambda o: o.get("criada_iso") or "", reverse=True)
    try:
        temas = [t for t in D.temas(SID.PERFORMANCE) if not t.get("area")]
        pessoas = [p for p in D.pessoas_com_setor() if p["setor_id"] == SID.PERFORMANCE and p["hmac"] != meu]
        uid, no_retrato = _usina_no_retrato({int(o["os"]) for o in abertas if str(o.get("os")).isdigit()})
    except Exception as e:      # noqa: BLE001 — o banco fora: a janela diz, nada é enviado
        import logging
        logging.exception("ETMs: a Nova demanda da usina %s não abriu", usina)
        return jsonify({"erro": f"Não consegui ler o banco agora ({type(e).__name__}). Tente de novo em instantes."}), 503
    nome_usina = ""
    if uid:
        try:
            from ...campo import visao
            nome_usina = (visao._Base().por_id.get(uid) or {}).get("nome") or ""
        except Exception:       # noqa: BLE001 — sem o nome do cadastro, vai o do Fracttal
            nome_usina = ""
    dia = lambda n: f"{n} {'dia útil' if n == 1 else 'dias úteis'}"   # noqa: E731
    return jsonify({
        "codigo": _codigo(), "novo_id": D.novo_id("d"), "setor_id": str(SID.PERFORMANCE),
        "acao": na_raiz("/t/comando/caixa-de-entrada/demandas/nova?etm=1"),
        "usina": [uid, nome_usina or ETM.usina_curta(usina)] if uid else None,
        "oss": [{"os": str(o["os"]), "titulo": o.get("titulo") or ""} for o in abertas if int(o["os"]) in no_retrato],
        "pessoas": [{"hmac": p["hmac"], "nome": p["nome"]} for p in sorted(pessoas, key=lambda p: p["nome"].lower())],
        "temas": [{"tema_id": t["tema_id"], "nome": f"{t['nome']} ({dia(t['prazo_dias_uteis'])})"} for t in temas],
        "tema_padrao": next((t["tema_id"] for t in temas if t["nome"] == TEMA_DA_ETM), ""),
        "limites": {"titulo": D.TITULO_MAX, "texto": D.TEXTO_MAX}})


# ── as demandas na linha do tempo (25/11/2026) ───────────────────────────────────────────────────────────────────────
# Levi, 25/11/2026: "Quando eu criar uma nova demanda, vai aparecer também na linha do tempo? Tem que aparecer [...] Na
# linha do tempo da OS". Entram as demandas da Caixa de entrada que citam uma OS de ETM da usina (a da abertura ou a de uma
# mensagem, o `oss` da demanda) ou a usina do Nexus; cada uma com quem pediu, para quem, o tema, a situação e o último
# passo, e o link para a Caixa, onde a conversa mora. Sem as chaves das demandas ou com o banco fora, não entram (e quem
# chama diz).
def demandas_das(folios, usina_id=None) -> list[dict]:
    """As demandas que citam alguma das OS (`folios`) ou a usina (`usina_id`), a mais nova primeiro."""
    from ...comando import demandas as D
    from ...prefixo import na_raiz
    if D.faltam_chaves():
        return []
    alvo = {int(f) for f in folios if str(f).isdigit()}
    hoje = datetime.now(BRT).date()
    out = []
    for d in D.lista(hoje, D.ler()):
        oss = set(d.get("oss") or [])
        if not (oss & alvo or (usina_id and any(u == usina_id for u, _ in d.get("usinas") or []))):
            continue
        q = d.get("registrado_em") or ""
        u = (d.get("passos") or [None])[-1]
        out.append({"id": d["demanda_id"], "titulo": d.get("titulo") or "(sem o texto)", "de": d.get("de_nome") or "",
                    "para": d.get("para_nome") or "", "tema": d.get("tema_nome") or "",
                    "situacao": (d.get("estado") or {}).get("rotulo") or "", "tom": (d.get("estado") or {}).get("tom") or "",
                    "aberta": bool((d.get("estado") or {}).get("aberta")), "iso": q,
                    "quando": d.get("aberta_txt") or "", "os": next((str(n) for n in d.get("oss") or [] if n in alvo), ""),
                    "ultimo": (f"{u['nome'] or 'Alguém'} {u['rotulo']}" + (f": {u['texto']}" if u.get("texto") else "")
                               + (f" · {u['quando_txt']}" if u.get("quando_txt") else "")) if u else "",
                    "caixa": na_raiz("/t/comando/caixa-de-entrada") + f"?d={d['demanda_id']}#demandas"})
    return sorted(out, key=lambda x: x["iso"], reverse=True)


# a conferência automática das OS de ETM pelos dados diários do PG (25/11/2026): a guardada em disco na subida e a rodada
# de meia em meia hora (fora dos testes), `performance/etm_conferencia.py`
def _ligar_conferencia(estado):
    from ...performance import etm_conferencia as C
    C.ligar(estado.app)


bp.record_once(_ligar_conferencia)
