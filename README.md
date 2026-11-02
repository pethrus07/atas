# Ágora

English · [Português](README.pt-BR.md)

A meeting recorder that runs entirely on one Windows machine. It writes the call to disk while it happens,
transcribes it locally on the GPU, separates who spoke, and builds structured minutes (decisions, action
items with owner and due date, open questions, risks). Every item in the minutes points to the exact part
of the conversation it came from. Anything that was not said shows up as a gap, never as data.

The visible name has been Ágora since 2026-10-22. The repository, the folder, `atas.py` and the `/ata`
skill keep the old name ("atas" means "minutes" in Portuguese) on purpose.

## Status

In daily use, local only (2026-11). Publishing minutes to clients (Cloudflare Worker + D1) still exists in the
code but has been switched off since 2026-10-22: the Worker is empty and nothing leaves the machine.

## The problem

Important meetings fade from memory within days. Taking notes during a call pulls attention away from the
conversation, and a summary written afterwards mixes what was said with what was remembered. Ágora records,
transcribes, and only keeps what it can quote.

## Stack

- Python 3.14: `tkinter` (window), `soundcard` and `sounddevice` (microphone and call audio capture),
  `faster-whisper` large-v3-turbo on the GPU (CUDA), `av`/ffmpeg (Opus), `numpy`.
- Python 3.12 in a separate venv: `sherpa-onnx` for speaker separation (diarization).
- Claude Code (`claude -p`) to turn the transcript into minutes, with a quote audit.
- Headless Chrome for the PDF.
- Cloudflare Worker + D1 (`worker/`), unused since 2026-10-22.

## How it works

```
[Windows machine, everything local]
 app.py (window) / atas.py (CLI)
   record.py       microphone + call audio -> .pcm on disk, chunk by chunk
   transcribe.py   Whisper large-v3-turbo (GPU) + vocabulary per meeting type
   diarize.py      separates the remote voices (own venv), with a cap
   estruturar.py   claude -p -> ata.json, audited by ata.py
   render.py       ata.md · ata.html · PDF · entregavel.pdf
   analise_fala.py speech review ("Raio-X", internal)
   ao_vivo.py      live transcript (ao-vivo.md) and the "interventionist" mode

[Cloudflare] worker/ (Worker + D1): empty and unused since 2026-10-22.
             upload.py and the publishing code stay in the repo, switched off.
```

If the PC freezes, the recording loses at most the last ~5 s: audio goes to disk in chunks.

## Running locally

Windows only, with an NVIDIA GPU for fast transcription (it works without one, just slower).

1. Main venv (Python 3.14): `faster-whisper soundcard sounddevice numpy av pytest pillow` and, for the GPU,
   `nvidia-cublas-cu12` and `nvidia-cudnn-cu12==9.*`.
2. Diarization venv (Python 3.12): `sherpa-onnx numpy`, with the ONNX models (~35 MB) in `local/models/diar/`.
3. Claude Code installed.
4. Copy `local/config.example.json` to `local/config.json`. No key is needed to record.
5. Run `python local/app.py` (window) or `python local/atas.py --help` (command line).

The day-to-day manual (daily stand-up, marking a moment, interventionist mode, meetings recorded on a phone,
practice mode) is in Portuguese at [docs/USO.md](docs/USO.md).

## Tests

```
python -m pytest tests -q                  # 211 tests, ~1 min
python -m pytest tests -q -m "not lento"   # skips the ones that use Whisper, Chrome or a real device
cd worker && npm test                      # 10 Worker tests (Miniflare)
```

The 2 tests in `tests/test_dispositivos_reais.py` need a real microphone and audio output. The audio fixtures
(`tests/fixtures/*.opus`) are synthetic voices (SAPI), not recordings of people.

## Layout

```
local/       app, CLI and the pipeline (record, transcribe, separate voices, structure, render)
tests/       pytest suite and synthetic fixtures
worker/      Cloudflare Worker + D1 (password-protected publishing, unused)
claude/      the /ata Claude Code skill
docs/        ARQUITETURA.md (source of truth), USO.md (manual), MELHORIAS.md (backlog), arquitetura/ (diagrams)
assets/      icon
```

Kept out of git: `atas-salvas/` (one folder per meeting, with audio and transcript), `fala-analise/`,
`local/config.json`, `local/out/`, `local/models/`.

## Architecture

- [docs/ARQUITETURA.md](docs/ARQUITETURA.md) (Portuguese): pipeline, data and retention, pitfalls, recipes.
- [docs/arquitetura/](docs/arquitetura/README.md): use cases (UML), process (BPMN) and containers (C4).

## Decisions and known limits

- Internal meetings never leave the machine. Client publishing has been off since 2026-10-22.
- Nothing is published on its own: memory, notes and tasks are proposed and only count after the owner says yes.
- Audio is deleted 30 days after the minutes are secured (structured and checked).
- Speaker separation makes mistakes on calls with many people. Only lines labelled "Você" (you) are attributed
  to the owner.
- Not yet calibrated with real use: the daily stand-up cap (`docs/MELHORIAS.md` §21) and the interventionist
  mode (§22).
- Built for one machine and one person. Venv paths live in the docs, not in an installer.

## License

All rights reserved.
