"""Geração em linhas (passo 6c do desenho Kimball de 08/10/2026): o `bd_thopen` e o `bd_performance`, uma aba por usina
e um inversor por coluna, viram dois fatos com `data_id`, `usina_id` e `equipamento_id`.

Por que: a auditoria de 08/10 achou a geração em formato largo, sem ID nenhum. Cruzar Campo × Performance exigia
traduzir à mão o nome da aba, e o resultado mudava conforme quem traduzia (59% ou 77% das usinas com OS no mês). A
regra 1 da casa manda a fonte larga virar linhas antes de entrar.

Os dois fatos (snapshot periódico diário: a fonte reescreve o dia quando corrige, e a carga troca o fato inteiro):
- `fato_geracao_usina_dia` — **1 linha = 1 aba de usina × 1 dia** que a aba tem até hoje. Medidas da usina (medidor,
  IPOA, GHI, chuva, disponibilidade, validado) e três AGREGADOS do inversor × dia (`energia_inversores_kwh`,
  `inversores_com_dado_qtd`, `inversores_qtd`), declarados assim: são a soma/contagem das linhas do outro fato.
- `fato_geracao_inversor_dia` — **1 linha = 1 inversor (coluna "Inversor n.m") × 1 dia com número**. Célula vazia ou
  com texto não vira linha.

Regras, cada uma com o caso que a criou:
- **Dia futuro não é fato.** O `bd_thopen` pré-cria as linhas até 22/03/2027 e o `bd_performance` até 22/11/2026
  (3.499 linhas futuras em 08/10, 0 células de inversor preenchidas nelas). Fica fora e conta na qualidade. Linha sem
  data (43 no `bd_performance`, onde estão 261 dos 262 kWh negativos) também.
- **Texto não é número; vírgula decimal é.** "#N/A" (48 células), "Valores Zerado", o cabeçalho repetido numa linha
  ("Inversor 3") = vazio e conta. "962,800" (30 células do `bd_thopen`) é 962,8 e "0.00" (271 do `bd_performance`) é
  0: 301 células de texto que valem 30.999 kWh. Ponto sozinho é decimal; "1.234.567" sem vírgula é ambíguo e vira
  vazio.
- **Fora da faixa = vazio + indicador 1.** Há leitura ACUMULADA no lugar da do dia (39 milhões de kWh num inversor do
  `bd_thopen`; 6,9 milhões no Multimedidor e 357 mil num inversor do `bd_performance`) e dias com 11 a 13 mil kWh em
  inversores cuja mediana é 1,5 mil. Somar isso daria a geração de anos num dia. O teto vem do cadastro (`tetos`); a
  linha fica no fato com o indicador, para a qualidade mostrar quanto caiu. O mesmo vale para IPOA, GHI e chuva fora
  do limite físico (`FAIXA`).
- **A usina vem SÓ do de-para publicado**, sistemas `BD_Thopen · aba` e `BD_Performance · aba` (a chave é o nome da
  aba; quem casa é `nexus/cadastro/banco.de_para`). Antes da publicação (é do Levi: passo 1 adiado), `usina_id` vazio e
  `usina_motivo = "aba sem de-para publicado"`; a qualidade mostra 0% de usina de propósito. Nada de mapa no código.
- **Aba de 2 usinas não liga.** O casamento por potência do `BD_Thopen · Dados Gerais Usinas` liga 2 chaves a 2 usinas
  cada ("a linha é das duas"); a geração da aba contaria em dobro no `usina_id`. Fica vazio, com o motivo.
- **Duas abas iguais da mesma usina não ligam** (`copias`): 5 pares em 08/10 com 100% dos números de inversor iguais
  (a aba velha parou, a nova segue); somar pelo usina_id dobraria o kWh. Quem decide qual vale é a tela Ligações.
  Duas abas que são PARTES da usina ("X 1" e "X 2" da "X 1 e 2") ligam as duas.
- **Dia repetido na mesma aba com valores diferentes sai inteiro** (não há como saber qual vale); repetido igual vale 1.
  Medido em 08/10: 0 nas duas fontes.
- **O equipamento do inversor vem só do apelido** `BD_Thopen · coluna` / `BD_Performance · coluna` do módulo de
  equipamento (`nexus_equipamentos · equipamento_apelido`): uma regra só para "qual ativo é a coluna Inversor 2.4".
- **Fora do fato, de propósito:** a coluna "Comentário" (texto livre), a "Usina" (a aba já diz), "SKID n (kWh)" e
  "Junco n.m" (têm "Disponibilidade" própria, como o SKID: não são coluna de inversor).

Puro: não lê nem grava nada. Quem lê o banco é `ferramentas/carregar_geracao.py` (só `--ensaio` até as decisões do
Levi). Herda o "encolher" do passo 0/1: aba regravada menor faz o fato encolher; `encolhidas` compara com a carga
anterior para a qualidade mostrar.
"""
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import date, datetime

from .calendario import data_id as _data_id

LIVRO = "nexus_geracao"
NOME_LIVRO = "Nexus · geração diária por usina (BD_Thopen e BD_Performance em linhas) e a qualidade da ligação"
ABA_USINA, ABA_INVERSOR = "fato_geracao_usina_dia", "fato_geracao_inversor_dia"
FONTES = ("bd_thopen", "bd_performance")
# o sistema do de-para (cadastro_nexus · de_para) em que a aba de cada fonte é a chave externa
SISTEMA_ABA = {"bd_thopen": "BD_Thopen · aba", "bd_performance": "BD_Performance · aba"}
SISTEMA_COLUNA = {"bd_thopen": "BD_Thopen · coluna", "bd_performance": "BD_Performance · coluna"}
MOTIVO_SEM_DE_PARA = "aba sem de-para publicado"
MOTIVO_ABA_NOVA = "aba fora do de-para publicado"
MOTIVO_COPIA = "aba com os mesmos números de outra aba da mesma usina (decidir na tela Ligações qual vale)"

CAB_USINA_DIA = ["geracao_usina_id", "data_id", "usina_id", "usina_ligada_por", "usina_motivo", "fonte", "aba",
                 "energia_medidor_kwh", "ipoa_kwh_m2", "ghi_kwh_m2", "chuva_mm", "disponibilidade_pct", "validado",
                 "energia_inversores_kwh", "inversores_com_dado_qtd", "inversores_qtd", "medidor_fora_da_faixa"]
# as três colunas do usina × dia que são agregado do inversor × dia (somar as duas não é somar duas medidas)
AGREGADAS_DO_INVERSOR = ("energia_inversores_kwh", "inversores_com_dado_qtd", "inversores_qtd")
CAB_INVERSOR_DIA = ["geracao_id", "data_id", "usina_id", "equipamento_id", "equipamento_ligado_por", "fonte", "aba",
                    "inversor", "energia_kwh", "kwh_fora_da_faixa"]
CAB_ATUALIZACAO = ["gerado_em", "maquina", "duracao_s", "linhas", "como_ler"]   # o mesmo da carga de hora em hora
# Para o catálogo (o mesmo molde de fato_ronda.py, fato_pt.py e programacao.py). (coluna, unidade, soma): o kWh soma
# entre usinas e dias; a irradiação e a chuva somam no tempo de UMA usina, não entre usinas (semi); a disponibilidade é
# média. Os três agregados do inversor × dia (AGREGADAS_DO_INVERSOR) não se somam com o próprio inversor × dia.
TIPO = "snapshot_periodico"
GRAO_USINA = "1 linha = 1 aba de usina × 1 dia (até hoje; dia futuro fora)"
GRAO_INVERSOR = "1 linha = 1 inversor (coluna \"Inversor n.m\") × 1 dia com número"
CHAVE_USINA, CHAVE_INVERSOR = ("geracao_usina_id",), ("geracao_id",)
MEDIDAS_USINA = (("energia_medidor_kwh", "kWh", "aditiva"), ("energia_inversores_kwh", "kWh", "aditiva"),
                 ("inversores_com_dado_qtd", "qtd", "semi"), ("inversores_qtd", "qtd", "semi"),
                 ("ipoa_kwh_m2", "kWh/m²", "semi"), ("ghi_kwh_m2", "kWh/m²", "semi"), ("chuva_mm", "mm", "semi"),
                 ("disponibilidade_pct", "%", "nao"), ("validado", "1/0", "aditiva"),
                 ("medidor_fora_da_faixa", "1/0", "aditiva"))
MEDIDAS_INVERSOR = (("energia_kwh", "kWh", "aditiva"), ("kwh_fora_da_faixa", "1/0", "aditiva"))

# Medida da usina -> as colunas que a valem, na ordem: vale a 1ª que EXISTE na aba (escolha por coluna, nunca célula a
# célula: misturar o IPOA "DEF" de um dia com o simples do outro faria uma série que nenhuma das duas é).
# No `bd_performance` o IPOA é o "DEF" (decisão da Performance) e a energia é o "Multimedidor".
COLUNAS_DA_USINA = (
    ("energia_medidor_kwh", ("Energia Produzida (kWh)", "Multimedidor")),
    ("ipoa_kwh_m2", ("IPOA (kWh/m²) DEF", "IPOA (kWh/m²)")),
    ("ghi_kwh_m2", ("GHI (kWh/m²)",)),
    ("chuva_mm", ("Chuva (mm)", "Pluviômetro (mm)")),
    ("disponibilidade_pct", ("Disponibilidade Usina (%)",)),
    ("validado", ("Validação",)),
)
ENERGIA_DA_USINA = frozenset(COLUNAS_DA_USINA[0][1])
# Limites físicos (o que passa disso não é medida do dia): irradiação diária acima do sol fora da atmosfera num plano
# que o segue (~18 kWh/m² nos dias mais longos do Brasil) e negativa; chuva acima de 500 mm num dia (o pluviômetro do
# `bd_performance` tem 40.209 "mm": é o acumulado); disponibilidade fora de 0 a 100%.
FAIXA = {"ipoa_kwh_m2": (0.0, 18.0), "ghi_kwh_m2": (0.0, 18.0), "chuva_mm": (0.0, 500.0),
         "disponibilidade_pct": (0.0, 100.0)}
HORAS_DIA = 24

_INVERSOR = re.compile(r"^\s*inversor\s*(\d+(?:\.\d+)?)\s*$", re.IGNORECASE)


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _id(v) -> int | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if math.isfinite(f) and f.is_integer() and f > 0 else None


def _sha(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


# ── leitura das células ─────────────────────────────────────────────────────────────────────────────────────────────
def numero(v) -> float | None:
    """Célula -> número. "962,800" (vírgula decimal) = 962,8; "1.234,5" = 1234,5; "853.1" = 853,1. "#N/A", "Valores
    Zerado", espaço não separável, "1.234.567" sem vírgula (ambíguo) e qualquer outro texto = None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return f if math.isfinite(f) else None
    s = str(v).replace("\xa0", "").replace(" ", "").strip()
    if re.fullmatch(r"-?\d+(,\d+)?", s):
        return float(s.replace(",", "."))
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+,\d+", s):
        return float(s.replace(".", "").replace(",", "."))
    return None


def _disponibilidade(v) -> float | None:
    """A fonte grava fração (1 = 100%: 25.352 células de 0 a 1 no `bd_thopen`) e, às vezes, texto "98,5%". Sai em %."""
    s = _txt(v)
    if s.endswith("%"):
        x = numero(s[:-1])
        return x
    x = numero(v)
    if x is None:
        return None
    return x * 100.0 if 0 <= x <= 1 else x


def data_da_linha(v) -> date | None:
    """A coluna "Data" (texto "2026-10-07", 100% assim em 08/10). Aceita também {"$dt": ...}, date e "07/10/2026".
    É o dia do calendário da planilha (não um instante): não há fuso a converter."""
    if isinstance(v, dict):
        v = v.get("$dt")
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = _txt(v)
    try:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", s)
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None
    return None


def rotulo_inversor(coluna) -> str | None:
    """"Inversor 1.1", "inversor 2.3" e "Inversor 4" -> "Inversor 1.1"... (23 colunas do `bd_thopen` vêm em minúscula).
    Outra coluna -> None (SKID, "Junco 1.1", disponibilidade: não são inversor)."""
    m = _INVERSOR.match(_txt(coluna))
    return f"Inversor {m.group(1)}" if m else None


def _cabecalho(linhas) -> list:
    return list(linhas[0].keys()) if linhas else []


def abas_de_geracao(abas: dict) -> list[tuple[str, list[dict], list[str]]]:
    """[(aba, linhas, colunas de inversor)] das abas de geração: têm "Data" e ao menos uma coluna "Inversor n.m" ou a
    energia da usina (há uma aba do `bd_thopen` só com a energia do medidor, sem inversor: entra com
    `inversores_qtd = 0`). As abas de cadastro e de histórico mensal ("Dados Gerais Usinas", "Info Geral", "Base
    UFV"...) e os históricos em formato longo de cliente (colunas "Data", "Usina", "Geração") ficam fora."""
    out = []
    for aba, linhas in (abas or {}).items():
        cab = _cabecalho(linhas)
        nomes = {_txt(c) for c in cab}
        inv = [c for c in cab if rotulo_inversor(c)]
        if "Data" in nomes and (inv or nomes & ENERGIA_DA_USINA):
            out.append((aba, linhas, inv))
    return out


# ── ligação: usina, teto e equipamento ──────────────────────────────────────────────────────────────────────────────
def usina_da_aba(sistema: str, aba: str, de_para) -> tuple[int | None, str | None, str]:
    """(usina_id, ligada_por, motivo) pelo de-para PUBLICADO (`cadastro_nexus · de_para`). Só os sistemas de aba valem:
    o `BD_Thopen · Dados Gerais Usinas` liga 84 abas por nome igual, mas usá-lo aqui seria um mapa escondido no código
    (decisão do Levi, seção 9 do desenho). Sem o sistema publicado: `MOTIVO_SEM_DE_PARA`. Aba que o de-para liga a 2+
    usinas (a soma do casamento por potência) não liga: o kWh contaria em dobro."""
    if sistema not in SISTEMA_ABA.values():
        raise ValueError(f"sistema de aba desconhecido: {sistema!r}")
    do_sistema = [d for d in de_para or () if _txt(d.get("sistema")) == sistema]
    if not do_sistema:
        return None, None, MOTIVO_SEM_DE_PARA
    da_aba = [d for d in do_sistema if _txt(d.get("chave_externa")) == _txt(aba)]
    if not da_aba:
        return None, None, MOTIVO_ABA_NOVA
    ids = sorted({i for i in (_id(d.get("usina_id")) for d in da_aba) if i})
    como = _txt(da_aba[0].get("casou_por"))
    if len(ids) == 1:
        return ids[0], f"de-para ({como})" if como else "de-para", ""
    if ids:
        return None, None, f"aba de {len(ids)} usinas no de-para ({como})"
    return None, None, como or "sem par no cadastro"


def potencia_kw(texto) -> float | None:
    """A "Potência dos inversores" do cadastro (texto livre: "250", "250 kW", "125 / 250", "75kWac", "100 kVA") -> o
    maior valor em kW. Número de corrente ou tensão ("999,9 A / 800 Vca") não conta; "N/I" = None."""
    s = _txt(texto).lower().replace(",", ".")
    vals = []
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*([a-z]*)", s):
        unid = m.group(2)
        if unid in ("", "e") or unid.startswith(("kw", "kva")):
            vals.append(float(m.group(1)))
    v = max(vals) if vals else None
    return v if v and v > 0 else None


def _mwp(usina: dict | None) -> float | None:
    if not usina:
        return None
    vs = [numero(usina.get(c)) for c in ("potencia_contratual", "potencia_real")]
    vs = [v for v in vs if v and v > 0]
    return max(vs) if vs else None


def tetos(usina: dict | None, maior_mwp: float | None) -> tuple[float | None, float | None, str]:
    """(teto do inversor, teto do medidor da usina, como) em kWh/dia: a potência o dia inteiro, que nenhum dia de sol
    alcança. Proposta do desenho (seção 9, decisão do Levi): inversor = potência dos inversores × 24 h. Sem ela, a
    potência da usina × 24 h (um inversor não gera mais que a usina dele); sem usina ligada, a MAIOR usina do cadastro
    × 24 h (7,02 MWp em 08/10 = 168 mil kWh/dia), que derruba a leitura acumulada (39 milhões) sem tocar no dia real (o
    maior inversor legítimo medido tem ~4 mil kWh/dia). Sem nada, só o negativo cai."""
    mwp = _mwp(usina)
    kw = potencia_kw(usina.get("potencia_inversores")) if usina else None
    if kw:
        inv, como = kw * HORAS_DIA, "potência dos inversores × 24 h"
    elif mwp:
        inv, como = mwp * 1000 * HORAS_DIA, "potência da usina × 24 h"
    elif maior_mwp:
        inv, como = maior_mwp * 1000 * HORAS_DIA, "maior usina do cadastro × 24 h"
    else:
        inv, como = None, "sem teto: só o negativo cai"
    usi = (mwp or maior_mwp or 0) * 1000 * HORAS_DIA or None
    return inv, usi, como


def chave_da_coluna(aba, coluna) -> str:
    """A chave externa do apelido `BD_Thopen · coluna` / `BD_Performance · coluna` em `nexus_equipamentos ·
    equipamento_apelido`: "aba|coluna", o formato do módulo de equipamento (o teste de ponta a ponta prova)."""
    return f"{_txt(aba)}|{_txt(coluna)}"


def indice_apelidos(apelidos) -> dict:
    """{(sistema, chave): equipamento_id} dos apelidos de coluna (linhas no CAB_APELIDO ou dicts lidos do banco).
    Qual inversor é qual equipamento é UMA regra, do módulo de equipamento ("Inversor 2.4" da aba da usina 7 -> o
    membro "<código da usina 7>-INVR2.4", só se for um): o fato só a lê, para não haver duas respostas."""
    sistemas = set(SISTEMA_COLUNA.values())
    out = {}
    for a in apelidos or ():
        eid, sistema, chave = (a.get("equipamento_id"), a.get("sistema"), a.get("chave_externa")) \
            if isinstance(a, dict) else (a[0], a[1], a[2])
        if _txt(sistema) in sistemas and _id(eid):
            out[(_txt(sistema), _txt(chave))] = _id(eid)
    return out


def equipamentos_das_colunas(fonte: str, aba: str, colunas, apelidos_idx: dict) -> dict:
    """{coluna: (equipamento_id, ligado_por)} pelos apelidos. Coluna sem apelido: fica fora (o fato leva vazio)."""
    sistema = SISTEMA_COLUNA[fonte]
    out = {}
    for c in colunas:
        eid = (apelidos_idx or {}).get((sistema, chave_da_coluna(aba, c)))
        if eid:
            out[c] = (eid, f"apelido {sistema}")
    return out


def cabecalhos(abas_por_fonte: dict) -> dict:
    """{(fonte, aba): [colunas]} das abas de geração: o que `equipamento.colunas_de_geracao` pede."""
    return {(f, aba): _cabecalho(linhas) for f in FONTES
            for aba, linhas, _c in abas_de_geracao((abas_por_fonte or {}).get(f))}


def usinas_das_abas(abas_por_fonte: dict, de_para) -> dict:
    """{(fonte, aba): usina_id} pelo de-para publicado (vazio = não liga): a outra metade do que
    `equipamento.colunas_de_geracao` pede. A aba que não liga fica sem apelido de coluna."""
    return {(f, aba): usina_da_aba(SISTEMA_ABA[f], aba, de_para)[0] for (f, aba) in cabecalhos(abas_por_fonte)}


# ── os fatos ────────────────────────────────────────────────────────────────────────────────────────────────────────
def _coluna(cab, nome):
    return next((c for c in cab if _txt(c) == nome), None)


def _dias(linhas, hoje: date | None, conta: Counter) -> list[tuple[date, dict]]:
    """As linhas com dia válido e não futuro, uma por dia, em ordem."""
    col = _coluna(_cabecalho(linhas), "Data")
    por_dia = defaultdict(list)
    for l in linhas:
        d = data_da_linha(l.get(col)) if col is not None else None
        if d is None:
            conta["sem_data"] += 1
        elif hoje and d > hoje:
            conta["dia_futuro"] += 1
        else:
            por_dia[d].append(l)
    out = []
    for d in sorted(por_dia):
        ls = por_dia[d]
        if len(ls) > 1:
            if any(x != ls[0] for x in ls[1:]):
                conta["dia_repetido_divergente"] += len(ls)
                continue
            conta["dia_repetido_igual"] += len(ls) - 1
        out.append((d, ls[0]))
    return out


def linhas_inversor_dia(fonte: str, aba: str, linhas: list[dict], usina, teto: float | None, equip: dict | None,
                        hoje: date | None = None) -> tuple[list[list], Counter]:
    """(linhas de `fato_geracao_inversor_dia`, contagens). 1 linha por célula de inversor com número; negativo ou acima
    do `teto` -> `energia_kwh` vazio e `kwh_fora_da_faixa = 1`. Duas colunas da mesma aba com o mesmo inversor
    ("Inversor 1.1" e "inversor 1.1") saem as duas: não há como saber qual vale."""
    uid = usina[0] if usina else None
    cab = _cabecalho(linhas)
    rotulos = {c: rotulo_inversor(c) for c in cab if rotulo_inversor(c)}
    repetidos = {r for r, n in Counter(rotulos.values()).items() if n > 1}
    conta = Counter()
    conta["coluna_repetida"] += sum(1 for r in rotulos.values() if r in repetidos)
    cols = [(c, r) for c, r in rotulos.items() if r not in repetidos]
    equip = equip or {}
    out = []
    for d, l in _dias(linhas, hoje, conta):
        did, iso = _data_id(d), d.isoformat()
        for c, rot in cols:
            v = l.get(c)
            if _txt(v) == "":
                continue
            x = numero(v)
            if x is None:
                conta["texto"] += 1
                continue
            fora = x < 0 or (teto is not None and x > teto)
            eid, como = equip.get(c) or (None, None)
            out.append([_sha(f"{fonte}|{aba}|{rot}|{iso}"), did, uid, eid, como, fonte, aba, rot,
                        None if fora else round(x, 3), 1 if fora else 0])
            conta["fora_da_faixa"] += fora
    return out, conta


def _medida(medida: str, v, teto_medidor, conta: Counter):
    if _txt(v) == "":
        return None, 0
    if medida == "disponibilidade_pct":
        x = _disponibilidade(v)
    else:
        x = numero(v)
    if x is None:
        conta[f"{medida}_texto"] += 1
        return None, 0
    if medida == "validado":
        return (int(x) if x in (0, 1) else None), 0
    if medida == "energia_medidor_kwh":
        if x < 0 or (teto_medidor is not None and x > teto_medidor):
            conta["medidor_fora_da_faixa"] += 1
            return None, 1
        return round(x, 3), 0
    lo, hi = FAIXA[medida]
    if not lo <= x <= hi:
        conta[f"{medida}_fora_da_faixa"] += 1
        return None, 0
    return round(x, 4 if medida.endswith("_m2") else 2), 0


def linhas_usina_dia(fonte: str, aba: str, linhas: list[dict], usina, hoje: date | None, colunas=None,
                     inversores=(), teto: float | None = None) -> tuple[list[list], Counter]:
    """(linhas de `fato_geracao_usina_dia`, contagens). `usina` = (usina_id, ligada_por, motivo) de `usina_da_aba`;
    `colunas` = as colunas de inversor da aba (o `inversores_qtd`); `inversores` = as linhas do inversor × dia DESTA aba
    (os três agregados saem delas, nunca de outra conta); `teto` = o do medidor (`tetos`)."""
    uid, como, motivo = usina if usina else (None, None, MOTIVO_SEM_DE_PARA)
    cab = _cabecalho(linhas)
    pega = {}
    for medida, opcoes in COLUNAS_DA_USINA:
        k = next((c for c in (_coluna(cab, o) for o in opcoes) if c is not None), None)
        if k is not None:
            pega[medida] = k
    if colunas is None:
        colunas = [c for c in cab if rotulo_inversor(c)]
    n_inv = len({rotulo_inversor(c) for c in colunas})
    i_dia, i_kwh = CAB_INVERSOR_DIA.index("data_id"), CAB_INVERSOR_DIA.index("energia_kwh")
    agg = defaultdict(lambda: [0.0, 0])
    for r in inversores:
        if r[i_kwh] is not None:
            a = agg[r[i_dia]]
            a[0] += r[i_kwh]
            a[1] += 1
    conta = Counter()
    out = []
    for d, l in _dias(linhas, hoje, conta):
        did = _data_id(d)
        m, fora = {}, 0
        for medida, _ in COLUNAS_DA_USINA:
            m[medida], f = _medida(medida, l.get(pega[medida]), teto, conta) if medida in pega else (None, 0)
            fora |= f
        soma, com = agg.get(did, (0.0, 0))
        if not any(v is not None for v in m.values()) and not com:
            conta["dia_sem_medida"] += 1
        out.append([_sha(f"{fonte}|{aba}|{d.isoformat()}"), did, uid, como, motivo or None, fonte, aba,
                    m["energia_medidor_kwh"], m["ipoa_kwh_m2"], m["ghi_kwh_m2"], m["chuva_mm"],
                    m["disponibilidade_pct"], m["validado"], round(soma, 3) if com else None, com, n_inv, fora])
    return out, conta


# ── encolher (herança do passo 0/1) ─────────────────────────────────────────────────────────────────────────────────
def dias_por_aba(linhas) -> dict:
    """{(fonte, aba): dias} das linhas do `fato_geracao_usina_dia` (listas no CAB_USINA_DIA ou dicts lidos do banco)."""
    i_f, i_a = CAB_USINA_DIA.index("fonte"), CAB_USINA_DIA.index("aba")
    out = Counter()
    for l in linhas or ():
        f, a = (l.get("fonte"), l.get("aba")) if isinstance(l, dict) else (l[i_f], l[i_a])
        out[(_txt(f), _txt(a))] += 1
    return dict(out)


def encolhidas(anterior: dict, atual: dict) -> list[tuple[str, str, int, int]]:
    """[(fonte, aba, dias antes, dias agora)] das abas que perderam dia desde a carga anterior (ou sumiram). O dia
    futuro não está em nenhuma das duas contas, então crescer é o normal; cair é aba regravada menor, e a troca integral
    apaga o que caiu (a guarda de verdade é a do passo 1)."""
    return sorted((f, a, n, atual.get((f, a), 0)) for (f, a), n in (anterior or {}).items()
                  if atual.get((f, a), 0) < n)


# ── a mesma usina em duas abas ──────────────────────────────────────────────────────────────────────────────────────
def _valores_inversor(linhas, hoje) -> dict:
    out = {}
    for l in linhas:
        d = data_da_linha(l.get(_coluna(_cabecalho(linhas), "Data")))
        if d is None or (hoje and d > hoje):
            continue
        for c in _cabecalho(linhas):
            rot = rotulo_inversor(c)
            x = numero(l.get(c)) if rot else None
            if x:                                       # zero não prova nada: duas partes paradas no mesmo dia
                out[(d, rot)] = x
    return out


def copias(ligadas, hoje=None, minimo: int = 10, fracao: float = 0.9) -> set:
    """{(fonte, aba)} das abas que são CÓPIA de outra aba da mesma usina: mesmo inversor, mesmo dia, mesmo número em
    >= 90% das células em comum (ao menos 10). Medido em 08/10 com o de-para calculado: 5 pares (1 no `bd_thopen`, 4
    no `bd_performance`) com 100% iguais — uma aba parada em 30/09 e a outra seguindo, a de nome igual ao do cadastro;
    somar as duas pelo usina_id dobraria o kWh de agosto e setembro. Qual vale é decisão de quem conhece a planilha
    (ignorar a outra na tela Ligações): até lá, nenhuma das duas liga. Duas abas que são PARTES da usina ("X 1" e "X 2"
    para a "X 1 e 2" do cadastro: 4 pares, 0 a 0,5% iguais) ligam as duas, e a soma pelo usina_id é a usina.
    `ligadas` = [(fonte, aba, usina_id, linhas)]."""
    por_usina = defaultdict(list)
    for fonte, aba, uid, linhas in ligadas:
        if uid:
            por_usina[uid].append((fonte, aba, linhas))
    out = set()
    for grupo in por_usina.values():
        if len(grupo) < 2:
            continue
        vals = [(f, a, _valores_inversor(ls, hoje)) for f, a, ls in grupo]
        for i in range(len(vals)):
            for j in range(i + 1, len(vals)):
                (fa, aa, va), (fb, ab, vb) = vals[i], vals[j]
                comum = va.keys() & vb.keys()
                iguais = sum(1 for k in comum if abs(va[k] - vb[k]) < 1e-6)
                if len(comum) >= minimo and iguais >= fracao * len(comum):
                    out |= {(fa, aa), (fb, ab)}
    return out


# ── a montagem ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _pct(n, total) -> float:
    return round(100.0 * n / total, 1) if total else 0.0


def montar(abas_por_fonte: dict, de_para, usinas, hoje, agora: str, *, apelidos=None, anterior=None,
           maquina: str | None = None, origem_em: str | None = None) -> tuple[dict, list, dict]:
    """(tabelas do livro `nexus_geracao`, linhas do inversor × dia, relatório só com contagens). Não lê nem grava.

    `abas_por_fonte` = {"bd_thopen": {aba: linhas}, "bd_performance": {...}}; `de_para` e `usinas` = as abas do
    `cadastro_nexus` (o de-para publicado: sem os sistemas de aba, a usina fica vazia); `apelidos` = as linhas de
    `nexus_equipamentos · equipamento_apelido` (sem elas, `equipamento_id` vazio); `anterior` = as linhas do
    `fato_geracao_usina_dia` da carga anterior (para `encolhidas`); `origem_em` = quando as duas bases foram gravadas
    (o que a API diz). O inversor × dia NÃO vai nas tabelas: não cabe em
    troca integral (~44 MB/dia) e espera a decisão do Levi (passo 0 ou livros mensais)."""
    hoje = hoje if isinstance(hoje, date) else date.fromisoformat(_txt(hoje)[:10])
    cad = {_id(u.get("usina_id")): u for u in usinas or ()
           if _id(u.get("usina_id")) and _txt(u.get("excluido")).lower() != "sim"}
    maior = max((m for m in (_mwp(u) for u in cad.values()) if m), default=None)
    apel = indice_apelidos(apelidos)
    fato_u, fato_i = [], []
    conta, motivos, como, teto_como, abas_n, sem_u = Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
    linhas_motivo = Counter()
    abas = [(fonte, aba, linhas, cols, usina_da_aba(SISTEMA_ABA[fonte], aba, de_para)) for fonte in FONTES
            for aba, linhas, cols in abas_de_geracao((abas_por_fonte or {}).get(fonte))]
    duplicadas = copias([(f, a, u[0], ls) for f, a, ls, _c, u in abas], hoje)
    por_usina = Counter(u[0] for f, a, _l, _c, u in abas if u[0] and (f, a) not in duplicadas)
    for fonte, aba, linhas, cols, usina in abas:
        abas_n[fonte] += 1
        if (fonte, aba) in duplicadas:
            usina = (None, None, MOTIVO_COPIA)
        u = cad.get(usina[0])
        t_inv, t_usi, t_como = tetos(u, maior)
        teto_como[t_como] += 1
        equip = equipamentos_das_colunas(fonte, aba, cols, apel) if usina[0] else {}
        li, ci = linhas_inversor_dia(fonte, aba, linhas, usina, t_inv, equip, hoje)
        lu, cu = linhas_usina_dia(fonte, aba, linhas, usina, hoje, cols, li, t_usi)
        fato_i += li
        fato_u += lu
        conta.update({f"inversor_{k}": v for k, v in ci.items()})
        conta.update(cu)
        conta["colunas_inversor"] += len(cols)
        conta["colunas_inversor_ligadas"] += len(equip)
        if usina[0]:
            como[usina[1]] += len(lu)
        else:
            motivos[usina[2]] += 1
            linhas_motivo[usina[2]] += len(lu)
            sem_u[aba] += len(lu)
    n_u, n_i = len(fato_u), len(fato_i)
    # rel e extra levam só contagens e caminhos; o nome da aba (= nome da usina) só vai no exemplo da qualidade
    com_u = sum(1 for l in fato_u if l[2] is not None)
    com_eq = sum(1 for l in fato_i if l[3] is not None)
    atual = dias_por_aba(fato_u)
    menores = encolhidas(dias_por_aba(anterior), atual) if anterior else []
    datas = sorted(l[1] for l in fato_u)
    # a aba que o Levi tirou da conta na tela Ligações (usina fora da operação da Grid) não é lacuna a consertar: o
    # percentual "sem as ignoradas" é o que a régua dos 98% da casa olha
    ignoradas = sum(n for m, n in linhas_motivo.items() if m.startswith("ignorado"))
    rel = {
        "gerado_em": agora, "abas": dict(abas_n), "linhas_usina_dia": n_u, "linhas_inversor_dia": n_i,
        "com_data": n_u, "com_usina": com_u, "pct_usina": _pct(com_u, n_u),
        "inversor_com_usina": sum(1 for l in fato_i if l[2] is not None), "inversor_com_equipamento": com_eq,
        "pct_equipamento": _pct(com_eq, n_i), "usina_por": dict(como), "abas_sem_usina_por_motivo": dict(motivos),
        "linhas_sem_usina_por_motivo": dict(linhas_motivo), "pct_usina_sem_ignoradas": _pct(com_u, n_u - ignoradas),
        "abas_copia": len(duplicadas), "usinas_em_2_abas": sum(1 for n in por_usina.values() if n > 1),
        "teto": dict(teto_como), "contagens": dict(sorted(conta.items())),
        "periodo": [datas[0], datas[-1]] if datas else None, "encolhidas": len(menores),
        "dias": len({l[1] for l in fato_u}),
    }
    extra = {"abas": dict(abas_n), "inversor_dia": n_i, "inversor_com_equipamento": com_eq,
             "inversor_fora_da_faixa": conta["inversor_fora_da_faixa"], "inversor_texto": conta["inversor_texto"],
             "medidor_fora_da_faixa": conta["medidor_fora_da_faixa"], "dia_futuro": conta["dia_futuro"],
             "sem_data": conta["sem_data"], "dia_sem_medida": conta["dia_sem_medida"],
             "dia_repetido_divergente": conta["dia_repetido_divergente"],
             "abas_sem_usina": dict(motivos), "linhas_sem_usina": dict(linhas_motivo),
             "pct_usina_sem_ignoradas": _pct(com_u, n_u - ignoradas), "abas_copia": len(duplicadas),
             "usinas_em_2_abas": sum(1 for n in por_usina.values() if n > 1), "teto": dict(teto_como),
             "encolhidas": [f"{f}|{a}: {n0} -> {n1}" for f, a, n0, n1 in menores[:10]], "encolhidas_qtd": len(menores)}
    q = {"fato": "geracao_usina_dia", "livro_origem": "bd_thopen · bd_performance (1 aba por usina)", "linhas": n_u,
         "com_data": n_u, "com_usina": com_u, "pct_data": _pct(n_u, n_u), "pct_usina": _pct(com_u, n_u),
         "usina_por_de_para": com_u, "usina_por_codigo": 0,
         "sem_usina_exemplos": "; ".join(f"{k} ({v})" for k, v in sem_u.most_common(6)) or None,
         "origem_atualizada_em": origem_em, "gerado_em": agora,
         "extra": json.dumps(extra, ensure_ascii=False, separators=(",", ":"))}
    from .fatos import CAB_QUALIDADE       # o cabeçalho da qualidade é um só para todos os fatos
    tabelas = {
        ABA_USINA: (CAB_USINA_DIA, fato_u),
        "qualidade": (list(CAB_QUALIDADE), [linha_qualidade(q, CAB_QUALIDADE)]),
        "atualizacao": (CAB_ATUALIZACAO, [[agora, maquina, None, n_u,
                                           "data_id = AAAAMMDD; usina_id do de-para publicado (vazio = ver "
                                           "usina_motivo); inversor × dia ainda fora do banco"]]),
    }
    return tabelas, fato_i, rel


def linha_qualidade(q: dict, cab: list) -> list:
    """A linha da aba `qualidade` no cabeçalho que a carga usar (`fatos.CAB_QUALIDADE`, que muda no passo 2 do desenho):
    preenche pelo NOME da coluna e deixa vazia a que não conhece."""
    return [q.get(c) for c in cab]
