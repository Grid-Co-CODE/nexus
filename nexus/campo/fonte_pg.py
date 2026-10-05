"""A fonte das telas da torre Campo · App que já têm dado no banco do Nexus (Levi, 04/10/2026: "pode gravar na API do
PG e ligar as telas"): os fechamentos que o coletor calcula pelo Fracttal e grava na API do PG (banco_campo.py),
entregues às regras copiadas do App no formato das tabelas DELE, para `_fila_supervisao`, `_gestao_os` e
`_gestao_prioridades` rodarem sem mudar linha.

- `qualidadelog` (o registro do fechamento): só a tarefa fechada PELO APP e que não é ronda, como no App. A nota é a do
  painel (`_qualidade_os`). `pontual` não vem: é a hora de início no celular contra a programação, que o Fracttal não
  tem. A assinatura vem como dada: o App não deixa concluir sem ela.
- `rondaos` e `rondas`: só o par que liga a OS de ronda à nota da ronda na fila de verificação (o `_rondas_os_pares` do
  App). A ronda NÃO vem como finalizada: a Triagem não conta ronda que o Nexus não viu inteira.
- o resto: vazio. `serve` diz que só a `qualidadelog` está inteira (Atenção e PT são do visao.py, pelos livros).
- e só depois que a coleta cobriu TUDO (aba de atualização, `completa`): a fila de verificação inteira e as aprovadas
  dos últimos 90 dias. Na 1ª carga (04/10) a coleta tinha 40 de ~2.900 OS; mostrar as telas ali punha 2.846 tarefas em
  "fora do App" só porque o coletor ainda não tinha chegado a elas.

Nome do técnico: decifrado na hora (NEXUS_CHAVE_CADASTRO); e-mail e supervisor pelo cadastro do App, como o
`_pessoa_por_nome` da fila faz. Nada disso volta ao banco. Cópia de 5 min; banco fora do ar = a tela volta ao App.

**Desde 05/10/2026, com `NEXUS_PESSOA_HMAC`, a fonte é o que o PRÓPRIO App grava** (`livros_app.py`: a nota do painel,
não a recalculada pelo Fracttal, que batia em só 14% das tarefas). Sem a chave, segue o livro do coletor, para a tela
não perder o técnico (o livro do App traz a pessoa só como código).
"""
import threading
import time
from datetime import datetime, timezone

from . import banco_campo, livros_app, regras_app, tabelas
from .coletor import contexto_do_tecnico
from .tabelas import TabelaSoLeitura

TTL_S = 300
SERVE = frozenset({"qualidadelog"})


def _epoch(iso) -> int:
    try:
        return int(datetime.fromisoformat(str(iso)).replace(tzinfo=timezone.utc).timestamp())
    except (TypeError, ValueError):
        return 0


def registro(l: dict, nome: str = "", email: str = "") -> dict:
    """A linha do banco no formato da tabela `qualidadelog` do App (_registrar_qualidade_log + _enriquecer_qlog)."""
    fim = l.get("fim") or ""
    return {
        "PartitionKey": "q", "RowKey": "%013d_%s_%s" % (_epoch(fim), l.get("os") or "", l.get("id_tarefa")),
        "os": l.get("os") or "", "tarefa": l.get("tarefa") or "", "email": email, "nome": nome,
        "qualidade": int(l.get("nota") or 0), "xp": 0, "n_fotos": int(l.get("n_fotos") or 0),
        "n_desc": int(l.get("n_desc") or 0), "obs_ok": bool(l.get("obs_ok")), "todas_sub": bool(l.get("todas_sub")),
        "assinou": True, "sub_ok": bool(l.get("sub_ok")), "geo_ok": bool(l.get("gps_fotos")), "offline": False,
        "id_wo": str(l.get("id_os") or ""), "rev": "aprovada" if l.get("status_os") == 3 else "",
        "foi_devolvida": bool(l.get("devolvida")), "server_ts": f"{fim}.000Z" if fim else "", "dev_ts": fim,
        "nota_itens": l.get("nota_itens") or "[]", "obs_app": "", "cluster": "", "usina": "",
        "fx": "ok", "fx_tipo": l.get("tipo") or "", "fx_crit": l.get("crit") or "",
        "fx_status": int(l.get("status_os") or 0), "fx_status_tarefa": int(l.get("status_tarefa") or 0),
        "fx_area": l.get("regiao") or "", "fx_ativo": l.get("ativo") or "", "fx_codigo": l.get("codigo") or "",
        "fx_ini": l.get("inicio") or "", "fx_final": fim, "fx_review": l.get("verificacao") or "",
        "fx_pct": 100, "fx_dur_prev_min": int(l.get("dur_prev_min") or 0),
        "fx_dur_real_min": int(l.get("dur_real_min") or 0), "fx_aprov": l.get("aprovacao") or "",
        "fx_rating": int(l.get("rating") or 0)}


class Fornecedor:
    """`tabelas.usar_fornecedor(Fornecedor(config))`: chamada com o nome da tabela do App, devolve a tabela."""

    def __init__(self, config, sessao=None, ttl_s=TTL_S):
        self.base = (config.get("GRIDCO_DB_API") or banco_campo.BASE_API).rstrip("/")
        self.chave = config.get("NEXUS_CHAVE_CADASTRO")
        self.sessao, self.ttl_s = sessao, ttl_s
        self._cache = {"t": 0.0, "v": None, "atualizacao": {}}
        self._trava = threading.Lock()
        self._cofre = None
        # com a chave do código da pessoa, a fonte é o livro do App; sem ela, o do coletor
        self.chave_hmac = config.get("NEXUS_PESSOA_HMAC")
        self.do_app = bool(self.chave_hmac)
        self._cache_app = {"t": 0.0, "fech": None, "rondas": None, "em": None}

    def livros(self) -> tuple[list, list]:
        """(fechamentos, rondas) dos livros do App. Erro de leitura sobe: quem chama anota e a tela avisa."""
        import requests
        with self._trava:
            c = self._cache_app
            if c["fech"] is not None and time.time() - c["t"] < self.ttl_s:
                return c["fech"], c["rondas"]
        s = self.sessao or requests
        fech = livros_app.ler(self.base, s, livros_app.LIVRO_FECHAMENTOS)
        rondas = livros_app.ler(self.base, s, livros_app.LIVRO_RONDAS)
        em = max((str(a.get("Registrado em") or "") for a in fech), default="") or None
        with self._trava:
            self._cache_app.update(t=time.time(), fech=fech, rondas=rondas, em=em)
        return fech, rondas

    def linhas(self) -> dict:
        """{id_tarefa: linha} do banco. Erro de leitura sobe: quem chama anota e a tela avisa."""
        with self._trava:
            if self._cache["v"] is not None and time.time() - self._cache["t"] < self.ttl_s:
                return self._cache["v"]
        v, atualizacao = banco_campo.ler_tudo(self.base, self.sessao)
        with self._trava:
            self._cache.update(t=time.time(), v=v, atualizacao=atualizacao)
        return v

    def coleta(self) -> str | None:
        """Quando o coletor gravou o banco pela última vez (o frescor que a tela mostra). Com o livro do App: o
        fechamento mais recente que ele trouxe."""
        if self.do_app:
            try:
                self.livros()
            except Exception:       # noqa: BLE001
                return None
            return self._cache_app["em"]
        try:
            self.linhas()
        except Exception:       # noqa: BLE001
            return None
        return self._cache["atualizacao"].get("publicado_em")

    def limpar(self):
        with self._trava:
            self._cache.update(t=0.0, v=None, atualizacao={})
            self._cache_app.update(t=0.0, fech=None, rondas=None, em=None)

    def completa(self) -> bool:
        """A última coleta cobriu a fila inteira e as aprovadas da janela? Antes disso, o número sai pela metade. O livro
        do App é inteiro por construção (o registro dos 90 dias, trocado de uma vez a cada rodada)."""
        if self.do_app:
            try:
                return bool(self.livros()[0])
            except Exception:       # noqa: BLE001
                return False
        try:
            self.linhas()
        except Exception:       # noqa: BLE001
            return False
        return str(self._cache["atualizacao"].get("completa") or "").strip().lower() == "sim"

    def serve(self, nome) -> bool:
        if nome not in SERVE:
            return False
        if self.do_app:
            return self.completa()
        try:
            return self.completa() and any(_do_registro(l) for l in self.linhas().values())
        except Exception:       # noqa: BLE001 — banco fora do ar: a tela fica no painel do App
            return False

    def __call__(self, nome):
        if self.do_app:
            return self._do_app(nome)
        if nome == "qualidadelog":
            return TabelaSoLeitura(nome, self._registros())
        if nome == "rondaos":
            return TabelaSoLeitura(nome, [_ronda_os(l) for l in self._rondas_do_banco()])
        if nome == "rondas":
            return TabelaSoLeitura(nome, [_ronda(l, self._nome(l)) for l in self._rondas_do_banco()])
        return TabelaSoLeitura(nome, [])

    def _do_app(self, nome):
        fech, rondas = self.livros()
        if nome == "qualidadelog":
            try:
                quem = livros_app.pessoas_por_codigo(self.chave_hmac)
            except Exception:       # noqa: BLE001 — sem o cadastro do App, sai sem e-mail (e sem supervisor)
                quem = {}
            out = []
            for a in fech:
                em, nm = quem.get(str(a.get("Técnico (HMAC)") or "").split(";")[0].strip(), ("", ""))
                out.append(livros_app.registro(a, em, nm))
            return TabelaSoLeitura(nome, out)
        com_os = [r for r in rondas if r.get("OS") and r.get("Data")]
        if nome == "rondaos":
            return TabelaSoLeitura(nome, [livros_app.ronda_os(r) for r in com_os])
        if nome == "rondas":
            return TabelaSoLeitura(nome, [livros_app.ronda(r) for r in com_os])
        return TabelaSoLeitura(nome, [])

    # ── pessoas: na hora, nunca no banco ───────────────────────────────────────────────────────────────────────────
    def _nome(self, l) -> str:
        cifrado = l.get("tecnico_cifrado")
        if not cifrado or not self.chave:
            return ""
        from ..cadastro.cifra import CifraErro, Cofre
        try:
            self._cofre = self._cofre or Cofre(self.chave)
            return self._cofre.decifrar(cifrado, contexto_do_tecnico(l.get("id_tarefa")))
        except CifraErro:
            return ""

    def _registros(self) -> list:
        try:
            por_nome = regras_app._pessoa_por_nome()
        except Exception:       # noqa: BLE001 — sem o cadastro do App, sai sem e-mail (e sem supervisor)
            por_nome = {}
        out = []
        for l in self.linhas().values():
            if not _do_registro(l):
                continue
            nome = self._nome(l)
            out.append(registro(l, nome, (por_nome.get(regras_app._norm(nome)) or {}).get("email") or ""))
        return out

    def _rondas_do_banco(self) -> list:
        return [l for l in self.linhas().values() if l.get("ronda") and l.get("ronda_dia") and l.get("os")]


def coleta() -> str | None:
    """O frescor da fonte ligada agora (None quando a fonte não é o banco do Nexus)."""
    f = tabelas.fornecedor()
    return f.coleta() if hasattr(f, "coleta") else None


def _do_registro(l) -> bool:
    return bool(l.get("pelo_app")) and not l.get("ronda") and l.get("nota") is not None


def _ronda_os(l) -> dict:
    return {"PartitionKey": "os", "RowKey": str(l["os"]), "folio": str(l["os"]), "id_work_order": l.get("id_os"),
            "usina": l.get("ronda_usina") or "", "data": l.get("ronda_dia"), "tipo": "", "email": "",
            "ativo": l.get("ativo") or ""}


def _ronda(l, nome) -> dict:
    # sem `finalizada`: o par serve à fila; a Triagem conta só ronda finalizada, e esta o Nexus não viu inteira
    return {"PartitionKey": l.get("ronda_dia"), "RowKey": f"nexus-{l['os']}", "email": "", "nome": nome,
            "usina": l.get("ronda_usina") or "", "cluster": l.get("equipe") or "", "qualidade": l.get("nota"),
            "falhas": "[]", "tipo": ""}
