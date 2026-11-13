"""O detalhe de um inversor na janela do Monitoramento (static/cos/inversores.js, 13/11/2026), as contas no node.

O dono: clicar num inversor e ver o gráfico dele "junto com o gráfico das strings dele, individual ou em grupo (por
exemplo por MPPT)". A regra das entradas é a da Ronda COS (entradas-do-inversor.ts), portada: a tela só afirma o MPPT que
o coletor declarou. A string não tem série gravada: o registro é da janela aberta, um ponto a cada 20 s, com buraco onde
não houve leitura. Ids fictícios (EXA01): o repositório é público."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parents[1] / "nexus" / "static" / "cos" / "inversores.js"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="sem node nesta máquina")


def rodar(corpo, *args):
    """Roda `corpo` no node com `N` = as contas do inversores.js e devolve o JSON que ele imprimir."""
    script = "require(process.argv[1]); const N = globalThis.NexusCosInversores; const A = process.argv.slice(2);\n" + corpo
    r = subprocess.run(["node", "-e", script, str(JS), *args], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def s(indice, corrente, mppt=None, **mais):
    return {"indice": indice, "mppt": mppt, "corrente": corrente, "sem_corrente": corrente is not None and corrente <= 0.05, **mais}


def mppt(indice, strings=(), tensao=650.0, corrente=10.0):
    return {"indice": indice, "nome": f"MPPT{indice}", "tensao": tensao, "corrente": corrente, "potencia": tensao * corrente / 1000,
            "corrente_strings": None, "discorda_das_strings": False, "strings": list(strings)}


# os formatos que chegam (os da Ronda COS): só strings (Huawei, SmartLogger), MPPT com strings (Sungrow SG75CX), só MPPT
# (SG125HV antigo) e nenhum dos dois (SG125HV do pacote novo); e as soltas ao lado de MPPT
HUAWEI = {"id": "EXA01:1", "mppts": [], "strings_sem_mppt": [s(1, 8.1), s(2, 0.0), s(3, None)]}
SUNGROW = {"id": "EXA02:1", "mppts": [mppt(1, [s(1, 9.0, 1), s(2, 0.0, 1)]), mppt(2, [s(3, 8.8, 2), s(4, 8.7, 2)])], "strings_sem_mppt": []}
SO_MPPT = {"id": "EXA03:1", "mppts": [mppt(1, tensao=700, corrente=50.0), mppt(2, tensao=702, corrente=49.0)], "strings_sem_mppt": []}
NADA = {"id": "EXA04:1", "mppts": [], "strings_sem_mppt": []}
MISTO = {"id": "EXA05:1", "mppts": [mppt(1, [s(1, 7.0, 1)])], "strings_sem_mppt": [s(5, 6.0), s(6, 6.1)]}


def vista(inv):
    return rodar("process.stdout.write(JSON.stringify(N.vistaDasEntradas(JSON.parse(A[0]))));", json.dumps(inv))


def entradas(inv):
    return rodar("process.stdout.write(JSON.stringify(N.entradasDoInversor(JSON.parse(A[0]))));", json.dumps(inv))


def test_a_vista_das_entradas_nos_quatro_formatos():
    v = vista(HUAWEI)
    assert v["titulo"] == "Strings (3)" and v["mppts"] == [] and not v["vazio"]
    assert v["rotuloSoltas"].startswith("O coletor não informa MPPT neste inversor")
    assert "não informa MPPT — por isso não há tensão na lista" in v["notaTensao"]
    assert v["teto"] == 8.1
    v = vista(SUNGROW)
    assert v["titulo"] == "MPPT e strings (2 MPPT · 4 strings)" and v["rotuloSoltas"] is None
    assert v["notaTensao"].endswith("a tensão mostrada é a do MPPT a que ela pertence.")
    v = vista(SO_MPPT)
    assert v["titulo"] == "MPPT (2)" and v["notaTensao"] is None and not v["temStrings"]
    v = vista(NADA)
    assert v["titulo"] == "MPPT e strings" and v["vazio"]
    v = vista(MISTO)
    assert v["titulo"] == "MPPT e strings (1 MPPT · 3 strings)" and v["rotuloSoltas"] == "Strings sem MPPT declarado (2)"


def test_o_nome_do_grupo_das_soltas_vale_para_cada_uma():
    # a string que declara um MPPT que a lista não traz não é "sem MPPT declarado"
    inv = {"id": "EXA06:1", "mppts": [mppt(1, [s(1, 7.0, 1)])], "strings_sem_mppt": [s(5, 6.0, 3)]}
    assert vista(inv)["rotuloSoltas"] == "Strings fora dos MPPT listados (1)"
    assert vista({"id": "EXA06:2", "mppts": [], "strings_sem_mppt": [s(1, 6.0, 3)]})["rotuloSoltas"].startswith("O coletor não lista MPPT")


def test_o_nome_da_string_e_o_do_coletor_so_quando_veio():
    assert rodar("process.stdout.write(JSON.stringify([N.nomeDaString({indice: 7}), N.nomeDaString({indice: 7, nome: ' PV7 '}),"
                 "N.nomeDaString({indice: 2, nome: ''})]));") == ["String7", "PV7", "String2"]


def test_as_series_nunca_inventam_mppt():
    e = entradas(HUAWEI)                                  # SmartLogger: strings sem MPPT, sem o "Por MPPT"
    assert e["tipo"] == "strings" and not e["porMppt"]
    assert [g["mppt"] for g in e["grupos"]] == [False] and e["grupos"][0]["nome"] == "Strings sem MPPT declarado"
    assert [x["chave"] for x in e["lista"]] == ["s1", "s2", "s3"] and e["lista"][2]["valor"] is None
    e = entradas(SUNGROW)                                 # MPPT declarado com strings: um grupo por MPPT
    assert e["porMppt"] and [(g["nome"], len(g["itens"])) for g in e["grupos"]] == [("MPPT1", 2), ("MPPT2", 2)]
    assert [x["grupo"] for x in e["lista"]] == ["m1", "m1", "m2", "m2"]
    e = entradas(MISTO)                                   # as soltas ao lado do MPPT ficam num grupo que se diz como tal
    assert [(g["chave"], g["mppt"]) for g in e["grupos"]] == [("m1", True), ("soltas", False)]
    e = entradas(SO_MPPT)                                 # sem string: a série é o MPPT, e não há o que agrupar
    assert e["tipo"] == "mppts" and not e["porMppt"] and [x["valor"] for x in e["lista"]] == [50.0, 49.0]
    assert entradas(NADA) == {"tipo": "nada", "lista": [], "grupos": [], "porMppt": False}
    # índice repetido (payload torto) não cola duas séries numa só
    dup = {"id": "EXA07:1", "mppts": [], "strings_sem_mppt": [s(1, 5.0), s(1, 6.0)]}
    assert [x["chave"] for x in entradas(dup)["lista"]] == ["s1", "s1~2"]


# 13/11/2026 10:00 em São Paulo (UTC−3)
T0 = 1794574800000


def test_o_registro_um_ponto_a_cada_20_s_com_buraco_onde_nao_houve_leitura():
    r = rodar("""
    const inv = JSON.parse(A[0]), t0 = +A[1], reg = N.novoRegistro("scada-exa01", t0), passos = [];
    passos.push(N.anotarRegistro(reg, [inv], t0));
    passos.push(N.anotarRegistro(reg, [inv], t0 + 3000));            // 3 s depois: não anota (um ponto a cada 20 s)
    const sem2 = JSON.parse(JSON.stringify(inv)); sem2.strings_sem_mppt.splice(1, 1);
    passos.push(N.anotarRegistro(reg, [sem2], t0 + 20000));          // a String2 não veio: buraco nela
    passos.push(N.anotarRegistro(reg, [], t0 + 40000));              // a leitura da usina estava velha: buraco em todas
    const nova = JSON.parse(JSON.stringify(inv)); nova.strings_sem_mppt.push({indice: 9, mppt: null, corrente: 4.5, sem_corrente: false});
    passos.push(N.anotarRegistro(reg, [nova], t0 + 60000));          // a String9 apareceu: o passado dela é buraco
    process.stdout.write(JSON.stringify({passos, t: reg.t, v: reg.v, s1: N.serieDoRegistro(reg, inv.id, "s1"),
      s2: N.serieDoRegistro(reg, inv.id, "s2"), s9: N.serieDoRegistro(reg, inv.id, "s9"),
      outro: N.serieDoRegistro(reg, "EXA99:1", "s1")}));
    """, json.dumps(HUAWEI), str(T0))
    assert r["passos"] == [True, False, True, True, True] and r["v"] == 4
    assert [round(m, 4) for m in r["t"]] == [600.0, round(600 + 1 / 3, 4), round(600 + 2 / 3, 4), 601.0]
    assert [p[1] for p in r["s1"]] == [8.1, 8.1, None, 8.1]
    assert [p[1] for p in r["s2"]] == [0.0, None, None, 0.0]
    assert [p[1] for p in r["s9"]] == [None, None, None, 4.5]
    assert r["outro"] == []


def test_o_registro_recomeca_na_virada_do_dia_e_guarda_no_maximo_15_h():
    t = T0 - (9 * 60 + 30) * 60000                     # 00:30: as 15 h de pontos cabem no mesmo dia
    r = rodar("""
    const inv = JSON.parse(A[0]), t0 = +A[1], reg = N.novoRegistro("scada-exa01", t0);
    for (let k = 0; k <= N.REG_MAX; k++) { N.anotarRegistro(reg, [inv], t0 + k * N.REG_MS); }
    const cheio = reg.t.length, primeiro = reg.t[0], serie = N.serieDoRegistro(reg, inv.id, "s1").length;
    const meia = t0 + 23.5 * 3600000 + 1000;                         // 00:00:01 do dia seguinte
    N.anotarRegistro(reg, [inv], meia);
    process.stdout.write(JSON.stringify({cheio, primeiro, serie, depois: reg.t.length, desde: reg.desde, meia, minuto: reg.t[0]}));
    """, json.dumps(HUAWEI), str(t))
    assert r["cheio"] == r["serie"] == 2700 and r["primeiro"] > 30       # o mais antigo saiu
    assert r["depois"] == 1 and r["desde"] == r["meia"] and r["minuto"] < 0.1


def test_as_marcas_do_eixo_de_um_trecho():
    assert rodar("process.stdout.write(JSON.stringify([N.marcasDoEixo(600, 610), N.marcasDoEixo(601.5, 700), N.marcasDoEixo(600, 600.2)]));") == [
        [600, 602, 604, 606, 608, 610], [630, 660, 690], [600]]


def test_sem_pedido_novo_so_os_dois_caminhos_de_sempre():
    # as strings vêm na resposta de 3 s do monitoramento: o detalhe não pede nada a mais nem a rota nenhuma nova
    texto = JS.read_text(encoding="utf-8")
    assert set(re.findall(r'pedir\("([^"]+)"', texto)) == {"/scada/monitoramento?entradas=separadas", "/scada/curva/"}
    assert "fetch(" in texto and texto.count("fetch(") == 3      # o refresh do login, o pedido direto e o pela porta
