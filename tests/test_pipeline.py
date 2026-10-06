# -*- coding: utf-8 -*-
"""Roteamento, publicação por decisão do Pedro e 'nenhuma falha silenciosa', com a
transcrição, o Claude, o Chrome e o Worker substituídos."""
import pytest
from conftest import segs_exemplo
from test_ata import _bruto

import analise_fala
import audio
import entregavel
import estruturar
import pipeline
import transcribe
import upload
from sessao import Sessao

CFG = {"meu_nome": "Pedro", "estruturar": True, "worker_url": "https://w.test",
       "upload_token": "t", "audio_reter_dias": 30, "publicacao_reter_dias": 90}


@pytest.fixture
def falsos(monkeypatch, tmp_path):
    chamadas = {"publicar": [], "pdf": [], "apagar": []}
    monkeypatch.setattr(transcribe, "transcrever_sessao",
                        lambda s, cfg, log=print: (segs_exemplo(), {
                            "modelo": "falso", "dispositivo": "cpu", "segundos_processamento": 0,
                            "diarizacao": {"status": "pulada", "motivo": "1 remoto", "falantes": 1}}))
    monkeypatch.setattr(estruturar, "chamar_claude", lambda *a, **k: (_bruto(), {"por": "falso"}))

    def pdf(h, p):
        chamadas["pdf"].append(p.name)
        p.write_bytes(b"%PDF-falso")
        return p
    monkeypatch.setattr(entregavel, "html_para_pdf", pdf)

    def pub(url, token, chave, titulo, html, senha, dias, tentativas=3):
        chamadas["publicar"].append({"chave": chave, "html": html, "senha": senha})
        return {"id": "f" * 32, "url": f"https://w.test/r/{'f' * 32}", "expira_em": "2026-12-29"}
    monkeypatch.setattr(upload, "publicar", pub)
    monkeypatch.setattr(upload, "apagar", lambda u, t, i: chamadas["apagar"].append(i) or {"apagada": True})
    monkeypatch.setattr(analise_fala, "FALA_DIR", tmp_path / "fala")
    monkeypatch.setattr(analise_fala, "_atualizar_vault", lambda linhas: None)
    return chamadas


def _gravada(raiz, tipo):
    s = Sessao.criar("Reunião teste", tipo, "p", ["Mauro"], raiz=raiz)
    s.mic_pcm.write_bytes(b"\x00\x00" * 16000 * 3)
    s.loop_pcm.write_bytes(b"\x00\x00" * 16000 * 3)
    s.m["inicio"] = "2026-09-30T14:00:00-03:00"
    s.estado("gravado")
    return s


def _silencio(*a, **k):
    return None


def test_parresia_nao_sai_da_maquina(raiz, falsos):
    s = _gravada(raiz, "parresia")
    et = pipeline.processar(s, dict(CFG), log=_silencio, publicar_=True)   # nem pedindo
    assert falsos["publicar"] == []
    assert et["publicacao"]["status"] == "pulada"
    assert "ata.pdf" in falsos["pdf"] and "entregavel.pdf" not in falsos["pdf"]
    assert not s.caminho("entregavel.html").exists()
    assert "Uso interno" in s.caminho("ata.html").read_text(encoding="utf-8")
    assert Sessao.abrir(s.pasta).m["estado"] == "pronto"


def test_cliente_nao_publica_sozinho(raiz, falsos):
    s = _gravada(raiz, "cliente")
    et = pipeline.processar(s, dict(CFG), log=_silencio)
    assert falsos["publicar"] == []
    assert et["publicacao"]["status"] == "pendente"
    assert s.caminho("entregavel.html").exists() and "entregavel.pdf" in falsos["pdf"]


def test_publicar_por_decisao_com_senha(raiz, falsos):
    s = _gravada(raiz, "cliente")
    pipeline.processar(s, dict(CFG), log=_silencio)
    pub = pipeline.publicar(Sessao.abrir(s.pasta), dict(CFG))
    p = falsos["publicar"][0]
    assert p["chave"] == s.id and "RYZE" in p["html"] and "Kubernetes" not in p["html"]
    assert len(p["senha"]) == 9 and p["senha"][4] == "-" and pub["senha"] == p["senha"]
    # reprocessar atualiza a página que já está no ar, com a MESMA senha
    pipeline.processar(Sessao.abrir(s.pasta), dict(CFG), log=_silencio, forcar=("estrutura",))
    assert len(falsos["publicar"]) == 2 and falsos["publicar"][1]["senha"] == p["senha"]


def test_mudar_para_interno_tira_do_ar(raiz, falsos):
    s = _gravada(raiz, "cliente")
    pipeline.processar(s, dict(CFG), log=_silencio)
    pipeline.publicar(Sessao.abrir(s.pasta), dict(CFG))
    s = Sessao.abrir(s.pasta)
    s.m["tipo"] = "parresia"
    s.salvar()
    pipeline.reaplicar(s, dict(CFG), log=_silencio)
    assert falsos["apagar"] == ["f" * 32]
    assert Sessao.abrir(s.pasta).m["publicacao"].get("apagada_em")


def test_pagina_apagada_nao_volta_sozinha(raiz, falsos):
    s = _gravada(raiz, "cliente")
    pipeline.processar(s, dict(CFG), log=_silencio)
    pipeline.publicar(Sessao.abrir(s.pasta), dict(CFG))
    pipeline.despublicar(Sessao.abrir(s.pasta), dict(CFG), "teste")
    pipeline.processar(Sessao.abrir(s.pasta), dict(CFG), log=_silencio, forcar=("estrutura",))
    assert len(falsos["publicar"]) == 1
    with pytest.raises(RuntimeError, match="apagada"):
        pipeline.publicar(Sessao.abrir(s.pasta), dict(CFG))
    pipeline.publicar(Sessao.abrir(s.pasta), dict(CFG), forcar=True)
    assert len(falsos["publicar"]) == 2


def test_legado_inferido_nao_publica(raiz, falsos):
    s = _gravada(raiz, "cliente")
    pipeline.processar(s, dict(CFG), log=_silencio)
    s = Sessao.abrir(s.pasta)
    s.m.update({"legado": True, "classificacao": "inferida"})
    s.salvar()
    with pytest.raises(RuntimeError, match="INFERIDO"):
        pipeline.publicar(s, dict(CFG))


def test_falha_do_claude_nao_perde_a_reuniao(raiz, falsos, monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("claude fora do ar")
    monkeypatch.setattr(estruturar, "chamar_claude", quebra)
    s = _gravada(raiz, "cliente")
    et = pipeline.processar(s, dict(CFG), log=_silencio)
    assert et["estrutura"]["status"] == "falhou" and "fora do ar" in et["estrutura"]["detalhe"]
    assert "## Transcrição" in s.caminho("ata.md").read_text("utf-8")
    assert et["publicacao"]["status"] == "pulada"      # sem ata estruturada não há entregável
    assert Sessao.abrir(s.pasta).m["estado"] == "pronto_com_falhas"
    import sessao
    assert [x.id for x in sessao.a_retomar(raiz)] == [s.id]   # a janela oferece retomar
    monkeypatch.setattr(estruturar, "chamar_claude", lambda *a, **k: (_bruto(), {"por": "falso"}))
    et = pipeline.processar(Sessao.abrir(s.pasta), dict(CFG), log=_silencio)
    assert et["estrutura"]["status"] == "ok" and et["publicacao"]["status"] == "pendente"


def test_sem_config_de_publicacao_falha_visivel(raiz, falsos):
    s = _gravada(raiz, "cliente")
    pipeline.processar(s, dict(CFG), log=_silencio)
    with pytest.raises(RuntimeError, match="worker_url"):
        pipeline.publicar(Sessao.abrir(s.pasta), dict(CFG, worker_url="", upload_token=""))


def test_audio_compactado_e_pcm_apagado(raiz, falsos):
    s = _gravada(raiz, "pessoal")
    et = pipeline.processar(s, dict(CFG), log=_silencio)
    assert et["audio"]["status"] == "ok"
    assert not s.mic_pcm.exists() and audio.fonte_audio(s, "mic").suffix == ".opus"


def test_sem_falas_e_falha_e_audio_nao_e_garantido(raiz, falsos, monkeypatch):
    monkeypatch.setattr(transcribe, "transcrever_sessao", lambda *a, **k: ([], {
        "modelo": "falso", "dispositivo": "cpu", "segundos_processamento": 0,
        "diarizacao": {"status": "pulada"}}))
    s = _gravada(raiz, "pessoal")
    et = pipeline.processar(s, dict(CFG), log=_silencio)
    assert et["transcricao"]["status"] == "falhou"
    assert et["falantes"]["status"] == "pulada"
    assert not pipeline.ata_garantida(Sessao.abrir(s.pasta)), "a retenção não pode apagar este áudio"


def test_processar_de_novo_nao_retranscreve(raiz, falsos, monkeypatch):
    s = _gravada(raiz, "pessoal")
    pipeline.processar(s, dict(CFG), log=_silencio)
    monkeypatch.setattr(transcribe, "transcrever_sessao",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("retranscreveu")))
    pipeline.processar(Sessao.abrir(s.pasta), dict(CFG), log=_silencio)


def test_refazer_a_ata_guarda_a_anterior(raiz, falsos):
    s = _gravada(raiz, "pessoal")
    pipeline.processar(s, dict(CFG), log=_silencio)
    pipeline.processar(Sessao.abrir(s.pasta), dict(CFG), log=_silencio, forcar=("transcricao",))
    assert list(s.pasta.glob("ata.antes-*.json")), "nomes confirmados e campos manuais se perderiam"


def test_dois_processamentos_ao_mesmo_tempo(raiz, falsos):
    s = _gravada(raiz, "pessoal")
    s.bater()
    with pipeline.Trava(s):
        with pytest.raises(pipeline.Ocupada):
            pipeline.processar(Sessao.abrir(s.pasta), dict(CFG), log=_silencio)
