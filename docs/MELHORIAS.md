# Atas · problemas e melhorias

Backlog do sistema. Cada item diz o que aconteceu, onde, e o que precisa mudar. A ordem é
de prioridade. Fonte: a primeira reunião longa real da v2 (05/10/2026, 3h09, alinhamento com o
Valter, sessão `2026-10-05_2303_alinhamento-valter`), conferida item a item contra a transcrição.

## Status em 06/10/2026 · branch `v2.1-analises`

| # | Item | Estado | Onde |
|---|---|---|---|
| 1 | Editar a ata publicava sozinho | ✅ corrigido + teste que pega o defeito antigo | `atas.py::_reaplicar`, `tests/test_v21.py` |
| 2 | PDF do cliente com a transcrição inteira | ✅ o cliente recebe só os **trechos citados**; a interna segue inteira | `render.html` |
| 3 | Raio-X invisível | ✅ cartão na tela final + `atas.py fala <id>` | `app.py::_cartao_fala`, `atas.py::c_fala` |
| 4 | Ata rasa em reunião longa | ✅ acima de 60 min, estrutura em **blocos de 40 min** + consolidação | `estruturar.py` |
| 5 | Avaliação interna | ✅ etapa `avaliacao` (cliente/Parresia, ≥ 15 min) + passo 4c do /ata | `avaliar.py`, skill |
| 6 | Raio-X mais completo | ✅ ritmo, turnos, maior monólogo, interrupções, resposta, perguntas, cansaço por 30 min, voz (volume e entonação), metas | `analise_fala.py` |
| 7 | Prazo relativo | ✅ "N dias", "N semanas", faixa "4 5 dias", por extenso | `ata._data_coerente` |
| 8 | Lacunas demais | ✅ revisão de decisão não é mais lacuna automática | `ata.lacunas` |
| 9 | Valores, escopo, resumo por tema | ✅ listas auditadas `valores` (V) e `escopo` (S) + `por_tema` | `ata.py`, `render.py` |
| 10 | Trechos "Palavra Por Palavra" do turbo | ⏳ pendente (investigar) | — |
| 11 | Raio-X grava no Sinapse sem perguntar | ✅ documentado como a única exceção (regra 7 do /ata) | skill |
| — | Marcar trechos fora de pauta | ⏳ parcial: o prompt tira de resumo e itens; falta marcar na transcrição interna | — |

Medido na reunião de 05/10 com a v2.1: ritmo **193 pal/min** (meta 130–180), muletas
**36,9 → 53,5 por mil** do primeiro ao último bloco (cansaço), entonação **3,2 semitons**.

## 🔴 Problemas (corrigir antes do próximo uso com cliente)

### 1. Editar a ata publicava a página do cliente sozinho · **corrigido, falta commit**
`atas.py render`, `falantes` e `confirmar` chamavam `pipeline.reaplicar(publicar_=not sem_publicar)`,
ou seja, `True`, que é **pedido explícito** de publicação. Em 06/10 o `render` tentou publicar a
ata do Valter; só não saiu porque o Worker v2 não está no ar (HTTP 404). Corrigido em
`local/atas.py::_reaplicar` para `False if sem_publicar else None` (só atualiza a página se ela
**já** estiver no ar), igual ao `processar`. **Falta:** teste de regressão que garanta que
`render`/`falantes`/`confirmar` de uma ata não publicada não chamam `publicar()`.

### 2. O entregável do cliente leva a transcrição inteira
`render.html(cliente=True)` inclui a transcrição completa (`<details class="transc">`). A ata de
05/10 virou um PDF de **179 páginas** com 15 minutos de conversa pessoal fora de pauta.
Um clique em "Publicar" mandaria isso ao cliente.
**Mudar:** por padrão, o entregável do cliente **não** leva transcrição; ou leva só os trechos
citados pelos itens verificados. Transcrição completa só na ata interna, ou por opção explícita.
Junto: marcar trechos **fora de pauta** (pessoal, político) para nunca saírem da máquina.

### 3. O Raio-X da Fala calcula, mas ninguém vê
`analise_fala.py` roda (etapa `raio_x`) e grava `fala-analise/` e a nota
`08-CRESCIMENTO/fala-raio-x.md`, mas a v2 **não mostra nem abre nada**. A v1 abria o painel
`raio-x.html` sozinha no fim (`run.py::abrir`). O Pedro achou que a função tinha sumido.
**Mudar:** no fim do processamento, a janela mostra um cartão com os números da reunião
(fatia de fala, confirmações/min, muletas/1k, tendência) e um botão "Ver Raio-X"; e um comando
`atas.py fala <id|ultima>` que imprime o relatório e abre o painel.

### 4. A estrutura automática fica rasa em reunião longa
190 min de reunião foram estruturados em 86 s, numa passada só. Ficaram de fora: os R$ 550 da
primeira parcela, a lista de funcionalidades do IoT, as regras do pacote de conteúdo (mês
corrido, artigo interno × de convidado, manual só PDF) e os pontos do Instituto. Tudo isso
estava na transcrição e foi acrescentado à mão.
**Mudar:** acima de ~60 min, estruturar **por blocos** (30–40 min, com sobreposição) e
consolidar; ou uma segunda passada só para "o que ficou de fora" com a lista do que a primeira já
pegou.

## 🟡 Melhorias pedidas

### 5. Avaliação interna junto da ata (pedido do Pedro, 06/10)
Toda reunião de negociação ou cliente deve sair com uma **parte interna**, nunca no entregável:
- **Afirmações conferidas:** o que o Pedro afirmou que estava certo, errado ou exagerado, com o
  timestamp e o que é verdade (cruzando com código, memória e números medidos).
- **Valores e negociação:** se os preços fecham contra o piso de hora dele, as concessões feitas e
  com ou sem contrapartida, a ancoragem, o que ficou mal precificado.
- **Postura:** o que funcionou e o que trabalhar, com os números do Raio-X.
- **O que corrigir com o cliente:** promessas erradas que ele vai testar.

Modelo pronto: `atas-salvas/2026-10-05_2303_alinhamento-valter/avaliacao-interna.md`.
Como a conferência exige cruzar com código e memória, ela é trabalho do **/ata** (Claude Code com
acesso aos repositórios), não do `estruturar.py`. O /ata deve oferecer a avaliação sempre que o
tipo for `cliente` ou `parresia`.

### 6. Raio-X da fala mais completo ("análise da minha voz")
Hoje conta palavras (muletas, confirmações, bordões, fatia). Dá para medir também, com o que já
temos (timestamps por palavra e o áudio do microfone guardado 30 dias):
- **ritmo** (palavras por minuto) e a variação dele ao longo da reunião;
- **pausas** e silêncios longos; **turno médio** e o **maior monólogo**;
- **interrupções**: fala do Pedro começando com o outro ainda falando (sobreposição mic × loop);
- **cansaço**: muletas e confirmações por bloco de 30 min (a reunião de 05/10 foi das 23h às 2h);
- **voz** (do áudio): volume e variação de entonação, para "falo monótono?" e "falo baixo?";
- comparação com as **metas** da nota `fala-e-apresentacao` (ex.: "aí" e "a gente").

### 7. Prazo relativo na auditoria
"Limite máximo de 15 dias", "em 4 ou 5 dias" e "semana que vem" viram lacuna mesmo ditos, porque
`ata._data_coerente` só entende "dia N", dia da semana e "N/M". **Mudar:** aceitar "N dias" e
"N semanas" contados da reunião, com tolerância de ±1 dia.

### 8. Lacunas demais
A ata de 05/10 tem 26 lacunas, 15 delas "data de revisão" de decisão. Vira ruído e esconde a
lacuna que importa (prazo de pagamento, por exemplo). **Mudar:** `revisar_em` vazio não vira
lacuna por padrão; só o prazo de encaminhamento com dono.

### 9. Campos que faltam no esquema da ata
- **Valores e pagamentos** (quanto, quando, condição: "R$ 450 na publicação na Play Store").
  Hoje ficam escondidos dentro do texto de uma decisão.
- **Itens de escopo / requisitos** (a lista de funcionalidades do IoT não tinha onde entrar).
- **Resumo por tema**: a reunião tratou de 3 projetos (conteúdo, Instituto, IoT) e a ata tem um
  só `projeto` (vazio). O resumo para o cliente que o Pedro prometeu é **por tema**.

### 10. Transcrição do áudio da chamada com trechos "Palavra Por Palavra"
Entre 1:47:28 e 1:57:00 (o Valter compartilhando tela e mexendo em loja) o turbo devolveu falas
com cada palavra em maiúscula e quebrada ("Ele Ter Um Site Já Que Descreve…"). Investigar se é o
vocabulário (hotwords) num trecho de áudio ruim, e marcar trecho de baixa confiança.

### 11. A etapa `raio_x` grava no Sinapse sem perguntar
É de propósito (nota auto, sem título), mas contradiz a regra do /ata "nada no Sinapse sem OK".
Deixar escrito na skill que a nota `fala-raio-x.md` é a **única** exceção.

## Já anotados em outros lugares
- Worker v2 não deployado (login do wrangler trocado): `ARQUITETURA.md` §14.
- Ao vivo nunca testado em reunião real: `ARQUITETURA.md` §13.
