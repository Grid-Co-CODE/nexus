"""A foto diária dos extintores fora do em dia (Segurança · HSEQ, 24/11/2026): o histórico que a tela não tinha.

O pedido (o mockup de Extintores aprovado pela Segurança, entrega 1): "hoje o Nexus só guarda a última conferência de
cada extintor, então não dá para saber o que estava vencido num dia passado. Cada dia sem a foto é um dia de histórico
perdido." A tela do histórico ("O que mudou nos atrasados", a entrega 3) lê daqui.

**O formato: só as mudanças, com a foto completa do mês** (a Segurança, 24/11/2026, depois da medida no banco real:
516 extintores fora do em dia num dia, ~188 mil linhas e 4,4 MB em um ano se cada dia fosse uma foto inteira; o
`livros.publicar` regrava e relê o livro a cada gravação, e o servidor também roda o banco). Livro
`nexus_hseq_extintores_historico`, registrado em `catalogo.py` antes da 1ª gravação, só acrescenta:
- `fato_extintor_dia`: 1 linha = 1 extintor num dia, de dois tipos (`tipo`). `completa`: a foto inteira, todos os
  extintores fora do em dia, no 1º dia de cada mês (e no 1º dia do livro). `mudanca`: só o extintor que entrou, saiu ou
  mudou de situação desde o dia anterior. A situação de um dia qualquer = a completa mais perto antes dele + as
  mudanças dali até ele (`estado_em`). Situação: `atrasado`, `perto`, `sem_validade` ou `em_dia` (com
  `sem_atualizacao` sim/não: o "sem atualização" soma às outras, como na tela) e, na mudança, `em_dia` (saiu da lista
  porque ficou em dia) ou `fora` (saiu da tela: excluído pela Segurança, marcado como não reconhecido, ou sumiu do
  livro do App). No atrasado, `venceu` diz o quê (recarga ou hidrostático).
- `fato_foto_dia`: 1 linha = 1 dia gravado, com os totais. **Dia sem esta linha é dia sem foto** (a API fora o dia
  inteiro): a tela mostra a lacuna, sem inventar.
No dia da completa, o estado montado pelas mudanças se compara com a foto: se não bate, o log diz quantos extintores
divergiram (só o número) e a completa vale.

Sem pessoa e sem cliente: o `usina_id` e o código do extintor (cadastro próprio do App) bastam.

A situação é a MESMA da tela: `extintores.extintores()` com as exclusões e as edições da Segurança
(`decisoes.separar`, que aplica o `aplicar_edicoes`), e os não reconhecidos fora das contas. Leitura que falha (o livro
do App, as decisões) não grava: a foto sem as exclusões diria vencido o extintor que a Segurança tirou.

Quando: a 1ª volta do laço depois das 06:00 de Brasília grava o dia, uma vez (o dia que já está no `fato_foto_dia` não
volta); a API fora, a volta seguinte tenta de novo. O laço é o `ligar`, chamado pelo `email_semanal.ligar` (que o
servir.py chama no servidor).
"""
import json
import logging
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from flask import current_app

from ..dados import fatos as D
from ..dados import livros

log = logging.getLogger("nexus.hseq")

LIVRO, NOME_LIVRO = "nexus_hseq_extintores_historico", "Nexus · foto diária dos extintores fora do em dia"
ABA, ABA_DIA = "fato_extintor_dia", "fato_foto_dia"
CAB = ("data_id", "tipo", "usina_id", "codigo", "situacao", "venceu", "sem_atualizacao")
CAB_DIA = ("data_id", "gravada_em", "completa", "extintores", "fora_do_em_dia", "linhas")
ABAS = ((ABA, CAB), (ABA_DIA, CAB_DIA))
HORA = 6                                    # a foto do dia sai depois das 06:00 de Brasília
SITUACOES = ("atrasado", "perto", "sem_validade", "em_dia")
SAIU = ("em_dia", "fora")                   # a mudança que tira o extintor da lista
_BRT = timezone(timedelta(hours=-3))
_LACO = {"thread": None, "parar": threading.Event(), "ultimo": None}
_TRAVA = threading.Lock()


def _agora() -> datetime:
    return datetime.now(_BRT)


def _data_id(d: date) -> int:
    return int(d.strftime("%Y%m%d"))


def _dia(data_id) -> date | None:
    try:
        return datetime.strptime(D._txt(data_id)[:8], "%Y%m%d").date()
    except ValueError:
        return None


def _int(v) -> int | None:
    try:
        return int(float(v)) if D._txt(v) else None
    except (TypeError, ValueError):
        return None


# ── a situação de hoje ────────────────────────────────────────────────────────────────────────────────────────────
def do_extintor(x: dict) -> dict:
    """A linha de um extintor da tela no formato do livro (sem o dia nem o tipo)."""
    return {"usina_id": x.get("usina_id") or "", "codigo": x["codigo"], "situacao": x["situacao"],
            "venceu": (x.get("vence_qual") or "") if x["situacao"] == "atrasado" else "",
            "sem_atualizacao": "sim" if x.get("sem_atualizacao") else "nao"}


def fora_do_em_dia(x: dict) -> bool:
    """Entra na foto: atrasado, perto de vencer, sem validade ou sem atualização (este soma às outras)."""
    return x["situacao"] != "em_dia" or bool(x.get("sem_atualizacao"))


def de_hoje(cfg, hoje: date) -> dict:
    """{"lista": [os extintores da tela, com as decisões], "erro"}: a MESMA conta da tela, no dia `hoje`. Erro quando o
    livro do App ou as decisões não foram lidos, ou quando a conta guardada ainda é de outro dia."""
    from . import decisoes as DEC
    from . import extintores as EXT
    leitura = EXT.extintores()
    d = leitura.dados or {}
    if leitura.erro or not d.get("livro_existe") or d.get("colunas_faltando"):
        return {"lista": [], "erro": f"livro do App sem leitura: {leitura.erro or 'ausente ou sem coluna'}"}
    if d.get("hoje") != hoje:
        return {"lista": [], "erro": f"a conta guardada é de {d.get('hoje')}, não de {hoje}"}
    est = DEC.ler(cfg, forcar=True)
    if est.get("erro"):
        return {"lista": [], "erro": f"decisões sem leitura: {est['erro']}"}
    ext, _nr, _exc = DEC.separar(d.get("extintores") or [], d.get("nao_reconhecidos") or [], est)
    return {"lista": ext, "erro": ""}


# ── o livro ───────────────────────────────────────────────────────────────────────────────────────────────────
def _arquivo_local(cfg) -> Path | None:
    p = cfg.get("NEXUS_HSEQ_EXTINTORES_HISTORICO_ARQUIVO")
    return Path(p) if p else None


def ler(cfg) -> dict:
    """{aba: [linhas]}. Livro que ainda não existe = vazio; erro de leitura sobe (quem grava não grava sem saber o que há).
    Teste sem o arquivo nunca vai à rede."""
    loc = _arquivo_local(cfg)
    if loc is not None:
        try:
            d = json.loads(loc.read_text(encoding="utf-8"))
        except FileNotFoundError:
            d = {}
        return {a: [dict(x) for x in d.get(a) or []] for a, _cab in ABAS}
    if cfg.get("TESTING"):
        return {a: [] for a, _cab in ABAS}
    from ..pcm.motivos import _banco
    base, sessao = _banco(cfg)
    a = livros.abas_conferidas(base, sessao, LIVRO, tuple(aba for aba, _cab in ABAS))
    return {aba: (list(livros._linhas(base, sessao, a[aba])) if aba in a else []) for aba, _cab in ABAS}


def _gravar(cfg, cru: dict) -> None:
    vazio = (lambda v: None if v in ("", None) else v)      # noqa: E731
    tabelas = {aba: (list(cab), [[vazio(x.get(c)) for c in cab] for x in cru[aba]]) for aba, cab in ABAS}
    loc = _arquivo_local(cfg)
    if loc is not None:
        loc.parent.mkdir(parents=True, exist_ok=True)
        tmp = loc.with_suffix(".tmp")
        tmp.write_text(json.dumps({a: [dict(zip(cab, l)) for l in corpo] for a, (cab, corpo) in tabelas.items()},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(loc)
        return
    token = cfg.get("GRIDCO_SQL_TOKEN")
    if not token:
        raise RuntimeError("sem a GRIDCO_SQL_TOKEN")
    from ..pcm.motivos import _banco
    base, sessao = _banco(cfg)
    livros.publicar(LIVRO, NOME_LIVRO, tabelas, base=base, token=token, sessao=sessao)


# ── a conta de um dia ─────────────────────────────────────────────────────────────────────────────────────────
def _chave(x: dict) -> tuple:
    return (D._txt(x.get("situacao")), D._txt(x.get("venceu")), D._txt(x.get("sem_atualizacao")))


def estado_em(cru: dict, dia: date) -> dict | None:
    """{código: linha} dos extintores fora do em dia no fim do `dia`: a completa mais perto antes dele (ou nele) + as
    mudanças depois dela até ele. None sem completa até o dia (antes da 1ª foto: a tela estima, entrega 3)."""
    ate = _data_id(dia)
    linhas = [x for x in cru.get(ABA) or [] if (_int(x.get("data_id")) or 0) <= ate]
    completas = sorted({_int(x["data_id"]) for x in linhas if D._txt(x.get("tipo")) == "completa"})
    if not completas:
        return None
    ini = completas[-1]
    est = {D._txt(x["codigo"]): dict(x) for x in linhas
           if D._txt(x.get("tipo")) == "completa" and _int(x["data_id"]) == ini}
    for x in sorted((x for x in linhas if D._txt(x.get("tipo")) == "mudanca" and _int(x["data_id"]) > ini),
                    key=lambda x: _int(x["data_id"])):
        cod = D._txt(x["codigo"])
        if D._txt(x.get("situacao")) in SAIU and D._txt(x.get("sem_atualizacao")) != "sim":
            est.pop(cod, None)
        else:
            est[cod] = dict(x)
    return est


def dias_gravados(cru: dict) -> set:
    """Os dias com foto (`fato_foto_dia`): o dia fora daqui é lacuna."""
    return {d for d in (_dia(x.get("data_id")) for x in cru.get(ABA_DIA) or []) if d}


def montar_dia(cru: dict, lista: list, hoje: date) -> tuple[list, dict]:
    """(as linhas novas do `fato_extintor_dia`, a linha do `fato_foto_dia`) do dia `hoje`, a partir dos extintores da
    tela (`lista`). A completa no 1º dia do mês e no 1º dia do livro; nos outros, só as mudanças desde o último estado."""
    did = _data_id(hoje)
    agora = {x["codigo"]: do_extintor(x) for x in lista if fora_do_em_dia(x)}
    na_tela = {x["codigo"]: x for x in lista}
    antes = estado_em(cru, hoje - timedelta(days=1))
    completa = antes is None or hoje.day == 1
    if completa:
        if antes is not None:
            diverge = (set(antes) ^ set(agora)) | {c for c in set(antes) & set(agora) if _chave(antes[c]) != _chave(agora[c])}
            if diverge:
                # só o número: o código do extintor não é pessoal, mas o log não precisa dele
                log.warning("foto completa dos extintores de %s: %d extintores divergiram do estado montado pelas "
                            "mudanças; vale a foto completa", hoje.isoformat(), len(diverge))
        novas = [dict(v, data_id=did, tipo="completa") for v in agora.values()]
    else:
        novas = [dict(v, data_id=did, tipo="mudanca") for c, v in agora.items()
                 if c not in antes or _chave(antes[c]) != _chave(v)]
        for c, v in antes.items():
            if c in agora:
                continue
            x = na_tela.get(c)
            novas.append({"data_id": did, "tipo": "mudanca", "usina_id": (x or v).get("usina_id") or "", "codigo": c,
                          "situacao": "em_dia" if x else "fora", "venceu": "", "sem_atualizacao": "nao"})
    dia = {"data_id": did, "gravada_em": _agora().isoformat(timespec="seconds"), "completa": "sim" if completa else "nao",
           "extintores": len(lista), "fora_do_em_dia": len(agora), "linhas": len(novas)}
    return sorted(novas, key=lambda x: x["codigo"]), dia


def publicar(cfg, agora: datetime | None = None) -> dict:
    """Grava a foto do dia, uma vez: {gravou, dia, linhas, completa, erro}. Antes das 06:00, com o dia já no livro ou
    com uma leitura que falhou, não grava (o laço tenta de novo na volta seguinte)."""
    agora = agora or _agora()
    hoje = agora.date()
    if agora.hour < HORA:
        return {"gravou": False, "dia": hoje.isoformat(), "erro": ""}
    with _TRAVA:
        cru = ler(cfg)
        if hoje in dias_gravados(cru):
            return {"gravou": False, "dia": hoje.isoformat(), "erro": ""}
        h = de_hoje(cfg, hoje)
        if h["erro"]:
            return {"gravou": False, "dia": hoje.isoformat(), "erro": h["erro"]}
        novas, dia = montar_dia(cru, h["lista"], hoje)
        cru = {ABA: cru[ABA] + novas, ABA_DIA: cru[ABA_DIA] + [dia]}
        _gravar(cfg, cru)
    return {"gravou": True, "dia": hoje.isoformat(), "linhas": len(novas), "completa": dia["completa"] == "sim",
            "erro": ""}


# ── o laço ────────────────────────────────────────────────────────────────────────────────────────────────────
def ligado(cfg) -> bool:
    """Grava nesta máquina? Sim no servidor; não onde NEXUS_HSEQ_EXT_FOTO_AUTO=0 nem onde NEXUS_CAMPO_AQUECER=0 (o PC)."""
    return (str(cfg.get("NEXUS_HSEQ_EXT_FOTO_AUTO", "1") or "1").strip() != "0"
            and str(cfg.get("NEXUS_CAMPO_AQUECER", "1") or "1").strip() != "0")


def ligar(app):
    """O laço: a cada 10 min, depois das 06:00 de Brasília, grava a foto do dia (uma vez). Só onde `ligado`. Quem chama
    é o `email_semanal.ligar` (o servir.py, no servidor), nunca o create_app: teste não fala com a rede."""
    if _LACO["thread"] is not None or not ligado(app.config):
        return

    def laco():
        espera = 180
        while not _LACO["parar"].wait(espera):
            espera = 600
            if _agora().hour < HORA:
                continue
            with app.app_context():
                try:
                    _LACO["ultimo"] = publicar(current_app.config)
                    if _LACO["ultimo"].get("gravou") or _LACO["ultimo"].get("erro"):
                        log.info("foto diária dos extintores: %s", _LACO["ultimo"])
                except Exception as e:      # noqa: BLE001 — o laço não morre por uma volta
                    _LACO["ultimo"] = {"erro": f"{type(e).__name__}: {e}"[:300]}
                    log.exception("foto diária dos extintores")

    from ..casca import fracttal_conta              # o laço declara o fundo: só o declarado tem o teto de 90 do porteiro
    _LACO["thread"] = threading.Thread(target=fracttal_conta.de_fundo("fundo:nexus-hseq-ext-foto", laco),
                                       name="nexus-hseq-ext-foto", daemon=True)
    _LACO["thread"].start()
