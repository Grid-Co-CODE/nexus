"""O arquivo das folhas emitidas automaticamente: `<pasta de dados>/pcm/relatorios/<tipo>/<ref>.html`.

Como o `relatorios/` do repositório do PCM, que o robô de lá commitava: diário e tarde guardados 30 dias, fechamento e
alerta sem limpeza. É documento, não dado: o HTML não vai ao banco (o banco é tabela; nexus/dados/CLAUDE.md), e cada
máquina guarda o seu. O que a emissão precisa saber de volta (quando foi, e a versão da semana que o alerta conferiu)
vai em `<meta name="nexus-...">` no próprio arquivo, sem JSON de estado ao lado.
"""
import html as _html
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from ...cadastro.ligacoes import pasta_dados

GUARDAR_DIAS = 30
_REF_DIA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REF_SEMANA = re.compile(r"^\d{4}-W\d{2}$")
REF = {"diario": _REF_DIA, "tarde": _REF_DIA, "semanal": _REF_SEMANA, "alerta": _REF_SEMANA}
_META = re.compile(r'<meta name="nexus-([a-z]+)" content="([^"]*)">')


def ref_valida(tipo: str, ref: str) -> bool:
    """Só o formato do tipo: é também o que impede um endereço de sair da pasta."""
    return tipo in REF and bool(REF[tipo].match(ref or ""))


def pasta(config, tipo: str) -> Path:
    return pasta_dados(config) / "pcm" / "relatorios" / tipo


def gravar(config, tipo: str, ref: str, html: str, gerado: datetime, extra: dict | None = None) -> Path:
    if not ref_valida(tipo, ref):
        raise ValueError(f"referência inválida para {tipo}: {ref!r}")
    metas = {"tipo": tipo, "ref": ref, "gerado": gerado.isoformat(timespec="minutes"), **(extra or {})}
    cab = "".join(f'<meta name="nexus-{k}" content="{_html.escape(str(v), quote=True)}">' for k, v in metas.items())
    html = html.replace('<meta charset="utf-8">', '<meta charset="utf-8">' + cab, 1)
    p = pasta(config, tipo)
    p.mkdir(parents=True, exist_ok=True)
    tmp = p / f".{ref}.tmp"
    tmp.write_text(html, encoding="utf-8")
    os.replace(tmp, p / f"{ref}.html")          # quem lê no meio da gravação vê o arquivo velho ou o novo, nunca meio
    return p / f"{ref}.html"


def _metas(arq: Path) -> dict:
    try:
        with open(arq, encoding="utf-8") as f:
            topo = f.read(4096)
    except OSError:
        return {}
    return {k: _html.unescape(v) for k, v in _META.findall(topo)}


def existe(config, tipo: str, ref: str) -> dict | None:
    """As marcas da folha guardada (gerado, geradaem...), ou None quando ela não existe."""
    if not ref_valida(tipo, ref):
        return None
    arq = pasta(config, tipo) / f"{ref}.html"
    return _metas(arq) if arq.is_file() else None


def ler(config, tipo: str, ref: str) -> str | None:
    if not ref_valida(tipo, ref):
        return None
    arq = pasta(config, tipo) / f"{ref}.html"
    try:
        return arq.read_text(encoding="utf-8")
    except OSError:
        return None


def listar(config, tipos, limite: int = 40) -> list[dict]:
    """As emissões guardadas dos `tipos`, da mais nova para a mais velha: [{tipo, ref, gerado (datetime ou None)}]."""
    out = []
    for tipo in tipos:
        p = pasta(config, tipo)
        if not p.is_dir():
            continue
        for arq in p.glob("*.html"):
            ref = arq.stem
            if not ref_valida(tipo, ref):
                continue
            m = _metas(arq)
            try:
                gerado = datetime.fromisoformat(m.get("gerado", ""))
            except ValueError:
                gerado = None
            out.append({"tipo": tipo, "ref": ref, "gerado": gerado})
    out.sort(key=lambda e: (e["gerado"].isoformat() if e["gerado"] else "", e["ref"]), reverse=True)
    return out[:limite]


def limpar(config, hoje: date) -> int:
    """Apaga diário e tarde com mais de 30 dias (o PCM fazia o mesmo). Devolve quantos saíram."""
    corte, saiu = hoje - timedelta(days=GUARDAR_DIAS), 0
    for tipo in ("diario", "tarde"):
        p = pasta(config, tipo)
        if not p.is_dir():
            continue
        for arq in p.glob("*.html"):
            try:
                if date.fromisoformat(arq.stem) < corte:
                    arq.unlink()
                    saiu += 1
            except (ValueError, OSError):
                continue
    return saiu
