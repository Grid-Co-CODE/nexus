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

Os filtros (Levi, 17/10/2026: "desenvolva" sobre a proposta e, no mesmo dia, "troque o filtro de região e coloque o de
cliente"): equipe, cliente, responsável, situação (com técnico, sem técnico, com aviso) e busca, em cascata como as
outras telas do PCM: cada um lista o que existe com os OUTROS aplicados,
e a opção escolhida fica na lista mesmo sem resultado.
"""
import collections
import json
import time
from datetime import date, datetime, timedelta

from ..campo import visao
from ..campo.ligacao_cadastro import SISTEMA_FRACTTAL, _norm, codigo_da_pessoa, mapas_de
from ..dados import fatos as D
from ..dados import livros
from . import atribuicoes as A
from .motivos import norm

FILTROS = ("equipe", "cliente", "responsavel", "situacao", "q")
SITUACOES = (("com_tecnico", "Com técnico"), ("sem_tecnico", "Sem técnico"), ("com_aviso", "Com aviso"))
EVIDENCIA_DIAS = 30
SEM_EQUIPE, SEM_REGIAO, SEM_RESPONSAVEL, SEM_CLIENTE = "Sem equipe", "Sem região", "Sem responsável", "Sem cliente"
APP_LIVRO, APP_ABA = "organizacao_app_campo", "Atribuicoes"
# o que a tela lê do banco numa listagem só (`visao.carregar`): o cadastro e a foto do App
DO_BANCO = tuple(("cadastro_nexus", a) for a in ("usinas", "equipes", "de_para", "pessoas", "clientes", "regioes_campo"))     + ((APP_LIVRO, APP_ABA),)
EVIDENCIA_S = 600            # a evidência de 30 dias não precisa ser mais fresca que 10 min
_EV: dict = {}


def limpar() -> None:
    _EV.clear()


class SemCadastro(Exception):
    """O cadastro do banco não foi lido (a API fora do ar, ou o teste sem banco): a tela abre com o aviso e nada grava."""

    def __str__(self):
        return f"Não consegui ler o cadastro no banco ({self.args[0] if self.args else 'erro'}): nada foi gravado."


def ler_base(meta: dict | None = None):
    """O cadastro do banco (`campo.visao._Base`), lido com uma listagem só (`visao.carregar`), ou SemCadastro com o
    tipo do erro. `meta`, se vier, recebe o que a listagem disse de cada aba (a evidência a usa)."""
    try:
        m = visao.carregar(DO_BANCO)
        if meta is not None:
            meta.update(m)
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
    """A regra da equipe, a mesma do App (o `espelhar_bd_operacoes.py`): cada pessoa de campo recebe as usinas EM
    OPERAÇÃO do cadastro com o mesmo `equipe_id` (Levi, 17/10/2026: "preenche os técnicos!!"; medido no banco no mesmo
    dia: 53 das 227 usinas da regra estavam fora de operação, e a tela abre só nas em operação). A lista nasce perto do
    que o campo vê hoje, e o PCM põe à mão a de fora de operação que precisar."""
    fr = _fracttal(base)
    out = []
    for uid, u in sorted(_usinas(base, todas=False).items()):
        eid = D._id(u.get("equipe_id"))
        for pid, p in sorted(pessoas.items()):
            if eid and p["equipe_id"] == eid:
                out.append(_pedido(uid, fr, pid, pessoas))
    return out


def pedidos_da_reemissao(base, pessoas: dict, est: dict, usina_id: int, hoje: int) -> list[dict]:
    """As ligações atuais da usina (valendo e agendadas) com o nome do Fracttal e o código de hoje: o que o App lê
    mudou (a usina foi renomeada no Fracttal, o e-mail foi corrigido no cadastro) e a linha precisa ir de novo."""
    fr = _fracttal(base)
    out = []
    for (uid, pid, _papel), x in sorted(A.atuais(est, hoje).items()):
        if uid != usina_id:
            continue
        p = _pedido(usina_id, fr, pid, pessoas, D._id(x.get("de_data_id")), D._id(x.get("ate_data_id")))
        # sem o código de hoje (o Nexus sem a chave do cadastro, o técnico promovido, a ficha sem e-mail), vai o gravado:
        # trocar o código bom por vazio tiraria a usina da pessoa no App sem o PCM decidir (revisão de 17/10)
        p["pessoa_hmac"] = p["pessoa_hmac"] or D._txt(x.get("pessoa_hmac"))
        p["usina_fracttal"] = p["usina_fracttal"] or D._txt(x.get("usina_fracttal"))
        out.append(p)
    return out


# ── a evidência de campo ──────────────────────────────────────────────────────────────────────────────────────
def _programacao_do_fim(base, sessao, meta, segunda: int) -> list[dict]:
    """As linhas da semana `segunda` no `fato_programacao`, lidas do FIM para trás. A carga põe as semanas do arquivo do
    robô (as 4 mais novas) depois das antigas (`programacao.mesclar_semanas`), então a semana em curso está no fim: lê
    página a página até passar dela (medido em 17/10/2026: 5 de 17 páginas, 4,4 s → ~1,4 s). Sem a contagem de linhas
    na listagem, lê a aba inteira."""
    if not meta or not meta[0]:
        return []
    sid, n = meta
    if not n:
        return [x for x in livros._linhas(base, sessao, sid) if D._id(x.get("data_id_semana")) == segunda]
    out, viu, off = [], False, ((n - 1) // 1000) * 1000
    while off >= 0:
        r = sessao.get(f"{base}/api/sheets/{sid}/rows", params={"limit": 1000, "offset": off}, timeout=60)
        r.raise_for_status()
        rows = r.json()
        rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
        da_semana = [x for x in (dict(zip(y.get("headers") or [], y.get("values") or [])) for y in rows)
                     if D._id(x.get("data_id_semana")) == segunda]
        out += da_semana
        if da_semana:
            viu = True
        elif viu:
            break                # já passou da semana em curso
        off -= 1000
    return out


def _evidencia(hoje: int, meta: dict | None = None) -> tuple[dict, str]:
    """({usina_id: {pessoa_id: {"rondas", "fechamentos", "na_programacao"}}}, erro), guardada por EVIDENCIA_S. Livro
    fora do ar = sem evidência, com o erro para a tela dizer. `meta`: a listagem que a tela já fez (senão, faz uma)."""
    g = _EV.get(hoje)
    if g and time.time() - g[0] < EVIDENCIA_S:
        return g[1], ""
    corte = _id_dia(_dia(hoje) - timedelta(days=EVIDENCIA_DIAS))
    segunda = _id_dia(_dia(hoje) - timedelta(days=_dia(hoje).weekday()))
    ev: dict = collections.defaultdict(lambda: collections.defaultdict(
        lambda: {"rondas": 0, "fechamentos": 0, "na_programacao": False}))
    try:
        base, sessao = visao._base(), visao._sessao()
        if not meta:
            r = sessao.get(f"{base}/api/sheets", timeout=60)
            r.raise_for_status()
            meta = {(x.get("workbook_key"), x.get("sheet_name")): (x.get("id"), int(x.get("row_count") or 0))
                    for x in r.json()}
        from concurrent.futures import ThreadPoolExecutor

        def fato(aba):
            sid = (meta.get(("nexus_fatos", aba)) or (None,))[0]
            return livros._linhas(base, sessao, sid) if sid else []
        # as três leituras são independentes: juntas (a espera é a rede)
        with ThreadPoolExecutor(max_workers=3) as exe:
            f_ronda, f_fech = exe.submit(fato, "fato_ronda"), exe.submit(fato, "fato_fechamento")
            f_prog = exe.submit(_programacao_do_fim, base, sessao,
                                meta.get(("nexus_programacao", "fato_programacao")), segunda)
            lidas = {"rondas": f_ronda.result(), "fechamentos": f_fech.result()}
            programacao = f_prog.result()
        for campo, linhas in lidas.items():
            for x in linhas:
                uid, pid, dia = D._id(x.get("usina_id")), D._id(x.get("pessoa_id")), D._id(x.get("data_id"))
                if uid and pid and dia and corte <= dia <= hoje:
                    ev[uid][pid][campo] += 1
        for x in programacao:
            uid, pid = D._id(x.get("usina_id")), D._id(x.get("pessoa_id_tecnico"))
            if uid and pid:
                ev[uid][pid]["na_programacao"] = True
    except Exception as ex:      # noqa: BLE001 — o banco fora não derruba a tela: só tira a evidência
        return {}, f"{type(ex).__name__}"
    ev = {u: dict(p) for u, p in ev.items()}
    _EV.clear()
    _EV[hoje] = (time.time(), ev)
    return ev, ""


# ── a foto do App ─────────────────────────────────────────────────────────────────────────────────────────────
def _comparar_app(cfg, base, nome_usina, nome_pessoa, vale: dict) -> dict:
    """{"existe", "so_no_app", "so_no_nexus", "pendencias"}: o `executa` do App contra o que vale no Nexus, no IDIOMA
    DO APP — a grafia da usina e o código da pessoa que vão na linha (revisão de 17/10: comparar pelos IDs do Nexus
    dava "igual" quando o App usa outra grafia da mesma usina, ou quando a linha vai sem código). `vale`:
    {(usina_id, pessoa_id): a linha vigente}."""
    try:
        linhas = visao._livro(APP_LIVRO, APP_ABA)
    except Exception:            # noqa: BLE001
        linhas = []
    if not linhas:
        return {"existe": False, "so_no_app": [], "so_no_nexus": [], "pendencias": []}
    m = mapas_de(cfg, base.de_para, base.pessoas)
    pend, nexus, app_ = {}, {}, {}
    for (uid, pid), x in vale.items():
        fr, cod = " ".join(D._txt(x.get("usina_fracttal")).split()), D._txt(x.get("pessoa_hmac"))
        if not fr:
            pend[("nx-usina", uid)] = f"{nome_usina(uid)}: vai ao App sem o nome do Fracttal (o App não acha a usina)"
        elif not cod:
            pend[("nx-pessoa", uid, pid)] = (f"{nome_usina(uid)} · {nome_pessoa(pid)}: vai ao App sem o código (sem "
                                             "e-mail no cadastro), e o App não a aplica")
        else:
            nexus[(_norm(fr), cod)] = (uid, pid, fr)
    for x in linhas:
        if D._txt(x.get("Papel")).lower() != "executa":
            continue
        usina, cod = " ".join(D._txt(x.get("Usina")).split()), D._txt(x.get("Pessoa (HMAC)"))
        uid, pid = m["usina"].get(_norm(usina)), m["hmac"].get(cod)
        if not uid:
            pend[("usina", usina)] = f"{usina}: usina do App sem o nome do Fracttal no de-para do cadastro"
        elif not pid:
            pend[("pessoa", uid, cod)] = (f"{nome_usina(uid)}: a pessoa de código {cod[:8]}… do App sem ficha que "
                                          "case (sem e-mail no cadastro, ou com outro e-mail)")
        else:
            app_[(_norm(usina), cod)] = (uid, pid, usina)

    def itens(lado: dict, outro: dict):
        return sorted(({"usina_id": u, "usina": nome_usina(u), "pessoa_id": p, "nome": nome_pessoa(p), "grafia": g}
                       for k, (u, p, g) in lado.items() if k not in outro),
                      key=lambda i: (norm(i["usina"]), norm(i["nome"]), i["grafia"]))
    return {"existe": True, "so_no_app": itens(app_, nexus), "so_no_nexus": itens(nexus, app_),
            "pendencias": [pend[k] for k in sorted(pend, key=str)]}


# ── a tela ────────────────────────────────────────────────────────────────────────────────────────────────────
def _pedido_dos_args(args) -> dict:
    return {k: " ".join(str(args.get(k) or "").split())[:80] for k in FILTROS}


def _passa(l: dict, pedido: dict, menos: str | None = None) -> bool:
    for k in ("equipe", "cliente", "responsavel"):
        if k != menos and pedido[k] and l[k] != pedido[k]:
            return False
    if menos != "situacao" and pedido["situacao"]:
        if pedido["situacao"] == "com_tecnico" and not l["tem_tecnico"]:
            return False
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
    for k in ("equipe", "cliente", "responsavel", "situacao"):
        c = collections.Counter()
        for l in linhas:
            if not _passa(l, pedido, menos=k):
                continue
            if k == "situacao":
                c["com_tecnico"] += l["tem_tecnico"]
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
    """O contexto da tela (`pcm/tecnicos.html`, no estilo da tela de PT do Campo). `args`: os filtros, `ver` (a aba:
    usina | tecnico | app) e `todas` (as usinas fora de operação também)."""
    hoje = hoje or A.hoje_id()
    pedido = _pedido_dos_args(args)
    ver = args.get("ver") if args.get("ver") in ("tecnico", "app") else "usina"
    lido = datetime.now(A._BRT).strftime("%H:%M")
    meta: dict = {}
    try:
        base = ler_base(meta)
    except SemCadastro as ex:
        return {"ver": ver, "linhas": [], "tecnicos": [], "total_usinas": 0, "pedido": pedido, "lido": lido,
                "resumo": {}, "resumo_op": {}, "resumo_todas": {}, "chips": {}, "todas_linhas": [],
                "todos_tecnicos": [], "opcoes_todas": {k: [] for k in ("equipe", "cliente", "responsavel")},
                "opcoes": {k: [] for k in FILTROS if k != "q"}, "todas": str(args.get("todas") or "") == "1",
                "situacoes": dict(SITUACOES), "hoje": hoje, "pessoas_json": [],
                "app": {"existe": False, "so_no_app": [], "so_no_nexus": [], "pendencias": []}, "livro_vazio": False,
                "erro": "", "erro_cadastro": ex.args[0] if ex.args else "erro", "avisos_gerais": []}
    pessoas = pessoas_de_campo(base, cfg)
    est = A.ler(cfg)
    atuais = A.atuais(est, hoje)
    fr = _fracttal(base)
    ev, erro_ev = _evidencia(hoje, meta)
    todas = str(args.get("todas") or "") == "1"
    # todas as usinas vão à página (as fora de operação escondidas): o filtro "Todas" é na própria página (17/10/2026)
    usinas = _usinas(base, todas=True)
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
            gravado = D._txt(x.get("pessoa_hmac"))
            tecnicos.append({"pessoa_id": pid, "nome": nome_pessoa(pid), "status": x["status"],
                             "de": _dm(D._id(x.get("de_data_id"))), "ate": _dm(D._id(x.get("ate_data_id"))),
                             "sem_email": not gravado})
            mudou_nome |= bool(nomes_fr) and D._txt(x.get("usina_fracttal")) != nomes_fr[0]
            mudou_codigo |= bool(hm) and gravado != hm
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
        sit = ("critico", "Sem técnico") if not tem else ("alerta", "Com aviso") if avisos else ("ok", "Com técnico")
        linhas.append({"sit": sit, "op": D._txt(u.get("status")).upper() == visao.STATUS_OPERACAO, "usina_id": uid, "nome": nome, "status": D._txt(u.get("status")), "equipe_id": eid,
                       "cliente": base.nome_cliente.get(D._id(u.get("cliente_id"))) or SEM_CLIENTE,
                       "equipe": base.nome_equipe.get(eid) or SEM_EQUIPE, "regiao": reg.get("nome") or SEM_REGIAO,
                       "responsavel": nome_pessoa(resp) if resp else SEM_RESPONSAVEL,
                       "fracttal": nomes_fr[0] if nomes_fr else "", "fracttal_mudou": mudou_nome,
                       "reenviar": mudou_nome or mudou_codigo, "tecnicos": tecnicos, "tem_tecnico": tem,
                       "evidencia": evidencia, "avisos": avisos,
                       "_busca": norm(" ".join([nome] + [t["nome"] for t in tecnicos]))})
    linhas.sort(key=lambda l: norm(l["nome"]))
    todas_linhas = linhas
    linhas = [l for l in todas_linhas if todas or l["op"]]          # o escopo: em operação, ou todas

    tecnicos_v, todos_v = [], []
    # a aba Por técnico mostra a conta mesmo na aba Por usina, e o topo conta todas as pessoas de campo
    nome_eq = base.nome_equipe
    cliente_de = {uid: base.nome_cliente.get(D._id(u.get("cliente_id"))) or SEM_CLIENTE
                  for uid, u in base.por_id.items()}
    for pid, p in pessoas.items():
        eq = nome_eq.get(p["equipe_id"]) or SEM_EQUIPE
        reg = (base.regiao.get(base.regiao_da_equipe.get(p["equipe_id"])) or {}).get("nome") or SEM_REGIAO
        us = sorted(({"usina_id": uid, "nome": nome_usina(uid), "status": x["status"],
                      "ate": _dm(D._id(x.get("ate_data_id")))}
                     for (uid, pp, _papel), x in atuais.items() if pp == pid), key=lambda u: norm(u["nome"]))
        sit = (("critico", "Sem usina") if not us else ("alerta", "Sem e-mail") if not p["hmac"]
               else ("ok", "Com usina"))
        t = {"pessoa_id": pid, "nome": p["nome"], "cargo": p["cargo"], "equipe": eq, "regiao": reg, "usinas": us,
             "sit": sit, "n_usinas": len(us), "sem_email": not p["hmac"],
             "rondas": sum(e.get(pid, {}).get("rondas", 0) for e in ev.values()),
             "fechamentos": sum(e.get(pid, {}).get("fechamentos", 0) for e in ev.values())}
        t["clientes"] = sorted({cliente_de.get(u["usina_id"]) or SEM_CLIENTE for u in us}, key=norm)
        t["_busca"] = norm(p["nome"])
        todos_v.append(t)
        # na visão por técnico, o cliente filtra quem tem usina dele
        if not ((pedido["equipe"] and eq != pedido["equipe"])
                or (pedido["cliente"] and not any(cliente_de.get(u["usina_id"]) == pedido["cliente"] for u in us))
                or (pedido["q"] and norm(pedido["q"]) not in norm(p["nome"]))):
            tecnicos_v.append(t)
    tecnicos_v.sort(key=lambda t: norm(t["nome"]))

    vale = {(u, p): x for (u, p, _papel), x in atuais.items() if x["status"] == "vale"}
    avisos_gerais = []
    if not cfg.get("NEXUS_CHAVE_CADASTRO"):
        avisos_gerais.append("Este Nexus não tem a chave do cadastro: os nomes aparecem pelo número e o e-mail (o "
                             "código que o App usa) não é lido.")
    if not cfg.get("NEXUS_PESSOA_HMAC"):
        avisos_gerais.append("Este Nexus não tem a NEXUS_PESSOA_HMAC: sem ela a linha iria sem assinatura e o App não a "
                             "aplicaria, então nada se grava.")
    if erro_ev:
        avisos_gerais.append(f"A evidência de campo não foi lida agora ({erro_ev}): a lista e os avisos de técnico "
                             "seguem valendo.")
    # o topo, como o da tela de PT: o universo da tela (as usinas da lista e as pessoas de campo), sem os filtros; as duas
    # contas (em operação e todas) vão à página, que troca ao clicar em "Todas"
    def _resumo(ls):
        return {"usinas": len(ls), "com_tecnico": sum(l["tem_tecnico"] for l in ls),
                "sem_tecnico": sum(not l["tem_tecnico"] for l in ls), "com_aviso": sum(bool(l["avisos"]) for l in ls),
                "pessoas": len(todos_v), "com_usina": sum(bool(t["usinas"]) for t in todos_v),
                "apoios": sum(1 for x in atuais.values() if D._txt(x.get("ate_data_id")) or x["status"] == "agendado")}
    resumo_op, resumo_todas = _resumo([l for l in todas_linhas if l["op"]]), _resumo(todas_linhas)
    resumo = resumo_todas if todas else resumo_op
    opcoes = _opcoes(linhas, pedido)
    visiveis = {id(l) for l in linhas if _passa(l, pedido)}
    for l in todas_linhas:
        l["_visivel"] = id(l) in visiveis
    vis_t = {id(t) for t in tecnicos_v}
    for t in todos_v:
        t["_visivel"] = id(t) in vis_t
    # as listas dos filtros: todo valor de toda usina (a escolha de "Todas" é na página); as contas, a página refaz
    opcoes_todas = {k: sorted({l[k] for l in todas_linhas} | ({pedido[k]} if pedido[k] else set()), key=norm)
                    for k in ("equipe", "cliente", "responsavel")}
    opcoes_todas["cliente"] = sorted(set(opcoes_todas["cliente"]) | {c for t in todos_v for c in t["clientes"]}, key=norm)
    opcoes_todas["equipe"] = sorted(set(opcoes_todas["equipe"]) | {t["equipe"] for t in todos_v}, key=norm)
    chips = dict(opcoes["situacao"], todas=sum(1 for l in linhas if _passa(l, pedido, menos="situacao")))
    return {"ver": ver, "linhas": [l for l in linhas if _passa(l, pedido)], "tecnicos": tecnicos_v, "lido": lido,
            "resumo": resumo, "resumo_op": resumo_op, "resumo_todas": resumo_todas, "chips": chips,
            "todas_linhas": todas_linhas, "todos_tecnicos": sorted(todos_v, key=lambda t: norm(t["nome"])),
            "opcoes_todas": opcoes_todas,
            "total_usinas": len(linhas), "pedido": pedido, "opcoes": opcoes, "todas": todas,
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
