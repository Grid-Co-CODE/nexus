"""O Controle de fornecedores (Nexus > Chamados > Fabricantes) por cima do código, em memória.

PARTE DO PACOTE `chamado_garantia` — puro, sem rede: quem lê a aba do banco é quem usa (o OS Creator pelo
`chamado_modelos_store`, o App de Campo pela API de planilhas) e entrega as linhas aqui.

Levi, 20/10/2026: "Essa lista tem que ser a mesma do nexus > fabricantes: ele escolhe o fabricante o app já filtra se é
inversor, cabine etc" e "quero também que quando a singrid adicione novos fabricantes em chamados > fabricantes apareça
atualizado no app". Até aqui esta lógica morava só no OS Creator (`chamado_modelos_store`), e o App seguia a lista do
código: veio para o pacote para os dois aplicarem a MESMA regra, sem cópia.

A aba é `os_creator · chamado_modelos` (WORKBOOK, ABA), uma linha por bloco, `chave` e `valor` (JSON):

    BASE                  toda inspeção, de qualquer ativo e fornecedor
    TIPO:<tipo de ativo>  o bloco do tipo ("TIPO:Inversor", "TIPO:Estrutura Trackers"…)
    MARCA:<fornecedor>    o que o fornecedor pede a mais, o canal de abertura, os tipos que ele atende (`atende`) e se
                          está arquivado

Bloco sem linha no banco vale o do código (`semente`). `aplicar` reescreve, EM MEMÓRIA e NO LUGAR, as estruturas do
`spec` (BASE, POR_TIPO, POR_FABRICANTE, TIPOS_DA_MARCA e MARCAS_CONHECIDAS): no lugar, e não trocando o objeto, porque
quem fez `from chamado_garantia.spec import POR_TIPO` guardou o objeto de origem. Fornecedor novo no banco entra na
escolha dos tipos que atende (`spec.marcas_para`) e passa a ser reconhecido no nome do ativo (`spec.marca_do_ativo`);
arquivado sai da escolha.
"""
from __future__ import annotations

import copy
import json

from . import spec as sp

WORKBOOK = "os_creator"
ABA = "chamado_modelos"
COLUNAS = ["chave", "valor"]
LIMITE_NOME = 40


# ── a foto do código, tirada na importação: é a ela que `aplicar` sempre volta antes de pôr o banco por cima ─────────
def _foto() -> dict:
    return {"BASE": copy.deepcopy(sp.BASE), "POR_TIPO": copy.deepcopy(sp.POR_TIPO),
            # deepcopy por marca quebra a identidade dos clones de propósito: ela é refeita por `CLONES`
            "POR_FABRICANTE": {m: copy.deepcopy(v) for m, v in sp.POR_FABRICANTE.items()},
            "TIPOS_DA_MARCA": copy.deepcopy(sp.TIPOS_DA_MARCA), "MARCAS_CONHECIDAS": list(sp.MARCAS_CONHECIDAS)}


_ORIG = _foto()
# No código, Brametal e Romiotto não têm lista própria: são o MESMO objeto da STI e da Hukseflux. Enquanto ninguém
# salvar o clone sozinho, ele segue o original — inclusive a versão editada dele.
CLONES = {c: o for c, o in {"Brametal": "STI", "Romiotto": "Hukseflux"}.items()
          if c in sp.POR_FABRICANTE and sp.POR_FABRICANTE.get(c) is sp.POR_FABRICANTE.get(o)}


# ── subtarefa: o dict do pacote (`spec._s`, com `so_para` em set) ↔ o JSON do banco ───────────────────────────────
def para_json(s: dict) -> dict:
    return {"desc": str(s.get("desc") or ""), "tipo": s.get("tipo") or "texto", "obrig": bool(s.get("obrig")),
            "anexo": bool(s.get("anexo")), "opcoes": list(s.get("opcoes") or []), "chave": str(s.get("chave") or ""),
            "so_para": sorted(s.get("so_para") or [])}


def de_json(d: dict) -> dict:
    return sp._s(str(d.get("desc") or "").strip(), d.get("tipo") or "texto", obrig=bool(d.get("obrig")),
                 anexo=bool(d.get("anexo")), opcoes=list(d.get("opcoes") or []) or None,
                 chave=str(d.get("chave") or ""), so_para=list(d.get("so_para") or []) or None)


def chave_valida(ch: str) -> bool:
    ch = str(ch or "")
    if ch == "BASE":
        return True
    if ch.startswith("TIPO:"):
        return ch[5:] in _ORIG["POR_TIPO"]
    if ch.startswith("MARCA:"):
        nome = ch[6:]
        return bool(nome.strip()) and nome == nome.strip() and len(nome) <= LIMITE_NOME and ":" not in nome
    return False


def semente(canal: dict | None = None) -> dict:
    """Os blocos como estão no código — o valor inicial e a rede de segurança. `canal` = {fornecedor: canal de
    abertura} do código de quem chama (o OS Creator tem o dele; o pacote não tem canal)."""
    canal = canal or {}
    out = {"BASE": {"subtarefas": [para_json(s) for s in _ORIG["BASE"]]}}
    for t, subs in _ORIG["POR_TIPO"].items():
        out["TIPO:" + t] = {"subtarefas": [para_json(s) for s in subs]}
    for m in sorted(set(_ORIG["POR_FABRICANTE"]) | set(_ORIG["TIPOS_DA_MARCA"])):
        out["MARCA:" + m] = {"subtarefas": [para_json(s) for s in _ORIG["POR_FABRICANTE"].get(m, [])],
                             "canal": canal.get(m, ""), "atende": sorted(_ORIG["TIPOS_DA_MARCA"].get(m, [])),
                             "arquivado": False, "igual_a": CLONES.get(m, "")}
    return out


# ── leitura ───────────────────────────────────────────────────────────────────────────────────────────────────
def de_registro(r: dict):
    """Uma linha da aba ({"chave", "valor", "_linha"?}) → (chave, valor) ou None. Linha ilegível é PULADA: um JSON
    estragado num fornecedor não pode tirar os outros da escolha."""
    r = r if isinstance(r, dict) else {}
    ch = str(r.get("chave") or "").strip()
    if not chave_valida(ch):
        return None
    try:
        v = json.loads(r.get("valor") or "{}")
    except (TypeError, ValueError):
        return None
    if not isinstance(v, dict) or not isinstance(v.get("subtarefas", []), list):
        return None
    v["_linha"] = r.get("_linha")
    return ch, v


def de_linhas(registros) -> dict:
    """{chave: valor} das linhas da aba. Chave repetida (duas pessoas criando o mesmo fornecedor ao mesmo tempo): vale a
    versão mais nova."""
    banco = {}
    for r in registros or ():
        x = de_registro(r)
        if not x:
            continue
        ch, v = x
        if ch not in banco or str(v.get("versao") or "") >= str(banco[ch].get("versao") or ""):
            banco[ch] = v
    return banco


def efetivo(banco: dict | None = None, canal: dict | None = None) -> dict:
    """Cada bloco como vale AGORA: o do banco quando existe, o do código quando não. `origem` diz qual."""
    out = {ch: dict(v, origem="codigo", versao="", por="") for ch, v in semente(canal).items()}
    for ch, v in (banco or {}).items():
        out[ch] = dict(out.get(ch, {"subtarefas": [], "canal": "", "atende": [], "arquivado": False, "igual_a": ""}),
                       **{k: x for k, x in v.items() if not k.startswith("_")}, origem="banco")
        if ch.startswith("MARCA:"):
            out[ch]["igual_a"] = ""                       # salvo sozinho, o clone passou a ter a lista dele
    return out


def _trocar_dict(d: dict, novo: dict):
    """Troca o conteúdo sem esvaziar no meio: quem lê em outra thread nunca vê o dicionário vazio."""
    d.update(novo)
    for k in [k for k in d if k not in novo]:
        del d[k]


def aplicar(banco: dict | None = None) -> None:
    """Joga os blocos do banco por cima do código, em memória, no lugar. Sem banco (ou `{}`), volta ao código puro. O
    canal de abertura não mora no pacote: quem tem o dele (o OS Creator) aplica a partir do `efetivo`."""
    banco = banco or {}
    ef = efetivo(banco)
    base = [de_json(x) for x in ef["BASE"].get("subtarefas") or []]
    tipos = {ch[5:]: [de_json(x) for x in v.get("subtarefas") or []] for ch, v in ef.items() if ch.startswith("TIPO:")}
    fabr, atende = {}, {}
    for ch, v in ef.items():
        if not ch.startswith("MARCA:") or v.get("arquivado"):
            continue                                      # arquivado some da escolha; o histórico fica na OS criada
        m = ch[6:]
        fabr[m] = [de_json(x) for x in v.get("subtarefas") or []]
        if v.get("atende"):
            atende[m] = set(v["atende"])
    for c, o in CLONES.items():
        if ("MARCA:" + c) not in banco and c in fabr and o in fabr:
            fabr[c] = fabr[o]                             # a mesma lista, como no código
    sp.BASE[:] = base
    _trocar_dict(sp.POR_TIPO, tipos)
    _trocar_dict(sp.POR_FABRICANTE, fabr)
    _trocar_dict(sp.TIPOS_DA_MARCA, atende)
    sp.MARCAS_CONHECIDAS[:] = sorted(set(_ORIG["MARCAS_CONHECIDAS"]) | set(atende))


def fornecedores(tipo_ativo: str | None = None) -> list:
    """Os fornecedores que valem agora (depois do `aplicar`), na ordem alfabética; com `tipo_ativo`, só os que atendem
    aquele tipo. É a lista que o técnico vê ao abrir o chamado (`spec.marcas_para`)."""
    return sp.marcas_para(tipo_ativo or "")
