"""O Relatório executivo do PCM (Interno Grid, Cliente e Abertura da Semana) dentro do Nexus (14/10/2026).

Levi, 14/10/2026, com o print do modal "Relatório executivo" da aba Gestão PCM do painel: "Quero trazer esses três
relatórios para a plataforma, com as mesmas métricas e parâmetros e estilos". No PCM ele é JavaScript que roda no
navegador sobre o gestao_pcm.json, o banco_dados.json e o confiabilidade.json (`js/relatorio_exec.js`, ~1.300 linhas, e
`css/relatorio_exec.css`). Aqui ele é a MESMA cópia (como o motor do PCM e o OS Creator), servida numa moldura da Central
de emissão: números, parâmetros e visual iguais por construção. Regras, como atualizar e a prova: CLAUDE.md desta pasta.

- `COPIAS`: o hash de cada arquivo copiado, com o fim de linha normalizado (LF); o teste reprova cópia editada.
- `TROCAS_JS`: o que muda ao servir, e só isto: os emojis da interface saem (regra do Nexus) e "Voltar ao painel" vira
  "Voltar". A cópia no disco fica idêntica à do PCM.
- Os dados vêm do `nexus/pcm/fonte.py` (cópia de 5 min no servidor, ETag no GitHub) e saem compactados (o
  gestao_pcm.json de 14/10/2026: 14,9 MB; com gzip, 0,75 MB, em 0,9 s na cópia de prova).
"""
import gzip
import hashlib
import json
import threading
from pathlib import Path

from flask import Response, abort, current_app, redirect, render_template, request, url_for

from .. import fonte

AQUI = Path(__file__).resolve().parent
ORIGEM = "fillipefigueiro-source/gridco-pcm-data, commit fb21576 (14/10/2026)"
COPIAS = {
    "relatorio_exec.js": "3bc2d0a9f672acdeec23cf3e77e2a01e29787be988e31dcb76d3aac55b3ba84e",
    "relatorio_exec.css": "6c9bb88b6a1160558d7f0a7ee63f27b6ff0bcebdc59f892c54e0c0d6164061b7",
    "gpv_cel.css": "c4a49f0a7d8139add1ebb97bf8f8160a24d9a8f4dc1c8457bdabd7166b0c9e1a",   # css/preventivas.css 86-92
}
TIPOS_DE_ARQUIVO = {"relatorio_exec.js": "application/javascript", "apoio.js": "application/javascript",
                    "relatorio_exec.css": "text/css", "gpv_cel.css": "text/css"}
TROCAS_JS = (("&#128196; ", ""), ("&#127970; ", ""), ("&#129309; ", ""), ("&#128197; ", ""), ("&#128424; ", ""),
             ("Voltar ao painel", "Voltar"))
DADOS = {"gestao_pcm.json": fonte.ler_gestao, "banco_dados.json": fonte.ler,
         "confiabilidade.json": fonte.ler_confiabilidade}
TELA_ID = "pcm-executivo"

_GZ: dict = {}
_TRAVA = threading.Lock()


def ler_copia(nome: str) -> bytes:
    """O arquivo como está na pasta, com o fim de linha normalizado (o git do Windows põe CRLF ao tirar do repositório)."""
    return (AQUI / nome).read_bytes().replace(b"\r\n", b"\n")


def hash_da_copia(nome: str) -> str:
    return hashlib.sha256(ler_copia(nome)).hexdigest()


def servido(nome: str) -> bytes:
    corpo = ler_copia(nome)
    if nome == "relatorio_exec.js":
        texto = corpo.decode("utf-8")
        for de, para in TROCAS_JS:
            texto = texto.replace(de, para)
        corpo = texto.encode("utf-8")
    return corpo


def _versao() -> str:
    """Muda quando a cópia muda: o navegador não fica com o arquivo velho em cache."""
    return hashlib.sha256("".join(COPIAS.values()).encode() + ler_copia("apoio.js")).hexdigest()[:10]


def _json_gz(nome: str, leitura) -> bytes:
    """O JSON compactado, guardado por versão do arquivo (a hora em que o fonte.py o baixou): sem refazer o gzip de
    15 MB a cada relatório. Só a versão de agora de cada arquivo fica na memória."""
    chave = (nome, leitura.fonte, leitura.baixado_em)
    with _TRAVA:
        guardado = _GZ.get(nome)
        if guardado and guardado[0] == chave:
            return guardado[1]
    gz = gzip.compress(json.dumps(leitura.dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 6)
    with _TRAVA:
        _GZ[nome] = (chave, gz)
    return gz


def painel_html(tema: str, logo: str) -> str:
    """O documento da moldura: a tela de partida (o botão que abre o modal do PCM) e os arquivos do PCM. As cores da tela
    de partida seguem o tema do Nexus (vem no endereço); a folha do relatório é a do PCM, em papel branco."""
    escuro = tema != "claro"
    fundo, tinta, mudo = ("#090d18", "#e8ecf4", "#9aa3b5") if escuro else ("#f5f7fb", "#191528", "#5d6475")
    v = _versao()
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Relatório executivo · PCM · Nexus</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="gpv_cel.css?v={v}"><link rel="stylesheet" href="relatorio_exec.css?v={v}">
<style>
body{{margin:0;font-family:"Plus Jakarta Sans",system-ui,sans-serif;background:{fundo};color:{tinta}}}
.rx-inicio{{max-width:720px;margin:28px auto;padding:0 16px}}
.rx-inicio p{{margin:0 0 14px;color:{mudo};font-size:14px;line-height:1.5}}
.rx-erro{{color:#e5484d}}
body.rex-on .rx-inicio{{display:none}}
</style></head><body>
<img class="l-logo" src="{logo}" alt="Grid Co." hidden>
<main class="rx-inicio">
  <p id="rx-estado">Carregando a Gestão PCM…</p>
  <button type="button" class="rex-btn" id="rx-gerar" disabled>Gerar relatório</button>
</main>
<script src="apoio.js?v={v}"></script>
<script src="relatorio_exec.js?v={v}"></script>
</body></html>"""


def registrar(bp, torre) -> None:
    """A tela da Central (`/t/relatorios/pcm-executivo`) e a moldura dela (`.../painel/`, com os arquivos e os dados ao
    lado: o JS do PCM lê `banco_dados.json` e `confiabilidade.json` pelo endereço relativo). As sub-rotas seguem a marca
    da tela no portão de setor."""
    base = f"/{TELA_ID}"

    def tela():
        from ...casca import tema_do_pedido
        return render_template("relatorios/pcm_executivo.html", torre=torre, tela=torre.tela(TELA_ID),
                               painel=f"/t/{torre.id}{base}/painel/?tema={tema_do_pedido()}")

    def painel():
        tema = "claro" if request.args.get("tema") == "claro" else "escuro"
        logo = url_for("static", filename="grid-h-verde.png")
        return Response(painel_html(tema, logo), mimetype="text/html", headers={"Cache-Control": "no-store"})

    def arquivo(nome: str):
        if nome in TIPOS_DE_ARQUIVO:
            return Response(servido(nome), mimetype=TIPOS_DE_ARQUIVO[nome], headers={"Cache-Control": "max-age=3600"})
        if nome in DADOS:
            leitura = DADOS[nome](current_app.config)
            if leitura.dados is None:
                return Response(json.dumps({"erro": leitura.erro or "sem dado"}), status=503,
                                mimetype="application/json", headers={"Cache-Control": "no-store"})
            if "gzip" in (request.headers.get("Accept-Encoding") or ""):
                return Response(_json_gz(nome, leitura), mimetype="application/json",
                                headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding",
                                         "Cache-Control": "no-store"})
            return Response(json.dumps(leitura.dados, ensure_ascii=False), mimetype="application/json",
                            headers={"Vary": "Accept-Encoding", "Cache-Control": "no-store"})
        abort(404)

    bp.add_url_rule(base, endpoint=TELA_ID, view_func=tela)
    bp.add_url_rule(f"{base}/painel/", endpoint=f"{TELA_ID}_painel", view_func=painel)
    bp.add_url_rule(f"{base}/painel", endpoint=f"{TELA_ID}_painel_sem_barra",
                    view_func=lambda: redirect(url_for(f".{TELA_ID}_painel", **request.args), code=308))
    bp.add_url_rule(f"{base}/painel/<nome>", endpoint=f"{TELA_ID}_arquivo", view_func=arquivo)
