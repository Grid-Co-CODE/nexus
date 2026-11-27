"""O Guia do App de Campo (21/11/2026): as perguntas que o Levi recebe sempre, cada uma com as telas do App e as regras.

Levi, pelo chat do App de Campo: "guia do app de campo. E pode ficar no Usina 360 com nova sessão mesmo [...] Então, como
funciona o almoxarifado no Nexus? Aí vai aparecer as telas e vai aparecer todas as regras ali embaixo"; "se o tema do
Nexus estiver claro, vai aparecer o tema claro do celular; se estiver escuro, o tema escuro do celular". Em 22/11: a busca
no alto, a separação por tema e o texto curto, "para quem tem pouco tempo, porém busca entender".

Quem faz o quê: o CONTEÚDO é do App de Campo (o pacote `guia-app-campo`: `guia.json` e um telefone por arquivo em
`telas/`, gerados pelo `_fonte/montar_guia.py` de lá); a TELA é do Nexus. O pacote é copiado para `nexus/static/guia-app/`
(o repositório é público: as telas usam nomes fictícios). Cada tela do telefone aceita `?tema=claro|escuro` e a mensagem
`postMessage({tipo: 'tema', tema})`, e a página do Nexus manda as duas (static/guia-app.js).

O `guia.json` (versão 1): `perguntas` com `id`, `titulo`, `tema`, `publico`, `resumo` (as frases curtas que a tela
mostra), `regras` (a fonte entre colchetes no fim), `casos`, `incerto` (o que o PCM precisa conferir: só o administrador e
o PCM veem) e `telas` (`arquivo`, `legenda`). A `resposta` existe no arquivo, mas a tela não mostra (repetia o resumo)."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

PASTA = Path(__file__).resolve().parents[1] / "static" / "guia-app"
ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,40}")
ARQ_RE = re.compile(r"telas/[a-z0-9][a-z0-9-]{0,60}\.(html|png)")
# o print do App em PNG (27/11/2026, Levi: "peça fotos novas para o app de campo"): o `arquivo` é o escuro e o
# `arquivo_claro` o claro; o `arquivo_html` (o telefone antigo, só durante a troca) a tela não usa
PNG_RE = re.compile(r"telas/[a-z0-9][a-z0-9-]{0,60}\.png")
_FONTE_RE = re.compile(r"\s*\[([^\[\]]{1,120})\]\s*$")
_CACHE: dict = {}


def limpar() -> None:
    _CACHE.clear()


def sem_acento(texto: str) -> str:
    """Minúscula e sem acento, para a busca (a mesma conta do static/guia-app.js)."""
    t = unicodedata.normalize("NFD", str(texto or "").lower())
    return " ".join("".join(c for c in t if unicodedata.category(c) != "Mn").split())


def _lista(v) -> list[str]:
    return [str(x).strip() for x in (v or []) if isinstance(x, str) and str(x).strip()]


def regra(texto: str) -> dict:
    """A regra e a fonte dela, que vem entre colchetes no fim ("... [fa:3113; v269]")."""
    m = _FONTE_RE.search(texto)
    return {"texto": texto[:m.start()].rstrip() if m else texto, "fonte": m.group(1).strip() if m else ""}


def _pergunta(p) -> dict | None:
    if not isinstance(p, dict):
        return None
    pid, titulo = str(p.get("id") or "").strip(), str(p.get("titulo") or "").strip()
    if not ID_RE.fullmatch(pid) or not titulo:
        return None
    telas = []
    for t in p.get("telas") or []:
        arq = str((t or {}).get("arquivo") or "").strip() if isinstance(t, dict) else ""
        if ARQ_RE.fullmatch(arq):           # o caminho vai ao src do iframe ou da imagem: só o formato do pacote
            tela = {"arquivo": arq, "legenda": str(t.get("legenda") or "").strip()}
            if arq.endswith(".png"):
                claro = str(t.get("arquivo_claro") or "").strip()
                tela.update(arquivo_claro=claro if PNG_RE.fullmatch(claro) else "", imagem=True)
            telas.append(tela)
    resumo, regras, casos = _lista(p.get("resumo")), _lista(p.get("regras")), _lista(p.get("casos"))
    return {"id": pid, "titulo": titulo, "tema": str(p.get("tema") or "").strip() or "Outros",
            "publico": _lista(p.get("publico")), "resumo": resumo, "regras": [regra(r) for r in regras],
            "casos": casos, "incerto": _lista(p.get("incerto")), "telas": telas,
            "busca": sem_acento(" ".join([titulo, *resumo, *regras, *casos]))}


def carregar() -> dict:
    """{"perguntas", "temas" [(nome, [perguntas])], "app", "atualizado_em", "erro"}; relido quando o arquivo muda."""
    arq = PASTA / "guia.json"
    try:
        marca = arq.stat().st_mtime_ns
    except OSError:
        return {"perguntas": [], "temas": [], "app": "", "atualizado_em": "", "erro": "sem o guia.json"}
    if _CACHE.get("marca") == marca:
        return _CACHE["guia"]
    try:
        d = json.loads(arq.read_text(encoding="utf-8"))
        if not isinstance(d, dict) or d.get("versao") != 1 or not isinstance(d.get("perguntas"), list):
            raise ValueError("o guia.json não é a versão 1 do pacote")
    except (OSError, ValueError) as ex:
        return {"perguntas": [], "temas": [], "app": "", "atualizado_em": "", "erro": f"{type(ex).__name__}: {ex}"[:200]}
    perguntas, vistos = [], set()
    for p in d["perguntas"]:
        n = _pergunta(p)
        if n and n["id"] not in vistos:
            vistos.add(n["id"])
            perguntas.append(n)
    # os temas na ordem que o pacote manda (`temas`, a ordem dos chips, desde 22/11/2026); sem a lista, na ordem em que
    # aparecem (o pacote põe primeiro as perguntas que o Levi citou). Tema de pergunta que falta na lista vai ao fim
    temas: dict[str, list] = {str(n).strip(): [] for n in (d.get("temas") or []) if isinstance(n, str) and str(n).strip()}
    for p in perguntas:
        temas.setdefault(p["tema"], []).append(p)
    temas = {n: ps for n, ps in temas.items() if ps}
    g = {"perguntas": perguntas, "temas": list(temas.items()), "app": str(d.get("app") or ""),
         "atualizado_em": str(d.get("atualizado_em") or ""), "erro": ""}
    _CACHE.update(marca=marca, guia=g)
    return g
