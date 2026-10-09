"""A AUXILIAR do motor sai do cadastro do Nexus, não da planilha da pasta do PCM.

A AUXILIAR da pasta do PCM (a planilha que o motor lê, `NOME`) não tem dado próprio: é um Power Query da aba CONSULTA do BD_Operações, que por sua vez é
outro Power Query da aba Operações (UFV = CLIENTE - OPERAÇÃO). Só atualiza quando alguém abre a planilha no Excel e
manda atualizar. Medido em 02/10/2026, contra o cadastro do Nexus (importado do BD em 29/09):
- a AUXILIAR tinha 166 usinas, o cadastro 258; 20 nomes da AUXILIAR já não existem no BD;
- nas 146 que casam, 18 estavam sem responsável O&M que o BD já tinha, 11 com status velho, 5 com outra equipe.

O motor lê seis colunas dela: UFV (chave), RESPONSÁVEL O&M (a coluna Responsável da planilha), CIDADE (o feriado
municipal), a primeira coluna com "MWp" no nome (o porte da usina, no RPN), Equipe Cluster (as abas de equipe) e Base
Equipe (o deslocamento, em sombra). O Nexus escreve essas colunas, mais as de identificação, na aba Operacoes_1 e com
os mesmos cabeçalhos: o motor continua sem mudança nenhuma.

O MWp da AUXILIAR ("CAPACIDADE INSTALADA (MWp)") é a POTÊNCIA CONTRATUAL do BD: bateu em 141 das 146 usinas; a
potência real, em 64.
"""
import os
import re
from pathlib import Path

import openpyxl

from ..cadastro.tipos import Legado, marcador

ABA = "Operacoes_1"


def _nome_que_o_motor_le() -> str:
    """O nome do arquivo que o motor do PCM procura (`motor/fonte_bd_api.df_auxiliar`). O motor é cópia idêntica
    do repositório do PCM e não se edita (motor/README.md), e o nome do arquivo leva o de quem montou a planilha:
    é lido de lá, e não repetido aqui, porque o repositório é público e nome de colega fica fora dele (Levi,
    08/10/2026). Se a cópia do motor trocar o nome, este acompanha; sem achar, um nome genérico, e o
    `test_pcm_auxiliar` acusa."""
    texto = (Path(__file__).parent / "motor" / "fonte_bd_api.py").read_text(encoding="utf-8")
    m = re.search(r'BASE_DIR,\s*"(AUXILIAR - [^"]+\.xlsx)"', texto)
    return m.group(1) if m else "AUXILIAR.xlsx"


NOME = _nome_que_o_motor_le()
# A ordem importa: o motor pega a PRIMEIRA coluna com "MWP" no nome e a que tem "RESPONS" e "O&M".
COLUNAS = ("UFV", "CÓDIGO", "STATUS", "CLIENTE", "Equipe Cluster", "RESPONSÁVEL O&M", "CAPACIDADE INSTALADA (MWp)",
           "OPERAÇÃO", "CIDADE", "UF", "Base Equipe", "CLUSTER", "IDUsina")
# Equipe de campo do PCM: UF + região + número ("SP Oeste 03"). Todas as da AUXILIAR seguiam o padrão. No BD, 50 usinas
# em operação têm na Equipe Cluster o próprio nome ou um código local ("Rio do Fogo 1", "MGLGPRT01-CA"): o Fracttal não
# tem equipe com esse nome, e o motor abria uma aba vazia para cada uma (S41 de teste, 02/10/2026: 133 abas em vez de 70).
EQUIPE_PCM = re.compile(r"^[A-Z]{2} [A-Za-zÀ-ú]+ \d{2}$")


class SemCadastro(RuntimeError):
    pass


def servico(config):
    """O serviço do cadastro, montado só com a configuração (a geração roda fora da tela do cadastro)."""
    if config.get("TESTING"):
        s = config.get("NEXUS_PCM_CADASTRO_TESTE")
        if s is None:
            raise SemCadastro("cadastro de teste ausente")
        return s
    from ..cadastro.armazem import ArmazemLocal
    from ..cadastro.cifra import CifraErro, Cofre
    from ..cadastro.servico import Servico
    from ..cadastro.telas import ARMAZEM_PADRAO
    chave = config.get("NEXUS_CHAVE_CADASTRO") or os.environ.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        raise SemCadastro("falta a NEXUS_CHAVE_CADASTRO no .env do Nexus")
    caminho = Path(config.get("NEXUS_ARMAZEM_LOCAL") or ARMAZEM_PADRAO)
    if not caminho.exists():
        raise SemCadastro(f"o cadastro não está nesta máquina ({caminho.name})")
    try:
        return Servico(ArmazemLocal(caminho), Cofre(chave))
    except CifraErro as ex:
        raise SemCadastro(str(ex)) from None


def _texto(v) -> str:
    """Texto como a planilha teria. "N/A" e "N/I" são "não tem" e "não informado": na AUXILIAR eram célula vazia, e o
    motor leria "N/I" como nome de cidade."""
    if v is None:
        return ""
    if isinstance(v, Legado):
        v = v.texto
    s = str(v).strip()
    return "" if marcador(s) else s


def _numero(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def linhas(srv) -> list[dict]:
    out = []
    for u in sorted(srv.registros("usinas"), key=lambda r: r.ordem):
        if u.ilegivel:
            continue
        cliente = _texto(srv.titulo_de("clientes", u.valor("cliente")))
        operacao = _texto(u.valor("nome"))
        equipe = _texto(srv.titulo_de("equipes", u.valor("equipe")))
        out.append({
            "UFV": f"{cliente} - {operacao}" if cliente else operacao,
            "CÓDIGO": _texto(u.valor("codigo")),
            "STATUS": _texto(u.valor("status")),
            "CLIENTE": cliente,
            "Equipe Cluster": equipe if EQUIPE_PCM.match(equipe) else "",
            # sem pessoa, a região da vaga ("NE · Fortaleza-CE e Teresina-PI"): é o que a AUXILIAR do BD_Operações
            # traria (a estrutura de O&M de 10/2026 pôs a região na RESPONSÁVEL O&M onde a vaga de Supervisor de
            # Campo está aberta; o Nexus guarda a pessoa vazia e a região à parte)
            "RESPONSÁVEL O&M": (_texto(srv.titulo_de("pessoas", u.valor("responsavel_om")))
                                or _texto(u.valor("responsavel_om_vaga"))),
            "CAPACIDADE INSTALADA (MWp)": _numero(u.valor("potencia_contratual")),
            "OPERAÇÃO": operacao,
            "CIDADE": _texto(u.valor("cidade")),
            "UF": _texto(u.valor("uf")),
            "Base Equipe": _texto(u.valor("base_equipe")),
            "CLUSTER": _texto(u.valor("cluster")),
            "IDUsina": _texto(u.valor("id_bd")),
        })
    return out


def escrever(srv, destino: Path) -> dict:
    ls = linhas(srv)
    if not ls:
        raise SemCadastro("o cadastro do Nexus não tem usina nenhuma")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = ABA
    ws.append(list(COLUNAS))
    for r in ls:
        ws.append([r[c] if r[c] != "" else None for c in COLUNAS])
    wb.save(destino)
    return {"usinas": len(ls),
            "sem_responsavel": sum(1 for r in ls if not r["RESPONSÁVEL O&M"]),
            "sem_equipe": sum(1 for r in ls if not r["Equipe Cluster"])}


def estado(config) -> dict:
    """O item da lista de conferência: de onde vem e quantas usinas."""
    try:
        srv = servico(config)
        ls = linhas(srv)
    except SemCadastro as ex:
        return {"nome": "Cadastro de usinas (AUXILIAR)", "ok": False, "obrigatorio": True,
                "detalhe": f"o motor lê do cadastro do Nexus, e {ex}"}
    if not ls:
        return {"nome": "Cadastro de usinas (AUXILIAR)", "ok": False, "obrigatorio": True,
                "detalhe": "o cadastro do Nexus não tem usina nenhuma: importe o BD_Operações em Base"}
    sem = sum(1 for r in ls if not r["RESPONSÁVEL O&M"])
    return {"nome": "Cadastro de usinas (AUXILIAR)", "ok": True, "obrigatorio": True,
            "detalhe": f"do cadastro do Nexus: {len(ls)} usinas, {sem} sem responsável O&M"}
