# -*- coding: utf-8 -*-
"""
Transcrição offline com faster-whisper + separação dos participantes remotos.

Duas passadas independentes:
  - mic   -> segmentos rotulados "Você"
  - loop  -> segmentos rotulados "Participante" (depois "Participante N" pela diarização)

Junta tudo e ordena por tempo. vad_filter=True corta o silêncio (enquanto um lado
fala, o outro canal fica mudo), o que acelera e evita "alucinação" no silêncio.

v2 (30/09/2026):
  - **GPU quando existe.** A RTX 3050 Ti (4 GB) nunca tinha sido usada: faltavam as
    DLLs do cuBLAS 12 e do cuDNN 9, que agora vêm dos pacotes pip `nvidia-*-cu12`
    dentro do venv. `_preparar_cuda()` põe essas pastas no caminho de DLLs antes do
    ctranslate2 carregar. Se a GPU falhar por qualquer motivo, cai para CPU/int8 e
    registra o motivo — nunca perde a transcrição por causa dela.
  - **Vocabulário do contexto** (`vocabulario.json` + participantes + projeto) vai
    como `hotwords`, que o faster-whisper repete em toda janela de 30 s (o
    `initial_prompt` só vale no começo do áudio).
  - **Número de participantes informado** crava a diarização; 1 remoto dispensa-a.
"""
import json
import os
import pathlib
import site
import subprocess
import sys
import tempfile
import time

_BASE = pathlib.Path(__file__).parent
_DIAR_PY = pathlib.Path(r"C:\Users\olive\.venvs\diar\Scripts\python.exe")
_DIAR_SCRIPT = _BASE / "diarize.py"
_VOCAB = _BASE / "vocabulario.json"

_MODELOS = {}
_CUDA_PRONTO = False

# Modelo por dispositivo quando o config diz "auto". Medido em 30/09/2026 — ver
# docs/ARQUITETURA.md §6 (tempo por minuto de áudio em cada combinação).
MODELO_AUTO = {"cuda": "large-v3-turbo", "cpu": "small"}


def _preparar_cuda():
    """Acrescenta as pastas bin/ dos pacotes nvidia-* ao caminho de DLLs."""
    global _CUDA_PRONTO
    if _CUDA_PRONTO:
        return
    pastas = []
    for sp in site.getsitepackages() + [site.getusersitepackages()]:
        nv = pathlib.Path(sp) / "nvidia"
        if nv.is_dir():
            pastas += [str(b) for b in nv.glob("*/bin") if b.is_dir()]
    for b in pastas:
        try:
            os.add_dll_directory(b)
        except (OSError, AttributeError):
            pass
    if pastas:
        os.environ["PATH"] = os.pathsep.join(pastas) + os.pathsep + os.environ.get("PATH", "")
    _CUDA_PRONTO = True


def carregar_modelo(tamanho="auto", dispositivo="auto", log=print):
    """Devolve (modelo, info). Tenta GPU e cai para CPU sem levantar."""
    import numpy as np
    from faster_whisper import WhisperModel

    tentativas = []
    if dispositivo in ("auto", "cuda"):
        tentativas.append(("cuda", "float16"))
    if dispositivo in ("auto", "cpu"):
        tentativas.append(("cpu", "int8"))
    motivo_gpu = None
    for dev, ct in tentativas:
        nome = MODELO_AUTO[dev] if tamanho in (None, "", "auto") else tamanho
        chave = (nome, dev, ct)
        if chave in _MODELOS:
            return _MODELOS[chave], {"modelo": nome, "dispositivo": dev, "precisao": ct}
        try:
            if dev == "cuda":
                _preparar_cuda()
            m = WhisperModel(nome, device=dev, compute_type=ct)
            # aquecimento: é aqui que a falta de cuBLAS/cuDNN aparece, não no construtor
            list(m.transcribe(np.zeros(16000, dtype=np.float32), language="pt")[0])
            _MODELOS[chave] = m
            info = {"modelo": nome, "dispositivo": dev, "precisao": ct}
            if motivo_gpu:
                info["gpu_indisponivel"] = motivo_gpu
            return m, info
        except Exception as e:
            if dev == "cuda":
                motivo_gpu = f"{type(e).__name__}: {e}"[:300]
                log(f"  (GPU indisponível, usando CPU: {motivo_gpu})")
            else:
                raise
    raise RuntimeError("nenhum dispositivo de transcrição disponível")


def vocabulario(tipo=None, projeto=None, participantes=None, meu_nome=None, caminho=_VOCAB):
    """Termos que o Whisper deve reconhecer nesta reunião (nomes, produtos, siglas)."""
    termos = []
    try:
        v = json.loads(pathlib.Path(caminho).read_text(encoding="utf-8"))
    except Exception:
        v = {}
    termos += v.get("sempre", [])
    if tipo:
        termos += v.get(tipo, [])
    if projeto:
        termos += (v.get("projetos") or {}).get(projeto, [])
    termos += list(participantes or [])
    if meu_nome:
        termos.append(meu_nome)
    vistos, out = set(), []
    for t in termos:
        t = str(t).strip()
        if t and t.lower() not in vistos:
            vistos.add(t.lower())
            out.append(t)
    return out[:40]


PAUSA_CORTE_S = 0.6          # pausa entre palavras que abre trecho novo


def _recortar(palavras, falante):
    """Palavras com tempo → trechos, cortando em pausa >= PAUSA_CORTE_S ou fim de frase.

    Existe porque o large-v3-turbo, quando recebe vocabulário (hotwords), para de emitir
    os tokens de tempo intermediários e devolve UM trecho para 30 s de fala (medido em
    30/09/2026: 4 falas → 1 trecho, mesmas 52 palavras). Um trecho de 36 s começando em
    0 s bagunça a intercalação com o outro canal e o timestamp de toda citação da ata.
    Recortando pelas palavras, a granularidade deixa de depender do modelo."""
    out, atual = [], []

    def fechar():
        if atual:
            txt = "".join(w.word for w in atual).strip()
            if txt:
                out.append({"speaker": falante, "start": round(float(atual[0].start), 2),
                            "end": round(float(atual[-1].end), 2), "text": txt})
    for w in palavras:
        if atual and (w.start - atual[-1].end >= PAUSA_CORTE_S or
                      (atual[-1].word.strip()[-1:] in ".?!" and w.start - atual[0].start >= 2.0)):
            fechar()
            atual = []
        atual.append(w)
    fechar()
    return out


def _passada(modelo, audio, falante, hotwords=None, idioma="pt"):
    kw = dict(language=idioma, vad_filter=True, beam_size=5, word_timestamps=True)
    if hotwords:
        kw["hotwords"] = ", ".join(hotwords)
    segmentos, _info = modelo.transcribe(audio, **kw)
    out = []
    for s in segmentos:
        if s.words:
            out += _recortar(s.words, falante)
        elif s.text.strip():
            out.append({"speaker": falante, "start": round(s.start, 2),
                        "end": round(s.end, 2), "text": s.text.strip()})
    return out


def _diarizar(arquivo, threshold, num_speakers, max_falantes, diar_py=None):
    """Roda diarize.py no venv separado. Devolve o dict de saída, ou levanta com o motivo."""
    py = pathlib.Path(diar_py) if diar_py else _DIAR_PY
    if not py.exists():
        raise RuntimeError(f"venv da diarização não encontrado: {py}")
    r = subprocess.run(
        [str(py), str(_DIAR_SCRIPT), str(arquivo), str(threshold), str(num_speakers),
         str(max_falantes)],
        capture_output=True, text=True, timeout=3600,
    )
    for ln in reversed((r.stdout or "").splitlines()):
        ln = ln.strip()
        if ln.startswith("{"):
            return json.loads(ln)
        if ln.startswith("["):                       # formato antigo (lista de turnos)
            t = json.loads(ln)
            return {"turnos": t, "falantes": len({x["speaker"] for x in t}), "modo": "?"}
    raise RuntimeError(f"diarização sem saída (código {r.returncode}): "
                       f"{(r.stderr or '').strip()[-400:]}")


def rotular_participantes(segs_part, turnos):
    """Reetiqueta 'Participante' -> 'Participante N' por sobreposição de tempo.

    Casa por TEMPO porque os dois lados são independentes: o Whisper corta por frase
    e o diarizador por troca de voz, então os limites nunca batem — o dono do trecho
    é quem mais o ocupa. Numera na ordem de aparição. Um locutor só → 'Participante'.
    Devolve o número de rótulos distintos aplicados."""
    if not turnos or not segs_part:
        return 1 if segs_part else 0

    def dono(seg):
        best, bid = 0.0, None
        for t in turnos:
            ov = min(seg["end"], t["end"]) - max(seg["start"], t["start"])
            if ov > best:
                best, bid = ov, t["speaker"]
        if bid is None:
            c = (seg["start"] + seg["end"]) / 2
            bid = min(turnos, key=lambda t: abs((t["start"] + t["end"]) / 2 - c))["speaker"]
        return bid

    for s in segs_part:
        s["_spk"] = dono(s)
    ids = {s["_spk"] for s in segs_part if s["_spk"] is not None}
    if len(ids) <= 1:
        for s in segs_part:
            s.pop("_spk", None)
        return 1
    ordem = {}
    for s in sorted(segs_part, key=lambda x: x["start"]):
        b = s["_spk"]
        if b is not None and b not in ordem:
            ordem[b] = len(ordem) + 1
    for s in segs_part:
        b = s.pop("_spk", None)
        s["speaker"] = f"Participante {ordem[b]}" if b in ordem else "Participante"
    return len(ordem)


def transcrever_sessao(sessao, cfg, log=print):
    """Transcreve os canais disponíveis da sessão. Devolve (segmentos, info)."""
    import audio as _audio

    t_ini = time.time()
    modelo, info = carregar_modelo(cfg.get("model", "auto"), cfg.get("dispositivo", "auto"), log)
    log(f"  Modelo {info['modelo']} em {info['dispositivo'].upper()}")
    hot = []
    if cfg.get("vocabulario", True):
        hot = vocabulario(sessao.tipo, sessao.m.get("projeto"), sessao.participantes_remotos(),
                          cfg.get("meu_nome"))
    info["vocabulario"] = len(hot)

    fonte_mic = _audio.fonte_audio(sessao, "mic")
    fonte_loop = _audio.fonte_audio(sessao, "loop")
    segs_voce, segs_part = [], []
    if fonte_mic:
        log("  Transcrevendo você…")
        segs_voce = _passada(modelo, _audio.ler_audio(fonte_mic), "Você", hot,
                             cfg.get("idioma", "pt"))
    if fonte_loop:
        log("  Transcrevendo a chamada…")
        audio_loop = _audio.ler_audio(fonte_loop)
        segs_part = _passada(modelo, audio_loop, "Participante", hot, cfg.get("idioma", "pt"))
    else:
        audio_loop = None

    # ── quem é quem do lado de lá ──
    remotos = sessao.participantes_remotos()
    diar = {"status": "pulada"}
    if segs_part and cfg.get("diarizar", True):
        if len(remotos) == 1:
            diar = {"status": "pulada", "motivo": "1 participante remoto informado",
                    "falantes": 1}
        else:
            n = len(remotos) if len(remotos) >= 2 else -1
            log("  Separando participantes" + (f" ({n} informados)…" if n > 0 else "…"))
            arq, tmp = fonte_loop, None
            try:
                if fonte_loop.suffix.lower() != ".pcm":
                    tmp = pathlib.Path(tempfile.mkdtemp()) / "loop.wav"
                    _audio.escrever_wav(tmp, audio_loop)
                    arq = tmp
                res = _diarizar(arq, cfg.get("diar_threshold", 0.5), n,
                                cfg.get("diar_max_falantes", 6), cfg.get("diar_python"))
                rot = rotular_participantes(segs_part, res.get("turnos"))
                diar = {"status": "ok", "modo": res.get("modo"), "falantes": rot,
                        "grupos_brutos": res.get("brutos")}
                log(f"    {rot} participante(s) remoto(s) ({res.get('modo')}; "
                    f"agrupamento bruto: {res.get('brutos')})")
            except Exception as e:
                diar = {"status": "falhou", "detalhe": f"{type(e).__name__}: {e}"[:500]}
                log(f"    ⚠ diarização falhou — todos do outro lado ficam 'Participante': {e}")
            finally:
                if tmp and tmp.exists():
                    try:
                        tmp.unlink()
                        tmp.parent.rmdir()
                    except OSError:
                        pass
    info["diarizacao"] = diar

    segs = segs_voce + segs_part
    segs.sort(key=lambda x: x["start"])
    info["segundos_processamento"] = round(time.time() - t_ini, 1)
    info["trechos"] = len(segs)
    log(f"  {len(segs)} trechos transcritos em {info['segundos_processamento']:.0f}s.")
    return segs, info


if __name__ == "__main__":
    # python transcribe.py <pasta-da-sessão>  → imprime os segmentos
    sys.path.insert(0, str(_BASE))
    from sessao import Sessao
    import config as _config
    s = Sessao.abrir(sys.argv[1])
    segs, info = transcrever_sessao(s, _config.carregar())
    print(json.dumps({"info": info, "segments": segs}, ensure_ascii=False, indent=2))
