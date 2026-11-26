"""A assinatura desenhada de quem dá o De acordo na PT (26/11/2026).

Levi, 26/11/2026, depois de saber que um operador do COS "só clica e já aprova direto": "o certo é ter a assinatura do
técnico e a assinatura dele"; "todas as PTs têm que pedir assinatura". Até a v364 do App o painel do Azure exigia o
desenho ("Assine no quadro: é a sua assinatura que vai no PDF da PT"); desde que a decisão veio para o Nexus, o PDF levava
só o nome, a data e "assinado no Nexus com a conta Microsoft". Agora o De acordo do Nexus pede o desenho no card de
assinar, e o Nexus:
- guarda a imagem cifrada no disco desta máquina (`<NEXUS_DADOS>/pt_assinaturas/`, com a chave do cadastro e o número da
  PT e o código do ativo como contexto). Não vai ao banco: a API tem leitura aberta e a assinatura é dado pessoal;
- manda a imagem ao App, de servidor para servidor, ANTES de gravar a decisão (`enviar_ao_app`), para o App desenhá-la no
  quadro "Aprovação" do PDF. Contrato v1 proposto ao App em 26/11/2026: `POST <base>/app/nexus/pt/<numero>/assinatura-
  aprovador` com a chave das Sugestões (`X-Nexus-Chave`) e `{"versao": 1, "codigo", "png_base64", "pessoa_hmac",
  "assinatura_id"}` → 200 `{"ok": true}`. O envio só liga com o 1 em Base → Chaves do Nexus ("PT: mandar a assinatura do
  De acordo ao App", `NEXUS_PT_ASSINATURA_APP`; o .env vale sem ela), quando a rota do App existir: desligado, o desenho
  é exigido e guardado, e a decisão segue como antes.

O "Não autorizo" não pede desenho: pede o motivo, que o técnico lê."""
from __future__ import annotations

import base64
import json
import re
import secrets
from pathlib import Path

PNG = b"\x89PNG\r\n\x1a\n"
MAX_BYTES = 200 * 1024
MIN_BYTES = 200            # um PNG em branco do quadro tem bem menos de desenho que isto não é assinatura
_DATA_URL = re.compile(r"data:image/png;base64,([A-Za-z0-9+/=\s]+)")


class Recusada(ValueError):
    """O desenho não serve ou não chegou ao App: o texto diz por quê, para a tela mostrar."""


def png_do_formulario(valor) -> bytes:
    """Os bytes do PNG que o quadro do card mandou (`data:image/png;base64,...`). Recusa o vazio, o que não é PNG e o
    grande demais."""
    m = _DATA_URL.fullmatch(str(valor or "").strip())
    if not m:
        raise Recusada("Assine no quadro antes de dar o De acordo: a sua assinatura vai no PDF da PT, ao lado da do "
                       "técnico.")
    try:
        dados = base64.b64decode(re.sub(r"\s", "", m.group(1)), validate=True)
    except ValueError:
        raise Recusada("A assinatura não chegou inteira. Assine de novo.") from None
    if not dados.startswith(PNG):
        raise Recusada("A assinatura não chegou inteira. Assine de novo.")
    if len(dados) > MAX_BYTES:
        raise Recusada("A assinatura ficou grande demais. Limpe o quadro e assine de novo.")
    if len(dados) < MIN_BYTES:
        raise Recusada("Assine no quadro antes de dar o De acordo: a sua assinatura vai no PDF da PT, ao lado da do "
                       "técnico.")
    return dados


def _pasta(cfg) -> Path | None:
    """A pasta das assinaturas; teste sem pasta de dados própria = None (não grava na pasta de verdade)."""
    from ..cadastro.ligacoes import pasta_dados
    try:
        return pasta_dados(cfg) / "pt_assinaturas"
    except RuntimeError:
        return None


def _nome(numero, codigo) -> str:
    seguro = lambda s: re.sub(r"[^A-Za-z0-9_-]", "_", str(s or ""))[:80]   # noqa: E731
    return f"{seguro(numero)}__{seguro(codigo) or 'sem_ativo'}.bin"


def _contexto(numero, codigo) -> str:
    return f"pt-assinatura/{numero}/{codigo or ''}"


def _cofre(cfg):
    from ..cadastro.cifra import Cofre
    chave = cfg.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        raise Recusada("Este Nexus não tem a chave do cadastro para guardar a assinatura.")
    return Cofre(chave)


def guardar(cfg, numero, codigo, png: bytes, quem_hmac: str, quando: str) -> None:
    """A assinatura cifrada no disco (a última de cada linha vale: o De acordo é um só)."""
    pasta = _pasta(cfg)
    if pasta is None:
        return
    pasta.mkdir(parents=True, exist_ok=True)
    corpo = json.dumps({"png": base64.b64encode(png).decode("ascii"), "por_hmac": quem_hmac, "em": quando})
    (pasta / _nome(numero, codigo)).write_text(_cofre(cfg).cifrar(corpo, _contexto(numero, codigo)), encoding="utf-8")


def ler(cfg, numero, codigo) -> dict | None:
    """{"png": bytes, "por_hmac", "em"} da assinatura guardada desta linha, ou None."""
    pasta = _pasta(cfg)
    arq = pasta / _nome(numero, codigo) if pasta is not None else None
    if arq is None or not arq.exists():
        return None
    try:
        d = json.loads(_cofre(cfg).decifrar(arq.read_text(encoding="utf-8"), _contexto(numero, codigo)))
        return {"png": base64.b64decode(d["png"]), "por_hmac": d.get("por_hmac") or "", "em": d.get("em") or ""}
    except Exception:            # noqa: BLE001 — arquivo de outra chave ou estragado: como se não houvesse
        return None


def envio_ligado(cfg) -> bool:
    """Base → Chaves do Nexus ("PT: mandar a assinatura do De acordo ao App") e, sem ela, o .env."""
    from ..auth import chaves
    return (chaves.valor("NEXUS_PT_ASSINATURA_APP", cfg) or "").strip() == "1"


def enviar_ao_app(numero, codigo, png: bytes, quem_hmac: str) -> None:
    """Manda a assinatura ao App (o contrato v1 no topo). Recusada quando o App não a aceita ou não responde."""
    from ..casca import relatos_app as R
    if not R.ligado():
        raise Recusada("Este Nexus não tem a chave do App para mandar a assinatura.")
    base = R._url()
    if base.endswith("/relatos"):
        base = base[: -len("/relatos")]
    from urllib.parse import quote
    corpo = {"versao": 1, "codigo": str(codigo or ""), "png_base64": base64.b64encode(png).decode("ascii"),
             "pessoa_hmac": quem_hmac, "assinatura_id": "a" + secrets.token_hex(6)[:11]}
    import urllib.request
    req = urllib.request.Request(f"{base}/pt/{quote(str(numero), safe='')}/assinatura-aprovador",
                                 data=json.dumps(corpo).encode("utf-8"), method="POST",
                                 headers={"X-Nexus-Chave": R._conf(R.NOME_CHAVE), "Accept": "application/json",
                                          "Content-Type": "application/json; charset=utf-8",
                                          "User-Agent": "Nexus-GridCo/1 (pt-assinatura)"})
    try:
        d = R._chamar(req)
    except R.FonteErro as ex:
        raise Recusada(f"O App não recebeu a assinatura ({ex}). Nada foi salvo; tente de novo.") from None
    if not isinstance(d, dict) or d.get("ok") is not True:
        raise Recusada("O App não confirmou a assinatura. Nada foi salvo; tente de novo.")
