"""A curadoria do que o campo contou fora do catálogo (26/10/2026, Levi: "Aprovar a peça fora do catálogo cadastra no
Fracttal"). Desenho: docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md (seção 4.5). O técnico conta, fotografa
e descreve o que não está no catálogo (e escolhe o específico do genérico com saldo); o PCM decide: cadastrar a peça no
Fracttal (`SP-<sigla>-NNN`), "é a peça X", confirmar o genérico ou descartar (com o motivo, cifrado). A decisão vai ao livro do
inventário e a quantidade entra no lote pela `contado_efetivo` (as contas da Task 3). O Fracttal aqui é o `EstoqueFalso`; o
livro é o arquivo da cópia de prova; o livro das contagens é o banco falso do Campo, como nos testes do contrato. Dado de
mentira: usina, códigos e IDs inventados, sem nome de gente."""
import json
import re
from datetime import datetime
from pathlib import Path

import pytest
from estoque_falso import EstoqueFalso
from test_campo_visao import BRT, _aba, banco  # noqa: F401  (banco é fixture)
from test_pcm_almoxarifado import _semear
from test_pcm_publicar import _no_setor, _pessoa

from nexus.campo import visao
from nexus.dados import almoxarifado as A
from nexus.dados import fato_inventario as F
from nexus.pcm.inventario import contas as C
from nexus.pcm.inventario import curadoria as CU
from nexus.pcm.inventario import estoque as E
from nexus.pcm.inventario.erros import Conflito
from test_pcm_inventario_estoque import _jwt, _result, api_do_clone, com_o_fracttal  # noqa: F401  (api_do_clone é fixture)

ALMOX = "10"
LIGADA = "de-para do Fracttal"
PESSOA = {"email": "pessoa.teste@exemplo.com", "nome": "Pessoa Teste"}
RAIZ = Path(__file__).resolve().parent.parent
USINA = "Thopen - Altair 1 - SP"                # a de-para do `banco` liga a Altair (usina 1)


def _linha(id_linha, tipo="fora_do_catalogo", contado="2", contagem="C-1", almox=ALMOX, **mais):
    """Uma linha do livro das contagens do jeito que a API a devolve: as 19 colunas."""
    l = dict.fromkeys(A.COLUNAS_CONTAGENS, "")
    l.update({"ID da contagem": contagem, "Enviada em": "2026-10-25T11:00:00Z", "Contada em": "2026-10-25T10:00:00Z",
              "ID do almoxarifado": almox, "Usina": USINA, "Tipo": tipo, "Contado": contado, "ID da linha": id_linha})
    l.update(mais)
    return l


def _contagem(*linhas):
    return list(linhas)


CABO = _linha("L-2", Descrição="Cabo azul 6 mm", Foto="foto-abc", contado="2")
CONECTOR = _linha("L-3", Descrição="Conector estanque", contado="4")
GENERICO = _linha("L-4", tipo="identificar", contado="4", **{"ID do item": "4", "Código": "SP-4",
                                                              "Identificado como": "2"})
EM_BRANCO = _linha("L-5", contado="", Descrição="Algo que ninguém contou")
PECA_DA_LISTA = _linha("L-1", tipo="item", contado="3", **{"ID do item": "1", "Código": "SP-1"})


@pytest.fixture
def cur(app, banco, tmp_path, monkeypatch):  # noqa: F811
    """O Nexus com os livros do App do almoxarifado (a lista de peças SP-1... e os almoxarifados 10 e 20), o livro das
    contagens com uma contagem do almoxarifado 10, o livro do inventário num arquivo e a pasta de dados de mentira."""
    monkeypatch.setattr(visao, "_agora", lambda: datetime(2026, 10, 25, 10, 0, tzinfo=BRT))
    _semear(banco)
    _aba(banco, A.LIVRO_CONTAGENS, A.ABA_CONTAGENS, _contagem(PECA_DA_LISTA, CABO, CONECTOR, GENERICO, EM_BRANCO))
    app.config.update(NEXUS_ALMOX_INVENTARIO_ARQUIVO=str(tmp_path / "inventario.json"), TESTING=True,
                      NEXUS_DADOS=str(tmp_path / "dados"))
    visao.limpar()
    F.limpar()
    return app


def _falso(**kw):
    """O Fracttal de mentira com os códigos que já existem na sigla CAB (e uma peça de outra sigla)."""
    return EstoqueFalso({ALMOX: {"5": {"saldo": 1, "codigo": "SP-CAB-001"}, "6": {"saldo": 1, "codigo": "SP-CAB-012"},
                                 "7": {"saldo": 1, "codigo": "SP-PEL-020"}}}, **kw)


def _livro(cfg, aba):
    return F.ler(cfg, forcar=True)[aba]


def _cadastrar(cfg, falso, linha="L-2", **mais):
    return CU.decidir(cfg, "C-1", linha, "cadastrar", sigla="CAB", nome="Cabo azul 6 mm", unidade="METRO", estoque=falso,
                      pessoa=PESSOA, **mais)


# ── o código novo ────────────────────────────────────────────────────────────────────────────────────────────────────

def test_proximo_codigo():
    assert CU.proximo_codigo(["SP-CAB-001", "SP-CAB-012"], "CAB") == "SP-CAB-013"
    assert CU.proximo_codigo([], "CAB") == "SP-CAB-001"
    assert CU.proximo_codigo(["SP-PEL-020", "SP-CAB-002"], "CAB") == "SP-CAB-003"      # só os da sigla
    assert CU.proximo_codigo(["SP-CAB-005-AV"], "CAB") == "SP-CAB-006"                   # o -AV também gasta o número
    assert CU.proximo_codigo(["sp-cab-020"], "cab") == "SP-CAB-021"                      # sem caixa
    assert CU.proximo_codigo(["SP-CABO-004", "SP-CAB-A", "XSP-CAB-009"], "CAB") == "SP-CAB-001"   # parecido não é da sigla
    assert CU.proximo_codigo(["SP-CAB-999"], "CAB") == "SP-CAB-1000"
    assert CU.proximo_codigo(["SP-CAB-001", "SP-CAB-012"], "CAB") == "SP-CAB-013"        # o próximo, não o buraco do 002


def test_as_siglas_e_a_do_teste_so_no_almoxarifado_de_teste(app):
    assert CU.SIGLAS == ("PEL", "PME", "CAB", "SEN", "CTR", "COM", "INS", "ARM", "EAX", "HSE", "CSM", "GER")
    cfg = {"NEXUS_ALMOX_TESTE_IDS": "134082"}
    assert "TST" not in CU.siglas(cfg, "10") and CU.siglas(cfg, "10") == CU.SIGLAS
    assert CU.siglas(cfg, "134082") == CU.SIGLAS + ("TST",)
    assert CU.siglas({}, "134082") == CU.SIGLAS                                         # sem a chave, nenhum é de teste


# ── as pendências ────────────────────────────────────────────────────────────────────────────────────────────────────

def test_pendencias_sao_o_fora_do_catalogo_e_o_generico(cur):
    p = {x["chave_linha"]: x for x in CU.pendencias(cur.config)}
    assert set(p) == {"L-2", "L-3", "L-4"}                  # o item da lista e o achado em branco não são pendência
    assert p["L-2"]["tipo"] == "fora_do_catalogo" and p["L-2"]["descricao"] == "Cabo azul 6 mm" and p["L-2"]["contado"] == 2
    assert p["L-2"]["contagem_id"] == "C-1" and p["L-2"]["id_almox"] == ALMOX and p["L-2"]["usina"] == USINA
    assert p["L-2"]["foto"] == "foto-abc" and p["L-2"]["tem_foto"] is False and p["L-3"]["foto"] == ""
    assert p["L-2"]["decisao"] is None
    g = p["L-4"]
    assert g["tipo"] == "identificar" and g["codigo"] == "SP-4" and g["identificado_como"] == "2"
    assert g["identificado_codigo"] == "SP-2" and g["identificado_nome"] == "Cabo 6 mm"      # do catálogo do App


def test_pendencias_so_das_contagens_nao_gravadas(cur):
    """A contagem que já foi aprovada ou gravada, a recusada (recontagem pedida) e a que a mais nova do almoxarifado
    substituiu não pedem decisão: decidir não mudaria o que já foi (ou nunca será) gravado."""
    velha = _linha("V-1", contagem="C-0", **{"Contada em": "2026-10-24T10:00:00Z", "Enviada em": "2026-10-24T11:00:00Z"})
    gravada = _linha("G-1", contagem="C-G", almox="20")
    recusada = _linha("R-1", contagem="C-R", almox="30")
    _aba(cur.extensions["nexus_dados_sessao"], A.LIVRO_CONTAGENS, A.ABA_CONTAGENS,
         [PECA_DA_LISTA, CABO, velha, gravada, recusada])
    visao.limpar()
    F.acrescentar(cur.config, F.ABA_EVENTO, [
        {"tipo": "peca_gravada", "contagem_id": "C-G", "id_almoxarifado": "20", "id_item": "1", "para_qtd": 1},
        {"tipo": "recontagem_pedida", "contagem_id": "C-R", "id_almoxarifado": "30"}])
    assert {(x["contagem_id"], x["chave_linha"]) for x in CU.pendencias(cur.config)} == {("C-1", "L-2")}
    # a gravação que só começou (a contagem aprovada) também fecha as decisões
    F.acrescentar(cur.config, F.ABA_EVENTO, [{"tipo": "aprovada", "contagem_id": "C-1", "id_almoxarifado": ALMOX}])
    assert CU.pendencias(cur.config) == []


def test_a_contagem_que_nao_se_aprova_nao_tira_a_boa_da_curadoria(cur):
    """A curadoria usa a regra da lista das contagens (`leitura.ler`, a revisão final de 27/10/2026): a mais nova do
    almoxarifado que não se aprova (do futuro pelo relógio do celular, ou com o contrato do App violado) não substitui as
    boas. Antes a curadoria tinha a conta dela, e a contagem do futuro sumia com as pendências da boa, que a lista ainda
    mostrava para aprovar."""
    futura = _linha("F-1", contagem="C-9", **{"Contada em": "2026-10-26T10:00:00Z", "Enviada em": "2026-10-26T11:00:00Z"})
    sem_linha = _linha("", contagem="C-8", **{"Contada em": "2026-10-25T12:00:00Z", "Enviada em": "2026-10-25T12:30:00Z"})
    _aba(cur.extensions["nexus_dados_sessao"], A.LIVRO_CONTAGENS, A.ABA_CONTAGENS,
         [PECA_DA_LISTA, CABO, CONECTOR, GENERICO, futura, sem_linha])
    visao.limpar()
    p = {(x["contagem_id"], x["chave_linha"]) for x in CU.pendencias(cur.config)}
    assert {("C-1", "L-2"), ("C-1", "L-3"), ("C-1", "L-4")} <= p
    CU.decidir(cur.config, "C-1", "L-3", "descartar", motivo="não é peça", pessoa=PESSOA)     # e ainda se decide


def test_pendencia_decidida_mostra_a_decisao(cur):
    CU.decidir(cur.config, "C-1", "L-3", "descartar", motivo="foto não mostra a peça", pessoa=PESSOA)
    p = {x["chave_linha"]: x for x in CU.pendencias(cur.config)}
    assert p["L-3"]["decisao"]["decisao"] == "descartar" and p["L-2"]["decisao"] is None


def test_pendencia_com_foto_guardada_sabe_onde_ela_esta(cur):
    from nexus.cadastro.ligacoes import pasta_dados
    destino = pasta_dados(cur.config) / "almox_inventario" / "fotos"
    destino.mkdir(parents=True)
    (destino / f"{CU.nome_da_foto('foto-abc')}.jpg").write_bytes(b"\xff\xd8\xff jpeg de mentira")
    p = {x["chave_linha"]: x for x in CU.pendencias(cur.config)}
    assert p["L-2"]["tem_foto"] is True and p["L-2"]["foto_id"] == CU.nome_da_foto("foto-abc")
    assert CU.foto(cur.config, p["L-2"]["foto_id"]) == b"\xff\xd8\xff jpeg de mentira"
    (destino.parent / "segredo.jpg").write_bytes(b"fora da pasta das fotos")
    for fora in ("../segredo", r"..\segredo", "../../etc/passwd", "naoexiste", "", None, "abc"):
        assert CU.foto(cur.config, fora) is None, fora          # o nome é o hash de 24 hex: nada de caminho


# ── cadastrar: cria a peça no Fracttal e registra ────────────────────────────────────────────────────────────────────

def test_cadastrar_cria_e_registra(cur):
    """O próximo código livre da sigla (o catálogo tem 001 e 012: o 013), nome e unidade ao Fracttal, e a decisão no livro com
    o ID e o código criados. A pessoa vai pelo código (HMAC); a usina, pela de-para; a linha do livro e o evento da auditoria."""
    falso = _falso()
    r = _cadastrar(cur.config, falso)
    assert r["decisao"] == "cadastrar" and r["codigo"] == "SP-CAB-013" and r["id_item"] and r["criada"] is True
    assert falso.chamadas == ["codigos", "criar_peca"]
    assert falso.codigos("CAB") == ["SP-CAB-001", "SP-CAB-012", "SP-CAB-013"]
    assert falso._catalogo[r["id_item"]] == {"codigo": "SP-CAB-013", "nome": "Cabo azul 6 mm", "unidade": "METRO"}
    d = _livro(cur.config, F.ABA_CURADORIA)
    assert len(d) == 1
    assert (d[0]["contagem_id"], d[0]["chave_linha"], d[0]["decisao"]) == ("C-1", "L-2", "cadastrar")
    assert (d[0]["id_item"], d[0]["codigo_criado"]) == (r["id_item"], "SP-CAB-013")
    assert d[0]["id_almoxarifado"] == ALMOX and d[0]["usina_id"] == 1 and d[0]["usina_ligada_por"] == LIGADA
    assert re.fullmatch(r"[0-9a-f]{24}", d[0]["pessoa_hmac"]) and PESSOA["email"] not in json.dumps(d)
    ev = [e for e in _livro(cur.config, F.ABA_EVENTO) if e["tipo"] == "curadoria"]
    assert len(ev) == 1 and ev[0]["contagem_id"] == "C-1" and ev[0]["id_item"] == r["id_item"] and ev[0]["codigo"] == "SP-CAB-013"
    assert ev[0]["usina_id"] == 1


def test_a_peca_cadastrada_entra_no_lote_com_as_achadas(cur):
    """A peça nova não está ligada ao almoxarifado: o contado dela são as achadas, e a gravação a liga e ajusta."""
    r = _cadastrar(cur.config, _falso())
    contagem = visao._livro(A.LIVRO_CONTAGENS, A.ABA_CONTAGENS)
    assert C.contado_efetivo(contagem, CU.decisoes(cur.config, "C-1"))[r["id_item"]] == 2.0
    lote = {i["id_item"]: i for i in C.itens_do_lote(contagem, {}, CU.decisoes(cur.config, "C-1"), {})}
    nova = lote[r["id_item"]]
    assert (nova["codigo"], nova["ligada"], nova["sistema"], nova["contado"], nova["situacao"]) == (
        "SP-CAB-013", False, 0.0, 2.0, "para_cima")


def test_cadastrar_com_resposta_perdida_nao_duplica(cur):
    """O caso que o código escolhido guardado antes de criar resolve: o Fracttal criou a peça, a conexão caiu e o Nexus não
    soube. Na nova tentativa da mesma linha o código reservado já existe no Fracttal: não cria de novo, acha o ID e só
    grava a decisão."""
    falso = _falso(perder_resposta={"criar_peca"})
    with pytest.raises(ConnectionError):
        _cadastrar(cur.config, falso)
    assert _livro(cur.config, F.ABA_CURADORIA) == []                       # a decisão não saiu: o Nexus não sabia o ID
    assert falso.codigos("CAB")[-1] == "SP-CAB-013"                        # mas a peça foi criada
    r = _cadastrar(cur.config, falso)
    assert falso.chamadas.count("criar_peca") == 1                         # nenhuma segunda peça
    assert r["codigo"] == "SP-CAB-013" and r["criada"] is False
    assert sum(1 for c in falso.codigos("CAB") if c == "SP-CAB-013") == 1
    d = _livro(cur.config, F.ABA_CURADORIA)
    assert [(x["decisao"], x["codigo_criado"]) for x in d] == [("cadastrar", "SP-CAB-013")]
    assert d[0]["id_item"] == r["id_item"] == [i for i, v in falso._catalogo.items() if v["codigo"] == "SP-CAB-013"][0]


def test_cadastrar_que_nao_chegou_ao_fracttal_reaproveita_o_codigo(cur):
    """O pedido que cai antes de o Fracttal criar (o limite de 429): o código reservado segue sendo o da linha, e a nova
    tentativa cria a peça com ele (e não com o 014: o 013 ficaria vazio para sempre)."""
    falso = _falso(limite_em=2)                                           # 1: codigos, 2: criar_peca (cai sem executar)
    with pytest.raises(E.Limite):
        _cadastrar(cur.config, falso)
    assert "SP-CAB-013" not in falso.codigos("CAB")
    r = _cadastrar(cur.config, falso)
    assert r["codigo"] == "SP-CAB-013" and r["criada"] is True
    assert falso.codigos("CAB")[-1] == "SP-CAB-013"


def test_o_cadastro_que_o_fracttal_recusa_solta_a_reserva(cur):
    """O Fracttal recusou o `criar_peca` (`Recusado`, o `success: false`: nada foi criado). A reserva do código sai, e a nova
    tentativa com os dados corrigidos (outro nome) não fica presa no "repita com os dados da reserva" (estacionado da revisão
    das Tasks 8 e 9, corrigido na revisão final de 27/10/2026)."""
    falso = _falso()
    criar = falso.criar_peca

    def recusa(codigo, nome, unidade="UNIDADE"):
        raise E.Recusado("INVALID_NAME", "inventories.item_insert")
    falso.criar_peca = recusa
    with pytest.raises(E.Recusado):
        CU.decidir(cur.config, "C-1", "L-2", "cadastrar", sigla="CAB", nome="Cabo azul 6 mm ###", unidade="METRO",
                   estoque=falso, pessoa=PESSOA)
    assert json.loads(CU._arquivo_reserva(cur.config, "C-1").read_text("utf-8")) == {}
    falso.criar_peca = criar
    r = _cadastrar(cur.config, falso)                      # o nome corrigido
    assert r["codigo"] == "SP-CAB-013" and r["criada"] is True
    assert [x["codigo_criado"] for x in _livro(cur.config, F.ABA_CURADORIA)] == ["SP-CAB-013"]


@pytest.mark.parametrize("resposta, solta", [
    ({"success": False, "message": "INVALID_NAME"}, True),   # o "não" com todas as letras: nada foi criado
    ({"success": True, "data": {}}, False),                    # sem o id: o Fracttal pode ter criado e não disse qual
    (None, False),                                             # sem corpo: idem
])
def test_so_a_recusa_do_fracttal_solta_a_reserva(cur, resposta, solta):
    """Pelo adaptador DE VERDADE (só o RPC é de mentira): a reserva do código sai só no `Recusado` (o `success: false`). O
    `ErroFracttal` sem o id ou sem corpo pode ter vindo depois de o Fracttal criar a peça: a reserva fica, e a nova tentativa a
    acha pelo código (`peca`, com o nome conferido) em vez de criar uma 2ª peça com outro código no catálogo do cliente (a
    re-revisão de 27/10/2026: a curadoria soltava em qualquer `ErroFracttal`)."""
    from test_pcm_inventario_estoque import CRIAR, PECAS, UNIDADES, Fracttal, em_paginas, estoque, ok
    catalogo = [{"id": 5, "code": "SP-CAB-001", "field_1": "Cabo 4 mm"}, {"id": 6, "code": "SP-CAB-012", "field_1": "Cabo 10 mm"}]
    fr = Fracttal({PECAS: em_paginas(catalogo), UNIDADES: ok([{"id": 362333, "description": "METRO"}]), CRIAR: resposta})
    with pytest.raises(E.ErroFracttal) as ex:
        _cadastrar(cur.config, estoque(fr))
    assert isinstance(ex.value, E.Recusado) is solta
    reservas = json.loads(CU._arquivo_reserva(cur.config, "C-1").read_text("utf-8"))
    assert ("L-2" in reservas) is not solta and _livro(cur.config, F.ABA_CURADORIA) == []
    if solta:
        return
    assert reservas["L-2"]["codigo"] == "SP-CAB-013"
    # a peça tinha sido criada: a nova tentativa a acha pelo código reservado, confere o nome e não cria outra
    fr.respostas[PECAS] = em_paginas(catalogo + [{"id": 77, "code": "SP-CAB-013", "field_1": "Cabo azul 6 mm"}])
    r = _cadastrar(cur.config, estoque(fr))
    assert (r["codigo"], r["id_item"], r["criada"]) == ("SP-CAB-013", "77", False) and fr.metodos.count(CRIAR) == 1


def test_a_decisao_depois_do_controle_da_gravacao_e_recusada(cur):
    """O controle da gravação existe (o `iniciar` o cria ANTES de registrar a aprovação no livro, e o registro falhou no meio):
    os eventos ainda dizem "nova", mas o lote já foi congelado. Decidir ali seria gravar o que a gravação ignora: `Conflito`
    (409), nada no livro, e o cadastro nem chega ao Fracttal (a re-revisão de 27/10/2026)."""
    from nexus.pcm.inventario import gravacao as G
    G._gravar_json(G._caminho(cur.config, "C-1"), {"contagem_id": "C-1", "id_almox": ALMOX, "estado": "parada",
                                                     "lotes": [], "itens": {}})
    falso = _falso()
    with pytest.raises(Conflito, match="já foi para a gravação"):
        _cadastrar(cur.config, falso)
    with pytest.raises(Conflito, match="já foi para a gravação"):
        CU.decidir(cur.config, "C-1", "L-3", "descartar", motivo="não é peça", pessoa=PESSOA)
    assert falso.chamadas == [] and _livro(cur.config, F.ABA_CURADORIA) == []
    assert not CU._arquivo_reserva(cur.config, "C-1").exists()


def test_a_decisao_que_chega_com_o_controle_novo_e_recusada(cur, monkeypatch):
    """O controle nasce enquanto o cadastro pagina o catálogo e cria a peça: a conferência de logo antes de escrever (com a
    trava da contagem) o vê, e a decisão não é registrada (o código fica reservado, como na contagem gravada no meio)."""
    from nexus.pcm.inventario import gravacao as G
    falso = _falso()
    criar = falso.criar_peca

    def criar_e_a_aprovacao_chega(codigo, nome, unidade="UNIDADE"):
        G._gravar_json(G._caminho(cur.config, "C-1"), {"contagem_id": "C-1", "id_almox": ALMOX, "estado": "gravando",
                                                         "lotes": [], "itens": {}})
        return criar(codigo, nome, unidade)
    falso.criar_peca = criar_e_a_aprovacao_chega
    with pytest.raises(Conflito, match="SP-CAB-013 foi criada no Fracttal"):
        _cadastrar(cur.config, falso)
    assert _livro(cur.config, F.ABA_CURADORIA) == []


def test_a_reserva_vale_para_a_outra_linha_da_mesma_sigla(cur):
    """Dois cadastros da mesma sigla em seguida, o 1º com a resposta perdida: o 2º não escolhe o mesmo código (a peça do 1º
    pode ainda não estar na lista do Fracttal quando o 2º lê)."""
    falso = _falso(perder_resposta={"criar_peca"})
    with pytest.raises(ConnectionError):
        _cadastrar(cur.config, falso, "L-2")
    falso._catalogo.clear()                                               # a lista do Fracttal "ainda não mostra" a 013
    r2 = _cadastrar(cur.config, falso, "L-3")
    assert r2["codigo"] == "SP-CAB-014"


def test_a_reserva_nao_guarda_login_nem_nome_de_gente(cur):
    from nexus.cadastro.ligacoes import pasta_dados
    _cadastrar(cur.config, _falso())
    arquivos = list((pasta_dados(cur.config) / "almox_inventario").glob("curadoria_*.json"))
    assert len(arquivos) == 1
    texto = arquivos[0].read_text("utf-8").lower()
    assert "sp-cab-013" in texto and "jwt" not in texto and "token" not in texto and "@" not in texto
    assert PESSOA["nome"].lower() not in texto


def test_cadastrar_exige_sigla_da_lista_nome_e_o_fracttal(cur):
    falso = _falso()
    for erro in (dict(sigla="XXX"), dict(sigla="TST"), dict(sigla=""), dict(nome=" "), dict(sigla=None)):
        args = dict(sigla="CAB", nome="Cabo azul 6 mm", unidade="METRO", estoque=falso, pessoa=PESSOA)
        args.update(erro)
        with pytest.raises(ValueError):
            CU.decidir(cur.config, "C-1", "L-2", "cadastrar", **args)
    with pytest.raises(ValueError, match="Fracttal"):
        CU.decidir(cur.config, "C-1", "L-2", "cadastrar", sigla="CAB", nome="Cabo", unidade="METRO", pessoa=PESSOA)
    assert falso.chamadas == [] and _livro(cur.config, F.ABA_CURADORIA) == []


def test_a_sigla_de_teste_so_vale_no_almoxarifado_de_teste(cur):
    """O cadastro com a sigla `TST` no almoxarifado de teste (o código `SP-TST-001`). Na tela do servidor ele nem aparece (o
    teste abaixo); quem o usa é a cópia de prova, que esvazia o `NEXUS_ALMOX_TESTE_IDS` e libera a sigla só para ele."""
    cur.config["NEXUS_ALMOX_TESTE_IDS"] = ALMOX
    _id, codigo, criada = CU._cadastrar(cur.config, "C-1", "L-2", ALMOX, "TST", "Peça de teste", "UNIDADE", _falso())
    assert (codigo, criada) == ("SP-TST-001", True)


def test_o_almoxarifado_de_teste_fica_fora_da_curadoria(cur):
    """Como a lista do Inventário, a régua e a Auditoria: a contagem do almoxarifado de teste não aparece na curadoria nem se
    decide (até 27/10/2026 a curadoria lia com `com_teste=True`, e uma decisão do PCM do servidor podia cair na contagem da
    prova). Nada é gravado nem pedido ao Fracttal."""
    cur.config["NEXUS_ALMOX_TESTE_IDS"] = ALMOX
    visao.limpar()
    assert CU.pendencias(cur.config) == [] and CU.contagens_abertas(cur.config) == {}
    falso = _falso()
    with pytest.raises(ValueError, match="não está no livro das contagens"):
        CU.decidir(cur.config, "C-1", "L-3", "descartar", motivo="não é peça", pessoa=PESSOA)
    with pytest.raises(ValueError):
        _cadastrar(cur.config, falso)
    assert falso.chamadas == [] and _livro(cur.config, F.ABA_CURADORIA) == []


# ── é a peça X, confirmar, descartar ─────────────────────────────────────────────────────────────────────────────────

def test_e_a_peca_entra_no_lote(cur):
    """A contagem com a peça 1 contada em 3 e 2 achadas que são ela: o lote da 1 sai com 5 (o total SUBSTITUI o saldo, a
    Task 3). Sem a decisão, as achadas ficam na curadoria e a 1 fica só com as 3."""
    contagem = visao._livro(A.LIVRO_CONTAGENS, A.ABA_CONTAGENS)
    sistema = {"1": {"saldo": 4, "minimo": None, "maximo": None, "ligacao": "L1", "codigo": "SP-1", "unidade": ""}}
    antes = {i["id_item"]: i for i in C.itens_do_lote(contagem, sistema, CU.decisoes(cur.config, "C-1"), {})}
    assert antes["1"]["contado"] == 3.0 and any(i["situacao"] == "curadoria" for i in antes.values())
    r = CU.decidir(cur.config, "C-1", "L-2", "e_a_peca", id_item="1", pessoa=PESSOA)
    assert r["decisao"] == "e_a_peca" and r["id_item"] == "1" and r["criada"] is False
    lote = {i["id_item"]: i for i in C.itens_do_lote(contagem, sistema, CU.decisoes(cur.config, "C-1"), {})}
    assert (lote["1"]["contado"], lote["1"]["situacao"], lote["1"]["delta"]) == (5.0, "para_cima", 1.0)
    d = _livro(cur.config, F.ABA_CURADORIA)[0]
    assert (d["decisao"], d["id_item"], d["usina_id"]) == ("e_a_peca", "1", 1)


def test_e_a_peca_aceita_a_peca_recem_cadastrada_que_a_varredura_ainda_nao_viu(cur):
    r = _cadastrar(cur.config, _falso(), "L-2")
    CU.decidir(cur.config, "C-1", "L-3", "e_a_peca", id_item=r["id_item"], pessoa=PESSOA)
    contagem = visao._livro(A.LIVRO_CONTAGENS, A.ABA_CONTAGENS)
    assert C.contado_efetivo(contagem, CU.decisoes(cur.config, "C-1"))[r["id_item"]] == 6.0      # 2 + 4


def test_e_a_peca_de_id_que_nao_existe_e_recusada(cur):
    """ID chutado não vira peça: o destino vem do catálogo do App."""
    for id_item in ("9999", "", None, "abc"):
        with pytest.raises(ValueError):
            CU.decidir(cur.config, "C-1", "L-2", "e_a_peca", id_item=id_item, pessoa=PESSOA)
    assert _livro(cur.config, F.ABA_CURADORIA) == []


def test_confirmar_o_generico_tira_do_generico_e_poe_no_especifico(cur):
    """O genérico (SP-4, 4 unidades) que o técnico identificou como a peça 2: confirmado (sem dizer outra), as unidades
    saem do genérico e entram na 2."""
    r = CU.decidir(cur.config, "C-1", "L-4", "confirmar", pessoa=PESSOA)
    assert r["id_item"] == "2"
    contagem = visao._livro(A.LIVRO_CONTAGENS, A.ABA_CONTAGENS)
    efetivo = C.contado_efetivo(contagem, CU.decisoes(cur.config, "C-1"))
    assert efetivo["4"] == 0.0 and efetivo["2"] == 4.0


def test_confirmar_outro_especifico_vale_o_que_o_pcm_disse(cur):
    r = CU.decidir(cur.config, "C-1", "L-4", "confirmar", id_item="3", pessoa=PESSOA)
    assert r["id_item"] == "3"
    contagem = visao._livro(A.LIVRO_CONTAGENS, A.ABA_CONTAGENS)
    assert C.contado_efetivo(contagem, CU.decisoes(cur.config, "C-1"))["3"] == 4.0


def test_confirmar_sem_o_tecnico_ter_dito_pede_a_peca(cur):
    _aba(cur.extensions["nexus_dados_sessao"], A.LIVRO_CONTAGENS, A.ABA_CONTAGENS,
         [_linha("L-4", tipo="identificar", contado="4", **{"ID do item": "4", "Código": "SP-4"})])
    visao.limpar()
    with pytest.raises(ValueError, match="peça"):
        CU.decidir(cur.config, "C-1", "L-4", "confirmar", pessoa=PESSOA)


def test_descartar_motivo_cifrado(cur):
    """O motivo é texto livre do PCM: só cifrado (o Cofre do cadastro), nunca em coluna em claro (a API do banco é
    aberta). Sem motivo, não descarta. O descartado não entra no lote."""
    motivo = "foto não mostra a peça, parece resto de obra"
    with pytest.raises(ValueError, match="motivo"):
        CU.decidir(cur.config, "C-1", "L-3", "descartar", pessoa=PESSOA)
    with pytest.raises(ValueError, match="motivo"):
        CU.decidir(cur.config, "C-1", "L-3", "descartar", motivo="   ", pessoa=PESSOA)
    assert _livro(cur.config, F.ABA_CURADORIA) == []
    r = CU.decidir(cur.config, "C-1", "L-3", "descartar", motivo=motivo, pessoa=PESSOA)
    assert r["decisao"] == "descartar" and r["id_item"] == ""
    d = _livro(cur.config, F.ABA_CURADORIA)[0]
    assert d["dados_cifrados"] and "foto" not in str(d["dados_cifrados"]).lower()
    assert motivo not in Path(cur.config["NEXUS_ALMOX_INVENTARIO_ARQUIVO"]).read_text("utf-8")      # nada em claro no livro
    assert F.decifrar(cur.config, F.ABA_CURADORIA, d) == {"motivo": motivo}
    contagem = visao._livro(A.LIVRO_CONTAGENS, A.ABA_CONTAGENS)
    assert C.contado_efetivo(contagem, CU.decisoes(cur.config, "C-1")).get("3") is None


def test_o_motivo_vai_cifrado_tambem_nas_outras_decisoes(cur):
    CU.decidir(cur.config, "C-1", "L-2", "e_a_peca", id_item="1", motivo="é o mesmo fusível, só sem a etiqueta", pessoa=PESSOA)
    d = _livro(cur.config, F.ABA_CURADORIA)[0]
    assert F.decifrar(cur.config, F.ABA_CURADORIA, d)["motivo"].startswith("é o mesmo fusível")
    assert "fusível" not in Path(cur.config["NEXUS_ALMOX_INVENTARIO_ARQUIVO"]).read_text("utf-8")


# ── as regras do que se pode decidir ─────────────────────────────────────────────────────────────────────────────────

def test_linha_decidida_nao_se_decide_de_novo(cur):
    """Dois do PCM com a mesma tela aberta não cadastram a mesma peça duas vezes: a 2ª decisão da linha é recusada, e o
    Fracttal nem é chamado."""
    falso = _falso()
    _cadastrar(cur.config, falso)
    chamadas = list(falso.chamadas)
    with pytest.raises(F.Recusada, match="esta linha já foi decidida"):
        _cadastrar(cur.config, falso)
    with pytest.raises(Conflito):
        CU.decidir(cur.config, "C-1", "L-2", "descartar", motivo="engano", pessoa=PESSOA)
    assert falso.chamadas == chamadas and len(_livro(cur.config, F.ABA_CURADORIA)) == 1


def test_decisao_depois_da_contagem_gravada_e_recusada(cur):
    """A decisão vale para o lote só enquanto a contagem não foi gravada: depois ela não mudaria o que já foi gravado."""
    F.acrescentar(cur.config, F.ABA_EVENTO, [{"tipo": "peca_gravada", "contagem_id": "C-1", "id_almoxarifado": ALMOX,
                                              "id_item": "1", "para_qtd": 3}])
    falso = _falso()
    with pytest.raises(Conflito, match="nova contagem"):
        _cadastrar(cur.config, falso)
    with pytest.raises(Conflito, match="nova contagem"):
        CU.decidir(cur.config, "C-1", "L-2", "e_a_peca", id_item="1", pessoa=PESSOA)
    assert falso.chamadas == [] and _livro(cur.config, F.ABA_CURADORIA) == []


def test_decisao_do_tipo_errado_ou_de_linha_que_nao_e_pendencia(cur):
    """Cadastrar e "é a peça X" são do achado fora do catálogo; confirmar é do genérico. A linha da lista (`item`), a
    em branco e a que não existe não se decidem."""
    for linha, decisao, args in (("L-4", "cadastrar", dict(sigla="CAB", nome="Cabo", estoque=_falso())),
                                 ("L-4", "e_a_peca", dict(id_item="1")), ("L-4", "descartar", dict(motivo="x")),
                                 ("L-2", "confirmar", dict(id_item="1")), ("L-1", "e_a_peca", dict(id_item="2")),
                                 ("L-5", "descartar", dict(motivo="x")), ("L-99", "descartar", dict(motivo="x"))):
        with pytest.raises(ValueError):
            CU.decidir(cur.config, "C-1", linha, decisao, pessoa=PESSOA, **args)
    with pytest.raises(ValueError):
        CU.decidir(cur.config, "C-1", "L-2", "apagar", pessoa=PESSOA)
    with pytest.raises(ValueError):
        CU.decidir(cur.config, "C-9", "L-2", "descartar", motivo="x", pessoa=PESSOA)         # contagem que não existe
    assert _livro(cur.config, F.ABA_CURADORIA) == []


def test_decisoes_no_formato_das_contas(cur):
    """`decisoes(cfg, contagem)` é o `curadoria` que a `contado_efetivo` e o `itens_do_lote` pedem: por linha, a decisão, o ID
    da peça e o código criado."""
    r = _cadastrar(cur.config, _falso())
    CU.decidir(cur.config, "C-1", "L-3", "descartar", motivo="não é peça", pessoa=PESSOA)
    assert CU.decisoes(cur.config, "C-1") == {
        "L-2": {"decisao": "cadastrar", "id_item": r["id_item"], "codigo": "SP-CAB-013"},
        "L-3": {"decisao": "descartar", "id_item": "", "codigo": ""}}
    assert CU.decisoes(cur.config, "C-OUTRA") == {}


# ── as telas ─────────────────────────────────────────────────────────────────────────────────────────────────────────

URL = "/t/pcm/pecas/inventario/curadoria"
CADASTRAR = "/os/_nexus/inventario/curadoria/cadastrar"             # a ponte: cadastrar fala com o Fracttal


def _pessoa_ms(app):
    """Quem entrou pela conta Microsoft da Grid: não tem o login do Fracttal, e o portão não encerra a sessão por isso (a de quem
    entrou pelo Fracttal cai se o pedido a /os chega sem o cookie dele). É quem a ponte atende sem o `os_sessao`."""
    import time
    c = _pessoa(app)
    with c.session_transaction() as sessao:
        sessao["via"], sessao["ms_ate"] = "microsoft", time.time() + 3600
    return c


def _estoque_da_sessao(monkeypatch, falso):
    monkeypatch.setattr(E, "estoque_da_sessao", lambda app: falso)


def test_tela_lista_as_pendencias_e_lembra_do_fracttal(cur, monkeypatch):
    _no_setor(monkeypatch, "PCM")
    r = _pessoa_ms(cur).get(URL)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Curadoria" in html
    assert "Cabo azul 6 mm" in html and "Conector estanque" in html and "sem foto" in html.lower()
    assert "SP-4" in html and "SP-2" in html                          # o genérico e o que o técnico escolheu
    assert "Algo que ninguém contou" not in html                      # em branco não é pendência
    # o lembrete: a API não grava grupo, criticidade nem curva ABC
    assert "grupo" in html.lower() and "criticidade" in html.lower() and "curva abc" in html.lower()
    assert 'name="decisao"' in html and "SP-CAB-013" not in html      # o código novo só aparece depois de cadastrar
    for sigla in CU.SIGLAS:
        assert f'value="{sigla}"' in html
    assert 'value="TST"' not in html


def test_tela_mostra_a_foto_guardada(cur, monkeypatch):
    from nexus.cadastro.ligacoes import pasta_dados
    destino = pasta_dados(cur.config) / "almox_inventario" / "fotos"
    destino.mkdir(parents=True)
    foto_id = CU.nome_da_foto("foto-abc")
    (destino / f"{foto_id}.jpg").write_bytes(b"\xff\xd8\xff jpeg de mentira")
    _no_setor(monkeypatch, "PCM")
    c = _pessoa_ms(cur)
    html = c.get(URL).get_data(as_text=True)
    assert f"{URL}/foto/{foto_id}.jpg" in html
    r = c.get(f"{URL}/foto/{foto_id}.jpg")
    assert r.status_code == 200 and r.mimetype == "image/jpeg" and r.data.startswith(b"\xff\xd8\xff")
    assert c.get(f"{URL}/foto/naoexiste.jpg").status_code == 404
    assert c.get(f"{URL}/foto/..%2F..%2Fsegredo.jpg").status_code == 404


def test_foto_exige_login(cur, cliente):
    assert cliente.get(f"{URL}/foto/abc.jpg").status_code in (302, 401, 403)


def test_so_o_setor_pcm_decide(cur, monkeypatch):
    """Só administrador e setor PCM (`pode_programar`) decidem: outro setor leva 403, sem nada no livro nem no Fracttal."""
    falso = _falso()
    _estoque_da_sessao(monkeypatch, falso)
    corpo = {"contagem": "C-1", "linha": "L-3", "decisao": "descartar", "motivo": "x"}
    c = _pessoa_ms(cur)
    _no_setor(monkeypatch, "Performance")
    assert c.post(f"{URL}/decidir", data=corpo).status_code == 403
    _no_setor(monkeypatch, "Responsáveis UFV")
    assert c.post(f"{URL}/decidir", data=corpo).status_code == 403
    assert c.post(CADASTRAR, data={"contagem": "C-1", "linha": "L-2", "sigla": "CAB", "nome": "Cabo"}).status_code == 403
    assert falso.chamadas == [] and F.ler(cur.config, forcar=True)[F.ABA_CURADORIA] == []
    _no_setor(monkeypatch, "pcm")
    assert c.post(f"{URL}/decidir", data=corpo).status_code == 303
    assert len(F.ler(cur.config, forcar=True)[F.ABA_CURADORIA]) == 1


def test_pedido_de_outro_site_e_recusado(cur, monkeypatch):
    _no_setor(monkeypatch, "PCM")
    r = _pessoa_ms(cur).post(f"{URL}/decidir", data={"contagem": "C-1", "linha": "L-3", "decisao": "descartar", "motivo": "x"},
                          headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    r = _pessoa_ms(cur).post(CADASTRAR, data={"contagem": "C-1", "linha": "L-2", "sigla": "CAB", "nome": "Cabo"},
                             headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and "erro" in r.get_json()


def test_tela_cadastra_pelo_login_de_quem_decide(cur, monkeypatch):
    """Cadastrar cria a peça no Fracttal com o login de quem decide: roda na ponte (`/os/_nexus/...`), que responde JSON, e a
    página, ao recarregar, mostra o aviso e o código novo."""
    falso = _falso()
    _estoque_da_sessao(monkeypatch, falso)
    _no_setor(monkeypatch, "PCM")
    c = com_o_fracttal(cur, _pessoa_ms(cur))
    r = c.post(CADASTRAR, data={"contagem": "C-1", "linha": "L-2", "sigla": "CAB", "nome": "Cabo azul 6 mm",
                                "unidade": "METRO"})
    assert r.status_code == 200 and r.get_json()["ok"] is True and r.get_json()["volta"].endswith(URL)
    assert "SP-CAB-013" in r.get_json()["mensagem"]
    assert falso.chamadas == ["codigos", "criar_peca"]
    html = c.get(r.get_json()["volta"]).get_data(as_text=True)
    assert "SP-CAB-013" in html and "cadastrada" in html.lower()


def test_cadastrar_nao_e_rota_de_t_pcm(cur, monkeypatch):
    """O cadastro fala com o Fracttal: em /t/pcm o login dele nunca chega, e a rota recusa antes de qualquer pedido."""
    falso = _falso()
    _estoque_da_sessao(monkeypatch, falso)
    _no_setor(monkeypatch, "PCM")
    r = _pessoa_ms(cur).post(f"{URL}/decidir", data={"contagem": "C-1", "linha": "L-2", "decisao": "cadastrar",
                                                     "sigla": "CAB", "nome": "Cabo"})
    assert r.status_code == 400 and "roda pela ponte do login do Fracttal" in r.get_data(as_text=True)
    assert falso.chamadas == [] and F.ler(cur.config, forcar=True)[F.ABA_CURADORIA] == []


def test_tela_e_a_peca_pelo_codigo_ou_pelo_id(cur, monkeypatch):
    """O PCM conhece o CÓDIGO da peça, não o ID: a tela aceita os dois, e o ID que vale é o do catálogo."""
    _no_setor(monkeypatch, "PCM")
    c = _pessoa_ms(cur)
    assert c.post(f"{URL}/decidir", data={"contagem": "C-1", "linha": "L-2", "decisao": "e_a_peca", "peca": "sp-1"}
                  ).status_code == 303
    assert c.post(f"{URL}/decidir", data={"contagem": "C-1", "linha": "L-3", "decisao": "e_a_peca", "peca": "2"}
                  ).status_code == 303
    d = F.ler(cur.config, forcar=True)[F.ABA_CURADORIA]
    assert [(x["chave_linha"], x["id_item"]) for x in d] == [("L-2", "1"), ("L-3", "2")]
    r = c.post(f"{URL}/decidir", data={"contagem": "C-1", "linha": "L-4", "decisao": "confirmar", "peca": "SP-NAO-EXISTE"})
    assert r.status_code == 400 and len(F.ler(cur.config, forcar=True)[F.ABA_CURADORIA]) == 2


def test_status_de_cada_recusa(cur, monkeypatch):
    """400 o pedido sem sentido, 409 a linha já decidida ou a contagem já gravada, 401 o Fracttal sem login, 429 o limite."""
    _no_setor(monkeypatch, "PCM")
    c = _pessoa_ms(cur)
    base = {"contagem": "C-1", "linha": "L-3", "decisao": "descartar", "motivo": "x"}
    assert c.post(f"{URL}/decidir", data={**base, "motivo": ""}).status_code == 400
    assert c.post(f"{URL}/decidir", data={**base, "decisao": "apagar"}).status_code == 400
    assert c.post(f"{URL}/decidir", data=base).status_code == 303
    r = c.post(f"{URL}/decidir", data=base)
    assert r.status_code == 409 and "esta linha já foi decidida" in r.get_data(as_text=True)
    F.acrescentar(cur.config, F.ABA_EVENTO, [{"tipo": "aprovada", "contagem_id": "C-1", "id_almoxarifado": ALMOX}])
    r = c.post(f"{URL}/decidir", data={**base, "linha": "L-2"})
    assert r.status_code == 409 and "nova contagem" in r.get_data(as_text=True)


def test_cadastrar_pela_senha_de_administrador_e_recusado(cur, logado, monkeypatch):
    """Cadastrar fala com o Fracttal no nome de quem decide, e a senha de administrador não é uma pessoa; o `os_sessao` que
    estiver no navegador é o login de OUTRA pessoa (a revisão final de 27/10/2026): 409 antes de qualquer pedido. As outras
    decisões (descartar, é a peça X, confirmar) são do Nexus e valem."""
    falso = _falso()
    _estoque_da_sessao(monkeypatch, falso)
    com_o_fracttal(cur, logado, "outra.pessoa@exemplo.test")
    r = logado.post(CADASTRAR, data={"contagem": "C-1", "linha": "L-2", "sigla": "CAB", "nome": "Cabo"})
    assert r.status_code == 409 and "senha de administrador" in r.get_json()["erro"] and falso.chamadas == []
    assert F.ler(cur.config, forcar=True)[F.ABA_CURADORIA] == []
    assert logado.post(f"{URL}/decidir", data={"contagem": "C-1", "linha": "L-3", "decisao": "descartar",
                                               "motivo": "x"}).status_code == 303


def test_cadastrar_com_a_conta_do_fracttal_de_outra_pessoa_e_recusado(cur, monkeypatch):
    """O cookie do OS Creator de outra conta no mesmo navegador: a peça nasceria no login de uma pessoa e a decisão no nome de
    outra. 409 com o link para entrar de novo, e nada vai ao Fracttal nem ao livro."""
    from nexus.pcm.inventario import ponte_os
    falso = _falso()
    _estoque_da_sessao(monkeypatch, falso)
    _no_setor(monkeypatch, "PCM")
    c = com_o_fracttal(cur, _pessoa_ms(cur), "outra.pessoa@exemplo.test")
    r = c.post(CADASTRAR, data={"contagem": "C-1", "linha": "L-2", "sigla": "CAB", "nome": "Cabo azul 6 mm"})
    assert r.status_code == 409 and r.get_json()["erro"] == ponte_os.OUTRA_CONTA and "/os/login?next=" in r.get_json()["login"]
    assert falso.chamadas == [] and F.ler(cur.config, forcar=True)[F.ABA_CURADORIA] == []


def test_limite_do_fracttal_na_curadoria_e_429(cur, monkeypatch):
    _estoque_da_sessao(monkeypatch, _falso(limite_em=1))
    _no_setor(monkeypatch, "PCM")
    r = com_o_fracttal(cur, _pessoa_ms(cur)).post(CADASTRAR, data={"contagem": "C-1", "linha": "L-2", "sigla": "CAB", "nome": "Cabo azul 6 mm"})
    assert r.status_code == 429 and "tente de novo" in r.get_json()["erro"].lower()


def test_rede_que_cai_no_cadastro_diz_que_o_codigo_ficou_reservado(cur, monkeypatch):
    """A resposta do `criar_peca` se perde: a ponte responde 502 com o texto do CADASTRO (o código ficou reservado, repetir com os
    mesmos dados não cria outra peça), e não o da régua ("grave de novo, é o mesmo número")."""
    _estoque_da_sessao(monkeypatch, _falso(perder_resposta={"criar_peca"}))
    _no_setor(monkeypatch, "PCM")
    r = com_o_fracttal(cur, _pessoa_ms(cur)).post(CADASTRAR, data={"contagem": "C-1", "linha": "L-2", "sigla": "CAB", "nome": "Cabo azul 6 mm"})
    assert r.status_code == 502 and "reservado" in r.get_json()["erro"] and "mesmo número" not in r.get_json()["erro"]
    assert F.ler(cur.config, forcar=True)[F.ABA_CURADORIA] == []


def test_o_login_do_fracttal_so_chega_na_ponte(cur, api_do_clone, monkeypatch):
    """O mesmo defeito da régua, no cadastro: o cookie `os_sessao` tem Path=/os e não vai para /t/pcm. O `estoque_da_sessao` é o
    DE VERDADE (só a rede do `api` do clone é de mentira) e o cookie vai com Path=/os: a ponte vê o login e cria a peça no
    Fracttal; uma rota /t/pcm, com o mesmo cliente, não vê (a sonda leva `SemLogin`)."""
    @cur.route("/t/pcm/pecas/inventario/_sonda")
    def sonda():
        try:
            E.estoque_da_sessao(cur)
            return "viu o login"
        except E.SemLogin:
            return "sem login"

    pedidos = []

    def post(url, headers=None, json=None, timeout=None):
        metodo = json[0]["method"]
        pedidos.append((metodo, headers["Authorization"]))
        if metodo == "inventories.items_list":
            return _result({"success": True, "total": 2, "data": [{"id": 5, "code": "SP-CAB-001"},
                                                                    {"id": 6, "code": "SP-CAB-012"}]})
        if metodo == "companies.units_list":
            return _result({"success": True, "total": 1, "data": [{"id": 362333, "description": "METRO"}]})
        assert metodo == "inventories.item_insert", metodo
        assert json[0]["params"]["code"] == "SP-CAB-013" and json[0]["params"]["id_unit"] == 362333
        return _result({"success": True, "data": {"id": 777, "description": "Cabo azul 6 mm    { SP-CAB-013 }"}})
    monkeypatch.setattr(api_do_clone.requests, "post", post)
    monkeypatch.setattr(E, "RITMO", E.Ritmo(dormir=lambda s: None))
    from nexus.torres.oscreator import ponte
    clone = ponte.clone(cur)
    jwt = _jwt()
    cookie = clone.session_interface.get_signing_serializer(clone).dumps(
        {"jwt": jwt, "conta": {"email": "pessoa.teste@exemplo.com", "nome": "Pessoa"}})     # a pessoa da sessão (`_pessoa`)
    _no_setor(monkeypatch, "PCM")
    c = _pessoa(cur)                                                    # a sessão nasceu do login do Fracttal
    c.set_cookie("os_sessao", cookie, path="/os")                       # como o login do Fracttal o grava
    assert c.get("/t/pcm/pecas/inventario/_sonda").get_data(as_text=True) == "sem login" and pedidos == []
    r = c.post(CADASTRAR, data={"contagem": "C-1", "linha": "L-2", "sigla": "CAB", "nome": "Cabo azul 6 mm",
                                "unidade": "METRO"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert [m for m, _ in pedidos] == ["inventories.items_list", "companies.units_list", "inventories.item_insert"]
    assert {h for _, h in pedidos} == {f"Bearer {jwt}"}                 # no login de quem apertou
    d = F.ler(cur.config, forcar=True)[F.ABA_CURADORIA]
    assert [(x["decisao"], x["id_item"], x["codigo_criado"]) for x in d] == [("cadastrar", "777", "SP-CAB-013")]
    # sem o cookie (a conta Microsoft não tem o login do Fracttal), a mesma ponte responde 401 com o link do login
    r = _pessoa_ms(cur).post(CADASTRAR, data={"contagem": "C-1", "linha": "L-3", "sigla": "CAB", "nome": "Conector"})
    assert r.status_code == 401 and "/os/login" in r.get_json()["login"]


def test_tela_de_quem_so_olha_nao_tem_formulario_nem_descricao_nem_foto(cur, monkeypatch):
    """O que o técnico escreveu e a foto dele (que podem mostrar gente, a placa de um equipamento, o que estiver à volta) são de
    quem decide: quem só vê a tela lê que há um achado fora do catálogo, a quantidade e a usina."""
    from nexus.cadastro.ligacoes import pasta_dados
    from nexus.pcm import telas
    destino = pasta_dados(cur.config) / "almox_inventario" / "fotos"
    destino.mkdir(parents=True)
    foto_id = CU.nome_da_foto("foto-abc")
    (destino / f"{foto_id}.jpg").write_bytes(b"\xff\xd8\xff jpeg de mentira")
    _no_setor(monkeypatch, "PCM")
    c = _pessoa_ms(cur)
    assert f"{URL}/foto/{foto_id}.jpg" in c.get(URL).get_data(as_text=True)         # quem decide vê
    monkeypatch.setattr(telas, "pode_programar", lambda: False)
    html = c.get(URL).get_data(as_text=True)
    assert "Achado fora do catálogo" in html and "2 unidades" in html
    assert "Cabo azul 6 mm" not in html and "Conector estanque" not in html and "/foto/" not in html and "sem foto" not in html
    assert "curadoria/decidir" not in html and 'name="decisao"' not in html
    assert c.get(f"{URL}/foto/{foto_id}.jpg").status_code == 403                    # nem a rota da foto


# ── a contagem gravada durante a decisão ────────────────────────────────────────────────────────────────────────────

class _GravaNoMeio(EstoqueFalso):
    """O Fracttal em cujo `criar_peca` outra pessoa grava a contagem (o PCM aprova e a gravação começa): o `_estados` do começo da
    decisão já era velho quando a peça foi criada."""

    def __init__(self, *a, cfg, **k):
        super().__init__(*a, **k)
        self._cfg = cfg

    def criar_peca(self, codigo, nome, unidade="UNIDADE"):
        r = super().criar_peca(codigo, nome, unidade)
        F.acrescentar(self._cfg, F.ABA_EVENTO, [{"tipo": "peca_gravada", "contagem_id": "C-1", "id_almoxarifado": ALMOX,
                                                  "id_item": "1", "para_qtd": 3}])
        return r


def test_a_contagem_gravada_durante_o_cadastro_nao_recebe_a_decisao(cur):
    """O estado da contagem é lido no começo, e o cadastro pagina o catálogo e cria a peça antes de escrever: a gravação pode
    chegar nesse intervalo. A decisão não entra no livro (valeria para um lote que já foi), e a mensagem diz o código que ficou
    criado no Fracttal; a reserva continua, para ele não ser escolhido de novo."""
    from nexus.cadastro.ligacoes import pasta_dados
    falso = _GravaNoMeio({ALMOX: {"5": {"saldo": 1, "codigo": "SP-CAB-001"}, "6": {"saldo": 1, "codigo": "SP-CAB-012"}}},
                         cfg=cur.config)
    with pytest.raises(Conflito, match=r"SP-CAB-013 foi criada no Fracttal, mas a contagem já tinha sido gravada"):
        _cadastrar(cur.config, falso)
    assert _livro(cur.config, F.ABA_CURADORIA) == [] and [e["tipo"] for e in _livro(cur.config, F.ABA_EVENTO)] == ["peca_gravada"]
    assert falso.codigos("CAB")[-1] == "SP-CAB-013"                                     # a peça existe no Fracttal
    (arq,) = list((pasta_dados(cur.config) / "almox_inventario").glob("curadoria_*.json"))
    assert "SP-CAB-013" in arq.read_text("utf-8")                                      # e a reserva segue
    with pytest.raises(Conflito, match="nova contagem"):                               # depois, a contagem já está fechada
        _cadastrar(cur.config, _falso())


def test_a_decisao_que_chega_depois_da_contagem_fechada_tambem_e_recusada(cur, monkeypatch):
    """O mesmo para as decisões que só gravam no livro: o estado é conferido de novo logo antes de escrever (o que fechou a
    contagem pode ser a recontagem pedida, a substituição ou a gravação)."""
    original = CU._usina_id

    def com_a_recontagem_no_meio(nome):
        F.acrescentar(cur.config, F.ABA_EVENTO, [{"tipo": "recontagem_pedida", "contagem_id": "C-1", "id_almoxarifado": ALMOX}])
        return original(nome)
    monkeypatch.setattr(CU, "_usina_id", com_a_recontagem_no_meio)
    with pytest.raises(Conflito, match="já tinha sido recusada"):
        CU.decidir(cur.config, "C-1", "L-2", "e_a_peca", id_item="1", pessoa=PESSOA)
    assert _livro(cur.config, F.ABA_CURADORIA) == []


# ── a reserva: os mesmos dados, e a peça achada é a desta linha ─────────────────────────────────────────────────────────

def test_nova_tentativa_com_outros_dados_nao_reaproveita_a_reserva(cur):
    """O código reservado é de uma peça com aquela sigla, aquele nome e aquela unidade. A tentativa seguinte da linha com outro
    dado é recusada (409) antes de qualquer pedido: com a peça já criada, a decisão ficaria ligada a uma peça com o nome errado; sem
    ela, criaria uma peça diferente da que a pessoa acha ter pedido. O mesmo nome com outra caixa ou espaço é o mesmo."""
    falso = _falso(perder_resposta={"criar_peca"})
    with pytest.raises(ConnectionError):
        _cadastrar(cur.config, falso)
    chamadas = list(falso.chamadas)
    for outro in (dict(sigla="PEL"), dict(nome="Cabo vermelho 6 mm"), dict(unidade="UNIDADE")):
        args = {**dict(sigla="CAB", nome="Cabo azul 6 mm", unidade="METRO", estoque=falso, pessoa=PESSOA), **outro}
        with pytest.raises(Conflito, match="SP-CAB-013.*outro dado"):
            CU.decidir(cur.config, "C-1", "L-2", "cadastrar", **args)
    assert falso.chamadas == chamadas and _livro(cur.config, F.ABA_CURADORIA) == []
    r = CU.decidir(cur.config, "C-1", "L-2", "cadastrar", sigla="cab", nome="  cabo AZUL 6 mm ", unidade="metro", estoque=falso,
                   pessoa=PESSOA)
    assert r["codigo"] == "SP-CAB-013" and r["criada"] is False


def test_a_tela_volta_preenchida_com_a_reserva(cur, monkeypatch):
    falso = _falso(perder_resposta={"criar_peca"})
    with pytest.raises(ConnectionError):
        _cadastrar(cur.config, falso)
    p = {x["chave_linha"]: x for x in CU.pendencias(cur.config)}
    assert p["L-2"]["reserva"]["codigo"] == "SP-CAB-013" and p["L-3"]["reserva"] is None
    _no_setor(monkeypatch, "PCM")
    html = _pessoa_ms(cur).get(URL).get_data(as_text=True)
    assert "já reservou o código SP-CAB-013" in html and '<option value="CAB" selected>' in html
    assert '<option value="METRO" selected>' in html and 'value="Cabo azul 6 mm"' in html


def test_a_peca_achada_com_outro_nome_nao_recebe_a_decisao(cur):
    """O código reservado foi achado no Fracttal, mas com outro nome: outra pessoa o usou depois (ou o nome foi trocado). Ligar a
    decisão a essa peça juntaria as unidades achadas ao estoque de uma peça que não é desta linha."""
    falso = _falso(perder_resposta={"criar_peca"})
    with pytest.raises(ConnectionError):
        _cadastrar(cur.config, falso)
    (id_item,) = [i for i, v in falso._catalogo.items() if v["codigo"] == "SP-CAB-013"]
    falso._catalogo[id_item]["nome"] = "Fusível de outra pessoa"
    with pytest.raises(Conflito, match=r"SP-CAB-013 existe no Fracttal com outro nome.*NÃO foi ligada"):
        _cadastrar(cur.config, falso)
    assert _livro(cur.config, F.ABA_CURADORIA) == [] and falso.chamadas.count("criar_peca") == 1


def test_nome_que_o_fracttal_nao_diz_nao_bloqueia():
    """A linha da lista sem o nome não prova diferença: só o nome que o Fracttal DIZ e que difere é conflito."""
    CU._conferir_o_nome_da_peca({"id": "9", "nome": ""}, {"nome": "Cabo azul"}, "SP-CAB-013")
    CU._conferir_o_nome_da_peca({"id": "9", "nome": "CABO  azul"}, {"nome": "Cabo azul"}, "SP-CAB-013")
    with pytest.raises(Conflito):
        CU._conferir_o_nome_da_peca({"id": "9", "nome": "Cabo preto"}, {"nome": "Cabo azul"}, "SP-CAB-013")


# ── as travas: uma por chave ───────────────────────────────────────────────────────────────────────────────────────────

def _em_fio(app, fazer):
    """Roda `fazer()` num fio com o contexto do app (a leitura dos livros do Campo pede o app). Devolve o fio."""
    import threading

    def correr():
        with app.app_context():
            fazer()
    t = threading.Thread(target=correr)
    t.start()
    return t


def test_duas_pessoas_na_mesma_linha_uma_ganha_e_a_outra_leva_409(cur, monkeypatch):
    """Com a tela aberta nas duas máquinas, o clique chega junto: a trava é da linha, e o que chega depois lê a decisão do que
    ganhou. Sem ela, os dois passavam da conferência e a linha ganhava duas decisões."""
    import time
    original = CU._usina_id

    def devagar(nome):
        time.sleep(0.4)                  # depois da conferência de "já decidida" e antes de escrever: onde a corrida acontece
        return original(nome)
    monkeypatch.setattr(CU, "_usina_id", devagar)
    resultados = []

    def decide():
        try:
            CU.decidir(cur.config, "C-1", "L-2", "e_a_peca", id_item="1", pessoa=PESSOA)
            resultados.append("ok")
        except Conflito as ex:
            resultados.append(str(ex))
    for t in [_em_fio(cur, decide), _em_fio(cur, decide)]:
        t.join(15)
    assert sorted(r == "ok" for r in resultados) == [False, True]
    assert "esta linha já foi decidida" in [r for r in resultados if r != "ok"][0]
    assert len(_livro(cur.config, F.ABA_CURADORIA)) == 1


class _CriarDevagar(EstoqueFalso):
    """O Fracttal que demora no `criar_peca` (a criação lenta) até o teste soltar."""

    def __init__(self, *a, **k):
        import threading
        super().__init__(*a, **k)
        self.entrou, self.soltar = threading.Event(), threading.Event()

    def criar_peca(self, codigo, nome, unidade="UNIDADE"):
        self.entrou.set()
        self.soltar.wait(10)
        return super().criar_peca(codigo, nome, unidade)


def test_o_cadastro_lento_de_uma_linha_nao_segura_a_decisao_de_outra(cur):
    """Uma trava do módulo, segurada enquanto o Fracttal cria a peça, faria todo o PCM esperar. A trava é da linha: com a L-2
    esperando o Fracttal, descartar a L-3 passa na hora."""
    import threading
    falso = _CriarDevagar({ALMOX: {"5": {"saldo": 1, "codigo": "SP-CAB-001"}}})
    t = _em_fio(cur, lambda: _cadastrar(cur.config, falso))
    try:
        assert falso.entrou.wait(10)
        feito = threading.Event()
        t2 = _em_fio(cur, lambda: (CU.decidir(cur.config, "C-1", "L-3", "descartar", motivo="não é peça", pessoa=PESSOA),
                                   feito.set()))
        assert feito.wait(10), "decidir outra linha esperou o cadastro lento no Fracttal"
        t2.join(10)
    finally:
        falso.soltar.set()
        t.join(10)
    assert sorted(x["chave_linha"] for x in _livro(cur.config, F.ABA_CURADORIA)) == ["L-2", "L-3"]


class _CodigosDevagar(EstoqueFalso):
    """A lista de códigos que leva um tempo: duas linhas da mesma sigla se cruzam entre ler a lista e reservar o código."""

    def codigos(self, sigla):
        import time
        r = super().codigos(sigla)
        time.sleep(0.3)
        return r


def test_duas_linhas_da_mesma_sigla_ao_mesmo_tempo_nao_escolhem_o_mesmo_codigo(cur):
    """Escolher o código e reservá-lo é uma conta só por sigla: sem a trava da sigla, as duas leriam a lista antes de qualquer
    reserva e as duas reservariam o 013 (e a 2ª criação recusada, ou, no pior caso, uma peça só para duas linhas)."""
    falso = _CodigosDevagar({ALMOX: {"5": {"saldo": 1, "codigo": "SP-CAB-001"}, "6": {"saldo": 1, "codigo": "SP-CAB-012"}}})
    resultados = {}

    def cadastra(linha):
        resultados[linha] = _cadastrar(cur.config, falso, linha)["codigo"]
    for t in [_em_fio(cur, lambda: cadastra("L-2")), _em_fio(cur, lambda: cadastra("L-3"))]:
        t.join(20)
    assert sorted(resultados.values()) == ["SP-CAB-013", "SP-CAB-014"]


def test_a_trava_de_uma_chave_e_so_dela():
    from nexus.pcm.inventario.travas import Travas
    t = Travas()
    assert t.de(("C-1", "L-2")) is t.de(("C-1", "L-2")) and t.de(("C-1", "L-2")) is not t.de(("C-1", "L-3"))


def test_sem_cor_fora_de_token_nem_endereco_da_raiz():
    t = (RAIZ / "nexus" / "templates" / "pcm" / "inventario_curadoria.html").read_text("utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", t) and "rgba(" not in t
    assert not re.search(r"""(href|action|src)="/""", t)
    css = (RAIZ / "nexus" / "static" / "pcm.css").read_text("utf-8")
    bloco = css[css.index("/* ── Curadoria do inventário"):]
    proximo = bloco.find("/* ── ", 10)
    bloco = bloco if proximo < 0 else bloco[:proximo]
    assert ".cu-" in bloco and not re.search(r"#[0-9a-fA-F]{3,8}\b", bloco) and "rgba(" not in bloco
    assert 'action="{{ raiz }}/os/_nexus/inventario/curadoria/cadastrar"' in t and "data-ponte" in t
