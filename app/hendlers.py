from aiogram import F , Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

import app.keyboards as kb 

router= Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.reply(f'Привет {message.from_user.first_name} !',
                        ##reply_markup=kb.settings)
                        reply_markup= kb.main)


@router.message(Command('help'))
async def get_help(message: Message):
    await message.reply('Это команда /help',
                        reply_markup= await kb.inline_services())

@router.message(F.text == 'Как дела?')
async def how_are_you(message: Message):
    await message.answer('ОК!')

@router.message(F.photo)
async def get_photo(message: Message):
    await message.answer(f'ID фото: {message.photo[-1].file_id}')
