# Registro de versões dos prompts

Cada versão usada na coleta fica congelada. Uma mudança gera um arquivo novo
(v2, v3...) e uma entrada aqui, com a data e o motivo. A coluna prompt_versao
da tabela metrica_requisicao aponta para estas versões.

## discursiva_v2 (23/10/2026)

Mudanças após o teste piloto do autor com a questão Hereges (Fuvest 2025),
em que a v1 mostrou quatro problemas causados pelas próprias regras:
- o feedback entregava a resposta (ex.: "retome o conceito de Inquisição"),
  porque a regra 9 da v1 mandava indicar os conceitos a mobilizar. Agora o
  feedback pode repetir o que o enunciado pede, mas não o conteúdo que
  atende ao pedido, e orienta com perguntas e trechos a reler;
- o feedback cobrava conteúdo fora do gabarito (autoridades civis), porque
  a v1 mandava mostrar o caminho para a resposta completa sem limite. Agora
  só cobra o que algum critério da rubrica exige;
- a confiança era baixa em respostas curtas e claramente erradas, porque a
  regra 8 da v1 misturava a qualidade da resposta com a certeza da nota.
  Agora a confiança mede só a certeza sobre a nota, com níveis definidos, e
  vem acompanhada de motivo_confianca;
- a saída passa a separar os leitores: a análise por critério é para o
  professor e pode citar o conteúdo esperado; o feedback é para o aluno.

Mudanças ligadas aos itens (a, b, c) das questões discursivas:
- novo campo {itens} no prompt e resposta do aluno identificada por item;
- cada critério informa o item a que se refere (campo item do contrato
  CorrecaoDiscursivaV2), e o sistema procura o trecho citado só na resposta
  desse item;
- o sistema refaz a conta da nota pelos pesos e status e recusa a correção
  se a nota não corresponder (no empate, aceita os dois arredondamentos).

## discursiva_v1 (21/10/2026)

Primeira versão do prompt das questões discursivas. Um único texto atende às
duas condições experimentais (com e sem resposta esperada, RF08): o que muda
é o conteúdo dos campos {resposta_esperada} e {condicao}. Regras principais:
- com rubrica, avaliar exatamente os critérios e pesos do professor; sem
  rubrica, definir de 3 a 5 critérios;
- citar literalmente o trecho da resposta do aluno (RF06);
- nota calculada pelos pesos: atendido vale o peso, parcial metade,
  nao_atendido zero, arredondada para múltiplo de 0,5 (RF07);
- feedback que mostra o caminho para a resposta completa sem entregá-la.

## objetiva_v2 (20/10/2026)

Pedido do autor após a revisão da v1: a explicação de cada alternativa errada
deve mostrar a natureza do erro e como o estudante poderia percebê-lo usando
outros conhecimentos (por exemplo, época trocada entre Modernismo e período
contemporâneo, ou contexto histórico errado).

Mudanças em relação à v1:
- contrato novo (CorrecaoObjetivaV2) com três campos por alternativa:
  tipo_de_erro (categoria fechada), elemento_incorreto (o ponto exato que
  está errado) e como_verificar (como perceber o erro sem o gabarito);
- regras específicas para erros de época, contexto, conceito e leitura;
- pede o período em vez de um ano quando não houver segurança sobre a data.

## objetiva_v1 (19/10/2026)

Primeira versão do prompt das questões objetivas. Pede, para cada alternativa
incorreta, o erro de raciocínio que leva a escolhê-la (RF02 e RF03), e para a
correta, os elementos do enunciado que a sustentam. Proíbe contrariar o
gabarito informado pelo professor e inventar dados fora do enunciado.

## teste_v1 (16/10/2026)

Prompt mínimo da etapa 1, usado só para confirmar que a chamada ao modelo e o
registro de métricas funcionam. Não é usado na coleta.
