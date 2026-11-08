"""O acesso dos clientes ao Nexus (07/11/2026, Levi: "Quero um acesso extra chamado 'clientes' onde eu boto o e-mail do
cliente avulso [...] e aí ele decide a senha"; e, decidido com ele no mesmo dia: a senha nasce por um LINK DE CONVITE de
uso único, e o cliente vê SÓ as usinas dele).

Por que assim:
- **O convite, não o "primeiro login define a senha".** O e-mail do cliente não é segredo: quem o soubesse entraria
  antes dele e criaria a senha no lugar dele. O link (`/entrar?convite=...`) nasce em Base → Acessos → Clientes, aparece
  uma vez na tela para a Grid mandar (WhatsApp, Teams ou o e-mail de quem manda: o e-mail do servidor está barrado no
  tenant), vale 7 dias e uma vez só. No arquivo vai o sha256 do token, nunca o token.
- **A senha só embaralhada (scrypt) e FORA do banco.** O banco tem leitura aberta (nexus/dados/CLAUDE.md, regra 8): nem
  o resumo da senha vai para lá. Mora no `clientes.json` da pasta de dados do Nexus (NEXUS_DADOS, a mesma do
  `acessos.json` dos administradores), com a mesma escrita atômica e a mesma trava (`acessos.py`).
- **A conta é ligada a um cliente do cadastro** (`cliente_id` de `cadastro_nexus · clientes`): é por ele que as telas
  do setor Clientes recortam as usinas. "Contrato" não existe como entidade no cadastro (`campo/visao_cliente.py`).
- **Remover vale no próximo clique**: o portão confere a conta a cada pedido (o arquivo é relido só quando muda).
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from . import acessos as A

ARQUIVO = "clientes.json"
CONVITE_DIAS = 7
SENHA_MIN = 10
SENHA_MAX = 200
SESSAO_S = 12 * 3600            # como a sessão da Microsoft: 12 h a partir do login
MAX_AUDITORIA = 1000
# o scrypt da biblioteca padrão: n=2^14, r=8 (16 MiB de memória por conferência); o sal é por conta
_N, _R, _P = 2 ** 14, 8, 1

Recusado = A.Recusado
Ilegivel = A.Ilegivel


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _vazio() -> dict:
    return {"versao": 1, "contas": [], "auditoria": []}


def _forma(dado) -> dict:
    if not isinstance(dado, dict):
        raise ValueError("clientes.json fora do formato")
    contas = [c for c in dado.get("contas") or [] if isinstance(c, dict) and c.get("email")]
    return {"versao": 1, "contas": contas, "auditoria": [x for x in dado.get("auditoria") or [] if isinstance(x, dict)]}


def _caminho(config):
    p = A.pasta(config)
    return None if p is None else p / ARQUIVO


def estado(config) -> dict:
    """{"contas": [...], "auditoria": [...], "sem_pasta", "erro"}: a tela mostra o erro e não grava por cima."""
    p = _caminho(config)
    if p is None:
        return {**_vazio(), "sem_pasta": True, "erro": ""}
    try:
        dado = A._ler(p, _forma) or _vazio()
    except Ilegivel as ex:
        return {**_vazio(), "sem_pasta": False, "erro": str(ex)}
    return {**dado, "sem_pasta": False, "erro": ""}


def _mudar(config, mudanca):
    p = _caminho(config)
    if p is None:
        raise Recusado("Este Nexus está sem pasta de dados (NEXUS_DADOS): nada foi gravado.")
    with A._trava(p):
        dado = A._ler(p, _forma) or _vazio()       # Ilegivel sobe: nada se grava por cima do que não abriu
        resultado = mudanca(dado)
        dado["auditoria"] = dado["auditoria"][-MAX_AUDITORIA:]
        A._gravar_atomico(p, dado)
        return resultado


def _resumo(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _embaralhar(senha: str, sal: bytes | None = None) -> str:
    sal = sal or secrets.token_bytes(16)
    h = hashlib.scrypt(senha.encode(), salt=sal, n=_N, r=_R, p=_P, maxmem=64 * 1024 * 1024, dklen=32)
    return f"scrypt${_N}${_R}${_P}${sal.hex()}${h.hex()}"


def _confere(senha: str, guardada: str) -> bool:
    try:
        _, n, r, p, sal, h = guardada.split("$")
        calc = hashlib.scrypt(senha.encode(), salt=bytes.fromhex(sal), n=int(n), r=int(r), p=int(p),
                              maxmem=64 * 1024 * 1024, dklen=32)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calc.hex(), h)


# o resumo de uma senha qualquer: a conferência de um e-mail que não existe gasta o mesmo tempo (não diz quem é cliente)
_FALSA = _embaralhar(secrets.token_urlsafe(16))


def _conta(dado: dict, email: str) -> dict | None:
    return next((c for c in dado["contas"] if c["email"] == email), None)


def _novo_convite(c: dict) -> str:
    token = secrets.token_urlsafe(32)
    c["convite_hash"] = _resumo(token)
    c["convite_expira"] = A._iso(_agora() + timedelta(days=CONVITE_DIAS))
    return token


# ── a tela Base → Acessos → Clientes ─────────────────────────────────────────────────────────────────────────────
def adicionar(config, email, cliente_id: int, nome_cliente: str, quem: str) -> tuple[str, str]:
    """Cria a conta do cliente (ou reativa a removida) e devolve (e-mail, token do convite)."""
    e = A.email_normal(email)
    if not cliente_id:
        raise Recusado("Escolha o cliente do cadastro: é por ele que o Nexus mostra só as usinas dele.")

    def mudanca(dado):
        c = _conta(dado, e)
        if c and c.get("status") == "ativa":
            raise Recusado(f"{e} já tem acesso de cliente. Para mandar um link novo, use Gerar link na linha dele.")
        quando = A._iso(_agora())
        if c is None:
            c = {"email": e}
            dado["contas"].append(c)
        c.update(cliente_id=int(cliente_id), cliente=nome_cliente, status="ativa", senha=None, senha_em=None,
                 criada_em=quando, por=quem)
        token = _novo_convite(c)
        dado["auditoria"].append({"quando": quando, "quem": quem, "acao": "adicionou", "email": e,
                                  "cliente": nome_cliente})
        return e, token

    return _mudar(config, mudanca)


def gerar_link(config, email, quem: str) -> str:
    """Um link novo (o anterior deixa de valer); serve também para trocar a senha esquecida."""
    e = A.email_normal(email)

    def mudanca(dado):
        c = _conta(dado, e)
        if not c or c.get("status") != "ativa":
            raise Recusado(f"{e} não tem acesso de cliente ativo.")
        token = _novo_convite(c)
        dado["auditoria"].append({"quando": A._iso(_agora()), "quem": quem, "acao": "gerou link", "email": e,
                                  "cliente": c.get("cliente") or ""})
        return token

    return _mudar(config, mudanca)


def remover(config, email, quem: str) -> str:
    """Tira o acesso: a senha e o convite saem, e a sessão aberta cai no próximo clique."""
    e = A.email_normal(email)

    def mudanca(dado):
        c = _conta(dado, e)
        if not c or c.get("status") != "ativa":
            raise Recusado(f"{e} não tem acesso de cliente ativo.")
        c.update(status="removida", senha=None, convite_hash=None, convite_expira=None,
                 removida_em=A._iso(_agora()), removida_por=quem)
        dado["auditoria"].append({"quando": A._iso(_agora()), "quem": quem, "acao": "removeu", "email": e,
                                  "cliente": c.get("cliente") or ""})
        return e

    return _mudar(config, mudanca)


# ── o convite e o login ──────────────────────────────────────────────────────────────────────────────────────────
def conta_do_convite(config, token: str) -> dict | None:
    """A conta ativa cujo convite é este token e ainda vale; senão None (vencido, usado, removido ou inventado)."""
    token = str(token or "")
    if not token or len(token) > 200:
        return None
    r = _resumo(token)
    for c in estado(config)["contas"]:
        if c.get("status") == "ativa" and c.get("convite_hash") and hmac.compare_digest(c["convite_hash"], r):
            expira = A._de_iso(c.get("convite_expira"))
            return c if expira and expira > _agora() else None
    return None


def definir_senha(config, token: str, senha: str, repetida: str) -> str:
    """A senha que o próprio cliente escolhe pelo link; o link deixa de valer. Devolve o e-mail."""
    senha = str(senha or "")
    if senha != str(repetida or ""):
        raise Recusado("As duas senhas não são iguais.")
    if len(senha) < SENHA_MIN:
        raise Recusado(f"A senha precisa ter pelo menos {SENHA_MIN} caracteres.")
    if len(senha) > SENHA_MAX:
        raise Recusado("A senha passou do tamanho máximo.")
    r = _resumo(str(token or ""))

    def mudanca(dado):
        c = next((x for x in dado["contas"] if x.get("status") == "ativa" and x.get("convite_hash")
                  and hmac.compare_digest(x["convite_hash"], r)), None)
        expira = A._de_iso((c or {}).get("convite_expira"))
        if not c or not expira or expira <= _agora():
            raise Recusado("Este link não vale mais (já foi usado ou passou dos 7 dias). Peça um novo à Grid Co.")
        local = c["email"].split("@")[0].lower()
        if len(local) >= 4 and local in senha.lower():
            raise Recusado("A senha não pode conter o seu e-mail.")
        c.update(senha=_embaralhar(senha), senha_em=A._iso(_agora()), convite_hash=None, convite_expira=None)
        dado["auditoria"].append({"quando": A._iso(_agora()), "quem": c["email"], "acao": "definiu a senha",
                                  "email": c["email"], "cliente": c.get("cliente") or ""})
        return c["email"]

    return _mudar(config, mudanca)


def conferir(config, email: str, senha: str) -> dict | None:
    """A conta ativa com esta senha, ou None. Gasta o mesmo tempo com e-mail que não existe."""
    try:
        e = A.email_normal(email)
    except Recusado:
        _confere(str(senha or ""), _FALSA)
        return None
    c = next((x for x in estado(config)["contas"] if x["email"] == e), None)
    if not c or c.get("status") != "ativa" or not c.get("senha"):
        _confere(str(senha or ""), _FALSA)
        return None
    return c if _confere(str(senha or ""), c["senha"]) else None


def conta_ativa(config, email: str, cliente_id) -> bool:
    """A sessão do cliente ainda vale? A conta segue ativa, com senha e com o mesmo cliente. Arquivo que não abre FECHA."""
    try:
        contas = A._ler(_caminho(config), _forma)["contas"] if _caminho(config) else []
    except (Ilegivel, TypeError):
        return False
    c = next((x for x in contas if x["email"] == email), None)
    return bool(c and c.get("status") == "ativa" and c.get("senha") and c.get("cliente_id") == cliente_id)
