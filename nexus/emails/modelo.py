"""O desenho dos e-mails que o Nexus manda (25/11/2026): tabelas e estilo na linha, que é o que o Outlook respeita, nas
cores do e-mail semanal da Segurança (`nexus/hseq/email_semanal.py`, `COR`). Cor em hex aqui é de propósito: o e-mail não
lê os tokens do `nexus.css` (é papel branco no Outlook de quem recebe)."""
from __future__ import annotations

from html import escape

from ..hseq.email_semanal import COR, FONTE

RODAPE = "E-mail automático do Nexus. Não responda: este endereço não recebe mensagens."


def h(s) -> str:
    return escape(str(s if s is not None else ""))


def paragrafo(txt: str) -> str:
    """Um parágrafo de texto (o que a pessoa escreveu no modelo): quebra de linha vira <br>, nada de HTML dela."""
    corpo = "<br>".join(h(x) for x in str(txt or "").split("\n"))
    return f'<p style="margin:0 0 14px;font-size:14px;line-height:21px;color:{COR["tinta"]};font-family:{FONTE}">{corpo}</p>'


def titulo_secao(txt: str) -> str:
    return (f'<p style="margin:18px 0 8px;font-size:12px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;'
            f'color:{COR["mudo"]};font-family:{FONTE}">{h(txt)}</p>')


def tabela(cabecalho: list[str], linhas: list[list], destaque: set[int] | None = None) -> str:
    """Uma tabela simples. `destaque`: os índices das linhas em vermelho (o atrasado, o vencido)."""
    destaque = destaque or set()
    th = "".join(f'<th align="left" style="padding:7px 8px;font-size:12px;color:{COR["mudo"]};border-bottom:1px solid '
                 f'{COR["linha"]};font-family:{FONTE}">{h(c)}</th>' for c in cabecalho)
    corpo = ""
    for i, ln in enumerate(linhas):
        cor = COR["critico"] if i in destaque else COR["tinta"]
        corpo += "<tr>" + "".join(f'<td style="padding:7px 8px;font-size:13px;color:{cor};border-bottom:1px solid '
                                  f'{COR["linha"]};font-family:{FONTE}">{h(c)}</td>' for c in ln) + "</tr>"
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">'
            f"<tr>{th}</tr>{corpo}</table>")


def botao(rotulo: str, link: str) -> str:
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:18px 0 4px"><tr>'
            f'<td bgcolor="{COR["verde"]}" style="background:{COR["verde"]};padding:12px 24px">'
            f'<a href="{h(link)}" style="color:{COR["navy"]};font-size:14px;font-weight:700;text-decoration:none;'
            f'font-family:{FONTE}">{h(rotulo)}</a></td></tr></table>')


def pagina(titulo: str, miolo: str, *, sobre: str = "", rodape: str = RODAPE) -> str:
    """O e-mail inteiro: a barra escura com o verde, o título, o miolo (HTML já montado por quem chama) e o rodapé."""
    return (
        f'<!doctype html><html><body style="margin:0;padding:0;background:{COR["fundo"]}">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{COR["fundo"]}">'
        f'<tr><td align="center" style="padding:24px 12px">'
        f'<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;'
        f'background:{COR["branco"]};border:1px solid {COR["linha"]}">'
        f'<tr><td style="background:{COR["navy"]};padding:16px 28px;border-bottom:3px solid {COR["verde"]}">'
        f'<span style="font-size:13px;font-weight:700;letter-spacing:1px;color:{COR["verde"]};font-family:{FONTE}">'
        f'GRID CO. · NEXUS</span>'
        + (f'<br><span style="font-size:12px;color:{COR["sub"]};font-family:{FONTE}">{h(sobre)}</span>' if sobre else "")
        + f'</td></tr><tr><td style="padding:24px 28px 8px">'
        f'<h1 style="margin:0 0 16px;font-size:20px;line-height:26px;color:{COR["tinta"]};font-family:{FONTE}">'
        f'{h(titulo)}</h1>{miolo}</td></tr>'
        f'<tr><td style="padding:14px 28px 22px;border-top:1px solid {COR["linha"]};font-size:12px;color:{COR["mudo"]};'
        f'font-family:{FONTE}">{h(rodape)}</td></tr></table></td></tr></table></body></html>')
