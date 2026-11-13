"""As demandas entre setores (12/11/2026, Levi: "os setores consigam conversar entre si sem ter que especificamente criar
um OS"; o desenho em docs/superpowers/specs/2026-11-12-demandas-entre-setores-design.md).

O que estes testes seguram: o prazo em dias úteis (sem fim de semana e feriado nacional), a pausa do "pedir informação",
a conclusão sozinha em 3 dias úteis, a vencida que avisa o setor; o livro `nexus_demandas` no catálogo antes da 1ª
gravação, com o texto e os nomes só cifrados; o papel e a vez de cada passo; a OS só da usina escolhida; e as telas
(a Caixa de entrada, a Nova demanda, os Temas do setor e o sininho). Banco falso do test_campo_visao; nomes fictícios."""
from datetime import date

from nexus.comando import demandas_regras as R


def _ev(evento, iso):
    return {"evento": evento, "registrado_em": iso}


ABRIU = {"registrado_em": "2026-11-11T13:00:00.000Z"}           # qua 11/11, 10:00 em Brasília


# ── a regra pura ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_prazo_pula_fim_de_semana_e_feriado():
    assert R.somar_dias_uteis(date(2026, 11, 13), 1) == date(2026, 11, 16)          # sexta + 1 = segunda
    assert R.somar_dias_uteis(date(2026, 11, 19), 1) == date(2026, 11, 23)          # 20/11 é feriado nacional
    assert R.dias_uteis_entre(date(2026, 11, 13), date(2026, 11, 16)) == 1
    assert R.dias_uteis_entre(date(2026, 11, 16), date(2026, 11, 13)) == -1


def test_situacoes_pelo_ultimo_evento():
    hoje = date(2026, 11, 12)
    assert R.estado(ABRIU, [], 2, hoje)["situacao"] == "nova"
    assert R.estado(ABRIU, [_ev("em_analise", "2026-11-11T15:00:00Z")], 2, hoje)["situacao"] == "em_analise"
    e = R.estado(ABRIU, [_ev("pediu_informacao", "2026-11-11T15:00:00Z")], 2, hoje)
    assert e["situacao"] == "aguardando" and e["pausada"] and not e["vencida"]
    passos = [_ev("em_analise", "2026-11-11T14:00:00Z"), _ev("respondeu", "2026-11-12T14:00:00Z")]
    assert R.estado(ABRIU, passos, 2, hoje)["situacao"] == "finalizada"
    devolvida = R.estado(ABRIU, passos + [_ev("devolveu", "2026-11-13T14:00:00Z")], 2, date(2026, 11, 13))
    assert devolvida["situacao"] == "devolvida" and devolvida["prazo"] == date(2026, 11, 17)      # 2 dias da devolução
    assert R.estado(ABRIU, passos + [_ev("concluiu", "2026-11-12T16:00:00Z")], 2, hoje)["situacao"] == "concluida"
    # o passo fora da vez não muda nada (concluir o que não foi respondido)
    assert R.estado(ABRIU, [_ev("concluiu", "2026-11-11T16:00:00Z")], 2, hoje)["situacao"] == "nova"


def test_a_pausa_empurra_o_prazo():
    assert R.estado(ABRIU, [], 2, date(2026, 11, 11))["prazo"] == date(2026, 11, 13)
    pausa = [_ev("pediu_informacao", "2026-11-12T14:00:00Z"), _ev("informou", "2026-11-16T14:00:00Z")]
    e = R.estado(ABRIU, pausa, 2, date(2026, 11, 16))
    assert e["situacao"] == "em_analise" and e["prazo"] == date(2026, 11, 17)      # sexta e segunda parados
    # com a pausa ainda aberta, o prazo anda junto até hoje
    aberta = R.estado(ABRIU, pausa[:1], 2, date(2026, 11, 16))
    assert aberta["pausada"] and aberta["prazo"] == date(2026, 11, 17) and not aberta["vencida"]


def test_vencida_e_conclusao_sozinha():
    e = R.estado(ABRIU, [_ev("em_analise", "2026-11-11T14:00:00Z")], 2, date(2026, 11, 16))
    assert e["vencida"] and e["dias_restantes"] == -1 and R.selo_do_prazo(e) == ("Vencida", "há 1 dia", "critico")
    assert R.selo_do_prazo(R.estado(ABRIU, [], 2, date(2026, 11, 13))) == ("Vence", "hoje", "critico")
    assert R.selo_do_prazo(R.estado(ABRIU, [], 2, date(2026, 11, 12))) == ("Falta", "1 dia", "alerta")
    respondida = [_ev("respondeu", "2026-11-10T14:00:00Z")]
    abriu_antes = {"registrado_em": "2026-11-09T13:00:00Z"}
    assert R.estado(abriu_antes, respondida, 2, date(2026, 11, 12))["situacao"] == "finalizada"
    s = R.estado(abriu_antes, respondida, 2, date(2026, 11, 13))
    assert s["situacao"] == "concluida" and s["sozinha"] and s["rotulo"] == "Concluída sozinha"


def _d(did, de, para, setor, estado):
    return {"demanda_id": did, "de_hmac": de, "para_hmac": para, "para_setor_id": setor, "titulo": did, "de_nome": de,
            "estado": estado}


def test_avisos_de_quem_pediu_de_quem_recebe_e_do_setor():
    hoje = date(2026, 11, 12)
    nova = R.estado(ABRIU, [], 5, hoje)
    falta1 = R.estado(ABRIU, [_ev("em_analise", "2026-11-11T14:00:00Z")], 2, hoje)
    vencida = R.estado({"registrado_em": "2026-11-05T13:00:00Z"}, [], 2, hoje)
    respondida = R.estado(ABRIU, [_ev("respondeu", "2026-11-12T12:00:00Z")], 2, hoje)
    aguardando = R.estado(ABRIU, [_ev("pediu_informacao", "2026-11-12T12:00:00Z")], 2, hoje)
    lista = [_d("d1", "ana", "eu", 2, nova), _d("d2", "ana", "eu", 2, falta1), _d("d3", "ana", "bia", 2, vencida),
             _d("d4", "eu", "ana", 7, respondida), _d("d5", "eu", "ana", 7, aguardando), _d("d6", "ana", "bia", 9, vencida)]
    meus = {a["demanda_id"]: a["tipo"] for a in R.avisos(lista, "eu", 2, hoje)}
    assert meus == {"d1": "nova", "d2": "prazo", "d3": "vencida", "d4": "respondida", "d5": "informacao"}
    assert [a["demanda_id"] for a in R.avisos(lista, "eu", 2, hoje)][0] == "d3"        # a vencida primeiro
    assert {a["demanda_id"] for a in R.avisos(lista, "outra", 3, hoje)} == set()


# ── o livro, a gravação e a lista ────────────────────────────────────────────────────────────────────────────────────
import io  # noqa: E402

import pytest  # noqa: E402
from test_campo_visao import _aba, banco  # noqa: E402,F401  (banco é fixture)

from nexus.auth import setor_telas as ST  # noqa: E402
from nexus.cadastro import fracttal_pessoal as FP  # noqa: E402
from nexus.cadastro import setores as S  # noqa: E402
from nexus.campo import visao  # noqa: E402
from nexus.comando import demandas as D  # noqa: E402
from nexus.dados import catalogo, explica  # noqa: E402

ANA = {"email": "ana@exemplo.test", "nome": "Ana Souza"}            # Supervisão de Campo (setor 2)
JU = {"email": "juliana@exemplo.test", "nome": "Juliana Prado"}     # Performance (setor 1)
BRUNO = {"email": "bruno@exemplo.test", "nome": "Bruno Lima"}       # Performance (setor 1)
SEM = {"email": "sem@exemplo.test", "nome": "Sem Setor"}            # sem setor
PDF = b"%PDF-1.4\n" + b"x" * 200


def _h(email):
    from nexus.cadastro.ligacao_campo import codigo_da_pessoa
    from test_campo_visao import CHAVE
    return codigo_da_pessoa(CHAVE, email).lower()


@pytest.fixture
def cena(app, banco, tmp_path, monkeypatch):
    """Dois setores (Performance = 1, Supervisão de Campo = 2), três pessoas com setor e uma sem; OS 18421 na Altair (1) e
    OS 18500 na Coração 1 (3); o tema "Dado que não bate" (2 dias úteis) na Performance."""
    app.config["NEXUS_DADOS"] = str(tmp_path / "dados")
    cfg, base = app.config, "http://pg.falso"
    with app.app_context():
        S.criar("Performance", cfg, base, banco)
        S.criar("Supervisão de Campo", cfg, base, banco)
        S.definir([{"id": 11, "email": JU["email"], "ficha": None, "por": ""},
                   {"id": 13, "email": BRUNO["email"], "ficha": None, "por": ""}], 1, cfg, base, banco)
        S.definir([{"id": 12, "email": ANA["email"], "ficha": None, "por": ""}], 2, cfg, base, banco)
    monkeypatch.setattr(FP, "ler_pessoal", lambda forcar=False, ler=None: {"pessoas": [
        {"id": 11, "nome": JU["nome"]}, {"id": 12, "nome": ANA["nome"]}, {"id": 13, "nome": BRUNO["nome"]},
        {"id": 14, "nome": SEM["nome"]}], "lido_em": 1, "erro": ""})
    _aba(banco, "nexus_os", "fato_tarefa_os", [
        {"os": 18421, "usina_id": 1, "tipo_tarefa": "corretiva", "status_os": "2"},
        {"os": 18500, "usina_id": 3, "tipo_tarefa": "preventiva", "status_os": "1"}])
    visao.limpar()
    ST.limpar()
    D.limpar()
    with app.test_request_context():
        tema = D.salvar_tema(1, "Dado que não bate", 2, JU)
    D.limpar()
    yield {"tema": tema["tema_id"], "banco": banco}
    D.limpar()
    ST.limpar()


def _form(cena, **kw):
    f = {"para_hmac": _h(JU["email"]), "para_setor_id": "1", "tema_id": cena["tema"], "titulo": "Coração 2 sem meta",
         "descricao": "A Coração 2 não aparece no registro mestre e a meta dela não sai.", "usinas": ["1"],
         "os": "18421", "novo_id": "d00000000001"}
    f.update(kw)
    return f


def test_o_livro_esta_no_catalogo_antes_da_1a_gravacao():
    l = catalogo.LIVRO_POR_NOME[D.LIVRO]
    assert l.abas == (D.ABA_TEMA, D.ABA_DEMANDA, D.ABA_USINA, D.ABA_EVENTO) and l.so_cresce == l.abas
    for fid, aba, chave in (("demanda", D.ABA_DEMANDA, "demanda_id"), ("demanda_usina", D.ABA_USINA, "id"),
                            ("evento_demanda", D.ABA_EVENTO, "id")):
        f = catalogo.POR_ID[fid]
        assert f.livro == f"{D.LIVRO} · {aba}" and f.chave == (chave,) and f.tipo == "sem_medida"
        assert fid in explica.RESUMO and fid in explica.PARA_QUE


def test_o_tema_do_setor_vai_cifrado_e_vale_a_ultima_versao(app, cena):
    with app.test_request_context():
        tid = cena["tema"]
        assert [(t["nome"], t["prazo_dias_uteis"]) for t in D.temas(1)] == [("Dado que não bate", 2)]
        D.salvar_tema(1, "Dado que não bate", 3, JU, tema_id=tid)
        D.salvar_tema(1, "Relatório do cliente", 3, BRUNO)
        rel = [t for t in D.temas(1) if t["nome"] == "Relatório do cliente"][0]["tema_id"]
        D.salvar_tema(1, "Relatório do cliente", 3, BRUNO, tema_id=rel, ativo=False)
        assert [(t["nome"], t["prazo_dias_uteis"]) for t in D.temas(1)] == [("Dado que não bate", 3)]
        assert len(D.temas(1, so_ativos=False)) == 2
        assert "Dado" not in str(cena["banco"].linhas(D.LIVRO, D.ABA_TEMA))
        for prazo in (0, 31):
            with pytest.raises(D.Recusada, match="dias úteis"):
                D.salvar_tema(1, "Outro", prazo, JU)
        with pytest.raises(D.Recusada, match="outro setor"):
            D.salvar_tema(2, "Dado que não bate", 2, ANA, tema_id=tid)


def test_abrir_grava_cifrado_e_o_segundo_envio_nao_duplica(app, cena):
    with app.test_request_context():
        d = D.abrir(_form(cena, usinas=["1", "3"], os="18421"), [], ANA)
        D.abrir(_form(cena, usinas=["1", "3"], os="18421"), [], ANA)              # o duplo clique
    linhas = cena["banco"].linhas(D.LIVRO, D.ABA_DEMANDA)
    assert len(linhas) == 1 and linhas[0]["demanda_id"] == d["demanda_id"] == "d00000000001"
    assert linhas[0]["para_hmac"] == _h(JU["email"]) and linhas[0]["de_hmac"] == _h(ANA["email"])
    assert int(linhas[0]["prazo_dias_uteis"]) == 2 and int(linhas[0]["os"]) == 18421
    assert int(linhas[0]["de_setor_id"]) == 2 and int(linhas[0]["para_setor_id"]) == 1
    texto = str(linhas)
    assert "Coração 2" not in texto and "Ana" not in texto and "Juliana" not in texto
    assert sorted(int(u["usina_id"]) for u in cena["banco"].linhas(D.LIVRO, D.ABA_USINA)) == [1, 3]


def test_a_os_tem_de_ser_da_usina_escolhida(app, cena):
    with app.test_request_context():
        with pytest.raises(D.Recusada, match="OS 18500"):
            D.abrir(_form(cena, usinas=["1"], os="18500"), [], ANA)
        assert [o["os"] for o in D.os_das_usinas({1})] == [18421]
    assert not cena["banco"].linhas(D.LIVRO, D.ABA_DEMANDA)


def test_destinatario_sem_setor_ou_tema_de_outro_setor_recusa(app, cena):
    with app.test_request_context():
        with pytest.raises(D.Recusada, match="não tem setor"):
            D.abrir(_form(cena, para_hmac=_h(SEM["email"])), [], ANA)
        with pytest.raises(D.Recusada, match="não é do setor"):
            D.abrir(_form(cena, para_setor_id="2"), [], ANA)
        with pytest.raises(D.Recusada, match="temas de Performance"):
            D.abrir(_form(cena, tema_id="m00000000099"), [], ANA)
        with pytest.raises(D.Recusada, match="login"):
            D.abrir(_form(cena), [], {})
    assert not cena["banco"].linhas(D.LIVRO, D.ABA_DEMANDA)


def test_o_papel_e_a_vez_de_cada_passo(app, cena):
    with app.test_request_context():
        did = D.abrir(_form(cena, os=""), [], ANA)["demanda_id"]
        with pytest.raises(D.Recusada, match="quem recebeu"):
            D.registrar(did, "respondeu", "ok", ANA)                  # quem pediu não responde
        with pytest.raises(D.Recusada, match="quem pediu"):
            D.registrar(did, "concluiu", "", JU)                     # quem recebeu não conclui
        with pytest.raises(D.Recusada, match="não vale agora"):
            D.registrar(did, "concluiu", "", ANA)                    # concluir o que não foi respondido
        D.registrar(did, "em_analise", "", JU)
        D.registrar(did, "pediu_informacao", "Qual usina?", JU)
        D.registrar(did, "informou", "A Coração 2.", ANA)
        D.registrar(did, "respondeu", "Faltava o de-para; ligado.", JU, "e00000000001")
        D.registrar(did, "respondeu", "Faltava o de-para; ligado.", JU, "e00000000001")    # o duplo clique
        with pytest.raises(D.Recusada, match="justificativa"):
            D.registrar(did, "devolveu", "", ANA)
        D.registrar(did, "devolveu", "Ainda não aparece a meta.", ANA)
        D.registrar(did, "respondeu", "Agora sim.", JU)
        D.registrar(did, "concluiu", "", ANA)
        with pytest.raises(D.Recusada, match="concluída"):
            D.registrar(did, "respondeu", "de novo", JU)
    evs = [e["evento"] for e in cena["banco"].linhas(D.LIVRO, D.ABA_EVENTO)]
    assert evs == ["em_analise", "pediu_informacao", "informou", "respondeu", "devolveu", "respondeu", "concluiu"]
    assert "de-para" not in str(cena["banco"].linhas(D.LIVRO, D.ABA_EVENTO))


def test_anexo_fora_do_limite_recusa_a_demanda_inteira(app, cena):
    with app.test_request_context():
        with pytest.raises(D.Recusada):
            D.abrir(_form(cena), [(f"a{i}.pdf", io.BytesIO(PDF)) for i in range(6)], ANA)
        assert not cena["banco"].linhas(D.LIVRO, D.ABA_DEMANDA)
        d = D.abrir(_form(cena), [("laudo.pdf", io.BytesIO(PDF))], ANA)
        D.limpar()
        caminho, a = D.arquivo(d["demanda_id"], 1)
        assert caminho.read_bytes() == PDF and a["nome"] == "laudo.pdf" and caminho.name == "1.pdf"


def test_a_lista_decifra_e_as_tres_abas(app, cena):
    with app.test_request_context():
        D.abrir(_form(cena), [], ANA)
        D.abrir(_form(cena, para_hmac=_h(BRUNO["email"]), titulo="Outra", novo_id="d00000000002"), [], ANA)
        D.limpar()
        lst = D.lista(date(2026, 11, 12))
        d1 = next(d for d in lst if d["demanda_id"] == "d00000000001")
        assert (d1["de_nome"], d1["para_nome"], d1["titulo"], d1["tema_nome"]) == (
            "Ana Souza", "Juliana Prado", "Coração 2 sem meta", "Dado que não bate")
        assert d1["inicio"].startswith("A Coração 2 não aparece no") and d1["de_setor_nome"] == "Supervisão de Campo"
        assert d1["usinas"] == [(1, "Altair")] and d1["os"] == 18421
        assert [d["demanda_id"] for d in D.da_aba(lst, "para", _h(JU["email"]), 1)] == ["d00000000001"]
        assert {d["demanda_id"] for d in D.da_aba(lst, "setor", _h(JU["email"]), 1)} == {"d00000000001", "d00000000002"}
        assert {d["demanda_id"] for d in D.da_aba(lst, "pedi", _h(ANA["email"]), 2)} == {"d00000000001", "d00000000002"}
        assert D.filtrar(lst, "abertas", pessoa=_h(BRUNO["email"]))[0]["demanda_id"] == "d00000000002"
        assert D.filtrar(lst, "concluidas") == []


# ── as telas ─────────────────────────────────────────────────────────────────────────────────────────────────────────
import re  # noqa: E402

CAIXA = "/t/comando/caixa-de-entrada"


def _cliente(app, pessoa):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logado=True, admin=False, usuario=dict(pessoa))
    return c


def _codigo(html):
    return html.split('name="codigo" value="', 1)[1].split('"', 1)[0]


def _linha(html, did):
    """O <li> da demanda na 1ª aba em que aparece."""
    return html.split(f'data-dm-linha="{did}"', 1)[1].split("</li>", 1)[0]


def _det(html, did):
    return html.split(f'data-dm-det="{did}"', 1)[1].split("</article>", 1)[0]


def _abrir_pela_api(app, cena, **kw):
    with app.test_request_context():
        d = D.abrir(_form(cena, **kw), [], ANA)
    D.limpar()
    return d["demanda_id"]


def test_a_caixa_mostra_a_demanda_para_quem_recebe_quem_pediu_e_o_setor(app, cena):
    did = _abrir_pela_api(app, cena)
    html = _cliente(app, JU).get(CAIXA).get_data(as_text=True)
    assert "Demandas entre setores" in html
    l = _linha(html, did)
    # o foco: o nome de quem pediu, o setor dele, o título e as primeiras palavras; o tema uma vez só (Levi, 11/11)
    assert "Ana Souza" in l and "Supervisão de Campo" in l and "Coração 2 sem meta" in l
    assert "A Coração 2 não aparece no…" in l and l.count("Dado que não bate") == 1
    assert "Faltam" in l and "dm-s-nova" in l
    det = _det(html, did)
    assert 'data-os-folio="18421"' in det and "Altair" in det and det.count("Dado que não bate") == 1
    assert 'value="respondeu"' in det and 'value="pediu_informacao"' in det and 'value="em_analise"' in det
    assert 'value="concluiu"' not in det
    # quem pediu vê em "Que eu pedi", sem os botões de quem recebe
    html = _cliente(app, ANA).get(CAIXA + "?dem=pedi").get_data(as_text=True)
    assert "Para Juliana Prado" in _linha(html, did) and 'value="respondeu"' not in _det(html, did)
    # o colega do setor vê em "Do meu setor" e não responde no lugar dela
    html = _cliente(app, BRUNO).get(CAIXA).get_data(as_text=True)
    assert did in html and "Quem responde é Juliana Prado" in _det(html, did) and 'value="respondeu"' not in html
    # quem não pediu, não recebeu e não é do setor não vê
    assert "Coração 2 sem meta" not in _cliente(app, SEM).get(CAIXA).get_data(as_text=True)


def test_a_nova_demanda_pela_tela_grava_uma_vez_e_o_anexo_so_para_quem_ve(app, cena):
    c = _cliente(app, ANA)
    html = c.get(CAIXA).get_data(as_text=True)
    assert 'id="dm-nova"' in html and "/demandas/pessoas" in html
    # quem recebe vem ao abrir o formulário (a Caixa não lê o Fracttal ao abrir), sem quem pede
    ps = c.get(CAIXA + "/demandas/pessoas").get_json()
    assert ps["ok"] and [(p["nome"], p["setor_nome"]) for p in ps["pessoas"]] == [
        ("Bruno Lima", "Performance"), ("Juliana Prado", "Performance")]
    f = _form(cena)
    dados = dict(f, codigo=_codigo(html), usinas="1", anexos=(io.BytesIO(PDF), "laudo.pdf"))
    r = c.post(CAIXA + "/demandas/nova", data=dados, content_type="multipart/form-data")
    assert r.status_code == 303 and r.headers["Location"].endswith(f"?dem=pedi&d={f['novo_id']}#demandas")
    assert len(cena["banco"].linhas(D.LIVRO, D.ABA_DEMANDA)) == 1
    # outro site e o formulário vencido não gravam
    c.post(CAIXA + "/demandas/nova", data=dict(_form(cena, novo_id="d00000000077"), codigo=_codigo(html)),
           headers={"Sec-Fetch-Site": "cross-site"})
    c.post(CAIXA + "/demandas/nova", data=dict(_form(cena, novo_id="d00000000078"), codigo="outro"))
    assert len(cena["banco"].linhas(D.LIVRO, D.ABA_DEMANDA)) == 1
    url = f"{CAIXA}/demandas/{f['novo_id']}/anexo/1"
    r = _cliente(app, BRUNO).get(url)                       # o setor de quem recebe vê
    assert r.status_code == 200 and r.data == PDF
    assert _cliente(app, SEM).get(url).status_code == 404
    # a recusa volta com o motivo e não grava
    html = c.get(CAIXA).get_data(as_text=True)
    c.post(CAIXA + "/demandas/nova", data=dict(_form(cena, os="18500", novo_id="d00000000079"), codigo=_codigo(html)))
    html = c.get(CAIXA).get_data(as_text=True)
    assert "A OS 18500 não é de nenhuma das usinas escolhidas" in html
    assert len(cena["banco"].linhas(D.LIVRO, D.ABA_DEMANDA)) == 1


def test_os_passos_pela_tela_no_papel_certo(app, cena):
    did = _abrir_pela_api(app, cena)
    ju, ana = _cliente(app, JU), _cliente(app, ANA)
    cod = _codigo(ju.get(CAIXA).get_data(as_text=True))
    r = ju.post(f"{CAIXA}/demandas/{did}/passo", data={"codigo": cod, "acao": "respondeu", "texto": "Ligado.",
                                                       "aba": "para", "novo_id": "e00000000001"})
    assert r.status_code == 303 and r.headers["Location"].endswith(f"?dem=para&d={did}#demandas")
    cod_ana = _codigo(ana.get(CAIXA).get_data(as_text=True))
    ju.post(f"{CAIXA}/demandas/{did}/passo", data={"codigo": cod, "acao": "concluiu", "aba": "para"})   # não é dela
    html = ju.get(CAIXA).get_data(as_text=True)
    assert "Esse passo é de quem pediu a demanda. Nada foi gravado." in html
    html = ana.get(CAIXA + "?dem=pedi&d=" + did).get_data(as_text=True)
    det = _det(html, did)
    assert 'value="concluiu"' in det and 'value="devolveu"' in det and "conclui sozinha em" in det
    ana.post(f"{CAIXA}/demandas/{did}/passo", data={"codigo": cod_ana, "acao": "concluiu", "aba": "pedi"})
    assert [e["evento"] for e in cena["banco"].linhas(D.LIVRO, D.ABA_EVENTO)] == ["respondeu", "concluiu"]
    html = ana.get(CAIXA + "?dem=pedi&d=" + did).get_data(as_text=True)
    assert 'data-f="concluidas"' in html and "dm-s-concluida" in _linha(html, did)


def test_as_os_da_usina_para_o_formulario(app, cena):
    j = _cliente(app, ANA).get(CAIXA + "/demandas/os?usinas=1,3").get_json()
    assert j["ok"] and [o["os"] for o in j["os"]] == [18500, 18421]
    assert j["os"][1]["rotulo"] == "OS 18421 · corretiva"
    assert _cliente(app, ANA).get(CAIXA + "/demandas/os?usinas=").get_json()["os"] == []


def test_os_temas_do_setor_cada_setor_mexe_nos_seus(app, cena):
    """Desde 13/11/2026 os temas são uma aba das demandas na Caixa de entrada (Levi: "eu gostaria que temas por setor fosse
    mais uma aba do demanda entre setores [...] E aí você tira o tema do setor na barra lateral")."""
    c = _cliente(app, JU)
    r = c.get("/t/comando/temas-do-setor")                                # o endereço de antes leva à aba
    assert r.status_code == 302 and r.headers["Location"].endswith("/t/comando/caixa-de-entrada?dem=temas#demandas")
    html = c.get(CAIXA + "?dem=temas").get_data(as_text=True)
    assert 'aria-selected="true" data-dm-aba="temas"' in html and '<section class="dm dm--temas"' in html
    painel = html.split('id="dm-painel-temas"', 1)[1].split("</table>", 1)[0]
    assert "Dado que não bate" in painel and "ao setor Performance" in painel and " hidden>" not in painel.split(">", 1)[0] + ">"
    # o campo do tema não se chama `nome` e vai sem o preenchimento automático (12/11/2026, Levi: "o campo que aparece
    # quando vou digitar está mal formatado"): o navegador abria a lista do que foi digitado em outros campos `nome`
    tabela = html.split('<table class="dm-temas">', 1)[1].split("</table>", 1)[0]
    assert 'name="nome"' not in tabela and tabela.count('name="tema"') == 2          # o tema que existe e o novo
    assert tabela.count('autocomplete="off"') == 4 and 'name="tema" maxlength="60" required autocomplete="off"' in tabela
    r = c.post("/t/comando/temas-do-setor/salvar", data={"codigo": _codigo(html), "setor_id": "1",
                                                         "tema": "Relatório do cliente", "prazo": "3"})
    assert r.status_code == 303 and r.headers["Location"].endswith("/t/comando/caixa-de-entrada?dem=temas#demandas")
    assert sorted(t["nome"] for t in D.temas(1)) == ["Dado que não bate", "Relatório do cliente"]
    # a página que ficou aberta de antes ainda manda `nome`: grava do mesmo jeito
    html = c.get(CAIXA + "?dem=temas").get_data(as_text=True)
    assert c.post("/t/comando/temas-do-setor/salvar", data={"codigo": _codigo(html), "setor_id": "1",
                                                            "nome": "Curva de geração", "prazo": "2"}).status_code == 303
    assert "Curva de geração" in [t["nome"] for t in D.temas(1)]
    # o tema do outro setor, não
    assert c.post("/t/comando/temas-do-setor/salvar", data={"codigo": _codigo(html), "setor_id": "2",
                                                            "nome": "Extintores", "prazo": "2"}).status_code == 403
    html = c.get(CAIXA + "?dem=temas").get_data(as_text=True)
    assert "Tema salvo." in html and "Relatório do cliente" in html and "Curva de geração" in html
    # quem não tem setor vê o aviso, sem o formulário
    html = _cliente(app, SEM).get(CAIXA + "?dem=temas").get_data(as_text=True)
    assert "ainda não tem setor no Nexus" in html and "temas-do-setor/salvar" not in html


# ── o sininho ────────────────────────────────────────────────────────────────────────────────────────────────────────
def _sino(html):
    return html.split('class="sino-topo sino-dem"', 1)[1].split("</details>", 1)[0]


def test_o_sininho_avisa_quem_recebe_quem_pediu_e_o_setor_na_vencida(app, cena):
    from datetime import timedelta
    did = _abrir_pela_api(app, cena)
    s = _sino(_cliente(app, JU).get(CAIXA).get_data(as_text=True))
    assert 'class="sino-n sino-n--dem">1<' in s and ">Nova</span> Coração 2 sem meta" in s and "de Ana Souza" in s
    assert f"/t/comando/caixa-de-entrada?dem=para&amp;d={did}#demandas" in s
    # o colega do setor só é avisado na vencida; quem não tem nada a ver, nada
    assert "Nenhuma demanda pede você agora." in _sino(_cliente(app, BRUNO).get(CAIXA).get_data(as_text=True))
    with app.test_request_context():
        depois = date.today() + timedelta(days=10)
        av = D.avisos_do_sino(_h(BRUNO["email"]), 1, hoje=depois)
        assert [(a["tipo"], a["para_nome"]) for a in av] == [("vencida", "Juliana Prado")]
        assert D.avisos_do_sino(_h(SEM["email"]), None, hoje=depois) == []
        D.registrar(did, "respondeu", "Ligado.", JU)
    D.limpar()
    s = _sino(_cliente(app, ANA).get(CAIXA).get_data(as_text=True))
    assert ">Respondida</span> Coração 2 sem meta" in s and "para Juliana Prado" in s and "dem=pedi" in s
    # o administrador pela senha (sem pessoa) não tem o sininho das demandas
    c = app.test_client()
    with c.session_transaction() as ss:
        ss.update(logado=True, admin=True)
    assert "sino-dem" not in c.get(CAIXA).get_data(as_text=True)


# ── o que a revisão de 12/11/2026 apontou ────────────────────────────────────────────────────────────────────────────
def test_a_pausada_nao_vence_hoje_nem_entra_no_vencem_ate_amanha():
    d = {"registrado_em": "2026-11-16T12:00:00.000Z", "para_hmac": "j", "de_hmac": "a", "para_setor_id": 1}
    pausa = [_ev("pediu_informacao", "2026-11-18T12:00:00.000Z")]            # no dia do prazo (2 dias úteis)
    for dia in (18, 19, 23):
        e = R.estado(d, pausa, 2, date(2026, 11, dia))
        assert e["situacao"] == "aguardando" and e["dias_restantes"] == 0
        x = dict(d, demanda_id="d1", estado=e)
        assert R.avisos([x], "j", 1, date(2026, 11, dia)) == []
        assert not D.filtrar([x], "vencem")


def test_o_passo_posto_no_banco_por_outra_pessoa_nao_vale(app, cena):
    did = _abrir_pela_api(app, cena)
    banco = cena["banco"]
    with app.test_request_context():
        D.registrar(did, "respondeu", "Ligado.", JU)
        evs = banco.linhas(D.LIVRO, D.ABA_EVENTO)
        falso = dict(evs[0], id="e00000000999", evento="concluiu", pessoa_hmac=_h(BRUNO["email"]))
        _aba_extra = [{k: falso.get(k) for k in D.CAB_EVENTO}]
        D._publicar(dict(D._ler_abas(), **{D.ABA_EVENTO: evs + _aba_extra}))
        d = next(x for x in D.lista() if x["demanda_id"] == did)
    assert d["estado"]["situacao"] == "finalizada"                       # o "concluiu" do Bruno não é de quem pediu


def test_a_gravacao_que_entrou_e_respondeu_com_erro_fica_com_os_anexos(app, cena, monkeypatch):
    original = D._publicar

    def grava_e_falha(t):
        original(t)
        raise TimeoutError("a resposta não veio")
    monkeypatch.setattr(D, "_publicar", grava_e_falha)
    with app.test_request_context():
        d = D.abrir(_form(cena), [("laudo.pdf", io.BytesIO(PDF))], ANA)
        monkeypatch.setattr(D, "_publicar", original)
        D.limpar()
        assert D.arquivo(d["demanda_id"], 1)[0].read_bytes() == PDF
    assert len(cena["banco"].linhas(D.LIVRO, D.ABA_DEMANDA)) == 1


def test_a_leitura_de_antes_da_gravacao_nao_fica_na_copia(app, cena, monkeypatch):
    original = D._ler_abas

    def lenta():
        t = original()
        D.limpar()                                                        # uma gravação terminou no meio da leitura
        return t
    monkeypatch.setattr(D, "_ler_abas", lenta)
    with app.test_request_context():
        D.limpar()
        assert D.ler()["temas"] and "livro" not in D._CACHE


def test_o_tema_novo_no_duplo_clique_e_um_so(app, cena):
    c = _cliente(app, JU)
    html = c.get(CAIXA + "?dem=temas").get_data(as_text=True)
    novo = html.split('id="dm-painel-temas"', 1)[1].split('name="novo_id" value="', 1)[1].split('"', 1)[0]
    dados = {"codigo": _codigo(html), "setor_id": "1", "nome": "Relatório do cliente", "prazo": "3", "novo_id": novo}
    c.post("/t/comando/temas-do-setor/salvar", data=dados)
    c.post("/t/comando/temas-do-setor/salvar", data=dados)
    with app.test_request_context():
        assert [t["nome"] for t in D.temas(1)].count("Relatório do cliente") == 1


def test_o_envio_grande_demais_volta_com_o_aviso_e_a_caixa_nao_le_o_fracttal(app, cena, monkeypatch):
    c = _cliente(app, ANA)
    lidas = []
    original = FP.ler_pessoal
    monkeypatch.setattr(FP, "ler_pessoal", lambda forcar=False, ler=None: lidas.append(1) or original())
    html = c.get(CAIXA + "?d=x%22%5D").get_data(as_text=True)          # o ?d= mexido não entra na tela
    assert lidas == [] and 'data-sel=""' in html
    r = c.post(CAIXA + "/demandas/nova", data=dict(_form(cena), codigo=_codigo(html),
                                                  anexos=(io.BytesIO(PDF + b"x" * (17 * 1024 * 1024)), "a.pdf")))
    assert r.status_code == 303
    assert "passam de 15 MB juntos" in c.get(CAIXA).get_data(as_text=True)
    assert not cena["banco"].linhas(D.LIVRO, D.ABA_DEMANDA)


# ── a janela da conversa da usina, por cima do prontuário (13/11/2026) ─────────────────────────────────────────────────
def test_a_janela_da_conversa_da_usina_conversa_pede_a_um_setor_e_lista_as_demandas(app, cena):
    """Levi, 13/11/2026: "essa parte de conversa. A ideia é montar uma caixa de entrada, é isso? Escolher o setor e tudo
    mais. Faça no mesmo modelo de janela. Janela acima, e aí faça algo bem versátil para as pessoas usarem"."""
    c = _cliente(app, ANA)
    JAN = "/t/comando/conversa/usina/1/janela"
    h = c.get(JAN).get_data(as_text=True)
    assert "<html" not in h and "data-pu-cv" in h                                   # um pedaço de página, para a janela
    for k in ("conversa", "pedir", "demandas"):
        assert f'data-pu-seg="{k}"' in h and f'data-pu-seg-painel="{k}"' in h
    # a conversa: o formulário de sempre, voltando à janela, com as áreas à vista
    assert 'name="voltar" value="/t/comando/conversa/usina/1/janela?aba=conversa"' in h
    assert '<details class="ins-outras conv-areas" open>' in h
    # o Pedir a um setor: a Nova demanda com a usina fixa, voltando à janela
    pedir = h.split('data-pu-seg-painel="pedir"', 1)[1].split('data-pu-seg-painel="demandas"', 1)[0]
    assert 'action="/t/comando/caixa-de-entrada/demandas/nova?usina_jan=1"' in pedir and "data-pu-dm-nova" in pedir
    assert 'name="usinas" value="1" data-dm-f-usina-fixa' in pedir and "data-dm-f-busca" not in pedir
    assert 'id="pu-dm-setor"' in pedir and "Dado que não bate" in pedir
    # a demanda enviada pela janela volta à janela, na aba das demandas da usina, e aparece lá
    dados = dict(_form(cena, novo_id="d00000000091"), codigo=_codigo(h))
    r = c.post("/t/comando/caixa-de-entrada/demandas/nova?usina_jan=1", data=dados)
    assert r.status_code == 303 and r.headers["Location"].endswith("/t/comando/conversa/usina/1/janela?aba=demandas")
    h = c.get(JAN + "?aba=demandas").get_data(as_text=True)
    assert "Demanda enviada." in h and "Coração 2 sem meta" in h.split('data-pu-seg-painel="demandas"', 1)[1]
    assert 'aria-selected="true" data-pu-seg="demandas"' in h
    # a mensagem na conversa volta à janela também
    r = c.post("/t/comando/conversa/acao", data={"codigo": _codigo(h), "objeto": "usina:1", "acao": "mensagem",
                                                  "texto": "Inversor 2 parado desde cedo",
                                                  "voltar": "/t/comando/conversa/usina/1/janela?aba=conversa"})
    assert r.status_code == 303 and "/t/comando/conversa/usina/1/janela?aba=conversa" in r.headers["Location"]
    h = c.get(JAN).get_data(as_text=True)
    assert "Inversor 2 parado desde cedo" in h
    # quem não pode ver a demanda não a vê na janela; aberta sozinha no navegador, leva à página da conversa
    assert "Coração 2 sem meta" not in _cliente(app, SEM).get(JAN + "?aba=demandas").get_data(as_text=True)
    r = c.get(JAN, headers={"Sec-Fetch-Dest": "document"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/t/comando/conversa/usina/1")
