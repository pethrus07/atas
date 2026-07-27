# -*- coding: utf-8 -*-
"""
Transcrição offline com faster-whisper (modelo 'small', já em cache).

Duas passadas independentes:
  - mic.wav       -> segmentos rotulados "Você"
  - loopback.wav  -> segmentos rotulados "Participante"

Depois junta tudo e ordena por tempo de início -> uma transcrição única
com quem falou. vad_filter=True corta o silêncio (enquanto um lado fala, o
outro canal fica mudo), o que acelera muito e evita "alucinação" no silêncio.

Limitação conhecida: numa call em grupo, todos os remotos vêm mixados no
loopback, então caem todos como "Participante" (distingue Você x lado de lá,
não cada pessoa remota).
"""
from faster_whisper import WhisperModel

_MODELO = None


def _get_modelo(tamanho="small"):
    global _MODELO
    if _MODELO is None:
        # CPU + int8: rápido, usa o cache local, não depende de CUDA/GPU.
        _MODELO = WhisperModel(tamanho, device="cpu", compute_type="int8")
    return _MODELO


def _passada(caminho_wav, falante, tamanho):
    modelo = _get_modelo(tamanho)
    segmentos, _info = modelo.transcribe(
        str(caminho_wav),
        language="pt",
        vad_filter=True,
        beam_size=5,
    )
    out = []
    for s in segmentos:
        texto = s.text.strip()
        if texto:
            out.append({
                "speaker": falante,
                "start": round(s.start, 2),
                "end": round(s.end, 2),
                "text": texto,
            })
    return out


def transcrever(mic_wav, loop_wav, tamanho="small"):
    """Devolve lista de {speaker, start, end, text} ordenada por start."""
    print("  Transcrevendo você...")
    segs = _passada(mic_wav, "Você", tamanho)
    print("  Transcrevendo participante...")
    segs += _passada(loop_wav, "Participante", tamanho)
    segs.sort(key=lambda x: x["start"])
    print(f"  {len(segs)} trechos transcritos.")
    return segs


if __name__ == "__main__":
    import pathlib, json
    out = pathlib.Path(__file__).parent / "out"
    segs = transcrever(out / "mic.wav", out / "loopback.wav")
    print(json.dumps(segs, ensure_ascii=False, indent=2))
