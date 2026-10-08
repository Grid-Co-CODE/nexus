"""Guarda: nenhum nome de técnico ou supervisor nos arquivos versionados (Levi, 08/10/2026, passo 2b da auditoria Kimball).

Por quê. O repositório `Grid-Co-CODE/nexus` é PÚBLICO e nome de quem vai a campo ao lado de nota, ronda sem OS ou
pendência é dado pessoal ligado a desempenho (LGPD). Em 08/10 a varredura achou nomes reais em docstring, CLAUDE.md,
mockup e teste; eles viraram referência genérica ("um técnico", "o programador do PCM", "Fulano de Tal"). Cite a pessoa
pelo PAPEL, nunca pelo nome.

Como. A lista de nomes é montada SÓ NA MEMÓRIA, das três fontes de pessoas do Nexus: o livro `rondas_app_campo` (coluna
`Técnico`, GET na API de leitura aberta), o cadastro do App (`identidades.json`, `NEXUS_CAMPO_IDENTIDADES`; fora o
administrador do App, que é o dono do repositório e assina as decisões) e o `cadastro_nexus · pessoas` decifrado com
`NEXUS_CHAVE_CADASTRO`. Nenhum nome é escrito aqui nem na mensagem de falha: ela só diz `caminho:linha`.
- nome inteiro, e primeiro nome + outro nome da pessoa (o "Nome padrão" é primeiro + último), sem acento nem caixa,
  inclusive com ponto ou hífen no meio (e-mail, identificador): em qualquer arquivo;
- o e-mail da pessoa: em qualquer arquivo;
- o primeiro nome SOZINHO só onde parece gente: com maiúscula, depois de artigo ou preposição ("a X pediu", "no PC do
  X"), fora de `tests/` (as fixtures usam primeiro nome fictício) e fora de palavra que é nome de usina ou cidade do
  cadastro. Primeiro nome sozinho também é nome de usina, de cidade e de mês: o que esta regra não pega, revise à mão.
Sem a chave, o cadastro do App ou o banco, o teste é pulado e diz por quê (a máquina de quem só programa não tem nada
disso). O histórico do git continua com os nomes de antes: este teste não reescreve histórico.
"""
import json
import re
import subprocess
import unicodedata
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
# A cópia IDÊNTICA do motor do PCM (nexus/pcm/motor/README.md: "Não edite estes arquivos", conferida por hash): o nome
# do arquivo AUXILIAR que o motor lê leva o nome de quem montou a planilha. Muda no repositório do PCM e é copiada.
COPIA_INTOCAVEL = {"nexus/pcm/motor/programacao_v7.py", "nexus/pcm/motor/fonte_bd_api.py",
                   "nexus/pcm/motor/gerar_bd_via_api.py"}
BINARIOS = (".png", ".ico", ".jpg", ".jpeg", ".gif", ".pdf", ".xlsx", ".zip")
PARTICULAS = {"de", "da", "do", "das", "dos", "e", "di", "du", "del", "van", "von"}
SEP = r"[\s._\-]+"
# o que vem antes de um primeiro nome quando ele é gente: "a X", "do X", "com o X", "pela X"...
ANTES_DE_GENTE = re.compile(r"(?:^|[\s(\"'])(?:o|a|do|da|pelo|pela|ao|à|com o|com a|que o|que a|e o|e a)\s+$",
                            re.IGNORECASE)


def _norm(s) -> str:
    return " ".join(unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower().split())


def _norm_com_mapa(linha: str):
    """O texto sem acento e em minúsculas, e o índice no original de cada caractere (para olhar a maiúscula e o que
    vem antes no texto de verdade)."""
    out, mapa = [], []
    for i, ch in enumerate(linha):
        for c in unicodedata.normalize("NFKD", ch):
            if unicodedata.combining(c):
                continue
            for x in c.encode("ascii", "ignore").decode().lower():
                out.append(x)
                mapa.append(i)
    return "".join(out), mapa


def _fontes():
    """(nomes, e-mails, palavras de usina e cidade), só na memória. Pula o teste sem o que precisa."""
    from nexus.cadastro.cifra import CifraErro, Cofre
    from nexus.cadastro.ligacoes import BASE_API
    from nexus.campo.pessoas import PASTA_DO_APP
    from nexus.config import ler_ambiente
    from nexus.dados import livros
    env = ler_ambiente()
    if not env.get("NEXUS_CHAVE_CADASTRO"):
        pytest.skip("sem NEXUS_CHAVE_CADASTRO nesta máquina: o cadastro de pessoas não decifra")
    ident_arq = Path(env.get("NEXUS_CAMPO_IDENTIDADES") or (PASTA_DO_APP / "identidades.json"))
    if not ident_arq.exists():
        pytest.skip("sem o identidades.json do App (NEXUS_CAMPO_IDENTIDADES) nesta máquina")
    import requests

    class SoLeitura:            # só GET: este teste nunca grava no banco
        def __init__(self):
            self.s = requests.Session()

        def get(self, *a, **k):
            return self.s.get(*a, **k)
    base, s = (env.get("GRIDCO_DB_API") or BASE_API).rstrip("/"), SoLeitura()
    try:
        pessoas = livros.ler(base, s, "cadastro_nexus", "pessoas")
        usinas = livros.ler(base, s, "cadastro_nexus", "usinas")
        rondas = livros.ler(base, s, "rondas_app_campo")
    except requests.RequestException as e:
        pytest.skip(f"sem acesso ao banco do Nexus ({type(e).__name__})")
    if not pessoas:
        pytest.skip("o cadastro de pessoas veio vazio do banco")
    nomes, emails = set(), set()
    cofre = Cofre(env["NEXUS_CHAVE_CADASTRO"])
    for p in pessoas:
        try:
            d = json.loads(cofre.decifrar(p["sensivel_cifrado"], f"banco/pessoas/{int(float(p['pessoa_id']))}"))
        except (CifraErro, ValueError, KeyError, TypeError):
            continue
        nomes.update({_norm(d.get("nome")), _norm(d.get("nome_padrao"))})
        if d.get("email"):
            emails.add(str(d["email"]).strip().lower())
    ident = json.loads(ident_arq.read_text(encoding="utf-8"))
    admins = {str(e).strip().lower() for e in ident.get("adminEmails") or []}
    for em, p in (ident.get("porEmail") or {}).items():
        if str(em).strip().lower() in admins:
            continue
        nomes.update({_norm((p or {}).get(c)) for c in ("nome", "nomePadrao", "supervisor")})
        emails.add(str(em).strip().lower())
    nomes.update(_norm(k) for k in (ident.get("supervisoresScope") or {}) if "@" not in str(k))
    nomes.update(_norm(r.get("Técnico")) for r in rondas)
    nomes.discard("")
    emails.discard("")
    lugares = {t for u in usinas for c in ("nome", "cidade") for t in _norm(u.get(c)).split()}
    return nomes, emails, lugares


def _regex_unica(alternativas) -> re.Pattern | None:
    alts = sorted(alternativas, key=len, reverse=True)
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(alts) + r")(?![a-z0-9])") if alts else None


def _padroes(nomes, emails, lugares):
    inteiros, primeiros = set(), set()
    for n in nomes:
        toks = [t for t in n.split() if t not in PARTICULAS]
        if len(toks) >= 2:
            inteiros.add(SEP.join(re.escape(t) for t in n.split()))
            inteiros.update(re.escape(toks[0]) + SEP + re.escape(t) for t in toks[1:])
        if toks and len(toks[0]) >= 3 and toks[0] not in lugares:
            primeiros.add(re.escape(toks[0]))
    return (_regex_unica(inteiros), re.compile("|".join(re.escape(e) for e in sorted(emails))) if emails else None,
            _regex_unica(primeiros))


def _versionados():
    try:
        r = subprocess.run(["git", "-C", str(RAIZ), "ls-files", "-z"], capture_output=True, check=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        pytest.skip("sem o git nesta máquina: não dá para saber o que é versionado")
    return [x.decode("utf-8") for x in r.stdout.split(b"\0") if x]


def test_nenhum_nome_de_tecnico_ou_supervisor_nos_arquivos_versionados():
    inteiro, email, primeiro = _padroes(*_fontes())
    achados = []
    for arq in _versionados():
        if arq in COPIA_INTOCAVEL or arq.lower().endswith(BINARIOS):
            continue
        try:
            texto = (RAIZ / arq).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        de_teste = arq.startswith("tests/")
        for n, linha in enumerate(texto.split("\n"), 1):
            norm, mapa = _norm_com_mapa(linha)
            if (inteiro and inteiro.search(norm)) or (email and email.search(norm)):
                achados.append(f"{arq}:{n}")
                continue
            if de_teste or not primeiro:
                continue
            for m in primeiro.finditer(norm):
                i, f = mapa[m.start()], mapa[m.end() - 1] + 1
                if (linha[i:i + 1].isupper() and ANTES_DE_GENTE.search(linha[:i])
                        and not re.match(r"\s*[\d-]", linha[f:f + 3])):
                    achados.append(f"{arq}:{n}")
                    break
    # só o caminho e a linha: o nome nunca vai para a saída do teste
    assert not achados, ("nome de pessoa em arquivo versionado (o repositório é público; cite pelo papel): "
                         + ", ".join(achados))
