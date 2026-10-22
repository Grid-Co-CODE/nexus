"""A justificativa do App não segura o Nexus (22/10/2026, nexus/pcm/motivos_app.py e a rota /t/pcm/motivos/app).

Caso real, 22/10/2026 das 13:51 às 14:08: com o servidor no swap, cada gravação no livro dos motivos levava minutos; o
servidor do App desiste em 20 s e manda de novo, e 7 justificativas de técnicos viraram 46 envios. Cada envio ficou
numa das 8 threads do Nexus esperando a vez de gravar (o Raio-X das 14:02: 6 de 8 threads nesta rota, 3,5 a 6 min
cada), e o Nexus parou para todo mundo. As 7 foram gravadas pelo envio que o App já tinha dado por perdido; os
reenvios responderam "gravou: false" e o App não escreveu a nota nem a etiqueta no Fracttal de nenhuma.

O que estes testes seguram: a justificativa entra numa fila na 1ª tentativa e é gravada por trás, mesmo quando o pedido
já respondeu 503; o pedido espera no máximo APP_ESPERA_S e no máximo dois esperam (o resto responde 503 na hora); o
reenvio não entra de novo na fila e recebe a resposta guardada; as que esperam vão juntas, numa leitura e numa gravação
do livro, e a recusa de uma não derruba as outras; a leitura que falha dentro da gravação responde 503, não 400 (o 400
o App toma por recusa definitiva e descarta a justificativa); e o reenvio do que o mesmo técnico já gravou hoje volta
"gravou: true", sem gravar nada de novo, para o App escrever a nota e a etiqueta."""
import threading
import time
from datetime import timedelta

import pytest

from nexus.pcm import motivos as M
from nexus.pcm import motivos_app as MA
from test_pcm_geracao import config, origem  # noqa: F401 (fixtures)
from test_pcm_motivos import PESSOA, TEC, _pelo_app, tela  # noqa: F401 (fixture)

OUTRO_TEC = "cd" * 12
CABINE = {"os": "5", "codigo": "UFV1-CAB01", "tarefa": "[Grid Co.] - MPM - Cabine"}
TRAFO = {"os": "5", "codigo": "UFV1-TR01", "tarefa": "[Grid Co.] - MPM - Trafo"}
AVULSA = {"os": "7", "codigo": "UFV2-INV03", "tarefa": "limpeza do  INVERSOR"}      # aberta na Gestão PCM


@pytest.fixture(autouse=True)
def _fila_limpa():
    MA.esquecer()
    yield
    assert MA.esperar_a_fila(15), "o gravador não esvaziou a fila"
    MA.esquecer()


def _motivo(cfg, nome):
    return next(m["id"] for m in M.ativos(M.ler(cfg)) if m["nome"] == nome)


def _corpo(tarefa, motivo, obs="", tec=TEC):
    return dict(tarefa, motivo=motivo, obs=obs, tecnico_hmac=tec, tecnico_nome="Técnico Teste")


def _marcas(cfg):
    return M.ler(cfg, forcar=True)["marcas"]


class _BancoLento:
    """O livro preso na gravação até `soltar` (o banco no swap), contando as leituras e as gravações."""

    def __init__(self, monkeypatch, request):
        self.solta = threading.Event()
        self.leituras = self.gravacoes = self.dentro = 0
        ler0, gravar0 = M._ler_cru, M._gravar_cru

        def ler(cfg):
            self.leituras += 1
            return ler0(cfg)

        def gravar(cfg, tabelas):
            self.dentro += 1
            assert self.solta.wait(10), "o teste não soltou o banco"
            self.gravacoes += 1
            gravar0(cfg, tabelas)
        monkeypatch.setattr(M, "_ler_cru", ler)
        monkeypatch.setattr(M, "_gravar_cru", gravar)
        request.addfinalizer(self.solta.set)          # o gravador nunca fica preso para o próximo teste

    def esperar(self, cond, prazo=5):
        fim = time.monotonic() + prazo
        while not cond():
            assert time.monotonic() < fim, "não chegou ao ponto esperado"
            time.sleep(0.01)


def _em_thread(app, corpo):
    """O envio numa thread (como o waitress), com a resposta em `saida`."""
    saida = {}

    def ir():
        r = _pelo_app(app, corpo)
        saida.update(status=r.status_code, json=r.get_json())
    t = threading.Thread(target=ir, daemon=True)
    t.start()
    return t, saida


def test_o_pedido_solta_a_thread_e_a_justificativa_e_gravada_assim_mesmo(app, tela, monkeypatch, request):
    cfg = app.config
    am = _motivo(cfg, "Aguardando material")
    monkeypatch.setattr(MA, "APP_ESPERA_S", 0.3)
    banco = _BancoLento(monkeypatch, request)
    t0 = time.monotonic()
    r = _pelo_app(app, _corpo(CABINE, am, "falta o disjuntor"))
    assert time.monotonic() - t0 < 3, "o pedido ficou preso esperando o banco"
    assert r.status_code == 503 and "vai ser gravada" in r.get_json()["erro"]
    assert banco.dentro == 1 and MA.esperando() == 0                 # a thread do pedido já está livre
    banco.solta.set()
    assert MA.esperar_a_fila(5)
    assert len(_marcas(cfg)) == 1                                     # gravada sem ninguém esperando
    # o reenvio recebe a resposta guardada: "gravou", e nada gravado de novo
    j = _pelo_app(app, _corpo(CABINE, am, "falta o disjuntor")).get_json()
    assert j["ok"] and j["gravou"] and j["arquivo"] == "em instantes" and j["marca"]["n"] == "Aguardando material"
    # e o seguinte, já sem a resposta guardada, pela última decisão (`repetida`)
    j = _pelo_app(app, _corpo(CABINE, am, "falta o disjuntor")).get_json()
    assert j["ok"] and j["gravou"] and j["arquivo"] == "sem mudança"
    assert len(_marcas(cfg)) == 1 and banco.gravacoes == 1


def test_no_maximo_dois_esperando(app, tela, monkeypatch, request):
    cfg = app.config
    am = _motivo(cfg, "Aguardando material")
    monkeypatch.setattr(MA, "APP_ESPERA_S", 8)
    banco = _BancoLento(monkeypatch, request)
    t1, s1 = _em_thread(app, _corpo(CABINE, am))
    banco.esperar(lambda: banco.dentro == 1)
    t2, s2 = _em_thread(app, _corpo(TRAFO, am))
    banco.esperar(lambda: MA.esperando() == 2)
    t0 = time.monotonic()
    r3 = _pelo_app(app, _corpo(AVULSA, am))
    assert time.monotonic() - t0 < 2 and r3.status_code == 503       # o 3º não espera: responde na hora
    banco.solta.set()
    t1.join(8), t2.join(8)
    assert s1["status"] == s2["status"] == 200 and s1["json"]["gravou"] and s2["json"]["gravou"]
    assert MA.esperar_a_fila(5) and len(_marcas(cfg)) == 3           # o 3º também foi gravado
    assert MA.esperando() == 0


def test_o_reenvio_nao_entra_de_novo_na_fila(app, tela, monkeypatch, request):
    cfg = app.config
    am = _motivo(cfg, "Aguardando material")
    monkeypatch.setattr(MA, "APP_ESPERA_S", 0.2)
    banco = _BancoLento(monkeypatch, request)
    for _ in range(3):                                                # o App manda de novo, e de novo
        assert _pelo_app(app, _corpo(CABINE, am)).status_code == 503
    assert MA.na_fila() == 1
    banco.solta.set()
    assert MA.esperar_a_fila(5) and banco.gravacoes == 1 and banco.leituras == 1
    assert _pelo_app(app, _corpo(CABINE, am)).get_json()["gravou"]


def test_as_que_esperam_vao_juntas_numa_leitura_e_numa_gravacao(app, tela, monkeypatch, request):
    cfg = app.config
    am, en = _motivo(cfg, "Aguardando material"), _motivo(cfg, "Engenharia")
    monkeypatch.setattr(MA, "APP_ESPERA_S", 0.2)
    banco = _BancoLento(monkeypatch, request)
    assert _pelo_app(app, _corpo(CABINE, am)).status_code == 503     # a 1ª grava sozinha (presa no banco)
    for c in (_corpo(TRAFO, am), _corpo(AVULSA, en), _corpo(CABINE, en, tec=OUTRO_TEC)):
        assert _pelo_app(app, c).status_code == 503                   # as 3 esperam na fila
    assert MA.na_fila() == 4
    banco.solta.set()
    assert MA.esperar_a_fila(5)
    assert banco.gravacoes == 2 and banco.leituras == 2               # 4 justificativas, 2 gravações do livro
    assert len(_marcas(cfg)) == 4
    vig = {(m["os"], m["codigo"]): m["motivo"] for k, m in M.vigentes(cfg, M.ler(cfg, forcar=True)).items()
           if not k.startswith("_")}
    assert vig == {("5", "UFV1-CAB01"): "Engenharia", ("5", "UFV1-TR01"): "Aguardando material",
                   ("7", "UFV2-INV03"): "Engenharia"}                 # a ordem de chegada vale


def test_o_lote_recusa_uma_e_grava_as_outras(app, tela, monkeypatch):
    """`marcar_lote`: uma leitura e uma gravação; a recusa de uma (o motivo que não existe, a tarefa sem OS) não derruba
    as outras; a gravação que falha vai para quem mudou e para quem veio depois de uma mudança."""
    cfg = app.config
    am, en = _motivo(cfg, "Aguardando material"), _motivo(cfg, "Engenharia")
    contas = {"ler": 0, "gravar": 0}
    ler0, gravar0 = M._ler_cru, M._gravar_cru
    monkeypatch.setattr(M, "_ler_cru", lambda c: (contas.__setitem__("ler", contas["ler"] + 1), ler0(c))[1])
    monkeypatch.setattr(M, "_gravar_cru", lambda c, t: (contas.__setitem__("gravar", contas["gravar"] + 1),
                                                        gravar0(c, t))[1])

    def p(tarefa, motivo, **k):
        return dict({"tarefa": tarefa, "motivo_id": motivo, "obs": "", "usuario": PESSOA, "origem": "app",
                     "quem_hmac": TEC}, **k)
    r = M.marcar_lote(cfg, [p(CABINE, am), p(TRAFO, 999), p({"os": "x", "tarefa": "t"}, am), p(AVULSA, en)])
    assert contas == {"ler": 1, "gravar": 1}
    assert r[0]["gravou"] and r[3]["gravou"] and len(_marcas(cfg)) == 2
    assert isinstance(r[1], M.Recusada) and "não existe mais" in str(r[1])
    assert isinstance(r[2], M.Recusada) and "não foi achada" in str(r[2])
    quem0 = M._quem

    def quem(cfg, usuario):
        if usuario and usuario.get("nome") == "quebra":
            raise RuntimeError("defeito no código da pessoa")
        return quem0(cfg, usuario)
    monkeypatch.setattr(M, "_quem", quem)
    r = M.marcar_lote(cfg, [p(TRAFO, en, usuario={"nome": "quebra"}), p(dict(AVULSA, codigo="UFV2-INV05"), en)])
    assert isinstance(r[0], RuntimeError) and r[1]["gravou"]
    monkeypatch.setattr(M, "_quem", quem0)

    def suja_e_falha(cru):
        cru[M.ABA_MARCA].append({"item_id": "lixo", "decidida_em": "2026-10-22T00:00:00Z"})
        raise RuntimeError("defeito no meio")
    r = M._gravar_lote(cfg, [suja_e_falha, M._preparar_marca(cfg, TRAFO, en, "", PESSOA, origem="app")[0]])
    assert isinstance(r[0], RuntimeError) and r[1]["gravou"]
    assert "lixo" not in {m["item_id"] for m in _marcas(cfg)} and len(_marcas(cfg)) == 4
    # a gravação que falha: quem decidiu antes de qualquer mudança fica com o resultado
    monkeypatch.setattr(M, "_gravar_cru", lambda c, t: (_ for _ in ()).throw(ConnectionError("caiu")))
    r = M.marcar_lote(cfg, [p(dict(AVULSA, codigo="UFV2-INV08"), None), p(CABINE, en),
                            p(dict(AVULSA, codigo="UFV2-INV09"), None)])
    assert r[0] == {"gravou": False, "marca": None, "repetida": False}
    assert isinstance(r[1], ConnectionError) and isinstance(r[2], ConnectionError)
    assert len(_marcas(cfg)) == 4                                     # nada gravado


def test_banco_que_cai_dentro_da_gravacao_responde_503(app, tela, monkeypatch):
    """O 400 o App toma por recusa definitiva (tira a justificativa do aparelho); banco fora é 503 (tenta de novo), e
    essa resposta não fica guardada: o reenvio grava de novo."""
    cfg = app.config
    am = _motivo(cfg, "Aguardando material")
    M.ler(cfg)                                                # a rota decide pela leitura guardada
    ler0 = M._ler_cru

    def fora(cfg):
        raise ConnectionError("o banco não respondeu")
    monkeypatch.setattr(M, "_ler_cru", fora)
    r = _pelo_app(app, _corpo(CABINE, am))
    assert r.status_code == 503 and not r.get_json()["ok"] and "nada foi gravado" in r.get_json()["erro"]
    with pytest.raises(M.Recusada, match="Não consegui ler os motivos"):      # nas telas, a recusa de sempre
        M.marcar(cfg, CABINE, am, "", PESSOA)
    monkeypatch.setattr(M, "_ler_cru", ler0)
    j = _pelo_app(app, _corpo(CABINE, am)).get_json()
    assert j["ok"] and j["gravou"] and j["arquivo"] == "em instantes" and len(_marcas(cfg)) == 1


def test_a_fila_tem_teto(app, tela, monkeypatch, request):
    cfg = app.config
    am = _motivo(cfg, "Aguardando material")
    monkeypatch.setattr(MA, "APP_ESPERA_S", 0.2)
    monkeypatch.setattr(MA, "FILA_MAX", 1)
    banco = _BancoLento(monkeypatch, request)
    assert _pelo_app(app, _corpo(CABINE, am)).status_code == 503     # gravando
    assert _pelo_app(app, _corpo(TRAFO, am)).status_code == 503      # na fila
    r = _pelo_app(app, _corpo(AVULSA, am))
    assert r.status_code == 503 and "cheia" in r.get_json()["erro"]
    banco.solta.set()
    assert MA.esperar_a_fila(5) and len(_marcas(cfg)) == 2


def test_a_resposta_ruim_nao_fica_guardada(app, tela, monkeypatch):
    """O banco que caiu no lote de quem já desistiu de esperar: o reenvio grava de novo, não recebe o 503 guardado."""
    cfg = app.config
    am = _motivo(cfg, "Aguardando material")
    monkeypatch.setattr(MA, "APP_ESPERA_S", 0.2)
    solta, ler0 = threading.Event(), M._ler_cru

    def lento_e_fora(cfg):
        solta.wait(5)
        raise ConnectionError("o banco não respondeu")
    monkeypatch.setattr(M, "_ler_cru", lento_e_fora)
    assert _pelo_app(app, _corpo(CABINE, am)).status_code == 503
    solta.set()
    assert MA.esperar_a_fila(5)
    monkeypatch.setattr(M, "_ler_cru", ler0)
    j = _pelo_app(app, _corpo(CABINE, am)).get_json()
    assert j["ok"] and j["gravou"] and len(_marcas(cfg)) == 1


def test_o_gravador_nao_morre(app, tela, monkeypatch):
    """O defeito num lote responde 503 a ele, e o gravador segue com os próximos; o lote que volta sem a resposta de
    alguma também (sem isto, aquela ficava "em voo" para sempre, e todo reenvio dela esperava em vão)."""
    from nexus.pcm import telas as T
    cfg = app.config
    am = _motivo(cfg, "Aguardando material")
    certo = T._motivos_do_app

    def defeito(cfg, ds):
        raise RuntimeError("defeito no lote")
    monkeypatch.setattr(T, "_motivos_do_app", defeito)
    r = _pelo_app(app, _corpo(CABINE, am))
    assert r.status_code == 503 and "não gravou (RuntimeError)" in r.get_json()["erro"]
    monkeypatch.setattr(T, "_motivos_do_app", lambda cfg, ds: [])
    monkeypatch.setattr(MA, "APP_ESPERA_S", 2)
    r = _pelo_app(app, _corpo(CABINE, am))
    assert r.status_code == 503 and "não gravou" in r.get_json()["erro"]
    monkeypatch.setattr(T, "_motivos_do_app", certo)
    assert _pelo_app(app, _corpo(CABINE, am)).get_json()["gravou"]


def test_o_defeito_numa_nao_segura_as_outras_do_lote(app, tela, monkeypatch, request):
    from nexus.pcm import telas as T
    cfg = app.config
    am = _motivo(cfg, "Aguardando material")
    achar = T._tarefa_do_app

    def quebra_na_trafo(cfg, d):
        if d["codigo"] == "UFV1-TR01":
            raise KeyError("linha torta na programação")
        return achar(cfg, d)
    monkeypatch.setattr(T, "_tarefa_do_app", quebra_na_trafo)
    monkeypatch.setattr(MA, "APP_ESPERA_S", 0.2)
    banco = _BancoLento(monkeypatch, request)
    assert _pelo_app(app, _corpo(AVULSA, am)).status_code == 503     # segura o gravador
    assert _pelo_app(app, _corpo(TRAFO, am)).status_code == 503      # a torta e a boa no mesmo lote
    assert _pelo_app(app, _corpo(CABINE, am)).status_code == 503
    banco.solta.set()
    assert MA.esperar_a_fila(5)
    assert {m["codigo_ativo"] for m in _marcas(cfg)} == {"UFV2-INV03", "UFV1-CAB01"}
    r = _pelo_app(app, _corpo(TRAFO, am))
    assert r.status_code == 503 and "não gravou (KeyError)" in r.get_json()["erro"]   # a ruim não ficou guardada
    assert _pelo_app(app, _corpo(CABINE, am)).get_json()["gravou"]


def test_a_gravacao_que_falha_responde_503(app, tela, monkeypatch):
    cfg = app.config
    am = _motivo(cfg, "Aguardando material")
    monkeypatch.setattr(M, "_gravar_cru", lambda c, t: (_ for _ in ()).throw(ConnectionError("caiu")))
    r = _pelo_app(app, _corpo(CABINE, am))
    assert r.status_code == 503 and "não gravou (ConnectionError)" in r.get_json()["erro"] and not _marcas(cfg)


def test_a_resposta_pronta_nao_espera_vaga(app, tela, monkeypatch, request):
    """O reenvio da que já foi gravada recebe a resposta na hora, mesmo com os dois lugares de espera tomados."""
    cfg = app.config
    am = _motivo(cfg, "Aguardando material")
    monkeypatch.setattr(MA, "APP_ESPERA_S", 0.2)
    banco = _BancoLento(monkeypatch, request)
    assert _pelo_app(app, _corpo(CABINE, am)).status_code == 503
    banco.solta.set()
    assert MA.esperar_a_fila(5)
    banco.solta.clear()                                               # o banco volta a ficar lento
    monkeypatch.setattr(MA, "APP_ESPERA_S", 8)
    t2, s2 = _em_thread(app, _corpo(TRAFO, am))
    t3, s3 = _em_thread(app, _corpo(AVULSA, am))
    banco.esperar(lambda: MA.esperando() == 2)
    t0 = time.monotonic()
    r = _pelo_app(app, _corpo(CABINE, am))
    assert r.status_code == 200 and r.get_json()["gravou"] and time.monotonic() - t0 < 2
    banco.solta.set()
    t2.join(8), t3.join(8)
    assert s2["status"] == s3["status"] == 200


def test_a_resposta_guardada_tem_prazo(app, tela, monkeypatch, request):
    cfg = app.config
    am = _motivo(cfg, "Aguardando material")
    monkeypatch.setattr(MA, "APP_ESPERA_S", 0.2)
    banco = _BancoLento(monkeypatch, request)
    assert _pelo_app(app, _corpo(CABINE, am)).status_code == 503
    banco.solta.set()
    assert MA.esperar_a_fila(5)
    monkeypatch.setattr(MA, "GUARDA_S", 0)                            # passou o prazo: vale a última decisão
    j = _pelo_app(app, _corpo(CABINE, am)).get_json()
    assert j["gravou"] and j["arquivo"] == "sem mudança" and banco.leituras == 2


def test_cada_app_com_a_sua_fila(app, tela, monkeypatch, request, tmp_path):
    """Dois apps no mesmo processo (os testes): a resposta guardada e o lote de um não valem para o outro."""
    from nexus import create_app
    outro = create_app({"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": "x"})
    outro.config.update({k: v for k, v in app.config.items() if k.startswith("NEXUS_")}, TESTING=True,
                        NEXUS_PCM_MOTIVOS_ARQUIVO=str(tmp_path / "outro.json"))
    am, en = _motivo(app.config, "Aguardando material"), _motivo(app.config, "Engenharia")
    monkeypatch.setattr(MA, "APP_ESPERA_S", 0.2)
    banco = _BancoLento(monkeypatch, request)
    # a resposta guardada de um app não vale para o outro
    assert _pelo_app(app, _corpo(AVULSA, am)).status_code == 503
    banco.solta.set()
    assert MA.esperar_a_fila(5)
    assert _pelo_app(outro, _corpo(AVULSA, am)).get_json()["gravou"]
    assert len(_marcas(app.config)) == len(_marcas(outro.config)) == 1
    banco.solta.clear()
    banco.gravacoes = 0
    assert _pelo_app(app, _corpo(TRAFO, en)).status_code == 503       # segura o gravador
    assert _pelo_app(app, _corpo(CABINE, am)).status_code == 503
    assert _pelo_app(outro, _corpo(CABINE, am)).status_code == 503    # a mesma, no outro app: outra na fila
    assert MA.na_fila() == 3
    banco.solta.set()
    assert MA.esperar_a_fila(5) and banco.gravacoes == 3
    assert len(_marcas(app.config)) == 3 and len(_marcas(outro.config)) == 2


def test_o_reenvio_da_justificativa_ja_gravada_hoje_volta_como_gravada(app, tela, monkeypatch):
    """O App só escreve a nota e a etiqueta no Fracttal com "gravou: true"; o envio que gravou e cuja resposta o App não
    viu (passou dos 20 s dele, ou o Nexus reiniciou) fazia o reenvio voltar "false", e a nota e a etiqueta nunca saíam."""
    cfg = app.config
    am, en = _motivo(cfg, "Aguardando material"), _motivo(cfg, "Engenharia")
    j1 = _pelo_app(app, _corpo(CABINE, am, "falta o disjuntor")).get_json()
    assert j1["gravou"]
    j2 = _pelo_app(app, _corpo(CABINE, am, "falta o disjuntor")).get_json()   # a resposta do 1º não chegou
    assert j2["ok"] and j2["gravou"] and j2["marca"] == j1["marca"] and j2["arquivo"] == "sem mudança"
    assert len(_marcas(cfg)) == 1 and len(tela.commits) == 1                  # nada gravado de novo
    # outro técnico com a mesma justificativa: não foi ele quem gravou
    assert not _pelo_app(app, _corpo(CABINE, am, "falta o disjuntor", tec=OUTRO_TEC)).get_json()["gravou"]
    # tirar o motivo, e o reenvio de tirar
    assert _pelo_app(app, _corpo(CABINE, None)).get_json()["gravou"]
    j = _pelo_app(app, _corpo(CABINE, None)).get_json()
    assert j["gravou"] and j["marca"] is None and len(_marcas(cfg)) == 2
    assert not _pelo_app(app, _corpo(CABINE, None, tec=OUTRO_TEC)).get_json()["gravou"]
    # a marca feita pelo PCM no Nexus com o mesmo código de pessoa não é "do App": o reenvio não a toma por dele
    M.marcar(cfg, TRAFO, en, "", PESSOA, origem="painel", quem_hmac=TEC)
    assert not _pelo_app(app, _corpo(TRAFO, en)).get_json()["gravou"]
    # tirar o que nunca teve motivo continua "sem mudança"
    j = _pelo_app(app, _corpo(AVULSA, None)).get_json()
    assert j["ok"] and not j["gravou"]


def test_tirar_o_motivo_que_saiu_do_cadastro_nao_e_reenvio(app, tela):
    """A justificativa de hoje cujo motivo o PCM tirou do cadastro deixa de valer; o técnico mandar tirar não é o
    reenvio de nada (a última decisão é a de marcar): "sem mudança", como sempre."""
    cfg = app.config
    am = _motivo(cfg, "Aguardando material")
    assert _pelo_app(app, _corpo(CABINE, am)).get_json()["gravou"]
    M.cadastro(cfg, "excluir", PESSOA, motivo_id=am)
    j = _pelo_app(app, _corpo(CABINE, None)).get_json()
    assert j["ok"] and not j["gravou"]


def test_o_reenvio_de_ontem_nao_e_o_de_hoje(app, tela, monkeypatch):
    """Tirar o motivo ontem e mandar tirar de novo hoje não é reenvio: "sem mudança", como sempre."""
    cfg = app.config
    am = _motivo(cfg, "Aguardando material")
    assert _pelo_app(app, _corpo(CABINE, am)).get_json()["gravou"]
    assert _pelo_app(app, _corpo(CABINE, None)).get_json()["gravou"]
    amanha = M._agora() + timedelta(days=1)
    monkeypatch.setattr(M, "_agora", lambda: amanha)
    assert not _pelo_app(app, _corpo(CABINE, None)).get_json()["gravou"]
