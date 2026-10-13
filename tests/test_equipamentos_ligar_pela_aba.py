"""Ligar pela aba Equipamentos (13/10/2026, Levi: "Em "Equipamentos da Usinas" ligue automaticamente pelos dados que temos
na aba equipamentos do BD_Performance!"). A chave da aba liga à usina do Registro mestre pela Usina Fractall dela, no
de-para do Fracttal das Ligações (o mesmo ciclo das Ligações entre bases), e a estrutura vem da aba. Não chuta: cada
chave que não liga sai com o motivo. Nenhum teste vai à rede: o banco é o falso."""
from test_base_equipamentos import _estado, app_eq, banco, cli  # noqa: F401  (fixtures)

from nexus.cadastro import estrutura_usina as E
from nexus.cadastro import ligacoes as L

FR = L.FRACTTAL


def _g(chave, fracttais=(), ufv=None, cabines=(), inversores=()):
    return {"chave": chave, "usina": chave, "fracttal": (list(fracttais) or [""])[0], "fracttais": list(fracttais),
            "cliente": "", "full_om": True, "string_box": False, "ufv_kwp": ufv, "ufv_inversores": None,
            "cabines": list(cabines), "inversores": list(inversores)}


ATUAL = {"linhas": [
    [1, FR, "Thopen - Brodowski 1 - SP", "código"],
    [3, FR, "Athon - Timon 1 - MA", "código"],
    [None, FR, "Grid Co. - Colíder 1", "ignorado: tarefa interna da Grid Co., não é usina"],
    [4, FR, "Thopen - Duas Usinas - SP", "nome"], [5, FR, "Thopen - Duas Usinas - SP", "nome"],
    [9, FR, "Thopen - Fora do Registro - SP", "código"],
    [None, "BD_Thopen · aba", "AP. do Taboado", "ignorado: buraco aceito: fora da operação da Grid (Levi, 04/10)"],
    [7, "BD_Performance · aba", "Brodowski Outra", "equipamentos → Fracttal (código)"],
]}


def test_a_proposta_liga_pela_usina_fractall_e_nao_chuta():
    aba = {"Brodowski": _g("Brodowski", ["Thopen - Brodowski 1 - SP"], ufv=1000.0),
           "Brodowski 1 (90)": _g("Brodowski 1 (90)", ["Thopen - Brodowski 1 - SP"]),
           "Timon": _g("Timon", ["Athon -  Timon 1 - MA"]),                    # dois espaços: o único de mesmo nome
           "Sem Nome": _g("Sem Nome"),
           "Rodrigues 2": _g("Rodrigues 2", ["Thopen - Rodrigues 1 - RN", "Thopen - Rodrigues 2 - RN"]),
           "Fora": _g("Fora", ["Thopen - Não Existe - SP"]),
           "Colider 1": _g("Colider 1", ["Grid Co. - Colíder 1"]),
           "Duas": _g("Duas", ["Thopen - Duas Usinas - SP"]),
           "Registro": _g("Registro", ["Thopen - Fora do Registro - SP"]),
           "AP. do Taboado": _g("AP. do Taboado", ["Thopen - Brodowski 1 - SP"]),
           "Brodowski Outra": _g("Brodowski Outra", ["Thopen - Brodowski 1 - SP"]),
           "Já": _g("Já", ["Thopen - Brodowski 1 - SP"])}
    est = {"supervisorios": [{"usina_supervisorio": "Já", "usina_id": 8, "excluido": False}]}   # ligada à mão, noutra
    p = E.proposta_pela_aba(aba, ATUAL, est, {1, 3, 4, 5, 7})
    assert p["ligar"] == {1: ["Brodowski", "Brodowski 1 (90)"], 3: ["Timon"]} and p["ja_ligadas"] == 1
    fora = {f["chave"]: f["motivo"] for f in p["fora"]}
    assert fora["Sem Nome"] == "sem a Usina Fractall na aba"
    assert fora["Rodrigues 2"].startswith("2 nomes do Fracttal na aba")
    assert "não está nas Ligações" in fora["Fora"]
    assert fora["Colider 1"].startswith("o nome do Fracttal está ignorado nas Ligações")
    assert "liga a 2 usinas" in fora["Duas"]
    assert fora["Registro"] == "a usina do nome do Fracttal não está no Registro mestre"
    # a aba dá à AP. do Taboado o nome do Fracttal de outra usina: as Ligações a ignoram, e ela fica de fora
    assert fora["AP. do Taboado"].startswith("a chave está ignorada nas Ligações")
    assert fora["Brodowski Outra"] == "as Ligações ligam esta chave a outra usina (id 7)"
    # a usina que já tem estrutura gravada não entra no botão: a chave nova dela vai para a lista, com o que fazer
    est["inversores"] = [{"usina_id": 3, "excluido": False}]
    p = E.proposta_pela_aba(aba, ATUAL, est, {1, 3, 4, 5, 7})
    assert 3 not in p["ligar"] and "já tem estrutura gravada" in {f["chave"]: f["motivo"] for f in p["fora"]}["Timon"]


def test_a_estrutura_vem_da_aba_como_o_trazer_da_tela():
    aba = {"Altair": _g("Altair", ufv=2000.0, cabines=[{"nome": "UG 01", "kwp": 1000.0}, {"nome": "UG 02", "kwp": 1000.0}]),
           "Altair 1 (73)": _g("Altair 1 (73)", inversores=[
               {"nome": "Inversor 1", "equipamento_supervisorio": "INVERSOR01", "cabine": "UG 01", "kwp": 500.0, "strings": 20},
               {"nome": "Inversor 2", "equipamento_supervisorio": "INVERSOR01", "cabine": "UG 01", "kwp": 500.0, "strings": 20}]),
           "Altair 2 (74)": _g("Altair 2 (74)", inversores=[
               {"nome": "Inversor 1", "equipamento_supervisorio": "INVERSOR01", "cabine": "UG 03", "kwp": None, "strings": 18}])}
    e = E.estrutura_da_aba(["Altair 2 (74)", "Altair 1 (73)", "Altair"], aba)
    assert [(s["chave"], s["principal"]) for s in e["supervisorios"]] == [("Altair", True), ("Altair 1 (73)", False),
                                                                          ("Altair 2 (74)", False)]
    # a UG 03 só aparece como Equipamento Parente: a cabine nasce sem potência
    assert [(c["nome"], c["potencia_kwp"]) for c in e["cabines"]] == [("UG 01", 1000.0), ("UG 02", 1000.0), ("UG 03", None)]
    assert [(i["chave"], i["nome"], i["cabine"]) for i in e["inversores"]] == [
        ("Altair 1 (73)", "Inversor 1", "UG 01"), ("Altair 2 (74)", "Inversor 1 · Altair 2 (74)", "UG 03")]
    assert e["avisos"] == ["Altair 1 (73): “INVERSOR01” duas vezes no supervisório (ficou o 1º)"]


def test_o_botao_liga_e_grava_a_estrutura_e_a_segunda_vez_nao_muda_nada(cli, banco):  # noqa: F811
    html = cli.get("/t/base/equipamentos").get_data(as_text=True)
    assert "Ligar 3 chaves em 1 usina" in html and "Pedra do Sal" in html and "sem a Usina Fractall na aba" in html
    r = cli.post("/t/base/equipamentos/ligar-aba", data={})
    aviso = cli.get(r.headers["Location"]).get_data(as_text=True)
    assert "Ligado pela aba Equipamentos: 3 chave(s) em 1 usina(s), com 2 cabine(s), 4 inversor(es)" in aviso
    e = _estado(banco)
    sup = {s["usina_supervisorio"]: s for s in e["sup"]}
    assert set(sup) == {"Brodowski", "Brodowski 1 (90)", "Brodowski 2 (91)"} and str(sup["Brodowski"]["principal"]) == "1"
    assert all(str(s["substitui_aba"]) == "0" for s in e["sup"])               # nada vai "no lugar da aba" sozinho
    inv = {i["nome"]: i for i in e["inv"]}
    assert set(inv) == {"Inversor 1.1", "Inversor 1.2", "Inversor 2.1", "Inversor 2.2"}
    assert inv["Inversor 1.1"]["equipamento_supervisorio"] == "INVERSOR01" and float(inv["Inversor 1.1"]["potencia_kwp"]) == 250
    r = cli.post("/t/base/equipamentos/ligar-aba", data={})
    assert "Nada novo para ligar pela aba" in cli.get(r.headers["Location"]).get_data(as_text=True)
    assert len(_estado(banco)["inv"]) == 4


def test_usina_com_estrutura_feita_a_mao_fica_como_esta(cli, banco):  # noqa: F811
    r = cli.post("/t/base/equipamentos/chave", data={"usina": 1, "acao": "ligar", "chave": "Outra Chave"})
    assert r.status_code == 303
    html = cli.get("/t/base/equipamentos").get_data(as_text=True)
    assert "Nada novo para ligar pela aba" in html and "já tem estrutura gravada" in html
    r = cli.post("/t/base/equipamentos/ligar-aba", data={})
    assert "Nada novo para ligar pela aba" in cli.get(r.headers["Location"]).get_data(as_text=True)
    assert {s["usina_supervisorio"] for s in _estado(banco)["sup"]} == {"Outra Chave"}
