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
    python atas.py formato <id> <f>       formato da reunião de cliente: descoberta, demo, alinhamento, nenhum
    python atas.py legado-proteger        plano para as atas da v1 no ar [--aplicar]
    python atas.py despublicar <id>       apaga a página do Worker
    python atas.py publicadas             o que está no Worker
    python atas.py abrir <id> [arquivo]   Explorer na pasta, com o arquivo selecionado
    python atas.py ao-vivo                caminho da transcrição ao vivo da gravação em curso
    python atas.py fala <id|ultima>       Raio-X da Fala: ritmo, turnos, cansaço, voz e metas [--sem-abrir]
    python atas.py fala --recalcular [--saida PASTA]   refaz o Raio-X das reuniões com as regras atuais (sem vault)
    python atas.py calibrar <id>          diarização com vários limiares no áudio guardado
    python atas.py importar-legado        traz as atas soltas de antes da v2
    python atas.py limpar-audio           aplica a retenção do áudio

<id> aceita o id completo, um prefixo único ou "ultima".
"""
import argparse
import json
import os
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
    extra = ""
    if s.tipo == "cliente":
        extra += f" · formato {s.m.get('formato') or '— (não informado)'}"
    print(f"# {s.m.get('titulo')}\n{s.resumo_curto()} · {s.m.get('projeto') or 'sem projeto'}"
          f" · estado {s.m.get('estado')}{extra}\npasta: {s.pasta}\n")
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
    # None = só atualiza a página se ela JÁ estiver no ar; publicar pela primeira vez é só `atas.py publicar`.
    # Era `not sem_publicar` (= True = pedido explícito): render/falantes/confirmar publicavam sozinhos (06/10/2026).
    at = pipeline.reaplicar(s, publicar_=False if getattr(a, "sem_publicar", False) else None)
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


def c_formato(a):
    """Corrige o formato da reunião (descoberta/demo/alinhamento; "nenhum" apaga). Só muda a
    leitura do Raio-X em reunião de cliente: a faixa da fatia de fala e as perguntas abertas."""
    s = achar(a.id)
    novo = None if a.formato in ("nenhum", "nao-sei", "não-sei") else a.formato
    if novo is not None and novo not in _sessao.FORMATOS:
        sys.exit(f"formato inválido: use {', '.join(_sessao.FORMATOS)} ou nenhum")
    antes = s.m.get("formato")
    s.m["formato"] = novo
    s.salvar()
    print(f"{s.id}: formato {antes or '—'} -> {novo or '—'}")
    if s.tipo != "cliente":
        print(f"  (a reunião é {TIPOS.get(s.tipo, s.tipo)}: o formato só pesa no Raio-X de cliente)")
    if s.status_etapa("raio_x") == "ok" and not a.sem_raio_x:
        raio_x(s)
        print("  Raio-X refeito com o formato novo (atas.py fala <id> mostra a leitura)")


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


def raio_x(s, cfg=None, log=print):
    """(Re)calcula o Raio-X da Fala de uma sessão: palavras, ritmo, turnos, cansaço, voz e metas.
    Usa o .pcm se ainda existir, senão o mic.opus guardado. Devolve o resultado de processar()."""
    import analise_fala
    import config as _config
    cfg = cfg or _config.carregar()
    segs, _ = _ata_de(s)
    if not segs:
        raise SystemExit("esta sessão não tem transcrição")
    import avaliar
    mic = s.mic_pcm if s.mic_pcm.exists() else s.caminho("audio") / "mic.opus"
    av = avaliar.mais_recente(s)                 # a página da reunião traz a postura da avaliação
    if av and not av.with_suffix(".html").exists():
        avaliar.escrever_html(s, av)
    r = analise_fala.processar(segs, s.m.get("titulo"), s.m.get("inicio") or "", tipo=s.tipo,
                               sessao_id=s.id, audio_mic=mic, metas=cfg.get("metas_fala"),
                               avaliacao_md=av.read_text(encoding="utf-8") if av else None,
                               participantes=s.participantes_remotos(), formato=s.m.get("formato"))
    s.etapa("raio_x", "ok", "nota do Sinapse atualizada" if r.get("vault") else "vault não encontrado")
    return r


def _imprimir_leitura(m):
    """Cada medida com a leitura: onde você ficou, a faixa, a mediana das últimas 5 e o que fazer."""
    marca = {"ok": "✓", "fora": "!", "info": "·", "pequena": "·"}
    if any(it["status"] == "pequena" for it in m.get("leitura") or []):
        print(f"  (amostra pequena: {m.get('palavras_voce')} palavras suas, menos de 1.000 — nenhuma meta julgada)")
    for it in m.get("leitura") or []:
        print(f"  {marca[it['status']]} {it['nome']}: {it['valor_txt']} — faixa {it['faixa']}")
        print(f"      {it['onde']}. {it['mediana_txt'][:1].upper() + it['mediana_txt'][1:]}.")
        if it["status"] == "fora" and it["dica"]:
            print(f"      O que fazer: {it['dica']}")


def c_fala(a):
    """O Raio-X da Fala de uma reunião: imprime a leitura das medidas e abre a página."""
    if a.recalcular:
        return c_fala_recalcular(a)
    if not a.id:
        raise SystemExit("informe a reunião (id ou ultima) ou use --recalcular")
    s = achar(a.id)
    r = raio_x(s)
    m = r["metrics"]
    print(f"Raio-X da Fala · {s.m.get('titulo')} · {m['dur_min']} min")
    if m.get("leitura"):
        _imprimir_leitura(m)
    else:
        for nome, val, meta, ok in m["metas"]:
            print(f"  {'·' if ok is None else '✓' if ok else '!'} {nome}: {val} (meta {meta})")
    if m.get("voz"):
        import analise_fala
        itens, evolucao = analise_fala.leitura_voz(m["voz"])
        for it in itens:
            print(f"  · {it['nome']}: {it['valor']} {it['unidade']} = {it['zona']}"
                  + (f" ({it['efeito']})" if it["efeito"] else ""))
        for t in evolucao:
            print(f"  · {t}")
    if m.get("blocos"):
        print("  · Ao longo da reunião (muleta pura/1k): "
              + " → ".join(str(b.get("muleta_pura_por_1000", b["muletas_por_1000"])) for b in m["blocos"]))
    print(f"\npágina: {r['pagina']}\npainel: {r['dashboard']}")
    if not a.sem_abrir:
        for alvo in (r["pagina"],):
            try:
                os.startfile(str(alvo))          # a página da reunião, no navegador
            except (AttributeError, OSError):
                pass


def _resumo_fala(m):
    """As medidas do Raio-X numa linha cada, lendo linha antiga (v2) e nova (v3): antes × depois."""
    import analise_fala as af
    r, p = m.get("ritmo") or {}, m.get("postura") or {}
    pura, aprox = af.valor_de(m, "muleta_pura_por_1000")
    fatia = next((it["faixa"].split(" (")[0] for it in m.get("leitura") or [] if it["chave"] == "share_fala"),
                 "35% a 55%")
    metas = m.get("metas", [])
    return {
        "palavras suas": m.get("palavras_voce"),
        "fatia (faixa)": f"{m.get('share_fala', 0) * 100:.0f}% ({fatia})",
        "muletas/1k (todas)": m.get("muletas_por_1000"),
        "muleta pura/1k": f"{af._br(pura)}{' (aprox.)' if aprox else ''}",
        "marcador/1k": m.get("marcador_por_1000", "—"),
        "aí/1k": af._br(af.valor_de(m, "ai_por_1000")[0]),
        "a gente/1k": p.get("a_gente_por_1000", "—"),
        "confirmações/min": m.get("conf_por_min"),
        "tomou a vez / apoio (sobrepos.)": (f"{r.get('tomou_vez')} / {r.get('apoio')} ({r.get('interrompeu')})"
                                            if "tomou_vez" in r else f"— ({r.get('interrompeu', '—')})"),
        "ppm": r.get("ppm", "—"),
        "sílabas/s · articulação": (f"{r.get('silabas_por_s')} · {r.get('articulacao_sil_s')}"
                                    if "silabas_por_s" in r else "—"),
        "resposta s · atropelo": (f"{r.get('resposta_media_s')} · {r.get('atropelo_pct')}%"
                                  if "atropelo_pct" in r else f"{r.get('resposta_media_s', '—')} · —"),
        "perguntas abertas / sim-não": (f"{r.get('perguntas_abertas')} / {r.get('perguntas_fechadas')}"
                                        if "perguntas_abertas" in r else f"{r.get('perguntas_reais', '—')} (total)"),
        "compromisso dono+prazo": (f"{m['compromissos']['completos']} de {m['compromissos']['total']}"
                                   if m.get("compromissos") else "—"),
        "metas batidas": (f"{sum(1 for x in metas if x[3] is True)} de {sum(1 for x in metas if x[3] is not None)}"
                          + (" (amostra pequena)" if any(x[3] is None for x in metas) else "")),
    }


def c_fala_recalcular(a):
    """Reprocessa as reuniões já analisadas com as regras atuais do Raio-X, SEM tocar no vault do
    Sinapse: regrava só o histórico e as páginas em --saida (padrão: fala-analise/). Com --saida
    noutra pasta, copia o histórico para lá antes e não mexe no de verdade. A voz não é medida de
    novo (as regras dela não mudaram): vem da linha antiga. Reuniões legadas (importadas da v1, sem
    tempos confiáveis) ficam como estão. Não grava nada na pasta da reunião. Imprime antes × depois."""
    import shutil
    import analise_fala as af
    import avaliar
    import config as _config
    cfg = _config.carregar()
    saida = pathlib.Path(a.saida).resolve() if a.saida else af.FALA_DIR.resolve()
    saida.mkdir(parents=True, exist_ok=True)
    antes = {r.get("id"): r for r in af.ler_historico(af.FALA_DIR)}
    if saida != af.FALA_DIR.resolve() and (af.FALA_DIR / "historico.jsonl").exists():
        shutil.copyfile(af.FALA_DIR / "historico.jsonl", saida / "historico.jsonl")
    alvo = [s for s in _sessao.listar() if not s.m.get("legado") and s.caminho("transcricao.json").exists()]
    if a.id:
        alvo = [s for s in alvo if a.id in s.id]
    for s in alvo:
        segs, _ = _ata_de(s)
        if not segs:
            continue
        velho = antes.get(s.id)
        av = avaliar.mais_recente(s)
        voz_antiga = ((velho or {}).get("metrics") or {}).get("voz")
        r = af.processar(segs, s.m.get("titulo"), s.m.get("inicio") or "", pasta=saida, tipo=s.tipo,
                         sessao_id=s.id, vault=False, metas=cfg.get("metas_fala"),
                         avaliacao_md=av.read_text(encoding="utf-8") if av else None,
                         participantes=s.participantes_remotos(), formato=s.m.get("formato"),
                         voz_pronta=voz_antiga if voz_antiga is not None else {})
        print(f"\n{s.id}  ({s.tipo})")
        novo = _resumo_fala(r["metrics"])
        velho_r = _resumo_fala(velho["metrics"]) if velho else {}
        for k, v in novo.items():
            print(f"  {k:<32} {str(velho_r.get(k, '—')):<34} → {v}")
    print(f"\nhistórico e páginas em: {saida} (o vault do Sinapse não foi tocado)")


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
    p = sub.add_parser("formato", help="formato da reunião de cliente (Raio-X): descoberta, demo, alinhamento ou nenhum")
    p.add_argument("id")
    p.add_argument("formato")
    p.add_argument("--sem-raio-x", action="store_true", help="não refazer o Raio-X agora")
    p.set_defaults(fn=c_formato)
    p = sub.add_parser("legado-proteger")
    p.add_argument("--aplicar", action="store_true")
    p.set_defaults(fn=c_legado_proteger)
    sub.add_parser("publicadas").set_defaults(fn=c_publicadas)
    p = sub.add_parser("abrir")
    p.add_argument("id", nargs="?", default="ultima")
    p.add_argument("arquivo", nargs="?")
    p.set_defaults(fn=c_abrir)
    sub.add_parser("ao-vivo").set_defaults(fn=c_ao_vivo)
    p = sub.add_parser("fala", help="Raio-X da Fala da reunião (ritmo, turnos, cansaço, voz, metas)")
    p.add_argument("id", nargs="?")
    p.add_argument("--sem-abrir", action="store_true", help="só imprime, não abre o painel")
    p.add_argument("--recalcular", action="store_true",
                   help="reprocessa as reuniões antigas com as regras atuais (não escreve no vault)")
    p.add_argument("--saida", help="com --recalcular: pasta do histórico e das páginas (padrão: fala-analise/)")
    p.set_defaults(fn=c_fala)
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
