"""As ocorrências com plano de ação (Levi, 18/10/2026: "Próximas peças: o mapa das usinas e as ocorrências com plano de
ação. siga!"). A origem é o painel próprio de um supervisor (a ocorrência, o histórico e o plano de ação, em quadro e
lista); o objetivo é o de toda a Visão do responsável: largar o painel próprio e usar só o Nexus. Desenho e decisões em
docs/superpowers/specs/2026-10-18-ocorrencias-plano-de-acao-design.md; a tela em nexus/torres/campo/ocorrencias_tela.py.

O Nexus é a FONTE: livro `nexus_ocorrencias` · `fato_evento_ocorrencia`, registrado no catálogo antes da 1ª gravação
(regra 10), com a trava de livro que só cresce. 1 linha = 1 EVENTO sobre 1 ocorrência:
- `criou` e `dados`: a ocorrência inteira como ficou (título, usina, equipamento, criticidade, status, início, fim,
  descrição, OS do Fracttal e chamado); vale a última;
- `acao`: uma ação do plano (nova ou mudada, pelo `acao_id`) inteira como ficou (o texto, o responsável, o prazo e a
  situação); vale a última de cada ação;
- `andamento`: uma linha do histórico, com o dia e a hora.
Só acrescenta: nada se edita nem se apaga. O estado de agora sai dos eventos: o `criou` de cada ocorrência primeiro, depois
os outros pela hora da gravação (com milissegundos; empate fica na ordem do livro). O `criou` vem antes porque o PC e o
servidor gravam o mesmo livro: um evento gravado na máquina de relógio atrasado pode ter a hora antes do `criou`, e não
pode sumir do estado por isso (revisão final de 18/10/2026).

A API do banco tem LEITURA ABERTA (nexus/dados/CLAUDE.md, regra 8): o título, a descrição, o chamado, o texto da ação, o
andamento, o nome do responsável da ação e quem fez vão só CIFRADOS (o Cofre, a chave do cadastro, como a observação do
responsável), com a cifra amarrada à linha inteira (a ocorrência, o evento, a ação e o id: a linha mudada de lugar não
abre). Em claro só IDs, códigos e datas: a usina pelo `usina_id` do cadastro (escolhida na tela), o ativo pelo código do
Fracttal (só letras, números e hífen, e da usina: o da dimensão de equipamento ou o que leva o código da usina; texto livre
não passa) e pelo `equipamento_id` quando o código está na dimensão (não liga = vazio), quem fez pelo `pessoa_id` e pelo
código do e-mail (`pessoa_hmac`), o responsável da ação pelo `pessoa_id` (escolhido na lista do cadastro), os códigos de
criticidade, status e situação, os dias (`data_id` e os papéis) e o número das OS do Fracttal (só algarismos).

Quem grava: o Responsável O&M (pelo login de pessoa, em qualquer usina, como a observação: quem cobre as férias de outro
registra nas usinas dele) e o administrador, sempre com um login de pessoa (a senha de administrador não diz quem é a
pessoa, e o histórico guarda quem fez). Gravar troca o livro inteiro, relido do banco antes (leitura que falha não grava:
gravaria por cima do que há), uma gravação por vez neste processo (`_TRAVA`); `livros.publicar` confere antes e depois.
- Página velha não desfaz a mudança de outra pessoa: o formulário leva a `versao` (o id do último evento da ocorrência ou
  da ação) e a gravação recusa se ela mudou (revisão final: a ocorrência finalizada por um voltava a "em andamento" quando
  outro, com a página aberta desde antes, salvava só a descrição).
- Clique duplo não duplica: o formulário de criar leva o id do que vai nascer (`novo_id`, `nova_acao_id`, `evento_id`), e
  a gravação que acha esse id no livro relido não grava de novo (o livro é para sempre: a cópia não sairia mais).
Duas máquinas gravando ao mesmo tempo (entre a releitura e a gravação) ainda podem perder um evento: o risco aceito nos
outros livros do Nexus.
"""
import json
import re
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone

from flask import current_app

from ..dados import fatos as D
from ..dados import livros
from ..dados.equipamento import canon

LIVRO, NOME_LIVRO, ABA = "nexus_ocorrencias", "Nexus · ocorrências com plano de ação", "fato_evento_ocorrencia"
CAB = ("id", "registrado_em", "data_id", "ocorrencia_id", "evento", "acao_id", "usina_id", "usina_ligada_por",
       "codigo_ativo", "equipamento_id", "equipamento_ligado_por", "criticidade", "status", "data_id_inicio",
       "data_id_fim", "os", "pessoa_id", "pessoa_hmac", "responsavel_pessoa_id", "situacao", "data_id_prazo",
       "dados_cifrados")
EVENTOS = ("criou", "dados", "acao", "andamento")
# os domínios (o código vai ao banco; o rótulo, à tela). A criticidade e o status são os do painel do supervisor
CRITICIDADES = {"baixa": "Baixa", "media": "Média", "alta": "Alta", "muito_alta": "Muito alta"}
PESO = {"baixa": 1, "media": 2, "alta": 3, "muito_alta": 4}
# a etiqueta da usina na Visão geral, pela criticidade mais alta das abertas: as cores das etiquetas de lá (a média e a
# baixa não pedem atenção sozinhas: ficam neutras)
COR_ETIQUETA = {"muito_alta": "critico", "alta": "alerta", "media": "neutro", "baixa": "neutro"}
STATUS = {"em_andamento": "Em andamento", "pausado": "Pausado", "finalizado": "Finalizado"}
SITUACOES = {"a_fazer": "A fazer", "em_andamento": "Em andamento", "concluida": "Concluída"}
TITULO_MAX, TEXTO_MAX, ACAO_MAX, CHAMADO_MAX, OS_MAX = 120, 2000, 500, 120, 10
# o código do ativo vai em claro: só o formato dos códigos do Fracttal (THPN-ALT100-INVR1). Sem isto, um nome, um telefone
# ou uma fórmula ("=HYPERLINK(...)", que a planilha da gravação executaria) iam parar no banco de leitura aberta
COD_RE = re.compile(r"[A-Z0-9][A-Z0-9._/-]{1,59}")
# o id de cada coisa: a letra do que é (o = ocorrência, a = ação, e = evento) e 11 hexadecimais. A letra na frente porque a
# API do banco infere o tipo da coluna: um id só de algarismos ("123456789012", "12e3...") voltaria como número
ID_RE = {p: re.compile(p + r"[0-9a-f]{11}") for p in "oae"}
# o piso das datas: "0202-10-15" (o ano com um dígito a menos, fácil de digitar no campo de data) virava um data_id de 7
# dígitos no acompanhamento da Engenharia, e o livro é para sempre. O prazo vai até 3 anos à frente pelo mesmo motivo
PISO = date(2024, 1, 1)
PRAZO_ANOS = 3
TTL_S = 60
CHAVES = ("NEXUS_CHAVE_CADASTRO", "NEXUS_PESSOA_HMAC", "GRIDCO_SQL_TOKEN")
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}
_GERACAO = [0]          # sobe a cada limpar(): a leitura que começou antes de uma gravação não pisa na cópia dela
_RELENDO = [False]      # a releitura por trás do `ler_sem_esperar` (uma por vez; trava própria: a `_TRAVA` é das gravações)
_TRAVA_RELER = threading.Lock()


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê, para a tela mostrar."""


def limpar() -> None:
    """Zera a cópia (e a pausa depois de uma falha): quem acabou de gravar tem de se ver na próxima leitura."""
    _CACHE.clear()
    _GERACAO[0] += 1


def novo_id(prefixo: str) -> str:
    return prefixo + uuid.uuid4().hex[:11]


def _id_do_form(v, prefixo: str) -> str | None:
    t = _txt(v)
    return t if ID_RE[prefixo].fullmatch(t) else None


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _dia(v) -> date | None:
    """`data_id` (AAAAMMDD, número ou texto) -> date."""
    n = D._int(v)
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


def _quando_txt(q: datetime | None) -> str:
    return q.strftime("%d/%m/%Y às %H:%M") if q else "—"


def _mais_tarde(a: datetime | None, b: datetime | None) -> datetime | None:
    return max(a, b) if a and b else (a or b)


def _os_lida(v) -> str:
    """O número das OS como foi gravado ("16034, 16040"). A API pode devolver a coluna como número (16034.0): sai sem o
    ponto, senão a ocorrência não se editaria mais (o ".0" não é algarismo)."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    t = _txt(v)
    return t[:-2] if re.fullmatch(r"[0-9]+\.0", t) else t


def _ctx(l: dict) -> str:
    """O contexto da cifra amarra o texto à linha inteira: quem tem a chave de gravação do banco e muda a linha de
    ocorrência, de evento ou de ação perde o texto, em vez de levá-lo para outro lugar."""
    return (f"banco/ocorrencias/{_txt(l.get('ocorrencia_id'))}/{_txt(l.get('evento'))}/"
            f"{_txt(l.get('acao_id')) or '-'}/{_txt(l.get('id'))}")


def _cofre():
    chave = current_app.config.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): sem ela o texto não vai cifrado")
    from ..cadastro.cifra import Cofre
    return Cofre(chave)


def cofre_ou_nada():
    try:
        return _cofre()
    except Recusada:
        return None


def faltam_chaves() -> list[str]:
    """As chaves do .env sem as quais nada se grava (a tela não mostra formulário que só recusaria)."""
    return [k for k in CHAVES if not current_app.config.get(k)]


def _banco():
    from . import visao
    return visao._base(), visao._sessao()


# ── ler ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
def ler(forcar: bool = False) -> dict:
    """{"eventos" (as linhas cruas), "lido_em", "erro"}, guardado por 1 minuto. Leitura que falha devolve a última boa com
    o erro; sem nenhuma, vazio com o erro (a tela diz que não leu, e não "nenhuma ocorrência"). Depois de uma falha, a
    próxima tentativa espera o mesmo minuto: a Visão geral lê este livro a cada carga, e com o banco lento cada carga
    esperaria o tempo limite da leitura."""
    agora = time.time()
    g = _CACHE.get("livro")
    if g and not forcar and agora - g["lido_em"] < TTL_S:
        return g
    f = _CACHE.get("falha")
    if f and not forcar and agora - f["em"] < TTL_S:
        return dict(g, erro=f["erro"], velha=True) if g else {"eventos": [], "lido_em": None, "erro": f["erro"]}
    geracao = _GERACAO[0]
    try:
        eventos = livros.ler(*_banco(), LIVRO, ABA)
    except Exception as ex:      # noqa: BLE001 — banco fora, rede: a tela diz e segue
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        if _GERACAO[0] == geracao:
            _CACHE["falha"] = {"em": time.time(), "erro": erro}
        return dict(g, erro=erro, velha=True) if g else {"eventos": [], "lido_em": None, "erro": erro}
    novo = {"eventos": eventos, "lido_em": time.time(), "erro": ""}
    if _GERACAO[0] == geracao:   # uma gravação no meio desta leitura deixou a cópia dela, mais nova: não piso nela
        _CACHE["livro"] = novo
        _CACHE.pop("falha", None)
    return novo


def ler_sem_esperar() -> dict:
    """O `ler` de quem só mostra (a etiqueta das ocorrências na Visão geral do responsável): a cópia que houver volta NA
    HORA e, vencida, a releitura vai por trás (uma por vez), pelas regras do `ler` (a falha espera o minuto dela). Sem
    cópia nenhuma (a 1ª vez depois de subir), lê agora. Levi, 19/10/2026: "quando eu já filtrei o responsável e vou
    filtrar o cliente carrega de novo ... e acaba demorando": cada filtro é um pedido, e quem olhava a tela mais de um
    minuto antes de filtrar esperava a releitura deste livro (a listagem do banco: 0,4 a 0,9 s no banco real). Quem grava
    neste processo já deixa a cópia nova (`_publicar`); a de outra máquina aparece na volta seguinte."""
    g = _CACHE.get("livro")
    if not g:
        return ler()
    if time.time() - g["lido_em"] >= TTL_S:
        _reler_por_tras()
    return g


def _reler_por_tras() -> None:
    with _TRAVA_RELER:
        if _RELENDO[0]:
            return
        _RELENDO[0] = True
    app = current_app._get_current_object()

    def rodar():
        try:
            with app.app_context():
                ler()
        except Exception:       # noqa: BLE001 — a etiqueta segue com a cópia que tem
            pass
        finally:
            with _TRAVA_RELER:
                _RELENDO[0] = False
    if app.config.get("TESTING"):
        rodar()
    else:
        threading.Thread(target=rodar, daemon=True, name="nexus-ocorrencias-reler").start()


def _abre(cofre, l: dict) -> dict:
    if not cofre or not l.get("dados_cifrados"):
        return {}
    try:
        return json.loads(cofre.decifrar(_txt(l.get("dados_cifrados")), _ctx(l)))
    except Exception:           # noqa: BLE001 — cifra de outra chave, adulterada ou mudada de linha: sai sem texto
        return {}


def _aplica_dados(oc: dict, l: dict, dados: dict, q, quem: str) -> None:
    oc.update(usina_id=D._id(l.get("usina_id")), cod=_txt(l.get("codigo_ativo")),
              equipamento_id=D._id(l.get("equipamento_id")), criticidade=_txt(l.get("criticidade")),
              status=_txt(l.get("status")), inicio=_dia(l.get("data_id_inicio")), fim=_dia(l.get("data_id_fim")),
              os=_os_lida(l.get("os")), titulo=dados.get("titulo") or "", descricao=dados.get("descricao") or "",
              chamado=dados.get("chamado") or "", versao=_txt(l.get("id")), versao_em=q, versao_por=quem,
              alterada_em=_mais_tarde(oc.get("alterada_em"), q))


def estado(eventos: list[dict], cofre=None, hoje: date | None = None) -> dict[str, dict]:
    """{ocorrencia_id: ocorrência} a partir dos eventos. Evento de ocorrência sem `criou` no livro fica fora (não há de que
    usina nem de que ocorrência ele é). Sem o `cofre` (sem a chave do cadastro), os códigos e as datas continuam e o texto
    sai vazio."""
    hoje = hoje or datetime.now(_BRT).date()
    ordem = {id(e): i for i, e in enumerate(eventos)}
    nunca = datetime.min.replace(tzinfo=_BRT)
    out: dict[str, dict] = {}
    for l in eventos:                                # 1º o criou de cada ocorrência (o 1º do livro): a base dela
        oid = _txt(l.get("ocorrencia_id"))
        if oid and _txt(l.get("evento")) == "criou" and oid not in out:
            dados, q = _abre(cofre, l), _quando(l.get("registrado_em"))
            quem = (dados.get("quem") or {}).get("nome") or ""
            out[oid] = {"id": oid, "_criou": id(l), "criada_em": q, "criada_por": quem, "acoes": [], "_acoes": {},
                        "andamentos": []}
            _aplica_dados(out[oid], l, dados, q, quem)
    for l in sorted(eventos, key=lambda e: (_quando(e.get("registrado_em")) or nunca, ordem[id(e)])):
        oc, ev = out.get(_txt(l.get("ocorrencia_id"))), _txt(l.get("evento"))
        if oc is None or ev not in ("dados", "acao", "andamento"):
            continue
        dados, q = _abre(cofre, l), _quando(l.get("registrado_em"))
        quem = (dados.get("quem") or {}).get("nome") or ""
        if ev == "dados":
            _aplica_dados(oc, l, dados, q, quem)
        elif ev == "acao":
            aid = _txt(l.get("acao_id"))
            if not aid:
                continue
            a = oc["_acoes"].get(aid)
            if a is None:
                a = oc["_acoes"][aid] = {"id": aid, "criada_em": q}
                oc["acoes"].append(a)
            a.update(texto=dados.get("texto") or "", responsavel_id=D._id(l.get("responsavel_pessoa_id")),
                     responsavel=dados.get("responsavel") or "", prazo=_dia(l.get("data_id_prazo")),
                     situacao=_txt(l.get("situacao")), alterada_em=q, alterada_por=quem, versao=_txt(l.get("id")))
            oc["alterada_em"] = _mais_tarde(oc["alterada_em"], q)
        else:
            oc["andamentos"].insert(0, {"quando": q, "quando_txt": _quando_txt(q), "nome": quem,
                                        "texto": dados.get("texto") or ""})
            oc["alterada_em"] = _mais_tarde(oc["alterada_em"], q)
    for oc in out.values():
        oc.pop("_acoes")
        oc.pop("_criou")
        oc["aberta"] = oc["status"] != "finalizado"
        for a in oc["acoes"]:
            a["aberta"] = a["situacao"] != "concluida"
            # a ação esquecida aberta numa ocorrência finalizada não está "atrasada": a ocorrência acabou
            a["atrasada"] = bool(oc["aberta"] and a["aberta"] and a["prazo"] and a["prazo"] < hoje)
        prazos = [a["prazo"] for a in oc["acoes"] if a["aberta"] and a["prazo"]]
        oc["proximo_prazo"] = min(prazos) if prazos else None
        oc["atrasada"] = bool(oc["aberta"] and oc["proximo_prazo"] and oc["proximo_prazo"] < hoje)
        oc["acoes_abertas"] = sum(a["aberta"] for a in oc["acoes"])
    return out


def ordenar(lista: list[dict]) -> list[dict]:
    """A ordem da lista (a do painel do supervisor): as abertas com prazo, a do prazo mais perto primeiro; as abertas sem
    prazo, a mais crítica e depois a mais antiga; as finalizadas no fim, a que terminou por último primeiro."""
    longe = date.max

    def chave(o):
        if not o["aberta"]:
            return (2, -(o["fim"] or o["inicio"] or date.min).toordinal(), o["id"])
        if o["proximo_prazo"]:
            return (0, o["proximo_prazo"].toordinal(), -PESO.get(o["criticidade"], 0), o["id"])
        return (1, -PESO.get(o["criticidade"], 0), (o["inicio"] or longe).toordinal(), o["id"])
    return sorted(lista, key=chave)


def abertas_por_usina(est: dict[str, dict]) -> dict[int, dict]:
    """{usina_id: {"n": quantas abertas, "pior": a criticidade mais alta delas}} (aberta = status diferente de
    finalizado), para a etiqueta da Visão geral."""
    out: dict[int, dict] = {}
    for o in est.values():
        if not o["aberta"] or not o["usina_id"]:
            continue
        u = out.setdefault(o["usina_id"], {"n": 0, "pior": o["criticidade"]})
        u["n"] += 1
        if PESO.get(o["criticidade"], 0) > PESO.get(u["pior"], 0):
            u["pior"] = o["criticidade"]
    return out


# ── gravar ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def pode_editar(admin: bool, responsavel_logado: str) -> bool:
    """Cria e edita: o administrador e quem é Responsável O&M de alguma usina mobilizada."""
    return bool(admin) or bool(responsavel_logado)


def _quem(usuario, pode: bool) -> dict:
    if not pode:
        raise Recusada("Só o Responsável O&M (pelo login do Fracttal) ou um administrador registra ocorrências")
    email = str((usuario or {}).get("email") or "").strip().lower()
    if not email:
        raise Recusada("Entre com o seu login (Fracttal ou Microsoft) para registrar: a senha de administrador não diz "
                       "quem é a pessoa")
    from .ligacao_cadastro import codigo_da_pessoa
    cfg = current_app.config
    codigo = codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), email)
    if not codigo:
        raise Recusada("Este Nexus não tem a chave do código da pessoa (NEXUS_PESSOA_HMAC)")
    if not cfg.get("GRIDCO_SQL_TOKEN"):
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN)")
    nome = " ".join(str((usuario or {}).get("nome") or "").split()) or email
    from . import visao
    try:
        pid = visao.pessoa_do_login(email, nome)
    except Exception:           # noqa: BLE001 — sem cadastro: fica o código do e-mail (regra 4: não liga = vazio)
        pid = None
    return {"email": email, "nome": nome, "hmac": codigo, "pessoa_id": pid}


def _linha(texto, maximo: int, falta: str, nome: str) -> str:
    """Uma linha só (o título, o chamado): os espaços repetidos viram um."""
    t = " ".join(str(texto or "").split())
    if falta and not t:
        raise Recusada(falta)
    if len(t) > maximo:
        raise Recusada(f"{nome} passou de {maximo} caracteres")
    return t


def _texto(texto, maximo: int, falta: str, nome: str) -> str:
    """Texto de várias linhas (a descrição, a ação, o andamento): as linhas ficam, os espaços repetidos de cada uma não."""
    t = "\n".join(" ".join(l.split()) for l in str(texto or "").strip().splitlines()).strip()
    if falta and not t:
        raise Recusada(falta)
    if len(t) > maximo:
        raise Recusada(f"{nome} passou de {maximo} caracteres")
    return t


def _data(v, campo: str, piso: date, teto: date, depois: str) -> date | None:
    """A data do <input type="date"> (AAAA-MM-DD); vazio = None; o resto é recusado com o porquê."""
    t = _txt(v)
    if not t:
        return None
    try:
        d = datetime.strptime(t, "%Y-%m-%d").date()
    except ValueError:
        raise Recusada(f"Data inválida no {campo}: escolha no calendário do campo") from None
    if d < piso:
        raise Recusada(f"Data inválida no {campo}: antes de {piso:%d/%m/%Y}")
    if d > teto:
        raise Recusada(depois)
    return d


def _os(v) -> str:
    """O número das OS do Fracttal: só algarismos comuns (0 a 9: o \\d aceitaria os de outras escritas, que iriam em
    claro para o banco), várias separadas por vírgula ("16034, 16040")."""
    t = _txt(v)
    if re.sub(r"[0-9,;/\s]", "", t):
        raise Recusada("O número da OS do Fracttal só tem algarismos (separe várias com vírgula)")
    nums = re.findall(r"[0-9]+", t)
    if len(nums) > OS_MAX or any(len(n) > 9 for n in nums):
        raise Recusada(f"Até {OS_MAX} OS do Fracttal, de até 9 algarismos cada")
    return ", ".join(nums)


def _equipamentos() -> dict:
    """{código canônico: (equipamento_id, usina_id)} da dimensão de equipamento (a cópia de 2 min do visao._livro); sem
    ela, vazio (não liga)."""
    from . import visao
    try:
        dim = visao._livro("nexus_equipamentos", "dim_equipamento")
    except Exception:           # noqa: BLE001 — sem a dimensão, não liga
        return {}
    return {canon(e.get("codigo")): (D._id(e.get("equipamento_id")), D._id(e.get("usina_id")))
            for e in dim if canon(e.get("codigo"))}


def _ativo(v, uid: int, usina: dict | None) -> tuple[str, int | None]:
    """(código canônico, equipamento_id ou None). O código vai em claro: só o formato do Fracttal e só desta usina (o da
    dimensão de equipamento, que não seja de outra usina, ou o que leva o código dela, a regra do `equipamento.valido`)."""
    cod = canon(v)
    if not cod:
        return "", None
    if not COD_RE.fullmatch(cod):
        raise Recusada("O código do ativo é o do Fracttal: letras, números e hífen, como THPN-ALT100-INVR1 (ele vai em "
                       "claro para o banco)")
    eq, dono = _equipamentos().get(cod, (None, None))
    if eq:
        if dono and dono != uid:
            raise Recusada("Este código do ativo é de outra usina no cadastro de equipamentos")
        return cod, eq
    cod_usina = canon((usina or {}).get("codigo"))
    if not cod_usina or cod_usina not in cod:
        raise Recusada(f"O código do ativo não é desta usina: o do Fracttal leva o código dela "
                       f"({cod_usina or 'sem código no cadastro'})")
    return cod, None


def _campos(form: dict, hoje: date, b, checar_usina: bool = True) -> dict:
    """Os campos da ocorrência validados, como vão ao estado (para comparar) e ao banco. `b` = o cadastro
    (`visao._Base`). Na edição a usina é conferida depois, com a ocorrência relida (a que saiu da operação continua)."""
    titulo = _linha(form.get("titulo"), TITULO_MAX, "Escreva o título da ocorrência", "O título")
    uid = D._id(form.get("usina_id"))
    if not uid:
        raise Recusada("Escolha a usina")
    if checar_usina and uid not in b.mobilizadas:
        raise Recusada("Esta usina não está mobilizada no cadastro")
    crit, st = _txt(form.get("criticidade")), _txt(form.get("status"))
    if crit not in CRITICIDADES:
        raise Recusada("Escolha a criticidade")
    if st not in STATUS:
        raise Recusada("Escolha o status")
    ini = _data(form.get("inicio"), "início", PISO, hoje, "O início não pode ser depois de hoje")
    if not ini:
        raise Recusada("Escolha o início da ocorrência")
    fim = _data(form.get("fim"), "fim", PISO, hoje, "O fim não pode ser depois de hoje")
    if fim and fim < ini:
        raise Recusada("O fim não pode ser antes do início")
    if fim and st != "finalizado":
        raise Recusada("Com a data de fim, o status é Finalizado: mude o status ou apague o fim")
    if st == "finalizado" and not fim:
        fim = hoje                      # finalizada sem o fim termina hoje (o campo diz isso na tela)
    cod, eq = _ativo(form.get("codigo_ativo"), uid, b.por_id.get(uid))
    return {"titulo": titulo, "usina_id": uid, "cod": cod, "equipamento_id": eq, "criticidade": crit, "status": st,
            "inicio": ini, "fim": fim, "descricao": _texto(form.get("descricao"), TEXTO_MAX, "", "A descrição"),
            "chamado": _linha(form.get("chamado"), CHAMADO_MAX, "", "O chamado"), "os": _os(form.get("os"))}


def _mudou(quem: str, quando: datetime | None, o_que: str) -> str:
    hora = f", {quando:%d/%m às %H:%M}" if quando else ""
    return (f"{o_que} mudou depois que você abriu a página ({quem or 'outra pessoa'}{hora}): recarregue para ver como "
            "ficou e refaça a sua mudança")


def _evento(cofre, evento: str, quem: dict, oid: str, usina_id: int, dados: dict, eid: str | None = None,
            **cols) -> dict:
    agora = datetime.now(timezone.utc)
    linha = {c: None for c in CAB}
    linha.update(id=eid or novo_id("e"),
                 registrado_em=agora.strftime("%Y-%m-%dT%H:%M:%S.") + f"{agora.microsecond // 1000:03d}Z",
                 data_id=int(agora.astimezone(_BRT).strftime("%Y%m%d")), ocorrencia_id=oid, evento=evento,
                 usina_id=usina_id, pessoa_id=quem["pessoa_id"], pessoa_hmac=quem["hmac"], **cols)
    dados = dict(dados, quem={"nome": quem["nome"], "email": quem["email"]})
    linha["dados_cifrados"] = cofre.cifrar(json.dumps(dados, ensure_ascii=False), _ctx(linha))
    return linha


def _evento_ocorrencia(cofre, evento: str, quem: dict, oid: str, c: dict) -> dict:
    return _evento(cofre, evento, quem, oid, c["usina_id"],
                   {"titulo": c["titulo"], "descricao": c["descricao"], "chamado": c["chamado"]},
                   usina_ligada_por="tela", codigo_ativo=c["cod"] or None, equipamento_id=c["equipamento_id"],
                   equipamento_ligado_por="codigo_ativo" if c["equipamento_id"] else None, criticidade=c["criticidade"],
                   status=c["status"], data_id_inicio=_id_dia(c["inicio"]), data_id_fim=_id_dia(c["fim"]),
                   os=c["os"] or None)


def _reler() -> list[dict]:
    """O livro relido do banco agora, sem a cópia: gravar sobre uma leitura velha apagaria o que outra pessoa gravou. A
    leitura que falha sobe (não grava); a listagem que omitiu o livro a trava do `livros.publicar` recusa."""
    return livros.ler(*_banco(), LIVRO, ABA)


def _publicar(eventos: list[dict]) -> None:
    """Grava o livro inteiro e deixa a cópia já com ele (quem gravou se vê na hora). O erro depois do envio pode ter
    gravado: a cópia é zerada, e a próxima leitura vai ao banco."""
    base, sessao = _banco()
    try:
        livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), [[e.get(c) for c in CAB] for e in eventos])},
                        base=base, token=current_app.config["GRIDCO_SQL_TOKEN"], sessao=sessao)
    except Exception:
        limpar()
        raise
    limpar()
    _CACHE["livro"] = {"eventos": [dict(e) for e in eventos], "lido_em": time.time(), "erro": ""}


def _da_ocorrencia(lido: list[dict], oid, cofre=None) -> dict:
    o = estado(lido, cofre).get(_txt(oid))
    if not o:
        raise Recusada("Não achei esta ocorrência: recarregue a página")
    return o


def criar(form: dict, usuario, pode: bool, hoje: date | None = None) -> dict:
    """Uma ocorrência nova (evento `criou`). Devolve a linha gravada (o `ocorrencia_id` leva à página dela). O `novo_id`
    do formulário vira o id dela: o 2º envio do mesmo formulário acha a ocorrência no livro e não grava outra."""
    quem = _quem(usuario, pode)
    hoje = hoje or datetime.now(_BRT).date()
    cofre = _cofre()
    from . import visao
    c = _campos(form, hoje, visao._Base())
    oid = _id_do_form(form.get("novo_id"), "o") or novo_id("o")
    with _TRAVA:
        lido = _reler()
        ja = next((l for l in lido if _txt(l.get("ocorrencia_id")) == oid and _txt(l.get("evento")) == "criou"), None)
        if ja:
            return ja
        nova = _evento_ocorrencia(cofre, "criou", quem, oid, c)
        _publicar(lido + [nova])
    return nova


_COMPARA = ("titulo", "usina_id", "cod", "criticidade", "status", "inicio", "fim", "descricao", "chamado", "os")


def editar(oid: str, form: dict, usuario, pode: bool, hoje: date | None = None) -> dict:
    """A ocorrência mudada (evento `dados`, com todos os campos como ficaram). Nada mudou = recusa (não grava à toa); a
    `versao` do formulário que não é mais a da ocorrência = recusa (a página velha desfaria a mudança de outra pessoa)."""
    quem = _quem(usuario, pode)
    hoje = hoje or datetime.now(_BRT).date()
    cofre = _cofre()
    from . import visao
    b = visao._Base()
    c = _campos(form, hoje, b, checar_usina=False)
    versao = _txt(form.get("versao"))
    with _TRAVA:
        lido = _reler()
        o = _da_ocorrencia(lido, oid, cofre)
        if c["usina_id"] != o["usina_id"] and c["usina_id"] not in b.mobilizadas:
            raise Recusada("Esta usina não está mobilizada no cadastro")
        if all(c[k] == o.get(k) for k in _COMPARA):
            raise Recusada("Nada mudou: a ocorrência já está assim")
        if versao and versao != o["versao"]:
            raise Recusada(_mudou(o["versao_por"], o["versao_em"], "Esta ocorrência"))
        nova = _evento_ocorrencia(cofre, "dados", quem, o["id"], c)
        _publicar(lido + [nova])
    return nova


def salvar_acao(oid: str, form: dict, usuario, pode: bool, pessoas: list[dict], hoje: date | None = None) -> dict:
    """Uma ação do plano, nova (`acao_id` vazio; o `nova_acao_id` do formulário vira o id dela) ou mudada (com a `versao`
    do formulário), inteira como ficou. O responsável é uma pessoa da lista do cadastro (`pessoas`, de
    `pessoas_do_cadastro`): fica o `pessoa_id`, e o nome vai cifrado. Quem saiu da lista continua responsável da ação
    dele (fechar a ação não obriga a trocar a pessoa)."""
    quem = _quem(usuario, pode)
    hoje = hoje or datetime.now(_BRT).date()
    texto = _texto(form.get("texto"), ACAO_MAX, "Escreva a ação", "A ação")
    pid = D._id(form.get("responsavel_id"))
    if not pid:
        raise Recusada("Escolha o responsável da ação na lista")
    situacao = _txt(form.get("situacao"))
    if situacao not in SITUACOES:
        raise Recusada("Escolha a situação da ação")
    teto = hoje + timedelta(days=365 * PRAZO_ANOS)
    prazo = _data(form.get("prazo"), "prazo", PISO, teto, f"O prazo passou de {PRAZO_ANOS} anos")
    if not prazo:
        raise Recusada("Escolha o prazo da ação")
    cofre = _cofre()
    resp = next((p for p in pessoas or [] if p.get("id") == pid), None)
    versao = _txt(form.get("versao"))
    with _TRAVA:
        lido = _reler()
        o = _da_ocorrencia(lido, oid, cofre)
        aid = _txt(form.get("acao_id"))
        if aid:
            a = next((x for x in o["acoes"] if x["id"] == aid), None)
            if not a:
                raise Recusada("Não achei esta ação: recarregue a página")
            if not resp and pid == a["responsavel_id"]:
                resp = {"id": pid, "nome": a["responsavel"]}
            if not resp:
                raise Recusada("Escolha o responsável da ação na lista")
            if (a["texto"], a["responsavel_id"], a["prazo"], a["situacao"]) == (texto, pid, prazo, situacao):
                raise Recusada("Nada mudou: a ação já está assim")
            if versao and versao != a["versao"]:
                raise Recusada(_mudou(a["alterada_por"], a["alterada_em"], "Esta ação"))
        else:
            if not resp:
                raise Recusada("Escolha o responsável da ação na lista")
            aid = _id_do_form(form.get("nova_acao_id"), "a") or novo_id("a")
            if any(x["id"] == aid for x in o["acoes"]):
                return {"ocorrencia_id": o["id"], "acao_id": aid, "ja_gravada": True}
        nova = _evento(cofre, "acao", quem, o["id"], o["usina_id"], {"texto": texto, "responsavel": resp["nome"]},
                       usina_ligada_por="ocorrencia", acao_id=aid, responsavel_pessoa_id=pid, situacao=situacao,
                       data_id_prazo=_id_dia(prazo))
        _publicar(lido + [nova])
    return nova


def registrar_andamento(oid: str, texto: str, usuario, pode: bool, evento_id: str | None = None) -> dict:
    """Uma linha do histórico, com o dia e a hora de agora e quem escreveu; nunca se edita nem se apaga. O `evento_id` do
    formulário vira o id dela: o 2º envio não grava outra."""
    quem = _quem(usuario, pode)
    texto = _texto(texto, TEXTO_MAX, "Escreva o andamento antes de salvar", "O andamento")
    cofre = _cofre()
    eid = _id_do_form(evento_id, "e")
    with _TRAVA:
        lido = _reler()
        o = _da_ocorrencia(lido, oid)
        if eid and any(_txt(l.get("id")) == eid for l in lido):
            return {"ocorrencia_id": o["id"], "id": eid, "ja_gravada": True}
        nova = _evento(cofre, "andamento", quem, o["id"], o["usina_id"], {"texto": texto}, eid=eid,
                       usina_ligada_por="ocorrencia")
        _publicar(lido + [nova])
    return nova


def pessoas_do_cadastro() -> list[dict]:
    """[{"id", "nome"}]: as pessoas do cadastro com nome (o "Nome padrão", decifrado), fora as desligadas e as excluídas,
    em ordem de nome: a lista do responsável da ação. Sem a chave do cadastro, vazia (a tela diz)."""
    from . import visao
    b = visao._Base()
    ids = {D._id(p.get("pessoa_id")) for p in b.pessoas
           if D._id(p.get("pessoa_id")) and p.get("sensivel_cifrado")
           and str(p.get("excluido") or "").strip().lower() != "sim"
           and str(p.get("status") or "").strip().lower() != "desligado"}
    nomes = b.nomes(ids)
    return sorted(({"id": i, "nome": nomes[i]} for i in ids if nomes.get(i)),
                  key=lambda p: (visao._norm_nome(p["nome"]), p["id"]))
