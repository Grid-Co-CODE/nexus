"""O canto central do OS Creator no Raio-X (31/10/2026; item 0 da 3.1+3.2 para os ativos, a 3.2 para a lista de OS).

O Levi não tem acesso ao servidor: a 1ª noite do leitor dos ativos (a paridade REST x RPC, as descrições cortadas pelo
detector de endereço) e a 1ª carga da lista de OS só se conferem pela tela. A seção do OS Creator do Raio-X (a da tarefa
0.4) ganha o bloco do canto central: o estado de cada peça resumido, só para administrador como o resto do Raio-X, e sem
texto de ativo, de OS nem nome de pessoa (só contagens, datas e ids).

O que estes testes seguram:
- o bloco dos ativos aparece com um estado inventado: a fonte, o lido em, a versão, a prontidão do leitor, a paridade (com
  as coberturas), o REST (a última boa e a última falha), as descrições cortadas (o número e os ids) e o disco;
- a peça irmã, a lista central de OS (3.2): quantas OS e quantas abertas, a janela lida inteira, a última entrega de cada
  faixa (e quem entregou as abertas), as falhas, os campos que o REST trouxe, o disco e a memória;
- elas não quebram sem o leitor ligado (o PC) nem com o OS Creator ainda não aberto no processo (o módulo nem carregado);
- a resposta não leva o texto da descrição de nenhum ativo, nem o de uma OS, nem o nome de uma pessoa.
Nada vai à rede; o catálogo e os estados são inventados (repositório público)."""
import re
import sys
import time

import pytest

from nexus.casca import raio_x as R
from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import ativos_central as AC  # noqa: E402
import ativos_leitor as AL  # noqa: E402
import os_central as OC  # noqa: E402
import os_leitor as OL  # noqa: E402

from test_oscreator_ativos_leitor import ARVORE, _catalogo_de  # noqa: E402


@pytest.fixture(autouse=True)
def _leve(monkeypatch):
    """O que não é deste bloco fica leve (o processador espera 1 s; a memória e a plataforma leem o /proc e arquivos), e o
    catálogo e o leitor começam limpos."""
    monkeypatch.setattr(R, "_processador", lambda janela_s=1.0: {"pct": 10, "nucleos": 4, "carga": None})
    monkeypatch.setattr(R, "_memoria_por_programa", lambda prazo_s=R.PRAZO_MEMORIA_S: None)
    monkeypatch.setattr(R, "RELATORIO_WEB", "/nao/existe/web.json")
    monkeypatch.setattr(R, "RELATORIO_WORKER", "/nao/existe/worker.json")
    for nome in ("_WORKER", "_WEB", "_MEMORIA", "_THREADS"):
        monkeypatch.setattr(R, nome, {"thread": None, "ultimo": None, "quando": None}, raising=False)
    monkeypatch.setattr(R, "_secao_uso_os", lambda app: {"tem": False, "banco_txt": "", "motivo": "teste"})
    for m in (AC, AL, OC, OL):
        m.reiniciar()
    yield
    OC.esperar_gravacao(5)
    for m in (AC, AL, OC, OL):
        m.reiniciar()


def _bloco(html: str) -> str:
    ini = html.index('id="canto-central"')
    return html[ini:html.index("</section>", ini)]


def _texto(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _pagina(logado) -> str:
    r = logado.get("/t/base/raio-x")
    assert r.status_code == 200
    return r.get_data(as_text=True)


def test_o_bloco_dos_ativos_com_um_estado_inventado(app, logado):
    agora = time.time()
    cat = _catalogo_de(ARVORE, lido_em=agora - 3600)
    AC.anotar_paridade_rest({"vale": True, "em": agora - 1800, "cob_ref": 99.5, "cob_rest": 100.0, "contra": "rpc",
                             "motivo": "9 códigos em comum"})
    AC.anotar_leitura_rest(True)
    AC.anotar_leitura_rest(False, "a leitura da noite: HTTPError: 500 do Fracttal")
    AC.anotar_descricao_cortada({"n": 3, "exemplos": [40, 41, 42]})
    app.config["NEXUS_PCM_FRACTTAL_TESTE"] = {"FRACTTAL_CLIENT_ID": "id-de-mentira", "FRACTTAL_CLIENT_SECRET": "s"}
    AL.ligar(app)                                                    # como no servidor, sem o laço (é teste)
    bloco = _bloco(_pagina(logado))
    txt = _texto(bloco)
    assert "Ativos centrais" in txt
    assert "rpc" in txt and cat.versao[:10] in txt and "%d ativos" % len(cat.lista) in txt
    assert "99,5" in txt and "100,0" in txt                         # as coberturas da paridade, em pt-BR
    assert "500 do Fracttal" in txt and "não está pronto" in txt    # a falha do REST depois da boa derruba a prontidão
    assert "40, 41, 42" in txt and "3 descrições" in txt
    assert "disco" in txt.lower()
    # nada de texto de ativo: nem a descrição, nem o caminho, nem o nome do cliente
    for it in ARVORE:
        desc = it["description"].split("{")[0].strip()
        assert desc not in bloco, desc
    assert "Cliente Alfa" not in bloco and "Usina Gama" not in bloco


def test_o_bloco_sem_o_leitor_ligado_o_pc(app, logado):
    """O PC: o OS Creator aberto (o módulo carregado), sem catálogo e sem o leitor (só o servir.py liga)."""
    txt = _texto(_bloco(_pagina(logado)))
    assert "Ativos centrais" in txt and "sem catálogo" in txt
    assert "só o servir.py liga o leitor" in txt


def test_o_bloco_com_o_os_creator_ainda_nao_aberto(app, logado, monkeypatch):
    """O módulo nem carregado no processo (ninguém abriu o OS Creator): o Raio-X não o importa e não quebra."""
    monkeypatch.delitem(sys.modules, "ativos_central")
    txt = _texto(_bloco(_pagina(logado)))
    assert "Ativos centrais" in txt and "ainda não foi aberto" in txt
    assert "ativos_central" not in sys.modules                       # o Raio-X não importou o catálogo


def test_o_bloco_nunca_derruba_a_pagina(app, logado, monkeypatch):
    def quebra():
        raise RuntimeError("defeito no estado")
    monkeypatch.setattr(AC, "estado", quebra)
    txt = _texto(_bloco(_pagina(logado)))
    assert "Ativos centrais" in txt and "não consegui" in txt.lower()


def test_so_administrador_ve_o_bloco(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"], s["admin"] = True, False
        s["usuario"] = {"email": "pessoa@exemplo.invalid", "nome": "Pessoa", "perfil": ""}
    assert c.get("/t/base/raio-x").status_code == 403


def test_o_bloco_sem_cor_fixa_e_sem_estilo(app, logado):
    _catalogo_de(ARVORE)
    bloco = _bloco(_pagina(logado))
    assert 'style="' not in bloco and not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", bloco)


# ── a lista central de OS (3.2) ──────────────────────────────────────────────────────────────────────────────────────────
def _os(os_id, status=1, dias=1.0, quem="Pessoa Fictícia Sete", desc="Descrição inventada que não pode aparecer"):
    from datetime import datetime, timedelta, timezone
    criada = (datetime.now(timezone.utc) - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    return {"id_work_orders_tasks": os_id * 10, "id_work_order": os_id, "wo_folio": str(30000 + os_id),
            "id_status_work_order": str(status), "description": desc, "items_log_description": "Item Inventado { X-1 }",
            "creation_date": criada, "created_by": quem, "code_create_by": "PF07", "user_assigned": quem,
            "id_personnel": 707, "tasks_log_task_type_main": "Corretiva", "labels": []}


def test_o_bloco_da_lista_de_os_com_um_estado_inventado(app, logado):
    from datetime import datetime, timedelta, timezone
    noventa = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    OC.receber([_os(1), _os(2), _os(3, status=3, dias=4), _os(4, status=2, dias=10)], OC.NOITE, desde=noventa)
    OC.receber([_os(1), _os(4, status=2, dias=10)], OC.ABERTAS, quem="tarefas_os")         # a 2 fica "a conferir"
    app.config["NEXUS_PCM_FRACTTAL_TESTE"] = {"FRACTTAL_CLIENT_ID": "id-de-mentira", "FRACTTAL_CLIENT_SECRET": "s"}
    OL.ligar(app)
    agora = time.time()
    OL._ESTADO["faixas"]["sete_dias"] = {"faixa": "sete_dias", "inicio": agora - 60, "fim": agora - 50, "pedidos": 4,
                                         "os": 0, "resultado": "a leitura não veio inteira: nada mudou",
                                         "erro": "LeituraIncompleta: a página 200 repetiu as anteriores"}
    # a leitura que a lista recusou (a trava de encolhimento, rodada 1): a faixa e o motivo, só com contagens
    OC._ESTADO["recusas"]["noite"] = {"faixa": "noite", "em": agora - 30, "de": 250, "sairiam": 150, "limite": 12,
                                      "motivo": "a noite encolheria a lista: tiraria 150 das 250 OS que ela cobre"}
    # e a que passou na 2ª leitura igual (o apagamento de verdade, rodada 2)
    OC._ESTADO["confirmadas"]["sete_dias"] = {"faixa": "sete_dias", "em": agora - 20, "de": 40, "sairam": 13,
                                              "motivo": "aceita na 2ª leitura: os 7 dias marcaram 13 das 40 OS"}
    bloco = _bloco(_pagina(logado))
    txt = _texto(bloco)
    assert "Lista central de OS" in txt
    assert "4 OS" in txt and "2 abertas" in txt and "1 a conferir" in txt
    assert noventa[8:10] + "/" + noventa[5:7] in txt                                       # a janela lida inteira, de 90 dias
    assert "tarefas_os" in txt and "abertas" in txt                                       # quem entregou as abertas
    assert "repetiu as anteriores" in txt and "FALHOU" in txt                              # a falha da faixa, com o motivo
    assert "4 pedidos" in txt and "disco" in txt.lower() and "memória" in txt.lower()
    assert "recusou" in txt and "tiraria 150 das 250 OS" in txt                            # a trava de encolhimento
    assert "aceita na 2ª leitura" in txt and "marcaram 13 das 40 OS" in txt
    assert "Ativos centrais" in txt                                                        # as duas peças, no mesmo bloco
    # nada de texto de OS nem nome de pessoa
    assert "Descrição inventada" not in bloco and "Pessoa Fictícia Sete" not in bloco and "Item Inventado" not in bloco


def test_o_bloco_da_lista_de_os_sem_o_leitor_e_sem_o_os_creator(app, logado, monkeypatch):
    txt = _texto(_bloco(_pagina(logado)))
    assert "Lista central de OS" in txt and "vazia" in txt and "só o servir.py liga o leitor" in txt
    monkeypatch.delitem(sys.modules, "os_central")
    txt = _texto(_bloco(_pagina(logado)))
    assert "Lista central de OS" in txt and "ainda não foi aberto" in txt and "os_central" not in sys.modules


def test_o_leitor_que_nao_ligou_na_subida_aparece_no_raio_x(app, logado):
    """O `servir.py` sobe o Nexus sem o leitor que quebrou (`ponte.ligar_leitor_do_clone`); a peça dele diz NÃO LIGOU e o erro, e
    não a frase de quem está no PC ("só o servir.py liga o leitor"). Quem não quebrou segue como era."""
    app.extensions[ponte.FALHOS] = {"os_leitor": "ImportError: No module named 'x'", "ativos_leitor": "SyntaxError: o clone quebrou"}
    txt = _texto(_bloco(_pagina(logado)))
    assert txt.count("NÃO LIGOU") == 2 and "ImportError: No module named" in txt and "SyntaxError: o clone quebrou" in txt
    assert "a pilha está no log do servidor" in txt
    assert "Catálogos pequenos" in txt                                         # a terceira peça segue como era (sem o aviso)


def test_a_ultima_noite_dos_ativos_e_a_recusa_aparecem_no_raio_x(app, logado, tmp_path):
    """Revisão final: a 1ª noite só se confere pelo Raio-X (o Levi não tem acesso ao servidor). O bloco dos ativos mostra o resultado
    da última leitura inteira (a hora, se o catálogo trocou, os pedidos, a foto do banco: gravou, linhas, mudaram, erro) e a
    troca recusada, e depois do reinício eles voltam do `ativos_estado.json`."""
    from datetime import datetime, timedelta, timezone
    brt = timezone(timedelta(hours=-3))
    inicio = datetime(2026, 11, 1, 2, 15, tzinfo=brt).timestamp()
    pasta = str(tmp_path / "ativos")
    AC.reiniciar(pasta=pasta)
    _catalogo_de(ARVORE)
    AC.anotar_noite({"inicio": inicio, "fim": inicio + 17 * 60, "ok": True, "pedidos": 830, "itens": 27100, "registros": 27050,
                     "sem_pai": 3, "resultado": "trocou",
                     "foto": {"gravou": True, "linhas": 27050, "mudaram": 12, "entraram": 3, "sairam": 1, "descricao_cortada": 2}})
    AC.reiniciar(pasta=pasta)                                            # o reinício: a memória se vai; a noite volta do disco
    AL.reiniciar()
    assert AC.estado()["noite"]["pedidos"] == 830                        # o 1º `atual()` do processo faz o boot local
    _catalogo_de(ARVORE)
    txt = _texto(_bloco(_pagina(logado)))
    assert "Última noite" in txt and "01/11 02:15" in txt and "levou 17 min" in txt
    assert "o catálogo aceitou a leitura" in txt and "830 pedidos, 27100 itens, 27050 registros, 3 sem o pai" in txt
    assert "foto do banco: gravou, 27050 linhas, 12 mudaram, 3 entraram, 1 saíram, 2 descrições cortadas" in txt
    # a noite que não trocou o catálogo e a foto que deu erro
    AC.anotar_noite({"inicio": inicio, "fim": inicio + 60, "ok": False, "pedidos": 4, "itens": 0, "registros": 0, "sem_pai": 0,
                     "resultado": "a leitura não veio inteira (LeituraIncompleta: vieram 300 de 27100): nada mudou",
                     "foto": {"erro": "o banco recusou a gravação (HTTP 500)"}})
    txt = _texto(_bloco(_pagina(logado)))
    assert "NÃO TROCOU O CATÁLOGO" in txt and "vieram 300 de 27100" in txt and "foto do banco: ERRO: o banco recusou" in txt
    # a troca recusada (a lista vazia) é dita, com a hora e os tamanhos
    AC.trocar([], "rest")
    txt = _texto(_bloco(_pagina(logado)))
    assert "Troca recusada" in txt and "a lista veio vazia" in txt
    # sem noite nenhuma: diz que ainda não houve
    AC.reiniciar()
    _catalogo_de(ARVORE)
    assert "ainda não houve neste servidor" in _texto(_bloco(_pagina(logado)))


def test_a_noite_da_lista_que_falhou_aparece_no_raio_x_depois_do_reinicio(app, logado, tmp_path):
    """A leitura da noite da lista de OS que falhou antes do reinício aparece na faixa "A noite" (FALHOU, quando, depois de quantos
    pedidos e o motivo), vinda do cabeçalho da cópia em disco; sem texto de OS nem nome."""
    from datetime import datetime, timedelta, timezone

    import os_disco as OD
    inicio = datetime(2026, 11, 1, 3, 21, tzinfo=timezone(timedelta(hours=-3))).timestamp()
    antes, OD.GRAVAR_A_CADA_S = OD.GRAVAR_A_CADA_S, 0
    try:
        OC.reiniciar(pasta=str(tmp_path / "os"))
        OC.anotar_leitura("noite", {"faixa": "noite", "inicio": inicio, "fim": inicio + 90, "pedidos": 12, "os": 0, "linhas": 0,
                                   "resultado": "a leitura não veio inteira (LeituraIncompleta: a página 8 veio curta): nada mudou",
                                   "erro": "LeituraIncompleta: a página 8 veio curta"})
        assert OC.esperar_gravacao(5)
        OC.reiniciar(pasta=str(tmp_path / "os"))                          # o reinício (um deploy)
        OL.reiniciar()
        txt = _texto(_bloco(_pagina(logado)))
    finally:
        OD.GRAVAR_A_CADA_S = antes
    assert "A noite" in txt and "FALHOU em 01/11 03:21, depois de 12 pedidos: LeituraIncompleta: a página 8 veio curta" in txt
