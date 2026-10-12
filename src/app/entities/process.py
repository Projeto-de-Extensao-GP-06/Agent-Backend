from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class ClienteEntity(BaseModel):
    nome: str
    cpf: str | None = None
    telefone: str | None = None
    ativo: bool = True


class PrioridadeEntity(BaseModel):
    nome: str
    peso: int = 0


class FaseProcessoEntity(BaseModel):
    nome: str
    ordem: int = 0


class SiglaTribunalEntity(BaseModel):
    sigla: str
    nome: str


class ProcessoEntity(BaseModel):
    cliente: ClienteEntity | None = None
    descricaoCaso: str | None = None
    observacao: str | None = None
    prioridade: PrioridadeEntity | None = None
    faseProcesso: FaseProcessoEntity | None = None
    ultimaAtualizacao: datetime | str | None = None
    dataHoraInicio: datetime | str | None = None
    ativo: bool = True
    dataAudiencia: datetime | str | None = None
    encerradoEm: datetime | str | None = None
    encerradoPorUsuario: str | None = None
    siglaTribunal: SiglaTribunalEntity | None = None
    valorCausa: float | None = None
    metadados_extras: dict[str, Any] = Field(default_factory=dict)
