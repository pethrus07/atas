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
   com senha — só se você mandar. **Desde 22/10/2026 a publicação não é usada** (decisão sua): as atas
   ficam só na máquina e o Worker está vazio.
5. No Claude: **`/ata`** — confirma quem é quem, fecha lacunas e recebe as propostas de
   memória, Sinapse, log de decisões e ClickUp (nada é publicado sem o seu sim).

Se o PC travar: abra o Atas de novo. Ele avisa "Gravação interrompida" e gera a ata com o
que foi gravado (perde-se no máximo os últimos ~5 s).

Reunião de **cliente** mostra uma linha discreta **Formato** (não sei · descoberta · demo ·
alinhamento). É opcional: só afina a leitura do Raio-X. Dá para corrigir depois com
`atas.py formato <id> demo`.

## Daily da Parresia
Tipo **Parresia** mostra a mesma linha discreta **Formato**: **reunião** (padrão) ou **daily**. Na daily:
- **Nada é medido**: sem Raio-X da fala, sem linha no histórico, sem nota no Sinapse, sem avaliação
  interna. Está no código (não é convenção): mesmo `atas.py fala` recusa.
- **Não precisa digitar ninguém.** As vozes saem da separação automática com um teto próprio da daily, e
  os nomes saem da **rodada** ("Rogério, e você?" seguido de outra voz) como **pista**: você confirma no
  `/ata`. A equipe (`daily_equipe`) e as frentes que você acompanha (`frentes_rastreadas`, hoje Frota WP
  SUP-953…959) ficam no `config.json`: complete a equipe uma vez.
- A ata da daily traz primeiro **Com você** (o que foi pedido a você ou toca suas frentes) e as
  **frentes**, depois **por pessoa** (fez · vai fazer · travado, com o card) e as decisões reais. Card
  só fica se o número foi dito perto da fala; card de frente dito que não virou item aparece como
  lacuna "menção não tratada".
- Duas dailies seguidas: na tela final, **Gravar a próxima daily** já grava, com "(2)" no título.
- Achar depois quem disse o quê: `daily SUP-953`, `daily deploy --pessoa Rogério --frente "Frota WP"
  --desde 2026-10-01`.

Os números do teto da daily (`daily_diar`) são **palpite** até calibrar numa daily real de 1 h
(`calibrar <id> --daily`). Detalhe: [ARQUITETURA §21](docs/ARQUITETURA.md).

## Marcar um momento
Ouviu algo que importa (um valor, um prazo, um "fechado")? Aperte **Ctrl+Alt+M**: funciona com o
Meet/Chrome na frente, sem trazer a janela do Atas. Ou clique **Marcar momento** na tela de gravação.
Sem som e sem popup; a tela (e o título na barra de tarefas) mostra "N momentos marcados". Apertar de
novo em até 2 s conta como a mesma marca. Com a transcrição ao vivo ligada, a marca aparece no
`ao-vivo.md` como `[mm:ss] ★ MARCA`, entre as falas (em até ~30 s), para o Claude que acompanha ver.

Na ata **interna**, a seção **Momentos marcados** vem no topo: para cada marca, o horário (clique leva
ao trecho na transcrição), o que foi dito de importante e a fala literal que sustenta; o trecho
analisado vai de 45 s antes a 15 s depois (você aperta depois de ouvir). Marca em trecho sem nada claro
aparece como "marcado — sem decisão clara no trecho". O entregável do cliente **não** leva marcas.

Lembrou depois? `marcar <id> 40:10 1:02:03` e `marcas <id>`; para a ata ler o trecho,
`processar <id> --forcar estrutura`. Áudio do celular: `importar <arquivo> --marcas "12:30,40:10"`.
O atalho muda em `marcar_atalho` no config (detalhe: [ARQUITETURA §20](docs/ARQUITETURA.md)).

## Intervencionista (o Claude responde sozinho)
Em **Mais opções**, marque **Intervencionista** (só aparece com GPU; liga o ao vivo junto). Vale só para
aquela reunião: começa sempre desligado. Na gravação, a linha discreta **Intervencionista ligado** liga
e desliga no meio da reunião (ligado no meio, só olha o que for dito dali em diante).

Ele lê o `ao-vivo.md` a cada 5 s e só chama o Claude quando um filtro sem IA acha algo: **pergunta para
você** (seu nome + "?", ou "você…?" logo antes de você falar; "você entendeu?" e "né?" no fim não contam),
**card** (SUP-NNN ou frente rastreada), **valor/prazo** (R$, reais, "15 mil", "dia 10", "em 15 dias") ou
**afirmação sobre um projeto** seu (nomes das notas de `03-PROJETOS` do Sinapse + `intervencionista.projetos`).
Na daily, só pergunta e card/frente. O Claude lê memória, Sinapse, repositórios e atas anteriores (só
leitura) e responde em até 2 linhas com a fonte, ou "não sei" (que não aparece na tela).

A resposta chega num **cartão no canto inferior direito**, por cima de tudo, **sem tirar o foco** da
chamada e sem som; some em 25 s ou com um clique. Teto: **20 chamadas por reunião**, uma por vez, no
mínimo **45 s** entre elas (`intervencionista` no config). Tudo fica em `intervencoes.jsonl` na pasta da
reunião (gatilho, trecho, resposta, fonte, custo), e o `/ata` confere. Detalhe: [ARQUITETURA §22](docs/ARQUITETURA.md).

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

## Modo treino (ensaiar sozinho)
1. Na janela, **Treinar** (no canto do "Nova reunião"). Escolha **Reunião** (ensaiar abertura,
   proposta, objeção, próximos passos) ou **Explicar um tema** (estudo), o assunto e a duração
   (2 a 5 min). Em "Mais opções": o alvo de ritmo e a nota do Sinapse para conferir o conteúdo.
2. **Começar**, fale, **Parar e ver o retorno**. Grava só o microfone.
3. A tela mostra 4 números com leitura (ritmo, pausas, muletas, entonação) contra o alvo, o último
   treino e as suas reuniões, e o retorno do Claude: **1 coisa para manter e 1 para mudar**.
   "Ouvir o trecho mais rápido" toca os 10 s mais corridos; "Ver tudo" abre a página completa.

Treino **nunca** entra no Raio-X das reuniões, no Sinapse nem em nada que sai da máquina.
```powershell
Invoke-Expression "$A treinar --tipo tema --assunto `"CAP`" --nota cap-e-consistencia"
Invoke-Expression "$A treino `"C:\...\ensaio.m4a`" --assunto `"proposta`""   # áudio já gravado (celular)
Invoke-Expression "$A treinos"                                                 # a evolução
```
Detalhe (o que mede, de onde vem cada régua, limites): [docs/ARQUITETURA.md §19](docs/ARQUITETURA.md).

## Onde fica cada coisa
Uma pasta por reunião em `atas-salvas/<data>_<hora>_<título>/`: `sessao.json` (contexto e
etapas), `transcricao.json`, **`ata.json`** (a ata canônica), `ata.md`/`.html`/`.pdf`,
`entregavel.pdf` (cliente), `audio/*.opus` e, se ligados, `ao-vivo.md` e `intervencoes.jsonl`. Treinos em `atas-salvas/treinos/<id>/` (`treino.json`,
`resultado.md`/`.html`, `audio/mic.opus`) e o histórico deles em `fala-analise/treinos.jsonl`. Tudo fora do git.

## Linha de comando
Sempre com o Python do venv:
```powershell
$A = "C:\Users\olive\.venvs\faster-whisper\Scripts\python.exe C:\Users\olive\Projetos\atas\local\atas.py"
Invoke-Expression "$A listar"            # reuniões
Invoke-Expression "$A mostrar ultima"    # a ata, lacunas e etapas
Invoke-Expression "$A buscar gateway --pessoa Mauro"
Invoke-Expression "$A retomar"           # gravação interrompida
Invoke-Expression "$A importar <áudio>"  # reunião presencial gravada no celular
Invoke-Expression "$A marcar ultima 40:10"   # marca um momento depois da reunião; `marcas ultima` lista
Invoke-Expression "$A daily SUP-953"        # quem disse o quê sobre o card, só nas dailies
```
Todos os comandos: `atas.py --help` e [docs/ARQUITETURA.md §11](docs/ARQUITETURA.md#11--receitas).

## Testes
```powershell
C:\Users\olive\.venvs\faster-whisper\Scripts\python.exe -m pytest tests -q   # 157 testes (151 rápidos + 6 lentos, -m "not lento" pula), ~70 s
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
