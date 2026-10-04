"""Casar o nome que outra base dá a uma usina com a usina do cadastro, quando a base não tem código.

Feito para o BD_Thopen (aba "Dados Gerais Usinas", 116 usinas, sem coluna de código), 04/10/2026. Pelo nome cru casavam
50; os nomes do cliente seguem outra convenção:
- romanos ("Ibaté II", "Guaratinguetá V") onde o cadastro usa número ("Ibaté 2", "Guaratinguetá 5");
- uma linha por usina onde o cadastro agrupa ("Ipixuna 1" e "Ipixuna 2" -> "Ipixuna 1 e 2"; "Guatambu" -> "Guatambu 1 a 4");
- sem o número onde o cadastro numera ("Caxambu" -> "Caxambu 1"), abreviação ("AP. do Taboado"), grafia ("Córrego do
  Sapucaia" x "Córrego de Sapucaia", "Pharma II" x "Pharmas 2").

Regras, nesta ordem de força:
1. Nome igual depois de normalizar (acento, "UFV", romano, abreviação, "1 e 2" aberto em "1" e "2"). A cidade e o estado
   do BD_Thopen têm erros (Saturnino "no Paraná", Sítio dos Nogueiras "no Mato Grosso", Junco "em Teresina"): com o nome
   igual, a localização diferente não veta, só fica escrita no "casou_por".
2. O cliente sem número, o cadastro numerado ("Caxambu" -> "Caxambu 1"): a localização veta e a potência confirma.
   "Ouro Branco I a V" da Thopen ficam em Bandeirantes/PR; a "Ouro Branco" do cadastro é em Ouro Branco/AL.
   Se o cadastro tem "X 1" e "X 2", a potência decide: bate com uma (liga nela) ou com a soma (a linha é das duas).
3. Parecido (90%+) e na mesma cidade.
4. A única usina do cliente naquela cidade, com uma palavra do nome em comum ("Senador" -> "Senador Elói I").
O que sobra com mais de um candidato NÃO casa: ligação errada é pior que ligação faltando.
"""
import re
import unicodedata
from difflib import SequenceMatcher

ROMANOS = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12}
UF = {"acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA", "ceara": "CE", "distrito federal": "DF",
      "espirito santo": "ES", "goias": "GO", "maranhao": "MA", "mato grosso": "MT", "mato grosso do sul": "MS",
      "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR", "pernambuco": "PE", "piaui": "PI",
      "rio de janeiro": "RJ", "rio grande do norte": "RN", "rio grande do sul": "RS", "rondonia": "RO", "roraima": "RR",
      "santa catarina": "SC", "sao paulo": "SP", "sergipe": "SE", "tocantins": "TO"}
_VAZIAS = {"ufv", "de", "do", "da", "dos", "das"}
_GENERICAS = {"sitio", "fazenda", "usina", "santa", "santo", "sao", "nova", "novo", "boa", "porto", "rio"}
TOLERANCIA = 0.15     # potência do cliente x potência contratual do cadastro


def _ascii(s) -> str:
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower().strip()


def palavras(s) -> list[str]:
    """Nome em palavras comparáveis: sem acento, sem "UFV" nem preposição, romano vira número, "ap." vira aparecida,
    plural simples cai ("pharmas" -> "pharma"). "100" (padrão do código) vira "1"."""
    t = _ascii(s).replace("ap.", "aparecida ")
    t = re.sub(r"\(([^)]*)\)", r" \1 ", t)
    out = []
    for w in re.findall(r"[a-z]+|\d+", t):
        if w in _VAZIAS:
            continue
        if w in ROMANOS:
            w = str(ROMANOS[w])
        elif w.isdigit():
            w = str(int(w) // 100) if len(w) == 3 and w.endswith("00") else str(int(w))
        elif len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


def variantes(nome) -> set[str]:
    """Os nomes que uma usina do cadastro responde. "Ipixuna 1 e 2" -> {"ipixuna 1", "ipixuna 2", "ipixuna"};
    "Guatambu 1 a 4" -> 1..4; "Topázio (Matão 2)" -> {"topazio matao 2", "topazio", "matao 2"}."""
    w = palavras(nome)
    base = [x for x in w if not x.isdigit() and x not in ("e", "a")]
    nums = [int(x) for x in w if x.isdigit()]
    out = {" ".join(x for x in w if x not in ("e", "a"))}
    if re.search(r"\d+\s+a\s+\d+", _ascii(nome)) and len(nums) == 2:
        nums = list(range(nums[0], nums[1] + 1))
    for n in nums:
        out.add(" ".join(base + [str(n)]))
    if base:
        out.add(" ".join(base))
    m = re.search(r"\(([^)]*)\)", str(nome or ""))
    if m:
        out |= {" ".join(palavras(m.group(1))), " ".join(palavras(re.sub(r"\(.*\)", "", str(nome))))}
    return {v for v in out if v}


def mesma_cidade(a, b) -> bool | None:
    """None = não dá para saber (um dos lados sem cidade)."""
    a, b = " ".join(palavras(a)), " ".join(palavras(b))
    if not a or not b:
        return None
    return a == b or a in b or b in a


def _base(v: str) -> str:
    return " ".join(x for x in v.split() if not x.isdigit())


def casar(item: dict, usinas: list[dict]) -> tuple[list, str] | None:
    """`item` = {"nomes": [...], "cidade", "uf", "mwp"}; `usinas` = [{"id", "nome", "cidade", "uf", "mwp"}] (já do
    cliente certo). Devolve ([ids], como) ou None."""
    uf_item = UF.get(_ascii(item.get("uf")), str(item.get("uf") or "").upper()[:2]) if item.get("uf") else None

    def diverge(u) -> bool:
        return (mesma_cidade(item.get("cidade"), u.get("cidade")) is False
                or bool(uf_item and u.get("uf") and u["uf"] != uf_item))

    nomes_item = {" ".join(palavras(n)) for n in item.get("nomes") or [] if n}
    nomes_item.discard("")
    if not nomes_item:
        return None
    exatas, so_base = [], []
    for u in usinas:
        v = variantes(u["nome"])
        numeradas = {x for x in v if any(p.isdigit() for p in x.split())}
        com_numero = numeradas or v
        # usina sem número no cadastro é a "1" das outras bases ("Brodowski" = "Thopen - Brodowski 1 - SP" no Fracttal);
        # vale só como nome-base, com a localização vetando: "Ouro Branco I" (PR) não é a "Ouro Branco" (AL)
        implicitas = set() if numeradas else {f"{x} 1" for x in v}
        if nomes_item & com_numero:
            exatas.append(u)
        elif nomes_item & (v | implicitas):
            so_base.append(u)
    # regra 1: nome igual; a localização só é anotada
    if len(exatas) > 1:
        sem_divergir = [u for u in exatas if not diverge(u)]
        if len(sem_divergir) == 1:
            exatas = sem_divergir
        else:
            return _pela_potencia(item, exatas)
    if len(exatas) == 1:
        return [exatas[0]["id"]], "nome" + (" (local diverge entre as bases)" if diverge(exatas[0]) else "")
    # regra 2: só o nome-base; a localização veta
    so_base = [u for u in so_base if not diverge(u)]
    if so_base:
        return _pela_potencia(item, so_base, aceita_sem_potencia=len(so_base) == 1)
    if not item.get("cidade"):
        return None
    na_cidade = [u for u in usinas if mesma_cidade(item["cidade"], u.get("cidade")) and not diverge(u)]
    # regra 3: parecido na mesma cidade
    parecidas = [u for u in na_cidade if max(SequenceMatcher(None, _base(a), _base(b)).ratio()
                                             for a in nomes_item for b in variantes(u["nome"])) >= 0.9]
    if len(parecidas) == 1:
        return [parecidas[0]["id"]], "nome parecido + cidade"
    # regra 4: a única do cliente na cidade, com palavra do nome em comum
    if len(na_cidade) == 1:
        u = na_cidade[0]
        comuns = {w for n in nomes_item for w in n.split() if not w.isdigit() and w not in _GENERICAS and len(w) > 3}
        if comuns & set(palavras(u["nome"])):
            r = _pela_potencia(item, [u], aceita_sem_potencia=True)
            return (r[0], "única da cidade + nome") if r else None
    return None


def _pela_potencia(item, candidatas, aceita_sem_potencia=False):
    """"Nova Londrina" e o cadastro com "Nova Londrina 1" e "2": a potência do cliente bate com uma (liga nela) ou com
    a soma (a linha do cliente é das duas). Com uma candidata só, a potência tem de confirmar quando os dois lados a
    têm: "AP. do Taboado" (0,41 MWp) não é a "Aparecida do Taboado 1 e 2" (2,58 MWp) do cadastro."""
    p = item.get("mwp")
    pots = [c.get("mwp") for c in candidatas]
    if not p or any(not x for x in pots):
        return ([candidatas[0]["id"]], "nome sem número") if aceita_sem_potencia else None
    perto = [c for c in candidatas if abs(c["mwp"] - p) <= TOLERANCIA * p]
    if len(perto) == 1:
        return [perto[0]["id"]], "nome + potência"
    if len(candidatas) > 1 and abs(sum(pots) - p) <= TOLERANCIA * p:
        return [c["id"] for c in candidatas], "nome + potência (soma)"
    return None
