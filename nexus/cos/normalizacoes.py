"""Normalizações (27/10/2026, Levi: "Gostaria de inserir no COS" a API de normalizações da Ronda COS): quando cada usina
voltou, pela hora que o COS registrou, e se a OS dela segue aberta no Fracttal.

Por que existe: o Fracttal só encerra a OS quando o técnico a fecha, muitas vezes horas ou dias depois da volta. Na
semana até 27/10/2026 foram 341 normalizações, e 208 delas ainda tinham a OS aberta no Fracttal (a OS 16702, de
Mandaguaçu, normalizada em 19/10 às 05:53, oito dias depois seguia "em processo").

De onde: `GET <Andamento>/api/normalizacoes` (contrato `versao: 1`, guia em docs do dono da Ronda COS), com a mesma chave
das outras telas do COS. A API é incremental: devolve um `cursor`, e o pedido seguinte com `desde=<cursor>` traz só o que
mudou. Aqui o Nexus guarda em memória as normalizações dos últimos 30 dias, por `registro` (o mesmo `registro` pode vir
de novo, com o estado novo: substitui), e pergunta o que mudou a cada minuto. Nada vai ao banco: a tela só lê.

O que é regra de lá e o Nexus não refaz: o que é normalização, a hora da volta (`normalizado_em`, já corrigida quando
alguém corrigiu), o tempo fora, a OS aberta no Fracttal (a varredura de 30 em 30 min de lá). Daqui são só os filtros, as
contas da faixa e o "há quanto tempo a OS segue aberta depois da volta".

**A tela vira "Ocorrências" (12/11/2026, protótipo aprovado pelo dono antes do porte):** as ocorrências EM ANDAMENTO entram
na mesma lista, no mesmo formato de linha, no topo, e o filtro "Situação" separa as duas (o dono recusou a tela nova
desenhada do zero: "segue o padrão da tela de Normalizações"). Elas vêm da fotografia de cada cliente (o que está aberto
agora, de qualquer data: a Santarém aberta desde julho aparece), com o detalhe do ciclo de 7 dias e o status da OS pelo
Panorama das OS abertas (`andamento`). Só no mês corrente: o mês é o da volta, e a em andamento ainda não voltou. Os números
da faixa das normalizadas (total, OS aberta, mediana, hora real) seguem contando só as normalizadas.
"""
import threading
import time
import urllib.parse
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median

from . import andamento as AND
from . import os_abertas as OA

VERSAO = 1
# Por mês (27/10/2026, Levi: "a única mudança que quero é ver por mês"; e depois "Pode tirar esses filtros de 7, 30 dias
# ou último dia"): o mês corrente (o padrão) e os anteriores, só DESDE outubro de 2026 (29/10/2026: "quero apenas de
# outubro para frente, não precisa carregar os outros meses"; até ali eram 3 meses, e a 1ª carga trazia agosto e setembro).
# A memória guarda desde o 1º dia de PRIMEIRO_MES, ~1.500 normalizações por mês.
PRIMEIRO_MES = (2026, 10)
MESES_NOME = ("Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro",
              "Novembro", "Dezembro")
# A cada minuto pergunta o que mudou (o guia: "se `mais` for false, espere 1 minuto").
TTL_S = 60
# A primeira carga de 30 dias vem em páginas: 300 itens levam ~2 s lá. Teto de páginas por pedido da tela, para ninguém
# esperar a carga inteira de uma vez; o resto vem nos pedidos seguintes, e a tela diz que está carregando.
PAGINA = 500
PAGINAS_POR_PEDIDO = 4
TIMEOUT_S = 15

# O status da OS aberta no Fracttal (o mesmo das OS em aberto). O segundo valor é o que o card da OS espera.
STATUS_OS = {1: ("Em processo", "Em Processo"), 2: ("Em verificação", "Em Verificação")}
# O filtro "Status Fracttal" (Levi, 27/10/2026): as duas abertas e a fechada (a OS que não está entre as abertas na
# última varredura: finalizada ou cancelada).
STATUS_FILTRO = {"processo": "Em processo", "verificacao": "Em verificação", "fechada": "Fechada"}
# Por onde a normalização foi registrada (`declarada_por`). Era "Operador" para `pessoa` até 27/10/2026, e o Levi
# perguntou o que queria dizer: é que uma pessoa do COS registrou a volta na Ronda COS (o nome a API não manda).
DECLARADA_POR = {"pessoa": "registrada pelo COS", "sistema": "registrada pelo sistema", "fracttal": "pelo Fracttal",
                 "religamento_remoto": "por religamento remoto", "criacao_da_os": "na criação da OS"}
BUSCA_MAX = 80
# A conferência da OS (`conferencia_da_os.situacao`, a Ronda COS relê a OS no Fracttal de 10 em 10 min; Levi, 29/10/2026:
# "quero proteções, geração_parou e conferência da OS na tabela"): o rótulo e o tom da casa. SEM_LEITURA é "ainda não
# lida", nunca "sem problema" (o guia, seção 9)
CONFERENCIA = {
    "AGUARDANDO_TECNICO": ("Aguardando técnico", "info"),
    "HORA_A_CORRIGIR": ("Hora a corrigir", "alerta"),
    "HORA_CONFERE": ("Hora confere", "neutro"),
    "FINALIZADA": ("Finalizada", "ok"),
    "TRAVADA": ("Travada", "critico"),
    "SEM_LEITURA": ("Ainda não lida", "neutro"),
}

_estado: dict[str, dict] = {}
_trava = threading.Lock()          # a memória
_trava_carga = threading.Lock()    # um pedido ao Andamento por vez (a primeira carga leva segundos)


@dataclass
class Painel:
    itens: list = field(default_factory=list)
    # todas as do mês (as normalizadas), da mais nova; `visiveis` = os registros da lista filtrada. A tela manda todas e
    # esconde as de fora do filtro do endereço: o filtro é da página (29/10/2026)
    todos: list = field(default_factory=list)
    visiveis: set = field(default_factory=set)
    contagem: dict = field(default_factory=dict)
    resumo: dict = field(default_factory=dict)
    varredura: datetime | None = None
    desfeitas: int = 0
    carregando: bool = False
    # as em andamento (12/11/2026): todas as de agora, da aberta mais nova; filtradas na página como as normalizadas
    # (os registros que passam no filtro do endereço também estão em `visiveis`)
    andamento: list = field(default_factory=list)
    com_andamento: bool = False          # o mês corrente: a lista leva as em andamento e o filtro Situação aparece


def _mes_de(d: datetime) -> datetime:
    return d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _mes_seguinte(d: datetime) -> datetime:
    return _mes_de(d.replace(day=28) + timedelta(days=4))


def meses(agora: datetime) -> list[tuple[str, str, datetime, datetime]]:
    """(chave "2026-10", rótulo, começo, começo do seguinte), do mês corrente para trás. O ano só no rótulo de mês de
    outro ano."""
    out, ini = [], _mes_de(agora)
    while True:                      # o corrente sempre; os de antes, até PRIMEIRO_MES
        rot = MESES_NOME[ini.month - 1] + ("" if ini.year == agora.year else f" de {ini.year}")
        out.append((ini.strftime("%Y-%m"), rot, ini, _mes_seguinte(ini)))
        ini = _mes_de(ini - timedelta(days=1))
        if (ini.year, ini.month) < PRIMEIRO_MES:
            return out


def inicio_da_guarda(agora: datetime) -> datetime:
    """Desde quando a memória guarda: o 1º dia do mês mais antigo da tela."""
    return meses(agora)[-1][2]


def mes_pedido(v, agora: datetime) -> str:
    """O mês pedido ("2026-10"), ou o corrente."""
    ms = meses(agora)
    return v if v in {m[0] for m in ms} else ms[0][0]


def limpar() -> None:
    with _trava:
        _estado.clear()


def validar(d) -> dict:
    if not isinstance(d, dict):
        raise AND.FonteErro("a resposta do Andamento não é um objeto")
    if d.get("versao") != VERSAO:
        raise AND.FonteErro(f"o Andamento fala a versão {d.get('versao')!r} das normalizações, e o Nexus entende a "
                            f"{VERSAO}")
    if not isinstance(d.get("normalizacoes"), list) or not isinstance(d.get("cursor"), str):
        raise AND.FonteErro("a resposta do Andamento não tem as normalizações")
    return d


def _data_da(n: dict) -> datetime | None:
    return AND.instante(n.get("normalizado_em")) or AND.instante(n.get("inicio"))


def ler(config, agora: datetime | None = None) -> AND.Leitura:
    """As normalizações guardadas (`dados = {"itens": [...], "carregando": bool}`), postas em dia se a última pergunta
    tem mais de 1 minuto. Na falha, a memória continua, dita velha.

    A cópia completa que venceu volta NA HORA, e a pergunta ao Andamento vai por trás (uma de cada vez; 29/10/2026, Levi:
    a tela "inventa de carregar sempre que clico"): o clique que caía depois do minuto esperava a Ronda COS responder (com
    ela a 3 s, o filtro levava 3,2 s), e todos os que abriam a tela esperavam juntos na trava da carga. Sem cópia, ou com
    a 1ª carga pela metade ("carregando"), a leitura é na hora, como antes."""
    f = AND.fonte(config)
    if not f.ligada:
        return AND.Leitura("", None, erro="a fonte do Andamento não está ligada neste servidor")
    agora = agora or AND.agora()
    with _trava:
        st = _estado.get(f.url)
        if st and st["completo"] and time.monotonic() - st["perguntado"] >= TTL_S:
            if not st.get("renovando"):
                st["renovando"] = True
                threading.Thread(target=_renovar, args=(f,), name="nexus-cos-normalizacoes", daemon=True).start()
            return _leitura(st)
    return _buscar(f, agora)


def _renovar(f) -> None:
    """A pergunta ao Andamento por trás da cópia vencida; o estado novo substitui o velho (e com ele a marca)."""
    try:
        _buscar(f, AND.agora())
    finally:
        with _trava:
            st = _estado.get(f.url)
            if st:
                st.pop("renovando", None)


def _buscar(f, agora: datetime) -> AND.Leitura:
    with _trava_carga:
        with _trava:
            st = _estado.get(f.url)
            # em dia há menos de 1 minuto, ou falhou há menos de 1 minuto (o Andamento fora não segura cada tela 15 s)
            if st and (st["completo"] or st.get("erro")) and time.monotonic() - st["perguntado"] < TTL_S:
                return _leitura(st)
            st = st or {"itens": {}, "cursor": "", "completo": False, "perguntado": 0.0, "lido_em": None}
        desde = st["cursor"] or inicio_da_guarda(agora).isoformat()
        itens, cursor, completo, erro = dict(st["itens"]), st["cursor"], False, ""
        try:
            for _ in range(PAGINAS_POR_PEDIDO):
                q = urllib.parse.urlencode({"desde": desde, "limite": PAGINA})
                d = validar(AND._pedir(f, "/api/normalizacoes?" + q, timeout=TIMEOUT_S))
                for n in d["normalizacoes"]:
                    if isinstance(n, dict) and n.get("registro"):
                        itens[str(n["registro"])] = n          # o mesmo registro volta com o estado novo: substitui
                cursor = desde = d["cursor"]
                if not d.get("mais"):
                    completo = True
                    break
        except AND.FonteErro as ex:
            erro = ("o Andamento ainda não tem a rota das normalizações, ou ela está desligada lá"
                    if ex.codigo == 404 else str(ex))
        corte = inicio_da_guarda(agora)
        itens = {k: n for k, n in itens.items() if (_data_da(n) or agora) >= corte}
        with _trava:
            if erro and not st["itens"] and not itens:
                return AND.Leitura("", None, erro=erro)
            novo = {"itens": itens, "cursor": cursor, "completo": completo or (bool(erro) and st["completo"]),
                    "perguntado": time.monotonic(), "lido_em": st["lido_em"] if erro else time.time(), "erro": erro}
            _estado[f.url] = novo
            return _leitura(novo)


def _leitura(st: dict) -> AND.Leitura:
    erro = st.get("erro", "")
    return AND.Leitura("", {"itens": list(st["itens"].values()), "carregando": not st["completo"]},
                       lido_em=st["lido_em"], erro=erro, velha=bool(erro))


# ── o que a tela mostra (puro) ───────────────────────────────────────────────────────────────────────────────────────
def duracao(minutos) -> str:
    """O tempo em minutos e horas, nunca em dias (Levi, 27/10/2026: "Conta em minutos e horas"): "45 min", "3 h 05",
    "75 h"."""
    try:
        m = max(0, int(minutos))
    except (TypeError, ValueError):
        return "—"
    if m < 60:
        return f"{m} min"
    h, r = divmod(m, 60)
    return f"{h} h {r:02d}" if r else f"{h} h"


def _minutos(v):
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _conferencia(c) -> dict | None:
    """A conferência da OS para a tela e o CSV; None quando a OS não foi criada pela Ronda COS (ou a normalização foi
    desfeita): a API manda null."""
    if not isinstance(c, dict):
        return None
    sit = str(c.get("situacao") or "").upper()
    rot, tom = CONFERENCIA.get(sit, (sit.replace("_", " ").capitalize() or "—", "neutro"))
    return {"situacao": sit, "rotulo": rot, "tom": tom, "tarefas": _minutos(c.get("tarefas")),
            "concluidas": _minutos(c.get("concluidas")), "dif_inicio": _minutos(c.get("diferenca_inicio_min")),
            "dif_fim": _minutos(c.get("diferenca_fim_min")),
            "inicio_fracttal": AND.instante(c.get("inicio_no_fracttal")),
            "conclusao_fracttal": AND.instante(c.get("conclusao_no_fracttal")),
            "finalizada_em": AND.instante(c.get("finalizada_em")), "lida_em": AND.instante(c.get("lida_em"))}


def _detalhes(d) -> dict:
    d = d if isinstance(d, dict) else {}
    notas = [str(x).strip() for x in d.get("notas") or [] if str(x or "").strip()]
    return {"acao": " ".join(str(d.get("acao") or "").split()), "descricao": str(d.get("descricao") or "").strip(),
            "notas": notas}


def _item(n: dict, agora: datetime) -> dict:
    volta = AND.instante(n.get("normalizado_em"))
    sev = str(n.get("severidade") or "").upper()
    aberta = n.get("os_aberta_no_fracttal") if isinstance(n.get("os_aberta_no_fracttal"), dict) else None
    status = STATUS_OS.get(aberta.get("status"), (f"status {aberta.get('status')}", "")) if aberta else ("", "")
    equip = [e for e in n.get("equipamentos") or [] if isinstance(e, dict)]
    informe = n.get("informe") if isinstance(n.get("informe"), dict) else {}
    try:
        fora = int(n.get("fora_min")) if n.get("fora_min") is not None else None
    except (TypeError, ValueError):
        fora = None
    return {
        "registro": str(n.get("registro")),
        "os": str(n.get("os") or "").strip(),
        "os_relacionadas": [str(x) for x in n.get("os_relacionadas") or [] if str(x).strip()],
        "cliente": str(n.get("cliente") or "").strip() or "(sem cliente)",
        "usina": str(n.get("usina") or n.get("usina_codigo") or "").strip() or "(sem usina)",
        "usina_codigo": str(n.get("usina_codigo") or ""),
        "equipamentos": [str(e.get("nome") or e.get("codigo") or "") for e in equip],
        "falha": str(n.get("tipo_falha_rotulo") or n.get("tipo_falha") or "").strip() or "—",
        "severidade": sev,
        "normalizada": n.get("normalizada") is not False,
        "inicio": AND.instante(n.get("inicio")),
        "volta": volta,
        "data": volta or AND.instante(n.get("inicio")),
        "fora": fora,
        "fora_txt": duracao(fora) if fora is not None else "—",
        "hora_real": n.get("hora_real") is not False,
        "fim_corrigido": bool(n.get("fim_corrigido")),
        "declarada_por": DECLARADA_POR.get(str(n.get("declarada_por") or ""), str(n.get("declarada_por") or "") or "—"),
        "aberta": bool(aberta),
        "status_filtro": ({1: "processo", 2: "verificacao"}.get(aberta.get("status"), "outro") if aberta
                          else "fechada"),
        "status": status[0],
        "status_card": status[1],
        "pct": int((aberta or {}).get("concluida_pct") or 0),
        "aberta_ha_dias": (agora - volta).days if aberta and volta else None,
        "varrida_em": AND.instante((aberta or {}).get("varrida_em")),
        "resumo": str(informe.get("resumo") or "").strip()[:160],
        # os dois nomes de pessoa que a API manda desde 28/10/2026 (o guia, seção 5): quem abriu a OS (o operador de
        # plantão; vazio quando a OS já existia e só foi ligada à ocorrência) e o técnico atribuído no Fracttal (quem a
        # recebeu, não prova quem foi ao local). Só na tela e no CSV: o Nexus não os guarda
        "operador": " ".join(str(n.get("os_aberta_por") or "").split()),
        "tecnico": " ".join(str(n.get("tecnico") or "").split()),
        "fora_do_escopo": bool(n.get("fora_do_escopo_oem")),
        # 29/10/2026: as proteções que atuaram (como o time escreve), a resposta do operador na falha de comunicação
        # (a geração parou? None nos outros tipos e antes de 28/10) e a OS do Fracttal contra a normalização do COS
        "protecoes": [" ".join(str(x).split()) for x in n.get("protecoes") or [] if str(x or "").strip()],
        "geracao_parou": n.get("geracao_parou") if isinstance(n.get("geracao_parou"), bool) else None,
        "conferencia": _conferencia(n.get("conferencia_da_os")),
        "situacao": "normalizada",
        # o "Detalhes da Atividade" do informe (29/10/2026, Levi: "quero o campo detalhes no normalizações"): a ação, a
        # descrição da ocorrência (sem o planejamento do PCM) e as notas das pessoas. Texto livre do time, às vezes com
        # nome e telefone: só na tela e no CSV, o Nexus não guarda (o guia da API, seção 2.3)
        **_detalhes(n.get("detalhes")),
    }


def alvo_da_busca(i: dict) -> str:
    """O texto em que a busca procura; a página leva o mesmo em cada linha (`data-f-busca`) e o JS procura igual. A em
    andamento leva também a etapa (técnico acionado, aguardando peça...)."""
    return " ".join([i["os"], *i["os_relacionadas"], i["cliente"], i["usina"], i["usina_codigo"], i["falha"],
                     *i["equipamentos"], i["operador"], i["tecnico"], i["resumo"], i["status"], i["acao"],
                     i["descricao"], *i["notas"], *([i["etapa"]] if i.get("etapa") else [])]).lower()


def _casa(i: dict, q: str) -> bool:
    q = q.lower()
    if q.isdigit() and (i["os"] == q or q in i["os_relacionadas"]):
        return True
    return q in alvo_da_busca(i)


# ── as em andamento (12/11/2026) ─────────────────────────────────────────────────────────────────────────────────────
# O filtro "Situação" (o dono, 11/11/2026: a tela unificada "segue o padrão da tela de Normalizações", com as normalizadas e
# as em andamento e um filtro que separa as duas).
SITUACAO_FILTRO = {"andamento": "Em andamento", "normalizada": "Normalizadas"}
# A "Geração parou" da em andamento, pela regra da Ronda COS (`paradaPeloTipo`, geracao-na-normalizacao.ts): os
# desligamentos e a atuação de proteção param o ativo pela própria definição, desde a abertura. Na falha de comunicação e
# no inversor offline a resposta só vem na normalização; e, pela regra do dono de 09/11/2026, falha de comunicação com a
# geração parada não existe (é desligamento): a aberta assim fica "a conferir". O resto (string, tracker, ventilador) não
# tem a pergunta.
PARAM_PELO_TIPO = frozenset({"DESLIGAMENTO_USINA", "DESLIGAMENTO_CABINE", "DESLIGAMENTO_QGBT", "DESLIGAMENTO_SKID",
                             "DESLIGAMENTO_INVERSOR", "ATUACAO_PROTECAO"})
PERGUNTA_NA_VOLTA = frozenset({"FALHA_COMUNICACAO", "INVERSOR_OFFLINE"})
# A OS aberta há menos disto e fora do Panorama ainda não passou pela varredura do Fracttal (de 30 em 30 min na Ronda COS):
# "Nova", e não "Fechada". O mesmo OS_NOVA_MIN da tela Prazos da R04 (nexus/cos/ocorrencias.py).
OS_NOVA_MIN = 40
# O tempo aberto em minutos e horas até 48 h; depois, em dias (a Santarém aberta desde julho daria "2.900 h").
DIAS_DEPOIS_DE_H = 48


def _codigo_do_tipo(o7: dict, rotulo: str) -> str:
    """O código do tipo (`DESLIGAMENTO_USINA`...): o da ocorrência de 7 dias; sem ela (a aberta há mais de 7 dias), pelo
    rótulo da fotografia."""
    if o7.get("tipo_falha_codigo"):
        return str(o7["tipo_falha_codigo"]).upper()
    r = (rotulo or "").lower()
    if r.startswith("desligamento") or r.startswith("atuação de proteção"):
        return "DESLIGAMENTO_USINA"
    if r.startswith("falha de comunica"):
        return "FALHA_COMUNICACAO"
    if r.startswith("inversor offline"):
        return "INVERSOR_OFFLINE"
    return ""


def _geracao_andamento(codigo: str, impacto: str) -> str | None:
    """"sim" (o tipo para a geração desde a abertura), "conferir" (falha de comunicação ou inversor offline aberto com a
    geração interrompida), "na_volta" (a pergunta é feita na normalização) ou None (o tipo não tem a pergunta)."""
    if codigo in PARAM_PELO_TIPO:
        return "sim"
    if codigo in PERGUNTA_NA_VOLTA:
        imp = (impacto or "").lower()
        return "conferir" if "interromp" in imp or imp.startswith("gera") else "na_volta"
    return None


def _tempo_aberto(minutos) -> str:
    if minutos is None:
        return "—"
    return duracao(minutos) if minutos < DIAS_DEPOIS_DE_H * 60 else f"{minutos // 1440} dias"


def _equipamentos(lista) -> list[str]:
    out = []
    for x in lista or []:
        nome = (x.get("nome") or x.get("codigo")) if isinstance(x, dict) else x
        if str(nome or "").strip():
            out.append(" ".join(str(nome).split()))
    return out


def _fracttal_andamento(folio: str, o7: dict, os_map: dict, varredura, agora: datetime) -> dict:
    """A célula "No Fracttal" da em andamento: o status da OS no Panorama das abertas (a varredura de 30 em 30 min), o que
    a ocorrência de 7 dias diz da OS, a OS nova que a varredura ainda não viu, ou fechada (a ocorrência segue aberta no COS
    com a OS já fechada no Fracttal)."""
    vazio = {"rotulo": "", "tom": "", "det": "", "filtro": "outro", "status": "", "status_card": "", "aberta": False,
             "pct": 0}
    if not folio:
        return vazio
    m = os_map.get(folio)
    if m:
        sit = "feita, falta finalizar" if m["situacao"] == "concluida" else "pendente"
        alerta = " · alerta: sem reconhecimento há +1 h" if m["em_alerta"] else ""
        return dict(vazio, rotulo=f"{m['status']} {m['pct']}%", tom="critico" if m["em_alerta"] else "alerta",
                    det=f"{sit} · OS aberta há {m['aberta_ha']}{alerta}",
                    filtro="verificacao" if "verifica" in m["status"].lower() else "processo", status=m["status"],
                    status_card=m["status_card"], aberta=True, pct=m["pct"])
    f = o7.get("os_fracttal")
    if isinstance(f, dict) and f:
        st = STATUS_OS.get(f.get("status"), ("Aberta", ""))
        pct = int(f.get("concluida_pct") or 0)
        return dict(vazio, rotulo=f"{st[0]} {pct}%", tom="alerta",
                    filtro={1: "processo", 2: "verificacao"}.get(f.get("status"), "outro"), status=st[0],
                    status_card=st[1], aberta=True, pct=pct)
    aberta_em = AND.instante(o7.get("os_aberta_em"))
    if aberta_em and ((varredura and aberta_em > varredura) or agora - aberta_em < timedelta(minutes=OS_NOVA_MIN)):
        return dict(vazio, rotulo="Nova", tom="neutro", filtro="processo", status="Nova",
                    det=f"aberta {aberta_em.astimezone(AND._BRT):%H:%M}; entra na varredura do Fracttal")
    return dict(vazio, rotulo="Fechada", tom="ok", filtro="fechada", status="Fechada")


def _item_andamento(cliente: str, u: dict, o: dict, o7: dict | None, os_map: dict, varredura,
                    agora: datetime) -> dict:
    """A ocorrência em andamento no formato da normalização (as mesmas chaves de `_item`, para a busca, o filtro e o CSV),
    com o que só ela tem: a etapa, o que aguarda, a "Geração parou" pelo tipo e a célula do Fracttal."""
    o7 = o7 or {}
    folio = str(o.get("os") or o7.get("os") or "").strip()
    if folio.startswith("R-"):                       # a ocorrência sem OS: a fotografia manda o registro curto
        folio = ""
    ini = AND.instante(o7.get("inicio")) or AND.instante(o.get("abertura"))
    minutos = max(0, int((agora - ini).total_seconds() // 60)) if ini else None
    falha = str(o7.get("tipo_falha") or o.get("tipo_falha") or "").strip() or "—"
    fr = _fracttal_andamento(folio, o7, os_map, varredura, agora)
    prot = [" ".join(str(x).split()) for x in o7.get("protecoes") or [] if str(x or "").strip()]
    if not prot and o.get("protecao") and str(o["protecao"]).strip() != "Sem proteção ativa":
        prot = [" ".join(str(o["protecao"]).split())]
    notas = [str((x.get("texto") if isinstance(x, dict) else x) or "").strip() for x in o7.get("notas") or []]
    notas = [x for x in notas if x]
    un = o.get("ultima_nota")
    if not notas and isinstance(un, dict) and str(un.get("texto") or "").strip():
        q = AND.instante(un.get("quando"))
        notas = [(f"{q.astimezone(AND._BRT):%d/%m %H:%M} · " if q else "") + str(un["texto"]).strip()]
    return {
        "registro": str(o.get("registro") or o7.get("registro") or ""),
        "os": folio,
        "os_relacionadas": [],
        "cliente": str(cliente or "").strip().upper() or "(sem cliente)",    # a grafia da API das normalizações
        "usina": str(o7.get("usina") or u.get("nome") or "").strip() or "(sem usina)",
        "usina_codigo": str(u.get("codigo") or o7.get("usina_codigo") or ""),
        "equipamentos": _equipamentos(o.get("equipamentos") or o7.get("equipamentos")),
        "falha": falha,
        "severidade": str(o7.get("severidade") or "").upper(),
        "normalizada": False,
        "inicio": ini,
        "volta": None,
        "data": ini,
        "fora": minutos,
        "fora_txt": _tempo_aberto(minutos),
        "hora_real": False,
        "fim_corrigido": False,
        "declarada_por": "",
        "aberta": fr["aberta"],
        "status_filtro": fr["filtro"],
        "status": fr["status"],
        "status_card": fr["status_card"],
        "pct": fr["pct"],
        "aberta_ha_dias": None,
        "varrida_em": None,
        "resumo": "",
        "operador": " ".join(str(o7.get("os_aberta_por") or "").split()),
        "tecnico": " ".join(str(o7.get("tecnico") or "").split()),
        "fora_do_escopo": False,
        "protecoes": prot,
        "geracao_parou": None,
        "conferencia": None,
        "acao": " ".join(str(o7.get("acao") or o.get("tipo_tarefa") or "").split()),
        "descricao": str(o7.get("descricao") or " · ".join(str(x) for x in (o.get("falha"), o.get("impacto")) if x)).strip(),
        "notas": notas,
        "situacao": "andamento",
        "etapa": " ".join(str(o7.get("estado_rotulo") or o.get("etapa") or "aberta").split()),
        "aguardando": ", ".join(" ".join(str(a).split()) for a in o.get("aguardando") or [] if str(a or "").strip()),
        "dias_andamento": minutos // 1440 if minutos is not None else 0,
        "geracao": _geracao_andamento(_codigo_do_tipo(o7, falha), str(o.get("impacto") or "")),
        "impacto": str(o.get("impacto") or "").strip(),
        "fracttal": fr,
    }


def andamento(fotografias, ocorrencias: dict, os_abertas, agora: datetime) -> list[dict]:
    """As ocorrências em andamento de todos os clientes, da que começou por último. `fotografias`: [(cliente, dados da
    fotografia)] (o que está aberto agora em cada usina, de qualquer data); `ocorrencias`: {registro: a do ciclo de 7 dias}
    (o detalhe: início, tipo, proteções, notas, quem abriu a OS); `os_abertas`: os dados do Panorama das OS abertas (o
    status no Fracttal), ou None. A mesma ocorrência em duas usinas da fotografia entra uma vez; a que a Ronda COS já diz
    normalizada no ciclo de 7 dias, não entra (a fotografia é da hora)."""
    os_map, varredura = {}, None
    if isinstance(os_abertas, dict):
        varredura = AND.instante(os_abertas.get("varredura_em"))
        for o in os_abertas.get("os") or []:
            if isinstance(o, dict) and o.get("folio") is not None:
                os_map[str(o["folio"])] = OA._item(o, agora)
    vistos, out = set(), []
    for cliente, dados in fotografias:
        for u in (dados or {}).get("usinas") or []:
            for o in u.get("ocorrencias") or []:
                reg = str(o.get("registro") or "")
                o7 = (ocorrencias or {}).get(reg)
                if not reg or reg in vistos or (o7 and o7.get("normalizada")):
                    continue
                vistos.add(reg)
                out.append(_item_andamento(cliente, u, o, o7, os_map, varredura, agora))
    out.sort(key=lambda i: i["data"] or agora, reverse=True)
    return out


def painel(leitura, agora: datetime, mes: str = "", cliente: str = "", usina: str = "", status: str = "",
           busca: str = "", operador: str = "", tecnico: str = "", falha: str = "", situacao: str = "",
           andamento: list | None = None) -> Painel | None:
    """A tela, do mês pedido (o corrente no padrão), pela hora da volta. Os filtros (Levi, 27/10/2026): cliente, usina,
    status no Fracttal e um texto livre; desde 28/10/2026 também o operador que abriu a OS ("Criado por") e o técnico, que
    a API passou a mandar. As opções de cada filtro contam sobre o mês, ANTES dos outros filtros (um contador que encolhe ao filtrar não diz mais quanto existe); as de usina, dentro do cliente escolhido.
    A faixa conta a lista filtrada, menos o status (senão a fatia aberta seria sempre 100%). A desfeita (a ocorrência
    voltou a aberta) fica fora da lista e é contada à parte; a sem hora real fica na lista e fora da mediana.

    `andamento` (12/11/2026, a tela Ocorrências): as em andamento (`andamento()`), que entram só no mês corrente, no topo,
    com os mesmos filtros e mais a Situação. Os números das normalizadas seguem só delas; as em andamento têm o seu.
    Sem `andamento` (None), a tela é a de Normalizações como era."""
    d = leitura.dados if leitura else None
    if not d:
        return None
    um_mes = next(m for m in meses(agora) if m[0] == mes_pedido(mes, agora))
    desde, ate = um_mes[2], um_mes[3]
    corrente = um_mes[0] == meses(agora)[0][0]
    todos = [_item(n, agora) for n in d.get("itens") or []]
    no_mes = [i for i in todos if i["data"] and desde <= i["data"] < ate]
    base = [i for i in no_mes if i["normalizada"]]
    com_andamento = corrente and andamento is not None
    ja = {i["registro"] for i in todos if i["normalizada"]}
    em_andamento = [i for i in andamento or () if i["registro"] not in ja] if com_andamento else []
    situacao = situacao if com_andamento and situacao in SITUACAO_FILTRO else ""
    busca = " ".join((busca or "").split())[:BUSCA_MAX]

    def passa(i):
        return ((not cliente or i["cliente"] == cliente) and (not usina or i["usina"] == usina)
                and (not operador or i["operador"] == operador) and (not tecnico or i["tecnico"] == tecnico)
                # o tipo de falha (29/10/2026, Levi: "quero um filtro para saber se foi falha de comunicação ou
                # desligamento"): pelo rótulo da Ronda COS, com os tipos que existem no mês
                and (not falha or i["falha"] == falha)
                and (not busca or _casa(i, busca)))
    recorte = [i for i in base if passa(i)] if situacao != "andamento" else []
    recorte_and = [i for i in em_andamento if passa(i)] if situacao != "normalizada" else []

    def no_status(lista):
        return [i for i in lista if i["status_filtro"] == status] if status in STATUS_FILTRO else list(lista)
    lista = no_status(recorte)
    lista.sort(key=lambda i: i["data"], reverse=True)
    lista_and = no_status(recorte_and)
    com_hora = [i["fora"] for i in recorte if i["hora_real"] and i["fora"] is not None]
    abertas = [i for i in recorte if i["aberta"]]
    varridas = [i["varrida_em"] for i in todos if i["varrida_em"]]
    contaveis = em_andamento + base                  # as opções contam as duas, antes dos filtros
    do_cliente = [i for i in contaveis if not cliente or i["cliente"] == cliente]
    todos = em_andamento + sorted(base, key=lambda i: i["data"], reverse=True)
    for i in todos:
        i["busca"] = alvo_da_busca(i)
    return Painel(
        itens=lista_and + lista,
        todos=todos,
        visiveis={i["registro"] for i in lista_and + lista},
        contagem={
            "cliente": dict(sorted(Counter(i["cliente"] for i in contaveis).items())),
            "usina": dict(sorted(Counter(i["usina"] for i in do_cliente).items())),
            "status": {k: sum(1 for i in contaveis if i["status_filtro"] == k) for k in STATUS_FILTRO},
            "operador": dict(sorted(Counter(i["operador"] for i in contaveis if i["operador"]).items())),
            "tecnico": dict(sorted(Counter(i["tecnico"] for i in contaveis if i["tecnico"]).items())),
            "falha": dict(Counter(i["falha"] for i in contaveis).most_common()),
            # a Situação só existe com as em andamento (no mês corrente)
            **({"situacao": {"andamento": len(em_andamento), "normalizada": len(base)}} if com_andamento else {}),
        },
        resumo={
            "total": len(recorte),
            "abertas": len(abertas),
            "abertas_pct": round(100 * len(abertas) / len(recorte)) if recorte else 0,
            "abertas_7d": sum(1 for i in abertas if (i["aberta_ha_dias"] or 0) >= 7),
            "mediana": duracao(median(com_hora)) if com_hora else "—",
            "sem_hora_real": sum(1 for i in recorte if not i["hora_real"]),
            "andamento": len(recorte_and),
            "andamento_7d": sum(1 for i in recorte_and if i["dias_andamento"] >= 7),
        },
        varredura=max(varridas) if varridas else None,
        desfeitas=sum(1 for i in no_mes if not i["normalizada"]),
        carregando=bool(d.get("carregando")),
        andamento=em_andamento,
        com_andamento=com_andamento,
    )


# O "Exportar CSV" (Levi, 27/10/2026): a lista da tela, com os filtros, e o que a tela resume numa coluna só. A Situação
# (12/11/2026) vai no fim, para as colunas de antes não mudarem de lugar.
CSV_COLUNAS = ("OS", "OS relacionadas", "Indisponível (min)", "Início", "Normalização", "Hora real da volta",
               "Hora corrigida", "Registrada", "Cliente", "Código da usina", "Usina", "Falha", "Equipamentos",
               "Severidade", "Aberta por (operador)", "Técnico", "Status no Fracttal", "% concluída", "Dias aberta depois da volta",
               "Informe", "Fora do escopo O&M", "Proteções", "Geração parou", "Conferência da OS",
               "Tarefas concluídas", "Data do evento no Fracttal", "Diferença do início (min)",
               "Conclusão no Fracttal", "Diferença da conclusão (min)", "Finalizada no Fracttal em",
               "Conferência lida em", "Ação", "Descrição da ocorrência", "Notas", "Situação")


def _csv_andamento(i: dict, h) -> list:
    fr = i["fracttal"]
    sit = "Em andamento · " + i["etapa"] + (f" · aguardando {i['aguardando']}" if i["aguardando"] else "")
    return [i["os"], "", "" if i["fora"] is None else i["fora"], h(i["inicio"]), "", "", "", "", i["cliente"],
            i["usina_codigo"], i["usina"], i["falha"], ", ".join(i["equipamentos"]), i["severidade"].title(),
            i["operador"], i["tecnico"], fr["status"], fr["pct"] if fr["aberta"] else "", "", "", "não",
            ", ".join(i["protecoes"]), "sim (pelo tipo)" if i["geracao"] == "sim" else "", *[""] * 8, i["acao"],
            i["descricao"], " | ".join(i["notas"]), sit]


def csv_linhas(p: Painel) -> list[list]:
    def h(d):
        return d.strftime("%d/%m/%Y %H:%M") if d else ""
    return [_csv_andamento(i, h) if i.get("situacao") == "andamento" else
            [i["os"], ", ".join(i["os_relacionadas"]), "" if i["fora"] is None else i["fora"], h(i["inicio"]),
             h(i["volta"]), "sim" if i["hora_real"] else "não",
             "sim" if i["fim_corrigido"] else "não", i["declarada_por"], i["cliente"], i["usina_codigo"], i["usina"],
             i["falha"], ", ".join(i["equipamentos"]), i["severidade"].title(), i["operador"], i["tecnico"],
             i["status"] if i["aberta"] else "Fechada", i["pct"] if i["aberta"] else "",
             "" if i["aberta_ha_dias"] is None else i["aberta_ha_dias"], i["resumo"],
             "sim" if i["fora_do_escopo"] else "não", ", ".join(i["protecoes"]),
             {True: "sim", False: "não"}.get(i["geracao_parou"], ""), *_csv_conferencia(i["conferencia"], h),
             i["acao"], i["descricao"], " | ".join(i["notas"]), "Normalizada"]
            for i in p.itens]


def _csv_conferencia(c, h) -> list:
    if not c:
        return [""] * 8
    tarefas = f"{c['concluidas']}/{c['tarefas']}" if c["tarefas"] is not None and c["concluidas"] is not None else ""
    return [c["rotulo"], tarefas, h(c["inicio_fracttal"]), "" if c["dif_inicio"] is None else c["dif_inicio"],
            h(c["conclusao_fracttal"]), "" if c["dif_fim"] is None else c["dif_fim"], h(c["finalizada_em"]),
            h(c["lida_em"])]
