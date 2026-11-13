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


def test_os_pedidos_sao_os_tres_caminhos_do_repasse_do_nexus():
    # as strings de AGORA vêm na resposta de 3 s do monitoramento; desde 13/11/2026 o histórico do dia vem do terceiro
    # caminho (`scada/entradas/<logger>/<modbus>?dia=`), e a curva leva o `?dia=`. Nada além do que o servidor repassa
    texto = JS.read_text(encoding="utf-8")
    assert set(re.findall(r'pedir\("([^"]+)"', texto)) == {"/scada/monitoramento?entradas=separadas", "/scada/curva/", "/scada/entradas/"}
    assert "fetch(" in texto and texto.count("fetch(") == 3      # o refresh do login, o pedido direto e o pela porta


def test_fechar_fecha_mesmo_com_o_inversor_aberto():
    # 13/11/2026, o dono: "o botão de fechar a tela de graficos nao ta funcionando". O `fechar()` zerava o detalhe ANTES
    # de limpar os gráficos; a limpeza chama o `aoMarcar` da curva do inversor, que lia `det.f` (já nulo): TypeError, e o
    # `dlg.close()` nunca chegava. Agora a limpeza vem antes, o fechamento fica num `finally`, e nenhum `aoMarcar` lê o
    # `det` global.
    texto = JS.read_text(encoding="utf-8")
    corpo = texto[texto.index("function fechar() {"):]
    corpo = corpo[: corpo.index("\n  }\n")]
    assert corpo.index("limparTodos()") < corpo.index("sairDoDetalhe()")
    assert corpo.index("finally") < corpo.index("dlg.close()")
    for trecho in texto.split("aoMarcar: function")[1:]:
        assert "det.f" not in trecho[: trecho.find("}") + 400].split("aoMarcar")[0][:400]


# --- o dia e o histórico das entradas (13/11/2026) ----------------------------------------------------------------------
# O dono: "como faço pra ver os gráficos de ontem ? precisamos armazenar por pelo menos 40 dias". A resposta é o contrato
# EntradasDoDia da Ronda COS (scada.entradas.ts): as correntes em centésimos de A, um ponto por balde de 5 min.

def historico(**mudar):
    r = {"usina_id": "EXA01", "modbus_id": 2, "dia": "2026-11-12", "hoje": "2026-11-13", "passo_min": 5,
         "primeiro_dia": "2026-11-10", "gravacao_desde": "2026-11-09", "unidades": {"s": "cA", "mv": "dV", "ma": "cA"},
         "strings": [{"indice": 1, "mppt": 1}, {"indice": 2, "mppt": 1}, {"indice": 3, "mppt": None}],
         "mppts": [{"indice": 1}],
         # 10:00, 10:05 e 10:20 de São Paulo (13:00Z...): entre 10:05 e 10:20 não houve balde
         "pontos": [{"em": "2026-11-12T13:00:00.000Z", "s": [812, 0, None], "mv": [6896], "ma": [812]},
                    {"em": "2026-11-12T13:05:00.000Z", "s": [820, 0, 455], "mv": [6900], "ma": [820]},
                    {"em": "2026-11-12T13:20:00.000Z", "s": [830, 5, 460], "mv": [6910], "ma": [835]}]}
    r.update(mudar)
    return r


def do_historico(r):
    return rodar("process.stdout.write(JSON.stringify(N.entradasDoHistorico(JSON.parse(A[0]))));", json.dumps(r))


def test_o_historico_vira_as_series_com_as_chaves_do_ao_vivo_e_buraco_onde_faltou_balde():
    h = do_historico(historico())
    # a mesma regra das entradas de agora: MPPT declarado com string, e a solta num grupo que se diz como tal
    assert h["ent"]["tipo"] == "strings" and h["ent"]["porMppt"]
    assert [(g["chave"], [x["chave"] for x in g["itens"]]) for g in h["ent"]["grupos"]] == [("m1", ["s1", "s2"]), ("soltas", ["s3"])]
    assert h["pontos"] == 3 and h["dia"] == "2026-11-12" and h["primeiroDia"] == "2026-11-10"
    s1 = h["series"]["s1"]
    assert [p[1] for p in s1] == [8.12, 8.2, None, 8.3]               # em A; o null no meio é o buraco de 10:05 a 10:20
    assert [round(p[0], 2) for p in s1] == [600, 605, 612.5, 620]
    assert [p[1] for p in h["series"]["s3"]] == [None, 4.55, None, 4.6]


def test_o_historico_do_so_mppt_e_do_que_nao_le_nada():
    so_mppt = do_historico(historico(strings=[], mppts=[{"indice": 1}, {"indice": 2}],
                                     pontos=[{"em": "2026-11-12T13:00:00.000Z", "s": [], "mv": [7001, 7020], "ma": [8050, None]}]))
    assert so_mppt["ent"]["tipo"] == "mppts" and not so_mppt["ent"]["porMppt"]
    assert so_mppt["series"] == {"m1": [[600, 80.5]], "m2": [[600, None]]}
    nada = do_historico(historico(strings=[], mppts=[], pontos=[]))
    assert nada["ent"]["tipo"] == "nada" and nada["series"] == {} and nada["pontos"] == 0


def test_a_ponta_ao_vivo_entra_depois_do_ultimo_balde_gravado():
    r = rodar("""
    const base = [[600, 8.1], [605, 8.2], [610, null]];
    process.stdout.write(JSON.stringify([
      N.comPontaDoRegistro(base, [[604, 9], [606, 8.3], [606.5, 8.4]]),     // só o que vem depois de 10:05
      N.comPontaDoRegistro(base, [[640, 8.5]]),                             // a janela abriu às 10:40: buraco no meio
      N.comPontaDoRegistro(base, []),
    ]));""")
    assert r[0] == [[600, 8.1], [605, 8.2], [610, None], [606, 8.3], [606.5, 8.4]]
    assert r[1] == [[600, 8.1], [605, 8.2], [610, None], [622.5, None], [640, 8.5]]
    assert r[2] == [[600, 8.1], [605, 8.2], [610, None]]


def test_o_aviso_diz_desde_quando_ha_historico():
    def aviso(hist, hoje=False, dia="2026-11-08", falhou=False, ponta=False):
        return rodar("process.stdout.write(JSON.stringify(N.avisoDoHistorico(JSON.parse(A[0]), A[1] === '1', A[2], A[3] === '1', A[4] === '1')));",
                     json.dumps(hist), "1" if hoje else "0", dia, "1" if falhou else "0", "1" if ponta else "0")
    vazio = lambda **m: {"pontos": 0, "dia": m.get("dia", "2026-11-08"), "primeiroDia": m.get("primeiro"), "desde": m.get("desde")}
    assert aviso(None) == "Lendo o histórico das strings do dia…"
    assert aviso(None, falhou=True).startswith("Não deu para ler o histórico das strings agora")
    assert aviso({"pontos": 5}) == ""
    # o dia de antes de a gravação começar: a frase do coordenador, com a data
    assert aviso(vazio(primeiro="2026-11-10", desde="2026-11-09")) == "O histórico das strings começou em 10/11."
    assert aviso(vazio()) == "O histórico das strings ainda não começou a ser gravado."
    assert aviso(vazio(dia="2026-11-12", desde="2026-11-09")).startswith("O coletor deste inversor não mandou string nem MPPT desde 09/11")
    assert aviso(vazio(dia="2026-11-12", primeiro="2026-11-10", desde="2026-11-09")).startswith("Nenhuma leitura de string gravada neste dia")
    assert aviso(vazio(dia="2026-11-13", primeiro="2026-11-13"), hoje=True, dia="", ponta=True).endswith(
        "Aparece a leitura ao vivo desde a abertura da janela.")


def test_o_dia_de_sao_paulo_ontem_e_o_limite_de_40_dias():
    r = rodar("""process.stdout.write(JSON.stringify([
      N.diaTexto(Date.UTC(2026, 10, 14, 2, 30)),       // 23:30 de 13/11 em São Paulo
      N.diaTexto(Date.UTC(2026, 10, 14, 3, 0)),        // 00:00 de 14/11
      N.diaMenos("2026-11-13", 1), N.diaMenos("2026-03-01", 1), N.diaMenos("2026-11-13", N.DIAS_ATRAS),
      N.diaCurto("2026-11-09")]));""")
    assert r == ["2026-11-13", "2026-11-14", "2026-11-12", "2026-02-28", "2026-10-04", "09/11"]
