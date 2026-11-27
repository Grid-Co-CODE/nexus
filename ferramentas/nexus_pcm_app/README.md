# Nexus PCM (o aplicativo do "Gerar no PC")

Gera a programação semanal no computador de uma pessoa do PCM e devolve a planilha ao Nexus (27/11/2026). O porquê, a API e
as regras estão em `nexus/pcm/CLAUDE.md`, seção "Gerar no PC e a vigia da memória".

## Para quem usa

1. Receba o aplicativo (`NexusPCM.exe`, um arquivo só; não precisa instalar Python) do administrador do Nexus, ou pelo
   "Baixar o aplicativo" da tela Gerar a semana quando o `NEXUS_PCM_APP_URL` estiver configurado. Na primeira vez o Windows pode avisar "editor desconhecido": "Mais
   informações" → "Executar assim mesmo".
2. No Nexus, "Ligar um computador": dê um nome e copie o código (ele só aparece uma vez).
3. Abra o aplicativo, cole o código e clique em Conectar. Só se faz isso uma vez por computador.
4. Escolha a semana e clique em "Gerar a semana". Leva de 15 a 40 minutos; a planilha volta sozinha ao Nexus, e o botão
   "Abrir no Nexus" leva à rodada para conferir e publicar no App.

## Para quem mantém

- `nexus_pcm.py`: a janela (tkinter), a conexão (o código cifrado pelo Windows, DPAPI, em `%LOCALAPPDATA%\NexusPCM`), a
  rodada (`rodar`) e o motor no processo filho (`--motor`, `--pre-leitura`). O motor e o adaptador da FAMA NÃO estão no .exe:
  vêm no pacote de cada rodada, do Nexus. Mudança no motor não pede .exe novo; mudança no aplicativo, sim.
- `construir.py`: gera o .exe com o PyInstaller fora do repositório (`%LOCALAPPDATA%\NexusPCM-build\dist`). O .exe não
  entra no git: entregue o arquivo ou publique-o e ponha o endereço em `NEXUS_PCM_APP_URL` (o link "Baixar o aplicativo" aparece).
- Teste sem a janela: `tests/test_pcm_geracao_pc.py::test_o_aplicativo_gera_no_pc_e_devolve` roda o `rodar` de verdade
  contra o Nexus de teste.
