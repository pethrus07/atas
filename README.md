# Atas — o registro oficial de toda reunião importante

Grava a reunião (Meet, Zoom, WhatsApp, ligação) **direto no disco enquanto ela acontece**,
transcreve **nesta máquina** (faster-whisper na GPU), separa quem falou, e o Claude monta
uma **ata estruturada** — decisões, encaminhamentos com dono e prazo, perguntas em aberto,
riscos — em que cada item aponta o trecho exato da conversa de onde saiu. O que não foi
dito aparece como lacuna, nunca como dado.

Reunião interna (Parresia, carreira, pessoal) **não sai da máquina**. Reunião de cliente
sai como PDF com a marca RYZE e, **quando você manda**, como página com senha que expira.

> **Para entender o sistema sozinho, leia [docs/ARQUITETURA.md](docs/ARQUITETURA.md).**

```
[XPS]                                                        [Cloudflare — só cliente]
 app.py (janela) / atas.py (CLI)                              worker.js
   record.py      mic + chamada → .pcm no disco, bloco a bloco   ├─ D1: HTML pronto + senha + expiração
   transcribe.py  Whisper large-v3-turbo (GPU) + vocabulário      ├─ /r/<id> atrás de senha
   diarize.py     separa os remotos (venv diar), com teto         └─ cron diário apaga o que expirou
   estruturar.py  claude -p → ata.json auditada (ata.py)
   render.py      ata.md · ata.html · PDF · entregavel.pdf
   upload.py      publica o entregável (só cliente)      POST →
   analise_fala.py Raio-X da fala (interno) → Sinapse sem títulos
```

## No dia a dia
1. Dois cliques no atalho **Atas** (ou em [local/gravar.bat](local/gravar.bat)).
2. Título, **tipo** (cliente · Parresia · carreira · pessoal), projeto e **quem vai falar
   do outro lado**. Os nomes ajudam a separar as vozes e a atribuir as tarefas.
3. **Testar o áudio** → **Gravar**. A janela mostra o tempo e o nível de cada lado, e
   avisa se o microfone ou a chamada ficarem mudos.
4. **Parar e gerar a ata.** No fim aparecem todas as etapas (✓ ok · ✗ falhou · – pulada ·
   ○ pendente). Em reunião de cliente, **Publicar para o cliente** sobe a página com senha.
5. No Claude: **`/ata`** — confirma quem é quem, fecha lacunas e recebe as propostas de
   memória, Sinapse, log de decisões e ClickUp (nada é publicado sem o seu sim).

Se o PC travar: abra o Atas de novo. Ele avisa "Gravação interrompida" e gera a ata com o
que foi gravado (perde-se no máximo os últimos ~5 s).

> **Consentimento (LGPD):** avise que está gravando. O áudio fica guardado **só nesta
> máquina** por 30 dias (para reprocessar ou calibrar) e depois é apagado.

## Onde fica cada coisa
Uma pasta por reunião em `atas-salvas/<data>_<hora>_<título>/`: `sessao.json` (contexto e
etapas), `transcricao.json`, **`ata.json`** (a ata canônica), `ata.md`/`.html`/`.pdf`,
`entregavel.pdf` (cliente) e `audio/*.opus`. Tudo fora do git.

## Linha de comando
Sempre com o Python do venv:
```powershell
$A = "C:\Users\olive\.venvs\faster-whisper\Scripts\python.exe C:\Users\olive\Projetos\atas\local\atas.py"
Invoke-Expression "$A listar"            # reuniões
Invoke-Expression "$A mostrar ultima"    # a ata, lacunas e etapas
Invoke-Expression "$A buscar gateway --pessoa Ricardo"
Invoke-Expression "$A retomar"           # gravação interrompida
```
Todos os comandos: `atas.py --help` e [docs/ARQUITETURA.md §11](docs/ARQUITETURA.md#11--receitas).

## Testes
```powershell
C:\Users\olive\.venvs\faster-whisper\Scripts\python.exe -m pytest tests -q   # 51 testes, ~16 s
cd worker; npm test                                                          # 10 testes do Worker (Miniflare)
```

## Montar do zero
- **Venv principal** `C:\Users\olive\.venvs\faster-whisper` (Python 3.14): `faster-whisper`,
  `soundcard`, `numpy`, `av`, `pytest`, `pillow` e, para a GPU, `nvidia-cublas-cu12` +
  `nvidia-cudnn-cu12==9.*` (o `transcribe.py` acha as DLLs sozinho).
- **Venv da diarização** `C:\Users\olive\.venvs\diar` (Python 3.12): `sherpa-onnx`, `numpy`.
  Modelos ONNX (~35 MB) em `local/models/diar/` (fora do git).
- **Claude Code** instalado (a extensão do VS Code basta: o `claude.exe` é achado sozinho).
- `local/config.example.json` → `local/config.json`. Nenhuma chave é obrigatória para gravar.
- Worker: [docs/ARQUITETURA.md §11](docs/ARQUITETURA.md#11--receitas) (D1, migrações, secret, homologação).
- A skill `/ata` vive em [claude/skills/ata](claude/skills/ata/SKILL.md) e é ligada em
  `~/.claude/skills/ata` por junction.
