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
import json
import pathlib
import subprocess

from faster_whisper import WhisperModel

_MODELO = None

# Diarização roda em venv separado (py3.12) via subprocess — ver diarize.py.
_DIAR_PY = pathlib.Path(r"C:\Users\olive\.venvs\diar\Scripts\python.exe")
_DIAR_SCRIPT = pathlib.Path(__file__).parent / "diarize.py"


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


def _diarizar_loopback(loop_wav, threshold=0.5, num_speakers=-1, diar_py=None):
    """Roda a diarização no venv separado. Devolve [{start,end,speaker}] ou None."""
    py = pathlib.Path(diar_py) if diar_py else _DIAR_PY
    if not py.exists() or not _DIAR_SCRIPT.exists():
        return None
    try:
        r = subprocess.run(
            [str(py), str(_DIAR_SCRIPT), str(loop_wav), str(threshold), str(num_speakers)],
            capture_output=True, text=True, timeout=1200,
        )
        # A saída JSON é a última linha não-vazia do stdout (sherpa loga no stderr).
        for ln in reversed((r.stdout or "").splitlines()):
            ln = ln.strip()
            if ln.startswith("["):
                return json.loads(ln)
    except Exception:
        return None
    return None


def _rotular_participantes(segs_part, turnos):
    """Reetiqueta 'Participante' -> 'Participante N' por sobreposição com os turnos.
    Se só houver 1 locutor (ou diarização falhar), mantém 'Participante'."""
    if not turnos:
        return
    def dono(seg):
        best, bid = 0.0, None
        for t in turnos:  # maior sobreposição
            ov = min(seg["end"], t["end"]) - max(seg["start"], t["start"])
            if ov > best:
                best, bid = ov, t["speaker"]
        if bid is None:  # sem sobreposição: turno de centro mais próximo
            c = (seg["start"] + seg["end"]) / 2
            bid = min(turnos, key=lambda t: abs((t["start"] + t["end"]) / 2 - c))["speaker"]
        return bid

    for s in segs_part:
        s["_spk"] = dono(s)
    ids = {s["_spk"] for s in segs_part if s["_spk"] is not None}
    if len(ids) <= 1:
        for s in segs_part:
            s.pop("_spk", None)
        return
    ordem = {}  # numera na ordem de aparição no tempo
    for s in sorted(segs_part, key=lambda x: x["start"]):
        b = s["_spk"]
        if b is not None and b not in ordem:
            ordem[b] = len(ordem) + 1
    for s in segs_part:
        b = s.pop("_spk", None)
        s["speaker"] = f"Participante {ordem[b]}" if b in ordem else "Participante"


def transcrever(mic_wav, loop_wav, tamanho="small", diar=None):
    """Devolve lista de {speaker, start, end, text} ordenada por start.

    diar: dict opcional {enabled, threshold, num_speakers, python} para separar
    os participantes remotos do loopback em 'Participante 1/2/3'."""
    print("  Transcrevendo você...")
    segs_voce = _passada(mic_wav, "Você", tamanho)
    print("  Transcrevendo participante...")
    segs_part = _passada(loop_wav, "Participante", tamanho)

    if diar and diar.get("enabled", True) and segs_part:
        print("  Separando participantes (diarização)...")
        turnos = _diarizar_loopback(
            loop_wav, diar.get("threshold", 0.5),
            diar.get("num_speakers", -1), diar.get("python"),
        )
        if turnos:
            _rotular_participantes(segs_part, turnos)
            nomes = sorted({s["speaker"] for s in segs_part})
            if len(nomes) > 1:
                print(f"    {len(nomes)} participantes identificados: {', '.join(nomes)}")
            else:
                print("    1 participante (sem separação necessária).")
        else:
            print("    diarização indisponível — mantendo 'Participante' único.")

    segs = segs_voce + segs_part
    segs.sort(key=lambda x: x["start"])
    print(f"  {len(segs)} trechos transcritos.")
    return segs


if __name__ == "__main__":
    import pathlib, json
    out = pathlib.Path(__file__).parent / "out"
    segs = transcrever(out / "mic.wav", out / "loopback.wav")
    print(json.dumps(segs, ensure_ascii=False, indent=2))
