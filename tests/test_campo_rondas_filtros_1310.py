"""Rondas: filtrar por cliente, usina, responsável e equipe (Levi, 13/10/2026: "deve dar para filtrar cliente, usina,
responsável e equipe!"). O responsável é o Responsável O&M da ficha da usina, o mesmo da Central de atenção.

Banco falso do test_campo_visao, com os responsáveis do test_campo_central_responsavel: Altair (2 rondas) e Brodowski 1
(1 ronda), da equipe SP Norte 01, cliente Thopen e responsável Ciclano Chefe; Coração 1 (nunca teve ronda), da equipe
SC Oeste 01, cliente Outro Cliente e responsável Beltrano Supervisor."""
import re

from test_campo_central_responsavel import com_responsavel  # noqa: F401  (fixture)
from test_campo_visao import banco  # noqa: F401  (fixture)


def _select(html, nome):
    """([(valor, rótulo)], valor escolhido) do <select name=...> da barra."""
    sel = html.split('<select class="gc-campo" name="%s"' % nome, 1)[1].split("</select>", 1)[0]
    ops = re.findall(r'<option value="([^"]*)"(?: selected)?>([^<]*)</option>', sel)
    escolhido = re.search(r'<option value="([^"]*)" selected>', sel)
    return ops, (escolhido.group(1) if escolhido else "")


def _usinas_na_tabela(html):
    """Os ids das usinas com link ao histórico na tabela que a aba mostra."""
    return re.findall(r'href="/t/campo/rondas/usina/(\d+)"', html)


def test_a_barra_tem_cliente_usina_responsavel_e_equipe(com_responsavel, logado):
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    for nome, todos in (("cliente", "todos os clientes"), ("usina", "todas as usinas"),
                        ("responsavel", "todos os responsáveis"), ("equipe", "todas as equipes")):
        ops, escolhido = _select(html, nome)
        assert ops[0][1] == todos and escolhido in ("", "*"), nome
    assert _select(html, "usina")[0][1:] == [("1", "Altair"), ("2", "Brodowski 1"), ("3", "Coração 1")]
    assert [r for _v, r in _select(html, "responsavel")[0][1:]] == ["Beltrano Supervisor", "Ciclano Chefe"]
    assert [r for _v, r in _select(html, "equipe")[0][1:]] == ["SC Oeste 01", "SP Norte 01"]
    # a busca da tabela leva os filtros novos junto
    busca = html.split('class="cn-busca"', 1)[1].split("</form>", 1)[0]
    assert "'usina'" not in busca              # (o laço do template não vaza para a página)
    h = logado.get("/t/campo/rondas?usina=1&responsavel=Ciclano+Chefe").get_data(as_text=True)
    busca = h.split('class="cn-busca"', 1)[1].split("</form>", 1)[0]
    assert '<input type="hidden" name="usina" value="1">' in busca
    assert '<input type="hidden" name="responsavel" value="Ciclano Chefe">' in busca


def test_a_usina_filtra_a_tabela_e_o_csv(com_responsavel, logado):
    todas = _usinas_na_tabela(logado.get("/t/campo/rondas").get_data(as_text=True))
    assert sorted(set(todas)) == ["1", "2"]                       # Coração 1 nunca teve ronda: fora dos Registros
    h = logado.get("/t/campo/rondas?usina=1").get_data(as_text=True)
    assert _select(h, "usina")[1] == "1" and set(_usinas_na_tabela(h)) == {"1"} and len(_usinas_na_tabela(h)) == 2
    csv = logado.get("/t/campo/rondas?usina=1&csv=1").get_data(as_text=True).strip().splitlines()
    assert len(csv) == 3 and all(";Altair;" in linha for linha in csv[1:])
    # a usina sem ronda aparece na aba Sem ronda, e só ela
    sem = logado.get("/t/campo/rondas?usina=3&aba=sem").get_data(as_text=True)
    assert _usinas_na_tabela(sem) == ["3"]


def test_o_responsavel_filtra_as_rondas_e_a_cobertura(com_responsavel, logado):
    ciclano = logado.get("/t/campo/rondas?responsavel=Ciclano+Chefe").get_data(as_text=True)
    assert _select(ciclano, "responsavel")[1] == "Ciclano Chefe" and sorted(set(_usinas_na_tabela(ciclano))) == ["1", "2"]
    assert "Nenhuma usina mobilizada sem ronda" in logado.get("/t/campo/rondas?responsavel=Ciclano+Chefe&aba=sem").get_data(as_text=True)
    beltrano = logado.get("/t/campo/rondas?responsavel=Beltrano+Supervisor").get_data(as_text=True)
    assert _usinas_na_tabela(beltrano) == []                      # a usina dele nunca teve ronda
    assert _usinas_na_tabela(logado.get("/t/campo/rondas?responsavel=Beltrano+Supervisor&aba=sem").get_data(as_text=True)) == ["3"]
    # "todos" volta a tudo
    assert sorted(set(_usinas_na_tabela(logado.get("/t/campo/rondas?responsavel=*").get_data(as_text=True)))) == ["1", "2"]


def test_a_lista_de_usinas_encolhe_com_os_outros_filtros(com_responsavel, logado):
    def usinas(q):
        return [r for _v, r in _select(logado.get("/t/campo/rondas" + q).get_data(as_text=True), "usina")[0][1:]]
    assert usinas("?cliente=Outro+Cliente") == ["Coração 1"]
    assert usinas("?responsavel=Ciclano+Chefe") == ["Altair", "Brodowski 1"]
    assert usinas("?equipe=SC+Oeste+01") == ["Coração 1"]
    # a escolhida fica na lista mesmo fora dos outros filtros (nada some da barra sem o × de alguém)
    assert "Altair" in usinas("?cliente=Outro+Cliente&usina=1")


def test_a_equipe_e_o_cliente_combinam_com_os_novos(com_responsavel, logado):
    h = logado.get("/t/campo/rondas?equipe=SP+Norte+01&usina=2").get_data(as_text=True)
    assert set(_usinas_na_tabela(h)) == {"2"}
    h = logado.get("/t/campo/rondas?cliente=Thopen&responsavel=Beltrano+Supervisor").get_data(as_text=True)
    assert _usinas_na_tabela(h) == []                             # nenhuma usina do Thopen é do Beltrano
