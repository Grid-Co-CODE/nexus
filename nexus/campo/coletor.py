"""O coletor da torre Campo · App: lê o Fracttal devagar, calcula a nota de cada tarefa que entrou na fila de
verificação e grava na API do PG (banco_campo.py). Levi, 04/10/2026: "pode gravar na API do PG e ligar as telas".

Ritmo: a cota do Fracttal é de 200 pedidos por minuto para a EMPRESA inteira, e o App de Campo vive dela (no domingo
04/10, perto das 20h, ela já estava esgotada). Por isso: uma pausa de PAUSA_S antes de cada pedido, no máximo MAX_OS
ordens novas por rodada (MAX_OS_NOITE fora do horário de campo) e a rodada PARA no primeiro 406/429: grava o que já
calculou e continua na próxima.

O que entra: toda tarefa da fila de verificação (status 2), a mais recente primeiro. Por ordem nova:
- OS de ronda: a nota é a que o próprio App escreveu no texto da OS ("Ronda ... · qualidade 87%"); nenhum pedido;
- as fotos (1 pedido). Sem a marca das fotos do App (pelo_app), a tarefa foi fechada fora dele e não há o que julgar,
  como no painel do App ("Fechadas fora do App"); com a marca, as subtarefas (mais 1 pedido) e as duas notas.
Tarefa que já está no banco só é relida se a data de fim mudou (voltou ao técnico e foi fechada de novo: devolvida) ou
se saiu da fila (aprovada, status 3, ou devolvida, status 1: 1 pedido por OS, e só com a fila lida INTEIRA, senão
uma página perdida para o 429 viraria um monte de "saídas" falsas).
A linha só muda (e só ganha `lido_em` novo) quando algo do Fracttal mudou: a API guarda histórico por linha.

Roda a cada NEXUS_CAMPO_COLETOR_MIN minutos (30) dentro do processo do Nexus, mas só onde NEXUS_CAMPO_COLETOR=1: uma
máquina só, senão duas leem a mesma fila e gastam a cota em dobro. À mão: ferramentas/coletar_campo.py.
"""
import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone

from . import banco_campo, fracttal, ligacao_cadastro, nota_fracttal, regras_app

log = logging.getLogger(__name__)

PAUSA_S = 2.0           # antes de cada pedido, no horário de campo: ~25 por minuto, um oitavo da cota da empresa
PAUSA_NOITE_S = 1.0     # fora dele: ~40 por minuto (a 1ª carga, 10.896 tarefas, não cabia na madrugada a 2 s)
# 429 de madrugada: espera e repete o MESMO pedido, em vez de encerrar a rodada. Na 1ª carga (04/10, 23:20 em diante)
# cada rodada levava um 429 a cada ~10 min, esperava 5 min e relia a fila inteira (~118 pedidos) antes de voltar às
# notas: o ritmo caiu de 43 para 17 tarefas por minuto. O próprio Fracttal diz "try again after 1 minute".
ESPERA_429_S = 90
TENTATIVAS_429_NOITE = 3
MAX_OS = 40             # ordens novas por rodada no horário de campo (até 2 pedidos cada)
MAX_OS_NOITE = 1000     # fora dele a cota sobra; com pendência, as rodadas emendam (espera_s)
MAX_SAIDAS = 60         # ordens que saíram da fila, relidas por rodada (1 pedido cada)
JANELA_DIAS = 90        # as aprovadas que as telas olham (Ordens de serviço e Triagem vão até 90 dias)
GRAVAR_A_CADA = 100     # na carga longa, grava a cada tantas OS: interromper não perde o que já foi feito
PAGINA = 100
FILA = "work_orders?id_status_work_order=2&limit=100&start={ini}&sort=final_date"   # a ordem do _fila_bruta do App
# As aprovadas, da mais recente para a mais antiga. Medido em 04/10: 22.304 no total, 5.646 com fim nos últimos 90
# dias (~63 páginas por rodada), numa ordem só aproximada (a página tem dias fora de ordem): por isso a leitura para
# quando a página INTEIRA passou do piso.
APROVADAS = "work_orders?id_status_work_order=3&limit=100&start={ini}&sort=final_date:desc"
# _resumo_curto_ronda do App: "Ronda <dia> · <usina> · qualidade 87% · duração real 34 min (...) — respostas"
_RONDA = re.compile(r"^\s*Ronda\s+(\d{4}-\d{2}-\d{2})\s+·\s+(.*?)\s+·\s+qualidade\s+(\d{1,3})\s*%"
                    r"(?:\s+·\s+duração real\s+(\d+)\s+min\s+\((\d{2}:\d{2}) às (\d{2}:\d{2})\))?"
                    r"(?:\s+—\s+(.*))?\s*$", re.S)
_HORA_DO_APP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$")    # foto.ts = toISOString()
_GPS_DO_APP = re.compile(r"^GPS\s+-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?$")
_ARQUIVO_DO_APP = re.compile(r"(-[0-9a-f]{8}|OS\d+-foto\d+-[0-9a-f]{12})\.[A-Za-z0-9]{2,5}(\?|$)")   # subir_fotos
SEM_NOTA = {"nota": None, "nota_itens": None, "nota_placar": None, "pontos_placar": None, "n_desc": None,
            "gps_fotos": None, "sub_ok": None, "todas_sub": None, "obs_ok": None, "ronda_dia": None, "ronda_usina": None,
            "ronda_duracao_min": None, "ronda_hora_ini": None, "ronda_hora_fim": None, "ronda_respostas": None,
            "ronda_pendencias": None, "ronda_lida": None}


def _int(v):
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _txt(v, limite=200):
    s = " ".join(str(v or "").split())
    return s[:limite] if s and s.lower() != "none" else None


def _min(seg):
    # durações em SEGUNDOS no Fracttal; a conta do _enriquecer_qlog do App
    try:
        return int(round(float(seg or 0) / 60.0))
    except (TypeError, ValueError):
        return 0


def utc(v) -> str | None:
    """A data do Fracttal em UTC, "AAAA-MM-DDTHH:MM:SS" (o formato que as regras do App comparam)."""
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def pelo_app(anexos) -> bool:
    """A tarefa foi fechada pelo App? A marca está nas fotos que ele sobe: a descrição leva a hora da foto
    (toISOString) e o GPS, e o arquivo leva o nome que o subir_fotos dá ("desc-1a2b3c4d.jpg", "OS15377-foto2-...")."""
    for a in anexos or []:
        partes = [p.strip() for p in str(a.get("description") or "").split(" · ")]
        if any(_HORA_DO_APP.match(p) or _GPS_DO_APP.match(p) for p in partes):
            return True
        if _ARQUIVO_DO_APP.search(str(a.get("value") or "")):
            return True
    return False


def ronda(w) -> dict | None:
    """O que o App escreveu na OS da ronda (_resumo_curto_ronda): dia, usina, nota de qualidade, duração real (a do
    celular: o real_duration do Fracttal infla quando a ronda sobe offline) e as respostas do checklist."""
    for campo in ("note", "task_note"):
        m = _RONDA.match(str(w.get(campo) or ""))
        if m:
            return {"dia": m.group(1), "usina": m.group(2).strip()[:120], "nota": int(m.group(3)),
                    "duracao": int(m.group(4)) if m.group(4) else None, "ini": m.group(5), "fim": m.group(6),
                    "respostas": (m.group(7) or "").strip()[:3800] or None}
    return None


def _ronda_da_os(w, ant, anexos, subs, base):
    """A linha da OS de ronda: o que o App escreveu no texto da OS, o campo "Pendências e ocorrências" (o que o
    supervisor lê para aprovar: falhas, item sem resposta, trackers com desvio, achados) e as fotos."""
    r = ronda(w)
    k = _int(w.get("id_work_orders_tasks"))
    fotos = [a for a in anexos if _int(a.get("id_work_order_task")) == k]
    pend = next((s.get("value") for s in subs if _int(s.get("id_work_order_task")) == k
                 and re.search(r"pend|ocorr", regras_app._norm(s.get("description") or ""))), None)
    return {**base(w, ant), **SEM_NOTA, "pelo_app": True, "ronda": True, "nota": r["nota"], "ronda_dia": r["dia"],
            "ronda_usina": r["usina"], "ronda_duracao_min": r["duracao"], "ronda_hora_ini": r["ini"],
            "ronda_hora_fim": r["fim"], "ronda_respostas": r["respostas"], "ronda_pendencias": _txt(pend, 3800),
            "n_fotos": len(fotos), "gps_fotos": any(nota_fracttal.descricao_da_foto(a.get("description"))[1]
                                                     for a in fotos),
            "ronda_lida": True}


def contexto_do_tecnico(id_tarefa) -> str:
    return f"{banco_campo.WORKBOOK}/{banco_campo.ABA}/{id_tarefa}/tecnico"


def _cofre(config):
    chave = config.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        return None
    from ..cadastro.cifra import CifraErro, Cofre
    try:
        return Cofre(chave)
    except CifraErro as e:
        log.warning("coletor campo: chave do cadastro inválida (%s); o nome do técnico não vai", e)
        return None


def _cifrar(cofre, w, ant):
    """O nome do técnico cifrado. O texto que já está no banco volta igual quando o nome não mudou (a cifra tem nonce
    aleatório: cifrar de novo mudaria a linha toda rodada). Sem a chave, fica o que já estava."""
    if cofre is None:
        return (ant or {}).get("tecnico_cifrado")
    nome = _txt(w.get("personnel_description"), 120)
    if not nome:
        return None
    from ..cadastro.cifra import CifraErro
    ctx = contexto_do_tecnico(_int(w.get("id_work_orders_tasks")))
    velho = (ant or {}).get("tecnico_cifrado")
    if velho:
        try:
            if cofre.decifrar(velho, ctx) == nome:
                return velho
        except CifraErro:
            pass
    return cofre.cifrar(nome, ctx)


def _ativo(w) -> str | None:
    """A usina e o código do ativo. NÃO a descrição inteira do Fracttal: o `items_log_description` traz o ENDEREÇO da
    usina ("Thopen - Indaiatuba 1 - SP Estrada IDT 150, S/N Indaiatuba ... { THPN-IND100 }"), que no cadastro do Nexus
    é dado sensível e vai cifrado; a leitura da API do PG não pede credencial. Foi em claro na 1ª carga (04/10, 20:55
    a 05/10, 00:2x) e sai na rodada seguinte, que regrava todas as linhas."""
    partes = (_txt(w.get("groups_1_description"), 120), _txt(w.get("code"), 60))
    return " · ".join(p for p in partes if p) or None


def _metadados(w, mapas=None) -> dict:
    """O que o Fracttal diz da tarefa: os mesmos campos que o _enriquecer_qlog do App copia para o registro dele. Com os
    `mapas` do cadastro, também o usina_id e o pessoa_id; sem eles (cadastro fora do ar), as duas colunas ficam como
    estavam no banco."""
    ids = {} if mapas is None else {
        "usina_id": ligacao_cadastro.usina_id(mapas, w.get("groups_1_description")),
        "pessoa_id": ligacao_cadastro.pessoa_id(mapas, w.get("personnel_description"))}
    return ids | {"id_tarefa": _int(w.get("id_work_orders_tasks")), "os": _txt(w.get("wo_folio"), 20),
            "id_os": _int(w.get("id_work_order")), "tarefa": _txt(regras_app._txt_tarefa(w)),
            "tecnico_id": _int(w.get("id_personnel")), "equipe": _txt(w.get("groups_1_description"), 60),
            "regiao": _txt(w.get("groups_2_description"), 60), "ativo": _ativo(w),
            "codigo": _txt(w.get("code"), 60), "tipo": _txt(w.get("tasks_log_task_type_main"), 60),
            "crit": _txt(w.get("priorities_description"), 30), "status_os": _int(w.get("id_status_work_order")),
            "status_tarefa": _int(w.get("id_status_work_order_task")), "inicio": utc(w.get("initial_date")),
            "fim": utc(w.get("final_date")), "verificacao": utc(w.get("review_date")),
            "aprovacao": utc(w.get("wo_final_date")), "dur_prev_min": _min(w.get("duration")),
            "dur_real_min": _min(w.get("real_duration")), "rating": _int(w.get("rating")) or None}


def _atualizar(ant, w, cofre, agora_iso, mapas=None):
    """A linha do banco com o que o Fracttal mudou (status, avaliação, datas), sem nota nova. None = nada mudou."""
    alvo = {**ant, **_metadados(w, mapas), "tecnico_cifrado": _cifrar(cofre, w, ant)}
    if banco_campo.normalizar(alvo) == banco_campo.normalizar(ant):
        return None
    alvo["lido_em"] = agora_iso
    return alvo


def _notas_da_ordem(folio, tarefas, ler, cofre, agora_iso, mapas=None) -> list:
    """As linhas das tarefas pendentes de uma OS, com a nota. `tarefas` = [(linha da fila, linha do banco ou None)]."""
    def base(w, ant):
        l = {**_metadados(w, mapas), "tecnico_cifrado": _cifrar(cofre, w, ant), "lido_em": agora_iso,
             "regua": regras_app.CODIGO_APP}
        # voltou ao técnico e foi fechada de novo (a data de fim mudou): é retrabalho, como o foi_devolvida do App
        l["devolvida"] = bool(ant and (ant.get("devolvida") or ant.get("fim") != l["fim"]))
        return l

    anexos = nota_fracttal.anexos_da_os(folio, ler)
    if all(ronda(w) for w, _ in tarefas):
        subs = nota_fracttal.subtarefas_da_os(folio, ler)
        return [_ronda_da_os(w, ant, anexos, subs, base) for w, ant in tarefas]
    da_tarefa = {}
    for a in anexos:
        da_tarefa.setdefault(_int(a.get("id_work_order_task")), []).append(a)
    do_app = {_int(w.get("id_work_orders_tasks")) for w, _ in tarefas
              if pelo_app(da_tarefa.get(_int(w.get("id_work_orders_tasks"))))}
    subs = nota_fracttal.subtarefas_da_os(folio, ler) if do_app else []
    linhas = []
    for w, ant in tarefas:
        l = base(w, ant)
        k = l["id_tarefa"]
        if k in do_app:
            n = nota_fracttal.nota(subs, anexos, tarefa=k)
            l.update(pelo_app=True, ronda=False, nota=n["q"],
                     nota_itens=json.dumps(n["itens"], ensure_ascii=False)[:6000], nota_placar=n["placar"]["q"],
                     pontos_placar=n["placar"]["pontos"], n_fotos=n["n_fotos"], n_desc=n["n_desc"],
                     gps_fotos=n["geo_ok"], sub_ok=n["sub_ok"], todas_sub=n["todas"], obs_ok=n["obs_ok"])
        else:
            l.update(SEM_NOTA, pelo_app=False, ronda=False, n_fotos=len(da_tarefa.get(k) or []))
        linhas.append(l)
    return linhas


def _paginas(ler, modelo, parar=None) -> list:
    """Todas as páginas (ou até `parar(página)` dizer chega). O 429 sobe: lista pela metade não serve a ninguém."""
    out, ini = [], 0
    while True:
        r = ler(modelo.format(ini=ini))
        pagina = (r.get("data") if isinstance(r, dict) else r) or []
        out += pagina
        if len(pagina) < PAGINA or (parar and parar(pagina)):
            return out
        ini += PAGINA


def _por_id(linhas) -> dict:
    out = {}
    for w in linhas:
        k = _int(w.get("id_work_orders_tasks"))
        if k is not None and k not in out:
            out[k] = w
    return out


def rodar(config, *, max_os=None, pausa_s=None, sessao=None, agora=None, gravar_a_cada=GRAVAR_A_CADA,
          relogio=None, espera_429_s=ESPERA_429_S) -> dict:
    """Uma rodada: fila e aprovadas do Fracttal -> notas do que falta -> banco. Devolve o relatório (sem segredo).
    Rodada que começou de madrugada e chegou ao horário de campo para ali e grava: a próxima já sai no ritmo do dia."""
    from ..pcm.geracao import horario_de_campo
    agora = agora or datetime.now(timezone.utc)
    relogio = relogio or (lambda: datetime.now(timezone.utc))
    agora_iso = agora.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    piso = (agora.astimezone(timezone.utc) - timedelta(days=JANELA_DIAS)).strftime("%Y-%m-%dT%H:%M:%S")
    noturna = not horario_de_campo(agora)
    if max_os is None:
        max_os = MAX_OS_NOITE if noturna else MAX_OS
    if pausa_s is None:
        pausa_s = PAUSA_NOITE_S if noturna else PAUSA_S
    base_api = (config.get("GRIDCO_DB_API") or banco_campo.BASE_API).rstrip("/")
    token = config.get("GRIDCO_SQL_TOKEN")
    cofre = _cofre(config)
    rel = {"inicio": agora_iso, "virou_dia": False, "fila": 0, "aprovadas": 0, "novas": 0, "notas": 0, "saidas": 0,
           "pedidos": 0, "esperas_429": 0,
           "pendentes": 0, "completa": False, "parou": False, "parou_por": None, "gravadas": 0, "conferidas": 0,
           "erro": None}

    def ler(path):
        tentativa = 0
        while True:
            if pausa_s:
                time.sleep(pausa_s)
            rel["pedidos"] += 1
            try:
                return fracttal.ler(path)
            except fracttal.Recusado:
                # de dia a cota é do App: para no primeiro 429. De madrugada, espera e repete (ESPERA_429_S)
                if not noturna or tentativa >= TENTATIVAS_429_NOITE:
                    raise
                tentativa += 1
                rel["esperas_429"] += 1
                time.sleep(espera_429_s)

    def parou(e):
        rel.update(parou=True, parou_por=str(e)[:200])

    atual, atu_ant = banco_campo.ler_tudo(base_api, sessao)
    novo = {k: dict(v) for k, v in atual.items()}
    try:
        mapas = ligacao_cadastro.mapas(config, sessao)
    except Exception as e:      # noqa: BLE001 — sem o cadastro, as colunas de ID ficam como estavam
        mapas = None
        log.warning("coletor campo: cadastro não lido (%s); usina_id e pessoa_id ficam como estavam", type(e).__name__)

    def gravar(pendentes):
        """Grava só se mudou alguma coisa (linhas ou a cobertura) e confere lendo de volta."""
        linhas = list(novo.values())
        cobertura = "sim" if rel["completa"] else "não"
        if (len(novo) == len(atual) and all(banco_campo.normalizar(l) == atual.get(l["id_tarefa"]) for l in linhas)
                and str(atu_ant.get("completa") or "") == cobertura):
            return
        if not token:
            rel["erro"] = "sem GRIDCO_SQL_TOKEN no .env do Nexus: calculado e não gravado"
            return
        resumo = banco_campo.resumo(linhas, regras_app.CODIGO_APP, completa=rel["completa"], pendentes=pendentes,
                                    fila=rel["fila"], aprovadas=rel["aprovadas"], janela_dias=JANELA_DIAS)
        try:
            g = banco_campo.gravar(linhas, resumo, base=base_api, token=token, sessao=sessao)
        except Exception as e:      # noqa: BLE001 — o relatório diz o que houve; a próxima rodada tenta de novo
            rel["erro"] = f"{type(e).__name__}: {e}"[:300]
            return
        rel.update(gravadas=g["gravadas"], conferidas=g["conferidas"])
        atual.clear()
        atual.update({k: banco_campo.normalizar(v) for k, v in novo.items()})
        atu_ant["completa"] = cobertura

    # 1) a fila de verificação inteira e as aprovadas da janela (a mais recente primeiro, até passar do piso). Lista
    #    pela metade não serve: sem as duas inteiras, a rodada para aqui e a próxima tenta de novo.
    try:
        na_fila = _por_id(_paginas(ler, FILA))
        aprovadas = _paginas(ler, APROVADAS,
                             parar=lambda p: max((utc(w.get("final_date")) or "") for w in p) < piso)
    except fracttal.Recusado as e:
        parou(e)
        return rel
    na_janela = {k: w for k, w in _por_id(aprovadas).items()
                 if k not in na_fila and (utc(w.get("final_date")) or "") >= piso}
    rel["fila"], rel["aprovadas"] = len(na_fila), len(na_janela)

    # 2) o que precisa de nota (nova ou fechada de novo) e o que só mudou de status
    pendentes = {}
    for k, w in {**na_janela, **na_fila}.items():
        ant = novo.get(k)
        # a ronda gravada antes de 05/10 só tinha a nota: relê para guardar as respostas, as pendências e as fotos
        if ant is None or ant.get("fim") != utc(w.get("final_date")) or (ant.get("ronda") and not ant.get("ronda_lida")):
            pendentes.setdefault(_txt(w.get("wo_folio"), 20), []).append((w, ant))
        else:
            mudou = _atualizar(ant, w, cofre, agora_iso, mapas)
            if mudou:
                novo[k] = mudou
    rel["novas"] = sum(len(v) for v in pendentes.values())

    # 3) o que estava na fila e saiu sem virar aprovada da janela: devolvida (1), cancelada, ou aprovada com o fim
    #    antes do piso
    sairam = {}
    for k, l in novo.items():
        if l.get("status_os") == 2 and k not in na_fila and k not in na_janela:
            sairam.setdefault(l["os"], []).append(k)
    for folio, ks in list(sairam.items())[:MAX_SAIDAS]:
        try:
            tarefas = nota_fracttal.tarefas_da_os(folio, ler)
        except fracttal.Recusado as e:
            parou(e)
            break
        por_id = {_int(t.get("id_work_orders_tasks")): t for t in tarefas}
        for k in ks:
            t = por_id.get(k)
            if t is None:
                continue
            mudou = _atualizar(novo[k], t, cofre, agora_iso, mapas) or dict(novo[k])
            if mudou.get("status_os") == 1:
                mudou["devolvida"] = True
            novo[k] = mudou
            rel["saidas"] += 1

    # 4) as notas, a OS mais recente primeiro; na carga longa, grava a cada GRAVAR_A_CADA ordens
    ordem = sorted(pendentes.items(), reverse=True,
                   key=lambda kv: max(utc(w.get("final_date")) or "" for w, _ in kv[1]))
    lote = ordem[:max_os]
    feitas = 0
    for folio, tarefas in lote:
        if rel["parou"]:
            break
        if noturna and horario_de_campo(relogio()):
            rel["virou_dia"] = True
            break
        try:
            linhas = _notas_da_ordem(folio, tarefas, ler, cofre, agora_iso, mapas)
        except fracttal.Recusado as e:
            parou(e)
            break
        for l in linhas:
            novo[l["id_tarefa"]] = l
        rel["notas"] += len(linhas)
        feitas += 1
        if gravar_a_cada and feitas % gravar_a_cada == 0 and feitas < len(lote):
            gravar(sum(len(t) for _, t in ordem[feitas:]))

    # 5) a cobertura: completa = fila e janela lidas inteiras e nada mais por calcular. As telas só saem do painel do
    #    App com ela (fonte_pg.py): número de fila pela metade seria pior do que número nenhum.
    rel["pendentes"] = sum(len(t) for _, t in ordem[feitas:])
    rel["completa"] = not rel["parou"] and rel["pendentes"] == 0
    gravar(rel["pendentes"])
    return rel


# ── rodada a cada N minutos, dentro do processo do Nexus (só onde NEXUS_CAMPO_COLETOR=1) ─────────────────────────
_LACO = {"thread": None, "ultimo": None, "parar": threading.Event()}


def espera_s(ultimo: dict | None, minutos: int, agora=None) -> int:
    """Quanto esperar até a próxima rodada. Fora do horário de campo, com coisa pendente e sem 429 nem erro, a próxima
    emenda (1 min): a 1ª carga de 04/10 tinha 10.896 tarefas (fila + aprovadas de 90 dias), ~7 h de pedidos, e com 30
    min entre rodadas não acabava antes das 6h, quando o limite cai para 40 OS por rodada. Um 429 de madrugada espera
    5 min, não 30: na 1ª carga a rodada parou às 21:2x e ficou meia hora parada à toa."""
    from ..pcm.geracao import horario_de_campo
    u = ultimo or {}
    if horario_de_campo(agora):
        return minutos * 60
    if u.get("erro"):
        return 120              # erro passageiro de madrugada (a API do PG deu 502 por 1 min em 05/10, 00:04): 2 min
    if u.get("parou"):
        return 300              # 429 de madrugada: a cota é por minuto ("try again after 1 minute"); 5 min sobra
    return 60 if (u.get("pendentes") or 0) > 0 else minutos * 60


def deve_rodar(agora=None) -> bool:
    """No horário de campo (seg a sex, 6h às 18h) o coletor NÃO roda. Segunda, 05/10, das 07:12 em diante, a cota do
    Fracttal da empresa ficou esgotada a manhã inteira (429 já no 1º pedido de cada rodada), e a lista do técnico no App
    (`/minhas-os`) depende de ler o Fracttal a cada 10 min: a OS 15423, criada às 09:53, não aparecia para ele. O Nexus
    é paralelo; o App, não. A carga fica pronta de madrugada e as telas do Nexus leem o banco."""
    from ..pcm.geracao import horario_de_campo
    return not horario_de_campo(agora)


def ligar(app):
    if _LACO["thread"] is not None:
        return
    minutos = max(5, int(app.config.get("NEXUS_CAMPO_COLETOR_MIN") or 30))

    def laco():
        while not _LACO["parar"].is_set():
            if not deve_rodar():
                _LACO["parar"].wait(minutos * 60)
                continue
            with app.app_context():
                try:
                    _LACO["ultimo"] = rodar(app.config)
                    log.info("coletor campo: %s", _LACO["ultimo"])
                except Exception as e:      # noqa: BLE001 — o laço não pode morrer por uma rodada
                    _LACO["ultimo"] = {"erro": f"{type(e).__name__}: {e}"[:300]}
                    log.exception("coletor campo")
            _LACO["parar"].wait(espera_s(_LACO["ultimo"], minutos))

    _LACO["thread"] = threading.Thread(target=laco, name="campo-coletor", daemon=True)
    _LACO["thread"].start()


def ultimo() -> dict | None:
    return _LACO["ultimo"]
