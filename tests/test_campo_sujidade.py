"""Sujidade e vegetação na tela Rondas (Levi, 05/10/2026: "Em rondas quero uma visão focando em sujidade e vegetação, é
importante!"): as respostas da ronda lidas do texto que o App escreve na OS do Fracttal, e a conta por usina."""
from test_campo_visao import _dia, banco  # noqa: F401  (fixture)

from nexus.campo import aprovacao, regras_app, ronda_checklist, visao

NOTA = ("Ronda 2026-10-05 · Thopen - Ibaté 2 - SP · qualidade 80% · duração real 82 min (17:30 às 18:52) — "
        "Computador: Ligado; CFTV: Ligado; Sujidade da vala de drenagem: Parcial; Piranômetro GHI (estação "
        "solarimétrica): Não se aplica; Piranômetro IPOA (mesa tracker, plano dos módulos): Sujo; Albedômetro (mesa "
        "tracker, voltado ao solo): Limpo; Sujidade dos módulos: 4; Altura da vegetação: 2; As luvas isolantes estão "
        "disponíveis?: Sim")


def test_le_as_respostas_do_texto_da_os_de_ronda():
    r = ronda_checklist.ler_nota(NOTA)
    assert (r["sujidade"], r["vegetacao"], r["vala"]) == (4, 2, "Parcial")
    assert r["sensores_sujos"] == ["IPOA"]
    assert ronda_checklist.ler_nota("Ronda sem checklist")["sujidade"] is None
    assert ronda_checklist.ler_nota(NOTA.replace("módulos: 4", "módulos: 9"))["sujidade"] is None   # fora de 1 a 5


def test_respostas_juntam_a_fila_e_as_aprovadas():
    ronda_checklist.limpar()
    regras_app._FILA_CACHE.update(linhas=[{"wo_folio": "500", "description": "Ronda Longa — Altair", "note": NOTA},
                                          {"wo_folio": "501", "description": "Preventiva", "note": NOTA}])
    ronda_checklist._APROVADAS["resp"] = {"400": {**ronda_checklist.ler_nota(NOTA.replace("módulos: 4", "módulos: 2")),
                                                  "fim": "2026-10-05"}}
    ronda_checklist._APROVADAS["carregado"] = True
    try:
        r = ronda_checklist.respostas()
        assert set(r) == {"500", "400"} and r["500"]["sujidade"] == 4 and r["400"]["sujidade"] == 2
    finally:
        regras_app._FILA_CACHE.update(linhas=None)
        ronda_checklist.limpar()


def test_ultima_leitura_por_usina_com_a_anterior(banco):  # noqa: F811
    d = visao.rondas().dados
    # as duas rondas da Altair têm a mesma OS (500) no banco falso: a anterior vem da mesma resposta
    resp = {"500": ronda_checklist.ler_nota(NOTA)}
    s = visao.sujidade_vegetacao(d["todas"], d["cobertura"], resp, 30, d["hoje"])
    assert [x["usina"] for x in s["linhas"]] == ["Altair"]
    x = s["linhas"][0]
    assert (x["sujidade"], x["vegetacao"], x["sensores_sujos"], x["data"]) == (4, 2, ["IPOA"], _dia(1))
    r = s["resumo"]
    assert (r["sujidade_alta"], r["vegetacao_alta"], r["sensores"], r["vala"]) == (1, 0, 1, 1)
    assert r["dist_sujidade"][4] == 1 and (r["com_leitura"], r["usinas"]) == (1, 3)


def test_aba_de_sujidade_e_vegetacao(banco, logado, monkeypatch):  # noqa: F811
    monkeypatch.setattr(ronda_checklist, "respostas", lambda: {"500": ronda_checklist.ler_nota(NOTA)})
    monkeypatch.setattr(ronda_checklist, "pedir_releitura", lambda app=None: None)
    monkeypatch.setattr(ronda_checklist, "estado", lambda: {"lendo": False, "erro": "", "lidas": True, "fila": True})
    monkeypatch.setattr(aprovacao, "_pedir_releitura", lambda: None)
    html = logado.get("/t/campo/rondas?aba=sujidade").get_data(as_text=True)
    assert "Sujidade e vegetação" in html and "Altura da vegetação" in html
    # 08/10: o número só com a cor da fonte, e o Status diz o porquê (sujidade 4, vala parcial, IPOA sujo)
    assert 'class="cn-nivel-txt cn-nivel-txt--4">4<' in html and "IPOA" in html and "Parcial" in html
    assert "Sujidade alta" in html and "Vala parcial" in html and "Sensor sujo (IPOA)" in html
    # os botões de filtro saíram (Levi: "se a pessoa quiser ordenar ela clica na coluna"): sv= não filtra mais
    assert "sv=" not in html and "Altair" in logado.get("/t/campo/rondas?aba=sujidade&sv=vegetacao").get_data(as_text=True)


def _pagina(inicio, n=100, fim="2026-10-05"):
    """Uma página da listagem de aprovadas: a 1ª OS de cada página é ronda (com resposta), o resto é outra coisa."""
    linhas = [{"wo_folio": str(1000 + inicio + i), "final_date": f"{fim}T12:00:00",
               "description": "Ronda Curta — Altair" if i == 0 else "Preventiva", "note": NOTA if i == 0 else ""}
              for i in range(n)]
    return {"data": linhas}


def test_aprovadas_guardam_o_que_veio_quando_o_fracttal_recusa(app, tmp_path, monkeypatch):
    """06/10: o 429 no meio da leitura jogava fora tudo; agora o que veio fica no arquivo e a próxima continua de onde
    parou (uma página antes, porque as novas empurram a lista)."""
    from nexus.campo import fracttal
    pedidos = []

    def ler(path):
        inicio = int(path.split("start=")[1].split("&")[0])
        pedidos.append(inicio)
        if inicio == 300 and len(pedidos) < 5:
            raise RuntimeError("o Fracttal recusou por excesso de pedidos (HTTP 429)")
        return _pagina(inicio, n=100 if inicio < 500 else 10)
    monkeypatch.setattr(fracttal, "ler", ler)
    monkeypatch.setattr(ronda_checklist, "PAUSA_S", 0)
    app.config.update(NEXUS_DADOS=str(tmp_path))
    ronda_checklist.limpar()
    try:
        with app.app_context():
            ronda_checklist._reler()
            e = ronda_checklist.estado()
            assert pedidos == [0, 100, 200, 300] and e["erro"] and not e["lidas"] and e["n"] == 3
            assert set(ronda_checklist.respostas()) == {"1000", "1100", "1200"}
            ronda_checklist.limpar()                      # reinício: volta do arquivo, sem pedir nada
            assert set(ronda_checklist.respostas()) == {"1000", "1100", "1200"}
            ronda_checklist._reler()                      # continua da página 200, não do começo
            assert pedidos[4:] == [200, 300, 400, 500]
            e = ronda_checklist.estado()
            assert e["lidas"] and not e["erro"] and e["ate"] == "2026-10-05" and e["n"] == 6
    finally:
        ronda_checklist.limpar()


def test_aprovadas_depois_da_primeira_vez_so_leem_as_novas(app, tmp_path, monkeypatch):
    """Lida uma vez por inteiro, a releitura para ao passar da última leitura completa (menos a margem): 1 página."""
    from nexus.campo import fracttal
    pedidos = []

    def ler(path):
        inicio = int(path.split("start=")[1].split("&")[0])
        pedidos.append(inicio)
        # da 2ª página em diante, OS aprovadas antes da última leitura completa
        return _pagina(inicio, fim="2026-10-05" if inicio == 0 else "2026-09-01")
    monkeypatch.setattr(fracttal, "ler", ler)
    monkeypatch.setattr(ronda_checklist, "PAUSA_S", 0)
    app.config.update(NEXUS_DADOS=str(tmp_path))
    ronda_checklist.limpar()
    try:
        with app.app_context():
            ronda_checklist._carregar()
            ronda_checklist._APROVADAS.update(ate="2026-10-04")
            ronda_checklist._reler()
            assert pedidos == [0, 100] and ronda_checklist.estado()["ate"] == "2026-10-05"
    finally:
        ronda_checklist.limpar()
