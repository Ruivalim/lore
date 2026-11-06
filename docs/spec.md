# lore: especificação

O produto descrito antes da implementação. Decisões de stack e desvios em `docs/plan.md`; uso e instalação no `README.md`.

## 1. Visão

`lore` será uma base pessoal de conhecimento formada por arquivos Markdown independentes. A pessoa poderá fazer uma pergunta pelo terminal, receber uma resposta sustentada pelos documentos locais e ver exatamente quais arquivos foram usados.

Quando a base não tiver material suficiente, `lore` poderá consultar um modelo externo mais forte, pesquisar fontes na internet e produzir duas saídas:

1. uma resposta imediata, marcada como não verificada;
2. um novo documento Markdown em estado de rascunho.

O rascunho só entrará na base confiável depois de revisão e aprovação humana.

O objetivo não é acumular conversas. O objetivo é transformar perguntas recorrentes em conhecimento durável, legível, versionável e reutilizável.

## 2. Relação com memória de agentes

`lore` e a memória que agentes de IA mantêm entre sessões (por exemplo, o Remnic) têm papéis separados.

### Memória de agentes

Memória operacional compartilhada entre agentes:

- decisões tomadas;
- preferências de trabalho;
- contexto entre sessões;
- restrições de ambiente;
- fatos úteis aos agentes;
- pendências.

### lore

Biblioteca pessoal curada:

- procedimentos;
- conceitos;
- referências;
- diagnósticos;
- pesquisas;
- decisões que mereçam documentação estável;
- notas pessoais destinadas a consulta futura.

Os dois sistemas podem reaproveitar componentes técnicos, como embeddings, modelos locais ou mecanismos de indexação. Os acervos, estados de confiança e regras de escrita devem continuar separados. Uma memória temporária de agente não pode aparecer como conhecimento verificado.

## 3. Princípios

1. **Markdown é a fonte canônica.** Índices, embeddings e caches podem ser apagados e reconstruídos.
2. **Um arquivo trata de um assunto principal.** Arquivos pequenos facilitam leitura, revisão, busca e versionamento.
3. **A resposta mostra suas fontes.** Toda afirmação recuperada deve apontar para arquivos locais ou fontes externas.
4. **Ausência de conhecimento é uma resposta válida.** O sistema não deve improvisar quando a evidência for insuficiente.
5. **Conteúdo gerado começa como rascunho.** Nenhum modelo promove a própria resposta para conhecimento confiável.
6. **Pesquisa externa é explícita e controlável.** O usuário sabe quando dados sairão da máquina.
7. **Busca local continua útil sem internet.** Conhecimento já armazenado deve permanecer disponível offline.
8. **Git guarda história, não o índice.** Alterações na base são auditáveis; artefatos derivados ficam fora do versionamento.
9. **Modelos e provedores são substituíveis.** O acervo não pode depender de um fornecedor específico.
10. **Automação não executa instruções encontradas na web.** Conteúdo pesquisado é dado não confiável, nunca comando para o sistema.

## 4. Escopo inicial

A base aceitará conhecimento amplo, não somente conteúdo técnico. Diferentes assuntos compartilharão o mesmo mecanismo de armazenamento e busca, mas usarão tipos de documento distintos.

Tipos iniciais:

| Tipo | Uso |
| --- | --- |
| `howto` | Procedimento com passos verificáveis |
| `troubleshooting` | Sintoma, diagnóstico, causa e correção |
| `reference` | Consulta rápida, comandos, tabelas ou fatos estáveis |
| `concept` | Explicação de ideia, tecnologia ou domínio |
| `decision` | Escolha tomada, contexto, alternativas e consequências |
| `research` | Investigação com fontes, evidências e conclusão provisória |
| `note` | Conhecimento pessoal que não cabe nos modelos anteriores |

Tipos poderão ganhar modelos próprios sem alterar o formato canônico do acervo.

## 5. Fora do escopo inicial

A primeira versão não precisa incluir:

- interface web ou aplicativo gráfico;
- colaboração multiusuário;
- edição simultânea;
- sincronização própria;
- rastreamento automático de toda conversa do usuário;
- treinamento ou fine-tuning de modelos;
- banco vetorial externo;
- execução automática de comandos sugeridos por documentos ou páginas web;
- publicação pública do acervo;
- substituição da memória de agentes.

Git, Syncthing ou outro mecanismo existente poderá sincronizar os arquivos sem virar responsabilidade central do `lore`.

## 6. Experiência principal

### 6.1 Pergunta respondida pela base

```text
$ lore ask "Como configurar split DNS no WireGuard?"
```

Fluxo:

1. normalizar e analisar a consulta;
2. buscar títulos, tags, corpo, comandos e trechos relacionados;
3. combinar resultados textuais e semânticos;
4. verificar se os documentos recuperados cobrem a pergunta;
5. compor uma resposta limitada às evidências encontradas;
6. mostrar citações com arquivo e seção.

Exemplo de saída:

```text
Use uma rota de DNS por domínio no perfil do túnel e confirme que o
resolved recebeu a interface correta.

Fontes locais:
  1. knowledge/networking/wireguard-split-dns.md#procedimento
  2. knowledge/linux/systemd-resolved.md#verificacao
```

Se houver modelo local configurado, ele poderá sintetizar a resposta. Sem modelo local, o sistema deverá continuar útil em modo extrativo, mostrando os melhores trechos com contexto.

### 6.2 Resposta parcial

Quando os documentos cobrirem apenas parte da pergunta:

```text
Encontrei material sobre WireGuard e systemd-resolved, mas nada sobre
NetworkManager.

Pesquisar a lacuna externamente e criar um rascunho? [S/n]
```

O sistema deve identificar e comunicar a lacuna. Não deve apresentar uma resposta parcial como completa.

### 6.3 Resposta ausente

Quando não houver evidência local suficiente:

```text
A base não contém uma resposta confiável.
Pesquisar externamente e criar um rascunho? [S/n] (5s)
```

Após confirmação, ou se a contagem acabar sem interação:

1. pesquisar fontes externas;
2. priorizar documentação oficial e fontes primárias;
3. enviar ao modelo somente a consulta e o contexto necessário;
4. produzir resposta com citações;
5. salvar documento em `drafts/`;
6. informar que resposta e documento ainda não foram verificados.

Exemplo:

```text
Resposta externa, ainda não verificada.
Rascunho salvo em:
  drafts/networking/wireguard-split-dns-networkmanager.md
```

### 6.4 Revisão

```text
$ lore review
```

A revisão deverá mostrar:

- conteúdo proposto;
- fontes usadas;
- data da pesquisa;
- alegações sem fonte;
- possíveis conflitos com documentos existentes;
- diferença em relação a uma versão anterior, quando houver.

Ações possíveis:

- aprovar;
- editar;
- rejeitar;
- pedir nova pesquisa;
- manter como rascunho;
- arquivar.

A aprovação move o documento para `knowledge/`, atualiza seus metadados e reindexa a base. Commit Git continua explícito, salvo se o usuário habilitar uma política automática no futuro.

### 6.5 Reutilização

Uma pergunta equivalente feita depois da aprovação deverá ser respondida pela base local. Pesquisa externa não deve ocorrer quando o acervo já tiver cobertura confiável e atual.

## 7. Estados do conhecimento

| Estado | Significado | Pode responder como confiável? |
| --- | --- | --- |
| `draft` | Gerado ou escrito, ainda não revisado | Não |
| `verified` | Revisado e aprovado por humano | Sim |
| `stale` | Já foi verificado, mas pode estar desatualizado | Somente com aviso |
| `archived` | Mantido por histórico, não deve orientar respostas atuais | Não |

Transições permitidas:

```text
draft -> verified
draft -> archived
verified -> stale
stale -> verified
stale -> archived
verified -> archived
```

Por padrão nenhuma transição para `verified` ocorre por decisão de um modelo. O dono do acervo pode ligar aprovação automática por origem em `[review]` (`auto-if-clean` ou `auto`); o que entra assim fica marcado `reviewed_by: auto` e segue na fila de revisão até um humano confirmar.

## 8. Formato dos documentos

Cada documento terá front matter YAML e corpo Markdown.

Exemplo:

```markdown
---
id: wireguard-split-dns-networkmanager
title: Split DNS com WireGuard e NetworkManager
type: howto
status: draft
tags:
  - linux
  - networking
  - wireguard
  - dns
created_at: 2026-09-21
updated_at: 2026-09-21
verified_at: null
review_after: 2027-03-21
sources:
  - url: https://example.org/official-documentation
    title: Official documentation
    accessed_at: 2026-09-21
---

# Split DNS com WireGuard e NetworkManager

## Quando usar

## Resposta curta

## Pré-requisitos

## Procedimento

## Como verificar

## Problemas comuns

## Limitações

## Fontes
```

### 8.1 Campos obrigatórios

- `id`: identificador estável e único;
- `title`: título humano;
- `type`: tipo do documento;
- `status`: estado de confiança;
- `tags`: termos auxiliares de descoberta;
- `created_at`: data de criação;
- `updated_at`: data da última alteração relevante;
- `sources`: lista de origens, vazia somente quando o conteúdo for experiência ou nota pessoal.

### 8.2 Campos condicionais

- `verified_at`: obrigatório para estado `verified`;
- `review_after`: recomendado para conteúdo sujeito a mudança;
- `supersedes`: documento anterior substituído;
- `related`: identificadores de documentos relacionados;
- `scope`: limites explícitos da resposta;
- `applies_to`: versões, plataformas ou contextos aos quais o conteúdo se aplica.

### 8.3 Fontes pessoais

Conhecimento vindo de experiência pessoal poderá usar origem não externa:

```yaml
sources:
  - kind: personal
    description: Verificado no homelab em 2026-09-21
```

O sistema não deve inventar URL para preencher metadados. `lore import` registra arquivo de origem local sem tratá-lo como fonte web:

```yaml
sources:
  - kind: local
    path: guia.md
    description: Markdown importado, conteúdo preservado.
```

## 9. Organização do acervo

O acervo mora num repositório próprio, separado do código do Lore. `lore init <caminho>` cria:

```text
acervo/
├── knowledge/      # verified e stale
├── drafts/         # rascunhos aguardando revisão
├── archive/        # rejeitados e arquivados
├── .gitignore      # ignora .lore/
└── .lore/
    ├── config.toml # opções deste acervo
    └── index.sqlite
```

Documentos e `.gitignore` entram no Git. Banco de índice, embeddings, lock e a config local ficam fora. Subpastas em `knowledge/` servem à navegação humana; a busca não depende delas, porque tags e conteúdo cruzam domínios.

## 10. Arquitetura conceitual

### 10.1 Camadas

```text
CLI
  -> serviço de aplicação
      -> repositório Markdown
      -> indexador local
      -> recuperador híbrido
      -> avaliador de cobertura
      -> compositor de resposta
      -> pesquisador externo
      -> gerenciador de revisão
```

### 10.2 Repositório Markdown

Responsável por:

- ler e validar front matter;
- criar rascunhos;
- mover documentos entre estados;
- detectar identificadores duplicados;
- preservar arquivos como fonte canônica;
- oferecer operações sem depender do índice.

### 10.3 Indexador local

Responsável por transformar documentos em unidades pesquisáveis:

- título;
- resumo;
- tags;
- cabeçalhos;
- seções;
- blocos de código;
- metadados de escopo e versão.

Cada trecho indexado deve manter referência ao arquivo, cabeçalho e posição de origem.

O índice será descartável e reconstruível. SQLite com FTS5 é a opção inicial recomendada para busca textual. Embeddings poderão ficar no mesmo índice local ou em armazenamento igualmente descartável, sem introduzir serviço externo na primeira versão.

### 10.4 Recuperação híbrida

A busca deverá combinar:

1. correspondência textual com BM25 ou equivalente;
2. correspondência semântica por embeddings;
3. reforço para título, tags, comandos e termos exatos;
4. filtros por estado, tipo, data, domínio e versão;
5. fusão e reordenação dos resultados.

Busca textual vem primeiro por ser rápida, explicável e boa para nomes, comandos e mensagens de erro. Busca semântica complementa perguntas com vocabulário diferente do documento.

A estratégia de combinação e os limites de cobertura devem ser calibrados com consultas reais. Números arbitrários de similaridade não devem ser tratados como confiança factual.

### 10.5 Avaliador de cobertura

Antes de responder, o sistema deverá classificar a recuperação como:

- suficiente;
- parcial;
- insuficiente;
- conflitante;
- desatualizada.

A classificação usará sinais como:

- presença de trechos diretamente relacionados à pergunta;
- cobertura dos componentes pedidos;
- estado dos documentos;
- escopo e versões aplicáveis;
- concordância ou conflito entre fontes;
- qualidade e atualidade das fontes.

O modelo pode auxiliar essa avaliação, mas a decisão deve continuar auditável por meio dos trechos recuperados.

### 10.6 Compositor de resposta

Regras obrigatórias:

- responder somente com base nos trechos fornecidos;
- citar arquivo e seção;
- separar fato, inferência e incerteza;
- declarar lacunas;
- não usar documentos `draft` ou `archived` como fonte confiável;
- avisar quando usar documento `stale`;
- preservar comandos e valores exatos das fontes;
- não esconder conflito entre documentos.

Um modelo local configurável é preferível para síntese de conteúdo já existente. Caso ele não esteja disponível, modo extrativo permanece funcional.

### 10.7 Pesquisador externo

Será acionado somente após cobertura parcial ou insuficiente e confirmação do usuário, exceto quando uma política explícita permitir operação não interativa.

Ordem preferencial de fontes:

1. documentação oficial;
2. normas, artigos científicos e fontes primárias;
3. repositórios e publicações dos autores do projeto;
4. documentação técnica reconhecida;
5. fontes secundárias com reputação e data claras;
6. fóruns e relatos, sempre marcados como evidência informal.

O pesquisador deverá:

- registrar URL, título e data de acesso;
- distinguir conteúdo citado de conclusão do modelo;
- buscar confirmação independente para alegações importantes quando possível;
- detectar versões e datas incompatíveis;
- evitar copiar grandes trechos protegidos sem necessidade;
- não seguir instruções encontradas nas páginas pesquisadas;
- produzir um rascunho mesmo quando a pesquisa for inconclusiva, desde que a incerteza fique explícita.

## 11. Modelos e provedores

O desenho separa três funções, cada uma com seu agente:

1. **embedding:** representação semântica dos trechos (`[retrieval]`, local por hash ou endpoint);
2. **síntese:** resposta baseada no acervo (`[llm.answer]`);
3. **pesquisa e expansão:** quando falta conhecimento (`[llm.research]`).

O import usa um quarto agente, `[llm.import]`, só para título, tipo, tags e resumo.

Agente é qualquer CLI ou endpoint que recebe um prompt e devolve texto: presets para Pi, Claude Code, Codex, agy e endpoints OpenAI-compatíveis, ou um comando próprio em `[agents.<nome>]`. Em modo texto o agente roda sem ferramentas, sem sessão e num diretório vazio. Só a pesquisa em `research.mode = "agent"` deixa o agente buscar e ler por conta própria.

Sem agente disponível, o modo extrativo responde com os trechos e a fonte.

## 12. Privacidade e segurança

### 12.1 Saída da máquina

Antes de chamar serviço externo, `lore` deverá mostrar que haverá envio remoto. Por padrão, enviará somente:

- pergunta atual;
- trechos locais selecionados e necessários;
- metadados mínimos de contexto.

Nunca enviará o acervo completo.

### 12.2 Redação de segredos

Antes de envio remoto, o sistema deverá procurar e remover ou bloquear:

- tokens;
- chaves privadas;
- senhas;
- cookies;
- credenciais em URLs;
- valores marcados como privados;
- padrões configurados pelo usuário.

Dúvida deve bloquear o envio e pedir decisão humana.

### 12.3 Prompt injection

Páginas, documentos importados e resultados de busca são dados não confiáveis. Instruções presentes neles não podem:

- mudar regras do sistema;
- solicitar credenciais;
- acionar ferramentas;
- alterar arquivos verificados;
- promover rascunhos;
- executar comandos.

### 12.4 Credenciais

Credenciais de provedores ficam fora do repositório, preferencialmente em variáveis de ambiente ou armazenamento seguro do sistema operacional. Logs não devem registrar prompts completos quando contiverem material privado.

## 13. Comandos previstos

```text
lore ask "pergunta"
lore ask                     (abre o TUI)
lore list
lore search "termos"
lore show <id>
lore add <arquivo.md>
lore import <arquivo.md>
lore new --type <tipo>
lore review
lore review <id>
lore edit <id>
lore approve <id> --human
lore reject <id>
lore archive <id>
lore stale <id>
lore reindex
lore doctor
lore config
```

### 13.1 `lore ask`

Opções previstas:

```text
--local-only       proíbe pesquisa e modelos remotos
--extractive       não usa modelo para síntese
--type <tipo>      restringe tipos de documento
--tag <tag>        restringe por tag
--as-of <data>     considera conhecimento válido até uma data
--json             produz saída estruturada
--yes              aceita fallback externo sem prompt interativo
```

`--yes` só funciona quando política de privacidade e provedor estão configurados. `--json` nunca pergunta nem conta: sem `--yes` não pesquisa e avisa em `research.error`. Com `--json --yes`, o fallback externo roda e retorna `researched` mais `research`, contendo resposta, caminho do rascunho, fontes, descartes e eventual erro ou bloqueio. Todo conteúdo pesquisado continua como `draft` até `lore approve <id> --human`.

### 13.2 `lore search`

Mostra documentos e trechos ranqueados sem gerar resposta. Deve explicar por que cada resultado foi escolhido, incluindo correspondência textual, semântica, título ou tag.

### 13.3 `lore doctor`

Verifica:

- configuração;
- documentos inválidos;
- identificadores duplicados;
- links internos quebrados;
- fontes ausentes;
- documentos vencidos;
- índice fora de sincronia;
- disponibilidade dos modelos;
- acesso aos provedores sem expor credenciais.

## 14. Configuração

Todas as opções, com o valor padrão e o que fazem, estão em `src/lore/config.example.toml`. Esse arquivo é a fonte dos defaults e o template de `lore init`; chave fora dele é ignorada e o `lore doctor` avisa.

## 15. Erros e degradação controlada

| Situação | Comportamento esperado |
| --- | --- |
| Sem internet | Responder com base local ou informar falta de cobertura |
| Modelo local indisponível | Usar resposta extrativa |
| Provedor remoto indisponível | Preservar pergunta e permitir repetir pesquisa depois |
| Documento inválido | Excluir do índice, explicar erro e manter arquivo intacto |
| Índice corrompido | Reconstruir a partir dos Markdown |
| Fontes conflitantes | Mostrar conflito e evitar conclusão falsa |
| Documento desatualizado | Avisar e oferecer nova pesquisa |
| Possível segredo no contexto | Bloquear envio remoto |
| Pesquisa sem boa fonte | Criar rascunho inconclusivo ou não criar, sempre explicar |
| Interrupção durante escrita | Usar gravação atômica e não deixar documento parcial |

## 16. Atualidade e manutenção

Documentos sujeitos a mudança poderão definir `review_after`. O sistema deverá listar conteúdo vencido:

```text
$ lore doctor
3 documentos precisam de revisão.
```

Revisão poderá:

- confirmar conteúdo sem alteração;
- atualizar fontes e instruções;
- marcar como `stale`;
- arquivar;
- substituir por novo documento usando `supersedes`.

O sistema não deve reescrever documentos verificados automaticamente. Pode sugerir alterações em novo rascunho.

## 17. Git e auditabilidade

Git registra:

- criação de conhecimento;
- promoção de rascunhos;
- correções;
- mudança de estado;
- substituição e arquivamento.

Operações do CLI modificam a árvore de trabalho, mas commit e push permanecem explícitos por padrão.

Mensagens sugeridas:

```text
docs(networking): add verified WireGuard split DNS guide
docs(health): refresh sources for sleep research
docs(finance): archive outdated tax reference
```

O sistema nunca fará push sem autorização explícita.

## 18. Estratégia de testes

### 18.1 Unidade

- parsing e validação do front matter;
- transições de estado;
- divisão de documentos em seções;
- ranking textual;
- fusão textual e semântica;
- filtros;
- citações;
- redação de segredos;
- escrita atômica;
- reconstrução do índice.

### 18.2 Integração

- importar documento, indexar e encontrar;
- responder pergunta conhecida com citação correta;
- detectar pergunta parcialmente coberta;
- acionar pesquisa externa somente após autorização;
- criar rascunho válido;
- aprovar rascunho e responder localmente na consulta seguinte;
- operar sem internet;
- recuperar de índice apagado ou corrompido.

### 18.3 Segurança

- prompt injection em página pesquisada;
- segredo em pergunta ou documento local;
- fonte maliciosa tentando alterar política;
- caminhos fora do repositório;
- links simbólicos inesperados;
- Markdown e YAML malformados;
- conteúdo remoto excessivamente grande.

### 18.4 Avaliação de recuperação

Será criado um conjunto de perguntas reais com documentos esperados. Métricas mínimas:

- documento correto entre os primeiros resultados;
- seção correta recuperada;
- taxa de perguntas desconhecidas corretamente recusadas;
- taxa de citações que sustentam a resposta;
- latência local;
- necessidade real de fallback externo.

### 18.5 Avaliação de respostas

Cada resposta será avaliada por:

- fidelidade às fontes;
- cobertura da pergunta;
- precisão das citações;
- clareza sobre incerteza;
- ausência de alegações não sustentadas;
- preservação exata de comandos e valores.

Avaliação humana será autoridade final. Julgamento por outro modelo pode ajudar na triagem, mas não substitui testes determinísticos e revisão.

## 19. Fases de implementação

### Fase 1: núcleo documental

- definir esquema de front matter;
- validar e carregar Markdown;
- criar comandos `new`, `add`, `show` e `doctor`;
- implementar estados e transições;
- preparar modelos por tipo de documento;
- configurar `.gitignore` para artefatos locais.

### Fase 2: busca local

- criar índice textual local;
- dividir documentos por seções;
- implementar `search`;
- reconstruir índice de forma determinística;
- criar conjunto inicial de consultas de avaliação.

### Fase 3: consulta fundamentada

- implementar `ask` em modo extrativo;
- integrar síntese local configurável;
- exigir citações;
- classificar cobertura como suficiente, parcial ou insuficiente;
- testar comportamento offline.

### Fase 4: pesquisa externa e rascunhos

- integrar modelo remoto forte;
- integrar busca web;
- aplicar política de fontes;
- adicionar proteção contra segredos e prompt injection;
- gerar rascunhos válidos;
- mostrar resposta externa como não verificada.

### Fase 5: revisão e promoção

- implementar fila de revisão;
- mostrar fontes, conflitos e diferenças;
- aprovar, rejeitar, arquivar e pedir nova pesquisa;
- reindexar após promoção;
- verificar ciclo completo de aprendizado.

### Fase 6: busca semântica e calibração

- integrar embeddings locais;
- combinar ranking textual e semântico;
- calibrar cobertura com perguntas reais;
- medir ganho sobre busca textual;
- manter opção de desativar embeddings.

Busca semântica entra depois da busca textual para que sua utilidade seja medida, não presumida.

## 20. Critérios de aceite da primeira versão útil

A primeira versão será considerada útil quando conseguir demonstrar este ciclo completo:

1. usuário adiciona documentos Markdown;
2. `lore` valida e indexa os documentos;
3. pergunta conhecida recebe resposta local com citações corretas;
4. pergunta desconhecida é recusada sem invenção;
5. usuário autoriza pesquisa externa;
6. pesquisa produz resposta marcada e rascunho com fontes;
7. usuário revisa e aprova o rascunho;
8. consulta equivalente passa a ser respondida localmente;
9. apagar o índice e executar `reindex` restaura o funcionamento;
10. modo offline continua respondendo o que já está na base.

Também será obrigatório:

- nenhum rascunho responder como verificado;
- nenhum envio remoto conter segredo detectado;
- nenhuma página pesquisada conseguir alterar regras ou executar ações;
- nenhuma operação sobrescrever documento verificado sem confirmação;
- todas as respostas indicarem origem local, externa ou mista.
