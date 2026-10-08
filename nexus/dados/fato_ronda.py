"""O fato ÚNICO de ronda (passo 3 do Kimball, 08/10/2026): uma linha por ronda realizada, venha de onde vier.

Por quê. A auditoria de 08/10 (GR-1, DR-5) achou a ronda espalhada em três livros, com três grãos e domínios
diferentes: o livro do App (`rondas_app_campo`, declarado "1 OS de ronda", mas 124 de 867 linhas não têm OS), o
checklist da carga única das rondas sem OS (`nexus_rondas_checklist`, 125) e a ronda avulsa lançada no Nexus
(`nexus_rondas_avulsas`). A vala tinha "Obstruída" num e "Suja" no outro; o sensor 0 era "limpo" num e "não marcado" no
outro. Cruzar sujidade da ronda com perda de geração exigia juntar os três à mão. Aqui eles viram UM fato, com os
domínios de `dominios.py`.

Grão: 1 linha = 1 ronda realizada. Tipo: foto acumulada (a linha muda depois de entrar: a "Situação da OS" anda de
"em verificação" para "criada"; medido em 08/10, as 302 em verificação têm até 30 dias e as 412 criadas, mais de 8).
Chave: `ronda_id`.
- ronda do App: `ronda_id = sha1("app|" + Início)[:16]`. O `Início` é o carimbo do aparelho, com milissegundos, e é
  único sozinho (0 repetições em 867, 08/10); o nome da usina no Fracttal NÃO é estável (em 05/10 a mesma usina vinha
  com e sem o espaço antes do hífen, ver `ligacao_cadastro._norm`).
- checklist: casa com a linha do App pelo MESMO `Início` (e a mesma usina, quando as duas ligaram). A linha do checklist
  cuja ronda já saiu da janela de 90 dias do App continua no fato como `app_sem_os`, com o mesmo `ronda_id`: as 125
  respostas não somem em ~09/11/2026.
- avulsa: `ronda_id = sha1("avulsa|" + id)[:16]`. Só as válidas: a anulada não foi realizada e a linha de anulação não é
  ronda (o livro da avulsa é só-acréscimo; a anulação é outra linha).
- chave repetida = erro (`GraoDuplicado`): um fato com duas linhas para a mesma ronda conta errado em silêncio.

Pessoa: o fato NUNCA leva o nome (a API do banco tem leitura aberta, regra 8). O HMAC do e-mail (`Técnico (HMAC)`,
quando o App mandar, passo 2) vence; depois o `pessoa_id` que o checklist/avulsa já gravaram (também do e-mail); por
último o nome em claro de hoje, que só liga se for de UMA pessoa do cadastro (homônimo não liga: ID errado é pior que
ID nenhum). `pessoa_hmac` guarda o código para religar depois; só com o nome, ele sai de `codigo_do_nome` (o "n:" +
HMAC do nome normalizado), que é decisão do Levi (spec, seção 9, item 2): sem ela, vazio.

Equipe: papel REGISTRO (a "Região" que o App gravou na hora da ronda). A avulsa não registra equipe (o `equipe_id` do
livro dela é a equipe da usina no cadastro, outro papel, GR-13): vai vazio; a equipe da usina vem do `usinas_historico`.

Herda do passo 0 (adiado pelo Levi, 08/10): o fato é refeito a cada hora a partir do livro do App, que guarda 90 dias.
A ronda do App de 11/08 sai do fato por volta de 09/11/2026. O checklist (livro próprio) e a avulsa (o Nexus é a fonte)
não se perdem. Com o passo 0, o fato vira ATUALIZAÇÃO por `ronda_id` (não só acréscimo: congelaria a 1ª situação).
"""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone

from ..campo.ligacao_cadastro import _norm as norm_nome
from ..campo.ligacao_cadastro import codigo_da_pessoa
from . import dominios as DOM
from .equipamento import FORA_DA_DIMENSAO
from .fatos import _id, _int, _txt, data_do_registro, ligar_equipamento, pct_versao
from .fatos import _pct as pct

FATO, TIPO = "ronda", "snapshot_acumulado"
GRAO = "1 linha = 1 ronda realizada (App com ou sem OS, checklist da carga única, avulsa válida)"
CHAVE = ("ronda_id",)
FONTES = (("rondas_app_campo", "OS de ronda"), ("nexus_rondas_checklist", "fato_checklist_ronda"),
          ("nexus_rondas_avulsas", "fato_ronda_avulsa"))
LIVRO_ORIGEM = " + ".join(l for l, _ in FONTES)
JANELA_ORIGEM = "90 dias (App)"
DURACAO_MAX_MIN = 480          # a regra do App (visao._duracao_min): fora de 0 a 8 h é relógio errado, não ronda

CAB_RONDA = ["ronda_id", "origem", "data_id", "usina_id", "usina_ligada_por", "equipe_id", "pessoa_id", "pessoa_hmac",
             "pessoa_ligada_por", "equipamento_id", "equipamento_ligado_por", "os", "id_os_fracttal", "os_situacao",
             "tipo_ronda", "inicio", "fim", "duracao_min", "nota_pts", "falhas_qtd", *DOM.INDICADORES_FALHA,
             "trackers_apontados_qtd", "trackers_respondidos_qtd", "checklist_fonte", "sujidade_nivel",
             "vegetacao_nivel", "vala_nivel", "sombreamento", "ipoa_sujo", "ghi_sujo", "albedo_sujo"]
# (coluna, unidade, soma) — para o catálogo (`Medida`). Indicador sem sufixo é 1/0 e soma.
MEDIDAS = (("duracao_min", "min", "aditiva"), ("nota_pts", "pts", "nao"), ("falhas_qtd", "qtd", "aditiva"),
           *((c, "1/0", "aditiva") for c in DOM.INDICADORES_FALHA),
           ("trackers_apontados_qtd", "qtd", "aditiva"), ("trackers_respondidos_qtd", "qtd", "aditiva"),
           ("sujidade_nivel", "nível 1-5", "nao"), ("vegetacao_nivel", "nível 1-5", "nao"),
           ("vala_nivel", "nível 1-3", "nao"), ("sombreamento", "1/0", "aditiva"), ("ipoa_sujo", "1/0", "aditiva"),
           ("ghi_sujo", "1/0", "aditiva"), ("albedo_sujo", "1/0", "aditiva"))
SENSORES = ("ipoa_sujo", "ghi_sujo", "albedo_sujo")     # o mesmo nome no checklist, na avulsa e no fato


class OrigemQ(list):
    """A lista `origem_q`, alinhada com as linhas do fato, e `fora`: o que ficou fora do fato e por quê (contagem)."""

    def __init__(self, itens=(), fora=None):
        super().__init__(itens)
        self.fora = Counter(fora or {})


class GraoDuplicado(ValueError):
    """Duas linhas com a mesma chave do fato: o grão quebrou. A carga não publica um fato que conta em dobro."""


def chave(prefixo: str, valor) -> str:
    return hashlib.sha1(f"{prefixo}|{_txt(valor)}".encode("utf-8")).hexdigest()[:16]


def conferir_grao(linhas: list[list], cab: list, col: str) -> None:
    """Sobe `GraoDuplicado` se a coluna-chave repete (ou vem vazia)."""
    i = cab.index(col)
    cont = Counter(l[i] for l in linhas)
    ruins = {k: n for k, n in cont.items() if n > 1 or not k}
    if ruins:
        ex = "; ".join(f"{k or '(vazio)'} ({n})" for k, n in list(ruins.items())[:5])
        raise GraoDuplicado(f"{col} repetido ou vazio em {sum(ruins.values())} linhas: {ex}")


def codigo_do_nome(chave_hmac: str):
    """A chave durável de quem só vem por nome: "n:" + HMAC(NEXUS_PESSOA_HMAC, nome normalizado). O Ligador pode calcular
    o mesmo código para o nome de cada pessoa do cadastro e religar quando ela entrar (KC-4). Ligar isto na carga é
    decisão do Levi (spec, seção 9, item 2); sem a chave, None."""
    if not chave_hmac:
        return None

    def f(nome):
        n = norm_nome(nome)
        c = codigo_da_pessoa(chave_hmac, n) if n else None
        return f"n:{c}" if c else None
    return f


def _equip(equip, codigo) -> tuple:
    """(equipamento_id, por onde ligou). `equip` é o que a carga entrega (`equipamento.ligar` com o índice da
    dimensão: código -> (ID, como)), uma função código -> ID ou um dicionário. Sem ele, (None, None)."""
    return ligar_equipamento(equip, codigo)


def _quando(iso):
    s = _txt(iso).replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def duracao_min(inicio, fim):
    a, b = _quando(inicio), _quando(fim)
    if not a or not b:
        return None
    m = (b - a).total_seconds() / 60
    return int(round(m)) if 0 <= m <= DURACAO_MAX_MIN else None


def _pessoa_pelo_nome(pessoa_por_nome, nome):
    """O pessoa_id do nome só quando ele é de UMA pessoa. Aceita {nome: id} (o `mapas()["pessoa"]`, que já tira os
    homônimos) ou {nome: {ids}} (aí o homônimo é visto aqui)."""
    n = norm_nome(nome)
    if not n or not pessoa_por_nome:
        return None
    v = pessoa_por_nome.get(n)
    if isinstance(v, (set, frozenset, list, tuple)):
        v = next(iter(v)) if len(set(v)) == 1 else None
    return _id(v)


def avulsas_validas(linhas) -> list[dict]:
    """A mesma regra do `nexus.campo.ronda_avulsa.validas` (o teste prova que batem): fora a linha de anulação e o
    lançamento anulado. Copiada para a camada de dados não importar a tela (Flask, cache da visão)."""
    anuladas = {str(l.get("anula_id")) for l in linhas if l.get("anula_id")}
    return [l for l in linhas if not l.get("anula_id") and str(l.get("id")) not in anuladas]


def _respostas_checklist(ck) -> dict:
    return {"checklist_fonte": "carga_unica_sem_os", "sujidade_nivel": DOM.nivel(ck.get("sujidade")),
            "vegetacao_nivel": DOM.nivel(ck.get("vegetacao")), "vala_nivel": DOM.vala(ck.get("vala")),
            "sombreamento": None, **{c: DOM.sensor(ck.get(c)) for c in SENSORES}}


def _linha(**kw) -> list:
    return [kw.get(c) for c in CAB_RONDA]


def fato_ronda(app: list[dict], checklist: list[dict], avulsas: list[dict], lig, pessoa_por_nome: dict | None,
               codigo_do_nome=None, equip=None) -> tuple[list[list], list[dict]]:
    """(linhas do fato, origem_q). `origem_q` anda junto com as linhas (mesma ordem) e leva o que a qualidade precisa
    da origem ("Usina", "Região", os textos fora do domínio); fica só na memória, não vai ao banco.

    `app`: as linhas do `rondas_app_campo`; `checklist`: as do `nexus_rondas_checklist · fato_checklist_ronda`;
    `avulsas`: TODAS as do `nexus_rondas_avulsas · fato_ronda_avulsa` (a anulação é filtrada aqui); `lig`: o `Ligador`
    (`fatos.Ligador`: usina, equipe, pessoa por HMAC); `pessoa_por_nome`: {nome normalizado: pessoa_id} (o `mapas()["pessoa"]`);
    `codigo_do_nome`: nome -> "n:<hmac>" (decisão do Levi; None = vazio); `equip`: código do ativo -> equipamento_id."""
    por_inicio: dict[str, list[dict]] = {}
    for ck in checklist:
        ini = _txt(ck.get("inicio"))
        if ini:
            por_inicio.setdefault(ini, []).append(ck)
    linhas, origem_q, vistos = [], [], set()

    for a in app:
        ini = _txt(a.get("Início"))
        if not ini:            # sem o carimbo não há ronda_id: fica fora e a qualidade conta
            origem_q.append({"_fora": "app_sem_inicio"})
            continue
        uid, como = lig.usina(a.get("Usina"), a.get("Ativo da usina no Fracttal"))
        cks, ck, casou = por_inicio.get(ini) or [], None, None
        if cks:
            vistos.add(ini)
            u_ck = _id(cks[0].get("usina_id"))
            if len(cks) > 1:
                casou = "ambiguo"
            elif uid and u_ck and uid != u_ck:
                casou = "conflito"       # mesmo carimbo, outra usina: nunca a resposta de outra ronda
            else:
                ck, casou = cks[0], "casou"
                if not uid and u_ck:
                    uid, como = u_ck, _txt(ck.get("usina_ligada_por")) or "checklist"
        hmac_ = _txt(a.get("Técnico (HMAC)")).split(";")[0].strip()
        nome = a.get("Técnico")
        pid, por = (lig.pessoa(hmac_), "hmac") if hmac_ else (None, None)
        if not pid and ck is not None and _id(ck.get("pessoa_id")):
            pid, por = _id(ck.get("pessoa_id")), "cadastro"
        if not pid:
            pid = _pessoa_pelo_nome(pessoa_por_nome, nome)
            por = "nome" if pid else None
        codigo_nome = codigo_do_nome(nome) if (codigo_do_nome and not hmac_ and _txt(nome)) else None
        presentes, desconhecidas = DOM.falhas(a.get("Falhas"))
        rotulos = len(presentes) + len(desconhecidas)
        os_ = _txt(a.get("OS")) or None
        resp = _respostas_checklist(ck) if ck is not None else {}
        eid, eq_como = _equip(equip, a.get("Ativo da usina no Fracttal"))     # a OS de ronda é sobre a usina
        linhas.append(_linha(
            ronda_id=chave("app", ini), origem="app_os" if os_ else "app_sem_os", data_id=data_do_registro(ini),
            usina_id=uid, usina_ligada_por=como, equipe_id=lig.equipe(a.get("Região")) or
            (_id(ck.get("equipe_id")) if ck is not None else None),
            pessoa_id=pid, pessoa_hmac=hmac_ or codigo_nome, pessoa_ligada_por=por,
            equipamento_id=eid, equipamento_ligado_por=eq_como, os=os_,
            id_os_fracttal=_txt(a.get("ID da OS no Fracttal")) or None, os_situacao=DOM.os_situacao(a.get("Situação da OS")),
            tipo_ronda=DOM.tipo_ronda(a.get("Tipo")), inicio=ini, fim=_txt(a.get("Fim")) or None,
            duracao_min=duracao_min(ini, a.get("Fim")), nota_pts=_int(a.get("Nota da ronda")), falhas_qtd=rotulos,
            **{c: int(c in presentes) for c in DOM.INDICADORES_FALHA},
            trackers_apontados_qtd=_int(a.get("Trackers apontados")),
            trackers_respondidos_qtd=_int(a.get("Trackers respondidos")), **resp))
        origem_q.append({"fonte": "app", "Usina": _txt(a.get("Usina")), "Região": _txt(a.get("Região")),
                         "situacao": _txt(a.get("Situação da OS")), "falhas_desconhecidas": desconhecidas,
                         "vala": _txt(ck.get("vala")) if ck is not None else "", "checklist": casou})

    # o checklist cuja ronda não está (mais) no livro do App: a resposta fica, com o mesmo ronda_id
    for ini, cks in por_inicio.items():
        if ini in vistos:
            continue
        if len(cks) > 1:
            origem_q.append({"_fora": "checklist_ambiguo", "n": len(cks)})
            continue
        ck = cks[0]
        pid = _id(ck.get("pessoa_id"))
        linhas.append(_linha(
            ronda_id=chave("app", ini), origem="app_sem_os", data_id=_id(ck.get("data_id")) or data_do_registro(ini),
            usina_id=_id(ck.get("usina_id")),
            usina_ligada_por=(_txt(ck.get("usina_ligada_por")) or "checklist") if _id(ck.get("usina_id")) else None,
            equipe_id=_id(ck.get("equipe_id")), pessoa_id=pid, pessoa_ligada_por="cadastro" if pid else None,
            tipo_ronda=DOM.tipo_ronda(ck.get("tipo")), inicio=ini, fim=_txt(ck.get("fim")) or None,
            duracao_min=duracao_min(ini, ck.get("fim")), **_respostas_checklist(ck)))
        origem_q.append({"fonte": "checklist", "Usina": "", "Região": "", "vala": _txt(ck.get("vala")),
                         "checklist": "so_no_livro"})

    for v in avulsas_validas(avulsas):
        rid = _txt(v.get("id"))
        if not rid:
            origem_q.append({"_fora": "avulsa_sem_id"})
            continue
        uid = _id(v.get("usina_id"))
        pid, por = _id(v.get("pessoa_id")), "cadastro"
        if not pid and _txt(v.get("pessoa_hmac")):
            pid, por = lig.pessoa(v.get("pessoa_hmac")), "hmac"
        ini = _txt(v.get("inicio")) or None
        dur = _int(v.get("duracao_min"))
        linhas.append(_linha(
            ronda_id=chave("avulsa", rid), origem="avulsa", data_id=_id(v.get("data_id")) or data_do_registro(ini),
            usina_id=uid, usina_ligada_por="cadastro" if uid else None, pessoa_id=pid,
            pessoa_hmac=_txt(v.get("pessoa_hmac")) or None, pessoa_ligada_por=por if pid else None,
            tipo_ronda=DOM.tipo_ronda(v.get("tipo")), inicio=ini, fim=_txt(v.get("fim")) or None,
            duracao_min=dur if dur is not None and 0 < dur <= DURACAO_MAX_MIN else duracao_min(ini, v.get("fim")),
            checklist_fonte="avulsa", sujidade_nivel=DOM.nivel(v.get("sujidade")),
            vegetacao_nivel=DOM.nivel(v.get("vegetacao")), vala_nivel=DOM.vala(v.get("vala")),
            sombreamento=DOM.sim_nao(v.get("sombreamento")),
            **{c: DOM.sensor_avulsa(v.get(c)) for c in SENSORES}))
        origem_q.append({"fonte": "avulsa", "Usina": "", "Região": "", "vala": _txt(v.get("vala"))})

    # `origem_q` traz também o que ficou fora (com "_fora"); as linhas, não. Alinhar antes de devolver.
    fora = Counter()
    for o in origem_q:
        if "_fora" in o:
            fora[o["_fora"]] += o.get("n", 1)
    conferir_grao(linhas, CAB_RONDA, "ronda_id")
    return linhas, OrigemQ((o for o in origem_q if "_fora" not in o), fora)


# ── Qualidade (a mesma conta para ronda e PT; a linha vai à aba `qualidade` pelo nome da coluna) ─────────────────
def _exemplos(cont: Counter) -> str | None:
    top = sorted(cont.items(), key=lambda kv: (-kv[1], str(kv[0])))[:6]      # empate pelo texto (fatos._exemplos)
    return "; ".join(f"{k or '(vazio)'} ({v})" for k, v in top) or None


def linha_de_qualidade(fato, livro, linhas, cab, origem_q, origem_em, agora, *, col_data="data_id",
                       col_pessoa="pessoa_id", hist=None, extra=None) -> dict:
    """A linha da aba `qualidade` como {coluna: valor}: as colunas de hoje (`fatos.CAB_QUALIDADE`) + as do passo 3
    (`com_equipamento`, `pct_equipamento`, `pct_usina_versao`, `pct_pessoa_versao`, `extra`), com 1 casa decimal.
    `hist` = {"pessoas": linhas, "usinas": linhas} do histórico (listas da carga ou dicts do banco); sem a entidade,
    o `pct_*_versao` dela fica vazio (não é 0%)."""
    i = {c: k for k, c in enumerate(cab)}
    n = len(linhas)
    com = {c: sum(1 for l in linhas if l[i[c]] is not None) for c in (col_data, "usina_id", "equipe_id", col_pessoa,
                                                                       "equipamento_id")}
    como = Counter(l[i["usina_ligada_por"]] for l in linhas)
    sem_u = Counter(o.get("Usina", "") for o, l in zip(origem_q, linhas) if l[i["usina_id"]] is None)
    sem_e = Counter(o.get("Região", "") for o, l in zip(origem_q, linhas) if l[i["equipe_id"]] is None)
    hist = hist or {}
    extra = dict(extra or {})
    if "equipamento_ligado_por" in i:
        # código válido que não é membro da dimensão da MESMA carga: órfão (deve dar 0); a qualidade conta, não esconde
        extra["equipamento_fora_da_dimensao"] = sum(1 for l in linhas
                                                    if l[i["equipamento_ligado_por"]] == FORA_DA_DIMENSAO)
    return {"fato": fato, "livro_origem": livro, "linhas": n, "com_data": com[col_data], "com_usina": com["usina_id"],
            "com_equipe": com["equipe_id"], "com_pessoa": com[col_pessoa], "pct_data": pct(com[col_data], n),
            "pct_usina": pct(com["usina_id"], n), "pct_equipe": pct(com["equipe_id"], n),
            "pct_pessoa": pct(com[col_pessoa], n), "usina_por_de_para": como.get("de-para do Fracttal", 0),
            "usina_por_codigo": como.get("código do ativo", 0), "sem_usina_exemplos": _exemplos(sem_u),
            "sem_equipe_exemplos": _exemplos(sem_e), "origem_atualizada_em": origem_em, "gerado_em": agora,
            "com_equipamento": com["equipamento_id"], "pct_equipamento": pct(com["equipamento_id"], n),
            "pct_usina_versao": pct_versao(linhas, cab, "usina_id", col_data, hist.get("usinas")),
            "pct_pessoa_versao": pct_versao(linhas, cab, col_pessoa, col_data, hist.get("pessoas")),
            "extra": json.dumps(extra or {}, ensure_ascii=False, sort_keys=True)}


def qualidade_ronda(linhas, origem_q, origem_em, agora, *, avulsas=(), hist=None) -> dict:
    """A linha de qualidade 'ronda'. O `extra` conta o que só este fato tem: as origens, quantas com checklist, as
    anuladas, como a pessoa ligou e o que veio fora do domínio (o que ficou vazio por isso)."""
    i = {c: k for k, c in enumerate(CAB_RONDA)}
    resumo_fora = getattr(origem_q, "fora", Counter())
    oq = list(origem_q)
    org = Counter(l[i["origem"]] for l in linhas)
    anul = sum(1 for a in avulsas if a.get("anula_id"))
    extra = {**{o: org.get(o, 0) for o in DOM.ORIGEM_RONDA},
             "checklist": sum(1 for l in linhas if l[i["checklist_fonte"]]),
             "checklist_so_no_livro": sum(1 for o in oq if o.get("checklist") == "so_no_livro"),
             "checklist_conflito": sum(1 for o in oq if o.get("checklist") in ("conflito", "ambiguo"))
             + resumo_fora.get("checklist_ambiguo", 0),
             "anuladas": anul, "fora_sem_chave": sum(v for k, v in resumo_fora.items() if k != "checklist_ambiguo"),
             **{f"pessoa_por_{k}": v for k, v in Counter(l[i["pessoa_ligada_por"]] for l in linhas if
                                                          l[i["pessoa_ligada_por"]]).items()},
             "os_situacao_fora": sum(1 for o, l in zip(oq, linhas) if o.get("situacao") and not l[i["os_situacao"]]),
             "vala_fora": sum(1 for o in oq if DOM.vala_fora(o.get("vala"))),
             "falha_desconhecida": sum(1 for o in oq if o.get("falhas_desconhecidas"))}
    return linha_de_qualidade(FATO, LIVRO_ORIGEM, linhas, CAB_RONDA, oq, origem_em, agora, hist=hist, extra=extra)
