"""EPI e EPC (Segurança · HSEQ): começa pelo EPI, as luvas isolantes de cada usina pela ronda diária.

Levi, 09/10/2026: "Gostaria que criasse um campo de EPI / EPC começando apenas por EPI, puxando as luvas das rondas
diárias".

De onde vem. Desde a v207 do App (29/09/2026, pedido da TST depois da reunião com a Thopen) a ronda diária pergunta
"As luvas isolantes estão disponíveis?" (Sim ou Não, foto sempre; sem "Não se aplica": toda usina tem de ter o par), e o
"Não" já vira ponto na Central do App e e-mail à TST. Desde a v249 (09/10/2026) o App manda o checklist da ronda no livro
`rondas_app_campo` (coluna "Checklist da ronda", "rótulo: valor; ..."), com e sem OS, para as rondas da janela de 90
dias: a resposta das luvas sai daí (`resposta`). A ronda (o dia, a usina, a OS, quem fez) é a do fato único de ronda
(`visao._rondas_ligadas`), juntada ao livro cru pelo `Início`, como as telas do Campo. Medido em 09/10: 240 respostas
de 28/09 a 09/10 (188 Sim, 52 Não).

As contas (por usina; o universo é o das usinas mobilizadas, como a Central de atenção):
- SEM LUVAS: a última ronda respondeu Não. "Desde" = o 1º Não da sequência de Nãos até a última ronda.
- SEM VERIFICAÇÃO: nenhuma resposta das luvas há 7 dias ou mais (o mesmo limite da ronda pendente), ou nunca.
- COM LUVAS: a última ronda respondeu Sim (e há menos de 7 dias).
Uma usina sem luvas e sem verificação recente conta como SEM LUVAS (o último dado que se tem é o Não).

A resposta ainda não está no fato de ronda (`fato_ronda`): a tela lê o texto do livro cru. Se o App mudar o rótulo da
pergunta, nenhuma resposta casa e a tela diz isso (`rondas_com_checklist` > 0 e nenhuma resposta).
"""
import re
from datetime import date

from ..campo import leitura, visao
from ..dados import carga as C
from ..dados import fatos as D

PERGUNTA = "As luvas isolantes estão disponíveis?"          # o rótulo do item `infra_luvas` no App (v207)
_RESPOSTA = re.compile(re.escape(PERGUNTA) + r"\s*:\s*([^;\[]+)")
DIAS_SEM_VERIFICAR = visao.DIAS_SEM_RONDA_ALERTA            # 7: a mesma régua da ronda pendente
HISTORICO = 8                                               # as últimas respostas que a linha mostra
SITUACOES = {"sem_luvas": ("Sem luvas", "critico"), "sem_verificacao": ("Sem verificação", "info"),
             "com_luvas": ("Com luvas", "ok")}


def resposta(checklist) -> bool | None:
    """True (Sim), False (Não) ou None (a ronda não respondeu a pergunta das luvas) a partir do "Checklist da ronda"."""
    m = _RESPOSTA.search(str(checklist or ""))
    if not m:
        return None
    v = visao._norm_nome(m.group(1))
    return True if v == "sim" else (False if v in ("nao", "não") else None)


def _situacao(verifs, hoje) -> dict:
    """A situação de UMA usina pelas verificações dela (da mais nova para a mais velha)."""
    if not verifs:
        return {"situacao": "sem_verificacao", "ultima": None, "dias": None, "desde": None}
    ult = verifs[0]
    dias = (hoje - ult["dia"]).days
    if ult["luvas"] is False:
        desde = ult["dia"]
        for v in verifs[1:]:
            if v["luvas"] is not False:
                break
            desde = v["dia"]
        return {"situacao": "sem_luvas", "ultima": ult, "dias": dias, "desde": desde}
    return {"situacao": "com_luvas" if dias < DIAS_SEM_VERIFICAR else "sem_verificacao", "ultima": ult, "dias": dias,
            "desde": None}


def luvas() -> leitura.Leitura:
    """Uma linha por usina mobilizada (e por usina com resposta, mesmo fora dela), com a situação das luvas, a última
    verificação e o histórico das últimas respostas. Cópia de 5 min, renovada em segundo plano (`visao._ler`)."""
    def calcular():
        b = visao._Base()
        hoje = visao._agora().date()
        cru = {D._txt(r.get("Início")): r for r in visao._livro(*C.ORIGEM_RONDAS)}
        com_checklist = sum(1 for r in cru.values() if D._txt(r.get("Checklist da ronda")))
        por_usina = {}
        for r in visao._rondas_ligadas(b):
            if r.get("avulsa") or not r.get("data"):
                continue
            raw = cru.get(D._txt(r.get("inicio"))) or {}
            luv = resposta(raw.get("Checklist da ronda"))
            if luv is None:
                continue
            chave = r.get("usina_id") or ("nome", r.get("usina"))
            por_usina.setdefault(chave, {"onde": r, "verifs": []})["verifs"].append({
                "dia": date.fromisoformat(r["data"]), "inicio": r.get("inicio") or "", "luvas": luv,
                "tecnico": r.get("tecnico") or "", "os": r.get("os")})
        linhas = []
        for uid in b.mobilizadas:
            por_usina.setdefault(uid, {"onde": {"usina_id": uid, **b.onde(uid)}, "verifs": []})
        for chave, u in por_usina.items():
            verifs = sorted(u["verifs"], key=lambda v: (v["dia"], v["inicio"]), reverse=True)
            o = u["onde"]
            linhas.append({"usina_id": o.get("usina_id"), "usina": o.get("usina") or "", "uf": o.get("uf", ""),
                           "regiao_br": o.get("regiao_br", ""), "cidade": o.get("cidade", ""),
                           "equipe": o.get("equipe", ""), "cliente": o.get("cliente", ""),
                           **{k: o.get(k, "") for k in visao._PAPEIS},
                           "mobilizada": o.get("usina_id") in b.mobilizadas, **_situacao(verifs, hoje),
                           "historico": verifs[:HISTORICO], "verificacoes": len(verifs),
                           "nao": sum(1 for v in verifs if v["luvas"] is False)})
        rank = {s: i for i, s in enumerate(SITUACOES)}
        linhas.sort(key=lambda x: (rank[x["situacao"]], x["desde"] or hoje, -(x["dias"] if x["dias"] is not None
                                                                               else 10 ** 6), x["usina"]))
        return {"usinas": linhas, "hoje": hoje, "rondas_com_checklist": com_checklist,
                "respostas": sum(x["verificacoes"] for x in linhas), "times": b.times(), **visao._estrutura(b),
                "fatos": visao._avisos("ronda")}
    return visao._ler(("hseq_epi_luvas",), calcular)


def contar(lista) -> dict:
    c = {"usinas": len(lista)}
    c.update({s: sum(1 for x in lista if x["situacao"] == s) for s in SITUACOES})
    return c


def _cartao(**k) -> dict:
    return {**k, "equipes": [], "usinas": 0, **dict.fromkeys(SITUACOES, 0)}


def _fechar(s, times, com_codigo) -> dict:
    tm = [(times or {}).get(e) or {} for e in s["equipes"]]
    s["tecnicos"] = sum(t.get("tecnicos", 0) for t in tm)
    s["equipes"] = sorted(f"{t['codigo']} {e}" if com_codigo and t.get("codigo") else e
                          for e, t in zip(s["equipes"], tm))
    s["n_equipes"] = len(s["equipes"])
    s["cor"] = "critico" if s["sem_luvas"] else ("alerta" if s["sem_verificacao"] else "ok")
    return s


def _somar(s, x):
    s["usinas"] += 1
    s[x["situacao"]] += 1
    if x.get("equipe") and x["equipe"] not in s["equipes"]:
        s["equipes"].append(x["equipe"])


def por_regiao(lista, regioes=(), times=None) -> list[dict]:
    """Um cartão por região de campo (o Supervisor de Campo), como os dos extintores e da Central; "Sem região de
    campo" por último."""
    info = {r["nome"]: r for r in regioes or ()}
    g = {}
    for x in lista:
        nome = x.get("regiao_campo") or visao.SEM_REGIAO
        r = info.get(nome) or {}
        s = g.get(nome) or g.setdefault(nome, _cartao(
            regiao=nome, supervisor_campo=r.get("supervisor", ""), coordenador_campo=r.get("coordenador", ""),
            base=r.get("base", ""), ordem=r.get("ordem", 10 ** 6)))
        _somar(s, x)
    return sorted((_fechar(s, times, True) for s in g.values()),
                  key=lambda s: (s["regiao"] == visao.SEM_REGIAO, -s["sem_luvas"], -s["sem_verificacao"], s["ordem"],
                                 s["regiao"]))


def por_gestor(lista, times=None) -> list[dict]:
    g = {}
    for x in lista:
        nome = x.get("gestor") or visao.SEM_GESTOR
        _somar(g.get(nome) or g.setdefault(nome, _cartao(gestor=nome)), x)
    return sorted((_fechar(s, times, False) for s in g.values()),
                  key=lambda s: (s["gestor"] == visao.SEM_GESTOR, -s["sem_luvas"], -s["sem_verificacao"], s["gestor"]))
