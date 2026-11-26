"""Concluir a OS de ETM no Fracttal antes de finalizar pela Performance (25/11/2026).

Levi, 25/11/2026: "para essas que a gente for finalizar pela performance e não tiver o S concluído ainda, a gente pode fazer
esse trabalho de concluir. E aí teria que colocar a data fim de tarefa de um por um [...] a data início [...] no primeiro
comentário, se não tiver nenhum início de atividade, nenhum comentário, a gente pode botar a data início a mesma data da
criação da OS [...] não pode concluir sem terminar a tarefa" (a OS concluída sem tarefa feita suja o dado do PCM).

Roda na sessão do Fracttal de quem conclui (o cookie do OS Creator, como o comentário que vai à nota da OS, `ponte.py`), com
as MESMAS funções do card da OS do OS Creator:
- `GET /os/_nexus/etm/os/<id>/concluir?folio=<nº>`: as tarefas da OS, cada uma com o início e o fim que já tem, o início
  sugerido (o da tarefa; sem ele, o 1º comentário da OS no Nexus; sem comentário, a criação da OS) e as subtarefas
  obrigatórias sem resposta;
- `POST` (JSON `{folio, comentario, tarefas: [{id, inicio, fim}]}`): confere TUDO antes de escrever (quem pode, o
  comentário, o checklist obrigatório respondido, a data fim de cada tarefa sem fim, fim depois do início e não no
  futuro); lança o registro de execução de cada tarefa sem fim (`registrar_execucao`, o "fazer a tarefa" do card), relê a OS
  e só conclui (`concluir_os_checado`, com a reconferência da data fim) se nenhuma tarefa ficou sem fim. Concluída no
  Fracttal, a OS é finalizada pela Performance no Nexus, com o comentário na linha do tempo.
A tarefa que já tem fim não é mexida. Parou no meio (o Fracttal recusou uma tarefa): as de antes ficam com o fim, a OS NÃO é
concluída, e a resposta diz qual parou.
"""
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

from flask import current_app, jsonify, request, session

from ...prefixo import na_raiz
from .ponte import bp_raiz, clone, sessao_do_os, _trava_da_os

BRT = timezone(timedelta(hours=-3))
NOTA_EXECUCAO = "Concluída pela Performance no Nexus (Finalizar da ETM)"
FOLGA_FUTURO = timedelta(minutes=5)          # o relógio da máquina de quem preenche pode estar uns minutos à frente
VOLTA = "/t/performance/etm"


def _login() -> str:
    return na_raiz("/os/login") + "?next=" + quote("/os/_nexus/card/voltar?" + urlencode({"de": VOLTA}, safe="/"), safe="")


def _quando(v) -> datetime | None:
    """A data do Fracttal ("2026-11-20T15:00:00Z", "2026-11-20 15:00:00") como datetime com fuso (sem fuso: UTC)."""
    t = str(v or "").strip().replace(" ", "T").replace("Z", "+00:00")
    if not t:
        return None
    try:
        d = datetime.fromisoformat(t)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _do_campo(v) -> datetime | None:
    """O que o <input type="datetime-local"> manda ("2026-11-20T12:00"), em Brasília."""
    t = str(v or "").strip()
    if not t:
        return None
    try:
        return datetime.fromisoformat(t).replace(tzinfo=BRT)
    except ValueError:
        return None


def _campo(d: datetime | None) -> str:
    return d.astimezone(BRT).strftime("%Y-%m-%dT%H:%M") if d else ""


def _txt(d: datetime | None) -> str:
    return d.astimezone(BRT).strftime("%d/%m/%Y %H:%M") if d else ""


def _primeiro_comentario(wid) -> datetime | None:
    """O 1º comentário da OS no Nexus (sem o do próprio Finalizar): o início sugerido de quem não iniciou a tarefa."""
    from ...engenharia import os_acompanhamento as O
    from ..performance.etm_tela import COMENTARIO_FIM
    try:
        est = O.estado(O.ler()["eventos"]).get(O.chave_da_os(wid)) or {}
    except Exception:            # noqa: BLE001 — sem o livro, vale a criação da OS
        return None
    qs = [e["quando"] for e in est.get("eventos") or [] if e.get("evento") == "comentario" and e.get("quando")
          and not str(e.get("texto") or "").startswith(COMENTARIO_FIM)]
    return min(qs) if qs else None


def _erro(texto: str, status: int = 400, **extra):
    return jsonify(dict({"erro": texto}, **extra)), status


@bp_raiz.route("/os/_nexus/etm/os/<int:wid>/concluir", methods=["GET", "POST"])
def etm_concluir(wid: int):
    from ...auth.origem import de_outro_site
    from ...engenharia import etm as ETM
    from ...engenharia import etm_marcas as M
    from ...engenharia import os_equipe
    from ..engenharia import _na_etm, _os_para_gravar, _quem_pode_etm
    from ..performance.etm_tela import comentar_fim, texto_do_fim
    post = request.method == "POST"
    if post and de_outro_site():
        return _erro("Pedido de outro site: nada foi feito.", 403)
    pode, _meu = _quem_pode_etm()
    if not pode:
        return _erro("Só quem é da Performance ou administrador conclui as OS de ETM.", 403)
    c = (request.get_json(silent=True) or {}) if post else {}
    folio = str((c.get("folio") if post else request.args.get("folio")) or "").strip()
    if not folio.isdigit():
        return _erro("Pedido sem o nº da OS.")
    texto = ""
    if post:
        try:
            texto = texto_do_fim(c.get("comentario"))
        except Exception as e:   # noqa: BLE001 — a Recusada do livro: o texto diz o que falta
            return _erro(str(e))
    o = os_equipe.ler_os(folio)                          # o REST da empresa: o status de agora, sem a sessão da pessoa
    if not o or str(o.get("wid")) != str(wid):
        return _erro("Não achei esta OS no Fracttal: recarregue a página.", 404)
    if o.get("status") in ("Concluída", "Cancelada"):
        return _erro(f"A OS {folio} já está {o['status'].lower()} no Fracttal: use o Finalizar das concluídas.", 409)
    app = current_app._get_current_object()
    s = sessao_do_os(app)
    jwt = str(s.get("jwt") or "")
    if not jwt:
        return _erro("Para concluir no Fracttal, entre pelo Fracttal.", 401, login=_login())
    clone(app)
    import api as os_api                                 # noqa: E402 — o `api` do clone (o `clone` põe no sys.path)
    from os_web import os_acoes_web as regra            # noqa: E402
    from os_web import sessao as os_sessao               # noqa: E402
    criada = _quando(o.get("criada_iso"))
    primeiro = _primeiro_comentario(wid)
    sugerido, origem = (primeiro, "o 1º comentário da OS") if primeiro else (criada, "a criação da OS")
    try:
        with _trava_da_os(folio), os_sessao.contexto(jwt, str((s.get("conta") or {}).get("email") or "")):
            d = os_api.get_os_detalhes(wid) or {}
            tarefas = [t for t in d.get("tarefas") or [] if isinstance(t, dict) and t.get("id") is not None]
            if not tarefas:
                return _erro("O Fracttal não devolveu as tarefas da OS agora. Nada foi feito; tente de novo.", 502)
            rot = regra.rotulos_tarefas(tarefas)
            sem_fim = [t for t in tarefas if not str(t.get("fim") or "").strip()]
            faltam = {t["id"]: regra.faltando_obrigatorias(os_api.subtarefas_da_tarefa(t["id"]), {}) for t in sem_fim}
            if not post:
                return jsonify({
                    "folio": folio, "status": o.get("status") or "", "origem_inicio": origem,
                    "tarefas": [{"id": t["id"], "rotulo": rot.get(t["id"]) or t.get("titulo") or t.get("ativo") or "Tarefa",
                                 "inicio": _campo(_quando(t.get("inicio"))), "fim": _txt(_quando(t.get("fim"))),
                                 "feita": bool(str(t.get("fim") or "").strip()),
                                 "sugerido": _campo(_quando(t.get("inicio")) or sugerido),
                                 "faltam": faltam.get(t["id"]) or []} for t in tarefas]})
            # ── o POST: conferir tudo antes de escrever qualquer coisa ──
            pendentes = [f"{rot.get(t) or 'tarefa'}: {', '.join(f[:3])}" for t, f in faltam.items() if f]
            if pendentes:
                return _erro("Há subtarefa obrigatória sem resposta (" + "; ".join(pendentes[:3]) + "). Responda o "
                             "checklist na página da OS antes de concluir. Nada foi feito.")
            datas = {str(x.get("id")): x for x in c.get("tarefas") or [] if isinstance(x, dict)}
            agora, plano, erros = datetime.now(timezone.utc), [], []
            for t in sem_fim:
                nome, x = rot.get(t["id"]) or "tarefa", datas.get(str(t["id"])) or {}
                ini = _quando(t.get("inicio")) or _do_campo(x.get("inicio"))
                fim = _do_campo(x.get("fim"))
                if not ini:
                    erros.append(f"{nome}: falta a data de início")
                elif not fim:
                    erros.append(f"{nome}: falta a data fim")
                elif fim < ini:
                    erros.append(f"{nome}: a data fim é anterior ao início")
                elif fim > agora + FOLGA_FUTURO:
                    erros.append(f"{nome}: a data fim está no futuro")
                elif criada and ini < criada - timedelta(days=1):
                    erros.append(f"{nome}: o início é anterior à criação da OS")
                else:
                    plano.append((t, nome, ini, fim))
            if erros:
                return _erro("Confira as datas (" + "; ".join(erros[:4]) + "). Nada foi feito.")
            # ── escrever: cada tarefa, a releitura e só então a conclusão ──
            for t, nome, ini, fim in plano:
                try:
                    os_api.registrar_execucao(t["id"], ini, fim, note=NOTA_EXECUCAO)
                except os_api.SessionExpired:
                    raise
                except Exception as e:   # noqa: BLE001 — o Fracttal recusou: para aqui, sem concluir
                    logging.warning("ETM %s: a tarefa %s não fechou (%s)", folio, t["id"], str(e)[:160])
                    return _erro(f"O Fracttal recusou a tarefa \"{nome}\" ({str(e)[:160]}). As anteriores ficaram com "
                                 "a data fim; a OS NÃO foi concluída.", 502)
            d2 = os_api.get_os_detalhes(wid) or {}
            resta = regra.tarefas_sem_fim(d2.get("tarefas")) if d2.get("tarefas") else ["(o Fracttal não devolveu as tarefas)"]
            if resta:
                return _erro("Ainda sem data fim no Fracttal: " + "; ".join(resta[:4]) + ". A OS NÃO foi concluída.", 502)
            r = os_api.concluir_os_checado(wid)
            if isinstance(r, dict) and r.get("ok") is False:
                return _erro("O Fracttal não concluiu a OS: " + str(r.get("msg") or "motivo não informado") + ".", 502)
    except os_api.SessionExpired:
        return _erro("A sessão do Fracttal venceu: entre de novo.", 401, login=_login())
    except Exception as e:       # noqa: BLE001 — Fracttal fora, cota
        logging.exception("ETM %s: a conclusão no Fracttal falhou", folio)
        return _erro(f"O Fracttal não respondeu ({type(e).__name__}). Confira a OS antes de tentar de novo.", 502)
    try:
        from os_web import lista_central                 # noqa: E402 — o Histórico do OS Creator vê a OS concluída
        lista_central.mudou(wid)
    except Exception:            # noqa: BLE001
        pass
    # concluída no Fracttal: a cópia das ETMs, a marcação e o comentário do Finalizar
    avisos = []
    try:
        ETM.reler_os(folio)
    except Exception:            # noqa: BLE001 — a cópia se acerta na próxima leitura
        avisos.append("a tela se atualiza na próxima leitura")
    osg = _os_para_gravar(_na_etm(o))
    try:
        M.marcar(osg, "finalizado", True, session.get("usuario"), pode)
    except M.Recusada as e:
        if str(e) != "Nada mudou":
            avisos.append(f"o finalizado não gravou ({e})")
    except Exception as e:       # noqa: BLE001
        logging.exception("ETM %s: concluída no Fracttal, o finalizado não gravou", folio)
        avisos.append(f"o finalizado não gravou ({type(e).__name__}): finalize de novo")
    if comentar_fim([osg], texto, pode):
        avisos.append("o comentário não gravou: comente de novo na OS")
    # a data fim da OS é a do fim da última tarefa (a que acabou de fechar ou a que já tinha)
    fins = [f for f in [_quando(t.get("fim")) for t in tarefas] + [p[3] for p in plano] if f]
    msg = f"OS {folio} concluída no Fracttal" + (f" (data fim {_txt(max(fins))})" if fins else "") +           " e finalizada pela Performance."
    return jsonify({"ok": True, "mensagem": msg + (" Atenção: " + "; ".join(avisos) + "." if avisos else ""),
                    "folio": folio})
