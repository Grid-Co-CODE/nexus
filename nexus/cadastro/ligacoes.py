"""Ligações entre as bases: o de_para calculado, os buracos e as decisões de quem corrige (tela Base → Ligações).

Pedido do Levi (04/10/2026): "quero uma tela para fazer os de-para pelo Nexus, quero que esses buracos de ligação fiquem
expostos para que possamos corrigir". Três tipos de buraco:
- chave de uma base que não liga a usina nenhuma (ex.: "Solier - Cascavel - CE" no Fracttal);
- ligação feita só pelo nome, que alguém precisa conferir;
- usina em operação que uma base não enxerga (ex.: as 13 da Elis Energia fora do Fracttal, 27/10/2026).

As decisões (ligar à mão, desligar, ignorar, ausência esperada) moram no arquivo de regras, fora do git (são nomes de
usina de cliente), e valem no próximo cálculo e no próximo envio ao banco. O cálculo guarda as fontes lidas
(`de_para_atual.json`): decidir não precisa buscar as bases de novo.
"""
import json
import os
import pickle
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

from . import banco as B
from . import casamento as K
from . import ligacao_fama
# o `fato_os_fama` só importa o calendário no topo, nada do cadastro: sem ciclo
from ..dados import fato_os_fama as FAMA

SISTEMA_FAMA = FAMA.SISTEMA

_BRT = timezone(timedelta(hours=-3))
DADOS_PADRAO = Path(r"C:\GridcoAuto\nexus") if os.name == "nt" else Path(__file__).resolve().parents[2] / "dados"
BASE_API = "https://app.gridco.com.br/db_performace"
FRACTTAL = "Fracttal · Classificação 1"
# (sistema no de-para, workbook, aba, coluna do nome, coluna do código, cliente fixo)
FONTES_API = (
    ("BD_Performance · Base UFV", "bd_performance", "Base UFV", "Usina", "Código", None),
    ("Tickets · Base de dados - Usinas", "tickets_performance", "Base de dados - Usinas", "Usina", "Código da usina", None),
    ("BD_Thopen · Dados Gerais Usinas", "bd_thopen", "Dados Gerais Usinas", "Usina", None, "Thopen"),
)
# Geração em linhas (passo 6c do Kimball, 08/10/2026): cada ABA de geração (uma por usina, um inversor por coluna) é
# uma chave do de-para, e é por ela que o fato `nexus_geracao · fato_geracao_usina_dia` acha o usina_id. Medido em
# 08/10: o sistema de antes (`BD_Performance · Base UFV`, chaves "XXXX-ABC100") casava 0 das 53 abas do BD_Performance,
# porque a aba tem o NOME da usina; a ponte é a aba "Info Geral" da mesma base, que tem o nome e o "Código Fractal".
# (sistema no de-para, workbook, aba de referência da mesma base)
FONTES_ABA = (
    ("BD_Thopen · aba", "bd_thopen", "Dados Gerais Usinas"),
    ("BD_Performance · aba", "bd_performance", "Info Geral"),
)
# Base que só cobre um cliente: usina de outro cliente fora dela não é buraco.
SO_DO_CLIENTE = {"BD_Thopen · Dados Gerais Usinas": "Thopen", "BD_Thopen · aba": "Thopen"}
# Base que não cobre um cliente: as abas do BD_Performance não têm usina da Thopen (0 de 47 usinas ligadas em 08/10; a
# geração delas está no BD_Thopen). Sem isto, a aba "Usinas fora" listaria as 80 da Thopen em operação.
SEM_O_CLIENTE = {"BD_Performance · aba": "Thopen"}
# Base que só cobre os clientes que a usam, sem lista fixa no código: a FAMA (11/11/2026, `ligacao_fama.py`). Usina fora
# dela não é buraco, e a aba "Usinas fora" listaria a carteira inteira
# O plant_id das fontes da plataforma (12/11/2026, a pendência 10 da camada de dados): as falhas de string e de tracker
# e os eventos de tracker só têm o `plant_id` e o nome que a fonte dá à usina, e o de-para não conhecia nenhum dos dois
# (esses fatos só ligavam por nome: 43,6% dos 163 mil eventos de tracker). As abas abaixo trazem o par com o nome
SISTEMA_PLANT = "Plataforma · plant_id"
ABAS_PLANT = (("falhas_performance", "cobertura"), ("falhas_performance", "strings_episodios"),
              ("falhas_performance", "trackers_episodios"), ("falhas_performance", "trackers_dia"))
SEM_AUSENCIA = frozenset({SISTEMA_FAMA, SISTEMA_PLANT})
# A tabela de equipamentos do BD_Performance fecha o ciclo da aba de geração (Levi, 08/10/2026: "usa a tabela
# equipamentos da BD_Performance como base de de-para, se liga ao fractall e aí você ligaria o fractal as usinas do
# BD_Operações e fecharia esse ciclo"). Uma linha por equipamento (a "UFV", as UGs, os inversores), com a "Usina" (o
# nome que as abas de geração das DUAS bases usam) e a "Usina Fractall" (a Classificação 1 do Fracttal, que é a chave
# do sistema FRACTTAL deste de-para). Ciclo: aba -> "Usina" da tabela -> "Usina Fractall" -> a usina a que o FRACTTAL
# liga aquela chave. (workbook, aba, coluna da usina, coluna do nome no Fracttal, coluna do cliente)
EQUIPAMENTOS = ("bd_performance", "Equipamentos", "Usina", "Usina Fractall", "Cliente")
VIA_EQUIPAMENTOS = "equipamentos → Fracttal"
# Como o de_para diz que a ligação veio só do nome (o que vale conferir na tela).
POR_NOME = ("nome", "única da cidade", "de-para de trackers")
TIPOS = ("ligar", "desligar", "ignorar", "ausencia")


# ── onde mora ──────────────────────────────────────────────────────────────────────────────────────────────────

def pasta_dados(config) -> Path:
    """Teste sem pasta própria não grava: em 04/10/2026 um teste escreveu no arquivo de regras de verdade."""
    if config.get("TESTING") and not config.get("NEXUS_DADOS"):
        raise RuntimeError("teste sem NEXUS_DADOS: recuso gravar na pasta de dados real")
    return Path(config.get("NEXUS_DADOS") or DADOS_PADRAO)


def caminho_regras(config) -> Path:
    if config.get("NEXUS_DE_PARA_REGRAS"):
        return Path(config["NEXUS_DE_PARA_REGRAS"])
    return pasta_dados(config) / "de_para_regras.json"


def caminho_atual(config) -> Path:
    return pasta_dados(config) / "de_para_atual.json"


def _gravar(p: Path, dado) -> None:
    """Grava inteiro ou nada, e guarda a versão anterior ao lado."""
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        p.with_suffix(p.suffix + ".anterior").write_bytes(p.read_bytes())
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(dado, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def _agora() -> str:
    return datetime.now(_BRT).isoformat(timespec="seconds")


# ── decisões ───────────────────────────────────────────────────────────────────────────────────────────────────

def carregar_regras(config) -> dict:
    p = caminho_regras(config)
    dado = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return {t: list(dado.get(t) or []) for t in TIPOS} | {"sobre": dado.get("sobre", "")}


class DecisaoInvalida(ValueError):
    pass


def decidir(config, acao: str, sistema: str, chave=None, usina_id=None, cliente_id=None, motivo="", quem="admin"):
    """ligar | desligar | ignorar | ausencia | desfazer. Uma decisão nova para a mesma chave substitui a anterior."""
    r = carregar_regras(config)
    chave = None if chave is None else str(chave)
    if acao == "desfazer":
        tipo = motivo                      # na tela, o tipo da decisão vem no campo "motivo" do desfazer
        if tipo not in TIPOS:
            raise DecisaoInvalida("tipo de decisão desconhecido")
        r[tipo] = [d for d in r[tipo] if not _mesma(d, sistema, chave, usina_id, cliente_id)]
    elif acao in ("ligar", "desligar"):
        if not chave or usina_id is None:
            raise DecisaoInvalida("falta a chave ou a usina")
        for t in ("ligar", "desligar", "ignorar"):
            r[t] = [d for d in r[t] if not (d.get("sistema") == sistema and str(d.get("chave")) == chave)]
        d = {"sistema": sistema, "chave": chave, "usina_id": int(usina_id), "quem": quem, "quando": _agora()}
        if motivo.strip():                 # o lote diz que veio dele (a aba Decisões mostra); fica só aqui, no arquivo
            d["motivo"] = motivo.strip()   # local: o de-para publicado leva "manual (dd/mm)" e nada mais
        r[acao].append(d)
    elif acao == "ignorar":
        if not chave or not motivo.strip():
            raise DecisaoInvalida("diga por que ignorar")
        for t in ("ligar", "desligar", "ignorar"):
            r[t] = [d for d in r[t] if not (d.get("sistema") == sistema and str(d.get("chave")) == chave)]
        r["ignorar"].append({"sistema": sistema, "chave": chave, "motivo": motivo.strip(), "quem": quem, "quando": _agora()})
    elif acao == "ausencia":
        if usina_id is None and cliente_id is None or not motivo.strip():
            raise DecisaoInvalida("diga a usina (ou o cliente) e o motivo")
        r["ausencia"].append({"sistema": sistema, "usina_id": None if usina_id is None else int(usina_id),
                              "cliente_id": None if cliente_id is None else int(cliente_id),
                              "motivo": motivo.strip(), "quem": quem, "quando": _agora()})
    else:
        raise DecisaoInvalida("ação desconhecida")
    _gravar(caminho_regras(config), r)
    return r


def _mesma(d, sistema, chave, usina_id, cliente_id) -> bool:
    if d.get("sistema") != sistema:
        return False
    if chave is not None:
        return str(d.get("chave") or d.get("contem")) == chave
    if usina_id is not None:
        return d.get("usina_id") == int(usina_id)
    return cliente_id is not None and d.get("cliente_id") == int(cliente_id)


# ── fontes ─────────────────────────────────────────────────────────────────────────────────────────────────────

def _linhas_api(base, sid):
    import requests
    out, offset = [], 0
    while True:
        r = requests.get(f"{base}/api/sheets/{sid}/rows", params={"limit": 1000, "offset": offset}, timeout=60)
        r.raise_for_status()
        rows = r.json()
        rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
        out += [dict(zip(x.get("headers") or [], x.get("values") or [])) for x in rows]
        if len(rows) < 1000:
            return out
        offset += 1000


def fontes(config) -> dict:
    """O Fracttal vem primeiro: o que ele liga vira a dica do de-para de trackers para o BD_Thopen."""
    if config.get("TESTING"):
        return config.get("NEXUS_LIGACOES_FONTES_TESTE") or {}
    import requests
    base = (config.get("GRIDCO_DB_API") or BASE_API).rstrip("/")
    abas = {(x["workbook_key"], x["sheet_name"]): x["id"] for x in requests.get(f"{base}/api/sheets", timeout=60).json()}
    out = {FRACTTAL: fracttal(config)}
    # os locais dos almoxarifados (25/10/2026): "Cliente - Usina - UF", a mesma chave da Classificação 1, lidos do livro
    # que o App publica (igual nas duas máquinas); o que a Classificação 1 não tem (a Nobres) entra para ligar à mão.
    # O almoxarifado de TESTE do inventário (NEXUS_ALMOX_TESTE_IDS) não: o local dele não é usina para ligar
    from ..dados import almoxarifado as ALM
    if (ALM.LIVRO_SALDO, ALM.ABA_SALDO) in abas:
        saldo = ALM.sem_almoxarifado_de_teste(_linhas_api(base, abas[(ALM.LIVRO_SALDO, ALM.ABA_SALDO)]), config)
        out[FRACTTAL] += locais_de_almoxarifado(saldo, {str(i.get("chave")) for i in out[FRACTTAL]})
    # as usinas que só a foto dos ativos tem (12/11/2026): depois das tarefas, da árvore do PCM e dos almoxarifados
    from ..dados import equipamento as EQP
    if (EQP.LIVRO_FOTO, EQP.ABA_FOTO) in abas:
        out[FRACTTAL] += usinas_da_foto(_linhas_api(base, abas[(EQP.LIVRO_FOTO, EQP.ABA_FOTO)]),
                                        {str(i.get("chave")) for i in out[FRACTTAL]})
    dicas = {}
    if ("de_para_trackers", "Resumo por usina") in abas:
        for t in _linhas_api(base, abas[("de_para_trackers", "Resumo por usina")]):
            if t.get("Fonte") == "Banco de Dados" and t.get("UFV Fracttal"):
                dicas[B.norm(re.sub(r"^\(\d+\)\s*", "", str(t["UFV Supervisório"])))] = t["UFV Fracttal"]
    lidas = {}
    for sistema, wb, aba, c_nome, c_cod, cliente in FONTES_API:
        itens = []
        lidas[(wb, aba)] = _linhas_api(base, abas[(wb, aba)])
        for d in lidas[(wb, aba)]:
            nome, cod = d.get(c_nome), d.get(c_cod) if c_cod else None
            if not nome:
                continue
            cod = cod if isinstance(cod, str) and cod.strip() else None
            it = {"chave": cod or nome, "codigo": cod, "nome": nome, "cliente": cliente or d.get("Cliente")}
            if not c_cod:          # base sem código (BD_Thopen): nome, cidade, estado e potência para o casamento
                mwp = d.get("Potência (MWp)")
                it.update({"nomes": [nome, d.get("Nome")], "cidade": d.get("Cidade"), "uf": d.get("Estado"),
                           "mwp": float(mwp) if isinstance(mwp, (int, float)) else None,
                           "dica": dicas.get(B.norm(nome)) or dicas.get(B.norm(d.get("Nome")))})
            itens.append(it)
        out[sistema] = itens
    # a tabela de equipamentos (a ponte aba -> Fracttal); sem a aba no banco, as abas casam como antes de 08/10
    equipamentos = _linhas_api(base, abas[EQUIPAMENTOS[:2]]) if EQUIPAMENTOS[:2] in abas else None
    # as chaves que a tela Equipamentos das usinas pôs "no lugar da aba" (13/10/2026): a visão do Nexus troca as linhas
    # delas, como em todo leitor da aba (estrutura_usina.sobrepor)
    from . import estrutura_usina as EU
    if (EU.LIVRO, EU.ABA_VISAO) in abas:
        equipamentos = EU.sobrepor(equipamentos or [], _linhas_api(base, abas[(EU.LIVRO, EU.ABA_VISAO)]))
    for sistema, wb, ref in FONTES_ABA:      # depois das FONTES_API: o `igual_a` aponta chaves já casadas
        ids = {a: sid for (w, a), sid in abas.items() if w == wb}
        if (wb, ref) not in lidas:
            lidas[(wb, ref)] = _linhas_api(base, abas[(wb, ref)]) if (wb, ref) in abas else []
        out[sistema] = itens_abas(sistema, _primeiras_linhas(base, ids), lidas[(wb, ref)], dicas, equipamentos)
    # os projetos da FAMA (11/11/2026): a dimensão que a leitura das OS, de 10 em 10 minutos, grava no banco; sem o livro
    # (antes da 1ª volta do servidor), a FAMA não aparece
    if (FAMA.LIVRO, FAMA.ABA_DIM) in abas:
        out[SISTEMA_FAMA] = ligacao_fama.itens(_linhas_api(base, abas[(FAMA.LIVRO, FAMA.ABA_DIM)]))
    # o plant_id das fontes da plataforma (12/11/2026): pelas abas de falhas e pela estrutura das usinas
    lidas_plant = [_linhas_api(base, abas[k]) for k in ABAS_PLANT if k in abas]
    if lidas_plant:
        sup = _linhas_api(base, abas[(EU.LIVRO, EU.ABA_SUP)]) if (EU.LIVRO, EU.ABA_SUP) in abas else []
        out[SISTEMA_PLANT] = itens_plant(lidas_plant, sup)
    return out


def _primeiras_linhas(base, ids: dict) -> dict:
    """{aba: [1ª linha]}: o cabeçalho e o nome na coluna "Usina" de cada aba, uma página de 1 linha por aba, em
    paralelo. Ler as abas inteiras levaria ~1 min (76 mil linhas em 08/10); a tela de Ligações espera por isto."""
    import requests
    from concurrent.futures import ThreadPoolExecutor

    def uma(item):
        aba, sid = item
        r = requests.get(f"{base}/api/sheets/{sid}/rows", params={"limit": 1, "offset": 0}, timeout=60)
        r.raise_for_status()
        rows = r.json()
        rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
        return aba, [dict(zip(x.get("headers") or [], x.get("values") or [])) for x in rows[:1]]

    with ThreadPoolExecutor(max_workers=6) as ex:
        return dict(ex.map(uma, ids.items()))


def indice_equipamentos(linhas) -> dict:
    """{nome da usina normalizado: [(cliente, nome no Fracttal ou None), ...]} da tabela de equipamentos (`EQUIPAMENTOS`),
    uma entrada por linha (equipamento)."""
    _wb, _aba, c_usina, c_fracttal, c_cliente = EQUIPAMENTOS
    out = defaultdict(list)
    for d in linhas or ():
        if str(d.get(c_usina) or "").strip():
            f = str(d.get(c_fracttal) or "").strip()
            out[B.norm(d[c_usina])].append((str(d.get(c_cliente) or "").strip(), f or None))
    return out


def ponte_equipamentos(nomes, indice: dict, so_cliente: str | None = None,
                       sem_cliente: str | None = None) -> tuple[str | None, str | None, str | None]:
    """(nome no Fracttal, motivo de não ter, nome da usina na tabela) de uma aba pela tabela de equipamentos. Vale o 1º
    dos `nomes` (a aba, depois a coluna Usina dela) que tem linha na tabela, só do cliente da base (`SO_DO_CLIENTE`,
    `SEM_O_CLIENTE`: E1 não é Thopen). A usina tem de dar UM nome do Fracttal em todas as suas linhas: a "Rodrigues 2"
    tinha 11 equipamentos em "Thopen - Rodrigues 2 - RN" e a linha UFV em "Thopen - Rodrigues 1 - RN" (08/10): escolher
    um dos dois seria chutar, e a tabela é que se conserta."""
    def do_cliente(c):
        return (not so_cliente or B.norm(c) == B.norm(so_cliente)) and not (sem_cliente and B.norm(c) == B.norm(sem_cliente))
    for n in nomes or ():
        linhas = [f for c, f in indice.get(B.norm(n), ()) if do_cliente(c)]
        if not linhas:
            continue
        unicos = {}
        for f in linhas:
            if f:
                unicos.setdefault(" ".join(f.split()).casefold(), f)    # espaço e caixa não fazem outro nome
        if len(unicos) == 1:
            return next(iter(unicos.values())), None, n
        if not unicos:
            return None, "sem 'Usina Fractall' na tabela de equipamentos", n
        return None, f"{len(unicos)} nomes do Fracttal na tabela de equipamentos", n
    return None, "sem linha na tabela de equipamentos", None


def itens_abas(sistema: str, primeiras: dict, referencia: list, dicas: dict | None = None,
               equipamentos: list | None = None) -> list[dict]:
    """As chaves de um sistema de aba (`FONTES_ABA`): uma por aba de GERAÇÃO (o mesmo critério do fato,
    `nexus.dados.geracao.abas_de_geracao`), e a chave é o nome da aba. `primeiras` = {aba: [1ª linha]};
    `referencia` = as linhas da aba de referência da mesma base (a 3ª coluna de `FONTES_ABA`); `equipamentos` = as
    linhas da tabela de equipamentos do BD_Performance (`EQUIPAMENTOS`; None = sem a ponte, como antes de 08/10).
    - Tabela de equipamentos (o caminho principal, Levi 08/10): a aba cuja "Usina" na tabela dá UM nome do Fracttal
      leva `ponte` = (FRACTTAL, nome, via); sem isso, `ponte_motivo` diz por quê. Quem resolve é `banco.de_para`, pela
      ligação que o FRACTTAL deu àquele nome; os caminhos abaixo continuam montados, para conferir e para a aba que a
      ponte não fecha.
    - Referência que já é sistema do de-para (o "Dados Gerais Usinas" do BD_Thopen): a aba cujo nome, ou a coluna
      Usina, é o de uma linha dela é a MESMA usina daquela chave: vai `igual_a`, e herda a ligação e as decisões da tela
      (98 de 100 abas em 08/10). Leva também cidade, estado, potência e a dica, para o casamento quando ela não liga.
    - Referência que não é sistema (a "Info Geral" do BD_Performance, que tem o nome e o "Código Fractal"): a aba em
      forma de código ("ABC100") é o próprio código; a aba com nome leva o código da Info Geral como `codigo` +
      `codigo_de` (53 de 53 abas acham a linha em 08/10) e o cliente dela, para o casamento quando o código não liga.
    Nome que está em 2 linhas da referência não é ponte: ligação errada é pior que faltando."""
    from ..dados.geracao import abas_de_geracao
    wb_ref = next(((w, r) for s, w, r in FONTES_ABA if s == sistema), None)
    sistema_ref = next((s for s, w, a, *_ in FONTES_API if (w, a) == wb_ref), None)
    cliente_fixo = SO_DO_CLIENTE.get(sistema)
    idx_eq = indice_equipamentos(equipamentos) if equipamentos is not None else None
    idx = defaultdict(list)
    for d in referencia or ():
        if d.get("Usina") not in (None, ""):
            idx[B.norm(d["Usina"])].append(d)
    out = []
    for aba, linhas, _cols in abas_de_geracao(primeiras):
        na_coluna = next((str(l["Usina"]).strip() for l in linhas if l.get("Usina") not in (None, "")), "")
        nomes = [aba] + ([na_coluna] if na_coluna and B.norm(na_coluna) != B.norm(aba) else [])
        par = next((idx[B.norm(n)][0] for n in nomes if len(idx.get(B.norm(n), ())) == 1), None)
        it = {"chave": aba, "nome": aba, "nomes": nomes}
        if cliente_fixo:
            it["cliente"] = cliente_fixo
        if sistema_ref:
            if par:
                mwp = par.get("Potência (MWp)")
                it.update({"igual_a": (sistema_ref, par["Usina"]), "cidade": par.get("Cidade"),
                           "uf": par.get("Estado"), "mwp": float(mwp) if isinstance(mwp, (int, float)) else None})
            it["dica"] = next((dicas[B.norm(n)] for n in nomes if B.norm(n) in (dicas or {})), None)
        else:
            if re.fullmatch(r"[A-Z]{3}\d{3}", aba.strip()):
                it["codigo"] = aba.strip()
            elif par and str(par.get("Código Fractal") or "").strip():
                it.update({"codigo": str(par["Código Fractal"]).strip(), "codigo_de": wb_ref[1]})
            if par and par.get("Cliente") and not cliente_fixo:
                it["cliente"] = par["Cliente"]
        if idx_eq is not None:
            nome_f, motivo, usina_eq = ponte_equipamentos(nomes, idx_eq, cliente_fixo, SEM_O_CLIENTE.get(sistema))
            if nome_f:
                it["ponte"] = (FRACTTAL, nome_f, VIA_EQUIPAMENTOS)
            else:
                it["ponte_motivo"] = motivo
            if usina_eq:
                it["usina_equipamentos"] = usina_eq
        out.append(it)
    return out


_USINA_UF = re.compile(r"\s*(.+?)\s+-\s+(.+?)\s+-\s+[A-Z]{2}\s*")
ARVORE = "_ativos_classificacao_cache.json"      # {id do ativo: [Classificação 1, Classificação 2]}, do motor do PCM


def usina_do_caminho(caminho):
    """"// Thopen/ Thopen - Brodowski 1 - SP/ Cabine 1/" -> ("Thopen", "Brodowski 1"). Só o pedaço "Cliente - Usina - UF"."""
    for p in str(caminho or "").split("/"):
        m = _USINA_UF.fullmatch(p)
        if m:
            return m.group(1), m.group(2)
    return None


def usinas_da_arvore(caminho: Path, ja: set) -> list[dict]:
    """As usinas da árvore de ativos do Fracttal ("Cliente - Usina - UF", a Classificação 1 de cada ativo, que o motor do
    PCM guarda ao lado da foto) que as tarefas ainda não têm. Caso de 27/10/2026: das 53 usinas que iam ao App sem o nome
    do Fracttal (PCM → Técnicos por usina), 40 da Faro, da Apolo e da RenoGrid estão na árvore e quase não têm tarefa;
    sem esta leitura elas não apareciam nas Ligações e não havia como ligá-las. Nome que só muda no espaço, na caixa ou
    no acento de uma chave que já existe não entra (seria a mesma usina duas vezes)."""
    if not caminho.exists():
        return []
    try:
        dado = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []                        # árvore ilegível: fica só o que as tarefas dizem
    vistos = {B.norm(k) for k in ja}
    novos = []
    for n in sorted({str(v[0]).strip() for v in dado.values() if isinstance(v, list) and v and v[0]}):
        if _USINA_UF.fullmatch(n) and B.norm(n) not in vistos:
            vistos.add(B.norm(n))
            novos.append({"chave": n, "nome": n, "origem": "árvore de ativos do Fracttal"})
    return novos


def usinas_da_foto(linhas_foto, ja: set) -> list[dict]:
    """As usinas da foto dos ativos do Fracttal no banco (`nexus_ativos_fracttal · foto_ativos`, que o leitor do servidor
    renova toda noite: igual nas duas máquinas) que ainda não são chave: a RAIZ de cada usina, o item cujo código é só o
    da usina ("XYZ-ABC100") e cujo nome é "Cliente - Usina - UF". Vai com o código, que é por onde ela liga ao Registro
    mestre. Caso de 12/11/2026: 14 usinas de um cliente em operação sem o nome do Fracttal no de-para, e a foto já com
    2.362 ativos com o prefixo dele; a tela só conhecia as usinas das tarefas e da árvore que o motor do PCM guarda em
    arquivo (a de quem rodou o PCM por último naquela máquina). O item que saiu do Fracttal não entra, e a grafia que só
    muda no espaço, na caixa ou no acento de uma chave que já existe também não (seria a mesma usina duas vezes)."""
    vistos = {B.norm(k) for k in ja}
    novos = []
    for x in sorted(linhas_foto or (), key=lambda x: str(x.get("descricao") or "")):
        cod, nome = str(x.get("codigo") or "").strip().upper(), str(x.get("descricao") or "").strip()
        if not cod or B.codigo_do_equipamento(cod) != cod or not _USINA_UF.fullmatch(nome):
            continue
        if str(x.get("fora_do_fracttal_desde") or "").strip() or B.norm(nome) in vistos:
            continue
        vistos.add(B.norm(nome))
        novos.append({"chave": nome, "nome": nome, "codigo": cod, "origem": "foto dos ativos do Fracttal"})
    return novos


def _chave_sup(v) -> str:
    """A chave do supervisório para comparar: os espaços juntados (a aba e a API PV escrevem "Assis Chateaubriand  Skid 1
    (79)", com espaço duplo, e a estrutura guarda com um) e sem caixa."""
    return " ".join(str(v or "").split()).casefold()


def _plant(v) -> str:
    """O plant_id como texto: 18749574.0 do banco é o 18749574; o de letras (o código-base) fica como vem."""
    t = str(v if v is not None else "").strip()
    return t[:-2] if re.fullmatch(r"\d+\.0", t) else t


def itens_plant(abas, supervisorios) -> list[dict]:
    """As chaves do sistema `Plataforma · plant_id`, uma por plant_id das abas de falhas (`ABAS_PLANT`), com a usina a
    que o NOME da fonte leva pela chave do supervisório da estrutura das usinas (`nexus_estrutura_usina ·
    dim_supervisorio`: uma chave serve a uma usina só, e quem a ligou foi a tela Equipamentos das usinas ou o Modo
    de-para). `pela_estrutura` = o usina_id, ou None: o nome fora da estrutura, a chave desligada e o plant_id cujos
    nomes levam a duas usinas não ligam (ficam à vista na seção, para ligar à mão). Medido em 12/11/2026: os 26 plant_id
    que aparecem em mais de uma fonte são a mesma usina com o mesmo nome, por isso a chave é só o plant_id."""
    dono = defaultdict(set)
    for x in supervisorios or ():
        if str(x.get("excluido") or "").strip().lower() != "sim" and B._id(x.get("usina_id")):
            dono[_chave_sup(x.get("usina_supervisorio"))].add(B._id(x.get("usina_id")))
    nomes = defaultdict(Counter)
    for linhas in abas or ():
        for x in linhas or ():
            pid, nome = _plant(x.get("plant_id")), " ".join(str(x.get("usina") or "").split())
            if pid and nome:
                nomes[pid][nome] += 1
    out = []
    for pid in sorted(nomes):
        usinas = set()
        for nome in nomes[pid]:
            d = dono.get(_chave_sup(nome), set())
            usinas |= d if len(d) == 1 else set()
        nome = nomes[pid].most_common(1)[0][0]
        out.append({"chave": pid, "nome": nome, "rotulo": f"{nome} · plant_id {pid}",
                    "pela_estrutura": next(iter(usinas)) if len(usinas) == 1 else None})
    return out


def locais_de_almoxarifado(linhas_saldo: list[dict], ja: set) -> list[dict]:
    """Os locais de almoxarifado ("Cliente - Usina - UF", do livro Saldo do App) que ainda não são chave do sistema
    Fracttal: a usina sem Classificação 1 nas tarefas (a Nobres, 25/10/2026) não aparecia na tela, e não havia como
    ligar o almoxarifado dela."""
    from ..dados.almoxarifado import chave_do_local
    novos = []
    for l in linhas_saldo:
        k = chave_do_local(l.get("Local do almoxarifado"))
        if k and k not in ja:
            ja = ja | {k}
            novos.append({"chave": k, "nome": k, "origem": "local de almoxarifado"})
    return novos


def fracttal(config) -> list[dict]:
    """Usinas do Fracttal ("Cliente - Usina - UF") com o código tirado dos códigos de equipamento das tarefas: a foto
    mais nova que o motor do PCM gravou nas rodadas do Nexus, mais as usinas da árvore de ativos guardada
    ao lado dela que ainda não têm tarefa (`usinas_da_arvore`). Sem foto, só a lista de ativos (pelo nome)."""
    from ..pcm import geracao as G
    trab, origem = G.pasta_trabalho(config), G.pasta_origem(config)
    # só a foto das rodadas do Nexus: a da pasta de origem do PCM (OneDrive da equipe) não se abre, porque o `pickle`
    # executa código do arquivo e quem grava lá não é só o motor (auditoria de 08/11/2026)
    fotos = [p for p in (Path(trab) / "geracoes").glob("*/.cache_semanal_api.pkl") if p.exists()]
    if fotos:
        foto = max(fotos, key=lambda p: p.stat().st_mtime)
        with open(foto, "rb") as f:          # arquivo do motor do PCM, gravado pelo Nexus na rodada (`geracoes/`)
            df = pickle.load(f)["df"]
        itens = []
        df = df.assign(_u=df["Ativo Classificação 1"].fillna("").astype(str).str.strip())
        for usina, g in df[df["_u"] != ""].groupby("_u"):
            cods = Counter(c for c in (B.codigo_do_equipamento(x) for x in g["Código"]) if c).most_common(1)
            itens.append({"chave": usina, "nome": usina, "codigo": cods[0][0] if cods else None, "tarefas": len(g)})
        # Ativo sem "Classificação 1" (04/10: 584 tarefas, Brodowski e Nobres entre elas). A usina sai do código do
        # equipamento ("BWK100-INVR1" é Brodowski) e, sem código que case, da "Localização ou parte de" do próprio
        # ativo ("// Thopen/ Thopen - Brodowski 1 - SP/ Cabine 1/"): é assim que "BWK200" e "Transformador 2" acham a usina.
        sem = df[df["_u"] == ""]
        for cod, g in sem.groupby(sem["Código"].map(lambda x: B.codigo_do_equipamento(x)
                                                    or "-".join(str(x or "sem código").split("-")[:2]))):
            it = {"chave": f"(sem Classificação 1) {cod}", "codigo": cod, "tarefas": len(g)}
            locais = Counter(m for m in (usina_do_caminho(x) for x in g["Localização ou parte de"]) if m).most_common(1)
            if locais:
                cliente, usina = locais[0][0]
                it.update({"cliente": cliente, "nomes": [usina], "origem": "localização no Fracttal",
                           "nome": f"{cliente} - {usina}"})
            itens.append(it)
        return itens + usinas_da_arvore(foto.parent / ARVORE, {str(i["chave"]) for i in itens})
    for pasta in (trab, origem):
        cache = Path(pasta or "") / ARVORE
        if pasta and cache.exists():
            nomes = sorted({v[0] for v in json.loads(cache.read_text(encoding="utf-8")).values() if v and v[0]})
            return [{"chave": n, "nome": n} for n in nomes]
    return []


# ── cálculo ────────────────────────────────────────────────────────────────────────────────────────────────────

def calcular(config, srv, fs: dict | None = None) -> dict:
    """Lê as bases (ou usa `fs`, as fontes já lidas), aplica as decisões e guarda o resultado."""
    fs = fontes(config) if fs is None else fs
    res = {"gerado_em": _agora() if fs is not None else None, "fontes": fs,
           "linhas": B.de_para(srv, fs, carregar_regras(config))}
    _gravar(caminho_atual(config), res)
    return res


def reaplicar(config, srv) -> dict | None:
    """Depois de uma decisão: as mesmas fontes, as regras novas. Sem buscar nada na rede."""
    atual = ler(config)
    if not atual:
        return None
    atual["linhas"] = B.de_para(srv, atual["fontes"], carregar_regras(config))
    _gravar(caminho_atual(config), atual)
    return atual


def ler(config) -> dict | None:
    p = caminho_atual(config)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# ── o que a tela mostra ────────────────────────────────────────────────────────────────────────────────────────

def _usinas(srv) -> list[dict]:
    out = []
    for u in srv.registros("usinas"):
        cliente = srv.titulo_de("clientes", u.valor("cliente"))
        pot = u.valor("potencia_contratual")
        out.append({"id": B._id(u.id), "nome": u.valor("nome"), "cliente": cliente,
                    "cliente_id": B._id(u.valor("cliente")) if isinstance(u.valor("cliente"), str) else None,
                    "titulo": f"{cliente} - {u.valor('nome')}" if cliente else str(u.valor("nome")),
                    "codigo": u.valor("codigo") or "", "cidade": u.valor("cidade"), "uf": u.valor("uf"),
                    "status": u.valor("status") or "", "equipe": srv.titulo_de("equipes", u.valor("equipe")),
                    "mwp": float(pot) if isinstance(pot, (int, float)) and not isinstance(pot, bool) else None})
    return out


def _sem_cliente_e_uf(nome, cliente) -> str:
    s = str(nome or "")
    if cliente and B.norm(s).startswith(B.norm(cliente)):
        s = s[len(str(cliente)):] if s.lower().startswith(str(cliente).lower()) else s.split(" - ", 1)[-1]
    s = re.sub(r"^\s*-\s*", "", s)
    return re.sub(r"\s*-\s*[A-Z]{2}\s*$", "", s).strip()


def mesmo_cliente(a, b) -> bool:
    """O mesmo cliente: o nome igual (sem acento, caixa e pontuação) ou um nome é o começo do outro, palavra por palavra.
    O Fracttal escreve o cliente mais curto que o cadastro ("Aurora" para a "Aurora Energia", nomes inventados; o caso
    real de 12/11/2026: por isso as chaves "<Cliente> - X 1 - UF" desse cliente nunca tinham sugestão). Começo de palavra
    não vale: "Aurorax" não é a "Aurora Energia". Quem escolhe o cliente da chave é o `_clientes_da_chave`: o exato
    primeiro, e o começo só sem ele."""
    x, y = B.norm(a).split(), B.norm(b).split()
    n = min(len(x), len(y))
    return bool(n) and x[:n] == y[:n]


def _nome_e_cliente(item: dict) -> tuple:
    nome, cliente = item.get("nome") or (item.get("nomes") or [item.get("chave")])[0], item.get("cliente")
    m = re.fullmatch(r"\s*(.+?)\s+-\s+(.+?)(?:\s+-\s+[A-Z]{2})?\s*", str(nome or ""))
    if not cliente and m:                   # Fracttal: "Athon - Matões 1 - MA" traz o cliente no próprio nome
        cliente, nome = m.group(1), m.group(2)
    return nome, cliente


def _clientes_da_chave(cliente, usinas: list[dict]) -> tuple[frozenset, frozenset]:
    """(os clientes do cadastro que valem para a chave, os que ficaram em dúvida). O de nome exato vale sozinho, se houver
    (revisão de 12/11/2026: com "Aurora" e "Aurora Solar" no cadastro, o começo do nome levava a chave da Aurora à usina
    da Aurora Solar a 100%; um cliente não é outro, Levi 04/10); sem ele, o que começa igual (`mesmo_cliente`), só se for
    UM. Dois pelo começo é dúvida: nenhum vale."""
    alvo = B.norm(cliente)
    nomes = {u["cliente"] for u in usinas if u.get("cliente")}
    exatos = frozenset(c for c in nomes if B.norm(c) == alvo)
    if exatos:
        return exatos, frozenset()
    pelo_comeco = frozenset(c for c in nomes if mesmo_cliente(c, cliente))
    if len({B.norm(c) for c in pelo_comeco}) == 1:
        return pelo_comeco, frozenset()
    return frozenset(), pelo_comeco


def novas_que_cruzam_cliente(srv, fontes: dict, novas: list[list], no_banco: list[dict]) -> list[dict]:
    """As ligações NOVAS (a chave não tem usina no banco) que uma regra automática faria entre a chave que diz um cliente
    e a usina de OUTRO: [{"sistema", "chave_externa", "de": [], "para": [usinas], "casou_por", "cliente_da_chave",
    "cliente_da_usina"}], por sistema e chave, no formato das trocas (`banco.chaves_que_trocariam`): entram na mesma
    lista do aceite da publicação (`banco.a_aceitar`). O cliente da chave é o do item ou, SÓ no Fracttal, o começo do nome
    (`_nome_e_cliente`; a revisão de 13/11/2026 achou o nome de outras bases lido como cliente: o skid "Usina - Skid 1"
    do supervisório entrava na lista); vale para ele o cliente do cadastro que as sugestões aceitam
    (`_clientes_da_chave`: o nome exato, ou o começo do nome se for um só). Não entra: a chave que o banco já liga (a mesma usina é o que já está lá;
    outra usina é troca), a ligada à mão, a que não diz cliente e a linha sem item nas bases lidas (o ID do BD da ficha,
    que vem do Registro mestre).

    O caso (13/11/2026): a trava da troca nasceu porque a chave do Fracttal de um cliente foi para a usina de outro pelo
    sufixo do código, e só pegava a chave que o banco já ligava. A mesma coisa numa chave nova (a usina que acabou de
    entrar no Fracttal) passava sem trava nenhuma. Medido nos dados do PC antes de fazer: só o Fracttal traz o cliente
    no nome (as outras bases têm o campo), e entre todas as ligações automáticas duas cruzavam cliente, as duas antigas
    e pelo cliente escrito errado na fonte."""
    usinas = _usinas(srv)
    cliente_de = {u["id"]: u.get("cliente") or "" for u in usinas}
    ja_ligadas = {(str(d.get("sistema")), B._chave_comparavel(d.get("chave_externa")))
                  for d in no_banco if B._inteiro(d.get("usina_id")) is not None}
    itens = {(str(s), B._chave_comparavel(it["chave"])): it for s, its in (fontes or {}).items() for it in its}
    agora: dict = {}
    for l in novas:
        a = agora.setdefault((str(l[1]), B._chave_comparavel(l[2])), {"ids": set(), "chave": l[2], "como": None})
        uid = B._inteiro(l[0])
        if uid is not None:
            a["ids"].add(uid)
            a["como"] = a["como"] or l[3]
    out = []
    for k in sorted(agora):
        a, it = agora[k], itens.get(k)
        como = str(a["como"] or "")
        if not a["ids"] or it is None or k in ja_ligadas or como.startswith("manual"):
            continue
        # o cliente no começo do nome é o padrão do Fracttal ("Cliente - Usina - UF"); noutra base o nome com " - "
        # não começa pelo cliente (o "Usina - Skid 1" do supervisório): lá só vale o campo do item
        dito = _nome_e_cliente(it)[1] if k[0] == FRACTTAL else it.get("cliente")
        if not B.norm(dito or ""):
            continue
        validos = _clientes_da_chave(dito, usinas)[0]
        de_outro = sorted({cliente_de.get(u) or "sem cliente" for u in a["ids"] if cliente_de.get(u) not in validos})
        if de_outro:
            out.append({"sistema": k[0], "chave_externa": a["chave"], "de": [], "para": sorted(a["ids"]),
                        "casou_por": a["como"], "cliente_da_chave": str(dito).strip(),
                        "cliente_da_usina": ", ".join(de_outro)})
    return out


_UFS = frozenset(K.UF.values())


def _uf_da_chave(item: dict) -> str | None:
    """A UF que a chave diz: a do item (o "Estado" do BD_Thopen, por extenso ou em sigla) ou a do fim do nome do Fracttal
    ("Cliente - Usina 1 - BA"); só as 27."""
    if item.get("uf"):
        uf = K.UF.get(K._ascii(item["uf"]), str(item["uf"]).strip().upper()[:2])
        return uf if uf in _UFS else None
    nome = item.get("nome") or (item.get("nomes") or [item.get("chave")])[0]
    m = re.search(r"\s-\s*([A-Z]{2})\s*$", str(nome or ""))
    return m.group(1) if m and m.group(1) in _UFS else None


def _trava(item: dict, u: dict, primeiro: str | None) -> str | None:
    """As mesmas travas do casamento automático (achadas na tela real, 04/10/2026), que valem para toda sugestão: o que
    impede a usina `u` de ser a chave, ou None. O identificador é o número ou a letra solta (`casamento.termos`)."""
    ids_u = K.identificadores_da_usina(u["nome"])
    if primeiro and ids_u and primeiro not in ids_u:
        return "o número"                   # "Marajoara 2" (e "Marajoara 2 1") não é a "Marajoara 1"; "Pinhal A", a B
    if item.get("cidade") and K.mesma_cidade(item["cidade"], u["cidade"]) is False:
        return "a cidade"                   # "Ouro Branco I" de Bandeirantes/PR não é a "Ouro Branco" de AL
    mwp = item.get("mwp")
    if mwp and u.get("mwp") and abs(u["mwp"] - mwp) > 0.4 * max(u["mwp"], mwp):
        return "a potência"                 # "AP. do Taboado" (0,41 MWp) não é a "Aparecida do Taboado 1 e 2" (2,58)
    return None


def sugestoes(item: dict, usinas: list[dict], n: int = 3) -> list[dict]:
    """As usinas do cadastro mais parecidas com uma chave sem par: código (letras do "AAA999"), nome, cliente e cidade.
    Só sugere; quem liga é a pessoa.

    A contenção de palavras (12/11/2026, `casamento.contencao`): a usina cujo nome contém todas as palavras da chave, com
    o mesmo número ou letra, vem a 100 se for a ÚNICA do cliente assim. Fica abaixo de 100, fora do lote
    (`casamento.NOTA_CONTIDA_*`, revisão de 12/11/2026): o nome do cadastro que cabe na chave, a chave com palavras a mais
    (95, a palavra a mais pode ser a que separa duas usinas); a chave sem o cliente (90); duas ou mais (80, e nenhuma
    sugestão acima de 95); e a UF da chave diferente da usina (95, sem vetar: a base também erra a UF). A sugestão com
    ressalva leva o texto em `ressalva`, que o "por quê" da seção mostra. O que só a parecença de letras acha segue como
    antes, e as travas valem para as duas."""
    cod = B.sufixo_codigo(item.get("codigo") or (item.get("chave") if re.fullmatch(r"[A-Z0-9-]+", str(item.get("chave"))) else ""))
    nome, cliente = _nome_e_cliente(item)
    texto = _sem_cliente_e_uf(nome, cliente)
    nome_item = " ".join(K.palavras(texto))
    termos = K.termos(texto)
    cli = B.norm(cliente or "")
    primeiro = K.primeiro_identificador(texto)
    uf = _uf_da_chave(item)
    # E1 não é Thopen (Levi, 04/10): nem como sugestão; o cliente exato, e sem ele o de nome mais curto
    # (`_clientes_da_chave`). Escolhido UMA vez por chave: dentro do laço das usinas era uma varredura do cadastro por
    # usina (12/11/2026, dados inventados: 60 chaves contra 260 usinas levavam 4,7 s)
    validos = _clientes_da_chave(cliente, usinas)[0] if cli else None
    do_cliente = [u for u in usinas if u.get("cliente") in validos] if cli else usinas
    # "a ÚNICA do cliente que contém as palavras com o mesmo número" conta antes das travas de cidade e de potência: a
    # outra candidata vetada pela cidade ainda é dúvida
    rel = {u["id"]: K.contencao(termos, u["nome"]) for u in do_cliente}
    contidas = {i for i, r in rel.items() if r in K.CONTIDAS}
    out = []
    for u in do_cliente:
        if _trava(item, u, primeiro):
            continue
        nota = 0.0
        cu = B.sufixo_codigo(u["codigo"])
        if cod and cu and cod == cu:
            nota += 0.6
        nome_u = " ".join(K.palavras(u["nome"]))
        semelhanca = SequenceMatcher(None, nome_item, nome_u).ratio() if nome_item and nome_u else 0
        if semelhanca >= 0.78:              # abaixo disso é coincidência de letra: na tela real (04/10), "Andradina"
            nota += 0.6 * semelhanca        # sugeria "Canarana" e "Anápolis" sugeria "Fernandópolis", a 53%
        if cli:
            nota += 0.15
        if item.get("cidade") and K.mesma_cidade(item["cidade"], u["cidade"]):
            nota += 0.15
        nota, ressalva = round(min(nota, 1) * 100), None
        if u["id"] in contidas:
            a_mais = rel[u["id"]] == K.MESMO_A_MAIS
            nota = max(nota, K.NOTA_CONTIDA_VARIAS if len(contidas) > 1 else K.NOTA_CONTIDA_SEM_CLIENTE if not cli
                       else K.NOTA_CONTIDA_A_MAIS if a_mais else K.NOTA_CONTIDA_UNICA)
            if a_mais:                      # 95 mesmo com o código e a parecença (o ruling da revisão de 12/11/2026)
                nota = min(nota, K.NOTA_CONTIDA_A_MAIS)
                extra = " ".join(sorted(termos[0] - K.termos(u["nome"])[0]))
                ressalva = (f"a chave tem palavras a mais que a {u['titulo']} ({extra}): pode ser outra usina, confira "
                            f"antes de ligar")
        if len(contidas) > 1:
            nota = min(nota, K.TETO_COM_DUVIDA)
        uf_u = str(u.get("uf") or "").strip().upper()
        if uf and uf_u and uf_u != uf:      # município de mesmo nome em outro estado; a base também erra a UF: não veta
            nota = min(nota, K.TETO_COM_DUVIDA)
            ressalva = ressalva or f"a {u['titulo']} é de {uf_u}, e a chave diz {uf}: confira antes de ligar"
        if nota >= 50:
            s = {"id": u["id"], "titulo": u["titulo"], "codigo": u["codigo"], "nota": nota}
            out.append(dict(s, ressalva=ressalva) if ressalva else s)
    return sorted(out, key=lambda x: -x["nota"])[:n]


def _numero(ns) -> str:
    """Os identificadores da chave como a frase os diz: os números em ordem, depois as letras em maiúscula ("2 e A")."""
    return " e ".join(sorted((w if w.isdigit() else w.upper() for w in ns),
                             key=lambda w: (not w.isdigit(), int(w) if w.isdigit() else 0, w)))


def porque(termos, cliente, candidatas: list[dict], sem_cliente: bool = False, vetadas=(), duvida=()) -> str:
    """O "por quê" do buraco sem sugestão (12/11/2026), no lugar do "sem par no cadastro", que não dizia o que fazer.
    `termos` = `casamento.termos` da chave; `candidatas` = as usinas que a chave poderia ser (as do cliente dela, ou
    todas); `sem_cliente`: o cliente da chave não está no cadastro; `vetadas` = [(usina, trava)]: as de nome contido e o
    mesmo número que uma trava tirou (a cidade ou a potência da base não batem com as do cadastro); `duvida` = os
    clientes do cadastro que começam como o da chave, quando são dois ou mais.
    Ordem: o cliente, a vetada (ela é a provável: "o cadastro tem a X 2, não a 1" estaria errado com a X 1 lá), o
    número, e o nada parecido."""
    def nome(u):
        return f"a {u['nome'] if cliente else u['titulo']}"
    if sem_cliente:
        return f"o cadastro não tem o cliente {cliente}: confira o nome do cliente ou crie no Registro mestre"
    if duvida:
        return (f"o cliente {cliente} começa como {' e '.join(sorted(duvida))} no cadastro: confira o nome do cliente "
                f"antes de ligar à mão")
    if vetadas:
        u, trava = vetadas[0]
        return f"o cadastro tem {nome(u)}, mas {trava} da base não bate com a do cadastro: confira antes de ligar à mão"
    outras = [u for u in candidatas if K.contencao(termos, u["nome"]) == K.OUTRO_NUMERO]
    if outras:
        tem = " e ".join(nome(u) for u in outras[:3])
        if not termos[1]:
            return f"o cadastro tem {tem}, com número, e a chave não diz qual: confira ou crie no Registro mestre"
        if not any(K.termos(u["nome"])[1] for u in outras):
            return f"o cadastro tem {tem}, sem número: confira se é a mesma usina antes de ligar à mão"
        return f"o cadastro tem {tem}, não a {_numero(termos[1])}: crie no Registro mestre"
    if cliente:
        return "o cadastro não tem usina parecida deste cliente: crie no Registro mestre"
    return "o cadastro não tem usina parecida: crie no Registro mestre"


def porque_sem_sugestao(item: dict, usinas: list[dict]) -> str:
    """O `porque` de uma chave das bases de sempre (a mesma leitura do nome, do cliente e das travas da `sugestoes`)."""
    nome, cliente = _nome_e_cliente(item)
    texto = _sem_cliente_e_uf(nome, cliente)
    termos = K.termos(texto)
    primeiro = K.primeiro_identificador(texto)
    cli = cliente if B.norm(cliente or "") else None
    validos, duvida = _clientes_da_chave(cli, usinas) if cli else (None, frozenset())
    do_cliente = [u for u in usinas if u.get("cliente") in validos] if cli else usinas
    vetadas = [(u, t) for u in do_cliente
               if K.contencao(termos, u["nome"]) in K.CONTIDAS and (t := _trava(item, u, primeiro))]
    return porque(termos, cli, do_cliente, sem_cliente=bool(cli) and not do_cliente and not duvida, vetadas=vetadas,
                  duvida=duvida)


def _por_nome(como: str) -> bool:
    return any(como.startswith(p) for p in POR_NOME)


def _indice_fama(usinas: list[dict], linhas_de_para: list) -> dict:
    """O índice da proposta da FAMA (`ligacao_fama.indice`) com as chaves do Fracttal já ligadas a cada usina."""
    fracttal = defaultdict(list)
    for uid, sistema, chave, _como in linhas_de_para:
        if sistema == FRACTTAL and uid is not None:
            fracttal[uid].append(str(chave))
    return ligacao_fama.indice(usinas, fracttal)


def sugestoes_de_100(buracos: list[dict], sistema: str) -> dict:
    """O que o botão "Ligar as sugestões de 100%" liga numa base (11/11/2026: a FAMA tinha 34 buracos com UMA sugestão de
    100%, e clicar 34 vezes era demais). Só liga o buraco com EXATAMENTE uma sugestão, de nota 100; a mesma usina como
    100% de duas chaves é ambíguo e as duas ficam para a pessoa. A tela conta o N e a rota liga por esta função só.
    Devolve {"ligar": [(chave, usina_id)], "pulos": {"varias": n, "abaixo": n, "sem": n, "repetida": n}}."""
    pulos = {"varias": 0, "abaixo": 0, "sem": 0, "repetida": 0}
    unicas = []
    for b in buracos:
        if b["sistema"] != sistema:
            continue
        sug = b.get("sugestoes") or []
        if not sug:
            pulos["sem"] += 1
        elif len(sug) > 1:
            pulos["varias"] += 1
        elif sug[0]["nota"] < 100:
            pulos["abaixo"] += 1
        else:
            unicas.append((b["chave"], sug[0]["id"]))
    por_usina = Counter(u for _, u in unicas)
    ligar = [(c, u) for c, u in unicas if por_usina[u] == 1]
    pulos["repetida"] = len(unicas) - len(ligar)
    return {"ligar": ligar, "pulos": pulos}


def sugestoes_de_100_todas(buracos: list[dict]) -> dict:
    """O que o botão geral "Ligar as N chaves com o nome no cadastro" liga (12/11/2026, Levi: "quando tiver mais de uma
    chave com nome no cadastro, tem que ter um botão de ligar usina com o cadastro"): a regra do `sugestoes_de_100`,
    base a base, somada. A mesma usina como 100% de chaves de bases DIFERENTES não é dúvida (a chave do Fracttal e o
    projeto da FAMA da mesma usina); de duas chaves da mesma base, é, e fica. A tela conta o N e a rota liga por esta
    função só. Devolve {"ligar": [(sistema, chave, usina_id)], "por_base": {sistema: pulos}}."""
    ligar, por_base = [], {}
    for sistema in sorted({b["sistema"] for b in buracos}):
        r = sugestoes_de_100(buracos, sistema)
        ligar += [(sistema, c, u) for c, u in r["ligar"]]
        por_base[sistema] = r["pulos"]
    return {"ligar": ligar, "por_base": por_base}


def _ja_ligada(sug: list[dict], ja_ligada: dict, sistema: str, chave: str, itens: dict) -> str | None:
    """A sugestão cuja usina já liga a OUTRA chave da mesma base cai abaixo de 100 (o lote não a liga: duas chaves de
    uma base na mesma usina é engano de uma delas, ou a mesma usina com dois nomes, e quem sabe é a pessoa) e o "por quê"
    diz qual. Muda as notas de `sug` no lugar; devolve o texto da 1ª, ou None."""
    texto = None
    for s in sug:
        outras = [(c, como) for c, como in ja_ligada.get((sistema, s["id"]), ()) if c != chave]
        if not outras:
            continue
        s["nota"] = min(s["nota"], K.TETO_COM_DUVIDA)
        if texto is None:
            c, como = outras[0]
            nome = itens.get((sistema, c), {}).get("rotulo") or c
            por = "por nome " if _por_nome(como) else ""
            texto = f"a {s['titulo']} já está ligada {por}a outra chave desta base ({nome}): confira antes de ligar"
    sug.sort(key=lambda x: -x["nota"])
    return texto


def panorama(srv, atual: dict | None, regras: dict) -> dict:
    """Os números por base e as quatro listas da tela."""
    usinas = _usinas(srv)
    por_id = {u["id"]: u for u in usinas}
    if not atual:
        return {"usinas": usinas, "sistemas": [], "buracos": [], "por_nome": [], "ausencias": {}, "decisoes": [],
                "gerado_em": None}
    itens = {(s, str(it["chave"])): it for s, its in atual["fontes"].items() for it in its}
    est = defaultdict(lambda: {"ligadas": set(), "buracos": set(), "ignoradas": set(), "usinas": set()})
    buracos, por_nome = [], []
    fama = {}                               # o índice da proposta da FAMA, montado uma vez (só se houver buraco dela)
    ja_ligada = defaultdict(list)           # (sistema, usina_id) -> [(chave, como)]: as chaves que já ligam a usina
    for uid, sistema, chave, como in atual["linhas"]:
        if uid is not None and not como.startswith("ignorado"):
            ja_ligada[(sistema, uid)].append((str(chave), como))
    for uid, sistema, chave, como in atual["linhas"]:
        e, chave = est[sistema], str(chave)
        if como.startswith("ignorado"):
            e["ignoradas"].add(chave)
        elif uid is None:
            e["buracos"].add(chave)
            it = itens.get((sistema, chave), {"chave": chave})
            if it.get("propor") == "fama":
                if not fama:
                    fama["idx"] = _indice_fama(usinas, atual["linhas"])
                sug = ligacao_fama.sugestoes(it, fama["idx"], por_id)
                razao = None if sug else porque(K.termos(ligacao_fama.nome_fama(it.get("nome"))), None, usinas)
            else:
                sug = sugestoes(it, usinas)
                razao = None if sug else porque_sem_sugestao(it, usinas)
            if razao and not (como.startswith(B.SEM_PAR) or como == B.A_DECIDIR):
                razao = None                # o motivo do de-para já é o porquê (conflito, desligado à mão, ...)
            if sug:                         # a usina já ligada a outra chave, e sem isso a ressalva da sugestão
                razao = (_ja_ligada(sug, ja_ligada, sistema, chave, itens)
                         or next((g["ressalva"] for g in sug if g.get("ressalva")), None))
            # `rotulo` e `os`: o que a seção mostra no lugar da chave quando ela é um id (o projeto da FAMA)
            buracos.append({"sistema": sistema, "chave": chave, "motivo": como, "porque": razao,
                            "tarefas": it.get("tarefas"), "nome": it.get("nome"), "cidade": it.get("cidade"),
                            "rotulo": it.get("rotulo"), "os": it.get("os"), "sugestoes": sug})
        else:
            e["ligadas"].add(chave)
            e["usinas"].add(uid)
            if _por_nome(como):
                por_nome.append({"sistema": sistema, "chave": chave, "usina_id": uid, "como": como,
                                 "usina": por_id.get(uid, {}).get("titulo", uid),
                                 "rotulo": itens.get((sistema, chave), {}).get("rotulo")})
    ausencias, n_aus = {}, {}
    for sistema, e in est.items():
        if sistema == "BD_Operações" or sistema in SEM_AUSENCIA:
            continue
        so, sem = SO_DO_CLIENTE.get(sistema), SEM_O_CLIENTE.get(sistema)
        esperadas = {(d.get("usina_id"), d.get("cliente_id")) for d in regras["ausencia"] if d.get("sistema") == sistema}
        fora = [u for u in usinas if u["status"] == "OPERAÇÃO" and u["id"] not in e["usinas"]
                and (not so or B.norm(u["cliente"]) == B.norm(so))
                and not (sem and B.norm(u["cliente"]) == B.norm(sem))
                and (u["id"], None) not in esperadas and (None, u["cliente_id"]) not in esperadas]
        grupos = defaultdict(list)
        for u in fora:
            grupos[(u["cliente"], u["cliente_id"])].append(u)
        ausencias[sistema] = sorted(grupos.items(), key=lambda kv: -len(kv[1]))
        n_aus[sistema] = len(fora)
    sistemas = []
    for sistema, e in sorted(est.items(), key=lambda kv: (kv[0] != "BD_Operações", kv[0])):
        total = len(e["ligadas"]) + len(e["buracos"])
        sistemas.append({"nome": sistema, "ligadas": len(e["ligadas"]), "total": total, "buracos": len(e["buracos"]),
                         "ignoradas": len(e["ignoradas"]), "fora": n_aus.get(sistema, 0),
                         "pct": round(100 * len(e["ligadas"]) / total, 1) if total else 100.0})
    decisoes = []
    for tipo in TIPOS:
        for d in regras[tipo]:
            if tipo == "ignorar" and not d.get("chave"):
                alvo = f"contém \"{d.get('contem')}\""
            elif tipo == "ausencia":
                alvo = (por_id.get(d.get("usina_id"), {}).get("titulo") if d.get("usina_id") is not None
                        else f"todas do cliente {next((u['cliente'] for u in usinas if u['cliente_id'] == d.get('cliente_id')), d.get('cliente_id'))}")
            else:                           # a chave que é um id (o projeto da FAMA) aparece pelo nome
                alvo = itens.get((d.get("sistema"), str(d.get("chave"))), {}).get("rotulo") or d.get("chave")
            decisoes.append({"tipo": tipo, "sistema": d.get("sistema") or "todas", "alvo": alvo,
                             "usina": por_id.get(d.get("usina_id"), {}).get("titulo") if tipo in ("ligar", "desligar") else "",
                             "motivo": d.get("motivo", ""), "quem": d.get("quem", ""), "quando": d.get("quando", ""),
                             "chave": d.get("chave") or d.get("contem"), "usina_id": d.get("usina_id"),
                             "cliente_id": d.get("cliente_id")})
    return {"usinas": usinas, "sistemas": sistemas, "buracos": buracos, "por_nome": por_nome, "ausencias": ausencias,
            "decisoes": decisoes, "gerado_em": atual.get("gerado_em")}
