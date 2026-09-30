# -*- coding: utf-8 -*-
"""
Atas — a janela. Dois cliques em gravar.bat (ou no atalho "Atas" da Área de Trabalho).

    Nova reunião  →  Checagem do áudio  →  Gravando  →  Gerando a ata  →  Pronto

Desenho (regra do Pedro: pouca informação, muito respiro): cada tela mostra só o
que se decide nela. O resto fica em "Mais opções", com um resumo de uma linha do
que está escolhido. Cor só onde comunica estado: vermelho = gravando ou problema.

Garantias que a janela dá, além das do gravador:
  - ao abrir, avisa de gravação interrompida e oferece processar o que sobrou;
  - fechar a janela durante a gravação pergunta antes, e nunca descarta áudio;
  - no fim, mostra TODAS as etapas com ok / falhou / pulada e o motivo;
  - erro inesperado aparece numa caixa e fica em local/atas.log.
"""
import ctypes
import math
import pathlib
import queue
import sys
import threading
import time
import tkinter as tk
import traceback
from tkinter import messagebox, ttk

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import config as _config  # noqa: E402
import sessao as _sessao  # noqa: E402
from sessao import TIPOS, Sessao  # noqa: E402

LOG = pathlib.Path(__file__).parent / "atas.log"
VERMELHO = "#C0392B"
CINZA = "#6E6E69"
VERDE = "#3A5A50"
ROTULO_ETAPA = {"transcricao": "Transcrição", "falantes": "Quem falou", "estrutura": "Ata (Claude)",
                "render": "Página", "pdf": "PDF", "publicacao": "Publicação", "raio_x": "Raio-X da fala",
                "audio": "Áudio guardado"}


def _log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass


def _console(mostrar):
    try:
        h = ctypes.windll.kernel32.GetConsoleWindow()
        if h:
            ctypes.windll.user32.ShowWindow(h, 9 if mostrar else 6)   # 9 restaura, 6 minimiza
    except Exception:
        pass


def _nivel_pct(rms):
    db = 20 * math.log10(max(rms, 1e-9))
    return max(0, min(100, (db + 60) * 2))          # -60 dB → 0 ; -10 dB → 100


ESCALA = 1.0     # definida ao abrir a janela: 1.0 = tela a 100%


def _p(n):
    """Pixels de desenho → pixels da tela. Espaço é o que dá respiro; sem escalar, 28 px
    numa tela a 250% viram nada."""
    return int(round(n * ESCALA))


def _fmt_tempo(seg):
    seg = int(seg)
    return f"{seg // 3600:02d}:{seg % 3600 // 60:02d}:{seg % 60:02d}"


def _dpi_nitido():
    """Sem isto o Windows amplia a janela do Tk como bitmap e o texto fica borrado
    na tela de alta densidade do XPS."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class App(tk.Tk):
    def __init__(self):
        _dpi_nitido()
        super().__init__()
        self.cfg = _config.carregar()
        self.title("Atas")
        global ESCALA
        ESCALA = self.winfo_fpixels("1i") / 96.0
        self.geometry(f"{_p(500)}x{_p(660)}")
        self.minsize(_p(460), _p(580))
        self.configure(padx=_p(32), pady=_p(28))
        self.report_callback_exception = self._erro_tk
        self.protocol("WM_DELETE_WINDOW", self._fechar)
        st = ttk.Style(self)
        try:
            st.theme_use("vista")
        except tk.TclError:
            pass
        base = "Segoe UI"
        st.configure("T.TLabel", font=(base, 18, "bold"))
        st.configure("Sub.TLabel", font=(base, 10), foreground=CINZA)
        st.configure("Campo.TLabel", font=(base, 10, "bold"))
        st.configure("Grande.TLabel", font=(base, 30, "bold"))
        st.configure("Rec.TLabel", font=(base, 14, "bold"), foreground=VERMELHO)
        st.configure("Alerta.TLabel", font=(base, 10), foreground=VERMELHO)
        st.configure("Ok.TLabel", font=(base, 10), foreground=VERDE)
        st.configure("Primario.TButton", font=(base, 11, "bold"), padding=(_p(16), _p(10)))
        st.configure("TButton", font=(base, 10), padding=(_p(10), _p(6)))
        st.configure("Link.TButton", font=(base, 9), padding=(0, 2))
        self.fonte = base
        self.q = queue.Queue()
        self.s = None
        self.g = None
        self.av = None
        self.disp = None
        self.processando = False
        self.dispensadas = set()
        self.tela = None
        self.after(100, self._drenar)
        self.inicio()
        self.after(800, lambda: _console(False))

    # ── utilidades ──────────────────────────────────────────────────────────
    def _limpar(self):
        if self.tela is not None:
            self.tela.destroy()
        self.tela = ttk.Frame(self)
        self.tela.pack(fill="both", expand=True)
        return self.tela

    def _erro_tk(self, exc, val, tb):
        txt = "".join(traceback.format_exception(exc, val, tb))
        _log(txt)
        _console(True)
        messagebox.showerror("Atas — erro", f"{val}\n\nDetalhes em {LOG}")

    def _drenar(self):
        try:
            while True:
                fn = self.q.get_nowait()
                fn()
        except queue.Empty:
            pass
        self.after(100, self._drenar)

    def _fechar(self):
        if self.g is not None:
            if messagebox.askyesno("Atas", "Parar a gravação e gerar a ata?\n\n"
                                   "(O áudio até aqui já está salvo no disco.)"):
                self.parar()
            return
        if self.processando:
            if not messagebox.askyesno("Atas", "A ata ainda está sendo gerada. Fechar mesmo "
                                       "assim?\n\nNada se perde: na próxima abertura o Atas "
                                       "oferece retomar."):
                return
        self.destroy()

    # ── tela 1: nova reunião ───────────────────────────────────────────────
    def inicio(self):
        f = self._limpar()
        self.title("Atas")
        pend = [x for x in _sessao.a_retomar() if x.id not in self.dispensadas]
        if pend:
            o = pend[-1]
            box = ttk.Frame(f)
            box.pack(fill="x", pady=(_p(0), _p(22)))
            titulo_aviso = ("Gravação interrompida" if o.orfa() else "Reunião com etapa falhada")
            ttk.Label(box, text=titulo_aviso, style="Alerta.TLabel").pack(anchor="w")
            ttk.Label(box, text=f"{o.m.get('titulo')} · {o.resumo_curto()}",
                      style="Sub.TLabel", wraplength=_p(400)).pack(anchor="w")
            linha_b = ttk.Frame(box)
            linha_b.pack(anchor="w", pady=(_p(6), _p(0)))
            ttk.Button(linha_b, text="Gerar a ata agora",
                       command=lambda: self.retomar(o)).pack(side="left")
            ttk.Button(linha_b, text="Agora não", style="Link.TButton",
                       command=lambda: (self.dispensadas.add(o.id), self.inicio())
                       ).pack(side="left", padx=(_p(12), 0))

        ttk.Label(f, text="Nova reunião", style="T.TLabel").pack(anchor="w", pady=(_p(0), _p(18)))

        def campo(rotulo, dica=None):
            ttk.Label(f, text=rotulo, style="Campo.TLabel").pack(anchor="w")
            if dica:
                ttk.Label(f, text=dica, style="Sub.TLabel").pack(anchor="w")

        campo("Título")
        self.v_titulo = tk.StringVar()
        e = ttk.Entry(f, textvariable=self.v_titulo, font=(self.fonte, 11))
        e.pack(fill="x", pady=(_p(6), _p(22)))
        e.focus_set()

        campo("Tipo")
        # sem valor padrão DE PROPÓSITO: herdar o tipo da reunião anterior fazia uma reunião
        # da Parresia gravada logo depois de uma de cliente ser tratada como cliente
        self.v_tipo = tk.StringVar(value="")
        linha = ttk.Frame(f)
        linha.pack(fill="x", pady=(_p(6), _p(22)))
        for k, rot in TIPOS.items():
            ttk.Radiobutton(linha, text=rot.split(" (")[0], value=k, variable=self.v_tipo,
                            command=lambda: self.l_tipo_falta.configure(text="")
                            ).pack(side="left", padx=(_p(0), _p(14)))
        self.l_tipo_falta = ttk.Label(f, text="", style="Alerta.TLabel")
        self.l_tipo_falta.pack(anchor="w")

        campo("Projeto")
        todas = _sessao.listar()
        projetos = sorted({s.m.get("projeto") for s in todas if s.m.get("projeto")})
        self.v_projeto = tk.StringVar()
        cb = ttk.Combobox(f, textvariable=self.v_projeto, values=projetos, font=(self.fonte, 11))
        cb.pack(fill="x", pady=(_p(6), _p(22)))

        campo("Quem vai falar do outro lado", "separe por vírgula — ajuda a separar as vozes")
        self.v_part = tk.StringVar()
        ttk.Entry(f, textvariable=self.v_part, font=(self.fonte, 11)).pack(fill="x", pady=(_p(4), _p(6)))

        def preencher(_evt=None):
            if self.v_part.get().strip():
                return
            mesmo = [s for s in todas if s.m.get("projeto") == self.v_projeto.get()
                     and s.m.get("participantes")]
            if mesmo:
                self.v_part.set(", ".join(mesmo[-1].m["participantes"]))
                if not self.v_tipo.get():
                    self.v_tipo.set(mesmo[-1].tipo)
        cb.bind("<<ComboboxSelected>>", preencher)

        # mais opções (recolhido, com resumo)
        self.v_ao_vivo = tk.BooleanVar(value=bool(self.cfg.get("ao_vivo")))
        self.v_claude = tk.BooleanVar(value=bool(self.cfg.get("estruturar", True)))
        mais = ttk.Frame(f)
        resumo = ttk.Label(f, style="Sub.TLabel")

        def atualizar_resumo(*_):
            resumo.configure(text=("Ata pelo Claude" if self.v_claude.get() else "Sem Claude")
                             + " · " + ("ao vivo ligado" if self.v_ao_vivo.get() else
                                        "ao vivo desligado"))
        aberto = {"v": False}

        def alternar():
            aberto["v"] = not aberto["v"]
            if aberto["v"]:
                mais.pack(fill="x", after=botao_mais, pady=(_p(4), _p(0)))
            else:
                mais.pack_forget()
        botao_mais = ttk.Button(f, text="Mais opções", style="Link.TButton", command=alternar)
        botao_mais.pack(anchor="w", pady=(_p(12), _p(0)))
        resumo.pack(anchor="w")
        ttk.Checkbutton(mais, text="Gerar a ata com o Claude ao terminar",
                        variable=self.v_claude, command=atualizar_resumo).pack(anchor="w")
        ttk.Checkbutton(mais, text="Transcrição ao vivo (usa a GPU; o Claude lê durante a reunião)",
                        variable=self.v_ao_vivo, command=atualizar_resumo).pack(anchor="w")
        atualizar_resumo()

        rod = ttk.Frame(f)
        rod.pack(side="bottom", fill="x")
        ttk.Label(rod, text="Avise que está gravando.", style="Sub.TLabel").pack(anchor="w",
                                                                                pady=(_p(0), _p(10)))
        ttk.Button(rod, text="Testar o áudio", style="Primario.TButton",
                   command=self.checar).pack(fill="x")
        self.bind("<Return>", lambda _e: self.checar())

    # ── tela 2: checagem ───────────────────────────────────────────────────
    def checar(self):
        if self.v_tipo.get() not in TIPOS:
            self.l_tipo_falta.configure(text="Escolha o tipo: ele decide para onde a ata vai.")
            return
        self.unbind("<Return>")
        part = [p.strip() for p in self.v_part.get().split(",") if p.strip()]
        self.ctx = {"titulo": self.v_titulo.get().strip(), "tipo": self.v_tipo.get(),
                    "projeto": self.v_projeto.get().strip(), "participantes": part}
        self.cfg["estruturar"] = self.v_claude.get()
        self.cfg["ao_vivo"] = self.v_ao_vivo.get()
        f = self._limpar()
        ttk.Label(f, text="Checando o áudio", style="T.TLabel").pack(anchor="w", pady=(_p(0), _p(6)))
        ttk.Label(f, text="3 segundos de cada lado…", style="Sub.TLabel").pack(anchor="w")
        corpo = ttk.Frame(f)
        corpo.pack(fill="x", pady=_p(24))

        def medir():
            import record
            try:
                disp = record.escolher_dispositivos(self.cfg.get("microfone"))
                niv = record.medir_niveis(disp)
                self.q.put(lambda: self._resultado_checagem(corpo, disp, niv))
            except Exception as e:
                msg = str(e)
                self.q.put(lambda: self._falha_checagem(corpo, msg))
        threading.Thread(target=medir, daemon=True).start()

    def _falha_checagem(self, corpo, msg):
        ttk.Label(corpo, text=msg, style="Alerta.TLabel", wraplength=_p(400)).pack(anchor="w")
        ttk.Button(self.tela, text="Voltar", command=self.inicio).pack(side="bottom", fill="x")

    def _resultado_checagem(self, corpo, disp, niv):
        self.disp = disp

        def linha(nome, dispositivo, ok, txt_ok, txt_ruim, grave):
            ttk.Label(corpo, text=nome, style="Campo.TLabel").pack(anchor="w")
            ttk.Label(corpo, text=dispositivo or "nenhum", style="Sub.TLabel").pack(anchor="w")
            ttk.Label(corpo, text=txt_ok if ok else txt_ruim,
                      style="Ok.TLabel" if ok else ("Alerta.TLabel" if grave else "Sub.TLabel"),
                      wraplength=_p(400)).pack(anchor="w", pady=(_p(2), _p(16)))
        linha("Seu microfone", disp["mic"].name if disp["mic"] else None, niv["mic"]["ok"],
              "com som", "mudo — confira o microfone antes de começar", True)
        linha("A chamada", disp["loop"].name if disp["loop"] else None, niv["loop"]["ok"],
              "com som", "em silêncio — normal se a chamada ainda não começou. Confira se o "
              "som dela sai por este dispositivo.", disp["loop"] is None)
        for av in disp["avisos"]:
            ttk.Label(corpo, text=av, style="Alerta.TLabel", wraplength=_p(400)).pack(anchor="w")
        rod = ttk.Frame(self.tela)
        rod.pack(side="bottom", fill="x")
        ttk.Button(rod, text="Gravar", style="Primario.TButton", command=self.gravar).pack(fill="x")
        ttk.Button(rod, text="Voltar", command=self.inicio).pack(fill="x", pady=(_p(8), _p(0)))
        self.bind("<Return>", lambda _e: self.gravar())

    # ── tela 3: gravando ───────────────────────────────────────────────────
    def gravar(self):
        import record
        self.unbind("<Return>")
        c = self.ctx
        self.s = Sessao.criar(c["titulo"], c["tipo"], c["projeto"], c["participantes"])
        self.g = record.Gravador(self.s, self.disp)
        self.g.iniciar()
        _log(f"gravando {self.s.id}")
        if self.cfg.get("ao_vivo"):
            import ao_vivo
            self.av = ao_vivo.AoVivo(self.s, self.cfg)
            self.av.start()
        f = self._limpar()
        ttk.Label(f, text="● Gravando", style="Rec.TLabel").pack(anchor="w")
        ttk.Label(f, text=self.s.m["titulo"], style="Sub.TLabel", wraplength=_p(400)).pack(anchor="w")
        self.l_tempo = ttk.Label(f, text="00:00:00", style="Grande.TLabel")
        self.l_tempo.pack(anchor="w", pady=(_p(18), _p(22)))
        self.barras = {}
        for nome, rot in (("mic", "Você"), ("loop", "Chamada")):
            if nome not in self.g.canais:
                continue
            ttk.Label(f, text=rot, style="Sub.TLabel").pack(anchor="w")
            b = ttk.Progressbar(f, maximum=100, length=_p(400))
            b.pack(fill="x", pady=(_p(2), _p(12)))
            self.barras[nome] = b
        self.l_alerta = ttk.Label(f, text="", style="Alerta.TLabel", wraplength=_p(400))
        self.l_alerta.pack(anchor="w", pady=(_p(6), _p(0)))
        self.v_topo = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="Manter esta janela na frente", variable=self.v_topo,
                        command=lambda: self.attributes("-topmost", self.v_topo.get())
                        ).pack(anchor="w", pady=(_p(18), _p(0)))
        ttk.Button(f, text="Parar e gerar a ata", style="Primario.TButton",
                   command=self.parar).pack(side="bottom", fill="x")
        self._tique()

    def _tique(self):
        if self.g is None:
            return
        dec = self.g.decorrido()
        self.l_tempo.configure(text=_fmt_tempo(dec))
        self.title(f"● {_fmt_tempo(dec)} — Atas")
        for k, b in self.barras.items():
            b["value"] = _nivel_pct(self.g.niveis().get(k, 0))
        alertas = []
        mic = self.g.mudo_ha("mic")
        if mic is not None and mic > 60:
            alertas.append(f"Seu microfone está mudo há {int(mic // 60)} min.")
        loop = self.g.mudo_ha("loop")
        if loop is not None and loop > 180 and dec > 180:
            alertas.append(f"Não chega som da chamada há {int(loop // 60)} min — confira a saída "
                           "de áudio do Windows.")
        for c in self.g.canais.values():
            if c.morto or not c.is_alive():
                alertas.append(f"O canal {c.nome} parou: {c.morto or 'motivo desconhecido'}")
            elif c.trocas:
                alertas.append(f"O canal {c.nome} caiu e voltou por {c.trocas[-1][9:]}")
        if self.av is not None and self.av.erro:
            alertas.append(self.av.erro)
        self.l_alerta.configure(text="\n".join(alertas))
        self.after(250, self._tique)

    def parar(self):
        g, self.g = self.g, None
        if g is None:
            return
        if self.av is not None:
            self.av.parar()
        g.parar()
        _log(f"parou {self.s.id} ({self.s.duracao_s():.0f}s)")
        self.attributes("-topmost", False)
        self.processar(self.s)

    # ── tela 4: gerando a ata ──────────────────────────────────────────────
    def retomar(self, s):
        if s.m.get("estado") == "gravando":
            s.m["audio"]["duracao_s"] = round(s.duracao_s(), 1)
            s.avisar("gravação interrompida (o processo parou sem encerrar); áudio recuperado "
                     "até o último bloco gravado")
            s.etapa("captura", "ok", f"recuperada após interrupção · {s.duracao_s():.0f}s")
            s.estado("gravado")
        self.processar(s)

    def processar(self, s):
        self.s = s
        self.processando = True
        f = self._limpar()
        self.title("Gerando a ata — Atas")
        ttk.Label(f, text="Gerando a ata", style="T.TLabel").pack(anchor="w")
        ttk.Label(f, text=f"{s.m.get('titulo')} · {round(s.duracao_s() / 60)} min",
                  style="Sub.TLabel", wraplength=_p(400)).pack(anchor="w", pady=(_p(0), _p(18)))
        self.l_msg = ttk.Label(f, text="Começando…", style="Sub.TLabel", wraplength=_p(400))
        self.l_msg.pack(anchor="w")
        barra = ttk.Progressbar(f, mode="indeterminate", length=_p(400))
        barra.pack(fill="x", pady=(_p(10), _p(0)))
        barra.start(12)

        def log(msg):
            _log(msg)
            m = str(msg).strip()
            self.q.put(lambda: self.l_msg.configure(text=m))

        def rodar():
            try:
                import pipeline
                pipeline.processar(s, self.cfg, log=log)
            except Exception as e:
                _log(traceback.format_exc())
                try:
                    s.avisar(f"erro no processamento: {e} — ver local/atas.log")
                except Exception:
                    pass
            finally:
                self.q.put(lambda: self.pronto(s))
        threading.Thread(target=rodar, daemon=True).start()

    # ── tela 5: pronto ─────────────────────────────────────────────────────
    def pronto(self, s):
        self.processando = False
        s = Sessao.abrir(s.pasta)
        f = self._limpar()
        falhas = [k for k, v in (s.m.get("etapas") or {}).items() if v.get("status") == "falhou"]
        self.title("Pronto — Atas")
        ttk.Label(f, text="Ata pronta" if not falhas else "Ata gerada, com falhas",
                  style="T.TLabel").pack(anchor="w")
        ttk.Label(f, text=s.m.get("titulo"), style="Sub.TLabel", wraplength=_p(400)).pack(anchor="w",
                                                                                    pady=(_p(0), _p(18)))
        for k in _sessao.ETAPAS[1:]:
            v = (s.m.get("etapas") or {}).get(k)
            if not v:
                continue
            marca = {"ok": "✓", "falhou": "✗", "pulada": "–", "pendente": "○"}.get(v["status"], "?")
            estilo = "Alerta.TLabel" if v["status"] == "falhou" else "Sub.TLabel"
            txt = f"{marca}  {ROTULO_ETAPA.get(k, k)}"
            if v["status"] != "ok" or k in ("estrutura", "publicacao"):
                txt += f" — {v.get('detalhe', '')}"
            ttk.Label(f, text=txt, style=estilo, wraplength=_p(410)).pack(anchor="w", pady=_p(1))

        pub = s.m.get("publicacao") or {}
        rod = ttk.Frame(f)
        rod.pack(side="bottom", fill="x")
        if s.status_etapa("publicacao") == "pendente":
            def publicar():
                import pipeline
                try:
                    pipeline.publicar(Sessao.abrir(s.pasta), self.cfg)
                except Exception as e:
                    messagebox.showerror("Atas", f"Não publicou: {e}")
                self.pronto(s)
            ttk.Button(rod, text="Publicar para o cliente (com senha)", style="Primario.TButton",
                       command=publicar).pack(fill="x", pady=(_p(0), _p(8)))
        if pub.get("url") and pub.get("senha") and not pub.get("apagada_em"):
            txt = f"{pub['url']}\nSenha: {pub['senha']}"

            def copiar():
                self.clipboard_clear()
                self.clipboard_append(txt)
            ttk.Button(rod, text="Copiar link e senha para o cliente", style="Primario.TButton",
                       command=copiar).pack(fill="x", pady=(_p(0), _p(8)))
        alvo = next((s.caminho(n) for n in ("entregavel.pdf", "ata.pdf", "ata.html", "ata.md")
                     if s.caminho(n).exists()), s.pasta)

        def abrir_pasta():
            import atas
            atas.abrir_no_explorer(alvo)

        def ver():
            import os
            h = s.caminho("ata.html")
            if h.exists():
                os.startfile(str(h))
        ttk.Button(rod, text="Ver a ata", command=ver).pack(fill="x")
        ttk.Button(rod, text="Abrir a pasta", command=abrir_pasta).pack(fill="x", pady=(_p(8), _p(0)))
        ttk.Button(rod, text="Nova reunião", command=self.inicio).pack(fill="x", pady=(_p(8), _p(0)))
        ttk.Label(rod, text="No Claude: /ata — revisar nomes, lacunas e o que atualizar.",
                  style="Sub.TLabel").pack(anchor="w", pady=(_p(14), _p(0)))


def main():
    try:
        App().mainloop()
    except Exception:
        _log(traceback.format_exc())
        _console(True)
        raise


if __name__ == "__main__":
    main()
