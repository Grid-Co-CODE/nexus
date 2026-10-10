"""Carga ÚNICA dos extintores no banco do Nexus (Levi, 09/10/2026: "traga para o banco do nexus agora"), antes de o App
publicar o livro dele.

Lê o cadastro inicial que o App de Campo usa (`extintores_cadastro.json`, gerado da planilha de controle da TST: 773
extintores em 81 usinas, com a última conferência do Forms da TST) e grava `extintores_app_campo · Extintores` no MESMO
contrato que o App vai publicar (`nexus.hseq.extintores.COLUNAS`). Quando o App começar a publicar (de hora em hora,
sync-xlsx com replace), a gravação dele substitui esta e traz as conferências feitas no App. Sem nome nem e-mail (a API
tem leitura aberta): a conferência do Forms vai sem "Conferido por" e a observação não vai. O status da TST é a regra do
App (`extintores.status_tst`, a mesma do `_ext_status`) no dia da carga, como o App faria ao publicar.

Depois de gravar, relê o livro e confere VALOR A VALOR com o que mandou (a API pode tipar a coluna: "12/2026" virar
data quebraria a conta das validades); qualquer diferença sai na tela e o comando termina com erro.

    python ferramentas/carregar_extintores_cadastro.py <extintores_cadastro.json>            mede e NÃO grava
    python ferramentas/carregar_extintores_cadastro.py <extintores_cadastro.json> --gravar   grava e confere
"""
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from nexus import create_app  # noqa: E402
from nexus.dados import carga, livros  # noqa: E402
from nexus.hseq import extintores as EXT  # noqa: E402

NOME = "Extintores pelo App (Nexus)"            # o mesmo display_name que o App usa ao criar o livro
CARGAS = {"CARREGADO": "CARREGADO", "SEM_CARGA": "SEM_CARGA", "SOBRECARGA": "SOBRECARGA"}


def linhas_do_cadastro(cad: dict, hoje) -> list[list]:
    """As linhas do livro (na ordem de COLUNAS), uma por extintor do cadastro, com a última conferência do Forms."""
    out = []
    for e in cad["extintores"]:
        u = e.get("ultima") or {}
        itens = u.get("itens") or {}
        nao = [k for k, v in itens.items() if str(v).upper() == "NAO"]
        dia = str(u.get("data") or "")[:10] or None
        carga_ = CARGAS.get(str(u.get("carga") or "").upper()) if dia else None
        st, motivo = (EXT.status_tst(carga_, set(nao), e.get("val2"), e.get("val3"), hoje) if dia else ("", ""))
        linha = {"Código": e["codigo"], "Usina": e["usina"], "Código da usina": e.get("cb"),
                 "Tipo de ativo": e.get("tipo"), "Ativo": e.get("ativo") or None, "Local": e.get("local"),
                 "Posição": e.get("posicao") or None, "Classe": e.get("classe") or None, "Peso (kg)": e.get("peso"),
                 "Validade da recarga": e.get("val2") or EXT.SEM_DATA,
                 "Validade do hidrostático": e.get("val3") or EXT.SEM_SELO, "Última conferência": dia,
                 "Origem da conferência": "Forms da TST" if dia else None, "Conferido por (HMAC)": None,
                 "Carga": carga_, "Itens NÃO": "; ".join(nao) or None, "Fotos": None, "Tem informação adicional": "não",
                 "Status": st or None, "Motivo": motivo or None, "Origem do cadastro": "Planilha da TST"}
        out.append([linha[c] for c in EXT.COLUNAS])
    return out


def _txt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        v = int(v)
    return str(v).strip()


def conferir(enviadas: list[list], lidas: list[dict]) -> Counter:
    """{coluna: linhas diferentes} entre o que foi mandado e o que o banco devolve, pela chave (Código)."""
    por_codigo = {_txt(l.get("Código")): l for l in lidas}
    dif = Counter()
    if len(por_codigo) != len(enviadas):
        dif["(linhas)"] = abs(len(por_codigo) - len(enviadas))
    for linha in enviadas:
        lido = por_codigo.get(_txt(linha[0])) or {}
        for c, v in zip(EXT.COLUNAS, linha):
            if _txt(v) != _txt(lido.get(c)):
                dif[c] += 1
    return dif


def main():
    cad = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    hoje = datetime.now(timezone(timedelta(hours=-3))).date()
    linhas = linhas_do_cadastro(cad, hoje)
    i = EXT.COLUNAS.index
    rel = {"extintores": len(linhas), "codigos_unicos": len({l[0] for l in linhas}),
           "usinas": len({l[i("Usina")] for l in linhas}), "dia_da_carga": hoje.isoformat(),
           "status": dict(Counter(l[i("Status")] or "sem conferência" for l in linhas)),
           "conferencias": [min(l[i("Última conferência")] for l in linhas if l[i("Última conferência")]),
                            max(l[i("Última conferência")] for l in linhas if l[i("Última conferência")])]}
    if rel["codigos_unicos"] != rel["extintores"]:
        sys.exit(f"código repetido no cadastro: {rel}")
    if "--gravar" not in sys.argv:
        rel["ensaio"] = "montado com o cadastro; nada gravado"
        print(json.dumps(rel, ensure_ascii=False, indent=1))
        return
    app = create_app()
    s = requests.Session()
    with app.app_context():
        base = carga._base(app.config)
        rel["gravado"] = livros.publicar(EXT.LIVRO, NOME, {EXT.ABA: (list(EXT.COLUNAS), linhas)}, base=base,
                                         token=app.config["GRIDCO_SQL_TOKEN"], sessao=s)
        dif = conferir(linhas, livros.ler(base, s, EXT.LIVRO, EXT.ABA))
    rel["diferencas_valor_a_valor"] = dict(dif) or "nenhuma"
    print(json.dumps(rel, ensure_ascii=False, indent=1))
    if dif:
        sys.exit(1)


if __name__ == "__main__":
    main()
