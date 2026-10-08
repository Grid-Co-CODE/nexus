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

from . import calendario, equipamento, fato_pt, fato_ronda, fatos, geracao, historico, livros, programacao

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
    # a linha que não mudou guarda o lido_em que já está no banco: a API guarda o histórico de cada linha que muda
    linhas = programacao.manter_lido_em(programacao.mesclar_semanas(no_banco, fonte), no_banco)
    tab, rm, q = tabelas_programacao(linhas, rp, hist_q, iso, maquina, sha_fonte)
    mudou = str(ant.get("sha_linhas") or "") != tab["atualizacao"][1][0][programacao.CAB_ATUALIZACAO.index(
        "sha_linhas")]
    rel.update(linhas=len(linhas), linhas_no_banco=len(no_banco), semanas=len(rm["semanas"]),
               tarefas=rm["tarefas"], ids_repetidos=rm["ids_repetidos"], mudou=mudou, pct=_resumo_q(q))
    if rm["ids_repetidos"]:
        return tab, False, dict(rel, nao_grava=f"{rm['ids_repetidos']} programacao_id repetidos no fato mesclado")
    return tab, mudou, rel


def montar_geracao(config, sessao, agora: datetime | None = None, *, apelidos=None, de_para=None) -> tuple:
    """(tabelas do `nexus_geracao`, linhas do inversor × dia, relatório). A cadência é DIÁRIA (depois da coleta noturna
    que grava o `bd_thopen` e o `bd_performance`) e a gravação está DESLIGADA até as decisões do Levi (8): quem chama
    é o `--ensaio` (`ferramentas/carregar_dados.py` e `ferramentas/carregar_geracao.py`). Lê as 171 abas inteiras
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

    _LACO["thread"] = threading.Thread(target=laco, name="nexus-carga-dados", daemon=True)
    _LACO["thread"].start()
