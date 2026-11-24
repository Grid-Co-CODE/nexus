"""Incidentes da Segurança · HSEQ (24/11/2026): os relatos de segurança do App de Campo (o botão vermelho da v376).

Levi, no chat do App de Campo (23/11/2026): "a pessoa vai lá no início, consegue relatar [...] entrará na parte de
segurança do Nexus". O App é a fonte; o Nexus lê a lista e as fotos no servidor do App com a chave das Sugestões e não
grava nada (`nexus/hseq/relatos_seguranca.py`, o contrato v1).

O que estes testes seguram: sem a chave o Nexus nem chama o App e a tela diz por quê; com ela, os relatos aparecem do
mais novo para o mais antigo, com a usina do cadastro pelo nome do local no Fracttal (e, sem ligação, o nome sem o
cliente e a UF), o responsável, as pessoas por função, o aviso à TST e o detalhe; o e-mail do autor e a chave nunca vão
ao HTML; os filtros aceitam vários valores, em cascata, com a conta; o App fora ou noutra versão vira aviso, nunca erro
500; a foto passa pelo Nexus só quando é imagem. App falso; nomes fictícios."""
import io
import json
import urllib.error

import pytest
from test_campo_visao import banco  # noqa: F401  (fixture)

from nexus.casca import relatos_app as R
from nexus.hseq import relatos_seguranca as RS

URL = "/t/hseq/incidentes"
CHAVE = "k" * 40
FOTO = b"\xff\xd8\xff\xe0" + b"0" * 100


def _relato(**kw):
    r = {"id": "sr-0001", "tipo": "acidente", "tipo_rotulo": "Acidente", "quando": "2026-11-23T09:41:00-03:00",
         "usina": "Thopen - Altair 1 - SP", "o_que_aconteceu": "Corte na mão ao abrir a caixa de junção.\nSem afastamento.",
         "acao_imediata": "Primeiros socorros no local.", "pessoas": [{"funcao": "tecnico", "quantidade": 2},
                                                                      {"funcao": "terceiro", "quantidade": 1}],
         "fotos": 2, "criado_em": "2026-11-23T12:41:03.000Z",
         "autor": {"nome": "Tecnico de Teste", "email": "tecnico.teste@exemplo.test", "papel": "Técnico"},
         "versao_app": "v376", "aviso_tst": {"situacao": "enviado", "enviado_em": "2026-11-23T12:41:05.000Z"}}
    r.update(kw)
    return r


class _Resposta(io.BytesIO):
    def __init__(self, dados, tipo):
        super().__init__(dados)
        self.headers = {"Content-Type": tipo}


class _AppFalso:
    """O servidor do App de mentira: a lista, as fotos e os erros que o teste mandar."""
    def __init__(self, relatos=None, fora=False, versao=1, status=200, tipo_foto="image/jpeg"):
        self.relatos = relatos if relatos is not None else [
            _relato(), _relato(id="sr-0002", tipo="condicao_insegura", tipo_rotulo="Condição insegura",
                               quando="2026-11-22T15:00:00-03:00", usina="Cliente Novo - Usina Nova - BA",
                               o_que_aconteceu="Cerca caída perto do inversor.", acao_imediata="", pessoas=[],
                               fotos=0, aviso_tst={"situacao": "nao_avisa"})]
        self.fora, self.versao, self.status, self.tipo_foto = fora, versao, status, tipo_foto
        self.pedidos = []

    def __call__(self, req, timeout=None):
        self.pedidos.append({"url": req.full_url, "chave": req.get_header("X-nexus-chave")})
        if self.fora:
            raise urllib.error.URLError("sem rede")
        if self.status != 200:
            raise urllib.error.HTTPError(req.full_url, self.status, "erro", {}, io.BytesIO(b"{}"))
        if "/foto/" in req.full_url:
            n = int(req.full_url.rsplit("/", 1)[1])
            if n >= 2:
                raise urllib.error.HTTPError(req.full_url, 404, "erro", {}, io.BytesIO(b"{}"))
            return _Resposta(FOTO, self.tipo_foto)
        return io.BytesIO(json.dumps({"versao": self.versao, "relatos": self.relatos}).encode("utf-8"))


@pytest.fixture
def app_falso(app, banco, monkeypatch):  # noqa: F811
    app.config["NEXUS_APP_RELATOS_CHAVE"] = CHAVE
    RS.limpar()
    falso = _AppFalso()
    monkeypatch.setattr(R, "_abrir", falso)
    yield falso
    RS.limpar()


def test_sem_a_chave_o_nexus_nem_chama_o_app(app, banco, logado, monkeypatch):  # noqa: F811
    app.config["NEXUS_APP_RELATOS_CHAVE"] = ""
    RS.limpar()
    falso = _AppFalso()
    monkeypatch.setattr(R, "_abrir", falso)
    html = logado.get(URL).get_data(as_text=True)
    assert "Os relatos do App de Campo ainda não estão ligados neste Nexus" in html and not falso.pedidos


def test_os_relatos_com_a_usina_do_cadastro_e_sem_o_email_nem_a_chave(app_falso, logado):
    html = logado.get(URL).get_data(as_text=True)
    p = app_falso.pedidos[0]
    assert p["url"].endswith("/app/nexus/seguranca/relatos") and p["chave"] == CHAVE
    assert '<h1 class="cn-titulo">Incidentes</h1>' in html and "cn-numeros" not in html
    # do mais novo para o mais antigo; o acidente em vermelho, a condição insegura em amarelo
    assert html.index("Corte na mão") < html.index("Cerca caída")
    assert '<span class="cn-st cn-t-critico">Acidente</span>' in html
    assert '<span class="cn-st cn-t-alerta">Condição insegura</span>' in html
    # a usina do cadastro pelo nome do local no Fracttal; sem ligação, o nome do App sem o cliente e a UF
    assert '<td>Altair<span class="det">Thopen</span></td>' in html
    assert "<td>Usina Nova" in html and "Cliente Novo - Usina Nova - BA" in html
    assert "2 técnicos, 1 terceiro" in html and "Enviado" in html and "Não avisa" in html
    assert "Primeiros socorros no local." in html and "Tecnico de Teste" in html
    assert 'href="/t/hseq/incidentes/sr-0001/foto/0"' in html and "/t/hseq/incidentes/sr-0001/foto/1" in html
    assert "/t/hseq/incidentes/sr-0001/foto/2" not in html
    assert "tecnico.teste@exemplo.test" not in html and CHAVE not in html and "azurewebsites" not in html


def test_os_filtros_aceitam_varios_valores_com_a_conta(app_falso, logado):
    so_acidente = logado.get(URL + "?tipo=Acidente").get_data(as_text=True)
    assert "Corte na mão" in so_acidente and "Cerca caída" not in so_acidente
    assert '<option value="Condição insegura">Condição insegura (1)</option>' in so_acidente
    # o Tipo na ordem da gravidade, não na alfabética
    assert so_acidente.index('<option value="Acidente"') < so_acidente.index('<option value="Condição insegura"')
    dois = logado.get(URL + "?tipo=Acidente&tipo=Condi%C3%A7%C3%A3o+insegura").get_data(as_text=True)
    assert "Corte na mão" in dois and "Cerca caída" in dois
    assert "data-fo" in dois and 'name="tipo" multiple data-todos="Todos"' in dois and "filtros-os.js" in dois
    nada = logado.get(URL + "?usina=Outra").get_data(as_text=True)
    assert "Nenhum relato com esses filtros." in nada and '<option value="Outra" selected>Outra (0)</option>' in nada
    busca = logado.get(URL + "?q=cerca").get_data(as_text=True)
    assert "Cerca caída" in busca and "Corte na mão" not in busca


@pytest.mark.parametrize("falha, frase", [({"fora": True}, "o App não respondeu"),
                                          ({"versao": 2}, "o App fala a versão 2 do contrato"),
                                          ({"status": 401}, "o App recusou a chave do Nexus")])
def test_o_app_fora_ou_noutra_versao_vira_aviso(app_falso, logado, falha, frase):
    for k, v in falha.items():
        setattr(app_falso, k, v)
    r = logado.get(URL)
    assert r.status_code == 200 and frase in r.get_data(as_text=True)


def test_o_responsavel_ufv_vem_da_ficha_da_usina_e_filtra(app_falso, logado, monkeypatch):
    from types import SimpleNamespace
    from nexus.campo import visao
    por_nome = {"thopen - altair 1 - sp": {"usina": "Altair", "cliente": "Thopen", "responsavel": "Fulano Responsavel",
                                           "usina_id": 1}}
    monkeypatch.setattr(visao, "usinas_do_fracttal", lambda: SimpleNamespace(dados={"por_nome": por_nome}))
    html = logado.get(URL + "?responsavel=Fulano+Responsavel").get_data(as_text=True)
    assert "<td>Fulano Responsavel</td>" in html and "Corte na mão" in html and "Cerca caída" not in html
    assert '<option value="Fulano Responsavel" selected>Fulano Responsavel (1)</option>' in html
    # o local sem usina no cadastro vai ao "!", para ligar em Base → Ligações
    assert "Locais sem usina no cadastro:</b> Cliente Novo - Usina Nova - BA" in html


def test_relato_sem_id_ou_sem_texto_fica_fora(app_falso, logado):
    app_falso.relatos = [_relato(id="ruim id!"), _relato(id="sr-0003", o_que_aconteceu=""), _relato(id="sr-0004")]
    html = logado.get(URL).get_data(as_text=True)
    assert html.count('class="cn-linha"') == 1 and "sr-0004" in html


def test_a_foto_passa_pelo_nexus_so_quando_e_imagem(app_falso, logado):
    r = logado.get(URL + "/sr-0001/foto/0")
    assert r.status_code == 200 and r.data == FOTO and r.mimetype == "image/jpeg"
    assert r.headers["Cache-Control"].startswith("private") and r.headers["X-Content-Type-Options"] == "nosniff"
    assert app_falso.pedidos[-1]["chave"] == CHAVE
    assert logado.get(URL + "/sr-0001/foto/2").status_code == 404        # o App não tem
    assert logado.get(URL + "/sr-0001/foto/5").status_code == 404        # fora do contrato: nem pergunta
    assert logado.get(URL + "/sr%20x/foto/0").status_code == 404
    app_falso.tipo_foto = "text/html"
    assert logado.get(URL + "/sr-0001/foto/0").status_code == 404
    app_falso.fora = True
    assert logado.get(URL + "/sr-0001/foto/0").status_code == 502


def test_a_tela_exige_login(app_falso, cliente):
    r = cliente.get(URL)
    assert r.status_code in (302, 401) and not app_falso.pedidos
