"""O "Celular pronto" do Piloto da coleta no Mapa de equipe (10/11/2026; `nexus/campo/equipe/celulares.py`).

O Levi, pela sessão Nexus Field: "tem como sabermos qual o técnico não aceitou tudo? no caso de aceitar tudo e tirar a
restrição da bateria" ("Sim, constrói"). Desde a 1.2.2 a casca manda em cada lote (e no aviso sem permissão) os
`ajustes` do aparelho: a versão do termo aceita, a localização (precisa, aproximada, sem), o "Permitir o tempo todo", a
bateria sem restrição e a notificação. O Piloto diz, por técnico: "Celular pronto" com os cinco; senão "Falta:" e o que
falta; sem os ajustes, o porquê (versão antiga do app, não aceitou o termo, nunca abriu o app). A 1.2.1 não manda o campo
e o Nexus de antes o ignorava: o contrato segue compatível.

O estado mora no disco da pasta de dados (cifrado, como o diário), não no banco: é a configuração do aparelho por
pessoa, e o reinício (todo push) não o apaga. Pessoas e aparelhos de mentira; nada vai à rede."""
import pytest
from test_equipe_rotas import (AGORA, SUPERVISORA, TECNICO, _chave, _ponto, _posicoes, _reiniciar, banco,  # noqa: F401
                               ms, relogio)

from nexus.campo.equipe import TERMO_ATUAL
from nexus.campo.equipe import celulares as CE
from nexus.campo.equipe import servico as S

PRONTO = {"termo": TERMO_ATUAL, "localizacao": "precisa", "tempoTodo": True, "bateriaSemRestricao": True,
          "notificacao": True}


def test_a_leitura_dos_ajustes_e_o_que_falta():
    assert TERMO_ATUAL == "5"                       # o termo da 1.2.3 (10/11/2026: a seção 2 declara o Início automático)
    assert CE.ler(PRONTO) == PRONTO and CE.faltas(PRONTO) == []
    meio = {**PRONTO, "termo": "3", "localizacao": "aproximada", "bateriaSemRestricao": False}
    assert CE.faltas(CE.ler(meio)) == ["termo novo", "localização precisa", "bateria sem restrição"]
    assert CE.faltas(CE.ler({**PRONTO, "termo": None, "tempoTodo": False, "notificacao": False})) == [
        "termo novo", "Permitir o tempo todo", "notificação"]
    # o que não segue o contrato não vale (e não apaga o que já se sabia): None
    for torto in (None, "x", [], {**PRONTO, "localizacao": "longe"}, {**PRONTO, "tempoTodo": "sim"},
                  {**PRONTO, "termo": 4}, {k: v for k, v in PRONTO.items() if k != "notificacao"},
                  {**PRONTO, "termo": "x" * 40}):
        assert CE.ler(torto) is None, torto


def test_a_situacao_do_celular_em_palavras():
    assert CE.situacao(True, {"ajustes": PRONTO}) == {"pronto": True, "tom": "ok", "texto": "Celular pronto"}
    s = CE.situacao(True, {"ajustes": {**PRONTO, "localizacao": "aproximada", "bateriaSemRestricao": False}})
    assert (s["pronto"], s["tom"], s["texto"]) == (False, "alerta", "Falta: localização precisa, bateria sem restrição")
    assert CE.situacao(True, {"ajustes": None})["texto"] == "Versão antiga do app"
    assert CE.situacao(True, None)["texto"] == "Não aceitou o termo ou não abriu o app"
    assert CE.situacao(False, None)["texto"] == "Nunca abriu o app"
    assert CE.situacao(False, None)["tom"] == "neutro"


def test_o_lote_leva_os_ajustes_e_o_reinicio_nao_os_apaga(app, cliente, banco, ms):  # noqa: F811
    chave = _chave(cliente)
    srv = S.do_app(app)
    assert srv.celulares.de(TECNICO) is None
    # o lote da 1.2.2 com os ajustes
    meio = {**PRONTO, "bateriaSemRestricao": False}
    r = _posicoes(cliente, chave, [_ponto(2)], ajustes=meio)
    assert r.status_code == 200 and r.get_json()["aceitos"] == 1
    assert srv.celulares.de(TECNICO)["ajustes"] == meio
    # o aviso sem permissão também os leva
    _posicoes(cliente, chave, [], permissao="sem", ajustes=PRONTO)
    assert srv.celulares.de(TECNICO)["ajustes"] == PRONTO
    # o ajuste torto não apaga o que se sabia, e o lote nunca cai por ele
    r = _posicoes(cliente, chave, [_ponto(1)], ajustes={"termo": 4})
    assert r.status_code == 200 and srv.celulares.de(TECNICO)["ajustes"] == PRONTO
    # o reinício (todo push) relê do disco
    _reiniciar(app)
    assert S.do_app(app).celulares.de(TECNICO)["ajustes"] == PRONTO
    # o lote sem o campo (a 1.2.1 e as de antes): versão antiga
    _posicoes(cliente, chave, [_ponto(0)])
    assert S.do_app(app).celulares.de(TECNICO) == {"ajustes": None, "desde": "2026-11-08T15:00:00Z"}


def test_quem_tem_chave(app, cliente, banco, ms):  # noqa: F811
    srv = S.do_app(app)
    assert srv.chaveiro.pessoas() == set()
    _chave(cliente)
    assert srv.chaveiro.pessoas() == {TECNICO}


def test_o_piloto_mostra_o_celular_pronto_de_cada_um(app, cliente, banco, ms, monkeypatch):  # noqa: F811
    """Na tela, para o administrador, no Piloto da coleta: a situação do celular de quem está no piloto."""
    from nexus.campo import mapa_responsaveis as MR
    monkeypatch.setattr(MR, "coordenadas", lambda: ({}, ""))
    app.config["NEXUS_ADMINS"] = "admin.teste@gridco.com.br"          # o administrador é conferido pela lista
    chave = _chave(cliente)
    _posicoes(cliente, chave, [_ponto(2)], ajustes={**PRONTO, "localizacao": "aproximada"})
    with cliente.session_transaction() as s:
        s["logado"], s["admin"] = True, True
        s["usuario"] = {"email": "admin.teste@gridco.com.br", "nome": "Admin Teste", "perfil": ""}
    html = cliente.get("/t/campo/equipe", query_string={"painel": "tecnicos"}).get_data(as_text=True)
    piloto = html.split('class="eq-piloto"', 1)[1].split("</details>", 1)[0]
    assert "Falta: localização precisa" in piloto and 'class="cn-pill cn-alerta eq-celular"' in piloto
    _posicoes(cliente, chave, [_ponto(1)], ajustes=PRONTO)
    html = cliente.get("/t/campo/equipe", query_string={"painel": "tecnicos"}).get_data(as_text=True)
    piloto = html.split('class="eq-piloto"', 1)[1].split("</details>", 1)[0]
    assert '<span class="cn-pill cn-ok eq-celular">Celular pronto</span>' in piloto


# ── parte 2 (10/11/2026): o Início automático do Xiaomi e o termo pela versão ─────────────────────────────────────
def test_o_inicio_automatico_do_xiaomi_entra_no_falta():
    """A casca 1.2.3 manda o 6º campo, `inicioAutomatico` (true, false ou null; null = não é Xiaomi/Redmi/POCO ou não se
    sabe). O caso, no celular do Levi pelo cabo: sem o Início automático do HyperOS o Android barra o app depois de
    atualizar ("process is not permitted to auto start") e a coleta não volta. Só o false falta."""
    assert CE.ler({**PRONTO, "inicioAutomatico": True}) == {**PRONTO, "inicioAutomatico": True}
    assert CE.faltas(CE.ler({**PRONTO, "inicioAutomatico": None})) == []
    assert CE.faltas(CE.ler({**PRONTO, "inicioAutomatico": False})) == ["Início automático"]
    assert CE.situacao(True, {"ajustes": CE.ler({**PRONTO, "inicioAutomatico": False, "notificacao": False})})[
        "texto"] == "Falta: notificação, Início automático"
    assert CE.ler({**PRONTO, "inicioAutomatico": "sim"}) is None              # fora do contrato
    assert CE.ler(PRONTO) == PRONTO                                            # a 1.2.2, sem o campo, segue valendo


def test_o_termo_vale_pela_versao_igual_ou_maior():
    """O termo aceito vale quando é número e não é menor que o TERMO_ATUAL: a ordem da subida não importa (o Nexus no "4"
    já aceita o "5" da 1.2.3; quando o TERMO_ATUAL subir para "5", a 1.2.2 passa a "Falta: termo novo")."""
    assert CE.faltas(CE.ler({**PRONTO, "termo": "5"})) == [] and CE.faltas(CE.ler({**PRONTO, "termo": "6"})) == []
    # desde a 1.2.3 (TERMO_ATUAL "5"), o celular ainda na 1.2.2 (termo "4") falta o termo novo
    assert CE.faltas(CE.ler({**PRONTO, "termo": "4"})) == ["termo novo"]
    assert CE.faltas(CE.ler({**PRONTO, "termo": "3"})) == ["termo novo"]
    assert CE.faltas(CE.ler({**PRONTO, "termo": "beta"})) == ["termo novo"]     # não é número: não vale
    assert CE.faltas(CE.ler({**PRONTO, "termo": None})) == ["termo novo"]
