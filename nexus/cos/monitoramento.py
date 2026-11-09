"""O Monitoramento do COS (09/11/2026): a geração em kW ao vivo e a curva do dia de cada usina com logger (SCADA Grid) e
do SunOP.

O dono: "geração em kw ao vivo com a curva de cada usina atualizando constantemente, somente as que tem logger e as que
são sunop, as da plataforma. Ignora esse monitoramento que já existe no nexus" (a Performance › Tempo real, que é a
Plataforma de Performance, outra fonte).

Nada aqui é regra de geração: o kW, a situação, o frescor e a curva vêm prontos da Ronda COS (o mesmo cartão da tela de
monitoramento de lá, pelo Andamento: `andamento.ler_geracao` e `andamento.ler_curvas`). Daqui são só os filtros, as
contas da faixa e o desenho da curva (o caminho do SVG), que é puro e testável sem Flask.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import andamento as AND

# A situação do cartão (a `chave` da Ronda COS, `ChaveSituacaoScada`) no grupo do filtro e no tom da casa. STANDBY é o
# inversor dormindo de noite ou sem sol: não é falha. A chave que o Nexus não conhece cai em "outras", neutra, com o
# texto que a Ronda COS mandou.
SITUACOES = {
    "GERANDO": ("gerando", "ok"),
    "PAROU": ("parada", "critico"),
    "SEM_COMUNICACAO": ("sem_comunicacao", "alerta"),
    "SEM_INVERSOR": ("outras", "neutro"),
    "STANDBY": ("outras", "neutro"),
}
GRUPOS = {
    "gerando": "Gerando",
    "parada": "Parada",
    "sem_comunicacao": "Sem comunicação",
    "outras": "Outras",
}
# A parada e a sem comunicação primeiro: o operador olha o que caiu antes do que gera.
_ORDEM_DO_GRUPO = {"parada": 0, "sem_comunicacao": 1, "outras": 2, "gerando": 3}
BUSCA_MAX = 80

# A janela da curva: o dia solar. Fora dela não há amostra (o coletor não grava das 19h às 4h, `scada_amostra`); as
# usinas ficam lado a lado no mesmo eixo, para a curva de uma se comparar com a da outra.
CURVA_DE_H, CURVA_ATE_H = 5, 19
LARGURA, ALTURA = 160, 36


def kw_txt(kw) -> str:
    """O kW em pt-BR, em MW a partir de 1.000 kW: "812 kW", "1,2 MW". None é "—" (a Ronda COS não sabe; nunca zero)."""
    if kw is None:
        return "—"
    if abs(kw) >= 1000:
        return f"{kw / 1000:.1f}".replace(".", ",") + " MW"
    return f"{kw:.0f} kW"


@dataclass
class Curva:
    """A curva do dia de uma usina no SVG: o caminho da linha e o da área (os trechos sem amostra ficam em branco, sem
    ponte entre eles), o máximo e quando, e os pontos para a dica do mouse."""
    linha: str = ""
    area: str = ""
    maximo: float | None = None
    maximo_em: str = ""
    pontos: list = field(default_factory=list)   # [(hh:mm, kw | None)] dentro da janela


def curva(kw: list, inicio: datetime | None, passo_min: int) -> Curva:
    """O desenho da curva no viewBox LARGURA × ALTURA, de CURVA_DE_H a CURVA_ATE_H, na escala da própria usina (de 0 ao
    máximo dela: a plataforma não guarda o kWp, e um teto inventado mentiria)."""
    if not inicio or not passo_min or not kw:
        return Curva()
    de = inicio.replace(hour=CURVA_DE_H, minute=0, second=0, microsecond=0)
    ate = inicio.replace(hour=CURVA_ATE_H, minute=0, second=0, microsecond=0)
    total_min = (ate - de).total_seconds() / 60
    pontos = []
    for i, v in enumerate(kw):
        t = inicio + timedelta(minutes=i * passo_min)
        if de <= t <= ate:
            pontos.append((t, v if isinstance(v, (int, float)) else None))
    valores = [v for _t, v in pontos if v is not None]
    if not valores:
        return Curva(pontos=[(t.strftime("%H:%M"), None) for t, _v in pontos])
    teto = max(max(valores), 1e-9)
    trechos, atual = [], []
    for t, v in pontos:
        if v is None:
            if atual:
                trechos.append(atual)
            atual = []
            continue
        x = (t - de).total_seconds() / 60 / total_min * LARGURA
        y = ALTURA - max(v, 0) / teto * (ALTURA - 2) - 1      # 1 px de folga em cima e embaixo, para o traço de 2 px
        atual.append((round(x, 1), round(y, 1)))
    if atual:
        trechos.append(atual)
    linha = " ".join("M" + " L".join(f"{x},{y}" for x, y in tr) for tr in trechos)
    area = " ".join(f"M{tr[0][0]},{ALTURA} " + " ".join(f"L{x},{y}" for x, y in tr) + f" L{tr[-1][0]},{ALTURA} Z"
                    for tr in trechos)
    i_max = max(range(len(pontos)), key=lambda i: pontos[i][1] if pontos[i][1] is not None else float("-inf"))
    return Curva(linha=linha, area=area, maximo=max(valores), maximo_em=pontos[i_max][0].strftime("%H:%M"),
                 pontos=[(t.strftime("%H:%M"), v) for t, v in pontos])


@dataclass
class Painel:
    itens: list = field(default_factory=list)
    resumo: dict = field(default_factory=dict)
    contagem: dict = field(default_factory=dict)
    clientes: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    gerado_em: datetime | None = None
    curvas_de: datetime | None = None


def _linha(u: dict, c: Curva | None, agora: datetime) -> dict:
    grupo, tom = SITUACOES.get(str((u.get("situacao") or {}).get("chave") or ""), ("outras", "neutro"))
    lido = AND.instante(u.get("lido_em"))
    return {
        "id": str(u.get("id") or ""),
        "fonte": "SunOP" if u.get("fonte") == "SUNOP" else "SCADA Grid",
        "codigo": u.get("usina_codigo") or "",
        "nome": str(u.get("nome") or u.get("id") or ""),
        "sub_usina": u.get("sub_usina"),
        "cliente": u.get("cliente") or "",
        "kw": u.get("kw"),
        "kw_txt": kw_txt(u.get("kw")),
        "inversores_online": u.get("inversores_online"),
        "inversores_total": u.get("inversores_total"),
        "situacao": str((u.get("situacao") or {}).get("texto") or "") or GRUPOS[grupo],
        "grupo": grupo,
        "tom": tom,
        "fresca": bool(u.get("fresca")),
        "lido": lido.strftime("%H:%M") if lido else "",
        "minutos_atras": u.get("minutos_atras"),
        "tem_curva": bool(u.get("tem_curva")),
        "curva": c,
    }


def painel(geracao, curvas, agora: datetime, cliente: str = "", grupo: str = "", busca: str = "",
           fixa: bool = False) -> Painel | None:
    """A tela: as usinas (a parada e a sem comunicação primeiro, depois por cliente e nome), filtradas pelo cliente, pela
    situação e pela busca. As contagens das opções contam ANTES dos filtros delas (um contador que encolhe ao filtrar não
    diz mais quanto existe); a faixa conta a lista filtrada.

    `fixa` é a ordem do videowall: por cliente e nome, sempre a mesma. Na parede o operador aprende onde cada usina fica,
    e a que cai não pode trocar de lugar com as outras; quem chama a atenção é a cor dela, não a posição."""
    d = geracao.dados if geracao else None
    if not d:
        return None
    c = (curvas.dados if curvas else None) or {}
    inicio, passo = AND.instante(c.get("inicio")), c.get("passo_min") or 0
    por_id = {str(x.get("id")): x.get("kw") or [] for x in c.get("curvas") or []}
    todas = [_linha(u, curva(por_id[str(u.get("id"))], inicio, passo) if str(u.get("id")) in por_id else None, agora)
             for u in d.get("usinas") or []]
    todas.sort(key=lambda x: (0 if fixa else _ORDEM_DO_GRUPO[x["grupo"]], x["cliente"].lower(), x["nome"].lower(),
                              x["sub_usina"] or 0))

    contagem_cliente: dict[str, int] = {}
    for x in todas:
        contagem_cliente[x["cliente"] or "(sem cliente)"] = contagem_cliente.get(x["cliente"] or "(sem cliente)", 0) + 1
    no_cliente = [x for x in todas if not cliente or (x["cliente"] or "(sem cliente)") == cliente]
    contagem = {g: sum(1 for x in no_cliente if x["grupo"] == g) for g in GRUPOS}
    contagem["velhas"] = sum(1 for x in no_cliente if not x["fresca"])
    contagem["todas"] = len(no_cliente)
    palavras = " ".join((busca or "").lower().split())[:BUSCA_MAX].split()
    lista = [x for x in no_cliente
             if (not grupo or (grupo == "velhas" and not x["fresca"]) or x["grupo"] == grupo)
             and all(p in " ".join((x["nome"], x["codigo"], x["cliente"])).lower() for p in palavras)]

    frescas = [x for x in lista if x["fresca"] and x["kw"] is not None]
    avisos = []
    fontes = d.get("fontes") or {}
    for nome, f in (("SCADA Grid", fontes.get("scada") or {}), ("SunOP", fontes.get("sunop") or {})):
        if f.get("configurado") and not f.get("ok") and f.get("motivo"):
            avisos.append(f"{nome}: {str(f['motivo']).rstrip('. ')}")
    if (fontes.get("scada") or {}).get("canal_calado"):
        avisos.append("SCADA Grid: o canal está sem leitura nova; os números podem estar parados")
    return Painel(
        itens=lista,
        resumo={
            "usinas": len(lista),
            "kw_agora": sum(x["kw"] for x in frescas) if frescas else None,
            "gerando": sum(1 for x in lista if x["grupo"] == "gerando"),
            "paradas": sum(1 for x in lista if x["grupo"] in ("parada", "sem_comunicacao")),
            "parada": sum(1 for x in lista if x["grupo"] == "parada"),
            "sem_comunicacao": sum(1 for x in lista if x["grupo"] == "sem_comunicacao"),
            "velhas": sum(1 for x in lista if not x["fresca"]),
        },
        contagem=contagem,
        clientes=sorted(contagem_cliente.items(), key=lambda kv: kv[0].lower()),
        avisos=avisos,
        gerado_em=AND.instante(d.get("gerado_em")),
        curvas_de=AND.instante(c.get("gerado_em")),
    )


# A escala do videowall (`?escala=`): 1 é uma tela só; 0,5 é a parede 2 x 2 (a letra volta ao tamanho de um monitor). O
# limite segura o endereço digitado errado (escala 0 sumiria com tudo; 10 não caberia nada).
ESCALA_MIN, ESCALA_MAX = 0.4, 2.0


def escala_pedida(v) -> float:
    try:
        e = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return 1
    return round(min(ESCALA_MAX, max(ESCALA_MIN, e)), 2) if e > 0 else 1


def anormal(x: dict) -> str:
    """O que a usina tem de anormal, para o videowall: "parada", "semcom", "velha" (sem leitura nova) ou "" (normal)."""
    if x["grupo"] == "parada":
        return "parada"
    if x["grupo"] == "sem_comunicacao":
        return "semcom"
    return "" if x["fresca"] else "velha"


_ORDEM_DA_ATENCAO = {"parada": 0, "semcom": 1, "velha": 2}


def parede(p: Painel) -> dict:
    """O videowall (09/11/2026): as usinas agrupadas por cliente, cada grupo aberto por um cartão do cliente com o total
    dele, e a coluna "Atenção agora" com as anormais (a parada, depois a sem comunicação, depois a sem leitura nova; a mais
    antiga primeiro). A coluna fica sempre à vista: quando as usinas não cabem e a grade gira em páginas, nenhum problema
    fica escondido na página que não está na tela."""
    grupos: dict[str, list] = {}
    for x in p.itens:
        grupos.setdefault(x["cliente"] or "(sem cliente)", []).append(x)
    clientes = []
    for nome, itens in grupos.items():
        frescas = [x for x in itens if x["fresca"] and x["kw"] is not None]
        clientes.append({"cliente": nome, "itens": itens, "kw_agora": sum(x["kw"] for x in frescas) if frescas else None,
                         "anormais": sum(1 for x in itens if anormal(x))})
    atencao = sorted((x for x in p.itens if anormal(x)),
                     key=lambda x: (_ORDEM_DA_ATENCAO[anormal(x)], -(x["minutos_atras"] or 0), x["nome"].lower()))
    return {"clientes": clientes, "atencao": atencao}
