"""O aviso "OS x criada para você" no sino (08/11/2026): a sugestão de uma colega do PCM ("Criação de OS direcionada ao
usuário"), aprovada pelo Levi. As OS em processo atribuídas à pessoa e criadas por outra, da lista central de OS (nada vai ao
Fracttal); o lote (a programação, as clonagens) vira um aviso só; e quem a pessoa é no Fracttal sai do catálogo do OS
Creator pelo e-mail (o aviso de execução deixa de depender do nome da sessão). Nomes, números e textos inventados."""
import re
from datetime import datetime, timedelta, timezone

import pytest
from test_campo_visao import banco  # noqa: F401  (fixture: o banco falso)
from test_comando_insights import PESSOA, limpo  # noqa: F401  (fixtures)

from nexus.comando import avisos as AV

BRT = timezone(timedelta(hours=-3))
AGORA = datetime(2026, 11, 10, 15, 0, tzinfo=BRT)
LIDA = "/t/comando/aviso/lida"
EU_ID, EU_CONTA = 777, 555          # o id da pessoa no Fracttal (id_personnel) e a conta (id_account)


class R:
    """O registro da lista central (só os campos que os avisos leem)."""
    def __init__(self, wid, folio, criado_por="Programador Exemplo", id_criador=900, criada_ha_h=2.0, status_id=1,
                 atribuido=EU_ID, descricao="Recomposição de String", data_fim="", minuto=None):
        self.id, self.folio, self.criado_por, self.id_criador = wid, folio, criado_por, id_criador
        self.status_id, self.id_atribuido, self.descricao, self.data_fim = status_id, atribuido, descricao, data_fim
        self.atribuido_a = "Fulana de Teste"
        c = (minuto or (AGORA - timedelta(hours=criada_ha_h))).astimezone(timezone.utc)
        self.data = c.strftime("%Y-%m-%dT%H:%M:%S")


class Lista:
    def __init__(self, regs):
        self.regs, self.versao, self.janela, self.pedidos = regs, 1, ("2026-10-28", "2026-11-10"), []

    def atual(self):
        return self

    def filtrar(self, visao, pessoa, de, ate, status=None, etiqueta=None):
        self.pedidos.append((visao, dict(pessoa), de))
        if visao == "atribuidas":
            return [r for r in self.regs if r.id_atribuido == pessoa.get("id_personnel") and r.status_id in (status or ())]
        quem = pessoa.get("nome")
        return [r for r in self.regs if r.criado_por == quem and r.status_id in (status or ())]


@pytest.fixture
def limpos():
    AV.limpar()
    yield
    AV.limpar()


def _lista(monkeypatch, regs):
    l = Lista(regs)
    monkeypatch.setattr(AV, "_os_central", lambda: l)
    return l


def test_a_os_criada_por_outro_para_mim_vira_aviso(monkeypatch, limpos):
    l = _lista(monkeypatch, [R(201, "18500"),
                             R(202, "18501", criado_por="Fulana de Teste", id_criador=EU_CONTA),   # eu criei para mim
                             R(203, "18502", status_id=2),                                        # já executada
                             R(204, "18503", atribuido=999),                                      # de outra pessoa
                             R(205, "18504", criada_ha_h=24 * 8)])                                # fora dos 7 dias
    itens = AV.atribuidas(EU_ID, EU_CONTA, "Fulana de Teste", AGORA)
    assert [(a["id"], a["titulo"], a["wid"], a["tipo"]) for a in itens] == [
        ("A:201", "OS 18500 criada para você", 201, "atribuida")]
    assert "por Programador Exemplo" in itens[0]["detalhe"] and "Recomposição de String" in itens[0]["detalhe"]
    visao, pessoa, de = l.pedidos[0]
    assert (visao, pessoa) == ("atribuidas", {"id_personnel": EU_ID}) and de == "2026-11-08"   # nada antes do início
    # a que eu mesma criei, pelo nome quando a OS não traz quem criou pelo id
    _lista(monkeypatch, [R(206, "18505", criado_por="FULANA DE TESTÉ", id_criador=None)])
    AV.limpar()
    assert AV.atribuidas(EU_ID, EU_CONTA, "Fulana de Teste", AGORA) == []
    assert AV.atribuidas(None, EU_CONTA, "Fulana de Teste", AGORA) == []                          # sem o id: nada


def test_o_lote_vira_um_aviso_so_com_o_link_das_atribuidas(monkeypatch, limpos):
    m = datetime(2026, 11, 10, 8, 30, 20, tzinfo=BRT)
    lote = [R(300 + i, str(18600 + i), minuto=m + timedelta(seconds=i)) for i in range(12)]
    _lista(monkeypatch, lote + [R(400, "18700", criado_por="Supervisor Exemplo", id_criador=901, minuto=m)])
    itens = {a["id"]: a for a in AV.atribuidas(EU_ID, EU_CONTA, "Fulana de Teste", AGORA)}
    assert set(itens) == {"L:900:202611100830", "A:400"}
    l = itens["L:900:202611100830"]
    assert l["titulo"] == "12 OS novas para você" and l["wid"] is None
    assert l["link"] == "/os/historico?modo=atribuidas&de=2026-11-10&ate=2026-11-10"
    assert "criadas por Programador Exemplo" in l["detalhe"]
    assert all(AV.AVISO_RE.fullmatch(i) for i in itens)
    # quem criou sem o id vira um código curto do nome (nunca o nome no aviso_id, que vai em claro ao banco)
    AV.limpar()
    _lista(monkeypatch, [R(500 + i, str(18800 + i), id_criador=None, minuto=m) for i in range(3)])
    (a,) = AV.atribuidas(EU_ID, EU_CONTA, "Fulana de Teste", AGORA)
    assert re.fullmatch(r"L:[0-9a-f]{10}:202611100830", a["id"]) and "Programador" not in a["id"]


def test_o_sino_usa_quem_a_pessoa_e_no_fracttal(app, banco, limpo, limpos, monkeypatch):  # noqa: F811
    """A sessão pela conta Microsoft traz o nome escrito de outro jeito ("Fulana T."): até 08/11/2026 o aviso de execução
    casava só por ele e não achava a OS. Agora o catálogo de pessoas do OS Creator, pelo e-mail, dá o id, a conta e o nome
    que o Fracttal grava."""
    exec_ = R(601, "18900", criado_por="Fulana de Teste", status_id=2, atribuido=1234,
              data_fim=(datetime.now(timezone.utc) - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S"))
    exec_.atribuido_a = "Técnico Exemplo"                       # quem executou (a própria pessoa não se avisa)
    agora = datetime.now(BRT)
    nova = R(602, "18901", minuto=agora - timedelta(hours=1))
    _lista(monkeypatch, [exec_, nova])
    monkeypatch.setattr(AV, "ATRIBUIDAS_DESDE", "2026-01-01")
    monkeypatch.setattr(AV, "_do_fracttal", lambda email: (EU_ID, EU_CONTA, "Fulana de Teste"))
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logado=True, admin=False, usuario=dict(PESSOA, nome="Fulana T."))
    html = c.get("/").get_data(as_text=True)
    sino = html.split('class="sino-topo"', 1)[1].split("</details>", 1)[0]
    assert "2 avisos das suas OS" in sino
    assert "OS 18900 concluída pelo técnico" in sino and "OS 18901 criada para você" in sino
    assert ">Para você</span>" in sino and "sino-sev--pedido" in sino
    # o "Marcar todas" leva também o aviso novo
    c.post(LIDA, data={"todos": "1", "voltar": "/"})
    linhas = banco.linhas(AV.LIVRO, AV.ABA)
    assert sorted((l["aviso_id"][:2], l["tipo"]) for l in linhas) == [("A:", "atribuida"), ("E:", "execucao")]


def test_o_lote_no_sino_leva_ao_historico(app, banco, limpo, limpos, monkeypatch):  # noqa: F811
    agora = datetime.now(BRT).replace(second=10, microsecond=0) - timedelta(hours=1)
    _lista(monkeypatch, [R(700 + i, str(19000 + i), minuto=agora + timedelta(seconds=i)) for i in range(4)])
    monkeypatch.setattr(AV, "ATRIBUIDAS_DESDE", "2026-01-01")
    monkeypatch.setattr(AV, "_do_fracttal", lambda email: (EU_ID, EU_CONTA, "Fulana de Teste"))
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logado=True, admin=False, usuario=dict(PESSOA))
    sino = c.get("/").get_data(as_text=True).split('class="sino-topo"', 1)[1].split("</details>", 1)[0]
    assert "4 OS novas para você" in sino and 'class="sino-aviso-lista"' in sino
    assert "/os/historico?modo=atribuidas&amp;de=" in sino
    aid = re.search(r'name="aviso" value="(L:[^"]+)"', sino).group(1)
    c.post(LIDA, data={"aviso": aid, "voltar": "/"})
    assert [(l["aviso_id"], l["tipo"]) for l in banco.linhas(AV.LIVRO, AV.ABA)] == [(aid, "atribuida")]


def test_sem_o_catalogo_segue_o_nome_da_sessao(monkeypatch):
    """Sem o clone ou sem a pessoa no catálogo, (None, None, ""): o sino segue como antes, pelo nome da sessão."""
    from nexus.torres.oscreator import ponte

    def quebra(nome):
        raise ImportError("sem o clone")
    monkeypatch.setattr(ponte, "modulo_do_clone", quebra)
    assert AV._do_fracttal("fulana@exemplo.test") == (None, None, "")
    assert AV._do_fracttal("") == (None, None, "")


def test_o_id_do_aviso_novo_e_o_de_lixo():
    for ok in ("A:123", "L:900:202611100830", "L:0a1b2c3d4e:202611100830"):
        assert AV.AVISO_RE.fullmatch(ok), ok
    for ruim in ("A:", "L:900:2026", "L:Fulana:202611100830", "A:1<script>"):
        assert not AV.AVISO_RE.fullmatch(ruim), ruim


def test_a_ligacao_do_setor_da_o_id_mesmo_sem_o_email_no_fracttal(app, monkeypatch):
    """A conta Microsoft com um e-mail que o Fracttal não tem: o id vem da ligação de Pessoas e setores (o código do e-mail
    na última decisão), e a conta e o nome, do catálogo pelo id."""
    from nexus.auth import setor_telas as ST
    from nexus.torres.oscreator import ponte
    with app.test_request_context():
        app.config["NEXUS_PESSOA_HMAC"] = "chave-de-teste"
        codigo = AV._codigo("fulana@exemplo.test")
        decisoes = [{"decidida_em": "2026-11-01T10:00:00Z", "pessoa_hmac": codigo, "fracttal_id": 111},
                    {"decidida_em": "2026-11-05T10:00:00Z", "pessoa_hmac": codigo, "fracttal_id": EU_ID},
                    {"decidida_em": "2026-11-06T10:00:00Z", "pessoa_hmac": "outro", "fracttal_id": 222}]
        monkeypatch.setattr(ST, "_banco", lambda: ("http://banco", None))
        monkeypatch.setattr(ST, "_setores_no_clique", lambda base, sessao: {"decisoes": decisoes})

        class Cat:
            @staticmethod
            def pessoas_guardadas():
                return [{"id_personnel": EU_ID, "id_account": EU_CONTA, "name": "Fulana de Teste", "email_h": "x"}], "rpc"

            @staticmethod
            def _hash_email(e):
                return "nao-casa"

            @staticmethod
            def _achar(linhas, h):
                return None
        monkeypatch.setattr(ponte, "modulo_do_clone", lambda nome: Cat)
        assert AV._do_fracttal_agora("fulana@exemplo.test") == (EU_ID, EU_CONTA, "Fulana de Teste")
        # sem o catálogo, fica o id da ligação (o aviso de OS atribuída já sai)
        monkeypatch.setattr(ponte, "modulo_do_clone", lambda nome: (_ for _ in ()).throw(ImportError("sem o clone")))
        assert AV._do_fracttal_agora("fulana@exemplo.test") == (EU_ID, None, "")
