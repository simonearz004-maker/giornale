"""Forma delle risposte attese dal modello (validate prima di qualsiasi uso)."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


def _low(v):
    return v.strip().lower() if isinstance(v, str) else v


class Evento(BaseModel):
    gruppi: list[str] = Field(min_length=1)
    categoria: str
    rilevanza: int = Field(ge=1, le=5)
    motivo: str = ""
    seguito_di: str | None = None
    indiscrezione: bool = False


class Selezione(BaseModel):
    eventi: list[Evento] = Field(default_factory=list)


class Impatto(BaseModel):
    per_chi: str
    testo: str
    stato: str = "possibile"
    fonti: list[str] = Field(default_factory=list)

    _n = field_validator("stato", mode="before")(_low)


class Spiegazione(BaseModel):
    titolo: str
    testo: str


class Dato(BaseModel):
    etichetta: str
    valore: str
    periodo: str = ""
    fonte: str


class Passo(BaseModel):
    tipo: str
    testo: str
    fonti: list[str] = Field(default_factory=list)

    _n = field_validator("tipo", mode="before")(_low)


class Affermazione(BaseModel):
    testo: str
    fonti: list[str] = Field(default_factory=list)
    natura: str = "fatto"

    _n = field_validator("natura", mode="before")(_low)


class Scheda(BaseModel):
    titolo: str = ""
    sintesi: str = ""
    perche_importa: list[Impatto] = Field(default_factory=list)
    spiegazione: Spiegazione | None = None
    dati: list[Dato] = Field(default_factory=list)
    contesto: str = ""
    prossimi_passi: list[Passo] = Field(default_factory=list)
    affermazioni: list[Affermazione] = Field(default_factory=list)
    divergenze: str = ""
    data_evento: str | None = None
    termini: list[str] = Field(default_factory=list)
    indiscrezione: bool = False
    materiale_insufficiente: bool = False


class Problema(BaseModel):
    campo: str = ""
    testo: str = ""
    motivo: str = ""


class Controllo(BaseModel):
    fedele: bool
    problemi: list[Problema] = Field(default_factory=list)


class Voce(BaseModel):
    termine: str
    definizione_semplice: str
    spiegazione: str = ""
    esempio: str = ""
    correlati: list[str] = Field(default_factory=list)


class Voci(BaseModel):
    voci: list[Voce] = Field(default_factory=list)


class Esito(BaseModel):
    termine: str
    corretta: bool
    motivo: str = ""


class Revisione(BaseModel):
    esiti: list[Esito] = Field(default_factory=list)
