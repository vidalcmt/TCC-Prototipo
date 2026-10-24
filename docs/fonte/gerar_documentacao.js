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
const VERSAO = "0.12";
const DATA = "24/10/2026";

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
    ["Tela de aceite ou ajuste da nota pelo professor", "Cadastro aberto: as contas são criadas pelo administrador"],
    ["Registro de métricas e exportação em CSV", ""],
    ["Login com contas individuais, papéis e limite diário de chamadas", ""],
    ["Atividades montadas pelo professor, impressas em folha A4", ""],
    ["Comparação com um método de similaridade de textos (baseline)", ""],
  ],
  [1, 1],
);

h2("1.4 Situação atual");
tabela(
  ["Etapa", "Conteúdo", "Situação"],
  [
    ["1", "Esqueleto, banco de dados e medição", "Concluída em 16/10/2026"],
    ["2", "Módulo objetivo", "Concluída em 19/10/2026; explicação v2 (tipo de erro) em 21/10/2026; v3 (explicação única e pistas) em 24/10/2026"],
    ["3", "Módulo discursivo", "Implementada em 21/10/2026; versão 2 do prompt e questões com itens em 23/10/2026, após o teste piloto"],
    ["4", "Tela de aceite do professor", "Implementada em 22/10/2026; aguardando revisão"],
    ["Apoio", "Login, contas, página inicial e novo visual com tema escuro", "Implementado em 23/10/2026; aguardando revisão"],
    ["Apoio", "Publicação no Google Cloud", "Pendente; depende do login"],
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
    ["Visual", "CSS próprio, sem biblioteca de componentes", "Poucas páginas; um arquivo de estilo com cores em variáveis permite o tema claro e o escuro sem dependência extra."],
    ["Login", "Sessão em cookie assinado (Starlette) e senhas com scrypt", "Ambos vêm prontos com o FastAPI e com o Python; nenhuma biblioteca de autenticação a mais para manter."],
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
    ["`app/main.py`", "Aplicação web: junta as rotas, aplica o login e trata os avisos de acesso"],
    ["`app/inicio.py`", "Página inicial e lista de correções que esperam revisão"],
    ["`app/contas/`", "Senhas (`senhas.py`), sessão e permissões (`sessao.py`), regras das contas (`servico.py`) e páginas de entrar, trocar senha e usuários (`router.py`)"],
    ["`app/config.py`", "Leitura das configurações do arquivo .env"],
    ["`app/database.py`", "Conexão com o banco e abertura de sessões"],
    ["`app/models.py`", "Definição das treze tabelas do banco"],
    ["`app/correcao/`", "Chamada ao modelo (`llm.py`), prompts (`prompts.py`), contratos de saída (`contratos.py`), explicação de objetivas (`objetiva.py`) e correção de discursivas (`discursiva.py`)"],
    ["`app/metricas/`", "Cálculo de custo (`precos.py`), números do artigo (`resumo.py`), página e exportações (`router.py`)"],
    ["`app/questoes/`", "Páginas de questões: lista dos dois tipos e objetivas (`router.py`), discursivas e respostas (`discursivas.py`), cliente do modelo para as rotas (`cliente.py`)"],
    ["`app/revisao/`", "Aceite ou ajuste da nota pelo professor: regra (`servico.py`) e rota (`router.py`)"],
    ["`app/atividades/`", "Atividades: montagem de conjuntos de questões e folha de impressão em A4 (`router.py`)"],
    ["`app/templates/`", "Páginas HTML; `base.html` tem a barra de navegação e `_macros.html` os elementos repetidos, como a nota circulada"],
    ["`app/static/`", "Estilo (`estilo.css`), script do tema e do menu (`app.js`) e fontes com as suas licenças"],
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
p("O banco tem treze tabelas. As oito primeiras foram criadas pela migração inicial do Alembic, a tabela `usuario` por uma migração própria, que também ligou revisões e chamadas ao usuário que as fez, as tabelas `item_questao` e `resposta_item` pela migração dos itens das discursivas, e as tabelas `atividade` e `atividade_questao` pela migração das atividades. Duas delas existem por razão metodológica e não devem ser simplificadas: `revisao_professor`, que guarda a nota sugerida e a nota final lado a lado e permite calcular a concordância, e `metrica_requisicao`, que registra também as falhas, porque a taxa de falha é um resultado da pesquisa.");
tabela(
  ["Tabela", "Finalidade"],
  [
    ["`questao`", "Enunciado, tipo, área, origem e nota máxima"],
    ["`alternativa`", "As cinco alternativas de uma questão objetiva e qual é a correta"],
    ["`criterio_rubrica`", "Critérios de correção de uma discursiva, com peso (opcional)"],
    ["`resposta_esperada`", "Resposta de referência de uma discursiva (opcional)"],
    ["`item_questao`", "Itens de uma discursiva (a, b, c), cada um com o seu comando (opcional)"],
    ["`resposta_item`", "Resposta do aluno a cada item, em questão com itens"],
    ["`atividade`", "Conjunto de questões montado pelo professor para uma turma"],
    ["`atividade_questao`", "Questões de uma atividade, na ordem escolhida"],
    ["`submissao`", "Resposta de um aluno ou do corpus a uma questão"],
    ["`correcao`", "Saída do modelo para uma submissão"],
    ["`revisao_professor`", "Decisão do professor sobre a nota sugerida"],
    ["`metrica_requisicao`", "Números de cada chamada ao modelo"],
    ["`usuario`", "Pessoas que podem entrar no sistema, com papel e situação"],
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
campos("item_questao", [
  ["`id`", "inteiro", "Identificador"],
  ["`questao_id`", "inteiro", "Questão a que pertence"],
  ["`letra`", "texto", "De a a e; única dentro da questão"],
  ["`enunciado`", "texto", "Comando do item"],
]);
campos("criterio_rubrica", [
  ["`id`", "inteiro", "Identificador"],
  ["`questao_id`", "inteiro", "Questão a que pertence"],
  ["`item_id`", "inteiro", "Item a que o critério se refere; vazio em questão sem itens ou em critério que vale para a resposta inteira"],
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
  ["`resposta_aluno`", "texto", "Resposta discursiva. Em questão com itens, o texto completo, com cada item identificado pela letra e os itens vazios marcados como \"(em branco)\""],
  ["`alternativa_escolhida`", "texto", "Letra escolhida, nas objetivas"],
  ["`codigo_corpus`", "texto", "Código anônimo da resposta no corpus, por exemplo `R014`"],
  ["`origem`", "texto", "`autor`, `voluntario` ou `especialista`; usada como variável de análise"],
  ["`criado_em`", "data e hora", "Momento do registro"],
]);
campos("resposta_item", [
  ["`id`", "inteiro", "Identificador"],
  ["`submissao_id`", "inteiro", "Resposta a que pertence"],
  ["`item_id`", "inteiro", "Item respondido; único dentro da resposta"],
  ["`texto`", "texto", "Resposta do aluno ao item; vazio quando o item ficou em branco"],
]);
campos("atividade", [
  ["`id`", "inteiro", "Identificador"],
  ["`titulo`", "texto", "Nome da atividade, por exemplo \"Revisão de Geografia\""],
  ["`turma`", "texto", "Turma a que se destina (opcional)"],
  ["`instrucoes`", "texto", "Instruções impressas no topo da folha do aluno (opcional)"],
  ["`usuario_id`", "inteiro", "Quem criou a atividade"],
  ["`criado_em`", "data e hora", "Momento da criação"],
]);
campos("atividade_questao", [
  ["`id`", "inteiro", "Identificador"],
  ["`atividade_id`", "inteiro", "Atividade"],
  ["`questao_id`", "inteiro", "Questão incluída; a mesma questão aparece no máximo uma vez em cada atividade, mas pode estar em várias atividades"],
  ["`ordem`", "inteiro", "Posição da questão na folha"],
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
  ["`correcao_id`", "inteiro", "Correção revisada; única, pois cada correção recebe no máximo uma revisão"],
  ["`usuario_id`", "inteiro", "Quem decidiu (vazio nas revisões anteriores ao login)"],
  ["`nota_sugerida`", "decimal", "Cópia da nota do modelo no momento da revisão"],
  ["`nota_final`", "decimal", "Nota atribuída pelo professor"],
  ["`aceitou_sugestao`", "verdadeiro ou falso", "Calculado: as duas notas são iguais"],
  ["`comentario`", "texto", "Justificativa do professor (opcional)"],
  ["`criado_em`", "data e hora", "Momento da revisão"],
]);
campos("metrica_requisicao", [
  ["`id`", "inteiro", "Identificador"],
  ["`correcao_id`", "inteiro", "Correção gerada (vazio quando a chamada falha)"],
  ["`questao_id`", "inteiro", "Questão que originou a chamada, gravada também nas falhas. Nas chamadas antigas, preenchida a partir da correção; falhas antigas ficam sem origem"],
  ["`submissao_id`", "inteiro", "Resposta do aluno que originou a chamada, nas discursivas"],
  ["`usuario_id`", "inteiro", "Quem pediu a chamada (vazio nas chamadas por linha de comando e nas anteriores ao login); usado no limite diário"],
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
campos("usuario", [
  ["`id`", "inteiro", "Identificador"],
  ["`nome`", "texto", "Nome exibido nas páginas e nas revisões"],
  ["`email`", "texto", "Usado para entrar; único e guardado em minúsculas"],
  ["`senha_resumo`", "texto", "Resumo criptográfico da senha (scrypt); a senha em si nunca é gravada"],
  ["`papel`", "texto", "`admin` ou `avaliador`"],
  ["`ativo`", "verdadeiro ou falso", "Conta desativada não entra e perde a sessão aberta"],
  ["`precisa_trocar_senha`", "verdadeiro ou falso", "Verdadeiro enquanto a senha for a provisória"],
  ["`criado_em`", "data e hora", "Momento da criação da conta"],
  ["`ultimo_acesso`", "data e hora", "Último login com sucesso"],
]);

// ---------------------------------------------------------------------
h1("4. Módulos e funções");

h2("4.1 Configuração: app/config.py");
tabela(["Elemento", "O que faz"], [
  ["`RAIZ`", "Caminho absoluto da pasta do projeto, usado para achar arquivos independentemente de onde o comando é rodado"],
  ["`Configuracao`", "Lê do arquivo .env a chave da API, o modelo, o banco e as opções de login listadas na seção 5.1, com valores padrão"],
  ["`FUSO`", "Fuso usado nas datas exibidas e na virada do dia do limite diário: `America/Sao_Paulo`"],
  ["`config`", "Instância única das configurações, importada pelos outros módulos. Sem `SECRET_KEY`, gera uma chave temporária e avisa no terminal"],
], [4, 6]);

h2("4.2 Banco de dados: app/database.py");
tabela(["Elemento", "O que faz"], [
  ["`Base`", "Classe da qual todas as tabelas herdam"],
  ["`engine`", "Conexão com o arquivo SQLite"],
  ["`SessionLocal`", "Fábrica de sessões; cada sessão é uma conversa com o banco"],
  ["`obter_sessao()`", "Abre uma sessão por requisição web e a fecha ao final, mesmo em caso de erro"],
], [4, 6]);

h2("4.3 Prompts: app/correcao/prompts.py");
p("Cada prompt é um arquivo em `prompts/<nome>/v<N>.md`. A linha `---usuario---` separa a instrução de sistema, que define o papel do modelo, da mensagem do usuário, que leva os dados da questão. Campos entre chaves, como `{enunciado}`, são preenchidos na hora da chamada, nas duas partes. Por isso, o texto de um prompt não pode ter chaves que não sejam campos.");
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
  ["`usuario_id`", "Quem pediu a chamada, gravado na métrica"],
  ["`questao_id`, `submissao_id`", "Origem da chamada, gravada na métrica antes do envio, para que também as falhas fiquem ligadas à questão e à resposta"],
], [4, 6]);
h3("Por que as novas tentativas automáticas estão desligadas");
p("Por padrão, a biblioteca da OpenAI repete uma chamada que falhou até duas vezes, sem avisar. Com isso, a latência medida somaria várias tentativas e uma falha intermediária desapareceria dos dados. Com `max_retries=0`, cada linha de `metrica_requisicao` corresponde a exatamente uma tentativa. Quando for preciso tentar de novo, como na execução em lote, o código chama outra vez e a nova tentativa vira outra linha.");

h2("4.5 Contrato de saída objetivo: app/correcao/contratos.py");
p("Define, em Pydantic, o formato que a API é obrigada a seguir na resposta, conforme a seção \"Contrato de saída da IA\" da especificação. As descrições dos campos são enviadas junto com o formato e orientam o modelo. Cada versão de prompt tem o seu contrato, registrado em `CONTRATO_POR_PROMPT`; as versões antigas permanecem no código para que as correções já gravadas continuem legíveis.");
tabela(["Elemento", "O que faz"], [
  ["`ExplicacaoAlternativa`, `CorrecaoObjetiva`", "Versão 1 (prompt `objetiva_v1`): por alternativa, `letra`, `correta`, `por_que` e `conceito_envolvido`"],
  ["`ExplicacaoAlternativaV2`, `CorrecaoObjetivaV2`", "Versão 2 (prompt `objetiva_v2`): acrescenta `tipo_de_erro`, `elemento_incorreto` e `como_verificar` a cada alternativa"],
  ["`ExplicacaoAlternativaV3`, `CorrecaoObjetivaV3`", "Versão 3 (prompt `objetiva_v3`, em uso): uma `explicacao` única e uma `pista` opcional por alternativa, e uma `pista_do_enunciado` para a questão"],
  ["Campos comuns da resposta", "`questao_id`, `alternativa_correta`, lista de `explicacoes`, `explicacao_correta` e `nivel_dificuldade_estimado` (baixo, medio ou alto)"],
  ["`ROTULOS_TIPO_DE_ERRO`", "Texto exibido na página para cada tipo de erro"],
  ["`CONTRATO_POR_PROMPT`", "Associa cada versão de prompt ao seu contrato"],
  ["`problemas_de_consistencia(...)`", "Confere a resposta com a questão cadastrada e devolve a lista de problemas; lista vazia significa resposta consistente"],
], [4, 6]);
p("O formato já é garantido pela API. A conferência verifica o conteúdo: a resposta precisa repetir o identificador da questão, concordar com o gabarito do professor, explicar cada alternativa exatamente uma vez e marcar como correta apenas a alternativa do gabarito.");
p("Nas versões 2 e 3, a conferência também exige que só as alternativas incorretas tenham `tipo_de_erro`; a correta deve vir com esse campo vazio. Na versão 3, a correta também não pode ter pista para eliminá-la.");
h3("Campos da versão 3");
p("A versão 3 nasceu da avaliação do autor de que a v2 era cansativa de ler: três blocos de texto por alternativa (\"O que está errado\", \"Por quê\" e \"Como perceber sem o gabarito\"). Ela junta os dois primeiros numa explicação curta e troca o terceiro por pistas de conteúdo que ajudam o estudante a resolver mais depressa, já que no vestibular o tempo conta.");
tabela(["Campo", "Conteúdo"], [
  ["`pista_do_enunciado`", "Da questão: a palavra, expressão ou dado do enunciado que indica o caminho da resolução e o que ele sinaliza. Exemplo: uma quantidade que se repete a cada dia, ao longo de vários dias, indica multiplicação"],
  ["`explicacoes[].tipo_de_erro`", "O mesmo da versão 2, exibido como etiqueta ao lado da explicação"],
  ["`explicacoes[].explicacao`", "Em até duas frases: o que está errado e por quê, ou, na correta, por que ela é a resposta"],
  ["`explicacoes[].pista`", "Só nas incorretas e só quando existir: a pista de conteúdo que permite eliminar a alternativa sem saber a resposta, como um elemento de outra época ou sistema. Exemplo: relações feudais numa questão sobre monarquia absolutista"],
  ["`explicacoes[].conceito_envolvido`", "O mesmo das versões anteriores"],
], [3, 7]);
p("O prompt proíbe pistas genéricas de prova, que não dependem do conteúdo, como o tamanho da alternativa, palavras absolutas (\"sempre\", \"nunca\") ou a posição da letra. Também permite deixar a pista vazia, para não forçar o modelo a inventar uma.");
h3("Campos da versão 2 por alternativa");
tabela(["Campo", "Na alternativa incorreta", "Na alternativa correta"], [
  ["`tipo_de_erro`", "A natureza do erro, escolhida na lista abaixo", "Vazio"],
  ["`elemento_incorreto`", "O ponto exato que está errado: data, período, autor, lugar, conceito ou relação", "Vazio"],
  ["`por_que`", "O raciocínio que leva o estudante a escolhê-la e por que ele não se sustenta", "Por que ela é a mais adequada"],
  ["`como_verificar`", "Como perceber o erro com outros conhecimentos, sem depender do gabarito", "Como confirmá-la com outros conhecimentos"],
  ["`conceito_envolvido`", "Conceito central, em 2 a 6 palavras", "Idem"],
], [3, 5, 3]);
h3("Tipos de erro");
tabela(["Valor", "Significado"], [
  ["`anacronismo`", "Atribui algo a uma época ou data que não é a sua, como características da arte contemporânea ao Modernismo de 1922"],
  ["`contexto_historico`", "Situa o fato em um contexto social, político ou geográfico errado"],
  ["`conceito_trocado`", "Confunde conceitos próximos, como indianismo romântico e antropofagia modernista"],
  ["`leitura_parcial`", "Apoia-se em parte do texto e ignora outra"],
  ["`extrapolacao`", "Afirma mais do que o texto permite"],
  ["`causa_efeito`", "Inverte ou inventa uma relação de causa e consequência"],
  ["`fato_incorreto`", "Afirma dado, autor ou evento falso"],
  ["`nao_responde`", "É verdadeira em si, mas não responde ao que foi perguntado"],
  ["`outro`", "Nenhuma das categorias anteriores"],
], [3, 7]);
p("Os campos `conceito_envolvido` e `tipo_de_erro` existem por razão metodológica: permitem agrupar os erros por conceito e contar quais tipos de erro os distratores exploram, o que alimenta a análise dos resultados.");

h2("4.6 Explicação de questões objetivas: app/correcao/objetiva.py");
tabela(["Elemento", "O que faz"], [
  ["`PROMPT_OBJETIVA`", "Prompt em uso: `objetiva`, versão 3. O contrato é escolhido pela versão"],
  ["`gabarito_da(questao)`", "Devolve a letra correta; recusa questão sem gabarito ou com mais de um"],
  ["`campos_do_prompt(questao)`", "Prepara identificador, enunciado, alternativas no formato `A) texto` e gabarito"],
  ["`gerar_explicacao(sessao, questao)`", "Chama o modelo, confere a resposta e grava a correção"],
  ["`ResultadoExplicacao`", "Agrupa a correção gravada (ou nada, na falha) e a métrica da chamada"],
], [4, 6]);
h3("Passos de gerar_explicacao");
numerada([
  "Carrega o prompt em uso (`objetiva_v3`) e chama `chamar_modelo` com o contrato da mesma versão (`CorrecaoObjetivaV3`).",
  "Se a chamada falhou, devolve a falha; a métrica já foi gravada por `chamar_modelo`.",
  "Se a resposta veio, confere a consistência com a questão.",
  "Se houver problema, não grava a correção, marca a métrica como falha e registra o motivo, por exemplo `saida inconsistente: alternativa_correta B diferente do gabarito D`.",
  "Se estiver tudo certo, grava a correção em `correcao` e liga a métrica a ela pelo campo `correcao_id`.",
]);
p("A explicação de uma objetiva pertence à questão, e não à resposta de um aluno. Por isso, nessas correções, o campo `submissao_id` fica vazio.");
h3("Prompt objetiva_v3 (em uso)");
p("O texto fica em `prompts/objetiva/v3.md`. Em resumo, ele instrui o modelo a:");
marcadores([
  "nunca questionar ou alterar o gabarito informado pelo professor;",
  "apontar a pista do enunciado que indica o caminho da resolução;",
  "explicar cada alternativa em até duas frases, juntando o que está errado e por quê;",
  "dar, quando houver, uma pista de conteúdo para eliminar cada alternativa incorreta, sem pistas genéricas de prova e sem forçar uma pista quando ela não existir;",
  "descrever o caminho até a resposta em até quatro passos curtos;",
  "afirmar numa pista só o que é verdadeiro para aquela questão, e não inventar dados, datas, autores ou citações.",
]);
p("Na página da questão, a pista do enunciado aparece num quadro antes das alternativas. Em cada alternativa aparecem a etiqueta do tipo de erro, a explicação e, quando houver, a pista para eliminar. Explicações geradas com as versões 1 e 2 continuam exibidas no formato original.");
h3("Prompt objetiva_v2 (substituído)");
p("O texto fica em `prompts/objetiva/v2.md`. A versão 1 continua em `prompts/objetiva/v1.md`. Nenhuma das duas é mais alterada. Em resumo, a versão 2 instrui o modelo a:");
marcadores([
  "nunca questionar ou alterar o gabarito informado pelo professor;",
  "para cada alternativa incorreta, classificar o tipo de erro, apontar o elemento exato que está errado e explicar o raciocínio plausível que levaria um estudante a escolhê-la (RF02 e RF03);",
  "mostrar como o estudante poderia perceber o erro por outros conhecimentos: o período ou contexto correto e suas características, o significado preciso dos conceitos confundidos ou o trecho do enunciado que contradiz a alternativa;",
  "usar o período (década, século, movimento) em vez de um ano quando não houver segurança sobre a data;",
  "para a correta, apontar os elementos do enunciado que a sustentam, e descrever em passos o caminho até a resposta;",
  "não inventar dados, autores ou citações fora do enunciado;",
  "escrever em português do Brasil, dirigido ao estudante, sem expressões como \"obviamente\".",
]);

h2("4.7 Páginas de questões: app/questoes/router.py");
tabela(["Rota", "O que faz"], [
  ["`GET /questoes`", "Lista todas as questões, objetivas e discursivas, 50 por página, com origem, área, início do enunciado e número de correções. Aceita os filtros `busca` (palavra no enunciado), `numero`, `tipo`, `area`, `fonte`, `ano` e `situacao` (`pendente`: tem correção esperando revisão; `sem_correcao`: nenhuma correção ainda) e o parâmetro `pagina`. As opções de área, origem e ano vêm do próprio banco, e os filtros se mantêm ao trocar de página"],
  ["`GET /questoes/nova`", "Formulário de cadastro manual (RF01)"],
  ["`POST /questoes`", "Valida e grava a questão: enunciado, as cinco alternativas e exatamente uma correta. Com erro, devolve o formulário preenchido e a lista de problemas"],
  ["`GET /questoes/{id}`", "Enunciado, alternativas com o gabarito destacado e, se existir, a explicação mais recente: tipo de erro, o que está errado, por quê, como perceber sem o gabarito, além de modelo, prompt, tempo e custo. Cada explicação é lida com o contrato da versão que a gerou"],
  ["`POST /questoes/{id}/explicar`", "Gera uma nova explicação e volta para a página da questão; na falha, a página mostra o motivo e o número da métrica"],
], [4, 6]);
p("A função `obter_cliente_llm` fornece o cliente do modelo às rotas. Nos testes, ela é trocada por um cliente falso, o que permite testar as páginas sem gastar crédito.");

h2("4.8 Contrato de saída discursivo");
p("Também em `app/correcao/contratos.py`. A versão 1 (`CorrecaoDiscursiva`) segue o formato da especificação; a versão 2 (`CorrecaoDiscursivaV2`), em uso, acrescenta os campos descritos adiante. Os campos `trecho_citado` e `usou_resposta_esperada` existem por razão metodológica: o primeiro distingue feedback específico de feedback genérico, e a proporção de critérios com trecho citado é métrica de qualidade; o segundo separa as duas condições experimentais na análise.");
tabela(["Campo", "Conteúdo"], [
  ["`questao_id`", "Identificador da questão"],
  ["`usou_resposta_esperada`", "Condição em que a correção rodou"],
  ["`analise_criterios`", "Lista com `criterio`, `peso`, `status` (atendido, parcial ou nao_atendido), `justificativa` e `trecho_citado`"],
  ["`feedback_elaborado`", "Texto ao aluno: o que faltou e o caminho para a resposta completa"],
  ["`nota_sugerida`, `nota_maxima`", "Nota proposta e nota máxima da questão"],
  ["`confianca`", "baixa, media ou alta"],
], [3, 7]);
h3("Campos acrescentados na versão 2");
tabela(["Campo", "Conteúdo"], [
  ["`analise_criterios[].item`", "Letra do item a que o critério se refere, ou nulo em questão sem itens e em critério que vale para a resposta inteira"],
  ["`motivo_confianca`", "Uma frase com o motivo do nível de confiança"],
], [3, 7]);
p("Na versão 2, a análise por critério é dirigida ao professor e pode citar o conteúdo esperado, porque é com ela que o professor confere a nota. O feedback é dirigido ao aluno e não pode conter esse conteúdo. A confiança passou a medir só a certeza sobre a nota, e não a qualidade da resposta.");
h3("Conferência da correção discursiva");
p("A função `problemas_da_discursiva` recusa a correção, que então conta como falha, quando:");
marcadores([
  "o identificador da questão é diferente;",
  "a condição informada pelo modelo não é a condição executada;",
  "a nota máxima é diferente da cadastrada, ou a nota sugerida fica fora do intervalo de zero à nota máxima;",
  "nenhum critério é analisado;",
  "há rubrica e o número de critérios ou os pesos são diferentes dos do professor;",
  "algum trecho citado não existe na resposta do aluno.",
]);
p("Na versão 2, a correção também é recusada quando:");
marcadores([
  "um critério é ligado a um item que a questão não tem, ou a qualquer item numa questão sem itens;",
  "há rubrica e os itens dos critérios são diferentes dos itens definidos pelo professor;",
  "o trecho citado em um critério ligado a um item não existe na resposta daquele item. Assim, um trecho do item a não serve de evidência para o item c, e um item em branco não pode ter trecho citado;",
  "a nota sugerida não corresponde à conta feita a partir dos pesos e dos status dos critérios. A função `nota_pelos_criterios` refaz a conta; quando o valor exato fica no meio de dois múltiplos de 0,5, os dois arredondamentos são aceitos.",
]);
p("A função `trecho_existe` confere os trechos citados. Ela ignora diferenças de maiúsculas, aspas e espaços e aceita trechos com reticências no meio, desde que cada parte exista na resposta e na mesma ordem. Uma paráfrase, ou um trecho inventado, é recusada.");

h2("4.9 Correção discursiva: app/correcao/discursiva.py");
tabela(["Elemento", "O que faz"], [
  ["`PROMPT_DISCURSIVA`", "Prompt em uso: `discursiva`, versão 2"],
  ["`compor_resposta(pares)`", "Monta o texto completo de uma resposta por itens, com cada item identificado pela letra e os vazios marcados como \"(em branco)\""],
  ["`campos_do_prompt(questao, submissao, usar)`", "Prepara enunciado, itens, nota máxima, rubrica numerada com pesos e itens, resposta esperada ou o aviso de que não há, resposta do aluno por item e a condição"],
  ["`gerar_correcao(sessao, submissao, usar)`", "Corrige a resposta em uma das duas condições, confere e grava a correção ligada à resposta e à métrica"],
  ["`CondicaoIndisponivel`", "Erro quando se pede a condição com resposta esperada para questão que não tem uma; nada é enviado ao modelo"],
], [4, 6]);
p("Na condição sem resposta esperada, o texto da resposta esperada não é enviado de forma alguma; o campo recebe apenas o aviso de que ela não foi informada. As duas condições usam o mesmo prompt, e só o conteúdo dos campos muda, o que torna a comparação justa.");
h3("Prompt discursiva_v2 (em uso)");
p("O texto fica em `prompts/discursiva/v2.md`. Ele foi escrito depois do teste piloto do autor com a questão 01 de História da Fuvest 2025, no qual a versão 1 mostrou quatro problemas causados pelas próprias regras do prompt.");
tabela(["Problema observado na v1", "Causa na v1", "Regra na v2"], [
  ["O feedback entregava a resposta (\"retome o conceito de Inquisição\")", "A regra 9 mandava indicar os conceitos e fatos que o aluno poderia mobilizar", "O feedback pode repetir o que o enunciado pede, que o aluno já conhece, mas não o conteúdo que atende ao pedido; orienta com trechos a reler e perguntas"],
  ["O feedback cobrava conteúdo que o gabarito não pede (autoridades civis)", "A regra 9 mandava mostrar o caminho para a resposta completa, sem limite", "O feedback só cobra o que algum critério da rubrica exige; sem rubrica, só o que o enunciado pede"],
  ["Confiança baixa numa resposta curta e claramente errada", "A regra 8 associava confiança baixa a resposta curta ou fora do tema, misturando qualidade da resposta e certeza da nota", "A confiança mede a certeza sobre a nota, com os três níveis definidos, e vem acompanhada de um motivo"],
  ["A análise por critério revelava o gabarito", "Não era um erro: a análise é do professor. Faltava deixar isso explícito", "A saída declara dois leitores: a análise, para o professor, pode citar o conteúdo esperado; o feedback, para o aluno, não pode"],
], [3, 3, 4]);
p("A v2 também trata os itens: avalia a evidência de cada critério só na resposta do item indicado, considera não atendidos os critérios de um item em branco e organiza o feedback por item. Ela informa ao modelo que o sistema refaz a conta da nota.");
h3("Prompt discursiva_v1 (substituído)");
p("O texto fica em `prompts/discursiva/v1.md` e continua no repositório, porque as correções feitas com ele no teste piloto apontam para esta versão. Em resumo, ele instrui o modelo a:");
marcadores([
  "com rubrica, avaliar exatamente os critérios e pesos do professor, na mesma ordem; sem rubrica, definir de 3 a 5 critérios;",
  "copiar literalmente o trecho da resposta do aluno que sustenta cada avaliação (RF06);",
  "calcular a nota pelos pesos: critério atendido vale o peso inteiro, parcial vale metade e não atendido vale zero, arredondando para múltiplo de 0,5 (RF07);",
  "escrever o feedback ao aluno reconhecendo o que ele acertou e mostrando o caminho para a resposta completa, sem entregá-la pronta;",
  "não inventar dados, datas, autores ou citações.",
]);

h2("4.10 Páginas de discursivas: app/questoes/discursivas.py");
tabela(["Rota", "O que faz"], [
  ["`GET /questoes/nova-discursiva`", "Formulário de cadastro: enunciado, itens, nota máxima, resposta esperada e rubrica opcionais (RF04)"],
  ["`POST /questoes/discursivas`", "Valida e grava. Linhas de rubrica vazias são ignoradas; linha só com critério ou só com peso é erro. Itens devem ser preenchidos em ordem e ser pelo menos dois; um critério só pode apontar para um item preenchido"],
  ["`GET /questoes/{id}`", "Para questão discursiva: itens, resposta esperada, rubrica com o item de cada critério, lista de respostas e formulário de nova resposta, com um campo por item quando houver"],
  ["`POST /questoes/{id}/respostas`", "Registra a resposta de um aluno com código anônimo e origem (RF05). Em questão com itens, grava a resposta de cada item e o texto completo; pelo menos um item precisa estar preenchido"],
  ["`GET /respostas/{id}`", "Resposta do aluno, botões de correção nas duas condições e todas as correções já feitas, da mais recente para a mais antiga"],
  ["`POST /respostas/{id}/corrigir`", "Corrige na condição escolhida (`com` ou `sem`) e volta para a página da resposta"],
], [4, 6]);
p("Na página da resposta, a nota aparece com o rótulo \"Nota sugerida pelo modelo\" e o aviso de que a nota final é do professor (RF07), junto com o nível e o motivo da confiança. A análise por critério leva o rótulo \"para o professor\" e o feedback, \"para o aluno\". Cada critério mostra o item, o status, a justificativa e o trecho citado. Em questão com itens, a resposta do aluno aparece item por item, com o comando de cada um. Aceitar ou ajustar a nota é a etapa 4.");
h3("Questões com itens");
p("Provas como a da Fuvest têm um texto-base e vários itens (a, b, c), cada um com o seu comando. O cadastro aceita até cinco itens, e a resposta do aluno tem um campo por item. A nota e a decisão do professor continuam valendo para a questão inteira, como na correção da Fuvest, que soma os itens. Ligar cada critério da rubrica a um item permite ao sistema conferir se o trecho citado veio da resposta certa.");

h2("4.11 Revisão do professor: app/revisao/");
p("Materializa os requisitos RF09 a RF11: a nota sugerida só vira nota final quando o professor a aceita ou informa outra, e as duas ficam gravadas lado a lado.");
tabela(["Elemento", "O que faz"], [
  ["`registrar_revisao(sessao, correcao, nota_final, comentario)`", "Grava a decisão. Recusa correção sem nota sugerida, correção já revisada e nota fora do intervalo de zero à nota máxima"],
  ["`revisao_da(sessao, correcao_id)`", "Devolve a revisão de uma correção, se houver"],
  ["`RevisaoInvalida`", "Erro com a mensagem exibida ao professor"],
  ["`POST /correcoes/{id}/revisao`", "Recebe a ação `aceitar` ou `ajustar`, a nota e o comentário, e volta para a página da resposta"],
], [4, 6]);
h3("Regras");
marcadores([
  "**Uma revisão por correção:** garantida pela regra e também pelo banco, com uma restrição de unicidade. Assim, nem um clique duplo grava duas decisões.",
  "**Decisão definitiva:** a revisão não é alterada depois. A decisão registrada é o dado da pesquisa.",
  "**Aceite calculado:** `aceitou_sugestao` é calculado comparando as duas notas, e não informado pela tela. Digitar a mesma nota sugerida também conta como aceite.",
  "**Proteção contra aceite por engano:** na tela, o botão acionado pela tecla Enter é o de registrar outra nota. Clicar em aceitar com outra nota digitada é recusado, com uma mensagem que explica o que fazer.",
]);
h3("Na página da resposta");
p("Cada correção mostra a nota sugerida e, ao lado, a nota final: \"Pendente\" até a decisão, depois a nota do professor, indicando se a sugestão foi aceita ou ajustada (por exemplo, \"Ajustada de 6,5 para 7,5 (+1)\"). O formulário de decisão fica no fim da correção, depois da análise por critério e do feedback, para que o professor leia a justificativa antes de decidir.");

h2("4.12 Custo: app/metricas/precos.py");
tabela(["Elemento", "O que faz"], [
  ["`Preco`", "Preços de um modelo: entrada, entrada em cache, gravação em cache e saída"],
  ["`carregar_tabela()`", "Lê `config/precos.toml` uma vez e guarda em memória"],
  ["`preco_do_modelo(modelo)`", "Procura pelo nome exato e, se não achar, pelo nome base (aceita sufixos de versão)"],
  ["`calcular_custo(...)`", "Aplica a fórmula da seção 5.2; devolve vazio para modelo sem preço, em vez de inventar um valor"],
], [4, 6]);

h2("4.13 Métricas na web: app/metricas/router.py e resumo.py");
p("O módulo `resumo.py` calcula, direto do banco, os números previstos na especificação para a seção de Resultados.");
tabela(["Número", "Como é calculado"], [
  ["Taxa de falha por tipo", "Chamadas com falha divididas pelo total de chamadas do tipo"],
  ["Custo médio por tipo", "Média de `custo_usd` das chamadas que consumiram tokens, inclusive as que falharam, porque também foram cobradas"],
  ["Tempo médio por tipo", "Média de `latencia_ms` das chamadas com sucesso"],
  ["Taxa de concordância", "Revisões com `aceitou_sugestao` verdadeiro divididas pelo total de revisões, no geral e por condição"],
  ["Desvio médio", "Média de nota final menos nota sugerida; positivo indica que o professor deu mais que o modelo"],
  ["Desvio absoluto médio", "Média do valor absoluto da diferença; mostra o tamanho do ajuste, sem que ajustes para cima e para baixo se anulem"],
], [3, 7]);
tabela(["Rota", "O que faz"], [
  ["`GET /metricas`", "Resumo das chamadas por tipo, concordância por condição e as 200 requisições mais recentes. Cada chamada mostra a origem, com links para a questão e a resposta, e quem a pediu. Com `?questao=` ou `?resposta=`, mostra só as chamadas daquela origem e o custo somado"],
  ["`GET /metricas/exportar.csv`", "Arquivo CSV com todas as requisições e todos os campos, para análise (RF14)"],
  ["`GET /metricas/revisoes.csv`", "Arquivo CSV com uma linha por revisão: resposta, origem, condição, prompt, nota sugerida, nota final, aceite e diferença"],
], [4, 6]);

h2("4.14 Aplicação: app/main.py");
p("Junta as rotas de todos os módulos e define quem pode acessar cada grupo. Toda página exige login, com três exceções: `/entrar`, `/sair` e `/saude`, além dos arquivos de estilo e fontes. As métricas exigem o papel de administrador. A documentação automática que o FastAPI gera em `/docs` foi desligada, porque listaria todas as rotas para qualquer visitante.");
tabela(["Situação", "O que o sistema faz"], [
  ["Sem login", "Leva à página de entrar e, depois do login, volta para a página pedida"],
  ["Senha provisória", "Leva à página de trocar senha antes de qualquer outra"],
  ["Avaliador em página de administrador", "Mostra o aviso \"Página restrita\" (código 403)"],
  ["Limite diário atingido", "Mostra o aviso \"Limite de hoje atingido\" (código 429), sem chamar o modelo"],
  ["`GET /saude`", "Responde que o servidor está no ar; é usada pelo monitoramento da publicação"],
], [4, 6]);

h2("4.15 Requisição de teste: scripts/teste_requisicao.py");
p("Faz uma chamada real ao modelo com o prompt `teste_v1` e mostra no terminal os números gravados. É o critério de pronto da etapa 1. Resultado da primeira execução, em 16/10/2026: sucesso, 77 tokens de entrada, 14 de saída, custo de US$ 0,000294 e latência de 3.587 ms.");

h2("4.16 Importador do ENEM: scripts/importar_enem.py");
p("Baixa questões da API comunitária enem.dev, que cobre as provas de 2009 a 2023, e grava uma cópia congelada em `dados/enem/` com a data de acesso. A API é mantida por voluntários e pode mudar ou sair do ar; a cópia garante que a pesquisa saiba exatamente quais questões usou.");
tabela(["Elemento", "O que faz"], [
  ["`buscar_questoes(ano, cliente)`", "Percorre todas as páginas da prova, respeitando o limite de uma requisição por segundo; para após cinco recusas seguidas"],
  ["`somente_texto(questao)`", "Diz se a questão não tem imagem no enunciado nem nas alternativas"],
  ["`FAIXAS`", "Numeração de cada área na prova regular: 1 a 45 (linguagens), 46 a 90 (humanas), 91 a 135 (natureza) e 136 a 180 (matemática)"],
  ["`fora_da_faixa(questoes, area)`", "Lista as questões cuja numeração não corresponde à área informada pela API"],
  ["`sem_duplicatas(questoes)`", "Mantém uma única cópia de cada número de questão e idioma"],
  ["`filtrar(questoes, area)`", "Mantém a área pedida, dentro da faixa de numeração, sem repetidas e, por padrão, só questões em texto"],
  ["`montar_enunciado(questao)`", "Junta o texto-base e o comando da questão"],
  ["`salvar_copia(...)`", "Grava o arquivo JSON congelado com fonte, data de acesso e filtros"],
  ["`importar_no_banco(questoes, sessao)`", "Grava questões e gabarito no banco, sem duplicar"],
  ["`main()`", "Lê as opções da linha de comando e executa os passos acima"],
], [4, 6]);
p("A conferência pela numeração foi incluída depois que a primeira importação, em 19/10/2026, trouxe como Ciências Humanas seis questões de outras áreas (30, 93, 96, 97, 98 e 153) e uma cópia repetida da questão 50. O arquivo congelado foi corrigido em 20/10/2026, mantendo a data de acesso original e registrando a correção no campo `correcoes` do próprio arquivo. Restaram 38 questões, numeradas de 47 a 90.");
p("Questões com imagem ficam de fora por padrão porque exigiriam que o modelo interpretasse a imagem, o que acrescentaria uma variável que a pesquisa não quer medir neste momento. A opção `--com-imagens` desliga o filtro.");

h2("4.17 Contas e login: app/contas/");
p("O login existe para evitar acessos indevidos e custos indevidos quando o sistema for publicado. Não há cadastro aberto: o administrador cria cada conta, o sistema gera uma senha provisória e a pessoa a troca no primeiro acesso.");
h3("Senhas: senhas.py");
tabela(["Elemento", "O que faz"], [
  ["`gerar_resumo(senha)`", "Calcula o resumo da senha com scrypt e um sal aleatório. Grava no formato `scrypt$n$r$p$sal$resumo`, que guarda também os parâmetros usados"],
  ["`conferir(senha, gravado)`", "Recalcula o resumo com os parâmetros gravados e compara em tempo constante, para que a demora da comparação não revele quantos caracteres coincidem"],
  ["`senha_provisoria()`", "Gera uma senha no formato `xxxx-xxxx-xxxx`, sem letras e números que se confundem, como l e 1"],
  ["`problema_na_senha_nova(...)`", "Exige pelo menos 8 caracteres e confirmação igual"],
], [4, 6]);
p("Os parâmetros do scrypt (N = 2^17, r = 8, p = 1) são os mínimos recomendados pela OWASP. Cada cálculo usa cerca de 128 MB de memória e leva perto de meio segundo, o que torna caro adivinhar senhas a partir de uma cópia do banco. Esse custo só aparece no login e na troca de senha.");
h3("Sessão e permissões: sessao.py");
tabela(["Elemento", "O que faz"], [
  ["`iniciar_sessao` e `encerrar_sessao`", "Gravam e apagam o usuário no cookie da sessão. O cookie é assinado com a `SECRET_KEY`: o navegador consegue lê-lo, mas não alterá-lo sem que o servidor perceba"],
  ["`marca_da_senha(usuario)`", "Trecho do resumo da senha guardado no cookie. Quando a senha muda, a marca deixa de conferir e as sessões abertas em outros navegadores caem"],
  ["`exigir_login`", "Confere a sessão em toda página protegida: usuário existente, ativo e com a marca certa. Também conta as correções que esperam revisão, número mostrado na barra de navegação"],
  ["`exigir_admin`", "Igual a `exigir_login`, mas recusa quem não é administrador"],
  ["`verificar_limite_diario(...)`", "Conta as chamadas ao modelo feitas pelo usuário desde a meia-noite de Brasília e recusa a próxima quando o limite é atingido"],
  ["`ControleDeTentativas`", "Depois de 5 senhas erradas para o mesmo e-mail em 10 minutos, recusa novas tentativas até a janela passar, mesmo com a senha certa"],
], [4, 6]);
h3("Regras das contas: servico.py");
tabela(["Elemento", "O que faz"], [
  ["`criar_conta(...)`", "Valida nome, e-mail e papel, recusa e-mail repetido e devolve a conta com a senha provisória"],
  ["`autenticar(...)`", "Confere e-mail e senha de conta ativa. Para um e-mail inexistente, faz o mesmo cálculo de uma conta real, para que o tempo de resposta não revele quais e-mails têm conta"],
  ["`trocar_senha(...)` e `redefinir_senha(...)`", "A primeira é feita pela própria pessoa; a segunda, pelo administrador, gera nova senha provisória e invalida a anterior"],
  ["`alterar_situacao(...)`", "Desativa ou reativa uma conta. O administrador não pode desativar a si mesmo, e o sistema mantém sempre pelo menos um administrador ativo"],
], [4, 6]);
h3("Páginas: router.py");
tabela(["Rota", "O que faz"], [
  ["`GET` e `POST /entrar`", "Página de login. Volta para a página pedida antes do login, só se ela for do próprio sistema, para que um link malicioso não redirecione a outro site"],
  ["`POST /sair`", "Encerra a sessão"],
  ["`GET` e `POST /trocar-senha`", "Troca de senha, obrigatória no primeiro acesso"],
  ["`GET` e `POST /usuarios`", "Lista as contas e cria novas (só administrador). A senha provisória aparece uma única vez, logo após a criação"],
  ["`POST /usuarios/{id}/redefinir-senha`", "Gera nova senha provisória, depois de confirmação na tela"],
  ["`POST /usuarios/{id}/situacao`", "Desativa ou reativa a conta; desativar pede confirmação"],
], [4, 6]);
h3("Papéis");
tabela(["Papel", "O que pode fazer"], [
  ["Avaliador", "Cadastrar questões e respostas, pedir correções e explicações, aceitar ou ajustar notas"],
  ["Administrador", "Tudo o que o avaliador faz, mais criar e gerenciar contas e ver métricas, custos e exportações"],
], [3, 7]);

h2("4.18 Página inicial: app/inicio.py");
tabela(["Rota", "O que faz"], [
  ["`GET /`", "Saudação, as cinco correções mais antigas que esperam decisão, as últimas revisões com quem decidiu, atalhos de cadastro e um resumo dos últimos 7 dias (o custo aparece só para administradores)"],
  ["`GET /revisar`", "Todas as correções que esperam decisão, da mais antiga para a mais recente"],
], [4, 6]);
p("A fila mostra primeiro as correções mais antigas para que nenhuma fique esquecida. O número de correções pendentes também aparece na barra de navegação, ao lado de \"Para revisar\".");

h2("4.19 Visual e tema escuro");
p("O visual usa a metáfora da folha de prova corrigida: fundo claro como papel, azul de caneta nas ações e a nota final do professor escrita à mão e circulada em vermelho. A nota sugerida pelo modelo aparece em caixa tracejada, para que a diferença entre sugestão e nota final seja visível de relance.");
tabela(["Elemento", "O que faz"], [
  ["Cores em variáveis CSS", "Cada cor tem um nome (`--papel`, `--tinta`, `--caneta-azul`, `--caneta-vermelha` e outras). O tema escuro redefine só esses valores, sem duplicar o resto do estilo"],
  ["Botão de tema", "Na barra de navegação e na página de entrar. Alterna entre claro e escuro e guarda a escolha no navegador. Sem escolha guardada, segue a preferência do sistema operacional"],
  ["Script no início da página", "Aplica o tema antes de desenhar a página, o que evita um clarão branco ao abrir uma página no tema escuro"],
  ["Fontes", "Atkinson Hyperlegible, desenhada para leitura por pessoas com baixa visão, nos textos; Caveat, manuscrita, só na nota circulada. As duas são servidas pelo próprio sistema, com as licenças em `app/static/fontes/`, sem depender de serviços externos"],
  ["Celular", "Abaixo de 760 pixels de largura, os links da barra ficam num menu e as colunas passam a ser empilhadas"],
  ["Datas", "Exibidas no horário de Brasília e, nas listas, de forma relativa (\"há 2 horas\", \"ontem\")"],
], [4, 6]);

h2("4.20 Primeiro administrador: scripts/criar_admin.py");
p("Cria a primeira conta de administrador pela linha de comando, já que não existe cadastro aberto. A senha provisória aparece uma única vez no terminal e precisa ser trocada no primeiro acesso. As contas seguintes são criadas pela página Usuários.");

h2("4.21 Atividades e impressão: app/atividades/router.py");
p("Permite ao professor montar uma atividade com questões já cadastradas, para uma turma, e imprimi-la numa folha A4 pronta, sem precisar formatar o material num editor de texto. É uma ferramenta de uso do professor: as atividades não entram na correção, nas métricas nem na análise da pesquisa.");
tabela(["Rota", "O que faz"], [
  ["`GET /atividades`", "Mostra as atividades em blocos, da mais recente para a mais antiga, com turma, número de questões e quem criou, e o formulário de nova atividade"],
  ["`POST /atividades`", "Cria a atividade com título (obrigatório), turma e instruções"],
  ["`GET /atividades/{id}`", "Questões da atividade em ordem, com botões para subir, descer e remover, e uma busca para adicionar questões, que esconde as que já estão na atividade e mostra até 20 resultados"],
  ["`POST /atividades/{id}/questoes`", "Adiciona uma questão ao fim; a mesma questão não entra duas vezes. Depois volta para a mesma busca, para adicionar várias em sequência"],
  ["`POST /atividades/{id}/questoes/{questao}/mover`", "Troca a questão de lugar com a anterior ou a seguinte"],
  ["`POST /atividades/{id}/questoes/{questao}/remover`", "Tira a questão da atividade e renumera as demais. A questão continua cadastrada"],
  ["`POST /atividades/{id}/editar` e `/excluir`", "Altera título, turma e instruções, ou apaga a atividade, depois de confirmação. Apagar a atividade não apaga as questões"],
  ["`GET /atividades/{id}/imprimir`", "Folha pronta para imprimir ou salvar em PDF pelo navegador. Com `gabarito=1`, é a versão do professor; `linhas` define quantas linhas cada resposta discursiva recebe (5, 8, 12 ou 16; padrão 8)"],
], [4, 6]);
h3("O que sai na folha");
tabela(["Parte", "Folha do aluno", "Folha com gabarito"], [
  ["Cabeçalho", "Título, turma e campos para nome, turma, data e nota", "Título, turma e a indicação \"Gabarito, uso do professor\""],
  ["Instruções", "Impressas logo abaixo do cabeçalho", "Omitidas"],
  ["Resumo", "Não há", "Lista das objetivas com a letra correta, pelo número da questão na folha"],
  ["Objetivas", "Enunciado e alternativas com um círculo para marcar", "A alternativa correta com o círculo preenchido e em negrito"],
  ["Discursivas", "Enunciado, valor em pontos e linhas para a resposta, separadas por item quando houver", "Enunciado, itens, resposta esperada e rubrica com os pontos de cada critério"],
], [2, 4, 4]);
p("A folha usa uma folha de estilo própria (`app/static/impressao.css`), sempre clara, com o tamanho de página A4 definido para a impressão. Uma questão de alternativas e o bloco de cada item não são quebrados entre páginas. A barra de controles do topo da tela não sai na impressão.");
p("Um layout padronizado de folha também prepara a fase posterior de reconhecimento de texto manuscrito: com as respostas sempre nas mesmas áreas da página, fica mais simples localizar cada resposta na imagem digitalizada.");

// ---------------------------------------------------------------------
h1("5. Configuração e execução");

h2("5.1 Arquivo .env");
p("O arquivo `.env` fica na raiz do projeto, é criado a partir de `.env.example` e nunca vai para o GitHub, porque contém a chave da API.");
tabela(["Variável", "Obrigatória", "Significado"], [
  ["`OPENAI_API_KEY`", "Sim", "Chave criada em platform.openai.com/api-keys"],
  ["`MODELO`", "Não", "Modelo usado; padrão `gpt-6.1-sol`. Trocar exige registrar no artigo"],
  ["`DATABASE_URL`", "Não", "Outro banco, sempre com caminho absoluto. Sem ela, usa `tcc.db` na raiz"],
  ["`SECRET_KEY`", "Sim, fora do computador do autor", "Chave que assina o cookie de login. Sem ela, o sistema usa uma chave temporária e todos saem a cada reinício. O comando que gera uma está no `.env.example`"],
  ["`COOKIE_SEGURO`", "Não", "`true` só com HTTPS, no servidor publicado: o navegador passa a enviar o cookie apenas por conexão criptografada"],
  ["`LIMITE_CHAMADAS_DIA`", "Não", "Máximo de chamadas ao modelo por pessoa por dia; padrão 60"],
  ["`NOME_SISTEMA`", "Não", "Nome exibido nas páginas; padrão Devolutiva"],
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
  "Criar o primeiro administrador: `python -m scripts.criar_admin --nome \"Seu Nome\" --email voce@exemplo.com`. Anotar a senha provisória mostrada.",
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
  ["`python -m scripts.criar_admin --nome ... --email ...`", "Criar uma conta de administrador pela linha de comando"],
  ["`python -m scripts.importar_enem --ano 2023 --area ciencias-humanas`", "Listar questões do ENEM em texto e congelar a cópia"],
  ["o mesmo comando com `--importar` no final", "Gravar também as questões no banco"],
], [5, 5]);

// ---------------------------------------------------------------------
h1("6. Testes automatizados");
p("Os testes rodam com `pytest` e não acessam a internet nem gastam crédito: a API da OpenAI e a API do ENEM são substituídas por versões falsas que devolvem respostas controladas. Total nesta versão: 172 testes. Os testes de páginas entram com uma conta de administrador criada no banco de teste, e o custo do scrypt é reduzido só nos testes, para que rodem em poucos segundos.");
tabela(["Arquivo", "O que verifica"], [
  ["`tests/test_precos.py`", "Custo correto para o modelo em uso; preço de cache aplicado; nome com sufixo de versão; modelo desconhecido não gera custo inventado"],
  ["`tests/test_llm.py`", "Sucesso grava tokens, custo, latência, modelo e prompt; resposta sem formato válido vira falha com tokens; erro de rede vira falha com motivo; cliente sem novas tentativas automáticas"],
  ["`tests/test_app.py`", "Rota de verificação pública; página de métricas e exportação em CSV; origem de cada chamada com links, filtro por questão e por resposta e custo somado"],
  ["`tests/test_contas.py`", "Resumo de senha e parâmetros da OWASP; nenhuma rota aberta sem login (todas as rotas da aplicação são percorridas); volta à página pedida só se for interna; senha errada, conta desativada e bloqueio por tentativas; troca obrigatória da senha provisória e suas validações; troca de senha encerra outras sessões; avaliador sem acesso a métricas e usuários; criação de conta com senha provisória exibida uma vez; nova senha invalida a anterior; desativação derruba a sessão; regras do último administrador; revisão e chamada gravam quem fez; fila de revisão; limite diário sem chamar o modelo; datas relativas e saudação no horário de Brasília; nome com aspas exibido com segurança"],
  ["`tests/test_objetiva.py`", "Versão 3: pista do enunciado, explicação única, pista opcional e recusa de pista na alternativa correta; explicação da v2 ainda legível; prompt montado com enunciado, alternativas e gabarito; correção v2 gravada e ligada à métrica; seis tipos de resposta inconsistente viram falha sem correção, incluindo tipo de erro na alternativa correta ou ausente nas incorretas; explicação antiga da v1 continua legível; resposta malformada; lista, detalhe e página inexistente; cadastro válido e inválido; geração pela página; falha exibida com o motivo"],
  ["`tests/test_itens.py`", "Cadastro com itens e critérios por item; itens fora de ordem, item único e critério ligado a item vazio; resposta com um campo por item e texto completo com itens em branco; prompt com e sem itens; trecho citado de outro item ou de item em branco; item inexistente ou diferente da rubrica; nota que não corresponde aos critérios, inclusive no empate; rótulos de professor e aluno e motivo da confiança na página; correção da v1 ainda legível"],
  ["`tests/test_discursiva.py`", "Trecho citado (seis casos, incluindo paráfrase e ordem invertida); prompt nas duas condições, sem vazar a resposta esperada; condição gravada na correção e na métrica; condição indisponível; nove tipos de saída inconsistente, incluindo nota diferente da conta pelos critérios; critérios livres sem rubrica; cadastro válido e inválido; registro de resposta; correção pela página com nota como sugestão; falhas exibidas"],
  ["`tests/test_revisao.py`", "Aceite e ajuste; mesma nota conta como aceite; nota fora do intervalo; segunda revisão recusada pela regra e pelo banco; correção sem nota; concordância e desvios por condição; resumo vazio sem divisão por zero; resumo de chamadas; formulário e ordem dos botões; erros da revisão; exportação das revisões"],
  ["`tests/test_atividades.py`", "Criação e título obrigatório; adicionar sem repetir, mover e remover com renumeração; busca que esconde as já incluídas; retorno só para dentro da atividade; editar e excluir sem apagar questões; folha do aluno com ordem, itens, alternativas e linhas; número de linhas; folha com gabarito, resumo das objetivas, resposta esperada e rubrica; acesso só com login"],
  ["`tests/test_lista_questoes.py`", "Páginas de 50 e página fora do intervalo; cada filtro, inclusive situação pendente e sem correção; filtros mantidos ao trocar de página; filtro sem resultado; opções dos filtros vindas do banco"],
  ["`tests/test_importar_enem.py`", "Paginação; parada após recusas seguidas; exclusão de numeração fora da área e de repetidas; filtro de área e de imagens; montagem do enunciado; importação com gabarito e sem duplicar"],
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
  ["Um contrato por versão de prompt", "Explicações antigas continuam legíveis e comparáveis com as novas"],
  ["Uma revisão por correção, sem edição posterior", "A decisão registrada é o dado da pesquisa; alterá-la depois comprometeria a medida de concordância"],
  ["Aceite calculado pela comparação das notas", "Evita inconsistência entre o que a tela informa e as notas gravadas"],
  ["Mesmo prompt nas duas condições, mudando só o campo da resposta esperada", "A diferença entre as condições fica restrita ao insumo do professor, o que torna a comparação válida"],
  ["Trecho citado conferido na resposta do aluno", "Um trecho inventado é uma alucinação e tornaria o feedback enganoso"],
  ["Nota calculada pelos pesos da rubrica", "Torna a nota sugerida explicável e verificável pelo professor a partir da análise por critério"],
  ["Pistas de conteúdo, e não pistas genéricas de prova", "A pista precisa ensinar algo da disciplina e valer para aquela questão; truques como \"a mais longa é a certa\" falham com frequência e não ensinam"],
  ["Pista opcional por alternativa", "Forçar uma pista em toda alternativa levaria o modelo a inventar pistas falsas"],
  ["Tipo de erro em categoria fechada", "Permite contar e comparar os tipos de erro na análise, o que um texto livre não permitiria"],
  ["Análise para o professor, feedback para o aluno", "O professor precisa ver o conteúdo esperado para conferir a nota; o aluno precisa ser orientado sem receber a resposta"],
  ["Nota recalculada pelo sistema", "A nota sugerida precisa ser explicável pela análise; uma conta errada do modelo tornaria a nota inconsistente com a própria justificativa"],
  ["Itens com resposta separada, mas nota por questão", "Permite conferir a evidência item a item sem mudar a unidade de análise da concordância, que continua sendo a questão"],
  ["Conferência da área pela numeração da prova", "A fonte comunitária classificou questões na área errada"],
  ["Explicação de objetiva ligada à questão, não a um aluno", "O RF02 pede a explicação de cada alternativa, que não depende de quem respondeu"],
  ["Contas criadas pelo administrador, sem cadastro aberto", "O sistema chama uma API paga; só pessoas convidadas devem gerar custo"],
  ["Sessão em cookie assinado, sem tabela de sessões", "Menos código e nenhuma tabela a limpar; a marca da senha no cookie permite derrubar sessões quando a senha muda ou a conta é desativada"],
  ["scrypt da biblioteca padrão do Python", "Algoritmo recomendado pela OWASP para senhas, sem dependência extra"],
  ["Limite diário de chamadas por pessoa", "Uma conta comprometida ou um uso por engano não consegue consumir o orçamento de um mês em um dia"],
  ["Impressão pelo navegador, sem gerar PDF no servidor", "O navegador já imprime e salva em PDF; gerar o arquivo no servidor exigiria uma dependência pesada sem ganho para o uso"],
  ["Atividades visíveis a todas as contas", "No protótipo, os avaliadores trabalham sobre o mesmo corpus. Num produto, cada professor veria só as suas, o que exige apenas filtrar por `usuario_id`"],
  ["Origem gravada em toda chamada, inclusive nas falhas", "Permite saber quanto custou cada questão e cada resposta, e onde ocorreram as falhas, sem depender de uma correção gravada"],
  ["Quem revisou e quem pediu a chamada gravados", "Permite separar os dados por avaliador na análise e conferir o uso de cada conta"],
  ["Métricas e custos só para administradores", "Os avaliadores da coleta não precisam ver custos, e ver a concordância acumulada poderia influenciar as suas decisões"],
  ["Fontes servidas pelo próprio sistema", "As páginas não dependem de serviços externos e não enviam dados de acesso a terceiros"],
], [4, 6]);

h2("8.2 Limitações e pontos de atenção");
marcadores([
  "**Versão do modelo:** a API devolveu `gpt-6.1-sol` sem sufixo de data, o que indica um nome que pode apontar para versões atualizadas ao longo do tempo. O artigo deve citar também o período da coleta, que está registrado em `criado_em`.",
  "**Questões do ENEM nos dados de treino:** é provável que o modelo já tenha visto essas questões e suas resoluções. Como o professor informa a resposta correta, o efeito é menor, mas deve ser declarado como limitação.",
  "**Dados de fonte comunitária:** a API classificou questões na área errada e repetiu uma questão, o que mostra que os dados precisam de conferência. O gabarito e o enunciado das questões escolhidas devem ser conferidos com a prova e o gabarito oficiais do INEP, que são a fonte primária citada no artigo.",
  "**Categorias de tipo de erro:** foram definidas pelo autor do protótipo a partir dos erros comuns em questões de Ciências Humanas. No artigo, devem ser apresentadas como categorização própria ou fundamentadas em literatura sobre análise de distratores.",
  "**Tokens gravados em cache:** o cálculo supõe que esses tokens já estão incluídos no total de entrada, como acontece com os tokens lidos do cache. A suposição ainda deve ser confirmada na documentação da OpenAI; ela só afeta requisições que usam cache.",
  "**Ancoragem:** o professor vê a nota sugerida antes de decidir, o que pode puxar a sua nota em direção à do modelo. A concordância medida é, portanto, a concordância nas condições de uso do sistema, e não uma comparação com uma correção independente. Isso deve ser declarado no artigo.",
  "**Duas correções da mesma resposta:** se o mesmo avaliador revisar as duas condições de uma resposta, a segunda decisão é influenciada pela primeira. O protocolo da coleta com especialistas deve definir quem revisa qual condição.",
  "**Pistas incorretas:** uma pista pode soar convincente e não valer para a questão. Não há conferência automática possível; a correção das pistas deve ser um dos aspectos avaliados pelos especialistas.",
  "**Feedback que entrega a resposta:** a regra da v2 reduz o problema, mas não há conferência automática possível, porque decidir se um texto revela a resposta exige interpretação. Convém incluir essa pergunta no instrumento dos especialistas e contar os casos na análise.",
  "**Correções do teste piloto:** as correções feitas com a v1 continuam no banco e identificadas pela versão do prompt. A comparação entre condições deve usar apenas correções da mesma versão.",
  "**Critérios sem rubrica:** quando o professor não informa rubrica, o modelo define os critérios a cada correção, e eles podem variar entre correções da mesma questão. Para comparar condições, o corpus deve usar questões com rubrica.",
  "**Geração na própria requisição da página:** o navegador espera a resposta do modelo, o que leva alguns segundos. É adequado para um usuário por vez; a execução em lote da etapa 5 roda por linha de comando.",
  "**Explicações anteriores:** a página mostra só a explicação mais recente. As anteriores continuam no banco e entram na análise.",
  "**Latência e rede:** a latência inclui o tempo de rede do computador onde o sistema roda. Medições comparadas entre si devem vir da mesma máquina e conexão.",
  "**Busca no enunciado:** o SQLite só ignora a diferença entre maiúsculas e minúsculas em letras sem acento. Buscar \"REVOLUÇÃO\" não encontra \"revolução\"; buscar em minúsculas, ou por parte da palavra sem acento (\"revolu\"), encontra.",
  "**Bloqueio por tentativas em memória:** a contagem de senhas erradas fica na memória do servidor e recomeça quando ele reinicia. É suficiente para um único servidor; com vários, precisaria ir para o banco.",
  "**Limite diário conta também as falhas:** uma chamada que falhou também foi cobrada pela OpenAI, por isso entra na contagem.",
  "**Chave de sessão:** sem `SECRET_KEY` no .env, cada reinício do servidor encerra todas as sessões. No servidor publicado, a chave é obrigatória e `COOKIE_SEGURO` deve estar ligado.",
]);

// ---------------------------------------------------------------------
h1("9. Glossário");
tabela(["Termo", "Significado"], [
  ["Alembic", "Ferramenta que registra e aplica mudanças na estrutura do banco de dados"],
  ["Anacronismo", "Atribuir a uma época algo que pertence a outra"],
  ["API", "Interface pela qual um programa usa serviços de outro; aqui, a forma de enviar textos ao modelo da OpenAI e de buscar questões do ENEM"],
  ["Baseline", "Método simples usado como referência de comparação nos resultados"],
  ["Branch", "Linha paralela de desenvolvimento no Git, que não afeta a principal até ser incorporada"],
  ["Cache de prompt", "Reaproveitamento, pela OpenAI, de trechos iniciais repetidos entre requisições, cobrados mais barato"],
  ["Commit", "Registro de um conjunto de mudanças no histórico do Git"],
  ["CSV", "Arquivo de texto com valores separados por vírgula, aberto por planilhas e pelo pandas"],
  ["Concordância", "Proporção de correções em que o professor aceitou a nota sugerida pelo modelo"],
  ["Cookie", "Pequeno texto que o site guarda no navegador e que volta a cada página; aqui, identifica a sessão de login"],
  ["Condição experimental", "Cada uma das formas de rodar a correção comparadas na pesquisa: com e sem resposta esperada"],
  ["Distrator", "Alternativa incorreta de uma questão objetiva, construída para parecer plausível"],
  ["Embeddings", "Representações numéricas do significado de um texto, usadas para medir semelhança"],
  ["FastAPI", "Biblioteca Python para construir aplicações web"],
  ["HTR", "Reconhecimento de texto manuscrito (do inglês Handwritten Text Recognition)"],
  ["HTTPS", "Conexão criptografada entre o navegador e o servidor"],
  ["JSON", "Formato de texto para dados estruturados em campos e valores"],
  ["Latência", "Tempo entre o envio da requisição e a chegada da resposta completa"],
  ["Migração", "Arquivo que descreve uma mudança na estrutura do banco e permite aplicá-la de forma repetível"],
  ["OWASP", "Fundação aberta que publica guias de segurança para aplicações web"],
  ["Papel", "Conjunto de permissões de uma conta: administrador ou avaliador"],
  ["Prompt", "Texto de instrução enviado ao modelo de linguagem"],
  ["Resumo criptográfico", "Valor calculado a partir da senha do qual não se consegue voltar à senha; também chamado de hash"],
  ["Item", "Parte de uma questão discursiva com comando próprio, identificada por letra (a, b, c), que compartilha o texto-base com as demais"],
  ["Rubrica", "Lista de critérios de correção de uma questão discursiva, cada um com seu peso na nota"],
  ["Rota", "Endereço da aplicação web associado a uma ação, como `GET /questoes`, que lista as questões"],
  ["Pull request", "Pedido para incorporar uma branch à principal, com espaço para revisão e comentários"],
  ["Pydantic", "Biblioteca que valida se dados têm os campos e tipos esperados"],
  ["Sal", "Valor aleatório misturado a cada senha antes do resumo, para que senhas iguais tenham resumos diferentes"],
  ["Saída estruturada", "Recurso da API que obriga o modelo a responder em JSON com um formato definido"],
  ["scrypt", "Função de resumo de senhas que exige muito processamento e memória, o que torna caro adivinhar senhas"],
  ["Sessão", "Período em que a pessoa fica conectada depois do login, sem digitar a senha de novo; aqui, até 12 horas"],
  ["SQLAlchemy", "Biblioteca que permite manipular tabelas do banco como classes Python"],
  ["SQLite", "Banco de dados guardado em um único arquivo, sem servidor"],
  ["Tema", "Conjunto de cores das páginas: claro ou escuro"],
  ["Token", "Unidade de texto (em geral parte de uma palavra) usada pela API para contar e cobrar o uso"],
], [3, 7]);

// ---------------------------------------------------------------------
h1("10. Histórico de versões");
tabela(["Data", "Versão", "Referência", "Mudança"], [
  ["24/10/2026", "0.12", "pull request das atividades", "Atividades com questões em ordem, aba própria na barra de navegação e folha de impressão em A4 para o aluno e com gabarito"],
  ["24/10/2026", "0.11", "pull request da lista de questões", "Lista de questões com 50 por página e filtros por palavra no enunciado, número, tipo, área, origem, ano e situação"],
  ["24/10/2026", "0.10", "pull request das métricas com origem", "Cada chamada ao modelo ligada à questão e à resposta de origem, inclusive nas falhas; links e filtro por questão ou resposta na página de métricas, com custo somado; colunas novas na exportação"],
  ["24/10/2026", "0.9", "pull request da objetiva_v3", "Explicação das objetivas mais curta: explicação única por alternativa com etiqueta do tipo de erro, pista do enunciado e pista de conteúdo para eliminar alternativas (prompt objetiva_v3)"],
  ["23/10/2026", "0.8", "pull request dos itens e da discursiva_v2", "Questões discursivas com itens e resposta por item; prompt discursiva_v2 após o teste piloto (feedback sem entregar a resposta e limitado à rubrica, confiança com motivo, análise para o professor); conferência do item de cada critério, do trecho por item e da conta da nota"],
  ["23/10/2026", "0.7", "pull request de login e visual", "Contas individuais criadas pelo administrador, senha provisória com troca obrigatória, papéis, bloqueio por tentativas, limite diário de chamadas, autoria de revisões e chamadas; página inicial com fila de revisão; novo visual com barra de navegação, tema claro e escuro e versão para celular"],
  ["22/10/2026", "0.6", "pull request da etapa 4", "Aceite ou ajuste da nota com uma revisão por correção (restrição no banco e migração), proteção contra aceite por engano, concordância e desvios na página de métricas, exportação das revisões"],
  ["21/10/2026", "0.5", "pull request da etapa 3", "Módulo discursivo: contrato e conferência (incluindo trecho citado), prompt discursiva_v1, cadastro com rubrica e resposta esperada opcionais, respostas de alunos e correção nas duas condições"],
  ["20/10/2026", "0.4", "pull request da explicação v2", "Explicação com tipo de erro, elemento errado e como perceber sem o gabarito (prompt objetiva_v2); importador confere a numeração da área e remove repetidas; arquivo congelado corrigido para 38 questões"],
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
  "OWASP. Password Storage Cheat Sheet. Disponível em: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html. Acesso em: 23 out. 2026.",
  "PERCIVAL, C.; JOSEFSSON, S. RFC 7914: The scrypt Password-Based Key Derivation Function. IETF, 2016. Disponível em: https://www.rfc-editor.org/rfc/rfc7914. Acesso em: 23 out. 2026.",
  "BRAILLE INSTITUTE. Atkinson Hyperlegible Font. Disponível em: https://www.brailleinstitute.org/freefont/. Acesso em: 23 out. 2026.",
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
