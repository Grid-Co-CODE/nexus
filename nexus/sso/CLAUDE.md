# CLAUDE.md — SSO da zeladoria (a Integração de Segurança dos fornecedores) no banco do Nexus

O SSO é o app de saúde e segurança dos fornecedores da zeladoria (`sso-zeladoria.gridco.com.br`): integração por vídeo
com quiz e certificado, APR, checklist de EPI, vistoria antes e depois, diário de obra e o cronograma dos fornecedores, e
a Gestão (a equipe da Grid Co. aprova presenças e lê tudo). É um site estático no Cloudflare do HEAD da zeladoria, que
falava direto com o Supabase, o mesmo projeto do Radar. O pacote de migração (código byte a byte da produção, o esquema,
as permissões e os volumes) ficou fora do repositório, em `Downloads\Deploy\sso_pacote_2026-11-12` no PC do Levi.

Levi, 12/11/2026, com o Supabase parado (a cota estourou em 11/11): "vamos migrar, isso sim! pode pôr no mesmo banco do
Nexus" (e nada de pagar o plano do Supabase para destravar).

## O que está no banco do Nexus

Um livro cifrado por módulo (`tabelas.py`), cada aba com o nome da view que o app usa, mais a aba `atualizacao` (o tipo
de cada coluna, a chave, quantas linhas vieram, a versão):

| Livro | Abas |
|---|---|
| `nexus_sso_integracao` | `iv_sessoes_video`, `iv_visualizacoes`, `iv_presencas`, `iv_perfis` |
| `nexus_sso_apr` | `apr_submissoes` |
| `nexus_sso_epi` | `epi_submissoes` |
| `nexus_sso_vistoria` | `vistoria_checklists` (a tabela solta `public.checklists` do Supabase) |
| `nexus_sso_diario` | `diario_registros`, `diario_usinas` |
| `nexus_sso_cronograma` | `cronograma_periodos`, `cronograma_historico` (só cresce), `cronograma_fornecedores` |
| `nexus_sso_arquivos` | `arquivos`: o inventário dos 5.079 arquivos do Storage (bucket, caminho, tamanho, tipo) |

- **Cifra:** o molde da Zeladoria (`nexus/zeladoria/guardar.py`, com a regra de `tabelas.coluna_cifrada` e o contexto
  `sso/<aba>/<chave>/<coluna>`). Todo texto, JSON e lista vai cifrado: nome, CPF, telefone, e-mail, empresa, as
  assinaturas em base64 e os formulários inteiros. Em claro só o que liga: ids, datas, estados, usina, serviço, fase. O
  fornecedor do cronograma é chave e vai cifrado (o MEI é pessoa); a usina do diário é chave e fica em claro.
- **Assinatura grande:** passa de 32 mil caracteres e vai partida em colunas `__p2`, `__p3`... (o `guardar`). O maior
  livro, o do APR, tem 4,8 MB.
- **Um livro por módulo** porque o banco recebe um arquivo por livro, e as assinaturas pesam.

## Os arquivos (fotos, PDFs, certificados, vídeo)

~2,5 GB, ~5.000 arquivos, ficaram **travados no Supabase** desde 11/11/2026: o Storage responde 402 até pelo painel, e só
volta pagando o plano (recusado) ou, talvez, quando a cota renovar em 10/12 (mas o espaço continua acima do limite). O
banco guarda as URLs do Supabase dentro das linhas (`certificado_url`, `desvios_urls`, `itens[].foto_url`,
`fotos[].url`, as imagens da vistoria): continuam lá, apontando para arquivo que hoje não abre. O inventário em
`nexus_sso_arquivos` diz o que existia, para resgatar sem perder nenhum se o Storage voltar.

## A cópia (feita uma vez, em 12/11/2026)

1. **Exportar no SQL Editor do Supabase** (o painel ainda lê o banco), em três partes, porque o editor e o Chrome não
   aguentam uma célula com tudo: o APR; o EPI com a vistoria; e o resto com os tipos (`format_type`), as chaves primárias
   e o inventário (`storage.objects` dos sete buckets do SSO). Cada parte é um JSON `{"parte", "gerado_em", "tabelas"}`,
   salvo fora do repositório (`Downloads\Deploy\sso_2026-11-12`): tem dado pessoal. O Chrome só deixa uma descarga
   automática por página: a segunda pede permissão na barra de endereço.
2. **Ensaiar:** `python ferramentas/copiar_sso.py --pasta <pasta das partes>` (só conta; nada sai da máquina).
3. **Gravar:** o mesmo com `--gravar`. Grava os sete livros e confere a contagem de cada aba. Depois que o Nexus gravar
   alguma mudança (versão acima de 0), a cópia recusa passar por cima (`--forcar` só com certeza).

Contagens da exportação de 12/11/2026 (as mesmas do levantamento do pacote): sessões 1, visualizações 52, presenças 31,
perfis 5, APR 162, EPI 78, vistorias 85, diário 104, usinas 54, cronograma 8, histórico 62, fornecedores 8, arquivos
5.079.

## Como provar

`python -m pytest tests/test_sso_copia.py -q`: um livro por módulo, a volta igual (inclusive a assinatura partida, o
JSON e o booleano), o pessoal cifrado no banco, a exportação incompleta que não grava, a cópia que não passa por cima e
os livros no catálogo.

## O que falta (o SSO ainda não funciona no Nexus)

- **A Gestão no Nexus:** as telas de aprovação, presenças, APR, EPI, vistoria, diário e cronograma, com o login e os
  setores do Nexus no lugar do login do Supabase (5 perfis, 4 aprovados).
- **Os formulários dos fornecedores:** páginas públicas do Nexus (sem login) que só enviam, com os arquivos no servidor
  do Nexus, atrás do login para ler (no Supabase os buckets eram públicos).
- **Os arquivos antigos:** resgatar se o Storage voltar, pelo inventário.
- **O endereço:** `sso-zeladoria.gridco.com.br` (Cloudflare do HEAD da zeladoria) passa a apontar para o Nexus.
