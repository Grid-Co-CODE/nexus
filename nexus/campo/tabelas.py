"""De onde as regras copiadas do App leem as tabelas dele (rondas e notas de fechamento).

Levi, 04/10/2026: "não quero ligação com Azure, quero que seja direto pelo GitHub pois subirei para um servidor que
Azure não existe". O Nexus NÃO lê o Storage do App no Azure. A fonte destas tabelas ainda não existe no Nexus: o dado
do App de Campo nasce no Azure (é onde o App grava) e precisa chegar ao banco do Nexus (API de dados, PostgreSQL da
T.I.) antes de as telas do Nexus poderem mostrá-lo. Até lá, `configurado()` é falso e cada tela segue no painel do App.

As regras copiadas (regras_app.py) chamam tabela_ronda(), tabela_decisoes()... e caem em `tabela(nome)`. A fonte nova
só precisa entregar o mesmo jeito de consultar (query_entities com "PartitionKey eq '...'", get_entity). Erro de
leitura fica ANOTADO: as regras do App engolem o erro e devolvem fila vazia, e a tela precisa dizer "não consegui ler".

Primeira fonte de verdade (04/10/2026): os fechamentos que o Nexus calcula pelo Fracttal e grava na API do PG
(fonte_pg.py). Ela serve a `qualidadelog` inteira e diz isso por `serve(nome)`; o resto vem vazio. `configurado` liga
só a tela cujas tabelas EXIGIDAS a fonte serve. Desde 05/10/2026 nenhuma tela abre o painel do App: Atenção, PT,
Rondas e Zeladoria são contas do Nexus (visao.py) pelos livros que o App grava no banco.
"""
import re
import threading

_FORNECEDOR = None      # a fonte das tabelas: função nome -> objeto com query_entities / get_entity (testes: falsas)
_LEITURA = threading.local()


class SemFonte(RuntimeError):
    pass


def usar_fornecedor(fornecedor):
    """Liga a fonte das tabelas (hoje só os testes ligam; a do banco do Nexus entra aqui)."""
    global _FORNECEDOR
    _FORNECEDOR = fornecedor


def fornecedor():
    return _FORNECEDOR


def configurado(nomes=()) -> bool:
    """Há fonte para as tabelas desta tela? Sem ela, a tela fica no painel do App. A fonte que diz o que serve
    (`serve(nome)`) só liga a tela se servir TODAS as tabelas pedidas."""
    if _FORNECEDOR is None:
        return False
    serve = getattr(_FORNECEDOR, "serve", None)
    return serve is None or all(serve(n if isinstance(n, str) else n[0]) for n in nomes)


_OPS = {"eq": lambda a, b: a == b, "ge": lambda a, b: a >= b, "gt": lambda a, b: a > b,
        "le": lambda a, b: a <= b, "lt": lambda a, b: a < b}


class TabelaSoLeitura:
    """Uma tabela do App montada pelo Nexus: o pedaço do TableClient que as regras usam, na ordem do Azure
    (PartitionKey, RowKey). Filtro que as regras ainda não mandavam é recusado (fica anotado), em vez de responder
    errado; gravar é recusado sempre: o Nexus não escreve nas tabelas do App."""

    def __init__(self, nome, entidades):
        self.nome = nome
        self._linhas = sorted((dict(e) for e in entidades),
                              key=lambda e: (str(e.get("PartitionKey") or ""), str(e.get("RowKey") or "")))

    def query_entities(self, filtro, select=None, **_):
        condicoes = []
        for parte in re.split(r"\s+and\s+", str(filtro or "").strip()):
            m = re.fullmatch(r"\s*(\w+) (eq|ge|gt|le|lt) '([^']*)'\s*", parte)
            if not m:
                raise ValueError(f"filtro não suportado na tabela {self.nome}: {filtro}")
            condicoes.append(m.groups())
        return [dict(e) for e in self._linhas
                if all(_OPS[op](str(e.get(campo, "")), valor) for campo, op, valor in condicoes)]

    def list_entities(self, **_):
        return [dict(e) for e in self._linhas]

    def get_entity(self, partition_key, row_key, **_):
        for e in self._linhas:
            if e.get("PartitionKey") == partition_key and e.get("RowKey") == row_key:
                return dict(e)
        raise KeyError((partition_key, row_key))

    def __getattr__(self, nome):
        if nome.startswith(("upsert", "create", "delete", "update", "submit")):
            def recusa(*_a, **_k):
                raise PermissionError(f"o Nexus não grava na tabela {self.nome} do App")
            return recusa
        raise AttributeError(nome)


def comecar_leitura():
    _LEITURA.erros = []


def erros_da_leitura() -> list[str]:
    return list(getattr(_LEITURA, "erros", []))


def _anotar(nome, erro):
    # só a tabela e o TIPO do erro: a mensagem pode trazer endereço ou credencial da fonte
    lista = getattr(_LEITURA, "erros", None)
    if lista is not None:
        lista.append(f"{nome} ({type(erro).__name__})")


def _nao_existe(erro) -> bool:
    # get_entity de linha que não existe é normal (o App trata como "nada guardado ainda")
    return isinstance(erro, KeyError) or type(erro).__name__ == "ResourceNotFoundError"


class _Vigiada:
    """Repassa à tabela da fonte e anota todo erro que não seja "não existe"."""

    def __init__(self, nome, cliente):
        self._nome, self._cliente = nome, cliente

    def __getattr__(self, atributo):
        alvo = getattr(self._cliente, atributo)
        if not callable(alvo):
            return alvo

        def chamada(*args, **kwargs):
            try:
                r = alvo(*args, **kwargs)
                # consulta paginada pode falhar no meio da iteração, fora deste try; as regras do App percorrem tudo,
                # então ler tudo aqui não muda o resultado
                return list(r) if atributo in ("query_entities", "list_entities") else r
            except Exception as erro:
                if not _nao_existe(erro):
                    _anotar(self._nome, erro)
                raise
        return chamada


def tabela(nome: str, particao: str | None = None):
    rotulo = f"{nome}/{particao}" if particao else nome
    try:
        if _FORNECEDOR is None:
            raise SemFonte(f"o Nexus ainda não tem a fonte de {rotulo} (o dado do App precisa chegar ao banco do Nexus)")
        return _Vigiada(rotulo, _FORNECEDOR(nome))
    except Exception as erro:
        _anotar(rotulo, erro)
        raise
