"""As OS do cliente pela FAMA (11/11/2026): `nexus_os_fama · fato_os_fama` e `dim_projeto_fama`. Puro: quem lê a FAMA e
grava é `nexus/dados/fama.py`; quem liga o projeto à usina é a tela Base → Ligações entre bases
(`nexus/cadastro/ligacao_fama.py`).

Levi, 11/11/2026: o cliente cria a OS na FAMA, ela aparece para o programador automático e cai no App de Campo; as
retroativas também entram. "A ideia é não ficarmos criando e editando e sim acompanhando." A fase 1 é sombra: o Nexus
lê, grava, liga as usinas e mostra; nada muda no campo.

Grão: 1 linha = 1 OS da FAMA atribuída à Grid, no estado da leitura mais recente. Foto acumulada: a OS anda de created a
closed e a linha muda (nunca acrescentar pela chave e congelar a 1ª versão). A chave é o id da OS na FAMA.

Governança (regra 8 do nexus/dados/CLAUDE.md: a API do banco tem leitura aberta):
- o `title` e a `description` são texto livre do cliente e vão SÓ cifrados, pelo Cofre do cadastro (a
  NEXUS_CHAVE_CADASTRO), amarrados à linha: o contexto leva a OS e o campo, e a cifra posta em outra linha não abre. A
  cifra que já está no banco fica quando o texto não mudou (o nonce é aleatório e a API guarda o histórico de cada linha
  que muda: sem isso, toda hora as ~4.700 linhas mudariam);
- `creator`, `responsible`, `approver`, a `partner_company` e o usuário das transações não entram (não há e-mail para
  virar código, e nome em claro não vai a um banco de leitura aberta);
- a usina vem SÓ da ligação decidida na tela (sistema `FAMA · Projetos`, chave = o id do projeto, `casou_por` "manual"):
  a proposta pelo nome é só proposta; sem a decisão, o `usina_id` fica vazio e conta na qualidade (regra 4: nunca
  chutar ID).
"""
import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone

# só o calendário no topo: a seção Ligações do cadastro importa este módulo (o SISTEMA), e o `fato_ronda` e o `fatos`
# importam o cadastro (o ciclo cadastro.ligacoes -> aqui -> fato_ronda -> cadastro.ligacao_campo -> cadastro.ligacoes)
from .calendario import data_id as _data_id

LIVRO, ABA, ABA_DIM = "nexus_os_fama", "fato_os_fama", "dim_projeto_fama"
NOME_LIVRO = "Nexus · OS do cliente pela FAMA (sombra: lidas da FAMA, com a usina do Nexus)"
# o sistema da FAMA no de-para do cadastro (Base → Ligações entre bases); a chave é o id do projeto na FAMA
SISTEMA = "FAMA · Projetos"
CAB_OS_FAMA = ["fama_os_id", "fama_projeto_id", "usina_id", "usina_ligada_por", "data_id_criacao", "data_id_prevista",
               "data_id_fim", "fama_status_id", "status", "fama_tipo_id", "tipo", "fama_severidade_id", "severidade",
               "fama_especialidade_id", "especialidade", "fama_tipo_equipe_id", "tipo_equipe", "contract_id",
               "dias_ate_fim_qtd", "titulo_cifrado", "descricao_cifrada"]
CAB_DIM = ["fama_projeto_id", "nome", "os_qtd"]
CAB_ATUALIZACAO = ["gerado_em", "maquina", "duracao_s", "linhas", "como_ler", "sha_linhas", "lido_em"]
COMO_LER = ("1 linha = 1 OS da FAMA atribuída à Grid, no estado da leitura mais recente; usina_id só pela ligação "
            "decidida em Base → Ligações entre bases (FAMA · Projetos); título e descrição só cifrados")
TIPO = "snapshot_acumulado"
GRAO = "1 linha = 1 OS da FAMA atribuída à Grid, no estado da leitura mais recente"
CHAVE = ("fama_os_id",)
# do dia da criação ao dia do fim, em Brasília: média, nunca soma (somar prazos de OS diferentes não diz nada)
MEDIDAS = (("dias_ate_fim_qtd", "dias", "nao"),)
FONTES = (("FAMA (API da prestadora)", "service-orders: a lista inteira das OS atribuídas à Grid"),)
JANELA_ORIGEM = "tudo: a FAMA devolve a lista inteira de uma vez, desde 08/2023 (só cresce)"
LIGADA_POR = "de-para FAMA · Projetos (decidido na tela)"
_BRT = timezone(timedelta(hours=-3))

# Os catálogos da FAMA medidos em 11/11/2026 (contagens, no servidor). Fora deles = vazio + conta (regra 4): o id da FAMA
# fica, e o valor novo aparece na qualidade para entrar aqui. A especialidade e o tipo de equipe não têm lista medida:
# vão como a FAMA escreve (catálogo dela, não texto livre)
STATUS = ("created", "planned", "under mobilization", "under execution", "paused", "under review", "executed",
          "approved", "closed")
TIPOS = ("Corrective", "Preventive/Predictive", "Vegetation control", "Modules cleaning",
         "Equipments and Materials movement")
SEVERIDADES = ("Critical", "Urgent", "Routine", "Non-Urgent")
ROTULO_MAX = 60
_ID_TEXTO = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _txt(v) -> str:
    return "" if v is None else " ".join(str(v).split())


def id_fama(v):
    """O id de um objeto da FAMA: o inteiro positivo ("10", 10.0 e "10.0" são 10: a API do banco pode devolver o número
    como texto ou com ".0"), ou o código em texto (letras, dígitos, hífen e sublinhado), se a FAMA usar um. Senão, None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v) if float(v).is_integer() and v > 0 else None
    s = str(v).strip()
    try:
        f = float(s)
    except ValueError:
        return s if _ID_TEXTO.fullmatch(s) and not s.isdigit() else None
    return int(f) if f.is_integer() and f > 0 else None


def _ordem(v) -> tuple:
    return (0, v, "") if isinstance(v, int) else (1, 0, str(v))


def dia(v) -> tuple[date | None, str]:
    """(o dia de Brasília, como veio). Com fuso: o dia em Brasília (regra 7). Sem fuso: UTC, como o resto do Nexus
    (`fatos.data_do_registro`), salvo a meia-noite exata, que é o dia escolhido num calendário e viraria o dia anterior.
    O dia só: ele mesmo. A qualidade conta cada jeito (a 1ª leitura do servidor diz qual a FAMA usa)."""
    s = str(v or "").strip()
    if not s:
        return None, "vazia"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        try:
            return date.fromisoformat(s), "dia"
        except ValueError:
            return None, "invalida"
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T", 1))
    except ValueError:
        return None, "invalida"
    if d.tzinfo is not None:
        return d.astimezone(_BRT).date(), "com_fuso"
    if (d.hour, d.minute, d.second, d.microsecond) == (0, 0, 0, 0):
        return d.date(), "meia_noite"
    return d.replace(tzinfo=timezone.utc).astimezone(_BRT).date(), "sem_fuso"


def _do_catalogo(obj, campo: str, dominio, fora: Counter, nome: str, id_reserva=None) -> tuple:
    """(id, nome) de um catálogo da FAMA ({id, <campo>}). Com `dominio`, o nome fora dele fica vazio e conta."""
    obj = obj if isinstance(obj, dict) else {}
    i = id_fama(obj.get("id"))
    if i is None:
        i = id_fama(id_reserva)
    rotulo = _txt(obj.get(campo) if obj.get(campo) is not None else obj.get("name"))
    if not rotulo:
        return i, None
    if dominio is not None:
        canon = {d.casefold(): d for d in dominio}.get(rotulo.casefold())
        if canon is None:
            fora[nome] += 1
        return i, canon
    return i, rotulo[:ROTULO_MAX]


def contexto(fama_os_id, campo: str) -> str:
    """O contexto da cifra: o livro, a aba, a OS e o campo (a cifra de uma linha não abre em outra)."""
    return f"{LIVRO}/{ABA}/{fama_os_id}/{campo}"


_CIFRADAS = (("titulo", "title", "titulo_cifrado"), ("descricao", "description", "descricao_cifrada"))


def _cifra(cofre, texto, oid, campo: str, coluna: str, anteriores: dict, conta: Counter):
    t = str(texto or "").strip()
    if not t:
        return None
    ctx = contexto(oid, campo)
    ant = (anteriores.get(oid) or {}).get(coluna)
    if ant and cofre.eh_cifrado(ant):
        try:
            if cofre.decifrar(ant, ctx) == t:
                conta["mantidas"] += 1
                return ant
        except Exception:       # noqa: BLE001 — CifraErro (outra chave, outra linha): cifra-se de novo
            conta["refeitas"] += 1
    conta["novas"] += 1
    return cofre.cifrar(t, ctx)


def textos(cofre, linha: dict) -> dict:
    """{"titulo", "descricao"} de uma linha do fato (do banco ou da montagem), decifrados no Nexus. Sobe `CifraErro` se a
    cifra não é desta linha ou desta chave."""
    oid = id_fama(linha.get("fama_os_id"))
    return {campo: (cofre.decifrar(linha[col], contexto(oid, campo)) if linha.get(col) else None)
            for campo, _f, col in _CIFRADAS}


def validas(itens) -> tuple[dict, dict]:
    """({fama_os_id: item}, relatório): as OS da lista com id, uma vez cada (a 1ª vale; a repetida conta)."""
    por_os, lidas, repetidas, sem_id = {}, 0, 0, 0
    for x in itens or ():
        lidas += 1
        oid = id_fama(x.get("id")) if isinstance(x, dict) else None
        if oid is None:
            sem_id += 1
        elif oid in por_os:
            repetidas += 1
        else:
            por_os[oid] = x
    return por_os, {"lidas": lidas, "repetidas": repetidas, "sem_id": sem_id}


def _projeto(x) -> dict:
    return x.get("project") if isinstance(x.get("project"), dict) else {}


def linhas(por_os: dict, ligacao: dict, cofre, anteriores: dict | None = None) -> tuple[list[list], dict]:
    """As linhas do fato (CAB_OS_FAMA), pela OS, e um relatório só de contagens. `por_os` = `validas`; `ligacao` =
    `ligacao_decidida` ({fama_projeto_id: usina_id}); `cofre` = o Cofre do cadastro; `anteriores` = {fama_os_id: linha do
    banco}, para manter a cifra do texto que não mudou."""
    anteriores = {id_fama(k): v for k, v in (anteriores or {}).items()}
    fora, datas, cifras = Counter(), Counter(), Counter()
    fim_antes, out = 0, []
    for oid in sorted(por_os, key=_ordem):
        x = por_os[oid]
        pid = id_fama(_projeto(x).get("id"))
        uid = ligacao.get(pid) if pid is not None else None
        dias = {}
        for col, campo in (("criacao", "creation_date"), ("prevista", "expected_execution_date"),
                           ("fim", "finish_date")):
            d, como = dia(x.get(campo))
            if como != "vazia":
                datas[como] += 1
            dias[col] = d
        lag = None
        if dias["criacao"] and dias["fim"]:
            lag = (dias["fim"] - dias["criacao"]).days
            if lag < 0:
                fim_antes, lag = fim_antes + 1, None
        st = _do_catalogo(x.get("status"), "service_status", STATUS, fora, "status", x.get("status_id"))
        tp = _do_catalogo(x.get("type"), "service_type", TIPOS, fora, "tipo")
        sv = _do_catalogo(x.get("severity"), "service_severity", SEVERIDADES, fora, "severidade")
        es = _do_catalogo(x.get("specialty"), "specialty", None, fora, "especialidade")
        eq = _do_catalogo(x.get("management_team_type"), "name", None, fora, "tipo_equipe")
        cif = [_cifra(cofre, x.get(f), oid, campo, col, anteriores, cifras) for campo, f, col in _CIFRADAS]
        out.append([oid, pid, uid, LIGADA_POR if uid else None,
                    *(_data_id(dias[c]) if dias[c] else None for c in ("criacao", "prevista", "fim")),
                    *st, *tp, *sv, *es, *eq, id_fama(x.get("contract_id")), lag, *cif])
    i_p = CAB_OS_FAMA.index("fama_projeto_id")
    rel = {"fora_do_dominio": dict(fora), "datas": dict(datas), "fim_antes_da_criacao": fim_antes,
           "cifras": dict(cifras), "sem_projeto": sum(1 for l in out if l[i_p] is None)}
    return out, rel


def dim_projetos(por_os: dict, anteriores: list[dict]) -> list[list]:
    """1 linha = 1 projeto da FAMA (CAB_DIM): o nome desta leitura e quantas OS ele tem nela. O projeto que não veio fica,
    com o nome de antes e 0 OS: a ligação decidida dele não se perde (a aba só cresce, `catalogo.LIVROS`)."""
    nomes, qtd = {}, Counter()
    for x in por_os.values():
        p = _projeto(x)
        pid = id_fama(p.get("id"))
        if pid is None:
            continue
        qtd[pid] += 1
        if _txt(p.get("name")):
            nomes.setdefault(pid, Counter())[_txt(p.get("name"))] += 1
    out = {pid: [pid, (sorted(nomes[pid].items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if pid in nomes else None), n]
           for pid, n in qtd.items()}
    for d in anteriores or ():
        pid = id_fama(d.get("fama_projeto_id"))
        if pid is not None and pid not in out:
            out[pid] = [pid, _txt(d.get("nome")) or None, 0]
    return [out[p] for p in sorted(out, key=_ordem)]


def ligacao_decidida(de_para: list[dict]) -> tuple[dict, dict]:
    """({fama_projeto_id: usina_id}, relatório) pelas linhas do `cadastro_nexus · de_para`: só o sistema da FAMA, só a
    ligação decidida na tela (`casou_por` "manual ..."; a proposta pelo nome não liga) e só a de UMA usina."""
    from .fatos import _id
    por = {}
    for d in de_para or ():
        if _txt(d.get("sistema")) != SISTEMA or not _txt(d.get("casou_por")).startswith("manual"):
            continue
        pid, uid = id_fama(d.get("chave_externa")), _id(d.get("usina_id"))
        if pid is not None and uid is not None:
            por.setdefault(pid, set()).add(uid)
    lig = {p: next(iter(u)) for p, u in por.items() if len(u) == 1}
    return lig, {"decididas": len(lig), "ambiguas": sum(1 for u in por.values() if len(u) > 1)}


def sha(linhas_fato: list[list], dim: list[list]) -> str:
    """A impressão digital do que vai ao banco (o fato e a dimensão, já em ordem): igual à da última gravação = nada
    mudou na FAMA nem nas ligações, e o livro não é regravado."""
    h = hashlib.sha1()
    for nome, ls in (("fato", linhas_fato), ("dim", dim)):
        h.update(nome.encode("utf-8"))
        for l in ls:
            h.update(json.dumps(l, ensure_ascii=False, default=str).encode("utf-8"))
            h.update(b"\x1e")
    return h.hexdigest()[:16]


def linha_qualidade(linhas_fato: list[list], dim: list[list], rel: dict, origem_em: str, agora: str,
                    linhas_antes: int | None = None) -> list:
    """A linha da aba `qualidade` (`fatos.CAB_QUALIDADE`): quanto liga a data de criação e a usina, os projetos sem a
    ligação decidida (o nome da usina pode ir em claro) e, no `extra`, o relatório da leitura (só contagens)."""
    from .fatos import CAB_QUALIDADE, _exemplos, _pct
    i = {c: CAB_OS_FAMA.index(c) for c in ("data_id_criacao", "usina_id", "fama_projeto_id")}
    n = len(linhas_fato)
    com_data = sum(1 for l in linhas_fato if l[i["data_id_criacao"]] is not None)
    com_usina = sum(1 for l in linhas_fato if l[i["usina_id"]] is not None)
    nomes = {d[0]: d[1] for d in dim}
    sem = Counter((nomes.get(l[i["fama_projeto_id"]]) or f"projeto {l[i['fama_projeto_id']]}")
                  if l[i["fama_projeto_id"]] is not None else "(sem projeto)"
                  for l in linhas_fato if l[i["usina_id"]] is None)
    projetos = {l[i["fama_projeto_id"]] for l in linhas_fato if l[i["fama_projeto_id"]] is not None}
    ligados = {l[i["fama_projeto_id"]] for l in linhas_fato if l[i["usina_id"]] is not None}
    extra = {k: rel.get(k) for k in ("lidas", "repetidas", "sem_id", "fora_do_dominio", "datas", "fim_antes_da_criacao",
                                     "cifras", "sem_projeto", "decididas", "ambiguas") if k in rel}
    extra.update(projetos=len(projetos), projetos_ligados=len(ligados), linhas_na_carga_anterior=linhas_antes)
    valores = {"fato": "os_fama", "livro_origem": "FAMA (API da prestadora) · service-orders", "linhas": n,
               "com_data": com_data, "com_usina": com_usina, "pct_data": _pct(com_data, n),
               "pct_usina": _pct(com_usina, n), "usina_por_de_para": com_usina, "usina_por_codigo": 0,
               "sem_usina_exemplos": _exemplos(sem), "origem_atualizada_em": origem_em, "gerado_em": agora,
               "extra": json.dumps(extra, ensure_ascii=False, sort_keys=True)}
    return [valores.get(c) for c in CAB_QUALIDADE]


def conferir_grao(linhas_fato: list[list]) -> None:
    """Sobe `GraoDuplicado` se o id da OS repete ou vem vazio: o fato não grava contando em dobro."""
    from .fato_ronda import conferir_grao as _conferir_grao
    _conferir_grao(linhas_fato, CAB_OS_FAMA, "fama_os_id")
