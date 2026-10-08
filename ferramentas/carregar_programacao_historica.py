"""Carga ÚNICA do histórico da programação do PCM no banco (passo 6b do Kimball, decisão 7).

Levi, 08/10/2026: "Tem que ter as semanas antigas mesmo, precisamos desses dados pois em menos de duas semanas será full
Nexus". O `banco_dados.json` que o App de Campo e o painel do PCM leem guarda só as 4 semanas mais recentes; as
anteriores só existem no histórico do git do repositório público do PCM (~5.900 versões desde 28/05/2026, uma a cada
~30 min). Esta ferramenta escolhe, para cada semana que já saiu do arquivo, a versão que melhor representa a semana
FECHADA, monta o fato dela com o MESMO código da carga (`programacao.fato_programacao`, os mesmos IDs do cadastro) e
junta às semanas do arquivo atual. Daí em diante, a carga de hora em hora mantém tudo pela mescla por semana
(`carga._programacao`): troca só as semanas que o arquivo traz.

A versão de cada semana (a regra e os casos que a criaram, medidos em 08/10/2026 nas 5.900 versões):
1. A ÚLTIMA versão em que a semana ainda estava no arquivo: o plano publicado + o estado final de cada tarefa. É o que
   a carga de hora em hora vai guardar das semanas futuras (a última leitura antes de a semana sair do arquivo).
2. Depois de fechada, a semana só deve PERDER bloco: o robô do PCM tira a OS cancelada no Fracttal (o "FIX #141" do
   `gerar_pcm_json.py`; a W38 perdeu 88 blocos entre 07/10 e 08/10, todos de OS que sumiram do arquivo inteiro). Por
   isso vale a última versão, depois da segunda-feira seguinte, cujos blocos estavam TODOS no fim da semana; a versão
   com bloco que não existia (bloco novo, ou o mesmo de outro dia ou hora) é a semana regerada depois do fato e não
   conta. Os casos: a W25, regerada em 29/06 com 464 linhas de 19 tarefas (uma só tarefa 75 vezes); a W35, em 31/08 às
   01:28, com 105 tarefas mudadas de dia ou hora; a W26 (29/06) e a W27 (07/07), com OS criadas depois da semana. Sem
   versão assim, vale a do fim da semana. Medido em 08/10: dos 786 blocos que saíram de semanas já fechadas, 740 são de
   OS que não estão mais no `gestao_pcm.json` (o robô do PCM tira de lá as canceladas); os outros 46, da W29, são OS
   vivas (35 "Nova OS") que o robô de julho só mantinha na semana ativa.
3. Semana sem versão de dentro dela (o arquivo só a trouxe depois que ela acabou) fica com a última versão, e o
   relatório diz isso.
4. O arquivo de 28/05 a 12/06/2026 tinha outro formato ("Semana 22", e não "2026-W22"): `formato_atual` traduz, sem
   inventar coluna. A semana que aparece nos dois formatos usa só o atual (o formato antigo é a 1ª versão do painel).

A prova da escolha: as semanas que estão no arquivo atual E no git são montadas pelos dois caminhos e comparadas linha a
linha (têm de dar 0 diferenças), e o relatório mostra, por semana, os blocos do fim da semana, os da versão escolhida e
os que saíram depois (OS cancelada).

Uso (só lê o git e faz GET na API; com --gravar, grava SÓ o `nexus_programacao`; o Fracttal não é tocado):
    python ferramentas/carregar_programacao_historica.py              ensaio: mede e compara, não grava
    python ferramentas/carregar_programacao_historica.py --gravar     grava o livro e confere relendo por GET
    --repo PASTA      o clone COMPLETO do gridco-pcm-data (padrão: C:\\GridcoAuto\\nexus\\pcm_git\\gridco-pcm-data.git;
                      para criar: git clone --bare https://github.com/fillipefigueiro-source/gridco-pcm-data.git)
    --sem-atualizar   não roda o `git fetch` antes (o clone tem de estar em dia com o arquivo do GitHub)
Imprime só contagens e IDs: nenhum nome de pessoa (a ferramenta liga os nomes na memória, como a carga).
"""
import argparse
import json
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nexus.dados import programacao as P  # noqa: E402

_BRT = timezone(timedelta(hours=-3))
REPO_PADRAO = Path(r"C:\GridcoAuto\nexus\pcm_git\gridco-pcm-data.git")
ARQUIVO = "banco_dados.json"
RAMO = "main"
_MESES = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8, "set": 9, "out": 10,
          "nov": 11, "dez": 12}


# ── o git ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def _git(repo: Path, *args) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True,
                          encoding="utf-8").stdout


def versoes(repo: Path, ramo: str = RAMO, arquivo: str = ARQUIVO) -> list[dict]:
    """As versões do arquivo, da mais antiga à mais nova: {commit, ts (epoch), blob}."""
    out, cur = [], None
    for l in _git(repo, "log", ramo, "--format=C %H %ct", "--raw", "--no-abbrev", "--", arquivo).splitlines():
        if l.startswith("C "):
            _c, h, ct = l.split(" ")
            cur = {"commit": h, "ts": int(ct)}
        elif l.startswith(":") and cur is not None:
            partes = l.split("\t")[0].split()
            if partes[4] != "D":
                out.append(dict(cur, blob=partes[3]))
            cur = None
    return out[::-1]


class Blobs:
    """`git cat-file --batch` aberto uma vez: ler 5.900 versões de ~6 MB sem abrir um processo por versão."""

    def __init__(self, repo: Path):
        self.p = subprocess.Popen(["git", "-C", str(repo), "cat-file", "--batch"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE)

    def ler(self, sha: str) -> bytes:
        self.p.stdin.write((sha + "\n").encode())
        self.p.stdin.flush()
        cab = self.p.stdout.readline().decode().split()
        if len(cab) < 3 or cab[1] != "blob":
            raise ValueError(f"objeto {sha} não é um blob no clone")
        dado = self.p.stdout.read(int(cab[2]))
        self.p.stdout.read(1)
        return dado

    def fechar(self):
        self.p.stdin.close()
        self.p.wait(timeout=30)


# ── o formato antigo (28/05 a 12/06/2026) ───────────────────────────────────────────────────────────────────────────
def _ano_da_semana(num: int, seg, mes, candidatos) -> int | None:
    """O ano em que a semana ISO `num` começa no dia `seg` do mês `mes`. O 1º arquivo (28/05) dizia "18–22 Mai 2025",
    mas 18/05/2025 foi um domingo: a semana 21 que começa num 18 de maio é a de 2026. Sem dia, vale o 1º candidato."""
    for a in dict.fromkeys(c for c in candidatos if c):
        try:
            d = date.fromisocalendar(a, num, 1)
        except ValueError:
            continue
        if (seg is None or d.day == seg) and (mes is None or d.month == mes):
            return a
    return None


def formato_atual(semana: dict, ano_do_commit: int | None = None) -> dict | None:
    """A semana no formato do painel de 28/05 a 12/06/2026 traduzida para o formato atual; a que já está no atual volta
    a mesma. None = não dá para saber a semana ISO (não vira fato). O que muda, e só isto:
    - "Semana 22" -> "2026-W22" (o ano: o que faz a segunda-feira da semana ISO cair no dia de `dates.seg`);
    - `dates` com o dia do mês em número sai: a semana ISO e o dia bastam (`programacao.data_do_bloco`);
    - `ativo` ("Cliente - Usina - UF", a Classificação 1 do Fracttal) vai para `usina`, que naquele formato vinha sem a
      UF (o de-para do Fracttal é pelo nome com a UF; sem ela, a usina só ligaria pelo código);
    - `termografia` -> `termo` e `prioridade` -> `criticidade` (as mesmas colunas da planilha, com outro nome)."""
    w = str((semana or {}).get("week") or "").strip()
    if re.fullmatch(r"\d{4}-W\d{1,2}", w.upper()):
        return semana
    m = re.fullmatch(r"semana\s+(\d{1,2})", w, re.IGNORECASE)
    if not m:
        return None
    num, dates = int(m.group(1)), semana.get("dates") or {}
    rotulo = f"{semana.get('label') or ''} {dates.get('label') or ''}"
    m_ano = re.search(r"(20\d\d)", rotulo)
    m_mes = re.search(r"\d+\s*[–-]\s*\d+\s+([A-Za-zç]{3})", rotulo)
    seg = dates.get("seg") if isinstance(dates.get("seg"), int) else None
    mes = _MESES.get(m_mes.group(1).lower()[:3]) if m_mes else None
    ano = _ano_da_semana(num, seg, mes, (dates.get("ano") if isinstance(dates.get("ano"), int) else None,
                                         int(m_ano.group(1)) if m_ano else None, ano_do_commit,
                                         (ano_do_commit or 1) - 1))
    if ano is None:
        return None
    linhas = []
    for r in semana.get("rows") or []:
        if not isinstance(r, dict):
            continue
        r = dict(r)
        if r.get("ativo"):
            r["usina"] = r["ativo"]
        for velho, novo in (("termografia", "termo"), ("prioridade", "criticidade")):
            if velho in r and novo not in r:
                r[novo] = r[velho]
        linhas.append(r)
    return {"week": f"{ano}-W{num:02d}", "num": num, "label": semana.get("label"), "dates": None,
            "geradaEm": semana.get("geradaEm"), "rows": linhas}


# ── a escolha da versão ─────────────────────────────────────────────────────────────────────────────────────────────
def fim_da_semana(week: str) -> datetime:
    """A segunda-feira seguinte, 00:00 de Brasília: a partir daí a semana está fechada."""
    seg = datetime.strptime(str(P.segunda_da_semana(week)), "%Y%m%d").date()
    return datetime.combine(seg + timedelta(days=7), datetime.min.time(), _BRT)


class Escolha:
    """O estado de UMA semana (num formato) ao longo das versões, na ordem: a versão do fim da semana (a última antes
    da segunda-feira seguinte), a última depois dela que só PERDEU blocos (é a escolhida) e a 1ª que trouxe bloco que
    não existia no fim da semana (a regeração, para o relatório).

    Vale a última versão que só perdeu blocos, e não "a última antes da 1ª regeração": a W32 teve 6 tarefas mudadas de
    dia em 14/08 que voltaram depois, e a versão final dela (27/08) só perdeu 7 blocos; parar na 1ª mudança a
    congelaria duas semanas antes, sem os status finais."""

    def __init__(self, week: str, formato: str = "atual"):
        self.week, self.formato, self.fim = week, formato, fim_da_semana(week)
        self.versoes = 0
        self.primeira = self.ultima = None          # índices (a última em que a semana estava no arquivo)
        self.fim_i, self.fim_ids = None, None       # a versão do fim da semana e os blocos dela
        self.aceita = None                          # a última versão aceita pela regra
        self.regerou_i, self.regerou = None, None   # a 1ª versão com bloco novo e quantos blocos novos ela trouxe

    def ver(self, i: int, ts: int, ids: list[str]):
        self.versoes += 1
        self.primeira = i if self.primeira is None else self.primeira
        self.ultima = i
        quando = datetime.fromtimestamp(ts, _BRT)
        if quando < self.fim:
            self.fim_i, self.fim_ids, self.aceita = i, frozenset(ids), i
            return
        if self.fim_ids is not None and not set(ids) <= self.fim_ids:
            if self.regerou_i is None:
                self.regerou_i, self.regerou = i, len(set(ids) - self.fim_ids)
            return
        self.aceita = i

    @property
    def escolhida(self) -> int:
        return self.aceita if self.aceita is not None else self.ultima

    @property
    def regra(self) -> str:
        if self.fim_i is None:
            return "sem versão de dentro da semana: a última"
        if self.escolhida == self.ultima:
            return "a última versão em que a semana estava no arquivo"
        return "mudou depois de fechada (bloco novo ou de outro dia): a última versão que só perdeu blocos"


def varrer(repo: Path, vs: list[dict], progresso=None) -> dict:
    """{(week, formato): Escolha} de todas as semanas de todas as versões. ~7 min nas 5.900 versões (cada uma é um JSON
    de até 6,6 MB): o tempo é ler o JSON, e a ferramenta é de uma vez só."""
    bl = Blobs(repo)
    estados = {}
    try:
        for i, v in enumerate(vs):
            try:
                dados = json.loads(bl.ler(v["blob"]))
            except ValueError:
                continue                            # versão com JSON quebrado: não é candidata a nada
            ano = datetime.fromtimestamp(v["ts"], _BRT).year
            v["gerado"] = (dados or {}).get("geradoEm") or (dados or {}).get("gerado_em")
            for s in (dados or {}).get("semanas") or []:
                if not isinstance(s, dict):
                    continue
                s2 = formato_atual(s, ano)
                if s2 is None or P.segunda_da_semana(s2["week"]) is None:
                    continue
                formato = "atual" if s2 is s else "antigo"
                k = (s2["week"].upper(), formato)
                estados.setdefault(k, Escolha(*k)).ver(i, v["ts"], P.ids_dos_blocos(s2))
            if progresso and i % 500 == 0:
                progresso(i, len(vs))
    finally:
        bl.fechar()
    return estados


def escolhas_por_semana(estados: dict) -> dict:
    """{week: Escolha}: o formato atual quando a semana existe nele; o antigo só para a semana que nunca chegou a ele."""
    out = {}
    for (week, formato), e in sorted(estados.items()):
        if formato == "atual" or week not in out:
            out[week] = e
    return out


def semana_da_versao(repo: Path, v: dict, week: str, formato: str = "atual") -> dict | None:
    """A semana `week` (no `formato` em que foi escolhida) da versão `v`, já no formato atual, num `dados` que o
    `fato_programacao` lê."""
    bl = Blobs(repo)
    try:
        dados = json.loads(bl.ler(v["blob"]))
    finally:
        bl.fechar()
    ano = datetime.fromtimestamp(v["ts"], _BRT).year
    for s in (dados or {}).get("semanas") or []:
        if not isinstance(s, dict):
            continue
        s2 = formato_atual(s, ano)
        if s2 and s2["week"].upper() == week and ("atual" if s2 is s else "antigo") == formato:
            return {"geradoEm": dados.get("geradoEm") or dados.get("gerado_em"), "semanas": [s2]}
    return None


# ── a montagem e a comparação ───────────────────────────────────────────────────────────────────────────────────────
def _quando(ts: int) -> str:
    return datetime.fromtimestamp(ts, _BRT).isoformat(timespec="seconds")


def diferencas(a: list, b: list) -> dict:
    """Compara duas montagens da MESMA semana, linha a linha pelo `programacao_id`, sem o `lido_em` (a hora da leitura
    é a única coisa que pode diferir entre ler o git e ler o arquivo)."""
    i_id, i_lido = P.CAB_PROGRAMACAO.index("programacao_id"), P.CAB_PROGRAMACAO.index("lido_em")
    ma = {l[i_id]: [v for j, v in enumerate(l) if j != i_lido] for l in a}
    mb = {l[i_id]: [v for j, v in enumerate(l) if j != i_lido] for l in b}
    colunas = Counter()
    for k in ma.keys() & mb.keys():
        for c, x, y in zip([c for c in P.CAB_PROGRAMACAO if c != "lido_em"], ma[k], mb[k]):
            if x != y:
                colunas[c] += 1
    return {"so_no_git": len(ma.keys() - mb.keys()), "so_no_arquivo": len(mb.keys() - ma.keys()),
            "em_comum": len(ma.keys() & mb.keys()), "linhas_diferentes": sum(1 for k in ma.keys() & mb.keys()
                                                                             if ma[k] != mb[k]),
            "colunas_diferentes": dict(colunas)}


def _contexto(config, sessao):
    """O que a carga de hora em hora usa para ligar os IDs, montado do mesmo jeito: cadastro, Ligador, mapas (o nome
    só na memória), a dimensão de equipamento e o histórico SCD2 para a junção da época."""
    from nexus.dados import carga, fatos, historico
    le = carga._Leitor(carga._base(config), sessao)
    cad = {a: le.ler(carga.CADASTRO, a) for a in ("usinas", "equipes", "pessoas", "de_para")}
    m = carga._mapas(config, sessao)
    lig = fatos.Ligador(cad["usinas"], cad["de_para"], cad["equipes"], m.get("hmac") or {})
    dados_pcm, lido_em = carga._ler_pcm(config)
    iso = datetime.now(_BRT).isoformat(timespec="seconds")
    _eqt, _pub, rel_eq, equip = carga._equipamentos(le, cad, dados_pcm, iso, carga._maquina())
    hist_q = {e: historico.migrar(le.ler(carga.LIVRO_DIM, f"{e}_historico"), e) for e in historico.RASTREADOS}
    return {"le": le, "lig": lig, "pessoas": m.get("pessoa") or {}, "equip": equip, "dados_pcm": dados_pcm,
            "lido_em": lido_em, "rel_eq": rel_eq, "hist_q": hist_q, "iso": iso}


def montar(config, sessao, repo: Path, *, atualizar: bool = True, log=print) -> dict:
    """Tudo menos gravar: a escolha por semana, o fato do histórico + o do arquivo atual, a comparação e as medidas."""
    if _git(repo, "rev-parse", "--is-shallow-repository").strip() != "false":
        raise SystemExit(f"{repo} é um clone raso: faltariam as semanas antigas (use um clone completo)")
    if atualizar:
        _git(repo, "fetch", "--quiet", "origin", f"+refs/heads/{RAMO}:refs/heads/{RAMO}")
    t0 = time.time()
    # o arquivo atual é lido logo depois do fetch: assim a versão dele já está no clone (a prova precisa dela)
    ctx = _contexto(config, sessao)
    if ctx["dados_pcm"] is None:
        raise SystemExit("sem o banco_dados.json atual (GitHub fora do ar?): nada montado")
    vs = versoes(repo)
    log(f"{len(vs)} versões de {ARQUIVO} no git ({_quando(vs[0]['ts'])} a {_quando(vs[-1]['ts'])})")
    estados = varrer(repo, vs, lambda i, n: log(f"  varrendo {i}/{n} ({round(time.time() - t0)} s)"))
    escolhas = escolhas_por_semana(estados)
    atuais = sorted({str(s.get("week")).upper() for s in ctx["dados_pcm"].get("semanas") or [] if s.get("week")})
    monta = lambda dados, lido: P.fato_programacao(dados, ctx["lig"], ctx["pessoas"], ctx["equip"], lido)  # noqa: E731
    fato_atual, rel_atual = monta(ctx["dados_pcm"], ctx["lido_em"])
    # a prova compara a MESMA publicação pelos dois caminhos: a versão do git com o geradoEm do arquivo lido agora (o
    # robô publica a cada ~30 min; comparar com outra versão mostraria a diferença entre duas rodadas, não entre caminhos)
    mesma = next((i for i in range(len(vs) - 1, -1, -1) if vs[i].get("gerado") == ctx["dados_pcm"].get("geradoEm")),
                 None)
    historico, por_semana, prova = [], {}, {"versao_do_arquivo_no_git": None if mesma is None else
                                            vs[mesma]["commit"][:9], "semanas": {}}
    for week, e in sorted(escolhas.items(), key=lambda kv: P.segunda_da_semana(kv[0])):
        v = vs[e.escolhida]
        dados = semana_da_versao(repo, v, week, e.formato)
        linhas, rel = monta(dados, _quando(v["ts"])) if dados else ([], {})
        ids = {l[0] for l in linhas}
        info = {"versao": v["commit"][:9], "versao_em": _quando(v["ts"]), "regra": e.regra, "formato": e.formato,
                "versoes": e.versoes, "no_arquivo_de": _quando(vs[e.primeira]["ts"]),
                "no_arquivo_ate": _quando(vs[e.ultima]["ts"]), "blocos": len(linhas), "tarefas": rel.get("tarefas"),
                "fora_do_plano": rel.get("fora_do_plano"),
                "blocos_no_fim_da_semana": len(e.fim_ids) if e.fim_ids is not None else None,
                "sairam_depois_do_fim": len(e.fim_ids - ids) if e.fim_ids is not None else None,
                "fonte": "arquivo atual" if week in atuais else "git"}
        if e.regerou_i is not None:
            # a 1ª versão depois de fechada com bloco que não estava no fim da semana; "passageira" = depois dela a
            # semana voltou a só perder blocos e a escolhida é posterior (a W32 em 14/08)
            info.update(mudou_depois_de_fechada_em=_quando(vs[e.regerou_i]["ts"]), blocos_novos=e.regerou,
                        passageira=e.escolhida > e.regerou_i, ultima_versao_em=_quando(vs[e.ultima]["ts"]))
        if week in atuais:
            do_arquivo = [l for l in fato_atual if P.semana_iso(l[1]) == week]
            dados_git = semana_da_versao(repo, vs[mesma], week) if mesma is not None else None
            git = monta(dados_git, ctx["lido_em"])[0] if dados_git else []
            prova["semanas"][week] = dict(diferencas(git, do_arquivo),
                                          escolha_da_regra_e_a_versao_do_arquivo=(e.escolhida == mesma))
            info["blocos"] = len(do_arquivo)
        else:
            historico += linhas
        por_semana[week] = info
    linhas = P.mesclar_semanas(historico, fato_atual)
    rm = P.resumo_das_linhas(linhas, rel_atual)
    return {"vs": vs, "escolhas": escolhas, "ctx": ctx, "linhas": linhas, "fato_atual": fato_atual,
            "rel_atual": rel_atual, "resumo": rm, "por_semana": por_semana, "prova": prova, "atuais": atuais,
            "tempo_s": round(time.time() - t0, 1)}


# ── gravar e conferir ───────────────────────────────────────────────────────────────────────────────────────────────
def gravar(config, sessao, r: dict, log=print) -> dict:
    """Grava o `nexus_programacao` (só ele) e confere relendo por GET: a contagem POR SEMANA tem de ser a enviada e o
    sha das linhas relidas, o gravado. O fato que já estiver no banco não se perde: as semanas dele que esta carga não
    traz ficam (a mesma mescla da carga de hora em hora); leitura que falha ou volta vazia com o livro existente
    aborta sem gravar."""
    from nexus.dados import carga, livros
    base = carga._base(config)
    ctx = r["ctx"]
    # conferir ANTES de gravar: a prova sem diferença e nenhuma semana vazia
    ruins = {w: p for w, p in r["prova"]["semanas"].items()
             if p["so_no_git"] or p["so_no_arquivo"] or p["linhas_diferentes"]}
    if r["prova"]["versao_do_arquivo_no_git"] is None or ruins:
        raise SystemExit(f"a prova git × arquivo não fechou ({ruins or 'versão do arquivo fora do clone'}): nada gravado")
    vazias = [w for w, i in r["por_semana"].items() if not i["blocos"]]
    if vazias:
        raise SystemExit(f"semanas sem bloco {vazias}: nada gravado")
    no_banco = []
    if ctx["le"].abas(P.LIVRO):
        no_banco = livros.ler(base, sessao, P.LIVRO, P.ABA)
        if not no_banco:
            raise SystemExit("o livro existe e o fato veio vazio: nada gravado (o fato não encolhe)")
    linhas = P.manter_lido_em(P.mesclar_semanas(no_banco, r["linhas"]), no_banco)
    tab, rm, _q = carga.tabelas_programacao(linhas, r["rel_atual"], ctx["hist_q"], ctx["iso"], carga._maquina(),
                                            P.sha_linhas(r["fato_atual"]))
    if rm["ids_repetidos"]:
        raise SystemExit(f"{rm['ids_repetidos']} programacao_id repetidos: nada gravado")
    enviado = Counter(P.semana_iso(l[1]) for l in linhas)
    log(f"gravando {len(linhas)} linhas em {len(enviado)} semanas ({len(no_banco)} já no banco)")
    gravado = livros.publicar(P.LIVRO, P.NOME_LIVRO, tab, base=base, token=config["GRIDCO_SQL_TOKEN"], sessao=sessao)
    relido = livros.ler(base, sessao, P.LIVRO, P.ABA)
    no_banco_agora = Counter(P.semana_iso(d.get("data_id_semana")) for d in relido)
    sha_enviado = tab["atualizacao"][1][0][P.CAB_ATUALIZACAO.index("sha_linhas")]
    sha_relido = P.sha_linhas(P.mesclar_semanas(relido, []))
    conf = {"gravado": gravado, "por_semana_enviado": dict(sorted(enviado.items())),
            "por_semana_no_banco": dict(sorted(no_banco_agora.items())),
            "semanas_diferentes": sorted(w for w in enviado.keys() | no_banco_agora.keys()
                                         if enviado.get(w) != no_banco_agora.get(w)),
            "sha_enviado": sha_enviado, "sha_relido": sha_relido, "sha_igual": sha_enviado == sha_relido,
            "ids_relidos_unicos": len({d.get("programacao_id") for d in relido}) == len(relido)}
    if conf["semanas_diferentes"] or not conf["sha_igual"] or not conf["ids_relidos_unicos"]:
        raise SystemExit("CONFERÊNCIA FALHOU depois de gravar: " + json.dumps(conf, ensure_ascii=False, default=str))
    return conf


def relatorio(r: dict) -> dict:
    rm = r["resumo"]
    return {"semanas": len(rm["semanas"]), "da_mais_antiga": rm["semanas"][0] if rm["semanas"] else None,
            "ate": rm["semanas"][-1] if rm["semanas"] else None, "linhas": rm["linhas"], "tarefas": rm["tarefas"],
            "ids_repetidos": rm["ids_repetidos"], "pct": rm["pct"], "com": rm["com"],
            "usina_por_de_para": rm["usina_por_de_para"], "usina_por_codigo": rm["usina_por_codigo"],
            "por_semana": r["por_semana"], "prova_git_x_arquivo": r["prova"], "semanas_do_arquivo": r["atuais"],
            "dimensao_de_equipamento": {k: r["ctx"]["rel_eq"].get(k) for k in ("erro", "indice", "membros")
                                         if k in r["ctx"]["rel_eq"]},
            "tempo_s": r["tempo_s"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=REPO_PADRAO)
    ap.add_argument("--gravar", action="store_true", help="grava o nexus_programacao e confere (sem: só ensaio)")
    ap.add_argument("--ensaio", action="store_true", help="o padrão: mede e compara, não grava")
    ap.add_argument("--sem-atualizar", action="store_true", help="não roda o git fetch antes")
    a = ap.parse_args()
    import requests
    from nexus import create_app
    app = create_app()
    s = requests.Session()
    log = lambda *x: print(*x, file=sys.stderr, flush=True)        # noqa: E731 — o progresso vai para o stderr
    with app.app_context():
        r = montar(app.config, s, a.repo, atualizar=not a.sem_atualizar, log=log)
        rel = relatorio(r)
        if a.gravar and not a.ensaio:
            if not app.config.get("GRIDCO_SQL_TOKEN"):
                raise SystemExit("sem GRIDCO_SQL_TOKEN: nada gravado")
            rel["conferencia"] = gravar(app.config, s, r, log)
        else:
            rel["ensaio"] = "montado com o dado real; nada gravado"
    print(json.dumps(rel, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
