"""Os e-mails automáticos do App de Campo, vistos pelo Nexus (24/11/2026).

Levi, pela sessão do App: "Gostaria de poder controlar esses e-mails automáticos ou ter pelo menos um controle! E
gostaria que estivesse no Nexus". O App manda pelo Microsoft Graph (naoresponda@), com os destinatários nas configurações
dele no Azure; o Nexus mostra o que sai, para quem e se saiu (Base › E-mails automáticos, só administrador). A edição
(ligar e desligar, modo teste, destinatários) vem depois, pelo livro `nexus_email_controle · fato_email_regra`.

O contrato com o App (fechado em 24/11/2026 com a sessão "App de campo sub"; o texto inteiro no `nexus/cadastro/CLAUDE.md`,
seção "E-mails automáticos"), do lado que o Nexus LÊ. Dois livros PRÓPRIOS (v380): o App publica cada livro com troca
integral, e uma aba nova no `email_app_campo` apagaria o "Envios" a cada publicação.
- `email_tipos_app_campo · Tipos`: uma linha por tipo — Tipo, Nome, Gatilho, Destino padrão (o PAPEL, nunca o endereço: a
  API do banco lê sem login), Ligado (sim/não), De onde vem a regra (Nexus | App Setting), Modo, Enviados 7d (envios, não
  destinatários), Falhas 7d, Último envio e Regra do Nexus em (ISO UTC);
- `email_todos_envios_app_campo · Todos os envios`: 1 linha = 1 destinatário de 1 envio, 30 dias — ID (`<quando>|<8
  hex>|<n>`: o que vem antes do último "|" é o envio), Tipo, Referência (sem nome nem e-mail), Destinatário (HMAC) (o
  `_pessoa_hmac`, inclusive das caixas como a do COS), Papel (a cópia vem como "cópia"), Quando (ISO UTC), Via, Situação
  (enviado | falhou | desligado | teste), Tentativas (vazia) e Erro (sem e-mail). Nasce no 1º envio depois da v380;
- `email_app_campo · Envios`: a de antes, só do e-mail semanal da Segurança (o fato `envio_email_seguranca` e a tela da
  Segurança dependem dela, e ela não muda). Enquanto o Todos os envios não existir, a tela mostra o semanal por ela.

Sem os livros, a tela mostra os tipos que o App tem (o `CATALOGO`, da v380) sem números: sem dado não se inventa. Puro:
nada de rede nem Flask; quem lê os livros é a tela (`torres/base/emails_tela.py`).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

LIVRO_TIPOS, ABA_TIPOS = "email_tipos_app_campo", "Tipos"
LIVRO_TODOS, ABA_TODOS = "email_todos_envios_app_campo", "Todos os envios"
LIVRO_SEMANAL, ABA_SEMANAL = "email_app_campo", "Envios"
DIAS = 7                    # a janela dos números da lista
HISTORICO_DIAS = 30         # o que o App guarda no Todos os envios

# os tipos da v380 (EMAIL_TIPOS do function_app.py, 24/11/2026), na ordem da tela; o livro Tipos, quando vier, manda no
# texto de cada um
CATALOGO = (
    ("pt_aviso", "PT aguardando assinatura", "Quando a PT nasce, e um lembrete aos 30 min se ninguém assinou",
     "Supervisor da usina (dia útil) · caixa do COS (fim de semana e feriado)"),
    ("luvas_tst", "Luvas isolantes com Não na ronda", "Uns 5 min depois que o técnico responde", "TST"),
    ("auditoria_diaria", "Auditoria diária", "Todo dia às 07:15", "Quem acompanha a auditoria"),
    ("seguranca_semanal", "Pendências da Segurança (semanal)", "Segunda de manhã, depois que o Nexus monta o resumo",
     "TST · supervisor responsável (com a TST em cópia)"),
    ("seguranca_relato", "Relato de acidente ou incêndio", "Na hora do relato", "TST"),
    ("encaminhamento", "Encaminhamento de demanda", "Quando alguém encaminha", "Quem recebeu o encaminhamento"),
    ("avulso", "E-mail avulso de teste", "Quando há item no email_avulso.json do App", "Quem testa"),
)
# desligar estes pede uma confirmação a mais na edição (quem deixaria de saber: a TST, o supervisor)
CRITICOS = frozenset({"pt_aviso", "seguranca_semanal", "seguranca_relato"})
# o que a confirmação diz, por tipo (o pedido de 24/11/2026: "dizendo que a TST ou o supervisor deixa de saber")
QUEM_DEIXA_DE_SABER = {
    "pt_aviso": "O supervisor da usina (e o COS no fim de semana e feriado) deixa de saber que há PT esperando a "
                "assinatura dele: a PT pode ficar parada e a equipe esperando em campo.",
    "seguranca_semanal": "A TST e os supervisores responsáveis deixam de receber as pendências da Segurança da semana.",
    "seguranca_relato": "A TST deixa de saber, na hora, de um acidente ou incêndio relatado no App.",
}
SITUACAO = {"enviado": ("ok", "Enviado"), "teste": ("info", "Teste"), "pendente": ("alerta", "Pendente"),
            "falhou": ("critico", "Falhou"), "vencido": ("critico", "Vencido"),
            "sem destinatário": ("alerta", "Sem destinatário"), "sem e-mail": ("alerta", "Sem e-mail"),
            "desligado": ("neutro", "Desligado")}
FALHAS = frozenset({"falhou", "vencido", "sem destinatário", "sem e-mail"})


def _t(v) -> str:
    return " ".join(str(v if v is not None else "").split())


def _quando(v) -> datetime | None:
    s = _t(v)
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _int(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _sim(v) -> bool | None:
    s = _t(v).lower()
    return True if s in ("sim", "true", "1", "ligado") else False if s in ("não", "nao", "false", "0", "desligado") else None


def _envio(id_linha: str) -> str:
    """O envio da linha: o ID é `<quando>|<8 hex>|<n>` (1 linha por destinatário); sem "|", a própria linha."""
    i = _t(id_linha)
    return i.rsplit("|", 1)[0] if "|" in i else i


def envios(todos: list[dict] | None, semanal: list[dict] | None) -> tuple[list[dict], str]:
    """(os envios normalizados, um por destinatário, de onde vieram: "todos" | "semanal" | "nenhum"). O Todos os envios
    manda; sem ele, o semanal da aba Envios (tipo seguranca_semanal)."""
    out = []
    if todos is not None:
        for n, r in enumerate(todos):
            out.append({"id": _t(r.get("ID")), "envio": _envio(r.get("ID")) or f"#{n}", "tipo": _t(r.get("Tipo")),
                        "referencia": _t(r.get("Referência")),
                        # o contrato chama a coluna "Destinatário (HMAC)"; a 1ª versão da tela lia "Destinatário"
                        "destinatario": _t(r.get("Destinatário (HMAC)") or r.get("Destinatário")),
                        "papel": _t(r.get("Papel")), "quando": _quando(r.get("Quando")), "via": _t(r.get("Via")),
                        "situacao": _t(r.get("Situação")).lower(), "tentativas": _int(r.get("Tentativas")),
                        "erro": _t(r.get("Erro"))})
        return out, "todos"
    if semanal is not None:
        for n, r in enumerate(semanal):
            out.append({"id": "", "envio": f"s{n}", "tipo": "seguranca_semanal", "referencia": _t(r.get("Semana")),
                        "destinatario": _t(r.get("Destinatário (HMAC)")), "papel": _t(r.get("Papel")),
                        # no livro a coluna é "Enviado em" (ISO UTC); o catálogo a chamava "Enviado em (UTC)"
                        "quando": _quando(r.get("Enviado em") or r.get("Enviado em (UTC)")), "via": _t(r.get("Via")),
                        "situacao": _t(r.get("Situação")).lower(), "tentativas": _int(r.get("Tentativas")),
                        "erro": _t(r.get("Erro"))})
        return out, "semanal"
    return [], "nenhum"


def quem(destinatario: str, nomes: dict, papel: str = "") -> str:
    """O destinatário para a tela: a pessoa ou a caixa pelo nome (o cadastro, o Fracttal, as listas das regras do
    Nexus), e o código que não casa com ninguém pelo papel ("Caixa do COS" é um código como os outros: o App manda o
    HMAC de todo endereço). O código nunca vai à tela (não volta a e-mail, mas é a chave da pessoa)."""
    d = _t(destinatario)
    if not d:
        return "—"
    if d.lower().startswith("caixa:"):
        return "Caixa " + d.split(":", 1)[1].strip()
    if nomes.get(d):
        return nomes[d]
    return f"Fora do cadastro ({papel})" if _t(papel) else "Fora do cadastro"


def _conta(es: list[dict]) -> tuple[int, int, int]:
    """(enviados, falhas, desligados) em ENVIOS, como o "Enviados 7d" do App: um envio com 3 destinatários conta 1. O
    envio com uma linha que falhou é falha."""
    sit: dict[str, set] = {}
    for e in es:
        sit.setdefault(e["envio"], set()).add(e["situacao"])
    env = sum(1 for s in sit.values() if s & {"enviado", "teste"} and not s & FALHAS)
    fal = sum(1 for s in sit.values() if s & FALHAS)
    des = sum(1 for s in sit.values() if s == {"desligado"})
    return env, fal, des


BRT = timezone(timedelta(hours=-3))      # o dia do gráfico é o de Brasília (o envio das 22h UTC-3 é do dia dele)
GRUPOS = ("enviado", "teste", "falhou", "barrado")


def _grupo(sits: set) -> str:
    """A situação de UM envio (com todas as linhas dele): falha vence, depois o barrado, o teste e o enviado."""
    if sits & FALHAS:
        return "falhou"
    if sits == {"desligado"}:
        return "barrado"
    if "teste" in sits:
        return "teste"
    if "enviado" in sits:
        return "enviado"
    return ""


def por_dia(es: list[dict], agora: datetime, dias: int = HISTORICO_DIAS) -> list[dict]:
    """Os envios de um tipo por dia de Brasília, do mais antigo ao de hoje (sempre `dias` dias, o dia sem envio com
    zero): [{dia, enviado, teste, falhou, barrado, total}]. Conta ENVIOS, como os números da lista (um aviso para três
    pessoas é um); o envio cai no dia da 1ª linha dele. Pendente não entra (ainda não é envio)."""
    hoje = agora.astimezone(BRT).date()
    inicio = hoje - timedelta(days=dias - 1)
    sits: dict[str, set] = {}
    quando: dict[str, datetime] = {}
    for e in es:
        if not e["quando"]:
            continue
        sits.setdefault(e["envio"], set()).add(e["situacao"])
        if e["envio"] not in quando or e["quando"] < quando[e["envio"]]:
            quando[e["envio"]] = e["quando"]
    linhas = {inicio + timedelta(days=n): dict.fromkeys(GRUPOS, 0) for n in range(dias)}
    for envio, s in sits.items():
        g, d = _grupo(s), quando[envio].astimezone(BRT).date()
        if g and d in linhas:
            linhas[d][g] += 1
    return [dict(v, dia=d, total=sum(v.values())) for d, v in linhas.items()]


def montar(tipos: list[dict] | None, todos: list[dict] | None, semanal: list[dict] | None, agora: datetime,
           regras: dict | None = None, catalogo=CATALOGO, criticos=CRITICOS) -> dict:
    """A lista da tela: {tipos: [{tipo, nome, gatilho, destino, ligado, origem, modo, regra_em, critico, enviados,
    falhas, desligados, ultimo, ultima_situacao, regra, pendente}], fonte, tem_tipos}. `ligado` None = o Nexus ainda não
    sabe (o App não publicou os Tipos). Os números são dos últimos `DIAS` dias, contados por envio; sem o livro dos
    envios, os do Tipos; sem nada, None (não zero). `regras` = as do Nexus que valem (`emails_controle.vigentes`);
    `pendente` = publicada aqui depois da que o App diz ter lido (o App relê a cada 5 min e publica os Tipos de hora em
    hora)."""
    lista, fonte = envios(todos, semanal)
    desde = agora - timedelta(days=DIAS)
    por_tipo: dict[str, list[dict]] = {}
    for e in lista:
        por_tipo.setdefault(e["tipo"], []).append(e)
    do_app = {_t(r.get("Tipo")): r for r in tipos or [] if _t(r.get("Tipo"))}
    # os e-mails do Nexus (25/11/2026) passam pela mesma conta, com o catálogo vazio: os tipos vêm todos em `tipos`
    ordem = [c[0] for c in catalogo] + [t for t in do_app if t not in {c[0] for c in catalogo}]
    padrao = {c[0]: c for c in catalogo}
    regras = regras or {}
    out = []
    for tipo in ordem:
        a, c = do_app.get(tipo) or {}, padrao.get(tipo) or (tipo, tipo, "", "")
        es = por_tipo.get(tipo) or []
        recentes = [e for e in es if e["quando"] and e["quando"] >= desde]
        ultimo = max((e for e in es if e["quando"]), key=lambda e: e["quando"], default=None)
        sabe = fonte == "todos" or (fonte == "semanal" and tipo == "seguranca_semanal")
        env, fal, des = _conta(recentes) if sabe else (None, None, None)
        if not sabe and a:
            # sem o livro dos envios, os números que o próprio App conta no Tipos
            env = _int(a.get("Enviados 7d")) if _t(a.get("Enviados 7d")) else None
            fal = _int(a.get("Falhas 7d")) if _t(a.get("Falhas 7d")) else None
        ult = ultimo["quando"] if ultimo else (_quando(a.get("Último envio")) if a else None)
        rg = regras.get(tipo)
        regra_em = _quando(a.get("Regra do Nexus em")) if a else None
        pendente = bool(rg) and (regra_em is None or (_quando(rg["alterado_em"]) or agora) > regra_em)
        out.append({"tipo": tipo, "nome": _t(a.get("Nome")) or c[1], "gatilho": _t(a.get("Gatilho")) or c[2],
                    "destino": _t(a.get("Destino padrão")) or c[3], "ligado": _sim(a.get("Ligado")) if a else None,
                    "origem": _t(a.get("De onde vem a regra")), "modo": _t(a.get("Modo")).lower(),
                    "regra_em": regra_em, "critico": tipo in criticos, "enviados": env, "falhas": fal,
                    "desligados": des, "ultimo": ult, "ultima_situacao": ultimo["situacao"] if ultimo else "",
                    "regra": rg, "pendente": pendente,
                    # o gráfico de 30 dias só com o livro que conta este tipo (None = o App ainda não diz)
                    "dias": por_dia(es, agora) if sabe else None})
    return {"tipos": out, "fonte": fonte, "tem_tipos": bool(do_app)}


def historico(todos: list[dict] | None, semanal: list[dict] | None, tipo: str, nomes: dict, agora: datetime) -> list[dict]:
    """Os envios de um tipo, um por destinatário, do mais novo para o mais antigo, dos últimos `HISTORICO_DIAS` dias:
    {quando, quem, papel, referencia, situacao, rotulo, tom, tentativas, erro, via, envio}."""
    lista, _f = envios(todos, semanal)
    desde = agora - timedelta(days=HISTORICO_DIAS)
    out = []
    for e in lista:
        if e["tipo"] != tipo or (e["quando"] and e["quando"] < desde):
            continue
        tom, rotulo = SITUACAO.get(e["situacao"], ("neutro", e["situacao"].capitalize() or "—"))
        out.append(dict(e, quem=quem(e["destinatario"], nomes, e["papel"]), tom=tom, rotulo=rotulo))
    return sorted(out, key=lambda e: e["quando"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
