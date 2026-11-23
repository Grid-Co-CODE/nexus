"""As fichas dos contratos na Visão do contrato (18/11/2026).

Levi, 17/11/2026, depois de ver o que a planilha de controle tem e não tem por cliente: "e se eu salvar os PDFs dos
contratos para você analisar e fazer algo melhor?" e "completa tudo!", "faça por subagentes para melhor confiabilidade".
Os PDFs (contrato, aditivos e anexos de cada cliente) foram lidos fora do Nexus, um leitor por cliente, num formato só:
cada regra com a categoria, o que vale hoje (e o que era antes, quando um aditivo mudou), o setor que executa, e a prova
(o arquivo, a página, a cláusula e o trecho literal). Cada trecho foi conferido por script contra o texto da página citada.

Este módulo só recebe o resultado: o administrador importa o .json na tela, o Nexus confere o formato e guarda na pasta de
dados do servidor, `contratos/fichas_contratos.json`. NUNCA no repositório (ele é público e o contrato tem valores e
cláusulas) nem no banco de leitura aberta. O que o contrato não diz chega como `lacunas`, e a tela mostra assim: sem dado
não se inventa.

Puro: nada de rede nem Flask.
"""
from __future__ import annotations

import re

from .controle import _chave

ARQUIVO = "fichas_contratos.json"
CATEGORIAS = ("SLA", "Entregáveis", "Rotinas", "Disponibilidade e desempenho", "Penalidades", "Benefícios",
              "Medição e faturamento", "Adicionais e hora extra", "Rescisão", "Seguros e documentação", "Outras obrigações")


class FichasInvalidas(ValueError):
    """O arquivo não é o das fichas dos contratos."""


def ler(dados) -> list[dict]:
    """As fichas de um .json importado: uma ficha, uma lista delas, ou {"fichas": [...]}. Confere o mínimo para a tela
    não quebrar (cliente, contratos, regras com categoria conhecida e referência) e recusa o resto."""
    if isinstance(dados, dict) and isinstance(dados.get("fichas"), list):
        dados = dados["fichas"]
    if isinstance(dados, dict):
        dados = [dados]
    if not isinstance(dados, list) or not dados:
        raise FichasInvalidas("não é o arquivo das fichas dos contratos")
    vistos = set()
    for f in dados:
        if not isinstance(f, dict) or not str(f.get("cliente") or "").strip():
            raise FichasInvalidas("há ficha sem o cliente")
        if _chave(f["cliente"]) in vistos:
            raise FichasInvalidas(f"o cliente {f['cliente']} aparece duas vezes")
        vistos.add(_chave(f["cliente"]))
        if not isinstance(f.get("contratos"), list) or not f["contratos"]:
            raise FichasInvalidas(f"a ficha de {f['cliente']} não tem contrato")
        for c in f["contratos"]:
            if not isinstance(c, dict) or not isinstance(c.get("regras"), list):
                raise FichasInvalidas(f"um contrato de {f['cliente']} não tem a lista de regras")
            for r in c["regras"]:
                if not isinstance(r, dict) or r.get("categoria") not in CATEGORIAS:
                    raise FichasInvalidas(f"regra de {f['cliente']} com categoria fora da lista: {r.get('categoria')!r}")
                if not isinstance(r.get("ref"), dict):
                    raise FichasInvalidas(f"regra de {f['cliente']} sem a referência (arquivo, página, cláusula)")
    return dados


def _origem(k: dict, campo: str, n: int, total: int) -> dict:
    return {"fonte": "contrato", "contrato": k.get("id") or k.get("arquivo"), "ref": (k.get(campo) or {}).get("ref"),
            "de": n, "total": total}


def completar(contratos: list[dict], fichas: dict[str, dict]) -> list[dict]:
    """O que a planilha de controle não tem e o contrato lido tem (18/11/2026, Levi: "bote os dados que faltam!").

    Só preenche o VAZIO: quando a planilha tem o dado, vale o dela, e a diferença aparece na tela ("A planilha de controle
    e o contrato não batem"). Cada campo preenchido leva em `origem` de qual contrato e de que página veio, e a tela marca
    "do contrato". Regras, uma a uma:
    - início e fim da vigência: o mais cedo entre os contratos do cliente que trazem a data (o 1º a vencer é o que pede
      atenção); o contrato que não traz a data não entra na conta;
    - aviso prévio e índice de reajuste: só quando todos os contratos que trazem o dado dizem o mesmo (dois valores
      diferentes não viram um: a tela mostra cada um nas regras);
    - data-base do reajuste: só a que é uma data (a "data da assinatura" escrita por extenso não é);
    - valor mensal: a soma dos contratos que trazem o valor, com quantos trazem e se há minuta (sem assinatura) entre eles.
    """
    out = []
    for c in contratos:
        f = fichas.get(c["cliente"])
        if not f:
            out.append(c)
            continue
        c, ks, origem = dict(c), f.get("contratos") or [], {}
        for campo, chave in (("inicio", "inicio"), ("fim", "fim")):
            if not c.get(campo):
                ds = sorted((str((k.get("vigencia") or {}).get(chave)), i) for i, k in enumerate(ks)
                            if re.match(r"^\d{4}-\d{2}-\d{2}$", str((k.get("vigencia") or {}).get(chave) or "")))
                if ds:
                    c[campo] = ds[0][0]
                    origem[campo] = _origem(ks[ds[0][1]], "vigencia", len(ds), len(ks))
        for campo, bloco, chave in (("aviso_dias", "renovacao", "aviso_previo_dias"), ("indice", "reajuste", "indice")):
            if c.get(campo) in (None, ""):
                tem = [(k, (k.get(bloco) or {}).get(chave)) for k in ks if (k.get(bloco) or {}).get(chave) not in (None, "")]
                if tem and len({str(v) for _, v in tem}) == 1:
                    c[campo] = int(tem[0][1]) if campo == "aviso_dias" else str(tem[0][1])
                    origem[campo] = _origem(tem[0][0], bloco, len(tem), len(ks))
        if not c.get("data_base"):
            tem = [(k, (k.get("reajuste") or {}).get("data_base")) for k in ks
                   if re.match(r"^\d{4}-\d{2}-\d{2}$", str((k.get("reajuste") or {}).get("data_base") or ""))]
            if tem and len({v for _, v in tem}) == 1:
                c["data_base"] = tem[0][1]
                origem["data_base"] = _origem(tem[0][0], "reajuste", len(tem), len(ks))
        valores = [(k.get("valor") or {}).get("mensal") for k in ks]
        nums = [float(v) for v in valores if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if nums:
            c["valor_mensal"] = round(sum(nums), 2)
            c["valor_info"] = {"com_valor": len(nums), "contratos": len(ks),
                               "minuta": any(d.get("assinado") is False for d in f.get("documentos") or [])}
        c["origem"] = origem
        out.append(c)
    return out


def por_cliente(fichas: list[dict], clientes: list[str]) -> dict[str, dict]:
    """{cliente da planilha: ficha}, casando o nome sem acento e sem caixa ("Greenyellow" é a GreenYellow da planilha).
    Ficha de cliente que a planilha não tem entra com o próprio nome."""
    nomes = {_chave(c): c for c in clientes}
    return {nomes.get(_chave(f["cliente"]), f["cliente"]): f for f in fichas}


# ── a etiqueta curta da cláusula ─────────────────────────────────────────────────────────────────────────────────────
# Levi, 19/11/2026: "eu gostaria que nessas regras tivessem tipo uma tagzinha [...] da cláusula do contrato [...] Tá
# dizendo ali, mas tem uma forma mais resumida dessa cláusula que a gente possa botar?". A referência que os leitores dos
# PDFs escreveram é "<documento>, <item>" ("Anexo II (Proposta Técnica), 4.7.2"; "Cláusula Vigésima Primeira, iii"); um
# terço dela passava de 25 caracteres. A etiqueta fica com o documento abreviado e o 1º número do item; a referência
# inteira segue na dica e na linha aberta.
_ORD_UNI = {"primeira": 1, "segunda": 2, "terceira": 3, "quarta": 4, "quinta": 5, "sexta": 6, "setima": 7, "oitava": 8,
            "nona": 9}
_ORD_DEZ = {"decima": 10, "vigesima": 20, "trigesima": 30, "quadragesima": 40, "quinquagesima": 50}
_DOCS = ((r"condic\w* especific\w*", "CE"), (r"condic\w* gera\w*", "CG"), (r"quadro resumo", "QR"),
         (r"criterio\w* tecnic\w*", "Crit. téc."), (r"termo de referencia", "TR"), (r"proposta", "Proposta"),
         (r"plano de manutencao", "Plano manut."), (r"aditivo", "Aditivo"), (r"contrato", "Contrato"))
_NUM = re.compile(r"(?<![\w.])(\d+(?:\.\d+)*(?:\s?\([a-z]{1,4}\))?)(?![\w])")
_ROMANO_MIN = re.compile(r"(?<![\w])([ivx]{1,5})(?![\w])")


def _sem_acento(t: str) -> str:
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFD", str(t)) if unicodedata.category(ch) != "Mn").lower()


def _ordinal(t: str) -> int | None:
    """"vigésima primeira" = 21; "décima" = 10; "quinta" = 5."""
    ps, n = _sem_acento(t).split(), 0
    for p in ps:
        if p in _ORD_DEZ:
            n += _ORD_DEZ[p]
        elif p in _ORD_UNI:
            n += _ORD_UNI[p]
        else:
            break
    return n or None


def clausula_curta(clausula) -> str:
    """A etiqueta da cláusula: "Anx II · 4.7.2", "Cl. 21 · iii", "Cl. 9 (c)", "CE · 3.1". Vazio quando não há referência."""
    t = " ".join(str(clausula or "").split())
    if not t:
        return ""
    s = _sem_acento(t)
    # o documento e o item: a 1ª vírgula separa ("Anexo IV – SLA, Tabela ..., item 4")
    doc, _, item = t.partition(",")
    sdoc = _sem_acento(doc)
    rotulo = ""
    m = re.search(r"\banexo\s+(?:n[ºo°.]?\s*)?([ivxlc]+|[a-z]|\d+)\b", sdoc)
    if m:
        rotulo = "Anx " + (m.group(1).upper() if not m.group(1).isdigit() else m.group(1))
    elif re.match(r"^\s*anexo\b", sdoc):
        m2 = re.search(r"\b([A-Z]{2,6})\b", doc)
        rotulo = "Anx " + m2.group(1) if m2 else "Anexo"
    elif re.match(r"^\s*clausula\b", sdoc):
        resto = re.sub(r"^\s*cl[aá]usula\s*", "", doc, flags=re.I)
        mn = _NUM.match(resto.strip())
        rotulo = "Cl. " + (mn.group(1) if mn else str(_ordinal(resto) or "")).strip()
        rotulo = rotulo.strip()
    elif _NUM.match(sdoc.strip()):
        # só o número: é a cláusula do corpo do contrato ("9 (c)", "2.12.1 (Relatório Mensal)")
        return ("Cl. " + _NUM.match(t.strip()).group(1)).replace("  ", " ")
    else:
        for padrao, abrev in _DOCS:
            if re.search(padrao, sdoc):
                rotulo = abrev
                break
        else:
            rotulo = doc.strip()[:14].rstrip(" -–(")
    # o item: o que vem primeiro entre o código ("MCEI.12", "A.8"), o número ("item 4.11", "4.7.2") e, na cláusula, o
    # romano miúdo ("iii"); o ano ("jan/2026") e o que está entre parênteses no nome do documento ("rev. 01") não contam
    num = ""
    partes = [item] if item else []
    if not rotulo.startswith(("Anx", "Cl.")):
        partes.append(re.sub(r"\([^)]*\)", " ", doc))
    for parte in partes:
        sp = _sem_acento(parte)
        achados = []
        mc = re.search(r"(?<![\w.])([A-Z]{1,6}\.\d+(?:\.\d+)*)(?![\w])", parte)
        if mc:
            achados.append((mc.start(), mc.group(1)))
        for mn in _NUM.finditer(sp):
            if not re.fullmatch(r"(19|20)\d\d", mn.group(1)):
                achados.append((mn.start(), mn.group(1)))
                break
        mr = _ROMANO_MIN.search(sp)
        if mr and rotulo.startswith("Cl."):
            achados.append((mr.start(), mr.group(1)))
        if achados:
            num = min(achados)[1]
            break
    if rotulo.startswith("Cl.") and rotulo.strip() == "Cl.":
        return ("Cl. " + num).strip() if num else t[:18]
    return f"{rotulo} · {num}" if num and num not in rotulo else rotulo
