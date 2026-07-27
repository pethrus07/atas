# -*- coding: utf-8 -*-
"""
Captura de áudio de reunião no Windows, sem driver e sem admin.

Grava DUAS fontes físicas separadas ao mesmo tempo, via WASAPI (lib soundcard):
  - o microfone padrão            -> vira o falante "Você"
  - o loopback do alto-falante    -> vira o falante "Participante"
    (tudo o que o outro lado fala e sai pelas suas caixas/fone)

São dois arquivos WAV mono 16 kHz. A separação de "quem falou" nasce daqui:
cada lado é uma fonte diferente, então não precisamos de diarização por IA.
"""
import threading
import wave
import numpy as np
import soundcard as sc

SR = 16000            # 16 kHz mono: o que o Whisper usa (o WASAPI reamostra sozinho)
BLOCK = SR // 10      # blocos de 100 ms -> parar leva no máximo ~100 ms


def _gravar_stream(recorder_ctx, parar_evt, buffer):
    """Roda numa thread: lê blocos até o evento de parada ser acionado."""
    with recorder_ctx as rec:
        while not parar_evt.is_set():
            buffer.append(rec.record(numframes=BLOCK))  # [BLOCK, canais] float32


def _mono(chunks):
    """Concatena os blocos e faz downmix estéreo -> mono."""
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    a = np.concatenate(chunks, axis=0)
    return a.mean(axis=1) if a.ndim == 2 else a


def _escrever_wav(caminho, mono_f32):
    """Grava WAV PCM 16-bit mono usando só a stdlib (sem soundfile/libsndfile)."""
    pcm = (np.clip(mono_f32, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def _rms(mono_f32):
    return float(np.sqrt(np.mean(np.square(mono_f32)))) if mono_f32.size else 0.0


def capturar(mic_wav, loop_wav):
    """
    Grava até o usuário apertar ENTER (ou Ctrl+C).
    Escreve mic_wav e loop_wav. Devolve um dict com diagnóstico (duração/RMS).
    """
    mic = sc.default_microphone()
    spk = sc.default_speaker()
    loop = sc.get_microphone(spk.name, include_loopback=True)

    print(f"  Microfone : {mic.name}")
    print(f"  Sistema   : {spk.name}  (loopback)")
    print()
    print("  >>> Se o áudio da chamada NÃO sair por esse alto-falante,")
    print("      troque a saída do Windows para ele antes de continuar.")
    print()

    parar = threading.Event()
    mic_buf, loop_buf = [], []
    t_mic = threading.Thread(target=_gravar_stream,
                             args=(mic.recorder(samplerate=SR), parar, mic_buf),
                             daemon=True)
    t_loop = threading.Thread(target=_gravar_stream,
                              args=(loop.recorder(samplerate=SR), parar, loop_buf),
                              daemon=True)
    t_mic.start()
    t_loop.start()

    try:
        input(">>> GRAVANDO... aperte ENTER para parar.\n")
    except KeyboardInterrupt:
        print("\n(parando...)")
    parar.set()
    t_mic.join()
    t_loop.join()

    mic_mono = _mono(mic_buf)
    loop_mono = _mono(loop_buf)
    _escrever_wav(mic_wav, mic_mono)
    _escrever_wav(loop_wav, loop_mono)

    diag = {
        "dur_mic": round(len(mic_mono) / SR, 1),
        "dur_loop": round(len(loop_mono) / SR, 1),
        "rms_mic": round(_rms(mic_mono), 5),
        "rms_loop": round(_rms(loop_mono), 5),
    }
    print(f"\n  Gravado: você {diag['dur_mic']}s (rms {diag['rms_mic']}) | "
          f"participante {diag['dur_loop']}s (rms {diag['rms_loop']})")

    # Guard-rail: loopback praticamente mudo = áudio provavelmente foi para outro device.
    if diag["rms_loop"] < 0.0005:
        print("  ⚠  ATENÇÃO: o áudio do sistema veio quase MUDO. Provavelmente a chamada")
        print("     estava tocando em outro dispositivo (fone/monitor). A fala do")
        print("     participante pode não ter sido capturada. Confira a saída de áudio.")
    if diag["rms_mic"] < 0.0005:
        print("  ⚠  ATENÇÃO: seu microfone veio quase mudo. Confira o mic de entrada.")

    return diag


if __name__ == "__main__":
    # Teste rápido: python record.py  (grava até ENTER em ./out)
    import pathlib
    out = pathlib.Path(__file__).parent / "out"
    out.mkdir(exist_ok=True)
    capturar(out / "mic.wav", out / "loopback.wav")
