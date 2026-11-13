"""Quem instalou o Nexus Field (13/11/2026). Levi, pela sessão Nexus Field: "conseguimos saber que já instalou o nexus field
e logou sem eu ter que ficar cadastrando?" ("Pede"). O caso: um técnico do piloto da localização ficou parado numa
versão antiga, e só se soube perguntando.

A fonte é o App de Campo (a v354, o contrato que a sessão do App mandou em 13/11/2026): a tabela dos aparelhos que a
casca registra a cada abertura com login, para os avisos (a `pushaparelhos`), publicada de hora em hora, aos :25, com
troca integral (o livro vazio não sobe), no livro `aparelhos_nexus_field_app_campo · Aparelhos` (catálogo: o fato
`aparelho_field`). 1 linha = 1 aparelho de 1 pessoa; a pessoa vem como o código do e-mail (HMAC com a
NEXUS_PESSOA_HMAC, o mesmo das outras colunas "(HMAC)" do App), sem e-mail nem o token do FCM. As colunas se leem pelo
NOME (a coluna nova do App entra no fim).

Quem não aparece não abriu o Nexus Field com login: o App pelo navegador não se registra, e o celular sem os serviços do
Google (sem FCM) também não (a tela diz isso).

A "versão atual" é a mais nova que algum aparelho tem: nenhum número fixo no código. Quando o 1º celular abrir com a
versão nova, quem ficou na de antes passa a "versão antiga". Por pessoa vale o aparelho do último acesso (o que ela usa).
"""
import re
from datetime import datetime, timedelta, timezone

LIVRO, ABA = "aparelhos_nexus_field_app_campo", "Aparelhos"
C_PESSOA, C_APARELHO, C_VERSAO = "Pessoa (HMAC)", "Aparelho", "Versão do Nexus Field"
C_INSTALADO, C_ACESSO = "Instalado em", "Último acesso"
_BRT = timezone(timedelta(hours=-3))
_HMAC = re.compile(r"[0-9a-f]{24}")
# A versão chega como o agente da casca, "NexusField/1.2.4", e a de teste como "NexusField/1.2.0-rc.1" (o 1º livro,
# 13/11/2026 11:25). Até ali a conta só lia "1.2.4" e "v1.2.4": nenhuma versão se lia, a "versão atual" ficava vazia e
# ninguém aparecia como "versão antiga", que é o caso que criou a coluna. O nome antes da barra sai; a prévia (o "-rc.1")
# fica abaixo da mesma versão sem ela e acima da anterior.
_VERSAO = re.compile(r"(?:[A-Za-z][\w. -]*/)?v?(\d{1,4}(?:\.\d{1,4}){0,3})(?:-([0-9A-Za-z][0-9A-Za-z.-]*))?")
# o filtro da tela (Base → Acessos → Pessoas e setores): o valor de cada linha e o rótulo
FILTRO = (("instalou", "Instalou"), ("antiga", "Versão antiga"), ("nao_instalou", "Não instalou"))


def _partes(texto) -> tuple | None:
    """("NexusField/1.2.0-rc.1") -> ([1, 2, 0], "rc.1"); o que não é versão -> None."""
    m = _VERSAO.fullmatch(str(texto or "").strip())
    return ([int(p) for p in m.group(1).split(".")], m.group(2) or "") if m else None


def versao(texto) -> tuple | None:
    """ "1.2.4", "v1.2.4" ou "NexusField/1.2.4" -> a chave que se compara número a número (1.2.10 > 1.2.9); a prévia
    ("1.2.0-rc.1") fica abaixo da mesma versão sem ela. O que não é versão -> None (não entra na conta da versão atual)."""
    p = _partes(texto)
    if not p:
        return None
    nums, pre = p
    nums = (nums + [0, 0, 0, 0])[:4]
    if not pre:
        return (*nums, 1, 0)
    n = re.findall(r"\d+", pre)
    return (*nums, 0, int(n[-1]) if n else 0)


def rotulo(texto) -> str:
    """A versão como a tela mostra: sem o nome do app ("NexusField/1.2.4" -> "1.2.4"), com a prévia quando há
    ("1.2.0-rc.1"). O que não se lê fica como veio."""
    p = _partes(texto)
    if not p:
        return str(texto or "").strip()
    nums, pre = p
    return ".".join(map(str, nums)) + (f"-{pre}" if pre else "")


def _quando(iso) -> datetime | None:
    """O instante do App (ISO em UTC; sem fuso, UTC) no horário de Brasília."""
    s = str(iso or "").strip().replace("Z", "+00:00")
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(_BRT)


def resumo(linhas) -> dict:
    """{"por_pessoa": {código: {...}}, "versao_atual": "1.2.4" | ""}. Por pessoa: o aparelho do último acesso
    (`versao`, `modelo`, `acesso`, `acesso_txt`, `instalado_txt`), `n` aparelhos, `antiga` (a versão abaixo da atual) e
    `outros` (os outros aparelhos, do mais recente ao mais velho). A linha sem o código da pessoa não entra."""
    por: dict[str, list[dict]] = {}
    for r in linhas or []:
        h = str(r.get(C_PESSOA) or "").strip().lower()
        if not _HMAC.fullmatch(h):
            continue
        v = str(r.get(C_VERSAO) or "").strip()
        por.setdefault(h, []).append({"versao": rotulo(v), "v": versao(v),
                                      "modelo": " ".join(str(r.get(C_APARELHO) or "").split()),
                                      "acesso": _quando(r.get(C_ACESSO)), "instalado": _quando(r.get(C_INSTALADO))})
    mais_nova = max(((a["v"], a["versao"]) for ap in por.values() for a in ap if a["v"]), default=None)
    atual = mais_nova[0] if mais_nova else None
    out = {}
    for h, ap in por.items():
        ap.sort(key=lambda a: a["acesso"] or datetime.min.replace(tzinfo=_BRT), reverse=True)
        a = ap[0]
        out[h] = {"versao": a["versao"], "modelo": a["modelo"], "acesso": a["acesso"],
                  "acesso_txt": a["acesso"].strftime("%d/%m/%Y %H:%M") if a["acesso"] else "",
                  "instalado_txt": a["instalado"].strftime("%d/%m/%Y") if a["instalado"] else "",
                  "n": len(ap), "antiga": bool(atual and a["v"] and a["v"] < atual),
                  "outros": [{"versao": o["versao"], "modelo": o["modelo"],
                              "acesso_txt": o["acesso"].strftime("%d/%m/%Y %H:%M") if o["acesso"] else ""}
                             for o in ap[1:]]}
    return {"por_pessoa": out, "versao_atual": mais_nova[1] if mais_nova else ""}


def ler() -> dict:
    """O resumo do livro do App, pela cópia de 2 minutos dos livros do Campo (`visao._livro`), com `erro` e `existe`
    (False = o App ainda não publicou: o livro que não existe é lido vazio). A leitura que falha não derruba a tela."""
    from . import visao
    try:
        linhas = visao._livro(LIVRO, ABA)
    except Exception as ex:      # noqa: BLE001 — o banco fora: a coluna diz e a tela segue
        return {"por_pessoa": {}, "versao_atual": "", "existe": False, "erro": type(ex).__name__}
    return dict(resumo(linhas), existe=bool(linhas), erro="")


def da_pessoa(dados: dict, codigo: str | None) -> dict:
    """O que a coluna e o filtro de uma linha mostram: {"tem", "info", "filtro"} (`filtro`: os valores do FILTRO que a
    linha atende, separados por "|", como o filtro-local.js lê)."""
    info = (dados.get("por_pessoa") or {}).get((codigo or "").lower()) if codigo else None
    if not info:
        return {"tem": False, "info": None, "filtro": "nao_instalou"}
    return {"tem": True, "info": info, "filtro": "instalou|antiga" if info["antiga"] else "instalou"}
