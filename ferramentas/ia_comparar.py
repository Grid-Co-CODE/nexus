"""O teste das IAs do Nexus IA, lado a lado (13/11/2026). Levi: "Teste com várias IAs. Tal como Sonnet, Opus, Gemini,
Groq, Grok [...] Qualquer IA que dê para puxar a API para fazermos o teste."

Para cada usina pedida, monta o dossiê de AGORA (o mesmo da tela, `nexus/comando/dossie.py`, só leitura) e faz as mesmas
perguntas a todos os modelos que têm a chave no ambiente (`nexus/comando/ia.py`), em paralelo. Sai uma página HTML com:
- por pergunta, a resposta de cada modelo lado a lado, com o tempo, os tokens, o custo estimado e os números que não
  estão no dossiê (cálculo da IA ou invenção: é por onde se confere primeiro);
- o resumo por modelo: tempo médio, custo total, quantas respostas, quantos erros e a fração de números do dossiê.

    python ferramentas/ia_comparar.py --usinas 1,23,68 [--perguntas "Como foi?|Por que caiu?"] [--modelos opus,grok]
           [--saida pasta] [--teto 5]

As chaves vêm do ambiente ou do .env do Nexus (ANTHROPIC_API_KEY, GEMINI_API_KEY, XAI_API_KEY, GROQ_API_KEY,
OPENROUTER_API_KEY): o modelo sem chave sai na página como "sem chave", sem chamada. Cada rodada CUSTA (os preços que não
são da Anthropic são de referência): o `--teto` (US$, padrão 5) para a rodada quando a conta estimada passa dele. Nada
grava no banco: o dossiê é só lido, e o resultado vai também em JSON ao lado da página.
"""
import argparse
import html
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

_BRT = timezone(timedelta(hours=-3))
PERGUNTAS = ("Como foi a performance no mês?", "Por que a usina caiu?", "Qual a tendência dos últimos meses?",
             "O que está aberto e atrasado?")


def _dossies(ids: list[int]) -> dict:
    """{usina_id: (nome, texto do dossiê)}, pelo Nexus desta máquina, como administrador e só lendo (GET)."""
    from dotenv import load_dotenv
    load_dotenv(RAIZ / ".env")
    from nexus import create_app
    app = create_app()
    out = {}
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logado=True, admin=True)
    for uid in ids:
        r = c.get(f"/t/comando/usinas/{uid}/dossie.md")
        if r.status_code != 200:
            print(f"usina {uid}: o dossiê não abriu ({r.status_code})")
            continue
        texto = r.get_data(as_text=True)
        nome = texto.splitlines()[0].removeprefix("# Dossiê da usina ").strip()
        out[uid] = (nome, texto)
    return out, app.config


def _md(t: str) -> str:
    """O texto da IA em HTML mínimo (escapado antes)."""
    out, lista = [], False
    for linha in html.escape(t or "").splitlines():
        s = linha.strip()
        item = s[:2] in ("- ", "* ", "• ")
        if item and not lista:
            out.append("<ul>")
            lista = True
        if not item and lista:
            out.append("</ul>")
            lista = False
        if item:
            out.append(f"<li>{s[2:]}</li>")
        elif s:
            out.append(f"<p>{s}</p>")
    if lista:
        out.append("</ul>")
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", "".join(out))


def _pagina(rodada: list[dict], modelos: list, quando: str) -> str:
    por_modelo = {m["id"]: {"rotulo": m["rotulo"], "provedor": m["provedor_nome"], "tem": m["tem_chave"], "n": 0, "erros": 0,
                            "ms": 0, "custo": 0.0, "num": 0, "num_ok": 0, "oficial": m["preco_oficial"]} for m in modelos}
    for item in rodada:
        for r in item["respostas"]:
            a = por_modelo[r["id"]]
            if r.get("ok"):
                a["n"] += 1
                a["ms"] += r.get("ms") or 0
                a["custo"] += r.get("custo_usd") or 0
                a["num"] += r["numeros"]["n"]
                a["num_ok"] += r["numeros"]["no_dossie"]
            else:
                a["erros"] += 1
    linhas = []
    for mid, a in por_modelo.items():
        if not a["tem"]:
            linhas.append(f"<tr class='sem'><td><b>{html.escape(a['rotulo'])}</b><br><small>{html.escape(a['provedor'])}</small></td>"
                          "<td colspan='5'>sem chave: não foi chamado</td></tr>")
            continue
        media = f"{a['ms'] / a['n'] / 1000:.1f} s".replace(".", ",") if a["n"] else "—"
        frac = f"{100 * a['num_ok'] / a['num']:.0f}%" if a["num"] else "—"
        linhas.append(f"<tr><td><b>{html.escape(a['rotulo'])}</b><br><small>{html.escape(a['provedor'])}</small></td>"
                      f"<td>{a['n']}</td><td>{a['erros']}</td><td>{media}</td>"
                      f"<td>US$ {a['custo']:.4f}{'' if a['oficial'] else ' (ref.)'}</td><td>{frac}</td></tr>".replace("US$ 0.", "US$ 0,"))
    blocos = []
    for item in rodada:
        cartoes = []
        for r in item["respostas"]:
            cab = f"<div class='cab'><b>{html.escape(r['rotulo'])}</b><small>{html.escape(r['provedor'])}</small></div>"
            if not r.get("ok"):
                cartoes.append(f"<article class='r erro'>{cab}<p>{html.escape(r.get('erro') or 'sem resposta')}</p></article>")
                continue
            n = r["numeros"]
            fora = (f"<span class='alerta' title='{html.escape(', '.join(n['fora']))}'>{n['no_dossie']} de {n['n']} números no "
                    f"dossiê · fora: {html.escape(', '.join(n['fora']))}</span>" if n["fora"] else
                    f"<span class='ok'>{n['no_dossie']} de {n['n']} números no dossiê</span>" if n["n"] else "")
            pe = (f"{r['ms'] / 1000:.1f} s · {r['entrada'] + (r.get('cache_lido') or 0)} → {r['saida']} tokens · "
                  f"US$ {r['custo_usd']:.4f}{'' if r['preco_oficial'] else ' (ref.)'}").replace(".", ",")
            cartoes.append(f"<article class='r'>{cab}<div class='txt'>{_md(r['texto'])}</div><p class='pe'>{fora}<span>{pe}</span></p></article>")
        blocos.append(f"<section class='q'><h3>{html.escape(item['usina'])} <small>·</small> {html.escape(item['pergunta'])}</h3>"
                      f"<div class='grade'>{''.join(cartoes)}</div></section>")
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nexus IA · teste das IAs</title>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{{--fundo:#090d18;--superficie:#161d30;--superficie-2:#1c2640;--tinta:#e9eef6;--tinta-2:#c3cad7;--mudo:#96a0b4;
--linha:rgba(255,255,255,.09);--verde:#a3d900;--ok:#4ade80;--ok-suave:rgba(74,222,128,.14);--alerta:#ffd83d;
--alerta-suave:rgba(255,216,61,.14);--critico:#ff5b6e}}
body{{margin:0;background:var(--fundo);color:var(--tinta);font:400 14px/1.5 Poppins,system-ui,sans-serif}}
main{{max-width:1400px;margin:0 auto;padding:24px 20px 60px}} h1{{margin:0 0 4px;font-size:26px}} .sub{{color:var(--mudo);margin:0 0 20px}}
table{{width:100%;border-collapse:collapse;background:var(--superficie);border-radius:10px;overflow:hidden;margin-bottom:28px}}
th,td{{text-align:left;padding:9px 12px;border-bottom:1px solid var(--linha);vertical-align:top}}
th{{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--mudo)}} tr.sem td{{color:var(--mudo)}}
small{{color:var(--mudo)}} .q{{margin:0 0 26px}} .q h3{{font-size:15px;margin:0 0 10px}}
.grade{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:10px}}
.r{{background:var(--superficie);border:1px solid var(--linha);border-radius:10px;padding:12px 14px;display:grid;gap:8px;align-content:start}}
.r.erro{{border-color:rgba(255,91,110,.4)}} .r.erro p{{color:var(--critico);margin:0}}
.cab{{display:flex;gap:8px;align-items:baseline}} .txt p{{margin:0 0 6px}} .txt ul{{margin:0 0 6px;padding-left:18px}}
.pe{{display:flex;flex-wrap:wrap;gap:6px 10px;margin:0;padding-top:8px;border-top:1px solid var(--linha);font-size:11.5px;color:var(--mudo)}}
.ok,.alerta{{padding:1px 7px;border-radius:6px;font-weight:600}} .ok{{color:var(--ok);background:var(--ok-suave)}}
.alerta{{color:var(--alerta);background:var(--alerta-suave)}}
</style></head><body><main>
<h1>Nexus IA · teste das IAs</h1>
<p class="sub">Rodada de {quando} (horário de Brasília). As mesmas perguntas, o mesmo dossiê de cada usina, um modelo por cartão.
Os custos marcados (ref.) usam preço de referência, não a tabela do provedor. "Números no dossiê": quantos números da resposta
estão no dossiê; o resto é cálculo da IA ou invenção, e é por ali que se confere.</p>
<table><thead><tr><th>Modelo</th><th>Respostas</th><th>Erros</th><th>Tempo médio</th><th>Custo da rodada</th><th>Números do dossiê</th></tr></thead>
<tbody>{''.join(linhas)}</tbody></table>
{''.join(blocos)}
</main></body></html>"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--usinas", required=True, help="ids das usinas, separados por vírgula (os do Comando > Usinas)")
    ap.add_argument("--perguntas", default="|".join(PERGUNTAS), help="separadas por |")
    ap.add_argument("--modelos", default="", help="ids dos modelos (padrão: todos os que têm chave)")
    ap.add_argument("--saida", default="", help="pasta da página (padrão: dados/ia do Nexus)")
    ap.add_argument("--teto", type=float, default=5.0, help="US$ máximos da rodada (estimado)")
    a = ap.parse_args(argv)
    ids = [int(x) for x in a.usinas.split(",") if x.strip()]
    perguntas = [p.strip() for p in a.perguntas.split("|") if p.strip()]
    dossies, cfg = _dossies(ids)
    from nexus.comando import ia as IA
    cfg = dict(cfg)
    for p in IA.PROVEDORES.values():                 # a chave do ambiente vale também (não só a do .env do Nexus)
        if os.environ.get(p["chave"]):
            cfg[p["chave"]] = os.environ[p["chave"]]
    modelos = IA.disponiveis(cfg)
    escolhidos = [m["id"] for m in modelos if m["tem_chave"] and (not a.modelos or m["id"] in a.modelos.split(","))]
    if not escolhidos:
        print("Nenhum modelo com chave: ponha ao menos uma destas no ambiente ou no .env do Nexus:",
              ", ".join(p["chave"] for p in IA.PROVEDORES.values()))
        return 2
    print(f"{len(dossies)} usina(s) x {len(perguntas)} pergunta(s) x {len(escolhidos)} modelo(s): {', '.join(escolhidos)}")
    rodada, gasto = [], 0.0
    for uid, (nome, texto) in dossies.items():
        for p in perguntas:
            if gasto >= a.teto:
                print(f"Teto da rodada (US$ {a.teto:.2f}) atingido: parei aqui.")
                break
            rs = IA.perguntar(cfg, escolhidos, texto, p)
            gasto += sum(r.get("custo_usd") or 0 for r in rs)
            rodada.append({"usina_id": uid, "usina": nome, "pergunta": p, "dossie_tokens": round(len(texto) / 4),
                           "respostas": rs})
            print(f"  {nome} · {p}: " + ", ".join(f"{r['id']} {'ok' if r.get('ok') else 'ERRO'}" for r in rs))
    quando = datetime.now(_BRT)
    pasta = Path(a.saida) if a.saida else Path(cfg.get("NEXUS_DADOS") or RAIZ / "dados") / "ia"
    pasta.mkdir(parents=True, exist_ok=True)
    nome = f"comparacao-{quando:%Y%m%d-%H%M}"
    (pasta / f"{nome}.json").write_text(json.dumps(rodada, ensure_ascii=False, indent=1), encoding="utf-8")
    (pasta / f"{nome}.html").write_text(_pagina(rodada, [m for m in modelos], quando.strftime("%d/%m/%Y às %H:%M")),
                                        encoding="utf-8")
    print(f"Gasto estimado: US$ {gasto:.4f}. Página: {pasta / (nome + '.html')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
