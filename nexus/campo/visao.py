"""A visão do Nexus para o Campo · App: as telas que antes abriam o painel do App (no Azure) numa moldura, agora com dado
nosso (Levi, 05/10/2026: "quero parar de referenciar o Azure e ter uma visão nossa!").

Tudo vem do banco (API db_performace), nunca do App nem do Azure:
- os livros que o próprio App grava de hora em hora (aos :25): `fechamentos_app_campo`, `pt_app_campo`,
  `zeladoria_app_campo`, `decisoes_app_campo` e `rondas_app_campo`;
- o cadastro do Nexus (`cadastro_nexus`): as usinas MOBILIZADAS (status OPERAÇÃO e data de mobilização já passada) e a
  equipe, o estado e a cidade de cada uma. A usina que o App escreve liga ao `usina_id` pelo mesmo `Ligador` da camada
  de dados (de-para do Fracttal; código do ativo de reserva).
A pessoa vem do App como código do e-mail (HMAC): o nome sai do cadastro do App (`identidades.json`), na hora, no
"Nome padrão" do cadastro (primeiro e último nome). Cópia de 5 min por tela; banco fora do ar = a tela avisa, não some.

As contas são NOSSAS e estão escritas em cada função: quem quiser saber por que um número deu tanto lê aqui.
"""
import re
import statistics
import time
from datetime import datetime, timedelta, timezone

from flask import current_app

from ..cadastro.calculos import nome_padrao
from ..dados import fatos as D
from ..dados import livros
from . import leitura, livros_app

_BRT = timezone(timedelta(hours=-3))
STATUS_OPERACAO = "OPERAÇÃO"
DIAS_SEM_RONDA_ALERTA = 7        # usina mobilizada sem ronda há 7 dias ou mais = ronda pendente
DIAS_COBERTURA = 14              # janela da cobertura de ronda (a mesma do ranking por região)
PT_PARADA_MIN = 120              # PT esperando o De acordo há mais de 2 h = parada
PESO_QUALIDADE, PESO_COBERTURA = 0.6, 0.4     # ranking por região, a mesma régua do painel do App
_DATA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")
# Região do Brasil pela UF do cadastro (Levi, 05/10: "Adicione uma coluna de região do Brasil"). Pela UF, e não pela
# coluna `regiao` do cadastro: medido em 05/10, ela tem "Centro Oeste" e "Centro-Oeste" e 2 usinas vazias.
REGIOES = ("Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul")
REGIAO_DA_UF = {**dict.fromkeys(("AC", "AP", "AM", "PA", "RO", "RR", "TO"), "Norte"),
                **dict.fromkeys(("AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"), "Nordeste"),
                **dict.fromkeys(("DF", "GO", "MT", "MS"), "Centro-Oeste"),
                **dict.fromkeys(("ES", "MG", "RJ", "SP"), "Sudeste"),
                **dict.fromkeys(("PR", "RS", "SC"), "Sul")}
SEM_EQUIPE = "Sem equipe"


class SemBanco(RuntimeError):
    pass


_CACHE: dict = {}
TTL_S = 300


def _ler(chave, calcular) -> leitura.Leitura:
    """Cópia de 5 min; leitura com erro não fica guardada e a tela diz qual fonte falhou."""
    g = _CACHE.get(chave)
    if g and time.time() - g.lido_em < TTL_S:
        return g
    try:
        r = leitura.Leitura(calcular(), time.time())
    except Exception as e:      # noqa: BLE001 — banco fora do ar: a tela avisa
        return leitura.Leitura({}, time.time(), f"Não consegui ler o banco do Nexus ({type(e).__name__})")
    _CACHE[chave] = r
    return r


def _sessao():
    s = current_app.extensions.get("nexus_dados_sessao")
    if s is None and current_app.config.get("TESTING"):
        raise SemBanco("teste sem banco")          # teste nunca vai à rede
    if s is None:
        import requests
        s = requests.Session()
    return s


def _base() -> str:
    from ..cadastro.ligacoes import BASE_API
    return (current_app.config.get("GRIDCO_DB_API") or BASE_API).rstrip("/")


def _livro(nome, aba=None) -> list[dict]:
    return livros.ler(_base(), _sessao(), nome, aba)


def _agora() -> datetime:
    return datetime.now(_BRT)


def _dt(iso) -> datetime | None:
    s = str(iso or "").strip().replace("Z", "+00:00")
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=_BRT)).astimezone(_BRT)


def _dia(iso) -> str:
    d = _dt(iso)
    return d.date().isoformat() if d else str(iso or "")[:10]


def _sim(v) -> bool:
    return str(v or "").strip().lower() in ("sim", "true", "1")


def _int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def nome_curto(nome) -> str:
    """O "Nome padrão" do cadastro (primeiro e último nome): Levi, 05/10: "tem que ter o nome resumido do técnico"."""
    s = " ".join(str(nome or "").split())
    return str(nome_padrao(s)) if " " in s else s


def _quem() -> dict:
    """{código do App: (e-mail, nome)}: o cadastro do App, na hora."""
    try:
        return livros_app.pessoas_por_codigo(current_app.config.get("NEXUS_PESSOA_HMAC"))
    except Exception:       # noqa: BLE001 — sem o cadastro do App, sai sem nome
        return {}


def _codigo(codigo) -> str:
    return str(codigo or "").split(";")[0].strip()


def _nome(quem: dict, codigo) -> str:
    """O nome resumido de quem o App mandou como código (vários e-mails: o primeiro)."""
    c = _codigo(codigo)
    return nome_curto((quem.get(c) or ("", ""))[1]) if c else ""


def _mobilizada(u: dict, hoje: str) -> bool:
    """Mobilizada = OPERAÇÃO no cadastro e com a data de mobilização já passada. Medido em 05/10: das 177 em OPERAÇÃO,
    49 não têm data de mobilização e NENHUMA delas teve ronda pelo App; as 107 com ronda têm a data (Levi: "tem usina
    que nem mobilizada está")."""
    d = str(u.get("data_mobilizacao") or "").strip()
    return (str(u.get("status") or "").strip().upper() == STATUS_OPERACAO
            and str(u.get("excluido") or "").strip().lower() != "sim"
            and bool(_DATA_ISO.match(d)) and d[:10] <= hoje)


class _Base:
    """O cadastro e o ligador, lidos uma vez por cálculo."""

    def __init__(self):
        self.usinas = _livro("cadastro_nexus", "usinas")
        self.equipes = _livro("cadastro_nexus", "equipes")
        self.lig = D.Ligador(self.usinas, _livro("cadastro_nexus", "de_para"), self.equipes, {})
        self.nome_equipe = {D._id(e.get("equipe_id")): str(e.get("nome") or "") for e in self.equipes}
        self.por_id = {D._id(u.get("usina_id")): u for u in self.usinas if D._id(u.get("usina_id"))}
        hoje = _agora().date().isoformat()
        self.mobilizadas = {uid: u for uid, u in self.por_id.items() if _mobilizada(u, hoje)}
        # em OPERAÇÃO no cadastro, mas sem data de mobilização (ou com ela no futuro): conserto é no cadastro
        self.sem_mobilizacao = sorted(str(u.get("nome") or "") for uid, u in self.por_id.items()
                                      if uid not in self.mobilizadas
                                      and str(u.get("status") or "").strip().upper() == STATUS_OPERACAO)

    def equipe_da_usina(self, uid) -> str:
        u = self.por_id.get(uid) or {}
        return self.nome_equipe.get(D._id(u.get("equipe_id")), "")

    def onde(self, uid, nome_da_fonte="") -> dict:
        """Usina (o nome do cadastro), equipe, estado, região do Brasil e cidade. Sem ligação: o nome que a fonte
        escreveu, o resto vazio."""
        u = self.por_id.get(uid) or {}
        uf = str(u.get("uf") or "").strip().upper()
        return {"usina": str(u.get("nome") or nome_da_fonte or ""), "uf": uf,
                "regiao_br": REGIAO_DA_UF.get(uf, ""), "cidade": str(u.get("cidade") or "").strip(),
                "equipe": (self.equipe_da_usina(uid) or SEM_EQUIPE) if u else ""}


# ── Rondas ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _rondas_ligadas(b: _Base) -> list[dict]:
    out = []
    for r in _livro("rondas_app_campo"):
        uid, _como = b.lig.usina(r.get("Usina"), r.get("Ativo da usina no Fracttal"))
        sit = str(r.get("Situação da OS") or "")
        out.append({"data": str(r.get("Data") or "")[:10], "os": r.get("OS"), "usina_id": uid,
                    **b.onde(uid, r.get("Usina")), "regiao": r.get("Região") or "",
                    "tecnico": nome_curto(r.get("Técnico")), "tipo": r.get("Tipo") or "",
                    "nota": _int(r.get("Nota da ronda")), "falhas": str(r.get("Falhas") or "").strip(),
                    "trk_apontados": _int(r.get("Trackers apontados")) or 0,
                    "trk_respondidos": _int(r.get("Trackers respondidos")) or 0, "situacao_os": sit,
                    "sem_os": sit.lower().startswith("não criada") or not r.get("OS"),
                    "mobilizada": uid in b.mobilizadas, "inicio": r.get("Início"), "fim": r.get("Fim")})
    return out


def _cobertura(b: _Base, rondas: list[dict], hoje) -> list[dict]:
    """Uma linha por usina MOBILIZADA: a última ronda e há quantos dias. Nunca teve ronda = 999."""
    ultima = {}
    for r in rondas:
        if r["usina_id"] and (r["usina_id"] not in ultima or r["data"] > ultima[r["usina_id"]]["data"]):
            ultima[r["usina_id"]] = r
    out = []
    for uid in b.mobilizadas:
        r = ultima.get(uid)
        dias = (hoje - datetime.fromisoformat(r["data"]).date()).days if r else 999
        out.append({"usina_id": uid, **b.onde(uid), "ultima": r["data"] if r else None, "dias": dias, "tecnico": r["tecnico"] if r else "",
                    "tipo": r["tipo"] if r else "", "falhas": r["falhas"] if r else "", "os": r["os"] if r else None})
    out.sort(key=lambda x: (-x["dias"], x["usina"]))
    return out


def rondas(dias: int = DIAS_COBERTURA) -> leitura.Leitura:
    def calcular():
        b = _Base()
        hoje = _agora().date()
        todas = [r for r in _rondas_ligadas(b) if r["mobilizada"]]
        piso = (hoje - timedelta(days=dias - 1)).isoformat()
        periodo = sorted((r for r in todas if r["data"] >= piso), key=lambda r: (r["data"], r["fim"] or ""), reverse=True)
        cob = _cobertura(b, todas, hoje)
        notas = [r["nota"] for r in periodo if r["nota"] is not None]
        return {"periodo": periodo, "cobertura": cob, "sem_mobilizacao": b.sem_mobilizacao,
                "resumo": {"rondas": len(periodo), "nota_media": round(statistics.mean(notas)) if notas else None,
                           "com_falha": sum(1 for r in periodo if r["falhas"]),
                           "sem_os": sum(1 for r in periodo if r["sem_os"]),
                           "usinas": len(cob), "cobertas": sum(1 for c in cob if c["dias"] < dias),
                           "sem_ronda_alerta": sum(1 for c in cob if c["dias"] >= DIAS_SEM_RONDA_ALERTA)}}
    return _ler(("visao_rondas", dias), calcular)


# ── Permissões de trabalho ───────────────────────────────────────────────────────────────────────────────────────
def pts() -> leitura.Leitura:
    """Todas as PT do livro do App. A PT NÃO passa pelo filtro de usina mobilizada: PT esperando decisão sempre aparece
    (esconder deixaria o técnico parado no campo)."""
    def calcular():
        b = _Base()
        quem = _quem()
        agora = _agora()
        out = []
        for r in _livro("pt_app_campo"):
            criada, decidida = _dt(r.get("Criada em")), _dt(r.get("Decidida em"))
            sit = str(r.get("Situação") or "").strip() or "aguardando"
            uid, _como = b.lig.usina(r.get("Usina"), r.get("Código do ativo"))
            out.append({"numero": str(r.get("Número") or ""), "os": r.get("OS"), "tarefa": r.get("Tarefa") or "",
                        "usina_id": uid, **b.onde(uid, r.get("Usina")), "ativo": r.get("Ativo") or "",
                        "codigo": r.get("Código do ativo") or "",
                        "solicitante": _nome(quem, r.get("Solicitante (HMAC)")), "situacao": sit,
                        "criada": criada, "decidida": decidida, "decidida_por": _nome(quem, r.get("Decidida por (HMAC)")),
                        "papel": r.get("Papel de quem decidiu") or "", "motivo": r.get("Motivo") or "",
                        "efeito": r.get("Efeito") or "",
                        "respostas_nao": _int(r.get("Respostas NÃO")) or 0, "faltam": r.get("Faltam") or "",
                        "atividades": [a.strip() for a in str(r.get("Atividades") or "").split(";") if a.strip()],
                        "forcada": _sim(r.get("Forçada")),
                        "espera_min": int((decidida - criada).total_seconds() // 60) if criada and decidida else None,
                        "idade_min": int((agora - criada).total_seconds() // 60) if criada and sit == "aguardando" else None})
        for p in out:
            p["parada"] = (p["idade_min"] or 0) > PT_PARADA_MIN
        aguardando = sorted((p for p in out if p["situacao"] == "aguardando"), key=lambda p: p["criada"] or agora)
        historico = sorted((p for p in out if p["situacao"] != "aguardando"), key=lambda p: p["criada"] or agora,
                           reverse=True)
        esperas = [p["espera_min"] for p in historico if p["espera_min"] is not None]
        situacoes = {}
        for p in out:
            situacoes[p["situacao"]] = situacoes.get(p["situacao"], 0) + 1
        return {"aguardando": aguardando, "historico": historico, "situacoes": situacoes,
                "resumo": {"aguardando": len(aguardando),
                           "mais_antiga_min": aguardando[0]["idade_min"] if aguardando else None,
                           "paradas": sum(1 for p in aguardando if p["parada"]),
                           "espera_mediana_min": round(statistics.median(esperas)) if esperas else None,
                           "com_nao": sum(1 for p in out if p["respostas_nao"])}}
    return _ler(("visao_pt",), calcular)


def pt(numero) -> dict | None:
    """Uma PT pelo número, do livro do App (a cópia de 5 min)."""
    d = pts().dados
    n = str(numero or "").strip()
    return next((p for p in (d.get("aguardando") or []) + (d.get("historico") or []) if p["numero"] == n), None)


# ── Zeladoria ────────────────────────────────────────────────────────────────────────────────────────────────────
def zeladoria() -> leitura.Leitura:
    def calcular():
        quem = _quem()
        hoje = _agora().date().isoformat()
        servicos = {}
        for r in _livro("zeladoria_app_campo"):
            os_ = str(r.get("OS") or "")
            s = servicos.setdefault(os_, {"os": os_, "usina": r.get("Usina") or "", "servico": r.get("Serviço") or "",
                                          "prestador": r.get("Prestador") or "", "etapas": [], "fechada": False,
                                          "motivo": ""})
            s["etapas"].append({"data": str(r.get("Data") or "")[:10], "etapa": r.get("Etapa") or "",
                                "quem": _nome(quem, r.get("Registrado por (HMAC)")), "fotos": _int(r.get("Fotos")) or 0,
                                "nao": _int(r.get("Respostas NÃO")) or 0, "assinada": _sim(r.get("Assinada"))})
            s["fechada"] = s["fechada"] or _sim(r.get("OS fechada"))
            s["motivo"] = s["motivo"] or (r.get("Motivo do fechamento") or "")
        lista = []
        for s in servicos.values():
            s["etapas"].sort(key=lambda e: e["data"])
            feitas = {str(e["etapa"]).lower() for e in s["etapas"]}
            s["ultima"] = s["etapas"][-1]["data"] if s["etapas"] else None
            s["diaria_hoje"] = any(e["data"] == hoje and "diar" in str(e["etapa"]).lower() for e in s["etapas"])
            s["epi"] = any("epi" in f for f in feitas)
            s["com_nao"] = sum(e["nao"] for e in s["etapas"])
            lista.append(s)
        lista.sort(key=lambda s: (s["fechada"], s["ultima"] or ""))
        abertas = [s for s in lista if not s["fechada"]]
        return {"servicos": lista, "resumo": {"servicos": len(lista), "abertos": len(abertas),
                                              "sem_diaria_hoje": sum(1 for s in abertas if not s["diaria_hoje"]),
                                              "sem_epi": sum(1 for s in abertas if not s["epi"])}}
    return _ler(("visao_zeladoria",), calcular)


# ── Ranking ──────────────────────────────────────────────────────────────────────────────────────────────────────
def ranking(dias: int = 30) -> leitura.Leitura:
    """Regiões: 60% a nota média dos fechamentos + 40% a cobertura de ronda (usinas mobilizadas da equipe com ronda nos
    últimos 14 dias), a régua do painel do App. Colaboradores: nota média, fechamentos, pontualidade e devolvidas no
    período, somados pelo código da pessoa (dois técnicos com o mesmo nome resumido não se misturam)."""
    def calcular():
        b = _Base()
        quem = _quem()
        agora = _agora()
        piso = agora - timedelta(days=dias)
        fech = [r for r in _livro("fechamentos_app_campo") if (_dt(r.get("Registrado em")) or agora) >= piso]
        cob = _cobertura(b, [r for r in _rondas_ligadas(b) if r["mobilizada"]], agora.date())

        def agrega(chave, nome=lambda k: k):
            g = {}
            for r in fech:
                k = chave(r)
                if not k:
                    continue
                a = g.setdefault(k, {"nome": nome(k), "os": 0, "notas": [], "pontuais": 0, "devolvidas": 0})
                a["os"] += 1
                if _int(r.get("Nota do painel")) is not None:
                    a["notas"].append(_int(r.get("Nota do painel")))
                a["pontuais"] += _sim(r.get("Pontual"))
                a["devolvidas"] += _sim(r.get("Devolvida"))
            for a in g.values():
                a["nota"] = round(statistics.mean(a["notas"])) if a["notas"] else None
                a["pontual_pct"] = round(100 * a["pontuais"] / a["os"]) if a["os"] else None
                a["devolvidas_pct"] = round(100 * a["devolvidas"] / a["os"]) if a["os"] else None
                del a["notas"]
            return g

        regioes = agrega(lambda r: str(r.get("Região") or "").strip())
        do_cadastro = {n for n in b.nome_equipe.values() if n}
        fora = sorted(({"nome": k, "os": a["os"]} for k, a in regioes.items() if k not in do_cadastro),
                      key=lambda a: -a["os"])
        regioes = {k: a for k, a in regioes.items() if k in do_cadastro}
        por_equipe = {}
        for c in cob:
            if c["equipe"]:
                e = por_equipe.setdefault(c["equipe"], {"usinas": 0, "cobertas": 0})
                e["usinas"] += 1
                e["cobertas"] += c["dias"] < DIAS_COBERTURA
        for nome, e in por_equipe.items():
            a = regioes.setdefault(nome, {"nome": nome, "os": 0, "pontuais": 0, "devolvidas": 0, "nota": None,
                                          "pontual_pct": None, "devolvidas_pct": None})
            a.update(usinas=e["usinas"], cobertas=e["cobertas"])
        for a in regioes.values():
            a.setdefault("usinas", 0)
            a.setdefault("cobertas", 0)
            a["cobertura_pct"] = round(100 * a["cobertas"] / a["usinas"]) if a["usinas"] else None
            # só pontua quem tem as duas partes: região sem fechamento no período (ou sem usina mobilizada) não pode
            # ganhar 100 só pela outra metade
            a["pontos"] = (round(PESO_QUALIDADE * a["nota"] + PESO_COBERTURA * a["cobertura_pct"])
                           if a["nota"] is not None and a["cobertura_pct"] is not None else None)
        colab = {k: a for k, a in agrega(lambda r: _codigo(r.get("Técnico (HMAC)")),
                                         lambda k: _nome(quem, k)).items() if a["nome"]}
        ordem = lambda a: (-(a["pontos"] if a.get("pontos") is not None else -1), a["nome"])
        return {"regioes": sorted(regioes.values(), key=ordem), "fora_do_cadastro": fora,
                "colaboradores": sorted(colab.values(), key=lambda a: (-(a["nota"] or 0), -a["os"], a["nome"])),
                "resumo": {"fechamentos": len(fech), "sem_nome": sum(1 for r in fech if not _nome(quem, r.get("Técnico (HMAC)")))}}
    return _ler(("visao_ranking", dias), calcular)


# ── Central de atenção ───────────────────────────────────────────────────────────────────────────────────────────
# Três visões (Levi, 05/10/2026): "separar Rondas feitas (histórico de rondas) e rondas pendentes, dando bastante
# atenção nas pendentes" e "separe o que é ronda e o que é Permissão de Trabalho".
PENDENTE = {"nunca": ("Nunca teve ronda", "critico"), "sem_ronda": ("Sem ronda", "critico"),
            "longa_pendente": ("Ronda longa pendente", "alerta")}
FEITA = {"sem_os": ("Sem OS no Fracttal", "alerta"), "incompleta": ("Evidência incompleta", "info"),
         "ok": ("Sem pendência", "ok")}
PT_STATUS = {"parada": ("Parada há mais de 2 h", "critico"), "aguardando": ("Aguardando", "alerta")}
LONGA_PENDENTE = "ronda longa pendente"


def _dm(iso) -> str:
    s = str(iso or "")
    return f"{s[8:10]}/{s[5:7]}" if len(s) >= 10 else ""


def atencao(dias: int = 14) -> leitura.Leitura:
    """O que pede ação no campo, em três visões. Só usina MOBILIZADA (a PT é a exceção, ver `pts`).
    - Rondas pendentes: uma linha por usina que pede ronda: sem ronda há 7 dias ou mais (ou nunca) ou com a ronda longa
      pendente pela última ronda dela (o App repete o aviso em toda ronda curta: uma linha só por usina).
    - Rondas feitas: o histórico do período, com o que ficou faltando: OS que o Fracttal não criou, evidência
      incompleta (foto, registro de ação, checklist).
    - Permissões de trabalho: as PT esperando o De acordo, da mais antiga para a mais nova.
    Nota baixa de fechamento NÃO entra: é a fila da Aprovação de OS."""
    def calcular():
        b = _Base()
        hoje = _agora().date()
        piso = (hoje - timedelta(days=dias - 1)).isoformat()
        rond = [r for r in _rondas_ligadas(b) if r["mobilizada"]]
        pendentes = []
        for c in _cobertura(b, rond, hoje):
            longa = LONGA_PENDENTE in c["falhas"].lower()
            if c["dias"] >= 999:
                tipo, obs = "nunca", "Nenhuma ronda pelo App desde que a usina foi mobilizada"
            elif c["dias"] >= DIAS_SEM_RONDA_ALERTA:
                tipo, obs = "sem_ronda", f"Última ronda em {_dm(c['ultima'])}" + (
                    "; a ronda longa também está pendente" if longa else "")
            elif longa:
                tipo, obs = "longa_pendente", f"O App pede a ronda longa (última ronda em {_dm(c['ultima'])})"
            else:
                continue
            pendentes.append({"tipo": tipo, "usina": c["usina"], "uf": c["uf"], "cidade": c["cidade"],
                              "equipe": c["equipe"], "regiao_br": c["regiao_br"],
                              "dias": c["dias"], "ultima": c["ultima"], "obs": obs})
        usinas = [{k: c[k] for k in ("usina", "equipe", "uf", "regiao_br", "cidade", "dias")}
                  for c in _cobertura(b, rond, hoje)]
        feitas = []
        for r in sorted((r for r in rond if r["data"] >= piso), key=lambda r: (r["data"], r["fim"] or ""), reverse=True):
            faltas = [f.strip() for f in r["falhas"].split(";") if f.strip() and f.strip().lower() != LONGA_PENDENTE]
            status = "sem_os" if r["sem_os"] else ("incompleta" if faltas else "ok")
            obs = "; ".join(([r["situacao_os"] or "OS não criada"] if r["sem_os"] else []) + faltas)
            feitas.append({"data": r["data"], "status": status, "usina": r["usina"], "uf": r["uf"], "cidade": r["cidade"],
                           "equipe": r["equipe"], "regiao_br": r["regiao_br"], "obs": obs, "feito_por": r["tecnico"], "os": None if r["sem_os"] else r["os"],
                           "nota": r["nota"], "tipo": r["tipo"]})
        p = pts()
        if p.erro:
            raise SemBanco(p.erro)
        return {"pendentes": pendentes, "feitas": feitas, "pts": p.dados.get("aguardando") or [], "usinas": usinas,
                "sem_mobilizacao": b.sem_mobilizacao}
    return _ler(("visao_atencao", dias), calcular)


def por_equipe(usinas, pendentes, feitas, pts) -> list[dict]:
    """Um cartão por equipe (Levi, 05/10: "agrupamento por cards das equipes, usinas pendentes de ronda e % de rondas
    feitas da equipe"). Feitas = usinas mobilizadas da equipe que NÃO estão pendentes (ronda nos últimos 7 dias e sem a
    longa pendente); % feitas = feitas ÷ usinas. Junto: as rondas do período e as PT esperando. As listas chegam já
    filtradas pela tela (região, busca), então o cartão conta o mesmo que a tabela."""
    eq = {}

    def card(nome):
        return eq.setdefault(nome or SEM_EQUIPE, {"equipe": nome or SEM_EQUIPE, "regioes": set(), "ufs": set(),
                                                  "usinas": 0, "pendentes": 0, "nunca": 0, "sem_ronda": 0,
                                                  "longa_pendente": 0, "rondas": 0, "ok": 0, "sem_os": 0,
                                                  "incompleta": 0, "pts": 0, "parada": 0})
    for u in usinas:
        c = card(u["equipe"])
        c["usinas"] += 1
        c["ufs"].update([u["uf"]] if u["uf"] else [])
        c["regioes"].update([u["regiao_br"]] if u["regiao_br"] else [])
    for x in pendentes:
        c = card(x["equipe"])
        c["pendentes"] += 1
        c[x["tipo"]] += 1
    for x in feitas:
        c = card(x["equipe"])
        c["rondas"] += 1
        c[x["status"]] += 1
    for x in pts:
        c = card(x.get("equipe"))
        c["pts"] += 1
        c["parada"] += bool(x.get("parada"))
        c["ufs"].update([x["uf"]] if x.get("uf") else [])
        c["regioes"].update([x["regiao_br"]] if x.get("regiao_br") else [])
    for c in eq.values():
        c["feitas"] = max(0, c["usinas"] - c["pendentes"])
        c["pct_feitas"] = round(100 * c["feitas"] / c["usinas"]) if c["usinas"] else None
        c["regioes"], c["ufs"] = sorted(c["regioes"]), sorted(c["ufs"])
    return list(eq.values())


def limpar():
    _CACHE.clear()
