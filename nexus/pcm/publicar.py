"""Publicar no App de Campo a semana que o Nexus gerou.

Levi, 09/10/2026: "faça as adaptações necessárias para que isso seja possível, semana que vem já quero full nexus sem
falta". O caminho é o MESMO do PC do PCM (`publicar_semana_github.py` do repositório do PCM): a
`Programação Semana NN.xlsx` e o `Observacoes_Semana.txt` vão para a raiz do repositório `gridco-pcm-data` pela API de
conteúdo do GitHub (PUT com o sha do arquivo que está lá). O push dispara o robô `semanal.yml` do PCM (gatilho
`Programa*.xlsx` e `Observacoes_Semana*.txt`, sem esperar o descanso de 30 min), que roda o `atualizacao_semanal.py`
e o `gerar_pcm_json.py` e regrava o `banco_dados.json`: é esse arquivo que o App de Campo lê. Nada muda no App nem no
robô. A semana vira a ativa do App na segunda-feira dela (o robô escolhe a semana pela data de hoje).

O que o Nexus NÃO manda: o `Observacoes_Semana_Atual.txt` (os ajustes da semana EM CURSO, que o painel do PCM grava).
A tela de publicar mostra o que está lá, para a pessoa decidir se pede para o painel limpar.

Antes (a tela pede a confirmação; `motivos_para_nao_publicar` barra): a rodada terminou bem, é geração de verdade (a
"-foto" é prova), a semana ainda não acabou, a planilha e as observações da rodada existem e todo bloco cai na semana.
Depois: relê do repositório cada arquivo enviado e compara o sha256 com o que foi (conferir depois de gravar), grava a
publicação na rodada (`publicacao.json` e o `status.json`) e guarda o plano publicado na reserva do Nexus
(`insumos.registrar_plano_publicado`): é o plano que o histórico usa enquanto a semana não fecha no banco.

Token: `NEXUS_PCM_GITHUB_TOKEN` (ambiente ou .env do Nexus; no servidor, um token só deste repositório, com escrita de
conteúdo). Sem ele, no PC, o login do `gh` da máquina (o de quem está no PC). Nunca é impresso nem gravado.
"""
import base64
import hashlib
import json
import os
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values

from . import fonte, geracao, historico_banco as HB, insumos as I

API = "https://api.github.com"
OBS_ATUAL = "Observacoes_Semana_Atual.txt"
_BRT = timezone(timedelta(hours=-3))
_trava = threading.Lock()


class PublicacaoErro(RuntimeError):
    pass


def _agora() -> datetime:
    return datetime.now(_BRT)


def nome_planilha(semana: str) -> str:
    """'2026-W43' -> 'Programação Semana 43.xlsx' (o nome que o robô do PCM procura)."""
    return f"Programação Semana {HB.segunda(semana).isocalendar()[1]:02d}.xlsx"


repositorio = fonte.repositorio


def token(config) -> tuple[str, str]:
    """(token, de onde veio), sem expor o valor. Nos testes, só o de teste."""
    if config.get("TESTING"):
        t = config.get("NEXUS_PCM_GITHUB_TOKEN") or ""
        return t, "teste" if t else ""
    t = os.environ.get("NEXUS_PCM_GITHUB_TOKEN") or config.get("NEXUS_PCM_GITHUB_TOKEN")
    if t:
        return t.strip(), "NEXUS_PCM_GITHUB_TOKEN"
    t = dotenv_values(geracao.RAIZ / ".env").get("NEXUS_PCM_GITHUB_TOKEN")
    if t:
        return t.strip(), "NEXUS_PCM_GITHUB_TOKEN do .env do Nexus"
    try:
        r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip(), "o login do gh desta máquina"
    except (OSError, subprocess.SubprocessError):
        pass
    return "", ""


def _sessao(config):
    s = config.get("NEXUS_PCM_GITHUB_SESSAO")       # os testes põem um GitHub falso aqui
    if s is not None:
        return s
    if config.get("TESTING"):
        raise PublicacaoErro("teste sem GitHub")
    import requests
    return requests.Session()


def _cab(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "Nexus-GridCo/1 (publicar semana)"}


def _url(repo: str, nome: str) -> str:
    return f"{API}/repos/{repo}/contents/{quote(nome)}"


def _ler(s, tok: str, repo: str, ramo: str, nome: str) -> dict | None:
    """O arquivo no repositório ({sha, bytes}) ou None."""
    r = s.get(_url(repo, nome), headers=_cab(tok), params={"ref": ramo}, timeout=60)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    j = r.json()
    conteudo = j.get("content")
    if conteudo is None and j.get("download_url"):       # arquivo acima de 1 MB: a API manda só o endereço
        d = s.get(j["download_url"], headers=_cab(tok), timeout=60)
        d.raise_for_status()
        dados = d.content
    else:
        dados = base64.b64decode(conteudo or "")
    return {"sha": j.get("sha"), "bytes": dados}


def _ultimo_commit(s, tok: str, repo: str, ramo: str, nome: str) -> dict | None:
    r = s.get(f"{API}/repos/{repo}/commits", headers=_cab(tok), params={"path": nome, "sha": ramo, "per_page": 1},
              timeout=60)
    if r.status_code != 200:
        return None
    xs = r.json() or []
    if not xs:
        return None
    c = xs[0].get("commit") or {}
    quando = (c.get("author") or {}).get("date") or ""
    try:
        quando = datetime.fromisoformat(quando.replace("Z", "+00:00")).astimezone(_BRT).strftime("%d/%m %H:%M")
    except ValueError:
        pass
    return {"sha": (xs[0].get("sha") or "")[:7], "quando": quando, "quem": (c.get("author") or {}).get("name") or "",
            "mensagem": (c.get("message") or "").splitlines()[0][:120]}


def _gravar(s, tok: str, repo: str, ramo: str, nome: str, dados: bytes, mensagem: str) -> str:
    """PUT do arquivo (com o sha do que está lá, se houver). Uma 2ª tentativa se o ramo andou no meio (409): o robô do
    PCM commita o banco_dados.json no mesmo ramo."""
    for _ in range(2):
        atual = _ler(s, tok, repo, ramo, nome)
        corpo = {"message": mensagem, "content": base64.b64encode(dados).decode("ascii"), "branch": ramo}
        if atual:
            corpo["sha"] = atual["sha"]
        r = s.put(_url(repo, nome), headers=_cab(tok), json=corpo, timeout=120)
        if r.status_code in (409, 422) and atual is not None:
            continue
        r.raise_for_status()
        return ((r.json() or {}).get("commit") or {}).get("sha", "")[:12]
    raise PublicacaoErro(f"{nome}: o repositório mudou duas vezes durante a gravação; tente de novo")


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def arquivos_da_rodada(config, rid: str) -> tuple[dict, list[tuple[str, Path]]]:
    """(status, [(nome no repositório, arquivo da rodada)])."""
    st = geracao.ler_status(config, rid)
    if not st:
        raise PublicacaoErro("rodada não encontrada")
    pasta = geracao.pasta_trabalho(config) / "geracoes" / rid
    return st, [(nome_planilha(st["semana"]), pasta / "saida" / "sombra.xlsx"),
                (I.OBSERVACOES, pasta / I.OBSERVACOES)]


def motivos_para_nao_publicar(config, rid: str, agora: datetime | None = None) -> list[str]:
    """O que impede publicar esta rodada (vazio = pode)."""
    if not geracao.RODADA_RE.match(rid or ""):
        return ["rodada inválida (as rodadas com a foto do Fracttal são prova e não se publicam)"]
    try:
        st, arqs = arquivos_da_rodada(config, rid)
    except PublicacaoErro as ex:
        return [str(ex)]
    out = []
    if st.get("estado") != "ok":
        out.append("a rodada não terminou bem")
    if HB.fim_da_semana(st["semana"]) <= (agora or _agora()):
        out.append(f"a semana {st['semana']} já acabou")
    for nome, p in arqs:
        if not p.exists():
            out.append(f"falta na rodada: {nome}")
    conf = st.get("conferencia") or {}
    if st.get("estado") == "ok" and not conf:
        out.append("a rodada não tem a conferência da semana (é de antes de 09/10/2026 ou a conferência falhou): "
                   "gere de novo")
    if conf.get("fora_da_semana"):
        out.append(f"{conf['fora_da_semana']} blocos fora da semana {st['semana']}")
    return out


def ja_comecou(semana: str, agora: datetime | None = None) -> bool:
    """A semana já começou (a segunda-feira dela já chegou)? Publicar agora troca a programação que o campo está
    seguindo: a tela pede uma confirmação a mais."""
    return HB.segunda(semana) <= (agora or _agora()).date()


def estado_no_repositorio(config, semana: str) -> dict:
    """O que o repositório do PCM tem hoje para a semana: a planilha (e o último commit dela) e os ajustes da semana em
    curso (`Observacoes_Semana_Atual.txt`). Para a tela de confirmar. Falha de rede vira `erro`, nunca exceção."""
    tok, de_onde = token(config)
    repo, ramo = repositorio(config)
    out = {"repo": repo, "ramo": ramo, "token": de_onde, "planilha": nome_planilha(semana), "existe": False,
           "commit": None, "obs_atual": None, "erro": ""}
    if not tok:
        out["erro"] = "sem token do GitHub (NEXUS_PCM_GITHUB_TOKEN)"
        return out
    try:
        s = _sessao(config)
        atual = _ler(s, tok, repo, ramo, out["planilha"])
        out["existe"] = atual is not None
        if atual is not None:
            out["commit"] = _ultimo_commit(s, tok, repo, ramo, out["planilha"])
        obs = _ler(s, tok, repo, ramo, OBS_ATUAL)
        out["obs_atual"] = obs["bytes"].decode("utf-8", errors="replace") if obs else ""
    except Exception as ex:      # noqa: BLE001 — a tela mostra e não publica
        out["erro"] = f"{type(ex).__name__}: {str(ex)[:160]}"
    return out


def publicar(config, rid: str, quem: str, agora: datetime | None = None) -> dict:
    """Publica a rodada no repositório do PCM e confere. Devolve o registro da publicação (também gravado na rodada)."""
    with _trava:
        motivos = motivos_para_nao_publicar(config, rid, agora)
        if motivos:
            raise PublicacaoErro("; ".join(motivos))
        tok, de_onde = token(config)
        if not tok:
            raise PublicacaoErro("sem token do GitHub: ponha NEXUS_PCM_GITHUB_TOKEN no .env do Nexus")
        repo, ramo = repositorio(config)
        st, arqs = arquivos_da_rodada(config, rid)
        s = _sessao(config)
        enviados = []
        for nome, p in arqs:
            dados = p.read_bytes()
            commit = _gravar(s, tok, repo, ramo, nome, dados,
                             f"chore: Nexus publica {nome} (semana {st['semana']}, rodada {rid})")
            enviados.append({"nome": nome, "commit": commit, "sha256": _sha256(dados), "bytes": len(dados)})
        # conferir depois de gravar: o que está no repositório é o que foi
        for e in enviados:
            lido = _ler(s, tok, repo, ramo, e["nome"])
            if not lido or _sha256(lido["bytes"]) != e["sha256"]:
                raise PublicacaoErro(f"{e['nome']}: o repositório não tem o arquivo enviado (gravado no commit "
                                     f"{e['commit']}); confira no GitHub antes de publicar de novo")
            e["conferido"] = True
        quando = (agora or _agora()).isoformat(timespec="seconds")
        pub = {"semana": st["semana"], "rodada": rid, "quando": quando, "quem": quem, "repo": repo, "ramo": ramo,
               "token": de_onde, "arquivos": enviados}
        pasta = geracao.pasta_trabalho(config) / "geracoes" / rid
        (pasta / "publicacao.json").write_text(json.dumps(pub, ensure_ascii=False, indent=1), encoding="utf-8")
        st["publicacao"] = pub
        geracao._gravar(pasta, st)
        # o plano publicado da semana vai para a reserva: é ele que o histórico usa até a semana fechar no banco
        chaves = HB.chaves_da_planilha(pasta / "saida" / "sombra.xlsx")
        I.registrar_plano_publicado(geracao.pasta_trabalho(config), st["semana"], chaves,
                                    f"publicado pelo Nexus em {pub['quando'][:16]} (rodada {rid})")
        pub["plano_chaves"] = len(chaves)
        return pub


def publicacoes(config) -> dict:
    """{semana: a publicação mais recente feita pelo Nexus} das rodadas da tela."""
    out = {}
    for st in geracao.ultimas(config, 40):
        p = st.get("publicacao")
        if p and (p["semana"] not in out or p["quando"] > out[p["semana"]]["quando"]):
            out[p["semana"]] = p
    return out


def semana_no_app(dados: dict | None, semana: str) -> dict | None:
    """A semana no `banco_dados.json` que o App lê (fonte.py): quando o robô a gerou e quantas linhas. None = ainda não
    está lá (o robô do PCM leva de 5 a 10 min depois do push)."""
    for s in (dados or {}).get("semanas") or []:
        if isinstance(s, dict) and s.get("week") == semana:
            return {"gerada_em": s.get("geradaEm") or "", "linhas": len(s.get("rows") or []),
                    "pendentes": len(s.get("pendentes") or [])}
    return None
