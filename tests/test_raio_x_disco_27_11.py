"""O disco do Nexus no Raio-X (27/11/2026)."""


def test_o_disco_do_nexus_mede_e_aparece(app, monkeypatch):
    """O quadro "Disco do Nexus" (27/11/2026, a cota de disco estourada travou a geração da W49): a medida tem teto de tempo
    e mostra as pastas que mais ocupam; a página nunca espera por ela."""
    from nexus.casca import raio_x as R
    monkeypatch.setattr(R, "DISCO_MAX_S", 0.5)
    m = R._medir_disco()
    assert {"por_tamanho", "por_arquivos", "contados", "raizes", "total_mb"} <= set(m)
    monkeypatch.setitem(R._DISCO, "medida", dict(m, hora="27/11 14:30"))
    monkeypatch.setitem(R._DISCO, "quando", 10**12)
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"], s["admin"] = True, True
    html = c.get("/t/base/raio-x?aba=memoria").get_data(as_text=True)
    assert "Disco do Nexus" in html and "Medido em 27/11 14:30" in html
