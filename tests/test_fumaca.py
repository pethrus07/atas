# -*- coding: utf-8 -*-
"""Fumaça do pipeline inteiro com peças reais: Whisper (GPU ou CPU), diarização no venv
diar, Chrome headless e Opus. Só o Claude e o Worker ficam de fora (custam e saem da
máquina). Áudio sintético (vozes SAPI em inglês): 41 s, fala alternada mic × chamada.

    ...python.exe -m pytest tests -m lento
"""
import pathlib

import numpy as np
import pytest

import audio
import pipeline
from sessao import Sessao

FX = pathlib.Path(__file__).parent / "fixtures"


@pytest.mark.lento
def test_pipeline_ponta_a_ponta(raiz, tmp_path, monkeypatch):
    import analise_fala
    monkeypatch.setattr(analise_fala, "FALA_DIR", tmp_path / "fala")
    monkeypatch.setattr(analise_fala, "_atualizar_vault", lambda linhas: None)
    s = Sessao.criar("Fumaça", "parresia", "teste", ["Richard"], raiz=raiz)
    for nome, pcm in (("mic", s.mic_pcm), ("loop", s.loop_pcm)):
        x = audio.ler_audio(FX / f"{nome}.opus")
        pcm.write_bytes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    s.m["inicio"] = "2026-09-30T14:00:00-03:00"
    s.estado("gravado")

    cfg = {"meu_nome": "Pedro", "idioma": "en", "model": "auto", "dispositivo": "auto",
           "estruturar": False, "diarizar": True, "audio_reter_dias": 30}
    et = pipeline.processar(s, cfg, log=print)

    assert et["transcricao"]["status"] == "ok", et["transcricao"]
    t = (s.pasta / "transcricao.json").read_text(encoding="utf-8").lower()
    assert "payment" in t and "gateway" in t
    segs, a = pipeline.carregar(s)
    assert {x["speaker"] for x in segs} == {"Você", "Participante"}
    assert len(segs) >= 7, "o recorte por palavras deveria devolver uma fala por trecho"
    # 1 remoto informado: a diarização é dispensada e o nome vem da partida
    assert et["falantes"]["status"] == "pulada" and "1 participante" in et["falantes"]["detalhe"]
    assert [p["nome"] for p in a["participantes"] if p["rotulo"] == "Participante"] == ["Richard"]
    assert et["estrutura"]["status"] == "pulada"
    assert et["publicacao"]["status"] == "pulada"
    assert s.caminho("ata.pdf").stat().st_size > 5000
    assert s.caminho("ata.pdf").read_bytes()[:4] == b"%PDF"
    assert et["audio"]["status"] == "ok" and not s.mic_pcm.exists()
    assert Sessao.abrir(s.pasta).m["estado"] == "pronto"


def test_recorte_por_palavras():
    """O turbo com vocabulário devolve 1 trecho para 30 s; o recorte refaz as frases."""
    import transcribe

    class W:
        def __init__(self, a, b, w):
            self.start, self.end, self.word = a, b, w
    ws = [W(0, .5, " Bom"), W(.5, 1, " dia."), W(1.1, 1.5, " Tudo"), W(1.5, 2.6, " certo?"),
          W(4.0, 4.5, " Sim"), W(4.5, 5, " claro")]
    r = transcribe._recortar(ws, "Você")
    assert [x["text"] for x in r] == ["Bom dia. Tudo certo?", "Sim claro"]
    assert r[1]["start"] == 4.0 and isinstance(r[1]["start"], float)
