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
    q = {x: request.form.get(x, "") for x in ("aba", "sistema", "ver") if request.form.get(x)}
    q.update({x: y for x, y in k.items() if y})
    return redirect(na_raiz("/t/base/governanca") + "?" + urlencode(q) + "#ligacoes", code=303)


def contexto(srv, cfg, args) -> dict:
    """O que a seção Ligações entre bases da Governança mostra (antes, a tela inteira)."""
    aba = args.get("aba") if args.get("aba") in dict(ABAS) else "buracos"
    sistema = args.get("sistema") or ""
    p = L.panorama(srv, L.ler(cfg), L.carregar_regras(cfg))

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
                erro=args.get("erro"), pode_publicar=bool(cfg.get("GRIDCO_SQL_TOKEN")), sem_par=B.SEM_PAR)


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
        cfg = current_app.config
        atual = L.ler(cfg)
        if not atual:
            return _volta(erro="Leia as bases antes de publicar.")
        if not cfg.get("GRIDCO_SQL_TOKEN"):
            return _volta(erro="Falta o GRIDCO_SQL_TOKEN no .env do Nexus.")
        base = (cfg.get("GRIDCO_DB_API") or L.BASE_API).rstrip("/")
        try:
            t = B.montar(srv, srv.cofre, atual["fontes"], B.ler_anteriores(base), L.carregar_regras(cfg))
        except Exception as ex:          # noqa: BLE001
            return _volta(erro=f"O banco recusou: {type(ex).__name__}: {str(ex)[:160]}")
        # O arquivo de cadastro e as bases lidas são DESTA máquina, e o de-para do banco não é só dela (10/11/2026; o caso em
        # banco.perdas_de_para). Duas regras, nesta ordem:
        # 1. a ligação de chave que esta máquina NÃO leu volta ao banco como estava (12/11/2026, banco.ligacoes_que_nao_li):
        #    o que a máquina não leu, ela não apaga;
        # 2. a chave que ela LEU e deixaria sem usina é perda de verdade: não publica, e a tela diz qual é.
        try:
            no_banco = B.ler_de_para(base)
        except Exception as ex:          # noqa: BLE001
            return _volta(erro=f"Não publiquei: não consegui ler o de-para do banco para comparar "
                               f"({type(ex).__name__}). Tente de novo em instantes.")
        mantidas = B.ligacoes_que_nao_li(t["de_para"][1], no_banco, B.ids_das_usinas(t))
        if mantidas:
            B.juntar_ao_de_para(t, mantidas)
        perdidas = B.chaves_que_perderia(t["de_para"][1], no_banco)
        if perdidas:
            n = len(perdidas)
            por = ", ".join(f"{s}: {q}" for s, q in B.perdas_de_para(t["de_para"][1], no_banco).most_common())
            quais = "; ".join(f"{d.get('sistema')}: {d.get('chave_externa')} (usina {B._inteiro(d.get('usina_id'))})"
                              for d in perdidas[:12]) + (f"; e mais {n - 12}" if n > 12 else "")
            return _volta(erro=f"Não publiquei: a publicação perderia {n} ligaç{'ões' if n > 1 else 'ão'} do de-para "
                               f"que o banco tem ({por}): {quais}. Esta máquina leu "
                               f"{'essas chaves e as' if n > 1 else 'essa chave e a'} deixaria sem usina: ligue nas "
                               f"Ligações (ou use \"Ler as bases de novo\", se as bases estiverem velhas) e publique de novo.")
        try:
            r = B.sincronizar(B.xlsx_bytes(t), base=base, token=cfg["GRIDCO_SQL_TOKEN"])
        except Exception as ex:          # noqa: BLE001
            return _volta(erro=f"O banco recusou: {type(ex).__name__}: {str(ex)[:160]}")
        m = len(mantidas)
        ficou = ("" if not m else " 1 ligação de chave que esta máquina não leu ficou como estava no banco." if m == 1
                 else f" {m} ligações de chaves que esta máquina não leu ficaram como estavam no banco.")
        return _volta(ok=f"Publicado no banco: {r.get('inserted', 0)} linhas novas, {r.get('updated', 0)} alteradas.{ficou}")
