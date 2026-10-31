"""A curadoria do inventário do almoxarifado (PCM → Almoxarifado → Curadoria; 26/10/2026).

Levi, 26/10/2026: a peça que o técnico acha fora do catálogo vira pendência: o campo descreve, fotografa e conta, e quem
decide é o PCM. Desenho: `docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md`, seção 4.5. Três fontes de
pendência, nas contagens que ainda não foram gravadas:

- `fora_do_catalogo` (a descrição, a foto e a quantidade): o PCM **cadastra** a peça no Fracttal (código `SP-<sigla>-NNN`, o
  próximo livre da sigla, nome e unidade), diz que **é a peça X** (do catálogo) ou **descarta** (com o motivo);
- `identificar` (o genérico com saldo, um por específico): o PCM **confirma** o específico que o técnico escolheu (ou outro);
- `avariado` (30/10/2026, a aba Avariados do App; `avariados.py`): a avariada de uma peça boa cujo `<código>-AV` não está no
  catálogo do App, a **"avariada sem cadastro"**. O PCM **cadastra** o -AV (o código é FIXO, `avariados.codigo_av`, nunca um
  `SP-<sigla>-NNN`; o nome no padrão dos -AV, `"[AVARIADO] " + o nome da boa`, e a unidade da boa, que a tela já traz e o PCM
  pode corrigir), diz que **é a peça X** ou **descarta**. O cadastro procura o -AV no Fracttal antes (`achar_peca`): achou
  (outra contagem o cadastrou, ou a resposta do criar se perdeu, e a varredura do App ainda não o viu), grava a decisão
  `e_a_peca` com aquele ID e não cria nada. Sem a reserva de código dos outros cadastros: o código fixo é a chave da nova
  tentativa. A revisão de 31/10/2026: o -AV REPETIDO no catálogo (dois itens com o código) não se cadastra (409; o PCM escolhe
  pelo "é a peça X"); "é a peça X" com X a própria peça boa é 400 (avariado nunca entra no bom), e com X qualquer peça que não
  é avariada também (`regua.avariada`, "as avariadas só entram numa peça avariada (-AV)"); e sem o catálogo do App lido agora a
  avariada não pede decisão (503 se pedirem), porque "não está no catálogo" seria falso.

A decisão vai ao livro do inventário (`fato_curadoria_inventario`, mais o evento `curadoria` da auditoria) e a quantidade
entra no lote pela `contas.contado_efetivo`: "é a peça X" e "cadastrar" somam as achadas ao contado da peça NESSA contagem (o
total substitui o saldo); o genérico confirmado tira as unidades do genérico e as põe no específico. A peça cadastrada é ligada
ao almoxarifado e ajustada na gravação da contagem, não aqui. `decisoes(cfg, contagem)` devolve as decisões no formato que as
contas pedem. Só `pcm.telas.pode_programar()` decide.

Regras com o caso que as criou:

- **A decisão vale só até a contagem ser gravada.** Depois ela não mudaria o que já foi gravado: a tela recusa (409) e manda
  fazer uma nova contagem. Gravada, ou com a gravação começada (aprovada), ou recusada (recontagem pedida), ou substituída pela
  mais nova do almoxarifado: nenhuma pede decisão.
- **Uma linha decidida não se decide de novo** (dois do PCM com a mesma tela aberta não cadastram a mesma peça duas vezes).
- **Cadastrar sem duplicar.** O `criar_peca` pode criar a peça e perder a resposta (a conexão cai depois de o Fracttal gravar).
  Antes de criar, o código escolhido vai para um controle local (`<NEXUS_DADOS>/almox_inventario/curadoria_<contagem>.json`,
  sem login, sem nome): na nova tentativa da mesma linha o código reservado é o da linha; se ele já existe no Fracttal
  (`Estoque.peca`), não cria de novo, acha o ID e só grava a decisão; se não existe, cria com ele. A reserva também vale
  para as outras linhas da mesma sigla (a peça recém-criada pode ainda não aparecer na lista do Fracttal). A reserva guarda a sigla,
  o nome e a unidade, e a nova tentativa tem de vir com os mesmos (`Conflito` se não); e a peça achada pelo código reservado tem de ter
  o mesmo nome (`field_1`), senão o código foi usado por outra pessoa e a decisão não se liga a ela. O `criar_peca` que o Fracttal
  RECUSA (`ErroFracttal`: nada foi criado) solta a reserva, para a nova tentativa com os dados corrigidos; a resposta perdida não.
- **Antes de escrever, o estado da contagem é conferido de novo** (o cadastro leva segundos, e a gravação pode chegar no meio): a
  decisão que chega à contagem já fechada é recusada, e a mensagem do cadastro diz o código que ficou criado no Fracttal.
- **As travas são por chave** (`travas.Travas`: a linha, a sigla, o arquivo de controle), nunca uma do módulo segurada enquanto se
  espera o Fracttal.
- **O próximo código usa o `Estoque.codigos`**, que traz as peças DESATIVADAS também (a lista de Peças e Suprimentos do Fracttal
  mostra "Não" em "Habilitado" e as mantém): o código de peça desativada não é reaproveitado.
- **A sigla `TST` só no almoxarifado de teste** (`almoxarifado.ids_de_teste`): a prova das gravações é lá, e `SP-TST-NNN` não
  pode nascer no catálogo de um cliente.
- **A foto** é a do achado, guardada em `<NEXUS_DADOS>/almox_inventario/fotos/<nome_da_foto(chave)>.jpg` e servida pela rota
  `.../curadoria/foto/<nome>.jpg` (`?mini=1`, a miniatura de 160 px; como as dos extintores, que o App envia ao Nexus e ficam em
  disco: nunca no banco, que a API abre a quem quiser). O App as envia pela rota assinada `POST .../pecas/inventario/foto`
  (`fotos_app.py`, 30/10/2026: a "Foto" da peça e as dos dados), com a chave que pôs no livro; o nome é o SHA-1 da chave
  (qualquer chave cabe num nome de arquivo). A descrição do técnico e a foto só aparecem para quem decide (`pode_programar`).
- **Grupo, criticidade e Curva ABC não se gravam pela API** (testado pelo PCM em 09/10): a tela lembra de completar na tela do
  Fracttal. **Nem o fabricante, o modelo e o número de série** (revisão final de 31/10/2026): o `item_insert` responde o
  `description` como "<nome>    { CODE }" (o passo 0), um campo de exibição, e ninguém provou o que escrevê-lo faz com o
  catálogo do cliente. O cadastrar não os manda (o `criar_peca` guarda o `descricao=""`, sem uso), e o cartão da linha que os
  tem lembra de completá-los junto do grupo, da criticidade e da Curva ABC (`descricao_dos_dados`).
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Response, abort, current_app, jsonify, redirect, render_template, request, session
from werkzeug.exceptions import RequestEntityTooLarge

from ...campo import visao
from ...cadastro.ligacoes import pasta_dados
from ...dados import almoxarifado as A
from ...dados import fato_inventario as F
from ...dados import fatos as D
from ...prefixo import na_raiz
from .. import telas
from . import avariados
from . import contas as C
from . import erros, leitura, quem, regua, travas
from . import estoque as E
from .erros import Conflito
from .leitura import SEM_CATALOGO
from .regua import fmt
from .travas import Travas

# as siglas do catálogo de peças (design 3.8); a do teste só no almoxarifado de teste
SIGLAS = ("PEL", "PME", "CAB", "SEN", "CTR", "COM", "INS", "ARM", "EAX", "HSE", "CSM", "GER")
SIGLA_DE_TESTE = "TST"
DECISOES_DO_TIPO = {"fora_do_catalogo": C.DECISOES_DO_ACHADO, "identificar": ("confirmar",),
                    "avariado": C.DECISOES_DO_ACHADO}
_O_QUE_E = {"fora_do_catalogo": "o achado fora do catálogo", "identificar": "o genérico a identificar",
            "avariado": "a avariada sem cadastro"}
UNIDADES = ("UNIDADE", "METRO", "MASSA")        # as que o catálogo de peças tem (as opções da tela)
NOME_MAX, MOTIVO_MAX = 120, 300
_FOTO_ID = re.compile(r"[0-9a-f]{24}")
# Uma trava por chave, nunca uma do módulo inteiro (o `criar_peca` e as páginas do catálogo levam segundos, e todo o PCM esperaria):
# - `_LINHA`, por (contagem, linha): ler, conferir e escrever a decisão (a mesma linha por dois ao mesmo tempo: um ganha, o outro 409);
# - `_SIGLA`, por sigla: escolher o próximo código e reservá-lo (duas linhas da mesma sigla não escolhem o mesmo número);
# - `_ARQUIVO`, por arquivo de controle: ler e regravar as reservas de uma contagem (linhas de siglas diferentes dividem o arquivo);
# - `_CODIGO_AV`, pelo código -AV: procurar e criar a avariada (duas contagens com a avariada da mesma peça boa não criam o -AV
#   duas vezes), no lugar da sigla e do arquivo, que a avariada não usa.
# A ordem é sempre essa (linha, sigla ou código -AV, arquivo), para uma não esperar pela outra em círculo; a da contagem
# (`travas.CONTAGEM`, a vez contra a aprovação) vem por último, só em volta da conferência final e da escrita, com as outras soltas.
_LINHA, _SIGLA, _ARQUIVO, _CODIGO_AV = Travas(), Travas(), Travas(), Travas()
_txt, _id = A._txt, A._id


# ── o código novo ────────────────────────────────────────────────────────────────────────────────────────────────────
def siglas(cfg, id_almox) -> tuple[str, ...]:
    """As siglas que se pode cadastrar neste almoxarifado: as do catálogo, e a do teste só no almoxarifado de teste."""
    return SIGLAS + ((SIGLA_DE_TESTE,) if _id(id_almox) in A.ids_de_teste(cfg) else ())


def proximo_codigo(codigos: list[str], sigla: str) -> str:
    """`SP-<sigla>-NNN`: o número seguinte ao maior que já existe na sigla (três dígitos, e mais quando passa de 999). O
    sufixo do código (`-AV`) não tira o número: SP-CAB-005-AV já gastou o 005. Sem caixa; o que é de outra sigla não conta."""
    sigla = str(sigla or "").strip().upper()
    if not sigla:
        raise ValueError("a sigla não pode ser vazia")
    padrao = re.compile(rf"SP-{re.escape(sigla)}-(\d+)(?:-[A-Z]+)?", re.IGNORECASE)
    maior = 0
    for c in codigos or []:
        m = padrao.fullmatch(str(c or "").strip())
        if m:
            maior = max(maior, int(m.group(1)))
    return f"SP-{sigla}-{maior + 1:03d}"


# ── o que o livro e o catálogo dizem ─────────────────────────────────────────────────────────────────────────────────
# o estado da lista das contagens (`leitura.ESTADOS`) como a curadoria o diz: a contagem aprovada, gravando ou gravada não se
# decide mais, nem a recusada nem a substituída
_DA_LEITURA = {"nova": "aberta", "revisada": "aberta", "recontagem_pedida": "recontagem", "substituida": "substituida",
               "gravando": "gravada", "gravada": "gravada", "gravada_com_conflitos": "gravada"}


def _estados(cfg, forcar: bool = False) -> tuple[dict, dict]:
    """({contagem_id: as linhas do livro das contagens}, {contagem_id: estado}). O estado diz se ainda se decide: `aberta`; ou
    `gravada` (a gravação feita ou começada), `recontagem` (recusada) e `substituida` (a mais nova do almoxarifado a substituiu).

    Pela leitura da lista das contagens (`leitura.ler`), a mesma regra das outras telas: o estado pelos eventos e a
    substituição só pelas contagens vivas e boas (`leitura._pode_substituir`). A curadoria tinha a conta dela, sem esse
    filtro: a contagem do futuro (o relógio do celular) ou fora do contrato sumia com as pendências da boa, que a lista ainda
    mostrava para aprovar (a revisão final de 27/10/2026). Sem o almoxarifado de teste, como as outras telas: até 27/10/2026
    ele aparecia só aqui, e uma decisão do PCM do servidor podia cair numa contagem da prova; a cópia de prova esvazia o
    `NEXUS_ALMOX_TESTE_IDS` para vê-lo. `forcar`: o livro do inventário relido agora (quem vai escrever)."""
    from . import leitura
    if forcar:
        F.ler(cfg, forcar=True)
    contagens = leitura.ler(cfg)["contagens"]
    return ({c["contagem_id"]: c["linhas"] for c in contagens},
            {c["contagem_id"]: _DA_LEITURA[c["estado"]] for c in contagens})


# por que a contagem não se decide mais: (como está agora, como já estava quando a decisão chegou ao fim)
_PORQUE = {"gravada": ("já foi gravada no Fracttal (ou a gravação já começou)",
                       "já tinha sido gravada no Fracttal (ou a gravação já tinha começado)"),
           "recontagem": ("foi recusada (recontagem pedida)", "já tinha sido recusada (recontagem pedida)"),
           "substituida": ("foi substituída por uma contagem mais nova do almoxarifado",
                           "já tinha sido substituída por uma contagem mais nova do almoxarifado")}


FOI_GRAVAR = ("Esta contagem já foi para a gravação: o lote foi congelado na aprovação, e a decisão não entra mais nele. Faça "
             "uma nova contagem.")


def _foi_para_a_gravacao(cfg, contagem_id: str) -> bool:
    """A contagem já tem o controle da gravação (`gravacao.existe`)? Vale mesmo quando o livro ainda a mostra aberta: o
    `iniciar` cria o controle ANTES de registrar a aprovação no livro, e se o registro falhou no meio (o banco que não
    confirmou), a contagem segue "nova" nos eventos com o lote já congelado. O controle ilegível conta como existente (na
    dúvida, nada entra)."""
    from . import gravacao
    try:
        return gravacao.existe(cfg, contagem_id)
    except F.Recusada:
        return True


def contagens_abertas(cfg) -> dict[str, list[dict]]:
    """`{contagem_id: linhas}` das contagens que ainda não foram gravadas (nem recusadas nem substituídas). A mesma linha
    reenviada pela fila offline do App conta uma vez (`contas._unicas`)."""
    por, estado = _estados(cfg)
    return {cid: C._unicas(ls) for cid, ls in por.items() if estado[cid] == "aberta"}


def _eh_pendencia(l: dict) -> bool:
    """A linha pede decisão: é do campo `fora_do_catalogo`, `identificar` ou `avariado` (a avariada que a leitura não levou ao
    -AV: a resolvida já chega como `item`), tem "ID da linha" e foi CONTADA (em branco, não há o que decidir: o achado em branco
    nem entra no lote). A avariada sem o ID E sem o Código da peça boa não é de peça nenhuma, como nas contas (a leitura põe
    o aviso do App na contagem). A avariada que não se resolveu porque o catálogo do App NÃO se leu agora (`_sem_catalogo`) não
    pede decisão enquanto ele não se lê: "não está no catálogo" seria falso, e a decisão vale mesmo depois de a linha se
    resolver (um "descartar" tomado agora venceria o -AV que existe). O ID "None" ou "nan" (o vazio do `sync-xlsx`) é sem ID
    (`almoxarifado.id_ou_vazio`)."""
    tipo = _txt(l.get("Tipo")).lower()
    return tipo in DECISOES_DO_TIPO and bool(_id(l.get("ID da linha"))) and A.contado(l.get("Contado")) is not None \
        and (tipo != "avariado" or ((bool(A.id_ou_vazio(l.get("ID do item"))) or bool(avariados.codigo_da_linha(l)))
                                    and not l.get("_sem_catalogo")))


def _decisoes_do_livro(linhas: list[dict]) -> dict:
    """{(contagem_id, chave_linha): a última decisão}: vale a mais nova pela hora gravada (a ordem do livro desempata)."""
    ultima: dict = {}
    for i, r in enumerate(linhas):
        k = (_txt(r.get("contagem_id")), _id(r.get("chave_linha")))
        marca = (_txt(r.get("decidida_em")), i)
        if k not in ultima or marca >= ultima[k][0]:
            ultima[k] = (marca, r)
    return {k: r for k, (_, r) in ultima.items()}


def decisoes(cfg, contagem_id: str) -> dict[str, dict]:
    """As decisões de uma contagem no formato da `contas.contado_efetivo` e da `contas.itens_do_lote`:
    `{ID da linha: {"decisao", "id_item", "codigo"}}` (o `codigo` é o da peça cadastrada)."""
    cid = _txt(contagem_id)
    return {chave: {"decisao": _txt(r.get("decisao")), "id_item": _id(r.get("id_item")), "codigo": _txt(r.get("codigo_criado"))}
            for (c, chave), r in _decisoes_do_livro(F.ler(cfg)[F.ABA_CURADORIA]).items() if c == cid}


def _catalogo() -> dict[str, dict] | None:
    """{id_item: {"codigo", "nome", "avariado"}} do catálogo do App (a varredura diária, a tela do Almoxarifado; `avariado` é a
    definição da casa, `regua.avariada`: o código -AV ou a marca do catálogo); None quando o saldo do App não chegou inteiro
    (número pela metade não vai para a tela, nem vira destino de peça)."""
    from .. import almoxarifado
    d = almoxarifado.montar().dados or {}
    if d.get("estado") != "ok":
        return None
    return {_id(c.get("id")): {"codigo": _txt(c.get("codigo")), "nome": _txt(c.get("nome")), "avariado": bool(c.get("avariado"))}
            for c in d.get("catalogo", [])}


def _usina_id(nome) -> int | None:
    """A usina do cadastro pelo nome que o Fracttal dá (a de-para; nunca o código). Sem ela, vazio."""
    lig = D.Ligador(visao._livro("cadastro_nexus", "usinas"), visao._livro("cadastro_nexus", "de_para"),
                    visao._livro("cadastro_nexus", "equipes"), {})
    uid = lig.usina_do_fracttal(nome)
    return int(uid) if uid else None


# ── as fotos ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def nome_da_foto(chave) -> str:
    """O nome (sem a extensão) da foto no disco: o SHA-1 da chave que o App pôs no livro. Qualquer chave cabe num nome de
    arquivo, e a chave nunca vira caminho."""
    return hashlib.sha1(_txt(chave).encode("utf-8")).hexdigest()[:24]


def _pasta_fotos(cfg) -> Path | None:
    try:
        return pasta_dados(cfg) / "almox_inventario" / "fotos"
    except RuntimeError:            # teste sem pasta de dados própria: não lê nem grava a de verdade
        return None


def foto(cfg, foto_id: str) -> bytes | None:
    """A foto do achado (JPEG), ou None. O nome tem de ser o de `nome_da_foto`: nada de caminho."""
    pasta = _pasta_fotos(cfg)
    if pasta is None or not _FOTO_ID.fullmatch(str(foto_id or "")):
        return None
    arq = pasta / f"{foto_id}.jpg"
    return arq.read_bytes() if arq.is_file() else None


def _tem_foto(cfg, chave) -> bool:
    return bool(_versao_da_foto(cfg, chave))


def _versao_da_foto(cfg, chave) -> str:
    """O instante do arquivo da foto (nanossegundos, em texto), ou "" sem a foto. Vai no endereço da tela (`?v=`): a mesma
    chave reenviada substitui a foto (o técnico a refez), e sem a versão o navegador mostraria a velha da cópia de 1 h
    (`Cache-Control: private, max-age=3600`; a revisão final de 31/10/2026)."""
    pasta = _pasta_fotos(cfg)
    if not _txt(chave) or pasta is None:
        return ""
    try:
        return str((pasta / f"{nome_da_foto(chave)}.jpg").stat().st_mtime_ns)
    except OSError:
        return ""


# ── fabricante, modelo e número de série (30/10/2026, itens 2 e 3 das melhorias) ────────────────────────────────────
# o rótulo da "Fotos dos dados" (`A.ROTULOS_FOTOS_DOS_DADOS`), a coluna do livro (que é também o rótulo da tela e da foto) e o
# rótulo curto do lembrete de completar no Fracttal; na ordem da tela
_DADOS_DA_PECA = (("fabricante", "Fabricante", "Fabricante"), ("modelo", "Modelo", "Modelo"),
                  ("serie", "Número de série", "Série"))
NAO_TEM = "não tem"


def _dado(v) -> str:
    """O fabricante, o modelo ou o número de série como a tela os diz: o "n/a" do técnico (sem caixa) é "não tem" (ele olhou, e a
    peça não tem); o vazio e o "None" que o `sync-xlsx` escreve no vazio são vazio (o livro de hoje, sem a coluna, também)."""
    t = A.campo(v)
    return NAO_TEM if t.lower() == A.NA else t


def descricao_dos_dados(l: dict) -> str:
    """"Fabricante: X · Modelo: Y · Série: Z", o que o cartão lembra de completar na tela do Fracttal depois de cadastrar, junto
    do grupo, da criticidade e da Curva ABC. NÃO vai ao Fracttal pela API (revisão final de 31/10/2026): o `item_insert` não tem
    campo próprio para eles, e o `description` que ele tem é o de exibição ("<nome>    { CODE }" na resposta do passo 0), sem
    prova do que escrevê-lo faz. O "n/a" e o vazio saem; sem nenhum, vazio (e o cartão não lembra nada a mais)."""
    partes = []
    for _, coluna, curto in _DADOS_DA_PECA:
        v = _dado(l.get(coluna))
        if v and v != NAO_TEM:
            partes.append(f"{curto}: {' '.join(v.split())}")
    return " · ".join(partes)


def _fotos_da_linha(cfg, l: dict) -> list[dict]:
    """As fotos do achado na ordem da tela: a da peça ("Foto") e as dos dados ("Fotos dos dados", `A.fotos_dos_dados`), só as que
    o App escreveu na linha (o dado "n/a" não tem foto). `tem`: a foto já chegou ao Nexus (ela vai depois da linha, pela fila
    offline do App; sem ela, "foto ainda não chegou"); `versao`: o instante do arquivo, para o endereço (`_versao_da_foto`)."""
    chaves = [("Peça", A.campo(l.get("Foto")))]
    dos_dados = A.fotos_dos_dados(l.get("Fotos dos dados"))
    chaves += [(coluna, dos_dados.get(rotulo_col, "")) for rotulo_col, coluna, _ in _DADOS_DA_PECA]
    out = []
    for rotulo, c in chaves:
        if c:
            versao = _versao_da_foto(cfg, c)
            out.append({"rotulo": rotulo, "foto_id": nome_da_foto(c), "tem": bool(versao), "versao": versao})
    return out


# ── as pendências ────────────────────────────────────────────────────────────────────────────────────────────────────
_BRT = timezone(timedelta(hours=-3))


def _quando_txt(iso) -> str:
    """"26/10, 10:00" (hora de Brasília) de uma hora ISO do livro; o que não é hora volta vazio."""
    try:
        d = E.instante(iso)
    except ValueError:
        return ""
    return d.astimezone(_BRT).strftime("%d/%m, %H:%M")


def _reservas_da_contagem(cfg, cid: str) -> dict:
    """As reservas de código desta contagem para a tela repetir os mesmos dados (`reserva` na pendência). Sem pasta de dados ou
    com o controle ilegível, vazio: quem decide encontra o erro de verdade ao cadastrar (`_ler_reservas`), a tela só não ajuda."""
    try:
        with _ARQUIVO.de(_arquivo_reserva(cfg, cid).name):
            return _ler_reservas(_arquivo_reserva(cfg, cid))
    except (F.Recusada, OSError):
        return {}


def pendencias(cfg) -> list[dict]:
    """As linhas `fora_do_catalogo`, `identificar` e `avariado` das contagens que não foram gravadas, na ordem em que a
    contagem as trouxe (a mais antiga primeiro), cada uma com a foto e a decisão que já tem (`decisao`: None se pende).
    `contado` já é número. No genérico, o específico que o técnico escolheu vem com o código e o nome do catálogo do App
    (quando o catálogo veio). A `reserva` é o que uma tentativa anterior de cadastrar esta linha reservou (código, sigla, nome,
    unidade), ou None. Na avariada sem cadastro, `codigo_av` (o -AV que falta), `nome_av` e `unidade_av` são o cadastrar já
    preenchido (as marcas do `avariados.resolver`), e `av_repetido` diz que há mais de um item com aquele código no catálogo
    (sem cadastrar: o PCM escolhe pelo "é a peça X"); nas outras, vazios.

    Desde 30/10/2026 (itens 2 e 3): `fabricante`, `modelo` e `serie` (texto; o "n/a" do técnico vira "não tem"; sem a coluna,
    vazio), `lembrar_no_fracttal` (o que o cartão lembra de completar na tela do Fracttal, `descricao_dos_dados`: não vai pela
    API) e `fotos`, a da peça e as dos dados na ordem da tela: `[{"rotulo": "Peça" | "Fabricante" | "Modelo" | "Número de
    série", "foto_id", "tem", "versao"}]` (`versao`: o instante do arquivo, que vai no endereço como `?v=`).
    O livro de hoje, sem as colunas novas, dá os três vazios e só a foto da peça: a tela de hoje."""
    abertas = contagens_abertas(cfg)
    decididas = _decisoes_do_livro(F.ler(cfg)[F.ABA_CURADORIA])
    catalogo = _catalogo() or {}
    out = []
    for cid, linhas in sorted(abertas.items(), key=lambda kv: (_txt(kv[1][0].get("Contada em")), kv[0])):
        reservas = _reservas_da_contagem(cfg, cid)
        for l in linhas:
            if not _eh_pendencia(l):
                continue
            chave = _id(l.get("ID da linha"))
            d = decididas.get((cid, chave))
            como = _id(l.get("Identificado como"))
            out.append({
                "contagem_id": cid, "chave_linha": chave, "tipo": _txt(l.get("Tipo")).lower(),
                "id_almox": _id(l.get("ID do almoxarifado")), "usina": _txt(l.get("Usina")),
                "contada_em": _txt(l.get("Contada em")), "contada_txt": _quando_txt(l.get("Contada em")), "contado": A.contado(l.get("Contado")),
                "descricao": _txt(l.get("Descrição")), "foto": _txt(l.get("Foto")),
                "foto_id": nome_da_foto(l.get("Foto")) if _txt(l.get("Foto")) else "",
                "tem_foto": _tem_foto(cfg, l.get("Foto")),
                "id_item": A.id_ou_vazio(l.get("ID do item")), "codigo": _txt(l.get("Código")),
                "identificado_como": como, "identificado_codigo": catalogo.get(como, {}).get("codigo", ""),
                "identificado_nome": catalogo.get(como, {}).get("nome", ""),
                "reserva": reservas.get(chave) if isinstance(reservas.get(chave), dict) else None,
                "codigo_av": _txt(l.get("_codigo_av")), "nome_av": _txt(l.get("_nome_av")),
                "unidade_av": _txt(l.get("_unidade_av")), "av_repetido": bool(l.get("_av_repetido")),
                "fabricante": _dado(l.get("Fabricante")), "modelo": _dado(l.get("Modelo")),
                "serie": _dado(l.get("Número de série")), "lembrar_no_fracttal": descricao_dos_dados(l),
                "fotos": _fotos_da_linha(cfg, l),
                "decisao": None if d is None else {
                    "decisao": _txt(d.get("decisao")), "id_item": _id(d.get("id_item")),
                    "codigo_criado": _txt(d.get("codigo_criado")), "quando": _txt(d.get("decidida_em")),
                    "quando_txt": _quando_txt(d.get("decidida_em"))}})
    return out


# ── o controle do cadastro: o código reservado antes de criar ───────────────────────────────────────────────────────
def _pasta_controle(cfg) -> Path:
    try:
        return pasta_dados(cfg) / "almox_inventario"
    except RuntimeError:
        raise F.Recusada("Este Nexus está em teste e sem pasta de dados própria: não cadastro peça, porque o controle do "
                         "código reservado precisa de onde ficar. Nada foi feito.") from None


def _arquivo_reserva(cfg, contagem_id: str) -> Path:
    """Um arquivo por contagem. O ID da contagem é opaco (o App o gera): o que não cabe num nome de arquivo vira o hash dele."""
    cid = _txt(contagem_id)
    seguro = re.sub(r"[^A-Za-z0-9_-]", "_", cid)
    nome = seguro if seguro == cid and len(cid) <= 60 else f"{seguro[:40]}_{hashlib.sha1(cid.encode()).hexdigest()[:10]}"
    return _pasta_controle(cfg) / f"curadoria_{nome}.json"


def _ler_reservas(arq: Path) -> dict:
    """{chave_linha: {"codigo", ...}}. Arquivo que não existe é vazio; o que existe e não se lê PARA tudo: ignorá-lo escolheria
    o código de novo, e a peça que a tentativa anterior criou ficaria duplicada."""
    try:
        d = json.loads(arq.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as ex:
        raise F.Recusada(f"Não consegui ler o controle dos códigos reservados ({arq.name}): nada foi cadastrado, para não "
                         "criar a peça duas vezes.") from ex
    if not isinstance(d, dict):
        raise F.Recusada(f"O controle dos códigos reservados ({arq.name}) está num formato que não conheço: nada foi cadastrado.")
    return d


def _gravar_reservas(arq: Path, dados: dict) -> None:
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(arq)


def _reservados(cfg, sigla: str) -> list[str]:
    """Os códigos da sigla que alguma contagem já reservou (a peça pode ter sido criada e ainda não aparecer na lista)."""
    pasta, prefixo = _pasta_controle(cfg), f"SP-{sigla}-".upper()
    codigos = []
    for arq in sorted(pasta.glob("curadoria_*.json")):
        for r in _ler_reservas(arq).values():
            c = _txt(r.get("codigo") if isinstance(r, dict) else "")
            if c.upper().startswith(prefixo):
                codigos.append(c)
    return codigos


# ── decidir ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def _achar_a_linha(cfg, contagem_id: str, chave_linha: str) -> dict:
    """A linha do livro das contagens que se decide, se ela pede decisão e a contagem ainda está aberta; senão `ValueError`
    (pedido sem sentido) ou `Conflito` (a contagem já foi gravada, recusada ou substituída)."""
    por, estado = _estados(cfg, forcar=True)           # quem decide vai escrever: o que foi gravado agora vale
    cid = _txt(contagem_id)
    if cid not in por:
        raise ValueError(f"A contagem {cid[:30]!r} não está no livro das contagens do App.")
    if estado[cid] != "aberta":
        raise Conflito(f"Esta contagem {_PORQUE[estado[cid]][0]}: a decisão não muda o que já foi gravado. Faça uma nova "
                       "contagem.")
    if _foi_para_a_gravacao(cfg, cid):                 # antes do Fracttal: o cadastro nem cria a peça
        raise Conflito(FOI_GRAVAR)
    chave = _id(chave_linha)
    for l in C._unicas(por[cid]):
        if _id(l.get("ID da linha")) == chave:
            if l.get("_sem_catalogo"):
                raise F.Recusada(f"{SEM_CATALOGO}. Decidir por esta avariada agora poderia valer contra o -AV que já existe: "
                                 "nada foi feito.")
            if not _eh_pendencia(l):
                raise ValueError("Esta linha não pede decisão (é peça da lista, ou ninguém a contou).")
            return l
    raise ValueError(f"A linha {chave[:30]!r} não está na contagem {cid[:30]!r}.")


def _peca_do_catalogo(cfg, id_item, cadastradas: dict[str, str]) -> str:
    """O ID de uma peça que o PCM disse: tem de estar no catálogo do App ou ter sido cadastrada por aqui (a varredura diária
    ainda não a viu; `cadastradas` é {id_item: o código criado}). ID chutado não vira peça: as unidades iriam para um item que
    não existe."""
    alvo = _id(id_item)
    if not alvo:
        raise ValueError("Informe a peça (o código ou o ID dela no Fracttal).")
    if not alvo.isdigit():
        raise ValueError(f"Não achei a peça {alvo[:30]!r} no catálogo do Fracttal: use o código dela (como SP-CAB-004) ou o ID.")
    if alvo in cadastradas:
        return alvo
    catalogo = _catalogo()
    if catalogo is None:
        raise F.Recusada("Não consegui ler o catálogo de peças do App agora (os livros do almoxarifado não estão inteiros): "
                         "não decido para uma peça que não consigo conferir. Tente de novo em instantes.")
    if alvo not in catalogo:
        raise ValueError(f"A peça {alvo} não existe no catálogo do Fracttal.")
    return alvo


def _nome_igual(a, b) -> bool:
    """O mesmo nome de peça, sem ligar para a caixa nem para o espaço a mais."""
    return " ".join(_txt(a).split()).casefold() == " ".join(_txt(b).split()).casefold()


def _conferir_a_reserva(reserva: dict, sigla: str, nome: str, unidade: str) -> None:
    """A nova tentativa de uma linha que já reservou código tem de vir com os MESMOS dados: o código reservado é de uma peça com
    aquela sigla, aquele nome e aquela unidade, e uma tentativa com outros dados criaria, se a anterior não chegou ao Fracttal,
    uma peça diferente da que a pessoa pensa ter pedido, ou, se chegou, ligaria a decisão a uma peça com o nome errado. A
    página já volta preenchida com a reserva (`pendencias`, `reserva`). `Conflito`; nada vai ao Fracttal."""
    diferencas = []
    if _txt(reserva.get("sigla")) and _txt(reserva.get("sigla")).upper() != sigla:
        diferencas.append(f"a sigla ({_txt(reserva.get('sigla')).upper()}, e não {sigla})")
    if _txt(reserva.get("nome")) and not _nome_igual(reserva.get("nome"), nome):
        diferencas.append(f"o nome ({_txt(reserva.get('nome'))!r}, e não {nome!r})")
    if _txt(reserva.get("unidade")) and _txt(reserva.get("unidade")).upper() != unidade:
        diferencas.append(f"a unidade ({_txt(reserva.get('unidade')).lower()}, e não {unidade.lower()})")
    if diferencas:
        raise Conflito(f"Uma tentativa anterior desta linha já reservou o código {_txt(reserva.get('codigo'))}, e esta vem com "
                       f"outro dado: {'; '.join(diferencas)}. Repita com os dados da reserva (a página já vem preenchida com "
                       "eles): trocar agora poderia criar uma segunda peça. Nada foi enviado ao Fracttal.")


def _conferir_o_nome_da_peca(achada: dict, reserva: dict, codigo: str) -> None:
    """A peça que o código reservado achou no Fracttal tem de ser a que ESTA linha pediu: com outro nome, o código foi usado por
    outra pessoa depois da reserva, e ligar a decisão a ela juntaria as unidades achadas à peça dos outros. O nome que o
    Fracttal não diz (a linha da lista sem `field_1`) não prova diferença e não bloqueia. `Conflito`."""
    do_fracttal = _txt(achada.get("nome"))
    if do_fracttal and not _nome_igual(do_fracttal, reserva.get("nome")):
        raise Conflito(f"O código {codigo} existe no Fracttal com outro nome ({do_fracttal!r}; esta linha reservou "
                       f"{_txt(reserva.get('nome'))!r}): não é a peça criada pela tentativa anterior, e a decisão NÃO foi ligada "
                       "a ela. Decida de outro jeito (é a peça de tal código, ou descartar) ou confira o código na tela do "
                       "Fracttal.")


def _cadastrar(cfg, contagem_id, chave, almox, sigla, nome, unidade, estoque) -> tuple[str, str, bool]:
    """Cria a peça no Fracttal sem duplicar. Devolve (id do item, código, criou agora).

    Linha SEM reserva: escolhe o próximo código da sigla (a lista do Fracttal e as reservas de todas as contagens), RESERVA-O no
    controle (com a sigla, o nome e a unidade pedidos) e só então cria. Linha COM reserva (uma tentativa anterior): confere que os
    dados são os mesmos (`_conferir_a_reserva`); se o código já existe no Fracttal, a peça foi criada e a resposta se perdeu:
    confere o nome (`_conferir_o_nome_da_peca`) e só devolve o ID, sem criar outra; se não existe, cria com o MESMO código.
    Sem a descrição: o fabricante, o modelo e a série não vão ao Fracttal (ver o cabeçalho)."""
    sigla = _txt(sigla).upper()
    if sigla not in siglas(cfg, almox):
        raise ValueError(f"A sigla {sigla[:10]!r} não é uma das do catálogo ({', '.join(siglas(cfg, almox))}).")
    nome = " ".join(_txt(nome).split())
    if not nome or len(nome) > NOME_MAX:
        raise ValueError(f"Informe o nome da peça (até {NOME_MAX} letras).")
    unidade = _txt(unidade).upper() or "UNIDADE"
    if estoque is None:
        raise ValueError("Cadastrar fala com o Fracttal: é preciso o login do Fracttal de quem decide.")
    arq = _arquivo_reserva(cfg, contagem_id)
    with _ARQUIVO.de(arq.name):
        reserva = _ler_reservas(arq).get(chave)
    if isinstance(reserva, dict) and _txt(reserva.get("codigo")):
        codigo = _txt(reserva["codigo"])             # o código desta linha já foi escolhido numa tentativa anterior
        _conferir_a_reserva(reserva, sigla, nome, unidade)
        achada = estoque.peca(codigo)                # criou e perdeu a resposta? então só falta o ID
        if achada is not None:
            _conferir_o_nome_da_peca(achada, reserva, codigo)
            return achada["id"], codigo, False
    else:
        with _SIGLA.de(sigla):
            codigo = proximo_codigo(list(estoque.codigos(sigla)) + _reservados(cfg, sigla), sigla)
            with _ARQUIVO.de(arq.name):
                reservas = _ler_reservas(arq)
                reservas[chave] = {"codigo": codigo, "sigla": sigla, "nome": nome, "unidade": unidade,
                                   "reservado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
                _gravar_reservas(arq, reservas)      # ANTES de criar: se a resposta se perder, a nova tentativa sabe qual era
    try:
        return str(estoque.criar_peca(codigo, nome, unidade)), codigo, True
    except E.Recusado:
        # o Fracttal recusou com todas as letras (o `success: false`): nada foi criado. A reserva sai, para a nova tentativa com
        # os dados corrigidos não ficar presa no "repita com os dados da reserva" (a revisão final de 27/10/2026). SÓ o
        # `Recusado`: o `ErroFracttal` sem corpo ou sem o id, a resposta perdida (rede) e o 429 NÃO soltam, porque a peça pode
        # ter sido criada; a reserva fica, e a nova tentativa a acha pelo código e confere o nome (`peca`). Soltar no "sem o
        # id" escolheria outro código e criaria uma 2ª peça no catálogo do cliente (a re-revisão de 27/10/2026)
        with _ARQUIVO.de(arq.name):
            reservas = _ler_reservas(arq)
            minha = reservas.get(chave)
            if isinstance(minha, dict) and _txt(minha.get("codigo")) == codigo:
                reservas.pop(chave)
                _gravar_reservas(arq, reservas)
        raise


def _e_a_peca_boa(l: dict, escolhida: str) -> bool:
    """O "é a peça X" de uma avariada que aponta a PRÓPRIA peça boa: as avariadas somariam ao estoque bom (o desenho: avariado
    nunca entra no bom). Pelo ID da boa; na linha sem o ID (o "None" do `sync-xlsx` inclusive: comparar com "None" deixava
    passar a boa), pelo Código dela contra o código de X no catálogo do App."""
    bom = A.id_ou_vazio(l.get("ID do item"))
    if bom:
        return _id(escolhida) == bom
    codigo = avariados.codigo_da_linha(l)
    if not codigo:
        return False
    de_x = ((_catalogo() or {}).get(_id(escolhida)) or {}).get("codigo", "")
    return "".join(_txt(de_x).split()).upper() == "".join(codigo.split()).upper()


def _e_avariada(id_item: str, cadastradas: dict[str, str]) -> bool:
    """A peça X do "é a peça X" de uma avariada é avariada (`regua.avariada`: o código com -AV no fim, ou a marca Avariado do
    catálogo)? Qualquer outra peça boa somaria as avariadas ao estoque bom dela (a revisão final de 31/10/2026: antes só a
    PRÓPRIA boa era recusada). Pelo catálogo do App ou, na peça cadastrada por aqui que a varredura ainda não viu, pelo código
    que a curadoria criou."""
    item = (_catalogo() or {}).get(id_item)
    if item:
        return regua.avariada(item.get("codigo"), item.get("avariado"))
    return regua.avariada(cadastradas.get(id_item, ""))


def _cadastrar_avariado(l: dict, nome, unidade, estoque) -> tuple[str, str, bool]:
    """O -AV da avariada sem cadastro, sem duplicar. Devolve (id do item, código, criou agora).

    O código é FIXO (`avariados.codigo_av` da peça boa, que o `resolver` deixou na linha): nunca o próximo `SP-<sigla>-NNN` (o
    que o cadastro do achado fora do catálogo escolhe), porque a casa reconhece a avariada pelo código (`regua.avariada`). Antes
    de criar, procura o código no Fracttal (`achar_peca`): achou, devolve o ID dele e não cria (outra contagem o cadastrou, ou
    a resposta do criar se perdeu, e a varredura do App ainda não o trouxe). O código fixo é a chave da nova tentativa, então a
    reserva em arquivo dos outros cadastros não é preciso; a trava por código faz duas contagens com a avariada da mesma boa
    procurarem e criarem uma de cada vez. O nome e a unidade são os que o PCM mandou ou, sem eles, os que a tela propõe (o
    padrão dos -AV e a unidade da boa). Sem a descrição, como no outro cadastro (ver o cabeçalho)."""
    codigo = _txt(l.get("_codigo_av"))
    if not codigo:
        raise ValueError("Esta avariada veio sem o código da peça boa: não há o -AV para cadastrar. Diga qual é a peça ou "
                         "descarte.")
    if l.get("_av_repetido"):
        # dois itens com o mesmo código no catálogo: o `achar_peca` escolheria um deles, que é o chute que o resolver evitou
        raise Conflito(f"Há mais de um item com o código {codigo} no catálogo: escolha pelo 'é a peça X'. Nada foi enviado ao "
                       "Fracttal.")
    nome = " ".join(_txt(nome or l.get("_nome_av")).split())
    if not nome or len(nome) > NOME_MAX:
        raise ValueError(f"Informe o nome da peça (até {NOME_MAX} letras).")
    unidade = (_txt(unidade) or _txt(l.get("_unidade_av"))).upper() or "UNIDADE"
    if estoque is None:
        raise ValueError("Cadastrar fala com o Fracttal: é preciso o login do Fracttal de quem decide.")
    with _CODIGO_AV.de(codigo.upper()):
        achada = estoque.achar_peca(codigo)
        if achada:
            return str(achada), codigo, False
        return str(estoque.criar_peca(codigo, nome, unidade)), codigo, True


def decidir(cfg, contagem_id: str, chave_linha: str, decisao: str, *, id_item: str | None = None, sigla: str | None = None,
            nome: str | None = None, unidade: str | None = None, motivo: str | None = None,
            estoque: E.Estoque | None = None, pessoa: dict | None) -> dict:
    """Registra a decisão do PCM sobre uma linha da contagem e devolve `{"decisao", "id_item", "codigo", "criada", "texto"}`.

    - `cadastrar` (achado fora do catálogo): cria a peça (`estoque.criar_peca`, no login de quem decide) com `sigla`, `nome` e
      `unidade`, e grava a decisão com o ID e o código criados. Na avariada sem cadastro, o código é o -AV fixo (a `sigla` não
      conta; `nome` e `unidade` vazios são os que a tela propõe), e o -AV que já existe no Fracttal vira `e_a_peca` com o ID
      dele, sem criar (`_cadastrar_avariado`);
    - `e_a_peca` (achado e avariada): `id_item` é a peça do catálogo a que as unidades pertencem;
    - `confirmar` (genérico): `id_item` é o específico (sem ele, o que o técnico escolheu);
    - `descartar` (achado): `motivo` obrigatório, cifrado.
    `motivo` também vai (cifrado) nas outras decisões, quando vem.

    `ValueError`: o pedido não faz sentido (nada foi feito). `Conflito`: a linha já foi decidida ou a contagem já não está
    aberta. `Recusada`: o livro (ou o controle do código) não deixou. O Fracttal levanta `Limite`, `SemLogin` e `ErroFracttal`.
    A decisão de uma linha é uma só: a 2ª é recusada, e o Fracttal nem é chamado."""
    if decisao not in F.DECISOES_CURADORIA:
        raise ValueError(f"Decisão que a curadoria não conhece: {str(decisao)[:20]!r}.")
    cid, chave = _txt(contagem_id), _id(chave_linha)
    motivo = " ".join(_txt(motivo).split())
    if len(motivo) > MOTIVO_MAX:
        raise ValueError(f"O motivo passa de {MOTIVO_MAX} letras.")
    with _LINHA.de((cid, chave)):
        l = _achar_a_linha(cfg, cid, chave)
        tipo = _txt(l.get("Tipo")).lower()
        if decisao not in DECISOES_DO_TIPO[tipo]:
            raise ValueError(f"A decisão {decisao!r} não é para esta linha ({_O_QUE_E[tipo]}): "
                             f"aqui vale {' ou '.join(DECISOES_DO_TIPO[tipo])}.")
        livro = F.ler(cfg, forcar=True)
        if (cid, chave) in _decisoes_do_livro(livro[F.ABA_CURADORIA]):
            raise Conflito("Nada foi feito: esta linha já foi decidida (por outra pessoa do PCM, ou num clique anterior). "
                           "Uma linha decidida não se decide de novo.")
        if decisao == "descartar" and not motivo:
            raise ValueError("Descartar pede o motivo (fica cifrado, na auditoria).")
        almox = _id(l.get("ID do almoxarifado"))
        cadastradas = {_id(r.get("id_item")): _txt(r.get("codigo_criado")) for r in livro[F.ABA_CURADORIA]
                       if _txt(r.get("decisao")) == "cadastrar" and _id(r.get("id_item"))}
        codigo, criada, texto = "", False, ""
        if decisao == "cadastrar" and tipo == "avariado":
            id_final, codigo, criada = _cadastrar_avariado(l, nome, unidade, estoque)
            if criada:
                texto = f"Peça avariada cadastrada no Fracttal: {codigo}. As unidades avariadas contam nela nesta contagem."
            else:
                # o -AV já existia (outra contagem o cadastrou, ou o criar perdeu a resposta): nada foi criado agora, e a
                # decisão é "é a peça" com aquele ID; o código vai só para a auditoria (`codigo_criado` é o que se criou)
                decisao = "e_a_peca"
                texto = (f"A peça {codigo} já existe no Fracttal: as unidades avariadas contam nela nesta contagem, sem "
                         "criar outra.")
        elif decisao == "cadastrar":
            id_final, codigo, criada = _cadastrar(cfg, cid, chave, almox, sigla, nome, unidade, estoque)
            texto = (f"Peça cadastrada no Fracttal: {codigo}." if criada else
                     f"A peça {codigo} já estava no Fracttal (a tentativa anterior a criou): usei ela, sem criar outra.")
        elif decisao == "descartar":
            id_final = ""
            texto = ("Avariadas descartadas: não entram na contagem." if tipo == "avariado"
                     else "Achado descartado: não entra na contagem.")
        else:
            escolhida = _id(id_item) or (_id(l.get("Identificado como")) if decisao == "confirmar" else "")
            if not escolhida:
                raise ValueError("Informe qual é a peça: o técnico não disse qual era o específico.")
            if tipo == "avariado" and _e_a_peca_boa(l, escolhida):
                raise ValueError("As avariadas não entram na peça boa: escolha o -AV (o código da boa com -AV no fim), ou "
                                 "cadastre-o.")
            id_final = _peca_do_catalogo(cfg, escolhida, cadastradas)
            if tipo == "avariado" and not _e_avariada(id_final, cadastradas):
                raise ValueError("As avariadas só entram numa peça avariada (-AV): escolha o -AV da peça (o código dela com -AV "
                                 "no fim, ou a marcada como avariada no catálogo), ou cadastre-o.")
            texto = ("As unidades saem do genérico e entram na peça escolhida." if decisao == "confirmar"
                     else "As unidades avariadas contam como unidades dessa peça nesta contagem." if tipo == "avariado"
                     else "As unidades achadas contam como unidades dessa peça nesta contagem.")
        usina = _usina_id(_txt(l.get("Usina")))
        quem_ = quem.colunas(cfg, pessoa)
        # a vez da contagem (`travas.CONTAGEM`) da conferência até a escrita: a aprovação que está lendo o lote termina antes, e
        # a decisão que chegou no meio dela é recusada aqui, em vez de gravada e ignorada pelo lote já montado (27/10/2026)
        with travas.CONTAGEM.de(cid):
            # a contagem pode ter sido gravada (ou recusada, ou substituída) enquanto o catálogo era paginado e a peça criada:
            # a decisão só vale para o lote de uma contagem ainda aberta. O estado vem do livro de AGORA, logo antes de escrever
            estado_agora = _estados(cfg, forcar=True)[1].get(cid)
            if estado_agora == "aberta" and _foi_para_a_gravacao(cfg, cid):
                estado_agora = "gravada"                 # o controle da gravação existe: o lote já foi congelado
            if estado_agora != "aberta":
                ja = _PORQUE.get(estado_agora, ("deixou de estar aberta", "já tinha deixado de estar aberta"))[1]
                if decisao == "cadastrar" and codigo:
                    # a avariada não reserva código: o -AV é fixo, e a nova contagem o acha pelo código no Fracttal
                    guarda = ("a próxima avariada desta peça o acha pelo código, sem criar outro" if tipo == "avariado"
                              else "o código continua reservado nesta linha")
                    raise Conflito(f"A peça {codigo} foi criada no Fracttal, mas a contagem {ja}: a decisão não foi registrada, "
                                   f"e {guarda}. Faça uma nova contagem.")
                raise Conflito(f"Esta contagem {ja} enquanto você decidia: a decisão não foi registrada. Faça uma nova "
                               "contagem.")
            # `codigo_criado` é o que esta decisão criou no Fracttal; o -AV achado (a avariada que virou "é a peça") vai só no
            # `codigo` do evento da auditoria
            linha = {"contagem_id": cid, "chave_linha": chave, "decisao": decisao, "id_item": id_final or None,
                     "codigo_criado": (codigo or None) if decisao == "cadastrar" else None, "id_almoxarifado": almox,
                     "usina_id": usina,
                     "usina_ligada_por": F.USINA_LIGADA_POR[0] if usina else None, **quem_}
            if motivo:
                linha["dados"] = {"motivo": motivo}
            F.acrescentar(cfg, F.ABA_CURADORIA, [linha])
            try:
                F.acrescentar(cfg, F.ABA_EVENTO, [{
                    "tipo": "curadoria", "contagem_id": cid, "id_almoxarifado": almox, "id_item": id_final or None,
                    "codigo": codigo or None, "usina_id": usina,
                    "usina_ligada_por": F.USINA_LIGADA_POR[0] if usina else None, **quem_}])
            except F.Recusada as ex:
                raise F.Recusada(f"A decisão ficou registrada, mas não consegui anotá-la na auditoria ({ex}).") from ex
    return {"decisao": decisao, "id_item": id_final, "codigo": codigo, "criada": criada, "texto": texto}


# ── as telas ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _peca_pelo_codigo_ou_id(texto) -> str:
    """O PCM conhece o código da peça (SP-CAB-004), não o ID: aceita o código (sem caixa) ou o ID, e devolve o ID. O que não
    está no catálogo volta como veio, e o `decidir` o recusa com o motivo."""
    t = _txt(texto)
    catalogo = _catalogo() or {}
    por_codigo = {v["codigo"].upper(): i for i, v in catalogo.items() if v["codigo"]}
    return por_codigo.get(t.upper(), t)


def _pagina(*, erro: str = "", status: int = 200):
    cfg = current_app.config
    erro_livro, lista = "", []
    try:
        lista = pendencias(cfg)
    except F.Recusada as ex:
        erro_livro = str(ex)
    except (visao.SemBanco, OSError) as ex:
        erro_livro = f"Não consegui ler as contagens no banco ({type(ex).__name__}): tente de novo em instantes."
    catalogo = _catalogo() or {}
    try:
        sem_catalogo = not erro_livro and not leitura.catalogo_lido()
    except (F.Recusada, visao.SemBanco, OSError):
        sem_catalogo = False            # o erro de leitura do livro do App já está na tela
    aviso = session.pop("pcm_curadoria_aviso", None) if status == 200 else None
    pode = telas.pode_programar()
    if not pode:
        # o que o técnico escreveu e a foto dele são de quem decide (podem mostrar gente, placa de equipamento, o que estiver à
        # volta): quem só olha vê que há um achado, a quantidade e a usina. Os dados da peça (fabricante, modelo, série) e as
        # fotos deles também (30/10/2026), como a descrição
        lista = [dict(p, descricao="", foto="", foto_id="", tem_foto=False, reserva=None, fabricante="", modelo="", serie="",
                      lembrar_no_fracttal="", fotos=[]) for p in lista]
    pendentes = [p for p in lista if p["decisao"] is None]
    resp = render_template(
        "pcm/inventario_curadoria.html", pendentes=pendentes, decididas=[p for p in lista if p["decisao"] is not None],
        siglas_de=lambda almox: siglas(cfg, almox), unidades=UNIDADES, fmt=fmt, pode=pode, ok=aviso or "",
        erro=erro, erro_livro=erro_livro, sem_catalogo=sem_catalogo,
        pecas=sorted(((v["codigo"], v["nome"]) for v in catalogo.values() if v["codigo"])))
    return resp, status


def registrar(bp) -> None:
    @bp.route("/pecas/inventario/curadoria", endpoint="inventario_curadoria")
    def curadoria_tela():
        return _pagina()

    @bp.route("/pecas/inventario/curadoria/foto/<foto_id>.jpg", endpoint="inventario_curadoria_foto")
    def curadoria_foto(foto_id):
        """A foto do achado, só para quem decide (`pode_programar`: administrador e setor PCM; quem só vê a tela não a vê). O portão de
        login e o da tela valem; não é rota pública. `?mini=1` é a miniatura de 160 px do cartão (`fotos_app.mini`); sem ele, a
        inteira, que a caixa da foto carrega só ao abrir."""
        from . import fotos_app
        if not telas.pode_programar():
            abort(403)
        dados = (fotos_app.mini if request.args.get("mini") else foto)(current_app.config, foto_id)
        if dados is None:
            abort(404)
        return Response(dados, mimetype="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})

    @bp.route("/pecas/inventario/foto", methods=["POST"], endpoint="inventario_foto_receber")
    def inventario_foto_receber():
        """O App envia cada foto do inventário (a "Foto" da peça e as do fabricante, do modelo e do número de série; 30/10/2026,
        `fotos_app.py`). Sem sessão: vale a assinatura HMAC (`fotos_app.receber`), e o portão de login deixa só o POST passar
        (`auth.ROTAS_PUBLICAS`). Como o precedente do PCM (`telas.motivo_do_app`), sem a régua de origem (`_de_outro_site`) e sem
        o CSRF das telas: o pedido vem do App, de outra origem e sem cookie, e quem prova que é o App é a assinatura.

        O corpo tem teto POR PEDIDO, posto antes de tocar no `request.files` (`fotos_app.TETO_DO_PEDIDO`: os 8 MB da foto mais 64 KB
        para os campos e o envelope do multipart; o precedente é a sugestão da casca): o pedido que declara mais é recusado sem
        ser lido, e o sem tamanho declarado para no teto; os dois viram o JSON do contrato (400), não o 413 em HTML. Dentro do
        teto, o Werkzeug já pôs o multipart no disco temporário quando a rota lê o arquivo, e o `receber` confere os 8 MB da foto
        (a revisão final de 31/10/2026: a nota antiga dizia que a foto grande era recusada sem ser lida, e não era)."""
        from . import fotos_app
        request.max_content_length = fotos_app.TETO_DO_PEDIDO
        try:
            arq = request.files.get("foto")
            chave, ts, sig = request.form.get("chave"), request.form.get("ts"), request.form.get("assinatura")
            dados = arq.read(fotos_app.TAMANHO_MAX + 1) if arq else b""
        except RequestEntityTooLarge:
            return jsonify({"ok": False, "mensagem": fotos_app.CORPO_GRANDE}), 400
        status, msg = fotos_app.receber(current_app.config, chave, ts, sig, dados)
        return jsonify({"ok": status == 200, "mensagem": msg}), status

    @bp.route("/pecas/inventario/curadoria/decidir", methods=["POST"], endpoint="inventario_curadoria_decidir")
    def curadoria_decidir():
        """Decide uma linha: "é a peça X", confirmar o genérico ou descartar. Só administrador e setor PCM (`pode_programar`).
        São decisões do Nexus, que só gravam no livro. **Cadastrar não passa por aqui**: ele cria a peça no Fracttal com o
        login de quem decide, e esse login (o cookie `os_sessao`) só chega às rotas debaixo de /os: o cadastro roda na ponte
        `/os/_nexus/inventario/curadoria/cadastrar` (`ponte_os.py`)."""
        if not telas.pode_programar() or telas._de_outro_site():
            abort(403)
        f = request.form
        decisao = _txt(f.get("decisao"))
        try:
            if decisao == "cadastrar":
                raise ValueError("Cadastrar fala com o Fracttal e roda pela ponte do login do Fracttal "
                                 "(/os/_nexus/inventario/curadoria/cadastrar), não por esta rota. Nada foi feito.")
            r = decidir(current_app.config, _txt(f.get("contagem")), _txt(f.get("linha")), decisao,
                        id_item=_peca_pelo_codigo_ou_id(f.get("peca")) if f.get("peca") else None, motivo=f.get("motivo"),
                        pessoa=quem.do_pedido())
        except (ValueError, OSError) as ex:
            status, texto = erros.resposta(ex)
            return _pagina(erro=texto, status=status)
        session["pcm_curadoria_aviso"] = r["texto"]
        return redirect(na_raiz("/t/pcm/pecas/inventario/curadoria"), code=303)
