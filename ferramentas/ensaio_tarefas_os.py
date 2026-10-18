"""O ensaio do `nexus_os · fato_tarefa_os` com o Fracttal de verdade (18/10/2026). Imprime só contagens.

    python ferramentas/ensaio_tarefas_os.py            lê o Fracttal (só GET), monta o fato, compara com a Gestão PCM; NÃO grava
    python ferramentas/ensaio_tarefas_os.py --gravar   a 1ª gravação (forcar), só com o OK do Levi; confere depois de gravar

Por quê (regra 8 do `nexus/dados/CLAUDE.md`: "medir com o dado real ANTES de gravar"): o livro no banco é para sempre.
O ensaio mostra as páginas e o tempo de cada status (a cota do Fracttal é de 200 pedidos por minuto para a empresa
inteira), a chave repetida (tem de ser 0), quanto liga a usina e o equipamento (abaixo de 98% na usina, conserta-se no
cadastro antes de gravar), a grafia dos tipos de tarefa no REST (para a Zeladoria e o Teste) e, por usina, as tarefas
abertas e atrasadas (mais de 10 dias) lado a lado com o `gestao_pcm.json` do robô do PCM, sem nenhuma exclusão dos dois
lados (o arquivo do PCM não traz o responsável da OS). Depois, à parte, quanto cada exclusão da Visão tira.
"""
import argparse
import json
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BRT = timezone(timedelta(hours=-3))


def _status(path: str) -> str:
    st = path.split("id_status_work_order=")[1].split("&")[0]
    return f"{st} (zeladoria)" if "tasks_log_task_type_main=" in path else st


def _dia(data_id) -> date | None:
    try:
        n = int(data_id)
        return date(n // 10000, n // 100 % 100, n % 100)
    except (TypeError, ValueError):
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gravar", action="store_true", help="a 1ª gravação no banco (só com o OK do Levi)")
    args = ap.parse_args()

    import requests
    from nexus import create_app
    from nexus.campo import fracttal
    from nexus.campo import tarefas_os as P
    from nexus.dados import equipamento as E
    from nexus.dados import fato_tarefa_os as F
    from nexus.dados import fatos as D
    from nexus.dados import livros

    app = create_app()
    with app.app_context():
        cfg = app.config
        if args.gravar:
            rel = P.publicar(cfg, forcar=True)
            print(json.dumps(rel, ensure_ascii=False, indent=1))
            if rel.get("gravado"):
                n = len(livros.ler(P._base(cfg), requests.Session(), F.LIVRO, F.ABA))
                print(f"conferido depois de gravar: {n} linhas no banco ({'igual' if n == rel['linhas'] else 'DIFERENTE'})")
            return

        hoje = datetime.now(BRT).date()
        # o banco antes do Fracttal: se ele não responder, a cota da empresa não se gasta à toa
        s, base = requests.Session(), P._base(cfg)
        cad = {aba: livros.ler(base, s, "cadastro_nexus", aba) for aba in ("usinas", "de_para", "equipes")}
        lig = D.Ligador(cad["usinas"], cad["de_para"], cad["equipes"], {})
        idx = E.indice(livros.ler(base, s, "nexus_equipamentos", "dim_equipamento"))
        bo = P._backoffice_hmac(cfg)
        paginas, tempo = Counter(), Counter()

        def ler(path):
            t0 = time.time()
            r = fracttal.ler(path)
            paginas[_status(path)] += 1
            tempo[_status(path)] += time.time() - t0
            return r
        t0 = time.time()
        rows = P.ler_fracttal(ler, hoje)
        print(f"leitura: {sum(paginas.values())} páginas em {time.time() - t0:.0f} s")
        for st in sorted(paginas):
            print(f"  status {st}: {paginas[st]} páginas, {tempo[st]:.0f} s de pedido")
        print("tipos de tarefa no REST:", dict(Counter(r.get("tasks_log_task_type_main") or "(vazio)" for r in rows)
                                              .most_common()))

        lin, rf = F.linhas(rows, lig, idx, bo or set(), cfg.get("NEXUS_PESSOA_HMAC") if bo is not None else None)
        F.conferir_grao(lin)
        q = dict(zip(D.CAB_QUALIDADE, F.linha_qualidade(lin, dict(rf, paginas=sum(paginas.values())), "", "")))
        print(f"fato: {len(lin)} linhas de {rf['lidas']} lidas; repetidas {rf['repetidas']}; sem chave {rf['sem_chave']}; "
              f"chave repetida depois do dedupe: 0")
        print(f"  usina ligada {q['pct_usina']}% (de-para {q['usina_por_de_para']}, código {q['usina_por_codigo']}); "
              f"equipamento {q['pct_equipamento']}%; data programada {q['pct_data']}%")
        print(f"  fora do domínio {rf['fora_do_dominio']}; backoffice {rf['backoffice']}")
        print(f"  sites sem usina: {q['sem_usina_exemplos']}")

        # ── a comparação com a Gestão PCM, sem exclusão dos dois lados ─────────────────────────────────────────────
        c = {k: F.CAB_TAREFA_OS.index(k) for k in F.CAB_TAREFA_OS}
        nome = {D._id(u.get("usina_id")): D._txt(u.get("nome")) for u in cad["usinas"]}
        nos, eles = Counter(), Counter()
        for l in lin:
            if l[c["status_os"]] not in ("em_processo", "em_verificacao") or l[c["estado_tarefa"]] == "finalizada":
                continue
            prog = _dia(l[c["data_id_programada"]])
            if not prog or prog < date(2026, 1, 1):                       # o escopo do robô do PCM (CORTE_DATA)
                continue
            nos[(l[c["usina_id"]], "abertas")] += 1
            nos[(l[c["usina_id"]], "atrasadas")] += (hoje - prog).days > 10
        from nexus.pcm import fonte
        g = fonte.ler_gestao(cfg)
        dados = getattr(g, "dados", None) or {}
        print(f"\nGestão PCM: gerado em {dados.get('geradoEm')}; {len(dados.get('tarefas') or [])} tarefas")
        for t in dados.get("tarefas") or []:
            st = str(t.get("osStatus") or "").lower()
            if not t.get("aberta") or not ("process" in st or "verific" in st):
                continue
            uid = lig.usina(t.get("usina"), "")[0]
            eles[(uid, "abertas")] += 1
            eles[(uid, "atrasadas")] += bool(t.get("atrasado"))
        for k in ("abertas", "atrasadas"):
            print(f"  {k}: Nexus {sum(v for (u, kk), v in nos.items() if kk == k)} × "
                  f"PCM {sum(v for (u, kk), v in eles.items() if kk == k)}")
        dif = sorted({u for u, _ in nos} | {u for u, _ in eles},
                     key=lambda u: -abs(nos[(u, "abertas")] - eles[(u, "abertas")]))
        print("  usinas com diferença (abertas e atrasadas, Nexus × PCM):")
        for u in dif[:20]:
            if nos[(u, "abertas")] != eles[(u, "abertas")] or nos[(u, "atrasadas")] != eles[(u, "atrasadas")]:
                print(f"    {nome.get(u, '(sem usina)')}: {nos[(u, 'abertas')]} × {eles[(u, 'abertas')]}; "
                      f"{nos[(u, 'atrasadas')]} × {eles[(u, 'atrasadas')]}")

        # ── o que cada exclusão da Visão tira das tarefas abertas ──────────────────────────────────────────────────
        abertas = [l for l in lin if l[c["status_os"]] in ("em_processo", "em_verificacao")
                   and l[c["estado_tarefa"]] != "finalizada"]
        chamados = {D._id(r.get("os")) for r in livros.ler(base, s, "nexus_chamados", "fato_chamado")}
        from nexus.pcm import motivos
        est = motivos.ler(cfg)
        vig = motivos.vigentes(cfg, est)
        vig.pop("_ilegiveis", None)
        marcas = {(D._id(m.get("os")), E.canon(m.get("codigo")), D.tarefa_chave(m.get("tarefa"))) for m in vig.values()
                  if m.get("tira") or m.get("origem_motivo") == "app"}
        com_marca = sum(1 for l in abertas if (l[c["os"]], E.canon(l[c["codigo_ativo"]]), l[c["tarefa_chave"]]) in marcas
                        or (l[c["os"]], "", l[c["tarefa_chave"]]) in marcas)
        print(f"\nexclusões nas {len(abertas)} tarefas abertas: backoffice {sum(l[c['do_backoffice']] for l in abertas)}, "
              f"motivo {com_marca}, chamado {sum(1 for l in abertas if l[c['os']] in chamados)}, "
              f"zeladoria {sum(1 for l in abertas if l[c['tipo_tarefa']] == 'zeladoria')}, "
              f"teste {sum(1 for l in abertas if l[c['tipo_tarefa']] == 'teste')}")


if __name__ == "__main__":
    main()
