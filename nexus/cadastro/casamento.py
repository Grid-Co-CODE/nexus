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
from functools import lru_cache

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


# ── a contenção de palavras: as sugestões da tela Ligações (12/11/2026) ────────────────────────────────────────────
# Levi, 12/11/2026: "tem muita coisa que dá para vir sugerido do Nexus e não está vindo". O caso real, aqui com nomes
# inventados: a chave "Cliente - Pinhal 1 - UF" do Fracttal (e o projeto "Pinhal I" da FAMA) é a "São Brás do Pinhal 1"
# do cadastro, e a parecença de letras (o corte de 0,78 da `ligacoes.sugestoes`) não chegava lá. Aqui só se SUGERE: o
# `casar` acima, o casamento automático, não usa nada disto (ligação errada é pior que faltando).
# As palavras que não fazem uma usina ser outra (a lista curta; as preposições já saem nas `palavras`). O "e" e o "a"
# NÃO estão aqui: só caem entre dois números ("1 e 2", "1 a 4"); fora disso, a letra solta é a usina (revisão de
# 12/11/2026: o "a" desta lista apagava a letra, e "Pinhal A" sugeria a "Pinhal B" a 100%)
GENERICAS_SUGESTAO = frozenset({"usina", "ufv", "solar", "cliente", "de", "do", "da", "dos", "das"})
# MESMO: a chave cabe no nome do cadastro (o caso do pedido, "Pinhal 1" e "São Brás do Pinhal 1"); MESMO_A_MAIS: o nome do
# cadastro cabe na chave, que tem palavras A MAIS ("Nova Quimera 1" contra a "Quimera 1"): a palavra a mais pode ser a que
# separa duas usinas, então fica fora do lote (o ruling da revisão de 12/11/2026: ligação errada é pior que nenhuma)
MESMO, MESMO_A_MAIS, OUTRO_NUMERO = "mesmo", "mesmo, a chave com palavras a mais", "outro número"
CONTIDAS = (MESMO, MESMO_A_MAIS)
# a nota da usina achada pela contenção (as duas fontes de sugestão: `ligacoes.sugestoes` e `ligacao_fama.sugestoes`)
NOTA_CONTIDA_UNICA = 100        # a ÚNICA usina do cliente que contém as palavras da chave, com o mesmo identificador
NOTA_CONTIDA_A_MAIS = 95        # a única, mas a chave tem palavras a mais: no alto, a um clique, fora do lote
NOTA_CONTIDA_SEM_CLIENTE = 90   # a única, mas a chave não diz o cliente: a trava do cliente não se confere
NOTA_CONTIDA_VARIAS = 80        # duas ou mais: nenhuma com certeza
TETO_COM_DUVIDA = 95            # com duas ou mais contidas, a UF diferente ou a usina já ligada: o lote não liga
_ROMANO = re.compile(r"x{0,3}(ix|iv|v?i{0,3})")
_VALOR_ROMANO = {"i": 1, "v": 5, "x": 10}


def _romano(w: str) -> int | None:
    """O romano que as `palavras` não convertem (passa do XII: "xiii" a "xxxix"), ou None."""
    if len(w) < 2 or not _ROMANO.fullmatch(w):
        return None
    total = 0
    for a, b in zip(w, w[1:] + " "):
        v = _VALOR_ROMANO[a]
        total += -v if _VALOR_ROMANO.get(b, 0) > v else v
    return total


def _fichas(texto) -> tuple[list[str], list[tuple[int, int]]]:
    """As `palavras` prontas para a contenção, e as faixas "N a M". O apóstrofo some antes ("D'Água" é "dagua", e não a
    letra "d"), e a letra abreviada também ("S. José": a letra com ponto não é a letra da usina); o "e" e o "a" entre dois
    números caem (a faixa é guardada); o romano acima do XII vira número."""
    t = re.sub(r"['’`´]", "", str(texto or ""))
    ws = palavras(re.sub(r"\b[^\W\d_]\.", " ", t))
    out, faixas = [], []
    for i, w in enumerate(ws):
        if w in ("e", "a") and 0 < i < len(ws) - 1 and ws[i - 1].isdigit() and ws[i + 1].isdigit():
            if w == "a":
                faixas.append((int(ws[i - 1]), int(ws[i + 1])))
            continue
        r = _romano(w)
        out.append(str(r) if r is not None else w)
    return out, faixas


def _identificador(w: str) -> bool:
    """O que separa uma usina da irmã: o número e a letra solta ("Pinhal A" não é a "Pinhal B")."""
    return w.isdigit() or len(w) == 1


def termos(texto) -> tuple[frozenset, frozenset]:
    """(palavras, identificadores) que contam na contenção: as `palavras` (sem acento e sem caixa, o romano em arábico) sem
    as genéricas, e os números e as letras soltas à parte. "UFV Pinhal II" -> ({"pinhal"}, {"2"})."""
    ws = [w for w in _fichas(texto)[0] if w not in GENERICAS_SUGESTAO]
    return frozenset(w for w in ws if not _identificador(w)), frozenset(w for w in ws if _identificador(w))


def primeiro_identificador(texto) -> str | None:
    """O 1º número ou letra solta da chave, na ordem escrita (a trava do número: "Quimera 2 1" é a 2)."""
    return next((w for w in _fichas(texto)[0] if _identificador(w) and w not in GENERICAS_SUGESTAO), None)


def _contidas(a: frozenset, b: frozenset) -> bool:
    """Todas as palavras de um lado estão no outro, e o lado menor tem uma palavra forte: "Nova", "Santa" ou "Rio"
    sozinha (as `_GENERICAS` da regra 4) está em meio cadastro e não diz usina nenhuma, e a sigla de duas letras ("GD")
    também não."""
    if not a or not b or not (a <= b or b <= a):
        return False
    menor = a if len(a) <= len(b) else b
    return any(len(w) > 2 and w not in _GENERICAS for w in menor)


@lru_cache(maxsize=8192)
def _termos_da_usina(nome: str) -> tuple:
    """As formas que o nome do cadastro responde, (palavras, identificadores) cada uma: o nome inteiro, e cada número do
    "1 e 2" e da faixa "1 a 4" sozinho (com as letras do nome); o de dentro e o de fora do parêntese ("Topázio (Matão
    2)"). A usina com identificador não responde pelo nome sem ele. Guardado por nome: a seção das Ligações compara cada
    buraco com o cadastro inteiro a cada visita."""
    nome = str(nome or "")
    pedacos = [nome]
    m = re.search(r"\(([^)]*)\)", nome)
    if m:
        pedacos += [m.group(1), re.sub(r"\(.*\)", " ", nome)]
    formas = set()
    for pedaco in pedacos:
        fichas, faixas = _fichas(pedaco)
        ws = frozenset(w for w in fichas if w not in GENERICAS_SUGESTAO and not _identificador(w))
        ids = [w for w in fichas if w not in GENERICAS_SUGESTAO and _identificador(w)]
        letras = frozenset(w for w in ids if not w.isdigit())
        nums = {w for w in ids if w.isdigit()} | {str(n) for a, b in faixas for n in range(a, b + 1)}
        formas.add((ws, frozenset(ids)))
        if len(nums) > 1:
            formas |= {(ws, letras | {n}) for n in nums}
    com_id = {f for f in formas if f[1]}
    return tuple(sorted(com_id or formas, key=lambda f: (sorted(f[0]), sorted(f[1]))))


def identificadores_da_usina(nome) -> frozenset:
    """Todos os números e letras que o nome do cadastro responde (a trava do número das sugestões)."""
    return frozenset(i for _, ids in _termos_da_usina(str(nome or "")) for i in ids)


def contencao(termos_da_chave, nome_da_usina) -> str | None:
    """`MESMO`: todas as palavras significativas da chave estão no nome do cadastro (inclusive igual) e os identificadores
    (números e letras soltas) são os mesmos, ou nenhum lado tem; `MESMO_A_MAIS`: o contrário, o nome do cadastro cabe na
    chave, que tem palavras a mais; `OUTRO_NUMERO`: as palavras batem e o identificador não ("Quimera 2" contra "Nova
    Quimera 1"); None: as palavras não batem. Vale cada forma do nome do cadastro (`_termos_da_usina`)."""
    ws, ns = termos_da_chave
    achado = None
    for uw, un in _termos_da_usina(str(nome_da_usina or "")):
        if not _contidas(ws, uw):
            continue
        if un != ns:
            achado = achado or OUTRO_NUMERO
        elif ws <= uw:
            return MESMO
        else:
            achado = MESMO_A_MAIS
    return achado
