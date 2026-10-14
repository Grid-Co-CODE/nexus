"""As entradas dos quatro relatórios e o recorte por cliente / cluster ou supervisor.

As mesmas do PCM, do mesmo repositório (o robô de lá as regrava; nada aqui vai ao Fracttal):
- `banco_dados.json` (a programação da semana) e `gestao_pcm.json` (as tarefas do ano): obrigatórios;
- `gerencial.json` (religamentos), `engenharia.json` (Confiabilidade), `operacoes.json` (cidade da usina e pessoas do
  cluster, só no Alerta) e `relatorios/feriados.json` (o que o Python do PCM exporta da planilha de feriados de 2026):
  sem eles a folha sai com a parte deles vazia, como no PCM.

O recorte é o da tela Relatórios do painel (js/relatorios.js: `rowsDe`, `tarefasG`, `eventosGer`): cliente igual; e o
"cluster / supervisor" casa com o cluster OU com o responsável. Ele recorta as linhas da programação, as tarefas da
Gestão PCM e os religamentos; o resumo de capacidade, as pendências e a qualidade da semana (Alerta), a engenharia e o
backlog do fechamento ficam da empresa toda, como lá. O backlog do diário com recorte é contado nas tarefas do recorte
(`diario.calcular`).
"""
import json
from datetime import date
from pathlib import Path

from .. import fonte

VAZIOS = {"gerencial": {"usinas": [], "eventos": []}, "engenharia": {"ativos": [], "kpi": {}},
          "operacoes": {"usinas": [], "clusters": []}}


def feriados(lista) -> list[tuple]:
    """[(tipo, uf, date, nome)] do relatorios/feriados.json ([{tipo, uf, data, nome}]); linha estranha fica de fora."""
    out = []
    for f in lista or []:
        try:
            out.append((f.get("tipo"), str(f.get("uf") or "").strip(), date.fromisoformat(str(f["data"])[:10]),
                        f.get("nome")))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return out


def montar(bd, gestao, gerencial=None, engenharia=None, operacoes=None, feriados_json=None) -> dict:
    return {"bd": bd or {}, "gestao": gestao or {}, "gerencial": gerencial or dict(VAZIOS["gerencial"]),
            "engenharia": engenharia or dict(VAZIOS["engenharia"]), "operacoes": operacoes or dict(VAZIOS["operacoes"]),
            "feriados": feriados(feriados_json), "recorte": None}


def de_pasta(pasta) -> dict:
    """As entradas lidas de uma pasta com os arquivos do repositório do PCM (a prova e os testes)."""
    p = Path(pasta)

    def ler(nome, padrao=None):
        try:
            return json.loads((p / nome).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return padrao
    return montar(ler("banco_dados.json", {}), ler("gestao_pcm.json", {}), ler("gerencial.json"), ler("engenharia.json"),
                  ler("operacoes.json"), ler("relatorios/feriados.json", []))


def carregar(config) -> tuple[dict | None, dict]:
    """(entradas, leituras) pelo `nexus/pcm/fonte.py` (cópia de 5 min, ETag). Entradas None quando falta o banco_dados
    ou a Gestão PCM: sem eles não há relatório. As leituras dizem de quando é cada arquivo e o erro de cada um."""
    lidos = {"bd": fonte.ler(config), "gestao": fonte.ler_gestao(config), "gerencial": fonte.ler_gerencial(config),
             "engenharia": fonte.ler_engenharia(config), "operacoes": fonte.ler_operacoes(config),
             "feriados": fonte.ler_feriados(config)}
    if lidos["bd"].dados is None or lidos["gestao"].dados is None:
        return None, lidos
    return montar(lidos["bd"].dados, lidos["gestao"].dados, lidos["gerencial"].dados, lidos["engenharia"].dados,
                  lidos["operacoes"].dados, lidos["feriados"].dados), lidos


def _casa(x, cliente, grupo) -> bool:
    return ((not cliente or (x.get("cliente") or "") == cliente)
            and (not grupo or (x.get("cluster") or "") == grupo or (x.get("responsavel") or "") == grupo))


def recortar(dados, cliente="", grupo="") -> dict:
    """As entradas só do cliente e/ou do cluster ou supervisor (o painel: `rowsDe`, `tarefasG`, `eventosGer`)."""
    cliente, grupo = (cliente or "").strip(), (grupo or "").strip()
    if not cliente and not grupo:
        return dados
    bd = dict(dados["bd"])
    bd["semanas"] = [dict(w, rows=[x for x in w.get("rows", []) if _casa(x, cliente, grupo)])
                     for w in dados["bd"].get("semanas", [])]
    g = dict(dados["gestao"])
    g["tarefas"] = [t for t in dados["gestao"].get("tarefas", []) if _casa(t, cliente, grupo)]
    ger = dict(dados["gerencial"])
    U = ger.get("usinas") or []
    ops = (dados.get("operacoes") or {}).get("usinas") or []

    def usina(e):
        i = e.get("u", -1)
        return U[i] if isinstance(i, int) and 0 <= i < len(U) else {}

    def evento_casa(e):
        u = usina(e)
        if cliente and (u.get("cliente") or "") != cliente:
            return False
        if grupo and (u.get("cluster") or "") != grupo and not any(
                o.get("usina") == u.get("usina") and (o.get("cluster") == grupo or o.get("responsavel") == grupo)
                for o in ops):
            return False
        return True
    ger["eventos"] = [e for e in ger.get("eventos", []) if evento_casa(e)]
    return dict(dados, bd=bd, gestao=g, gerencial=ger, recorte=(cliente, grupo))


def opcoes(bd, cliente="", grupo="") -> dict:
    """As escolhas do recorte, em cascata (regra das telas do PCM, 09/10/2026): cada lista mostra só o que existe com o
    OUTRO filtro aplicado; a escolhida fica na lista mesmo sem nada. Clientes, clusters e supervisores das linhas das
    semanas do banco, como o painel (supervisor "TBD" fica de fora)."""
    rows = [r for w in (bd or {}).get("semanas", []) for r in w.get("rows", [])]
    com_grupo = [r for r in rows if not grupo or r.get("cluster") == grupo or r.get("responsavel") == grupo]
    com_cliente = [r for r in rows if not cliente or r.get("cliente") == cliente]
    clientes = sorted({r.get("cliente") for r in com_grupo if r.get("cliente")} | ({cliente} if cliente else set()))
    clusters = sorted({r.get("cluster") for r in com_cliente if r.get("cluster")})
    supervisores = sorted({r.get("responsavel") for r in com_cliente if r.get("responsavel") and r.get("responsavel") != "TBD"})
    if grupo and grupo not in clusters and grupo not in supervisores:
        clusters = sorted(set(clusters) | {grupo})
    return {"clientes": clientes, "clusters": clusters, "supervisores": supervisores}


def semanas(bd) -> list[tuple[str, str]]:
    """[(week, rótulo)] das semanas do banco, a mais nova primeiro (a lista da tela)."""
    ws = sorted((w.get("week") for w in (bd or {}).get("semanas", []) if w.get("week")), reverse=True)
    rot = {w.get("week"): w.get("label") for w in (bd or {}).get("semanas", [])}
    return [(w, rot.get(w) or w) for w in ws]
