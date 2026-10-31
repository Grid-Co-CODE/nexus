"""As fotos do inventário que o App envia ao Nexus (30/10/2026, itens 2 e 3 das melhorias do Almoxarifado). Desenho:
docs/superpowers/specs/2026-10-30-almoxarifado-melhorias-design.md, seção "2 e 3". Uma rota só recebe a "Foto" da peça e as
dos dados (fabricante, modelo, número de série): `POST /t/pcm/pecas/inventario/foto`, sem sessão, assinada por HMAC com a
chave derivada da NEXUS_PESSOA_HMAC (o molde do extintor, `nexus/hseq/fotos.py`). O contrato do lado do App é a seção 2 da
revisão de 30/10/2026 da proposta das contagens. As fotos vão para uma pasta de dados de mentira (`tmp_path`)."""
import hashlib
import hmac
import io
import time

import pytest
from PIL import Image

from nexus.auth import ROTAS_PUBLICAS
from nexus.pcm.inventario import curadoria as CU

URL = "/t/pcm/pecas/inventario/foto"
VER = "/t/pcm/pecas/inventario/curadoria/foto"
SEGREDO = "segredo-de-teste-das-fotos"


@pytest.fixture
def fotos(app, tmp_path):
    """O Nexus com a chave das fotos e a pasta de dados de mentira; devolve a pasta onde as fotos ficam."""
    app.config.update(NEXUS_DADOS=str(tmp_path / "dados"), NEXUS_PESSOA_HMAC=SEGREDO, TESTING=True)
    return tmp_path / "dados" / "almox_inventario" / "fotos"


def _jpeg(tamanho=(2400, 1800), cor=(40, 160, 90)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", tamanho, cor).save(buf, "JPEG")
    return buf.getvalue()


def _enviar(app, chave="foto-abc", ts=None, dados=None, assinatura=None, cliente=None):
    """O que o App faz: o multipart com a chave, a hora, a assinatura e o arquivo, sem sessão nenhuma."""
    from nexus.pcm.inventario import fotos_app as FA
    dados = _jpeg() if dados is None else dados
    ts = int(time.time()) if ts is None else ts
    sig = assinatura or FA.assinatura(FA.chave(app.config), chave, ts, dados)
    return (cliente or app.test_client()).post(
        URL, data={"chave": chave, "ts": str(ts), "assinatura": sig, "foto": (io.BytesIO(dados), "f.jpg")},
        content_type="multipart/form-data")


def _arquivos(pasta):
    """Tudo o que existe debaixo da pasta (caminhos relativos), para provar que nada mais foi gravado."""
    return sorted(str(p.relative_to(pasta)).replace("\\", "/") for p in pasta.rglob("*") if p.is_file()) \
        if pasta.exists() else []


def _cor(caminho) -> tuple:
    return Image.open(caminho).convert("RGB").getpixel((5, 5))


def test_a_assinatura_e_a_do_contrato_com_o_app(fotos, app):
    """A chave e a assinatura são as da proposta do App (seção 2): a chave é HMAC-SHA256(NEXUS_PESSOA_HMAC,
    "nexus:pcm:fotos-inventario") e a assinatura, HMAC-SHA256(chave, "<chave>|<ts>|<sha256 hex do arquivo>") em hex."""
    from nexus.pcm.inventario import fotos_app as FA
    assert FA.ROTULO_CHAVE == b"nexus:pcm:fotos-inventario"
    k = hmac.new(SEGREDO.encode(), b"nexus:pcm:fotos-inventario", hashlib.sha256).digest()
    assert FA.chave(app.config) == k
    dados = b"qualquer coisa"
    esperada = hmac.new(k, f"foto-abc|1761800000|{hashlib.sha256(dados).hexdigest()}".encode(), hashlib.sha256).hexdigest()
    assert FA.assinatura(k, "foto-abc", 1761800000, dados) == esperada
    assert FA.assinatura(k, "foto-abc", "1761800000", dados) == esperada              # o ts do formulário chega como texto
    # outra chave derivada que a do extintor: a assinatura de uma não vale na outra rota
    from nexus.hseq import fotos as HF
    assert HF.chave(app.config) != k


def test_recebe_e_guarda(fotos, app):
    r = _enviar(app)
    assert r.status_code == 200 and r.get_json()["ok"] is True
    nome = CU.nome_da_foto("foto-abc")
    assert _arquivos(fotos) == [f"{nome}.jpg", f"mini/{nome}.jpg"]                   # nada pela metade, nada a mais
    assert max(Image.open(fotos / f"{nome}.jpg").size) == 1600                         # reduzida a 1600 px
    assert max(Image.open(fotos / "mini" / f"{nome}.jpg").size) == 160                 # e a miniatura de 160 px
    assert CU._tem_foto(app.config, "foto-abc") and CU.foto(app.config, nome).startswith(b"\xff\xd8\xff")
    # a pequena que já cabe também é regravada (sem os metadados do celular) e ganha a miniatura
    assert _enviar(app, chave="foto-pequena", dados=_jpeg((300, 200))).status_code == 200
    assert Image.open(fotos / f"{CU.nome_da_foto('foto-pequena')}.jpg").size == (300, 200)
    assert max(Image.open(fotos / "mini" / f"{CU.nome_da_foto('foto-pequena')}.jpg").size) == 160


def test_a_foto_sai_sem_os_metadados_do_celular_e_em_pe(fotos, app):
    """A foto é sempre regravada: o EXIF do celular (a marca, a localização) não fica no disco, e a orientação dele é aplicada
    antes (a foto tirada com o celular deitado não aparece de lado na curadoria)."""
    exif = Image.Exif()
    exif[0x0112] = 6                       # Orientation: girar 90° para ficar em pé
    exif[0x010F] = "Celular de teste"      # Make
    buf = io.BytesIO()
    Image.new("RGB", (300, 200), (40, 160, 90)).save(buf, "JPEG", exif=exif.tobytes())
    assert _enviar(app, dados=buf.getvalue()).status_code == 200
    guardada = Image.open(fotos / f"{CU.nome_da_foto('foto-abc')}.jpg")
    assert guardada.size == (200, 300) and 0x010F not in guardada.getexif() and 0x0112 not in guardada.getexif()


def test_mesma_chave_substitui(fotos, app):
    """A fila offline do App reenvia; o técnico pode refazer a foto: a mesma chave reenviada substitui a guardada."""
    assert _enviar(app, dados=_jpeg(cor=(200, 20, 20))).status_code == 200
    nome = CU.nome_da_foto("foto-abc")
    assert _cor(fotos / f"{nome}.jpg")[0] > 150
    assert _enviar(app, dados=_jpeg(cor=(20, 20, 200))).status_code == 200
    assert _cor(fotos / f"{nome}.jpg")[2] > 150 and _cor(fotos / f"{nome}.jpg")[0] < 100
    assert _cor(fotos / "mini" / f"{nome}.jpg")[2] > 150                                # a miniatura também
    assert _arquivos(fotos) == [f"{nome}.jpg", f"mini/{nome}.jpg"]


def test_assinatura_errada_401(fotos, app):
    from nexus.pcm.inventario import fotos_app as FA
    assert _enviar(app, assinatura="0" * 64).status_code == 401
    ts, dados = int(time.time()), _jpeg()
    k = FA.chave(app.config)
    assert _enviar(app, ts=ts, dados=dados, assinatura=FA.assinatura(k, "outra-chave", ts, dados)).status_code == 401
    assert _enviar(app, ts=ts, dados=dados, assinatura=FA.assinatura(k, "foto-abc", ts, b"outro arquivo")).status_code == 401
    assert _enviar(app, ts=ts, dados=dados, assinatura=FA.assinatura(k, "foto-abc", ts - 1, dados)).status_code == 401
    # a do extintor (outra chave derivada) não vale aqui
    from nexus.hseq import fotos as HF
    sig_ext = hmac.new(HF.chave(app.config), f"foto-abc|{ts}|{hashlib.sha256(dados).hexdigest()}".encode(),
                       hashlib.sha256).hexdigest()
    assert _enviar(app, ts=ts, dados=dados, assinatura=sig_ext).status_code == 401
    # assinatura com letra fora do ASCII não derruba a rota (o `compare_digest` de texto não aceita)
    assert _enviar(app, ts=ts, dados=dados, assinatura="é" * 64).status_code == 401
    assert _arquivos(fotos) == []


def test_fora_da_janela_401(fotos, app):
    agora = int(time.time())
    assert _enviar(app, ts=agora - 16 * 60).status_code == 401
    assert _enviar(app, ts=agora + 16 * 60).status_code == 401
    assert "janela" in _enviar(app, ts=agora - 16 * 60).get_json()["mensagem"]
    assert _arquivos(fotos) == []
    assert _enviar(app, ts=agora - 14 * 60).status_code == 200                         # dentro dos 15 min, para os dois lados
    assert _enviar(app, ts=agora + 14 * 60).status_code == 200
    assert _enviar(app, ts="ontem", assinatura="0" * 64).status_code == 400           # ts que não é número é formato


def test_nao_imagem_400(fotos, app):
    r = _enviar(app, dados=b"isto nao e imagem")
    assert r.status_code == 400 and "imagem" in r.get_json()["mensagem"]
    assert _enviar(app, dados=_jpeg()[:200]).status_code == 400                       # o JPEG cortado também não é imagem
    assert _arquivos(fotos) == []


def test_maior_que_8mb_400(fotos, app):
    from nexus.pcm.inventario import fotos_app as FA
    grande = _jpeg() + b"\0" * (8 * 1024 * 1024)
    r = _enviar(app, dados=grande)
    assert r.status_code == 400 and "8 MB" in r.get_json()["mensagem"]
    assert _arquivos(fotos) == []
    assert FA.receber(app.config, "foto-abc", int(time.time()), "x", b"")[0] == 400     # vazia também


def test_chave_vazia_ou_longa_400(fotos, app):
    from nexus.pcm.inventario import fotos_app as FA
    for chave in ("", "   ", "x" * 201):
        assert _enviar(app, chave=chave).status_code == 400, chave
    agora, dados = int(time.time()), _jpeg((40, 40))
    k = FA.chave(app.config)
    for chave in ("a\nb", "a\x00b", "a\tb", "a\x7fb", "a\x85b"):                       # caractere de controle (C0, DEL, C1)
        assert FA.receber(app.config, chave, agora, FA.assinatura(k, chave, agora, dados), dados, agora=agora)[0] == 400, \
            repr(chave)
    assert _arquivos(fotos) == []
    assert _enviar(app, chave="x" * 200).status_code == 200                            # 200 cabe
    assert _enviar(app, chave="fabricante 4f2c-ç").status_code == 200                  # espaço e acento não são controle


def test_chave_com_barras_nao_vira_caminho(fotos, app, tmp_path):
    """A chave é texto do App: o arquivo é sempre o SHA-1 dela dentro da pasta das fotos, nunca um caminho."""
    for chave in ("../x", "..\\..\\x", "/etc/passwd", "C:\\x.jpg", "mini/../../x"):
        assert _enviar(app, chave=chave).status_code == 200, chave
    nomes = [CU.nome_da_foto(c) for c in ("../x", "..\\..\\x", "/etc/passwd", "C:\\x.jpg", "mini/../../x")]
    assert _arquivos(fotos) == sorted([f"{n}.jpg" for n in nomes] + [f"mini/{n}.jpg" for n in nomes])
    assert _arquivos(tmp_path / "dados") == sorted(f"almox_inventario/fotos/{a}" for a in _arquivos(fotos))
    assert not (tmp_path / "x").exists() and not (fotos.parent / "x").exists()


def test_sem_hmac_503(fotos, app):
    app.config["NEXUS_PESSOA_HMAC"] = ""
    r = app.test_client().post(URL, data={"chave": "foto-abc"})
    assert r.status_code == 503 and "desligado" in r.get_json()["mensagem"]
    assert _arquivos(fotos) == []


def test_sem_pasta_de_dados_503(app):
    """O teste sem pasta de dados própria não grava a de verdade: a rota recusa como desligada."""
    from nexus.pcm.inventario import fotos_app as FA
    app.config.update(NEXUS_PESSOA_HMAC=SEGREDO, TESTING=True, NEXUS_DADOS="")
    agora, dados = int(time.time()), _jpeg((40, 40))
    sig = FA.assinatura(FA.chave(app.config), "foto-abc", agora, dados)
    assert FA.receber(app.config, "foto-abc", agora, sig, dados)[0] == 503


def test_rota_publica_so_post(fotos, app):
    """Pública só para quem assina, e só POST: GET não serve foto nenhuma (sem login, vai ao Entrar)."""
    assert "torre_pcm.inventario_foto_receber" in ROTAS_PUBLICAS
    regras = [r for r in app.url_map.iter_rules() if r.endpoint == "torre_pcm.inventario_foto_receber"]
    assert [r.rule for r in regras] == [URL] and "GET" not in regras[0].methods
    anon = app.test_client()
    r = anon.get(URL)
    assert r.status_code == 302 and "/entrar" in r.headers["Location"]
    # a rota de ver continua atrás do login
    assert _enviar(app).status_code == 200
    r = anon.get(f"{VER}/{CU.nome_da_foto('foto-abc')}.jpg?mini=1")
    assert r.status_code == 302 and "/entrar" in r.headers["Location"]


def test_mini_so_para_quem_pode_programar(fotos, app, logado, monkeypatch):
    from nexus.pcm import telas
    assert _enviar(app).status_code == 200
    nome = CU.nome_da_foto("foto-abc")
    r = logado.get(f"{VER}/{nome}.jpg?mini=1")                     # o administrador pode programar
    assert r.status_code == 200 and r.mimetype == "image/jpeg" and max(Image.open(io.BytesIO(r.data)).size) == 160
    r = logado.get(f"{VER}/{nome}.jpg")                            # sem o mini, a inteira
    assert r.status_code == 200 and max(Image.open(io.BytesIO(r.data)).size) == 1600
    assert logado.get(f"{VER}/{'0' * 24}.jpg?mini=1").status_code == 404
    # a miniatura que se perdeu (ou a foto que chegou sem ela) é refeita da inteira, uma vez
    (fotos / "mini" / f"{nome}.jpg").unlink()
    r = logado.get(f"{VER}/{nome}.jpg?mini=1")
    assert r.status_code == 200 and max(Image.open(io.BytesIO(r.data)).size) == 160
    assert (fotos / "mini" / f"{nome}.jpg").is_file()
    # a inteira mais nova que a miniatura (trocada sem passar pela rota): a miniatura velha não vale, é refeita
    import os
    Image.new("RGB", (800, 600), (20, 20, 200)).save(fotos / f"{nome}.jpg", "JPEG")
    futuro = time.time() + 60
    os.utime(fotos / f"{nome}.jpg", (futuro, futuro))
    r = logado.get(f"{VER}/{nome}.jpg?mini=1")
    assert r.status_code == 200 and Image.open(io.BytesIO(r.data)).convert("RGB").getpixel((5, 5))[2] > 150
    monkeypatch.setattr(telas, "pode_programar", lambda: False)
    assert logado.get(f"{VER}/{nome}.jpg?mini=1").status_code == 403
    assert logado.get(f"{VER}/{nome}.jpg").status_code == 403
