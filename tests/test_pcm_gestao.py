"""Gestão PCM no Nexus (Levi, 07/10/2026: "traga a visão de acompanhamento de manutenção do aplicativo para o Nexus
conforme prints"): o bloco "Manutenções — Plano & Fila" do painel do PCM (js/preventivas.js do gridco-pcm-data),
com as mesmas contas. Regras puras em nexus/pcm/gestao.py; tela em nexus/pcm/telas.py.

Nenhum teste vai à rede: a fonte é um arquivo local no formato do gestao_pcm.json, com datas relativas a hoje.
"""
import base64
import json
import os

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from nexus.pcm import gestao as G

H = G.hoje()
M = G.meses(H)          # [mês retrasado, mês passado, mês corrente]


def t(usina, tarefa, estado, mes=None, tipo="Preventiva", os_="100", cluster="SP Leste 02", resp="Responsável A",
      criacao=None, dia="10"):
    mes = mes or M[2]
    return {"os": os_, "cliente": usina.split(" - ")[0], "usina": usina, "cluster": cluster, "responsavel": resp,
            "tipo": tipo, "tarefa": tarefa, "estado": estado, "aberta": estado != "Finalizada", "osStatus": "",
            "dataProg": f"{mes}-{dia}", "criacao": f"{criacao or mes}-05", "etiquetas": [], "atrasado": False}


ALTAIR, TUCANO = "Thopen - Altair 1 - SP", "Semp - Tucano 1 - BA"


def tarefas():
    return [
        t(ALTAIR, "MPM das cabines", "Finalizada", os_="101"),
        t(ALTAIR, "MPM inversores", "Não Iniciada", os_="101"),
        t(ALTAIR, "MPA da usina", "Finalizada", os_="102"),
        t(ALTAIR, "MPA trackers", "Não Iniciada", os_="102"),
        t(ALTAIR, "Fusível queimado", "Finalizada", tipo="Corretiva", os_="103", mes=M[2], criacao=M[1]),
        t(ALTAIR, "Disjuntor", "Não Iniciada", tipo="Corretiva Emergencial", os_="104"),
        t(TUCANO, "MPT da usina", "Finalizada", os_="201", cluster="BA Sul 01", resp="Responsável B", mes=M[1]),
        t(TUCANO, "Religar inversor", "Finalizada", tipo="Religamento Remoto", os_="202", cluster="BA Sul 01",
          resp="Responsável B"),
        # fora da conta: tipo Teste, Preventiva sem sigla, mês fora da janela e usina sem cadastro
        t(ALTAIR, "Verificação de cadastro", "Finalizada", tipo="Teste", os_="900"),   # sem sigla: o tipo decide
        t(ALTAIR, "Limpeza geral", "Finalizada", os_="901"),
        t(ALTAIR, "MPM antiga", "Finalizada", os_="902", mes="2020-01"),
        {**t(ALTAIR, "MPM sem usina", "Finalizada", os_="903"), "usina": "(sem usina)"},
    ]


def test_base_preventiva_pelo_mes_programado_e_demanda_pela_criacao():
    b = G.base(G.escopo(tarefas()), M)
    chave = {(r["usi"], r["sig"], r["mes"]): (r["f"], r["t"]) for r in b}
    assert chave[(ALTAIR, "MPM", M[2])] == (1, 2) and chave[(ALTAIR, "MPA", M[2])] == (1, 2)
    assert chave[(ALTAIR, "corr", M[1])] == (1, 1)              # a corretiva conta no mês em que foi CRIADA
    assert chave[(ALTAIR, "emerg", M[2])] == (0, 1)
    assert chave[(TUCANO, "relig", M[2])] == (1, 1)             # religamento remoto agrupa com o religamento
    assert len(b) == 6                                          # Teste, sem sigla, fora da janela e sem usina: fora


def test_matriz_padrao_por_cliente_com_o_geral_sem_as_corretivas():
    mx = G.matriz(G.base(G.escopo(tarefas()), M), G.Opcoes(), M)
    assert mx["cols"] == ["MPM", "MPT", "MPS", "MPA", "CORR"]
    thopen = next(g for g in mx["grupos"] if g["nome"] == "Thopen")
    assert (thopen["cel"]["MPM"]["f"], thopen["cel"]["MPM"]["t"]) == (1, 2)
    assert (thopen["cel"]["CORR"]["f"], thopen["cel"]["CORR"]["t"]) == (1, 2)       # corretiva + emergencial
    assert (thopen["tudo"]["f"], thopen["tudo"]["t"]) == (2, 4)                       # o Geral: só as preventivas
    assert [g["nome"] for g in mx["grupos"]] == ["Thopen", "Semp"]                    # mais pendentes primeiro
    assert (mx["total"]["tudo"]["f"], mx["total"]["tudo"]["t"], mx["usinas"]) == (3, 5, 2)


def test_colunas_por_mes_com_todos_somam_as_corretivas_como_no_painel():
    mx = G.matriz(G.base(G.escopo(tarefas()), M), G.Opcoes(dim="res", col="mes"), M)
    assert mx["cols"] == M
    ana = next(g for g in mx["grupos"] if g["nome"] == "Responsável A")
    assert (ana["cel"][M[1]]["f"], ana["cel"][M[1]]["t"]) == (1, 1)
    assert (ana["tudo"]["f"], ana["tudo"]["t"]) == (3, 6)     # no painel, Mês + Todos põe corretiva no Geral


def test_celula_mpa_em_fracao_que_abre_a_fila_e_o_resto_pelo_valor():
    mx = G.matriz(G.base(G.escopo(tarefas()), M), G.Opcoes(), M)
    altair = next(f for g in mx["grupos"] for f in g["filhos"] if f["nome"] == ALTAIR)
    c = G.celula(altair["cel"]["MPA"], "MPA", G.Opcoes(), ALTAIR)
    assert (c["txt"], c["cls"], c["drill"]) == ("1/2", "and", True)
    assert G.celula(altair["cel"]["MPM"], "MPM", G.Opcoes(), ALTAIR)["txt"] == "50%"
    assert G.celula(altair["cel"]["MPM"], "MPM", G.Opcoes(val="pend"), ALTAIR)["txt"] == "1"
    assert G.celula(None, "MPS", G.Opcoes(), ALTAIR) == {"txt": "—", "cls": "nulo", "drill": False, "os": ""}
    assert "102 (1/2)" in c["os"] and "#" not in c["os"]          # OS só com o número (convenção do Nexus)


def test_busca_sem_acento_e_mes():
    b = G.base(G.escopo(tarefas()), M)
    assert [g["nome"] for g in G.matriz(b, G.Opcoes(busca="tucano"), M)["grupos"]] == ["Semp"]
    assert G.matriz(b, G.Opcoes(mes=M[0]), M)["grupos"] == []


def test_fila_pelo_fracttal_atraso_pela_programada():
    ts = [t(ALTAIR, "MPA da usina", "Não Iniciada", os_="102", mes=M[0], dia="01"),
          t(ALTAIR, "MPA trackers", "Finalizada", os_="102", mes=M[0], dia="03"),
          t(TUCANO, "MPS inversores", "Finalizada", os_="301")]
    fila = G.fila_fracttal(G.escopo(ts), H)
    a = next(x for x in fila if x["os"] == "102")
    assert (a["tipo"], a["sit"]["k"], a["prog"], a["bdFin"], a["bdTot"]) == ("MPA", "Atrasada", f"{M[0]}-01", 1, 2)
    assert a["atraso"] == G.dias(f"{M[0]}-01", H)
    assert next(x for x in fila if x["os"] == "301")["sit"]["k"] == "Concluída"


def test_ultima_observacao_datada_e_criticidade():
    log = "• 02/09/2026 - pediu peça\n• 15/09/2026 - peça chegou\n• 01/08/2026 - aberta"
    assert G.ultima_obs(log) == "15/09/2026 - peça chegou"
    assert [G.crit_cls(c) for c in ("Muito Crítico", "Alta", "Média", "Baixa", "")] == ["crit", "crit", "and", "ok", ""]
    assert G.norm("Utragaz – Ibirapuã 200 - BA") == "ultragaz ibirapua 2"


def _pacote(dados, senha):
    salt, iv = os.urandom(16), os.urandom(12)
    chave = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=1000).derive(senha.encode())
    ct = AESGCM(chave).encrypt(iv, json.dumps(dados).encode(), None)
    b = lambda x: base64.b64encode(x).decode()          # noqa: E731
    return {"cifrado": True, "iter": 1000, "salt": b(salt), "iv": b(iv), "ct": b(ct), "geradoEm": "x", "itens": 1}


def _gerencial():
    ontem = H.isoformat()[:8] + "01" if H.day > 1 else H.isoformat()
    return {"manut": [
        {"tipo": "MPA", "cliente": "Thopen", "usina": "Thopen – Altair 1", "usina_curta": "Altair 1", "cluster": "SP Leste 02",
         "os": "102", "prevista": f"{M[0]}-05", "criticidade": "Crítico", "status": "",
         "obs": "• 01/09/2026 - aguardando peça\n• 20/09/2026 - peça chegou"},
        {"tipo": "MPS", "cliente": "Semp", "usina": "Semp – Tucano 1", "usina_curta": "Tucano 1", "cluster": "BA Sul 01",
         "os": "", "prevista": "2099-01-01", "criticidade": "Média", "status": "", "obs": ""},
        {"tipo": "MPA", "cliente": "Semp", "usina": "Semp – Tucano 1", "usina_curta": "Tucano 1", "os": "301",
         "prevista": ontem, "criticidade": "Baixa", "status": "Finalizado", "obs": ""}],
        "bd": {"102": {"fin": 1, "total": 2, "tasks": [{"prog": f"{M[1]}-20"}]},
               "301": {"fin": 3, "total": 3, "sit": "Concluída", "tasks": [{"prog": f"{M[0]}-02"}]}}}


def test_decifra_o_mpas_do_painel_e_monta_a_fila_da_gerencial():
    assert G.decifrar(_pacote(_gerencial(), "abc"), "abc")["manut"][0]["os"] == "102"
    with pytest.raises(Exception):
        G.decifrar(_pacote(_gerencial(), "abc"), "errada")
    fila = G.fila_gerencial(_gerencial(), H)
    a, b, c = fila
    assert (a["sit"]["k"], a["prog"], a["atraso"], a["critSemData"], a["obs"]) == (
        "Atrasada", f"{M[1]}-20", G.dias(f"{M[0]}-05", H), True, "20/09/2026 - peça chegou")
    assert (b["semOS"], b["sit"]["k"], b["critCls"]) == (True, "Não iniciada", "and")
    assert c["conclu"] and c["atraso"] is None
    par = G.par_topo(G.base(G.escopo(tarefas()), M), M, fila)
    assert (par["rotina"], par["atrasadas"], par["mais_antiga"], par["crit_sem_data"], par["sem_os"]) == (
        50, 1, G.dias(f"{M[0]}-05", H), 1, 1)


def test_criticidade_e_observacao_por_usina_para_o_plano():
    mapa = G.crit_obs(_gerencial())
    assert G.achar(mapa, ALTAIR) == {"crit": "Crítico", "obs": "20/09/2026 - peça chegou"}
    assert G.achar(mapa, "Outra - Usina - MG") is None


# ── a tela ───────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def com_fonte(app, tmp_path):
    p = tmp_path / "gestao_pcm.json"
    p.write_text(json.dumps({"geradoEm": "2026-10-07T19:36:01", "tarefas": tarefas()}), encoding="utf-8")
    app.config["NEXUS_PCM_GESTAO_FONTE"] = str(p)
    return tmp_path


def test_tela_plano_mostra_a_matriz_e_os_controles(logado, com_fonte):
    r = logado.get("/t/pcm/gestao")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "Plano &amp; Fila" in html and "TOTAL GERAL" in html and "Thopen" in html and ALTAIR in html
    assert "50%" in html and "1/2" in html and "modo=fila" in html          # a fração da MPA abre a Fila
    assert "Corretivas" in html and "do plano do mês concluído" in html
    html = logado.get("/t/pcm/gestao?dim=res&col=mes&val=pend").get_data(as_text=True)
    assert "Responsável A" in html and G.rot_mes(M[1]) in html


def test_tela_fila_sem_a_chave_da_gerencial_mostra_o_lado_fracttal_sem_parecer_erro(logado, com_fonte):
    """Levi (08/10/2026): sem a senha do mpas.json a Fila mostra só o lado do Fracttal, e a tela diz isso sem
    parecer erro: nota informativa (não o aviso amarelo) e os números do Fracttal no topo."""
    html = logado.get("/t/pcm/gestao?modo=fila").get_data(as_text=True)
    assert "Programada" in html and "102" in html and "Tarefas" in html
    assert "Enquanto este Nexus não tem a chave" in html and "pcm-aviso--alerta" not in html
    assert "MPA e MPS pelo Fracttal" in html and "pela Data Programada" in html
    assert "sem OS no Fracttal" not in html and "críticas sem data futura" not in html   # não existem sem a Gerencial
    assert 'href="?modo=fila&amp;pend=atraso"' in html and 'href="?modo=fila&amp;pend=concl"' in html


def test_tela_fila_com_a_chave_da_gerencial(app, logado, com_fonte):
    p = com_fonte / "mpas.json"
    p.write_text(json.dumps(_pacote(_gerencial(), "s3nha-de-teste-xyz")), encoding="utf-8")
    app.config.update(NEXUS_PCM_MPAS_FONTE=str(p), NEXUS_PCM_MPAS_SENHA="s3nha-de-teste-xyz")
    html = logado.get("/t/pcm/gestao?modo=fila").get_data(as_text=True)
    assert "peça chegou" in html and "Crítico" in html and "críticas sem data futura" in html
    assert "chave da Gerencial" not in html
    html = logado.get("/t/pcm/gestao").get_data(as_text=True)
    assert "Criticidade · observação" in html and "peça chegou" in html
    assert "s3nha-de-teste-xyz" not in html                               # a senha nunca vai para a página


def test_chave_errada_da_gerencial_avisa_e_a_fila_segue_com_o_fracttal(app, logado, com_fonte):
    p = com_fonte / "mpas.json"
    p.write_text(json.dumps(_pacote(_gerencial(), "a-certa")), encoding="utf-8")
    app.config.update(NEXUS_PCM_MPAS_FONTE=str(p), NEXUS_PCM_MPAS_SENHA="a-errada")
    html = logado.get("/t/pcm/gestao?modo=fila").get_data(as_text=True)
    assert "pcm-aviso--alerta" in html and "não abriu o mpas.json" in html     # aqui é falha de verdade: amarelo
    assert "Programada" in html and "102" in html and "a-errada" not in html


def test_tela_sem_fonte_avisa(logado):
    r = logado.get("/t/pcm/gestao")
    assert r.status_code == 200 and "Não consegui ler" in r.get_data(as_text=True)


# ── o que a sessão de 08/10 acrescentou ──────────────────────────────────────────────────────────────────────
def test_kpi_concluidas_filtra_a_fila():
    """O KPI "concluídas" é um filtro (pend=concl): a URL o descartava e a Fila voltava inteira (a prova achou)."""
    o = G.opcoes({"modo": "fila", "pend": "concl"}, M)
    assert o.pend == "concl"
    fila = G.fila_gerencial(_gerencial(), H)
    assert [x["os"] for x in G.fila_filtrada(fila, o)] == ["301"]
    assert G.opcoes({"pend": "qualquer"}, M).pend == "todas"


def test_data_invalida_rola_como_no_navegador():
    """O painel lê 30/02 como 02/03 (new Date do navegador); mês 13 e dia 32 são inválidos nos dois."""
    assert G.dias("2026-02-30", H) == G.dias("2026-03-02", H) is not None
    assert G.dias("2026-13-01", H) is None and G.dias("2026-02-32", H) is None and G.dias("2026-2-3", H) is None


def test_drill_da_fracao_e_filtro_de_usina_de_cima_nao_se_confundem():
    fila = G.fila_fracttal(G.escopo([t(ALTAIR, "MPA da usina", "Não Iniciada", os_="102"),
                                     t(TUCANO, "MPS inversores", "Finalizada", os_="301")]), H)
    o = G.opcoes({"modo": "fila", "drill": ALTAIR, "dt": "MPA"}, M)
    assert (o.drill_usina, o.drill_tipo) == (ALTAIR, "MPA")
    assert [x["os"] for x in G.fila_filtrada(fila, o)] == ["102"]
    assert G.opcoes({"usina": ALTAIR}, M).drill_usina == ""            # "usina" é o filtro de cima
    assert {x["usina"] for x in G.filtrar_topo(G.escopo(tarefas()), usina=ALTAIR.upper())} == {ALTAIR}


def test_escolhas_de_cima_juntam_grafias_que_so_mudam_na_maiuscula():
    ts = [t(ALTAIR, "MPM", "Finalizada", cluster="PA Norte 01"), t(ALTAIR, "MPM", "Finalizada", cluster="PA Norte 01"),
          t(TUCANO, "MPM", "Finalizada", cluster="PA NORTE 01")]
    e = G.escolhas_topo(ts)
    assert e["cluster"] == ["PA Norte 01"] and e["usina"] == [TUCANO, ALTAIR]


def test_fila_da_gerencial_obedece_os_filtros_de_cima_com_nome_frouxo():
    fila = G.fila_universo([], _gerencial(), {"cliente": "SEMP", "usina": "", "cluster": "", "responsavel": ""}, H)
    assert {x["cli"] for x in fila} == {"Semp"}
    fila = G.fila_universo([], _gerencial(), {"cliente": "", "usina": ALTAIR, "cluster": "", "responsavel": ""}, H)
    assert [x["os"] for x in fila] == ["102"]                        # "Thopen - Altair 1 - SP" acha "Thopen – Altair 1"


def test_tela_plano_filtros_de_cima_e_drill(logado, com_fonte):
    html = logado.get("/t/pcm/gestao?usina=" + ALTAIR).get_data(as_text=True)
    assert ALTAIR in html and "Tucano" not in html.split("<tbody>")[1] and "Limpar filtros" in html
    html = logado.get("/t/pcm/gestao").get_data(as_text=True)
    assert "drill=Thopen" in html and "dt=MPA" in html                 # a fração MPA abre a Fila da usina
    html = logado.get("/t/pcm/gestao?modo=fila&drill=" + ALTAIR + "&dt=MPA").get_data(as_text=True)
    assert "Filtrado:" in html and "voltar ao Plano" in html and "301" not in html.split("<tbody>")[1]


def test_tela_usinas_dos_grupos_vem_escondidas_e_sem_emoji(logado, com_fonte):
    import re
    html = logado.get("/t/pcm/gestao").get_data(as_text=True)
    assert re.search(r'<tr class="pg-usina pg-filho" data-g="\d+" hidden>', html)   # abre no clique, como o painel
    html += logado.get("/t/pcm/gestao?modo=fila").get_data(as_text=True)
    assert not re.search("[\U0001F000-\U0001FAFF☀-➿]", html)   # severidade por cor e palavra, sem emoji


def test_gestao_pcm_aparece_no_menu_da_torre_pcm_como_tela_pronta(app, logado):
    from nexus.torres import telas_com_conteudo
    assert "/t/pcm/gestao" in telas_com_conteudo(app)
    assert '<a href="/t/pcm/gestao" class="com-conteudo"' in logado.get("/").get_data(as_text=True)


def test_fonte_confere_com_etag_e_nao_baixa_de_novo_o_que_nao_mudou(app, monkeypatch):
    """O gestao_pcm.json tem 14,7 MB: a cada 5 min o Nexus pergunta ao GitHub se mudou (If-None-Match) e, com o
    304, segue com a cópia em memória em vez de baixar e ler de novo (1,3 s medidos em 08/10/2026)."""
    import io
    import urllib.error
    from nexus.pcm import fonte
    corpo = json.dumps({"geradoEm": "x", "tarefas": []}).encode()
    pedidos = []

    class Resp(io.BytesIO):
        headers = {"ETag": '"v1"'}

    def abrir(req, timeout=None):
        pedidos.append(req.get_header("If-none-match"))
        if req.get_header("If-none-match") == '"v1"':
            raise urllib.error.HTTPError(req.full_url, 304, "Not Modified", {}, None)
        return Resp(corpo)
    url = "https://exemplo.invalido/gestao_pcm.json"
    monkeypatch.setattr(fonte.urllib.request, "urlopen", abrir)
    monkeypatch.setattr(fonte, "TTL_S", 0)
    monkeypatch.setitem(app.config, "NEXUS_PCM_GESTAO_FONTE", url)
    fonte._cache.pop(url, None)
    a = fonte.ler_gestao(app.config)
    b = fonte.ler_gestao(app.config)
    assert pedidos == [None, '"v1"'] and b.dados is a.dados and not b.velha and not b.erro
    fonte._cache.pop(url, None)


def test_arquivo_novo_do_robo_tira_da_memoria_o_que_era_da_versao_velha(logado, com_fonte):
    """Cada versão do gestao_pcm.json prende ~49 MB de tarefas: a nova entra, a velha sai inteira."""
    from nexus.pcm import telas
    p = com_fonte / "gestao_pcm.json"
    for h in ("versao-a", "versao-b"):
        p.write_text(json.dumps({"geradoEm": "2026-10-08T12:00:00", "dataHash": h, "tarefas": tarefas()}), encoding="utf-8")
        assert logado.get("/t/pcm/gestao").status_code == 200
    chaves = [k for k in telas._G_CACHE if isinstance(k, tuple)]
    assert chaves and all("versao-a" not in k for k in chaves) and any("versao-b" in k for k in chaves)


# ── o que a revisão de 08/10 acertou ─────────────────────────────────────────────────────────────────────────
def _fonte_unica(com_fonte, ts, versao):
    """O cache da tela é pela versão do arquivo: cada teste com tarefas próprias precisa de uma versão própria."""
    p = com_fonte / "gestao_pcm.json"
    p.write_text(json.dumps({"geradoEm": "2026-10-08T12:00:00", "dataHash": versao, "tarefas": ts}), encoding="utf-8")


def test_celula_de_grupo_nao_diz_sem_preventiva_quando_tem_tarefa(logado, com_fonte):
    """O painel põe a dica "sem preventiva no período" nas células de grupo e do TOTAL, que têm tarefa (68% com a
    dica dizendo que não há preventiva). No Nexus, a célula de usina mostra as OS e a de grupo fica sem dica."""
    mx = G.plano(G.base(G.escopo(tarefas()), M), G.Opcoes(), M)
    thopen = next(g for g in mx["grupos"] if g["nome"] == "Thopen")
    assert thopen["tds"][0]["txt"] == "50%" and thopen["tds"][0]["os"] == ""
    assert "101 (1/2)" in thopen["filhos"][0]["tds"][0]["os"]
    _fonte_unica(com_fonte, tarefas(), "rev-grupo")
    corpo = logado.get("/t/pcm/gestao").get_data(as_text=True).split("<tbody>")[1].split("</tbody>")[0]
    assert "sem preventiva no período" not in corpo and 'title="OS — 101 (1/2)' in corpo   # a legenda fica


def test_cabecalho_tipo_da_fila_ordena_pelo_tipo():
    """No painel o Tipo não ordena nada (a chave não existe e cai na Prevista); aqui ordena."""
    ts = [t(TUCANO, "MPS inversores", "Não Iniciada", os_="301"), t(ALTAIR, "MPA da usina", "Não Iniciada", os_="102"),
          t(TUCANO, "MPS cabine", "Não Iniciada", os_="302")]
    fila = G.fila_fracttal(G.escopo(ts), H)
    assert [x["tipo"] for x in G.fila_filtrada(fila, G.opcoes({"modo": "fila", "ordemf": "tipo"}, M))] == ["MPA", "MPS", "MPS"]
    assert [x["tipo"] for x in G.fila_filtrada(fila, G.opcoes({"modo": "fila", "ordemf": "tipo", "descf": "1"}, M))][0] == "MPS"


def test_atrasada_ha_menos_de_um_dia_nao_vira_nenhuma_vencida(logado, com_fonte, monkeypatch):
    """Venceu ontem e ainda não deu meio-dia: é atrasada com 0 dia (o painel conta do meio-dia). O par do topo dizia
    "1 OS atrasada" e, embaixo, "nenhuma com a data vencida"."""
    from datetime import datetime, timedelta
    manha = datetime.combine(H, datetime.min.time(), G._BRT).replace(hour=9)
    monkeypatch.setattr(G, "agora", lambda: manha)
    ontem = (H - timedelta(days=1)).isoformat()
    ts = [{**t(ALTAIR, "MPA da usina", "Não Iniciada", os_="102"), "dataProg": ontem}]
    _fonte_unica(com_fonte, ts, "rev-ontem")
    html = logado.get("/t/pcm/gestao?modo=fila").get_data(as_text=True)
    assert "1 <small>OS atrasada</small>" in html and "vencida há menos de 1 dia" in html
    assert "nenhuma com a data vencida" not in html


def test_filtros_de_cima_em_cascata():
    """Levi, 09/10/2026: "Os filtros tem que se auto filtrar também": escolhido o cliente, Usina, Equipe cluster e
    Responsável só listam os dele; o cliente não se restringe a si mesmo; o valor escolhido fica na lista."""
    ts = [t(ALTAIR, "MPM", "Finalizada", cluster="SP Leste 02", resp="Responsável A"),
          t(TUCANO, "MPM", "Finalizada", cluster="BA Sul 01", resp="Responsável B")]
    e = G.escolhas_topo(ts, {"cliente": "thopen", "usina": "", "cluster": "", "responsavel": ""})
    assert e["usina"] == [ALTAIR] and e["cluster"] == ["SP Leste 02"] and e["responsavel"] == ["Responsável A"]
    assert e["cliente"] == ["Semp", "Thopen"]
    e = G.escolhas_topo(ts, {"cliente": "Thopen", "usina": TUCANO, "cluster": "", "responsavel": ""})
    assert TUCANO in e["usina"] and e["cluster"] == []
    assert G.escolhas_topo(ts) == G.escolhas_topo(ts, {})          # sem filtro, tudo como antes
