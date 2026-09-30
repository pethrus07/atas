# -*- coding: utf-8 -*-
import datetime as dt

import numpy as np

import audio
from sessao import Sessao


def _pcm(p, seg=3):
    x = (0.2 * np.sin(np.arange(16000 * seg) / 16000 * 2 * np.pi * 300)).astype(np.float32)
    p.write_bytes((x * 32767).astype("<i2").tobytes())


def test_aposenta_pcm_so_depois_de_conferir(raiz):
    s = Sessao.criar("x", "pessoal", raiz=raiz)
    _pcm(s.mic_pcm)
    _pcm(s.loop_pcm)
    feitos = audio.aposentar_pcm(s)
    assert set(feitos) == {"mic", "loop"}
    assert not s.mic_pcm.exists() and (s.audio_dir / "mic.opus").exists()
    assert abs(len(audio.ler_audio(s.audio_dir / "mic.opus")) / 16000 - 3) < 0.1
    assert audio.fonte_audio(s, "mic") == s.audio_dir / "mic.opus"


def test_pcm_fica_se_o_opus_nao_conferir(raiz, monkeypatch):
    s = Sessao.criar("x", "pessoal", raiz=raiz)
    _pcm(s.mic_pcm, seg=5)
    monkeypatch.setattr(audio, "duracao_opus", lambda c: 1.0)
    try:
        audio.aposentar_pcm(s)
    except RuntimeError:
        pass
    assert s.mic_pcm.exists(), "sem Opus conferido, o PCM não pode sumir"


def test_retencao(raiz):
    velha = Sessao.criar("velha", "pessoal", raiz=raiz)
    nova = Sessao.criar("nova", "pessoal", raiz=raiz)
    for s, dias in ((velha, 40), (nova, 2)):
        s.m["inicio"] = (dt.datetime.now().astimezone() - dt.timedelta(days=dias)).isoformat()
        s.m["estado"] = "pronto"
        s.salvar()
        s.audio_dir.mkdir()
        (s.audio_dir / "mic.opus").write_bytes(b"x")
    limpas = audio.limpar_expirados([velha, nova], 30)
    assert limpas == [velha.id]
    assert not velha.audio_dir.exists() and nova.audio_dir.exists()
