# os_creator/os_web/investigar_web.py
"""As regras do "Investigar ativo" (26/10/2026), puras, sem Flask e sem rede.

Levi, 26/10/2026: "Gostaria de poder clicar com botão direito do mouse em cima do inversor e ter a opção 'Investigar
ativo'. Vai aproveitar o pré carregamento de histórico de OS do OS Creator filtrando esse ativo, deve mostrar o período
filtrado e eu devo conseguir fazer novos filtros e pesquisas pela visão."

- O ATIVO sai do catálogo de ativos que já está no disco (`api._catalogo_cru`), nunca do Fracttal: pelo código que a
  plataforma manda (o gravado no de-para ou o derivado do nome, `_frac_inv_code`) e, sem ele no catálogo, pelo número do
  inversor dentro da usina (a regra do `aplicarSugestao` do perf.js, a mesma do Criar OS). O derivado erra onde a árvore
  do Fracttal mudou (na Pharma II ele dá THPN-PHS200-INVR1.1 e o Fracttal tem THPN-PHS100-INVR2.1): o código que não
  existe no catálogo não vira "nenhuma OS", vira o aviso e a procura pelo nome.
- As OS saem da lista do Histórico que a Visão COS já carrega (`rotas.ler_lista`, "Todos", 30 dias): o período DENTRO
  desses 30 dias é recortado dela, sem pedido nenhum; fora deles, a lista daquele período (a mesma régua do Histórico,
  guardada para quem vier depois).
- A OS é "do ativo" quando o código dele está entre os itens dela (`codigos` da linha, `api._extrai_codigos`: a OS
  agrupada de dois inversores aparece nos dois); "da usina" pelo nome curto da usina, o mesmo do Histórico.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata

DIAS_PADRAO = 30                       # o período do Histórico (e da Visão COS): é a lista que já está carregada
SUFIXO_INVERSOR = "INVR"               # chamado_garantia.ativos.TIPO_POR_SUFIXO: INVR → Inversor


def _norm(t) -> str:
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", t).strip().lower()


def usina_curta(usina_full: str) -> str:
    """'Thopen - Ceilândia 1 - DF' → 'Ceilândia 1' (a mesma régua do `api._usina_curta`, que dá o nome da usina de cada
    linha do Histórico). Repetida aqui para estas regras rodarem sem o api.py."""
    partes = [p.strip() for p in str(usina_full or "").split(" - ") if p.strip()]
    if len(partes) <= 1:
        return str(usina_full or "").strip()
    partes = partes[1:]
    if len(partes) > 1 and len(partes[-1]) == 2 and partes[-1].isalpha():
        partes = partes[:-1]
    return " - ".join(partes)


def _sem_zero(n: str) -> str:
    return ".".join(str(int(p)) for p in n.split("."))


def numero(texto) -> str:
    """O número do inversor no NOME, sem zero à esquerda: 'Inversor 01.02' → '1.2', 'Inversor 1.1 (UG 02)' → '1.1'. O
    N.M vale mais que o número solto, como no `_frac_inv_code` da plataforma (o derivado "INVR{N.M}")."""
    t = str(texto or "")
    m = re.search(r"\d+\.\d+", t) or re.search(r"\d+", t)
    return _sem_zero(m.group(0)) if m else ""


def numero_do_codigo(code) -> str:
    """O número do inversor no CÓDIGO, só no último segmento: 'THPN-CGH100-INVR1.10' → '1.10' (o 100 é da usina)."""
    partes = str(code or "").split("-")
    m = re.search(r"\d+(?:\.\d+)?", partes[-1]) if len(partes) >= 2 else None
    return _sem_zero(m.group(0)) if m else ""


def _sufixo(code: str) -> str:
    partes = str(code or "").split("-")
    return "".join(c for c in partes[-1] if c.isalpha()) if len(partes) >= 2 else ""


def _do_registro(a: dict, como: str, aviso: str = "") -> dict:
    nome = (str(a.get("description") or "").split("{")[0]).strip()
    return {"code": str(a.get("code") or "").strip(), "nome": nome or str(a.get("code") or ""),
            "cliente": str(a.get("cliente") or ""), "usina": str(a.get("usina") or ""),
            "usina_curta": usina_curta(a.get("usina") or ""), "como": como, "aviso": aviso}


def resolver(catalogo, codigo: str = "", usina: str = "", nome: str = "") -> dict:
    """O ativo a investigar: {code, nome, cliente, usina, usina_curta, como, aviso}. `como`: "codigo" (achado pelo código
    que veio), "nome" (pelo número do inversor na usina), "" (não achei o ativo; com `usina_curta`, a usina foi achada)."""
    cod = str(codigo or "").strip()
    vazio = {"code": "", "nome": str(nome or "").strip(), "cliente": "", "usina": "", "usina_curta": "", "como": "",
             "aviso": ""}
    catalogo = [a for a in (catalogo or []) if isinstance(a, dict)]
    if cod:
        alvo = cod.upper()
        for a in catalogo:
            if str(a.get("code") or "").strip().upper() == alvo:
                return _do_registro(a, "codigo")
    # a usina: o nome inteiro do Fracttal ('Thopen - Inhapi 1 - AL', o que o de-para da plataforma manda) ou o curto
    u, uc = _norm(usina), _norm(usina_curta(usina))
    da_usina = [a for a in catalogo if u and (_norm(a.get("usina")) == u or _norm(usina_curta(a.get("usina"))) in (u, uc))]
    sem_cod = (f"O código {cod} não está no catálogo de ativos do OS Creator" if cod
               else "A plataforma não mandou o código do Fracttal deste inversor")
    n = numero(nome)
    if da_usina and n:
        invs = [a for a in da_usina if _sufixo(a.get("code")) == SUFIXO_INVERSOR and numero_do_codigo(a.get("code")) == n]
        if len(invs) == 1:
            return _do_registro(invs[0], "nome", sem_cod + f": achei o inversor {n} da usina pelo nome. Confira o "
                                                           "código abaixo.")
        if len(invs) > 1:
            vazio["aviso"] = (sem_cod + f", e a usina tem {len(invs)} inversores {n} "
                              f"({', '.join(str(a.get('code')) for a in invs[:4])}): abaixo, as OS da usina inteira.")
    if da_usina:
        a = da_usina[0]
        vazio.update(cliente=str(a.get("cliente") or ""), usina=str(a.get("usina") or ""),
                     usina_curta=usina_curta(a.get("usina") or ""))
        if not vazio["aviso"]:
            vazio["aviso"] = (sem_cod + (f", e não achei o inversor {n} nesta usina" if n else "")
                              + ": abaixo, as OS da usina inteira.")
        return vazio
    vazio["aviso"] = sem_cod + (f" e não achei a usina {usina} no catálogo." if usina else ".")
    return vazio


def do_ativo(linha: dict, code: str) -> bool:
    """A OS é deste ativo: o código dele está entre os itens dela (a OS de várias tarefas tem vários)."""
    alvo = str(code or "").strip().upper()
    return bool(alvo) and any(str(c or "").strip().upper() == alvo for c in (linha.get("codigos") or []))


def da_usina(linha: dict, usina_curta_: str) -> bool:
    return bool(usina_curta_) and _norm(linha.get("usina")) == _norm(usina_curta_)


def _data(v):
    try:
        return dt.date.fromisoformat(str(v or "")[:10])
    except ValueError:
        return None


def periodo(de, ate, hoje: dt.date) -> tuple[str, str, str]:
    """(de, ate, aviso) em 'AAAA-MM-DD'. Sem data (ou torta), o padrão do Histórico: os últimos 30 dias, que é a lista que
    já está carregada. Invertido, troca; no futuro, para em hoje."""
    padrao_de, padrao_ate = hoje - dt.timedelta(days=DIAS_PADRAO), hoje
    d, a = _data(de) or padrao_de, _data(ate) or padrao_ate
    aviso = ""
    if a > hoje:
        a = hoje
    if d > a:
        d, a = a, d
        aviso = "O início vinha depois do fim: troquei as datas."
    return d.isoformat(), a.isoformat(), aviso


def janela_carregada(de: str, ate: str, hoje: dt.date) -> tuple[str, str] | None:
    """O período da lista JÁ carregada (os 30 dias do Histórico) quando [de, ate] cabe nele: aí as OS são recortadas
    dela, sem ir ao Fracttal. None = o período sai dele (a lista daquele período, como no Histórico)."""
    padrao_de, padrao_ate = (hoje - dt.timedelta(days=DIAS_PADRAO)).isoformat(), hoje.isoformat()
    return (padrao_de, padrao_ate) if padrao_de <= de and ate <= padrao_ate else None


def no_periodo(linha: dict, de: str, ate: str) -> bool:
    """Pela data de CRIAÇÃO, como o período do Histórico (o filtro do Fracttal é no creation_date)."""
    d = str(linha.get("data") or "")[:10]
    return bool(d) and de <= d <= ate
