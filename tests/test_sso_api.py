"""A API do SSO da zeladoria no Nexus (12/11/2026): o site fica fora do Nexus e fala com ela no lugar do Supabase.

O que o Supabase garantia (o RLS da seção 7.2 do pacote de migração) vale aqui: o fornecedor sem login só envia e não lê
nada; o gestor pendente só vê o próprio perfil; o aprovado vê e mexe; a linha do fornecedor nasce com os campos do
servidor; os arquivos só abrem com o link assinado. Banco falso; pessoas, empresas e usinas fictícias.
"""
from datetime import datetime, timezone
from io import BytesIO

import pytest

from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.sso import api as API
from nexus.sso import copia, gravacao as G, leitura, limite
from nexus.sso import regras as R
from nexus.sso import tabelas as T
from tests.pg_falso import ApiPGFalsa

CHAVE = gerar_chave()
AGORA = datetime(2026, 11, 12, 13, 0, tzinfo=timezone.utc)
SITE = "https://sso.exemplo.test"
S1 = "11111111-1111-4111-8111-111111111111"
S2 = "22222222-2222-4222-8222-222222222222"
V1 = "33333333-3333-4333-8333-333333333333"
P1 = "44444444-4444-4444-8444-444444444444"
P2 = "55555555-5555-4555-8555-555555555555"
U_OK = "66666666-6666-4666-8666-666666666666"
U_PEND = "77777777-7777-4777-8777-777777777777"
A1 = "88888888-8888-4888-8888-888888888888"
NOVO = "99999999-9999-4999-8999-999999999999"
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
PDF = b"%PDF-1.4\n" + b"x" * 200
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 200
ANTIGA = "https://supabase.exemplo.test/storage/v1/object/public/apr-arquivos/a1/desvio-1-foto.jpg"

TIPOS = {
    "integracao_video.sessoes_video": "id:uuid titulo:text descricao:text url_video:text duracao_segundos:integer "
    "perguntas_quiz:jsonb ativo:boolean criado_em:timestamptz atualizado_em:timestamptz nome_curso_certificado:text "
    "carga_horaria_texto:text cidade_realizacao:text conteudo_programatico:jsonb",
    "integracao_video.visualizacoes": "id:uuid sessao_id:uuid progresso_max_segundos:integer concluido:boolean "
    "iniciado_em:timestamptz atualizado_em:timestamptz",
    "integracao_video.presencas": "id:uuid sessao_id:uuid visualizacao_id:uuid nome_completo:text cpf:text "
    "empresa_contratada:text usina:text cargo_funcao:text telefone:text respostas_quiz:jsonb nota_quiz:integer "
    "quiz_aprovado:boolean assinatura_base64:text declaracao_aceita:boolean declaracao_aceita_em:timestamptz "
    "progresso_max_segundos:integer concluido_em:timestamptz pdf_gerado_em:timestamptz criado_em:timestamptz "
    "atualizado_em:timestamptz email:text numero_certificado:text status_aprovacao:text aprovado_em:timestamptz "
    "aprovado_por:uuid origem:text certificado_url:text motivo_rejeicao:text",
    "integracao_video.perfis": "user_id:uuid email:text status:text criado_em:timestamptz nome_completo:text "
    "cargo_registro:text assinatura_padrao_base64:text",
    "apr.submissoes": "id:uuid usina:text numero_os:text data_liberacao:date empresa_contratada:text responsavel:text "
    "descricao_tarefa:text atividades:jsonb instalacoes_desenergizadas:jsonb epis:jsonb riscos:jsonb "
    "assinaturas_urls:jsonb observacoes:text desvios_urls:jsonb criado_em:timestamptz assinaturas:jsonb",
    "epi.checklists": "id:uuid servico:text empresa:text colaborador:text data:date itens:jsonb assinatura:text "
    "pendencias:integer criado_em:timestamptz",
    "public.checklists": "id:uuid created_at:timestamptz fase:text fornecedor_nome:text fornecedor_empresa:text "
    "fornecedor_contato:text usina:text servico:text dados:jsonb editado_em:timestamptz editado_por:text "
    "excluido_em:timestamptz excluido_por:text",
    "diario.registros": "id:uuid usina:text data:date servico:text empresa:text responsavel:text observacao:text "
    "fotos:jsonb videos:jsonb criado_em:timestamptz",
    "diario.usinas": "nome:text",
    "cronograma.periodos": "id:uuid usina:text fornecedor:text servicos:text[] data_inicio:date data_fim:date "
    "status:text status_manual:boolean ordem:integer observacao:text criado_em:timestamptz atualizado_em:timestamptz "
    "vinculos_manuais:jsonb",
    "cronograma.periodos_historico": "id:uuid periodo_id:uuid usina:text fornecedor:text acao:text detalhes:jsonb "
    "alterado_por:text alterado_em:timestamptz",
    "cronograma.fornecedores": "nome:text",
}


def _tipos():
    out = {}
    for t, s in TIPOS.items():
        out[t] = [[c.split(":")[0], c.split(":")[1].replace("timestamptz", "timestamp with time zone")]
                  for c in s.split()]
    return out


def _partes():
    chaves = {t: "id" for t in TIPOS} | {"integracao_video.perfis": "user_id", "diario.usinas": "nome",
                                         "cronograma.fornecedores": "nome"}
    tabelas = {
        "integracao_video.sessoes_video": [
            {"id": S1, "titulo": "Integração", "ativo": True, "duracao_segundos": 600,
             "url_video": "https://supabase.exemplo.test/storage/v1/object/public/integracao-video-midia/video.mp4",
             "perguntas_quiz": [{"pergunta": "?", "alternativas": ["a", "b"], "correta": 0}]},
            {"id": S2, "titulo": "Antiga", "ativo": False, "duracao_segundos": 100}],
        "integracao_video.visualizacoes": [{"id": V1, "sessao_id": S1, "progresso_max_segundos": 0, "concluido": False}],
        "integracao_video.presencas": [
            {"id": P1, "sessao_id": S1, "nome_completo": "Fulano de Tal", "cpf": "000.000.000-00", "usina": "Usina Teste",
             "status_aprovacao": "pendente", "origem": "app", "assinatura_base64": "data:image/png;base64,AAAA"},
            {"id": P2, "sessao_id": S1, "nome_completo": "Ciclano Importado", "cpf": "111.111.111-11", "usina": "Usina Teste",
             "status_aprovacao": "pendente", "origem": "planilha", "assinatura_base64": None}],
        "integracao_video.perfis": [
            {"user_id": U_OK, "email": "gestor@exemplo.test", "status": "aprovado", "nome_completo": "Gestor Teste"},
            {"user_id": U_PEND, "email": "pendente@exemplo.test", "status": "pendente"}],
        "apr.submissoes": [{"id": A1, "usina": "Usina Teste", "numero_os": "123", "data_liberacao": "2026-11-09",
                            "empresa_contratada": "Empresa X", "responsavel": "Beltrano", "descricao_tarefa": "Roçagem",
                            "desvios_urls": [ANTIGA]}],
        "epi.checklists": [], "public.checklists": [], "diario.registros": [],
        "diario.usinas": [{"nome": "Usina Teste"}],
        "cronograma.periodos": [], "cronograma.periodos_historico": [], "cronograma.fornecedores": [],
    }
    return [{"parte": "resto", "gerado_em": "2026-11-12T12:40:00+00:00", "tipos": _tipos(), "chaves": chaves,
             "arquivos": [{"bucket": "apr-arquivos", "caminho": "a1/desvio-1-foto.jpg", "bytes": 10,
                           "tipo": "image/jpeg", "criado_em": "2026-11-08T10:00:00+00:00"}],
             "tabelas": tabelas}]


@pytest.fixture
def banco():
    api = ApiPGFalsa()
    copia.copiar(_partes(), cofre=Cofre(CHAVE), base="http://pg.falso", token="t", sessao=api, gravar=True, agora=AGORA)
    return api


@pytest.fixture
def sso(app, banco, tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_SSO_GRAVA", "1")
    app.config.update(GRIDCO_DB_API="http://pg.falso", GRIDCO_SQL_TOKEN="t", NEXUS_CHAVE_CADASTRO=CHAVE,
                      NEXUS_DADOS=str(tmp_path), NEXUS_SSO_ORIGENS=SITE)
    app.extensions["nexus_dados_sessao"] = banco
    G.esquecer()
    limite.zerar()
    yield app
    G.esquecer()
    limite.zerar()


def _cab(app, email=None, admin=False):
    cab = {"Origin": SITE}
    if email is not None or admin:
        cab["Authorization"] = "Bearer " + R.emitir_passe(app, email or "", admin)
    return cab


def _gravar(cli, cab, view, op="insert", **kw):
    return cli.post("/t/sso/api/gravar", json={"ops": [{"op": op, "view": view, **kw}]}, headers=cab)


def _apr(id_=NOVO, **mais):
    return {"id": id_, "usina": "Usina Teste", "numero_os": "456", "data_liberacao": "2026-11-12",
            "empresa_contratada": "Empresa Y", "responsavel": "Fulano", "descricao_tarefa": "Limpeza", **mais}


# ── o fornecedor: só envia ──────────────────────────────────────────────────────────────────────────────────────────
def test_fornecedor_envia_apr_e_nao_le_nada(sso):
    cli = sso.test_client()
    r = _gravar(cli, _cab(sso), "apr_submissoes", linhas=[_apr()])
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["resultado"] == [[]]                       # não lê de volta o que mandou
    g = G.do_app(sso.config)
    nova = g.linha("apr_submissoes", NOVO)
    assert nova["criado_em"] and nova["atividades"] == [] and nova["riscos"] == {}     # os padrões do Postgres
    for view in ("apr_submissoes", "iv_presencas", "iv_perfis", "epi_submissoes", "checklists", "diario_registros",
                 "cronograma_periodos"):
        assert cli.get(f"/t/sso/api/v/{view}", headers=_cab(sso)).get_json() == [], view


def test_fornecedor_nao_atualiza_nem_apaga(sso):
    cli = sso.test_client()
    r = _gravar(cli, _cab(sso), "iv_presencas", op="update", patch={"status_aprovacao": "aprovado"},
                filtros=[["eq", "id", P1]])
    assert r.status_code == 403
    r = _gravar(cli, _cab(sso), "apr_submissoes", op="delete", filtros=[["eq", "id", A1]])
    assert r.status_code == 403
    assert G.do_app(sso.config).linha("iv_presencas", P1)["status_aprovacao"] == "pendente"


def test_presenca_do_fornecedor_nasce_pendente_sem_certificado(sso):
    cli = sso.test_client()
    linha = {"id": NOVO, "sessao_id": S1, "visualizacao_id": V1, "nome_completo": "Novo Fornecedor",
             "cpf": "222.222.222-22", "status_aprovacao": "aprovado", "certificado_url": "x", "origem": "planilha",
             "aprovado_por": U_OK, "respostas_quiz": [0]}
    assert _gravar(cli, _cab(sso), "iv_presencas", linhas=[linha]).status_code == 200
    p = G.do_app(sso.config).linha("iv_presencas", NOVO)
    assert (p["status_aprovacao"], p["origem"], p["certificado_url"], p["aprovado_por"]) == ("pendente", "app", None, None)


def test_sessao_inativa_e_obrigatoria_faltando_sao_recusadas(sso):
    cli = sso.test_client()
    r = _gravar(cli, _cab(sso), "iv_visualizacoes", linhas=[{"id": NOVO, "sessao_id": S2}])
    assert r.status_code == 400, r.get_json()
    r = _gravar(cli, _cab(sso), "apr_submissoes", linhas=[_apr(usina="")])
    assert r.status_code == 400 and "usina" in r.get_json()["message"]
    r = _gravar(cli, _cab(sso), "epi_submissoes", linhas=[{"servico": "outro", "empresa": "E", "colaborador": "C",
                                                           "data": "2026-11-12"}])
    assert r.status_code == 400                                      # o CHECK do serviço
    r = _gravar(cli, _cab(sso), "apr_submissoes", linhas=[_apr(id_="nao-e-uuid")])
    assert r.status_code == 400


def test_fornecedor_nao_grava_link_de_outro_site(sso):
    cli = sso.test_client()
    r = _gravar(cli, _cab(sso), "apr_submissoes", linhas=[_apr(desvios_urls=["https://outro.test/foto.jpg"])])
    assert r.status_code == 400
    ok = f"http://localhost/t/sso/storage/v1/object/public/apr-arquivos/{NOVO}/desvio-1-a.jpg"
    r = _gravar(cli, _cab(sso), "apr_submissoes",
                linhas=[_apr(desvios_urls=[ok], assinaturas=[{"nome": "F", "assinatura_base64": "data:image/png;base64,AA=="}])])
    assert r.status_code == 200, r.get_json()


def test_fornecedor_le_so_o_que_o_formulario_precisa(sso):
    cli = sso.test_client()
    sessoes = cli.get("/t/sso/api/v/iv_sessoes_video?eq=ativo:true", headers=_cab(sso)).get_json()
    assert [s["id"] for s in sessoes] == [S1]
    assert sessoes[0]["url_video"] == "http://localhost/t/sso/video/integracao-video-midia/video.mp4"
    assert cli.get("/t/sso/api/v/iv_visualizacoes", headers=_cab(sso)).get_json() == []      # sem o id, nada
    uma = cli.get(f'/t/sso/api/v/iv_visualizacoes?eq=id:"{V1}"', headers=_cab(sso)).get_json()
    assert [v["id"] for v in uma] == [V1]
    assert cli.get("/t/sso/api/v/diario_usinas?select=nome", headers=_cab(sso)).get_json() == [{"nome": "Usina Teste"}]


def test_pedido_de_outro_site_e_recusado(sso):
    cli = sso.test_client()
    r = cli.post("/t/sso/api/gravar", json={"ops": [{"op": "insert", "view": "apr_submissoes", "linhas": [_apr()]}]},
                 headers={"Origin": "https://malicioso.test"})
    assert r.status_code == 403
    pre = cli.open("/t/sso/api/gravar", method="OPTIONS", headers={"Origin": SITE,
                                                                     "Access-Control-Request-Method": "POST"})
    assert pre.status_code == 200 and pre.headers["Access-Control-Allow-Origin"] == SITE
    assert "authorization" in pre.headers["Access-Control-Allow-Headers"]


def test_limite_por_ip(sso, monkeypatch):
    monkeypatch.setitem(limite.TETOS, "envio", 2)
    cli = sso.test_client()
    assert _gravar(cli, _cab(sso), "diario_usinas", linhas=[{"nome": "Usina A"}]).status_code == 200
    assert _gravar(cli, _cab(sso), "diario_usinas", linhas=[{"nome": "Usina B"}]).status_code == 200
    assert _gravar(cli, _cab(sso), "diario_usinas", linhas=[{"nome": "Usina C"}]).status_code == 429


# ── a Gestão: pendente não vê nada, aprovado vê e mexe ─────────────────────────────────────────────────────────────
def test_pendente_so_ve_o_proprio_perfil(sso):
    cli = sso.test_client()
    cab = _cab(sso, "pendente@exemplo.test")
    assert cli.get("/t/sso/api/eu", headers=cab).get_json()["papel"] == "pendente"
    assert cli.get("/t/sso/api/v/iv_presencas", headers=cab).get_json() == []
    perfis = cli.get("/t/sso/api/v/iv_perfis", headers=cab).get_json()
    assert [p["user_id"] for p in perfis] == [U_PEND]
    r = _gravar(cli, cab, "iv_perfis", op="update", patch={"status": "aprovado"}, filtros=[["eq", "user_id", U_PEND]])
    assert r.status_code == 403


def test_pessoa_nova_cria_a_propria_linha_sempre_pendente(sso):
    cli = sso.test_client()
    cab = _cab(sso, "nova@exemplo.test")
    eu = cli.get("/t/sso/api/eu", headers=cab).get_json()
    assert eu["papel"] == "pendente" and eu["user"]["id"] == R.id_do_email("nova@exemplo.test")
    r = _gravar(cli, cab, "iv_perfis", linhas=[{"user_id": eu["user"]["id"], "email": "x", "status": "aprovado"}])
    assert r.status_code == 200
    linha = G.do_app(sso.config).linha("iv_perfis", eu["user"]["id"])
    assert (linha["status"], linha["email"]) == ("pendente", "nova@exemplo.test")
    r = _gravar(cli, cab, "iv_perfis", linhas=[{"user_id": U_OK, "email": "x"}])      # a linha de outro, não
    assert r.status_code == 403


def test_aprovado_ve_tudo_com_os_arquivos_assinados_e_aprova(sso):
    cli = sso.test_client()
    cab = _cab(sso, "GESTOR@exemplo.test")
    presencas = cli.get("/t/sso/api/v/iv_presencas?order=criado_em:desc", headers=cab).get_json()
    assert {p["id"] for p in presencas} == {P1, P2} and any(p["cpf"] == "000.000.000-00" for p in presencas)
    apr = cli.get("/t/sso/api/v/apr_submissoes", headers=cab).get_json()[0]
    url = apr["desvios_urls"][0]
    assert url.startswith("http://localhost/t/sso/storage/v1/object/public/apr-arquivos/a1/desvio-1-foto.jpg?a=")
    patch = {"status_aprovacao": "aprovado", "aprovado_por": U_OK, "aprovado_em": "2026-11-12T13:00:00Z",
             "certificado_url": "http://localhost/t/sso/storage/v1/object/public/certificados-integracao-video/x.pdf?a=zz"}
    r = _gravar(cli, cab, "iv_presencas", op="update", patch=patch, filtros=[["eq", "id", P1]])
    assert r.status_code == 200
    p = G.do_app(sso.config).linha("iv_presencas", P1)
    assert p["status_aprovacao"] == "aprovado"
    assert p["certificado_url"].endswith("/certificados-integracao-video/x.pdf")        # sem a assinatura de 12 h


def test_aprovado_cria_com_select_e_historico_so_cresce(sso):
    cli = sso.test_client()
    cab = _cab(sso, "gestor@exemplo.test")
    r = cli.post("/t/sso/api/gravar", headers=cab, json={"ops": [{"op": "insert", "view": "cronograma_historico",
                                                                  "linhas": [{"acao": "criado", "usina": "Usina Teste"}]}]})
    nova = r.get_json()["resultado"][0][0]
    assert nova["id"] and nova["alterado_em"]
    r = _gravar(cli, cab, "cronograma_historico", op="update", patch={"acao": "x"}, filtros=[["eq", "id", nova["id"]]])
    assert r.status_code == 403                                     # o RLS só dava select e insert
    assert _gravar(cli, cab, "diario_registros", op="delete", filtros=[["eq", "id", NOVO]]).status_code == 200


@pytest.mark.parametrize("email", ["admin@exemplo.test", ""])        # pelo Fracttal e pela senha de administrador
def test_administrador_sem_perfil_ganha_a_linha_aprovada(sso, email):
    sso.config["NEXUS_ADMINS"] = "admin@exemplo.test"
    cli = sso.test_client()
    cab = _cab(sso, email, admin=True)
    eu = cli.get("/t/sso/api/eu", headers=cab).get_json()
    assert eu["papel"] == "gestao"
    assert G.do_app(sso.config).linha("iv_perfis", eu["user"]["id"])["status"] == "aprovado"
    meu = cli.get(f'/t/sso/api/v/iv_perfis?eq=user_id:"{eu["user"]["id"]}"', headers=cab).get_json()
    assert [p["status"] for p in meu] == ["aprovado"]                 # o app acha a linha e não mostra a tela de espera


def test_passe_mexido_vale_como_fornecedor(sso):
    cli = sso.test_client()
    cab = {"Origin": SITE, "Authorization": "Bearer " + R.emitir_passe(sso, "gestor@exemplo.test", False) + "x"}
    assert cli.get("/t/sso/api/eu", headers=cab).status_code == 401
    assert cli.get("/t/sso/api/v/iv_presencas", headers=cab).get_json() == []


# ── os arquivos ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _enviar(cli, cab, bucket, caminho, dados, upsert=False):
    return cli.post("/t/sso/api/arquivo", headers=cab, content_type="multipart/form-data",
                    data={"bucket": bucket, "caminho": caminho, "upsert": "true" if upsert else "false",
                          "arquivo": (BytesIO(dados), caminho.split("/")[-1])})


def test_fornecedor_envia_foto_sem_sobrescrever_e_so_imagem(sso):
    cli = sso.test_client()
    assert _enviar(cli, _cab(sso), "epi-fotos", f"{NOVO}/item-1-luva.jpg", JPG).status_code == 200
    assert _enviar(cli, _cab(sso), "epi-fotos", f"{NOVO}/item-1-luva.jpg", JPG).status_code == 409
    assert _enviar(cli, _cab(sso), "epi-fotos", f"{NOVO}/item-2.jpg", b"<html><script>").status_code == 400
    assert _enviar(cli, _cab(sso), "epi-fotos", "../fora.jpg", JPG).status_code == 400
    assert _enviar(cli, _cab(sso), "certificados-integracao-video", "x.pdf", PDF).status_code == 403


def test_arquivo_so_abre_com_o_link_assinado(sso):
    cli = sso.test_client()
    _enviar(cli, _cab(sso), "checklist-fotos", "antes/1-a.jpg", JPG)
    base = "/t/sso/storage/v1/object/public/checklist-fotos/antes/1-a.jpg"
    assert cli.get(base).status_code == 403
    assert cli.get(base + "?a=" + R._assinador(sso).dumps("x")).status_code == 403
    from nexus.sso import arquivos as A
    r = cli.get(base + "?a=" + A.assinar(sso, "checklist-fotos", "antes/1-a.jpg"), headers={"Origin": SITE})
    assert r.status_code == 200 and r.mimetype == "image/jpeg" and r.data == JPG
    assert r.headers["Access-Control-Allow-Origin"] == SITE              # o html2canvas do PDF lê com CORS


def test_certificado_pela_funcao_da_gestao_sobrescreve(sso):
    cli = sso.test_client()
    dados = {"bucket": "certificados-integracao-video", "caminho": f"{P1}.pdf", "contentType": "application/pdf"}

    def subir(cab, conteudo):
        return cli.post("/t/sso/functions/v1/iv-upload-arquivo", headers=cab, content_type="multipart/form-data",
                        data={**dados, "arquivo": (BytesIO(conteudo), "c.pdf")})
    assert subir(_cab(sso, "pendente@exemplo.test"), PDF).get_json()["ok"] is False
    assert subir(_cab(sso, "gestor@exemplo.test"), PDF).get_json()["ok"] is True
    assert subir(_cab(sso, "gestor@exemplo.test"), PDF + b"2").get_json()["ok"] is True       # o certificado corrigido


def test_video_da_sessao_ativa_abre_sem_login_e_so_ele(sso, tmp_path):
    from nexus.sso import arquivos as A
    A.guardar(sso.config, "integracao-video-midia", "video.mp4", BytesIO(MP4), sobrescrever=True)
    A.guardar(sso.config, "integracao-video-midia", "outro.mp4", BytesIO(MP4), sobrescrever=True)
    cli = sso.test_client()
    r = cli.get("/t/sso/video/integracao-video-midia/video.mp4", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206 and len(r.data) == 10
    assert cli.get("/t/sso/video/integracao-video-midia/outro.mp4").status_code == 404


# ── o progresso, o link de assinatura e a gravação no banco ─────────────────────────────────────────────────────────
def test_progresso_do_video_grava_em_degraus_e_conclui(sso):
    cli = sso.test_client()

    def mandar(s):
        return cli.post("/t/sso/api/rpc/atualizar_progresso", headers=_cab(sso),
                        json={"p_visualizacao_id": V1, "p_progresso_segundos": s}).get_json()
    assert mandar(10) == {"gravou": False}                           # menos de 30 s: não regrava o livro
    assert mandar(40) == {"gravou": True}
    assert mandar(20) == {"gravou": False}                           # nunca diminui
    assert mandar(590) == {"gravou": True}
    assert G.do_app(sso.config).linha("iv_visualizacoes", V1)["concluido"] is False     # 600 s: conclui com 597
    assert mandar(597) == {"gravou": True}                           # a duração menos 3 s (97% daria 582)
    v = G.do_app(sso.config).linha("iv_visualizacoes", V1)
    assert (v["progresso_max_segundos"], v["concluido"]) == (597, True)


def test_link_de_assinatura_grava_uma_vez(sso):
    cli = sso.test_client()
    url = "/t/sso/functions/v1/iv-presenca-assinatura"
    assert cli.get(url + f"?id={P2}").get_json() == {"ok": True, "nomeCompleto": "Ciclano Importado", "jaAssinado": False}
    r = cli.post(url, headers=_cab(sso), json={"id": P2, "assinaturaBase64": "data:image/png;base64,BBBB"})
    assert r.get_json() == {"ok": True}
    r = cli.post(url, headers=_cab(sso), json={"id": P2, "assinaturaBase64": "data:image/png;base64,CCCC"})
    assert r.status_code == 409
    assert G.do_app(sso.config).linha("iv_presencas", P2)["assinatura_base64"] == "data:image/png;base64,BBBB"


def test_persistir_grava_cifrado_e_volta_igual(sso, banco):
    cli = sso.test_client()
    _gravar(cli, _cab(sso), "iv_presencas", linhas=[{"id": NOVO, "sessao_id": S1, "nome_completo": "Nova Pessoa",
                                                     "cpf": "333.333.333-33", "email": "nova@exemplo.test"}])
    g = G.do_app(sso.config)
    assert g.persistir()["gravados"] == [T.LIVRO_INTEGRACAO]
    bruto = next(l for l in banco.linhas(T.LIVRO_INTEGRACAO, "iv_presencas") if l["id"] == NOVO)
    assert Cofre.eh_cifrado(bruto["cpf"]) and Cofre.eh_cifrado(bruto["nome_completo"])
    est = leitura.ler_banco("http://pg.falso", banco, Cofre(CHAVE))
    assert est["versoes"][T.LIVRO_INTEGRACAO] == g.estado["versao"]
    assert next(p for p in est["abas"]["iv_presencas"] if p["id"] == NOVO)["cpf"] == "333.333.333-33"
    assert not g.diario.read_text(encoding="utf-8").strip()               # o diário esvaziou depois do banco
    with pytest.raises(copia.CopiaRecusada):                             # e a cópia do Supabase não passa por cima
        copia.copiar(_partes(), cofre=Cofre(CHAVE), base="http://pg.falso", token="t", sessao=banco, gravar=True,
                     agora=AGORA)


def test_diario_se_reaplica_ao_reiniciar(sso):
    cli = sso.test_client()
    assert _gravar(cli, _cab(sso), "apr_submissoes", linhas=[_apr()]).status_code == 200
    G.esquecer()                                                           # o servidor reiniciou antes do lote
    with sso.app_context():
        assert G.do_app(sso.config).linha("apr_submissoes", NOVO) is not None


def test_onde_nao_grava_o_sso_responde_503(sso, monkeypatch):
    monkeypatch.setenv("NEXUS_SSO_GRAVA", "0")
    G.esquecer()
    r = sso.test_client().get("/t/sso/api/v/iv_sessoes_video", headers=_cab(sso))
    assert r.status_code == 503


# ── o passe pelo login do Nexus ─────────────────────────────────────────────────────────────────────────────────────
def test_voltar_pede_o_login_e_volta_com_o_passe(sso, logado):
    para = SITE + "/gestao/index.html"
    sem = sso.test_client().get("/t/sso/voltar?para=" + para)
    assert sem.status_code == 302 and "/entrar" in sem.headers["Location"]
    r = logado.get("/t/sso/voltar?para=" + para)
    assert r.status_code == 302 and r.headers["Location"].startswith(para + "#nexus_sso=")
    assert logado.get("/t/sso/voltar?para=https://malicioso.test/gestao/").status_code == 400
    assert logado.get("/t/sso/voltar?para=" + SITE + "/apr/").status_code == 400


def test_pagina_do_administrador(sso, logado):
    r = logado.get("/t/sso/admin")
    assert r.status_code == 200 and "SSO da zeladoria" in r.get_data(as_text=True)


def test_as_rotas_publicas_do_sso_estao_no_portao():
    from nexus.auth import ROTAS_PUBLICAS
    assert API.PUBLICAS <= ROTAS_PUBLICAS
    assert "sso.voltar" not in ROTAS_PUBLICAS and "sso.admin" not in ROTAS_PUBLICAS


def test_usina_em_claro_da_copia_antiga_le_e_regrava_cifrada(app, tmp_path, monkeypatch):
    """A 1ª cópia (12/11/2026) deixou a usina em claro, e um fornecedor digitou nela o nome de uma pessoa: a leitura aceita
    o texto em claro, e o "Regravar cifrado" do administrador regrava os livros com a regra de agora."""
    api = ApiPGFalsa()
    monkeypatch.setattr(T, "_CLARO", T._CLARO | {"usina"})               # a regra da cópia antiga
    monkeypatch.setattr(T, "_CLARO_POR_ABA", {("diario_usinas", "nome")})
    copia.copiar(_partes(), cofre=Cofre(CHAVE), base="http://pg.falso", token="t", sessao=api, gravar=True, agora=AGORA)
    monkeypatch.undo()
    assert api.linhas(T.LIVRO_DIARIO, "diario_usinas")[0]["nome"] == "Usina Teste"
    monkeypatch.setenv("NEXUS_SSO_GRAVA", "1")
    app.config.update(GRIDCO_DB_API="http://pg.falso", GRIDCO_SQL_TOKEN="t", NEXUS_CHAVE_CADASTRO=CHAVE,
                      NEXUS_DADOS=str(tmp_path))
    app.extensions["nexus_dados_sessao"] = api
    G.esquecer()
    with app.app_context():
        g = G.do_app(app.config)
    assert g.linha("apr_submissoes", A1)["usina"] == "Usina Teste"       # o claro antigo se lê
    g.regravar_tudo("administrador")
    G.esquecer()                                                          # reiniciou antes do lote: o pedido fica
    with app.app_context():
        g = G.do_app(app.config)
    assert set(g.persistir()["gravados"]) == set(T.LIVROS)
    assert Cofre.eh_cifrado(api.linhas(T.LIVRO_DIARIO, "diario_usinas")[0]["nome"])
    assert Cofre.eh_cifrado(api.linhas(T.LIVRO_APR, "apr_submissoes")[0]["usina"])
    assert leitura.ler_banco("http://pg.falso", api, Cofre(CHAVE))["abas"]["diario_usinas"] == [{"nome": "Usina Teste"}]
    G.esquecer()


# ── a revisão de 12/11/2026 ─────────────────────────────────────────────────────────────────────────────────────────
def test_video_acima_de_25_mb_entra_pela_gestao(sso):
    """O teto de 25 MB do Nexus valia antes do teto do bucket (a 1ª leitura do formulário confere o tamanho): o vídeo
    da integração, de 28 MB, voltava 413."""
    cli = sso.test_client()
    grande = MP4 + b"\x00" * (26 * 1024 * 1024)
    r = cli.post("/t/sso/functions/v1/iv-upload-arquivo", headers=_cab(sso, "gestor@exemplo.test"),
                 content_type="multipart/form-data",
                 data={"bucket": "integracao-video-midia", "caminho": "video.mp4", "contentType": "video/mp4",
                       "arquivo": (BytesIO(grande), "v.mp4")})
    assert r.status_code == 200 and r.get_json()["bytes"] == len(grande)


def test_linha_grande_demais_e_fase_fora_da_lista(sso):
    cli = sso.test_client()
    r = _gravar(cli, _cab(sso), "apr_submissoes", linhas=[_apr(observacoes="x" * (1100 * 1024))])
    assert r.status_code == 400 and "grande" in r.get_json()["message"]
    r = _gravar(cli, _cab(sso), "checklists", linhas=[{"fase": "Fulano de Tal", "dados": {}}])
    assert r.status_code == 400
    assert _gravar(cli, _cab(sso), "checklists", linhas=[{"fase": "antes", "dados": {"usina": "U"}}]).status_code == 200


def test_texto_livre_do_fornecedor_vai_cifrado(sso, banco):
    cli = sso.test_client()
    _gravar(cli, _cab(sso), "apr_submissoes", linhas=[_apr(numero_os="Fulano 123.456.789-00")])
    G.do_app(sso.config).persistir()
    bruto = next(l for l in banco.linhas(T.LIVRO_APR, "apr_submissoes") if l["id"] == NOVO)
    assert Cofre.eh_cifrado(bruto["numero_os"]) and Cofre.eh_cifrado(bruto["usina"])


def test_fornecedor_nao_planta_arquivo_no_caminho_antigo(sso):
    cli = sso.test_client()
    r = _enviar(cli, _cab(sso), "apr-arquivos", "a1/desvio-1-foto.jpg", JPG)        # está no inventário do Supabase
    assert r.status_code == 409


def test_passe_de_administrador_reconfere_a_lista_e_o_sem_email_vence_em_2h(sso, monkeypatch):
    import time as _time
    cli = sso.test_client()
    sso.config["NEXUS_ADMINS"] = ""
    eu = cli.get("/t/sso/api/eu", headers=_cab(sso, "ex-admin@exemplo.test", admin=True)).get_json()
    assert eu["papel"] == "pendente"                                   # saiu da lista: o passe não o faz administrador
    cab = _cab(sso, "", admin=True)
    agora = _time.time()
    monkeypatch.setattr(_time, "time", lambda: agora + 3 * 3600)
    assert cli.get("/t/sso/api/eu", headers=cab).status_code == 401


def test_progresso_absurdo_e_recusado(sso):
    cli = sso.test_client()
    for v in ("inf", 1e300):
        r = cli.post("/t/sso/api/rpc/atualizar_progresso", headers=_cab(sso),
                     json={"p_visualizacao_id": V1, "p_progresso_segundos": v})
        assert r.status_code in (200, 400)
    assert G.do_app(sso.config).linha("iv_visualizacoes", V1)["progresso_max_segundos"] <= 600


def test_administrador_tira_da_lista_de_usinas_do_diario(sso, logado):
    with sso.app_context():
        G.do_app(sso.config)
    r = logado.post("/t/sso/admin/usina-diario", data={"nome": "Usina Teste"})
    assert r.status_code == 302
    assert G.do_app(sso.config).linha("diario_usinas", "Usina Teste") is None
    assert sso.test_client().post("/t/sso/admin/usina-diario", data={"nome": "x"}).status_code == 302   # sem login: Entrar


def test_regravar_diz_o_resultado_e_o_segundo_clique_nao_pede_outra(sso, logado):
    """12/11/2026: o Levi clicou em "Regravar cifrado" e a página ficou em "gravando…" sem dizer que tinha terminado (tinha).
    Agora ela diz "Regravando" enquanto o lote não grava, relê a situação, e diz "Pronto" quando os sete livros estão no
    banco; o 2º clique durante a regravação não pede outra."""
    with sso.app_context():
        g = G.do_app(sso.config)
    assert logado.post("/t/sso/admin/regravar").status_code == 302
    v = g.regravacao["versao"]
    assert logado.post("/t/sso/admin/regravar").status_code == 302
    assert g.regravacao["versao"] == v                                  # o 2º clique não pediu outra
    s = logado.get("/t/sso/admin/situacao").get_json()
    assert s["pendente"] is True and s["regravacao"]["concluida"] is False
    pagina = logado.get("/t/sso/admin").get_data(as_text=True)
    assert "Regravando" in pagina and "disabled" in pagina.split('id="sso-regravar-bt"')[1][:80]
    assert set(g.persistir()["gravados"]) == set(T.LIVROS)
    s = logado.get("/t/sso/admin/situacao").get_json()
    assert s["pendente"] is False and s["regravacao"]["concluida"] is True and s["gravado_em"]
    assert "Pronto" in logado.get("/t/sso/admin").get_data(as_text=True)
    assert sso.test_client().get("/t/sso/admin/situacao").status_code == 302          # sem login: Entrar
