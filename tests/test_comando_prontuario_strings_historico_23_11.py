"""O cartão Strings e trackers do prontuário com o histórico do mês (23/11/2026). A Performance, na Rodrigues 2: "strings
e tracker não mostra o histórico, só o que está em aberto no momento. É necessário que haja essa visualização"; o Levi
escolheu abrir com o mês inteiro. O cartão segue dizendo o que está fora agora e ganha, fechada, a lista de TODAS as
ocorrências do mês (as que voltaram e as abertas), da mais nova para a mais velha, com a volta e a perda."""
from datetime import date

from test_campo_responsaveis import HOJE, tela  # noqa: F401  (tela é fixture)
from test_campo_visao import banco  # noqa: F401  (banco é fixture)

from nexus.campo import visao
from nexus.comando import prontuario as PR

EP = {"strings": [
    {"mes": "2026-11", "inversor": "Inversor 2.1", "string": "Ipv22", "saiu": "2026-11-12 06:00", "voltou": "2026-11-23 06:00",
     "situacao": "voltou entre varreduras", "perda_kwh": 1099.4},
    {"mes": "2026-11", "inversor": "Inversor 1.1", "string": "Ipv12", "saiu": "2026-11-06 06:00", "voltou": "2026-11-06 15:20",
     "situacao": "voltou", "perda_kwh": 110.3},
    {"mes": "2026-11", "inversor": "Inversor 3.1", "string": "Ipv13", "saiu": "2026-11-20 08:00", "situacao": "em aberto",
     "perda_kwh": 12},
    {"mes": "2026-10", "inversor": "Inversor 1.2", "string": "Ipv10", "saiu": "2026-10-01 08:10", "voltou": "2026-11-01 06:00",
     "situacao": "voltou de madrugada", "perda_kwh": 3359.3}],                  # outro mês: fica fora do histórico
    "trackers": [{"mes": "2026-11", "tracker": "TRK41", "parou": "2026-11-15 09:00", "voltou": "2026-11-15 13:00",
                  "situacao": "voltou", "perda_kwh": 3.5, "cronico": "0"}]}


def test_o_historico_do_mes_traz_as_que_voltaram_e_as_abertas_da_mais_nova_para_a_mais_velha():
    st = PR.strings_trackers(EP, date(2026, 11, 23))
    assert [(h["tipo"], h["nome"], h["saiu"], h["voltou"], h["perda"]) for h in st["historico"]] == [
        ("string", "Inversor 3.1 · Ipv13", "20/11 08:00", "", "12,0 kWh"),
        ("tracker", "TRK41", "15/11 09:00", "15/11 13:00", "3,5 kWh"),
        ("string", "Inversor 2.1 · Ipv22", "12/11 06:00", "23/11 06:00", "1.099,4 kWh"),
        ("string", "Inversor 1.1 · Ipv12", "06/11 06:00", "06/11 15:20", "110,3 kWh")]
    assert [h["aberta"] for h in st["historico"]] == [True, False, False, False]
    # o que está fora agora não muda: só a Ipv13 segue aberta
    assert [(i["inversor"], i["strings"]) for i in st["inversores"]] == [("Inversor 3.1", ["Ipv13"])]
    assert PR.strings_trackers({}, date(2026, 11, 23))["historico"] == []


def test_o_cartao_mostra_o_historico_do_mes_fechado(tela, banco, logado):  # noqa: F811
    mes = f"{HOJE:%Y-%m}"
    banco._id("falhas_performance", "strings_episodios")["linhas"] = [
        {"headers": ["mes", "usina", "inversor", "string", "saiu", "voltou", "situacao", "perda_kwh"],
         "values": [mes, "Altair", "Inversor 2.1", "Ipv22", f"{mes}-01 06:00", f"{mes}-01 15:00", "voltou", 99.5]}]
    visao.limpar()
    h = logado.get("/t/campo/usinas/1").get_data(as_text=True)
    assert '<details class="pu-st-hist">' in h and "Histórico do mês (1)" in h
    assert "Inversor 2.1 · Ipv22" in h and "voltou 01/" in h and "99,5 kWh" in h
    assert "Nenhuma string fora nem tracker parado agora." in h                   # e o "agora" segue dito
