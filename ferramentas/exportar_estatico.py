"""Exporta a casca do Nexus como site estático, para o GitHub Pages.

Uso:  python ferramentas/exportar_estatico.py [pasta_saida] [--base /nexus]

O Pages não roda Flask, então o que vai para lá é uma VITRINE da casca: o Início, o menu por torre e toda
tela no placeholder "em construção". Fica de fora, de propósito:
- o login (a vitrine é pública; não há o que proteger nela);
- a troca de cadeira (é POST na sessão) e o botão Sair;
- qualquer tela com dado: até as telas do cadastro saem no placeholder genérico. O exportador nunca chama
  as views das torres, só o template tela.html, então nem o ensaio local do cadastro nem a chave de cifra
  são lidos. A varredura no fim derruba a exportação se aparecer e-mail, CPF ou telefone no HTML.
"""
import argparse
import re
import secrets
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from flask import render_template  # noqa: E402

from nexus import create_app  # noqa: E402

# Padrões que não podem aparecer na vitrine pública.
PROIBIDOS = {
    "e-mail": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}"),
    "CPF": re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
    "telefone": re.compile(r"\(?\b\d{2}\)?\s?9\d{4}-?\d{4}\b"),
}


def _app():
    # Chaves descartáveis: a exportação não usa sessão real, e nada do .env da máquina entra no site.
    app = create_app({"NEXUS_SECRET_KEY": secrets.token_hex(16), "NEXUS_SENHA_ADMIN": secrets.token_hex(16)})
    app.config.update(NEXUS_CHAVE_CADASTRO=None, NEXUS_ARMAZEM_LOCAL=None)
    return app


def _ajustar(html: str, base: str) -> str:
    """Links absolutos do app viram links do Pages; some o que depende de servidor."""
    html = re.sub(r'<form class="cadeira".*?</form>', "", html, flags=re.S)
    html = re.sub(r'<a class="[^"]*\bsair\b[^"]*".*?</a>', "", html, flags=re.S)
    # O convite a escolher cadeira aponta para um seletor que a vitrine não tem.
    html = re.sub(r'<p class="aviso">Escolha uma cadeira.*?</p>', "", html, flags=re.S)

    def troca(m):
        attr, caminho = m.group(1), m.group(2)
        if caminho.startswith("/static/") or caminho.endswith((".css", ".png", ".js")):
            return f'{attr}="{base}{caminho}"'
        destino = caminho if caminho.endswith("/") else caminho + "/"
        return f'{attr}="{base}{destino}"'

    html = re.sub(r'\b(href|src|data-primeira)="(/[^"/][^"]*|/)"', troca, html)
    faixa = ('<div class="faixa-vitrine">Visualização estática da casca do Nexus. '
             'Sem login e sem dados: as telas mostram só o que cada uma vai responder.</div>')
    return html.replace('<div class="corpo">', faixa + '\n<div class="corpo">', 1)


def exportar(saida: Path, base: str) -> int:
    app = _app()
    if saida.exists():
        shutil.rmtree(saida)
    paginas = {}
    torres = app.extensions["nexus_torres"]
    # test_request_context resolve a rota sem despachar: o contexto do menu sabe a torre atual, e nenhuma
    # view (nem o portão de login) roda.
    with app.test_request_context("/"):
        paginas["index.html"] = render_template(
            "inicio.html", torres=torres, total_telas=sum(len(t.telas) for t in torres))
    for torre in torres:
        for tela in torre.telas:
            with app.test_request_context(f"/t/{torre.id}/{tela.id}"):
                paginas[f"t/{torre.id}/{tela.id}/index.html"] = render_template(
                    "tela.html", torre=torre, tela=tela)

    for relativo, html in paginas.items():
        html = _ajustar(html, base)
        for nome, padrao in PROIBIDOS.items():
            achado = padrao.search(html)
            if achado:
                raise SystemExit(f"Exportação abortada: {nome} em {relativo} ({achado.group(0)[:4]}...)")
        destino = saida / relativo
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(html, encoding="utf-8")

    # Só o CSS e o logo da casca; o CSS do cadastro não vai, porque nenhuma tela dele sai.
    (saida / "static").mkdir(parents=True, exist_ok=True)
    for arq in ("nexus.css", "grid-h-branco.png"):
        shutil.copy2(RAIZ / "nexus" / "static" / arq, saida / "static" / arq)
    (saida / ".nojekyll").write_text("", encoding="utf-8")
    return len(paginas)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("saida", nargs="?", default=str(RAIZ / "_site"))
    p.add_argument("--base", default="/nexus", help="caminho do site no Pages (repo de projeto = /<repo>)")
    a = p.parse_args()
    n = exportar(Path(a.saida), a.base.rstrip("/"))
    print(f"{n} páginas exportadas em {a.saida}")
