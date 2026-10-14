# -*- coding: utf-8 -*-
"""
Da gravação à ata: as etapas, na ordem, cada uma registrada no sessao.json.

    transcricao → falantes → (backup .md) → estrutura → render → pdf
                → publicacao (só cliente, só quando o Pedro manda) → raio_x → audio

Propriedades que valem para todas:
  - **Retomável.** Cada etapa pula se o resultado já está no disco. Reprocessar uma
    sessão órfã ou que falhou é chamar `processar()` de novo.
  - **Nenhuma falha silenciosa.** Toda etapa termina como ok / falhou / pulada /
    pendente, com o motivo, e a UI e o CLI mostram a lista inteira no fim.
  - **A transcrição é protegida primeiro.** O backup .md é escrito logo depois de
    transcrever, antes do Claude, do navegador ou da rede. O PCM só é aposentado
    depois de o Opus conferir, e o Opus só é apagado pela retenção depois de a ata
    estar garantida (estruturada, com falas, sem etapa falhada).
  - **Um processamento por vez.** `.processando.lock` impede a janela e o /ata de
    processarem a mesma sessão juntos (dois processos aposentando o mesmo PCM perdiam
    áudio — achado da revisão de 30/09/2026).

Roteamento por tipo (decisões 1 e 5 de 30/09/2026): só `cliente` gera entregável RYZE e
pode ser publicado — e **só quando o Pedro manda** (botão na tela "Pronto", ou
`atas.py publicar`), nunca sozinho. Mudar o tipo para interno tira a página do ar.
"""
import os
import time
import traceback

import ata as _ata
import config as _config
import render
from sessao import (TIPOS_PUBLICAVEIS, Batedor, ORFA_APOS_S, agora_iso, escrever_json,
                    ler_json, listar)


class Ocupada(RuntimeError):
    pass


class Trava:
    """Lock por sessão com O_EXCL. Lock de processo morto (batida parada) é retomado."""

    def __init__(self, s):
        self.s = s
        self.p = s.caminho(".processando.lock")

    def __enter__(self):
        try:
            fd = os.open(self.p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            idade = self.s.segundos_desde_batida()
            if idade is not None and idade < ORFA_APOS_S:
                raise Ocupada("esta reunião já está sendo processada em outra janela")
            self.p.unlink(missing_ok=True)
            fd = os.open(self.p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return self

    def __exit__(self, *exc):
        self.p.unlink(missing_ok=True)
        return False


def _salvar_ata(s, a):
    escrever_json(s.caminho("ata.json"), a)


def _backup_ata(s):
    """Antes de refazer uma ata, guarda a atual (pode ter nomes confirmados e campos manuais)."""
    p = s.caminho("ata.json")
    if p.exists():
        destino = s.caminho(f"ata.antes-{time.strftime('%Y%m%d-%H%M%S')}.json")
        destino.write_bytes(p.read_bytes())
        return destino
    return None


def carregar(s):
    """(segmentos, ata) da sessão, do que estiver no disco."""
    t = ler_json(s.caminho("transcricao.json"), {}) or {}
    segs = t.get("segments", [])
    a = ler_json(s.caminho("ata.json"))
    return segs, a


def _rodar(s, nome, fn, log):
    try:
        return fn()
    except Exception as e:
        try:
            with open(s.pasta / "erros.log", "a", encoding="utf-8") as f:
                f.write(f"--- {nome} {agora_iso()}\n{traceback.format_exc()}\n")
            s.etapa(nome, "falhou", f"{type(e).__name__}: {e}")
        except Exception:
            pass
        log(f"  ✗ {nome}: {e}")
        return None


def renderizar(s, a, segs, log=print, pdf=True):
    """ata.md + ata.html e, em cliente estruturada, entregavel.html; depois os PDFs."""
    def _paginas():
        s.caminho("ata.md").write_text(render.markdown(a, segs), encoding="utf-8")
        s.caminho("ata.html").write_text(render.html(a, segs), encoding="utf-8")
        if _cliente_com_entregavel(s, a):
            s.caminho("entregavel.html").write_text(render.html(a, segs, cliente=True),
                                                    encoding="utf-8")
        s.etapa("render", "ok")
        return True
    if not _rodar(s, "render", _paginas, log) or not pdf:
        return
    _rodar(s, "pdf", lambda: _pdfs(s, a, segs), log)


def _cliente_com_entregavel(s, a):
    return s.tipo in TIPOS_PUBLICAVEIS and a.get("status") in ("estruturada", "revisada")


def _pdfs(s, a, segs):
    import entregavel
    feitos = []
    alvos = [("ata", False)] + ([("entregavel", True)] if _cliente_com_entregavel(s, a) else [])
    for nome, cli in alvos:
        tmp = s.caminho(f".{nome}.imprimir.html")
        tmp.write_text(render.html(a, segs, cliente=cli, impressao=True), encoding="utf-8")
        try:
            entregavel.html_para_pdf(tmp, s.caminho(f"{nome}.pdf"))
            feitos.append(f"{nome}.pdf")
        finally:
            tmp.unlink(missing_ok=True)
    s.etapa("pdf", "ok", ", ".join(feitos))


def despublicar(s, cfg, motivo):
    import upload
    pub = s.m.get("publicacao") or {}
    alvo = pub.get("id") or (pub.get("url") or "").rstrip("/").split("/")[-1]
    if not alvo:
        return None
    r = upload.apagar(cfg["worker_url"], cfg["upload_token"], alvo)
    s.m["publicacao"] = {"apagada_em": agora_iso(), "id": alvo, "motivo": motivo}
    s.salvar()
    s.etapa("publicacao", "ok", f"página apagada do Worker ({motivo})")
    return r


def publicar(s, cfg, log=print, forcar=False):
    """Publica o entregável. Só roda quando o Pedro manda (botão / CLI)."""
    import upload
    if s.tipo not in TIPOS_PUBLICAVEIS:
        raise RuntimeError("reunião interna não sai da máquina")
    pub = dict(s.m.get("publicacao") or {})
    if pub.get("apagada_em") and not forcar:
        raise RuntimeError(f"a página desta reunião foi apagada em {pub['apagada_em'][:10]}; "
                           "use --forcar para publicar de novo")
    if s.m.get("legado") and s.m.get("classificacao") != "confirmada":
        raise RuntimeError("reunião antiga com tipo INFERIDO: confirme antes com "
                           "`atas.py tipo <id> cliente`")
    ent = s.caminho("entregavel.html")
    if not ent.exists():
        raise RuntimeError("sem entregável (a ata ainda não foi estruturada)")
    if not _config.pode_publicar(cfg):
        raise RuntimeError("worker_url/upload_token ausentes no config.json")
    if pub.get("legado") or pub.get("apagada_em"):
        pub = {}
    senha = pub.get("senha") or upload.gerar_senha()
    log("  Publicando a página do cliente (com senha)…")
    r = upload.publicar(cfg["worker_url"], cfg["upload_token"], s.id, s.m.get("titulo"),
                        ent.read_text(encoding="utf-8"), senha,
                        cfg.get("publicacao_reter_dias", 90))
    pub.update({"url": r["url"], "id": r["id"], "senha": senha, "expira_em": r.get("expira_em"),
                "em": agora_iso()})
    s.m["publicacao"] = pub
    s.salvar()
    s.etapa("publicacao", "ok", r["url"])
    return pub


def _etapa_publicacao(s, a, cfg, log, publicar_):
    pub = s.m.get("publicacao") or {}
    no_ar = pub.get("url") and not pub.get("legado") and not pub.get("apagada_em")
    if s.tipo not in TIPOS_PUBLICAVEIS:
        if no_ar and _config.pode_publicar(cfg):
            despublicar(s, cfg, "o tipo da reunião mudou para interno")
            return
        s.etapa("publicacao", "pulada", "reunião interna não sai da máquina")
        return
    if not s.caminho("entregavel.html").exists():
        s.etapa("publicacao", "pulada", "sem entregável (a ata ainda não foi estruturada)")
        return
    if publicar_ or (no_ar and publicar_ is not False):
        publicar(s, cfg, log)                 # pedido explícito, ou atualizar a que já está no ar
        return
    s.etapa("publicacao", "pendente", "entregável pronto — publicar é decisão sua "
            "(botão na tela ou `atas.py publicar`)")


VOCE_PENDENTE = ("áudio do celular: confirme quem é você no /ata (`atas.py falantes <id> "
                 "\"Participante N=Você\"` ou `confirmar <id>`); medir a voz de outra pessoa como se "
                 "fosse a sua estragaria o histórico")


def voce_a_confirmar(s):
    """Reunião do celular em que ainda não se sabe com certeza quais falas são do Pedro."""
    return s.celular and not (s.m.get("celular") or {}).get("voce_confirmado")


def ata_garantida(s):
    """A ata desta reunião já não depende do áudio? Só então a retenção pode apagá-lo."""
    segs, a = carregar(s)
    if not segs or not a or a.get("status") not in ("estruturada", "revisada"):
        return False
    return not any(v.get("status") == "falhou" for k, v in (s.m.get("etapas") or {}).items()
                   if k in ("transcricao", "estrutura"))


def processar(s, cfg=None, log=print, forcar=(), estruturar=None, publicar_=None):
    """Roda (ou retoma) todas as etapas. Devolve o dict de etapas do sessao.json.

    publicar_: None = não publica (só atualiza a página se ela já estiver no ar);
    True = publica; False = não toca na publicação."""
    import analise_fala
    import audio
    import avaliar as _aval
    import estruturar as _estr
    import transcribe

    cfg = cfg or _config.carregar()
    with Trava(s), Batedor(s):
        s.estado("processando")

        # ── transcrição ──
        segs, a = carregar(s)
        if "transcricao" in forcar or not s.caminho("transcricao.json").exists():
            if not (audio.fonte_audio(s, "mic") or audio.fonte_audio(s, "loop")
                    or audio.fonte_audio(s, "celular")):
                s.etapa("transcricao", "falhou", "não há áudio nesta sessão")
                s.estado("falhou")
                return s.m["etapas"]
            r = _rodar(s, "transcricao", lambda: transcribe.transcrever_sessao(s, cfg, log), log)
            if r is None:
                s.estado("falhou")
                return s.m["etapas"]
            segs, info = r
            escrever_json(s.caminho("transcricao.json"), {"segments": segs, "info": info})
            if segs:
                s.etapa("transcricao", "ok", f"{len(segs)} trechos · {info['modelo']} "
                        f"({info['dispositivo']}) · {info['segundos_processamento']:.0f}s",
                        **{k: info[k] for k in ("modelo", "dispositivo") if k in info})
            else:
                s.etapa("transcricao", "falhou", "nenhuma fala reconhecida no áudio — o áudio "
                        "fica guardado; confira o microfone e a saída de som")
            d = info.get("diarizacao") or {}
            s.etapa("falantes", {"falhou": "falhou", "ok": "ok"}.get(d.get("status"), "pulada"),
                    d.get("detalhe") or d.get("motivo") or
                    f"{d.get('falantes', 1)} remoto(s) · {d.get('modo', '—')}")
            if a is not None:
                _backup_ata(s)
            a = None
        if a is None:
            a = _ata.base(s, segs, cfg.get("meu_nome", "Pedro"))
            a["lacunas"] = _ata.lacunas(a)
        # backup antes de qualquer coisa que dependa de rede ou de outro programa
        s.caminho("ata.md").write_text(render.markdown(a, segs), encoding="utf-8")
        _salvar_ata(s, a)

        # ── estrutura (Claude) ──
        quer = cfg.get("estruturar", True) if estruturar is None else estruturar
        if not quer:
            if a.get("status") == "pendente":
                s.etapa("estrutura", "pulada", "desligada — rode /ata depois")
        elif a.get("status") == "pendente" or "estrutura" in forcar:
            if a.get("status") != "pendente":
                _backup_ata(s)
            r = _rodar(s, "estrutura", lambda: _estr.estruturar(s, segs, cfg, log), log)
            if r is not None:
                a, motivo = r
                if motivo:
                    s.etapa("estrutura", "pulada", motivo)
                else:
                    c = _ata.contagem(a)
                    s.etapa("estrutura", "ok",
                            f"{c['decisoes']} decisões · {c['encaminhamentos']} encaminhamentos"
                            f" · {c['nao_verificados']} sem origem · {c['lacunas']} lacunas",
                            custo_usd=(a.get("gerado") or {}).get("custo_usd"))
                _salvar_ata(s, a)

        # ── páginas e PDF ──
        renderizar(s, a, segs, log)

        # ── publicação (só cliente, só por decisão do Pedro) ──
        if publicar_ is not False:
            _rodar(s, "publicacao", lambda: _etapa_publicacao(s, a, cfg, log, publicar_), log)

        # ── Raio-X da fala (interno) ──
        rx = {"m": None}
        if s.m.get("legado"):
            s.etapa("raio_x", "pulada", "reunião anterior à v2 já está no histórico")
        elif voce_a_confirmar(s):
            s.etapa("raio_x", "pendente", VOCE_PENDENTE)
        elif segs:
            def _rx():
                # o .pcm ainda existe aqui (a etapa de áudio vem depois); depois, vale o .opus
                mic = s.audio_da_voz()
                av = _aval.mais_recente(s)
                r = analise_fala.processar(segs, s.m.get("titulo"), s.m.get("inicio") or "",
                                           tipo=s.tipo, sessao_id=s.id, audio_mic=mic,
                                           metas=cfg.get("metas_fala"),
                                           participantes=s.participantes_remotos(),
                                           formato=s.m.get("formato"),
                                           avaliacao_md=av.read_text(encoding="utf-8") if av else None)
                rx["m"] = r.get("metrics")
                s.etapa("raio_x", "ok", "nota do Sinapse atualizada" if r.get("vault")
                        else "vault não encontrado nesta máquina")
            _rodar(s, "raio_x", _rx, log)

        # ── áudio: PCM → Opus conferido; retenção das antigas ──
        def _aud():
            feitos = audio.aposentar_pcm(s)
            dias = cfg.get("audio_reter_dias", 30)
            if feitos:
                s.etapa("audio", "ok", " · ".join(f"{k} {v['mb']} MB" for k, v in feitos.items())
                        + f" · guardado {dias} dias depois da ata pronta", retencao_dias=dias)
            elif s.status_etapa("audio") != "ok":
                s.etapa("audio", "pulada", "sem PCM para compactar")
            limpas = audio.limpar_expirados(
                [x for x in listar(s.pasta.parent) if x.id != s.id and ata_garantida(x)], dias)
            if limpas:
                log(f"  Retenção: áudio apagado de {len(limpas)} reunião(ões) antiga(s)")
        if not s.m.get("legado"):
            _rodar(s, "audio", _aud, log)

        # ── avaliação interna (v2.1): afirmações conferidas, valores, negociação, postura ──
        # Só reunião de cliente/Parresia com ata estruturada; nunca vai ao entregável.
        if (a.get("status") in ("estruturada", "revisada") and _aval.deve_avaliar(s, segs, cfg)
                and voce_a_confirmar(s)):
            s.etapa("avaliacao", "pendente", VOCE_PENDENTE)
        elif (a.get("status") in ("estruturada", "revisada") and _aval.deve_avaliar(s, segs, cfg)
                and (s.status_etapa("avaliacao") != "ok" or "avaliacao" in forcar)):
            def _av():
                caminho, meta = _aval.avaliar(s, segs, a, rx["m"], cfg, log)
                analise_fala.pagina_da_reuniao(s.id, caminho.read_text(encoding="utf-8"))
                s.etapa("avaliacao", "ok", f"{caminho.name} · {meta['segundos']:.0f}s",
                        custo_usd=meta.get("custo_usd"))
            _rodar(s, "avaliacao", _av, log)

        falhas = [k for k, v in s.m["etapas"].items() if v.get("status") == "falhou"]
        s.m["processado_em"] = agora_iso()
        s.estado("pronto" if not falhas else "pronto_com_falhas")
    return s.m["etapas"]


def reaplicar(s, cfg=None, log=print, publicar_=None):
    """Depois de editar ata.json (nomes, itens): audita de novo, renderiza e, se a página
    do cliente já estiver no ar, atualiza (mesma URL, mesma senha)."""
    cfg = cfg or _config.carregar()
    segs, a = carregar(s)
    if a is None:
        raise RuntimeError("esta sessão ainda não tem ata.json")
    a["_remotos"] = s.participantes_remotos()
    _ata.auditar(a, segs)
    a.pop("_remotos", None)
    _salvar_ata(s, a)
    renderizar(s, a, segs, log)
    if publicar_ is not False:
        _rodar(s, "publicacao", lambda: _etapa_publicacao(s, a, cfg, log, publicar_), log)
    return a
