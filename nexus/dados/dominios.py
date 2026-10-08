"""Os domínios dos fatos do Nexus: a lista fechada de valores de cada atributo, num lugar só.

Auditoria Kimball de 08/10/2026 (GR-1, DR-5): a mesma coluna da ronda tinha significados diferentes conforme o livro.
- Vala: o App e o checklist usam {Limpa, Parcial, Obstruída, Não se aplica}; a ronda avulsa (formulário de 07/10) usa
  {Limpa, Parcial, Suja, Não se aplica}. "Suja" não existe no App e não soma com "Obstruída".
- Sensor: no checklist 0 = verificado limpo e vazio = não se aplica; na avulsa 0 = "não marcado", que conta como limpo
  sem ninguém ter olhado.
Daqui em diante o fato importa ESTA definição (`fato_ronda`, `fato_pt`) e a fonte nova também deve importar. Valor fora
da lista vira VAZIO e conta na qualidade: nunca se chuta o vizinho mais parecido (regra 4 do `nexus/dados/CLAUDE.md`).

O mapeamento dos domínios ANTIGOS (o que já está gravado) para o novo está em `MAPA_ANTIGO`, escrito como dado para os
testes provarem cada linha dele.
"""
import re
import unicodedata


def norm(v) -> str:
    """Sem acento, sem caixa, espaço único: "Obstruída " e "obstruida" são o mesmo rótulo."""
    s = unicodedata.normalize("NFKD", "" if v is None else str(v)).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


# ── Ronda ────────────────────────────────────────────────────────────────────────────────────────────────────────
ORIGEM_RONDA = ("app_os", "app_sem_os", "avulsa")
TIPO_RONDA = ("curta", "longa")
# O texto livre ("Criada — Fracttal barrou por excesso de requisições", 15 variações em 08/10) vira 4 situações; o
# motivo longo fica fora do fato (é mensagem de erro, e a API do banco tem leitura aberta).
OS_SITUACAO = ("criada", "em_verificacao", "criada_com_aviso", "nao_criada")
# De onde vieram as respostas do checklist da linha. "app" é o passo 2 (o App manda as respostas no livro de rondas);
# "carga_unica_texto_os" só existe se o Levi aprovar a carga única das respostas lidas do texto da OS (spec, seção 9).
CHECKLIST_FONTE = ("app", "carga_unica_sem_os", "avulsa", "carga_unica_texto_os")

# Vala: um nível ordenado (1 melhor, 3 pior), para tirar média e comparar com a perda. "Não se aplica" (usina sem vala)
# e sem resposta = vazio.
VALA = {"limpa": 1, "parcial": 2, "obstruida": 3}
VALA_ROTULO = {1: "Limpa", 2: "Parcial", 3: "Obstruída"}
VALA_NAO_SE_APLICA = "nao se aplica"

# Sensor (IPOA, GHI, albedômetro): 1 = sujo, 0 = VERIFICADO limpo, vazio = não verificado ou não se aplica.
SENSOR = {"sujo": 1, "limpo": 0}

# As falhas que o App escreve na ronda ("Falhas", separadas por ";"). Medido em 08/10: 6 rótulos, 421 de 867 rondas com
# alguma. Cada uma vira um indicador 1/0 no fato. "evidência incompleta (faltam fotos)" casa pelo começo.
FALHAS = {"ronda longa pendente": "longa_pendente", "item sem foto de evidencia": "item_sem_foto",
          "acao prescrita sem registro": "acao_sem_registro", "checklist incompleto": "checklist_incompleto",
          "sem gps": "sem_gps", "evidencia incompleta": "evidencia_incompleta"}
INDICADORES_FALHA = tuple(FALHAS.values())

# ── PT ───────────────────────────────────────────────────────────────────────────────────────────────────────────
# "vencida" entra porque a tela de PT do Nexus já trata a PT vencida (nexus/torres/campo SITUACAO_PT): é uma PT que teve
# o De acordo e passou do prazo. Deixar fora apagaria uma situação que o App escreve.
PT_SITUACAO = ("aguardando", "de_acordo", "negada", "vencida")
PT_DECIDIDAS = ("de_acordo", "negada", "vencida")
PT_PARADA_MIN = 120          # o mesmo limite da tela (nexus/campo/visao.PT_PARADA_MIN): esperando há mais de 2 h

# ── O que já está gravado, traduzido para o domínio novo (documentação viva: os testes leem daqui) ───────────────────
MAPA_ANTIGO = {
    "vala": {
        # App (texto da OS) e checklist da carga única de 06/10 (`nexus_rondas_checklist`)
        "app_e_checklist": {"Limpa": 1, "Parcial": 2, "Obstruída": 3, "Não se aplica": None, "": None},
        # formulário da avulsa de 07/10 (livro ainda com 0 linhas): "Suja" não tem par no App -> vazio até o Levi decidir
        "avulsa_07_10": {"Limpa": 1, "Parcial": 2, "Suja": None, "Não se aplica": None, "": None},
    },
    "sensor": {
        # checklist: já 1/0/vazio com o significado certo
        "checklist": {1: 1, 0: 0, None: None, "Sujo": 1, "Limpo": 0, "Não se aplica": None},
        # avulsa de 07/10: grava int(marcado). 0 = não marcado, que NÃO é limpo verificado -> vazio
        "avulsa_07_10": {1: 1, 0: None, None: None},
    },
}


def vala(v):
    """"Obstruída" -> 3; "Não se aplica", vazio e qualquer outro texto ("Suja") -> None."""
    return VALA.get(norm(v))


def vala_fora(v) -> bool:
    """O texto veio preenchido e não é do domínio nem "Não se aplica" (ex.: "Suja"): conta na qualidade."""
    n = norm(v)
    return bool(n) and n not in VALA and n != VALA_NAO_SE_APLICA


def sensor(v):
    """Sensor no domínio novo: "Sujo"/1 -> 1, "Limpo"/0 -> 0; "Não se aplica", vazio e o resto -> None. Vale para o
    checklist (que já gravou 1/0 com 0 = limpo verificado)."""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(v) if v in (0, 1) else None
    n = norm(v)
    if n in SENSOR:
        return SENSOR[n]
    return {"1": 1, "0": 0, "1.0": 1, "0.0": 0}.get(n)


def sensor_avulsa(v):
    """A avulsa: texto do domínio ("Sujo", "Limpo") quando o formulário ganhar três estados; o 1/0 do formulário de 07/10
    vale só no 1 (0 = não marcado, não verificado)."""
    if isinstance(v, str) and norm(v) in SENSOR:
        return SENSOR[norm(v)]
    return 1 if sensor(v) == 1 else None


def nivel(v, maximo=5):
    """Sujidade e vegetação: 1 a 5; outro valor = vazio."""
    try:
        i = int(round(float(v)))
    except (TypeError, ValueError):
        return None
    return i if 1 <= i <= maximo else None


def sim_nao(v):
    """"sim" -> 1, "não" -> 0, vazio -> None (o sombreamento da avulsa)."""
    n = norm(v)
    return 1 if n in ("sim", "1", "true") else (0 if n in ("nao", "0", "false") else None)


def tipo_ronda(v):
    n = norm(v)
    return n if n in TIPO_RONDA else None


def os_situacao(txt):
    """A "Situação da OS" do App -> o domínio. "Criada" sozinho = criada; "Criada — <aviso>" = criada_com_aviso."""
    n = norm(txt)
    if not n:
        return None
    if n.startswith("nao criada"):
        return "nao_criada"
    if n.startswith("em verificacao"):
        return "em_verificacao"
    if n == "criada":
        return "criada"
    if n.startswith("criada"):
        return "criada_com_aviso"
    return None


def falhas(txt) -> tuple[set, list]:
    """("Falhas" do App) -> (indicadores presentes, rótulos desconhecidos). Rótulo repetido conta uma vez."""
    achadas, desconhecidas = set(), []
    for parte in str(txt or "").split(";"):
        n = norm(parte)
        if not n:
            continue
        col = next((c for rot, c in FALHAS.items() if n == rot or n.startswith(rot + " ") or n.startswith(rot + "(")),
                   None)
        if col:
            achadas.add(col)
        elif n not in desconhecidas:
            desconhecidas.append(n)
    return achadas, desconhecidas


def pt_situacao(txt):
    """A "Situação" da PT. Vazia = aguardando (como a tela lê, `visao.pts`); fora da lista = None."""
    n = norm(txt).replace(" ", "_")
    if not n:
        return "aguardando"
    return n if n in PT_SITUACAO else None


_CODIGO = re.compile(r"^[a-z0-9_]{1,30}$")


def codigo(v):
    """Valor que o sistema escreve como código curto ("anexada", "Admin"): minúsculo, sem acento; o que não tem forma
    de código (frase, texto livre) = vazio, porque texto livre não entra no fato (regra 8)."""
    n = norm(v).replace(" ", "_")
    return n if _CODIGO.match(n) else None
