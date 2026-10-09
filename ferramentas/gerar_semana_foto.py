"""Gera uma semana no Nexus com a FOTO do Fracttal, sem ler o Fracttal (`nexus.pcm.geracao.gerar_com_foto`).

Para que serve: provar mudança no motor ou nos insumos, e comparar com a semana oficial do PCM partindo do MESMO
Fracttal. O motor do PCM grava, na pasta dele, os caches do que leu do Fracttal (`.cache_semanal_api.pkl` e
companhia); a rodada leva uma cópia deles, com o motor sem credencial e com o Fracttal numa porta fechada: se ele
tentar ler, falha. Ler o Fracttal horas depois muda a semana (S41, 02/10/2026: 157 tarefas a mais e 280 horários) e não
prova nada. Não gasta cota (200 pedidos/min da empresa inteira) e pode rodar no horário de campo.

Os insumos são os da geração da tela: os do Nexus, a AUXILIAR do cadastro e o histórico de antes da semana (do banco,
ou a reserva do Nexus com --historico nexus). A pasta do PCM só é lida. A rodada fica em
C:\\GridcoAuto\\nexus\\pcm\\geracoes\\<data>-<semana>-foto[-rotulo] e não entra na lista da tela.

Uso:
    python ferramentas/gerar_semana_foto.py --semana 2026-W42
    python ferramentas/gerar_semana_foto.py --semana 2026-W42 --historico nexus --rotulo hist-nexus
    python ferramentas/gerar_semana_foto.py --semana 2026-W42 --contra <rodada ou planilha>   compara linha a linha
    --foto PASTA    onde está a foto (padrão: a pasta do PCM desta máquina)
Imprime só contagens e números de OS: nenhum nome de pessoa.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nexus.pcm import comparar, geracao  # noqa: E402


def _planilha(p: Path) -> Path:
    """Uma rodada (a pasta) vale pela saída dela; uma planilha vale por si."""
    p = Path(p)
    return p / "saida" / "sombra.xlsx" if p.is_dir() else p


def relatorio(st: dict, origem: Path | None, contra: Path | None) -> dict:
    pasta = Path(st["_pasta"])
    saida = pasta / "saida" / "sombra.xlsx"
    rel = {k: st.get(k) for k in ("id", "semana", "estado", "duracao_s", "erro", "credencial", "historico", "resumo",
                                  "conferencia", "oficial", "comparacao")}
    rel["pasta"] = str(pasta)
    rel["foto"] = {"intacta": st["foto"].get("intacta"),
                   "arquivos": {n: c["de"] for n, c in st["foto"]["arquivos"].items()}}
    rel["insumos"] = [{k: i.get(k) for k in ("nome", "atualizado", "detalhe", "aviso") if i.get(k) not in (None, "")}
                      for i in st.get("insumos") or []]
    if st.get("estado") == "ok":
        n = int(st["semana"].split("W")[1])
        anterior = origem / f"Programação Semana {n - 1:02d}.xlsx" if origem else None
        if anterior and anterior.exists():
            rel["contra_a_semana_anterior"] = dict(comparar.entre_semanas(anterior, saida), arquivo=anterior.name)
        if contra:
            rel["contra"] = dict(comparar.comparar(_planilha(contra), saida), arquivo=str(_planilha(contra)))
    return rel


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--semana", default=None, help="2026-W42 (padrão: a da próxima segunda)")
    ap.add_argument("--historico", choices=("banco", "nexus"), default="banco")
    ap.add_argument("--foto", type=Path, default=None)
    ap.add_argument("--rotulo", default="")
    ap.add_argument("--contra", type=Path, default=None, help="rodada ou planilha para comparar linha a linha")
    a = ap.parse_args()
    from nexus import create_app
    app = create_app()
    cfg = app.config
    semana = a.semana or geracao.semana_padrao()
    st = geracao.gerar_com_foto(cfg, semana, foto=a.foto, historico=a.historico, rotulo=a.rotulo)
    st["_pasta"] = str(geracao.pasta_trabalho(cfg) / "geracoes" / st["id"])
    rel = relatorio(st, geracao.pasta_origem(cfg), a.contra)
    print(json.dumps(rel, ensure_ascii=False, indent=1, default=str))
    ok = st.get("estado") == "ok" and st["foto"].get("intacta")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
