"""O e-mail semanal das pendências da Segurança (24/10/2026).

A TST: "Receber report semanal das pendências por email, pra mim e pro supervisor responsável". Levi escolheu mandar
pelo App de Campo, que já manda e-mail (o Não das luvas vai à TST): o Nexus monta o resumo de cada destinatário toda
segunda de manhã e publica no livro `nexus_hseq_email` (registrado no catálogo antes da 1ª gravação); o App lê, manda e
diz o que mandou.

Quem recebe:
- a TST: todas as pessoas do setor Segurança (Base → Acessos → Pessoas e setores), pelo código do e-mail delas (`pessoa_hmac`),
  com as pendências de todas as usinas;
- cada Responsável UFV (o Responsável O&M da ficha da usina, o mesmo dos cartões da Mesa), só com as usinas dele, pelo
  código do e-mail: o da aba Pessoas e setores (Base → Acessos) (a pessoa ligada ao usuário do Fracttal) ou, sem ele, o do e-mail da ficha.
  Quem não tem código fica sem e-mail e a prévia diz.

O que vai no livro (a API é compartilhada, regra 8): o código da pessoa (HMAC) e o número dela no cadastro, nunca o nome
nem o e-mail; o corpo leva só usinas, clientes, números e o link para a Mesa filtrada pelo número da pessoa (`?r=`),
sem o nome. Cada linha vai assinada (HMAC com a chave derivada da NEXUS_PESSOA_HMAC, rótulo `nexus:hseq:email`).

Publica na segunda depois das 07:00 de Brasília, uma vez por semana (a semana que já está no livro não é publicada de
novo), no servidor (`ligado`). Até 30/10/2026 era só com `NEXUS_HSEQ_EMAIL_AUTO=1`; com o teste do App de 6 de 6 (a W44,
publicada à mão, foi toda para o Levi) e o Levi sem acesso ao `.env` do servidor, ficou ligado por padrão:
`NEXUS_HSEQ_EMAIL_AUTO=0` desliga, e não liga onde `NEXUS_CAMPO_AQUECER=0` (o PC e a cópia de prova), como a Zeladoria
no banco.
"""
import hashlib
import hmac
import logging
import threading
from datetime import datetime, timedelta, timezone

from flask import current_app

from ..dados import fatos as D
from ..dados import livros

log = logging.getLogger(__name__)

LIVRO, NOME_LIVRO, ABA = "nexus_hseq_email", "Nexus · e-mail semanal das pendências da Segurança", "fato_email_pendencias"
CAB = ("semana", "gerado_em", "data_id", "papel", "pessoa_id", "destinatario_hmac", "assunto", "corpo_texto", "corpo_html",
       "assinatura")
ROTULO_CHAVE = b"nexus:hseq:email"
ENDERECO = "https://app.gridco.com.br"       # o Nexus no servidor (na raiz desde a fase 4): o link do e-mail
HORA = 7                                     # segunda, 07:00 de Brasília
# O livro é a caixa de saída: o App lê a semana, manda e confirma nele, e a linha que não saiu vence na segunda seguinte.
# Semana velha não serve a ninguém e o livro crescia para sempre (Levi, 08/11/2026: "tem alguma utilidade esse livro? se
# não pode apagar"): o `publicar` guarda a corrente e as 3 anteriores. A corrente nunca sai, nem com o livro cheio.
SEMANAS_GUARDADAS = 4
# as cores do e-mail em hex, como as do PDF da Segurança (relatorio.py): o leitor de e-mail não lê as variáveis do
# nexus.css, e o fundo é claro (o Outlook e o Gmail abrem em branco)
COR = {"navy": "#090d18", "verde": "#a3d900", "tinta": "#111827", "mudo": "#5b6475", "linha": "#e3e7ee",
       "fundo": "#f3f5f8", "branco": "#ffffff", "sub": "#c9cfdb", "critico": "#c8102e", "alerta": "#b26a00",
       "planilha": "#1d6f42"}
FONTE = "'Segoe UI',Roboto,Arial,sans-serif"
RODAPE = ("E-mail automático do Nexus (Segurança · HSEQ), toda segunda de manhã. Não responda: este endereço não recebe "
          "mensagens.")
# o e-mail do responsável vai com a TST em cópia (03/11/2026, Levi: "sempre mandar para responsável e deixar a [TST]
# em cópia"): quem copia é o App, com os destinatários das linhas da TST da mesma semana (quem é TST o Nexus decide, no
# setor Segurança); o livro e a assinatura não mudam
COPIA = " A Segurança (TST) recebe uma cópia."
POR_USINA_MAX = 25                           # as usinas no corpo; a planilha leva todas
_BRT = timezone(timedelta(hours=-3))
_LACO = {"thread": None, "parar": threading.Event(), "ultimo": None}


def _agora() -> datetime:
    return datetime.now(_BRT)


def semana(d) -> str:
    """A semana ISO do dia ('2026-W44')."""
    a, s, _ = d.isocalendar()
    return f"{a}-W{s:02d}"


def assinatura(linha: dict, chave_base: str) -> str:
    """HMAC-SHA256 em hex minúsculo de "email|semana|destinatario_hmac|assunto|corpo_texto", com a chave derivada da
    NEXUS_PESSOA_HMAC (`ROTULO_CHAVE`). Sem chave: "" (o App não manda a linha)."""
    base = (chave_base or "").strip()
    if not base:
        return ""
    chave = hmac.new(base.encode("utf-8"), ROTULO_CHAVE, hashlib.sha256).digest()
    partes = ("email", linha.get("semana"), linha.get("destinatario_hmac"), linha.get("assunto"), linha.get("corpo_texto"))
    return hmac.new(chave, "|".join(D._txt(p) for p in partes).encode("utf-8"), hashlib.sha256).hexdigest()


# ── quem recebe ─────────────────────────────────────────────────────────────────────────────────────────────────────
def destinatarios(cfg) -> dict:
    """{"tst": [{pessoa_id, hmac}], "responsaveis": {nome: {pessoa_id, hmac}}, "erro"}. O nome fica só aqui dentro (os
    cartões da Mesa agrupam pelo nome); no livro vão o número e o código."""
    from ..auth.setor_telas import setor_de_cada_codigo
    from ..cadastro import setores as S
    from ..campo import visao
    from ..cadastro.ligacao_campo import mapas_de
    out = {"tst": [], "responsaveis": {}, "erro": ""}
    b = visao._Base()
    try:
        st = S.ler(visao._base(), visao._sessao())
    except Exception as e:      # noqa: BLE001 — sem os setores, a TST fica sem e-mail e a prévia diz
        st = {"decisoes": [], "setores": [], "erro": type(e).__name__}
    out["erro"] = st.get("erro") or ""
    decisoes = st.get("decisoes") or []
    seg = {s["setor_id"] for s in S.ativos(st.get("setores") or []) if S._norm(s.get("nome")) == "seguranca"}
    por_codigo = setor_de_cada_codigo(decisoes)
    pid_do_codigo = {d["pessoa_hmac"]: d.get("pessoa_id") for d in sorted(decisoes, key=lambda x: x["decidida_em"])
                     if d.get("pessoa_hmac")}
    out["tst"] = [{"pessoa_id": pid_do_codigo.get(c), "hmac": c} for c, sid in sorted(por_codigo.items()) if sid in seg]
    # o código de cada pessoa: o do usuário do Fracttal ligado a ela e, sem ele, o do e-mail da ficha
    codigo_da = {}
    for c, pid in mapas_de(cfg, [], b.pessoas)["hmac"].items():
        codigo_da.setdefault(pid, c)
    for d in sorted(decisoes, key=lambda x: x["decidida_em"]):
        if d.get("pessoa_id") and d.get("pessoa_hmac"):
            codigo_da[d["pessoa_id"]] = d["pessoa_hmac"]
    for u in b.usinas:
        pid = D._id(u.get("responsavel_om_id"))
        if pid:
            nome = b.nome_da_pessoa(pid, "Responsável")
            out["responsaveis"].setdefault(nome, {"pessoa_id": pid, "hmac": codigo_da.get(pid, "")})
    return out


# ── o que vai no e-mail ─────────────────────────────────────────────────────────────────────────────────────────────
def _plural(n, um, varios):
    return f"{n} {um if n == 1 else varios}"


ROT_AGIR = {"pts": ("PT parada", "PTs paradas"), "vencidos": ("extintor vencido", "extintores vencidos"),
            "nr": ("extintor não reconhecido", "extintores não reconhecidos"),
            "sem_luvas": ("usina sem luvas", "usinas sem luvas")}
ROT_ATENCAO = {"perto": ("extintor perto de vencer", "extintores perto de vencer"),
               "sem_atual": ("extintor sem atualização", "extintores sem atualização"),
               "luvas_semv": ("usina sem verificar as luvas", "usinas sem verificar as luvas"),
               "ronda": ("nova ronda pedida", "novas rondas pedidas")}


def _por_usina(L) -> list[dict]:
    """As usinas com o que pede ação agora, a que tem mais primeiro: {usina, cliente, n: {chave: número}, total}."""
    from . import extintores as EXT
    g = {}
    for k in ROT_AGIR:
        for x in L[k]:
            u = g.setdefault((EXT.valor_do_filtro(x, "cliente"), x.get("usina") or ""),
                             {"usina": x.get("usina") or "", "cliente": EXT.valor_do_filtro(x, "cliente"), "n": {}})
            u["n"][k] = u["n"].get(k, 0) + 1
    for u in g.values():
        u["total"] = sum(u["n"].values())
    return sorted(g.values(), key=lambda u: (-u["total"], u["usina"].lower()))


def montar(L: dict, *, papel: str, hoje, link: str, planilha: str) -> dict:
    """{assunto, corpo_texto, corpo_html} do e-mail de um destinatário (`L` = as listas da Mesa já filtradas). O HTML é
    de e-mail (03/11/2026, Levi: "Deixe a estrutura um pouco mais bonita e o link para o arquivo em excel deixe mais
    bonito e formatado"): tabelas e estilo na linha, que é o que o Outlook respeita, numa coluna de até 600 px; os
    botões são células com fundo (o `<a>` sozinho perde o fundo no Outlook)."""
    agir = {k: len(L[k]) for k in ROT_AGIR}
    atencao = {k: len(L[k]) for k in ROT_ATENCAO}
    total, total_at = sum(agir.values()), sum(atencao.values())
    quem = "nas suas usinas" if papel == "responsavel" else "de todas as usinas"
    botao = "Abrir o meu Painel no Nexus" if papel == "responsavel" else "Abrir a Mesa da Segurança no Nexus"
    assunto = (f"Pendências da Segurança {quem} · semana de {hoje:%d/%m}: "
               + (_plural(total, "para agir", "para agir") if total else "nada para agir agora"))
    usinas = _por_usina(L)
    linhas_u = [(u["usina"], u["cliente"], " · ".join(_plural(n, *ROT_AGIR[k]) for k, n in u["n"].items()), u["total"])
                for u in usinas[:POR_USINA_MAX]]
    mais = len(usinas) - POR_USINA_MAX
    t = [f"Pendências da Segurança {quem}, {hoje:%d/%m/%Y}.", "", "Para agir agora"]
    t += [f"- {_plural(agir[k], *ROT_AGIR[k])}" for k in ROT_AGIR]
    t += ["", "Atenção"] + [f"- {_plural(atencao[k], *ROT_ATENCAO[k])}" for k in ROT_ATENCAO]
    if linhas_u:
        t += ["", "Por usina"] + [f"- {u} ({c}): {o}" for u, c, o, _n in linhas_u]
        if mais > 0:
            t.append(f"- e mais {mais} usinas: veja no Nexus")
    rodape = RODAPE + (COPIA if papel == "responsavel" else "")
    t += ["", f"{botao}: {link}", f"Planilha em Excel, caso a caso: {planilha}", "", rodape]
    return {"assunto": assunto, "corpo_texto": "\n".join(t),
            "corpo_html": _html(quem, hoje, agir, atencao, total, total_at, linhas_u, mais, botao, link, planilha,
                                rodape)}


def _maiuscula(x: str) -> str:
    """Só a 1ª letra em maiúscula ("PT parada" segue com o PT; o `capitalize` faria "Pt parada")."""
    return x[:1].upper() + x[1:]


def _html(quem, hoje, agir, atencao, total, total_at, linhas_u, mais, botao, link, planilha, rodape) -> str:
    from html import escape as e
    c = COR

    def caixa(n, rotulo, cor):
        return (f'<td width="48%" style="padding:14px 16px;border:1px solid {c["linha"]};border-radius:10px;'
                f'background:{c["branco"]}"><div style="font-size:30px;line-height:1;font-weight:700;color:{cor}">{n}</div>'
                f'<div style="margin-top:6px;font-size:13px;color:{c["mudo"]}">{rotulo}</div></td>')

    def lista(titulo, itens, rotulos, cor):
        h = [f'<div style="margin:22px 0 6px;font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;'
             f'color:{c["mudo"]}">{titulo}</div>',
             '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">']
        for k, n in itens.items():
            um, varios = rotulos[k]
            tom = cor if n else c["mudo"]
            h.append(f'<tr><td style="padding:9px 0;border-bottom:1px solid {c["linha"]};font-size:14px;'
                     f'color:{c["tinta"] if n else c["mudo"]}">{e(_maiuscula(um if n == 1 else varios))}</td>'
                     f'<td align="right" style="padding:9px 0;border-bottom:1px solid {c["linha"]};font-size:15px;'
                     f'font-weight:700;color:{tom}">{n}</td></tr>')
        return h + ["</table>"]

    def botao_html(href, texto, cheio, selo=""):
        fundo = f'background:{c["verde"]};' if cheio else f'background:{c["branco"]};border:1px solid {c["navy"]};'
        # o selo da planilha (XLSX no verde da planilha): diz antes do clique que é um arquivo para baixar
        selo = (f'<span style="display:inline-block;margin-right:10px;padding:2px 6px;border-radius:4px;'
                f'background:{c["planilha"]};color:{c["branco"]};font-size:11px;font-weight:700;letter-spacing:.04em;'
                f'vertical-align:1px">{selo}</span>') if selo else ""
        return (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:10px"><tr>'
                f'<td style="{fundo}border-radius:8px"><a href="{e(href)}" style="display:inline-block;padding:12px 22px;'
                f'font-size:14px;font-weight:700;color:{c["navy"]};text-decoration:none">{selo}{texto}</a></td></tr></table>')

    h = [f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{c["fundo"]};'
         f'font-family:{FONTE}"><tr><td align="center" style="padding:24px 12px">',
         f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;'
         f'background:{c["branco"]};border:1px solid {c["linha"]};border-radius:12px;border-collapse:separate">',
         # o cabeçalho: navy com a linha verde, como o topo do Nexus
         f'<tr><td style="background:{c["navy"]};padding:20px 24px;border-bottom:3px solid {c["verde"]};'
         f'border-radius:12px 12px 0 0"><div style="font-size:12px;font-weight:700;letter-spacing:.08em;'
         f'text-transform:uppercase;color:{c["verde"]}">Nexus · Segurança · HSEQ</div>'
         f'<div style="margin-top:6px;font-size:20px;font-weight:700;color:{c["branco"]}">Pendências da Segurança '
         f'{e(quem)}</div><div style="margin-top:4px;font-size:13px;color:{c["sub"]}">Semana de {hoje:%d/%m/%Y}</div>'
         f'</td></tr>',
         f'<tr><td style="padding:20px 24px 4px">',
         # os dois números da semana
         '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:separate;'
         'border-spacing:0"><tr>',
         caixa(total, "para agir agora", c["critico"] if total else c["mudo"]), '<td width="4%"></td>',
         caixa(total_at, "em atenção", c["alerta"] if total_at else c["mudo"]), "</tr></table>"]
    h += lista("Para agir agora", agir, ROT_AGIR, c["critico"])
    h += lista("Atenção", atencao, ROT_ATENCAO, c["alerta"])
    if linhas_u:
        h += [f'<div style="margin:22px 0 6px;font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;'
              f'color:{c["mudo"]}">Por usina</div>',
              '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">',
              f'<tr><th align="left" style="padding:8px 8px 8px 0;border-bottom:2px solid {c["linha"]};font-size:12px;'
              f'color:{c["mudo"]};font-weight:600">Usina</th><th align="left" style="padding:8px;border-bottom:2px solid '
              f'{c["linha"]};font-size:12px;color:{c["mudo"]};font-weight:600">Para agir</th><th align="right" '
              f'style="padding:8px 0;border-bottom:2px solid {c["linha"]};font-size:12px;color:{c["mudo"]};'
              f'font-weight:600">Total</th></tr>']
        for usina, cliente, o_que, n in linhas_u:
            h.append(f'<tr><td valign="top" style="padding:9px 8px 9px 0;border-bottom:1px solid {c["linha"]}">'
                     f'<div style="font-size:14px;font-weight:600;color:{c["tinta"]}">{e(usina)}</div>'
                     f'<div style="font-size:12px;color:{c["mudo"]}">{e(cliente)}</div></td>'
                     f'<td valign="top" style="padding:9px 8px;border-bottom:1px solid {c["linha"]};font-size:13px;'
                     f'color:{c["tinta"]}">{e(o_que)}</td>'
                     f'<td valign="top" align="right" style="padding:9px 0;border-bottom:1px solid {c["linha"]};'
                     f'font-size:15px;font-weight:700;color:{c["critico"]}">{n}</td></tr>')
        if mais > 0:
            h.append(f'<tr><td colspan="3" style="padding:9px 0;font-size:13px;color:{c["mudo"]}">e mais {mais} usinas: '
                     f'veja no Nexus</td></tr>')
        h.append("</table>")
    # os dois caminhos: o Nexus e a planilha em Excel
    h += ['<div style="margin-top:24px"></div>', botao_html(link, botao, True), botao_html(planilha,
          "Baixar a planilha em Excel", False, "XLSX"),
          f'<div style="margin-top:8px;font-size:12px;color:{c["mudo"]}">A planilha traz caso a caso, uma aba por '
          f'pendência, com os mesmos filtros.</div>',
          "</td></tr>",
          f'<tr><td style="padding:18px 24px 22px"><div style="border-top:1px solid {c["linha"]};padding-top:12px;'
          f'font-size:12px;color:{c["mudo"]}">{e(rodape)}</div></td></tr>',
          "</table>", "</td></tr></table>"]
    return "\n".join(h)


def _no_nexus(caminho: str, **args) -> str:
    from urllib.parse import urlencode

    from ..prefixo import na_raiz
    q = urlencode({k: v for k, v in args.items() if v})
    return ENDERECO + na_raiz(caminho) + (f"?{q}" if q else "")


def _links(pessoa_id=None) -> dict:
    """{link, planilha}. O responsável abre o Painel dele no Campo · App (03/11/2026, Levi: "O link do Nexus que vai
    para o e-mail tem que ser o nexus > campo app > painel (filtrado no responsável)"); a TST, que não é responsável de
    usina, a Mesa da Segurança. A planilha é a da Mesa, filtrada. Sempre pelo número da pessoa (`r`), nunca o nome."""
    if pessoa_id:
        return {"link": _no_nexus("/t/campo/responsaveis", r=pessoa_id, modo="painel"),
                "planilha": _no_nexus("/t/hseq/mesa/pendencias.xlsx", r=pessoa_id)}
    return {"link": _no_nexus("/t/hseq/mesa"), "planilha": _no_nexus("/t/hseq/mesa/pendencias.xlsx")}


def da_semana(cfg, hoje=None) -> dict:
    """{linhas: as linhas do livro desta semana, sem_codigo: [nomes dos responsáveis sem código], erros}: o e-mail de
    cada destinatário, com as mesmas contas da Mesa. Quem não tem pendência nenhuma não recebe."""
    from ..torres.hseq import _pendencias
    agora = _agora()
    hoje = hoje or agora.date()
    sem = semana(hoje)
    try:
        dest = destinatarios(cfg)
    except Exception as e:      # noqa: BLE001 — sem o cadastro, ninguém recebe e a prévia diz
        dest = {"tst": [], "responsaveis": {}, "erro": "", "falhou": type(e).__name__}
    linhas, sem_codigo = [], []
    base = {"semana": sem, "gerado_em": agora.isoformat(timespec="seconds"), "data_id": int(hoje.strftime("%Y%m%d"))}
    geral = _pendencias({})
    erros = dict(geral["erros"], **({"cadastro": dest["falhou"]} if dest.get("falhou") else {}))
    if not erros:
        corpo = montar(geral["listas"], papel="tst", hoje=hoje, **_links())
        for p in dest["tst"]:
            linhas.append(dict(base, papel="tst", pessoa_id=p["pessoa_id"] or "", destinatario_hmac=p["hmac"], **corpo))
        for nome, p in sorted(dest["responsaveis"].items()):
            L = _pendencias({"responsavel": nome})["listas"]
            if not any(L.values()):
                continue
            if not p["hmac"]:
                sem_codigo.append(nome)
                continue
            linhas.append(dict(base, papel="responsavel", pessoa_id=p["pessoa_id"], destinatario_hmac=p["hmac"],
                               **montar(L, papel="responsavel", hoje=hoje, **_links(p["pessoa_id"]))))
    chave = cfg.get("NEXUS_PESSOA_HMAC")
    for x in linhas:
        x["assinatura"] = assinatura(x, chave)
    return {"linhas": linhas, "sem_codigo": sem_codigo, "erros": erros, "semana": sem,
            "tst_sem_setor": dest["erro"], "n_tst": len(dest["tst"]),
            # só para a prévia (o nome nunca vai ao livro)
            "nomes": {p["pessoa_id"]: nome for nome, p in dest["responsaveis"].items()}}


# ── o livro ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _banco(cfg):
    from ..pcm.motivos import _banco as banco
    return banco(cfg)


def ler(cfg) -> list[dict]:
    base, sessao = _banco(cfg)
    a = livros.abas_conferidas(base, sessao, LIVRO, (ABA,))     # "não li" não vira "semana sem linha"
    return list(livros._linhas(base, sessao, a[ABA])) if ABA in a else []


def publicar(cfg, hoje=None) -> dict:
    """Publica as linhas da semana (uma vez: a semana que já está no livro não volta). {publicadas, semana, ...}."""
    if not str(cfg.get("NEXUS_PESSOA_HMAC") or "").strip():
        return {"publicadas": 0, "erro": "sem a NEXUS_PESSOA_HMAC: o App não mandaria linha sem assinatura"}
    token = cfg.get("GRIDCO_SQL_TOKEN")
    if not token:
        return {"publicadas": 0, "erro": "sem a GRIDCO_SQL_TOKEN"}
    # o livro primeiro: com a semana já nele, o laço (de 10 em 10 min, a semana inteira) não monta os e-mails de todos
    # para jogar fora (achado 5 da auditoria de 08/11/2026)
    velhas = ler(cfg)
    sem = semana(hoje or _agora().date())
    if any(D._txt(x.get("semana")) == sem for x in velhas):
        return {"publicadas": 0, "semana": sem, "erro": ""}
    d = da_semana(cfg, hoje)
    if d["erros"]:
        return {"publicadas": 0, "semana": d["semana"], "erro": f"fonte sem leitura: {', '.join(d['erros'])}"}
    vazio = (lambda v: None if v in ("", None) else v)      # noqa: E731
    guardar = {semana((hoje or _agora().date()) - timedelta(days=7 * i)) for i in range(SEMANAS_GUARDADAS)}
    manter = [x for x in velhas if D._txt(x.get("semana")) in guardar]
    corpo = [[vazio(x.get(c)) for c in CAB] for x in manter + d["linhas"]]
    base, sessao = _banco(cfg)
    livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), corpo)}, base=base, token=token, sessao=sessao)
    return {"publicadas": len(d["linhas"]), "semana": d["semana"], "sem_codigo": len(d["sem_codigo"]), "erro": ""}


def devido(agora: datetime) -> bool:
    """Da segunda, 07:00, até o fim da semana: a API fora a segunda inteira não perde a semana (achado 4 da auditoria de
    08/11/2026; o App aceita a linha até a segunda seguinte). Repetir quem impede é o `publicar` (uma vez por semana)."""
    return agora.weekday() > 0 or agora.hour >= HORA


def ligado(cfg) -> bool:
    """Publica nesta máquina? Sim no servidor; não onde NEXUS_HSEQ_EMAIL_AUTO=0 nem onde NEXUS_CAMPO_AQUECER=0 (o PC)."""
    return (str(cfg.get("NEXUS_HSEQ_EMAIL_AUTO", "1") or "1").strip() != "0"
            and str(cfg.get("NEXUS_CAMPO_AQUECER", "1") or "1").strip() != "0")


def ligar(app):
    """O laço: a cada 10 min, da segunda depois das 07:00 em diante, publica a semana (uma vez). Só onde `ligado`. Quem chama é o
    servir.py (o servidor), nunca o create_app nem o app.py: teste não fala com a rede."""
    if _LACO["thread"] is not None or not ligado(app.config):
        return

    def laco():
        espera = 120
        while not _LACO["parar"].wait(espera):
            espera = 600
            if not devido(_agora()):
                continue
            with app.app_context():
                try:
                    _LACO["ultimo"] = publicar(current_app.config)
                    if _LACO["ultimo"].get("publicadas") or _LACO["ultimo"].get("erro"):
                        log.info("e-mail semanal da Segurança: %s", _LACO["ultimo"])
                except Exception as e:      # noqa: BLE001 — o laço não morre por uma volta
                    _LACO["ultimo"] = {"erro": f"{type(e).__name__}: {e}"[:300]}
                    log.exception("e-mail semanal da Segurança")

    from ..casca import fracttal_conta              # o laço declara o fundo: só o declarado tem o teto de 90 do porteiro
    _LACO["thread"] = threading.Thread(target=fracttal_conta.de_fundo("fundo:nexus-hseq-email", laco),
                                       name="nexus-hseq-email", daemon=True)
    _LACO["thread"].start()
