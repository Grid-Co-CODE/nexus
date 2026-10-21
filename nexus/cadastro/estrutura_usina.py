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

O de-para do tempo real (20/10/2026, Levi: "Boa, é isso mesmo. Implementa no tempo real"): o "Modo de-para" da
plataforma grava aqui, pelas rotas da torre Base (`salvar_depara`), um REMENDO de uma ou mais chaves: a chave ligada à
usina do Registro mestre (a que o livro ainda não tem nasce semeada pela aba, como no "Ligar pela aba"), as strings
corretas, a cabine (sempre a CABN do Fracttal, "UG NN"), o ativo do Fracttal do inversor (o `equipamento_id` derivado do
código e conferido na dimensão de equipamento) e o Conferido; o kWp da usina inteira é recalculado pela regra do Levi.
A chave só passa a valer no lugar da aba se, depois do remendo, ela difere da aba APENAS pela regra do de-para (strings,
cabine pela CABN, o kWp que a regra calculou, a UFV do Registro e o "N de Inversores" contado; `fora_da_regra`), e a
usina vale por inteiro ou nada (`_marcar`, 21/10/2026): as chaves dela que seguem com a aba marcam juntas ou nenhuma,
sem exceção, e a já marcada cuja visão o salvar mudou numa usina segura volta para a aba. O resto grava, não marca e vai
nos avisos. A chave fora da aba e do livro (a "Nova chave"), a usina com uma chave irmã da aba fora do livro e, com a
chave da UFV valendo, mover de cabine os inversores de uma chave que segue com a aba são recusados. Nunca exclui o que
não veio (a diferença para o Salvar da tela); só sai a cabine sem código do Fracttal e sem inversor no Nexus (e nem ela
se ficaria órfã nos leitores). A linhagem vai em três colunas no fim (`potencia_regra`, `fracttal_ligado_por`, `conferido_em`, listas em
`nexus/dados/dominios.py`), e a visão ganhou o "Código Fracttal".
"""
import contextlib
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

from ..dados import dominios as DOM
from ..dados import equipamento as EQ
from ..dados import fatos as D
from ..dados import livros

log = logging.getLogger(__name__)

LIVRO, NOME_LIVRO = "nexus_estrutura_usina", "Nexus · estrutura das usinas"
ABA_SUP, ABA_CAB, ABA_INV, ABA_VISAO = "dim_supervisorio", "dim_cabine", "dim_inversor", "aba_equipamentos"
_CONTROLE = ("criado_em", "alterado_em", "alterado_por_hmac", "excluido")
CAB_SUP = ("supervisorio_id", "usina_id", "usina_supervisorio", "usina_exibicao", "principal", "full_om", "string_box",
           "substitui_aba") + _CONTROLE
# as colunas do de-para do tempo real (20/10/2026) vão no FIM, depois do controle: quem lê o livro por posição (o BI, a
# leitura aberta do banco) não se perde, como o `banco.COLUNAS_NO_FIM` do cadastro. A linha gravada antes delas é lida
# com elas vazias
CAB_CAB = ("cabine_id", "usina_id", "nome", "potencia_kwp", "equipamento_id", "codigo_fracttal", "ordem") + _CONTROLE + (
    "potencia_regra",)
CAB_INV = ("inversor_id", "usina_id", "supervisorio_id", "cabine_id", "nome", "equipamento_supervisorio",
           "potencia_kwp", "strings_esperadas_qtd", "equipamento_id", "codigo_fracttal", "ordem") + _CONTROLE + (
    "potencia_regra", "fracttal_ligado_por", "conferido_em")
# fora do selo da usina: o controle e a data do Conferido (data pode voltar do banco escrita de outro jeito e daria
# mudança falsa; quem conferiu de novo muda também o `fracttal_ligado_por`, que está no selo)
_FORA_DO_SELO = _CONTROLE + ("usina_id", "conferido_em")
# a visão: as colunas da aba Equipamentos que os leitores usam, com o MESMO nome ("Chave" e "Chave 2" são as
# concatenações que a aba tem; "Observações" é texto livre e fica fora: regra 8), e os IDs do Nexus no fim. O "Código
# Fracttal" (20/10/2026) vem depois dos IDs: o código do ativo da linha do inversor e da UG, que a aba não tem (a
# plataforma derivava o do inversor pelo nome, e na Pharma II isso dava THPN-PHS200-INVR1.1 em vez do THPN-PHS100-INVR2.1
# que o Fracttal tem hoje). Leitor antigo, que pega as colunas pelo nome dele, ignora a coluna a mais
CAB_VISAO = ("Cliente", "Usina", "Usina Supervisório", "Usina Fractall", "Equipamento", "Equipamento Supervisório",
             "Equipamento Parente", "Chave", "Chave 2", "Potência (kWp)", "N de Inversores", "String Box", "Full O&M",
             "Strings Ativas", "usina_id", "supervisorio_id", "cabine_id", "inversor_id", "Código Fracttal")
ABA_EQUIPAMENTOS = ("bd_performance", "Equipamentos")
ABA_ATIVOS = ("nexus_equipamentos", "dim_equipamento")
TTL_S, TTL_ABA_S, TTL_ATIVOS_S = 60, 600, 3600
MAX_CABINES, MAX_INVERSORES, MAX_TEXTO = 300, 3000, 120
_TRAVA = threading.Lock()
_CACHE: dict = {}
# os salvar do de-para em curso neste processo, da chegada do pedido à resposta (2ª revisão final, 21/10/2026). O waitress
# serve em threads, e o pedido que o navegador abandonou (o estouro de 180 s, o 502/504 do proxy) CONTINUA aqui: o estado
# relido na hora devolvia o selo de antes (o GET não espera a trava), a tela concluía "está como antes: salve de novo", e
# segundos depois o Nexus gravava (provado com o livros.publicar segurado: selo 716a75e1… no meio, c36f51a4… depois). O
# estado diz `gravando` (este contador ou a trava ocupada por qualquer gravação do livro) e a tela espera
_EM_CURSO = {"n": 0}
_EM_CURSO_TRAVA = threading.Lock()


@contextlib.contextmanager
def em_curso():
    """Conta um pedido de gravação do de-para enquanto ele roda (inclusive a leitura da aba e da dimensão, antes da trava)."""
    with _EM_CURSO_TRAVA:
        _EM_CURSO["n"] += 1
    try:
        yield
    finally:
        with _EM_CURSO_TRAVA:
            _EM_CURSO["n"] -= 1


def gravando() -> bool:
    """Há gravação do livro em curso neste processo (um salvar do de-para ou qualquer gravação sob a trava)."""
    return _EM_CURSO["n"] > 0 or _TRAVA.locked()


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê, para a tela mostrar. `status` é o HTTP que a rota JSON do de-para devolve:
    400 o pedido torto, 409 o conflito com o que está gravado (o selo velho, a chave de outra usina, o código do Fracttal
    em outro inversor), 503 o banco fora ou o Nexus sem a chave de gravação. `usina_id` e `usina_supervisorio` dizem a
    usina (e a chave) CULPADA quando a recusa é de uma só (20/10/2026): o de-para manda até 50 chaves de várias usinas
    num pedido, e uma recusa derrubava o lote inteiro sem dizer qual (a Cambé pela chave "Cambé" levava junto as outras);
    com a culpada, a tela tira essa usina do lote e reenvia o resto."""

    def __init__(self, texto: str = "", status: int = 400, usina_id=None, usina_supervisorio: str = ""):
        super().__init__(texto)
        self.status = status
        self.usina_id = usina_id
        self.usina_supervisorio = usina_supervisorio or ""


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
            "codigo_fracttal": texto(x.get("codigo_fracttal")), "ordem": _int(x.get("ordem")) or 0, **_controle(x),
            "potencia_regra": DOM.da_lista(x.get("potencia_regra"), DOM.POTENCIA_REGRA)}


def _inv(x: dict):
    iid, nome = D._id(x.get("inversor_id")), texto(x.get("nome"))
    if not iid or not nome:
        return None
    return {"inversor_id": iid, "usina_id": D._id(x.get("usina_id")), "supervisorio_id": D._id(x.get("supervisorio_id")),
            "cabine_id": D._id(x.get("cabine_id")), "nome": nome,
            "equipamento_supervisorio": texto(x.get("equipamento_supervisorio")),
            "potencia_kwp": _num(x.get("potencia_kwp")), "strings_esperadas_qtd": _int(x.get("strings_esperadas_qtd")),
            "equipamento_id": D._id(x.get("equipamento_id")), "codigo_fracttal": texto(x.get("codigo_fracttal")),
            "ordem": _int(x.get("ordem")) or 0, **_controle(x),
            "potencia_regra": DOM.da_lista(x.get("potencia_regra"), DOM.POTENCIA_REGRA),
            "fracttal_ligado_por": DOM.da_lista(x.get("fracttal_ligado_por"), DOM.FRACTTAL_LIGADO_POR),
            "conferido_em": D._txt(x.get("conferido_em"))}


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
    do negócio (os de controle, como a data, podem voltar do banco escritos de outro jeito e dariam mudança falsa).
    As colunas de 20/10/2026 entram (menos a data do Conferido): o selo de toda usina mudou uma vez, no deploy delas,
    e a aba aberta antes pede para recarregar."""
    def so_negocio(itens, cab):
        return [[x.get(c) for c in cab if c not in _FORA_DO_SELO] for x in itens]
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
    (UG) saem na chave da usina; cada inversor, na chave dele. Inversor sem chave não sai (não é de leitor nenhum).
    Cabine cujo nome não é "UG NN" não sai como linha de UG (20/10/2026): o "Ligar pela aba" trouxe do "Equipamento
    Parente" da aba uma cabine "UFV" (Aparecida do Taboado, usina 11) e uma "PEI" (usina 85), e a linha de Equipamento
    "UFV" com o kWp da cabine seria lida pela plataforma e pelas Falhas como a própria usina (458 kWp no lugar de 2.422).
    O inversor dela segue com o "Equipamento Parente" que tem, como na aba."""
    info_u = info_u or {}
    pega = [s for s in u["supervisorios"] if todas or s["substitui_aba"]]
    # o nome do Fracttal vai COMO o Fracttal escreve (só sem as pontas), nunca com o `texto` (2ª revisão final,
    # 21/10/2026): o índice de code-base da plataforma (`_frac_codebase_index`) guarda a description exata do Fracttal, e a
    # Belo Jardim (usina 32) é "Thopen - Belo Jardim  1 - PE", com espaço DUPLO, na aba, no Fracttal e nas Ligações; com os
    # espaços juntados a usina marcada ficava "fora do Fracttal" (sem OS abertas, sem a cascata de queda) sem aviso
    cliente, fr = texto(info_u.get("cliente")) or None, str(info_u.get("fracttal") or "").strip() or None
    n_na_cab = Counter(i["cabine_id"] for i in u["inversores"] if i["cabine_id"])
    cab = {c["cabine_id"]: c for c in u["cabines"]}
    ugs = [c for c in u["cabines"] if _numero_da_ug(c["nome"]) is not None]
    out = []
    for s in pega:
        disp = exibicao(s, info_u) or s["usina_supervisorio"]
        comum = {"Cliente": cliente, "Usina": disp, "Usina Fractall": fr, "String Box": "Sim" if s["string_box"] else "Não",
                 "Full O&M": "Sim" if s["full_om"] else "Não", "usina_id": s["usina_id"],
                 "supervisorio_id": s["supervisorio_id"]}
        if s["principal"]:
            sup = "" if norm(s["usina_supervisorio"]) == norm(disp) else s["usina_supervisorio"]
            kwp = info_u.get("kwp")
            if kwp is None and any(c["potencia_kwp"] is not None for c in ugs):
                kwp = round(sum(c["potencia_kwp"] or 0 for c in ugs), 3)
            out.append(dict(comum, **{"Usina Supervisório": sup or None, "Equipamento": "UFV", "Chave 2": f"{sup}UFV",
                                      "Potência (kWp)": kwp, "N de Inversores": len(u["inversores"]) or None}))
            for c in ugs:
                out.append(dict(comum, **{"Usina Supervisório": sup or None, "Equipamento": c["nome"],
                                          "Equipamento Parente": "UFV", "Chave 2": f"{sup}{c['nome']}",
                                          "Potência (kWp)": c["potencia_kwp"],
                                          "N de Inversores": n_na_cab.get(c["cabine_id"]) or None,
                                          "cabine_id": c["cabine_id"],
                                          "Código Fracttal": c.get("codigo_fracttal") or None}))
        for i in u["inversores"]:
            if i["supervisorio_id"] != s["supervisorio_id"]:
                continue
            eq, esup, chave = nome_de_inversor(i["nome"]), i["equipamento_supervisorio"], s["usina_supervisorio"]
            c = cab.get(i["cabine_id"])
            out.append(dict(comum, **{"Usina Supervisório": chave, "Equipamento": eq, "Equipamento Supervisório": esup or None,
                                      "Equipamento Parente": c["nome"] if c else None,
                                      "Chave": f"{chave}{esup}" if esup else None, "Chave 2": f"{chave}{eq}",
                                      "Potência (kWp)": i["potencia_kwp"], "Strings Ativas": i["strings_esperadas_qtd"],
                                      "cabine_id": i["cabine_id"], "inversor_id": i["inversor_id"],
                                      "Código Fracttal": i.get("codigo_fracttal") or None}))
    return [{c: x.get(c) for c in CAB_VISAO} for x in out]


def visao_aba(est: dict, info: dict | None) -> list[dict]:
    """A visão inteira: as usinas com alguma chave "no lugar da aba", na ordem do ID (o sha não muda de máquina)."""
    usinas = sorted({s["usina_id"] for s in est["supervisorios"] if not s["excluido"] and s["substitui_aba"]})
    return [x for uid in usinas for x in visao_da_usina(da_usina(est, uid), (info or {}).get(uid))]


def _campo_da_chave(linha: dict) -> str:
    """A coluna de onde sai a chave da linha (`chave_efetiva`): "Usina Supervisório" e, vazia, "Usina"."""
    return "Usina Supervisório" if texto(linha.get("Usina Supervisório")) else "Usina"


def sobrepor(linhas_aba, linhas_visao) -> list[dict]:
    """A aba com as chaves da visão trocadas: tira da aba as linhas de UFV, UG e inversor das chaves que a visão traz e
    põe as da visão. É o mesmo que cada leitor da aba faz do lado dele (a plataforma, o gêmeo, o coletor).

    A linha da visão HERDA a grafia da aba quando a chave bate pelo `texto` (20/10/2026): o Nexus guarda a chave com
    espaço único, e a aba e a API PV escrevem "Assis Chateaubriand  Skid 1 (79)", com espaço DUPLO. A plataforma busca o
    cadastro pela grafia exata da fonte (o `us` do `load_equipamentos`, só com `strip`): com a grafia do Nexus, a Skid 1
    marcada perdia as strings esperadas, o kWp, o nome de exibição e o Full O&M no tempo real, sem aviso. A grafia é a da
    1ª linha da aba com aquela chave; o "Chave" (a chave + o nome no supervisório) acompanha.
    O "Usina Fractall" também herda (2ª revisão final, 21/10/2026): a plataforma acha a usina no índice do Fracttal pela
    description EXATA, e a "Thopen - Belo Jardim  1 - PE" (espaço duplo) escrita com os espaços juntados deixava a Belo
    Jardim marcada "fora do Fracttal". Vale a grafia da aba da MESMA chave quando o `texto` bate (só os espaços mudam);
    nome de outra letra (acento) não herda: a comparação acusa e a chave não marca."""
    visao = list(linhas_visao or ())
    chaves = {chave_efetiva(x) for x in visao}
    if not chaves:
        return list(linhas_aba or ())
    grafia, fracttal = {}, {}
    for x in linhas_aba or ():
        k = chave_efetiva(x)
        if k in chaves and k not in grafia:
            grafia[k] = str(x.get(_campo_da_chave(x)))
        fr = x.get("Usina Fractall")
        if k in chaves and isinstance(fr, str) and fr.strip():
            fracttal.setdefault((k, texto(fr)), fr.strip())
    fica = [x for x in linhas_aba or () if chave_efetiva(x) not in chaves or not _tipo_linha(x.get("Equipamento"))]
    out = []
    for x in visao:
        k, campo = chave_efetiva(x), _campo_da_chave(x)
        g = grafia.get(k)
        if g is not None and g != x.get(campo):
            antes, x = str(x.get(campo) or ""), dict(x, **{campo: g})
            if campo == "Usina Supervisório" and str(x.get("Chave") or "").startswith(antes):
                x["Chave"] = g + str(x["Chave"])[len(antes):]
            if campo == "Usina Supervisório" and str(x.get("Chave 2") or "").startswith(antes):
                x["Chave 2"] = g + str(x["Chave 2"])[len(antes):]
        fr = fracttal.get((k, texto(x.get("Usina Fractall"))))
        if fr is not None and fr != x.get("Usina Fractall"):
            x = dict(x, **{"Usina Fractall": fr})
        out.append(x)
    return fica + out


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
    linhas da visão dela. {"na_aba", "iguais", "n", "dif": [textos] (até 40), "itens": [{tipo, texto, cabine_id?,
    inversor_id?}] (todas)}. Compara só o que a aba tem: o "Código Fracttal" da visão (20/10/2026) não existe na aba, e
    a chave com o ativo ligado continua "igual à aba". O `tipo` de cada diferença (20/10/2026) é o que o de-para do tempo
    real usa para saber se ela vem da regra dele (`fora_da_regra`): o texto é para gente, o tipo é para a conta."""
    if g is None:
        t = "A chave não está na aba Equipamentos: marcada, os leitores passam a conhecê-la só pelo Nexus."
        return {"na_aba": False, "iguais": False, "n": 1, "dif": [t], "itens": [{"tipo": "fora_da_aba", "texto": t}]}
    itens = []

    def poe(texto_, tipo, **ids):
        itens.append(dict(ids, tipo=tipo, texto=texto_))

    def num(v):
        x = _num(v)
        return None if x is None else round(x, 2)

    def txt(rotulo, a, n, tipo, **ids):
        if norm(a) != norm(n):
            poe(f"{rotulo}: “{a or '—'}” na aba, “{n or '—'}” no Nexus.", tipo, **ids)

    def val(rotulo, a, n, tipo, **ids):
        if (a is None) != (n is None) or (a is not None and abs(a - n) > 0.05):
            poe(f"{rotulo}: {a if a is not None else '—'} na aba, {n if n is not None else '—'} no Nexus.", tipo, **ids)
    ufv = next((x for x in linhas if x["Equipamento"] == "UFV"), None)
    ugs = [x for x in linhas if x.get("cabine_id") and not x.get("inversor_id")]
    invs = [x for x in linhas if x.get("inversor_id")]
    um = linhas[0] if linhas else {}
    if linhas:
        # o nome de exibição de TODA linha da chave na aba (2ª revisão final, 21/10/2026): na Taguaí (usina 136) a 1ª
        # linha da "Taguaí 1 (173)" é uma UFV solta com Usina = "Taguaí 1 (173)" e os inversores dizem "Taguaí"; a visão
        # escreve um nome só na chave inteira, e comparar só com a 1ª deixava a chave marcar com o USINA_GRUPO trocado
        # (as duas plantas deixavam de se juntar no macro e na Entrada, e as Falhas perdiam o cadastro do inversor)
        for a in g.get("usinas") or [g["usina"]]:
            txt("Nome de exibição", a, um.get("Usina"), "exibicao")
        # o nome do Fracttal pelo `texto` sem caixa, e não pelo `norm`: a diferença só de espaços o `sobrepor` resolve
        # (herda a grafia da aba), mas a de acento ("Taguai" × "Taguaí") vira outra description no índice do Fracttal da
        # plataforma, e a usina marcada ficaria "fora do Fracttal" sem aviso (a Belo Jardim, 2ª revisão final de 20/10)
        fa, fn = texto(g["fracttal"]), texto(um.get("Usina Fractall"))
        if fa.lower() != fn.lower():
            poe(f"Nome no Fracttal: “{fa or '—'}” na aba, “{fn or '—'}” no Nexus.", "fracttal")
        txt("Cliente", g["cliente"], um.get("Cliente"), "cliente")
        if g["full_om"] != (um.get("Full O&M") == "Sim"):
            poe(f"Full O&M: {'Sim' if g['full_om'] else 'Não'} na aba, {um.get('Full O&M')} no Nexus.", "full_om")
        if g["string_box"] != (um.get("String Box") == "Sim"):
            poe(f"String Box: {'Sim' if g['string_box'] else 'Não'} na aba, {um.get('String Box')} no Nexus.",
                "string_box")
    if g["ufv_kwp"] is not None or ufv:
        if not ufv:
            poe(f"A linha da usina (UFV, {g['ufv_kwp']} kWp) está nesta chave na aba; no Nexus, esta não é a chave da "
                "usina.", "ufv_em_outra_chave")
        elif g["ufv_kwp"] is None and not g["cabines"]:
            poe("No Nexus esta é a chave da usina (UFV e cabines); na aba, a linha da usina fica em outra chave.",
                "ufv_em_outra_chave")
        else:
            val("Potência da usina (kWp)", num(g["ufv_kwp"]), num(ufv["Potência (kWp)"]), "kwp_usina")
            val("Inversores da usina", g["ufv_inversores"], _int(ufv["N de Inversores"]), "inversores_usina")
    if g["cabines"] or ugs:
        a = {norm(c["nome"]): c for c in g["cabines"]}
        n = {norm(x["Equipamento"]): x for x in ugs}
        for k in a.keys() - n.keys():
            poe(f"Cabine {a[k]['nome']} está na aba e não no Nexus.", "cabine_so_na_aba")
        for k in n.keys() - a.keys():
            poe(f"Cabine {n[k]['Equipamento']} está no Nexus e não na aba.", "cabine_so_no_nexus",
                cabine_id=n[k]["cabine_id"])
        for k in a.keys() & n.keys():
            val(f"Cabine {a[k]['nome']} (kWp)", num(a[k]["kwp"]), num(n[k]["Potência (kWp)"]), "kwp_cabine",
                cabine_id=n[k]["cabine_id"])

    def chave_inv(sup, nome):
        return ("s", norm(sup)) if sup else ("n", norm(nome))
    a = {chave_inv(i["equipamento_supervisorio"], i["nome"]): i for i in g["inversores"]}
    n = {chave_inv(x["Equipamento Supervisório"], x["Equipamento"]): x for x in invs}
    for k in sorted(a.keys() - n.keys(), key=lambda k: natural(k[1])):
        i = a[k]
        poe(f"{i['equipamento_supervisorio'] or i['nome']} ({i['nome']}) está na aba e não no Nexus.",
            "inversor_so_na_aba")
    for k in sorted(n.keys() - a.keys(), key=lambda k: natural(k[1])):
        x = n[k]
        poe(f"{x['Equipamento Supervisório'] or x['Equipamento']} ({x['Equipamento']}) está no Nexus e não na aba.",
            "inversor_so_no_nexus", inversor_id=x["inversor_id"])
    for k in sorted(a.keys() & n.keys(), key=lambda k: natural(k[1])):
        i, x = a[k], n[k]
        quem, ids = i["equipamento_supervisorio"] or i["nome"], {"inversor_id": x["inversor_id"]}
        txt(f"{quem}: nome", i["nome"], x["Equipamento"], "nome_inversor", **ids)
        txt(f"{quem}: cabine", i["cabine"], x["Equipamento Parente"], "cabine_do_inversor", cabine_id=x["cabine_id"],
            **ids)
        val(f"{quem}: kWp", num(i["kwp"]), num(x["Potência (kWp)"]), "kwp_inversor", **ids)
        val(f"{quem}: strings", i["strings"], _int(x["Strings Ativas"]), "strings_inversor", **ids)
    dif = [x["texto"] for x in itens]
    return {"na_aba": True, "iguais": not dif, "n": len(dif),
            "dif": dif[:40] + ([f"... e mais {len(dif) - 40} diferenças."] if len(dif) > 40 else []), "itens": itens}


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
    as cabines (UG: nome, kWp, inversores) e os inversores (nome, nome no supervisório, cabine, kWp, strings).
    A usina de exibição (`usina`) é a das linhas de INVERSOR quando a chave tem (2ª revisão final, 21/10/2026): na Taguaí a
    1ª linha da "Taguaí 1 (173)" é uma UFV solta com Usina = "Taguaí 1 (173)", e os inversores dizem "Taguaí"; o "Ligar
    pela aba" guardava a da UFV solta e o USINA_GRUPO dos leitores trocava. `usinas` = todos os nomes da chave na aba, na
    ordem (a comparação acusa a chave em que eles não são um só)."""
    out = {}
    for d in linhas or ():
        chave = texto(d.get("Usina Supervisório")) or texto(d.get("Usina"))
        tipo = _tipo_linha(d.get("Equipamento"))
        if not chave or not tipo:
            continue
        g = out.setdefault(chave, {"chave": chave, "usina": texto(d.get("Usina")), "usinas": [], "fracttal": "",
                                   "fracttais": [], "cliente": "", "full_om": False, "string_box": False,
                                   "ufv_kwp": None, "ufv_inversores": None, "cabines": [], "inversores": []})
        exib = texto(d.get("Usina"))
        if exib and exib not in g["usinas"]:
            g["usinas"].append(exib)
        if tipo == "inversor" and exib and not g["inversores"]:
            g["usina"] = exib
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


def dimensao(base: str, sessao) -> dict:
    """{"por_codigo": {código canônico: {equipamento_id, codigo, usina_id, familia}}, "por_usina": {usina_id: [ativos]},
    "lido_em", "erro"}: a dimensão de equipamento do Nexus (`nexus_equipamentos · dim_equipamento`: os ativos do
    Fracttal, já com a usina pelo código), guardada por 1 hora. São ~22 mil linhas (5 s na 1ª leitura, 13/10/2026).
    O `por_codigo` leva também o ativo SEM usina: os 41 THPN-PHS100 da Pharmas (a árvore nova do Fracttal, fora da foto de
    22/09) não ligam a usina nenhuma pelo código e são justamente os que o de-para vai gravar. Falha = a última boa com o
    erro, ou vazio com o erro."""
    c = _CACHE.get("ativos")
    if c and time.time() - c["lido_em"] < TTL_ATIVOS_S:
        return c
    try:
        a = livros.abas(base, sessao, ABA_ATIVOS[0])
        linhas = livros._linhas(base, sessao, a[ABA_ATIVOS[1]]) if ABA_ATIVOS[1] in a else []
        por, por_codigo = {}, {}
        for d in linhas:
            uid, eid, cod = D._id(d.get("usina_id")), D._id(d.get("equipamento_id")), EQ.canon(d.get("codigo"))
            if cod:
                por_codigo[cod] = {"equipamento_id": eid, "codigo": cod, "usina_id": uid,
                                   "familia": texto(d.get("familia"))}
            if uid and eid:
                por.setdefault(uid, []).append({"equipamento_id": eid, "codigo": texto(d.get("codigo")),
                                                "descricao": texto(d.get("descricao")),
                                                "familia": texto(d.get("familia"))})
        c = {"por_usina": por, "por_codigo": por_codigo, "lido_em": time.time(), "erro": ""}
        _CACHE["ativos"] = c
        return c
    except Exception as ex:  # noqa: BLE001
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        return dict(c, erro=erro) if c else {"por_usina": {}, "por_codigo": {}, "lido_em": None, "erro": erro}


def ativos_da_usina(base: str, sessao, usina_id: int) -> dict:
    """{"ativos": [{equipamento_id, codigo, descricao, familia}], "erro"} da dimensão de equipamento (`dimensao`): a tela
    pede só quando a usina abre, depois de desenhar. Inversor é a família INVR (2.071 ativos); cabine, CABN ou SKID."""
    c = dimensao(base, sessao)
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
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN): nada foi gravado.", 503)
    with _TRAVA:
        try:
            est = _ler_banco(base, sessao)
        except Exception as ex:  # noqa: BLE001
            raise Recusada(f"Não consegui ler a estrutura no banco ({type(ex).__name__}): nada foi gravado, para não "
                           "apagar o que já está lá.", 503) from ex
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


def _regra_da_tela(g, kwp) -> str:
    """A linhagem do kWp que o Salvar da tela Base > Equipamentos grava: o mesmo número que estava gravado guarda a regra
    dele (o kWp que o de-para calculou e a tela devolveu sem mexer segue "real_por_string"); número novo é o digitado
    (o "Distribuir potência" inclusive), "informada"; sem número, vazio."""
    if g is not None and g.get("potencia_kwp") == kwp:
        return g.get("potencia_regra") or ""
    return "informada" if kwp is not None else ""


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
            novo["potencia_regra"] = _regra_da_tela(g, novo["potencia_kwp"])
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
            novo["potencia_regra"] = _regra_da_tela(g, novo["potencia_kwp"])
            # o ativo do Fracttal que a tela devolveu igual guarda a linhagem do de-para; trocado aqui, ela não vale mais
            # (o Conferido era daquele código)
            mesmo = bool(g) and g["codigo_fracttal"] == novo["codigo_fracttal"]
            novo.update(fracttal_ligado_por=g["fracttal_ligado_por"] if mesmo else "",
                        conferido_em=g["conferido_em"] if mesmo else "")
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
                # o kWp vem da aba: sem linhagem (vazio), como os 1.932 inversores ligados assim em 13/10/2026
                est["cabines"].append({"cabine_id": pc, "usina_id": uid, "nome": c["nome"],
                                       "potencia_kwp": c["potencia_kwp"], "equipamento_id": None,
                                       "codigo_fracttal": "", "ordem": ordem, **controle, "potencia_regra": ""})
                cid_de[norm(c["nome"])] = pc
                pc += 1
            for ordem, i in enumerate(e["inversores"], 1):
                est["inversores"].append({"inversor_id": pi, "usina_id": uid, "supervisorio_id": sid_de[i["chave"]],
                                          "cabine_id": cid_de.get(norm(i["cabine"])) if i["cabine"] else None,
                                          "nome": i["nome"], "equipamento_supervisorio": i["equipamento_supervisorio"],
                                          "potencia_kwp": i["potencia_kwp"],
                                          "strings_esperadas_qtd": i["strings_esperadas_qtd"], "equipamento_id": None,
                                          "codigo_fracttal": "", "ordem": ordem, **controle, "potencia_regra": "",
                                          "fracttal_ligado_por": "", "conferido_em": ""})
                pi += 1
                n_str += i["strings_esperadas_qtd"] or 0
            usinas, n_ch = usinas + 1, n_ch + len(chaves)
            n_cab, n_inv = n_cab + len(e["cabines"]), n_inv + len(e["inversores"])
            avisos += e["avisos"]
        return {"usinas": usinas, "chaves": n_ch, "cabines": n_cab, "inversores": n_inv, "strings": n_str,
                "puladas": puladas, "avisos": avisos,
                "log": f"ligou pela aba {n_ch} chave(s) em {usinas} usina(s), {n_cab} cabine(s), {n_inv} inversor(es)"}
    return _gravar(mudar, cfg, base, sessao, quem_email, info)


# ── O de-para do tempo real (20/10/2026) ──────────────────────────────────────────────────────────────────────────────
# Levi, 20/10/2026, com o protótipo do "Modo de-para": "Boa, é isso mesmo. Implementa no tempo real e adapta na base o
# de-para". A plataforma (o tempo real e a Base · De-para de equipamentos) lê o estado pela rota `/depara/estado` e grava
# pela `/depara/salvar` (telas_equipamentos.py), na mesma origem, como administrador: um REMENDO por chave do
# supervisório, nunca a usina inteira. Caso que criou: a Itajá (RN) estava sem de-para ("Itaja 1 (228)" na API PV ×
# "Itaja 1 (551)" no cadastro), e strings, cabine e ativo do Fracttal só mudavam editando a aba Equipamentos. A ponte da
# fonte para a chave continua no livro da plataforma (`nexus_depara`): um escritor por livro.
MAX_DEPARA = 50
_CABN = re.compile(r"CABN0*(\d+)$")
_INVR = re.compile(r"INVR(\d+(?:\.\d+)?)$")
# a regra do kWp diz de qual potência do Registro mestre saiu (decisão 3 do Levi, alterada em 20/10/2026: "onde não tem
# potência real, vai usar potência contratual"; as 68 usinas sem a real têm a contratual, na mesma unidade, MWp)
REGRA_DO_REGISTRO = {"real": "real_por_string", "contratual": "contratual_por_string"}
# os avisos do salvar vão como {usina_id, usina_supervisorio, tipo, texto} (o contrato com a plataforma, 20/10/2026): o
# texto é para gente; o `tipo` é curto e ESTÁVEL, para a tela agrupar e decidir (mudar um nome aqui quebra a tela).
# `usina_supervisorio` vazio = o aviso é da usina inteira (o kWp, uma cabine)
TIPOS_AVISO = ("semeada_pela_aba", "nao_marcada", "sem_potencia", "sem_strings", "cabine_fora_do_padrao",
               "cabine_excluida", "cabine_sem_inversores")


def _aviso(usina_id, chave, tipo: str, texto_: str) -> dict:
    assert tipo in TIPOS_AVISO, tipo
    return {"usina_id": usina_id, "usina_supervisorio": chave or "", "tipo": tipo, "texto": texto_}


def _kw(x) -> str:
    """kWp para gente, como a tela escreve: "3.196 kWp", "159,8 kWp"; sem número, "sem kWp"."""
    if x is None:
        return "sem kWp"
    s = f"{x:,.3f}".rstrip("0").rstrip(".")
    return s.replace(",", "§").replace(".", ",").replace("§", ".") + " kWp"


def nome_da_cabine(codigo) -> str:
    """"ITA100-CABN2" → "UG 02". A cabine é SEMPRE a CABN do Fracttal (decisão 2 do Levi, 20/10/2026: "foque em
    cabine"; na Altair as 5 UG da aba são 5 SKID debaixo de UMA CABN, e no Nexus fica uma cabine só) e o nome continua
    "UG NN": os leitores da aba só reconhecem cabine pelo "UG" (a disponibilidade da plataforma perderia calada uma
    cabine chamada "Cabine 2"). Vazio = o código não é de cabine."""
    m = _CABN.search(EQ.canon(codigo))
    return f"UG {int(m.group(1)):02d}" if m else ""


def rotulo_do_inversor(codigo) -> str:
    """"THPN-PHS100-INVR2.1" → "Inversor 2.1". O número sai do CÓDIGO, nunca da descrição: pela descrição (com a marca e
    o modelo, "Inversor 1.3 Huawei SUN2000-250KTL-H1") o número certo saía em 2,2% dos inversores da frota (medido em
    20/10/2026; o "1" do "H1"). Vazio = o código não é de inversor."""
    m = _INVR.search(EQ.canon(codigo))
    return f"Inversor {m.group(1)}" if m else ""


def _numero_da_ug(nome):
    m = re.fullmatch(r"ug\s*0*(\d+)", norm(nome))
    return int(m.group(1)) if m else None


def fora_da_regra(cmp: dict, u: dict, info_u: dict | None = None) -> list[str]:
    """As diferenças de `comparar_chave` que o de-para NÃO explica (textos; vazio = a chave só difere da aba pela regra,
    e só então o salvar a marca no lugar da aba). Da regra (20/10/2026, as decisões do Levi):
    - as strings corretas ("Strings Ativas"): é o que o de-para grava;
    - o kWp de inversor e de cabine que a regra do kWp calculou (a linhagem é `real_por_string` ou
      `contratual_por_string`: o 1.298,08 da aba vira 1.298,0 na Itajá); kWp com outra linhagem não é do de-para;
    - a cabine pela CABN (decisão 2): a cabine que só o Nexus tem e a do inversor que mudou de UG têm o código da CABN;
      a que só a aba tem vale quando TODAS as cabines vivas da usina já são CABN (a UG 01 da Pharma II deu lugar à
      UG 02);
    - a potência da UFV quando vem do Registro mestre (real, senão contratual: `info_u`) e o "N de Inversores" da UFV,
      que o Nexus CONTA (na Itajá real a UFV da aba é 2.596,16 kWp, a soma das UG, e sem "N de Inversores": até esta
      regra a "Itajá" nunca marcava, e os leitores ficavam com a UG 1.298,08 sem a CABN);
    - o "Código Fracttal" (a comparação nem olha).
    Tudo o mais é fora: Full O&M, String Box, nome do inversor (a coluna do BD), nome de exibição, nome no Fracttal,
    cliente, inversor de um lado só (o parado que não veio no pedido some dos leitores se a chave marcar), a chave fora da
    aba e a UFV em outra chave."""
    regras = set(REGRA_DO_REGISTRO.values())
    cab = {c["cabine_id"]: c for c in u["cabines"]}
    inv = {i["inversor_id"]: i for i in u["inversores"]}
    info_u = info_u or {}
    do_registro = info_u.get("kwp") is not None and info_u.get("kwp_de") in REGRA_DO_REGISTRO

    def com_cabn(cid):
        return bool((cab.get(cid) or {}).get("codigo_fracttal"))
    fora = []
    for it in cmp.get("itens") or ():
        t = it["tipo"]
        if t == "kwp_cabine":
            ok = (cab.get(it.get("cabine_id")) or {}).get("potencia_regra") in regras
        elif t == "kwp_inversor":
            ok = (inv.get(it.get("inversor_id")) or {}).get("potencia_regra") in regras
        elif t in ("cabine_so_no_nexus", "cabine_do_inversor"):
            ok = com_cabn(it.get("cabine_id"))
        elif t == "cabine_so_na_aba":
            # só as UG contam: a "UFV" e a "PEI" fora do padrão nem saem na visão (ver `visao_da_usina`)
            ugs = [c for c in cab.values() if _numero_da_ug(c.get("nome")) is not None]
            ok = bool(ugs) and all(c["codigo_fracttal"] for c in ugs)
        elif t in ("strings_inversor", "inversores_usina"):
            ok = True
        elif t == "kwp_usina":
            ok = do_registro
        else:
            ok = False
        if not ok:
            fora.append(it["texto"])
    return fora


def _validar_depara(itens, usinas_validas) -> list[dict]:
    """Os itens do pedido, limpos e conferidos entre si, sem ler o banco. Recusa: chave vazia ou repetida, usina fora do
    Registro mestre, inversor sem o nome no supervisório ou duas vezes na mesma chave, strings que não são um inteiro
    maior que zero, código que não é de inversor (INVRn.m) ou de cabine (CABNn) e o mesmo código em dois inversores."""
    if not isinstance(itens, list) or not itens:
        raise Recusada("O pedido não trouxe nenhuma chave do supervisório: nada foi gravado.")
    if len(itens) > MAX_DEPARA:
        raise Recusada(f"Mais de {MAX_DEPARA} chaves num pedido só: nada foi gravado.")
    out, chaves, codigos = [], set(), set()
    for n, it in enumerate(itens):
        if not isinstance(it, dict):
            raise Recusada(f"O {n + 1}º item do pedido não é uma chave do supervisório: nada foi gravado.")
        chave, uid = texto(it.get("usina_supervisorio")), D._id(it.get("usina_id"))
        quem = {"usina_id": uid, "usina_supervisorio": chave}      # a culpada vai na recusa (a tela tira só ela do lote)
        if not chave:
            raise Recusada(f"O {n + 1}º item está sem a chave do supervisório: nada foi gravado.", 400, **quem)
        if uid not in usinas_validas:
            raise Recusada(f"A chave “{chave}” aponta para uma usina fora do Registro mestre: nada foi gravado.", 400,
                           **quem)
        if chave in chaves:
            raise Recusada(f"A chave “{chave}” veio duas vezes no pedido: nada foi gravado.", 400, **quem)
        chaves.add(chave)
        invs = it.get("inversores") or []
        if not isinstance(invs, list) or len(invs) > MAX_INVERSORES or not all(isinstance(i, dict) for i in invs):
            raise Recusada(f"Os inversores da chave “{chave}” vieram fora do formato: nada foi gravado.", 400, **quem)
        limpos, sups = [], set()
        for m, i in enumerate(invs):
            esup = texto(i.get("equipamento_supervisorio"))
            if not esup:
                raise Recusada(f"“{chave}”: o {m + 1}º inversor está sem o nome no supervisório: nada foi gravado.", 400,
                               **quem)
            if norm(esup) in sups:
                raise Recusada(f"“{chave}”: o inversor “{esup}” veio duas vezes: nada foi gravado.", 400, **quem)
            sups.add(norm(esup))
            v = i.get("strings")
            s = _num(v)
            if v not in (None, "") and (s is None or s != int(s) or s < 1):
                raise Recusada(f"“{chave}” · {esup}: as strings corretas têm de ser um número inteiro maior que zero: "
                               "nada foi gravado.", 400, **quem)
            cod, cab = EQ.canon(i.get("codigo_fracttal")), EQ.canon(i.get("cabine_codigo_fracttal"))
            if cod and not rotulo_do_inversor(cod):
                raise Recusada(f"“{chave}” · {esup}: {cod} não é um código de inversor do Fracttal (…-INVRn.m): nada foi "
                               "gravado.", 400, **quem)
            if cab and not nome_da_cabine(cab):
                raise Recusada(f"“{chave}” · {esup}: {cab} não é um código de cabine do Fracttal (…-CABNn; a cabine é "
                               "sempre a CABN): nada foi gravado.", 400, **quem)
            if cod and cod in codigos:
                raise Recusada(f"O código {cod} veio em dois inversores do pedido: um código do Fracttal fica num "
                               "inversor só. Nada foi gravado.", 400, **quem)
            if cod:
                codigos.add(cod)
            limpos.append({"equipamento_supervisorio": esup, "nome": texto(i.get("nome")),
                           "strings": None if s is None else int(s), "codigo_fracttal": cod,
                           "cabine_codigo_fracttal": cab, "conferido": _sim(i.get("conferido"))})
        out.append({"chave": chave, "usina_id": uid, "selo": texto(it.get("selo")), "inversores": limpos})
    return out


def _ids_na_dimensao(itens, por_codigo) -> dict:
    """{código: equipamento_id} de cada código do pedido: o ID é DERIVADO do código no servidor
    (`equipamento.equipamento_id`, o mesmo número em qualquer máquina), nunca o que vem do pedido, e o código tem de ser
    membro da dimensão de equipamento. O que não é membro, ou que a dimensão guarda com outro ID, recusa o pedido
    inteiro com o código (regra 4: nunca chutar ID; até 20/10/2026 o Salvar da tela aceitava o `equipamento_id` que
    viesse, e só não mordia porque ninguém mandava)."""
    ids = {}
    for it in itens:
        for i in it["inversores"]:
            for cod in (i["codigo_fracttal"], i["cabine_codigo_fracttal"]):
                if not cod or cod in ids:
                    continue
                membro = (por_codigo or {}).get(cod)
                quem = {"usina_id": it["usina_id"], "usina_supervisorio": it["chave"]}
                if not membro:
                    raise Recusada(f"O código {cod} não está na dimensão de equipamento do Nexus (nexus_equipamentos · "
                                   "dim_equipamento): confira o código. Nada foi gravado.", 400, **quem)
                eid = EQ.equipamento_id(cod)
                if membro.get("equipamento_id") and membro["equipamento_id"] != eid:
                    raise Recusada(f"A dimensão de equipamento guarda o código {cod} com outro ID: nada foi gravado "
                                   "(o ID não se chuta).", 409, **quem)
                ids[cod] = eid
    return ids


def _recalcular_kwp(est, uid, info_u, muda, chave: str = "") -> tuple[dict, list]:
    """A regra do Levi (20/10/2026, "isso resolve o de-para e garante os cálculos de perdas"), na usina INTEIRA: kWp do
    inversor = kWp da usina no Registro mestre ÷ Σ strings corretas de todos os inversores vivos da usina × strings do
    inversor; kWp da cabine = a soma dos inversores dela. A soma é da usina, nunca só das chaves do pedido: na Itajá,
    salvar só a Itaja 1 daria 2.596 ÷ 76 strings × 19 = 649 kWp por inversor, o dobro do certo (324,5). Sem a potência
    real, a contratual (decisão 3). Três casos, todos com aviso (`_aviso`), nunca 0 nem vazio por cima de dado (Levi,
    20/10/2026):
    - sem a real E sem a contratual: o kWp e a linhagem ficam COMO ESTAVAM (até a 2ª revisão de 20/10 o kWp virava
      branco na usina inteira, inclusive o digitado à mão, e a chave marcada perdia o kWp nos leitores: PR e perda);
    - o inversor vivo sem strings corretas guarda o kWp de antes, e esse kWp é DESCONTADO do Registro antes de dividir
      pelos que têm strings: a soma da usina continua = Registro (sem o desconto, a Sapopema, com 2 dos 20 inversores sem
      strings, somava 3.515,6 kWp contra 3.196 do Registro, +10%). Se o descontado já cobre o Registro, a usina é
      recusada (não sobra kWp para dividir). A tela faz a MESMA conta (`plataforma/static/depara_tabela.js`);
    - a cabine cujo nome não é "UG NN" (a "UFV" da usina 11, a "PEI" da 85, vindas do "Equipamento Parente" da aba)
      fica fora da conta e não vira linha de UG na visão."""
    kwp_u, de = info_u.get("kwp"), info_u.get("kwp_de") or ""
    if kwp_u and de not in REGRA_DO_REGISTRO:
        raise Recusada(f"Não sei de qual potência do Registro mestre veio o kWp da usina {uid}: nada foi gravado.", 503,
                       uid, chave)
    regra = REGRA_DO_REGISTRO[de] if kwp_u else ""
    invs = [i for i in est["inversores"] if i["usina_id"] == uid and not i["excluido"]]
    vivas = [c for c in est["cabines"] if c["usina_id"] == uid and not c["excluido"]]
    cabs = [c for c in vivas if _numero_da_ug(c["nome"]) is not None]
    nome = texto(info_u.get("nome")) or f"usina {uid}"
    avisos, calc = [], {}
    for c in vivas:
        if _numero_da_ug(c["nome"]) is None:
            avisos.append(_aviso(uid, "", "cabine_fora_do_padrao",
                                 f"{nome}: a cabine “{c['nome']}” não se chama “UG NN” e ficou fora da conta do kWp e da "
                                 "visão (os leitores só reconhecem cabine pelo “UG”; uma linha “UFV” com o kWp dela seria "
                                 "lida como a usina). Renomeie ou tire na Base > Equipamentos das usinas."))
    if not regra:
        avisos.append(_aviso(uid, "", "sem_potencia",
                             f"{nome}: sem potência real nem contratual no Registro mestre, o kWp dos inversores e das "
                             "cabines ficou como estava (nunca vazio por cima de dado). Preencha a potência no Registro "
                             "mestre e salve de novo."))
        return {i["inversor_id"]: i["potencia_kwp"] for i in invs}, avisos
    com = [i for i in invs if (i["strings_esperadas_qtd"] or 0) > 0]
    sem = [i for i in invs if not (i["strings_esperadas_qtd"] or 0) > 0]
    desconto = sum(i["potencia_kwp"] or 0 for i in sem)
    resto = kwp_u - desconto
    if sem:
        lista = "; ".join(f"{i['nome']} ({_kw(i['potencia_kwp'])})" for i in sem[:12]) + (
            f"; e mais {len(sem) - 12}" if len(sem) > 12 else "")
        avisos.append(_aviso(uid, "", "sem_strings",
                             f"{nome}: {len(sem)} inversor(es) sem strings corretas ficaram com o kWp de antes, "
                             f"descontado do Registro mestre antes de dividir pelos {len(com)} que têm strings "
                             f"({_kw(kwp_u)} − {_kw(round(desconto, 3))} = {_kw(round(resto, 3))}): {lista}."))
    if com:
        if resto <= 0:
            raise Recusada(f"{nome}: os {len(sem)} inversor(es) sem strings corretas guardam {_kw(round(desconto, 3))} "
                           f"(o kWp de antes), o que já cobre os {_kw(kwp_u)} do Registro mestre: não sobra kWp para os "
                           f"{len(com)} que têm strings. Informe as strings deles (ou corrija o kWp na Base > "
                           "Equipamentos das usinas). Nada foi gravado.", 409, uid, chave)
        total = sum(i["strings_esperadas_qtd"] for i in com)
        for i in com:
            calc[i["inversor_id"]] = resto / total * i["strings_esperadas_qtd"]
            muda(i, potencia_kwp=round(calc[i["inversor_id"]], 3), potencia_regra=regra)
    for c in cabs:
        dela = [i for i in invs if i["cabine_id"] == c["cabine_id"]]
        if any(i["inversor_id"] in calc for i in dela):
            # a soma sai dos valores sem arredondar: a Pharma II fecha 990,0 (arredondando cada um, 989,998); o inversor
            # sem strings entra com o kWp de antes (o mesmo que foi descontado do Registro)
            soma = sum(calc.get(i["inversor_id"], i["potencia_kwp"] or 0) for i in dela)
            muda(c, potencia_kwp=round(soma, 3), potencia_regra=regra)
    return {i["inversor_id"]: i["potencia_kwp"] for i in invs}, avisos


def _cabine_da_cabn(est, uid, cod, eid, controle, muda, chave: str = "") -> int:
    """A cabine da usina para a CABN do Fracttal: a que já tem o código; senão a "UG NN" de mesmo número ainda sem
    código (a da aba, que o "Ligar pela aba" trouxe: a Itajá tem UG 01 e UG 02), que passa a ter o código; senão nasce a
    "UG NN". A "UG NN" de mesmo número ligada a OUTRO código recusa: duas CABN não viram uma cabine."""
    cabs = [c for c in est["cabines"] if c["usina_id"] == uid and not c["excluido"]]
    c = next((c for c in cabs if EQ.canon(c["codigo_fracttal"]) == cod), None)
    if c:
        muda(c, equipamento_id=eid)
        return c["cabine_id"]
    nome = nome_da_cabine(cod)
    c = next((c for c in cabs if _numero_da_ug(c["nome"]) == _numero_da_ug(nome)), None)
    if c and c["codigo_fracttal"]:
        raise Recusada(f"A cabine {c['nome']} desta usina já está ligada a {c['codigo_fracttal']}, e o pedido traz {cod} "
                       "para o mesmo número: nada foi gravado.", 409, uid, chave)
    if c:
        muda(c, codigo_fracttal=cod, equipamento_id=eid)
        return c["cabine_id"]
    cid = _proximo(est["cabines"], "cabine_id")
    est["cabines"].append({"cabine_id": cid, "usina_id": uid, "nome": nome, "potencia_kwp": None, "equipamento_id": eid,
                           "codigo_fracttal": cod, "ordem": max((x["ordem"] for x in cabs), default=0) + 1, **controle,
                           "potencia_regra": ""})
    muda(None)
    return cid


def _semear_pela_aba(est, uid, chave, aba_chaves, controle, muda) -> tuple[dict, dict | None]:
    """(a chave nova no livro, o aviso). A chave do pedido que o livro ainda não tem nasce SEMEADA PELA ABA antes do
    remendo, com o mesmo `estrutura_da_aba` do "Ligar pela aba": Full O&M, String Box, o nome de exibição, as cabines UG e
    TODOS os inversores da aba com o nome e as strings (e o kWp) da aba. Caso que criou (2ª revisão, 20/10/2026): a
    Coração 2 (usina 77, nada no Nexus) nascia com Full O&M = Não, só com os inversores que mandaram leitura naquela hora
    e com o nome do código do Fracttal ("Inversor 2.1" no lugar do "Inversor 1.1" da aba, a coluna do BD); marcada, a
    usina saía de trackers, PR e ocorrências e o inversor parado deixava de ser esperado.
    - A chave é a da usina (`principal`) só se a usina ainda não tem uma E a aba põe a UFV (ou as UG) nesta chave: a
      "Coração 2 (112)" só tem inversores na aba, e como principal levaria a UFV para ela (a comparação acusaria a UFV em
      outra chave e ela nunca valeria no lugar da aba).
    - A cabine de mesmo nome que a usina já tem é a mesma (a cabine é da usina); o nome de inversor que a usina já usa
      em outra chave ganha a chave no nome, como no "Ligar pela aba" e no "Trazer da aba".
    - Chave que não está na aba NEM no Nexus (a "Nova chave" que a tela oferecia: o nome que a fonte manda) é RECUSADA
      (409, com a culpada; 2ª revisão final, 21/10/2026). Ela nunca vale no lugar da aba (os leitores não a conhecem), e
      gravada ela virava a chave da usina e prendia os códigos do Fracttal nos inversores dela (um código num inversor vivo
      só): na Pharma 2 (usina 108), o Salvar da "PHARMA 2 API" criava "Inversor 2.1" a "2.6" com os THPN-PHS100-INVR2.x,
      e o da "Pharma 2" (a chave da aba) com os mesmos códigos levava 409 para sempre (o de-para não solta código). A
      chave nova é ligada na Base > Equipamentos das usinas, à vista.
    - Sem a aba lida não há de onde semear: recusa (503), para não nascer pela metade."""
    tem_principal = any(x["usina_id"] == uid and x["principal"] and not x["excluido"] for x in est["supervisorios"])
    sid = _proximo(est["supervisorios"], "supervisorio_id")
    if aba_chaves is None:
        raise Recusada(f"A aba Equipamentos não foi lida: a chave “{chave}” ainda não está no Nexus e só nasce semeada "
                       "pela aba (Full O&M, String Box e os inversores com o nome da aba). Nada foi gravado; tente de "
                       "novo.", 503, uid, chave)
    g = aba_chaves.get(chave)
    if g is None:
        raise Recusada(f"A chave “{chave}” não está na aba Equipamentos nem no Nexus: o de-para não cria chave nova (ela "
                       "nunca valeria no lugar da aba, os leitores não a conhecem, e prenderia os códigos do Fracttal nos "
                       "inversores dela). Escolha a chave da aba, ou ligue a chave na Base > Equipamentos das usinas "
                       "antes. Nada foi gravado.", 409, uid, chave)
    e = estrutura_da_aba([chave], aba_chaves)
    s0 = e["supervisorios"][0]
    na_aba_e_da_usina = g.get("ufv_kwp") is not None or bool(g.get("cabines"))
    s = {"supervisorio_id": sid, "usina_id": uid, "usina_supervisorio": chave, "usina_exibicao": s0["exibicao"],
         "principal": na_aba_e_da_usina and not tem_principal, "full_om": s0["full_om"],
         "string_box": s0["string_box"], "substitui_aba": False, **controle}
    est["supervisorios"].append(s)
    muda(None)
    vivas = [c for c in est["cabines"] if c["usina_id"] == uid and not c["excluido"]]
    cid_de = {norm(c["nome"]): c["cabine_id"] for c in vivas}
    ordem = max((c["ordem"] for c in vivas), default=0)
    for c in e["cabines"]:
        if norm(c["nome"]) in cid_de:
            continue
        ordem += 1
        cid = _proximo(est["cabines"], "cabine_id")
        # o kWp vem da aba: sem linhagem (vazio), como no "Ligar pela aba"
        est["cabines"].append({"cabine_id": cid, "usina_id": uid, "nome": c["nome"], "potencia_kwp": c["potencia_kwp"],
                               "equipamento_id": None, "codigo_fracttal": "", "ordem": ordem, **controle,
                               "potencia_regra": ""})
        cid_de[norm(c["nome"])] = cid
        muda(None)
    vivos = [i for i in est["inversores"] if i["usina_id"] == uid and not i["excluido"]]
    usados = {norm(i["nome"]) for i in vivos}
    ordem = max((i["ordem"] for i in vivos), default=0)
    for i in e["inversores"]:
        final, k = i["nome"], 1
        while norm(final) in usados:
            k += 1
            final = f"{i['nome']} · {chave}" if k == 2 else f"{i['nome']} · {chave} ({k - 1})"
        usados.add(norm(final))
        ordem += 1
        est["inversores"].append({"inversor_id": _proximo(est["inversores"], "inversor_id"), "usina_id": uid,
                                  "supervisorio_id": sid,
                                  "cabine_id": cid_de.get(norm(i["cabine"])) if i["cabine"] else None,
                                  "nome": final, "equipamento_supervisorio": i["equipamento_supervisorio"],
                                  "potencia_kwp": i["potencia_kwp"], "strings_esperadas_qtd": i["strings_esperadas_qtd"],
                                  "equipamento_id": None, "codigo_fracttal": "", "ordem": ordem, **controle,
                                  "potencia_regra": "", "fracttal_ligado_por": "", "conferido_em": ""})
        muda(None)
    t = (f"A chave “{chave}” não estava no Nexus e foi semeada pela aba Equipamentos antes do de-para: "
         f"{len(e['inversores'])} inversor(es) com o nome e as strings da aba, {len(e['cabines'])} cabine(s), Full O&M "
         f"{'Sim' if s['full_om'] else 'Não'}, String Box {'Sim' if s['string_box'] else 'Não'}"
         + (", como a chave da usina (UFV e cabines)" if s["principal"] else "") + ".")
    if e["avisos"]:
        t += " Na aba: " + "; ".join(e["avisos"]) + "."
    return s, _aviso(uid, chave, "semeada_pela_aba", t)


def _soma_na_aba(aba_chaves: dict | None, chave: str) -> float:
    return sum(a.get("kwp") or 0 for a in ((aba_chaves or {}).get(chave) or {}).get("inversores") or ())


def _marcar(est, usinas, sid_de, ja_marcada, info, aba_chaves, muda, avisos, visao_antes: dict) -> list[dict]:
    """Marca no lugar da aba, usina a usina, o que passa (`fora_da_regra` vazio) e devolve a `marcacao` [{usina_id,
    usina_supervisorio, principal, marcada, fora_da_regra}] (as do pedido primeiro, na ordem dele). `visao_antes` =
    {usina_id: as linhas de `visao_da_usina(..., todas=True)` do começo do salvar}, para saber o que ele mudou.

    A usina vale por INTEIRO ou nada (2ª revisão final, 21/10/2026): a regra do kWp recalcula a usina inteira, e marcar só
    parte das chaves deixava os leitores misturando a UFV e as UG do Nexus com inversores da aba, nada fechando entre si nem
    com o Registro (a Assis só com a Skid 1: UFV 6.296, inversores 6.446,0, UG 02 a 04 com 1.256,2 contra 1.293,6 dos
    inversores; a Rodrigues II com a 2.2 e a 2.3: UFV 2.116,8 contra 2.339,4; e a principal marcada sozinha, que a medida da
    2ª revisão achou em 6 usinas reais: Junco, Parelhas, Rodrigues I, Saturnino 1, Senador Elói I, Tanabi). Então:
    - todas as chaves da usina que ainda seguem com a aba são conferidas JUNTAS: as do pedido, a da UFV e das cabines
      (`principal`) e as outras com inversor no Nexus ou na aba. Só marcam se TODAS passarem; a que não passa segura as
      outras, e o aviso diz qual, por quê e quanto os leitores somariam se só as outras marcassem. SEM exceção (3ª
      revisão, 21/10/2026): até ela a chave do pedido IGUAL à aba marcava sozinha com a usina segura ("os leitores não
      mudam"), e era a porta do estado parcial: a Itaja 2 marcada sozinha (a Itaja 1 com o Full O&M diferente na aba), o
      Salvar seguinte da Itaja 1 com 20 strings refazia o kWp da usina inteira e a Itaja 2 levava 316,18 por inversor
      aos leitores (2.596 ÷ 156 × 19) ao lado da UG 02 da aba com 1.298,08;
    - a já marcada não é conferida de novo e continua marcada enquanto este salvar não mudar o que ela leva aos leitores
      (as linhas dela na visão, `visao_antes`). Numa usina que fica segura, a já marcada cuja visão MUDOU volta para a
      aba (com o aviso): é o mesmo estado parcial pela outra porta (a chave marcada na Base > Equipamentos, ou a
      principal marcada sozinha antes desta regra), o kWp e as UG recalculados indo aos leitores ao lado dos inversores
      da aba. A já marcada cuja visão não mudou fica como está: tirá-la agora mudaria os leitores sem motivo."""
    marcacao = []
    pos = {sid: n for n, sid in enumerate(dict.fromkeys(sid_de.values()))}

    def ja(s):
        return ja_marcada.get(s["supervisorio_id"], s["substitui_aba"])
    for uid in usinas:
        u, info_u = da_usina(est, uid), info.get(uid)
        nome = texto((info_u or {}).get("nome")) or f"usina {uid}"
        linhas_u = visao_da_usina(u, info_u, todas=True)
        antes = (visao_antes or {}).get(uid) or []
        mudaram = [s for s in u["supervisorios"] if ja(s) and not _mesma_visao(
            [x for x in antes if x["supervisorio_id"] == s["supervisorio_id"]],
            [x for x in linhas_u if x["supervisorio_id"] == s["supervisorio_id"]])]
        com_inv = {i["supervisorio_id"] for i in u["inversores"]}
        alvo = sorted((s for s in u["supervisorios"] if s["supervisorio_id"] in pos and not ja(s)),
                      key=lambda s: pos[s["supervisorio_id"]])
        alvo += sorted((s for s in u["supervisorios"] if not ja(s) and s["supervisorio_id"] not in pos
                        and (s["principal"] or s["supervisorio_id"] in com_inv
                             or ((aba_chaves or {}).get(s["usina_supervisorio"]) or {}).get("inversores"))),
                       key=lambda s: (not s["principal"], natural(s["usina_supervisorio"])))
        if not alvo:
            continue
        cmp, fora = {}, {}
        for s in alvo:
            sid = s["supervisorio_id"]
            if aba_chaves is None:
                cmp[sid], fora[sid] = None, ["a aba Equipamentos não foi lida, e sem ela não há comparação"]
            else:
                cmp[sid] = comparar_chave(aba_chaves.get(s["usina_supervisorio"]),
                                          [x for x in linhas_u if x["supervisorio_id"] == sid])
                fora[sid] = fora_da_regra(cmp[sid], u, info_u)
        presas = [s for s in alvo if fora[s["supervisorio_id"]]]
        quem = ", ".join(f"“{p['usina_supervisorio']}”" for p in presas[:4]) + (
            f" e mais {len(presas) - 4}" if len(presas) > 4 else "")
        seguras = []
        for s in alvo:
            sid, f = s["supervisorio_id"], fora[s["supervisorio_id"]]
            ok = not presas
            papel = f" (a chave da UFV e das cabines de {nome})" if s["principal"] and sid not in pos else ""
            if ok:
                muda(s, substitui_aba=True)
            elif f:
                avisos.append(_aviso(uid, s["usina_supervisorio"], "nao_marcada",
                                     f"A chave “{s['usina_supervisorio']}”{papel} não vale no lugar da aba porque: "
                                     + "; ".join(x.rstrip(".") for x in f[:6]) + ("; ..." if len(f) > 6 else "")
                                     + f". A estrutura ficou gravada no Nexus ({len(f)} diferença(s) com a aba fora "
                                       "da regra do de-para); os leitores seguem com a aba nesta chave. Confira na "
                                       "Base > Equipamentos das usinas."))
            else:
                seguras.append(s)
                f = [f"{quem}, da mesma usina, não vale(m) no lugar da aba, e a usina vale por inteiro ou nada"]
                avisos.append(_aviso(uid, s["usina_supervisorio"], "nao_marcada",
                                     f"A chave “{s['usina_supervisorio']}”{papel} não vale no lugar da aba porque: {f[0]}. "
                                     "A estrutura ficou gravada no Nexus; os leitores seguem com a aba nesta chave."))
            marcacao.append({"usina_id": uid, "usina_supervisorio": s["usina_supervisorio"], "principal": s["principal"],
                             "marcada": ok, "fora_da_regra": f})
        # a já marcada cuja visão este salvar mudou, numa usina que fica segura: volta para a aba (ver a docstring)
        voltaram = mudaram if presas else []
        for s in voltaram:
            muda(s, substitui_aba=False)
            papel = f" (a chave da UFV e das cabines de {nome})" if s["principal"] else ""
            f = [f"{quem}, da mesma usina, não vale(m) no lugar da aba, e a usina vale por inteiro ou nada: ela valia, e "
                 "este Salvar mudou o que ela leva aos leitores"]
            avisos.append(_aviso(uid, s["usina_supervisorio"], "nao_marcada",
                                 f"A chave “{s['usina_supervisorio']}”{papel} valia no lugar da aba e voltou para a aba: "
                                 "este Salvar mudou o que ela leva aos leitores (a regra recalcula o kWp e as cabines da "
                                 f"usina inteira), e {quem}, da mesma usina, não vale(m) no lugar da aba; a usina vale por "
                                 "inteiro ou nada. A estrutura ficou gravada no Nexus; os leitores seguem com a aba nesta "
                                 "chave até a usina valer inteira."))
            marcacao.append({"usina_id": uid, "usina_supervisorio": s["usina_supervisorio"], "principal": s["principal"],
                             "marcada": False, "fora_da_regra": f})
        if seguras or voltaram:
            # o que os leitores somariam se as que passam marcassem sem as outras (o estado misto que a regra evita)
            def soma(vale):
                t = 0.0
                for s in u["supervisorios"]:
                    if vale(s):
                        t += sum(i["potencia_kwp"] or 0 for i in u["inversores"] if i["supervisorio_id"] == s["supervisorio_id"])
                    else:
                        t += _soma_na_aba(aba_chaves, s["usina_supervisorio"])
                return round(t, 3)
            passam = {s["supervisorio_id"] for s in seguras + voltaram}
            ja_vale = [s["usina_supervisorio"] for s in u["supervisorios"] if s["substitui_aba"]]
            t = (f"{nome}: a usina não passou a valer no lugar da aba, porque {quem} não vale(m), e a usina vale por inteiro "
                 "ou nada (a regra recalcula o kWp da usina inteira). Marcando só as outras, os leitores somariam "
                 f"{_kw(soma(lambda s: s['substitui_aba'] or s['supervisorio_id'] in passam))} nos inversores, contra "
                 f"{_kw((info_u or {}).get('kwp'))} do Registro mestre.")
            if ja_vale:
                t += (" Já valem no lugar da aba " + ", ".join(f"“{c}”" for c in ja_vale[:4]) + (" e mais" if len(ja_vale) > 4
                      else "") + f": nos leitores a usina fica com {_kw(soma(lambda s: s['substitui_aba']))} nos "
                      "inversores.")
            avisos.append(_aviso(uid, "", "nao_marcada", t + " Acerte a(s) que não vale(m) e salve de novo."))
    ordem = {c: n for n, c in enumerate(sid_de)}            # as do pedido na ordem dele; as outras depois, como vieram
    marcacao.sort(key=lambda m: (0, ordem[m["usina_supervisorio"]]) if m["usina_supervisorio"] in ordem else (1, 0))
    return marcacao


def estado_da_usina(est: dict, usina_id: int, info_u: dict | None) -> dict:
    """O que o modo de-para mostra de uma usina: o selo, o kWp do Registro mestre e de qual potência veio, as chaves,
    as cabines e os inversores (com a linhagem). O formato é o contrato com a plataforma (o GET e a volta do salvar)."""
    u, info_u = da_usina(est, usina_id), info_u or {}
    chave = {s["supervisorio_id"]: s["usina_supervisorio"] for s in u["supervisorios"]}
    kwp = info_u.get("kwp")
    return {"usina_id": usina_id, "nome": texto(info_u.get("nome")), "codigo": texto(info_u.get("codigo")),
            "selo": selo(u), "kwp": kwp, "kwp_de": (info_u.get("kwp_de") or None) if kwp is not None else None,
            "chaves": [{"supervisorio_id": s["supervisorio_id"], "usina_supervisorio": s["usina_supervisorio"],
                        "principal": s["principal"], "substitui_aba": s["substitui_aba"]} for s in u["supervisorios"]],
            "cabines": [{"cabine_id": c["cabine_id"], "nome": c["nome"], "codigo_fracttal": c["codigo_fracttal"] or None,
                         "potencia_kwp": c["potencia_kwp"], "potencia_regra": c.get("potencia_regra") or None}
                        for c in u["cabines"]],
            "inversores": [{"inversor_id": i["inversor_id"], "supervisorio_id": i["supervisorio_id"],
                            "usina_supervisorio": chave.get(i["supervisorio_id"], ""), "nome": i["nome"],
                            "equipamento_supervisorio": i["equipamento_supervisorio"], "cabine_id": i["cabine_id"],
                            "strings_esperadas_qtd": i["strings_esperadas_qtd"], "potencia_kwp": i["potencia_kwp"],
                            "codigo_fracttal": i["codigo_fracttal"] or None, "equipamento_id": i["equipamento_id"],
                            "potencia_regra": i.get("potencia_regra") or None,
                            "fracttal_ligado_por": i.get("fracttal_ligado_por") or None,
                            "conferido_em": i.get("conferido_em") or None} for i in u["inversores"]]}


def usinas_das_chaves(est: dict, chaves, validas=None) -> tuple[list, list]:
    """(o usina_id de cada chave pedida, sem repetir e na ordem do pedido; as chaves que não estão ligadas a usina
    nenhuma). Com `validas` (os ids do Registro mestre), a chave ligada a uma usina que saiu do Registro conta como sem
    usina: o modo de-para não tem kWp nem nome para mostrar dela."""
    dono = {s["usina_supervisorio"]: s["usina_id"] for s in est["supervisorios"] if not s["excluido"]}
    uids, sem = [], []
    for c in chaves:
        uid = dono.get(c)
        if not uid or (validas is not None and uid not in validas):
            sem.append(c)
        elif uid not in uids:
            uids.append(uid)
    return uids, sem


def salvar_depara(itens, cfg, base, sessao, *, info: dict, por_codigo: dict, aba_chaves: dict | None = None,
                  quem_email: str = "", irmas_da_aba: dict | None = None) -> dict:
    """Grava o remendo do modo de-para num só `_gravar` (a trava, o livro relido do banco, o selo de cada usina: um que
    não confere recusa tudo, e a recusa diz a usina culpada). Para cada chave do pedido:
    1. liga à usina do Registro mestre (ligada a outra usina, recusa); a chave que o livro ainda não tem nasce SEMEADA
       PELA ABA (`_semear_pela_aba`: Full O&M, String Box, exibição, as UG e todos os inversores da aba com o nome e as
       strings da aba), e só então vem o remendo; a chave que não está na aba nem no livro é recusada (a "Nova chave").
       A chave da aba que é da MESMA usina (`irmas_da_aba`: {usina_id: [chaves]}, a regra do "Ligar pela aba", pela
       Usina Fractall nas Ligações) e ainda não está no livro nem no pedido recusa a usina (409): a conta do kWp dividiria
       o Registro só pelas strings das chaves do Nexus (a Coração 2 sozinha: 250 → 812,5 kWp por inversor, e a usina
       somaria 6.500 nos leitores, 3.250 da Coração 1 pela aba e 3.250 da Coração 2 pelo Nexus, contra 3.250 do
       Registro). Salvam-se as duas juntas;
    2. acha o inversor pela chave e pelo nome no supervisório; sem ele, pelo NOME dentro da usina (o `nome` do pedido,
       que é o do cadastro, senão o da aba para a chave e o nome no supervisório), e o inversor achado sem nome no
       supervisório ganha o do pedido (os 214 da aba sem ele: a Cambé, as Ibirapuã). Inversor de outra chave ou com outro
       nome no supervisório recusa a usina. Sem nenhum, nasce com o `nome` do pedido, senão o da aba, e só então o
       "Inversor N.M" do código. O nome ("Equipamento", a coluna do BD) do inversor que já existe NUNCA muda (decisão 5);
    3. põe as strings, a cabine (`_cabine_da_cabn`), o ativo do Fracttal com o ID derivado e o Conferido;
    4. recalcula o kWp da usina inteira (`_recalcular_kwp`);
    5. MARCA no lugar da aba (`_marcar`) só o que, depois do remendo, difere da aba APENAS pela regra do de-para
       (`fora_da_regra`: strings, cabine pela CABN, kWp que a regra calculou, a UFV do Registro e o "N de Inversores"
       contado); qualquer outra diferença grava a estrutura, NÃO marca e vai nos avisos ("não vale no lugar da aba
       porque: ..."). **A usina vale por inteiro ou nada** (2ª revisão final e 3ª revisão, 21/10/2026): TODAS as chaves
       dela que ainda seguem com a aba (as do pedido, a da UFV e das cabines, e as outras com inversor no Nexus ou na
       aba) são conferidas juntas e só marcam se todas passarem, sem exceção (nem a chave igual à aba); a já marcada
       fica, menos numa usina segura em que este salvar mudou a visão dela: volta para a aba. Caso: a regra recalcula o
       kWp da usina inteira, e marcar só parte deixava os leitores com a UFV e as UG do Nexus e os inversores da aba (a
       Assis só com a Skid 1: UFV 6.296 e inversores 6.446,0, +2,4%; a Rodrigues II: 2.116,8 × 2.339,4, +10,5%; a Itajá
       com o Full O&M da Itaja 1 diferente: a UG 01 excluída e os 4 inversores da Itaja 1, vindos da aba, apontando para
       ela; a Itaja 2 marcada sozinha por ser igual à aba e, no salvar seguinte, levando 316,18 por inversor aos leitores).
    Até a 2ª revisão de 20/10/2026 toda chave do pedido virava "no lugar da aba" sem comparar: a chave da aba que o
    Nexus não tinha nascia com Full O&M = Não, só com os inversores que leram naquela hora e com o nome do código (a
    Coração 2: "Inversor 1.1" virava "Inversor 2.1", a usina saía de trackers e PR, o inversor parado sumia).
    O que não veio fica como está (código, cabine ou strings vazios no pedido = não mexe): o remendo não exclui inversor
    nem chave; só sai a cabine da usina SEM código do Fracttal e sem inversor no Nexus, a cada salvar (a UG 01 da Pharma
    II, quando os inversores vão para a CABN2, "UG 02"; a UG vazia contaria cabine a mais na disponibilidade), e nem ela
    quando a chave da UFV vale no lugar da aba e uma chave que segue com a aba ainda tem, na aba, inversor nela (ficaria
    órfão nos leitores). Com a chave da UFV já valendo, mover de cabine os inversores de uma chave que segue com a aba
    recusa a usina (409): a UFV e as UG dos leitores não fechariam com eles. A cabine COM código nunca sai por aqui (vai
    nos avisos).
    Avisos: [{usina_id, usina_supervisorio, tipo, texto}] (`TIPOS_AVISO`). `info` = {usina_id: nome, codigo, cliente,
    kwp, kwp_de, fracttal}, da tela (o Registro mestre e as Ligações); `por_codigo` = a dimensão de equipamento
    (`dimensao`); `aba_chaves` = a aba Equipamentos agrupada (`aba_equipamentos`; None = não se leu)."""
    info = info or {}
    limpos = _validar_depara(itens, set(info))
    ids = _ids_na_dimensao(limpos, por_codigo)
    usinas = sorted({it["usina_id"] for it in limpos})
    chave_da_usina = {}                          # a 1ª chave do pedido de cada usina: vai na recusa que é da usina
    for it in limpos:
        chave_da_usina.setdefault(it["usina_id"], it["chave"])

    def mudar(est, agora, quem):
        controle = {"criado_em": agora, "alterado_em": agora, "alterado_por_hmac": quem, "excluido": False}
        conta = {"n": 0}

        def muda(x, **campos):
            """Muda só o que é diferente, e só o que mudou ganha a data e quem (x None = algo nasceu)."""
            if x is None:
                conta["n"] += 1
            elif any(x.get(k) != v for k, v in campos.items()):
                x.update(campos, alterado_em=agora, alterado_por_hmac=quem)
                conta["n"] += 1
        # o selo de cada usina, TODOS antes de mexer em qualquer uma
        selos = {uid: selo(da_usina(est, uid)) for uid in usinas}
        for it in limpos:
            if it["selo"] != selos[it["usina_id"]]:
                raise Recusada(f"A estrutura da usina da chave “{it['chave']}” mudou desde que a tela abriu (outra aba "
                               "ou outra pessoa): recarregue. Nada foi gravado.", 409, it["usina_id"], it["chave"])
        com_inversor = {i["cabine_id"] for i in est["inversores"] if i["usina_id"] in usinas and not i["excluido"]}
        # o começo do salvar: o que cada chave levava aos leitores (a já marcada cuja visão muda volta para a aba numa
        # usina segura, `_marcar`), quem já valia e a cabine de cada inversor (o guarda da cabine órfã, lá embaixo)
        visao_antes = {uid: visao_da_usina(da_usina(est, uid), info.get(uid), todas=True) for uid in usinas}
        valia = {s["supervisorio_id"] for s in est["supervisorios"] if s["usina_id"] in usinas and not s["excluido"]
                 and s["substitui_aba"]}
        cabine_antes = {i["inversor_id"]: i["cabine_id"] for i in est["inversores"]
                        if i["usina_id"] in usinas and not i["excluido"]}
        sid_de, ja_marcada, avisos = {}, {}, []
        for it in limpos:
            uid, chave = it["usina_id"], it["chave"]
            s = next((x for x in est["supervisorios"] if x["usina_supervisorio"] == chave and not x["excluido"]), None)
            if s and s["usina_id"] != uid:
                raise Recusada(f"A chave “{chave}” já está ligada a outra usina (id {s['usina_id']}): desligue lá antes. "
                               "Nada foi gravado.", 409, uid, chave)
            if not s:
                s, a = _semear_pela_aba(est, uid, chave, aba_chaves, controle, muda)
                if a:
                    avisos.append(a)
            sid_de[chave] = s["supervisorio_id"]
            ja_marcada[s["supervisorio_id"]] = s["substitui_aba"]
        # a chave da aba da MESMA usina que o livro ainda não tem e que não veio: a conta do kWp ficaria sem as strings dela
        no_livro = {s["usina_supervisorio"] for s in est["supervisorios"] if not s["excluido"]}
        for uid in usinas:
            faltam = [c for c in (irmas_da_aba or {}).get(uid) or () if c not in no_livro]
            if faltam:
                nome = texto((info.get(uid) or {}).get("nome")) or f"usina {uid}"
                lista = ", ".join(f"“{c}”" for c in faltam[:6]) + (f" e mais {len(faltam) - 6}" if len(faltam) > 6 else "")
                raise Recusada(f"{nome}: a aba Equipamentos tem {lista}, que pela Usina Fractall (as Ligações) é desta usina "
                               "e ainda não está no Nexus. A regra do kWp divide o Registro mestre pelas strings de TODA a "
                               "usina, e sem essa chave a divisão sairia só pelas do Nexus (os leitores somariam a usina "
                               "duas vezes). Salve as plantas juntas, ou ligue a chave na Base > Equipamentos das usinas "
                               "(Trazer da aba) antes. Nada foi gravado.", 409, uid, chave_da_usina[uid])
        recebeu = {}
        for it in limpos:
            uid, chave = it["usina_id"], it["chave"]
            sid = sid_de[chave]
            # o nome da aba para (chave, nome no supervisório): o 2º na ordem do nome do inversor novo
            nome_na_aba = {norm(a["equipamento_supervisorio"]): a["nome"]
                           for a in ((aba_chaves or {}).get(chave) or {}).get("inversores") or ()
                           if a.get("equipamento_supervisorio")}
            for i in it["inversores"]:
                esup, cod, cab = i["equipamento_supervisorio"], i["codigo_fracttal"], i["cabine_codigo_fracttal"]
                cab_id = _cabine_da_cabn(est, uid, cab, ids[cab], controle, muda, chave) if cab else None
                vivos = [x for x in est["inversores"] if x["usina_id"] == uid and not x["excluido"]]
                inv = next((x for x in vivos if x["supervisorio_id"] == sid
                            and norm(x["equipamento_supervisorio"]) == norm(esup)), None)
                novo = False
                if inv is None:
                    nome = i["nome"] or nome_na_aba.get(norm(esup), "")
                    x = next((x for x in vivos if nome and norm(x["nome"]) == norm(nome)), None)
                    if x and x["supervisorio_id"] not in (sid, None):
                        dela = next((c["usina_supervisorio"] for c in est["supervisorios"]
                                     if c["supervisorio_id"] == x["supervisorio_id"]), "?")
                        raise Recusada(f"“{chave}” · {esup}: o inversor “{x['nome']}” desta usina chega pela chave "
                                       f"“{dela}”: o de-para dele é por essa chave. Nada foi gravado.", 409, uid, chave)
                    if x and x["equipamento_supervisorio"]:
                        raise Recusada(f"“{chave}” · {esup}: o inversor “{x['nome']}” já está nesta chave com o nome "
                                       f"“{x['equipamento_supervisorio']}” no supervisório: confira qual dos dois é o "
                                       "da fonte. Nada foi gravado.", 409, uid, chave)
                    if x:
                        # o inversor do cadastro sem o nome no supervisório (214 na aba, 13/10) ganha o da fonte
                        inv = x
                        muda(inv, equipamento_supervisorio=esup, supervisorio_id=sid)
                    else:
                        nome = nome or rotulo_do_inversor(cod)
                        if not nome:
                            raise Recusada(f"“{chave}” · {esup}: inversor novo sem nome e sem o código do Fracttal (de "
                                           "onde sairia o “Inversor N.M”): nada foi gravado.", 400, uid, chave)
                        if any(norm(x["nome"]) == norm(nome) for x in vivos):
                            raise Recusada(f"“{chave}” · {esup}: a usina já tem um inversor “{nome}” (o nome é a coluna "
                                           "do BD e não se repete na usina): mande o nome do cadastro. Nada foi "
                                           "gravado.", 409, uid, chave)
                        inv = {"inversor_id": _proximo(est["inversores"], "inversor_id"), "usina_id": uid,
                               "supervisorio_id": sid, "cabine_id": None, "nome": nome,
                               "equipamento_supervisorio": esup, "potencia_kwp": None, "strings_esperadas_qtd": None,
                               "equipamento_id": None, "codigo_fracttal": "",
                               "ordem": max((x["ordem"] for x in vivos), default=0) + 1, **controle,
                               "potencia_regra": "", "fracttal_ligado_por": "", "conferido_em": ""}
                        est["inversores"].append(inv)
                        muda(None)
                        novo = True
                campos = {}
                if i["strings"] is not None:
                    campos["strings_esperadas_qtd"] = i["strings"]
                if cab_id:
                    campos["cabine_id"] = cab_id
                if cod:
                    campos.update(codigo_fracttal=cod, equipamento_id=ids[cod])
                    recebeu[cod] = (inv["inversor_id"], uid, chave)
                final = campos.get("codigo_fracttal", inv["codigo_fracttal"])
                mesmo = EQ.canon(final) == EQ.canon(inv["codigo_fracttal"])
                # o Conferido é da linha; a data é a da 1ª vez com ESTE código (conferir de novo não muda nada)
                campos["conferido_em"] = ((inv["conferido_em"] if mesmo and inv["conferido_em"] else agora)
                                          if i["conferido"] else "")
                campos["fracttal_ligado_por"] = ("conferido" if i["conferido"] else "sugestao") if final else ""
                if novo:
                    inv.update(campos)
                else:
                    muda(inv, **campos)
        # um código do Fracttal num inversor vivo só, na frota inteira (o "inversor repetido" do protótipo: a Coração 2
        # sugeria os mesmos ativos da Coração 1); conferido depois de aplicar, para a troca entre dois inversores passar
        for cod, (iid, uid, chave) in recebeu.items():
            outro = next((x for x in est["inversores"] if not x["excluido"] and x["inversor_id"] != iid
                          and EQ.canon(x["codigo_fracttal"]) == cod), None)
            if outro:
                raise Recusada(f"O código {cod} já está no inversor “{outro['nome']}” (usina {outro['usina_id']}): um "
                               "código do Fracttal fica num inversor vivo só. Nada foi gravado.", 409, uid, chave)
        kwp = {}
        for uid in usinas:
            k, a = _recalcular_kwp(est, uid, info[uid], muda, chave_da_usina[uid])
            kwp.update(k)
            avisos += a
        # a cabine que este salvar esvaziou: sem o código do Fracttal ela era a UG da aba e sai (decisão 2, a cabine é a
        # CABN; na Pharma II a UG 01 vazia faria a disponibilidade contar 2 cabines, e o "Cabine N = usina N" do site
        # agrupado deixaria de valer); com o código, é uma CABN e fica (só o aviso). Sai PROVISÓRIA antes da marcação (a
        # conferência vê a usina como ela vai ficar) e só de vez depois dela, pelo guarda da cabine órfã
        agora_com = {i["cabine_id"] for i in est["inversores"] if i["usina_id"] in usinas and not i["excluido"]}
        vazias = []
        for c in est["cabines"]:
            if c["cabine_id"] not in com_inversor - agora_com or c["excluido"]:
                continue
            if c["codigo_fracttal"]:
                avisos.append(_aviso(c["usina_id"], "", "cabine_sem_inversores",
                                     f"A cabine {c['nome']} (usina {c['usina_id']}) ficou sem inversores e fica: é a "
                                     f"{c['codigo_fracttal']} do Fracttal, e o de-para nunca tira uma CABN. Tire na "
                                     "Base > Equipamentos das usinas se ela não existe."))
            else:
                c["excluido"] = True
                vazias.append(c)
        marcacao = _marcar(est, usinas, sid_de, ja_marcada, info, aba_chaves, muda, avisos, visao_antes)
        # o guarda da cabine órfã (2ª revisão final e 3ª revisão, 21/10/2026). Com a chave da UFV e das cabines no lugar
        # da aba, as UFV e as UG dos leitores são as do Nexus, e o inversor de uma chave que segue com a aba aponta para a
        # UG pela aba ("Equipamento Parente").
        # 1. Este salvar mover de cabine os inversores de uma chave que seguia e segue com a aba, com a da UFV já valendo,
        #    RECUSA a usina: a UFV e as UG iriam aos leitores com o kWp e a contagem do Nexus, e os inversores dela com a
        #    cabine da aba. Caso (3ª revisão): a "Itajá" marcada na Base e a Itaja 1 com o Full O&M diferente na aba; levar
        #    a Itaja 1 para a CABN2 deixava a UG 02 com 2.596 kWp nos leitores e só os 1.298,08 da Itaja 2 apontando para
        #    ela, e a UG 01 presa no Nexus (até então o salvar passava e só segurava a UG 01, com um aviso)
        for uid in usinas:
            u = da_usina(est, uid)
            if not any(s["principal"] and s["supervisorio_id"] in valia for s in u["supervisorios"]):
                continue
            segue = {s["supervisorio_id"]: s["usina_supervisorio"] for s in u["supervisorios"]
                     if not s["substitui_aba"] and s["supervisorio_id"] not in valia}
            movido = next((i for i in u["inversores"] if i["supervisorio_id"] in segue
                           and cabine_antes.get(i["inversor_id"]) not in (None, i["cabine_id"])), None)
            if movido:
                x = segue[movido["supervisorio_id"]]
                nome = texto((info.get(uid) or {}).get("nome")) or f"usina {uid}"
                raise Recusada(f"{nome}: a chave da UFV vale no lugar da aba e “{x}” segue com a aba: mover os inversores "
                               f"de “{x}” de cabine deixaria a UFV e as UG dos leitores sem fechar; acerte “{x}” ou salve "
                               "as chaves juntas. Nada foi gravado.", 409, uid, x)
        # 2. A cabine sem código do Fracttal e sem inversor no Nexus sai a CADA salvar da usina, não só a que este salvar
        #    esvaziou (a UG 01 da Itajá que o guarda segurou ficava no Nexus para sempre, com o kWp antigo: depois que a
        #    Itaja 1 passou a valer, ia aos leitores vazia, ao lado da UG 02 com a usina toda). Fica só a UG para a qual
        #    uma chave que segue com a aba ainda aponta na aba, com a da UFV valendo (sem ela, os inversores dessa chave
        #    ficariam órfãos nos leitores: a disponibilidade os punha numa UG sem linha), com o aviso, até a chave valer
        for c in vazias:
            c["excluido"] = False
        esvaziou = {c["cabine_id"] for c in vazias}
        com_inv = {i["cabine_id"] for i in est["inversores"] if i["usina_id"] in usinas and not i["excluido"]}
        excluidas = []
        for c in est["cabines"]:
            if c["usina_id"] not in usinas or c["excluido"] or c["codigo_fracttal"] or c["cabine_id"] in com_inv:
                continue
            ficou = "ficou" if c["cabine_id"] in esvaziou else "estava"
            u = da_usina(est, c["usina_id"])
            presas = [s["usina_supervisorio"] for s in u["supervisorios"] if not s["substitui_aba"] and any(
                norm(a.get("cabine")) == norm(c["nome"])
                for a in ((aba_chaves or {}).get(s["usina_supervisorio"]) or {}).get("inversores") or ())]
            if presas and any(s["principal"] and s["substitui_aba"] for s in u["supervisorios"]):
                avisos.append(_aviso(c["usina_id"], "", "cabine_sem_inversores",
                                     f"A cabine {c['nome']} (usina {c['usina_id']}) {ficou} sem inversores no Nexus e "
                                     "fica: a chave da UFV e das cabines vale no lugar da aba, e na aba os inversores de "
                                     + ", ".join(f"“{p}”" for p in presas[:4]) + " (que seguem com a aba) ainda estão "
                                     "nela; sem ela eles ficariam órfãos nos leitores. Sai no salvar em que essas chaves "
                                     "valerem no lugar da aba."))
                continue
            muda(c, excluido=True)
            excluidas.append({"cabine_id": c["cabine_id"], "usina_id": c["usina_id"], "nome": c["nome"]})
            avisos.append(_aviso(c["usina_id"], "", "cabine_excluida",
                                 f"A cabine {c['nome']} (usina {c['usina_id']}) {ficou} sem inversores e saiu: era a "
                                 "da aba, sem código do Fracttal, e a cabine é a CABN."))
        return {"mudancas": conta["n"], "usinas": [estado_da_usina(est, uid, info.get(uid)) for uid in usinas],
                "kwp": kwp, "avisos": avisos, "cabines_excluidas": excluidas, "marcacao": marcacao,
                "log": f"de-para do tempo real: {conta['n']} mudança(s) em {len(limpos)} chave(s) das usinas "
                       f"{', '.join(map(str, usinas))}"}
    return _gravar(mudar, cfg, base, sessao, quem_email, info)
