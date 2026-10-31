"""Os avariados na contagem do inventário (Levi, 30/10/2026, item 5 das melhorias do Almoxarifado). Desenho:
`docs/superpowers/specs/2026-10-30-almoxarifado-melhorias-design.md`, seção "5. Avariados na contagem".

O técnico conta as peças boas na lista e, na aba **Avariados** do App, as unidades avariadas de uma peça BOA do catálogo. A
linha chega no livro das contagens com o Tipo `avariado`, o "ID do item" e o "Código" da BOA e, no "Contado", as unidades
avariadas. A avariada de uma peça é, no catálogo do Fracttal, a peça de código `<código da boa>-AV` (a régua de 14/10; a
definição da casa é a `regua.avariada`). Daí:

- **`resolver`** leva cada linha `avariado` ao `-AV` pelo catálogo do App (`leitura.ler(cfg)["itens"]`, o livro Itens da
  varredura diária): achou UM item com o código `<código da boa>-AV` (sem caixa e sem espaço), a linha vira linha de peça
  (Tipo `item`) desse item, com o ID e o Código dele e a marca `_avariado_de` (o ID da boa). Daí em diante ela é uma peça
  qualquer da contagem: contagem absoluta, em branco não zera, a não ligada ao almoxarifado a gravação liga. Não achou, a
  linha fica `avariado` e vai à curadoria como "avariada sem cadastro", levando o que o cadastro precisa: `_codigo_av` (o -AV
  que falta), `_nome_av` e `_unidade_av` (a unidade da boa, em maiúsculas, como as opções da tela). Achou DOIS com o mesmo
  código: escolher um seria chutar o ID; a linha fica `avariado` com `_av_repetido`, e a curadoria pede o "é a peça X".
- **O catálogo que não se leu não é catálogo vazio** (`itens` None, revisão de 31/10/2026): a falha ficaria na cópia de 5 min
  da leitura, e toda avariada que acha o -AV viraria "sem cadastro", e a linha direta do -AV contaria sozinha, sem a trava do
  dobro. A avariada fica `avariado` com `_sem_catalogo`: a leitura põe o aviso na contagem dela (não se aprova até o catálogo
  ser lido), e a curadoria não a oferece.
- **Roda UMA vez**, na `leitura.ler`, sobre as linhas de cada contagem: o lote, a curadoria, a gravação e as contas da lista
  veem as mesmas linhas resolvidas, e o número não muda de uma tela para a outra.
- **O código da boa** sai do catálogo pelo ID (o ID é a chave; o Código da linha é a cópia do App, que pode estar velha) e,
  sem o ID no catálogo (ou sem o ID na linha), do Código da linha (`codigo_da_linha`: o "None" do `sync-xlsx` não é código).
  Sem o ID E sem o Código a avariada não é de peça nenhuma: é o contrato do App violado, e a leitura põe o aviso na contagem.
- **Avariado nunca tira do bom:** a contagem da boa é a da linha dela. A avariada só conta para o `-AV`.

**O nome do -AV** (`nome_av`, o que o cadastrar da curadoria propõe): o padrão lido nos -AV do livro Itens do App no banco em
30/10/2026 (só leitura): todos os itens de código `-AV` levam o nome da peça boa com o prefixo `"[AVARIADO] "`, a mesma unidade
da boa e a marca Avariado = Sim. A marca o App tira do próprio código e do nome na varredura (não é um campo a mais do
Fracttal): o -AV cadastrado com esse código e esse nome sai marcado na varredura seguinte, e o código já basta para a casa
(`regua.avariada`).

Puro, como as contas: dicts entram, dicts saem (cópias; o que entra não muda, porque a cópia de 5 min do livro do App é de
todos)."""
from __future__ import annotations

from ...dados import almoxarifado as A

SUFIXO = "-AV"
PREFIXO_DO_NOME = "[AVARIADO] "

_txt, _id = A._txt, A._id


def _sem_espaco(codigo) -> str:
    return "".join(str(codigo or "").split()).upper()


def codigo_av(codigo) -> str:
    """O código da avariada de uma peça: `<código>-AV`, sem caixa e sem espaço (" sp-3 " → "SP-3-AV"). O de um código que já
    termina em -AV é ele mesmo (o -AV de um -AV não é SP-3-AV-AV). Sem o código, vazio: não há -AV de uma peça sem código."""
    c = _sem_espaco(codigo)
    if not c:
        return ""
    return c if c.endswith(SUFIXO) else c + SUFIXO


def nome_av(nome) -> str:
    """O nome no padrão dos -AV do catálogo: "[AVARIADO] " + o nome da boa (os espaços a mais saem). Sem o nome, vazio (o
    PCM escreve). O nome que já tem o prefixo não ganha outro."""
    n = " ".join(str(nome or "").split())
    if not n:
        return ""
    return n if n.upper().startswith(PREFIXO_DO_NOME.strip().upper()) else PREFIXO_DO_NOME + n


def codigo_da_linha(l: dict) -> str:
    """O "Código" da linha do livro das contagens, aparado; o vazio e o "None" que o `sync-xlsx` escreve no lugar do vazio
    voltam "" (o "None" viraria o -AV "NONE-AV")."""
    c = _txt((l or {}).get("Código"))
    return "" if c.lower() == "none" else c


def _por_codigo(itens: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for id_item, v in (itens or {}).items():
        if isinstance(v, dict) and _sem_espaco(v.get("codigo")):
            out.setdefault(_sem_espaco(v.get("codigo")), []).append(_id(id_item))
    return out


def resolver(linhas: list[dict], itens: dict[str, dict] | None) -> list[dict]:
    """As linhas de UMA contagem com as avariadas levadas ao `-AV` (ver o cabeçalho). `itens`: `{id_item: {codigo, nome,
    unidade}}`, o catálogo do App como a `leitura` o monta; None é o catálogo que NÃO se leu agora (a avariada fica marcada
    `_sem_catalogo`), e {} o lido e vazio. Devolve cópias, na mesma ordem; as linhas que não são `avariado` saem iguais (cópias
    também)."""
    sem_catalogo = itens is None
    catalogo = {_id(k): v for k, v in (itens or {}).items() if isinstance(v, dict)}
    por_codigo = _por_codigo(catalogo)
    out = []
    for l in linhas or []:
        if not isinstance(l, dict):
            continue
        copia = dict(l)
        out.append(copia)
        if _txt(l.get("Tipo")).lower() != "avariado":
            continue
        if sem_catalogo:
            copia["_sem_catalogo"] = True
            continue
        id_bom = _id(l.get("ID do item"))
        bom = catalogo.get(id_bom) or {}
        alvo = codigo_av(bom.get("codigo") or codigo_da_linha(l))
        achados = por_codigo.get(alvo, []) if alvo else []
        if len(achados) == 1:
            id_av = achados[0]
            copia.update({"Tipo": "item", "ID do item": id_av, "Código": _txt(catalogo[id_av].get("codigo")),
                          "_avariado_de": id_bom})
        else:
            copia.update({"_codigo_av": alvo, "_nome_av": nome_av(bom.get("nome")),
                          "_unidade_av": _txt(bom.get("unidade")).upper(), "_av_repetido": len(achados) > 1})
    return out
