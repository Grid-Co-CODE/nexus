"""O deploy espera a gravação do inventário (Levi, 26/10/2026; DEPLOY.md, seção 8).

Enquanto a gravação do inventário tem um lote aberto no Fracttal (a sessão de ajuste, modo 2), o almoxarifado fica travado.
Push na `main` reinicia o Nexus em ~2 min, e o restart no meio do lote mataria a gravação com o almoxarifado travado. O
`deploy/atualizar.sh` pergunta ao `ferramentas/gravacao_aberta.py` e, havendo lote aberto, deixa o restart para a rodada
seguinte, por no máximo 10 minutos contados da 1ª espera. Aqui: a decisão do ajudante (com o relógio de mentira) e o
script rodado no clone de mentira do `test_deploy_atualizar` (o ajudante ausente, o que pede espera, o que quebra)."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from test_deploy_atualizar import BASH, Servidor, _executavel

from ferramentas import gravacao_aberta as GA
from nexus.pcm.inventario import gravacao as G

AGORA = datetime(2026, 10, 26, 15, 0, tzinfo=timezone.utc)


def _controle(pasta, cid="C-1", estado="gravando", lote="aberto", salvo=AGORA - timedelta(seconds=20)):
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"{cid}.json").write_text(json.dumps({
        "contagem_id": cid, "id_almox": "10", "estado": estado, "lotes": [{"n": 1, "estado": lote}],
        "atualizado_em": salvo.strftime("%Y-%m-%dT%H:%M:%SZ")}), encoding="utf-8")


# ── a decisão ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_espera_o_lote_aberto_por_no_maximo_10_min(tmp_path):
    pasta = tmp_path / "almox_inventario"
    _controle(pasta)
    codigo, porque = GA.decidir(pasta, AGORA)
    assert codigo == 1 and (pasta / GA.MARCA).exists()                                  # a 1ª espera marca a hora
    assert "no máximo mais 10 min" in porque                                           # e não "mais 11" (27/10/2026)
    _controle(pasta, salvo=AGORA + timedelta(minutes=9, seconds=20))                   # a gravação viva salva sempre
    assert "no máximo mais 1 min" in GA.decidir(pasta, AGORA + timedelta(minutes=9, seconds=30))[1]
    _controle(pasta, salvo=AGORA + timedelta(minutes=8, seconds=50))                   # a gravação viva salva sempre
    assert GA.decidir(pasta, AGORA + timedelta(minutes=9))[0] == 1                     # ainda dentro dos 10 min
    _controle(pasta, salvo=AGORA + timedelta(minutes=9, seconds=50))                   # a gravação segue viva
    codigo, porque = GA.decidir(pasta, AGORA + timedelta(minutes=10))
    assert codigo == 0 and "reinicia assim mesmo" in porque and not (pasta / GA.MARCA).exists()
    # a próxima gravação aberta ganha os 10 min dela
    assert GA.decidir(pasta, AGORA + timedelta(minutes=10, seconds=10))[0] == 1


@pytest.mark.parametrize("estado, lote, salvo", [
    ("parada", "aberto", AGORA),                              # parada (sem login): esperar não a ajuda
    ("concluida", "feito", AGORA),
    ("encerrada", "feito", AGORA),
    ("gravando", "aberto", AGORA - timedelta(minutes=6)),    # "gravando" sem salvar há 6 min: o restart já a matou
])
def test_o_que_nao_segura_o_restart(tmp_path, estado, lote, salvo):
    pasta = tmp_path / "almox_inventario"
    _controle(pasta, estado=estado, lote=lote, salvo=salvo)
    (pasta / GA.MARCA).write_text(AGORA.isoformat(), encoding="utf-8")
    assert GA.decidir(pasta, AGORA)[0] == 0 and not (pasta / GA.MARCA).exists()


@pytest.mark.parametrize("lote", ["abrindo", "aberto", "fechando", "pendente", "feito"])
def test_a_gravacao_viva_segura_com_o_lote_aberto_e_entre_um_lote_e_outro(tmp_path, lote):
    """Os três estados da sessão seguram, e também a gravação VIVA entre um lote e outro (a revisão final de 27/10/2026): o
    intervalo entre lotes deixava o restart passar, e ele matava a gravação logo antes de abrir o lote seguinte."""
    pasta = tmp_path / "almox_inventario"
    _controle(pasta, lote=lote)
    assert GA.decidir(pasta, AGORA)[0] == 1


def test_sem_a_pasta_e_com_a_vez_e_o_ilegivel(tmp_path):
    """Sem a pasta (nenhuma gravação ainda): pode reiniciar. A vez do almoxarifado e o controle ilegível não contam."""
    assert GA.decidir(tmp_path / "nao_existe", AGORA)[0] == 0
    pasta = tmp_path / "almox_inventario"
    pasta.mkdir()
    (pasta / "trava-10.json").write_text(json.dumps({"contagem_id": "C-1"}), encoding="utf-8")
    (pasta / "C-9.json").write_text("{não é json", encoding="utf-8")
    assert GA.decidir(pasta, AGORA)[0] == 0


def test_main_acha_a_pasta_como_o_nexus_e_diz_esperar(tmp_path, capsys):
    """A pasta pela `NEXUS_DADOS`, como o Nexus a acha (`gravacao._pasta`); só a saída 1 COM a linha `ESPERAR` segura."""
    _controle(tmp_path / G.PASTA, salvo=AGORA)
    assert GA.main(cfg={"NEXUS_DADOS": str(tmp_path)}, agora=AGORA) == 1
    assert capsys.readouterr().out.strip() == GA.ESPERAR
    assert GA.main(cfg={"NEXUS_DADOS": str(tmp_path)}, agora=AGORA + timedelta(minutes=11)) == 0
    assert capsys.readouterr().out.strip() == ""


def test_qualquer_erro_deixa_o_deploy_seguir(tmp_path, monkeypatch, capsys):
    def quebra(*a, **kw):
        raise OSError("disco (de mentira)")
    monkeypatch.setattr(GA, "decidir", quebra)
    assert GA.main(cfg={"NEXUS_DADOS": str(tmp_path)}, agora=AGORA) == 0
    saida = capsys.readouterr()
    assert saida.out.strip() == "" and "OSError" in saida.err


# ── o script ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
# o python falso do clone: o ajudante responde pelo arquivo de controle do teste (espera, ou quebra sem o ESPERAR); o resto
# é a conferência do boot, como no test_deploy_atualizar
_PYTHON = r"""arq="${@: -1}"
case "$arq" in
  *gravacao_aberta.py)
    echo "ajudante $*" >> "$NEXUS_TESTE_LOG"
    if [ -e "$NEXUS_TESTE_CONTROLE/espera" ]; then echo ESPERAR; exit 1; fi
    if [ -e "$NEXUS_TESTE_CONTROLE/quebra" ]; then echo "Traceback (de mentira)" >&2; exit 1; fi
    exit 0 ;;
esac
echo "python $*" >> "$NEXUS_TESTE_LOG"
[ ! -e "$NEXUS_TESTE_CONTROLE/boot_falha" ]"""


def _servidor(tmp_path, com_ajudante=True):
    s = Servidor(tmp_path)
    _executavel(s.clone / ".venv" / "bin" / "python", _PYTHON)
    if com_ajudante:
        ajudante = s.clone / "ferramentas" / "gravacao_aberta.py"
        ajudante.parent.mkdir(exist_ok=True)
        ajudante.write_text("# o ajudante do Nexus que está no ar (o python falso responde por ele)\n")
    return s


@pytest.mark.skipif(BASH is None, reason="sem bash nesta máquina")
def test_o_script_espera_o_lote_aberto_e_depois_reinicia(tmp_path):
    s = _servidor(tmp_path)
    antes = s.head()
    s.commit("leia.txt", "novo\n")
    s.falhar("espera")
    codigo, feito, saida = s.rodar()
    assert (codigo, feito) == (0, ["pip", "python", "ajudante"]), saida              # sem restart
    assert s.head() == antes and "gravação do inventário está andando" in saida      # a pasta do serviço não andou
    s.falhar("espera", False)
    codigo, feito, saida = s.rodar()                                                 # a rodada seguinte: o lote fechou
    assert (codigo, feito) == (0, ["pip", "python", "ajudante", "systemctl"]), saida
    assert s.head() != antes


@pytest.mark.skipif(BASH is None, reason="sem bash nesta máquina")
def test_o_ajudante_que_quebra_nao_segura_o_deploy(tmp_path):
    """O ajudante que falha (sai com 1 sem o ESPERAR, como um Python ou um sudo que quebra): o deploy segue."""
    s = _servidor(tmp_path)
    s.falhar("quebra")
    codigo, feito, saida = s.rodar()
    assert (codigo, feito) == (0, ["pip", "python", "ajudante", "systemctl"]), saida


@pytest.mark.skipif(BASH is None, reason="sem bash nesta máquina")
def test_sem_o_ajudante_o_deploy_segue(tmp_path):
    """O 1º deploy que traz o ajudante: a pasta do serviço ainda não o tem, e o deploy segue como sempre."""
    s = _servidor(tmp_path, com_ajudante=False)
    codigo, feito, saida = s.rodar()
    assert (codigo, feito) == (0, ["pip", "python", "systemctl"]), saida
