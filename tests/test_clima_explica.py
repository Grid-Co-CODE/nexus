"""O "o que quer dizer" do Clima e risco (09/10/2026, Levi: "estou achando um pouco limitado e pouco entendível para um leigo,
deixe mais didático"): os textos do `explica.py`, os avisos iguais juntos, o motivo resumido (o da tabela da Atenção e o da tabela
do mapa), os dias com o nome que se fala e o "O que fazer" dos números do topo. Nada vai à rede."""
import re
from datetime import datetime, timedelta, timezone

from nexus.performance.clima import alertas as A
from nexus.performance.clima import explica as EX
from nexus.performance.clima import visao as V
from nexus.performance.clima.fontes import Aviso
from nexus.performance.clima.geotiff import Amostra

BRT = timezone(timedelta(hours=-3))
REF = datetime(2026, 10, 9, 9, 0, tzinfo=BRT)          # uma sexta-feira
FIM_DO_DIA = REF.replace(hour=23, minute=59)
SEVERIDADE = {1: "Perigo Potencial", 2: "Perigo", 3: "Grande Perigo"}


def _aviso(nivel, evento, inicio=None, fim=None):
    return Aviso(f"{evento}-{nivel}-{inicio}", "hoje", evento, SEVERIDADE[nivel], nivel, inicio or REF - timedelta(hours=1),
                 fim or FIM_DO_DIA, {"type": "Polygon", "coordinates": []}, (0.0, 0.0, 0.0, 0.0))


def _dias(*valores):
    amigaveis = V.dias_amigaveis(None, REF)
    return [V.celula_de_risco(i, Amostra(v, "ponto"), V.rotulos_dos_dias(None, REF), amigaveis) for i, v in enumerate(valores)]


# ── o explica.py ─────────────────────────────────────────────────────────────────────────────────────────────────────

def test_todo_evento_que_manda_agir_tem_texto_proprio():
    for evento in A.EVENTOS_QUE_ESTRAGAM_USINA:
        assert EX.conhecido(evento), evento
        assert all(EX.evento(evento)[k] for k in ("o_que_e", "na_usina", "conferir")), evento


def test_evento_que_o_explica_nao_conhece_cai_no_generico_e_nao_some():
    assert not EX.conhecido("Ciclone Extratropical") and EX.evento("Ciclone Extratropical") == EX.GENERICO
    g = V.glossario([{"grupos": V.agrupar_avisos([_aviso(1, "Ciclone Extratropical")], REF)}])
    assert [(e["nome"], e["conhecido"]) for e in g["eventos_agora"]] == [("Ciclone extratropical", False)]
    assert len(g["eventos_outros"]) == len(EX.EVENTOS)                   # os conhecidos todos, na lista dos "outros"


def test_o_glossario_poe_primeiro_os_eventos_de_agora_sem_repetir():
    grupos = V.agrupar_avisos([_aviso(2, "Tempestade"), _aviso(1, "Baixa Umidade"), _aviso(1, "Tempestade")], REF)
    g = V.glossario([{"grupos": grupos}, {"grupos": grupos}])
    assert [e["nome"] for e in g["eventos_agora"]] == ["Tempestade", "Baixa umidade"]
    assert "Tempestade" not in [e["nome"] for e in g["eventos_outros"]] and len(g["eventos_outros"]) == len(EX.EVENTOS) - 2
    assert [n["nome"] for n in g["niveis"]] == ["Perigo Potencial", "Perigo", "Grande Perigo"]


def test_os_textos_nao_tem_emoji_nem_cor_como_nome_de_nivel():
    textos = [t for d in (*EX.EVENTOS.values(), EX.GENERICO, EX.FOCO, EX.RISCO_FOGO) for t in d.values()]
    textos += [n["quer_dizer"] for n in EX.NIVEIS_INMET] + [x for c in EX.COMO_LER for x in (c["quer_dizer"], c["fazer"])]
    for t in textos:
        assert not re.search("[\U0001F300-\U0001FAFF☀-➿]", t), t
        assert not re.search(r"\b(amarelo|laranja|vermelho)\b", t), t
    assert [c["id"] for c in EX.COMO_LER] == [A.AGIR, A.ATENCAO, A.SEM_ALERTA]


def test_nome_amigavel_tira_a_maiuscula_do_meio():
    assert EX.nome_amigavel("Chuvas Intensas") == "Chuvas intensas"
    assert EX.nome_amigavel("  Baixa   Umidade ") == "Baixa umidade" and EX.nome_amigavel("") == ""


# ── os avisos iguais juntos ──────────────────────────────────────────────────────────────────────────────────────────

def test_tres_avisos_do_mesmo_evento_e_nivel_viram_um_grupo_com_a_janela_de_todos():
    # o caso de 09/10: "Baixa Umidade" hoje, amanhã e depois, três pílulas iguais na tabela
    dia = timedelta(days=1)
    avisos = [_aviso(1, "Baixa Umidade"),
              _aviso(1, "Baixa Umidade", inicio=(REF + dia).replace(hour=0, minute=0), fim=FIM_DO_DIA + dia),
              _aviso(1, "Baixa Umidade", inicio=(REF + 2 * dia).replace(hour=0, minute=0), fim=FIM_DO_DIA + 2 * dia)]
    (g,) = V.agrupar_avisos(avisos, REF)
    assert (g["nome"], g["severidade"], g["n"], g["em_vigor"]) == ("Baixa umidade", "Perigo Potencial", 3, True)
    assert g["quando"] == "agora, até 11/10 23:59 · 3 avisos"


def test_aviso_sem_fim_deixa_a_janela_aberta():
    avisos = [_aviso(1, "Baixa Umidade"), Aviso("x", "hoje", "Baixa Umidade", "Perigo Potencial", 1, REF - timedelta(hours=2),
                                                  None, {}, (0, 0, 0, 0))]
    (g,) = V.agrupar_avisos(avisos, REF)
    assert g["fim"] is None and g["quando"] == "agora · 2 avisos"


def test_o_que_manda_agir_vem_antes_e_o_mesmo_evento_em_dois_niveis_vira_um_evento():
    grupos = V.agrupar_avisos([_aviso(1, "Baixa Umidade"), _aviso(2, "Baixa Umidade"), _aviso(2, "Vendaval")], REF)
    assert [(g["nome"], g["severidade"], g["agir"]) for g in grupos] == [
        ("Vendaval", "Perigo", True), ("Baixa umidade", "Perigo", False), ("Baixa umidade", "Perigo Potencial", False)]
    eventos = V.por_evento(grupos, REF)
    assert [(e["nome"], e["severidade"], e["nivel"], e["n"], e["agir"]) for e in eventos] == [
        ("Vendaval", "Perigo", 2, 1, True), ("Baixa umidade", "Perigo", 2, 2, False)]
    assert eventos[1]["detalhe"] == "Perigo: agora, até 23:59 · Perigo Potencial: agora, até 23:59"
    assert eventos[1]["quando"] == "agora, até 23:59 · 2 avisos"


def test_aviso_que_ainda_vai_comecar_diz_a_partir_de():
    inicio = (REF + timedelta(days=1)).replace(hour=8, minute=0)
    (g,) = V.agrupar_avisos([_aviso(2, "Vendaval", inicio=inicio, fim=inicio + timedelta(hours=12))], REF)
    assert (g["em_vigor"], g["comeca"], g["quando"]) == (False, "10/10 08:00", "a partir de 10/10 08:00, até 10/10 20:00")


# ── o motivo resumido ────────────────────────────────────────────────────────────────────────────────────────────────

def test_motivo_curto_junta_o_mesmo_evento_e_para_nos_dois_mais_importantes():
    avisos = [_aviso(2, "Baixa Umidade"), _aviso(1, "Baixa Umidade"), _aviso(1, "Tempestade")]
    assert V.motivo_curto(avisos, None, _dias(1.0, 1.0, 1.0, 1.0), REF) == (
        "Baixa umidade (Perigo) · Tempestade (Perigo Potencial) · e mais 1")


def test_motivo_curto_poe_o_fogo_perto_primeiro_e_o_risco_com_os_dias_falados():
    assert V.motivo_curto([], {"km": 2.34, "n": 1}, _dias(1.0, 1.0, 1.0, 1.0), REF) == (
        "Fogo a 2,3 km · Risco de fogo crítico de hoje a seg 12/10")
    inicio = (REF + timedelta(days=1)).replace(hour=8, minute=0)
    assert V.motivo_curto([_aviso(2, "Vendaval", inicio=inicio, fim=inicio + timedelta(hours=1))], None, _dias(0.1, 0.1, 0.1, 0.1),
                          REF) == "Vendaval (Perigo, a partir de 10/10 08:00)"
    assert V.motivo_curto([], None, _dias(0.1, 0.1, 0.1, 0.1), REF) == ""          # risco baixo não é motivo


# ── os dias com o nome que se fala ───────────────────────────────────────────────────────────────────────────────────

def test_os_dias_do_risco_com_o_nome_que_se_fala():
    assert V.dias_amigaveis(None, REF) == ["hoje", "amanhã", "dom 11/10", "seg 12/10"]
    arquivo_de_ontem = (REF - timedelta(days=1)).replace(hour=6, minute=32)
    assert V.dias_amigaveis(arquivo_de_ontem, REF) == ["ontem", "hoje", "amanhã", "dom 11/10"]


def test_a_frase_do_risco_e_a_palavra_de_cada_dia():
    cels = _dias(0.1, 0.8, 0.8, 0.1)
    assert V.frase_do_risco(cels) == "Risco de fogo alto amanhã e dom 11/10 (0,80)"          # "amanhã", nunca "em amanhã"
    assert [c["palavra"] for c in cels] == ["Mínimo", "Alto", "Alto", "Mínimo"]
    assert [c["palavra"] for c in _dias(0.2, 0.5, 0.99, None)] == ["Baixo", "Médio", "Crítico", "—"]


# ── o "O que fazer" dos números do topo ──────────────────────────────────────────────────────────────────────────────

def test_o_que_fazer_so_aparece_quando_o_nivel_tem_usina():
    assert V._celula_da_faixa("agir", "Agir agora", 2, "x", [], traco=False, ambar=False)["fazer"].startswith("Avisar")
    assert V._celula_da_faixa("agir", "Agir agora", 0, "x", [], traco=False, ambar=False)["fazer"] == ""
    assert V._celula_da_faixa("sem", "Sem alerta", 3, "x", [], traco=True, ambar=False)["fazer"] == ""       # "—": não dá para dizer
    assert V._celula_da_faixa("cobertura", "Cobertura", 9, "x", [], traco=False, ambar=False)["fazer"] == ""
