"""A visão da tela Técnicos por usina (17/10/2026): o cadastro do banco, quem o PCM pôs em cada usina
(`atribuicoes.py`), o que aconteceu em campo e, quando o App publicar a foto dele, o que o App usa hoje.

Tudo vem do banco (regra 12 do `nexus/dados/CLAUDE.md`: as duas máquinas leem igual), pelo mesmo leitor das telas do
Campo (`campo.visao._Base` e `_livro`, guardados por 2 minutos):
- as usinas, as equipes, as regiões de campo, as pessoas e o `de_para` do `cadastro_nexus`. O nome da usina no Fracttal
  (sistema "Fracttal · Classificação 1") é por onde o App acha a usina; o e-mail da ficha vira o código HMAC por onde o
  App acha a pessoa (`ligacao_cadastro.codigo_da_pessoa`). Sem a chave do cadastro, nomes pelo número e sem código;
- a evidência ao lado de cada usina, para o PCM decidir (não grava nada sozinha): quem rondou (`fato_ronda`) e quem
  fechou tarefa (`fato_fechamento`) ali nos últimos 30 dias, quem é técnico na programação da semana
  (`fato_programacao.pessoa_id_tecnico`) e o técnico do cadastro (`tecnico_om_id`);
- a foto do App (`organizacao_app_campo · Atribuicoes`, o passo A1 do pacote do App): o que só o App tem, o que só o
  Nexus tem e as pendências para a troca (pessoa do App sem ficha que case, usina sem `de_para`).

Os filtros (Levi, 17/10/2026, "desenvolva" sobre a proposta): equipe, região de campo, responsável, situação (sem
técnico, com aviso) e busca, em cascata como as outras telas do PCM: cada um lista o que existe com os OUTROS aplicados,
e a opção escolhida fica na lista mesmo sem resultado.
"""
import collections
import json
from datetime import date, datetime, timedelta

from ..campo import visao
from ..campo.ligacao_cadastro import SISTEMA_FRACTTAL, _norm, codigo_da_pessoa, mapas_de
from ..dados import fatos as D
from . import atribuicoes as A
from .motivos import norm

FILTROS = ("equipe", "regiao", "responsavel", "situacao", "q")
SITUACOES = (("sem_tecnico", "Sem técnico"), ("com_aviso", "Com aviso"))
EVIDENCIA_DIAS = 30
SEM_EQUIPE, SEM_REGIAO, SEM_RESPONSAVEL = "Sem equipe", "Sem região", "Sem responsável"
APP_LIVRO, APP_ABA = "organizacao_app_campo", "Atribuicoes"


class SemCadastro(Exception):
    """O cadastro do banco não foi lido (a API fora do ar, ou o teste sem banco): a tela abre com o aviso e nada grava."""

    def __str__(self):
        return f"Não consegui ler o cadastro no banco ({self.args[0] if self.args else 'erro'}): nada foi gravado."


def ler_base():
    """O cadastro do banco (`campo.visao._Base`), ou SemCadastro com o tipo do erro."""
    try:
        return visao._Base()
    except Exception as ex:      # noqa: BLE001 — qualquer falha de leitura vira o aviso da tela
        raise SemCadastro(type(ex).__name__) from ex


def _dia(d: int) -> date:
    return datetime.strptime(str(d), "%Y%m%d").date()


def _id_dia(d: date) -> int:
    return int(d.strftime("%Y%m%d"))


def _dm(d) -> str:
    """AAAAMMDD → dd/mm (vazio quando não há data)."""
    return _dia(d).strftime("%d/%m") if d else ""


def _iso_dia(d) -> str:
    return _dia(d).isoformat() if d else ""


def _excluida(x: dict) -> bool:
    return D._txt(x.get("excluido")).lower() == "sim"


# ── o cadastro ────────────────────────────────────────────────────────────────────────────────────────────────
def pessoas_de_campo(base, cfg) -> dict:
    """{pessoa_id: {"nome", "equipe_id", "cargo", "hmac"}} das pessoas de campo (vínculo "Colaborador de campo", não
    desligadas, não excluídas), decifradas uma vez. Sem a chave do cadastro: "Pessoa <id>" e sem código."""
    chave, chave_hmac = cfg.get("NEXUS_CHAVE_CADASTRO"), cfg.get("NEXUS_PESSOA_HMAC")
    cofre = None
    if chave:
        from ..cadastro.cifra import Cofre
        cofre = Cofre(chave)
    out = {}
    for p in base.pessoas:
        pid = D._id(p.get("pessoa_id"))
        if (not pid or D._txt(p.get("vinculo")) != visao.CAMPO or _excluida(p)
                or D._txt(p.get("status")).lower() == "desligado"):
            continue
        nome, email = "", ""
        if cofre and p.get("sensivel_cifrado"):
            try:
                s = json.loads(cofre.decifrar(p["sensivel_cifrado"], f"banco/pessoas/{pid}"))
                nome, email = visao.nome_curto(s.get("nome_padrao") or s.get("nome")), D._txt(s.get("email"))
            except Exception:    # noqa: BLE001 — cifra de outra chave: pelo número
                pass
        out[pid] = {"nome": nome or f"Pessoa {pid}", "equipe_id": D._id(p.get("equipe_id")),
                    "cargo": D._txt(p.get("cargo")), "hmac": codigo_da_pessoa(chave_hmac, email) or ""}
    return out


def _usinas(base, todas: bool = True) -> dict:
    """{usina_id: linha do cadastro} das não excluídas; sem `todas`, só as em operação."""
    return {uid: u for uid, u in base.por_id.items()
            if not _excluida(u) and (todas or D._txt(u.get("status")).upper() == visao.STATUS_OPERACAO)}


def _fracttal(base) -> dict:
    """{usina_id: [nomes no Fracttal]} pelo `de_para`, em ordem alfabética (o 1º é o que vai ao App)."""
    out: dict[int, list[str]] = {}
    for d in base.de_para:
        uid = D._id(d.get("usina_id"))
        if uid and D._txt(d.get("sistema")) == SISTEMA_FRACTTAL and D._txt(d.get("chave_externa")):
            out.setdefault(uid, []).append(" ".join(D._txt(d.get("chave_externa")).split()))
    return {k: sorted(set(v)) for k, v in out.items()}


def nome_no_fracttal(base, usina_id: int) -> str:
    """O nome da usina no Fracttal que vai ao App (o 1º do `de_para`, em ordem alfabética); vazio = sem `de_para`."""
    return (_fracttal(base).get(usina_id) or [""])[0]


def _pedido(uid, fracttal, pid, pessoas, de=None, ate=None) -> dict:
    return {"usina_id": uid, "usina_fracttal": (fracttal.get(uid) or [""])[0], "pessoa_id": pid,
            "pessoa_hmac": (pessoas.get(pid) or {}).get("hmac") or "", "na_usina": True,
            "de": _iso_dia(de), "ate": _iso_dia(ate)}


def pedidos_da_carga_inicial(base, pessoas: dict) -> list[dict]:
    """A regra da equipe, a mesma do App (o `espelhar_bd_operacoes.py`): cada pessoa de campo recebe as usinas do
    cadastro (não excluídas) com o mesmo `equipe_id`. Assim a lista nasce perto do que o campo vê hoje."""
    fr = _fracttal(base)
    out = []
    for uid, u in sorted(_usinas(base).items()):
        eid = D._id(u.get("equipe_id"))
        for pid, p in sorted(pessoas.items()):
            if eid and p["equipe_id"] == eid:
                out.append(_pedido(uid, fr, pid, pessoas))
    return out


def pedidos_da_reemissao(base, pessoas: dict, est: dict, usina_id: int, hoje: int) -> list[dict]:
    """As ligações atuais da usina (valendo e agendadas) com o nome do Fracttal e o código de hoje: o que o App lê
    mudou (a usina foi renomeada no Fracttal, o e-mail foi corrigido no cadastro) e a linha precisa ir de novo."""
    fr = _fracttal(base)
    return [_pedido(usina_id, fr, pid, pessoas, D._id(x.get("de_data_id")), D._id(x.get("ate_data_id")))
            for (uid, pid, _papel), x in sorted(A.atuais(est, hoje).items()) if uid == usina_id]


# ── a evidência de campo ──────────────────────────────────────────────────────────────────────────────────────
def _evidencia(hoje: int) -> tuple[dict, str]:
    """({usina_id: {pessoa_id: {"rondas", "fechamentos", "na_programacao"}}}, erro). Livro fora do ar = sem evidência,
    com o erro para a tela dizer."""
    corte = _id_dia(_dia(hoje) - timedelta(days=EVIDENCIA_DIAS))
    segunda = _id_dia(_dia(hoje) - timedelta(days=_dia(hoje).weekday()))
    ev: dict = collections.defaultdict(lambda: collections.defaultdict(
        lambda: {"rondas": 0, "fechamentos": 0, "na_programacao": False}))
    try:
        for aba, campo in (("fato_ronda", "rondas"), ("fato_fechamento", "fechamentos")):
            for x in visao._livro("nexus_fatos", aba):
                uid, pid, dia = D._id(x.get("usina_id")), D._id(x.get("pessoa_id")), D._id(x.get("data_id"))
                if uid and pid and dia and corte <= dia <= hoje:
                    ev[uid][pid][campo] += 1
        for x in visao._livro("nexus_programacao", "fato_programacao"):
            uid, pid = D._id(x.get("usina_id")), D._id(x.get("pessoa_id_tecnico"))
            if uid and pid and D._id(x.get("data_id_semana")) == segunda:
                ev[uid][pid]["na_programacao"] = True
    except Exception as ex:      # noqa: BLE001 — o banco fora não derruba a tela: só tira a evidência
        return {}, f"{type(ex).__name__}"
    return ev, ""


# ── a foto do App ─────────────────────────────────────────────────────────────────────────────────────────────
def _comparar_app(cfg, base, nome_usina, nome_pessoa, vale: set) -> dict:
    """{"existe", "so_no_app", "so_no_nexus", "pendencias"}: o `executa` do App contra o que vale no Nexus."""
    try:
        linhas = visao._livro(APP_LIVRO, APP_ABA)
    except Exception:            # noqa: BLE001
        linhas = []
    if not linhas:
        return {"existe": False, "so_no_app": [], "so_no_nexus": [], "pendencias": []}
    m = mapas_de(cfg, base.de_para, base.pessoas)
    pares, pend = set(), {}
    for x in linhas:
        if D._txt(x.get("Papel")).lower() != "executa":
            continue
        usina, cod = " ".join(D._txt(x.get("Usina")).split()), D._txt(x.get("Pessoa (HMAC)"))
        uid = m["usina"].get(_norm(usina))
        pid = m["hmac"].get(cod)
        if not uid:
            pend[("usina", usina)] = f"{usina}: usina do App sem o nome do Fracttal no de-para do cadastro"
        elif not pid:
            pend[("pessoa", uid, cod)] = (f"{nome_usina(uid)}: uma pessoa do App sem ficha que case (sem e-mail no "
                                          "cadastro, ou com outro e-mail)")
        else:
            pares.add((uid, pid))

    def itens(ps):
        return [{"usina_id": u, "usina": nome_usina(u), "pessoa_id": p, "nome": nome_pessoa(p)}
                for u, p in sorted(ps, key=lambda t: (norm(nome_usina(t[0])), norm(nome_pessoa(t[1]))))]
    return {"existe": True, "so_no_app": itens(pares - vale), "so_no_nexus": itens(vale - pares),
            "pendencias": [pend[k] for k in sorted(pend, key=str)]}


# ── a tela ────────────────────────────────────────────────────────────────────────────────────────────────────
def _pedido_dos_args(args) -> dict:
    return {k: " ".join(str(args.get(k) or "").split())[:80] for k in FILTROS}


def _passa(l: dict, pedido: dict, menos: str | None = None) -> bool:
    for k in ("equipe", "regiao", "responsavel"):
        if k != menos and pedido[k] and l[k] != pedido[k]:
            return False
    if menos != "situacao" and pedido["situacao"]:
        if pedido["situacao"] == "sem_tecnico" and l["tem_tecnico"]:
            return False
        if pedido["situacao"] == "com_aviso" and not l["avisos"]:
            return False
    if menos != "q" and pedido["q"] and norm(pedido["q"]) not in l["_busca"]:
        return False
    return True


def _opcoes(linhas: list[dict], pedido: dict) -> dict:
    """{filtro: [(valor, quantas)]}: cada filtro com os OUTROS aplicados; a escolha fica mesmo sem resultado."""
    out = {}
    for k in ("equipe", "regiao", "responsavel", "situacao"):
        c = collections.Counter()
        for l in linhas:
            if not _passa(l, pedido, menos=k):
                continue
            if k == "situacao":
                c["sem_tecnico"] += not l["tem_tecnico"]
                c["com_aviso"] += bool(l["avisos"])
            else:
                c[l[k]] += 1
        if pedido[k] and pedido[k] not in c:
            c[pedido[k]] = 0
        if k == "situacao":
            out[k] = [(v, c[v]) for v, _r in SITUACOES if c[v] or pedido[k] == v]
        else:
            out[k] = sorted(c.items(), key=lambda t: norm(t[0]))
    return out


def montar(cfg, args, hoje: int | None = None) -> dict:
    """O contexto da tela (`pcm/tecnicos.html`). `args`: os filtros, `ver` (usina | tecnico) e `todas` (as usinas fora
    de operação também)."""
    hoje = hoje or A.hoje_id()
    pedido, ver = _pedido_dos_args(args), ("tecnico" if args.get("ver") == "tecnico" else "usina")
    try:
        base = ler_base()
    except SemCadastro as ex:
        return {"ver": ver, "linhas": [], "tecnicos": [], "total_usinas": 0, "pedido": pedido,
                "opcoes": {k: [] for k in FILTROS if k != "q"}, "todas": str(args.get("todas") or "") == "1",
                "situacoes": dict(SITUACOES), "hoje": hoje, "pessoas_json": [],
                "app": {"existe": False, "so_no_app": [], "so_no_nexus": [], "pendencias": []}, "livro_vazio": False,
                "erro": "", "erro_cadastro": ex.args[0] if ex.args else "erro", "avisos_gerais": []}
    pessoas = pessoas_de_campo(base, cfg)
    est = A.ler(cfg)
    atuais = A.atuais(est, hoje)
    fr = _fracttal(base)
    ev, erro_ev = _evidencia(hoje)
    todas = str(args.get("todas") or "") == "1"
    usinas = _usinas(base, todas=todas)
    ids = ({pid for (_u, pid, _p) in atuais} | {pid for e in ev.values() for pid in e}
           | {D._id(u.get(c)) for u in usinas.values() for c in ("tecnico_om_id", "responsavel_om_id")})
    nomes = base.nomes({i for i in ids if i})

    def nome_pessoa(pid):
        return (pessoas.get(pid) or {}).get("nome") or nomes.get(pid) or f"Pessoa {pid}"

    def nome_usina(uid):
        return D._txt((base.por_id.get(uid) or {}).get("nome")) or f"Usina {uid}"

    por_usina: dict[int, list] = collections.defaultdict(list)
    for (uid, pid, _papel), x in atuais.items():
        por_usina[uid].append((pid, x))
    linhas = []
    for uid, u in usinas.items():
        eid = D._id(u.get("equipe_id"))
        reg = base.regiao.get(base.regiao_da_equipe.get(eid)) or {}
        resp = D._id(u.get("responsavel_om_id"))
        nomes_fr = fr.get(uid) or []
        tecnicos, avisos = [], []
        mudou_nome = mudou_codigo = False
        for pid, x in sorted(por_usina.get(uid, []), key=lambda t: norm(nome_pessoa(t[0]))):
            hm = (pessoas.get(pid) or {}).get("hmac") or ""
            tecnicos.append({"pessoa_id": pid, "nome": nome_pessoa(pid), "status": x["status"],
                             "de": _dm(D._id(x.get("de_data_id"))), "ate": _dm(D._id(x.get("ate_data_id"))),
                             "sem_email": not hm})
            mudou_nome |= bool(nomes_fr) and D._txt(x.get("usina_fracttal")) != nomes_fr[0]
            mudou_codigo |= bool(hm) and D._txt(x.get("pessoa_hmac")) != hm
        na_lista = {t["pessoa_id"] for t in tecnicos}
        do_cad = D._id(u.get("tecnico_om_id"))
        evid = {pid: dict(e) for pid, e in (ev.get(uid) or {}).items()}
        if do_cad and do_cad not in evid:
            evid[do_cad] = {"rondas": 0, "fechamentos": 0, "na_programacao": False}
        evidencia = sorted(({"pessoa_id": pid, "nome": nome_pessoa(pid), "do_cadastro": pid == do_cad, **e}
                            for pid, e in evid.items()),
                           key=lambda e: (-(e["rondas"] + e["fechamentos"]), not e["na_programacao"], norm(e["nome"])))
        tem = any(t["status"] == "vale" for t in tecnicos)
        if not tem:
            avisos.append("Sem técnico")
        if not nomes_fr:
            avisos.append("Sem nome do Fracttal: o App não acha esta usina")
        elif len(nomes_fr) > 1:
            avisos.append("Duas grafias no Fracttal: vai ao App a primeira")
        if mudou_nome:
            avisos.append("O nome no Fracttal mudou: reenviar ao App")
        if mudou_codigo:
            avisos.append("O e-mail de um técnico mudou no cadastro: reenviar ao App")
        for t in tecnicos:
            if t["sem_email"]:
                avisos.append(f"{t['nome']} sem e-mail no cadastro: o App não o reconhece")
        for e in evidencia:
            if e["pessoa_id"] not in na_lista and (e["rondas"] or e["fechamentos"]):
                avisos.append(f"{e['nome']} {'rondou' if e['rondas'] else 'fechou tarefa'} aqui e não está na lista")
        nome = nome_usina(uid)
        linhas.append({"usina_id": uid, "nome": nome, "status": D._txt(u.get("status")), "equipe_id": eid,
                       "equipe": base.nome_equipe.get(eid) or SEM_EQUIPE, "regiao": reg.get("nome") or SEM_REGIAO,
                       "responsavel": nome_pessoa(resp) if resp else SEM_RESPONSAVEL,
                       "fracttal": nomes_fr[0] if nomes_fr else "", "fracttal_mudou": mudou_nome,
                       "reenviar": mudou_nome or mudou_codigo, "tecnicos": tecnicos, "tem_tecnico": tem,
                       "evidencia": evidencia, "avisos": avisos,
                       "_busca": norm(" ".join([nome] + [t["nome"] for t in tecnicos]))})
    linhas.sort(key=lambda l: norm(l["nome"]))

    tecnicos_v = []
    if ver == "tecnico":
        nome_eq = base.nome_equipe
        for pid, p in pessoas.items():
            eq = nome_eq.get(p["equipe_id"]) or SEM_EQUIPE
            reg = (base.regiao.get(base.regiao_da_equipe.get(p["equipe_id"])) or {}).get("nome") or SEM_REGIAO
            if ((pedido["equipe"] and eq != pedido["equipe"]) or (pedido["regiao"] and reg != pedido["regiao"])
                    or (pedido["q"] and norm(pedido["q"]) not in norm(p["nome"]))):
                continue
            us = sorted(({"usina_id": uid, "nome": nome_usina(uid), "status": x["status"],
                          "ate": _dm(D._id(x.get("ate_data_id")))}
                         for (uid, pp, _papel), x in atuais.items() if pp == pid), key=lambda u: norm(u["nome"]))
            tecnicos_v.append({"pessoa_id": pid, "nome": p["nome"], "equipe": eq, "regiao": reg, "usinas": us,
                               "n_usinas": len(us), "sem_email": not p["hmac"],
                               "rondas": sum(e.get(pid, {}).get("rondas", 0) for e in ev.values()),
                               "fechamentos": sum(e.get(pid, {}).get("fechamentos", 0) for e in ev.values())})
        tecnicos_v.sort(key=lambda t: norm(t["nome"]))

    vale = {(u, p) for (u, p, _papel), x in atuais.items() if x["status"] == "vale"}
    avisos_gerais = []
    if not cfg.get("NEXUS_CHAVE_CADASTRO"):
        avisos_gerais.append("Este Nexus não tem a chave do cadastro: os nomes aparecem pelo número e o e-mail (o "
                             "código que o App usa) não é lido.")
    if not cfg.get("NEXUS_PESSOA_HMAC"):
        avisos_gerais.append("Este Nexus não tem a NEXUS_PESSOA_HMAC: as linhas vão sem o código e sem a assinatura, e "
                             "o App não as aplica.")
    if erro_ev:
        avisos_gerais.append(f"A evidência de campo não foi lida agora ({erro_ev}): a lista e os avisos de técnico "
                             "seguem valendo.")
    return {"ver": ver, "linhas": [l for l in linhas if _passa(l, pedido)], "tecnicos": tecnicos_v,
            "total_usinas": len(linhas), "pedido": pedido, "opcoes": _opcoes(linhas, pedido), "todas": todas,
            "situacoes": dict(SITUACOES), "hoje": hoje,
            "pessoas_json": sorted(({"id": pid, "nome": p["nome"], "equipe_id": p["equipe_id"]}
                                    for pid, p in pessoas.items()), key=lambda p: norm(p["nome"])),
            "app": _comparar_app(cfg, base, nome_usina, nome_pessoa, vale),
            "livro_vazio": not est.get("decisoes"), "erro": est.get("erro") or "", "erro_cadastro": "",
            "avisos_gerais": avisos_gerais}


def historico_da_usina(cfg, base, pessoas: dict, usina_id: int) -> list[dict]:
    """As decisões da usina (da mais nova à mais antiga) com o nome de quem foi posto ou tirado e de quem decidiu (pelo
    código do e-mail do login; vazio = a senha de administrador)."""
    m = mapas_de(cfg, base.de_para, base.pessoas)
    hist = A.historico(cfg, A.ler(cfg), usina_id)
    ids = {h["pessoa_id"] for h in hist} | {m["hmac"].get(h["quem_hmac"]) for h in hist}
    nomes = base.nomes({i for i in ids if i})

    def nome(pid):
        return (pessoas.get(pid) or {}).get("nome") or nomes.get(pid) or (f"Pessoa {pid}" if pid else "")
    out = []
    for h in hist:
        q = m["hmac"].get(h["quem_hmac"])
        out.append(dict(h, nome=nome(h["pessoa_id"]), de=_dm(h["de"]), ate=_dm(h["ate"]),
                        quem=nome(q) if q else ("administrador (senha)" if not h["quem_hmac"] else "alguém fora do "
                                                                                                   "cadastro"),
                        quando_txt=_quando(h["quando"])))
    return out


def _quando(iso: str) -> str:
    """A hora UTC gravada → dd/mm/aaaa hh:mm de Brasília."""
    try:
        d = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=A.timezone.utc).astimezone(A._BRT)
    except ValueError:
        return iso
    return d.strftime("%d/%m/%Y %H:%M")
