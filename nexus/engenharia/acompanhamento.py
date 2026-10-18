"""O acompanhamento dos ativos com sinal da Confiabilidade (Levi, 18/10/2026: "os membros de engenharia ou
administradores pegar aqueles ativos com sinal para acompanhar ou alguém da engenharia poder encaminhar para a pessoa
ver!"; "o que está sendo acompanhado sai de ativos com sinal e passam para em acompanhamento"). Desenho e decisões em
docs/superpowers/specs/2026-10-18-engenharia-acompanhamento-design.md.

O Nexus é a FONTE: livro `nexus_engenharia_acompanhamento`, registrado no catálogo antes da 1ª gravação (regra 10), com
duas abas gravadas sempre juntas (gravar sem uma a apagaria):
- `fato_acompanhamento_ativo`: 1 linha = 1 EVENTO sobre 1 acompanhamento de 1 ativo (`pegou`, `encaminhou`, `dados`,
  `comentario`, `encerrou`). Só acrescenta: nada se edita nem se apaga, e o estado de agora sai dos eventos, na ordem
  da gravação (o mesmo cuidado das Contestações: dois eventos no mesmo segundo ficam na ordem em que foram gravados).
- `dim_diagnostico`: o cadastro dos diagnósticos, como os motivos do PCM: excluir marca `excluido = sim` e o ID não
  volta. Antes da 1ª gravação vale o CADASTRO_INICIAL, que entra no banco junto com ela.

A API do banco tem LEITURA ABERTA (nexus/dados/CLAUDE.md, regra 8): quem fez (nome e e-mail), o nome de quem passou a
acompanhar e o texto do comentário vão só CIFRADOS (o Cofre, a chave do cadastro, como as Contestações); a pessoa liga
pelo código do e-mail (`pessoa_hmac`, `responsavel_hmac`). O ativo vai pelo código canônico e pelo `equipamento_id` da
dimensão de equipamento; a usina pelo `usina_id` que a Confiabilidade já liga ao cadastro (não liga = vazio).

Gravar troca o livro inteiro, relido do banco antes (leitura que falha não grava: gravaria por cima do que há), uma
gravação por vez neste processo (`_TRAVA`); `livros.publicar` confere a contagem depois. Duas máquinas gravando no mesmo
segundo ainda podem perder um evento: o mesmo risco aceito nos setores e nas Contestações.
"""
import json
import threading
import time
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone

from flask import current_app

from ..dados import livros
from ..dados.equipamento import canon, equipamento_id

LIVRO, NOME_LIVRO = "nexus_engenharia_acompanhamento", "Nexus · acompanhamento dos ativos da Engenharia"
ABA_DIAG, ABA_EVENTO = "dim_diagnostico", "fato_acompanhamento_ativo"
CAB_EVENTO = ("id", "registrado_em", "data_id", "acompanhamento_id", "evento", "codigo_ativo", "equipamento_id",
              "usina_id", "usina_ligada_por", "pessoa_hmac", "responsavel_hmac", "diagnostico_id",
              "data_id_inicio_analise", "data_id_fim_analise", "nivel_na_entrada", "falhas_30d_qtd", "falhas_7d_qtd",
              "dados_cifrados")
CAB_DIAG = ("diagnostico_id", "nome", "descricao", "criado_em", "alterado_em", "excluido", "alterado_por_hmac")
EVENTOS = ("pegou", "encaminhou", "dados", "comentario", "encerrou")
COMECO = ("pegou", "encaminhou")          # os eventos que começam um acompanhamento (e trocam quem acompanha)
# a lista que o Levi começou no pedido ("comunicação, disjuntor"); o resto a Engenharia cadastra na tela
CADASTRO_INICIAL = (("Comunicação", ""), ("Disjuntor", ""))
TEXTO_MAX = 2000                          # o teto das atualizações das Contestações
SETOR = "engenharia"                      # o nome do setor (sem acento nem caixa) de quem age, além do administrador
TTL_S = 60
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê, para a tela mostrar."""


def limpar() -> None:
    """Zera a cópia: quem acabou de gravar tem de se ver na próxima leitura."""
    _CACHE.clear()


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _int(v) -> int | None:
    """A API pode devolver tudo como texto ("5", "5.0", "20261018"): o número sai igual."""
    if v is None or _txt(v) == "":
        return None
    try:
        return int(float(_txt(v).replace(",", ".")))
    except ValueError:
        return None


def _sim(v) -> bool:
    return _norm(v) in ("sim", "1", "true", "verdadeiro")


def _dia(v) -> date | None:
    """`data_id` (AAAAMMDD) -> date."""
    n = _int(v)
    if not n:
        return None
    try:
        return datetime.strptime(str(n), "%Y%m%d").date()
    except ValueError:
        return None


def _id_dia(d: date | None) -> int | None:
    return int(d.strftime("%Y%m%d")) if d else None


def _quando(v) -> datetime | None:
    try:
        return datetime.fromisoformat(_txt(v).replace("Z", "+00:00")).astimezone(_BRT)
    except ValueError:
        return None


def _cofre():
    chave = current_app.config.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): sem ela nada vai cifrado")
    from ..cadastro.cifra import Cofre
    return Cofre(chave)


def _cofre_ou_nada():
    try:
        return _cofre()
    except Recusada:
        return None


def _ctx(eid) -> str:
    return f"banco/engenharia_acompanhamento/{eid}/dados"


def _banco():
    from ..campo import visao
    return visao._base(), visao._sessao()


def _ler_banco(base: str, sessao) -> dict:
    """As duas abas lidas agora (uma listagem e duas leituras). Livro que ainda não existe = vazio. Erro sobe."""
    a = livros.abas(base, sessao, LIVRO)
    return {"eventos": livros._linhas(base, sessao, a[ABA_EVENTO]) if ABA_EVENTO in a else [],
            "diagnosticos": livros._linhas(base, sessao, a[ABA_DIAG]) if ABA_DIAG in a else []}


def ler(forcar: bool = False) -> dict:
    """{"eventos", "diagnosticos" (as linhas cruas), "lido_em", "erro"}, guardado por 1 minuto. Leitura que falha
    devolve a última boa com o erro; sem nenhuma, vazio com o erro (a tela diz que não leu, e não "nenhum")."""
    g = _CACHE.get("livro")
    if g and not forcar and time.time() - g["lido_em"] < TTL_S:
        return g
    try:
        d = _ler_banco(*_banco())
    except Exception as ex:      # noqa: BLE001 — banco fora, rede: a tela diz e não deixa gravar
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        if g:
            return dict(g, erro=erro, velha=True)
        return {"eventos": [], "diagnosticos": [], "lido_em": None, "erro": erro}
    g = dict(d, lido_em=time.time(), erro="")
    _CACHE["livro"] = g
    return g


def diagnosticos(linhas: list[dict]) -> list[dict]:
    """O cadastro, pelo id: [{"id", "nome", "descricao", "excluido"}]. Livro sem cadastro = o CADASTRO_INICIAL."""
    if not linhas:
        return [{"id": i, "nome": n, "descricao": d, "excluido": False} for i, (n, d) in enumerate(CADASTRO_INICIAL, 1)]
    out = [{"id": _int(l.get("diagnostico_id")), "nome": _txt(l.get("nome")), "descricao": _txt(l.get("descricao")),
            "excluido": _sim(l.get("excluido"))} for l in linhas]
    return sorted((d for d in out if d["id"]), key=lambda d: d["id"])


def _linhas_do_cadastro(linhas: list[dict]) -> list[dict]:
    """As linhas da aba do cadastro como vão ao banco: as que há, ou o cadastro inicial na 1ª gravação."""
    if linhas:
        return linhas
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return [{"diagnostico_id": d["id"], "nome": d["nome"], "descricao": d["descricao"], "criado_em": agora,
             "alterado_em": agora, "excluido": None, "alterado_por_hmac": None} for d in diagnosticos([])]


def _abre(cofre, l: dict) -> dict:
    if not cofre or not l.get("dados_cifrados"):
        return {}
    try:
        return json.loads(cofre.decifrar(_txt(l.get("dados_cifrados")), _ctx(_txt(l.get("id")))))
    except Exception:           # noqa: BLE001 — cifra de outra chave ou adulterada: sai sem nome nem texto
        return {}


def estado(eventos: list[dict]) -> dict[str, dict]:
    """{acompanhamento_id: acompanhamento} a partir dos eventos, na ordem da gravação. Evento sem o começo dele no livro
    (um `dados` cujo `pegou` não está) fica fora: não há de quem nem de que ativo ele é."""
    cofre = _cofre_ou_nada()
    ordem = {id(e): i for i, e in enumerate(eventos)}
    linhas = sorted(eventos, key=lambda e: (_quando(e.get("registrado_em")) or datetime.min.replace(tzinfo=_BRT),
                                            ordem[id(e)]))
    out: dict[str, dict] = {}
    for l in linhas:
        aid, ev = _txt(l.get("acompanhamento_id")), _txt(l.get("evento"))
        if not aid or ev not in EVENTOS:
            continue
        a = out.get(aid)
        if a is None and ev not in COMECO:
            continue
        dados, q = _abre(cofre, l), _quando(l.get("registrado_em"))
        quem = dados.get("quem") or {}
        if a is None:
            a = out[aid] = {
                "id": aid, "cod": _txt(l.get("codigo_ativo")), "equipamento_id": _int(l.get("equipamento_id")),
                "usina_id": _int(l.get("usina_id")), "usina_ligada_por": _txt(l.get("usina_ligada_por")),
                "responsavel": {"hmac": "", "nome": ""}, "encaminhado_por": "", "desde": q, "inicio": None,
                "fim": None, "diagnostico_id": None, "comentarios": [], "aberto": True, "encerrado_em": None,
                "nivel_entrada": _txt(l.get("nivel_na_entrada")), "falhas30_entrada": _int(l.get("falhas_30d_qtd")),
                "falhas7_entrada": _int(l.get("falhas_7d_qtd"))}
        if ev in COMECO:
            resp = _txt(l.get("responsavel_hmac"))
            a["responsavel"] = {"hmac": resp, "nome": dados.get("responsavel") or ""}
            # encaminhar para si mesmo é assumir: não há "encaminhado por" você mesmo
            a["encaminhado_por"] = (quem.get("nome") or "") if ev == "encaminhou" and _txt(l.get("pessoa_hmac")) != resp else ""
        if _dia(l.get("data_id_inicio_analise")):
            a["inicio"] = _dia(l.get("data_id_inicio_analise"))
        if _int(l.get("diagnostico_id")):
            a["diagnostico_id"] = _int(l.get("diagnostico_id"))
        if ev == "comentario":
            a["comentarios"].insert(0, {"quando": q, "quando_txt": q.strftime("%d/%m/%Y às %H:%M") if q else "—",
                                        "nome": quem.get("nome") or quem.get("email") or "",
                                        "texto": dados.get("texto") or ""})
        elif ev == "encerrou":
            a["fim"], a["aberto"], a["encerrado_em"] = _dia(l.get("data_id_fim_analise")), False, q
    return out


def aberto_de(acomps: dict[str, dict], cod) -> dict | None:
    """O acompanhamento aberto do ativo (pelo código canônico), ou None."""
    c = canon(cod)
    return next((a for a in acomps.values() if a["aberto"] and canon(a["cod"]) == c), None)


def codigo(usuario) -> str | None:
    """O código da pessoa do login (o mesmo do App e dos setores), ou None sem e-mail ou sem a NEXUS_PESSOA_HMAC."""
    from ..campo.ligacao_cadastro import codigo_da_pessoa
    email = str((usuario or {}).get("email") or "").strip().lower()
    return codigo_da_pessoa(current_app.config.get("NEXUS_PESSOA_HMAC"), email) if email else None


def pode_agir(setor: dict | None, admin: bool) -> bool:
    """Pega, encaminha, salva, comenta e mexe no cadastro: o administrador e quem é do setor Engenharia."""
    return bool(admin) or _norm((setor or {}).get("nome")) == SETOR


def _quem(usuario, pode: bool, o_que: str) -> dict:
    if not pode:
        raise Recusada(f"Só quem é da Engenharia ou administrador {o_que}")
    email = str((usuario or {}).get("email") or "").strip().lower()
    if not email:
        raise Recusada("Entre com o seu login (Microsoft ou Fracttal) para acompanhar: a senha de administrador não "
                       "diz quem é a pessoa")
    cod = codigo(usuario)
    if not cod:
        raise Recusada("Este Nexus não tem a chave do código da pessoa (NEXUS_PESSOA_HMAC)")
    if not current_app.config.get("GRIDCO_SQL_TOKEN"):
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN)")
    return {"email": email, "nome": " ".join(str((usuario or {}).get("nome") or "").split()) or email, "hmac": cod}


def _evento(cofre, evento: str, quem: dict, aid: str, ativo: dict, *, responsavel: dict | None = None,
            inicio: date | None = None, fim: date | None = None, diagnostico_id: int | None = None,
            texto: str = "", entrada: dict | None = None) -> dict:
    """Uma linha do fato. `ativo` = {"cod", "usina_id", "usina_ligada_por"}; `entrada` = a foto do sinal, só no evento
    que começa o acompanhamento ({"nivel", "nFalha", "n7"})."""
    eid = uuid.uuid4().hex[:12]
    agora = datetime.now(timezone.utc)
    dados = {"quem": {"nome": quem["nome"], "email": quem["email"]}}
    if responsavel:
        dados["responsavel"] = responsavel["nome"]
    if texto:
        dados["texto"] = texto
    cod = canon(ativo.get("cod"))
    entrada = entrada or {}
    return {"id": eid, "registrado_em": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "acompanhamento_id": aid, "evento": evento,
            "codigo_ativo": cod, "equipamento_id": equipamento_id(cod), "usina_id": _int(ativo.get("usina_id")),
            "usina_ligada_por": _txt(ativo.get("usina_ligada_por")) or None, "pessoa_hmac": quem["hmac"],
            "responsavel_hmac": responsavel["hmac"] if responsavel else None, "diagnostico_id": diagnostico_id,
            "data_id_inicio_analise": _id_dia(inicio), "data_id_fim_analise": _id_dia(fim),
            "nivel_na_entrada": _txt(entrada.get("nivel")) or None, "falhas_30d_qtd": _int(entrada.get("nFalha")),
            "falhas_7d_qtd": _int(entrada.get("n7")),
            "dados_cifrados": cofre.cifrar(json.dumps(dados, ensure_ascii=False), _ctx(eid))}


def _reler() -> dict:
    """O livro relido do banco agora, sem a cópia: gravar sobre uma leitura velha apagaria o que outra pessoa gravou."""
    return _ler_banco(*_banco())


def _publicar(eventos: list[dict], diags: list[dict]) -> None:
    base, sessao = _banco()
    dg = _linhas_do_cadastro(diags)
    livros.publicar(LIVRO, NOME_LIVRO, {ABA_DIAG: (list(CAB_DIAG), [[d.get(c) for c in CAB_DIAG] for d in dg]),
                                        ABA_EVENTO: (list(CAB_EVENTO), [[e.get(c) for c in CAB_EVENTO] for e in eventos])},
                    base=base, token=current_app.config["GRIDCO_SQL_TOKEN"], sessao=sessao)
    limpar()


def pegar(ativo: dict, usuario, pode: bool) -> dict:
    """A pessoa do login começa a acompanhar o ativo, com o início da análise em hoje. `ativo` = o item de sinais da
    Confiabilidade no formato {"cod", "usina_id", "usina_ligada_por", "nivel", "nFalha", "n7"}."""
    quem = _quem(usuario, pode, "pega um ativo para acompanhar")
    cofre = _cofre()
    if not canon(ativo.get("cod")):
        raise Recusada("Ativo sem código")
    with _TRAVA:
        lido = _reler()
        ab = aberto_de(estado(lido["eventos"]), ativo.get("cod"))
        if ab:
            raise Recusada(f"Este ativo já está com {ab['responsavel']['nome'] or 'outra pessoa'}")
        nova = _evento(cofre, "pegou", quem, uuid.uuid4().hex[:12], ativo, responsavel=quem,
                       inicio=datetime.now(_BRT).date(), entrada=ativo)
        _publicar(lido["eventos"] + [nova], lido["diagnosticos"])
    return nova


def _ativo_de(a: dict) -> dict:
    return {"cod": a["cod"], "usina_id": a["usina_id"], "usina_ligada_por": a.get("usina_ligada_por")}


def _do_livro(lido: dict, acompanhamento_id) -> dict:
    """O acompanhamento aberto, ou a recusa: não achado, ou encerrado (encerrado fica só para ler)."""
    a = estado(lido["eventos"]).get(_txt(acompanhamento_id))
    if not a:
        raise Recusada("Não achei este acompanhamento: recarregue a página")
    if not a["aberto"]:
        raise Recusada("Este acompanhamento já foi encerrado: fica só para ler")
    return a


def encaminhar(ativo: dict, para_hmac: str, usuario, pode: bool, pessoas: list[dict]) -> dict:
    """Passa o ativo para uma pessoa da Engenharia (`pessoas`, de `pessoas_da_engenharia`). Ativo livre: começa o
    acompanhamento com quem recebeu, o início em hoje. Ativo acompanhado: troca quem acompanha (para si mesmo = assumir)."""
    quem = _quem(usuario, pode, "encaminha um ativo")
    para = next((p for p in pessoas or [] if p.get("hmac") and p["hmac"] == _txt(para_hmac)), None)
    if not para:
        raise Recusada("Escolha uma pessoa da Engenharia para encaminhar")
    cofre = _cofre()
    if not canon(ativo.get("cod")):
        raise Recusada("Ativo sem código")
    resp = {"hmac": para["hmac"], "nome": para.get("nome") or ""}
    with _TRAVA:
        lido = _reler()
        ab = aberto_de(estado(lido["eventos"]), ativo.get("cod"))
        if ab and ab["responsavel"]["hmac"] == resp["hmac"]:
            raise Recusada(f"Este ativo já está com {ab['responsavel']['nome'] or resp['nome']}")
        if ab:
            nova = _evento(cofre, "encaminhou", quem, ab["id"], _ativo_de(ab), responsavel=resp)
        else:
            nova = _evento(cofre, "encaminhou", quem, uuid.uuid4().hex[:12], ativo, responsavel=resp,
                           inicio=datetime.now(_BRT).date(), entrada=ativo)
        _publicar(lido["eventos"] + [nova], lido["diagnosticos"])
    return nova


def _data(v, campo: str) -> date | None:
    """A data do <input type="date"> (AAAA-MM-DD); vazio = None; o resto é recusado."""
    t = _txt(v)
    if not t:
        return None
    try:
        return datetime.strptime(t, "%Y-%m-%d").date()
    except ValueError:
        raise Recusada(f"Data inválida no {campo}: escolha no calendário do campo") from None


def salvar(acompanhamento_id: str, inicio: str, fim: str, diagnostico_id: str, usuario, pode: bool,
           hoje: date | None = None) -> dict:
    """Muda o início e o diagnóstico (evento `dados`) ou, com o fim, encerra (evento `encerrou`, que exige o
    diagnóstico: o fim da análise é o dia em que ela terminou, decisão do Levi de 18/10/2026)."""
    quem = _quem(usuario, pode, "muda um acompanhamento")
    hoje = hoje or datetime.now(_BRT).date()
    ini = _data(inicio, "início da análise")
    if not ini:
        raise Recusada("Escolha o início da análise")
    f = _data(fim, "fim da análise")
    diag = _int(diagnostico_id)
    if ini > hoje:
        raise Recusada("O início da análise não pode ser depois de hoje")
    if f and f > hoje:
        raise Recusada("O fim da análise não pode ser depois de hoje")
    if f and f < ini:
        raise Recusada("O fim da análise não pode ser antes do início")
    if f and not diag:
        raise Recusada("Para encerrar, escolha o diagnóstico")
    cofre = _cofre()
    with _TRAVA:
        lido = _reler()
        a = _do_livro(lido, acompanhamento_id)
        diag = diag or a["diagnostico_id"]
        if diag and diag != a["diagnostico_id"] and not any(
                d["id"] == diag and not d["excluido"] for d in diagnosticos(lido["diagnosticos"])):
            raise Recusada("Este diagnóstico não existe no cadastro (ou foi excluído): escolha outro")
        if not f and ini == a["inicio"] and diag == a["diagnostico_id"]:
            raise Recusada("Nada mudou")
        nova = _evento(cofre, "encerrou" if f else "dados", quem, a["id"], _ativo_de(a), inicio=ini, fim=f,
                       diagnostico_id=diag)
        _publicar(lido["eventos"] + [nova], lido["diagnosticos"])
    return nova


def comentar(acompanhamento_id: str, texto: str, usuario, pode: bool) -> dict:
    """Um comentário, com a data e a hora de agora e quem escreveu. Qualquer um da Engenharia escreve (o Levi não quis
    "só quem acompanha escreve", 18/10/2026); nunca se edita nem se apaga."""
    quem = _quem(usuario, pode, "comenta um acompanhamento")
    texto = "\n".join(" ".join(l.split()) for l in str(texto or "").strip().splitlines()).strip()
    if not texto:
        raise Recusada("Escreva o comentário antes de salvar")
    if len(texto) > TEXTO_MAX:
        raise Recusada(f"O comentário passou de {TEXTO_MAX} caracteres")
    cofre = _cofre()
    with _TRAVA:
        lido = _reler()
        a = _do_livro(lido, acompanhamento_id)
        nova = _evento(cofre, "comentario", quem, a["id"], _ativo_de(a), texto=texto)
        _publicar(lido["eventos"] + [nova], lido["diagnosticos"])
    return nova


# ── o cadastro dos diagnósticos (como o Cadastro de motivos do PCM) ───────────────────────────────────────────────────
NOME_MIN, NOME_MAX, DESCRICAO_MAX = 2, 60, 300
SEM_NOME = "(sem nome no Fracttal)"


def _nome_diag(nome) -> str:
    n = " ".join(str(nome or "").split())
    if not NOME_MIN <= len(n) <= NOME_MAX:
        raise Recusada(f"O nome do diagnóstico tem de ter de {NOME_MIN} a {NOME_MAX} caracteres")
    return n


def _descricao(descricao) -> str:
    d = " ".join(str(descricao or "").split())
    if len(d) > DESCRICAO_MAX:
        raise Recusada(f"A descrição passou de {DESCRICAO_MAX} caracteres")
    return d


def _repetido(linhas: list[dict], nome: str, fora=None) -> None:
    if any(_norm(l.get("nome")) == _norm(nome) and not _sim(l.get("excluido")) and _int(l.get("diagnostico_id")) != fora
           for l in linhas):
        raise Recusada(f"O diagnóstico {nome} já existe")


def _linha_do_cadastro(linhas: list[dict], diagnostico_id) -> dict:
    l = next((l for l in linhas if _int(l.get("diagnostico_id")) == _int(diagnostico_id)), None)
    if not l:
        raise Recusada("Não achei este diagnóstico: recarregue a página")
    if _sim(l.get("excluido")):
        raise Recusada("Este diagnóstico foi excluído")
    return l


def _gravar_cadastro(mudar, usuario, pode: bool) -> dict:
    """Relê o livro, muda a aba do cadastro e grava as duas abas (os eventos como estavam)."""
    quem = _quem(usuario, pode, "mexe no cadastro dos diagnósticos")
    with _TRAVA:
        lido = _reler()
        linhas = [dict(l) for l in _linhas_do_cadastro(lido["diagnosticos"])]
        agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        alvo = mudar(linhas)
        alvo.update(alterado_em=agora, alterado_por_hmac=quem["hmac"])
        alvo.setdefault("criado_em", agora)
        _publicar(lido["eventos"], linhas)
    return alvo


def criar_diagnostico(nome: str, descricao: str, usuario, pode: bool) -> dict:
    n, d = _nome_diag(nome), _descricao(descricao)

    def mudar(linhas):
        _repetido(linhas, n)
        # o ID é o maior + 1, contando os excluídos: um ID nunca volta (os acompanhamentos antigos apontam para ele)
        nova = {"diagnostico_id": max((_int(l.get("diagnostico_id")) or 0 for l in linhas), default=0) + 1,
                "nome": n, "descricao": d or None, "excluido": None}
        linhas.append(nova)
        return nova
    return _gravar_cadastro(mudar, usuario, pode)


def mudar_diagnostico(diagnostico_id: int, nome: str, descricao: str, usuario, pode: bool) -> dict:
    n, d = _nome_diag(nome), _descricao(descricao)

    def mudar(linhas):
        l = _linha_do_cadastro(linhas, diagnostico_id)
        _repetido(linhas, n, fora=_int(diagnostico_id))
        l.update(nome=n, descricao=d or None)
        return l
    return _gravar_cadastro(mudar, usuario, pode)


def excluir_diagnostico(diagnostico_id: int, usuario, pode: bool) -> dict:
    def mudar(linhas):
        l = _linha_do_cadastro(linhas, diagnostico_id)
        l["excluido"] = "sim"
        return l
    return _gravar_cadastro(mudar, usuario, pode)


def pessoas_da_engenharia() -> list[dict]:
    """[{"hmac", "nome"}]: quem é do setor Engenharia hoje (a última decisão de cada pessoa do Fracttal, livro
    `nexus_setores`), com o código do e-mail; o nome vem do pessoal do Fracttal (guardado 1 h, só na memória e na tela).
    Os nomes primeiro, em ordem; quem está sem nome no Fracttal, no fim."""
    from ..cadastro import fracttal_pessoal as FP
    from ..cadastro import setores as S
    st = S.ler(*_banco())
    sid = next((s["setor_id"] for s in S.ativos(st.get("setores") or []) if _norm(s["nome"]) == SETOR), None)
    if sid is None:
        return []
    ultima = {}
    for d in sorted(st.get("decisoes") or [], key=lambda x: str(x.get("decidida_em") or "")):
        ultima[str(d.get("fracttal_id"))] = d
    nomes = {str(p.get("id")): p.get("nome") for p in (FP.ler_pessoal().get("pessoas") or [])}
    out = [{"hmac": d["pessoa_hmac"], "nome": nomes.get(fid) or SEM_NOME} for fid, d in ultima.items()
           if d.get("setor_id") == sid and d.get("pessoa_hmac")]
    return sorted(out, key=lambda p: (p["nome"] == SEM_NOME, _norm(p["nome"])))
