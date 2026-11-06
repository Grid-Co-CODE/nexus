"""As rondas da zeladoria lidas do Fracttal pelo Nexus (etapa 5, 06/11/2026): o lugar da função `fracttal-sync` do Radar.

No Supabase, uma tarefa agendada (a cada 2 min) chamava a função, que a cada 2 h relia no Fracttal as OS criadas desde o
último corte menos 1 dia, separava as de ronda e gravava `fracttal_rondas`; a view `rf_fracttal_ultimas` dava a última
ronda de cada usina. É disso que vivem a Criticidade e a última ronda de cada usina no app.

Por que ler o Fracttal, e não as rondas da Usinas 360°: as duas vêm da mesma OS de ronda, e onde as duas têm a OS os níveis
batem (1.191 OS, 2.378 comparações, 06/11/2026), mas o Radar tinha 205 rondas de agosto e setembro que não passaram pelo
App de Campo, e o fato da Usinas 360° só conhece o que o App publica. A regra aqui é a do Radar, linha por linha
(`fracttal-sync/index.ts` e `_shared/fracttal.ts`): o que é ronda, a usina, o tipo, os níveis lidos da nota.

Só onde a gravação está ligada (o servidor, depois da troca): antes dela, as rondas vêm da cópia do Supabase. Grava pelo
gravador da Zeladoria (diário e lote), só as linhas que mudaram. Lê pelo leitor do Fracttal do Nexus, como fundo declarado
no porteiro (a cota de 200 pedidos por minuto é da empresa inteira). As fotos não são guardadas: o app as busca no
Fracttal na hora (`fracttal-fotos`).
"""
import re
import threading
import unicodedata
from datetime import datetime, timedelta, timezone

PAGINA = 100
MAX_PAGINAS = 12                    # o teto de uma volta da função do Radar pelo agendamento
A_CADA = timedelta(hours=2)         # o "recente" do Radar: a cada 2 h (o botão força na hora)
DIA = timedelta(days=1)
_BRT = timezone(timedelta(hours=-3))
SISTEMA = {"status": "aprovado", "papel": "HEAD", "email": "nexus:rondas-do-fracttal"}
# o que não conta na comparação: a hora em que a linha foi lida e o que era das fotos salvas no Supabase
FORA_DA_COMPARACAO = {"atualizado_em", "fotos_salvas_em", "fotos_qtd", "fotos_tentativas", "fotos_erro"}
_UMA_VEZ = threading.Lock()


class LimiteFracttal(RuntimeError):
    """O Fracttal recusou pela cota da empresa: a volta para e continua na próxima."""


def chave_usina(s) -> str:
    """A mesma normalização do Radar (sem acento, minúsculas, " - " uniforme, espaços juntos): a chave da usina."""
    t = unicodedata.normalize("NFD", str(s or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"\s*-\s*", " - ", t)
    return re.sub(r"\s+", " ", t).strip()


def eh_ronda(o: dict) -> bool:
    d = str(o.get("description") or "")
    return bool(re.match(r"^\s*ronda\b", d, re.I)) or (
        bool(re.search(r"\bronda\b", d, re.I)) and str(o.get("tasks_log_types_2_description") or "").lower() == "zeladoria")


def _data_brt(v) -> str | None:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return str(v)[:10]
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(_BRT).date().isoformat()


def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def para_linha(o: dict, agora_iso: str) -> dict | None:
    """Uma OS de ronda do REST vira a linha de `fracttal_rondas`, como no Radar; sem usina, None."""
    desc = str(o.get("description") or "")
    partes = desc.split(" — ")
    usina = str(o.get("groups_1_description") or "").strip() or (partes[1].strip() if len(partes) > 1 else "")
    if not usina:
        return None
    nota = str(o.get("task_note") or o.get("note") or "")

    def n(padrao):
        m = re.search(padrao, nota, re.I)
        return int(m.group(1)) if m else None

    quando = o.get("initial_date") or o.get("date_maintenance") or o.get("creation_date")
    tipo = re.search(r"ronda\s+(curta|longa)", desc, re.I)
    tecnico = str(o.get("personnel_description") or o.get("user_assigned") or o.get("created_by") or "").strip()
    return {
        "folio": str(o.get("wo_folio")), "id_work_order": _int(o.get("id_work_order")), "data": _data_brt(quando),
        "data_hora": quando, "tipo": tipo.group(1).capitalize() if tipo else None,
        "usina_texto": usina, "usina_chave": chave_usina(usina), "codigo_ativo": o.get("code"),
        "sujidade": n(r"sujidade dos m[oó]dulos\s*:\s*(\d+)"), "vegetacao": n(r"vegeta[cç][aã]o\s*:\s*(\d+)"),
        "qualidade": n(r"qualidade\s*(\d+)\s*%"), "tecnico": tecnico or None,
        "status": _int(o.get("id_status_work_order")), "descricao": desc[:300], "resumo": nota[:2000],
        "atualizado_em": agora_iso,
    }


def _ordem(r: dict):
    return (str(r.get("data") or ""), str(r.get("data_hora") or ""), _int(r.get("folio")) or 0)


def ultimas(rondas) -> list:
    """A view `rf_fracttal_ultimas` do Radar: por usina, a última ronda que não foi cancelada; a nota da última que tem
    nível; e o total. A regra saiu da comparação com a view (120 de 120 usinas, 06/11/2026)."""
    por = {}
    for r in rondas:
        if r.get("status") == 4 or not r.get("usina_chave"):
            continue
        por.setdefault(r["usina_chave"], []).append(r)
    out = []
    for chave, lst in por.items():
        lst = sorted(lst, key=_ordem, reverse=True)
        top = lst[0]
        nota = next((x for x in lst if x.get("sujidade") is not None or x.get("vegetacao") is not None), None)
        out.append({
            "usina_chave": chave, "usina_texto": top.get("usina_texto"), "folio": top.get("folio"), "data": top.get("data"),
            "tipo": top.get("tipo"), "tecnico": top.get("tecnico"), "qualidade": (nota or top).get("qualidade"),
            "codigo_ativo": top.get("codigo_ativo"), "sujidade": nota.get("sujidade") if nota else None,
            "vegetacao": nota.get("vegetacao") if nota else None, "folio_nota": nota.get("folio") if nota else None,
            "data_nota": nota.get("data") if nota else None, "total_rondas": len(lst),
            "fotos_salvas_em": top.get("fotos_salvas_em"), "fotos_qtd": top.get("fotos_qtd"),
            "fotos_tentativas": top.get("fotos_tentativas"),
        })
    return out


def _igual(a: dict | None, b: dict) -> bool:
    if a is None:
        return False
    for k, v in b.items():
        if k in FORA_DA_COMPARACAO:
            continue
        x = a.get(k)
        if (x is None) != (v is None) or (x is not None and str(x) != str(v)):
            return False
    return True


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).isoformat(timespec="seconds")


def _quando(v) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def ler_paginas(desde: datetime, ate: datetime, ler, max_paginas: int = MAX_PAGINAS) -> tuple[list, int, bool]:
    """(as OS de ronda, páginas lidas, completo) das OS CRIADAS entre `desde` e `ate`, como a função do Radar."""
    from ..campo import fracttal
    ler = ler or fracttal.ler
    fmt = "%Y-%m-%dT%H:%M:%S-00"
    rondas, paginas, ini = [], 0, 0
    while paginas < max_paginas:
        try:
            r = ler(f"work_orders?since={desde.astimezone(timezone.utc).strftime(fmt)}"
                    f"&until={ate.astimezone(timezone.utc).strftime(fmt)}&type_date=creation_date&limit={PAGINA}&start={ini}")
        except fracttal.Recusado as e:
            # 429/406 é a cota da empresa; sem credencial é outra coisa, e diz o que é
            if "excesso de pedidos" in str(e):
                raise LimiteFracttal(str(e)[:200]) from None
            raise
        paginas += 1
        dados = (r.get("data") if isinstance(r, dict) else r) or []
        rondas += [o for o in dados if eh_ronda(o)]
        if len(dados) < PAGINA:
            return rondas, paginas, True
        ini += PAGINA
    return rondas, paginas, False


def sincronizar(g, ler=None, agora: datetime | None = None, forcar: bool = False) -> dict:
    """Uma volta: relê o recente (a cada 2 h, ou na hora com `forcar`) e grava pelo gravador só o que mudou.
    {"ok", "gravadas", "paginas", "erro", "ocupado"?}, a resposta que o botão do Radar espera."""
    if not _UMA_VEZ.acquire(blocking=False):
        return {"ok": False, "ocupado": True, "gravadas": 0}
    try:
        agora = agora or datetime.now(timezone.utc)
        agora_iso = _iso(agora)
        st = next((dict(l) for l in g.estado["abas"].get("fracttal_sync", []) if l.get("id") == "principal"), {"id": "principal"})
        ultima = _quando(st.get("ultima_sync_recente"))
        if not forcar and ultima and agora - ultima < A_CADA:
            return {"ok": True, "gravadas": 0, "paginas": 0, "erro": None, "pulou": True}
        corte = _quando(st.get("recente_ate")) or agora
        erro, os_lidas, paginas, completo = None, [], 0, False
        try:
            os_lidas, paginas, completo = ler_paginas(corte - DIA, agora + DIA, ler)
        except LimiteFracttal:
            erro = "Limite de consultas do Fracttal atingido (200/min para a empresa toda); continua sozinho na próxima volta."
        except Exception as e:  # noqa: BLE001 — Fracttal fora, sem credencial: a volta registra e a próxima tenta
            erro = f"O Fracttal não respondeu agora ({type(e).__name__}); a próxima volta tenta de novo."
        novas = {}
        for o in os_lidas:
            linha = para_linha(o, agora_iso)
            if linha:
                novas[linha["folio"]] = linha
        atuais = {str(l.get("folio")): l for l in g.estado["abas"].get("fracttal_rondas", [])}
        mudaram = [l for f, l in novas.items() if not _igual(atuais.get(f), l)]
        juntas = dict(atuais)
        for l in mudaram:
            juntas[l["folio"]] = {**(atuais.get(l["folio"]) or {}), **l}
        ult_novas = {u["usina_chave"]: u for u in ultimas(juntas.values())}
        ult_atuais = {str(u.get("usina_chave")): u for u in g.estado["abas"].get("fracttal_ultimas", [])}
        ult_mudaram = [u for k, u in ult_novas.items() if not _igual(ult_atuais.get(k), u)]
        ult_sairam = [k for k in ult_atuais if k not in ult_novas]
        st.update(ultima_execucao=agora_iso, ultimo_erro=erro, em_execucao_desde=None,
                  paginas_lidas=(_int(st.get("paginas_lidas")) or 0) + paginas,
                  rondas_gravadas=(_int(st.get("rondas_gravadas")) or 0) + len(mudaram))
        if completo:
            st.update(recente_ate=agora_iso, ultima_sync_recente=agora_iso)
        ops = []
        if mudaram:
            ops.append({"op": "upsert", "view": "rf_fracttal_rondas", "linhas": mudaram})
        if ult_mudaram:
            ops.append({"op": "upsert", "view": "rf_fracttal_ultimas", "linhas": ult_mudaram})
        ops += [{"op": "delete", "view": "rf_fracttal_ultimas", "filtros": [["eq", "usina_chave", k]]} for k in ult_sairam]
        ops.append({"op": "upsert", "view": "rf_fracttal_sync", "linhas": [st]})
        g.aplicar(ops, SISTEMA, g.estado["versao"], interno=True)
        return {"ok": not erro, "gravadas": len(mudaram), "paginas": paginas, "erro": erro, "estado": st}
    finally:
        _UMA_VEZ.release()
