"""O uso das telas do OS Creator e os pedidos ao Fracttal, por hora, no banco (31/10/2026, etapa 0 do canto central do OS
Creator). Quem mede é a casca, na memória (`casca/uso_os.py` e `casca/fracttal_conta.py`): de hora em hora tira as horas
fechadas dos contadores para o DISCO do servidor e, UMA vez por dia (03:45 de Brasília), as leva ao banco. Aqui mora só o
fato: as colunas, o grão, a chave, a gravação e a leitura. Módulo puro: nada de Flask, e a rede só pela sessão que o
chamador passa.

Em 13 e 14/10/2026 o OS Creator prendeu as threads do Nexus e ninguém soube dizer quais telas as pessoas abrem, a que hora,
em quantas, quanto cada uma demora e quanto pede ao Fracttal (200 pedidos por minuto, para a empresa toda). Os dois
contadores só viviam na memória: um deploy ou um reinício apagava a história, e o "antes e depois" de cada etapa seguinte
seria chute. O livro é um por mês (`nexus_oscreator_uso_AAAA_MM`; o mês é o do `hora_id`, de Brasília), com três abas:

- `fato_uso_hora`: 1 linha = 1 rota × clique ou automático × 1 hora.
- `fato_fracttal_hora`: 1 linha = 1 origem × 1 método × 1 hora (quem pediu ao Fracttal e o quê).
- `fato_fracttal_total_hora`: 1 linha = 1 hora, o total dos pedidos de todas as origens juntas e o maior número de pedidos
  num minuto (Ruling N, 31/10/2026). O contador do Fracttal entrega o total como uma linha de origem `*` e método `*` no
  meio do detalhe, e `separar_total` a leva para a aba própria: um total dentro do detalhe mistura dois grãos (regra 1 do
  `nexus/dados/CLAUDE.md`), e quem soma `pedidos_qtd` do detalhe contaria em dobro. O pico do total não é a soma dos picos.

Foto periódica da hora que fechou, nas três.

- **Nada pessoal, nem o setor** (regras 4 e 8; o banco tem leitura aberta e não apaga). Rota, hora e contagens. A contagem
  de pessoas distintas (`pessoas_qtd`) não diz quem. O corte por setor fica só no disco do servidor, por dia, 30 dias.
- **Regravar a mesma hora não duplica.** `gravar` relê o livro do mês, troca as linhas de mesma chave e publica pelo
  `livros.publicar` (que confere a contagem depois e, antes, a trava `so_cresce`). Quando a gravação seguinte repete uma hora
  (a anterior falhou na conferência, ou o processo morreu entre gravar e limpar o pendente), a linha mais nova vale.
- **Leitura curta não grava.** Cada aba lida é conferida com o `row_count` da listagem do banco: página que volta sem a
  última linha daria um livro menor, e a gravação de UMA linha o levaria de volta ao tamanho que o `so_cresce` aceita,
  apagando as últimas (a lição do livro do inventário, 26/10/2026).
- **Uma vez por dia, não de hora em hora** (Ruling M): gravar o livro do mês inteiro custa ~7 s de processador no mês cheio
  (medido em 31/10/2026: o `xlsx` sozinho, 5,7 s), e o Nexus é UM processo com o servidor já apertado. Às 03:45, a hora mais
  parada, o custo é o mesmo e não trava ninguém; o pendente do disco cobre o resto do dia (e o Raio-X o lê de lá).
- **Medidas** (catálogo): as contagens de pedidos, recusas e erros somam; as pessoas distintas, a mediana e o p95 em ms e o
  pico por minuto não somam em corte nenhum.
"""
from datetime import datetime, timedelta

from . import livros
from .fato_ronda import GraoDuplicado

LIVRO_MOLDE = "nexus_oscreator_uso_AAAA_MM"
LIVRO_DO_MES = "nexus_oscreator_uso_{}_{}"
NOME_DO_MES = "Nexus · uso do OS Creator e pedidos ao Fracttal por hora ({}-{})"
ABA_USO, ABA_FRACTTAL, ABA_TOTAL = "fato_uso_hora", "fato_fracttal_hora", "fato_fracttal_total_hora"
ABAS = (ABA_USO, ABA_FRACTTAL, ABA_TOTAL)
NOME_DA_ABA = {ABA_USO: "uso", ABA_FRACTTAL: "fracttal", ABA_TOTAL: "total"}     # como `ler_dias` chama cada uma
TOTAL = "*"                                  # a origem e o método da linha de total que o contador do Fracttal entrega

CAB_USO = ["hora_id", "data_id", "hora", "rota", "automatico", "pedidos_qtd", "pessoas_qtd", "duracao_p50_ms",
           "duracao_p95_ms", "erros_qtd", "ocupado_qtd", "fracttal_qtd"]
CAB_FRACTTAL = ["hora_id", "data_id", "hora", "origem", "metodo", "pedidos_qtd", "recusas_qtd", "erros_qtd",
                "pico_minuto_qtd"]
CAB_FRACTTAL_TOTAL = ["hora_id", "data_id", "hora", "pedidos_qtd", "recusas_qtd", "erros_qtd", "pico_minuto_qtd"]
CABS = {ABA_USO: CAB_USO, ABA_FRACTTAL: CAB_FRACTTAL, ABA_TOTAL: CAB_FRACTTAL_TOTAL}
CHAVE_USO = ("hora_id", "rota", "automatico")
CHAVE_FRACTTAL = ("hora_id", "origem", "metodo")
CHAVE_TOTAL = ("hora_id",)
CHAVES = {ABA_USO: CHAVE_USO, ABA_FRACTTAL: CHAVE_FRACTTAL, ABA_TOTAL: CHAVE_TOTAL}

TIPO = "snapshot_periodico"
GRAO_USO = ("1 linha = 1 rota × clique ou automático × 1 hora de Brasília: o uso das telas do OS Creator (e das rotas "
            "do Nexus que o OS Creator chama), medido na memória do servidor, guardado no disco de hora em hora e levado ao "
            "banco uma vez por dia")
GRAO_FRACTTAL = ("1 linha = 1 origem × 1 método × 1 hora de Brasília dos pedidos do Nexus ao Fracttal: quem pediu (a rota "
                 "ou a tarefa de fundo) e o quê (o método); o total da hora mora no fato fracttal_total_hora")
GRAO_TOTAL = ("1 linha = 1 hora de Brasília: o total dos pedidos do Nexus ao Fracttal, de todas as origens juntas, e o maior "
              "número de pedidos num único minuto da hora")
# (coluna, unidade, soma) para o `catalogo.Medida`. Contagem de pedidos soma; pessoas distintas, o tempo e o pico por minuto não.
MEDIDAS_USO = (("pedidos_qtd", "qtd", "aditiva"), ("pessoas_qtd", "qtd", "nao"), ("duracao_p50_ms", "ms", "nao"),
               ("duracao_p95_ms", "ms", "nao"), ("erros_qtd", "qtd", "aditiva"), ("ocupado_qtd", "qtd", "aditiva"),
               ("fracttal_qtd", "qtd", "aditiva"))
MEDIDAS_FRACTTAL = (("pedidos_qtd", "qtd", "aditiva"), ("recusas_qtd", "qtd", "aditiva"), ("erros_qtd", "qtd", "aditiva"),
                    ("pico_minuto_qtd", "qtd", "nao"))
MEDIDAS_TOTAL = MEDIDAS_FRACTTAL                  # as mesmas quatro: o total soma como o detalhe, e o pico não soma
JANELA_ORIGEM = ("o Nexus é a fonte (a memória do servidor, guardada no disco de hora em hora e levada ao banco uma vez "
                 "por dia, às 03:45 de Brasília)")

# Cada coluna depois do tempo: "t" texto da chave, "b" 1 ou 0, "n" número inteiro de 0 para cima, "n?" o mesmo ou vazio
# (o balde só de pedidos que o teto recusou não tem duração: célula vazia, nunca 0).
_ESQUEMA = {ABA_USO: (("rota", "t"), ("automatico", "b"), ("pedidos_qtd", "n"), ("pessoas_qtd", "n"),
                      ("duracao_p50_ms", "n?"), ("duracao_p95_ms", "n?"), ("erros_qtd", "n"), ("ocupado_qtd", "n"),
                      ("fracttal_qtd", "n")),
            ABA_FRACTTAL: (("origem", "t"), ("metodo", "t"), ("pedidos_qtd", "n"), ("recusas_qtd", "n"),
                           ("erros_qtd", "n"), ("pico_minuto_qtd", "n")),
            ABA_TOTAL: (("pedidos_qtd", "n"), ("recusas_qtd", "n"), ("erros_qtd", "n"), ("pico_minuto_qtd", "n"))}
_MEDIDAS_DO_TOTAL = ("pedidos_qtd", "recusas_qtd", "erros_qtd", "pico_minuto_qtd")


class LeituraIncompleta(RuntimeError):
    """O livro do mês voltou com menos linhas do que a listagem do banco diz: não se grava por cima."""


# ── o tempo ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def _hora(v) -> str:
    """`AAAAMMDDHH` de uma hora que existe (mês 13 e hora 25 são recusados), ou ValueError. O banco às vezes devolve o inteiro
    com o ponto zero ("2026103010.0", como o ID do Fracttal no almoxarifado): é a mesma hora, e a chave não pode mudar por isso
    (a linha relida não casaria com a nova e a hora se repetiria)."""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip() if v is not None and not isinstance(v, bool) else ""
    if s.endswith(".0"):
        s = s[:-2]
    if len(s) != 10 or not s.isascii() or not s.isdigit():
        raise ValueError(f"hora_id fora da forma AAAAMMDDHH: {s[:20]!r}")
    datetime.strptime(s, "%Y%m%d%H")
    return s


def livro_do_mes(hora_id) -> str:
    """O livro do mês da hora (de Brasília): `nexus_oscreator_uso_2026_10`."""
    h = _hora(hora_id)
    return LIVRO_DO_MES.format(h[:4], h[4:6])


# ── uma linha ────────────────────────────────────────────────────────────────────────────────────────────────────────
def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _vazio(v) -> bool:
    return v is None or str(v).strip().lower() in ("", "none", "nan")      # o sync-xlsx real devolve a célula vazia como "None"


def _numero(v, estrito: bool):
    """O inteiro de 0 para cima, ou None. Estrito (a linha de quem chama): só int de verdade. Lenient (a que voltou do banco,
    que pode ser texto, "12.0" ou "None"): lê o texto e o ponto decimal."""
    if estrito:
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError(f"esperava um número inteiro de 0 para cima, veio {v!r}")
        return v
    if _vazio(v) or isinstance(v, bool):
        return None
    try:
        n = float(str(v).replace(",", ".")) if not isinstance(v, (int, float)) else float(v)
    except ValueError:
        return None
    return int(round(n)) if n == n and abs(n) != float("inf") else None


def _linha(d: dict, aba: str, estrito: bool) -> list:
    """A linha na ordem do cabeçalho. `estrito`: o que o contador entrega (qualquer defeito é ValueError de quem chama);
    senão o que voltou do banco (lê o texto, e a célula vazia segue vazia; só uma linha sem hora ou sem chave é erro)."""
    h = _hora(d.get("hora_id"))
    out = {"hora_id": int(h), "data_id": int(h[:8]), "hora": int(h[8:])}
    for col, tipo in _ESQUEMA[aba]:
        v = d.get(col)
        if tipo == "t":
            t = _txt(v)
            if estrito and (not t or t.lower() == "none"):
                raise ValueError(f"{col} vazio")
            out[col] = t
        elif tipo == "b":
            n = _numero(v, estrito)
            if n not in (0, 1):
                raise ValueError(f"{col} tem de ser 1 ou 0, veio {v!r}")
            out[col] = n
        else:
            if tipo == "n?" and (v is None if estrito else _vazio(v)):
                out[col] = None
                continue
            n = _numero(v, estrito)
            if n is None and not estrito:
                out[col] = None                               # número ilegível no banco: segue vazio, sem inventar
                continue
            out[col] = n
    return [out[c] for c in CABS[aba]]


def _chave(linha: list, aba: str) -> tuple:
    return tuple(linha[CABS[aba].index(c)] for c in CHAVES[aba])


def valida(d, aba: str) -> bool:
    """A linha, como o contador a entrega (e como o pendente em disco a guarda), tem a forma de `aba`? O pendente que volta
    do disco passa por aqui: uma linha ruim é ignorada, porque deixada no meio das boas faria `gravar` subir para sempre e
    ninguém mais gravaria. Na aba do detalhe a linha de total (`*` e `*`) vale; um `*` só na origem ou só no método, não."""
    try:
        if not isinstance(d, dict):
            return False
        if aba == ABA_FRACTTAL and (_txt(d.get("origem")) == TOTAL) != (_txt(d.get("metodo")) == TOTAL):
            return False
        _linha(d, aba, estrito=True)
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def separar_total(linhas) -> tuple:
    """`(o detalhe, os totais)` das linhas do contador do Fracttal. A linha de origem `*` e método `*` é o TOTAL da hora e vira
    uma linha de 1 por hora (`hora_id` e as quatro medidas); as outras são o detalhe, como vieram. Um `*` só na origem ou só
    no método é defeito de quem chama (ValueError): somaria o que não é total."""
    detalhe, totais = [], []
    for d in linhas or ():
        origem, metodo = _txt(d.get("origem")), _txt(d.get("metodo"))
        if origem == TOTAL and metodo == TOTAL:
            totais.append({c: d.get(c) for c in ("hora_id",) + _MEDIDAS_DO_TOTAL})
        elif TOTAL in (origem, metodo):
            raise ValueError(f"linha do Fracttal com {TOTAL} só na origem ou só no método: {origem!r} e {metodo!r}")
        else:
            detalhe.append(d)
    return detalhe, totais


# ── o grão ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def conferir_grao(linhas: list, aba: str) -> None:
    """Sobe `GraoDuplicado` se a chave da aba repete ou vem com alguma parte vazia: o fato não grava contando em dobro.
    `linhas`: os dicts que o contador entrega."""
    chave = CHAVES[aba]
    vistas, ruins = {}, {}
    for d in linhas:
        k = tuple(_txt(d.get(c)) for c in chave)
        vistas[k] = vistas.get(k, 0) + 1
    for k, n in vistas.items():
        if n > 1 or not all(k):
            ruins[k] = n
    if ruins:
        ex = "; ".join(f"{' | '.join(k) or '(vazio)'} ({n})" for k, n in list(ruins.items())[:5])
        raise GraoDuplicado(f"{aba}: a chave ({', '.join(chave)}) repete ou vem vazia em {sum(ruins.values())} linhas: {ex}")


# ── o livro no banco ─────────────────────────────────────────────────────────────────────────────────────────────────
def _listar(base: str, sessao) -> list:
    r = sessao.get(f"{base}/api/sheets", timeout=60)
    r.raise_for_status()
    return r.json()


def _ler_livro(base: str, sessao, livro: str, listagem: list | None = None, abas: tuple = ABAS) -> dict:
    """{aba: [linhas do banco, como dict]} das `abas` do livro do mês. Livro (ou aba) que ainda não existe é vazio. Cada aba
    lida é conferida com o `row_count` da listagem: leitura curta sobe `LeituraIncompleta`, e nada se grava por cima dela."""
    listadas = {x["sheet_name"]: x for x in (listagem if listagem is not None else _listar(base, sessao))
                if x.get("workbook_key") == livro}
    out = {}
    for aba in abas:
        x = listadas.get(aba)
        if x is None:
            out[aba] = []
            continue
        lidas = livros._linhas(base, sessao, x["id"])
        esperadas = livros._int(x.get("row_count"))
        if esperadas is not None and len(lidas) < esperadas:
            raise LeituraIncompleta(f"{livro}.{aba}: li {len(lidas)} linhas e o banco diz {esperadas}")
        out[aba] = lidas
    return out


def _mesclar(no_banco: list, novas: list, aba: str) -> list:
    """As linhas do banco com as novas por cima (mesma chave: vale a nova), em ordem. Uma linha do banco que não é nossa
    (sem hora, sem o 1 ou 0 do automático) sobe como ValueError: gravar por cima dela a esconderia."""
    por_chave = {}
    for d in no_banco:
        l = _linha(d, aba, estrito=False)
        por_chave[_chave(l, aba)] = l
    for l in novas:
        por_chave[_chave(l, aba)] = l
    return [por_chave[k] for k in sorted(por_chave)]


def gravar(linhas_uso: list, linhas_fracttal: list, *, base: str, token: str, sessao) -> dict:
    """Leva as linhas dos dois contadores (`uso_os.drenar` e `fracttal_conta.drenar`) ao livro do mês de cada hora.

    A linha de total do Fracttal (origem `*` e método `*`, que o contador entrega no meio do detalhe) vai para a aba
    `fato_fracttal_total_hora`, 1 linha por hora (`separar_total`); o detalhe, para a `fato_fracttal_hora`. Relê o livro do
    mês, troca as linhas de mesma chave e publica pelo `livros.publicar` (conferido antes, pela trava `so_cresce`, e depois,
    pela contagem de cada aba). As três abas vão sempre juntas (gravar o livro sem uma a apagaria). Lote que atravessa a
    virada do mês vai a dois livros, o mais velho primeiro. Chave repetida ou linha fora da forma sobe ANTES de qualquer
    pedido ao banco. Sem linha nenhuma, não toca no banco.

    Devolve `{"gravado": {livro: {aba: linhas no livro}}, "uso_qtd", "fracttal_qtd", "total_qtd"}`, só contagens."""
    detalhe, totais = separar_total(linhas_fracttal)
    cru = {ABA_USO: list(linhas_uso or ()), ABA_FRACTTAL: detalhe, ABA_TOTAL: totais}
    for aba, lista in cru.items():
        conferir_grao(lista, aba)
    novas = {aba: [_linha(d, aba, estrito=True) for d in lista] for aba, lista in cru.items()}
    por_livro: dict = {}
    for aba, lista in novas.items():
        for l in lista:
            por_livro.setdefault(livro_do_mes(l[0]), {a: [] for a in ABAS})[aba].append(l)
    gravado = {}
    for livro in sorted(por_livro):
        ano, mes = livro.rsplit("_", 2)[-2:]
        banco = _ler_livro(base, sessao, livro)
        tabelas = {aba: (list(CABS[aba]), _mesclar(banco[aba], por_livro[livro][aba], aba)) for aba in ABAS}
        gravado[livro] = livros.publicar(livro, NOME_DO_MES.format(ano, mes), tabelas, base=base, token=token,
                                         sessao=sessao)
    return {"gravado": gravado, "uso_qtd": len(novas[ABA_USO]), "fracttal_qtd": len(novas[ABA_FRACTTAL]),
            "total_qtd": len(novas[ABA_TOTAL])}


def ler_dias(base: str, sessao, hora_id, dias: int = 7, abas: tuple = (ABA_USO, ABA_TOTAL)) -> dict:
    """`{"uso": [...], "total": [...]}` dos últimos `dias` dias de Brasília (o dia de `hora_id` e os anteriores), lidos do
    livro de cada mês que a janela toca (a virada do mês lê dois). Só as `abas` pedidas: por padrão o uso e o total da hora,
    que é o que o Raio-X mostra; o detalhe do Fracttal é a aba maior do livro e fica de fora (com `abas=ABAS` vem junto, em
    "fracttal"). Cada linha é um dict com as colunas do fato, número como número e a célula vazia como None. Livro que ainda
    não existe é vazio. Falha de rede ou leitura curta sobe: quem mostra (o Raio-X) decide o que dizer."""
    h = _hora(hora_id)
    hoje = datetime.strptime(h[:8], "%Y%m%d")
    primeiro = hoje - timedelta(days=max(1, int(dias)) - 1)
    corte = int(primeiro.strftime("%Y%m%d") + "00")
    livros_do_periodo = sorted({livro_do_mes((primeiro + timedelta(days=i)).strftime("%Y%m%d") + "00")
                                for i in range((hoje - primeiro).days + 1)})
    listagem = _listar(base, sessao)
    out = {aba: [] for aba in abas}
    for livro in livros_do_periodo:
        for aba, linhas in _ler_livro(base, sessao, livro, listagem, abas).items():
            for d in linhas:
                l = _linha(d, aba, estrito=False)
                if l[0] >= corte:
                    out[aba].append(dict(zip(CABS[aba], l)))
    return {NOME_DA_ABA[aba]: out[aba] for aba in abas}
