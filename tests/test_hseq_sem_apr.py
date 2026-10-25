"""Atividades feitas sem APR ou sem PT (24/10/2026, `nexus/hseq/apr.py`, a aba "Sem APR ou PT" da tela de APR e PT). A
TST: "preciso de uma visibilidade de atividades realizadas sem APR e sem PT, por exemplo essa APR OS #16866 precisa de
PT, porém o técnico não fez". O livro da APR é o que o App publica desde a v298 do servidor (`apr_app_campo · APR`).

O banco falso do Campo (test_campo_visao.py): três tarefas da OS 800 fechadas pelo App em Altair, há 5, 6 e 7 horas."""
from datetime import datetime, timedelta, timezone

from test_campo_visao import CHAVE, _aba, banco  # noqa: F401  (banco é fixture)

from nexus.campo import visao
from nexus.campo.ligacao_cadastro import codigo_da_pessoa

TEC = codigo_da_pessoa(CHAVE, "tec1@exemplo.test")


def _apr(os_, dia, precisa="sim", pt="", tipo="do dia", **kw):
    d = {"APR": f"20261020T000000-{os_}", "Tipo": tipo, "OS": os_, "Dia": dia, "Criada em": f"{dia}T12:00:00.000Z",
         "Usina": "Thopen - Altair 1 - SP", "Técnico (HMAC)": TEC, "Tarefa": "", "Código do ativo": "", "Versões": 1,
         "Atividades críticas": "Proteção para trabalhos com eletricidade", "Precisa de PT": precisa, "PT": pt}
    d.update(kw)
    return d


def _dias_dos_fechamentos():
    brt = timezone(timedelta(hours=-3))
    return sorted({(datetime.now(timezone.utc) - timedelta(hours=h)).astimezone(brt).date().isoformat()
                   for h in (5, 6, 7)})


def test_sem_o_livro_da_apr_a_aba_diz_e_nao_quebra(banco, logado):
    html = logado.get("/t/hseq/apr-pt?aba=sem").get_data(as_text=True)
    assert 'aria-current="page">Sem APR ou PT</a>' in html and "O livro da APR ainda não chegou" in html


def test_a_apr_que_pedia_pt_e_ficou_sem(banco, logado):
    _aba(banco, "apr_app_campo", "APR", [
        _apr("16866", "2026-10-20"),                                             # pedia PT e ficou sem
        _apr("16867", "2026-10-20", pt="PT-16867-2010-1000"),                    # teve PT: não entra
        _apr("16868", "2026-10-20", precisa=""),                                 # ainda não medida: não entra
        _apr("16869", "2026-10-20", precisa="não", **{"Atividades críticas": ""})])
    visao.limpar()
    html = logado.get("/t/hseq/apr-pt?aba=sem").get_data(as_text=True)
    corpo = html[html.index("<tbody>"):html.index("</tbody>")]
    assert ">16866<" in corpo and ">16867<" not in corpo and ">16868<" not in corpo and ">16869<" not in corpo
    assert "Proteção para trabalhos com eletricidade" in corpo and "Altair" in corpo and "Técnico Silva" in corpo
    assert '<select class="gc-campo" id="pt-cliente"' in html and '<option value="Thopen">Thopen (1)</option>' in html
    assert "Nenhuma APR pedindo PT" in logado.get("/t/hseq/apr-pt?aba=sem&cliente=Outro+Cliente").get_data(as_text=True)


def test_a_os_fechada_sem_apr_e_a_que_tem(banco, logado):
    _aba(banco, "apr_app_campo", "APR", [_apr("16866", "2026-10-20")])
    visao.limpar()
    html = logado.get("/t/hseq/apr-pt?aba=sem&tipo=apr").get_data(as_text=True)
    corpo = html[html.index("<tbody>"):html.index("</tbody>")]
    assert ">800<" in corpo and "Altair" in corpo and "Preventiva" in corpo           # as tarefas da OS 800, sem APR
    # com a APR do dia da OS 800 (nos dias em que as tarefas fecharam), sai
    _aba(banco, "apr_app_campo", "APR", [_apr("800", d) for d in _dias_dos_fechamentos()])
    visao.limpar()
    html = logado.get("/t/hseq/apr-pt?aba=sem&tipo=apr").get_data(as_text=True)
    assert "Nenhuma OS fechada pelo App sem APR" in html


def test_o_livro_da_apr_esta_no_catalogo_antes_da_primeira_gravacao():
    from nexus.dados import catalogo as C
    from nexus.hseq import apr as APR
    f = {x.id: x for x in C.FATOS}["apr"]
    assert f.livro == f"{APR.LIVRO} · {APR.ABA}" and f.area == "hseq"
