"""A tela PCM → Almoxarifado (25/10/2026). Levi: "No fractall temos almoxarifado, gostaria de uma visão para a gestão
desse almoxarifado na parte de PCM"; a prévia foi aprovada no mesmo dia. Desenho:
docs/superpowers/specs/2026-10-25-almoxarifado-design.md.

A pergunta: que peça está abaixo do mínimo ou no limite, em que almoxarifado, e o que saiu nas OS? O dado é o que o App
de Campo publica da varredura diária do inventário do Fracttal (os livros e as contas em `nexus/dados/almoxarifado.py`,
as MESMAS da carga do histórico); o Nexus não chama o Fracttal.

De onde vem cada parte:
- o saldo, do ciclo mais novo dos livros do App quando os três (Ciclo, Itens, Saldo) são do mesmo ciclo e o ciclo leu
  90% da lista; senão, do último ciclo aplicado no histórico do Nexus (`nexus_almoxarifado`), com o aviso. Sem ciclo
  aplicado no Nexus (o ensaio, antes da NEXUS_ALMOX_GRAVAR), o aviso e nenhum número: número pela metade não vai à tela;
- o almoxarifado de TESTE (NEXUS_ALMOX_TESTE_IDS, 26/10/2026: a prova das gravações do inventário no Fracttal) não entra
  em nada daqui: as linhas dele saem do Saldo DEPOIS de os três livros serem conferidos como inteiros (o ciclo conta as
  do teste nas "Linhas de saldo"), senão todo ciclo com o teste viraria "chegou pela metade";
- o consumo, do `fato_peca_lancada` do Nexus (tudo desde o início, Levi, 25/10/2026); enquanto ele não existe, do livro
  Peças do App (90 dias), com a nota.

As melhorias de 30/10/2026 (docs/superpowers/specs/2026-10-30-almoxarifado-melhorias-design.md): a criticidade e a Curva
ABC do cadastro da peça no Fracttal (e o custo) vêm do App no fim dos livros Itens e Saldo. O Nexus sobe antes do App, então
"a coluna não existe no livro" (`tem_curva`, `tem_criticidade`, `tem_custo`) é diferente de "o Fracttal não deu o valor":
o primeiro não cobra nada, o segundo vai para o Cadastro a corrigir. O que o Fracttal não deu fica vazio, nunca "C" nem 0.

Avariada é UMA definição, a do `regua.avariada` (a marca Avariado do catálogo OU o código terminado em -AV): vale na aba
Avariadas, no número do alto e na etiqueta do Catálogo. A avariada com saldo não é erro de cadastro (a peça espera destino): a
aba diz há quanto tempo (`_paradas`, pelos ciclos aplicados do histórico).
"""
from datetime import datetime, timedelta, timezone

from flask import current_app, render_template

from ..cadastro.tipos import exibir
from ..campo import visao
from ..dados import almoxarifado as A
from ..dados import fato_almoxarifado as F
from ..dados import livros
from ..dados.dominios import norm
from .inventario import regua, revisao

TELA = "pecas"
_RECUSA = "recusada"


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _num(v) -> float:
    return A.numero(v) or 0.0


def _campo(v) -> str:
    """O texto de um campo do cadastro da peça: o vazio que o `sync-xlsx` do App escreve como "None" (ou o "nan") é
    vazio, não a palavra. A criticidade "None" na tela seria um nível que o Fracttal não deu."""
    t = _txt(v)
    return "" if t.lower() in ("none", "nan") else t


# o ID sem o ".0" que a API às vezes põe ("7.0" é o 7): o mesmo da dimensão de dados, que a carga e o filtro do teste usam
_id = A._id


def _abas(livro) -> dict:
    return visao._ciclo(("_abas", livro), lambda: livros.abas(visao._base(), visao._sessao(), livro))


def _quando(iso) -> str:
    d = visao._dt(iso)
    return d.astimezone(timezone(timedelta(hours=-3))).strftime("%d/%m, %H:%M") if d else "?"


def _dia(data_id) -> str:
    t = _id(data_id)
    return f"{t[6:8]}/{t[4:6]}/{t[:4]}" if len(t) == 8 else ""


# ── as duas fontes do saldo, no mesmo formato ─────────────────────────────────────────────────────────────────────────

def _do_app(ciclo: dict, itens: list[dict], saldo: list[dict], b) -> dict:
    its = {_id(i.get("ID do item")): {"codigo": _txt(i.get("Código")), "nome": _txt(i.get("Nome")),
                                       "unidade": _txt(i.get("Unidade")), "familia": _txt(i.get("Família")),
                                       "avariado": _txt(i.get("Avariado")).lower() == "sim",
                                       "nao_lido": _txt(i.get("Lido")).lower() == "não",
                                       "criticidade": _campo(i.get("Criticidade")),
                                       "curva": A.curva_abc(i.get("Curva ABC"))} for i in itens}
    linhas = [{"id_item": _id(s.get("ID do item")), "id_almox": _id(s.get("ID do almoxarifado")),
               "almox": _txt(s.get("Almoxarifado")), "usina_id": b.lig.usina_do_fracttal(
                   A.chave_do_local(s.get("Local do almoxarifado")) or ""),
               "saldo": A.numero(s.get("Saldo")), "minimo": A.numero(s.get("Mínimo")),
               "custo": A.custo(s.get("Custo unitário"))} for s in saldo]
    # "tem" é a coluna existir no livro (o App de antes não a manda), e não ela ter valor: o livro sem a coluna não é
    # cobrado no Cadastro a corrigir, o com a coluna e a peça sem valor é
    return {"inicio": _txt(ciclo.get(A.INICIO)), "fim": _txt(ciclo.get("Fim do ciclo")),
            "lidos": ciclo.get("Itens lidos"), "total": ciclo.get("Itens na lista do Fracttal"), "itens": its,
            "linhas": linhas, "tem_criticidade": bool(itens) and "Criticidade" in itens[0],
            "tem_curva": bool(itens) and "Curva ABC" in itens[0], "tem_custo": bool(saldo) and "Custo unitário" in saldo[0]}


def _do_nexus(ult: dict, abas_nx: dict, teste: frozenset | set = frozenset()) -> dict | None:
    """O último ciclo aplicado no histórico: a foto dele no livro do mês e as dimensões do Nexus. `teste`: os
    almoxarifados de teste (a carga não grava mais as linhas deles, mas o ID pode ser posto depois de uma já gravada)."""
    mes = F.livro_do_mes(int(float(_id(ult.get("data_id")))))
    if F.ABA_SALDO not in _abas(mes):
        return None
    inicio = _txt(ult.get("ciclo_inicio"))
    foto = [l for l in visao._livro(mes, F.ABA_SALDO)
            if _txt(l.get("ciclo_inicio")) == inicio and _id(l.get("id_almoxarifado")) not in teste]
    almox = {_id(a.get("id_almoxarifado")): _txt(a.get("nome"))
             for a in (visao._livro(F.LIVRO, F.ABA_DIM_ALMOX) if F.ABA_DIM_ALMOX in abas_nx else [])}
    # só os itens que estão na foto (a revisão de 25/10/2026): a dimensão guarda todo item já visto, inclusive os
    # desativados há meses, e o item não lido no ciclo apareceria como "sem saldo em nenhum almoxarifado"
    na_foto = {_id(l.get("id_item")) for l in foto}
    dim = visao._livro(F.LIVRO, F.ABA_DIM_ITEM) if F.ABA_DIM_ITEM in abas_nx else []
    its = {_id(i.get("id_item")): {"codigo": _txt(i.get("codigo")), "nome": _txt(i.get("nome")),
                                    "unidade": _txt(i.get("unidade")), "familia": _txt(i.get("familia")),
                                    "avariado": _txt(i.get("avariado")) in ("1", "1.0"), "nao_lido": False,
                                    "criticidade": _campo(i.get("criticidade")),
                                    "curva": A.curva_abc(i.get("curva_abc"))}
           for i in dim if _id(i.get("id_item")) in na_foto}
    linhas = [{"id_item": _id(l.get("id_item")), "id_almox": _id(l.get("id_almoxarifado")),
               "almox": almox.get(_id(l.get("id_almoxarifado")), _id(l.get("id_almoxarifado"))),
               "usina_id": int(float(_id(l.get("usina_id")))) if _id(l.get("usina_id")) else None,
               "saldo": A.numero(l.get("saldo_qtd")), "minimo": A.numero(l.get("minimo_qtd")),
               "custo": A.custo(l.get("custo_unitario_brl"))} for l in foto]
    # No histórico a chave da coluna não diz se o App a mandou: a carga grava as colunas novas (vazias) mesmo com o livro
    # do App de antes, e a dimensão e o livro do mês as têm desde o Nexus novo. Então "tem" é a chave existir E ao menos
    # uma peça trazer valor: o histórico em que nenhuma peça jamais teve curva (ou custo) é o App que não a manda, e
    # cobrar "todas as peças sem Curva ABC" no Cadastro a corrigir seria cobrar o que o Fracttal nem foi perguntado
    def tem(linhas: list[dict], chave: str) -> bool:
        return any(_txt(l.get(chave)) not in ("", "None", "nan") for l in linhas)

    return {"inicio": inicio, "fim": _txt(ult.get("fim")), "lidos": ult.get("itens_lidos_qtd"),
            "total": ult.get("itens_lista_qtd"), "itens": its, "linhas": linhas,
            "tem_criticidade": tem(dim, "criticidade"), "tem_curva": tem(dim, "curva_abc"),
            "tem_custo": tem(foto, "custo_unitario_brl")}


# ── as partes da tela ────────────────────────────────────────────────────────────────────────────────────────────────

def _usina(b, uid) -> str | None:
    u = b.por_id.get(uid) if uid else None
    return _txt(u.get("nome")) if u else None


def _situacao(saldo, minimo) -> str:
    """A situação de uma peça num almoxarifado, na tela: a `A.situacao` (que o histórico também usa e não muda) com o
    SALDO UNITÁRIO separado do "no limite" (Levi, 30/10/2026). Mínimo 1 e saldo 1 é quase todo o "no limite" (a peça que
    ninguém pediu para repor): a próxima saída zera, mas não é pedido de compra por si, e misturada escondia as que
    estão no limite de verdade (saldo 2 e mínimo 2 continua no limite)."""
    sit = A.situacao(saldo, minimo)
    return "saldo_unitario" if sit == "no_limite" and A.numero(saldo) == 1 else sit


_CURVA_N = {"A": 0, "B": 1, "C": 2}


def _ordem(x: dict) -> tuple:
    """A ordem DENTRO de um grupo da Reposição (o grupo vem antes: abaixo do mínimo, no limite, saldo unitário; um crítico
    no limite não passa à frente de uma peça comum abaixo): a criticidade (1.Crítico primeiro; sem número por último), a
    curva (A, B, C; sem curva por último) e, depois, a chave de sempre do grupo (abaixo: a mais longe do mínimo; os
    outros: almoxarifado e código). Sem criticidade nem curva no livro, é a ordem de antes."""
    base = (x["crit_n"] or 99, _CURVA_N.get(x["curva"], 3))
    return base + ((-x["falta"],) if x["situacao"] == "abaixo" else (x["almox"], x["codigo"]))


def _partes(fonte: dict, b) -> dict:
    its, out = fonte["itens"], []
    for l in fonte["linhas"]:
        i = its.get(l["id_item"], {})
        sit = _situacao(l["saldo"], l["minimo"])
        # saldo vazio (o Fracttal não deu o número) é "não informado": fora da Reposição e das contas (a revisão de
        # 25/10/2026: virava "abaixo, falta 2" e uma "zerada" no cartão)
        cod, nome = i.get("codigo") or l["id_item"], i.get("nome", "")
        crit_n, crit_nome = revisao._criticidade(i.get("criticidade"))
        out.append(dict(l, codigo=cod, nome=nome, familia=i.get("familia", ""), unidade=(i.get("unidade") or "").lower(),
                        avariado=i.get("avariado", False), avariada=regua.avariada(cod, i.get("avariado", False)),
                        situacao=sit, usina=_usina(b, l["usina_id"]),
                        falta=max((l["minimo"] or 0) - l["saldo"], 0) if l["saldo"] is not None else 0,
                        busca=norm(f"{cod} {nome}"), criticidade=i.get("criticidade", ""), crit_n=crit_n,
                        crit_nome=crit_nome, crit_nivel=min(crit_n, 4) if crit_n else None, curva=i.get("curva", ""),
                        custo=l.get("custo")))
    abaixo = sorted((x for x in out if x["situacao"] == "abaixo"), key=_ordem)
    limite = sorted((x for x in out if x["situacao"] == "no_limite"), key=_ordem)
    unitario = sorted((x for x in out if x["situacao"] == "saldo_unitario"), key=_ordem)
    for x in abaixo + limite + unitario:
        x["pct"] = min(100, round(100 * x["saldo"] / x["minimo"])) if x["minimo"] else 0
    cards = {}
    for x in out:
        c = cards.setdefault(x["id_almox"], {"id": x["id_almox"], "nome": x["almox"], "usina": x["usina"], "pecas": 0,
                                             "abaixo": 0, "no_limite": 0, "saldo_unitario": 0, "sem_minimo": 0,
                                             "zeradas": 0, "ok": 0, "nao_informado": 0})
        c["pecas"] += 1
        c["abaixo"] += x["situacao"] == "abaixo"
        c["no_limite"] += x["situacao"] == "no_limite"
        c["saldo_unitario"] += x["situacao"] == "saldo_unitario"
        c["sem_minimo"] += not (x["minimo"] and x["minimo"] > 0)
        c["zeradas"] += x["saldo"] == 0
        c["ok"] += x["situacao"] == "ok"
        c["nao_informado"] += x["situacao"] == "nao_informado"
    for c in cards.values():
        c["pct_ok"] = round(100 * c["ok"] / c["pecas"]) if c["pecas"] else 0
    catalogo = []
    for iid, i in its.items():
        onde = [x for x in out if x["id_item"] == iid and (x["saldo"] or 0) > 0]
        catalogo.append(dict(i, id=iid, avariado=regua.avariada(i.get("codigo") or iid, i.get("avariado", False)),
                             total=sum(x["saldo"] for x in onde), almoxes=[x["almox"] for x in onde],
                             onde=[f"{x['almox']}: {x['saldo']:g}" for x in onde],
                             busca=norm(f"{i.get('codigo', '')} {i.get('nome', '')}")))
    catalogo.sort(key=lambda c: (c["familia"], c["codigo"]))
    sem_min = {}
    for x in out:
        if not (x["minimo"] and x["minimo"] > 0) and x["situacao"] != "nao_informado":
            sem_min[x["almox"]] = sem_min.get(x["almox"], 0) + 1
    # as peças COM saldo sem curva (ou sem criticidade) no Fracttal: completar é lá. None = o livro nem traz a coluna
    # ainda (o App de antes), e aí não há o que cobrar
    com_saldo = {x["id_item"] for x in out if (x["saldo"] or 0) > 0}

    def sem(campo: str, tem) -> int | None:
        return sum(1 for iid in com_saldo if not its.get(iid, {}).get(campo)) if tem else None

    kpis = {"almoxarifados": len(cards), "com_saldo": len(com_saldo),
            "abaixo": len(abaixo), "no_limite": len(limite), "saldo_unitario": len(unitario),
            "sem_minimo": sum(sem_min.values())}      # as avariadas (peça × almoxarifado com saldo) são contadas em `_avariadas`
    return {"kpis": kpis, "reposicao": abaixo + limite, "saldo_unitario": unitario, "linhas": out,
            "por_almoxarifado": sorted(cards.values(), key=lambda c: c["nome"]), "catalogo": catalogo,
            "tem_criticidade": fonte.get("tem_criticidade", False), "tem_curva": fonte.get("tem_curva", False),
            "tem_custo": fonte.get("tem_custo", False),
            "cadastro": {"sem_minimo": [{"almoxarifado": a, "n": n} for a, n in sorted(sem_min.items())],
                         "sem_curva": sem("curva", fonte.get("tem_curva")),
                         "sem_criticidade": sem("criticidade", fonte.get("tem_criticidade"))}}


def _paradas(chaves: set, hoje) -> dict:
    """Há quanto tempo cada (id_item, id_almox) está com saldo, SEM interrupção, pelos ciclos aplicados do histórico do Nexus
    (`nexus_almoxarifado`: a foto do Saldo de cada ciclo, um livro por mês). Anda do ciclo mais novo para trás enquanto o
    saldo da peça ali for maior que zero; o primeiro ciclo dessa corrida é o `desde`. `hoje` é a data (BRT) do cálculo.

    O que NUNCA se inventa é a data de entrada: a foto é de um ciclo por dia, não de cada saída. Se o saldo já era maior que
    zero no primeiro ciclo do histórico, a parada é "há pelo menos N dias" (`pelo_menos`, com o `inicio` do histórico), porque
    antes dele não se sabe. Saldo zero, vazio ou a peça fora da foto de um ciclo interrompe a corrida (o que não foi medido não
    vira "continuou com saldo"); o ciclo anulado não conta nem interrompe, nem vale como começo do histórico; o ciclo aplicado
    SEM nenhuma linha no livro do mês (livro que não veio) também é pulado, e não interrompe.

    Chave que não deu corrida (sem ciclo aplicado, ou o saldo de hoje ainda não está no histórico) fica fora do resultado:
    a tela diz "sem histórico ainda" em vez de chutar uma data. Sai: {chave: {"desde", "dias", "pelo_menos", "inicio"}}."""
    if not chaves or F.ABA_CICLO not in _abas(F.LIVRO):
        return {}
    bons = {_txt(c.get("ciclo_inicio")): _id(c.get("data_id")) for c in visao._livro(F.LIVRO, F.ABA_CICLO)
            if _txt(c.get("situacao")) == "aplicado" and _id(c.get("anulado")) != "1" and _id(c.get("data_id"))}
    fotos = {}
    for mes in sorted({F.livro_do_mes(int(float(d))) for d in bons.values()}):
        if F.ABA_SALDO not in _abas(mes):
            continue
        for l in visao._livro(mes, F.ABA_SALDO):
            inicio = _txt(l.get("ciclo_inicio"))
            if inicio not in bons:
                continue
            foto = fotos.setdefault(inicio, {})
            chave = (_id(l.get("id_item")), _id(l.get("id_almoxarifado")))
            if chave in chaves:
                foto[chave] = A.numero(l.get("saldo_qtd"))
    ordem = sorted(fotos)                  # o início é um ISO com o mesmo formato: a ordem do texto é a do tempo
    if not ordem:
        return {}
    out = {}
    for chave in chaves:
        corrida = []
        for inicio in reversed(ordem):
            saldo = fotos[inicio].get(chave)
            if saldo is None or saldo <= 0:
                break
            corrida.append(inicio)
        if corrida:
            primeiro = corrida[-1]
            dia = datetime.strptime(bons[primeiro], "%Y%m%d").date()
            out[chave] = {"desde": _dia(bons[primeiro]), "dias": max((hoje - dia).days, 0),
                          "pelo_menos": primeiro == ordem[0], "inicio": _dia(bons[ordem[0]])}
    return out


def _avariadas(linhas: list[dict], tem_custo: bool, hoje) -> list[dict]:
    """A aba Avariadas: cada peça avariada (a definição do `regua.avariada`) COM saldo, num almoxarifado, e há quanto tempo
    ela está parada ali; a mais parada primeiro (sem histórico por último). O valor é saldo × custo unitário só quando o livro
    traz o custo e o Fracttal o deu: sem ele, vazio, nunca 0."""
    av = [x for x in linhas if x["avariada"] and (x["saldo"] or 0) > 0]
    paradas = _paradas({(x["id_item"], x["id_almox"]) for x in av}, hoje)
    out = []
    for x in av:
        p = paradas.get((x["id_item"], x["id_almox"]), {})
        valor = round(x["saldo"] * x["custo"], 2) if tem_custo and x["custo"] is not None else None
        out.append({"id_item": x["id_item"], "id_almox": x["id_almox"], "codigo": x["codigo"], "nome": x["nome"],
                    "familia": x["familia"], "unidade": x["unidade"], "almox": x["almox"], "usina": x["usina"],
                    "saldo": x["saldo"], "custo": x["custo"], "valor": valor,
                    "valor_txt": exibir("moeda", valor) if valor is not None else "", "busca": x["busca"],
                    "dias": p.get("dias"), "desde": p.get("desde", ""), "pelo_menos": p.get("pelo_menos", False),
                    "inicio": p.get("inicio", "")})
    out.sort(key=lambda a: (a["dias"] is None, -(a["dias"] or 0), a["codigo"], a["almox"]))
    return out


def _consumo(pecas_nx: list[dict] | None, pecas_app: list[dict], fonte: dict) -> tuple[list[dict], str]:
    its = fonte["itens"] if fonte else {}
    nomes = {l["id_almox"]: l["almox"] for l in (fonte or {}).get("linhas", [])}
    out = []
    if pecas_nx is not None:
        for p in pecas_nx:
            lancada = _id(p.get("lancada")) == "1"
            out.append({"data_id": _id(p.get("data_id")), "os": _txt(p.get("os")), "id_item": _id(p.get("id_item")),
                        "codigo": _txt(p.get("codigo")), "quantidade": _num(p.get("quantidade_qtd")),
                        "id_almox": _id(p.get("id_almoxarifado")),
                        "situacao": "lançada" if lancada else _RECUSA, "recusa": _txt(p.get("recusa"))})
        origem = "nexus"
    else:
        for p in pecas_app:
            iso = _txt(p.get("Usada em")) or _txt(p.get("Recebido em"))
            d = visao._dt(iso)
            out.append({"data_id": d.astimezone(timezone(timedelta(hours=-3))).strftime("%Y%m%d") if d else "",
                        "os": _txt(p.get("OS")), "id_item": _id(p.get("ID do item")), "codigo": _txt(p.get("Código")),
                        "quantidade": _num(p.get("Quantidade")), "id_almox": _id(p.get("ID do almoxarifado")),
                        "situacao": "lançada" if _txt(p.get("Situação")).lower() == "lançada" else _RECUSA,
                        "recusa": _txt(p.get("Motivo da recusa")) or ("outro" if _txt(p.get("Situação")).lower()
                                                                       != "lançada" else "")})
        origem = "app"
    for c in out:
        i = its.get(c["id_item"], {})
        c.update(nome=i.get("nome", ""), familia=i.get("familia", ""), almox=nomes.get(c["id_almox"], c["id_almox"]),
                 dia=_dia(c["data_id"]), busca=norm(f"{c['codigo']} {i.get('nome', '')} {c['os']}"))
    out.sort(key=lambda c: (c["data_id"], c["os"]))
    return out, origem


def montar():
    """Tudo o que a tela mostra (cópia de 5 min e renovada por trás, como as telas do Campo)."""
    def calcular():
        abas_app = {l: _abas(l) for l in (A.LIVRO_CICLO, A.LIVRO_ITENS, A.LIVRO_SALDO, A.LIVRO_PECAS)}
        if not all(abas_app[l] for l in (A.LIVRO_CICLO, A.LIVRO_ITENS, A.LIVRO_SALDO)):
            return {"estado": "sem_livro"}
        ciclo, itens = visao._livro(A.LIVRO_CICLO, A.ABA_CICLO), visao._livro(A.LIVRO_ITENS, A.ABA_ITENS)
        saldo = visao._livro(A.LIVRO_SALDO, A.ABA_SALDO)
        pecas_app = visao._livro(A.LIVRO_PECAS, A.ABA_PECAS) if abas_app[A.LIVRO_PECAS] else []
        abas_nx = _abas(F.LIVRO)
        b, aviso = visao._Base(), ""
        ciclos = visao._livro(F.LIVRO, F.ABA_CICLO) if F.ABA_CICLO in abas_nx else []
        anulados = {_txt(c.get("ciclo_inicio")) for c in ciclos if _id(c.get("anulado")) == "1"}
        bons = [c for c in ciclos if _txt(c.get("situacao")) == "aplicado" and _id(c.get("anulado")) != "1"]
        inicio = A.ciclo_comum(ciclo, itens, saldo)
        # por que o ciclo do App não serve (a revisão de 25/10/2026: os livros que chegaram pela metade e o ciclo
        # anulado no Nexus também vão para a reserva)
        porque = ("Os livros do App chegaram de ciclos diferentes" if not inicio
                  else f"Os livros do App chegaram pela metade ({A.conferir_ciclo(ciclo, itens, saldo)})"
                  if A.conferir_ciclo(ciclo, itens, saldo)
                  else "O último ciclo do App leu menos de 90% dos itens" if not A.completo(ciclo[0])
                  else f"O ciclo de {_quando(inicio)} foi anulado no Nexus" if inicio in anulados else "")
        cfg = current_app.config
        if not porque:
            # o teste sai AGORA, depois de `conferir_ciclo` (que conta as linhas do livro inteiro)
            fonte = _do_app(ciclo[0], itens, A.sem_almoxarifado_de_teste(saldo, cfg), b)
            antes = [c for c in bons if _txt(c.get("ciclo_inicio")) != inicio]
            n_antes = A.numero(max(antes, key=lambda c: _txt(c.get("ciclo_inicio"))).get("itens_lista_qtd")) if antes \
                else None
            n_agora = A.numero(fonte["total"])
            if n_antes and n_agora is not None and n_agora < A.COMPLETUDE_MIN * n_antes:
                aviso = (f"O Fracttal listou {n_agora:g} itens, {n_antes - n_agora:g} a menos que no ciclo anterior: "
                         "confira se o catálogo foi limpo.")
        else:
            fonte = _do_nexus(max(bons, key=lambda c: _txt(c.get("ciclo_inicio"))), abas_nx,
                              A.ids_de_teste(cfg)) if bons else None
            if not fonte:
                return {"estado": "incoerente",
                        "aviso": f"{porque}, e o Nexus ainda não guardou um ciclo bom: nenhum número até o próximo."}
            aviso = f"{porque}: mostrando o saldo de {_quando(fonte['inicio'])}."
        fim = visao._dt(fonte["fim"] or fonte["inicio"])
        if fim and visao._agora() - fim > timedelta(hours=A.CICLO_VELHO_H):
            aviso = (aviso + " " if aviso else "") + (f"Saldo de {_quando(fonte['fim'] or fonte['inicio'])}: a "
                                                       "varredura do App não publicou desde então.")
        d = _partes(fonte, b)
        d["avariadas"] = _avariadas(d["linhas"], d["tem_custo"], visao._agora().date())
        d["kpis"]["avariadas"] = len(d["avariadas"])
        pecas_nx = visao._livro(F.LIVRO, F.ABA_PECA) if F.ABA_PECA in abas_nx else None
        d["consumo"], d["consumo_fonte"] = _consumo(pecas_nx, pecas_app, fonte)
        d["kpis"]["lancadas"] = sum(1 for c in d["consumo"] if c["situacao"] == "lançada")
        d["kpis"]["recusadas"] = sum(1 for c in d["consumo"] if c["situacao"] == _RECUSA)
        d["cadastro"]["recusadas"] = [c for c in d["consumo"] if c["situacao"] == _RECUSA]
        n = (lambda v: f"{A.numero(v):g}" if A.numero(v) is not None else "?")        # "574.0" da API vira "574"
        d.update(estado="ok", aviso=aviso, ciclo={"fim": _quando(fonte["fim"] or fonte["inicio"]),
                                                  "lidos": n(fonte["lidos"]), "total": n(fonte["total"])},
                 almoxarifados=sorted({x["almox"] for x in d["linhas"]}),
                 familias=sorted({i["familia"] for i in fonte["itens"].values() if i["familia"]}))
        return d
    return visao._ler(("pcm_almoxarifado",), calcular)


def registrar(bp) -> None:
    @bp.route(f"/{TELA}", endpoint=TELA)
    def tela():
        g = montar()
        # quantas contagens do inventário esperam o PCM (o número da aba Inventário); fora da conta guardada de 5 min, porque o
        # estado vem dos eventos e muda a cada revisão. Sem ler o livro, a aba segue sem número
        return render_template("pcm/almoxarifado.html", d=g.dados or {}, erro=g.erro,
                               inventario_a_revisar=revisao.a_revisar(current_app.config))

