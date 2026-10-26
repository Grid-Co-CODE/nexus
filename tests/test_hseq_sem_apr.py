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


def _os_800_criada(banco, data_id=20261020):
    _aba(banco, "nexus_os", "fato_tarefa_os", [{"fracttal_tarefa_id": 1, "os": "800", "data_id_criacao": data_id},
                                               {"fracttal_tarefa_id": 2, "os": "800", "data_id_criacao": data_id + 2}])


def test_a_os_fechada_sem_apr_e_a_que_tem(banco, logado):
    """A régua do App (26/10/2026): a APR vale para a atividade, não para o dia; qualquer APR da OS até o dia do serviço
    cobre (a retomada de tarefa pausada não pede outra)."""
    _aba(banco, "apr_app_campo", "APR", [_apr("16866", "2026-10-20")])
    _os_800_criada(banco)
    visao.limpar()
    html = logado.get("/t/hseq/apr-pt?aba=sem&tipo=apr").get_data(as_text=True)
    corpo = html[html.index("<tbody>"):html.index("</tbody>")]
    assert ">800<" in corpo and "Altair" in corpo and "Preventiva" in corpo           # as tarefas da OS 800, sem APR
    assert "<th>Feita em</th>" in html and "<th>OS criada em</th>" in html and ">20/10/2026<" in corpo
    # uma APR da OS dias antes do serviço cobre (a tarefa iniciada com APR, pausada e fechada depois)
    from datetime import date as _date, timedelta as _td
    antes = (_date.fromisoformat(_dias_dos_fechamentos()[0]) - _td(days=3)).isoformat()
    _aba(banco, "apr_app_campo", "APR", [_apr("800", antes)])
    visao.limpar()
    assert "Nenhuma OS fechada pelo App sem APR" in logado.get("/t/hseq/apr-pt?aba=sem&tipo=apr").get_data(as_text=True)
    # a APR feita DEPOIS do serviço não cobre
    depois = (_date.fromisoformat(_dias_dos_fechamentos()[-1]) + _td(days=1)).isoformat()
    _aba(banco, "apr_app_campo", "APR", [_apr("800", depois)])
    visao.limpar()
    assert ">800<" in logado.get("/t/hseq/apr-pt?aba=sem&tipo=apr").get_data(as_text=True)


def test_a_os_criada_antes_do_registro_das_aprs_fica_fora(banco, logado):
    """A OS criada antes de 10/10 pode ter a APR por tarefa de antes do registro (a 14334: APR de 06/10, retomada 20 dias
    depois); a OS sem a data de criação (finalizada, fora do fato_tarefa_os) também fica fora."""
    _aba(banco, "apr_app_campo", "APR", [_apr("16866", "2026-10-20")])
    _os_800_criada(banco, 20261001)
    visao.limpar()
    assert "Nenhuma OS fechada pelo App sem APR" in logado.get("/t/hseq/apr-pt?aba=sem&tipo=apr").get_data(as_text=True)
    _aba(banco, "nexus_os", "fato_tarefa_os", [{"fracttal_tarefa_id": 1, "os": "999", "data_id_criacao": 20261020}])
    visao.limpar()
    assert "Nenhuma OS fechada pelo App sem APR" in logado.get("/t/hseq/apr-pt?aba=sem&tipo=apr").get_data(as_text=True)


def test_o_dia_do_servico_e_a_hora_do_celular(banco, logado):
    """O fechamento que chegou ao servidor dias depois (o celular offline) vale pelo dia em que o técnico fez: com a APR
    nesse dia, cobre (medido em 26/10: 4 OS da mesma usina feitas em 21 e 23/10 chegaram em 26/10)."""
    from test_campo_visao import _fech
    _aba(banco, "fechamentos_app_campo", "Fechamentos", [_fech(1, 90, **{"Hora do celular": "2026-10-21T13:00:00.000Z"})])
    _aba(banco, "apr_app_campo", "APR", [_apr("800", "2026-10-21")])
    _os_800_criada(banco, 20261020)
    visao.limpar()
    assert "Nenhuma OS fechada pelo App sem APR" in logado.get("/t/hseq/apr-pt?aba=sem&tipo=apr").get_data(as_text=True)
    _aba(banco, "apr_app_campo", "APR", [_apr("800", "2026-10-25")])
    visao.limpar()
    html = logado.get("/t/hseq/apr-pt?aba=sem&tipo=apr").get_data(as_text=True)
    assert ">800<" in html and ">21/10/2026<" in html                                  # feita em 21/10, sem APR até lá


def test_o_livro_da_apr_esta_no_catalogo_antes_da_primeira_gravacao():
    from nexus.dados import catalogo as C
    from nexus.hseq import apr as APR
    f = {x.id: x for x in C.FATOS}["apr"]
    assert f.livro == f"{APR.LIVRO} · {APR.ABA}" and f.area == "hseq"
