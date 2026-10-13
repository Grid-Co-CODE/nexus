"""Equipamentos das usinas no Nexus (Base → Equipamentos das usinas, 13/10/2026).

Levi, 13/10/2026: "Temos que substituir a aba equipamentos aproveitando o que tem lá e usando o Nexus como ponto de
partida a partir daquele produto. Precisamos ligar a usina do Fractal com Usina cadastrada no registro mestre com usina
do supervisório para aí poder ligar os inversores, quantidade de cabines, quantidade de inversor por cabine, quantidade de
strings por inversor, potência sendo calculado pelo kwp da usina e das cabines... precisamos ter uma versatilidade no
Nexus, não pode ser âncora". E logo depois: "Não quero que faça as conexões automaticamente, quero poder ver e fazer de
forma versátil, pq se só você fizer vai ficar fácil de entender para você, quando eu for fazer não vou entender nada".

O que é:
- O ponto de partida é a usina do Registro mestre (`usina_id`). A ela se ligam, À MÃO: o nome no Fracttal (a Classificação
  1, pela MESMA decisão da seção Ligações: um de-para só, `ligacoes.decidir`) e as chaves do supervisório (a "Usina
  Supervisório" da aba Equipamentos, a chave que a plataforma usa por dentro). Uma usina pode ter várias: a Altair tem
  seis na aba (a "Altair", com a UFV e as cabines, e "Altair 1 (73)" a "Altair 5 (77)", uma por cabine, com os
  inversores); 85 das usinas da aba têm mais de uma (medido em 13/10/2026).
- A estrutura é da USINA: as cabines (a "UG" da aba, com kWp) e os inversores, cada um com a chave do supervisório por
  onde chega, o nome lá, a cabine, kWp, strings esperadas e o ativo do Fracttal. A cabine é da usina, e não da chave,
  porque na aba a UG fica numa chave e os inversores dela em outra (a Altair, acima: 1.311 dos 2.201 inversores da aba
  apontam para uma UG de outra chave).
- Potência: a da usina (Registro mestre) contra a soma das cabines e a dos inversores. Sem o kWp do inversor, conta o da
  cabine dividido pelos inversores dela, e a tela diz que é calculado.
- A aba Equipamentos (`bd_performance · Equipamentos`, no banco) é SÓ referência: o "Trazer da aba" da tela preenche o
  rascunho, e nada é gravado sem o Salvar de quem decide.

No lugar da aba (13/10/2026, Levi: "pode fazer todas as fases! vamos pra cima!"): cada chave tem a marca
`substitui_aba`. As chaves marcadas saem também numa VISÃO no formato da aba Equipamentos (`aba_equipamentos`, as mesmas
colunas, com os IDs no fim), e cada leitor da aba (a plataforma, o gêmeo, o coletor, a ponte das Ligações) troca as linhas
daquelas chaves pelas da visão (`sobrepor`): o resto do leitor não muda. A chave de cada linha é a da plataforma, "Usina
Supervisório" e, sem ela, "Usina". A linha da usina (UFV) e as das cabines (UG) saem na chave da usina (`principal`), com
"Usina Supervisório" vazia quando a chave é o próprio nome de exibição (como 103 das 146 UFV da aba); a do inversor, sempre
com a chave. O nome de exibição é o da chave (`usina_exibicao`, o "Usina" da aba; vazio = o do Registro mestre). A tela
mostra, chave a chave, o que muda para os leitores (`comparar_chave`) antes de marcar.

O dado: livro `nexus_estrutura_usina` (catálogo do Nexus), três abas de estado: `dim_supervisorio`, `dim_cabine`,
`dim_inversor`, e a visão `aba_equipamentos`, refeita a cada gravação. Gravar troca o livro inteiro (relido do banco antes, sob trava: nunca a cópia de 1 minuto) e o
`livros.publicar` confere a contagem. ID novo = maior + 1 e não volta; excluir marca `excluido = sim`. O Salvar leva o
selo da usina que a tela abriu: se a usina mudou no meio (outra aba, outra pessoa), nada é gravado. Quem mudou vai em
`alterado_por_hmac` (regra 8: nada de e-mail no banco, que tem leitura aberta) e no log da máquina.
"""
import copy
import hashlib
import json
import logging
import re
import threading
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone

from ..dados import fatos as D
from ..dados import livros

log = logging.getLogger(__name__)

LIVRO, NOME_LIVRO = "nexus_estrutura_usina", "Nexus · estrutura das usinas"
ABA_SUP, ABA_CAB, ABA_INV, ABA_VISAO = "dim_supervisorio", "dim_cabine", "dim_inversor", "aba_equipamentos"
_CONTROLE = ("criado_em", "alterado_em", "alterado_por_hmac", "excluido")
CAB_SUP = ("supervisorio_id", "usina_id", "usina_supervisorio", "usina_exibicao", "principal", "full_om", "string_box",
           "substitui_aba") + _CONTROLE
CAB_CAB = ("cabine_id", "usina_id", "nome", "potencia_kwp", "equipamento_id", "codigo_fracttal", "ordem") + _CONTROLE
CAB_INV = ("inversor_id", "usina_id", "supervisorio_id", "cabine_id", "nome", "equipamento_supervisorio",
           "potencia_kwp", "strings_esperadas_qtd", "equipamento_id", "codigo_fracttal", "ordem") + _CONTROLE
# a visão: as colunas da aba Equipamentos que os leitores usam, com o MESMO nome ("Chave" e "Chave 2" são as
# concatenações que a aba tem; "Observações" é texto livre e fica fora: regra 8), e os IDs do Nexus no fim
CAB_VISAO = ("Cliente", "Usina", "Usina Supervisório", "Usina Fractall", "Equipamento", "Equipamento Supervisório",
             "Equipamento Parente", "Chave", "Chave 2", "Potência (kWp)", "N de Inversores", "String Box", "Full O&M",
             "Strings Ativas", "usina_id", "supervisorio_id", "cabine_id", "inversor_id")
ABA_EQUIPAMENTOS = ("bd_performance", "Equipamentos")
ABA_ATIVOS = ("nexus_equipamentos", "dim_equipamento")
TTL_S, TTL_ABA_S, TTL_ATIVOS_S = 60, 600, 3600
MAX_CABINES, MAX_INVERSORES, MAX_TEXTO = 300, 3000, 120
_TRAVA = threading.Lock()
_CACHE: dict = {}


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê, para a tela mostrar."""


# ── leitura e normalização ───────────────────────────────────────────────────────────────────────────────────────────
def norm(s) -> str:
    """Para comparar nomes: sem acento, sem caixa, espaços únicos."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def texto(v) -> str:
    """Texto limpo para gravar: espaços únicos, no máximo `MAX_TEXTO` caracteres."""
    return " ".join(str(v or "").split())[:MAX_TEXTO]


def _num(v):
    """kWp: número >= 0 ou None ("338,1" vale 338,1)."""
    if v is None or isinstance(v, bool) or (isinstance(v, str) and not v.strip()):
        return None
    try:
        x = float(v) if isinstance(v, (int, float)) else float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return round(x, 3) if x >= 0 and x == x and x != float("inf") else None


def _int(v):
    x = _num(v)
    return int(round(x)) if x is not None else None


def natural(s) -> list:
    """Ordem de gente: "INVR1.2" antes de "INVR1.10"."""
    return [(0, int(p), "") if p.isdigit() else (1, 0, p.lower()) for p in re.split(r"(\d+)", str(s or "")) if p]


def _sim(v) -> bool:
    return D._txt(v).lower() in ("sim", "true", "1", "1.0")


def _controle(x: dict) -> dict:
    return {"criado_em": D._txt(x.get("criado_em")), "alterado_em": D._txt(x.get("alterado_em")),
            "alterado_por_hmac": D._txt(x.get("alterado_por_hmac")), "excluido": _sim(x.get("excluido"))}


def _sup(x: dict):
    sid, chave = D._id(x.get("supervisorio_id")), texto(x.get("usina_supervisorio"))
    if not sid or not chave:
        return None
    return {"supervisorio_id": sid, "usina_id": D._id(x.get("usina_id")), "usina_supervisorio": chave,
            "usina_exibicao": texto(x.get("usina_exibicao")), "principal": _sim(x.get("principal")),
            "full_om": _sim(x.get("full_om")), "string_box": _sim(x.get("string_box")),
            "substitui_aba": _sim(x.get("substitui_aba")), **_controle(x)}


def _cab(x: dict):
    cid, nome = D._id(x.get("cabine_id")), texto(x.get("nome"))
    if not cid or not nome:
        return None
    return {"cabine_id": cid, "usina_id": D._id(x.get("usina_id")), "nome": nome,
            "potencia_kwp": _num(x.get("potencia_kwp")), "equipamento_id": D._id(x.get("equipamento_id")),
            "codigo_fracttal": texto(x.get("codigo_fracttal")), "ordem": _int(x.get("ordem")) or 0, **_controle(x)}


def _inv(x: dict):
    iid, nome = D._id(x.get("inversor_id")), texto(x.get("nome"))
    if not iid or not nome:
        return None
    return {"inversor_id": iid, "usina_id": D._id(x.get("usina_id")), "supervisorio_id": D._id(x.get("supervisorio_id")),
            "cabine_id": D._id(x.get("cabine_id")), "nome": nome,
            "equipamento_supervisorio": texto(x.get("equipamento_supervisorio")),
            "potencia_kwp": _num(x.get("potencia_kwp")), "strings_esperadas_qtd": _int(x.get("strings_esperadas_qtd")),
            "equipamento_id": D._id(x.get("equipamento_id")), "codigo_fracttal": texto(x.get("codigo_fracttal")),
            "ordem": _int(x.get("ordem")) or 0, **_controle(x)}


def _ler_banco(base: str, sessao) -> dict:
    a = livros.abas(base, sessao, LIVRO)

    def le(aba, f):
        return [y for y in (f(x) for x in livros._linhas(base, sessao, a[aba])) if y] if aba in a else []
    return {"supervisorios": le(ABA_SUP, _sup), "cabines": le(ABA_CAB, _cab), "inversores": le(ABA_INV, _inv),
            "visao": livros._linhas(base, sessao, a[ABA_VISAO]) if ABA_VISAO in a else []}


def ler(base: str, sessao, forcar: bool = False) -> dict:
    """{"supervisorios", "cabines", "inversores", "lido_em", "erro"}: o livro, guardado por 1 minuto. Leitura que falha
    devolve a última boa com o erro (`velha`); sem nenhuma, vazio com o erro (a tela não deixa gravar sem saber o que há)."""
    c = _CACHE.get("livro")
    if c and not forcar and time.time() - c["lido_em"] < TTL_S:
        return c
    try:
        d = _ler_banco(base, sessao)
    except Exception as ex:      # noqa: BLE001 — banco fora, rede
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        if c:
            return dict(c, erro=erro, velha=True)
        return {"supervisorios": [], "cabines": [], "inversores": [], "visao": [], "lido_em": None, "erro": erro}
    c = dict(d, lido_em=time.time(), erro="")
    _CACHE["livro"] = c
    return c


def da_usina(est: dict, usina_id: int) -> dict:
    """O que a usina tem de pé (sem os excluídos): as chaves do supervisório, as cabines e os inversores, na ordem."""
    def vivos(itens):
        return [x for x in itens if x["usina_id"] == usina_id and not x["excluido"]]
    return {"supervisorios": sorted(vivos(est["supervisorios"]), key=lambda s: norm(s["usina_supervisorio"])),
            "cabines": sorted(vivos(est["cabines"]), key=lambda c: (c["ordem"], norm(c["nome"]))),
            "inversores": sorted(vivos(est["inversores"]), key=lambda i: (i["ordem"], norm(i["nome"])))}


def selo(u: dict) -> str:
    """A impressão do que a usina tem de pé: o Salvar só grava se o banco ainda estiver como a tela abriu. Só os campos
    do negócio (os de controle, como a data, podem voltar do banco escritos de outro jeito e dariam mudança falsa)."""
    def so_negocio(itens, cab):
        return [[x.get(c) for c in cab if c not in _CONTROLE + ("usina_id",)] for x in itens]
    corpo = json.dumps([so_negocio(u["supervisorios"], CAB_SUP), so_negocio(u["cabines"], CAB_CAB),
                        so_negocio(u["inversores"], CAB_INV)], ensure_ascii=False)
    return hashlib.sha1(corpo.encode("utf-8")).hexdigest()[:16]


def resumo(u: dict) -> dict:
    """Quantas chaves, cabines, inversores e strings; kWp das cabines e dos inversores (o informado; sem ele, o da cabine
    dividido pelos inversores dela, contado também à parte como calculado); e o que falta preencher."""
    cabs, invs = u["cabines"], u["inversores"]
    cab = {c["cabine_id"]: c for c in cabs}
    n_na_cab = Counter(i["cabine_id"] for i in invs if i["cabine_id"])
    kwp_inf = kwp_calc = 0.0
    for i in invs:
        c = cab.get(i["cabine_id"])
        if i["potencia_kwp"] is not None:
            kwp_inf += i["potencia_kwp"]
        elif c and c["potencia_kwp"] is not None:
            kwp_calc += c["potencia_kwp"] / n_na_cab[c["cabine_id"]]
    com_kwp = [c["potencia_kwp"] for c in cabs if c["potencia_kwp"] is not None]
    return {"chaves": len(u["supervisorios"]), "no_lugar_da_aba": sum(1 for s in u["supervisorios"] if s["substitui_aba"]),
            "cabines": len(cabs), "inversores": len(invs),
            "strings": sum(i["strings_esperadas_qtd"] or 0 for i in invs),
            "kwp_cabines": round(sum(com_kwp), 3) if com_kwp else None,
            "kwp_inversores": round(kwp_inf + kwp_calc, 3) if invs and (kwp_inf or kwp_calc) else None,
            "kwp_calculado": round(kwp_calc, 3),
            "sem_chave": sum(1 for i in invs if not i["supervisorio_id"]),
            "sem_cabine": sum(1 for i in invs if not i["cabine_id"] or i["cabine_id"] not in cab),
            "sem_strings": sum(1 for i in invs if i["strings_esperadas_qtd"] is None)}


def conferir_potencia(kwp_usina, kwp) -> str:
    """"fecha" (até 0,5% de diferença), "perto" (até 5%), "nao_fecha" ou "" (falta um dos dois)."""
    if not kwp_usina or kwp is None:
        return ""
    d = abs(kwp - kwp_usina) / kwp_usina
    return "fecha" if d <= 0.005 else ("perto" if d <= 0.05 else "nao_fecha")


# ── a visão no formato da aba Equipamentos (o que os leitores da aba passam a ler) ───────────────────────────────────
def exibicao(s: dict, info_u: dict | None) -> str:
    """O nome de exibição da chave: o dela ("Usina" da aba), senão o da usina no Registro mestre."""
    return s["usina_exibicao"] or texto((info_u or {}).get("nome"))


def nome_de_inversor(nome: str) -> str:
    """Os leitores da aba só contam como inversor a linha cujo Equipamento começa por "Inversor" (a plataforma, o gêmeo e
    o coletor): o nome que não começa assim sai com o prefixo, e a comparação mostra."""
    return nome if norm(nome).startswith("inversor") else f"Inversor {nome}"


def chave_efetiva(linha: dict) -> str:
    """A chave de uma linha no formato da aba, como a plataforma a lê: "Usina Supervisório" e, sem ela, "Usina"."""
    return texto(linha.get("Usina Supervisório")) or texto(linha.get("Usina"))


def visao_da_usina(u: dict, info_u: dict | None, todas: bool = False) -> list[dict]:
    """As linhas no formato da aba Equipamentos das chaves da usina marcadas "no lugar da aba" (todas, com `todas`: é o
    que a comparação usa). A usina (UFV, com a potência do Registro mestre ou, sem ela, a soma das cabines) e as cabines
    (UG) saem na chave da usina; cada inversor, na chave dele. Inversor sem chave não sai (não é de leitor nenhum)."""
    info_u = info_u or {}
    pega = [s for s in u["supervisorios"] if todas or s["substitui_aba"]]
    cliente, fr = texto(info_u.get("cliente")) or None, texto(info_u.get("fracttal")) or None
    n_na_cab = Counter(i["cabine_id"] for i in u["inversores"] if i["cabine_id"])
    cab = {c["cabine_id"]: c for c in u["cabines"]}
    out = []
    for s in pega:
        disp = exibicao(s, info_u) or s["usina_supervisorio"]
        comum = {"Cliente": cliente, "Usina": disp, "Usina Fractall": fr, "String Box": "Sim" if s["string_box"] else "Não",
                 "Full O&M": "Sim" if s["full_om"] else "Não", "usina_id": s["usina_id"],
                 "supervisorio_id": s["supervisorio_id"]}
        if s["principal"]:
            sup = "" if norm(s["usina_supervisorio"]) == norm(disp) else s["usina_supervisorio"]
            kwp = info_u.get("kwp")
            if kwp is None and any(c["potencia_kwp"] is not None for c in u["cabines"]):
                kwp = round(sum(c["potencia_kwp"] or 0 for c in u["cabines"]), 3)
            out.append(dict(comum, **{"Usina Supervisório": sup or None, "Equipamento": "UFV", "Chave 2": f"{sup}UFV",
                                      "Potência (kWp)": kwp, "N de Inversores": len(u["inversores"]) or None}))
            for c in u["cabines"]:
                out.append(dict(comum, **{"Usina Supervisório": sup or None, "Equipamento": c["nome"],
                                          "Equipamento Parente": "UFV", "Chave 2": f"{sup}{c['nome']}",
                                          "Potência (kWp)": c["potencia_kwp"],
                                          "N de Inversores": n_na_cab.get(c["cabine_id"]) or None,
                                          "cabine_id": c["cabine_id"]}))
        for i in u["inversores"]:
            if i["supervisorio_id"] != s["supervisorio_id"]:
                continue
            eq, esup, chave = nome_de_inversor(i["nome"]), i["equipamento_supervisorio"], s["usina_supervisorio"]
            c = cab.get(i["cabine_id"])
            out.append(dict(comum, **{"Usina Supervisório": chave, "Equipamento": eq, "Equipamento Supervisório": esup or None,
                                      "Equipamento Parente": c["nome"] if c else None,
                                      "Chave": f"{chave}{esup}" if esup else None, "Chave 2": f"{chave}{eq}",
                                      "Potência (kWp)": i["potencia_kwp"], "Strings Ativas": i["strings_esperadas_qtd"],
                                      "cabine_id": i["cabine_id"], "inversor_id": i["inversor_id"]}))
    return [{c: x.get(c) for c in CAB_VISAO} for x in out]


def visao_aba(est: dict, info: dict | None) -> list[dict]:
    """A visão inteira: as usinas com alguma chave "no lugar da aba", na ordem do ID (o sha não muda de máquina)."""
    usinas = sorted({s["usina_id"] for s in est["supervisorios"] if not s["excluido"] and s["substitui_aba"]})
    return [x for uid in usinas for x in visao_da_usina(da_usina(est, uid), (info or {}).get(uid))]


def sobrepor(linhas_aba, linhas_visao) -> list[dict]:
    """A aba com as chaves da visão trocadas: tira da aba as linhas de UFV, UG e inversor das chaves que a visão traz e
    põe as da visão. É o mesmo que cada leitor da aba faz do lado dele (a plataforma, o gêmeo, o coletor)."""
    visao = list(linhas_visao or ())
    chaves = {chave_efetiva(x) for x in visao}
    if not chaves:
        return list(linhas_aba or ())
    return [x for x in linhas_aba or () if chave_efetiva(x) not in chaves or not _tipo_linha(x.get("Equipamento"))] + visao


def _celula(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return round(float(v), 3)
    s = str(v).strip()
    try:
        return round(float(s.replace(",", ".")), 3) if re.fullmatch(r"-?\d+([.,]\d+)?", s) else s
    except ValueError:
        return s


def _mesma_visao(a, b) -> bool:
    """As duas listas dizem o mesmo (o banco devolve número como texto, inteiro como real...)."""
    def n(linhas):
        return [[_celula(x.get(c)) for c in CAB_VISAO] for x in linhas or ()]
    return n(a) == n(b)


def comparar_chave(g: dict | None, linhas: list[dict]) -> dict:
    """O que muda para os leitores da aba se a chave passar a vir do Nexus: o grupo dela na aba (`agrupar_aba`) contra as
    linhas da visão dela. {"na_aba", "iguais", "n", "dif": [textos]} (até 40 textos)."""
    if g is None:
        return {"na_aba": False, "iguais": False, "n": 1,
                "dif": ["A chave não está na aba Equipamentos: marcada, os leitores passam a conhecê-la só pelo Nexus."]}
    dif = []

    def num(v):
        x = _num(v)
        return None if x is None else round(x, 2)

    def txt(rotulo, a, n):
        if norm(a) != norm(n):
            dif.append(f"{rotulo}: “{a or '—'}” na aba, “{n or '—'}” no Nexus.")

    def val(rotulo, a, n):
        if (a is None) != (n is None) or (a is not None and abs(a - n) > 0.05):
            dif.append(f"{rotulo}: {a if a is not None else '—'} na aba, {n if n is not None else '—'} no Nexus.")
    ufv = next((x for x in linhas if x["Equipamento"] == "UFV"), None)
    ugs = [x for x in linhas if x.get("cabine_id") and not x.get("inversor_id")]
    invs = [x for x in linhas if x.get("inversor_id")]
    um = linhas[0] if linhas else {}
    if linhas:
        txt("Nome de exibição", g["usina"], um.get("Usina"))
        txt("Nome no Fracttal", g["fracttal"], um.get("Usina Fractall"))
        txt("Cliente", g["cliente"], um.get("Cliente"))
        if g["full_om"] != (um.get("Full O&M") == "Sim"):
            dif.append(f"Full O&M: {'Sim' if g['full_om'] else 'Não'} na aba, {um.get('Full O&M')} no Nexus.")
        if g["string_box"] != (um.get("String Box") == "Sim"):
            dif.append(f"String Box: {'Sim' if g['string_box'] else 'Não'} na aba, {um.get('String Box')} no Nexus.")
    if g["ufv_kwp"] is not None or ufv:
        if not ufv:
            dif.append(f"A linha da usina (UFV, {g['ufv_kwp']} kWp) está nesta chave na aba; no Nexus, esta não é a chave "
                       "da usina.")
        elif g["ufv_kwp"] is None and not g["cabines"]:
            dif.append("No Nexus esta é a chave da usina (UFV e cabines); na aba, a linha da usina fica em outra chave.")
        else:
            val("Potência da usina (kWp)", num(g["ufv_kwp"]), num(ufv["Potência (kWp)"]))
            val("Inversores da usina", g["ufv_inversores"], _int(ufv["N de Inversores"]))
    if g["cabines"] or ugs:
        a = {norm(c["nome"]): c for c in g["cabines"]}
        n = {norm(x["Equipamento"]): x for x in ugs}
        for k in a.keys() - n.keys():
            dif.append(f"Cabine {a[k]['nome']} está na aba e não no Nexus.")
        for k in n.keys() - a.keys():
            dif.append(f"Cabine {n[k]['Equipamento']} está no Nexus e não na aba.")
        for k in a.keys() & n.keys():
            val(f"Cabine {a[k]['nome']} (kWp)", num(a[k]["kwp"]), num(n[k]["Potência (kWp)"]))

    def chave_inv(sup, nome):
        return ("s", norm(sup)) if sup else ("n", norm(nome))
    a = {chave_inv(i["equipamento_supervisorio"], i["nome"]): i for i in g["inversores"]}
    n = {chave_inv(x["Equipamento Supervisório"], x["Equipamento"]): x for x in invs}
    for k in sorted(a.keys() - n.keys(), key=lambda k: natural(k[1])):
        i = a[k]
        dif.append(f"{i['equipamento_supervisorio'] or i['nome']} ({i['nome']}) está na aba e não no Nexus.")
    for k in sorted(n.keys() - a.keys(), key=lambda k: natural(k[1])):
        x = n[k]
        dif.append(f"{x['Equipamento Supervisório'] or x['Equipamento']} ({x['Equipamento']}) está no Nexus e não na aba.")
    for k in sorted(a.keys() & n.keys(), key=lambda k: natural(k[1])):
        i, x = a[k], n[k]
        quem = i["equipamento_supervisorio"] or i["nome"]
        txt(f"{quem}: nome", i["nome"], x["Equipamento"])
        txt(f"{quem}: cabine", i["cabine"], x["Equipamento Parente"])
        val(f"{quem}: kWp", num(i["kwp"]), num(x["Potência (kWp)"]))
        val(f"{quem}: strings", i["strings"], _int(x["Strings Ativas"]))
    return {"na_aba": True, "iguais": not dif, "n": len(dif),
            "dif": dif[:40] + ([f"... e mais {len(dif) - 40} diferenças."] if len(dif) > 40 else [])}


def comparar_usina(u: dict, info_u: dict | None, aba_chaves: dict) -> dict:
    """{supervisorio_id: comparar_chave} de todas as chaves da usina (marcadas ou não: é o que a tela mostra antes)."""
    linhas = visao_da_usina(u, info_u, todas=True)
    out = {}
    for s in u["supervisorios"]:
        out[s["supervisorio_id"]] = comparar_chave(aba_chaves.get(s["usina_supervisorio"]),
                                                   [x for x in linhas if x["supervisorio_id"] == s["supervisorio_id"]])
    return out


# ── a aba Equipamentos (referência) e os ativos do Fracttal ──────────────────────────────────────────────────────────
def _tipo_linha(equip) -> str:
    e = D._txt(equip)
    if e.upper() == "UFV":
        return "ufv"
    if e.upper().startswith("UG"):
        return "cabine"
    if e.lower().startswith("inversor"):
        return "inversor"
    return ""


def agrupar_aba(linhas) -> dict:
    """{chave do supervisório: {...}} da aba Equipamentos, a mesma chave da plataforma (Usina Supervisório, senão Usina).
    Cada chave: a usina de exibição, o nome no Fracttal, o cliente, Full O&M, String Box, a linha UFV (kWp, inversores),
    as cabines (UG: nome, kWp, inversores) e os inversores (nome, nome no supervisório, cabine, kWp, strings)."""
    out = {}
    for d in linhas or ():
        chave = texto(d.get("Usina Supervisório")) or texto(d.get("Usina"))
        tipo = _tipo_linha(d.get("Equipamento"))
        if not chave or not tipo:
            continue
        g = out.setdefault(chave, {"chave": chave, "usina": texto(d.get("Usina")), "fracttal": "", "fracttais": [],
                                   "cliente": "", "full_om": False, "string_box": False, "ufv_kwp": None,
                                   "ufv_inversores": None, "cabines": [], "inversores": []})
        g["fracttal"] = g["fracttal"] or texto(d.get("Usina Fractall"))
        if texto(d.get("Usina Fractall")) and texto(d.get("Usina Fractall")) not in g["fracttais"]:
            g["fracttais"].append(texto(d.get("Usina Fractall")))     # todos: a chave com dois nomes não liga sozinha
        g["cliente"] = g["cliente"] or texto(d.get("Cliente"))
        g["full_om"] = g["full_om"] or _sim(d.get("Full O&M"))
        g["string_box"] = g["string_box"] or _sim(d.get("String Box"))
        if tipo == "ufv":
            g["ufv_kwp"] = _num(d.get("Potência (kWp)"))
            g["ufv_inversores"] = _int(d.get("N de Inversores"))
        elif tipo == "cabine":
            g["cabines"].append({"nome": texto(d.get("Equipamento")), "kwp": _num(d.get("Potência (kWp)")),
                                 "inversores": _int(d.get("N de Inversores"))})
        else:
            g["inversores"].append({"nome": texto(d.get("Equipamento")),
                                    "equipamento_supervisorio": texto(d.get("Equipamento Supervisório")),
                                    "cabine": texto(d.get("Equipamento Parente")), "kwp": _num(d.get("Potência (kWp)")),
                                    "strings": _int(d.get("Strings Ativas"))})
    return out


def aba_equipamentos(base: str, sessao) -> dict:
    """A aba Equipamentos agrupada (`agrupar_aba`), guardada por 10 minutos. Falha = a última boa, ou vazio com o erro."""
    c = _CACHE.get("aba")
    if c and time.time() - c["lido_em"] < TTL_ABA_S:
        return c
    try:
        a = livros.abas(base, sessao, ABA_EQUIPAMENTOS[0])
        linhas = livros._linhas(base, sessao, a[ABA_EQUIPAMENTOS[1]]) if ABA_EQUIPAMENTOS[1] in a else []
        c = {"chaves": agrupar_aba(linhas), "lido_em": time.time(), "erro": ""}
    except Exception as ex:      # noqa: BLE001
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        return dict(c, erro=erro) if c else {"chaves": {}, "lido_em": None, "erro": erro}
    _CACHE["aba"] = c
    return c


def ativos_da_usina(base: str, sessao, usina_id: int) -> dict:
    """{"ativos": [{equipamento_id, codigo, descricao, familia}], "erro"} da dimensão de equipamento do Nexus
    (`nexus_equipamentos · dim_equipamento`: os ativos do Fracttal, já com a usina pelo código), guardada por 1 hora.
    São ~22 mil linhas (5 s na 1ª leitura, 13/10/2026): a tela pede só quando a usina abre, depois de desenhar. Inversor
    é a família INVR (2.071 ativos); cabine, CABN ou SKID."""
    c = _CACHE.get("ativos")
    if not c or time.time() - c["lido_em"] >= TTL_ATIVOS_S:
        try:
            a = livros.abas(base, sessao, ABA_ATIVOS[0])
            linhas = livros._linhas(base, sessao, a[ABA_ATIVOS[1]]) if ABA_ATIVOS[1] in a else []
            por: dict = {}
            for d in linhas:
                uid, eid = D._id(d.get("usina_id")), D._id(d.get("equipamento_id"))
                if uid and eid:
                    por.setdefault(uid, []).append({"equipamento_id": eid, "codigo": texto(d.get("codigo")),
                                                    "descricao": texto(d.get("descricao")),
                                                    "familia": texto(d.get("familia"))})
            c = {"por_usina": por, "lido_em": time.time(), "erro": ""}
            _CACHE["ativos"] = c
        except Exception as ex:  # noqa: BLE001
            erro = f"{type(ex).__name__}: {str(ex)[:160]}"
            if not c:
                return {"ativos": [], "erro": erro}
            c = dict(c, erro=erro)
    return {"ativos": sorted(c["por_usina"].get(usina_id, []), key=lambda x: (x["familia"], natural(x["codigo"]))),
            "erro": c.get("erro", "")}


# ── gravação ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _quem(cfg, email: str) -> str:
    from ..campo.ligacao_cadastro import codigo_da_pessoa
    return codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), email) or ""


def _linhas_do_livro(est: dict, visao: list[dict]) -> dict:
    """As três abas ordenadas pelo ID (o sha do livro não muda de máquina para máquina) e a visão. Indicador como 1/0
    (regra 3); `excluido` como na casa: "sim" ou vazio."""
    def vazio(v):
        return None if v in ("", None) else v

    def valor(c, v):
        if c in ("full_om", "string_box", "principal", "substitui_aba"):
            return 1 if v else 0
        if c == "excluido":
            return "sim" if v else None
        return vazio(v)

    def tab(itens, cab, chave_id):
        return (list(cab), [[valor(c, x.get(c)) for c in cab] for x in sorted(itens, key=lambda x: x[chave_id])])
    return {ABA_SUP: tab(est["supervisorios"], CAB_SUP, "supervisorio_id"),
            ABA_CAB: tab(est["cabines"], CAB_CAB, "cabine_id"),
            ABA_INV: tab(est["inversores"], CAB_INV, "inversor_id"),
            ABA_VISAO: (list(CAB_VISAO), [[vazio(x.get(c)) for c in CAB_VISAO] for x in visao])}


def _gravar(mudar, cfg, base, sessao, quem_email: str = "", info: dict | None = None) -> dict:
    """Relê o banco (nunca a cópia de 1 minuto), aplica a mudança e grava o livro inteiro se algo mudou: as três abas de
    estado ou a visão, refeita com `info` ({usina_id: nome, cliente, kwp, fracttal}, o que a tela sabe do Registro mestre
    e das Ligações; sem `info`, a visão gravada segue como está). Sem a chave de gravação, ou sem ler, nada é gravado."""
    token = cfg.get("GRIDCO_SQL_TOKEN")
    if not token:
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN): nada foi gravado.")
    with _TRAVA:
        try:
            est = _ler_banco(base, sessao)
        except Exception as ex:  # noqa: BLE001
            raise Recusada(f"Não consegui ler a estrutura no banco ({type(ex).__name__}): nada foi gravado, para não "
                           "apagar o que já está lá.") from ex
        estado = ("supervisorios", "cabines", "inversores")
        antes = copy.deepcopy({k: est[k] for k in estado})
        resultado = mudar(est, _agora(), _quem(cfg, quem_email))
        visao = visao_aba(est, info) if info is not None else est["visao"]
        visao_mudou = info is not None and not _mesma_visao(visao, est["visao"])
        if {k: est[k] for k in estado} != antes or visao_mudou:
            livros.publicar(LIVRO, NOME_LIVRO, _linhas_do_livro(est, visao), base=base, token=token, sessao=sessao)
            est["visao"] = visao
        resultado.update(visao_linhas=len(est["visao"]), visao_mudou=visao_mudou)
        _CACHE["livro"] = dict(est, lido_em=time.time(), erro="")
    log.info("Estrutura das usinas: %s, por %s.", resultado.get("log", "sem mudança"),
             quem_email or "senha de administrador")
    return resultado


def _proximo(itens, chave_id) -> int:
    return max((x[chave_id] for x in itens), default=0) + 1


def ligar_supervisorio(usina_id: int, chave: str, cfg, base, sessao, quem_email: str = "", exibicao_aba: str = "",
                       info: dict | None = None) -> dict:
    """Liga uma chave do supervisório à usina do Registro mestre. Chave ligada a OUTRA usina é recusada (uma chave, uma
    usina: é por ela que a plataforma acha a usina); ligada a esta, nada muda. A chave pode não estar na aba (usina
    nova): quem decide é a pessoa, e a tela avisa. Nasce com o nome de exibição da aba (`exibicao_aba`, vazio = o do
    Registro mestre), como a chave da usina se a usina ainda não tem uma, e FORA do lugar da aba (marcar é decisão)."""
    chave = texto(chave)
    if not chave:
        raise Recusada("Escolha ou digite a chave do supervisório.")
    if not usina_id:
        raise Recusada("Escolha a usina do Registro mestre.")

    def mudar(est, agora, quem):
        ativa = next((s for s in est["supervisorios"] if s["usina_supervisorio"] == chave and not s["excluido"]), None)
        if ativa and ativa["usina_id"] != usina_id:
            raise Recusada(f"A chave “{chave}” já está ligada a outra usina (id {ativa['usina_id']}): desligue lá "
                           "antes. Nada foi gravado.")
        if ativa:
            return {"supervisorio_id": ativa["supervisorio_id"], "novo": False, "log": "a chave já estava ligada"}
        sid = _proximo(est["supervisorios"], "supervisorio_id")
        tem_principal = any(s["usina_id"] == usina_id and s["principal"] and not s["excluido"] for s in est["supervisorios"])
        est["supervisorios"].append({"supervisorio_id": sid, "usina_id": usina_id, "usina_supervisorio": chave,
                                     "usina_exibicao": texto(exibicao_aba), "principal": not tem_principal,
                                     "full_om": False, "string_box": False, "substitui_aba": False, "criado_em": agora,
                                     "alterado_em": agora, "alterado_por_hmac": quem, "excluido": False})
        return {"supervisorio_id": sid, "novo": True, "log": f"ligou a chave {chave} à usina {usina_id}"}
    return _gravar(mudar, cfg, base, sessao, quem_email, info)


def desligar_supervisorio(supervisorio_id: int, usina_id: int, cfg, base, sessao, quem_email: str = "",
                          info: dict | None = None) -> dict:
    """Tira a chave da usina (ela passa a excluída; o ID não volta). Os inversores que chegavam por ela ficam na usina,
    sem chave, à vista na tela para ganhar outra: desligar uma chave nunca apaga inversor. Se era a chave da usina, a
    1ª das que ficam passa a ser (a tela diz)."""
    def mudar(est, agora, quem):
        s = next((s for s in est["supervisorios"] if s["supervisorio_id"] == supervisorio_id and not s["excluido"]), None)
        if not s or s["usina_id"] != usina_id:
            raise Recusada("Esta chave já não está ligada a esta usina (a lista mudou desde que a tela abriu): nada foi "
                           "gravado.")
        era_principal = s["principal"]
        s.update(excluido=True, principal=False, substitui_aba=False, alterado_em=agora, alterado_por_hmac=quem)
        soltos = 0
        for i in est["inversores"]:
            if i["supervisorio_id"] == supervisorio_id and not i["excluido"]:
                i.update(supervisorio_id=None, alterado_em=agora, alterado_por_hmac=quem)
                soltos += 1
        nova = None
        if era_principal:
            restam = sorted((x for x in est["supervisorios"] if x["usina_id"] == usina_id and not x["excluido"]),
                            key=lambda x: norm(x["usina_supervisorio"]))
            if restam:
                nova = restam[0]
                nova.update(principal=True, alterado_em=agora, alterado_por_hmac=quem)
        return {"chave": s["usina_supervisorio"], "usina_id": s["usina_id"], "inversores_sem_chave": soltos,
                "nova_principal": nova["usina_supervisorio"] if nova else "",
                "log": f"desligou a chave {s['usina_supervisorio']} da usina {s['usina_id']} ({soltos} inversor(es) "
                       "ficaram sem chave)"}
    return _gravar(mudar, cfg, base, sessao, quem_email, info)


def _validar(dados: dict) -> tuple[dict, list, list]:
    """As chaves, as cabines e os inversores que a tela mandou, limpos e conferidos entre si. Recusa nome vazio ou
    repetido na usina, o mesmo nome no supervisório duas vezes na mesma chave, cabine que não está na lista, número
    negativo ou que não é número, strings fracionadas e listas grandes demais. Se a chave é da usina, `mudar` confere."""
    chaves = {}
    for c in list(dados.get("chaves") or [])[:200]:
        sid = D._id(c.get("supervisorio_id"))
        if sid:
            chaves[sid] = {"full_om": bool(c.get("full_om")), "string_box": bool(c.get("string_box")),
                           "usina_exibicao": texto(c.get("usina_exibicao")), "principal": bool(c.get("principal")),
                           "substitui_aba": bool(c.get("substitui_aba"))}
    if sum(1 for c in chaves.values() if c["principal"]) > 1:
        raise Recusada("Só uma chave pode ser a da usina (a da UFV e das cabines): nada foi gravado.")
    cabs, invs = list(dados.get("cabines") or []), list(dados.get("inversores") or [])
    if len(cabs) > MAX_CABINES or len(invs) > MAX_INVERSORES:
        raise Recusada("Estrutura grande demais para uma usina: nada foi gravado.")

    def kwp(v, oque):
        x = _num(v)
        if v not in (None, "") and x is None:
            raise Recusada(f"A potência {oque} não é um número maior ou igual a zero: nada foi gravado.")
        return x

    limpas, vistas = [], set()
    for n, c in enumerate(cabs):
        nome = texto(c.get("nome"))
        if not nome:
            raise Recusada(f"A {n + 1}ª cabine está sem nome: nada foi gravado.")
        if norm(nome) in vistas:
            raise Recusada(f"Duas cabines com o nome “{nome}”: nada foi gravado.")
        vistas.add(norm(nome))
        limpas.append({"id": D._id(c.get("id")), "k": str(c.get("k") or c.get("id") or f"n{n}"), "nome": nome,
                       "potencia_kwp": kwp(c.get("potencia_kwp"), f"da cabine “{nome}”"),
                       "equipamento_id": D._id(c.get("equipamento_id")),
                       "codigo_fracttal": texto(c.get("codigo_fracttal")), "ordem": n + 1})
    ks = {c["k"] for c in limpas}
    if len(ks) != len(limpas):
        raise Recusada("A lista de cabines veio com a mesma referência duas vezes: recarregue a página.")
    limpos, vistos, vistos_sup = [], set(), set()
    for n, i in enumerate(invs):
        nome = texto(i.get("nome"))
        if not nome:
            raise Recusada(f"O {n + 1}º inversor está sem nome: nada foi gravado.")
        if norm(nome) in vistos:
            raise Recusada(f"Dois inversores com o nome “{nome}”: nada foi gravado.")
        vistos.add(norm(nome))
        chave = D._id(i.get("chave"))
        sup = texto(i.get("equipamento_supervisorio"))
        if sup and (chave, norm(sup)) in vistos_sup:
            raise Recusada(f"Dois inversores com o nome “{sup}” no supervisório, na mesma chave: nada foi gravado.")
        if sup:
            vistos_sup.add((chave, norm(sup)))
        cab = str(i.get("cabine") or "")
        if cab and cab not in ks:
            raise Recusada(f"O inversor “{nome}” aponta para uma cabine que não está na lista: nada foi gravado.")
        strings = i.get("strings_esperadas_qtd")
        s = _num(strings)
        if strings not in (None, "") and (s is None or s != int(s)):
            raise Recusada(f"As strings do inversor “{nome}” têm de ser um número inteiro: nada foi gravado.")
        limpos.append({"id": D._id(i.get("id")), "chave": chave, "cabine": cab or None, "nome": nome,
                       "equipamento_supervisorio": sup, "potencia_kwp": kwp(i.get("potencia_kwp"), f"do inversor “{nome}”"),
                       "strings_esperadas_qtd": None if s is None else int(s),
                       "equipamento_id": D._id(i.get("equipamento_id")),
                       "codigo_fracttal": texto(i.get("codigo_fracttal")), "ordem": n + 1})
    return chaves, limpas, limpos


def salvar_usina(usina_id: int, dados: dict, selo_tela: str, cfg, base, sessao, quem_email: str = "",
                 info: dict | None = None) -> dict:
    """Grava a estrutura da usina como a tela mandou: o que veio com id atualiza (e só ganha `alterado_em` se mudou), o
    que veio sem id nasce com id novo, e o que estava gravado e não veio passa a excluído. Só grava se o banco ainda
    estiver como a tela abriu (`selo_tela`)."""
    if not usina_id:
        raise Recusada("Escolha a usina do Registro mestre.")
    chaves, cabs, invs = _validar(dados)

    def mudar(est, agora, quem):
        u = da_usina(est, usina_id)
        if selo(u) != selo_tela:
            raise Recusada("A estrutura desta usina mudou desde que a tela abriu (outra aba ou outra pessoa): recarregue "
                           "a página. Nada foi gravado.")
        minhas = {s["supervisorio_id"]: s for s in u["supervisorios"]}
        for i in invs:
            if i["chave"] and i["chave"] not in minhas:
                raise Recusada(f"O inversor “{i['nome']}” aponta para uma chave do supervisório que não é desta usina: "
                               "nada foi gravado.")
        mudou = 0
        for sid, novo in chaves.items():
            s = minhas.get(sid)
            if s and any(s[k] != v for k, v in novo.items()):
                s.update(novo, alterado_em=agora, alterado_por_hmac=quem)
                mudou += 1
        escolhida = next((sid for sid, c in chaves.items() if c["principal"] and sid in minhas), None)
        if escolhida:
            for s in minhas.values():
                if s["principal"] and s["supervisorio_id"] != escolhida:
                    s.update(principal=False, alterado_em=agora, alterado_por_hmac=quem)
                    mudou += 1
        gravadas = {c["cabine_id"]: c for c in u["cabines"]}
        id_da_k, prox = {}, _proximo(est["cabines"], "cabine_id")
        for c in cabs:
            novo = {k: c[k] for k in ("nome", "potencia_kwp", "equipamento_id", "codigo_fracttal", "ordem")}
            g = gravadas.pop(c["id"], None) if c["id"] else None
            if g:
                if any(g[k] != v for k, v in novo.items()):
                    g.update(novo, alterado_em=agora, alterado_por_hmac=quem)
                    mudou += 1
                id_da_k[c["k"]] = g["cabine_id"]
            else:
                est["cabines"].append(dict(novo, cabine_id=prox, usina_id=usina_id, criado_em=agora, alterado_em=agora,
                                           alterado_por_hmac=quem, excluido=False))
                id_da_k[c["k"]] = prox
                prox, mudou = prox + 1, mudou + 1
        for g in gravadas.values():                    # não veio: excluída (o ID não volta)
            g.update(excluido=True, alterado_em=agora, alterado_por_hmac=quem)
            mudou += 1
        gravados = {i["inversor_id"]: i for i in u["inversores"]}
        prox = _proximo(est["inversores"], "inversor_id")
        for i in invs:
            novo = {"supervisorio_id": i["chave"], "cabine_id": id_da_k.get(i["cabine"]) if i["cabine"] else None,
                    **{k: i[k] for k in ("nome", "equipamento_supervisorio", "potencia_kwp", "strings_esperadas_qtd",
                                         "equipamento_id", "codigo_fracttal", "ordem")}}
            g = gravados.pop(i["id"], None) if i["id"] else None
            if g:
                if any(g[k] != v for k, v in novo.items()):
                    g.update(novo, alterado_em=agora, alterado_por_hmac=quem)
                    mudou += 1
            else:
                est["inversores"].append(dict(novo, inversor_id=prox, usina_id=usina_id, criado_em=agora,
                                              alterado_em=agora, alterado_por_hmac=quem, excluido=False))
                prox, mudou = prox + 1, mudou + 1
        for g in gravados.values():
            g.update(excluido=True, alterado_em=agora, alterado_por_hmac=quem)
            mudou += 1
        depois = da_usina(est, usina_id)
        return {"mudancas": mudou, "selo": selo(depois), "resumo": resumo(depois), "usina": depois,
                "log": f"{mudou} mudança(s) na usina {usina_id}"}
    return _gravar(mudar, cfg, base, sessao, quem_email, info)


def republicar_visao(cfg, base, sessao, info: dict, quem_email: str = "") -> dict:
    """Refaz a visão com o que a tela sabe agora (o nome no Fracttal mudou nas Ligações, a potência no Registro mestre) e
    grava só se ela mudou."""
    return _gravar(lambda est, agora, quem: {"log": "conferiu a visão no formato da aba"}, cfg, base, sessao,
                   quem_email, info)

# ── Ligar pela aba Equipamentos (13/10/2026) ───────────────────────────────────────────────────────────────────────────
# Levi: "Em "Equipamentos da Usinas" ligue automaticamente pelos dados que temos na aba equipamenetos do BD_Performance!"
# (de manhã tinha sido "não quero que faça as conexões automaticamente"; o automático agora é dele, e a tela segue
# mostrando o que ligou e o que ficou de fora). O caminho é o MESMO ciclo das Ligações entre bases (08/10/2026): a
# "Usina Fractall" da aba é a Classificação 1 do Fracttal, e o de-para do Fracttal das Ligações diz a usina do Registro
# mestre. Não chuta: chave sem o nome do Fracttal, com dois nomes, com nome fora do de-para, ignorado ou de duas usinas,
# e chave que as Ligações ignoram ou ligam a OUTRA usina nas abas de geração (a "AP. do Taboado" tem na aba o nome do
# Fracttal da Aparecida do Taboado 1 e 2, mas é outra usina, fora da operação) ficam de fora, com o motivo.
SISTEMAS_ABA = ("BD_Thopen · aba", "BD_Performance · aba")


def proposta_pela_aba(aba_chaves: dict, atual: dict | None, est: dict, usinas) -> dict:
    """{"ligar": {usina_id: [chaves]}, "fora": [{chave, motivo}], "ja_ligadas": n} das chaves da aba ainda sem usina
    no livro. `atual` = o de-para calculado das Ligações (`ligacoes.ler`); `usinas` = os ids do Registro mestre."""
    from .ligacoes import FRACTTAL
    ligado, por_norma, decisao = {}, {}, {}
    for linha in (atual or {}).get("linhas") or []:
        if len(linha) < 3 or not linha[2]:
            continue
        uid, sistema, chave = D._id(linha[0]), linha[1], str(linha[2])
        como = str(linha[3] or "") if len(linha) > 3 else ""
        if sistema == FRACTTAL:
            ids, _como = ligado.setdefault(chave, (set(), como))
            if uid:
                ids.add(uid)
            por_norma.setdefault(norm(chave), set()).add(chave)
        elif sistema in SISTEMAS_ABA:
            decisao.setdefault(norm(chave), []).append((uid, como))
    dono = {s["usina_supervisorio"] for s in est["supervisorios"] if not s["excluido"]}
    # a usina que já tem estrutura gravada não recebe nada daqui (o ligar_pela_aba a pularia): a chave nova dela vai
    # para a lista, para não oferecer no botão o que ele não faz (no servidor, 13/10: "Ligar 1 chave" que não ligava)
    com_estrutura = {x["usina_id"] for k in ("supervisorios", "cabines", "inversores") for x in est.get(k) or []
                     if not x.get("excluido")}
    usinas = set(usinas)
    ligar, fora, ja = {}, [], 0
    for chave in sorted(aba_chaves, key=natural):
        if chave in dono:
            ja += 1
            continue
        nomes = sorted(set(aba_chaves[chave].get("fracttais") or ([aba_chaves[chave]["fracttal"]]
                                                                 if aba_chaves[chave].get("fracttal") else [])))
        motivo, uid = "", None
        if not nomes:
            motivo = "sem a Usina Fractall na aba"
        elif len(nomes) > 1:
            motivo = f"{len(nomes)} nomes do Fracttal na aba ({', '.join(nomes)})"
        else:
            nome = nomes[0]
            chave_fr = nome if nome in ligado else None
            if chave_fr is None:
                cands = por_norma.get(norm(nome), set())
                if len(cands) == 1:
                    chave_fr = next(iter(cands))
                else:
                    motivo = (f"o nome do Fracttal “{nome}” casa {len(cands)} chaves das Ligações" if cands
                              else f"o nome do Fracttal “{nome}” não está nas Ligações")
            if chave_fr is not None:
                ids, como = ligado[chave_fr]
                if como.startswith("ignorado"):
                    motivo = f"o nome do Fracttal está ignorado nas Ligações ({como})"
                elif len(ids) != 1:
                    motivo = (f"o nome do Fracttal “{nome}” liga a {len(ids)} usinas nas Ligações" if ids
                              else f"o nome do Fracttal “{nome}” não está ligado a nenhuma usina nas Ligações")
                else:
                    uid = next(iter(ids))
            if uid is not None:
                d = decisao.get(norm(chave), [])
                ign = next((c for _u, c in d if c.startswith("ignorado")), "")
                outra = sorted({u for u, _c in d if u and u != uid})
                if uid not in usinas:
                    motivo = "a usina do nome do Fracttal não está no Registro mestre"
                elif ign:
                    motivo = f"a chave está ignorada nas Ligações ({ign})"
                elif outra:
                    motivo = f"as Ligações ligam esta chave a outra usina (id {outra[0]})"
                elif uid in com_estrutura:
                    motivo = (f"a usina (id {uid}) já tem estrutura gravada: ligue esta chave nela e use o "
                              "“Trazer da aba”")
        if motivo:
            fora.append({"chave": chave, "motivo": motivo})
        else:
            ligar.setdefault(uid, []).append(chave)
    return {"ligar": ligar, "fora": fora, "ja_ligadas": ja}


def estrutura_da_aba(chaves: list, aba_chaves: dict) -> dict:
    """As chaves, as cabines e os inversores de UMA usina a partir da aba, como o "Trazer da aba" da tela: a chave da
    usina (UFV e cabines) é a única com a linha UFV (sem ela ou com mais de uma, a 1ª); a cabine é da usina, pelo nome
    (as UG e o Equipamento Parente dos inversores); o inversor vai pela chave dele, e o nome que outra chave já usou
    ganha a chave no nome. O mesmo nome no supervisório duas vezes na mesma chave fica só no 1º (a tela não salvaria a
    usina com os dois) e vai para os avisos."""
    chaves = sorted(chaves, key=natural)
    com_ufv = [c for c in chaves if aba_chaves[c].get("ufv_kwp") is not None]
    principal = com_ufv[0] if len(com_ufv) == 1 else chaves[0]
    sups = [{"chave": c, "exibicao": texto(aba_chaves[c].get("usina")), "principal": c == principal,
             "full_om": bool(aba_chaves[c].get("full_om")), "string_box": bool(aba_chaves[c].get("string_box"))}
            for c in chaves]
    cabs, cab_de = [], {}

    def cabine(nome, kwp=None):
        n = norm(nome)
        if n not in cab_de:
            cab_de[n] = {"nome": texto(nome), "potencia_kwp": kwp}
            cabs.append(cab_de[n])
        elif cab_de[n]["potencia_kwp"] is None and kwp is not None:
            cab_de[n]["potencia_kwp"] = kwp
        return cab_de[n]
    for c in chaves:
        for g in aba_chaves[c].get("cabines") or []:
            if texto(g.get("nome")):
                cabine(g["nome"], g.get("kwp"))
    invs, nomes, sup_vistos, avisos = [], set(), set(), []
    for c in chaves:
        for a in aba_chaves[c].get("inversores") or []:
            nome, sup = texto(a.get("nome")), texto(a.get("equipamento_supervisorio"))
            if not nome:
                continue
            if sup and (c, norm(sup)) in sup_vistos:
                avisos.append(f"{c}: “{sup}” duas vezes no supervisório (ficou o 1º)")
                continue
            if sup:
                sup_vistos.add((c, norm(sup)))
            final, k = nome, 1
            while norm(final) in nomes:
                k += 1
                final = f"{nome} · {c}" if k == 2 else f"{nome} · {c} ({k - 1})"
            nomes.add(norm(final))
            pai = cabine(a["cabine"])["nome"] if texto(a.get("cabine")) else None
            invs.append({"chave": c, "cabine": pai, "nome": final, "equipamento_supervisorio": sup,
                         "potencia_kwp": a.get("kwp"), "strings_esperadas_qtd": a.get("strings")})
    return {"supervisorios": sups, "cabines": cabs, "inversores": invs, "avisos": avisos}


def ligar_pela_aba(proposta: dict, aba_chaves: dict, cfg, base, sessao, quem_email: str = "",
                   info: dict | None = None) -> dict:
    """Grava, de uma vez, as chaves da proposta e a estrutura da aba de cada usina AINDA SEM ESTRUTURA no livro (a usina
    que já tem chave, cabine ou inversor gravado fica como está: lá vale o que foi feito à mão, e o "Trazer da aba" da
    tela completa). Nasce FORA do lugar da aba: os leitores só passam a ler do Nexus a chave que alguém marcar. Chave que
    alguém ligou enquanto isso, a outra usina, fica de fora (o livro é relido dentro da trava)."""
    def mudar(est, agora, quem):
        dono = {s["usina_supervisorio"] for s in est["supervisorios"] if not s["excluido"]}
        ps, pc, pi = (_proximo(est["supervisorios"], "supervisorio_id"), _proximo(est["cabines"], "cabine_id"),
                      _proximo(est["inversores"], "inversor_id"))
        controle = {"criado_em": agora, "alterado_em": agora, "alterado_por_hmac": quem, "excluido": False}
        usinas, n_ch, n_cab, n_inv, n_str, puladas, avisos = 0, 0, 0, 0, 0, [], []
        for uid in sorted(proposta.get("ligar") or {}):
            u = da_usina(est, uid)
            if u["supervisorios"] or u["cabines"] or u["inversores"]:
                puladas.append(uid)
                continue
            chaves = [c for c in proposta["ligar"][uid] if c not in dono and c in aba_chaves]
            if not chaves:
                continue
            e = estrutura_da_aba(chaves, aba_chaves)
            sid_de = {}
            for s in e["supervisorios"]:
                est["supervisorios"].append({"supervisorio_id": ps, "usina_id": uid, "usina_supervisorio": s["chave"],
                                             "usina_exibicao": s["exibicao"], "principal": s["principal"],
                                             "full_om": s["full_om"], "string_box": s["string_box"],
                                             "substitui_aba": False, **controle})
                sid_de[s["chave"]] = ps
                dono.add(s["chave"])
                ps += 1
            cid_de = {}
            for ordem, c in enumerate(e["cabines"], 1):
                est["cabines"].append({"cabine_id": pc, "usina_id": uid, "nome": c["nome"],
                                       "potencia_kwp": c["potencia_kwp"], "equipamento_id": None,
                                       "codigo_fracttal": "", "ordem": ordem, **controle})
                cid_de[norm(c["nome"])] = pc
                pc += 1
            for ordem, i in enumerate(e["inversores"], 1):
                est["inversores"].append({"inversor_id": pi, "usina_id": uid, "supervisorio_id": sid_de[i["chave"]],
                                          "cabine_id": cid_de.get(norm(i["cabine"])) if i["cabine"] else None,
                                          "nome": i["nome"], "equipamento_supervisorio": i["equipamento_supervisorio"],
                                          "potencia_kwp": i["potencia_kwp"],
                                          "strings_esperadas_qtd": i["strings_esperadas_qtd"], "equipamento_id": None,
                                          "codigo_fracttal": "", "ordem": ordem, **controle})
                pi += 1
                n_str += i["strings_esperadas_qtd"] or 0
            usinas, n_ch = usinas + 1, n_ch + len(chaves)
            n_cab, n_inv = n_cab + len(e["cabines"]), n_inv + len(e["inversores"])
            avisos += e["avisos"]
        return {"usinas": usinas, "chaves": n_ch, "cabines": n_cab, "inversores": n_inv, "strings": n_str,
                "puladas": puladas, "avisos": avisos,
                "log": f"ligou pela aba {n_ch} chave(s) em {usinas} usina(s), {n_cab} cabine(s), {n_inv} inversor(es)"}
    return _gravar(mudar, cfg, base, sessao, quem_email, info)

