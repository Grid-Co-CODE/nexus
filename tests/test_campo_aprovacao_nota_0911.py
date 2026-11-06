"""O motivo da nota abaixo de 80 na Aprovação de OS (Levi, 09/11/2026, pelo Scrum master: "Em OS 8159 aprovação de OS diz
que está aprovado porém a OS tem nota 50 no app, o interessante é ele saber o motivo da nota, tem que ter 'motivo da
nota abaixo de 80'"). A nota do App abaixo de 80 deixa a OS Em dúvida (era só aviso, e a OS caía em Pronta), com o
porquê pela "Composição da nota" que o App grava; e a mensagem do PDF e do Aprovar separa a sessão que acabou do
servidor que não respondeu (o chat OS Creator, no mesmo dia)."""
import json
from pathlib import Path

from test_campo_prefiltro import FECHADO, P, _anexada, _fatos, _os, _tarefa

from nexus.campo import aprovacao, nota_app, prefiltro

COMPOSICAO = json.dumps([
    {"rot": "Subtarefas obrigatórias", "peso": 30, "pts": 30, "det": "5 de 5 respondidas"},
    {"rot": "Fotos", "peso": 25, "pts": 0, "det": "0 de 4 pedidas"},
    {"rot": "Observações", "peso": 20, "pts": 20, "det": ""},
    {"rot": "Fotos com descrição", "peso": 15, "pts": 5, "det": "1 de 3 com descrição"},
    {"rot": "Assinatura", "peso": 10, "pts": 0, "det": "não assinou"}])
MOTIVO = ("Fotos perdeu 25 de 25 (0 de 4 pedidas); Fotos com descrição perdeu 10 de 15 (1 de 3 com descrição); "
          "Assinatura perdeu 10 de 10 (não assinou)")


def test_o_motivo_sai_da_composicao_o_que_mais_perdeu_primeiro():
    assert nota_app.motivo(55, COMPOSICAO) == MOTIVO
    assert nota_app.motivo(80, COMPOSICAO) == "" and nota_app.motivo(None, COMPOSICAO) == ""   # nada a explicar
    # sem a composição no livro, diz isso em vez de inventar o porquê ("sem dado não se inventa")
    assert nota_app.motivo(50, "") == nota_app.motivo(50, "lixo") == "o App não guardou a composição desta nota"
    assert nota_app.motivo(60, [{"rot": "Fotos", "peso": 25, "pts": 13.3}]) == "Fotos perdeu 11,7 de 25"


def test_nota_abaixo_de_80_deixa_a_os_em_duvida_com_o_motivo():
    fatos = _fatos([{"id": "1", "anexada": _anexada(1)}])
    # sem nada contra nos fatos, a OS com nota 95 segue Pronta (a leitura rápida das respostas e do GPS, da 4ª rodada,
    # dada como feita e sem nada: `meta` = {})
    assert prefiltro.classificar(_os(_tarefa(qualidade=95, id_wt="7")), fatos, FECHADO, P, {})["coluna"] == "pronta"
    r = prefiltro.classificar(_os(_tarefa(qualidade=55, id_wt="7", nota_itens=COMPOSICAO)), fatos, FECHADO, P, {})
    assert r["coluna"] == "duvida"
    nota = [a for a in r["avisos"] if a["tipo"] == "nota"]
    assert len(nota) == 1 and nota[0]["nivel"] == "alerta"
    assert nota[0]["texto"] == f"Nota do App 55%, abaixo de 80%: {MOTIVO}"
    # o motivo é o destaque do cartão e não se repete como aviso solto da regra do App
    assert "nota" in prefiltro.TIPOS_DO_MOTIVO
    assert not any(a["tipo"] == "app" and a["texto"].startswith("Nota do App") for a in r["avisos"])
    # ainda sem as fotos lidas: a nota já basta para a dúvida (como a OS fechada fora do App)
    assert prefiltro.classificar(_os(_tarefa(qualidade=55, id_wt="7")), None, FECHADO, P)["coluna"] == "duvida"


def test_a_ronda_e_a_tarefa_fora_do_app_nao_entram_na_regra_da_nota():
    """A nota da ronda vem com as falhas (outro aviso) e a tarefa fora do App não tem nota do App."""
    fatos = _fatos([{"id": "1", "anexada": _anexada(1)}])
    r = prefiltro.classificar(_os(_tarefa(qualidade=40, ronda=True, id_wt="7")), fatos, FECHADO, P)
    assert not any(a["tipo"] == "nota" for a in r["avisos"])


def test_o_motivo_da_barra_lateral_traz_o_porque_da_nota():
    m = aprovacao.motivos(_tarefa(qualidade=55, nota_itens=COMPOSICAO))
    assert ("alerta", f"Nota do App 55%, abaixo de 80%: {MOTIVO}") in m


def test_a_composicao_da_nota_vem_do_fechamento_da_mesma_nota(monkeypatch):
    """A nota da fila é a de um fechamento da OS no registro do App; o porquê vem do fechamento com a MESMA nota, o mais
    novo (a OS fechada duas vezes no App tem duas composições)."""
    linhas = [{"os": "8159", "qualidade": 70, "server_ts": "2026-11-01T10:00:00Z", "nota_itens": "velha"},
              {"os": "8159", "qualidade": 50, "server_ts": "2026-11-02T10:00:00Z", "nota_itens": "a de 50"},
              {"os": "8159", "qualidade": 50, "server_ts": "2026-11-01T09:00:00Z", "nota_itens": "a de 50 antiga"},
              {"os": "", "qualidade": 10, "server_ts": "2026-11-02T10:00:00Z", "nota_itens": "sem os"}]

    class _Tabela:
        def query_entities(self, _filtro):
            return iter(linhas)
    monkeypatch.setattr(aprovacao.regras_app, "tabela_qlog", lambda: _Tabela())
    comp = aprovacao._composicao_da_nota()
    assert aprovacao._composicao_de(comp, "8159", 50) == "a de 50"
    assert aprovacao._composicao_de(comp, "8159", 70) == "velha"
    assert aprovacao._composicao_de(comp, "8159", 99) == "" and aprovacao._composicao_de(comp, "1", 50) == ""


def test_o_pdf_e_o_aprovar_separam_a_sessao_do_servidor_sem_resposta():
    js = Path(__file__).resolve().parents[1].joinpath("nexus", "torres", "campo", "templates", "campo",
                                                      "aprovacao.html").read_text(encoding="utf-8")
    assert "if (r.redirected || !r.json) { dizer(SESSAO); return; }" not in js            # o caso da OS 8159
    assert "if (r.redirected) { dizer(SESSAO); return; }" in js
    assert "if (!r.json) { dizer(SEM_RESPOSTA_PDF); return; }" in js
    assert "O servidor não respondeu a tempo: tente de novo em instantes. Nada foi gravado no Fracttal." in js
    # no Aprovar a resposta sem JSON pode ter gravado: manda conferir no Fracttal e para o lote com a mesma frase
    assert "if (!r.json) { msg(c, SEM_RESPOSTA_APROVAR, 'critico'); return 'sem_resposta'; }" in js
    assert "r === 'sem_resposta' ? SEM_RESPOSTA_APROVAR" in js and "r === 'sem_resposta') { parar(c, r)" in js
