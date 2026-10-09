"""Extintores das usinas (Segurança · HSEQ): o que está vencido, perto de vencer e sem conferência há mais de 30 dias,
por supervisor de campo e por gestor de contrato.

Levi, 09/10/2026: "Gostaria de adicionar no Nexus algo que inseri no app: Extintores. Ficará no módulo de segurança.
Nele será possível ver a tabela dos extintores com uma visão do que está atrasado, perto de atrasar e sem atualização a
mais de 30 dias. Preciso da visão por supervisor."

De onde vem. A ronda de extintores do App de Campo (v247, 08/10/2026) substituiu o Microsoft Forms da TST: o técnico
confere extintor por extintor (carga, os 9 itens, as duas validades e a foto da etiqueta). O cadastro inicial é a
planilha de controle da TST (773 extintores em 81 usinas; o que o técnico acha fora da lista entra pelo App) e fica fora
do Fracttal. O App publica no banco o livro `extintores_app_campo`, aba `Extintores` (`COLUNAS`): 1 linha = 1 extintor,
com a última conferência (a do App ou, antes dele, a do Forms da TST) e as duas validades. Nada vem do Azure. Até o App
publicar o livro, a tela diz que ele ainda não chegou.

As situações (as contas são NOSSAS e estão aqui; o status que o App manda não entra na conta):
- ATRASADO: a recarga (2º nível) ou o teste hidrostático (3º nível) venceu. A data da etiqueta vale até o último dia do
  mês e só o ano vale até 31/12 (aba Legenda da planilha da TST).
- PERTO DE VENCER: não está atrasado e uma das duas vence em até 30 dias (o "Alerta de vencimento" da aba Legenda).
- SEM VALIDADE: a etiqueta da recarga está sem data e nada venceu nem vence em 30 dias: não dá para dizer se está em
  dia, então nunca conta como "em dia".
- EM DIA: o resto.
Essas quatro são exclusivas (cada extintor em uma, nessa ordem) e somam o total. À parte:
- SEM ATUALIZAÇÃO: a última conferência foi há mais de 30 dias, ou nunca houve. Soma-se às outras (um extintor pode
  estar atrasado E sem atualização): as contagens da faixa não somam ao total.

O status da TST (crítico, atenção, ok, ok sem validade), que olha também a carga e os itens do checklist, é a MESMA
regra do App (`_ext_status` no function_app.py, conferida 831 de 831 com o "Status geral" da planilha da TST em
08/10/2026): `status_tst`. Prova de 09/10/2026, fora do repositório (o cadastro tem nome de usina e o repositório é
público): as duas regras rodadas no cadastro inicial, 773 extintores × 549 dias (01/08/2026 a 31/01/2028), 424.377
comparações e 0 diferença; o status gravado no cadastro, 773 de 773. O teste (`tests/test_hseq_extintores.py`) fixa a
grade de casos do App, inclusive a virada do mês.
"""
import calendar
import re
from datetime import date

from ..campo import leitura, visao
from ..dados import livros

LIVRO = "extintores_app_campo"
ABA = "Extintores"
# O contrato com o App (a ordem do livro). Coluna nova entra no FIM. A pessoa vai como HMAC do e-mail e a observação do
# técnico NÃO vai (a API do banco tem leitura aberta): só "Tem informação adicional" (sim/não)
COLUNAS = ("Código", "Usina", "Código da usina", "Tipo de ativo", "Ativo", "Local", "Posição", "Classe", "Peso (kg)",
           "Validade da recarga", "Validade do hidrostático", "Última conferência", "Origem da conferência",
           "Conferido por (HMAC)", "Carga", "Itens NÃO", "Fotos", "Tem informação adicional", "Status", "Motivo",
           "Origem do cadastro")
# sem estas, a conta sairia errada sem aviso (validade vazia vira "sem validade"): a tela não conta pela metade
ESSENCIAIS = ("Código", "Usina", "Validade da recarga", "Validade do hidrostático", "Última conferência")
ALERTA_DIAS = 30            # o "Alerta de vencimento (dias)" da aba Legenda da TST (EXT_ALERTA_DIAS no App)
SEM_ATUALIZACAO_DIAS = 30   # Levi, 09/10: "sem atualização a mais de 30 dias"
SEM_DATA, SEM_SELO = "Sem data", "Sem selo"
# o NÃO destes deixa o extintor CRÍTICO; o dos outros quatro, em ATENÇÃO (aba Legenda da TST; EXT_ITENS_* no App)
ITENS_CRITICOS = (("manometro", "manômetro"), ("gatilho", "gatilho"), ("lacre", "lacre"), ("mangueira", "mangueira"),
                  ("casco", "casco"))
ITENS_ATENCAO = (("difusor", "difusor"), ("sinalizacao", "sinalização"), ("suporte", "suporte"),
                 ("pintura", "pintura"))
# as situações exclusivas, na ordem de gravidade (é a ordem da tabela): (rótulo, tom)
SITUACOES = {"atrasado": ("Atrasado", "critico"), "perto": ("Perto de vencer", "alerta"),
             "sem_validade": ("Sem validade", "neutro"), "em_dia": ("Em dia", "ok")}
# o que filtra a tabela (a faixa de números): as três do pedido e a sem validade
FILTROS = ("atrasado", "perto", "sem_atualizacao", "sem_validade")
STATUS_TST = {"CRITICO": ("Crítico", "critico"), "ATENCAO": ("Atenção", "alerta"), "OK": ("OK", "ok"),
              "OK_SEM_VALIDADE": ("OK sem validade", "neutro")}
_LONGE = 10 ** 6


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def validade_fim(v) -> date | None:
    """O último dia em que a etiqueta vale: 'MM/AAAA' até o último dia do mês; só o ano ('AAAA') até 31/12. 'Sem data',
    'Sem selo', vazio ou fora do formato = None (a validade é desconhecida). A mesma conta do App (`_ext_validade_fim`).
    O ano pode chegar como número ("2027.0": a API não garante o tipo)."""
    s = re.sub(r"\.0+$", "", _txt(v))
    m = re.fullmatch(r"(\d{1,2})/(\d{4})", s)
    if m:
        mes, ano = int(m.group(1)), int(m.group(2))
        return date(ano, mes, calendar.monthrange(ano, mes)[1]) if 1 <= mes <= 12 and 2000 <= ano <= 2100 else None
    if re.fullmatch(r"\d{4}", s) and 2000 <= int(s) <= 2100:
        return date(int(s), 12, 31)
    return None


def itens_nao(v) -> set:
    """Os itens do checklist com NÃO na última conferência: 'manometro; difusor' -> {'manometro', 'difusor'}. Aceita o
    rótulo com acento ("manômetro", "sinalização") e a vírgula."""
    return {visao._norm_nome(x).replace(" ", "") for x in re.split(r"[;,]", _txt(v)) if x.strip()}


def status_tst(carga, nao: set, val2, val3, hoje: date) -> tuple[str, str]:
    """(status, motivo) de UM extintor pela regra da TST (aba Legenda da planilha de controle, 29/09/2026), a mesma do
    App (`_ext_status`). CRITICO = validade vencida, sem carga, sobrecarga, ou NÃO em manômetro, gatilho, lacre,
    mangueira ou casco. ATENCAO = a validade vence em até 30 dias, ou NÃO em difusor, sinalização, suporte ou pintura.
    OK_SEM_VALIDADE = checklist limpo e sem a data da recarga. OK = o resto. "Validade" são as DUAS etiquetas."""
    crit, aten = [], []
    c = _txt(carga).upper().replace(" ", "_")
    if c == "SEM_CARGA":
        crit.append("sem carga")
    elif c == "SOBRECARGA":
        crit.append("sobrecarga")
    fim = validade_fim(val2)
    for v, f, venc, vence in ((val2, fim, "recarga vencida em %s", "recarga vence em %s"),
                              (val3, validade_fim(val3), "teste hidrostático vencido em %s",
                               "teste hidrostático vence em %s")):
        if f is None:
            continue
        dias = (f - hoje).days
        if dias < 0:
            crit.append(venc % _txt(v))
        elif dias <= ALERTA_DIAS:
            aten.append(vence % f.strftime("%d/%m"))
    crit += [rot + ": Não" for k, rot in ITENS_CRITICOS if k in nao]
    aten += [rot + ": Não" for k, rot in ITENS_ATENCAO if k in nao]
    if crit:
        return "CRITICO", " · ".join(crit)
    if aten:
        return "ATENCAO", " · ".join(aten)
    if fim is None:
        return "OK_SEM_VALIDADE", "Checklist limpo, mas falta a validade"
    return "OK", "Nada fora do lugar e validade em dia"


def tempo(dias) -> str:
    """Quanto tempo, para quem lê a tabela: até 59 dias, em dias ("43 d"); até 2 anos, em meses ("18 meses"); depois,
    em anos ("3 anos"). Na 1ª conferência com o cadastro da TST (09/10/2026) a tabela dizia "venceu há 557 d" e "vence
    em 1179 d": em dias, o número longo não diz nada a quem olha; e "1 ano e 6 meses" alargava a coluna a ponto de a
    tabela não caber a 1440 px. O mês é a média (30,44 d)."""
    n = abs(int(dias))
    if n < 60:
        return f"{n} d"
    meses = round(n / 30.44)
    return f"{meses} meses" if meses < 24 else f"{meses // 12} anos"


def _data(v) -> date | None:
    """O dia da conferência: 'AAAA-MM-DD' (o dia de Brasília, como o App manda) ou um ISO com hora (UTC vira
    Brasília)."""
    d = visao._dt(v)
    return d.date() if d else None


def situacao(x: dict, hoje: date) -> dict:
    """A situação de um extintor (uma linha do livro) no dia `hoje` (de Brasília). Ver o topo do módulo."""
    val2, val3 = _txt(x.get("Validade da recarga")), _txt(x.get("Validade do hidrostático"))
    f2, f3 = validade_fim(val2), validade_fim(val3)
    datas = sorted((f, qual) for f, qual in ((f2, "recarga"), (f3, "hidrostático")) if f)
    vencidas = [d for d in datas if d[0] < hoje]
    # a data que manda: a vencida mais antiga (atrasado) ou a próxima a vencer
    ref = vencidas[0] if vencidas else next((d for d in datas if d[0] >= hoje), None)
    dias_vence = (ref[0] - hoje).days if ref else None
    if vencidas:
        sit = "atrasado"
    elif dias_vence is not None and dias_vence <= ALERTA_DIAS:
        sit = "perto"
    elif f2 is None:
        sit = "sem_validade"
    else:
        sit = "em_dia"
    conf = _data(x.get("Última conferência"))
    dias_conf = (hoje - conf).days if conf else None
    nao = itens_nao(x.get("Itens NÃO"))
    # sem conferência nenhuma (o extintor cadastrado no App e ainda não conferido) não há status da TST
    st, motivo = status_tst(x.get("Carga"), nao, val2, val3, hoje) if conf else ("", "")
    # o que o status tem além da validade (a carga e os itens com NÃO): a tabela já mostra as validades ao lado
    checklist = " · ".join(p for p in motivo.split(" · ") if p.startswith(("sem carga", "sobrecarga"))
                           or p.endswith(": Não")) if st in ("CRITICO", "ATENCAO") else ""
    return {"val2": val2 or SEM_DATA, "val3": val3 or SEM_SELO, "fim2": f2, "fim3": f3,
            "situacao": sit, "atrasado": sit == "atrasado", "perto": sit == "perto",
            "sem_validade": sit == "sem_validade", "em_dia": sit == "em_dia",
            "vence": ref[0] if ref else None, "vence_qual": ref[1] if ref else "", "dias_vence": dias_vence,
            "conferencia": conf, "dias_conferencia": dias_conf,
            "sem_atualizacao": conf is None or dias_conf > SEM_ATUALIZACAO_DIAS,
            "status": st, "motivo": motivo, "motivo_checklist": checklist, "itens_nao": sorted(nao)}


def _num(v):
    try:
        f = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return int(f) if f == int(f) else f


def linha(x: dict, b, quem: dict, hoje: date) -> dict:
    """Uma linha do livro como a tela usa: o extintor, a situação e, do cadastro do Nexus, a usina e os papéis da
    estrutura de O&M de 10/2026 (a região de campo com o Supervisor de Campo, o gestor de contrato). A usina liga pelo
    nome do Fracttal (de-para do cadastro) e, sem ele, pelo código do ativo onde o extintor fica ou pelo código da
    usina (o mesmo `Ligador` dos fatos; código de duas usinas não liga). Sem ligação: o nome que o App escreveu, sem
    região nem gestor (cai em "Sem região de campo" e "Sem gestor de contrato")."""
    codigo, usina = _txt(x.get("Código")), _txt(x.get("Usina"))
    uid, _como = b.lig.usina(usina, _txt(x.get("Ativo")) or _txt(x.get("Código da usina")))
    return {"codigo": codigo, "ext": codigo.rsplit("-", 1)[-1], "usina_id": uid, **b.onde(uid, usina),
            "usina_fonte": usina, "tipo": _txt(x.get("Tipo de ativo")), "ativo": _txt(x.get("Ativo")),
            "local": _txt(x.get("Local")), "posicao": _txt(x.get("Posição")), "classe": _txt(x.get("Classe")),
            "peso": _num(x.get("Peso (kg)")), "origem_conferencia": _txt(x.get("Origem da conferência")),
            "conferido_por": visao._nome(quem, x.get("Conferido por (HMAC)")), "fotos": visao._int(x.get("Fotos")),
            "info_adicional": visao._sim(x.get("Tem informação adicional")),
            "origem_cadastro": _txt(x.get("Origem do cadastro")), **situacao(x, hoje)}


def extintores() -> leitura.Leitura:
    """Todos os extintores do livro, com a situação de hoje. Cópia de 5 min e renovada em segundo plano, como as telas
    do Campo (`visao._ler`). Livro que ainda não existe: lista vazia e `livro_existe` falso (a tela diz)."""
    def calcular():
        abas = visao._ciclo(("_abas", LIVRO), lambda: livros.abas(visao._base(), visao._sessao(), LIVRO))
        linhas = visao._livro(LIVRO, ABA) if ABA in abas else []
        b = visao._Base()
        hoje = visao._agora().date()
        publicado = visao._atualizados().get(LIVRO) if abas else None
        d = {"livro_existe": bool(abas), "aba_existe": ABA in abas, "hoje": hoje,
             "publicado_em": visao._hm_brt(publicado) if publicado else "", "times": b.times(), **visao._estrutura(b)}
        # o livro chegou sem uma coluna da conta (o App mudou o nome?): nenhum número, e a tela diz qual falta
        d["colunas_faltando"] = [c for c in ESSENCIAIS if linhas and c not in linhas[0]]
        if d["colunas_faltando"]:
            return {**d, "extintores": []}
        quem = visao._quem() if any(_txt(x.get("Conferido por (HMAC)")) for x in linhas) else {}
        return {**d, "extintores": [linha(x, b, quem, hoje) for x in linhas if _txt(x.get("Código"))]}
    return visao._ler(("hseq_extintores",), calcular)


def contar(lista) -> dict:
    """Os números da faixa: o total, as usinas e cada situação (as exclusivas e a sem atualização)."""
    c = {"total": len(lista), "usinas": len({x["usina"] for x in lista}),
         "sem_atualizacao": sum(x["sem_atualizacao"] for x in lista)}
    c.update({s: sum(x["situacao"] == s for x in lista) for s in SITUACOES})
    return c


def ordenar(lista, filtro: str = "") -> list:
    """A ordem da tabela: o mais grave primeiro (atrasado, perto, sem validade, em dia) e, dentro dele, o vencido há
    mais tempo e o que vence antes. No filtro "sem atualização", a conferência mais antiga primeiro (nunca conferido no
    topo)."""
    rank = {s: i for i, s in enumerate(SITUACOES)}
    if filtro == "sem_atualizacao":
        return sorted(lista, key=lambda x: (-(x["dias_conferencia"] if x["dias_conferencia"] is not None else _LONGE),
                                            x["usina"], x["codigo"]))
    return sorted(lista, key=lambda x: (rank[x["situacao"]], x["dias_vence"] if x["dias_vence"] is not None else _LONGE,
                                        x["usina"], x["codigo"]))


# ── Cartões por supervisor (região de campo) e por gestor de contrato ─────────────────────────────────────────────
# A "visão por supervisor" do pedido segue a estrutura de O&M de 10/2026, como a Central de atenção: o cartão é o da
# REGIÃO DE CAMPO, com o Supervisor de Campo e o Coordenador (ou a vaga), e a alternância leva ao GESTOR DE CONTRATO
# (Supervisor PM, pela usina). As listas chegam já filtradas pela tela, então o cartão conta o mesmo que a tabela.
_SOMA = ("extintores", "atrasado", "perto", "sem_validade", "em_dia", "sem_atualizacao")


def _cartao(**k) -> dict:
    return {**k, "equipes": [], "_usinas": set(), "_usinas_atrasado": set(), **dict.fromkeys(_SOMA, 0)}


def _somar(s, x):
    s["extintores"] += 1
    s[x["situacao"]] += 1
    s["sem_atualizacao"] += x["sem_atualizacao"]
    s["_usinas"].add(x["usina"])
    if x["atrasado"]:
        s["_usinas_atrasado"].add(x["usina"])
    if x.get("equipe") and x["equipe"] not in s["equipes"]:
        s["equipes"].append(x["equipe"])


def _fechar(s, times, com_codigo) -> dict:
    tm = [(times or {}).get(e) or {} for e in s["equipes"]]
    s["tecnicos"] = sum(t.get("tecnicos", 0) for t in tm)
    s["equipes"] = sorted(f"{t['codigo']} {e}" if com_codigo and t.get("codigo") else e
                          for e, t in zip(s["equipes"], tm))
    s["n_equipes"] = len(s["equipes"])
    s["usinas"], s["usinas_atrasado"] = len(s.pop("_usinas")), len(s.pop("_usinas_atrasado"))
    s["cor"] = ("critico" if s["atrasado"] else "alerta" if s["perto"] else "ok" if s["extintores"] else "neutro")
    return s


def por_regiao(lista, regioes=(), times=None) -> list[dict]:
    """Um cartão por região de campo (`regioes` = `_Base.regioes()`), com o Supervisor de Campo e o Coordenador ("vaga"
    quando não há ninguém), a base, as equipes das usinas e os técnicos delas. Usina sem região vai para o cartão
    próprio `SEM_REGIAO`, sempre por último. Ordem: mais atrasados, mais perto de vencer, a ordem da estrutura."""
    info = {r["nome"]: r for r in regioes or ()}
    g = {}
    for x in lista:
        nome = x.get("regiao_campo") or visao.SEM_REGIAO
        r = info.get(nome) or {}
        s = g.get(nome) or g.setdefault(nome, _cartao(
            regiao=nome, supervisor_campo=r.get("supervisor", ""), coordenador_campo=r.get("coordenador", ""),
            base=r.get("base", ""), ordem=r.get("ordem", _LONGE)))
        _somar(s, x)
    out = [_fechar(s, times, True) for s in g.values()]
    return sorted(out, key=lambda s: (s["regiao"] == visao.SEM_REGIAO, -s["atrasado"], -s["perto"], s["ordem"],
                                      s["regiao"]))


def por_gestor(lista, times=None) -> list[dict]:
    """Um cartão por gestor de contrato (Supervisor PM), pelas usinas dele; usina sem gestor no cadastro vai para o
    cartão próprio `SEM_GESTOR`, sempre por último."""
    g = {}
    for x in lista:
        nome = x.get("gestor") or visao.SEM_GESTOR
        _somar(g.get(nome) or g.setdefault(nome, _cartao(gestor=nome)), x)
    out = [_fechar(s, times, False) for s in g.values()]
    return sorted(out, key=lambda s: (s["gestor"] == visao.SEM_GESTOR, -s["atrasado"], -s["perto"], s["gestor"]))
