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
    ronda_checklist._APROVADAS["notas"] = {"400": NOTA.replace("módulos: 4", "módulos: 2")}
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
    assert 'class="cn-nivel cn-nivel--4">4<' in html and "IPOA" in html and "Parcial" in html
    html = logado.get("/t/campo/rondas?aba=sujidade&sv=vegetacao").get_data(as_text=True)
    assert "Nenhuma usina com leitura" in html                       # vegetação 2: não é alta
    html = logado.get("/t/campo/rondas?aba=sujidade&sv=sujidade").get_data(as_text=True)
    assert "Altair" in html
