// Gera docs/Documentacao_Tecnica.docx a partir do conteúdo deste arquivo.
// O texto da documentação fica aqui para que cada mudança apareça no pull
// request e possa ser revisada junto com o código.
//
// Uso: npm install docx  (uma vez)  e depois  node docs/fonte/gerar_documentacao.js

const fs = require("fs");
const path = require("path");
const {
  AlignmentType, BorderStyle, Document, Footer, Header, HeadingLevel, LevelFormat,
  Packer, PageBreak, PageNumber, Paragraph, ShadingType, Table, TableCell, TableRow,
  TextRun, WidthType,
} = require("docx");

// ---------- Aparência ----------
const FONTE = "Arial";
const FONTE_CODIGO = "Consolas";
const COR_TITULO = "1F3864";
const COR_DISCRETA = "595959";
const LARGURA_UTIL = 9071; // A4 com margens de 3 cm (esquerda) e 2 cm (direita), em DXA
const BORDA = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
const BORDAS = { top: BORDA, bottom: BORDA, left: BORDA, right: BORDA };

// ---------- Texto com marcação simples: **negrito** e `código` ----------
function runs(texto, extra = {}) {
  return texto
    .split(/(\*\*[^*]+\*\*|`[^`]+`)/)
    .filter(Boolean)
    .map((parte) => {
      if (parte.startsWith("**")) return new TextRun({ text: parte.slice(2, -2), bold: true, ...extra });
      if (parte.startsWith("`")) return new TextRun({ text: parte.slice(1, -1), font: FONTE_CODIGO, size: 20, ...extra });
      return new TextRun({ text: parte, ...extra });
    });
}

const conteudo = [];
const listasNumeradas = [];

const p = (texto, opcoes = {}) =>
  conteudo.push(new Paragraph({ children: runs(texto), spacing: { after: 120, line: 300 }, ...opcoes }));
const h1 = (texto) => conteudo.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(texto)] }));
const h2 = (texto) => conteudo.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(texto)] }));
const h3 = (texto) => conteudo.push(new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(texto)] }));
const quebra = () => conteudo.push(new Paragraph({ children: [new PageBreak()] }));

function marcadores(itens) {
  for (const item of itens) {
    conteudo.push(new Paragraph({
      numbering: { reference: "marcadores", level: 0 },
      children: runs(item),
      spacing: { after: 80, line: 290 },
    }));
  }
}

function numerada(itens) {
  const ref = `num-${listasNumeradas.length + 1}`;
  listasNumeradas.push(ref);
  for (const item of itens) {
    conteudo.push(new Paragraph({
      numbering: { reference: ref, level: 0 },
      children: runs(item),
      spacing: { after: 80, line: 290 },
    }));
  }
}

function codigo(linhas) {
  linhas.forEach((linha, i) => {
    conteudo.push(new Paragraph({
      children: [new TextRun({ text: linha || " ", font: FONTE_CODIGO, size: 19 })],
      shading: { type: ShadingType.CLEAR, fill: "F2F2F2", color: "auto" },
      spacing: { before: i === 0 ? 60 : 0, after: i === linhas.length - 1 ? 160 : 0 },
      indent: { left: 200, right: 200 },
      keepNext: i < linhas.length - 1,
      keepLines: true,
    }));
  });
}

function tabela(cabecalho, linhas, proporcoes) {
  const total = proporcoes.reduce((a, b) => a + b, 0);
  const larguras = proporcoes.map((x) => Math.floor((x / total) * LARGURA_UTIL));
  larguras[larguras.length - 1] += LARGURA_UTIL - larguras.reduce((a, b) => a + b, 0);

  const celula = (texto, i, cabeca) =>
    new TableCell({
      borders: BORDAS,
      width: { size: larguras[i], type: WidthType.DXA },
      shading: cabeca ? { type: ShadingType.CLEAR, fill: "D9E2F3", color: "auto" } : undefined,
      margins: { top: 60, bottom: 60, left: 100, right: 100 },
      children: [new Paragraph({ children: runs(texto, cabeca ? { bold: true, size: 20 } : { size: 20 }) })],
    });

  conteudo.push(new Table({
    width: { size: LARGURA_UTIL, type: WidthType.DXA },
    columnWidths: larguras,
    rows: [
      new TableRow({ tableHeader: true, children: cabecalho.map((t, i) => celula(t, i, true)) }),
      ...linhas.map((linha) => new TableRow({ cantSplit: true, children: linha.map((t, i) => celula(t, i, false)) })),
    ],
  }));
  conteudo.push(new Paragraph({ children: [], spacing: { after: 120 } }));
}

// =====================================================================
// CAPA
// =====================================================================
const VERSAO = "0.3";
const DATA = "19/10/2026";

conteudo.push(new Paragraph({ spacing: { before: 2400 }, children: [] }));
conteudo.push(new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { after: 240 },
  children: [new TextRun({ text: "Documentação Técnica do Protótipo", bold: true, size: 40, color: COR_TITULO })],
}));
conteudo.push(new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { after: 1600 },
  children: [new TextRun({
    text: "Sistema de correção automatizada com feedback elaborado para questões objetivas e discursivas",
    size: 26, color: COR_DISCRETA,
  })],
}));
for (const [rotulo, valor] of [
  ["Autor", "Felipe Vidal Cominetti"],
  ["Orientador", "Prof. Gildomiro Bairros"],
  ["Curso", "Engenharia de Software, UniAmérica Centro Universitário, Foz do Iguaçu (PR)"],
  ["Repositório", "github.com/vidalcmt/TCC-Prototipo"],
  ["Versão", `${VERSAO}, de ${DATA}`],
]) {
  conteudo.push(new Paragraph({
    alignment: AlignmentType.CENTER, spacing: { after: 100 },
    children: [new TextRun({ text: `${rotulo}: `, bold: true }), new TextRun(valor)],
  }));
}
quebra();

// =====================================================================
// CONTEÚDO
// =====================================================================
h1("Conteúdo");
numerada([
  "Introdução", "Arquitetura", "Modelo de dados", "Módulos e funções", "Configuração e execução",
  "Testes automatizados", "Processo de desenvolvimento", "Decisões técnicas e limitações",
  "Glossário", "Histórico de versões", "Referências",
]);
p("Este documento acompanha o código e é atualizado no mesmo pull request de cada mudança. Quando houver divergência entre este texto e o código, vale o código, e a divergência deve ser corrigida aqui.");
quebra();

// ---------------------------------------------------------------------
h1("1. Introdução");

h2("1.1 Objetivo do sistema");
p("O sistema apoia o professor na correção de questões. Nas questões objetivas, o professor cadastra a questão e indica a alternativa correta, e o sistema explica o raciocínio que leva a cada alternativa, inclusive às erradas. Nas questões discursivas, o sistema analisa a resposta do aluno, produz um feedback elaborado e sugere uma nota.");
p("A nota sugerida nunca é final. Ela só passa a valer depois que o professor a aceita ou a ajusta, o que garante a revisão humana em toda correção.");

h2("1.2 Papel do protótipo na pesquisa");
p("A pesquisa segue a metodologia Design Science Research (DSR), na qual se constrói um artefato e se avalia o seu desempenho. O protótipo é esse artefato e, ao mesmo tempo, o instrumento que gera os dados da seção de Resultados do artigo: custo por correção, tempo de resposta, taxa de falhas e concordância entre a nota sugerida e a nota do professor.");
p("Por esse motivo, a medição foi implementada antes de qualquer funcionalidade. Toda chamada ao modelo de linguagem registra seus números desde a primeira requisição, inclusive quando falha.");

h2("1.3 Escopo");
tabela(
  ["Dentro do escopo", "Fora do escopo"],
  [
    ["Cadastro de questões objetivas e discursivas", "Reconhecimento de texto manuscrito (fase posterior, medida à parte)"],
    ["Explicação das alternativas das objetivas", "Treinamento ou ajuste fino de modelo próprio"],
    ["Feedback e nota sugerida nas discursivas, com e sem resposta esperada", "Acesso direto de alunos ao sistema"],
    ["Tela de aceite ou ajuste da nota pelo professor", "Publicação em ambiente de produção"],
    ["Registro de métricas e exportação em CSV", ""],
    ["Comparação com um método de similaridade de textos (baseline)", ""],
  ],
  [1, 1],
);

h2("1.4 Situação atual");
tabela(
  ["Etapa", "Conteúdo", "Situação"],
  [
    ["1", "Esqueleto, banco de dados e medição", "Concluída em 16/10/2026"],
    ["2", "Módulo objetivo", "Implementada em 19/10/2026; falta o teste com a chave real"],
    ["3", "Módulo discursivo", "Pendente"],
    ["4", "Tela de aceite do professor", "Pendente"],
    ["5", "Execução em lote e baseline", "Pendente"],
    ["6", "Análise e coleta com especialistas", "Pendente"],
  ],
  [1, 5, 4],
);

// ---------------------------------------------------------------------
h1("2. Arquitetura");

h2("2.1 Tecnologias e motivos da escolha");
tabela(
  ["Camada", "Escolha", "Motivo"],
  [
    ["Linguagem", "Python 3.11 ou superior", "As bibliotecas de comparação de textos em português usadas no baseline existem de forma madura em Python."],
    ["Servidor web", "FastAPI", "Leve, rápido de escrever e já conhecido pelo autor."],
    ["Páginas", "HTML gerado no servidor (Jinja2)", "Dispensa um projeto de interface separado, o que reduz o código no prazo disponível."],
    ["Banco de dados", "SQLite", "Um único arquivo, sem servidor para instalar. Suficiente para um usuário por vez."],
    ["Acesso ao banco", "SQLAlchemy", "Permite trabalhar com as tabelas como classes Python, sem escrever SQL à mão."],
    ["Evolução do banco", "Alembic", "Registra cada mudança na estrutura das tabelas como uma migração versionada."],
    ["Validação de dados", "Pydantic", "Confere se a resposta do modelo tem exatamente os campos e tipos esperados."],
    ["Modelo de linguagem", "OpenAI gpt-6.1-sol", "Equilíbrio entre qualidade e custo; a versão exata é gravada em cada requisição."],
    ["Testes", "pytest", "Padrão em Python; os testes usam um cliente falso e não gastam crédito."],
  ],
  [2, 3, 6],
);

h2("2.2 Fluxo de uma chamada ao modelo");
p("Toda chamada ao modelo passa pela função `chamar_modelo`, em `app/correcao/llm.py`. Não existe outro caminho até a API, o que garante que nenhuma requisição fique sem medição.");
numerada([
  "O módulo de correção carrega o prompt versionado (por exemplo, `objetiva_v1`) e preenche os campos com os dados da questão.",
  "`chamar_modelo` dispara o cronômetro e envia a requisição à API, pedindo a resposta no formato definido por uma classe Pydantic.",
  "A API devolve a resposta, o nome exato do modelo que a gerou e a contagem de tokens consumidos.",
  "A função para o cronômetro, lê os tokens e calcula o custo com a tabela de preços.",
  "Se a resposta veio no formato esperado, a requisição é marcada como sucesso; se não veio, ou se houve erro, é marcada como falha, com o motivo.",
  "Uma linha é gravada na tabela `metrica_requisicao` em todos os casos, e o resultado volta para quem chamou.",
]);

h2("2.3 Estrutura de pastas");
tabela(
  ["Caminho", "Conteúdo"],
  [
    ["`app/main.py`", "Aplicação web: rotas da página inicial e de verificação"],
    ["`app/config.py`", "Leitura das configurações do arquivo .env"],
    ["`app/database.py`", "Conexão com o banco e abertura de sessões"],
    ["`app/models.py`", "Definição das oito tabelas do banco"],
    ["`app/correcao/`", "Chamada ao modelo (`llm.py`), prompts (`prompts.py`), contratos de saída (`contratos.py`) e explicação de objetivas (`objetiva.py`)"],
    ["`app/metricas/`", "Cálculo de custo (`precos.py`), página e exportação de métricas (`router.py`)"],
    ["`app/questoes/`", "Páginas de questões: lista, cadastro, detalhe e geração da explicação"],
    ["`app/revisao/`", "Reservada para a tela de aceite (etapa 4)"],
    ["`app/templates/`", "Páginas HTML"],
    ["`config/precos.toml`", "Preços por modelo, com fonte e data de acesso"],
    ["`prompts/`", "Prompts versionados e registro de mudanças"],
    ["`alembic/`", "Migrações do banco"],
    ["`scripts/`", "Utilitários de linha de comando"],
    ["`dados/`", "Corpus e cópias congeladas de questões"],
    ["`baseline/`", "Comparação por similaridade de textos (etapa 5)"],
    ["`tests/`", "Testes automatizados"],
    ["`docs/`", "Esta documentação e o seu gerador"],
  ],
  [3, 7],
);

// ---------------------------------------------------------------------
h1("3. Modelo de dados");
p("O banco tem oito tabelas, criadas pela migração inicial do Alembic. Duas delas existem por razão metodológica e não devem ser simplificadas: `revisao_professor`, que guarda a nota sugerida e a nota final lado a lado e permite calcular a concordância, e `metrica_requisicao`, que registra também as falhas, porque a taxa de falha é um resultado da pesquisa.");
tabela(
  ["Tabela", "Finalidade"],
  [
    ["`questao`", "Enunciado, tipo, área, origem e nota máxima"],
    ["`alternativa`", "As cinco alternativas de uma questão objetiva e qual é a correta"],
    ["`criterio_rubrica`", "Critérios de correção de uma discursiva, com peso (opcional)"],
    ["`resposta_esperada`", "Resposta de referência de uma discursiva (opcional)"],
    ["`submissao`", "Resposta de um aluno ou do corpus a uma questão"],
    ["`correcao`", "Saída do modelo para uma submissão"],
    ["`revisao_professor`", "Decisão do professor sobre a nota sugerida"],
    ["`metrica_requisicao`", "Números de cada chamada ao modelo"],
  ],
  [3, 7],
);

const campos = (titulo, linhas) => { h3(titulo); tabela(["Campo", "Tipo", "Descrição"], linhas, [3, 2, 6]); };

campos("questao", [
  ["`id`", "inteiro", "Identificador"],
  ["`tipo`", "texto", "`objetiva` ou `discursiva`"],
  ["`enunciado`", "texto", "Texto completo da questão"],
  ["`area`", "texto", "Área do conhecimento, por exemplo `ciencias-humanas`"],
  ["`fonte`", "texto", "Origem, por exemplo `ENEM 2023, questão 60`"],
  ["`ano`", "inteiro", "Ano da prova de origem"],
  ["`nota_maxima`", "decimal", "Nota máxima da questão (padrão 10)"],
  ["`criado_em`", "data e hora", "Momento do cadastro, em UTC"],
]);
campos("alternativa", [
  ["`id`", "inteiro", "Identificador"],
  ["`questao_id`", "inteiro", "Questão a que pertence"],
  ["`letra`", "texto", "De A a E"],
  ["`texto`", "texto", "Texto da alternativa"],
  ["`correta`", "verdadeiro ou falso", "Se é a alternativa correta"],
]);
campos("criterio_rubrica", [
  ["`id`", "inteiro", "Identificador"],
  ["`questao_id`", "inteiro", "Questão a que pertence"],
  ["`descricao`", "texto", "O que o critério avalia"],
  ["`peso`", "decimal", "Peso do critério na nota"],
]);
campos("resposta_esperada", [
  ["`questao_id`", "inteiro", "Questão a que pertence (uma resposta por questão)"],
  ["`texto`", "texto", "Resposta de referência"],
]);
campos("submissao", [
  ["`id`", "inteiro", "Identificador"],
  ["`questao_id`", "inteiro", "Questão respondida"],
  ["`resposta_aluno`", "texto", "Resposta discursiva"],
  ["`alternativa_escolhida`", "texto", "Letra escolhida, nas objetivas"],
  ["`codigo_corpus`", "texto", "Código anônimo da resposta no corpus, por exemplo `R014`"],
  ["`origem`", "texto", "`autor`, `voluntario` ou `especialista`; usada como variável de análise"],
  ["`criado_em`", "data e hora", "Momento do registro"],
]);
campos("correcao", [
  ["`id`", "inteiro", "Identificador"],
  ["`submissao_id`", "inteiro", "Submissão corrigida (vazio nas explicações de objetivas)"],
  ["`questao_id`", "inteiro", "Questão"],
  ["`feedback_json`", "texto", "Saída completa do modelo, em JSON"],
  ["`nota_sugerida`", "decimal", "Nota proposta pelo modelo (discursivas)"],
  ["`usou_resposta_esperada`", "verdadeiro ou falso", "Condição experimental da correção"],
  ["`modelo`", "texto", "Modelo que gerou a saída"],
  ["`prompt_versao`", "texto", "Versão do prompt usada"],
  ["`criado_em`", "data e hora", "Momento da correção"],
]);
campos("revisao_professor", [
  ["`id`", "inteiro", "Identificador"],
  ["`correcao_id`", "inteiro", "Correção revisada"],
  ["`nota_sugerida`", "decimal", "Cópia da nota do modelo no momento da revisão"],
  ["`nota_final`", "decimal", "Nota atribuída pelo professor"],
  ["`aceitou_sugestao`", "verdadeiro ou falso", "Calculado: as duas notas são iguais"],
  ["`comentario`", "texto", "Justificativa do professor (opcional)"],
  ["`criado_em`", "data e hora", "Momento da revisão"],
]);
campos("metrica_requisicao", [
  ["`id`", "inteiro", "Identificador"],
  ["`correcao_id`", "inteiro", "Correção gerada (vazio quando a chamada falha)"],
  ["`tipo_questao`", "texto", "`objetiva` ou `discursiva`"],
  ["`usou_resposta_esperada`", "verdadeiro ou falso", "Condição experimental"],
  ["`modelo_solicitado`", "texto", "Nome pedido à API, por exemplo `gpt-6.1-sol`"],
  ["`modelo`", "texto", "Nome devolvido pela API; registra a versão exata"],
  ["`prompt_versao`", "texto", "Versão do prompt, por exemplo `objetiva_v1`"],
  ["`tokens_entrada`", "inteiro", "Total de tokens enviados"],
  ["`tokens_entrada_cache`", "inteiro", "Parte da entrada lida do cache, cobrada mais barato"],
  ["`tokens_escrita_cache`", "inteiro", "Parte da entrada gravada no cache"],
  ["`tokens_saida`", "inteiro", "Tokens gerados pelo modelo"],
  ["`tokens_raciocinio`", "inteiro", "Parte da saída usada em raciocínio interno, cobrada como saída"],
  ["`custo_usd`", "decimal", "Custo calculado, em dólares"],
  ["`latencia_ms`", "decimal", "Tempo do envio até a resposta completa, em milissegundos"],
  ["`sucesso`", "verdadeiro ou falso", "Se veio uma saída válida"],
  ["`motivo_falha`", "texto", "Descrição do erro, quando houver"],
  ["`criado_em`", "data e hora", "Momento da requisição, em UTC; documenta o período da coleta"],
]);

// ---------------------------------------------------------------------
h1("4. Módulos e funções");

h2("4.1 Configuração: app/config.py");
tabela(["Elemento", "O que faz"], [
  ["`RAIZ`", "Caminho absoluto da pasta do projeto, usado para achar arquivos independentemente de onde o comando é rodado"],
  ["`Configuracao`", "Lê `OPENAI_API_KEY`, `MODELO` e `DATABASE_URL` do arquivo .env, com valores padrão"],
  ["`config`", "Instância única das configurações, importada pelos outros módulos"],
], [4, 6]);

h2("4.2 Banco de dados: app/database.py");
tabela(["Elemento", "O que faz"], [
  ["`Base`", "Classe da qual todas as tabelas herdam"],
  ["`engine`", "Conexão com o arquivo SQLite"],
  ["`SessionLocal`", "Fábrica de sessões; cada sessão é uma conversa com o banco"],
  ["`obter_sessao()`", "Abre uma sessão por requisição web e a fecha ao final, mesmo em caso de erro"],
], [4, 6]);

h2("4.3 Prompts: app/correcao/prompts.py");
p("Cada prompt é um arquivo em `prompts/<nome>/v<N>.md`. A linha `---usuario---` separa a instrução de sistema, que define o papel do modelo, da mensagem do usuário, que leva os dados da questão. Campos entre chaves, como `{enunciado}`, são preenchidos na hora da chamada.");
tabela(["Elemento", "O que faz"], [
  ["`Prompt`", "Guarda nome, versão, texto de sistema e modelo da mensagem do usuário"],
  ["`Prompt.identificador`", "Devolve o rótulo gravado nas métricas, por exemplo `teste_v1`"],
  ["`Prompt.mensagens(**campos)`", "Monta a lista de mensagens enviada à API, com os campos preenchidos"],
  ["`carregar_prompt(nome, versao)`", "Lê o arquivo do disco e devolve um `Prompt`; avisa se faltar o separador"],
], [4, 6]);

h2("4.4 Chamada ao modelo: app/correcao/llm.py");
p("Este é o módulo central da medição. A seção 2.2 descreve o seu fluxo.");
tabela(["Elemento", "O que faz"], [
  ["`TEMPO_LIMITE_S`", "Tempo máximo de espera por uma resposta: 120 segundos"],
  ["`cliente_padrao()`", "Cria o cliente da OpenAI uma única vez, com as novas tentativas automáticas desligadas"],
  ["`ResultadoChamada`", "Agrupa a saída validada (ou nada, na falha) e a linha de métrica gravada"],
  ["`_campo(objeto, *nomes)`", "Lê um campo de contagem de tokens que pode não existir, devolvendo zero"],
  ["`chamar_modelo(...)`", "Envia a requisição, mede, calcula o custo e grava a métrica em qualquer resultado"],
], [4, 6]);
h3("Parâmetros de chamar_modelo");
tabela(["Parâmetro", "Significado"], [
  ["`sessao`", "Sessão do banco onde a métrica é gravada"],
  ["`prompt`", "Prompt já carregado"],
  ["`formato`", "Classe Pydantic que define o formato exigido da resposta"],
  ["`campos`", "Valores que preenchem o prompt"],
  ["`tipo_questao`", "Rótulo gravado na métrica (`objetiva` ou `discursiva`)"],
  ["`usou_resposta_esperada`", "Condição experimental gravada na métrica"],
  ["`modelo`", "Permite trocar o modelo em um experimento; por padrão, o do .env"],
  ["`cliente`", "Permite usar um cliente falso nos testes"],
], [4, 6]);
h3("Por que as novas tentativas automáticas estão desligadas");
p("Por padrão, a biblioteca da OpenAI repete uma chamada que falhou até duas vezes, sem avisar. Com isso, a latência medida somaria várias tentativas e uma falha intermediária desapareceria dos dados. Com `max_retries=0`, cada linha de `metrica_requisicao` corresponde a exatamente uma tentativa. Quando for preciso tentar de novo, como na execução em lote, o código chama outra vez e a nova tentativa vira outra linha.");

h2("4.5 Contrato de saída objetivo: app/correcao/contratos.py");
p("Define, em Pydantic, o formato que a API é obrigada a seguir na resposta, conforme a seção \"Contrato de saída da IA\" da especificação. As descrições dos campos são enviadas junto com o formato e orientam o modelo.");
tabela(["Elemento", "O que faz"], [
  ["`ExplicacaoAlternativa`", "Uma alternativa: `letra`, `correta`, `por_que` e `conceito_envolvido`"],
  ["`CorrecaoObjetiva`", "A resposta completa: `questao_id`, `alternativa_correta`, lista de `explicacoes`, `explicacao_correta` e `nivel_dificuldade_estimado` (baixo, medio ou alto)"],
  ["`problemas_de_consistencia(...)`", "Confere a resposta com a questão cadastrada e devolve a lista de problemas; lista vazia significa resposta consistente"],
], [4, 6]);
p("O formato já é garantido pela API. A conferência verifica o conteúdo: a resposta precisa repetir o identificador da questão, concordar com o gabarito do professor, explicar cada alternativa exatamente uma vez e marcar como correta apenas a alternativa do gabarito.");
p("O campo `conceito_envolvido` existe por razão metodológica: permite agrupar os erros por conceito na análise dos resultados.");

h2("4.6 Explicação de questões objetivas: app/correcao/objetiva.py");
tabela(["Elemento", "O que faz"], [
  ["`PROMPT_OBJETIVA`", "Prompt usado: `objetiva`, versão 1"],
  ["`gabarito_da(questao)`", "Devolve a letra correta; recusa questão sem gabarito ou com mais de um"],
  ["`campos_do_prompt(questao)`", "Prepara identificador, enunciado, alternativas no formato `A) texto` e gabarito"],
  ["`gerar_explicacao(sessao, questao)`", "Chama o modelo, confere a resposta e grava a correção"],
  ["`ResultadoExplicacao`", "Agrupa a correção gravada (ou nada, na falha) e a métrica da chamada"],
], [4, 6]);
h3("Passos de gerar_explicacao");
numerada([
  "Carrega o prompt `objetiva_v1` e chama `chamar_modelo` com o formato `CorrecaoObjetiva`.",
  "Se a chamada falhou, devolve a falha; a métrica já foi gravada por `chamar_modelo`.",
  "Se a resposta veio, confere a consistência com a questão.",
  "Se houver problema, não grava a correção, marca a métrica como falha e registra o motivo, por exemplo `saida inconsistente: alternativa_correta B diferente do gabarito D`.",
  "Se estiver tudo certo, grava a correção em `correcao` e liga a métrica a ela pelo campo `correcao_id`.",
]);
p("A explicação de uma objetiva pertence à questão, e não à resposta de um aluno. Por isso, nessas correções, o campo `submissao_id` fica vazio.");
h3("Prompt objetiva_v1");
p("O texto fica em `prompts/objetiva/v1.md`. Em resumo, ele instrui o modelo a:");
marcadores([
  "nunca questionar ou alterar o gabarito informado pelo professor;",
  "para cada alternativa incorreta, identificar o erro de raciocínio plausível que levaria um estudante a escolhê-la e explicar por que ele não se sustenta (RF02 e RF03);",
  "para a correta, apontar os elementos do enunciado que a sustentam, e descrever em passos o caminho até a resposta;",
  "não inventar dados, autores ou citações fora do enunciado;",
  "escrever em português do Brasil, dirigido ao estudante, sem expressões como \"obviamente\".",
]);

h2("4.7 Páginas de questões: app/questoes/router.py");
tabela(["Rota", "O que faz"], [
  ["`GET /questoes`", "Lista as questões objetivas, com origem, área, início do enunciado e número de explicações geradas"],
  ["`GET /questoes/nova`", "Formulário de cadastro manual (RF01)"],
  ["`POST /questoes`", "Valida e grava a questão: enunciado, as cinco alternativas e exatamente uma correta. Com erro, devolve o formulário preenchido e a lista de problemas"],
  ["`GET /questoes/{id}`", "Enunciado, alternativas com o gabarito destacado e, se existir, a explicação mais recente com modelo, prompt, tempo e custo"],
  ["`POST /questoes/{id}/explicar`", "Gera uma nova explicação e volta para a página da questão; na falha, a página mostra o motivo e o número da métrica"],
], [4, 6]);
p("A função `obter_cliente_llm` fornece o cliente do modelo às rotas. Nos testes, ela é trocada por um cliente falso, o que permite testar as páginas sem gastar crédito.");

h2("4.8 Custo: app/metricas/precos.py");
tabela(["Elemento", "O que faz"], [
  ["`Preco`", "Preços de um modelo: entrada, entrada em cache, gravação em cache e saída"],
  ["`carregar_tabela()`", "Lê `config/precos.toml` uma vez e guarda em memória"],
  ["`preco_do_modelo(modelo)`", "Procura pelo nome exato e, se não achar, pelo nome base (aceita sufixos de versão)"],
  ["`calcular_custo(...)`", "Aplica a fórmula da seção 5.2; devolve vazio para modelo sem preço, em vez de inventar um valor"],
], [4, 6]);

h2("4.9 Métricas na web: app/metricas/router.py");
tabela(["Rota", "O que faz"], [
  ["`GET /metricas`", "Página com as 200 requisições mais recentes"],
  ["`GET /metricas/exportar.csv`", "Arquivo CSV com todas as requisições e todos os campos, para análise (RF14)"],
], [4, 6]);

h2("4.10 Aplicação: app/main.py");
tabela(["Rota", "O que faz"], [
  ["`GET /`", "Página inicial, com o modelo configurado"],
  ["`GET /saude`", "Verificação rápida de que o servidor está no ar"],
], [4, 6]);

h2("4.11 Requisição de teste: scripts/teste_requisicao.py");
p("Faz uma chamada real ao modelo com o prompt `teste_v1` e mostra no terminal os números gravados. É o critério de pronto da etapa 1. Resultado da primeira execução, em 16/10/2026: sucesso, 77 tokens de entrada, 14 de saída, custo de US$ 0,000294 e latência de 3.587 ms.");

h2("4.12 Importador do ENEM: scripts/importar_enem.py");
p("Baixa questões da API comunitária enem.dev, que cobre as provas de 2009 a 2023, e grava uma cópia congelada em `dados/enem/` com a data de acesso. A API é mantida por voluntários e pode mudar ou sair do ar; a cópia garante que a pesquisa saiba exatamente quais questões usou.");
tabela(["Elemento", "O que faz"], [
  ["`buscar_questoes(ano, cliente)`", "Percorre todas as páginas da prova, respeitando o limite de uma requisição por segundo; para após cinco recusas seguidas"],
  ["`somente_texto(questao)`", "Diz se a questão não tem imagem no enunciado nem nas alternativas"],
  ["`filtrar(questoes, area)`", "Mantém só a área pedida e, por padrão, só questões em texto"],
  ["`montar_enunciado(questao)`", "Junta o texto-base e o comando da questão"],
  ["`salvar_copia(...)`", "Grava o arquivo JSON congelado com fonte, data de acesso e filtros"],
  ["`importar_no_banco(questoes, sessao)`", "Grava questões e gabarito no banco, sem duplicar"],
  ["`main()`", "Lê as opções da linha de comando e executa os passos acima"],
], [4, 6]);
p("Questões com imagem ficam de fora por padrão porque exigiriam que o modelo interpretasse a imagem, o que acrescentaria uma variável que a pesquisa não quer medir neste momento. A opção `--com-imagens` desliga o filtro.");

// ---------------------------------------------------------------------
h1("5. Configuração e execução");

h2("5.1 Arquivo .env");
p("O arquivo `.env` fica na raiz do projeto, é criado a partir de `.env.example` e nunca vai para o GitHub, porque contém a chave da API.");
tabela(["Variável", "Obrigatória", "Significado"], [
  ["`OPENAI_API_KEY`", "Sim", "Chave criada em platform.openai.com/api-keys"],
  ["`MODELO`", "Não", "Modelo usado; padrão `gpt-6.1-sol`. Trocar exige registrar no artigo"],
  ["`DATABASE_URL`", "Não", "Outro banco, sempre com caminho absoluto. Sem ela, usa `tcc.db` na raiz"],
], [3, 2, 6]);

h2("5.2 Tabela de preços");
p("Os preços ficam em `config/precos.toml`, em dólares por milhão de tokens, com a fonte e a data de acesso. Valores em vigor nesta versão, consultados em 15/10/2026:");
tabela(["Modelo", "Entrada", "Entrada em cache", "Gravação em cache", "Saída"], [
  ["`gpt-6.1-sol` (em uso)", "2,00", "0,10", "2,50", "10,00"],
  ["`gpt-6-luna`", "0,10", "0,01", "0,125", "0,50"],
  ["`gpt-6-astra`", "10,00", "1,00", "12,50", "50,00"],
], [3, 2, 2, 2, 2]);
p("O custo de cada requisição é calculado assim, com os tokens lidos da resposta da API:");
codigo([
  "entrada normal = entrada - lidos do cache - gravados no cache",
  "custo = ( entrada normal x preço de entrada",
  "        + tokens lidos do cache x preço de entrada em cache",
  "        + tokens gravados no cache x preço de gravação em cache",
  "        + tokens de saída x preço de saída ) / 1.000.000",
]);

h2("5.3 Primeira execução no Windows");
numerada([
  "Clonar o repositório: `git clone https://github.com/vidalcmt/TCC-Prototipo.git` e entrar na pasta.",
  "Criar o ambiente virtual: `python -m venv .venv`.",
  "Ativar o ambiente: `.venv\\Scripts\\Activate.ps1`. O terminal passa a mostrar `(.venv)` no início da linha. Todo comando abaixo exige esse prefixo.",
  "Instalar as dependências: `pip install -r requirements.txt`.",
  "Criar o .env: `Copy-Item .env.example .env` e colar a chave na linha `OPENAI_API_KEY`.",
  "Criar o banco: `alembic upgrade head`.",
  "Testar a conexão: `python -m scripts.teste_requisicao`.",
]);
p("Se o PowerShell bloquear a ativação do ambiente, rode antes `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`, que libera scripts só na janela atual.");

h2("5.4 Comandos do dia a dia");
tabela(["Comando", "Para que serve"], [
  ["`git pull`", "Trazer as mudanças mais recentes do GitHub"],
  ["`pip install -r requirements.txt`", "Instalar dependências novas, quando o arquivo mudar"],
  ["`alembic upgrade head`", "Aplicar mudanças novas na estrutura do banco"],
  ["`uvicorn app.main:app --reload`", "Subir o sistema em http://localhost:8000; as questões ficam em /questoes"],
  ["`pytest`", "Rodar os testes automatizados"],
  ["`python -m scripts.importar_enem --ano 2023 --area ciencias-humanas`", "Listar questões do ENEM em texto e congelar a cópia"],
  ["o mesmo comando com `--importar` no final", "Gravar também as questões no banco"],
], [5, 5]);

// ---------------------------------------------------------------------
h1("6. Testes automatizados");
p("Os testes rodam com `pytest` e não acessam a internet nem gastam crédito: a API da OpenAI e a API do ENEM são substituídas por versões falsas que devolvem respostas controladas. Total nesta versão: 28 testes.");
tabela(["Arquivo", "O que verifica"], [
  ["`tests/test_precos.py`", "Custo correto para o modelo em uso; preço de cache aplicado; nome com sufixo de versão; modelo desconhecido não gera custo inventado"],
  ["`tests/test_llm.py`", "Sucesso grava tokens, custo, latência, modelo e prompt; resposta sem formato válido vira falha com tokens; erro de rede vira falha com motivo; cliente sem novas tentativas automáticas"],
  ["`tests/test_app.py`", "Rota de verificação; página de métricas e exportação em CSV"],
  ["`tests/test_objetiva.py`", "Prompt montado com enunciado, alternativas e gabarito; correção gravada e ligada à métrica; quatro tipos de resposta inconsistente viram falha sem correção; resposta malformada; lista, detalhe e página inexistente; cadastro válido e inválido; geração pela página; falha exibida com o motivo"],
  ["`tests/test_importar_enem.py`", "Paginação; parada após recusas seguidas; filtro de área e de imagens; montagem do enunciado; importação com gabarito e sem duplicar"],
], [3, 7]);

// ---------------------------------------------------------------------
h1("7. Processo de desenvolvimento");

h2("7.1 Revisão antes de entrar no código principal");
p("Nenhuma mudança entra na branch `main` sem revisão conjunta. O fluxo é:");
numerada([
  "Cada etapa ou correção é feita em uma branch própria, separada da `main`.",
  "As mudanças são divididas em commits pequenos, cada um com uma mensagem que explica o motivo.",
  "Um pull request é aberto com um roteiro de revisão: o que mudou, por que e o que conferir.",
  "A revisão é feita em conjunto, função por função, e os ajustes pedidos entram na mesma branch.",
  "Só depois da aprovação o pull request é incorporado à `main`.",
  "Esta documentação é atualizada no mesmo pull request.",
]);

h2("7.2 Prompts versionados");
p("Um prompt usado na coleta de dados não é editado. Qualquer mudança gera um arquivo novo (`v2`, `v3`) e uma entrada em `prompts/CHANGELOG.md` com data e motivo. Como cada métrica grava a versão do prompt, é sempre possível dizer qual texto gerou cada resultado.");

h2("7.3 Atualização de preços");
p("Ao mudar um valor em `config/precos.toml`, a data de acesso no mesmo arquivo também muda, porque a seção de Materiais e Métodos cita a fonte com essa data.");

h2("7.4 Corpus congelado");
p("O corpus de validação é congelado em 25/10/2026 e não muda depois disso. Cada resposta recebe um código anônimo e uma origem; nenhum nome de pessoa entra no repositório.");

// ---------------------------------------------------------------------
h1("8. Decisões técnicas e limitações");

h2("8.1 Decisões");
tabela(["Decisão", "Motivo"], [
  ["Um único ponto de chamada ao modelo", "Garante que toda requisição seja medida"],
  ["Falhas gravadas como métricas", "A taxa de falha é um resultado da pesquisa"],
  ["Tokens lidos da API, nunca estimados", "O custo reportado precisa ser o custo real"],
  ["Nome do modelo devolvido pela API gravado", "Registra a versão exata usada, exigência da reprodutibilidade"],
  ["Sem novas tentativas automáticas", "Cada medição corresponde a uma tentativa"],
  ["Questões do ENEM só em texto", "Evita uma variável (interpretação de imagem) fora do objetivo"],
  ["Cópia congelada das questões", "A fonte comunitária pode mudar; a pesquisa precisa ser reproduzível"],
  ["SQLite em vez de um servidor de banco", "Um usuário por vez; menos instalação e manutenção"],
  ["Resposta que contradiz o gabarito conta como falha", "Uma explicação incompatível com a decisão do professor é inutilizável, e a taxa de falha precisa refletir isso"],
  ["Explicação de objetiva ligada à questão, não a um aluno", "O RF02 pede a explicação de cada alternativa, que não depende de quem respondeu"],
], [4, 6]);

h2("8.2 Limitações e pontos de atenção");
marcadores([
  "**Versão do modelo:** a API devolveu `gpt-6.1-sol` sem sufixo de data, o que indica um nome que pode apontar para versões atualizadas ao longo do tempo. O artigo deve citar também o período da coleta, que está registrado em `criado_em`.",
  "**Questões do ENEM nos dados de treino:** é provável que o modelo já tenha visto essas questões e suas resoluções. Como o professor informa a resposta correta, o efeito é menor, mas deve ser declarado como limitação.",
  "**Gabarito de fonte comunitária:** o gabarito das questões escolhidas deve ser conferido com o gabarito oficial do INEP, que é a fonte primária citada no artigo.",
  "**Tokens gravados em cache:** o cálculo supõe que esses tokens já estão incluídos no total de entrada, como acontece com os tokens lidos do cache. A suposição ainda deve ser confirmada na documentação da OpenAI; ela só afeta requisições que usam cache.",
  "**Revisão duplicada:** a tabela `revisao_professor` ainda permite mais de uma revisão para a mesma correção. A restrição será incluída na etapa 4.",
  "**Geração na própria requisição da página:** o navegador espera a resposta do modelo, o que leva alguns segundos. É adequado para um usuário por vez; a execução em lote da etapa 5 roda por linha de comando.",
  "**Explicações anteriores:** a página mostra só a explicação mais recente. As anteriores continuam no banco e entram na análise.",
  "**Latência e rede:** a latência inclui o tempo de rede do computador onde o sistema roda. Medições comparadas entre si devem vir da mesma máquina e conexão.",
]);

// ---------------------------------------------------------------------
h1("9. Glossário");
tabela(["Termo", "Significado"], [
  ["Alembic", "Ferramenta que registra e aplica mudanças na estrutura do banco de dados"],
  ["API", "Interface pela qual um programa usa serviços de outro; aqui, a forma de enviar textos ao modelo da OpenAI e de buscar questões do ENEM"],
  ["Baseline", "Método simples usado como referência de comparação nos resultados"],
  ["Branch", "Linha paralela de desenvolvimento no Git, que não afeta a principal até ser incorporada"],
  ["Cache de prompt", "Reaproveitamento, pela OpenAI, de trechos iniciais repetidos entre requisições, cobrados mais barato"],
  ["Commit", "Registro de um conjunto de mudanças no histórico do Git"],
  ["CSV", "Arquivo de texto com valores separados por vírgula, aberto por planilhas e pelo pandas"],
  ["Embeddings", "Representações numéricas do significado de um texto, usadas para medir semelhança"],
  ["FastAPI", "Biblioteca Python para construir aplicações web"],
  ["HTR", "Reconhecimento de texto manuscrito (do inglês Handwritten Text Recognition)"],
  ["JSON", "Formato de texto para dados estruturados em campos e valores"],
  ["Latência", "Tempo entre o envio da requisição e a chegada da resposta completa"],
  ["Migração", "Arquivo que descreve uma mudança na estrutura do banco e permite aplicá-la de forma repetível"],
  ["Prompt", "Texto de instrução enviado ao modelo de linguagem"],
  ["Rota", "Endereço da aplicação web associado a uma ação, como `GET /questoes`, que lista as questões"],
  ["Pull request", "Pedido para incorporar uma branch à principal, com espaço para revisão e comentários"],
  ["Pydantic", "Biblioteca que valida se dados têm os campos e tipos esperados"],
  ["Saída estruturada", "Recurso da API que obriga o modelo a responder em JSON com um formato definido"],
  ["SQLAlchemy", "Biblioteca que permite manipular tabelas do banco como classes Python"],
  ["SQLite", "Banco de dados guardado em um único arquivo, sem servidor"],
  ["Token", "Unidade de texto (em geral parte de uma palavra) usada pela API para contar e cobrar o uso"],
], [3, 7]);

// ---------------------------------------------------------------------
h1("10. Histórico de versões");
tabela(["Data", "Versão", "Referência", "Mudança"], [
  ["19/10/2026", "0.3", "pull request da etapa 2", "Módulo objetivo: contrato de saída, conferência com o gabarito, prompt objetiva_v1, páginas de lista, cadastro, detalhe e geração da explicação"],
  ["19/10/2026", "0.2", "pull request de revisão", "Novas tentativas automáticas desligadas; caminho do banco sem dependência da pasta; limite de tentativas no importador; primeira versão desta documentação"],
  ["16/10/2026", "0.1.1", "commit 18da774", "Importador de questões do ENEM"],
  ["16/10/2026", "0.1", "commit 374eeba", "Etapa 1: esqueleto, banco de dados e medição"],
], [2, 1.6, 3, 5.4]);

// ---------------------------------------------------------------------
h1("11. Referências");
marcadores([
  "Especificação do Protótipo, TCC II (documento interno do projeto).",
  "OPENAI. Pricing. Disponível em: https://developers.openai.com/api/docs/pricing. Acesso em: 15 out. 2026.",
  "OPENAI. Structured model outputs. Disponível em: https://developers.openai.com/api/docs/guides/structured-outputs. Acesso em: 15 out. 2026.",
  "ENEM API. Documentação. Disponível em: https://docs.enem.dev/introduction. Acesso em: 16 out. 2026.",
]);

// =====================================================================
// DOCUMENTO
// =====================================================================
const documento = new Document({
  creator: "Felipe Vidal Cominetti",
  title: "Documentação Técnica do Protótipo",
  styles: {
    default: { document: { run: { font: FONTE, size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: FONTE, color: COR_TITULO },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0, keepNext: true, keepLines: true } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: FONTE, color: COR_TITULO },
        paragraph: { spacing: { before: 280, after: 140 }, outlineLevel: 1, keepNext: true, keepLines: true } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 23, bold: true, font: FONTE, color: "404040" },
        paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 2, keepNext: true, keepLines: true } },
    ],
  },
  numbering: {
    config: [
      { reference: "marcadores", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•",
        alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
      ...listasNumeradas.map((reference) => ({
        reference,
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 540, hanging: 360 } } } }],
      })),
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 },
        margin: { top: 1701, bottom: 1134, left: 1701, right: 1134 },
      },
      titlePage: true,
    },
    headers: {
      default: new Header({ children: [new Paragraph({
        alignment: AlignmentType.RIGHT,
        children: [new TextRun({ text: `Documentação Técnica do Protótipo, versão ${VERSAO}`, size: 18, color: COR_DISCRETA })],
      })] }),
    },
    footers: {
      default: new Footer({ children: [new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [
          new TextRun({ text: "Página ", size: 18, color: COR_DISCRETA }),
          new TextRun({ children: [PageNumber.CURRENT], size: 18, color: COR_DISCRETA }),
          new TextRun({ text: " de ", size: 18, color: COR_DISCRETA }),
          new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 18, color: COR_DISCRETA }),
        ],
      })] }),
    },
    children: conteudo,
  }],
});

const saida = path.join(__dirname, "..", "Documentacao_Tecnica.docx");
Packer.toBuffer(documento).then((buffer) => {
  fs.writeFileSync(saida, buffer);
  console.log(`Gerado: ${saida}`);
});
