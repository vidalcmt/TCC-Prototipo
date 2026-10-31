"""Posição de cada elemento da folha de respostas, em milímetros.

A mesma função serve para imprimir a folha e, depois, para ler a folha
digitalizada: o sistema sabe exatamente onde estão as marcas de alinhamento,
o QR code, cada bolinha das objetivas e cada caixa das discursivas. Por isso o
layout não depende do navegador nem da impressora, só da atividade.

Uma folha impressa não pode mudar de layout depois de entregue aos alunos.
Por isso, depois que as folhas são geradas, as questões da atividade ficam
travadas (ver app/atividades/router.py).
"""

from dataclasses import dataclass, field

LARGURA, ALTURA = 210.0, 297.0  # A4

# Marcas de alinhamento: quadrados pretos nos quatro cantos da área lida.
MARCA = 8.0
MARCAS = ((10.0, 10.0), (192.0, 10.0), (10.0, 254.0), (192.0, 254.0))  # canto superior esquerdo de cada uma

QR_X, QR_Y, QR_LADO = 160.0, 12.0, 26.0
AREA_X0, AREA_X1 = 20.0, 190.0
AREA_Y0, AREA_Y1 = 44.0, 250.0  # entre o cabeçalho e as marcas de baixo
CANHOTO_Y = 268.0  # abaixo da linha de recorte, só na primeira página

LINHA_RESPOSTA = 8.0  # altura de uma linha de escrita
RAIO_BOLHA = 2.6
PASSO_BOLHA = 9.0
ALTURA_LINHA_OBJETIVA = 8.0
COLUNAS_OBJETIVAS = (AREA_X0 + 2.0, 108.0)
ROTULO_SECAO = 7.0


@dataclass
class Bolha:
    numero: int          # número da questão na atividade
    questao_id: int
    letra: str
    x: float             # centro
    y: float
    r: float = RAIO_BOLHA


@dataclass
class Caixa:
    numero: int
    questao_id: int
    item: str | None     # letra do item, ou None em questão sem itens
    rotulo: str
    x: float
    y: float
    largura: float
    altura: float        # área de escrita, abaixo do rótulo
    linhas: int


@dataclass
class Rotulo:
    texto: str
    x: float
    y: float


@dataclass
class Pagina:
    numero: int
    bolhas: list[Bolha] = field(default_factory=list)
    caixas: list[Caixa] = field(default_factory=list)
    rotulos: list[Rotulo] = field(default_factory=list)


def conteudo_qr(codigo: str, pagina: int) -> str:
    return f"DEVOLUTIVA|{codigo}|{pagina}"


def ler_qr(texto: str) -> tuple[str, int] | None:
    """Interpreta o conteúdo do QR code de uma folha; None se não for uma folha do sistema."""
    partes = (texto or "").strip().split("|")
    if len(partes) != 3 or partes[0] != "DEVOLUTIVA" or not partes[2].isdigit():
        return None
    return partes[1], int(partes[2])


LETRAS_PADRAO = "ABCDE"


def letras(questao) -> list[str]:
    """Letras das bolinhas: as alternativas cadastradas ou, se não houver, A a E.

    Uma objetiva sem alternativas cadastradas ainda recebe bolinhas, para a
    folha sair completa; a correção avisa que falta o gabarito.
    """
    return [a.letra for a in questao.alternativas] or list(LETRAS_PADRAO)


def montar(atividade, linhas: int) -> list[Pagina]:
    """Distribui as respostas da atividade em páginas.

    Objetivas primeiro, numa grade de bolinhas em duas colunas; depois uma
    caixa por discursiva, ou uma por item. A numeração segue a ordem da
    atividade, a mesma do caderno de questões.
    """
    paginas = [Pagina(numero=1)]
    y = AREA_Y0

    objetivas = [(n, i.questao) for n, i in enumerate(atividade.itens, start=1) if i.questao.tipo == "objetiva"]
    discursivas = [(n, i.questao) for n, i in enumerate(atividade.itens, start=1) if i.questao.tipo == "discursiva"]

    if objetivas:
        paginas[-1].rotulos.append(Rotulo("Questões objetivas: preencha totalmente uma bolinha por questão.", AREA_X0, y))
        y += ROTULO_SECAO
        linhas_por_coluna = int((AREA_Y1 - y) // ALTURA_LINHA_OBJETIVA)
        y_inicio = y
        for indice, (numero, questao) in enumerate(objetivas):
            if indice and indice % (linhas_por_coluna * len(COLUNAS_OBJETIVAS)) == 0:
                paginas.append(Pagina(numero=len(paginas) + 1))
                y_inicio = AREA_Y0
            posicao = indice % (linhas_por_coluna * len(COLUNAS_OBJETIVAS))
            coluna, linha = divmod(posicao, linhas_por_coluna)
            x0 = COLUNAS_OBJETIVAS[coluna]
            yc = y_inicio + linha * ALTURA_LINHA_OBJETIVA + ALTURA_LINHA_OBJETIVA / 2
            paginas[-1].rotulos.append(Rotulo(f"{numero}", x0, yc))
            for k, letra in enumerate(letras(questao)):
                paginas[-1].bolhas.append(Bolha(numero, questao.id, letra, x0 + 14.0 + k * PASSO_BOLHA, yc))
        # abaixo da linha mais baixa da grade (a primeira coluna é sempre a mais longa)
        y = max(r.y for r in paginas[-1].rotulos if r.texto.isdigit()) + ALTURA_LINHA_OBJETIVA / 2 + 4.0

    caixas = []
    for numero, questao in discursivas:
        if questao.itens:
            for item in questao.itens:
                caixas.append((numero, questao, item.letra, f"Questão {numero}, item {item.letra})"))
        else:
            caixas.append((numero, questao, None, f"Questão {numero}"))

    altura_escrita = linhas * LINHA_RESPOSTA
    for numero, questao, item, rotulo in caixas:
        altura_total = ROTULO_SECAO + altura_escrita
        if y + altura_total > AREA_Y1:
            paginas.append(Pagina(numero=len(paginas) + 1))
            y = AREA_Y0
        paginas[-1].caixas.append(Caixa(numero, questao.id, item, rotulo, AREA_X0, y + ROTULO_SECAO,
                                        AREA_X1 - AREA_X0, altura_escrita, linhas))
        y += altura_total + 4.0
    return paginas


def maximo_de_linhas() -> int:
    """Uma caixa precisa caber numa página."""
    return int((AREA_Y1 - AREA_Y0 - ROTULO_SECAO) // LINHA_RESPOSTA)
