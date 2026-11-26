"""O card de assinar a PT (30/10/2026): o link do e-mail de PT aguardando do App abre a PT no Nexus, num card por cima da
tela desfocada, para o supervisor assinar pelo celular (Levi, pelo chat do App de Campo: "a parte de abrir PT e assinar
no e-mail automático deve encaminhar para o Nexus para eles assinarem por lá ... ao assinar ele vê também se tem mais
alguma aberta para alguma usina dele"). Desde a v314 do App o aviso vai ao Responsável UFV da ficha da usina, que por
isso também decide. Banco falso (pg_falso) e nomes de mentira (o repositório é público)."""
import json
import re
import time
from pathlib import Path
from test_campo_visao import ASSINATURA_PNG  # noqa: E402  (a assinatura de teste do De acordo)

import pytest

from nexus.cadastro.cifra import Cofre
from nexus.campo import decisao_pt, visao
from nexus.cadastro.ligacao_campo import codigo_da_pessoa
from test_campo_visao import (CHAVE, CHAVE_CADASTRO, USINAS, _aba, _entrar_no_fracttal, _jwt, _pessoas, _pt,
                              _pt4_de_dois_equipamentos, banco)  # noqa: F401 (banco é fixture)

RESP = "responsavel@exemplo.test"
CARD_PT1 = "/t/campo/pt/PT-1/assinar?ativo=THPN-ALT100-INVR1"


@pytest.fixture
def com_responsavel(banco):
    """A Altair (usina 1) com o Responsável UFV 94 na ficha (`responsavel_om_id`), como a ficha do Nexus que o App lê
    desde a v314; ele não é supervisor de campo, gestor de contrato nem do COS."""
    usinas = [dict(u, responsavel_om_id=94) if u["usina_id"] == 1 else u for u in USINAS]
    _aba(banco, "cadastro_nexus", "usinas", usinas)
    cofre = Cofre(CHAVE_CADASTRO)
    resp = {"pessoa_id": 94, "vinculo": "Supervisor", "cargo": None, "equipe_id": None, "status": "Ativo",
            "supervisor_id": None, "excluido": "não",
            "sensivel_cifrado": cofre.cifrar(json.dumps({"nome": "Responsável Exemplo", "nome_padrao": "Responsável Exemplo",
                                                         "email": RESP}), "banco/pessoas/94")}
    _aba(banco, "cadastro_nexus", "pessoas", _pessoas() + [resp])
    visao.limpar()
    return banco


def _sessao(app, email, nome="Pessoa Exemplo", admin=False):
    """A sessão do Nexus de uma pessoa pela conta Microsoft dela (a porta desde 14/10/2026: não cai junto com a do
    Fracttal, que só o OS Creator pede), sem ser administradora."""
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"], s["admin"], s["via"], s["ms_ate"] = True, admin, "microsoft", time.time() + 3600
        s["usuario"] = {"email": email, "nome": nome, "perfil": ""}
    return c


def test_o_responsavel_ufv_da_ficha_decide_a_pt(com_responsavel):
    p = visao.pt("PT-1")
    assert decisao_pt.pode_decidir(p, RESP) == (True, "responsável UFV")
    assert decisao_pt.aprovadores(p)["texto"].startswith("O Responsável UFV (Responsável Exemplo)")
    # os papéis de antes seguem: a supervisora de campo da região e o gestor de contrato
    assert decisao_pt.pode_decidir(p, "supervisora@exemplo.test") == (True, "supervisor de campo")
    assert decisao_pt.pode_decidir(p, "beltrano@exemplo.test") == (True, "gestor de contrato")
    # na usina de outro responsável, não: a Coração 1 não tem o 94 na ficha
    coracao = dict(p, usina_id=3)
    ok, porque = decisao_pt.pode_decidir(coracao, RESP)
    assert ok is False and "Responsável UFV" not in porque


def test_o_link_fixo_lista_as_pts_para_o_de_acordo_de_quem_entrou(app, com_responsavel):
    """O link para salvar no celular (Levi, 20/11/2026: "pode fazer um link específico para aprovação de PTs e APRs via
    celular?"): as PTs que a pessoa da sessão pode decidir, cada uma abrindo o card de assinar dela."""
    c = _sessao(app, RESP, "Responsável Exemplo")
    html = c.get("/t/campo/pt/assinar").get_data(as_text=True)
    assert "PTs para o seu De acordo" in html and 'href="/t/campo/pt/PT-1/assinar?ativo=THPN-ALT100-INVR1"' in html
    assert "Salve este endereço no celular" in html
    # quem não pode decidir nenhuma lê que não há, e quem o Nexus não acha no cadastro lê o que fazer
    outro = _sessao(app, "ninguem@exemplo.test", "Ninguém Exemplo")
    html = outro.get("/t/campo/pt/assinar").get_data(as_text=True)
    assert "/t/campo/pt/PT-1/assinar" not in html and "O Nexus não achou você no cadastro de pessoas" in html


def test_o_plantao_do_cos_vai_de_sexta_18h_a_segunda_6h():
    """Levi, 14/11/2026: "O pessoal do COS pode dar o de acordo a partir de sexta-feira, 6 horas da noite, até segunda,
    6 horas da manhã. Passou disso, só com o supervisor". No horário de Brasília."""
    from datetime import datetime
    h = lambda d, hora, minuto=0: datetime(2026, 11, d, hora, minuto, tzinfo=decisao_pt._BRT)  # noqa: E731
    assert not decisao_pt.cos_no_plantao(h(13, 17, 59)) and decisao_pt.cos_no_plantao(h(13, 18))      # sexta
    assert decisao_pt.cos_no_plantao(h(14, 12)) and decisao_pt.cos_no_plantao(h(15, 23, 59))         # sábado e domingo
    assert decisao_pt.cos_no_plantao(h(16, 5, 59)) and not decisao_pt.cos_no_plantao(h(16, 6))       # segunda
    assert not decisao_pt.cos_no_plantao(h(11, 3))                                                    # quarta
    # o feriado nacional inteiro também (Levi, 21/11/2026: "Sim, feriado conta como plantão"): Finados, uma segunda
    assert decisao_pt.cos_no_plantao(h(2, 10)) and decisao_pt.cos_no_plantao(h(20, 9))               # e a Consciência Negra
    # o ponto facultativo não ("Não, só feriado nacional"): Carnaval (terça) e Corpus Christi (quinta) de 2026
    from datetime import datetime
    assert not decisao_pt.cos_no_plantao(datetime(2026, 2, 17, 10, tzinfo=decisao_pt._BRT))
    assert not decisao_pt.cos_no_plantao(datetime(2026, 6, 4, 10, tzinfo=decisao_pt._BRT))


def test_o_setor_cos_dos_acessos_decide_a_pt_no_plantao(com_responsavel, monkeypatch):
    """O COS vale pelo setor da pessoa do login em Base → Acessos (as 11 pessoas do COS não têm ficha no cadastro, que é
    o do time de campo): sem ficha nenhuma, a pessoa do setor COS decide no plantão e só nele."""
    from datetime import datetime

    from nexus.cadastro import setores as S
    cos = "plantao.cos@exemplo.test"
    _aba(com_responsavel, S.LIVRO, S.ABA_SETOR, [{"setor_id": 5, "nome": "COS", "criado_em": "2026-10-12",
                                                  "alterado_em": "", "excluido": "não"}])
    com_responsavel._id(S.LIVRO, S.ABA_DECISAO)["linhas"] = [
        {"headers": list(S.CAB_DECISAO),
         "values": ["2026-10-12T10:00:00-03:00", 20261012, 700, "", "", codigo_da_pessoa(CHAVE, cos), 5, "", "tela"]}]
    S._CACHE.clear()
    p = visao.pt("PT-1")
    monkeypatch.setattr(decisao_pt, "_agora", lambda: datetime(2026, 11, 14, 22, tzinfo=decisao_pt._BRT))  # sábado
    assert decisao_pt.pode_decidir(p, cos) == (True, "COS")
    monkeypatch.setattr(decisao_pt, "_agora", lambda: datetime(2026, 11, 16, 9, tzinfo=decisao_pt._BRT))   # segunda 9h
    ok, porque = decisao_pt.pode_decidir(p, cos)
    assert ok is False and "plantão" in porque and "Responsável UFV (Responsável Exemplo)" in porque
    # quem não está no setor COS segue sem poder, no plantão também
    monkeypatch.setattr(decisao_pt, "_agora", lambda: datetime(2026, 11, 14, 22, tzinfo=decisao_pt._BRT))
    assert decisao_pt.pode_decidir(p, "outra.pessoa@exemplo.test")[0] is False
    S._CACHE.clear()


def test_o_card_mostra_a_pt_e_a_assinatura_volta_ao_card_com_as_outras(app, com_responsavel):
    c = _sessao(app, RESP, "Responsável Exemplo")
    html = c.get(CARD_PT1).get_data(as_text=True)
    assert 'class="pa-fundo"' in html and 'class="pa-card"' in html
    for txt in ("PT-1", "Técnico Silva", "Troca de string", "Inversor 1", "THPN-ALT100-INVR1", "700",
                "Eletricidade: 3 sim, 2 não, 0 NA", "2 itens marcados NÃO"):
        assert txt in html, txt
    assert 'action="/os/_nexus/pt/PT-1/decidir"' in html
    assert f'<input type="hidden" name="volta" value="{CARD_PT1}">' in html
    assert '<input type="hidden" name="card" value="1">' in html
    assert "Outras PTs esperando" not in html                       # a lista vem depois de assinar
    # só com a entrada do Nexus, sem o login do Fracttal (20/11/2026): grava, volta ao card com o aviso e as outras PTs
    # das usinas dele (a PT-2, da Altair)
    r = c.post("/os/_nexus/pt/PT-1/decidir", data={"decisao": "de_acordo", "assinatura_png": ASSINATURA_PNG, "codigo": "THPN-ALT100-INVR1",
                                                   "volta": CARD_PT1, "card": "1"})
    assert r.headers["Location"] == CARD_PT1
    linhas = com_responsavel.linhas("nexus_pt_decisoes", "fato_decisao_pt")
    assert [(d["pt"], d["codigo_ativo"], d["decisao"], d["decidida_por_hmac"]) for d in linhas] == [
        ("PT-1", "THPN-ALT100-INVR1", "de_acordo", codigo_da_pessoa(CHAVE, RESP))]
    html = c.get(CARD_PT1).get_data(as_text=True)
    assert "De acordo salvo." in html and "/decidir" not in html
    outras = html.split("Outras PTs esperando nas suas usinas", 1)[1]
    assert 'href="/t/campo/pt/PT-2/assinar?ativo=THPN-ALT100-INVR1"' in outras and "PT-1" not in outras.split("</section>")[0]
    # o aviso de gravada aparece uma vez só
    assert "De acordo salvo." not in c.get(CARD_PT1).get_data(as_text=True)
    # a outra abre no próprio card, com o formulário
    assert 'action="/os/_nexus/pt/PT-2/decidir"' in c.get("/t/campo/pt/PT-2/assinar?ativo=THPN-ALT100-INVR1").get_data(as_text=True)


def test_a_pt_ja_decidida_no_app_diz_quem_e_quando_sem_botao(com_responsavel, logado):
    html = logado.get("/t/campo/pt/PT-3/assinar?ativo=THPN-ALT100-INVR1").get_data(as_text=True)
    assert "/decidir" not in html and "no painel do App" in html and "(Admin)" in html
    # o administrador vê todas as que esperam, da mais antiga para a mais nova (PT-1 há 30 h, PT-2 há 1 h)
    outras = html.split("Outras PTs esperando nas suas usinas", 1)[1]
    assert outras.index("PT-1") < outras.index("PT-2")


def test_quem_nao_pode_assinar_ve_o_porque_sem_botao(app, com_responsavel):
    # quem pediu a PT (o técnico das PT do banco falso): o porquê e nenhuma outra dele para assinar
    html = _sessao(app, "tec1@exemplo.test", "Técnico Um").get(CARD_PT1).get_data(as_text=True)
    assert "Você não pode assinar esta PT." in html and "Quem pediu a PT não a decide" in html
    assert "/decidir" not in html and "Nenhuma outra PT esperando nas suas usinas." in html
    # quem não tem papel nesta usina: quem pode, com o Responsável UFV primeiro
    html = _sessao(app, "ninguem@exemplo.test", "Ninguém").get(CARD_PT1).get_data(as_text=True)
    assert "Você não pode assinar esta PT." in html and "o Responsável UFV (Responsável Exemplo)" in html
    assert "/decidir" not in html
    # e, sem ser achada no cadastro, o que fazer; quem pediu a PT lê só o porquê dele
    assert "O Nexus não achou você no cadastro de pessoas" in html
    assert "O Nexus não achou você" not in _sessao(app, "tec1@exemplo.test").get(CARD_PT1).get_data(as_text=True)


def test_a_pt_de_dois_equipamentos_pede_a_linha_e_a_que_nao_chegou_rele_uma_vez(app, banco, logado, monkeypatch):
    _pt4_de_dois_equipamentos(banco)
    html = logado.get("/t/campo/pt/PT-4/assinar").get_data(as_text=True)
    assert "Escolha o" in html and "/decidir" not in html
    assert 'href="/t/campo/pt/PT-4/assinar?ativo=THPN-ALT100-INVR1"' in html
    assert 'href="/t/campo/pt/PT-4/assinar?ativo=THPN-ALT100-INVR2"' in html
    assert 'action="/os/_nexus/pt/PT-4/decidir"' in logado.get(
        "/t/campo/pt/PT-4/assinar?ativo=THPN-ALT100-INVR2").get_data(as_text=True)
    # a PT que ainda não está na cópia: relê o livro na hora, uma vez por minuto no máximo
    from nexus.torres import campo
    relidas = []
    monkeypatch.setattr(visao, "esquecer_pt", lambda: relidas.append(1))
    monkeypatch.setitem(campo._RELIDA_PT, "em", 0.0)
    html = logado.get("/t/campo/pt/PT-9/assinar?ativo=").get_data(as_text=True)
    assert "Esta PT ainda não chegou ao Nexus." in html and relidas == [1]
    logado.get("/t/campo/pt/PT-9/assinar?ativo=")
    assert relidas == [1]


def test_os_itens_nao_vem_da_coluna_nova_do_livro(banco, logado):
    com_itens = dict(_pt("PT-1", 30), **{"Itens NÃO": "Bloqueio da fonte feito?; Área isolada e sinalizada?"})
    _aba(banco, "pt_app_campo", "PT", [com_itens, _pt("PT-2", 1)])
    visao.limpar()
    html = logado.get(CARD_PT1).get_data(as_text=True)
    lista = re.search(r'<ol class="pa-nao">(.*?)</ol>', html, re.S).group(1)
    assert "<li>Bloqueio da fonte feito?</li>" in lista and "<li>Área isolada e sinalizada?</li>" in lista
    assert "itens marcados NÃO no checklist" not in html          # com a lista, a contagem não se repete
    assert visao.pt("PT-2")["itens_nao"] == []                     # sem a coluna: lista vazia, o card mostra a contagem


def test_o_card_cabe_no_celular():
    css = (Path(__file__).resolve().parents[1] / "nexus" / "static" / "campo.css").read_text(encoding="utf-8")
    bloco = css[css.index("/* O card de assinar a PT"):]
    assert ".pa-fundo{position:fixed;inset:0" in bloco and "backdrop-filter:blur(6px)" in bloco
    celular = bloco[bloco.index("@media (max-width:600px)"):]
    assert ".pa-dados{grid-template-columns:minmax(0,1fr)" in celular and ".pa-botoes .gc-btn{flex-basis:100%}" in celular
    assert "min-height:44px" in bloco                               # o dedo acerta os botões e as linhas da lista


def test_a_decisao_passa_atras_do_proxy_que_troca_o_host(app, com_responsavel, monkeypatch):
    """30/10/2026, 1º dia do card: uma Responsável UFV deu o De acordo e leu "Origem recusada." No servidor da T.I. o
    Nexus não recebe o endereço público no Host, e a decisão comparava o Origin com ele: o mesmo POST com o Origin certo
    dava 403 em produção. Agora vale a régua da moldura (o Sec-Fetch-Site do navegador; sem ele, o Origin)."""
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"], s["admin"], s["via"], s["ms_ate"] = True, False, "microsoft", time.time() + 3600
        s["usuario"] = {"email": RESP, "nome": "Responsável Exemplo", "perfil": ""}
    _entrar_no_fracttal(app, c, _jwt(email=RESP), RESP, "Responsável Exemplo")
    form = {"decisao": "de_acordo", "assinatura_png": ASSINATURA_PNG, "codigo": "THPN-ALT100-INVR1", "volta": CARD_PT1, "card": "1"}
    # a camada da T.I.: o navegador fala com app.gridco.com.br, e o Nexus recebe outro Host (o pedido chega com os
    # cookies; só o Host muda no caminho)
    original = app.wsgi_app

    def proxy_da_ti(environ, start_response):
        environ["HTTP_HOST"] = "127.0.0.1:5070"
        return original(environ, start_response)
    monkeypatch.setattr(app, "wsgi_app", proxy_da_ti)
    proxy = {}
    # outro site (o navegador diz cross-site): recusa, nada grava
    r = c.post("/os/_nexus/pt/PT-1/decidir", data=form, headers={"Origin": "https://app.gridco.com.br",
                                                                  "Sec-Fetch-Site": "cross-site"}, **proxy)
    assert r.status_code == 403 and "nexus_pt_decisoes" not in com_responsavel.workbooks
    # a própria página (same-origin), com o Origin público que o Host não mostra: grava e volta ao card
    r = c.post("/os/_nexus/pt/PT-1/decidir", data=form, headers={"Origin": "https://app.gridco.com.br",
                                                                  "Sec-Fetch-Site": "same-origin"}, **proxy)
    assert r.status_code == 302 and r.headers["Location"].endswith(CARD_PT1)
    assert [d["decisao"] for d in com_responsavel.linhas("nexus_pt_decisoes", "fato_decisao_pt")] == ["de_acordo"]
