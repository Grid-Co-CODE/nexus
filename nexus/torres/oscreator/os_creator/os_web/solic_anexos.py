# os_creator/os_web/solic_anexos.py
"""Os anexos da Nova solicitação, guardados no servidor até o PCM aprovar na Fila (Levi, 29/10/2026: "quero que seja
possível adicionar anexos como PDFS e fotos. E quando o PCM gere uma OS pela fila de PCM com aquela solicitação o anexo
vá junto!").

Por que no servidor, e não na solicitação do Fracttal: nenhuma ferramenta nossa sabe GRAVAR anexo numa solicitação (só
ler, `requests.attachments_list`), e provar a chamada exigiria gravar numa solicitação de verdade. O Levi escolheu guardar
aqui até a aprovação; na aprovação, cada arquivo sobe na tarefa da OS pelo caminho provado dos anexos da Engenharia
(`api.attach_imagem_os`), e o que subiu sai do servidor. Na solicitação vista no Fracttal web o anexo não aparece; o bloco
[PCM] da observação diz quais arquivos estão no Nexus.

Uma pasta por nº de solicitação, na pasta de dados do OS Creator (`api._data_dir()`), com o nome já limpo pelo
`solic_eng_web.nome_seguro`. Quem lê só aceita um nome que está na pasta: nada de caminho vindo de fora."""
from __future__ import annotations

import os

import api

PASTA = "solic_anexos"
RAIZ = None               # None = a pasta de dados do OS Creator; os testes apontam para uma pasta temporária


def _pasta(id_code, raiz=None):
    n = str(id_code or "").strip()
    if not n.isdigit():
        return None
    return os.path.join(str(raiz or RAIZ or api._data_dir()), PASTA, n)


def listar(id_code, raiz=None) -> list:
    """[{nome, tamanho}] dos anexos guardados da solicitação, em ordem de nome. [] sem pasta."""
    p = _pasta(id_code, raiz)
    if not p or not os.path.isdir(p):
        return []
    out = []
    for nome in sorted(os.listdir(p), key=str.lower):
        caminho = os.path.join(p, nome)
        if os.path.isfile(caminho) and not nome.endswith(".parcial"):
            out.append({"nome": nome, "tamanho": os.path.getsize(caminho)})
    return out


def guardar(id_code, anexos_ok, raiz=None) -> int:
    """Grava cada anexo ({nome, bytes}) na pasta da solicitação; devolve quantos gravou. Grava com outro nome e troca de
    uma vez: um reinício no meio (o deploy de cada push) não deixa arquivo pela metade."""
    p = _pasta(id_code, raiz)
    if not p or not anexos_ok:
        return 0
    os.makedirs(p, exist_ok=True)
    n = 0
    for a in anexos_ok:
        destino = os.path.join(p, a["nome"])
        with open(destino + ".parcial", "wb") as f:
            f.write(a["bytes"])
        os.replace(destino + ".parcial", destino)
        n += 1
    return n


def ler(id_code, nome, raiz=None):
    """Os bytes de um anexo guardado — só de um nome que ESTÁ na pasta (o nome vem do navegador). None se não houver."""
    if not any(x["nome"] == nome for x in listar(id_code, raiz)):
        return None
    with open(os.path.join(_pasta(id_code, raiz), nome), "rb") as f:
        return f.read()


def apagar(id_code, nomes, raiz=None) -> None:
    """Tira da pasta os anexos que já subiram para a OS; a pasta vazia sai junto."""
    p = _pasta(id_code, raiz)
    if not p:
        return
    guardados = {x["nome"] for x in listar(id_code, raiz)}
    for nome in nomes or []:
        if nome in guardados:
            try:
                os.remove(os.path.join(p, nome))
            except OSError:
                pass
    try:
        if os.path.isdir(p) and not os.listdir(p):
            os.rmdir(p)
    except OSError:
        pass
