"""Os arquivos do SSO (fotos, vídeos, PDFs dos certificados) no disco do servidor do Nexus, no lugar do Storage do Supabase.

Ficam em `<NEXUS_DADOS>/sso/arquivos/<bucket>/<caminho>`, com o MESMO bucket e caminho que o app sempre usou (como os PDFs
dos contratos da Zeladoria, `nexus/zeladoria/contratos_pdf.py`): grandes demais para o banco, que guarda planilhas
(~1,5 GB por mês em outubro de 2026). No Supabase os buckets eram públicos (quem tinha o endereço abria a foto com CPF e
assinatura); aqui só abre com o link assinado que a Gestão recebe ao ler (12 h) ou com o passe dela, e o vídeo da sessão
ativa, que o fornecedor assiste sem login.

As URLs antigas do Supabase continuam dentro das linhas: ao ler, toda URL de arquivo (`/storage/v1/object/public/
<bucket>/<caminho>`, de qualquer endereço) vira o endereço do Nexus com a assinatura. O arquivo antigo que ainda não
foi resgatado (os ~2,5 GB travados no Supabase desde 11/11/2026) responde 404, e abre quando a página do administrador
(`/t/sso/admin`) o receber pelo caminho do inventário.
"""
from __future__ import annotations

import os
import re
import shutil
import uuid
from pathlib import Path

from itsdangerous import BadData, URLSafeTimedSerializer

from . import esquema as E

FOLGA = 2 * 1024 ** 3                 # o disco do servidor não fica com menos de 2 GB livres por causa do SSO
VALIDADE_S = 12 * 3600                # o link assinado vale 12 h (o turno da Gestão)
_SEGMENTO = r"[A-Za-z0-9_-][A-Za-z0-9._-]{0,150}"
CAMINHO = re.compile(rf"^{_SEGMENTO}(?:/{_SEGMENTO}){{0,3}}$")
URL = re.compile(r"^(?P<antes>(?:https?:)?(?://[^/\s?#]+)?(?:/[^\s?#]*?)?)/storage/v1/object/public/"
                 r"(?P<bucket>[a-z0-9-]{3,63})/(?P<caminho>[^?#\s]+)(?P<depois>[?#].*)?$")
_DATA_IMAGEM = re.compile(r"^data:image/(png|jpeg|jpg|webp);base64,[A-Za-z0-9+/=\s]*$")


class Recusado(ValueError):
    """O arquivo ou o caminho não vale; a mensagem vai para o app."""


def pasta(config) -> Path:
    from ..cadastro.ligacoes import pasta_dados
    return Path(pasta_dados(config)) / "sso" / "arquivos"


def caminho_ok(caminho: str, *, do_inventario: bool = False) -> bool:
    """O caminho que o app monta (`<id>/desvio-1-foto.jpg`, `antes/<ts>-<rand>.jpg`); o do inventário, só sem `..`."""
    c = str(caminho or "")
    if do_inventario:
        return bool(c) and len(c) <= 400 and not c.startswith("/") and "\\" not in c and "\x00" not in c \
            and ".." not in c.split("/") and all(ord(x) >= 32 for x in c)
    return len(c) <= 300 and bool(CAMINHO.match(c))


def arquivo(config, bucket: str, caminho: str, *, do_inventario: bool = False) -> Path:
    """O arquivo do bucket e do caminho, sempre dentro da pasta do SSO."""
    if bucket not in E.BUCKETS or not caminho_ok(caminho, do_inventario=do_inventario):
        raise Recusado("caminho de arquivo inválido")
    base = (pasta(config) / bucket).resolve()
    alvo = (base / caminho).resolve()
    if base not in alvo.parents:
        raise Recusado("caminho de arquivo inválido")
    return alvo


def existe(config, bucket: str, caminho: str) -> bool:
    try:
        return arquivo(config, bucket, caminho, do_inventario=True).is_file()
    except Recusado:
        return False


def livre(config) -> int:
    p = pasta(config)
    while not p.exists() and p != p.parent:
        p = p.parent
    return shutil.disk_usage(p).free


def guardar(config, bucket: str, caminho: str, fluxo, *, sobrescrever: bool, do_inventario: bool = False) -> dict:
    """Grava o arquivo (troca atômica) lendo o fluxo aos pedaços: o vídeo da integração tem 28 MB e não precisa estar
    inteiro na memória. Recusa o tipo fora do bucket (pelos primeiros bytes), o tamanho acima do teto, o arquivo que já
    existe (o fornecedor nunca escreve por cima, como o `upsert: false` do Supabase) e o disco sem folga."""
    regra = E.BUCKETS.get(bucket)
    if regra is None:
        raise Recusado("bucket inválido")
    alvo = arquivo(config, bucket, caminho, do_inventario=do_inventario)
    if alvo.exists() and not sobrescrever:
        raise Recusado("o arquivo já existe")
    alvo.parent.mkdir(parents=True, exist_ok=True)
    # o rascunho tem nome só dele: dois envios ao mesmo caminho não escrevem no mesmo arquivo (revisão de 12/11/2026)
    tmp = alvo.with_name(f"{alvo.name}.{uuid.uuid4().hex}.enviando")
    tamanho, tipo = 0, None
    try:
        with open(tmp, "wb") as f:
            while True:
                pedaco = fluxo.read(1024 * 1024)
                if not pedaco:
                    break
                if tipo is None:
                    tipo = E.tipo_do_arquivo(pedaco)
                    if tipo not in regra["tipos"]:
                        raise Recusado("tipo de arquivo não aceito aqui")
                tamanho += len(pedaco)
                if tamanho > regra["max"]:
                    raise Recusado(f"o arquivo passa de {regra['max'] // E.MB} MB")
                if tamanho % (64 * 1024 * 1024) < len(pedaco) and livre(config) < FOLGA:
                    raise Recusado("o servidor está sem espaço para arquivos agora")
                f.write(pedaco)
            if tipo is None:
                raise Recusado("arquivo vazio")
            if livre(config) < FOLGA:
                raise Recusado("o servidor está sem espaço para arquivos agora")
            f.flush()
            os.fsync(f.fileno())
        if sobrescrever:
            os.replace(tmp, alvo)
        else:
            try:
                os.link(tmp, alvo)              # cria só se não existe: o 2º envio ao mesmo caminho perde, sem trocar
            except FileExistsError:
                raise Recusado("o arquivo já existe") from None
    finally:
        if tmp.exists():
            tmp.unlink()
    return {"tipo": tipo, "bytes": tamanho}


# ── o link assinado ──────────────────────────────────────────────────────────────────────────────────────────────────
def _assinador(app) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(app.secret_key, salt="nexus/sso/arquivo")


def assinar(app, bucket: str, caminho: str) -> str:
    return _assinador(app).dumps(f"{bucket}/{caminho}")


def confere(app, assinatura: str | None, bucket: str, caminho: str) -> bool:
    if not assinatura:
        return False
    try:
        return _assinador(app).loads(assinatura, max_age=VALIDADE_S) == f"{bucket}/{caminho}"
    except BadData:
        return False


def _andar(obj, troca):
    if isinstance(obj, str):
        return troca(obj)
    if isinstance(obj, list):
        return [_andar(x, troca) for x in obj]
    if isinstance(obj, dict):
        return {k: _andar(v, troca) for k, v in obj.items()}
    return obj


def assinadas(app, obj, base: str):
    """Cada URL de arquivo dentro de `obj` (a linha, o JSON dentro dela) vira o endereço do Nexus com a assinatura."""
    from urllib.parse import quote

    def troca(s):
        m = URL.match(s) if "/storage/v1/object/public/" in s else None
        if not m or m.group("bucket") not in E.BUCKETS:
            return s
        b, c = m.group("bucket"), m.group("caminho")
        return f"{base}/storage/v1/object/public/{b}/{c}?a={quote(assinar(app, b, c))}"
    return _andar(obj, troca)


def sem_assinatura(obj):
    """O que a Gestão manda de volta (a linha editada) vai ao banco sem a assinatura, que vence em 12 h."""
    def troca(s):
        m = URL.match(s) if "/storage/v1/object/public/" in s else None
        if not m or not m.group("depois"):
            return s
        return s[:m.start("depois")]
    return _andar(obj, troca)


def estranhas(obj, host: str) -> list:
    """As URLs que o fornecedor não pode gravar: só arquivo deste Nexus num bucket do SSO, ou a assinatura desenhada
    (`data:image/png;base64,...`). Sem isto, a linha levaria à Gestão um link de outro site."""
    achadas = []

    def olha(s):
        # sem os caracteres de controle e os espaços que o navegador ignora no esquema (java, um tab e script:)
        t = re.sub(r"[\x00-\x20]", "", s).lower()
        if t.startswith(("http:", "https:", "//", "javascript:", "vbscript:", "file:")):
            m = URL.match(s.strip())
            dono = (m.group("antes").split("//", 1)[-1].split("/", 1)[0].lower() if m and "//" in m.group("antes")
                    else "")
            if not m or m.group("bucket") not in E.BUCKETS or dono != host.lower() or m.group("depois"):
                achadas.append(s[:80])
        elif t.startswith("data:") and not _DATA_IMAGEM.match(s.strip()):
            achadas.append(s[:40])
        return s
    _andar(obj, olha)
    return achadas


def situacao(config, est: dict | None) -> dict:
    """Para a página do administrador: o disco, e, por bucket, quantos do inventário antigo já estão aqui."""
    por_bucket = {}
    for a in ((est or {}).get("abas", {}).get(T_ARQUIVOS, []) if est else []):
        b = a.get("bucket")
        if b not in E.BUCKETS:
            continue
        d = por_bucket.setdefault(b, {"inventario": 0, "aqui": 0, "faltam": []})
        d["inventario"] += 1
        if existe(config, b, str(a.get("caminho") or "")):
            d["aqui"] += 1
        elif len(d["faltam"]) < 5:
            d["faltam"].append(a.get("caminho"))
    try:
        disco = livre(config)
    except OSError:
        disco = None
    return {"livre_gb": round(disco / 1024 ** 3, 1) if disco is not None else None, "buckets": por_bucket}


T_ARQUIVOS = "arquivos"
