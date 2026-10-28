"""A aba Sugestões do Início (Levi, 24/10/2026: "em início quero uma sub aba chamada 'Sugestões'. Vai ter uma tela para a
pessoa sugerir, os administradores verão em lista a pessoa que pediu, o que pediu e anexos ... Bote um limite no tamanho
desses arquivos para não pesar tanto no server").

O que estes testes seguram: a sugestão vai ao livro com o texto e o nome só cifrados e os anexos no disco com nome
neutro; os limites (5 arquivos, 5 MB cada, 15 MB juntos, os tipos e o conteúdo que bate com a extensão) recusam a
sugestão inteira sem gravar nada; a área só entre as torres que a pessoa vê; o 2º envio do mesmo formulário não grava
outra; outro site e formulário vencido não gravam; só o administrador vê a lista e baixa os anexos. Banco falso do
test_campo_visao; nomes fictícios."""
import io
import json

import pytest
from test_campo_visao import banco  # noqa: F401  (fixture)

from nexus.casca import sugestoes as S
from nexus.dados import catalogo, explica

PESSOA = {"email": "fulana@exemplo.test", "nome": "Fulana de Teste", "perfil": ""}
PDF = b"%PDF-1.4\n" + b"x" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"y" * 200
URL = "/?aba=sugestoes"


@pytest.fixture
def dados(app, banco, tmp_path):
    app.config["NEXUS_DADOS"] = str(tmp_path / "dados")
    S.limpar()
    yield tmp_path / "dados"
    S.limpar()


def _cliente(app, admin=False, usuario=PESSOA):
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"] = True
        s["admin"] = admin
        if usuario:
            s["usuario"] = dict(usuario)
    return c


def _codigo(c) -> str:
    html = c.get(URL).get_data(as_text=True)
    return html.split('name="codigo" value="', 1)[1].split('"', 1)[0]


def _form(c, **kw):
    f = {"codigo": _codigo(c), "titulo": "Filtro por usina no relatório", "area": "pcm",
         "descricao": "Hoje o relatório traz todas.\nQueria escolher uma usina."}
    f.update(kw)
    return f


def _arq(nome, dados):
    return (io.BytesIO(dados), nome)


# ── o livro e o disco ────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_sugestao_vai_cifrada_ao_livro_e_o_anexo_ao_disco_com_nome_neutro(app, banco, dados):
    c = _cliente(app)
    r = c.post(URL, data=dict(_form(c), anexos=[_arq("Relatório de julho.pdf", PDF), _arq("tela.png", PNG)]),
               content_type="multipart/form-data")
    assert r.status_code == 302 and r.headers["Location"].endswith("/?aba=sugestoes")
    linhas = banco.linhas(S.LIVRO, S.ABA)
    assert len(linhas) == 1
    x = linhas[0]
    assert x["area"] == "pcm" and x["pessoa_hmac"] and S.ID_RE.fullmatch(x["id"]) and str(x["data_id"]).startswith("20")
    bruto = json.dumps(linhas, ensure_ascii=False, default=str)
    for texto in ("Filtro", "relatório", "Fulana", "fulana@", "Relatório de julho", "tela.png"):
        assert texto not in bruto, texto                     # nada de texto livre, nome nem nome de arquivo em claro
    pasta = dados / "sugestoes" / x["id"]
    assert sorted(p.name for p in pasta.iterdir()) == ["1.pdf", "2.png"]
    assert (pasta / "1.pdf").read_bytes() == PDF
    s = S.lista()[0]
    assert (s["titulo"], s["nome"], s["email"], s["area"]) == ("Filtro por usina no relatório", "Fulana de Teste",
                                                               "fulana@exemplo.test", "pcm")
    assert s["descricao"] == "Hoje o relatório traz todas.\nQueria escolher uma usina."     # as quebras de linha ficam
    assert [(a["nome"], a["imagem"]) for a in s["anexos"]] == [("Relatório de julho.pdf", False), ("tela.png", True)]
    # quem mandou vê o aviso de enviada (e não a lista, que é do administrador)
    html = c.get(URL).get_data(as_text=True)
    assert "Sugestão enviada" in html and "Sugestões recebidas" not in html


def test_o_segundo_envio_do_mesmo_formulario_nao_grava_outra(app, banco, dados):
    c = _cliente(app)
    f = _form(c, novo_id="s0123456789a")
    assert c.post(URL, data=f).status_code == 302
    assert c.post(URL, data=f).status_code == 302
    assert [l["id"] for l in banco.linhas(S.LIVRO, S.ABA)] == ["s0123456789a"]


def test_o_banco_que_recusa_nao_deixa_anexo_orfao_no_disco(app, banco, dados, monkeypatch):
    def falha(*a, **k):
        raise RuntimeError("banco fora")
    monkeypatch.setattr(S.livros, "publicar", falha)
    c = _cliente(app)
    r = c.post(URL, data=dict(_form(c), anexos=[_arq("a.pdf", PDF)]), content_type="multipart/form-data")
    html = r.get_data(as_text=True)
    assert r.status_code == 400 and "Não consegui gravar agora" in html and "anexe os arquivos de novo" in html
    assert not list((dados / "sugestoes").glob("*/*"))
    # o que a pessoa escreveu volta no formulário
    assert "Filtro por usina no relatório" in html


# ── os limites ───────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("anexos,trecho", [
    ([("a.exe", b"MZ" + b"\x00" * 50)], "tipo de arquivo não aceito"),
    ([("falso.pdf", b"MZ\x00\x00 executavel")], "não é .pdf de verdade"),
    ([("falso.png", PDF)], "não é .png de verdade"),
    ([("vazio.txt", b"")], "veio vazio"),
    ([("grande.pdf", b"%PDF-" + b"0" * (5 * 1024 * 1024))], "passa de 5 MB"),
    ([(f"{i}.png", PNG) for i in range(6)], "o limite é 5 por sugestão"),
    ([(f"{i}.pdf", b"%PDF-" + b"0" * (4 * 1024 * 1024)) for i in range(4)], "passam de 15 MB juntos"),
])
def test_anexo_fora_do_limite_recusa_a_sugestao_inteira(app, banco, dados, anexos, trecho):
    c = _cliente(app)
    r = c.post(URL, data=dict(_form(c), anexos=[_arq(n, d) for n, d in anexos]), content_type="multipart/form-data")
    html = r.get_data(as_text=True)
    assert r.status_code == 400 and trecho in html and "Nada foi enviado" in html, html[-600:]
    assert banco.linhas(S.LIVRO, S.ABA) == [] and not (dados / "sugestoes").exists()


def test_os_tipos_aceitos_passam_pelo_conteudo():
    assert S.conteudo_bate(".md", "# Título\n- item".encode())
    assert S.conteudo_bate(".txt", "\ufeffolá".encode("utf-16"))
    assert S.conteudo_bate(".docx", b"PK\x03\x04resto") and not S.conteudo_bate(".docx", b"texto")
    assert S.conteudo_bate(".doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1resto") and not S.conteudo_bate(".doc", b"MZ")
    assert S.conteudo_bate(".jpg", b"\xff\xd8\xff\xe0") and S.conteudo_bate(".webp", b"RIFF\x00\x00\x00\x00WEBPVP8 ")
    assert not S.conteudo_bate(".md", b"MZ\x90\x00\x03\x00")      # executável renomeado para .md
    assert S.nome_seguro("C:\\fakepath\\..\\Plano #2.PDF") == "Plano _2.pdf"


def test_pedido_maior_que_o_teto_nao_e_lido(app, banco, dados):
    c = _cliente(app)
    # 17 MB de corpo (o teto é 15 MB + 1 MB do formulário): recusado pelo tamanho declarado, antes de ler o formulário
    r = c.post(URL, data=dict(_form(c), lastro="0" * (17 * 1024 * 1024)))
    assert r.status_code == 400 and "passam de 15 MB juntos" in r.get_data(as_text=True)
    assert banco.linhas(S.LIVRO, S.ABA) == []


def test_titulo_descricao_e_area_obrigatorios_e_area_so_entre_as_que_a_pessoa_ve(app, banco, dados):
    c = _cliente(app)
    for kw, trecho in (({"titulo": "  "}, "Escreva um título"), ({"descricao": ""}, "Escreva a descrição"),
                       ({"titulo": "x" * 121}, "passou de 120"), ({"area": "inventada"}, "não está entre as que")):
        r = c.post(URL, data=_form(c, **kw))
        assert r.status_code == 400 and trecho in r.get_data(as_text=True), kw
    # sem área (nenhuma em especial) vale
    assert c.post(URL, data=_form(c, area="")).status_code == 302
    assert banco.linhas(S.LIVRO, S.ABA)[0]["area"] is None


def test_a_area_e_so_das_torres_da_pessoa(app, banco, dados, monkeypatch):
    from nexus.auth import setor_telas
    monkeypatch.setattr(setor_telas, "liberadas_do_menu", lambda: {"pcm/quadro", "cos/mesa"})
    c = _cliente(app)
    html = c.get(URL).get_data(as_text=True)
    opcoes = html.split('id="sug-area"', 1)[1].split("</select>", 1)[0]
    assert 'value="pcm"' in opcoes and 'value="cos"' in opcoes and 'value="performance"' not in opcoes
    r = c.post(URL, data=_form(c, area="performance"))
    assert r.status_code == 400 and banco.linhas(S.LIVRO, S.ABA) == []


# ── quem grava e quem lê ─────────────────────────────────────────────────────────────────────────────────────────────
def test_outro_site_e_formulario_vencido_nao_gravam(app, banco, dados):
    c = _cliente(app)
    r = c.post(URL, data=_form(c), headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 400 and "Pedido de outro site" in r.get_data(as_text=True)
    r = c.post(URL, data=_form(c, codigo="velho"))
    assert r.status_code == 400 and "O formulário venceu" in r.get_data(as_text=True)
    assert banco.linhas(S.LIVRO, S.ABA) == []


def test_a_senha_de_administrador_le_mas_nao_manda(app, banco, dados):
    c = _cliente(app, admin=True, usuario=None)
    html = c.get(URL).get_data(as_text=True)
    assert 'name="titulo"' not in html and "Entre com o seu login" in html and "Nenhuma sugestão ainda" in html
    with c.session_transaction() as s:
        s["sugestoes_codigo"] = "abc"
    r = c.post(URL, data={"codigo": "abc", "titulo": "T", "descricao": "D"})
    assert r.status_code == 400 and "Entre com o seu login" in r.get_data(as_text=True)


def test_so_o_administrador_ve_a_lista_e_baixa_os_anexos(app, banco, dados):
    c = _cliente(app)
    c.post(URL, data=dict(_form(c), anexos=[_arq("Plano.pdf", PDF), _arq("print.png", PNG)]),
           content_type="multipart/form-data")
    sid = banco.linhas(S.LIVRO, S.ABA)[0]["id"]
    assert c.get(f"{URL}&anexo={sid}&n=1").status_code == 403
    app.config["NEXUS_ADMINS"] = "chefe@exemplo.test"      # o portão segue a lista de administradores a cada pedido
    adm = _cliente(app, admin=True, usuario={"email": "chefe@exemplo.test", "nome": "Chefe"})
    html = adm.get(URL).get_data(as_text=True)
    assert "Sugestões recebidas (1)" in html and "Fulana de Teste" in html and "fulana@exemplo.test" in html
    assert "Filtro por usina no relatório" in html and "PCM" in html and "Plano.pdf" in html
    assert f"anexo={sid}&amp;n=2" in html
    r = adm.get(f"{URL}&anexo={sid}&n=1")
    assert r.status_code == 200 and r.data == PDF and r.mimetype == "application/pdf"
    assert "attachment" in r.headers["Content-Disposition"] and "Plano.pdf" in r.headers["Content-Disposition"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    r = adm.get(f"{URL}&anexo={sid}&n=2")
    assert r.status_code == 200 and r.mimetype == "image/png" and "inline" in r.headers["Content-Disposition"]
    for ruim in (f"anexo={sid}&n=9", "anexo=../../etc&n=1", f"anexo={sid}&n=x", "anexo=s000000000000&n=1"):
        assert adm.get(f"{URL}&{ruim}").status_code == 404, ruim


def test_sem_as_chaves_a_tela_diz_e_nao_mostra_formulario(app, banco, dados):
    app.config["NEXUS_CHAVE_CADASTRO"] = ""
    html = _cliente(app).get(URL).get_data(as_text=True)
    assert "ainda não grava sugestões" in html and "NEXUS_CHAVE_CADASTRO" in html and 'name="titulo"' not in html


# ── as abas e o catálogo ─────────────────────────────────────────────────────────────────────────────────────────────
def test_as_tres_abas_do_inicio_e_o_post_so_na_de_sugestoes(app, banco, dados):
    c = _cliente(app)
    for url in ("/", "/?aba=atualizacoes", URL):
        nav = c.get(url).get_data(as_text=True).split('class="gc-subabas"', 1)[1].split("</nav>", 1)[0]
        assert "Visão geral" in nav and "Atualizações" in nav and ">Sugestões<" in nav, url
    assert 'aria-current="page">Sugestões' in c.get(URL).get_data(as_text=True)
    assert c.post("/", data={}).status_code == 405
    assert c.post("/?aba=atualizacoes", data={}).status_code == 405


def test_o_livro_esta_no_catalogo_antes_da_1a_gravacao():
    l = catalogo.LIVRO_POR_NOME[S.LIVRO]
    # 28/10/2026: a 2ª aba, a do status, registrada antes da 1ª mudança; o livro já existe (a 1ª sugestão foi mandada)
    assert l.abas == (S.ABA, S.ABA_STATUS) and l.so_cresce == (S.ABA, S.ABA_STATUS) and l.no_banco
    st = catalogo.POR_ID["status_sugestao"]
    assert st.livro == f"{S.LIVRO} · {S.ABA_STATUS}" and st.chave == ("id",) and st.chave[0] == S.CAB_STATUS[0]
    assert "status_sugestao" in explica.RESUMO and "status_sugestao" in explica.PARA_QUE
    f = catalogo.POR_ID["sugestao"]
    assert f.livro == f"{S.LIVRO} · {S.ABA}" and f.chave == ("id",) and f.tipo == "sem_medida"
    assert f.chave[0] == S.CAB[0] and "pessoa_id" in S.CAB and "data_id" in S.CAB
    assert "sugestao" in explica.RESUMO and "sugestao" in explica.PARA_QUE


def test_baixar_arquivos_leva_todos_os_anexos_num_zip_so_para_o_administrador(app, banco, dados):
    """Levi, 24/10/2026: "gostaria a opção 'Baixar arquivos' baixa todos os arquivos da sugestão"."""
    import zipfile
    c = _cliente(app)
    c.post(URL, data=dict(_form(c, titulo="Filtro/por usina"), anexos=[_arq("Plano.pdf", PDF), _arq("print.png", PNG),
                                                                       _arq("Plano.pdf", PDF + b"2")]),
           content_type="multipart/form-data")
    sid = banco.linhas(S.LIVRO, S.ABA)[0]["id"]
    assert c.get(f"{URL}&anexo={sid}&n=todos").status_code == 403
    app.config["NEXUS_ADMINS"] = "chefe@exemplo.test"
    adm = _cliente(app, admin=True, usuario={"email": "chefe@exemplo.test", "nome": "Chefe"})
    assert f"anexo={sid}&amp;n=todos" in adm.get(URL).get_data(as_text=True)
    r = adm.get(f"{URL}&anexo={sid}&n=todos")
    assert r.status_code == 200 and r.mimetype == "application/zip"
    assert "attachment" in r.headers["Content-Disposition"] and "Filtro_por usina.zip" in r.headers["Content-Disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.data))
    assert z.namelist() == ["Plano.pdf", "print.png", "Plano (2).pdf"]      # o nome repetido não apaga o outro
    assert z.read("Plano.pdf") == PDF and z.read("Plano (2).pdf") == PDF + b"2" and z.read("print.png") == PNG
    for ruim in ("anexo=s000000000000&n=todos", "anexo=../x&n=todos"):
        assert adm.get(f"{URL}&{ruim}").status_code == 404, ruim


def test_sugestao_sem_anexo_nao_mostra_baixar_arquivos(app, banco, dados):
    c = _cliente(app)
    c.post(URL, data=_form(c))
    app.config["NEXUS_ADMINS"] = "chefe@exemplo.test"
    adm = _cliente(app, admin=True, usuario={"email": "chefe@exemplo.test", "nome": "Chefe"})
    html = adm.get(URL).get_data(as_text=True)
    assert "Filtro por usina no relatório" in html and "Baixar arquivos" not in html
    sid = banco.linhas(S.LIVRO, S.ABA)[0]["id"]
    assert adm.get(f"{URL}&anexo={sid}&n=todos").status_code == 404



# ── 28/10/2026: o status, as Minhas sugestões, a lista recolhida e o contador ──────────────────────────────────────────
ADMIN = {"email": "chefe@exemplo.test", "nome": "Chefe de Teste"}
OUTRA = {"email": "beltrana@exemplo.test", "nome": "Beltrana de Teste", "perfil": ""}


def _admin(app):
    app.config["NEXUS_ADMINS"] = ADMIN["email"]       # o portão segue a lista de administradores a cada pedido
    return _cliente(app, admin=True, usuario=ADMIN)


def _mandar(c, titulo, novo_id):
    assert c.post(URL, data=_form(c, titulo=titulo, novo_id=novo_id)).status_code == 302


def _status(c, sid, status, **kw):
    return c.post(URL + "&acao=status", data=dict({"codigo": _codigo(c), "sugestao": sid, "status": status}, **kw))


def test_o_administrador_muda_o_status_e_a_pessoa_ve_em_minhas_sugestoes(app, banco, dados):
    """Levi, 28/10/2026: "No sugestões recebidas deve ter a opção de mudar o status da solicitação: Iniciada, Em
    verificação e Conclusão" e "Do lado direito tem um espaço para 'Minhas sugestões'"."""
    c = _cliente(app)
    _mandar(c, "Primeira ideia", "s00000000001")
    _mandar(c, "Segunda ideia", "s00000000002")
    _mandar(_cliente(app, usuario=OUTRA), "Ideia da outra", "s00000000003")
    adm = _admin(app)
    r = _status(adm, "s00000000001", "verificacao")
    assert r.status_code == 302 and r.headers["Location"].endswith("#sug-s00000000001")
    linhas = banco.linhas(S.LIVRO, S.ABA_STATUS)
    assert [(l["sugestao_id"], l["status"]) for l in linhas] == [("s00000000001", "verificacao")]
    assert linhas[0]["pessoa_hmac"] and "Chefe" not in str(linhas[0])                # quem mudou, só cifrado
    assert len(banco.linhas(S.LIVRO, S.ABA)) == 3                                     # as sugestões ficaram
    _status(adm, "s00000000001", "verificacao")                                       # a mesma de novo: não grava
    assert len(banco.linhas(S.LIVRO, S.ABA_STATUS)) == 1
    _status(adm, "s00000000001", "concluida")
    assert [l["status"] for l in banco.linhas(S.LIVRO, S.ABA_STATUS)] == ["verificacao", "concluida"]
    # a pessoa vê as dela, com o status; não vê a da outra pessoa
    html = c.get(URL).get_data(as_text=True)
    minhas = html.split('class="sug-minhas"', 1)[1].split("</aside>", 1)[0]
    assert "Primeira ideia" in minhas and "Segunda ideia" in minhas and "Ideia da outra" not in minhas
    assert "Concluída" in minhas and "Nova" in minhas
    assert "Sugestões recebidas" not in html


def test_a_lista_recebida_vem_recolhida_e_a_concluida_por_ultimo(app, banco, dados):
    c = _cliente(app)
    _mandar(c, "Ideia antiga", "s00000000001")
    _mandar(c, "Ideia concluida", "s00000000002")
    adm = _admin(app)
    _status(adm, "s00000000002", "concluida")
    html = adm.get(URL).get_data(as_text=True)
    lista = html.split('class="sug-lista"', 1)[1].split("</ol>", 1)[0]
    assert '<details class="sug-dobra">' in lista and "<details class=\"sug-dobra\" open" not in lista
    assert lista.index("Ideia antiga") < lista.index("Ideia concluida")
    assert 'action="/?aba=sugestoes&amp;acao=status"' in lista and 'name="status"' in lista
    assert "Status mudado para Concluída" in html                              # o aviso da troca, uma vez
    assert "Status mudado" not in adm.get(URL).get_data(as_text=True)


def test_so_o_administrador_muda_e_o_formulario_vencido_nao_grava(app, banco, dados):
    c = _cliente(app)
    _mandar(c, "Ideia", "s00000000001")
    assert _status(c, "s00000000001", "concluida").status_code == 403
    adm = _admin(app)
    _status(adm, "s00000000001", "concluida", codigo="velho")
    _status(adm, "s00000000001", "inventado")
    _status(adm, "s99999999999", "concluida")
    assert banco.linhas(S.LIVRO, S.ABA_STATUS) == []
    html = adm.get(URL).get_data(as_text=True)
    assert "O status não mudou" in html


def test_o_contador_ao_lado_de_sugestoes(app, banco, dados):
    """Levi, 28/10/2026: "Tem que ter um contador no cabeçalho ao lado de Sugestões mostrando quantas sugestões ainda
    não estão concluídas!". O administrador conta todas; a pessoa, as dela."""
    c = _cliente(app)
    _mandar(c, "Uma", "s00000000001")
    _mandar(c, "Duas", "s00000000002")
    _mandar(_cliente(app, usuario=OUTRA), "Da outra", "s00000000003")
    adm = _admin(app)
    _status(adm, "s00000000001", "concluida")
    S.limpar()

    def numero(cli, url="/"):
        nav = cli.get(url).get_data(as_text=True).split('class="gc-subabas"', 1)[1].split("</nav>", 1)[0]
        return nav.split('class="sug-contador"', 1)[1].split(">", 1)[1].split("<", 1)[0] if "sug-contador" in nav else None
    assert numero(adm) == "2" and numero(adm, "/?aba=atualizacoes") == "2" and numero(adm, URL) == "2"
    assert numero(c) == "1"                                       # só a dela que falta concluir
    _status(adm, "s00000000002", "concluida")
    S.limpar()
    assert numero(c) is None                                      # tudo concluído: sem número
    assert S.abertas({"linhas": [{"id": "s00000000009"}], "status": []}) == 1


def test_o_contador_nunca_segura_o_inicio_sem_banco(app, logado):
    """Sem o banco falso no teste (e, no servidor, sem a cópia), a aba sai sem número e o Início abre."""
    S.limpar()
    r = logado.get("/")
    assert r.status_code == 200 and "sug-contador" not in r.get_data(as_text=True)
