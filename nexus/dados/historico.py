"""O histórico das dimensões que mudam com o tempo (no método Kimball, "SCD tipo 2": válido de / até).

Por que existe: o cadastro do Nexus guarda só o ESTADO ATUAL. Quando um técnico muda de equipe ou de supervisor, a nota
de agosto dele passaria a contar para o supervisor novo. Aqui cada membro (pessoa, usina) tem versões; mudar um campo
RASTREADO fecha a versão vigente e abre outra. Para saber de quem era o fechamento de 12/08: a versão do membro com
valido_de_id <= 20260812 < valido_ate_id (`da_epoca`).

**Grão: 1 linha = 1 versão de 1 membro, com a troca no dia de Brasília** (grão diário: o dia fica com o último estado).
Chave: (id, versao). Junção com o fato: `valido_de_id <= data_id < valido_ate_id` (aberto = 99991231). `valido_de` e
`valido_ate` continuam em texto AAAA-MM-DD (aberto = vazio) para quem já lê. Não é fato: não tem tipo nem medidas.
Anda de hora em hora, na carga (:40), no livro `nexus_dimensoes`.

As regras, cada uma com o caso que a criou (auditoria Kimball de 08/10/2026):

1. **A 1ª versão de todo membro vale "desde sempre" (1900-01-01), com `inicio_presumido = 1`.** Até 08/10 ela começava
   no `alterado_em` da importação do cadastro (30/09) e os fatos começam em 11/08: a junção da época não achava versão
   para 74,9% dos fechamentos com pessoa e 73,8% com usina. Antes de existir histórico, vale o que se sabia na 1ª
   carga. É uma presunção (a auditoria chamou de chute), por isso fica marcada: quem quer só o que foi visto filtra
   `inicio_presumido = 0`. As linhas já gravadas migram na carga seguinte (`migrar`, idempotente); membro novo nasce do
   mesmo jeito (dimensão que chega atrasada).
2. **Dia de Brasília.** O `alterado_em` do cadastro vem em UTC ("…Z"): 133 de 134 pessoas tinham 30/09 02:xxZ, que é
   29/09 em Brasília. A 1ª versão usava o dia UTC e as trocas, o de Brasília; ficha criada depois das 21h nascia no dia
   seguinte e o fato do próprio dia não achava versão.
3. **A troca vale no dia do `alterado_em`**, limitado entre o início da vigente e hoje. Antes valia o dia da carga que
   a viu: troca gravada na segunda e publicada na sexta mandava segunda a quinta para o supervisor antigo. O
   `alterado_em` é a última edição de QUALQUER campo (pode cair depois da troca rastreada), mas fica mais perto.
4. **Duas trocas no mesmo dia = uma versão.** Antes nascia [06/10, 06/10), que nunca casa e repete a chave
   (id, valido_de). Troca que desfaz a do mesmo dia reabre a versão anterior.
5. **Reentrada abre hoje.** Membro fechado que volta reabria no `alterado_em` antigo, por cima da versão fechada: o
   fato de 01/10 casava 2 versões (simulado na auditoria).
6. **Só `excluido = sim` fecha.** O cadastro não apaga linha: quem some da leitura é leitura falha ou publicação menor,
   e antes isso fechava todo mundo. Cadastro lido vazio, ou histórico anterior lido vazio com o livro já gravado: o
   histórico NÃO anda nesta carga e `pulou_motivo` diz por quê.
7. **Conferir antes de publicar** (`conferir`, usado por `tabelas`): por membro, sem sobreposição, sem buraco e com uma
   vigente. Se a carga piorou algum desses além do que as exclusões e reentradas dela explicam, sai o anterior.

O que isto NÃO segura (herda dos passos 0 e 1, adiados pelo Levi em 08/10/2026):
- O histórico continua refeito a partir de si mesmo e regravado inteiro a cada hora. Uma leitura PARCIAL que volte com
  200 não é pega: o membro cujas linhas faltaram renasce "desde sempre" e as versões fechadas dele somem. Só o log
  só-acréscimo do passo 0 resolve.
- Com dois donos do cadastro (passo 1), uma publicação antiga vira mudança real. As regras 3 e 4 amortecem o vai e vem
  (a troca com data anterior cai no início da vigente e a sobrescreve; voltar ao estado anterior reabre a versão), mas
  não o impedem.

Só os campos que mudam a análise são acompanhados (RASTREADOS); mudar o resto não abre versão. Nada sensível: só IDs e
campos que já vão em claro no `cadastro_nexus`.
"""
from datetime import date, datetime, timedelta, timezone

from .calendario import data_id as _data_id

RASTREADOS = {
    "pessoas": ("pessoa_id", ("equipe_id", "supervisor_id", "cargo", "vinculo", "status")),
    "usinas": ("usina_id", ("cliente_id", "equipe_id", "status", "responsavel_om_id", "tecnico_om_id", "cluster",
                            "regiao")),
}
# Gravadas no banco desde a 1ª carga (05/10/2026): para elas, o livro existir basta para a regra 6 (ver `ja_gravado`).
GRAVADAS_DESDE_05_10 = ("pessoas", "usinas")
ABERTO = None                       # valido_ate (texto) de quem está vigente
ABERTO_ID = 99991231                # valido_ate_id de quem está vigente: a junção é um `<` sem caso especial
DESDE_SEMPRE = date(1900, 1, 1)     # início presumido da 1ª versão (regra 1)
DESDE_SEMPRE_ID = 19000101
_FIM = ("versao", "valido_de", "valido_ate", "valido_de_id", "valido_ate_id", "vigente", "inicio_presumido")
ABA_QUALIDADE = "qualidade_historico"
CAB_QUALIDADE = ["entidade", "membros", "versoes", "presumidas", "sobreposicoes", "buracos", "sem_vigente",
                 "ausentes_na_leitura", "pulou_motivo", "gerado_em"]
_BRT = timezone(timedelta(hours=-3))


def cabecalho(entidade: str) -> list:
    col_id, cols = RASTREADOS[entidade]
    return [col_id, *cols, *_FIM]


def _v(x):
    """O mesmo valor, venha a API com 12, 12.0 ou "12": a mudança é do dado, não do tipo."""
    if x is None or (isinstance(x, str) and not x.strip()):
        return None
    if isinstance(x, float) and x.is_integer():
        return int(x)
    if isinstance(x, str):
        s = x.strip()
        try:
            f = float(s)
            return int(f) if f.is_integer() else s
        except ValueError:
            return s
    return x


def dia_brt(iso) -> date | None:
    """O dia de Brasília de um carimbo: "2026-09-30T02:15:00Z" (UTC) → 29/09/2026.

    Sem fuso = UTC (é como o cadastro e o App gravam). Só a data ("2026-09-30") = o próprio dia: não há hora para
    converter, e tratá-la como meia-noite UTC a jogaria para o dia anterior."""
    if iso is None:
        return None
    if isinstance(iso, datetime):
        d = iso
    elif isinstance(iso, date):
        return iso
    else:
        s = str(iso).strip()
        if not s:
            return None
        if len(s) == 10:
            try:
                return date.fromisoformat(s)
            except ValueError:
                return None
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(_BRT).date()


def _de_id(i) -> date | None:
    i = _v(i)
    if not isinstance(i, int) or i == ABERTO_ID:
        return None
    try:
        return date(i // 10000, i // 100 % 100, i % 100)
    except ValueError:
        return None


def _dia(texto, id_=None) -> date | None:
    """Uma ponta da versão: o texto AAAA-MM-DD (o formato de antes de 08/10 só tinha ele) ou o inteiro AAAAMMDD."""
    if isinstance(texto, datetime):
        return texto.date()
    if isinstance(texto, date):
        return texto
    s = str(texto or "").strip()[:10]
    if s:
        try:
            return date.fromisoformat(s)
        except ValueError:
            pass
    return _de_id(id_)


def _excluido(a: dict) -> bool:
    return str(a.get("excluido") or "").strip().lower() in ("sim", "1", "true")


def _como_dicts(linhas, entidade: str) -> list[dict]:
    cab = cabecalho(entidade)
    return [l if isinstance(l, dict) else dict(zip(cab, l)) for l in linhas or []]


def _versoes(linhas, entidade: str, *, migrar_inicio: bool) -> dict:
    """{id: [versão, …]} em ordem de início. Cada versão: attrs, de, ate (None = vigente), presumido, versao.

    Com `migrar_inicio`, a 1ª versão de cada membro passa a "desde sempre" (regra 1) e some a versão de duração zero
    (início = fim: a de duas trocas no mesmo dia antes de 08/10, que nunca casa com fato e repete a chave)."""
    col_id, cols = RASTREADOS[entidade]
    por = {}
    for h in _como_dicts(linhas, entidade):
        rid = _v(h.get(col_id))
        if rid is None:
            continue
        ver = _v(h.get("versao"))
        por.setdefault(rid, []).append({"attrs": tuple(_v(h.get(c)) for c in cols),
                                        "de": _dia(h.get("valido_de"), h.get("valido_de_id")),
                                        "ate": _dia(h.get("valido_ate"), h.get("valido_ate_id")),
                                        "presumido": 1 if _v(h.get("inicio_presumido")) == 1 else 0,
                                        "versao": ver if isinstance(ver, int) else 0})
    for vs in por.values():
        if migrar_inicio:
            vs[:] = [x for x in vs if x["de"] is None or x["ate"] is None or x["ate"] != x["de"]] or vs
        vs.sort(key=lambda x: (x["de"] or date.min, x["ate"] or date.max, x["versao"]))
        if migrar_inicio:
            vs[0]["de"], vs[0]["presumido"] = DESDE_SEMPRE, 1
    return por


def _ordem_id(rid):
    return (0, rid, "") if isinstance(rid, (int, float)) else (1, 0, str(rid))


def _linhas(por: dict) -> list[list]:
    out = []
    for rid in sorted(por, key=_ordem_id):
        for n, x in enumerate(por[rid], 1):
            de, ate = x["de"], x["ate"]
            out.append([rid, *x["attrs"], n, de.isoformat() if de else None, ate.isoformat() if ate else ABERTO,
                        _data_id(de) if de else None, _data_id(ate) if ate else ABERTO_ID,
                        "sim" if ate is None else "não", x["presumido"]])
    return out


def migrar(anteriores: list[dict], entidade: str) -> list[dict]:
    """O histórico gravado, no cabeçalho de 08/10: a versão de menor `valido_de` de cada membro vira 1900-01-01 /
    19000101 com `inicio_presumido = 1`, `versao` numerada 1, 2… por membro e os `*_id` calculados. Idempotente:
    aplicar duas vezes dá o mesmo que uma. `atualizar` já migra; esta é a mesma conta, exposta para medir e testar."""
    cab = cabecalho(entidade)
    return [dict(zip(cab, l)) for l in _linhas(_versoes(anteriores, entidade, migrar_inicio=True))]


def _limite(quando: date | None, de: date, hoje: date) -> date:
    """Dia da troca (regra 3): o do `alterado_em`, nunca antes do início da vigente nem depois de hoje."""
    return min(max(quando or hoje, de), max(hoje, de))


def atualizar(entidade: str, atuais: list[dict], anteriores: list[dict], hoje, *,
              livro_existe: bool = False) -> tuple[list[list], dict]:
    """O histórico novo a partir do cadastro lido agora (`atuais`) e do histórico gravado (`anteriores`).

    Devolve (linhas no `cabecalho(entidade)`, relatório). `hoje` = o dia de Brasília da carga (date ou "AAAA-MM-DD").
    `livro_existe`: o histórico desta entidade já foi gravado antes (ver `ja_gravado`); com ele, um anterior lido vazio
    é leitura falha, não começo (regra 6). No relatório: `publicar = False` = não publique a aba desta entidade;
    `segurar = True` = não publique o livro nesta hora (o anterior veio vazio: publicar trocaria o histórico por
    nada)."""
    col_id, cols = RASTREADOS[entidade]
    if isinstance(hoje, datetime):
        hoje = hoje.astimezone(_BRT).date() if hoje.tzinfo else hoje.date()
    elif not isinstance(hoje, date):
        hoje = date.fromisoformat(str(hoje)[:10])
    rel = {"entidade": entidade, "novos": 0, "trocas": 0, "trocas_no_mesmo_dia": 0, "exclusoes": 0, "reentradas": 0,
           "ausentes_na_leitura": 0, "repetidos_no_cadastro": 0, "pulou_motivo": None, "publicar": True,
           "segurar": False}
    vistos = {}
    for a in atuais or []:
        rid = _v(a.get(col_id))
        if rid is None:
            continue
        if rid in vistos:
            rel["repetidos_no_cadastro"] += 1
            continue
        vistos[rid] = a
    if not anteriores and livro_existe:
        rel.update(pulou_motivo="histórico anterior lido vazio com o livro já gravado: nada publicado nesta carga",
                   publicar=False, segurar=True)
        return [], _contar(rel, {})
    por = _versoes(anteriores, entidade, migrar_inicio=True)
    if not vistos:
        rel["pulou_motivo"] = "cadastro lido vazio: o histórico não andou nesta carga"
        # nada antes e nada agora: não cria aba vazia (a carga seguinte a acharia vazia com o livro gravado e seguraria)
        rel["publicar"] = bool(por)
        return _linhas(por), _contar(rel, por)

    for rid, a in vistos.items():
        vs = por.get(rid)
        agora = tuple(_v(a.get(c)) for c in cols)
        quando = dia_brt(a.get("alterado_em"))
        vig = vs[-1] if vs and vs[-1]["ate"] is None else None
        if _excluido(a):
            if vig is not None:                                   # só a exclusão fecha (regra 6)
                t = _limite(quando, vig["de"], hoje)
                if t == vig["de"]:
                    vs.pop()          # vigente de duração zero some; a anterior já termina neste dia
                else:
                    vig["ate"] = t
                rel["exclusoes"] += 1
            continue
        if not vs:                                                # membro novo: desde sempre (regra 1)
            por[rid] = [{"attrs": agora, "de": DESDE_SEMPRE, "ate": None, "presumido": 1, "versao": 0}]
            rel["novos"] += 1
            continue
        if vig is None:                                           # reentrada: abre hoje (regra 5)
            ult = vs[-1]
            de = max(hoje, ult["ate"])
            if ult["ate"] == de and ult["attrs"] == agora:
                ult["ate"] = None     # saiu e voltou igual no mesmo dia: a mesma versão segue
            else:
                vs.append({"attrs": agora, "de": de, "ate": None, "presumido": 0, "versao": 0})
            rel["reentradas"] += 1
            continue
        if vig["attrs"] == agora:
            continue
        t = _limite(quando, vig["de"], hoje)
        if t == vig["de"]:                                        # 2ª troca no mesmo dia: sobrescreve (regra 4)
            vig["attrs"] = agora
            rel["trocas_no_mesmo_dia"] += 1
            ant = vs[-2] if len(vs) > 1 else None
            if ant is not None and ant["ate"] == vig["de"] and ant["attrs"] == agora:
                vs.pop()
                ant["ate"] = None     # desfez a troca do mesmo dia: a versão anterior reabre
        else:
            vig["ate"] = t
            vs.append({"attrs": agora, "de": t, "ate": None, "presumido": 0, "versao": 0})
            rel["trocas"] += 1
    # ausência não fecha (regra 6): só conta, para a qualidade mostrar quantos o cadastro deixou de trazer
    rel["ausentes_na_leitura"] = sum(1 for rid, vs in por.items()
                                     if rid not in vistos and vs and vs[-1]["ate"] is None)
    return _linhas(por), _contar(rel, por)


def _contar(rel: dict, por: dict) -> dict:
    rel.update(membros=len(por), versoes=sum(len(v) for v in por.values()),
               presumidas=sum(1 for v in por.values() for x in v if x["presumido"]))
    return rel


def conferir(linhas, entidade: str) -> dict:
    """Saúde do histórico, por membro: {sobreposicoes, buracos, sem_vigente}.

    sobreposicoes = pares de versões seguidas em que a 2ª começa antes de a 1ª acabar (inclui 2 vigentes) e versões que
    acabam antes de começar; buracos = pares em que a 2ª começa depois de a 1ª acabar (fato desse intervalo não acha
    versão); sem_vigente = membros sem versão aberta. Não migra nada: confere o que vai ser publicado."""
    por = _versoes(linhas, entidade, migrar_inicio=False)
    sob = bur = sem = 0
    for vs in por.values():
        sob += sum(1 for x in vs if x["de"] is not None and x["ate"] is not None and x["ate"] < x["de"])
        for p, n in zip(vs, vs[1:]):
            if p["ate"] is None or (n["de"] or date.min) < p["ate"]:
                sob += 1
            elif (n["de"] or date.min) > p["ate"]:
                bur += 1
        sem += not any(x["ate"] is None for x in vs)
    return {"sobreposicoes": sob, "buracos": bur, "sem_vigente": sem}


_COLS_ID = tuple(c for c, _ in RASTREADOS.values())


def _intervalo(l) -> tuple:
    """(id, valido_de_id, valido_ate_id) de uma linha do histórico: dict (lido do banco; no formato de antes de 08/10,
    sem os `*_id`, usa o texto) ou lista no `cabecalho` novo (montada pela carga)."""
    if isinstance(l, dict):
        rid = next((l[c] for c in _COLS_ID if c in l), None)
        de, ate = _v(l.get("valido_de_id")), _v(l.get("valido_ate_id"))
        if not isinstance(de, int):
            d = _dia(l.get("valido_de"))
            de = _data_id(d) if d else None
        if not isinstance(ate, int):
            d = _dia(l.get("valido_ate"))
            ate = _data_id(d) if d else ABERTO_ID
        return _v(rid), de, ate
    return _v(l[0]), _v(l[-4]), _v(l[-3])


def _indice(historico) -> dict:
    idx = {}
    for l in historico or []:
        rid, de, ate = _intervalo(l)
        if rid is not None and isinstance(de, int) and isinstance(ate, int):
            idx.setdefault(rid, []).append((de, ate, l))
    return idx


def _achar(idx: dict, rid, data_id) -> list:
    rid, d = _v(rid), _v(data_id)
    if rid is None or not isinstance(d, int):
        return []
    return [l for de, ate, l in idx.get(rid, ()) if de <= d < ate]


def da_epoca(historico, id_, data_id):
    """A versão do membro `id_` que valia no dia `data_id` (AAAAMMDD), ou None se não há EXATAMENTE uma.

    Mais de uma (sobreposição) também é None: devolver a primeira esconderia o defeito e atribuiria o fato ao acaso.
    `historico` = as linhas da aba (dicts, como o banco devolve) ou as montadas pela carga (listas)."""
    achou = _achar(_indice(historico), id_, data_id)
    return achou[0] if len(achou) == 1 else None


def cobertura(linhas_fato, cab: list, col_id: str, col_data: str, historico) -> tuple[int, int]:
    """(fatos com ID e data, quantos deles acham EXATAMENTE 1 versão): a base de `pct_pessoa_versao` e
    `pct_usina_versao` na qualidade dos fatos.

    Medido em 08/10/2026 com o histórico de antes: 25,4% dos fechamentos (pessoa) e 26,4% (usina); a meta é 100%."""
    idx = _indice(historico)
    i_id, i_d = cab.index(col_id), cab.index(col_data)
    n = um = 0
    for l in linhas_fato or []:
        rid, d = (l.get(col_id), l.get(col_data)) if isinstance(l, dict) else (l[i_id], l[i_d])
        if _v(rid) is None or _v(d) is None:
            continue
        n += 1
        um += len(_achar(idx, rid, d)) == 1
    return n, um


def ja_gravado(abas_dim, entidade: str) -> bool:
    """O histórico desta entidade já foi gravado antes? Decide a regra 6 (anterior lido vazio = leitura falha).

    `abas_dim` = as abas do `nexus_dimensoes` (o `livros.abas`). Pessoas e usinas estão no banco desde 05/10/2026: basta
    o livro existir (aba `atualizacao`), mesmo que a listagem não traga a aba delas, que é justamente a leitura falha
    (`livros.ler` devolve vazio quando a aba não aparece). Entidade que entrar depois em RASTREADOS: só quando a aba
    dela aparecer, senão a 1ª carga dela nunca andaria."""
    abas_dim = abas_dim or ()
    if "atualizacao" not in abas_dim:
        return False
    return entidade in GRAVADAS_DESDE_05_10 or f"{entidade}_historico" in abas_dim


def tabelas(cadastro: dict, anteriores: dict, hoje, gerado_em: str, abas_dim=()) -> tuple[dict, dict]:
    """O que a carga põe no `nexus_dimensoes`: {aba: (cabeçalho, linhas)} com `<entidade>_historico` e a
    `qualidade_historico`, e o relatório {entidade: rel, "segurar": bool}. Pura: não lê nem grava.

    Conferência (regra 7): se o histórico novo tem mais sobreposição que o anterior, ou mais buraco / membro sem vigente
    do que as reentradas / exclusões desta carga explicam, sai o anterior (migrado) e `pulou_motivo` diz o que achou.
    `segurar = True`: o histórico anterior de alguma entidade veio vazio com o livro já gravado; a aba dela NÃO vem e a
    carga não deve publicar o `nexus_dimensoes` nesta hora (a gravação troca o livro: seria trocar o histórico por
    nada)."""
    tab, rel, qual = {}, {"segurar": False}, []
    for e in RASTREADOS:
        ant = (anteriores or {}).get(e) or []
        linhas, r = atualizar(e, (cadastro or {}).get(e) or [], ant, hoje, livro_existe=ja_gravado(abas_dim, e))
        if r["publicar"]:
            novo = conferir(linhas, e)
            antes_l = _linhas(_versoes(ant, e, migrar_inicio=True))
            antes = conferir(antes_l, e)
            if (novo["sobreposicoes"] > antes["sobreposicoes"]
                    or novo["buracos"] > antes["buracos"] + r["reentradas"]
                    or novo["sem_vigente"] > antes["sem_vigente"] + r["exclusoes"]):
                r["pulou_motivo"] = (f"conferência falhou ({novo['sobreposicoes']} sobreposições, {novo['buracos']} "
                                     f"buracos, {novo['sem_vigente']} sem vigente): publicado o histórico anterior")
                r["conferencia_recusada"] = novo
                linhas = antes_l
                _contar(r, _versoes(linhas, e, migrar_inicio=False))
            tab[f"{e}_historico"] = (cabecalho(e), linhas)
        rel["segurar"] = rel["segurar"] or r["segurar"]
        c = conferir(linhas, e)
        r.update(c)
        qual.append([e, r["membros"], r["versoes"], r["presumidas"], c["sobreposicoes"], c["buracos"],
                     c["sem_vigente"], r["ausentes_na_leitura"], r["pulou_motivo"], gerado_em])
        rel[e] = r
    tab[ABA_QUALIDADE] = (CAB_QUALIDADE, qual)
    return tab, rel
