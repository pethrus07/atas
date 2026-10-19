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

Daily da Parresia (19/10/2026, ARQUITETURA §21): NUNCA o atalho "1 remoto = todo o loopback é ele"
(foi o que pôs 34 min de 7 pessoas no Mauro em 09/10); sem participantes (ou com 1), limiar + teto
com os parâmetros próprios `daily_diar`; a equipe (`daily_equipe`) entra no vocabulário.
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


def vocabulario(tipo=None, projeto=None, participantes=None, meu_nome=None, caminho=_VOCAB, equipe=None):
    """Termos que o Whisper deve reconhecer nesta reunião (nomes, produtos, siglas). `equipe` (a
    daily) vem primeiro: são os nomes da rodada, e o limite de 40 termos não pode cortá-los."""
    termos = list(equipe or [])
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


def _diarizar(arquivo, threshold, num_speakers, max_falantes, diar_py=None, referencia=None,
              fatia_min=None, min_seg=None):
    """Roda diarize.py no venv separado. Devolve o dict de saída, ou levanta com o motivo.
    `referencia`: wav com a voz do Pedro → a saída traz `similaridade` por grupo (áudio do celular).
    `fatia_min`/`min_seg`: o teto da daily; None = o da reunião normal (a linha de comando não muda)."""
    py = pathlib.Path(diar_py) if diar_py else _DIAR_PY
    if not py.exists():
        raise RuntimeError(f"venv da diarização não encontrado: {py}")
    cmd = [str(py), str(_DIAR_SCRIPT), str(arquivo), str(threshold), str(num_speakers),
           str(max_falantes)] + ([str(referencia)] if referencia else [])
    if fatia_min is not None or min_seg is not None:
        if not referencia:
            cmd.append("")                            # posição da referência vazia
        cmd += [str(fatia_min if fatia_min is not None else ""), str(min_seg if min_seg is not None else "")]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    for ln in reversed((r.stdout or "").splitlines()):
        ln = ln.strip()
        if ln.startswith("{"):
            return json.loads(ln)
        if ln.startswith("["):                       # formato antigo (lista de turnos)
            t = json.loads(ln)
            return {"turnos": t, "falantes": len({x["speaker"] for x in t}), "modo": "?"}
    raise RuntimeError(f"diarização sem saída (código {r.returncode}): "
                       f"{(r.stderr or '').strip()[-400:]}")


def params_diar(sessao, cfg):
    """(threshold, max_falantes, fatia_min, min_seg) da diarização desta sessão. Na daily vêm de
    `daily_diar` (PALPITE até calibrar numa daily real); fora dela, fatia_min/min_seg = None (o teto
    de sempre, dentro do diarize.py)."""
    import config as _config
    from sessao import fora_da_medicao
    thr = cfg.get("diar_threshold", 0.5)
    if not fora_da_medicao(sessao):
        return thr, cfg.get("diar_max_falantes", 6), None, None
    d = {**_config.PADROES["daily_diar"], **(cfg.get("daily_diar") or {})}
    return (d.get("threshold", thr), d["max_falantes"], d["min_fatia"], d["min_segundos"])


def _teto(fatia_min, min_seg):
    """Os argumentos do teto só quando há teto próprio (daily): a chamada da reunião normal fica igual."""
    return {} if fatia_min is None and min_seg is None else {"fatia_min": fatia_min, "min_seg": min_seg}


def equipe_daily(sessao, cfg):
    """Os nomes da equipe (universo da rodada e vocabulário), só na daily."""
    import config as _config
    from sessao import fora_da_medicao
    if not fora_da_medicao(sessao):
        return []
    return list(cfg.get("daily_equipe") or _config.PADROES["daily_equipe"])


def rotular_participantes(segs_part, turnos, prefixo="Participante", ordem_out=None):
    """Reetiqueta 'Participante' -> 'Participante N' por sobreposição de tempo.

    Casa por TEMPO porque os dois lados são independentes: o Whisper corta por frase
    e o diarizador por troca de voz, então os limites nunca batem — o dono do trecho
    é quem mais o ocupa. Numera na ordem de aparição. Um locutor só → 'Participante'.
    Devolve o número de rótulos distintos aplicados. `prefixo` troca o 'Participante' (o áudio
    do celular usa 'Falante'); `ordem_out` (dict) recebe {grupo do diarizador: N}."""
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
        s["speaker"] = f"{prefixo} {ordem[b]}" if b in ordem else prefixo
    if ordem_out is not None:
        ordem_out.update(ordem)
    return len(ordem)


def transcrever_celular(sessao, cfg, log=print):
    """Reunião presencial importada do celular: um canal só com todo mundo (ver celular.py).
    Transcreve, separa as vozes com N = participantes informados + o Pedro, acha qual grupo é o
    Pedro (amostra de referência, depois tom) e rotula "Você" / "Participante N", a confirmar."""
    import audio as _audio
    import celular

    t_ini = time.time()
    modelo, info = carregar_modelo(cfg.get("model", "auto"), cfg.get("dispositivo", "auto"), log)
    log(f"  Modelo {info['modelo']} em {info['dispositivo'].upper()}")
    remotos = sessao.participantes_remotos()
    hot = vocabulario(sessao.tipo, sessao.m.get("projeto"), remotos, cfg.get("meu_nome"),
                      equipe=equipe_daily(sessao, cfg)) if cfg.get("vocabulario", True) else []
    info["vocabulario"] = len(hot)
    fonte = _audio.fonte_audio(sessao, "celular")
    x = _audio.ler_audio(fonte)
    log("  Transcrevendo o áudio do celular…")
    segs = _passada(modelo, x, "Falante", hot, cfg.get("idioma", "pt"))

    n = len(remotos) + 1 if remotos else -1
    ref = celular.referencia(cfg)
    if ref is None:
        try:
            ref = celular.criar_referencia(log=log)
        except Exception as e:
            log(f"    sem amostra da sua voz ({e}); vou tentar pelo tom")
    diar, sims, ordem = {"status": "pulada"}, {}, {}
    if segs and cfg.get("diarizar", True):
        log("  Separando as vozes" + (f" ({n} pessoas, contando você)…" if n > 0 else "…"))
        tmp = pathlib.Path(tempfile.mkdtemp()) / "celular.wav"
        try:
            _audio.escrever_wav(tmp, x)
            thr, mx, fmin, smin = params_diar(sessao, cfg)
            res = _diarizar(tmp, thr, n, mx, cfg.get("diar_python"), referencia=ref, **_teto(fmin, smin))
            rot = rotular_participantes(segs, res.get("turnos"), prefixo="Falante", ordem_out=ordem)
            sims = {f"Falante {ordem[int(k)]}": v for k, v in (res.get("similaridade") or {}).items()
                    if int(k) in ordem}
            diar = {"status": "ok", "modo": res.get("modo"), "falantes": rot,
                    "grupos_brutos": res.get("brutos")}
            if res.get("similaridade_erro"):
                diar["referencia_erro"] = res["similaridade_erro"]
        except Exception as e:
            diar = {"status": "falhou", "detalhe": f"{type(e).__name__}: {e}"[:500]}
            log(f"    ⚠ separação de vozes falhou — todas as falas ficam num rótulo só: {e}")
        finally:
            if tmp.exists():
                tmp.unlink()
            try:
                tmp.parent.rmdir()
            except OSError:
                pass

    rotulos = sorted({s["speaker"] for s in segs})
    escolha = celular.escolher_voce(sims) if len(rotulos) >= 2 else \
        {"rotulo": None, "metodo": "nenhum", "evidencia": "as vozes não foram separadas"}
    tons = {}
    if escolha["rotulo"] is None and len(rotulos) >= 2:
        tom_ref = celular.tom_de_referencia()
        if tom_ref:
            import analise_fala
            for r in rotulos:
                v = analise_fala.voz([dict(s, speaker="Você") for s in segs if s["speaker"] == r], fonte)
                if v:
                    tons[r] = v["tom_hz"]
            escolha = celular.escolher_voce(sims, tons, tom_ref)
            escolha["tom_referencia_hz"] = tom_ref
    mapa = celular.aplicar_rotulos(segs, escolha["rotulo"])
    cel = {**escolha, "rotulo": "Você" if escolha["rotulo"] else None, "grupo": escolha["rotulo"],
           "similaridades": {mapa.get(k, k): v for k, v in sims.items()},
           "tons_hz": {mapa.get(k, k): v for k, v in tons.items()},
           "referencia": str(ref) if ref else None, "voce_confirmado": False}
    sessao.m["celular"] = cel
    sessao.salvar()
    quem = ("você = " + escolha["rotulo"] + f" pela {'amostra de voz' if escolha['metodo'] == 'referencia' else 'altura da voz'}"
            " (a confirmar)") if escolha["rotulo"] else "não deu para saber qual é você (a confirmar no /ata)"
    if diar.get("status") == "ok":
        diar["detalhe"] = f"{diar['falantes']} voz(es) · {diar.get('modo')} · {quem}"
    log(f"    {quem}")
    info["diarizacao"] = diar
    info["celular"] = cel
    segs.sort(key=lambda s: s["start"])
    info["segundos_processamento"] = round(time.time() - t_ini, 1)
    info["trechos"] = len(segs)
    log(f"  {len(segs)} trechos transcritos em {info['segundos_processamento']:.0f}s.")
    return segs, info


def transcrever_sessao(sessao, cfg, log=print):
    """Transcreve os canais disponíveis da sessão. Devolve (segmentos, info)."""
    import audio as _audio

    if sessao.celular:                             # um canal só, todos juntos (14/10/2026)
        return transcrever_celular(sessao, cfg, log)

    t_ini = time.time()
    modelo, info = carregar_modelo(cfg.get("model", "auto"), cfg.get("dispositivo", "auto"), log)
    log(f"  Modelo {info['modelo']} em {info['dispositivo'].upper()}")
    hot = []
    if cfg.get("vocabulario", True):
        hot = vocabulario(sessao.tipo, sessao.m.get("projeto"), sessao.participantes_remotos(),
                          cfg.get("meu_nome"), equipe=equipe_daily(sessao, cfg))
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
    from sessao import fora_da_medicao
    daily = fora_da_medicao(sessao)
    diar = {"status": "pulada"}
    if segs_part and cfg.get("diarizar", True):
        # o atalho de 1 remoto NUNCA vale na daily: 1 nome digitado numa reunião de 7 pessoas é um
        # nome da lista, não a contagem (09/10/2026: 34 min de 7 pessoas atribuídos ao Mauro)
        if len(remotos) == 1 and not daily:
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
                thr, mx, fmin, smin = params_diar(sessao, cfg)
                res = _diarizar(arq, thr, n, mx, cfg.get("diar_python"), **_teto(fmin, smin))
                rot = rotular_participantes(segs_part, res.get("turnos"))
                diar = {"status": "ok", "modo": res.get("modo"), "falantes": rot,
                        "grupos_brutos": res.get("brutos")}
                if daily:
                    diar["parametros"] = {"threshold": thr, "max_falantes": mx, "min_fatia": fmin,
                                          "min_segundos": smin, "calibrado": False}
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
