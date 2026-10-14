"""Os quatro relatórios do PCM na Central de emissão (14/10/2026, Levi: "Quero trazer esses quatro relatórios para a
plataforma, com as mesmas métricas e parâmetros e estilos"): Relatório diário de manutenção, Recuperação da tarde,
Fechamento da semana e Alerta da programação (nexus/pcm/relatorios).

Que as contas são as do Python do PCM, byte a byte, prova o `ferramentas/prova_relatorios_pcm.py` contra uma cópia do
repositório de lá (dado real, que não vem para este repositório público). Aqui, com um PCM de mentira: as contas que
importam, o formato brasileiro, o recorte, a tela, o setor PCM e os horários da emissão automática."""
import json
from datetime import datetime, timedelta

import pytest

from conftest import SENHA_TESTE
from nexus.cadastro import setores as S
from nexus.pcm.relatorios import TIPOS, agenda, arquivo, dados, emitir, regras
from test_campo_visao import banco  # noqa: F401  (fixture)
from test_setor_telas import ANA, BASE, _como, setores  # noqa: F401  (fixtures)

BRT = regras.BRT
DANI = "dani@exemplo.test"          # setor PCM


def _linha(os_id, dia, status, cliente="Cliente A", cluster="SP NORTE 01", resp="Pessoa Um", h_ini="07:00",
           h_fim="09:00", dur=2.0, desloc=0.5, **extra):
    return {"os_id": os_id, "dia": dia, "status": status, "cliente": cliente, "cluster": cluster, "responsavel": resp,
            "usina": f"{cliente} - Usina X - SP", "tarefa": f"[MPC] - Tarefa {os_id}", "tipo": "MPC", "duracao": dur,
            "desloc": desloc, "h_ini": h_ini, "h_fim": h_fim, "reprog": "Não", "vezes": 1, **extra}


BD = {
    "semana_ativa": "2026-W42",
    "semanas": [
        {"week": "2026-W42", "label": "Semana 42 · 12–16 Out 2026", "geradaEm": "2026-10-09T20:00:00Z",
         "dates": {"seg": "12/10", "ter": "13/10", "qua": "14/10", "qui": "15/10", "sex": "16/10"},
         "resumo": {"SP NORTE 01": {"hh_util": 50, "hh_disp": 44, "pend": 2},
                    "SC OESTE 01": {"hh_util": 20, "hh_disp": 44, "pend": 0}},
         "rows": [
             _linha(1001, "Segunda-feira", "Finalizados"),
             _linha(1002, "Segunda-feira", "Em progresso", h_ini="08:00", h_fim="10:00"),
             _linha(1003, "Segunda-feira", "Não iniciada", h_ini="14:00", h_fim="16:00"),
             _linha(1004, "Segunda-feira", "Finalizados", foraDoPlano=True),
             _linha(1005, "Terça-feira", "Finalizados"),
             _linha(1006, "Terça-feira", "pausado", cliente="Cliente B", cluster="SC OESTE 01", resp="Pessoa Dois",
                    h_ini="09:00", h_fim="25:00", dur=9.0, vezes=5, reprog="Sim"),
         ],
         "pendentes": [{"os_id": 2001, "motivo": "MPA noturna: defina o dia nas observações"},
                       {"os_id": 2002, "motivo": 'Usina "Cliente A - Usina Y - SP" não recebeu dia na semana'}],
         "qualidade": [{"tipo": "NOME", "item": "Usina X", "detalhe": "nome diferente no Fracttal", "acao": "corrigir"}]},
        {"week": "2026-W43", "label": "Semana 43 · 19–23 Out 2026", "geradaEm": "2026-10-16T21:00:00Z",
         "dates": {"seg": "19/10", "ter": "20/10", "qua": "21/10", "qui": "22/10", "sex": "23/10"},
         "resumo": {"SP NORTE 01": {"hh_util": 10, "hh_disp": 44, "pend": 0}},
         "rows": [_linha(1101, "Segunda-feira", "Não iniciada")], "pendentes": [], "qualidade": []},
    ],
}
GESTAO = {"totalAbertas": 10, "totalAtrasadas": 4, "tarefas": [
    {"os": 3001, "tipo": "Corretiva", "cliente": "Cliente A", "usina": "Cliente A - Usina X - SP", "tarefa": "[MPC] - Troca",
     "cluster": "SP NORTE 01", "responsavel": "Pessoa Um", "criacao": "2026-10-12", "dataFinal": "", "aberta": True,
     "atrasado": False},
    {"os": 3002, "tipo": "Religamento", "cliente": "Cliente B", "usina": "Cliente B - Usina Z - SC", "tarefa": "Religar",
     "cluster": "SC OESTE 01", "responsavel": "Pessoa Dois", "criacao": "2026-10-12", "dataFinal": "2026-10-12",
     "aberta": False, "atrasado": False},
    {"os": 3003, "tipo": "Preventiva", "cliente": "Cliente A", "usina": "Cliente A - Usina X - SP", "tarefa": "[MPA] - Limpeza",
     "cluster": "SP NORTE 01", "responsavel": "Pessoa Um", "criacao": "2026-10-12", "dataFinal": "", "aberta": True,
     "atrasado": True},
]}
GERENCIAL = {"usinas": [{"usina": "Usina X", "regiao": "SP", "cliente": "Cliente A", "cluster": "SP NORTE 01"}],
             "eventos": [{"u": 0, "os": 4001, "cat": "campo", "ini": "2026-10-12T08:00", "hDia": 3.5, "peso": 1}]}
ENGENHARIA = {"kpi": {"ativosSinal": 3, "mttr": 4.25, "mtbf": 1500, "abaixo85": 2},
              "ativos": [{"nome": "INV-01", "usina": "Usina X", "nFalha": 5, "nivel": "critico"}]}
OPERACOES = {"usinas": [{"usina": "Usina X", "cidade": "Ribeirão"}],
             "clusters": [{"cluster": "SP NORTE 01", "pessoas": 2}, {"cluster": "SC OESTE 01", "pessoas": 0}]}
FERIADOS = [{"tipo": "NACIONAL", "uf": "TODOS", "data": "2026-10-12", "nome": "Nossa Senhora Aparecida"}]


def _entradas():
    return dados.montar(json.loads(json.dumps(BD)), json.loads(json.dumps(GESTAO)), GERENCIAL, ENGENHARIA, OPERACOES,
                        FERIADOS)


@pytest.fixture
def pcm(app, tmp_path):
    """O repositório do PCM de mentira, em arquivos locais (o `fonte` lê arquivo local sem cópia em memória)."""
    arqs = {"banco_dados.json": BD, "gestao_pcm.json": GESTAO, "gerencial.json": GERENCIAL,
            "engenharia.json": ENGENHARIA, "operacoes.json": OPERACOES, "feriados.json": FERIADOS}
    for nome, conteudo in arqs.items():
        (tmp_path / nome).write_text(json.dumps(conteudo, ensure_ascii=False), encoding="utf-8")
    app.config.update(NEXUS_PCM_FONTE=str(tmp_path / "banco_dados.json"),
                      NEXUS_PCM_GESTAO_FONTE=str(tmp_path / "gestao_pcm.json"),
                      NEXUS_PCM_GERENCIAL_FONTE=str(tmp_path / "gerencial.json"),
                      NEXUS_PCM_ENGENHARIA_FONTE=str(tmp_path / "engenharia.json"),
                      NEXUS_PCM_OPERACOES_FONTE=str(tmp_path / "operacoes.json"),
                      NEXUS_PCM_FERIADOS_FONTE=str(tmp_path / "feriados.json"),
                      NEXUS_DADOS=str(tmp_path / "dados"))
    return tmp_path


def _agora(texto):
    return datetime.fromisoformat(texto).replace(tzinfo=BRT)


# ── as contas ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_diario_conta_o_dia_como_o_pcm():
    f = emitir(_entradas(), "diario", "2026-10-12", _agora("2026-10-13T06:10"))
    html = f["html"]
    # 3 programadas no plano (a 4ª foi fora do plano), 1 finalizada, 1 em andamento e 1 não iniciada
    assert f["resumo"] == {"prog": 3, "fin": 1, "naoProg": 2, "relig": 1}
    assert '<div class="v">33%</div><div class="n">Aderência do dia</div>' in html
    assert "1 de 3 programadas · +1 fora do plano" in html and "1 não iniciadas · 1 em andamento" in html
    assert "3,5 h diurnas" in html                                          # formato brasileiro (o PCM escrevia 3.5)
    assert "de 10 abertas · saldo do dia +2" in html and ">4</div><div class=\"n\">Backlog atrasado" in html
    assert "o que aconteceu ontem" in html and "Relatório gerado pelo Nexus · app.gridco.com.br" in html
    assert "INV-01" in html and "pcm.gridco.com.br" not in html


def test_tarde_separa_a_manha_e_o_pendente():
    f = emitir(_entradas(), "tarde", "2026-10-12", _agora("2026-10-12T13:05"))
    assert f["resumo"]["manha"] == 2 and f["resumo"]["pendentes"] == 1 and f["resumo"]["os"] == 1
    assert "corte às 13:05" in f["html"] and "#1002" in f["html"]


def test_fechamento_e_a_tendencia_da_semana():
    f = emitir(_entradas(), "semanal", "2026-W42", _agora("2026-10-16T17:20"))
    assert f["resumo"]["prog"] == 5 and f["resumo"]["fin"] == 2 and f["resumo"]["rolaram"] == 1
    assert f["resumo"]["reincidentes"] == 1                                 # a 1006 rolou 5 vezes e segue aberta
    assert '<div class="v">40%</div><div class="n">Aderência da semana</div>' in f["html"]
    assert "MTTR de 4,3 h" in f["html"]                                    # 4,25 arredonda o meio para cima


def test_alerta_faz_as_checagens_que_valem_para_a_semana():
    f = emitir(_entradas(), "alerta", "2026-W42", _agora("2026-10-09T20:10"))
    html = f["html"]
    assert "Duração implausível ou janela impossível — 1 OS, 1 tarefas" in html
    assert "Clusters acima da capacidade semanal — 1 de 2" in html
    assert "Feriados na semana — 1" in html and "Nossa Senhora Aparecida" in html
    assert "Cluster com programação mas sem pessoa no BD de Operações — 1" in html
    assert "OS com 5 rolagens ou mais programadas de novo — 1 OS" in html
    assert html.count('class="al-bloco"') == 17                            # as 17 checagens, das altas às baixas
    assert emitir(_entradas(), "alerta", "2026-W99", _agora("2026-10-09T20:10")) is None


def test_recorte_por_cliente_e_por_supervisor_como_o_painel():
    ent = _entradas()
    f = emitir(ent, "diario", "2026-10-12", _agora("2026-10-13T06:10"), cliente="Cliente B")
    assert f["resumo"]["prog"] == 0 and "Sem OS programadas para o dia" in f["html"]
    # com recorte, o backlog é o das tarefas do recorte (a do Cliente B está fechada), não o total da empresa
    assert "de 0 abertas" in f["html"] and "o que aconteceu ontem · Cliente B" in f["html"]
    f = emitir(ent, "semanal", "2026-W42", _agora("2026-10-16T17:20"), grupo="Pessoa Dois")
    assert f["resumo"]["prog"] == 1 and "· Pessoa Dois" in f["html"]
    # o fechamento com recorte segue mostrando o backlog da empresa toda (como no painel)
    assert ">4</div><div class=\"n\">Backlog atrasado" in f["html"]
    # as entradas originais não mudam
    assert len(ent["bd"]["semanas"][0]["rows"]) == 6


def test_as_escolhas_do_recorte_sao_em_cascata():
    o = dados.opcoes(BD)
    assert o["clientes"] == ["Cliente A", "Cliente B"] and "Pessoa Dois" in o["supervisores"]
    o = dados.opcoes(BD, cliente="Cliente B")
    assert o["clusters"] == ["SC OESTE 01"] and o["supervisores"] == ["Pessoa Dois"]
    o = dados.opcoes(BD, grupo="SC OESTE 01")
    assert o["clientes"] == ["Cliente B"]


def test_numeros_no_formato_brasileiro_e_o_do_pcm_na_prova():
    assert (regras.f1(1469.45), regras.f0(1469.5), regras.n(12345), regras.p0(82.5)) == ("1.469,5", "1.470", "12.345", "83")
    with regras.modo_original():
        assert (regras.f1(1469.45), regras.f0(82.5), regras.n(12345.9), regras.p0(82.5)) == ("1469.5", "82", "12.345", "82")


# ── a Central e a tela ─────────────────────────────────────────────────────────────────────────────────────────────
def test_o_administrador_ve_os_quatro_na_central(logado, pcm):
    html = logado.get("/t/relatorios/central").get_data(as_text=True)
    for t in TIPOS.values():
        assert f'href="/t/relatorios/{t.tela_id}"' in html and t.nome in html
    assert "A Plataforma de Performance ainda não está ligada" in html     # o aviso segue para os da plataforma


def test_o_setor_pcm_ve_os_quatro_sem_marcar_e_a_performance_nao(app, setores, pcm):   # noqa: F811
    novo = S.criar("PCM", app.config, BASE, setores)
    S.definir([{"id": 703, "email": DANI, "ficha": None, "por": ""}], novo["setor_id"], app.config, BASE, setores)
    dani = _como(app, DANI)
    html = dani.get("/t/relatorios/central").get_data(as_text=True)
    assert all(f'href="/t/relatorios/{t.tela_id}"' in html for t in TIPOS.values())
    assert "A Plataforma de Performance ainda não está ligada" not in html  # nenhum cartão da plataforma para ela
    assert dani.get("/t/relatorios/pcm-diario").status_code == 200
    ana = _como(app, ANA)
    assert 'href="/t/relatorios/pcm-diario"' not in ana.get("/t/relatorios/central").get_data(as_text=True)
    assert ana.get("/t/relatorios/pcm-diario").status_code == 403
    assert ana.get("/t/relatorios/pcm-diario/folha?dia=2026-10-12").status_code == 403    # a sub-rota segue a tela


def test_a_tela_tem_o_tipo_o_periodo_o_recorte_e_so_gera_quando_pede(logado, pcm):
    html = logado.get("/t/relatorios/pcm-semanal").get_data(as_text=True)
    assert "1 · Tipo" in html and "2 · Período e recorte" in html and "Emitidos automaticamente" in html
    assert all(t.nome in html for t in TIPOS.values()) and 'aria-current="page"' in html
    assert '<option value="2026-W42" selected>' in html                    # o fechamento traz a semana ativa
    assert "Cliente B" in html and "Pessoa Dois" in html and '<iframe id="rp-folha"' not in html
    html = logado.get("/t/relatorios/pcm-alerta").get_data(as_text=True)
    assert '<option value="2026-W43" selected>' in html                    # o alerta traz a semana publicada mais nova
    html = logado.get("/t/relatorios/pcm-diario?gerar=1&dia=2026-10-12&cliente=Cliente+A").get_data(as_text=True)
    assert 'src="/t/relatorios/pcm-diario/folha?dia=2026-10-12&amp;cliente=Cliente+A"' in html
    assert "Abrir em nova aba" in html


def test_a_folha_sai_com_o_dado_do_pcm_e_a_margem_de_tela(logado, pcm):
    r = logado.get("/t/relatorios/pcm-diario/folha?dia=2026-10-12")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
    assert "Relatório diário de manutenção" in html and '<div class="v">33%</div>' in html
    assert regras.CSS_TELA in html
    html = logado.get("/t/relatorios/pcm-alerta/folha?semana=2026-W42").get_data(as_text=True)
    assert "Alerta da programação" in html and "Feriados na semana — 1" in html


def test_sem_os_dados_do_pcm_a_tela_abre_e_a_folha_explica(logado):
    # nos testes, sem as fontes, o fonte.py não vai à rede
    html = logado.get("/t/relatorios/pcm-semanal").get_data(as_text=True)
    assert "Não consegui ler a programação do PCM agora" in html
    r = logado.get("/t/relatorios/pcm-diario/folha?dia=2026-10-12")
    assert r.status_code == 503 and "Não consegui ler os dados do PCM agora" in r.get_data(as_text=True)


# ── a emissão automática ───────────────────────────────────────────────────────────────────────────────────────────
def test_a_emissao_automatica_segue_os_horarios_do_pcm(app, logado, pcm):
    cfg = app.config
    # quarta 07:00: o diário de ontem e o alerta da semana nova (W43 > a ativa W42); a tarde só depois das 13:00
    assert agenda.volta(cfg, _agora("2026-10-14T07:00"))["emitidos"] == ["diario 2026-10-13", "alerta 2026-W43"]
    assert agenda.volta(cfg, _agora("2026-10-14T07:05"))["emitidos"] == []      # já emitidos: não repete
    assert agenda.volta(cfg, _agora("2026-10-14T13:05"))["emitidos"] == ["tarde 2026-10-14"]
    # sexta 17:10: o fechamento da semana ativa (e o diário e a tarde do dia)
    assert "semanal 2026-W42" in agenda.volta(cfg, _agora("2026-10-16T17:10"))["emitidos"]
    # a folha guardada abre pela tela, e a lista mostra
    html = logado.get("/t/relatorios/pcm-diario").get_data(as_text=True)
    assert 'href="/t/relatorios/pcm-diario/emitido/2026-10-13"' in html and "ter 13/10" in html
    r = logado.get("/t/relatorios/pcm-diario/emitido/2026-10-13")
    assert r.status_code == 200 and "Relatório diário de manutenção" in r.get_data(as_text=True)
    assert logado.get("/t/relatorios/pcm-diario/emitido/2026-10-01").status_code == 404
    assert logado.get("/t/relatorios/pcm-diario/emitido/..%2Fsegredo").status_code == 404


def test_o_fechamento_perdido_na_sexta_nao_sai_no_sabado_e_a_tarde_nao_sai_no_fim_de_semana(app, pcm):
    feitos = agenda.volta(app.config, _agora("2026-10-17T18:00"))["emitidos"]
    assert not any(e.startswith(("semanal", "tarde")) for e in feitos) and "diario 2026-10-16" in feitos


def test_o_alerta_sai_de_novo_quando_a_semana_e_republicada(app, pcm):
    cfg = app.config
    assert "alerta 2026-W43" in agenda.volta(cfg, _agora("2026-10-14T07:00"))["emitidos"]
    bd = json.loads((pcm / "banco_dados.json").read_text(encoding="utf-8"))
    bd["semanas"][1]["geradaEm"] = "2026-10-17T09:00:00Z"
    (pcm / "banco_dados.json").write_text(json.dumps(bd, ensure_ascii=False), encoding="utf-8")
    assert agenda.volta(cfg, _agora("2026-10-14T08:00"))["emitidos"] == ["alerta 2026-W43"]
    assert arquivo.existe(cfg, "alerta", "2026-W43")["geradaem"] == "2026-10-17T09:00:00Z"


def test_diario_e_tarde_guardados_por_30_dias(app, pcm):
    cfg = app.config
    velho = (datetime(2026, 10, 14) - timedelta(days=40)).date().isoformat()
    arquivo.gravar(cfg, "diario", velho, '<html><head><meta charset="utf-8"></head></html>', _agora("2026-09-05T06:00"))
    agenda.volta(cfg, _agora("2026-10-14T07:00"))
    assert arquivo.existe(cfg, "diario", velho) is None and arquivo.existe(cfg, "diario", "2026-10-13") is not None


def test_desligada_por_maquina_e_sem_dado_nao_emite(app):
    app.config["NEXUS_PCM_RELATORIOS_AUTO"] = "0"
    agenda.ligar(app)
    assert agenda._LACO["thread"] is None
    assert agenda.volta(app.config, _agora("2026-10-14T07:00"))["erro"].startswith("banco_dados.json")


def test_a_referencia_do_arquivo_nao_sai_da_pasta():
    assert arquivo.ref_valida("diario", "2026-10-13") and arquivo.ref_valida("alerta", "2026-W43")
    for ruim in ("../x", "2026-10-13/../../x", "2026-W43", ""):
        assert not arquivo.ref_valida("diario", ruim)
    assert not arquivo.ref_valida("semanal", "2026-10-13") and not arquivo.ref_valida("outro", "2026-10-13")


def test_a_senha_de_admin_ve_a_central(cliente, pcm):
    assert cliente.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    assert cliente.get("/t/relatorios/pcm-tarde").status_code == 200
