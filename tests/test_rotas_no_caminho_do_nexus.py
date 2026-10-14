"""Toda rota do Nexus mora num caminho que o Caddy do servidor manda ao Nexus (13/10/2026, Levi, com o print do "Not
Found" em app.gridco.com.br/atualizacoes: "Atualizações não carrega").

O caso: a aba Atualizações do Início nasceu em `/atualizacoes`. Com o Nexus na raiz de app.gridco.com.br, o Caddy
divide por caminho (DEPLOY.md, seção 5b): ao Nexus vão só a raiz exata, `/t/*`, `/entrar`, `/sair`, `/saude`, `/tema`,
`/os` e `/os/*` e o `/static/*` (menos os três estáticos da plataforma); todo o resto vai à plataforma. Nos testes e no
PC direto na 5070 a aba abria; no servidor, `/atualizacoes` caía na plataforma, que respondia o "Not Found" dela (sem
login, mandava ao `/login` da plataforma). A aba virou `/?aba=atualizacoes` (a raiz exata é do Nexus).

A mesma divisão é a da `ferramentas/porta_local.destino`, que o `app.py` do PC usa para juntar o Nexus e a plataforma
numa origem só: este teste passa cada rota do Nexus por ela. Rota nova fora desses caminhos: ponha debaixo de um deles
(a aba do Início é `/?aba=...`; a tela de torre é `/t/<torre>/<tela>`) ou combine a linha nova do Caddy com a T.I. e
acrescente o segmento no `SEGMENTOS_NEXUS` da porta_local no mesmo trabalho."""
import re

from ferramentas.porta_local import destino


def test_toda_rota_do_nexus_vai_ao_nexus_pela_divisao_do_caddy(app):
    fora = []
    for regra in app.url_map.iter_rules():
        caminho = re.sub(r"<[^>]+>", "x", regra.rule)
        if destino(caminho, "raiz")[0] != "nexus":
            fora.append(regra.rule)
    assert fora == [], f"rotas que, no servidor, o Caddy mandaria à plataforma: {fora}"


def test_a_aba_atualizacoes_e_a_raiz_com_a_aba(logado):
    assert destino("/", "raiz")[0] == "nexus" and destino("/atualizacoes", "raiz")[0] == "plataforma"
    html = logado.get("/").get_data(as_text=True)
    assert 'href="/?aba=atualizacoes"' in html and 'href="/atualizacoes"' not in html
    assert logado.get("/?aba=atualizacoes").status_code == 200
