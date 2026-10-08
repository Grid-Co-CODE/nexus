"""Copia do function_app.py do App de Campo as regras que a torre Campo · App usa, sem mudar a lógica.

Mesmo princípio do motor do PCM (nexus/pcm/motor/): o Nexus não reinterpreta a regra do App, ele copia. Assim o número
da tela do Nexus é o do painel do App por construção. O que muda é só de onde o dado é lido: as tabelas pela chave só de
leitura do Nexus (nexus/campo/tabelas.py) e o Fracttal pelo leitor do Nexus (nexus/campo/fracttal.py), só GET.

A cópia leva a LÓGICA, sem comentários nem docstrings (ast.unparse): o repositório do Nexus é público e os comentários
do App citam colegas pelo nome completo e casos internos. A fidelidade é conferida pela árvore do código (ast.dump),
não pelo texto: tests/test_campo_regras_app.py acusa qualquer diferença de lógica entre a cópia e o App.

Uso (Levi, 04/10/2026: "pode passar para o Nexus"):
    python ferramentas/extrair_regras_campo.py "<...>/App_Campo/middleware/function_app.py"

Rode de novo quando o App publicar versão que mexa nestas funções.
"""
import ast
import hashlib
import symtable
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "nexus" / "campo" / "regras_app.py"

# O que as telas chamam no App. O resto vem pelo fecho.
#   Aprovação de OS:    rota gestao/supervisao/fila
#   Ordens de serviço:  rota gestao/os
# Central de atenção e Permissões de trabalho saíram da cópia em 05/10/2026: são contas do próprio Nexus
# (nexus/campo/visao.py), pelos livros que o App grava no banco (Levi: "quero parar de referenciar o Azure").
RAIZES = ("_fila_supervisao", "_janela", "TRIAGEM_NOTA_OK",
          "_cadastro_tab",          # o ident() do Nexus (nexus/campo/pessoas.py) usa o cadastro da tabela como o do App
          # Ordens de serviço: rota gestao/os. A tela saiu em 08/10/2026: tire "_gestao_os" na próxima vez que o
          # extrator rodar (rodar só para isso traria junto o que o App mudou desde a última cópia)
          "_gestao_os", "_janela_str",
          # Nota do fechamento recalculada com o que o Fracttal guarda (nexus/campo/nota_fracttal.py): a do PAINEL é a
          # `_qualidade_os` (é ela que o App grava no registro, `qualidade`); a `_qualidade_v2` é só a do placar
          "_qualidade_os", "_qualidade_v2",
          # Triagem de qualidade: rota gestao/prioridades
          "_gestao_prioridades")
# Trocados pelo Nexus (fim do arquivo gerado):
#   _tabela  abre a conexão do Storage do App e ainda tenta CRIAR a tabela
#   tabela   é a tabela dos TOKENS do Fracttal de cada pessoa; o Nexus só lê as partições cadastro e pt
#   fx       chama o Fracttal com a credencial do App (e escreve, se pedirem); o Nexus só lê, devagar
#   ident    lê o identidades.json de dentro do pacote do App
#   tabela_qlog  abre a conexão do App direto (sem passar por _tabela); a tabela é a "qualidadelog"
#   _varredura_carregar  (v235, 06/10/2026) põe na memória a fila que o relógio do App guarda para todas as cópias dele
#                no armazenamento do Azure (blob "varredura"); o _fila_bruta a chama antes de ler o Fracttal. Copiada,
#                arrastava o cliente do blob (abre a conexão do App) e mais 13 nomes. O Nexus não toca o Azure e relê a
#                própria fila em segundo plano (nexus/campo/aprovacao.py): devolve False, que é o que o App faz numa
#                cópia sem armazenamento ("cada cópia lê sozinha, como antes")
FORA = {"_tabela", "tabela", "fx", "ident", "tabela_qlog", "_varredura_carregar"}


def _definicoes(arvore):
    defs = {}
    for no in arvore.body:
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defs[no.name] = no
        elif isinstance(no, (ast.Assign, ast.AnnAssign)):
            alvos = no.targets if isinstance(no, ast.Assign) else [no.target]
            for alvo in alvos:
                if isinstance(alvo, ast.Name):
                    defs[alvo.id] = no
    return defs


def _globais(no) -> set:
    """Os nomes que o nó lê do MÓDULO. Parâmetro e variável local de função não puxam nada para a cópia: o
    `app = str(d.get("obs") ...)` de dentro do _obs_do_fechamento trazia o `app = func.FunctionApp()` do Azure
    (achado em 04/10/2026, ao copiar a régua da nota)."""
    raiz = symtable.symtable(ast.unparse(no), "<copia>", "exec")
    out = {s.get_name() for s in raiz.get_symbols() if s.is_referenced()}
    pilha = list(raiz.get_children())
    while pilha:
        escopo = pilha.pop()
        out |= {s.get_name() for s in escopo.get_symbols() if s.is_global() or s.is_declared_global()}
        pilha.extend(escopo.get_children())
    return out


def _nomes(no):
    return (({x.id for x in ast.walk(no) if isinstance(x, ast.Name)} & _globais(no))
            | {x.attr for x in ast.walk(no) if isinstance(x, ast.Attribute)})


def fecho(defs, raizes=RAIZES, fora=FORA):
    vistos, fila = set(), list(raizes)
    while fila:
        nome = fila.pop()
        if nome in vistos or nome in fora or nome not in defs:
            continue
        vistos.add(nome)
        fila.extend(n for n in _nomes(defs[nome]) if n in defs and n not in vistos)
    return vistos


def sem_docstrings(no):
    """O nó sem as docstrings (a de cada função e classe dentro dele)."""
    import copy
    no = copy.deepcopy(no)
    for x in ast.walk(no):
        if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and x.body:
            primeiro = x.body[0]
            if isinstance(primeiro, ast.Expr) and isinstance(getattr(primeiro, "value", None), ast.Constant) \
                    and isinstance(primeiro.value.value, str):
                x.body = x.body[1:] or [ast.Pass()]
    return no


def assinatura(no) -> str:
    """O que a fidelidade compara: a árvore do código, sem docstrings, sem posição de linha."""
    return ast.dump(sem_docstrings(no), annotate_fields=True, include_attributes=False)


def assinaturas_trocadas(arvore) -> dict:
    defs = _definicoes(arvore)
    return {n: hashlib.sha256(assinatura(defs[n]).encode("utf-8")).hexdigest()[:16] for n in sorted(FORA) if n in defs}


def nos_do_app(fonte_texto):
    """{nome: nó} de tudo o que a cópia leva, e a árvore inteira."""
    arvore = ast.parse(fonte_texto)
    defs = _definicoes(arvore)
    return {n: defs[n] for n in fecho(defs)}, arvore


def _imports_da_biblioteca_padrao(arvore):
    out = []
    for no in arvore.body:
        if isinstance(no, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in no.names] if isinstance(no, ast.Import) else [no.module or ""]
            if all(m.split(".")[0] in sys.stdlib_module_names for m in mods):
                out.append(ast.unparse(no) + "\n")
    return out


SUBSTITUTOS = '''

# ── Trocados pelo Nexus ────────────────────────────────────────────────────────────────────────────────────────────
# O resto deste arquivo é a lógica do App, intocada. Estes é que mudam: de onde o dado vem, nunca a conta.
from . import fracttal as _fracttal_do_nexus  # noqa: E402
from . import pessoas as _pessoas_do_nexus  # noqa: E402
from .tabelas import tabela as _tabela_do_nexus  # noqa: E402


def _tabela(nome, cache_attr=None):
    return _tabela_do_nexus(nome)


def tabela():
    return _pessoas_do_nexus.tabela_dos_tokens()


def tabela_qlog():
    return _tabela_do_nexus("qualidadelog")


def fx(path, method="GET", body=None, _tentativa=0):
    return _fracttal_do_nexus.ler(path, method, body)


def ident():
    return _pessoas_do_nexus.ident(_cadastro_tab)


def _varredura_carregar():
    return False
'''


def gerar(fonte: Path) -> str:
    bruto = fonte.read_bytes()
    texto = bruto.decode("utf-8")
    codigo = hashlib.sha256(bruto).hexdigest()[:16]
    nos, arvore = nos_do_app(texto)
    unicos = sorted({id(no): no for no in nos.values()}.values(), key=lambda no: no.lineno)
    # Nada copiado pode abrir a conexão do App: com ela o Nexus leria e escreveria em qualquer tabela, inclusive a
    # dos tokens. Função nova do App que abra a conexão direto tem de entrar em FORA, com o seu substituto.
    abrem = sorted(n for n, no in nos.items() if "from_connection_string" in ast.unparse(no))
    if abrem:
        raise SystemExit("estas abrem a conexão do App e precisam de substituto em FORA: " + ", ".join(abrem))
    partes = [
        '"""CÓPIA da lógica de regras do App de Campo (function_app.py). NÃO EDITE: rode ferramentas/extrair_regras_campo.py.\n\n'
        f"Origem: function_app.py do App, codigo {codigo} (o número que o /api/health do App mostra quando é esta a\n"
        f"versão no ar). Copiado em {datetime.now():%d/%m/%Y %H:%M}. Sem comentários nem docstrings (o repositório é\n"
        "público); o porquê de cada regra está no código do App. Só o acesso a dado foi trocado (fim do arquivo).\n"
        '"""\n',
        "# ruff: noqa\n",
        f'CODIGO_APP = "{codigo}"\n',
        f"COPIADAS = {tuple(sorted(nos))!r}\n",
        # a assinatura, no App, do que o Nexus trocou: se o App mudar um destes, o substituto pode ter ficado para trás
        f"ASSINATURAS_TROCADAS = {assinaturas_trocadas(arvore)!r}\n\n",
        *_imports_da_biblioteca_padrao(arvore),
        "\n\n",
        "\n\n\n".join(ast.unparse(sem_docstrings(no)) for no in unicos),
        "\n",
        SUBSTITUTOS,
    ]
    return "".join(partes)


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    fonte = Path(argv[1])
    DESTINO.write_text(gerar(fonte), encoding="utf-8", newline="\n")
    print(f"gravado: {DESTINO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
