"""Os PDFs dos contratos dos clientes, que o Radar guardava no arquivo privado `contratos-zeladoria` do Supabase.

Levi, 06/11/2026: guardar no servidor do Nexus (o Supabase restringe o projeto em 10/11). São 105 arquivos, 442 MB: grande
demais para o banco do Nexus, que guarda planilhas. Ficam no disco do servidor, na pasta de dados
(`<NEXUS_DADOS>/zeladoria/contratos/<caminho>`), como os anexos das Sugestões, com o MESMO caminho que o Radar gravou na
tabela `zeladoria_contratual_docs` (`caminho_pdf` e `caminho_zeladoria`). Assim a tela do Radar abre o PDF pelo Nexus sem
mudar nada além da ponte.

Quem envia: só o administrador, pela página `/t/zeladoria/contratos-pdf`. Quem abre: quem está aprovado no Radar, e só os
caminhos que a cópia do banco cita (nada de abrir um arquivo qualquer da pasta pelo endereço).
"""
import os
from pathlib import Path

MB = 1024 * 1024
MAX_MB = 60                         # o maior do Supabase em 06/11/2026 tinha 27,5 MB


class Recusado(ValueError):
    """O envio ou o caminho não vale; a mensagem vai para a tela."""


def pasta(config) -> Path:
    from ..cadastro.ligacoes import pasta_dados
    return Path(pasta_dados(config)) / "zeladoria" / "contratos"


def caminhos(est: dict) -> dict:
    """{caminho: o documento} de todos os PDFs que a cópia cita (o inteiro e o recorte só de zeladoria)."""
    out = {}
    for d in (est or {}).get("abas", {}).get("zeladoria_contratual_docs", []):
        for col in ("caminho_pdf", "caminho_zeladoria"):
            c = str(d.get(col) or "").strip()
            if c:
                out[c] = d
    return out


def arquivo(config, caminho: str) -> Path:
    """O arquivo do caminho, sempre dentro da pasta dos contratos (caminho com `..`, absoluto ou com `\\` é recusado)."""
    c = str(caminho or "").strip()
    if not c or c.startswith("/") or "\\" in c or ".." in c.split("/") or "\x00" in c:
        raise Recusado("caminho de PDF inválido")
    base = pasta(config).resolve()
    alvo = (base / c).resolve()
    if base != alvo and base not in alvo.parents:
        raise Recusado("caminho de PDF inválido")
    return alvo


def existe(config, caminho: str) -> bool:
    try:
        return arquivo(config, caminho).is_file()
    except Recusado:
        return False


def guardar(config, caminho: str, dados: bytes) -> int:
    """Grava o PDF (troca atômica). Só PDF de verdade e até MAX_MB."""
    if len(dados) > MAX_MB * MB:
        raise Recusado(f"o arquivo passa de {MAX_MB} MB")
    if not dados.startswith(b"%PDF"):
        raise Recusado("o arquivo não é um PDF")
    alvo = arquivo(config, caminho)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    tmp = alvo.with_name(alvo.name + ".enviando")
    with open(tmp, "wb") as f:
        f.write(dados)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, alvo)
    return len(dados)


def situacao(config, est: dict) -> list:
    """Cada PDF que a cópia cita: o cliente, o título, se é o recorte, e se já está no Nexus (com o tamanho)."""
    out = []
    for c, d in sorted(caminhos(est).items()):
        try:
            f = arquivo(config, c)
            tam = f.stat().st_size if f.is_file() else None
        except Recusado:
            tam = None
        out.append({"caminho": c, "cliente": d.get("cliente"), "titulo": d.get("titulo"),
                    "recorte": c == str(d.get("caminho_zeladoria") or "").strip(), "mb": round(tam / MB, 1) if tam else None})
    return out
