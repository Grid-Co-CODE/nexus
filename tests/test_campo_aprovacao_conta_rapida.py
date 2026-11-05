"""A conta da Aprovação de OS sem refazer o que não muda (Desempenho, 05/11/2026).

O caso: a 1ª visita à Aprovação de OS depois do deploy (c82bf99) esperou 97 s pelo 1º byte, e o Raio-X contou 15
pedidos presos em 24 h, o último "trabalhando" (processador, não rede) na `/t/campo/aprovacao`. Medido no PC com uma fila
de 5.500 tarefas sobre o registro e o cadastro reais: 23 s de conta fria. A cópia da regra do App devolve no máximo 200
linhas por chamada, e a `fila_toda` junta as 28 páginas; a cada página a fonte remontava o registro do App inteiro (o
`livros_app.registro` chamado 161.472 vezes para 5.568 fechamentos) e as tabelas de rondas. E duas visitas ao mesmo tempo
faziam a conta duas vezes, disputando o processador com a releitura da fila. A regra copiada não muda (`regras_app.py`
não se edita): muda de onde o dado vem e quem espera quem.
"""
import threading
import time

from test_campo_livros_app import livros  # noqa: F401 — a fixture dos livros do App

from nexus.campo import aprovacao, leitura, livros_app, regras_app, tabelas


def test_o_registro_do_app_e_montado_uma_vez_por_leitura_dos_livros(livros, monkeypatch):  # noqa: F811
    f, _api = livros
    montados, real = [], livros_app.registro
    monkeypatch.setattr(livros_app, "registro", lambda *a, **k: montados.append(1) or real(*a, **k))
    for _pagina in range(5):                                          # as páginas da fila_toda
        tabelas.tabela("qualidadelog").query_entities("PartitionKey eq 'q'")
        tabelas.tabela("rondaos").query_entities("PartitionKey eq 'os'")
    assert len(montados) == 4, f"{len(montados)} montagens de 4 fechamentos: o registro refeito a cada página"
    f.limpar()                                                        # os livros relidos (a cópia de 5 min venceu)
    tabelas.tabela("qualidadelog").query_entities("PartitionKey eq 'q'")
    assert len(montados) == 8


def _fila_lenta(monkeypatch, chamadas):
    def lenta(req, esc):
        chamadas.append(req.params.get("pag"))
        time.sleep(0.2)
        return {"linhas": [{"os": "1", "id_wt": 1}], "pagina": {"paginas": 1}, "janela": {}, "resumo": {},
                "baldes": {}, "sem_cadastro": 0}
    monkeypatch.setattr(regras_app, "_fila_supervisao", lenta)
    monkeypatch.setattr(regras_app, "_FILA_CACHE", {"t": time.time(), "ts": time.time(), "linhas": [{"id_work_orders_tasks": 1}]})
    monkeypatch.setattr(aprovacao, "_ultimo_fechamento_no_app", lambda: {})
    monkeypatch.setattr(aprovacao, "_PRONTA", {})
    leitura.limpar()


def test_duas_visitas_ao_mesmo_tempo_fazem_a_conta_uma_vez(monkeypatch):
    chamadas, saidas = [], []
    _fila_lenta(monkeypatch, chamadas)
    visitas = [threading.Thread(target=lambda: saidas.append(aprovacao.fila_toda(aprovacao.FILA_INTEIRA)))
               for _ in range(3)]
    for v in visitas:
        v.start()
    for v in visitas:
        v.join(10)
    assert len(saidas) == 3 and all((s.dados or {}).get("linhas") for s in saidas)
    assert chamadas == ["1"], f"{len(chamadas)} contas para a mesma fila: cada visita refazia a conta"


def test_depois_do_deploy_com_a_fila_do_disco_velha_a_conta_comeca_no_boot(monkeypatch):
    """O deploy acha a fila do disco com mais de 10 min e a relê do Fracttal (minutos). Enquanto isso a visita fazia a
    conta sobre a fila do disco na hora: agora ela começa no boot, e a visita a encontra pronta ou em curso."""
    feitos, prontas = [], threading.Event()
    monkeypatch.setattr(aprovacao, "carregar_do_disco",
                        lambda app: regras_app._FILA_CACHE.update(t=time.time() - 3600, ts=time.time() - 3600,
                                                                  linhas=[{"id_work_orders_tasks": 1}]) or True)
    monkeypatch.setattr(regras_app, "_FILA_CACHE", {})
    monkeypatch.setattr(aprovacao, "_reler", lambda app: feitos.append("releitura"))
    monkeypatch.setattr(aprovacao, "_ESTADO", dict(aprovacao._ESTADO, lendo=False))
    monkeypatch.setattr(aprovacao, "fila_toda", lambda params, usinas=None: feitos.append("conta") or prontas.set())
    aprovacao.aquecer(None)
    assert prontas.wait(5), "a conta da fila do disco não começou no boot"
    assert "releitura" in feitos or [t for t in threading.enumerate() if t.name == "nexus-fila-fracttal"]
