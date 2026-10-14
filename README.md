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
1. Dois cliques no atalho **Atas** (Área de Trabalho).
2. Título, **tipo** (cliente · Parresia · carreira · pessoal) e **quem fala do outro lado**
   — os nomes ajudam a separar as vozes e a atribuir as tarefas.
3. **Gravar.** A tela mostra o tempo, o nível de cada lado e o microfone em uso (o do fone,
   se ele estiver plugado). Só aparece aviso se houver problema.
4. **Parar e gerar a ata.** Em reunião de cliente, **Publicar para o cliente** sobe a página
   com senha — só se você mandar.
5. No Claude: **`/ata`** — confirma quem é quem, fecha lacunas e recebe as propostas de
   memória, Sinapse, log de decisões e ClickUp (nada é publicado sem o seu sim).

Se o PC travar: abra o Atas de novo. Ele avisa "Gravação interrompida" e gera a ata com o
que foi gravado (perde-se no máximo os últimos ~5 s).

Reunião de **cliente** mostra uma linha discreta **Formato** (não sei · descoberta · demo ·
alinhamento). É opcional: só afina a leitura do Raio-X. Dá para corrigir depois com
`atas.py formato <id> demo`.

## Reunião presencial (gravada no celular)
Uma conversa sem chamada não passa pelo PC. Grave no celular e traga o arquivo:

1. **No Android:** grave com o gravador do próprio celular. Para o arquivo chegar ao PC:
   - **Na mão, sem app extra:** no gravador, **Compartilhar → OneDrive →** pasta `Atas-celular`.
   - **Sozinho:** o app do OneDrive no Android **não** sincroniza pasta local (só envia a
     câmera). Use um app ponte: **FolderSync** (grátis, com anúncio) ou **Round Sync** (rclone,
     código aberto, grátis), sincronizando `Recordings/Atas-celular` do celular → pasta
     `Atas-celular` do OneDrive, **só envio, só no Wi-Fi**. Evite OneSync/Autosync: a versão
     grátis limita o arquivo a 10 MB, e 1 h de reunião passa disso.
   - **Antes da primeira reunião real**, grave 10 min com a tela apagada e confira o arquivo:
     Xiaomi e Samsung podem matar a gravação. Tire o gravador e o app ponte da otimização de
     bateria.
2. **No PC** (a pasta do OneDrive já sincroniza sozinha):
   ```powershell
   Invoke-Expression "$A vigiar `"$env:OneDrive\Atas-celular`""      # importa o que é novo, sem duplicar
   Invoke-Expression "$A importar `"C:\...\2026-10-14_1030.m4a`" --titulo `"Oficina Jonas`" --tipo cliente --participantes `"Jonas`""
   ```
   Sem `--tipo` a reunião fica **pendente**: não gera entregável nem publica até
   `atas.py tipo <id> <tipo>`. A data sai do `--data`, do nome do arquivo (`AAAA-MM-DD_HHMM.m4a`)
   ou da data do arquivo. Nada é agendado no Windows; `vigiar --continuo` fica olhando até Ctrl+C.
3. **No Claude, `/ata`:** como tudo está num canal só, o sistema **estima** qual voz é a sua
   (pela amostra da sua voz em `local/models/voz-referencia.wav`, ou pelo tom) e pergunta se
   acertou. Até você confirmar, o Raio-X da fala espera.

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
Invoke-Expression "$A buscar gateway --pessoa Mauro"
Invoke-Expression "$A retomar"           # gravação interrompida
Invoke-Expression "$A importar <áudio>"  # reunião presencial gravada no celular
```
Todos os comandos: `atas.py --help` e [docs/ARQUITETURA.md §11](docs/ARQUITETURA.md#11--receitas).

## Testes
```powershell
C:\Users\olive\.venvs\faster-whisper\Scripts\python.exe -m pytest tests -q   # 108 testes (104 rápidos + 4 lentos, -m "not lento" pula), ~60 s
cd worker; npm test                                                          # 10 testes do Worker (Miniflare)
```

## Montar do zero
- **Venv principal** `C:\Users\olive\.venvs\faster-whisper` (Python 3.14): `faster-whisper`,
  `soundcard`, `sounddevice`, `numpy`, `av`, `pytest`, `pillow` e, para a GPU, `nvidia-cublas-cu12` +
  `nvidia-cudnn-cu12==9.*` (o `transcribe.py` acha as DLLs sozinho).
- **Venv da diarização** `C:\Users\olive\.venvs\diar` (Python 3.12): `sherpa-onnx`, `numpy`.
  Modelos ONNX (~35 MB) em `local/models/diar/` (fora do git).
- **Claude Code** instalado (a extensão do VS Code basta: o `claude.exe` é achado sozinho).
- `local/config.example.json` → `local/config.json`. Nenhuma chave é obrigatória para gravar.
- Worker: [docs/ARQUITETURA.md §11](docs/ARQUITETURA.md#11--receitas) (D1, migrações, secret, homologação).
- A skill `/ata` vive em [claude/skills/ata](claude/skills/ata/SKILL.md) e é ligada em
  `~/.claude/skills/ata` por junction.
