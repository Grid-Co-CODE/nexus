# os_creator/os_web/rotas_investigar.py
"""O "Investigar ativo" (26/10/2026): o histórico de OS de UM ativo, para a janela por cima do Tempo real.

Levi, 26/10/2026: "Gostaria de poder clicar com botão direito do mouse em cima do inversor e ter a opção 'Investigar
ativo'. Vai aproveitar o pré carregamento de histórico de OS do OS Creator filtrando esse ativo, deve mostrar o período
filtrado e eu devo conseguir fazer novos filtros e pesquisas pela visão. Vai abrir uma sub janela sobrepondo a tela dando
um blur de fundo que nem quando vamos criar OS."

`/os/historico/ativo?codigo=<código do Fracttal>&usina=<usina>&nome=<inversor>[&de=&ate=]`. A plataforma abre com
`janela=1` (a ponte do Nexus tira o topo, como no Criar OS). O que vai ao Fracttal: NADA além do que o Histórico já
faria — a lista é a de "Todos" dos últimos 30 dias, a mesma da Visão COS (`rotas.ler_lista`, guardada para todos); o
período dentro dela é recortado aqui; fora dela, a lista daquele período (a régua do Histórico). Status, tipo de tarefa,
a busca e o "este ativo × a usina inteira" são locais (no navegador, sobre as linhas da usina). As regras:
`investigar_web.py`."""
from __future__ import annotations

import datetime as dt

from flask import Blueprint, render_template, request

import api

from . import investigar_web as IW
from . import rotas as R

bp = Blueprint("os_web_investigar", __name__, url_prefix="/os")

# as colunas da janela: as do Histórico Geral sem cliente e usina (a janela já diz qual é) e com o tipo de tarefa, que é
# o que se procura ao investigar um ativo (o religamento, a corretiva, a preventiva)
COLS = [("Nº", "folio"), ("Tipo de tarefa", "tipo_tarefa"), ("Ativo", "ativo"), ("Descrição", "descricao"),
        ("Criação", "data"), ("Evento", "event_date"), ("Fim", "data_fim"), ("Status", "status"),
        ("Etiqueta", "etiqueta")]


def _catalogo() -> list:
    """O catálogo de ativos que já está no disco, sem cópia e sem ir ao Fracttal (vencido também serve: o código de um
    inversor não muda de um dia para o outro). Sem catálogo, a janela diz que não achou o ativo."""
    try:
        c = api._catalogo_cru() or {}
    except Exception:                    # noqa: BLE001 — sem catálogo, o resolver devolve o aviso
        return []
    return list(c.get("assets") or [])


@bp.route("/historico/ativo")
@R.exige_sessao
def historico_ativo():
    hoje = dt.date.today()
    de, ate, aviso_periodo = IW.periodo(request.args.get("de"), request.args.get("ate"), hoje)
    forcar = request.args.get("atualizar") == "1"
    codigo = (request.args.get("codigo") or "").strip()[:80]
    usina = (request.args.get("usina") or "").strip()[:160]
    nome = (request.args.get("nome") or "").strip()[:120]
    rotulo = (request.args.get("rotulo") or "").strip()[:120] or nome
    ativo = IW.resolver(_catalogo(), codigo, usina, nome)

    # a lista já carregada (os 30 dias da Visão COS) quando o período cabe nela; senão, a lista daquele período
    carregada = IW.janela_carregada(de, ate, hoje)
    l_de, l_ate = carregada or (de, ate)
    lista, linhas, info, erro = R.ler_lista("criadas", "TODOS", None, l_de, l_ate, None, forcar=forcar,
                                            aviso=R._progresso_de(request.args.get("p")))
    R.preparar_linhas(lista)
    total_srv, teto = int(info.get("total") or 0), int(info.get("cap") or 0)
    # o teto de 2.000 corta as OS MAIS ANTIGAS da lista: dizer (a janela pode mostrar "nenhuma OS" de um ativo que tem)
    cortadas = max(0, total_srv - len(linhas)) if teto and total_srv > teto else 0

    code, uc = ativo["code"], ativo["usina_curta"]
    mostradas = []
    for l in linhas:
        if not IW.no_periodo(l, de, ate):
            continue
        meu = IW.do_ativo(l, code)
        if meu or IW.da_usina(l, uc):
            mostradas.append(dict(l, _do_ativo=meu))
    n_ativo = sum(1 for l in mostradas if l["_do_ativo"])
    escopo = "usina" if (request.args.get("escopo") == "usina" or not code) else "ativo"
    status_opts = sorted({l.get("status") for l in mostradas if l.get("status")})
    tipos_tarefa = sorted({t for l in mostradas for t in str(l.get("tipo_tarefa") or "").split(" / ") if t})
    return render_template(
        "historico_ativo.html", conta=R._conta(), aba="hist", ativo=ativo, rotulo=rotulo, codigo_pedido=codigo,
        usina_pedida=usina, nome_pedido=nome, de=de, ate=ate, aviso_periodo=aviso_periodo, carregada=bool(carregada),
        dias_padrao=IW.DIAS_PADRAO, linhas=mostradas, n_ativo=n_ativo, n_usina=len(mostradas), escopo=escopo,
        status_opts=status_opts, tipos_tarefa=tipos_tarefa, cols=COLS, datas=R.DATAS, fmt=api.fmt_data_br, erro=erro,
        cortadas=cortadas, total_srv=total_srv, teto=teto, janela=request.args.get("janela") == "1",
        lista_de=(dt.datetime.fromtimestamp(lista.criada_em, api._BR_TZ).strftime("%H:%M") if lista else ""))
