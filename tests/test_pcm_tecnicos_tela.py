"""A tela Técnicos por usina (17/10/2026, PCM → Técnicos por usina; rotas em nexus/pcm/telas.py).

O que estes testes seguram: quem vê (setores PCM e Responsáveis UFV) e quem edita (administrador e setor PCM; a carga
inicial só o administrador), pôr e tirar com a tela voltando filtrada, a carga inicial só com o livro vazio, o reenviar
ao App, a página sem e-mail de ninguém e o histórico da usina. O banco é o falso do `test_pcm_tecnicos_usina`."""
import json

from nexus.pcm import atribuicoes as A
from test_pcm_publicar import _no_setor, _pessoa
from test_pcm_tecnicos_usina import F1, PESSOA, _h, banco  # noqa: F401 (fixture)
from nexus.cadastro import setor_ids as SID

ROTA = "/t/pcm/tecnicos-por-usina"


def _decisoes(app):
    return A.ler(app.config, forcar=True)["decisoes"]


def _atuais(app):
    return A.atuais(A.ler(app.config, forcar=True), A.hoje_id())


def test_quem_ve_e_quem_edita(app, banco, monkeypatch):
    c = _pessoa(app)
    por = {"usina_id": "1", "pessoa_id": "10", "acao": "por"}
    _no_setor(monkeypatch, SID.RESPONSAVEL_UFV)
    assert c.get(ROTA).status_code == 200
    assert c.post(ROTA + "/decidir", data=por).status_code == 403
    # quem vê: o portão por setor (desligado nos testes) segue o `Tela.do_setor` da torre
    from nexus.auth import setor_telas as ST
    with app.test_request_context():
        assert "pcm/tecnicos-por-usina" in ST.das_do_setor({"id": SID.RESPONSAVEL_UFV, "nome": "Responsáveis UFV"})
        assert "pcm/tecnicos-por-usina" in ST.das_do_setor({"id": SID.PCM, "nome": "PCM"})
        assert "pcm/tecnicos-por-usina" not in ST.das_do_setor({"id": SID.PERFORMANCE, "nome": "Performance"})
    _no_setor(monkeypatch, SID.PCM)
    r = c.post(ROTA + "/decidir", data=por)
    assert r.status_code == 303 and len(_decisoes(app)) == 1
    assert c.post(ROTA + "/carga-inicial").status_code == 403
    # pedido de outro site não grava, nem para quem pode
    assert c.post(ROTA + "/decidir", data=dict(por, pessoa_id="11"),
                  headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_por_e_tirar_volta_filtrado(app, banco, logado):
    r = logado.post(ROTA + "/decidir", data={"usina_id": "1", "pessoa_id": "10", "acao": "por", "ate": "2030-12-31",
                                             "obs": "apoio", "v_equipe": "SP Norte 01"})
    assert r.status_code == 303 and r.headers["Location"].endswith(ROTA + "?equipe=SP+Norte+01")
    linha = _decisoes(app)[0]
    assert linha["usina_fracttal"] == F1 and linha["pessoa_hmac"] == _h("t10@exemplo.test")
    assert int(linha["ate_data_id"]) == 20301231 and linha["assinatura"]
    assert "Técnico posto na usina." in logado.get(ROTA).get_data(as_text=True)
    logado.post(ROTA + "/decidir", data={"usina_id": "1", "pessoa_id": "10", "acao": "tirar"})
    assert _atuais(app) == {}
    r = logado.post(ROTA + "/decidir", data={"usina_id": "1", "pessoa_id": "10", "acao": "tirar"})
    assert "já não está nesta usina" in logado.get(ROTA).get_data(as_text=True)


def test_carga_inicial_so_com_livro_vazio(app, banco, logado):
    assert "Carga inicial pela equipe" in logado.get(ROTA).get_data(as_text=True)
    assert logado.post(ROTA + "/carga-inicial").status_code == 303
    dec = _decisoes(app)
    assert len(dec) == 5 and {d["origem"] for d in dec} == {"carga_inicial"}
    html = logado.get(ROTA).get_data(as_text=True)
    assert "5 ligações" in html and "Carga inicial pela equipe" not in html
    logado.post(ROTA + "/carga-inicial")
    assert len(_decisoes(app)) == 5
    assert "o livro já tem decisões" in logado.get(ROTA).get_data(as_text=True)


def _esperado(html, usina=None):
    """O resumo que a tela mostrou para confirmar: o do Reenviar tudo, ou o do Reenviar de uma usina."""
    import re
    if usina is None:
        return re.search(r'action="[^"]*/reemitir-tudo"[\s\S]*?name="esperado" value="([^"]+)"', html).group(1)
    return re.search(rf'name="usina_id" value="{usina}"><input type="hidden" name="acao" value="reemitir">'
                     r'<input type="hidden" name="esperado" value="([^"]+)"', html).group(1)


def test_reemitir_regrava_com_o_nome_novo(app, banco, logado):
    A.decidir(app.config, usina_id=1, usina_fracttal="Nome Antigo", pessoa_id=10, pessoa_hmac=_h("t10@exemplo.test"),
              na_usina=True, usuario=PESSOA)
    html = logado.get(ROTA).get_data(as_text=True)
    assert "Reenviar ao App" in html
    # sem o resumo que a tela mostrou, nada vai (revisão de 05/11/2026: a conta é conferida dentro da trava)
    assert logado.post(ROTA + "/decidir", data={"usina_id": "1", "acao": "reemitir"}).status_code == 303
    assert len(_decisoes(app)) == 1 and "Faltou a conferência da tela" in logado.get(ROTA).get_data(as_text=True)
    assert logado.post(ROTA + "/decidir", data={"usina_id": "1", "acao": "reemitir",
                                                "esperado": _esperado(html, 1)}).status_code == 303
    dec = _decisoes(app)
    assert len(dec) == 2 and dec[-1]["usina_fracttal"] == F1 and dec[-1]["origem"] == "reemissao"


def test_pagina_sem_email_de_ninguem(app, banco, logado):
    logado.post(ROTA + "/decidir", data={"usina_id": "1", "pessoa_id": "10", "acao": "por"})
    for ver in ("usina", "tecnico"):
        html = logado.get(f"{ROTA}?ver={ver}").get_data(as_text=True)
        assert "exemplo.test" not in html and "Técnico Dez" in html
    dados = json.loads(html.split('id="tu-dados">', 1)[1].split("</script>", 1)[0])
    assert dados["pessoas"] and all(set(p) == {"id", "nome", "equipe_id"} for p in dados["pessoas"])


def test_historico_da_usina(app, banco, logado):
    logado.post(ROTA + "/decidir", data={"usina_id": "1", "pessoa_id": "10", "acao": "por", "obs": "apoio nas férias"})
    logado.post(ROTA + "/decidir", data={"usina_id": "1", "pessoa_id": "10", "acao": "tirar"})
    r = logado.get(ROTA + "/historico?usina=1")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and html.index("tirou") < html.index("pôs") and "apoio nas férias" in html
    assert "Técnico Dez" in html and "administrador (senha)" in html
    assert logado.get(ROTA + "/historico?usina=x").status_code == 404


def test_banco_fora_a_tela_abre_e_diz(app, logado):
    """Sem o banco (o rastreador do prefixo, ou a API fora do ar), a tela abre com o aviso e sem botão de gravar."""
    r = logado.get(ROTA)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Não consegui ler o cadastro no banco" in html and "Carga inicial" not in html
    assert logado.get(ROTA + "/historico?usina=1").status_code == 503
    r = logado.post(ROTA + "/decidir", data={"usina_id": "1", "pessoa_id": "10", "acao": "por"})
    assert r.status_code == 303 and "Não consegui ler o cadastro no banco" in logado.get(ROTA).get_data(as_text=True)


def test_tirar_leva_o_nome_e_o_codigo_que_o_app_tem(app, banco, logado):
    """O App acha a ligação a tirar pelo nome da usina e pelo código que foram na linha que pôs: o tirar leva os
    mesmos, mesmo que o nome no Fracttal tenha mudado depois."""
    A.decidir(app.config, usina_id=1, usina_fracttal="Nome Antigo", pessoa_id=10, pessoa_hmac="c" * 24,
              na_usina=True, usuario=PESSOA)
    logado.post(ROTA + "/decidir", data={"usina_id": "1", "pessoa_id": "10", "acao": "tirar"})
    ult = _decisoes(app)[-1]
    assert ult["na_usina"] == "nao" and ult["usina_fracttal"] == "Nome Antigo" and ult["pessoa_hmac"] == "c" * 24


def test_abas_no_estilo_da_pt_e_a_comparacao_com_o_app(app, banco, logado):
    """As abas Por usina, Por técnico e, com a foto do App, Comparação com o App; os chips das situações."""
    html = logado.get(ROTA).get_data(as_text=True)
    assert 'class="campo-nativa"' in html and 'class="cn-numeros"' in html and "Sem técnico" in html
    assert "Por técnico" in html and "Comparação com o App" not in html
    from test_pcm_tecnicos_usina import _aba
    _aba(banco, "organizacao_app_campo", "Atribuicoes", [{"Usina": F1, "Pessoa (HMAC)": _h("t11@exemplo.test"),
                                                           "Papel": "executa"}])
    from nexus.campo import visao
    visao.limpar()
    html = logado.get(ROTA + "?ver=app").get_data(as_text=True)
    assert "Comparação com o App" in html and "Pendências para a troca" in html and "Técnico Onze" in html


def test_tabela_com_cliente_sem_regiao_e_sem_o_botao_tecnico_na_linha(app, banco, logado):
    """Levi, 17/10: a coluna Cliente antes da Usina, sem a Região de campo; sem o botão "Técnico" na célula (o "Pôr
    técnico" fica no detalhe da linha); os técnicos um em cima do outro, sem a borda verde."""
    logado.post(ROTA + "/decidir", data={"usina_id": "1", "pessoa_id": "10", "acao": "por"})
    html = logado.get(ROTA).get_data(as_text=True)
    cab = html.split("<thead>", 1)[1].split("</thead>", 1)[0]
    assert cab.index("Cliente") < cab.index("Usina") and "Região" not in cab
    assert 'class="tu-mais"' not in html and "Pôr técnico" in html
    assert 'id="f-cliente"' in html and 'id="f-regiao"' not in html


def test_o_filtro_e_na_pagina(app, banco, logado):
    """Levi, 17/10: "sempre que vou puxar um filtro ele carrega o site de novo, deveria só filtrar os dados direto". As
    linhas vão todas à página (as que não passam, escondidas), com o que cada filtro olha; as listas não mandam o
    formulário; as duas abas estão na página."""
    import re
    html = logado.get(ROTA + "?equipe=SP+Norte+01").get_data(as_text=True)
    assert "data-filtro-local" in html and "filtro-local.js" in html and "this.form.submit()" not in html
    linhas = re.findall(r'<tr class="cn-linha"[^>]*>', html)
    assert len(linhas) == 4                                           # as 4 usinas, a desmobilizada também
    escondidas = [l for l in linhas if l.rstrip(">").endswith(" hidden")]
    assert len(escondidas) == 2                                       # a da SC Oeste 01 e a fora de operação
    assert all('data-f-equipe="' in l and 'data-f-situacao="' in l and 'data-f-busca="' in l for l in linhas)
    assert sum('data-fl-fora="1"' in l for l in linhas) == 1
    assert 'data-aba-secao="usina"' in html and 'data-aba-secao="tecnico"' in html


def _nomes_antigos(app):
    """Duas usinas cujo nome no Fracttal mudou depois de as ligações irem ao App."""
    for uid, pid in ((1, 10), (2, 11)):
        A.decidir(app.config, usina_id=uid, usina_fracttal=f"Nome Antigo {uid}", pessoa_id=pid,
                  pessoa_hmac=_h(f"t{pid}@exemplo.test"), na_usina=True, usuario=PESSOA)


def test_reenviar_tudo_ao_app_confirma_a_conta_e_grava_uma_vez(app, banco, logado, monkeypatch):
    """O "Reenviar tudo ao App" (05/11/2026): as ligações de todas as usinas cujo nome do Fracttal ou código mudou, com a
    confirmação de quantas vão, numa gravação só. A conta que mudou desde que a tela abriu não grava."""
    from test_pcm_tecnicos_usina import F2
    _nomes_antigos(app)
    html = logado.get(ROTA).get_data(as_text=True)
    esperado = _esperado(html)
    assert "Reenviar tudo ao App" in html and esperado.startswith("2-")
    assert 'data-confirmar="Reenviar ao App as 2 ligações' in html
    r = logado.post(ROTA + "/reemitir-tudo", data={"esperado": "2-0000000000000000"})
    assert r.status_code == 303 and len(_decisoes(app)) == 2
    assert "A conta mudou desde que a tela abriu" in logado.get(ROTA).get_data(as_text=True)
    gravou = []
    original = A._gravar_cru
    monkeypatch.setattr(A, "_gravar_cru", lambda c, t, *a: (gravou.append(1), original(c, t, *a)))
    r = logado.post(ROTA + "/reemitir-tudo", data={"esperado": esperado, "v_equipe": "SP Norte 01"})
    assert r.status_code == 303 and r.headers["Location"].endswith(ROTA + "?equipe=SP+Norte+01") and gravou == [1]
    dec = _decisoes(app)
    assert len(dec) == 4 and [d["origem"] for d in dec[2:]] == ["reemissao", "reemissao"]
    assert {d["usina_fracttal"] for d in dec[2:]} == {F1, F2}
    html = logado.get(ROTA).get_data(as_text=True)
    assert "2 ligações reenviadas ao App" in html and "Reenviar tudo ao App" not in html


def test_reenviar_tudo_sem_a_conferencia_da_tela_nao_grava(app, banco, logado):
    """Revisão de 05/11/2026 (achado 5): o `esperado` é obrigatório. Ausente ou vazio, nada vai; o "0" com nada a
    reenviar é recusa clara, não "Gravado"."""
    _nomes_antigos(app)
    for dados in ({}, {"esperado": ""}):
        assert logado.post(ROTA + "/reemitir-tudo", data=dados).status_code == 303
        assert "Faltou a conferência da tela" in logado.get(ROTA).get_data(as_text=True)
    assert len(_decisoes(app)) == 2
    logado.post(ROTA + "/reemitir-tudo", data={"esperado": _esperado(logado.get(ROTA).get_data(as_text=True))})
    assert len(_decisoes(app)) == 4
    assert logado.post(ROTA + "/reemitir-tudo", data={"esperado": "0"}).status_code == 303
    html = logado.get(ROTA).get_data(as_text=True)
    assert "Nada a reenviar" in html and "Nada foi gravado" in html and len(_decisoes(app)) == 4


def test_um_tirar_entre_a_tela_e_o_clique_nao_volta_e_a_tela_diz_que_a_conta_mudou(app, banco, logado):
    """Revisão de 05/11/2026 (achado 2): a conta da tela e a gravação tinham uma janela entre elas. O PCM tira uma pessoa
    (noutra aba, ou outra pessoa do PCM) depois de a tela abrir e antes do clique: o Reenviar tudo, montado da leitura
    velha, a punha de volta. Agora os pedidos saem de uma leitura nova, dentro da trava, e só vão se o resumo for o
    confirmado."""
    _nomes_antigos(app)
    esperado = _esperado(logado.get(ROTA).get_data(as_text=True))
    A.decidir(app.config, usina_id=2, usina_fracttal="Nome Antigo 2", pessoa_id=11,
              pessoa_hmac=_h("t11@exemplo.test"), na_usina=False, usuario=PESSOA)
    assert logado.post(ROTA + "/reemitir-tudo", data={"esperado": esperado}).status_code == 303
    assert "A conta mudou desde que a tela abriu" in logado.get(ROTA).get_data(as_text=True)
    dec = _decisoes(app)
    assert len(dec) == 3 and "reemissao" not in {d["origem"] for d in dec}
    assert (2, 11, "executa") not in _atuais(app)


def test_a_recusa_renova_a_leitura_e_a_tela_seguinte_ja_mostra_a_conta_nova(app, banco, logado):
    """Re-revisão de 05/11/2026 (N3): quando a conferência dentro da trava recusa, a leitura que ela acabou de fazer vale
    como a leitura de agora. Antes, a cópia de 1 minuto do livro seguia velha, e a tela seguinte mostrava o resumo velho
    (e recusava de novo) até a cópia vencer."""
    from pathlib import Path
    _nomes_antigos(app)
    esperado = _esperado(logado.get(ROTA).get_data(as_text=True))
    assert esperado.startswith("2-")
    # outra máquina tira a ligação da usina 2: o livro muda sem passar pela cópia deste Nexus
    arq = Path(app.config["NEXUS_PCM_ATRIBUICOES_ARQUIVO"])
    d = json.loads(arq.read_text(encoding="utf-8"))
    d[A.ABA].append(dict(d[A.ABA][-1], decidida_em="2026-10-17T13:00:00Z", na_usina="nao"))
    arq.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    assert _esperado(logado.get(ROTA).get_data(as_text=True)) == esperado          # a cópia ainda mostra a conta velha
    assert logado.post(ROTA + "/reemitir-tudo", data={"esperado": esperado}).status_code == 303
    html = logado.get(ROTA).get_data(as_text=True)
    assert "A conta mudou desde que a tela abriu" in html and _esperado(html).startswith("1-")
    assert "reemissao" not in {x["origem"] for x in _decisoes(app)}


def test_reenviar_tudo_so_quem_programa_e_da_propria_pagina(app, banco, monkeypatch):
    _nomes_antigos(app)
    c = _pessoa(app)
    _no_setor(monkeypatch, SID.RESPONSAVEL_UFV)
    assert "Reenviar tudo ao App" not in c.get(ROTA).get_data(as_text=True)
    assert c.post(ROTA + "/reemitir-tudo", data={"esperado": "2-x"}).status_code == 403
    _no_setor(monkeypatch, SID.PCM)
    esperado = _esperado(c.get(ROTA).get_data(as_text=True))
    assert c.post(ROTA + "/reemitir-tudo", data={"esperado": esperado},
                  headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert len(_decisoes(app)) == 2
    assert c.post(ROTA + "/reemitir-tudo", data={"esperado": esperado}).status_code == 303
    assert len(_decisoes(app)) == 4
