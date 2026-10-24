"""O Acompanhamento de chamados que abriu com a leitura anterior troca sozinho quando a nova chega (24/10/2026,
`static/acomp.js`, `esperarANova`). Levi escolheu abrir a 1ª vez do dia com a lista de ontem (com a hora e o
"atualizando") em vez de esperar ~40 s o Fracttal; a tela pergunta ao `/os/chamados/acompanhamento/estado` de 5 em 5 s e
recarrega quando a hora da cópia muda. Roda o script de verdade no node, com o DOM, o fetch e o relógio de mentira."""
import json
import shutil
import subprocess

import pytest

from nexus.torres.oscreator import ponte

JS = ponte.RAIZ_CLONE + "/os_web/static/acomp.js"

RODAR = r"""
const fs = require("fs");
// node -e: argv[0] é o node, os argumentos começam no 1
const respostas = JSON.parse(process.argv[1]);
const comRenovando = process.argv[2] === "1";
let recarregou = 0, pedidos = 0, timers = [];
const fonte = {getAttribute: (k) => (k === "data-quando" ? "22/10/2026 18:10:00" : null)};
global.document = {
  querySelector: (sel) => (sel === ".ac-fonte[data-renovando]" ? (comRenovando ? fonte : null) : null),
  querySelectorAll: () => [], getElementById: () => null, addEventListener: () => {},
};
global.location = {reload: () => { recarregou += 1; }, pathname: "/", search: ""};
global.window = global;
global.OsCarga = {buscar: async () => ({})};
global.setInterval = (fn) => { timers.push(fn); return timers.length; };
global.clearInterval = (id) => { timers[id - 1] = null; };
global.fetch = async (url) => {
  pedidos += 1;
  const j = respostas[Math.min(pedidos - 1, respostas.length - 1)];
  return {ok: true, json: async () => j};
};
eval(fs.readFileSync(process.argv[3], "utf8"));
(async () => {
  for (let i = 0; i < 40; i++) {
    const fn = timers[0];
    if (!fn) break;
    await fn();
    await new Promise((r) => setImmediate(r));
  }
  console.log(JSON.stringify({recarregou, pedidos, parou: !timers[0]}));
})();
"""


def _rodar(respostas, renovando=True) -> dict:
    if not shutil.which("node"):
        pytest.skip("sem node nesta máquina")
    r = subprocess.run(["node", "-e", RODAR, json.dumps(respostas), "1" if renovando else "0", JS],
                       capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_recarrega_quando_a_nova_chega():
    velha = {"quando": "22/10/2026 18:10:00", "renovando": True}
    nova = {"quando": "24/10/2026 08:01:00", "renovando": False}
    assert _rodar([velha, velha, nova]) == {"recarregou": 1, "pedidos": 3, "parou": True}


def test_para_sem_recarregar_quando_a_releitura_termina_sem_copia_nova():
    """O Fracttal falhou: fica a lista que está, com a hora dela, e a tela para de perguntar."""
    assert _rodar([{"quando": "22/10/2026 18:10:00", "renovando": False}]) == \
        {"recarregou": 0, "pedidos": 1, "parou": True}


def test_desiste_em_3_minutos():
    r = _rodar([{"quando": "22/10/2026 18:10:00", "renovando": True}])
    assert r == {"recarregou": 0, "pedidos": 36, "parou": True}


def test_a_tela_lida_agora_nao_pergunta_nada():
    assert _rodar([{"quando": "x", "renovando": False}], renovando=False) == \
        {"recarregou": 0, "pedidos": 0, "parou": True}
