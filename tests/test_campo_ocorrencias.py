"""As ocorrências com plano de ação (Levi, 18/10/2026: "Próximas peças: o mapa das usinas e as ocorrências com plano de
ação. siga!"). As decisões dele no quiz: uma tela própria no Campo · App (lista e quadro, criar e editar) e, na Visão
geral, quantas ocorrências abertas cada usina tem; o Responsável O&M (pelo login do Fracttal) e os administradores criam
e editam, os outros só veem; os campos essenciais; o plano de ação com responsável, prazo e situação, e o andamento com
data. Desenho em docs/superpowers/specs/2026-10-18-ocorrencias-plano-de-acao-design.md.

Banco falso do test_campo_visao: as usinas 1, 2 e 3 estão mobilizadas; as pessoas 90 a 93 têm nome (cifrado) no cadastro.
Nomes fictícios."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest
from test_campo_visao import CHAVE_CADASTRO, banco  # noqa: F401  (banco é fixture)

from nexus.cadastro.cifra import Cofre
from nexus.campo import ocorrencias as O
from nexus.dados import catalogo, explica, livros

BRT = timezone(timedelta(hours=-3))
HOJE = datetime.now(BRT).date()
ADMIN = {"email": "admin@exemplo.test", "nome": "Fulana Administradora"}
RESP = {"email": "beltrano@exemplo.test", "nome": "Beltrano Supervisor"}
_N = [0]


def _t(minutos: int) -> str:
    return (datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=minutos)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ev(evento, oid, quando, cofre=None, dados=None, **cols):
    """Uma linha do livro como o banco devolve (as colunas que o evento não usa, vazias)."""
    _N[0] += 1
    eid = f"e{_N[0]:04d}"
    linha = {c: None for c in O.CAB}
    linha.update(id=eid, registrado_em=quando, evento=evento, ocorrencia_id=oid, **cols)
    if cofre and dados is not None:
        linha["dados_cifrados"] = cofre.cifrar(json.dumps(dados, ensure_ascii=False), O._ctx(eid))
    return linha


def _criou(oid, quando, cofre=None, dados=None, usina_id=1, criticidade="media", status="em_andamento", inicio=20261001,
           fim=None, **kw):
    return _ev("criou", oid, quando, cofre, dados, usina_id=usina_id, criticidade=criticidade, status=status,
               data_id_inicio=inicio, data_id_fim=fim, **kw)


def _acao(oid, quando, acao_id, situacao="a_fazer", prazo=None, usina_id=1, **kw):
    return _ev("acao", oid, quando, acao_id=acao_id, situacao=situacao, data_id_prazo=prazo, usina_id=usina_id, **kw)


# ── o estado sai dos eventos (puro) ──────────────────────────────────────────────────────────────────────────────────
def test_a_ultima_decisao_vale_e_o_texto_sai_decifrado():
    cofre = Cofre(CHAVE_CADASTRO)
    q = {"quem": {"nome": "Beltrano Supervisor", "email": "beltrano@exemplo.test"}}
    ev = [_criou("A", _t(0), cofre, dict(q, titulo="Inversor 2 desligando", descricao="Desarma à tarde",
                                         chamado="Fabricante 123"), criticidade="baixa", os="16034"),
          _ev("dados", "A", _t(5), cofre, dict(q, titulo="Inversor 2 desarmando", descricao="Desarma às 14 h",
                                               chamado=""),
              usina_id=1, criticidade="alta", status="pausado", data_id_inicio=20261001, os="16034, 16040")]
    oc = O.estado(ev, cofre)["A"]
    assert (oc["criticidade"], oc["status"], oc["titulo"], oc["os"]) == ("alta", "pausado", "Inversor 2 desarmando",
                                                                        "16034, 16040")
    assert (oc["descricao"], oc["chamado"], oc["usina_id"]) == ("Desarma às 14 h", "", 1)
    assert oc["inicio"] == date(2026, 10, 1) and oc["fim"] is None and oc["aberta"]
    assert oc["criada_por"] == "Beltrano Supervisor" and oc["criada_em"] < oc["alterada_em"]
    # sem a chave do cadastro, os códigos e as datas continuam; o texto sai vazio
    sem = O.estado(ev, None)["A"]
    assert (sem["titulo"], sem["criticidade"], sem["status"]) == ("", "alta", "pausado")


def test_a_acao_editada_fica_com_a_ultima_decisao_e_o_andamento_vem_do_mais_novo():
    cofre = Cofre(CHAVE_CADASTRO)
    q = {"quem": {"nome": "Beltrano Supervisor"}}
    ev = [_criou("A", _t(0), cofre, dict(q, titulo="T")),
          _acao("A", _t(1), "a1", prazo=20261020, cofre=cofre, dados=dict(q, texto="Trocar o fusível",
                                                                           responsavel="Ciclano Chefe"),
                responsavel_pessoa_id=91),
          _acao("A", _t(2), "a2", cofre=cofre, dados=dict(q, texto="Chamar o fabricante",
                                                          responsavel="Beltrano Supervisor"), responsavel_pessoa_id=90),
          _acao("A", _t(3), "a1", situacao="concluida", prazo=20261020, cofre=cofre,
                dados=dict(q, texto="Trocar o fusível da string 3", responsavel="Ciclano Chefe"),
                responsavel_pessoa_id=91),
          _ev("andamento", "A", _t(4), cofre, dict(q, texto="Fusível trocado"), usina_id=1),
          _ev("andamento", "A", _t(6), cofre, dict(q, texto="O fabricante respondeu"), usina_id=1)]
    oc = O.estado(ev, cofre)["A"]
    assert [(a["id"], a["situacao"], a["texto"]) for a in oc["acoes"]] == [
        ("a1", "concluida", "Trocar o fusível da string 3"), ("a2", "a_fazer", "Chamar o fabricante")]
    assert (oc["acoes"][0]["responsavel_id"], oc["acoes"][0]["responsavel"]) == (91, "Ciclano Chefe")
    assert oc["acoes"][0]["prazo"] == date(2026, 10, 20)
    assert [x["texto"] for x in oc["andamentos"]] == ["O fabricante respondeu", "Fusível trocado"]
    assert oc["andamentos"][0]["nome"] == "Beltrano Supervisor" and oc["andamentos"][0]["quando_txt"].endswith("09:06")
    assert oc["proximo_prazo"] is None and (oc["acoes_abertas"], len(oc["acoes"])) == (1, 2)


def test_evento_sem_o_criou_ou_desconhecido_fica_fora():
    ev = [_ev("dados", "X", _t(0), usina_id=1, criticidade="alta", status="em_andamento", data_id_inicio=20261001),
          _acao("Y", _t(1), "a1"),
          _criou("A", _t(2)), _ev("apagou", "A", _t(3)), _ev("andamento", "", _t(4))]
    est = O.estado(ev, None)
    assert list(est) == ["A"] and est["A"]["andamentos"] == []


def test_dois_eventos_no_mesmo_segundo_ficam_na_ordem_da_gravacao():
    ev = [_criou("A", _t(0), criticidade="baixa"),
          _ev("dados", "A", _t(1), usina_id=1, criticidade="alta", status="em_andamento", data_id_inicio=20261001),
          _ev("dados", "A", _t(1), usina_id=1, criticidade="muito_alta", status="em_andamento", data_id_inicio=20261001)]
    assert O.estado(ev, None)["A"]["criticidade"] == "muito_alta"


def test_o_proximo_prazo_e_o_da_acao_em_aberto_e_o_atraso_e_contra_hoje():
    ev = [_criou("A", _t(0)),
          _acao("A", _t(1), "a1", prazo=20261025), _acao("A", _t(2), "a2", prazo=20261015, situacao="em_andamento"),
          _acao("A", _t(3), "a3", prazo=20261001, situacao="concluida"), _acao("A", _t(4), "a4")]
    oc = O.estado(ev, None, hoje=date(2026, 10, 18))["A"]
    assert oc["proximo_prazo"] == date(2026, 10, 15) and oc["atrasada"]
    assert [a["atrasada"] for a in oc["acoes"]] == [False, True, False, False]
    assert not O.estado(ev, None, hoje=date(2026, 10, 14))["A"]["atrasada"]


def test_a_lista_vai_pelo_prazo_da_proxima_acao_e_a_finalizada_por_ultimo():
    ev = [_criou("A", _t(0), criticidade="baixa"), _acao("A", _t(1), "a1", prazo=20261020),
          _criou("B", _t(2), criticidade="baixa", inicio=20261005),
          _criou("C", _t(3), criticidade="media"), _acao("C", _t(4), "c1", prazo=20261012),
          _criou("D", _t(5), status="finalizado", fim=20261010), _acao("D", _t(6), "d1", prazo=20261001),
          _criou("E", _t(7), criticidade="muito_alta", inicio=20261008),
          _criou("F", _t(8), status="finalizado", fim=20261016)]
    lista = O.ordenar(list(O.estado(ev, None).values()))
    # com prazo (o mais perto primeiro), sem prazo (a mais crítica, depois a mais antiga) e as finalizadas no fim (a
    # que terminou por último primeiro)
    assert [o["id"] for o in lista] == ["C", "A", "E", "B", "F", "D"]


def test_a_finalizada_sai_das_abertas_e_vale_a_pior_criticidade():
    ev = [_criou("A", _t(0), usina_id=1, criticidade="alta"),
          _criou("B", _t(1), usina_id=1, criticidade="muito_alta", status="finalizado", fim=20261010),
          _criou("C", _t(2), usina_id=1, criticidade="media", status="pausado"),
          _criou("D", _t(3), usina_id=3, criticidade="baixa")]
    assert O.abertas_por_usina(O.estado(ev, None)) == {1: {"n": 2, "pior": "alta"}, 3: {"n": 1, "pior": "baixa"}}


def test_o_livro_e_o_fato_estao_no_catalogo_antes_da_primeira_gravacao():
    l = catalogo.LIVRO_POR_NOME[O.LIVRO]
    assert l.abas == (O.ABA,) and l.so_cresce == (O.ABA,) and not l.no_banco
    f = next(f for f in catalogo.FATOS if f.livro == f"{O.LIVRO} · {O.ABA}")
    # sem medida: cada linha é um evento, conta-se linhas (o teste da camada exige o tipo sem_medida sem medidas)
    assert (f.area, f.tipo, f.chave, f.medidas) == ("campo", "sem_medida", ("id",), ())
    assert {d: f.dims[d][0] for d in ("data", "usina", "equipamento", "pessoa", "os")} == {
        "data": "id", "usina": "id", "equipamento": "id", "pessoa": "id", "os": "cod"}
    assert f.id in explica.RESUMO and f.id in explica.PARA_QUE
    assert all(c in O.CAB for c in ("data_id", "usina_id", "usina_ligada_por", "equipamento_id",
                                    "equipamento_ligado_por", "pessoa_id", "pessoa_hmac", "dados_cifrados"))


# ── gravar e ler no banco ────────────────────────────────────────────────────────────────────────────────────────────
def _form(**kw):
    f = {"titulo": "Inversor 2 desarmando", "usina_id": "1", "codigo_ativo": "", "criticidade": "alta",
         "status": "em_andamento", "inicio": (HOJE - timedelta(days=2)).isoformat(), "fim": "",
         "descricao": "Desarma todo dia às 14 h", "chamado": "Fabricante 4455", "os": "16034"}
    f.update(kw)
    return f


def _estado():
    O.limpar()
    return O.estado(O.ler()["eventos"], O.cofre_ou_nada())


def test_criar_grava_cifrado_e_le_de_volta(banco):
    ev = O.criar(_form(codigo_ativo="thpn-alt100-etkr1 "), ADMIN, True)
    linhas = banco.linhas(O.LIVRO, O.ABA)
    assert len(linhas) == 1
    x = linhas[0]
    assert (x["evento"], x["usina_id"], x["criticidade"], x["status"], x["os"]) == ("criou", 1, "alta", "em_andamento",
                                                                                   "16034")
    assert x["data_id"] == int(datetime.now(BRT).strftime("%Y%m%d")) and x["registrado_em"].endswith("Z")
    assert x["data_id_inicio"] == int((HOJE - timedelta(days=2)).strftime("%Y%m%d")) and x["data_id_fim"] is None
    # o código do ativo vai canônico; sem a dimensão de equipamento no banco, não liga (não liga = vazio)
    assert (x["codigo_ativo"], x["equipamento_id"], x["equipamento_ligado_por"]) == ("THPN-ALT100-ETKR1", None, None)
    assert x["usina_ligada_por"] == "tela" and x["pessoa_hmac"]
    bruto = json.dumps(linhas, ensure_ascii=False, default=str)
    for texto in ("Inversor 2", "Desarma", "Fabricante", "Fulana", "admin@"):
        assert texto not in bruto, texto                                   # nada de texto livre nem nome em claro
    oc = _estado()[ev["ocorrencia_id"]]
    assert (oc["titulo"], oc["descricao"], oc["chamado"], oc["criada_por"]) == (
        "Inversor 2 desarmando", "Desarma todo dia às 14 h", "Fabricante 4455", "Fulana Administradora")


def test_o_ativo_que_esta_na_dimensao_liga_pelo_equipamento_id(banco):
    from test_campo_visao import _aba
    _aba(banco, "nexus_equipamentos", "dim_equipamento", [
        {"equipamento_id": 900, "codigo": "THPN-ALT100-ETKR1", "descricao": "Tracker 1", "usina_id": 1}])
    O.criar(_form(codigo_ativo="THPN-ALT100-ETKR1"), ADMIN, True)
    x = banco.linhas(O.LIVRO, O.ABA)[0]
    assert (x["equipamento_id"], x["equipamento_ligado_por"]) == (900, "codigo_ativo")


def test_editar_o_plano_de_acao_e_o_andamento(banco):
    oid = O.criar(_form(), RESP, True)["ocorrencia_id"]
    O.editar(oid, _form(status="pausado", criticidade="muito_alta", os="16034, 16040"), RESP, True)
    pessoas = [{"id": 91, "nome": "Ciclano Chefe"}, {"id": 90, "nome": "Beltrano Supervisor"}]
    prazo = (HOJE + timedelta(days=5)).isoformat()
    a1 = O.salvar_acao(oid, {"acao_id": "", "texto": "Trocar o fusível", "responsavel_id": "91", "prazo": prazo,
                             "situacao": "a_fazer"}, RESP, True, pessoas)["acao_id"]
    O.salvar_acao(oid, {"acao_id": a1, "texto": "Trocar o fusível", "responsavel_id": "91", "prazo": prazo,
                        "situacao": "concluida"}, RESP, True, pessoas)
    O.registrar_andamento(oid, "Fusível trocado;\n  a geração voltou", RESP, True)
    oc = _estado()[oid]
    assert (oc["status"], oc["criticidade"], oc["os"]) == ("pausado", "muito_alta", "16034, 16040")
    assert [(a["id"], a["situacao"], a["responsavel"]) for a in oc["acoes"]] == [(a1, "concluida", "Ciclano Chefe")]
    assert oc["andamentos"][0]["texto"] == "Fusível trocado;\na geração voltou"
    assert oc["andamentos"][0]["nome"] == "Beltrano Supervisor"
    assert [l["evento"] for l in banco.linhas(O.LIVRO, O.ABA)] == ["criou", "dados", "acao", "acao", "andamento"]
    assert all(l["usina_id"] == 1 for l in banco.linhas(O.LIVRO, O.ABA))   # todo evento liga à usina da ocorrência
    with pytest.raises(O.Recusada, match="Nada mudou"):
        O.editar(oid, _form(status="pausado", criticidade="muito_alta", os="16034,16040"), RESP, True)


def test_finalizada_sem_o_fim_termina_hoje(banco):
    oid = O.criar(_form(status="finalizado"), ADMIN, True)["ocorrencia_id"]
    oc = _estado()[oid]
    assert oc["fim"] == HOJE and not oc["aberta"]


@pytest.mark.parametrize("campos, motivo", [
    ({"titulo": "   "}, "Escreva o título"),
    ({"titulo": "x" * 121}, "passou de 120"),
    ({"usina_id": ""}, "Escolha a usina"),
    ({"usina_id": "4"}, "não está mobilizada"),
    ({"criticidade": "urgente"}, "Escolha a criticidade"),
    ({"status": "cancelado"}, "Escolha o status"),
    ({"inicio": ""}, "Escolha o início"),
    ({"inicio": "2026-13-01"}, "Data inválida no início"),
    ({"inicio": "0202-10-15"}, "antes de 01/01/2024"),
    ({"inicio": (HOJE + timedelta(days=1)).isoformat()}, "início não pode ser depois de hoje"),
    ({"fim": (HOJE - timedelta(days=5)).isoformat(), "status": "finalizado"}, "fim não pode ser antes do início"),
    ({"fim": HOJE.isoformat()}, "status é Finalizado"),
    ({"descricao": "x" * 2001}, "passou de 2000"),
    ({"chamado": "x" * 121}, "passou de 120"),
    ({"os": "16034 e 16040"}, "só tem algarismos"),
    ({"codigo_ativo": "fulano@exemplo.test"}, "código do ativo"),
])
def test_recusa_com_o_porque_e_nada_grava(banco, campos, motivo):
    with pytest.raises(O.Recusada, match=motivo):
        O.criar(_form(**campos), ADMIN, True)
    assert banco.syncs == 0


def test_quem_nao_pode_ou_sem_login_de_pessoa_nao_grava(banco):
    with pytest.raises(O.Recusada, match="Responsável O&M"):
        O.criar(_form(), RESP, False)
    with pytest.raises(O.Recusada, match="senha de administrador"):
        O.criar(_form(), {}, True)                                         # o administrador que entrou pela senha
    assert banco.syncs == 0


def test_sem_a_chave_do_cadastro_nao_grava(banco, app):
    app.config["NEXUS_CHAVE_CADASTRO"] = None
    with pytest.raises(O.Recusada, match="chave do cadastro"):
        O.criar(_form(), ADMIN, True)
    assert banco.syncs == 0


def test_recusas_da_acao_e_do_andamento(banco):
    oid = O.criar(_form(), ADMIN, True)["ocorrencia_id"]
    pessoas = [{"id": 91, "nome": "Ciclano Chefe"}]
    base = {"acao_id": "", "texto": "Trocar o fusível", "responsavel_id": "91", "prazo": "", "situacao": "a_fazer"}
    for campos, motivo in (({"texto": " "}, "Escreva a ação"), ({"texto": "x" * 501}, "passou de 500"),
                           ({"responsavel_id": "90"}, "responsável da ação na lista"),
                           ({"situacao": "talvez"}, "Escolha a situação"),
                           ({"prazo": "2026-02-30"}, "Data inválida no prazo"),
                           ({"prazo": (HOJE + timedelta(days=4 * 365)).isoformat()}, "prazo passou de 3 anos"),
                           ({"acao_id": "naoexiste"}, "Não achei esta ação")):
        with pytest.raises(O.Recusada, match=motivo):
            O.salvar_acao(oid, dict(base, **campos), ADMIN, True, pessoas)
    with pytest.raises(O.Recusada, match="Não achei esta ocorrência"):
        O.salvar_acao("000000000000", base, ADMIN, True, pessoas)
    with pytest.raises(O.Recusada, match="Escreva o andamento"):
        O.registrar_andamento(oid, "  ", ADMIN, True)
    with pytest.raises(O.Recusada, match="passou de 2000"):
        O.registrar_andamento(oid, "x" * 2001, ADMIN, True)
    assert banco.syncs == 1                                                # só a criação gravou


def test_a_releitura_que_falha_nao_grava_por_cima(banco):
    O.criar(_form(), ADMIN, True)
    banco.omitir.add(O.LIVRO)                     # a listagem do banco omite o livro por um instante: a releitura vê vazio
    with pytest.raises(livros.GravacaoRecusada):
        O.criar(_form(titulo="Outra"), ADMIN, True)
    banco.omitir.clear()
    assert len(banco.linhas(O.LIVRO, O.ABA)) == 1


def test_a_leitura_que_falha_devolve_o_erro_e_a_ultima_boa(banco, monkeypatch):
    O.criar(_form(), ADMIN, True)
    O.limpar()
    assert len(O.ler()["eventos"]) == 1

    def fora(*a, **k):
        raise ConnectionError("banco fora")
    monkeypatch.setattr(livros, "ler", fora)
    g = O.ler(forcar=True)
    assert len(g["eventos"]) == 1 and "ConnectionError" in g["erro"]       # a última boa, com o erro
    O.limpar()
    g = O.ler()
    assert g["eventos"] == [] and "ConnectionError" in g["erro"] and g["lido_em"] is None


def test_as_pessoas_do_cadastro_para_o_responsavel_da_acao(banco):
    nomes = [p["nome"] for p in O.pessoas_do_cadastro()]
    assert nomes == sorted(nomes) and {"Beltrano Supervisor", "Ciclano Chefe"} <= set(nomes)
    assert all(p["id"] for p in O.pessoas_do_cadastro())


# ── a tela (Campo · App → Ocorrências) ───────────────────────────────────────────────────────────────────────────────
TECNICO = {"email": "tecnico@exemplo.test", "nome": "Técnico Qualquer"}


@pytest.fixture(autouse=True)
def _sem_copia():
    O.limpar()
    yield
    O.limpar()


@pytest.fixture
def cad(banco, app):
    """O cadastro com o Responsável O&M de cada usina (a Altair e a Brodowski 1 do 91, a Coração 1 do 90) e o
    administrador pelo e-mail (NEXUS_ADMINS)."""
    from test_campo_visao import USINAS, _aba
    from nexus.campo import visao
    _aba(banco, "cadastro_nexus", "usinas", [dict(u, responsavel_om_id={1: 91, 2: 91, 3: 90}.get(u["usina_id"]))
                                             for u in USINAS])
    app.config["NEXUS_ADMINS"] = ADMIN["email"]
    visao.limpar()
    return banco


def _entra(cliente, usuario=None):
    from conftest import SENHA_TESTE
    cliente.post("/entrar", data={"senha": SENHA_TESTE})
    if usuario:
        with cliente.session_transaction() as s:
            s["usuario"] = dict(usuario, perfil="")
    return cliente


def _oid(resp) -> str:
    return resp.headers["Location"].split("/ocorrencias/")[1].split("?")[0].split("#")[0]


def test_a_tela_esta_no_menu_do_campo_e_e_dos_responsaveis_ufv():
    from nexus.torres.campo import TORRE
    t = TORRE.tela("ocorrencias")
    assert t.nome == "Ocorrências" and t.do_setor == "Responsáveis UFV"
    ids = [x.id for x in TORRE.telas]
    assert ids.index("ocorrencias") == ids.index("responsaveis") + 1


def test_a_lista_abre_nas_abertas_e_o_quadro_tem_as_tres_colunas(cad, cliente):
    c = _entra(cliente, ADMIN)
    a = O.criar(_form(titulo="Inversor 2 desarmando", criticidade="alta"), ADMIN, True)["ocorrencia_id"]
    O.criar(_form(titulo="Cerca caída", usina_id="3", criticidade="baixa", status="pausado"), ADMIN, True)
    O.criar(_form(titulo="Trafo aquecendo", status="finalizado"), ADMIN, True)
    html = c.get("/t/campo/ocorrencias?responsavel=*").get_data(as_text=True)
    assert "Inversor 2 desarmando" in html and "Cerca caída" in html and "Trafo aquecendo" not in html
    assert f"/t/campo/ocorrencias/{a}" in html and "Nova ocorrência" in html and "Altair" in html
    assert "Todas" in html and "Abertas" in html
    html = c.get("/t/campo/ocorrencias?responsavel=*&status=*").get_data(as_text=True)
    assert "Trafo aquecendo" in html
    q = c.get("/t/campo/ocorrencias?responsavel=*&ver=quadro").get_data(as_text=True)
    assert all(f">{col}<" in q for col in ("Em andamento", "Pausado", "Finalizado")) and "Trafo aquecendo" in q


def test_criar_pela_tela(cad, cliente):
    c = _entra(cliente, ADMIN)
    html = c.get("/t/campo/ocorrencias/nova?usina=3").get_data(as_text=True)
    assert 'name="titulo"' in html and '<option value="3" selected>' in html
    r = c.post("/t/campo/ocorrencias/nova", data=_form(titulo="Cerca caída", usina_id="3"))
    assert r.status_code == 302
    html = c.get(r.headers["Location"]).get_data(as_text=True)
    assert "Ocorrência registrada" in html and "Cerca caída" in html and "Coração 1" in html
    assert "Fulana Administradora" in html and O.estado(O.ler(forcar=True)["eventos"], None)[_oid(r)]["usina_id"] == 3


def test_a_recusa_na_tela_diz_o_porque_e_guarda_o_que_foi_digitado(cad, cliente):
    c = _entra(cliente, ADMIN)
    r = c.post("/t/campo/ocorrencias/nova", data=_form(titulo="Cerca caída", inicio="2026-13-01"))
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Data inválida no início" in html and 'value="Cerca caída"' in html
    assert cad.syncs == 0


def test_quem_nao_pode_so_ve(cad, cliente):
    oid = O.criar(_form(titulo="Inversor 2 desarmando"), ADMIN, True)["ocorrencia_id"]
    c = _entra(cliente, TECNICO)
    html = c.get("/t/campo/ocorrencias?responsavel=*").get_data(as_text=True)
    assert "Inversor 2 desarmando" in html and "Nova ocorrência" not in html
    html = c.get(f"/t/campo/ocorrencias/{oid}").get_data(as_text=True)
    assert "Inversor 2 desarmando" in html and "Registrar andamento" not in html and "Salvar a ação" not in html
    r = c.post("/t/campo/ocorrencias/nova", data=_form())
    assert r.status_code == 403 and "Responsável O&amp;M" in r.get_data(as_text=True)
    assert c.post(f"/t/campo/ocorrencias/{oid}/andamento", data={"texto": "x"}).status_code == 403
    assert len(cad.linhas(O.LIVRO, O.ABA)) == 1


def test_o_administrador_da_senha_ve_o_aviso_de_entrar_com_o_login(cad, logado):
    html = logado.get("/t/campo/ocorrencias").get_data(as_text=True)
    assert "entre com o seu login" in html.lower() and "Nova ocorrência" not in html


def test_o_responsavel_registra_e_a_lista_abre_nas_usinas_dele(cad, cliente):
    O.criar(_form(titulo="Inversor 2 desarmando"), ADMIN, True)                 # na Altair, do Ciclano
    c = _entra(cliente, RESP)                                    # o Beltrano é o Responsável O&M da Coração 1
    r = c.post("/t/campo/ocorrencias/nova", data=_form(titulo="Cerca caída", usina_id="3"))
    assert r.status_code == 302
    html = c.get("/t/campo/ocorrencias").get_data(as_text=True)
    assert "Cerca caída" in html and "Inversor 2 desarmando" not in html
    assert "Inversor 2 desarmando" in c.get("/t/campo/ocorrencias?responsavel=*").get_data(as_text=True)


def test_o_plano_de_acao_e_o_andamento_pela_tela(cad, cliente):
    c = _entra(cliente, ADMIN)
    oid = O.criar(_form(), ADMIN, True)["ocorrencia_id"]
    html = c.get(f"/t/campo/ocorrencias/{oid}").get_data(as_text=True)
    assert "Nenhuma ação no plano ainda" in html and '<option value="91">Ciclano Chefe</option>' in html
    ontem = (HOJE - timedelta(days=1)).isoformat()
    r = c.post(f"/t/campo/ocorrencias/{oid}/acao", data={"acao_id": "", "texto": "Trocar o fusível",
                                                          "responsavel_id": "91", "prazo": ontem, "situacao": "a_fazer"})
    assert r.status_code == 302
    r = c.post(f"/t/campo/ocorrencias/{oid}/andamento", data={"texto": "Fusível comprado"})
    html = c.get(r.headers["Location"]).get_data(as_text=True)
    assert "Andamento registrado" in html and "Fusível comprado" in html and "Trocar o fusível" in html
    assert "Ciclano Chefe" in html and "oc-atrasada" in html
    aid = O.estado(O.ler(forcar=True)["eventos"], None)[oid]["acoes"][0]["id"]
    r = c.post(f"/t/campo/ocorrencias/{oid}/acao", data={"acao_id": aid, "texto": "Trocar o fusível",
                                                          "responsavel_id": "91", "prazo": ontem,
                                                          "situacao": "concluida"})
    html = c.get(r.headers["Location"]).get_data(as_text=True)
    assert "Ação salva" in html and "Concluída" in html and "oc-atrasada" not in html
    lista = c.get("/t/campo/ocorrencias?responsavel=*").get_data(as_text=True)
    assert "Sem ação em aberto" in lista


def test_a_lista_mostra_a_proxima_acao_e_o_atraso(cad, cliente):
    c = _entra(cliente, ADMIN)
    oid = O.criar(_form(), ADMIN, True)["ocorrencia_id"]
    O.salvar_acao(oid, {"acao_id": "", "texto": "Chamar o fabricante", "responsavel_id": "90",
                        "prazo": (HOJE - timedelta(days=2)).isoformat(), "situacao": "em_andamento"}, ADMIN, True,
                  [{"id": 90, "nome": "Beltrano Supervisor"}])
    html = c.get("/t/campo/ocorrencias?responsavel=*").get_data(as_text=True)
    assert "Chamar o fabricante" in html and "Beltrano Supervisor" in html and "oc-atrasada" in html


def test_editar_pela_tela(cad, cliente):
    c = _entra(cliente, ADMIN)
    oid = O.criar(_form(), ADMIN, True)["ocorrencia_id"]
    r = c.post(f"/t/campo/ocorrencias/{oid}/dados", data=_form(status="pausado"))
    assert r.status_code == 302
    html = c.get(r.headers["Location"]).get_data(as_text=True)
    assert "Ocorrência salva" in html and ">Pausado<" in html
    html = c.post(f"/t/campo/ocorrencias/{oid}/dados", data=_form(status="pausado")).get_data(as_text=True)
    assert "Nada mudou" in html


def test_os_filtros(cad, cliente):
    c = _entra(cliente, ADMIN)
    O.criar(_form(titulo="Ocorrencia Altair"), ADMIN, True)
    O.criar(_form(titulo="Ocorrencia Coracao", usina_id="3", criticidade="baixa"), ADMIN, True)
    O.criar(_form(titulo="Ocorrencia Brodowski", usina_id="2", criticidade="muito_alta", status="pausado"), ADMIN, True)

    def titulos(q):
        html = c.get("/t/campo/ocorrencias?" + q).get_data(as_text=True)
        return {t for t in ("Ocorrencia Altair", "Ocorrencia Coracao", "Ocorrencia Brodowski") if t in html}
    assert titulos("responsavel=*&usina=3") == {"Ocorrencia Coracao"}
    assert titulos("responsavel=*&criticidade=alta") == {"Ocorrencia Altair"}
    assert titulos("responsavel=*&status=pausado") == {"Ocorrencia Brodowski"}
    assert titulos("responsavel=Ciclano+Chefe") == {"Ocorrencia Altair", "Ocorrencia Brodowski"}


def test_pedido_de_outro_site_e_403(cad, cliente):
    c = _entra(cliente, ADMIN)
    oid = O.criar(_form(), ADMIN, True)["ocorrencia_id"]
    acao = {"acao_id": "", "texto": "x", "responsavel_id": "91", "prazo": "", "situacao": "a_fazer"}
    for caminho, dados in (("/t/campo/ocorrencias/nova", _form()), (f"/t/campo/ocorrencias/{oid}/dados", _form()),
                           (f"/t/campo/ocorrencias/{oid}/acao", acao),
                           (f"/t/campo/ocorrencias/{oid}/andamento", {"texto": "x"})):
        assert c.post(caminho, data=dados, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403, caminho
    assert len(cad.linhas(O.LIVRO, O.ABA)) == 1


def test_sem_a_chave_do_cadastro_a_tela_avisa_e_continua_mostrando(cad, cliente, app):
    c = _entra(cliente, ADMIN)
    oid = O.criar(_form(), ADMIN, True)["ocorrencia_id"]
    app.config["NEXUS_CHAVE_CADASTRO"] = None
    O.limpar()
    html = c.get("/t/campo/ocorrencias?responsavel=*").get_data(as_text=True)
    assert "chave do cadastro" in html and f"/t/campo/ocorrencias/{oid}" in html
    r = c.get(f"/t/campo/ocorrencias/{oid}")
    assert r.status_code == 200 and "chave do cadastro" in r.get_data(as_text=True)


def test_banco_fora_a_tela_diz(cad, cliente, monkeypatch):
    c = _entra(cliente, ADMIN)
    monkeypatch.setattr(O, "ler", lambda forcar=False: {"eventos": [], "lido_em": None,
                                                        "erro": "ConnectionError: banco fora"})
    r = c.get("/t/campo/ocorrencias")
    assert r.status_code == 200 and "Não consegui ler as ocorrências no banco" in r.get_data(as_text=True)


def test_ocorrencia_que_nao_existe_e_404(cad, cliente):
    c = _entra(cliente, ADMIN)
    assert c.get("/t/campo/ocorrencias/000000000000").status_code == 404
    assert c.get("/t/campo/ocorrencias/nao-e-id").status_code == 404
