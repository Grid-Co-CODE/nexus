"""Ligações entre bases: os buracos do de_para à vista, e a correção feita ali mesmo.

Pedido do Levi (04/10/2026): "quero uma tela para fazer os de-para pelo Nexus, quero que esses buracos de ligação
fiquem expostos para que possamos corrigir". Desde 11/10/2026 é a SEÇÃO do fim de Base → Governança de dados ("essa
visão de Base > Ligações entre bases vire uma seção no final de Governança de dados"): o `contexto` monta o que a seção
mostra, a Governança o desenha, e o endereço antigo `/t/base/ligacoes` redireciona para lá. As ações (ler de novo,
decidir, publicar) seguem nestas rotas e voltam à seção. A lógica mora em ligacoes.py.
"""
import re
from datetime import datetime
from urllib.parse import urlencode

from flask import current_app, redirect, request

from . import banco as B
from . import ligacoes as L
from ..auth.origem import de_outro_site as _de_outro_site
from ..prefixo import na_raiz
from .telas import _quem, _tela

ABAS = (("buracos", "Buracos"), ("por-nome", "Ligado por nome"), ("fora", "Usinas fora"), ("decisoes", "Decisões"))
# o botão geral (12/11/2026): o `alvo_sistema` dele, e a confirmação que só ele manda (um formulário de uma base sem a
# base não vira "todas": vazio continua erro)
TODAS, CONFIRMA_TODAS = "todas", "todas as bases"
MINIMO_GERAL = 2         # Levi: "quando tiver mais de uma chave com nome no cadastro"
PULOS = (("varias", "com mais de uma sugestão"), ("abaixo", "com sugestão abaixo de 100%"), ("sem", "sem sugestão"),
         ("repetida", "com a mesma usina sugerida a duas chaves"))


def _int(v):
    m = re.match(r"\s*(\d+)", str(v or ""))
    return int(m.group(1)) if m else None


def _hora(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return ""


def _volta(**k):
    q = {x: request.form.get(x, "") for x in ("aba", "sistema", "ver", "trocas") if request.form.get(x)}
    q.update({x: y for x, y in k.items() if y})
    return redirect(na_raiz("/t/base/governanca") + "?" + urlencode(q) + "#ligacoes", code=303)


def _base(cfg) -> str:
    return (cfg.get("GRIDCO_DB_API") or L.BASE_API).rstrip("/")


def _usinas_txt(ids) -> str:
    ids = [str(i) for i in ids]
    return ("usina " + ids[0]) if len(ids) == 1 else ("usinas " + ", ".join(ids[:-1]) + " e " + ids[-1])


def _recusa_do_aceite(lista: list[dict]) -> str:
    """O aviso da publicação que não saiu por causa da lista do aceite: quantas de cada tipo e as 5 primeiras (a lista
    inteira abre logo abaixo dele)."""
    mudam, novas = [x for x in lista if x["de"]], [x for x in lista if not x["de"]]
    partes = []
    if mudam:
        partes.append(f"{len(mudam)} chave{'s trocariam' if len(mudam) > 1 else ' trocaria'} de usina")
    if novas:
        partes.append(f"{len(novas)} chave{'s novas ligariam' if len(novas) > 1 else ' nova ligaria'} à usina de outro "
                      "cliente")

    def uma(x):
        if x["de"]:
            return (f"{x['sistema']}: {x['chave_externa']} (no banco, {_usinas_txt(x['de'])}; aqui, "
                    f"{_usinas_txt(x['para'])}, por {x['casou_por']})")
        return (f"{x['sistema']}: {x['chave_externa']} (a chave diz {x['cliente_da_chave']}; aqui, "
                f"{_usinas_txt(x['para'])}, do cliente {x['cliente_da_usina']}, por {x['casou_por']})")
    n = len(lista)
    quais = "; ".join(uma(x) for x in lista[:5]) + (f"; e mais {n - 5}" if n > 5 else "")
    return (f"Não publiquei: {' e '.join(partes)} sem ninguém ter decidido: {quais}. Na lista abaixo, decida cada uma "
            "ou publique com estas ligações.")


def _trocas_da_tela(srv, cfg, atual, regras, usinas) -> dict:
    """A lista do aceite da publicação (`banco.a_aceitar`: as chaves que trocariam de usina e as ligações novas que
    cruzam cliente), com o título de cada usina e a marca do conjunto para o "Publicar com estas ligações". Lê o de-para
    do BANCO, por isso só roda quando o endereço traz `trocas=1` (a recusa da publicação o põe, e os botões da lista o
    devolvem): a Governança de toda visita não lê o banco. Em cada linha, o botão do lado seguro:
    - `manter` = a usina do "Manter a do banco" (a decisão de ligar): só quando o banco liga a chave a UMA usina que
      ainda está no cadastro e a chave passa pelas decisões da tela (a do BD_Operações é o ID do BD da ficha: a decisão
      não a alcança, e o botão gravaria uma decisão sem efeito);
    - `nao_ligar` = a usina do "Não ligar" da ligação nova que cruza cliente (a decisão de desligar: a chave fica sem
      usina, à espera de alguém ligar à certa): só quando a publicação a liga a UMA usina.
    Sem botão, `sem_manter` diz por quê. A lista é contada nas linhas que esta máquina calculou, como na rota
    (`ligacoes_publicar`): mesma função, mesmo conjunto, mesma marca."""
    try:
        brutas = B.a_aceitar(srv, atual["fontes"], B.de_para(srv, atual["fontes"], regras), B.ler_de_para(_base(cfg)))
    except Exception as ex:          # noqa: BLE001 — o banco fora não derruba a Governança: a tela diz
        return {"erro": "A lista das chaves que trocariam de usina não abriu: não consegui ler o de-para do banco "
                        f"({type(ex).__name__}). Tente de novo em instantes."}
    titulo = {u["id"]: u["titulo"] for u in usinas}
    lista = []
    for x in brutas:
        manter = nao_ligar = None
        if not x["de"]:                         # ligação nova que cruza cliente
            sem = "" if len(x["para"]) == 1 else "a chave ligaria a mais de uma usina"
            nao_ligar = None if sem else x["para"][0]
        else:
            sem = ("vem do ID do BD da ficha: corrija no Registro mestre" if x["casou_por"] == B.COMO_ID_BD
                   else "o banco liga a mais de uma usina" if len(x["de"]) > 1
                   else "" if x["de"][0] in titulo else "a usina do banco saiu do cadastro")
            manter = None if sem else x["de"][0]
        lista.append(dict(x, de=[{"id": i, "titulo": titulo.get(i)} for i in x["de"]],
                          para=[{"id": i, "titulo": titulo.get(i)} for i in x["para"]],
                          manter=manter, nao_ligar=nao_ligar, sem_manter=sem))
    return {"lista": lista, "assinatura": B.assinatura_das_trocas(brutas)}


def contexto(srv, cfg, args) -> dict:
    """O que a seção Ligações entre bases da Governança mostra (antes, a tela inteira)."""
    aba = args.get("aba") if args.get("aba") in dict(ABAS) else "buracos"
    sistema = args.get("sistema") or ""
    atual, regras = L.ler(cfg), L.carregar_regras(cfg)
    p = L.panorama(srv, atual, regras)
    trocas = _trocas_da_tela(srv, cfg, atual, regras, p["usinas"]) if args.get("trocas") and atual else {}

    def filtra(xs):
        return [x for x in xs if not sistema or x["sistema"] == sistema]
    fora = [(s, sum(len(us) for _, us in g), g) for s, g in p["ausencias"].items()
            if (not sistema or s == sistema) and g]
    contagem = {"buracos": len(filtra(p["buracos"])), "por-nome": len(filtra(p["por_nome"])),
                "fora": sum(t for _, t, _ in fora), "decisoes": len(p["decisoes"])}
    lote = L.sugestoes_de_100(p["buracos"], sistema) if sistema else {"ligar": []}
    # o botão geral vale para todas as bases, com ou sem uma escolhida
    n_geral = len(L.sugestoes_de_100_todas(p["buracos"])["ligar"])
    return dict(p=p, aba=aba, n_sugestoes_100=len(lote["ligar"]), n_nome_cadastro=n_geral, minimo_geral=MINIMO_GERAL,
                todas=TODAS, confirma_todas=CONFIRMA_TODAS, abas=ABAS, sistema=sistema, buracos=filtra(p["buracos"]), por_nome=filtra(p["por_nome"]),
                fora=fora, contagem=contagem, gerado_em=_hora(p["gerado_em"]), hora=_hora, ok=args.get("ok"),
                erro=args.get("erro"), pode_publicar=bool(cfg.get("GRIDCO_SQL_TOKEN")), sem_par=B.SEM_PAR,
                ver_trocas=bool(args.get("trocas")), trocas=trocas.get("lista") or [],
                trocas_assinatura=trocas.get("assinatura") or "", trocas_erro=trocas.get("erro"))


def registrar_ligacoes(bp):
    @bp.route("/ligacoes")
    def ligacoes():
        # a tela virou a seção do fim da Governança (11/10/2026): favorito e link antigo caem nela, com os filtros
        q = request.query_string.decode("utf-8", "replace")
        return redirect(na_raiz("/t/base/governanca") + ("?" + q if q else "") + "#ligacoes", code=302)

    @bp.route("/ligacoes/recalcular", methods=["POST"])
    @_tela("Ligações entre bases")
    def ligacoes_recalcular(srv):
        try:
            L.calcular(current_app.config, srv)
        except Exception as ex:          # noqa: BLE001 — base fora do ar: a tela diz, não quebra
            return _volta(erro=f"Não consegui ler as bases: {type(ex).__name__}: {str(ex)[:160]}")
        return _volta(ok="Bases lidas de novo.")

    @bp.route("/ligacoes/decidir", methods=["POST"])
    @_tela("Ligações entre bases")
    def ligacoes_decidir(srv):
        cfg, f = current_app.config, request.form
        try:
            L.decidir(cfg, f.get("acao", ""), f.get("alvo_sistema", ""), chave=f.get("chave") or None,
                      usina_id=_int(f.get("usina")), cliente_id=_int(f.get("cliente_id")),
                      motivo=f.get("motivo", ""), quem=_quem())
        except L.DecisaoInvalida as ex:
            return _volta(erro=str(ex))
        L.reaplicar(cfg, srv)
        return _volta(ok="Decisão gravada e aplicada.")

    @bp.route("/ligacoes/aceitar-sugestoes", methods=["POST"])
    @_tela("Ligações entre bases")
    def ligacoes_aceitar_sugestoes(srv):
        """Liga de uma vez os buracos com UMA sugestão de 100%: numa base (o botão da base) ou em todas (o botão geral do
        alto, `alvo_sistema` = "todas" com a confirmação dele; 12/11/2026). A regra é a mesma função que conta o N do
        botão (`L.sugestoes_de_100` e `L.sugestoes_de_100_todas`). Grava pelo `L.decidir` uma a uma e reaplica UMA vez no
        fim. Não publica: o "Publicar no banco" segue sendo o passo do administrador."""
        if _de_outro_site():
            return "Pedido de outro site: nada foi ligado.", 403
        cfg, f = current_app.config, request.form
        sistema = f.get("alvo_sistema", "")
        todas = sistema == TODAS
        if todas and f.get("confirmar") != CONFIRMA_TODAS:
            return _volta(erro="O botão geral liga todas as bases e pede a confirmação dele: nada foi ligado.")
        if not sistema:
            return _volta(erro="Escolha uma base: o botão vale para uma base por vez.")
        p = L.panorama(srv, L.ler(cfg), L.carregar_regras(cfg))
        if todas:
            lote = L.sugestoes_de_100_todas(p["buracos"])
            itens, por_base = lote["ligar"], lote["por_base"]
            motivo = "nome igual ao do cadastro, ligado em lote"
        else:
            lote = L.sugestoes_de_100(p["buracos"], sistema)
            itens, por_base = [(sistema, c, u) for c, u in lote["ligar"]], {sistema: lote["pulos"]}
            motivo = "sugestão de 100% aceita em lote"
        feitas, recusadas = 0, []
        for alvo, chave, usina_id in itens:
            try:                 # uma recusa não para o lote nem deixa as outras sem o reaplicar do fim
                L.decidir(cfg, "ligar", alvo, chave=chave, usina_id=usina_id, motivo=motivo, quem=_quem())
                feitas += 1
            except L.DecisaoInvalida as ex:
                recusadas.append(f"{chave} ({str(ex)[:80]})")
        if feitas:
            L.reaplicar(cfg, srv)
        n = feitas
        feitas_txt = f"{n} ligaç{'ões feitas' if n != 1 else 'ão feita'}"
        if todas:
            msg = f"{feitas_txt}; publique no banco para valer."
            ficaram = sum(sum(pu.values()) for pu in por_base.values())
            if ficaram:
                por = "; ".join(f"{base}: " + ", ".join(f"{pu[k]} {txt}" for k, txt in PULOS if pu[k])
                                for base, pu in por_base.items() if any(pu.values()))
                msg += f" Ficaram {ficaram} para você decidir ({por})."
        else:
            pu = por_base[sistema]
            msg = f"{feitas_txt} (as sugestões de 100% sem outra parecida). Publique no banco para valer."
            por = [f"{pu[k]} {txt}" for k, txt in PULOS if pu[k]]
            if por:
                msg += f" Ficaram {sum(pu.values())} para você decidir: " + ", ".join(por) + "."
        if recusadas:
            msg += f" {len(recusadas)} recusada(s) pelo de-para: " + "; ".join(recusadas[:5]) + "."
        return _volta(ok=msg)

    @bp.route("/ligacoes/publicar", methods=["POST"])
    @_tela("Ligações entre bases")
    def ligacoes_publicar(srv):
        # o aceite das trocas é passo de risco, e a marca não é segredo (calcula-se com o de-para do banco, de leitura
        # aberta): o pedido tem de vir de uma página deste Nexus, como no "Ligar as sugestões" (revisão de 12/11/2026)
        if _de_outro_site():
            return "Pedido de outro site: nada foi publicado.", 403
        cfg = current_app.config
        atual = L.ler(cfg)
        if not atual:
            return _volta(erro="Leia as bases antes de publicar.")
        if not cfg.get("GRIDCO_SQL_TOKEN"):
            return _volta(erro="Falta o GRIDCO_SQL_TOKEN no .env do Nexus.")
        base = _base(cfg)
        try:
            t = B.montar(srv, srv.cofre, atual["fontes"], B.ler_anteriores(base), L.carregar_regras(cfg))
        except Exception as ex:          # noqa: BLE001
            return _volta(erro=f"O banco recusou: {type(ex).__name__}: {str(ex)[:160]}")
        # O arquivo de cadastro e as bases lidas são DESTA máquina, e o de-para do banco não é só dela (10/11/2026; o caso em
        # banco.perdas_de_para). Quatro regras (`banco.conferir_com_o_banco`, a mesma conta da ferramenta do PC):
        # 1. a ligação de chave que esta máquina NÃO leu volta ao banco como estava (12/11/2026, banco.ligacoes_que_nao_li):
        #    o que a máquina não leu, ela não apaga;
        # 2. a chave que ela LEU e deixaria sem usina é perda de verdade: não publica, e a tela diz qual é;
        # 3. a chave que TROCARIA de usina por regra automática (12/11/2026, banco.chaves_que_trocariam) não publica sem o
        #    aceite da lista que a tela mostrou: a chave de um cliente tinha ido para a usina de outro, calada. Contada
        #    nas linhas que ESTA máquina calculou, antes de juntar as mantidas: é o mesmo conjunto da tela
        #    (`_trocas_da_tela`), e a chave que a máquina não leu não é troca dela;
        # 4. a ligação NOVA que uma regra automática faria entre a chave que diz um cliente e a usina de outro
        #    (13/11/2026, ligacoes.novas_que_cruzam_cliente) entra na mesma lista do aceite: é o mesmo erro do item 3
        #    numa chave que o banco ainda não tinha.
        try:
            no_banco = B.ler_de_para(base)
        except Exception as ex:          # noqa: BLE001
            return _volta(erro=f"Não publiquei: não consegui ler o de-para do banco para comparar "
                               f"({type(ex).__name__}). Tente de novo em instantes.")
        conferido = B.conferir_com_o_banco(t, no_banco, srv, atual["fontes"])
        mantidas, perdidas, trocas = conferido["mantidas"], conferido["perdidas"], conferido["trocas"]
        if perdidas:
            n = len(perdidas)
            por = ", ".join(f"{s}: {q}" for s, q in B.perdas_de_para(t["de_para"][1], no_banco).most_common())
            quais = "; ".join(f"{d.get('sistema')}: {d.get('chave_externa')} (usina {B._inteiro(d.get('usina_id'))})"
                              for d in perdidas[:12]) + (f"; e mais {n - 12}" if n > 12 else "")
            return _volta(erro=f"Não publiquei: a publicação perderia {n} ligaç{'ões' if n > 1 else 'ão'} do de-para "
                               f"que o banco tem ({por}): {quais}. Esta máquina leu "
                               f"{'essas chaves e as' if n > 1 else 'essa chave e a'} deixaria sem usina: ligue nas "
                               f"Ligações (ou use \"Ler as bases de novo\", se as bases estiverem velhas) e publique de novo.")
        if trocas and request.form.get("aceitar_trocas") != B.assinatura_das_trocas(trocas):
            return _volta(erro=_recusa_do_aceite(trocas), trocas="1")
        try:
            r = B.sincronizar(B.xlsx_bytes(t), base=base, token=cfg["GRIDCO_SQL_TOKEN"])
        except Exception as ex:          # noqa: BLE001
            return _volta(erro=f"O banco recusou: {type(ex).__name__}: {str(ex)[:160]}")
        m = len(mantidas)
        n = sum(1 for x in trocas if x["de"])               # as que trocaram de usina
        c = len(trocas) - n                                 # as novas que cruzam cliente
        ficou = ("" if not m else " 1 ligação de chave que esta máquina não leu ficou como estava no banco." if m == 1
                 else f" {m} ligações de chaves que esta máquina não leu ficaram como estavam no banco.")
        trocou = "" if not n else "1 chave trocou de usina" if n == 1 else f"{n} chaves trocaram de usina"
        ligou = ("" if not c else "1 chave nova foi ligada à usina de outro cliente" if c == 1
                 else f"{c} chaves novas foram ligadas à usina de outro cliente")
        aceite = f" {' e '.join(x for x in (trocou, ligou) if x)}, com o seu aceite." if trocas else ""
        return _volta(ok=f"Publicado no banco: {r.get('inserted', 0)} linhas novas, {r.get('updated', 0)} alteradas."
                         f"{ficou}{aceite}")
