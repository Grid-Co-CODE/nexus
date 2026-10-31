"""A revisão 1 da tarefa 2.2 do canto central do OS Creator (31/10/2026): o leitor dos ativos do servidor que sabe quando NÃO
está pronto, a sondagem estrita, o que se repete e o que falha na hora, e a foto sem o endereço da usina.

O que estes testes seguram:
- a prontidão do leitor expira: a conferência da leitura REST de mais de 30 h, ou uma leitura REST que falhou (a dos novos ou
  a da noite) depois da última boa, tiram o leitor da prontidão, e o botão volta ao RPC; a leitura boa seguinte a devolve, e o
  reinício não a esquece. Os novos demais (mais de 400) não são falha;
- a 1ª conferência pede 99% nos dois sentidos e diz os códigos que faltam; toda noite as coberturas ficam na paridade;
- só o erro de passagem (a recusa, a conexão, o tempo, o 5xx) é repetido; o resto falha na hora, sem esperar;
- a leitura inteira é ordenada pelo id, e o REST que recusa a ordem falha com o motivo claro;
- a foto guarda o que o catálogo não tem pela diferença de ids, e grava a descrição SEM o endereço da usina (Ruling AK);
- o núcleo concorrente dos novos com as funções de verdade: uma leitura por vez, o frescor de 60 s, a espera da que está em
  curso e a que estoura o teto;
- o disco fica com a versão vigente, mesmo com as gravações terminando em ordem trocada;
- com o leitor pronto, o catálogo só vence com 26 h;
- a revisão 2 (Ruling AP): o 4xx da 1ª página diz o que houve (a ordem, a credencial ou o HTTP), e a gravação pendente
  escreve o catálogo do momento (o objeto trocado por outro da mesma versão não a faz ser pulada).
Fracttal, banco e disco são dublês ou pastas de teste: nada vai à rede. Nomes, códigos e usinas são de mentira."""
import sys
import threading
import time

import pytest
import requests
from pg_falso import ApiPGFalsa

from nexus.campo import fracttal
from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
import ativos_central as AC  # noqa: E402
import ativos_leitor as AL  # noqa: E402

from nexus.dados import equipamento as eq  # noqa: E402
from test_oscreator_ativos_leitor import ARVORE, GAMA, RestFalso, _catalogo_de, _it, _lote, _muitos, _rpc  # noqa: E402

BASE = "http://pg.falso"


@pytest.fixture(autouse=True)
def dormidas(monkeypatch):
    AC.reiniciar()
    AL.reiniciar()
    feitas = []
    monkeypatch.setattr(AL, "_dormir", feitas.append)
    monkeypatch.setattr(api, "_ASSETS_RENOVA", {"tentou": time.time()})       # a renovação por trás fica de fora
    yield feitas
    AC.reiniciar()
    AL.reiniciar()


@pytest.fixture
def banco(app):
    pg = ApiPGFalsa(como_texto=True)
    app.extensions["nexus_dados_sessao"] = pg
    app.config.update(GRIDCO_SQL_TOKEN="token-de-teste", GRIDCO_DB_API=BASE)
    return pg


def _conferida(em=None):
    AC.anotar_paridade_rest({"vale": True, "motivo": "conferida", "em": time.time() if em is None else em})


def _ligado():
    AC.ligar_leitor(pedir_novos=lambda: True, esperar_novos=lambda teto, so: {"terminou": True}, estado=lambda: {})


def _novo(i, pai=10):
    return _it(i, "CAL-GAM100-INVR9%d.1" % (i - 5000), "Inversor novo %d    { x }" % i, pai)


# ── a prontidão que expira (Important 2) ────────────────────────────────────────────────────────────────────────────────
def test_prontidao_expira_pela_idade(monkeypatch):
    base = _muitos(40)
    _catalogo_de(base)
    _ligado()
    _conferida(em=time.time() - AC.PARIDADE_VALE_S - 60)              # a última noite boa ficou para trás
    assert not AC.leitor_pronto() and AC.paridade_recente() is None and not AC.estado()["leitor_pronto"]
    _conferida()
    assert AC.leitor_pronto()
    # fora da prontidão, o botão volta ao caminho do PC (o RPC com a sessão da pessoa)
    _conferida(em=time.time() - AC.PARIDADE_VALE_S - 60)
    baixou = []
    monkeypatch.setattr(api, "get_assets", lambda: baixou.append(1) or AC.montar_registros(AL.para_registro(base)))
    api.load_assets_cached(True)
    assert baixou == [1]
    # e sem a paridade recente os novos não entram (só voltam com uma noite boa)
    assert "não está conferida" in AL.ler_novos(ler=RestFalso(base + [_novo(5000)]))["erro"]


def test_a_falha_dos_novos_derruba_e_a_leitura_boa_seguinte_devolve(tmp_path, monkeypatch):
    pasta = str(tmp_path / "oscreator")
    AC.reiniciar(pasta=pasta)
    base = _muitos(120)
    _catalogo_de(base)
    _ligado()
    _conferida()
    assert AC.leitor_pronto()
    # a página fora de ordem (o REST ignorou o sort): nada entra, e a prontidão cai
    rel = AL.ler_novos(ler=RestFalso(base + [_novo(5000)], ignora_sort=True))
    assert rel["acrescentados"] == 0 and "maior id para o menor" in rel["erro"]
    assert not AC.leitor_pronto() and "os novos" in AC.estado()["rest"]["falha"]
    # o reinício não esquece que o REST está falhando (o ativos_estado.json)
    AC.reiniciar(pasta=pasta)
    _ligado()
    assert not AC.leitor_pronto() and AC.paridade_recente() is not None
    # fora da prontidão, o botão vai ao RPC
    baixou = []
    monkeypatch.setattr(api, "get_assets", lambda: baixou.append(1) or AC.montar_registros(AL.para_registro(base)))
    api.load_assets_cached(True)
    assert baixou == [1]
    # a leitura boa seguinte (a dos novos de :08 ou :38) devolve
    rel = AL.ler_novos(ler=RestFalso(base + [_novo(5000)]))
    assert rel["acrescentados"] == 1 and not rel["erro"] and AC.leitor_pronto()
    # a exceção do cliente também derruba (depois das duas esperas da conexão que caiu)
    def caiu(path):
        raise requests.ConnectionError("a rede caiu")
    assert "ConnectionError" in AL.ler_novos(ler=caiu)["erro"] and not AC.leitor_pronto()
    assert AL.ler_novos(ler=RestFalso(base + [_novo(5000)]))["erro"] == "" and AC.leitor_pronto()
    # os novos demais NÃO são falha: o REST respondeu, e eles ficam para a noite (o limite é 400)
    demais = [_novo(6000 + k) for k in range(450)]
    rel = AL.ler_novos(ler=RestFalso(base + [_novo(5000)] + demais))
    assert rel["muitos"] == 450 and not rel["erro"] and "mais de 400" in rel["resultado"] and AC.leitor_pronto()


def test_a_leitura_da_noite_que_falha_derruba(app, banco):
    _catalogo_de(_muitos(250))
    _ligado()
    _conferida()
    rel = AL.ler_completo(app, ler=RestFalso(_muitos(250), curta_em=100))
    assert "não veio inteira" in rel["resultado"] and not AC.leitor_pronto()
    assert "a leitura da noite" in AC.estado()["rest"]["falha"]
    AL.ler_completo(app, ler=RestFalso(_muitos(250)))                  # a noite seguinte, inteira e conferida
    assert AC.leitor_pronto() and AC.paridade_rest()["vale"]


# ── a 1ª conferência estrita (Important 3) ──────────────────────────────────────────────────────────────────────────────
def test_primeira_conferencia_estrita_nos_dois_sentidos(app, banco):
    itens = _muitos(201)                                                # a usina e 199 inversores: 200 no catálogo
    _catalogo_de(itens)
    # o REST sem 3 dos 200 (98,5%): na 1ª conferência não vale, e o motivo diz quais faltam
    sem3 = [i for i in itens if i["id"] not in (1000, 1001, 1002)]
    rel = AL.ler_completo(app, ler=RestFalso(sem3))
    p = AC.paridade_rest()
    assert not p["vale"] and p["primeira"] and "1ª conferência" in p["motivo"]
    assert "CAL-GAM100-INVR0.0, CAL-GAM100-INVR0.1, CAL-GAM100-INVR0.2" in p["motivo"]
    assert (p["cob_ref"], p["cob_rest"]) == (98.5, 100.0) and banco.syncs == 0 and "segue pelo RPC" in rel["resultado"]
    assert AC.estado()["paridade_rest"]["cob_ref"] == 98.5                 # e as coberturas aparecem no estado
    # o REST com 3 códigos que o catálogo não tem (98,5% dos dele no catálogo): também não, com os exemplos
    extras = itens + [_it(7000 + k, "CAL-GAM100-EXTR%d" % k, "Extra %d" % k, 10) for k in range(3)]
    AL.ler_completo(app, ler=RestFalso(extras))
    p = AC.paridade_rest()
    assert not p["vale"] and "CAL-GAM100-EXTR0" in p["motivo"] and p["cob_rest"] == 98.52
    # sem 1 dos 200 (99,5%): vale
    sem1 = [i for i in itens if i["id"] != 1000]
    AL.ler_completo(app, ler=RestFalso(sem1))
    p = AC.paridade_rest()
    assert p["vale"] and p["primeira"] and p["cob_ref"] == 99.5 and p["cob_rest"] == 100.0
    # depois de valer, a leitura que encolhe passa daqui e quem decide é o catálogo (a recusa até duas leituras confirmarem)
    rel = AL.ler_completo(app, ler=RestFalso(_muitos(150)))
    p = AC.paridade_rest()
    assert p["vale"] and not p["primeira"] and p["cob_ref"] < 80 and "recusou" in rel["resultado"]


# ── o que se repete e o que falha na hora (minor 5) ─────────────────────────────────────────────────────────────────────
def _http(status):
    r = requests.Response()
    r.status_code = status
    return requests.HTTPError("HTTP %d" % status, response=r)


def test_so_o_erro_de_passagem_e_repetido(dormidas):
    casos = ((_http(400), False), (_http(401), False), (_http(403), False), (_http(404), False),
             (ValueError("a resposta não é JSON"), False),
             (_http(500), True), (_http(503), True), (requests.ConnectionError("caiu"), True),
             (requests.Timeout("esgotou"), True), (fracttal.Recusado("excesso de pedidos (HTTP 429)"), True))
    for erro, repete in casos:
        chamadas = []

        def ler(path, erro=erro):
            chamadas.append(path)
            raise erro
        dormidas.clear()
        with pytest.raises(type(erro)):
            AL._pedir(ler, "items?limit=100&start=0", [0])
        assert len(chamadas) == (3 if repete else 1), erro
        assert dormidas == (list(AL.ESPERAS_RECUSA_S) if repete else []), erro


# ── a leitura inteira ordenada pelo id (minor 6) ────────────────────────────────────────────────────────────────────────
def test_leitura_inteira_ordenada_pelo_id_e_o_sort_recusado(app, banco):
    rest = RestFalso(_muitos(150))
    assert len(AL.ler_todos_rest(ler=rest)) == 150 and all("sort=id:asc" in p for p in rest.paths)

    def recusa_o_sort(path):
        raise _http(400)
    with pytest.raises(AL.LeituraIncompleta, match="sort=id:asc, HTTP 400"):
        AL.ler_todos_rest(ler=recusa_o_sort)
    _catalogo_de(_muitos(150))
    _ligado()
    _conferida()
    rel = AL.ler_completo(app, ler=recusa_o_sort)
    assert "recusou a leitura ordenada" in rel["resultado"] and "RPC" in rel["resultado"] and not AC.leitor_pronto()


# ── a foto: o que o catálogo não tem, e a descrição sem o endereço da usina (minor 7, Ruling AK) ─────────────────────────
def test_fora_do_catalogo_pela_diferenca_de_ids(app, banco):
    base = _muitos(60)
    _catalogo_de(base)
    _conferida()
    # o REST dá o caminho de um item novo como "// / " (sem trecho): o catálogo não o tem, mas ele está no Fracttal
    sem_trecho = _it(9000, "CAL-GAM100-SEMTRECHO", "Sem trecho", 10, parent_description="// / ")
    rel = AL.ler_completo(app, ler=RestFalso(base + [sem_trecho]))
    assert rel["foto"]["gravou"] and "CAL-GAM100-SEMTRECHO" not in AC.atual().por_codigo
    por_id = {int(l["fracttal_item_id"]): l for l in banco.linhas(eq.LIVRO_FOTO, eq.ABA_FOTO)}
    assert 9000 in por_id and por_id[9000]["fora_do_fracttal_desde"] is None and 1 in por_id   # e a raiz


def test_a_foto_grava_a_descricao_sem_o_endereco_da_usina(app, banco):
    AC.trocar(AC.montar_registros(_rpc()), "rpc", lido_em=time.time() - 7200)
    AL.ler_completo(app, ler=RestFalso(ARVORE))
    linhas = banco.linhas(eq.LIVRO_FOTO, eq.ABA_FOTO)
    caudas = {10: "Zona Rural km 4", 11: "Zona Rural km 9"}             # o endereço de cada usina (de mentira)
    pai = {int(l["fracttal_item_id"]): int(l["pai_item_id"]) if l["pai_item_id"] else None for l in linhas}

    def usina_de(i):
        while i is not None and pai.get(i) is not None and pai.get(pai[i]) is not None:
            i = pai[i]
        return i
    for l in linhas:                                                    # nenhuma descrição leva o endereço da usina dela
        cauda = caudas.get(usina_de(int(l["fracttal_item_id"])))
        assert not cauda or cauda not in (l["descricao"] or ""), l
    por = {int(l["fracttal_item_id"]): l["descricao"] for l in linhas}
    assert (por[1], por[10], por[20], por[21], por[25]) == ("Cliente Alfa", GAMA, "Cabine 1", "Cabine 2", "Skid 1")
    assert por[11] == "Beta Solar - Usina Delta 2 - BA" and por[30] == "Inversor 1.1 Marca X"
    # a dimensão recebe a descrição limpa, e a foto segue servindo de catálogo (o mesmo cliente e usina)
    dim = {m[1]: dict(zip(eq.CAB_DIM, m)) for m in eq.membros(linhas, {}, [])}
    assert dim["CAL-GAM100-CABN1"]["descricao"] == "Cabine 1" and dim["CAL-GAM100"]["descricao"] == GAMA
    registros, _ = AC.registros_da_foto(linhas)
    assert {r["code"]: (r["cliente"], r["usina"]) for r in registros} == {
        r["code"]: (r["cliente"], r["usina"]) for r in AC.atual().lista}


# ── o núcleo concorrente dos novos, com as funções de verdade (minor 8) ─────────────────────────────────────────────────
def test_nucleo_concorrente_dos_novos(app, monkeypatch):
    base = _muitos(120)
    _catalogo_de(base)
    _conferida()
    app.config["NEXUS_PCM_FRACTTAL_TESTE"] = {"FRACTTAL_CLIENT_ID": "id-de-mentira", "FRACTTAL_CLIENT_SECRET": "s"}
    AL.ligar(app)
    rest = RestFalso(base + [_novo(5000)])
    solta, pedidos = threading.Event(), []

    def lento(path):
        pedidos.append(path)
        solta.wait(5)
        return rest(path)
    monkeypatch.setattr(fracttal, "ler", lento)
    try:
        assert AL.pedir_novos() and AL.pedir_novos() and AL.pedir_novos()          # três cliques juntos
        assert sum(1 for t in threading.enumerate() if t.name == "nexus-ativos-novos") == 1   # uma leitura só
        assert AL.ler_completo(app, ler=rest)["resultado"] == "já havia uma leitura do Fracttal em curso"
        d = AL.esperar_novos(0.2, so_em_curso=True)                                # estourou a espera
        assert d == {"terminou": False, "acrescentados": 0, "sem_pai": 0, "muitos": 0, "muitos_mais": False, "erro": ""}
    finally:
        solta.set()
    d = AL.esperar_novos(5, so_em_curso=True)
    assert d["terminou"] and d["acrescentados"] == 1 and d["erro"] == "" and len(pedidos) == 2
    # a leitura de menos de 60 s serve: pedir de novo não pede nada ao Fracttal
    assert AL.esperar_novos(5)["acrescentados"] == 1 and len(pedidos) == 2
    t0 = time.monotonic()
    assert AL.esperar_novos(5, so_em_curso=True)["terminou"] and time.monotonic() - t0 < 1   # nada em curso: na hora
    # passado o frescor, uma leitura nova (agora sem novidade: 1 pedido)
    AL._NOVOS["fim_em"] = time.time() - AL.NOVOS_FRESCO_S - 1
    d = AL.esperar_novos(5)
    assert d["terminou"] and d["acrescentados"] == 0 and len(pedidos) == 3
    assert not any(t.name == "nexus-ativos-novos" and t.is_alive() for t in threading.enumerate())


# ── o disco com a versão vigente (minor 9) ──────────────────────────────────────────────────────────────────────────────
def test_o_disco_fica_com_a_versao_vigente(tmp_path):
    pasta = str(tmp_path / "oscreator")
    AC.reiniciar(pasta=pasta)
    assert AC.trocar(_lote(10), "rpc")
    assert AC.trocar(_lote(11), "rpc")
    vigente = AC.atual()
    AC._gravar_disco()                         # a gravação da troca de antes chegando depois: grava o vigente
    AC.reiniciar(pasta=pasta)
    assert AC.atual().versao == vigente.versao and len(AC.atual().lista) == 11
    # o mesmo com os novos do dia: a versão de antes deles não volta ao disco
    novos = AC.montar_registros(AL.para_registro(_muitos(2) + [_novo(5000)]))
    assert AC.acrescentar([r for r in novos if r["id"] == 5000], "rest") == 1
    com_novo = AC.atual()
    AC._gravar_disco()
    AC.reiniciar(pasta=pasta)
    assert AC.atual().versao == com_novo.versao and 5000 in AC.atual().por_id


# ── com o leitor pronto, o catálogo vence com 26 h (minor 14) ───────────────────────────────────────────────────────────
def test_vencido_com_o_leitor_pronto_tolera_26_horas():
    AC.trocar(_lote(10), "rpc", lido_em=time.time() - 25 * 3600)
    assert api.catalogo_vencido(AC.atual())                             # sem o leitor: as 24 h de sempre
    _ligado()
    _conferida()
    assert not api.catalogo_vencido(AC.atual())                         # com ele pronto: a noite de hoje ainda vem
    AC.reiniciar()
    AC.trocar(_lote(10), "rpc", lido_em=time.time() - 27 * 3600)
    _ligado()
    _conferida()
    assert api.catalogo_vencido(AC.atual())


# ── a revisão 2 (Ruling AP) ─────────────────────────────────────────────────────────────────────────────────────────────
def test_o_erro_da_primeira_pagina_diz_o_que_houve():
    """Ruling AP (3): só o 400 e o 422 da 1ª página falam do `sort`; o 401 e o 403 são a credencial da empresa recusada; o
    resto diz o HTTP. Antes, todo 4xx culpava o `sort`, e quem lia o estado ia atrás da coisa errada."""
    casos = ((400, "sort=id:asc, HTTP 400", "credencial"), (422, "sort=id:asc, HTTP 422", "credencial"),
             (401, "credencial da empresa (HTTP 401)", "sort"), (403, "credencial da empresa (HTTP 403)", "sort"),
             (404, "HTTP 404 na 1ª página", "sort"), (409, "HTTP 409 na 1ª página", "sort"))
    for status, diz, nao_diz in casos:
        def ler(path, status=status):
            raise _http(status)
        with pytest.raises(AL.LeituraIncompleta) as e:
            AL.ler_todos_rest(ler=ler)
        motivo = str(e.value)
        assert diz in motivo and nao_diz not in motivo and motivo.endswith("o catálogo segue pelo RPC"), (status, motivo)


def test_a_gravacao_pendente_escreve_o_catalogo_do_momento(tmp_path, monkeypatch):
    """Ruling AP (4): a gravação em disco escreve o catálogo VIGENTE quando a trava do disco chega, e não o objeto que a pediu.
    O `acrescentar` sem novos e a troca pela mesma lista põem no lugar outro objeto da MESMA versão; com o `cat is _ATUAL`, a
    gravação pendente era pulada e o disco ficava uma versão atrás. Ela só pula se o disco já tem o mesmo estado."""
    import ativos_disco
    pasta = str(tmp_path / "oscreator")
    AC.reiniciar(pasta=pasta)
    assert AC.trocar(_lote(10), "rpc")
    escritas = []
    real = ativos_disco._trocar_de_uma_vez
    monkeypatch.setattr(ativos_disco, "_trocar_de_uma_vez", lambda d, e: escritas.append(d) or real(d, e))

    def esperar(cond):
        fim = time.monotonic() + 5
        while not cond():
            assert time.monotonic() < fim
            time.sleep(0.01)
    # 1) a troca instala a versão nova e a gravação dela fica esperando a trava do disco; enquanto isso, os novos do dia sem
    #    novidade trocam o objeto (a mesma versão, o `novos_em` andou)
    with ativos_disco.TRAVA:
        a = threading.Thread(target=AC.trocar, args=(_lote(11), "rpc"))
        a.start()
        esperar(lambda: len(AC.atual().lista) == 11)
        quando = time.time()
        assert AC.acrescentar([], "rest", lido_em=quando) == 0
    a.join(5)
    assert len(escritas) == 1
    AC.reiniciar(pasta=pasta)
    assert len(AC.atual().lista) == 11 and AC.atual().novos_em == quando
    # 2) duas gravações pendentes, terminando em qualquer ordem: a 1ª que pega a trava grava o vigente, a 2ª vê o disco igual
    #    e pula
    escritas.clear()
    novo = [r for r in AC.montar_registros(AL.para_registro(_muitos(2) + [_novo(5000)])) if r["id"] == 5000]
    with ativos_disco.TRAVA:
        b = threading.Thread(target=AC.trocar, args=(_lote(12), "rpc"))
        b.start()
        esperar(lambda: len(AC.atual().lista) == 12)
        c = threading.Thread(target=AC.acrescentar, args=(novo, "rest"))
        c.start()
        esperar(lambda: 5000 in AC.atual().por_id)
    b.join(5)
    c.join(5)
    vigente = AC.atual()
    assert len(escritas) == 1
    AC.reiniciar(pasta=pasta)
    assert AC.atual().versao == vigente.versao and 5000 in AC.atual().por_id and len(AC.atual().lista) == 13
    # 3) nada mudou desde a última gravação: não escreve de novo
    escritas.clear()
    AC._gravar_disco()
    assert escritas == []
