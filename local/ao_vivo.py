# -*- coding: utf-8 -*-
"""
Atas ao vivo (R9) — MVP: transcrição incremental num arquivo que o Claude lê.

Enquanto grava, a cada `ao_vivo_janela_s` segundos esta thread pega o áudio NOVO
dos dois PCM (que já estão sendo escritos no disco pelo gravador), transcreve com
um modelo pequeno e acrescenta as falas em `ao-vivo.md` na pasta da sessão:

    [12:34] Você: …
    [12:41] Participante: …

É o "workaround que já existia" da nota atas-ao-vivo do Sinapse: o Pedro
conversava com o Claude no chat durante a reunião. Agora o Claude tem o que está
sendo dito — `python atas.py ao-vivo` devolve o caminho do arquivo.

Custo: só roda na GPU. Na CPU a transcrição disputaria processador com a própria
chamada, então sem GPU fica desligado e a tela diz por quê. Nada disso substitui a
transcrição final, que é feita de novo, inteira, com o modelo grande e diarização.
"""
import threading
import time

import numpy as np

SR = 16000
_GPU = {}


def gpu_disponivel():
    """Há placa CUDA? (~0,5 s na primeira vez, por causa do import; depois vem do cache). É o que
    decide se a janela oferece o intervencionista: sem GPU o ao vivo não roda (§12)."""
    if "v" not in _GPU:
        try:
            import ctranslate2
            _GPU["v"] = ctranslate2.get_cuda_device_count() > 0
        except Exception:
            _GPU["v"] = False
    return _GPU["v"]


class AoVivo(threading.Thread):
    def __init__(self, sessao, cfg, log=print):
        super().__init__(daemon=True, name="ao-vivo")
        self.s = sessao
        self.cfg = cfg
        self.log = log
        self.janela = int(cfg.get("ao_vivo_janela_s", 30))
        self.offsets = {"mic": 0, "loop": 0}   # em amostras
        self._parar = threading.Event()
        self.modelo = None
        self.erro = None
        self.falas = 0
        self._marcas = []                       # instantes (s) do Ctrl+Alt+M ainda não escritos
        self._trava = threading.Lock()

    def marcar(self, t):
        """Marca de momento (Ctrl+Alt+M, 22/10/2026): vira `[mm:ss] ★ MARCA` no ao-vivo.md, no PONTO
        CERTO — junto do lote em que o áudio daquele instante foi transcrito, ordenada com as falas.
        Escrever na hora poria a marca antes de falas que a precederam (o áudio delas ainda não foi
        transcrito). Chamado da thread do Tk."""
        with self._trava:
            self._marcas.append(float(t))

    def _marcas_ate(self, coberto):
        with self._trava:
            prontas = [t for t in self._marcas if t <= coberto]
            self._marcas = [t for t in self._marcas if t > coberto]
        return prontas

    def parar(self):
        self._parar.set()

    def _novo(self, nome, pcm, ate_amostra):
        if not pcm.exists():
            return None, 0
        ini = self.offsets[nome]
        n = min(pcm.stat().st_size // 2, ate_amostra) - ini
        if n < SR * 2:
            return None, ini
        with open(pcm, "rb") as f:
            f.seek(ini * 2)
            raw = f.read(n * 2)
        self.offsets[nome] = ini + len(raw) // 2
        return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0, ini

    def _ciclo(self, final=False):
        import ata as _ata
        # não lê o último 1 s, que pode estar sendo escrito (exceto no fechamento)
        limite = 10 ** 12 if final else None
        linhas = []
        for nome, pcm, rotulo in (("mic", self.s.mic_pcm, "Você"),
                                  ("loop", self.s.loop_pcm, "Participante")):
            if not pcm.exists():
                continue
            ate = limite or max(0, pcm.stat().st_size // 2 - SR)
            x, ini = self._novo(nome, pcm, ate)
            if x is None:
                continue
            segs, _ = self.modelo.transcribe(x, language="pt", vad_filter=True, beam_size=1,
                                             condition_on_previous_text=False)
            for sg in segs:
                t = sg.text.strip()
                if t:
                    linhas.append((ini / SR + sg.start, rotulo, t))
        # as marcas cujo instante os canais já cobriram entram neste lote, na ordem do tempo
        canais = [n for n, pcm in (("mic", self.s.mic_pcm), ("loop", self.s.loop_pcm)) if pcm.exists()]
        coberto = float("inf") if final else (min(self.offsets[n] for n in canais) / SR if canais else 0.0)
        marcas = [(t0, "★", None) for t0 in self._marcas_ate(coberto)]
        if linhas or marcas:
            n_falas = len(linhas)
            linhas = sorted(linhas + marcas, key=lambda x: (x[0], x[1] != "★"))
            with open(self.s.caminho("ao-vivo.md"), "a", encoding="utf-8") as f:
                for t0, rot, txt in linhas:
                    if rot == "★":
                        f.write(f"[{_ata.fmt_t(t0)}] ★ MARCA\n")
                    else:
                        f.write(f"[{_ata.fmt_t(t0)}] {rot}: {txt}\n")
            self.falas += n_falas

    def run(self):
        import transcribe
        try:
            self.modelo, info = transcribe.carregar_modelo("small", "cuda", log=lambda *_: None)
        except Exception as e:
            self.erro = f"ao vivo desligado: sem GPU ({e})"[:300]
            self.s.avisar(self.erro)
            return
        cab = self.s.caminho("ao-vivo.md")
        if not cab.exists():
            cab.write_text(f"# Ao vivo — {self.s.m.get('titulo')}\n\n"
                           "_Transcrição preliminar, sem separação de participantes. A ata "
                           "final é refeita do zero ao terminar._\n\n", encoding="utf-8")
        while not self._parar.wait(self.janela):
            try:
                self._ciclo()
            except Exception as e:
                self.erro = f"{type(e).__name__}: {e}"[:300]
                time.sleep(self.janela)
        try:
            self._ciclo(final=True)
        except Exception:
            pass
