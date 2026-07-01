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

@router.message(Command('get_photo'))
async def get_photo(message: Message):
    await message.answer_photo(photo='https://yandex.ru/images/search?img_url=https%3A%2F%2Fmedia.istockphoto.com%2Fid%2F2152934415%2Fru%2F%25D1%2584%25D0%25BE%25D1%2582%25D0%25BE%2F%25D0%25BC%25D0%25B0%25D0%25BB%25D0%25B5%25D0%25BD%25D1%258C%25D0%25BA%25D0%25B8%25D0%25B9-%25D0%25B8%25D0%25B3%25D1%2580%25D0%25B8%25D0%25B2%25D1%258B%25D0%25B9-%25D1%2588%25D0%25BE%25D1%2582%25D0%25BB%25D0%25B0%25D0%25BD%25D0%25B4%25D1%2581%25D0%25BA%25D0%25B8%25D0%25B9-%25D0%25BA%25D0%25BE%25D1%2582%25D0%25B5%25D0%25BD%25D0%25BE%25D0%25BA-%25D1%2581-%25D0%25BA%25D0%25BE%25D1%2580%25D0%25BE%25D1%2582%25D0%25BA%25D0%25B8%25D0%25BC%25D0%25B8-%25D0%25BB%25D0%25B0%25D0%25BF%25D0%25BA%25D0%25B0%25D0%25BC%25D0%25B8.jpg%3Fs%3D612x612%26w%3D0%26k%3D20%26c%3DL1gZegkpyoA7wyxg3xuNhF6vPgMaIciAXoYHzrkM_OM%3D&lr=10740&pos=1&rpt=simage&source=serp&text=котенка',
                               caption='Это кот')
