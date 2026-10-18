"""Visão do responsável (12/10/2026): as usinas de cada Responsável O&M em DOIS BLOCOS, Performance (meta, PR e
disponibilidade) e Acompanhamento (rondas, PT, chamados e extintores), cada usina numa linha compacta que abre o detalhe,
e em cada bloco onde focar e o que pode esperar.

Levi, 12/10/2026: "Precisamos criar uma visão que os supervisores irão usar, uma visão que ele olha as usinas, as metas,
os problemas, onde ele deve focar, no que ele deve deixar. No caso seria separado por responsável". Depois do 1º
desenho: "aposte em um formato reduzido que quando eu expanda aparece mais informações / Separe a visão em dois blocos
(...) Seria interessante também incluir os extintores nesse acompanhamento!", aprovado no protótipo com "só tira a parte
de Tempo do COS". E: "O nexus é um ambiente centralizado e precisamos ter os dados se conversando!".

NENHUM indicador é refeito aqui com régua nova: cada número é o da tela dona dele, da MESMA fonte que o Nexus já usa, e
cada alerta usa a régua da tela dona (`REGUAS`, que a tela mostra). O que é nosso é só juntar pela usina do cadastro
(`usina_id`) e ordenar o foco. As fontes:
- Performance
  - meta do mês: o Gerencial da plataforma publicado no banco (`nexus_performance · fato_meta_usina_mes`,
    plataforma/gerencial_publicar.py), os números da Visão gerencial;
  - disponibilidade: o diário do Gerencial › Disponibilidade (`falhas_performance · disponibilidade_dia`); o mês é a
    média dos dias (a régua de lá é 12 h de sol por dia, então a média dos dias é a disponibilidade do mês);
  - ativos que falham: os sinais da Engenharia › Confiabilidade (OS de falha do Fracttal, últimos 30 dias).
- Acompanhamento
  - rondas e PT: as contas da Central de atenção e de APR e PT (`visao.atencao`, `visao.pts`);
  - chamados: as OS de acompanhamento de chamado no banco (`nexus_chamados · fato_chamado`, o mesmo dado do quadro
    Acompanhamento de chamados; `nexus/campo/chamados_acompanhamento.py`). Até 12/10 vinham da planilha de tickets
    (`tickets_performance`): mais de 1.000 "abertos", contra 18 do quadro;
  - extintores: a conta do HSEQ (`nexus/hseq/extintores.py`, o livro que o App publica).
O Tempo do COS saiu no protótipo aprovado (12/10/2026): a régua continua na tela do COS.

Cada fonte é lida à parte (regra 13 da casa: peça que falha não para as outras): a que falhou some da conta, e a tela diz
qual foi. Responsável O&M = o da ficha da usina (`usinas.responsavel_om_id`), o mesmo da Central de atenção. Só usina
MOBILIZADA (a régua das rondas). Cópia de 5 min, refeita em segundo plano (`visao._ler`).
"""
import collections
import re
import unicodedata
from datetime import date, timedelta, timezone

from . import visao

LIVRO_META, ABA_META = "nexus_performance", "fato_meta_usina_mes"
LIVRO_DISP, ABA_DISP = "falhas_performance", "disponibilidade_dia"
LIVRO_CHAMADOS, ABA_CHAMADOS = "nexus_chamados", "fato_chamado"
# as janelas (12/10/2026): a série do PR diário do Painel NOC e as OS que formaram a disponibilidade, publicadas pela
# plataforma (plataforma/gerencial_publicar.py e falhas_publicar.py)
ABA_DIA = "fato_desempenho_usina_dia"
ABA_DISP_OS = "disponibilidade_os"
LIVRO_EQUIP, ABA_EQUIP = "nexus_equipamentos", "dim_equipamento"
# os sistemas do de-para em que a chave é o NOME da usina como a planilha escreve (o Gerencial e o diário da
# disponibilidade usam esses nomes: "Santa Bárbara I", "Boa Esperança do Sul 1 e 2")
SISTEMAS_NOME = ("BD_Thopen · aba", "BD_Performance · aba", "BD_Thopen · Dados Gerais Usinas",
                 "BD_Performance · Base UFV", "Tickets · Base de dados - Usinas")

# ── As réguas (cada uma é a da tela dona; a tela mostra este texto) ───────────────────────────────────────────────
META_NA_META = 97        # Visão gerencial (atgTag): 97% ou mais = "Na meta"
META_ATENCAO = 90        # de 90% a 97% = "Atenção"; abaixo de 90% = "Abaixo"
DISP_OK = 99             # Disponibilidade (classePill): 99% ou mais = verde
DISP_CRITICO = 80        # abaixo de 80% = vermelho; entre os dois, âmbar
# o 3º bloco, embaixo dos dois na largura toda (18/10/2026, o modelo A escolhido pelo Levi): o que um supervisor tinha
# no painel próprio (OS abertas e atrasadas, tarefas paradas, semana, zeladoria), "pegando tudo do Fracttal ou Nexus"
BLOCOS = (("perf", "Performance", "Meta, PR e disponibilidade do mês"),
          ("acomp", "Acompanhamento", "Rondas, limpeza, PT, chamados e extintores"),
          ("manut", "Manutenção", "OS, tarefas paradas, semana e zeladoria"))
REGUAS = (
    ("perf", "meta", "Meta do mês", "Visão gerencial da plataforma: atingimento abaixo de 90% é crítico (Abaixo), de 90% "
                                    "a 97% é atenção, 97% ou mais está na meta. PR abaixo do PR previsto é atenção."),
    ("perf", "disp", "Disponibilidade", "Gerencial › Disponibilidade: abaixo de 80% é crítico, de 80% a 99% é atenção, "
                                        "99% ou mais está ok. O mês é a média dos dias fechados."),
    ("perf", "ativos", "Ativos falhando", "Engenharia › Confiabilidade, últimos 30 dias: crítico com 4 falhas em 30 dias "
                                          "ou 3 em 7; atenção com 3 em 30, 2 em 7 ou acima do P90 da família; monitorar "
                                          "pode esperar."),
    ("acomp", "ronda", "Rondas", "Central de atenção: nunca teve ronda, ou sem ronda há 7 dias ou mais, é crítico; ronda "
                                 "longa pendente é atenção."),
    ("acomp", "limpeza", "Limpeza", "Rondas › Sujidade e vegetação, a última leitura da usina: nível 5 ou vala obstruída "
                                    "é crítico; nível 4, vala parcial ou sensor sujo é atenção."),
    ("acomp", "pt", "PT", "APR e PT: PT esperando o De acordo há mais de 2 h é crítico; se é de hoje, vai para o "
                                "topo (técnico parado no campo agora). Esperando há menos de 2 h, atenção."),
    ("acomp", "chamados", "Chamados", "Acompanhamento de chamados: chamado de garantia em aberto com o fabricante é "
                                      "atenção (o mesmo dado do quadro, publicado no banco de hora em hora)."),
    ("acomp", "extintores", "Extintores", "Segurança · HSEQ › Extintores: recarga ou teste hidrostático vencido é "
                                          "crítico; vence em até 30 dias ou sem conferência há mais de 30 dias é atenção."),
    ("manut", "parada", "Parada agora", "As OS de parada ainda abertas no mês (a disponibilidade do Gerencial, que vem "
                                        "do Fracttal): qualquer uma, da usina inteira ou de um equipamento, é crítico e "
                                        "vai para a faixa do topo."),
    ("manut", "atrasadas", "OS atrasadas", "A régua do PCM (Gestão PCM e relatórios): tarefa aberta com a Data "
                                           "Programada há mais de 10 dias é atenção; há mais do limite que você escolhe "
                                           "no bloco (30 dias, se ninguém mudou) é crítico. Ficam de fora o backoffice, "
                                           "a tarefa parada por motivo, a OS de chamado, a zeladoria e o Teste."),
    ("manut", "paradas", "Tarefas pausadas", "Fora da programação do PCM: tarefa tirada da programação por um motivo, ou "
                                            "justificada pelo técnico no App, é atenção."),
    ("manut", "semana", "Semana passada", "Fechamento da semana do PCM: linhas do plano finalizadas ÷ linhas do plano; "
                                          "abaixo da meta de 85% é atenção. A semana vem do arquivo do PCM, copiado "
                                          "para o banco de hora em hora."),
    ("manut", "zeladoria", "Zeladoria", "As tarefas do tipo Zeladoria no Fracttal: com a data programada vencida e não "
                                        "feita, é atenção."),
)
ROTULO_AREA = {a: r for _b, a, r, _t in REGUAS}
BLOCO_DA_AREA = {a: b for b, a, _r, _t in REGUAS}
# O foco: PT parada DE HOJE vem antes de tudo (é gente parada no campo agora); depois crítico e atenção. A PT parada de
# dias anteriores continua crítica (a régua da Central), mas sem o "agora": medido em 12/10/2026, 33 das 34 PT esperando
# eram de 1 a 6 dias atrás (nunca decididas no App), e todas no topo enterravam a única de hoje
PESO = {"agora": 20, "critico": 10, "atencao": 3}
NIVEIS = ("critico", "atencao", "ok")
_BRT = timezone(timedelta(hours=-3))


# ── Nome da planilha -> usina do cadastro ───────────────────────────────────────────────────────────────────────
_ROMANOS = {"I": "1", "II": "2", "III": "3", "IV": "4", "V": "5", "VI": "6", "VII": "7", "VIII": "8", "IX": "9",
            "X": "10", "XI": "11", "XII": "12"}


def norm_nome(s) -> str:
    """Sem acento, sem caixa, pontuação vira espaço e romano vira número ("Santa Bárbara I" = "santa barbara 1"): é a
    regra que a Disponibilidade da plataforma usa para casar o PG com o BD (`norm2`)."""
    t = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().upper()
    return " ".join(_ROMANOS.get(p, p) for p in re.sub(r"[^A-Z0-9]+", " ", t).split())


class Nomes:
    """Liga o nome que a planilha escreve à usina do cadastro. Ordem: o de-para publicado dos sistemas de nome
    (`SISTEMAS_NOME`), o nome do cadastro e, por último, o nome do Fracttal (de-para "Fracttal · Classificação 1") ou o
    código. Nome que serve a duas usinas não liga (regra 4: ligação errada é pior que faltando). Medido em 12/10/2026
    com o Gerencial: 139 das 161 usinas ligam (131 pelo de-para, 4 pelo nome, 4 pelo Fracttal); as 22 que sobram são
    usinas fora do Full O&M (Ouro Branco, Delmiro Gouveia), que não estão mobilizadas no cadastro."""

    def __init__(self, b):
        por = collections.defaultdict(set)
        for d in b.de_para:
            uid = visao.D._id(d.get("usina_id"))
            if uid and str(d.get("sistema") or "").strip() in SISTEMAS_NOME and norm_nome(d.get("chave_externa")):
                por[norm_nome(d.get("chave_externa"))].add(uid)
        self.por_de_para = {k: next(iter(v)) for k, v in por.items() if len(v) == 1}
        nomes = collections.defaultdict(set)
        for uid, u in b.por_id.items():
            if str(u.get("excluido") or "").strip().lower() != "sim" and norm_nome(u.get("nome")):
                nomes[norm_nome(u.get("nome"))].add(uid)
        self.por_nome = {k: next(iter(v)) for k, v in nomes.items() if len(v) == 1}
        self.lig = b.lig

    def usina(self, nome, fracttal="", codigo="") -> tuple:
        n = norm_nome(nome)
        if n and n in self.por_de_para:
            return self.por_de_para[n], "de-para"
        if n and n in self.por_nome:
            return self.por_nome[n], "nome do cadastro"
        c = norm_nome(codigo)
        if c and c in self.por_de_para:
            return self.por_de_para[c], "de-para"
        # por último, o Fracttal (o nome "Cliente - Usina - UF" do de-para) ou o código do cadastro (só de UMA usina)
        uid, como = self.lig.usina(str(fracttal or nome or ""), str(codigo or nome or ""))
        return (uid, como) if uid else (None, None)


def _num(v):
    if isinstance(v, bool) or v in (None, ""):
        return None
    try:
        x = float(str(v).replace(",", ".")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _int(v):
    x = _num(v)
    return int(x) if x is not None else None


def _dia_do_id(v) -> date | None:
    """20261012 -> date(2026, 10, 12)."""
    i = _int(v)
    try:
        return date(i // 10000, (i // 100) % 100, i % 100) if i else None
    except ValueError:
        return None


# ── Meta do mês (Gerencial da plataforma, publicado no banco) ───────────────────────────────────────────────────
def metas(nomes: Nomes, mes_id: int) -> tuple[dict, dict]:
    """{usina_id: produção, meta, atingimento, PR e PR previsto do mês} pelas linhas do Gerencial. Usina do cadastro
    com duas linhas no Gerencial (Santarém 1 e Santarém 2 são a "Santarém 1 e 2"): a produção e a meta somam e o
    atingimento é refeito sobre a soma (o Gerencial faz atingimento = produção ÷ meta); o PR é a média das linhas
    pesada pela meta. Uma linha só: os números dela, sem conta."""
    todas = visao._livro(LIVRO_META, ABA_META)
    do_mes = [r for r in todas if _int(r.get("mes_id")) == mes_id]
    por, sem = collections.defaultdict(list), []
    for r in do_mes:
        uid, _como = nomes.usina(r.get("usina"))
        if uid:
            por[uid].append(r)
        else:
            sem.append(str(r.get("usina") or ""))
    out = {}
    for uid, rs in por.items():
        if len(rs) == 1:
            r = rs[0]
            ating, pr, prm = _num(r.get("atingimento_pct")), _num(r.get("pr_pct")), _num(r.get("pr_meta_pct"))
        else:
            com_meta = [r for r in rs if _num(r.get("meta_kwh")) and _num(r.get("prod_kwh")) is not None]
            m = sum(_num(r["meta_kwh"]) for r in com_meta)
            ating = round(100 * sum(_num(r["prod_kwh"]) for r in com_meta) / m, 1) if m else None
            com_pr = [r for r in com_meta if _num(r.get("pr_pct")) is not None and _num(r.get("pr_meta_pct")) is not None]
            mp = sum(_num(r["meta_kwh"]) for r in com_pr)
            pr = round(sum(_num(r["pr_pct"]) * _num(r["meta_kwh"]) for r in com_pr) / mp, 1) if mp else None
            prm = round(sum(_num(r["pr_meta_pct"]) * _num(r["meta_kwh"]) for r in com_pr) / mp, 1) if mp else None
        prod = [_num(r.get("prod_kwh")) for r in rs if _num(r.get("prod_kwh")) is not None]
        meta = [_num(r.get("meta_kwh")) for r in rs if _num(r.get("meta_kwh")) is not None]
        cob = [_int(r.get("dias_cobertos_qtd")) for r in rs if _int(r.get("dias_cobertos_qtd")) is not None]
        out[uid] = {"prod_kwh": sum(prod) if prod else None, "meta_kwh": sum(meta) if meta else None,
                    "atingimento": ating, "pr": pr, "pr_meta": prm, "dias_cob": min(cob) if cob else None,
                    "dias_mes": _int(rs[0].get("dias_mes_qtd")), "full_om": any(_int(r.get("full_om")) == 1 for r in rs),
                    "linhas": [str(r.get("usina") or "") for r in rs]}
    meses = sorted({_int(r.get("mes_id")) for r in todas if _int(r.get("mes_id"))})
    return out, {"publicado": bool(todas), "linhas": len(do_mes), "ligadas": sum(len(v) for v in por.values()),
                 "sem_usina": sorted(sem), "ultimo_mes": meses[-1] if meses else None}


# ── Disponibilidade (Gerencial › Disponibilidade, o diário publicado) ───────────────────────────────────────────
def disponibilidade(nomes: Nomes, mes: str) -> tuple[dict, dict]:
    """{usina_id: disponibilidade do mês (%), horas perdidas, dias, potência}. Por usina do Gerencial, a média dos dias
    fechados (a régua de lá: 100·(1 − h/12) por dia, e 12 h × dias no mês: a média dos dias é o mês). Usina do cadastro
    com duas do Gerencial (Aparecida do Taboado 1 e 2): pesadas pela potência, como o resumo por cliente de lá. Provado
    em 12/10/2026: 129 de 130 usinas iguais à tela da plataforma (a 130ª porque a tela ao vivo revarreu depois)."""
    linhas = [r for r in visao._livro(LIVRO_DISP, ABA_DISP) if str(r.get("mes") or "") == mes]
    por_nome = {}
    for r in linhas:
        n = str(r.get("usina") or "").strip()
        d = _num(r.get("disp"))
        if not n or d is None:
            continue
        x = por_nome.setdefault(n, {"dias": [], "h": 0.0, "pot": _num(r.get("pot_kwp")),
                                    "fracttal": str(r.get("usina_fracttal") or "")})
        x["dias"].append(d)
        x["h"] += _num(r.get("h_perdidas")) or 0.0
    por, sem = collections.defaultdict(list), []
    for n, x in por_nome.items():
        uid, _como = nomes.usina(n, fracttal=x["fracttal"])
        if uid:
            por[uid].append(x)
        else:
            sem.append(n)
    out = {}
    for uid, xs in por.items():
        pesos = [(x["pot"] or 1.0) for x in xs]
        tot = sum(pesos)
        disp = sum(p * (sum(x["dias"]) / len(x["dias"])) for p, x in zip(pesos, xs)) / tot
        out[uid] = {"disp": round(disp, 2), "h_perdidas": round(sum(p * x["h"] for p, x in zip(pesos, xs)) / tot, 1),
                    "dias": max(len(x["dias"]) for x in xs), "pot_kwp": sum(x["pot"] or 0 for x in xs) or None}
    ate = max((str(r.get("dia") or "") for r in linhas), default="")
    return out, {"publicado": bool(linhas), "ate": ate, "usinas": len(por_nome), "sem_usina": sorted(sem)}


def paradas_abertas(nomes: Nomes, mes: str) -> tuple[dict, dict]:
    """{usina_id: [OS de parada AINDA aberta]} para a faixa "Parada agora" (18/10/2026; o painel próprio de um
    supervisor tinha a faixa "Usinas desligadas"). Fonte: as OS que formaram a disponibilidade do mês
    (`falhas_performance · disponibilidade_os`, a plataforma publica do Fracttal), as com `aberta`; a mesma ligação pelo
    nome da `disponibilidade` (cada nome uma vez). A mais antiga primeiro."""
    linhas = [r for r in visao._livro(LIVRO_DISP, ABA_DISP_OS) if str(r.get("mes") or "") == mes]
    abertas = [r for r in linhas if str(r.get("aberta") or "").strip().lower() in ("sim", "true", "1")]
    uid_de, out = {}, collections.defaultdict(list)
    for r in abertas:
        n, f = str(r.get("usina") or "").strip(), str(r.get("usina_fracttal") or "")
        if (n, f) not in uid_de:
            uid_de[(n, f)] = nomes.usina(n, fracttal=f)[0]
        uid = uid_de[(n, f)]
        if uid:
            ini = str(r.get("inicio") or "")
            out[uid].append({"os": str(r.get("os") or ""), "tipo": str(r.get("tipo") or "—"),
                             "escopo": str(r.get("escopo") or "—"), "codigo": str(r.get("codigo_ativo") or ""),
                             "inicio": _hora(ini), "_ini": ini})
    for lst in out.values():
        lst.sort(key=lambda o: (o["_ini"], o["os"]))
    return dict(out), {"publicado": bool(linhas), "abertas": len(abertas),
                       "sem_usina": sorted({n for (n, _f), u in uid_de.items() if not u})}


def _programacao_recente(segundas: set) -> list[dict]:
    """As linhas do `fato_programacao` das semanas pedidas (a passada e a corrente), lidas do FIM para trás, como a tela
    Técnicos por usina (`pcm.tecnicos_usina._programacao_do_fim`): a carga põe as 4 semanas do arquivo do PCM no fim
    (`programacao.mesclar_semanas`), e a aba inteira (16.540 linhas em 18/10/2026) levava 4,4 s a cada conta da Visão.
    Para depois de passar das semanas pedidas. Sem a listagem das abas, a aba inteira."""
    from ..dados import programacao as PG
    base, s = visao._base(), visao._sessao()
    try:
        r = s.get(f"{base}/api/sheets", timeout=60)
        r.raise_for_status()
        meta = next(((x.get("id"), int(x.get("row_count") or 0)) for x in r.json()
                     if x.get("workbook_key") == PG.LIVRO and x.get("sheet_name") == PG.ABA), None)
    except Exception:       # noqa: BLE001 — sem a listagem: a aba inteira, pela cópia de sempre
        meta = None
    if not meta or not meta[0]:
        return visao._livro(PG.LIVRO, PG.ABA)
    sid, n = meta
    out, viu, off = [], False, ((max(n, 1) - 1) // 1000) * 1000
    while off >= 0:
        r = s.get(f"{base}/api/sheets/{sid}/rows", params={"limit": 1000, "offset": off}, timeout=60)
        r.raise_for_status()
        rows = r.json()
        rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
        achadas = [x for x in (dict(zip(y.get("headers") or [], y.get("values") or [])) for y in rows)
                   if visao.D._id(x.get("data_id_semana")) in segundas]
        out += achadas
        if achadas:
            viu = True
        elif viu:
            break           # já passou das semanas pedidas
        off -= 1000
    return out


def manutencao_fonte(b, hoje, agora) -> tuple[dict, dict]:
    """{usina_id: o dado cru do bloco Manutenção} (18/10/2026; a conta é `nexus/campo/manutencao.py`): as tarefas das OS
    do Fracttal (`nexus_os`), os motivos do Fora da programação (decifrados aqui: a marca guarda a usina e a tarefa
    cifradas), as OS de chamado e a programação. O nível NÃO sai daqui: depende do limite de quem olha
    (`com_manutencao`, no pedido). Sem o `nexus_os` no banco, só as paradas por marca e a semana."""
    from flask import current_app
    from ..dados import fato_tarefa_os as FT
    from ..dados.calendario import data_id
    from . import manutencao as M
    cfg = current_app.config
    tarefas = visao._livro(FT.LIVRO, FT.ABA)
    q = next(iter(visao._livro(FT.LIVRO, "qualidade")), {})
    # sem os motivos, a tarefa parada por motivo conta como atrasada: a tela avisa (revisão de 18/10/2026: passava calado).
    # A leitura que falha com uma cópia boa na memória (`velha`) segue com as marcas dela, sem aviso
    marcas, erro_motivos, ilegiveis = [], "", 0
    try:
        from ..pcm import motivos
        est = motivos.ler(cfg)
        if est.get("erro") and not est.get("lido_em"):
            erro_motivos = est["erro"]
        vig = motivos.vigentes(cfg, est)
        ilegiveis = visao.D._int(vig.pop("_ilegiveis", 0)) or 0
        marcas = M.marcas_paradas(vig, lambda m: b.lig.usina(m.get("usina"), m.get("codigo"))[0])
    except Exception as e:      # noqa: BLE001 — sem os motivos, o resto do bloco vale
        erro_motivos = f"{type(e).__name__}: {str(e)[:120]}"
    chamados_os = {visao.D._id(r.get("os")) for r in visao._livro(LIVRO_CHAMADOS, ABA_CHAMADOS)} - {None}
    t = M.tarefas_por_usina(tarefas if tarefas else None, marcas, chamados_os, hoje)
    passada = hoje - timedelta(days=hoje.weekday() + 7)
    prog = _programacao_recente({data_id(passada), data_id(passada + timedelta(days=7))})
    s = M.semana_por_usina(prog, hoje, agora.strftime("%H:%M"))
    ano, sem, _ = passada.isocalendar()
    por = {uid: {**t.get(uid, {}), **s.get(uid, {})} for uid in set(t) | set(s)}
    return por, {"publicado": bool(tarefas), "gerado_em": str(q.get("gerado_em") or ""), "erro_motivos": erro_motivos,
                 "ilegiveis": ilegiveis, "semana_passada": f"{ano}-W{sem:02d}"}


FOTO_VELHA_H = 2        # o laço grava de hora em hora (do :10 ao :20): passou de 2 h, ao menos uma volta não gravou


def foto_das_os(gerado_em, agora) -> dict:
    """De quando é a foto das OS no banco (o `gerado_em` da qualidade do `nexus_os`, gravado por qualquer máquina) e se
    está velha, no relógio do pedido. A tela dizia só a hora ("às 09:10"), e a foto de ontem passava por de hoje (revisão
    de 18/10/2026). `quando`: "das 09:10" hoje, "de 17/10 às 09:10" noutro dia."""
    d = visao._dt(gerado_em)
    if not d:
        return {"quando": "", "horas": None, "velha": False}
    d, agora = d.astimezone(_BRT), agora.astimezone(_BRT)
    horas = (agora - d).total_seconds() / 3600
    quando = f"das {d:%H:%M}" if d.date() == agora.date() else f"de {d:%d/%m} às {d:%H:%M}"
    return {"quando": quando, "horas": int(horas), "velha": horas > FOTO_VELHA_H}


def limpeza() -> tuple[dict, dict]:
    """{usina_id: a última leitura de sujidade e vegetação} (18/10/2026): a conta das Rondas (`visao.sujidade_vegetacao`,
    a régua `visao.criticidade`), com o checklist do fato de ronda e as respostas das OS de ronda que o processo já tem
    (sem pedir releitura ao Fracttal: a tela Rondas é quem pede). 90 dias: a última leitura, de quando for."""
    from . import ronda_checklist
    lei = visao.rondas()
    if lei.erro:
        raise visao.SemBanco(lei.erro)
    d = lei.dados or {}
    suj = visao.sujidade_vegetacao(d.get("todas") or [], d.get("cobertura") or [], ronda_checklist.respostas(), 90,
                                   d.get("hoje") or visao._agora().date().isoformat(), d.get("validacoes") or [])
    por = {x["usina_id"]: x for x in suj.get("linhas") or [] if x.get("usina_id")}
    return por, {"com_leitura": len(por)}


# ── O Ranking das equipes (18/10/2026): a régua do ranking por região do App, por usina, nos dois períodos ──────────
def ranking_fonte(b, hoje) -> tuple[dict, dict]:
    """{usina_id: {"atual", "anterior"}} com as notas do App (as tarefas fechadas e as rondas) e a ronda de cada usina
    mobilizada (`ranking_equipes.agregar`). O agrupamento por equipe sai no pedido, porque os filtros são de quem olha.
    As duas leituras já estão na cópia do ciclo quando a Visão é feita (medido no banco real em 18/10/2026: as rondas em
    0,03 s e o fato de fechamento em 0,00 s depois da conta da Visão, que lê os dois para a Central)."""
    from . import ranking_equipes
    fech = visao._fato("fechamento", b)
    per = ranking_equipes.periodos(hoje)
    desde = {uid: str(u.get("data_mobilizacao") or "")[:10] for uid, u in b.mobilizadas.items()}
    return (ranking_equipes.agregar(fech["linhas"], visao._rondas_ligadas(b), b.mobilizadas, hoje, desde),
            {"de": fech["de"], "aviso": fech["aviso"],
             **{p: (ini.isoformat(), fim.isoformat()) for p, (ini, fim) in per.items()}})


# ── Ativos falhando (Engenharia › Confiabilidade) ───────────────────────────────────────────────────────────────
def _engenharia() -> dict:
    """Os dados da Confiabilidade, com a cópia dela (as OS de falha do Fracttal lidas em segundo plano)."""
    from ..torres import engenharia
    return engenharia._dados()


def ativos() -> tuple[dict, dict]:
    """{usina_id: quantos ativos em crítico, atenção e monitorar, e os piores}: os sinais da Confiabilidade, sem régua
    nova (o nível é o de lá). Ativo sem usina no cadastro fica fora (não há de quem ele seja)."""
    from ..engenharia import os_falhas
    g = _engenharia()
    d = g.get("dados") or {}
    por = collections.defaultdict(lambda: {"critico": 0, "atencao": 0, "monitorar": 0, "lista": []})
    for s in d.get("sinais") or []:
        uid = s.get("usina_id")
        if not uid or s.get("nivel") not in ("critico", "atencao", "monitorar"):
            continue
        x = por[uid]
        x[s["nivel"]] += 1
        x["lista"].append({"nome": s.get("nome") or s.get("cod") or "", "cod": s.get("cod") or "", "fam": s.get("fam") or "",
                           "nivel": s["nivel"], "porque": "; ".join(s.get("porQue") or []), "falhas": s.get("nFalha") or 0})
    est = os_falhas.estado()
    return dict(por), {"completa": est.get("completa", False), "lendo": est.get("lendo", False),
                       "sem_cadastro": g.get("sem_cadastro", False), "sinais": len(d.get("sinais") or [])}


NIVEL_ATIVO = {"critico": "Crítico", "atencao": "Atenção", "monitorar": "Monitorar"}


def _dia_da_os(d: str, hoje: date) -> date | None:
    """O dia de uma OS da Confiabilidade ("13/10 09:30", sem o ano): o ano de hoje, ou o anterior se cair no futuro (a
    janela é de 30 dias: a OS de 28/12 vista em 05/01 é do ano passado)."""
    try:
        dia, mes = (int(x) for x in str(d or "").split()[0].split("/")[:2])
        x = date(hoje.year, mes, dia)
    except (ValueError, IndexError):
        return None
    return x if x <= hoje else date(hoje.year - 1, mes, dia)


def ativos_da_usina(uid: int, hoje: date) -> dict:
    """A janela dos ativos falhando da usina (Levi, 13/10/2026: "Para esses ativos falhando da engenharia, conseguimos
    criar uma visão?"): os sinais da Engenharia › Confiabilidade da usina em crítico e atenção (os mesmos do detalhe da
    linha, na régua de lá, sem régua nova), cada um com o porquê, os números da gaveta de lá (falhas em 30 e em 7 dias,
    o P90 da família, MTBF, MTTR e a disponibilidade do ativo) e as últimas OS; e a linha do tempo dos 30 dias (ativo ×
    dia, a OS de falha e a de serviço). Os em monitorar só contados. Lê o que a Confiabilidade já leu (não refaz conta
    nem lê o Fracttal de novo); não mexe nos dicionários dela (são o cache da tela de lá)."""
    from ..engenharia import confiabilidade as C, os_falhas
    from ..torres import engenharia as E
    g = _engenharia()
    sinais = [s for s in ((g.get("dados") or {}).get("sinais") or []) if s.get("usina_id") == uid]
    dias = [hoje - timedelta(days=i) for i in range(C.JANELA_DIAS - 1, -1, -1)]
    ordem = {"critico": 0, "atencao": 1}
    ativos = []
    for s in sorted((s for s in sinais if s.get("nivel") in ordem), key=lambda s: (ordem[s["nivel"]], -(s.get("nFalha") or 0))):
        por_dia = collections.defaultdict(list)
        for o in s.get("os") or []:
            d = _dia_da_os(o.get("d"), hoje)
            if d:
                por_dia[d].append(o)
        disp = s.get("disp")
        ativos.append({
            "nome": s.get("nome") or s.get("cod") or "", "cod": s.get("cod") or "", "fam": s.get("fam") or "",
            "crit": s.get("crit") or "", "nivel": s["nivel"], "nivel_txt": NIVEL_ATIVO[s["nivel"]],
            "cls": "critico" if s["nivel"] == "critico" else "alerta", "porque": list(s.get("porQue") or []),
            "falhas": s.get("nFalha") or 0, "n7": s.get("n7") or 0, "n30": s.get("n30") or 0, "p90": s.get("p90"),
            "servicos": s.get("nServico") or 0, "circuito": s.get("circuito") or "",
            "mtbf": E._h(s.get("mtbf")), "mttr": E._h(s.get("mttr")), "disp": E._pct(disp),
            "disp_cls": "neutro" if disp is None else ("ok" if disp >= C.META_DISP else "critico"),
            "os": list(s.get("os") or []),
            "linha": [{"dia": d, "oss": por_dia.get(d, []), "falhas": sum(1 for o in por_dia.get(d, []) if not o.get("servico")),
                       "servicos": sum(1 for o in por_dia.get(d, []) if o.get("servico"))} for d in dias]})
    est = os_falhas.estado()
    return {"ativos": ativos, "dias": dias, "janela": C.JANELA_DIAS, "max_os": C.MAX_OS, "meta_disp": C.META_DISP,
            "monitorar": sum(1 for s in sinais if s.get("nivel") == "monitorar"),
            "criticos": sum(1 for a in ativos if a["nivel"] == "critico"),
            "atencao": sum(1 for a in ativos if a["nivel"] == "atencao"),
            "completa": est.get("completa", False), "sem_cadastro": g.get("sem_cadastro", False)}


# ── Chamados (as OS de acompanhamento de chamado, no banco) ─────────────────────────────────────────────────────
def chamados(hoje: date) -> tuple[dict, dict]:
    """{usina_id: abertos, em verificação e a lista}: o fato `nexus_chamados · fato_chamado` (o mesmo dado do quadro
    Acompanhamento de chamados). O nome do equipamento sai da dimensão de equipamento pelo `equipamento_id` (sem ele, o
    código do ativo). Concluído não conta: é o Finalizados do quadro."""
    linhas = visao._livro(LIVRO_CHAMADOS, ABA_CHAMADOS)
    nome_equip = {}
    if linhas:
        nome_equip = {visao.D._id(r.get("equipamento_id")): str(r.get("descricao") or "").strip()
                      for r in visao._livro(LIVRO_EQUIP, ABA_EQUIP) if visao.D._id(r.get("equipamento_id"))}
    por = collections.defaultdict(lambda: {"abertos": 0, "verificacao": 0, "lista": []})
    sem = 0
    for r in linhas:
        sit = str(r.get("situacao") or "")
        if sit not in ("aberto", "verificacao"):
            continue
        uid = visao.D._id(r.get("usina_id"))
        if not uid:
            sem += sit == "aberto"
            continue
        x = por[uid]
        x["abertos" if sit == "aberto" else "verificacao"] += 1
        ini = _dia_do_id(r.get("data_id_abertura"))
        eid = visao.D._id(r.get("equipamento_id"))
        x["lista"].append({"os": _int(r.get("os")), "situacao": sit, "dias": (hoje - ini).days if ini else None,
                           "equip": (nome_equip.get(eid) or str(r.get("codigo_ativo") or "") or "equipamento")[:48],
                           "fabricante": str(r.get("fabricante") or ""), "componente": str(r.get("componente") or "")})
    for x in por.values():
        x["lista"].sort(key=lambda c: (c["situacao"] != "aberto", -(c["dias"] or 0)))
        x["mais_antigo"] = max((c["dias"] for c in x["lista"] if c["situacao"] == "aberto" and c["dias"] is not None),
                               default=None)
    return dict(por), {"publicado": bool(linhas), "abertos": sum(x["abertos"] for x in por.values()) + sem,
                       "sem_usina": sem}


# ── Extintores (Segurança · HSEQ) ───────────────────────────────────────────────────────────────────────────────
def extintores() -> tuple[dict, dict]:
    """{usina_id: total, vencidos, a vencer, sem conferência e os piores}: a conta do HSEQ (`hseq/extintores.py`, as
    situações exclusivas e a "sem atualização" à parte), sem régua nova."""
    from ..hseq import extintores as E
    lei = E.extintores()
    if lei.erro:
        raise visao.SemBanco(lei.erro)
    d = lei.dados or {}
    por = collections.defaultdict(lambda: {"total": 0, "vencidos": 0, "a_vencer": 0, "sem_conferir": 0,
                                           "sem_validade": 0, "lista": []})
    for x in d.get("extintores") or []:
        uid = x.get("usina_id")
        if not uid:
            continue
        e = por[uid]
        e["total"] += 1
        e["vencidos"] += x["situacao"] == "atrasado"
        e["a_vencer"] += x["situacao"] == "perto"
        e["sem_validade"] += x["situacao"] == "sem_validade"
        e["sem_conferir"] += bool(x.get("sem_atualizacao"))
        if x["situacao"] in ("atrasado", "perto") or x.get("sem_atualizacao"):
            onde = " · ".join(v for v in (x.get("local") or "", x.get("posicao") or "") if v)
            if x["situacao"] == "atrasado":
                txt = f"{x.get('vence_qual') or 'validade'} venceu em {_dm(x.get('vence'))}"
            elif x["situacao"] == "perto":
                txt = f"{x.get('vence_qual') or 'validade'} vence em {x.get('dias_vence')} dias"
            else:
                txt = (f"sem conferência há {x.get('dias_conferencia')} dias" if x.get("dias_conferencia") is not None
                       else "nunca conferido")
            e["lista"].append({"ext": x.get("ext") or x.get("codigo") or "", "onde": onde[:40], "txt": txt,
                               "ordem": {"atrasado": 0, "perto": 1}.get(x["situacao"], 2)})
    for e in por.values():
        e["lista"].sort(key=lambda i: (i["ordem"], i["ext"]))
    return dict(por), {"publicado": bool(d.get("livro_existe")), "extintores": sum(e["total"] for e in por.values())}


# ── Os alertas de cada bloco ────────────────────────────────────────────────────────────────────────────────────
def _pct(x, casas=0) -> str:
    if x is None:
        return "—"
    return (f"{x:.{casas}f}".replace(".", ",")) + "%"


def _virgula(x, casas=1) -> str:
    return "—" if x is None else f"{x:.{casas}f}".replace(".", ",")


def _mwh(kwh) -> str:
    return "—" if kwh is None else f"{kwh / 1000:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _duracao(m) -> str:
    m = int(round(m or 0))
    if m >= 1440:
        return f"{m // 1440} d {(m % 1440) // 60} h"
    return f"{m // 60} h {m % 60:02d} min" if m >= 60 else f"{m} min"


def _dm(d) -> str:
    s = d.isoformat() if hasattr(d, "isoformat") else str(d or "")
    return f"{s[8:10]}/{s[5:7]}" if len(s) >= 10 else "—"


def cls_meta(a) -> str:
    return "neutro" if a is None else ("ok" if a >= META_NA_META else ("alerta" if a >= META_ATENCAO else "critico"))


def cls_disp(x) -> str:
    return "neutro" if x is None else ("ok" if x >= DISP_OK else ("alerta" if x >= DISP_CRITICO else "critico"))


def alertas_performance(u: dict) -> tuple[list[dict], list[str]]:
    """Os alertas de Performance (meta, PR, disponibilidade, ativos) e o que está bem. Fonte sem dado da usina não
    alerta nem elogia: fica "—"."""
    al, bem = [], []
    m = u.get("meta") or {}
    a = m.get("atingimento")
    if a is not None:
        if a < META_ATENCAO:
            al.append({"area": "meta", "nivel": "critico", "titulo": f"Meta do mês em {_pct(a)}",
                       "detalhe": "abaixo de 90% (a Visão gerencial chama de Abaixo)"})
        elif a < META_NA_META:
            al.append({"area": "meta", "nivel": "atencao", "titulo": f"Meta do mês em {_pct(a)}", "detalhe": "entre 90% e 97%"})
        else:
            bem.append(f"na meta ({_pct(a)})")
    if m.get("pr") is not None and m.get("pr_meta") is not None and m["pr"] < m["pr_meta"]:
        al.append({"area": "meta", "nivel": "atencao", "titulo": f"PR {_pct(m['pr'], 1)} abaixo do previsto",
                   "detalhe": f"previsto {_pct(m['pr_meta'], 1)}"})
    d = u.get("disp") or {}
    if d.get("disp") is not None:
        x = d["disp"]
        h = f"{_virgula(d.get('h_perdidas'))} h paradas no mês"
        if x < DISP_CRITICO:
            al.append({"area": "disp", "nivel": "critico", "titulo": f"Disponibilidade {_pct(x, 1)}", "detalhe": h})
        elif x < DISP_OK:
            al.append({"area": "disp", "nivel": "atencao", "titulo": f"Disponibilidade {_pct(x, 1)}", "detalhe": h})
        else:
            bem.append(f"disponibilidade {_pct(x, 1)}")
    at = u.get("ativos") or {}
    for nivel in ("critico", "atencao"):
        lista = [x for x in at.get("lista") or [] if x["nivel"] == nivel]
        if lista:
            al.append({"area": "ativos", "nivel": nivel,
                       "titulo": f"{len(lista)} ativo{'s' if len(lista) != 1 else ''} "
                                 f"{'em crítico' if nivel == 'critico' else 'pedindo atenção'}"})
    if at and not at.get("critico") and not at.get("atencao"):
        bem.append("nenhum ativo em crítico ou atenção")
    return al, bem


def alertas_acompanhamento(u: dict) -> tuple[list[dict], list[str]]:
    """Os alertas de Acompanhamento (ronda, PT, chamados, extintores) e o que está bem."""
    al, bem = [], []
    r = u.get("ronda") or {}
    if r.get("tipo") in ("nunca", "sem_ronda"):
        al.append({"area": "ronda", "nivel": "critico",
                   "titulo": "Nunca teve ronda" if r["tipo"] == "nunca" else f"Sem ronda há {r['dias']} dias"})
    elif r.get("tipo") == "longa_pendente":
        al.append({"area": "ronda", "nivel": "atencao", "titulo": "Ronda longa pendente"})
    elif r.get("dias") is not None and r["dias"] < 999:
        bem.append("ronda " + ("hoje" if r["dias"] == 0 else ("ontem" if r["dias"] == 1 else f"há {r['dias']} dias")))
    # a limpeza da última ronda, na régua das Rondas (`visao.criticidade`: o "status" dela, o mais grave primeiro)
    for texto, cor in (u.get("limpeza") or {}).get("status") or ():
        if cor in ("critico", "alerta"):
            al.append({"area": "limpeza", "nivel": "critico" if cor == "critico" else "atencao", "titulo": texto})
    p = u.get("pt") or {}
    grupos_pt = (("agora", lambda x: x["hoje"] and x["parada"]), ("critico", lambda x: not x["hoje"] and x["parada"]),
                 ("atencao", lambda x: not x["parada"]))
    for nivel, de_quem in grupos_pt:
        n = sum(1 for x in p.get("lista", []) if de_quem(x))
        if n:
            al.append({"area": "pt", "nivel": nivel,
                       "titulo": {"agora": f"{n} PT parada{'s' if n != 1 else ''} há mais de 2 h",
                                  "critico": f"{n} PT sem decisão desde {_dm(p.get('desde'))}",
                                  "atencao": f"{n} PT esperando o De acordo"}[nivel]})
    c = u.get("chamados") or {}
    if c.get("abertos"):
        al.append({"area": "chamados", "nivel": "atencao",
                   "titulo": f"{c['abertos']} chamado{'s' if c['abertos'] != 1 else ''} em aberto"})
    else:
        bem.append("sem chamado aberto")
    e = u.get("extintores") or {}
    if e.get("vencidos"):
        al.append({"area": "extintores", "nivel": "critico",
                   "titulo": f"{e['vencidos']} extintor{'es' if e['vencidos'] != 1 else ''} vencido{'s' if e['vencidos'] != 1 else ''}"})
    if e.get("a_vencer"):
        al.append({"area": "extintores", "nivel": "atencao",
                   "titulo": f"{e['a_vencer']} extintor{'es' if e['a_vencer'] != 1 else ''} vence{'m' if e['a_vencer'] != 1 else ''} em até 30 dias"})
    if e.get("sem_conferir") and not e.get("vencidos") and not e.get("a_vencer"):
        al.append({"area": "extintores", "nivel": "atencao",
                   "titulo": f"{e['sem_conferir']} extintor{'es' if e['sem_conferir'] != 1 else ''} sem conferência há mais de 30 dias"})
    if e.get("total") and not e.get("vencidos") and not e.get("a_vencer") and not e.get("sem_conferir"):
        bem.append(f"{e['total']} extintor{'es' if e['total'] != 1 else ''} em dia")
    return al, bem


def _nivel(al) -> str:
    if any(a["nivel"] in ("agora", "critico") for a in al):
        return "critico"
    return "atencao" if al else "ok"


# ── O que a linha compacta mostra e o detalhe que ela abre ──────────────────────────────────────────────────────
def _v(txt, cls, sub="") -> dict:
    return {"txt": txt, "cls": cls, "sub": sub}


def linha_performance(u: dict) -> dict:
    """Os valores da linha (meta, PR × previsto, disponibilidade; a etiqueta do ativo) e o detalhe (cada item:
    rótulo, o principal em destaque, o resto e os itens)."""
    m, d, at = u.get("meta") or {}, u.get("disp") or {}, u.get("ativos") or {}
    pr, prm = m.get("pr"), m.get("pr_meta")
    valores = {"meta": _v(_pct(m.get("atingimento")), cls_meta(m.get("atingimento"))),
               "pr": (_v(_virgula(pr), "alerta" if pr < prm else "ok", f"/ {_virgula(prm)}") if pr is not None and prm is not None
                      else _v(_virgula(pr), "neutro") if pr is not None else _v("—", "neutro")),
               "disp": _v(_pct(d.get("disp"), 1), cls_disp(d.get("disp")))}
    tag = None
    if at.get("critico"):
        tag = ("critico", f"{at['critico']} ativo{'s' if at['critico'] != 1 else ''} crítico{'s' if at['critico'] != 1 else ''}")
    elif at.get("atencao"):
        tag = ("alerta", f"{at['atencao']} ativo{'s' if at['atencao'] != 1 else ''} em atenção")
    det = []
    if m.get("meta_kwh"):
        det.append({"rot": "Meta do mês", "forte": f"{_mwh(m.get('prod_kwh'))} de {_mwh(m['meta_kwh'])} MWh",
                    "resto": f"{_pct(m.get('atingimento'))} · meta até {m.get('dias_cob') or '—'} dias cobertos", "itens": []})
    else:
        det.append({"rot": "Meta do mês", "forte": "", "resto": "sem meta publicada para esta usina", "itens": []})
    if pr is not None:
        det.append({"rot": "PR", "forte": _pct(pr, 1), "resto": f"previsto {_pct(prm, 1)}" if prm is not None else "",
                    "alerta": "abaixo do previsto" if prm is not None and pr < prm else "", "itens": []})
    if d.get("disp") is not None:
        det.append({"rot": "Disponibilidade", "forte": _pct(d["disp"], 1),
                    "resto": f"{_virgula(d.get('h_perdidas'))} h paradas no mês", "itens": []})
    falhando = [x for x in at.get("lista") or [] if x["nivel"] in ("critico", "atencao")]
    if falhando:
        det.append({"rot": "Ativos falhando", "forte": "",
                    "resto": f"{len(falhando)} com sinal na Confiabilidade",
                    "itens": [{"forte": x["nome"], "txt": x["porque"]} for x in falhando[:3]],
                    "mais": max(0, len(falhando) - 3)})
    return {"valores": valores, "tag": tag, "det": det}


def _limpeza(x) -> tuple[dict, str]:
    """A coluna Limpeza ("S2 V5", na cor do achado mais grave da régua das Rondas) e o texto do detalhe."""
    if not x:
        return _v("—", "neutro"), ""
    s, v = x.get("sujidade"), x.get("vegetacao")
    cores = {c for _t, c in x.get("status") or ()}
    cls = "critico" if "critico" in cores else ("alerta" if "alerta" in cores else "ok")
    partes = [f"Sujidade {s}" if s else "", f"Vegetação {v}" if v else ""]
    vala = str(x.get("vala") or "").strip()
    if vala and vala.lower() != "limpa":
        partes.append(f"vala {vala.lower()}")
    if x.get("sensores_sujos"):
        partes.append("sensor sujo (" + ", ".join(x["sensores_sujos"]) + ")")
    partes.append(f"ronda de {_dm(x.get('data'))}")
    txt = " ".join(p for p in (f"S{s}" if s else "", f"V{v}" if v else "") if p) or "—"
    return _v(txt, cls), " · ".join(p for p in partes if p)


def linha_acompanhamento(u: dict) -> dict:
    """Os valores da linha (ronda, limpeza, PT, chamados, extintores) e o detalhe."""
    r, p, c, e = u.get("ronda") or {}, u.get("pt") or {}, u.get("chamados") or {}, u.get("extintores") or {}
    lim, lim_txt = _limpeza(u.get("limpeza"))
    if r.get("tipo") == "nunca":
        ronda, ronda_txt = _v("nunca", "critico"), "Nunca teve ronda pelo App desde a mobilização"
    elif r.get("tipo") == "sem_ronda":
        ronda, ronda_txt = _v(f"há {r['dias']} d", "critico"), f"Sem ronda há {r['dias']} dias (última em {_dm(r.get('ultima'))})"
    elif r.get("tipo") == "longa_pendente":
        ronda, ronda_txt = _v("longa pend.", "alerta"), f"Ronda longa pendente · última ronda em {_dm(r.get('ultima'))}"
    elif r.get("dias") is not None and r["dias"] < 999:
        ronda = _v("hoje" if r["dias"] == 0 else f"há {r['dias']} d", "ok")
        ronda_txt = f"Em dia · última ronda em {_dm(r.get('ultima'))}"
    else:
        ronda, ronda_txt = _v("—", "neutro"), ""
    if p.get("paradas_hoje"):
        pt = _v(f"{p['paradas_hoje']} agora", "critico")
    elif p.get("paradas_antigas"):
        pt = _v(f"{p['paradas_antigas']} s/ decisão", "critico")
    elif p.get("aguardando"):
        pt = _v(f"{p['aguardando']} esperando", "alerta")
    else:
        pt = _v("—", "neutro")
    if c.get("abertos"):
        ch = _v(f"{c['abertos']} aberto{'s' if c['abertos'] != 1 else ''}", "alerta")
    elif c.get("verificacao"):
        ch = _v("em verificação", "neutro")
    else:
        ch = _v("—", "neutro")
    if e.get("vencidos"):
        ext = _v(f"{e['vencidos']} vencido{'s' if e['vencidos'] != 1 else ''}", "critico")
    elif e.get("a_vencer"):
        ext = _v(f"{e['a_vencer']} a vencer", "alerta")
    elif e.get("sem_conferir"):
        ext = _v(f"{e['sem_conferir']} s/ conf.", "alerta")
    elif e.get("total"):
        ext = _v(f"{e['total']} ok", "ok")
    else:
        ext = _v("—", "neutro")
    det = []
    if ronda_txt:
        det.append({"rot": "Ronda", "forte": "", "resto": ronda_txt, "itens": []})
    if lim_txt:
        det.append({"rot": "Limpeza", "forte": "", "resto": lim_txt, "itens": []})
    if p.get("aguardando"):
        det.append({"rot": "PT", "forte": "", "resto": f"{p['aguardando']} esperando o De acordo",
                    "itens": [{"forte": f"OS {x['os'] or x['numero']}", "txt": f"há {_duracao(x['idade_min'])}",
                               "agora": x["hoje"] and x["parada"],
                               "sem_decisao": f"sem decisão desde {_dm(x['dia'])}" if x["parada"] and not x["hoje"] else "",
                               "numero": x["numero"], "codigo": x["codigo"], "titulo": x["tarefa"]} for x in p["lista"][:3]],
                    "mais": max(0, len(p["lista"]) - 3)})
    if c.get("abertos") or c.get("verificacao"):
        det.append({"rot": "Chamados", "forte": "", "resto": f"{c.get('abertos', 0)} em aberto no Acompanhamento de chamados"
                    + (f" · {c['verificacao']} em verificação" if c.get("verificacao") else ""),
                    "itens": [{"forte": x["equip"], "txt": " · ".join(v for v in (
                        x["fabricante"], f"aberto há {x['dias']} d" if x["situacao"] == "aberto" and x["dias"] is not None
                        else ("em verificação" if x["situacao"] == "verificacao" else ""), f"OS {x['os']}") if v)}
                              for x in c["lista"][:3]],
                    "mais": max(0, len(c["lista"]) - 3)})
    if e.get("total"):
        det.append({"rot": "Extintores", "forte": "",
                    "resto": f"{e['total']} cadastrados · {e['vencidos']} vencido{'s' if e['vencidos'] != 1 else ''} · "
                             f"{e['a_vencer']} a vencer · {e['sem_conferir']} sem conferência há mais de 30 dias",
                    "itens": [{"forte": f"Extintor {x['ext']}", "txt": (f"({x['onde']}) " if x["onde"] else "") + x["txt"]}
                              for x in e["lista"][:3]],
                    "mais": max(0, len(e["lista"]) - 3)})
    return {"valores": {"ronda": ronda, "limpeza": lim, "pt": pt, "chamados": ch, "extintores": ext}, "tag": None,
            "det": det}


def _pt_vazia() -> dict:
    return {"aguardando": 0, "paradas": 0, "paradas_hoje": 0, "paradas_antigas": 0, "desde": "", "lista": []}


def montar(b, usinas_ronda, pendentes, pts, fontes, hoje) -> list[dict]:
    """Uma linha por usina MOBILIZADA, com o que cada fonte diz dela e os dois blocos (alertas, o que está bem, o nível
    e o peso de cada um; os valores da linha compacta e o detalhe). `hoje` = o dia de Brasília (a PT parada de hoje é a
    do técnico parado agora)."""
    ronda = {u.get("usina_id"): u for u in usinas_ronda}
    pend = {x.get("usina_id"): x for x in pendentes}
    pt = collections.defaultdict(_pt_vazia)
    for x in pts:
        if x.get("usina_id"):
            p = pt[x["usina_id"]]
            criada = x.get("criada")
            dia = criada.astimezone(_BRT).date().isoformat() if hasattr(criada, "astimezone") else ""
            de_hoje = dia == hoje.isoformat()
            p["aguardando"] += 1
            if x.get("parada"):
                p["paradas"] += 1
                p["paradas_hoje" if de_hoje else "paradas_antigas"] += 1
                if not de_hoje and dia and (not p["desde"] or dia < p["desde"]):
                    p["desde"] = dia
            p["lista"].append({"numero": x.get("numero"), "codigo": x.get("codigo"), "os": x.get("os"),
                               "tarefa": str(x.get("tarefa") or "")[:70], "idade_min": x.get("idade_min"),
                               "parada": bool(x.get("parada")), "hoje": de_hoje, "dia": dia})
    out = []
    for uid in b.mobilizadas:
        o = b.onde(uid)
        r = dict(ronda.get(uid) or {})
        if uid in pend:
            r.update(tipo=pend[uid].get("tipo"), obs=pend[uid].get("obs"))
        u = {"usina_id": uid, **{k: o[k] for k in ("usina", "uf", "cidade", "equipe", "cliente", "regiao_campo",
                                                  "gestor", "responsavel", "cluster")},
             "meta": fontes["metas"].get(uid), "disp": fontes["disp"].get(uid), "ativos": fontes["ativos"].get(uid),
             "chamados": fontes["chamados"].get(uid), "extintores": fontes["extintores"].get(uid), "ronda": r,
             "pt": pt.get(uid) or _pt_vazia(),
             # 18/10/2026: a limpeza da última ronda e as paradas abertas (fontes novas: por `.get`, a fonte que não
             # veio não quebra a conta)
             "limpeza": (fontes.get("limpeza") or {}).get(uid),
             "paradas_abertas": (fontes.get("paradas") or {}).get(uid) or [],
             "manutencao": (fontes.get("manut") or {}).get(uid) or {}}
        for bloco, alertas, linha in (("perf", alertas_performance, linha_performance),
                                      ("acomp", alertas_acompanhamento, linha_acompanhamento)):
            al, bem = alertas(u)
            al.sort(key=lambda a: -PESO[a["nivel"]])
            u[bloco] = {"alertas": al, "bem": bem, "nivel": _nivel(al), "peso": sum(PESO[a["nivel"]] for a in al),
                        **linha(u)}
        u["nivel"] = min((u["perf"]["nivel"], u["acomp"]["nivel"]), key=NIVEIS.index)
        u["foco"] = u["perf"]["peso"] + u["acomp"]["peso"]
        out.append(u)
    out.sort(key=ordem_do_foco)
    return out


# ── O bloco Manutenção (18/10/2026): o nível depende do limite de quem olha, então sai no pedido ──────────────────
def limite_do_pedido(valor) -> int:
    """O limite das atrasadas (Levi, 18/10/2026: "o supervisor decide, começa com 30 dias mas pode alterar"): número
    fora de 10 a 365 vai ao mais perto (atrasada já é mais de 10 dias); texto ou vazio vale 30. Nunca um erro."""
    from .manutencao import LIMITE_MAX, LIMITE_MIN, LIMITE_PADRAO
    try:
        n = int(str(valor).strip())
    except (TypeError, ValueError):
        return LIMITE_PADRAO
    return max(LIMITE_MIN, min(LIMITE_MAX, n))


def _plural(n, um, varios) -> str:
    return f"{n} {um if n == 1 else varios}"


def alertas_manutencao(u: dict, limite: int) -> tuple[list[dict], list[str]]:
    """Os alertas do bloco Manutenção e o que está bem, na régua das telas donas (ver `REGUAS`, bloco manut) e com o
    limite das atrasadas de quem olha."""
    from .manutencao import META_SEMANA
    m, al, bem = u.get("manutencao") or {}, [], []
    pa = u.get("paradas_abertas") or []
    if pa:
        al.append({"area": "parada", "nivel": "critico", "titulo": _plural(len(pa), "OS de parada aberta",
                                                                           "OS de parada abertas")})
    if m.get("atrasadas"):
        maior = m.get("maior_atraso") or 0
        al.append({"area": "atrasadas", "nivel": "critico" if maior > limite else "atencao",
                   "titulo": f"{_plural(m['atrasadas'], 'tarefa atrasada', 'tarefas atrasadas')}, a mais antiga há "
                             f"{maior} dias"})
    elif m.get("os_abertas"):
        bem.append("nenhuma tarefa atrasada")
    if m.get("paradas"):
        al.append({"area": "paradas", "nivel": "atencao",
                   "titulo": _plural(m["paradas"], "tarefa fora da programação", "tarefas fora da programação")})
    pct = m.get("passada_pct")
    if pct is not None and pct < META_SEMANA:
        al.append({"area": "semana", "nivel": "atencao", "titulo": f"semana passada com {_virgula(pct)}% do plano feito"})
    elif pct is not None:
        bem.append(f"semana passada com {_virgula(pct)}% do plano feito")
    if m.get("zeladoria_vencida"):
        al.append({"area": "zeladoria", "nivel": "atencao", "titulo": f"zeladoria vencida desde {_dm(m['zeladoria_vencida'])}"})
    return al, bem


def _curto(txt, n=16) -> str:
    t = str(txt or "")
    t = t[len("Aguardando "):] if t.startswith("Aguardando ") else t
    return t if len(t) <= n else t[:n - 1] + "…"


def linha_manutencao(u: dict, limite: int) -> dict:
    """Os valores da linha (OS abertas, atrasadas, vencem, paradas, semana, zeladoria) e o detalhe. O item de OS do
    detalhe leva `os_card` (o card da OS do Nexus), nunca `numero`: no template, `numero` vira o botão da PT."""
    m, pa = u.get("manutencao") or {}, u.get("paradas_abertas") or []
    abertas, atr, maior = m.get("os_abertas") or 0, m.get("atrasadas") or 0, m.get("maior_atraso") or 0
    v_os = _v(str(abertas), "neutro") if abertas else _v("—", "neutro")
    if atr:
        v_atr = _v(str(atr), "critico" if maior > limite else "alerta", f"{maior} d")
    else:
        v_atr = _v("0", "ok") if abertas else _v("—", "neutro")
    v_ven = _v(str(m["vencem"]), "neutro") if m.get("vencem") else _v("—", "neutro")
    v_par = _v(str(m["paradas"]), "alerta", _curto(m.get("motivo_comum"))) if m.get("paradas") else _v("—", "neutro")
    pct = m.get("passada_pct")
    from .manutencao import META_SEMANA
    v_sem = _v("—", "neutro") if pct is None else _v(f"{_virgula(pct, 0)}%", "ok" if pct >= META_SEMANA else "alerta")
    if m.get("zeladoria_vencida"):
        v_zel = _v(f"venc. {_dm(m['zeladoria_vencida'])}", "alerta")
    elif m.get("zeladoria_proxima"):
        v_zel = _v(f"próx. {_dm(m['zeladoria_proxima'])}", "neutro")
    else:
        v_zel = _v("—", "neutro")
    det = []
    if pa:
        det.append({"rot": "Parada agora", "forte": "", "resto": _plural(len(pa), "OS de parada aberta",
                                                                          "OS de parada abertas"),
                    "itens": [{"forte": f"OS {p['os']}", "txt": f"{p['escopo']} · {p['tipo']} · desde {p['inicio']}",
                               "os_card": {"wid": None, "folio": p["os"]}} for p in pa[:3]],
                    "mais": max(0, len(pa) - 3)})
    if abertas:
        det.append({"rot": "OS abertas", "forte": "", "resto": _plural(abertas, "OS aberta", "OS abertas")
                    + (f" · {m['em_verificacao']} esperando a aprovação" if m.get("em_verificacao") else ""),
                    "itens": []})
    if atr:
        det.append({"rot": "Atrasadas", "forte": "",
                    "resto": f"{_plural(atr, 'tarefa', 'tarefas')} em {_plural(m.get('atrasadas_os') or 0, 'OS', 'OS')}, "
                             f"a mais antiga há {maior} dias (programada há mais de 10 dias)",
                    "itens": [{"forte": f"OS {x['os']}", "txt": " · ".join(t for t in (
                        f"há {x['dias']} d", (x.get("tipo") or "").replace("_", " ")) if t),
                               "os_card": {"wid": x.get("wid"), "folio": x["os"]}}
                              for x in m.get("lista_atrasadas") or []],
                    "mais": max(0, (m.get("atrasadas_os") or 0) - len(m.get("lista_atrasadas") or []))})
    if m.get("vencem"):
        det.append({"rot": "Vencem até amanhã", "forte": "", "itens": [],
                    "resto": _plural(m["vencem"], "tarefa programada para hoje ou amanhã",
                                     "tarefas programadas para hoje ou amanhã")})
    if m.get("paradas"):
        det.append({"rot": "Pausadas", "forte": "",
                    "resto": _plural(m["paradas"], "tarefa fora da programação", "tarefas fora da programação"),
                    "itens": [{"forte": f"OS {x['os']}", "txt": " · ".join(t for t in (
                        x.get("motivo"), f"desde {_dm(x['desde'])}" if x.get("desde") else "", x.get("quem")) if t),
                               "os_card": {"wid": x.get("wid"), "folio": x["os"]}}
                              for x in m.get("lista_paradas") or []],
                    "mais": 0})
    if pct is not None or m.get("hoje_devidas"):
        partes = []
        if pct is not None:
            partes.append(f"semana passada ({m.get('passada')}): {m['passada_feitas']} de {m['passada_prog']} linhas do "
                          f"plano feitas ({_virgula(pct)}%)")
        if m.get("hoje_devidas"):
            partes.append(f"hoje até agora: {m['hoje_feitas']} de {m['hoje_devidas']}")
        det.append({"rot": "Semana", "forte": "", "resto": " · ".join(partes), "itens": []})
    if m.get("zeladoria_proxima") or m.get("zeladoria_vencida") or m.get("zeladoria_ultima"):
        det.append({"rot": "Zeladoria", "forte": "", "itens": [], "resto": " · ".join(t for t in (
            f"vencida desde {_dm(m['zeladoria_vencida'])}" if m.get("zeladoria_vencida") else "",
            f"próxima {_dm(m['zeladoria_proxima'])}" if m.get("zeladoria_proxima") else "",
            f"última feita {_dm(m['zeladoria_ultima'])}" if m.get("zeladoria_ultima") else "") if t)})
    return {"valores": {"os": v_os, "atrasadas": v_atr, "vencem": v_ven, "paradas": v_par, "semana": v_sem,
                        "zeladoria": v_zel},
            "tag": ("critico", "parada") if pa else None, "det": det}


def ordem_da_manutencao(u: dict):
    """A Manutenção pelo nível; dentro dele, parada primeiro, depois mais tarefas atrasadas, mais tarefas paradas e a
    semana mais baixa (decisão do Levi, 18/10/2026); no empate, o nome."""
    m = u.get("manutencao") or {}
    pct = m.get("passada_pct")
    return (NIVEIS.index(u["manut"]["nivel"]), -len(u.get("paradas_abertas") or []), -(m.get("atrasadas") or 0),
            -(m.get("paradas") or 0), pct if pct is not None else 999, u["usina"])


def com_manutencao(usinas: list[dict], limite: int) -> list[dict]:
    """As usinas com o bloco Manutenção no limite de quem olha: cópias rasas (a cópia guardada de 5 min, comum a todos,
    nunca muda) com `manut` e o nível e o foco refeitos com os três blocos."""
    out = []
    for u in usinas:
        v = dict(u)
        al, bem = alertas_manutencao(v, limite)
        al.sort(key=lambda a: -PESO[a["nivel"]])
        v["manut"] = {"alertas": al, "bem": bem, "nivel": _nivel(al), "peso": sum(PESO[a["nivel"]] for a in al),
                      **linha_manutencao(v, limite)}
        v["nivel"] = min((v["perf"]["nivel"], v["acomp"]["nivel"], v["manut"]["nivel"]), key=NIVEIS.index)
        v["foco"] = v["perf"]["peso"] + v["acomp"]["peso"] + v["manut"]["peso"]
        out.append(v)
    out.sort(key=ordem_do_foco)
    return out


def ordem_do_foco(u: dict):
    """A usina que mais pede o responsável em cima: o peso dos dois blocos; no empate, a mais longe da meta e o nome."""
    ating = (u.get("meta") or {}).get("atingimento")
    return (-u["foco"], ating if ating is not None else 999, u["usina"])


def bloco(usinas: list[dict], qual: str) -> dict:
    """As linhas de um bloco e a triagem. TODAS as usinas viram linha, inclusive as em dia (Levi, 13/10/2026: "tem que
    aparecer todas as usinas do responsável inclusive as que estão em dia"; até ali as em dia ficavam recolhidas no fim),
    na ordem do bloco ("ordene da pior meta para a melhor em performance e em acompanhamento ordene pelas rondas"): a
    Performance pela meta do mês, da pior para a melhor (sem meta no fim); o Acompanhamento pela ronda (`ordem_da_ronda`).
    A cor de cada linha continua a do nível dela."""
    chave = {"perf": ordem_da_meta, "manut": ordem_da_manutencao}.get(qual, ordem_da_ronda)
    tri = collections.Counter(u[qual]["nivel"] for u in usinas)
    return {"linhas": sorted(usinas, key=chave), "tri": {n: tri.get(n, 0) for n in NIVEIS}}


def ordem_da_meta(u: dict):
    """A Performance: da pior meta do mês para a melhor; sem meta publicada, no fim; no empate, o nome."""
    ating = (u.get("meta") or {}).get("atingimento")
    return (ating is None, ating if ating is not None else 0, u["usina"])


RONDA_ORDEM = {"nunca": 0, "sem_ronda": 1, "longa_pendente": 2}


def ordem_da_ronda(u: dict):
    """O Acompanhamento pela ronda, a pior em cima, na régua da Central de atenção: nunca teve ronda; sem ronda há 7
    dias ou mais (mais dias primeiro); ronda longa pendente; em dia (a mais antiga primeiro: "há 4 d" antes de "hoje");
    sem dado de ronda no fim. No empate, o nome."""
    r = u.get("ronda") or {}
    dias = r.get("dias") if isinstance(r.get("dias"), (int, float)) and r.get("dias") < 999 else None
    grupo = RONDA_ORDEM.get(r.get("tipo"), 3 if dias is not None else 4)
    return (grupo, -(dias or 0), u["usina"])


# ── A Visão geral (18/10/2026) ────────────────────────────────────────────────────────────────────────────────────
# Levi: "uma visão onde unifica todas as usinas", com os KPIs dos três blocos que, ao clicar, "já filtra as usinas em
# atenção daquele bloco". Cada chave é (bloco, rótulo, a condição): o número usa a MESMA condição que o conta no `soma`
# (nenhuma régua nova); a chave do bloco são as usinas que pedem atenção nele (focar ou acompanhar), e
# `<bloco>.<nível>`, só aquele nível. Vai no endereço (`?modo=geral&filtro=manut.atrasadas`); chave que não existe é
# ignorada.
def _meta(u) -> dict:
    return u.get("meta") or {}


def _manut(u) -> dict:
    return u.get("manutencao") or {}


def _abaixo_da_meta(u) -> bool:
    a = _meta(u).get("atingimento")
    return a is not None and a < META_NA_META


def _pr_abaixo(u) -> bool:
    m = _meta(u)
    return m.get("pr") is not None and m.get("pr_meta") is not None and m["pr"] < m["pr_meta"]


def _disp_abaixo(u) -> bool:
    d = (u.get("disp") or {}).get("disp")
    return d is not None and d < DISP_OK


def _semana_abaixo(u) -> bool:
    from .manutencao import META_SEMANA
    p = _manut(u).get("passada_pct")
    return p is not None and p < META_SEMANA


FILTROS_GERAL = {
    "perf.abaixo_meta": ("perf", "Abaixo da meta", _abaixo_da_meta),
    "perf.pr_abaixo": ("perf", "PR abaixo", _pr_abaixo),
    "perf.disp": ("perf", "Disponibilidade abaixo de 99%", _disp_abaixo),
    "acomp.rondas": ("acomp", "Rondas pendentes",
                     lambda u: (u.get("ronda") or {}).get("tipo") in ("nunca", "sem_ronda", "longa_pendente")),
    "acomp.pts": ("acomp", "PT esperando", lambda u: bool((u.get("pt") or {}).get("aguardando"))),
    "acomp.chamados": ("acomp", "Chamados", lambda u: bool((u.get("chamados") or {}).get("abertos"))),
    "acomp.ext": ("acomp", "Extintores vencidos", lambda u: bool((u.get("extintores") or {}).get("vencidos"))),
    "manut.atrasadas": ("manut", "Tarefas atrasadas", lambda u: bool(_manut(u).get("atrasadas"))),
    "manut.paradas": ("manut", "Tarefas pausadas", lambda u: bool(_manut(u).get("paradas"))),
    "manut.semana": ("manut", "Semana passada abaixo de 85%", _semana_abaixo),
}
for _b, _nome, _txt in BLOCOS:
    FILTROS_GERAL[_b] = (_b, "pedem atenção", lambda u, b=_b: (u.get(b) or {}).get("nivel", "ok") != "ok")
    FILTROS_GERAL[f"{_b}.critico"] = (_b, "focar", lambda u, b=_b: (u.get(b) or {}).get("nivel") == "critico")
    FILTROS_GERAL[f"{_b}.atencao"] = (_b, "acompanhar", lambda u, b=_b: (u.get(b) or {}).get("nivel") == "atencao")


def filtro_geral(valor) -> str | None:
    """A chave do filtro da Visão geral, ou None (vazio, lixo ou chave que não existe: a aba abre sem filtro)."""
    v = str(valor or "").strip()
    return v if v in FILTROS_GERAL else None


# a ordem dos blocos na Visão geral (Levi, 18/10/2026: "A ordem é essa mesmo: Performance, manutenção e acompanhamento")
BLOCOS_GERAL = ("perf", "manut", "acomp")


def bloco_geral(valor, filtro: str | None) -> str | None:
    """O bloco que ordena e destaca a lista (Levi: "ao clicar no bloco em Visão geral destaque as colunas daquele bloco
    e ordene de acordo com aquele bloco"): o `bloco` do endereço; sem ele, o bloco do filtro; sem os dois, nenhum."""
    v = str(valor or "").strip()
    if v in BLOCOS_GERAL:
        return v
    return FILTROS_GERAL[filtro][0] if filtro in FILTROS_GERAL else None


def lista_geral(usinas: list[dict], filtro: str | None, qual: str | None) -> list[dict]:
    """As usinas do filtro, na ordem do bloco escolhido (a mesma régua de ordem do bloco: a pior meta, a pior ronda,
    a Manutenção pelo nível e pelas atrasadas); sem bloco, na ordem que vieram (a do foco, `ordem_do_foco`)."""
    lista = filtrar_geral(usinas, filtro)
    return bloco(lista, qual)["linhas"] if qual in BLOCOS_GERAL else lista


def filtrar_geral(usinas: list[dict], chave: str | None) -> list[dict]:
    """As usinas que entram no filtro `chave`; sem chave válida, todas."""
    if chave not in FILTROS_GERAL:
        return list(usinas)
    cond = FILTROS_GERAL[chave][2]
    return [u for u in usinas if cond(u)]


def soma(nome: str, usinas: list[dict]) -> dict:
    """O resumo de um grupo de usinas (um responsável, ou o filtro da tela), por bloco: a triagem (focar, acompanhar,
    pode esperar); na Performance, a meta do grupo (produção ÷ meta das usinas com meta, a conta do Gerencial), as
    usinas abaixo de 97% e com PR abaixo do previsto, e a disponibilidade média pesada pela potência (o resumo por
    cliente de lá); no Acompanhamento, as rondas pendentes, as PT esperando (paradas e paradas de hoje), os chamados em
    aberto e os extintores vencidos. E os ativos em crítico e as 3 usinas que mais pedem."""
    s = {"responsavel": nome, "usinas": len(usinas), "pts": 0, "paradas": 0, "agora": 0, "rondas": 0, "chamados": 0,
         "ext_vencidos": 0, "ativos_criticos": 0, "abaixo_meta": 0, "pr_abaixo": 0,
         # a Manutenção (18/10/2026): OS abertas, tarefas atrasadas, tarefas paradas, OS de parada aberta e a semana
         # passada do grupo (linhas do plano feitas ÷ linhas do plano, a conta do Fechamento)
         "os_abertas": 0, "atrasadas": 0, "tarefas_paradas": 0, "paradas_abertas": 0}
    prod = meta = disp_p = pot = 0.0
    sem_prog = sem_feitas = 0
    for u in usinas:
        m = u.get("meta") or {}
        if m.get("prod_kwh") is not None and m.get("meta_kwh"):
            prod += m["prod_kwh"]
            meta += m["meta_kwh"]
        if m.get("atingimento") is not None and m["atingimento"] < META_NA_META:
            s["abaixo_meta"] += 1
        if m.get("pr") is not None and m.get("pr_meta") is not None and m["pr"] < m["pr_meta"]:
            s["pr_abaixo"] += 1
        d = u.get("disp") or {}
        if d.get("disp") is not None:
            p = d.get("pot_kwp") or 1.0
            disp_p += p * d["disp"]
            pot += p
        s["pts"] += u["pt"]["aguardando"]
        s["paradas"] += u["pt"]["paradas"]
        s["agora"] += u["pt"]["paradas_hoje"]
        s["rondas"] += (u.get("ronda") or {}).get("tipo") in ("nunca", "sem_ronda", "longa_pendente")
        s["chamados"] += (u.get("chamados") or {}).get("abertos", 0)
        s["ext_vencidos"] += (u.get("extintores") or {}).get("vencidos", 0)
        s["ativos_criticos"] += (u.get("ativos") or {}).get("critico", 0)
        m = u.get("manutencao") or {}
        s["os_abertas"] += m.get("os_abertas") or 0
        s["atrasadas"] += m.get("atrasadas") or 0
        s["tarefas_paradas"] += m.get("paradas") or 0
        s["paradas_abertas"] += len(u.get("paradas_abertas") or [])
        sem_prog += m.get("passada_prog") or 0
        sem_feitas += m.get("passada_feitas") or 0
    # o bloco Manutenção só existe depois do limite de quem olha (`com_manutencao`); sem ele, a triagem dele é zero
    for qual in ("perf", "acomp", "manut"):
        tri = collections.Counter(u[qual]["nivel"] for u in usinas if qual in u)
        s[qual] = {n: tri.get(n, 0) for n in NIVEIS}
    s["meta_pct"] = round(100 * prod / meta, 1) if meta else None
    s["disp"] = round(disp_p / pot, 1) if pot else None
    s["semana_pct"] = round(100 * sem_feitas / sem_prog, 1) if sem_prog else None
    s["pior"] = [u["usina"] for u in sorted((u for u in usinas if u["nivel"] == "critico"), key=ordem_do_foco)[:3]]
    s["nivel"] = min(("critico" if s[q]["critico"] else ("atencao" if s[q]["atencao"] else "ok")
                      for q in ("perf", "acomp", "manut")), key=NIVEIS.index)
    return s


def por_responsavel(usinas: list[dict]) -> list[dict]:
    """Um cartão por Responsável O&M (`soma` das usinas dele, já filtradas pela tela). "Sem responsável O&M" por último;
    antes, quem tem mais usinas pedindo foco."""
    g = collections.defaultdict(list)
    for u in usinas:
        g[u.get("responsavel") or visao.SEM_RESPONSAVEL].append(u)
    out = [soma(nome, us) for nome, us in g.items()]
    out.sort(key=lambda s: (s["responsavel"] == visao.SEM_RESPONSAVEL,
                            -(s["perf"]["critico"] + s["acomp"]["critico"] + s["manut"]["critico"]),
                            -(s["perf"]["atencao"] + s["acomp"]["atencao"] + s["manut"]["atencao"]), s["responsavel"]))
    return out


# ── As janelas: o dia a dia de onde vem cada número (12/10/2026) ───────────────────────────────────────────────
# Levi: "Precisamos de visuais que expliquem melhor para o supervisor o que está acontecendo, esses dados são muito
# importantes e interessantes porém precisamos mostrar para o supervisor de onde está vindo!". Cada janela lê o MESMO dado
# da tela dona, publicado no banco pela plataforma.
def _linhas_da_usina(linhas, uid, nomes, campo="usina", fracttal="usina_fracttal") -> list[dict]:
    """As linhas cujo nome (o da planilha) liga à usina `uid` do cadastro (`Nomes`, a mesma ligação da meta e da
    disponibilidade); o nome de cada linha é resolvido uma vez."""
    vistos, out = {}, []
    for r in linhas:
        n = str(r.get(campo) or "")
        if n not in vistos:
            vistos[n] = nomes.usina(n, fracttal=str(r.get(fracttal) or ""))[0]
        if vistos[n] == uid:
            out.append(r)
    return out


def serie_diaria(uid: int, mes_id: int, nomes: Nomes) -> dict:
    """O dia a dia da usina no mês (`nexus_performance · fato_desempenho_usina_dia`): {dias: [{dia, geracao_kwh, meta_kwh,
    ipoa, ipoa_meta, pr, pr_meta}], usinas_gerencial, publicado}. A geração é a do dia que o Gerencial conta no
    atingimento (vazia no dia que só o PR diário tem); o POA e o PR, os do PR diário do Painel NOC. Usina do cadastro com
    duas usinas no Gerencial (Santarém 1 e 2): a geração soma por dia, e a meta também, só das que têm geração no dia
    (é a conta do Gerencial somada); o POA e o PR são a média pesada pela meta (sem meta, a média simples)."""
    todas = visao._livro(LIVRO_META, ABA_DIA)
    rs = _linhas_da_usina([r for r in todas if _int(r.get("mes_id")) == mes_id], uid, nomes)
    por = collections.defaultdict(list)
    for r in rs:
        d = _dia_do_id(r.get("data_id"))
        if d:
            por[d.day].append(r)
    dias = []
    for dia in sorted(por):
        xs = por[dia]
        ger = [_num(r.get("geracao_kwh")) for r in xs if _num(r.get("geracao_kwh")) is not None]
        contam = [r for r in xs if _num(r.get("geracao_kwh")) is not None] or xs
        meta = [_num(r.get("meta_kwh")) for r in contam if _num(r.get("meta_kwh")) is not None]

        def media(campo):
            vs = [(_num(r.get(campo)), _num(r.get("meta_kwh")) or 1.0) for r in xs if _num(r.get(campo)) is not None]
            peso = sum(w for _v, w in vs)
            return round(sum(v * w for v, w in vs) / peso, 2) if peso else None
        dias.append({"dia": dia, "geracao_kwh": sum(ger) if ger else None, "meta_kwh": sum(meta) if meta else None,
                     "ipoa": media("ipoa_kwh_m2"), "ipoa_meta": media("ipoa_meta_kwh_m2"), "pr": media("pr_pct"),
                     "pr_meta": media("pr_meta_pct")})
    return {"dias": dias, "usinas_gerencial": sorted({str(r.get("usina") or "") for r in rs}), "publicado": bool(todas)}


def tabela_meta(serie: dict, disp: dict | None = None, disp_mes: float | None = None) -> dict:
    """A tabela da janela da Meta (Levi: "uma tabelinha de dia do mês, geração meta, geração real do dia e um total no
    final"): uma linha por dia que o Gerencial conta (o que tem geração), em MWh, e o total (a soma dos dias e a meta dos
    mesmos dias: é a conta do Gerencial, atingimento = produção ÷ meta dos dias cobertos). Provado em 13/10/2026 com o
    Gerencial de outubro: fecha nas 135 usinas com série (produção, dias e %). O dia só do PR diário (sem geração) fica
    de fora: ele não entra na conta.

    E o porquê do dia (Levi, 13/10/2026: "na tabelinha da meta por dia você adicione o POA DEF e a disponibilidade!"): o
    POA do dia (o da série, o do PR diário; vazio quando o sensor não leu) e a disponibilidade do dia fechado (`disp` =
    `disp_diaria`, a do Gerencial › Disponibilidade; vazia até o dia fechar). Geração baixa com POA baixo é tempo; com
    disponibilidade baixa é parada. No total, o POA é a soma dos dias da tabela e a disponibilidade é a do mês
    (`disp_mes`, a média dos dias fechados: o mesmo número da coluna Disp. da Visão)."""
    por_dia = {x["dia"]: x for x in (disp or {}).get("dias") or []}
    linhas, soma_meta, soma_real, soma_poa, com_poa = [], 0.0, 0.0, 0.0, 0
    for d in serie.get("dias") or []:
        meta = None if d.get("meta_kwh") is None else d["meta_kwh"] / 1000
        real = None if d.get("geracao_kwh") is None else d["geracao_kwh"] / 1000
        if real is None:
            continue
        if meta is not None:
            soma_meta += meta
            soma_real += real
        pct = round(100 * real / meta) if meta and real is not None else None
        poa = d.get("ipoa")
        if poa is not None:
            soma_poa += poa
            com_poa += 1
        dd = (por_dia.get(d["dia"]) or {}).get("disp")
        linhas.append({"dia": d["dia"], "meta": meta, "real": real, "dif": None if meta is None or real is None else real - meta,
                       "pct": pct, "cls": cls_meta(pct), "poa": poa, "disp": dd, "disp_cls": cls_disp(dd)})
    pct = round(100 * soma_real / soma_meta, 1) if soma_meta else None
    return {"linhas": linhas, "total": {"meta": soma_meta or None, "real": soma_real if soma_meta else None,
                                        "dif": (soma_real - soma_meta) if soma_meta else None, "pct": pct,
                                        "cls": cls_meta(pct), "poa": round(soma_poa, 2) if com_poa else None,
                                        "disp": disp_mes, "disp_cls": cls_disp(disp_mes)},
            "disp_ate": (disp or {}).get("ate") or "", "com_disp": bool(por_dia)}


def disp_diaria(uid: int, mes: str, nomes: Nomes) -> dict:
    """O mapa diário da disponibilidade da usina no mês (o "Mapa diário · usina × dia" do Gerencial › Disponibilidade, só
    esta usina): {dias: [{dia, disp, h}], ate}. Duas usinas do Gerencial na mesma do cadastro: pesadas pela potência."""
    rs = _linhas_da_usina([r for r in visao._livro(LIVRO_DISP, ABA_DISP) if str(r.get("mes") or "") == mes], uid, nomes)
    por = collections.defaultdict(list)
    for r in rs:
        dia = str(r.get("dia") or "")[:10]
        if _num(r.get("disp")) is not None and dia:
            por[dia].append(r)
    dias = []
    for dia in sorted(por):
        xs = por[dia]
        pesos = [(_num(r.get("pot_kwp")) or 1.0) for r in xs]
        tot = sum(pesos)
        disp = sum(p * _num(r.get("disp")) for p, r in zip(pesos, xs)) / tot
        h = sum(p * (_num(r.get("h_perdidas")) or 0.0) for p, r in zip(pesos, xs)) / tot
        dias.append({"dia": int(dia[8:10]), "data": dia, "disp": round(disp, 1), "h": round(h, 2),
                     "faixa": faixa_disp(disp)})
    return {"dias": dias, "ate": max(por) if por else ""}


def faixa_disp(d) -> str:
    """A faixa da legenda do mapa diário da Disponibilidade (a mesma de lá): 100% sem evento, 99–100%, 95–99%, 80–95%,
    50–80% e abaixo de 50%."""
    if d is None:
        return "sem"
    return ("c0" if d >= 99.95 else "c-ok" if d >= 99 else "c-a1" if d >= 95 else "c-a2" if d >= 80
            else "c-r1" if d >= 50 else "c-r2")


def _hora(iso) -> str:
    s = str(iso or "")
    return f"{s[8:10]}/{s[5:7]} {s[11:16]}" if len(s) >= 16 else (f"{s[8:10]}/{s[5:7]}" if len(s) >= 10 else "—")


def os_disponibilidade(uid: int, mes: str, nomes: Nomes) -> dict:
    """As OS que formaram a disponibilidade da usina no mês (`falhas_performance · disponibilidade_os`, a conta do
    Gerencial): {oss: [{os, tipo, origem, escopo, inicio, fim, aberta, duracao_min, sol_min, perda_kwh}], totais,
    publicado}. Duração = do início ao fim da OS (o relógio); horas de sol = as de 06–18 h da OS dentro do mês (as que
    contam na conta), as mesmas em cada usina dela; perda = a da OS NESTA usina pela régua de lá (kWp afetado × horas de
    sol, sem a irradiação), e por isso o total é a perda da usina no Gerencial. Desde 15/10/2026 a disponibilidade é só
    do Fracttal, isolada da geração (até ali a geração "desmentia" dias e a OS podia ficar com 0). Até 13/10/2026 a
    plataforma repartia a perda da OS de duas usinas pela potência (setembro: 47.893 kWh entre Rodrigues 1 e 2)."""
    from datetime import datetime as _dt
    todas = visao._livro(LIVRO_DISP, ABA_DISP_OS)
    rs = _linhas_da_usina([r for r in todas if str(r.get("mes") or "") == mes], uid, nomes)
    oss = []
    for r in rs:
        ini, fim = str(r.get("inicio") or ""), str(r.get("fim") or "")
        dur = None
        try:
            if ini and fim:
                dur = max(0, int((_dt.fromisoformat(fim[:19]) - _dt.fromisoformat(ini[:19])).total_seconds() // 60))
        except ValueError:
            dur = None
        aberta = str(r.get("aberta") or "").strip().lower() in ("sim", "true", "1")
        oss.append({"os": str(r.get("os") or ""), "tipo": str(r.get("tipo") or "—"), "origem": str(r.get("origem") or ""),
                    "escopo": str(r.get("escopo") or "—"), "codigo": str(r.get("codigo_ativo") or ""),
                    "inicio": _hora(ini), "fim": _hora(fim) if fim else "", "aberta": aberta, "duracao_min": dur,
                    "sol_min": _int(r.get("duracao_sol_min")), "perda_kwh": _num(r.get("perda_kwh")), "_ini": ini})
    oss.sort(key=lambda o: (o["_ini"], o["os"]))
    return {"oss": oss, "publicado": bool(todas),
            "total_perda": sum(o["perda_kwh"] or 0 for o in oss) if oss else None,
            "total_sol_min": sum(o["sol_min"] or 0 for o in oss) if oss else None}


def _ler_fonte(nome, f, erros):
    """Uma fonte (regra 13): a que falha volta vazia, e a tela diz qual foi e por quê."""
    try:
        return f()
    except Exception as e:      # noqa: BLE001 — fonte fora: as outras seguem
        erros[nome] = f"{type(e).__name__}: {str(e)[:120]}"
        return {}, {}


def visao_responsaveis() -> "visao.leitura.Leitura":
    """A conta da tela, numa cópia de 5 min (`visao._ler`)."""
    def calcular():
        b = visao._Base()
        agora = visao._agora()
        hoje = agora.date()
        at = visao.atencao(visao.DIAS_COBERTURA)
        if at.erro:
            raise visao.SemBanco(at.erro)
        pts = visao.pts()
        erros = {}
        nomes = Nomes(b)
        mes_id, mes = hoje.year * 100 + hoje.month, hoje.strftime("%Y-%m")
        met, met_i = _ler_fonte("metas", lambda: metas(nomes, mes_id), erros)
        dsp, dsp_i = _ler_fonte("disp", lambda: disponibilidade(nomes, mes), erros)
        atv, atv_i = _ler_fonte("ativos", ativos, erros)
        cha, cha_i = _ler_fonte("chamados", lambda: chamados(hoje), erros)
        ext, ext_i = _ler_fonte("extintores", extintores, erros)
        lim, lim_i = _ler_fonte("limpeza", limpeza, erros)
        par, par_i = _ler_fonte("paradas", lambda: paradas_abertas(nomes, mes), erros)
        man, man_i = _ler_fonte("manut", lambda: manutencao_fonte(b, hoje, agora), erros)
        rk, rk_i = _ler_fonte("ranking", lambda: ranking_fonte(b, hoje), erros)
        if pts.erro:
            erros["pt"] = pts.erro
        fontes = {"metas": met, "disp": dsp, "ativos": atv, "chamados": cha, "extintores": ext, "limpeza": lim,
                  "paradas": par, "manut": man}
        usinas = montar(b, at.dados.get("usinas") or [], at.dados.get("pendentes") or [],
                        (pts.dados or {}).get("aguardando") or [], fontes, hoje)
        responsaveis_por_pessoa = {}
        for uid in b.mobilizadas:
            pid = visao.D._id((b.por_id.get(uid) or {}).get("responsavel_om_id"))
            if pid:
                responsaveis_por_pessoa[pid] = b.responsavel_da_usina(uid)
        return {"usinas": usinas, "mes_id": mes_id, "hoje": hoje.isoformat(), "erros": erros,
                "info": {"metas": met_i, "disp": dsp_i, "ativos": atv_i, "chamados": cha_i, "extintores": ext_i,
                         "limpeza": lim_i, "paradas": par_i, "manut": man_i, "ranking": rk_i},
                # o Ranking das equipes (18/10/2026): as notas do App por usina e quantos técnicos cada equipe tem
                "ranking_por_usina": rk,
                "tecnicos_por_equipe": {nome: t.get("tecnicos", 0) for nome, t in b.times().items()},
                "responsaveis_por_pessoa": responsaveis_por_pessoa, "sem_mobilizacao": b.sem_mobilizacao,
                "fatos": at.dados.get("fatos") or {}, **visao._estrutura(b)}
    return visao._ler(("visao_responsaveis",), calcular)
