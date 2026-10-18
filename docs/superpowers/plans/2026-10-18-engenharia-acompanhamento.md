# Acompanhamento dos ativos da Engenharia — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** na Confiabilidade, pegar e encaminhar ativos com sinal, acompanhá-los na gaveta (início, fim, diagnóstico,
comentários) e separá-los nas abas Ativos com sinal, Em acompanhamento e Encerrados, com o dado num livro novo do banco.

**Architecture:** um módulo de regras e livro (`nexus/engenharia/acompanhamento.py`, no molde de
`nexus/contratos/tratamento.py` e do cadastro de `nexus/pcm/motivos.py`) grava eventos só acrescentados e deriva o estado;
uma função pura separa os ativos nas abas a partir dos sinais e das datas das falhas que a Confiabilidade passa a entregar;
a torre monta as abas e a gaveta (um pedaço de template só, usado na página e na resposta das ações).

**Tech Stack:** Python 3, Flask, Jinja, JS sem biblioteca, pytest; banco pela API `db_performace` (`nexus/dados/livros.py`).

**Spec:** `docs/superpowers/specs/2026-10-18-engenharia-acompanhamento-design.md` (rascunho aprovado:
`docs/mockups/engenharia-acompanhamento.html`).

## Global Constraints

- Repositório público: nenhum nome de colega em código, teste ou `.md`; fixtures com nome fictício (`Ana Lima`, `Beto Souza`).
- Cor só por token do `nexus.css`, nos temas escuro e claro: nada de `#hex`/`rgba()` em CSS de tela nem em `style` de template (`tests/test_tema.py`).
- Texto da tela em pt-BR, sem emoji; comentário de código em pt-BR, dizendo o porquê.
- Endereço nunca a partir da raiz: `url_for`, `{{ raiz }}`, `|na_raiz`, `nexusRota` (`tests/test_prefixo.py`).
- Toda ação é POST e passa por `_de_outro_site()` (`nexus/torres/moldura.py`) → 403; nome e e-mail nunca em URL.
- Banco: só `livros.ler`/`livros.publicar`; relido antes de gravar (leitura que falha não grava), as duas abas sempre juntas, uma gravação por vez (`threading.Lock`); nome, e-mail e texto só cifrados (Cofre, `NEXUS_CHAVE_CADASTRO`); pessoa pelo `codigo_da_pessoa(NEXUS_PESSOA_HMAC, email)`.
- Teste nunca vai à rede: `tests/pg_falso.py` em `app.extensions["nexus_dados_sessao"]`.
- Commits só no ramo `engenharia/acompanhamento` da worktree `C:/GridcoAuto/wt/nexus-eng-acomp`; **nenhum push** (push na `main` é produção em ~2 min e só com o OK do Levi). Não reiniciar a 5070.
- Rodar na worktree, com o `.env` copiado (o `test_sem_nomes_no_repositorio.py` só roda com ele): `python -m pytest -q`.

## Review Focus

1. A API devolve tudo como texto (`ApiPGFalsa(como_texto=True)`: `"20261018"`, `"20261018.0"`, `"5.0"`): o estado tem de sair igual. Teste na Task 1.
2. O mesmo ativo com caixa ou espaço diferentes (`"ibi200-invr1.3 "` × `"IBI200-INVR1.3"`): casa pelo `canon` da dimensão de equipamento. Teste na Task 4.
3. Comentário com HTML (`<script>alert(1)</script>`) sai escapado na gaveta. Teste na Task 5.
4. Livro que ainda não existe e banco fora: a tela abre, as abas dizem "Não consegui ler os acompanhamentos" em vez de "nenhum", e nada grava. Testes nas Tasks 1 e 5.
5. Data inválida no Salvar (`"2026-02-31"`, `"18/10/2026"`, início vazio): recusa com a mensagem e nada grava. Teste na Task 2.

---

### Task 1: O livro — catálogo, leitura, estado e Pegar

**Files:**
- Create: `nexus/engenharia/acompanhamento.py`
- Modify: `nexus/dados/catalogo.py` (`FATOS`, perto de `tratamento_contestacao`; `LIVROS`, perto de `nexus_contestacoes_tratamento`), `nexus/dados/explica.py` (`RESUMO`, `PARA_QUE`)
- Test: `tests/test_engenharia_acompanhamento.py` (novo)

**Interfaces:**
- Produces:
  - `LIVRO = "nexus_engenharia_acompanhamento"`, `NOME_LIVRO = "Nexus · acompanhamento dos ativos da Engenharia"`, `ABA_DIAG = "dim_diagnostico"`, `ABA_EVENTO = "fato_acompanhamento_ativo"`
  - `CAB_EVENTO = ("id", "registrado_em", "data_id", "acompanhamento_id", "evento", "codigo_ativo", "equipamento_id", "usina_id", "usina_ligada_por", "pessoa_hmac", "responsavel_hmac", "diagnostico_id", "data_id_inicio_analise", "data_id_fim_analise", "nivel_na_entrada", "falhas_30d_qtd", "falhas_7d_qtd", "dados_cifrados")`
  - `CAB_DIAG = ("diagnostico_id", "nome", "descricao", "criado_em", "alterado_em", "excluido", "alterado_por_hmac")`
  - `EVENTOS = ("pegou", "encaminhou", "dados", "comentario", "encerrou")`; `CADASTRO_INICIAL = (("Comunicação", ""), ("Disjuntor", ""))`; `TEXTO_MAX = 2000`; `SETOR = "engenharia"`
  - `class Recusada(ValueError)`; `limpar() -> None` (zera a cópia)
  - `ler(forcar: bool = False) -> dict` → `{"eventos": [linha crua], "diagnosticos": [linha crua], "lido_em": float | None, "erro": str}`; cópia de 60 s; banco fora devolve a última boa com `erro`, ou vazio com `erro`
  - `diagnosticos(linhas: list[dict]) -> list[dict]` → `[{"id": int, "nome": str, "descricao": str, "excluido": bool}]`; livro sem cadastro = `CADASTRO_INICIAL` com ids 1 e 2
  - `estado(eventos: list[dict]) -> dict[str, dict]` → `{acompanhamento_id: A}`, com `A = {"id", "cod", "equipamento_id": int|None, "usina_id": int|None, "responsavel": {"hmac", "nome"}, "encaminhado_por": str, "desde": datetime (gravação do 1º evento, BRT), "inicio": date, "fim": date|None, "diagnostico_id": int|None, "comentarios": [{"quando": datetime, "quando_txt": "17/10/2026 às 09:12", "nome", "texto"}] (o mais novo primeiro), "aberto": bool, "encerrado_em": datetime|None, "nivel_entrada": str, "falhas30_entrada": int|None, "falhas7_entrada": int|None}`; ordem dos eventos = ordem de gravação (como `tratamento.estado`)
  - `codigo(usuario: dict | None) -> str | None`; `pode_agir(setor: dict | None, admin: bool) -> bool` (administrador, ou o nome do setor sem acento nem caixa == `SETOR`)
  - `pegar(ativo: dict, usuario: dict | None, pode: bool) -> dict` (o evento gravado); `ativo = {"cod", "usina_id", "usina_ligada_por", "nivel", "nFalha", "n7"}` (o item de `sinais` da Confiabilidade)

- [ ] **Step 1: Write the failing tests** (fixture `banco`: `ApiPGFalsa()`, `app.config.update(GRIDCO_DB_API="http://pg.falso", NEXUS_CHAVE_CADASTRO=gerar_chave(), NEXUS_PESSOA_HMAC="hmac-teste", GRIDCO_SQL_TOKEN="tk")`, `app.extensions["nexus_dados_sessao"] = api`, dentro de `app.app_context()`, `A.limpar()` antes e depois; `banco_texto`: o mesmo com `ApiPGFalsa(como_texto=True)`; `ATIVO = {"cod": "IBI200-INVR1.3", "usina_id": 1, "usina_ligada_por": "de-para do Fracttal", "nivel": "critico", "nFalha": 5, "n7": 3}`; `ANA`/`BETO` como nas Contestações. Ajudantes do arquivo, usados nas tasks seguintes: `_como(cli, usuario, admin=False)` (a sessão, como nas Contestações); `_a()` = o único acompanhamento de `A.estado(A.ler(forcar=True)["eventos"])` e `_aid()` = o id dele; `_aid_de(cod)` = o id do acompanhamento aberto do código, ou `None`; `_lista(html)` = o trecho de `<div class="eg-itens">` até o fim da lista da aba; `_dec(fracttal_id, setor_id, hmac, quando)` = uma decisão no formato de `setores._decisao`)

```python
def test_catalogo_registra_o_livro_e_o_fato():
    l = catalogo.LIVRO_POR_NOME[A.LIVRO]
    assert l.abas == (A.ABA_DIAG, A.ABA_EVENTO) and all(catalogo.aba_segue_a_regra(x) for x in l.abas)
    f = catalogo.POR_ID["acompanhamento_ativo"]
    assert f.area == "engenharia" and f.tipo == "transacao" and f.chave == ("id",)
    assert f.fontes == (f"{A.LIVRO} · {A.ABA_EVENTO}",)
    assert {m.coluna for m in f.medidas} == {"falhas_30d_qtd", "falhas_7d_qtd"}
    assert "acompanhamento_ativo" in explica.RESUMO and "acompanhamento_ativo" in explica.PARA_QUE

def test_pegar_comeca_com_a_pessoa_e_o_inicio_hoje(banco):
    A.pegar(ATIVO, ANA, pode=True)
    (a,) = A.estado(A.ler(forcar=True)["eventos"]).values()
    assert a["aberto"] and a["responsavel"]["nome"] == "Ana Lima" and a["cod"] == "IBI200-INVR1.3"
    assert a["inicio"] == datetime.now(BRT).date() and a["fim"] is None and a["nivel_entrada"] == "critico"
    assert a["falhas30_entrada"] == 5 and a["falhas7_entrada"] == 3 and a["equipamento_id"] == equipamento_id("IBI200-INVR1.3")
    assert [d["nome"] for d in A.diagnosticos(banco.linhas(A.LIVRO, A.ABA_DIAG))] == ["Comunicação", "Disjuntor"]
    ev = banco.linhas(A.LIVRO, A.ABA_EVENTO)
    assert len(ev) == 1 and list(ev[0]) == list(A.CAB_EVENTO)
    claro = json.dumps(ev, ensure_ascii=False, default=str).lower()
    assert "ana lima" not in claro and ANA["email"] not in claro

def test_pegar_recusa_sem_poder_sem_login_e_ativo_ja_acompanhado(banco):
    with pytest.raises(A.Recusada, match="Engenharia"):
        A.pegar(ATIVO, ANA, pode=False)
    with pytest.raises(A.Recusada, match="login"):
        A.pegar(ATIVO, None, pode=True)
    A.pegar(ATIVO, ANA, pode=True)
    with pytest.raises(A.Recusada, match="já está com Ana Lima"):
        A.pegar(dict(ATIVO, cod=" ibi200-invr1.3"), BETO, pode=True)

def test_leitura_como_texto_da_o_mesmo_estado(banco_texto):     # Review Focus 1: a API devolveu tudo como texto
    A.pegar(ATIVO, ANA, pode=True)
    assert isinstance(banco_texto.linhas(A.LIVRO, A.ABA_EVENTO)[0]["falhas_30d_qtd"], str)
    a = _a()
    assert a["falhas30_entrada"] == 5 and a["usina_id"] == 1 and a["inicio"] == datetime.now(BRT).date()
    assert a["equipamento_id"] == equipamento_id("IBI200-INVR1.3") and a["aberto"]
    assert [d["id"] for d in A.diagnosticos(banco_texto.linhas(A.LIVRO, A.ABA_DIAG))] == [1, 2]

def test_banco_fora_nao_grava_e_a_leitura_diz(banco, monkeypatch):    # Review Focus 4
    monkeypatch.setattr(banco, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("fora")))
    assert A.ler(forcar=True)["erro"] and A.ler()["eventos"] == []
    with pytest.raises(requests.ConnectionError):
        A.pegar(ATIVO, ANA, pode=True)
    assert banco.syncs == 0
```

- [ ] **Step 2: Run** `python -m pytest -q tests/test_engenharia_acompanhamento.py` — Expected: FAIL (`ModuleNotFoundError: nexus.engenharia.acompanhamento`).

- [ ] **Step 3: Implement** `acompanhamento.py` (Task 1 interfaces) e o catálogo.
  - Cifra: `dados_cifrados = Cofre.cifrar(json.dumps({"quem": {"nome", "email"}, "responsavel": nome, "texto": ...}), f"banco/engenharia_acompanhamento/{id}/dados")`; chave ausente = `Recusada` antes de gravar.
  - `_publicar(eventos, diags)` grava `{ABA_DIAG: ..., ABA_EVENTO: ...}` numa chamada só; o cadastro sem linha no banco vai como o `CADASTRO_INICIAL`.
  - `equipamento_id(canon(cod))` de `nexus/dados/equipamento.py`; `codigo_ativo` gravado como `canon(cod)`.
  - Catálogo: `Fato("acompanhamento_ativo", "Acompanhamento dos ativos da Engenharia", "engenharia", "nexus_engenharia_acompanhamento · fato_acompanhamento_ativo", "1 linha = 1 evento (pegou, encaminhou, dados, comentario, encerrou) sobre 1 acompanhamento de 1 ativo", _d(data=("id", "data_id (o dia de Brasília do evento); papéis data_id_inicio_analise e data_id_fim_analise"), usina=("id", "usina_id (a ligação da Confiabilidade com o cadastro)"), equipamento=("id", "equipamento_id (código do ativo)"), pessoa=("cod", "pessoa_hmac (quem fez) e responsavel_hmac (quem acompanha)")), tipo="transacao", chave=("id",), medidas=_m((("falhas_30d_qtd", "qtd", "semi"), ("falhas_7d_qtd", "qtd", "semi"))), fontes=(...,), janela_origem="o Nexus é a fonte", observacao=...)`; `Livro("nexus_engenharia_acompanhamento", ("dim_diagnostico", "fato_acompanhamento_ativo"), "a cada pegar, encaminhar, salvar, comentário e mudança no cadastro dos diagnósticos (tela Engenharia > Confiabilidade)", "nexus/engenharia/acompanhamento.py, pela tela Engenharia > Confiabilidade", False, "registrado em 18/10/2026 antes da 1ª gravação (regra 10): nasce no 1º Pegar, com o cadastro inicial (Comunicação, Disjuntor)")`.

- [ ] **Step 4: Run** `python -m pytest -q tests/test_engenharia_acompanhamento.py tests/test_dados_camada.py tests/test_dados_organograma.py` — Expected: PASS.

- [ ] **Step 5: Commit** `git add nexus/engenharia/acompanhamento.py nexus/dados/catalogo.py nexus/dados/explica.py tests/test_engenharia_acompanhamento.py && git commit -m "feat(engenharia): o livro do acompanhamento dos ativos - catalogo, leitura, estado e Pegar"`

### Task 2: Encaminhar, Salvar (dados e encerrar) e Comentar

**Files:**
- Modify: `nexus/engenharia/acompanhamento.py`
- Test: `tests/test_engenharia_acompanhamento.py`

**Interfaces:**
- Consumes: Task 1 (`ler`, `estado`, `_publicar`, `Recusada`).
- Produces:
  - `encaminhar(ativo: dict, para_hmac: str, usuario: dict | None, pode: bool, pessoas: list[dict]) -> dict` — `pessoas` = `[{"hmac", "nome"}]` da Engenharia (Task 3); ativo livre começa o acompanhamento com quem recebeu; ativo com acompanhamento aberto troca quem acompanha
  - `salvar(acompanhamento_id: str, inicio: str, fim: str, diagnostico_id: str, usuario: dict | None, pode: bool, hoje: date | None = None) -> dict` — datas `"AAAA-MM-DD"` (o `<input type="date">`); com `fim` grava `encerrou`, sem `fim` grava `dados`; nada mudou = `Recusada("Nada mudou")`
  - `comentar(acompanhamento_id: str, texto: str, usuario: dict | None, pode: bool) -> dict`

- [ ] **Step 1: Write the failing tests**

```python
PESSOAS = lambda: [{"hmac": A.codigo(ANA), "nome": "Ana Lima"}, {"hmac": A.codigo(BETO), "nome": "Beto Souza"}]

def test_encaminhar_so_para_a_engenharia_e_troca_quem_acompanha(banco):
    A.encaminhar(ATIVO, A.codigo(BETO), ANA, True, PESSOAS())
    (a,) = A.estado(A.ler(forcar=True)["eventos"]).values()
    assert a["responsavel"]["nome"] == "Beto Souza" and a["encaminhado_por"] == "Ana Lima" and a["aberto"]
    with pytest.raises(A.Recusada, match="Engenharia"):
        A.encaminhar(ATIVO, "hmac-de-fora", ANA, True, PESSOAS())
    with pytest.raises(A.Recusada, match="já está com Beto Souza"):
        A.encaminhar(ATIVO, A.codigo(BETO), ANA, True, PESSOAS())
    A.encaminhar(ATIVO, A.codigo(ANA), ANA, True, PESSOAS())          # assumir = encaminhar para si
    assert len(A.estado(A.ler(forcar=True)["eventos"])) == 1          # o mesmo acompanhamento

def test_salvar_muda_e_encerra_so_com_fim_e_diagnostico(banco):
    A.pegar(ATIVO, ANA, pode=True); aid = _aid()
    hoje = date(2026, 10, 18)
    A.salvar(aid, "2026-10-15", "", "1", BETO, True, hoje)            # qualquer um da Engenharia muda
    assert _a()["inicio"] == date(2026, 10, 15) and _a()["diagnostico_id"] == 1 and _a()["aberto"]
    for ini, fim, diag, erro in (("2026-10-15", "2026-10-17", "", "diagnóstico"), ("2026-10-15", "2026-10-14", "1", "antes do início"),
                                 ("2026-10-15", "2026-10-19", "1", "depois de hoje"), ("2026-10-19", "", "1", "depois de hoje")):
        with pytest.raises(A.Recusada, match=erro):
            A.salvar(aid, ini, fim, diag, ANA, True, hoje)
    A.salvar(aid, "2026-10-15", "2026-10-17", "1", ANA, True, hoje)
    assert not _a()["aberto"] and _a()["fim"] == date(2026, 10, 17)
    with pytest.raises(A.Recusada, match="encerrado"):
        A.comentar(aid, "depois", ANA, True)

def test_data_invalida_recusa_e_nao_grava(banco):                 # Review Focus 5
    A.pegar(ATIVO, ANA, pode=True); n = len(banco.linhas(A.LIVRO, A.ABA_EVENTO))
    for ini in ("2026-02-31", "18/10/2026", ""):
        with pytest.raises(A.Recusada, match="início"):
            A.salvar(_aid(), ini, "", "1", ANA, True, date(2026, 10, 18))
    assert len(banco.linhas(A.LIVRO, A.ABA_EVENTO)) == n

def test_comentario_cifrado_com_hora_quem_e_limites(banco):
    A.pegar(ATIVO, ANA, pode=True)
    A.comentar(_aid(), "  Datalogger   perde o link\n\nTrocar cabo ", BETO, True)
    (c,) = _a()["comentarios"]
    assert c["texto"] == "Datalogger perde o link\n\nTrocar cabo" and c["nome"] == "Beto Souza" and "às" in c["quando_txt"]
    with pytest.raises(A.Recusada, match="Escreva"):
        A.comentar(_aid(), "   ", ANA, True)
    with pytest.raises(A.Recusada, match="2000"):
        A.comentar(_aid(), "x" * 2001, ANA, True)
    assert "datalogger" not in json.dumps(banco.linhas(A.LIVRO, A.ABA_EVENTO), default=str).lower()
```

- [ ] **Step 2: Run** `python -m pytest -q tests/test_engenharia_acompanhamento.py` — Expected: FAIL (`AttributeError: ... 'encaminhar'`).
- [ ] **Step 3: Implement** `encaminhar`, `salvar`, `comentar` (texto normalizado como `tratamento.atualizar`; regras do spec, "As regras" 2 a 5; diagnóstico excluído não se escolhe).
- [ ] **Step 4: Run** the same command — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -am "feat(engenharia): encaminhar, salvar (encerrar com fim e diagnostico) e comentar o acompanhamento"`

### Task 3: Cadastro de diagnósticos e as pessoas da Engenharia

**Files:**
- Modify: `nexus/engenharia/acompanhamento.py`
- Test: `tests/test_engenharia_acompanhamento.py`

**Interfaces:**
- Produces:
  - `criar_diagnostico(nome: str, descricao: str, usuario, pode: bool) -> dict`; `mudar_diagnostico(diagnostico_id: int, nome: str, descricao: str, usuario, pode: bool) -> dict`; `excluir_diagnostico(diagnostico_id: int, usuario, pode: bool) -> dict` — id = maior + 1 (nunca volta); nome de 2 a 60 caracteres, único sem acento nem caixa; descrição até 300; excluir marca `excluido = "sim"`
  - `pessoas_da_engenharia() -> list[dict]` → `[{"hmac", "nome"}]` pelo nome: as pessoas cuja última decisão (`setores.vigentes`) é o setor de nome `SETOR`, com `pessoa_hmac`; o nome pelo `fracttal_id` em `fracttal_pessoal.ler_pessoal()["pessoas"]` (sem nome no Fracttal: `"(sem nome no Fracttal)"`)

- [ ] **Step 1: Write the failing tests**

```python
def test_cadastro_cria_renomeia_e_exclui_sem_reaproveitar_id(banco):
    A.criar_diagnostico("Proteção", "", ANA, True)
    A.mudar_diagnostico(3, "Proteção (relé)", "Relé de proteção atuando", ANA, True)
    A.excluir_diagnostico(3, ANA, True)
    A.criar_diagnostico("Inversor", "", ANA, True)
    ds = A.diagnosticos(A.ler(forcar=True)["diagnosticos"])
    assert [(d["id"], d["nome"], d["excluido"]) for d in ds] == [
        (1, "Comunicação", False), (2, "Disjuntor", False), (3, "Proteção (relé)", True), (4, "Inversor", False)]
    with pytest.raises(A.Recusada, match="já existe"):
        A.criar_diagnostico("comunicacao", "", ANA, True)
    with pytest.raises(A.Recusada):
        A.criar_diagnostico("A", "", ANA, True)
    with pytest.raises(A.Recusada, match="Engenharia"):
        A.criar_diagnostico("Outro", "", ANA, False)

def test_pessoas_da_engenharia_pelo_setor_e_o_nome_do_fracttal(app, monkeypatch):
    setores = [{"setor_id": 1, "nome": "Engenharia", "excluido": False}, {"setor_id": 2, "nome": "Performance", "excluido": False}]
    decisoes = [_dec(10, 1, "h10", "2026-10-12T10:00:00Z"), _dec(11, 2, "h11", "2026-10-12T10:00:00Z"),
                _dec(12, 1, "h12", "2026-10-12T10:00:00Z"), _dec(12, None, "h12", "2026-10-13T10:00:00Z")]
    monkeypatch.setattr(S, "ler", lambda *a, **k: {"setores": setores, "decisoes": decisoes, "lido_em": 1, "erro": ""})
    monkeypatch.setattr(FP, "ler_pessoal", lambda *a, **k: {"pessoas": [{"id": 10, "nome": "Ana Lima"}, {"id": 11, "nome": "Beto Souza"}], "erro": ""})
    assert A.pessoas_da_engenharia() == [{"hmac": "h10", "nome": "Ana Lima"}]
```

- [ ] **Step 2: Run** `python -m pytest -q tests/test_engenharia_acompanhamento.py` — Expected: FAIL.
- [ ] **Step 3: Implement** (as duas abas de novo a cada gravação, como em Task 1).
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -am "feat(engenharia): cadastro de diagnosticos e as pessoas da Engenharia para o encaminhar"`

### Task 4: As contas — falhas de cada ativo e a separação das abas

**Files:**
- Modify: `nexus/engenharia/confiabilidade.py` (`calcular`), `nexus/engenharia/acompanhamento.py`
- Test: `tests/test_engenharia_confiabilidade.py` (falhasEm), `tests/test_engenharia_acompanhamento.py` (separar)

**Interfaces:**
- Produces:
  - `calcular(...)["falhasEm"]: dict[str, list[dict]]` — chave `canon(cod)`; `[{"quando": datetime (UTC), "os": str (wo_folio), "tipo": str}]` em ordem crescente; só `TIPOS_SINAL`, fora serviço (`RX_SERVICO`) e teste; **todo o período** lido (não só os 30 dias)
  - `separar(sinais: list[dict], acomps: dict[str, dict], falhas_em: dict[str, list[dict]]) -> dict` → `{"sinal": [ativo + {"ja": {"diagnostico_id", "fim"} | None}], "aberto": [{"acomp", "ativo": dict | None, "novas": [falha]}], "encerrado": [{"acomp", "ativo": dict | None, "voltou": datetime | None}]}`; casa pelo `canon(cod)`; "novas" = `quando > acomp["desde"]`; "voltou" = 1ª falha com `quando >= 00:00 (BRT) do dia seguinte ao fim`; ordem de "aberto": mais novas, depois nível (crítico, atenção, monitorar, sem sinal), depois `desde`; de "encerrado": `encerrado_em` decrescente

- [ ] **Step 1: Write the failing tests**

```python
# test_engenharia_confiabilidade.py
def test_falhas_em_tem_so_as_que_contam_no_sinal_e_todo_o_periodo():
    linhas = [_os("IBI200-INVR1.3", 40), _os("IBI200-INVR1.3", 2, tipo="Religamento"),
              _os("IBI200-INVR1.3", 3, tarefa="Limpeza do inversor"), _os("IBI200-INVR1.3", 1)]
    f = C.calcular(linhas, _onde, AGORA)["falhasEm"]["IBI200-INVR1.3"]
    assert [round((AGORA - x["quando"]).days) for x in f] == [40, 1] and f[0]["tipo"] == "Corretiva"

# test_engenharia_acompanhamento.py (acomps montados à mão, sem banco)
def _ac(cod, desde, inicio, fim=None, diag=None):
    return {"id": cod, "cod": cod, "desde": desde, "inicio": inicio, "fim": fim, "diagnostico_id": diag,
            "aberto": fim is None, "encerrado_em": desde if fim else None,
            "responsavel": {"hmac": "h-ana", "nome": "Ana Lima"}, "nivel_entrada": "critico"}
def _f(quando):
    return {"quando": quando, "os": "1", "tipo": "Corretiva"}
D = lambda d, h=8, m=0: datetime(2026, 10, d, h, m, tzinfo=BRT)

def test_separar_tira_o_acompanhado_e_o_encerrado_sem_falha_nova():
    sinais = [{"cod": c, "nivel": "atencao"} for c in ("IBI200-INVR1.3", "IBI200-TRK07", "IBI200-INV02")]
    acomps = {"a1": _ac("IBI200-INVR1.3", D(16), date(2026, 10, 16)),
              "a2": _ac("IBI200-TRK07", D(1), date(2026, 10, 1), fim=date(2026, 10, 10), diag=2)}
    s = A.separar(sinais, acomps, {"IBI200-TRK07": [_f(D(9))]})
    assert [x["cod"] for x in s["sinal"]] == ["IBI200-INV02"] and s["sinal"][0]["ja"] is None
    assert [x["acomp"]["cod"] for x in s["aberto"]] == ["IBI200-INVR1.3"]
    assert [(x["acomp"]["cod"], x["voltou"]) for x in s["encerrado"]] == [("IBI200-TRK07", None)]

def test_encerrado_volta_so_com_falha_do_dia_seguinte_ao_fim():
    sinais, acomps = [{"cod": "IBI200-TRK07", "nivel": "atencao"}], {"a2": _ac("IBI200-TRK07", D(1), date(2026, 10, 1), fim=date(2026, 10, 10), diag=2)}
    assert A.separar(sinais, acomps, {"IBI200-TRK07": [_f(D(10, 23))]})["sinal"] == []
    s = A.separar(sinais, acomps, {"IBI200-TRK07": [_f(D(11, 0, 30))]})
    assert s["sinal"][0]["ja"] == {"diagnostico_id": 2, "fim": date(2026, 10, 10)} and s["encerrado"][0]["voltou"] == D(11, 0, 30)

def test_falha_nova_conta_da_gravacao_do_inicio_do_acompanhamento():
    acomps = {"a1": _ac("IBI200-INVR1.3", D(16, 14, 20), date(2026, 10, 10))}
    (x,) = A.separar([{"cod": "IBI200-INVR1.3", "nivel": "critico"}], acomps,
                     {"IBI200-INVR1.3": [_f(D(12)), _f(D(17))]})["aberto"]
    assert [f["quando"] for f in x["novas"]] == [D(17)]

def test_codigo_casa_sem_caixa_nem_espaco():                      # Review Focus 2
    s = A.separar([{"cod": " ibi200-invr1.3", "nivel": "critico"}], {"a1": _ac("IBI200-INVR1.3", D(16), date(2026, 10, 16))}, {})
    assert s["sinal"] == [] and s["aberto"][0]["ativo"]["cod"] == " ibi200-invr1.3"
```

- [ ] **Step 2: Run** `python -m pytest -q tests/test_engenharia_confiabilidade.py tests/test_engenharia_acompanhamento.py` — Expected: FAIL.
- [ ] **Step 3: Implement** `falhasEm` no laço de `calcular` (as linhas já agrupadas por código) e `separar`.
- [ ] **Step 4: Run** the same — Expected: PASS (inclusive os testes antigos da Confiabilidade).
- [ ] **Step 5: Commit** `git commit -am "feat(engenharia): as falhas de cada ativo e a separacao das abas do acompanhamento"`

### Task 5: A tela — abas, filtros, listas e a gaveta

**Files:**
- Modify: `nexus/torres/engenharia/__init__.py` (`ABAS`, `confiabilidade()`), `nexus/torres/engenharia/templates/engenharia/confiabilidade.html`, `nexus/static/engenharia.css`
- Create: `nexus/torres/engenharia/templates/engenharia/_gaveta.html` (o conteúdo da gaveta sai do laço do template para cá)
- Test: `tests/test_engenharia_acompanhamento.py`

**Interfaces:**
- Consumes: `A.ler`, `A.estado`, `A.diagnosticos`, `A.pode_agir`, `A.pessoas_da_engenharia`, `A.separar`, `calcular(...)["falhasEm"]`, `setor_telas.acesso()`.
- Produces:
  - `ABAS = (("ativos", "Ativos com sinal"), ("acompanhamento", "Em acompanhamento"), ("encerrados", "Encerrados"), ("indicadores", "Indicadores"), ("diagnosticos", "Diagnósticos"))` — `diagnosticos` só para quem `pode`
  - filtro novo `quem` (o `responsavel_hmac`), só nas abas `acompanhamento` ("Quem acompanha") e `encerrados` ("Quem acompanhava"); os de hoje valem nas três listas; o `nivel` é o de agora em `acompanhamento` e o `nivel_entrada` em `encerrados`
  - `_gaveta.html` recebe `a` (o ativo: o item de `sinais`, senão o de `ativos`, senão `{"cod", "usina"}` do acompanhamento), `acomp` (aberto ou `None`), `anteriores`, `novas`, `pode`, `pessoas`, `diags`, `meta`, `janela`, `h`, `pct`, `aviso`, `erro`; blocos e textos do spec ("A gaveta do ativo") e do rascunho
  - o cartão vira `<article class="eg-item">` com `<button class="eg-item-abrir" data-gaveta=...>` (botão dentro de botão não vale) e, na aba `ativos` e para quem `pode`, `.eg-item-acoes` com "Pegar para acompanhar" e "Encaminhar" (este abre a gaveta no seletor)
  - classes novas em `engenharia.css`, só com tokens: `eg-acomp`, `eg-acomp-dono`, `eg-acomp-aviso`, `eg-acomp-campos` (uma coluna abaixo de 640 px), `eg-acomp-tl`, `eg-ant`, `eg-sem`, `eg-item-acoes`, `eg-pill--ok`, `eg-tag--ok`

- [ ] **Step 1: Write the failing tests** (fixture `tela`: `banco` + `os_falhas.linhas`/`estado`/`pedir_releitura`, `torre._onde_do_cadastro` e o relógio em `AGORA` (06/10/2026 15:00 UTC) como em `test_tela_de_confiabilidade`; as OS dão sinal a `IBI200-INVR1.3` (falhas de 1, 2, 3 e 10 dias atrás), `IBI200-TRK07` (5 e 20) e `IBI200-INV02` (1 e 4); `ST.acesso` devolvendo o setor `{"id": 1, "nome": "Engenharia"}`; `A.pessoas_da_engenharia` devolvendo `PESSOAS()`; no livro, gravados pelo próprio módulo: aberto em `IBI200-INVR1.3` com Ana Lima e encerrado em `IBI200-TRK07` com fim de hoje e diagnóstico 2 (sem falha depois do fim); `IBI200-INV02` livre; a fixture devolve o `ApiPGFalsa`)

```python
def test_tela_tem_as_abas_e_os_numeros(tela, cliente):
    html = _como(cliente, ANA).get("/t/engenharia/confiabilidade").get_data(as_text=True)
    assert "Em acompanhamento <i>1</i>" in html and "Encerrados <i>1</i>" in html and ">Diagnósticos<" in html
    assert "Pegar para acompanhar" in html and "IBI200-TRK07" not in _lista(html)
    ac = cliente.get("/t/engenharia/confiabilidade?aba=acompanhamento").get_data(as_text=True)
    assert "IBI200-INVR1.3" in ac and "Com Ana Lima" in ac and 'name="quem"' in ac
    assert 'name="quem"' not in html

def test_filtro_quem_acompanha(tela, cliente):
    url = f"/t/engenharia/confiabilidade?aba=acompanhamento&quem={A.codigo(BETO)}"
    assert "IBI200-INVR1.3" not in _lista(_como(cliente, ANA).get(url).get_data(as_text=True))

def test_quem_nao_e_da_engenharia_le_sem_botoes(tela, cliente, monkeypatch):
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(), "setor": {"id": 2, "nome": "Performance"}, "erro": ""})
    html = _como(cliente, BETO).get("/t/engenharia/confiabilidade?aba=acompanhamento").get_data(as_text=True)
    assert "IBI200-INVR1.3" in html and "Pegar para acompanhar" not in html and "Salvar comentário" not in html and ">Diagnósticos<" not in html

def test_comentario_com_html_sai_escapado(tela, cliente):          # Review Focus 3
    A.comentar(_aid_de("IBI200-INVR1.3"), "<script>alert(1)</script>", ANA, True)
    html = _como(cliente, ANA).get("/t/engenharia/confiabilidade?aba=acompanhamento").get_data(as_text=True)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "<script>alert(1)" not in html

def test_banco_fora_a_tela_abre_e_avisa(tela, cliente, monkeypatch):   # Review Focus 4
    monkeypatch.setattr(tela, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("fora")))
    A.limpar()
    html = _como(cliente, ANA).get("/t/engenharia/confiabilidade?aba=acompanhamento").get_data(as_text=True)
    assert "Não consegui ler os acompanhamentos" in html and "Nenhum ativo em acompanhamento" not in html
```

- [ ] **Step 2: Run** `python -m pytest -q tests/test_engenharia_acompanhamento.py tests/test_engenharia_confiabilidade.py` — Expected: FAIL.
- [ ] **Step 3: Implement** a view, o template, o `_gaveta.html` e o CSS (desenho do rascunho; painel ao lado e faixa de números sobre todos os sinais, como hoje).
- [ ] **Step 4: Run** `python -m pytest -q tests/test_engenharia_acompanhamento.py tests/test_engenharia_confiabilidade.py tests/test_tema.py tests/test_prefixo.py` — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -am "feat(engenharia): abas Em acompanhamento e Encerrados, filtro Quem acompanha e o acompanhamento na gaveta"`

### Task 6: As ações na tela — rotas, gaveta que grava e o cadastro

**Files:**
- Modify: `nexus/torres/engenharia/__init__.py` (rotas), `templates/engenharia/_gaveta.html` (formulários), `templates/engenharia/confiabilidade.html` (JS e a aba Diagnósticos), `nexus/static/engenharia.css`
- Test: `tests/test_engenharia_acompanhamento.py`

**Interfaces:**
- Consumes: Tasks 1 a 5.
- Produces (todas POST, `_de_outro_site()` → 403; quem não `pode` recebe a recusa e nada grava):
  - `/t/engenharia/confiabilidade/acompanhamento/pegar` (form `cod`), `/acompanhamento/encaminhar` (`cod`, `para`), `/acompanhamento/<aid>/salvar` (`inicio`, `fim`, `diagnostico`), `/acompanhamento/<aid>/comentar` (`texto`): respondem 200 com o `_gaveta.html` do ativo, relido do banco (`A.ler(forcar=True)`), com `aviso` ("Comentário salvo.", "Salvo.", "Encerrado." e, quando houver falha depois do fim, "O ativo volta para Ativos com sinal: teve falha depois do fim.") ou `erro` (o texto da `Recusada`; banco fora: "Não consegui gravar no banco (<Tipo>). Nada mudou; tente de novo em instantes.")
  - `/t/engenharia/confiabilidade/diagnosticos/criar` (`nome`, `descricao`), `/diagnosticos/<int:did>/salvar`, `/diagnosticos/<int:did>/excluir`: 303 para `?aba=diagnosticos`, com o aviso ou o erro na sessão (chaves próprias, como `_AVISO`/`_ERRO` das Contestações)
  - JS na página: o formulário da gaveta vai por `fetch` e troca o conteúdo da gaveta pela resposta; ao fechar a gaveta depois de uma gravação, a página recarrega (listas e números); o "Pegar" do cartão grava e recarrega; o campo do fim avisa na hora, pelo `data-falhas` (os dias, `AAAA-MM-DD` de Brasília, de todas as falhas do ativo em `falhasEm`: a falha depois do fim digitado faz o ativo voltar, mesmo a de antes de ele entrar em acompanhamento, e o início pode ser mudado no mesmo formulário), "Há <n> falha(s) depois desta data de fim: o ativo volta para Ativos com sinal ao encerrar."

- [ ] **Step 1: Write the failing tests**

```python
SAME = {"Sec-Fetch-Site": "same-origin"}

def test_pegar_pela_gaveta_e_comentar(tela, cliente):
    _como(cliente, BETO)
    r = cliente.post("/t/engenharia/confiabilidade/acompanhamento/pegar", data={"cod": "IBI200-INV02"}, headers=SAME)
    assert r.status_code == 200 and "Com Beto Souza" in r.get_data(as_text=True) and "Salvar comentário" in r.get_data(as_text=True)
    aid = _aid_de("IBI200-INV02")
    r = cliente.post(f"/t/engenharia/confiabilidade/acompanhamento/{aid}/comentar", data={"texto": "Trocar cabo"}, headers=SAME)
    assert "Comentário salvo" in r.get_data(as_text=True) and "Trocar cabo" in r.get_data(as_text=True)

def test_encaminhar_lista_so_a_engenharia(tela, cliente):
    g = _como(cliente, ANA).post("/t/engenharia/confiabilidade/acompanhamento/encaminhar",
                                 data={"cod": "IBI200-INV02", "para": A.codigo(BETO)}, headers=SAME).get_data(as_text=True)
    sel = re.search(r'<select name="para".*?</select>', g, re.S).group(0)
    assert "Com Beto Souza" in g and sel.count("<option") == len(PESSOAS()) + 1      # + o "Escolha"

def test_salvar_encerra_e_avisa_quando_volta(tela, cliente):
    # INVR1.3 teve falha em 05/10 (1 dia antes de AGORA): encerrar com fim 04/10 faz o ativo voltar
    html = _como(cliente, ANA).get("/t/engenharia/confiabilidade?aba=acompanhamento").get_data(as_text=True)
    assert re.search(r'data-falhas="[^"]*2026-10-05', html)
    g = cliente.post(f"/t/engenharia/confiabilidade/acompanhamento/{_aid_de('IBI200-INVR1.3')}/salvar",
                     data={"inicio": "2026-10-01", "fim": "2026-10-04", "diagnostico": "1"}, headers=SAME).get_data(as_text=True)
    assert "Encerrado." in g and "volta para Ativos com sinal" in g

def test_acao_de_outro_site_ou_sem_poder_nao_grava(tela, cliente, monkeypatch):
    _como(cliente, ANA)
    assert cliente.post("/t/engenharia/confiabilidade/acompanhamento/pegar", data={"cod": "IBI200-INV02"},
                        headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(), "setor": {"id": 2, "nome": "Performance"}, "erro": ""})
    g = cliente.post("/t/engenharia/confiabilidade/acompanhamento/pegar", data={"cod": "IBI200-INV02"}, headers=SAME).get_data(as_text=True)
    assert "Engenharia" in g and _aid_de("IBI200-INV02") is None

def test_cadastro_pela_aba_diagnosticos(tela, cliente):
    r = _como(cliente, ANA).post("/t/engenharia/confiabilidade/diagnosticos/criar", data={"nome": "Proteção"}, headers=SAME)
    assert r.status_code == 303 and r.headers["Location"].endswith("/t/engenharia/confiabilidade?aba=diagnosticos")
    assert "Proteção" in cliente.get("/t/engenharia/confiabilidade?aba=diagnosticos").get_data(as_text=True)
```

- [ ] **Step 2: Run** `python -m pytest -q tests/test_engenharia_acompanhamento.py` — Expected: FAIL (404 nas rotas).
- [ ] **Step 3: Implement** rotas, formulários, a aba Diagnósticos (editar na própria linha, como o Cadastro de motivos do PCM) e o JS.
- [ ] **Step 4: Run** `python -m pytest -q tests/test_engenharia_acompanhamento.py tests/test_tema.py tests/test_prefixo.py tests/test_auth.py` — Expected: PASS (inclusive `test_toda_rota_nao_publica_exige_login`).
- [ ] **Step 5: Commit** `git commit -am "feat(engenharia): pegar, encaminhar, salvar e comentar pela gaveta, e o cadastro de diagnosticos"`

### Task 7: Documentação, a suíte inteira e a prova de tela

**Files:**
- Modify: `nexus/torres/engenharia/CLAUDE.md` (seção nova "Acompanhamento (18/10/2026)": pedido, regras, o dado, como provar), `nexus/torres/engenharia/__init__.py` (docstring), `nexus/dados/CLAUDE.md` (linha na tabela "O que existe"), `CLAUDE.md` da raiz (a linha da Engenharia), `nexus/torres/CLAUDE.md` (a linha `engenharia/`)

- [ ] **Step 1: Write** os `.md` (corrigir as linhas velhas, não acrescentar ao lado; sem nome de colega).
- [ ] **Step 2: Run** `python -m pytest -q` (em segundo plano se passar de 2 min) — Expected: tudo passa, `test_sem_nomes_no_repositorio.py` rodando (não "skipped").
- [ ] **Step 3: Prova de tela** com um script fora do repositório (scratchpad): o cliente de teste com o banco falso e os dados do rascunho renderiza as abas Ativos com sinal, Em acompanhamento, Encerrados e Diagnósticos; o HTML e a `nexus/static` vão a uma pasta servida por `python -m http.server`; no navegador do app, cada aba e a gaveta aberta em 1440 px e 375 px, nos temas escuro e claro (`data-tema="claro"`), sem rolagem horizontal. Expected: igual ao rascunho, nada cortado.
- [ ] **Step 4: Commit** `git commit -am "docs(engenharia): o acompanhamento dos ativos nos .md da area, dos dados e da raiz"`
