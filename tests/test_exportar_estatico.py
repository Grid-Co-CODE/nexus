"""A vitrine do GitHub Pages é pública: não pode levar login, cadastro nem dado de pessoa."""
import re

from ferramentas.exportar_estatico import PROIBIDOS, exportar


def test_vitrine_sem_login_sem_dado_e_com_links_do_pages(tmp_path):
    n = exportar(tmp_path, "/nexus")
    assert n == 1 + sum(1 for _ in tmp_path.glob("t/*/*/index.html"))
    for pagina in tmp_path.rglob("*.html"):
        html = pagina.read_text(encoding="utf-8")
        assert 'class="cadeira"' not in html and 'href="/sair"' not in html, pagina
        assert 'name="senha"' not in html, pagina
        for nome, padrao in PROIBIDOS.items():
            assert not padrao.search(html), (nome, pagina)
        # Todo link interno aponta para o caminho do Pages; nada sobra na raiz do domínio.
        assert not re.search(r'(href|src|data-primeira)="/(?!nexus/)', html), pagina
    # O CSS do cadastro não vai: nenhuma tela dele sai com conteúdo próprio.
    assert not (tmp_path / "static" / "cadastro.css").exists()
    assert (tmp_path / "static" / "nexus.css").exists()


def test_exportacao_aborta_se_aparecer_email(tmp_path, monkeypatch):
    import ferramentas.exportar_estatico as exp

    original = exp._ajustar
    monkeypatch.setattr(exp, "_ajustar", lambda html, base: original(html, base) + "fulano@exemplo.com")
    try:
        exportar(tmp_path, "/nexus")
    except SystemExit as erro:
        assert "e-mail" in str(erro)
    else:
        raise AssertionError("a exportação devia ter abortado")
