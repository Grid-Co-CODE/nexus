"""Gerar a semana no PC (27/11/2026): o motor do PCM roda no computador de uma pessoa do PCM, e a planilha volta ao Nexus.

O caso: a geração da W49 morreu quatro vezes (26/11 às 17:34, 17:58 e 18:26; 27/11 às 08:45), sempre na leitura das 48 mil
OS, e nenhuma na hora de um deploy. O motor roda dentro do teto de memória do serviço do Nexus (3 GB, com o Nexus em
2,5 GB), e quando a soma passa, o Linux derruba o serviço inteiro ("O Nexus reiniciou enquanto o motor rodava"). Levi,
27/11/2026: "a gente ter a possibilidade de rodar a programação semanal no computador separado [...] roda a programação
semanal no computador dela e aí salva no Nexus"; "tem que ser algo bem feito"; e as OS da FAMA juntas.

Como é:
- **O computador ligado** (`ligar`): quem programa (PCM ou administrador) cria um código pessoal na tela Gerar a semana e o
  cola UMA vez no aplicativo "Nexus PCM" (`ferramentas/nexus_pcm_app`). O código leva o endereço do Nexus e uma chave
  aleatória; o Nexus guarda só o hash da chave (`computadores_pcm.json` na pasta de trabalho do PCM, configuração de acesso
  desta instalação, como os administradores de Base → Acessos) e pode desligá-la a qualquer hora.
- **A rodada no PC** (`abrir_rodada`): a MESMA preparação da rodada do servidor (`geracao._preparar`: prioridades,
  confiabilidade, feriados, observações, histórico do banco, cadastro, fora da programação) e as OS da FAMA lidas do banco
  agora (`geracao._fama`); o estado é "no_pc" (nunca "interrompida": quem roda é o PC). O pacote (`pacote`) leva esses
  arquivos, o motor do Nexus e o adaptador da FAMA (`fama_motor.py`, `fama_base.py`, `semana.py`: o MESMO código do
  servidor), e a FAMA reduzida ao que o motor usa: o título não vai, só a sigla da preventiva que ele diz (`fama_motor.sigla`
  lê o título; com a sigla no lugar, dá a mesma sigla).
- **As chaves do Fracttal** (`credencial`): o aplicativo as pede ao Nexus a cada rodada, pela conexão com a chave do
  computador, e as guarda só na memória. Nunca vão no pacote nem ficam no disco do PC.
- **A volta** (`entregar`): a planilha e o log voltam pela mesma chave, e o Nexus termina a rodada pelo MESMO
  `geracao.concluir` do servidor (a FAMA de volta a FAMA-<id>, o "sem:", o resumo, a conferência e a comparação); dali em
  diante é uma rodada como as outras (Publicar no App).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import secrets
import threading
import zipfile
from datetime import datetime
from pathlib import Path

from . import fama_motor as FM
from . import geracao as G

ARQUIVO = "computadores_pcm.json"
PREFIXO = "NXPCM1."
NO_PC = "no_pc"
_trava = threading.Lock()
PLANILHA_MAX = 40 * 1024 * 1024        # a planilha da semana tem ~1-2 MB; o teto só barra o envio absurdo
LOG_MAX = 8 * 1024 * 1024
AQUI = Path(__file__).resolve().parent
# o que vai do Nexus no pacote, além do motor: o adaptador da FAMA e o que ele importa (sem banco nem cadastro)
MODULOS_DA_FAMA = ("fama_motor.py", "fama_base.py", "semana.py")
# os campos da OS da FAMA que o adaptador do motor usa (`fama_motor.aplicar` e `linha_do_motor`)
CAMPOS_DA_FAMA = ("fama_os_id", "status", "tipo", "usina_id", "data_id_prevista", "data_id_criacao")


class Recusado(RuntimeError):
    """O pedido do aplicativo que não vale (chave desligada, rodada de outro computador, planilha que não é planilha)."""


def _agora() -> str:
    return datetime.now(G._BRT).isoformat(timespec="seconds")


def _sha(chave: str) -> str:
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()


# ── os computadores ligados ────────────────────────────────────────────────────────────────────────────────────────────
def _arquivo(config) -> Path:
    return G.pasta_trabalho(config) / ARQUIVO


def _ler(config) -> list[dict]:
    try:
        d = json.loads(_arquivo(config).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [c for c in d.get("computadores", []) if isinstance(c, dict)] if isinstance(d, dict) else []


def _gravar(config, lista: list[dict]) -> None:
    p = _arquivo(config)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps({"computadores": lista}, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def computadores(config) -> list[dict]:
    """Os computadores ligados (sem o hash), o mais novo primeiro."""
    return [{k: v for k, v in c.items() if k != "sha"} for c in sorted(_ler(config), key=lambda c: c.get("criado_em") or "",
                                                                       reverse=True)]


def codigo(url: str, chave: str) -> str:
    """O código que a pessoa cola no aplicativo: o endereço do Nexus e a chave, num texto só."""
    bruto = json.dumps({"u": url.rstrip("/"), "k": chave}, separators=(",", ":")).encode("utf-8")
    return PREFIXO + base64.urlsafe_b64encode(bruto).decode("ascii").rstrip("=")


def ligar(config, nome: str, quem: str, url: str) -> str:
    """Liga um computador: guarda o hash de uma chave nova e devolve o código (a única vez em que a chave aparece)."""
    nome = " ".join(str(nome or "").split())[:60]
    if not nome:
        raise Recusado("Dê um nome ao computador (por exemplo, o PC do PCM no escritório).")
    chave = secrets.token_urlsafe(32)
    with _trava:
        lista = _ler(config)
        lista.append({"id": secrets.token_hex(4), "nome": nome, "sha": _sha(chave), "criado_em": _agora(),
                      "criado_por": quem, "ativo": True, "ultimo_uso": None})
        _gravar(config, lista)
    return codigo(url, chave)


def desligar(config, cid: str, quem: str) -> bool:
    with _trava:
        lista = _ler(config)
        achou = False
        for c in lista:
            if c.get("id") == cid and c.get("ativo"):
                c.update(ativo=False, desligado_em=_agora(), desligado_por=quem)
                achou = True
        if achou:
            _gravar(config, lista)
    return achou


def quem_e(config, chave: str | None) -> dict | None:
    """O computador ligado dono desta chave (o hash comparado em tempo constante), ou None. Marca o último uso."""
    chave = str(chave or "").strip()
    if not chave:
        return None
    sha = _sha(chave)
    with _trava:
        lista = _ler(config)
        for c in lista:
            if c.get("ativo") and hmac.compare_digest(str(c.get("sha") or ""), sha):
                c["ultimo_uso"] = _agora()
                _gravar(config, lista)
                return {k: v for k, v in c.items() if k != "sha"}
    return None


# ── a rodada no PC ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _reduzir_fama(fama: dict) -> dict:
    """A FAMA da rodada só com o que o motor usa: sem o título (só a sigla da preventiva), e o cadastro só com os nomes
    e a equipe de cada usina."""
    linhas = []
    for l in fama.get("linhas") or []:
        r = {k: l.get(k) for k in CAMPOS_DA_FAMA}
        r["titulo"] = FM.sigla(l)            # a sigla (MPM, MPA...) no lugar do título dá a mesma sigla no PC
        linhas.append(r)
    cadastro = {str(uid): {"nomes": list(u.get("nomes") or []), "equipe": u.get("equipe") or ""}
                for uid, u in (fama.get("cadastro") or {}).items()}
    return {"linhas": linhas, "cadastro": cadastro, "tirar_preventivas": bool(fama.get("tirar_preventivas", True))}


def abrir_rodada(config, semana: str, comp: dict) -> dict:
    """Abre a rodada da semana para o computador: prepara os insumos como a do servidor e deixa o estado "no_pc"."""
    if not G.SEMANA_RE.match(semana or ""):
        raise ValueError("semana inválida")
    conf = G.conferir(config, semana)
    if not conf["pronto"]:              # o mesmo portão do servidor (a credencial também: o PC a recebe do Nexus)
        raise G.NaoPronto("falta: " + ", ".join(i["nome"] for i in conf["itens"] if not i["ok"]))
    trabalho = G.pasta_trabalho(config)
    limpeza = G.limpar_rodadas(config)     # os caches das rodadas antigas (a cota de disco do servidor, 27/11/2026)
    rid = datetime.now(G._BRT).strftime("%Y%m%d-%H%M%S") + "-" + semana
    pasta = trabalho / "geracoes" / rid
    (pasta / "saida").mkdir(parents=True, exist_ok=False)
    origem = G.pasta_origem(config)
    try:
        insumos = G._preparar(config, semana, pasta, trabalho, origem)
    except G.NaoPronto:
        import shutil
        shutil.rmtree(pasta, ignore_errors=True)
        raise
    fama = G._fama(config, ler_o_fracttal=True)
    st = {"id": rid, "semana": semana, "estado": NO_PC, "inicio": _agora(), "credencial": "no PC",
          "insumos": insumos, "motor": "no PC", "limpeza": limpeza,
          "pc": {"computador": comp["id"], "nome": comp.get("nome") or "", "etapa": "preparando", "atualizado": _agora()}}
    if fama is not None and "fora" in fama:
        st["fama"] = {"fora": fama["fora"]}
    elif fama is not None:
        (pasta / "fama.json").write_text(json.dumps(_reduzir_fama(fama), ensure_ascii=False, default=str),
                                         encoding="utf-8")
        st["pc"]["fama"] = True
    G._gravar(pasta, st)
    return st


def _rodada(config, rid: str, comp: dict) -> tuple[Path, dict]:
    pasta = G._pasta_rodada(config, rid)
    st = G.ler_status(config, rid) if pasta else None
    if not st or (st.get("pc") or {}).get("computador") != comp["id"]:
        raise Recusado("Essa rodada não é deste computador.")
    return pasta, st


def pacote(config, rid: str, comp: dict) -> bytes:
    """O .zip da rodada para o aplicativo: os insumos da pasta da rodada, o motor e o adaptador da FAMA, e o `rodada.json`."""
    pasta, st = _rodada(config, rid, comp)
    if st.get("estado") != NO_PC:
        raise Recusado("Essa rodada já terminou.")
    motor = G.caminho_motor(config)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        # a pasta inteira, com as SUBPASTAS: os feriados moram em `Feriados/` (a prova no ar de 27/11/2026 levou só os
        # arquivos de cima, e o motor rodou a W49 sem feriados); fora a saída, o status e o log, que são da volta
        for f in sorted(pasta.rglob("*")):
            rel = f.relative_to(pasta)
            if f.is_file() and rel.parts[0] != "saida" and rel.as_posix() not in ("status.json", "log_motor.txt"):
                z.write(f, "rodada/" + rel.as_posix())
        z.writestr("pcm/__init__.py", "")
        for nome in MODULOS_DA_FAMA:
            z.write(AQUI / nome, f"pcm/{nome}")
        z.writestr("pcm/motor/__init__.py", "")
        for f in sorted(motor.parent.glob("*.py")):
            z.write(f, f"pcm/motor/{f.name}")
        z.writestr("rodada.json", json.dumps({
            "id": st["id"], "semana": st["semana"], "fama": bool((st.get("pc") or {}).get("fama")),
            "fama_fora": (st.get("fama") or {}).get("fora") or "", "motor": motor.name,
            "url_api": G.URL_API, "intervalo_s": G.INTERVALO_S, "ttl_fama_min": FM.TTL_MIN,
            "tempo_max_s": G.TEMPO_MAX_S, "cache": FM.CACHE}, ensure_ascii=False))
    return buf.getvalue()


def credencial(config) -> dict:
    """As chaves do Fracttal para o aplicativo (só a um computador ligado; quem chama confere a chave)."""
    cred = G.credencial(config)
    if not cred.ok:
        raise Recusado("O Nexus não tem a credencial do Fracttal.")
    return {"client_id": cred.client_id, "client_secret": cred.client_secret, "base_url": G.URL_API}


def andamento(config, rid: str, comp: dict, etapa: str) -> None:
    """A etapa em que o PC está (a tela de Gerar a semana a mostra enquanto roda)."""
    pasta, st = _rodada(config, rid, comp)
    if st.get("estado") != NO_PC:
        return
    st["pc"] = dict(st.get("pc") or {}, etapa=str(etapa or "")[:120], atualizado=_agora())
    G._gravar(pasta, st)


def _relato_da_fama(relato: dict) -> dict | None:
    """O relatório da FAMA que o PC mandou, só com contagens e o motivo (nada de texto livre longo)."""
    f = relato.get("fama")
    if not isinstance(f, dict):
        return None
    out = {}
    for k, v in f.items():
        if isinstance(v, bool) or isinstance(v, int):
            out[str(k)[:40]] = v
        elif isinstance(v, str):
            out[str(k)[:40]] = v[:300]
    return out


def entregar(config, rid: str, comp: dict, planilha: bytes | None, log: bytes | None, relato: dict) -> dict:
    """A volta do PC: grava a planilha e o log na rodada e a termina pelo MESMO `geracao.concluir` do servidor."""
    pasta, st = _rodada(config, rid, comp)
    if st.get("estado") != NO_PC:
        raise Recusado("Essa rodada já terminou.")
    if planilha is not None and (len(planilha) > PLANILHA_MAX or not planilha.startswith(b"PK")):
        raise Recusado("O arquivo enviado não é uma planilha.")
    (pasta / "log_motor.txt").write_bytes((log or b"")[-LOG_MAX:])
    saida = pasta / "saida" / "sombra.xlsx"
    if planilha:
        saida.write_bytes(planilha)
    try:
        codigo_ = int(relato.get("codigo"))
    except (TypeError, ValueError):
        codigo_ = 1
    fama = _relato_da_fama(relato)
    if fama is not None:
        st["fama"] = fama
    tentou = bool((st.get("pc") or {}).get("fama")) and fama is not None and "fora" not in fama
    st["codigo"] = codigo_
    st["pc"] = dict(st.get("pc") or {}, etapa="terminou", atualizado=_agora())
    try:
        G.concluir(pasta, st, saida, G.pasta_origem(config), codigo_ if planilha else (codigo_ or 1),
                   depois_da_fama=tentou)
    except Exception as ex:      # noqa: BLE001 — qualquer falha fica no status, como na rodada do servidor
        st["estado"] = "falhou"
        st["erro"] = f"{type(ex).__name__}: {str(ex)[:300]}"
    if st.get("estado") == "falhou" and relato.get("erro"):
        st["erro"] = str(relato["erro"])[:600]
    st["fim"] = _agora()
    try:
        st["duracao_s"] = int(relato.get("duracao_s"))
    except (TypeError, ValueError):
        pass
    G._gravar(pasta, st)
    return {"id": rid, "estado": st["estado"]}
