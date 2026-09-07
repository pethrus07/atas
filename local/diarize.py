# -*- coding: utf-8 -*-
"""
Diarização offline do canal de LOOPBACK (participantes remotos), via sherpa-onnx.

Roda no venv 'diar' (Python 3.12) — separado do venv de transcrição (3.14),
porque as libs de áudio/ML não convivem no mesmo ambiente. É chamado pelo
transcribe.py por subprocess.

Uso (CLI): python diarize.py <wav_16k_mono> [threshold] [num_speakers]
Saída: JSON em stdout — lista de {start, end, speaker(int)} ordenada por início.

Modelos (offline, baixados uma vez) em models/diar/:
  - sherpa-onnx-pyannote-segmentation-3-0/model.onnx  (detecta fala/troca de voz)
  - embedding.onnx  (CAM++ — vetor de voz p/ agrupar quem é quem)
"""
import json
import pathlib
import sys
import wave

import numpy as np
import sherpa_onnx

BASE = pathlib.Path(__file__).parent
SEG = BASE / "models" / "diar" / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx"
EMB = BASE / "models" / "diar" / "embedding.onnx"


def _ler_wav(caminho):
    with wave.open(str(caminho), "rb") as w:
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        raw = w.readframes(n)
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr


def diarizar(caminho, threshold=0.5, num_speakers=-1):
    """Devolve [{start, end, speaker}] para o áudio (fala de vários locutores)."""
    cfg = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(SEG)),
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(EMB)),
        clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=int(num_speakers),   # -1 = descobrir sozinho (usa threshold)
            threshold=float(threshold),       # maior = menos locutores
        ),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    if not cfg.validate():
        raise RuntimeError("configuração de diarização inválida (modelos ausentes?)")
    sd = sherpa_onnx.OfflineSpeakerDiarization(cfg)
    audio, sr = _ler_wav(caminho)
    if sr != sd.sample_rate:
        raise RuntimeError(f"wav a {sr}Hz, esperado {sd.sample_rate}Hz")
    if audio.size == 0:
        return []
    res = sd.process(audio).sort_by_start_time()
    return [{"start": round(r.start, 2), "end": round(r.end, 2), "speaker": int(r.speaker)}
            for r in res]


if __name__ == "__main__":
    wav = sys.argv[1]
    thr = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
    nsp = int(sys.argv[3]) if len(sys.argv) > 3 else -1
    print(json.dumps(diarizar(wav, thr, nsp), ensure_ascii=False))
