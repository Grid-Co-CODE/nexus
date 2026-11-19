"""Comando › Visão gerencial (teste), 19/11/2026: a página e o dados.json dela.

Levi, 19/11/2026, depois de aprovar o desenho em mockup com dado real: "tá massa! sobe como Visão gerencial (teste)". O
que a tela é, a nota de cumprimento do contrato e o que fica fora dela estão em `nexus/comando/gerencial.py` (puro) e no
`nexus/comando/CLAUDE.md`. Aqui só se juntam as fontes, cada uma na cópia que a tela dona já usa:

- as usinas, a meta, o PR e as OS: a conta do Usinas 360° › Usinas (`_usinas_montadas`) e a Visão do responsável;
- a disponibilidade e a meta dos meses fechados: o mês a mês do prontuário (`prontuario_dados._de_todas`);
- as rondas do mês fechado: o fechamento guardado (`nexus_atividade_mes`);
- a saúde de cada usina: a pontuação do dossiê do cliente (`dossie_cliente.pontuar`);
- o valor mensal, a vigência e a garantia de disponibilidade: o Comando › Contratos (`contratos/edicao.visao`, só leitura).

Só para quem é da Grid (o cliente não abre: a tela tem o valor dos contratos). Fonte que não abre vira aviso na tela, e o
resto vale. O nome do gestor do contrato não sai daqui (o dados.json não leva pessoa).
"""
import logging
import threading
import time

from flask import current_app, jsonify, render_template

from . import TORRE, bp
from .contratos_tela import _so_interno

_log = logging.getLogger(__name__)
COPIA_S = 60
_REFAZENDO: dict = {"thread": None}


def _f(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _contratos(hoje):
    """(o `edicao.visao` do Comando › Contratos, None) ou (None, o aviso) quando ele não abre: a tela segue sem os valores."""
    from ...contratos import edicao as E
    from .contratos_tela import _base
    try:
        base = _base()
        if not base["itens"]["cliente"]:
            return None, "os contratos (a carga inicial não está neste servidor)"
        return E.visao(base, E.aplicar(base, E.abrir(E.ler_banco())), hoje, [], None, False), None
    except Exception:            # noqa: BLE001 — o Contratos fora do ar não derruba o portfólio: os valores somem e a tela diz
        _log.exception("Visão gerencial: o Comando › Contratos não abriu")
        return None, "os contratos (o valor mensal e a garantia de disponibilidade)"


def _usinas(hoje) -> tuple[list[dict], list[str]]:
    """Uma por usina mobilizada, no formato do `gerencial.montar`, e o que ficou de fora."""
    from ...campo import visao
    from ...comando import carteira_ia as CI
    from ...comando import dossie_cliente as DC
    from ...comando import gerencial as G
    from ...comando import prontuario as PR
    from ...dados import fato_atividade_mes as AM
    from . import _carteira_ia, _usinas_montadas
    from .prontuario_dados import _de_todas
    m = _usinas_montadas()
    lei = _de_todas()
    d = lei.dados or {}
    avisos = list(m.get("avisos") or []) + list((d.get("erros") or {}).values())
    if lei.erro:
        avisos.append(f"o histórico das usinas ({lei.erro})")
    if m.get("erro"):
        avisos.append(f"a Visão do responsável ({m['erro']})")
    dz = _carteira_ia()
    brutos, mes_txt = dz.get("brutos") or {}, dz.get("mes") or "mês"
    da_visao = {u.get("usina_id"): u for u in (m.get("visao") or {}).get("usinas") or []}
    metas, disps, ms = d.get("metas") or {}, d.get("disps") or {}, G.meses(hoje)
    try:
        rondas, meses_fato = AM.rondas_por_mes(visao._livro(AM.LIVRO, AM.ABA) if any(not x["atual"] for x in ms) else [])
    except Exception:            # noqa: BLE001 — sem o fechamento guardado, as rotinas do mês fechado ficam fora da nota
        _log.exception("Visão gerencial: o fechamento guardado (nexus_atividade_mes) não abriu")
        rondas, meses_fato = {}, set()
        avisos.append("o fechamento guardado dos meses (as rondas do mês fechado)")
    out = []
    for l in m.get("linhas") or []:
        uid, nome = l.get("usina_id"), CI._t(l.get("usina"))
        if not uid or not nome:
            continue
        vu = da_visao.get(uid) or {}
        man, dias = vu.get("manutencao") or {}, PR._int((vu.get("ronda") or {}).get("dias"))
        nunca = dias is not None and dias >= 999            # 999 é a marca de "nunca teve ronda" da Visão
        prog, semana = PR._int(man.get("passada_prog")) or 0, str(man.get("passada") or "")
        meses = {}
        for x in ms:
            mid = x["id"]
            dd = (disps.get(mid) or {}).get(uid) or {}
            if x["atual"]:
                meses[mid] = {"meta": _f(l.get("atingimento")), "pr": _f(l.get("pr")), "pr_prev": _f(l.get("pr_meta")),
                              "disp": _f(dd.get("disp"))}
                continue
            mes_id = int(mid[:4]) * 100 + int(mid[5:7])
            mt = (metas.get(mes_id) or {}).get(uid) or {}
            meses[mid] = {"meta": _f(mt.get("atingimento")), "pr": _f(mt.get("pr")), "pr_prev": _f(mt.get("pr_meta")),
                          "disp": _f(dd.get("disp")),
                          # o mês que o fato tem é zero de verdade para a usina sem ronda; o que ele não tem, None
                          "rondas": AM.rondas_do_mes(rondas, meses_fato, uid, mes_id)}
        out.append({
            "uid": uid, "usina": nome, "cliente": l.get("cliente") or "", "codigo": l.get("codigo") or "", "mwp": _f(l.get("mwp")),
            "pontos": DC.pontuar(brutos[nome], mes_txt)[0] if nome in brutos else None,
            "ronda_dias": None if nunca else dias, "nunca_rondada": nunca,
            "plano_pct": _f(man.get("passada_pct")) if prog else None,
            "plano_txt": (f"{PR._int(man.get('passada_feitas')) or 0} de {prog} tarefas do plano"
                          + (f" · {semana.split('-')[-1]}" if semana else "")) if prog else "",
            "os_abertas": l.get("os_abertas"),
            "os_urgentes": sum(1 for o in man.get("os_nao_iniciadas") or [] if isinstance(o, dict) and o.get("urgente")),
            "os_atrasadas_n": PR._int(man.get("atrasadas_os")) or 0, "mais_antiga_d": PR._int(man.get("maior_atraso")),
            "meses": meses})
    return out, avisos


@bp.route("/visao-gerencial")
def visao_gerencial():
    """A página: o JavaScript pede o dados.json e desenha o portfólio, o parque do cliente e a nota da usina."""
    _so_interno()
    return render_template("comando/gerencial.html", torre=TORRE, tela=TORRE.tela("visao-gerencial"))


_ORDEM_SEV = {"critico": 0, "atencao": 1, "info": 2}


def _sem_a_usina(titulo: str, usina: str) -> str:
    """"Usina X: CAB1 sem comunicação" vira "CAB1 sem comunicação": na tela da usina, o nome dela já está no alto."""
    pre = f"{usina}: "
    return titulo[len(pre):] if usina and titulo.startswith(pre) and len(titulo) > len(pre) else titulo


@bp.route("/visao-gerencial/usina/<int:uid>/insights.json")
def visao_gerencial_insights(uid: int):
    """O que o Nexus Insights aponta AGORA na usina, para a tela da usina juntar com a nota do contrato (19/11/2026, Levi:
    "clicando na usina, eu queria que a informação fosse uma mescla do que a gente tem agora com o que a gente tem no Nexus
    Insights"). Os insights vivos (não concluídos) da usina, do mais grave para o menos, com o que a regra viu, o que
    fazer, a torre dona e com quem está; o resto (responder, assumir, a conversa) fica no Nexus Insights, aberto pelo
    `abrir`. A janela é sempre AGORA: o filtro de mês da tela vale para a nota, não para os insights."""
    from urllib.parse import quote

    from ...comando import regras as RG
    from ...prefixo import na_raiz
    from . import ES, MO, PD, _com_estado, _meu_hmac, _nomes_das_torres, _usinas_montadas, _ve_o_insight
    _so_interno()
    m = _usinas_montadas()
    vivos = [i for i in (m.get("vivos") or {}).get(uid) or [] if _ve_o_insight(i)]
    lista = _com_estado(vivos, ES.atual(), _meu_hmac(), MO.torres_da_pessoa(), peds=PD.por_objeto(PD.atual()))
    nomes = _nomes_das_torres()
    out = []
    for i in sorted(lista, key=lambda x: (_ORDEM_SEV.get(x["sev"], 9), x.get("regra") or "", x["id"])):
        if i["pedidos"]:
            com_quem = ", ".join(f"{p['nome']}: {p['sit_rotulo'] if p.get('situacao') in ('atrasado', 'hoje') else p['rotulo']}"
                                 for p in i["pedidos"])
        elif i["estado"] == "assumiu":
            com_quem = "Com você" if i["meu"] else (f"Com {i['por']}" if i["por"] else "Assumido")
        else:
            com_quem = "Ninguém avisado"
        out.append({"id": i["id"], "regra": i["regra"], "regra_nome": i["regra_nome"], "sev": i["sev"],
                    "sev_rot": i["sev_rot"], "sev_tom": i["sev_tom"], "titulo": _sem_a_usina(i.get("titulo") or "", i.get("usina") or ""),
                    "torre_nome": nomes.get(i.get("torre"), i.get("torre") or ""), "evid": list(i.get("evid") or [])[:6],
                    "acao": i.get("acao") or "", "link": na_raiz(i["link"]) if i.get("link") else "",
                    "abrir": na_raiz("/t/comando/insights") + f"?abrir={quote(i['id'], safe='')}#ins-{i['id'].replace(':', '-')}",
                    "com_quem": com_quem, "estado": i["estado"]})
    resp = jsonify({"ok": True, "janela": "agora", "calculando": bool(m.get("insights_calculando")), "insights": out,
                    "contas": {k: sum(1 for x in out if x["sev"] == k) for k in RG.SEVERIDADES}})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/visao-gerencial/dados.json")
def visao_gerencial_dados():
    """O portfólio de agora: clientes, usinas, o contrato de cada cliente e a nota de cada usina em cada mês do filtro."""
    _so_interno()
    resp = jsonify(dados_gerencial())
    resp.headers["Cache-Control"] = "no-store"
    return resp


def dados_gerencial() -> dict:
    """O portfólio de agora (`gerencial.montar`), na cópia de 1 minuto por aplicação: a conta junta cinco fontes (1,5 s
    com todas quentes, medido na bancada em 19/11/2026) e não muda de pessoa para pessoa (não leva nome nem o que cada um
    pode editar). O Comando › Nexus Insights lê a mesma cópia (19/11/2026), sem o valor dos contratos."""
    from ...campo import visao
    from ...comando import gerencial as G
    copia = current_app.extensions.setdefault("nexus_gerencial", {})
    if not copia.get("dados") or time.time() - copia.get("ts", 0) > COPIA_S:
        agora = visao._agora()
        usinas, avisos = _usinas(agora.date())
        contratos, aviso = _contratos(agora.date())
        if aviso:
            avisos.append(aviso)
        copia.update(dados=G.montar(usinas, contratos, agora.date(), agora.strftime("%d/%m/%Y às %H:%M"), avisos), ts=time.time())
    return copia["dados"]


def dados_gerencial_sem_esperar() -> dict | None:
    """A cópia do portfólio para o Comando › Nexus Insights, sem segurar o pedido (19/11/2026). Logo depois do deploy das
    14:29 o Levi abriu a tela e o portfólio ficou em "Lendo o portfólio…" até a conta fria terminar ("a tela mudou do
    nada, cadê os clientes?"; carregou depois). Agora, como o motor dos insights (`motor.sem_esperar`): com a cópia em
    dia, ela; vencida, ela mesma na hora e a nova se faz por trás; sem cópia (o Nexus acabou de subir), a conta começa por
    trás e volta None, e a tela diz que está montando e pede de novo sozinha."""
    if current_app.config.get("TESTING"):
        return dados_gerencial()
    copia = current_app.extensions.setdefault("nexus_gerencial", {})
    if copia.get("dados") and time.time() - copia.get("ts", 0) <= COPIA_S:
        return copia["dados"]
    _refazer_por_tras()
    return copia.get("dados")


def _refazer_por_tras() -> None:
    t = _REFAZENDO["thread"]
    if t is not None and t.is_alive():
        return
    app = current_app._get_current_object()

    def rodar():
        with app.app_context():
            try:
                copia = app.extensions.setdefault("nexus_gerencial", {})
                copia["ts"] = 0                      # vencida: a `dados_gerencial` refaz
                dados_gerencial()
            except Exception:    # noqa: BLE001 — a tela segue com a cópia velha, ou dizendo que está montando
                _log.exception("Visão gerencial: a conta por trás falhou")
    t = threading.Thread(target=rodar, name="nexus-gerencial", daemon=True)
    _REFAZENDO["thread"] = t
    t.start()
