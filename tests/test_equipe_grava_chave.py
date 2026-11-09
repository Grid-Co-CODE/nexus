"""A gravação do Mapa de equipe ligada pela tela Base → Chaves (09/11/2026, pedido da sessão Nexus Field: a variável
NEXUS_EQUIPE_GRAVA só existia no .env do servidor, que o Levi não alcança). A chave da tela é da MÁQUINA (o chaves.json
da pasta de dados): gravada no servidor, vale só lá, e a regra "uma máquina por vez" continua. Vence a do .env e vale sem
reiniciar: as rotas do celular conferem a cada pedido (a cópia de 30 s, zerada ao gravar) e o laço do gravador, a cada
rodada."""
import pytest

from nexus.auth import chaves
from nexus.campo.equipe import gravador as G

NOME = "NEXUS_EQUIPE_GRAVA"


@pytest.fixture
def cfg(app, tmp_path):
    app.config["NEXUS_DADOS"] = str(tmp_path)
    app.config.pop(NOME, None)
    chaves._CACHE.clear()
    yield app.config
    app.config.pop(NOME, None)
    chaves._CACHE.clear()


def test_a_conferencia_aceita_so_1_ou_0(app, cfg):
    with app.test_request_context():
        assert "grava nesta máquina" in chaves.gravar(cfg, NOME, "1", "admin")
        assert "não grava nesta máquina" in chaves.gravar(cfg, NOME, "0", "admin")
        for ruim in ("sim", "2", "true", "01"):
            with pytest.raises(chaves.Recusada):
                chaves.gravar(cfg, NOME, ruim, "admin")


def test_a_da_tela_liga_vence_o_env_e_vale_sem_reiniciar(app, cfg):
    assert not G.ativo(cfg)                                   # sem a tela e sem o .env: não grava
    with app.test_request_context():
        chaves.gravar(cfg, NOME, "1", "admin")
    assert G.ativo(cfg)                                       # gravar zera a cópia de 30 s: vale na hora
    cfg[NOME] = "1"
    with app.test_request_context():
        chaves.gravar(cfg, NOME, "0", "admin")
    assert not G.ativo(cfg)                                   # o 0 da tela desliga, mesmo com o .env em 1
    with app.test_request_context():
        chaves.apagar(cfg, NOME, "admin")
    assert G.ativo(cfg)                                       # apagada da tela, volta a do .env


def test_a_chave_que_nao_abre_nao_liga(app, cfg, monkeypatch):
    """O chaves.json ilegível (a leitura que quebra) não liga a gravação: sem saber, não grava."""
    monkeypatch.setattr(chaves, "valor", lambda *a, **k: (_ for _ in ()).throw(OSError("disco")))
    assert not G.ativo(cfg)


def test_o_laco_espera_desligado_e_liga_sem_reiniciar(monkeypatch, app):
    estados = iter([False, False, True, True])
    monkeypatch.setattr(G, "ativo", lambda config: next(estados))
    criados, rodadas = [], []

    class _Gravador:
        def __init__(self, app_, srv):
            criados.append(srv)

        def rodada(self, agora):
            rodadas.append(agora)
    monkeypatch.setattr(G, "Gravador", _Gravador)
    from nexus.campo.equipe import servico
    monkeypatch.setattr(servico, "do_app", lambda app_: "o serviço")
    voltas = []

    def _dorme(s):
        voltas.append(s)
        if len(voltas) == 4:
            raise KeyboardInterrupt
    monkeypatch.setattr(G.time, "sleep", _dorme)
    with pytest.raises(KeyboardInterrupt):
        G._laco(app)
    # desligado nas duas primeiras voltas (nada é montado), ligado nas duas seguintes: um gravador, duas rodadas
    assert criados == ["o serviço"] and len(rodadas) == 2 and voltas == [G.A_CADA_S] * 4


def test_o_laco_sobe_em_toda_maquina_fora_dos_testes(monkeypatch):
    iniciados = []

    class _Thread:
        def __init__(self, target, args, daemon, name):
            self.name = name

        def start(self):
            iniciados.append(self.name)
    monkeypatch.setattr(G.threading, "Thread", _Thread)

    class _App:
        config = {"TESTING": False}                           # sem a gravação ligada: o laço sobe e espera
    G.ligar(_App())
    assert iniciados == ["nexus-equipe-gravador"]
    _App.config = {"TESTING": True}
    G.ligar(_App())
    assert iniciados == ["nexus-equipe-gravador"]             # nunca em teste
