"""Carga ÚNICA do checklist das rondas que ficaram sem OS (Levi, 06/10/2026: "Atualize o banco de dados com essas
rondas passadas sem OS, mas não será rotina").

A ronda sem OS não tem o texto da OS no Fracttal, de onde o Nexus lê sujidade e vegetação; as respostas só existiam no
registro da ronda no App. Elas foram exportadas uma vez da tabela de rondas do App (um JSON com PartitionKey = dia,
inicio, email e respostas, lido com a conta do Levi; o Nexus não lê o Azure) e entram aqui no fato
`nexus_rondas_checklist · fato_checklist_ronda`, com os IDs do cadastro e sem nome nem e-mail (a API tem leitura aberta).

    python ferramentas/carregar_checklist_rondas_sem_os.py <export.json>            mede e NÃO grava
    python ferramentas/carregar_checklist_rondas_sem_os.py <export.json> --gravar   grava e confere
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from nexus import create_app  # noqa: E402
from nexus.campo.ligacao_cadastro import codigo_da_pessoa  # noqa: E402
from nexus.dados import carga, fatos, livros  # noqa: E402

LIVRO, NOME = "nexus_rondas_checklist", "Nexus · checklist das rondas sem OS (carga única de 06/10/2026)"
ORIGEM = ("rondas_app_campo", "OS de ronda")


def montar(config, sessao, export: list[dict]):
    base = carga._base(config)
    cad = {a: livros.ler(base, sessao, carga.CADASTRO, a) for a in ("usinas", "equipes", "de_para")}
    lig = fatos.Ligador(cad["usinas"], cad["de_para"], cad["equipes"], carga._pessoas_por_codigo(config, sessao))
    sem_os = [l for l in livros.ler(base, sessao, *ORIGEM) if not str(l.get("OS") or "").strip()]
    regs = {}
    for r in export:
        regs.setdefault((str(r.get("PartitionKey") or ""), str(r.get("inicio") or "")), []).append(r)
    unicos = {k: v[0] for k, v in regs.items() if len(v) == 1 and k[1]}
    chave = config.get("NEXUS_PESSOA_HMAC") or ""
    linhas, origem = fatos.fato_checklist_ronda(sem_os, unicos, lig,
                                                lambda e: codigo_da_pessoa(chave, e) if chave else "")
    agora = datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec="seconds")
    q = fatos.qualidade("ronda_checklist", "rondas_app_campo + registro da ronda no App", linhas,
                        fatos.CAB_CHECKLIST_RONDA, origem, livros.atualizado_em(base, sessao, ORIGEM[0]), agora)
    tabelas = {"fato_checklist_ronda": (fatos.CAB_CHECKLIST_RONDA, linhas),
               "qualidade": (fatos.CAB_QUALIDADE, [q]),
               "atualizacao": (carga.CAB_ATUALIZACAO, [[agora, "pc", None, len(linhas),
                                                        "carga única; liga ao rondas_app_campo por usina_id + inicio"]])}
    i = fatos.CAB_CHECKLIST_RONDA.index
    rel = {"sem_os_no_livro": len(sem_os), "casaram": len(linhas), "pct_data": q[7], "pct_usina": q[8],
           "pct_equipe": q[9], "pct_pessoa": q[10], "sem_usina": q[13], "sem_equipe": q[14],
           "com_sujidade": sum(1 for l in linhas if l[i("sujidade")] is not None),
           "com_vegetacao": sum(1 for l in linhas if l[i("vegetacao")] is not None),
           "dias": [min((l[i("data_id")] or 0) for l in linhas) if linhas else None,
                    max((l[i("data_id")] or 0) for l in linhas) if linhas else None]}
    return tabelas, rel


def main():
    export = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    app = create_app()
    s = requests.Session()
    with app.app_context():
        tabelas, rel = montar(app.config, s, export)
        if "--gravar" in sys.argv:
            rel["gravado"] = livros.publicar(LIVRO, NOME, tabelas, base=carga._base(app.config),
                                             token=app.config["GRIDCO_SQL_TOKEN"], sessao=s)
        else:
            rel["ensaio"] = "montado com o dado real; nada gravado"
    print(json.dumps(rel, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
