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


def _abre(dispositivo):
    """Tenta abrir o dispositivo de verdade e ler um bloco.

    Existe porque o `soundcard` só falha na HORA DE ABRIR, não ao listar: ele
    exige que o mix format do device seja EXTENSIBLE e faz isso com um
    `assert` seco —

        assert ppMixFormat[0][0].Format.wFormatTag == 0xFFFE

    Um `AssertionError` sem mensagem, dentro de uma thread, com o .bat
    fechando a janela em seguida: o gravador simplesmente não abria, e não
    sobrava nada na tela para explicar. Foi o que aconteceu em 03/09/2026 com
    o `Microphone (AB13X USB Audio)`, que tinha virado o microfone padrão.
    """
    try:
        with dispositivo.recorder(samplerate=SR) as r:
            r.record(numframes=BLOCK)
        return True
    except Exception:
        return False


def _escolher_mic(preferido=None):
    """Primeiro microfone que ABRE, não o primeiro que existe.

    Ordem: o que o config pedir, depois o padrão do Windows, depois os demais.
    Devolve (microfone, aviso) — o aviso é dito em voz alta na tela, porque
    gravar com um microfone que não é o que a pessoa acha que é dá uma ata
    com a sua voz baixa e nenhum sinal de que algo mudou.
    """
    candidatos, vistos = [], set()

    def juntar(d):
        if d is not None and d.name not in vistos:
            vistos.add(d.name)
            candidatos.append(d)

    if preferido:
        for m in sc.all_microphones(include_loopback=False):
            if preferido.lower() in m.name.lower():
                juntar(m)
    try:
        juntar(sc.default_microphone())
    except Exception:
        pass
    for m in sc.all_microphones(include_loopback=False):
        juntar(m)

    if not candidatos:
        raise RuntimeError("Nenhum microfone encontrado no Windows.")

    padrao = candidatos[0].name
    for m in candidatos:
        if _abre(m):
            aviso = None
            if m.name != padrao:
                aviso = (f"o dispositivo padrão ({padrao}) não abre neste driver; "
                         f"gravando por {m.name}")
            return m, aviso
    raise RuntimeError(
        "Nenhum microfone do sistema pôde ser aberto. Todos falharam ao iniciar a captura.")


def capturar(mic_wav, loop_wav, mic_preferido=None):
    """
    Grava até o usuário apertar ENTER (ou Ctrl+C).
    Escreve mic_wav e loop_wav. Devolve um dict com diagnóstico (duração/RMS).
    """
    mic, aviso_mic = _escolher_mic(mic_preferido)

    # o loopback pode falhar pelo mesmo motivo do microfone; se falhar, vale
    # mais gravar só a sua voz do que não gravar reunião nenhuma
    spk = sc.default_speaker()
    loop, aviso_loop = sc.get_microphone(spk.name, include_loopback=True), None
    if not _abre(loop):
        alternativas = [m for m in sc.all_microphones(include_loopback=True)
                        if m.isloopback and m.name != loop.name]
        loop = next((m for m in alternativas if _abre(m)), None)
        if loop is None:
            raise RuntimeError(
                f"O loopback de '{spk.name}' não abre e não há outro disponível.")
        aviso_loop = (f"o loopback da saída padrão ({spk.name}) não abre; "
                      f"capturando de {loop.name} — confira se a chamada toca AÍ")

    print(f"  Microfone : {mic.name}")
    if aviso_mic:
        print(f"  ⚠  {aviso_mic}")
    print(f"  Sistema   : {loop.name}  (loopback)")
    if aviso_loop:
        print(f"  ⚠  {aviso_loop}")
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
    except EOFError:
        # sem console interativo (execução agendada, pipe): não dá para
        # esperar ENTER. Melhor parar limpo do que estourar e perder o áudio.
        print("(sem terminal interativo — encerrando a captura)")
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
