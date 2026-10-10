"""A PT no Fracttal, para as telas do Nexus (Levi, 05/10/2026): o PDF que o App anexa na tarefa quando dá o De acordo
e a assinatura do técnico na APR. Nada passa pelo App nem pelo Azure, e nada vai para o banco: a assinatura é dado
pessoal e só aparece na tela de quem entrou no Nexus.

- **PDF** ("um histórico das PTs assinadas podendo exportar o anexo do PDF puxando a assinatura do colaborador e quem
  aceitou, conforme estava no Azure"): no De acordo, o `_pt_efeito` do App gera o PDF (com as duas assinaturas) e
  anexa na tarefa com a descrição "Permissão de Trabalho <número>". A lista de anexos da OS vem pelo REST do Fracttal
  (a credencial do OS Creator) com o link do arquivo já assinado (vale 24 h; medido em 05/10, PT-15457-0510-1751). O
  Nexus baixa e entrega: o link não sai para o navegador. PT negada não tem PDF (o App pausa a tarefa).
- **Assinatura do técnico** ("ao lado de A PT tem que ter a assinatura do técnico"): é a da APR, no formulário de
  Compliance da tarefa (`filled_by_signature`), que só sai pelo RPC `tasks.work_order_offline_ptw_download`, com o
  login de uma PESSOA. O Nexus usa o login do Fracttal do OS Creator de quem está olhando (o mesmo com que ele
  assina a PT). O valor pode vir como imagem (data URI), como link pronto ou como caminho do arquivo, que se assina
  com `companies.s3_object_get` (os três formatos que o `_pt_ass_de_valor` do App aceita).
"""
import base64
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone

from . import nota_fracttal

PDF_MAX = 15 * 1024 * 1024
IMG_MAX = 3 * 1024 * 1024
CACHE_S = 3600          # a assinatura de uma PT não muda: 1 h sem pedir de novo ao Fracttal (a cota é da empresa)
_ASSINATURAS: dict = {}


class SemArquivo(LookupError):
    """O Fracttal não tem o que se pediu: o texto diz por quê, para a tela mostrar."""


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def _baixar(url: str, limite: int) -> bytes:
    import requests
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    if len(r.content) > limite:
        raise SemArquivo("o arquivo no Fracttal é grande demais")
    return r.content


# ── o PDF da PT ──────────────────────────────────────────────────────────────────────────────────────────────────
def pdf(os_, numero, ler=None) -> bytes:
    """O PDF que o App anexou na tarefa no De acordo. SemArquivo quando não há (PT negada, decidida antes de o App
    anexar, ou o anexo falhou)."""
    descricao = _norm(f"Permissão de Trabalho {numero}")
    anexo = next((a for a in nota_fracttal.anexos_da_os(os_, ler)
                  if _norm(a.get("description")) == descricao and a.get("value")), None)
    if not anexo:
        raise SemArquivo(f"o PDF da {numero} não está nos anexos da OS {os_} no Fracttal")
    corpo = _baixar(str(anexo["value"]), PDF_MAX)
    if not corpo.startswith(b"%PDF"):
        raise SemArquivo("o anexo do Fracttal não é um PDF")
    return corpo


# ── o PDF da APR ─────────────────────────────────────────────────────────────────────────────────────────────────
# Levi, 09/10/2026: "invés de PDF e baixar terá uma coluna de PT e APR, terá como baixar o relatório de ambas
# individualmente". Desde a v251 o App anexa toda APR na tarefa como PDF, com a descrição "APR OS 15223 09-10-2026
# 07h42" (+ " v2" na versão de Novo risco da APR do dia; `_aprpdf_nome` do App), no horário de Brasília.
_APR_QUANDO = re.compile(r"(\d{2})-(\d{2})-(\d{4}) (\d{2})h(\d{2})")
_BRT = timezone(timedelta(hours=-3))


def _quando_apr(descricao) -> datetime | None:
    m = _APR_QUANDO.search(str(descricao or ""))
    try:
        return datetime(int(m[3]), int(m[2]), int(m[1]), int(m[4]), int(m[5])) if m else None
    except ValueError:
        return None


def apr_pdf(os_, criada=None, ler=None) -> tuple[bytes, str]:
    """(o PDF, a descrição do anexo) da APR da OS. Com mais de uma APR na OS (tarefas ou dias diferentes), a de horário
    mais perto da criação da PT: a APR que abre a PT nasce junto com ela. SemArquivo quando o App ainda não anexou."""
    alvo = _norm(f"APR OS {os_}")
    cands = [a for a in nota_fracttal.anexos_da_os(os_, ler)
             if a.get("value") and (_norm(a.get("description")) == alvo or _norm(a.get("description")).startswith(alvo + " "))]
    if not cands:
        raise SemArquivo(f"a APR da OS {os_} ainda não está nos anexos do Fracttal (o App anexa o PDF minutos depois)")
    if criada:
        ref = (criada.astimezone(_BRT) if criada.tzinfo else criada).replace(tzinfo=None)
        cands.sort(key=lambda a: abs((_quando_apr(a.get("description")) - ref).total_seconds())
                   if _quando_apr(a.get("description")) else float("inf"))
    a = cands[0]
    corpo = _baixar(str(a["value"]), PDF_MAX)
    if not corpo.startswith(b"%PDF"):
        raise SemArquivo("o anexo da APR no Fracttal não é um PDF")
    return corpo, str(a.get("description") or f"APR OS {os_}")


# ── a assinatura do técnico na APR ───────────────────────────────────────────────────────────────────────────────
def id_tarefa(os_, tarefa, ler=None) -> int | None:
    """A tarefa da OS a que a PT se refere: a única da OS, ou a de mesma descrição. Duas candidatas = não chuta."""
    tarefas = [t for t in nota_fracttal.tarefas_da_os(os_, ler) if t.get("id_work_orders_tasks")]
    ids = {int(float(t["id_work_orders_tasks"])) for t in tarefas}
    if len(ids) == 1:
        return ids.pop()
    alvo = _norm(tarefa)
    iguais = {int(float(t["id_work_orders_tasks"])) for t in tarefas if alvo and _norm(t.get("tasks_description")) == alvo}
    return iguais.pop() if len(iguais) == 1 else None


def _imagem(valor, rpc) -> str:
    """A assinatura como data URI, dos três formatos que o Fracttal guarda."""
    if isinstance(valor, dict):
        valor = valor.get("url") or valor.get("key") or valor.get("name") or valor.get("value") or ""
    s = str(valor or "").strip()
    if not s:
        raise SemArquivo("a APR desta tarefa não tem a assinatura do técnico")
    if re.match(r"^data:image/(png|jpe?g);base64,", s, re.I):
        if len(s) > IMG_MAX * 4 // 3:
            raise SemArquivo("a assinatura na APR é grande demais")
        return s
    if s.startswith("https://"):
        url = s
    elif "/" in s and not re.match(r"^[a-z]+:", s, re.I):
        r = rpc("companies.s3_object_get", {"name": s})
        d = r.get("data") if isinstance(r, dict) else r
        url = d.get("url") if isinstance(d, dict) else None
        if not url:
            raise SemArquivo("o Fracttal não assinou o endereço da assinatura")
    else:
        raise SemArquivo("a assinatura veio num formato que o Nexus não conhece")
    corpo = _baixar(url, IMG_MAX)
    tipo = "jpeg" if corpo[:3] == b"\xff\xd8\xff" else "png"
    return f"data:image/{tipo};base64," + base64.b64encode(corpo).decode()


def assinatura_do_tecnico(numero, id_wt: int, rpc) -> str:
    """A assinatura que o técnico desenhou na APR (data URI). `rpc(metodo, params)` chama o Fracttal com o login de
    quem está olhando. Guardada 1 h em memória (nunca em disco nem no banco)."""
    guardada = _ASSINATURAS.get(numero)
    if guardada and time.time() - guardada[0] < CACHE_S:
        return guardada[1]
    r = rpc("tasks.work_order_offline_ptw_download", {"id_work_order_task": int(id_wt)})
    d = (r or {}).get("data") if isinstance(r, dict) else None
    if not d:
        raise SemArquivo("o Fracttal não entregou a APR desta tarefa")
    valor = next((f["values"]["filled_by_signature"] for f in (d.get("pre") or [])
                  if isinstance(f, dict) and isinstance(f.get("values"), dict)
                  and f["values"].get("filled_by_signature")), None)
    img = _imagem(valor, rpc)
    _ASSINATURAS[numero] = (time.time(), img)
    return img


def limpar():
    _ASSINATURAS.clear()
