"""Quem recebe, pelo PAPEL no Registro mestre (25/11/2026, a fase 2 dos e-mails do Nexus).

Uma lista fixa de e-mails vale para todas as usinas; o papel acha a pessoa de cada uma. O caso que pediu: o aviso das
luvas tem de ir à TST e ao supervisor responsável DAQUELA usina (Levi, 24/11/2026), e uma lista fixa mandaria o aviso de
todas as usinas a todos os supervisores.

Os papéis da usina vêm da ficha dela (`campo.decisao_pt.aprovadores`, a mesma régua do De acordo da PT): o Responsável UFV
(o Responsável O&M da ficha), o supervisor de campo da região (com a vaga aberta, o coordenador) e o gestor de contrato.
Os papéis de setor vêm de Base → Acessos → Pessoas e setores (`nexus_setores`, pelo código de cada pessoa).

O e-mail de cada pessoa: o da ficha (cofre do cadastro, `fracttal_pessoal.fichas`), o do usuário do Fracttal ligado a ela
(a cópia de Pessoas e setores, sem ler o Fracttal na hora) e o das pessoas de fora do Fracttal. Pessoa sem e-mail fica de
fora e a prévia diz quem (nunca se inventa endereço).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..cadastro import setor_ids as SID

# o papel → o nome na tela. Os "da usina" dependem da usina da mensagem; os de setor, não
DA_USINA = {"responsavel_ufv": "Responsável UFV da usina", "supervisor_campo": "Supervisor de campo da usina",
            "gestor_contrato": "Gestor de contrato da usina"}
DE_SETOR = {"tst": ("TST (setor Segurança)", SID.SEGURANCA), "cos": ("COS (o setor)", SID.COS),
            "pcm": ("PCM (o setor)", SID.PCM), "supervisao_campo": ("Supervisão Campo (o setor)", SID.SUPERVISAO_CAMPO),
            "engenharia": ("Engenharia (o setor)", SID.ENGENHARIA)}
_CHAVE_APROVADORES = {"responsavel_ufv": ("responsável UFV",),
                      "supervisor_campo": ("supervisor de campo", "coordenador de campo"),
                      "gestor_contrato": ("gestor de contrato",)}


def nomes() -> dict:
    """{papel: nome} de todos, na ordem da tela."""
    return {**DA_USINA, **{k: v[0] for k, v in DE_SETOR.items()}}


@dataclass
class Contexto:
    """O que se lê uma vez por rodada: a base do cadastro, o e-mail de cada pessoa e o setor de cada código."""
    b: object = None
    email_da_pessoa: dict = field(default_factory=dict)      # pessoa_id → e-mail
    email_do_codigo: dict = field(default_factory=dict)      # código HMAC → e-mail
    setor_do_codigo: dict = field(default_factory=dict)      # código HMAC → setor_id
    erros: list = field(default_factory=list)


def contexto(cfg) -> Contexto:
    """Lê tudo o que os papéis precisam (dentro de um app_context). O que não abrir vai em `erros` (a prévia diz)."""
    from ..cadastro.fracttal_pessoal import fichas
    from ..cadastro.ligacao_campo import codigo_da_pessoa
    from ..campo import visao
    chave = cfg.get("NEXUS_PESSOA_HMAC")
    c = Contexto(b=visao._Base())
    emails: set[str] = set()
    for f in fichas(c.b.pessoas, cfg.get("NEXUS_CHAVE_CADASTRO")):
        if "@" in f["email"]:
            c.email_da_pessoa[f["pessoa_id"]] = f["email"]
            emails.add(f["email"])
    try:
        from ..cadastro.telas_fracttal import copia_sem_esperar
        for x in copia_sem_esperar()["rel"].get("linhas") or []:
            e = str(x.get("email") or "").strip().lower()
            if "@" not in e:
                continue
            emails.add(e)
            pid = (x.get("ficha") or {}).get("pessoa_id") if isinstance(x.get("ficha"), dict) else x.get("ficha")
            if pid:
                c.email_da_pessoa.setdefault(pid, e)        # a ficha sem e-mail fica com o do Fracttal ligado a ela
    except Exception as ex:      # noqa: BLE001
        c.erros.append(f"o pessoal do Fracttal não abriu ({type(ex).__name__})")
    try:
        # o cadastro do App de Campo (o e-mail com que o técnico e o supervisor entram no App), ligado à ficha pelo nome:
        # na 1ª prévia (25/11/2026), 6 dos 9 Responsáveis UFV não tinham e-mail na ficha, e o e-mail semanal da
        # Segurança já os achava por este lado
        from ..cadastro.ligacao_campo import mapas_de, pessoa_id as pid_do_nome
        from ..campo import livros_app
        m = mapas_de(cfg, [], c.b.pessoas)
        for _cod, (e, nome) in livros_app.pessoas_por_codigo(chave).items():
            e = str(e or "").strip().lower()
            if "@" not in e:
                continue
            emails.add(e)
            if pid := pid_do_nome(m, nome):
                c.email_da_pessoa.setdefault(pid, e)
    except Exception as ex:      # noqa: BLE001
        c.erros.append(f"o cadastro do App não abriu ({type(ex).__name__})")
    try:
        from ..cadastro import pessoas_fora
        for p in pessoas_fora.ler().get("pessoas") or []:
            e = str(p.get("email") or "").strip().lower()
            if "@" in e:
                emails.add(e)
    except Exception as ex:      # noqa: BLE001
        c.erros.append(f"as pessoas de fora do Fracttal não abriram ({type(ex).__name__})")
    for e in emails:
        if cod := codigo_da_pessoa(chave, e):
            c.email_do_codigo[cod] = e
    try:
        from ..auth.setor_telas import setor_de_cada_codigo
        from ..cadastro import setores as S
        st = S.ler(visao._base(), visao._sessao())
        c.setor_do_codigo = setor_de_cada_codigo(st.get("decisoes") or [])
        # a pessoa da ficha pelo código em Pessoas e setores (o usuário do Fracttal ligado à ficha, o mesmo caminho do
        # e-mail semanal da Segurança): o e-mail vem de quem tem aquele código (o Fracttal, o App, as de fora)
        for d in sorted(st.get("decisoes") or [], key=lambda x: x["decidida_em"]):
            pid, cod = d.get("pessoa_id"), d.get("pessoa_hmac")
            if pid and cod and c.email_do_codigo.get(cod):
                c.email_da_pessoa.setdefault(pid, c.email_do_codigo[cod])
        if st.get("erro"):
            c.erros.append(f"os setores vieram velhos ({st['erro']})")
    except Exception as ex:      # noqa: BLE001
        c.erros.append(f"os setores não abriram ({type(ex).__name__})")
    return c


def da_usina(c: Contexto, papel: str, usina_id) -> list[dict]:
    """[{email, papel, pessoa_id}] do papel na usina; sem a pessoa ou sem o e-mail dela, vazio."""
    from ..campo.decisao_pt import aprovadores
    ids = aprovadores({"usina_id": usina_id}, c.b)["ids"]
    out = []
    for k in _CHAVE_APROVADORES.get(papel, ()):
        pid = ids.get(k)
        if pid and c.email_da_pessoa.get(pid):
            out.append({"email": c.email_da_pessoa[pid], "papel": DA_USINA[papel], "pessoa_id": pid})
            break
    return out


def do_setor(c: Contexto, papel: str) -> list[dict]:
    nome, sid = DE_SETOR[papel]
    return [{"email": c.email_do_codigo[cod], "papel": nome, "pessoa_id": None}
            for cod, s in sorted(c.setor_do_codigo.items()) if s == sid and c.email_do_codigo.get(cod)]


def resolver(c: Contexto, papeis_ou_emails, usina_id=None) -> list[dict]:
    """A lista de destinatários de um modelo: papéis ("responsavel_ufv", "tst", ...) e e-mails soltos. Sem repetição."""
    out, vistos = [], set()
    for x in papeis_ou_emails or []:
        x = str(x or "").strip().lower()
        if x in DA_USINA:
            achados = da_usina(c, x, usina_id) if usina_id else []
        elif x in DE_SETOR:
            achados = do_setor(c, x)
        elif "@" in x:
            achados = [{"email": x, "papel": "lista do modelo", "pessoa_id": None}]
        else:
            achados = []
        for a in achados:
            if a["email"] not in vistos:
                vistos.add(a["email"])
                out.append(a)
    return out
