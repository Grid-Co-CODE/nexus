"""As fontes novas do dossiê da usina: a programação do PCM e o que o contrato pede (19/11/2026).

Levi, 19/11/2026: "Fontes novas, nesta ordem: Programação do PCM: confirme se a semana seguinte já está no banco antes da
segunda. Contratos: garantia de disponibilidade, PR próprio e prazos de atendimento, sem valores em reais". Medido no banco
no mesmo dia: o PCM publica a semana seguinte na sexta à noite; até lá o dossiê diz "ainda não publicou", nunca "nada
programado". Usinas, clientes e regras inventados."""
import re
from datetime import date, datetime

from nexus.comando import dossie as DS
from nexus.comando import dossie_fontes as DF

HOJE = date(2026, 11, 19)                      # quinta: a semana corrente é a de 16/11, a seguinte a de 23/11
AGORA = datetime(2026, 11, 19, 10, 0)


def _bloco(usina, dia, hora, os=19515, tipo="Preventiva", status="nao_iniciada", minutos=60, semana=20261116, repro=0):
    return {"usina_id": usina, "data_id_semana": semana, "data_id_programada": dia, "hora_inicio": hora, "os": os,
            "tipo_tarefa": tipo, "status_execucao": status, "duracao_min": minutos, "reprogramada": repro}


# ── a programação do PCM ─────────────────────────────────────────────────────────────────────────────────────────────
def test_a_programacao_junta_os_blocos_da_tarefa_por_dia_os_e_tipo():
    linhas = [_bloco(7, 20261116, "11:51", minutos=126, status="finalizada"), _bloco(7, 20261116, "09:30", minutos=126),
              _bloco(7, 20261117, "08:15", tipo="Religamento", os=19749, minutos=10, repro=1),
              _bloco(8, 20261116, "07:00"), _bloco(7, 20261109, "07:00", semana=20261109)]
    p = DF.programacao_da_usina(linhas, 7, HOJE)
    c = p["corrente"]
    assert c["periodo"] == "16/11 a 22/11" and p["seguinte"]["periodo"] == "23/11 a 29/11" and c["a_mais"] == 0
    assert [(t["dia"], t["hora"], t["tipo"], t["os"], t["min"], t["blocos"]) for t in c["tarefas"]] == [
        ("seg 16/11", "09:30", "Preventiva", "19515", 252, 2), ("ter 17/11", "08:15", "Religamento", "19749", 10, 1)]
    assert c["tarefas"][0]["status"] == {"finalizada": 1, "não iniciada": 1} and not c["tarefas"][0]["reprogramada"]
    assert c["tarefas"][1]["reprogramada"]
    assert not p["seguinte_publicada"] and p["seguinte"]["tarefas"] == []


def test_a_semana_seguinte_publicada_e_do_fato_inteiro_e_nao_da_usina():
    p = DF.programacao_da_usina([_bloco(8, 20261123, "07:00", semana=20261123)], 7, HOJE)
    assert p["seguinte_publicada"] and p["seguinte"]["tarefas"] == [] and p["corrente"]["tarefas"] == []


def test_a_usina_com_muitas_tarefas_mostra_as_primeiras_e_conta_o_resto():
    linhas = [_bloco(7, 20261116 + d, f"{8 + h:02d}:00", os=20000 + d * 10 + h) for d in range(5) for h in range(8)]
    c = DF.programacao_da_usina(linhas, 7, HOJE)["corrente"]
    assert len(c["tarefas"]) == DF.MAX_TAREFAS and c["a_mais"] == 40 - DF.MAX_TAREFAS


# ── o contrato ───────────────────────────────────────────────────────────────────────────────────────────────────────
REGRAS = [
    {"categoria": "Disponibilidade e desempenho", "nome": "Disponibilidade garantida",
     "vigente": "Disponibilidade mínima de 98,5% ao mês", "ref": {"clausula": "5.1"}},
    {"categoria": "Disponibilidade e desempenho", "nome": "PR mínimo",
     "vigente": "PR anual de 78%; abaixo disso, desconto de R$ 1.500,00 por ponto", "ref": {"clausula": "5.3"}},
    {"categoria": "SLA", "nome": "Atendimento emergencial", "prazo": "4 h", "vigente": "Chegar à usina em até 4 horas",
     "ref": {"clausula": "7.2"}},
    {"categoria": "SLA", "nome": "Atendimento emergencial", "prazo": "4 h", "vigente": "Chegar à usina em até 4 horas",
     "ref": {"clausula": "7.2"}},
    {"categoria": "Penalidades", "nome": "Multa por atraso", "vigente": "R$ 10.000,00 por dia"},
    {"categoria": "Medição e faturamento", "nome": "Mensalidade", "vigente": "R$ 50.000,00"},
]
FICHAS = {"Cliente Alfa Energia": {"contratos": [{"usinas": [{"nome": "Usina Um"}], "regras": REGRAS}]}}


def test_o_contrato_traz_a_garantia_o_pr_e_os_prazos_sem_nenhum_valor_em_reais():
    c = DF.contrato_da_usina(FICHAS, "cliente alfa energia", "Usina Um")
    assert c["contratos"] == 1 and c["ligada"] and c["garantia"]["pct"] == 98.5 and c["garantia"]["clausula"] == "5.1"
    assert [d["nome"] for d in c["desempenho"]] == ["PR mínimo"]              # a garantia não se repete na lista
    assert c["desempenho"][0]["texto"] == "PR anual de 78%; abaixo disso, desconto de (valor no contrato) por ponto"
    assert [(s["nome"], s["prazo"], s["clausula"]) for s in c["sla"]] == [("Atendimento emergencial", "4 h", "7.2")]
    assert "R$" not in str(c) and "Multa" not in str(c) and "Mensalidade" not in str(c)


def test_o_cliente_sem_pdf_lido_nao_tem_contrato_e_o_de_varios_contratos_liga_pela_usina():
    assert DF.contrato_da_usina(FICHAS, "Cliente Beta", "Usina X") == {"contratos": 0}
    assert DF.contrato_da_usina(None, "Cliente Alfa Energia", "Usina Um") == {"contratos": 0}
    fichas = {"Cliente Alfa": {"contratos": [
        {"usinas": [{"nome": "UFV Usina Um"}], "regras": [{"categoria": "SLA", "nome": "Emergencial", "prazo": "4 h"}]},
        {"usinas": [{"nome": "UFV ALF200 (Usina Dois)"}], "regras": [{"categoria": "SLA", "nome": "Emergencial", "prazo": "8 h"}]}]}}
    um = DF.contrato_da_usina(fichas, "Cliente Alfa", "Usina Um")
    assert um["contratos"] == 2 and um["ligada"] and [s["prazo"] for s in um["sla"]] == ["4 h"]
    dois = DF.contrato_da_usina(fichas, "Cliente Alfa", "Outro nome no cadastro", codigo="alf200")     # pelo código
    assert dois["ligada"] and [s["prazo"] for s in dois["sla"]] == ["8 h"]
    tres = DF.contrato_da_usina(fichas, "Cliente Alfa", "Usina Três")
    assert not tres["ligada"] and [s["prazo"] for s in tres["sla"]] == ["4 h", "8 h"] and tres["garantia"] is None


# ── no dossiê ────────────────────────────────────────────────────────────────────────────────────────────────────────
def _dossie(extras):
    return DS.montar({"x": {"usina": "Usina Um", "insights": None}, "cu": {}, "p": {}}, AGORA, extras=extras)["texto"]


def _secao(texto, titulo):
    return re.split(r"^## \d+\. ", texto.split(f". {titulo}\n", 1)[1], maxsplit=1, flags=re.M)[0]


def test_as_duas_secoes_entram_antes_do_que_ficou_de_fora_sem_mexer_no_numero_das_antigas():
    texto = _dossie({})
    titulos = re.findall(r"^## (\d+)\. (.+)$", texto, flags=re.M)
    assert titulos[3:5] == [("4", "COS"), ("5", "OS e manutenção")]            # o pedido da IA cita o §4 e o §5
    assert titulos[-3:] == [("17", "Programação do PCM"), ("18", "Contrato"), ("19", "O que ficou de fora")]
    assert f"(formato {DS.VERSAO})" in texto and DS.VERSAO >= 8


def test_a_programacao_no_dossie_diz_a_janela_e_nao_confunde_nao_publicada_com_nada_programado():
    linhas = [_bloco(7, 20261116, "09:30", minutos=126), _bloco(7, 20261116, "11:51", minutos=126, status="finalizada"),
              _bloco(7, 20261117, "08:15", tipo="Religamento", os=19749, minutos=10, repro=1)]
    s = _secao(_dossie({"programacao": DF.programacao_da_usina(linhas, 7, HOJE)}), "Programação do PCM")
    assert "- Janela: a semana corrente e a seguinte" in s and "sexta à noite" in s
    assert "- Semana corrente (16/11 a 22/11): 2 tarefas programadas" in s
    assert "  - seg 16/11 09:30 · Preventiva · OS 19515 · 4 h 12 em 2 blocos · 1 não iniciada, 1 finalizada" in s
    assert "  - ter 17/11 08:15 · Religamento · OS 19749 · 10 min · não iniciada · reprogramada" in s
    varias = [_bloco(7, 20261118, f"{8 + n:02d}:00", status=st) for n, st in enumerate(
        ["finalizada", "finalizada", "nao_iniciada", "nao_iniciada", "em_progresso", "em_progresso", "pausada"])]
    s2 = _secao(_dossie({"programacao": DF.programacao_da_usina(varias, 7, HOJE)}), "Programação do PCM")
    assert "em 7 blocos · 2 não iniciadas, 2 em andamento, 1 pausada, 2 finalizadas" in s2
    assert "- Semana seguinte (23/11 a 29/11): o PCM ainda não publicou. Não quer dizer que não há nada programado." in s
    # publicada e sem nada para a usina: aí sim "nenhuma tarefa"
    s = _secao(_dossie({"programacao": DF.programacao_da_usina([_bloco(8, 20261123, "07:00", semana=20261123)], 7, HOJE)}),
               "Programação do PCM")
    assert "- Semana seguinte (23/11 a 29/11): nenhuma tarefa programada para esta usina." in s
    assert "- Semana corrente (16/11 a 22/11): nenhuma tarefa programada para esta usina." in s


def test_o_contrato_no_dossie_diz_a_garantia_o_pr_e_os_prazos_e_nunca_um_valor():
    s = _secao(_dossie({"contrato": DF.contrato_da_usina(FICHAS, "Cliente Alfa Energia", "Usina Um")}), "Contrato")
    assert "- Janela: o contrato como está hoje no Comando › Contratos" in s and "Valores em reais não entram" in s
    assert "- Garantia de disponibilidade: 98,5% (cláusula 5.1): Disponibilidade mínima de 98,5% ao mês" in s
    assert "  - PR mínimo (cláusula 5.3): PR anual de 78%; abaixo disso, desconto de (valor no contrato) por ponto" in s
    assert "- Prazos de atendimento (SLA): 1" in s and "  - Atendimento emergencial: 4 h (cláusula 7.2)" in s
    assert "R$" not in s and "Multa" not in s


def test_sem_leitura_e_sem_contrato_lido_ficam_escritos_e_entram_no_que_ficou_de_fora():
    texto = _dossie({"programacao": None, "contrato": None})
    assert "- Sem leitura da programação do PCM agora. Não quer dizer que não há nada programado." in texto
    assert "- Sem leitura do Comando › Contratos agora." in texto
    fora = texto.split("O que ficou de fora", 1)[1]
    assert "- a programação do PCM" in fora and "- o Comando › Contratos (a garantia e os prazos do contrato)" in fora
    s = _secao(_dossie({"contrato": {"contratos": 0}}), "Contrato")
    assert "- Sem dado: o contrato deste cliente ainda não foi lido no Comando › Contratos" in s
    s = _secao(_dossie({"contrato": DF.contrato_da_usina({"Cliente Alfa": {"contratos": [{"usinas": [], "regras": [
        {"categoria": "SLA", "nome": "Emergencial", "prazo": "4 h"}]}]}}, "Cliente Alfa", "Usina Um")}), "Contrato")
    assert "- Garantia de disponibilidade: o contrato lido não traz um percentual garantido (sem dado; não é 0%)." in s


def test_o_como_ler_explica_as_duas_secoes():
    texto = _dossie({})
    assert "PLANEJADO" in texto.split("## 1. ", 1)[0] and "garantia do contrato" in texto.split("## 1. ", 1)[0]


# ── a tela: quem lê o banco e entrega as linhas ──────────────────────────────────────────────────────────────────────
def test_os_extras_do_dossie_leem_a_programacao_e_o_contrato_uma_vez_para_todas_as_usinas(app, monkeypatch):
    """O Insights de madrugada monta 144 dossiês em fila: a programação das duas semanas e as fichas dos contratos são
    lidas UMA vez (cópia de 10 minutos por app), e cada usina tira a parte dela."""
    from nexus.campo import responsaveis as R
    from nexus.campo import visao
    from nexus.torres import comando as TC
    from nexus.torres.comando import gerencial_tela as GT
    lidas = {"programacao": 0, "contratos": 0}

    def programacao(segundas, listagem=None):
        lidas["programacao"] += 1
        assert segundas == {20261116, 20261123}
        return [_bloco(7, 20261116, "09:30"), _bloco(8, 20261117, "10:00", os=20001)]

    def contratos(hoje):
        lidas["contratos"] += 1
        return {"fichas": FICHAS}, None
    monkeypatch.setattr(R, "_programacao_recente", programacao)
    monkeypatch.setattr(GT, "_contratos", contratos)
    monkeypatch.setattr(visao, "_agora", lambda: AGORA)
    with app.test_request_context():
        e7 = TC._extras_do_dossie(7, "ALF100", {"cliente": "Cliente Alfa Energia", "usina": "Usina Um"})
        e8 = TC._extras_do_dossie(8, "ALF200", {"cliente": "Cliente Sem Contrato", "usina": "Usina Oito"})
    assert [t["os"] for t in e7["programacao"]["corrente"]["tarefas"]] == ["19515"]
    assert [t["os"] for t in e8["programacao"]["corrente"]["tarefas"]] == ["20001"]
    assert e7["contrato"]["garantia"]["pct"] == 98.5 and e8["contrato"] == {"contratos": 0}
    assert lidas == {"programacao": 1, "contratos": 1}


def test_a_fonte_que_nao_abre_nao_fica_guardada_e_vai_para_o_que_ficou_de_fora(app, monkeypatch):
    from nexus.campo import responsaveis as R
    from nexus.campo import visao
    from nexus.torres import comando as TC
    from nexus.torres.comando import gerencial_tela as GT
    estado = {"ok": False}

    def programacao(segundas, listagem=None):
        if not estado["ok"]:
            raise RuntimeError("banco fora")
        return [_bloco(7, 20261116, "09:30")]
    monkeypatch.setattr(R, "_programacao_recente", programacao)
    monkeypatch.setattr(GT, "_contratos", lambda hoje: (None, "os contratos (a carga inicial não está neste servidor)"))
    monkeypatch.setattr(visao, "_agora", lambda: AGORA)
    with app.test_request_context():
        e = TC._extras_do_dossie(7, "", {"cliente": "Cliente Alfa Energia", "usina": "Usina Um"})
        assert e["programacao"] is None and e["contrato"] is None
        estado["ok"] = True                              # o banco volta: a leitura seguinte já vem (o erro não se guarda)
        assert TC._extras_do_dossie(7, "", {})["programacao"]["corrente"]["tarefas"]
