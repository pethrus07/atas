# -*- coding: utf-8 -*-
"""R5: a nota do Sinapse não leva o título da reunião (nome de cliente, assunto da Parresia)."""
import analise_fala


def test_nota_do_vault_sem_titulo(tmp_path, monkeypatch):
    vault = tmp_path / "sinapse" / "08-CRESCIMENTO"
    vault.mkdir(parents=True)
    monkeypatch.setenv("SINAPSE_VAULT", str(tmp_path / "sinapse"))
    segs = [{"speaker": "Você", "start": 0, "end": 60, "text": "aí tipo a gente vai entendeu?"},
            {"speaker": "Participante", "start": 61, "end": 120, "text": "certo"}]
    r = analise_fala.processar(segs, "alinhamento atualização de frota ClienteX", "2026-09-30T10:00",
                               pasta=tmp_path / "fala", tipo="parresia", sessao_id="s1")
    nota = (vault / "fala-raio-x.md").read_text(encoding="utf-8")
    assert r["vault"] is not None
    assert "frota" not in nota and "ClienteX" not in nota
    assert "| Parresia |" in nota
    # o painel local continua com o título (fica só nesta máquina)
    assert "ClienteX" in (tmp_path / "fala" / "raio-x.html").read_text(encoding="utf-8")


def test_reescrever_nota_completa_tipos_antigos(tmp_path, monkeypatch):
    vault = tmp_path / "sinapse" / "08-CRESCIMENTO"
    vault.mkdir(parents=True)
    monkeypatch.setenv("SINAPSE_VAULT", str(tmp_path / "sinapse"))
    segs = [{"speaker": "Você", "start": 0, "end": 60, "text": "olá"}]
    analise_fala.processar(segs, "Cliente Y", "2026-08-01T10:00", pasta=tmp_path / "fala", vault=False)
    analise_fala.reescrever_nota(tmp_path / "fala", {"2026-08-01T10:00|Cliente Y": "cliente"})
    nota = (vault / "fala-raio-x.md").read_text(encoding="utf-8")
    assert "Cliente Y" not in nota and "| cliente |" in nota
