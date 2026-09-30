# -*- coding: utf-8 -*-
"""
Diarização offline do canal de LOOPBACK (participantes remotos), via sherpa-onnx.

Roda no venv 'diar' (Python 3.12) — separado do venv de transcrição (3.14),
porque o sherpa-onnx não tem roda para o 3.14. É chamado pelo transcribe.py por
subprocess. Aqui só entram numpy e sherpa_onnx.

Uso (CLI): python diarize.py <audio.pcm|audio.wav> [threshold] [num_speakers] [max_falantes]
Saída (stdout, última linha): JSON
    {"turnos": [{start, end, speaker}], "falantes": N, "modo": "...", "brutos": M}

Modelos (offline, baixados uma vez) em models/diar/:
  - sherpa-onnx-pyannote-segmentation-3-0/model.onnx  (detecta fala/troca de voz)
  - embedding.onnx  (CAM++ — vetor de voz p/ agrupar quem é quem)

Como o número de falantes é decidido (v2, 30/09/2026):
  1. **Número conhecido** (o Pedro informou os participantes na partida) → é
     cravado. É a alavanca mais forte: com um inteiro >= 1 o threshold nem é consultado.
  2. **Número desconhecido** → agrupa pelo threshold e aplica o TETO: só conta como
     pessoa o grupo que ocupa >= FATIA_MIN do tempo de fala; se sobrar menos grupos
     relevantes do que o agrupamento abriu, roda de novo cravando esse número
     (limitado a max_falantes). É o conserto do "1 pessoa = 78 Participantes" de
     08/09/2026: a cauda de clusters minúsculos era a mesma voz variando pelo codec.
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
SR = 16000
FATIA_MIN = 0.05     # grupo com menos de 5% da fala não é contado como pessoa
MIN_SEG_S = 20.0     # ...nem grupo com menos de 20 s de fala no total


def _ler(caminho):
    p = pathlib.Path(caminho)
    if p.suffix.lower() == ".pcm":
        n = p.stat().st_size // 2
        return np.fromfile(str(p), dtype="<i2", count=n).astype(np.float32) / 32768.0, SR
    with wave.open(str(p), "rb") as w:
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        raw = w.readframes(n)
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr


def _rodar(audio, threshold, num_clusters):
    cfg = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(SEG)),
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(EMB)),
        # threshold = distância máxima para dois trechos serem a MESMA pessoa:
        # quanto menor, mais locutores. Voz de loopback varia muito pelo codec.
        clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=int(num_clusters), threshold=float(threshold)),
        # Descartam fala e pausa curtas demais: sem isso, um "aham" no meio da
        # frase do outro abriria turno e o rótulo trocaria no meio do trecho.
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    if not cfg.validate():
        raise RuntimeError("configuração de diarização inválida (modelos ausentes?)")
    sd = sherpa_onnx.OfflineSpeakerDiarization(cfg)
    res = sd.process(audio).sort_by_start_time()
    return [{"start": round(r.start, 2), "end": round(r.end, 2), "speaker": int(r.speaker)}
            for r in res]


def relevantes(turnos, fatia_min=FATIA_MIN, min_seg=MIN_SEG_S):
    """Quantos grupos têm fala suficiente para serem uma pessoa de verdade."""
    tempo = {}
    for t in turnos:
        tempo[t["speaker"]] = tempo.get(t["speaker"], 0.0) + (t["end"] - t["start"])
    total = sum(tempo.values()) or 1.0
    return sum(1 for v in tempo.values() if v / total >= fatia_min and v >= min_seg)


def diarizar(caminho, threshold=0.5, num_speakers=-1, max_falantes=6):
    audio, sr = _ler(caminho)
    if sr != SR:
        raise RuntimeError(f"áudio a {sr}Hz, esperado {SR}Hz")
    if audio.size == 0:
        return {"turnos": [], "falantes": 0, "modo": "vazio", "brutos": 0}
    if int(num_speakers) >= 1:
        turnos = _rodar(audio, threshold, int(num_speakers))
        return {"turnos": turnos, "falantes": len({t["speaker"] for t in turnos}),
                "modo": "informado", "brutos": int(num_speakers)}
    turnos = _rodar(audio, threshold, -1)
    brutos = len({t["speaker"] for t in turnos})
    n = max(1, min(int(max_falantes), relevantes(turnos)))
    if n < brutos:
        turnos = _rodar(audio, threshold, n)
        modo = "teto"
    else:
        modo = "limiar"
    return {"turnos": turnos, "falantes": len({t["speaker"] for t in turnos}),
            "modo": modo, "brutos": brutos}


if __name__ == "__main__":
    arq = sys.argv[1]
    thr = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
    nsp = int(sys.argv[3]) if len(sys.argv) > 3 else -1
    mx = int(sys.argv[4]) if len(sys.argv) > 4 else 6
    print(json.dumps(diarizar(arq, thr, nsp, mx), ensure_ascii=False))
