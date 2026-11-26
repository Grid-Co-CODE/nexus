"""O que mudou nos atrasados (25/11/2026, `nexus/hseq/extintores_mudou.py`): os atrasados numa data de início e hoje, os
antigos, os novos e os resolvidos, e as barras por dia, pela foto diária (`extintores_historico`) e, antes dela, pela
estimativa da validade de hoje. Códigos e usinas fictícios."""
import json
from datetime import date

import pytest
from test_campo_visao import _aba, banco  # noqa: F401  (banco é fixture)
from test_hseq_extintores import com_cadastro, com_livro  # noqa: F401

from nexus.hseq import extintores_historico as H
from nexus.hseq import extintores_mudou as M

HOJE = date(2026, 11, 25)


def _x(cod, sit, fim=None, usina_id=1, cliente="Cliente Alfa"):
    return {"codigo": cod, "usina": f"Usina {usina_id}", "usina_id": usina_id, "cliente": cliente, "situacao": sit,
            "fim2": fim, "fim3": None, "vence": fim, "vence_qual": "recarga"}


def _foto(dia, tipo, cod, sit, usina_id=1):
    return {"data_id": int(dia.strftime("%Y%m%d")), "tipo": tipo, "usina_id": usina_id, "codigo": cod, "situacao": sit,
            "venceu": "recarga" if sit == "atrasado" else "", "sem_atualizacao": "nao"}


def _dia(dia):
    return {"data_id": int(dia.strftime("%Y%m%d"))}


# A foto: em 22/11 (a completa) A e B atrasados; em 23/11 o B foi recarregado (em dia) e o C venceu; 24/11 ficou sem
# foto (o banco fora); hoje, A, C e D atrasados (o D venceu ontem)
CRU = {H.ABA: [_foto(date(2026, 11, 22), "completa", "A", "atrasado"), _foto(date(2026, 11, 22), "completa", "B", "atrasado"),
               _foto(date(2026, 11, 23), "mudanca", "B", "em_dia"), _foto(date(2026, 11, 23), "mudanca", "C", "atrasado")],
       H.ABA_DIA: [_dia(date(2026, 11, 22)), _dia(date(2026, 11, 23))]}
ATUAIS = [_x("A", "atrasado", date(2026, 10, 31)), _x("B", "em_dia", date(2027, 11, 30)),
          _x("C", "atrasado", date(2026, 11, 22)), _x("D", "atrasado", date(2026, 11, 24)),
          _x("E", "atrasado", date(2026, 9, 30), usina_id=2, cliente="Cliente Beta")]


def _todos(x):
    return True


def test_antigos_novos_e_resolvidos_pela_foto():
    r = M.comparar(CRU, ATUAIS, HOJE, date(2026, 11, 22), _todos, {})
    assert (r["n_inicio"], r["n_hoje"], r["estimado"]) == (2, 4, False)
    assert [x["codigo"] for x in r["antigos"]] == ["A"]
    assert [x["codigo"] for x in r["novos"]] == ["E", "C", "D"]        # pela validade que venceu, a mais antiga primeiro
    assert r["resolvidos"] == 1                                         # o B
    b = {x["dia"]: x for x in r["barras"]}
    assert (b[date(2026, 11, 22)]["antigos"], b[date(2026, 11, 22)]["novos"]) == (2, 0)
    assert (b[date(2026, 11, 23)]["antigos"], b[date(2026, 11, 23)]["novos"]) == (1, 1)
    assert b[date(2026, 11, 24)]["como"] == "lacuna" and b[date(2026, 11, 24)]["antigos"] is None   # sem inventar
    assert (b[HOJE]["como"], b[HOJE]["antigos"], b[HOJE]["novos"]) == ("real", 1, 3)


def test_o_inicio_sem_foto_parte_da_ultima_foto_antes():
    r = M.comparar(CRU, ATUAIS, HOJE, date(2026, 11, 24), _todos, {})
    assert r["de_usado"] == date(2026, 11, 23) and r["n_inicio"] == 2 and r["resolvidos"] == 0


def test_antes_da_1a_foto_e_estimado_pela_validade_e_sem_resolvidos():
    r = M.comparar(CRU, ATUAIS, HOJE, date(2026, 11, 1), _todos, {})
    # em 01/11 só o A (venceu em 31/10) e o E (30/09) estavam vencidos pela validade de hoje
    assert (r["estimado"], r["n_inicio"], r["resolvidos"]) == (True, 2, None)
    assert {x["codigo"] for x in r["antigos"]} == {"A", "E"}
    b = {x["dia"]: x for x in r["barras"]}
    assert b[date(2026, 11, 10)]["como"] == "estimado" and b[date(2026, 11, 22)]["como"] == "foto"


def test_os_filtros_da_tela_valem_tambem_nos_dias_de_foto():
    """O código da foto liga ao extintor de hoje; o que saiu da tela, à usina dele (`por_usina`)."""
    cru = {H.ABA: CRU[H.ABA] + [_foto(date(2026, 11, 22), "completa", "Z", "atrasado", usina_id=2)], H.ABA_DIA: CRU[H.ABA_DIA]}
    so_beta = (lambda x: x.get("cliente") == "Cliente Beta")
    r = M.comparar(cru, ATUAIS, HOJE, date(2026, 11, 22), so_beta, {2: ATUAIS[4]})
    assert r["n_inicio"] == 1 and r["resolvidos"] == 1                  # o Z (excluído, da usina 2) estava atrasado
    assert [x["codigo"] for x in r["novos"]] == ["E"] and r["n_hoje"] == 1


def test_a_data_de_inicio_vai_ate_90_dias_e_nunca_depois_de_hoje():
    assert M.comparar(CRU, ATUAIS, HOJE, date(2025, 1, 1), _todos, {})["de"] == date(2026, 8, 27)
    assert M.comparar(CRU, ATUAIS, HOJE, date(2027, 1, 1), _todos, {})["de"] == HOJE


def test_o_grafico_em_numeros_redondos():
    r = M.comparar(CRU, ATUAIS, HOJE, date(2026, 11, 22), _todos, {})
    g = M.grafico(r["barras"])
    assert [m["v"] for m in g["marcas"]] == [0, 1, 2, 3, 4] and g["com_total"]
    lac = next(b for b in g["barras"] if b["como"] == "lacuna")
    assert lac["total"] is None and lac["ha"] == 0
    hoje = g["barras"][-1]
    assert hoje["total"] == 4 and hoje["yn"] < hoje["ya"] <= g["base"]
    muitos = [{"dia": date(2026, 11, 1), "como": "foto", "antigos": 130, "novos": 20}] * 40
    g2 = M.grafico(muitos)
    assert [m["v"] for m in g2["marcas"]] == [0, 50, 100, 150, 200] and not g2["com_total"]
    assert sum(b["rotulo"] for b in g2["barras"]) <= 13


# ── a tela ───────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def livro(app, tmp_path):
    arq = tmp_path / "historico.json"
    app.config["NEXUS_HSEQ_EXTINTORES_HISTORICO_ARQUIVO"] = str(arq)
    return arq


def test_a_secao_so_le_a_foto_quando_abre(com_cadastro, livro, logado, monkeypatch):
    lidas = []
    real = H.ler
    monkeypatch.setattr(H, "ler", lambda cfg: lidas.append(1) or real(cfg))
    html = logado.get("/t/hseq/extintores?cliente=Thopen").get_data(as_text=True)
    assert lidas == []                                                  # a página da tabela não lê a foto
    assert '<details class="hs-mudou" id="mudou" data-busca="/t/hseq/extintores/mudou?cliente=Thopen">' in html
    assert "O que mudou nos atrasados" in html and "Estimado" in html   # e o "!" explica
    # o pedaço, sem foto nenhuma ainda: tudo estimado, sem resolvidos
    pedaco = logado.get("/t/hseq/extintores/mudou?cliente=Thopen").get_data(as_text=True)
    assert lidas == [1] and "<html" not in pedaco
    assert "estimado" in pedaco and "Resolvidos no período" in pedaco and ">—</dd>" in pedaco
    assert 'name="de" value="02/10/2026"' in pedaco                    # 7 dias antes do dia da tela (09/10/2026)


def test_com_a_foto_os_numeros_da_tela(com_cadastro, livro, logado):
    """No dia da tela (09/10/2026) há 2 atrasados (ALT01 e COR01). A foto de 08/10 tinha só o COR01 e um outro que foi
    resolvido."""
    livro.write_text(json.dumps({H.ABA: [_foto(date(2026, 10, 8), "completa", "COR100-INFC1-PPCI-EXT01", "atrasado", 3),
                                         _foto(date(2026, 10, 8), "completa", "ALT100-INFC1-PPCI-EXT03", "atrasado", 1)],
                                 H.ABA_DIA: [_dia(date(2026, 10, 8))]}), encoding="utf-8")
    p = logado.get("/t/hseq/extintores/mudou?de=08/10/2026").get_data(as_text=True)
    assert "estimado" not in p.split("Atrasados por dia")[0]
    import re
    assert re.findall(r'<dd class="[^"]+">([^<]+)</dd>', p) == ["1", "1", "1"]   # antigo COR01, novo ALT01, 1 resolvido
    assert "Ver o novo" in p and "Ver o antigo" in p and "ALT100-INFC1-PPCI-EXT01" in p
    assert 'class="hs-graf"' in p and 'class="hs-graf-antigo"' in p
    # a data errada volta ao padrão; sem login, o pedaço não sai
    assert 'value="02/10/2026"' in logado.get("/t/hseq/extintores/mudou?de=ontem").get_data(as_text=True)
    assert logado.application.test_client().get("/t/hseq/extintores/mudou").status_code == 302
