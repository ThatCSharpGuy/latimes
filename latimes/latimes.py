import logging
import re
from collections import defaultdict, namedtuple
from datetime import datetime
from typing import Dict, List, Tuple

from dateutil.relativedelta import relativedelta
from unidecode import unidecode

from latimes.config import LatimesConfiguration, LatimesOutputFormatting
from latimes.exceptions import InvalidTimeStringException

TIME_REGEX_PORTION = (
    r"(?P<hora>[0-9]{1,2})(?::(?P<minutes>[0-9]{1,2}))?\s?(?P<period>(am|pm|AM|PM))$"
)

TIEMPO_REGEXES = [
    re.compile(r"^(?P<dia>[a-zA-Z]+)\s" + TIME_REGEX_PORTION),
    re.compile(
        r"^(?P<dia>[0-9]{1,2})\s(de)?\s?(?P<mes>[a-zA-Z]+)\s" + TIME_REGEX_PORTION
    ),
]

DIAS = {
    dia: valor
    for valor, dia in enumerate(
        ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    )
}
MESES = {
    mes: valor + 1
    for valor, mes in enumerate(
        [
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        ]
    )
}
DIA_DOMINGO = 6


def convert_times(cadena_tiempo: str, configuration: LatimesConfiguration) -> str:
    try:
        tiempo_usuario = interpreta_cadena_tiempo(cadena_tiempo)
    except ValueError as value_error:
        raise InvalidTimeStringException() from value_error
    tiempos = transforma_zonas_horarias(tiempo_usuario, configuration)
    return format_results(tiempo_usuario, tiempos, configuration.output_formatting)


def interpreta_cadena_tiempo(cadena_tiempo: str) -> datetime:
    today = datetime.today()
    clean_time_string = unidecode(cadena_tiempo.lower())
    logging.info(f"Today's date is {today.isoformat()}")
    logging.info(f"Processing {clean_time_string}")
    for regex in TIEMPO_REGEXES:
        match = regex.match(clean_time_string)
        if match:
            break
    else:
        raise ValueError(f'"{cadena_tiempo}" is not a valid time string')

    valores = match.groupdict()

    if "mes" not in valores:
        dia_usuario = DIAS[valores["dia"].casefold()]

        dia_actual = today.weekday()
        if dia_usuario > dia_actual:
            dias_faltantes = dia_usuario - dia_actual
            fecha_solicitada = today + relativedelta(days=dias_faltantes)
        else:
            dias_para_domingo = DIA_DOMINGO - dia_actual + 1
            fecha_solicitada = today + relativedelta(
                days=dias_para_domingo + dia_usuario
            )
    else:
        mes_usuario = MESES[valores["mes"]]
        dia_usuario = int(valores["dia"])

        fecha_solicitada = datetime(today.year, mes_usuario, dia_usuario)
        if fecha_solicitada < today:
            fecha_solicitada = fecha_solicitada + relativedelta(years=1)

    minutes = int(valores["minutes"] or 0)
    hora = int(valores["hora"]) + (0 if valores["period"] == "am" else 12)

    return datetime(
        fecha_solicitada.year,
        fecha_solicitada.month,
        fecha_solicitada.day,
        hora,
        minutes,
    )


def transforma_zonas_horarias(
    valor_final: datetime, configuration: LatimesConfiguration
) -> List[Tuple[str, datetime]]:
    tiempos = []
    valor_localizado = configuration.starting_timezone.localize(valor_final)
    for pais, zona_horaria in configuration.convert_to.items():
        tiempos.append((pais, valor_localizado.astimezone(zona_horaria)))

    return tiempos


DateDiff = namedtuple("DateDiff", ["time", "day_difference"])


def format_results(
    anchor_datetime: datetime,
    results: List[Tuple[str, datetime]],
    output_formatting: LatimesOutputFormatting,
) -> str:
    aggregates: Dict[DateDiff, List[str]] = defaultdict(list)

    for pais, time in results:
        restored_time = time.replace(tzinfo=None)
        difference = restored_time.date() - anchor_datetime.date()
        date_diff = DateDiff(restored_time, difference.days)
        aggregates[date_diff].append(pais)

    times = []
    for date_diff, time_zones in aggregates.items():
        time_formatted = date_diff.time.strftime(output_formatting.time_format_string)
        if date_diff.day_difference:
            time_formatted += "%+d" % date_diff.day_difference

        if output_formatting.aggregate:
            joint_timezones = output_formatting.aggregate_joiner.join(time_zones)
            times.append(f"{time_formatted} {joint_timezones}")
        else:
            for time_zone in time_zones:
                times.append(f"{time_formatted} {time_zone}")

    return output_formatting.different_time_joiner.join(times)
