"""Os projetos da FAMA em Base → Ligações entre bases (11/11/2026): o sistema `FAMA · Projetos` do de-para.

Cada projeto da FAMA é uma usina de um cliente que abre OS na FAMA (as OS do cliente pela FAMA, `nexus/dados/fama.py`).
A tela lê os projetos da `nexus_os_fama · dim_projeto_fama` do banco (`ligacoes.fontes`, no "Ler as bases de novo"): a
chave é o id do projeto na FAMA (o nome pode mudar lá; o id, não), e o nome vai no rótulo, que a seção mostra no lugar do
id. A FAMA só cobre os clientes que a usam: usina fora dela não é buraco (sem a aba "Usinas fora", `SEM_AUSENCIA`).

A proposta pelo nome NUNCA liga sozinha (`so_decisao`): o de-para põe a linha sem usina, "a decidir na tela"
(`banco.A_DECIDIR`), e a seção mostra a proposta como sugestão de um clique. Quem liga é o Levi, pelo `decidir` de sempre;
o fato das OS lê só a ligação decidida (`fato_os_fama.ligacao_decidida`). Levi, 11/11/2026: o Levi confirma cada ligação.

O normalizador é próprio da FAMA (`nome_fama`): o `project.name` vem com o número em romano ("Usina II"), e o cadastro e o
Fracttal chamam a mesma usina de "Usina 2" ou "<Cliente> - Usina 2 - UF". O `banco.norm` e o `ligacao_campo._norm` servem
ao de-para inteiro e aos fatos: mudá-los mudaria ligações que já existem (o pedido: não mudar o normalizador
compartilhado). Aqui: sem acento e sem caixa; a sigla do estado no fim cai (só as 27 UFs: "II" não é estado); do lado do
cadastro e do Fracttal, o cliente na frente também; "UFV" e as preposições caem; o romano vira arábico (I a XXXIX, só a
palavra inteira: "Vivi" e "Civil" ficam) e o zero à esquerda cai. A proposta é o nome IGUAL depois disso, contra o nome da
usina, o título "<Cliente> - <Usina>" e as chaves do Fracttal ligadas a ela; mais de uma usina, todas aparecem, nenhuma
com certeza (o mesmo nome em dois clientes).
"""
import re
import unicodedata

from ..dados import fato_os_fama as F
from . import casamento as K

SISTEMA = F.SISTEMA
UFS = frozenset("ac al ap am ba ce df es go ma mt ms mg pa pb pr pe pi rj rn rs ro rr sc sp se to".split())
_SEPARA = re.compile(r"\s+-\s*|\s*-\s+")
_ROMANO = re.compile(r"(x{0,3})(ix|iv|v?i{0,3})")
_VALOR = {"i": 1, "v": 5, "x": 10}
_FORA = frozenset({"ufv", "de", "do", "da", "dos", "das"})


def _qtd(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError, OverflowError):
        return None


def _romano(w: str) -> int | None:
    if not w or not _ROMANO.fullmatch(w):
        return None
    total = 0
    for a, b in zip(w, w[1:] + " "):
        v = _VALOR[a]
        total += -v if _VALOR.get(b, 0) > v else v
    return total


def nome_fama(s, *, tirar_cliente: bool = False) -> str:
    """O nome comparável: "Lagoa II" -> "lagoa 2"; com `tirar_cliente`, "Cliente - Lagoa 2 - RN" -> "lagoa 2"."""
    t = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    partes = [p for p in (x.strip() for x in _SEPARA.split(" ".join(t.split()))) if p]
    if len(partes) > 1 and partes[-1] in UFS:
        partes = partes[:-1]
    if tirar_cliente and len(partes) > 1:
        partes = partes[1:]
    out = []
    for w in re.findall(r"[a-z]+|\d+", " ".join(partes)):
        if w in _FORA:
            continue
        n = _romano(w)
        out.append(str(n) if n is not None else (str(int(w)) if w.isdigit() else w))
    return " ".join(out)


def itens(linhas_dim) -> list[dict]:
    """As chaves do sistema FAMA para o de-para, uma por projeto da `dim_projeto_fama` (o id da FAMA; "11.0" do banco é
    o 11), na ordem do id. `so_decisao`: só a decisão da tela liga; `propor`: a seção propõe pelo `nome_fama`."""
    out = {}
    for d in linhas_dim or ():
        pid = F.id_fama(d.get("fama_projeto_id"))
        if pid is None or str(pid) in out:
            continue
        nome = " ".join(str(d.get("nome") or "").split())
        out[str(pid)] = {"chave": str(pid), "nome": nome or None, "rotulo": nome or f"projeto {pid}",
                         "os": _qtd(d.get("os_qtd")), "so_decisao": True, "propor": "fama"}
    return [out[k] for k in sorted(out, key=lambda k: (0, int(k), "") if k.isdigit() else (1, 0, k))]


def indice(usinas: list[dict], fracttal_por_usina: dict | None = None) -> dict:
    """{nome comparável: {usina_id}}: o nome da usina, o título "<Cliente> - <Usina>" sem o cliente e as chaves do Fracttal
    ligadas a ela sem o cliente e a UF. `usinas` = `ligacoes._usinas`; `fracttal_por_usina` = {usina_id: [chave]}."""
    idx = {}
    for u in usinas:
        for n in (nome_fama(u.get("nome")), nome_fama(u.get("titulo"), tirar_cliente=True)):
            if n:
                idx.setdefault(n, set()).add(u["id"])
    for uid, chaves in (fracttal_por_usina or {}).items():
        for k in chaves:
            n = nome_fama(k, tirar_cliente=True)
            if n:
                idx.setdefault(n, set()).add(uid)
    return idx


def sugestoes(item: dict, idx: dict, por_id: dict, n: int = 3) -> list[dict]:
    """A proposta pelo nome de um projeto da FAMA: as usinas de nome igual pela régua da FAMA. Uma só = 100%; o mesmo nome
    em mais de uma usina, todas, divididas (quem escolhe é a pessoa).

    Sem o nome igual, a contenção de palavras (12/11/2026, `casamento.contencao`: "Pinhal I" é a "São Brás do Pinhal 1"),
    contra os mesmos nomes do índice. O projeto não diz o cliente, então a única contida vem abaixo de 100
    (`NOTA_CONTIDA_SEM_CLIENTE`): a pessoa confirma. Ligada a chave do Fracttal dessa usina, o índice a acha pelo nome
    igual, e aí sim a 100."""
    nome = nome_fama(item.get("nome"))
    ids = sorted(i for i in idx.get(nome, ()) if i in por_id)
    if ids:
        return [{"id": i, "titulo": por_id[i]["titulo"], "codigo": por_id[i]["codigo"], "nota": 100 // len(ids)}
                for i in ids][:n]
    t = K.termos(nome)
    ids = sorted({i for k, us in idx.items() if K.contencao(t, k) in K.CONTIDAS for i in us if i in por_id})
    nota = K.NOTA_CONTIDA_SEM_CLIENTE if len(ids) == 1 else K.NOTA_CONTIDA_VARIAS
    return [{"id": i, "titulo": por_id[i]["titulo"], "codigo": por_id[i]["codigo"], "nota": nota} for i in ids][:n]
