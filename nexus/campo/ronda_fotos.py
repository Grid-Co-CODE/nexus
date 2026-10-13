"""As fotos da ronda, dos anexos da OS no Fracttal, separadas em sujidade, vegetação e as demais (Levi, 06/10/2026: "ao
clicar no botão aparecer os anexos, separando vegetação e sujidade, aparece pequeno e se eu clicar expande!").

O App sobe as fotos da ronda como anexos da tarefa da OS (`subir_fotos`), cada uma com a descrição "<item do checklist>
— <resposta>": "Sujidade dos módulos — 4", "Altura da vegetação — 5", "Sujidade da vala de drenagem — parcial", "Zona
valetas critica" (medido em 06/10 nas OS 15504, 15520 e 14504). A descrição da PRIMEIRA foto o App troca pela capa
("Ronda 2026-10-06 — <usina> · qualidade 100%"), então ela cai nas demais. OS sem anexo existe (15055: as fotos não
subiram); ronda sem OS não tem foto no Fracttal (as fotos dela ficam só no App).

A lista de anexos vem pelo REST (a credencial do OS Creator) com o link do arquivo já assinado; o Nexus baixa e entrega,
o link não sai para o navegador. Cota: 1 pedido por OS aberta, guardado 20 min; o download da imagem não é pedido à API.
Nada vai para o banco.
"""
import hashlib
import os
import threading
import time
import unicodedata
from collections import OrderedDict
from pathlib import Path

from . import nota_fracttal

LISTA_S = 1200               # a lista de anexos de uma OS, 20 min sem pedir de novo (o link assinado vale 24 h)
# as últimas fotos inteiras baixadas (até ~700 kB cada). Eram 40, e a ronda tem 45 a 50: o `preparar` baixava todas
# para as miniaturas e, ao chegar na última, a 1ª (sujidade, vegetação) já tinha saído; ampliar a foto baixava de novo
# do Fracttal a cada clique (13/10/2026, Levi: "na hora de ver expandido demora muito"). Agora há também a cópia em disco.
FOTOS_EM_MEMORIA = 80
TELAS_EM_MEMORIA = 150       # a versão de tela da foto ampliada (~100 a 250 kB)
TELA_PX = 1600               # a ampliada: o lado maior (a do App vem com 1280x1700), em JPEG progressivo
ARQUIVOS_MAX = 6000          # a cópia em disco: passou disso, as mais antigas saem
MINIS_EM_MEMORIA = 600       # as últimas miniaturas (~10 kB cada)
PARALELO = 6                 # downloads ao preparar as miniaturas de uma OS (o arquivo vem do S3, não é pedido à API)
FOTO_MAX = 10 * 1024 * 1024
MINI_PX = 240                # a miniatura: o lado maior (a tela mostra 96 px; 240 fica nítido em tela de alta densidade)
MIME = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
GRUPOS = (("sujidade", "Sujidade dos módulos", ("sujidade dos modulos",)),
          ("vegetacao", "Vegetação", ("altura da vegetacao", "sombreamento por vegetacao")),
          ("outras", "Demais fotos da ronda", ()))
# as demais, por tipo (Levi, 06/10: "deixe recolhido, quando expandir quero que mostre por tipo, o que é piranômetro e
# etc"), pelo começo da descrição que o App escreve (o rótulo do item do checklist)
TIPOS = (("sensores", "Sensores: piranômetros e albedômetro", ("piranometro", "albedometro")),
         ("vala", "Vala de drenagem", ("sujidade da vala",)),
         ("infra", "Infraestrutura: sala, almoxarifado, banheiro, portaria, placas, computador, CFTV e luvas",
          ("computador", "cftv", "entrada da usina", "placas", "sala de o&m", "almoxarifado", "banheiro", "as luvas")),
         ("ocorrencias", "Pragas, dejetos e módulos trincados", ("pragas", "dejeto", "modulo trincado")),
         ("zonas", "Zonas percorridas", ("zona",)),
         ("capa", "Capa da ronda", ("ronda ",)),
         ("resto", "Outras", ()))
_LISTAS: dict = {}
_FOTOS: OrderedDict = OrderedDict()
_MINIS: OrderedDict = OrderedDict()
_TELAS: OrderedDict = OrderedDict()
_PASTA = {"dir": None, "gravados": 0}
_EM_CURSO: dict = {}         # a mesma foto pedida duas vezes ao mesmo tempo baixa uma vez só
_PREPARADAS: dict = {}
_TRAVA = threading.Lock()


class SemFoto(LookupError):
    """O que se pediu não está nos anexos da OS."""


def configurar(pasta) -> None:
    """A pasta da cópia em disco das fotos (a `dados/` do Nexus, `cache_fotos_ronda`): a inteira, a de tela e a
    miniatura de cada foto, pelo arquivo do Fracttal. Sobrevive ao reinício (cada deploy reinicia o Nexus). Sem ela (os
    testes), só a memória. Quem chama é o `nexus.campo.instalar`."""
    _PASTA["dir"] = Path(pasta) if pasta else None


def _id_arquivo(valor) -> str:
    """O arquivo no Fracttal, sem a assinatura do link (que muda a cada leitura da lista): o mesmo arquivo, a mesma
    chave, em disco e no endereço (`v`) que o navegador guarda."""
    return hashlib.sha1(str(valor or "").split("?", 1)[0].encode("utf-8")).hexdigest()[:20]


def _do_disco(nome: str):
    d = _PASTA["dir"]
    if not d:
        return None
    try:
        return (d / nome).read_bytes()
    except OSError:
        return None


def _para_o_disco(nome: str, corpo: bytes) -> None:
    d = _PASTA["dir"]
    if not d or not corpo:
        return
    try:
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / f"{nome}.{threading.get_ident()}.tmp"
        tmp.write_bytes(corpo)
        os.replace(tmp, d / nome)
    except OSError:
        return
    _PASTA["gravados"] += 1
    if _PASTA["gravados"] % 200 == 0:
        _podar(d)


def _podar(d: Path) -> None:
    """Passou de ARQUIVOS_MAX, saem as mais antigas (pela data do arquivo)."""
    try:
        arqs = sorted((p for p in d.iterdir() if p.is_file() and not p.name.endswith(".tmp")),
                      key=lambda p: p.stat().st_mtime)
    except OSError:
        return
    for p in arqs[:max(0, len(arqs) - ARQUIVOS_MAX)]:
        try:
            p.unlink()
        except OSError:
            pass


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def _ext(url) -> str:
    return str(url or "").split("?", 1)[0].rsplit(".", 1)[-1].lower()


def _grupo(desc) -> str:
    d = _norm(desc)
    return next((g for g, _t, prefixos in GRUPOS if any(d.startswith(p) for p in prefixos)), "outras")


def anexos(os_, ler=None) -> list[dict]:
    """As imagens anexadas na OS: [{i, desc, resposta, grupo, valor, mime}], na ordem do Fracttal."""
    chave = str(os_)
    g = _LISTAS.get(chave)
    if g and time.time() - g[0] < LISTA_S:
        return g[1]
    out = []
    for a in nota_fracttal.anexos_da_os(chave, ler):
        valor = str(a.get("value") or "")
        mime = MIME.get(_ext(valor))
        if not valor or not mime:
            continue
        desc = str(a.get("description") or "").strip()
        # a capa ("Ronda <dia> — <usina> · qualidade N%") não tem resposta de checklist
        capa = _norm(desc).startswith("ronda ")
        resposta = desc.split(" — ", 1)[1].strip() if " — " in desc and not capa else ""
        out.append({"i": len(out), "desc": desc, "resposta": resposta, "grupo": _grupo(desc), "valor": valor,
                    "mime": mime})
    _LISTAS[chave] = (time.time(), out)
    return out


def _tipo(desc) -> str:
    d = _norm(desc)
    return next((k for k, _t, prefixos in TIPOS if any(d.startswith(p) for p in prefixos)), "resto")


# a legenda cabe em 96 px: o nome curto de cada item (o completo vai no título e na foto ampliada)
CURTO = (("piranometro ghi", "GHI"), ("piranometro ipoa", "IPOA"), ("albedometro", "Albedômetro"),
         ("sujidade da vala", "Vala"), ("entrada da usina", "Portaria"), ("placas de sinalizacao", "Placas"),
         ("as luvas", "Luvas"), ("sala de o&m", "Sala de O&M"), ("dejeto", "Dejeto"), ("modulo trincado", "Trincado"),
         ("ronda ", "Capa"))


def _rotulo(desc) -> str:
    """O nome curto do item, para a legenda da miniatura: "Piranômetro GHI (estação solarimétrica) — limpo" -> "GHI";
    sem nome curto, o rótulo até o " — " ("Zona portoes", "Almoxarifado")."""
    d = _norm(desc)
    return next((c for p, c in CURTO if d.startswith(p)), None) or desc.split(" — ", 1)[0].split(" (", 1)[0].strip()[:28]


def grupos(os_, ler=None) -> list[dict]:
    """Sujidade, vegetação e as demais, cada uma com as suas fotos (sem o link, que fica no servidor). As demais vêm
    também separadas por tipo (`tipos`)."""
    fotos = [dict({k: f[k] for k in ("i", "desc", "resposta", "grupo")}, rotulo=_rotulo(f["desc"]), tipo=_tipo(f["desc"]),
                  v=_id_arquivo(f["valor"])[:10])
             for f in anexos(os_, ler)]
    out = [{"chave": g, "titulo": t, "fotos": [f for f in fotos if f["grupo"] == g]} for g, t, _p in GRUPOS]
    out[2]["tipos"] = [{"chave": k, "titulo": t, "fotos": [f for f in out[2]["fotos"] if f["tipo"] == k]}
                       for k, t, _p in TIPOS]
    return out


def _baixar(url: str) -> bytes:
    import requests
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    if len(r.content) > FOTO_MAX:
        raise SemFoto("a foto no Fracttal é grande demais")
    return r.content


def _guardado(cache: OrderedDict, limite: int, chave, fazer):
    """O que já está em memória volta na hora; o que outro pedido está fazendo, espera por ele em vez de baixar de
    novo (a grade pede as miniaturas em paralelo enquanto o `preparar` também as faz)."""
    with _TRAVA:
        if chave in cache:
            cache.move_to_end(chave)
            return cache[chave]
        # a chave de "em andamento" leva a cache: a miniatura e a foto inteira da mesma OS e índice são duas coisas (com
        # a mesma chave, a miniatura esperava por si mesma 60 s ao pedir a foto inteira)
        em_curso = (id(cache), chave)
        ev = _EM_CURSO.get(em_curso)
        dono = ev is None
        if dono:
            ev = _EM_CURSO[em_curso] = threading.Event()
    if not dono:
        ev.wait(60)
        with _TRAVA:
            if chave in cache:
                return cache[chave]
    try:
        item = fazer()
        with _TRAVA:
            cache[chave] = item
            while len(cache) > limite:
                cache.popitem(last=False)
        return item
    finally:
        if dono:
            with _TRAVA:
                _EM_CURSO.pop(em_curso, None)
            ev.set()


def _item(os_, i: int, ler=None) -> dict:
    lista = anexos(os_, ler)
    if not 0 <= int(i) < len(lista):
        raise SemFoto(f"a OS {os_} não tem a foto {i}")
    return lista[int(i)]


def foto(os_, i: int, ler=None) -> tuple[bytes, str]:
    """(bytes, mime) da i-ésima imagem da OS, como está no Fracttal. As últimas ficam em memória e todas em disco:
    abrir de novo não baixa de novo, nem depois de reiniciar."""
    def fazer():
        it = _item(os_, i, ler)
        nome = f"{_id_arquivo(it['valor'])}.{_ext(it['valor']) or 'jpg'}"
        corpo = _do_disco(nome)
        if corpo is None:
            corpo = _baixar(it["valor"])
            _para_o_disco(nome, corpo)
        return corpo, it["mime"]
    return _guardado(_FOTOS, FOTOS_EM_MEMORIA, (str(os_), int(i)), fazer)


def _reduzir(corpo: bytes, mime: str, px: int = MINI_PX, qualidade: int = 80, progressivo: bool = False):
    try:
        import io

        from PIL import Image, ImageOps
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(corpo))).convert("RGB")
        im.thumbnail((px, px))
        saida = io.BytesIO()
        im.save(saida, "JPEG", quality=qualidade, optimize=True, progressive=progressivo)
        return saida.getvalue(), "image/jpeg"
    except Exception:       # noqa: BLE001 — sem Pillow ou imagem que ele não abre: vai a foto inteira
        return corpo, mime


def _derivada(cache: OrderedDict, limite: int, sufixo: str, os_, i: int, ler, so_se_menor=False,
              **reducao) -> tuple[bytes, str]:
    """A miniatura ou a de tela: da memória, do disco ou reduzida da inteira (e guardada nos dois). `so_se_menor`: a de
    tela de uma foto que já chega pequena sairia maior que a inteira; aí vai a inteira."""
    def fazer():
        it = _item(os_, i, ler)
        nome = f"{_id_arquivo(it['valor'])}{sufixo}.jpg"
        corpo = _do_disco(nome)
        if corpo is not None:
            return corpo, "image/jpeg"
        inteira, mime = foto(os_, i, ler)
        corpo, mime_r = _reduzir(inteira, mime, **reducao)
        if mime_r == "image/jpeg" and (not so_se_menor or len(corpo) < len(inteira)):
            _para_o_disco(nome, corpo)
            return corpo, mime_r
        return inteira, mime        # sem o Pillow, ou a de tela não ficou menor: vai a inteira
    return _guardado(cache, limite, (str(os_), int(i)), fazer)


def miniatura(os_, i: int, ler=None) -> tuple[bytes, str]:
    """A foto reduzida para a grade (a foto do App vem com 1280x1700: medido em 06/10, 182 a 690 kB a inteira e 7 a
    14 kB a miniatura). Sem o Pillow, a foto inteira."""
    return _derivada(_MINIS, MINIS_EM_MEMORIA, "_m", os_, i, ler)


def tela(os_, i: int, ler=None) -> tuple[bytes, str]:
    """A foto da caixa ampliada: o lado maior em TELA_PX, JPEG progressivo (aparece logo e vai firmando), menor que a
    inteira. A inteira continua no endereço com ?original=1."""
    return _derivada(_TELAS, TELAS_EM_MEMORIA, "_t", os_, i, ler, so_se_menor=True, px=TELA_PX, qualidade=82,
                     progressivo=True)


def preparar(os_, em_segundo_plano=None):
    """Faz as miniaturas da OS em paralelo logo que a grade é pedida: sem isto, a 1ª abertura de uma OS com 39 fotos
    levava ~10 s chegando de 4 em 4. Uma vez por OS a cada 20 min."""
    chave = str(os_)
    with _TRAVA:
        if time.time() - _PREPARADAS.get(chave, 0) < LISTA_S:
            return
        _PREPARADAS[chave] = time.time()

    def rodar():
        from concurrent.futures import ThreadPoolExecutor

        def uma(i):
            try:
                miniatura(chave, i)
            except Exception:       # noqa: BLE001 — a grade pede de novo a que faltar
                pass

        def ampliada(i):
            try:
                tela(chave, i)
            except Exception:       # noqa: BLE001 — a caixa pede de novo a que faltar
                pass
        with ThreadPoolExecutor(PARALELO) as ex:
            ordem = [f["i"] for f in sorted(anexos(chave), key=lambda f: f["grupo"] == "outras")]
            list(ex.map(uma, ordem))
            # depois das miniaturas, a de tela de cada uma: ampliar não espera o Fracttal (13/10/2026)
            list(ex.map(ampliada, ordem))
    (em_segundo_plano or (lambda f: threading.Thread(target=f, daemon=True, name="nexus-ronda-fotos").start()))(rodar)


def limpar():
    _LISTAS.clear()
    with _TRAVA:
        _FOTOS.clear()
        _MINIS.clear()
        _TELAS.clear()
        _PREPARADAS.clear()
