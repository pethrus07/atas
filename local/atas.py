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
    python atas.py formato <id> <f>       formato: cliente → descoberta, demo, alinhamento; parresia → daily; nenhum
    python atas.py daily <termo>          busca só nas dailies [--pessoa X] [--frente "Frota WP"] [--desde AAAA-MM-DD]
    python atas.py marcar <id> <mm:ss>... marca momentos depois da reunião [--remover]
    python atas.py marcas <id>            os momentos marcados e o que a ata achou em cada um
    python atas.py importar <áudio>       reunião presencial gravada no celular --titulo T [--tipo] [--projeto]
                                          [--participantes "A,B"] [--formato F] [--data "AAAA-MM-DD HH:MM"]
                                          [--marcas "12:30,40:10"]
    python atas.py vigiar <pasta>         importa os áudios novos da pasta (sem duplicar) [--continuo]
    python atas.py voz-referencia [<id>]  refaz a amostra da sua voz que acha "Você" no áudio do celular
    python atas.py legado-proteger        plano para as atas da v1 no ar [--aplicar]
    python atas.py despublicar <id>       apaga a página do Worker
    python atas.py publicadas             o que está no Worker
    python atas.py abrir <id> [arquivo]   Explorer na pasta, com o arquivo selecionado
    python atas.py ao-vivo                caminho da transcrição ao vivo da gravação em curso
    python atas.py fala <id|ultima>       Raio-X da Fala: ritmo, turnos, cansaço, voz e metas [--sem-abrir]
    python atas.py fala --recalcular [--saida PASTA]   refaz o Raio-X das reuniões com as regras atuais (sem vault)
    python atas.py calibrar <id>          diarização com vários limiares no áudio guardado [--daily]
    python atas.py importar-legado        traz as atas soltas de antes da v2
    python atas.py limpar-audio           aplica a retenção do áudio
    python atas.py treinar                treino de fala sozinho (só o microfone) [--tipo reuniao|tema|leitura]
                                          [--assunto A] [--nota <nome ou caminho>] [--duracao 180] [--alvo 4.8]
    python atas.py treino <áudio>         analisa um treino já gravado (ex.: do celular), mesmas opções
    python atas.py treinos                os treinos com a evolução [--tipo] [-n 20] [--manter <id>]

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
    elif s.tipo == "parresia":
        extra += (" · formato daily (fora da medição)" if _sessao.fora_da_medicao(s) else " · formato reunião")
    if s.celular:
        cel = s.m.get("celular") or {}
        extra += (" · áudio do celular, quem é \"Você\": "
                  + ("confirmado" if cel.get("voce_confirmado") else
                     f"A CONFIRMAR ({cel.get('evidencia') or 'ainda não processado'})"))
    print(f"# {s.m.get('titulo')}\n{s.resumo_curto()} · {s.m.get('projeto') or 'sem projeto'}"
          f" · estado {s.m.get('estado')}{extra}\npasta: {s.pasta}\n")
    if s.tipo == _sessao.TIPO_PENDENTE:
        print("TIPO PENDENTE: escolha com `atas.py tipo <id> <cliente|parresia|carreira|pessoal>` "
              "(até lá não há entregável, publicação nem avaliação)\n")
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
    if s.celular and _confirmar_voce_por_pares(s, pares):
        segs, at = _ata_de(s)                    # os rótulos podem ter trocado
    rotulos = {p["rotulo"] for p in at["participantes"]}
    for r in pares:
        if r not in rotulos:
            sys.exit(f"rótulo {r!r} não existe nesta ata ({', '.join(sorted(rotulos))})")
    for p in at["participantes"]:
        if p["rotulo"] in pares:
            p.update({"nome": pares[p["rotulo"]], "origem": "pedro", "confirmado": True})
    _sessao.escrever_json(s.caminho("ata.json"), at)
    _reaplicar(s, a)
    _depois_de_confirmar_voce(s)


def _confirmar_voce_por_pares(s, pares):
    """Áudio do celular: "Participante 2=Você" (ou =Pedro) diz qual rótulo é o Pedro; "Você=Você"
    confirma o palpite. Tira esses pares de `pares` e grava a confirmação. Devolve True se tratou."""
    eu = {"você", "voce", _config.carregar().get("meu_nome", "Pedro").lower()}
    alvo = [r for r, n in pares.items() if n.lower() in eu]
    if not alvo:
        return False
    if len(alvo) > 1:
        sys.exit("só um rótulo pode ser você: " + ", ".join(alvo))
    import celular
    r = alvo[0]
    del pares[r]
    try:
        mudou = celular.confirmar_voce(s, None if r == "Você" else r,
                                       _config.carregar().get("meu_nome", "Pedro"))
    except ValueError as e:
        sys.exit(str(e))
    print(f"você = {r}" + (" (rótulos trocados na transcrição)" if mudou else " (confirmado)"))
    if mudou and (_sessao.ler_json(s.caminho("ata.json")) or {}).get("status") in ("estruturada", "revisada"):
        print("  a ata foi montada com o palpite antigo: refaça com "
              f"`atas.py processar {s.id} --forcar estrutura,avaliacao`")
    return True


def _depois_de_confirmar_voce(s):
    """Com "Você" confirmado, o Raio-X que ficou pendente roda agora."""
    s = Sessao.abrir(s.pasta)
    if s.celular and (s.m.get("celular") or {}).get("voce_confirmado") \
            and s.status_etapa("raio_x") == "pendente":
        if raio_x(s) is not None:
            print("  Raio-X da fala calculado (atas.py fala <id> mostra a leitura)")


def c_confirmar(a):
    s = achar(a.id)
    segs, at = _ata_de(s)
    if s.celular and not (s.m.get("celular") or {}).get("voce_confirmado"):
        import celular
        if not any(x["speaker"] == "Você" for x in segs):
            sys.exit("áudio do celular sem \"Você\": diga qual rótulo é você com "
                     f"`atas.py falantes {s.id} \"Participante N=Você\"`")
        celular.confirmar_voce(s, None, _config.carregar().get("meu_nome", "Pedro"))
        segs, at = _ata_de(s)
    for p in at["participantes"]:
        if p.get("nome"):
            p["confirmado"] = True
    at["status"] = "revisada"
    at["revisado"] = {"em": _sessao.agora_iso(), "por": "pedro"}
    _sessao.escrever_json(s.caminho("ata.json"), at)
    _reaplicar(s, a)
    _depois_de_confirmar_voce(s)


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
    formato_antes = s.m.get("formato")
    if not _sessao.formato_valido(a.tipo, formato_antes):
        s.m["formato"] = None                    # formato de outro tipo (ex.: daily → cliente) não vaza
    s.salvar()
    print(f"{s.id}: {antes} -> {a.tipo}" + (f" · projeto {s.m['projeto']}" if a.projeto else ""))
    if formato_antes and s.m.get("formato") is None:
        print(f"  formato {formato_antes} não vale para {TIPOS.get(a.tipo, a.tipo)}: limpo")
        if formato_antes == _sessao.FORMATO_DAILY:
            print(f"  deixou de ser daily: a ata e o Raio-X saem com `atas.py processar {s.id} --forcar estrutura`")
    if _sessao.ler_json(s.caminho("ata.json")):
        pipeline.reaplicar(s)                    # tipo interno tira a página do ar
    if antes == _sessao.TIPO_PENDENTE:
        # áudio do celular importado sem tipo: o Raio-X muda a leitura (a fatia depende do tipo)
        if s.status_etapa("raio_x") == "ok":
            raio_x(s)
        if a.tipo in ("cliente", "parresia"):
            print(f"  avaliação interna: `atas.py processar {s.id} --forcar avaliacao`")
        if a.tipo == "cliente":
            print("  entregável pronto para revisar; publicar continua sendo decisão sua (`publicar`)")


def c_formato(a):
    """Corrige o formato da reunião, que vale por tipo (`sessao.FORMATOS`): cliente → descoberta/demo/
    alinhamento (muda a leitura do Raio-X); parresia → daily (tira a reunião de TODA a medição);
    "nenhum" apaga."""
    s = achar(a.id)
    novo = None if a.formato in ("nenhum", "nao-sei", "não-sei", "reuniao", "reunião") else a.formato
    if not _sessao.formato_valido(s.tipo, novo):
        validos = _sessao.formatos_do_tipo(s.tipo)
        sys.exit(f"formato inválido para {TIPOS.get(s.tipo, s.tipo)}: use "
                 + (", ".join(validos) + " ou nenhum" if validos else "nenhum (este tipo não tem formato)"))
    antes = s.m.get("formato")
    s.m["formato"] = novo
    s.salvar()
    print(f"{s.id}: formato {antes or '—'} -> {novo or '—'}")
    if _sessao.fora_da_medicao(s):
        if antes != novo:
            _tirar_da_medicao(s)
        return
    if antes == _sessao.FORMATO_DAILY:
        print(f"  deixou de ser daily: a ata e o Raio-X saem com `atas.py processar {s.id} --forcar estrutura`")
        return
    if s.status_etapa("raio_x") == "ok" and not a.sem_raio_x:
        raio_x(s)
        print("  Raio-X refeito com o formato novo (atas.py fala <id> mostra a leitura)")


def _tirar_da_medicao(s):
    """A reunião virou daily depois de medida: tira a linha do histórico (com backup), refaz a nota do
    vault e o painel, apaga a página/relatório dela em fala-analise/, guarda a avaliação interna como
    *.antes-daily.* (não apaga) e marca raio_x e avaliacao como "pulada"."""
    import analise_fala
    import avaliar
    import pipeline
    r = analise_fala.remover_reuniao(s.id)
    if r["linha"]:
        print(f"  Raio-X: linha tirada do histórico (backup em {r['backup'].name})"
              + (f"; {len(r['apagados'])} arquivo(s) da reunião apagado(s) em fala-analise/" if r["apagados"] else ""))
        print("  nota do Sinapse refeita sem ela" if r["vault"] else "  (vault não encontrado nesta máquina)")
    else:
        print("  Raio-X: a reunião não estava no histórico")
    for x in avaliar.tirar_da_medicao(s):
        print(f"  avaliação interna guardada como {x.name}")
    s = Sessao.abrir(s.pasta)
    s.etapa("raio_x", "pulada", pipeline.FORA_DA_MEDICAO)
    s.etapa("avaliacao", "pulada", pipeline.FORA_DA_MEDICAO)
    at = _sessao.ler_json(s.caminho("ata.json")) or {}
    if not _ata.e_daily(at):
        print(f"  a ata ainda é a de reunião normal; a da daily (pessoas, com você, frentes): "
              f"`atas.py processar {s.id} --forcar estrutura`"
              + (" (com `transcricao,estrutura` refaz também quem falou, enquanto o áudio existir)"
                 if (s.audio_dir / "loop.opus").exists() else ""))


def c_marcar(a):
    """Marca momentos depois da reunião ("lembrei que em 40:10 ele falou do prazo"). A ata passa a
    tratar o trecho na próxima estrutura; até lá a marca aparece como pendente."""
    import marcas
    s = achar(a.id)
    if s.m.get("estado") == "gravando" and not s.orfa():
        sys.exit("esta reunião está sendo gravada agora: marque pela janela (atalho ou botão Marcar)")
    try:
        horarios = marcas.ler_horarios(a.horarios)
    except ValueError as e:
        sys.exit(str(e))
    dur = s.duracao_s()
    for t in horarios:
        if dur and t > dur + 1:
            sys.exit(f"{_ata.fmt_t(t)} passa do fim da reunião ({_ata.fmt_t(dur)})")
    if a.remover:
        antes = marcas.lista(s)
        s.m["marcas"] = [m for m in antes if not any(abs(m["t"] - t) < marcas.REPIQUE_S for t in horarios)]
        s.salvar()
        print(f"{len(antes) - len(s.m['marcas'])} marca(s) removida(s)")
    else:
        for t in horarios:
            m = marcas.adicionar(s, t, "depois")
            print(f"  {_ata.fmt_t(t)} " + ("marcado" if m else "já havia uma marca aí (±2 s)"))
    _imprimir_marcas(s)
    if _sessao.ler_json(s.caminho("ata.json")):
        print(f"\npara a ata ler o trecho: `atas.py processar {s.id} --forcar estrutura`")


def _imprimir_marcas(s):
    import marcas
    _, at = _ata_de(s)
    mom = {x.get("marca_t"): x for x in (at or {}).get("momentos") or []}
    ids = marcas.identificadas(marcas.lista(s))
    if not ids:
        print("nenhum momento marcado")
        return
    print(f"{len(ids)} momento(s) marcado(s) · trecho de {marcas.JANELA_ANTES_S} s antes a "
          f"{marcas.JANELA_DEPOIS_S} s depois")
    from render import texto_momento
    for mid, m in ids:
        mo = mom.get(round(m["t"], 1))
        if mo is None:
            o_que = "ainda não está na ata"
        else:
            frase, vazio = texto_momento(mo)
            o_que = (f"{frase} — \"{mo['citacao']}\" [{mo.get('t')}]" if frase else vazio)
            if mo.get("itens"):
                o_que += " · na ata: " + ", ".join(mo["itens"])
        print(f"  {mid}  {_ata.fmt_t(m['t']):>8}  ({m.get('origem')})  {o_que}")


def c_marcas(a):
    _imprimir_marcas(achar(a.id))


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
    import pipeline
    if _sessao.fora_da_medicao(s):               # daily: nunca medida (a trava também está no analise_fala)
        s.etapa("raio_x", "pulada", pipeline.FORA_DA_MEDICAO)
        return None
    cfg = cfg or _config.carregar()
    segs, _ = _ata_de(s)
    if not segs:
        raise SystemExit("esta sessão não tem transcrição")
    import avaliar
    mic = s.audio_da_voz()                       # .pcm, mic.opus ou o arquivo único do celular
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
    if r is None:
        print(f"{s.id}: daily — fora da medição (sem Raio-X da fala)")
        return
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
        if _sessao.fora_da_medicao(s):
            print(f"\n{s.id}  daily: fora da medição (pulada)")
            continue
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


def c_daily(a):
    """Busca só nas dailies: quem disse o quê sobre qual card. Do ata.json (pessoas, com você, decisões,
    encaminhamentos) e, se a ata não tiver nada, da transcrição. Nome confirmado ou "Rótulo (nome?)"."""
    import daily
    achou = 0
    for s in _sessao.listar():
        if not _sessao.fora_da_medicao(s):
            continue
        quando = str(s.m.get("inicio") or s.m.get("criado") or "")
        if a.desde and quando[:10] < a.desde:
            continue
        segs, at = _ata_de(s)
        if at is None:
            continue
        if not _ata.e_daily(at):                 # daily com ata de reunião normal: só a transcrição
            at = {**at, "pessoas": [], "com_voce": [],
                  "frentes_rastreadas": daily.frentes_do_config(_config.carregar())}
        hits = daily.buscar(at, segs, a.termo, a.pessoa, a.frente)
        if not hits:
            continue
        print(f"{quando[:16].replace('T', ' ')} · {s.id}")
        for h in hits[:a.n]:
            card = f" · {h['card']}" if h.get("card") else ""
            susp = " ⚠ origem não localizada" if h.get("verificado") is False else ""
            print(f"  [{h.get('t')}] {h['quem']}{card} · {h['onde']}: {h['texto']}{susp}")
        achou += len(hits)
    if not achou:
        print(f"nada sobre {a.termo!r} nas dailies" + (f" de {a.pessoa}" if a.pessoa else ""))


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
    mx, fmin, smin = cfg.get("diar_max_falantes", 6), None, None
    if a.daily or _sessao.fora_da_medicao(s):
        # os parâmetros da daily são PALPITE até esta conta numa daily real (quantas pessoas falaram?)
        d = {**_config.PADROES["daily_diar"], **(cfg.get("daily_diar") or {})}
        mx, fmin, smin = d["max_falantes"], d["min_fatia"], d["min_segundos"]
        print(f"  teto da daily: até {mx} vozes, grupo com ≥{fmin:.1%} da fala e ≥{smin:.0f} s")
    for thr in [float(x) for x in a.limiares.split(",")]:
        r = transcribe._diarizar(tmp, thr, -1, mx, cfg.get("diar_python"), fatia_min=fmin, min_seg=smin)
        tempo = {}
        for x in r.get("turnos") or []:
            tempo[x["speaker"]] = tempo.get(x["speaker"], 0.0) + x["end"] - x["start"]
        tot = sum(tempo.values()) or 1
        fatias = " ".join(f"{v / tot:.0%}" for v in sorted(tempo.values(), reverse=True))
        print(f"  limiar {thr:.2f}: agrupamento bruto {r.get('brutos'):>3} → {r['falantes']} "
              f"falante(s) ({r.get('modo')}) · fatias {fatias}")
    tmp.unlink(missing_ok=True)


def c_importar_legado(a):
    import legado
    feitos = legado.importar()
    print(f"{len(feitos)} ata(s) importada(s)")


def _data_arg(txt):
    import datetime as _dt
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d_%H%M", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(txt.strip(), fmt)
        except ValueError:
            pass
    sys.exit(f"data inválida: {txt!r} (use \"AAAA-MM-DD HH:MM\")")


def _resumo_importada(s):
    cel = s.m.get("celular") or {}
    print(f"\n{s.id} → {s.m.get('estado')} · tipo {s.tipo}")
    if s.tipo == _sessao.TIPO_PENDENTE:
        print(f"  tipo PENDENTE: `atas.py tipo {s.id} <cliente|parresia|carreira|pessoal>`")
    print(f"  quem é você: {cel.get('evidencia') or '—'}")
    print("  feche no Claude com /ata (confirma quem é você, os nomes e o tipo)")


def c_importar_celular(a):
    """Reunião presencial gravada no celular: um arquivo de áudio → uma sessão (ver celular.py)."""
    import celular
    if not _sessao.formato_valido(a.tipo or _sessao.TIPO_PENDENTE, a.formato):
        sys.exit(f"formato inválido: use {', '.join(_sessao.formatos_do_tipo(a.tipo or _sessao.TIPO_PENDENTE))}")
    if a.tipo and a.tipo not in TIPOS:
        sys.exit(f"tipo inválido: use {', '.join(TIPOS)} (sem --tipo a reunião fica pendente)")
    part = [p.strip() for p in (a.participantes or "").split(",") if p.strip()]
    try:
        import marcas
        mk = marcas.ler_horarios([a.marcas]) if a.marcas else []
    except ValueError as e:
        sys.exit(str(e))
    try:
        s = celular.importar(a.arquivo, titulo=a.titulo, tipo=a.tipo, projeto=a.projeto or "",
                             participantes=part, formato=a.formato, marcas=mk,
                             quando=_data_arg(a.data) if a.data else None,
                             processar=not a.sem_processar, log=print, forcar=a.forcar,
                             apagar_origem=a.apagar_origem)
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        sys.exit(f"não importou: {e}")
    if a.sem_processar:
        print(f"{s.id} criada; processe com `atas.py processar {s.id}`")
        return
    _imprimir_etapas(s, s.m.get("etapas") or {})
    _resumo_importada(s)


def c_vigiar(a):
    """Importa os áudios novos de uma pasta (ex.: a pasta Atas-celular do OneDrive). Uma passada,
    ou --continuo (repete a cada --intervalo s até Ctrl+C). Nada é agendado no Windows."""
    import time
    import celular
    if a.tipo and a.tipo not in TIPOS:
        sys.exit(f"tipo inválido: use {', '.join(TIPOS)} (sem --tipo cada reunião fica pendente)")
    while True:
        try:
            feitos = celular.vigiar(a.pasta, tipo=a.tipo, projeto=a.projeto or "",
                                    processar=not a.sem_processar, log=print,
                                    apagar_origem=a.apagar_origem)
        except FileNotFoundError as e:
            sys.exit(str(e))
        novos = [(arq, r) for arq, r in feitos if not r.startswith(("falhou", "ainda"))]
        for arq, r in feitos:
            print(f"  {arq.name}: {r}")
        if novos and not a.sem_processar:
            for _arq, sid in novos:
                _resumo_importada(Sessao.abrir(sid))
        if not a.continuo:
            print(f"{len(novos)} reunião(ões) importada(s) de {a.pasta}")
            return
        try:
            time.sleep(a.intervalo)
        except KeyboardInterrupt:
            return


def c_voz_referencia(a):
    """Refaz a amostra da voz do Pedro (o canal do microfone de uma reunião do Atas)."""
    import celular
    s = achar(a.id) if a.id else None
    try:
        p = celular.criar_referencia(s)
    except RuntimeError as e:
        sys.exit(str(e))
    print(f"{p} (fora do git; é a sua voz, fica só nesta máquina)")


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


# ── modo treino (14/10/2026): ensaio sozinho, fora do Raio-X das reuniões ───
def _opcoes_treino(a):
    import treino
    if a.tipo not in treino.TIPOS_TREINO:
        sys.exit(f"tipo de treino inválido: use {', '.join(treino.TIPOS_TREINO)}")
    nota = None
    if a.nota:
        try:
            nota = str(treino.achar_nota(a.nota))
        except FileNotFoundError as e:
            sys.exit(str(e))
    return dict(tipo=a.tipo, assunto=a.assunto or "", nota=nota, duracao_alvo_s=a.duracao, alvo=a.alvo)


def _imprimir_treino(t):
    import treino
    print()
    print("\n".join(treino.texto_resultado(t)))
    print(f"\npasta: {t.pasta}")


def c_treinar(a):
    """Grava um treino pelo terminal (só o microfone) e mostra o resultado."""
    import record
    import treino
    op = _opcoes_treino(a)
    cfg = _config.carregar()
    disp = record.escolher_so_microfone(cfg.get("microfone"))
    t = treino.Treino.criar(op["tipo"], op["assunto"], op["nota"], op["duracao_alvo_s"], op["alvo"])
    print(f"  Microfone: {disp['mic'].name}")
    for av in disp["avisos"]:
        print(f"  ⚠ {av}")
    if t.m.get("leitura"):                     # leitura ritmada: o texto, com uma pausa em cada barra
        print(f"\n  Leia em voz alta ({t.m['leitura']['titulo']}), pausando em cada barra:\n")
        print("  " + treino.BARRA.join(t.m["leitura"]["trechos"]))
        op["duracao_alvo_s"] = t.m["duracao_alvo_s"]
    g = record.Gravador(t, disp)
    g.iniciar()
    try:
        input(f"\n  >>> TREINANDO ({treino.TIPOS_TREINO[op['tipo']]}, alvo "
              f"{op['duracao_alvo_s'] // 60}:{op['duracao_alvo_s'] % 60:02d}) — ENTER para parar.\n")
    except (KeyboardInterrupt, EOFError):
        pass
    g.parar()
    treino.analisar(t, cfg, log=print, claude=not a.sem_claude)
    _imprimir_treino(t)


def c_treino_arquivo(a):
    """Um áudio já gravado vira treino (o arquivo de origem não é tocado)."""
    import treino
    op = _opcoes_treino(a)
    cfg = _config.carregar()
    try:
        t = treino.importar(a.arquivo, op["tipo"], op["assunto"], op["nota"], op["duracao_alvo_s"], op["alvo"],
                            quando=_data_arg(a.data) if a.data else None)
    except (ValueError, FileNotFoundError) as e:
        sys.exit(f"não importou: {e}")
    treino.analisar(t, cfg, log=print, claude=not a.sem_claude)
    _imprimir_treino(t)


def c_treinos(a):
    """Os treinos com a evolução: cada um contra o anterior do mesmo tipo e contra as reuniões."""
    import treino
    br = treino._br
    if a.manter:
        try:
            t = treino.achar(a.manter)
        except FileNotFoundError as e:
            sys.exit(str(e))
        t.m["manter"] = True
        t.salvar()
        print(f"{t.id}: o áudio fica guardado (fora da retenção de 30 dias)")
        return
    linhas = [r for r in treino.ler_treinos() if not a.tipo or r.get("tipo") == a.tipo][-a.n:]
    if not linhas:
        print("nenhum treino ainda: `atas.py treinar` ou o botão Treinar da janela")
        return
    print(f"{'data':16}  {'tipo':8} {'fala':>5} {'síl/s':>6} {'pausas/min':>10} {'muleta/1k':>9} {'entonação':>9}")
    for r in linhas:
        m = r.get("metrics") or {}
        print(f"{str(r.get('data', ''))[:16].replace('T', ' '):16}  {r.get('tipo', ''):8} "
              f"{treino._mmss(m.get('fala_s')):>5} {br(m.get('silabas_por_s'), 2):>6} "
              f"{br(m.get('pausas_por_min'), 1):>10} {br(m.get('muleta_pura_por_1000'), 1):>9} "
              f"{br(m.get('entonacao_st'), 1) + ' st' if m.get('entonacao_st') is not None else '—':>9}"
              + ("" if r.get("retorno") else "  (sem Claude)"))
    for tipo in dict.fromkeys(r.get("tipo") for r in linhas):
        do_tipo = [r["metrics"] for r in linhas if r.get("tipo") == tipo and r.get("metrics")]
        if len(do_tipo) >= 2:
            p, u = do_tipo[0], do_tipo[-1]
            print(f"\n{treino.TIPOS_TREINO.get(tipo, tipo)}: ritmo {br(p.get('silabas_por_s'), 2)} → "
                  f"{br(u.get('silabas_por_s'), 2)} sílabas/s · pausas {br(p.get('pausas_por_min'), 1)} → "
                  f"{br(u.get('pausas_por_min'), 1)}/min · muleta {br(p.get('muleta_pura_por_1000'), 1)} → "
                  f"{br(u.get('muleta_pura_por_1000'), 1)}/1k ({len(do_tipo)} treinos)")
    reun = treino.comparar(None, None, "9999", treinos=[])["reunioes"]
    if reun.get("silabas_por_s"):
        print(f"\nSuas reuniões (mediana das últimas {reun['silabas_por_s']['n']}): "
              f"{br(reun['silabas_por_s']['mediana'], 2)} sílabas/s"
              + (f" · muleta {br(reun['muleta_pura_por_1000']['mediana'], 1)}/1k" if reun.get("muleta_pura_por_1000") else "")
              + ". A distância entre o treino e a reunião é o que ainda não passou para a conversa.")


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
    p = sub.add_parser("formato", help="formato da reunião: cliente → descoberta, demo, alinhamento; parresia → daily; ou nenhum")
    p.add_argument("id")
    p.add_argument("formato")
    p.add_argument("--sem-raio-x", action="store_true", help="não refazer o Raio-X agora")
    p.set_defaults(fn=c_formato)
    p = sub.add_parser("marcar", help="marca momentos depois da reunião: marcar <id> 12:30 40:10")
    p.add_argument("id")
    p.add_argument("horarios", nargs="+", help="mm:ss ou h:mm:ss (vírgula também separa)")
    p.add_argument("--remover", action="store_true", help="tira as marcas desses horários (±2 s)")
    p.set_defaults(fn=c_marcar)
    p = sub.add_parser("marcas", help="lista os momentos marcados e o que a ata achou em cada um")
    p.add_argument("id", nargs="?", default="ultima")
    p.set_defaults(fn=c_marcas)
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
    p.add_argument("--daily", action="store_true", help="com o teto da daily (daily_diar no config)")
    p.set_defaults(fn=c_calibrar)
    p = sub.add_parser("daily", help="busca só nas dailies: quem disse o quê sobre qual card")
    p.add_argument("termo", help="palavra, assunto ou card (SUP-953)")
    p.add_argument("--pessoa")
    p.add_argument("--frente", help='uma das frentes_rastreadas do config, ex.: "Frota WP"')
    p.add_argument("--desde", help="AAAA-MM-DD")
    p.add_argument("-n", type=int, default=20, help="máximo de menções por daily")
    p.set_defaults(fn=c_daily)
    sub.add_parser("importar-legado").set_defaults(fn=c_importar_legado)
    p = sub.add_parser("importar", help="reunião presencial gravada no celular (um arquivo de áudio)")
    p.add_argument("arquivo")
    p.add_argument("--titulo")
    p.add_argument("--tipo", help="cliente, parresia, carreira ou pessoal; sem ele = pendente")
    p.add_argument("--projeto")
    p.add_argument("--participantes", help='quem mais estava na sala, sem você: "Ana,Breno"')
    p.add_argument("--formato", help="descoberta, demo ou alinhamento (cliente); daily (parresia)")
    p.add_argument("--data", help='início da reunião, "AAAA-MM-DD HH:MM" (padrão: nome ou data do arquivo)')
    p.add_argument("--marcas", help='momentos marcados no áudio, mm:ss separados por vírgula: "12:30,40:10"')
    p.add_argument("--sem-processar", action="store_true", help="só cria a sessão")
    p.add_argument("--forcar", action="store_true", help="importar de novo um arquivo já importado")
    p.add_argument("--apagar-origem", action="store_true", help="apaga o arquivo de origem depois de conferir a cópia")
    p.set_defaults(fn=c_importar_celular)
    p = sub.add_parser("vigiar", help="importa os áudios novos de uma pasta (sem duplicar)")
    p.add_argument("pasta")
    p.add_argument("--tipo", help="para pasta de um tipo só; sem ele cada reunião fica pendente")
    p.add_argument("--projeto")
    p.add_argument("--continuo", action="store_true", help="fica vigiando até Ctrl+C")
    p.add_argument("--intervalo", type=int, default=120, help="segundos entre passadas (--continuo)")
    p.add_argument("--sem-processar", action="store_true")
    p.add_argument("--apagar-origem", action="store_true")
    p.set_defaults(fn=c_vigiar)
    p = sub.add_parser("voz-referencia", help="refaz a amostra da sua voz (acha \"Você\" no áudio do celular)")
    p.add_argument("id", nargs="?")
    p.set_defaults(fn=c_voz_referencia)
    sub.add_parser("limpar-audio").set_defaults(fn=c_limpar)
    for nome, fn, ajuda in (("treinar", c_treinar, "treino de fala sozinho: grava só o microfone"),
                            ("treino", c_treino_arquivo, "analisa um treino já gravado (arquivo de áudio)")):
        p = sub.add_parser(nome, help=ajuda)
        if nome == "treino":
            p.add_argument("arquivo")
            p.add_argument("--data", help='quando foi o treino, "AAAA-MM-DD HH:MM" (padrão: nome ou data do arquivo)')
        p.add_argument("--tipo", default="reuniao", help="reuniao (padrão), tema ou leitura (ler em voz alta)")
        p.add_argument("--assunto", help="sobre o que é o treino (opcional)")
        p.add_argument("--nota", help="nota de estudo do Sinapse para conferir o conteúdo (nome em 02-ESTUDO ou caminho)")
        p.add_argument("--duracao", type=int, default=180, help="alvo de duração em segundos (padrão 180)")
        p.add_argument("--alvo", type=float, default=None, help="alvo de sílabas/s (4.8 padrão; 4.5 na leitura)")
        p.add_argument("--sem-claude", action="store_true", help="só as métricas")
        p.set_defaults(fn=fn)
    p = sub.add_parser("treinos", help="os treinos com a evolução")
    p.add_argument("--tipo", help="reuniao ou tema")
    p.add_argument("-n", type=int, default=20)
    p.add_argument("--manter", metavar="ID", help="guarda o áudio deste treino (fora da retenção)")
    p.set_defaults(fn=c_treinos)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
