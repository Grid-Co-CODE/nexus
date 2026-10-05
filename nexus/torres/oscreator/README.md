# OS Creator Web — clone dentro da torre OS Creator

Cópia do OS Creator Web que roda no supervisório de O&M: o serviço `os_creator/os_web` do repositório `oem`,
na porta 5090, publicado em `/os/*` pela plataforma. Foi trazida para cá em 30/09/2026, a pedido do Levi: "clone o
OS Creator Web que está no meu supervisório de OEM para a pasta do OS Creator do Nexus".

## De onde veio

- A origem é `C:\GridcoBuild\oem`, branch `pcm-no-oem`, **com o que ainda não foi commitado lá**: 35 arquivos nunca
  commitados e 32 alterados. É a versão que está no ar no supervisório, e não a do `main` do oem.
- O caminho relativo é o mesmo dos dois lados: `oem/<x>` → `nexus/torres/oscreator/<x>`. Por isso o código roda sem
  mudança:
  - o serviço sobe com a pasta atual em `os_creator`;
  - o `chamado_insp_spec` acha o `chamado_garantia` na pasta de cima.

## O que veio (120 arquivos, 1,6 MB)

- O `os_web` inteiro: 35 módulos, os templates, o static e o relay.
- Os 23 módulos do OS Creator que ele importa, direta ou indiretamente (inclusive dentro de função):
  - `api.py`;
  - as specs de chamado, inspeção, COS e solicitação;
  - os stores de modelos, observações e temas;
  - `gridco_abas`;
  - os `tickets_*`;
  - `steps/engenharia` e `steps/ui.py`.
- O pacote `chamado_garantia`, com o `assets/` (ícone, logo e fontes) e o `requirements.txt`.

## O que ficou de fora de propósito

| Arquivo | Por quê |
|---|---|
| `fracttal_login.txt` | é o login salvo do desktop |
| `assets_cache.json` | é o catálogo de ativos, dado que já vazou uma vez por instalador público |
| `tokens.txt`, `gridco_sql_token.txt` | são segredo; o código lê da variável `GRIDCO_SQL_TOKEN` ou de `%APPDATA%` |
| `app.py`, `main.py`, as outras telas de `steps/` | são o app de desktop (PyQt), e a web não usa |
| `.bat`, `.spec`, documentos | não fazem parte do serviço |

## Como foi conferido

- Original e clone foram rodados lado a lado, cada um num processo limpo:
  - os 58 módulos importam;
  - as 111 rotas são iguais;
  - `/os/login` responde 200, `/os/` responde 302 (vai para o login), e ícone e CSS respondem 200;
  - o clone não carrega nada de fora desta pasta.
- A suíte do Nexus continua com 206 testes passando.
- O repositório é público, então a cópia passou antes por uma varredura:
  - não achou CPF, telefone, token nem chave;
  - os únicos e-mails são 6 contatos de garantia de fabricantes, que já estão públicos no oem.

## Ligado ao Nexus (30/09/2026)

O Nexus serve o clone em `/os/*`, **dentro do próprio processo**, sem segundo serviço. A ponte fica em `ponte.py`,
nesta pasta.

- **Login:** a ponte é uma rota do Nexus, então quem não entrou no Nexus para no portão dele. Depois disso, o login
  do Fracttal é o do próprio OS Creator, por pessoa.
- **Telas da torre:** cada uma (`/t/os/<tela>`) leva ao OS Creator na seção dela.

  | Tela da torre | Abre em |
  |---|---|
  | Início | `/os/` |
  | Histórico de OS | `/os/historico` |
  | Ativos Fracttal | `/os/ativos` |
  | Performance | `/os/performance` |
  | COS | `/os/cos` |
  | PCM | `/os/setor/pcm` |
  | Chamados | `/os/chamados` |
  | Engenharia | `/os/engenharia` |
  | Solicitação | `/os/solicitacao` |
  | Clonagem de OS | `/os/clonar` |

  O "Setores" virou um item por setor e entrou "Ativos Fracttal" (Levi, 04/10/2026). Cada setor abre o mesmo
  endereço do card dele na tela inicial do OS Creator.
- **Menu lateral → aba nova** (Levi, 04/10: "os botões laterais devem contribuir em adicionar novas abas também na
  tela acima"). Com a casca do OS Creator de pé, o clique no menu não recarrega a página: manda à casca
  `{nexusOs: 1, url, rotulo}` e ela abre a tela numa aba nova (ou reativa a que já existe). A porta é posta no
  `abas.js` pela ponte (`_OUVIR_NEXUS`) e só ouve a janela-mãe; a ETag do abas.js ajustado leva o hash do conteúdo,
  para o navegador largar a versão anterior. Sem a casca (login do Fracttal na tela), o clique abre a página normal.
  Provado num ensaio com o abas.js ajustado de verdade: 2 abas novas, repetir não duplica, "/os/" volta ao Início.

- **Dentro da casca do Nexus, com o menu lateral** (Levi, 30/09). Cada tela da torre mostra o OS Creator numa
  moldura. Até então abria em tela cheia, porque o clone usa `window.top` para saber se é a casca. Numa moldura, isso
  quebrava duas coisas: as abas dele não ligavam, e o login dele tomava a janela. A ponte troca, na resposta,
  `window.top` por `window.__osTopo()`, que é a janela mais alta que ainda é do OS Creator. Fora do Nexus, essa
  janela é o próprio `window.top`, então nada muda no supervisório. Se o oem mudar esses trechos, os testes da
  moldura acusam.
- **Topo do OS Creator no Nexus** (Levi, 04/10): sem o "← Plataforma" (o menu lateral já leva a qualquer lugar) e sem
  o símbolo e o "Grid Co." (o topo do Nexus já tem); fica só o "Sistema de Ordens de Serviço", centralizado. As
  páginas do Nexus também saem de qualquer moldura. A troca é feita na resposta, pela ponte, para o clone continuar
  idêntico ao do oem.
- **Sincronizado com o oem em 04/10:** `os_web/templates/solic_fila.html` (a Fila do PCM dava 500: pedia
  `p.id_account`, campo que a lista de responsáveis não tem; o oem corrigiu em 02/10 para `id_personnel`). Era o
  único arquivo diferente entre o clone e o oem.
- **Sessão:** a chave da sessão do clone é derivada da `NEXUS_SECRET_KEY`. Não é a do supervisório e não precisa de
  segredo novo. O cookie continua `os_sessao`, só em `/os`.
- **Quando sobe:** o clone só sobe na primeira visita ao `/os/`. Se ele quebrar (faltou PyQt6, por exemplo), o
  `/os/*` mostra um aviso e o resto do Nexus segue.
- **Testes:** `tests/test_torre_oscreator.py`. Nenhum teste fala com o Fracttal.
- **O que não funciona igual:**
  - o login pelo OAuth do Fracttal tem a volta configurada para o supervisório; e-mail e senha funcionam normal;
  - gravar ticket precisa do `GRIDCO_SQL_TOKEN`, que vem da variável ou do `%APPDATA%` da máquina.

## Rodar sozinho (sem o Nexus e sem mexer no 5090)

```
cd nexus/torres/oscreator/os_creator
set OS_WEB_PORTA=5091
python -m os_web.servir
```

Depois abra `http://127.0.0.1:5091/os/login`. O login no Fracttal é por pessoa, como no supervisório.

## Antes de mexer

- **Agora são duas cópias.** O que mudar no oem não chega aqui sozinho, e o que mudar aqui não volta para lá.
  Para sincronizar, copie de novo os mesmos arquivos. Por isso a ponte não edita o clone.
- Usa a mesma pasta de dados do OS Creator (`%APPDATA%\CriarOS-Fracttal`). Na mesma máquina, ele divide com o
  supervisório a chave da sessão e o token do banco.
- Precisa do PyQt6 instalado, porque a tela de Engenharia importa `steps/engenharia`, que puxa `steps/ui.py`.
