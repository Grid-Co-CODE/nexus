"""As observações da semana como regras, para a tela (01/10/2026, Levi: "uma forma mais moderna [...] que não ocupe
tanta tela").

O motor (programacao_v7.py, linhas 452-580) continua lendo o MESMO texto de sempre: uma regra por linha. Este módulo
só lê esse texto para a tela mostrar e editar, e escreve de volta na gramática do motor:

    @usina Nome = seg, qua        dias de atendimento da usina
    13480; não                    a OS fica fora da semana
    10369; qua; tarefas; manhã    a OS vai no dia (e, se quiser, só nas tarefas e no turno), com "só:" e "sem:"
    # texto                       comentário

Linha que a tela não mexeu volta IDÊNTICA (o texto original fica guardado em `bruta`): a ordem e a escrita de quem
digitou não mudam por causa da tela. Os problemas usam as mesmas mensagens do motor, para a pessoa ver ANTES de gerar
o que hoje só aparece no log.
"""
import re
import unicodedata

DIAS = ("seg", "ter", "qua", "qui", "sex")
NOMES_DIA = {"seg": "Segunda", "ter": "Terça", "qua": "Quarta", "qui": "Quinta", "sex": "Sexta"}
_DIA = {"SEG": "seg", "SEGUNDA": "seg", "TER": "ter", "TERCA": "ter", "QUA": "qua", "QUARTA": "qua",
        "QUI": "qui", "QUINTA": "qui", "SEX": "sex", "SEXTA": "sex"}
TURNOS = ("manhã", "tarde", "noite")


def _sem_acento(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()


def dia(s: str) -> str | None:
    return _DIA.get(_sem_acento(s).strip().upper())


def _ordenar(dias) -> list[str]:
    tem = set(dias)          # uma vez só: com gerador, o set refeito a cada dia esvaziava depois do primeiro
    return [d for d in DIAS if d in tem]


def ler_linha(bruta: str) -> dict:
    """Uma linha do arquivo como regra. Espelha as decisões do motor sobre a mesma linha."""
    s = (bruta or "").strip()
    base = {"bruta": bruta, "problema": None}
    if not s:
        return dict(base, tipo="vazia")
    if s.startswith("#"):
        return dict(base, tipo="comentario", texto=s[1:].strip())
    if s.lower().startswith("@usina"):
        corpo = s[6:]
        if "=" not in corpo:
            return dict(base, tipo="usina", usina=corpo.strip(), dias=[],
                        problema="regra de usina sem '=' — use: @usina Nome = seg, qua")
        nome, _, dias_s = corpo.partition("=")
        toks = [t for t in re.split(r"[,\s]+", dias_s.strip()) if t]
        dias = _ordenar(d for d in (dia(t) for t in toks) if d)
        ruins = [t for t in toks if not dia(t)]
        r = dict(base, tipo="usina", usina=nome.strip(), dias=dias)
        if not nome.strip():
            r["problema"] = "nome da usina vazio"
        elif not dias:
            r["problema"] = f"nenhum dia reconhecido em '{dias_s.strip()}' — use seg/ter/qua/qui/sex"
        elif ruins:
            r["problema"] = f"ignorado: {', '.join(ruins)}"
        return r
    partes = [p.strip() for p in s.split(";")]
    if not partes[0].isdigit():
        if ";" in s or re.match(r"^\s*os\s*[\s#nº:.-]*\d", s, re.I):
            return dict(base, tipo="nota", texto=s, problema="comece pelo número da OS, sem prefixo (ex.: 10369; qua)")
        return dict(base, tipo="nota", texto=s)
    os_id = int(partes[0])
    campos = partes[1:]
    sem = [c for c in campos if re.match(r"^\s*sem\s*:", c, re.I)]
    so = [c for c in campos if re.match(r"^\s*(s[óo]|apenas)\s*:", c, re.I)]
    campos = [c for c in campos if c not in sem and c not in so]

    def _lista(c):
        return [k.strip() for k in re.split(r"[;,]", re.sub(r"^\s*\w+\s*:", "", c[0])) if k.strip()] if c else []

    dia_s = campos[0] if campos else ""
    if _sem_acento(dia_s).strip().upper() in ("NAO", "NO"):
        return dict(base, tipo="fora", os=os_id)
    toks = [t for t in re.split(r"[,;/\s]+", dia_s.strip()) if t]
    dias = _ordenar(d for d in (dia(t) for t in toks) if d)
    ruins = [t for t in toks if not dia(t) and _sem_acento(t).upper() != "E"]
    turno = (campos[2] if len(campos) > 2 else "").strip()
    r = dict(base, tipo="fixar", os=os_id, dias=dias,
             tarefas=[t.strip() for t in (campos[1] if len(campos) > 1 else "").split(",") if t.strip()],
             turno=turno, so=_lista(so), sem=_lista(sem))
    if toks and not dias:
        r["problema"] = f"dia não reconhecido ({', '.join(toks)}) — use seg/ter/qua/qui/sex"
    elif ruins:
        r["problema"] = f"trecho ignorado no campo dia: {', '.join(ruins)}"
    elif turno and _sem_acento(turno).upper() not in ("MANHA", "TARDE", "NOITE"):
        r["problema"] = f"turno não reconhecido ('{turno}') — use manhã/tarde/noite"
    return r


def ler(texto: str) -> list[dict]:
    return [ler_linha(l) for l in (texto or "").splitlines()]


def escrever_regra(r: dict) -> str:
    """A regra na gramática do motor. Só é usada para regra nova ou mexida na tela."""
    t = r.get("tipo")
    if t == "usina":
        return f"@usina {r['usina'].strip()} = {', '.join(_ordenar(r.get('dias') or []))}"
    if t == "fora":
        return f"{int(r['os'])}; não"
    if t == "fixar":
        campos = [str(int(r["os"])), ", ".join(_ordenar(r.get("dias") or [])), ", ".join(r.get("tarefas") or []),
                  r.get("turno") or ""]
        while len(campos) > 1 and not campos[-1]:
            campos.pop()
        if r.get("so"):
            campos.append("só: " + ", ".join(r["so"]))
        if r.get("sem"):
            campos.append("sem: " + ", ".join(r["sem"]))
        return "; ".join(campos)
    if t == "comentario":
        return "# " + (r.get("texto") or "")
    return r.get("texto") or r.get("bruta") or ""


def resumo(regras: list[dict]) -> dict:
    usinas = [r for r in regras if r["tipo"] == "usina"]
    return {"usinas": len(usinas),
            # quantas usinas atendem em cada dia: o resumo de uma linha do bloco recolhido
            "por_dia": {d: sum(1 for r in usinas if d in r.get("dias", [])) for d in DIAS},
            "fora": sum(1 for r in regras if r["tipo"] == "fora"),
            "fixar": sum(1 for r in regras if r["tipo"] == "fixar"),
            "notas": sum(1 for r in regras if r["tipo"] in ("nota", "comentario")),
            "problemas": sum(1 for r in regras if r.get("problema"))}


# ── as usinas do Fracttal e qual regra vale para cada uma (01/10/2026) ───────────────────────────────────────────
# O motor compara a regra com a "Classificação 1" do ativo no Fracttal ("Athon - Marabá 1 - PA"), por PEDAÇO do
# nome com fronteira de palavra ("Marabá 1" casa com "Athon - Marabá 1 - PA" e não com "Marabá 10"). Usina sem
# regra é atendida em qualquer dia. As funções abaixo repetem essa regra (programacao_v7.py, linhas 377-386 e 1904-1912).

def norm_usina(s) -> str:
    return re.sub(r"\s+", " ", _sem_acento(s).lower()).strip()


def casa(usina_fracttal: str, regra_norm: str) -> bool:
    return re.search(r"\b" + re.escape(regra_norm) + r"\b", norm_usina(usina_fracttal)) is not None


def separar_nome(fracttal: str) -> dict | None:
    """'Athon -  Timon 1 - MA' -> cliente Athon, nome Timon 1, UF MA. O que não tem esse formato não é usina (os
    níveis de criticidade '1.Essencial', o nome solto de um cliente, 'Usina Teste')."""
    # hífen com espaço de pelo menos um lado: o Fracttal tem "Thopen - Araçoiaba da Serra 1- SP" (sem espaço antes)
    partes = [p.strip() for p in re.split(r"\s+-\s*|\s*-\s+", fracttal.strip())]
    if len(partes) < 3 or not re.fullmatch(r"[A-Z]{2}", partes[-1]) or not partes[0]:
        return None
    nome = " - ".join(partes[1:-1])
    if not nome or "usina teste" in norm_usina(fracttal):
        return None
    return {"fracttal": fracttal.strip(), "cliente": partes[0], "nome": nome, "uf": partes[-1]}


def usinas_por_dia(regras: list[dict], usinas_fracttal: list[str]) -> list[dict]:
    """Cada usina do Fracttal com os dias em que o motor a atenderia e a regra que decide.

    Como o motor: só entra regra sem problema; nome repetido fica na posição da primeira vez com os dias da última;
    a primeira regra (nessa ordem) que casa com a usina vence."""
    valendo = {}                                         # nome normalizado -> índice da regra que dá os dias
    for i, r in enumerate(regras):
        if r["tipo"] == "usina" and r.get("usina") and r.get("dias"):    # o motor descarta nome vazio e regra sem dia
            valendo[norm_usina(r["usina"])] = i
    saida = []
    for f in usinas_fracttal:
        info = separar_nome(f)
        if not info:
            continue
        regra = next((i for chave, i in valendo.items() if casa(f, chave)), None)
        info["regra"] = regra
        info["dias"] = list(regras[regra]["dias"]) if regra is not None else list(DIAS)
        saida.append(info)
    saida.sort(key=lambda u: (_sem_acento(u["cliente"]).lower(), _sem_acento(u["nome"]).lower()))
    # o nome curto vira a regra quando ele só casa com esta usina; senão, o nome inteiro do Fracttal
    for u in saida:
        curto = norm_usina(u["nome"])
        outras = [x for x in saida if x is not u and casa(x["fracttal"], curto)]
        u["nome_regra"] = u["nome"] if not outras else u["fracttal"]
        u["divide"] = [x["nome"] for x in saida if x is not u and u["regra"] is not None and x["regra"] == u["regra"]]
    return saida


CACHE_ATIVOS = "_ativos_classificacao_cache.json"


def ler_usinas_fracttal(pastas) -> tuple[list[str], float | None]:
    """A lista de usinas do Fracttal (a Classificação 1 dos ativos) do cache que o próprio motor grava ao ler o
    Fracttal: custo zero de API. Usa o cache mais novo entre as pastas dadas (a do PCM e as rodadas do Nexus)."""
    import json
    from pathlib import Path
    achados = [p for p in (Path(x) / CACHE_ATIVOS for x in pastas if x) if p.exists()]
    if not achados:
        return [], None
    p = max(achados, key=lambda x: x.stat().st_mtime)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], None
    nomes = sorted({(v[0] or "").strip() for v in raw.values() if v and (v[0] or "").strip()})
    return nomes, p.stat().st_mtime


def regras_sem_usina(regras: list[dict], usinas: list[dict]) -> list[int]:
    """Regras de usina que não casam com nenhuma usina do Fracttal: ficam à vista para ninguém perder."""
    usadas = {u["regra"] for u in usinas if u["regra"] is not None}
    return [i for i, r in enumerate(regras) if r["tipo"] == "usina" and i not in usadas]


def semana_anterior(semana: str) -> str:
    """'2026-W41' -> '2026-W40', atravessando a virada do ano pelo calendário ISO."""
    from datetime import date, timedelta
    ano, num = semana.split("-W")
    seg = date.fromisocalendar(int(ano), int(num), 1) - timedelta(days=7)
    iso = seg.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"
