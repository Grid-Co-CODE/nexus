"""A foto dos ativos do Fracttal no banco, `nexus_ativos_fracttal · foto_ativos`, renovada toda noite (31/10/2026, etapa 2 do
canto central do OS Creator; desenho `docs/superpowers/specs/2026-10-30-oscreator-canto-central-design.md`).

Até aqui ela era a carga única de 11/10/2026 (as fotos que o OS Creator guardou em arquivo, `ferramentas/carregar_ativos_
fracttal.py --gravar`, quem gravava era o Levi): 22.357 linhas que só envelheciam, e a dimensão de equipamento
(`equipamento.py`), que a lê de hora em hora, envelhecia junto. Agora o leitor dos ativos do servidor
(`nexus/torres/oscreator/os_creator/ativos_leitor.py`) lê o Fracttal inteiro de madrugada e, DEPOIS que o catálogo do OS
Creator aceitou a leitura (a guarda é uma só: a leitura incompleta, a que encolhe mais de 5% e a que não bate com o catálogo
não chegam aqui), entrega os itens a `gravar`. A ferramenta ficou só com a medição: uma máquina grava (regra 11 do
`nexus/dados/CLAUDE.md`), e é o servidor.

O GRÃO: 1 linha = 1 item do Fracttal com 1 código (o par `fracttal_item_id` + `codigo`; a raiz de cada cliente, sem
`pai_item_id`, inclusive: é dela que sai o nome do cliente no caminho do ativo). As colunas são as de `equipamento.CAB_FOTO`,
com três no fim desde 31/10: `id_type_item`, `id_group_task` e `fora_do_fracttal_desde` (data_id).
- O CÓDIGO QUE SAI DO FRACTTAL FICA (os fatos antigos ligam por ele, como os 719 códigos de junho que a carga única levou),
  marcado com o dia em que deixou de vir; voltou, a marca sai. Na 1ª renovação, os códigos da foto mais velha que a de 22/09
  já não estavam nela: ganham a marca desse dia (20260922), e não o da renovação.
- `foto_em` é o dia (de Brasília) em que a LINHA mudou pela última vez. Por isso a mesma leitura amanhã dá o mesmo sha e o
  livro não é trocado (são 22 mil linhas: trocar todo dia sem nada novo regravaria a dimensão de equipamento junto).
- A leitura do banco é CONFERIDA (`ler`): a aba que a listagem não traz, ou que vem com menos linhas que o `row_count` dela,
  não grava (gravar por cima de uma leitura curta apagaria os códigos que saíram do Fracttal, que só existem aqui). E o livro
  é `so_cresce` no catálogo: a trava do `livros.publicar` confere de novo antes de trocar.
- A `descricao` vai SEM endereço, em TODA linha (Rulings AK e AN, revisões 1 e 2 da 2.2). A API do banco tem leitura aberta, e
  o endereço da usina já saiu dela uma vez, no mesmo dia em que entrou (04/10/2026, a 1ª carga do Campo · App). Três passos:
  1. o leitor passa a cada linha lida hoje o nome do item como o Fracttal o põe no caminho (`ativos_foto.nomes_no_caminho`:
     sem a cauda de endereço da usina);
  2. a linha que NÃO veio hoje (o código que saiu do Fracttal, como os 719 de junho) é recalculada aqui pela própria
     descrição e pelo próprio pai (`nome_de_quem_saiu`, que o leitor monta com o grafo da noite: os itens lidos hoje e as
     linhas antigas que não vieram). Mudou a descrição, mudou a linha: o `foto_em` vai para o dia, e a marca de fora segue a
     regra de sempre (a que já tinha marca fica com ela; essas contam em `fora_mudaram`);
  3. o detector de endereço (`sem_endereco`) confere toda descrição que vai ao banco (a nova, a igual, a que saiu) e corta
     antes do 1º marcador (`MARCADORES_DE_ENDERECO`): a usina fora de "Cliente - Usina - UF" e o nível com endereço próprio,
     colado por UM espaço, passavam pelo corte do passo 1. A noite conta quantas ele cortou (`descricao_cortada`, com até 5
     `fracttal_item_id` de exemplo; nunca o texto). A usina cujo nome fechou no padrão "Cliente - Usina - UF" NÃO passa por
     ele (Ruling AQ, revisão 3): o corte na sigla do estado já fechou o nome, e usina rural com "Fazenda", "Sítio" ou
     "Chácara" no nome é comum na carteira (o detector a cortaria no "Fazenda", e a foto servindo de catálogo juntaria duas
     usinas de fazenda numa só). Quem diz qual usina fechou no padrão é o leitor (`usinas_no_padrao`, e o
     `nome_de_quem_saiu` para a linha que saiu), e a isenção só vale para o nome que termina na sigla do estado.
  A linha que saiu é repetida pelos passos 2 e 3 até parar: a 2ª noite parte do que a 1ª gravou e não muda nada. A 1ª
  renovação troca TODAS as linhas da carga única de 11/10, que tinham o endereço, inclusive as que saíram.
- O nome do livro (`equipamento.NOME_FOTO`) só vale para quem o cria: o livro existe desde 11/10, e o `livros.publicar` não
  troca o nome do que já existe.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import date, datetime, timedelta, timezone

from . import equipamento as eq
from . import livros

_BRT = timezone(timedelta(hours=-3))
CAB_FOTO = eq.CAB_FOTO
_I = {c: i for i, c in enumerate(CAB_FOTO)}
CAB_ATUALIZACAO = ["gerado_em", "maquina", "duracao_s", "linhas", "como_ler", "sha_linhas", "fora_do_fracttal"]
COMO_LER = ("1 linha = 1 item do Fracttal com 1 código (fracttal_item_id + codigo; a raiz do cliente é a linha sem "
            "pai_item_id); foto_em = o dia em que a linha mudou pela última vez; fora_do_fracttal_desde = o dia (data_id) "
            "em que o código deixou de vir na leitura do Fracttal, vazio = está no Fracttal")

# O DETECTOR DE ENDEREÇO (Ruling AN, revisão 2 da 2.2): o que ainda é endereço depois do corte do nome no caminho. A revisão
# achou dois furos naquele corte, que conhece só a forma "Cliente - Usina - UF" e o endereço da usina repetido atrás do nome:
# a usina fora dessa forma, com o endereço depois de UM espaço ("Cliente Alfa - Usina Delta Rua Sem Padrao 12", e o nível de
# dentro com o mesmo endereço), e o nível com endereço PRÓPRIO ("Inversor 1.2 Marca X Rua Outra 55"). Por isso a foto confere
# TODA descrição antes de gravar e corta antes do 1º destes marcadores. Só os inequívocos, como palavra inteira e sem
# distinguir maiúsculas: o falso positivo custa um nome de equipamento truncado na dimensão (um nível chamado "Cabine
# Fazenda Alguma Coisa" perde o resto), e o contador `descricao_cortada` mostra quantos e quais ids. A usina que fechou no
# padrão "Cliente - Usina - UF" fica de fora (`_TERMINA_NA_UF`, Ruling AQ).
# DE ONDE VEIO A LISTA (item 0 da 3.1+3.2, a re-revisão das rodadas 2 e 3 da 2.2): os marcadores do 1º desenho e as abreviações
# que o `os_web/ativo_curto.ENDERECO` do OS Creator já viu no dado real ("Faz.", "FZ.", "Estr.", "R.", "Povoado", "Bairro",
# "Distrito", "Localidade", "Comunidade", "Loteamento"; o `ativo_curto` corta o nome CURTO da coluna do Histórico, e foi no
# catálogo inteiro que ele achou cada uma). FICARAM DE FORA, por darem falso positivo em equipamento: "Lote" sozinho e "Zona"
# sozinha ("Inversor Lote 2", "Cabine Zona 1"; "Zona Rural" continua) e o "S/N", que em equipamento é número de série
# ("Medidor ... S/N 123456"): o endereço que o tem já é pego pela rua. A abreviação de uma letra só ("R.") vale seguida de
# espaço ("R. Alfa 12"): "R.1" é numeração. A sigla de rodovia vai à parte, em maiúsculas, como se escreve, e só com a sigla
# de uma das 27 UFs ou do BR, hífen e EXATAMENTE 3 dígitos ("MT-010", "BR-163"; o BR também com espaço, "BR 101"): com
# qualquer par de letras e 2 ou 3 dígitos, o código de modelo ("DW-125", "CF-22", "SG-250") virava estrada; em minúscula ela
# é mais modelo de equipamento que estrada. Os padrões de comunicação serial RS-232, RS-422 e RS-485 (o conversor RS-485 é
# certo em usina solar) NÃO são a rodovia do RS (Ruling AW, rodada 1 da 3.1+3.2): a medida do detector na cópia local do
# catálogo do OS Creator (31/10/2026, 26.620 itens, só contagens) achou na sigla "RS" exatamente dois cortes, ambos no nível da
# usina e ambos RS-232/422/485; "Estr." e as siglas MT, SE e AC não cortaram nenhum nível de dentro, e ficaram.
# Vale SÓ para a foto do banco: o caminho do catálogo (`ativos_foto.caminhos`, o cliente e a usina das telas) não passa por
# aqui, e a paridade com o RPC não muda.
MARCADORES_DE_ENDERECO = ("Rua", "R.", "Av.", "Avenida", "Rod.", "Rodovia", "Estrada", "Estr.", "Km", "CEP", "Fazenda",
                          "Faz.", "FZ.", "Sítio", "Sitio", "Chácara", "Chacara", "Gleba", "Zona Rural", "Povoado", "Bairro",
                          "Distrito", "Localidade", "Comunidade", "Loteamento")
UFS = ("AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ",
       "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO")
PADROES_SERIAIS = ("RS-232", "RS-422", "RS-485")
SIGLA_DE_RODOVIA = r"\b(?!(?:%s)\b)(?:%s)-\d{3}\b|\bBR\s+\d{3}\b" % (
    "|".join(re.escape(p) for p in PADROES_SERIAIS), "|".join(UFS + ("BR",)))
# a usina isenta do detector tem de terminar na sigla do estado ("... - MT"): a lista do leitor que viesse errada não abre a
# porta para um endereço depois dela
_TERMINA_NA_UF = re.compile(r"\s-\s[A-Z]{2}$")
_SOBRA_NO_FIM = " \t-–—,;:/(|"                  # o separador que fica antes do marcador cortado ("Cabine 2 - Av. Beta")
VOLTAS_MAX = 5                                  # a linha que saiu, repetida até parar: cada volta só encurta


def _marcador(m: str) -> str:
    """A expressão de um marcador como palavra inteira: nada de letra colada antes e, se ele termina em letra, depois
    ("Estradas" e "Kmx" não são endereço; "Av." já termina no ponto). A abreviação de uma letra só ("R.") pede um espaço
    depois: "R. Alfa 12" é rua, "R.1" é numeração de equipamento. O espaço do meio vale qualquer espaço."""
    corpo = r"\s+".join(re.escape(p) for p in m.split())
    if m[-1].isalnum():
        fim = r"(?!\w)"
    elif len(m) <= 2:
        fim = r"(?=\s)"
    else:
        fim = ""
    return r"(?<!\w)" + corpo + fim


_ENDERECO = re.compile("(?i:%s)|%s" % ("|".join(_marcador(m) for m in MARCADORES_DE_ENDERECO), SIGLA_DE_RODOVIA))


def sem_endereco(descricao) -> tuple:
    """(a descrição sem o endereço, se o detector cortou). Corta antes do 1º marcador (`MARCADORES_DE_ENDERECO`, a sigla de
    rodovia) e tira o separador que sobrar no fim; sem nome antes do marcador, a linha vai sem descrição (None). Cortar o que
    já foi cortado não muda nada."""
    texto = _txt(descricao)
    if not texto:
        return None, False
    m = _ENDERECO.search(texto)
    if m is None:
        return texto, False
    return texto[:m.start()].rstrip(_SOBRA_NO_FIM) or None, True


def _isenta(texto, no_padrao: bool) -> bool:
    """A usina cujo nome fechou no padrão "Cliente - Usina - UF" (quem diz é o leitor) e que termina na sigla do estado não
    passa pelo detector (Ruling AQ)."""
    return bool(no_padrao and texto and _TERMINA_NA_UF.search(texto))


def _limpar_quem_saiu(descricao, pai, nome_de_quem_saiu) -> tuple:
    """(a descrição, se o detector cortou) de uma linha que não veio na leitura de hoje: o nome no caminho pela própria
    descrição e pelo próprio pai (`nome_de_quem_saiu(pai, descricao)`, do leitor: o nome e se é uma usina que fechou no padrão,
    que o detector não corta; sem ele, só o detector) e o detector, repetidos até parar. Parar é o que faz a 2ª noite não
    mudar a linha que a 1ª limpou: ela parte do que a 1ª gravou."""
    atual, cortou = _txt(descricao) or None, False
    for _ in range(VOLTAS_MAX):
        nome, no_padrao = nome_de_quem_saiu(pai, atual) if nome_de_quem_saiu is not None and atual else (atual, False)
        nome = _txt(nome) or None
        if _isenta(nome, no_padrao):
            novo, corte = nome, False
        else:
            novo, corte = sem_endereco(nome)
        cortou = cortou or corte
        if novo == atual:
            break
        atual = novo
    return atual, cortou


class LeituraCurta(RuntimeError):
    """A foto do banco não veio inteira (a listagem não traz a aba, ou ela veio com menos linhas que o banco diz ter): nada
    se grava por cima."""


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _int(v):
    try:
        i = int(round(float(v)))
    except (TypeError, ValueError, OverflowError):
        return None
    return i if i > 0 else None


def _canon_linha(d) -> list:
    """A linha no formato de comparação (`CAB_FOTO`), venha do banco (a API pode devolver tudo como texto) ou da leitura."""
    if not isinstance(d, dict):
        d = dict(zip(CAB_FOTO, d))
    return [_int(d.get("fracttal_item_id")), eq.canon(d.get("codigo")) or None, _txt(d.get("descricao")) or None,
            _int(d.get("pai_item_id")), _txt(d.get("tipo_fracttal")) or None, _txt(d.get("foto_em"))[:10] or None,
            _int(d.get("id_type_item")), _int(d.get("id_group_task")), _int(d.get("fora_do_fracttal_desde"))]


def _chave(l) -> tuple:
    return (l[_I["fracttal_item_id"]], l[_I["codigo"]])


def _conteudo(l) -> list:
    """A linha sem o `foto_em`: é o que diz se ela mudou."""
    return [v for i, v in enumerate(l) if i != _I["foto_em"]]


def _ordem(l) -> tuple:
    """Em ordem de item e código; no empate (a mesma chave duas vezes, que não devia haver), pela linha inteira: a ordem não
    pode depender de como o banco devolveu, senão o sha muda sem o conteúdo mudar."""
    return (l[0] or 0, l[1] or "", json.dumps(l, ensure_ascii=False, default=str))


def linha_do_item(item: dict, tipo_code=None, nome: str | None = None) -> list:
    """A linha de um item lido do Fracttal (o formato cru do RPC que o leitor monta: id, code, description, id_parent,
    id_type_item, id_group_task) com o `tipo_code` do registro do catálogo (o mesmo `tipo_fracttal` da carga de 11/10; a raiz
    do cliente não tem). A `descricao` é o `nome` (o nome do item no caminho, sem o endereço da usina: é o que o leitor da noite
    passa); sem ele, a descrição sem o "{ CÓDIGO }" do fim. O `foto_em`, a marca de fora e o detector de endereço são da
    `renovar`."""
    cod = eq.canon(item.get("code"))
    descricao = (_txt(nome) or None) if nome is not None else eq._descricao(item.get("description"), cod)
    return [_int(item.get("id")), cod or None, descricao, _int(item.get("id_parent")),
            _txt(tipo_code) or None, None, _int(item.get("id_type_item")), _int(item.get("id_group_task")), None]


def _data_id(dia: date) -> int:
    return int(dia.strftime("%Y%m%d"))


def _de_11_10(linhas) -> bool:
    """A foto da carga única (lida do banco sem a coluna da marca, que entrou em 31/10)."""
    ricas = [d for d in linhas or () if isinstance(d, dict)]
    return bool(ricas) and not any("fora_do_fracttal_desde" in d for d in ricas)


def renovar(antigas, novas, hoje: date, *, de_11_10: bool | None = None, nome_de_quem_saiu=None,
            usinas_no_padrao=frozenset()) -> tuple[list, dict]:
    """(as linhas da foto renovada, em ordem; o relatório só com contagens). PURA: `antigas` são as linhas lidas do banco
    (dicionários, ou as listas de `ler`, com `de_11_10` dito), `novas` as do Fracttal de agora (`linha_do_item`). Ver o topo
    do módulo: o código que saiu fica marcado, o que voltou perde a marca, e o `foto_em` só muda na linha que mudou.
    A descrição de TODA linha passa pelo detector de endereço (`sem_endereco`) antes de comparar, menos a da usina que fechou
    no padrão "Cliente - Usina - UF" (`usinas_no_padrao`, os ids que o leitor diz; Ruling AQ); a da linha que não veio hoje é
    recalculada antes (`_limpar_quem_saiu`, com o `nome_de_quem_saiu(pai, descricao)` do leitor). A linha que saiu e muda
    só a descrição ganha o dia (`foto_em`) e conta em `fora_mudaram`; a que sai hoje conta em `sairam`, como sempre. O
    relatório traz `descricao_cortada` (quantas o detector cortou) e `descricao_cortada_exemplos` (até 5 ids, nunca o
    texto)."""
    hoje_iso, hoje_id = hoje.isoformat(), _data_id(hoje)
    cortadas: list = []
    # a foto da carga única (sem a coluna da marca): a linha de uma foto mais velha que a última já tinha saído do Fracttal
    # no dia da última
    de_11_10 = _de_11_10(antigas) if de_11_10 is None else de_11_10
    velhas = [_canon_linha(d) for d in (antigas or ())]
    ultima = max((l[_I["foto_em"]] or "" for l in velhas), default="")
    try:
        saiu_antes = _data_id(date.fromisoformat(ultima)) if de_11_10 and ultima else None
    except ValueError:
        saiu_antes = None
    por_chave: dict = {}
    sobras = []                                                     # a mesma chave duas vezes no banco: nenhuma se perde
    for l in velhas:
        if _chave(l) in por_chave:
            sobras.append(l)
        else:
            por_chave[_chave(l)] = l
    rel = {"lidas_do_fracttal": 0, "iguais": 0, "mudaram": 0, "entraram": 0, "voltaram": 0, "sairam": 0,
           "fora_mudaram": 0, "fora_do_fracttal": 0}
    out, vistas = [], set()
    for nova in novas:
        nova = list(nova)
        if _chave(nova) in vistas:
            continue
        vistas.add(_chave(nova))
        rel["lidas_do_fracttal"] += 1
        if _isenta(nova[_I["descricao"]], nova[_I["fracttal_item_id"]] in usinas_no_padrao):
            cortou = False
        else:
            nova[_I["descricao"]], cortou = sem_endereco(nova[_I["descricao"]])
        if cortou:
            cortadas.append(nova[_I["fracttal_item_id"]])
        velha = por_chave.get(_chave(nova))
        if velha is not None and _conteudo(velha) == _conteudo(nova):
            nova[_I["foto_em"]] = velha[_I["foto_em"]] or hoje_iso
            rel["iguais"] += 1
        else:
            nova[_I["foto_em"]] = hoje_iso
            if velha is None:
                rel["entraram"] += 1
            elif velha[_I["fora_do_fracttal_desde"]]:
                rel["voltaram"] += 1
            else:
                rel["mudaram"] += 1
        out.append(nova)
    # a linha que não veio hoje (e a chave repetida no banco, que também fica): a descrição recalculada e conferida, e o resto
    # pelas regras de sempre
    for chave, velha in list(por_chave.items()) + [(None, l) for l in sobras]:
        if chave in vistas:
            continue
        linha = list(velha)
        linha[_I["descricao"]], cortou = _limpar_quem_saiu(velha[_I["descricao"]], velha[_I["pai_item_id"]],
                                                           nome_de_quem_saiu)
        if cortou:
            cortadas.append(linha[_I["fracttal_item_id"]])
        mudou = linha[_I["descricao"]] != velha[_I["descricao"]]
        if chave is not None and not linha[_I["fora_do_fracttal_desde"]]:
            antiga = saiu_antes is not None and (velha[_I["foto_em"]] or "") < ultima
            linha[_I["fora_do_fracttal_desde"]] = saiu_antes if antiga else hoje_id
            linha[_I["foto_em"]] = hoje_iso
            rel["sairam"] += 1
        elif mudou:
            linha[_I["foto_em"]] = hoje_iso
            rel["fora_mudaram" if linha[_I["fora_do_fracttal_desde"]] else "mudaram"] += 1
        out.append(linha)
    out.sort(key=_ordem)
    rel["fora_do_fracttal"] = sum(1 for l in out if l[_I["fora_do_fracttal_desde"]])
    rel["linhas"] = len(out)
    rel["descricao_cortada"] = len(cortadas)
    rel["descricao_cortada_exemplos"] = sorted(i for i in cortadas if i is not None)[:5]
    return out, rel


def sha(linhas) -> str:
    """O sha do conteúdo (as linhas já no formato de comparação, em ordem): o mesmo em qualquer máquina."""
    corpo = json.dumps(sorted(linhas, key=_ordem), ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha1(corpo.encode("utf-8")).hexdigest()


def contar(linhas) -> dict:
    """As contagens de uma foto (a medição da ferramenta e o relatório): linhas, sem código, raízes, fora do Fracttal e
    quantas linhas de cada `foto_em`."""
    ls = [_canon_linha(l) for l in linhas or ()]
    por_dia: dict = {}
    for l in ls:
        if l[_I["foto_em"]]:
            por_dia[l[_I["foto_em"]]] = por_dia.get(l[_I["foto_em"]], 0) + 1
    return {"foto_ativos": len(ls), "sem_codigo": sum(1 for l in ls if not l[_I["codigo"]]),
            "raizes": sum(1 for l in ls if not l[_I["pai_item_id"]]),
            "fora_do_fracttal": sum(1 for l in ls if l[_I["fora_do_fracttal_desde"]]),
            "por_foto": dict(sorted(por_dia.items()))}


def ler(base: str, sessao) -> tuple[list, bool]:
    """(as linhas da foto no banco, já no formato de comparação; se é a foto da carga única de 11/10), CONFERIDAS: o livro que
    ainda não existe é a 1ª gravação ([]); o que existe tem de trazer a aba e, nela, as linhas que a listagem diz
    (`row_count`). Senão, `LeituraCurta` e nada se grava. As linhas saem em listas, e não nos dicionários que a API dá: são
    ~27 mil, lidas de madrugada ao lado da leitura do Fracttal, num servidor que já anda apertado de memória."""
    r = sessao.get(f"{base}/api/workbooks", timeout=60)
    r.raise_for_status()
    w = next((x for x in r.json() if x.get("key") == eq.LIVRO_FOTO), None)
    r = sessao.get(f"{base}/api/sheets", timeout=60)
    r.raise_for_status()
    listadas = {x["sheet_name"]: x for x in r.json() if x.get("workbook_key") == eq.LIVRO_FOTO}
    if w is None and not listadas:
        return [], False
    n = livros._int((w or {}).get("sheet_count"))
    if eq.ABA_FOTO not in listadas or (n is not None and len(listadas) < n):
        raise LeituraCurta(f"{eq.LIVRO_FOTO}: a listagem do banco não trouxe a aba {eq.ABA_FOTO} inteira (o livro diz "
                           f"{n} abas e vieram {len(listadas)}); não gravo por cima")
    aba = listadas[eq.ABA_FOTO]
    esperado = livros._int(aba.get("row_count"))
    linhas = livros._linhas(base, sessao, aba["id"])
    if esperado is None or len(linhas) != esperado:
        raise LeituraCurta(f"{eq.LIVRO_FOTO}.{eq.ABA_FOTO}: li {len(linhas)} linhas e o banco diz {esperado}; não gravo "
                           "por cima")
    de_11_10 = _de_11_10(linhas)
    return [_canon_linha(d) for d in linhas], de_11_10


def gravar(novas, *, base: str, token: str, sessao, maquina: str, antigas=None, de_11_10: bool = False,
           hoje: date | None = None, nome_de_quem_saiu=None, usinas_no_padrao=frozenset()) -> dict:
    """Renova a foto com as linhas do Fracttal de agora (`linha_do_item`): lê a do banco (conferida; `antigas` e `de_11_10` se
    quem chama já leu, pela mesma `ler`), junta (`renovar`, com o `nome_de_quem_saiu` do leitor para a linha que não veio e
    as `usinas_no_padrao`, que o detector não corta) e grava SÓ se o sha das linhas mudou, pelo `livros.publicar` (que
    confere a trava `so_cresce` antes e cada aba depois). Devolve o relatório (contagens, `gravou`, o sha). Levanta
    `LeituraCurta`, `livros.GravacaoRecusada` e o erro do banco: quem chama (o leitor da noite) os guarda no estado."""
    t0 = time.time()
    if not token:
        raise RuntimeError("sem o GRIDCO_SQL_TOKEN: a foto dos ativos não é gravada")
    hoje = hoje or datetime.now(_BRT).date()
    if antigas is None:
        antigas, de_11_10 = ler(base, sessao)
    linhas, rel = renovar(antigas, novas, hoje, de_11_10=de_11_10, nome_de_quem_saiu=nome_de_quem_saiu,
                          usinas_no_padrao=usinas_no_padrao)
    novo, velho = sha(linhas), sha([_canon_linha(d) for d in antigas])
    rel["sha_linhas"] = novo
    if novo == velho:
        return dict(rel, gravou=False, motivo="nada mudou desde a última renovação")
    agora = datetime.now(_BRT).isoformat(timespec="seconds")
    tabelas = {eq.ABA_FOTO: (CAB_FOTO, linhas),
               "atualizacao": (CAB_ATUALIZACAO, [[agora, maquina, round(time.time() - t0, 1), len(linhas), COMO_LER, novo,
                                                  rel["fora_do_fracttal"]]])}
    rel["conferido"] = livros.publicar(eq.LIVRO_FOTO, eq.NOME_FOTO, tabelas, base=base, token=token, sessao=sessao)
    return dict(rel, gravou=True)
