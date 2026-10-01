# -*- coding: utf-8 -*-
"""
Captura de áudio de reunião no Windows, sem driver e sem admin — e sem perder nada.

Grava DUAS fontes físicas separadas ao mesmo tempo, via WASAPI (lib soundcard):
  - o microfone                 -> vira o falante "Você"
  - o loopback do alto-falante  -> vira "Participante" (tudo o que sai pelas caixas/fone)

A separação "você × o outro lado" nasce daqui, sem IA.

O que mudou na v2 (30/09/2026) e por quê:
  - **Cada bloco de 100 ms vai para o disco na hora** (`mic.pcm`/`loop.pcm` na pasta da
    sessão), sem buffer do Python e com fsync a cada 5 s. Antes o áudio vivia numa lista em
    memória e só virava WAV no fim; um travamento do PC em ~20/09 apagou a conversa com o
    Ricardo inteira. Agora um crash custa no máximo os últimos ~5 s.
  - **Dispositivo que cai é reaberto**, e o buraco é preenchido com silêncio medido pelo
    relógio, para a linha do tempo dos dois canais continuar batendo.
  - **O Windows não dorme** enquanto grava (SetThreadExecutionState) — a hibernação desta
    máquina é conhecida por derrubar a sessão.
  - **Checagem antes de começar** (`medir_niveis`) e níveis ao vivo para a UI.
"""
import ctypes
import os
import threading
import time

import numpy as np
import soundcard as sc

SR = 16000            # 16 kHz mono: o que o Whisper usa (o WASAPI reamostra sozinho)
BLOCK = SR // 10      # blocos de 100 ms
FSYNC_S = 5.0
LIMIAR_MUDO = 0.0005  # RMS abaixo disso = canal praticamente mudo

_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


def manter_acordado(ligar=True):
    """Impede o Windows de suspender/hibernar enquanto a reunião é gravada."""
    try:
        flags = _ES_CONTINUOUS | (_ES_SYSTEM_REQUIRED if ligar else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(flags)
    except Exception:
        pass


def _mono(data):
    return data.mean(axis=1) if data.ndim == 2 else data


def _pcm16(mono_f32):
    return (np.clip(mono_f32, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


def _rms(x):
    return float(np.sqrt(np.mean(np.square(x)))) if x.size else 0.0


# ── COM por thread ────────────────────────────────────────────────────────────
def _guardiao_com(pronto):
    """Segura o MTA do processo vivo enquanto o programa existir.

    O MTA de um processo some quando a última thread que chamou CoInitializeEx(MTA)
    termina. O `soundcard` só o inicializa na thread que o importa; se ela acaba (a
    checagem de áudio da janela), até ler `.name` de um dispositivo passa a dar
    0x800401F0. Com esta thread viva, toda thread sem COM próprio cai no MTA implícito."""
    try:
        ctypes.windll.ole32.CoInitializeEx(None, 0x0)
    except Exception:
        pass
    pronto.set()
    threading.Event().wait()          # dorme para sempre (daemon: morre com o processo)


_com_pronto = threading.Event()
threading.Thread(target=_guardiao_com, args=(_com_pronto,), daemon=True,
                 name="guardiao-com").start()
_com_pronto.wait(2)


class com_na_thread:
    """Inicializa o COM (MTA) na thread atual e desfaz ao sair.

    Existe por causa do erro 0x800401F0 (CO_E_NOTINITIALIZED) que derrubou os dois
    canais na primeira reunião real da v2 (30/09/2026, 4 min, 0 bytes gravados): o
    `soundcard` inicializa o COM UMA vez, na thread que o importa. Na janela, essa
    era a thread da checagem de áudio, que termina — e com ela o MTA do processo.
    Toda thread que abre dispositivo passa por aqui."""

    def __enter__(self):
        self._dono = False
        try:
            hr = ctypes.windll.ole32.CoInitializeEx(None, 0x0)   # COINIT_MULTITHREADED
            self._dono = hr in (0, 1)                            # S_OK / S_FALSE
        except Exception:
            pass
        return self

    def __exit__(self, *exc):
        if self._dono:
            try:
                ctypes.windll.ole32.CoUninitialize()
            except Exception:
                pass
        return False


# ── segunda via: PortAudio (sounddevice) ─────────────────────────────────────
class _GravadorPA:
    def __init__(self, idx, canais):
        import sounddevice as sd
        extra = None
        try:
            extra = sd.WasapiSettings(auto_convert=True)       # o Windows reamostra p/ 16 kHz
        except Exception:
            pass
        self._st = sd.InputStream(device=idx, samplerate=SR, channels=canais, dtype="float32",
                                  blocksize=BLOCK, extra_settings=extra)

    def __enter__(self):
        self._st.start()
        return self

    def __exit__(self, *exc):
        try:
            self._st.stop()
        finally:
            self._st.close()
        return False

    def record(self, numframes):
        dado, _estouro = self._st.read(numframes)
        return dado


class MicPortAudio:
    """Mesmo contrato do microfone do `soundcard` (`name`, `recorder()`), via PortAudio.

    É a via do microfone que o `soundcard` não abre — o `Microphone (AB13X USB Audio)`,
    o fone USB do Pedro, que não reporta o formato EXTENSIBLE (03/09 e 30/09/2026). O
    PortAudio fala WASAPI sem essa exigência."""

    via = "portaudio"

    def __init__(self, nome, idx, canais):
        self.name = nome
        self.idx = idx
        self.canais = canais

    def recorder(self, samplerate=SR):
        return _GravadorPA(self.idx, self.canais)

    @classmethod
    def achar(cls, nome):
        try:
            import sounddevice as sd
        except Exception:
            return None
        apis = sd.query_hostapis()
        alvo = nome.lower()
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] < 1 or "WASAPI" not in apis[d["hostapi"]]["name"]:
                continue
            if d["name"].lower() == alvo or alvo in d["name"].lower() or d["name"].lower() in alvo:
                return cls(nome, i, min(2, int(d["max_input_channels"])))
        return None


# ── escolha de dispositivo ────────────────────────────────────────────────────
def _abre(dispositivo):
    """Tenta abrir o dispositivo de verdade e ler um bloco.

    O `soundcard` só falha na HORA DE ABRIR, não ao listar (assert seco de formato
    EXTENSIBLE). Por isso nenhum dispositivo é escolhido sem abrir."""
    try:
        with com_na_thread():
            with dispositivo.recorder(samplerate=SR) as r:
                r.record(numframes=BLOCK)
        return True
    except Exception:
        return False


_INTERNOS = ("realtek", "intel", "smart sound", "array", "integrad", "internal", "conexant")


def _e_interno(nome):
    n = (nome or "").lower()
    return any(k in n for k in _INTERNOS)


def _escolher_mic(preferido=None):
    """O microfone certo é o do FONE, não o do notebook.

    Ordem: o que o config pedir; o padrão do Windows; dispositivos externos (USB,
    Bluetooth — o fone) antes dos internos. Para cada um, tenta o `soundcard` e, se
    não abrir, a via PortAudio. Devolve (microfone, aviso)."""
    with com_na_thread():
        todos = list(sc.all_microphones(include_loopback=False))
        try:
            padrao_win = sc.default_microphone()
        except Exception:
            padrao_win = None
    candidatos, vistos = [], set()

    def juntar(d):
        if d is not None and d.name not in vistos:
            vistos.add(d.name)
            candidatos.append(d)

    if preferido:
        for m in todos:
            if preferido.lower() in m.name.lower():
                juntar(m)
    # fone plugado (USB/Bluetooth) ganha do microfone do notebook, mesmo que o Windows
    # ainda aponte para o interno: quem pluga o fone vai falar por ele
    for m in todos:
        if not _e_interno(m.name):
            juntar(m)
    juntar(padrao_win)
    for m in todos:
        juntar(m)
    if not candidatos:
        raise RuntimeError("Nenhum microfone encontrado no Windows.")

    desejado = candidatos[0].name
    for m in candidatos:
        escolhido = m if _abre(m) else None
        if escolhido is None:
            pa = MicPortAudio.achar(m.name)
            if pa is not None and _abre(pa):
                escolhido = pa
        if escolhido is not None:
            aviso = None
            if escolhido.name != desejado:
                aviso = f"{desejado} não abriu; gravando sua voz por {escolhido.name}"
            return escolhido, aviso
    raise RuntimeError("Nenhum microfone do sistema pôde ser aberto.")


def _escolher_loop():
    """Loopback da saída padrão; se não abrir, o primeiro loopback que abre.
    Devolve (loopback|None, aviso). None = grava só a sua voz (melhor que nada)."""
    with com_na_thread():
        spk = sc.default_speaker()
        try:
            loop = sc.get_microphone(spk.name, include_loopback=True)
        except Exception:
            loop = None
        todos = [m for m in sc.all_microphones(include_loopback=True) if m.isloopback]
    if loop is not None and _abre(loop):
        return loop, None
    for m in todos:
        if (loop is None or m.name != loop.name) and _abre(m):
            return m, (f"o som da saída padrão ({spk.name}) não abre; capturando de "
                       f"{m.name} — confira se a chamada toca aí")
    return None, (f"não consigo ouvir a chamada — só a sua voz será gravada. "
                  f"Confira a saída de som ({spk.name}).")


def escolher_dispositivos(mic_preferido=None):
    mic, aviso_mic = _escolher_mic(mic_preferido)
    loop, aviso_loop = _escolher_loop()
    return {"mic": mic, "loop": loop, "avisos": [a for a in (aviso_mic, aviso_loop) if a]}


def medir_niveis(disp, segundos=3.0):
    """Checagem de ~3 s antes de gravar: RMS de cada canal.

    O loopback em silêncio aqui é normal se a chamada ainda não começou, então
    vira aviso e não bloqueio; o microfone mudo é quase sempre problema."""
    out = {}
    n = int(SR * segundos)
    for nome in ("mic", "loop"):
        d = disp.get(nome)
        if d is None:
            out[nome] = {"rms": 0.0, "pico": 0.0, "ok": False, "erro": "sem dispositivo"}
            continue
        try:
            with com_na_thread(), d.recorder(samplerate=SR) as r:
                x = _mono(r.record(numframes=n))
            out[nome] = {"rms": round(_rms(x), 5), "pico": round(float(np.max(np.abs(x))), 4),
                         "ok": _rms(x) >= LIMIAR_MUDO}
        except Exception as e:
            out[nome] = {"rms": 0.0, "pico": 0.0, "ok": False, "erro": repr(e)}
    return out


# ── um canal = uma thread que escreve blocos no disco ────────────────────────
class Canal(threading.Thread):
    MAX_FALHAS_SEGUIDAS = 60      # ~1 min tentando reabrir sem conseguir ler um bloco
    RESYNC_S = 10.0               # a cada 10 s confere o canal contra o relógio

    def __init__(self, nome, dispositivo, caminho_pcm, t0, reescolher=None):
        super().__init__(daemon=True, name=f"canal-{nome}")
        self.nome = nome
        self.disp = dispositivo
        self.caminho = caminho_pcm
        self.t0 = t0                      # time.monotonic() do início da sessão
        self.reescolher = reescolher      # função que devolve um dispositivo novo
        self.amostras = 0
        self.nivel = 0.0                  # RMS do último bloco (para a UI)
        self.ultimo_som = time.monotonic()
        self.erros = []
        self.lacunas = []                 # [(início_s, duração_s)] preenchidas com silêncio
        self.trocas = []                  # dispositivos usados depois de uma queda
        self.morto = None                 # motivo, se o canal desistiu
        self._parar = threading.Event()

    def parar(self):
        self._parar.set()

    def _preencher_lacuna(self, f):
        """Se o canal está > 1 s atrás do relógio (dispositivo caiu, descontinuidade do
        WASAPI, deriva do relógio da placa), completa com silêncio: os dois canais
        continuam alinhados e o timestamp das citações não escorrega."""
        esperado = int((time.monotonic() - self.t0) * SR)
        falta = esperado - self.amostras
        if falta > SR:
            self.lacunas.append((round(self.amostras / SR, 1), round(falta / SR, 1)))
            restante = falta
            while restante > 0:
                k = min(restante, SR * 10)
                f.write(b"\x00\x00" * k)
                restante -= k
            self.amostras += falta

    def run(self):
        with com_na_thread():
            self._run()

    def _run(self):
        try:
            f = open(self.caminho, "ab", buffering=0)
        except Exception as e:
            self.morto = f"não abriu {self.caminho.name}: {type(e).__name__}: {e}"
            self.erros.append(self.morto)
            return
        with f:
            ult_sync = ult_resync = time.monotonic()
            seguidas = 0
            while not self._parar.is_set():
                try:
                    with self.disp.recorder(samplerate=SR) as rec:
                        self._preencher_lacuna(f)
                        while not self._parar.is_set():
                            x = _mono(rec.record(numframes=BLOCK))
                            f.write(_pcm16(x))
                            self.amostras += len(x)
                            seguidas = 0
                            self.nivel = _rms(x)
                            agora = time.monotonic()
                            if self.nivel >= LIMIAR_MUDO:
                                self.ultimo_som = agora
                            if agora - ult_resync >= self.RESYNC_S:
                                self._preencher_lacuna(f)
                                ult_resync = agora
                            if agora - ult_sync >= FSYNC_S:
                                os.fsync(f.fileno())
                                ult_sync = agora
                except Exception as e:
                    seguidas += 1
                    self.erros.append(f"{time.strftime('%H:%M:%S')} {type(e).__name__}: {e}")
                    del self.erros[:-50]
                    if seguidas > self.MAX_FALHAS_SEGUIDAS:
                        self.morto = f"desistiu após {seguidas} falhas seguidas: {e}"
                        break
                    self._parar.wait(1.0)
                    if self.reescolher:
                        try:
                            novo = self.reescolher()
                            if novo is not None and novo.name != self.disp.name:
                                self.trocas.append(f"{time.strftime('%H:%M:%S')} {novo.name}")
                                self.disp = novo
                        except Exception:
                            pass
            try:
                os.fsync(f.fileno())
            except Exception:
                pass


class Gravador:
    """Grava os dois canais direto na pasta da sessão.

        g = Gravador(sessao, dispositivos); g.iniciar(); ...; diag = g.parar()
    """

    def __init__(self, sessao, disp):
        self.s = sessao
        self.disp = disp
        self.canais = {}
        self.t0 = None
        self._batedor = None

    def iniciar(self):
        from sessao import Batedor, agora_iso
        self.t0 = time.monotonic()
        manter_acordado(True)
        mic, loop = self.disp.get("mic"), self.disp.get("loop")
        self.s.m["inicio"] = self.s.m.get("inicio") or agora_iso()
        self.s.m["dispositivos"] = {"mic": mic.name if mic else None,
                                    "loop": loop.name if loop else None}
        for a in self.disp.get("avisos") or []:
            self.s.avisar(a)
        self.s.m["estado"] = "gravando"
        self.s.salvar()
        self._batedor = Batedor(self.s).__enter__()
        if mic is not None:
            # na queda, tenta primeiro o MESMO microfone (pelo nome), não o padrão do Windows
            self.canais["mic"] = Canal("mic", mic, self.s.mic_pcm, self.t0,
                                       reescolher=lambda n=mic.name: _escolher_mic(n)[0])
        if loop is not None:
            self.canais["loop"] = Canal("loop", loop, self.s.loop_pcm, self.t0,
                                        reescolher=lambda: _escolher_loop()[0])
        for c in self.canais.values():
            c.start()

    def decorrido(self):
        return time.monotonic() - self.t0 if self.t0 else 0.0

    def niveis(self):
        return {k: c.nivel for k, c in self.canais.items()}

    def mudo_ha(self, nome):
        c = self.canais.get(nome)
        return (time.monotonic() - c.ultimo_som) if c else None

    def parar(self):
        from sessao import agora_iso
        for c in self.canais.values():
            c.parar()
        for c in self.canais.values():
            c.join(timeout=5)
        manter_acordado(False)
        if self._batedor:
            self._batedor.__exit__(None, None, None)
        diag = {}
        for nome, c in self.canais.items():
            diag[nome] = {"segundos": round(c.amostras / SR, 1), "erros": c.erros[-5:],
                          "lacunas": c.lacunas, "trocas": c.trocas, "morto": c.morto}
            if c.morto:
                self.s.avisar(f"o canal {nome} PAROU no meio da gravação: {c.morto}")
            elif c.erros:
                self.s.avisar(f"o canal {nome} caiu {len(c.erros)}x e foi reaberto")
            if c.trocas:
                self.s.avisar(f"o canal {nome} passou a gravar por {c.trocas[-1]}")
                self.s.m["dispositivos"][f"{nome}_depois"] = c.trocas
        self.s.m["fim"] = agora_iso()
        self.s.m["audio"].update({"duracao_s": round(self.s.duracao_s(), 1), "canais": diag})
        self.s.m["estado"] = "gravado"
        self.s.salvar()
        self.s.etapa("captura", "ok", **{"segundos": round(self.s.duracao_s(), 1)})
        return diag


if __name__ == "__main__":
    # Teste rápido: python record.py  → mede 3 s de cada canal e mostra os dispositivos
    d = escolher_dispositivos()
    print("mic :", d["mic"].name if d["mic"] else None)
    print("loop:", d["loop"].name if d["loop"] else None)
    for a in d["avisos"]:
        print("⚠ ", a)
    print(medir_niveis(d))
