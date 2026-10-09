---
translation_of: guides/curate.md
---

# Curadoria do acervo

Esta página é para o arquivista que trabalha na SPA de curadoria. Ela diz, tela por tela, **que
decisão se toma ali, o que o clique escreve e se dá para desfazer** — e nomeia o que não tem volta
nenhuma.

A SPA é servida pela própria API (uma origem, sem CORS), e toda tela lê e escreve pelo cliente gerado
a partir do contrato OpenAPI. As telas são declaradas em `apps/curator/src/router.tsx` e a navegação
em `apps/curator/src/components/layout/AppShell.tsx`. O menu tem **16 entradas**: as telas que ninguém
abre no meio da catalogação — o plano de arranjo, os catálogos, o painel de workers, o ledger de
execuções, os diagnósticos e as contas — são cartões de `/configuracoes`, não itens de menu
(*Configurações*, abaixo). Uma rota também não vem do menu: a ficha da descrição,
`/acervo/$descriptionId`, é alcançada pela lista e pela árvore. O roteador, por isso, declara **25
telas**. O próprio menu pode ser recolhido a ícones, o que é uma escolha de apresentação e não de
permissão — *O menu se recolhe a ícones*, abaixo.

Vale ler duas páginas junto com esta: [Modelo de dados](data-model.md) para o que os ledgers e as
tabelas significam, e [Instalação e implantação](install.md) para o esquema, as contas e a
implantação em volta das telas.

## A única regra

Toda escrita ou tem desfazer, ou avisa que não tem. O merge guarda um ledger; a purga tem prévia e
não tem desfazer; a edição da descrição guarda o antes e o depois. Quando uma tela não tem nem uma
coisa nem outra, esta página diz em negrito.

O trabalho de leitura não declara permissão: ler é o que uma sessão autenticada é. As telas que
decidem carregam a área em que escrevem, e a API recusa com 403 e uma frase quando a conta não a
carrega.

## O que não tem volta

!!! warning "Estas escritas não têm desfazer"

    As operações abaixo apagam ou dissolvem uma linha que nada mais reconstrói. A purga de stopwords
    mostra uma prévia; a exclusão pede que você digite o código de referência; o merge de entidades
    não tem nem uma coisa nem outra — o painel avisa. Leia a confirmação.

- **Purga de stopwords** — `POST /api/v1/taxonomy/tags/stopwords/purge`. Apaga toda tag cujo nome
  seja um termo banido nos eixos `TAG` ou `ALL`. Os vínculos caem em cascata e a classificação de
  assunto da tag vai junto. Ela tem prévia (`POST
  /api/v1/taxonomy/tags/stopwords/purge/preview`, que lista as tags que morreriam) e **não tem
  desfazer**: o merge guarda o estado anterior e restaura, a purga não. Banir
  (`POST /api/v1/taxonomy/tags/stopwords`) não apaga nada; só a purga apaga, e a mensagem de sucesso
  avisa que isso não aparece no ledger de merges.

- **Excluir uma descrição** — `DELETE /api/v1/documents/{description_id}`. Definitivo. A API grava
  antes um retrato ISAD(G) da linha inteira no ledger de exclusões, e esse retrato é uma **trilha,
  não uma lixeira**: `/acervo/excluidas` o mostra e nada o restaura. O ledger de revisões não
  sobrevive (ele cai junto com a descrição), e é por isso que o retrato existe. Uma descrição com
  filhos não pode ser excluída — o serviço recusa e diz quantos estão abaixo; exclua ou mova os
  filhos primeiro. A tela pede que o arquivista digite o código de referência (ou o identificador,
  quando não há código) antes de o botão liberar.

- **Unificar entidades** — `POST /api/v1/taxonomy/entities/merge`. As entidades absorvidas deixam de
  existir, seus vínculos passam para a canônica e suas grafias viram sinônimos, para o extrator
  continuar reconhecendo-as. Entidades **não têm catálogo de propostas nem ledger**, então este é o
  merge sem desfazer — o privilégio das tags é ter ledger. O painel avisa em vez de oferecer um
  botão de volta, e não há rota de prévia: a tela declara o efeito documentado em vez de inventar
  números. Renomear a canônica faz parte da mesma escrita, e o nome antigo vira sinônimo.

- **Excluir ou purgar entidades sem vínculo** — `DELETE /api/v1/taxonomy/entities/{entity_id}` e
  `POST /api/v1/taxonomy/entities/orphans/purge`. A tela só oferece a exclusão numa linha cuja
  contagem de uso é zero, e a purga remove toda entidade que nenhuma descrição carrega, então nenhum
  vínculo se perde — mas a linha vai embora e não há ledger que a restaure.

Há ainda uma escrita cujo efeito alcança o passado: **um veto de NER** (`POST
/api/v1/taxonomy/entities/ner-exclusions`) expurga as entidades já extraídas daquela grafia, com os
vínculos. Remover o veto (`DELETE`, o "remover veto" da tela) reabre o termo para as próximas
extrações; **não traz de volta** o que o veto já apagou.

### O lote que tem desfazer

Materializar o arranjo a partir do plano (`POST /api/v1/hierarchy/materialisation/apply`) é
reversível, e o desfazer está na tela. Ele só roda depois de uma prévia
(`POST /api/v1/hierarchy/materialisation/preview`, calculada pelo mesmo planejador) e grava uma
entrada de ledger por execução (`GET /api/v1/hierarchy/materialisation/log`). O desfazer é
`DELETE /api/v1/hierarchy/materialisation/log/{materialisation_id}`, e ele restaura exatamente o que
a execução mudou:

- toda descrição que ele moveu volta à **unidade superior e ao nível que tinha antes**;
- os nós que a execução **criou** são apagados — o que só é possível restaurando primeiro, porque a
  auto-referência é `RESTRICT`;
- os planos que apontavam para um nó apagado voltam a "não materializado", para o próximo apply não
  tentar ligar descrições a uma linha que não existe mais.

O desfazer **recusa** quando uma execução posterior ligou descrições que o ledger não conhece, porque
reverter ali desligaria trabalho que nunca fez parte desta decisão. Reverter uma execução concluída é
um fato novo e registrado: a entrada guarda `undone_at` e quem desfez.

## Revisão, difusão e o que a IA não pode reescrever

### O ciclo de revisão

`review_status` é o ciclo da validação humana sobre o trabalho da IA. Os cinco valores são
`PENDING_AI`, `AI_APPROVED`, `NEEDS_REVIEW`, `HUMAN_APPROVED` e `REJECTED`. `HUMAN_APPROVED` é o
escudo: o predicado de escrita do pipeline de IA o exclui, então nenhum worker de relatório reescreve
em silêncio uma descrição que o arquivista validou. Editar qualquer campo ISAD(G), ou as tags e
entidades da descrição, grava `HUMAN_APPROVED` por `PATCH /api/v1/documents/{description_id}` (ou
pelas rotas de vínculo), registra o antes e o depois em `archive_document_revisions` e tira a
descrição da fila da IA.

### As duas exceções documentadas

- **`worker_embedding`** de propósito não usa o predicado de escrita da IA. O embedding é um índice
  derivado do texto, não conteúdo arquivístico: uma descrição `HUMAN_APPROVED` cujo texto mudou
  precisa ser re-embedada, ou a busca semântica serviria um vetor velho. Ele escreve só a coluna
  `embedding` e o próprio carimbo (o MD5 do texto efetivo), e pula descrições `REJECTED`.
- **Publicar não é travar.** `is_published` é escolhido pelo mesmo `PATCH` de qualquer campo ISAD(G),
  e **não** congela a descrição contra a IA. O predicado de escrita lê apenas `review_status`. Reusar
  o status de revisão para a difusão teria feito uma correção de digitação equivaler a publicar, e
  teria travado toda descrição publicada contra o melhoramento da IA.

Os outros workers de IA ficam de fora de uma descrição `HUMAN_APPROVED`; o que uma pessoa decidiu não
é reescrito pelo pipeline.

### Difusão não é revisão

Revisão é uma afirmação sobre o registro; publicação é uma decisão sobre o que expor. `is_published`
é coluna própria, editada pela caixa "Publicar na difusão" na aba `Descrição` da ficha, e o predicado
público é exatamente `is_published`. Nada é publicado por padrão, então a superfície de difusão nasce
vazia.

Publicar expõe a descrição pela superfície aberta, sem autenticação:

- `GET /api/v1/public/documents` e `GET /api/v1/public/documents/{description_id}`.

Duas regras valem ali. O filtro `published_only` é definido **no servidor** e não é parâmetro do
cliente, então nenhuma query string pode pedir um registro não publicado; e um identificador não
publicado responde 404, nunca 403, porque um status distinto confirmaria que a descrição existe.

A projeção pública é mais estreita que a do curador, campo a campo. Ela carrega os campos ISAD(G)
`original_title`, `final_title`, `document_date`, `reference_code`, `level`, `scope_content`,
`language_name` e `producers`; o enriquecimento `typology`, as tags (nome), as entidades (nome e
tipo) e as gavetas de assunto (nome e contagem); a miniatura; o ramo (`ancestors`) e o
`children_count`. Ela deliberadamente **não** carrega o processo de curadoria nem a narrativa não
publicada: `review_status`, `is_anomaly`, `anomaly_reasons`, `archivist_notes`, `provenance`,
`suggested_final_title`, `admin_bio_history`, `admin_archival_history` e `access_conditions`. O
conjunto de facetas públicas também é mais estreito — `anomaly_reason` não é publicado.

## Quem pode decidir o quê

A autorização é um nível declarado por operação, imposto por um único guard. As quatro permissões de
escrita são áreas, não botões:

| Permissão | A área |
| --- | --- |
| `CURATE` | o registro e seus assuntos: os campos ISAD(G), vínculos, tags, entidades, conflitos e as taxonomias que os movem |
| `CATALOGUE` | os catálogos fechados: níveis, tipologias, vocabulário do acervo, gavetas de assunto, regras de limpeza e trechos |
| `OPERATE` | os workers de IA: rodar um, mudar o padrão persistido dele e o painel de saúde |
| `ADMIN` | contas e sessões |

| Papel | Carrega | Lê |
| --- | --- | --- |
| `VIEWER` | nada | tudo o que uma sessão autenticada alcança |
| `CURATOR` | `CURATE`, `CATALOGUE` | o mesmo, mais as telas que decidem o registro e os catálogos |
| `ADMIN` | `CURATE`, `CATALOGUE`, `OPERATE`, `ADMIN` | tudo, incluindo os workers e as contas |

Ler não é permissão: é o que uma sessão autenticada é, e uma leitura pura não declara nada.

### O menu esconde; nunca concede

A casca filtra as entradas pela área em que a tela **escreve**
(`apps/curator/src/lib/permissions.ts`, um espelho do mapa de papéis do servidor), e um grupo vazio
não é renderizado. As telas que só leem não carregam permissão e ficam visíveis para todo papel:
Início, a lista do acervo, a árvore, a trilha de excluídas e o diagnóstico do arranjo. Um `VIEWER`
vê, portanto, exatamente os grupos "Curadoria" e "Acervo" — todos os outros grupos existem para
decidir, e ficam escondidos.

A mesma regra governa os cartões de `/configuracoes`, e é o catálogo de cartões
(`apps/curator/src/lib/settings.ts`) que a página e a entrada de menu leem: um cartão fica escondido
quando a conta não carrega a área em que a tela escreve, uma aba com todos os cartões escondidos não é
renderizada, e a entrada fica no menu enquanto **ao menos um** cartão for alcançável. Um `VIEWER` não
tem Configurações nenhuma, e uma URL direta até ela chega a uma página que diz por que está vazia em
vez de fingir que quebrou.

O espelho é de mão única de propósito. Ele encurta o menu; nunca faz a API aceitar uma requisição. Uma
URL direta para uma tela em que a conta não pode trabalhar ainda chega à API, e a API responde 403
com uma frase — essa é a verdade, e a entrada escondida é uma cortesia.

### O menu se recolhe a ícones

Um controle no cabeçalho do próprio menu o dobra numa coluna de ícones de 64px e o devolve, e o
navegador lembra a escolha: a largura de uma coluna da tela é estado de apresentação, então mora no
`localStorage` e não na conta — a API não tem coluna para isso.

Recolhido, cada entrada mantém o ícone; o rótulo continua sendo o nome acessível do link e o `title`
carrega rótulo e dica, de modo que a dica fica escondida e nunca cortada. A entrada ativa mantém a cor
de destaque, os títulos de seção viram filetes e o rodapé de sessão vira a inicial da conta mais dois
botões de ícone. O nome da atribuição sai do menu, mas não da página: a atribuição é renderizada no pé
de toda tela (`AttributionFooter`, ADR 0006). Os ícones vêm do `lucide-react`, um glifo por entrada.

## Curadoria

| Tela | Decisão | Reversível? |
| --- | --- | --- |
| Início — `/` | qual fila pendente abrir | sim (só leitura) |

### Início — `/`

A lista de trabalho. Ela responde "o que precisa de mim hoje?" com um cartão por fila e a rota que
resolve a pendência, já filtrada. É uma **leitura de predicados existentes**
(`GET /api/v1/curation/inbox`): nada é escrito. Um cartão que a casca não reconhece como abrível
mostra "tela pendente" em vez de apontar para o vazio.

## Acervo

| Tela | Decisão | Reversível? |
| --- | --- | --- |
| Lista e busca — `/acervo/lista` | como recortar o acervo | sim (só leitura) |
| Árvore — `/acervo/arvore` | onde a descrição fica no arranjo | sim, movendo; remover o nó significa excluir a descrição |
| Excluídas — `/acervo/excluidas` | nenhuma (o ledger do que saiu) | sim (só leitura) |
| Descrição — `/acervo/$descriptionId` | o registro, seus assuntos e seu lugar | em geral sim; a exclusão não |

### Lista e busca — `/acervo/lista`

A busca facetada do acervo: o termo (lexical ou semântica), tipologia, gaveta de assunto, tipo de
entidade, nível, um ramo do arranjo e um intervalo de datas. A URL é o estado, então uma lista
filtrada é compartilhável e o botão voltar funciona. Nada é escrito. O modo semântico traz uma nota
honesta: a qualidade medida dele é fraca (Hit@10 0,625), então prefira o lexical quando souber o
termo.

### Árvore — `/acervo/arvore`

O arranjo como navegação. Selecionar um nó mostra o ramo, os filhos e as descrições dentro dele, tudo
em leitura. A única escrita da tela é "Criar nó" (`POST /api/v1/hierarchy/nodes`, `CURATE`): declara
um Fundo, uma Seção ou uma Série que a origem não entregou e que o fatiador, por isso, não tem como
propor. A descrição nova nasce `HUMAN_APPROVED`, e a escada é validada contra o pai escolhido pela
mesma regra de um mover. O lugar dela é reversível movendo a descrição; remover o nó significa
excluir a descrição, o que é definitivo.

!!! note "Arranjo não é assunto"

    Este é o eixo objetivo — onde a descrição fica na proveniência. Os selos de assunto vivem na
    lista e na ficha; misturá-los aqui ensinaria o arquivista a "consertar" um assunto arrastando uma
    descrição para outro ramo.

### Excluídas — `/acervo/excluidas`

A trilha das exclusões, em leitura (`GET /api/v1/documents/deletions`), com busca e paginação no
servidor porque a trilha não tem teto. Ela **não é uma lixeira**: cada entrada é o retrato ISAD(G)
que a API gravou antes de excluir, e nada aqui restaura coisa alguma. Responde "fui eu que excluí
isto?" — código, título, nível, quem excluiu, quando, quantos filhos havia, e o retrato inteiro sob
demanda.

### Descrição — `/acervo/$descriptionId`

A ficha, com quatro abas na URL. O título sugerido aparece **ao lado** do campo que ele propõe e
nunca é o valor guardado: ele é derivado na leitura a partir dos trechos de escopo `TITLE`, e só o
arquivista escreve `final_title`.

#### Descrição

A decisão é o próprio registro: qualquer campo ISAD(G), o nível, a tipologia, `access_conditions` e
`is_published`, com uma nota do porquê. A escrita é `PATCH /api/v1/documents/{description_id}`
(`CURATE`). Ela registra o antes e o depois do que mudou em `archive_document_revisions`, grava a
autoria a partir da sessão e define `HUMAN_APPROVED` — o que tira a descrição da fila da IA.
Reversível: outra edição registra uma nova revisão; o histórico é só de acréscimo e o valor anterior
fica visível na aba `Histórico`. Publicar e retirar usam o mesmo comando e são igualmente
reversíveis.

#### Assuntos

A decisão é quais tags e entidades esta descrição carrega e em que gaveta cada tag fica. As escritas
são `POST`/`DELETE /api/v1/documents/{description_id}/tags[/{tag_id}]` e o par de entidades
(`CURATE`), mais `PATCH /api/v1/taxonomy/tags/{tag_id}` para a gaveta. Associar e desassociar são
reversíveis: a revisão guarda a **lista inteira de nomes** de cada lado, e chamar a mesma rota duas
vezes não escreve revisão nenhuma.

!!! warning "A gaveta é uma decisão sobre o vocabulário, não sobre esta descrição"

    Mudar a gaveta de uma tag move a tag em **todas** as descrições que a carregam, e a tela diz
    isso ao lado do seletor. Escolher "sem gaveta" devolve a tag ao classificador de assunto, que
    vai tentar arquivá-la de novo na próxima execução.

#### Arranjo

A decisão é onde esta descrição fica e em que nível. A escrita é
`POST /api/v1/hierarchy/nodes/{description_id}/move` (`CURATE`), e a rota declara para onde o nó vai:
`new_parent_id=null` significa "para a raiz", então não há como mudar só o nível — a tela sempre
envia a unidade superior que está mostrando. A API valida antes de escrever (um Item não pode ter
filhos, um Dossiê não pode ficar sem pai, mover para dentro da própria subárvore é recusado), e mover
uma unidade leva a subárvore inteira: o caminho é reescrito em uma instrução. A mudança fica no
histórico desta descrição e é reversível movendo a unidade de volta.

#### Histórico

As revisões desta descrição, em leitura, campo a campo com o valor antigo e o novo. No fim do
histórico fica a exclusão, longe do cabeçalho de propósito — é a única ação que remove um registro
para sempre, e a confirmação (digitar o código de referência) é o que separa "excluir" de "excluir
*esta* descrição". Veja **o que não tem volta** acima.

## Arranjo

O plano é alcançado por `/configuracoes` — decidir as rungs é trabalho de montagem, não curadoria do
dia a dia — e o diagnóstico ficou no menu, sob "Acervo", ao lado da árvore que ele lê. Sem o plano, o
grupo "Arranjo" teria uma linha só, então ele deixou de existir.

| Tela | Decisão | Reversível? |
| --- | --- | --- |
| Plano de arranjo — `/arranjo/plano` | aprovar ou rejeitar cada rung proposta, e materializar a árvore | sim — a decisão pode ser reaberta, e a materialização tem desfazer |
| Diagnóstico — `/arranjo/diagnostico` | nenhuma (a evidência; o conserto é em outra tela) | sim (só leitura) |

### Plano de arranjo — `/arranjo/plano`

A máquina lê os códigos de referência e propõe as rungs; a decisão é do arquivista. Em cada rung a
evidência vem primeiro — a contagem de descrições, os níveis declarados, as amostras — e o formulário
por último:

- **Propor níveis** — `POST /api/v1/hierarchy/plans/suggest` (`CURATE`). Escreve as perguntas. É
  idempotente por código e nunca reescreve uma rung que saiu de `SUGGESTED`, então a mesma pergunta
  não é feita de novo.
- **Aprovar** uma rung — `PATCH /api/v1/hierarchy/plans/{plan_id}` (`CURATE`) com `APPROVED`, o nível
  escolhido, um título opcional, um código opcional em "fundir em" e uma nota. Aprovar **exige** o
  nível: é a decisão que o código não sabe tomar.
- **Rejeitar** — a mesma rota com `REJECTED`. Uma rung rejeitada deixa suas descrições órfãs de
  propósito: elas caem na rung aprovada mais próxima acima.
- **Reabrir decisão** — a mesma rota com `SUGGESTED`. Reversível: a decisão volta para a fila e a
  próxima proposta pode atualizar a evidência dela. A decisão nunca é sobrescrita por uma proposta
  nova.

O painel lateral materializa a árvore: ele sempre oferece "Conferir o que será feito" primeiro, e o
botão de aplicar fica desabilitado até a prévia existir. Só as rungs aprovadas são materializadas. A
prévia e o apply compartilham um planejador, então o número aprovado é o número escrito. O que o
desfazer restaura está descrito em **o lote que tem desfazer**.

### Diagnóstico — `/arranjo/diagnostico`

O diagnóstico estrutural, uma seção por problema, cada uma com sua contagem e sua evidência (uma
seção com zero continua visível, porque saber que a checagem rodou importa). Ele **não oferece
correção silenciosa**: cada linha leva à tela onde o conserto é uma decisão registrada — o plano, a
árvore ou a aba de arranjo da descrição. As contagens se sobrepõem de propósito (um Dossiê na raiz é
ao mesmo tempo `ORPHAN` e `DOSSIER_WITHOUT_PARENT`), por isso não há um total geral.

## Catálogos

Os três são alcançados por `/configuracoes`, sob *Arranjo e catálogos*: são o vocabulário com que o
trabalho é escrito, não o trabalho — e é por isso que o menu não os carrega mais.

Os dois catálogos fechados que o arquivista mantém e o vocabulário do acervo. Nenhum deles apaga: uma
linha se aposenta com `is_active=false`, porque as chaves estrangeiras são `SET NULL` e remover uma
linha desclassificaria toda descrição que aponta para ela, além de apagar o registro de que ela
existiu.

| Tela | Decisão | Reversível? |
| --- | --- | --- |
| Níveis de descrição — `/arranjo/niveis` | a escada contra a qual o arranjo é escrito | sim (aposentar e reativar) |
| Tipologias — `/arranjo/tipologias` | a forma diplomática que o classificador propõe | sim (aposentar e reativar) |
| Vocabulário do acervo — `/vocabulario` | o que os códigos e termos deste acervo significam | sim (aposentar e reativar) |

### Níveis de descrição — `/arranjo/niveis`

O catálogo de níveis. Criar um degrau é `POST /api/v1/hierarchy/levels` e editar é
`PATCH /api/v1/hierarchy/levels/{level_id}` (`CATALOGUE`): nome, descrição, grafias aceitas, se exige
unidade superior e se pode ter filhos. Duas regras que a tela declara em vez de contornar:

- **não há exclusão.** `is_active=false` é o caminho, e o peso de um degrau desativado continua
  visível;
- **o ordinal não é editável.** Mudá-lo renumeraria a árvore contra a qual o passado foi decidido; um
  ordinal errado é um degrau novo, não um renome.

A assimetria é deliberada: um nível desconhecido que chega da origem entra como não classificado e a
descrição segue, enquanto o arquivista não pode gravar um nível que não existe.

### Tipologias — `/arranjo/tipologias`

O catálogo das tipologias documentais — a forma diplomática (ata, ofício, planta), nem arranjo nem
assunto. `POST /api/v1/typologies` e `PATCH /api/v1/typologies/{typology_id}` (`CATALOGUE`) mantêm o
nome e a descrição de contexto. O classificador recebe **só o nome**: acrescentar o contexto faz o
modelo perder o vínculo e colapsar o acervo numa única tipologia (medido), então o contexto é
documentação para quem lê. Desativar uma tipologia é a única alavanca que alcança o modelo — ela
deixa de ser proposta sem desclassificar nenhuma descrição — e é por isso que o peso das desativadas
continua na tela.

### Vocabulário do acervo — `/vocabulario`

O que *este* acervo declara, em oposição ao que a língua ou o software fixam. Duas listas:

- **nomes de arranjo** — `POST`/`PATCH /api/v1/vocabulary/arrangement-terms` (`CATALOGUE`): um token
  (`SMU`) ou o código inteiro (`BR PRADAP`) mapeado para o nome que a proposta de arranjo sugere; o
  código inteiro tem precedência sobre o último token;
- **termos do acervo** — `POST`/`PATCH /api/v1/vocabulary/collection-terms` (`CATALOGUE`): as
  grafias que o acervo carrega e que não são assunto, tipadas para a faceta Lugar reivindicar um
  lugar enquanto o nome de uma pessoa não vai a lugar nenhum.

O que é propriedade da língua portuguesa — *rua*, *não identificado*, *303 anos*, um ano solto — fica
no perfil de idioma e **não** aparece aqui: mudá-lo seria mudar o significado que o software dá à
palavra. Retirar um termo não o apaga, e um termo retirado volta a ser tratado como assunto na
próxima execução do classificador.

## Assuntos

| Tela | Decisão | Reversível? |
| --- | --- | --- |
| Tags — `/assuntos/tags` | o peso, as duplicatas, a fila de merges e os termos banidos | o merge sim (ledger); a purga **não** |
| Categorias — `/assuntos/categorias` | as gavetas de assunto que o classificador lê | sim (aposentar e reativar) |
| Descobrir gavetas — `/assuntos/descobrir` | se um tema proposto merece uma gaveta | sim (a proposta não escreve nada) |
| Não é assunto — `/assuntos/excecoes` | quais termos saem do eixo de assunto | sim (banir não apaga nada) |

### Tags — `/assuntos/tags`

Uma rota, quatro perguntas, uma conversa só: o arquivista vê que `alvenarias` pesa pouco, encontra a
quase-duplicata dela e decide se a absorve. A aba ativa está na URL.

#### Relevância

Só leitura: `GET /api/v1/taxonomy/tags/relevance/{method}`. A contagem mostra o que domina o acervo;
o TF-IDF mostra o que é específico, punindo o que aparece em toda parte. As duas listas respondem
perguntas diferentes de propósito.

#### Similaridade

Pares por similaridade de trigrama, mostrados crus, com a pontuação e os dois identificadores. A
leitura é `GET /api/v1/taxonomy/tags/similar`. A similaridade não diz qual grafia é a boa:
`'alameda cabral'` e `'al. alameda cabral'` têm 1,000.

A decisão é unificar: `POST /api/v1/taxonomy/tags/merge` (`CURATE`), depois de um dry-run
(`POST /api/v1/taxonomy/tags/merge/preview`, uma leitura que calcula o mesmo plano que a escrita
executa). O painel abre sempre com o impacto na frente: documentos atualizados, vínculos reescritos,
tags absorvidas, grafias registradas e reapontadas, e o aviso que precisa ser lido antes do clique —
`category_would_be_lost`, quando a canônica não tem gaveta e uma absorvida tem, o que faria o merge
apagar uma classificação de assunto.

O merge é **reversível**: a escrita é registrada por tag absorvida no ledger de merges antes de
qualquer coisa mudar, e o desfazer (`DELETE /api/v1/taxonomy/tags/merge-log/{merge_id}`, `CURATE`)
restaura a linha, os vínculos, a classificação e o estado das grafias. O desfazer apaga apenas os
vínculos que o merge criou, então não solta um documento que já carregava a canônica. As linhas também
podem ser marcadas entre si e unificadas como um conjunto, que é como um merge atravessa vários pares
(`carlos de carvalho` aparece em mais de uma linha).

#### Propostas de merge

Os conjuntos da máquina, com a decisão separada da escrita:

- **Propor clusters** — `POST /api/v1/taxonomy/tags/merge-proposals/suggest` (`CURATE`) registra a
  pergunta. Um veredito já tomado nunca é sobrescrito.
- **Conferir impacto** — `POST /api/v1/taxonomy/tags/merge/preview` com o id da proposta, o mesmo
  planejador.
- **Aprovar** / **Rejeitar** — `PATCH /api/v1/taxonomy/tags/merge-proposals/{proposal_id}`
  (`CURATE`). Aprovar registra a **intenção**; não absorve nada. O status vai de `SUGGESTED` para
  `APPROVED`/`REJECTED` e depois `APPLIED`.
- **Aplicar em lote** — `POST /api/v1/taxonomy/tags/merge/batch` (`CURATE`) absorve os conjuntos
  selecionados e grava `APPLIED` no mesmo savepoint. A tela recusa um lote acima de 200 clusters (a
  API também recusa). Um conjunto cujos membros já saíram é reportado em `skipped`, nunca como falha.
- **Editar** um conjunto — marca para fora as tags que não pertencem, escolhe a canônica e aplica a
  seleção revisada pelo mesmo planejador; a proposta da máquina é então fechada como rejeitada,
  porque a pergunta foi respondida de outro jeito.

O **ledger** abaixo lista só merges aplicados, cada um com o nome absorvido, a canônica, a contagem de
documentos, a autoria e o horário. O desfazer dele é a restauração exata descrita acima, e o
"desfazer" da tela é a mesma rota. Um merge feito aqui também passa por uma proposta, então o ledger é
a história da escrita e o status é a da decisão.

#### Stopwords

Os termos banidos, e a única escrita destrutiva da taxonomia. A tela separa três coisas:

- **Banir** — `POST /api/v1/taxonomy/tags/stopwords` (`CURATE`) registra que um termo não vale a pena
  num eixo: `TAG` (o eixo de assunto), `ENTITY` (NER) ou `ALL`. Uma palavra tem exatamente um escopo
  — banir de novo **move** — e banir **não apaga nada**.
- **Desbanir** — `DELETE /api/v1/taxonomy/tags/stopwords` (`CURATE`). Reversível.
- **Purgar** — `POST /api/v1/taxonomy/tags/stopwords/purge` (`CURATE`), depois de
  `POST /api/v1/taxonomy/tags/stopwords/purge/preview`. Esta é a escrita que apaga as tags, e ela
  **não tem desfazer**. A prévia lista as tags que morreriam, com a contagem de documentos e a
  gaveta, e o botão de aplicar fica desabilitado até a prévia existir.

!!! warning "O escopo protege o outro eixo"

    A purga lê apenas `TAG`/`ALL`. Um termo banido no eixo `ENTITY` é um veto de NER e nunca pode
    fazer a purga de assunto apagar uma tag que o curador manteve — os dois são guardados em lugares
    diferentes de propósito.

### Categorias — `/assuntos/categorias`

As gavetas que o classificador de assunto lê. `POST /api/v1/taxonomy/macro-categories` e
`PATCH /api/v1/taxonomy/macro-categories/{category_id}` (`CATALOGUE`) as criam, renomeiam, descrevem,
aposentam e reativam; uma gaveta aposentada mantém o peso visível. Duas notas honestas da tela: o
**rótulo do classificador** é um ajuste do curador, não uma melhoria — medido em 44 tags rotuladas à
mão, uma frase em vez do nome nu leva a 0,000 com 65% das tags numa única gaveta — e uma **gaveta nova
só passa a valer quando o classificador rodar de novo**, porque o carimbo do worker é o hash do
conjunto de rótulos, o que devolve as tags à fila sozinho.

### Descobrir gavetas — `/assuntos/descobrir`

Roda o motor de agrupamento de verdade (`POST /api/v1/taxonomy/tags/suggest-macro`, só leitura:
`AUTHENTICATED`) sobre as tags ou os documentos para achar um tema que o vocabulário ainda não cobre.
É um clique deliberado e não um carregamento de página: o motor leva segundos e pode rodar num
subprocesso. Os clusters são **propostas** — nada entra no vocabulário antes de o arquivista
cadastrar, o que é `POST /api/v1/taxonomy/macro-categories` (`CATALOGUE`). Descartar uma proposta é
local à tela. Um corpus pequeno demais responde com uma sugestão vazia e uma mensagem, não com um
erro.

### Não é assunto — `/assuntos/excecoes`

A metade curada do "isto não é assunto de jeito nenhum". O guarda determinístico pega o que tem forma
— uma data, um placeholder, um logradouro, um número solto — e, na medição real, pegou 1 de 4 dos
não-assuntos rotulados à mão; o resto é julgamento semântico que nenhuma regra resolve (`pessoas`,
`vista aérea`, `capanema`). A tela mostra os candidatos do guarda com a evidência deles (peso, se a
faceta Lugar reivindica o termo, se a mesma grafia também é entidade) e oferece registrá-los com
`source=RULE` ou um a um.

A escrita é `POST /api/v1/taxonomy/tags/subject-exclusions` (`CURATE`) e a reversão é `DELETE`
(`CURATE`, o "restaurar" da tela). **Banir aqui não apaga nada**: a tag continua no acervo, continua
vinculada e continua alcançável pela busca — só a classificação de assunto para de adivinhar. A rota
deliberadamente não propõe nada para a metade semântica: os sinais disponíveis mentem, e um modelo que
não sabe se abster responderia com confiança e errado.

## Entidades

| Tela | Decisão | Reversível? |
| --- | --- | --- |
| Entidades — `/entidades/lista` | o tipo de um nome, e se dois nomes são um | o tipo sim; o merge **não** |
| Exclusões de NER — `/entidades/excecoes` | quais grafias são assunto, não nome próprio | a linha do veto sim; as entidades expurgadas **não** |
| Conflitos — `/entidades/conflitos` | se uma colisão pertence ao eixo de assunto ou aos nomes | sim (ledger e desfazer) |

### Entidades — `/entidades/lista`

O vocabulário de nomes próprios, por peso ou por similaridade. Três decisões:

- **Reclassificar o tipo** — `PATCH /api/v1/taxonomy/entities/{entity_id}/reclassify` (`CURATE`), só
  entre `ORG`, `PER` e `LOC`. Isso não é renomear um rótulo: o serviço grava também o sinônimo de
  ancoragem, então o extrator devolve aquela grafia com o tipo novo em toda execução futura.
- **Excluir** uma entidade — `DELETE /api/v1/taxonomy/entities/{entity_id}` (`CURATE`), oferecido só
  numa linha que nenhuma descrição carrega, onde apagar não perde vínculo. Sem desfazer.
- **Purgar órfãs** — `POST /api/v1/taxonomy/entities/orphans/purge` (`CURATE`): a mesma decisão em
  lote. Sem desfazer.
- **Unificar** — `POST /api/v1/taxonomy/entities/merge` (`CURATE`): as entidades absorvidas deixam de
  existir, seus vínculos passam para a canônica, suas grafias viram sinônimos, e um nome novo opcional
  para a canônica faz o antigo virar sinônimo também. Entidades não têm catálogo de propostas nem
  **ledger**: não há desfazer, e o painel avisa em vez de oferecer um botão de volta. Também não há
  rota de prévia — a tela declara o efeito documentado em vez de inventar números. A lista de pares é
  evidência crua, com os dois identificadores, porque duas linhas podem ler o mesmo nome e a canônica
  é uma escolha que o arquivista precisa conseguir distinguir.

### Exclusões de NER — `/entidades/excecoes`

O veto "esta grafia é assunto, não nome próprio". A escrita é `POST
/api/v1/taxonomy/entities/ner-exclusions` (`CURATE`), com um motivo guardado para auditoria; a
reversão é `DELETE` (o "remover veto" da tela). Dois comportamentos que a tela declara porque nenhum
deles é visível na lista: o bloqueio é **por limite de token**, não por nome exato (o spaCy funde
tokens vizinhos, então um `iptu` vetado não barraria `"IPTU do Batel"` numa comparação exata), e ele
**vale para trás** — as entidades já extraídas daquela grafia são apagadas, com os vínculos, e
remover o veto não as traz de volta.

Esta é a outra metade da governança bidirecional: ela registra o curador ou o juiz dizendo "isto
pertence ao eixo de assunto", e é guardada separada das stopwords do eixo de assunto de propósito,
para um veto aqui nunca fazer a purga de assunto apagar uma tag que o curador manteve.

### Conflitos — `/entidades/conflitos`

A mesma grafia nos dois eixos: "isto é assunto ou nome próprio?". Três leituras respondem a três
perguntas, e ler só a primeira era o que escondia o trabalho do juiz:

- **Pendentes** — a varredura ao vivo de trigrama (`GET /api/v1/taxonomy/conflicts/cross-domain`),
  anotada com o veredito do juiz onde existe e separada por `pair_kind`: "grafias diferentes" (uma
  pergunta de grafia) e "nomes idênticos" (uma pergunta estrutural) não são a mesma lista, e juntas
  nenhuma das duas fica visível.
- **Decididos pelo juiz** — a fila de revisão (`GET /api/v1/taxonomy/conflicts/judged`). Uma
  auto-resolução apaga a linha perdedora, então a maior parte das decisões do juiz não pode aparecer
  na varredura ao vivo.
- **Resoluções** — o ledger (`GET /api/v1/taxonomy/conflicts/resolutions`), com o desfazer.

A decisão é precedida pela prévia (`POST /api/v1/taxonomy/conflicts/resolve/preview`, uma leitura):
ela devolve **os dois vereditos** com o que cada um transfere, apaga e bloqueia, calculados pelo mesmo
planejador que a escrita executa. Os dois vereditos são guardados em **lugares diferentes de
propósito**:

- **a tag vence** — os vínculos da entidade passam para a tag, a linha da entidade é apagada e o
  termo é registrado em `domain_ner_exclusions`, carregando o motivo, a origem e a tag que o
  justifica;
- **a entidade vence** — os vínculos da tag passam para a entidade, a linha da tag é apagada e o nome
  da tag entra nas stopwords de escopo `TAG`.

Colapsar os dois deixaria um veto de NER fazer a purga de assunto apagar a tag vencedora.

Resolver é `POST /api/v1/taxonomy/conflicts/resolve` (`CURATE`) e o desfazer é
`DELETE /api/v1/taxonomy/conflicts/resolutions/{resolution_id}` (`CURATE`). O desfazer é exato porque
o ledger grava `created_link_ids` e `ban_created`: as duas escritas usam `ON CONFLICT DO NOTHING`,
então reverter uma resolução posterior não pode levantar um bloqueio que uma anterior plantou, nem
apagar um vínculo que já existia antes. O ledger restaura a linha perdedora a partir do retrato dela.
Um par já resolvido pode ser decidido de novo — a segunda resolução é independente, e cada uma tem o
próprio desfazer.

!!! note "Um par resolvido sai da varredura ao vivo"

    A resolução apaga a linha perdedora, então o join de trigrama não pode devolvê-la e a lista ao
    vivo não tem o que anotar. É por isso que o trabalho sobrevive na fila do juiz e no ledger, e é
    por isso que as abas `Decididos` e `Resoluções` existem.

## Qualidade

| Tela | Decisão | Reversível? |
| --- | --- | --- |
| Trechos — `/qualidade/trechos` | de qual consumidor um trecho repetido sai | sim (desativar ou remover do catálogo) |
| Regras — `/qualidade/regras` | se uma regra reescreve o texto ou só sinaliza | sim: a desativação tem caminho de volta, e a regra desativada continua na tela |
| Anomalias — `/qualidade/anomalias` | nenhuma (a correção é a revisão da ficha) | sim (só leitura) |

### Trechos — `/qualidade/trechos`

O catálogo de trechos repetidos. É o maior ganho medido do projeto: 53% do acervo compartilhava o
mesmo bloco de `scope_content`, e um prefixo de título repetido dominava os embeddings e degradava a
busca. A decisão que importa é o **escopo**: de qual consumidor o trecho sai — `EMBEDDING` (o vetor),
`NER` (os nomes) ou `TITLE` (o título sugerido). O mesmo bloco é retirado dos consumidores que ele
prejudica e mantido onde ajuda: aprovar tudo o que a máquina sugeriu piorou o ranking (Hit@10 0,562 →
0,500), e é por isso que não existe botão de "aprovar todos" nesta tela.

- **Procurar** — `POST /api/v1/quality/text-templates/suggest` (`CATALOGUE`) registra os candidatos
  como **sugestões inativas**: nada entra no texto da IA antes de o arquivista aprovar um escopo.
- **Escrever um trecho** — `POST /api/v1/quality/text-templates` (`CATALOGUE`). Ele nasce aprovado e
  aplicado e devolve as descrições afetadas à fila da IA; o botão de cadastrar só libera depois de o
  impacto ser visto.
- **Aprovar / rejeitar / desativar / salvar escopo / remover** —
  `PATCH`/`DELETE /api/v1/quality/text-templates/{template_id}` (`CATALOGUE`). Remover tira o trecho
  do catálogo e devolve as descrições afetadas à fila da IA.

### Regras — `/qualidade/regras`

O único lugar onde uma expressão regular pode reescrever o acervo. `rule_kind` é a diferença entre
limpar e destruir, e a tela torna a escolha explícita:

- `REWRITE` substitui cada ocorrência na coluna alvo na próxima execução — o worker de limpeza a
  filtra explicitamente, então uma regra de validação nunca reescreve;
- `VALIDATE` e `LLM_CHECK` só sinalizam; o sinal vira um motivo de anomalia na descrição.

As escritas são `POST /api/v1/quality/cleaning-rules` (`CATALOGUE`) — salva só depois da prévia,
quando a regra reescreve — `PATCH /api/v1/quality/cleaning-rules/{rule_id}/deactivate` e
`PATCH /api/v1/quality/cleaning-rules/{rule_id}/activate`, as duas `CATALOGUE`. Uma regra nunca é
apagada, e o caminho de volta é uma rota, não uma regra nova: a listagem aceita
`include_inactive=true`, que é o que coloca as regras aposentadas no fim da tela com o botão que as
devolve à fila. Reativar preserva o id e o histórico que recadastrar a regra teria perdido.
Desativar é a metade segura do par — é o que se procura quando uma regra está errada, então a saída
dela precisa existir.

Uma regra `REWRITE` ativa é a coisa mais barulhenta da tela, e a prévia é o que a torna visível: uma
regra de teste já ficou ativa e carimbou o acervo inteiro sem casar com nada.

### Anomalias — `/qualidade/anomalias`

O que o validador de qualidade marcou, em leitura (`GET /api/v1/documents` filtrado por
`NEEDS_REVIEW`, opcionalmente por motivo de anomalia). As contagens por motivo são a faceta da própria
busca sobre o conjunto filtrado inteiro, e clicar numa delas estreita a lista. Uma fila vazia tem duas
causas muito diferentes e a tela as distingue: o acervo está limpo, ou nenhuma regra que sinaliza
(uma `VALIDATE` ou `LLM_CHECK`) está ativa — uma regra `REWRITE` muda o texto e nunca sinaliza. A
correção é a revisão humana da ficha, na descrição.

## Sistema

A máquina, não o acervo. Tudo aqui pertence a quem opera a instalação, e as três telas são alcançadas
por `/configuracoes`, sob *Operação*: o menu ficou com o que o arquivista consulta catalogando, e não
é isto.

| Tela | Decisão | Reversível? |
| --- | --- | --- |
| Workers de IA — `/sistema/workers` | com qual modelo um worker roda, e se rodá-lo agora | o padrão configurado sim; os efeitos de uma execução seguem o que ela escreveu |
| Execuções — `/sistema/execucoes` | nenhuma (o ledger e as falhas agrupadas) | sim (só leitura) |
| Diagnóstico — `/sistema/diagnostico` | nenhuma (banco, modelos, storage, processo) | sim (só leitura) |

### Workers de IA — `/sistema/workers`

O catálogo dos nove workers, na ordem do pipeline, com a engine, o preset e a configuração efetiva na
linha recolhida — "com qual modelo isto está rodando?" é a pergunta que a tela existe para responder.
Duas escritas por worker, ambas `OPERATE`:

- **Rodar agora** — `POST /api/v1/system/workers/{worker_name}/runs`. A execução usa a configuração
  efetiva, ajustada só para esta vez; nada no painel vira padrão. Toda execução deixa uma linha no
  ledger de execuções, e um worker com execução em andamento desabilita os dois botões — a garantia é
  o índice único parcial no banco, e a tela só evita oferecer o que o banco recusaria.
- **Configurar** — `PUT /api/v1/system/workers/{worker_name}/settings` define o padrão persistido
  (parcial de propósito: um campo vazio continua seguindo o código), e
  `DELETE /api/v1/system/workers/{worker_name}/settings` o remove. Toda escrita deixa uma revisão
  (`GET /api/v1/system/workers/{worker_name}/settings/revisions`), então o padrão é reversível: a
  lista de revisões está ali, e "Voltar ao padrão do código" remove a linha.

O painel em si não oferece desfazer para uma execução. A reversibilidade de uma execução é a
reversibilidade do que ela escreveu — um desfazer de merge, de materialização, de conflito — e um
worker que carimba a própria fila não refaz o trabalho só porque foi rodado de novo. Um worker
marcado como não respeitando o bloqueio de revisão humana é o `worker_embedding`, a exceção
documentada.

### Execuções — `/sistema/execucoes`

O ledger de execuções, em leitura: uma linha por execução, da linha de comando e do painel, com a
configuração **já resolvida** que a execução usou (então ele continua legível depois que um preset
muda no código), a duração, o desfecho e quem pediu. Acima dele, as falhas dos últimos 30 dias
agrupadas por causa (`GET /api/v1/system/failures`), que respondem à pergunta que o ledger não
responde: quarenta linhas dizendo a mesma frase são uma causa. Clicar num grupo filtra o ledger
abaixo em vez de abrir uma segunda lista, e a referência de uma falha é o que se procura no log.

### Diagnóstico — `/sistema/diagnostico`

Quatro verificações independentes (`GET /api/v1/system/health`, `OPERATE`): o banco com suas
contagens, o servidor Ollama com os modelos que os presets exigem e quais deles faltam, o storage das
miniaturas e a configuração efetiva do processo. Cada verificação responde por si — um banco fora do
ar não pode esconder que o Ollama está bem — e nenhum valor de segredo é mostrado: o cartão do
processo informa que um segredo existe, nunca qual é. Nada aqui escreve.

## Configurações

A landing que reúne o que a instalação *é*, fora do caminho do que o arquivista faz todo dia. Ela
mesma não escreve nada.

| Tela | Decisão | Reversível? |
| --- | --- | --- |
| Configurações — `/configuracoes` | qual tela de montagem abrir | sim (só leitura) |
| Usuários — `/configuracoes/usuarios` | quem existe, o que pode fazer e onde está conectado | sim (desativar e reativar) |

### Configurações — `/configuracoes`

Uma página de cartões, e cada cartão abre uma tela que já existia com a rota que sempre teve: o que
mudou foi como se chega até ela. Três abas, na ordem da escada de permissões que elas percorrem:

| Aba | Cartões |
| --- | --- |
| Arranjo e catálogos | Plano de arranjo (`CURATE`), Níveis de descrição, Tipologias e Vocabulário do acervo (`CATALOGUE`) |
| Operação | Workers de IA, Execuções e Diagnóstico (`OPERATE`) |
| Acesso | Usuários (`ADMIN`) |

A aba fica na URL (`?aba=`), então dá para mandar alguém direto aos "cartões dos workers". Uma aba que
a conta não pode preencher não é renderizada, e um `?aba=` que a nomeie cai na primeira aba que a
conta *pode* preencher: um link válido para quem mandou ainda aterrissa em algo honesto para quem lê.
Cada cartão carrega a área em que a sua tela escreve, e a entrada que abre esta página segue as mesmas
áreas — a regra está em *O menu esconde; nunca concede*, acima.

### Usuários — `/configuracoes/usuarios`

As contas da instalação, a superfície `ADMIN`. As escritas são `POST /api/v1/users` (criar),
`PATCH /api/v1/users/{user_id}` (nome, papel, ativa), `POST /api/v1/users/{user_id}/password`
(redefinir) e as rotas de sessão `GET`/`DELETE /api/v1/users/{user_id}/sessions[/{session_id}]` —
todas `ADMIN`. Quatro fatos que a API impõe e a tela declara:

- **a senha criada aqui é temporária.** O administrador a digitou, então a conta a troca no primeiro
  acesso, exatamente como no bootstrap do CLI;
- **desativar encerra todas as sessões da conta na hora**, que é o que torna o sinalizador real;
- **redefinir a senha encerra todas as sessões** e destrava um bloqueio por tentativas falhas;
- **a última conta de administrador ativa não pode ser desativada nem rebaixada** (`LastAdminError`,
  409). É o único beco sem saída que não tem volta pela tela; a entrada é o CLI no host.

Não há exclusão. Uma conta é desativada, porque os ledgers carregam o nome e o id dela, e uma decisão
cujo autor não existe mais é um registro pior do que uma conta fechada. Revogar uma sessão que
pertence a outra conta responde 404 e não 200, porque só o id não pode enumerar os acessos de outras
pessoas; a linha que é a própria sessão do arquivista fica marcada como "esta sessão".

A conta desta tela **nunca é a primeira**. Uma instalação sem conta nenhuma é criada pela tela de
primeiro acesso, que ela responde à primeira visita, ou pela CLI na máquina, e as duas se fecham para
sempre quando uma conta existe — inclusive uma desativada (ADR 0011). Depois disso, esta é a única
superfície que cria contas.
