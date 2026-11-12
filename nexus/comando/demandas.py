"""As demandas entre setores (12/11/2026, Levi: "os setores consigam conversar entre si sem ter que especificamente criar
um OS"): a gravação e a leitura do livro `nexus_demandas`. A regra (prazo, situação, avisos) mora em `demandas_regras.py`;
o desenho aprovado, em docs/superpowers/specs/2026-11-12-demandas-entre-setores-design.md.

O Nexus é a FONTE. Quatro abas, todas só acrescentam (registradas no catálogo antes da 1ª gravação, regra 10):
- `dim_tema`: 1 versão de 1 tema de 1 setor (vale a última por `tema_id`): o setor, o prazo em dias úteis, se está em uso;
- `fato_demanda`: 1 demanda aberta: quem pediu e quem recebe por código, o setor de cada um, o tema, o prazo do tema na
  hora e a OS (o número);
- `fato_demanda_usina`: 1 usina de 1 demanda;
- `fato_evento_demanda`: 1 passo de 1 demanda (em análise, pediu informação, informou, respondeu, devolveu, concluiu).

O banco tem leitura aberta: em claro só IDs, códigos e números; o nome do tema, o título, a descrição, os nomes das
pessoas, os textos dos passos e os nomes dos anexos vão cifrados (o Cofre, a chave do cadastro), cada um amarrado à
linha dele. Os anexos ficam no disco do servidor (a pasta de dados do Nexus, `demandas/<id>/`), com nome neutro, pela
regra das Sugestões. As abas vão juntas a cada gravação, sobre o livro relido do banco, uma gravação por vez.
"""
import json
import re
import shutil
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from flask import current_app

from ..dados import livros
from ..dados.conexao import banco as _banco
from . import demandas_regras as R

LIVRO, NOME_LIVRO = "nexus_demandas", "Nexus · demandas entre setores"
ABA_TEMA, ABA_DEMANDA, ABA_USINA, ABA_EVENTO = "dim_tema", "fato_demanda", "fato_demanda_usina", "fato_evento_demanda"
CAB_TEMA = ("id", "tema_id", "registrado_em", "data_id", "setor_id", "prazo_dias_uteis", "ativo", "pessoa_id",
            "pessoa_hmac", "dados_cifrados")
CAB_DEMANDA = ("demanda_id", "registrado_em", "data_id_criacao", "de_hmac", "de_pessoa_id", "de_setor_id", "para_hmac",
               "para_pessoa_id", "para_setor_id", "tema_id", "prazo_dias_uteis", "os", "dados_cifrados")
CAB_USINA = ("id", "demanda_id", "usina_id")
CAB_EVENTO = ("id", "demanda_id", "evento", "registrado_em", "data_id", "pessoa_id", "pessoa_hmac", "dados_cifrados")
ABAS = ((ABA_TEMA, CAB_TEMA), (ABA_DEMANDA, CAB_DEMANDA), (ABA_USINA, CAB_USINA), (ABA_EVENTO, CAB_EVENTO))
# os ids: a letra do que é e 11 hexadecimais (a API do banco infere o tipo da coluna: só algarismos voltaria número)
ID_DEMANDA = re.compile(r"d[0-9a-f]{11}")
ID_EVENTO = re.compile(r"e[0-9a-f]{11}")
ID_TEMA = re.compile(r"m[0-9a-f]{11}")
ID_VERSAO = re.compile(r"v[0-9a-f]{11}")
TEMA_MAX, TITULO_MAX, TEXTO_MAX, PASSO_MAX = 60, 120, 4000, 2000
PRAZO_MIN, PRAZO_MAX = 1, 30
TTL_S = 60
CHAVES = ("NEXUS_CHAVE_CADASTRO", "NEXUS_PESSOA_HMAC", "GRIDCO_SQL_TOKEN")
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}
# quem faz cada passo, e em que situação ele vale (o resto é recusado com o texto da tela)
PASSOS = {
    "em_analise": ("recebe", ("nova", "devolvida")),
    "pediu_informacao": ("recebe", ("nova", "em_analise", "devolvida")),
    "respondeu": ("recebe", ("nova", "em_analise", "devolvida")),
    "informou": ("pediu", ("aguardando",)),
    "concluiu": ("pediu", ("finalizada",)),
    "devolveu": ("pediu", ("finalizada",)),
}
COM_TEXTO = ("pediu_informacao", "respondeu", "informou", "devolveu")
ROTULO_PASSO = {"em_analise": "colocou em análise", "pediu_informacao": "pediu uma informação",
                "informou": "respondeu ao pedido de informação", "respondeu": "respondeu e finalizou",
                "devolveu": "devolveu", "concluiu": "concluiu"}


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê, para a tela mostrar."""


def limpar() -> None:
    _CACHE.clear()


def novo_id(letra: str = "d") -> str:
    return letra + uuid.uuid4().hex[:11]


def faltam_chaves() -> list[str]:
    return [k for k in CHAVES if not current_app.config.get(k)]


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _int(v) -> int | None:
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


def _agora_iso() -> tuple[str, int]:
    agora = datetime.now(timezone.utc)
    return (agora.strftime("%Y-%m-%dT%H:%M:%S.") + f"{agora.microsecond // 1000:03d}Z",
            int(agora.astimezone(_BRT).strftime("%Y%m%d")))


def _cofre():
    chave = current_app.config.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): sem ela o texto não vai cifrado")
    from ..cadastro.cifra import Cofre
    return Cofre(chave)


def _ctx(aba: str, l: dict) -> str:
    """A cifra amarra o texto à linha: mudar a linha no banco perde o texto, em vez de levá-lo para outra."""
    if aba == ABA_TEMA:
        return f"banco/demandas/tema/{_txt(l.get('id'))}/{_txt(l.get('tema_id'))}/{_txt(l.get('setor_id'))}"
    if aba == ABA_DEMANDA:
        return f"banco/demandas/{_txt(l.get('demanda_id'))}/{_txt(l.get('de_hmac'))}/{_txt(l.get('para_hmac'))}"
    return f"banco/demandas/evento/{_txt(l.get('id'))}/{_txt(l.get('demanda_id'))}/{_txt(l.get('evento'))}"


def _decifrar(cofre, aba: str, l: dict) -> dict:
    if not cofre or not l.get("dados_cifrados"):
        return {}
    try:
        return json.loads(cofre.decifrar(l["dados_cifrados"], _ctx(aba, l)))
    except Exception:            # noqa: BLE001 — linha mexida no banco ou chave trocada: fica sem o texto
        return {}


def _quem(usuario) -> dict:
    """Quem está fazendo: o código do e-mail do login (a senha de administrador não diz quem é a pessoa)."""
    email = str((usuario or {}).get("email") or "").strip().lower()
    if not email:
        raise Recusada("Entre com o seu login (Microsoft ou Fracttal): a senha de administrador não diz quem é a pessoa")
    from ..cadastro.ligacao_campo import codigo_da_pessoa
    cfg = current_app.config
    codigo = codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), email)
    if not codigo:
        raise Recusada("Este Nexus não tem a chave do código da pessoa (NEXUS_PESSOA_HMAC)")
    if not cfg.get("GRIDCO_SQL_TOKEN"):
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN)")
    nome = " ".join(str((usuario or {}).get("nome") or "").split()) or email
    pid = None
    try:
        from ..campo import visao
        pid = visao.pessoa_do_login(email, nome)
    except Exception:            # noqa: BLE001 — sem cadastro: fica o código do e-mail (regra 4: não liga = vazio)
        pid = None
    return {"email": email, "nome": nome, "hmac": codigo.lower(), "pessoa_id": pid}


# ── o livro ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def _ler_abas() -> dict:
    base, sessao = _banco()
    a = livros.abas(base, sessao, LIVRO)
    return {aba: (livros._linhas(base, sessao, a[aba]) if a.get(aba) else []) for aba, _cab in ABAS}


def _publicar(tabelas: dict) -> None:
    """As abas juntas (livro que só cresce não grava sem uma aba que o banco tem). A aba ainda vazia só entra depois da
    1ª linha dela."""
    base, sessao = _banco()
    saida = {aba: (list(cab), [[l.get(c) for c in cab] for l in tabelas.get(aba) or []])
             for aba, cab in ABAS if tabelas.get(aba)}
    try:
        livros.publicar(LIVRO, NOME_LIVRO, saida, base=base, token=current_app.config["GRIDCO_SQL_TOKEN"],
                        sessao=sessao)
    finally:
        limpar()


def ler(forcar: bool = False) -> dict:
    """{"temas", "demandas", "usinas", "eventos", "lido_em", "erro"}, guardado por 1 minuto. Leitura que falha devolve a
    última boa com o erro."""
    agora = time.time()
    g = _CACHE.get("livro")
    if g and not forcar and agora - g["lido_em"] < TTL_S:
        return g
    try:
        t = _ler_abas()
    except Exception as ex:      # noqa: BLE001 — banco fora, rede: a tela diz e segue
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        return dict(g, erro=erro) if g else {"temas": [], "demandas": [], "usinas": [], "eventos": [], "lido_em": None,
                                             "erro": erro}
    _CACHE["livro"] = {"temas": t[ABA_TEMA], "demandas": t[ABA_DEMANDA], "usinas": t[ABA_USINA],
                       "eventos": t[ABA_EVENTO], "lido_em": agora, "erro": ""}
    return _CACHE["livro"]


def copia() -> dict | None:
    """Só a cópia guardada, sem esperar o banco (o sininho de toda página): velha, relê por trás; sem cópia (o Nexus
    acabou de subir), começa a leitura por trás e devolve None, e a página abre sem o número. Nos testes, lê na hora."""
    if current_app.config.get("TESTING"):
        return ler()
    g = _CACHE.get("livro")
    if not g or time.time() - g["lido_em"] >= TTL_S:
        from ..auth import setor_telas as ST
        app = current_app._get_current_object()

        def reler():
            with app.app_context():
                ler(forcar=True)
        ST._em_fundo("demandas", reler)
    return g


def avisos_do_sino(meu_hmac: str, meu_setor: int | None, hoje: date | None = None) -> list[dict]:
    """Os avisos do sininho (demandas_regras.avisos) pela cópia: a situação de cada demanda sai dos ids e dos passos, em
    claro; só as que viram aviso são decifradas (o título e quem pediu)."""
    lido = copia()
    if not lido or not (meu_hmac or meu_setor is not None):
        return []
    hoje = hoje or datetime.now(_BRT).date()
    eventos: dict[str, list[dict]] = {}
    for e in lido["eventos"]:
        eventos.setdefault(_txt(e.get("demanda_id")), []).append(e)
    base, por = [], {}
    for l in lido["demandas"]:
        did = _txt(l.get("demanda_id"))
        if not ID_DEMANDA.fullmatch(did):
            continue
        d = {"demanda_id": did, "para_hmac": _txt(l.get("para_hmac")).lower(), "de_hmac": _txt(l.get("de_hmac")).lower(),
             "para_setor_id": _int(l.get("para_setor_id")),
             "estado": R.estado(l, eventos.get(did, []), _int(l.get("prazo_dias_uteis")) or 0, hoje)}
        base.append(d)
        por[did] = l
    av = R.avisos(base, (meu_hmac or "").lower(), meu_setor, hoje)
    try:
        cofre = _cofre()
    except Recusada:
        cofre = None
    for a in av:
        dados = _decifrar(cofre, ABA_DEMANDA, por[a["demanda_id"]])
        a.update(titulo_curto=_txt(dados.get("titulo")), de_nome=_txt(dados.get("de_nome")),
                 para_nome=_txt(dados.get("para_nome")))
    return av


# ── os temas do setor ────────────────────────────────────────────────────────────────────────────────────────────────
def _temas_de(linhas: list[dict], cofre) -> dict[str, dict]:
    """{tema_id: a última versão}, com o nome decifrado."""
    out = {}
    for l in linhas:
        tid = _txt(l.get("tema_id"))
        if not ID_TEMA.fullmatch(tid):
            continue
        out[tid] = {"tema_id": tid, "setor_id": _int(l.get("setor_id")), "prazo_dias_uteis": _int(l.get("prazo_dias_uteis")),
                    "ativo": _txt(l.get("ativo")).lower() in ("1", "sim", "true"),
                    "nome": _txt(_decifrar(cofre, ABA_TEMA, l).get("nome"))}
    return out


def temas(setor_id: int | None = None, so_ativos: bool = True) -> list[dict]:
    try:
        cofre = _cofre()
    except Recusada:
        cofre = None
    ts = [t for t in _temas_de(ler()["temas"], cofre).values()
          if (setor_id is None or t["setor_id"] == setor_id) and (t["ativo"] or not so_ativos)]
    return sorted(ts, key=lambda t: (t["setor_id"] or 0, t["nome"].lower()))


def salvar_tema(setor_id: int, nome: str, prazo_dias_uteis, usuario: dict, tema_id: str | None = None,
                ativo: bool = True) -> dict:
    """Uma versão nova do tema (o novo, a troca do nome ou do prazo, desativar). O nome tem de 1 a 60 caracteres e o
    prazo, de 1 a 30 dias úteis."""
    nome = " ".join(str(nome or "").split())
    if not nome or len(nome) > TEMA_MAX:
        raise Recusada(f"O tema precisa de um nome, até {TEMA_MAX} caracteres")
    prazo = _int(prazo_dias_uteis)
    if prazo is None or not PRAZO_MIN <= prazo <= PRAZO_MAX:
        raise Recusada(f"O prazo é de {PRAZO_MIN} a {PRAZO_MAX} dias úteis")
    if _int(setor_id) is None:
        raise Recusada("Escolha o setor do tema")
    quem = _quem(usuario)
    cofre = _cofre()
    tid = _txt(tema_id)
    with _TRAVA:
        t = _ler_abas()
        if tid and not any(_txt(l.get("tema_id")) == tid for l in t[ABA_TEMA]):
            raise Recusada("Não achei esse tema: recarregue a página")
        if tid:
            atual = _temas_de(t[ABA_TEMA], cofre).get(tid) or {}
            if atual.get("setor_id") != _int(setor_id):
                raise Recusada("Esse tema é de outro setor")
        tid = tid or novo_id("m")
        registrado, data_id = _agora_iso()
        linha = {"id": novo_id("v"), "tema_id": tid, "registrado_em": registrado, "data_id": data_id,
                 "setor_id": _int(setor_id), "prazo_dias_uteis": prazo, "ativo": "sim" if ativo else "não",
                 "pessoa_id": quem["pessoa_id"], "pessoa_hmac": quem["hmac"]}
        linha["dados_cifrados"] = cofre.cifrar(json.dumps({"nome": nome, "quem": quem["nome"]}, ensure_ascii=False),
                                               _ctx(ABA_TEMA, linha))
        t[ABA_TEMA] = t[ABA_TEMA] + [linha]
        _publicar(t)
    return {"tema_id": tid, "nome": nome, "prazo_dias_uteis": prazo, "ativo": ativo, "setor_id": _int(setor_id)}


# ── quem é quem e as OS da usina ─────────────────────────────────────────────────────────────────────────────────────
def pessoas_com_setor() -> list[dict]:
    """[{hmac, nome, setor_id, setor_nome}]: as pessoas do Nexus com setor ativo (as decisões de Base → Acessos → Pessoas
    e setores), com o nome do pessoal do Fracttal. Sem o nome, a pessoa não entra (não há como escolhê-la)."""
    from ..auth import setor_telas as ST
    from ..cadastro import fracttal_pessoal as FP
    from ..cadastro import setores as S
    st = ST._setores_no_clique(*_banco())
    ativos = {s["setor_id"]: s["nome"] for s in S.ativos(st.get("setores") or [])}
    nomes = {p["id"]: p["nome"] for p in (FP.ler_pessoal().get("pessoas") or []) if p.get("id") is not None}
    ultima = {}
    for d in sorted(st.get("decisoes") or [], key=lambda x: x["decidida_em"]):
        ultima[d["fracttal_id"]] = d
    out, vistos = [], set()
    for fid, d in ultima.items():
        h, sid = _txt(d.get("pessoa_hmac")).lower(), d.get("setor_id")
        if not h or sid not in ativos or h in vistos or not nomes.get(fid):
            continue
        vistos.add(h)
        out.append({"hmac": h, "nome": nomes[fid], "setor_id": sid, "setor_nome": ativos[sid]})
    return sorted(out, key=lambda p: p["nome"].lower())


def os_das_usinas(usina_ids) -> list[dict]:
    """As OS do retrato do Fracttal no banco (`nexus_os · fato_tarefa_os`: as abertas e em verificação) das usinas, uma
    por OS: [{os, usina_id, tipo, status}], a mais nova primeiro."""
    from ..campo import visao
    from ..dados import fato_tarefa_os as FT
    alvo = {int(u) for u in usina_ids or [] if _int(u) is not None}
    if not alvo:
        return []
    por = {}
    for t in visao._livro(FT.LIVRO, FT.ABA):
        uid, n = _int(t.get("usina_id")), _int(t.get("os"))
        if uid in alvo and n and n not in por:
            por[n] = {"os": n, "usina_id": uid, "tipo": _txt(t.get("tipo_tarefa")).replace("_", " "),
                      "status": _txt(t.get("status_os"))}
    return sorted(por.values(), key=lambda o: -o["os"])


# ── os anexos (a regra das Sugestões) ────────────────────────────────────────────────────────────────────────────────
def _pasta(did: str) -> Path:
    from ..cadastro.ligacoes import pasta_dados
    if not ID_DEMANDA.fullmatch(did):
        raise Recusada("Demanda inválida")
    return pasta_dados(current_app.config) / "demandas" / did


def _gravar_anexos(did: str, lista: list[dict]) -> list[dict]:
    if not lista:
        return []
    pasta = _pasta(did)
    pasta.mkdir(parents=True, exist_ok=True)
    feitos = []
    for i, a in enumerate(lista, 1):
        destino = pasta / f"{i}{a['ext']}"
        tmp = destino.with_name(destino.name + ".parcial")        # arquivo pela metade nunca aparece na lista
        tmp.write_bytes(a["dados"])
        tmp.replace(destino)
        feitos.append({"n": i, "nome": a["nome"], "arquivo": destino.name, "tamanho": len(a["dados"])})
    return feitos


def arquivo(did: str, n) -> tuple[Path, dict] | None:
    """O anexo `n` da demanda (caminho e o registro decifrado), ou None."""
    d = next((x for x in lista() if x["demanda_id"] == did), None)
    a = next((a for a in (d or {}).get("anexos") or [] if str(a.get("n")) == str(n)), None)
    if not a:
        return None
    caminho = _pasta(did) / _txt(a.get("arquivo"))
    return (caminho, a) if caminho.is_file() else None


# ── abrir e cada passo ───────────────────────────────────────────────────────────────────────────────────────────────
def _texto(v, maximo: int, falta: str, nome: str) -> str:
    t = str(v or "").replace("\r\n", "\n").strip()
    if not t:
        raise Recusada(falta)
    if len(t) > maximo:
        raise Recusada(f"{nome} passou de {maximo} caracteres")
    return t


def abrir(form: dict, arquivos, usuario: dict) -> dict:
    """Uma demanda nova (ver o desenho). O `novo_id` do formulário vira o id: o 2º envio (o duplo clique, o F5) acha a
    demanda no livro e não grava outra. Recusa sem gravar nada: sem pessoa no login, a pessoa sem esse setor, o tema de
    outro setor ou desativado, a OS fora das usinas, o anexo fora do limite."""
    from ..casca import sugestoes as SUG
    quem = _quem(usuario)
    cofre = _cofre()
    para_hmac = _txt(form.get("para_hmac")).lower()
    para_setor = _int(form.get("para_setor_id"))
    pessoas = {p["hmac"]: p for p in pessoas_com_setor()}
    para = pessoas.get(para_hmac)
    if not para:
        raise Recusada("Escolha a pessoa da lista: essa pessoa não tem setor no Nexus")
    if para["setor_id"] != para_setor:
        raise Recusada(f"{para['nome']} não é do setor escolhido: {para['nome']} é de {para['setor_nome']}")
    if para_hmac == quem["hmac"]:
        raise Recusada("A demanda é para outra pessoa: escolha quem vai receber")
    tema = next((t for t in temas(para_setor) if t["tema_id"] == _txt(form.get("tema_id"))), None)
    if not tema:
        raise Recusada(f"Escolha um dos temas de {para['setor_nome']}")
    titulo = " ".join(_texto(form.get("titulo"), TITULO_MAX, "Escreva um título", "O título").split())
    descricao = _texto(form.get("descricao"), TEXTO_MAX, "Escreva a descrição", "A descrição")
    usinas = sorted({u for u in (_int(x) for x in (form.get("usinas") or [])) if u})
    os_n = _int(form.get("os"))
    if os_n and os_n not in {o["os"] for o in os_das_usinas(usinas)}:
        raise Recusada(f"A OS {os_n} não é de nenhuma das usinas escolhidas: escolha uma OS da lista")
    try:
        lista_anexos = SUG.anexos(arquivos or [])
    except SUG.Recusada as ex:
        raise Recusada(str(ex)) from None
    did = _txt(form.get("novo_id"))
    did = did if ID_DEMANDA.fullmatch(did) else novo_id("d")
    meu = pessoas.get(quem["hmac"])
    with _TRAVA:
        t = _ler_abas()
        ja = next((l for l in t[ABA_DEMANDA] if _txt(l.get("demanda_id")) == did), None)
        if ja:
            return ja
        registrado, data_id = _agora_iso()
        linha = {"demanda_id": did, "registrado_em": registrado, "data_id_criacao": data_id, "de_hmac": quem["hmac"],
                 "de_pessoa_id": quem["pessoa_id"], "de_setor_id": meu["setor_id"] if meu else None,
                 "para_hmac": para_hmac, "para_pessoa_id": None, "para_setor_id": para_setor,
                 "tema_id": tema["tema_id"], "prazo_dias_uteis": tema["prazo_dias_uteis"], "os": os_n}
        feitos = _gravar_anexos(did, lista_anexos)
        dados = {"titulo": titulo, "descricao": descricao, "de_nome": quem["nome"], "para_nome": para["nome"],
                 "anexos": feitos}
        linha["dados_cifrados"] = cofre.cifrar(json.dumps(dados, ensure_ascii=False), _ctx(ABA_DEMANDA, linha))
        t[ABA_DEMANDA] = t[ABA_DEMANDA] + [linha]
        t[ABA_USINA] = t[ABA_USINA] + [{"id": f"{did}-{u}", "demanda_id": did, "usina_id": u} for u in usinas]
        try:
            _publicar(t)
        except Exception:
            if feitos:
                shutil.rmtree(_pasta(did), ignore_errors=True)
            raise
    return linha


def registrar(demanda_id: str, evento: str, texto: str, usuario: dict, novo_id_: str | None = None) -> dict:
    """Um passo da demanda, no papel e na vez certos (`PASSOS`); o texto é obrigatório no pedir informação, no informar,
    no responder e no devolver (a justificativa). O `novo_id` do formulário torna o 2º envio inofensivo."""
    did, evento = _txt(demanda_id), _txt(evento)
    if not ID_DEMANDA.fullmatch(did):
        raise Recusada("Não achei esta demanda: recarregue a página")
    if evento not in PASSOS:
        raise Recusada("Esse passo não existe")
    quem = _quem(usuario)
    cofre = _cofre()
    papel, vale_em = PASSOS[evento]
    texto = _texto(texto, PASSO_MAX, "Escreva a justificativa" if evento == "devolveu" else "Escreva o texto",
                   "O texto") if evento in COM_TEXTO else ""
    eid = _txt(novo_id_)
    eid = eid if ID_EVENTO.fullmatch(eid) else novo_id("e")
    with _TRAVA:
        t = _ler_abas()
        d = next((l for l in t[ABA_DEMANDA] if _txt(l.get("demanda_id")) == did), None)
        if not d:
            raise Recusada("Não achei esta demanda: recarregue a página")
        if any(_txt(l.get("id")) == eid for l in t[ABA_EVENTO]):
            return {}
        dono = _txt(d.get("para_hmac")) if papel == "recebe" else _txt(d.get("de_hmac"))
        if dono.lower() != quem["hmac"]:
            raise Recusada("Esse passo é de quem recebeu a demanda" if papel == "recebe"
                           else "Esse passo é de quem pediu a demanda")
        evs = [e for e in t[ABA_EVENTO] if _txt(e.get("demanda_id")) == did]
        sit = R.estado(d, evs, _int(d.get("prazo_dias_uteis")) or 0, datetime.now(_BRT).date())["situacao"]
        if sit not in vale_em:
            raise Recusada(f"A demanda está {R.SITUACOES[sit][0].lower()}: esse passo não vale agora")
        registrado, data_id = _agora_iso()
        linha = {"id": eid, "demanda_id": did, "evento": evento, "registrado_em": registrado, "data_id": data_id,
                 "pessoa_id": quem["pessoa_id"], "pessoa_hmac": quem["hmac"]}
        linha["dados_cifrados"] = cofre.cifrar(json.dumps({"texto": texto, "nome": quem["nome"]}, ensure_ascii=False),
                                               _ctx(ABA_EVENTO, linha))
        t[ABA_EVENTO] = t[ABA_EVENTO] + [linha]
        _publicar(t)
    return linha


# ── a lista para a Caixa ─────────────────────────────────────────────────────────────────────────────────────────────
def _quando(iso) -> datetime | None:
    try:
        t = datetime.fromisoformat(_txt(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(_BRT)


def _inicio(texto: str, n: int = 6) -> str:
    p = texto.split()
    return " ".join(p[:n]) + ("…" if len(p) > n else "")


def lista(hoje: date | None = None) -> list[dict]:
    """As demandas decifradas, com o estado de agora e o selo do prazo. As abertas pelo prazo mais perto primeiro; depois
    as fechadas, da mais nova para a mais velha."""
    hoje = hoje or datetime.now(_BRT).date()
    try:
        cofre = _cofre()
    except Recusada:
        cofre = None
    lido = ler()
    temas_ = _temas_de(lido["temas"], cofre)
    try:
        from ..auth import setor_telas as ST
        st = ST._setores_no_clique(*_banco())
        nome_setor = {s["setor_id"]: s["nome"] for s in st.get("setores") or []}
    except Exception:            # noqa: BLE001 — sem os setores, a linha sai sem o nome do setor
        nome_setor = {}
    usinas_de: dict[str, list[int]] = {}
    for u in lido["usinas"]:
        uid = _int(u.get("usina_id"))
        if uid:
            usinas_de.setdefault(_txt(u.get("demanda_id")), []).append(uid)
    try:
        from ..campo import visao
        nomes_usina = {uid: f.get("nome") or "" for uid, f in visao._Base().por_id.items()}
    except Exception:            # noqa: BLE001
        nomes_usina = {}
    eventos: dict[str, list[dict]] = {}
    for e in lido["eventos"]:
        eventos.setdefault(_txt(e.get("demanda_id")), []).append(e)
    out = []
    for l in lido["demandas"]:
        did = _txt(l.get("demanda_id"))
        if not ID_DEMANDA.fullmatch(did):
            continue
        dados = _decifrar(cofre, ABA_DEMANDA, l)
        evs = eventos.get(did, [])
        tema = temas_.get(_txt(l.get("tema_id"))) or {}
        e = R.estado(l, evs, _int(l.get("prazo_dias_uteis")) or 0, hoje)
        passos = []
        for ev in evs:
            dd = _decifrar(cofre, ABA_EVENTO, ev)
            q = _quando(ev.get("registrado_em"))
            passos.append({"evento": _txt(ev.get("evento")), "rotulo": ROTULO_PASSO.get(_txt(ev.get("evento")), ""),
                           "quando_txt": q.strftime("%d/%m %H:%M") if q else "", "nome": _txt(dd.get("nome")),
                           "texto": _txt(dd.get("texto"))})
        q = _quando(l.get("registrado_em"))
        descricao = _txt(dados.get("descricao"))
        out.append({
            "demanda_id": did, "de_hmac": _txt(l.get("de_hmac")).lower(), "de_nome": _txt(dados.get("de_nome")),
            "de_setor_id": _int(l.get("de_setor_id")), "de_setor_nome": nome_setor.get(_int(l.get("de_setor_id")), ""),
            "para_hmac": _txt(l.get("para_hmac")).lower(), "para_nome": _txt(dados.get("para_nome")),
            "para_setor_id": _int(l.get("para_setor_id")),
            "para_setor_nome": nome_setor.get(_int(l.get("para_setor_id")), ""),
            "tema_id": _txt(l.get("tema_id")), "tema_nome": tema.get("nome") or "",
            "titulo": _txt(dados.get("titulo")), "descricao": descricao, "inicio": _inicio(descricao),
            "usinas": [(u, nomes_usina.get(u, f"usina {u}")) for u in sorted(usinas_de.get(did, []))],
            "os": _int(l.get("os")), "anexos": dados.get("anexos") or [], "legivel": bool(dados),
            "aberta_txt": q.strftime("%d/%m %H:%M") if q else "", "registrado_em": _txt(l.get("registrado_em")),
            "passos": passos, "estado": e, "selo": R.selo_do_prazo(e)})
    abertas = sorted((d for d in out if d["estado"]["aberta"]),
                     key=lambda d: (d["estado"]["prazo"] or date.max, d["registrado_em"]))
    fechadas = sorted((d for d in out if not d["estado"]["aberta"]), key=lambda d: d["registrado_em"], reverse=True)
    return abertas + fechadas


def da_aba(lst: list[dict], aba: str, meu_hmac: str, meu_setor: int | None) -> list[dict]:
    meu_hmac = (meu_hmac or "").lower()
    if aba == "pedi":
        return [d for d in lst if meu_hmac and d["de_hmac"] == meu_hmac]
    if aba == "setor":
        return [d for d in lst if meu_setor is not None and d["para_setor_id"] == meu_setor]
    return [d for d in lst if meu_hmac and d["para_hmac"] == meu_hmac]


FILTROS = (("abertas", "Abertas"), ("vencem", "Vencem até amanhã"), ("vencidas", "Vencidas"),
           ("finalizadas", "Finalizadas"), ("concluidas", "Concluídas"))


def _passa(d: dict, filtro: str) -> bool:
    e = d["estado"]
    if filtro == "vencem":
        return e["aberta"] and e["dias_restantes"] is not None and 0 <= e["dias_restantes"] <= 1 and not e["vencida"]
    if filtro == "vencidas":
        return e["vencida"]
    if filtro == "finalizadas":
        return e["situacao"] == "finalizada"
    if filtro == "concluidas":
        return e["situacao"] == "concluida"
    return e["aberta"]


def filtrar(lst: list[dict], filtro: str, pessoa: str = "", tema: str = "") -> list[dict]:
    filtro = filtro if filtro in dict(FILTROS) else "abertas"
    return [d for d in lst if _passa(d, filtro) and (not pessoa or d["para_hmac"] == pessoa.lower())
            and (not tema or d["tema_id"] == tema)]


def contas(lst: list[dict]) -> dict:
    return {k: sum(1 for d in lst if _passa(d, k)) for k, _ in FILTROS}


def filtros_da(d: dict) -> list[str]:
    """Os filtros da faixa em que a demanda aparece (a tela esconde e mostra a linha sem recarregar)."""
    return [k for k, _ in FILTROS if _passa(d, k)]
