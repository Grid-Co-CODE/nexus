"""O OS Creator Web do Nexus roda sem PyQt6 (canto central, etapa 1, 31/10/2026).

O clone nasceu como cópia do app de mesa (o oem), que é PyQt6. Quase todo teste do OS Creator abria com
`pytest.importorskip("PyQt6")`, com o motivo "o clone importa o steps/ui.py ao montar a tela de Engenharia". Já não
importava: a rota da Engenharia só lê o descritor (`steps/engenharia/__init__.py`), e o import da tela de mesa estava
dentro do `abrir()`, que a web nunca chama. O resultado era pior que o motivo: numa máquina sem PyQt6 (um servidor sem tela,
por exemplo) a suíte do OS Creator inteira pulava em silêncio, e ninguém via que não estava rodando.

O que estes testes seguram:
- com o PyQt6 BLOQUEADO (num subprocesso: o bloqueio não pode vazar para os outros testes), a ponte, o `api` e todo
  `os_web.*` importam, o Nexus sobe com o clone, o login do OS Creator abre e a tela de Engenharia abre pelo descritor;
- nada do repositório importa PyQt (o que era só do app de mesa saiu da cópia) e nenhum teste o pede para pular;
- o PyQt6 não é requisito de ninguém: saiu do requirements.txt só porque nada o importa.
"""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
BIBLIOTECAS_QT = ("PyQt6", "PyQt5", "PySide6", "PySide2")
# pastas que não são código do repositório: cópias de trabalho, o dado do servidor, ambientes e cache
NAO_E_CODIGO = {".git", ".superpowers", ".claude", ".venv", "venv", "dados", "node_modules", "__pycache__", "_site"}
SENHA = "senha-de-teste"

# O roteiro do subprocesso. O bloqueio é o `sys.modules[nome] = None`: `import PyQt6...` levanta ModuleNotFoundError,
# como numa máquina sem a biblioteca. Imprime uma linha JSON no fim (o resto da saída, como o log de import, é ruído).
ROTEIRO = textwrap.dedent('''
    import importlib, json, os, pkgutil, sys
    for nome in ("PyQt6", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets", "PyQt6.QtSvg", "PyQt6.sip",
                 "PyQt5", "PySide6", "PySide2"):
        sys.modules[nome] = None
    sys.path.insert(0, os.getcwd())
    saida = {}
    try:
        import PyQt6  # noqa: F401
        saida["bloqueado"] = False
    except ImportError:
        saida["bloqueado"] = True

    from nexus.torres.oscreator import ponte
    # como a ponte faz ao subir o clone: é da pasta dele que se importa `api` e `os_web`
    sys.path.append(ponte.RAIZ_CLONE)
    import api  # noqa: F401
    import os_web
    importados = ["nexus.torres.oscreator.ponte", "api"]
    for m in pkgutil.iter_modules(os_web.__path__):
        importlib.import_module("os_web." + m.name)
        importados.append("os_web." + m.name)
    saida["importados"] = importados

    # o Nexus inteiro e o clone, como o servidor os sobe, e as duas telas do OS Creator que o PyQt6 já amarrou
    os.environ.pop("OS_WEB_SUPERVISORIO_URL", None)      # com o endereço, a tela troca a moldura vazia pelo quadro dele
    from nexus import create_app
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": "%(senha)s"})
    app.config["TESTING"] = True
    app.config["SESSION_COOKIE_SECURE"] = False
    cliente = app.test_client()
    saida["entrar"] = cliente.post("/entrar", data={"senha": "%(senha)s"}).status_code
    login = cliente.get("/os/login")
    saida["login"] = login.status_code
    saida["login_diz"] = "Sistema de Ordens de Servi\\u00e7o" in login.get_data(as_text=True)

    clone = ponte.clone(app)
    jwt = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"
    valor = clone.session_interface.get_signing_serializer(clone).dumps(
        {"jwt": jwt, "conta": {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid"}})
    cliente.set_cookie("os_sessao", valor, path="/os")
    eng = cliente.get("/os/engenharia")
    html = eng.get_data(as_text=True)
    saida["engenharia"] = eng.status_code
    saida["engenharia_titulo"] = "Engenharia" in html
    saida["engenharia_descricao"] = "OS de ETM e as an\\u00e1lises da Engenharia" in html     # vem do descritor
    saida["engenharia_icone"] = '<circle cx="12" cy="7" r="3"/>' in html                     # idem

    saida["qt_carregado"] = sorted(m for m, v in sys.modules.items()
                                   if v is not None and m.split(".")[0] in ("PyQt6", "PyQt5", "PySide6", "PySide2"))
    print("RESULTADO=" + json.dumps(saida))
''') % {"senha": SENHA}


@pytest.fixture(scope="module")
def sem_pyqt():
    """O que o roteiro viu, com o PyQt6 bloqueado. Um subprocesso por módulo de teste: sobe o Nexus uma vez só."""
    env = dict(os.environ, PYTHONUTF8="1")
    env.pop("OS_WEB_SUPERVISORIO_URL", None)
    r = subprocess.run([sys.executable, "-c", ROTEIRO], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8",
                       timeout=180, env=env)
    linhas = [l for l in r.stdout.splitlines() if l.startswith("RESULTADO=")]
    assert r.returncode == 0 and linhas, "o roteiro caiu:\n" + (r.stderr or r.stdout)[-3000:]
    return json.loads(linhas[-1][len("RESULTADO="):])


def test_ponte_e_os_web_importam_sem_pyqt(sem_pyqt):
    assert sem_pyqt["bloqueado"], "o bloqueio não pegou: o teste não prova nada"
    importados = sem_pyqt["importados"]
    assert "nexus.torres.oscreator.ponte" in importados and "api" in importados
    # todos os módulos do os_web, inclusive as rotas de cada tela e a da Engenharia
    assert "os_web.rotas" in importados and "os_web.rotas_engenharia" in importados
    assert len([m for m in importados if m.startswith("os_web.")]) > 30
    assert sem_pyqt["qt_carregado"] == []


def test_o_nexus_sobe_o_clone_e_a_engenharia_abre_sem_pyqt(sem_pyqt):
    assert sem_pyqt["entrar"] == 302
    assert sem_pyqt["login"] == 200 and sem_pyqt["login_diz"]
    assert sem_pyqt["engenharia"] == 200 and sem_pyqt["engenharia_titulo"]
    # o título, a descrição e o ícone vêm do descritor `steps/engenharia`, a única coisa dele que a web lê
    assert sem_pyqt["engenharia_descricao"] and sem_pyqt["engenharia_icone"]


# ── o repositório inteiro: nada importa PyQt, nada o pede para pular ────────────────────────────────────────────────
def _python_do_repositorio():
    for pasta, subpastas, arquivos in os.walk(RAIZ):
        subpastas[:] = [p for p in subpastas if p not in NAO_E_CODIGO]
        for nome in arquivos:
            if nome.endswith(".py"):
                yield Path(pasta, nome)


def _usos_de_qt(arq: Path):
    """(linha, o que) de cada `import PyQt6...` e de cada pedido do nome dele a `importorskip`, `find_spec` ou
    `import_module` (o jeito de pular teste: foi o que o `importorskip("PyQt6")` fez por semanas)."""
    import ast
    try:
        arvore = ast.parse(arq.read_text(encoding="utf-8", errors="replace"), filename=str(arq))
    except (SyntaxError, ValueError):                      # o que nem compila ninguém importa
        return
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes = [a.name for a in no.names]
        elif isinstance(no, ast.ImportFrom):
            nomes = [no.module or ""] if not no.level else []
        elif isinstance(no, ast.Call) and no.args and isinstance(no.args[0], ast.Constant) \
                and isinstance(no.args[0].value, str):
            f = no.func
            nome_f = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            nomes = [no.args[0].value] if nome_f in ("importorskip", "find_spec", "import_module", "__import__") else []
        else:
            continue
        for n in nomes:
            if n.split(".")[0] in BIBLIOTECAS_QT:
                yield no.lineno, n


def test_nada_no_repositorio_importa_nem_pede_pyqt():
    """O que era só do app de mesa (`steps/ui.py` e a tela dele) saiu da cópia do OS Creator; nenhum teste pula por falta
    de PyQt6. Volta o PyQt6 a algum arquivo? Este teste diz qual, e o requisito volta junto (teste abaixo)."""
    usos = [f"{arq.relative_to(RAIZ).as_posix()}:{linha} ({o_que})"
            for arq in _python_do_repositorio() for linha, o_que in _usos_de_qt(arq)]
    assert usos == [], "\n".join(usos)


def test_o_pyqt_nao_e_requisito_de_ninguem():
    """Ruling Q do desenho do canto central: o PyQt6 só sai do requirements.txt se nada o importa (teste acima). O do
    clone (`os_creator/requirements.txt`) era o do app de mesa, e a página "OS Creator não subiu" aponta para ele."""
    for arq in (RAIZ / "requirements.txt", RAIZ / "nexus" / "torres" / "oscreator" / "os_creator" / "requirements.txt"):
        linhas = [l.split("#", 1)[0].strip().lower() for l in arq.read_text(encoding="utf-8").splitlines()]
        assert [l for l in linhas if l.startswith(("pyqt", "pyside"))] == [], arq.relative_to(RAIZ).as_posix()
