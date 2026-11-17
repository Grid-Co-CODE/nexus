"""O Raio-X diz como ESTE servidor faz o deploy (16/11/2026, Levi: "resolva o que consegue!").

O caso: depois do deploy das 21:13 de 16/11/2026 o Raio-X do servidor disse "não leu o arquivo que o deploy grava: não
existe", com o Nexus rodando de uma pasta que não é a do roteiro, e o teto de memória de 3 GB, que o
`deploy/atualizar.sh` tiraria sozinho, seguia lá. Tudo indica que o servidor não roda o script deste repositório (um
script próprio da T.I., ou uma cópia antiga): aí a regra de um reinício por hora, a espera da gravação do inventário e a
retirada do teto não valem lá. O Levi não tem acesso ao servidor: o Raio-X passa a mostrar, só para administrador, de
onde o Nexus roda, que arquivos o deploy deixou na pasta do git e de quando são, e o que as unidades do systemd e o cron
que citam o Nexus mandam rodar. Valores de variável de ambiente nunca aparecem (podem ser segredo); só os nomes.
Os caminhos e os arquivos aqui são de mentira."""
import os
import time

from nexus.casca import raio_x as R


def _servidor(tmp_path):
    git = tmp_path / "clone" / ".git"
    git.mkdir(parents=True)
    (git / "nexus-instalado").write_text("abc1234\n", encoding="utf-8")
    (git / "FETCH_HEAD").write_text("x\n", encoding="utf-8")
    antigo = time.time() - 26 * 86400
    os.utime(git / "nexus-instalado", (antigo, antigo))
    unidades = tmp_path / "systemd"
    (unidades / "timers.target.wants").mkdir(parents=True)
    (unidades / "nexus.service").write_text(
        "[Unit]\nDescription=Nexus\n[Service]\nUser=fulano\nWorkingDirectory=/srv/nexus\n"
        "Environment=NEXUS_PORTA=5070 SEGREDO=muito-secreto\nEnvironmentFile=/srv/nexus/.env\n"
        "ExecStart=/srv/nexus/.venv/bin/python servir.py\nMemoryMax=3G\nRestart=always\n", encoding="utf-8")
    (unidades / "atualiza-nexus.service").write_text(
        "[Service]\nType=oneshot\nExecStart=/usr/local/bin/atualiza.sh --token=zzz999\n", encoding="utf-8")
    (unidades / "atualiza-nexus.timer").write_text("[Timer]\nOnUnitActiveSec=2min\nUnit=atualiza-nexus.service\n",
                                                   encoding="utf-8")
    (unidades / "outra-coisa.service").write_text("[Service]\nExecStart=/usr/bin/outra\n", encoding="utf-8")
    (unidades / "timers.target.wants" / "atualiza-nexus.timer").write_text("", encoding="utf-8")
    (unidades / "nexus.service.d").mkdir()
    (unidades / "nexus.service.d" / "override.conf").write_text("[Service]\nMemoryMax=3G\n", encoding="utf-8")
    cron = tmp_path / "cron.d"
    cron.mkdir()
    (cron / "nexus").write_text("# comentário com nexus\n*/5 * * * * root CHAVE=segredo /srv/nexus/copia.sh\n",
                                encoding="utf-8")
    (cron / "outro").write_text("0 3 * * * root /usr/bin/limpa\n", encoding="utf-8")
    return git, unidades, cron


def _texto(linhas):
    return "\n".join(f"{r}: {t}" for r, t in linhas)


def test_o_diagnostico_diz_de_onde_roda_o_que_o_deploy_deixou_e_o_que_o_systemd_manda(tmp_path):
    git, unidades, cron = _servidor(tmp_path)
    linhas = R._como_o_servidor_atualiza(pasta_git=git, unidades=(str(unidades),), cron=(str(cron),))
    t = _texto(linhas)
    assert f"Pasta do git: {git}" in t
    # os arquivos do deploy: o que existe (com a data) e o que falta
    assert "nexus-instalado: abc1234, gravado em " in t and "(há 26 dias)" in t
    assert "nexus-reiniciado: não existe" in t and "nexus-teto: não existe" in t and "nexus-espera: não existe" in t
    assert "FETCH_HEAD: gravado em " in t
    # as unidades que citam o Nexus, com as linhas que dizem o que roda; a que não cita fica de fora
    assert "nexus.service: User=fulano; WorkingDirectory=/srv/nexus; ExecStart=/srv/nexus/.venv/bin/python servir.py; MemoryMax=3G; Restart=always" in t
    assert "atualiza-nexus.timer: OnUnitActiveSec=2min; Unit=atualiza-nexus.service" in t
    assert "atualiza-nexus.service: ExecStart=/usr/local/bin/atualiza.sh --token=…" in t
    assert "nexus.service.d/override.conf: MemoryMax=3G" in t
    assert "outra-coisa" not in t and "/usr/bin/limpa" not in t
    assert "Timers ligados: atualiza-nexus.timer" in t
    assert "nexus: */5 * * * * root CHAVE=… /srv/nexus/copia.sh" in t and "comentário" not in t


def test_nenhum_valor_de_variavel_aparece(tmp_path):
    git, unidades, cron = _servidor(tmp_path)
    t = _texto(R._como_o_servidor_atualiza(pasta_git=git, unidades=(str(unidades),), cron=(str(cron),)))
    for segredo in ("muito-secreto", "5070", "zzz999", "segredo", ".env"):
        assert segredo not in t, segredo
    assert "Environment" not in t                      # nem o nome das variáveis: não ajuda a entender o deploy


def test_o_script_do_repositorio_rodando_aparece_como_tal(tmp_path):
    git, unidades, cron = _servidor(tmp_path)
    agora = time.time()
    for nome in ("nexus-reiniciado", "nexus-teto"):
        (git / nome).write_text("1\n", encoding="utf-8")
        os.utime(git / nome, (agora - 60, agora - 60))
    t = _texto(R._como_o_servidor_atualiza(pasta_git=git, unidades=(str(unidades),), cron=(str(cron),)))
    assert "nexus-teto: gravado em " in t and "(há 1 min)" in t
    assert t.startswith("Leitura: o deploy do repositório gravou há 1 min")


def test_sem_os_arquivos_recentes_a_leitura_diz_que_o_script_do_repositorio_nao_roda(tmp_path):
    git, unidades, cron = _servidor(tmp_path)
    (git / "nexus-teto").write_text("quando=x" + chr(10), encoding="utf-8")       # o que sobrou de quando o script rodava ali
    velho = time.time() - 2 * 86400
    os.utime(git / "nexus-teto", (velho, velho))
    t = _texto(R._como_o_servidor_atualiza(pasta_git=git, unidades=(str(unidades),), cron=(str(cron),)))
    assert t.startswith("Leitura: o deploy/atualizar.sh do repositório NÃO está rodando neste clone")


def test_pastas_que_nao_abrem_nao_derrubam(tmp_path):
    linhas = R._como_o_servidor_atualiza(pasta_git=tmp_path / "nao-existe", unidades=(str(tmp_path / "x"),),
                                          cron=(str(tmp_path / "y"),))
    t = _texto(linhas)
    assert "nexus-instalado: não existe" in t and "Unidades do systemd que citam o Nexus: nenhuma" in t


def test_fora_do_linux_o_raio_x_nao_mostra_nada(monkeypatch):
    monkeypatch.setattr(R.sys, "platform", "win32")
    assert R._como_o_servidor_atualiza() is None


def test_a_pagina_mostra_o_diagnostico_recolhido(logado, monkeypatch):
    monkeypatch.setattr(R, "_processador", lambda janela_s=1.0: {"pct": 10, "nucleos": 4, "carga": None, "maquina": None})
    monkeypatch.setattr(R, "_como_o_servidor_atualiza", lambda: [("Leitura", "o deploy do repositório gravou há 1 min"),
                                                                 ("Pasta do git", "/srv/nexus/.git")])
    html = logado.get("/t/base/raio-x").get_data(as_text=True)
    trecho = html.split("Como este servidor atualiza", 1)[1].split("</details>", 1)[0]
    assert "o deploy do repositório gravou há 1 min" in trecho and "/srv/nexus/.git" in trecho
    monkeypatch.setattr(R, "_como_o_servidor_atualiza", lambda: None)
    assert "Como este servidor atualiza" not in logado.get("/t/base/raio-x").get_data(as_text=True)
    monkeypatch.setattr(R, "_como_o_servidor_atualiza", lambda: 1 / 0)       # o diagnóstico nunca derruba o Raio-X
    r = logado.get("/t/base/raio-x")
    assert r.status_code == 200 and "Como este servidor atualiza" not in r.get_data(as_text=True)


# ── o que o timer da plataforma manda rodar (o que o Raio-X das 22:12 de 16/11/2026 mostrou faltar) ─────────────────
# No servidor não há timer do Nexus: quem o atualiza é um timer da plataforma, com um script que não está em nenhum dos
# dois repositórios e cuja unidade nem cita o Nexus. O bloco passa a mostrar a unidade de todo timer ligado daquela pasta
# e, do script que ela manda rodar, só as linhas que citam o Nexus, o git, o pip ou o systemctl, sem nada que possa ser
# segredo.
def _com_o_timer_da_plataforma(tmp_path):
    git, unidades, cron = _servidor(tmp_path)
    script = tmp_path / "atualiza-tudo.sh"
    script.write_text("\n".join([
        "#!/bin/bash",
        "# comentário que cita o nexus",
        "cd /srv/plataforma && git pull https://bot:ghp_abcdefghijklmnopqrstuvwxyz0123456789@github.com/x/y.git",
        "echo outra coisa",
        "cd /srv/nexus && git pull --ff-only",
        "TOKEN=segredo-do-script /srv/nexus/.venv/bin/pip install -r requirements.txt",
        "systemctl restart nexus",
        "curl -H 'Authorization: Bearer abcdefghijklmnopqrstuvwxyzABCD0123456789' https://exemplo.invalid/restart",
    ]) + "\n", encoding="utf-8")
    (unidades / "plataforma-update.timer").write_text("[Timer]\nOnUnitActiveSec=1min\n", encoding="utf-8")
    (unidades / "plataforma-update.service").write_text(
        "[Service]\nType=oneshot\nExecStart=/bin/bash '" + script.as_posix() + "'\n", encoding="utf-8")
    (unidades / "timers.target.wants" / "plataforma-update.timer").write_text("", encoding="utf-8")
    (unidades / "timers.target.wants" / "apt-daily.timer").write_text("", encoding="utf-8")     # do sistema: sem arquivo aqui
    return git, unidades, cron


def test_o_script_do_timer_ligado_aparece_so_com_as_linhas_do_deploy(tmp_path):
    git, unidades, cron = _com_o_timer_da_plataforma(tmp_path)
    t = _texto(R._como_o_servidor_atualiza(pasta_git=git, unidades=(str(unidades),), cron=(str(cron),)))
    assert "plataforma-update.timer: OnUnitActiveSec=1min" in t
    assert "plataforma-update.service: ExecStart=/bin/bash " in t          # a unidade que nem cita o Nexus
    assert "atualiza-tudo.sh: cd /srv/nexus && git pull --ff-only" in t
    assert "atualiza-tudo.sh: systemctl restart nexus" in t
    assert "atualiza-tudo.sh: cd /srv/plataforma && git pull https://…@github.com/x/y.git" in t
    assert "atualiza-tudo.sh: TOKEN=… /srv/nexus/.venv/bin/pip install -r requirements.txt" in t
    assert "outra coisa" not in t and "comentário que cita" not in t and "apt-daily.timer:" not in t
    assert "atualiza-tudo.sh: curl -H 'Authorization: Bearer …' https://exemplo.invalid/restart" in t
    for segredo in ("ghp_", "abcdefghijklmnop", "segredo-do-script", "bot:"):
        assert segredo not in t, segredo


def test_a_unidade_ja_listada_nao_aparece_duas_vezes(tmp_path):
    git, unidades, cron = _com_o_timer_da_plataforma(tmp_path)
    linhas = R._como_o_servidor_atualiza(pasta_git=git, unidades=(str(unidades),), cron=(str(cron),))
    rotulos = [r for r, _t in linhas]
    assert rotulos.count("atualiza-nexus.timer") == 1 and rotulos.count("atualiza-nexus.service") == 1


def test_script_grande_binario_ou_que_nao_abre_nao_derruba(tmp_path, monkeypatch):
    git, unidades, cron = _com_o_timer_da_plataforma(tmp_path)
    script = tmp_path / "atualiza-tudo.sh"
    script.write_bytes(b"\x7fELF\x00\x00binario que cita nexus e git\n")
    t = _texto(R._como_o_servidor_atualiza(pasta_git=git, unidades=(str(unidades),), cron=(str(cron),)))
    assert "atualiza-tudo.sh:" not in t and "plataforma-update.service" in t
    script.write_text("systemctl restart nexus\n" * 40, encoding="utf-8")                  # muitas linhas: corta
    linhas = R._como_o_servidor_atualiza(pasta_git=git, unidades=(str(unidades),), cron=(str(cron),))
    do_script = [x for r, x in linhas if r == "atualiza-tudo.sh"]
    assert len(do_script) == R.MAX_LINHAS_DE_SCRIPT + 1 and do_script[-1] == "(…)"
    monkeypatch.setattr(R, "MAX_SCRIPT_BYTES", 10)                                         # grande demais: nem lê
    t = _texto(R._como_o_servidor_atualiza(pasta_git=git, unidades=(str(unidades),), cron=(str(cron),)))
    assert "atualiza-tudo.sh:" not in t
