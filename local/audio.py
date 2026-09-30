# -*- coding: utf-8 -*-
"""
Áudio da sessão depois de gravado: ler, compactar, conferir e aposentar.

Retenção (decisão 3 de 30/09/2026): o áudio fica **só nesta máquina**, compactado
em Opus (~12 MB por 100 min por canal), por `audio_reter_dias` (padrão 30), e então é
apagado. Nunca sobe. Serve para três coisas que o "só texto" não permitia:
reprocessar uma reunião que falhou, retranscrever com um modelo melhor e calibrar
a diarização em voz real — as 27 atas de jul–set/2026 não servem para isso
porque o áudio delas já não existe.

Ordem de segurança: o PCM só é apagado depois de o Opus existir E decodificar com
a mesma duração. Um PCM nunca some antes de ter substituto conferido.
"""
import datetime as _dt
import pathlib
import shutil

import numpy as np

SR = 16000
BITRATE = 24000


def ler_pcm(caminho):
    """PCM 16 bits mono 16 kHz → float32 em [-1, 1]. Tolera arquivo com byte ímpar
    no fim (crash no meio de uma escrita)."""
    p = pathlib.Path(caminho)
    if not p.exists() or p.stat().st_size < 2:
        return np.zeros(0, dtype=np.float32)
    n = p.stat().st_size // 2
    a = np.fromfile(str(p), dtype="<i2", count=n)
    return a.astype(np.float32) / 32768.0


def ler_audio(caminho):
    """Lê .pcm (cru) ou qualquer formato que o PyAV decodifique (opus, wav…)."""
    p = pathlib.Path(caminho)
    if p.suffix.lower() == ".pcm":
        return ler_pcm(p)
    from faster_whisper.audio import decode_audio
    return decode_audio(str(p), sampling_rate=SR)


def escrever_wav(caminho, mono_f32):
    import wave
    pcm = (np.clip(mono_f32, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def compactar_opus(origem_pcm, destino_opus):
    """PCM → Ogg/Opus mono 16 kHz, via PyAV (sem ffmpeg externo)."""
    import av
    x = ler_pcm(origem_pcm)
    if x.size == 0:
        # PCM sumido ou vazio (outro processo já aposentou?): nunca gravar um Opus vazio
        # por cima de um bom
        raise RuntimeError(f"origem de áudio vazia ou ausente: {origem_pcm}")
    pcm = (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2")
    destino_opus = pathlib.Path(destino_opus)
    tmp = destino_opus.with_suffix(".opus.tmp")
    with av.open(str(tmp), "w", format="ogg") as cont:
        st = cont.add_stream("libopus", rate=SR)
        st.bit_rate = BITRATE
        st.layout = "mono"
        passo = SR // 50 * 10             # blocos de 200 ms
        for i in range(0, len(pcm), passo):
            fr = av.AudioFrame.from_ndarray(pcm[i:i + passo].reshape(1, -1), format="s16",
                                            layout="mono")
            fr.sample_rate = SR
            for pkt in st.encode(fr):
                cont.mux(pkt)
        for pkt in st.encode(None):
            cont.mux(pkt)
    tmp.replace(destino_opus)
    return destino_opus


def duracao_opus(caminho):
    import av
    with av.open(str(caminho)) as c:
        st = c.streams.audio[0]
        if st.duration and st.time_base:
            return float(st.duration * st.time_base)
        return sum(fr.samples for fr in c.decode(st)) / (st.rate or SR)


def aposentar_pcm(sessao):
    """Compacta mic/loop para audio/*.opus, confere a duração e só então apaga o PCM."""
    sessao.audio_dir.mkdir(exist_ok=True)
    feitos = {}
    for nome, pcm in (("mic", sessao.mic_pcm), ("loop", sessao.loop_pcm)):
        if not pcm.exists():
            continue
        dur_pcm = pcm.stat().st_size / 2 / SR
        destino = sessao.audio_dir / f"{nome}.opus"
        confere = False
        if destino.exists():                   # já compactado numa execução anterior?
            try:
                confere = abs(duracao_opus(destino) - dur_pcm) <= max(1.0, 0.01 * dur_pcm)
            except Exception:
                confere = False
        if not confere:
            compactar_opus(pcm, destino)
        dur_opus = duracao_opus(destino)
        if dur_pcm > 1 and abs(dur_opus - dur_pcm) > max(1.0, 0.01 * dur_pcm):
            raise RuntimeError(f"{nome}.opus tem {dur_opus:.1f}s e o PCM {dur_pcm:.1f}s — "
                               f"PCM mantido")
        pcm.unlink()
        feitos[nome] = {"segundos": round(dur_opus, 1),
                        "mb": round(destino.stat().st_size / 1e6, 1)}
    return feitos


def fonte_audio(sessao, nome):
    """O áudio disponível de um canal: o PCM se ainda existir, senão o Opus."""
    pcm = sessao.mic_pcm if nome == "mic" else sessao.loop_pcm
    if pcm.exists():
        return pcm
    op = sessao.audio_dir / f"{nome}.opus"
    return op if op.exists() else None


def limpar_expirados(sessoes, dias):
    """Apaga audio/ das sessões prontas mais velhas que `dias`. Devolve os ids limpos."""
    if not dias or dias <= 0:
        return []
    limite = _dt.datetime.now().astimezone() - _dt.timedelta(days=dias)
    limpas = []
    for s in sessoes:
        if s.m.get("estado") not in ("pronto", "pronto_com_falhas") or not s.audio_dir.exists():
            continue
        # conta a partir de quando a ata ficou pronta, não do início da reunião: uma
        # gravação órfã recuperada semanas depois não perde o áudio na hora
        ini = s.m.get("processado_em") or s.m.get("fim") or s.m.get("inicio") or s.m.get("criado")
        try:
            quando = _dt.datetime.fromisoformat(ini)
        except (TypeError, ValueError):
            continue
        if quando.tzinfo is None:
            quando = quando.astimezone()
        if quando < limite:
            shutil.rmtree(s.audio_dir, ignore_errors=True)
            s.etapa("audio", "ok", f"áudio apagado pela retenção de {dias} dias", apagado=True)
            limpas.append(s.id)
    return limpas
