import logging
from datetime import datetime
from typing import Dict, Tuple

import aiohttp
from aiogram import Bot, Dispatcher, executor, types

from config import TELEGRAM_API_TOKEN, OPEN_WHETHER_API_TOKEN
from messages import *

# Configure logging
logging.basicConfig(format='%(levelname)-8s [%(asctime)s] %(name)s: %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize bot, dispatcher and storage
bot = Bot(token=TELEGRAM_API_TOKEN)
dp = Dispatcher(bot=bot)


@dp.message_handler(state='*', commands='start')
async def cmd_start(message: types.Message):
    """
    Conversation's entry point
    """
    await message.reply(text=MSG_ENTER_CITY)


@dp.message_handler(state='*')
async def location_handler(message: types.Message):
    """
    Do request to OpenWeatherMap API
    """
    city_from_msg = message.text.strip(' .,!&?@$#^*()_-=+"\'№%;:')  # Clearing a message
    forecast = await request_forecast(city=city_from_msg)
    if forecast:
        weather, precipitation, advice = parse_forecast(forecast)
        if precipitation or weather and advice:

            msg = MSG_FORECAST.format(*weather)
            msg += MSG_OUTFIT_ADVICE.format(*advice)
            if precipitation:
                msg += MSG_UMBRELLA_ADVICE

            await message.reply(text=msg)
        else:
            await message.reply(text=MSG_PARSE_ERROR)
    else:
        await message.reply(text=MSG_UNKNOWN.format(city_from_msg))


# ============================================================================
# OPENWEATHERMAP API REQUESTS
# ============================================================================

async def request_forecast(city: str) -> Dict or None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://api.openweathermap.org/data/2.5/forecast",
                                   params={'q': city,
                                           'units': 'metric',
                                           'lang': 'en',
                                           'APPID': OPEN_WHETHER_API_TOKEN}) as resp:
                data = await resp.json()
                if data['cod'] == '200':
                    logger.info(f"For the city '{city}' received forecast")
                    return data

    except aiohttp.ClientError as e:
        logger.error(e)

    except LookupError:
        logger.info(f"City with name '{city}' not found")


def parse_forecast(resp: Dict) -> Tuple or None:
    """
    Parse OpenWeatherMap response to format message for user.
    """
    utc_offset = resp['city']['timezone']
    today_dt = resp['list'][0]['dt'] - utc_offset

    today = datetime.fromtimestamp(today_dt).day  # number of the day in month
    weather_emodji = {
        'Thunderstorm': '🌩',
        'Drizzle': '🌦',
        'Rain': '🌧',
        'Snow': '🌨',
        'Atmosphere': '☁️',
        'Clear': '☀️',
        'Clouds': '⛅️'
    }
    try:
        city = resp['city']['name']
        country = resp['city']['country']

        current_temp = round(resp['list'][0]['main']['temp'])
        current_wind_speed = round(resp['list'][0]['wind']['speed'], ndigits=1)
        current_wind_direction = calc_wind_direction(resp['list'][0]['wind']['deg'])
        current_weather_desc = resp['list'][0]['weather'][0]['description']
        current_weather_emodji = weather_emodji[resp['list'][0]['weather'][0]['main']]

        # For advising an outfit
        precipitation = False
        min_temperature = round(resp['list'][0]['main']['temp_min'])
        min_feels_temperature = round(resp['list'][0]['main']['feels_like'])

        # Search min temperature today, umbrella checks
        for f in resp['list'][:8]:  # 8 - for reach max today forecasts (8 times each 3h)
            if datetime.fromtimestamp(f['dt'] - utc_offset).day == today:  # only for today
                if f['main']['feels_like'] < min_feels_temperature:
                    min_feels_temperature = round(f['main']['feels_like'])

                if f['main']['temp'] < min_temperature:
                    min_temperature = round(f['main']['temp'])

                # Precipitation check to advise an umbrella
                weather_id = f['weather'][0]['id'] // 100

                if 2 <= weather_id <= 5:  # 2-5 codes means precipitation
                    precipitation = True
                logger.debug(f'{weather_id} {precipitation}')
            else:  # if next day - break
                break

        outfit = get_outfit(min_feels_temperature)
        format_forecast = (
            (
                city,
                country,
                current_weather_emodji,
                current_weather_desc,
                current_temp,
                current_wind_direction,
                current_wind_speed,
            ),
            precipitation,
            (
                min_temperature,
                min_feels_temperature,
                outfit[0],
                outfit[1]
            )
        )
        return format_forecast

    except LookupError:
        logger.error('Parse error!')


def calc_wind_direction(deg: int) -> str:
    """
    Calculates wind direction by degrees.
    """
    assert 0 <= deg <= 360

    directions = ['N', 'NW', 'W', 'SW', 'S', 'SE', 'E', 'NE', 'N']
    return directions[round(deg / 45)]


def get_outfit(min_feels_temp: int) -> Tuple:
    """
    Match outfit to temperature.
    """
    if min_feels_temp > 40:
        return 'paranja', 'cap'
    if 40 >= min_feels_temp > 35:
        return 'swimsuit', 'swimming mask'
    elif 35 >= min_feels_temp > 30:
        return 'swimming trunks', 'slippers'
    elif 30 >= min_feels_temp > 25:
        return 'polo', 'shorts'
    elif 25 >= min_feels_temp > 20:
        return 't-shirt', 'sneakers'
    elif 20 >= min_feels_temp > 15:
        return 'sweatshirt', 'chinos'
    elif 15 >= min_feels_temp > 10:
        return 'hoodie', 'pants'
    elif 10 >= min_feels_temp > 5:
        return 'windbreaker', 'jeans'
    elif 5 >= min_feels_temp > 0:
        return 'leather jacket', 'chelsea',
    elif 0 >= min_feels_temp > -5:
        return 'cloak', 'gloves'
    elif -5 >= min_feels_temp > -10:
        return 'coat', 'scarf',
    elif -10 >= min_feels_temp > -15:
        return 'jacket', 'hat'
    elif -15 >= min_feels_temp > -20:
        return 'quilted jacket', 'shoes'
    elif -20 >= min_feels_temp > -25:
        return 'underpants', 'fur boots'
    elif -25 >= min_feels_temp > -30:
        return 'overalls', 'wool socks'
    elif -30 >= min_feels_temp > -35:
        return 'down jacket', 'felt boots'
    else:
        return 'thermal underwear', 'ski suit'


if __name__ == '__main__':
    executor.start_polling(dispatcher=dp,
                           skip_updates=True,
                           )
