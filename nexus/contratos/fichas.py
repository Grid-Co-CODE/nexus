"""As fichas dos contratos na Visão do contrato (18/11/2026).

Levi, 17/11/2026, depois de ver o que a planilha de controle tem e não tem por cliente: "e se eu salvar os PDFs dos
contratos para você analisar e fazer algo melhor?" e "completa tudo!", "faça por subagentes para melhor confiabilidade".
Os PDFs (contrato, aditivos e anexos de cada cliente) foram lidos fora do Nexus, um leitor por cliente, num formato só:
cada regra com a categoria, o que vale hoje (e o que era antes, quando um aditivo mudou), o setor que executa, e a prova
(o arquivo, a página, a cláusula e o trecho literal). Cada trecho foi conferido por script contra o texto da página citada.

Este módulo só recebe o resultado: o administrador importa o .json na tela, o Nexus confere o formato e guarda na pasta de
dados do servidor, `contratos/fichas_contratos.json`. NUNCA no repositório (ele é público e o contrato tem valores e
cláusulas) nem no banco de leitura aberta. O que o contrato não diz chega como `lacunas`, e a tela mostra assim: sem dado
não se inventa.

Puro: nada de rede nem Flask.
"""
from __future__ import annotations

from .controle import _chave

ARQUIVO = "fichas_contratos.json"
CATEGORIAS = ("SLA", "Entregáveis", "Rotinas", "Disponibilidade e desempenho", "Penalidades", "Benefícios",
              "Medição e faturamento", "Adicionais e hora extra", "Rescisão", "Seguros e documentação", "Outras obrigações")


class FichasInvalidas(ValueError):
    """O arquivo não é o das fichas dos contratos."""


def ler(dados) -> list[dict]:
    """As fichas de um .json importado: uma ficha, uma lista delas, ou {"fichas": [...]}. Confere o mínimo para a tela
    não quebrar (cliente, contratos, regras com categoria conhecida e referência) e recusa o resto."""
    if isinstance(dados, dict) and isinstance(dados.get("fichas"), list):
        dados = dados["fichas"]
    if isinstance(dados, dict):
        dados = [dados]
    if not isinstance(dados, list) or not dados:
        raise FichasInvalidas("não é o arquivo das fichas dos contratos")
    vistos = set()
    for f in dados:
        if not isinstance(f, dict) or not str(f.get("cliente") or "").strip():
            raise FichasInvalidas("há ficha sem o cliente")
        if _chave(f["cliente"]) in vistos:
            raise FichasInvalidas(f"o cliente {f['cliente']} aparece duas vezes")
        vistos.add(_chave(f["cliente"]))
        if not isinstance(f.get("contratos"), list) or not f["contratos"]:
            raise FichasInvalidas(f"a ficha de {f['cliente']} não tem contrato")
        for c in f["contratos"]:
            if not isinstance(c, dict) or not isinstance(c.get("regras"), list):
                raise FichasInvalidas(f"um contrato de {f['cliente']} não tem a lista de regras")
            for r in c["regras"]:
                if not isinstance(r, dict) or r.get("categoria") not in CATEGORIAS:
                    raise FichasInvalidas(f"regra de {f['cliente']} com categoria fora da lista: {r.get('categoria')!r}")
                if not isinstance(r.get("ref"), dict):
                    raise FichasInvalidas(f"regra de {f['cliente']} sem a referência (arquivo, página, cláusula)")
    return dados


def por_cliente(fichas: list[dict], clientes: list[str]) -> dict[str, dict]:
    """{cliente da planilha: ficha}, casando o nome sem acento e sem caixa ("Greenyellow" é a GreenYellow da planilha).
    Ficha de cliente que a planilha não tem entra com o próprio nome."""
    nomes = {_chave(c): c for c in clientes}
    return {nomes.get(_chave(f["cliente"]), f["cliente"]): f for f in fichas}
