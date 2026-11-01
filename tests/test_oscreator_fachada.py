"""A fachada do `api` depois de o arquivo ser repartido (31/10/2026, etapa 5.3 do canto central).

O `api.py` tinha 6.631 linhas, e cada assunto (criar OS, o Histórico, o card, as solicitações...) morava nele. Na 5.3 cada assunto
foi para o módulo dele, sem mudar uma linha do código além do prefixo `api.` (README do OS Creator, "O mapa dos módulos"). O que a
ponte, as rotas e os testes conhecem continua sendo o `api.X`, e é por esse nome que os testes TROCAM as funções
(`monkeypatch.setattr(api, "_rpc_call", ...)`): se o código que mudou de lugar chamasse a função do módulo dele pelo nome local, a
troca não valeria, e o teste passaria sem testar nada. O que estes testes seguram:
- todo nome que o `api` tinha antes da 5.3 (406, em `oscreator_nomes_do_api.json`) continua nele;
- o que saiu do `api.py` mora num dos módulos do mapa (e não em outro lugar qualquer);
- nenhuma função de módulo chama outra função do mesmo arquivo pelo nome local: vai pelo `api.`, como o teste a troca;
- todo `api.X` escrito nos módulos existe de verdade (um `api.` posto na frente de uma variável local quebraria só na hora de
  rodar aquele caminho);
- toda função que um módulo importa de OUTRO módulo do clone (o `montar_registros` do `ativos_central`) também vai pelo `api.`;
- qualquer módulo pode ser importado antes do `api` (os 14 que o `api` reexporta terminam com `import api`; o `os_juntar` chama o
  `api` na hora, pelo `_api()`, e o `fracttal_erro` não o importa).
Nada aqui vai à rede."""
import ast
import importlib
import inspect
import json
import subprocess
import sys
import symtable
from pathlib import Path

import pytest

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone

CLONE = Path(ponte.RAIZ_CLONE)
NOMES_ANTES = json.loads(Path(__file__).with_name("oscreator_nomes_do_api.json").read_text(encoding="utf-8"))
# o mapa: cada módulo que recebeu um assunto do `api.py` (o README tem a tabela)
MODULOS = ("os_tempo", "os_anexos", "os_execucao", "os_planos", "perf_alvos", "os_chamados", "os_estado", "os_detalhe",
           "os_historico", "os_solicitacoes", "os_criar", "dash_os", "ativos_carga", "catalogos_rpc", "os_juntar", "fracttal_erro")
# onde uma função do `api` pode ter nascido: o `api.py`, os módulos do mapa, os do canto central que ele reexporta e os ganchos que a
# camada web instala no `api` com o app de pé (`os_web.sessao.instalar` troca a sessão; a lista central instala o `ID_PELA_LISTA`):
# com o `os_web` carregado, `api._read_jwt.__module__` é `os_web.sessao`, e é assim que deve ser
ONDE_PODE_MORAR = set(MODULOS) | {"api", "ativos_central", "catalogos", "builtins"}
DE_BIBLIOTECA = {"datetime", "concurrent", "threading", "contextlib", "uuid", "requests", "typing", "chamado_garantia", "dotenv",
                 "keyring", "os_web"}


def test_todo_nome_que_o_api_tinha_continua_nele():
    faltam = [n for n in NOMES_ANTES if not hasattr(api, n)]
    assert faltam == []


def test_o_que_saiu_do_api_mora_num_modulo_do_mapa():
    fora = []
    for n in NOMES_ANTES:
        obj = getattr(api, n, None)
        if callable(obj) and getattr(obj, "__module__", None):
            dono = obj.__module__
            if dono not in ONDE_PODE_MORAR and dono.split(".")[0] not in DE_BIBLIOTECA:
                fora.append((n, dono))
    assert fora == []
    # os erros são os mesmos objetos de sempre, só moraram em outro arquivo
    import fracttal_erro
    assert api.FracttalError is fracttal_erro.FracttalError and api.SessionExpired is fracttal_erro.SessionExpired
    assert issubclass(api.SessionExpired, api.FracttalError) and api.SessionExpired.session_expired is True


def _globais_chamadas_em_funcao(codigo: str) -> set:
    """Os nomes que alguma função (ou método) do arquivo usa como GLOBAL: o `symtable` sabe o que é variável local, argumento e
    nome de dentro de função, e não confunde."""
    achados: set = set()

    def visita(tab, dentro_de_funcao):
        for s in tab.get_symbols():
            if dentro_de_funcao and s.is_global() and s.is_referenced():
                achados.add(s.get_name())
        for filha in tab.get_children():
            visita(filha, dentro_de_funcao or filha.get_type() == "function")
    visita(symtable.symtable(codigo, "modulo.py", "exec"), False)
    return achados


@pytest.mark.parametrize("modulo", [m for m in MODULOS if m not in ("fracttal_erro", "os_juntar")])
def test_funcao_de_modulo_chama_funcao_do_mesmo_arquivo_pelo_api(modulo):
    """O que o teste troca é o `api.X`: a função que só o nome local alcança não é trocada, e o teste de quem a chama passa
    sem testar nada. Por isso toda função e classe do módulo que é chamada de DENTRO de uma função vai pelo `api.`."""
    codigo = (CLONE / (modulo + ".py")).read_text(encoding="utf-8")
    definidas = {n.name for n in ast.parse(codigo).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    pelo_nome_local = sorted(_globais_chamadas_em_funcao(codigo) & definidas)
    assert pelo_nome_local == [], "chamadas pelo nome local em %s: %s (use `api.<nome>`)" % (modulo, pelo_nome_local)


def test_todo_api_x_dos_modulos_existe():
    ruins, sem_import = [], []
    for modulo in MODULOS:
        arvore = ast.parse((CLONE / (modulo + ".py")).read_text(encoding="utf-8"))
        usos = [n for n in ast.walk(arvore) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                and n.value.id == "api"]
        for n in usos:
            if not hasattr(api, n.attr):
                ruins.append("%s:%d api.%s" % (modulo, n.lineno, n.attr))
        # usa o `api.` mas não o importa: quebra só na hora da chamada (NameError), longe de onde se mexeu
        if usos and not any(isinstance(n, ast.Import) and any(a.name == "api" for a in n.names) for n in arvore.body):
            sem_import.append(modulo)
    assert ruins == [] and sem_import == []


@pytest.mark.parametrize("modulo", MODULOS)
def test_funcao_importada_de_outro_modulo_do_clone_tambem_vai_pelo_api(modulo):
    """Revisão final da etapa 5: o `ativos_carga` importava o `montar_registros` do `ativos_central` (`as _build_records`) e o
    chamava pelo nome local; o `api._build_records` é o mesmo objeto, mas o teste que o trocasse no `api` não era visto por ele.
    Toda função importada com `from <outro módulo do clone> import ...` e chamada de dentro de uma função vai pelo `api.` (as
    classes, como `FracttalError` do `except`, e a biblioteca padrão ficam de fora: não são trocadas por teste nenhum)."""
    codigo = (CLONE / (modulo + ".py")).read_text(encoding="utf-8")
    do_clone = {p.stem for p in CLONE.glob("*.py")}
    importados = {a.asname or a.name for n in ast.parse(codigo).body
                  if isinstance(n, ast.ImportFrom) and n.module in do_clone for a in n.names}
    carregado = importlib.import_module(modulo)
    funcoes = {nome for nome in importados if inspect.isfunction(getattr(carregado, nome, None))}
    pelo_nome_local = sorted(_globais_chamadas_em_funcao(codigo) & funcoes)
    assert pelo_nome_local == [], "função de outro módulo chamada pelo nome local em %s: %s (use `api.<nome>`)" % (
        modulo, pelo_nome_local)


def test_o_cache_dos_motivos_de_pausa_vale_pelo_apelido_do_api(monkeypatch):
    """O `motivos_pausa` religava o cache com `global` (`_PAUSA_CACHE = [...]`), e o apelido `api._PAUSA_CACHE`, a lista de
    antes, ficava vazio para sempre. O cache é UMA lista: o `motivos_pausa` muda o conteúdo dela, e o `api` a enxerga."""
    import os_execucao
    monkeypatch.setattr(os_execucao, "_PAUSA_CACHE", os_execucao._PAUSA_CACHE)      # o desfazer devolve o nome ao que era
    lista = api._PAUSA_CACHE
    lista.clear()
    pedidos = []

    def rpc(metodo, params, **k):
        pedidos.append(metodo)
        return {"data": [{"id": 1, "description": " Almoço "}, {"id": 2, "description": "Banheiro"},
                         {"id": None, "description": "sem id"}]}
    monkeypatch.setattr(api, "_rpc_call", rpc)
    try:
        motivos = api.motivos_pausa()
        assert motivos == [{"id": 1, "descricao": "Almoço"}, {"id": 2, "descricao": "Banheiro"}]
        assert api._PAUSA_CACHE == motivos and api._PAUSA_CACHE is os_execucao._PAUSA_CACHE is lista
        assert api.motivos_pausa() == motivos and len(pedidos) == 1              # a 2ª vez sai do cache, sem pedido
        api._PAUSA_CACHE.clear()                                                  # quem limpa pelo apelido limpa o cache de verdade
        api.motivos_pausa()
        assert len(pedidos) == 2
    finally:
        lista.clear()


@pytest.mark.parametrize("modulo", MODULOS)
def test_o_modulo_importa_antes_do_api(modulo):
    """Os módulos que o `api` reexporta terminam com `import api` (ele os importa no fim do arquivo, a fachada); o `os_juntar`
    (o `os_criar` o importa) chama o `api` na hora, pelo `_api()`, e o `fracttal_erro` não o importa. Importado primeiro, o círculo
    se fecha sem erro, e o `api` sai inteiro. Num interpretador limpo, para ninguém ter carregado o `api` antes."""
    codigo = ("import sys\nsys.path.append(%r)\nimport %s\nimport api\nassert api.FracttalError.__name__ == 'FracttalError'\n"
              "assert callable(api._rpc_call) and hasattr(api, 'clonar_os')\n" % (str(CLONE), modulo))
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, cwd=str(CLONE.parents[3]))
    assert r.returncode == 0, r.stderr[-600:]
