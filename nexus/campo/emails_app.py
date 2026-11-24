"""Os e-mails automáticos do App de Campo, vistos pelo Nexus (24/11/2026).

Levi, pela sessão do App: "Gostaria de poder controlar esses e-mails automáticos ou ter pelo menos um controle! E
gostaria que estivesse no Nexus". O App manda pelo Microsoft Graph (naoresponda@), com os destinatários nas configurações
dele no Azure; o Nexus mostra o que sai, para quem e se saiu (Base › E-mails automáticos, só administrador). A edição
(ligar e desligar, modo teste, destinatários) vem depois, pelo livro `nexus_email_controle · fato_email_regra`.

O contrato com o App (fechado em 24/11/2026 com a sessão "App de campo sub"), do lado que o Nexus LÊ:
- `email_app_campo · Tipos`: uma linha por tipo — Tipo, Nome, Gatilho, Destino padrão (o PAPEL, nunca o endereço: a API
  do banco lê sem login), Ligado, De onde vem a regra (App Setting | Nexus), Enviados 7d, Falhas 7d, Último envio;
- `email_app_campo · Todos os envios`: grão 1 envio, 30 dias — ID, Tipo, Referência (OS, PT ou usina, sem nome de
  pessoa), Destinatário (o código HMAC da pessoa; caixa sem pessoa = "caixa:COS", "caixa:TST"...), Papel, Quando (ISO
  UTC), Via, Situação (enviado | falhou | pendente | vencido | sem destinatário | desligado | teste), Tentativas, Erro
  (só o código e o texto curto, sem e-mail nem nome);
- `email_app_campo · Envios`: a de antes, só do e-mail semanal da Segurança (o fato `envio_email_seguranca` do catálogo e a
  tela da Segurança dependem dela, e ela não muda). Enquanto a aba nova não existir, a tela mostra o semanal por ela.

Sem o livro, a tela mostra os tipos que o App tem (o `CATALOGO`, como a sessão do App descreveu em 24/11) sem números:
sem dado não se inventa. Puro: nada de rede nem Flask; quem lê os livros é a tela (`torres/base/emails_tela.py`).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

LIVRO = "email_app_campo"
ABA_TIPOS, ABA_TODOS, ABA_SEMANAL = "Tipos", "Todos os envios", "Envios"
DIAS = 7                    # a janela dos números da lista
HISTORICO_DIAS = 30         # o que o App guarda na aba de todos os envios

# os tipos de hoje (App v378, 24/11/2026), na ordem da tela; o livro Tipos, quando vier, manda no texto de cada um
CATALOGO = (
    ("pt_aviso", "PT aguardando assinatura", "Quando a PT nasce, e um lembrete aos 30 min",
     "Supervisor da usina (dia útil) ou a caixa do COS (fim de semana e feriado)"),
    ("luvas_tst", "Luvas isolantes reprovadas na ronda", "Uns 5 min depois do \"Não\" nas luvas", "TST"),
    ("auditoria_diaria", "Auditoria diária", "Todo dia às 07:15, com o PDF", "A lista da auditoria"),
    ("seguranca_semanal", "E-mail semanal da Segurança", "Segunda de manhã",
     "TST e responsáveis O&M (a lista que o Nexus publica)"),
    ("seguranca_relato", "Relato de acidente ou incêndio", "Na hora do relato", "Segurança (sem lista própria, a TST)"),
    ("encaminhamento", "Encaminhamento", "Quando alguém recebe um encaminhamento", "Quem recebe"),
)
# desligar estes pede uma confirmação a mais na edição (quem deixaria de saber: a TST, o supervisor)
CRITICOS = frozenset({"pt_aviso", "seguranca_semanal", "seguranca_relato"})
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


def envios(todos: list[dict] | None, semanal: list[dict] | None) -> tuple[list[dict], str]:
    """(os envios normalizados, de onde vieram: "todos" | "semanal" | "nenhum"). A aba de todos os envios manda; sem ela,
    o semanal da aba Envios (tipo seguranca_semanal)."""
    out = []
    if todos is not None:
        for r in todos:
            out.append({"id": _t(r.get("ID")), "tipo": _t(r.get("Tipo")), "referencia": _t(r.get("Referência")),
                        "destinatario": _t(r.get("Destinatário")), "papel": _t(r.get("Papel")),
                        "quando": _quando(r.get("Quando")), "via": _t(r.get("Via")),
                        "situacao": _t(r.get("Situação")).lower(), "tentativas": _int(r.get("Tentativas")),
                        "erro": _t(r.get("Erro"))})
        return out, "todos"
    if semanal is not None:
        for r in semanal:
            out.append({"id": "", "tipo": "seguranca_semanal", "referencia": _t(r.get("Semana")),
                        "destinatario": _t(r.get("Destinatário (HMAC)")), "papel": _t(r.get("Papel")),
                        # no livro a coluna é "Enviado em" (ISO UTC); o catálogo a chamava "Enviado em (UTC)"
                        "quando": _quando(r.get("Enviado em") or r.get("Enviado em (UTC)")), "via": _t(r.get("Via")),
                        "situacao": _t(r.get("Situação")).lower(), "tentativas": _int(r.get("Tentativas")),
                        "erro": _t(r.get("Erro"))})
        return out, "semanal"
    return [], "nenhum"


def quem(destinatario: str, nomes: dict) -> str:
    """O destinatário para a tela: a caixa pelo nome dela, a pessoa pelo nome (do cadastro do App ou da ficha do
    Registro mestre com e-mail), e o código que não casa com ninguém como "sem e-mail no cadastro" (o código não volta a
    e-mail)."""
    d = _t(destinatario)
    if not d:
        return "—"
    if d.lower().startswith("caixa:"):
        return "Caixa " + d.split(":", 1)[1].strip()
    return nomes.get(d) or "Pessoa sem e-mail no cadastro"


def montar(tipos: list[dict] | None, todos: list[dict] | None, semanal: list[dict] | None, agora: datetime) -> dict:
    """A lista da tela: {tipos: [{tipo, nome, gatilho, destino, ligado, origem, critico, enviados, falhas, ultimo,
    ultima_situacao}], fonte, tem_tipos}. `ligado` None = o Nexus ainda não sabe (o App não publicou os Tipos). Os números
    são dos últimos `DIAS` dias, contados no envio; sem envio nenhum do tipo, ficam None (não zero)."""
    lista, fonte = envios(todos, semanal)
    desde = agora - timedelta(days=DIAS)
    por_tipo: dict[str, list[dict]] = {}
    for e in lista:
        por_tipo.setdefault(e["tipo"], []).append(e)
    do_app = {_t(r.get("Tipo")): r for r in tipos or [] if _t(r.get("Tipo"))}
    ordem = [c[0] for c in CATALOGO] + [t for t in do_app if t not in {c[0] for c in CATALOGO}]
    padrao = {c[0]: c for c in CATALOGO}
    out = []
    for tipo in ordem:
        a, c = do_app.get(tipo) or {}, padrao.get(tipo) or (tipo, tipo, "", "")
        es = por_tipo.get(tipo) or []
        recentes = [e for e in es if e["quando"] and e["quando"] >= desde]
        ultimo = max((e for e in es if e["quando"]), key=lambda e: e["quando"], default=None)
        sabe = fonte == "todos" or (fonte == "semanal" and tipo == "seguranca_semanal")
        out.append({"tipo": tipo, "nome": _t(a.get("Nome")) or c[1], "gatilho": _t(a.get("Gatilho")) or c[2],
                    "destino": _t(a.get("Destino padrão")) or c[3], "ligado": _sim(a.get("Ligado")) if a else None,
                    "origem": _t(a.get("De onde vem a regra")), "critico": tipo in CRITICOS,
                    "enviados": sum(1 for e in recentes if e["situacao"] == "enviado") if sabe else None,
                    "falhas": sum(1 for e in recentes if e["situacao"] in FALHAS) if sabe else None,
                    "ultimo": ultimo["quando"] if ultimo else None,
                    "ultima_situacao": ultimo["situacao"] if ultimo else ""})
    return {"tipos": out, "fonte": fonte, "tem_tipos": bool(do_app)}


def historico(todos: list[dict] | None, semanal: list[dict] | None, tipo: str, nomes: dict, agora: datetime) -> list[dict]:
    """Os envios de um tipo, do mais novo para o mais antigo, dos últimos `HISTORICO_DIAS` dias: {quando, quem, papel,
    referencia, situacao, rotulo, tom, tentativas, erro, via}."""
    lista, _f = envios(todos, semanal)
    desde = agora - timedelta(days=HISTORICO_DIAS)
    out = []
    for e in lista:
        if e["tipo"] != tipo or (e["quando"] and e["quando"] < desde):
            continue
        tom, rotulo = SITUACAO.get(e["situacao"], ("neutro", e["situacao"].capitalize() or "—"))
        out.append(dict(e, quem=quem(e["destinatario"], nomes), tom=tom, rotulo=rotulo))
    return sorted(out, key=lambda e: e["quando"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
