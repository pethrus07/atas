# -*- coding: utf-8 -*-
"""
Diarização offline do canal de LOOPBACK (participantes remotos), via sherpa-onnx.

Roda no venv 'diar' (Python 3.12) — separado do venv de transcrição (3.14),
porque o sherpa-onnx não tem roda para o 3.14. É chamado pelo transcribe.py por
subprocess. Aqui só entram numpy e sherpa_onnx.

Uso (CLI): python diarize.py <audio.pcm|audio.wav> [threshold] [num_speakers] [max_falantes] [referencia.wav]
Saída (stdout, última linha): JSON
    {"turnos": [{start, end, speaker}], "falantes": N, "modo": "...", "brutos": M,
     "similaridade": {speaker: cosseno com a voz de referência}}   ← só com referência

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


def _embedding(extrator, audio):
    st = extrator.create_stream()
    st.accept_waveform(SR, audio)
    st.input_finished()
    v = np.asarray(extrator.compute(st), dtype=np.float32)
    return v / (np.linalg.norm(v) + 1e-9)


def similaridades(audio, turnos, referencia, max_s=30.0, min_s=2.0):
    """Quanto a voz de cada grupo parece com a voz de referência (cosseno entre os vetores CAM++).

    Serve ao áudio do celular (14/10/2026): um canal só, com o Pedro junto dos outros. A referência
    é uma amostra da voz dele tirada do canal do microfone de uma reunião gravada pelo Atas (que só
    tem ele). Cada grupo entra com os turnos mais longos até `max_s`; grupo com menos de `min_s`
    de fala fica de fora (vetor de voz de 1 s não diz nada)."""
    ext = sherpa_onnx.SpeakerEmbeddingExtractor(
        sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(EMB)))
    ref, sr = _ler(referencia)
    if sr != SR or ref.size < SR * min_s:
        raise RuntimeError("amostra de referência ausente, curta ou fora de 16 kHz")
    e_ref = _embedding(ext, ref)
    out = {}
    for spk in sorted({t["speaker"] for t in turnos}):
        pedacos, tot = [], 0.0
        for t in sorted((t for t in turnos if t["speaker"] == spk),
                        key=lambda t: t["end"] - t["start"], reverse=True):
            pedacos.append(audio[int(t["start"] * SR):int(t["end"] * SR)])
            tot += t["end"] - t["start"]
            if tot >= max_s:
                break
        if tot < min_s:
            continue
        out[str(spk)] = round(float(np.dot(e_ref, _embedding(ext, np.concatenate(pedacos)))), 3)
    return out


def diarizar(caminho, threshold=0.5, num_speakers=-1, max_falantes=6, referencia=None):
    audio, sr = _ler(caminho)
    if sr != SR:
        raise RuntimeError(f"áudio a {sr}Hz, esperado {SR}Hz")
    if audio.size == 0:
        return {"turnos": [], "falantes": 0, "modo": "vazio", "brutos": 0}
    if int(num_speakers) >= 1:
        turnos = _rodar(audio, threshold, int(num_speakers))
        res = {"turnos": turnos, "falantes": len({t["speaker"] for t in turnos}),
               "modo": "informado", "brutos": int(num_speakers)}
    else:
        turnos = _rodar(audio, threshold, -1)
        brutos = len({t["speaker"] for t in turnos})
        n = max(1, min(int(max_falantes), relevantes(turnos)))
        if n < brutos:
            turnos = _rodar(audio, threshold, n)
            modo = "teto"
        else:
            modo = "limiar"
        res = {"turnos": turnos, "falantes": len({t["speaker"] for t in turnos}),
               "modo": modo, "brutos": brutos}
    if referencia:
        try:
            res["similaridade"] = similaridades(audio, res["turnos"], referencia)
        except Exception as e:                    # referência é bônus: nunca derruba a diarização
            res["similaridade_erro"] = f"{type(e).__name__}: {e}"[:300]
    return res


if __name__ == "__main__":
    arq = sys.argv[1]
    thr = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
    nsp = int(sys.argv[3]) if len(sys.argv) > 3 else -1
    mx = int(sys.argv[4]) if len(sys.argv) > 4 else 6
    ref = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] else None
    print(json.dumps(diarizar(arq, thr, nsp, mx, ref), ensure_ascii=False))
