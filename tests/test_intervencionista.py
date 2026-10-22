# -*- coding: utf-8 -*-
"""Ao vivo intervencionista (22/10/2026, ARQUITETURA §22): filtro determinístico, teto e intervalo,
registro em intervencoes.jsonl, Claude mockado e o cartão sem foco."""
import json
import subprocess

import pytest

import intervencionista as iv
from sessao import Sessao

NOMES = ["Pedro"]
FRENTES = [{"nome": "Frota WP", "palavras": ["MainWP", "frota"], "cards": ["SUP-953", "SUP-954"]}]
PROJETOS = ["Instituto Automação", "Commagente", "Ware IoT"]


def F(t, rot, txt):
    return {"t": float(t), "rotulo": rot, "texto": txt}


def tipos(falas, daily=False, inicio=0):
    gs, pend = iv.gatilhos(falas, inicio, NOMES, FRENTES, PROJETOS, daily=daily)
    return [g["tipo"] for g in gs], pend


# ── leitura do ao-vivo.md ───────────────────────────────────────────────────
def test_le_so_linhas_inteiras_e_pula_cabecalho_e_marca(tmp_path):
    p = tmp_path / "ao-vivo.md"
    p.write_text("# Ao vivo — x\n\n_Transcrição preliminar._\n\n[00:05] Você: Bom dia.\n"
                 "[00:09] ★ MARCA\n[1:02:03] Participante: Quanto fica?\n[01:1", encoding="utf-8")
    falas, off = iv.ler_novas(p, 0)
    assert falas == [F(5, "Você", "Bom dia."), F(3723, "Participante", "Quanto fica?")]
    with open(p, "a", encoding="utf-8") as f:
        f.write("0] Você: Fica 600.\n")
    novas, off2 = iv.ler_novas(p, off)
    assert novas == [F(70, "Você", "Fica 600.")] and off2 > off
    assert iv.ler_novas(p, off2) == ([], off2)


# ── filtro: cada gatilho e cada não-gatilho ───────────────────────────────
def test_pergunta_com_o_nome_dele_dispara():
    assert tipos([F(10, "Participante", "Pedro, o app já está na loja?")])[0] == ["pergunta"]


def test_pergunta_com_voce_so_dispara_se_ele_responde_em_seguida():
    q = F(10, "Participante", "E você consegue entregar isso quando?")
    assert tipos([q, F(14, "Você", "Então, deixa eu ver.")])[0] == ["pergunta"]
    assert tipos([q, F(14, "Participante", "Porque o cliente pediu.")])[0] == []
    assert tipos([q, F(60, "Você", "Bom.")])[0] == []                        # resposta longe demais


def test_pergunta_sem_a_fala_seguinte_fica_pendente_e_vira_gatilho_depois():
    falas = [F(10, "Participante", "Você tem o link do relatório?")]
    gs, pend = iv.gatilhos(falas, 0, NOMES, FRENTES, PROJETOS)
    assert gs == [] and pend == [0]
    falas.append(F(13, "Você", "Tenho sim."))
    achados, ainda = iv.reavaliar_pendentes(falas, pend, NOMES)
    assert [g["motivo"] for g in achados] == ["pergunta para você"] and ainda == []


@pytest.mark.parametrize("txt", ["O elemento pode ser desse tamanho, mas a navegação não, você entendeu?",
                                 "Boa noite Pedro, beleza?", "Aqui você não fez nada, né?", "Você entendeu?",
                                 "Só que a diferença é assim. Por que eu quero te dizer isso?",
                                 "Que é um projeto, você entendeu, Pedro?"])
def test_tique_de_confirmacao_nao_e_pergunta(txt):
    # medido no ao vivo de 19/10: "você entendeu?" sozinho gastava o teto inteiro na primeira hora
    assert tipos([F(1, "Participante", txt), F(3, "Você", "Sim.")])[0] == []


def test_pergunta_de_verdade_antes_do_tique_conta():
    assert iv.perguntas_de_verdade("Você chegou a fazer algum teste? Entendeu?") == ["Você chegou a fazer algum teste?"]
    assert tipos([F(1, "Participante", "Você chegou a fazer algum teste? Entendeu?"), F(4, "Você", "Fiz.")])[0] == ["pergunta"]


def test_nao_dispara_pergunta_do_proprio_pedro_nem_afirmacao_com_o_nome():
    assert tipos([F(1, "Você", "Você viu o e-mail que eu mandei?"), F(3, "Participante", "Vi sim.")])[0] == []
    assert tipos([F(1, "Participante", "O Pedro mandou o e-mail ontem à noite.")])[0] == []
    assert tipos([F(1, "Participante", "Como é que tá o tempo aí?")])[0] == []   # sem nome nem "você"


@pytest.mark.parametrize("txt", ["Fechamos em R$ 450 na publicação.", "Isso dá uns 15 mil por ano.",
                                 "A parcela de 700 cai quando?", "Fica pronto em 15 dias.",
                                 "Te pago dia 10 sem falta.", "Dá um desconto de 20% nisso aí.",
                                 "São 300 reais o piloto."])
def test_valor_numero_e_prazo_disparam(txt):
    assert tipos([F(1, "Participante", txt)])[0] == ["valor"]


@pytest.mark.parametrize("txt", ["Hoje eu fui lá ver as máquinas.", "Amanhã a gente conversa.",
                                 "Tem um roteador 4G com VPN aqui.", "Eu tenho 2 filhos pequenos.",
                                 "Isso foi em 2024 numa feira.", "É 100% local para a gente.",
                                 "Mas se eu tenho 20 máquinas, toda hora eu tenho que ficar desligando."])
def test_conversa_sem_valor_nao_dispara(txt):
    assert tipos([F(1, "Participante", txt)])[0] == []


def test_card_e_frente_disparam():
    assert tipos([F(1, "Participante", "O SUP-1031 voltou pro backlog.")])[0] == ["card"]
    gs, _ = iv.gatilhos([F(1, "Participante", "O sup 953 travou de novo.")], 0, NOMES, FRENTES, PROJETOS)
    assert gs[0]["motivo"] == "card SUP-953 (frente Frota WP)"
    gs, _ = iv.gatilhos([F(1, "Participante", "O MainWP parou de sincronizar.")], 0, NOMES, FRENTES, PROJETOS)
    assert gs[0]["tipo"] == "card" and "Frota WP" in gs[0]["motivo"]


def test_afirmacao_sobre_projeto_conhecido_dispara_e_mencao_solta_nao():
    assert tipos([F(1, "Participante", "O site do Instituto Automação já está no ar com as notícias.")])[0] == ["projeto"]
    assert tipos([F(1, "Participante", "Commagente.")])[0] == []                  # curta
    assert tipos([F(1, "Participante", "Eu gosto muito do nome Commagente para a marca nova")])[0] == []


def test_daily_so_dispara_com_voce_e_frentes():
    falas = [F(1, "Participante", "Fechamos em R$ 450 na publicação."),
             F(5, "Participante", "O site do Instituto Automação já está no ar com as notícias."),
             F(9, "Participante", "Pedro, você viu o SUP-953?"),
             F(20, "Participante", "O MainWP parou de sincronizar.")]
    assert tipos(falas, daily=True)[0] == ["pergunta", "card"]


def test_nomes_de_projeto_do_sinapse(tmp_path):
    pasta = tmp_path / "03-PROJETOS"
    pasta.mkdir()
    (pasta / "celiware-ihm.md").write_text("---\ntipo: projeto\n---\n\n# Ware IoT (ex-Celiware IHM) — IHM portátil\n",
                                           encoding="utf-8")
    (pasta / "valter.md").write_text("# Valter\n", encoding="utf-8")
    (pasta / "instituto-automacao-historico-2026-08-27.md").write_text("# velho\n", encoding="utf-8")
    (pasta / "MOC-projetos.md").write_text("# MOC\n", encoding="utf-8")
    nomes = iv.nomes_de_projeto({"intervencionista": {"projetos": ["Fábrica de Conteúdo"]}}, vault=tmp_path,
                                excluir=["Valter", "Pedro"])
    assert nomes == ["Fábrica de Conteúdo", "celiware ihm", "Ware IoT"]     # "Celiware IHM" = o nome do arquivo


# ── teto, intervalo, fila, uma por vez ────────────────────────────────────
class Relogio:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def G(t, tipo="valor", chave=None):
    return {"t": float(t), "tipo": tipo, "chave": chave or f"{tipo}@{t}", "motivo": tipo, "trecho": "x",
            "rotulo": "Participante", "i": 0}


def test_teto_e_intervalo():
    rel = Relogio()
    ctl = iv.Controle({**iv.PADRAO, "max_chamadas": 2, "intervalo_min_s": 45}, rel)
    ctl.oferecer(G(10))
    assert ctl.proximo(10)["t"] == 10
    ctl.oferecer(G(20))
    assert ctl.proximo(20) is None                    # ainda em curso: nunca duas ao mesmo tempo
    ctl.terminou()
    assert ctl.proximo(20) is None                    # intervalo de 45 s
    rel.t = 46
    assert ctl.proximo(30)["t"] == 20
    ctl.terminou()
    ctl.oferecer(G(80))
    rel.t = 200
    assert ctl.teto() and ctl.proximo(80) is None and ctl.chamadas == 2


def test_fila_fica_com_o_mais_importante_e_descarta_o_velho():
    ctl = iv.Controle(iv.PADRAO, Relogio())
    ctl.oferecer(G(10, "projeto"))
    ctl.oferecer(G(12, "pergunta"))
    ctl.oferecer(G(14, "valor"))
    assert ctl.fila["tipo"] == "pergunta"
    ctl2 = iv.Controle(iv.PADRAO, Relogio())
    ctl2.oferecer(G(10))
    assert ctl2.proximo(10 + iv.PADRAO["validade_s"] + 1) is None and ctl2.fila is None


def test_a_mesma_chave_nao_dispara_de_novo_logo():
    rel = Relogio()
    ctl = iv.Controle({**iv.PADRAO, "intervalo_min_s": 0}, rel)
    ctl.oferecer(G(10, "card", "card:SUP-953"))
    assert ctl.proximo(10)
    ctl.terminou()
    assert ctl.oferecer(G(100, "card", "card:SUP-953")) is False
    assert ctl.oferecer(G(400, "card", "card:SUP-953")) is True


# ── a thread com o Claude mockado: registro e entrega ─────────────────────
@pytest.fixture
def sessao(raiz):
    return Sessao.criar("alinhamento valter", "cliente", "", ["Valter"], raiz=raiz)


def _escrever(s, *linhas):
    with open(s.caminho("ao-vivo.md"), "a", encoding="utf-8") as f:
        for ln in linhas:
            f.write(ln + "\n")


def test_passo_chama_registra_e_entrega(sessao, tmp_path, monkeypatch):
    monkeypatch.setenv("SINAPSE_VAULT", str(tmp_path / "vazio"))
    chamadas, entregues = [], []

    def falso(g, ctx, m, cfg, guardar_proc=None):
        chamadas.append((g, ctx))
        return {"sabe": True, "resposta": "Combinado em 14/10: R$ 450 quando a 1.5.0 entrar na loja.",
                "fonte": "memory/iot-ihm-portatil-valter.md", "segundos": 12.3, "custo_usd": 0.04, "modelo": "m"}
    rel = Relogio()
    cfg = {"meu_nome": "Pedro", "intervencionista": {"max_chamadas": 2, "intervalo_min_s": 45}}
    t = iv.Intervencionista(sessao, cfg, entregar=entregues.append, chamar=falso, relogio=rel)
    _escrever(sessao, "# Ao vivo", "", "[01:00] Você: Bom, sobre o app.",
              "[01:05] Participante: Pedro, quanto ficou a parcela do IoT mesmo?")
    item = t.passo()
    assert item["gatilho"] == "pergunta" and item["trecho"].startswith("Pedro, quanto")
    assert item["resposta"].startswith("Combinado") and item["custo_usd"] == 0.04 and item["mostrado"]
    assert [c[0]["t"] for c in chamadas] == [65.0] and len(chamadas[0][1]) == 2   # contexto vai junto
    assert entregues == [item]
    # segundo gatilho dentro do intervalo: não chama; depois do intervalo: chama; depois: teto
    _escrever(sessao, "[01:20] Participante: Fechamos em R$ 800 no total.")
    assert t.passo() is None and len(chamadas) == 1
    rel.t = 50
    assert t.passo()["gatilho"] == "valor"
    _escrever(sessao, "[01:40] Participante: E o SUP-953, como ficou?")
    rel.t = 200
    assert t.passo() is None and t.chamadas == 2
    reg = iv.ler_registro(sessao)
    assert [r["evento"] for r in reg] == ["intervencao", "intervencao", "teto"]
    assert {"gatilho", "trecho", "resposta", "fonte", "custo_usd", "t", "motivo"} <= set(reg[0])


def test_nao_sei_e_erro_ficam_so_no_registro(sessao, tmp_path, monkeypatch):
    monkeypatch.setenv("SINAPSE_VAULT", str(tmp_path / "vazio"))
    entregues = []
    resp = iter([{"sabe": False, "resposta": "não sei", "fonte": ""}, RuntimeError("sem resposta em 120 s")])

    def falso(*a, **k):
        r = next(resp)
        if isinstance(r, Exception):
            raise r
        return r
    rel = Relogio()
    t = iv.Intervencionista(sessao, {"intervencionista": {"intervalo_min_s": 0}}, entregar=entregues.append,
                            chamar=falso, relogio=rel)
    _escrever(sessao, "[00:10] Participante: Pedro, isso roda offline?")
    assert t.passo()["mostrado"] is False
    _escrever(sessao, "[00:20] Participante: Fica em R$ 250 o piloto.")
    item = t.passo()
    assert "sem resposta" in item["erro"] and item["mostrado"] is False
    assert entregues == []


def test_ligado_no_meio_nao_dispara_pelo_que_foi_dito_antes(sessao, tmp_path, monkeypatch):
    monkeypatch.setenv("SINAPSE_VAULT", str(tmp_path / "vazio"))
    chamadas = []
    t = iv.Intervencionista(sessao, {}, chamar=lambda *a, **k: chamadas.append(1) or
                            {"sabe": True, "resposta": "x", "fonte": "a.md"}, desde_t=300)
    _escrever(sessao, "[02:00] Participante: Fechamos em R$ 450.", "[05:30] Você: Certo.")
    assert t.passo() is None and chamadas == []


def test_limpar_resposta_aplica_a_regra_3(tmp_path):
    proj, mem = tmp_path / "Projetos", tmp_path / "mem"
    (proj / "atas" / "docs").mkdir(parents=True)
    (proj / "atas" / "docs" / "X.md").write_text("x", encoding="utf-8")
    mem.mkdir()
    cfg = {"projetos_dir": str(proj), "memoria_dir": str(mem)}
    r = iv.limpar_resposta({"sabe": True, "resposta": "R$ 450.", "fonte": ""}, cfg)
    assert r["sabe"] is False and r["motivo_nao_sei"] == "respondeu sem fonte"
    longa = iv.limpar_resposta({"sabe": True, "resposta": "a\nb\nc " + "palavra " * 60, "fonte": "atas/docs/X.md"}, cfg)
    assert longa["resposta"].startswith("a b") and len(longa["resposta"]) <= 240 and "c" not in longa["resposta"][:4]
    assert longa["fonte_conferida"] is True
    assert iv.limpar_resposta({"sabe": True, "resposta": "x", "fonte": "memory/nao-existe.md"}, cfg)["fonte_conferida"] is False
    assert iv.limpar_resposta({"sabe": True, "resposta": "x", "fonte": "conversa de 14/10"}, cfg)["fonte_conferida"] is None


def test_chamar_claude_so_leitura_e_saida_estruturada(monkeypatch, tmp_path):
    vistos = {}

    class Proc:
        returncode = 0

        def __init__(self, cmd, **kw):
            vistos["cmd"], vistos["kw"] = cmd, kw

        def communicate(self, timeout=None):
            vistos["timeout"] = timeout
            return json.dumps({"structured_output": {"sabe": True, "resposta": "ok", "fonte": "a.md"},
                               "total_cost_usd": 0.03, "modelUsage": {"m1": {"outputTokens": 9}}}).encode(), b""

        def poll(self):
            return 0
    monkeypatch.setattr(subprocess, "Popen", Proc)
    (tmp_path / "mem").mkdir()
    cfg = {"claude_cli": __file__, "projetos_dir": str(tmp_path), "memoria_dir": str(tmp_path / "mem")}
    r = iv.chamar_claude(G(10, "pergunta"), [F(10, "Participante", "Pedro, e aí?")],
                         {"titulo": "t", "tipo": "cliente"}, cfg)
    cmd = vistos["cmd"]
    assert cmd[cmd.index("--tools") + 1] == "Read,Grep,Glob" and "--json-schema" in cmd
    assert cmd[cmd.index("--add-dir") + 1] == str(tmp_path / "mem") and vistos["kw"]["cwd"] == str(tmp_path)
    assert "NADA inventado" in cmd[2] and "não sei" in cmd[2]
    assert r == {"sabe": True, "resposta": "ok", "fonte": "a.md", "segundos": r["segundos"], "custo_usd": 0.03,
                 "modelo": "m1"}


# ── o cartão: sem foco, por cima, some sozinho e com clique ──────────────
def test_cartao_sem_foco_por_cima_e_some():
    tk = pytest.importorskip("tkinter")
    import ctypes
    try:
        raiz = tk.Tk()
    except tk.TclError:
        pytest.skip("sem tela")
    try:
        raiz.geometry("200x100+50+50")
        raiz.update()
        u = ctypes.windll.user32
        u.GetForegroundWindow.restype = ctypes.c_void_p
        antes = u.GetForegroundWindow()
        c = iv.Cartao(raiz, {"gatilho": "pergunta", "t": "01:05", "resposta": "R$ 450 na loja.",
                             "fonte": "memory/x.md"}, segundos=0.4)
        for _ in range(5):
            raiz.update()
        assert c.estilo & iv._WS_EX_NOACTIVATE and c.estilo & iv._WS_EX_TOOLWINDOW
        assert raiz.call("wm", "attributes", c.top, "-topmost") == 1
        assert u.GetForegroundWindow() == antes                 # não roubou o foco
        raiz.after(700)
        raiz.update()
        assert not c.vivo()                                     # sumiu sozinho
        c2 = iv.Cartao(raiz, {"gatilho": "valor", "t": "02:00", "resposta": "x", "fonte": ""}, segundos=30)
        raiz.update()
        c2.top.winfo_children()[0].event_generate("<Button-1>")
        raiz.update()
        assert not c2.vivo()                                    # um clique fecha
    finally:
        raiz.destroy()


# ── a janela: ligar no meio liga o ao vivo junto ─────────────────────────
def test_ligar_no_meio_liga_o_ao_vivo_e_comeca_de_agora(sessao, monkeypatch, tmp_path):
    import queue
    import ao_vivo
    import app
    monkeypatch.setenv("SINAPSE_VAULT", str(tmp_path / "vazio"))
    ligados = []

    class AoVivoFalso:
        def __init__(self, s, cfg):
            ligados.append(s.id)

        def start(self):
            pass
    monkeypatch.setattr(ao_vivo, "AoVivo", AoVivoFalso)
    monkeypatch.setattr(iv.Intervencionista, "start", lambda self: None)

    class Grav:
        def decorrido(self):
            return 125.0

    class Falso:
        s, cfg, av, iv, cartao, g, q, l_interv = sessao, {}, None, None, None, Grav(), queue.Queue(), None
        _ligar_ao_vivo = app.App._ligar_ao_vivo
        _ligar_interv = app.App._ligar_interv
        _desligar_interv = app.App._desligar_interv
        _texto_interv = app.App._texto_interv
    f = Falso()
    app.App._alternar_interv(f)
    assert ligados == [sessao.id] and f.iv is not None and f.iv.desde_t == 125.0
    app.App._alternar_interv(f)
    assert f.iv is None
