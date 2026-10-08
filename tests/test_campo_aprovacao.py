"""Aprovação de OS nativa do Nexus (Levi, 04/10/2026: "pode passar para o Nexus").

A fila crua vem do Fracttal (OS em revisão, status 2) e a nota do registro das tabelas do App; aqui os dois são falsos,
no mesmo formato. As regras são a cópia das do App (nexus/campo/regras_app.py).
"""
import re
from datetime import datetime, timedelta

import pytest
from test_campo_regras_app import TabelaFalsa

from nexus.campo import aprovacao, fracttal, leitura, tabelas


def _quando(atras_dias):
    return (datetime.utcnow() - timedelta(days=atras_dias)).strftime("%Y-%m-%dT%H:%M:%S")


def _os(folio, atras, tecnico="Técnico 1"):
    """Uma tarefa em revisão como o Fracttal devolve em work_orders?id_status_work_order=2."""
    return {"id_work_orders_tasks": int(folio) * 10, "id_work_order": int(folio), "wo_folio": str(folio),
            "final_date": _quando(atras), "personnel_description": tecnico, "groups_1_description": "SP 01",
            "groups_2_description": "SP Interior", "items_log_description": "Usina A",
            "tasks_description": f"Tarefa da OS {folio}", "rating": 0}


def _nota(folio, qualidade):
    """O registro do App no fechamento (tabela qualidadelog)."""
    return {"PartitionKey": "q", "RowKey": f"q{folio}", "os": str(folio), "server_ts": _quando(1),
            "qualidade": qualidade, "foi_devolvida": False, "foto_divergente": False,
            "fx_dur_prev_min": 60, "fx_dur_real_min": 70}


class FracttalFalso:
    """Responde como a API REST do Fracttal: o total na chamada de limit=1, as páginas de 100 pelo start=."""

    def __init__(self, linhas, recusar=False):
        self.linhas, self.recusar, self.pedidos = linhas, recusar, []

    def __call__(self, path):
        self.pedidos.append(path)
        if self.recusar:
            raise fracttal.Recusado("o Fracttal recusou por excesso de pedidos (HTTP 429)")
        assert path.startswith("work_orders?id_status_work_order=2"), path
        if "start=" not in path:
            return {"total": len(self.linhas), "data": self.linhas[:1]}
        ini = int(re.search(r"start=(\d+)", path).group(1))
        return {"data": self.linhas[ini:ini + 100]}


@pytest.fixture
def campo():
    dados = {"qualidadelog": [_nota(15102, 96), _nota(15088, 71)]}
    fx = FracttalFalso([_os(15002, 33, "Técnico 7"), _os(15088, 8, "Técnico 4"), _os(15102, 4, "Técnico 5")])
    tabelas.usar_fornecedor(lambda nome: TabelaFalsa(dados.setdefault(nome, [])))
    fracttal.usar_fornecedor(fx)
    leitura.limpar_cache()
    yield fx
    tabelas.usar_fornecedor(None)
    fracttal.usar_fornecedor(None)
    leitura.limpar_cache()


def test_fila_tem_os_grupos_e_numeros_do_painel_do_app(campo):
    d = aprovacao.fila({"dias": "60"}).dados
    assert d["baldes"] == {"completa": 1, "olho": 1, "fora_do_app": 1}
    r = d["resumo"]
    assert (r["tarefas"], r["aged7d"], r["aged30d"], r["pelo_app"]) == (3, 2, 1, 2)
    # a mais antiga primeiro, como no App
    assert [x["os"] for x in d["linhas"]] == ["15002", "15088", "15102"]
    assert {x["os"]: x["balde"] for x in d["linhas"]} == {"15002": "fora_do_app", "15088": "olho", "15102": "completa"}


def test_filtro_por_grupo_vale_para_a_lista_e_os_numeros(campo):
    d = aprovacao.fila({"dias": "60", "balde": "olho"}).dados
    assert [x["os"] for x in d["linhas"]] == ["15088"]
    assert d["resumo"]["tarefas"] == 1               # no App o resumo também é do grupo escolhido
    assert d["baldes"]["completa"] == 1              # e os grupos continuam contando todos


def test_parametro_estranho_nao_chega_nas_regras(campo):
    d = aprovacao.fila({"dias": "60", "qualquer": "coisa"}).dados
    assert d["resumo"]["tarefas"] == 3


def test_nexus_so_le_o_fracttal_e_uma_vez_a_cada_10_min(campo):
    aprovacao.fila({"dias": "60"})
    aprovacao.fila({"dias": "60", "balde": "olho"})     # outro filtro, mesma fila crua (cache do próprio App)
    paginas = [p for p in campo.pedidos if "start=" in p]
    assert len(paginas) == 1 and len(campo.pedidos) == 2
    with pytest.raises(fracttal.Recusado):
        fracttal.ler("work_orders/15002", "PUT", {"id_status_work_order": 3})


def test_fracttal_recusou_vira_aviso(campo):
    campo.recusar = True
    leitura.limpar_cache()
    lida = aprovacao.fila({"dias": "60"})
    assert not lida.dados and "recusou" in aprovacao.estado()["erro"]


def test_tela_nao_espera_o_fracttal(logado, campo, monkeypatch):
    """Levi, 05/10: "fica carregando infinito". A visita não lê o Fracttal: pede a releitura em segundo plano e
    responde na hora, dizendo que está lendo."""
    pendentes = []
    monkeypatch.setattr(aprovacao, "em_segundo_plano", pendentes.append)
    html = logado.get("/t/campo/aprovacao").get_data(as_text=True)
    assert "Lendo a fila de verificação do Fracttal" in html and campo.pedidos == []
    logado.get("/t/campo/aprovacao")
    assert len(pendentes) == 1                         # uma releitura por vez, por mais visitas que cheguem
    pendentes[0]()                                     # a releitura termina
    lidos = len(campo.pedidos)
    html = logado.get("/t/campo/aprovacao?ver=Sem+cadastro").get_data(as_text=True)
    assert ">15102<" in html and "fila lida em" in html and len(pendentes) == 1
    # e a cópia do App serve a fila relida, sem ir ao Fracttal na hora da tela: desde o v235 (06/10) o _fila_bruta
    # do App mede a idade da fila por _FILA_CACHE["t"]; sem ele, cada visita relia as 55 páginas
    assert len(campo.pedidos) == lidos


def test_recusa_mantem_a_ultima_fila_boa_e_espera_para_tentar_de_novo(logado, campo):
    import time
    from nexus.campo import regras_app
    assert ">15102<" in logado.get("/t/campo/aprovacao?ver=Sem+cadastro").get_data(as_text=True)
    regras_app._FILA_CACHE["t"] = time.time() - 20 * 60     # a fila envelheceu (o relógio da cópia do App)
    campo.recusar = True
    html = logado.get("/t/campo/aprovacao?ver=Sem+cadastro").get_data(as_text=True)
    assert ">15102<" in html and "A última releitura falhou" in html
    antes = len(campo.pedidos)
    logado.get("/t/campo/aprovacao")
    assert len(campo.pedidos) == antes                 # 5 min sem pedir de novo ao Fracttal


def test_tela_do_nexus(logado, campo):
    html = logado.get("/t/campo/aprovacao?ver=Sem+cadastro").get_data(as_text=True)
    assert "<iframe" not in html and 'class="campo-nativa"' in html
    assert "Evidência completa" in html and "Precisa do seu olho" in html and "Fechadas fora do App" in html
    assert ">15102<" in html and ">15088<" in html and ">15002<" in html
    html = logado.get("/t/campo/aprovacao?ver=Sem+cadastro&balde=olho").get_data(as_text=True)
    assert ">15088<" in html and ">15102<" not in html


def test_tela_com_fracttal_recusando_avisa(logado, campo):
    campo.recusar = True
    leitura.limpar_cache()
    html = logado.get("/t/campo/aprovacao").get_data(as_text=True)
    assert "O Fracttal não entregou a fila" in html and "Abrir no App" not in html and "azurewebsites" not in html
