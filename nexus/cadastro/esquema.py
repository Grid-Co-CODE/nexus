"""O esquema do cadastro: cada campo do BD_Operações declarado UMA vez (Levi, 29/09/2026: "tudo o que é editado
no BD_Operações poderá ser editado também").

As telas, a validação, a cifra e a importação saem daqui. Campo novo é uma linha nesta lista.

modo:
- "digitado": a pessoa digita.
- "automatico": o Nexus calcula (era fórmula no Excel), mas a pessoa pode sobrepor, como fazia digitando por
  cima da fórmula (76 técnicos, 48 eletricistas, 55 mantenedores estavam digitados na aba Operações).
- "calculado": só o Nexus calcula (a receita contratual, a localização, as colunas de cidade das pessoas).

sensivel: vai CIFRADO para o armazém e aparece mascarado até a pessoa pedir para ver. Nas pessoas, o registro
inteiro é cifrado (quase todo campo identifica alguém); o `sensivel` ali só decide o que a tela mascara.
mascarar=False: cifrado no armazém, mas VISÍVEL na tela. Latitude e longitude (Levi, 29/09: "deve ter a
informação da latitude e longitude"): quem usa o cadastro precisa ver; quem lê a API por outro sistema, não. Na lista, ficam
fora das colunas padrão (30/09: "fica só na retaguarda"); o botão Colunas traz de volta.

IDs: número simples por cadastro, 1, 2, 3 (Levi, 29/09: "reduza as caracteres do ID"). O IDUsina do Excel
("UFV-001") fica guardado no campo "ID do BD": é por ele que a importação casa a usina entre uma carga e outra.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Campo:
    id: str
    rotulo: str
    tipo: str = "texto"
    secao: str = ""
    coluna_bd: str | None = None       # cabeçalho no BD_Operações (casado sem acento e sem maiúscula)
    lista: str | None = None           # tipo "lista": id da lista; tipo "ref": id da entidade
    modo: str = "digitado"
    obrigatorio: bool = False
    sensivel: bool = False
    unico: bool = False
    ajuda: str = ""
    na_lista: bool = False             # aparece como coluna na tela de lista
    mascarar: bool | None = None       # None = segue o `sensivel`; False = cifrado, mas visível na tela

    @property
    def editavel(self) -> bool:
        return self.modo in ("digitado", "automatico")

    @property
    def oculto(self) -> bool:
        """Mascarado na tela até alguém pedir para ver (e fora do formulário até lá)."""
        return self.sensivel and self.mascarar is not False


@dataclass(frozen=True)
class Secao:
    id: str
    nome: str


@dataclass(frozen=True)
class Entidade:
    id: str
    singular: str
    plural: str
    aba_bd: str | None
    prefixo_id: str
    digitos_id: int
    campos: tuple[Campo, ...]
    secoes: tuple[Secao, ...]
    cifra_registro: bool = False       # pessoas: o registro inteiro vai cifrado
    campo_titulo: str = "nome"
    torre: str = "base"
    rota_lista: str = ""
    rota_ficha: str = ""

    def campo(self, cid: str) -> Campo:
        return self._por_id[cid]

    @property
    def _por_id(self) -> dict:
        return {c.id: c for c in self.campos}

    def tem(self, cid: str) -> bool:
        return cid in self._por_id


def _c(*a, **k):
    return Campo(*a, **k)


# ── USINAS (aba Operações, 74 colunas) ─────────────────────────────────────
_S_USINA = (
    Secao("identificacao", "Identificação"),
    Secao("contrato", "Contrato e receita"),
    Secao("equipe", "Equipe e contatos"),
    Secao("tecnica", "Técnica"),
    Secao("localizacao", "Localização"),
    Secao("cmms", "CMMS e acessos"),
    Secao("seguranca", "Segurança e internet"),
)

USINAS = Entidade(
    id="usinas", singular="usina", plural="usinas", aba_bd="Operações", prefixo_id="", digitos_id=0,
    torre="base", rota_lista="/t/base/registro-mestre", rota_ficha="/t/base/usina/",
    secoes=_S_USINA,
    campos=(
        _c("nome", "Operação", secao="identificacao", coluna_bd="OPERAÇÃO", obrigatorio=True, na_lista=True),
        _c("codigo", "Código", secao="identificacao", coluna_bd="CÓDIGO", unico=True, na_lista=True),
        _c("id_bd", "ID do BD", secao="identificacao", coluna_bd="IDUsina", unico=True, na_lista=True,
           ajuda="O IDUsina da planilha (UFV-001). É por ele que a importação reconhece a usina."),
        _c("status", "Status", "lista", "identificacao", "STATUS", lista="status_usina", obrigatorio=True,
           na_lista=True),
        _c("cliente", "Cliente", "ref", "identificacao", "CLIENTE", lista="clientes", na_lista=True,
           ajuda="Cadastro próprio, com ID: separa usinas de mesmo nome e clientes diferentes."),
        _c("tipologia", "Tipologia", "lista", "identificacao", "TIPOLOGIA", lista="tipologia"),
        _c("faixa_potencia", "Faixa de potência", "lista", "identificacao", "FAIXA POTÊNCIA", lista="faixa_potencia"),
        _c("nome_spe", "Nome SPE", secao="identificacao", coluna_bd="Nome SPE"),
        _c("cnpj", "CNPJ", secao="identificacao", coluna_bd="CNPJ", sensivel=True),

        _c("contrato_assinado", "Contrato assinado", "simnao", "contrato", "Contrato Assinado"),
        _c("prazo_meses", "Prazo contratual (meses)", "inteiro", "contrato", "Prazo Contratual (Meses)"),
        _c("preco_mwp", "Preço por MWp (mensal)", "moeda", "contrato", sensivel=True,
           ajuda="Preenchido, a receita mensal é calculada: preço × potência contratual. Era a fórmula do "
                 "Excel em 70 usinas."),
        _c("receita_mensal", "Receita mensal", "moeda", "contrato", "Receita Mensal", modo="automatico",
           sensivel=True, ajuda="Vazia, sai do preço por MWp × potência contratual."),
        _c("receita_contratual", "Receita contratual", "moeda", "contrato", "Receita Contratual", modo="calculado",
           sensivel=True, ajuda="Receita mensal × prazo contratual."),
        _c("cnpj_faturamento", "CNPJ de faturamento", secao="contrato", coluna_bd="CNPJ de Faturamento", sensivel=True),
        _c("gestor_contrato", "Gestor de contrato", "ref", "contrato", "Gestor de Contrato", lista="pessoas"),
        _c("data_mobilizacao", "Data de mobilização", "data", "contrato", "Data Mobilização"),
        _c("conta_contrato", "Conta contrato", "texto_longo", "contrato", "Conta Contrato", sensivel=True),
        _c("instalacao", "Instalação (UC)", "texto_longo", "contrato", "Instalação", sensivel=True),
        _c("ucs", "UCs", "inteiro", "contrato", "Ucs"),
        _c("concessionaria", "Concessionária", "sugestao", "contrato", "CONCESSIONÁRIA"),

        _c("equipe", "Equipe", "ref", "equipe", "Equipe Cluster", lista="equipes", na_lista=True),
        _c("cluster", "Cluster", "lista", "equipe", "CLUSTER", lista="cluster"),
        _c("regiao", "Região", "lista", "equipe", "REGIÃO", lista="regiao"),
        _c("base_equipe", "Base da equipe", "texto", "equipe", "Base Equipe", modo="automatico",
           ajuda="Vazia, é a cidade da primeira pessoa ativa da equipe."),
        _c("responsavel_om", "Responsável O&M", "ref", "equipe", "RESPONSÁVEL O&M", lista="pessoas", na_lista=True),
        _c("tecnico_om", "Técnico O&M", "ref", "equipe", "Técnico O&M", lista="pessoas", modo="automatico",
           ajuda="Automático: o técnico ativo da equipe."),
        _c("contato_tecnico", "Contato do técnico", "telefone", "equipe", "Contato Técnico", modo="automatico",
           sensivel=True, ajuda="Automático: telefone corporativo do técnico (ou o pessoal)."),
        _c("eletricista_om", "Eletricista O&M", "ref", "equipe", "Eletricista O&M", lista="pessoas",
           modo="automatico", ajuda="Automático: o eletricista ativo da equipe."),
        _c("contato_eletricista", "Contato do eletricista", "telefone", "equipe", "Contato Eletricista",
           modo="automatico", sensivel=True),
        _c("mantenedor_om", "Mantenedor O&M", "ref", "equipe", "Mantenedor O&M", lista="pessoas", modo="automatico",
           ajuda="Automático: o mantenedor ativo da equipe."),
        _c("contato_mantenedor", "Contato do mantenedor", "telefone", "equipe", "Contato Mantenedor",
           modo="automatico", sensivel=True),

        _c("potencia_contratual", "Potência contratual (MWp)", "numero", "tecnica", "POTÊNCIA CONTRATUAL (MWp)",
           na_lista=True),
        _c("potencia_real", "Potência real (MWp)", "numero", "tecnica", "POTÊNCIA REAL (MWp)"),
        _c("capacidade_instalada", "Capacidade instalada (MW)", "numero", "tecnica", "CAPACIDADE INSTALADA (MW)"),
        _c("area_instalada", "Área instalada (ha)", "numero", "tecnica", "ÁREA INSTALADA (ha)"),
        _c("n_inversores", "Nº de inversores", "inteiro", "tecnica", "Nº INVERSORES"),
        _c("fabricante_inversores", "Fabricante dos inversores", "sugestao", "tecnica", "FABRICANTE INVERSORES"),
        _c("modelo_inversores", "Modelo dos inversores", "sugestao", "tecnica", "MODELO INVERSORES"),
        _c("potencia_inversores", "Potência dos inversores", "texto", "tecnica", "POTÊNCIA INVERSORES"),
        _c("n_modulos", "Nº de módulos", "inteiro", "tecnica", "NÚMERO MÓDULOS"),
        _c("fabricante_modulos", "Fabricante dos módulos", "sugestao", "tecnica", "FABRICANTE MÓDULOS"),
        _c("modelo_modulo", "Modelo do módulo", "sugestao", "tecnica", "MODELO MÓDULO"),
        _c("potencia_modulos", "Potência dos módulos (Wp)", "texto", "tecnica", "POTÊNCIA MÓDULOS (Wp)"),
        _c("fabricante_tracker", "Fabricante do tracker", "sugestao", "tecnica", "FABRICANTE TRACKER"),
        _c("qtd_tcu_motor", "Qtd. de TCU e motor", "inteiro", "tecnica", "QTD TCU E MOTOR"),
        _c("modelo_tracker", "Modelo do tracker", "sugestao", "tecnica", "MODELO TRACKER"),
        _c("n_cabine", "Nº de cabines", "inteiro", "tecnica", "Nº Cabine"),
        _c("n_skid", "Nº de SKID", "inteiro", "tecnica", "Nº SKID"),
        _c("n_qgbt", "Nº de QGBT", "inteiro", "tecnica", "Nº QGBT"),
        _c("n_transformador", "Nº de transformadores", "inteiro", "tecnica", "Nº Transformador"),
        _c("tipo_transformador", "Tipo do transformador", "sugestao", "tecnica", "Tipo do Transformador"),
        _c("tensao_linha", "Tensão de linha (kV)", "texto", "tecnica", "TENSÃO DE LINHA (kV)"),
        _c("tr_aux", "TR auxiliar", "texto", "tecnica", "TR AUX."),

        _c("cidade", "Cidade", secao="localizacao", coluna_bd="CIDADE", na_lista=True),
        _c("uf", "UF", "lista", "localizacao", "UF", lista="uf", na_lista=True),
        _c("pais", "País", "sugestao", "localizacao", "PAÍS"),
        _c("localizacao", "Localização", "texto", "localizacao", "LOCALIZAÇÃO", modo="calculado",
           ajuda="Cidade, UF e país, como a fórmula do Excel."),
        _c("endereco", "Endereço", "texto_longo", "localizacao", "ENDEREÇO", sensivel=True),
        _c("cep", "CEP", secao="localizacao", coluna_bd="CEP", sensivel=True),
        _c("latitude", "Latitude", "coordenada", "localizacao", "LATITUDE", sensivel=True, mascarar=False),
        _c("longitude", "Longitude", "coordenada", "localizacao", "LONGITUDE", sensivel=True, mascarar=False),
        _c("maps", "Link do mapa", "url", "localizacao", "Maps", sensivel=True),

        _c("codigo_instalacao_cmms", "Código de instalação (CMMS)", secao="cmms", coluna_bd="Código Instalação (CMMS)"),
        _c("codigo_equipamento_cmms", "Código de equipamento (CMMS)", secao="cmms",
           coluna_bd="Código Equipamento (CMMS)"),
        _c("acesso_comando_remoto", "Acesso para comando remoto", "simnao", "cmms", "Acesso para Comando Remoto"),
        _c("acesso_visualizacao", "Acesso para visualização", "simnao", "cmms",
           "Acesso para Visualização (Site de Monitoramento)"),
        _c("databook", "Databook", "simnao", "cmms", "Databook"),

        _c("empresa_seguranca_local", "Empresa de segurança local", secao="seguranca",
           coluna_bd="Empresa Segurança Local"),
        _c("contato_seguranca_local", "Contato da segurança local", secao="seguranca",
           coluna_bd="Contato Segurança Local", sensivel=True),
        _c("empresa_seguranca_remota", "Empresa de segurança remota", secao="seguranca",
           coluna_bd="Empresa Segurança Remota"),
        _c("contato_seguranca_remota", "Contato da segurança remota", secao="seguranca",
           coluna_bd="Contato Segurança Remota", sensivel=True),
        _c("prestador_internet", "Prestador de internet", secao="seguranca", coluna_bd="Prestador de Serviço - Internet"),
        _c("contato_internet", "Contato da internet", secao="seguranca", coluna_bd="Contato - Internet", sensivel=True),
    ),
)

# ── PESSOAS (aba Relação Geral Colaboradores + supervisores e gestores das listas do Auxiliar) ─
_S_PESSOA = (
    Secao("identificacao", "Identificação"),
    Secao("contato", "Contato"),
    Secao("documentos", "Documentos e endereço"),
    Secao("calculados", "Calculados"),
)

PESSOAS = Entidade(
    id="pessoas", singular="colaborador", plural="colaboradores", aba_bd="Relação Geral Colaboradores",
    prefixo_id="", digitos_id=0, cifra_registro=True, torre="pessoas",
    rota_lista="/t/pessoas/colaboradores", rota_ficha="/t/pessoas/colaborador/",
    secoes=_S_PESSOA,
    campos=(
        _c("nome", "Nome", secao="identificacao", coluna_bd="Nome", obrigatorio=True),
        _c("nome_padrao", "Nome padrão", secao="identificacao", coluna_bd="Nome Padrão", modo="automatico",
           na_lista=True, ajuda="Automático: primeiro e último nome."),
        _c("vinculo", "Vínculo", "lista", "identificacao", lista="vinculo", obrigatorio=True, na_lista=True,
           ajuda="Supervisores e gestores de contrato vinham só das listas do Auxiliar."),
        _c("cargo", "Cargo", "lista", "identificacao", "Cargo", lista="cargos", na_lista=True),
        _c("equipe", "Equipe", "ref", "identificacao", "Cluster", lista="equipes", na_lista=True),
        _c("status", "Status de contratação", "lista", "identificacao", "Status de Contratação",
           lista="status_contratacao", na_lista=True),
        _c("data_admissao", "Data de admissão", "data", "identificacao", "Data de Admissão", sensivel=True),
        _c("cliente", "Cliente", "sugestao", "identificacao", "Cliente"),
        _c("supervisor", "Supervisor", "ref", "identificacao", "Supervisor", lista="pessoas", modo="automatico",
           na_lista=True, ajuda="Automático: o responsável O&M das usinas da equipe."),

        _c("email", "E-mail", "email", "contato", "email", unico=True),
        _c("telefone_corporativo", "Telefone corporativo", "telefone", "contato", "Telefone Corporativo",
           sensivel=True),
        _c("telefone_pessoal", "Telefone pessoal", "telefone", "contato", "Telefone Pessoal", sensivel=True),

        _c("cpf", "CPF", "cpf", "documentos", "CPF", sensivel=True, unico=True),
        _c("endereco", "Endereço", "texto_longo", "documentos", "endereco", sensivel=True),
        _c("cidade", "Cidade", secao="documentos", coluna_bd="Cidade"),

        _c("cidade_uf_endereco", "Cidade/UF (do endereço)", secao="calculados", coluna_bd="Cidade/UF (do endereço)",
           modo="calculado"),
        _c("cidade_uf_fallback", "Cidade/UF (reserva)", secao="calculados", coluna_bd="Cidade/UF (fallback)",
           modo="calculado"),
        _c("cidade_estado_base", "Cidade/Estado (base da equipe)", secao="calculados",
           coluna_bd="Cidade/Estado (Base Equipe)", modo="calculado"),
    ),
)

# ── EQUIPES (a "Equipe Cluster" das usinas e o "Cluster" das pessoas, agora com cadastro próprio) ──
EQUIPES = Entidade(
    id="equipes", singular="equipe", plural="equipes", aba_bd=None, prefixo_id="", digitos_id=0,
    torre="base", rota_lista="/t/base/equipes", rota_ficha="/t/base/equipe/",
    secoes=(Secao("identificacao", "Identificação"),),
    campos=(
        _c("nome", "Nome", secao="identificacao", obrigatorio=True, unico=True, na_lista=True),
        _c("observacao", "Observação", "texto_longo", "identificacao"),
    ),
)

# ── CLIENTES (a coluna CLIENTE da aba Operações, agora com cadastro e ID) ─────
CLIENTES = Entidade(
    id="clientes", singular="cliente", plural="clientes", aba_bd=None, prefixo_id="", digitos_id=0,
    torre="base", rota_lista="/t/base/clientes", rota_ficha="/t/base/cliente/",
    secoes=(Secao("identificacao", "Identificação"),),
    campos=(
        _c("nome", "Nome", secao="identificacao", obrigatorio=True, unico=True, na_lista=True),
        _c("observacao", "Observação", "texto_longo", "identificacao"),
    ),
)

ENTIDADES: dict[str, Entidade] = {e.id: e for e in (USINAS, CLIENTES, PESSOAS, EQUIPES)}

# ── LISTAS (Auxiliar, Parametros e as listas suspensas) ─────────────────────
LISTAS: dict[str, str] = {
    "status_usina": "Status da usina",
    "tipologia": "Tipologia",
    "faixa_potencia": "Faixa de potência",
    "cluster": "Cluster",
    "regiao": "Região",
    "uf": "UF",
    "cargos": "Cargos",
    "status_contratacao": "Status de contratação",
    "vinculo": "Vínculo",
    "estrutura_zeladoria": "Estrutura da equipe de zeladoria",
    "estrutura_mpa_mps": "Estrutura da equipe MPA/MPS",
    "status_operacional": "Status operacional (colaboradores locais)",
    "modalidade": "Modalidade (colaboradores locais)",
    "status_contrato": "Status do contrato (colaboradores locais)",
    "filtro_locais": "Filtro dos locais",
}
