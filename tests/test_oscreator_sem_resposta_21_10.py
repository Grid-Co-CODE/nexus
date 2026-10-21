"""A gravação que fica sem resposta não vira erro técnico (21/10/2026). Levi criou uma OS pelo OS Creator (Performance ›
Trackers) às 10:03 e a tela disse "SyntaxError: Failed to execute 'json' on 'Response': Unexpected end of JSON input": o
deploy das 09:57 reiniciou o servidor no meio do pedido, o proxy devolveu a resposta vazia, e a OS 16932 tinha sido
criada no Fracttal (o ticket da aba Trackers, que vem depois, não). Quem lê "erro" cria de novo e duplica.

Agora o `OsCarga.buscar` (o `carga.js`, que toda tela do OS Creator usa para gravar) entrega, numa GRAVAÇÃO sem resposta
de verdade (vazia, o erro do proxy sem JSON, a rede que caiu), uma resposta em JSON com o aviso: as telas já mostram o
`erro` que vem no JSON, e o aviso diz para conferir antes de repetir. Leitura e resposta da própria rota (com o erro dela
em JSON) passam como vieram. Roda no node, com uma página de mentira."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from nexus.torres.oscreator import ponte

CARGA = Path(ponte.RAIZ_CLONE) / "os_web" / "static" / "carga.js"

PAGINA = r"""
function elem() { return {hidden: false, className: '', textContent: '', innerHTML: '', style: {},
  classList: {add() {}, remove() {}, toggle() {}}, setAttribute() {}, appendChild() {}, remove() {},
  addEventListener() {}, querySelector() { return elem(); }}; }
globalThis.document = {addEventListener() {}, createElement: elem, body: elem()};
globalThis.addEventListener = () => {};
globalThis.window = globalThis;
globalThis.location = {href: 'http://x/os/', origin: 'http://x', pathname: '/os/', search: ''};
"""

CASOS = r"""
const casos = {
  vazia_502: ['POST', () => Promise.resolve(new Response('', {status: 502}))],
  rede_caiu: ['POST', () => Promise.reject(new TypeError('Failed to fetch'))],
  ok_json: ['POST', () => Promise.resolve(new Response(JSON.stringify({ok: true, mensagem: 'criada'}),
                                                       {status: 200, headers: {'Content-Type': 'application/json'}}))],
  ok_vazia: ['POST', () => Promise.resolve(new Response('', {status: 200}))],
  erro_html_500: ['POST', () => Promise.resolve(new Response('<html>Internal Server Error</html>',
                                                             {status: 500, headers: {'Content-Type': 'text/html'}}))],
  ocupado_json_503: ['POST', () => Promise.resolve(new Response(JSON.stringify({erro: 'OS Creator ocupado'}),
                                                                {status: 503, headers: {'Content-Type': 'application/json'}}))],
  pdf: ['POST', () => Promise.resolve(new Response('%PDF-1.4', {status: 200, headers: {'Content-Type': 'application/pdf'}}))],
  leitura_vazia: ['GET', () => Promise.resolve(new Response('', {status: 502}))],
};
(async () => {
  const out = {};
  for (const [nome, [metodo, resposta]] of Object.entries(casos)) {
    globalThis.fetch = resposta;
    try {
      const r = await OsCarga.buscar('/os/api/x', {method: metodo}, 'Gravando…');
      const texto = await r.text();
      let j = null; try { j = JSON.parse(texto); } catch (e) { j = null; }
      out[nome] = {status: r.status, ok: r.ok, json: j, texto: j ? null : texto};
    } catch (e) { out[nome] = {lancou: String(e)}; }
  }
  OsCarga.esconder();
  console.log(JSON.stringify(out));
})();
"""


@pytest.fixture(scope="module")
def saida():
    if not shutil.which("node"):
        pytest.skip("sem node nesta máquina")
    js = PAGINA + CARGA.read_text(encoding="utf-8") + CASOS
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _aviso(caso) -> bool:
    j = caso.get("json") or {}
    return j.get("sem_resposta") is True and "confira" in j.get("erro", "") and caso["ok"] is False


def test_gravacao_com_resposta_vazia_vira_o_aviso(saida):
    assert _aviso(saida["vazia_502"]) and saida["vazia_502"]["status"] == 502
    assert _aviso(saida["ok_vazia"])                                   # 200 sem corpo: não dá para saber se gravou


def test_a_rede_que_caiu_no_meio_vira_o_aviso(saida):
    assert _aviso(saida["rede_caiu"])


def test_o_erro_do_servidor_sem_json_vira_o_aviso(saida):
    assert _aviso(saida["erro_html_500"]) and saida["erro_html_500"]["status"] == 500


def test_a_resposta_da_rota_passa_como_veio(saida):
    assert saida["ok_json"] == {"status": 200, "ok": True, "json": {"ok": True, "mensagem": "criada"}, "texto": None}
    assert saida["ocupado_json_503"]["json"] == {"erro": "OS Creator ocupado"}       # o recado do teto, em JSON
    assert saida["pdf"] == {"status": 200, "ok": True, "json": None, "texto": "%PDF-1.4"}


def test_leitura_nao_muda(saida):
    assert saida["leitura_vazia"] == {"status": 502, "ok": False, "json": None, "texto": ""}
