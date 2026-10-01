# -*- coding: utf-8 -*-
"""Gravação com os dispositivos DE VERDADE, na mesma sequência de threads da janela.

Existe porque os testes com dispositivo falso não pegaram o 0x800401F0 que, em
30/09/2026, fez a primeira reunião real da v2 gravar 0 bytes: a checagem rodava numa
thread que terminava e levava junto o COM do processo. Grava ~2 s num diretório
temporário (apagado no fim) e exige áudio no disco.

    ...python.exe -m pytest tests -m lento
"""
import threading
import time

import pytest

from sessao import Sessao


@pytest.mark.lento
def test_grava_depois_da_checagem_em_outra_thread(raiz):
    res = {}

    def checar():
        import record
        res["disp"] = record.escolher_dispositivos()
        res["niv"] = record.medir_niveis(res["disp"], segundos=0.5)

    t = threading.Thread(target=checar)
    t.start()
    t.join()
    if "disp" not in res:
        pytest.skip("sem dispositivo de áudio nesta máquina")
    import record
    d = res["disp"]
    assert d["mic"].name                      # ler o nome já quebrava
    s = Sessao.criar("real", "pessoal", raiz=raiz)
    g = record.Gravador(s, d)
    ini = threading.Thread(target=g.iniciar)
    ini.start()
    ini.join()
    time.sleep(2.2)
    diag = g.parar()
    assert s.mic_pcm.stat().st_size > 16000 * 2 * 1.5, diag
    assert not diag["mic"]["morto"], diag
    if d["loop"] is not None:
        assert s.loop_pcm.stat().st_size > 16000 * 2 * 1.5, diag


@pytest.mark.lento
def test_segunda_via_portaudio_le_o_microfone():
    import record
    d = record.escolher_dispositivos()
    pa = record.MicPortAudio.achar(d["mic"].name)
    if pa is None:
        pytest.skip("PortAudio não enxerga o microfone")
    assert record._abre(pa)
