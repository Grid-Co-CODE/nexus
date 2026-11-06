"""Base → Acessos, aba Administradores do App de Campo (05/11/2026): quem administra o App de Campo, escolhido no Nexus.

Levi, 05/11/2026: "os administradores do App de Campo e os técnicos por usina têm de ser escolhidos no Nexus". O dado e as
regras moram em `nexus/pcm/admins_app.py` (o livro `nexus_acessos_app_campo`, que o App lê de 5 em 5 minutos); aqui ficam
as contas da aba e o pôr e o tirar. A página e o POST são os de Base → Acessos (`telas_acessos.py`): só o administrador do
Nexus vê e grava, e o POST confere o código do formulário e a origem.

- **Quem dá para escolher** (2ª volta de 05/11/2026, Levi, olhando a aba no ar: "Só tá aparecendo os técnicos, tem que
  aparecer todos do pessoas e setores!"; a maioria dos administradores do App é do escritório, sem ficha): a união das
  fichas do cadastro não desligadas nem excluídas com as pessoas de Base → Acessos → Pessoas e setores (o pessoal do
  Fracttal, pela cópia que aquela aba guarda: esta aba nunca lê o Fracttal na hora, pede a leitura nova por trás). Cada
  usuário do Fracttal vale pela ligação de HOJE (a última decisão de cada `fracttal_id` no `nexus_setores`): o código, a
  ficha e o setor dela. Sem ligação, só o palpite da aba pelo e-mail junta o usuário à ficha; o palpite pelo nome não (2ª
  revisão de 05/11/2026: o analista do escritório com o primeiro e último nome de um técnico seria a ficha do técnico, e o
  Pôr faria o técnico administrador), e quem fica sem ficha vai com o código do e-mail do Fracttal (a mesma conta que a
  ligação gravaria). A mesma pessoa aparece uma vez: pela ficha para onde a ligação (ou o e-mail) aponta, ou pelo código
  (o mesmo e-mail é a mesma pessoa para o App). O nome é o da ficha; sem ficha, o de Pessoas e setores. Cada uma com o
  setor, ou "ficha de campo", e a busca da página vale para o nome e o setor.
- **Quem fica na lista sem rádio**, com o porquê (2ª revisão de 05/11/2026; o POST recusa também): a ligação ou o palpite
  que aponta para uma ficha desligada ou excluída (e, da ligação, o aviso de refazê-la); o usuário do Fracttal sem nome
  (sem a cópia do Fracttal, as ligações de hoje vêm pelo número do usuário, e nunca se dá acesso a quem não se confere);
  e, sem a chave do cadastro, quem não tem ficha (a ficha e a conta com o mesmo e-mail apareceriam duas vezes). Sem o
  livro dos setores, o Pôr trava inteiro (o código das fichas ligadas sairia errado).
- **Os marcadores** (só avisam; a pessoa segue escolhível): o e-mail de outro domínio, comparado exato com o do avulso
  (Levi, 05/11/2026: "Deixar aparecer"; o administrador do App entra pela conta Microsoft da Grid, e outro domínio nunca
  casa), e a conta do Fracttal desativada (o login do App é pela Microsoft).
- **O código da pessoa** (por onde o App a acha): o da ficha é o do `responsaveis.conta_dos_codigos` (o do usuário do
  Fracttal ligado, a ligação de hoje, e, sem ele, o do e-mail da ficha). Sem código, ou com o código que cai em duas fichas
  (também quando ele chega sem ficha, por Pessoas e setores ou pelo avulso), a pessoa não vira administrador (409, com o
  porquê); nem com o código que já vale na lista por outra ficha (o usuário do Fracttal religado leva o código junto).
- **O avulso** (Levi: "tem que ter como fazer avulso também so digitando o e-mail"): o e-mail digitado, só @gridco.com.br
  (`admins_app.email_do_avulso`), com o código do `codigo_da_pessoa`, o mesmo do App. O código que é de alguém da lista
  leva a linha para essa pessoa (o `pessoa_id` quando ela tem ficha), sem o e-mail, e o de quem está sem rádio recusa com
  o porquê; o de ninguém vai sem ficha, com o e-mail só cifrado, e a tela o mostra decifrado, "avulso (sem ficha)".
- **Quem decidiu** sai do código do e-mail do login: pela pessoa da lista que o tem ou pelo e-mail que este Nexus conhece
  (os administradores e quem entrou em 30 dias). Vazio = a senha de administrador.
- **O nome sai antes da gravação** no Pôr e no Tirar (revisão de 05/11/2026): um erro na leitura do cadastro depois de
  gravar viraria "nada mudou" com a linha já no livro.
"""
import json
import unicodedata
from types import SimpleNamespace

from ..dados import fatos as D
from ..pcm import admins_app as AA
from ..pcm import atribuicoes as A

SEM_HMAC = ("Este Nexus não tem a NEXUS_PESSOA_HMAC: a linha iria sem assinatura e o App não a aplicaria. Nada foi "
            "gravado.")
# a pessoa de Pessoas e setores, sem ficha, cujo usuário do Fracttal não tem e-mail (nem ligação com código)
SEM_CODIGO_FRACTTAL = "sem e-mail no usuário do Fracttal: o App não a reconheceria; corrija o cadastro do Fracttal antes"
FICHA_DE_CAMPO, SEM_SETOR, AVULSO = "ficha de campo", "sem setor", "avulso (sem ficha)"
# quem fica na lista sem rádio, e por quê (2ª revisão de 05/11/2026)
FICHA_FORA = "a ficha está desligada ou excluída no cadastro"
LIGACAO_FORA = "a ligação em Pessoas e setores aponta para uma ficha desligada: refaça a ligação"
SEM_NOME = "o Fracttal não respondeu: sem o nome, não dá para conferir quem é"
# sem a cópia porque a 1ª leitura ainda vem vindo (todo deploy começa assim; 3ª revisão de 05/11/2026: a 1ª tela do Levi
# depois do push dizia que o Fracttal não respondeu, sem o Fracttal ter falhado)
CHEGANDO = "a leitura do Fracttal ainda está chegando: recarregue a página em alguns segundos"
SEM_CHAVE = "sem a chave do cadastro, o Nexus não confere se ela já tem ficha"
# os marcadores, que só avisam
OUTRO_DOMINIO = "outro domínio: o App não o reconhece como administrador"
CONTA_INATIVA = "conta do Fracttal desativada"
NOME_DE_DESLIGADA = "o nome bate com uma ficha desligada: confira se é a mesma pessoa"
TEM_FICHA_AGORA = "esta pessoa tem ficha agora: tire e ponha de novo para ligar à ficha"


class SemCadastro(Exception):
    """O cadastro de pessoas do banco não foi lido: a aba mostra o que já está no livro, e o Pôr fica travado."""


def _cadastro_vazio() -> dict:
    return {"fichas": {}, "codigos": {}, "ambiguos": {}, "cod_ambiguo": {}, "dominios": {}}


def _dominio(email) -> str:
    e = str(email or "").strip().lower()
    return e.rsplit("@", 1)[1] if "@" in e else ""


def _cadastro(cfg) -> dict:
    """{"fichas": {pessoa_id: {"nome", "cargo", "vinculo", "ativa"}}, "codigos": {pessoa_id: código},
    "ambiguos": {pessoa_id: por que ficou sem}, "cod_ambiguo": {código: por que}, "dominios": {código: domínio do e-mail}}
    do cadastro de pessoas do banco, decifrado uma vez. O `cod_ambiguo` é o código que saiu de duas fichas: quem chega com
    ele sem ficha (Pessoas e setores, o avulso) também não entra. O `dominios` só guarda o domínio (o marcador de outro
    domínio), nunca o e-mail. Sem a chave do cadastro, os nomes pelo número (e só os códigos de Pessoas e setores)."""
    from ..campo import visao
    from ..campo.ligacao_cadastro import codigo_da_pessoa
    from ..pcm import responsaveis as RP
    try:
        linhas = visao._livro("cadastro_nexus", "pessoas")
    except Exception as ex:      # noqa: BLE001 — banco fora, ou o teste sem banco
        raise SemCadastro(type(ex).__name__) from ex
    chave, chave_hmac = cfg.get("NEXUS_CHAVE_CADASTRO"), cfg.get("NEXUS_PESSOA_HMAC")
    cofre = None
    if chave:
        from ..cadastro.cifra import Cofre
        cofre = Cofre(chave)
    fichas, dominios = {}, {}
    for p in linhas:
        pid = D._id(p.get("pessoa_id"))
        if not pid:
            continue
        nome = ""
        if cofre and p.get("sensivel_cifrado"):
            try:
                s = json.loads(cofre.decifrar(p["sensivel_cifrado"], f"banco/pessoas/{pid}"))
                nome = visao.nome_curto(s.get("nome_padrao") or s.get("nome"))
                if c := codigo_da_pessoa(chave_hmac, s.get("email")):
                    dominios[c] = _dominio(s.get("email"))
            except Exception:    # noqa: BLE001 — cifra de outra chave: pelo número
                pass
        fora = D._txt(p.get("excluido")).lower() == "sim" or D._txt(p.get("status")).lower() == "desligado"
        fichas[pid] = {"pessoa_id": pid, "nome": nome or f"Pessoa {pid}", "cargo": D._txt(p.get("cargo")),
                       "vinculo": D._txt(p.get("vinculo")), "ativa": not fora}
    conta = RP.conta_dos_codigos(cfg, SimpleNamespace(pessoas=linhas))
    por_que = conta["por_que"]
    cod_ambiguo = {conta["antes"][p]: w for p, w in por_que.items() if w == RP.AMBIGUO and conta["antes"].get(p)}
    return {"fichas": fichas, "codigos": conta["codigos"], "ambiguos": por_que, "cod_ambiguo": cod_ambiguo,
            "dominios": dominios}


def _pessoas_e_setores(cfg) -> dict:
    """As pessoas de Base → Acessos → Pessoas e setores: {"pessoas": [{"fracttal_id", "nome", "sem_nome", "chegando",
    "pessoa_id", "codigo", "setor", "por" ("ligacao" | "email" | ""), "nome_de" (a ficha do palpite pelo nome),
    "conta_ativa"}], "dominios", "estado_fracttal", "idade_s", "vencida", "erro_setores"}. O pessoal do Fracttal vem da
    cópia daquela aba, sem nunca ler o Fracttal na hora (`telas_fracttal.copia_sem_esperar`, que pede a leitura nova por
    trás); a ligação de hoje e o setor, do livro `nexus_setores`. Sem a cópia, as ligações de hoje vêm pelo número do
    usuário, sem nome (`chegando` enquanto a 1ª leitura vem vindo). Sem o livro dos setores (nem a cópia dele), ninguém, e
    o `erro_setores` trava o Pôr."""
    from ..cadastro import setores as S
    from ..cadastro import telas_fracttal as TF
    from ..campo import visao
    from ..campo.ligacao_cadastro import codigo_da_pessoa
    out = {"pessoas": [], "dominios": {}, "estado_fracttal": "fora", "idade_s": None, "vencida": False,
           "erro_setores": ""}
    try:
        st = S.ler(visao._base(), visao._sessao())
    except Exception as ex:      # noqa: BLE001 — sem o banco (o teste sem banco): a aba diz
        st = {"setores": [], "decisoes": [], "lido_em": None, "erro": type(ex).__name__}
    if st.get("erro") and not st.get("lido_em"):
        out["erro_setores"] = D._txt(st["erro"])[:160]
        return out
    nome_setor = {s["setor_id"]: s["nome"] for s in st.get("setores") or []}

    def setor(sid) -> str:
        return (nome_setor.get(sid) or f"setor {sid}") if sid else ""
    hoje: dict = {}
    for d in sorted(st.get("decisoes") or [], key=lambda x: x["decidida_em"]):
        hoje[d["fracttal_id"]] = d          # a ligação de hoje de cada usuário do Fracttal
    try:
        copia = TF.copia_sem_esperar()
    except Exception:            # noqa: BLE001 — a cópia do Fracttal fora não tira a aba do ar: o caminho fechado
        copia = {"rel": {"linhas": []}, "idade_s": None, "vencida": False, "estado": "fora"}
    chave = cfg.get("NEXUS_PESSOA_HMAC")
    linhas = copia["rel"].get("linhas") or []
    out["estado_fracttal"] = copia["estado"] if linhas or copia["estado"] != "copia" else "fora"
    out["idade_s"], out["vencida"] = copia["idade_s"], copia["vencida"]
    for x in linhas:
        fid = D._id(x.get("id"))
        if not fid:
            continue
        email_c = codigo_da_pessoa(chave, x.get("email")) or ""
        if email_c:
            out["dominios"][email_c] = _dominio(x.get("email"))
        d = hoje.get(fid)
        if d:
            pid, codigo, sid, por = d.get("pessoa_id"), D._txt(d.get("pessoa_hmac")), d.get("setor_id"), "ligacao"
        elif x.get("ficha") and x.get("por") == "e-mail":
            # sem ligação, só o palpite pelo e-mail junta à ficha (o pelo nome juntava o analista ao técnico homônimo)
            pid, codigo, sid, por = x["ficha"].get("pessoa_id"), email_c, None, "email"
        else:
            # sem ficha: o código do e-mail do Fracttal, a mesma conta que a ligação gravaria (`setores.definir`)
            pid, codigo, sid, por = None, email_c, None, ""
        nome = D._txt(x.get("nome"))
        # o palpite pelo nome (sem ligação nem e-mail que bata) não junta, mas fica anotado: se a ficha estiver
        # desligada, a linha ganha o marcador para conferir (pode ser um homônimo; 3ª revisão de 05/11/2026)
        nome_de = D._id((x.get("ficha") or {}).get("pessoa_id")) if not d and x.get("por") == "nome" else None
        out["pessoas"].append({"fracttal_id": fid, "nome": nome or f"Usuário do Fracttal {fid}", "sem_nome": not nome,
                               "chegando": False, "pessoa_id": D._id(pid), "codigo": codigo, "setor": setor(sid),
                               "por": por, "nome_de": nome_de, "conta_ativa": bool(x.get("conta_ativa"))})
    if not linhas:
        # sem a cópia do Fracttal: quem tem a ligação de hoje segue na lista, pelo número, sem nome (fica sem rádio);
        # "chegando" quando a 1ª leitura ainda vem vindo, e não falhou
        chegando = out["estado_fracttal"] == "chegando"
        for fid, d in sorted(hoje.items(), key=lambda t: t[0]):
            out["pessoas"].append({"fracttal_id": fid, "nome": f"Usuário do Fracttal {fid}", "sem_nome": True,
                                   "chegando": chegando, "pessoa_id": D._id(d.get("pessoa_id")),
                                   "codigo": D._txt(d.get("pessoa_hmac")), "setor": setor(d.get("setor_id")),
                                   "por": "ligacao", "nome_de": None, "conta_ativa": None})
    return out


def _uniao(cad: dict, ps: dict, sem_chave: bool = False) -> list[dict]:
    """Quem a aba mostra para escolher: as fichas ativas e as pessoas de Pessoas e setores, cada pessoa uma vez. A ficha é
    a pessoa quando a ligação (ou o palpite pelo e-mail) aponta para ela; sem ficha ativa, junta pelo código. Quem não se
    pode escolher fica na lista com o `bloqueio` (o porquê), sem rádio. Cada uma: {valor (o do rádio), pessoa_id, codigo,
    nome, setor, rotulo, cargo, vinculo, porque, bloqueio, aviso, tem_codigo, outro_dominio, conta_inativa, nomes,
    fracttal_ids, busca}."""
    fichas, codigos, ambiguos, cod_ambiguo = cad["fichas"], cad["codigos"], cad["ambiguos"], cad["cod_ambiguo"]
    dominios = {**ps.get("dominios", {}), **cad.get("dominios", {})}

    def nova(pid, codigo, nome, *, cargo="", vinculo="", porque="", bloqueio="", aviso="") -> dict:
        return {"pessoa_id": pid, "codigo": codigo, "nome": nome, "setor": "", "cargo": cargo, "vinculo": vinculo,
                "porque": porque, "bloqueio": bloqueio, "aviso": aviso, "nomes": [nome], "fracttal_ids": [], "contas": [],
                "nome_de_desligada": False}
    por_chave: dict = {}
    for pid, f in fichas.items():
        if f["ativa"]:
            por_chave[("ficha", pid)] = nova(pid, codigos.get(pid) or "", f["nome"], cargo=f["cargo"],
                                             vinculo=f["vinculo"], porque=ambiguos.get(pid, ""))
    por_codigo = {p["codigo"]: k for k, p in por_chave.items() if p["codigo"]}
    for u in ps["pessoas"]:
        pid, codigo = u["pessoa_id"], u["codigo"]
        if pid and pid in fichas and not fichas[pid]["ativa"]:
            # a ligação (ou o palpite pelo e-mail) aponta para uma ficha desligada ou excluída: fica na lista, sem rádio,
            # e nunca junta a outra pessoa (o recontratado tem a ficha nova, com o código pelo e-mail)
            k = ("fora", u["fracttal_id"])
            por_chave[k] = nova(None, codigo, u["nome"], bloqueio=FICHA_FORA,
                                aviso=LIGACAO_FORA if u["por"] == "ligacao" else "")
        else:
            k = ("ficha", pid) if pid and ("ficha", pid) in por_chave else por_codigo.get(codigo) if codigo else None
            if k is None:
                # sem ficha ativa: a pessoa pelo código; o código que saiu de duas fichas não volta por aqui (o porquê de
                # lá), e quem não tem nome (sem a cópia do Fracttal) não se confere
                k = ("codigo", codigo) if codigo else ("fracttal", u["fracttal_id"])
                sem_nome = (CHEGANDO if u.get("chegando") else SEM_NOME) if u["sem_nome"] else ""
                por_chave[k] = nova(None, codigo, u["nome"], porque=cod_ambiguo.get(codigo, "") if codigo else "",
                                    bloqueio=sem_nome or (SEM_CHAVE if sem_chave else ""))
                if codigo:
                    por_codigo[codigo] = k
        p = por_chave[k]
        nome_de = u.get("nome_de")
        if nome_de and nome_de in fichas and not fichas[nome_de]["ativa"]:
            p["nome_de_desligada"] = True               # só avisa: pode ser um homônimo
        p["setor"] = p["setor"] or u["setor"]
        if u["nome"] not in p["nomes"]:
            p["nomes"].append(u["nome"])
        p["fracttal_ids"].append(u["fracttal_id"])
        if u["conta_ativa"] is not None:
            p["contas"].append(u["conta_ativa"])
    out = []
    for p in por_chave.values():
        rotulo = p["setor"] or (FICHA_DE_CAMPO if p["pessoa_id"] else SEM_SETOR)
        valor = (str(p["pessoa_id"]) if p["pessoa_id"] else f"codigo:{p['codigo']}" if p["codigo"]
                 else f"fracttal:{p['fracttal_ids'][0]}")
        dominio = dominios.get(p["codigo"]) if p["codigo"] else ""
        out.append(dict(p, rotulo=rotulo, valor=valor, tem_codigo=bool(p["codigo"]) and not p["porque"],
                        # comparado exato com o do avulso: o gridco.com sem o .br também é outro (Levi: "Deixar aparecer")
                        outro_dominio=bool(dominio) and dominio != AA.DOMINIO_AVULSO,
                        conta_inativa=bool(p["contas"]) and not any(p["contas"]),
                        busca=_sem_acento(" ".join((*p["nomes"], rotulo, p["cargo"], p["vinculo"])))))
    out.sort(key=lambda p: (_sem_acento(p["nome"]), p["valor"]))
    return out


def _do_codigo(uniao: list[dict], codigo: str) -> dict | None:
    """A pessoa da lista com este código: a que se pode escolher primeiro (o recontratado tem a ficha nova e a ligação
    velha com o mesmo código); senão a que está sem rádio, para o porquê."""
    achadas = [p for p in uniao if codigo and p["codigo"] == codigo]
    return next((p for p in achadas if not p["bloqueio"]), achadas[0] if achadas else None)


def _emails_conhecidos(cfg) -> dict:
    """{código: e-mail} dos administradores do Nexus e de quem entrou em 30 dias: quem decide aqui é administrador, e o
    do escritório não tem ficha no cadastro (o e-mail só aparece nesta tela, que já é de administrador)."""
    from ..campo.ligacao_cadastro import codigo_da_pessoa
    from . import acessos as AC
    from . import admins_do_servidor
    chave = cfg.get("NEXUS_PESSOA_HMAC")
    if not chave:
        return {}
    emails = set(admins_do_servidor())
    try:
        emails |= {a["email"] for a in AC.estado(cfg)["admins"]} | {x["email"] for x in AC.logins_recentes(cfg)}
    except Exception:            # noqa: BLE001 — a lista da tela fora não tira a aba do ar
        pass
    emails.discard(AC.SENHA_DE_ADMIN)
    return {c: e for e in sorted(emails) if (c := codigo_da_pessoa(chave, e))}


def _dm(d) -> str:
    return f"{str(d)[6:8]}/{str(d)[4:6]}/{str(d)[:4]}" if d else ""


def _sem_acento(s) -> str:
    """Sem acento, sem caixa, espaço único: o que a busca da página compara (o JavaScript tira o acento do digitado)."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def _nome(fichas: dict, pid) -> str:
    return (fichas.get(pid) or {}).get("nome") or (f"Pessoa {pid}" if pid else "")


def _do_avulso(historico: list[dict]) -> dict:
    """{código: o e-mail decifrado do avulso}. Só a linha que o pôs leva o e-mail; a do tirar sai por este mapa."""
    return {h["pessoa_hmac"]: h["email"] for h in historico if h.get("email")}


def _pessoa_da_linha(pid, codigo, fichas, por_pid, por_codigo, avulsos) -> tuple[str, str]:
    """(nome, o que vai ao lado) de uma linha do livro: a ficha pelo ID; sem ficha, o avulso pelo e-mail decifrado, a
    pessoa de Pessoas e setores pelo código ou, fora dela hoje, "pessoa sem ficha"."""
    if pid:
        return _nome(fichas, pid), (por_pid.get(pid) or {}).get("rotulo", "")
    if avulsos.get(codigo):
        return avulsos[codigo], AVULSO
    p = por_codigo.get(codigo)
    if p:
        return p["nome"], p["rotulo"]
    return "pessoa sem ficha", "fora de Pessoas e setores hoje"


def contexto(cfg) -> dict:
    """O que a aba mostra: os administradores do App que valem hoje, quem dá para escolher, o histórico e os avisos.
    Tudo com o prefixo `app_` (a página de Acessos é uma só, com as três abas)."""
    from .acessos import hora_br
    est = AA.ler(cfg)
    hoje = A.hoje_id()
    erro_cadastro = ""
    try:
        cad = _cadastro(cfg)
    except SemCadastro as ex:
        cad, erro_cadastro = _cadastro_vazio(), str(ex) or "erro"
    sem_chave = not cfg.get("NEXUS_CHAVE_CADASTRO")
    ps = _pessoas_e_setores(cfg)
    uniao = _uniao(cad, ps, sem_chave)
    fichas, codigos, ambiguos = cad["fichas"], cad["codigos"], cad["ambiguos"]
    por_pid = {p["pessoa_id"]: p for p in uniao if p["pessoa_id"]}
    # por código, a pessoa que se pode escolher vence a que está sem rádio (o recontratado e a ligação velha)
    por_codigo = {p["codigo"]: p for p in sorted(uniao, key=lambda p: not p["bloqueio"]) if p["codigo"]}
    por_codigo_fichas = {c: pid for pid, c in codigos.items()}
    dominios = {**ps["dominios"], **cad["dominios"]}
    emails = _emails_conhecidos(cfg)
    hist = AA.historico(cfg, est)
    avulsos = _do_avulso(hist)

    def quem(h):
        if not h:
            return "administrador (senha)"
        if h in por_codigo:
            return por_codigo[h]["nome"]
        if h in por_codigo_fichas:
            return _nome(fichas, por_codigo_fichas[h])
        return emails.get(h) or "alguém fora do cadastro"

    def pessoa(pid, codigo):
        return _pessoa_da_linha(pid, codigo, fichas, por_pid, por_codigo, avulsos)

    atuais = AA.atuais(est, hoje)
    # só com a chave do cadastro o Nexus lê o e-mail das fichas e confere o código de cada linha (re-revisão de
    # 05/11/2026, N1: sem ela, toda linha posta pelo e-mail da ficha avisava "tire e ponha de novo", em falso)
    confere = bool(cfg.get("NEXUS_CHAVE_CADASTRO")) and not erro_cadastro
    vigentes = []
    for (codigo, _papel), x in atuais.items():
        pid = A._int_ou_none(x.get("pessoa_id"))
        nome, detalhe = pessoa(pid, codigo)
        hoje_cod = codigos.get(pid) if pid else None
        hoje_p = por_codigo.get(codigo)
        dominio = dominios.get(codigo, "")
        vigentes.append({"pessoa_id": pid, "nome": nome, "detalhe": detalhe, "avulso": detalhe == AVULSO,
                         "pessoa_hmac": codigo, "status": x["status"], "desde": hora_br(x.get("decidida_em")),
                         "de": _dm(A._int_ou_none(x.get("de_data_id"))), "ate": _dm(A._int_ou_none(x.get("ate_data_id"))),
                         "quem": quem(D._txt(x.get("decidida_por_hmac"))),
                         "outro_dominio": bool(dominio) and dominio != AA.DOMINIO_AVULSO,
                         # o código de hoje da ficha é outro (o e-mail mudou), ou ela perdeu o código (o mesmo em duas
                         # fichas, ou o do e-mail dela é o do usuário do Fracttal ligado a outra): o App acha a pessoa
                         # pelo código da linha, o de antes
                         "codigo_mudou": bool(pid) and confere and (bool(hoje_cod) and hoje_cod != codigo
                                                                    or pid in ambiguos),
                         # o inverso do "Nada mudou" (2ª revisão de 05/11/2026): posta sem ficha, a pessoa ganhou ficha
                         # depois; a linha segue sem `pessoa_id` até tirar e pôr de novo
                         "tem_ficha_agora": not pid and bool(hoje_p and hoje_p["pessoa_id"] and not hoje_p["bloqueio"])})
    vigentes.sort(key=lambda v: (_sem_acento(v["nome"]), v["pessoa_hmac"]))
    dono = {c: A._int_ou_none(x.get("pessoa_id")) for (c, _p), x in atuais.items()}
    escolher = []
    for p in uniao:
        c = p["codigo"]
        if c and c in dono and (dono[c] is None or dono[c] == p["pessoa_id"]):
            continue                 # já é administrador do App pelo código (para o App, a mesma pessoa)
        # o código dela já vale na lista por outra ficha (o usuário do Fracttal religado): fica na lista, com o porquê
        escolher.append(dict(p, outra=_nome(fichas, dono[c]) if c and c in dono and not p["bloqueio"] else ""))
    historico = []
    for h in hist:
        nome, detalhe = pessoa(h["pessoa_id"], h["pessoa_hmac"])
        historico.append(dict(h, nome=nome, detalhe=detalhe, avulso=detalhe == AVULSO, quem=quem(h["quem_hmac"]),
                              quando_br=hora_br(h["quando"]), de=_dm(h["de"]), ate=_dm(h["ate"])))
    tem_hmac = bool(str(cfg.get("NEXUS_PESSOA_HMAC") or "").strip())
    grava = bool(AA._arquivo_local(cfg) or cfg.get("GRIDCO_SQL_TOKEN"))
    pode = tem_hmac and grava and not est.get("erro")
    pode_por = pode and not erro_cadastro and not ps["erro_setores"]
    # o aviso do Fracttal: sem cópia, "chegando" (a 1ª leitura vem vindo: todo deploy começa assim) ou "fora" (a leitura
    # falhou: as ligações pelo número, sem rádio); com a cópia vencida, "velha", com a idade da leitura do Fracttal
    idade, estado = ps["idade_s"], ps["estado_fracttal"]
    fracttal = estado if estado in ("chegando", "fora") else "velha" if ps["vencida"] else ""
    return {"app_vigentes": vigentes, "app_escolher": escolher, "app_historico": historico,
            "app_erro": est.get("erro") or "", "app_velha": bool(est.get("velha")), "app_erro_cadastro": erro_cadastro,
            "app_erro_setores": ps["erro_setores"], "app_fracttal": fracttal,
            "app_fracttal_min": int(idade // 60) if idade is not None else 0,
            "app_sem_hmac": not tem_hmac, "app_sem_token": not grava, "app_sem_chave": sem_chave,
            "app_pode_tirar": pode, "app_pode_por": pode_por,
            # o avulso leva o e-mail cifrado: sem a chave do cadastro, o formulário nem aparece
            "app_pode_por_email": pode_por and not sem_chave,
            "app_escolhiveis": sum(1 for p in escolher if not p["bloqueio"]),
            "app_sem_codigo": sum(1 for p in escolher if not p["tem_codigo"] and not p["bloqueio"]),
            "app_sem_radio": sum(1 for p in escolher if p["bloqueio"]),
            # o pessoa_id vazio (sem ficha) conta aqui: a governança do livro (nexus/dados/CLAUDE.md)
            "app_sem_ficha": sum(1 for v in vigentes if not v["pessoa_id"]),
            "app_avulsos": sum(1 for v in vigentes if v["avulso"])}


def _lista_de_agora(cfg) -> tuple[dict, list]:
    """(o cadastro, quem a aba mostra), lidos agora para o Pôr (o Fracttal, só pela cópia). O cadastro ou o livro dos
    setores que não se leram recusam: sem eles, o código da pessoa sairia errado."""
    try:
        cad = _cadastro(cfg)
    except SemCadastro as ex:
        raise AA.Recusada(f"Não consegui ler o cadastro de pessoas no banco ({ex}): nada foi gravado.") from ex
    ps = _pessoas_e_setores(cfg)
    if ps["erro_setores"]:
        raise AA.Recusada(f"Não consegui ler Pessoas e setores no banco ({ps['erro_setores'][:80]}): sem a ligação de "
                          "hoje, o código da pessoa pode sair errado. Nada foi gravado.")
    return cad, _uniao(cad, ps, not cfg.get("NEXUS_CHAVE_CADASTRO"))


def _achar(uniao: list[dict], escolha) -> dict | None:
    """A pessoa do rádio: o número da ficha, `codigo:<código>` (sem ficha) ou `fracttal:<id>` (sem código)."""
    e = D._txt(escolha)
    if e.startswith("codigo:"):
        return _do_codigo(uniao, e[len("codigo:"):])
    if e.startswith("fracttal:"):
        fid = D._id(e[len("fracttal:"):])
        achadas = [p for p in uniao if fid and fid in p["fracttal_ids"]]
        return next((p for p in achadas if not p["bloqueio"]), achadas[0] if achadas else None)
    pid = D._id(e)
    return next((p for p in uniao if pid and p["pessoa_id"] == pid), None)


def _por_pessoa(cfg, cad: dict, p: dict, obs, usuario) -> str:
    """Põe a pessoa da lista (ficha ou não). O texto do aviso, ou `AA.Recusada`."""
    nome = p["nome"]                 # antes da gravação: depois dela, nada pode falhar calado
    if p["bloqueio"]:
        # quem a lista mostra sem rádio também não entra por um POST feito à mão (nem pelo avulso)
        raise AA.Recusada(f"{nome}: {p['bloqueio']}. Nada foi gravado.")
    if p["porque"]:
        raise AA.Recusada(f"{nome}: sem código, porque {p['porque']}: o App acharia outra pessoa; corrija o cadastro "
                          "antes.")
    if not p["codigo"]:
        raise AA.Recusada(f"{nome}: {AA.SEM_CODIGO if p['pessoa_id'] else SEM_CODIGO_FRACTTAL}.")
    est = AA.ler(cfg, forcar=True)
    outra = AA.atuais(est, A.hoje_id()).get((p["codigo"], "admin"))
    outra_pid = A._int_ou_none(outra.get("pessoa_id")) if outra else None
    if outra and outra_pid is not None and outra_pid != p["pessoa_id"]:
        # o código já vale na lista por outra ficha (o usuário do Fracttal religado leva o código junto); o
        # `admins_app.decidir` também recusa, aqui é para dizer quem
        raise AA.Recusada(f"{nome}: o código dela já está na lista de administradores do App com outra ficha "
                          f"({_nome(cad['fichas'], outra_pid)}): tire aquela antes. Nada foi gravado.")
    r = AA.decidir(cfg, pessoa_id=p["pessoa_id"], pessoa_hmac=p["codigo"], ativo=True, usuario=usuario, obs=obs or "")
    if not r["gravou"]:
        return f"Nada mudou: {nome} já é administrador do App de Campo."
    return f"{nome} agora é administrador do App de Campo. O App lê a lista de 5 em 5 minutos."


def por(cfg, escolha, obs, usuario) -> str:
    """Põe a pessoa escolhida na lista (a ficha pelo número; sem ficha, pelo código). O texto do aviso, ou
    `AA.Recusada`."""
    if not str(cfg.get("NEXUS_PESSOA_HMAC") or "").strip():
        raise AA.Recusada(SEM_HMAC)
    cad, uniao = _lista_de_agora(cfg)
    p = _achar(uniao, escolha)
    if p is None:
        raise AA.Recusada("Essa pessoa não está entre as fichas ativas do cadastro (desligada ou excluída) nem em "
                          "Pessoas e setores: atualize a página. Nada foi gravado.")
    return _por_pessoa(cfg, cad, p, obs, usuario)


def por_email(cfg, email, obs, usuario) -> str:
    """O avulso: põe pelo e-mail digitado. O código que é de alguém da lista leva a linha para essa pessoa (a mesma pessoa
    não aparece duas vezes), e o de quem está sem rádio pela ficha desligada ou sem a chave do cadastro recusa com o
    porquê; o de ninguém, ou o de quem só está sem o nome do Fracttal, vai sem ficha, com o e-mail só cifrado (3ª revisão
    de 05/11/2026: o e-mail digitado já diz quem é, e depois de todo deploy a cópia do Fracttal ainda não chegou). O texto
    do aviso, ou `AA.Recusada`."""
    from ..campo.ligacao_cadastro import codigo_da_pessoa
    chave = str(cfg.get("NEXUS_PESSOA_HMAC") or "").strip()
    if not chave:
        raise AA.Recusada(SEM_HMAC)
    email = AA.email_do_avulso(email)            # o formato e o domínio antes de ler o banco
    codigo = codigo_da_pessoa(chave, email)
    cad, uniao = _lista_de_agora(cfg)
    if codigo in cad["cod_ambiguo"]:
        raise AA.Recusada(f"{email}: sem código, porque {cad['cod_ambiguo'][codigo]}: o App acharia outra pessoa; "
                          "corrija o cadastro antes.")
    p = _do_codigo(uniao, codigo)
    if p is not None and p["bloqueio"] not in (SEM_NOME, CHEGANDO):
        return _por_pessoa(cfg, cad, p, obs, usuario)
    est = AA.ler(cfg, forcar=True)
    outra = AA.atuais(est, A.hoje_id()).get((codigo, "admin"))
    outra_pid = A._int_ou_none(outra.get("pessoa_id")) if outra else None
    if outra and outra_pid is not None:
        raise AA.Recusada(f"{email}: o código deste e-mail já está na lista de administradores do App com uma ficha "
                          f"({_nome(cad['fichas'], outra_pid)}): tire aquela antes. Nada foi gravado.")
    r = AA.decidir(cfg, pessoa_id=None, pessoa_hmac=codigo, ativo=True, usuario=usuario, obs=obs or "", email=email)
    if not r["gravou"]:
        return f"Nada mudou: {email} já é administrador do App de Campo."
    return f"{email} agora é administrador do App de Campo (avulso, sem ficha). O App lê a lista de 5 em 5 minutos."


def _nome_para_o_aviso(cfg, est: dict, pid, codigo: str) -> str:
    """O nome de quem a linha tira, lido ANTES da gravação: a ficha; sem ficha, o e-mail do avulso ou o nome de Pessoas
    e setores."""
    if pid:
        try:
            return _nome(_cadastro(cfg)["fichas"], pid)
        except SemCadastro:
            return f"Pessoa {pid}"
    email = _do_avulso(AA.historico(cfg, est)).get(codigo)
    if email:
        return email
    try:
        cad = _cadastro(cfg)
    except SemCadastro:
        cad = _cadastro_vazio()
    p = _do_codigo(_uniao(cad, _pessoas_e_setores(cfg), not cfg.get("NEXUS_CHAVE_CADASTRO")), codigo)
    return p["nome"] if p else "A pessoa sem ficha"


def tirar(cfg, pessoa_hmac, usuario) -> str:
    """Tira dos administradores do App quem vale hoje com este código (o da linha que pôs: é por ele que o App acha),
    com ficha ou sem (o avulso também)."""
    if not str(cfg.get("NEXUS_PESSOA_HMAC") or "").strip():
        raise AA.Recusada(SEM_HMAC)
    est = AA.ler(cfg, forcar=True)
    if est.get("erro"):
        raise AA.Recusada(f"Não consegui ler os administradores do App no banco ({est['erro'][:80]}): nada foi gravado.")
    codigo = D._txt(pessoa_hmac)
    x = AA.atuais(est, A.hoje_id()).get((codigo, "admin")) if codigo else None
    if not x:
        raise AA.Recusada("Essa pessoa já não é administradora do App de Campo (alguém mudou agora): atualize a página.")
    pid = A._int_ou_none(x.get("pessoa_id"))
    nome = _nome_para_o_aviso(cfg, est, pid, codigo)      # o nome antes da gravação (revisão de 05/11/2026)
    AA.decidir(cfg, pessoa_id=pid, pessoa_hmac=codigo, ativo=False, usuario=usuario)
    return f"{nome} deixou de ser administrador do App de Campo. O App lê a lista de 5 em 5 minutos."
