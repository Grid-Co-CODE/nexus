"""A faxina do /tmp do usuário do serviço (28/11/2026): a cota de disco estourou com 6 GB de temporários esquecidos."""
import os
import time

from nexus.casca import faxina_tmp as F


def test_a_faxina_tira_so_o_arquivo_velho_solto(tmp_path):
    agora = time.time()
    velho, novo = tmp_path / "tmpk3j2xab.xlsx", tmp_path / "tmpzz99yyq.xlsx"
    velho.write_bytes(b"x" * 1024)
    novo.write_bytes(b"x")
    os.utime(velho, (agora - 5 * 86400, agora - 5 * 86400))
    pasta = tmp_path / "pasta_velha"                         # pasta fica, mesmo velha (pode ser de alguém em uso)
    pasta.mkdir()
    (pasta / "dentro.bin").write_bytes(b"x")
    os.utime(pasta / "dentro.bin", (agora - 9 * 86400, agora - 9 * 86400))
    r = F.faxinar(tmp_path, agora)
    assert r["arquivos"] == 1 and not velho.exists() and novo.exists() and (pasta / "dentro.bin").exists()


def test_o_resumo_agrupa_pelo_nome_e_conta_os_velhos(tmp_path):
    agora = time.time()
    for i, idade in enumerate((10, 1, 5)):
        p = tmp_path / f"tmpabc{i}defgh.pdf"
        p.write_bytes(b"x" * 100)
        os.utime(p, (agora - idade * 86400, agora - idade * 86400))
    (tmp_path / "conversor_potencias.xlsx").write_bytes(b"x")
    r = F.resumo(tmp_path, agora)
    g = {x["grupo"]: x for x in r["grupos"]}
    assert g["tmp*.pdf"]["arquivos"] == 3 and g["tmp*.pdf"]["velhos"] == 2
    assert "conversor_potencias.xlsx" in g


def test_a_faxina_nao_liga_nos_testes(app):
    app.config["TESTING"] = True
    F.ligar(app)
    assert F._ESTADO["ligada"] is False


def test_o_raio_x_mostra_o_tmp(app, monkeypatch):
    monkeypatch.setattr(F, "resumo", lambda *a, **k: {"pasta": "/tmp", "dias": 3, "ultima": {"quando": "28/11 10:00",
                        "arquivos": 7, "mb": 12.5, "erros": 0}, "grupos": [{"grupo": "tmp*.xlsx", "arquivos": 7, "mb": 12.5, "velhos": 7}]})
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"], s["admin"] = True, True
    html = c.get("/t/base/raio-x?aba=memoria").get_data(as_text=True)
    assert "O /tmp do usuário do serviço" in html and "tmp*.xlsx" in html and "Última faxina: 28/11 10:00, 7 arquivos" in html
