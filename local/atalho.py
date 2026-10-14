# -*- coding: utf-8 -*-
"""
Atalho global do "marcar momento" (14/10/2026): funciona com o Meet/Chrome em foco e a janela do
Atas atrás. `RegisterHotKey` do Windows via ctypes, sem dependência nova.

Por que uma thread própria: o WM_HOTKEY de um RegisterHotKey(hWnd=NULL) vai para a fila de
mensagens DA THREAD que registrou. A thread registra, fica num GetMessageW e, no fim, recebe um
WM_QUIT (PostThreadMessageW) e libera o atalho (UnregisterHotKey) ela mesma — UnregisterHotKey de
outra thread não libera um atalho de hWnd NULL.

Padrão: **Ctrl+Alt+M** (config `marcar_atalho`). O Windows entrega o atalho registrado ANTES do
aplicativo em foco: enquanto grava, nenhum programa recebe Ctrl+Alt+M — conferido em 14/10:
  - Google Meet: a ajuda oficial não usa Ctrl+Alt+M (sites de terceiros citam "minimizar vídeo" ou
    "silenciar todos", só para organizador; se existir, simplesmente não dispara durante a gravação);
  - Word: Ctrl+Alt+M = novo comentário (fica indisponível enquanto grava);
  - VS Code: sem atalho padrão em Ctrl+Alt+M; Windows: nenhum; teclados desta máquina (ABNT2 e
    US): AltGr+M não produz caractere.
Se outro programa já tiver registrado o mesmo atalho global, o registro falha e a tela diz isso
(o botão "Marcar" continua valendo).
"""
import ctypes
import ctypes.wintypes as wt
import threading

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
PADRAO = "ctrl+alt+m"
_MODS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}


def ler(texto):
    """"ctrl+alt+m" → (modificadores, tecla virtual). Levanta ValueError."""
    partes = [p.strip().lower() for p in (texto or PADRAO).split("+") if p.strip()]
    if len(partes) < 2:
        raise ValueError(f"atalho inválido: {texto!r} (ex.: ctrl+alt+m)")
    mods = 0
    for p in partes[:-1]:
        if p not in _MODS:
            raise ValueError(f"modificador desconhecido em {texto!r}: {p}")
        mods |= _MODS[p]
    tecla = partes[-1]
    if len(tecla) == 1 and tecla.isalnum():
        vk = ord(tecla.upper())
    elif tecla.startswith("f") and tecla[1:].isdigit() and 1 <= int(tecla[1:]) <= 24:
        vk = 0x6F + int(tecla[1:])
    else:
        raise ValueError(f"tecla não suportada em {texto!r}: {tecla}")
    return mods, vk


def legivel(texto):
    return "+".join(p.capitalize() if len(p) > 1 else p.upper() for p in (texto or PADRAO).split("+"))


class AtalhoGlobal(threading.Thread):
    """a = AtalhoGlobal(callback); a.start(); a.pronto.wait(); a.erro (None = registrado); ...; a.parar()

    `callback()` roda NESTA thread: quem chama deve só anotar o instante e repassar para a thread
    da janela (é o que o app.py faz)."""

    _ID = 0xA7A5

    def __init__(self, callback, atalho=PADRAO):
        super().__init__(daemon=True, name="atalho-marcar")
        self.callback = callback
        self.atalho = atalho or PADRAO
        self.mods, self.vk = ler(self.atalho)
        self.pronto = threading.Event()
        self.erro = None
        self.registrado = False
        self.disparos = 0
        self._tid = None
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._user32.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, wt.UINT, wt.UINT]
        self._user32.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]
        self._user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
        self._user32.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]

    def run(self):
        u = self._user32
        self._tid = self._k32.GetCurrentThreadId()
        msg = wt.MSG()
        # força a criação da fila de mensagens da thread antes de avisar que está pronta:
        # sem fila, um PostThreadMessageW (parar) que chegue cedo se perde
        u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
        if not u.RegisterHotKey(None, self._ID, self.mods | MOD_NOREPEAT, self.vk):
            err = ctypes.get_last_error()
            self.erro = (f"{legivel(self.atalho)} já está em uso por outro programa: use o botão Marcar"
                         if err == 1409 else f"não consegui registrar {legivel(self.atalho)} (erro {err})")
            self.pronto.set()
            return
        self.registrado = True
        self.pronto.set()
        try:
            while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam == self._ID:
                    self.disparos += 1
                    try:
                        self.callback()
                    except Exception:
                        pass
        finally:
            u.UnregisterHotKey(None, self._ID)
            self.registrado = False

    def parar(self, timeout=2):
        if self._tid is not None and self.is_alive():
            self._user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
        self.join(timeout)
        return not self.is_alive()


def iniciar(callback, atalho=PADRAO, espera_s=2):
    """Sobe a thread e espera o registro. Devolve o AtalhoGlobal (veja `.erro`)."""
    a = AtalhoGlobal(callback, atalho)
    a.start()
    a.pronto.wait(espera_s)
    return a
