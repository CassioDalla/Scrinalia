---
translation_of: guides/curate.md
---

# Curadoria do acervo

Esta página é para o arquivista que trabalha na SPA de curadoria. Ela diz, tela por tela, **que
decisão se toma ali, o que o clique escreve e se dá para desfazer** — e nomeia o que não tem volta
nenhuma.

A SPA é servida pela própria API (uma origem, sem CORS), e toda tela lê e escreve pelo cliente gerado
a partir do contrato OpenAPI. As telas são declaradas em `apps/curator/src/router.tsx`, e **como cada
uma se chama** em `apps/curator/src/lib/screens.ts`: um registro por tela guarda o rótulo que o menu,
o cartão de configurações e o título da própria página leem, então os três não podem discordar
(*Um nome por tela, um verbo por ação*, abaixo). O menu tem **17 entradas**: as telas que ninguém
abre no meio da catalogação — o plano de arranjo, os catálogos, o painel de workers, o ledger de
execuções, os diagnósticos e as contas — são cartões de `/configuracoes`, não itens de menu
(*Configurações*, abaixo). Uma rota também não vem do menu: a ficha da descrição,
`/acervo/$descriptionId`, é alcançada pela lista e pela árvore. O roteador, por isso, declara **26
telas**. O próprio menu pode ser recolhido a ícones, o que é uma escolha de apresentação e não de
permissão — *O menu se recolhe a ícones*, abaixo.

Vale ler duas páginas junto com esta: [Modelo de dados](data-model.md) para o que os ledgers e as
tabelas significam, e [Instalação e implantação](install.md) para o esquema, as contas e a
implantação em volta das telas.

## A única regra

Toda escrita ou tem desfazer, ou avisa que não tem. O merge, a purga de stopwords e o expurgo de NER
guardam um ledger;
a edição da descrição guarda o antes e o depois. Quando uma tela não tem nem uma
coisa nem outra, esta página diz em negrito.

O trabalho de leitura não declara permissão: ler é o que uma sessão autenticada é. As telas que
decidem carregam a área em que escrevem, e a API recusa com 403 e uma frase quando a conta não a
carrega.

## O que não tem volta

!!! warning "Estas escritas não têm desfazer"

    As operações abaixo apagam ou dissolvem uma linha que nada mais reconstrói. A exclusão pede que
    você digite o código de referência. Leia a confirmação.

- **Excluir uma descrição** — `DELETE /api/v1/documents/{description_id}`. Definitivo. A API grava
  antes um retrato ISAD(G) da linha inteira no ledger de exclusões, e esse retrato é uma **trilha,
  não uma lixeira**: `/acervo/excluidas` o mostra e nada o restaura. O ledger de revisões não
  sobrevive (ele cai junto com a descrição), e é por isso que o retrato existe. Uma descrição com
  filhos não pode ser excluída — o serviço recusa e diz quantos estão abaixo; exclua ou mova os
  filhos primeiro. A tela pede que o arquivista digite o código de referência (ou o identificador,
  quando não há código) antes de o botão liberar.

- **Excluir ou purgar entidades sem vínculo** — `DELETE /api/v1/taxonomy/entities/{entity_id}` e
  `POST /api/v1/taxonomy/entities/orphans/purge`. A tela só oferece a exclusão numa linha cuja
  contagem de uso é zero, e a purga remove toda entidade que nenhuma descrição carrega, então nenhum
  vínculo se perde — mas a linha vai embora e não há ledger que a restaure.

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
- os planos que apontavam para um nó apagado voltam a "não materializado", para a próxima aplicação não
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
- **Publicar não é travar.** Publicar não altera `review_status`: é um escopo de canal mais a
  aprovação que a cobertura exige (ADR 0023). Um registro coberto é `HUMAN_APPROVED` porque a
  cobertura exige, e é essa aprovação — não a publicação — que bloqueia a IA. O publicador nunca
  aprova no lugar do curador: publicar um ramo cujo filho ainda está `PENDING_AI` não cobre nada até
  que uma pessoa o aprove.

Os outros workers de IA ficam de fora de uma descrição `HUMAN_APPROVED`; o que uma pessoa decidiu não
é reescrito pelo pipeline.

### Difusão não é revisão

Revisão é uma afirmação sobre o registro; publicação é uma decisão sobre onde ele aparece. Uma
descrição é exposta num canal quando é `HUMAN_APPROVED`, um **escopo positivo** daquele canal a cobre
— o próprio nó ou um ancestral com `include_descendants` — e nenhum **escopo negativo** a cobre. A
cobertura é uma leitura, não um booleano guardado: um filho aprovado depois entra no canal do seu ramo
sem um segundo ato, e a exclusão é o override deliberado. Nada é publicado por padrão, então a
superfície de difusão nasce vazia.

O separador é a página **Difusão**, `/difusao`, em `CURATE`. Ela tem quatro visões: *A publicar* (as
aprovadas que nenhum canal carrega, com filtro de ramo e seleção), *Publicadas* (o que cada canal
carrega, com os selos), *Publicações por ramo* (os escopos positivos e negativos, com nó, contagens e
autor) e *Histórico* (os lotes, com o desfazer). Uma escrita são dois passos: a pré-visualização
resolve o ramo ou a seleção por canal e devolve os elegíveis, uma amostra e o que fica de fora — não
aprovados, já cobertos, excluídos — com um token; a confirmação ecoa o token e aplica. O token é uma
checagem de consistência, não uma permissão: um conjunto que mudou entre as duas chamadas é recusado
com "pré-visualize de novo", e a escrita é autorizada pela sessão. Todo lote é uma linha de ledger e
pode ser desfeito; o desfazer restaura o que está inalterado e reporta o que deixou.

As três remoções são distintas. **Manter privado** grava o escopo negativo no nó, que vence qualquer
escopo positivo do ramo — e revoga um escopo positivo direto no mesmo nó no mesmo lote. **Retirar o
ramo** revoga o escopo positivo do ramo, e o que um ancestral cobre continua coberto. As exclusões são
listadas e desfeitas em *Publicações por ramo*. A ficha não publica mais: o cartão de publicação é um
status somente leitura com os selos dos canais e um link para cá, e o formulário de revisão é só sobre
o registro.

A superfície pública lê o canal `public_site`, não uma união:

- `GET /api/v1/public/site` — a identidade do site; 404 enquanto o canal não está configurado ou está
  pausado.
- `GET /api/v1/public/documents` e `GET /api/v1/public/documents/{description_id}` — a cobertura de
  `public_site`.

O canal é definido **no servidor** e não é parâmetro do cliente, então nenhuma query string pode pedir
um registro que o canal não carrega; e um identificador fora dele responde 404, nunca 403, porque um
status distinto confirmaria que a descrição existe. As duas rotas de documentos respondem 404 enquanto
o canal está pausado: para um visitante, o site não está lá.

A página do operador, **Canais de difusão**, `/configuracoes/difusao`, adiciona uma definição,
configura, pausa e — num canal de exportação — salva a agenda. Ela nunca publica. As duas permissões
são diferentes de propósito: configurar um destino é `OPERATE`, decidir o que vai para ele é `CURATE`.
O registry traz o site público embutido (`public_site`), cuja configuração é a identidade de
apresentação que o aplicativo lê (título, descrição, instituição, contato, logotipo, idioma, endereço
público e indexação); habilitá-lo não instala o aplicativo público (#46).

A projeção pública é mais estreita que a do curador, campo a campo. Ela carrega os campos ISAD(G)
`original_title`, `final_title`, `document_date`, `reference_code`, `level`, `scope_content`,
`language_name` e `producers`; o enriquecimento `typology`, as tags (nome), as entidades (nome e
tipo) e as categorias de assunto (nome e contagem); a miniatura — ainda a referência `s3://`
guardada, porque a rota pública que serve os bytes é a #46 (ADR 0017); o ramo (`ancestors`) e o
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
| `CATALOGUE` | os catálogos fechados: níveis, tipologias, vocabulário do acervo, categorias de assunto, regras de limpeza e trechos |
| `OPERATE` | os workers de IA: rodar um, mudar o padrão persistido dele e o painel de saúde |
| `ADMIN` | contas e sessões |

| Papel | Carrega | Lê |
| --- | --- | --- |
| `VIEWER` | nada | tudo o que uma sessão autenticada alcança |
| `CURATOR` | `CURATE`, `CATALOGUE` | o mesmo, mais as telas que decidem o registro e os catálogos |
| `ADMIN` | `CURATE`, `CATALOGUE`, `OPERATE`, `ADMIN` | tudo, incluindo os workers e as contas |

Ler não é permissão: é o que uma sessão autenticada é, e uma leitura pura não declara nada.

### Entrar, e esquecer a senha

O formulário de entrada não é uma rota: ele é desenhado no lugar da casca, então um link direto
sobrevive a ele — quem abre `/acervo/lista` sem sessão entra e cai em `/acervo/lista`. Uma senha
errada e um endereço que não existe respondem a mesma frase, de propósito: o formulário não é uma
enumeração de quem tem conta.

Não há **recuperação por e-mail** nesta instalação, e a tela não finge o contrário. Abaixo do botão,
*Esqueci minha senha* abre uma explicação curta do caminho que existe: um administrador redefine a
senha na tela de contas (*Usuários*, abaixo), a senha é temporária e a conta a troca no primeiro
acesso, a redefinição encerra todas as sessões dessa conta e destrava um bloqueio — e, se o último
administrador ativo for justamente quem não consegue entrar, o terminal do servidor é a volta
([Operação](operate.md) é dona desse procedimento). Nada na tela promete uma mensagem, porque
nenhuma mensagem é enviada.

**A senha temporária é credencial para a troca e para nada mais.** Enquanto a conta ainda a carrega,
a API recusa toda operação de `/api/v1` — leituras inclusive — com `PASSWORD_CHANGE_REQUIRED`, e a
casca desenha a troca de senha forçada no lugar de toda tela. As três operações em que esse
formulário se apoia continuam alcançáveis: ler a sessão (`GET /auth/me`), encerrá-la
(`POST /auth/logout`) e trocar a senha (`POST /auth/password`, que limpa a marca). A recusa não
depende da tela: um script com a senha que foi impressa num terminal, ou digitada por um
administrador, recebe a mesma frase e nenhum acesso ao acervo. A troca abre o resto da API na mesma
sessão.

### A interface fala duas línguas

A interface de curadoria é escrita em português e inglês, e a escolha é da **conta**, não da
instalação: *Automático*, *Português* e *English* ficam no rodapé da conta, no menu. Uma conta nova
começa em *Automático*, que é guardado como "nenhuma escolha" e segue o navegador — `pt*` abre em
português, `en*` em inglês e todo o resto em português, a língua da instalação. Depois de entrar, a
escolha da conta vence: uma estação compartilhada não pode entregar a um arquivista a língua do
anterior.

A língua não é uma preferência de cliente pintada sobre um servidor em português: toda requisição
leva `Accept-Language`, e a API compõe a sua `message` — a confirmação de uma escrita e a recusa de
outra — na língua pedida (ADR 0020 §4). A troca não recarrega a página; o shell re-renderiza com o
catálogo novo, e datas, números e plurais a acompanham via `Intl`.

O que não muda entre as duas línguas: os caminhos continuam em português (`/acervo/lista`), o que a
#239 acompanha, e o conteúdo do registro nunca é traduzido.

### O menu esconde; nunca concede

A casca filtra as entradas pela área em que a tela **escreve**
(`apps/curator/src/lib/permissions.ts`, um espelho do mapa de papéis do servidor), e um grupo vazio
não é renderizado. As telas que só leem não carregam permissão e ficam visíveis para todo papel:
Início, a lista do acervo, a árvore, o histórico de exclusões e o diagnóstico do arranjo. Um `VIEWER`
vê, portanto, o grupo "Acervo" e a entrada "Início", que fica sem cabeçalho — todos os outros grupos
existem para decidir, e ficam escondidos.

A mesma regra governa os cartões de `/configuracoes`, e é o catálogo de cartões
(`apps/curator/src/lib/settings.ts`) que a página e a entrada de menu leem: um cartão fica escondido
quando a conta não carrega a área em que a tela escreve, uma aba com todos os cartões escondidos não é
renderizada, e a entrada fica no menu enquanto **ao menos um** cartão for alcançável. Um `VIEWER` não
tem Configurações nenhuma, e uma URL direta até ela chega a uma página que diz por que está vazia em
vez de fingir que quebrou.

O espelho é de mão única de propósito. Ele encurta o menu; nunca faz a API aceitar uma requisição. Uma
URL direta para uma tela em que a conta não pode trabalhar ainda chega à API, e a API responde 403
com uma frase — essa é a verdade, e a entrada escondida é uma cortesia.

### Um nome por tela, um verbo por ação

A interface cresceu tela por tela, e o vocabulário cresceu com ela: o menu dizia *Tags* enquanto a
página que ele abria dizia "Vocabulário de tags", o cartão de configurações dizia *Usuários* enquanto
a página dizia "Contas", e duas telas diferentes se chamavam *Diagnóstico*. Dois arquivos agora são
donos dessas palavras.

`apps/curator/src/lib/screens.ts` guarda **um registro por tela** — a rota, o rótulo e a dica que diz
o que ela decide. O rótulo é a mesma string nos três lugares que discordavam: a entrada de menu, o
cartão de configurações e o `<h1>` da própria página, que o `PageHeader` resolve a partir do id de
tela que a rota declara. Uma rota, por isso, não consegue passar um título próprio; a ficha da
descrição é a única exceção, e é o catálogo que a marca como a tela cujo título é o do próprio
registro.

Abaixo do título, o cabeçalho tem os mesmos quatro espaços em toda tela: o rótulo, uma linha dizendo o
que a tela decide, o **estado** do que foi lido — uma contagem, um filtro, um total — e as ações. A
contagem disputava o mesmo espaço com a linha explicativa, e é por isso que umas telas se explicavam e
outras só relatavam totais; enquanto a leitura está em curso, o espaço do estado mostra um esqueleto
da própria altura, para o cabeçalho não pular quando os números chegam.

`apps/curator/src/lib/copy.ts` guarda o nome do produto — reexportado de `lib/attribution.ts`, que é
dono dele para o aviso de licença — e **um verbo por ação**, com a palavra do meio da execução. Os
verbos que esta página usa são os desse arquivo:

| Ação | A palavra na tela |
| --- | --- |
| escrever uma linha editada | **Salvar** |
| trazer uma linha à existência | **Criar** (o gatilho ao lado diz *+ Nova…*) |
| tirar um termo de uma lista — um veto, uma exclusão | **Remover** |
| destruir um registro, sempre atrás de uma prévia ou de uma confirmação digitada | **Excluir** |
| a chave `is_active` de uma **linha de catálogo** — um nível, uma tipologia, uma categoria, uma regra de limpeza, um termo do acervo | **Aposentar** / **Reativar** |
| desativar uma **conta** | **Desativar** / **Reativar** |
| disparar uma execução de worker | **Rodar agora** |
| unificar duas entradas de vocabulário | **Mesclar** |
| confirmar um plano calculado | **Aplicar** |
| calcular o que uma escrita destrutiva faria, sem escrever | **Conferir impacto** |

`Aposentar` e `Desativar` são duas palavras de propósito: uma linha de catálogo e uma conta saem do
sistema de maneiras diferentes, e uma palavra só para as duas diria que não. Banir um termo mantém o
verbo próprio (`Banir` / `Desbanir`), porque é outra marca e não exclui nada.

### A tela tem a altura de uma janela

A casca tem exatamente uma viewport e a **página nunca rola**: o que rola é a coluna de conteúdo, então
a rail — e a entrada de `Configurações` no pé dela — fica onde está numa tela longa. O cabeçalho da
própria tela é fixo dentro dessa coluna, e é isso que mantém o título, o estado e **as ações** ao
alcance: "Propor níveis", "Rodar agora" e "Excluir órfãs" saíam da janela junto com o conteúdo. Medido
a 1440x900 na lista de entidades: o documento tem 900px numa janela de 900px, o conteúdo tem 3299px
numa coluna de 867px e o menu tem 734px numa caixa de 734px.

A coluna **não tem largura máxima**: ela preenche o que a janela der, então a mesma tela tem a mesma
largura em qualquer monitor. Antes disso cada tela carregava o próprio teto e eles tinham divergido —
`max-w-5xl` na maioria, `max-w-4xl` em cinco, `max-w-6xl` em uma — então duas telas lado a lado num
monitor largo paravam de crescer em pontos diferentes. Quem mantém o próprio teto é o **conteúdo**: um
parágrafo mantém a medida legível, um campo de texto mantém a largura de campo.

O menu **se dobra numa seção aberta**, mais a seção em que o arquivista está — essa fica aberta por
construção, porque uma entrada ativa escondida dentro de um grupo recolhido é um menu que esconde onde
você está. Clicar num título abre o grupo e fecha o que foi aberto à mão; navegar fecha esse, então o
menu nunca escorrega para três. O título não carrega ícone: o glifo é da entrada. `Início` fica no topo
sem título, como a entrada do pé, porque uma seção que junta uma linha é uma linha de cromo.

### A identidade está na tela

A rail é o navy da identidade (`#14202B`), e a logomarca está nela nos dois estados: expandida é o
lockup completo — a ficha com a aba terracota e **Scrinalia** em PT Serif — e recolhida é só a marca
recortada. Recolhida, essa marca é **também o controle que expande a rail**: a marca é o que se clica
para trazer as palavras de volta, e é isso que faz valer a pena mantê-la em 64px.

Um filete de 2px de terracota fecha o cabeçalho da tela, e os dois cartões que vêm antes de uma sessão
— o formulário de entrada e a configuração inicial — carregam o mesmo motivo no topo, onde antes
estava o nome em texto simples. As duas fichas não são iguais: a configuração inicial centraliza o
lockup sob a tagline, e o formulário de entrada põe um lockup maior à direita e não carrega tagline
nenhuma — ali a ficha é só a marca.

O accent continua o azul que era, e a terracota é cor de **marca** e não de interação: a terracota é
`oklch(… 31)` e a cor de perigo é `oklch(… 25)`, seis graus de distância, então um botão terracota e
"Excluir" seriam da mesma cor. O navy, por outro lado, compartilha a matiz do accent de propósito — e
é por isso que a rail e os botões parecem uma coisa só.

### O menu se recolhe a ícones

Um controle no cabeçalho do próprio menu o dobra numa coluna de ícones de 64px e o devolve, e o
navegador lembra a escolha: a largura de uma coluna da tela é estado de apresentação, então mora no
`localStorage` e não na conta — a API não tem coluna para isso.

Recolhido, cada entrada mantém o ícone; o rótulo continua sendo o nome acessível do link e o `title`
carrega rótulo e dica, de modo que a dica fica escondida e nunca cortada. A entrada ativa mantém a cor
de destaque, os títulos de grupo viram filetes e o acordeão fica desligado — um título sem rótulo numa
coluna de 64px é um clique que não diz nada —, então as dezesseis entradas aparecem de uma vez. O
rodapé de sessão vira a inicial da conta mais dois botões de ícone.

O nome da atribuição sai do menu, mas não da página: a atribuição é renderizada no pé de **toda** tela
(`AttributionFooter`, ADR 0006), incluindo as três que vêm antes de uma sessão — a configuração inicial,
o formulário de entrada e a troca de senha forçada — e ela termina com a versão da instalação, sozinha à
direita. Os ícones vêm do `lucide-react`, um glifo por entrada.

## Curadoria

| Tela | Decisão | Reversível? |
| --- | --- | --- |
| Início — `/` | qual fila pendente abrir | sim (só leitura) |

### Início — `/`

A lista de trabalho. Ela responde "o que precisa de mim hoje?" com um cartão por fila. Cada cartão
abre a tela que resolve a pendência, já filtrada: a aba e o estado da fila viajam como busca tipada
da própria tela. É uma **leitura de predicados existentes**
(`GET /api/v1/curation/inbox`): nada é escrito.

## Acervo

| Tela | Decisão | Reversível? |
| --- | --- | --- |
| Nova Descrição — `/acervo/nova` | digitar uma descrição ou importar um CSV (curador) | o registro entra no pipeline como `PENDING_AI`; a aprovação (ou rejeição) acontece no dossiê, e só ali |
| Lista e busca — `/acervo/lista` | como recortar o acervo | sim (só leitura) |
| Árvore — `/acervo/arvore` | onde a descrição fica no arranjo | sim, movendo; remover o nó significa excluir a descrição |
| Histórico de exclusões — `/acervo/excluidas` | nenhuma (o registro do que saiu) | sim (só leitura) |
| Descrição — `/acervo/$descriptionId` | o registro, seus assuntos e seu lugar | em geral sim; a exclusão não |

### Nova Descrição — `/acervo/nova`

A porta de entrada do acervo: uma descrição digitada inteira, ou um CSV importado. As duas são abas
na URL — **Digitar** (o padrão) e **Importar CSV** (`?modo=csv`) — porque são duas formas de entrada
do mesmo trabalho, não dois trabalhos: as duas põem o registro no staging e enfileiram a mesma
`transfer` que a coleta usa, e a descrição do Acervo nasce `PENDING_AI`. A tela **não é uma
aprovação**: o dossiê é onde o registro é revisto e aprovado depois que a IA rodar. É uma escrita
`CURATE`, e é a primeira entrada do menu *Acervo*.

**Digitar** é o registro ISAD(G) inteiro: trinta controles nas sete áreas da norma, o nível e o idioma
como seletores, a data como texto com a gramática do idioma, o controle do objeto digital desabilitado
até a #198. O formulário gera um id `manual-<uuid>`, então um reenvio é o mesmo registro; um
`description_id` duplicado é recusado antes da gravação. Só o título é obrigatório — uma descrição pode
nascer incompleta e ser completada no dossiê.

**Pontos de acesso** são chips sobre o catálogo de tags, não uma string separada por vírgulas. A busca
enquanto digita escolhe uma grafia existente; digitar um termo e escolher *Adicionar* mantém a grafia
do arquivista. Um resumo abaixo do campo diz o que a `transfer` vai fazer com a string — criar uma
grafia nova, ligá-la a um sinônimo ou descartá-la por ser um termo bloqueado, ter menos de três ou mais
de cem caracteres — e aponta as entradas cuja grafia guardada difere da digitada. O resumo é `POST
/api/v1/taxonomy/tags/preview`, uma leitura: uma grafia desconhecida é `NEW` e só é criada pela
`transfer` no arquivamento. Nada é removido nem reescrito pela prévia: remover um termo é decisão do
arquivista. O campo continua opcional, e a string que ele envia é a mesma da coluna do CSV e da chave
mapeada do scraper.

**Produtor(es)** sugere nomes a partir do catálogo de entidades. Digitar no campo consulta `GET
/api/v1/taxonomy/entities?term=` — a mesma busca que o dossiê usa para associar uma entidade — e
escolher uma sugestão copia o nome para o texto, **nunca o `entity_id`**. A cópia é literal (o catálogo
guarda os nomes das entidades em minúsculas) e substitui só o trecho entre dois separadores, então as
vírgulas, os espaços e os outros nomes do arquivista continuam como estavam; o cursor fica depois do
nome copiado e o campo segue editável. É uma cópia e não um vínculo: uma mesclagem ou renomeação
posterior da entidade não alcança a descrição, e a ajuda embaixo do campo diz isso. A lista não é
filtrada por tipo de entidade, porque o NER classifica o mesmo órgão como `ORG`, `LOC` ou `PER` e
qualquer filtro esconderia um produtor real; o tipo vai como dica da sugestão. Um nome que o catálogo
não tem continua digitável, e o campo continua sendo a string que o contrato carrega. A relação, com os
filtros que ela destravaria, está na #242.

**Importar CSV** é a origem `csv` (#191, ADR 0019). O arquivo é interpretado **no navegador** (vírgula
ou ponto e vírgula, campos entre aspas, CRLF, UTF-8 com queda para Windows-1252); a tela mostra os
cabeçalhos detectados, uma prévia e as conferências locais, e envia só uma lista limitada de linhas
como JSON — nada vai para o storage de objetos e não existe rota multipart, então uma instalação cujo
storage não está configurado importa um CSV do mesmo jeito. O mapa é o da API (`GET
/api/v1/ingestion/csv/spec`), então um cabeçalho não pode ser aceito pela tela e recusado pelo
servidor; a API revalida cada linha com o contrato de staging, e a resposta por linha diz **aceita**,
**duplicada** (o `description_id` já existe) ou **inválida**, com o campo e a frase. Uma importação
parcial é normal. As linhas aceitas entram no staging como `origin_code='csv'` e uma `transfer` é
enfileirada depois delas.

O caminho antigo `/sistema/ingestao/nova` redireciona para cá, então um link compartilhado ainda abre
o formulário digitado.

### Lista e busca — `/acervo/lista`

A busca facetada do acervo: o termo, uma de **três ordens**, tipologia, categoria de assunto, tipo de
entidade, nível, um ramo do arranjo e um intervalo de datas. A URL é o estado, então uma lista
filtrada é compartilhável e o botão voltar funciona. Nada é escrito.

As três ordens respondem a perguntas diferentes, e a tela diz qual é qual:

| Modo | Pelo que ordena | Quando escolher |
| --- | --- | --- |
| Lexical (padrão) | `ts_rank` sobre o `search_vector` gerado, com reforço quando uma tag ou entidade casa | O arquivista sabe o termo que o título usa |
| Semântica | Similaridade de cosseno entre o termo e o vetor da descrição | O arquivista sabe o assunto, mas não o vocabulário do fundo |
| Híbrida | As duas fundidas por Reciprocal Rank Fusion (`RRF_K = 60`, janela `RRF_DEPTH = 100`) | O modo que não exige escolher, ao custo de carregar o modelo |

Os números por trás dessas frases ficam em `docs/log.md`, ao lado da bancada que os produziu
(`testing/evaluation/retrieval_modes.py`), e não nesta página: uma página que guarda um número que
deve mudar mente na próxima execução. O que a tela diz é que a evidência é um conjunto rotulado
pequeno e que serve de proxy, e que o modo lexical é preferível quando o termo é conhecido — o único
caso em que os dois braços diferem por margem larga.

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

### Histórico de exclusões — `/acervo/excluidas`

A trilha das exclusões, em leitura (`GET /api/v1/documents/deletions`), com busca e paginação no
servidor porque a trilha não tem teto. Ela **não é uma lixeira**: cada entrada é o retrato ISAD(G)
que a API gravou antes de excluir, e nada aqui restaura coisa alguma. Responde "fui eu que excluí
isto?" — código, título, nível, quem excluiu, quando, quantos filhos havia, e o retrato inteiro sob
demanda.

### Difusão — `/difusao`

O que o acervo expõe, e onde. Entrada de topo em Acervo, `CURATE`, e a metade do curador na decisão
que a página de canais do operador configura: o canal é o destino, esta página é o que vai para ele.

O cabeçalho carrega os mesmos quatro números em todas as visões — no site público, em canais,
aprovadas sem canal, em revisão — da rota de resumo, a mesma definição que o cartão do Início lê.
Quatro visões:

- **A publicar** — as aprovadas que nenhum canal carrega. Filtre por ramo, selecione registros ou
  publique o ramo inteiro; a pré-visualização mostra, por canal, os elegíveis, uma amostra e o que
  fica de fora (não aprovados, já cobertos, excluídos). Criar um escopo de ramo sem registro elegível
  é permitido de propósito: um filho aprovado depois entra nele sem um segundo ato.
- **Publicadas** — o que cada canal carrega, com os selos. **Manter privado** abre o mesmo painel com
  os canais do registro pré-selecionados: o lote revoga um escopo positivo direto no registro e grava
  o negativo, então a exclusão vence o escopo de um ancestral. Desmarcar um canal ali é "retirar do
  canal"; manter todos é "retirar de todos".
- **Publicações por ramo** — os escopos positivos e negativos, com nó, canal, a contagem que o
  desfazer alcançaria e as aprovadas do nó, o autor e a data. **Retirar o ramo** revoga o escopo
  positivo; **Desfazer a exclusão** revoga o negativo.
- **Histórico** — cada lote com o gesto, os canais, as contagens de aplicados e pulados, o autor, a
  data e o desfazer. O desfazer reverte entrada por entrada, restaura o que está inalterado e reporta
  o que pulou; um segundo desfazer é recusado.

Uma escrita é pré-visualizar e confirmar. A pré-visualização é uma leitura — não escreve nada — e o
token que ela devolve é ecoado pela confirmação: um conjunto que mudou entre as duas chamadas, um
token expirado ou adulterado responde 409 com "pré-visualize de novo". É uma checagem de consistência,
não uma permissão; a escrita é o `CURATE` da sessão. Publicar não aprova: um registro coberto é
`HUMAN_APPROVED` porque a cobertura exige, e um registro ainda em revisão é pulado pela
pré-visualização.

O seletor só oferece os canais configurados e ativos; um pausado é recusado com uma frase, e a página
de canais o marca como pausado.

### Descrição — `/acervo/$descriptionId`

A ficha, com quatro abas na URL. O título sugerido aparece **ao lado** do campo que ele propõe e
nunca é o valor guardado: ele é derivado na leitura a partir dos trechos de escopo `TITLE`, e só o
arquivista escreve `final_title`.

#### Descrição

O primeiro cartão é a **miniatura**, e ela vem da API, não do navegador: a leitura anuncia
`thumbnail_url` e a SPA a liga a um `<img>`, então o cliente nunca monta um caminho e nunca fala com o
bucket (ADR 0017). Os bytes são `GET /api/v1/documents/{description_id}/thumbnail` (`AUTHENTICATED`);
a rota responde 404 quando a origem não tinha imagem, quando o objeto não está mais no bucket ou
quando esta instalação não tem armazenamento de objetos — neste último caso a leitura não anuncia
`thumbnail_url`, então o cartão é o mesmo "Sem imagem" e nenhum pedido é feito (ADR 0022). O 503 fica
para um storage configurado que não pode ser lido. Quatro das 101 descrições do acervo de referência
não têm imagem de origem, então "Sem imagem" é um estado normal, e uma URI guardada cujo objeto sumiu
mostra "Imagem indisponível" — nunca o ícone de imagem quebrada. A lista do acervo mostra a mesma
miniatura a 56 px, que é como se reconhece uma fotografia sem abrir o dossiê.

A decisão é o próprio registro, agrupado nas áreas da norma — **3.1 Identidade**, **3.2 Contexto**,
**3.3 Conteúdo e estrutura**, **3.4 Acesso e uso**, **3.5 Materiais relacionados**, **3.6 Notas** e
**3.7 Controle da descrição** — mais o nível, a tipologia e o selo de difusão, com uma nota do porquê.
O registro ISAD(G) inteiro é editável: o acervo guarda todo campo que o transform de staging
interpretou, não o subconjunto que a transferência copiava. A escrita é `PATCH
/api/v1/documents/{description_id}` (`CURATE`). Ela registra o antes e o depois do que mudou em
`archive_document_revisions`, grava a autoria a partir da sessão e define `HUMAN_APPROVED` — o que tira
a descrição da fila da IA. Reversível: outra edição registra uma nova revisão; o histórico é só de
acréscimo e o valor anterior fica visível na aba `Histórico`. Publicar e retirar usam o mesmo comando e
são igualmente reversíveis.

Dois valores são exibidos e não editados, porque são evidência e não descrição: `date_expression` (a
data como a fonte escreveu — `Década de 1980` ao lado do `1980-01-01` interpretado, que é o que o
parser conseguiu dela) e `original_url` (a página de onde o registro foi lido). O nível e a tipologia
são seletores sobre os seus catálogos; `language_name` é um seletor sobre `GET /api/v1/languages`, um
catálogo declarado em código porque um idioma não carrega regra que a instituição edite. O valor
guardado é o nome do catálogo: uma variante declarada (`Português/Brasil`, `Português Brasil`) é
dobrada na transferência, então a coleção inteira lê uma grafia — e o seletor **mantém um valor que o
catálogo não conhece**, marcado como tal, para que abrir o dossiê nunca apague um idioma que o
catálogo nunca viu. O pai declarado aparece em 3.1 mesmo enquanto está pendente (`BR PRPMC —
aguardando`), porque a origem pode entregar o filho antes do pai; o vínculo em si se faz na aba
`Arranjo`.

O cartão **Objeto digital** aparece com o controle **desabilitado**: o acervo guarda a descrição, não
o arquivo, e o objeto digital é a #198. A frase que diz isso é definida uma vez
(`apps/curator/src/lib/copy.ts`) e o formulário de entrada manual mostra a mesma.

#### Assuntos

A decisão é quais tags e entidades esta descrição carrega e em que categoria cada tag fica. As escritas
são `POST`/`DELETE /api/v1/documents/{description_id}/tags[/{tag_id}]` e o par de entidades
(`CURATE`), mais `PATCH /api/v1/taxonomy/tags/{tag_id}` para a categoria. Associar e desassociar são
reversíveis: a revisão guarda a **lista inteira de nomes** de cada lado, e chamar a mesma rota duas
vezes não escreve revisão nenhuma.

Cada entidade mostra a **origem do seu vínculo**: `IA` quando o extrator a escreveu, `confirmada`
quando uma pessoa a associou ou confirmou, e `não rastreada` para um vínculo escrito antes de a coluna
existir. Uma origem desconhecida nunca é exibida como se fosse do modelo. `Confirmar` associa uma
entidade que o extrator já propôs sem duplicá-la: o vínculo fica onde está e sua origem vira `HUMAN` —
o veredito positivo que o arquivista não conseguia registrar antes (#135). Confirmar um vínculo que já
existia não muda nome nenhum, então não escreve revisão: o registro da confirmação é a origem do
vínculo, e a descrição vira `HUMAN_APPROVED`, o que a tira da fila da IA.

!!! warning "A categoria é uma decisão sobre o vocabulário, não sobre esta descrição"

    Mudar a categoria de uma tag move a tag em **todas** as descrições que a carregam, e a tela diz
    isso ao lado do seletor. Escolher "sem categoria" devolve a tag ao classificador de assunto, que
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

O plano é alcançado por `/configuracoes` — decidir os degraus é trabalho de montagem, não curadoria do
dia a dia — e o diagnóstico ficou no menu, sob "Acervo", ao lado da árvore que ele lê. Sem o plano, o
grupo "Arranjo" teria uma linha só, então ele deixou de existir.

| Tela | Decisão | Reversível? |
| --- | --- | --- |
| Plano de arranjo — `/arranjo/plano` | aprovar ou rejeitar cada degrau proposto, e materializar a árvore | sim — a decisão pode ser reaberta, e a materialização tem desfazer |
| Diagnóstico do arranjo — `/arranjo/diagnostico` | nenhuma (a evidência; o conserto é em outra tela) | sim (só leitura) |

### Plano de arranjo — `/arranjo/plano`

A máquina lê os códigos de referência e propõe os degraus; a decisão é do arquivista. Em cada degrau a
evidência vem primeiro — a contagem de descrições, os níveis declarados, as amostras — e o formulário
por último:

- **Propor níveis** — `POST /api/v1/hierarchy/plans/suggest` (`CURATE`). Escreve as perguntas. É
  idempotente por código e nunca reescreve um degrau que saiu de `SUGGESTED`, então a mesma pergunta
  não é feita de novo.
- **Aprovar** um degrau — `PATCH /api/v1/hierarchy/plans/{plan_id}` (`CURATE`) com `APPROVED`, o nível
  escolhido, um título opcional, um código opcional em "fundir em" e uma nota. Aprovar **exige** o
  nível: é a decisão que o código não sabe tomar.
- **Rejeitar** — a mesma rota com `REJECTED`. Um degrau rejeitado deixa suas descrições órfãs de
  propósito: elas caem no degrau aprovado mais próximo acima.
- **Reabrir decisão** — a mesma rota com `SUGGESTED`. Reversível: a decisão volta para a fila e a
  próxima proposta pode atualizar a evidência dela. A decisão nunca é sobrescrita por uma proposta
  nova.

Os degraus aparecem como a árvore que os códigos implicam, não como uma lista recuada. A caixa à
esquerda de uma linha recolhe aquele ramo — a linha passa a dizer quantos degraus e quantas decisões
ele esconde —, enquanto o chevron do cartão abre o corpo da decisão; recolher o ramo não reinicia os
cartões que estão dentro dele: expandir devolve cada um como estava. Os filtros de status, aviso e
código mantêm os pais e o ramo de cada
degrau que casa, e um pai de um degrau que casa não pode ser recolhido. **Recolher os decididos**
fecha os ramos que não têm nenhum degrau ainda `SUGGESTED`. A URL guarda só o topo de cada ramo
recolhido, então o colega abre a mesma vista.

O painel lateral materializa a árvore: ele sempre oferece "Conferir impacto" primeiro, e o
botão de aplicar fica desabilitado até a prévia existir. Só os degraus aprovados são materializados. A
prévia e a aplicação compartilham um planejador, então o número aprovado é o número escrito. O que o
desfazer restaura está descrito em **o lote que tem desfazer**.

### Diagnóstico do arranjo — `/arranjo/diagnostico`

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
linha desclassificaria toda descrição que aponta para ela, além de excluir o registro de que ela
existiu.

| Tela | Decisão | Reversível? |
| --- | --- | --- |
| Níveis de descrição — `/arranjo/niveis` | a escada contra a qual o arranjo é escrito | sim (aposentar e reativar) |
| Tipologias — `/arranjo/tipologias` | a forma diplomática que o classificador propõe, e as descrições que ele recusou | sim (aposentar e reativar; arquivar uma descrição é uma revisão do documento) |
| Vocabulário do acervo — `/vocabulario` | o que os códigos e termos deste acervo significam | sim (aposentar e reativar) |

### Níveis de descrição — `/arranjo/niveis`

O catálogo de níveis. Criar um degrau é `POST /api/v1/hierarchy/levels` e editar é
`PATCH /api/v1/hierarchy/levels/{level_id}` (`CATALOGUE`): nome, descrição, grafias aceitas, se exige
unidade superior e se pode ter filhos. Duas regras que a tela declara em vez de contornar:

- **não há exclusão.** `is_active=false` é o caminho, e o peso de um degrau aposentado continua
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
documentação para quem lê. Aposentar uma tipologia é a única alavanca que alcança o modelo — ela
deixa de ser proposta sem desclassificar nenhuma descrição — e é por isso que o peso das aposentadas
continua na tela.

A tela também lista as descrições que o classificador recusou. `GET /api/v1/typologies/refusals`
(`AUTHENTICATED`) devolve uma página das descrições cuja melhor pontuação ficou abaixo do limiar, da
mais próxima do limiar para a mais distante, com o palpite da execução e a pontuação que ela viu. A
lista lê o mesmo predicado da contagem do classificador e deixa de fora a descrição que uma pessoa já
arquivou, mesmo que a linha da fila continue no banco. Escolher uma tipologia ali é
`PATCH /api/v1/documents/{id}` (`CURATE`): a escrita do dossiê, que grava a revisão e marca a
descrição como `HUMAN_APPROVED`. Dá para voltar atrás pelo dossiê, e o antes/depois fica na trilha.
Uma lista vazia quer dizer que nenhuma recusa está aberta, não que o catálogo cobre o acervo — uma
descrição que nenhuma execução alcançou não tem linha, e arquivar uma a tira da lista sem apagar a
evidência. Se nenhuma tipologia serve, crie ou reative uma no catálogo da mesma tela; ainda não existe
veredito durável para "esta descrição não tem tipologia".

### Vocabulário do acervo — `/vocabulario`

O que *este* acervo declara, em oposição ao que a língua ou o software fixam. Duas listas:

- **nomes de arranjo** — `POST`/`PATCH /api/v1/vocabulary/arrangement-terms` (`CATALOGUE`): um token
  (`SMU`) ou o código inteiro (`BR PRADAP`) mapeado para o nome que a proposta de arranjo sugere; o
  código inteiro tem precedência sobre o último token;
- **termos do acervo** — `POST`/`PATCH /api/v1/vocabulary/collection-terms` (`CATALOGUE`): as
  grafias que o acervo carrega e que não são assunto, tipadas para o guarda reconhecer um lugar ou
  um nome de pessoa. O que o nome *é* fica no eixo de entidades (`LOC`, `PER`), não num estado da
  tag: o eixo de assunto simplesmente para de adivinhar sobre ele.

O que é propriedade da língua portuguesa — *rua*, *não identificado*, *303 anos*, um ano solto — fica
no perfil de idioma e **não** aparece aqui: mudá-lo seria mudar o significado que o software dá à
palavra. Aposentar um termo não o exclui, e um termo aposentado volta a ser tratado como assunto na
próxima execução do classificador.

## Assuntos

| Tela | Decisão | Reversível? |
| --- | --- | --- |
| Tags — `/assuntos/tags` | o peso, as duplicatas, a fila de merges **e a decisão de assunto de cada tag** | o merge sim (ledger); a decisão de assunto sim (dá para voltar atrás) |
| Categorias — `/assuntos/categorias` | as categorias de assunto que o classificador lê, **e o que está dentro de cada uma** | sim (aposentar e reativar) |
| Descobrir Categorias — `/assuntos/descobrir` | se um tema proposto merece uma categoria | sim (a proposta não escreve nada) |
| Não é assunto — `/assuntos/excecoes` | quais termos saem do eixo de assunto e têm a grafia banida de voltar a ser tag | sim (o banimento não apaga nada, e o desfazer levanta o banimento que esta decisão plantou) |
| Grafias bloqueadas — `/assuntos/grafias` | quais grafias a extração não pode recriar, e a exclusão das tags que já existem com elas | o bloqueio sim (desbanir); a exclusão sim (uma linha de ledger por tag, restaurando a tag, os vínculos e as grafias — nunca o bloqueio) |

### Tags — `/assuntos/tags`

Uma rota, quatro perguntas, uma conversa só: o arquivista vê que `alvenarias` pesa pouco, encontra a
quase-duplicata dela e decide se a absorve. Três das abas são o jeito de olhar; a quarta,
**Classificar**, é onde a decisão de assunto se toma, e é onde os dois cartões de assunto do Início
caem. A aba ativa está na URL.

As grafias bloqueadas eram a quinta aba, e são **Grafias bloqueadas — `/assuntos/grafias`** desde a
#232: tela própria, ao lado de *Não é assunto*, porque a descrição desta página nunca dizia que a aba
guardava a única escrita que apaga uma tag. `?aba=stopwords` continua respondendo com a tela nova.

#### Relevância

Só leitura: `GET /api/v1/taxonomy/tags/relevance/{method}`. A contagem mostra o que domina o acervo;
o TF-IDF mostra o que é específico, punindo o que aparece em toda parte. As duas listas respondem
perguntas diferentes de propósito.

#### Similaridade

Pares por similaridade de trigrama, mostrados crus, com a pontuação e os dois identificadores. A
leitura é `GET /api/v1/taxonomy/tags/similar`. A similaridade não diz qual grafia é a boa:
`'alameda cabral'` e `'al. alameda cabral'` têm 1,000.

A decisão é unificar: `POST /api/v1/taxonomy/tags/merge` (`CURATE`), depois de uma prévia
(`POST /api/v1/taxonomy/tags/merge/preview`, uma leitura que calcula o mesmo plano que a escrita
executa). O painel abre sempre com o impacto na frente: documentos atualizados, vínculos reescritos,
tags absorvidas, grafias registradas e reapontadas, e o aviso que precisa ser lido antes do clique —
`category_would_be_lost`, quando a canônica não tem categoria e uma absorvida tem, o que faria o merge
excluir uma classificação de assunto.

O merge é **reversível**: a escrita é registrada por tag absorvida no ledger de merges antes de
qualquer coisa mudar, e o desfazer (`DELETE /api/v1/taxonomy/tags/merge-log/{merge_id}`, `CURATE`)
restaura a linha, os vínculos, a classificação e o estado das grafias. O desfazer apaga apenas os
vínculos que o merge criou, então não solta um documento que já carregava a canônica. As linhas também
podem ser marcadas entre si e unificadas como um conjunto, que é como um merge atravessa vários pares
(`carlos de carvalho` aparece em mais de uma linha).

Uma seleção marcada tem um **segundo destino**, e ele é o outro tipo de escrita: **Banir N marcadas**
registra as grafias em `POST /api/v1/taxonomy/tags/stopwords` (`CURATE`), no eixo escolhido ao lado do
botão. Banir **não apaga nada** — as tags continuam no acervo, vinculadas e alcançáveis pela busca, e o
passo que as exclui é a exclusão das tags em **Grafias bloqueadas — `/assuntos/grafias`**, atrás da
própria prévia e com um ledger que restaura cada tag. A marcação sobrevive ao banimento: a mesclagem
para a qual ela foi feita continua possível.

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

#### Classificar

Onde o assunto de uma tag se decide, e a aba que os cartões do Início abrem. A leitura é
`GET /api/v1/taxonomy/tags/catalog` (`AUTHENTICATED`), filtrada por `subject_state` e opcionalmente
por `macro_category_id`, paginada e ordenada por peso — a tag que mais descrições carrega é a decisão
que vale mais primeiro. Ela existe porque o type-ahead não responde a essa pergunta: ele exige um
termo e devolve um topo por peso, então o cartão que prometia "76 tags sem categoria de assunto" não
tinha leitura que marcasse quais linhas eram.

O estado é uma **partição**, e `ALL` é a ausência de filtro, não um estado:

| `subject_state` | O que significa |
| --- | --- |
| `PENDING` | Sem categoria e sem veredito: ninguém decidiu. É o que o cartão do Início conta |
| `NOT_SUBJECT` | Uma pessoa declarou que a tag não é assunto; o classificador para de adivinhar sobre ela e a grafia fica banida de voltar a ser tag |
| `LOW_CONFIDENCE` | O classificador rodou, não teve confiança para arquivar a tag e a deixou sem decisão |

A linha carrega a evidência (peso e a confiança do classificador) e exatamente um de dois destinos,
por `PATCH /api/v1/taxonomy/tags/{tag_id}` (`CURATE`):

- **uma categoria** — a categoria em que a tag entra. A decisão é **global**: muda o selo de todas as
  descrições que carregam a tag, e a tela diz isso antes do clique;
- **não é assunto** — `macro_category_id=null`, que é a mesma escrita que a tela *Não é assunto* faz.
  A tag continua no acervo e alcançável pela busca, e só a coluna seria uma decisão que a próxima
  execução sobrescreve; por isso o termo entra em `domain_subject_exclusions` **e a grafia é banida no
  escopo `TAG`**, para a próxima ingestão não recriá-la. O caminho de volta é
  `DELETE /api/v1/taxonomy/tags/subject-exclusions`, e ele levanta só o banimento que esta decisão
  plantou.

Um produtor, um lugar ou uma pessoa **não** é um terceiro destino. O que o nome *é* pertence ao eixo
de entidades, onde ele carrega um tipo (`LOC`, `PER`, `ORG`) que a busca e a projeção pública leem;
uma grafia que é tag e entidade ao mesmo tempo se resolve em **Conflitos — `/entidades/conflitos`**,
que bane a grafia perdedora e guarda um ledger. Declarar o termo não-assunto é o que o tira da fila de
assunto; a entidade é onde ele mantém o significado. A medição por trás do estado removido continua
valendo — `alfa` alcança 2.376 descrições e `cidade` 1.865, e forçá-las para dentro de uma categoria é
causa medida do defeito de classificação —, mas a resposta agora é a entidade e a exclusão, não um
quarto estado da tag.

As mesmas duas ações valem para uma **seleção**, uma requisição por tag, e o lote informa quantas tags
escreveu e para onde. Nada nesta aba exclui: banir uma grafia e excluir as tags ficam em **Grafias
bloqueadas — `/assuntos/grafias`**, cada um no seu passo, e a exclusão guarda um ledger com o desfazer
de cada tag.

### Grafias bloqueadas — `/assuntos/grafias`

As grafias que um bloqueio mantém fora do vocabulário, e a única escrita da taxonomia que apaga uma
tag. Era a quarta aba de **Tags** até a #232, e virou tela própria porque a página em que ela morava
descrevia relevância, duplicatas e mesclagem, e nunca dizia que a aba guardava a única escrita
destrutiva do eixo de assunto.

Não é uma segunda vista de *Não é assunto*, e a tela diz isso na primeira linha: o veredito é sobre o
que o termo **significa** — e é o que faz a classificação de assunto parar de adivinhar —, enquanto o
bloqueio é sobre a **grafia** — e é o que impede a próxima ingestão de recriar a tag. Confirmar um
veredito planta um bloqueio no escopo `TAG`, e é por isso que a mesma grafia aparece nas duas listas: a
lista diz de onde veio cada bloqueio, e o que veio de um veredito leva de volta à tela que decidiu. As
duas telas se apontam, e o gate `testing/unit/curator/test_curator_copy.py` falha se um dos links ou o
redirecionamento de `?aba=stopwords` desaparecer.

A tela separa três coisas:

- **Banir** — `POST /api/v1/taxonomy/tags/stopwords` (`CURATE`) registra que um termo não vale a pena
  num eixo: `TAG` (o eixo de assunto), `ENTITY` (NER) ou `ALL`. Uma palavra tem exatamente um escopo
  — banir de novo **move** — e banir **não apaga nada**. Um banimento digitado aqui é gravado com
  `source=HUMAN`; o que a tela *Não é assunto* planta é `EXCLUSION`, e o que uma resolução de
  conflito planta é `CONFLICT`. A lista mostra o escopo em todo termo e a origem como selo quando ela
  não é `HUMAN` — um termo digitado aqui é o padrão, e o selo marca os que chegaram como consequência
  de outra decisão.
- **Desbanir** — `DELETE /api/v1/taxonomy/tags/stopwords` (`CURATE`). Reversível.
- **Casamento** — `PATCH /api/v1/taxonomy/tags/stopwords` (`CURATE`) muda como um banimento existente
  casa, sem banir de novo: banir de novo sobrescreveria a origem que um conflito ou a tela *Não é
  assunto* registraram. `TOKEN` bloqueia a palavra **e qualquer nome que a contenha como palavra
  inteira** — o span fundido `IPTU do Exemplo` — e `EXACT` bloqueia só a grafia, que é o que uma
  palavra genérica que inicia um nome próprio precisa: `alameda` bloqueia `alameda`, nunca `Alameda
  Cabral`. Só os eixos `ENTITY`/`ALL` leem isso. Toda entrada de `domain_ner_exclusions` casa pela
  grafia exata pelo mesmo motivo: o conflito era sobre `casa`, não sobre `casa da memória` (#160).
- **Excluir as tags** — `POST /api/v1/taxonomy/tags/stopwords/purge` (`CURATE`), depois de
  `POST /api/v1/taxonomy/tags/stopwords/purge/preview`. Esta é a escrita que apaga as tags. A prévia
  lista as tags que morreriam, com a contagem de documentos, a categoria **e de onde veio o
  banimento** (`HUMAN`, `CONFLICT` ou `EXCLUSION`), para um termo banido com o acervo em mente não se
  confundir com um digitado à mão; o botão de aplicar fica desabilitado até a prévia existir.

Cada tag apagada é gravada num **ledger** (`archive_stopword_purge_log`) antes de sumir: o retrato da
linha, os documentos que a carregavam e as grafias que apontavam para ela. A resposta da exclusão traz
os `purge_ids`, a tela os mostra em **Registro das exclusões**, e `DELETE
/api/v1/taxonomy/tags/stopwords/purge-log/{purge_id}` (`CURATE`) restaura a tag, os vínculos e as
grafias; um identificador desconhecido é **404** e uma segunda tentativa é **409**. O desfazer **não**
levanta o bloqueio — o termo continua bloqueado, e a próxima exclusão lista a tag restaurada de novo.

!!! warning "O escopo protege o outro eixo"

    A exclusão lê apenas `TAG`/`ALL`. Um termo bloqueado no eixo `ENTITY` é um veto de NER e nunca
    pode fazer a exclusão de assunto apagar uma tag que o curador manteve — os dois são guardados em
    lugares diferentes de propósito.

### Categorias — `/assuntos/categorias`

As categorias que o classificador de assunto lê. `POST /api/v1/taxonomy/macro-categories` e
`PATCH /api/v1/taxonomy/macro-categories/{category_id}` (`CATALOGUE`) as criam, renomeiam, descrevem,
aposentam e reativam; uma categoria aposentada mantém o peso visível. Duas notas honestas da tela: o
**rótulo do classificador** é um ajuste do curador, não uma melhoria — medido em 44 tags rotuladas à
mão, uma frase em vez do nome nu leva a 0,000 com 65% das tags numa única categoria — e uma **categoria nova
só passa a valer quando o classificador rodar de novo**, porque o carimbo do worker é o hash do
conjunto de rótulos, o que devolve as tags à fila sozinho.

Cada cartão abre em duas abas. **Descrições** lista as descrições que a categoria contém, dez por vez,
pela busca do acervo (`GET /api/v1/documents?macro_category_id=`, `AUTHENTICATED`); o selo do cartão
conta descrições **distintas** pela mesma junção, então o número do cartão e o `total` da lista são uma
definição contada duas vezes. Uma categoria sem nenhuma diz isso — as aposentadas não são um defeito.
**Editar** é o formulário: nome, rótulo do classificador e descrição.

O botão da linha abre uma **prévia somente leitura** de uma descrição — código de referência, título,
data, nível e tipologia, caminho no arranjo, as tags com as suas categorias e a situação de revisão —
sobre a lista, para reconhecer a descrição sem uma ida ao dossiê. O painel não escreve nada: o
**Editar** dele sai para `/acervo/{description_id}?aba=descricao`. A categoria aberta, a página dela e
a descrição em prévia vivem na URL, então o botão voltar fecha o painel e a página sobrevive a ele.

### Descobrir Categorias — `/assuntos/descobrir`

Roda o motor de agrupamento de verdade (`POST /api/v1/taxonomy/tags/suggest-macro`, só leitura:
`AUTHENTICATED`) sobre as tags ou os documentos para achar um tema que o vocabulário ainda não cobre.
É um clique deliberado e não um carregamento de página: o motor leva segundos e pode rodar num
subprocesso. Os clusters são **propostas** — nada entra no vocabulário antes de o arquivista
cadastrar, o que é `POST /api/v1/taxonomy/macro-categories` (`CATALOGUE`). Descartar uma proposta é
local à tela. Um corpus pequeno demais responde com uma sugestão vazia e uma mensagem, não com um
erro.

Lendo os **documentos**, a tela oferece as colunas que o clustering lê: `GET
/api/v1/taxonomy/tags/suggest-macro/columns` publica o texto da IA e o subconjunto que a execução lê
quando o corpo não escolhe nenhuma, e a tela desenha um checkbox por coluna a partir dessa leitura —
ela não digita os cinco nomes. `final_title` está no corpus e **fora** do padrão: uma coluna pode
entrar no que a IA lê sem mudar em silêncio o que o clustering lê. O corpo só leva
`columns_to_extract` depois que uma coluna se move, e a rota recusa um nome desconhecido com **400**
que o nomeia (antes do #174 o erro de digitação chegava a um `getattr` e respondia **500**), recusa
uma lista vazia, e recusa a lista com `source_type=tags`, onde ela seria ignorada.

### Não é assunto — `/assuntos/excecoes`

A metade curada do "isto não é assunto de jeito nenhum". O guarda determinístico pega o que tem forma
— uma data, um placeholder, um logradouro, um número solto — e, na medição real, pegou 1 de 4 dos
não-assuntos rotulados à mão; o resto é julgamento semântico que nenhuma regra resolve (`pessoas`,
`vista aérea`, `capanema`). A tela mostra os candidatos do guarda com a evidência deles (peso, se o
termo é um lugar, se a mesma grafia também é entidade, a categoria que o bloquearia e se a grafia já
está banida) e oferece registrá-los com `source=RULE` ou um a um.

Confirmar planeja e aplica numa só chamada: a escrita abaixo consome o mesmo planejador que a rota de
prévia usa, então as duas não podem discordar. A prévia é `POST
/api/v1/taxonomy/tags/subject-exclusions/preview` (`AUTHENTICATED`); ela recebe os termos e nada mais,
porque um plano não tem motivo a declarar nem proveniência a informar, e responde `applicable` e
`blocked`. O campo **Vetar termos** a consulta enquanto a digitação assenta (250 ms) e mostra a
recusa **antes** do clique: um termo cuja tag já está numa categoria é nomeado com a categoria
enquanto o arquivista ainda pode mudar o termo, e a resposta da escrita só confirma. O campo grava
todos os termos que se aplicam, então uma recusa parcial não desabilita o botão — só uma lista em que
**todos** os termos estão bloqueados desabilita, porque aí a escrita não registraria nada.

A escrita é `POST /api/v1/taxonomy/tags/subject-exclusions` (`CURATE`), e ela faz duas coisas de uma
vez: registra o termo em `domain_subject_exclusions`, para o classificador de assunto parar de
adivinhar sobre ele, **e bane a grafia no escopo `TAG`**, para a próxima ingestão não recriar a tag
que acabou de ser decidida. **O banimento não apaga nada**: a tag continua no acervo, continua
vinculada e continua alcançável pela busca. Removê-la é um ato separado — a exclusão das tags em
**Grafias bloqueadas — `/assuntos/grafias`**, atrás da própria prévia e com um ledger que restaura
cada tag — e a prévia diz quais banimentos foram plantados aqui (`EXCLUSION`) e quais à mão
(`HUMAN`).

A tela e **Grafias bloqueadas** são dois objetos, não dois filtros, e cada uma aponta para a outra:
esta decide o que o termo **significa** e é o que para o classificador; aquela veta a **grafia** e é o
que impede a extração de recriar a tag. Um veredito planta um bloqueio `TAG`, então a mesma grafia
aparece nas duas listas — a lista de bloqueios diz qual veio de um veredito e leva de volta para cá.

Duas respostas que a tela precisa mostrar:

- um termo cuja tag já está numa **categoria** não é aplicado: ele volta em `blocked` com a categoria
  que precisa ser esvaziada primeiro, porque "em que categoria esta tag está?" é uma pergunta sobre a
  *tag*, respondida no catálogo de tags, e uma afirmação sobre um *termo* não pode desarquivar um
  veredito humano. O código é `SUBJECT_EXCLUSIONS_BLOCKED` quando nada foi aplicado e algo foi
  recusado, `SUBJECT_EXCLUSIONS_PARTIAL` quando alguns foram aplicados e alguns recusados, e
  `created` / `banned` / `blocked` levam as três respostas;
- a rota deliberadamente não propõe nada para a metade semântica: os sinais disponíveis mentem, e um
  modelo que não sabe se abster responderia com confiança e errado.

A reversão é `DELETE` (`CURATE`, o "restaurar" da tela). Ela responde `removed` e `unbanned`, e o
levantamento é exato: só um banimento que esta decisão plantou sai com ela. Uma grafia que uma pessoa
baniu na tela **Grafias bloqueadas**, ou que uma resolução de conflito plantou antes, sobrevive.

## Entidades

| Tela | Decisão | Reversível? |
| --- | --- | --- |
| Entidades — `/entidades/lista` | o tipo de um nome, a grafia de um nome, e se dois nomes são um | o tipo sim; a renomeação **sim** (uma linha no ledger); o merge **sim** (uma linha por entidade absorvida) |
| Remover de Entidades — `/entidades/excecoes` | quais grafias são assunto, não nome próprio, e o expurgo retroativo que as segue | ambos **sim**: a linha do veto pelo seu próprio `DELETE`, o expurgo pelo seu ledger (`archive_ner_purge_log`) |
| Conflitos — `/entidades/conflitos` | se uma colisão pertence ao eixo de assunto ou aos nomes, um par de cada vez ou uma categoria inteira de uma vez | sim (uma linha no ledger por par, com o desfazer) |

### Entidades — `/entidades/lista`

O vocabulário de nomes próprios, por peso ou por similaridade. Cinco decisões:

- **Reclassificar o tipo** — `PATCH /api/v1/taxonomy/entities/{entity_id}/reclassify` (`CURATE`), só
  entre `ORG`, `PER` e `LOC`. Isso não é renomear um rótulo: o serviço grava também o sinônimo de
  ancoragem, então o extrator devolve aquela grafia com o tipo novo em toda execução futura.
- **Renomear** — `PATCH /api/v1/taxonomy/entities/{entity_id}` (`CURATE`): corrige a grafia de um
  nome, e **não** é um merge. A grafia anterior continua ancorada como sinônimo a menos que o
  arquivista desligue `keep_old_synonym`, que é o que faz uma extração futura da grafia antiga
  continuar resolvendo para esta entidade — e um erro de digitação é exatamente o caso em que ela não
  deveria. A escrita deixa uma linha `RENAME` no mesmo ledger que o merge usa, então o "desfazer" da
  tela restaura o nome e remove a grafia que ele plantou. Uma grafia que outra entidade já carrega é um
  **409** que nomeia o gêmeo e aponta para o merge, nunca uma sobrescrita silenciosa e nunca um
  conflito estrutural cru.
- **Excluir** uma entidade — `DELETE /api/v1/taxonomy/entities/{entity_id}` (`CURATE`), oferecido só
  numa linha que nenhuma descrição carrega, onde excluir não perde vínculo. Sem desfazer.
- **Purgar órfãs** — `POST /api/v1/taxonomy/entities/orphans/purge` (`CURATE`): a mesma decisão em
  lote. Sem desfazer.
- **Mesclar** — `POST /api/v1/taxonomy/entities/merge` (`CURATE`): as entidades absorvidas deixam de
  existir, seus vínculos passam para a canônica, suas grafias viram sinônimos, e um nome novo opcional
  para a canônica faz o antigo virar sinônimo também. A decisão é precedida da prévia
  (`POST /api/v1/taxonomy/entities/merge/preview`, uma leitura): ela devolve quantas descrições passam
  a carregar a canônica, quantos vínculos são reescritos, quais entidades são absorvidas e os avisos a
  olhar, calculada pelo **mesmo planejador** que a escrita executa. Entidades não têm catálogo de
  propostas, mas têm ledger: cada absorvida é registrada **antes** de qualquer mudança, e o desfazer
  (`DELETE /api/v1/taxonomy/entities/merge-log/{merge_id}`, o "desfazer" da tela) restaura a linha,
  seus vínculos, suas grafias e o nome que a canônica perdeu.
  `GET /api/v1/taxonomy/entities/merge-log` é a trilha, buscável pelas duas grafias de cada entrada.
  A lista de pares é evidência crua, com os dois identificadores, porque duas linhas podem ler nomes
  quase iguais e a canônica é uma escolha que o arquivista precisa conseguir distinguir.

O merge tem três portas e um único painel atrás de todas: a seleção na **Relevância**, um par na
**Similaridade** e o cartão **Mesclar pelo nome** acima das abas. O cartão existe porque as outras duas
são guiadas por listas que o arquivista não controla — a relevância é ordenada por peso e limitada,
então dois nomes carregados por números muito diferentes de descrições nunca ficam na mesma página, e
a similaridade é trigrama, a única medida que falha no par de que ele tem mais certeza (`smu` e `smcs
secretaria municipal de comunicação social`: 68 descrições contra 1, e 0.045 de similaridade). O cartão
recebe os nomes pelo type-ahead que a aba Assuntos do dossiê já usa, então herda o piso de dois
caracteres da API em vez de inventar um; mostra o peso de cada nome, para a canônica ser escolhida com
os números à vista; e **a lista é dele** — não consome as caixas marcadas na Relevância, e com menos de
dois nomes nada é escrito.

Ler é a outra metade desta tela, e o cartão se abre nela. Um nome se expande nas **descrições que o
carregam** — a busca do acervo (`GET /api/v1/documents`) com `entity_id`, paginada de dez em dez
dentro do cartão, de modo que o selo acima e o `total` da lista são um número contado duas vezes;
`testing/integration/api/controller/test_entity_documents.py` falha quando os dois deixam de
concordar. Clicar numa linha abre a prévia somente-leitura (`?descricao=`) que a tela de categorias já
usa, e nada nela escreve. O "Editar" dela cai na aba **Assuntos** do dossiê, que é onde as entidades
de uma descrição são adicionadas e removidas. Um cartão fica aberto por vez, e `?aberta=`, `?offset=`
e `?descricao=` carregam esse estado na URL — então o botão voltar fecha o painel e um colega pode
receber a mesma vista exata.

A segunda aba do cartão é a renomeação, e o botão **Renomear** ao lado do nome é quem a abre. Ele é o
recurso da própria linha e nunca mescla: o merge parte de dois ou mais nomes e só renomeia a canônica
como efeito colateral.

### Remover de Entidades — `/entidades/excecoes`

O veto "esta grafia é assunto, não nome próprio". **Vetar não apaga nada.** A escrita é `POST
/api/v1/taxonomy/entities/ner-exclusions` (`CURATE`), com um motivo guardado para auditoria, e a
reversão é `DELETE` (o "remover veto" da tela), que reabre o termo para as próximas extrações. Um
comportamento que a tela declara porque não é visível na lista: o bloqueio é **por limite de token**,
não por nome exato (o spaCy funde tokens vizinhos, então um `iptu` vetado não barraria `"IPTU do
Batel"` numa comparação exata).

A metade retroativa é um ato separado, **Expurgar do passado**:
`POST /api/v1/taxonomy/entities/ner-exclusions/purge` (`CURATE`), depois de
`POST /api/v1/taxonomy/entities/ner-exclusions/purge/preview`. O impacto lista toda entidade já
extraída de uma grafia vetada, com as descrições que a carregam, e a escrita consome o mesmo plano.
Cada entidade apagada entra num **ledger** (`archive_ner_purge_log`) antes de sair: o snapshot da
linha, os documentos que a carregavam, as grafias que apontavam para ela e o `excluded_term` que a
justificou. A resposta carrega os `purge_ids`, a tela os mostra em **Histórico de expurgos**, e
`DELETE /api/v1/taxonomy/entities/ner-exclusions/purge-log/{purge_id}` restaura a entidade, os seus
vínculos e as suas grafias — **sem** levantar o veto, então o próximo expurgo lista a entidade
restaurada de novo. Use-o para reverter a perda; use "remover veto" para reabrir o termo.

A tela de conflitos resolve o mesmo choque com o mesmo par de escritas, e lá também é reversível na
mesma forma: uma linha de ledger por par (`archive_conflict_resolution_log`), com a linha perdedora, os
seus vínculos e as suas grafias restauradas pelo desfazer. Chegar à operação por qualquer das telas
restaura as mesmas coisas.

Esta é a outra metade da governança bidirecional: ela registra o curador ou o juiz dizendo "isto
pertence ao eixo de assunto", e é guardada separada das stopwords do eixo de assunto de propósito,
para um veto aqui nunca fazer a purga de assunto excluir uma tag que o curador manteve.

### Conflitos — `/entidades/conflitos`

A mesma grafia nos dois eixos: "isto é assunto ou nome próprio?". Três leituras respondem a três
perguntas, e ler só a primeira era o que escondia o trabalho do juiz:

- **Pendentes** — a varredura ao vivo de trigrama (`GET /api/v1/taxonomy/conflicts/cross-domain`),
  anotada com o veredito do juiz onde existe e filtrada por `pair_kind`: "grafias diferentes" (uma
  pergunta de grafia) e "nomes idênticos" (uma pergunta estrutural) não são a mesma lista, e juntas
  nenhuma das duas fica visível. A mesma leitura aceita `entity_type` (`ORG`/`PER`/`LOC`), porque "rua
  é entidade" é uma decisão sobre uma categoria de colisões e não sobre um par.
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

Colapsar os dois deixaria um veto de NER fazer a purga de assunto excluir a tag vencedora.

Resolver é `POST /api/v1/taxonomy/conflicts/resolve` (`CURATE`) e o desfazer é
`DELETE /api/v1/taxonomy/conflicts/resolutions/{resolution_id}` (`CURATE`). O desfazer é exato porque
o ledger grava `created_link_ids` e `ban_created`: as duas escritas usam `ON CONFLICT DO NOTHING`,
então reverter uma resolução posterior não pode levantar um bloqueio que uma anterior plantou, nem
excluir um vínculo que já existia antes. O ledger restaura a linha perdedora a partir do retrato dela.
Um par já resolvido pode ser decidido de novo — a segunda resolução é independente, e cada uma tem o
próprio desfazer.

!!! note "Um par resolvido sai da varredura ao vivo"

    A resolução apaga a linha perdedora, então o join de trigrama não pode devolvê-la e a lista ao
    vivo não tem o que anotar. É por isso que o trabalho sobrevive na fila do juiz e no ledger, e é
    por isso que as abas `Decididos` e `Resoluções` existem.

#### Decidir uma categoria de uma vez

Uma colisão é decidida um par de cada vez, mas a decisão que o arquivista está de fato tomando é
categórica — "rua é entidade" — e um acervo pode ter dezenas da mesma grafia nos dois eixos. O lote,
`POST /api/v1/taxonomy/conflicts/resolve/batch` (`CURATE`), aplica um veredito à **seleção** inteira
que a lista mostra: os mesmos filtros `pair_kind` e `entity_type`, o mesmo `threshold`, e nada além.

A unidade da decisão é a seleção; a unidade da escrita continua sendo o par. Cada par é planejado pelo
mesmo planejador que a prévia de um par usa e escrito dentro do seu próprio savepoint, então um par que
falha não desfaz os outros, e cada par fica com a sua linha no ledger e o seu `resolution_id` — o
desfazer continua sendo por par mesmo quando o clique foi categórico. Um par cujo perdedor um par
anterior do mesmo lote já removeu é relatado em `skipped` **com o motivo**, nunca como falha: é
trabalho terminado, e chamá-lo de falha é o que já transformou um lote limpo numa parede de linhas
vermelhas.

O `limit` limita uma requisição, porque um clique que escreve milhares de linhas no ledger é um clique
que ninguém revisou. O `remaining` é a mesma leitura que a lista faz, feita de novo com os mesmos
filtros, então o número antes do clique e o número depois dele são uma só medição — a tela não pode
afirmar que uma categoria acabou quando a página seguinte discorda.

## Qualidade

| Tela | Decisão | Reversível? |
| --- | --- | --- |
| Trechos — `/qualidade/trechos` | de qual consumidor um trecho repetido sai | aposentar **sim**; remover do catálogo é definitivo |
| Regras — `/qualidade/regras` | se uma regra reescreve o texto ou só sinaliza | sim: aposentar tem caminho de volta, e a regra aposentada continua na tela |
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
- **Aprovar / rejeitar / aposentar / salvar escopo / remover** —
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
Aposentar é a metade segura do par — é o que se procura quando uma regra está errada, então a saída
dela precisa existir.

Uma regra `REWRITE` ativa é a coisa mais barulhenta da tela, e a prévia é o que a torna visível: uma
regra de teste já ficou ativa e carimbou o acervo inteiro sem casar com nada.

Uma regra `LLM_CHECK` também nomeia uma **engine** e um **preset**, e os dois são escolhidos do
registro em vez de digitados de memória: os dois selects são alimentados por
`GET /api/v1/quality/cleaning-rules/engines`, que é o catálogo do próprio eixo de qualidade de título
— os mesmos nomes contra os quais `get_engine` valida, então um modelo que se aposenta deixa de ser
oferecido aqui na mesma mudança que o aposenta. O par é conferido quando a regra é gravada, então uma
regra que não pode rodar não pode ser salva (a recusa é um `422` nomeando as opções), e engine vazia
continua legal: significa o padrão do eixo. Uma regra gravada antes dessa conferência existir degrada
em vez de derrubar a execução — o validador registra o motivo, valida de forma determinística, e a
identidade de produtor dele é a de "sem modelo", então a fila e o contador do painel descrevem a
execução que de fato aconteceu.

### Anomalias — `/qualidade/anomalias`

O que o validador de qualidade marcou, em leitura (`GET /api/v1/documents` filtrado por
`NEEDS_REVIEW`, opcionalmente por motivo de anomalia). As contagens por motivo são a faceta da própria
busca sobre o conjunto filtrado inteiro, e clicar numa delas estreita a lista. Uma fila vazia tem duas
causas muito diferentes e a tela as distingue: o acervo está limpo, ou nenhuma regra que sinaliza
(uma `VALIDATE` ou `LLM_CHECK`) está ativa — uma regra `REWRITE` muda o texto e nunca sinaliza. A
correção é a revisão humana da ficha, na descrição.

## Sistema

A máquina, não o acervo. Tudo aqui pertence a quem opera a instalação, e as três telas são
alcançadas por `/configuracoes`, sob *Operação*: o menu ficou com o que o arquivista consulta
catalogando, e não é isto. As duas formas de entrada do acervo moram no Acervo (`/acervo/nova`), e a
página de origens é do operador; as rotas de leitura continuam autenticadas, então um curador que
segue uma URL direta ainda a vê só para leitura.

| Tela | Decisão | Reversível? |
| --- | --- | --- |
| Origens — `/sistema/ingestao` | qual origem adicionar, as URLs e a agenda, se ela está ativa e se enfileira uma execução (operador) | a configuração, a agenda e a pausa são reversíveis; a tela não escreve descrição |
| Workers e execuções — `/sistema/workers` | se roda um worker agora (**Painel**); se para uma execução ativa (**Execuções**) | sim para a configuração da própria execução; os efeitos de uma execução seguem o que ela escreveu. Sem desfazer para uma execução cancelada: ela continua cancelada, e uma nova execução é uma nova linha no ledger |
| Saúde do sistema — `/sistema/diagnostico` | nenhuma (banco, modelos, storage, processo) | sim (só leitura) |

### Origens — `/sistema/ingestao`

A etapa à frente do Acervo, origem por origem (ADR 0016). **Origens** lista as fontes configuradas:
cada cartão tem a fila que a próxima execução leria, os números de processados e falhas, a última
execução e a ativa, a agenda e a configuração efetiva. O **operador** adiciona uma definição pelo
seletor, edita a configuração do adaptador (URLs de listagem e detalhe da coleta de referência, a
espera de cortesia), salva um cron de cinco campos num fuso IANA, **Desativa/Ativa** e **Enfileira
execução**. Pausar mantém a linha, a agenda e as execuções; só a execução é recusada. Uma instalação
nova começa sem fonte configurada e mostra **Nenhuma origem configurada**; o fluxo de adicionar
ativa a definição escolhida. A execução é o mesmo ledger dos workers de IA; um período que dispara
com a origem já rodando é pulado, não enfileirado.

**Entradas** mostra as linhas manual e CSV só para leitura, com o status e um link para o Acervo:
elas são as formas de entrada, não fontes, e as duas escritas que ficavam aqui estão em *Nova
descrição* (#205). O cartão é `OPERATE`; as rotas de leitura continuam autenticadas, então um
curador que segue uma URL direta vê a página só para leitura, com os controles escondidos. As rotas
genéricas de worker recusam `ingestion` — uma execução dela precisa da origem, e as rotas da origem
são o seletor.

### Workers e execuções — `/sistema/workers`

Uma tela com duas abas na URL (#207), e ela responde ao ciclo de conferir a execução que antes
precisava de duas telas: a aba **Painel** enfileira e mostra a fila, e a aba **Execuções** é o ledger
do que rodou. A última execução de um worker é um link para o ledger filtrado por esse worker, com a
linha exata realçada; o caminho antigo `/sistema/execucoes` redireciona para lá com os filtros
preservados. Só a aba ativa é montada, então só a leitura dela é consultada em ciclo.

O catálogo dos dez workers, na ordem do pipeline, com a engine, o preset e a configuração efetiva na
linha recolhida — "com qual modelo isto está rodando?" é a pergunta que a tela existe para responder,
e aqui a resposta é **só leitura**. O que a instalação está *configurada* a fazer é uma tela própria
(*Configuração dos Workers*, abaixo), porque são perguntas diferentes: esta é o que a máquina está
fazendo. A linha carrega a fila — pendentes, processados, falhas, última execução — e a única escrita
é `OPERATE`. Expandida, ela abre quatro fatos: a configuração efetiva, a **fila**, o **livro** do
worker (`Carimbos (descrições)` quando o livro é um carimbo, `Processados` caso contrário) e a última
execução. A fila e o livro ficam separados de propósito, e `guides/operate.pt.md` é quem diz o que
cada um dos dois conta:

- **Rodar agora** — `POST /api/v1/system/workers/{worker_name}/runs`. A execução usa a configuração
  efetiva, ajustada só para esta vez; nada ajustado aqui vira padrão. Toda execução deixa uma linha no
  ledger de execuções, e um worker com execução em andamento desabilita o botão — a garantia é o
  índice único parcial no banco, e a tela só evita oferecer o que o banco recusaria.

A linha `ingestion` é a exceção ao botão de execução: a execução dela pertence a uma origem, então a linha leva a `/sistema/ingestao` (a tela da origem) e a rota genérica a recusa.

Os campos do painel de execução vêm do contrato, não de uma caixa de texto: `declared_options` nomeia
as opções que o worker aceita e, para uma lista de colunas, as colunas que o texto da IA tem
(`original_title`, `final_title`, `scope_content`, `admin_bio_history`, `provenance`), então a tela
renderiza um checkbox, um número ou as próprias colunas. O único bloco livre é *Repasses ao engine
(avançado)*: um repasse cru ao construtor da engine, por execução e nunca persistido, com as chaves que
o eixo já repassa (`model`, `device`, `host`, ...) como dica. É a exceção nomeada da #120 — existe para
quem conhece a biblioteca, e a engine valida o valor.

O painel em si não oferece desfazer para uma execução. A reversibilidade de uma execução é a
reversibilidade do que ela escreveu — um desfazer de merge, de materialização, de conflito — e um
worker que carimba a própria fila não refaz o trabalho só porque foi rodado de novo. O painel marca
**quatro** workers como fora do bloqueio de revisão humana — a transferência staging → archive, o
juiz de conflito assunto x entidade, a categorização de assunto (tags) e o `worker_embedding` — e só
o `worker_embedding` reescreve uma *descrição*: ele re-gera o vetor de um texto mudado mesmo numa
descrição aprovada, a exceção documentada. Os outros três trabalham sobre unidades que não são
descrições (um registro de staging, um par, uma tag).

### Execuções — a aba do ledger

Desde a #207 o ledger é a aba **Execuções** de `/sistema/workers`, e `/sistema/execucoes` redireciona
para ela com a busca preservada. É leitura exceto pela parada: uma linha por execução, da linha de
comando e do painel, com a configuração **já resolvida** que a execução usou (então ele continua
legível depois que
um preset muda no código), as **opções efetivas do worker** (as colunas que ele leu, o limiar, o teto —
resolvidas quando a execução começou, então "quais colunas a execução #N leu?" tem resposta), a
duração, o desfecho e quem pediu. Uma linha anterior à coluna de opções diz "opções não registradas
nesta execução". Acima dele, as falhas dos últimos 30 dias
agrupadas por causa (`GET /api/v1/system/failures`), que respondem à pergunta que o ledger não
responde: quarenta linhas dizendo a mesma frase são uma causa. Clicar num grupo filtra o ledger
abaixo em vez de abrir uma segunda lista, e a referência de uma falha é o que se procura no log.

A única escrita é **Cancelar execução…** numa linha ativa (`POST /api/v1/system/runs/{run_id}/cancel`,
`OPERATE`). Uma execução na fila que nenhum runner reivindicou é cancelada na hora; uma em andamento só
recebe o pedido, e a linha continua dizendo "em execução" com uma nota até o worker chegar ao limite do
lote — o lote em curso é comitado, não interrompido, porque uma passada do modelo não pode ser cortada
no meio. Um segundo clique é o mesmo pedido, e uma execução que já terminou responde `409`.

### Saúde do sistema — `/sistema/diagnostico`

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
| Canais de difusão — `/configuracoes/difusao` | qual canal adicionar, a configuração, o ciclo de vida e (num export) a agenda | sim (a configuração, a agenda e a pausa; nada é excluído) |
| Configuração dos Workers — `/configuracoes/workers` | o padrão persistido de cada worker, e o histórico dele | sim (remover a linha) |
| Usuários — `/configuracoes/usuarios` | quem existe, o que pode fazer e onde está conectado | sim (desativar e reativar) |

### Configurações — `/configuracoes`

Uma página de cartões, e cada cartão abre uma tela que já existia com a rota que sempre teve: o que
mudou foi como se chega até ela. Três abas, na ordem da escada de permissões que elas percorrem:

| Aba | Cartões |
| --- | --- |
| Arranjo e catálogos | Plano de arranjo (`CURATE`), Níveis de descrição, Tipologias e Vocabulário do acervo (`CATALOGUE`) |
| Operação | Workers e execuções, Origens, Canais de difusão, Configuração dos Workers e Saúde do sistema (`OPERATE`) |
| Acesso | Usuários (`ADMIN`) |

A aba fica na URL (`?aba=`), então dá para mandar alguém direto aos "cartões dos workers". Uma aba que
a conta não pode preencher não é renderizada, e um `?aba=` que a nomeie cai na primeira aba que a
conta *pode* preencher: um link válido para quem mandou ainda aterrissa em algo honesto para quem lê.
Cada cartão carrega a área em que a sua tela escreve, e a entrada que abre esta página segue as mesmas
áreas — a regra está em *O menu esconde; nunca concede*, acima.

### Canais de difusão — `/configuracoes/difusao`

A página do operador para onde o acervo publicado sai (issue #213, ADR 0023), a gêmea deliberada de
Origens: uma tela diz por onde os dados entram, esta diz por onde o registro sai. Ela lê todas as
definições que o pacote traz em uma requisição, então uma definição sem linha é o que o seletor de
adição oferece e uma definição com linha é um cartão. Uma instalação nova não tem linha nenhuma: o
estado vazio é real, não decorativo.

Cada cartão traz o nome do canal, a capacidade — `LIVE` (lido a cada requisição) ou `EXPORT` (produzido
por uma execução) —, o ciclo de vida e o resumo da configuração, renderizado dos mesmos `config_fields`
que o formulário renderiza. As ações são **Editar configuração**, **Agenda** (só `EXPORT`),
**Enfileirar execução** (só `EXPORT`, desabilitado enquanto o canal tem execução em andamento),
**Desativar/Ativar** e, para o site público, **Ver site** — visível só com o canal ativo e um endereço
público configurado, porque o link é o endereço que o operador digitou, não uma afirmação de que há um
site no ar. Pausar é o ciclo de vida: a linha, a configuração e a agenda ficam, e o canal simplesmente
deixa de ser oferecido a quem lê.

Um cartão `EXPORT` mostra também a agenda e a **última execução**, com o status e o link para o ledger
filtrado por aquele canal. A execução é o worker `diffusion` do ledger compartilhado, com o canal como
eixo (issue #212, ADR 0023 §7): uma segunda execução do mesmo canal responde 409, dois canais exportam
ao mesmo tempo, e um canal que o pacote traz sem adaptador responde 422 e não enfileira nada.

Adicionar é um gesto só, num painel lateral: escolher uma definição que o pacote traz, preencher a
configuração e salvar. O salvamento é um único `PATCH` que cria a linha e a ativa, porque um canal que o
pacote não consegue validar não é linha — o título do site público é obrigatório. **Desativar** é a
pausa (`PATCH {"enabled": false}`); nada é excluído. A configuração é validada pelo modelo do próprio
canal a cada leitura e a cada escrita, então um erro de digitação é um 422 com uma frase, e a página
renderiza **um formulário genérico** sobre os campos do canal, e não um componente por canal. O cartão do
site público diz a consequência que o dono pergunta: o aplicativo público é uma superfície separada, e
habilitar o canal não o instala. O seletor também oferece o conjunto de dados aberto (`dataset`), o
primeiro `EXPORT` que o pacote traz: o cartão configura o destino, os formatos e a licença dos dados, e a
execução escreve o pacote que a [Operação](operate.md) descreve.

### Configuração dos Workers — `/configuracoes/workers`

O que a instalação está *configurada* a fazer, separado do que a máquina está fazendo (issue #53). Um
cartão por worker, na ordem do pipeline, cada um com a linha persistida de `archive_worker_settings` e
suas revisões — as duas escritas são `OPERATE`:

- **Salvar padrão** — `PUT /api/v1/system/workers/{worker_name}/settings` grava o padrão. É parcial de
  propósito: um campo vazio continua seguindo o código, e a precedência não muda —
  `argumento explícito > a linha de archive_worker_settings > o default da assinatura`. O formulário
  renderiza um controle por opção declarada (uma lista de colunas como as colunas que o texto da IA
  tem); `limit` não aparece, porque um teto pertence a uma execução, e `config` continua recusado como
  opção, porque é um dataclass do runner e não um valor JSON. `engine_name`, `preset` e
  `db_batch_size` têm campo próprio e são recusados dentro das opções, que seriam uma segunda
  definição do mesmo campo.
- **Conferir impacto** — `POST /api/v1/system/workers/{worker_name}/queue/preview` responde quantas
  unidades a configuração que o formulário mostra deixaria na fila, e não escreve nada. Existe porque a
  fila é chaveada pela identidade do produtor: salvar outra engine, outro preset ou outro limiar relê
  as unidades afetadas sozinho, e esse custo precisa ser legível antes de ser pago. O número some assim
  que um campo muda, então ele nunca descreve uma configuração que o formulário não mostra mais.
- **Voltar ao padrão do código** — `DELETE /api/v1/system/workers/{worker_name}/settings` remove a
  linha. Toda escrita deixa uma revisão
  (`GET /api/v1/system/workers/{worker_name}/settings/revisions`), listada no cartão, então o padrão é
  reversível e quem o alterou fica nomeado.

Um worker cuja engine vive na regra `LLM_CHECK` ativa (`quality-validator`) não oferece a escolha de
engine/preset aqui: um segundo lugar para escolher a mesma engine seria uma segunda fonte de verdade,
então o cartão diz onde ela vive e oferece só os parâmetros de execução. A tela lê
`GET /api/v1/system/workers/settings`, que não é o `GET /api/v1/system/workers` do painel — o painel
conta nove filas, e esta tela não mostra nenhuma delas.

Uma linha gravada antes da validação de opções não é um erro novo: a leitura ignora a opção que não
consegue mais honrar e explica isso na nota do cartão ("Padrão salvo ignorado — …"), então a tela
responde com o default do código em vez de derrubar o contador da fila. Salvar o formulário de novo
escreve só os campos que ele mostra, o que cura a linha.

### Usuários — `/configuracoes/usuarios`

As contas da instalação, a superfície `ADMIN`. As escritas são `POST /api/v1/users` (criar),
`PATCH /api/v1/users/{user_id}` (nome, papel, ativa), `POST /api/v1/users/{user_id}/password`
(redefinir) e as rotas de sessão `GET`/`DELETE /api/v1/users/{user_id}/sessions[/{session_id}]` —
todas `ADMIN`. Cinco fatos que a API impõe e a tela declara:

- **a senha criada aqui é temporária.** O administrador a digitou, então a conta a troca no primeiro
  acesso, exatamente como no bootstrap do CLI;
- **desativar encerra todas as sessões da conta na hora**, que é o que torna o sinalizador real;
- **redefinir a senha encerra todas as sessões** e destrava um bloqueio por tentativas falhas. A ação
  fica na própria linha da conta (**redefinir senha**), sem precisar expandir a ficha, e a confirmação
  nomeia as duas consequências;
- **redefinir a própria conta desconecta você.** A redefinição administrativa não tem o "mantenha esta
  sessão" do **Trocar senha**, então o administrador que aponta para a própria linha encerra a sessão
  em que está; a tela avisa antes do clique e aponta o **Trocar senha** no rodapé da sessão, que a
  mantém;
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
