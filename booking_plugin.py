from datetime import datetime

from dotenv import load_dotenv
from langchain_core.tools import tool

from errors import BookingUnavailableError, ValidationError, require_env, safe_tool
from travelline_client import TravelLineClient, TravelLineConfig

load_dotenv()

# Заполняются в initialize_plugin() перед стартом
HOTEL_BOOKING_SITE_URL: str | None = None
travelline_client: TravelLineClient | None = None


def _parse_date(value: str, field_name: str) -> datetime:
    try:
        return datetime.strptime(value, "%d-%m-%Y")
    except ValueError:
        raise ValidationError(
            f"Некорректный формат даты в поле '{field_name}': {value}. Ожидается ДД-ММ-ГГГГ"
        )


def _validate_dates(check_in: str, check_out: str) -> tuple[datetime, datetime]:
    d_in = _parse_date(check_in, "check_in")
    d_out = _parse_date(check_out, "check_out")
    if d_out <= d_in:
        raise ValidationError("Дата выезда должна быть позже даты заезда")
    if d_in.date() < datetime.now().date():
        raise ValidationError("Дата заезда не может быть в прошлом")
    return d_in, d_out


@tool
@safe_tool
async def search_available_rooms(check_in: str, check_out: str, guests: int) -> list[dict]:
    """Найти доступные номера на указанные даты.

    Args:
        check_in: дата заезда в формате ДД-ММ-ГГГГ
        check_out: дата выезда в формате ДД-ММ-ГГГГ
        guests: количество гостей
    """
    d_in, d_out = _validate_dates(check_in, check_out)
    if guests <= 0:
        raise ValidationError("Количество гостей должно быть больше нуля")

    room_stays = await travelline_client.search_room_stays(
        d_in.strftime("%Y-%m-%d"), d_out.strftime("%Y-%m-%d"), guests
    )

    if not room_stays:
        raise BookingUnavailableError("На выбранные даты свободных номеров нет")

    # TODO: свериться с реальной структурой ответа TravelLine и при
    # необходимости поправить имена полей ниже по коду (room_type/offer_id)
    return room_stays


@tool
@safe_tool
def generate_booking_link(room_type: str, offer_id: str, check_in: str, check_out: str) -> str:
    """Сформировать ссылку на предзаполненную форму бронирования.

    Параметры room_type и offer_id берутся из результата search_available_rooms.

    Args:
        room_type: id категории номера
        offer_id: id тарифа/предложения
        check_in: дата заезда в формате ДД-ММ-ГГГГ
        check_out: дата выезда в формате ДД-ММ-ГГГГ
    """
    d_in, d_out = _validate_dates(check_in, check_out)
    nights = (d_out - d_in).days
    iso_date = d_in.strftime("%Y-%m-%d")

    return (
        f"{HOTEL_BOOKING_SITE_URL}?be-offer={offer_id}&room-type={room_type}"
        f"&date={iso_date}&nights={nights}"
    )


@tool
@safe_tool
def get_booking_management_info() -> str:
    """Объяснить гостю, как самостоятельно изменить или отменить существующую бронь."""
    return (
        "Чтобы изменить или отменить бронирование, перейдите по ссылке "
        "«Управлять бронированием» в письме-подтверждении, которое пришло на вашу "
        "почту после оформления брони. Там нужно ввести номер бронирования и код "
        "доступа, указанный в том же письме."
    )


def initialize_plugin() -> None:
    """Проверка обязательных настроек и создание клиентов перед стартом плагина."""
    global HOTEL_BOOKING_SITE_URL, travelline_client

    HOTEL_BOOKING_SITE_URL = require_env("HOTEL_BOOKING_SITE_URL")

    travelline_config = TravelLineConfig(
        client_id=require_env("TRAVELLINE_CLIENT_ID"),
        client_secret=require_env("TRAVELLINE_CLIENT_SECRET"),
        property_id=require_env("TRAVELLINE_PROPERTY_ID"),
    )
    travelline_client = TravelLineClient(travelline_config)


TOOLS = [search_available_rooms, generate_booking_link, get_booking_management_info]