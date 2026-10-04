"""Etapa 2: gerar a semana no Nexus, em SOMBRA.

O motor é o do PCM (programacao_v7.py e os dois leitores do Fracttal), copiado sem mudança em motor/. O Nexus:
1. confere o que o motor precisa: credencial, insumos e o próprio motor;
2. monta uma pasta por rodada, FORA do OneDrive, e escreve nela os insumos que moram no Nexus (insumos.py:
   prioridades, confiabilidade, histórico, feriados e observações), no formato que o motor lê, e a AUXILIAR, que sai
   do cadastro do Nexus (auxiliar.py). Da pasta do PCM só vêm as durações aprendidas. Na sombra, o Nexus importa os arquivos do Fabrício antes, para as duas
   gerações partirem do mesmo ponto;
3. volta o histórico para antes da semana: na 2ª geração o motor marcava tudo como reprogramado (415 tarefas na
   semana 40), e assim tanto faz rodar antes ou depois do Fabrício;
4. roda o motor num SUBPROCESSO, com ambiente próprio. O FRACTTAL_BASE_URL do motor tem /api/ e o do OS Creator, que
   roda dentro do Nexus, não; no mesmo processo um quebraria o outro. As variáveis NEXUS_* não vão para o motor;
5. compara a planilha que saiu com a oficial da mesma semana, se ela já existir.
Nada é publicado: a semana do campo continua sendo a do Fabrício.

Credencial (decisão do Levi, 30/09: "pode usar do OS Creator, mesma lógica porém sem a parte de login"): o
client_credentials do Fracttal que o OS Creator lê do .env da pasta dele. A leitura pela API não precisa do login de
pessoa (o RPC); o motor do PCM usa o mesmo método.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import openpyxl
from dotenv import dotenv_values

from . import auxiliar as A
from . import comparar
from . import insumos as I

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
MOTOR = AQUI / "motor" / "programacao_v7.py"
ENV_OS_CREATOR = RAIZ / "nexus" / "torres" / "oscreator" / "os_creator" / ".env"
# Fora do OneDrive e fora do AppData, como o ensaio do cadastro (o Claude desktop virtualiza o AppData).
TRABALHO_PADRAO = Path(r"C:\GridcoAuto\nexus\pcm") if os.name == "nt" else RAIZ / "dados" / "pcm"
# A pasta do PCM sincronizada nesta máquina: é de lá que o Fabrício gera. Na sombra, os insumos vêm dela.
ORIGEM_PADRAO = (Path.home() / "OneDrive - GRID CO" / "Área de Trabalho" / "Grid Co_ - 4. O&M" / "11.Pré-Operação"
                 / "6. PCM" / "09. Programação Semanal")
# O que ainda vem da pasta do PCM. Prioridades, Confiabilidade, Histórico, Feriados e Observações moram no Nexus
# desde 30/09/2026 (insumos.py) e são escritos na rodada a partir de lá. A AUXILIAR sai do cadastro desde 02/10.
INSUMOS = (  # (arquivo, obrigatório)
    ("duracoes_aprendidas.json", False),      # modo sombra no motor: só preenche uma coluna
)
URL_API = "https://app.fracttal.com/api/"
# 1 pedido por segundo. Fora do GitHub o motor anda a 0,15 s, rápido demais para os 200/min que robôs e App de Campo
# dividem na EMPRESA inteira desde 24/09.
INTERVALO_S = "1.0"
TEMPO_MAX_S = 60 * 60
SEMANA_RE = re.compile(r"^\d{4}-W\d{2}$")
RODADA_RE = re.compile(r"^\d{8}-\d{6}-\d{4}-W\d{2}$")
_BRT = timezone(timedelta(hours=-3))

_trava = threading.Lock()
_rodando: dict[str, tuple[str, threading.Thread]] = {}


class Ocupado(RuntimeError):
    pass


class NaoPronto(RuntimeError):
    pass


@dataclass
class Credencial:
    ok: bool
    onde: str
    client_id: str = field(default="", repr=False)
    client_secret: str = field(default="", repr=False)


def _cfg(config, chave, padrao=None):
    return config.get(chave) or os.environ.get(chave) or padrao


def pasta_trabalho(config) -> Path:
    return Path(_cfg(config, "NEXUS_PCM_TRABALHO", TRABALHO_PADRAO))


def pasta_origem(config) -> Path | None:
    if config.get("TESTING") and not config.get("NEXUS_PCM_ORIGEM"):
        return None
    return Path(_cfg(config, "NEXUS_PCM_ORIGEM", ORIGEM_PADRAO))


def caminho_motor(config) -> Path:
    return Path(_cfg(config, "NEXUS_PCM_MOTOR", MOTOR))


def credencial(config) -> Credencial:
    """Onde está o client_credentials do Fracttal, sem nunca expor o valor. Ordem: ambiente do processo (servidor),
    .env do Nexus, .env do OS Creator dentro do Nexus, e um .env apontado por NEXUS_FRACTTAL_ENV."""
    if config.get("TESTING"):
        fontes = [("teste", config.get("NEXUS_PCM_FRACTTAL_TESTE") or {})]
    else:
        fontes = [("ambiente", os.environ), ("o .env do Nexus", dotenv_values(RAIZ / ".env"))]
        if ENV_OS_CREATOR.exists():
            fontes.append(("o .env do OS Creator", dotenv_values(ENV_OS_CREATOR)))
        extra = _cfg(config, "NEXUS_FRACTTAL_ENV")
        if extra and Path(extra).exists():
            fontes.append((f"o .env de {Path(extra).parent.name}", dotenv_values(extra)))
    for onde, vals in fontes:
        cid = (vals.get("FRACTTAL_CLIENT_ID") or "").strip()
        seg = (vals.get("FRACTTAL_CLIENT_SECRET") or "").strip()
        if cid and seg:
            return Credencial(True, onde, cid, seg)
    return Credencial(False, "")


def horario_de_campo(agora: datetime | None = None) -> bool:
    """Seg a sex, das 06h às 18h: o motor lê o Fracttal inteiro e divide a cota com o App de Campo."""
    a = (agora or datetime.now(_BRT)).astimezone(_BRT)
    return a.weekday() < 5 and 6 <= a.hour < 18


def semana_padrao(hoje: date | None = None) -> str:
    """A da próxima segunda-feira, como o motor faz sem --semana."""
    h = hoje or datetime.now(_BRT).date()
    seg = h + timedelta(days=(7 - h.weekday()) or 7)
    iso = seg.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def _quando(ts: float) -> str:
    return datetime.fromtimestamp(ts, _BRT).strftime("%d/%m %H:%M")


def conferir(config, semana: str | None = None) -> dict:
    itens = []
    m = caminho_motor(config)
    itens.append({"nome": "Motor do PCM", "ok": m.exists(), "obrigatorio": True,
                  "detalhe": "cópia idêntica do programacao_v7.py em nexus/pcm/motor" if m.exists() else "motor não encontrado"})
    c = credencial(config)
    itens.append({"nome": "Credencial do Fracttal", "ok": c.ok, "obrigatorio": True,
                  "detalhe": f"encontrada em {c.onde}" if c.ok else
                  "falta: copie o .env do OS Creator para nexus/torres/oscreator/os_creator/.env"})
    origem = pasta_origem(config)
    tem_origem = bool(origem and origem.is_dir())
    itens.append({"nome": "Pasta do PCM", "ok": tem_origem, "obrigatorio": True,
                  "detalhe": "a mesma de onde o Fabrício gera" if tem_origem else "pasta não encontrada"})
    for nome, obrig in INSUMOS:
        p = origem / nome if origem else None
        existe = bool(p and p.exists())
        itens.append({"nome": nome, "ok": existe or not obrig, "obrigatorio": obrig,
                      "detalhe": ("na pasta do PCM, atualizado em " + _quando(p.stat().st_mtime)) if existe else
                      ("falta" if obrig else "opcional, ausente")})
    itens.append(A.estado(config))
    itens += I.estado(pasta_trabalho(config), origem if tem_origem else None, semana or semana_padrao())
    return {"pronto": all(i["ok"] for i in itens), "itens": itens}


def preparar_historico(src, dst, semana: str) -> None:
    """O histórico como era ANTES da semana: tira a semana de cada tarefa e refaz a contagem."""
    wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    cab = list(next(it))
    ix = {c: i for i, c in enumerate(cab)}
    novas = []
    for r in it:
        if not r or not r[ix["task_key"]]:
            continue
        r = list(r)
        semanas = sorted(s for s in str(r[ix["weeks"]] or "").split(",") if s.strip() and s.strip() != semana)
        if not semanas:
            continue
        r[ix["weeks"]] = ",".join(semanas)
        r[ix["count"]] = len(semanas)
        r[ix["first_week"]] = semanas[0]
        r[ix["last_week"]] = semanas[-1]
        novas.append(r)
    wb.close()
    out = openpyxl.Workbook()
    wo = out.active
    wo.append(cab)
    for r in novas:
        wo.append(r)
    out.save(dst)


def _ambiente(cred: Credencial, pasta: Path, saida: Path) -> dict:
    fora = ("PCM_PROG_DIR", "PCM_OUTPUT", "PCM_WEEK_FORCE")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("NEXUS_", "FRACTTAL_")) and k not in fora}
    env.update({"FRACTTAL_CLIENT_ID": cred.client_id, "FRACTTAL_CLIENT_SECRET": cred.client_secret,
                "FRACTTAL_BASE_URL": URL_API, "FRACTTAL_INTERVALO_S": INTERVALO_S,
                "PCM_PROG_DIR": str(pasta), "PCM_OUTPUT": str(saida),
                "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    # No Linux o TZ põe o motor no horário de Brasília. No Windows o C runtime não entende "America/Sao_Paulo" e o
    # relógio do motor saía 4 h adiantado (S41 de teste, 02/10/2026: rodou às 17:28 e o log dizia 21:28): depois das
    # 20h o "hoje" do motor viraria o dia seguinte e a idade das tarefas andaria um dia. Lá o relógio do PC já é BRT.
    if os.name != "nt":
        env["TZ"] = "America/Sao_Paulo"
    else:
        env.pop("TZ", None)
    return env


def _gravar(pasta: Path, st: dict) -> None:
    tmp = pasta / "status.json.tmp"
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(pasta / "status.json")


def _oficial(origem: Path | None, semana: str) -> Path | None:
    if not origem:
        return None
    p = origem / f"Programação Semana {int(semana.split('W')[1]):02d}.xlsx"
    return p if p.exists() else None


def iniciar(config, semana: str) -> dict:
    if not SEMANA_RE.match(semana or ""):
        raise ValueError("semana inválida")
    conf = conferir(config, semana)
    if not conf["pronto"]:
        raise NaoPronto("falta: " + ", ".join(i["nome"] for i in conf["itens"] if not i["ok"]))
    trabalho = pasta_trabalho(config)
    chave = str(trabalho.resolve())
    with _trava:
        ativo = _rodando.get(chave)
        if ativo and ativo[1].is_alive():
            raise Ocupado(ativo[0])
        rid = datetime.now(_BRT).strftime("%Y%m%d-%H%M%S") + "-" + semana
        pasta = trabalho / "geracoes" / rid
        (pasta / "saida").mkdir(parents=True, exist_ok=False)
        origem = pasta_origem(config)
        insumos = []
        for nome, _obrig in INSUMOS:
            p = origem / nome
            if not p.exists():
                continue
            shutil.copy2(p, pasta / nome)
            insumos.append({"nome": nome, "sha": _sha(p), "atualizado": _quando(p.stat().st_mtime),
                            "detalhe": "da pasta do PCM"})
        # os outros saem do Nexus, no formato que o motor lê; o histórico ainda volta para antes da semana
        try:
            aux = A.escrever(A.servico(config), pasta / A.NOME)
            insumos.append({"nome": "Cadastro de usinas (AUXILIAR)", "sha": _sha(pasta / A.NOME),
                            "atualizado": datetime.now(_BRT).isoformat(timespec="minutes"),
                            "detalhe": f"do cadastro do Nexus: {aux['usinas']} usinas, "
                                       f"{aux['sem_responsavel']} sem responsável O&M"})
            insumos += I.materializar(trabalho, pasta, semana)
        except A.SemCadastro as ex:
            shutil.rmtree(pasta, ignore_errors=True)
            raise NaoPronto(f"cadastro de usinas: {ex}") from ex
        except I.InsumoErro as ex:
            shutil.rmtree(pasta, ignore_errors=True)
            raise NaoPronto(str(ex)) from ex
        preparar_historico(pasta / "historico_do_nexus.xlsx", pasta / "Historico_Programacoes.xlsx", semana)
        cred = credencial(config)
        st = {"id": rid, "semana": semana, "estado": "rodando", "inicio": datetime.now(_BRT).isoformat(timespec="seconds"),
              "credencial": cred.onde, "insumos": insumos, "motor": str(caminho_motor(config))}
        _gravar(pasta, st)
        saida = pasta / "saida" / "sombra.xlsx"
        t = threading.Thread(target=_executar, name=f"pcm-{rid}", daemon=True,
                             args=(pasta, st, _ambiente(cred, pasta, saida), caminho_motor(config), origem, saida))
        _rodando[chave] = (rid, t)
        t.start()
    return st


def _executar(pasta: Path, st: dict, env: dict, motor: Path, origem: Path, saida: Path) -> None:
    t0 = time.monotonic()
    log = pasta / "log_motor.txt"
    try:
        with open(log, "wb") as f:
            r = subprocess.run([sys.executable, str(motor), "--semana", st["semana"]], cwd=str(pasta), env=env,
                               stdout=f, stderr=subprocess.STDOUT, timeout=TEMPO_MAX_S)
        st["codigo"] = r.returncode
        if r.returncode == 0 and saida.exists():
            st["estado"] = "ok"
            st["resumo"] = comparar.resumo(saida)
            oficial = _oficial(origem, st["semana"])
            if oficial:
                shutil.copy2(oficial, pasta / "oficial.xlsx")
                st["oficial"] = {"arquivo": oficial.name, "atualizado": _quando(oficial.stat().st_mtime)}
                st["comparacao"] = comparar.comparar(pasta / "oficial.xlsx", saida)
        else:
            st["estado"] = "falhou"
            st["erro"] = _cauda(log, 12) or f"o motor terminou com código {r.returncode} sem planilha"
    except subprocess.TimeoutExpired:
        st["estado"] = "falhou"
        st["erro"] = f"o motor passou de {TEMPO_MAX_S // 60} min e foi parado"
    except Exception as ex:      # noqa: BLE001 — qualquer falha fica no status, nunca derruba o Nexus
        st["estado"] = "falhou"
        st["erro"] = f"{type(ex).__name__}: {str(ex)[:300]}"
    st["fim"] = datetime.now(_BRT).isoformat(timespec="seconds")
    st["duracao_s"] = int(time.monotonic() - t0)
    _gravar(pasta, st)


def _cauda(p: Path, n: int) -> str:
    try:
        linhas = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(linhas[-n:]).strip()


def _pasta_rodada(config, rid: str) -> Path | None:
    if not RODADA_RE.match(rid or ""):
        return None
    p = pasta_trabalho(config) / "geracoes" / rid
    return p if (p / "status.json").exists() else None


def ler_status(config, rid: str) -> dict | None:
    p = _pasta_rodada(config, rid)
    if not p:
        return None
    try:
        return json.loads((p / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def log(config, rid: str, ultimas: int | None = None) -> str:
    p = _pasta_rodada(config, rid)
    if not p:
        return ""
    if ultimas:
        return _cauda(p / "log_motor.txt", ultimas)
    try:
        return (p / "log_motor.txt").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def ativa(config, rid: str) -> bool:
    """A rodada está de fato rodando neste processo? Um status "rodando" de um Nexus que reiniciou no meio não está."""
    ativo = _rodando.get(str(pasta_trabalho(config).resolve()))
    return bool(ativo and ativo[0] == rid and ativo[1].is_alive())


def aguardar(config, rid: str, timeout: float) -> dict | None:
    ativo = _rodando.get(str(pasta_trabalho(config).resolve()))
    if ativo and ativo[0] == rid:
        ativo[1].join(timeout)
    return ler_status(config, rid)


def ultimas(config, n: int = 8) -> list[dict]:
    base = pasta_trabalho(config) / "geracoes"
    if not base.is_dir():
        return []
    out = []
    for p in sorted((x for x in base.iterdir() if RODADA_RE.match(x.name)), reverse=True)[:n]:
        st = ler_status(config, p.name)
        if st:
            out.append(st)
    return out
