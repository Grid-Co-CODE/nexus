"""Limpa o index.html do Radar de Fornecedores para ele entrar no Nexus como o clone da torre Zeladoria.

O que faz, e por quê:
- troca os nomes de colegas pelo papel ("o aprovador" vira Head, a segunda alçada vira Analista, o supervisor da equipe
  primarizada vira Equipe), em identificadores, rótulos, comentários e chaves de dado. O repositório do Nexus é público.
  O de-para com os nomes fica FORA dele (`--nomes`, um JSON {"texto": "troca"}), e a frase vem antes do nome solto;
- tira o Supabase: as duas constantes (endereço e chave) e o carregador das CDNs. No lugar do carregador entra o marcador
  `<!--ZELADORIA:PONTE-->`, onde a torre, ao servir, põe a ponte (nexus/static/zeladoria/ponte.js);
- põe `<!--ZELADORIA:CONFIG-->` logo no `<head>`, antes de qualquer script, para a configuração da torre;
- faz o app abrir na aba pedida pelo menu do Nexus (`window.ZELADORIA_ABA`);
- troca o e-mail de exemplo da tela de login.

Cada troca estrutural tem de acontecer exatamente uma vez. Se o Radar mudar e uma delas não casar, a ferramenta para e
diz qual, em vez de gerar um clone pela metade. No fim ela procura os nomes que sobraram: sobrando algum, sai com erro e
lista as linhas.

Uso: python -I ferramentas/zeladoria_limpar_clone.py --origem <index.html do Radar> --nomes <de_para.json> --saida
nexus/torres/zeladoria/clone/radar.html
"""
import argparse
import json
import re
import sys
from pathlib import Path


class TrocaFalhou(RuntimeError):
    pass


def _uma_vez(texto: str, velho, novo: str, o_que: str, regex=False, flags=0) -> str:
    if regex:
        achados = re.findall(velho, texto, flags)
        if len(achados) != 1:
            raise TrocaFalhou(f"{o_que}: esperava 1, achei {len(achados)}")
        return re.sub(velho, lambda _m: novo, texto, count=1, flags=flags)
    n = texto.count(velho)
    if n != 1:
        raise TrocaFalhou(f"{o_que}: esperava 1, achei {n}")
    return texto.replace(velho, novo)


def trocar_nomes(texto: str, de_para: dict) -> str:
    for velho in sorted((k for k in de_para if not k.startswith("_")), key=len, reverse=True):
        texto = texto.replace(velho, de_para[velho])
    return texto


def limpar(texto: str, de_para: dict) -> str:
    texto = trocar_nomes(texto, de_para)
    # o cronograma importado (arquivo do PCM) escreve "Rota do <supervisor>" com o nome de verdade: a rota se
    # reconhece pelo começo do texto, sem depender do nome
    n = texto.count("/rota (do )?equipe")
    if n != 3:
        raise TrocaFalhou(f"a regra da rota da equipe: esperava 3, achei {n}")
    texto = texto.replace("/rota (do )?equipe", r"/^\s*rota\b")
    texto = _uma_vez(texto, r"^var SUPABASE_URL = '[^']*';\r?\n", "", "a constante do endereço do Supabase",
                     regex=True, flags=re.M)
    texto = _uma_vez(texto, r"^var SUPABASE_ANON_KEY = '[^']*';\r?\n", "", "a constante da chave do Supabase",
                     regex=True, flags=re.M)
    texto = _uma_vez(texto, "window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY)",
                     "window.supabase.createClient()", "a criação do cliente")
    texto = _uma_vez(texto, r"<script>\s*/\* Carrega o supabase-js.*?</script>", "<!--ZELADORIA:PONTE-->",
                     "o carregador das CDNs", regex=True, flags=re.S)
    texto = _uma_vez(texto, r"^<head>\r?$", "<head>\n<!--ZELADORIA:CONFIG-->", "o <head>", regex=True, flags=re.M)
    texto = _uma_vez(texto, "var ui = { tab: 'overview',", "var ui = { tab: (window.ZELADORIA_ABA || 'overview'),",
                     "a aba inicial")
    texto = texto.replace("voce@gridco.com.br", "voce@empresa.com.br")
    return texto


def sobras(texto: str, de_para: dict) -> list:
    nomes = {k.lower() for k in de_para if not k.startswith("_")}
    padrao = re.compile("|".join(re.escape(n) for n in sorted(nomes)), re.IGNORECASE)
    return [i for i, linha in enumerate(texto.splitlines(), 1) if padrao.search(linha)]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--origem", required=True)
    p.add_argument("--nomes", required=True)
    p.add_argument("--saida", required=True)
    a = p.parse_args(argv)
    texto = Path(a.origem).read_text(encoding="utf-8")
    de_para = json.loads(Path(a.nomes).read_text(encoding="utf-8"))
    try:
        limpo = limpar(texto, de_para)
    except TrocaFalhou as e:
        print(f"parei: {e}", file=sys.stderr)
        return 1
    linhas = sobras(limpo, de_para)
    if linhas:
        print(f"parei: sobraram nomes em {len(linhas)} linha(s): {linhas[:30]}", file=sys.stderr)
        return 1
    saida = Path(a.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(limpo, encoding="utf-8", newline="\n")
    print(f"ok: {saida} ({len(limpo.splitlines())} linhas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
