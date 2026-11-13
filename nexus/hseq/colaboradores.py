"""Colaboradores (Segurança · HSEQ): as pessoas do cadastro do Nexus vistas pela Segurança, só leitura.

Pedido da Segurança (05/11/2026): acompanhar os colaboradores pela base que o Nexus já usa, sem uma segunda lista, e
continuar vendo quem foi desligado ("após o colaborador ser demitido eu ainda preciso ter a visibilidade dele"). Por isso
a tela LÊ o cadastro de Pessoas (Pessoas → Colaboradores Operação, o livro `cadastro_nexus · pessoas` no banco) e não
grava nada: incluir, corrigir ou desligar alguém continua sendo no cadastro. Uma lista própria da Segurança divergiria
do cadastro em pouco tempo (a pessoa sai da empresa e segue aparecendo como apta numa das duas).

Desligado = o "Status de contratação" da ficha é Desligado; a ficha fica no cadastro e a tela a mostra no filtro
Desligados. Sem status conta como ativo, a mesma régua do Campo (`visao._Base._time`: medido em 05/10/2026, os sem status
estão em equipes sem nenhum Ativo, e tirá-los zerava as equipes). Ficha excluída (`excluido = sim`) não entra.

O nome mora cifrado na ficha (`sensivel_cifrado`, contexto `banco/pessoas/<id>`): sem a `NEXUS_CHAVE_CADASTRO`, a tela
mostra o número da pessoa e avisa. Da ficha a tela usa só o nome; CPF, telefone e e-mail não saem do cofre.

A documentação de segurança de cada pessoa (ASO, NRs, integrações, anuências, documentos) mora em
`documentacao.py`, ligada pelo `pessoa_id` desta lista.
"""
import json

from ..cadastro import esquema
from ..campo import leitura, visao
from ..dados import fatos as D

# o filtro de situação, na ordem da faixa de números; Ativos é o padrão (quem abre quer ver quem está na operação)
SITUACOES = {"ativos": "Ativos", "desligados": "Desligados", "todos": "Todos"}
PADRAO = "ativos"
DESLIGADO = "desligado"
SEM_STATUS = "Sem status"


def _txt(v) -> str:
    return str(v or "").strip()


def desligado(status) -> bool:
    return _txt(status).lower() == DESLIGADO


def _nomes(pessoas, chave) -> dict:
    """{pessoa_id: nome completo} decifrado da ficha; sem a chave, vazio (a tela mostra o número)."""
    if not chave:
        return {}
    from ..cadastro.cifra import CifraErro, Cofre
    cofre, out = Cofre(chave), {}
    for p in pessoas:
        pid = D._id(p.get("pessoa_id"))
        if not pid or not p.get("sensivel_cifrado"):
            continue
        try:
            s = json.loads(cofre.decifrar(p["sensivel_cifrado"], f"banco/pessoas/{pid}"))
        except (CifraErro, ValueError):
            continue
        out[pid] = _txt(s.get("nome") or s.get("nome_padrao"))
    return out


def colaboradores() -> leitura.Leitura:
    """Uma linha por ficha de pessoa do cadastro (não excluída), com o vínculo, o cargo, a equipe, a região de campo da
    equipe e o status de contratação. Cópia de 5 min, renovada em segundo plano (`visao._ler`)."""
    def calcular():
        from flask import current_app
        pessoas = visao._livro("cadastro_nexus", "pessoas")
        equipes = {D._id(e.get("equipe_id")): e for e in visao._livro("cadastro_nexus", "equipes")
                   if D._id(e.get("equipe_id"))}
        regioes = {D._id(r.get("regiao_campo_id")): _txt(r.get("nome")) for r in
                   visao._livro("cadastro_nexus", "regioes_campo")
                   if D._id(r.get("regiao_campo_id")) and _txt(r.get("excluido")).lower() != "sim"}
        chave = current_app.config.get("NEXUS_CHAVE_CADASTRO")
        nomes = _nomes(pessoas, chave)
        linhas = []
        for p in pessoas:
            pid = D._id(p.get("pessoa_id"))
            if not pid or _txt(p.get("excluido")).lower() == "sim":
                continue
            e = equipes.get(D._id(p.get("equipe_id"))) or {}
            status = _txt(p.get("status"))
            linhas.append({
                "pessoa_id": pid, "nome": nomes.get(pid) or f"Pessoa {pid}", "com_nome": pid in nomes,
                "vinculo": esquema.rotulo_lista("vinculo", _txt(p.get("vinculo"))),
                "cargo": _txt(p.get("cargo")), "equipe": _txt(e.get("nome")),
                "regiao": regioes.get(D._id(e.get("regiao_campo_id")), ""),
                "status": status or SEM_STATUS, "desligado": desligado(status)})
        linhas.sort(key=lambda x: (not x["com_nome"], visao._norm_nome(x["nome"]), x["pessoa_id"]))
        return {"pessoas": linhas, "sem_chave": not chave,
                "sem_nome": sum(1 for x in linhas if not x["com_nome"])}
    return visao._ler(("hseq_colaboradores",), calcular)


def situacao(valor) -> str:
    """O filtro de situação do endereço; o que não for conhecido volta ao padrão (Ativos)."""
    return valor if valor in SITUACOES else PADRAO


def na_situacao(x, sit) -> bool:
    return sit == "todos" or (sit == "desligados") == x["desligado"]


def contar(lista) -> dict:
    deslig = sum(1 for x in lista if x["desligado"])
    return {"todos": len(lista), "ativos": len(lista) - deslig, "desligados": deslig}


def opcoes(lista, campo) -> list[str]:
    """Os valores de um filtro (vínculo, cargo, região), em ordem alfabética, sem o vazio."""
    return sorted({x[campo] for x in lista if x[campo]}, key=str.lower)
