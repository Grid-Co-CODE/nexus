"""As telas dos relatórios do PCM na Central de emissão (torre Relatórios), no desenho da tela Relatórios do painel do PCM:
"1 · Tipo", "2 · Período e recorte" (dia ou semana, cliente, cluster ou supervisor), Gerar, a folha ao lado com
"Imprimir / PDF" e "Abrir em nova aba", e os emitidos automaticamente.

- `/t/relatorios/pcm-<tipo>`: a tela. É leve (a pré-carga a abre a cada 2 min para quem é do setor): lê só o
  banco_dados.json (cópia de 5 min) para as semanas e o recorte, e nunca monta a folha sozinha;
- `/t/relatorios/pcm-<tipo>/folha`: a folha sob demanda, com o dado de agora (o painel montava no navegador; aqui é o
  servidor, com as mesmas contas). Não grava nada;
- `/t/relatorios/pcm-<tipo>/emitido/<ref>`: uma folha guardada pela emissão automática (`agenda.py`).
As sub-rotas seguem a marca da tela no portão de setor (`setor_telas.pode`).
"""
from datetime import date, datetime, timedelta
from functools import partial
from urllib.parse import urlencode

from flask import Response, abort, current_app, render_template, request

from ...auth import setor_telas
from .. import fonte
from . import TIPOS, arquivo, dados, emitir
from .alerta import semana_nova
from .regras import BRT, CSS_TELA, DIAS_PT, h


def _hoje() -> date:
    return datetime.now(BRT).date()


def _ref_padrao(tipo, bd) -> str:
    """O que a tela já traz escolhido: o diário de ontem, a tarde de hoje, o fechamento da semana ativa e o alerta da
    semana publicada mais nova (a que o automático confere)."""
    if tipo.id == "diario":
        return (_hoje() - timedelta(days=1)).isoformat()
    if tipo.id == "tarde":
        return _hoje().isoformat()
    semanas = [w for w, _ in dados.semanas(bd)]
    if tipo.id == "alerta":
        nova = semana_nova(bd)[0]
        if nova:
            return nova
    return bd.get("semana_ativa") or (semanas[0] if semanas else "")


def _ref_pedida(tipo, args, bd) -> str:
    if tipo.por == "dia":
        try:
            return date.fromisoformat(str(args.get("dia") or "")[:10]).isoformat()
        except ValueError:
            return _ref_padrao(tipo, bd)
    semana = str(args.get("semana") or "")
    return semana if semana in {w for w, _ in dados.semanas(bd)} else _ref_padrao(tipo, bd)


def _rotulo(tipo, ref, bd) -> str:
    if tipo.por == "dia":
        try:
            d = date.fromisoformat(ref)
            return f"{DIAS_PT[d.weekday()][:3].lower()} {d:%d/%m}"
        except ValueError:
            return ref
    return dict(dados.semanas(bd)).get(ref) or f"Semana {ref[-2:]}"


def _com_margem_de_tela(html: str) -> str:
    return html.replace("</style>", CSS_TELA + "</style>", 1)


def _folha_simples(titulo: str, texto: str, status: int = 200) -> Response:
    corpo = (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>{h(titulo)}</title></head>'
             f'<body style="font-family:Segoe UI,Arial,sans-serif;font-size:11pt;padding:12mm"><p>{h(texto)}</p>'
             f'</body></html>')
    return Response(corpo, status=status, mimetype="text/html", headers={"Cache-Control": "no-store"})


def pagina(torre, tipo_id: str):
    tipo = TIPOS[tipo_id]
    cfg = current_app.config
    leitura = fonte.ler(cfg)
    bd = leitura.dados or {}
    cliente = (request.args.get("cliente") or "").strip()[:120]
    grupo = (request.args.get("grupo") or "").strip()[:120]
    ref = _ref_pedida(tipo, request.args, bd) if bd or tipo.por == "dia" else ""
    base = f"/t/{torre.id}/{tipo.tela_id}"
    folha_url = ""
    if request.args.get("gerar") == "1" and ref:
        q = {("dia" if tipo.por == "dia" else "semana"): ref}
        q.update({k: v for k, v in (("cliente", cliente), ("grupo", grupo)) if v})
        folha_url = f"{base}/folha?{urlencode(q)}"
    liberadas = setor_telas.liberadas_do_menu()
    tipos = [t for t in TIPOS.values()
             if liberadas is None or setor_telas.chave(torre.id, t.tela_id) in liberadas]
    try:
        guardados = arquivo.listar(cfg, [tipo.id])
    except RuntimeError:            # teste sem pasta de dados: a lista fica vazia
        guardados = []
    emitidos = [{"ref": e["ref"], "rotulo": _rotulo(tipo, e["ref"], bd),
                 "quando": e["gerado"].strftime("%d/%m %H:%M") if e["gerado"] else "",
                 "url": f"{base}/emitido/{e['ref']}"} for e in guardados]
    return render_template("relatorios/pcm.html", torre=torre, tela=torre.tela(tipo.tela_id), tipo=tipo, tipos=tipos,
                           base=base, ref=ref, cliente=cliente, grupo=grupo, semanas=dados.semanas(bd),
                           opcoes=dados.opcoes(bd, cliente, grupo), folha_url=folha_url, emitidos=emitidos,
                           rotulo_ref=_rotulo(tipo, ref, bd) if ref else "",
                           erro_fonte="" if bd else (leitura.erro or "sem dado"))


def folha(tipo_id: str):
    tipo = TIPOS[tipo_id]
    cfg = current_app.config
    entradas, lidos = dados.carregar(cfg)
    if entradas is None:
        falta = "; ".join(f"{'banco_dados.json' if k == 'bd' else 'gestao_pcm.json'}: {v.erro}"
                          for k, v in lidos.items() if k in ("bd", "gestao") and v.dados is None)
        return _folha_simples(tipo.nome, f"Não consegui ler os dados do PCM agora ({falta}). Tente de novo em instantes.",
                              503)
    ref = _ref_pedida(tipo, request.args, entradas["bd"])
    cliente = (request.args.get("cliente") or "").strip()[:120]
    grupo = (request.args.get("grupo") or "").strip()[:120]
    resultado = emitir(entradas, tipo.id, ref, datetime.now(BRT), cliente, grupo)
    if resultado is None:
        return _folha_simples(tipo.nome, f"O banco de dados do PCM não tem a semana {ref}.", 404)
    return Response(_com_margem_de_tela(resultado["html"]), mimetype="text/html", headers={"Cache-Control": "no-store"})


def emitido(tipo_id: str, ref: str):
    if not arquivo.ref_valida(tipo_id, ref):
        abort(404)
    try:
        html = arquivo.ler(current_app.config, tipo_id, ref)
    except RuntimeError:            # teste sem pasta de dados
        html = None
    if html is None:
        abort(404)
    return Response(_com_margem_de_tela(html), mimetype="text/html")


def registrar(bp, torre) -> None:
    """As rotas das quatro telas na torre Relatórios (vencem o placeholder `/<tela_id>` da torre)."""
    for tipo in TIPOS.values():
        bp.add_url_rule(f"/{tipo.tela_id}", endpoint=f"{tipo.tela_id}", view_func=partial(pagina, torre, tipo.id))
        bp.add_url_rule(f"/{tipo.tela_id}/folha", endpoint=f"{tipo.tela_id}_folha", view_func=partial(folha, tipo.id))
        bp.add_url_rule(f"/{tipo.tela_id}/emitido/<ref>", endpoint=f"{tipo.tela_id}_emitido",
                        view_func=partial(emitido, tipo.id))
