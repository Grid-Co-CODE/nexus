"""Tela Base > Equipamentos das usinas (13/10/2026): a usina do Registro mestre ligada, à mão, às chaves do supervisório
(a "Usina Supervisório"), e os equipamentos dela nas colunas da aba Equipamentos (cabines, inversores, strings,
potência). As regras e o livro do banco moram em `estrutura_usina.py`.

**Sem Fracttal na tela** (Levi, 13/10/2026: "já temos a ligação com o Fractall pelo registro mestre que é o código da UFV,
só precisamos ligar o que aparece no repositório do que vai aparecer lá na plataforma de tempo real, então tem que
funcionar mais como uma tabela que nem era na TEquipamentos do BD_Performance"; ligar ao OS Creator fica para depois).
Saíram o passo do nome do Fracttal e o ativo do Fracttal de cada cabine e inversor; as rotas `/fracttal` e `/ativos` e os
campos `equipamento_id`/`codigo_fracttal` do livro ficam (o que já foi gravado não se perde). O nome do Fracttal da
visão no formato da aba ("Usina Fractall") continua vindo das Ligações, sem passo na tela.

Levi, 13/10/2026: "Não quero que faça as conexões automaticamente, quero poder ver e fazer de forma versátil, pq se só
você fizer vai ficar fácil de entender para você, quando eu for fazer não vou entender nada". Por isso nada liga sozinho:
a tela ordena as opções (as parecidas primeiro, com o porquê escrito) e quem escolhe é a pessoa; o "Trazer da aba"
preenche um rascunho, e só o Salvar grava.

Só administrador (o Registro mestre e a gravação no banco). Os POST são da própria página (`_de_outro_site`, a régua da
moldura e da Integração Fracttal); o Salvar da estrutura vai por fetch com JSON e devolve o estado novo (os IDs novos),
sem recarregar (a lista de inversores de uma usina grande passa de 40 linhas: recarregar perdia a rolagem).
"""
import difflib
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from flask import current_app, jsonify, redirect, render_template, request, session, url_for

from ..dados import fatos as D
from ..dados.livros import GravacaoRecusada
from . import banco as B
from . import estrutura_usina as E
from . import ligacoes as L
from .telas import _quem, _tela

log = logging.getLogger(__name__)

TITULO = "Equipamentos das usinas"
_BRT = timezone(timedelta(hours=-3))
FILTROS = (("", "Todas as usinas"), ("sem_chave", "Sem chave do supervisório"),
           ("sem_inversores", "Sem inversores"), ("potencia", "Potência que não fecha"))
SEM_CLIENTE = "-"            # o valor do filtro de cliente para as usinas sem cliente no Registro mestre
_CHAVE_AVISO = "equipamentos_aviso"


def _meu_email() -> str:
    u = session.get("usuario")
    return str(u.get("email") or "").strip().lower() if isinstance(u, dict) else ""


def _de_outro_site() -> bool:
    from ..torres.moldura import _de_outro_site as regra
    return regra()


def _banco():
    from ..campo import visao
    return visao._base(), visao._sessao()


def _hora(ts) -> str:
    return datetime.fromtimestamp(ts, _BRT).strftime("%d/%m às %H:%M") if ts else ""


def _parecido(a, b) -> float:
    return difflib.SequenceMatcher(None, E.norm(a), E.norm(b)).ratio()


def _usinas(srv) -> list[dict]:
    """As usinas do Registro mestre (as da seção Ligações) com a potência que a conferência usa: a REAL (a instalada, em
    MWp) e, sem ela, a contratual. Medido em 13/10/2026: a aba Equipamentos bate com a real (Araputanga 1: real 3,469 MWp,
    contratual 3,25; a UFV da aba, 3.469,2 kWp), e 68 das 258 usinas ainda não têm a real."""
    real = {}
    for u in srv.registros("usinas"):
        v = u.valor("potencia_real")
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            real[B._id(u.id)] = float(v)
    out = []
    for x in L._usinas(srv):
        r, c = real.get(x["id"]), x.get("mwp")
        kr, kc = (round(r * 1000, 3) if r else None), (round(c * 1000, 3) if c and c > 0 else None)
        out.append(dict(x, kwp_real=kr, kwp_contratual=kc, kwp=kr or kc,
                        kwp_de="real" if kr else ("contratual" if kc else "")))
    return out


def _info_usinas(srv, cfg, usinas: list | None = None) -> dict:
    """{usina_id: {nome, codigo, cliente, kwp, kwp_de, fracttal}}: o que a visão no formato da aba e o de-para do tempo
    real levam de cada usina, do Registro mestre (o nome, o código, o cliente e a potência da conferência, com a origem
    dela: o de-para grava a linhagem do kWp) e das Ligações (o 1º nome do Fracttal ligado)."""
    _nomes, fr_da_usina, _dono, _lido = _fracttal(cfg)
    return {u["id"]: {"nome": u["nome"], "codigo": u["codigo"], "cliente": u["cliente"], "kwp": u["kwp"],
                      "kwp_de": u["kwp_de"], "fracttal": (fr_da_usina.get(u["id"]) or [{}])[0].get("chave", "")}
            for u in (usinas if usinas is not None else _usinas(srv))}


def _leituras(forcar: bool = False) -> tuple:
    """(estrutura gravada, aba Equipamentos agrupada, pode gravar?). Banco fora (ou teste sem banco): as duas vazias com o
    erro, e nada se grava sem saber o que já está lá."""
    try:
        base, sessao = _banco()
    except Exception as ex:      # noqa: BLE001
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        return ({"supervisorios": [], "cabines": [], "inversores": [], "lido_em": None, "erro": erro},
                {"chaves": {}, "lido_em": None, "erro": erro})
    if forcar:
        E._CACHE.pop("aba", None)
    return E.ler(base, sessao, forcar=forcar), E.aba_equipamentos(base, sessao)


def _fracttal(cfg) -> tuple:
    """(nomes do Fracttal, {usina_id: [{chave, como}]}, {nome: [usina_id]}, lido?) do de_para calculado da seção Ligações
    (`de_para_atual.json`, sem rede)."""
    atual = L.ler(cfg)
    da_usina, dono = defaultdict(list), defaultdict(list)
    for linha in (atual or {}).get("linhas") or []:
        if len(linha) >= 3 and linha[1] == L.FRACTTAL and linha[0]:
            da_usina[linha[0]].append({"chave": linha[2], "como": linha[3] if len(linha) > 3 else ""})
            dono[linha[2]].append(linha[0])
    nomes = [it["chave"] for it in ((atual or {}).get("fontes") or {}).get(L.FRACTTAL, []) if it.get("chave")]
    return nomes, da_usina, dono, atual is not None


def editor_dados(d: dict) -> dict:
    """O estado da usina como o JavaScript da tela edita: a cabine ganha a referência `c<id>` (a nova, `n<...>`), e o
    inversor aponta a cabine por ela e a chave pelo `supervisorio_id`."""
    return {"selo": E.selo(d),
            "chaves": [{"supervisorio_id": s["supervisorio_id"], "chave": s["usina_supervisorio"],
                        "usina_exibicao": s["usina_exibicao"], "principal": s["principal"],
                        "full_om": s["full_om"], "string_box": s["string_box"], "substitui_aba": s["substitui_aba"]}
                       for s in d["supervisorios"]],
            "cabines": [{"id": c["cabine_id"], "k": f"c{c['cabine_id']}", "nome": c["nome"],
                         "potencia_kwp": c["potencia_kwp"], "equipamento_id": c["equipamento_id"],
                         "codigo_fracttal": c["codigo_fracttal"]} for c in d["cabines"]],
            "inversores": [{"id": i["inversor_id"], "nome": i["nome"], "chave": i["supervisorio_id"],
                            "cabine": f"c{i['cabine_id']}" if i["cabine_id"] else None,
                            "equipamento_supervisorio": i["equipamento_supervisorio"], "potencia_kwp": i["potencia_kwp"],
                            "strings_esperadas_qtd": i["strings_esperadas_qtd"], "equipamento_id": i["equipamento_id"],
                            "codigo_fracttal": i["codigo_fracttal"]} for i in d["inversores"]]}


def _painel(u: dict, est: dict, aba: dict, fr_nomes, fr_dono, nome_usina: dict, info: dict) -> dict:
    """O que a usina aberta mostra: os 2 passos (as chaves do supervisório e os equipamentos) e as chaves da aba,
    ordenadas pelo parecido com a usina, sem nada escolhido."""
    d = E.da_usina(est, u["id"])
    # as chaves do supervisório: as da aba Equipamentos, as que têm motivo primeiro (o motivo vai escrito)
    dono_chave = {s["usina_supervisorio"]: s["usina_id"] for s in est["supervisorios"] if not s["excluido"]}
    minhas = {s["usina_supervisorio"] for s in d["supervisorios"]}
    sugeridas, todas = [], []
    for chave, g in aba["chaves"].items():
        if chave in minhas:
            continue
        dono = dono_chave.get(chave)
        porque = []          # sem o "mesmo nome do Fracttal na aba" (13/10/2026: a tela não fala de Fracttal)
        nota = max(_parecido(g["usina"], u["nome"]), _parecido(chave, u["nome"]))
        if nota >= 0.75:
            porque.append("nome parecido")
        item = {"chave": chave, "usina_aba": g["usina"], "fracttal": g["fracttal"], "porque": ", ".join(porque),
                "dono": nome_usina.get(dono, f"usina {dono}") if dono else "", "inversores": len(g["inversores"]),
                "cabines": len(g["cabines"]), "ufv_kwp": g["ufv_kwp"], "nota": nota}
        todas.append(item)
        if porque and not dono:
            sugeridas.append(item)
    sugeridas.sort(key=lambda x: (-x["nota"], E.norm(x["chave"])))
    todas.sort(key=lambda x: E.norm(x["chave"]))
    usa = defaultdict(int)
    for i in d["inversores"]:
        usa[i["supervisorio_id"]] += 1
    chaves = [dict(s, inversores=usa.get(s["supervisorio_id"], 0), na_aba=aba["chaves"].get(s["usina_supervisorio"]))
              for s in d["supervisorios"]]
    ref_aba = {s["usina_supervisorio"]: aba["chaves"][s["usina_supervisorio"]] for s in d["supervisorios"]
               if s["usina_supervisorio"] in aba["chaves"]}
    # a tabela de referência (sem mexer no que está guardado da aba: são os mesmos objetos da cópia de 10 minutos)
    ref_tab = [{"chave": ch, "usina": g["usina"], "fracttal": g["fracttal"], "ufv_kwp": g["ufv_kwp"], "cabines": g["cabines"],
                "inversores": len(g["inversores"]), "strings": sum(i["strings"] or 0 for i in g["inversores"]),
                "sem_strings": sum(1 for i in g["inversores"] if i["strings"] is None), "full_om": g["full_om"]}
               for ch, g in ref_aba.items()]
    return {"usina": u, "sugeridas": sugeridas[:10],
            "todas": todas, "chaves": chaves, "ref_aba": ref_aba, "ref_tab": ref_tab,
            "editor": dict(editor_dados(d), usina_id=u["id"], kwp_usina=u["kwp"], kwp_de=u["kwp_de"], aba=ref_aba,
                           nome_registro=u["nome"],
                           comparacao=E.comparar_usina(d, info.get(u["id"]), aba["chaves"]) if not aba.get("erro") else {},
                           ativos_url=url_for("torre_base.equipamentos_ativos", usina=u["id"]),
                           salvar_url=url_for("torre_base.equipamentos_salvar"))}


def contexto(srv, cfg, args) -> dict:
    reler = args.get("reler") == "1"
    est, aba = _leituras(forcar=reler)
    fr_nomes, fr_da_usina, fr_dono, fr_lido = _fracttal(cfg)
    usinas = _usinas(srv)
    nome_usina = {u["id"]: u["titulo"] for u in usinas}
    lista = []
    for u in usinas:
        r = E.resumo(E.da_usina(est, u["id"]))
        lista.append(dict(u, fracttal=fr_da_usina.get(u["id"], []), resumo=r,
                          pot=E.conferir_potencia(u["kwp"], r["kwp_inversores"] if r["inversores"] else r["kwp_cabines"])))
    lista.sort(key=lambda x: E.norm(x["titulo"]))
    q = str(args.get("q") or "").strip()[:120]
    filtro = args.get("filtro") if args.get("filtro") in dict(FILTROS) else ""
    # o cliente (13/10/2026, Levi: "tem que dar para filtrar o cliente!"): o do Registro mestre de cada usina, com
    # quantas usinas ele tem; SEM_CLIENTE = as usinas sem cliente na ficha. Só vale um cliente que está na lista
    por_cliente = Counter(x["cliente"] or "" for x in lista)
    clientes = sorted(((c or SEM_CLIENTE, c or "Sem cliente", n) for c, n in por_cliente.items()),
                      key=lambda c: (c[0] == SEM_CLIENTE, E.norm(c[1])))
    cliente = str(args.get("cliente") or "")
    if cliente not in {c[0] for c in clientes}:
        cliente = ""

    def passa(x):
        if cliente and (x["cliente"] or SEM_CLIENTE) != cliente:
            return False
        if q and E.norm(q) not in E.norm(f"{x['titulo']} {x['codigo']} {x['cidade'] or ''}"):
            return False
        r = x["resumo"]
        return {"": True, "sem_chave": not r["chaves"],
                "sem_inversores": not r["inversores"], "potencia": x["pot"] in ("perto", "nao_fecha")}[filtro]
    sel = D._id(args.get("usina"))
    aberta = next((x for x in lista if x["id"] == sel), None)
    info = _info_usinas(srv, cfg, usinas)
    painel = _painel(aberta, est, aba, fr_nomes, fr_dono, nome_usina, info) if aberta else None
    aviso = session.pop(_CHAVE_AVISO, None)
    pode_gravar = bool(cfg.get("GRIDCO_SQL_TOKEN")) and not est.get("erro")
    # o que a "Ligar pela aba Equipamentos" ligaria agora, e o que fica de fora com o motivo (13/10/2026)
    auto = E.proposta_pela_aba(aba["chaves"], L.ler(cfg), est, {u["id"] for u in usinas}) if not aba.get("erro") else \
        {"ligar": {}, "fora": [], "ja_ligadas": 0}
    auto = dict(auto, n_chaves=sum(len(v) for v in auto["ligar"].values()), n_usinas=len(auto["ligar"]))
    return {"lista": [x for x in lista if passa(x)], "total": len(lista), "q": q, "filtro": filtro, "filtros": FILTROS,
            "cliente": cliente, "clientes": clientes,
            "painel": painel, "aviso": aviso, "erro_livro": est.get("erro") or "", "livro_velho": est.get("velha", False),
            "erro_aba": aba.get("erro") or "", "aba_lida_em": _hora(aba.get("lido_em")), "fr_lido": fr_lido,
            "sem_token": not cfg.get("GRIDCO_SQL_TOKEN"), "pode_gravar": pode_gravar,
            "n_chave": sum(1 for x in lista if x["resumo"]["chaves"]),
            "n_inversores": sum(1 for x in lista if x["resumo"]["inversores"]),
            "n_strings": sum(x["resumo"]["strings"] for x in lista),
            "n_chaves_aba": len(aba["chaves"]),
            "n_no_lugar": sum(1 for s in est["supervisorios"] if s["substitui_aba"] and not s["excluido"]),
            "n_visao": len(est.get("visao") or []),
            "n_chaves_ligadas": sum(1 for c in aba["chaves"] if any(
                s["usina_supervisorio"] == c and not s["excluido"] for s in est["supervisorios"])),
            "auto": auto,
            "volta": {k: v for k, v in (("q", q), ("filtro", filtro), ("cliente", cliente)) if v}}


def _volta(usina=None, ancora: str = "") -> str:
    """A mesma tela, com a busca e o filtro de antes (só os conhecidos, nunca um endereço vindo do formulário)."""
    q = {}
    busca = (request.form.get("q") or "").strip()[:120]
    if busca:
        q["q"] = busca
    if request.form.get("filtro") in dict(FILTROS) and request.form.get("filtro"):
        q["filtro"] = request.form["filtro"]
    cliente = (request.form.get("cliente") or "").strip()[:120]
    if cliente:                                     # vai como parâmetro do endereço (url_for codifica); a tela confere
        q["cliente"] = cliente
    if usina:
        q["usina"] = usina
    return url_for("torre_base.equipamentos", **q) + (f"#{ancora}" if ancora else "")


def _responder(ok: bool, texto: str, status: int = 200, usina=None, ancora: str = ""):
    """Formulário: 303 de volta à usina, com o aviso guardado na sessão. Fetch com JSON: o aviso em JSON."""
    if "application/json" in (request.headers.get("Accept") or ""):
        r = jsonify(ok=ok, aviso=texto if ok else "", erro="" if ok else texto)
        r.status_code = status
        return r
    session[_CHAVE_AVISO] = {"tom": "ok" if ok else "critico", "texto": texto}
    return redirect(_volta(usina, ancora), code=303)


def _ligar_fracttal(srv):
    cfg, f = current_app.config, request.form
    uid = D._id(f.get("usina"))
    if _de_outro_site():
        return _responder(False, "Pedido de outro site: nada foi gravado.", 403, uid)
    acao, chave = f.get("acao"), " ".join(str(f.get("chave") or "").split())
    if uid not in {u["id"] for u in L._usinas(srv)}:
        return _responder(False, "Usina fora do Registro mestre: nada foi gravado.", 400)
    if acao not in ("ligar", "desligar") or not chave:
        return _responder(False, "Escolha o nome do Fracttal: nada foi gravado.", 400, uid, "passo-fracttal")
    nomes, _da_usina, _dono, lido = _fracttal(cfg)
    if not lido:
        return _responder(False, "As bases ainda não foram lidas: em Governança de dados > Ligações, use \"Ler as bases "
                                 "de novo\". Nada foi gravado.", 409, uid, "passo-fracttal")
    if chave not in nomes:
        return _responder(False, f"“{chave}” não está na lista do Fracttal lida pelas Ligações: nada foi gravado.", 400,
                          uid, "passo-fracttal")
    try:
        L.decidir(cfg, acao, L.FRACTTAL, chave=chave, usina_id=uid, quem=_quem())
    except L.DecisaoInvalida as ex:
        return _responder(False, str(ex), 400, uid, "passo-fracttal")
    L.reaplicar(cfg, srv)
    feito = "ligado a esta usina" if acao == "ligar" else "desligado desta usina"
    extra = _refazer_visao(srv, cfg)
    return _responder(True, f"“{chave}” {feito}. Vale já no Nexus; no banco, depois do Publicar no banco (Governança de "
                            f"dados > Ligações entre bases).{extra}", usina=uid, ancora="passo-fracttal")


def _refazer_visao(srv, cfg) -> str:
    """Refaz a visão no formato da aba (o nome no Fracttal ou a potência mudaram fora da estrutura). Grava só se mudou;
    falha aqui não desfaz o que já foi decidido, só avisa."""
    try:
        est = E.ler(*_banco(), forcar=True)
    except Exception as ex:      # noqa: BLE001 — sem banco: não há visão a refazer daqui
        log.error("Equipamentos: a estrutura não foi lida para refazer a visão (%s).", type(ex).__name__)
        return ""
    if not any(s["substitui_aba"] and not s["excluido"] for s in est["supervisorios"]) and not est.get("visao"):
        return ""
    try:
        r = E.republicar_visao(cfg, *_banco(), _info_usinas(srv, cfg), quem_email=_meu_email())
    except E.Recusada as ex:
        return f" A visão no formato da aba não foi refeita: {ex}"
    except Exception as ex:      # noqa: BLE001
        log.error("Equipamentos: a visão não foi refeita (%s: %s).", type(ex).__name__, ex)
        return f" A visão no formato da aba não foi refeita ({type(ex).__name__}): tente de novo pelo botão da tela."
    return f" A visão no formato da aba foi refeita ({r['visao_linhas']} linhas)." if r.get("visao_mudou") else ""


def _visao(srv):
    """POST do botão "Refazer a visão": o Registro mestre (nome, cliente, potência) mudou e nenhuma estrutura foi salva."""
    uid = D._id(request.form.get("usina"))
    if _de_outro_site():
        return _responder(False, "Pedido de outro site: nada foi gravado.", 403, uid)
    try:
        texto = _refazer_visao(srv, current_app.config).strip() or "A visão no formato da aba já estava em dia."
    except Exception as ex:      # noqa: BLE001 — banco fora
        return _responder(False, f"Não consegui ler a estrutura no banco ({type(ex).__name__}).", 503, uid)
    return _responder(not texto.startswith("A visão no formato da aba não"), texto, usina=uid)


def _chave(srv):
    cfg, f = current_app.config, request.form
    uid = D._id(f.get("usina"))
    if _de_outro_site():
        return _responder(False, "Pedido de outro site: nada foi gravado.", 403, uid)
    if uid not in {u["id"] for u in L._usinas(srv)}:
        return _responder(False, "Usina fora do Registro mestre: nada foi gravado.", 400)
    acao = f.get("acao")
    try:
        base, sessao = _banco()
        info = _info_usinas(srv, cfg)
        if acao == "ligar":
            chave = f.get("chave_nova") or f.get("chave") or ""
            grupo = E.aba_equipamentos(base, sessao)["chaves"].get(E.texto(chave))
            r = E.ligar_supervisorio(uid, chave, cfg, base, sessao, quem_email=_meu_email(),
                                     exibicao_aba=(grupo or {}).get("usina", ""), info=info)
            na_aba = grupo is not None
            texto = (f"Chave “{E.texto(chave)}” {'ligada' if r['novo'] else 'já estava ligada'} a esta usina."
                     + ("" if na_aba else " Ela não está na aba Equipamentos: confira se é o nome exato que o "
                                          "supervisório usa."))
        elif acao == "desligar":
            r = E.desligar_supervisorio(D._id(f.get("supervisorio_id")), uid, cfg, base, sessao,
                                        quem_email=_meu_email(), info=info)
            texto = (f"Chave “{r['chave']}” desligada."
                     + (f" {r['inversores_sem_chave']} inversor(es) ficaram sem chave: escolha outra para eles na "
                        "estrutura e salve." if r["inversores_sem_chave"] else "")
                     + (f" A chave da usina (UFV e cabines) passou a ser “{r['nova_principal']}”."
                        if r["nova_principal"] else ""))
        else:
            return _responder(False, "Ação desconhecida: nada foi gravado.", 400, uid)
    except E.Recusada as ex:
        return _responder(False, str(ex), 409, uid, "passo-chave")
    except Exception as ex:      # noqa: BLE001 — a gravação ou a conferência falhou: a tela diz, nada some calado
        log.error("Equipamentos: a chave não foi gravada (%s: %s).", type(ex).__name__, ex)
        return _responder(False, f"A gravação no banco falhou ({type(ex).__name__}). Recarregue: se a chave não mudou, "
                                 "tente de novo.", 500, uid, "passo-chave")
    return _responder(True, texto, usina=uid, ancora="passo-chave")


def _ligar_aba(srv):
    """POST do "Ligar pela aba Equipamentos" (13/10/2026): a proposta de agora (relida, nunca a da página) e uma gravação
    só. O que ficou de fora segue listado na tela, com o motivo."""
    cfg = current_app.config
    if _de_outro_site():
        return _responder(False, "Pedido de outro site: nada foi gravado.", 403)
    try:
        base, sessao = _banco()
        aba = E.aba_equipamentos(base, sessao)
        if aba.get("erro"):
            return _responder(False, f"Não consegui ler a aba Equipamentos ({aba['erro']}): nada foi gravado.", 503)
        est = E.ler(base, sessao, forcar=True)
        if est.get("erro"):
            return _responder(False, "Não consegui ler a estrutura no banco: nada foi gravado.", 503)
        usinas = _usinas(srv)
        proposta = E.proposta_pela_aba(aba["chaves"], L.ler(cfg), est, {u["id"] for u in usinas})
        if not proposta["ligar"]:
            return _responder(True, "Nada novo para ligar pela aba: as chaves que ligam sozinhas já estão ligadas.")
        r = E.ligar_pela_aba(proposta, aba["chaves"], cfg, base, sessao, quem_email=_meu_email(),
                             info=_info_usinas(srv, cfg, usinas))
    except E.Recusada as ex:
        return _responder(False, str(ex), 409)
    except Exception as ex:      # noqa: BLE001 — a gravação ou a conferência falhou: a tela diz, nada some calado
        log.error("Equipamentos: a ligação pela aba não foi gravada (%s: %s).", type(ex).__name__, ex)
        return _responder(False, f"A gravação no banco falhou ({type(ex).__name__}). Recarregue e veja o que ficou "
                                 "ligado antes de tentar de novo.", 500)
    strings = f"{r['strings']:,}".replace(",", ".")
    texto = (f"Ligado pela aba Equipamentos: {r['chaves']} chave(s) em {r['usinas']} usina(s), com {r['cabines']} "
             f"cabine(s), {r['inversores']} inversor(es) e {strings} strings esperadas, a potência e os nomes no "
             "supervisório da aba.")
    if r["puladas"]:
        texto += (f" {len(r['puladas'])} usina(s) já tinham estrutura gravada à mão e ficaram como estavam (use o "
                  "\"Trazer da aba\" nelas).")
    if r["avisos"]:
        texto += f" Avisos: {'; '.join(r['avisos'][:5])}."
    if proposta["fora"]:
        texto += f" {len(proposta['fora'])} chave(s) da aba não ligam sozinhas: a lista e o motivo estão na tela."
    return _responder(True, texto)


def _salvar(srv):
    cfg = current_app.config
    if _de_outro_site():
        return jsonify(ok=False, erro="Pedido de outro site: nada foi gravado."), 403
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return jsonify(ok=False, erro="Pedido sem os dados da estrutura: nada foi gravado."), 400
    uid = D._id(dados.get("usina_id"))
    if uid not in {u["id"] for u in L._usinas(srv)}:
        return jsonify(ok=False, erro="Usina fora do Registro mestre: nada foi gravado."), 400
    try:
        base, sessao = _banco()
        info = _info_usinas(srv, cfg)
        r = E.salvar_usina(uid, dados, str(dados.get("selo") or ""), cfg, base, sessao, quem_email=_meu_email(),
                           info=info)
    except E.Recusada as ex:
        return jsonify(ok=False, erro=str(ex)), 409
    except Exception as ex:      # noqa: BLE001
        log.error("Equipamentos: a estrutura da usina %s não foi gravada (%s: %s).", uid, type(ex).__name__, ex)
        return jsonify(ok=False, erro=f"A gravação no banco falhou ({type(ex).__name__}). Recarregue a página: se a "
                                      "estrutura não mudou, tente de novo."), 500
    n = r["mudancas"]
    aviso = "Nada mudou: a estrutura já estava assim." if not n else f"Salvo: {n} mudança{'s' if n > 1 else ''} gravada{'s' if n > 1 else ''} no banco."
    if r.get("visao_mudou"):
        aviso += f" A visão no formato da aba foi refeita ({r['visao_linhas']} linhas): os leitores pegam no próximo minuto."
    aba = E.aba_equipamentos(base, sessao)
    return jsonify(ok=True, aviso=aviso, resumo=r["resumo"], editor=editor_dados(r["usina"]),
                   comparacao=E.comparar_usina(r["usina"], info.get(uid), aba["chaves"]) if not aba.get("erro") else {})


def _ativos():
    uid = D._id(request.args.get("usina"))
    if not uid:
        return jsonify(ativos=[], erro="Usina não informada.")
    try:
        base, sessao = _banco()
    except Exception as ex:      # noqa: BLE001
        return jsonify(ativos=[], erro=f"{type(ex).__name__}: {str(ex)[:160]}")
    return jsonify(E.ativos_da_usina(base, sessao, uid))


# ── o de-para do tempo real (20/10/2026) ─────────────────────────────────────────────────────────────────────────────
# O "Modo de-para" do tempo real e a Base · De-para de equipamentos (telas da plataforma de Performance, abertas dentro do
# Nexus pela porta única, na MESMA origem) leem e gravam a estrutura por aqui. O livro é do Nexus: a troca integral sob
# a trava deste processo não aceita um segundo escritor, então a plataforma manda só o remendo e o Nexus calcula o kWp
# com o Registro mestre DESTA máquina (o mesmo que a tela Equipamentos mostra). Só administrador (`_tela`), só da mesma
# origem (`_de_outro_site`, inclusive o GET: é a rota que o fetch da página chama), JSON nos dois sentidos. O formato é o
# contrato com a plataforma: `nexus/cadastro/CLAUDE.md`, seção "De-para do tempo real".
def _recusa_json(motivo: str, status: int, usina_id=None, usina_supervisorio: str = ""):
    """`{ok: false, motivo}`; a recusa que é de UMA usina leva também `usina_id` e `usina_supervisorio` da culpada
    (20/10/2026): o pedido leva até 50 chaves de várias usinas, e a tela tira só a culpada do lote e reenvia o resto."""
    corpo = {"ok": False, "motivo": motivo}
    if usina_id is not None or usina_supervisorio:
        corpo.update(usina_id=usina_id, usina_supervisorio=usina_supervisorio or "")
    r = jsonify(**corpo)
    r.status_code = status
    return r


def _depara_estado(srv):
    """`GET /t/base/equipamentos/depara/estado?chaves=A|B` (ou `?usinas=93,108`): a usina inteira de cada chave, com o
    selo, o kWp do Registro mestre e de onde veio, as chaves, as cabines e os inversores. Relê o banco (nunca a cópia de
    1 minuto): o selo que sai daqui é o que o salvar confere, e a cópia de outra máquina daria 409 em seguida."""
    if _de_outro_site():
        return _recusa_json("Pedido de outro site.", 403)
    chaves = [E.texto(c) for c in str(request.args.get("chaves") or "").split("|") if E.texto(c)]
    pedidas = [x.strip() for x in str(request.args.get("usinas") or "").split(",") if x.strip()]
    if not chaves and not pedidas:
        return _recusa_json("Diga as chaves do supervisório (?chaves=A|B) ou as usinas (?usinas=93,108).", 400)
    if len(chaves) > E.MAX_DEPARA or len(pedidas) > E.MAX_DEPARA:
        return _recusa_json(f"No máximo {E.MAX_DEPARA} chaves e {E.MAX_DEPARA} usinas por pedido.", 400)
    try:
        base, sessao = _banco()
        est = E.ler(base, sessao, forcar=True)
    except Exception as ex:      # noqa: BLE001 — sem banco
        return _recusa_json(f"Não consegui ler a estrutura no banco ({type(ex).__name__}).", 503)
    if est.get("erro"):
        return _recusa_json("Não consegui ler a estrutura no banco: sem ela o selo não vale. Tente de novo.", 503)
    info = _info_usinas(srv, current_app.config)
    uids, sem = E.usinas_das_chaves(est, chaves, set(info))
    fora, ordem = [], []
    for x in pedidas:
        uid = D._id(x)
        if uid not in info:
            fora.append(x)
        elif uid not in ordem:
            ordem.append(uid)
    ordem += [u for u in uids if u not in ordem]
    # `gravando` (2ª revisão final, 21/10/2026): há gravação do livro em curso neste processo. Depois do estouro de 180 s
    # ou do 502/504 do proxy o pedido abandonado continua aqui, e o estado de agora ainda é o de antes: a tela espera o
    # `gravando` cair antes de concluir "está como antes" (sem isso ela guardava o selo velho e o 2º Salvar levava 409)
    return jsonify(ok=True, usinas=[E.estado_da_usina(est, uid, info[uid]) for uid in ordem], chaves_sem_usina=sem,
                   usinas_fora_do_registro=fora, gravando=E.gravando())


def _irmas_da_aba(aba_chaves: dict | None, cfg, info: dict) -> dict | None:
    """{usina_id: [chaves da aba]}: a que usina cada chave da aba pertence pela regra do "Ligar pela aba" (a Usina
    Fractall dela no de-para do Fracttal das Ligações, sem chutar), como se o livro estivesse vazio. O salvar recusa a
    usina que tem na aba uma chave assim fora do Nexus e fora do pedido (2ª revisão final, 21/10/2026: a Coração 2 salva
    sozinha dividia o Registro só pelas strings dela). Sem a aba ou sem as Ligações, None (não confere)."""
    if aba_chaves is None:
        return None
    try:
        return E.proposta_pela_aba(aba_chaves, L.ler(cfg), {"supervisorios": [], "cabines": [], "inversores": []},
                                   set(info))["ligar"]
    except Exception as ex:      # noqa: BLE001 — as Ligações ilegíveis não seguram o de-para; o log diz
        log.warning("Equipamentos: as Ligações não foram lidas para o de-para (%s: %s).", type(ex).__name__, ex)
        return None


def _pede_codigo(itens) -> bool:
    return any(isinstance(i, dict) and (i.get("codigo_fracttal") or i.get("cabine_codigo_fracttal"))
               for it in itens if isinstance(it, dict) and isinstance(it.get("inversores"), list)
               for i in it["inversores"])


def _depara_salvar(srv):
    """`POST /t/base/equipamentos/depara/salvar` (JSON `{itens: [...]}`): o remendo do modo de-para
    (`estrutura_usina.salvar_depara`). Recusa com `{ok: false, motivo}` e o HTTP da recusa (o selo velho, 409), mais
    `usina_id`/`usina_supervisorio` quando a recusa é de uma usina só. Os `avisos` vão como `{usina_id,
    usina_supervisorio, tipo, texto}` (`estrutura_usina.TIPOS_AVISO`) e a `marcacao` diz, chave a chave, se passou a
    valer no lugar da aba e, se não, por quê."""
    cfg = current_app.config
    if _de_outro_site():
        return _recusa_json("Pedido de outro site: nada foi gravado.", 403)
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict) or not isinstance(dados.get("itens"), list):
        return _recusa_json("Pedido sem os itens do de-para: nada foi gravado.", 400)
    try:
        with E.em_curso():                # o estado diz `gravando` enquanto este pedido roda (a tela espera)
            base, sessao = _banco()
            info = _info_usinas(srv, cfg)
            dim = E.dimensao(base, sessao)
            if _pede_codigo(dados["itens"]) and dim.get("erro") and not dim["por_codigo"]:
                return _recusa_json("Não consegui ler a dimensão de equipamento do Nexus: sem ela o código do Fracttal "
                                    "não se confere. Nada foi gravado.", 503)
            # a aba que não se leu (sem nenhuma cópia) vai como None, não como vazia: o salvar não marca a chave da UFV
            # e das cabines sem comparar e diz por quê; vazia diria "a chave não está na aba", que é outra coisa
            aba = E.aba_equipamentos(base, sessao)
            aba_chaves = aba.get("chaves") if aba.get("chaves") or not aba.get("erro") else None
            r = E.salvar_depara(dados["itens"], cfg, base, sessao, info=info, por_codigo=dim["por_codigo"],
                                aba_chaves=aba_chaves, quem_email=_meu_email(),
                                irmas_da_aba=_irmas_da_aba(aba_chaves, cfg, info))
    except E.Recusada as ex:
        return _recusa_json(str(ex), ex.status, ex.usina_id, ex.usina_supervisorio)
    except GravacaoRecusada as ex:
        return _recusa_json(f"O banco recusou a gravação ({ex}): nada foi gravado.", 409)
    except Exception as ex:      # noqa: BLE001 — a gravação ou a conferência falhou: a tela diz, nada some calado
        log.error("Equipamentos: o de-para do tempo real não foi gravado (%s: %s).", type(ex).__name__, ex)
        return _recusa_json(f"A gravação no banco falhou ({type(ex).__name__}). Leia o estado de novo: se nada mudou, "
                            "tente outra vez.", 500)
    return jsonify(ok=True, usinas=r["usinas"], kwp={str(k): v for k, v in r["kwp"].items()},
                   visao_mudou=r["visao_mudou"], erros=[], avisos=r["avisos"], mudancas=r["mudancas"],
                   cabines_excluidas=r["cabines_excluidas"], marcacao=r["marcacao"])


def registrar_equipamentos(bp) -> None:
    """Pendura a tela na torre Base (`/t/base/equipamentos`), vencendo o placeholder, e as ações dela."""
    @bp.route("/equipamentos")
    @_tela(TITULO)
    def equipamentos(srv):
        return render_template("cadastro/equipamentos.html", **contexto(srv, current_app.config, request.args))

    @bp.route("/equipamentos/fracttal", methods=["POST"])
    @_tela(TITULO)
    def equipamentos_fracttal(srv):
        return _ligar_fracttal(srv)

    @bp.route("/equipamentos/chave", methods=["POST"])
    @_tela(TITULO)
    def equipamentos_chave(srv):
        return _chave(srv)

    @bp.route("/equipamentos/visao", methods=["POST"])
    @_tela(TITULO)
    def equipamentos_visao(srv):
        return _visao(srv)

    @bp.route("/equipamentos/ligar-aba", methods=["POST"])
    @_tela(TITULO)
    def equipamentos_ligar_aba(srv):
        return _ligar_aba(srv)

    @bp.route("/equipamentos/salvar", methods=["POST"])
    @_tela(TITULO)
    def equipamentos_salvar(srv):
        return _salvar(srv)

    @bp.route("/equipamentos/ativos")
    @_tela(TITULO)
    def equipamentos_ativos(srv):  # noqa: ARG001 — o decorador garante administrador e cadastro
        return _ativos()

    @bp.route("/equipamentos/depara/estado")
    @_tela(TITULO)
    def equipamentos_depara_estado(srv):
        return _depara_estado(srv)

    @bp.route("/equipamentos/depara/salvar", methods=["POST"])
    @_tela(TITULO)
    def equipamentos_depara_salvar(srv):
        return _depara_salvar(srv)
