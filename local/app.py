# -*- coding: utf-8 -*-
"""
Atas — a janela. Dois cliques no atalho "Atas" da Área de Trabalho (ou em gravar.bat).

    Nova reunião  →  Gravando  →  Pronto

Desenho (regra do Pedro: pouca informação, muito respiro). Na v2 inicial eram cinco
telas, com uma de checagem de áudio no meio, e o Pedro achou "um pouquinho too much"
(30/09/2026). Agora:
  - **Nova reunião** pede só o que muda o destino da ata: título, tipo e quem fala do
    outro lado. Projeto, Claude e ao vivo ficam em "Mais opções", com resumo de uma linha.
  - **Gravar** já grava. Os dispositivos são escolhidos e conferidos em segundo plano;
    a tela de gravação mostra qual microfone está valendo e só fala de problema se ele
    existir.
  - **Pronto** mostra o resultado e só lista etapas que falharam; o resto fica em
    "Detalhes".
Cor só onde comunica estado: vermelho = gravando ou problema.

Garantias, além das do gravador: ao abrir, avisa de gravação interrompida e oferece
gerar a ata; fechar durante a gravação pergunta antes e nunca descarta áudio; se os
dois canais pararem, a tela diz NÃO ESTÁ GRAVANDO em vez de seguir contando o tempo;
erro inesperado aparece numa caixa e fica em local/atas.log.
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
import record  # noqa: E402  (importado na thread principal: segura o COM do processo)
import sessao as _sessao  # noqa: E402
from sessao import FORMATOS, TIPOS, Sessao  # noqa: E402

LOG = pathlib.Path(__file__).parent / "atas.log"
FORMATO_NAO_SEI = "não sei"
VERMELHO = "#C0392B"
CINZA = "#6E6E69"
VERDE = "#3A5A50"
ROTULO_ETAPA = {"transcricao": "Transcrição", "falantes": "Quem falou", "estrutura": "Ata (Claude)",
                "render": "Página", "pdf": "PDF", "publicacao": "Publicação",
                "raio_x": "Raio-X da fala", "audio": "Áudio guardado",
                "avaliacao": "Avaliação interna"}
ESCALA = 1.0     # definida ao abrir a janela: 1.0 = tela a 100%


def _p(n):
    """Pixels de desenho → pixels da tela. Sem escalar, 28 px numa tela a 250% viram nada."""
    return int(round(n * ESCALA))


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


def _dpi_nitido():
    """Sem isto o Windows amplia a janela do Tk como bitmap e o texto fica borrado no XPS."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _nivel_pct(rms):
    db = 20 * math.log10(max(rms, 1e-9))
    return max(0, min(100, (db + 60) * 2))          # -60 dB → 0 ; -10 dB → 100


def _fmt_tempo(seg):
    seg = int(seg)
    return f"{seg // 3600:02d}:{seg % 3600 // 60:02d}:{seg % 60:02d}"


def formato_da_tela(tipo, escolha):
    """O que vai para o sessao.json: o formato só vale em cliente; "não sei" = None."""
    return escolha if tipo == "cliente" and escolha in FORMATOS else None


def _curto(nome):
    """'Microphone (AB13X USB Audio)' → 'AB13X USB Audio'."""
    if nome and "(" in nome and nome.endswith(")"):
        return nome[nome.index("(") + 1:-1]
    return nome or "—"


class App(tk.Tk):
    def __init__(self):
        _dpi_nitido()
        super().__init__()
        global ESCALA
        ESCALA = self.winfo_fpixels("1i") / 96.0
        self.cfg = _config.carregar()
        self.title("Atas")
        self.geometry(f"{_p(440)}x{_p(540)}")
        self.minsize(_p(400), _p(480))
        self.configure(padx=_p(32), pady=_p(28))
        self.report_callback_exception = self._erro_tk
        self.protocol("WM_DELETE_WINDOW", self._fechar)
        st = ttk.Style(self)
        try:
            st.theme_use("vista")
        except tk.TclError:
            pass
        base = "Segoe UI"
        self.fonte = base
        st.configure("T.TLabel", font=(base, 18, "bold"))
        st.configure("Sub.TLabel", font=(base, 10), foreground=CINZA)
        st.configure("Campo.TLabel", font=(base, 10, "bold"))
        st.configure("Grande.TLabel", font=(base, 30, "bold"))
        st.configure("Rec.TLabel", font=(base, 14, "bold"), foreground=VERMELHO)
        st.configure("Alerta.TLabel", font=(base, 10), foreground=VERMELHO)
        st.configure("Primario.TButton", font=(base, 11, "bold"), padding=(_p(16), _p(10)))
        st.configure("TButton", font=(base, 10), padding=(_p(10), _p(6)))
        st.configure("Link.TButton", font=(base, 9), padding=(0, _p(2)))
        st.configure("Valor.TLabel", font=(base, 12, "bold"))
        st.configure("ValorAlerta.TLabel", font=(base, 12, "bold"), foreground=VERMELHO)
        st.configure("Texto.TLabel", font=(base, 10))
        st.configure("Link.TLabel", font=(base, 10, "underline"), foreground=CINZA)
        self.q = queue.Queue()
        self.s = self.g = self.av = None
        self.gt = None                  # gravador do treino (separado: parar um treino nunca gera ata)
        self.analisando_treino = False
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
        _log("".join(traceback.format_exception(exc, val, tb)))
        _console(True)
        messagebox.showerror("Atas — erro", f"{val}\n\nDetalhes em {LOG}")

    def _drenar(self):
        try:
            while True:
                self.q.get_nowait()()
        except queue.Empty:
            pass
        self.after(100, self._drenar)

    def _fechar(self):
        if self.gt is not None:
            if messagebox.askyesno("Atas", "Parar o treino e ver o retorno?"):
                self.treino_parar()
            return
        if self.analisando_treino and not messagebox.askyesno(
                "Atas", "O treino ainda está sendo analisado. Fechar mesmo assim?"):
            return
        if self.g is not None:
            if messagebox.askyesno("Atas", "Parar a gravação e gerar a ata?\n\n"
                                   "(O áudio até aqui já está salvo.)"):
                self.parar()
            return
        if self.processando and not messagebox.askyesno(
                "Atas", "A ata ainda está sendo gerada. Fechar mesmo assim?\n\n"
                "Nada se perde: na próxima abertura o Atas oferece terminar."):
            return
        self.destroy()

    def _link(self, pai, texto, comando):
        """Texto clicável, sem borda (regra do Pedro: borda só quando comunica estado)."""
        lb = ttk.Label(pai, text=texto, style="Link.TLabel", cursor="hand2")
        lb.bind("<Button-1>", lambda _e: comando())
        lb.invoke = comando                  # as fotos de conferência da janela clicam por aqui
        return lb

    def _recolhivel(self, pai, rotulo, resumo_txt, link=False):
        """Botão 'rótulo' + linha de resumo; devolve o frame que abre/fecha."""
        corpo = ttk.Frame(pai)
        botao = self._link(pai, rotulo, lambda: None) if link else ttk.Button(pai, text=rotulo, style="Link.TButton")
        botao.pack(anchor="w")
        resumo = ttk.Label(pai, text=resumo_txt, style="Sub.TLabel", wraplength=_p(370))
        resumo.pack(anchor="w")
        aberto = {"v": False}

        def alternar():
            aberto["v"] = not aberto["v"]
            if aberto["v"]:
                corpo.pack(fill="x", after=resumo, pady=(_p(8), 0))
            else:
                corpo.pack_forget()
        if link:
            botao.bind("<Button-1>", lambda _e: alternar())
            botao.invoke = alternar
        else:
            botao.configure(command=alternar)
        return corpo, resumo

    # ── 1 · nova reunião ───────────────────────────────────────────────────
    def inicio(self):
        f = self._limpar()
        self.title("Atas")
        pend = [x for x in _sessao.a_retomar() if x.id not in self.dispensadas]
        if pend:
            o = pend[-1]
            box = ttk.Frame(f)
            box.pack(fill="x", pady=(0, _p(20)))
            ttk.Label(box, text=("Gravação interrompida" if o.orfa() else "Ata que não terminou")
                      + f" · {o.resumo_curto()}", style="Alerta.TLabel",
                      wraplength=_p(370)).pack(anchor="w")
            linha = ttk.Frame(box)
            linha.pack(anchor="w", pady=(_p(4), 0))
            ttk.Button(linha, text="Terminar agora", command=lambda: self.processar(o, retomar=True)
                       ).pack(side="left")
            ttk.Button(linha, text="Agora não", style="Link.TButton",
                       command=lambda: (self.dispensadas.add(o.id), self.inicio())
                       ).pack(side="left", padx=(_p(12), 0))

        cab = ttk.Frame(f)
        cab.pack(fill="x", pady=(0, _p(20)))
        ttk.Label(cab, text="Nova reunião", style="T.TLabel").pack(side="left")
        # modo treino (14/10/2026): um acesso discreto, à direita do título; não mexe no fluxo da reunião
        self._link(cab, "Treinar", self.treino_inicio).pack(side="right")

        ttk.Label(f, text="Título", style="Campo.TLabel").pack(anchor="w")
        self.v_titulo = tk.StringVar()
        e = ttk.Entry(f, textvariable=self.v_titulo, font=(self.fonte, 11))
        e.pack(fill="x", pady=(_p(6), _p(20)))
        e.focus_set()

        ttk.Label(f, text="Tipo", style="Campo.TLabel").pack(anchor="w")
        # sem valor padrão DE PROPÓSITO: herdar o da reunião anterior fazia Parresia virar cliente
        self.v_tipo = tk.StringVar(value="")
        linha = ttk.Frame(f)
        linha.pack(fill="x", pady=(_p(6), 0))
        # formato (14/10/2026): só aparece em cliente, uma linha discreta, "não sei" de padrão.
        # Afina a faixa da fatia de fala no Raio-X (descoberta 35–50%; demo/alinhamento 45–60%).
        self.v_formato = tk.StringVar(value=FORMATO_NAO_SEI)
        l_formato = ttk.Frame(f)
        ttk.Label(l_formato, text="Formato", style="Sub.TLabel").pack(side="left")
        ttk.Combobox(l_formato, textvariable=self.v_formato, state="readonly", width=12,
                     values=[FORMATO_NAO_SEI, *FORMATOS], font=(self.fonte, 9)
                     ).pack(side="left", padx=(_p(8), 0))

        def tipo_escolhido():
            self.l_falta.configure(text="")
            if self.v_tipo.get() == "cliente":
                l_formato.pack(anchor="w", after=linha, pady=(_p(8), 0))
            else:
                l_formato.pack_forget()
                self.v_formato.set(FORMATO_NAO_SEI)
        for k, rot in TIPOS.items():
            ttk.Radiobutton(linha, text=rot.split(" (")[0].split(" /")[0], value=k,
                            variable=self.v_tipo, command=tipo_escolhido
                            ).pack(side="left", padx=(0, _p(14)))
        self.l_falta = ttk.Label(f, text="", style="Alerta.TLabel")
        self.l_falta.pack(anchor="w", pady=(0, _p(14)))

        ttk.Label(f, text="Quem fala do outro lado", style="Campo.TLabel").pack(anchor="w")
        self.v_part = tk.StringVar()
        ttk.Entry(f, textvariable=self.v_part, font=(self.fonte, 11)).pack(fill="x", pady=(_p(6), _p(4)))
        ttk.Label(f, text="nomes separados por vírgula", style="Sub.TLabel").pack(anchor="w",
                                                                                  pady=(0, _p(20)))

        # mais opções: projeto, Claude, ao vivo
        self.v_projeto = tk.StringVar()
        self.v_claude = tk.BooleanVar(value=bool(self.cfg.get("estruturar", True)))
        self.v_ao_vivo = tk.BooleanVar(value=bool(self.cfg.get("ao_vivo")))
        corpo, resumo = self._recolhivel(f, "Mais opções", "")

        def atualizar(*_):
            partes = [self.v_projeto.get().strip() or "sem projeto",
                      "ata pelo Claude" if self.v_claude.get() else "sem Claude"]
            if self.v_ao_vivo.get():
                partes.append("ao vivo")
            resumo.configure(text=" · ".join(partes))
        todas = _sessao.listar()
        projetos = sorted({s.m.get("projeto") for s in todas if s.m.get("projeto")})
        ttk.Label(corpo, text="Projeto", style="Sub.TLabel").pack(anchor="w")
        cb = ttk.Combobox(corpo, textvariable=self.v_projeto, values=projetos,
                          font=(self.fonte, 10))
        cb.pack(fill="x", pady=(_p(2), _p(8)))

        def projeto_escolhido(_e=None):
            atualizar()
            if not self.v_part.get().strip():
                mesmo = [s for s in todas if s.m.get("projeto") == self.v_projeto.get()
                         and s.m.get("participantes")]
                if mesmo:
                    self.v_part.set(", ".join(mesmo[-1].m["participantes"]))
        cb.bind("<<ComboboxSelected>>", projeto_escolhido)
        cb.bind("<KeyRelease>", atualizar)
        ttk.Checkbutton(corpo, text="Gerar a ata com o Claude", variable=self.v_claude,
                        command=atualizar).pack(anchor="w")
        ttk.Checkbutton(corpo, text="Transcrição ao vivo (o Claude acompanha a reunião)",
                        variable=self.v_ao_vivo, command=atualizar).pack(anchor="w")
        atualizar()

        rod = ttk.Frame(f)
        rod.pack(side="bottom", fill="x")
        ttk.Label(rod, text="Avise que está gravando.", style="Sub.TLabel").pack(anchor="w",
                                                                                pady=(0, _p(10)))
        self.b_gravar = ttk.Button(rod, text="Gravar", style="Primario.TButton",
                                   command=self.gravar)
        self.b_gravar.pack(fill="x")

    # ── 2 · gravando ───────────────────────────────────────────────────────
    def gravar(self):
        if self.v_tipo.get() not in TIPOS:
            self.l_falta.configure(text="Escolha o tipo: ele decide para onde a ata vai.")
            return
        self.ctx = {"titulo": self.v_titulo.get().strip(), "tipo": self.v_tipo.get(),
                    "projeto": self.v_projeto.get().strip(),
                    "formato": formato_da_tela(self.v_tipo.get(), self.v_formato.get()),
                    "participantes": [p.strip() for p in self.v_part.get().split(",") if p.strip()]}
        self.cfg["estruturar"] = self.v_claude.get()
        self.cfg["ao_vivo"] = self.v_ao_vivo.get()
        self.b_gravar.configure(text="Preparando o áudio…", state="disabled")

        def preparar():
            try:
                disp = record.escolher_dispositivos(self.cfg.get("microfone"))
                self.q.put(lambda: self._comecar(disp))
            except Exception as e:
                msg = str(e)
                _log(traceback.format_exc())
                self.q.put(lambda: (messagebox.showerror("Atas", f"Não consegui abrir o áudio:\n{msg}"),
                                    self.inicio()))
        threading.Thread(target=preparar, daemon=True).start()

    def _comecar(self, disp):
        c = self.ctx
        self.s = Sessao.criar(c["titulo"], c["tipo"], c["projeto"], c["participantes"],
                              formato=c.get("formato"))
        self.g = record.Gravador(self.s, disp)
        self.g.iniciar()
        _log(f"gravando {self.s.id} · mic {disp['mic'].name} "
             f"({getattr(disp['mic'], 'via', 'soundcard')}) · loop "
             f"{disp['loop'].name if disp['loop'] else None}")
        if self.cfg.get("ao_vivo"):
            import ao_vivo
            self.av = ao_vivo.AoVivo(self.s, self.cfg)
            self.av.start()
        f = self._limpar()
        self.l_rec = ttk.Label(f, text="● Gravando", style="Rec.TLabel")
        self.l_rec.pack(anchor="w")
        ttk.Label(f, text=self.s.m["titulo"], style="Sub.TLabel", wraplength=_p(370)).pack(anchor="w")
        self.l_tempo = ttk.Label(f, text="00:00:00", style="Grande.TLabel")
        self.l_tempo.pack(anchor="w", pady=(_p(18), _p(24)))
        self.barras = {}
        for nome, rot in (("mic", "Você"), ("loop", "Chamada")):
            if nome not in self.g.canais:
                continue
            ttk.Label(f, text=rot, style="Sub.TLabel").pack(anchor="w")
            b = ttk.Progressbar(f, maximum=100)
            b.pack(fill="x", pady=(_p(2), _p(14)))
            self.barras[nome] = b
        disp_txt = f"Microfone: {_curto(disp['mic'].name)}"
        ttk.Label(f, text=disp_txt, style="Sub.TLabel", wraplength=_p(370)).pack(anchor="w")
        self.l_alerta = ttk.Label(f, text="\n".join(disp["avisos"]), style="Alerta.TLabel",
                                  wraplength=_p(370))
        self.l_alerta.pack(anchor="w", pady=(_p(8), 0))
        self.avisos_disp = list(disp["avisos"])
        rod = ttk.Frame(f)
        rod.pack(side="bottom", fill="x")
        # marcar momento (14/10/2026): uma linha discreta acima do Parar; o contador só aparece
        # depois da primeira marca. Sem som nem popup: a call está em primeiro plano.
        linha = ttk.Frame(rod)
        linha.pack(fill="x", pady=(0, _p(12)))
        self._link(linha, "Marcar momento", lambda: self._marcar(self.g.decorrido() if self.g else None,
                                                                 "botao")).pack(side="left")
        self.l_atalho = ttk.Label(linha, text="", style="Sub.TLabel")
        self.l_atalho.pack(side="left", padx=(_p(8), 0))
        self.l_marcas = ttk.Label(linha, text="", style="Sub.TLabel")
        self.l_marcas.pack(side="right")
        ttk.Button(rod, text="Parar e gerar a ata", style="Primario.TButton",
                   command=self.parar).pack(fill="x")
        self._ligar_atalho()
        self._tique()

    # ── marcar momento (14/10/2026) ─────────────────────────────────────────
    def _ligar_atalho(self):
        import atalho
        self.at = None
        try:
            def disparou():                      # thread do atalho: só anota o instante
                g = self.g
                if g is not None:
                    t = g.decorrido()
                    self.q.put(lambda: self._marcar(t, "atalho"))
            self.at = atalho.iniciar(disparou, self.cfg.get("marcar_atalho") or atalho.PADRAO)
            if self.at.erro:
                self.avisos_disp.append(self.at.erro)
                self.at = None
            else:
                self.l_atalho.configure(text=atalho.legivel(self.at.atalho))
        except Exception as e:
            _log(traceback.format_exc())
            self.avisos_disp.append(f"atalho de marcar indisponível ({e}): use o botão")

    def _desligar_atalho(self):
        at, self.at = getattr(self, "at", None), None
        if at is not None:
            at.parar()

    def _marcar(self, t, origem):
        import marcas
        if self.g is None or self.s is None or t is None:
            return
        try:
            nova = marcas.adicionar(self.s, t, origem)
        except RuntimeError:                 # o ao vivo mexeu no manifesto no mesmo instante
            _log(traceback.format_exc())
            self.s.salvar()                  # a marca já está em s.m; só falta o disco
            nova = True
        if nova is not None and self.cfg.get("marcar_som"):
            try:
                import winsound
                winsound.MessageBeep(0)
            except Exception:
                pass
        n = len(marcas.lista(self.s))
        self.l_marcas.configure(text=f"{n} momento{'s' if n != 1 else ''} marcado{'s' if n != 1 else ''}")

    def _tique(self):
        if self.g is None:
            return
        dec = self.g.decorrido()
        vivos = [c for c in self.g.canais.values() if c.is_alive() and not c.morto]
        if not vivos:
            self.l_rec.configure(text="✕ NÃO ESTÁ GRAVANDO")
            self.title("✕ Não está gravando — Atas")
        else:
            # a janela fica atrás do Meet: o título (barra de tarefas) confirma a marca sem roubar foco
            n = len(self.s.m.get("marcas") or [])
            self.title(f"● {_fmt_tempo(dec)}" + (f" · {n} marcado{'s' if n != 1 else ''}" if n else "")
                       + " — Atas")
        self.l_tempo.configure(text=_fmt_tempo(dec))
        for k, b in self.barras.items():
            b["value"] = _nivel_pct(self.g.niveis().get(k, 0))
        alertas = list(self.avisos_disp)
        mic = self.g.mudo_ha("mic")
        if mic is not None and mic > 60:
            alertas.append(f"Seu microfone está mudo há {int(mic // 60)} min.")
        loop = self.g.mudo_ha("loop")
        if loop is not None and loop > 180 and dec > 180:
            alertas.append(f"Não chega som da chamada há {int(loop // 60)} min.")
        for c in self.g.canais.values():
            if c.morto or not c.is_alive():
                alertas.append(f"O canal {'do microfone' if c.nome == 'mic' else 'da chamada'} "
                               f"parou: {c.morto or 'motivo desconhecido'}")
            elif c.trocas:
                alertas.append(f"O {'microfone' if c.nome == 'mic' else 'som da chamada'} caiu e "
                               f"voltou por {_curto(c.trocas[-1][9:])}")
        if self.av is not None and self.av.erro:
            alertas.append(self.av.erro)
        self.l_alerta.configure(text="\n".join(dict.fromkeys(alertas)))
        self.after(250, self._tique)

    def parar(self):
        g, self.g = self.g, None
        if g is None:
            return
        self._desligar_atalho()
        if self.av is not None:
            self.av.parar()
        g.parar()
        _log(f"parou {self.s.id} ({self.s.duracao_s():.0f}s)")
        self.processar(self.s)

    # ── 3 · gerando / pronto ───────────────────────────────────────────────
    def processar(self, s, retomar=False):
        if retomar and s.m.get("estado") == "gravando":
            s.m["audio"]["duracao_s"] = round(s.duracao_s(), 1)
            s.avisar("gravação interrompida; áudio recuperado até o último bloco gravado")
            s.etapa("captura", "ok", f"recuperada após interrupção · {s.duracao_s():.0f}s")
            s.estado("gravado")
        self.s = s
        self.processando = True
        f = self._limpar()
        self.title("Gerando a ata — Atas")
        ttk.Label(f, text="Gerando a ata", style="T.TLabel").pack(anchor="w")
        ttk.Label(f, text=f"{s.m.get('titulo')} · {round(s.duracao_s() / 60)} min",
                  style="Sub.TLabel", wraplength=_p(370)).pack(anchor="w", pady=(0, _p(20)))
        self.l_msg = ttk.Label(f, text="Começando…", style="Sub.TLabel", wraplength=_p(370))
        self.l_msg.pack(anchor="w")
        barra = ttk.Progressbar(f, mode="indeterminate")
        barra.pack(fill="x", pady=(_p(10), 0))
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

    def _cartao_fala(self, f, s):
        """Raio-X da Fala na tela final (v2.1). A v2 calculava e não mostrava nada; o Pedro achou
        que a função tinha sumido. Só o que não bateu a meta fica à vista; o resto, no painel."""
        import json
        import analise_fala
        hist = analise_fala.FALA_DIR / "historico.jsonl"
        reg = None
        if hist.exists():
            for ln in hist.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if r.get("id") == s.id:
                    reg = r
        if not reg or not reg.get("metrics", {}).get("metas"):
            return
        m = reg["metrics"]
        caixa = ttk.Frame(f)
        caixa.pack(fill="x", pady=(0, _p(14)))
        ttk.Label(caixa, text="Sua fala nesta reunião", style="Sub.TLabel").pack(anchor="w")
        # v3 (14/10/2026): ok None = amostra pequena (< 1.000 palavras suas): número sem julgamento
        fora = [x for x in m["metas"] if x[3] is False]
        pequena = any(x[3] is None for x in m["metas"])
        for nome, val, meta, _ok in fora[:3]:
            ttk.Label(caixa, text=f"!  {nome}: {val} (meta {meta})", style="Alerta.TLabel",
                      wraplength=_p(370)).pack(anchor="w")
        if pequena:
            ttk.Label(caixa, text=f"·  amostra pequena ({m.get('palavras_voce', 0)} palavras suas, menos de 1.000): "
                                  "os números só informam", style="Sub.TLabel", wraplength=_p(370)).pack(anchor="w")
        elif not fora:
            ttk.Label(caixa, text="✓  todas as metas batidas", style="Sub.TLabel").pack(anchor="w")
        if m.get("voz"):
            itens = {it["chave"]: it for it in analise_fala.leitura_voz(m["voz"])[0]}
            ent, vol = itens["entonacao_st"], itens["volume_variacao_db"]
            ttk.Label(caixa, text=f"·  voz {ent['zona']} ({ent['valor']} semitons), "
                                  f"volume {vol['zona']}", style="Sub.TLabel").pack(anchor="w")

        def abrir(caminho):
            import os
            if caminho.exists():
                os.startfile(str(caminho))
        linha = ttk.Frame(caixa)
        linha.pack(fill="x", pady=(_p(4), 0))
        pagina = analise_fala.FALA_DIR / analise_fala._arquivo_pagina(reg) if "safe" in reg else None
        ttk.Button(linha, text="Ver o Raio-X completo", style="Link.TButton",
                   command=lambda: abrir(pagina if pagina and pagina.exists()
                                         else analise_fala.FALA_DIR / "raio-x.html")).pack(side="left")
        import avaliar
        aval = avaliar.mais_recente(s)
        if aval:
            alvo = aval.with_suffix(".html") if aval.with_suffix(".html").exists() else aval
            ttk.Button(linha, text="Avaliação interna", style="Link.TButton",
                       command=lambda: abrir(alvo)).pack(side="right")

    def pronto(self, s):
        self.processando = False
        s = Sessao.abrir(s.pasta)
        etapas = s.m.get("etapas") or {}
        falhas = [(k, v) for k, v in etapas.items() if v.get("status") == "falhou"]
        f = self._limpar()
        self.title("Pronto — Atas")
        ttk.Label(f, text="Ata pronta" if not falhas else "Ata com problema",
                  style="T.TLabel").pack(anchor="w")
        ttk.Label(f, text=s.m.get("titulo"), style="Sub.TLabel", wraplength=_p(370)).pack(
            anchor="w", pady=(0, _p(18)))
        for k, v in falhas:
            ttk.Label(f, text=f"{ROTULO_ETAPA.get(k, k)}: {v.get('detalhe', '')}",
                      style="Alerta.TLabel", wraplength=_p(370)).pack(anchor="w", pady=(0, _p(6)))
        est = etapas.get("estrutura") or {}
        if est.get("status") == "ok":
            ttk.Label(f, text=est.get("detalhe", ""), style="Sub.TLabel",
                      wraplength=_p(370)).pack(anchor="w", pady=(0, _p(12)))
        self._cartao_fala(f, s)
        corpo, _ = self._recolhivel(f, "Detalhes", "")
        for k in _sessao.ETAPAS[1:]:
            v = etapas.get(k)
            if v:
                marca = {"ok": "✓", "falhou": "✗", "pulada": "–", "pendente": "○"}.get(v["status"], "?")
                ttk.Label(corpo, text=f"{marca}  {ROTULO_ETAPA.get(k, k)} — {v.get('detalhe', '')}",
                          style="Sub.TLabel", wraplength=_p(370)).pack(anchor="w")

        rod = ttk.Frame(f)
        rod.pack(side="bottom", fill="x")
        pub = s.m.get("publicacao") or {}
        if s.status_etapa("publicacao") == "pendente":
            def publicar():
                import pipeline
                try:
                    pipeline.publicar(Sessao.abrir(s.pasta), self.cfg)
                except Exception as e:
                    messagebox.showerror("Atas", f"Não publicou: {e}")
                self.pronto(s)
            ttk.Button(rod, text="Publicar para o cliente", command=publicar).pack(
                fill="x", pady=(0, _p(8)))
        elif pub.get("url") and pub.get("senha") and not pub.get("apagada_em"):
            txt = f"{pub['url']}\nSenha: {pub['senha']}"
            ttk.Button(rod, text="Copiar link e senha",
                       command=lambda: (self.clipboard_clear(), self.clipboard_append(txt))
                       ).pack(fill="x", pady=(0, _p(8)))

        def ver():
            import os
            h = s.caminho("ata.html")
            if h.exists():
                os.startfile(str(h))

        def pasta():
            import atas
            alvo = next((s.caminho(n) for n in ("entregavel.pdf", "ata.pdf", "ata.html")
                         if s.caminho(n).exists()), s.pasta)
            atas.abrir_no_explorer(alvo)
        ttk.Button(rod, text="Ver a ata", style="Primario.TButton", command=ver).pack(fill="x")
        linha = ttk.Frame(rod)
        linha.pack(fill="x", pady=(_p(10), 0))
        ttk.Button(linha, text="Abrir a pasta", style="Link.TButton", command=pasta).pack(side="left")
        ttk.Button(linha, text="Nova reunião", style="Link.TButton", command=self.inicio).pack(side="right")

    # ── modo treino (14/10/2026): Treino → Treinando → Seu treino ──────────
    # Ensaio sozinho, só o microfone; o resultado fica fora do Raio-X das reuniões (treino.py).
    def _campo(self, f, rotulo, topo=0):
        ttk.Label(f, text=rotulo, style="Campo.TLabel").pack(anchor="w", pady=(_p(topo), 0))

    def treino_inicio(self):
        import treino as _tr
        f = self._limpar()
        self.title("Treino — Atas")
        cab = ttk.Frame(f)
        cab.pack(fill="x")
        ttk.Label(cab, text="Treino", style="T.TLabel").pack(side="left")
        self._link(cab, "Reuniões", self.inicio).pack(side="right")
        ttk.Label(f, text="Você fala sozinho. Fica fora do Raio-X das reuniões.", style="Sub.TLabel",
                  wraplength=_p(370)).pack(anchor="w", pady=(_p(2), _p(20)))

        self._campo(f, "Tipo")
        self.v_ttipo = tk.StringVar(value=getattr(self, "_ult_ttipo", "reuniao"))
        linha = ttk.Frame(f)
        linha.pack(fill="x", pady=(_p(6), _p(20)))
        for k, rot in _tr.TIPOS_TREINO.items():
            ttk.Radiobutton(linha, text=rot, value=k, variable=self.v_ttipo).pack(side="left", padx=(0, _p(14)))

        linha = ttk.Frame(f)
        linha.pack(fill="x")
        ttk.Label(linha, text="Assunto", style="Campo.TLabel").pack(side="left")
        ttk.Label(linha, text="opcional", style="Sub.TLabel").pack(side="left", padx=(_p(8), 0))
        self.v_tassunto = tk.StringVar()
        e = ttk.Entry(f, textvariable=self.v_tassunto, font=(self.fonte, 11))
        e.pack(fill="x", pady=(_p(6), _p(20)))
        e.focus_set()

        self._campo(f, "Duração")
        self.v_tdur = tk.IntVar(value=getattr(self, "_ult_tdur", _tr.DURACAO_PADRAO_S // 60))
        linha = ttk.Frame(f)
        linha.pack(fill="x", pady=(_p(6), _p(20)))
        for n in _tr.DURACOES_MIN:
            ttk.Radiobutton(linha, text=f"{n} min", value=n, variable=self.v_tdur).pack(side="left", padx=(0, _p(14)))

        # mais opções: alvo de ritmo e a nota do Sinapse que confere o conteúdo
        alvos = {f"{_tr._br(a, 1)} sílabas/s · {r}": a for a, r in sorted(_tr.ALVOS.items(), key=lambda x: -x[0])}
        self._alvos = alvos
        self.v_talvo = tk.StringVar(value=next(k for k, a in alvos.items() if a == _tr.ALVO_PADRAO))
        notas = _tr.notas_de_estudo()
        self._notas = notas
        self.v_tnota = tk.StringVar(value="nenhuma")
        corpo, resumo = self._recolhivel(f, "Mais opções", "", link=True)

        def atualizar(*_):
            nota = self.v_tnota.get()
            resumo.configure(text=f"ritmo alvo {_tr._br(alvos[self.v_talvo.get()], 1)} sílabas/s · "
                                  + ("sem nota" if nota == "nenhuma" else f"confere com a nota {nota}"))
        ttk.Label(corpo, text="Alvo de ritmo", style="Sub.TLabel").pack(anchor="w")
        cb = ttk.Combobox(corpo, textvariable=self.v_talvo, values=list(alvos), state="readonly",
                          font=(self.fonte, 10))
        cb.pack(fill="x", pady=(_p(2), _p(8)))
        cb.bind("<<ComboboxSelected>>", atualizar)
        ttk.Label(corpo, text="Nota do Sinapse para conferir o conteúdo (explicar tema)",
                  style="Sub.TLabel", wraplength=_p(370)).pack(anchor="w")
        cbn = ttk.Combobox(corpo, textvariable=self.v_tnota, values=["nenhuma", *notas], state="readonly",
                           font=(self.fonte, 10))
        cbn.pack(fill="x", pady=(_p(2), 0))
        cbn.bind("<<ComboboxSelected>>", atualizar)
        atualizar()

        rod = ttk.Frame(f)
        rod.pack(side="bottom", fill="x")
        self.b_treinar = ttk.Button(rod, text="Começar", style="Primario.TButton", command=self.treino_gravar)
        self.b_treinar.pack(fill="x")

    def treino_gravar(self):
        nota = self.v_tnota.get()
        self._ult_ttipo, self._ult_tdur = self.v_ttipo.get(), self.v_tdur.get()
        self.tctx = {"tipo": self.v_ttipo.get(), "assunto": self.v_tassunto.get().strip(),
                     "nota": str(self._notas[nota]) if nota in self._notas else None,
                     "duracao_alvo_s": int(self.v_tdur.get()) * 60, "alvo": self._alvos[self.v_talvo.get()]}
        self.b_treinar.configure(text="Preparando o microfone…", state="disabled")

        def preparar():
            try:
                disp = record.escolher_so_microfone(self.cfg.get("microfone"))
                self.q.put(lambda: self._treino_comecar(disp))
            except Exception as e:
                msg = str(e)
                _log(traceback.format_exc())
                self.q.put(lambda: (messagebox.showerror("Atas", f"Não consegui abrir o microfone:\n{msg}"),
                                    self.treino_inicio()))
        threading.Thread(target=preparar, daemon=True).start()

    def _treino_comecar(self, disp):
        import treino as _tr
        c = self.tctx
        self.t = _tr.Treino.criar(c["tipo"], c["assunto"], c["nota"], c["duracao_alvo_s"], c["alvo"])
        self.gt = record.Gravador(self.t, disp)
        self.gt.iniciar()
        _log(f"treino {self.t.id} · mic {disp['mic'].name}")
        f = self._limpar()
        self.l_trec = ttk.Label(f, text="● Treinando", style="Rec.TLabel")
        self.l_trec.pack(anchor="w")
        ttk.Label(f, text=_tr.TIPOS_TREINO[c["tipo"]] + (f" · {c['assunto']}" if c["assunto"] else ""),
                  style="Sub.TLabel", wraplength=_p(370)).pack(anchor="w")
        self.l_ttempo = ttk.Label(f, text="0:00", style="Grande.TLabel")
        self.l_ttempo.pack(anchor="w", pady=(_p(18), 0))
        self.l_talvo = ttk.Label(f, text=f"alvo {_tr._mmss(c['duracao_alvo_s'])}", style="Sub.TLabel")
        self.l_talvo.pack(anchor="w", pady=(0, _p(24)))
        ttk.Label(f, text="Microfone", style="Sub.TLabel").pack(anchor="w")
        self.b_tnivel = ttk.Progressbar(f, maximum=100)
        self.b_tnivel.pack(fill="x", pady=(_p(2), _p(14)))
        ttk.Label(f, text=f"Microfone: {_curto(disp['mic'].name)}", style="Sub.TLabel",
                  wraplength=_p(370)).pack(anchor="w")
        self.l_talerta = ttk.Label(f, text="\n".join(disp["avisos"]), style="Alerta.TLabel", wraplength=_p(370))
        self.l_talerta.pack(anchor="w", pady=(_p(8), 0))
        ttk.Button(f, text="Parar e ver o retorno", style="Primario.TButton",
                   command=self.treino_parar).pack(side="bottom", fill="x")
        self._treino_tique()

    def _treino_tique(self):
        import treino as _tr
        if self.gt is None:
            return
        dec, alvo = self.gt.decorrido(), self.tctx["duracao_alvo_s"]
        self.title(f"● {_tr._mmss(dec)} — Treino")
        self.l_ttempo.configure(text=_tr._mmss(dec))
        if dec >= alvo:
            self.l_talvo.configure(text=f"passou do alvo de {_tr._mmss(alvo)}: feche a ideia")
        self.b_tnivel["value"] = _nivel_pct(self.gt.niveis().get("mic", 0))
        c = self.gt.canais.get("mic")
        alerta = ""
        if c is None or c.morto or not c.is_alive():
            alerta = "O microfone parou: " + ((c.morto if c else None) or "motivo desconhecido")
        elif (self.gt.mudo_ha("mic") or 0) > 20:
            alerta = "Não chega som do microfone."
        self.l_talerta.configure(text=alerta)
        self.after(250, self._treino_tique)

    def treino_parar(self):
        import treino as _tr
        g, self.gt = self.gt, None
        if g is None:
            return
        g.parar()
        t = self.t
        self.analisando_treino = True
        f = self._limpar()
        self.title("Analisando o treino — Atas")
        ttk.Label(f, text="Analisando o treino", style="T.TLabel").pack(anchor="w")
        ttk.Label(f, text=f"{_tr._mmss(t.duracao_s())} gravados", style="Sub.TLabel").pack(anchor="w", pady=(0, _p(20)))
        self.l_tmsg = ttk.Label(f, text="Começando…", style="Sub.TLabel", wraplength=_p(370))
        self.l_tmsg.pack(anchor="w")
        barra = ttk.Progressbar(f, mode="indeterminate")
        barra.pack(fill="x", pady=(_p(10), 0))
        barra.start(12)

        def log(msg):
            _log(msg)
            m = str(msg).strip()
            self.q.put(lambda: self.l_tmsg.configure(text=m))

        def rodar():
            try:
                _tr.analisar(t, self.cfg, log=log)
            except Exception as e:
                _log(traceback.format_exc())
                try:
                    t.m.setdefault("resultado", {})["erro"] = f"erro na análise: {e} — ver local/atas.log"
                    t.salvar()
                except Exception:
                    pass
            finally:
                self.q.put(lambda: self.treino_resultado(t))
        threading.Thread(target=rodar, daemon=True).start()

    def treino_resultado(self, t):
        import treino as _tr
        self.analisando_treino = False
        t = _tr.Treino.abrir(t.pasta)
        r = t.m.get("resultado") or {}
        m = r.get("metrics") or {}
        f = self._limpar()
        self.title("Seu treino — Atas")
        self.geometry(f"{self.winfo_width()}x{max(self.winfo_height(), _p(660))}")
        ttk.Label(f, text="Seu treino", style="T.TLabel").pack(anchor="w")
        sub = _tr.TIPOS_TREINO.get(t.tipo_treino, "") + (f" · {t.m['assunto']}" if t.m.get("assunto") else "")
        if m:
            sub += f" · {_tr._mmss(m.get('fala_s'))} de fala"
        ttk.Label(f, text=sub, style="Sub.TLabel", wraplength=_p(370)).pack(anchor="w", pady=(0, _p(18)))
        if r.get("erro"):
            ttk.Label(f, text=r["erro"], style="Alerta.TLabel", wraplength=_p(370)).pack(anchor="w")

        # os 4 números, cada um com meia linha de leitura e a comparação
        for it in r.get("principais") or []:
            linha = ttk.Frame(f)
            linha.pack(fill="x")
            ttk.Label(linha, text=it["nome"], style="Texto.TLabel").pack(side="left")
            ttk.Label(linha, text=it["valor_txt"], style="ValorAlerta.TLabel" if it["status"] == "fora"
                      else "Valor.TLabel").pack(side="right")
            leit = " · ".join(x for x in (it.get("curto"), it["comparacao"]) if x and x != "—")
            ttk.Label(f, text=leit, style="Sub.TLabel", wraplength=_p(370)).pack(anchor="w", pady=(0, _p(12)))

        # o retorno do Claude: 1 coisa para manter, 1 para mudar
        ret = r.get("retorno")
        if ret:
            for rot, chave in (("Manter", "manter"), ("Mudar", "mudar")):
                ttk.Label(f, text=rot, style="Campo.TLabel").pack(anchor="w", pady=(_p(6), 0))
                ttk.Label(f, text=ret[chave]["texto"], style="Texto.TLabel", wraplength=_p(370),
                          justify="left").pack(anchor="w")
        elif r.get("retorno_erro") and not r.get("erro"):
            ttk.Label(f, text=f"Sem retorno do Claude: {r['retorno_erro']}", style="Sub.TLabel",
                      wraplength=_p(370)).pack(anchor="w", pady=(_p(6), 0))

        # links: ouvir o trecho mais corrido · ver tudo (a página com a leitura completa de cada número,
        # os pontos do Claude e o conteúdo contra a nota). O resto não cabe na janela, e não deve.
        links = ttk.Frame(f)
        links.pack(fill="x", pady=(_p(16), 0))
        pagina = t.caminho("resultado.html")
        if pagina.exists():
            def ver():
                import os
                os.startfile(str(pagina))
            self._link(links, "Ver tudo", ver).pack(side="right")
        tc = m.get("trecho_corrido")
        if tc:
            def ouvir():
                def tocar():
                    try:
                        wav = _tr.trecho_wav(t, tc["ini"], tc["fim"])
                        if wav is None:
                            self.q.put(lambda: messagebox.showinfo("Atas", "O áudio deste treino já foi apagado."))
                            return
                        import winsound
                        winsound.PlaySound(str(wav), winsound.SND_FILENAME | winsound.SND_ASYNC)
                    except Exception as e:
                        _log(traceback.format_exc())
                        self.q.put(lambda: messagebox.showerror("Atas", f"Não consegui tocar o trecho: {e}"))
                threading.Thread(target=tocar, daemon=True).start()
            self._link(links, f"Ouvir o trecho mais rápido ({_tr._mmss(tc['ini'])})", ouvir).pack(side="left")

        rod = ttk.Frame(f)
        rod.pack(side="bottom", fill="x")
        ttk.Button(rod, text="Treinar de novo", style="Primario.TButton", command=self.treino_inicio).pack(fill="x")
        linha = ttk.Frame(rod)
        linha.pack(fill="x", pady=(_p(10), 0))
        self._link(linha, "Abrir a pasta",
                   lambda: __import__("atas").abrir_no_explorer(t.caminho("resultado.html"))).pack(side="left")
        self._link(linha, "Reuniões", self.inicio).pack(side="right")


def main():
    try:
        App().mainloop()
    except Exception:
        _log(traceback.format_exc())
        _console(True)
        raise


if __name__ == "__main__":
    main()
