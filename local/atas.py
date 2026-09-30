# -*- coding: utf-8 -*-
"""
Atas — linha de comando. É a interface do /ata (Claude) e o plano B da janela.

    python atas.py gravar                 grava pelo terminal (a janela é o app.py)
    python atas.py retomar                processa gravações interrompidas
    python atas.py processar <id|ultima>  [--sem-claude] [--sem-publicar] [--forcar transcricao,estrutura]
    python atas.py listar                 [--tipo T] [--projeto P] [-n 20]
    python atas.py mostrar <id|ultima>    a ata, as lacunas e as etapas
    python atas.py buscar <termo>         [--pessoa X] [--projeto P] [--tipo T]
    python atas.py anterior <id>          a reunião anterior do mesmo projeto
    python atas.py falantes <id> "Participante 1=Valter" ["Participante 2=Valter" ...]
    python atas.py confirmar <id>         aceita os nomes deduzidos e marca a ata como revisada
    python atas.py render <id>            reaudita e regera .md/.html/.pdf (e republica se já publicada)
    python atas.py decisoes <id>          as decisões no formato do log (decisoes.jsonl)
    python atas.py publicar <id>          publica (só cliente; decisão do Pedro) [--forcar]
    python atas.py tipo <id> <tipo>       corrige/confirma o tipo [--projeto P]; interno tira do ar
    python atas.py legado-proteger        plano para as atas da v1 no ar [--aplicar]
    python atas.py despublicar <id>       apaga a página do Worker
    python atas.py publicadas             o que está no Worker
    python atas.py abrir <id> [arquivo]   Explorer na pasta, com o arquivo selecionado
    python atas.py ao-vivo                caminho da transcrição ao vivo da gravação em curso
    python atas.py calibrar <id>          diarização com vários limiares no áudio guardado
    python atas.py importar-legado        traz as atas soltas de antes da v2
    python atas.py limpar-audio           aplica a retenção do áudio

<id> aceita o id completo, um prefixo único ou "ultima".
"""
import argparse
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import ata as _ata  # noqa: E402
import config as _config  # noqa: E402
import sessao as _sessao  # noqa: E402
from sessao import TIPOS, Sessao  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def achar(ref):
    todas = _sessao.listar()
    if ref in (None, "", "ultima", "última"):
        s = _sessao.ultima()
        if not s:
            sys.exit("nenhuma reunião ainda")
        return s
    exatas = [s for s in todas if s.id == ref]
    if exatas:
        return exatas[0]
    cands = [s for s in todas if s.id.startswith(ref) or ref in s.id]
    if len(cands) == 1:
        return cands[0]
    if not cands:
        sys.exit(f"nenhuma reunião casa com {ref!r}")
    sys.exit("mais de uma reunião casa: " + ", ".join(s.id for s in cands[:8]))


def _ata_de(s):
    import pipeline
    segs, a = pipeline.carregar(s)
    return segs, a


# ── comandos ─────────────────────────────────────────────────────────────────
def c_listar(a):
    for s in _sessao.listar()[-a.n:]:
        if a.tipo and s.tipo != a.tipo:
            continue
        if a.projeto and a.projeto.lower() not in (s.m.get("projeto") or "").lower():
            continue
        at = _sessao.ler_json(s.caminho("ata.json")) or {}
        st = at.get("status", "—")
        print(f"{s.id:<55} {TIPOS.get(s.tipo, s.tipo):<18} {s.m.get('projeto') or '':<22} "
              f"{s.m.get('estado'):<17} ata:{st}")


def c_mostrar(a):
    s = achar(a.id)
    segs, at = _ata_de(s)
    print(f"# {s.m.get('titulo')}\n{s.resumo_curto()} · {s.m.get('projeto') or 'sem projeto'}"
          f" · estado {s.m.get('estado')}\npasta: {s.pasta}\n")
    if at:
        from render import markdown
        md = markdown(at, segs)
        corte = md.find("## Transcrição")
        print(md[:corte] if corte > 0 else md)
        if a.transcricao:
            print(md[corte:])
    print("## Etapas")
    for k in _sessao.ETAPAS:
        v = (s.m.get("etapas") or {}).get(k)
        if v:
            print(f"- {k}: {v['status']}{' — ' + v['detalhe'] if v.get('detalhe') else ''}")
    for av in s.m.get("avisos") or []:
        print(f"- aviso: {av}")
    pub = s.m.get("publicacao") or {}
    if pub.get("url"):
        protecao = ("link da v1, SEM senha nem prazo" if pub.get("legado")
                    else "senha guardada no sessao.json")
        print(f"- publicada: {pub['url']} ({protecao})"
              + (f" · expira {pub['expira_em'][:10]}" if pub.get("expira_em") else ""))


def c_buscar(a):
    termo = _ata.norm(a.termo)
    for s in _sessao.listar():
        if a.tipo and s.tipo != a.tipo:
            continue
        if a.projeto and a.projeto.lower() not in (s.m.get("projeto") or "").lower():
            continue
        segs, at = _ata_de(s)
        at = at or {}
        nomes = _ata.nomes_por_rotulo(at)
        if a.pessoa:
            p = _ata.norm(a.pessoa)
            pessoas = [_ata.norm(x) for x in (s.m.get("participantes") or [])] + \
                      [_ata.norm(x) for x in nomes.values()]
            if not any(p in x for x in pessoas):
                continue
        achados = []
        for lista, _ in _ata.LISTAS:
            for it in at.get(lista, []):
                texto = " ".join(str(it.get(k) or "") for k in
                                 ("decisao", "acao", "pergunta", "risco", "contexto", "dono", "quem"))
                if termo in _ata.norm(texto):
                    achados.append(f"  {it['id']} [{it.get('t')}] "
                                   f"{it.get('decisao') or it.get('acao') or it.get('pergunta') or it.get('risco')}")
        if not achados and not a.so_ata:
            for f in _ata.falas(segs):
                if termo in _ata.norm(f["text"]):
                    achados.append(f"  [{_ata.fmt_t(f['start'])}] {nomes.get(f['speaker'], f['speaker'])}: "
                                   f"{f['text'][:160]}")
                    if len(achados) >= 5:
                        break
        if achados:
            print(f"{s.id} · {TIPOS.get(s.tipo)} · {s.m.get('projeto') or ''}")
            print("\n".join(achados))


def c_anterior(a):
    s = achar(a.id)
    proj = s.m.get("projeto")
    pessoas = set(s.m.get("participantes") or [])
    antes = [x for x in _sessao.listar() if (x.m.get("inicio") or "") < (s.m.get("inicio") or "")
             and x.id != s.id]
    mesmo = [x for x in antes if proj and x.m.get("projeto") == proj] or \
            [x for x in antes if pessoas & set(x.m.get("participantes") or [])]
    if not mesmo:
        print("nenhuma reunião anterior do mesmo projeto ou com as mesmas pessoas")
        return
    print(mesmo[-1].id)


def c_falantes(a):
    s = achar(a.id)
    segs, at = _ata_de(s)
    if not at:
        sys.exit("sem ata.json")
    pares = {}
    for par in a.pares:
        if "=" not in par:
            sys.exit(f"use 'Rótulo=Nome': {par!r}")
        r, n = par.split("=", 1)
        pares[r.strip()] = n.strip()
    rotulos = {p["rotulo"] for p in at["participantes"]}
    for r in pares:
        if r not in rotulos:
            sys.exit(f"rótulo {r!r} não existe nesta ata ({', '.join(sorted(rotulos))})")
    for p in at["participantes"]:
        if p["rotulo"] in pares:
            p.update({"nome": pares[p["rotulo"]], "origem": "pedro", "confirmado": True})
    _sessao.escrever_json(s.caminho("ata.json"), at)
    _reaplicar(s, a)


def c_confirmar(a):
    s = achar(a.id)
    segs, at = _ata_de(s)
    for p in at["participantes"]:
        if p.get("nome"):
            p["confirmado"] = True
    at["status"] = "revisada"
    at["revisado"] = {"em": _sessao.agora_iso(), "por": "pedro"}
    _sessao.escrever_json(s.caminho("ata.json"), at)
    _reaplicar(s, a)


def _reaplicar(s, a):
    import pipeline
    at = pipeline.reaplicar(s, publicar_=not getattr(a, "sem_publicar", False))
    c = _ata.contagem(at)
    print(f"ok · {c['lacunas']} lacunas · {c['nao_verificados']} sem origem · {s.caminho('ata.html')}")


def c_render(a):
    _reaplicar(achar(a.id), a)


def c_decisoes(a):
    s = achar(a.id)
    _, at = _ata_de(s)
    for d in (at or {}).get("decisoes", []):
        if d.get("verificado") is False:
            continue
        print(json.dumps(_ata.decisao_para_log(at, d), ensure_ascii=False))


def c_processar(a):
    import pipeline
    s = achar(a.id)
    forcar = tuple(x.strip() for x in (a.forcar or "").split(",") if x.strip())
    et = pipeline.processar(s, log=print, forcar=forcar,
                            estruturar=False if a.sem_claude else None,
                            publicar_=False if a.sem_publicar else None)
    _imprimir_etapas(s, et)


def _imprimir_etapas(s, et):
    print(f"\n{s.id} → {s.m.get('estado')}")
    for k in _sessao.ETAPAS:
        v = et.get(k)
        if v:
            marca = {"ok": "✓", "falhou": "✗", "pulada": "–", "pendente": "○"}.get(v["status"], "?")
            print(f"  {marca} {k:<11} {v.get('detalhe', '')}")
    pub = s.m.get("publicacao") or {}
    if pub.get("url") and not pub.get("legado"):
        print(f"\n  Link: {pub['url']}  (senha no sessao.json)")
    print(f"  Pasta: {s.pasta}")


def c_retomar(a):
    import pipeline
    orf = _sessao.a_retomar()
    if not orf:
        print("nenhuma gravação interrompida nem etapa essencial falhada")
        return
    for s in orf:
        print(f"retomando {s.id} ({s.resumo_curto()})")
        if s.m.get("estado") == "gravando":
            s.m["audio"]["duracao_s"] = round(s.duracao_s(), 1)
            s.avisar("gravação interrompida (o processo parou sem encerrar); áudio "
                     "recuperado até o último bloco gravado")
            s.etapa("captura", "ok", f"recuperada após interrupção · {s.duracao_s():.0f}s")
            s.estado("gravado")
        _imprimir_etapas(s, pipeline.processar(s, log=print))


def c_publicar(a):
    import pipeline
    s = achar(a.id)
    try:
        pub = pipeline.publicar(s, _config.carregar(), forcar=a.forcar)
    except RuntimeError as e:
        sys.exit(f"não publicou: {e}")
    # a senha não vai para o terminal: está no sessao.json, e a janela tem o botão de copiar
    print(f"Link: {pub['url']}\nSenha: guardada em {s.caminho('sessao.json')} (publicacao.senha)")


def c_despublicar(a):
    import pipeline
    s = achar(a.id)
    r = pipeline.despublicar(s, _config.carregar(), "pedido do Pedro")
    if r is None:
        sys.exit("esta reunião não está publicada")
    print("apagada" if r.get("apagada") else f"o Worker não tinha a página ({r})")


def c_tipo(a):
    """Corrige/confirma tipo e projeto (as antigas vieram com classificação inferida)."""
    import pipeline
    s = achar(a.id)
    if a.tipo not in TIPOS:
        sys.exit(f"tipo inválido: use {', '.join(TIPOS)}")
    antes = s.tipo
    s.m["tipo"] = a.tipo
    if a.projeto is not None:
        s.m["projeto"] = a.projeto
    s.m["classificacao"] = "confirmada"
    s.salvar()
    print(f"{s.id}: {antes} -> {a.tipo}" + (f" · projeto {s.m['projeto']}" if a.projeto else ""))
    if _sessao.ler_json(s.caminho("ata.json")):
        pipeline.reaplicar(s)                    # tipo interno tira a página do ar


def c_legado_proteger(a):
    """As atas da v1 estão no Worker sem senha e sem prazo. Sem --aplicar só mostra o plano:
    interna (Parresia/carreira/pessoal) -> apagar; cliente -> senha nova + expiração."""
    import upload
    cfg = _config.carregar()
    plano = []
    for s in _sessao.listar():
        pub = s.m.get("publicacao") or {}
        if not (s.m.get("legado") and pub.get("legado") and pub.get("url")):
            continue
        rid = pub["url"].rstrip("/").split("/")[-1]
        acao = "apagar" if s.tipo not in _sessao.TIPOS_PUBLICAVEIS else "proteger"
        plano.append((s, rid, acao))
        print(f"  {acao:<9} {TIPOS.get(s.tipo):<18} {s.m.get('classificacao', '?'):<10} {s.id}")
    n_ap = sum(1 for p in plano if p[2] == "apagar")
    print(f"{len(plano)} ata(s) da v1 no ar · apagar {n_ap} · proteger {len(plano) - n_ap}")
    if not a.aplicar:
        print("(nada foi feito — rode com --aplicar para executar)")
        return
    for s, rid, acao in plano:
        if acao == "apagar":
            upload.apagar(cfg["worker_url"], cfg["upload_token"], rid)
            s.m["publicacao"] = {"apagada_em": _sessao.agora_iso(), "id": rid,
                                 "motivo": "ata interna da v1"}
        else:
            senha = upload.gerar_senha()
            upload._pedido("PATCH", cfg["worker_url"].rstrip("/") + f"/api/atas/{rid}",
                           cfg["upload_token"],
                           {"senha": senha, "expira_dias": cfg.get("publicacao_reter_dias", 90)})
            s.m["publicacao"].update({"senha": senha, "protegida_em": _sessao.agora_iso()})
        s.salvar()
    print("feito")
    print("apagada" if r.get("apagada") else f"o Worker não tinha a página ({r})")


def c_publicadas(a):
    import upload
    cfg = _config.carregar()
    for x in upload.listar(cfg["worker_url"], cfg["upload_token"]).get("atas", []):
        print(f"{x['id']}  {x['data'][:10]}  senha:{'sim' if x['tem_senha'] else 'NÃO'}  "
              f"expira:{(x.get('expira_em') or 'nunca')[:10]}  {'v1 ' if x['legado'] else ''}"
              f"{x['titulo']}")


def abrir_no_explorer(caminho):
    """Regra do Pedro: 'abrir' = Explorer na pasta com o arquivo selecionado."""
    p = pathlib.Path(caminho).resolve()
    if p.is_dir():
        subprocess.Popen(["explorer.exe", str(p)])
    else:
        subprocess.Popen(f'explorer.exe /select,"{p}"')


def c_abrir(a):
    s = achar(a.id)
    alvo = s.caminho(a.arquivo) if a.arquivo else (
        next((s.caminho(n) for n in ("entregavel.pdf", "ata.pdf", "ata.html", "ata.md")
              if s.caminho(n).exists()), s.pasta))
    abrir_no_explorer(alvo)
    print(alvo)


def c_ao_vivo(a):
    grav = [s for s in _sessao.listar() if s.m.get("estado") == "gravando" and not s.orfa()]
    if not grav:
        print("nenhuma gravação em curso")
        return
    p = grav[-1].caminho("ao-vivo.md")
    print(p if p.exists() else f"{p} (ainda não existe: ao vivo desligado ou sem fala)")


def c_calibrar(a):
    import audio
    import tempfile
    import transcribe
    cfg = _config.carregar()
    s = achar(a.id)
    fonte = audio.fonte_audio(s, "loop")
    if not fonte:
        sys.exit("sem áudio do loopback guardado nesta reunião")
    tmp = pathlib.Path(tempfile.mkdtemp()) / "loop.wav"
    audio.escrever_wav(tmp, audio.ler_audio(fonte))
    print(f"{s.id} · participantes informados: {s.participantes_remotos() or 'nenhum'}")
    for thr in [float(x) for x in a.limiares.split(",")]:
        r = transcribe._diarizar(tmp, thr, -1, cfg.get("diar_max_falantes", 6), cfg.get("diar_python"))
        print(f"  limiar {thr:.2f}: agrupamento bruto {r.get('brutos'):>3} → {r['falantes']} "
              f"falante(s) ({r.get('modo')})")
    tmp.unlink(missing_ok=True)


def c_importar(a):
    import legado
    feitos = legado.importar()
    print(f"{len(feitos)} ata(s) importada(s)")


def c_limpar(a):
    import audio
    import pipeline
    cfg = _config.carregar()
    garantidas = [s for s in _sessao.listar() if pipeline.ata_garantida(s)]
    limpas = audio.limpar_expirados(garantidas, cfg.get("audio_reter_dias", 30))
    print(f"áudio apagado de {len(limpas)} reunião(ões)")


# ── gravação pelo terminal ───────────────────────────────────────────────────
def c_gravar(a):
    import pipeline
    import record
    cfg = _config.carregar()
    print("=" * 56 + "\n  ATAS — gravador de reunião\n" + "=" * 56)
    print("\n  Lembrete: avise que está gravando.\n")
    titulo = input("  Título: ").strip()
    tipos = list(TIPOS)
    print("  Tipo: " + "  ".join(f"[{i + 1}] {TIPOS[t]}" for i, t in enumerate(tipos)))
    esc = input("  Tipo (1-4): ").strip()
    tipo = tipos[int(esc) - 1] if esc.isdigit() and 1 <= int(esc) <= 4 else "pessoal"
    projeto = input("  Projeto (opcional): ").strip()
    part = [p.strip() for p in input("  Quem vai falar do outro lado (vírgulas): ").split(",")
            if p.strip()]
    s = Sessao.criar(titulo, tipo, projeto, part)
    disp = record.escolher_dispositivos(cfg.get("microfone"))
    print(f"\n  Microfone: {disp['mic'].name}\n  Chamada  : "
          f"{disp['loop'].name if disp['loop'] else '(nenhuma)'}")
    for av in disp["avisos"]:
        print(f"  ⚠ {av}")
    niv = record.medir_niveis(disp)
    if not niv["mic"]["ok"]:
        print("  ⚠ seu microfone está mudo")
    if not niv["loop"]["ok"]:
        print("  (a chamada está em silêncio — normal se ainda não começou)")
    g = record.Gravador(s, disp)
    g.iniciar()
    try:
        input("\n  >>> GRAVANDO — ENTER para parar.\n")
    except (KeyboardInterrupt, EOFError):
        pass
    g.parar()
    _imprimir_etapas(s, pipeline.processar(s, cfg, log=print))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="atas", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gravar").set_defaults(fn=c_gravar)
    sub.add_parser("retomar").set_defaults(fn=c_retomar)
    p = sub.add_parser("processar")
    p.add_argument("id", nargs="?", default="ultima")
    p.add_argument("--sem-claude", action="store_true")
    p.add_argument("--sem-publicar", action="store_true")
    p.add_argument("--forcar", default="")
    p.set_defaults(fn=c_processar)
    p = sub.add_parser("listar")
    p.add_argument("--tipo")
    p.add_argument("--projeto")
    p.add_argument("-n", type=int, default=30)
    p.set_defaults(fn=c_listar)
    p = sub.add_parser("mostrar")
    p.add_argument("id", nargs="?", default="ultima")
    p.add_argument("--transcricao", action="store_true")
    p.set_defaults(fn=c_mostrar)
    p = sub.add_parser("buscar")
    p.add_argument("termo")
    p.add_argument("--pessoa")
    p.add_argument("--projeto")
    p.add_argument("--tipo")
    p.add_argument("--so-ata", action="store_true", help="não procurar na transcrição")
    p.set_defaults(fn=c_buscar)
    p = sub.add_parser("anterior")
    p.add_argument("id", nargs="?", default="ultima")
    p.set_defaults(fn=c_anterior)
    p = sub.add_parser("falantes")
    p.add_argument("id")
    p.add_argument("pares", nargs="+")
    p.add_argument("--sem-publicar", action="store_true")
    p.set_defaults(fn=c_falantes)
    for nome, fn in (("confirmar", c_confirmar), ("render", c_render)):
        p = sub.add_parser(nome)
        p.add_argument("id", nargs="?", default="ultima")
        p.add_argument("--sem-publicar", action="store_true")
        p.set_defaults(fn=fn)
    for nome, fn in (("decisoes", c_decisoes), ("despublicar", c_despublicar)):
        p = sub.add_parser(nome)
        p.add_argument("id", nargs="?", default="ultima")
        p.set_defaults(fn=fn)
    p = sub.add_parser("publicar")
    p.add_argument("id", nargs="?", default="ultima")
    p.add_argument("--forcar", action="store_true", help="republicar página já apagada")
    p.set_defaults(fn=c_publicar)
    p = sub.add_parser("tipo")
    p.add_argument("id")
    p.add_argument("tipo")
    p.add_argument("--projeto")
    p.set_defaults(fn=c_tipo)
    p = sub.add_parser("legado-proteger")
    p.add_argument("--aplicar", action="store_true")
    p.set_defaults(fn=c_legado_proteger)
    sub.add_parser("publicadas").set_defaults(fn=c_publicadas)
    p = sub.add_parser("abrir")
    p.add_argument("id", nargs="?", default="ultima")
    p.add_argument("arquivo", nargs="?")
    p.set_defaults(fn=c_abrir)
    sub.add_parser("ao-vivo").set_defaults(fn=c_ao_vivo)
    p = sub.add_parser("calibrar")
    p.add_argument("id")
    p.add_argument("--limiares", default="0.5,0.6,0.7,0.8,0.9,0.95")
    p.set_defaults(fn=c_calibrar)
    sub.add_parser("importar-legado").set_defaults(fn=c_importar)
    sub.add_parser("limpar-audio").set_defaults(fn=c_limpar)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
