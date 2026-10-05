"""Torre Campo · App: modo gerencial do App de Campo. Leia o CLAUDE.md desta pasta antes de mexer.

Cada tela com aba no painel do App abre o próprio painel, na aba dela, até ganhar a versão do Nexus. A versão do Nexus
liga sozinha quando a chave só de leitura das tabelas do App existe (nexus/campo/tabelas.py).
"""
from datetime import datetime
from urllib.parse import urlencode

from flask import current_app, render_template, request
from markupsafe import Markup, escape

from ...campo import aprovacao as campo_aprovacao
from ...campo import atencao as campo_atencao
from ...campo import fonte_pg as campo_fonte
from ...campo import ordens as campo_ordens
from ...campo import pt as campo_pt
from ...campo import tabelas as campo_tabelas
from ...campo import triagem as campo_triagem
from ..modelo import Tela, Torre

TORRE = Torre(
    id="campo",
    nome="Campo · App",
    ordem=90,
    icone="hard-hat",
    descricao="Modo gerencial do App de Campo: aprovação, PT, rondas, zeladoria e qualidade.",
    telas=[
        Tela("atencao", "Central de atenção",
             "Que ponto do campo está aberto ou parado há dias?",
             "Rotas gestao/* do App de Campo"),
        Tela("aprovacao", "Aprovação de OS",
             "Que OS em revisão posso aprovar em lote e qual pede meu olho?",
             "Rotas gestao/* do App de Campo"),
        # Levi, 04/10/2026: "crie para PT, ZELADORIA". As duas abas do painel do App não tinham lugar na torre.
        # A PT fica junto da aprovação de OS porque as duas são fila de decisão do supervisor. A "APR e PT" da
        # torre HSEQ é outra pergunta (OS de risco sem APR ou PT assinada) e continua lá.
        Tela("pt", "Permissões de trabalho",
             "Que PT está esperando o De acordo do supervisor, e há quanto tempo?",
             "Fila de PT do painel de gestão do App de Campo"),
        Tela("os", "Ordens de serviço",
             "As OS estão sendo fechadas com evidência?",
             "Rotas gestao/* do App de Campo"),
        Tela("rondas", "Rondas",
             "Que usina está sem ronda de campo há mais tempo?",
             "Rotas gestao/* do App de Campo"),
        # Zeladoria é acompanhamento do dia, como a ronda: serviço de terceiro com APR, vistoria, EPI e fechamento.
        Tela("zeladoria", "Zeladoria",
             "Que serviço de terceiro está parado, sem diária hoje ou com EPI pendente?",
             "Aba Zeladoria do painel de gestão do App de Campo"),
        Tela("ranking", "Ranking",
             "Qual região tem qualidade e cobertura melhores?",
             "Rotas gestao/* do App de Campo"),
        Tela("triagem", "Triagem de qualidade",
             "O que exige ação hoje na qualidade do fechamento?",
             "Rotas gestao/* do App de Campo"),
        Tela("imagens", "Imagens da ronda",
             "Que foto de ronda mostra um problema?",
             "Motor de imagem do App de Campo"),
        Tela("rotas", "Rotas do dia",
             "Qual a melhor ordem de visitas para cada equipe?",
             "Programação do PCM + localização das usinas"),
    ],
)

bp = TORRE.criar_blueprint(__name__)

# Enquanto a chave só de leitura das tabelas do App não existe, cada tela que tem aba no painel de gestão do App abre o
# próprio painel, na aba dela, dentro do Nexus (Levi, 04/10/2026: "você construiu as abas mas ainda não vejo nada").
# O painel aceita moldura (não manda X-Frame-Options), faz o login Microsoft por popup e abre direto numa aba com
# #ir=<aba> (gestao.html, v225). Nada aqui lê ou grava dado do App: é o painel dele, com o login dele. Quando a tela
# nativa existir, a view dela entra no lugar desta.
PAINEL_PADRAO = "https://gridco-campo-mw.azurewebsites.net/api/gestao"
# Tela do Nexus -> abas do painel do App que ela mostra. O menu do App fica fora da vista (ver .campo-recorte no
# nexus.css), então toda aba que precisa ser alcançada tem de estar aqui: Encaminhamentos entra na Central de atenção,
# como no encaixe de 04/10.
ABAS_DO_PAINEL = {
    "atencao": [("atn", "Atenção"), ("enc", "Encaminhamentos")],
    "aprovacao": [("su", "Supervisão")],
    "pt": [("pt", "Permissões de trabalho")],
    "os": [("os", "Ordens de serviço")],
    "rondas": [("ro", "Rondas")],
    "zeladoria": [("zl", "Zeladoria")],
    "ranking": [("des", "Desempenho")],
    "triagem": [("vg", "Triagem de qualidade")],
    "imagens": [("img", "Imagens")],
}


def _painel() -> str:
    return current_app.config.get("NEXUS_CAMPO_PAINEL") or PAINEL_PADRAO


# ── Central de atenção do Nexus (aprovada pelo Levi em 04/10/2026, proposta em
#    https://claude.ai/artifact/SBPyaREFJpHAEKimd7xnHv). As contas são as do App (nexus/campo/atencao.py). ──────────
# Cor do tipo como no painel do App (ATNCOLS): vermelho o que piora a usina, azul o que é registro, âmbar o resto.
COR_DO_TIPO = {"praga": "critico", "nao_fez": "critico", "os_falha": "critico",
               "tracker": "info", "os_branco": "info"}
SITUACAO_ENC = {"feita": ("Feito", "ok"), "confirmada": ("Confirmado", "ok"), "resolvida": ("Resolvido", "ok")}


def _url(**mudar) -> str:
    """O endereço desta tela com os filtros de agora, trocando só o que se pede (None tira o filtro)."""
    args = {k: v for k, v in request.args.items() if v}
    for k, v in mudar.items():
        if v in (None, ""):
            args.pop(k, None)
        else:
            args[k] = v
    return "?" + urlencode(args) if args else "?"


def _dia_curto(iso) -> str:
    s = str(iso or "")
    return f"{s[8:10]}/{s[5:7]}" if len(s) >= 10 else "—"


def _idade(dias) -> str:
    n = int(dias or 0)
    return "nunca" if n >= 999 else ("hoje" if n == 0 else f"{n} d")


def _cor_idade(dias) -> str:
    n = int(dias or 0)
    return "critico" if n >= 14 else ("alerta" if n >= 7 else "neutro")


def _atencao_nativa():
    tela = TORRE.tela("atencao")
    aba = "enc" if request.args.get("aba") == "enc" else "pontos"
    dias = int(request.args.get("dias")) if request.args.get("dias") in ("7", "14", "30") else 14
    enc = campo_atencao.encaminhamentos()
    ctx = dict(torre=TORRE, tela=tela, aba=aba, dias=dias, painel=_painel(), url=_url, dia_curto=_dia_curto,
               idade=_idade, cor_idade=_cor_idade, enc=enc, situacao_enc=SITUACAO_ENC)
    if aba == "enc":
        return render_template("campo/atencao.html", leitura=enc, **ctx)
    leitura = campo_atencao.central(dias)
    todos = leitura.dados.get("pontos") or []
    regiao = request.args.get("regiao", "")
    # Como no painel do App: os números e os botões de tipo contam a região escolhida, não o tipo escolhido, para o
    # número do botão bater com o que a lista mostra quando ele é clicado.
    na_regiao = [p for p in todos if not regiao or p.get("cluster") == regiao]
    f, tipo, q = request.args.get("f", ""), request.args.get("tipo", ""), request.args.get("q", "").strip().lower()
    lista = [p for p in na_regiao
             if (f != "velhos" or int(p.get("dias") or 0) >= 7)
             and (not tipo or p.get("tipo") == tipo)
             and (not q or q in " ".join(str(p.get(k) or "") for k in ("usina", "oque", "detalhe", "nome", "os")).lower())]
    por_tipo = {}
    for p in na_regiao:
        por_tipo[p["tipo"]] = por_tipo.get(p["tipo"], 0) + 1
    por_usina = {}
    for p in lista:          # a lista já vem do mais velho para o mais novo: o 1º de cada usina é o mais antigo dela
        por_usina.setdefault(p.get("usina") or "", []).append(p)
    por_usina = sorted(por_usina.items(), key=lambda kv: -int(kv[1][0].get("dias") or 0))
    lido = datetime.fromtimestamp(leitura.lido_em).strftime("%H:%M")
    return render_template(
        "campo/atencao.html", leitura=leitura, lido=lido, lista=lista, total=len(na_regiao),
        velhos=sum(1 for p in na_regiao if int(p.get("dias") or 0) >= 7),
        usinas=len({p.get("usina") for p in na_regiao}),
        sem_ronda=por_tipo.get("sem_ronda", 0), por_tipo=por_tipo, tipos=leitura.dados.get("tipos") or {},
        regioes=sorted({p.get("cluster") for p in todos if p.get("cluster")}), regiao=regiao, f=f, tipo=tipo,
        q=request.args.get("q", ""), vista="usina" if request.args.get("vista") == "usina" else "tabela",
        por_usina=por_usina, cor_tipo=COR_DO_TIPO, dias_sem_ronda=campo_atencao.regras_app.ATN_DIAS_SEM_RONDA, **ctx)


# ── Aprovação de OS do Nexus (proposta aprovada em 04/10/2026: https://claude.ai/artifact/UqLiJApqDHA7bVqD59hPFY).
#    A fila e os grupos são os do App (nexus/campo/aprovacao.py). ─────────────────────────────────────────────────
GRUPOS = (("completa", "Evidência completa", "ok",
           "Subtarefas respondidas, nota alta, tempo dentro do previsto, nenhuma foto marcada. Não pede análise, "
           "pede decisão."),
          ("olho", "Precisa do seu olho", "alerta",
           "Nota abaixo de 80, tempo muito fora do previsto, foto marcada pelo motor ou já devolvida antes."),
          ("fora_do_app", "Fechadas fora do App", "neutro",
           "Sem evidência para julgar por aqui. Encolhe conforme a equipe adota o App, e é essa a métrica deste "
           "grupo."))


def _cor_espera(dias) -> str:
    n = int(dias or 0)
    return "critico" if n >= 30 else ("alerta" if n >= 7 else "ok")


def _aprovacao_nativa():
    tela = TORRE.tela("aprovacao")
    leitura = campo_aprovacao.fila(request.args)
    d = leitura.dados
    lido = datetime.fromtimestamp(leitura.lido_em).strftime("%H:%M")
    return render_template(
        "campo/aprovacao.html", torre=TORRE, tela=tela, leitura=leitura, lido=lido, d=d, grupos=GRUPOS,
        nome_grupo={g[0]: (g[1], g[2]) for g in GRUPOS}, balde=request.args.get("balde", ""), url=_url,
        dia_curto=_dia_curto, cor_espera=_cor_espera, painel=_painel(), coleta=_coleta())


# ── Permissões de trabalho do Nexus (proposta aprovada em 04/10/2026: https://claude.ai/artifact/DjP2sXABw5rz5FFjVFNKBu).
#    As PT e a situação de cada uma são as do App (nexus/campo/pt.py). ────────────────────────────────────────────
SITUACAO_PT = {"aguardando": ("Aguardando", "alerta"), "de_acordo": ("De acordo", "ok"),
               "negada": ("Não autorizada", "critico"), "vencida": ("Vencida", "neutro")}


def _idade_min(m) -> str:
    m = int(m or 0)
    return f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} min"


def _pt_nativa():
    tela = TORRE.tela("pt")
    leitura = campo_pt.painel()
    d = leitura.dados
    sit = request.args.get("sit", "")
    historico = [p for p in d.get("historico") or [] if not sit or p.get("situacao") == sit]
    return render_template(
        "campo/pt.html", torre=TORRE, tela=tela, leitura=leitura, d=d, historico=historico, sit=sit,
        situacoes=SITUACAO_PT, lido=datetime.fromtimestamp(leitura.lido_em).strftime("%H:%M"), url=_url,
        idade_min=_idade_min, painel=_painel())


# ── Ordens de serviço do Nexus (Levi, 04/10/2026: "passa para o Nexus logo"). Os números e a lista são os do App
#    (nexus/campo/ordens.py); faixas de qualidade e o alerta de previsto/real como no OSCOLS do painel. ──────────
FAIXAS_OS = (("", "Todas"), ("bad", "Não está bom"), ("warn", "Atenção"), ("ok", "Bom"), ("dev", "Devolvidas"))


def _situacao_os(x) -> tuple[str, str]:
    if x.get("devolvida"):
        return "Devolvida", "critico"
    q = int(x.get("qualidade") or 0)
    return ("Bom", "ok") if q >= 85 else (("Atenção", "alerta") if q >= 70 else ("Não está bom", "critico"))


def _na_faixa(x, faixa) -> bool:
    q = int(x.get("qualidade") or 0)
    return {"": True, "dev": bool(x.get("devolvida")), "bad": q < 70, "warn": 70 <= q < 85, "ok": q >= 85}.get(faixa, True)


def _ordens_nativa():
    tela = TORRE.tela("os")
    dias = int(request.args.get("dias")) if request.args.get("dias") in ("7", "30", "90") else 7
    leitura = campo_ordens.painel(dias)
    d = leitura.dados
    atual = d.get("atual") or {}
    faixa, regiao, q = request.args.get("faixa", ""), request.args.get("regiao", ""), request.args.get("q", "").strip()
    todas = atual.get("linhas") or []
    lista = [x for x in todas if _na_faixa(x, faixa) and (not regiao or x.get("cluster") == regiao)
             and (not q or q.lower() in " ".join(str(x.get(k) or "") for k in ("os", "tarefa", "tecnico", "usina")).lower())]
    return render_template(
        "campo/ordens.html", torre=TORRE, tela=tela, leitura=leitura, dias=dias, r=atual.get("resumo") or {},
        ra=d.get("anterior") or {}, lista=lista, total=len(todas), faixas=FAIXAS_OS, faixa=faixa, regiao=regiao, q=q,
        regioes=sorted({x.get("cluster") for x in todas if x.get("cluster")}), situacao=_situacao_os, url=_url,
        dia_curto=_dia_curto, lido=datetime.fromtimestamp(leitura.lido_em).strftime("%H:%M"), painel=_painel(),
        coleta=_coleta())


# ── Triagem de qualidade do Nexus (Levi, 04/10/2026: "pode gravar na API do PG e ligar as telas"). A mesa de triagem
#    do App (nexus/campo/triagem.py): OS e supervisores; rondas e usinas sem ronda continuam no App. ─────────────
def _rot_item(i) -> str:
    # o rotItem do painel do App
    if i.get("tipo") == "os":
        return f"OS {i.get('id')}"
    if i.get("tipo") == "ronda":
        return f"Ronda {_dia_curto(i.get('data') or i.get('quando') or i.get('id'))}"
    if i.get("tipo") in ("usina", "usina_nunca"):
        return i.get("onde") or "Cobertura"
    return i.get("quem") or str(i.get("id") or "")


def _motivo(texto) -> Markup:
    """O motivo vem do App com <b> no número que importa: escapa tudo e devolve só o negrito."""
    return Markup(str(escape(texto or "")).replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>"))


def _triagem_nativa():
    tela = TORRE.tela("triagem")
    dias = int(request.args.get("dias")) if request.args.get("dias") in ("7", "30", "90") else 30
    leitura = campo_triagem.painel(dias)
    return render_template(
        "campo/triagem.html", torre=TORRE, tela=tela, leitura=leitura, d=leitura.dados, dias=dias, url=_url,
        dia_curto=_dia_curto, rot_item=_rot_item, motivo=_motivo, painel=_painel(), coleta=_coleta(),
        lido=datetime.fromtimestamp(leitura.lido_em).strftime("%H:%M"))


def _coleta() -> str:
    """Quando o coletor gravou o banco (o frescor do dado do Fracttal), "04/10 21:30"."""
    iso = campo_fonte.coleta()
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m %H:%M") if iso else ""
    except ValueError:
        return ""


# tela -> (versão do Nexus, ela tem tudo de que precisa?). Sem isso, a tela segue no painel do App (moldura abaixo).
TELAS_DO_NEXUS = {
    "atencao": (_atencao_nativa, lambda: campo_tabelas.configurado(campo_atencao.TABELAS)),
    "aprovacao": (_aprovacao_nativa, campo_aprovacao.configurado),
    "pt": (_pt_nativa, campo_pt.configurado),
    "os": (_ordens_nativa, campo_ordens.configurado),
    "triagem": (_triagem_nativa, campo_triagem.configurado),
}


def _painel_na_aba(tela_id: str, abas: list[tuple[str, str]]):
    def view():
        nativa = TELAS_DO_NEXUS.get(tela_id)
        if nativa and nativa[1]():
            return nativa[0]()
        painel = _painel()
        # só aba conhecida entra no endereço; o que vier diferente na URL cai na primeira
        pedida = request.args.get("aba", "")
        aba = next((a for a, _ in abas if a == pedida), abas[0][0])
        return render_template("campo/painel.html", torre=TORRE, tela=TORRE.tela(tela_id),
                               abas=abas, aba=aba, destino=f"{painel}#ir={aba}")
    return view


# A rota fixa vence o placeholder genérico /<tela_id>. "Rotas do dia" não existe no App e segue placeholder.
for _tela_id, _abas in ABAS_DO_PAINEL.items():
    bp.add_url_rule(f"/{_tela_id}", endpoint=f"painel_{_tela_id}", view_func=_painel_na_aba(_tela_id, _abas))
