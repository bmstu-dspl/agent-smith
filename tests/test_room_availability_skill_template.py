from pathlib import Path


SKILLS_DOC = Path(__file__).parents[1] / "docs" / "skills.md"


def test_room_availability_template_names_the_canonical_travelline_tool() -> None:
    instructions = SKILLS_DOC.read_text(encoding="utf-8")

    assert "`search_available_rooms`" in instructions
    assert "обычно его имя заканчивается" not in instructions


def test_room_availability_template_defines_ranked_three_item_pages() -> None:
    instructions = SKILLS_DOC.read_text(encoding="utf-8")
    normalized = instructions.lower()

    assert "не более 3" in instructions
    assert "самые подходящие" in instructions
    assert "есть ещё варианты" in instructions
    assert "не вызывай `search_available_rooms` повторно" in normalized


def test_room_availability_template_defines_rich_result_markup() -> None:
    instructions = SKILLS_DOC.read_text(encoding="utf-8")

    assert "**Название или категория номера**" in instructions
    assert "*Цена или варианты цены*" in instructions
    assert "[Забронировать](booking_link)" in instructions


def test_room_availability_template_loads_details_once_per_visible_page() -> None:
    instructions = SKILLS_DOC.read_text(encoding="utf-8")

    assert "`get_room_details`" in instructions
    assert "не более 3 `room_id`" in instructions
    assert "один раз для текущей тройки" in instructions
    assert "именно в текущем ходе агента" in instructions
    assert "Предыдущий вызов `get_room_details` не считается" in instructions
    assert "`image_urls`" in instructions


def test_room_availability_template_tracks_unseen_room_ids_between_pages() -> None:
    instructions = SKILLS_DOC.read_text(encoding="utf-8")

    assert "упорядоченную очередь уникальных `room_id`" in instructions
    assert "следующей тройки непоказанных `room_id`" in instructions
    assert "не повторяй ранее показанные категории" in instructions
