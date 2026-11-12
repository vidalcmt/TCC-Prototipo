"""Página do administrador com o resumo das avaliações da leitura."""

import csv
import io

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import obter_sessao
from app.leitura.avaliacao import NOTAS, VEREDITOS, linhas_csv, resumo
from app.templates_config import templates

router = APIRouter(prefix="/leitura", tags=["leitura"])


@router.get("/avaliacoes", response_class=HTMLResponse)
def pagina(request: Request, sessao: Session = Depends(obter_sessao)):
    total, grupos = resumo(sessao)
    return templates.TemplateResponse(request, "avaliacoes_leitura.html",
                                      {"total": total, "grupos": grupos, "NOTAS": NOTAS,
                                                                  "VEREDITOS": VEREDITOS})


@router.get("/avaliacoes.csv")
def exportar(sessao: Session = Depends(obter_sessao)):
    linhas = linhas_csv(sessao)
    saida = io.StringIO()
    campos = ["atividade", "folha", "campo", "nota", "corrigiu_erro_aluno", "servico", "com_revisao", "trocas",
              "trocas_certas", "trocas_erradas", "trocas_erro_aluno", "trocas_detalhe", "texto_ocr", "texto_lido",
              "atual", "avaliada_em"]
    escritor = csv.DictWriter(saida, fieldnames=campos)
    escritor.writeheader()
    escritor.writerows(linhas)
    return Response(saida.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="avaliacoes_leitura.csv"'})
