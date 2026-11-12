# O site do SSO falando com o Nexus (para o HEAD da zeladoria aplicar)

O Supabase parou em 11/11/2026. Os dados do SSO já estão no banco do Nexus (os livros `nexus_sso_*`, cifrados), e o Nexus
responde no lugar dele em `https://app.gridco.com.br/t/sso`. O site continua no seu Cloudflare, no mesmo endereço
(`sso-zeladoria.gridco.com.br`) e com a mesma cara: **muda um arquivo só**.

## O que fazer

1. No seu repositório do site, troque o `integracao-seguranca/shared/supabase-client.js` pelo `supabase-client.js`
   desta pasta (copie o arquivo inteiro, sem mudar nada).
2. Suba na `main` do seu repositório, como sempre: o GitHub Actions publica o worker `integracao-video-gridco`.
3. Confira (no celular e no computador):
   - `/campo/`: o vídeo toca, o quiz e a assinatura enviam, e aparece "Integração concluída";
   - `/apr/`, `/epi/`, `/vistoria/` e `/diario/`: enviar um de cada, com foto;
   - "Sou da gestão": leva ao login do Nexus e volta à Gestão já logado. Quem está aprovado no SSO vê tudo; quem não
     está vê a tela de espera, como antes.

Opcional: a linha do supabase-js (`<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/...">`) pode sair
dos seis `index.html`; com ou sem ela, o site funciona (o arquivo novo ocupa o lugar dela).

## O que muda para quem usa

- **Fornecedor:** nada. Os formulários enviam como antes e continuam sem login.
- **Gestão:** o login passa a ser o do Nexus (o mesmo do Fracttal), e não mais e-mail e senha do Supabase. A pessoa é
  achada pelo e-mail do login: o perfil aprovado no SSO continua aprovado. Quem entra pela 1ª vez fica "pendente" até
  um gestor aprovar em Usuários, como antes. O login vale 8 h; depois, a página busca outro sozinha.
- **Arquivos:** fotos, vídeos e certificados ficam no servidor do Nexus e só abrem pela Gestão (no Supabase qualquer
  pessoa com o endereço abria). Os arquivos de antes de 11/11 ficaram travados no Supabase: aparecem quebrados até serem
  resgatados (o administrador do Nexus os recebe em `app.gridco.com.br/t/sso/admin`).
- **O vídeo da integração** também ficou no Supabase: até o administrador enviá-lo pela mesma página (ou a Gestão, na
  aba Sessões / Quiz), a integração não passa da 1ª etapa. Se você tem o `integracao-zeladoria.mp4` original, mande ao
  Levi.

## Voltar atrás

O arquivo antigo de volta no lugar e outro push. (Com o Supabase parado, o site antigo também não funciona.)

## Do lado do Nexus (para quem mantém o Nexus)

- A API: `nexus/sso/api.py`; as regras (o RLS do Supabase): `nexus/sso/regras.py` e `nexus/sso/esquema.py`; o guia:
  `nexus/sso/CLAUDE.md`.
- O site que pode falar com a API: `NEXUS_SSO_ORIGENS` (padrão: `https://sso-zeladoria.gridco.com.br`).
- Para provar numa cópia local, troque só a linha `var NEXUS = ...` do arquivo pelo endereço da cópia.
