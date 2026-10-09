"""A estrutura de O&M de 10/2026 no cadastro (Levi, 08/10/2026, sobre a "Nova Estrutura O&M Equipe": "pode adaptar,
deixa as vagas preparadas"): as regiões de campo, com a vaga de Supervisor de Campo e a de Coordenador, e, em cada equipe
volante, o código (E-01 a E-40) e a região. Carga ÚNICA, do CSV da estrutura (fora do git, porque é organograma interno:
`C:\\GridcoAuto\\nexus\\estrutura_campo_2026-10.csv`), pela `ferramentas/importar_estrutura_campo.py`; depois disso a
estrutura se edita na tela (Base → Regiões de campo e a ficha da equipe).

As regras são as da casa (nexus/dados/CLAUDE.md, regra 4: não chutar):
- a equipe do CSV casa com a do cadastro pelo nome EXATO; sem ele, pelo nome sem acento, sem caixa e sem espaço, e só
  quando é UMA equipe viva. Duas equipes com o nome, nenhuma, só uma excluída, ou o código já em outra equipe: vai para
  a lista "fora", com o motivo, e nada é gravado nela (o conserto é no cadastro, não no palpite);
- região que já existe (pelo nome) é reaproveitada: rodar de novo não duplica, e quem já foi posto nela fica;
- pessoa nunca vem do CSV: a região nasce com as duas vagas abertas (vazio = vaga);
- grava no armazém LOCAL do cadastro, pelo serviço (versão, selo, auditoria e histórico, como a tela). O banco recebe
  na publicação de sempre (`ferramentas/publicar_cadastro.py`).
"""
import csv
import io
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .esquema import VINCULO_COORDENADOR_CAMPO, VINCULO_SUPERVISOR_CAMPO
from .tipos import Legado

COLUNAS = ("regiao_campo", "base_regiao", "codigo_equipe", "equipe", "base_equipe")
QUEM = "estrutura de campo 10/2026"
STATUS_OPERACAO = "OPERAÇÃO"
SEM_REGIAO = "Sem região de campo"


class EstruturaErro(ValueError):
    """O CSV não é o da estrutura (coluna faltando, equipe ou código repetido, região com duas bases)."""


def ler_csv(texto: str) -> list[dict]:
    """As linhas do CSV (';', UTF-8 com ou sem BOM), conferidas: as cinco colunas, cada equipe e cada código uma vez só,
    e cada região com uma base só (senão a região nasceria com a base da linha que viesse primeiro)."""
    leitor = csv.DictReader(io.StringIO(texto.lstrip("\ufeff")), delimiter=";")
    faltam = [c for c in COLUNAS if c not in (leitor.fieldnames or [])]
    if faltam:
        raise EstruturaErro("faltam colunas no CSV: " + ", ".join(faltam))
    linhas = [{c: str(l.get(c) or "").strip() for c in COLUNAS} for l in leitor if any((l.get(c) or "").strip()
                                                                                     for c in COLUNAS)]
    for c in ("regiao_campo", "codigo_equipe", "equipe"):
        vazias = [i + 2 for i, l in enumerate(linhas) if not l[c]]
        if vazias:
            raise EstruturaErro(f"coluna {c} vazia nas linhas {vazias}")
    for c in ("codigo_equipe", "equipe"):
        rep = [k for k, n in Counter(_norm(l[c]) for l in linhas).items() if n > 1]
        if rep:
            raise EstruturaErro(f"{c} repetido no CSV: {', '.join(sorted(rep))}")
    bases = defaultdict(set)
    for l in linhas:
        bases[l["regiao_campo"]].add(l["base_regiao"])
    duas = sorted(r for r, b in bases.items() if len(b) > 1)
    if duas:
        raise EstruturaErro(f"região com mais de uma base no CSV: {', '.join(duas)}")
    return linhas


def _norm(s) -> str:
    """Sem acento, sem caixa e sem espaço: "SP Norte  01" e "sp norte 01" são o mesmo nome; "SP Norte 1" não."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", "", s)


@dataclass
class Plano:
    regioes: list = field(default_factory=list)      # {"nome", "base", "ordem", "id" (a que já existe) ou None}
    casadas: list = field(default_factory=list)      # {"codigo", "equipe_csv", "equipe_id", "nome_cadastro", "regiao",
    #                                                     "como" (exato | normalizado), "muda": {campo: (antes, depois)}}
    fora: list = field(default_factory=list)         # {"codigo", "equipe_csv", "regiao", "motivo"}
    usinas_por_regiao: dict = field(default_factory=dict)   # {região: usinas em OPERAÇÃO pela equipe} (+ SEM_REGIAO)
    vinculos_faltando: list = field(default_factory=list)
    avisos: list = field(default_factory=list)


def planejar(srv, linhas: list[dict]) -> Plano:
    """O que a carga faria, sem gravar nada (é o ensaio, e a mesma conta que o `aplicar` usa)."""
    plano = Plano()
    existentes = {_norm(r.valores.get("nome")): r for r in srv.registros("regioes_campo")}
    ordem = []
    for l in linhas:
        if l["regiao_campo"] not in ordem:
            ordem.append(l["regiao_campo"])
    base_de = {l["regiao_campo"]: l["base_regiao"] for l in linhas}
    for i, nome in enumerate(ordem, start=1):
        r = existentes.get(_norm(nome))
        plano.regioes.append({"nome": nome, "base": base_de[nome], "ordem": i, "id": r.id if r else None})
        if r and str(r.valores.get("base") or "") != base_de[nome]:
            plano.avisos.append(f"A região {nome} já existe com outra base ({r.valores.get('base') or 'vazia'}); "
                                f"fica a do Nexus.")
    id_da_regiao = {x["nome"]: x["id"] for x in plano.regioes}

    vivas = srv.registros("equipes")
    excluidas = [e for e in srv.registros("equipes", incluir_excluidos=True) if e.excluido]
    exato, normal = defaultdict(list), defaultdict(list)
    for e in vivas:
        exato[str(e.valores.get("nome") or "").strip()].append(e)
        normal[_norm(e.valores.get("nome"))].append(e)
    dono_do_codigo = {_norm(e.valores.get("codigo")): e for e in vivas if e.valores.get("codigo")}
    usadas = {}
    for l in linhas:
        item = {"codigo": l["codigo_equipe"], "equipe_csv": l["equipe"], "regiao": l["regiao_campo"]}
        cands, como = exato.get(l["equipe"], []), "exato"
        if not cands:
            cands, como = normal.get(_norm(l["equipe"]), []), "normalizado"
        if len(cands) != 1:
            if cands:
                motivo = f"{len(cands)} equipes do cadastro com esse nome ({como})"
            elif any(_norm(e.valores.get("nome")) == _norm(l["equipe"]) for e in excluidas):
                motivo = "só uma equipe EXCLUÍDA do cadastro tem esse nome"
            else:
                motivo = "nenhuma equipe do cadastro com esse nome"
            plano.fora.append({**item, "motivo": motivo})
            continue
        e = cands[0]
        dono = dono_do_codigo.get(_norm(l["codigo_equipe"]))
        if dono is not None and dono.id != e.id:
            plano.fora.append({**item, "motivo": f"o código {l['codigo_equipe']} já é da equipe {dono.titulo} "
                                                 f"(ID {dono.id})"})
            continue
        if e.id in usadas:
            plano.fora.append({**item, "motivo": f"a equipe do cadastro {e.titulo} já casou com {usadas[e.id]}"})
            continue
        usadas[e.id] = l["equipe"]
        muda = {}
        if str(e.valores.get("codigo") or "") != l["codigo_equipe"]:
            muda["codigo"] = (e.valores.get("codigo"), l["codigo_equipe"])
        reg_atual = e.valores.get("regiao_campo")
        reg_nova = id_da_regiao[l["regiao_campo"]]
        if reg_nova is None or reg_atual != reg_nova:
            muda["regiao_campo"] = (reg_atual.texto if isinstance(reg_atual, Legado) else reg_atual, l["regiao_campo"])
        plano.casadas.append({**item, "equipe_id": e.id, "nome_cadastro": e.titulo, "como": como, "muda": muda})

    # quantas usinas em OPERAÇÃO ficam em cada região, pela equipe da usina, já com a carga (a região que a equipe tem
    # hoje vale para quem não casou com o CSV)
    nome_da_regiao = {r.id: r.titulo for r in srv.registros("regioes_campo")}
    regiao_da_equipe = {e.id: nome_da_regiao.get(e.valores.get("regiao_campo")) for e in vivas
                        if isinstance(e.valores.get("regiao_campo"), str)}
    regiao_da_equipe.update({c["equipe_id"]: c["regiao"] for c in plano.casadas})
    conta = Counter()
    for u in srv.registros("usinas"):
        if u.valores.get("status") == STATUS_OPERACAO:
            conta[regiao_da_equipe.get(u.valores.get("equipe")) or SEM_REGIAO] += 1
    plano.usinas_por_regiao = {r["nome"]: conta.get(r["nome"], 0) for r in plano.regioes}
    plano.usinas_por_regiao[SEM_REGIAO] = conta.get(SEM_REGIAO, 0)
    plano.vinculos_faltando = [v for v in (VINCULO_SUPERVISOR_CAMPO, VINCULO_COORDENADOR_CAMPO)
                               if v not in srv.listas().get("vinculo", [])]
    return plano


def foto(srv) -> dict:
    """{entidade: {id: (versão, excluído, valores)}} e as listas: o retrato para conferir antes × depois."""
    out = {eid: {r.id: (r.versao, r.excluido, {k: (v.texto if isinstance(v, Legado) else v) for k, v in r.valores.items()})
                 for r in srv.registros(eid, incluir_excluidos=True)}
           for eid in ("usinas", "pessoas", "clientes", "equipes", "regioes_campo")}
    out["listas"] = {k: list(v) for k, v in srv.listas().items()}
    return out


def aplicar(srv, plano: Plano, quem: str = QUEM) -> dict:
    """Grava pelo serviço, como a tela grava (versão, selo, auditoria, histórico): os vínculos novos na lista, as regiões
    que faltam (com as vagas abertas) e o código e a região de cada equipe casada. Erro numa equipe não para as outras:
    volta em "erros"."""
    for v in plano.vinculos_faltando:
        srv.adicionar_valor("vinculo", v, quem=quem)
    ids, erros = {}, []
    for r in plano.regioes:
        if r["id"]:
            ids[r["nome"]] = r["id"]
            continue
        res = srv.criar("regioes_campo", {"nome": r["nome"], "base": r["base"]}, quem=quem)
        if not res.ok:
            erros.append(f"região {r['nome']}: {res.erros}")
            continue
        ids[r["nome"]] = res.registro.id
    gravadas = 0
    for c in plano.casadas:
        if c["regiao"] not in ids:
            erros.append(f"equipe {c['equipe_csv']}: a região {c['regiao']} não foi criada")
            continue
        e = srv.registro("equipes", c["equipe_id"])
        res = srv.salvar("equipes", e.id, {"codigo": c["codigo"], "regiao_campo": ids[c["regiao"]]}, e.versao,
                         quem=quem)
        if not res.ok:
            erros.append(f"equipe {c['equipe_csv']}: {res.erros}")
            continue
        gravadas += bool(res.mudou)
    return {"regioes": ids, "equipes_gravadas": gravadas, "erros": erros}


def conferir(srv, plano: Plano, antes: dict) -> list[str]:
    """Depois de gravar: as regiões do CSV existem (as novas com as duas vagas abertas), cada equipe casada tem o código e
    a região, e o resto ficou como estava: usinas, pessoas e clientes com a mesma versão e os mesmos valores, as equipes
    que não casaram iguais, e as casadas mudaram só no código e na região. Toda linha com o selo conferindo. Lista vazia =
    conferido."""
    depois, problemas = foto(srv), []
    regs = {r.titulo: r for r in srv.registros("regioes_campo")}
    for r in plano.regioes:
        reg = regs.get(r["nome"])
        if reg is None:
            problemas.append(f"região {r['nome']} não está no cadastro")
        elif r["id"] is None and (reg.valores.get("supervisor_campo") or reg.valores.get("coordenador_campo")):
            problemas.append(f"região nova {r['nome']} nasceu com alguém no cargo (devia nascer vaga)")
    for c in plano.casadas:
        e = srv.registro("equipes", c["equipe_id"])
        rid = e.valores.get("regiao_campo")
        if e.valores.get("codigo") != c["codigo"] or not isinstance(rid, str) or srv.titulo_de("regioes_campo", rid) != c["regiao"]:
            problemas.append(f"equipe {c['equipe_csv']} sem o código ou a região da carga")
    for eid in ("usinas", "pessoas", "clientes"):
        if antes[eid] != depois[eid]:
            mudou = sorted(set(antes[eid]) ^ set(depois[eid])) or [i for i in antes[eid] if antes[eid][i] != depois[eid].get(i)]
            problemas.append(f"{eid} mudou ({len(mudou)} registro(s)): devia ficar intacto")
    casadas = {c["equipe_id"] for c in plano.casadas}
    if set(antes["equipes"]) != set(depois["equipes"]):
        problemas.append("o conjunto de equipes mudou")
    for i, (versao, excl, vals) in antes["equipes"].items():
        dv = depois["equipes"].get(i)
        if dv is None:
            continue
        if i not in casadas and dv != (versao, excl, vals):
            problemas.append(f"equipe {i} não casou e mudou")
        elif i in casadas and ({k: v for k, v in vals.items() if k not in ("codigo", "regiao_campo")}
                               != {k: v for k, v in dv[2].items() if k not in ("codigo", "regiao_campo")} or dv[1] != excl):
            problemas.append(f"equipe {i} mudou além do código e da região")
    for k, v in antes["listas"].items():
        if k != "vinculo" and depois["listas"].get(k) != v:
            problemas.append(f"a lista {k} mudou")
    faltam = [v for v in (VINCULO_SUPERVISOR_CAMPO, VINCULO_COORDENADOR_CAMPO)
              if v not in depois["listas"].get("vinculo", [])]
    if faltam:
        problemas.append("a lista de vínculos não tem " + ", ".join(faltam))
    sem_selo = [f"{eid} {r.id}" for eid in ("usinas", "pessoas", "clientes", "equipes", "regioes_campo")
                for r in srv.registros(eid, incluir_excluidos=True) if not r.selo_ok]
    if sem_selo:
        problemas.append(f"{len(sem_selo)} linha(s) com o selo que não confere")
    return problemas
