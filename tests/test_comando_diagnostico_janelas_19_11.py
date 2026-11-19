"""Cada dado do dossiê declara a sua janela de tempo (Levi, 19/11/2026).

O achado dele no Insights: "o resumo do mês diz '0 desligamentos com a geração parada' enquanto o título fala do SKID 2
parado hoje. Cada dado precisa declarar a sua janela de tempo (hoje, até ontem, mês parcial) para que o texto não se
contradiga". As duas frases estavam certas, cada uma na janela dela: a tabela por mês do COS só conta a parada JÁ
NORMALIZADA (a usina voltou), e o SKID parado hoje ainda está aberto, fora dela. O dossiê não dizia isso, e o pedido
mandava usar o número da tabela.

O que estes testes seguram: o dossiê escreve a janela do COS agora, da tabela por mês e da performance, e avisa quando há
parada aberta fora da contagem; o pedido do diagnóstico manda cada número levar a janela; e a conferência pega o "zero
desligamentos" dito com parada aberta hoje (refaz uma vez pensando e, se insistir, a tela avisa)."""
import json

from nexus.comando import diagnostico as DG
from nexus.comando import dossie as DS

ABERTA = {"grupo": "critico", "motivo": "SKID 2 desligado", "tom": "critico", "os_rotulo": "OS 19900", "ha": "3 h",
          "etapa": "Técnico acionado"}
SEM_COM = {"grupo": "sem_com", "motivo": "Falha de comunicação", "tom": "sem_com", "os_rotulo": "OS 19901", "ha": "1 h", "etapa": ""}
COS = {"total": 4, "por_mes": [{"rot": "novembro", "parou": 0, "n": 1}, {"rot": "outubro", "parou": 3, "n": 3}], "ultimas": []}


def _cos(ocs, estado="critico"):
    return "\n".join(DS._cos({"estado": estado, "os_cos": ocs}, {"cos": COS}))


# ── o dossiê ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_cos_agora_diz_que_e_de_hoje_e_que_a_parada_aberta_nao_esta_na_tabela_do_mes():
    t = _cos([ABERTA])
    assert "- Agora (hoje, a fotografia do COS neste momento): 1 ocorrência aberta" in t
    assert "SKID 2 desligado (crítico)" in t
    aviso = next(l for l in t.splitlines() if "NÃO ENTRA" in l)
    assert aviso.startswith("- ") and "1 ocorrência aberta" in aviso and "já normalizadas" in aviso


def test_a_tabela_por_mes_declara_que_so_conta_a_parada_ja_normalizada():
    t = _cos([])
    assert "- Agora (hoje, a fotografia do COS neste momento): nenhuma ocorrência aberta." in t
    titulo = next(l for l in t.splitlines() if l.startswith("Por mês"))
    assert "JÁ NORMALIZADAS" in titulo and "parcial" in titulo
    assert "NÃO ENTRA" not in t                                   # sem nada aberto, não há o que avisar


def test_a_falha_de_comunicacao_aberta_nao_e_parada_fora_da_contagem():
    t = _cos([SEM_COM], estado="sem_com")
    assert "1 ocorrência aberta" in t and "NÃO ENTRA" not in t   # comunicação não é desligamento: não muda a contagem
    dois = _cos([ABERTA, SEM_COM])
    assert "2 ocorrências abertas" in dois
    assert "1 ocorrência aberta agora com equipamento parado" in next(l for l in dois.splitlines() if "NÃO ENTRA" in l)


def test_a_leitura_que_faltou_segue_dizendo_sem_leitura():
    t = "\n".join(DS._cos({"estado": "sem_leitura", "os_cos": []}, {"cos": COS}))
    assert "- Agora: sem leitura do COS (a fonte não respondeu ou a usina não está na fotografia). Não quer dizer normal." in t


def test_a_performance_diz_que_o_mes_parcial_vai_ate_ontem():
    linhas = DS._performance({}, {}, {"painel": {"perf": {"periodo": "10 de 31 dias", "medidores": []}}})
    assert "- O mês corrente é parcial: os números cobrem 10 de 31 dias." in linhas
    assert any("até ontem" in l and "hoje não entra" in l for l in linhas)


def test_o_como_ler_explica_as_tres_janelas():
    regra = next(l for l in DS.COMO_LER if "JANELA" in l)
    assert "AGORA" in regra and "ATÉ ONTEM" in regra and "JÁ NORMALIZADAS" in regra


def test_o_formato_do_dossie_e_o_do_diagnostico_mudaram_de_versao():
    # o guardado com o pedido antigo é refeito na próxima abertura (`diagnostico.guardado` olha a VERSAO)
    assert DS.VERSAO >= 7 and DG.VERSAO == 6      # o dossiê foi a 8 no mesmo dia, com a programação do PCM e o contrato


# ── o pedido e a conferência ─────────────────────────────────────────────────────────────────────────────────────────
def test_o_pedido_manda_cada_numero_levar_a_janela():
    regra = next(l for l in DG.PEDIDO.splitlines() if l.startswith("- Janela de tempo"))
    assert "até ontem" in regra and "normalizados" in regra and "hoje" in regra
    assert "zero" in regra and "parada" in regra                 # o caso do Levi: zero no mês com parada aberta hoje


DOSSIE = """# Dossiê da usina Exemplo

## 4. COS

- Agora (hoje, a fotografia do COS neste momento): 1 ocorrência aberta
  - SKID 2 desligado (crítico); OS 19900; aberta 3 h; Técnico acionado
- 1 ocorrência aberta agora com equipamento parado ou em falha NÃO ENTRA na tabela por mês abaixo.
- Normalizações registradas: 4.

Por mês (janela: só as paradas JÁ NORMALIZADAS; o mês corrente é parcial):
| Mês | Desligamentos (a geração parou) | Sem a geração parar (não é desligamento) | Normalizações no total |
| --- | --- | --- | --- |
| novembro | 0 | 1 | 1 |
| outubro | 3 | 0 | 3 |
"""
DIA = "2026-11-19"


def _diag(situacao):
    return {"situacao": situacao, "tem_que_fazer": [], "pode_fazer": [], "pendente": []}


def test_a_conferencia_pega_o_zero_desligamentos_dito_com_parada_aberta_hoje():
    falhas = DG.conferir(_diag("SKID 2 parado hoje. O mês segue com 0 desligamentos com a geração parada."), DOSSIE, DIA)
    assert len(falhas) == 1 and "aberta" in falhas[0] and "desligamento" in falhas[0]
    for dito in ("Nenhum desligamento em novembro.", "Mês sem desligamentos.", "Zero desligamentos no mês."):
        assert DG.conferir(_diag("SKID 2 parado. " + dito), DOSSIE, DIA), dito


def test_o_zero_com_a_janela_dita_passa():
    certo = "SKID 2 parado hoje (aberto há 3 h); no mês, 0 desligamentos já normalizados."
    assert DG.conferir(_diag(certo), DOSSIE, DIA) == []


def test_sem_parada_aberta_o_zero_do_mes_e_so_o_da_tabela():
    sem = DOSSIE.replace("1 ocorrência aberta\n  - SKID 2 desligado (crítico); OS 19900; aberta 3 h; Técnico acionado\n"
                         "- 1 ocorrência aberta agora com equipamento parado ou em falha NÃO ENTRA na tabela por mês abaixo.",
                         "nenhuma ocorrência aberta.")
    assert "nenhuma ocorrência aberta." in sem
    assert DG.conferir(_diag("Usina em dia: 0 desligamentos em novembro."), sem, DIA) == []
    so_com = DOSSIE.replace("SKID 2 desligado (crítico)", "Falha de comunicação (sem comunicação)").replace(
        "- 1 ocorrência aberta agora com equipamento parado ou em falha NÃO ENTRA na tabela por mês abaixo.\n", "")
    assert DG.conferir(_diag("Sem comunicação agora; 0 desligamentos em novembro."), so_com, DIA) == []


def test_a_contradicao_refaz_uma_vez_pensando_e_se_insistir_a_tela_avisa(tmp_path, monkeypatch):
    chamadas = []

    def falsa(cfg, ids, dossie, pergunta, historico=None, setores=None, meu_setor="", instrucoes=None, pensar=True):
        chamadas.append(pensar)
        texto = "SKID 2 parado hoje. O mês segue com 0 desligamentos."
        return [{"ok": True, "id": "claude-haiku-5-5", "rotulo": "Claude Haiku 5.5", "ms": 10,
                 "texto": "<diagnostico>" + json.dumps(_diag(texto), ensure_ascii=False) + "</diagnostico>"}]
    monkeypatch.setattr(DG.IA, "perguntar", falsa)
    monkeypatch.setattr(DG.IA, "registrar", lambda *a, **k: None)
    d = DG.gerar({"NEXUS_DADOS": str(tmp_path), "TESTING": True}, 1, DOSSIE, 100, DIA)
    assert chamadas == [False, True]                              # a busca, e a 2ª vez pensando
    assert d["refeito"] is True and len(d["conferir"]) == 1 and d["versao"] == 6
