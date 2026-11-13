"""A documentação de segurança de cada colaborador (Segurança · HSEQ, 06/11/2026): ASO, NRs, integrações, anuências e
documentos, por pessoa do cadastro. O Nexus é a FONTE: a Segurança edita na tela Colaboradores e carrega a planilha que
usava até aqui ("Atualização de Ativos") pela própria tela.

O dado (livro `nexus_hseq_documentacao`, registrado em `nexus/hseq/catalogo.py` antes da 1ª gravação), só acrescenta:
`fato_documentacao`, 1 linha = 1 registro da situação de 1 item de documentação de 1 pessoa; vale o último de cada
(pessoa, item). Em claro: o `pessoa_id` do cadastro, o item (domínio, `ITENS`), a origem (tela ou planilha), o dia e o
código de quem registrou. A situação, a data e o nome de quem registrou vão só cifrados (regra 8: a API tem leitura
aberta, e o ASO é dado de saúde).

As regras que a Segurança deu (05/11/2026):
- OK = Válido; FALTA = Falta; ASSINATURA e SOLICITADO (ASSINATURA) = Pendente assinatura.
- A data é sempre no formato brasileiro (dd/mm/aaaa). "10/24/2026" não é data brasileira: não entra, e a conferência diz.
- A data das NRs é a de REALIZAÇÃO; a validade sai da periodicidade da norma (`Item.meses`). No ASO e na CNH a data já é
  a validade. Item sem periodicidade definida (NR-06, NR-12, NR-24, integrações, direção defensiva) não vence até a
  Segurança definir.
- Da aba de saúde, só a data do ASO; os exames não entram.
- "SOLICITADO" sozinho, "Não possui ASO no servidor" e "Falta enviar para assinatura" seguem a proposta enviada ao Levi
  (Solicitado, Falta e Pendente assinatura), até a Segurança confirmar.

Pessoa só pelo cadastro (`pessoa_id`): na planilha, o nome casa com o nome completo da ficha (sem acento nem caixa) ou,
se não casar, com o primeiro e o último nome quando eles são de UMA pessoa só. Nome que não casa ou casa com duas não
entra (nunca chutar ID, regra 4) e a conferência lista. Os terceiros (aba com a coluna EMPRESA) não estão no cadastro e
ficam fora até o Levi decidir.
"""
import io
import json
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from ..dados import fatos as D
from ..dados import livros
from . import decisoes as DEC

LIVRO, NOME_LIVRO = "nexus_hseq_documentacao", "Nexus · documentação de segurança dos colaboradores"
ABA = "fato_documentacao"
CAB = ("registrado_em", "data_id", "pessoa_id", "item", "origem", "registrado_por_hmac", "dados_cifrados")
ORIGENS = ("tela", "planilha")
TTL_S = 60
ALERTA_DIAS = 30                    # "vence em breve": a mesma régua dos extintores
LINHAS_MAX = 3000                   # linhas por aba da planilha (a de hoje tem 120)
COLUNAS_MAX = 60                    # a planilha tem aba com 16 mil colunas vazias: lê só as primeiras

SITUACOES = {"valido": "Válido", "falta": "Falta", "pendente_assinatura": "Pendente assinatura",
             "solicitado": "Solicitado", "nao_se_aplica": "Não se aplica"}
# o estado que a tela mostra (a situação + a validade), do mais grave para o menos; o tom é a cor do Nexus
ESTADOS = {"vencido": ("Vencido", "critico"), "falta": ("Falta", "critico"),
           "pendente_assinatura": ("Pendente assinatura", "alerta"), "solicitado": ("Solicitado", "alerta"),
           "vence_logo": ("Vence em breve", "alerta"), "valido": ("Válido", "ok"),
           "nao_se_aplica": ("Não se aplica", "neutro"), "sem_registro": ("Sem registro", "neutro")}
PENDENCIAS = ("vencido", "falta", "pendente_assinatura", "solicitado", "vence_logo")


@dataclass(frozen=True)
class Item:
    id: str
    rotulo: str
    tipo: str                       # realizacao (a data é a de realização), validade (a data é o vencimento), situacao
    meses: int | None = None        # a periodicidade da norma, só para `realizacao`
    colunas: tuple = field(default=())   # os cabeçalhos da planilha que viram este item (normalizados por `_cab`)
    norma: str = ""


ITENS = (
    Item("aso", "ASO", "validade", colunas=("ASO - VAL",), norma="a data é a validade (PCMSO, NR-07)"),
    Item("nr10", "NR-10 básico", "realizacao", 24, ("NR 10",), "reciclagem bienal (NR-10, 10.8.8.2)"),
    Item("nr10_sep", "NR-10 SEP", "realizacao", 24, ("NR 10 SEP",), "reciclagem bienal (NR-10)"),
    Item("nr35", "NR-35", "realizacao", 24, ("NR 35",), "treinamento periódico bienal (NR-35)"),
    Item("nr06", "NR-06", "realizacao", None, ("NR 06",), "sem prazo na norma: a definir"),
    Item("nr12", "NR-12", "realizacao", None, ("NR 12",), "reciclagem por mudança, sem prazo: a definir"),
    Item("nr24", "NR-24", "realizacao", None, ("NR 24",), "sem prazo na norma: a definir"),
    Item("direcao_defensiva", "Direção defensiva", "realizacao", None, ("DIRECAO DEFENSIVA",), "regra interna: a definir"),
    Item("integracao_grid", "Integração Grid", "realizacao", None, ("INTEGRACAO GRID",), "regra interna: a definir"),
    Item("integracao_cliente", "Integração cliente", "realizacao", None, ("INTEGRACAO CLIENTE",),
         "regra de cada cliente: a definir"),
    Item("anuencia_nr10", "Anuência NR-10", "situacao", colunas=("ANUENCIA 10",)),
    Item("anuencia_nr35", "Anuência NR-35", "situacao", colunas=("ANUENCIA 35",)),
    Item("ficha_epi", "Ficha de EPI", "situacao", colunas=("FICHA DE EPI",)),
    Item("ordem_servico", "Ordem de serviço (OS)", "situacao", colunas=("OS",)),
    Item("ficha_registro", "Ficha de registro", "situacao", colunas=("FICHA DE REGISTRO",)),
    Item("ctps", "CTPS", "situacao", colunas=("CTPS",)),
    Item("rg", "RG", "situacao", colunas=("RG",)),
    # a coluna CPF da planilha é o NÚMERO (não entra nunca); o documento é a CPF2 (na aba Demitidos, a "Coluna1")
    Item("cpf_doc", "CPF (documento)", "situacao", colunas=("CPF2", "COLUNA1")),
    Item("cnh", "CNH", "validade", colunas=("CNH",), norma="a data é a validade"),
    Item("cartao_vacina", "Cartão de vacina", "situacao", colunas=("CARTAO DE VACINA",)),
)
POR_ID = {i.id: i for i in ITENS}
_DATA_BR = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})$")
_TRAVA = threading.Lock()
_CACHE: dict = {}

Recusada = DEC.Recusada


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def _cab(s) -> str:
    """O cabeçalho da planilha comparável: sem acento, maiúsculo, um espaço só ("ASO -  Val" = "ASO - VAL")."""
    return _norm(s).upper()


# ── o valor da planilha ─────────────────────────────────────────────────────────────────────────────────────
def data_br(texto) -> date | None:
    """dd/mm/aaaa (ou aa). Formato brasileiro sempre: "10/24/2026" não é data (mês 24)."""
    m = _DATA_BR.match(str(texto or "").strip())
    if not m:
        return None
    d, mes, a = (int(x) for x in m.groups())
    try:
        return date(a + 2000 if a < 100 else a, mes, d)
    except ValueError:
        return None


def ler_valor(v) -> tuple[str, date | None] | None | bool:
    """(situação, data) de uma célula; None = célula vazia (nada a registrar); False = valor que o Nexus não reconhece
    (a conferência mostra, e ele não entra)."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return "valido", v.date()
    if isinstance(v, date):
        return "valido", v
    t = str(v).strip()
    if not t:
        return None
    if re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", t):
        d = data_br(t)
        return ("valido", d) if d else False
    n = _cab(t)
    if n == "OK":
        return "valido", None
    if n in ("NA", "N.A", "N.A.", "N/A", "-", "NAO SE APLICA"):
        return "nao_se_aplica", None
    if "ASSINA" in n or "D4SIGN" in n:
        return "pendente_assinatura", None
    if n in ("FALTA", "NAO POSSUI ASO NO SERVIDOR"):
        return "falta", None
    if n in ("SOLICITADO", "SOLICIDADO"):
        return "solicitado", None
    return False


# ── a situação de um item ───────────────────────────────────────────────────────────────────────────────────
def _somar_meses(d: date, meses: int) -> date:
    m = d.month - 1 + meses
    a, m = d.year + m // 12, m % 12 + 1
    for dia in (d.day, 30, 29, 28):
        try:
            return date(a, m, dia)
        except ValueError:
            continue
    return date(a, m, 28)


def validade(item: Item, situacao: str, d: date | None) -> date | None:
    if situacao != "valido" or not d:
        return None
    if item.tipo == "validade":
        return d
    if item.tipo == "realizacao" and item.meses:
        return _somar_meses(d, item.meses)
    return None


def estado(item: Item, reg: dict | None, hoje: date) -> dict:
    """{estado, vence, dias}: o que a tela mostra de UM item de UMA pessoa."""
    if not reg:
        return {"estado": "sem_registro", "vence": None, "dias": None}
    vence = validade(item, reg["situacao"], reg.get("data"))
    if reg["situacao"] != "valido":
        return {"estado": reg["situacao"], "vence": None, "dias": None}
    if vence is None:
        return {"estado": "valido", "vence": None, "dias": None}
    dias = (vence - hoje).days
    return {"estado": "vencido" if dias < 0 else ("vence_logo" if dias <= ALERTA_DIAS else "valido"),
            "vence": vence, "dias": dias}


def ficha(registros: dict | None, hoje: date) -> list[dict]:
    """Os itens de UMA pessoa, na ordem de `ITENS`, com o registro e o estado."""
    out = []
    for i in ITENS:
        reg = (registros or {}).get(i.id)
        out.append({"item": i, "reg": reg, **estado(i, reg, hoje)})
    return out


def resumo(registros: dict | None, hoje: date) -> dict:
    """{estado: quantos} de UMA pessoa e o pior estado (o primeiro de `ESTADOS` que ela tem, fora o sem registro)."""
    c = {e: 0 for e in ESTADOS}
    for x in ficha(registros, hoje):
        c[x["estado"]] += 1
    pior = next((e for e in PENDENCIAS if c[e]), "valido" if c["valido"] else "sem_registro")
    return {"contagem": c, "pior": pior, "pendencias": sum(c[e] for e in PENDENCIAS),
            "registrados": len(ITENS) - c["sem_registro"]}


# ── ler o livro ─────────────────────────────────────────────────────────────────────────────────────────────
def _arquivo_local(cfg) -> Path | None:
    p = cfg.get("NEXUS_HSEQ_DOCUMENTACAO_ARQUIVO")
    return Path(p) if p else None


def _ler_cru(cfg) -> list[dict]:
    loc = _arquivo_local(cfg)
    if loc is not None:
        try:
            return [dict(x) for x in json.loads(loc.read_text(encoding="utf-8")).get(ABA) or []]
        except FileNotFoundError:
            return []
    if cfg.get("TESTING"):
        return []
    from ..pcm.motivos import _banco
    base, sessao = _banco(cfg)
    a = livros.abas(base, sessao, LIVRO)
    return list(livros._linhas(base, sessao, a[ABA])) if ABA in a else []


def _ctx(pessoa_id, item, quando) -> str:
    return f"hseq/documentacao/{pessoa_id}/{item}/{quando}"


def _estado(cfg, cru: list[dict]) -> dict:
    """{pessoa_id: {item: {situacao, data, registrado_em, origem}}}: o último registro de cada (pessoa, item). Linha que
    não abre (outra chave, mexida) ou com item/situação fora do domínio não conta."""
    cofre = DEC._cofre(cfg)
    out: dict = {}
    for x in DEC._ordem(cru):
        pid, item, quando = D._id(x.get("pessoa_id")), D._txt(x.get("item")), D._txt(x.get("registrado_em"))
        if not pid or item not in POR_ID:
            continue
        dados = DEC._decifrar(cofre, x, _ctx(pid, item, quando))
        if dados.get("situacao") not in SITUACOES:
            continue
        d = DEC._dia(dados.get("data")) if dados.get("data") else None
        out.setdefault(pid, {})[item] = {"situacao": dados["situacao"], "data": d, "registrado_em": quando,
                                         "origem": D._txt(x.get("origem"))}
    return out


def ler(cfg, forcar: bool = False) -> dict:
    """{"pessoas": {pessoa_id: {item: registro}}, "linhas", "erro", "lido_em"}, guardado por 1 minuto. Sem a chave do
    cadastro, nenhuma situação abre (e a tela diz)."""
    chave = str(_arquivo_local(cfg) or "banco")
    g = _CACHE.get(chave)
    if g and not forcar and time.time() - g["lido_em"] < TTL_S:
        return g
    try:
        cru = _ler_cru(cfg)
    except Exception as ex:  # noqa: BLE001 — banco fora, rede: a tela diz
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        return dict(g, erro=erro, velha=True) if g else {"pessoas": {}, "linhas": 0, "erro": erro, "lido_em": None}
    g = {"pessoas": _estado(cfg, cru), "linhas": len(cru), "erro": "", "lido_em": time.time()}
    _CACHE[chave] = g
    return g


def limpar() -> None:
    _CACHE.clear()


# ── gravar ──────────────────────────────────────────────────────────────────────────────────────────────────
def _gravar_cru(cfg, cru: list[dict]) -> None:
    """Troca o livro inteiro e confere (`livros.publicar` relê e compara; o livro só cresce). Na cópia de prova, o
    arquivo."""
    vazio = (lambda v: None if v in ("", None) else v)      # noqa: E731
    tabelas = {ABA: (list(CAB), [[vazio(x.get(c)) for c in CAB] for x in cru])}
    loc = _arquivo_local(cfg)
    if loc is not None:
        loc.parent.mkdir(parents=True, exist_ok=True)
        tmp = loc.with_suffix(".tmp")
        tmp.write_text(json.dumps({ABA: [dict(zip(CAB, l)) for l in tabelas[ABA][1]]}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(loc)
        return
    token = cfg.get("GRIDCO_SQL_TOKEN")
    if not token:
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN): nada foi gravado.")
    from ..pcm.motivos import _banco
    base, sessao = _banco(cfg)
    livros.publicar(LIVRO, NOME_LIVRO, tabelas, base=base, token=token, sessao=sessao)


def _acrescentar(cfg, novos: list[tuple], origem: str, usuario: dict | None) -> int:
    """Grava os registros [(pessoa_id, item, situacao, data)] de uma vez, relendo o livro antes (leitura que falha não
    grava). Só o que muda o último registro da pessoa entra: a mesma planilha carregada duas vezes não grava nada."""
    if origem not in ORIGENS:
        raise Recusada("Origem que o Nexus não conhece.")
    cofre = DEC._cofre(cfg)
    if cofre is None:
        raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): a situação vai cifrada, e sem "
                       "ela nada é gravado.")
    codigo, nome = DEC._quem(cfg, usuario)
    agora = DEC._agora()
    quando = agora.isoformat(timespec="seconds")
    with _TRAVA:
        try:
            cru = _ler_cru(cfg)
        except Exception as ex:  # noqa: BLE001
            raise Recusada(f"Não consegui ler a documentação no banco ({type(ex).__name__}): nada foi gravado, para não "
                           "apagar o que já está lá.") from ex
        atual = _estado(cfg, cru)
        linhas = []
        for pid, item, sit, d in novos:
            reg = (atual.get(pid) or {}).get(item)
            if reg and reg["situacao"] == sit and reg.get("data") == d:
                continue
            dados = {"situacao": sit, "data": d.isoformat() if d else "", "quem": nome}
            linhas.append({"registrado_em": quando, "data_id": int(agora.strftime("%Y%m%d")), "pessoa_id": pid,
                           "item": item, "origem": origem, "registrado_por_hmac": codigo,
                           "dados_cifrados": cofre.cifrar(json.dumps(dados, ensure_ascii=False),
                                                          _ctx(pid, item, quando))})
            (atual.setdefault(pid, {}))[item] = {"situacao": sit, "data": d}
        if linhas:
            cru = cru + linhas
            _gravar_cru(cfg, cru)
        _CACHE[str(_arquivo_local(cfg) or "banco")] = {"pessoas": _estado(cfg, cru), "linhas": len(cru), "erro": "",
                                                       "lido_em": time.time()}
    return len(linhas)


def registrar(cfg, *, pessoa_id: int, item: str, situacao: str, data_txt: str, usuario: dict | None, pode: bool) -> str:
    """Um item de uma pessoa, pela tela. A data vem do campo de data do navegador (aaaa-mm-dd) ou digitada (dd/mm/aaaa)."""
    if not pode:
        raise Recusada("Só quem é da Segurança ou administrador edita a documentação.")
    i = POR_ID.get(item)
    if not i:
        raise Recusada("Item que o Nexus não conhece.")
    if situacao not in SITUACOES:
        raise Recusada("Situação que o Nexus não conhece: escolha uma da lista.")
    t = str(data_txt or "").strip()
    d = None
    if t:
        d = DEC._dia(t) if re.match(r"^\d{4}-\d{2}-\d{2}$", t) else data_br(t)
        if not d:
            raise Recusada("Data que o Nexus não entende: use dd/mm/aaaa.")
    if situacao != "valido":
        d = None                    # só o válido tem data (a de realização ou a validade)
    elif i.tipo == "validade" and not d:
        raise Recusada(f"{i.rotulo} válido precisa da data de validade.")
    n = _acrescentar(cfg, [(int(pessoa_id), item, situacao, d)], "tela", usuario)
    return f"{i.rotulo}: {SITUACOES[situacao].lower()}" + (f" ({d.strftime('%d/%m/%Y')})" if d else "") + (
        "." if n else " (já estava assim; nada mudou).")


# ── a planilha ──────────────────────────────────────────────────────────────────────────────────────────────
def _indice(pessoas: list[dict]) -> tuple[dict, dict]:
    """({nome completo normalizado: [pessoa_id]}, {primeiro + último nome: [pessoa_id]}) das fichas com nome."""
    completo, curto = {}, {}
    for p in pessoas:
        if not p.get("com_nome"):
            continue
        n = _norm(p["nome"])
        completo.setdefault(n, []).append(p["pessoa_id"])
        partes = n.split()
        if len(partes) >= 2:
            curto.setdefault(f"{partes[0]} {partes[-1]}", []).append(p["pessoa_id"])
    return completo, curto


def casar(nome, indice) -> tuple[int | None, str]:
    """(pessoa_id, como casou) ou (None, por quê). Nunca chuta: duas fichas com o mesmo nome não casam."""
    completo, curto = indice
    n = _norm(nome)
    ids = completo.get(n) or []
    if len(ids) == 1:
        return ids[0], "nome completo"
    if len(ids) > 1:
        return None, "nome de mais de uma ficha"
    partes = n.split()
    ids = curto.get(f"{partes[0]} {partes[-1]}") if len(partes) >= 2 else None
    if ids and len(ids) == 1:
        return ids[0], "primeiro e último nome"
    return None, "nome de mais de uma ficha" if ids else "não está no cadastro"


def ler_planilha(conteudo: bytes, pessoas: list[dict]) -> dict:
    """A conferência da planilha, sem gravar: o que entraria (`registros`), quem não casou com o cadastro, os valores que
    o Nexus não reconhece e o que ficou de fora (terceiros, abas sem a coluna FUNCIONARIO). Os nomes da planilha só
    servem para casar, na memória; nada além do `pessoa_id` sai daqui para o banco."""
    from openpyxl import load_workbook
    try:
        wb = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    except Exception as ex:  # noqa: BLE001 — arquivo que não é xlsx
        raise Recusada(f"Não consegui abrir a planilha ({type(ex).__name__}): envie o arquivo .xlsx.") from ex
    indice = _indice(pessoas)
    por_col = {c: i for i in ITENS for c in i.colunas}
    candidatos: dict = {}           # (pid, item) -> [(data ou mínimo, ordem da aba, situacao, data)]
    abas, fora, nao_casou, desconhecidos, aproximados = [], [], {}, {}, {}
    nome_da_ficha = {p["pessoa_id"]: p["nome"] for p in pessoas}
    for ordem, ws in enumerate(wb.worksheets):
        linhas = ws.iter_rows(max_col=COLUNAS_MAX, max_row=LINHAS_MAX, values_only=True)
        cab = [_cab(c) for c in (next(linhas, None) or ())]
        if "FUNCIONARIO" not in cab:
            fora.append((ws.title.strip(), "sem a coluna FUNCIONARIO"))
            continue
        if "EMPRESA" in cab:
            fora.append((ws.title.strip(), "terceiros: não estão no cadastro (decisão do Levi)"))
            continue
        i_nome = cab.index("FUNCIONARIO")
        cols = [(j, por_col[c]) for j, c in enumerate(cab) if c in por_col]
        lidas = casadas = 0
        for r in linhas:
            nome = str(r[i_nome] or "").strip() if i_nome < len(r) else ""
            if not nome:
                continue
            lidas += 1
            pid, como = casar(nome, indice)
            if not pid:
                nao_casou[" ".join(nome.split())] = como
                continue
            casadas += 1
            if como != "nome completo":
                aproximados[" ".join(nome.split())] = nome_da_ficha.get(pid, "")
            for j, item in cols:
                v = ler_valor(r[j] if j < len(r) else None)
                if v is None:
                    continue
                if v is False:
                    k = (ws.title.strip(), item.rotulo, str(r[j]).strip())
                    desconhecidos[k] = desconhecidos.get(k, 0) + 1
                    continue
                sit, d = v
                if item.tipo == "situacao":
                    d = None        # documento sem validade: a data da planilha (quando houver) é só o "tem"
                candidatos.setdefault((pid, item.id), []).append((d or date.min, -ordem, sit, d))
        abas.append({"aba": ws.title.strip(), "pessoas": lidas, "casadas": casadas, "itens": len(cols)})
    # a mesma pessoa em duas abas (o ASO na aba de saúde e na de ativos): vale a data mais nova; sem data, a 1ª aba
    registros = [(pid, item, *max(c, key=lambda t: (t[0], t[1]))[2:]) for (pid, item), c in sorted(candidatos.items())]
    return {"abas": abas, "fora": fora, "nao_casou": sorted(nao_casou.items()), "aproximados": sorted(aproximados.items()),
            "desconhecidos": sorted(((a, i, v, n) for (a, i, v), n in desconhecidos.items()), key=lambda t: -t[3]),
            "registros": registros, "pessoas": len({r[0] for r in registros})}


def mudancas(cfg, registros: list[tuple]) -> int:
    """Quantos registros da planilha mudam o que o Nexus já tem (os que a gravação acrescentaria)."""
    atual = ler(cfg, forcar=True)["pessoas"]
    return sum(1 for pid, item, sit, d in registros
               if not ((r := (atual.get(pid) or {}).get(item)) and r["situacao"] == sit and r.get("data") == d))


def carregar_planilha(cfg, registros: list[tuple], usuario: dict | None, pode: bool) -> int:
    if not pode:
        raise Recusada("Só quem é da Segurança ou administrador carrega a planilha.")
    if not registros:
        raise Recusada("A planilha não tem nenhum registro de pessoa do cadastro: nada foi gravado.")
    return _acrescentar(cfg, registros, "planilha", usuario)
