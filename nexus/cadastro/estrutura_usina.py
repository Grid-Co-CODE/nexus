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

O dado: livro `nexus_estrutura_usina` (catálogo do Nexus), três abas de estado: `dim_supervisorio`, `dim_cabine`,
`dim_inversor`. Gravar troca o livro inteiro (relido do banco antes, sob trava: nunca a cópia de 1 minuto) e o
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
ABA_SUP, ABA_CAB, ABA_INV = "dim_supervisorio", "dim_cabine", "dim_inversor"
_CONTROLE = ("criado_em", "alterado_em", "alterado_por_hmac", "excluido")
CAB_SUP = ("supervisorio_id", "usina_id", "usina_supervisorio", "full_om", "string_box") + _CONTROLE
CAB_CAB = ("cabine_id", "usina_id", "nome", "potencia_kwp", "equipamento_id", "codigo_fracttal", "ordem") + _CONTROLE
CAB_INV = ("inversor_id", "usina_id", "supervisorio_id", "cabine_id", "nome", "equipamento_supervisorio",
           "potencia_kwp", "strings_esperadas_qtd", "equipamento_id", "codigo_fracttal", "ordem") + _CONTROLE
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
            "full_om": _sim(x.get("full_om")), "string_box": _sim(x.get("string_box")), **_controle(x)}


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
    return {"supervisorios": le(ABA_SUP, _sup), "cabines": le(ABA_CAB, _cab), "inversores": le(ABA_INV, _inv)}


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
        return {"supervisorios": [], "cabines": [], "inversores": [], "lido_em": None, "erro": erro}
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
    return {"chaves": len(u["supervisorios"]), "cabines": len(cabs), "inversores": len(invs),
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
        g = out.setdefault(chave, {"chave": chave, "usina": texto(d.get("Usina")), "fracttal": "", "cliente": "",
                                   "full_om": False, "string_box": False, "ufv_kwp": None, "ufv_inversores": None,
                                   "cabines": [], "inversores": []})
        g["fracttal"] = g["fracttal"] or texto(d.get("Usina Fractall"))
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


def _linhas_do_livro(est: dict) -> dict:
    """As três abas ordenadas pelo ID (o sha do livro não muda de máquina para máquina). Indicador como 1/0 (regra 3);
    `excluido` como na casa: "sim" ou vazio."""
    def valor(c, v):
        if c in ("full_om", "string_box"):
            return 1 if v else 0
        if c == "excluido":
            return "sim" if v else None
        return None if v in ("", None) else v

    def tab(itens, cab, chave_id):
        return (list(cab), [[valor(c, x.get(c)) for c in cab] for x in sorted(itens, key=lambda x: x[chave_id])])
    return {ABA_SUP: tab(est["supervisorios"], CAB_SUP, "supervisorio_id"),
            ABA_CAB: tab(est["cabines"], CAB_CAB, "cabine_id"),
            ABA_INV: tab(est["inversores"], CAB_INV, "inversor_id")}


def _gravar(mudar, cfg, base, sessao, quem_email: str = "") -> dict:
    """Relê o banco (nunca a cópia de 1 minuto), aplica a mudança e grava o livro inteiro se algo mudou. Sem a chave de
    gravação, ou sem conseguir ler, nada é gravado."""
    token = cfg.get("GRIDCO_SQL_TOKEN")
    if not token:
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN): nada foi gravado.")
    with _TRAVA:
        try:
            est = _ler_banco(base, sessao)
        except Exception as ex:  # noqa: BLE001
            raise Recusada(f"Não consegui ler a estrutura no banco ({type(ex).__name__}): nada foi gravado, para não "
                           "apagar o que já está lá.") from ex
        antes = copy.deepcopy(est)
        resultado = mudar(est, _agora(), _quem(cfg, quem_email))
        if est != antes:
            livros.publicar(LIVRO, NOME_LIVRO, _linhas_do_livro(est), base=base, token=token, sessao=sessao)
        _CACHE["livro"] = dict(est, lido_em=time.time(), erro="")
    log.info("Estrutura das usinas: %s, por %s.", resultado.get("log", "sem mudança"),
             quem_email or "senha de administrador")
    return resultado


def _proximo(itens, chave_id) -> int:
    return max((x[chave_id] for x in itens), default=0) + 1


def ligar_supervisorio(usina_id: int, chave: str, cfg, base, sessao, quem_email: str = "") -> dict:
    """Liga uma chave do supervisório à usina do Registro mestre. Chave ligada a OUTRA usina é recusada (uma chave, uma
    usina: é por ela que a plataforma acha a usina); ligada a esta, nada muda. A chave pode não estar na aba (usina
    nova): quem decide é a pessoa, e a tela avisa."""
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
        est["supervisorios"].append({"supervisorio_id": sid, "usina_id": usina_id, "usina_supervisorio": chave,
                                     "full_om": False, "string_box": False, "criado_em": agora, "alterado_em": agora,
                                     "alterado_por_hmac": quem, "excluido": False})
        return {"supervisorio_id": sid, "novo": True, "log": f"ligou a chave {chave} à usina {usina_id}"}
    return _gravar(mudar, cfg, base, sessao, quem_email)


def desligar_supervisorio(supervisorio_id: int, usina_id: int, cfg, base, sessao, quem_email: str = "") -> dict:
    """Tira a chave da usina (ela passa a excluída; o ID não volta). Os inversores que chegavam por ela ficam na usina,
    sem chave, à vista na tela para ganhar outra: desligar uma chave nunca apaga inversor."""
    def mudar(est, agora, quem):
        s = next((s for s in est["supervisorios"] if s["supervisorio_id"] == supervisorio_id and not s["excluido"]), None)
        if not s or s["usina_id"] != usina_id:
            raise Recusada("Esta chave já não está ligada a esta usina (a lista mudou desde que a tela abriu): nada foi "
                           "gravado.")
        s.update(excluido=True, alterado_em=agora, alterado_por_hmac=quem)
        soltos = 0
        for i in est["inversores"]:
            if i["supervisorio_id"] == supervisorio_id and not i["excluido"]:
                i.update(supervisorio_id=None, alterado_em=agora, alterado_por_hmac=quem)
                soltos += 1
        return {"chave": s["usina_supervisorio"], "usina_id": s["usina_id"], "inversores_sem_chave": soltos,
                "log": f"desligou a chave {s['usina_supervisorio']} da usina {s['usina_id']} ({soltos} inversor(es) "
                       "ficaram sem chave)"}
    return _gravar(mudar, cfg, base, sessao, quem_email)


def _validar(dados: dict) -> tuple[dict, list, list]:
    """As chaves, as cabines e os inversores que a tela mandou, limpos e conferidos entre si. Recusa nome vazio ou
    repetido na usina, o mesmo nome no supervisório duas vezes na mesma chave, cabine que não está na lista, número
    negativo ou que não é número, strings fracionadas e listas grandes demais. Se a chave é da usina, `mudar` confere."""
    chaves = {}
    for c in list(dados.get("chaves") or [])[:200]:
        sid = D._id(c.get("supervisorio_id"))
        if sid:
            chaves[sid] = (bool(c.get("full_om")), bool(c.get("string_box")))
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


def salvar_usina(usina_id: int, dados: dict, selo_tela: str, cfg, base, sessao, quem_email: str = "") -> dict:
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
        for sid, (full_om, string_box) in chaves.items():
            s = minhas.get(sid)
            if s and (s["full_om"], s["string_box"]) != (full_om, string_box):
                s.update(full_om=full_om, string_box=string_box, alterado_em=agora, alterado_por_hmac=quem)
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
    return _gravar(mudar, cfg, base, sessao, quem_email)
