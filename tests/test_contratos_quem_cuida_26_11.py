"""Comando > Contratos, 26/11/2026: Quem cuida de quê, a visão reduzida (`nexus/contratos/setores.py`).

As regras dos contratos juntadas em atividades com o setor dono, pela distribuição que a gestão deu: o COS com o tempo real
(usina ou equipamento parado, perda de comunicação), a Performance com a baixa geração, o desvio e o alarme menor, a
Manutenção (Supervisão de Campo) com o sobreaviso e a chegada ao local, o PCM com a resposta à falha. Tudo inventado (o
repositório é público)."""
from nexus.contratos import setores as S
from test_contratos_editavel_18_11 import _como, carga  # noqa: F401 — a fixture da carga inicial


def _r(i, cat, nome, texto, **k):
    return {"_id": i, "categoria": cat, "nome": nome, "contratual": texto, "vigente": None, **k}


def test_o_setor_de_cada_atividade():
    at = S.atividade
    assert at("Atendimento", _r(1, "SLA", "Sobreaviso fora do expediente", "Equipe de sobreaviso"))[1] == S.MAN
    # "sobreaviso" contém "aviso": antes caía no COS (o avisar a falha)
    assert at("Atendimento", _r(1, "SLA", "Chegada ao local: criticidade alta", "em até 4 h"))[1] == S.MAN
    assert at("Atendimento", _r(1, "SLA", "Resposta a falha: risco alto", "Perda de comunicação ou perda de geração maior que 30%"))[1] == S.COS
    assert at("Atendimento", _r(1, "SLA", "Evento menor: intervenção", "Evento menor = sem perda de energia e sem perda de comunicação"))[1] == S.PERF
    assert at("Atendimento", _r(1, "SLA", "Reporte de desvio operacional", "Reportar em até 1 dia"))[1] == S.PERF
    assert at("Atendimento", _r(1, "SLA", "Monitoramento remoto 24x7", "pelo centro de operação"))[1] == S.COS
    assert at("Atendimento", _r(1, "SLA", "Resposta a falha: risco crítico", "Ameaça à segurança de pessoas"))[1] == S.SEG
    assert at("Atendimento", _r(1, "SLA", "Correção de falha de baixa criticidade", "em até 5 dias úteis"))[1] == S.PCM
    # a roçada da zeladoria: o "\b" da regra (antes um caractere de controle, que nunca casava)
    assert at("Entregáveis", _r(1, "Entregáveis", "Relatório de roçada", "com fotos"))[1] == S.ZEL
    assert at("Financeiro", _r(1, "Medição e faturamento", "Troca de inversor", "x"))[1] != S.ZEL


def test_a_visao_reduzida_conta_a_regra_uma_vez_por_cliente():
    fichas = {
        "Solar Alfa": {"contratos": [
            {"regras": [_r("a1", "SLA", "Sobreaviso fora do expediente", "Equipe de sobreaviso", prazo="4 h"),
                        _r("a2", "SLA", "Resposta a falha: risco alto", "Perda de comunicação: até 6 h", prazo="6 h"),
                        _r("a3", "Rescisão", "Aviso de rescisão", "90 dias")]},
            {"regras": [_r("a4", "SLA", "Sobreaviso fora do expediente", "Equipe de sobreaviso", prazo="4 h")]}]},   # a mesma, noutro contrato
        "Solar Beta": {"contratos": [{"regras": [_r("b1", "SLA", "Sobreaviso no fim de semana", "Plantão")]}]}}
    d = S.montar(fichas)
    at = next(t for t in d["temas"] if t["nome"] == "Atendimento")
    assert (at["regras"], at["clientes"]) == (3, 2)
    sob = next(a for a in at["atividades"] if a["setor"] == S.MAN)
    assert sob["por_cliente"] == {"Solar Alfa": ["a1"], "Solar Beta": ["b1"]} and sob["origem"] == "Levi"
    cos = next(a for a in at["atividades"] if a["setor"] == S.COS)
    assert cos["tambem"] == ["Manutenção", "PCM"] and cos["regras"] == 1
    assert d["matriz"] == {S.MAN: {"Atendimento": 2}, S.COS: {"Atendimento": 1}}
    assert d["ordem"] == [S.COS, S.MAN]                                  # a rescisão não é dos quatro temas
    assert [a["setor"] for a in at["atividades"]] == [S.COS, S.MAN]       # na ordem dos setores


def test_a_tela_recebe_quem_cuida_de_que(carga, cliente):  # noqa: F811
    adm = _como(cliente, "admin@gridco.com.br", admin=True)
    d = adm.get("/t/comando/contratos/dados.json").get_json()
    q = d["quem_cuida"]
    assert [t["nome"] for t in q["temas"]] == ["Atendimento", "Entregáveis", "Metas", "Financeiro"]
    ids = {r["_id"] for f in d["fichas"].values() for k in f["contratos"] for r in k.get("regras") or []}
    assert all(i in ids for t in q["temas"] for a in t["atividades"] for v in a["por_cliente"].values() for i in v)
    js = cliente.get("/static/contratos.js").get_data(as_text=True)
    assert "function vQuem()" in js and 'href="#/quem"' in js
