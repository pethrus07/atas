# -*- coding: utf-8 -*-
"""R1: o áudio está no DISCO durante a captura, e um dispositivo que cai não
desalinha a linha do tempo. Usa um dispositivo falso (sem placa de som)."""
import time

import numpy as np

import record
from sessao import Sessao

SR = record.SR


class _Rec:
    def __init__(self, dev):
        self.dev = dev

    def __enter__(self):
        if self.dev.falhar_ao_abrir:
            self.dev.falhar_ao_abrir -= 1
            raise RuntimeError("dispositivo sumiu")
        return self

    def __exit__(self, *a):
        return False

    def record(self, numframes):
        time.sleep(numframes / SR)                  # tempo real
        self.dev.lidos += 1
        if self.dev.cair_apos and self.dev.lidos == self.dev.cair_apos:
            raise RuntimeError("caiu no meio")
        t = np.arange(numframes) / SR
        return (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32).reshape(-1, 1)


class Falso:
    def __init__(self, nome="falso", cair_apos=None, falhar_ao_abrir=0):
        self.name = nome
        self.lidos = 0
        self.cair_apos = cair_apos
        self.falhar_ao_abrir = falhar_ao_abrir

    def recorder(self, samplerate):
        return _Rec(self)


def test_audio_vai_para_o_disco_durante_a_captura(raiz):
    s = Sessao.criar("x", "pessoal", raiz=raiz)
    g = record.Gravador(s, {"mic": Falso(), "loop": Falso(), "avisos": []})
    g.iniciar()
    time.sleep(1.2)
    # o processo "morre" aqui: nada foi encerrado, e mesmo assim o áudio existe
    tamanho = s.mic_pcm.stat().st_size
    assert tamanho >= SR * 2 * 0.8, "o PCM deveria ter ~1 s de áudio já gravado"
    assert Sessao.abrir(s.pasta).m["estado"] == "gravando"
    g.parar()
    assert Sessao.abrir(s.pasta).m["estado"] == "gravado"
    assert s.status_etapa("captura") == "ok"


def test_queda_de_dispositivo_preenche_a_lacuna(raiz, monkeypatch):
    s = Sessao.criar("x", "pessoal", raiz=raiz)
    dev = Falso(cair_apos=5, falhar_ao_abrir=0)   # cai depois de 0,5 s; reabre após ~1 s
    # a reescolha não pode ir buscar o microfone de verdade da máquina
    monkeypatch.setattr(record, "_escolher_mic", lambda preferido=None: (dev, None))
    g = record.Gravador(s, {"mic": dev, "loop": None, "avisos": []})
    g.iniciar()
    time.sleep(3.5)
    diag = g.parar()
    dur_arquivo = s.mic_pcm.stat().st_size / 2 / SR
    assert diag["mic"]["erros"], "a queda deveria ter sido registrada"
    assert diag["mic"]["lacunas"], "a lacuna deveria ter sido preenchida com silêncio"
    assert abs(dur_arquivo - g.decorrido()) < 0.6, (dur_arquivo, g.decorrido())


def test_pcm_com_byte_impar_ainda_le(tmp_path):
    import audio
    p = tmp_path / "x.pcm"
    p.write_bytes(b"\x10\x00" * 100 + b"\x01")    # crash no meio de uma amostra
    assert len(audio.ler_pcm(p)) == 100
