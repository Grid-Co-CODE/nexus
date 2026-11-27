"""O teto em tamanho da cópia das fotos de ronda (27/11/2026): ela chegou a 1 GB e o serviço do Nexus bateu na cota de
disco do usuário dele no servidor (Errno 122), travando a geração da semana do PCM. É só cópia: a foto que sai é baixada
de novo do Fracttal."""
import os
import time

from nexus.campo import ronda_fotos as R


def test_a_poda_corta_pelo_tamanho_e_tira_as_mais_antigas(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "MB_MAX", 1)                     # 1 MB de teto
    agora = time.time()
    for i in range(5):                                       # 5 fotos de 400 kB: 2 MB
        p = tmp_path / f"foto{i}.jpg"
        p.write_bytes(b"x" * 400 * 1024)
        os.utime(p, (agora - 100 + i, agora - 100 + i))     # a foto0 é a mais antiga
    (tmp_path / "x.123.tmp").write_bytes(b"x" * 2 * 2**20)  # a que ainda está sendo gravada não conta nem sai
    R._podar(tmp_path)
    ficaram = sorted(p.name for p in tmp_path.iterdir())
    assert ficaram == ["foto3.jpg", "foto4.jpg", "x.123.tmp"]


def test_a_poda_pela_quantidade_continua(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "ARQUIVOS_MAX", 2)
    for i in range(4):
        (tmp_path / f"f{i}.jpg").write_bytes(b"x")
        os.utime(tmp_path / f"f{i}.jpg", (1000 + i, 1000 + i))
    R._podar(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["f2.jpg", "f3.jpg"]
