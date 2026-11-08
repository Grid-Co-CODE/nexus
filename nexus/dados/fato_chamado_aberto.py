"""Os chamados de garantia em aberto, para o App de Campo (08/11/2026): `nexus_chamados_abertos · fato_chamado_aberto`.
Puro: quem lê a lista central de OS do OS Creator e grava é `nexus/torres/oscreator/chamados_abertos.py`.

Desenho de 08/11/2026 ("o chamado do tracker na ronda", aprovado pelo Levi, "segue!"): na ronda, o tracker que já tem
chamado aberto aparece só com o aviso ("Chamado aberto · Inspeção OS 19234 · administrativa OS 19235 · desde 03/11"), sem
veredito e sem botão de abrir outro chamado. O App não vê o Fracttal inteiro nem o quadro do Acompanhamento de chamados do
OS Creator: lê este livro, que o Nexus regrava de 10 em 10 minutos a partir do que o OS Creator já tem na memória (a lista
central de OS, lida pela credencial da empresa; os tickets da cópia do quadro), sem pedido novo ao Fracttal.

O QUE É "EM ABERTO" (o quadro do Acompanhamento é a régua; `acomp_web.coluna`):
- a Inspeção de garantia (tipo Inspeção, etiqueta Aguardando Garantia) ainda não concluída (em processo ou em verificação)
  e que não tem OS de acompanhamento;
- a OS de acompanhamento (tipo Administrativa, etiqueta CHAMADOS, a marca "[CHAMADO] Acompanhamento" na nota) em processo.
  Em verificação ou concluída está em "Finalizados" no quadro: o chamado fechou. Cancelada não conta (a Inspeção dela volta a
  valer sozinha, se ainda aberta).
A coluna, na régua do quadro: `aguardando_inspecao` (a Inspeção ainda em processo, sem administrativa: ela só nasce quando a
Inspeção é realizada, Levi em 08/11/2026), `chegaram` (a analista ainda não escreveu o ticket), `ticket_aberto` (o ticket está
escrito). A Inspeção realizada que ainda espera a administrativa vem com a coluna vazia.
O ticket é a subtarefa da administrativa, e o REST do Fracttal não a traz (medido em 12/10/2026): ele vem da cópia do quadro
(lido com a sessão de quem abriu), e sem ela a coluna fica VAZIA, nunca um palpite (regra 4). Vazio = "em aberto, a coluna
não é conhecida agora".

O GRÃO: 1 linha = 1 chamado em aberto, pela Inspeção; a administrativa retroativa sem Inspeção (a analista cria à mão a de
um chamado antigo), pela própria administrativa. Chave (inspecao_folio, adm_folio). É foto: encolhe quando os chamados
fecham, de propósito. Por isso a aba `atualizacao` diz quando a foto foi gerada e quantas linhas tem: o App trata a foto
velha (mais de 30 min) ou a leitura com menos linhas que o `row_count` como "não li", nunca como "não tem chamado".

SEM PESSOA E SEM TEXTO LIVRE (regra 8: a API do banco tem leitura aberta): nº das OS, o código do ativo como o Fracttal
escreve, os IDs (`equipamento_id` e `usina_id` pela dimensão de equipamento: não liga = vazio) e o dia de Brasília em que a
Inspeção nasceu. Cada linha vai ASSINADA (HMAC-SHA256 com a chave derivada da NEXUS_PESSOA_HMAC, rótulo
`nexus:oscreator:chamados-app`, como os outros livros que o App lê do Nexus): o token do banco grava em todo o banco e uma
linha falsa esconderia o tracker do técnico. O App ignora e conta a linha sem assinatura ou que não confere.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata
from datetime import datetime, timezone

from .equipamento import canon
from .fatos import _id, _txt, data_do_registro

LIVRO, ABA, ABA_ATU = "nexus_chamados_abertos", "fato_chamado_aberto", "atualizacao"
NOME_LIVRO = "Nexus · chamados de garantia em aberto (para o App de Campo)"
# as colunas, nesta ordem, são o contrato com o App; coluna nova só no FIM, nos dois lados. A assinatura cobre os
# `ASSINADOS`, na ordem; a linhagem (regra 5: por onde o equipamento e a usina ligaram) vem depois dela, fora da assinatura
ASSINADOS = ("inspecao_folio", "adm_folio", "codigo", "equipamento_id", "usina_id", "coluna", "data_id_inspecao",
             "atualizado_em")
CAB = list(ASSINADOS) + ["assinatura", "equipamento_ligado_por", "usina_ligada_por"]
CAB_ATU = ["gerado_em", "linhas", "lista_lida_em", "tickets_lidos_em", "assinatura"]
COLUNAS = ("aguardando_inspecao", "chegaram", "ticket_aberto")
# foto do que está aberto agora, sem medida (o tipo do catálogo para o fato sem medida; o "foto" está no grão e na aba
# `atualizacao`)
TIPO = "sem_medida"
GRAO = ("1 linha = 1 chamado de garantia em aberto agora, pela Inspeção (a administrativa retroativa sem Inspeção, pela "
        "própria administrativa)")
CHAVE = ("inspecao_folio", "adm_folio")
FONTES = (("OS Creator (lista central de OS, credencial da empresa)", "Inspeções de garantia e OS de acompanhamento"),
          ("OS Creator (cópia do quadro do Acompanhamento de chamados)", "o ticket de cada OS de acompanhamento"))
JANELA_ORIGEM = "o que está aberto agora (foto; a lista central guarda toda OS aberta, de qualquer idade)"
MEDIDAS = ()
# a chave da assinatura (a MESMA conta no App): deriva da NEXUS_PESSOA_HMAC; mudou aqui, muda lá
ROTULO_CHAVE = b"nexus:oscreator:chamados-app"

# CÓPIAS do pacote `chamado_garantia` e do quadro (`acomp_web`): a camada de dados não importa o clone do OS Creator, e um
# teste confere que são as mesmas (tests/test_dados_chamado_aberto.py)
TIPO_INSPECAO, ETIQUETA_INSPECAO = "Inspeção", "Aguardando Garantia"
TIPO_ADM, ETIQUETA_ADM = "Administrativa", "CHAMADOS"
MARCA_NOTA = "[CHAMADO] Acompanhamento"
LINHA_AGUARDANDO = "Campos do formulário do fabricante: aguardando a inspeção"
EM_PROCESSO, EM_VERIFICACAO, CONCLUIDA, CANCELADA = 1, 2, 3, 4


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", _txt(s)).encode("ascii", "ignore").decode("ascii")
    return " ".join(s.lower().split())


def _campo(r, nome):
    """O campo do registro da lista central (`RegistroOS`: atributo e `get`) ou de um dicionário (os testes)."""
    g = getattr(r, "get", None)
    if callable(g):
        return g(nome)
    return getattr(r, nome, None)


def _codigo(r) -> str:
    c = _campo(r, "code")
    if not c:
        cods = _campo(r, "codigos") or ()
        c = cods[-1] if cods else ""
    return _txt(c)


def etiquetas(r) -> set:
    """Os nomes das etiquetas da OS, normalizados. A lista central guarda ((id, nome), ...)."""
    out = set()
    for e in _campo(r, "etiquetas") or ():
        nome = e[1] if isinstance(e, (tuple, list)) and len(e) > 1 else (e.get("nome") if isinstance(e, dict) else e)
        if _norm(nome):
            out.add(_norm(nome))
    return out


def eh_inspecao(r) -> bool:
    return _norm(_campo(r, "tipo_tarefa")) == _norm(TIPO_INSPECAO) and _norm(ETIQUETA_INSPECAO) in etiquetas(r)


def eh_acompanhamento(r) -> bool:
    """A OS de acompanhamento do quadro: a etiqueta CHAMADOS (o quadro lê pela etiqueta) e o `acomp_web.eh_os3` (a marca da
    nota; sem nota, o título com o tipo Administrativa)."""
    if _norm(ETIQUETA_ADM) not in etiquetas(r):
        return False
    if MARCA_NOTA in _txt(_campo(r, "note")):
        return True
    return ("acompanhamento de chamado" in _norm(_campo(r, "descricao"))
            and _norm(TIPO_ADM) in _norm(_campo(r, "tipo_tarefa")))


def _num(rx: str, s: str) -> str:
    m = re.search(rx, s)
    return m.group(1) if m else ""


_RX_CADEIA = re.compile(r"\b(?:OS de campo|OS de abertura|Inspeção|Ativo)\s*:")


def cadeia(nota) -> tuple[str, str]:
    """(nº da Inspeção, código do ativo) da linha da cadeia da nota da administrativa, como o `acomp_web.ler_nota`: a do
    App ("OS de campo: X · Inspeção: Y · Ativo: Z") e a da retroativa ("OS de abertura: X · ..."; sem "Inspeção:", a OS de
    campo faz o papel dela)."""
    txt = _txt(nota)
    i = txt.find(MARCA_NOTA)
    if i < 0:
        return "", ""
    for linha in txt[i:].split("\n")[1:]:
        s = linha.strip()
        if s and _RX_CADEIA.search(s):
            abertura, campo = _num(r"OS de abertura:\s*(\d+)", s), _num(r"OS de campo:\s*(\d+)", s)
            insp = _num(r"Inspeção:\s*(\d+)", s)
            return (insp or campo) if abertura else insp, _num(r"Ativo:\s*(\S+)", s)
    return "", ""


def nota_aguardando(nota) -> bool:
    """A cópia do `chamado_garantia.nota_aguardando`: a nota da administrativa ainda espera a inspeção."""
    return LINHA_AGUARDANDO.lower() in _txt(nota).lower()


def iso_z(d: datetime) -> str:
    """O instante em ISO UTC com Z, até o segundo: o formato do `atualizado_em` e do `gerado_em` que o App assina igual."""
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _t(v) -> str:
    """O campo como texto, do jeito que a assinatura e a comparação usam: vazio = "", número inteiro sem ".0" (a API pode
    devolver tudo como texto, ou o inteiro como float)."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    s = str(v).strip()
    return s[:-2] if re.fullmatch(r"\d+\.0", s) else s


def _chave_hmac(chave_base: str) -> bytes | None:
    base = (chave_base or "").strip()
    return hmac.new(base.encode("utf-8"), ROTULO_CHAVE, hashlib.sha256).digest() if base else None


def texto_assinado(linha: dict) -> str:
    return "|".join(["chamado_aberto"] + [_t(linha.get(c)) for c in ASSINADOS])


def assinatura(linha: dict, chave_base: str) -> str:
    """HMAC-SHA256 em hex minúsculo do texto "chamado_aberto|inspecao_folio|adm_folio|codigo|equipamento_id|usina_id|
    coluna|data_id_inspecao|atualizado_em" (campo vazio = texto vazio). Sem chave: "" (o App não aceita a linha)."""
    k = _chave_hmac(chave_base)
    return hmac.new(k, texto_assinado(linha).encode("utf-8"), hashlib.sha256).hexdigest() if k else ""


def texto_assinado_atualizacao(linha: dict) -> str:
    return "|".join(["atualizacao_chamados"] + [_t(linha.get(c)) for c in CAB_ATU[:-1]])


def assinatura_atualizacao(linha: dict, chave_base: str) -> str:
    """A da linha da `atualizacao`: "atualizacao_chamados|gerado_em|linhas|lista_lida_em|tickets_lidos_em"."""
    k = _chave_hmac(chave_base)
    return hmac.new(k, texto_assinado_atualizacao(linha).encode("utf-8"), hashlib.sha256).hexdigest() if k else ""


def _conteudo(linha: dict) -> tuple:
    """O que a linha diz, sem a hora e a assinatura: igual ao da foto anterior, a hora de quando ficou assim fica."""
    return tuple(_t(linha.get(c)) for c in CAB if c not in ("atualizado_em", "assinatura"))


def _ligar(equip, codigo) -> tuple:
    """(equipamento_id, usina_id) pelo código na dimensão de equipamento; não liga = (None, None), nunca chutado."""
    if not equip or not codigo:
        return None, None
    v = equip(canon(codigo)) if callable(equip) else equip.get(canon(codigo))
    if not v:
        return None, None
    eid, uid = (tuple(v) + (None, None))[:2] if isinstance(v, (tuple, list)) else (v, None)
    return _id(eid), _id(uid)


def linhas(registros, tickets: dict | None, equip, anteriores, agora: datetime, chave_base: str,
           conta: dict | None = None, a_conferir=frozenset()) -> list[dict]:
    """As linhas do fato, ordenadas pela chave (o mesmo conteúdo dá o mesmo arquivo).

    `registros`: as OS da lista central (ou dicionários com id, folio, tipo_tarefa, etiquetas, status_id, note, descricao,
    code, data); `tickets`: {id da administrativa: o ticket} da cópia do quadro, só das que ela leu (fora dela = não sei);
    `equip`: código canônico → (equipamento_id, usina_id); `anteriores`: as linhas gravadas agora no banco, para a linha que
    não mudou manter o `atualizado_em` (e a assinatura) de quando ficou assim; `conta`: as contagens da volta."""
    conta = conta if conta is not None else {}
    for k in ("inspecoes", "acompanhamentos", "sem_inspecao", "mais_de_um", "sem_equipamento", "coluna_desconhecida",
              "a_conferir"):
        conta.setdefault(k, 0)
    tickets = tickets or {}
    insp, adms = {}, {}
    for r in registros or ():
        st = _campo(r, "status_id")
        if eh_inspecao(r):
            f = _t(_campo(r, "folio"))
            if f:
                insp[f] = r
        elif eh_acompanhamento(r) and st != CANCELADA:
            f, _ativo = cadeia(_campo(r, "note"))
            adms.setdefault(f, []).append(r)
    ante = {(_t(a.get("inspecao_folio")), _t(a.get("adm_folio"))): a for a in anteriores or ()}
    stamp = iso_z(agora)
    out = []

    def montar(f_insp: str, i, a):
        codigo = _codigo(i) if i is not None else ""
        if not codigo and a is not None:
            codigo = _codigo(a) or cadeia(_campo(a, "note"))[1]
        eid, uid = _ligar(equip, codigo)
        if eid is None:
            conta["sem_equipamento"] += 1
        if a is None:
            col = "aguardando_inspecao" if _campo(i, "status_id") == EM_PROCESSO else ""
        elif (i is not None and _campo(i, "status_id") == EM_PROCESSO) or nota_aguardando(_campo(a, "note")):
            col = "aguardando_inspecao"
        elif _campo(a, "id") in tickets and tickets[_campo(a, "id")] is not None:
            col = "ticket_aberto" if _txt(tickets[_campo(a, "id")]) else "chegaram"
        else:
            col = ""
        if not col:
            conta["coluna_desconhecida"] += 1
        if any(x is not None and _campo(x, "id") in a_conferir for x in (i, a)):
            conta["a_conferir"] += 1
        lin = {"inspecao_folio": f_insp, "adm_folio": _t(_campo(a, "folio")) if a is not None else "",
               "codigo": codigo, "equipamento_id": eid, "usina_id": uid, "coluna": col,
               "data_id_inspecao": data_do_registro(_campo(i, "data")) if i is not None else None,
               "equipamento_ligado_por": "código do ativo" if eid else "",
               "usina_ligada_por": "equipamento" if uid else ""}
        velha = ante.get((lin["inspecao_folio"], lin["adm_folio"]))
        mesma = velha is not None and _conteudo(velha) == _conteudo(lin)
        lin["atualizado_em"] = (_t(velha.get("atualizado_em")) or stamp) if mesma else stamp
        lin["assinatura"] = assinatura(lin, chave_base)
        out.append({c: lin.get(c) for c in CAB})

    for f, lista in adms.items():
        abertas = [a for a in lista if _campo(a, "status_id") == EM_PROCESSO]
        if len(abertas) > 1 and f:
            conta["mais_de_um"] += 1
        for a in abertas:
            conta["acompanhamentos"] += 1
            if not f:
                conta["sem_inspecao"] += 1
            montar(f, insp.get(f) if f else None, a)
    for f, i in insp.items():
        if _campo(i, "status_id") in (EM_PROCESSO, EM_VERIFICACAO) and not adms.get(f):
            conta["inspecoes"] += 1
            montar(f, i, None)
    out.sort(key=lambda l: (l["inspecao_folio"], l["adm_folio"]))
    return out


def atualizacao(n_linhas: int, agora: datetime, lista_lida_em: datetime | None, tickets_lidos_em: datetime | None,
                chave_base: str) -> dict:
    """A linha única da aba `atualizacao`: quando a foto foi gerada, quantas linhas tem e de quando são as leituras."""
    lin = {"gerado_em": iso_z(agora), "linhas": int(n_linhas),
           "lista_lida_em": iso_z(lista_lida_em) if lista_lida_em else "",
           "tickets_lidos_em": iso_z(tickets_lidos_em) if tickets_lidos_em else ""}
    lin["assinatura"] = assinatura_atualizacao(lin, chave_base)
    return lin


def corpo(linhas_: list[dict], cab) -> list[list]:
    """As linhas no formato do `livros.publicar`: vazio vira None (célula vazia no xlsx)."""
    return [[None if l.get(c) in ("", None) else l.get(c) for c in cab] for l in linhas_]
