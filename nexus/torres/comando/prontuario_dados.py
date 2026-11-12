"""As fontes do prontuário da usina no Comando (12/11/2026; a conta é `nexus/comando/prontuario.py`).

O que vem do banco para TODAS as usinas (o mês a mês da meta e da disponibilidade, as normalizações do COS, a zeladoria
semanal, as tarefas das OS abertas com o nome do ativo, os chamados de garantia e o resumo da estrutura) é lido uma vez
e guardado por usina na cópia de 5 min do Campo (`visao._ler`, a chave `comando_prontuarios`): o clique na usina não
espera cinco leituras do banco, e a cópia vencida volta na hora e se refaz por trás, como as outras contas das telas. O
resto já tem a cópia da tela dona (as rondas, as PT, as luvas, a conversa, as demandas) e é só filtrado pela usina.

Cada fonte que não abre fica de fora com o aviso (`avisos`); o resto da página vale. Nada aqui lê o Fracttal.
"""
import collections
import logging

from flask import session

from ...campo import responsaveis as R
from ...campo import visao
from ...comando import prontuario as PR

_log = logging.getLogger(__name__)
CHAVE = ("comando_prontuarios",)
MESES = 6            # os meses do mês a mês (o banco tem a meta desde 10/2026)
PT_NA_LISTA = 4
# O "Criar OS" do prontuário (Levi, 12/11/2026: "Também deve ser possível criar OS para a UFV"; e, vendo o botão do
# ticket: "na parte de criar OS, vai ter as opções que é possível hoje. Então, OS avulsa, OS de performance, OS de
# engenharia, inspeção de chamados, solicitação de OS. E aí o ticket pode tirar o botão de ticket"). As cinco formas de
# criar OS que o OS Creator tem hoje: (o nome, o que é, o endereço no OS Creator, leva a usina?). A OS avulsa (o "Criar OS
# do zero" de lá) e a solicitação aceitam o ativo pelo endereço (`?ativo=<o código do ativo da usina>`,
# `tradicional_web.sugestao`): a tela abre com o cliente e a usina escolhidos. A Performance pergunta o plano primeiro,
# a Engenharia tem a tela dela e a inspeção pede o ativo pelo id do Fracttal: essas abrem sem a usina.
CRIAR_OS = (("OS avulsa", "qualquer serviço, do zero, direto no Fracttal", "/os/tradicional", True),
            ("OS de Performance", "geração e ETM, inversor, string ou tracker; nasce com o ticket", "/os/performance", False),
            ("OS de Engenharia", "as OS que a Engenharia abre", "/os/engenharia", False),
            ("Inspeção de chamados", "a inspeção que abre o chamado de garantia", "/os/chamados/inspecao", False),
            ("Solicitação de OS", "pedir a OS ao PCM e acompanhar o pedido", "/os/solicitacao", True))


def criar_os(codigo: str) -> list[dict]:
    """As opções do Criar OS para a usina de código `codigo` (o do cadastro, que é o do ativo dela no Fracttal): [{rot,
    sub, url}]. Sem o código no cadastro, todas abrem sem a usina escolhida."""
    from urllib.parse import quote
    ativo = f"?ativo={quote(str(codigo).strip())}" if str(codigo or "").strip() else ""
    return [{"rot": rot, "sub": sub, "url": url + (ativo if leva else "")} for rot, sub, url, leva in CRIAR_OS]


def _id(v):
    return visao.D._id(v)


def _de_todas():
    """{"metas": {AAAAMM: {usina_id: linha}}, "disps": {"AAAA-MM": {usina_id: linha}}, "cos", "zel", "tarefas",
    "chamados" ({usina_id: [linhas]}), "nomes_equip" {equipamento_id: descrição}, "estrutura" {usina_id: resumo},
    "erros" {fonte: o que ficou de fora}} na cópia de 5 min."""
    def calcular():
        b = visao._Base()
        nomes = R.Nomes(b)
        erros: dict[str, str] = {}

        def tentar(chave, aviso, f, vazio):
            try:
                return f()
            except Exception:       # noqa: BLE001 — a fonte que não abre fica de fora; o resto do prontuário vale
                _log.exception("prontuário: %s não abriu", aviso)
                erros[chave] = aviso
                return vazio

        def ler_metas():
            ids = sorted({R._int(r.get("mes_id")) for r in visao._livro(R.LIVRO_META, R.ABA_META)} - {None}, reverse=True)
            return {mid: R.metas(nomes, mid)[0] for mid in ids[:MESES]}

        def ler_disps():
            ms = sorted({str(r.get("mes") or "") for r in visao._livro(R.LIVRO_DISP, R.ABA_DISP)} - {""}, reverse=True)
            return {m: R.disponibilidade(nomes, m)[0] for m in ms[:MESES]}

        def por_usina(livro, aba, campos):
            out = collections.defaultdict(list)
            for r in visao._livro(livro, aba):
                uid = _id(r.get("usina_id"))
                if uid:
                    out[uid].append({k: r.get(k) for k in campos})
            return dict(out)

        def ler_cos():
            from ...cos import normalizacoes_banco as NB
            return por_usina(NB.LIVRO, NB.ABA, ("os", "tipo_falha", "inicio", "normalizado_em", "fora_min", "geracao_parou",
                                                "fora_do_escopo_oem"))

        def ler_zel():
            from ...campo import zeladoria_banco as ZB
            return por_usina(ZB.LIVRO, ZB.ABA, ("semana", "data_id_semana", "vegetacao_nivel", "sujidade_nivel", "vala",
                                                "recomendacao", "situacao_vegetacao", "data_id_situacao_vegetacao",
                                                "os_zeladoria_vegetacao", "situacao_sujidade", "data_id_situacao_sujidade",
                                                "os_zeladoria_sujidade"))

        def ler_tarefas():
            from ...dados import fato_tarefa_os as FT
            return por_usina(FT.LIVRO, FT.ABA, ("os", "codigo_ativo", "equipamento_id", "data_id_criacao", "tipo_tarefa",
                                                "estado_tarefa", "status_os"))

        def ler_chamados():
            return por_usina(R.LIVRO_CHAMADOS, R.ABA_CHAMADOS, ("os", "data_id_abertura", "data_id_fim", "codigo_ativo",
                                                                "equipamento_id", "situacao", "fabricante", "componente",
                                                                "status"))

        def ler_estrutura():
            from ...cadastro import estrutura_usina as EU
            from ...dados.conexao import banco
            est = EU.ler(*banco())
            if est.get("erro") and not est.get("lido_em"):
                raise RuntimeError(est["erro"])
            out = {}
            for uid in b.mobilizadas:
                u = EU.da_usina(est, uid)
                if u["inversores"] or u["cabines"]:
                    r = EU.resumo(u)
                    out[uid] = {k: r.get(k) for k in ("cabines", "inversores", "strings", "kwp_inversores")}
            return out
        d = {"metas": tentar("meses", "o mês a mês da meta", ler_metas, {}),
             "disps": tentar("disp", "o mês a mês da disponibilidade", ler_disps, {}),
             "cos": tentar("cos", "o histórico do COS", ler_cos, {}),
             "zel": tentar("zel", "a leitura semanal da zeladoria", ler_zel, {}),
             "tarefas": tentar("tarefas", "as tarefas das OS abertas por equipamento", ler_tarefas, {}),
             "chamados": tentar("chamados", "os chamados de garantia", ler_chamados, {}),
             "estrutura": tentar("estrutura", "a estrutura da usina no Nexus", ler_estrutura, {})}

        def ler_nomes():
            # só os ativos que as tarefas e os chamados citam (o livro tem 31 mil equipamentos)
            usados = {_id(t.get("equipamento_id")) for ts in d["tarefas"].values() for t in ts}
            usados |= {_id(c.get("equipamento_id")) for cs in d["chamados"].values() for c in cs}
            usados.discard(None)
            return {_id(r.get("equipamento_id")): str(r.get("descricao") or "").strip()
                    for r in visao._livro(R.LIVRO_EQUIP, R.ABA_EQUIP) if _id(r.get("equipamento_id")) in usados}
        d["nomes_equip"] = tentar("nomes", "o nome dos equipamentos", ler_nomes, {})
        d["erros"] = erros
        return d
    return visao._ler(CHAVE, calcular)


# as telas que o prontuário cita: o link, o botão e o bloco da tela que a pessoa não abre não aparecem (a Central da
# usina já fazia assim com as Ocorrências, a Mesa da Segurança e as Rondas)
_CAMINHOS = {"os": "/os/tradicional", "conversa": "/t/comando/conversa/usina/{id}", "rondas": "/t/campo/rondas/usina/{id}",
             "mesa": "/t/hseq/mesa", "cos": "/t/cos/ronda", "garantias": "/t/chamados/garantias",
             "insights": "/t/comando/insights", "caixa": "/t/comando/caixa-de-entrada", "central": "/t/campo/responsaveis"}


def _pode(usina_id: int) -> dict:
    """{chave de `_CAMINHOS`: a pessoa abre?}, pela mesma régua do portão (`setor_telas.pode`); sem portão, tudo."""
    from ...auth import setor_telas
    liberadas = setor_telas.liberadas_do_menu()
    return {k: liberadas is None or setor_telas.pode(c.format(id=usina_id), liberadas) for k, c in _CAMINHOS.items()}


def contexto(usina_id: int, cu: dict | None = None, rel_url: str = "") -> dict | None:
    """Tudo o que o `comando/_prontuario.html` pede, para as duas portas da mesma página: o Comando > Usinas
    (/t/comando/usinas/<id>) e a aba Central da usina da Usinas 360°, que esta página substituiu (Levi, 12/11/2026: "essa
    visão irá substituir a central da usina"). `cu` = a Central já calculada por quem chama (a aba da Usinas 360°);
    `rel_url` = o endereço do relatório em PDF de quem chama. None = a usina não está na lista (não mobilizada)."""
    from ...campo import responsaveis as campo_resp
    from ...campo.manutencao import LIMITE_PADRAO
    from ...comando import regras as RG
    from ..campo import _central_da_usina, _iniciais
    from . import _usinas_montadas
    m = _usinas_montadas()
    x = next((l for l in m["linhas"] if l["usina_id"] == usina_id), None)
    if x is None:
        return None
    if cu is None:
        cu = _central_da_usina(campo_resp.com_manutencao(m["visao"].get("usinas") or [], LIMITE_PADRAO), usina_id)
    vivos = sorted(m["vivos"].get(usina_id) or [], key=lambda i: (RG.ORDEM_SEV.get(i.get("sev"), 9), i.get("titulo") or ""))
    # o título do insight sem o nome da usina na frente ("Mandaguaçu: 1 extintor vencido"): a página já é dela
    vivos = [dict(i, titulo=PR.sem_o_nome(i.get("titulo"), x.get("usina") or "")) for i in vivos]
    return {"x": x, "cu": cu, "insights": vivos, "severidades": RG.SEVERIDADES, "regras": RG.REGRAS, "avisos": m["avisos"],
            "iniciais": _iniciais, "sem_responsavel": visao.SEM_RESPONSAVEL,
            "p": montar(usina_id, x, cu, vivos, rel_url=rel_url)}


def montar(usina_id: int, x: dict, cu: dict, vivos: list[dict], rel_url: str = "") -> dict:
    """O que o prontuário mostra além da Central da usina (`cu`) e da linha da lista (`x`): o parecer e o que pede
    atenção, o painel do alto, a linha de cada cartão, o mês a mês, o COS, a zeladoria, as rondas, os equipamentos com OS
    aberta, os chamados, a segurança, as demandas, a conversa, a composição e a linha do tempo. `avisos` = o que não
    abriu."""
    hoje = visao._agora().date()
    lei = _de_todas()
    d = lei.dados or {}
    avisos = ([f"o histórico da usina ({lei.erro})"] if lei.erro else []) + list((d.get("erros") or {}).values())
    u = cu.get("u") or {}

    meses = PR.mes_a_mes({mid: (m or {}).get(usina_id) for mid, m in (d.get("metas") or {}).items()},
                         {mes: (v or {}).get(usina_id) for mes, v in (d.get("disps") or {}).items()}, hoje)
    anterior = next((m for m in meses if not m["parcial"]), None)
    cos = PR.cos_historico((d.get("cos") or {}).get(usina_id), hoje)
    zel = PR.zeladoria_semanas((d.get("zel") or {}).get(usina_id))
    tarefas = (d.get("tarefas") or {}).get(usina_id) or []
    nomes = d.get("nomes_equip") or {}
    chamados = [dict(c, equip=nomes.get(_id(c.get("equipamento_id"))) or str(c.get("codigo_ativo") or ""))
                for c in (d.get("chamados") or {}).get(usina_id) or []]
    abertos_por_ativo = {str(c["codigo_ativo"]).strip(): c for c in chamados
                         if str(c.get("situacao") or "") in ("aberto", "verificacao") and c.get("codigo_ativo")}
    equip = PR.equipamentos_abertos(tarefas, nomes, abertos_por_ativo, x.get("codigo") or "")

    hist = None
    try:
        from ...campo import ronda_checklist
        dr = visao.rondas().dados or {}
        hist = visao.historico_usina(dr.get("todas") or [], ronda_checklist.respostas(), usina_id, dr.get("validacoes") or [])
    except Exception:           # noqa: BLE001
        _log.exception("prontuário: as rondas não abriram")
        avisos.append("o histórico de rondas")

    pts = []
    try:
        dp = visao.pts().dados or {}
        pts = sorted((p for p in dp.get("historico") or [] if p.get("usina_id") == usina_id),
                     key=lambda p: str(p.get("criada") or ""), reverse=True)
    except Exception:           # noqa: BLE001
        _log.exception("prontuário: as PT não abriram")
        avisos.append("o histórico das PT")

    luvas = None
    try:
        from ...hseq import epi as EPI
        lv = EPI.luvas()
        if not lv.erro:
            luvas = next((l for l in (lv.dados or {}).get("usinas") or [] if l.get("usina_id") == usina_id), None)
    except Exception:           # noqa: BLE001
        _log.exception("prontuário: as luvas não abriram")

    # as demandas entre setores que citam a usina: só as que a pessoa pode ver (quem pediu, quem recebeu, o setor de quem
    # recebeu e o administrador); pela cópia do livro, sem esperar o banco
    demandas = []
    try:
        from ...comando import demandas as D
        from .demandas_tela import _pode_ver
        lido = None if D.faltam_chaves() else D.copia()
        if lido is not None:
            demandas = [dm for dm in D.lista(hoje, lido=lido)
                        if any(uid == usina_id for uid, _n in dm["usinas"]) and _pode_ver(dm)]
    except Exception:           # noqa: BLE001
        _log.exception("prontuário: as demandas não abriram")

    conversa = {"n": 0, "ultima": None}
    try:
        from ...comando import conversa as CV
        msgs = (CV.atual().get(f"usina:{usina_id}") or {}).get("mensagens") or []
        conversa = {"n": len(msgs), "ultima": msgs[-1] if msgs else None}
    except Exception:           # noqa: BLE001
        _log.exception("prontuário: a conversa da usina não abriu")

    try:
        ficha = visao._Base().por_id.get(usina_id) or {}
    except Exception:           # noqa: BLE001
        ficha = {}
    mob = PR.do_data_id(str(ficha.get("data_mobilizacao") or "").replace("-", "")[:8])
    itens = PR.atencao(u, x.get("os_cos"), vivos, demandas, x.get("usina") or "")
    pts_aguardando = PR._int((cu.get("pts") or {}).get("aguardando")) or 0
    resumos = PR.resumos(u, x, vivos, cos, luvas, pts_aguardando, cu.get("seguranca") or (), demandas, conversa["n"])
    return {
        "parecer": PR.parecer(itens),
        "atencao": itens,
        "em_dia": PR.em_dia(u),
        "painel": PR.painel(u, x, itens, cos, vivos, resumos, anterior),
        "resumos": resumos,
        "pts_aguardando": pts_aguardando,
        # as ações do alto: criar a OS (as formas de hoje do OS Creator, com a usina escolhida onde a tela de lá aceita) e
        # o relatório em PDF do cliente
        "criar_os": criar_os(x.get("codigo") or ""), "rel_url": rel_url,
        "rel_meses": cu.get("rel_meses") or [], "rel_mes": cu.get("rel_mes") or "", "rel_temas": cu.get("rel_temas") or [],
        "rel_campos": cu.get("rel_campos") or [],
        "meses": meses, "cos": cos, "zel": zel,
        "rondas": PR.rondas_resumo(hist) if hist is not None else None,
        "equip": equip,
        "os_grupos": PR.os_grupos(u.get("manutencao"), (((u.get("manut") or {}).get("valores") or {}).get("atrasadas") or {})
                                  .get("cls") or "alerta"),
        "chamados_abertos": (u.get("chamados") or {}).get("lista") or [],
        "chamados_n": (u.get("chamados") or {}).get("abertos") or 0,
        "pts": [{"numero": p.get("numero"), "dia": p.get("apr_dia") or "", "os": PR._int(p.get("os")),
                 "situacao": PR._SITUACAO_PT.get(str(p.get("situacao") or ""), str(p.get("situacao") or "").replace("_", " ")),
                 "solicitante": p.get("solicitante") or "", "tarefa": p.get("tarefa") or ""} for p in pts[:PT_NA_LISTA]],
        "pts_n": len(pts), "luvas": luvas,
        # as PT que esperam o De acordo agora (a lista do Painel, a parada de hoje primeiro): na aba da Usinas 360° cada
        # uma abre a decisão na janela de lá
        "pts_espera": (cu.get("pts") or {}).get("linhas") or [],
        "pode": _pode(usina_id),
        "demandas": demandas, "conversa": conversa,
        "composicao": PR.composicao(ficha, (d.get("estrutura") or {}).get(usina_id), x.get("cliente") or ""),
        "mobilizada": mob.strftime("%m/%Y") if mob else "",
        "linha": PR.linha_do_tempo(hoje, hist or [], cos["todas"], pts, chamados, tarefas),
        "fontes": PR.FONTES, "linha_dias": PR.LINHA_DO_TEMPO_DIAS, "avisos": avisos,
        "admin": bool(session.get("admin")),
    }
