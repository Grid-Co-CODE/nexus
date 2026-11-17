"""A planilha de controle de obrigações dos contratos, na Visão do contrato (16/11/2026).

Retorno da área de Contratos que o Levi trouxe (o supervisor de contratos, no 1º olhar da prévia): "Só não encontrei algum
setor que fale sobre renovação contratual e/ou ajuste contratual de 12 meses. Essas datas são importantes para a gestão de
contratos". E o Levi, com a pasta do Backoffice: "ATUALIZE AGORA COM DADOS REAIS!".

A fonte é a planilha que a própria área mantém, `Controle_Obrigacoes_Contratos_GridCo_R00.xlsx` (SharePoint, Gridco › 4.
O&M › 17. Backoffice › 2. Contratos): a aba Carteira (uma linha por cliente e recorte, com o supervisor, a vigência, a
data-base e o índice do reajuste e o aviso prévio de renovação, tirados dos contratos), a Calendario (uma linha por
obrigação, com o vencimento e o status) e a Usinas (as usinas de cada cliente, do Fracttal). O Nexus não reescreve nada
disso: lê, faz as duas contas que a área pediu (até quando avisar a renovação e quando é o próximo reajuste) e mostra.

Onde mora: a planilha é importada na tela (o administrador sobe o arquivo) e o resultado fica na pasta de dados do
servidor, `contratos/controle_obrigacoes.json`. NUNCA no repositório (ele é público e a planilha tem nomes, valores e
cláusulas) nem no banco de leitura aberta.

Puro: nada de rede nem Flask.
"""
from __future__ import annotations

import io
import re
import unicodedata
from datetime import date, datetime

ARQUIVO = "controle_obrigacoes.json"
GERAL = "contrato (nivel geral)"
ALERTA_PADRAO = 7                    # a obrigação sem "Alerta com antecedência": a régua da prévia ("vence em até 1 semana")
ABAS = ("Carteira", "Calendario", "Usinas")


class PlanilhaInvalida(ValueError):
    """A planilha não é a de controle de obrigações (falta aba ou coluna)."""


def _chave(t) -> str:
    t = "".join(c for c in unicodedata.normalize("NFKD", str(t or "")) if not unicodedata.combining(c)).lower()
    t = t.replace("(auto)", "").replace("*", "")
    return " ".join(t.split())


def _txt(v) -> str:
    return " ".join(str(v).split()) if v not in (None, "") else ""


def _data(v) -> str | None:
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    m = re.match(r"^\s*(\d{2})/(\d{2})/(\d{4})\s*$", str(v or ""))
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def _int(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _tabela(ws, colunas: dict[str, str]) -> list[dict]:
    """As linhas da aba como {campo: valor}, achando o cabeçalho pelo nome (a coluna pode mudar de lugar). `colunas` =
    {campo: o começo do nome da coluna, sem acento e sem caixa}."""
    linhas = list(ws.iter_rows(values_only=True))
    for i, cab in enumerate(linhas[:15]):
        nomes = [_chave(c) for c in cab or ()]
        idx = {}
        for campo, comeco in colunas.items():
            j = next((k for k, n in enumerate(nomes) if n.startswith(comeco)), None)
            if j is not None:
                idx[campo] = j
        if len(idx) == len(colunas):
            return [{campo: (r[j] if j < len(r) else None) for campo, j in idx.items()}
                    for r in linhas[i + 1:] if r and any(c not in (None, "") for c in r)]
    raise PlanilhaInvalida(f"a aba {ws.title} não tem as colunas esperadas ({', '.join(colunas.values())})")


def ler_planilha(conteudo: bytes, nome_arquivo: str = "") -> dict:
    """{"arquivo", "contratos": [...], "obrigacoes": [...]} da planilha (bytes do .xlsx). Recusa a planilha errada."""
    import openpyxl
    try:
        wb = openpyxl.load_workbook(io.BytesIO(conteudo), data_only=True, read_only=True)
    except Exception as ex:      # noqa: BLE001 — arquivo que não é .xlsx
        raise PlanilhaInvalida(f"não consegui abrir como .xlsx ({type(ex).__name__})") from ex
    faltam = [a for a in ABAS if a not in wb.sheetnames]
    if faltam:
        raise PlanilhaInvalida("faltam as abas " + ", ".join(faltam) + ": é a planilha de controle de obrigações?")
    carteira = _tabela(wb["Carteira"], {
        "cliente": "cliente", "supervisor": "supervisor de contratos", "recorte": "recorte",
        "referencia": "no / referencia", "inicio": "inicio da vigencia", "fim": "fim da vigencia",
        "data_base": "data-base do reajuste", "indice": "indice de reajuste", "aviso": "aviso previo de renovacao",
        "sla": "sla de atendimento", "resumo": "resumo do contrato", "pasta": "pasta do contrato",
        "observacoes": "observacoes", "alerta": "alerta"})
    calendario = _tabela(wb["Calendario"], {
        "cliente": "cliente", "recorte": "recorte", "supervisor": "supervisor", "tipo": "tipo de obrigacao",
        "descricao": "descricao", "clausula": "clausula", "periodicidade": "periodicidade", "vencimento": "vencimento",
        "alerta_dias": "alerta com antecedencia", "executor": "executor", "status": "status", "entrega": "data de entrega",
        "observacoes": "observacoes"})
    usinas = _tabela(wb["Usinas"], {"codigo": "codigo fracttal", "cliente": "cliente", "usina": "usina", "uf": "uf",
                                    "recorte": "recorte"})

    por_cliente: dict[str, list[dict]] = {}
    for r in carteira:
        if _txt(r["cliente"]):
            por_cliente.setdefault(_txt(r["cliente"]), []).append(r)
    us_cli: dict[str, list[dict]] = {}
    for u in usinas:
        if _txt(u["cliente"]) and _txt(u["usina"]):
            us_cli.setdefault(_chave(u["cliente"]), []).append(
                {"usina": _txt(u["usina"]), "codigo": _txt(u["codigo"]), "uf": _txt(u["uf"]), "recorte": _txt(u["recorte"])})

    contratos = []
    for cliente, rs in sorted(por_cliente.items(), key=lambda kv: _chave(kv[0])):
        geral = next((r for r in rs if _chave(r["recorte"]) == GERAL), None)
        base = geral or rs[0]

        def campo(k, conv=_txt):
            v = conv(base[k])
            return v if v not in (None, "") else next((conv(r[k]) for r in rs if conv(r[k]) not in (None, "")), conv(None))
        recortes = [{"recorte": _txt(r["recorte"]) or "Todas", "supervisor": _txt(r["supervisor"])}
                    for r in rs if _chave(r["recorte"]) != GERAL]
        sups = {x["supervisor"] for x in recortes if x["supervisor"]}
        gestor = _txt(geral["supervisor"]) if geral else (next(iter(sups)) if len(sups) == 1 else "")
        lista = sorted(us_cli.get(_chave(cliente), []), key=lambda u: _chave(u["usina"]))
        for x in recortes:
            x["usinas"] = sum(1 for u in lista if _chave(u["recorte"]) == _chave(x["recorte"]))
        ref = campo("referencia")
        contratos.append({
            "cliente": cliente, "gestor": gestor, "recortes": recortes if (len(recortes) > 1 or not gestor) else [],
            "referencia": ref, "nao_localizado": ref.upper().startswith("[CONTRATO NÃO LOCALIZADO") or
                                                ref.upper().startswith("[CONTRATO NAO LOCALIZADO"),
            "inicio": campo("inicio", _data), "fim": campo("fim", _data), "data_base": campo("data_base", _data),
            "indice": campo("indice"), "aviso_dias": campo("aviso", _int), "sla": campo("sla"),
            "resumo": campo("resumo"), "pasta": campo("pasta"), "observacoes": campo("observacoes"),
            "alerta_planilha": _txt(base["alerta"]), "usinas": lista})

    obrigacoes = []
    for r in calendario:
        desc, venc = _txt(r["descricao"]), _data(r["vencimento"])
        # a linha 5 da aba é o exemplo do formato ("— EXEMPLO") e não entra em conta nenhuma (o LEIA-ME da planilha)
        if not _txt(r["cliente"]) or not desc or not venc or desc.upper().endswith("EXEMPLO"):
            continue
        obrigacoes.append({"cliente": _txt(r["cliente"]), "recorte": _txt(r["recorte"]), "supervisor": _txt(r["supervisor"]),
                           "tipo": _txt(r["tipo"]), "descricao": desc, "clausula": _txt(r["clausula"]),
                           "periodicidade": _txt(r["periodicidade"]), "vencimento": venc,
                           "alerta_dias": _int(r["alerta_dias"]), "executor": _txt(r["executor"]),
                           "status": _txt(r["status"]), "entrega": _data(r["entrega"]),
                           "observacoes": _txt(r["observacoes"])})
    obrigacoes.sort(key=lambda o: (o["vencimento"], _chave(o["cliente"])))
    if not contratos:
        raise PlanilhaInvalida("a aba Carteira não tem nenhum cliente")
    return {"arquivo": nome_arquivo, "contratos": contratos, "obrigacoes": obrigacoes}


# ── as contas (com o "hoje" de quem abre) ─────────────────────────────────────────────────────────────────────────────
def _d(iso: str | None) -> date | None:
    try:
        return date.fromisoformat(iso) if iso else None
    except ValueError:
        return None


def _aniversario(base: date, ano: int) -> date:
    try:
        return base.replace(year=ano)
    except ValueError:               # 29/02 em ano que não é bissexto
        return base.replace(year=ano, day=28)


def proximo_reajuste(data_base: date | None, hoje: date) -> date | None:
    """O 1º aniversário da data-base, a partir de 12 meses dela, que ainda não passou (hoje conta)."""
    if not data_base:
        return None
    ano = data_base.year + 1
    while _aniversario(data_base, ano) < hoje:
        ano += 1
    return _aniversario(data_base, ano)


def tom_obrigacao(o: dict, hoje: date) -> str:
    """ok entregue; critico vencida e não entregue; alerta dentro do alerta da própria linha (sem ele, 1 semana); neutro."""
    if _chave(o.get("status")) == "entregue":
        return "ok"
    v = _d(o.get("vencimento"))
    if v is None:
        return "neutro"
    dias = (v - hoje).days
    if dias < 0:
        return "critico"
    return "alerta" if dias <= (o.get("alerta_dias") if o.get("alerta_dias") is not None else ALERTA_PADRAO) else "neutro"


def com_datas(dados: dict, hoje: date) -> dict:
    """Os contratos e as obrigações com as contas de hoje: dias até o fim da vigência, a data limite do aviso de renovação
    (fim menos o aviso prévio), o próximo reajuste, as obrigações em atraso; e o tom de cada obrigação."""
    obr = []
    for o in dados.get("obrigacoes") or []:
        v = _d(o.get("vencimento"))
        obr.append({**o, "tom": tom_obrigacao(o, hoje), "dias": (v - hoje).days if v else None})
    contratos = []
    for c in dados.get("contratos") or []:
        fim, base = _d(c.get("fim")), _d(c.get("data_base"))
        avisar = None
        if fim and c.get("aviso_dias") is not None:
            from datetime import timedelta
            avisar = fim - timedelta(days=int(c["aviso_dias"]))
        reaj = proximo_reajuste(base, hoje)
        atrasadas = [o for o in obr if o["cliente"] == c["cliente"] and o["tom"] == "critico"]
        criticos = []
        if fim and fim < hoje:
            criticos.append(f"vigência vencida há {(hoje - fim).days} dias")
        elif avisar and avisar < hoje:
            criticos.append(f"o prazo do aviso de renovação passou há {(hoje - avisar).days} dias")
        if atrasadas:
            criticos.append(f"{len(atrasadas)} obrigaç{'ão' if len(atrasadas) == 1 else 'ões'} em atraso")
        datas = [d for d in (avisar if avisar and avisar >= hoje else None, fim if fim and fim >= hoje else None, reaj) if d]
        contratos.append({**c, "dias_fim": (fim - hoje).days if fim else None,
                          "avisar_ate": avisar.isoformat() if avisar else None,
                          "dias_aviso": (avisar - hoje).days if avisar else None,
                          "proximo_reajuste": reaj.isoformat() if reaj else None,
                          "dias_reajuste": (reaj - hoje).days if reaj else None,
                          "atrasadas": len(atrasadas), "criticos": criticos,
                          "proxima_data": min(datas).isoformat() if datas else None})
    return {**dados, "contratos": contratos, "obrigacoes": obr, "hoje": hoje.isoformat()}
