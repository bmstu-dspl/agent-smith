from datetime import datetime

from dotenv import load_dotenv
from langchain_core.tools import tool

from errors import BookingUnavailableError, ValidationError, require_env, safe_tool
from travelline_client import TravelLineClient, TravelLineConfig

load_dotenv()

# Заполняется в initialize_plugin() перед стартом
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


def _format_room_stay(room_stay: dict) -> dict:
    """Превращает сырой ответ TravelLine в компактную структуру для LLM."""
    price = room_stay["total"]["priceBeforeTax"]
    loyalty_discount = _get_loyalty_discount(room_stay)

    return {
        "room_id": room_stay["roomType"]["id"],
        "rate_plan_id": room_stay["ratePlan"]["id"],
        "description": room_stay["fullPlacementsName"],
        "meal_plan": room_stay["mealPlanCode"],
        "price": price,
        "price_with_loyalty_discount": (price - loyalty_discount) if loyalty_discount else None,
        "currency": room_stay["currencyCode"],
        "free_cancellation_until": room_stay["cancellationPolicy"]["freeCancellationDeadlineLocal"],
        "penalty_amount": room_stay["cancellationPolicy"]["penaltyAmount"],
        "booking_link": room_stay["bookingFormLink"],
    }

def _get_loyalty_discount(room_stay: dict) -> float | None:
    """Ищет скидку за регистрацию в программе лояльности среди доступных скидок."""
    for discount in room_stay.get("availableDiscounts", []):
        if discount.get("reason") == "LoyaltyDiscount":
            return discount["amount"]
    return None



@tool
@safe_tool
async def search_available_rooms(
    check_in: str, check_out: str, adults: int, child_ages: list[int] | None = None
) -> list[dict]:
    """Найти доступные номера на указанные даты. Каждый результат уже содержит
    готовую ссылку на предзаполненную форму бронирования (booking_link) —
    её нужно просто отправить гостю, ничего дополнительно собирать не нужно.
    Похожие варианты с разной ценой могут отличаться условиями (например,
    штрафом за позднюю отмену — поле penalty_amount) — используй эти цифры,
    чтобы объяснить гостю разницу, если он спросит.

    Args:
        check_in: дата заезда в формате ДД-ММ-ГГГГ
        check_out: дата выезда в формате ДД-ММ-ГГГГ
        adults: количество взрослых, минимум 1. Гости от 12 лет считаются
            взрослыми — включайте их сюда, а не в child_ages
        child_ages: список возрастов детей младше 12 лет (например, [5, 8]);
            не указывать или оставить пустым, если детей до 12 лет нет
    """
    d_in, d_out = _validate_dates(check_in, check_out)
    if adults <= 0:
        raise ValidationError("Должен быть хотя бы один взрослый")
    for age in child_ages or []:
        if not (0 <= age <= 11):
            raise ValidationError(
                f"Некорректный возраст ребёнка: {age}. "
                "Дети принимаются до 11 лет включительно, гостей от 12 лет "
                "нужно указывать в adults"
            )

    room_stays = await travelline_client.search_room_stays(
        d_in.strftime("%Y-%m-%d"), d_out.strftime("%Y-%m-%d"), adults, child_ages
    )

    if not room_stays:
        raise BookingUnavailableError("На выбранные даты свободных номеров нет")

    return [_format_room_stay(rs) for rs in room_stays]


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
    global travelline_client

    travelline_config = TravelLineConfig(
        client_id=require_env("TRAVELLINE_CLIENT_ID"),
        client_secret=require_env("TRAVELLINE_CLIENT_SECRET"),
        property_id=require_env("TRAVELLINE_PROPERTY_ID"),
    )
    travelline_client = TravelLineClient(travelline_config)


TOOLS = [search_available_rooms, get_booking_management_info]