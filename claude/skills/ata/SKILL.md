---
name: ata
description: Fecha uma reunião gravada pelo Atas do Pedro — revisa nomes dos falantes e lacunas, mostra o que mudou desde a reunião anterior do mesmo assunto e PROPÕE (nunca publica) atualizações de memória, Sinapse, log de decisões e cards de ClickUp. Use quando o Pedro disser "/ata", "fecha a ata", "o que saiu da reunião", "o que ficou decidido com X", "revisa a última reunião", ou pedir para buscar algo dito numa reunião. Também serve durante a reunião ("o que ele acabou de dizer?") lendo a transcrição ao vivo.
---

# /ata — fechar uma reunião do Atas

O Atas (`C:\Users\olive\Projetos\atas`) grava, transcreve, e o Claude já gerou uma ata
estruturada (`ata.json`) no fim da gravação. Esta skill é a **segunda metade**: você, com
o Pedro, confere o que a máquina não pode confirmar sozinha e **propõe** o que atualizar.

**Todo comando** roda com o Python do venv (nunca o do PATH), pelo PowerShell:

```powershell
$A = "C:\Users\olive\.venvs\faster-whisper\Scripts\python.exe C:\Users\olive\Projetos\atas\local\atas.py"
Invoke-Expression "$A mostrar ultima"
```

## Regras que não se negociam

1. **Nada é publicado por você.** ClickUp, memória, Sinapse, log de decisões, e-mail ao
   cliente: tudo é **proposta** até o Pedro dizer sim *na hora*. OK de uma reunião não vale
   para a próxima.
2. **ClickUp só pelos wrappers com o token dele** em `~/Projetos/qa-parresia/scripts`
   (ex.: `clickup-comentar.sh`; comentário é Quill Delta, nunca Markdown — modelo em
   `cliente-comentar-sup689.py`). **Nunca** pelo MCP, que escreve como o Otávio.
3. **Operação da Parresia fica fora do Sinapse.** Tipo `parresia` não gera nota no vault;
   só `carreira` (a trajetória do Pedro) entra lá, em `08-CRESCIMENTO`.
4. **Só as falas de "Você" são do Pedro.** "Participante N" é o áudio da chamada, e a
   separação de vozes erra: um rótulo pode ser várias pessoas, e várias pessoas um rótulo.
   Tarefa sem dono confirmado não vira tarefa do Pedro.
5. **Nada inventado.** Item com `verificado: false` (citação não achada na transcrição) é
   apresentado como suspeito, nunca como fato. Prazo não dito é lacuna, não data.
6. **Credencial nunca aparece no chat.** A senha da página do cliente fica no `sessao.json`;
   diga onde está, não a imprima (a janela do Atas tem o botão de copiar).
7. **Única escrita automática no Sinapse:** a nota `08-CRESCIMENTO/fala-raio-x.md`, que a
   etapa `raio_x` regrava sem título de reunião. Todo o resto do vault é proposta. A **daily**
   (`formato daily`) nunca entra nela: fica fora de toda medição (passo 1e).
8. **Avaliação interna nunca vai ao cliente.** `avaliacao-interna*.md` fica na pasta da sessão;
   o render não lê esse arquivo. Fala de conversa pessoal (política, renda) não sai da máquina.

## Passo a passo

### 1. Qual reunião
- Sem argumento: `mostrar ultima`. Com nome/assunto: `listar` ou `buscar <termo>` e
  confirme com ele qual é.
- Leia o que `mostrar` imprime (ata + lacunas + etapas). Se alguma etapa **falhou**, diga
  primeiro, em uma linha, com o motivo. Se a ata está `pendente` (Claude falhou no fim da
  gravação): `processar <id> --forcar estrutura`.

### 1a. Momentos marcados (comece por aqui, se houver)
- O Pedro marcou na hora o que importava (Ctrl+Alt+M ou o botão). `marcas <id>` lista cada
  marca com o que a ata achou no trecho (45 s antes a 15 s depois); a seção "Momentos marcados"
  também abre o `mostrar`. **Apresente isto antes de tudo**, uma linha por marca: horário, o que
  foi dito, a citação, e em que item da ata virou (`na ata: D3, V2`).
- Marca **"sem decisão clara no trecho"** ou com **citação descartada**: leia você o trecho na
  transcrição (`mostrar <id> --transcricao`, do horário −45 s ao +15 s) e diga o que acha que ele
  marcou, com a fala literal; pergunte se é isso. Nunca preencha sem a fala.
- Marca **pendente** ("trecho ainda não lido pelo Claude", acrescentada depois com `marcar`):
  ofereça `processar <id> --forcar estrutura`.
- Decisão, valor, compromisso ou prazo de um trecho marcado que **não** está nas listas da ata
  é a lacuna mais importante da revisão: proponha o item com citação e `t` (passo 4b).
- Ele lembrou de outro momento? `marcar <id> <mm:ss>` (e `--remover` para tirar).

### 1b. Formato (só cliente, e só se estiver vazio)
- `mostrar` imprime `formato` na linha de cabeçalho. Se for cliente e vier "— (não informado)",
  **proponha** um, com o motivo em uma linha, e pergunte junto com o passo 2 (uma pergunta só):
  **descoberta** (o cliente explica o problema, o Pedro pergunta), **demo** (o Pedro mostra o
  sistema), **alinhamento** (status, combinados, próximos passos). Na dúvida, "não sei" é
  resposta válida: deixe vazio.
- Com o sim dele: `formato <id> <descoberta|demo|alinhamento>`. O comando refaz o Raio-X (a
  faixa da fatia de fala muda: descoberta 35–50%, demo/alinhamento 45–60%, vazio 35–55%).
- Parresia com cara de daily (rodada pelo nome, muitas vozes, status de cards) e `formato reunião`:
  **pergunte** se é daily. Nunca converta sozinho (`formato <id> daily` mexe no histórico do Raio-X).

### 1c. Projeto (cliente e carreira, só se estiver vazio)
- O sinapse-app mostra os compromissos do Pedro na tela **Frentes** lendo `ata.json` +
  `sessao.json`, e a reunião só cai na frente certa se `sessao.json.projeto` tiver o **nome da
  nota do vault** (o app casa o slug com o nome do arquivo da nota, o título ou a última pasta
  de `pastas:`). Ex.: `toninho-motores`, `celiware-ihm`, `atas`, `desbravando`,
  `instituto-automacao`.
- Se o tipo é `cliente` ou `carreira` e o `mostrar` diz "sem projeto": **proponha** um, casando
  título, participantes e conteúdo com as notas de `C:\Users\olive\Projetos\sinapse\03-PROJETOS`
  e `04-NEGOCIO` (**só leitura** do vault), com o motivo em uma linha. Se a reunião cobriu vários
  projetos, diga isso e sugira o principal.
- Pergunte junto com o formato/quem é quem (uma pergunta só). Com o sim dele:
  `tipo <id> <tipo> --projeto <slug>`. Não mexa em reuniões antigas por conta própria.

### 1d. Reunião presencial do celular (`origem: celular` no `mostrar`)
- Um canal só: **"Você" foi estimado pela voz** (amostra de referência ou tom) e está "a
  confirmar"; o Raio-X e a avaliação ficam `pendente` até ele confirmar. Pergunte isso
  **primeiro**, mostrando 2–3 falas de "Você" com `[mm:ss]` e a evidência do `mostrar`.
  - Acertou: `confirmar <id>` (ou `falantes <id> "Você=Você"`).
  - Errou / ninguém virou "Você": `falantes <id> "Participante 2=Você"` (troca os rótulos na
    transcrição). Se a ata já estava estruturada, ofereça `processar <id> --forcar estrutura,avaliacao`.
  - O Raio-X roda sozinho depois da confirmação.
- **Tipo pendente** (importado sem `--tipo`): pergunte o tipo junto (nunca deduza cliente):
  `tipo <id> <cliente|parresia|carreira|pessoal>`. Até lá não há entregável nem publicação.

### 1e. Daily da Parresia (`formato daily` no `mostrar`) — roteiro próprio, curto
A daily é reunião diária interna, >1 h, 7+ pessoas, e o Pedro fala pouco. Ela fica **fora de toda
medição** (sem Raio-X, sem histórico, sem nota no vault, sem avaliação interna: está no código). A ata
é `atas/daily@1`: **Com você**, as **frentes rastreadas** (`frentes_rastreadas` no config, hoje Frota
WP SUP-953…959), **por pessoa** (fez · vai fazer · travado, com card) e decisões/encaminhamentos reais.
Nesta ordem, e **só isto** (pule os passos 3, 4, 4b, 4c, 4d e a tabela do passo 5):
1. **Quem falou, pela rodada.** O `mostrar` traz "Quem falou, pela rodada (pista)": rótulo → nome com
   a evidência `[mm:ss] "Rogério, e você?" → Participante 3 começa a falar`. Mostre a lista (rótulo,
   nome proposto, 1 evidência, e a fala de abertura do rótulo para ele reconhecer a voz) e pergunte
   **de uma vez só**. Com o sim: `falantes <id> "Participante 3=Rogério" ...` e `confirmar <id>`.
   Nunca confirme sozinho; nome sem pista fica sem nome. Os números da diarização da daily são palpite
   até calibrar (`calibrar <id> --daily`): se ele disser quantas pessoas falaram, rode e mostre.
2. **Com você.** Os itens `C` (pedido · para você saber · decisão), com quem disse, card e `[mm:ss]`.
   É a lista que ele lê primeiro; item `⚠ origem não localizada` é suspeito.
3. **Frentes.** Para cada frente rastreada, o que foi dito (menções com `[mm:ss]`), em que item virou, e
   as lacunas **"menção não tratada"** (card dito que não virou item) e **"card citado mas não dito
   perto"**: leia o trecho (`mostrar <id> --transcricao`) e proponha o item com citação literal, ou
   diga que era só menção. Proponha a **atualização da frente** (ex.: comentário no card SUP-953 pelo
   wrapper, Quill Delta, com a citação e o timestamp) — rascunho, nunca enviado sem o sim dele.
4. **Decisões reais** → `decisoes <id>` → `~/Projetos/qa-parresia/rotinas/decisoes.jsonl`, com o sim.
- **Não proponha** card nem memória para assunto que não é do Pedro (a rodada dos outros fica na ata,
  para a busca). Sinapse: nada (Parresia). Publicação: nunca sem o OK dele, na hora.
- "Quem disse o quê sobre o SUP-953?" → `daily SUP-953` (ou `daily <termo> --pessoa Rogério
  --frente "Frota WP" --desde 2026-10-01`): data, sessão, quem (nome confirmado ou "Participante 3
  (Rogério?)"), card e trecho; se veio da transcrição e não de um item, diga isso.
- Reunião antiga que era daily (ex.: 09/10): **pergunte** antes; com o sim, `formato <id> daily` (tira
  do histórico com backup, refaz a nota do vault, guarda a avaliação como `*.antes-daily.*`) e, se
  ele quiser a ata nova, `processar <id> --forcar transcricao,estrutura` (só com o áudio guardado).

### 2. Quem é quem (sempre antes de tudo)
- Mostre só os rótulos que importam: com nome deduzido "a confirmar", ou sem nome e com fala
  relevante. Para cada um, a evidência (`[mm:ss] trecho`).
- Pergunte de uma vez só, em lista. Ao confirmar:
  `falantes <id> "Participante 1=Valter" "Participante 3=Valter" "Participante 2=Sara"`
  (vários rótulos podem ir para o mesmo nome). Depois `confirmar <id>` marca como revisada.
- Estes comandos reauditam e regeram página/PDF, e **atualizam** a página do cliente se ela
  já estava no ar (mesma URL, mesma senha). Use `--sem-publicar` se ele não quiser.

### 3. Lacunas
- Liste as lacunas **que ele consegue fechar** (dono e prazo de encaminhamento, data de
  revisão de decisão). Não despeje a lista inteira: agrupe e pergunte o essencial.
- Ao fechar uma, edite o `ata.json` da pasta da sessão e ponha o campo em `manual`
  (ex.: `"prazo": "2026-10-10", "manual": ["prazo"]`) — senão a auditoria o remove por
  não estar na transcrição. Depois: `render <id>`.
- Decisão sem `revisar_em`: **sugira** uma data (padrão +30 dias) e diga que é sugestão.
  "Decisão sem revisão vira regra por esquecimento." (Desde a v2.1 isso não é mais lacuna
  automática: era ruído que escondia a lacuna que importava.)
- Prazo dito como "em 15 dias" / "4 ou 5 dias" / "duas semanas" agora é conferido pela
  auditoria; se ainda assim virou lacuna, o Pedro confirma e você põe em `manual`.

### 4. O que mudou desde a última
- `anterior <id>` devolve a reunião anterior do mesmo projeto (ou com as mesmas pessoas).
  `mostrar <anterior>`: para cada encaminhamento dela, diga se nesta reunião ele foi
  **citado como feito**, **citado como pendente** ou **não apareceu** — com o timestamp.
  Decisões que mudaram: mostre a de antes e a de agora lado a lado.

### 4b. Reunião longa: leia a transcrição inteira
- Acima de ~60 min, a ata automática sai em blocos, mas ainda pode deixar coisa de fora.
  Leia a transcrição toda (junte as falas por pessoa e por tempo) e confira contra a ata:
  **valores**, **escopo**, regras combinadas e **pedidos que o Pedro fez a você**.
- O que faltar entra no `ata.json` com citação literal e timestamp (a auditoria confere), com
  backup antes. Depois `render <id>`.

### 4c. Avaliação interna (cliente e Parresia) — "ele evoluindo significa eu evoluindo"
- A etapa `avaliacao` gera `avaliacao-interna.md` sozinha (Claude só com leitura de código e
  memória). Leia, **confira** e complete; se não existir, escreva. Seções:
  1. **Afirmações do Pedro conferidas**, as erradas primeiro: tabela Quando | O que disse |
     O que é | Por que importa. Só chame de errado o que você conferiu (grep no código,
     memória, número medido); o resto é "não conferido".
  2. **Valores** contra o piso de hora dele (`negociacao.piso_hora` no config).
  3. **Negociação**: ancoragem, concessões com/sem troca, escopo × preço, custo revelado.
  4. **Postura**, com os números de `atas.py fala <id> --sem-abrir` (metas, cansaço, voz).
  5. **O que corrigir com o cliente.**
- Releia os números antes de entregar. Apresente a avaliação no chat (ele quer ler ali); o
  arquivo fica como registro.
- Modelo: `atas-salvas/2026-10-05_2303_alinhamento-valter/avaliacao-interna.md`.

### 4d. Raio-X da Fala
- `atas.py fala <id>` recalcula e abre o painel: fatia de fala, confirmações/min,
  muletas/1k, ritmo (pal/min nos turnos), maior monólogo, interrupções, cansaço por bloco de
  30 min e voz (volume e entonação, do áudio do microfone). Metas em `metas_fala` no config.

### 5. Propostas (roteadas pelo TIPO da reunião)

| Tipo | Memória do Claude | Log de decisões | Sinapse | ClickUp |
|---|---|---|---|---|
| `parresia` | só fatos duráveis (papel, pessoas, estado de frente) | `~/Projetos/qa-parresia/rotinas/decisoes.jsonl` | **nada** | cards/comentários propostos |
| `parresia` + `daily` | nada de assunto que não é do Pedro | só as decisões reais | **nada** | só atualização das frentes rastreadas e o "Com você" (passo 1e) |
| `carreira` | sim | — | `08-CRESCIMENTO/` (ex.: `transicao-para-po.md`) | — |
| `cliente` | estado do projeto | — | nota do projeto em `03-PROJETOS/` (decisão e conhecimento, sem conteúdo do cliente, sem número operacional) | só se for projeto com board |
| `pessoal` | se durável | — | nota do tema | — |

- **Log de decisões**: `decisoes <id>` já imprime cada decisão verificada no formato do
  `decisoes.jsonl` (`data, decisao, contexto, quem, destrava, revisar_em, origem`).
  Mostre as linhas, preencha `destrava` com ele, e só então acrescente ao arquivo.
- **ClickUp**: para cada encaminhamento com dono e que é trabalho de board, mostre o
  rascunho (título, lista, responsável, prazo, descrição com a citação e o timestamp).
  Nada é criado sem o "sim" dele, e cada card é confirmado um a um se ele pedir.
- **Memória / Sinapse**: diga o arquivo e a frase exata que entraria. Ao fim de uma
  entrega, o fluxo dele é: revisão → commit/push → você registra no Sinapse.

### 6. Mandar ao cliente (tipo `cliente`)
- O entregável é `entregavel.pdf` (só itens verificados, só nomes confirmados, marca RYZE;
  resumo só depois de todos os falantes confirmados).
  Abrir = Explorer na pasta com o arquivo selecionado: `abrir <id> entregavel.pdf`.
- A página online **só sobe quando ele manda**: botão na janela, ou `publicar <id>` depois do
  sim dele na hora. Tem senha (no `sessao.json`, nunca no chat) e expira em 90 dias.
  `despublicar <id>` apaga do ar.
- Reunião antiga (legado) vem com tipo INFERIDO: `tipo <id> cliente --projeto X` confirma, e
  só então ela pode ser publicada. Mudar para interno tira a página do ar.

## Perguntas sobre reuniões passadas

"O que ficou decidido com o Mauro sobre X?" →
`buscar X --pessoa Mauro` (procura nas decisões/encaminhamentos e, se não achar, na
transcrição), depois `mostrar <id>` da mais relevante. Responda com data, quem e o
timestamp; se a fonte for só a transcrição (não um item da ata), diga isso.
As reuniões de antes da v2 (jul–set/2026) vieram do backup `.md`: não têm áudio, e a
separação de participantes delas é ruim (um participante virou dezenas de rótulos).

## Durante a reunião (ao vivo)

Se o Pedro ligou "Transcrição ao vivo", `ao-vivo` devolve o caminho do `ao-vivo.md` da
gravação em curso. Leia as últimas linhas para responder o que ele perguntar. É
transcrição preliminar, sem separar participantes; a ata final é refeita do zero.
Uma linha `[mm:ss] ★ MARCA` é o Pedro apertando Ctrl+Alt+M naquele instante: olhe as falas logo antes
(ele aperta depois de ouvir) — é o que ele achou importante.

Se o intervencionista estava ligado (ARQUITETURA §22), a pasta tem `intervencoes.jsonl`: cada resposta
que apareceu no cartão (gatilho, trecho, resposta, fonte, custo). Ao fechar a ata, confira as respostas
mostradas contra a ata e a fonte, e diga ao Pedro qual estava errada ou não ajudou (é a calibragem do
filtro). Nada dali vira fato sem a citação da transcrição final.
