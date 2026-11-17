"""A planilha de controle de obrigações dos contratos, na Visão do contrato (16/11/2026).

Retorno da área de Contratos que o Levi trouxe (o supervisor de contratos, no 1º olhar da prévia): "Só não encontrei algum
setor que fale sobre renovação contratual e/ou ajuste contratual de 12 meses. Essas datas são importantes para a gestão de
contratos". E o Levi, com a pasta do Backoffice: "ATUALIZE AGORA COM DADOS REAIS!".

A fonte é a planilha que a própria área mantém, `Controle_Obrigacoes_Contratos_GridCo_R00.xlsx` (SharePoint, Gridco › 4.
O&M › 17. Backoffice › 2. Contratos): a aba Carteira (uma linha por cliente e recorte, com o supervisor, a vigência, a
data-base e o índice do reajuste e o aviso prévio de renovação, tirados dos contratos), a Calendario (uma linha por
obrigação, com o vencimento e o status) e a Usinas (as usinas de cada cliente, do Fracttal). O Nexus não reescreve nada
disso: lê, faz as duas contas que a área pediu (até quando avisar a renovação e quando é o próximo reajuste) e mostra.

Desde 17/11/2026 (Levi, ao ver Entregáveis, Metas e Financeiro vazios: "na fonte que eu mandei não tem nada de
atendimento, entregáveis, metas e financeiro???????????"): a planilha tem oito abas e só três eram lidas. Agora também:
- a **Adicionais** (E-CTR-04, a memória de cobrança: o serviço feito fora do valor fixo, o valor, a resposta do cliente,
  o BM e a NF), que vira o Financeiro do contrato;
- a **Cadastros** (as metas da Estrutura R02, a antecedência padrão do alerta e o prazo da memória), que dá as metas;
- no Calendario, a linha **sem vencimento** (era descartada; a planilha a põe na pauta como "SEM DATA") e as colunas que
  a planilha calcula por fórmula (o semáforo, o "conta no KPI de entregáveis" e o "entregue no prazo").
As fórmulas da planilha usam o HOJE() de quem abre; por isso o Nexus refaz as mesmas regras com o hoje dele, em vez de
guardar o valor que o Excel calculou no dia em que salvou (`com_datas`). As regras estão copiadas das fórmulas, célula a
célula, e citadas em cada função. A Pauta_Semanal e a Indicadores_Mes são somas dessas colunas por supervisor: o Nexus
soma as mesmas colunas por contrato, e não as lê.

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
# as abas que entraram em 17/11/2026; a planilha sem elas (a de teste antiga, uma revisão anterior) ainda importa
OPCIONAIS = ("Adicionais", "Cadastros")
CANCELADO = "cancelado / nao se aplica"
PRAZO_MEMORIA = 10                   # Cadastros: "Prazo da memória de cobrança (dias após execução)"


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


def _tabela(ws, colunas: dict[str, str], opcionais: dict[str, str] | None = None) -> list[dict]:
    """As linhas da aba como {campo: valor}, achando o cabeçalho pelo nome (a coluna pode mudar de lugar). `colunas` =
    {campo: o começo do nome da coluna, sem acento e sem caixa}; `opcionais`, as que podem faltar (viram None)."""
    linhas = list(ws.iter_rows(values_only=True))
    opcionais = opcionais or {}
    for i, cab in enumerate(linhas[:15]):
        nomes = [_chave(c) for c in cab or ()]
        idx = {}
        for campo, comeco in {**colunas, **opcionais}.items():
            j = next((k for k, n in enumerate(nomes) if n.startswith(comeco)), None)
            if j is not None:
                idx[campo] = j
        if all(c in idx for c in colunas):
            return [{campo: (r[idx[campo]] if campo in idx and idx[campo] < len(r) else None)
                     for campo in {**colunas, **opcionais}}
                    for r in linhas[i + 1:] if r and any(c not in (None, "") for c in r)]
    raise PlanilhaInvalida(f"a aba {ws.title} não tem as colunas esperadas ({', '.join(colunas.values())})")


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _parametros(ws) -> dict:
    """A aba Cadastros: as metas da Estrutura R02 e os dois prazos que as fórmulas usam (B9 e B10). Rótulo na coluna A,
    valor na B; o que faltar fica None (sem meta não se inventa meta)."""
    rotulos = {"meta · entregaveis": "meta_entregaveis", "meta · obrigacoes vencidas": "meta_vencidas",
               "meta · adicionais": "meta_adicionais", "meta · cobertura": "meta_cobertura",
               "antecedencia padrao": "alerta_padrao", "prazo da memoria": "prazo_memoria"}
    out = dict.fromkeys(rotulos.values())
    for r in ws.iter_rows(max_col=2, values_only=True):
        k = _chave(r[0] if r else "")
        for comeco, campo in rotulos.items():
            if k.startswith(comeco) and _num(r[1] if len(r) > 1 else None) is not None:
                out[campo] = _num(r[1])
    return out


def ler_planilha(conteudo: bytes, nome_arquivo: str = "") -> dict:
    """{"arquivo", "contratos", "obrigacoes", "adicionais", "parametros", "abas"} da planilha (bytes do .xlsx). Recusa a
    planilha errada."""
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
        "observacoes": "observacoes"}, {"evidencia": "evidencia"})
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
        # a linha 5 da aba é o exemplo do formato ("— EXEMPLO") e não entra em conta nenhuma (o LEIA-ME da planilha). A
        # linha sem vencimento ENTRA (até 17/11/2026 era descartada): a planilha a leva à pauta como "SEM DATA"
        if not _txt(r["cliente"]) or not desc or desc.upper().endswith("EXEMPLO"):
            continue
        obrigacoes.append({"cliente": _txt(r["cliente"]), "recorte": _txt(r["recorte"]), "supervisor": _txt(r["supervisor"]),
                           "tipo": _txt(r["tipo"]), "descricao": desc, "clausula": _txt(r["clausula"]),
                           "periodicidade": _txt(r["periodicidade"]), "vencimento": venc,
                           "alerta_dias": _int(r["alerta_dias"]), "executor": _txt(r["executor"]),
                           "status": _txt(r["status"]), "entrega": _data(r["entrega"]),
                           "observacoes": _txt(r["observacoes"]), "evidencia": _txt(r["evidencia"])})
    obrigacoes.sort(key=lambda o: (o["vencimento"] or "9999", _chave(o["cliente"])))
    if not contratos:
        raise PlanilhaInvalida("a aba Carteira não tem nenhum cliente")

    # a memória de cobrança (E-CTR-04): uma linha por serviço feito fora do valor fixo
    adicionais = []
    if "Adicionais" in wb.sheetnames:
        for r in _tabela(wb["Adicionais"], {
                "cliente": "cliente", "recorte": "recorte", "supervisor": "supervisor", "usina": "usina",
                "servico": "servico executado", "execucao": "data de execucao", "valor_estimado": "valor estimado",
                "memoria": "memoria enviada", "resposta": "resposta do cliente", "valor_aprovado": "valor aprovado",
                "bm": "bm / competencia", "faturamento": "data do faturamento"},
                {"os": "no os fracttal", "pedido": "pedido / aviso", "base": "base contratual", "nf": "no da nf",
                 "observacoes": "observacoes"}):
            serv = _txt(r["servico"])
            if not _txt(r["cliente"]) or not serv or serv.upper().endswith("EXEMPLO"):
                continue
            adicionais.append({"cliente": _txt(r["cliente"]), "recorte": _txt(r["recorte"]),
                               "supervisor": _txt(r["supervisor"]), "usina": _txt(r["usina"]), "servico": serv,
                               "os": _txt(r["os"]), "execucao": _data(r["execucao"]), "pedido": _txt(r["pedido"]),
                               "base": _txt(r["base"]), "valor_estimado": _num(r["valor_estimado"]),
                               "memoria": _data(r["memoria"]), "resposta": _txt(r["resposta"]),
                               "valor_aprovado": _num(r["valor_aprovado"]), "bm": _txt(r["bm"]), "nf": _txt(r["nf"]),
                               "faturamento": _data(r["faturamento"]), "observacoes": _txt(r["observacoes"])})
        adicionais.sort(key=lambda a: (a["execucao"] or "0000", _chave(a["cliente"])), reverse=True)
    parametros = _parametros(wb["Cadastros"]) if "Cadastros" in wb.sheetnames else {}
    return {"arquivo": nome_arquivo, "contratos": contratos, "obrigacoes": obrigacoes, "adicionais": adicionais,
            "parametros": parametros, "abas": [a for a in ABAS + OPCIONAIS if a in wb.sheetnames]}


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


def tom_obrigacao(o: dict, hoje: date, alerta_padrao: int = ALERTA_PADRAO) -> str:
    """O semáforo da planilha (Calendario, coluna Semáforo): ok entregue; cancelado ("—"); sem_data (SEM DATA); critico
    (VERMELHO, vencida e não entregue); alerta (ÂMBAR, dentro do alerta da linha; sem ele, o padrão da Cadastros, 7
    dias); neutro (VERDE)."""
    st = _chave(o.get("status"))
    if st == CANCELADO:
        return "cancelado"
    if st == "entregue":
        return "ok"
    v = _d(o.get("vencimento"))
    if v is None:
        return "sem_data"
    dias = (v - hoje).days
    if dias < 0:
        return "critico"
    return "alerta" if dias <= (o.get("alerta_dias") if o.get("alerta_dias") is not None else alerta_padrao) else "neutro"


def conta_entregavel(o: dict) -> bool:
    """Calendario, "Conta no KPI de entregáveis": =SE(E(OU(ESQUERDA(E;10)="Entregável";ESQUERDA(E;7)="Medição");
    L<>"Cancelado / não se aplica");1;0)."""
    tipo = str(o.get("tipo") or "")
    return (tipo[:10] == "Entregável" or tipo[:7] == "Medição") and _chave(o.get("status")) != CANCELADO


def entregue_no_prazo(o: dict) -> bool | None:
    """Calendario, "Entregue no prazo": só para a entregue; no prazo se a data de entrega é até o vencimento."""
    if _chave(o.get("status")) != "entregue":
        return None
    e, v = _d(o.get("entrega")), _d(o.get("vencimento"))
    return bool(e and v and e <= v)


def situacao_adicional(a: dict, hoje: date, prazo_memoria: int = PRAZO_MEMORIA) -> str:
    """Adicionais, "Situação": Faturado (tem data de faturamento); Reprovado; sem memória enviada, "Memória atrasada" se
    passou o prazo (a execução + 10 dias, Cadastros) ou "Memória a enviar"; aprovado (ou aprovado parcial), "Aprovado —
    faturar"; senão "Aguardando cliente"."""
    from datetime import timedelta
    if a.get("faturamento"):
        return "Faturado"
    resp = _chave(a.get("resposta"))
    if resp == "reprovado":
        return "Reprovado"
    if not a.get("memoria"):
        ex = _d(a.get("execucao"))
        return "Memória atrasada" if ex and hoje > ex + timedelta(days=prazo_memoria) else "Memória a enviar"
    if resp in ("aprovado", "aprovado parcial"):
        return "Aprovado — faturar"
    return "Aguardando cliente"


def valor_adicional(a: dict) -> float:
    """Adicionais, "Valor p/ KPI": o aprovado; sem ele, o estimado; sem nenhum, 0."""
    for k in ("valor_aprovado", "valor_estimado"):
        if isinstance(a.get(k), (int, float)):
            return float(a[k])
    return 0.0


def com_datas(dados: dict, hoje: date) -> dict:
    """Os contratos e as obrigações com as contas de hoje: dias até o fim da vigência, a data limite do aviso de renovação
    (fim menos o aviso prévio), o próximo reajuste, as obrigações em atraso; e o tom de cada obrigação."""
    par = dados.get("parametros") or {}
    alerta = int(par["alerta_padrao"]) if par.get("alerta_padrao") is not None else ALERTA_PADRAO
    prazo = int(par["prazo_memoria"]) if par.get("prazo_memoria") is not None else PRAZO_MEMORIA
    obr = []
    for o in dados.get("obrigacoes") or []:
        v = _d(o.get("vencimento"))
        obr.append({**o, "tom": tom_obrigacao(o, hoje, alerta), "dias": (v - hoje).days if v else None,
                    "entregavel": conta_entregavel(o), "no_prazo": entregue_no_prazo(o),
                    "mes": o["vencimento"][:7] if o.get("vencimento") else None})
    adic = []
    for a in dados.get("adicionais") or []:
        sit = situacao_adicional(a, hoje, prazo)
        adic.append({**a, "situacao": sit, "faturado": bool(a.get("faturamento")), "valor": valor_adicional(a),
                     "mes": a["execucao"][:7] if a.get("execucao") else None})
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
    return {**dados, "contratos": contratos, "obrigacoes": obr, "adicionais": adic, "hoje": hoje.isoformat(),
            # a importação antiga (antes de 17/11/2026) não tem as abas novas: a página pede para importar de novo
            "abas": dados.get("abas") or list(ABAS)}
