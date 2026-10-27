"""Torre COS: a tela Acionamentos e distribuidoras (26/10/2026) — quem aciono e qual o canal da distribuidora desta UF?

Quem aciono vem do cadastro do Nexus (o banco falso do Campo, test_campo_visao.py: Altair e Brodowski 1 são da Sudeste
03, com a Supervisora Campo; Coração 1 é da Sul 01, com a vaga aberta); a UC, o canal e os chamados à concessionária, do
Andamento (`GET /api/nexus/<cliente>/distribuidoras`). Nada vai à rede; pessoas, telefones e UCs são fictícios."""
import json

import pytest
from test_campo_visao import CHAVE_CADASTRO, USINAS, _aba, _pessoas, banco  # noqa: F401  (banco é fixture)

from nexus.cadastro.cifra import Cofre
from nexus.campo import visao
from nexus.cos import acionamentos as AC
from nexus.cos import andamento as AND

CHAVE = "chave-de-teste-do-andamento"


def _linha(html, usina):
    """A linha da usina na tabela, até o fim dela."""
    i = html.index(f"<b>{usina}</b>")
    return html[i:html.index("</tr>", i)]


def test_a_chave_da_concessionaria_e_a_conta_da_ronda_cos():
    """A mesma de `chaveDaConcessionaria` (`chamados.regra.ts` da Ronda COS): é por ela que o canal de lá casa."""
    assert [AC.chave_da_concessionaria(x) for x in ("CPFL PAULISTA", "Energisa MT", "Equatorial Goiás", "  EDP-ES ", None)] \
        == ["CPFL_PAULISTA", "ENERGISA_MT", "EQUATORIAL_GOIAS", "EDP_ES", ""]


def test_o_telefone_vira_link_para_discar():
    assert AC.numero_para_discar("(17) 99999-0001") == "+5517999990001"
    assert AC.numero_para_discar("+55 17 99999-0001") == "+5517999990001"
    assert AC.numero_para_discar("") == ""


# --- a tela ----------------------------------------------------------------------------------------------------------

def _cadastro(api):
    """O técnico (1), o eletricista (2) e o Responsável O&M (90) na Altair, com o contato do técnico na ficha da usina; a
    Supervisora Campo (92) com o telefone corporativo; a Coração 1 com a Celesc no cadastro; a Brodowski 1 sem nada."""
    cofre = Cofre(CHAVE_CADASTRO)
    nomes = {1: "Técnico Alfa", 2: "Eletricista Beta", 92: "Supervisora Campo", 90: "Beltrano Supervisor"}
    tels = {92: {"telefone_corporativo": "(17) 99999-0001"}, 2: {"telefone_pessoal": "(17) 97777-0003"}}
    pessoas = []
    for p in _pessoas():
        pid = p["pessoa_id"]
        if pid in nomes:
            s = {"nome": nomes[pid], "nome_padrao": nomes[pid], **tels.get(pid, {})}
            p = dict(p, sensivel_cifrado=cofre.cifrar(json.dumps(s), f"banco/pessoas/{pid}"))
        pessoas.append(p)
    _aba(api, "cadastro_nexus", "pessoas", pessoas)
    usinas = []
    for u in USINAS:
        u = dict(u)
        if u["usina_id"] == 1:
            u.update(tecnico_om_id=1, eletricista_om_id=2, responsavel_om_id=90, concessionaria="CPFL Paulista",
                     sensivel_cifrado=cofre.cifrar(json.dumps({"contato_tecnico": "(17) 98888-0002"}), "banco/usinas/1"))
        if u["usina_id"] == 3:
            u.update(concessionaria="Celesc")
        usinas.append(u)
    _aba(api, "cadastro_nexus", "usinas", usinas)
    visao.limpar()


def _distribuidoras(**mudar):
    d = {"versao": 1, "cliente": "Thopen", "gerado_em": "2026-10-26T15:00:00-03:00", "desde": "2026-09-26T15:00:00-03:00",
         "usinas": [{"codigo": "THPN-ALT100", "nome": "Altair 1", "cidade": "Altair", "uf": "São Paulo",
                     "ucs": [{"parte": "", "uc": "1234567", "concessionaria": "CPFL PAULISTA", "chave": "CPFL_PAULISTA"}]},
                    {"codigo": "THPN-XYZ999", "nome": "Usina Sem Cadastro", "cidade": "", "uf": "",
                     "ucs": [{"parte": "", "uc": "999", "concessionaria": "COPEL", "chave": "COPEL"}]}],
         "canais": [{"chave": "CPFL_PAULISTA", "nome": "CPFL_PAULISTA", "sms": None, "contato": "WhatsApp (19) 99908-8888"},
                    {"chave": "CELESC", "nome": "Celesc", "sms": {"numero": "48196", "formato": "SEM LUZ <UC>",
                                                                  "confianca": "baixa"},
                     "contato": "WhatsApp (48) 99860-0067 (só grupo B)"}],
         "chamados": [{"registro": "r1", "os": "17001", "usina_codigo": "THPN-ALT100", "usina": "Altair 1", "parte": "",
                       "uc": "1234567", "concessionaria": "CPFL PAULISTA", "chave": "CPFL_PAULISTA", "protecoes": ["27"],
                       "estado": "SEM_PROTOCOLO", "criado_em": "2026-10-26T10:00:00-03:00",
                       "enviado_em": "2026-10-26T10:01:00-03:00", "saiu_do_celular_em": None, "resposta_em": None,
                       "protocolo": None, "protocolo_em": None, "aberto_por": "sistema", "protocolo_por": None},
                      {"registro": "r2", "os": "17002", "usina_codigo": "THPN-ALT100", "usina": "Altair 1", "parte": "",
                       "uc": "1234567", "concessionaria": "CPFL PAULISTA", "chave": "CPFL_PAULISTA", "protecoes": ["81"],
                       "estado": "PROTOCOLO", "criado_em": "2026-10-20T10:00:00-03:00",
                       "enviado_em": "2026-10-20T10:01:00-03:00", "saiu_do_celular_em": None, "resposta_em": None,
                       "protocolo": "998877", "protocolo_em": "2026-10-20T10:05:00-03:00", "aberto_por": "pessoa",
                       "protocolo_por": "sistema"}],
         "truncado": False, "gateway": {"visto_em": "2026-10-26T14:50:00-03:00", "status": "pass"}}
    d.update(mudar)
    return d


@pytest.fixture(autouse=True)
def _limpa():
    AND.limpar_cache()
    yield
    AND.limpar_cache()


@pytest.fixture
def tela(banco, app, logado, monkeypatch):
    _cadastro(banco)
    app.config.update(NEXUS_COS_ANDAMENTO_URL="http://andamento.exemplo:3002", NEXUS_COS_ANDAMENTO_CHAVE=CHAVE,
                      NEXUS_COS_ANDAMENTO_CLIENTES="Thopen")
    respostas = {"/api/nexus/Thopen/distribuidoras": _distribuidoras()}

    def pedir(f, caminho):
        r = respostas.get(caminho)
        if r is None:
            raise AND.FonteErro("o Andamento não tem este cliente, ou a rota do Nexus está desligada lá", 404)
        return r
    monkeypatch.setattr(AND, "_pedir", pedir)
    monkeypatch.setattr(AND, "agora", lambda: AND.instante("2026-10-26T15:00:00-03:00"))
    logado.respostas = respostas
    return logado


def test_quem_aciono_e_a_distribuidora_de_cada_usina(tela):
    html = tela.get("/t/cos/acionamentos").get_data(as_text=True)
    altair = _linha(html, "Altair")
    # quem aciono, do cadastro: a supervisora da região com o corporativo, o técnico com o contato da ficha da usina, o
    # eletricista com o pessoal (sem o corporativo), o responsável sem telefone
    assert "Supervisora Campo" in altair and 'href="tel:+5517999990001"' in altair and "Sudeste 03" in altair
    assert "Técnico Alfa" in altair and "(17) 98888-0002" in altair
    assert "Eletricista Beta" in altair and "(17) 97777-0003" in altair and "Beltrano Supervisor" in altair
    # a distribuidora, do Andamento: a UC e o canal para abrir à mão; o chamado sem protocolo pede ação
    assert "CPFL PAULISTA" in altair and "UC 1234567" in altair and "WhatsApp (19) 99908-8888" in altair
    assert "1 chamado pede ação" in altair
    coracao = _linha(html, "Coração 1")
    # sem UC na Ronda COS: a concessionária do cadastro, casada com o canal pela chave; a vaga de supervisor aparece
    assert "Celesc" in coracao and "UC não está na Ronda COS" in coracao and "<b>48196</b>" in coracao
    assert "vaga" in coracao
    brodowski = _linha(html, "Brodowski 1")
    assert "sem concessionária no cadastro" in brodowski
    # os chamados de 30 dias e o celular do SMS
    assert "sem protocolo" in html and "998877" in html and "lido da resposta" in html and "com sinal" in html
    # a usina com UC na Ronda COS que não liga ao cadastro é dita, para o conserto no cadastro
    assert "Usina Sem Cadastro (THPN-XYZ999)" in html


def test_filtros_de_cliente_uf_e_busca(tela):
    html = tela.get("/t/cos/acionamentos?cliente=Outro Cliente").get_data(as_text=True)
    assert "<b>Coração 1</b>" in html and "<b>Altair</b>" not in html and "998877" not in html
    html = tela.get("/t/cos/acionamentos?q=altair").get_data(as_text=True)
    assert "<b>Altair</b>" in html and "<b>Coração 1</b>" not in html and "998877" in html
    html = tela.get("/t/cos/acionamentos?uf=SC").get_data(as_text=True)
    assert "<b>Coração 1</b>" in html and "<b>Brodowski 1</b>" not in html


def test_andamento_sem_a_rota_ou_desligado_mostra_so_o_cadastro(tela, app):
    tela.respostas.clear()                                                # o Andamento de antes da rota: 404
    html = tela.get("/t/cos/acionamentos").get_data(as_text=True)
    assert "Thopen: o Andamento não tem este cliente, ou a rota do Nexus está desligada lá" in html
    assert "Supervisora Campo" in html and "UC 1234567" not in html and "UC não está na Ronda COS" in html
    assert "sem a leitura do Andamento" in html                          # a faixa não conta chamados pela metade
    app.config.update(NEXUS_COS_ANDAMENTO_URL="", NEXUS_COS_ANDAMENTO_CHAVE="")
    AND.limpar_cache()
    html = tela.get("/t/cos/acionamentos").get_data(as_text=True)
    assert "não está ligado neste servidor" in html and "Supervisora Campo" in html
    assert "Chamados à distribuidora nos últimos" not in html and "sem a leitura do Andamento" in html


def test_sem_a_chave_do_cadastro_nao_abre_contato(tela, app):
    app.config["NEXUS_CHAVE_CADASTRO"] = None
    visao.limpar()
    html = tela.get("/t/cos/acionamentos").get_data(as_text=True)
    assert "não tem a chave do cadastro" in html and "tel:+55" not in html and "Supervisora Campo" not in html


def test_com_o_cadastro_fora_nao_mostra_lista_pela_metade(tela, monkeypatch):
    def falha():
        raise ConnectionError("banco fora")
    monkeypatch.setattr(visao, "_Base", falha)
    html = tela.get("/t/cos/acionamentos").get_data(as_text=True)
    assert "Não consegui ler o cadastro do Nexus (ConnectionError)" in html and "Quem aciono</th>" not in html
