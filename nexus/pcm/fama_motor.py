"""O adaptador do programador para as OS da FAMA (fase 2: pronto e DESLIGADO; 11/11/2026).

Levi, 11/11/2026: o cliente cria a OS na FAMA, ela vai para o programador automático e cai no App de Campo. Na fase 1 a
FAMA só aparece no Quadro (`fama_quadro.py`): pôr as OS dela no motor ocuparia as horas das equipes e mudaria a semana
oficial do Fracttal mesmo sem publicar. A fase 2, combinada depois com o App, liga por `NEXUS_FAMA_PROGRAMA=1`: a rodada
põe as OS da FAMA na programação e tira a preventiva do Fracttal das usinas da FAMA, porque nelas a preventiva passa a
ser a da FAMA (decisão do Levi). Sem a variável, o `geracao.py` nem chama este módulo: a rodada é a de hoje.

O motor é cópia idêntica do PCM e não se edita (`motor/README.md`): ele lê o Fracttal pelo `fonte_bd_api.df_semanal`,
que devolve o `.cache_semanal_api.pkl` da pasta da rodada enquanto o cache está dentro do TTL. É ali que as OS da FAMA
entram, no formato das linhas do Fracttal (`COLS_BD_SEMANAL` do `motor/gerar_bd_via_api.py`):
- na rodada com a FOTO (`gerar_com_foto`), o cache é a foto copiada;
- na rodada de verdade, o cache só existiria depois que o motor lesse o Fracttal: a rodada faz a MESMA leitura antes (o
  `df_semanal` do motor, num subprocesso com o ambiente do motor), põe as OS da FAMA e roda o motor com o TTL longo, para
  ele usar o cache que recebeu em vez de ler de novo.

A linha da FAMA (`linha_do_motor`): o "OSs ID" é um NÚMERO substituto (`substituto`: 9.000.000.000 + o id da FAMA),
porque o motor faz int() no "OSs ID" (`task_key`, a tarefa atômica) e "FAMA-101" derrubaria a rodada; depois do motor, a
planilha volta a dizer FAMA-101 (`depois_do_motor`). A usina é o nome que o motor usa (o do Fracttal pelo de-para,
como ele aparece nas tarefas da usina no cache), a equipe é a das tarefas do Fracttal da usina (sem tarefa, a do
cadastro, se for do padrão do PCM, "UF Região NN"), o tipo vai para corretiva ou preventiva, a "Data Programada" é a
previsão e a duração é a que o motor dá à tarefa sem informação (`DURACAO_PADRAO_H`; vazia, o motor de verdade quebra).
A tarefa é "OS da FAMA <id>": o título NÃO vai, porque o log do motor imprime o texto das tarefas e o título só se
decifra na tela.

"Usina da FAMA" é a que tem OS da FAMA ligada (qualquer situação); a preventiva do Fracttal que sai é a ainda por fazer
(nem finalizada nem cancelada); a feita fica, porque é histórico (o placar do mês e a recorrência do motor a contam).
"""
import ast
import hashlib
import os
import pickle
import subprocess
import sys
from collections import Counter
from pathlib import Path

from . import fama_os as F
from .semana import _norm

VARIAVEL = "NEXUS_FAMA_PROGRAMA"
CACHE = ".cache_semanal_api.pkl"
BASE = 9_000_000_000            # o "OSs ID" da FAMA no motor: longe de qualquer número de OS do Fracttal
TTL_MIN = "180"                 # o TTL do cache com as OS da FAMA na rodada de verdade (o padrão do motor é 10 min)
COLUNAS_DO_MOTOR = Path(__file__).resolve().parent / "motor" / "gerar_bd_via_api.py"
# o tipo da FAMA no motor. A roçada e a limpeza de módulos são Zeladoria, como no Fracttal (13/11/2026, Levi: "regra que
# tem em um tem que ter em outro"): o motor as põe em paralelo, fora das horas da equipe (`is_zeladoria`)
TIPO_NO_MOTOR = {"corrective": "Corretiva", "preventive/predictive": "Preventiva", "vegetation control": "Zeladoria",
                 "modules cleaning": "Zeladoria", "equipments and materials movement": "Preventiva"}
FECHADA = ("Finalizados", "Cancelado")             # o "Status" da OS no Fracttal que já não é trabalho
# A duração da OS da FAMA no motor: a que o próprio motor dá à tarefa sem informação (`_estimate_h_sem_fracttal`, o
# último recurso, 1,5 h). Vazia não dá: a preventiva sem sigla (MPx) e sem par na Lista de Prioridades fica com o
# `mttr_h_fallback` NaN (a coluna mistura número e None) e o `alloc_diurno` quebra (int(round(NaN))). Achado na prova de
# 11/11/2026 com o motor de verdade e a foto de mentira: a rodada inteira falhou.
DURACAO_PADRAO_H = 1.5
# o que o leitor do motor (`transformar_wo_para_bd`) grava numa linha sem o dado: data e duração vazias, "Não" nos
# sim/não, 0 no percentual e texto vazio no resto
_DATAS = ("Data Calculada", "Data Programada", "Data inicial", "Data final", "Data de Criação da OS",
          "Data de finalização da OS", "Data do Incidente")
_DURACOES = ("Tarefa -> Duração estimada", "Tempo de execução", "Tempo de inatividade planejado do ativo", "Total de Horas")
_NAO = ("Fora de serviço", "Parou o equipamento?")
# a leitura do Fracttal da rodada de verdade, a mesma que o motor faria no começo dele
PRE_LEITURA = ("import sys; sys.path.insert(0, sys.argv[1]); import fonte_bd_api; fonte_bd_api.df_semanal(); "
               "print('[FAMA] o Fracttal foi lido antes do motor (a mesma leitura dele)', flush=True)")


class FamaErro(RuntimeError):
    """A rodada com a FAMA ligada não sai sem as OS da FAMA. Nunca traz título nem nome de pessoa."""


def ligado(config) -> bool:
    """A FAMA está no programador nesta máquina (`NEXUS_FAMA_PROGRAMA=1`)? Desde 13/11/2026 o `config.carregar_config`
    a liga por padrão onde a FAMA é lida (a NEXUS_FAMA_CHAVE está na máquina); "0" desliga."""
    return str(config.get(VARIAVEL) or "").strip() == "1"


def colunas_do_motor() -> list[str]:
    """As `COLS_BD_SEMANAL` do leitor do motor, lidas do arquivo (importá-lo leria o .env e mexeria no terminal)."""
    arvore = ast.parse(COLUNAS_DO_MOTOR.read_text(encoding="utf-8"))
    for no in arvore.body:
        if isinstance(no, ast.Assign) and any(getattr(t, "id", "") == "COLS_BD_SEMANAL" for t in no.targets):
            return list(ast.literal_eval(no.value))
    raise FamaErro("o leitor do motor não tem as COLS_BD_SEMANAL")


def substituto(fama_os_id) -> str | None:
    """O "OSs ID" da OS da FAMA no motor (texto, como o "OSs ID" que vem da API do Fracttal)."""
    i = F.inteiro(fama_os_id)
    return str(BASE + i) if i is not None and i < BASE else None


def fama_do_substituto(v) -> int | None:
    """O id da FAMA de um "OSs ID" substituto (número, texto ou o float da planilha); None para as OS do Fracttal."""
    try:
        i = int(float(str(v).strip()))
    except (TypeError, ValueError, OverflowError):
        return None
    return i - BASE if i > BASE else None


# A sigla da preventiva pela periodicidade que o título diz (13/11/2026, Levi: "regra que tem em um tem que ter em
# outro"): o motor decide a preventiva vencida pela sigla na tarefa (`_fila_elegivel`: MPS e MPA voltam sempre; MPM, MPW,
# MPQ e MPT só no mês da semana; sem sigla, não voltam) e a ordena por ela (MPA > MPS > MPT > MPM > MPQ). Os nomes são
# os do motor (`SIGLAS_MULTI`: MPM mensal, MPW semanal, MPT trimestral, MPS semestral, MPA anual, MPB bianual, MPQ
# quinzenal). A ordem conta: "bianual" antes de "anual". Medido em 13/11 nas 91 preventivas abertas da FAMA: 60 dizem
# "mensal", 18 "anual" e 13 nada.
SIGLA_DA_PERIODICIDADE = (("MPB", r"\bbianua(l|is)\b|\bbienal\b"), ("MPA", r"\banua(l|is)\b|\bannual\b"),
                          ("MPS", r"\bsemestra(l|is)\b"), ("MPT", r"\btrimestra(l|is)\b"),
                          ("MPQ", r"\bquinzena(l|is)\b"), ("MPM", r"\bmensa(l|is)\b|\bmonthly\b"),
                          ("MPW", r"\bsemana(l|is)\b|\bweekly\b"))


def sigla(linha: dict) -> str:
    """A sigla da preventiva da FAMA pelo título (vazia para a corretiva e para o título que não diz a periodicidade).
    Só a sigla sai daqui: o título nunca vai ao motor (o log dele imprime o texto das tarefas)."""
    import re
    if not _norm(linha.get("tipo")).startswith("preventive"):
        return ""
    t = str(linha.get("titulo") or "").lower()
    return next((s for s, rx in SIGLA_DA_PERIODICIDADE if re.search(rx, t)), "")


def tarefa(fama_os_id, sigla_: str = "") -> str:
    return f"OS da FAMA {F.inteiro(fama_os_id)}" + (f" · {sigla_}" if sigla_ else "")


def _vazio(coluna: str):
    if coluna in _DATAS or coluna in _DURACOES:
        return None
    if coluna in _NAO:
        return "Não"
    return 0 if coluna == "% Concluída" else ""


def _quando(d):
    import pandas as pd
    return pd.Timestamp(d) if d else None


def linha_do_motor(linha: dict, nome: str, equipe: str, colunas: list[str]) -> dict:
    """A OS da FAMA (aberta ou em andamento) como uma linha do leitor do motor, com todas as `colunas`."""
    r = {c: _vazio(c) for c in colunas}
    r.update({"OSs ID": substituto(linha.get("fama_os_id")), "Status": "Em processo", "Código": "", "Ativo": nome,
              "Tarefa": tarefa(linha.get("fama_os_id"), sigla(linha)), "Ativo Classificação 1": nome,
              "Ativo Classificação 2": equipe,
              "Estado da Tarefa": F.ESTADO_DA_TAREFA[_norm(linha.get("status"))],
              "Tipo de tarefa": TIPO_NO_MOTOR[_norm(linha.get("tipo"))],
              "Data Programada": _quando(F.data_de(linha.get("data_id_prevista"))),
              "Data de Criação da OS": _quando(F.data_de(linha.get("data_id_criacao"))),
              "Tarefa -> Duração estimada": _horas(DURACAO_PADRAO_H)})
    return r


def _horas(h: float):
    import pandas as pd
    return pd.Timedelta(hours=h)


def _moda(valores) -> str:
    c = Counter(v for v in (str(x).strip() for x in valores if x is not None) if v and v.lower() != "nan")
    return c.most_common(1)[0][0] if c else ""


def aplicar(df, linhas: list[dict], cadastro: dict):
    """(o cache novo, o relatório): tira a preventiva por fazer do Fracttal das usinas da FAMA e põe as OS da FAMA abertas
    e em andamento. Aplicar de novo no mesmo cache não duplica (as linhas da FAMA que já estavam saem antes)."""
    import pandas as pd
    faltam = [c for c in colunas_do_motor() if c not in df.columns]
    if faltam:
        raise FamaErro(f"o cache da rodada não tem as colunas do motor ({', '.join(faltam[:3])}…)")
    cols = list(df.columns)
    rel = {"os_fama": 0, "preventivas_tiradas": 0, "usinas": 0, "sem_usina": 0, "sem_previsao": 0,
           "sem_nome_no_fracttal": 0, "sem_equipe": 0, "tipo_desconhecido": 0, "numero_invalido": 0}
    df = df[~df["OSs ID"].map(lambda v: fama_do_substituto(v) is not None)]
    ativo = df["Ativo Classificação 1"].map(_norm)
    usinas = sorted({uid for uid in (F.inteiro(l.get("usina_id")) for l in linhas) if uid in cadastro})
    rel["usinas"] = len(usinas)
    nomes = {uid: {_norm(n) for n in cadastro[uid].get("nomes") or [] if _norm(n)} for uid in usinas}
    da_fama = set().union(*nomes.values()) if nomes else set()
    tirar = (ativo.isin(da_fama) & df["Tipo de tarefa"].map(lambda t: _norm(t).startswith("preventiva"))
             & ~df["Status"].isin(FECHADA) & (df["Estado da Tarefa"] != "Finalizados"))
    rel["preventivas_tiradas"] = int(tirar.sum())
    # o nome e a equipe de cada usina como o motor os vê: os das tarefas do Fracttal dela no cache
    usina = {}
    for uid in usinas:
        daqui = df[ativo.isin(nomes[uid])]
        nome = _moda(daqui["Ativo Classificação 1"]) or (cadastro[uid].get("nomes") or [""])[0]
        # sem tarefa do Fracttal, a equipe do cadastro, com qualquer nome (13/11/2026): até ali só valia a do padrão do PCM
        # ("UF Região NN"), e na simulação da W47 208 das 264 OS da FAMA ficaram fora por "sem equipe", porque as usinas
        # da Faro têm equipes locais no cadastro ("Cabo Branco 2 e 3"). A equipe local é uma equipe como as outras: o
        # motor dá a ela os mesmos 70% de 8,8 h por dia (Levi: "regra que tem em um tem que ter em outro")
        eq = str(cadastro[uid].get("equipe") or "").strip()
        usina[uid] = (nome, _moda(daqui["Ativo Classificação 2"]) or eq)
    novas = []
    for l in linhas:
        if F.situacao(l.get("status")) is None:
            continue
        uid = F.inteiro(l.get("usina_id"))
        motivo = ("sem_usina" if uid not in usina else "sem_previsao" if F.data_de(l.get("data_id_prevista")) is None
                  else "tipo_desconhecido" if _norm(l.get("tipo")) not in TIPO_NO_MOTOR
                  else "numero_invalido" if substituto(l.get("fama_os_id")) is None
                  else "sem_nome_no_fracttal" if not usina[uid][0] else "sem_equipe" if not usina[uid][1] else "")
        if motivo:
            rel[motivo] += 1
            continue
        novas.append(linha_do_motor(l, usina[uid][0], usina[uid][1], cols))
    rel["os_fama"] = len(novas)
    nov = pd.DataFrame(novas, columns=cols)
    for c in cols:                           # a mesma forma das colunas do cache (data segue data; duração, duração)
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            nov[c] = pd.to_datetime(nov[c], errors="coerce").astype(df[c].dtype)
        elif pd.api.types.is_timedelta64_dtype(df[c]):
            nov[c] = pd.to_timedelta(nov[c], errors="coerce").astype(df[c].dtype)
    out = pd.concat([df[~tirar], nov], ignore_index=True) if novas else df[~tirar].reset_index(drop=True)
    return out, rel


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:12]


def aplicar_no_cache(pasta: Path, linhas: list[dict], cadastro: dict) -> dict:
    """O `aplicar` no `.cache_semanal_api.pkl` da rodada, regravado com a mesma idade (o TTL do motor é pela idade do
    arquivo, e a foto guarda a dela). Devolve o relatório, com o sha do cache que o motor recebe."""
    cache = Path(pasta) / CACHE
    try:
        with open(cache, "rb") as f:
            d = pickle.load(f)
    except (OSError, pickle.UnpicklingError, EOFError) as ex:
        raise FamaErro(f"o {CACHE} da rodada não abriu ({type(ex).__name__})") from ex
    if not isinstance(d, dict) or d.get("v") != 1 or "df" not in d:
        raise FamaErro(f"o {CACHE} da rodada não tem a forma que o motor lê")
    df, rel = aplicar(d["df"], linhas, cadastro)
    idade = cache.stat()
    tmp = cache.with_name(cache.name + ".tmp")
    with open(tmp, "wb") as f:
        pickle.dump(dict(d, df=df), f)
    os.replace(tmp, cache)
    os.utime(cache, ns=(idade.st_atime_ns, idade.st_mtime_ns))
    rel["cache_sha"] = _sha(cache)
    return rel


def entrada(config, ler_o_fracttal: bool) -> dict | None:
    """As OS da FAMA e o cadastro das usinas para a rodada, lidos agora (no pedido de gerar, antes da rodada começar).

    O portão é o FRESCOR do livro, não a contagem (revisão de 11/11/2026): a leitura da FAMA parada (o batimento da carga
    com mais de `fama_os.FRESCOR_H`, ou nenhum) = a FAMA fica fora da rodada (`geracao._fama`: desde 13/11/2026 a rodada
    sai a de sempre, com o motivo; antes ela não saía), porque tirar a preventiva do Fracttal e pôr OS
    da FAMA que já podem ter andado lá seria pior que a semana de sempre; o livro fresco e sem OS (a FAMA não tem nada para
    a Grid) = None, a semana de sempre."""
    try:
        lido = F._linhas_fama(config)
    except Exception as ex:      # noqa: BLE001 — o nome do erro, nunca a mensagem (pode trazer endereço)
        raise FamaErro(f"não consegui ler as OS da FAMA ({type(ex).__name__})") from ex
    if F.velho(lido.gerado_em):
        quando = F.quando(lido.gerado_em)
        raise FamaErro(f"a leitura da FAMA parou ({f'a última é de {quando}' if quando else 'nenhuma leitura no livro'}): "
                       f"a FAMA fica fora desta rodada")
    if not lido.linhas:
        return None
    try:
        cadastro = F.cadastro_das_usinas(config)
    except Exception as ex:      # noqa: BLE001
        raise FamaErro(f"não consegui ler o cadastro das usinas ({type(ex).__name__})") from ex
    return {"linhas": lido.linhas, "cadastro": cadastro, "ler_o_fracttal": ler_o_fracttal}


def antes_do_motor(pasta: Path, st: dict, env: dict, motor: Path, fama: dict, log, timeout: int) -> dict:
    """Na rodada, antes do motor: a leitura do Fracttal (só na de verdade; na da foto o cache é a foto), as OS da FAMA no
    cache e a linha do resumo no log (só contagens). Devolve o ambiente do motor (na de verdade, com o TTL longo)."""
    pasta = Path(pasta)
    if fama["ler_o_fracttal"]:
        log.write("[FAMA] lendo o Fracttal antes do motor, para pôr as OS da FAMA na semana\n".encode("utf-8"))
        log.flush()
        try:
            r = subprocess.run([sys.executable, "-c", PRE_LEITURA, str(Path(motor).parent)], cwd=str(pasta), env=env,
                               stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        except subprocess.TimeoutExpired as ex:
            raise FamaErro(f"a leitura do Fracttal antes do motor passou de {timeout // 60} min") from ex
        if r.returncode != 0 or not (pasta / CACHE).is_file():
            raise FamaErro(f"a leitura do Fracttal antes do motor falhou (código {r.returncode})")
        env = dict(env, PROG_API_TTL_MIN=TTL_MIN)
    st["fama"] = aplicar_no_cache(pasta, fama["linhas"], fama["cadastro"])
    x = st["fama"]
    log.write((f"[FAMA] {x['os_fama']} OS da FAMA entraram na semana; {x['preventivas_tiradas']} preventivas do Fracttal "
               f"saíram de {x['usinas']} usinas da FAMA; ficaram de fora: {x['sem_usina']} sem usina, {x['sem_previsao']} "
               f"sem previsão, {x['sem_nome_no_fracttal']} sem nome no Fracttal, {x['sem_equipe']} sem equipe, "
               f"{x['tipo_desconhecido']} de tipo desconhecido\n").encode("utf-8"))
    log.flush()
    return env


def depois_do_motor(planilha: Path) -> dict:
    """Na planilha que o motor gerou, o "OSs ID" substituto volta a ser FAMA-<id>, em toda aba com a coluna (as das
    equipes e a _Pendentes). Sem nenhum a trocar, a planilha nem é regravada."""
    import openpyxl
    wb = openpyxl.load_workbook(planilha)
    n = 0
    for ws in wb.worksheets:
        if ws.max_row < 2:
            continue
        cab = [c.value for c in ws[1]]
        if "OSs ID" not in cab:
            continue
        col = cab.index("OSs ID") + 1
        for lin in range(2, ws.max_row + 1):
            c = ws.cell(row=lin, column=col)
            fid = fama_do_substituto(c.value) if c.value not in (None, "") else None
            if fid is not None:
                c.value = F.numero(fid)
                n += 1
    if n:
        wb.save(planilha)
    wb.close()
    return {"linhas": n}
