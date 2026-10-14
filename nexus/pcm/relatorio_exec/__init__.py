"""O Relatório executivo do PCM (Interno Grid, Cliente e Abertura da Semana) dentro do Nexus (14/10/2026).

Levi, 14/10/2026, com o print do modal "Relatório executivo" da aba Gestão PCM do painel: "Quero trazer esses três
relatórios para a plataforma, com as mesmas métricas e parâmetros e estilos". No PCM ele é JavaScript que roda no
navegador sobre o gestao_pcm.json, o banco_dados.json e o confiabilidade.json (`js/relatorio_exec.js`, ~1.300 linhas, e
`css/relatorio_exec.css`). Aqui ele é a MESMA cópia (como o motor do PCM e o OS Creator): números, parâmetros e visual
iguais por construção. Regras, como atualizar e a prova: CLAUDE.md desta pasta.

- A tela segue a estrutura de toda a Central (Levi, 14/10/2026: "Use a mesma estrutura do print 1 para todos os
  relatórios"): os três tipos são itens do bloco "Relatório Gerencial PCM" (`TIPOS`, `?tipo=`), o período e o escopo do
  modal do painel ficam na coluna da esquerda (`PRESETS` e as listas do gestao_pcm.json) e a folha, à direita. Ela é o
  documento da moldura (`painel_html`, modo "previa"), que lê os dados ao lado e monta a folha sozinho com a escolha
  que veio no endereço, pelos mesmos campos que o modal do painel preenche (`apoio.js`).
- `COPIAS`: o hash de cada arquivo copiado, com o fim de linha normalizado (LF); o teste reprova cópia editada. O
  `painel_pcm.js` são os trechos do js/app.js e do js/preventivas.js que o relatório usa, linha a linha.
- `TROCAS_JS`: o que muda ao servir, e só isto: os emojis da interface saem (regra do Nexus) e "Voltar ao painel" vira
  "Voltar". A cópia no disco fica idêntica à do PCM.
- Os dados vêm do `nexus/pcm/fonte.py` (cópia de 5 min no servidor, ETag no GitHub) e saem compactados (o
  gestao_pcm.json de 14/10/2026: 14,9 MB; com gzip, 0,75 MB, em 0,9 s na cópia de prova).
- A Gerencial (Levi, 14/10/2026: "traz a Gerencial cifrada para aparecer o MPA/MPS"): o mpas.json é cifrado (o
  repositório do PCM é público) e o servidor o abre com a `NEXUS_PCM_MPAS_SENHA` do .env, a senha do login de
  administrador do painel (`gerencial.json`). Sem ela, o "MPA/MPS atrasadas" sai como no painel sem a senha: "tarefas
  abertas há +30 dias".
"""
import gzip
import hashlib
import json
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

from flask import Response, abort, current_app, redirect, render_template, request, url_for

from .. import fonte

AQUI = Path(__file__).resolve().parent
ORIGEM = "fillipefigueiro-source/gridco-pcm-data, main e6cdab4 (14/10/2026)"
COPIAS = {
    "relatorio_exec.js": "3bc2d0a9f672acdeec23cf3e77e2a01e29787be988e31dcb76d3aac55b3ba84e",
    "relatorio_exec.css": "6c9bb88b6a1160558d7f0a7ee63f27b6ff0bcebdc59f892c54e0c0d6164061b7",
    "gpv_cel.css": "c4a49f0a7d8139add1ebb97bf8f8160a24d9a8f4dc1c8457bdabd7166b0c9e1a",   # css/preventivas.css 86-92
    # os trechos do js/app.js e do js/preventivas.js que o relatório usa (as faixas de linha estão no próprio arquivo)
    "painel_pcm.js": "5d33d7d8eb38fd431d9041732b076ba071ab1734a1ffe0cb3f653771cfdf9da1",
}
TIPOS_DE_ARQUIVO = {"relatorio_exec.js": "application/javascript", "apoio.js": "application/javascript",
                    "painel_pcm.js": "application/javascript", "relatorio_exec.css": "text/css",
                    "gpv_cel.css": "text/css"}
TROCAS_JS = (("&#128196; ", ""), ("&#127970; ", ""), ("&#129309; ", ""), ("&#128197; ", ""), ("&#128424; ", ""),
             ("Voltar ao painel", "Voltar"))
DADOS = {"gestao_pcm.json": fonte.ler_gestao, "banco_dados.json": fonte.ler,
         "confiabilidade.json": fonte.ler_confiabilidade}
TELA_ID = "pcm-executivo"
# Os três tipos do modal do painel, cada um um item do bloco "Relatório Gerencial PCM" da Central (14/10/2026, Levi:
# "abaixo terá um bloco 'Relatório Gerencial PCM' onde terá os três tipos de relatório"). O ícone faz o papel do emoji
# do modal do PCM (prédio, aperto de mão, calendário), que no Nexus não entra.
TIPOS = {
    "interno": {"nome": "Interno Grid", "icone": "buildings",
                "descricao": "o que rodou, o que travou e onde agir · versão completa"},
    "cliente": {"nome": "Cliente", "icone": "handshake",
                "descricao": "o que entregamos e o que vem a seguir · sem dados internos"},
    "semana": {"nome": "Abertura da Semana", "icone": "calendar-check",
               "descricao": "atenção, rolagens e atrasos da semana programada · 2 páginas"},
}
# Os períodos prontos do modal do painel (rexPreset); a conta de cada um mora no static/relatorios.js, a mesma de lá
PRESETS = (("sem", "Esta semana"), ("semp", "Semana passada"), ("mes", "Este mês"), ("mesp", "Mês passado"),
           ("30d", "Últimos 30 dias"))
BRT = timezone(timedelta(hours=-3))

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


def _sem_dado(erro: str, status: int = 503) -> Response:
    return Response(json.dumps({"erro": erro}), status=status, mimetype="application/json",
                    headers={"Cache-Control": "no-store"})


def painel_html(tema: str, logo: str, modo: str = "inicio") -> str:
    """O documento da moldura. `modo`: "previa" = a folha da coluna da direita da Central (monta sozinha com a escolha do
    endereço, em papel branco, sem a barra do painel: o "Imprimir / PDF" é o da Central); "aba" = a mesma folha numa aba
    nova, com a barra do painel; "inicio" = a tela de partida do painel (o botão que abre o modal do PCM). As cores da
    tela de partida seguem o tema do Nexus (vem no endereço); a folha é a do PCM, em papel branco."""
    escuro = tema != "claro"
    fundo, tinta, mudo = ("#090d18", "#e8ecf4", "#9aa3b5") if escuro else ("#f5f7fb", "#191528", "#5d6475")
    v = _versao()
    classe = {"previa": "rx-previa", "aba": "rx-aba"}.get(modo, "")
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
body.rx-previa{{background:#fff}}
body.rx-previa .rx-inicio{{display:none}}
body.rx-previa #rex-view{{position:static;overflow:visible;background:#fff}}
body.rx-previa .rex-bar{{display:none}}
body.rx-previa .rex-a4{{margin:0;max-width:none;box-shadow:none}}
body.rx-aba .rex-bar .rex-btn-2{{display:none}}
</style></head><body class="{classe}">
<img class="l-logo" src="{logo}" alt="Grid Co." hidden>
<main class="rx-inicio">
  <p id="rx-estado">Carregando a Gestão PCM…</p>
  <button type="button" class="rex-btn" id="rx-gerar" disabled>Gerar relatório</button>
</main>
<script src="painel_pcm.js?v={v}"></script>
<script src="apoio.js?v={v}"></script>
<script src="relatorio_exec.js?v={v}"></script>
</body></html>"""


def _data(v) -> str:
    try:
        return date.fromisoformat(str(v or "")[:10]).isoformat()
    except ValueError:
        return ""


def pedido(args) -> dict:
    """A escolha da coluna da esquerda (os campos do modal do painel), limpa: o tipo, o período, o cliente, a equipe
    cluster, as usinas e a opção das preventivas criadas no período. Sem período, o do painel: este mês."""
    tipo = args.get("tipo") if args.get("tipo") in TIPOS else "interno"
    hoje = datetime.now(BRT).date()
    de, ate = _data(args.get("de")), _data(args.get("ate"))
    if not de and not ate:
        de, ate = hoje.replace(day=1).isoformat(), hoje.isoformat()
    usinas = [u.strip()[:200] for u in args.getlist("usi") if u.strip()][:500]
    return {"tipo": tipo, "de": de, "ate": ate, "cli": (args.get("cli") or "").strip()[:160],
            "clu": (args.get("clu") or "").strip()[:160], "usi": usinas, "semprev": args.get("semprev") == "1"}


def endereco_da_folha(base: str, p: dict) -> str:
    """O endereço do documento da moldura com a escolha (sem o prefixo: o template põe). A Abertura da Semana não leva
    período nem a opção das preventivas: no painel ela usa a semana mais recente da programação."""
    q = [("tipo", p["tipo"])]
    if p["tipo"] != "semana":
        q += [("de", p["de"]), ("ate", p["ate"])]
    q += [(k, p[k]) for k in ("cli", "clu") if p[k]] + [("usi", u) for u in p["usi"]]
    if p["semprev"] and p["tipo"] != "semana":
        q.append(("semprev", "1"))
    return f"{base}/painel/?" + urlencode(q + [("gerar", "1")])


def _dica(p: dict) -> str:
    fmt = lambda iso: f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"          # noqa: E731
    partes = [TIPOS[p["tipo"]]["nome"]]
    partes.append("a semana mais recente da programação" if p["tipo"] == "semana" else f"{fmt(p['de'])} a {fmt(p['ate'])}")
    partes += [x for x in (p["cli"], p["clu"]) if x]
    if p["usi"]:
        partes.append(f"{len(p['usi'])} usina(s)")
    return " · ".join(partes) + " · gerado agora com o dado do PCM"


def _gerencial_json() -> Response:
    """A Gerencial (o mpas.json) aberta pelo servidor com a senha do .env, só com o que a Fila das MPA/MPS do painel lê
    (`manut` e `bd`). Sem a senha, 503: o relatório sai como no painel sem ela."""
    from ..telas import _gerencial      # a mesma cópia aberta da Gestão PCM: decifra uma vez por versão do arquivo
    mp, erro = _gerencial(current_app.config)
    if mp is None:
        return _sem_dado(erro or "sem a Gerencial")
    corpo = {"geradoEm": mp.get("geradoEm") or "", "manut": mp.get("manut") or [], "bd": mp.get("bd") or {}}
    return Response(json.dumps(corpo, ensure_ascii=False), mimetype="application/json",
                    headers={"Cache-Control": "no-store"})


def registrar(bp, torre, lado) -> None:
    """A tela da Central (`/t/relatorios/pcm-executivo?tipo=`) e a moldura dela (`.../painel/`, com os arquivos e os
    dados ao lado: o JS do PCM lê `banco_dados.json` e `confiabilidade.json` pelo endereço relativo). `lado` = os blocos
    da coluna da esquerda da Central. As sub-rotas seguem a marca da tela no portão de setor."""
    base = f"/{TELA_ID}"

    def tela():
        from ...casca import tema_do_pedido
        p = pedido(request.args)
        g = fonte.ler_gestao(current_app.config)      # a cópia de 5 min do servidor: a mesma da Gestão PCM
        filtros = (g.dados or {}).get("filtros") or {}
        endereco, erro = "", ""
        if request.args.get("gerar") == "1":
            if p["tipo"] != "semana" and not (p["de"] and p["ate"] and p["de"] <= p["ate"]):
                erro = "Confira o período: o início vem antes do fim."
            else:
                endereco = endereco_da_folha(f"/t/{torre.id}{base}", p)
        return render_template("relatorios/pcm_executivo.html", torre=torre, tela=torre.tela(TELA_ID),
                               lado=lado(TELA_ID, p["tipo"]), tipo=dict(TIPOS[p["tipo"]], id=p["tipo"]), p=p,
                               presets=PRESETS, clientes=filtros.get("clientes") or [],
                               clusters=filtros.get("clusters") or [], usinas=filtros.get("usinas") or [],
                               base=f"/t/{torre.id}{base}", folha_url=endereco,
                               aba_url=f"{endereco}&aba=1&tema={tema_do_pedido()}" if endereco else "",
                               dica=_dica(p) if endereco else "", erro=erro,
                               erro_fonte="" if g.dados else (g.erro or "sem dado"))

    def painel():
        tema = "claro" if request.args.get("tema") == "claro" else "escuro"
        logo = url_for("static", filename="grid-h-verde.png")
        modo = "inicio" if request.args.get("gerar") != "1" else ("aba" if request.args.get("aba") == "1" else "previa")
        return Response(painel_html(tema, logo, modo), mimetype="text/html", headers={"Cache-Control": "no-store"})

    def arquivo(nome: str):
        if nome in TIPOS_DE_ARQUIVO:
            return Response(servido(nome), mimetype=TIPOS_DE_ARQUIVO[nome], headers={"Cache-Control": "max-age=3600"})
        if nome == "gerencial.json":
            return _gerencial_json()
        if nome in DADOS:
            leitura = DADOS[nome](current_app.config)
            if leitura.dados is None:
                return _sem_dado(leitura.erro or "sem dado")
            if "gzip" in (request.headers.get("Accept-Encoding") or ""):
                return Response(_json_gz(nome, leitura), mimetype="application/json",
                                headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding",
                                         "Cache-Control": "no-store"})
            return Response(json.dumps(leitura.dados, ensure_ascii=False), mimetype="application/json",
                            headers={"Vary": "Accept-Encoding", "Cache-Control": "no-store"})
        abort(404)

    bp.add_url_rule(base, endpoint=TELA_ID, view_func=tela)
    bp.add_url_rule(f"{base}/painel/", endpoint=f"{TELA_ID}_painel", view_func=painel)
    # o endereço relativo dos arquivos precisa da barra; a escolha vai inteira (as várias usinas também)
    bp.add_url_rule(f"{base}/painel", endpoint=f"{TELA_ID}_painel_sem_barra",
                    view_func=lambda: redirect(url_for(f".{TELA_ID}_painel") + (
                        "?" + request.query_string.decode("latin-1") if request.query_string else ""), code=308))
    bp.add_url_rule(f"{base}/painel/<nome>", endpoint=f"{TELA_ID}_arquivo", view_func=arquivo)
