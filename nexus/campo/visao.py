"""A visão do Nexus para o Campo · App: as telas que antes abriam o painel do App (no Azure) numa moldura, agora com dado
nosso (Levi, 05/10/2026: "quero parar de referenciar o Azure e ter uma visão nossa!").

Tudo vem do banco (API db_performace), nunca do App nem do Azure:
- os livros que o próprio App grava de hora em hora (aos :25): `fechamentos_app_campo`, `pt_app_campo`,
  `zeladoria_app_campo`, `decisoes_app_campo` e `rondas_app_campo`;
- o cadastro do Nexus (`cadastro_nexus`): as usinas MOBILIZADAS (status OPERAÇÃO e data de mobilização já passada) e a
  equipe, o estado e a cidade de cada uma. A usina que o App escreve liga ao `usina_id` pelo mesmo `Ligador` da camada
  de dados (de-para do Fracttal; código do ativo de reserva).
A pessoa vem do App como código do e-mail (HMAC): o nome sai do cadastro do App (`identidades.json`), na hora, no
"Nome padrão" do cadastro (primeiro e último nome). Cópia de 5 min por tela; banco fora do ar = a tela avisa, não some.

Desde 08/10/2026 (passo 4 do Kimball) a contagem e a ligação (usina_id, pessoa_id, data_id) de Rondas, Central de
atenção e PT saem do FATO conformado (`nexus_fatos` · `fato_ronda`, `fato_pt`, `fato_fechamento`); o livro cru só dá o
que o fato não tem (veredito, pendências, observação, horários), juntado pela chave do fato. Ver "Os fatos" abaixo.

As contas são NOSSAS e estão escritas em cada função: quem quiser saber por que um número deu tanto lê aqui.
"""
import collections
import json
import re
import statistics
import time
from datetime import datetime, timedelta, timezone

from flask import current_app

from ..cadastro.calculos import nome_padrao
from ..dados import carga as C
from ..dados import dominios as DOM
from ..dados import fato_pt as FPT
from ..dados import fato_ronda as FR
from ..dados import fatos as D
from ..dados import livros
from . import leitura, livros_app

_BRT = timezone(timedelta(hours=-3))
STATUS_OPERACAO = "OPERAÇÃO"
DIAS_SEM_RONDA_ALERTA = 7        # usina mobilizada sem ronda há 7 dias ou mais = ronda pendente
DIAS_COBERTURA = 14              # janela da cobertura de ronda (a mesma do ranking por região)
PT_PARADA_MIN = DOM.PT_PARADA_MIN  # PT esperando o De acordo há mais de 2 h = parada (o mesmo limite do fato_pt)
PESO_QUALIDADE, PESO_COBERTURA = 0.6, 0.4     # ranking por região, a mesma régua do painel do App
_DATA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")
# Região do Brasil pela UF do cadastro (Levi, 05/10: "Adicione uma coluna de região do Brasil"). Pela UF, e não pela
# coluna `regiao` do cadastro: medido em 05/10, ela tem "Centro Oeste" e "Centro-Oeste" e 2 usinas vazias.
REGIOES = ("Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul")
REGIAO_DA_UF = {**dict.fromkeys(("AC", "AP", "AM", "PA", "RO", "RR", "TO"), "Norte"),
                **dict.fromkeys(("AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"), "Nordeste"),
                **dict.fromkeys(("DF", "GO", "MT", "MS"), "Centro-Oeste"),
                **dict.fromkeys(("ES", "MG", "RJ", "SP"), "Sudeste"),
                **dict.fromkeys(("PR", "RS", "SC"), "Sul")}
SEM_EQUIPE = "Sem equipe"
SEM_SUPERVISOR = "Sem supervisor"
SEM_CLUSTER = "Sem cluster"
CAMPO = "Colaborador de campo"       # o vínculo de quem vai a campo no cadastro (técnico, eletricista, mantenedor)


class SemBanco(RuntimeError):
    pass


_CACHE: dict = {}
TTL_S = 300


_CALCULOS: dict = {}         # chave -> a conta que a gerou (para renovar sem ninguém pedir)
_USADO: dict = {}            # chave -> quando a tela pediu pela última vez
_RENOVANDO: set = set()
_LIVROS: dict = {}           # (livro, aba) -> (quando, linhas): as contas de um mesmo ciclo leem o banco uma vez
LIVRO_S = 120
USO_S = 2 * 3600             # conta que ninguém abriu em 2 h para de ser renovada (volta na próxima visita)
_TRAVA = __import__("threading").Lock()


def _calcular(chave, calcular) -> leitura.Leitura:
    try:
        r = leitura.Leitura(calcular(), time.time())
    except FR.GraoDuplicado:
        # o livro desta hora tem duas linhas para a mesma ronda (ou PT × ativo) e o banco ainda não tem um fato anterior:
        # a tela não mostra número contado em dobro (passo 4, 08/10/2026); a qualidade da carga diz qual chave repetiu
        return leitura.Leitura({}, time.time(), "O livro do App tem a mesma linha duas vezes (chave repetida no fato): "
                                                "a tela não conta em dobro")
    except Exception as e:      # noqa: BLE001 — banco fora do ar: a tela avisa
        return leitura.Leitura({}, time.time(), f"Não consegui ler o banco do Nexus ({type(e).__name__})")
    _CACHE[chave] = r
    return r


def _renovar(chave, app=None):
    """Refaz uma conta em segundo plano (uma por vez por chave); a tela segue com a cópia anterior até lá."""
    with _TRAVA:
        if chave in _RENOVANDO or chave not in _CALCULOS:
            return
        _RENOVANDO.add(chave)
    app = app or current_app._get_current_object()

    def rodar():
        try:
            with app.app_context():
                velha = _CACHE.get(chave)
                nova = _calcular(chave, _CALCULOS[chave])
                if nova.erro and velha:      # banco fora: fica a cópia boa, que a tela já mostra com a hora dela
                    _CACHE[chave] = velha
        finally:
            with _TRAVA:
                _RENOVANDO.discard(chave)
    if app.config.get("TESTING"):
        rodar()
    else:
        __import__("threading").Thread(target=rodar, daemon=True, name="nexus-campo-renovar").start()


def _ler(chave, calcular) -> leitura.Leitura:
    """As contas das telas ficam prontas na memória (Levi, 06/10: "O certo seria carregar e ficar carregado no
    cache!"). Medido em 06/10: frias, Central 4,6 s, Rondas 3,0 s e Ranking 3,1 s (13, 7 e 8 leituras do banco);
    quentes, menos de 0,05 s. A cópia vencida (5 min) volta NA HORA e a conta se refaz em segundo plano; `manter_quente`
    refaz as contas usadas antes de vencerem e aquece as principais ao subir. Só a 1ª visita depois de subir, sem o
    aquecimento, espera a conta. Leitura com erro não fica guardada (a tela diz qual fonte falhou)."""
    _CALCULOS[chave] = calcular
    _USADO[chave] = time.time()
    g = _CACHE.get(chave)
    if g:
        if time.time() - g.lido_em >= TTL_S:
            _renovar(chave)
        return g
    return _calcular(chave, calcular)


def manter_quente(app, intervalo_s: int = 60):
    """Ao subir, faz as contas das telas principais; depois, a cada minuto, refaz as que alguém usou nas últimas 2 h
    e estão a 1 min de vencer. Lê só o banco do Nexus (nada de Fracttal)."""
    def aquecer():
        with app.app_context():
            for f in (rondas, pts, zeladoria, lambda: atencao(), usinas_do_fracttal):
                try:
                    f()
                except Exception:       # noqa: BLE001 — a tela tenta de novo na visita
                    pass

    def laco():
        aquecer()
        while True:
            time.sleep(intervalo_s)
            agora = time.time()
            for chave in list(_CALCULOS):
                g = _CACHE.get(chave)
                if agora - _USADO.get(chave, 0) > USO_S:
                    continue
                if not g or agora - g.lido_em >= TTL_S - intervalo_s:
                    _renovar(chave, app)
    __import__("threading").Thread(target=laco, daemon=True, name="nexus-campo-quente").start()


def _sessao():
    s = current_app.extensions.get("nexus_dados_sessao")
    if s is None and current_app.config.get("TESTING"):
        raise SemBanco("teste sem banco")          # teste nunca vai à rede
    if s is None:
        import requests
        s = requests.Session()
    return s


def _base() -> str:
    from ..cadastro.ligacoes import BASE_API
    return (current_app.config.get("GRIDCO_DB_API") or BASE_API).rstrip("/")


def _livro(nome, aba=None) -> list[dict]:
    """Um livro do banco; o mesmo livro pedido por várias contas no mesmo ciclo é lido uma vez (2 min)."""
    chave = (nome, aba)
    g = _LIVROS.get(chave)
    if g and time.time() - g[0] < LIVRO_S:
        return g[1]
    linhas = livros.ler(_base(), _sessao(), nome, aba)
    _LIVROS[chave] = (time.time(), linhas)
    return linhas


def _agora() -> datetime:
    return datetime.now(_BRT)


def _dt(iso) -> datetime | None:
    s = str(iso or "").strip().replace("Z", "+00:00")
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=_BRT)).astimezone(_BRT)


def _dia(iso) -> str:
    d = _dt(iso)
    return d.date().isoformat() if d else str(iso or "")[:10]


def _sim(v) -> bool:
    return str(v or "").strip().lower() in ("sim", "true", "1")


def _int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def _norm_nome(s) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def supervisor_da_pessoa(email: str, nome: str = "") -> str:
    """Para o login pelo Fracttal (06/10/2026): o nome do supervisor que entrou, como os filtros mostram; vazio se ele
    não é supervisor no cadastro (ou sem a chave do cadastro)."""
    return _Base().supervisor_da_pessoa(email, nome)


def nome_curto(nome) -> str:
    """O "Nome padrão" do cadastro (primeiro e último nome): Levi, 05/10: "tem que ter o nome resumido do técnico"."""
    s = " ".join(str(nome or "").split())
    return str(nome_padrao(s)) if " " in s else s


def _quem() -> dict:
    """{código do App: (e-mail, nome)}: o cadastro do App, na hora."""
    try:
        return livros_app.pessoas_por_codigo(current_app.config.get("NEXUS_PESSOA_HMAC"))
    except Exception:       # noqa: BLE001 — sem o cadastro do App, sai sem nome
        return {}


def _codigo(codigo) -> str:
    return str(codigo or "").split(";")[0].strip()


def _nome(quem: dict, codigo) -> str:
    """O nome resumido de quem o App mandou como código (vários e-mails: o primeiro)."""
    c = _codigo(codigo)
    return nome_curto((quem.get(c) or ("", ""))[1]) if c else ""


def _mobilizada(u: dict, hoje: str) -> bool:
    """Mobilizada = OPERAÇÃO no cadastro e com a data de mobilização já passada. Medido em 05/10: das 177 em OPERAÇÃO,
    49 não têm data de mobilização e NENHUMA delas teve ronda pelo App; as 107 com ronda têm a data (Levi: "tem usina
    que nem mobilizada está")."""
    d = str(u.get("data_mobilizacao") or "").strip()
    return (str(u.get("status") or "").strip().upper() == STATUS_OPERACAO
            and str(u.get("excluido") or "").strip().lower() != "sim"
            and bool(_DATA_ISO.match(d)) and d[:10] <= hoje)


def nome_cluster(c) -> str:
    """O cluster do cadastro com uma grafia só: medido em 05/10, "SP Oeste" e "SP OESTE", "PR Norte" e "PR NORTE",
    "RN OESTE" conviviam (o conserto é no cadastro). A UF fica em maiúsculas; o resto, com a inicial maiúscula."""
    partes = str(c or "").split()
    if not partes:
        return SEM_CLUSTER
    return " ".join([partes[0].upper()] + [x.capitalize() for x in partes[1:]])


class _Base:
    """O cadastro e o ligador, lidos uma vez por cálculo."""

    def __init__(self):
        self.usinas = _livro("cadastro_nexus", "usinas")
        self.equipes = _livro("cadastro_nexus", "equipes")
        self.de_para = _livro("cadastro_nexus", "de_para")
        self.lig = D.Ligador(self.usinas, self.de_para, self.equipes, {})
        self._nomes_lidos, self._nomes_pedidos = {}, set()
        self.nome_equipe = {D._id(e.get("equipe_id")): str(e.get("nome") or "") for e in self.equipes}
        self.por_id = {D._id(u.get("usina_id")): u for u in self.usinas if D._id(u.get("usina_id"))}
        hoje = _agora().date().isoformat()
        self.mobilizadas = {uid: u for uid, u in self.por_id.items() if _mobilizada(u, hoje)}
        # em OPERAÇÃO no cadastro, mas sem data de mobilização (ou com ela no futuro): conserto é no cadastro
        self.sem_mobilizacao = sorted(str(u.get("nome") or "") for uid, u in self.por_id.items()
                                      if uid not in self.mobilizadas
                                      and str(u.get("status") or "").strip().upper() == STATUS_OPERACAO)
        self.pessoas = _livro("cadastro_nexus", "pessoas")
        self.time = self._time(self.pessoas)
        self.nome_cliente = {D._id(c.get("cliente_id")): str(c.get("nome") or "") for c in _livro("cadastro_nexus", "clientes")}

    def _time(self, pessoas) -> dict:
        """{equipe_id: técnicos, cargos, supervisor} pelo cadastro de pessoas (Levi, 05/10: "um número ao lado
        indicando o número de técnicos" e "um filtro para supervisor"). Técnico = colaborador de campo da equipe que
        não está Desligado: medido em 05/10, os 28 sem status no cadastro estão todos em equipes sem nenhum Ativo, e
        contar só os Ativos zerava essas equipes. Supervisor = o `supervisor_id` dos técnicos da equipe (em 05/10, uma
        equipe tem sempre um só); o nome é o "Nome padrão" da ficha dele, decifrado na hora (NEXUS_CHAVE_CADASTRO)."""
        time = {}
        for p in pessoas:
            eid = D._id(p.get("equipe_id"))
            if (not eid or str(p.get("vinculo") or "").strip() != CAMPO
                    or str(p.get("status") or "").strip().lower() == "desligado"
                    or str(p.get("excluido") or "").strip().lower() == "sim"):
                continue
            e = time.setdefault(eid, {"tecnicos": 0, "ativos": 0, "cargos": collections.Counter(),
                                      "supervisores": collections.Counter()})
            e["tecnicos"] += 1
            e["ativos"] += str(p.get("status") or "").strip() == "Ativo"
            e["cargos"][str(p.get("cargo") or "sem cargo").strip()] += 1
            if D._id(p.get("supervisor_id")):
                e["supervisores"][D._id(p.get("supervisor_id"))] += 1
        nomes = self._nomes({s for e in time.values() for s in e["supervisores"]}, pessoas)
        for e in time.values():
            sid = e["supervisores"].most_common(1)[0][0] if e["supervisores"] else None
            e["supervisor"] = nomes.get(sid, f"Supervisor {sid}") if sid else SEM_SUPERVISOR
            e["cargos"] = dict(e["cargos"])
            del e["supervisores"]
        return time

    @staticmethod
    def _nomes(ids, pessoas) -> dict:
        """O "Nome padrão" de cada pessoa pedida, decifrado da ficha. Sem a chave do cadastro, vazio (a tela mostra o
        número da pessoa)."""
        chave = current_app.config.get("NEXUS_CHAVE_CADASTRO")
        if not chave or not ids:
            return {}
        from ..cadastro.cifra import CifraErro, Cofre
        cofre, out = Cofre(chave), {}
        for p in pessoas:
            pid = D._id(p.get("pessoa_id"))
            if pid in ids and p.get("sensivel_cifrado"):
                try:
                    s = json.loads(cofre.decifrar(p["sensivel_cifrado"], f"banco/pessoas/{pid}"))
                except (CifraErro, ValueError):
                    continue
                out[pid] = nome_curto(s.get("nome_padrao") or s.get("nome"))
        return out

    def nomes(self, ids) -> dict:
        """{pessoa_id: "Nome padrão"} das pessoas pedidas, decifradas uma vez por cálculo (rondas, última OS e PT pedem
        as mesmas pessoas). O `pessoa_id` vem do fato: o nome é atributo da pessoa, sai da ficha do cadastro."""
        falta = {i for i in ids if i} - self._nomes_pedidos
        if falta:
            self._nomes_pedidos |= falta
            self._nomes_lidos.update(self._nomes(falta, self.pessoas))
        return self._nomes_lidos

    def supervisor_da_pessoa(self, email: str, nome: str = "") -> str:
        """O nome (como as telas mostram) da pessoa que entrou, se ela é supervisor: pelo e-mail da ficha, ou pelo nome
        quando ele é de UMA pessoa. Medido em 06/10: nenhum dos 10 supervisores tem e-mail no cadastro, então o nome
        decide, comparado de três jeitos (completo, curto e o do e-mail: fulana.souza@ -> "fulana souza") contra o
        nome e o "Nome padrão" da ficha. Supervisor = vínculo "Supervisor" ou o `supervisor_id` de alguém."""
        chave = current_app.config.get("NEXUS_CHAVE_CADASTRO")
        if not chave:
            return ""
        from ..cadastro.cifra import CifraErro, Cofre
        cofre = Cofre(chave)
        sups = {D._id(p.get("supervisor_id")) for p in self.pessoas if D._id(p.get("supervisor_id"))}
        por_email, por_nome = [], []
        alvo_email = str(email or "").strip().lower()
        local = alvo_email.split("@")[0].replace(".", " ").replace("_", " ").replace("-", " ") if "@" in alvo_email else ""
        alvos = {x for x in (_norm_nome(nome), _norm_nome(nome_curto(nome)), _norm_nome(local)) if x}
        for p in self.pessoas:
            pid = D._id(p.get("pessoa_id"))
            if not pid or not p.get("sensivel_cifrado") or str(p.get("excluido") or "").strip().lower() == "sim":
                continue
            try:
                s = json.loads(cofre.decifrar(p["sensivel_cifrado"], f"banco/pessoas/{pid}"))
            except (CifraErro, ValueError):
                continue
            if alvo_email and str(s.get("email") or "").strip().lower() == alvo_email:
                por_email.append((p, s))
            elif alvos & {_norm_nome(x) for x in (s.get("nome"), s.get("nome_padrao"), nome_curto(s.get("nome")),
                                                   nome_curto(s.get("nome_padrao"))) if x}:
                por_nome.append((p, s))
        achados = por_email or por_nome
        if len(achados) != 1:
            return ""
        p, s = achados[0]
        if str(p.get("vinculo") or "").strip() != "Supervisor" and D._id(p.get("pessoa_id")) not in sups:
            return ""
        return nome_curto(s.get("nome_padrao") or s.get("nome"))

    def equipe_da_usina(self, uid) -> str:
        u = self.por_id.get(uid) or {}
        return self.nome_equipe.get(D._id(u.get("equipe_id")), "")

    def time_da_usina(self, uid) -> dict:
        u = self.por_id.get(uid) or {}
        return self.time.get(D._id(u.get("equipe_id"))) or {}

    def times(self) -> dict:
        """{nome da equipe: técnicos, ativos, cargos, supervisor}, para os cartões."""
        return {self.nome_equipe.get(eid, ""): e for eid, e in self.time.items() if self.nome_equipe.get(eid)}

    def onde(self, uid, nome_da_fonte="") -> dict:
        """Usina (o nome do cadastro), equipe, estado, região do Brasil e cidade. Sem ligação: o nome que a fonte
        escreveu, o resto vazio."""
        u = self.por_id.get(uid) or {}
        uf = str(u.get("uf") or "").strip().upper()
        return {"usina": str(u.get("nome") or nome_da_fonte or ""), "uf": uf,
                "regiao_br": REGIAO_DA_UF.get(uf, ""), "cidade": str(u.get("cidade") or "").strip(),
                "equipe": (self.equipe_da_usina(uid) or SEM_EQUIPE) if u else "",
                "supervisor": (self.time_da_usina(uid).get("supervisor") or SEM_SUPERVISOR) if u else "",
                "cliente": self.nome_cliente.get(D._id(u.get("cliente_id")), "") if u else "",
                "cluster": nome_cluster(u.get("cluster")) if u else ""}


# ── Os fatos (passo 4 do Kimball, 08/10/2026) ─────────────────────────────────────────────────────────────────────
# Levi, 08/10: as telas tiram a contagem e a ligação (usina_id, pessoa_id, data_id) do fato conformado, e não refazendo
# a ligação dos livros crus a cada conta. Antes, Rondas, Central e PT ligavam a usina de novo a cada cálculo, com um
# `Ligador` próprio, e liam o checklist da carga única à parte: duas regras para a mesma conta (a da carga e a da tela).
# Agora a tela usa o fato do banco quando ele é da MESMA versão dos livros de origem; senão (o banco ainda não tem o
# fato, ou o App regravou o livro depois da carga, ou a carga falhou nele) monta o fato NA HORA com a mesma função da
# carga (`carga.montar_*`) e diz isso, discretamente, no topo da tela. O que o fato não tem (veredito, pendências, a
# observação, os horários, o texto das falhas) vem do livro cru, juntado pela chave do fato.
LIVRO_FATOS = C.LIVRO_FATOS
# fato -> (aba no banco, livro do App de onde vem, livros que só o Nexus grava e o fato também lê)
FATOS_DA_TELA = {"ronda": ("fato_ronda", C.ORIGEM_RONDAS[0], (C.ORIGEM_AVULSAS[0], C.ORIGEM_CHECKLIST[0])),
                 "pt": ("fato_pt", C.ORIGEM_PT[0], ()),
                 "fechamento": ("fato_fechamento", C.ORIGEM_FECHAMENTOS[0], ())}
_CAB_DO_FATO = {"ronda": FR.CAB_RONDA, "pt": FPT.CAB_PT, "fechamento": D.CAB_FECHAMENTO}
FORCAR_MEMORIA = False          # monta sempre na hora (a medição antes × depois e os testes)


def _ciclo(chave, ler):
    """O mesmo dado pedido por várias contas no mesmo ciclo (2 min) é lido uma vez (como `_livro`)."""
    g = _LIVROS.get(chave)
    if g and time.time() - g[0] < LIVRO_S:
        return g[1]
    v = ler()
    _LIVROS[chave] = (time.time(), v)
    return v


def _atualizados() -> dict:
    """{livro: quando foi gravado} pela API (`/api/workbooks`)."""
    def ler():
        r = _sessao().get(f"{_base()}/api/workbooks", timeout=60)
        r.raise_for_status()
        return {w.get("key"): w.get("updated_at") or w.get("atualizado_em") for w in r.json()}
    return _ciclo(("_workbooks",), ler)


def _abas_dos_fatos() -> dict:
    return _ciclo(("_abas", LIVRO_FATOS), lambda: livros.abas(_base(), _sessao(), LIVRO_FATOS))


def _hm_brt(iso) -> str:
    d = _dt(iso)
    return d.strftime("%d/%m %H:%M") if d else "?"


def _defasado(nome: str, q: dict | None) -> str:
    """Vazio se o fato gravado no banco é da versão dos livros de origem que a API tem agora; senão, o porquê (vai
    para o aviso discreto da tela). A carga grava `origem_atualizada_em` = a hora do livro do App que ela leu."""
    if not q:
        return "o banco ainda não tem"
    if "falhou_nesta_carga" in str(q.get("extra") or ""):
        return f"a carga das {_hm_brt(q.get('gerado_em'))} falhou neste fato"
    _aba, origem, do_nexus = FATOS_DA_TELA[nome]
    quando = _atualizados()
    lido, agora = _dt(q.get("origem_atualizada_em")), _dt(quando.get(origem))
    if not lido or not agora or lido != agora:
        return (f"o banco tem a carga das {_hm_brt(q.get('gerado_em'))}, de antes do livro do App das "
                f"{_hm_brt(quando.get(origem))}")
    gerado = _dt(q.get("gerado_em"))
    for livro in do_nexus:            # a avulsa é lançada no Nexus a qualquer hora: lançamento novo = fato velho
        em = _dt(quando.get(livro))
        if em and (not gerado or em > gerado):
            return f"o banco tem a carga das {_hm_brt(q.get('gerado_em'))}, de antes do último lançamento no Nexus"
    return ""


def _montar_na_hora(nome: str, b: "_Base") -> list[dict]:
    """O fato montado na memória com a MESMA função da carga (`carga.montar_*`), o mesmo `Ligador` e a mesma tradução
    da pessoa (`carga.mapas_das_linhas`). Sem o `equipamento_id` (a tela não usa; montar a dimensão leria 15 abas)."""
    m = _ciclo(("_mapas",), lambda: C.mapas_das_linhas(current_app.config, b.de_para, b.pessoas))
    lig = C.ligador({"usinas": b.usinas, "de_para": b.de_para, "equipes": b.equipes}, m)

    def ler(livro, aba):
        return _livro(livro, aba)
    if nome == "ronda":
        linhas = C.montar_ronda(ler, lig, m)[0]
    elif nome == "pt":
        linhas = C.montar_pt(ler, lig, agora=_agora())[0]
    else:
        linhas = C.montar_fechamento(ler, lig)[0]
    cab = _CAB_DO_FATO[nome]
    return [dict(zip(cab, l)) for l in linhas]


def _fato(nome: str, b: "_Base") -> dict:
    """{"linhas": [{coluna: valor}], "de": "banco" | "memoria", "aviso": texto discreto para a tela}. Uma vez por ciclo.
    As linhas do banco podem vir como texto (a API não garante o tipo): quem usa passa por `D._id`, `D._int`, `D._txt`."""
    def ler():
        aba = FATOS_DA_TELA[nome][0]
        q = None
        try:
            abas = _abas_dos_fatos()
            if aba in abas and "qualidade" in abas:
                q = next((l for l in _livro(LIVRO_FATOS, "qualidade") if D._txt(l.get("fato")) == nome), None)
            motivo = _defasado(nome, q) if aba in abas else "o banco ainda não tem"
        except Exception:       # noqa: BLE001 — sem saber de que versão é o fato do banco, a conta é feita na hora
            abas, motivo = {}, "não consegui conferir o fato do banco"
        if not motivo and not FORCAR_MEMORIA:
            return {"linhas": _livro(LIVRO_FATOS, aba), "de": "banco", "aviso": ""}
        try:
            return {"linhas": _montar_na_hora(nome, b), "de": "memoria",
                    "aviso": f"{aba} calculado na hora; {motivo or 'medição'}"}
        except FR.GraoDuplicado:
            # o grão quebrou no livro desta hora: nunca número contado em dobro. Se o banco tem o da carga anterior, a
            # tela mostra esse e diz; senão, a tela avisa o erro (`_calcular`)
            if aba not in abas:
                raise
            return {"linhas": _livro(LIVRO_FATOS, aba), "de": "banco",
                    "aviso": f"{aba}: o livro desta hora tem linha repetida; a tela mostra a carga das "
                             f"{_hm_brt((q or {}).get('gerado_em'))}"}
    return _ciclo(("_fato", nome), ler)


def _avisos(*nomes) -> dict:
    """{fato: aviso} dos fatos que a conta usou (vazio quando veio do banco)."""
    return {n: (_LIVROS.get(("_fato", n)) or (0, {}))[1].get("aviso", "") for n in nomes}


def _dia_do_fato(v) -> str:
    """`data_id` (AAAAMMDD, o dia de Brasília) -> "AAAA-MM-DD"."""
    i = D._id(v)
    return f"{i // 10000:04d}-{i // 100 % 100:02d}-{i % 100:02d}" if i else ""


# os sensores na ordem em que a tela sempre mostrou (IPOA, albedômetro, GHI)
SENSORES_DA_TELA = (("ipoa_sujo", "IPOA"), ("albedo_sujo", "Albedômetro"), ("ghi_sujo", "GHI"))


def _checklist_do_fato(x) -> dict | None:
    """As respostas que o FATO tem (a carga única das rondas sem OS e a avulsa), no formato do
    `ronda_checklist.ler_nota`. A ronda com OS não tem resposta no fato: vem do texto da OS no Fracttal."""
    if not D._txt(x.get("checklist_fonte")):
        return None
    sombra = D._int(x.get("sombreamento"))
    return {"sujidade": DOM.nivel(x.get("sujidade_nivel")), "vegetacao": DOM.nivel(x.get("vegetacao_nivel")),
            "vala": DOM.VALA_ROTULO.get(D._int(x.get("vala_nivel")), ""),
            "sombreamento": {1: "sim", 0: "não"}.get(sombra, ""),
            "sensores_sujos": [n for c, n in SENSORES_DA_TELA if D._int(x.get(c)) == 1]}


# ── Rondas ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _avulsas_da_tela() -> list[dict]:
    """As linhas válidas do livro da avulsa com o nome e o comentário decifrados (`ronda_avulsa.para_tela`), uma vez por
    ciclo: as rondas avulsas e as validações por foto moram no mesmo livro."""
    from . import ronda_avulsa
    return _ciclo(("_avulsas_tela",), lambda: ronda_avulsa.para_tela(_livro(ronda_avulsa.LIVRO, ronda_avulsa.ABA)))


def resposta_da_ronda(r, respostas: dict) -> dict:
    """As respostas do checklist de UMA ronda: pela OS (o texto da OS no Fracttal) ou, sem OS, as do fato (a carga única
    das rondas sem OS, a avulsa)."""
    return (respostas.get(str(r["os"])) if r.get("os") else None) or r.get("checklist") or {}


def _nome_do_tecnico(r: dict, quem: dict) -> str:
    """O nome que o livro de rondas traz: `Técnico` (o nome em claro, até o App trocar) ou `Técnico (HMAC)` (o código do
    e-mail, a partir do pacote `rondas-tecnico-hmac` do App, 08/10/2026), pela mesma tradução dos outros livros do
    App (`livros_app.nome_do_tecnico`, a mesma da fonte das regras copiadas). As DUAS colunas valem: na troca, uma
    leitura no meio do `sync-xlsx` pode pegar linha com o cabeçalho velho e linha com o novo."""
    return nome_curto(livros_app.nome_do_tecnico(r, quem))


def _rondas_ligadas(b: _Base) -> list[dict]:
    """As rondas pelo fato único de ronda (`fato_ronda`): uma linha por ronda realizada (App com e sem OS, a resposta
    da carga única, a avulsa válida). Do fato: a ronda (`ronda_id`), o dia (`data_id`, dia de Brasília do início), a
    usina (`usina_id`), a pessoa (`pessoa_id`), o tipo, a nota, os trackers, se ficou sem OS e as respostas que o fato
    tem. Do livro cru, pela chave (a ronda do App pelo `Início`, a avulsa pelo `ronda_id` dela): o texto das falhas, a
    situação da OS (o motivo), a região escrita pelo App, o nome e o comentário da avulsa. Equipe, estado, região do
    Brasil, cliente e supervisor são os do cadastro pela usina (Levi, 05/10: nunca a "Região" que o App escreve; o
    `equipe_id` do fato é o papel "registro", a equipe que o App anotou). O nome da pessoa é o "Nome padrão" da ficha
    pelo `pessoa_id`; sem ele, o que o livro traz."""
    f = _fato("ronda", b)
    cru = {D._txt(r.get("Início")): r for r in _livro(*C.ORIGEM_RONDAS)}
    avulsas = {FR.chave("avulsa", a.get("id")): a for a in _avulsas_da_tela()}
    quem = _quem()
    nomes = b.nomes({D._id(x.get("pessoa_id")) for x in f["linhas"]})
    out = []
    for x in f["linhas"]:
        origem, rid = D._txt(x.get("origem")), D._txt(x.get("ronda_id"))
        uid, pid = D._id(x.get("usina_id")), D._id(x.get("pessoa_id"))
        base = {"ronda_id": rid, "origem": origem, "data": _dia_do_fato(x.get("data_id")), "usina_id": uid,
                "pessoa_id": pid, "tipo": D._txt(x.get("tipo_ronda")), "mobilizada": uid in b.mobilizadas,
                "inicio": D._txt(x.get("inicio")) or None, "fim": D._txt(x.get("fim")) or None,
                "checklist": _checklist_do_fato(x)}
        if origem == "avulsa":
            # a ronda AVULSA, lançada à mão no Nexus (07/10/2026): sem OS por natureza (não é a pendência "sem OS no
            # Fracttal") e sem nota (a do App depende de foto e GPS)
            a = avulsas.get(rid) or {}
            if FR.eh_validacao_foto(a):
                continue        # uma carga antiga pode ter posto a validação por foto no fato: ela não é ronda
            out.append({**base, "os": None, **b.onde(uid), "regiao": "",
                        "tecnico": nomes.get(pid) or nome_curto(a.get("nome")), "nota": None, "falhas": "",
                        "trk_apontados": 0, "trk_respondidos": 0, "situacao_os": "", "sem_os": False,
                        "avulsa": True, "avulsa_id": str(a.get("id") or ""), "avulsa_hmac": a.get("pessoa_hmac"),
                        "comentario": a.get("comentario") or ""})
            continue
        r = cru.get(D._txt(x.get("inicio"))) or {}
        sit = str(r.get("Situação da OS") or "")
        out.append({**base, "os": D._txt(x.get("os")) or None, **b.onde(uid, r.get("Usina")),
                    "regiao": r.get("Região") or "", "tecnico": nomes.get(pid) or _nome_do_tecnico(r, quem),
                    "nota": D._int(x.get("nota_pts")), "falhas": str(r.get("Falhas") or "").strip(),
                    "trk_apontados": D._int(x.get("trackers_apontados_qtd")) or 0,
                    "trk_respondidos": D._int(x.get("trackers_respondidos_qtd")) or 0, "situacao_os": sit,
                    "sem_os": origem == "app_sem_os" or D._txt(x.get("os_situacao")) == "nao_criada",
                    "tecnico_codigo": bool(D._txt(r.get("Técnico (HMAC)")))})
    return out


# ── Validação por foto (Levi, 08/10/2026) ────────────────────────────────────────────────────────────────────────
# O livro da avulsa recebe também linhas de "criticidade validada pela foto": níveis de sujidade e vegetação que um
# colega revisou a partir das fotos das rondas do App, em nome de quem validou (`origem = "validacao_foto"`). NÃO é ronda
# realizada: fora do fato_ronda, de Registros, cobertura, Quem ronda, Painel e duração. Entra só como a LEITURA de
# sujidade e vegetação da usina naquele dia (aba Sujidade e vegetação e Histórico da usina), com o selo "Validada por
# foto". Havendo ronda do App no mesmo dia na mesma usina, o valor validado é o que vale para a usina e a linha do
# técnico aparece marcada como revisada.
VALIDADA_EXPLICACAO = ("Validada por foto: níveis de sujidade e vegetação revisados a partir das fotos das rondas do "
                       "App. Não é ronda nova.")


def validacoes_por_foto(b: _Base) -> list[dict]:
    """As validações por foto que valem (sem as anuladas), com a usina do cadastro e quem validou. Lidas do livro da
    avulsa (são outro grão: não entram em fato nenhum por enquanto), com os domínios de `dominios.py`."""
    linhas = [a for a in _avulsas_da_tela() if FR.eh_validacao_foto(a)]
    nomes = b.nomes({D._id(a.get("pessoa_id")) for a in linhas})
    out = []
    for a in linhas:
        uid = D._id(a.get("usina_id"))
        dia = _dia_do_fato(a.get("data_id")) or str(a.get("data") or "")[:10]
        if not uid or not _DATA_ISO.match(dia):
            continue
        out.append({"id": str(a.get("id") or ""), "data": dia, "usina_id": uid, **b.onde(uid),
                    "mobilizada": uid in b.mobilizadas, "validada": True, "lancada_em": str(a.get("lancada_em") or ""),
                    "tecnico": nomes.get(D._id(a.get("pessoa_id"))) or nome_curto(a.get("nome")),
                    "sujidade": DOM.nivel(a.get("sujidade")), "vegetacao": DOM.nivel(a.get("vegetacao")),
                    "vala": DOM.VALA_ROTULO.get(DOM.vala(a.get("vala")), ""),
                    "sombreamento": {1: "sim", 0: "não"}.get(DOM.sim_nao(a.get("sombreamento")), ""),
                    "sensores_sujos": [n for c, n in SENSORES_DA_TELA if DOM.sensor_avulsa(a.get(c)) == 1]})
    # a mais recente do dia vence (duas validações da mesma usina no mesmo dia: vale a última lançada)
    out.sort(key=lambda v: (v["data"], v["lancada_em"]), reverse=True)
    return out


def _validacao_do_dia(validacoes) -> dict:
    """{(usina_id, dia): a validação que vale naquele dia} (a lista já vem da mais recente para a mais antiga)."""
    out = {}
    for v in validacoes:
        out.setdefault((v["usina_id"], v["data"]), v)
    return out


def _cobertura(b: _Base, rondas: list[dict], hoje) -> list[dict]:
    """Uma linha por usina MOBILIZADA: a última ronda e há quantos dias. Nunca teve ronda = 999."""
    ultima = {}
    for r in rondas:
        # ronda sem dia (o fato não achou o dia do início) não diz há quanto tempo foi: fica fora desta conta
        if r["usina_id"] and r["data"] and (r["usina_id"] not in ultima or r["data"] > ultima[r["usina_id"]]["data"]):
            ultima[r["usina_id"]] = r
    out = []
    for uid in b.mobilizadas:
        r = ultima.get(uid)
        dias = (hoje - datetime.fromisoformat(r["data"]).date()).days if r else 999
        out.append({"usina_id": uid, **b.onde(uid), "ultima": r["data"] if r else None, "dias": dias, "tecnico": r["tecnico"] if r else "",
                    "tipo": r["tipo"] if r else "", "falhas": r["falhas"] if r else "", "os": r["os"] if r else None})
    out.sort(key=lambda x: (-x["dias"], x["usina"]))
    return out


# Os limites da ronda são os do App (LIMIARES_PADRAO do function_app.py, copiado em regras_app.py): a tela do Nexus
# chama de "Muito bom", "Atenção" e "Não está bom" exatamente o que o painel do App chamava.
def _limites() -> dict:
    from . import regras_app
    return regras_app.LIMIARES_PADRAO


def _duracao_min(r) -> int | None:
    """Do início ao fim, carimbados pelo aparelho (como o `_duracao_ronda` do App, sem a pausa, que o livro não traz).
    Fora de 0 a 8 h = relógio errado, não ronda: fica sem duração."""
    a, b = _dt(r.get("inicio")), _dt(r.get("fim"))
    if not a or not b:
        return None
    m = (b - a).total_seconds() / 60
    return int(round(m)) if 0 <= m <= 480 else None


def _veredito(r, lim) -> tuple[str, str]:
    """O `_veredito_ronda` do App, na mesma ordem, com o que o livro traz: o GPS só aparece como a falha "sem GPS"."""
    q, dur = r["nota"] or 0, r["dur_min"]
    falhas = [f for f in (x.strip() for x in r["falhas"].split(";")) if f]
    sem_gps = any("gps" in f.lower() for f in falhas)
    tt, tr = r["trk_apontados"], r["trk_respondidos"]
    curta = dur is not None and dur < lim["ronda_dur_min"]
    if curta and (sem_gps or (tt and tr == 0)) or sem_gps:
        return "critico", "Não está bom"
    if tt and tr == 0:
        return "critico", "Sem devolutiva"
    if curta:
        return "alerta", "Atenção"
    if q < lim["ronda_critico_q"]:
        return "critico", "Não está bom"
    if q >= lim["ronda_exemplar_q"] and not falhas and (not tt or tr == tt):
        return "ok", "Muito bom"
    if q < lim["ronda_atencao_q"] or falhas:
        return "alerta", "Atenção"
    return "ok", "Bom"


def motivo_sem_os(situacao) -> str:
    """O motivo de a OS da ronda não ter nascido, em português de quem lê a tela (Levi, 05/10: "não entendi essa
    observação, minha conta fracttal já está conectada"). O App cria a OS de ronda com a conta Fracttal do TÉCNICO
    (`token_fracttal_valido(email do técnico)`); a mensagem crua dele ("Conecte sua conta Fracttal") é para o técnico.
    Medido em 05/10: 114 de 771 rondas sem OS por isso, e o App desiste depois de 5 tentativas (uma por minuto), então a
    ronda antiga não ganha OS quando o técnico conecta depois."""
    s = str(situacao or "")
    if "Conecte sua conta Fracttal" in s:
        return "OS não criada: o técnico não tinha conectado a conta Fracttal dele no App"
    if "Sessão Fracttal expirada" in s:
        return "OS não criada: a conta Fracttal do técnico tinha desconectado no App (sessão vencida)"
    if "responsável não resolvido" in s:
        quem = s.split("para", 1)[-1].strip(" '\"") if "para" in s else ""
        return "OS não criada: o Fracttal não achou o técnico como responsável" + (f" ({quem})" if quem else "")
    return s or "OS não criada"


def _hm(iso) -> str:
    d = _dt(iso)
    return d.strftime("%H:%M") if d else ""


def _tecnicos_por_equipe(b: _Base) -> dict:
    """{equipe_id: [nome curto dos técnicos]} pelo cadastro de pessoas, com a regra de `_Base._time` (colaborador de
    campo da equipe que não está Desligado). O nome é decifrado na hora (NEXUS_CHAVE_CADASTRO); sem a chave, as listas
    vêm vazias e a tela mostra só quantos são."""
    ids = {}
    for p in b.pessoas:
        eid = D._id(p.get("equipe_id"))
        if (not eid or str(p.get("vinculo") or "").strip() != CAMPO
                or str(p.get("status") or "").strip().lower() == "desligado"
                or str(p.get("excluido") or "").strip().lower() == "sim"):
            continue
        ids.setdefault(eid, set()).add(D._id(p.get("pessoa_id")))
    nomes = b._nomes({pid for s in ids.values() for pid in s}, b.pessoas)
    return {eid: sorted({nomes[pid] for pid in pids if nomes.get(pid)}) for eid, pids in ids.items()}


def _ultima_os_por_usina(b: _Base) -> dict:
    """{usina_id: a última OS fechada pelo App na usina, de QUALQUER tipo}: número, dia, tipo e quem fez (Levi, 08/10:
    "última OS feita na usina (para conseguir rastrear a última vez que o técnico foi lá)"). Vem do fato
    `fato_fechamento` (passo 4, 08/10/2026): a usina, a OS, o tipo, a hora e a pessoa (`pessoa_id`) são os do fato; o
    nome de quem não ligou ao cadastro sai do código do App no livro cru, juntado pela chave do fato
    (`fechamento_id`). Limite: só o que passou pelo App, e o livro guarda 90 dias; OS fechada direto no Fracttal não
    aparece."""
    f = _fato("fechamento", b)
    cru = {D.chave_fechamento(a): a for a in _livro(*C.ORIGEM_FECHAMENTOS)}
    quem = _quem()
    nomes = b.nomes({D._id(x.get("pessoa_id")) for x in f["linhas"]})
    out = {}
    for x in f["linhas"]:
        uid, quando = D._id(x.get("usina_id")), _dt(x.get("registrado_em"))
        if not uid or not quando:
            continue
        if uid not in out or quando > out[uid]["quando"]:
            pid = D._id(x.get("pessoa_id"))
            nome = nomes.get(pid) or _nome(quem, (cru.get(D._txt(x.get("fechamento_id"))) or {}).get("Técnico (HMAC)"))
            out[uid] = {"os": D._txt(x.get("os")), "quando": quando, "data": quando.date().isoformat(),
                        "tipo": D._txt(x.get("tipo_os")), "tecnico": nome}
    return out


def _registro_da_cobertura(b: _Base, cobertura: list[dict], ligadas: list[dict]) -> str:
    """Completa cada usina da cobertura para a aba "Sem ronda" e o indicador "Nunca tiveram ronda" (Levi, 08/10/2026):
    - `nunca`: nenhuma ronda em TODO o registro do Nexus, não só no período. Desde o passo 4 (08/10) é o fato único de
      ronda inteiro (`ligadas`): ele já une o livro de rondas do App, as avulsas e a carga única do checklist das
      rondas sem OS (`nexus_rondas_checklist`), inclusive a ronda que já saiu da janela de 90 dias do App;
    - `tecnicos` (nomes curtos) e `n_tecnicos`: os técnicos da equipe da usina, pelo cadastro;
    - `ultima_os`: a última OS fechada pelo App na usina (`_ultima_os_por_usina`).
    Devolve desde quando vai o registro (o dia mais antigo do fato), que o indicador diz no `title`."""
    com_ronda = {r["usina_id"] for r in ligadas if r["usina_id"]}
    datas = [r["data"] for r in ligadas if _DATA_ISO.match(r["data"] or "")]
    tecnicos, ultima_os = _tecnicos_por_equipe(b), _ultima_os_por_usina(b)
    for c in cobertura:
        eid = D._id((b.por_id.get(c["usina_id"]) or {}).get("equipe_id"))
        c["nunca"] = c["usina_id"] not in com_ronda
        c["tecnicos"] = tecnicos.get(eid, [])
        c["n_tecnicos"] = (b.time.get(eid) or {}).get("tecnicos", 0)
        c["ultima_os"] = ultima_os.get(c["usina_id"])
    return min(datas, default="")


def rondas(dias: int = DIAS_COBERTURA) -> leitura.Leitura:
    """As rondas de usina mobilizada, cada uma com duração, horário de Brasília e veredito, e a cobertura das usinas.
    A conta do período (os indicadores) é `painel_rondas`, depois dos filtros da tela."""
    def calcular():
        b = _Base()
        hoje = _agora().date()
        lim = _limites()
        ligadas = _rondas_ligadas(b)
        todas = [r for r in ligadas if r["mobilizada"]]
        for r in todas:
            r["dur_min"] = _duracao_min(r)
            r["ini_hm"], r["fim_hm"] = _hm(r["inicio"]), _hm(r["fim"])
            # a avulsa não tem nota (sem foto nem GPS): veredito "—", nunca o "Não está bom" de nota zero
            r["veredito"] = ("neutro", "—") if r.get("avulsa") else _veredito(r, lim)
            # o que ficou faltando na ronda (as "rondas feitas" que saíram da Central de atenção, 05/10)
            faltas = [f.strip() for f in r["falhas"].split(";") if f.strip() and f.strip().lower() != LONGA_PENDENTE]
            r["pendencia"] = "sem_os" if r["sem_os"] else ("incompleta" if faltas else "")
            r["pend_obs"] = "; ".join(([motivo_sem_os(r["situacao_os"])] if r["sem_os"] else []) + faltas)
        todas.sort(key=lambda r: (r["data"], r["fim"] or ""), reverse=True)
        cobertura = _cobertura(b, todas, hoje)
        desde = _registro_da_cobertura(b, cobertura, ligadas)
        return {"todas": todas, "cobertura": cobertura, "sem_mobilizacao": b.sem_mobilizacao,
                "hoje": hoje.isoformat(), "registro_desde": desde,
                "validacoes": [v for v in validacoes_por_foto(b) if v["mobilizada"]],
                "fatos": _avisos("ronda", "fechamento"), "aviso_tecnico": _aviso_tecnico(ligadas)}
    return _ler(("visao_rondas",), calcular)


def _aviso_tecnico(ligadas) -> str:
    """O App passa a mandar o técnico das rondas como código (`Técnico (HMAC)`, pacote de 08/10/2026). Sem a chave
    NEXUS_PESSOA_HMAC neste Nexus o código não vira nome: a tela não quebra e diz o que falta."""
    sem_nome = sum(1 for r in ligadas if r.get("tecnico_codigo") and not r["tecnico"])
    if not sem_nome or current_app.config.get("NEXUS_PESSOA_HMAC"):
        return ""
    return (f"O App manda o técnico das rondas como código (HMAC) e este Nexus não tem a chave NEXUS_PESSOA_HMAC: "
            f"{sem_nome} ronda{'s' if sem_nome != 1 else ''} sem o nome do técnico.")


def _quem_ronda(r) -> tuple:
    """Quem fez a ronda, para agrupar (Quem ronda): o `pessoa_id` do fato; sem ele, o nome que o livro trouxe. Até
    08/10/2026 o grupo era o nome escrito: a mesma pessoa com duas grafias virava duas linhas (79 grafias para 54
    pessoas nos 90 dias medidos em 08/10)."""
    return ("p", r["pessoa_id"]) if r.get("pessoa_id") else ("n", r["tecnico"] or "—")


def _pendente(c) -> bool:
    """A usina pede ronda: a mesma regra da Central de atenção (sem ronda há 7 dias ou mais, nunca, ou a ronda longa
    pendente pela última ronda)."""
    return c["dias"] >= DIAS_SEM_RONDA_ALERTA or LONGA_PENDENTE in str(c.get("falhas") or "").lower()


def _resumo_rondas(rondas, lim) -> dict:
    notas = [r["nota"] for r in rondas if r["nota"] is not None]
    durs = [r["dur_min"] for r in rondas if r["dur_min"] is not None]
    return {"rondas": len(rondas), "longas": sum(1 for r in rondas if r["tipo"] == "longa"),
            "usinas_rondadas": len({r["usina_id"] or r["usina"] for r in rondas}),
            "nota": round(statistics.mean(notas)) if notas else None,
            "dur_media": round(statistics.mean(durs)) if durs else None,
            "dur_mediana": round(statistics.median(durs)) if durs else None,
            "curtas": sum(1 for d in durs if d < lim["ronda_dur_min"]),
            "ultima": max((r["data"] for r in rondas), default="")}


def _por_cluster(periodo, cobertura, lim) -> list[dict]:
    """Quem ronda por cluster (Levi, 05/10: "seria melhor por cluster, aí nesse cluster clicando apareceria as mesmas
    informações porém por pessoa do cluster e também tem que ter um contador de usinas pendentes de ronda"). O cluster é
    o do cadastro (registro mestre), pela usina. Pendentes do cluster = usinas mobilizadas dele que pedem ronda (a regra
    da Central). Pendentes da pessoa = as da equipe em que ela mais ronda (a equipe da usina, do cadastro), e QUAIS são
    (Levi, 08/10: "quando aparece o técnico tem tipo 'pendentes de ronda = 5' clicando na linha tem que aparecer quais
    são essas 5"). Cobertura do cluster = usinas dele com ronda no período ÷ usinas dele, a mesma conta do indicador
    "Cobertura de usinas" e do Painel (para o cartão do cluster bater com o resto da tela)."""
    com_ronda = {r["usina_id"] for r in periodo if r["usina_id"]}
    pend_eq, usinas_cl, pend_cl, equipes_cl, lista_eq, lista_cl, cobertas_cl = {}, {}, {}, {}, {}, {}, {}
    for c in cobertura:                     # a cobertura já vem da mais atrasada para a menos
        cl, eq = c.get("cluster") or SEM_CLUSTER, c.get("equipe") or SEM_EQUIPE
        usinas_cl[cl] = usinas_cl.get(cl, 0) + 1
        cobertas_cl[cl] = cobertas_cl.get(cl, 0) + (c["usina_id"] in com_ronda)
        equipes_cl.setdefault(cl, set()).add(eq)
        if _pendente(c):
            pend_cl[cl] = pend_cl.get(cl, 0) + 1
            pend_eq[eq] = pend_eq.get(eq, 0) + 1
            lista_eq.setdefault(eq, []).append(_item_pendente(c))
            lista_cl.setdefault(cl, []).append(_item_pendente(c))
    rondas_cl = {}
    for r in periodo:
        rondas_cl.setdefault(r.get("cluster") or SEM_CLUSTER, []).append(r)
    out = []
    for cl in sorted(set(usinas_cl) | set(rondas_cl)):
        rs = rondas_cl.get(cl, [])
        pessoas = {}
        for r in rs:
            pessoas.setdefault(_quem_ronda(r), []).append(r)
        lista = []
        for prs in pessoas.values():
            eqs = {}
            for r in prs:
                eqs[r["equipe"] or SEM_EQUIPE] = eqs.get(r["equipe"] or SEM_EQUIPE, 0) + 1
            equipe = max(eqs, key=eqs.get)
            lista.append({"tecnico": prs[0]["tecnico"] or "—", "equipe": equipe, "pendentes": pend_eq.get(equipe, 0),
                          "pendentes_usinas": lista_eq.get(equipe, []), **_resumo_rondas(prs, lim)})
        n = usinas_cl.get(cl, 0)
        out.append({"cluster": cl, "usinas": n, "pendentes": pend_cl.get(cl, 0), "pendentes_usinas": lista_cl.get(cl, []),
                    "cobertas": cobertas_cl.get(cl, 0),
                    "cobertura_pct": round(100 * cobertas_cl.get(cl, 0) / n) if n else None,
                    "equipes": sorted(equipes_cl.get(cl, set())), "tecnicos": len(pessoas),
                    "pessoas": sorted(lista, key=lambda q: (-q["rondas"], q["tecnico"])), **_resumo_rondas(rs, lim)})
    return sorted(out, key=lambda c: (-c["pendentes"], -c["rondas"], c["cluster"]))


def _item_pendente(c) -> dict:
    """Uma usina que pede ronda, com o porquê escrito como a Central de atenção escreve (`atencao`): o status
    (`PENDENTE`) e a observação."""
    longa = LONGA_PENDENTE in str(c.get("falhas") or "").lower()
    if c["dias"] >= 999:
        tipo, obs = "nunca", "Nenhuma ronda pelo App desde que a usina foi mobilizada"
    elif c["dias"] >= DIAS_SEM_RONDA_ALERTA:
        tipo, obs = "sem_ronda", f"Última ronda em {_dm(c.get('ultima'))}" + (
            "; a ronda longa também está pendente" if longa else "")
    else:
        tipo, obs = "longa_pendente", f"O App pede a ronda longa (última ronda em {_dm(c.get('ultima'))})"
    rot, cor = PENDENTE[tipo]
    return {"usina": c["usina"], "usina_id": c["usina_id"], "equipe": c.get("equipe") or "", "dias": c["dias"],
            "ultima": c.get("ultima"), "tipo": tipo, "longa": longa, "status": rot, "cor": cor, "obs": obs}


# ── Painel: quem está melhor (Levi, 08/10/2026: "acho que deve inserir uma visão a mais, dashboards que mostre de
# fato, regiões com melhores indicadores, melhores coberturas, quais equipes tem melhor qualidade e cobertura, qual
# cliente, qual supervisor!") ────────────────────────────────────────────────────────────────────────────────────
DIMENSOES = (("regiao_br", "Região do Brasil"), ("equipe", "Equipe"), ("cliente", "Cliente"), ("supervisor", "Supervisor"))
# grupo com 1 ou 2 usinas mobilizadas: uma usina a mais ou a menos com ronda muda a cobertura em 50 pontos ou mais
BASE_PEQUENA = 3


def comparativos(periodo, cobertura, lim=None) -> dict:
    """Os mesmos números do painel, agrupados por região do Brasil (pela UF), equipe, cliente e supervisor, todos do
    cadastro, pela usina. Cobertura = usinas mobilizadas do grupo com ronda no período ÷ usinas do grupo (a conta do
    indicador "Cobertura de usinas"); qualidade = a nota média das rondas do grupo; duração média = a média de fim −
    início; pendentes = a regra da Central. Índice = 60% qualidade + 40% cobertura, a régua do ranking por região do
    painel do App; grupo sem uma das duas não ganha índice, para não ganhar 100 pela outra metade. Melhor índice
    primeiro. `base_pequena` marca o grupo com menos de `BASE_PEQUENA` usinas (o número dele oscila muito)."""
    lim = lim or _limites()
    com_ronda = {r["usina_id"] for r in periodo if r["usina_id"]}
    out = {}
    for chave, _rot in DIMENSOES:
        g = {}
        for c in cobertura:
            a = g.setdefault(c.get(chave) or "—", {"nome": c.get(chave) or "—", "usinas": 0, "cobertas": 0,
                                                    "pendentes": 0, "rs": []})
            a["usinas"] += 1
            a["cobertas"] += c["usina_id"] in com_ronda
            a["pendentes"] += _pendente(c)
        for r in periodo:
            if (r.get(chave) or "—") in g:
                g[r.get(chave) or "—"]["rs"].append(r)
        lista = []
        for a in g.values():
            a.update(_resumo_rondas(a.pop("rs"), lim))
            a["cobertura_pct"] = round(100 * a["cobertas"] / a["usinas"]) if a["usinas"] else None
            a["indice"] = (round(PESO_QUALIDADE * a["nota"] + PESO_COBERTURA * a["cobertura_pct"])
                           if a["nota"] is not None and a["cobertura_pct"] is not None else None)
            a["base_pequena"] = a["usinas"] < BASE_PEQUENA
            lista.append(a)
        lista.sort(key=lambda a: (a["indice"] is None, -(a["indice"] or 0), -(a["cobertura_pct"] or 0), a["nome"]))
        out[chave] = lista
    return out


# ── Sujidade e vegetação: o que está mais crítico ─────────────────────────────────────────────────────────────────
# Levi, 08/10/2026: "quero que não fique ordenado pela data e sim pelo o que está mais crítico, um balanço entre
# vegetação, sujidade, vala e sensores. Terá um status com atenção por exemplo (vegetação 4 = vegetação alta, vegetação
# 5 = vegetação muito alta, alta sujidade, vala obstruída e etc.)". Os pesos (a soma é a nota de criticidade):
# - sujidade e vegetação: nível 5 vale 5, nível 4 vale 3, nível 3 vale 1 (acima de 3 já pede ação no App; o 3 só
#   desempata), 1 e 2 valem 0;
# - vala obstruída (ou "suja", a palavra da ronda avulsa) vale 4; parcial, 2;
# - cada sensor sujo (IPOA, albedômetro, GHI) vale 2: sensor sujo falseia a irradiação e o PR da usina inteira.
# Assim vegetação 5 + vala obstruída (9) passa à frente de sujidade 5 sozinha (5), e uma usina com tudo no nível 4
# (3 + 3 = 6) passa à frente de uma vala só obstruída (4). O sombreamento entra no Status, mas não pesa: em 804 rondas
# lidas (07/10) só uma tinha a resposta, e era texto livre.
PESO_NIVEL = {5: 5, 4: 3, 3: 1}
PESO_VALA = {"obstruida": 4, "suja": 4, "parcial": 2}
PESO_SENSOR = 2
_SEM_SOMBRA = {"", "nao", "sem", "nenhum", "nenhuma", "ausente", "nao se aplica", "sem sombreamento", "nao ha", "ok",
               "limpo", "none"}


def criticidade(x) -> tuple[int, list[tuple[str, str]]]:
    """(nota de criticidade, [(o que chama atenção, cor)]) de uma leitura de sujidade e vegetação, o mais grave
    primeiro. Cor: "critico" (nível 5, vala obstruída), "alerta" (nível 4, vala parcial, sensor sujo), "info"
    (sombreamento apontado). Sem nada: lista vazia (a tela diz "Sem alerta")."""
    pontos, itens = 0, []
    for campo, nome in (("vegetacao", "Vegetação"), ("sujidade", "Sujidade")):
        n = x.get(campo)
        pontos += PESO_NIVEL.get(n, 0)
        if n == 5:
            itens.append((f"{nome} muito alta", "critico"))
        elif n == 4:
            itens.append((f"{nome} alta", "alerta"))
    vala = _norm_txt(x.get("vala"))
    pontos += PESO_VALA.get(vala, 0)
    if PESO_VALA.get(vala) == 4:
        itens.append(("Vala obstruída", "critico"))
    elif vala == "parcial":
        itens.append(("Vala parcial", "alerta"))
    sensores = list(x.get("sensores_sujos") or [])
    if sensores:
        pontos += PESO_SENSOR * len(sensores)
        itens.append(("Sensor sujo (" + ", ".join(sensores) + ")", "alerta"))
    if _norm_txt(x.get("sombreamento")) not in _SEM_SOMBRA:
        itens.append(("Sombreamento", "info"))
    ordem = {"critico": 0, "alerta": 1, "info": 2}
    itens.sort(key=lambda i: ordem[i[1]])
    return pontos, itens


def historico_usina(todas, respostas: dict, usina_id, validacoes=()) -> list[dict]:
    """O histórico de rondas de uma usina (Levi, 05/10: "quando clicarmos no nome da usina já aparece o histórico de
    rondas com data e sujidade e vegetação"): todas as rondas do livro (90 dias), a mais recente primeiro, com as
    respostas do checklist lidas da OS no Fracttal (`ronda_checklist`; só das OS que o Nexus leu: as em verificação e
    as aprovadas dos últimos 45 dias).
    Validação por foto (Levi, 08/10/2026): entra como uma linha própria (`validada`, a leitura da usina naquele dia,
    em nome de quem validou), que não é ronda; a ronda do App do MESMO dia ganha `revisada` (os níveis dela foram
    revisados: o que vale para a usina é a linha validada)."""
    do_dia = {dia: v for (uid, dia), v in _validacao_do_dia(validacoes).items() if uid == usina_id}
    out = []
    for r in todas:
        if r["usina_id"] != usina_id:
            continue
        resp = resposta_da_ronda(r, respostas)
        v = do_dia.get(r["data"])
        out.append({**r, "sujidade": resp.get("sujidade"), "vegetacao": resp.get("vegetacao"), "vala": resp.get("vala") or "",
                    "sombreamento": resp.get("sombreamento") or "", "sensores_sujos": resp.get("sensores_sujos") or [],
                    "lida": bool(resp), "revisada": ({"por": v["tecnico"], "sujidade": v["sujidade"],
                                                      "vegetacao": v["vegetacao"]} if v else None)})
    for dia, v in do_dia.items():
        revisa = [x for x in out if x["data"] == dia and x.get("revisada")]
        out.append({**v, "tipo": "", "dur_min": None, "nota": None, "veredito": ("neutro", "—"), "falhas": "",
                    "pendencia": "", "pend_obs": "", "os": None, "sem_os": False, "avulsa": False, "lida": True,
                    "ini_hm": "", "fim_hm": "", "fim": None, "revisa": [{"tecnico": x["tecnico"], "os": x["os"]}
                                                                       for x in revisa]})
    # a validação fica em cima das rondas do dia dela: é o valor que vale para a usina
    return sorted(out, key=lambda r: (r["data"], "~" if r.get("validada") else (r["fim"] or "")), reverse=True)


def painel_rondas(todas, cobertura, dias: int, hoje_iso: str) -> dict:
    """Os indicadores do período, sobre as listas já filtradas pela tela (região, supervisor):
    - cobertura = usinas mobilizadas com ronda no período ÷ usinas mobilizadas, e a mesma conta no período anterior de
      mesmo tamanho (a seta);
    - qualidade abaixo do limite = nota abaixo de 85 (o "atenção" do App);
    - abaixo de 10 min = checklist não percorrido (o tempo mínimo do App);
    - usina mais atrasada = a mobilizada há mais tempo sem ronda."""
    lim = _limites()
    hoje = datetime.fromisoformat(hoje_iso).date()
    piso = (hoje - timedelta(days=dias - 1)).isoformat()
    piso_ant = (hoje - timedelta(days=2 * dias - 1)).isoformat()
    periodo = [r for r in todas if r["data"] >= piso]
    anterior = [r for r in todas if piso_ant <= r["data"] < piso]
    usinas = {c["usina_id"] for c in cobertura}
    cobertas = {r["usina_id"] for r in periodo} & usinas
    cobertas_ant = {r["usina_id"] for r in anterior} & usinas
    pct = lambda n: round(100 * n / len(usinas)) if usinas else None
    notas = [r["nota"] for r in periodo if r["nota"] is not None]
    durs = [r["dur_min"] for r in periodo if r["dur_min"] is not None]
    atrasada = cobertura[0] if cobertura else None
    quem = {}
    for r in periodo:
        q = quem.setdefault(_quem_ronda(r), {"tecnico": r["tecnico"] or "—", "rondas": 0, "usinas": set(), "notas": [],
                                                  "durs": [], "curtas": 0, "longas": 0, "ultima": "", "equipe": r["equipe"]})
        q["rondas"] += 1
        q["usinas"].add(r["usina"])
        q["notas"] += [r["nota"]] if r["nota"] is not None else []
        q["durs"] += [r["dur_min"]] if r["dur_min"] is not None else []
        q["curtas"] += r["dur_min"] is not None and r["dur_min"] < lim["ronda_dur_min"]
        q["longas"] += r["tipo"] == "longa"
        q["ultima"] = max(q["ultima"], r["data"])
    for q in quem.values():
        q["usinas"] = len(q["usinas"])
        q["nota"] = round(statistics.mean(q["notas"])) if q["notas"] else None
        q["dur_mediana"] = round(statistics.median(q["durs"])) if q["durs"] else None
        del q["notas"], q["durs"]
    return {"clusters": _por_cluster(periodo, cobertura, lim),
        "periodo": periodo, "trackers": [r for r in periodo if r["trk_apontados"]], "hoje": hoje_iso,
        "quem": sorted(quem.values(), key=lambda q: (-q["rondas"], q["tecnico"])),
        "kpi": {"rondas": len(periodo), "hoje": sum(1 for r in periodo if r["data"] == hoje_iso),
                "usinas": len(usinas), "cobertas": len(cobertas), "cobertura_pct": pct(len(cobertas)),
                "cobertura_ant_pct": pct(len(cobertas_ant)),
                "qualidade": round(statistics.mean(notas)) if notas else None,
                "abaixo_limite": sum(1 for n in notas if n < lim["ronda_atencao_q"]), "limite": lim["ronda_atencao_q"],
                "dur_media": round(statistics.mean(durs)) if durs else None,
                "dur_mediana": round(statistics.median(durs)) if durs else None,
                "curtas": sum(1 for d in durs if d < lim["ronda_dur_min"]), "dur_min": lim["ronda_dur_min"],
                # nunca teve ronda em TODO o registro do Nexus, não só no período (Levi, 08/10: "em KPIs coloque mais
                # um, quantas usinas nunca tiveram ronda"); `rondas` marca `nunca` com o livro, as avulsas e a carga
                "atrasada": atrasada, "nunca": sum(1 for c in cobertura if c.get("nunca", c["dias"] >= 999)),
                "sem_ronda_alerta": sum(1 for c in cobertura if c["dias"] >= DIAS_SEM_RONDA_ALERTA),
                "sem_os": sum(1 for r in periodo if r["sem_os"])}}


def sujidade_vegetacao(todas, cobertura, respostas: dict, dias: int, hoje_iso: str, validacoes=()) -> dict:
    """Sujidade dos módulos e altura da vegetação por usina (Levi, 05/10: "é importante!"): a última leitura de cada
    usina mobilizada no período e a anterior a ela (a seta), pelas respostas da ronda que o App escreve na OS do
    Fracttal (`ronda_checklist`). Nível de 1 a 5; acima de 3 pede ação (o `alerta_acima` do App). Junto: vala de
    drenagem, sombreamento, dejeto de pássaro e os sensores (IPOA, albedômetro, GHI) que a ronda achou sujos.
    Validação por foto (Levi, 08/10/2026): é a leitura da usina naquele dia (`validada`, em nome de quem validou) e,
    havendo ronda no mesmo dia, vale no lugar dela (a ronda do dia não é leitura da usina: foi revisada). Não conta nas
    rondas lidas (não é ronda)."""
    hoje = datetime.fromisoformat(hoje_iso).date()
    piso = (hoje - timedelta(days=dias - 1)).isoformat()
    usinas = {c["usina_id"]: c for c in cobertura}
    do_dia = {k: v for k, v in _validacao_do_dia(validacoes).items() if k[0] in usinas}
    leituras = {}
    com_os = lidas = 0
    revisadas = {}
    for r in sorted(todas, key=lambda r: (r["data"], r["fim"] or ""), reverse=True):
        if r["usina_id"] not in usinas or not (r["os"] or r.get("checklist")):
            continue
        com_os += r["data"] >= piso
        resp = resposta_da_ronda(r, respostas)
        if not resp or (resp.get("sujidade") is None and resp.get("vegetacao") is None):
            continue
        lidas += r["data"] >= piso
        if (r["usina_id"], r["data"]) in do_dia:     # revisada pela foto: a validação do dia é a leitura da usina
            revisadas.setdefault((r["usina_id"], r["data"]), []).append(r)
            continue
        leituras.setdefault(r["usina_id"], []).append((r, resp))
    for (uid, dia), v in do_dia.items():
        leituras.setdefault(uid, []).append(({**v, "os": next((x["os"] for x in revisadas.get((uid, dia), []) if x["os"]), None),
                                              "fim": None, "tipo": "", "revisa": [{"tecnico": x["tecnico"], "os": x["os"]}
                                                                                for x in revisadas.get((uid, dia), [])]}, v))
    for lst in leituras.values():
        lst.sort(key=lambda par: (par[0]["data"], "~" if par[0].get("validada") else (par[0]["fim"] or "")), reverse=True)
    linhas = []
    for uid, lst in leituras.items():
        r, resp = lst[0]
        if r["data"] < piso:
            continue
        ant = lst[1][1] if len(lst) > 1 else {}
        c = usinas[uid]
        linhas.append({"usina": c["usina"], "usina_id": uid, "equipe": c["equipe"], "uf": c["uf"], "regiao_br": c["regiao_br"],
                       "supervisor": c.get("supervisor"), "data": r["data"], "tecnico": r["tecnico"], "os": r["os"],
                       "tipo": r["tipo"], "sujidade": resp.get("sujidade"), "sujidade_ant": ant.get("sujidade"),
                       "vegetacao": resp.get("vegetacao"), "vegetacao_ant": ant.get("vegetacao"),
                       "vala": resp.get("vala") or "", "sombreamento": resp.get("sombreamento") or "",
                       "dejeto": resp.get("dejeto") or "", "sensores_sujos": resp.get("sensores_sujos") or [],
                       "avulsa": bool(r.get("avulsa")), "validada": bool(r.get("validada")),
                       "revisa": r.get("revisa") or []})
    for x in linhas:
        x["pontos"], x["status"] = criticidade(x)
        x["vala_peso"] = PESO_VALA.get(_norm_txt(x["vala"]), 0)      # a cor e a ordem da coluna Vala, sem acento
    alto = lambda n: n is not None and n > 3
    # o mais crítico primeiro (Levi, 08/10: "não fique ordenado pela data"); empate: o maior nível, depois a mais
    # recente, depois o nome
    linhas.sort(key=lambda x: x["usina"])
    linhas.sort(key=lambda x: x["data"], reverse=True)          # ordenação estável: o critério principal fica por último
    linhas.sort(key=lambda x: (-x["pontos"], -max(x["sujidade"] or 0, x["vegetacao"] or 0)))
    dist = lambda k: {n: sum(1 for x in linhas if x[k] == n) for n in range(1, 6)}
    media = lambda k: round(statistics.mean([x[k] for x in linhas if x[k] is not None]), 1) if any(x[k] is not None for x in linhas) else None
    return {"linhas": linhas,
            "resumo": {"usinas": len(usinas), "com_leitura": len(linhas), "sem_leitura": len(usinas) - len(linhas),
                       "sujidade_alta": sum(1 for x in linhas if alto(x["sujidade"])),
                       "vegetacao_alta": sum(1 for x in linhas if alto(x["vegetacao"])),
                       "sensores": sum(1 for x in linhas if x["sensores_sujos"]),
                       "vala": sum(1 for x in linhas if x["vala"] and _norm_txt(x["vala"]) not in ("limpa", "ok", "nao se aplica")),
                       "sujidade_media": media("sujidade"), "vegetacao_media": media("vegetacao"),
                       "dist_sujidade": dist("sujidade"), "dist_vegetacao": dist("vegetacao"),
                       "rondas_com_os": com_os, "rondas_lidas": lidas}}


def _norm_txt(s) -> str:
    import unicodedata
    return " ".join(unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower().split())


# ── Permissões de trabalho ───────────────────────────────────────────────────────────────────────────────────────
def pts() -> leitura.Leitura:
    """Todas as PT, pelo fato conformado (`fato_pt`, passo 4 de 08/10/2026): 1 linha = 1 PT × ativo (o App decide por
    linha), a mesma contagem de antes (linha do livro). Do fato: a PT, a usina (`usina_id`), a situação (o domínio de
    `dominios.py`), as datas, a espera, o solicitante e o decisor (`*_pessoa_id`, `*_hmac`), as respostas NÃO e a
    forçada. Do livro cru, pela chave do fato (`pt_linha_id` = Número + Código do ativo): tarefa, ativo, papel, motivo,
    efeito, o que falta, as atividades e o 1º aviso. A idade de quem espera é a de AGORA (o `parada` do fato é a foto da
    hora da carga; o limite é o mesmo, `dominios.PT_PARADA_MIN`). A PT NÃO passa pelo filtro de usina mobilizada: PT
    esperando decisão sempre aparece (esconder deixaria o técnico parado no campo)."""
    def calcular():
        b = _Base()
        quem = _quem()
        agora = _agora()
        f = _fato("pt", b)
        cru = {FR.chave(D._txt(r.get("Número")), D._txt(r.get("Código do ativo"))): r for r in _livro(*C.ORIGEM_PT)}
        nomes = b.nomes({D._id(x.get(c)) for x in f["linhas"] for c in ("solicitante_pessoa_id", "decisor_pessoa_id")})
        out = []
        for x in f["linhas"]:
            r = cru.get(D._txt(x.get("pt_linha_id"))) or {}
            criada, decidida = _dt(x.get("criada_em")), _dt(x.get("decidida_em"))
            # situação fora do domínio (o App escreveu uma nova): o fato fica vazio; a tela mostra a palavra do App
            sit = D._txt(x.get("situacao")) or str(r.get("Situação") or "").strip() or "aguardando"
            uid = D._id(x.get("usina_id"))
            out.append({"numero": D._txt(x.get("pt")), "os": D._txt(x.get("os")) or None, "tarefa": r.get("Tarefa") or "",
                        "usina_id": uid, **b.onde(uid, r.get("Usina")), "ativo": r.get("Ativo") or "",
                        "codigo": D._txt(x.get("codigo_ativo")),
                        "solicitante": nomes.get(D._id(x.get("solicitante_pessoa_id")))
                        or _nome(quem, x.get("solicitante_hmac")), "situacao": sit,
                        "criada": criada, "decidida": decidida,
                        "decidida_por": nomes.get(D._id(x.get("decisor_pessoa_id"))) or _nome(quem, x.get("decisor_hmac")),
                        "papel": r.get("Papel de quem decidiu") or "", "motivo": r.get("Motivo") or "",
                        "efeito": r.get("Efeito") or "",
                        "respostas_nao": D._int(x.get("respostas_nao_qtd")) or 0, "faltam": r.get("Faltam") or "",
                        "atividades": [a.strip() for a in str(r.get("Atividades") or "").split(";") if a.strip()],
                        "forcada": D._int(x.get("forcada")) == 1, "aviso_em": _dt(r.get("1º aviso em")),
                        "aviso_motivo": r.get("1º aviso: motivo") or "",
                        "espera_min": D._int(x.get("espera_min")),
                        "idade_min": int((agora - criada).total_seconds() // 60) if criada and sit == "aguardando" else None})
        for p in out:
            p["parada"] = (p["idade_min"] or 0) > PT_PARADA_MIN
        aguardando = sorted((p for p in out if p["situacao"] == "aguardando"), key=lambda p: p["criada"] or agora)
        historico = sorted((p for p in out if p["situacao"] != "aguardando"), key=lambda p: p["criada"] or agora,
                           reverse=True)
        esperas = [p["espera_min"] for p in historico if p["espera_min"] is not None]
        situacoes = {}
        for p in out:
            situacoes[p["situacao"]] = situacoes.get(p["situacao"], 0) + 1
        return {"aguardando": aguardando, "historico": historico, "situacoes": situacoes, "times": b.times(),
                "fatos": _avisos("pt"),
                "resumo": {"aguardando": len(aguardando),
                           "mais_antiga_min": aguardando[0]["idade_min"] if aguardando else None,
                           "paradas": sum(1 for p in aguardando if p["parada"]),
                           "espera_mediana_min": round(statistics.median(esperas)) if esperas else None,
                           "com_nao": sum(1 for p in out if p["respostas_nao"])}}
    return _ler(("visao_pt",), calcular)


def pts_por_equipe(pts, times=None) -> list[dict]:
    """Um cartão por equipe com as PT dela (Levi, 05/10: "a divisão por equipe mostrando o que está pendente"): quem é
    o supervisor, quantos técnicos, quantas esperam, quantas paradas e a lista, da mais antiga para a mais nova. A
    equipe com mais PT parada vem primeiro."""
    eq = {}
    for p in pts:
        nome = p.get("equipe") or SEM_EQUIPE
        tm = (times or {}).get(nome) or {}
        c = eq.setdefault(nome, {"equipe": nome, "supervisor": p.get("supervisor") or tm.get("supervisor") or SEM_SUPERVISOR,
                                 "tecnicos": tm.get("tecnicos", 0), "cargos": tm.get("cargos", {}), "regioes": set(),
                                 "pts": [], "parada": 0})
        c["pts"].append(p)
        c["parada"] += bool(p.get("parada"))
        c["regioes"].update([p["regiao_br"]] if p.get("regiao_br") else [])
    for c in eq.values():
        c["regioes"] = sorted(c["regioes"])
    return sorted(eq.values(), key=lambda c: (-c["parada"], -len(c["pts"]), c["equipe"]))


def pt(numero) -> dict | None:
    """Uma PT pelo número, do livro do App (a cópia de 5 min)."""
    d = pts().dados
    n = str(numero or "").strip()
    return next((p for p in (d.get("aguardando") or []) + (d.get("historico") or []) if p["numero"] == n), None)


# ── Zeladoria ────────────────────────────────────────────────────────────────────────────────────────────────────
def zeladoria() -> leitura.Leitura:
    def calcular():
        quem = _quem()
        hoje = _agora().date().isoformat()
        servicos = {}
        for r in _livro("zeladoria_app_campo"):
            os_ = str(r.get("OS") or "")
            s = servicos.setdefault(os_, {"os": os_, "usina": r.get("Usina") or "", "servico": r.get("Serviço") or "",
                                          "prestador": r.get("Prestador") or "", "etapas": [], "fechada": False,
                                          "motivo": ""})
            s["etapas"].append({"data": str(r.get("Data") or "")[:10], "etapa": r.get("Etapa") or "",
                                "quem": _nome(quem, r.get("Registrado por (HMAC)")), "fotos": _int(r.get("Fotos")) or 0,
                                "nao": _int(r.get("Respostas NÃO")) or 0, "assinada": _sim(r.get("Assinada"))})
            s["fechada"] = s["fechada"] or _sim(r.get("OS fechada"))
            s["motivo"] = s["motivo"] or (r.get("Motivo do fechamento") or "")
        lista = []
        for s in servicos.values():
            s["etapas"].sort(key=lambda e: e["data"])
            feitas = {str(e["etapa"]).lower() for e in s["etapas"]}
            s["ultima"] = s["etapas"][-1]["data"] if s["etapas"] else None
            s["diaria_hoje"] = any(e["data"] == hoje and "diar" in str(e["etapa"]).lower() for e in s["etapas"])
            s["epi"] = any("epi" in f for f in feitas)
            s["com_nao"] = sum(e["nao"] for e in s["etapas"])
            lista.append(s)
        lista.sort(key=lambda s: (s["fechada"], s["ultima"] or ""))
        abertas = [s for s in lista if not s["fechada"]]
        return {"servicos": lista, "resumo": {"servicos": len(lista), "abertos": len(abertas),
                                              "sem_diaria_hoje": sum(1 for s in abertas if not s["diaria_hoje"]),
                                              "sem_epi": sum(1 for s in abertas if not s["epi"])}}
    return _ler(("visao_zeladoria",), calcular)


# (o Ranking saiu em 08/10/2026 com a tela dele, Levi: "ordens de serviço e imagens da ronda e ranking são
# redundantes"; a régua 60/40 vive nos comparativos do Painel das Rondas)


# ── Equipe e supervisor das usinas do Fracttal ───────────────────────────────────────────────────────────────────
FRACTTAL_C1 = "Fracttal · Classificação 1"


def usinas_do_fracttal() -> leitura.Leitura:
    """Para filtrar o que vem do Fracttal por equipe ou supervisor (Levi, 05/10: "As usinas do Fracttal são ligadas
    com as usinas do antigo BD_Operações de forma que dê para fazer essas ligações, certo?" Sim: pelo de-para "Fracttal ·
    Classificação 1" do cadastro, o mesmo do Ligador). {"equipes": {equipe: [nome no Fracttal]}, "supervisores":
    {supervisor: [nome no Fracttal]}, "sem_de_para": [usina mobilizada sem nome do Fracttal]}."""
    def calcular():
        b = _Base()
        nomes = {}
        for d in _livro("cadastro_nexus", "de_para"):
            uid = D._id(d.get("usina_id"))
            if uid and str(d.get("sistema") or "").strip() == FRACTTAL_C1 and str(d.get("chave_externa") or "").strip():
                nomes.setdefault(uid, set()).add(str(d["chave_externa"]).strip())
        from . import regras_app
        equipes, supervisores, por_nome = {}, {}, {}
        for uid in b.por_id:
            o = b.onde(uid)
            for n in nomes.get(uid, ()):
                equipes.setdefault(o["equipe"], set()).add(n)
                supervisores.setdefault(o["supervisor"], set()).add(n)
                # o nome do Fracttal (normalizado como a cópia do App normaliza) -> a usina do cadastro
                por_nome[regras_app._norm(n)] = {k: o[k] for k in ("usina", "equipe", "supervisor", "uf", "regiao_br")}
        return {"equipes": {k: sorted(v) for k, v in equipes.items() if k},
                "supervisores": {k: sorted(v) for k, v in supervisores.items() if k}, "por_nome": por_nome,
                "sem_de_para": sorted(str(u.get("nome") or "") for uid, u in b.mobilizadas.items() if uid not in nomes)}
    return _ler(("visao_usinas_fracttal",), calcular)


# ── Central de atenção ───────────────────────────────────────────────────────────────────────────────────────────
# Três visões (Levi, 05/10/2026): "separar Rondas feitas (histórico de rondas) e rondas pendentes, dando bastante
# atenção nas pendentes" e "separe o que é ronda e o que é Permissão de Trabalho".
PENDENTE = {"nunca": ("Nunca teve ronda", "critico"), "sem_ronda": ("Sem ronda", "critico"),
            "longa_pendente": ("Ronda longa pendente", "alerta")}
FEITA = {"sem_os": ("Sem OS no Fracttal", "alerta"), "incompleta": ("Evidência incompleta", "info"),
         "ok": ("Sem pendência", "ok")}
PT_STATUS = {"parada": ("Parada há mais de 2 h", "critico"), "aguardando": ("Aguardando", "alerta")}
LONGA_PENDENTE = "ronda longa pendente"


def _dm(iso) -> str:
    s = str(iso or "")
    return f"{s[8:10]}/{s[5:7]}" if len(s) >= 10 else ""


def atencao(dias: int = 14) -> leitura.Leitura:
    """O que pede ação no campo, em três visões. Só usina MOBILIZADA (a PT é a exceção, ver `pts`).
    - Rondas pendentes: uma linha por usina que pede ronda: sem ronda há 7 dias ou mais (ou nunca) ou com a ronda longa
      pendente pela última ronda dela (o App repete o aviso em toda ronda curta: uma linha só por usina).
    - Rondas feitas: o histórico do período, com o que ficou faltando: OS que o Fracttal não criou, evidência
      incompleta (foto, registro de ação, checklist).
    - Permissões de trabalho: as PT esperando o De acordo, da mais antiga para a mais nova.
    Nota baixa de fechamento NÃO entra: é a fila da Aprovação de OS."""
    def calcular():
        b = _Base()
        hoje = _agora().date()
        piso = (hoje - timedelta(days=dias - 1)).isoformat()
        rond = [r for r in _rondas_ligadas(b) if r["mobilizada"]]
        pendentes = []
        for c in _cobertura(b, rond, hoje):
            longa = LONGA_PENDENTE in c["falhas"].lower()
            if c["dias"] >= 999:
                tipo, obs = "nunca", "Nenhuma ronda pelo App desde que a usina foi mobilizada"
            elif c["dias"] >= DIAS_SEM_RONDA_ALERTA:
                tipo, obs = "sem_ronda", f"Última ronda em {_dm(c['ultima'])}" + (
                    "; a ronda longa também está pendente" if longa else "")
            elif longa:
                tipo, obs = "longa_pendente", f"O App pede a ronda longa (última ronda em {_dm(c['ultima'])})"
            else:
                continue
            pendentes.append({"tipo": tipo, "usina": c["usina"], "uf": c["uf"], "cidade": c["cidade"],
                              "equipe": c["equipe"], "regiao_br": c["regiao_br"], "supervisor": c["supervisor"],
                              "dias": c["dias"], "ultima": c["ultima"], "obs": obs})
        usinas = [{k: c[k] for k in ("usina", "equipe", "supervisor", "uf", "regiao_br", "cidade", "dias")}
                  for c in _cobertura(b, rond, hoje)]
        feitas = []
        for r in sorted((r for r in rond if r["data"] >= piso), key=lambda r: (r["data"], r["fim"] or ""), reverse=True):
            faltas = [f.strip() for f in r["falhas"].split(";") if f.strip() and f.strip().lower() != LONGA_PENDENTE]
            status = "sem_os" if r["sem_os"] else ("incompleta" if faltas else "ok")
            obs = "; ".join(([motivo_sem_os(r["situacao_os"])] if r["sem_os"] else []) + faltas)
            feitas.append({"data": r["data"], "status": status, "usina": r["usina"], "uf": r["uf"], "cidade": r["cidade"],
                           "equipe": r["equipe"], "regiao_br": r["regiao_br"], "supervisor": r["supervisor"],
                           "obs": obs, "feito_por": r["tecnico"], "os": None if r["sem_os"] else r["os"],
                           "nota": r["nota"], "tipo": r["tipo"]})
        p = pts()
        if p.erro:
            raise SemBanco(p.erro)
        return {"pendentes": pendentes, "feitas": feitas, "pts": p.dados.get("aguardando") or [], "usinas": usinas,
                "times": b.times(), "sem_mobilizacao": b.sem_mobilizacao,
                "fatos": {**_avisos("ronda"), **(p.dados.get("fatos") or {})}}
    return _ler(("visao_atencao", dias), calcular)


def por_equipe(usinas, pendentes, feitas, pts, times=None) -> list[dict]:
    """Um cartão por equipe (Levi, 05/10: "agrupamento por cards das equipes, usinas pendentes de ronda e % de rondas
    feitas da equipe"). Feitas = usinas mobilizadas da equipe que NÃO estão pendentes (ronda nos últimos 7 dias e sem a
    longa pendente); % feitas = feitas ÷ usinas. Junto: as rondas do período, as PT esperando e, do cadastro, quantos
    técnicos a equipe tem e quem é o supervisor. As listas chegam já filtradas pela tela (região, supervisor, busca),
    então o cartão conta o mesmo que a tabela."""
    eq = {}

    def card(nome):
        return eq.setdefault(nome or SEM_EQUIPE, {"equipe": nome or SEM_EQUIPE, "regioes": set(), "ufs": set(),
                                                  "usinas": 0, "pendentes": 0, "nunca": 0, "sem_ronda": 0,
                                                  "longa_pendente": 0, "rondas": 0, "ok": 0, "sem_os": 0,
                                                  "incompleta": 0, "pts": 0, "parada": 0})
    for u in usinas:
        c = card(u["equipe"])
        c["usinas"] += 1
        c["ufs"].update([u["uf"]] if u["uf"] else [])
        c["regioes"].update([u["regiao_br"]] if u["regiao_br"] else [])
    for x in pendentes:
        c = card(x["equipe"])
        c["pendentes"] += 1
        c[x["tipo"]] += 1
    for x in feitas:
        c = card(x["equipe"])
        c["rondas"] += 1
        c[x["status"]] += 1
    for x in pts:
        c = card(x.get("equipe"))
        c["pts"] += 1
        c["parada"] += bool(x.get("parada"))
        c["ufs"].update([x["uf"]] if x.get("uf") else [])
        c["regioes"].update([x["regiao_br"]] if x.get("regiao_br") else [])
    for c in eq.values():
        tm = (times or {}).get(c["equipe"]) or {}
        c["tecnicos"], c["ativos"], c["cargos"] = tm.get("tecnicos", 0), tm.get("ativos", 0), tm.get("cargos", {})
        c["supervisor"] = tm.get("supervisor") or SEM_SUPERVISOR
        c["feitas"] = max(0, c["usinas"] - c["pendentes"])
        c["pct_feitas"] = round(100 * c["feitas"] / c["usinas"]) if c["usinas"] else None
        c["regioes"], c["ufs"] = sorted(c["regioes"]), sorted(c["ufs"])
    return list(eq.values())


# Somados por supervisor (Levi, 08/10/2026: "além de por equipe e tabela, adicione mais um botão (por supervisor). Faça
# o mesmo na tela permissões de trabalho"). Só os números que se somam; o % e as feitas são refeitos sobre a soma.
_SOMA_SUPERVISOR = ("usinas", "pendentes", "nunca", "sem_ronda", "longa_pendente", "rondas", "ok", "sem_os",
                    "incompleta", "pts", "parada", "tecnicos", "ativos")


def por_supervisor(cartoes) -> list[dict]:
    """Um cartão por supervisor, somando os cartões de equipe dele (`por_equipe`, já filtrados pela tela): usinas
    pendentes, % feitas, o detalhe por status, PT esperando e paradas, técnicos e equipes. O supervisor da equipe é o
    mesmo do cartão de equipe (o `supervisor_id` dos técnicos, no cadastro); equipe sem supervisor no cadastro vai para
    o cartão próprio `SEM_SUPERVISOR`."""
    g = {}
    for c in cartoes:
        nome = c.get("supervisor") or SEM_SUPERVISOR
        s = g.setdefault(nome, {"supervisor": nome, "equipes": [], "regioes": set(), "ufs": set(),
                                **dict.fromkeys(_SOMA_SUPERVISOR, 0)})
        s["equipes"].append(c["equipe"])
        for k in _SOMA_SUPERVISOR:
            s[k] += c.get(k) or 0
        s["regioes"].update(c.get("regioes") or [])
        s["ufs"].update(c.get("ufs") or [])
    for s in g.values():
        s["equipes"] = sorted(s["equipes"])
        s["n_equipes"] = len(s["equipes"])
        s["feitas"] = max(0, s["usinas"] - s["pendentes"])
        s["pct_feitas"] = round(100 * s["feitas"] / s["usinas"]) if s["usinas"] else None
        s["regioes"], s["ufs"] = sorted(s["regioes"]), sorted(s["ufs"])
    return list(g.values())


def limpar():
    _CACHE.clear()
    _LIVROS.clear()
    _CALCULOS.clear()
    _USADO.clear()
