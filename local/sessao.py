# -*- coding: utf-8 -*-
"""
Sessão = uma reunião, do primeiro bloco de áudio ao PDF, numa pasta só.

    atas-salvas/2026-09-30_1402_alinhamento-po/
        sessao.json        o manifesto: contexto (R6), estado e o resultado de cada etapa
        .batida            tocado a cada 5 s enquanto grava — é assim que se sabe que o
                           gravador morreu (a pasta fica "gravando" e a batida para)
        mic.pcm            PCM 16 bits mono 16 kHz, escrito DURANTE a captura
        loop.pcm           idem, do loopback
        transcricao.json   segmentos {speaker, start, end, text}
        ata.json           a ata canônica (schema atas/ata@1) — ver estruturar.py
        ata.md / .html / .pdf         renderizações internas
        entregavel.html / .pdf        só em reunião de cliente
        audio/mic.opus, loop.opus     o áudio compactado, apagado após N dias

Por que PCM cru e não WAV: o `wave` escreve o cabeçalho com tamanho zero e só o
corrige no close(). Se o processo morre no meio, o WAV diz que tem 0 amostras. O
PCM cru não tem cabeçalho para corromper: o que chegou ao disco é o que existe.
Foi exatamente o que perdeu a conversa com o Mauro em ~20/09/2026 — o áudio
vivia na memória e só ia para o disco no fim.

Este módulo não importa nada pesado: o CLI e a UI usam para listar sem carregar
o Whisper.
"""
import datetime as _dt
import json
import os
import pathlib
import re
import time
import unicodedata

BASE = pathlib.Path(__file__).resolve().parent.parent
SALVAS = BASE / "atas-salvas"
SR = 16000

SCHEMA_SESSAO = "atas/sessao@1"

# O tipo decide marca, destino dos dados e roteamento (R6). A ordem é a da UI.
TIPOS = {
    "cliente": "Cliente",
    "parresia": "Parresia (interna)",
    "carreira": "Carreira",
    "pessoal": "Pessoal / estudo",
}
# Só reunião de cliente sai da máquina (decisão 1 de 30/09/2026).
TIPOS_PUBLICAVEIS = {"cliente"}

BATIDA_S = 5          # intervalo da batida enquanto grava
ORFA_APOS_S = 45      # batida mais velha que isso = gravador morto

ETAPAS = ["captura", "transcricao", "falantes", "estrutura", "render", "pdf",
          "publicacao", "raio_x", "audio"]


def agora_iso():
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def slug(texto, maximo=48):
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return (t[:maximo].rstrip("-")) or "reuniao"


def novo_id(titulo, quando=None):
    quando = quando or _dt.datetime.now()
    return f"{quando:%Y-%m-%d_%H%M}_{slug(titulo)}"


import threading as _threading

_TRAVA_ESCRITA = _threading.Lock()


def _escrever_atomico(caminho, texto):
    """Escreve num temporário e troca: um crash no meio nunca deixa JSON pela metade.

    No Windows o `os.replace` falha com PermissionError (WinError 5) se outro processo
    estiver lendo o destino naquele instante — a janela listando, o /ata, o Defender,
    o indexador. Daí o temporário com nome único e as novas tentativas."""
    tmp = caminho.with_name(f"{caminho.name}.{os.getpid()}.{_threading.get_ident()}.tmp")
    with _TRAVA_ESCRITA:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(texto)
            f.flush()
            os.fsync(f.fileno())
        for n in range(20):
            try:
                os.replace(tmp, caminho)
                return
            except PermissionError:
                time.sleep(0.05 * (n + 1))
        os.replace(tmp, caminho)


def escrever_json(caminho, dado):
    _escrever_atomico(pathlib.Path(caminho), json.dumps(dado, ensure_ascii=False, indent=2))


def ler_json(caminho, padrao=None):
    p = pathlib.Path(caminho)
    if not p.exists():
        return padrao
    return json.loads(p.read_text(encoding="utf-8"))


class Sessao:
    def __init__(self, pasta, manifesto):
        self.pasta = pathlib.Path(pasta)
        self.m = manifesto

    # ── criação e leitura ──────────────────────────────────────────────────
    @classmethod
    def criar(cls, titulo, tipo, projeto="", participantes=None, raiz=None):
        if tipo not in TIPOS:
            raise ValueError(f"tipo inválido: {tipo!r} (use {', '.join(TIPOS)})")
        raiz = pathlib.Path(raiz) if raiz else SALVAS
        raiz.mkdir(parents=True, exist_ok=True)
        titulo = (titulo or "").strip() or f"Reunião {time.strftime('%d/%m/%Y %H:%M')}"
        base_id = novo_id(titulo)
        sid, n = base_id, 2
        while (raiz / sid).exists():          # duas reuniões no mesmo minuto
            sid, n = f"{base_id}-{n}", n + 1
        pasta = raiz / sid
        pasta.mkdir()
        m = {
            "schema": SCHEMA_SESSAO,
            "id": sid,
            "titulo": titulo,
            "tipo": tipo,
            "projeto": (projeto or "").strip(),
            "participantes": [p.strip() for p in (participantes or []) if p and p.strip()],
            "criado": agora_iso(),
            "inicio": None,
            "fim": None,
            "estado": "preparando",
            "dispositivos": {},
            "audio": {"sr": SR},
            "etapas": {},
            "avisos": [],
        }
        s = cls(pasta, m)
        s.salvar()
        return s

    @classmethod
    def abrir(cls, pasta_ou_id, raiz=None):
        p = pathlib.Path(pasta_ou_id)
        if not p.is_absolute() and not p.exists():
            p = (pathlib.Path(raiz) if raiz else SALVAS) / str(pasta_ou_id)
        m = ler_json(p / "sessao.json")
        if m is None:
            raise FileNotFoundError(f"não é uma sessão do Atas: {p}")
        return cls(p, m)

    def salvar(self):
        escrever_json(self.pasta / "sessao.json", self.m)

    # ── atalhos ───────────────────────────────────────────────────────────
    @property
    def id(self):
        return self.m["id"]

    @property
    def tipo(self):
        return self.m.get("tipo") or "pessoal"

    def caminho(self, nome):
        return self.pasta / nome

    @property
    def mic_pcm(self):
        return self.pasta / "mic.pcm"

    @property
    def loop_pcm(self):
        return self.pasta / "loop.pcm"

    @property
    def audio_dir(self):
        return self.pasta / "audio"

    def participantes_remotos(self):
        return list(self.m.get("participantes") or [])

    # ── estado e etapas ───────────────────────────────────────────────────
    def estado(self, novo):
        self.m["estado"] = novo
        self.salvar()

    def etapa(self, nome, status, detalhe=None, **extra):
        """status: ok | falhou | pulada | pendente. Nada de falha silenciosa: toda
        etapa que roda deixa aqui o que aconteceu, e a UI mostra esta lista."""
        reg = {"status": status, "em": agora_iso()}
        if detalhe:
            reg["detalhe"] = str(detalhe)[:2000]
        reg.update(extra)
        self.m.setdefault("etapas", {})[nome] = reg
        self.salvar()

    def status_etapa(self, nome):
        return (self.m.get("etapas") or {}).get(nome, {}).get("status")

    def avisar(self, texto):
        self.m.setdefault("avisos", [])
        if texto not in self.m["avisos"]:
            self.m["avisos"].append(texto)
        self.salvar()

    # ── batida (detecção de gravador morto) ─────────────────────────────────
    def bater(self):
        p = self.pasta / ".batida"
        p.write_text(str(time.time()), encoding="ascii")

    def segundos_desde_batida(self):
        p = self.pasta / ".batida"
        if not p.exists():
            return None
        return time.time() - p.stat().st_mtime

    def orfa(self):
        """Gravação ou processamento que não terminou e cujo processo morreu."""
        est = self.m.get("estado")
        if est == "gravando":
            idade = self.segundos_desde_batida()
            return idade is None or idade > ORFA_APOS_S
        if est in ("gravado", "processando"):
            idade = self.segundos_desde_batida()
            return idade is None or idade > ORFA_APOS_S
        return False

    # ── áudio ──────────────────────────────────────────────────────────────
    def duracao_s(self):
        """Duração pelo tamanho dos PCM (o que realmente chegou ao disco)."""
        dur = 0.0
        for p in (self.mic_pcm, self.loop_pcm):
            if p.exists():
                dur = max(dur, p.stat().st_size / 2 / SR)
        if not dur:
            dur = float((self.m.get("audio") or {}).get("duracao_s") or 0)
        return dur

    def resumo_curto(self):
        ini = self.m.get("inicio") or self.m.get("criado") or ""
        try:
            quando = _dt.datetime.fromisoformat(ini).strftime("%d/%m %H:%M")
        except ValueError:
            quando = ini[:16]
        return f"{quando} · {round(self.duracao_s() / 60)} min · {TIPOS.get(self.tipo, self.tipo)}"


class Batedor:
    """Toca a .batida da sessão a cada BATIDA_S segundos enquanto o bloco roda.

    Serve à gravação e ao processamento: se qualquer dos dois morrer (crash,
    PC travado, janela fechada), a batida para e a próxima abertura do Atas
    enxerga a sessão como órfã e oferece retomar."""

    def __init__(self, sessao):
        import threading
        self.s = sessao
        self._parar = threading.Event()
        self._t = threading.Thread(target=self._rodar, daemon=True)

    def _rodar(self):
        while not self._parar.is_set():
            try:
                self.s.bater()
            except Exception:
                pass
            self._parar.wait(BATIDA_S)

    def __enter__(self):
        self.s.bater()
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._parar.set()
        self._t.join(timeout=2)
        return False


def listar(raiz=None):
    raiz = pathlib.Path(raiz) if raiz else SALVAS
    if not raiz.exists():
        return []
    out = []
    for p in sorted(raiz.iterdir()):
        if p.is_dir() and (p / "sessao.json").exists():
            try:
                out.append(Sessao.abrir(p))
            except Exception:
                continue
    out.sort(key=lambda s: s.m.get("inicio") or s.m.get("criado") or "")
    return out


def orfas(raiz=None):
    return [s for s in listar(raiz) if s.orfa()]


def a_retomar(raiz=None):
    """Órfãs + as que terminaram com falha numa etapa que a ata precisa. É o que a janela
    oferece ao abrir e o que `atas.py retomar` processa."""
    essenciais = {"transcricao", "estrutura", "render", "pdf"}
    out = []
    for s in listar(raiz):
        est = s.m.get("estado")
        falhou = [k for k, v in (s.m.get("etapas") or {}).items() if v.get("status") == "falhou"]
        if s.orfa() or est == "falhou" or (est == "pronto_com_falhas" and set(falhou) & essenciais):
            out.append(s)
    return out


def ultima(raiz=None):
    todas = [s for s in listar(raiz) if s.m.get("estado") not in ("preparando", "descartada")]
    return todas[-1] if todas else None
