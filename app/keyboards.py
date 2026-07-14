from aiogram.types import (ReplyKeyboardMarkup, KeyboardButton,
                           InlineKeyboardMarkup,InlineKeyboardButton)

from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

main=ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text='Отели')],
    [KeyboardButton(text='Избранное'), KeyboardButton(text='Мои брони')]
    ],
    resize_keyboard=True,
    input_field_placeholder='Выберите пункт ниже')

settings = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
    text='авиасейлс',url='https://www.aviasales.ru/hotels?source=promo_hotels_tooltip')]
    ])

services = ['авиасейлс', 'суточно.ру', 'Яндекс Путешествия']

async def inline_services():
    keyboard = InlineKeyboardBuilder()
    for service in services:
        keyboard.add(InlineKeyboardButton(text=service, url='https://www.aviasales.ru/hotels?source=promo_hotels_tooltip'))
    return keyboard.adjust(2).as_markup()