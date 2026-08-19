import os
from flask import Flask, render_template, request, session, redirect, url_for
import requests
from dotenv import load_dotenv
from collections import defaultdict
from datetime import datetime

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
API_KEY = os.getenv("OPENWEATHER_API_KEY")
BASE_URL = "https://api.openweathermap.org/data/2.5"


def clean_city(city):
    """Normalize city string for API calls, e.g. 'Lahore, PK' -> 'Lahore,PK'"""
    return city.replace(', ', ',').strip()


def get_weather(city, unit='metric'):
    url = f'{BASE_URL}/weather'
    params = {
        'q': clean_city(city),
        'appid': API_KEY,
        'units': unit
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if 'main' in data:
            return data
    return None


def get_hourly_forecast(city, unit='metric'):
    url = f'{BASE_URL}/forecast'
    params = {
        'q': clean_city(city),
        'appid': API_KEY,
        'units': unit
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        # 'list' contains forecasts every 3 hours; grab the next 8 (24 hours)
        return data['list'][:8]
    else:
        return None


def get_daily_forecast(city, unit='metric'):
    url = f'{BASE_URL}/forecast'
    params = {
        'q': clean_city(city),
        'appid': API_KEY,
        'units': unit
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        return None

    data = response.json()
    days = defaultdict(list)

    # group all 3-hour entries by date
    for entry in data['list']:
        date_str = entry['dt_txt'].split(' ')[0]  # e.g. '2026-08-03'
        days[date_str].append(entry)

    daily_summary = []
    for date_str, entries in days.items():
        temps = [e['main']['temp'] for e in entries]
        pops = [e.get('pop', 0) for e in entries]
        # pick the midday entry for a representative icon/description if available
        midday = next((e for e in entries if '12:00:00' in e['dt_txt']), entries[0])

        daily_summary.append({
            'date': datetime.strptime(date_str, '%Y-%m-%d').strftime('%A, %b %d'),
            'date_raw': date_str,
            'min_temp': round(min(temps)),
            'max_temp': round(max(temps)),
            'description': midday['weather'][0]['description'],
            'precipitation': round(max(pops) * 100),
            'hours': entries  # keep full 3-hour entries for "hourly for this day"
        })

    return daily_summary


def get_onecall(lat, lon, unit='metric'):
    url = f'{BASE_URL}/onecall'
    params = {
        'lat': lat,
        'lon': lon,
        'exclude': 'minutely,hourly,daily,alerts',
        'appid': API_KEY,
        'units': unit
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    return None


def icon_class_for(description):
    description = description.lower() if description else ''
    if 'rain' in description or 'drizzle' in description:
        return 'rain'
    if 'storm' in description or 'thunder' in description:
        return 'storm'
    if 'snow' in description:
        return 'snow'
    if 'clear' in description and 'night' in description:
        return 'moon'
    if 'clear' in description:
        return 'sun'
    if 'cloud' in description:
        return 'cloud'
    if any(term in description for term in ['mist', 'fog', 'haze', 'smoke']):
        return 'fog'
    return 'cloud'


app.jinja_env.globals['icon_class_for'] = icon_class_for


def get_city_cards(cities, unit='metric'):
    cards = []
    for city in cities:
        if len(cards) >= 4:
            break
        weather = get_weather(city, unit)
        if not weather:
            continue
        cards.append({
            'city': f"{weather.get('name', city)}, {weather.get('sys', {}).get('country', '')}",
            'temp': round(weather['main']['temp']),
            'max_temp': round(weather['main'].get('temp_max', weather['main']['temp'])),
            'min_temp': round(weather['main'].get('temp_min', weather['main']['temp'])),
            'description': weather['weather'][0]['description'].title(),
            'icon_class': icon_class_for(weather['weather'][0]['description'])
        })
    return cards


def build_home_weather(weather_data, hourly_data, weekly_data, unit='metric'):
    if not weather_data:
        return {
            'city': 'Unknown',
            'current_temp': '--',
            'temp_max': '--',
            'temp_min': '--',
            'condition': 'Unavailable',
            'condition_icon': 'cloud',
            'hourly': [],
            'weekly': [],
            'metrics': {
                'uv_index': 'N/A', 'precipitation': 'N/A', 'visibility': 'N/A',
                'pressure': 'N/A', 'humidity': 'N/A', 'wind': 'N/A',
                'sunrise': 'N/A', 'sunset': 'N/A'
            }
        }

    hourly_cards = []
    if hourly_data:
        for hour in hourly_data:
            hourly_cards.append({
                'time': hour['dt_txt'].split(' ')[1][:5],
                'temp': round(hour['main']['temp']),
                'icon': icon_class_for(hour['weather'][0]['description'])
            })

    weekly_cards = []
    if weekly_data:
        for day in weekly_data:
            date_parts = day['date'].split(', ')
            weekly_cards.append({
                'day': date_parts[0],
                'date': date_parts[1] if len(date_parts) > 1 else day['date'],
                'temp': day['max_temp'],
                'icon': icon_class_for(day['description'])
            })

    onecall = get_onecall(weather_data['coord']['lat'], weather_data['coord']['lon'], unit)
    uv_index = round(onecall['current']['uvi'], 1) if onecall and onecall.get('current') and 'uvi' in onecall['current'] else 'N/A'
    precipitation = 0
    if weather_data.get('rain'):
        precipitation = weather_data['rain'].get('1h', weather_data['rain'].get('3h', 0))
    elif weather_data.get('snow'):
        precipitation = weather_data['snow'].get('1h', weather_data['snow'].get('3h', 0))

    metrics = {
        'uv_index': uv_index,
        'precipitation': f"{precipitation} mm" if precipitation != 0 else '0 mm',
        'visibility': f"{round(weather_data.get('visibility', 0) / 1000, 1)} km",
        'pressure': f"{weather_data['main'].get('pressure', 0)} hPa",
        'humidity': f"{weather_data['main'].get('humidity', 0)}%",
        'wind': f"{round(weather_data['wind'].get('speed', 0), 1)} m/s",
        'sunrise': datetime.fromtimestamp(weather_data['sys']['sunrise']).strftime('%I:%M %p'),
        'sunset': datetime.fromtimestamp(weather_data['sys']['sunset']).strftime('%I:%M %p')
    }

    return {
        'city': f"{weather_data.get('name', '')}, {weather_data.get('sys', {}).get('country', '')}",
        'current_temp': round(weather_data['main']['temp']),
        'temp_max': round(weather_data['main'].get('temp_max', weather_data['main']['temp'])),
        'temp_min': round(weather_data['main'].get('temp_min', weather_data['main']['temp'])),
        'condition': weather_data['weather'][0]['description'].title(),
        'condition_icon': icon_class_for(weather_data['weather'][0]['description']),
        'hourly': hourly_cards,
        'weekly': weekly_cards,
        'metrics': metrics
    }
def get_weather_by_coords(lat, lon, unit='metric'):
    url = f'{BASE_URL}/weather'
    params = {
        'lat': lat,
        'lon': lon,
        'appid': API_KEY,
        'units': unit
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if 'main' in data:
            return data
    return None
@app.route('/use-current-location')
def use_current_location():
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    unit = session.get('unit', 'metric')
    if not lat or not lon:
        return redirect(url_for('locations'))

    weather_data = get_weather_by_coords(lat, lon, unit)
    if weather_data:
        city_name = weather_data.get('name', 'Current Location')
        country = weather_data.get('sys', {}).get('country', '')
        resolved_city = f"{city_name},{country}" if country else city_name
        return redirect(url_for('home', city=resolved_city))
    return redirect(url_for('locations'))

@app.route('/')
def home():
    city = request.args.get('city', 'Lahore')
    unit = session.get('unit', 'metric')
    dark_mode = session.get('dark_mode', True)
    weather_data = get_weather(city, unit)
    hourly_data = get_hourly_forecast(city, unit)
    weekly_data = get_daily_forecast(city, unit)
    weather_view = build_home_weather(weather_data, hourly_data, weekly_data, unit)

    saved = session.get('saved_cities', [])
    other_cities = [c for c in saved if c != city][:3]
    other_city_cards = get_city_cards(other_cities, unit) if other_cities else []

    return render_template(
        'home.html',
        weather=weather_view,
        other_cities=other_city_cards,
        city=city,
        unit=unit,
        unit_label='F' if unit == 'imperial' else 'C',
        dark_mode=dark_mode
    )


@app.route('/forecast')
def forecast():
    city = request.args.get('city', 'Lahore')
    unit = session.get('unit', 'metric')
    dark_mode = session.get('dark_mode', True)
    daily_data = get_daily_forecast(city, unit)
    today_hours = daily_data[0]['hours'] if daily_data else []
    return render_template(
        'forecast.html',
        daily=daily_data,
        today_hours=today_hours,
        city=city,
        unit=unit,
        unit_label='F' if unit == 'imperial' else 'C',
        dark_mode=dark_mode
    )


@app.route('/forecast/<date>')
def forecast_day(date):
    city = request.args.get('city', 'Lahore')
    unit = session.get('unit', 'metric')
    daily_data = get_daily_forecast(city, unit) or []

    selected_day = None
    for day in daily_data:
        if day['date_raw'] == date:
            selected_day = day
            break

    return render_template('forecast_day.html', day=selected_day, city=city, unit=unit)


@app.route('/details')
def details():
    city = request.args.get('city', 'Lahore')
    unit = session.get('unit', 'metric')
    dark_mode = session.get('dark_mode', True)
    weather_data = get_weather(city, unit)
    detail_cards = []
    if weather_data:
        onecall = get_onecall(weather_data['coord']['lat'], weather_data['coord']['lon'], unit)
        uv_index = round(onecall['current']['uvi'], 1) if onecall and onecall.get('current') and 'uvi' in onecall['current'] else 'N/A'
        precipitation = 0
        if weather_data.get('rain'):
            precipitation = weather_data['rain'].get('1h', weather_data['rain'].get('3h', 0))
        elif weather_data.get('snow'):
            precipitation = weather_data['snow'].get('1h', weather_data['snow'].get('3h', 0))

        detail_cards = [
            {'label': 'UV Index', 'value': uv_index, 'icon': 'uv'},
            {'label': 'Precipitation', 'value': f"{precipitation} mm", 'icon': 'rain'},
            {'label': 'Visibility', 'value': f"{round(weather_data.get('visibility', 0) / 1000, 1)} km", 'icon': 'visibility'},
            {'label': 'Pressure', 'value': f"{weather_data['main'].get('pressure', 0)} hPa", 'icon': 'pressure'},
            {'label': 'Humidity', 'value': f"{weather_data['main'].get('humidity', 0)}%", 'icon': 'humidity'},
            {'label': 'Wind', 'value': f"{round(weather_data['wind'].get('speed', 0), 1)} m/s", 'icon': 'wind'},
            {'label': 'Sunrise', 'value': datetime.fromtimestamp(weather_data['sys']['sunrise']).strftime('%I:%M %p'), 'icon': 'sunrise'},
            {'label': 'Sunset', 'value': datetime.fromtimestamp(weather_data['sys']['sunset']).strftime('%I:%M %p'), 'icon': 'sunset'}
        ]

    return render_template(
        'details.html',
        weather=weather_data,
        city=city,
        unit_label='F' if unit == 'imperial' else 'C',
        detail_cards=detail_cards,
        dark_mode=dark_mode
    )


@app.route('/locations', methods=['GET', 'POST'])
def locations():
    if 'saved_cities' not in session:
        session['saved_cities'] = []

    if request.method == 'POST':
        new_city = request.form.get('city')
        if new_city and new_city not in session['saved_cities']:
            session['saved_cities'].append(new_city)
            session.modified = True

    unit = session.get('unit', 'metric')
    default_cities = ['Miami, FL', 'Seattle, WA', 'Tokyo, JP', 'Paris, FR']
    lookup_cities = session['saved_cities'] if session['saved_cities'] else default_cities
    cards = get_city_cards(lookup_cities, unit)

    return render_template(
        'locations.html',
        saved_cities=session['saved_cities'],
        cards=cards,
        unit_label='F' if unit == 'imperial' else 'C'
    )


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if 'unit' not in session:
        session['unit'] = 'metric'  # default Celsius
    if 'dark_mode' not in session:
        session['dark_mode'] = False

    if request.method == 'POST':
        session['unit'] = request.form.get('unit', 'metric')
        session['dark_mode'] = 'dark_mode' in request.form  # checkbox present = True

    return render_template('settings.html', unit=session['unit'], dark_mode=session['dark_mode'])


if __name__ == "__main__":
    app.run(debug=True)