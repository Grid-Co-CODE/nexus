"""As fotos do inventário do almoxarifado que o App envia ao Nexus (PCM → Almoxarifado → Curadoria; 30/10/2026).

Levi, 30/10/2026 (itens 2 e 3 das melhorias do Almoxarifado): na peça achada fora do catálogo, o fabricante, o modelo e o
número de série, cada um com a foto da placa ou da etiqueta, e "foto obrigatória para o que vai à curadoria". A "Foto" da
peça já ia no livro das contagens desde 27/10, mas a curadoria mostrava "sem foto": faltava a rota que recebe. Desenho:
`docs/superpowers/specs/2026-10-30-almoxarifado-melhorias-design.md`, seção "2 e 3"; o lado do App é a seção 2 da revisão de
30/10/2026 da proposta das contagens (`_propostas/inventario-contagens/REVISAO-2026-10-30.md`, na pasta de documentos do App).

**Uma rota só recebe todas as fotos do inventário**: a "Foto" da peça (coluna 12 do livro) e as dos dados (coluna 18,
"Fotos dos dados"). `POST <raiz>/t/pcm/pecas/inventario/foto`, multipart com `chave` (a MESMA que o App pôs na coluna), `ts`
(segundos Unix), `assinatura` e o arquivo em `foto`. Sem sessão: vale a assinatura (a rota está em `auth.ROTAS_PUBLICAS`, e só
por POST). No molde do extintor (`nexus/hseq/fotos.receber`): HMAC-SHA256 com uma chave DERIVADA da NEXUS_PESSOA_HMAC (outro
rótulo, `ROTULO_CHAVE`, para a assinatura de uma rota não valer na outra), janela de 15 min no `ts` e até 8 MB. A validação é
a própria: a chave é texto opaco do App (até 200 caracteres, sem caractere de controle), sem o código em maiúsculas nem o
`dia` do extintor, e **a mesma chave reenviada substitui** (a fila offline do App reenvia; o técnico pode refazer a foto). A
chave nunca vira caminho: o arquivo é `curadoria.nome_da_foto(chave)` (o SHA-1).

Guarda em `<NEXUS_DADOS>/almox_inventario/fotos/<nome>.jpg` (regravada em JPEG de até 1600 px) e a miniatura de 160 px em
`mini/<nome>.jpg`, feita no recebimento: a curadoria mostra as miniaturas de todos os achados, e refazê-las a cada abertura
leria cada foto inteira (o caso dos extintores, 19/10/2026, `hseq/fotos.mini`). A foto é SEMPRE decodificada e regravada,
mesmo a pequena: sai sem os metadados do celular (a localização do GPS no EXIF) e já na orientação certa. Nunca no banco
(a API abre a quem quiser) nem no git. Quem vê é a rota da curadoria, só com login e só a quem `pode_programar`.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import threading
import time
import unicodedata
from pathlib import Path

from ...hseq import fotos as HF
from . import curadoria as CU

ROTULO_CHAVE = b"nexus:pcm:fotos-inventario"   # deriva a chave das fotos do inventário da NEXUS_PESSOA_HMAC
JANELA_S = 15 * 60
TAMANHO_MAX = 8 * 1024 * 1024
LADO_MAX, QUALIDADE = 1600, 82
MINI_PX, MINI_QUALIDADE = 160, 75             # a miniatura do cartão da curadoria (a tela mostra até 96 px; 160 fica nítido)
CHAVE_MAX = 200


def chave(cfg) -> bytes | None:
    """A chave das assinaturas: HMAC-SHA256(NEXUS_PESSOA_HMAC, ROTULO_CHAVE). Sem a NEXUS_PESSOA_HMAC, None (a rota recusa)."""
    base = str(cfg.get("NEXUS_PESSOA_HMAC") or "").strip()
    return hmac.new(base.encode(), ROTULO_CHAVE, hashlib.sha256).digest() if base else None


def assinatura(k: bytes, chave_foto: str, ts, dados: bytes) -> str:
    """HMAC-SHA256 de "chave|ts|sha256 do arquivo", em hex (o App calcula igual, com a mesma chave derivada)."""
    msg = f"{chave_foto}|{int(ts)}|{hashlib.sha256(dados).hexdigest()}".encode()
    return hmac.new(k, msg, hashlib.sha256).hexdigest()


def _chave_valida(c: str) -> bool:
    """Não vazia, até `CHAVE_MAX` caracteres e sem caractere de controle (C0, DEL, C1: a quebra de linha de uma chave colada
    no livro não é a mesma chave) nem metade de par substituto (não se codifica para a assinatura)."""
    return bool(c.strip()) and len(c) <= CHAVE_MAX and not any(unicodedata.category(ch) in ("Cc", "Cs") for ch in c)


def _gravar(arq: Path, dados: bytes) -> None:
    """Inteiro ou nada: escreve ao lado e troca. O nome do parcial leva a thread, para dois envios da mesma chave ao mesmo
    tempo (a fila do App reenviando) não escreverem no mesmo arquivo."""
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_name(f"{arq.name}.{threading.get_ident()}.parcial")
    try:
        tmp.write_bytes(dados)
        tmp.replace(arq)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _regravar(dados: bytes) -> tuple[bytes, bytes] | None:
    """(a foto de até 1600 px, a miniatura de 160 px), as duas em JPEG, ou None se não for imagem. O JPEG grande é decodificado
    já reduzido (`draft`, a escala de 1/2, 1/4 ou 1/8 que ainda cobre 1600 px): a foto de 12 MP do celular cabe em 4x menos
    memória. A orientação do EXIF é aplicada antes de o EXIF sair (a foto deitada do celular não fica de lado na tela)."""
    try:
        from PIL import Image, ImageOps
        im = Image.open(io.BytesIO(dados))
        if im.format == "JPEG":
            im.draft("RGB", (LADO_MAX, LADO_MAX))
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((LADO_MAX, LADO_MAX))
        inteira = io.BytesIO()
        im.save(inteira, "JPEG", quality=QUALIDADE, optimize=True)
        im.thumbnail((MINI_PX, MINI_PX))
        mini_ = io.BytesIO()
        im.save(mini_, "JPEG", quality=MINI_QUALIDADE, optimize=True)
        return inteira.getvalue(), mini_.getvalue()
    except Exception:       # noqa: BLE001 — não é imagem (ou está cortada)
        return None


def receber(cfg, chave_foto, ts, assinatura_recebida, dados: bytes, agora=None) -> tuple[int, str]:
    """(status HTTP, mensagem): 200 guardada; 400 formato (chave, ts, tamanho, não é imagem); 401 assinatura ou janela; 503
    o Nexus sem a chave (ou sem a pasta de dados, ou o disco que não gravou). Confere tudo antes de gravar."""
    k = chave(cfg)
    destino = CU._pasta_fotos(cfg)
    if not k or destino is None:
        return 503, "recebimento das fotos do inventário desligado neste Nexus (sem NEXUS_PESSOA_HMAC)"
    chave_foto = "" if chave_foto is None else str(chave_foto)
    if not _chave_valida(chave_foto):
        return 400, f"chave da foto vazia, com mais de {CHAVE_MAX} caracteres ou com caractere de controle"
    try:
        ts = int(ts)
    except (TypeError, ValueError):
        return 400, "hora (ts) fora do formato"
    if abs((agora or time.time()) - ts) > JANELA_S:
        return 401, "hora do envio fora da janela de 15 min"
    if not dados or len(dados) > TAMANHO_MAX:
        return 400, "foto vazia ou maior que 8 MB"
    # em bytes: o `compare_digest` de texto levanta TypeError com letra fora do ASCII (seria um 500, não um 401)
    recebida = str(assinatura_recebida or "").strip().lower().encode("utf-8", "replace")
    if not hmac.compare_digest(assinatura(k, chave_foto, ts, dados).encode(), recebida):
        return 401, "assinatura não confere"
    fotos = _regravar(dados)
    if fotos is None:
        return 400, "o arquivo não é uma imagem"
    nome = CU.nome_da_foto(chave_foto)
    try:
        _gravar(destino / f"{nome}.jpg", fotos[0])
        _gravar(destino / "mini" / f"{nome}.jpg", fotos[1])     # depois da inteira: a miniatura mais nova que ela vale
    except OSError:
        return 503, "não consegui guardar a foto agora: tente de novo"
    return 200, "foto guardada"


def mini(cfg, foto_id: str) -> bytes | None:
    """A miniatura (160 px) da foto, ou None. A de `mini/` vale se não for mais velha que a inteira; sem ela (a foto que
    chegou antes desta rota, a miniatura apagada), é refeita da inteira uma vez e guardada. O nome tem de ser o de
    `curadoria.nome_da_foto`: nada de caminho."""
    pasta = CU._pasta_fotos(cfg)
    foto_id = str(foto_id or "")
    if pasta is None or not CU._FOTO_ID.fullmatch(foto_id):
        return None
    arq, copia = pasta / f"{foto_id}.jpg", pasta / "mini" / f"{foto_id}.jpg"
    try:
        if copia.stat().st_mtime_ns >= arq.stat().st_mtime_ns:
            return copia.read_bytes()
    except OSError:         # sem a miniatura (ou sem a foto): segue
        pass
    dados = CU.foto(cfg, foto_id)
    red = HF.reduzir(dados, MINI_PX, MINI_QUALIDADE) if dados else None
    if not red:
        return None
    try:
        _gravar(copia, red[0])
    except OSError:         # sem conseguir guardar, serve a reduzida do mesmo jeito
        pass
    return red[0]
