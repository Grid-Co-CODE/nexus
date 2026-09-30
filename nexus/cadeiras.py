"""Catálogo de cadeiras (Estrutura O&M, book R02), com a torre em que cada uma começa.

Por enquanto são as dez da spec R06 do Nexus. Cadeira nova entra no FIM; id publicado nunca muda
(mesma regra de numeração do book), porque a sessão e, depois, os acessos guardam o id.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Cadeira:
    id: str
    nome: str
    torre_inicial: str


_LISTA = [
    Cadeira("dir", "Diretoria de Operações", "comando"),
    Cadeira("head", "Head de Operação de Ativos", "comando"),
    Cadeira("ctr", "Coordenador de Operação e Contratos", "contratos"),
    Cadeira("sct", "Supervisor de Contratos", "contratos"),
    Cadeira("cos", "Supervisor do COS", "cos"),
    Cadeira("op", "Operador do COS", "cos"),
    Cadeira("man", "Coordenador de Manutenção", "campo"),
    Cadeira("scp", "Supervisor de Campo", "campo"),
    Cadeira("pcm", "Coordenador de PCM", "pcm"),
    Cadeira("perf", "Coordenadora de Pós-Operação — Performance", "performance"),
]

CADEIRAS: dict[str, Cadeira] = {c.id: c for c in _LISTA}
