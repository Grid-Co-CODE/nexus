"""O SSO da zeladoria (a "Integração de Segurança", sso-zeladoria.gridco.com.br) dentro do banco do Nexus.

Levi, 12/11/2026: o Supabase do Radar e do SSO parou (a cota estourou) e "vamos migrar [...] pode pôr no mesmo banco do
Nexus". As tabelas do SSO viram livros cifrados do Nexus, com os mesmos nomes que o app usa (as views `public.*` do
Supabase). Leia o `CLAUDE.md` desta pasta antes de mexer.
"""
