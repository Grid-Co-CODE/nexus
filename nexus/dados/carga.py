"""A carga da camada de dados: lê os livros de origem e o cadastro, grava as dimensões e os fatos com os IDs.

De hora em hora, aos :40 (os livros do App chegam aos :25), dentro do processo do Nexus. Só lê a API do banco (e o
`banco_dados.json` público do PCM, o mesmo arquivo nas duas máquinas) e grava no banco: não toca em Fracttal, API PV
nem SunOp. Duas máquinas com o Nexus no ar (o PC do Levi e o servidor) não gravam em dobro: a carga só grava se a
última tiver mais de `INTERVALO_MIN` minutos (a hora fica no próprio livro, aba `atualizacao`); a que chegar depois,
pula. `NEXUS_CARGA_DADOS=0` desliga numa máquina.

Livros que esta carga mantém (registrados em `catalogo.LIVROS`):
- `nexus_dimensoes`: `dim_data` (o calendário), `feriados_locais`, `pessoas_historico` e `usinas_historico` (o
  histórico SCD2, `historico.py`), `qualidade_historico` e `atualizacao`. Se o histórico anterior veio vazio com o
  livro já gravado, o livro NÃO é gravado nesta hora (`segurar_dimensoes`): seria trocar o histórico por nada.
- `nexus_fatos`: `fato_fechamento`, `fato_ronda` (o fato único de ronda), `fato_pt`, `qualidade` (uma linha por fato)
  e `atualizacao`.
- `nexus_equipamentos` (08/10/2026): `dim_equipamento`, `equipamento_apelido`, `qualidade`, `atualizacao`. Montada
  ANTES dos fatos (eles levam o `equipamento_id`); gravada só quando o sha das linhas muda (muda por semana; ~1 MB) e
  só quando todas as fontes foram lidas (o PCM fora do ar numa hora tiraria da dimensão o que só ele tem).
- `nexus_programacao` (08/10/2026, decisão 7): `fato_programacao`, `qualidade`, `atualizacao`, pela MESCLA POR SEMANA
  (`_programacao`): a fonte guarda 4 semanas, então a carga lê o fato do banco, troca só as semanas do arquivo e mantém
  as outras. Leitura que falha ou volta vazia com o livro existente não grava (o fato não encolhe); grava só quando o
  sha das linhas muda.

Montado e NÃO gravado (só `ferramentas/carregar_dados.py --ensaio`, até a decisão do Levi):
- `nexus_geracao · fato_geracao_usina_dia` (`montar_geracao`, cadência DIÁRIA; decisão 8: publicar o de-para das abas,
  o teto, o IPOA; o inversor × dia não cabe em troca integral).

Isolamento (revisão de 08/10/2026, regra 13 do CLAUDE.md da pasta): peça nova que falha (o grão da ronda ou da PT, a
fonte da dimensão de equipamento fora do ar, o SCD2) fica como está no banco nesta hora e o resto anda; cada livro grava
sozinho e o erro de um sobe no fim. Só a fonte do fechamento e o cadastro derrubam a carga inteira, como antes.

O que esta carga HERDA dos passos 0 e 1 (adiados pelo Levi em 08/10/2026), escrito para ninguém achar que está
resolvido:
- Tudo é troca integral (`sync-xlsx?replace=true`) refeita da origem a cada hora. Os livros do App guardam 90 dias: a
  ronda de 11/08 sai do `fato_ronda` em ~09/11/2026, a PT de 28/09 sai do `fato_pt` em ~27/12/2026, o fechamento sai
  com 90 dias. O checklist da carga única e a avulsa não se perdem (livros próprios).
- Origem lida vazia (livro que some = [] em `livros.ler`) encolhe o fato e é gravada. Recusar carga encolhida é o
  passo 1. Até lá, `rel["encolheram"]` e o `extra` da qualidade mostram as linhas da carga anterior.
"""
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from . import almoxarifado as almox
from . import calendario, equipamento, fato_almoxarifado, fato_pt, fato_ronda, fatos, geracao, historico, livros
from . import programacao

LIVRO_DIM, NOME_DIM = "nexus_dimensoes", "Nexus · dimensões (calendário, feriados, histórico de pessoas e usinas)"
LIVRO_FATOS, NOME_FATOS = "nexus_fatos", "Nexus · fatos com os IDs do cadastro e a qualidade da ligação"
ORIGEM_FECHAMENTOS = ("fechamentos_app_campo", "Fechamentos")
ORIGEM_RONDAS, ORIGEM_CHECKLIST, ORIGEM_AVULSAS = fato_ronda.FONTES
ORIGEM_PT = fato_pt.FONTES[0]
DE_PARA_TRACKERS = ("de_para_trackers", "De-Para Trackers")
GEMEO_ALIAS = ("gemeo_digital", "alias")
CADASTRO = "cadastro_nexus"
INTERVALO_MIN = 50
MINUTO_DA_HORA = 40
CAB_ATUALIZACAO = ["gerado_em", "maquina", "duracao_s", "linhas", "como_ler"]
_BRT = timezone(timedelta(hours=-3))
log = logging.getLogger("nexus.dados")
_LACO = {"thread": None, "parar": threading.Event(), "ultimo": None}


def _agora():
    return datetime.now(_BRT)


def _base(config) -> str:
    from ..cadastro.ligacoes import BASE_API
    return (config.get("GRIDCO_DB_API") or BASE_API).rstrip("/")


def _maquina() -> str:
    return "servidor" if os.name != "nt" else "pc"


def ultima(base, sessao) -> datetime | None:
    for l in livros.ler(base, sessao, LIVRO_FATOS, "atualizacao"):
        try:
            return datetime.fromisoformat(str(l.get("gerado_em")))
        except (TypeError, ValueError):
            return None
    return None


def _feriados(config) -> dict:
    """Os feriados dos insumos do PCM (o mesmo arquivo que o motor lê). Sem o arquivo, calendário sem feriado."""
    try:
        from ..pcm import geracao as pcm_geracao, insumos
        return insumos.carregar(pcm_geracao.pasta_trabalho(config)).get("feriados") or {}
    except Exception:       # noqa: BLE001 — sem insumos nesta máquina
        return {}


def _mapas(config, sessao) -> dict:
    """{"hmac": {código do e-mail: pessoa_id}, "pessoa": {nome normalizado: pessoa_id}} pelo cadastro decifrado na
    hora (`ligacao_cadastro.mapas`, uma leitura só para o fato inteiro). Sem NEXUS_CHAVE_CADASTRO, vazio; sem
    NEXUS_PESSOA_HMAC, o mapa dos códigos vem vazio. O nome só fica na memória: nunca vai ao fato."""
    if not config.get("NEXUS_CHAVE_CADASTRO"):
        return {}
    from ..campo.ligacao_cadastro import mapas
    return _sem_chave_sem_codigo(config, mapas(config, sessao))


def mapas_das_linhas(config, de_para: list[dict], pessoas: list[dict]) -> dict:
    """O `_mapas` com as linhas do cadastro que quem chama já leu: as telas do Campo montam o fato na hora (passo 4 do
    Kimball, 08/10/2026) com a MESMA tradução da carga, sem reler o cadastro."""
    if not config.get("NEXUS_CHAVE_CADASTRO"):
        return {}
    from ..campo.ligacao_cadastro import mapas_de
    return _sem_chave_sem_codigo(config, mapas_de(config, de_para, pessoas))


def _sem_chave_sem_codigo(config, m: dict) -> dict:
    if not config.get("NEXUS_PESSOA_HMAC"):
        m["hmac"] = {}
    return m


def ligador(cad: dict, m: dict) -> fatos.Ligador:
    """O `Ligador` dos fatos do Campo, o MESMO na carga e nas telas (passo 4 do Kimball, 08/10/2026): usina pelo de-para
    do Fracttal (código do ativo de reserva), equipe pelo nome, pessoa pelo código HMAC do e-mail. `cad` = as abas
    `usinas`, `de_para` e `equipes` do cadastro; `m` = `_mapas` / `mapas_das_linhas`."""
    return fatos.Ligador(cad["usinas"], cad["de_para"], cad["equipes"], m.get("hmac") or {})


# ── A montagem dos fatos do Campo: UMA só, para a carga (que grava) e para as telas (passo 4 do Kimball, 08/10/2026) ──
# Levi, 08/10: as telas tiram a contagem e a ligação do fato conformado; enquanto o banco não tem o fato desta hora, a
# tela monta o fato na hora com ESTAS funções. `ler(livro, aba)` lê a fonte: o `_Leitor` da carga ou o `_livro` da tela.
def montar_fechamento(ler, lig, equip=None) -> tuple[list, list]:
    """(linhas do `fato_fechamento`, linhas de origem)."""
    fech = ler(*ORIGEM_FECHAMENTOS)
    return fatos.fato_fechamento(fech, lig, equip), fech


def montar_ronda(ler, lig, m: dict, equip=None) -> tuple[list, list, list]:
    """(linhas do `fato_ronda`, origem_q, avulsas lidas). O nome em claro do livro só liga a pessoa na memória
    (`m["pessoa"]`); o código do nome (`fato_ronda.codigo_do_nome`) segue desligado (decisão do Levi)."""
    app_r, ck, av = ler(*ORIGEM_RONDAS), ler(*ORIGEM_CHECKLIST), ler(*ORIGEM_AVULSAS)
    linhas, oq = fato_ronda.fato_ronda(app_r, ck, av, lig, m.get("pessoa") or {}, None, equip)
    return linhas, oq, av


def montar_pt(ler, lig, equip=None, *, agora=None) -> tuple[list, list]:
    """(linhas do `fato_pt`, linhas de origem). `agora`: a hora da conta (a `parada` de quem ainda espera)."""
    pt = ler(*ORIGEM_PT)
    return fato_pt.fato_pt(pt, lig, equip, agora=agora), pt


def _pessoas_por_codigo(config, sessao) -> dict:
    """{código HMAC do e-mail: pessoa_id}. Sem as duas chaves, vazio (a ferramenta do checklist usa)."""
    if not (config.get("NEXUS_PESSOA_HMAC") and config.get("NEXUS_CHAVE_CADASTRO")):
        return {}
    return _mapas(config, sessao).get("hmac") or {}


class _Leitor:
    """Lê do banco com UMA listagem de abas por carga (o `livros.ler` relista todas as abas do banco a cada chamada)
    e guarda o que já leu: os livros do App servem ao fato e à dimensão de equipamento sem ler duas vezes."""

    def __init__(self, base, sessao):
        self.base, self.s, self._cache = base, sessao, {}
        r = sessao.get(f"{base}/api/sheets", timeout=60)
        r.raise_for_status()
        self._abas = {}
        for x in r.json():
            self._abas.setdefault(x.get("workbook_key"), {})[x["sheet_name"]] = x["id"]
        r = sessao.get(f"{base}/api/workbooks", timeout=60)
        r.raise_for_status()
        self.atualizado = {w.get("key"): w.get("updated_at") or w.get("atualizado_em") for w in r.json()}

    def abas(self, livro) -> dict:
        return dict(self._abas.get(livro) or {})

    def ler(self, livro, aba) -> list[dict]:
        if (livro, aba) not in self._cache:
            sid = self._abas.get(livro, {}).get(aba)
            self._cache[(livro, aba)] = livros._linhas(self.base, self.s, sid) if sid else []
        return self._cache[(livro, aba)]

    def primeiras(self, livro) -> dict:
        """{aba: [1ª linha]} de cada aba do livro (o cabeçalho), em paralelo: ~8 s nas 171 abas de geração contra
        43–65 s lendo as abas inteiras (medido em 08/10)."""
        def uma(item):
            aba, sid = item
            r = self.s.get(f"{self.base}/api/sheets/{sid}/rows", params={"limit": 1, "offset": 0}, timeout=60)
            r.raise_for_status()
            rows = r.json()
            rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
            return aba, [dict(zip(x.get("headers") or [], x.get("values") or [])) for x in rows[:1]]
        with ThreadPoolExecutor(max_workers=6) as ex:
            return dict(ex.map(uma, sorted(self.abas(livro).items())))


def _colunas_de_geracao(le: _Leitor, de_para) -> tuple[list, str]:
    """As colunas "Inversor n.m" das abas de geração já ligadas a uma usina (o que vira apelido `BD_* · coluna`).
    Sem os sistemas de aba publicados no de-para (é do Levi, decisão 8), nenhuma aba liga e a resposta é [] SEMPRE,
    sem ler nada: vir igual toda hora é o que impede o sha da dimensão de oscilar e regravar o livro."""
    sistemas = set(geracao.SISTEMA_ABA.values())
    if not any(str(d.get("sistema") or "").strip() in sistemas for d in de_para or ()):
        return [], "de-para das abas de geração não publicado"
    prim = {f: le.primeiras(f) for f in geracao.FONTES}
    return (equipamento.colunas_de_geracao(geracao.cabecalhos(prim), geracao.usinas_das_abas(prim, de_para)),
            "cabeçalhos lidos")


def _ler_pcm(config):
    """(dados, lido_em) do `banco_dados.json` do PCM; sem a fonte (testes, rede fora), (None, None)."""
    try:
        from ..pcm import fonte
        leit = fonte.ler(config)
    except Exception:       # noqa: BLE001 — a carga não morre porque o GitHub do PCM não respondeu
        return None, None
    em = datetime.fromtimestamp(leit.baixado_em, _BRT).isoformat(timespec="seconds") if leit.baixado_em else None
    return leit.dados, em


def _extra(q: dict, **mais) -> dict:
    e = json.loads(q.get("extra") or "{}")
    e.update({k: v for k, v in mais.items() if v is not None})
    q["extra"] = json.dumps(e, ensure_ascii=False, sort_keys=True)
    return q


def _resumo_q(q: dict) -> dict:
    return {k: q.get(f"pct_{k}") for k in ("data", "usina", "equipe", "pessoa", "equipamento", "usina_versao",
                                           "pessoa_versao")}


def _erro(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"[:300]


def _ler_ou(le: "_Leitor", livro, aba, padrao):
    try:
        return le.ler(livro, aba)
    except Exception:       # noqa: BLE001 — leitura de apoio (a qualidade anterior): sem ela, só falta a comparação
        return padrao


def _equipamentos(le: "_Leitor", cad: dict, dados_pcm, iso: str, maquina: str) -> tuple:
    """(tabelas do `nexus_equipamentos` ou None, publicar?, relatório, equip) — `equip` é o que os fatos usam para pôr
    o `equipamento_id` (código -> (ID, por onde)).

    Se uma fonte da dimensão falha (são 8 abas, o `campo_nexus` com ~11 mil linhas), a dimensão não é gravada nesta
    hora e os fatos ligam pelo índice da dimensão GRAVADA: o `fato_fechamento` não perde o `equipamento_id` (nem a
    hora) por causa de uma fonte que só a dimensão lê. Colisão de ID é o caso desenhado à parte: nem dimensão nem
    `equipamento_id` (seria juntar dois equipamentos num ID)."""
    try:
        cod = {fonte: [r.get(col) for r in le.ler(livro, aba)] for fonte, livro, aba, col in equipamento.FONTES_BANCO}
        if dados_pcm is not None:
            cod["pcm"] = programacao.codigos(dados_pcm)
        colunas, colunas_como = _colunas_de_geracao(le, cad["de_para"])
        eqt, rel_eq = equipamento.montar(le.ler(equipamento.LIVRO_FOTO, equipamento.ABA_FOTO), cod, cad["usinas"],
                                         le.ler(*DE_PARA_TRACKERS), le.ler(*GEMEO_ALIAS), colunas, agora=iso,
                                         maquina=maquina)
        mudou = equipamento.mudou(eqt, le.ler(equipamento.LIVRO, "atualizacao"))
    except equipamento.ColisaoDeId as e:
        return None, False, {"erro": f"ColisaoDeId: {e}"[:300], "publicar": False}, None
    except Exception as e:      # noqa: BLE001 — a fonte da dimensão falhou: os fatos seguem
        rel_eq = {"erro": _erro(e), "publicar": False}
        log.warning("carga de dados: dimensão de equipamento falhou, não gravada nesta hora: %s", rel_eq["erro"])
        try:
            ix = equipamento.indice(le.ler(equipamento.LIVRO, "dim_equipamento"))
            rel_eq["indice"] = "dimensão gravada"
        except Exception:   # noqa: BLE001 — sem ela, só o código com usina liga (marcado "fora da dimensão")
            ix, rel_eq["indice"] = {}, "nenhum"
        return None, False, rel_eq, (lambda c: equipamento.ligar(c, ix))
    publicar_eq = mudou and dados_pcm is not None
    rel_eq.update(mudou=mudou, publicar=publicar_eq, colunas_de_geracao=colunas_como,
                  **({} if dados_pcm is not None else {"nao_publica": "PCM não lido nesta carga"}))
    ix = equipamento.indice(eqt["dim_equipamento"][1])
    return eqt, publicar_eq, rel_eq, (lambda c: equipamento.ligar(c, ix))


def _fato_ou_anterior(le: "_Leitor", fato: str, aba: str, cab: list, montar_fato, q_antes: list, iso: str,
                      falhou: dict):
    """((cab, linhas), linha de qualidade) do fato desta hora; se ele falhar, a aba COMO ESTÁ no banco e a linha de
    qualidade anterior com o erro no `extra`. None se falhou e a aba nunca foi gravada (não há o que apagar).

    Se nem a aba anterior se consegue ler, o erro original sobe: aí a carga inteira não grava nesta hora (gravar o
    `nexus_fatos` sem a aba a apagaria)."""
    try:
        linhas, q = montar_fato()
        return (cab, linhas), q
    except Exception as e:      # noqa: BLE001 — isolamento: ver `montar`
        falhou[fato], erro = _erro(e), e
        log.warning("carga de dados: fato %s falhou, a aba fica como está no banco: %s", fato, falhou[fato])
        try:
            if aba not in le.abas(LIVRO_FATOS):
                return None
            linhas_ant = le.ler(LIVRO_FATOS, aba)
        except Exception:       # noqa: BLE001
            raise e from None
    cab_ant = list(linhas_ant[0]) if linhas_ant else list(cab)
    q = next((dict(l) for l in q_antes if str(l.get("fato")) == fato), None) or {"fato": fato, "gerado_em": None}
    q = {c: q.get(c) for c in fatos.CAB_QUALIDADE}
    q["linhas"] = len(linhas_ant)
    try:
        ex = json.loads(q.get("extra") or "{}")
    except (TypeError, ValueError):
        ex = {}
    # a qualidade vai para a API de LEITURA ABERTA (regra 8): a mensagem de uma exceção qualquer pode trazer o valor
    # que a causou (um nome, um texto do App). Lá vai só o tipo; a mensagem do grão quebrado (só chaves sha1) vai
    # inteira, porque é ela que diz o que consertar. A mensagem completa fica no log e no relatório da carga.
    ex.update(falhou_nesta_carga=falhou[fato] if isinstance(erro, fato_ronda.GraoDuplicado) else type(erro).__name__,
              falhou_em=iso)
    q["extra"] = json.dumps(ex, ensure_ascii=False, sort_keys=True)
    return (cab_ant, [[d.get(c) for c in cab_ant] for d in linhas_ant]), q


def montar(config, sessao, agora: datetime | None = None, *, ensaio: bool = False) -> tuple[dict, dict, dict]:
    """(livros a gravar {livro: tabelas}, montados sem gravar {livro: tabelas}, relatório só com contagens). Não grava.

    Os livros a gravar são os de hora em hora; o `nexus_equipamentos` só vem quando mudou e todas as fontes foram
    lidas, e o `nexus_dimensoes` não vem quando o histórico tem de ser segurado. O `nexus_programacao` vem quando o fato
    mesclado mudou (`_programacao`); com `ensaio`, ele vem montado mesmo sem mudar, para medir."""
    agora = agora or _agora()
    base = _base(config)
    iso = agora.isoformat(timespec="seconds")
    maquina = _maquina()
    le = _Leitor(base, sessao)
    cad = {a: le.ler(CADASTRO, a) for a in ("usinas", "equipes", "pessoas", "de_para")}
    m = _mapas(config, sessao)
    lig = ligador(cad, m)
    fech = le.ler(*ORIGEM_FECHAMENTOS)
    dados_pcm, pcm_lido_em = _ler_pcm(config)
    # ISOLAMENTO (revisão de 08/10/2026): até o passo 2-6 a carga lia 5 abas e gravava o fechamento; agora lê ~15 e
    # monta 3 fatos novos, a dimensão de equipamento e o SCD2. Um defeito numa peça nova (o mesmo Início duas vezes no
    # livro de rondas, um 500 no `de_para_trackers`) derrubava a carga inteira e o `fato_fechamento`, que funcionava,
    # parava de andar. Agora cada peça nova que falha fica como estava no banco nesta hora e o resto segue; o erro vai
    # para `rel["falhou"]`, para o log e para o `extra` da qualidade do fato.
    falhou = {}
    rel = {"gerado_em": iso, "maquina": maquina, "falhou": falhou}

    # ── a dimensão de equipamento, antes dos fatos (passo 6a) ──────────────────────────────────────────────────────
    eqt, publicar_eq, rel_eq, equip = _equipamentos(le, cad, dados_pcm, iso, maquina)
    if rel_eq.get("erro"):
        falhou["equipamento"] = rel_eq["erro"]
    rel["equipamento"] = rel_eq

    # ── o histórico (passo 5) ──────────────────────────────────────────────────────────────────────────────────────
    fer = _feriados(config)
    nac, locais = calendario.feriados(fer)
    dias = calendario.dias(nac)
    try:
        abas_dim = le.abas(LIVRO_DIM)
        anteriores = {e: le.ler(LIVRO_DIM, f"{e}_historico") for e in historico.RASTREADOS}
        tab_hist, rel_hist = historico.tabelas({e: cad[e] for e in historico.RASTREADOS}, anteriores, agora.date(),
                                               iso, abas_dim)
        # a qualidade dos fatos mede a junção da época contra o histórico que vai ser gravado (ou o anterior)
        hist_q = {e: (tab_hist[f"{e}_historico"][1] if f"{e}_historico" in tab_hist
                      else historico.migrar(anteriores[e], e)) for e in historico.RASTREADOS}
    except Exception as e:      # noqa: BLE001 — o SCD2 quebrado segura o nexus_dimensoes, não os fatos
        # gravar o livro sem as abas do histórico as apagaria (troca integral): o livro inteiro fica para a hora seguinte
        falhou["historico"] = _erro(e)
        log.warning("carga de dados: histórico falhou, nexus_dimensoes segurado: %s", falhou["historico"])
        tab_hist, rel_hist, hist_q = {}, {"segurar": True}, {}

    # ── os fatos ───────────────────────────────────────────────────────────────────────────────────────────────────
    fato_f, _fech = montar_fechamento(le.ler, lig, equip)
    q_antes = _ler_ou(le, LIVRO_FATOS, "qualidade", [])

    def _ronda():
        linhas, oq, av = montar_ronda(le.ler, lig, m, equip)
        return linhas, fato_ronda.qualidade_ronda(linhas, oq, le.atualizado.get(ORIGEM_RONDAS[0]), iso, avulsas=av,
                                                  hist=hist_q)

    def _pt():
        linhas, pt = montar_pt(le.ler, lig, equip, agora=agora)
        return linhas, fato_pt.qualidade_pt(linhas, pt, le.atualizado.get(ORIGEM_PT[0]), iso, hist=hist_q)

    # GraoDuplicado (ou a fonte fora do ar) num fato novo: a aba dele fica como está no banco nesta hora (gravar o
    # livro sem ela a apagaria, troca integral) e o fechamento anda
    t_ronda = _fato_ou_anterior(le, "ronda", "fato_ronda", fato_ronda.CAB_RONDA, _ronda, q_antes, iso, falhou)
    t_pt = _fato_ou_anterior(le, "pt", "fato_pt", fato_pt.CAB_PT, _pt, q_antes, iso, falhou)

    # ── a qualidade (uma linha por fato) ──────────────────────────────────────────────────────────────────────────
    antes = {str(l.get("fato")): l.get("linhas") for l in q_antes}
    i_eq = fatos.CAB_FECHAMENTO.index("equipamento_ligado_por")
    orfaos = sum(1 for l in fato_f if l[i_eq] == equipamento.FORA_DA_DIMENSAO)
    q_f = dict(zip(fatos.CAB_QUALIDADE, fatos.qualidade(
        "fechamento", ORIGEM_FECHAMENTOS[0], fato_f, fatos.CAB_FECHAMENTO, fech,
        le.atualizado.get(ORIGEM_FECHAMENTOS[0]), iso, hist=hist_q, extra={"equipamento_fora_da_dimensao": orfaos})))
    fat = {"fato_fechamento": (fatos.CAB_FECHAMENTO, fato_f)}
    qs = [q_f]
    for aba, t in (("fato_ronda", t_ronda), ("fato_pt", t_pt)):
        if t is not None:                   # None = falhou e nunca foi gravado: a aba não existe, nada a apagar
            fat[aba], q = t
            qs.append(q)
    encolheram = {}
    for q in qs:
        if q["fato"] in falhou:
            continue                        # a aba anterior, intocada: a conta de encolher não se aplica
        try:
            ant = int(float(antes.get(q["fato"])))
        except (TypeError, ValueError):
            ant = None
        _extra(q, linhas_na_carga_anterior=ant)
        if ant is not None and q["linhas"] < ant:
            encolheram[q["fato"]] = [ant, q["linhas"]]

    dim = {"dim_data": (calendario.CAB_DIA, dias), "feriados_locais": (calendario.CAB_FERIADO, locais), **tab_hist,
           "atualizacao": (CAB_ATUALIZACAO, [[iso, maquina, None, len(dias),
                                              "data_id = AAAAMMDD; histórico: a versão da época é a linha com "
                                              "valido_de_id <= data_id < valido_ate_id (vigente: 99991231)"]])}
    fat["qualidade"] = (fatos.CAB_QUALIDADE, [[q.get(c) for c in fatos.CAB_QUALIDADE] for q in qs])
    fat["atualizacao"] = (CAB_ATUALIZACAO, [[iso, maquina, None, sum(len(fat[a][1]) for a in fat if a.startswith(
        "fato_")), "IDs do cadastro_nexus; vazio = não ligou (ver qualidade)"]])
    gravar = {LIVRO_FATOS: fat}
    if not rel_hist["segurar"]:
        gravar[LIVRO_DIM] = dim
    if publicar_eq:
        gravar[equipamento.LIVRO] = eqt
    rel.update({
        "fato_fechamento": len(fato_f), "pct_usina": q_f["pct_usina"], "pct_equipe": q_f["pct_equipe"],
        "pct_pessoa": q_f["pct_pessoa"],
        "fato_ronda": None if "ronda" in falhou else len(fat["fato_ronda"][1]),
        "fato_pt": None if "pt" in falhou else len(fat["fato_pt"][1]),
        "pct": {q["fato"]: _resumo_q(q) for q in qs if q["fato"] not in falhou}, "encolheram": encolheram,
        "feriados_nacionais": len(nac), "feriados_locais": len(locais),
        **{f"{e}_historico": len(tab_hist.get(f"{e}_historico", (None, []))[1]) for e in historico.RASTREADOS},
        "historico_pulou": {e: rel_hist[e]["pulou_motivo"] for e in historico.RASTREADOS
                            if (rel_hist.get(e) or {}).get("pulou_motivo")},
        "segurar_dimensoes": rel_hist["segurar"], "pcm": "lido" if dados_pcm is not None else "não lido",
        "grava": sorted(gravar)})

    nao_grava = {}
    # ── a programação do PCM (passo 6b; decisão 7, 08/10/2026: mescla por semana) ─────────────────────────────────
    # livro próprio e isolado (regra 13): o que falha aqui só deixa de gravar a programação nesta hora
    try:
        tab_p, grava_p, rel["programacao"] = _programacao(le, dados_pcm, pcm_lido_em, lig, m, equip, hist_q, iso,
                                                          maquina, medir=ensaio)
    except Exception as e:      # noqa: BLE001
        falhou["programacao"] = _erro(e)
        log.warning("carga de dados: programação falhou, não gravada nesta hora: %s", falhou["programacao"])
        tab_p, grava_p, rel["programacao"] = None, False, {"erro": falhou["programacao"]}
    if grava_p:
        gravar[programacao.LIVRO] = tab_p
        rel["grava"] = sorted(gravar)
    elif ensaio and tab_p:
        nao_grava[programacao.LIVRO] = tab_p
    if ensaio:
        if eqt is not None and not publicar_eq:
            nao_grava[equipamento.LIVRO] = eqt          # para medir o tamanho; gravar, só quando mudar
    return gravar, nao_grava, rel


def tabelas_programacao(linhas: list, rel_fonte: dict, hist_q: dict, iso: str, maquina: str,
                        sha_fonte: str | None) -> tuple[dict, dict, dict]:
    """(as três abas do `nexus_programacao`, o resumo das linhas, a linha de qualidade) para o fato MESCLADO (as semanas
    do banco + as do arquivo). Uma conta só, para a carga de hora em hora e para a carga única do histórico
    (`ferramentas/carregar_programacao_historica.py`). A `atualizacao` leva o sha das linhas (sem o `lido_em`: o
    `geradoEm` do PCM muda a cada ~30 min sem nada mudar) e o sha das linhas do arquivo (`sha_fonte`), para a carga não
    reler o fato do banco quando o arquivo não mudou."""
    cab = programacao.CAB_PROGRAMACAO
    rm = programacao.resumo_das_linhas(linhas, rel_fonte)
    q = dict(zip(fatos.CAB_QUALIDADE, programacao.linha_qualidade(rm, fatos.CAB_QUALIDADE, None, iso)))
    q["pct_usina_versao"] = fatos.pct_versao(linhas, cab, "usina_id", "data_id_programada", hist_q.get("usinas"))
    q["pct_pessoa_versao"] = fatos.pct_versao(linhas, cab, "pessoa_id_tecnico", "data_id_programada",
                                              hist_q.get("pessoas"))
    i = cab.index("equipamento_ligado_por")
    _extra(q, equipamento_fora_da_dimensao=sum(1 for l in linhas if l[i] == equipamento.FORA_DA_DIMENSAO))
    tab = {programacao.ABA: (cab, linhas),
           "qualidade": (fatos.CAB_QUALIDADE, [[q.get(c) for c in fatos.CAB_QUALIDADE]]),
           "atualizacao": (programacao.CAB_ATUALIZACAO,
                           [[iso, maquina, None, len(linhas), programacao.sha_linhas(linhas), sha_fonte,
                             len(rm["semanas"]), "1 linha = 1 bloco de agenda; foraDoPlano fora (outro grão); "
                                                 "data_id_semana = a segunda-feira da semana ISO"]])}
    return tab, rm, q


def _programacao(le: "_Leitor", dados, lido_em, lig, m, equip, hist_q, iso, maquina, *,
                 medir: bool = False) -> tuple[dict | None, bool, dict]:
    """(tabelas do `nexus_programacao` ou None, gravar nesta hora?, resumo só com contagens).

    Decisão 7 (Levi, 08/10/2026: "Tem que ter as semanas antigas mesmo, precisamos desses dados pois em menos de duas
    semanas será full Nexus"): o `banco_dados.json` guarda só 4 semanas, então a carga lê o fato que está no banco,
    troca só as semanas que o arquivo traz e mantém as outras (`programacao.mesclar_semanas`). NÃO grava nesta hora:
    - sem o arquivo do PCM;
    - com o livro existente, se a leitura do fato falhou ou veio vazia: gravar trocaria o histórico pelas 4 semanas do
      arquivo, e a API não devolve o que se apagou (o fato não encolhe);
    - com `programacao_id` repetido no fato mesclado (grão quebrado);
    - sem mudança: o sha das linhas do arquivo é o da última gravação (nem relê o fato) ou o do fato mesclado é.
    `medir` (o `--ensaio`) monta o fato mesclado mesmo sem mudança, para medir."""
    if dados is None:
        return None, False, {"pulou": "sem a fonte do PCM (banco_dados.json) nesta máquina ou nesta hora"}
    fonte, rp = programacao.fato_programacao(dados, lig, m.get("pessoa") or {}, equip, lido_em)
    sha_fonte = programacao.sha_linhas(fonte)
    rel = {"semanas_do_arquivo": rp.get("semanas"), "linhas_do_arquivo": len(fonte),
           "fora_do_plano": rp.get("fora_do_plano"), "blocos_repetidos": rp.get("blocos_repetidos")}
    # o arquivo degradado do PCM (26/10/2026: o Fracttal devolveu 0 registros e as 4 semanas saíram sem status): a
    # semana sem status não troca a do banco (`mesclar_semanas`), e o arquivo todo degradado não grava nada
    ruins = programacao.semanas_degradadas(fonte)
    if ruins:
        rel["semanas_degradadas"] = sorted(ruins)
        log.warning("programação: o arquivo do PCM chegou sem o status das tarefas nas semanas %s", sorted(ruins))
        if len(ruins) == len({l[programacao.CAB_PROGRAMACAO.index("data_id_semana")] for l in fonte}):
            return None, False, dict(rel, nao_grava="o arquivo do PCM chegou degradado (nenhuma tarefa com status) "
                                                    "em todas as semanas: o fato do banco fica como está")
    existe = bool(le.abas(programacao.LIVRO))
    ant = _ler_ou(le, programacao.LIVRO, "atualizacao", []) if existe else []
    ant = dict(ant[0]) if ant else {}
    if existe and not medir and ant and str(ant.get("sha_fonte") or "") == sha_fonte:
        return None, False, dict(rel, mudou=False, motivo="o arquivo do PCM não mudou desde a última gravação")
    no_banco = []
    if existe:
        try:
            no_banco = le.ler(programacao.LIVRO, programacao.ABA)
        except Exception as e:      # noqa: BLE001 — sem o fato do banco, gravar apagaria o histórico
            return None, False, dict(rel, nao_grava=f"leitura do fato no banco falhou ({type(e).__name__}): "
                                                    "o fato não encolhe")
        if not no_banco:
            return None, False, dict(rel, nao_grava="o livro existe e o fato veio vazio: o fato não encolhe")
    # a linha que não mudou guarda o lido_em que já está no banco: a API guarda o histórico de cada linha que muda; as
    # semanas antigas ganham o equipamento que entrou na dimensão depois delas (só melhora, `religar_equipamento`)
    linhas = programacao.manter_lido_em(
        programacao.religar_equipamento(programacao.mesclar_semanas(no_banco, fonte), equip), no_banco)
    tab, rm, q = tabelas_programacao(linhas, rp, hist_q, iso, maquina, sha_fonte)
    mudou = str(ant.get("sha_linhas") or "") != tab["atualizacao"][1][0][programacao.CAB_ATUALIZACAO.index(
        "sha_linhas")]
    rel.update(linhas=len(linhas), linhas_no_banco=len(no_banco), semanas=len(rm["semanas"]),
               tarefas=rm["tarefas"], ids_repetidos=rm["ids_repetidos"], mudou=mudou, pct=_resumo_q(q))
    if rm["ids_repetidos"]:
        return tab, False, dict(rel, nao_grava=f"{rm['ids_repetidos']} programacao_id repetidos no fato mesclado")
    return tab, mudou, rel


def montar_geracao(config, sessao, agora: datetime | None = None, *, apelidos=None, de_para=None) -> tuple:
    """(tabelas do `nexus_geracao`, linhas do inversor × dia, relatório). Quem grava é o `gerar_geracao` (depois de cada
    subida do `bd_thopen` ou do `bd_performance`); o `--ensaio` das ferramentas só mede. Lê as 171 abas inteiras
    (43–65 s em 08/10). `apelidos`: os do `nexus_equipamentos` (sem eles, lê os publicados); `de_para`: um de-para
    calculado (sem ele, o publicado)."""
    agora = agora or _agora()
    base = _base(config)
    t0 = time.time()
    le = _Leitor(base, sessao)
    usinas = le.ler(CADASTRO, "usinas")
    cad_de_para = le.ler(CADASTRO, "de_para") if de_para is None else de_para
    fontes = {f: {aba: le.ler(f, aba) for aba in le.abas(f)} for f in geracao.FONTES}
    anterior = le.ler(geracao.LIVRO, geracao.ABA_USINA)
    if apelidos is None:
        apelidos = le.ler(equipamento.LIVRO, "equipamento_apelido")
    origem_em = "; ".join(f"{f}: {le.atualizado.get(f)}" for f in geracao.FONTES)
    t_ler = round(time.time() - t0, 1)
    t1 = time.time()
    tab, inversor, rel = geracao.montar(fontes, cad_de_para, usinas, agora.date(), agora.isoformat(timespec="seconds"),
                                        apelidos=apelidos, anterior=anterior, maquina=_maquina(), origem_em=origem_em)
    rel["tempo_s"] = {"ler": t_ler, "montar": round(time.time() - t1, 1)}
    return tab, inversor, rel


def origem_da_geracao(config, sessao) -> str:
    """A hora da última subida do `bd_thopen` e do `bd_performance` (o `updated_at` dos livros), no texto que a montagem
    grava em `qualidade.origem_atualizada_em`: igual = nada subiu desde a última montagem."""
    le = _Leitor(_base(config), sessao)
    return "; ".join(f"{f}: {le.atualizado.get(f)}" for f in geracao.FONTES)


def gerar_geracao(config, sessao=None, *, gravar=True, forcar=False, agora=None) -> dict:
    """A geração em linhas, DEPOIS DE CADA SUBIDA dos BDs (Levi, 11/10/2026: "BD_Performance e BD_Thopen são preenchidos
    diariamente parte por API e parte manual; logo depois de serem preenchidos eu subo para o PG. Se você quiser fazer o
    nexus_geração um produto do BD_Performance e BD_Thopen e usar apenas ele como referência eu apoio"). Os BDs seguem a
    FONTE: aqui só se lê deles. Monta só quando o `updated_at` de um dos dois mudou desde a última montagem (a correção
    manual de um dia passado entra na seguinte); aba que perdeu dias (leitura vazia ou menor que a anterior) recusa a
    gravação inteira e diz qual foi; o inversor × dia vai em um livro por mês e só o mês que mudou é regravado. Relatório
    só com contagens."""
    import requests
    s = sessao or requests.Session()
    base = _base(config)
    origem = origem_da_geracao(config, s)
    if not forcar:
        q = (livros.ler(base, s, geracao.LIVRO, "qualidade") or [{}])[0]
        if q.get("origem_atualizada_em") == origem:
            return {"pulou": "nenhuma subida nova do BD_Thopen nem do BD_Performance desde a última montagem",
                    "origem": origem}
    t0 = time.time()
    tab, inversor, rel = montar_geracao(config, s, agora)
    if rel.get("encolhidas") and not forcar:
        return dict(rel, recusou="aba com menos dias que a gravada (leitura vazia ou encolhida): nada gravado; veja "
                                 "'encolhidas' e grave com forcar depois de conferir")
    por_mes = geracao.inversor_por_mes(inversor)
    gravados = livros.ler(base, s, geracao.LIVRO, geracao.ABA_MESES)
    mudaram = geracao.meses_que_mudaram(por_mes, gravados)
    agora_txt = (agora or _agora()).isoformat(timespec="seconds")
    tab[geracao.ABA_MESES] = (list(geracao.CAB_MESES), geracao.linhas_meses(por_mes, gravados, mudaram, agora_txt))
    rel["meses"] = {"total": len(por_mes), "a_gravar": mudaram}
    if not gravar:
        return dict(rel, ensaio="montado com o dado real; nada gravado")
    if not config.get("GRIDCO_SQL_TOKEN"):
        return dict(rel, erro="sem GRIDCO_SQL_TOKEN: montado e não gravado")
    gravado = {}
    # os meses do inversor primeiro: o `nexus_geracao` (com a origem na qualidade) é a marca de montagem completa; se um
    # mês falhar, a próxima volta monta de novo
    for m in mudaram:
        gravado[m] = livros.publicar(m, f"Nexus · geração por inversor e dia ({m[-7:-3]}-{m[-2:]})",
                                     {geracao.ABA_INVERSOR: (list(geracao.CAB_INVERSOR_DIA), por_mes[m])}, base=base,
                                     token=config["GRIDCO_SQL_TOKEN"], sessao=s)
    gravado[geracao.LIVRO] = livros.publicar(geracao.LIVRO, geracao.NOME_LIVRO, tab, base=base,
                                             token=config["GRIDCO_SQL_TOKEN"], sessao=s)
    rel["gravado"], rel["duracao_s"] = gravado, round(time.time() - t0, 1)
    return rel


def _sha_pecas(pecas: list[dict]) -> str:
    import hashlib
    linhas = sorted(json.dumps(sorted((k, "" if v is None else str(v)) for k, v in p.items()), ensure_ascii=False)
                    for p in pecas)
    return hashlib.sha1("\n".join(linhas).encode("utf-8")).hexdigest()[:16]


def _linhas_cab(linhas: list[dict], cab: list) -> list[list]:
    return [[d.get(c) for c in cab] for d in linhas]


def gerar_almoxarifado(config, sessao=None, *, gravar=True, forcar=False, agora=None, medir=False) -> dict:
    """O histórico do almoxarifado (25/10/2026): o livro do App guarda só o último ciclo da varredura, e aqui o Nexus
    acrescenta, a cada ciclo novo e completo, a foto do saldo (no livro do mês) e a linha do ciclo, e as peças lançadas
    pelo App (`fato_almoxarifado.py`). Roda no laço de hora em hora com PORTÃO PRÓPRIO, como a `gerar_geracao`: a carga
    dos fatos só grava os 4 livros dela, e o portão dela é o horário do `nexus_fatos` (se o PC ganhar a hora, o servidor
    pula, e o ciclo do dia se perderia). O portão daqui: um ciclo novo (pelo início) ou peças novas (o sha).

    Não grava (o relatório diz por quê, só contagens): sem os livros do App; com o livro do Nexus existente e a leitura
    dele vazia (o histórico não encolhe; a trava `so_cresce` do `livros.publicar` confere de novo); sem a
    NEXUS_ALMOX_GRAVAR=1 (Levi, 25/10/2026: o Nexus sobe antes do App, em ensaio, e a gravação liga depois do ensaio
    com o 1º ciclo real). Ciclo incompleto (menos de 90% dos itens lidos) ou com chave repetida no saldo entra só
    como recusado; livros do App de ciclos diferentes ou que chegaram pela metade (`conferir_ciclo`) não aplicam NESTA
    hora e não ficam vistos (a hora seguinte aplica). `medir` (o `--ensaio`): mede o ciclo do App mesmo já visto."""
    import requests
    s = sessao or requests.Session()
    base = _base(config)
    agora = agora or _agora()
    iso, t0 = agora.isoformat(timespec="seconds"), time.time()
    F = fato_almoxarifado
    le = _Leitor(base, s)
    if not all(le.abas(l) for l in (almox.LIVRO_CICLO, almox.LIVRO_ITENS, almox.LIVRO_SALDO)):
        return {"pulou": "o App ainda não publica o almoxarifado"}
    ciclo, itens = le.ler(almox.LIVRO_CICLO, almox.ABA_CICLO), le.ler(almox.LIVRO_ITENS, almox.ABA_ITENS)
    saldo = le.ler(almox.LIVRO_SALDO, almox.ABA_SALDO)
    pecas_app = le.ler(almox.LIVRO_PECAS, almox.ABA_PECAS) if le.abas(almox.LIVRO_PECAS) else []
    inicio, sha = almox.ciclo_comum(ciclo, itens, saldo), _sha_pecas(pecas_app)
    abas = (F.ABA_CICLO, F.ABA_PECA, F.ABA_DIM_ITEM, F.ABA_DIM_ALMOX, "qualidade", "atualizacao")
    banco = {a: [] for a in abas}
    if le.abas(F.LIVRO):
        try:
            banco = {a: le.ler(F.LIVRO, a) for a in abas}
        except Exception as e:      # noqa: BLE001 — sem o histórico lido, gravar o apagaria
            return {"nao_grava": f"a leitura do {F.LIVRO} falhou ({type(e).__name__}): o histórico não encolhe"}
        if not banco[F.ABA_CICLO] and not banco[F.ABA_PECA]:
            return {"nao_grava": f"o {F.LIVRO} existe e veio vazio: o histórico não encolhe"}
    vistos = {str(c.get("ciclo_inicio") or "") for c in banco[F.ABA_CICLO]}
    ant = dict(banco["atualizacao"][0]) if banco["atualizacao"] else {}
    novo = bool(inicio) and (inicio not in vistos or medir)
    rel = {"ciclo": inicio, "ciclo_novo": novo, "incoerente": inicio is None, "pecas_app": len(pecas_app)}
    if not forcar and not medir and not novo and str(ant.get("sha_pecas") or "") == sha:
        return dict(rel, pulou="nenhum ciclo novo do App nem peça nova desde a última gravação")
    falta = almox.conferir_ciclo(ciclo, itens, saldo) if novo else ""
    if falta:
        novo = False                       # passageiro: não aplica nem marca visto; a hora seguinte tenta de novo
        rel["nao_aplica"] = falta
    cad = {a: le.ler(CADASTRO, a) for a in ("usinas", "de_para", "equipes")}
    if not cad["de_para"]:
        # a revisão de 25/10/2026: com o de-para lido vazio, a foto do dia ficaria sem usina para sempre
        return dict(rel, nao_grava="o de-para do cadastro veio vazio: a usina não liga nesta hora")
    lig = ligador(cad, {"hmac": _pessoas_por_codigo(config, s)})
    linhas_ciclo = _linhas_cab(banco[F.ABA_CICLO], F.CAB_CICLO)
    extra = {}
    dim_item, dim_almox = _linhas_cab(banco[F.ABA_DIM_ITEM], F.CAB_DIM_ITEM), _linhas_cab(banco[F.ABA_DIM_ALMOX],
                                                                                        F.CAB_DIM_ALMOX)
    q_ant = {str(q.get("fato") or ""): [q.get(c) for c in fatos.CAB_QUALIDADE] for q in banco["qualidade"]}
    q_saldo, mes, linhas_mes, aplicado = q_ant.get("saldo_almox"), None, None, str(ant.get("ciclo_inicio") or "")
    if novo:
        c0 = ciclo[0]
        conta = f"{_int_ou_none(c0.get('Itens lidos'))} de {_int_ou_none(c0.get('Itens na lista do Fracttal'))} itens lidos"
        nao_lidos = sum(1 for i in itens if str(i.get("Lido") or "").strip().lower() != "sim")
        bons = [c for c in banco[F.ABA_CICLO] if str(c.get("situacao") or "") == "aplicado"
                and str(c.get("anulado") or "0").split(".")[0] != "1"]
        antes = _int_ou_none(max(bons, key=lambda c: str(c.get("ciclo_inicio") or "")).get("itens_lista_qtd")) if bons else None
        agora_n = _int_ou_none(c0.get("Itens na lista do Fracttal"))
        extra = {"nao_lidos": nao_lidos}
        if antes and agora_n is not None and agora_n < almox.COMPLETUDE_MIN * antes:
            # só aviso: o PCM pode ter limpado o catálogo (a completude é a do próprio ciclo)
            extra["queda_itens"] = rel["queda_itens"] = {"antes": antes, "agora": agora_n}
        # o almoxarifado de teste (NEXUS_ALMOX_TESTE_IDS) não entra no histórico, que só cresce; o filtro vem DEPOIS do
        # `conferir_ciclo` acima, que conta as linhas do livro inteiro (o ciclo conta as do teste)
        saldo_real = almox.sem_almoxarifado_de_teste(saldo, config)
        foto = F.saldo_do_ciclo(saldo_real, lig)
        ids = [l[0] for l in foto]
        rel.update(saldo_linhas=len(foto), saldo_repetidos=len(ids) - len(set(ids)), nao_lidos=nao_lidos)
        uid = [l[F.CAB_SALDO.index("usina_id")] for l in foto]
        rel["pct_usina"] = round(100.0 * sum(1 for u in uid if u) / len(uid), 1) if uid else 0.0
        if rel["saldo_repetidos"]:
            linhas_ciclo.append(F.linha_ciclo(c0, "recusado", f"chave repetida no saldo ({rel['saldo_repetidos']})", iso,
                                              nao_lidos))
            rel["recusado"] = f"chave repetida no saldo ({rel['saldo_repetidos']})"
        elif almox.completo(c0):
            mes = F.livro_do_mes(foto[0][F.CAB_SALDO.index("data_id")]) if foto else None
            no_mes = []
            if mes and le.abas(mes):
                try:
                    no_mes = le.ler(mes, F.ABA_SALDO)
                except Exception as e:      # noqa: BLE001
                    return dict(rel, nao_grava=f"a leitura do {mes} falhou ({type(e).__name__}): a foto não encolhe")
                if not no_mes:
                    return dict(rel, nao_grava=f"o {mes} existe e veio vazio: a foto não encolhe")
            # a foto deste ciclo que já estiver no mês (o mês gravou e a marca falhou na hora anterior) é trocada, não
            # repetida
            i = F.CAB_SALDO.index("ciclo_inicio")
            linhas_ciclo.append(F.linha_ciclo(c0, "aplicado", conta, iso, nao_lidos))
            dim_item = F.mesclar_dim(banco[F.ABA_DIM_ITEM], F.dim_itens(itens), "id_item", F.CAB_DIM_ITEM)
            novas_almox = F.dim_almoxarifados(saldo_real, lig)
            dim_almox = F.religar_almox(F.mesclar_dim(banco[F.ABA_DIM_ALMOX], novas_almox, "id_almoxarifado",
                                                      F.CAB_DIM_ALMOX), lig)
            # o mês corrente religado pela dimensão de agora (o almoxarifado ligado depois ganha a usina nas fotos dele)
            linhas_mes = F.religar_saldo([l for l in _linhas_cab(no_mes, F.CAB_SALDO) if str(l[i] or "") != inicio]
                                         + foto, dim_almox)
            sem_usina = [a[2] or a[1] for a in novas_almox if not a[3]]
            q_saldo = F.linha_qualidade("saldo_almox", foto, F.CAB_SALDO, inicio, iso, sem_usina=sem_usina)
            aplicado = inicio
            rel.update(almoxarifados=len(novas_almox), sem_usina=len(sem_usina), mes=mes)
        else:
            linhas_ciclo.append(F.linha_ciclo(c0, "recusado", f"{conta} (menos de 90%)", iso, nao_lidos))
            rel["recusado"] = conta
    usina_do_almox = {str(a[0]): (_int_ou_none(a[3]), a[4]) for a in dim_almox}
    pecas = F.mesclar_pecas(banco[F.ABA_PECA], pecas_app, lig, usina_do_almox)
    if not linhas_ciclo and not pecas:
        # a revisão de 25/10/2026: sem ciclo e sem peça não há o que guardar; gravar criaria um livro vazio, e a trava
        # do "livro existe e veio vazio" pararia o histórico para sempre
        return dict(rel, pulou="nada a guardar: nenhum ciclo aplicável e nenhuma peça lançada")
    q = [F.linha_qualidade("ciclo_varredura", linhas_ciclo, F.CAB_CICLO, inicio or "", iso,
                           extra=extra if novo else None),
         F.linha_qualidade("peca_lancada", pecas, F.CAB_PECA, inicio or "", iso)]
    q.insert(0, q_saldo or F.linha_qualidade("saldo_almox", [], F.CAB_SALDO, "", iso))
    como_ler = ("o saldo de um dia: o último ciclo aplicado (situacao = aplicado, anulado = 0) que começou nele, no "
                "livro do mês (fato_saldo_almox, pelo ciclo_inicio)")
    tab = {F.ABA_CICLO: (F.CAB_CICLO, linhas_ciclo), F.ABA_PECA: (F.CAB_PECA, pecas),
           F.ABA_DIM_ITEM: (F.CAB_DIM_ITEM, dim_item), F.ABA_DIM_ALMOX: (F.CAB_DIM_ALMOX, dim_almox),
           "qualidade": (list(fatos.CAB_QUALIDADE), q),
           "atualizacao": (F.CAB_ATUALIZACAO, [[iso, _maquina(), round(time.time() - t0, 1),
                                                len(linhas_ciclo) + len(pecas), como_ler, aplicado, sha]])}
    rel.update(ciclos=len(linhas_ciclo), pecas=len(pecas))
    if not gravar or str(config.get("NEXUS_ALMOX_GRAVAR") or "").strip() != "1":
        return dict(rel, ensaio="montado com o dado real; nada gravado (a gravação liga com NEXUS_ALMOX_GRAVAR=1)")
    if not config.get("GRIDCO_SQL_TOKEN"):
        return dict(rel, erro="sem GRIDCO_SQL_TOKEN: montado e não gravado")
    gravado, tok = {}, config["GRIDCO_SQL_TOKEN"]
    # o livro do mês primeiro: o nexus_almoxarifado (com o ciclo aplicado) é a marca; se o mês falhar, a próxima hora
    # vê o ciclo como novo e tenta de novo
    if linhas_mes is not None:
        gravado[mes] = livros.publicar(mes, f"Nexus · saldo do almoxarifado por ciclo ({mes[-7:-3]}-{mes[-2:]})",
                                       {F.ABA_SALDO: (F.CAB_SALDO, linhas_mes)}, base=base, token=tok, sessao=s)
    gravado[F.LIVRO] = livros.publicar(F.LIVRO, F.NOME_LIVRO, tab, base=base, token=tok, sessao=s)
    return dict(rel, gravado=gravado, duracao_s=round(time.time() - t0, 1))


def _int_ou_none(v):
    n = almox.numero(v)
    return int(n) if n is not None else None


def anular_ciclo_almox(config, inicio: str, sessao=None, *, gravar=False) -> dict:
    """Marca um ciclo aplicado errado como anulado (`ferramentas/anular_ciclo_almox.py`). Não apaga linha nenhuma: o
    livro só cresce; as contas ignoram o ciclo anulado e a foto dele fica no livro do mês."""
    import requests
    s = sessao or requests.Session()
    base, F = _base(config), fato_almoxarifado
    le = _Leitor(base, s)
    cabs = {F.ABA_CICLO: F.CAB_CICLO, F.ABA_PECA: F.CAB_PECA, F.ABA_DIM_ITEM: F.CAB_DIM_ITEM,
            F.ABA_DIM_ALMOX: F.CAB_DIM_ALMOX, "qualidade": list(fatos.CAB_QUALIDADE),
            "atualizacao": F.CAB_ATUALIZACAO}
    linhas = {a: le.ler(F.LIVRO, a) for a in cabs}
    alvo = [c for c in linhas[F.ABA_CICLO] if str(c.get("ciclo_inicio") or "") == inicio]
    if not alvo:
        return {"nao_achou": inicio}
    for c in alvo:
        c["anulado"] = 1
    if not gravar:
        return {"anulado": inicio, "ensaio": "nada gravado"}
    tab = {a: (cab, _linhas_cab(linhas[a], cab)) for a, cab in cabs.items()}
    return {"anulado": inicio, "gravado": livros.publicar(F.LIVRO, F.NOME_LIVRO, tab, base=base,
                                                          token=config["GRIDCO_SQL_TOKEN"], sessao=s)}


def rodar(config, sessao=None, *, gravar=True, forcar=False, agora=None) -> dict:
    """Uma carga. Devolve o relatório (só contagens). Com `gravar`, grava e confere os livros de `montar`, nesta
    ordem: a dimensão de equipamento (quando mudou), as dimensões (salvo se seguradas) e os fatos. Cada livro é
    independente: o que falha não segura os outros, e o erro sobe depois de tentar todos."""
    import requests
    s = sessao or requests.Session()
    base = _base(config)
    t0 = time.time()
    if gravar and not forcar:
        u = ultima(base, s)
        if u and (agora or _agora()) - u < timedelta(minutes=INTERVALO_MIN):
            return {"pulou": f"a última carga é de {u.isoformat(timespec='minutes')} (outra máquina ou a mesma)"}
    a_gravar, _montados, rel = montar(config, s, agora)
    if gravar:
        if not config.get("GRIDCO_SQL_TOKEN"):
            return dict(rel, erro="sem GRIDCO_SQL_TOKEN: montado e não gravado")
        dur = round(time.time() - t0, 1)
        for t in a_gravar.values():
            t["atualizacao"][1][0][2] = dur
        nomes = {equipamento.LIVRO: equipamento.NOME, LIVRO_DIM: NOME_DIM, LIVRO_FATOS: NOME_FATOS,
                 programacao.LIVRO: programacao.NOME_LIVRO}
        # só estes quatro livros são desta carga (a programação desde 08/10/2026, decisão 7: mescla por semana); outro
        # aqui (a geração) é erro de programação, nunca uma gravação calada: espera a decisão 8 do Levi
        fora = set(a_gravar) - set(nomes)
        if fora:
            raise ValueError(f"livro que esta carga não grava: {sorted(fora)}")
        rel["gravado"], erros = {}, {}
        for livro in nomes:                 # a dimensão de equipamento antes dos fatos que levam o ID dela
            if livro not in a_gravar:
                continue
            # cada livro é uma gravação independente (isolamento, revisão de 08/10): o `nexus_equipamentos`, novo e
            # o maior dos três, que falha na gravação ou na conferência não pode segurar o `nexus_fatos` daquela hora.
            # O erro não fica calado: sobe no fim, depois de tentar os outros (regra 9, "diferença é erro")
            try:
                rel["gravado"][livro] = livros.publicar(livro, nomes[livro], a_gravar[livro], base=base,
                                                        token=config["GRIDCO_SQL_TOKEN"], sessao=s)
            except Exception as e:      # noqa: BLE001
                erros[livro] = e
                rel.setdefault("erro_gravacao", {})[livro] = _erro(e)
                log.error("carga de dados: gravação de %s falhou: %s", livro, _erro(e))
        if erros:
            raise next(iter(erros.values()))
    rel["duracao_s"] = round(time.time() - t0, 1)
    return rel


def _espera_s(agora=None) -> float:
    agora = agora or _agora()
    alvo = agora.replace(minute=MINUTO_DA_HORA, second=0, microsecond=0)
    if alvo <= agora:
        alvo += timedelta(hours=1)
    return (alvo - agora).total_seconds()


def ligar(app):
    """O laço de hora em hora. Quem chama é o `nexus.dados.instalar` (app.py e servir.py), nunca o create_app."""
    if _LACO["thread"] is not None:
        return

    def laco():
        while not _LACO["parar"].wait(_espera_s()):
            with app.app_context():
                try:
                    _LACO["ultimo"] = rodar(app.config)
                    log.info("carga de dados: %s", _LACO["ultimo"])
                except Exception as e:      # noqa: BLE001 — o laço não morre por uma carga
                    _LACO["ultimo"] = {"erro": f"{type(e).__name__}: {e}"[:300]}
                    log.exception("carga de dados")
                # a geração é à parte: só monta quando um dos BDs subiu, e a falha dela não segura a carga da hora
                try:
                    _LACO["geracao"] = gerar_geracao(app.config)
                    log.info("geração: %s", {k: v for k, v in _LACO["geracao"].items()
                                             if k in ("pulou", "recusou", "gravado", "erro", "meses", "duracao_s")})
                except Exception as e:      # noqa: BLE001
                    _LACO["geracao"] = {"erro": f"{type(e).__name__}: {e}"[:300]}
                    log.exception("geração")
                # o almoxarifado também (25/10/2026): portão próprio (ciclo novo do App ou peça nova) e a falha dele
                # não segura nada
                try:
                    _LACO["almoxarifado"] = gerar_almoxarifado(app.config)
                    # as contagens também (a revisão de 25/10/2026: o ensaio tem de medir antes de ligar a gravação)
                    log.info("almoxarifado: %s", {k: v for k, v in _LACO["almoxarifado"].items()
                                                  if k in ("pulou", "ensaio", "nao_grava", "nao_aplica", "gravado",
                                                           "erro", "recusado", "incoerente", "ciclo", "saldo_linhas",
                                                           "saldo_repetidos", "almoxarifados", "sem_usina",
                                                           "pct_usina", "nao_lidos", "queda_itens", "pecas")})
                except Exception as e:      # noqa: BLE001
                    _LACO["almoxarifado"] = {"erro": f"{type(e).__name__}: {e}"[:300]}
                    log.exception("almoxarifado")

    _LACO["thread"] = threading.Thread(target=laco, name="nexus-carga-dados", daemon=True)
    _LACO["thread"].start()
