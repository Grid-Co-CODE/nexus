"""A visão do Nexus para o Campo · App: as telas que antes abriam o painel do App (no Azure) numa moldura, agora com dado
nosso (Levi, 05/10/2026: "quero parar de referenciar o Azure e ter uma visão nossa!").

Tudo vem do banco (API db_performace), nunca do App nem do Azure:
- os livros que o próprio App grava de hora em hora (aos :25): `fechamentos_app_campo`, `pt_app_campo`,
  `zeladoria_app_campo`, `decisoes_app_campo` e `rondas_app_campo`;
- o cadastro do Nexus (`cadastro_nexus`): as usinas em OPERAÇÃO e a equipe de cada uma são a base da cobertura de
  ronda e do ranking por região. A usina que o App escreve liga ao `usina_id` pelo mesmo `Ligador` da camada de dados
  (de-para do Fracttal; código do ativo de reserva).
A pessoa vem do App como código do e-mail (HMAC): o nome sai do cadastro do App (`identidades.json`), na hora. Nada
volta ao banco. Cópia de 5 min por tela (`leitura.py`); banco fora do ar = a tela avisa, não some.

As contas são NOSSAS e estão escritas em cada função: quem quiser saber por que um número deu tanto lê aqui.
"""
import statistics
import time
from datetime import datetime, timedelta, timezone

from flask import current_app

from ..dados import fatos as D
from ..dados import livros
from . import leitura, livros_app

_BRT = timezone(timedelta(hours=-3))
STATUS_OPERACAO = "OPERAÇÃO"
DIAS_SEM_RONDA_ALERTA = 7        # usina em operação sem ronda há 7 dias ou mais = ponto de atenção
DIAS_COBERTURA = 14              # janela da cobertura de ronda (a mesma do ranking por região)
PT_PARADA_MIN = 120              # PT esperando o De acordo há mais de 2 h = ponto de atenção
PESO_QUALIDADE, PESO_COBERTURA = 0.6, 0.4     # ranking por região, a mesma régua do painel do App


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


def _quem() -> dict:
    """{código do App: (e-mail, nome)}: o cadastro do App, na hora."""
    try:
        return livros_app.pessoas_por_codigo(current_app.config.get("NEXUS_PESSOA_HMAC"))
    except Exception:       # noqa: BLE001 — sem o cadastro do App, sai sem nome
        return {}


def _nome(quem: dict, codigo) -> str:
    primeiro = str(codigo or "").split(";")[0].strip()
    return (quem.get(primeiro) or ("", ""))[1] if primeiro else ""


class _Base:
    """O cadastro e o ligador, lidos uma vez por cálculo."""

    def __init__(self):
        self.usinas = _livro("cadastro_nexus", "usinas")
        self.equipes = _livro("cadastro_nexus", "equipes")
        self.lig = D.Ligador(self.usinas, _livro("cadastro_nexus", "de_para"), self.equipes, {})
        self.nome_equipe = {D._id(e.get("equipe_id")): str(e.get("nome") or "") for e in self.equipes}
        self.em_operacao = {D._id(u.get("usina_id")): u for u in self.usinas
                            if str(u.get("status") or "").strip().upper() == STATUS_OPERACAO
                            and str(u.get("excluido") or "").strip().lower() != "sim" and D._id(u.get("usina_id"))}

    def equipe_da_usina(self, uid) -> str:
        u = self.em_operacao.get(uid) or {}
        return self.nome_equipe.get(D._id(u.get("equipe_id")), "")


# ── Rondas ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _rondas_ligadas(b: _Base) -> list[dict]:
    out = []
    for r in _livro("rondas_app_campo"):
        uid, _como = b.lig.usina(r.get("Usina"), r.get("Ativo da usina no Fracttal"))
        sit = str(r.get("Situação da OS") or "")
        out.append({"data": str(r.get("Data") or "")[:10], "os": r.get("OS"), "usina": r.get("Usina") or "",
                    "usina_id": uid, "regiao": r.get("Região") or "", "tecnico": r.get("Técnico") or "",
                    "tipo": r.get("Tipo") or "", "nota": _int(r.get("Nota da ronda")),
                    "falhas": str(r.get("Falhas") or "").strip(), "trk_apontados": _int(r.get("Trackers apontados")) or 0,
                    "trk_respondidos": _int(r.get("Trackers respondidos")) or 0, "situacao_os": sit,
                    "sem_os": sit.lower().startswith("não criada") or not r.get("OS"),
                    "inicio": r.get("Início"), "fim": r.get("Fim")})
    return out


def _cobertura(b: _Base, rondas: list[dict], hoje) -> list[dict]:
    """Uma linha por usina em OPERAÇÃO: a última ronda e há quantos dias. Nunca teve ronda = 999."""
    ultima = {}
    for r in rondas:
        if r["usina_id"] and (r["usina_id"] not in ultima or r["data"] > ultima[r["usina_id"]]["data"]):
            ultima[r["usina_id"]] = r
    out = []
    for uid, u in b.em_operacao.items():
        r = ultima.get(uid)
        dias = (hoje - datetime.fromisoformat(r["data"]).date()).days if r else 999
        out.append({"usina_id": uid, "usina": u.get("nome") or "", "equipe": b.equipe_da_usina(uid),
                    "ultima": r["data"] if r else None, "dias": dias, "tecnico": r["tecnico"] if r else "",
                    "tipo": r["tipo"] if r else ""})
    out.sort(key=lambda x: (-x["dias"], x["usina"]))
    return out


def rondas(dias: int = DIAS_COBERTURA) -> leitura.Leitura:
    def calcular():
        b = _Base()
        hoje = _agora().date()
        todas = _rondas_ligadas(b)
        piso = (hoje - timedelta(days=dias - 1)).isoformat()
        periodo = sorted((r for r in todas if r["data"] >= piso), key=lambda r: (r["data"], r["fim"] or ""), reverse=True)
        cob = _cobertura(b, todas, hoje)
        notas = [r["nota"] for r in periodo if r["nota"] is not None]
        return {"periodo": periodo, "cobertura": cob,
                "resumo": {"rondas": len(periodo), "nota_media": round(statistics.mean(notas)) if notas else None,
                           "com_falha": sum(1 for r in periodo if r["falhas"]),
                           "sem_os": sum(1 for r in periodo if r["sem_os"]),
                           "usinas": len(cob), "cobertas": sum(1 for c in cob if c["dias"] < dias),
                           "sem_ronda_alerta": sum(1 for c in cob if c["dias"] >= DIAS_SEM_RONDA_ALERTA),
                           "nao_ligadas": sum(1 for r in periodo if not r["usina_id"])}}
    return _ler(("visao_rondas", dias), calcular)


# ── Permissões de trabalho ───────────────────────────────────────────────────────────────────────────────────────
def pts() -> leitura.Leitura:
    def calcular():
        quem = _quem()
        agora = _agora()
        out = []
        for r in _livro("pt_app_campo"):
            criada, decidida = _dt(r.get("Criada em")), _dt(r.get("Decidida em"))
            sit = str(r.get("Situação") or "").strip() or "aguardando"
            out.append({"numero": r.get("Número"), "os": r.get("OS"), "tarefa": r.get("Tarefa") or "",
                        "usina": r.get("Usina") or "", "regiao": r.get("Região") or "", "ativo": r.get("Ativo") or "",
                        "solicitante": _nome(quem, r.get("Solicitante (HMAC)")), "situacao": sit,
                        "criada": criada, "decidida": decidida, "decidida_por": _nome(quem, r.get("Decidida por (HMAC)")),
                        "papel": r.get("Papel de quem decidiu") or "", "motivo": r.get("Motivo") or "",
                        "respostas_nao": _int(r.get("Respostas NÃO")) or 0, "faltam": r.get("Faltam") or "",
                        "atividades": r.get("Atividades") or "", "forcada": _sim(r.get("Forçada")),
                        "espera_min": int((decidida - criada).total_seconds() // 60) if criada and decidida else None,
                        "idade_min": int((agora - criada).total_seconds() // 60) if criada and sit == "aguardando" else None})
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
                           "paradas": sum(1 for p in aguardando if (p["idade_min"] or 0) > PT_PARADA_MIN),
                           "espera_mediana_min": round(statistics.median(esperas)) if esperas else None,
                           "com_nao": sum(1 for p in out if p["respostas_nao"])}}
    return _ler(("visao_pt",), calcular)


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
    """Regiões: 60% a nota média dos fechamentos + 40% a cobertura de ronda (usinas da equipe com ronda nos últimos 14
    dias), a régua do painel do App. Colaboradores: nota média, fechamentos, pontualidade e devolvidas no período."""
    def calcular():
        b = _Base()
        quem = _quem()
        agora = _agora()
        piso = agora - timedelta(days=dias)
        fech = [r for r in _livro("fechamentos_app_campo") if (_dt(r.get("Registrado em")) or agora) >= piso]
        cob = _cobertura(b, _rondas_ligadas(b), agora.date())

        def agrega(chave):
            g = {}
            for r in fech:
                k = chave(r)
                if not k:
                    continue
                a = g.setdefault(k, {"nome": k, "os": 0, "notas": [], "pontuais": 0, "devolvidas": 0})
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
            # só pontua quem tem as duas partes: região sem fechamento no período (ou sem usina em operação) não
            # pode ganhar 100 só pela outra metade
            a["pontos"] = (round(PESO_QUALIDADE * a["nota"] + PESO_COBERTURA * a["cobertura_pct"])
                           if a["nota"] is not None and a["cobertura_pct"] is not None else None)
        colab = agrega(lambda r: _nome(quem, r.get("Técnico (HMAC)")))
        ordem = lambda a: (-(a["pontos"] if a.get("pontos") is not None else -1), a["nome"])
        return {"regioes": sorted(regioes.values(), key=ordem), "fora_do_cadastro": fora,
                "colaboradores": sorted(colab.values(), key=lambda a: (-(a["nota"] or 0), -a["os"], a["nome"])),
                "resumo": {"fechamentos": len(fech), "sem_nome": sum(1 for r in fech if not _nome(quem, r.get("Técnico (HMAC)")))}}
    return _ler(("visao_ranking", dias), calcular)


# ── Central de atenção ───────────────────────────────────────────────────────────────────────────────────────────
TIPOS_ATENCAO = {
    "sem_ronda": ("Usina sem ronda", "critico"),
    "pt_parada": ("PT esperando o De acordo", "alerta"),
    "ronda_sem_os": ("Ronda sem OS no Fracttal", "alerta"),
    "longa_pendente": ("Ronda longa pendente", "alerta"),
    "ronda_incompleta": ("Ronda com evidência incompleta", "info"),
}
LONGA_PENDENTE = "ronda longa pendente"


def atencao(dias: int = 14) -> leitura.Leitura:
    """O que pede ação, juntando as fontes: usina em operação sem ronda há 7 dias ou mais; PT esperando o De acordo há
    mais de 2 h; ronda cuja OS o Fracttal não criou; ronda longa pendente (uma vez por usina, pela última ronda dela: o
    App repete o aviso em toda ronda curta); ronda com evidência incompleta (foto, registro de ação, checklist). Nota
    baixa de fechamento NÃO entra: é a fila da Aprovação de OS (e o fechamento aprovado direto no Fracttal nunca tem
    decisão no painel, o que encheria esta lista de ponto falso). Os tratamentos da Central do App ficam ao lado."""
    def calcular():
        b = _Base()
        quem = _quem()
        agora = _agora()
        hoje = agora.date()
        piso = (hoje - timedelta(days=dias - 1)).isoformat()
        pontos = []
        rond = _rondas_ligadas(b)
        for c in _cobertura(b, rond, hoje):
            if c["dias"] >= DIAS_SEM_RONDA_ALERTA:
                pontos.append({"tipo": "sem_ronda", "usina": c["usina"], "regiao": c["equipe"], "dias": c["dias"],
                               "oque": "nunca teve ronda pelo App" if c["dias"] >= 999 else f"última ronda {c['ultima']}",
                               "quem": c["tecnico"], "os": None, "quando": c["ultima"]})
        for p in pts().dados.get("aguardando") or []:
            if (p["idade_min"] or 0) > PT_PARADA_MIN:
                pontos.append({"tipo": "pt_parada", "usina": p["usina"], "regiao": p["regiao"],
                               "dias": (p["idade_min"] or 0) // 1440, "oque": f"PT {p['numero']} · {p['tarefa'][:60]}",
                               "quem": p["solicitante"], "os": p["os"],
                               "quando": p["criada"].date().isoformat() if p["criada"] else None})
        ultima_da_usina = {}
        for r in rond:
            if r["data"] < piso:
                continue
            idade = (hoje - datetime.fromisoformat(r["data"]).date()).days
            chave = r["usina_id"] or r["usina"]
            if chave not in ultima_da_usina or r["data"] > ultima_da_usina[chave]["data"]:
                ultima_da_usina[chave] = r
            if r["sem_os"]:
                pontos.append({"tipo": "ronda_sem_os", "usina": r["usina"], "regiao": r["regiao"], "dias": idade,
                               "oque": r["situacao_os"] or "OS não criada", "quem": r["tecnico"], "os": r["os"],
                               "quando": r["data"]})
            faltas = [f.strip() for f in r["falhas"].split(";") if f.strip() and f.strip().lower() != LONGA_PENDENTE]
            if faltas:
                pontos.append({"tipo": "ronda_incompleta", "usina": r["usina"], "regiao": r["regiao"], "dias": idade,
                               "oque": "; ".join(faltas), "quem": r["tecnico"], "os": r["os"], "quando": r["data"]})
        for r in ultima_da_usina.values():
            if LONGA_PENDENTE in r["falhas"].lower():
                pontos.append({"tipo": "longa_pendente", "usina": r["usina"], "regiao": r["regiao"],
                               "dias": (hoje - datetime.fromisoformat(r["data"]).date()).days,
                               "oque": "o App pede a ronda longa desta usina", "quem": r["tecnico"], "os": r["os"],
                               "quando": r["data"]})
        pontos.sort(key=lambda p: (-int(p["dias"] or 0), p["tipo"], p["usina"]))
        tratados = [{"quando": _dia(d.get("Quando")), "os": d.get("OS"), "acao": d.get("Ação") or "",
                     "texto": d.get("Texto") or "", "tipo": d.get("Tipo do ponto") or "", "usina": d.get("Usina") or "",
                     "prazo": d.get("Prazo") or "", "por": _nome(quem, d.get("Decidido por (HMAC)"))}
                    for d in _livro("decisoes_app_campo") if str(d.get("Origem") or "") == "Central de atenção"]
        por_tipo = {}
        for p in pontos:
            por_tipo[p["tipo"]] = por_tipo.get(p["tipo"], 0) + 1
        return {"pontos": pontos, "por_tipo": por_tipo, "tratados": sorted(tratados, key=lambda t: t["quando"],
                                                                           reverse=True)}
    return _ler(("visao_atencao", dias), calcular)


def limpar():
    _CACHE.clear()
