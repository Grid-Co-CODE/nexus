"""O que cada alerta quer dizer, em linguagem de quem não é da meteorologia (09/10/2026).

Levi, 09/10/2026, olhando a tela Clima e risco: "estou achando um pouco limitado e pouco entendível para um leigo, deixe mais
didático". A tela dizia o QUE havia ("Tempestade · vermelho", "risco de fogo 1,00") e não o que isso quer dizer para a usina nem
o que conferir. Aqui mora esse texto, uma vez só: a lista, a página da usina e o mapa leem daqui.

Regras do texto: frases curtas; o que pode acontecer NA USINA (equipamento, acesso, vegetação) e o que CONFERIR, nunca uma
ordem de serviço nem um procedimento de segurança (esses são do HSEQ e do supervisor); nada de cor como nome de nível (a cor
vai na tela; a palavra do INMET vai no texto). Evento que o INMET publicar e que não está aqui cai na explicação genérica, e a
tela continua mostrando o nome dele: nada some.
"""
from ...cadastro.servico import chave_texto
from . import fontes as F

# Os três níveis do INMET (a severidade que vem no aviso), do mais leve ao mais grave.
NIVEIS_INMET = (
    {"nivel": 1, "nome": "Perigo Potencial", "quer_dizer": "pode acontecer algo; vale acompanhar"},
    {"nivel": 2, "nome": "Perigo", "quer_dizer": "é provável que cause estrago"},
    {"nivel": 3, "nome": "Grande Perigo", "quer_dizer": "o nível mais alto: risco de grande estrago"},
)
QUER_DIZER_NIVEL = {n["nivel"]: n["quer_dizer"] for n in NIVEIS_INMET}

# O evento do aviso (pelo nome do INMET, sem acento e sem caixa): o que é, o que pode acontecer na usina, o que conferir.
_EVENTOS = {
    "Tempestade": (
        "Chuva forte com raios e rajadas de vento em pouco tempo; às vezes granizo.",
        "Raio nos equipamentos, inversores e proteções desarmando, vento forçando estruturas e módulos.",
        "Depois que passar: inversores e proteções que desarmaram, módulos, estruturas e cerca."),
    "Chuvas Intensas": (
        "Muita chuva em poucas horas.",
        "Alagamento do acesso e dos eletrocentros, erosão nas bases das estruturas e nas valas de cabos.",
        "Drenagem, valas de cabos, bases das estruturas e o acesso à usina."),
    "Acumulado de Chuva": (
        "Muita chuva somada ao longo de dias.",
        "Solo encharcado, erosão, talude cedendo e acesso difícil.",
        "Drenagem, taludes, valas de cabos e o acesso à usina."),
    "Vendaval": (
        "Vento forte por horas.",
        "Esforço nas estruturas e nos trackers, módulo ou cobertura soltando, objetos jogados contra os módulos.",
        "Se os trackers foram para a posição de proteção contra vento; depois, fixações, estruturas e módulos."),
    "Ventos Costeiros": (
        "Vento forte no litoral.",
        "Esforço nas estruturas e nos trackers das usinas perto do mar.",
        "Fixações, estruturas e trackers."),
    "Granizo": (
        "Pedras de gelo caindo com a chuva.",
        "Vidro de módulo trincado ou quebrado.",
        "Trincas nos módulos e a geração das strings no dia seguinte."),
    "Baixa Umidade": (
        "Ar muito seco.",
        "A vegetação seca pega fogo com facilidade, e a poeira suja os módulos mais rápido.",
        "Roçagem e aceiro em dia, extintores no lugar e a sujidade dos módulos."),
    "Onda de Calor": (
        "Temperatura bem acima do normal por vários dias.",
        "Módulos e inversores quentes geram menos, e o inversor pode limitar a potência.",
        "Ventilação dos inversores e eletrocentros e quedas de geração nas horas mais quentes."),
    "Declínio de Temperatura": (
        "Queda forte da temperatura.",
        "Pouco efeito na geração.",
        "Nada específico na usina."),
    "Geada": (
        "Gelo fino sobre as superfícies de madrugada.",
        "Módulos cobertos de gelo geram menos até o gelo derreter.",
        "A geração do começo da manhã; ela volta quando o gelo derrete."),
}
EVENTOS = {chave_texto(nome): {"o_que_e": a, "na_usina": b, "conferir": c} for nome, (a, b, c) in _EVENTOS.items()}
GENERICO = {"o_que_e": f"Aviso meteorológico do {F.extenso('inmet')} para a região da usina.",
            "na_usina": f"Depende do evento: veja o aviso completo no portal de alertas do {F.extenso('inmet')}.",
            "conferir": "A usina, quando o aviso terminar."}

FOCO = {"o_que_e": "Um satélite viu fogo num ponto a até 5 km da usina na última hora. Nem todo foco é incêndio, mas fogo perto "
                   "é risco real.",
        "na_usina": "O fogo na vegetação pode chegar aos módulos, aos cabos e à cerca.",
        "conferir": "Quem estiver perto confere o local; aceiro, roçagem e extintores."}
RISCO_FOGO = {"o_que_e": f"Previsão do {F.extenso('inpe')}, de 0 a 1, de quanto a vegetação em volta da usina pode pegar "
                         "fogo, pelo tempo seco, pelo calor e pelos dias sem chuva. Alto a partir de 0,70; crítico acima de 0,95.",
              "na_usina": "Com risco alto ou crítico, qualquer faísca ou queimada vizinha pode virar incêndio perto dos módulos.",
              "conferir": "Roçagem e aceiro em dia e extintores no lugar."}

# Os três níveis da USINA, na ordem da tela: o que quer dizer e o que fazer com ele.
COMO_LER = (
    {"id": "agir", "rotulo": "Agir agora",
     "quer_dizer": f"Fogo a até 5 km da usina, ou aviso forte do {F.extenso('inmet')}: Grande Perigo de qualquer tipo, ou "
                   "Perigo de tempestade, chuva forte, vento ou granizo.",
     "fazer": "Avisar o supervisor da região e conferir a usina assim que der."},
    {"id": "atencao", "rotulo": "Atenção",
     "quer_dizer": f"Algum outro aviso do {F.extenso('inmet')} (agora ou nos próximos dias) ou risco de fogo alto ou "
                   "crítico em algum dos próximos quatro dias.",
     "fazer": "Acompanhar; nada a fazer agora."},
    {"id": "sem", "rotulo": "Sem alerta",
     "quer_dizer": "Nenhum aviso, nenhum fogo perto e risco de fogo abaixo de alto, com as três fontes lidas.",
     "fazer": "Nada."},
)


def evento(nome) -> dict:
    """O texto do evento do INMET (`o_que_e`, `na_usina`, `conferir`); o genérico se o nome não é conhecido."""
    return EVENTOS.get(chave_texto(nome), GENERICO)


def conhecido(nome) -> bool:
    return chave_texto(nome) in EVENTOS


def nome_amigavel(nome) -> str:
    """"Chuvas Intensas" -> "Chuvas intensas": o INMET escreve cada palavra com maiúscula, e no meio de uma frase isso parece
    nome próprio."""
    s = " ".join(str(nome or "").split())
    return s[:1].upper() + s[1:].lower() if s else s
