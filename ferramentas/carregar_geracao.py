"""A geração em linhas (passo 6c do Kimball, 08/10/2026), à mão: o `bd_thopen` e o `bd_performance` viram
`nexus_geracao · fato_geracao_usina_dia` (e o inversor × dia, só medido). Ver `nexus/dados/geracao.py`.

    python ferramentas/carregar_geracao.py --ensaio                   monta com o dado real e NÃO grava
    python ferramentas/carregar_geracao.py --ensaio --de-para-local   idem, com o de-para CALCULADO agora (as bases
                                                                      de hoje + as decisões da tela Ligações), sem
                                                                      publicar: quanto ligaria depois da publicação
    python ferramentas/carregar_geracao.py --ensaio --xlsx PASTA      grava os dois xlsx na PASTA, para medir o tamanho

    python ferramentas/carregar_geracao.py --gravar [--forcar]       GRAVA (decisão 8 do Levi, 11/10/2026): o
                                                                      `nexus_geracao` e os livros do mês que mudaram,
                                                                      e confere; sem --forcar, pula se os BDs não
                                                                      subiram e recusa aba encolhida

No servidor quem grava é a carga de hora em hora (`carga.gerar_geracao`), só quando o BD_Thopen ou o BD_Performance
subiu. Os BDs são a fonte (o Levi preenche por API e à mão e sobe ao PG): aqui só se lê deles. O ensaio só faz GET na
API (leitura aberta); não lê o Fracttal. Imprime só contagens, nunca nome de usina.
"""
import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from nexus.cadastro import banco as B  # noqa: E402
from nexus.cadastro import ligacoes as L  # noqa: E402
from nexus.config import ler_ambiente  # noqa: E402
from nexus.dados import carga, geracao, livros  # noqa: E402

_BRT = timezone(timedelta(hours=-3))


class _Usina:
    def __init__(self, d: dict):
        self.id, self._d = str(int(float(d["usina_id"]))), d     # a API devolve 17 ou 17.0; o cadastro usa "17"

    def valor(self, c):
        return self._d.get("cliente_id") if c == "cliente" else self._d.get(c)


class CadastroDoBanco:
    """O que `banco.de_para` precisa do serviço do cadastro, lido do `cadastro_nexus` PUBLICADO (as duas máquinas leem
    igual; nada cifrado é aberto). Só para o ensaio: a publicação de verdade sai da tela Ligações."""

    def __init__(self, usinas: list[dict], clientes: list[dict]):
        self.usinas = [_Usina(u) for u in usinas if str(u.get("excluido") or "").lower() != "sim" and u.get("usina_id")]
        self.clientes = {str(int(float(c["cliente_id"]))): c.get("nome") for c in clientes if c.get("cliente_id")}

    def registros(self, entidade, incluir_excluidos=False):
        return self.usinas if entidade == "usinas" else []

    def titulo_de(self, entidade, ref):
        if ref in (None, ""):
            return ""
        return self.clientes.get(str(int(float(ref))), "") if entidade == "clientes" else ""


def de_para_local(config, usinas, clientes) -> list[dict]:
    """O de-para como a tela Ligações publicaria agora (sem gravar nada, nem o `de_para_atual.json`)."""
    linhas = B.de_para(CadastroDoBanco(usinas, clientes), L.fontes(config), L.carregar_regras(config))
    return [dict(zip(B.CAB_DE_PARA, l)) for l in linhas]


def medir(config, sessao=None, *, de_para_proprio=False, xlsx: Path | None = None, apelidos=None):
    """O relatório do ensaio (só contagens). Não grava no banco. A leitura e a montagem são as da carga
    (`carga.montar_geracao`, uma regra só); sem `apelidos`, lê os publicados em `nexus_equipamentos ·
    equipamento_apelido` (o equipamento do inversor vem só de lá)."""
    s = sessao or requests.Session()
    base = (config.get("GRIDCO_DB_API") or L.BASE_API).rstrip("/")
    t1 = time.time()
    de_para = None
    if de_para_proprio:
        cad = {a: livros.ler(base, s, "cadastro_nexus", a) for a in ("usinas", "clientes")}
        de_para = de_para_local(config, cad["usinas"], cad["clientes"])
    t_de_para = round(time.time() - t1, 1)
    tabelas, inversor, rel = carga.montar_geracao(config, s, datetime.now(_BRT), apelidos=apelidos, de_para=de_para)
    rel["tempo_s"]["de_para"] = t_de_para
    rel["de_para"] = "calculado agora (não publicado)" if de_para_proprio else "publicado"
    if xlsx:
        xlsx.mkdir(parents=True, exist_ok=True)
        for nome, t in ((geracao.LIVRO, tabelas),
                        (geracao.ABA_INVERSOR, {geracao.ABA_INVERSOR: (geracao.CAB_INVERSOR_DIA, inversor)})):
            t3 = time.time()
            conteudo = B.xlsx_bytes(t)
            (xlsx / f"{nome}.xlsx").write_bytes(conteudo)
            rel.setdefault("xlsx", {})[nome] = {"mb": round(len(conteudo) / 1e6, 2), "s": round(time.time() - t3, 1)}
    return rel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ensaio", action="store_true", help="monta e não grava")
    ap.add_argument("--gravar", action="store_true", help="grava o nexus_geracao e os meses que mudaram (confere)")
    ap.add_argument("--forcar", action="store_true", help="com --gravar: grava mesmo sem subida nova ou com aba encolhida")
    ap.add_argument("--de-para-local", action="store_true", help="usa o de-para calculado agora, sem publicar")
    ap.add_argument("--xlsx", type=Path, help="pasta onde gravar os xlsx para medir")
    a = ap.parse_args()
    if a.gravar:
        rel = carga.gerar_geracao(ler_ambiente(), gravar=True, forcar=a.forcar)
        rel.pop("abas", None)
        print(json.dumps(rel, ensure_ascii=False, indent=1, default=str))
        return
    if not a.ensaio:
        sys.exit("diga o modo: --ensaio (mede, não grava) ou --gravar (grava e confere)")
    rel = medir(ler_ambiente(), de_para_proprio=a.de_para_local, xlsx=a.xlsx)
    print(json.dumps(rel, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
