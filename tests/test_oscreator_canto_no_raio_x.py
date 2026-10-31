"""O canto central do OS Creator no Raio-X (31/10/2026; item 0 da 3.1+3.2 para os ativos, a 3.2 para a lista de OS).

O Levi não tem acesso ao servidor: a 1ª noite do leitor dos ativos (a paridade REST x RPC, as descrições cortadas pelo
detector de endereço) e a 1ª carga da lista de OS só se conferem pela tela. A seção do OS Creator do Raio-X (a da tarefa
0.4) ganha o bloco do canto central: o estado de cada peça resumido, só para administrador como o resto do Raio-X, e sem
texto de ativo, de OS nem nome de pessoa (só contagens, datas e ids).

O que estes testes seguram:
- o bloco dos ativos aparece com um estado inventado: a fonte, o lido em, a versão, a prontidão do leitor, a paridade (com
  as coberturas), o REST (a última boa e a última falha), as descrições cortadas (o número e os ids) e o disco;
- ele não quebra sem o leitor ligado (o PC) nem com o OS Creator ainda não aberto no processo (o módulo nem carregado);
- a resposta não leva o texto da descrição de nenhum ativo.
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
    AC.reiniciar()
    AL.reiniciar()
    yield
    AC.reiniciar()
    AL.reiniciar()


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
