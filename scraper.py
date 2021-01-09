#!/usr/bin/env python3
"""
Lincensed under the MIT License.
See LICENSE file for more information.
"""

import json
import re
import sys
import unicodedata
from pathlib import Path
from zipfile import ZipFile

import requests
import tbapy

#
# Define constants that the program uses
#

# Load the auth key
AUTH_PATH = Path('tba_token.txt')
if not AUTH_PATH.exists():
    print('Error: the tba_token.txt file does not exist! You must generate a'
          + ' Read API authorization key on The Blue Alliance website. This can be'
          + ' done at: https://www.thebluealliance.com/account. Place the generated'
          + ' Read API Key in a file named tba_token.txt')
    sys.exit()

AUTH_KEY = AUTH_PATH.read_text().strip()

# Load the year from the YEAR file
YEAR = Path('YEAR').read_text().strip()
print(f'Downloaded data for year {YEAR}')

# The directory where downloaded GeoNames data is cached
CACHE_DIR = Path.cwd() / 'cache'

# When the latitude/longitude location of a place cannot be found, it is put
# into the broken_places file. This file is deleted (and recreated if needed)
# with each run of the scraper.
BROKEN_PLACES_FILE = CACHE_DIR / 'broken_places'


class GeoNamesFile():
    """
    A helper class to hold the url and name of a GeoNames file as
    well as if it needs to be unzipped after download.
    """

    def __init__(self, url, name, unzip):
        self.url = url
        self.name = name
        self.unzip = unzip


# What GeoNames files to download, name to save them as (within
# CACHE_DIR), and whether or not they need to be unzipped.
POSTAL_FILES = [
    GeoNamesFile(url='https://download.geonames.org/export/zip/allCountries.zip',
                 name='allCountries.zip',
                 unzip=True),
    GeoNamesFile(url='https://download.geonames.org/export/dump/readme.txt',
                 name='allCountries.readme',
                 unzip=False),
    GeoNamesFile(url='https://download.geonames.org/export/dump/cities1000.zip',
                 name='cities1000.zip',
                 unzip=True),
    GeoNamesFile(url='https://download.geonames.org/export/dump/readme.txt',
                 name='cities1000.readme',
                 unzip=False),
    GeoNamesFile(url='https://download.geonames.org/export/dump/admin1CodesASCII.txt',
                 name='admin1CodesASCII.txt',
                 unzip=False),
    GeoNamesFile(url='https://download.geonames.org/export/dump/countryInfo.txt',
                 name='countryInfo.txt',
                 unzip=False)
]

# The attributes to copy from teams into the output. In the original AWK
# scripts, this was automatically loaded from a file called `attribs`. These
# are the attributes that are stored in `teamFullInfo.json`. `team.json` only
# has the team numbers and their associated latitude and longitude
# coordinates.
TEAM_ATTRIBS = [
    'address',
    'city',
    'country',
    'gmaps_place_id',
    'gmaps_url',
    'home_championship',
    'key',
    'lat',
    'lng',
    'location_name',
    'motto',
    'name',
    'nickname',
    'postal_code',
    'rookie_year',
    'state_prov',
    'team_number',
    'website'
]

# Additional country code mappings. Currently, this adds country
# codes for Czech Republic (CZ) and Chinese Taipei (TW) because
# those are the names used by FIRST/TBA, but Geonames has those
# countries listed as Czechia and Taiwan, respectively.
# It also adds the mapping of USA to US because TBA returns USA
# but Geonames has the country name United States.
# This dictionary is used in load_geonames_data
EXTRA_COUNTRY_CODES = {
    'Chinese Taipei': 'TW',
    'Czech Republic': 'CZ',
    'USA': 'US'
}

# The chunk size used when downloading files from GeoNames.
DOWNLOAD_CHUNK_SIZE = 16384

#
# Initial program setup
#

# Set up caching
if not CACHE_DIR.exists():
    CACHE_DIR.mkdir()
elif CACHE_DIR.is_file():
    print(f'Error: file "{str(CACHE_DIR)}" exists where the cache directory'
          + ' is supposed to be created! Please delete the file!')
    sys.exit()

# Delete the current broken_places file if it exists
if BROKEN_PLACES_FILE.exists():
    BROKEN_PLACES_FILE.unlink()


#
# Function definitions
#

def get_geonames_data(use_cache):
    """
    Download and unzips all the information from GeoNames into
    CACHE_DIR.
    """
    print('Downloading GeoNames data...')

    for file in POSTAL_FILES:
        print(f'Downloading {file.url}...')

        path = CACHE_DIR / file.name

        # Download the file from the URL and save it (except in cache mode,
        # where the already-downloaded file is used if it exists). Download in
        # streaming mode so the entire file is not loaded into memory
        # before saving.
        if not use_cache or not path.exists():
            with requests.get(file.url, stream=True) as req:
                # If there is an error downloading, just crash
                req.raise_for_status()

                with open(path, 'wb') as writer:
                    for chunk in req.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                        writer.write(chunk)

        # If the file is a zip file, extract it to the data directory
        if file.unzip:
            print('Unzipping...')
            with ZipFile(path, 'r') as zip:
                zip.extractall(CACHE_DIR)


def load_geonames_data():
    """Load all the GeoNames data from the downloaded files."""
    print('Loading GeoNames data...')

    #
    # Definitions
    #
    geo_names = {}

    # Function to read this specific format of TSV files GeoNames provides. It
    # reads the file line by line (row by row) and breaks each row into
    # columns, calling callback with each row (as a list of columns). The sep
    # parameter changes the separator, so it can read CSV files, etc. as well.
    def read_tsv(file, callback, sep='\t'):
        with open(file, 'rt', encoding='utf-8') as reader:
            for line in reader:
                # Skip empty and blank lines and comments (which start with #)
                if line.lstrip().startswith('#') or not line or line.isspace():
                    continue
                row = line.split(sep)
                callback(row)

    #
    # Initialize the country codes table
    #
    print('Loading country code mappings...')
    geo_names['ccodes'] = {}

    # Fill in the country codes table with data from CACHE_DIR/countryInfo.txt
    def process_ccode_row(row):
        geo_names['ccodes'][row[4]] = row[0]

    read_tsv(CACHE_DIR / 'countryInfo.txt', process_ccode_row)

    # Add/replace additional country code mappings
    for country in EXTRA_COUNTRY_CODES:
        geo_names['ccodes'][country] = EXTRA_COUNTRY_CODES[country]

    # Remove the empty string key from the table, if it exists
    geo_names['ccodes'].pop('', None)

    #
    # Initialize the zipLocs dictionary, which contains latitude and
    # longitude coordinates for every zip code of every country in
    # allCountries.txt.
    #
    print('Loading zip code locations...')
    geo_names['zipLocs'] = {}

    # Fill in the zipLocs table with data from CACHE_DIR/allCountries.txt
    # The first key is the country code (row[0]), the second key is the zip
    # (row[1]), and row[9] and row[10] are latitude and longitude coordinates,
    # respectively.
    def process_zip_data_col(row):
        # Name the country and zip all uppercase (some zip codes have letters)
        ccode = row[0].upper()
        zip = row[1].upper()

        # If the country's entry doesn't exist, initialize it.
        if not ccode in geo_names['zipLocs']:
            geo_names['zipLocs'][ccode] = {}

        # Assign the zip's lat and lng in the dictionary.
        geo_names['zipLocs'][ccode][zip] = {
            'lat': row[9],
            'lng': row[10]
        }

    read_tsv(CACHE_DIR / 'allCountries.txt', process_zip_data_col)

    #
    # Initialize the adms dictionary, which maps administrative division
    # codes to their ASCII encoded English names. For example, the
    # administrative division code US.AK maps to the name Alaska. These
    # mappings come from admin1CodesASCII.txt
    #
    print('Loading administrative division names...')
    geo_names['adms'] = {}

    def process_admin_codes(row):
        # row[0] is the administrative division code, row[2] is the ASCII
        # encoded English name of the administrative division code. For
        # example, the ascii encoded name for São Paulo would be Sao Paulo (ã
        # is replaced with a)
        geo_names['adms'][row[0]] = row[2].upper()

    read_tsv(CACHE_DIR / 'admin1CodesASCII.txt', process_admin_codes)

    #
    # Initialize the cities dictionary, which holds the latitude and
    # longitude coordinates for each city in cities1000.txt. The dictionary
    # is actually a dictionary with country names as the keys, where each key
    # maps to a dictionary with state/province names as keys, where each key
    # maps to a dictionary with cities as keys, where each key maps to a
    # dictionary with a lat and lng entry for the latitude and longitude of
    # that city.
    #
    # In other words, the format is:
    #
    # geoNames['cities'] = {
    #     'United States': {
    #         'New Hampshire': {
    #             'Manchester': {
    #                 'lat': 42.99564,
    #                 'lng': -71.45479
    #             }
    #             # ... more cities in New Hampshire
    #         }
    #         # ... more states in the US
    #     }
    #     # ... more countries
    # }
    #
    print('Loading city locations...')
    geo_names['cities'] = {}

    # Load the latitude and longitude for each city in cities1000.txt and put
    # them in geoNames['cities']
    def process_cities(row):
        city_name_ascii = row[2].upper()
        country_code = row[8]
        state_code = row[10]
        # Name of the administrative division (state, province, etc.)
        # See comment above about the adms dictionary for further explanation.
        admin_name_ascii = geo_names['adms'].get(f'{country_code}.{state_code}')

        # Ignore nonexistant administrative divisions
        if not admin_name_ascii:
            return

        # This helper function puts the latitude and longitude of the city
        # into the cities table (see comment at the beginning of this section
        # for information about the format of the cities table)
        def setLatLng(country, state, city):
            if not country in geo_names['cities']:
                geo_names['cities'][country] = {}

            if not state in geo_names['cities'][country]:
                geo_names['cities'][country][state] = {}

            geo_names['cities'][country][state][city] = {
                'lat': row[4],
                'lng': row[5]
            }

        # Set the latitude and longitude of the city for the current row
        setLatLng(country_code, admin_name_ascii, city_name_ascii)

        if country_code == 'TW':
            # For Taiwan, use the city name for both the city name and
            # administrative division name (this is how the locations come from
            # TBA)
            setLatLng(country_code, city_name_ascii, city_name_ascii)
        elif country_code == 'IL':
            # Apparently Israel has bad district names and sometimes uses the
            # alternative city names, so the country code is used for the
            # administrative division name and all alternative names for cities
            # are added (in addition to the regular city name, which was
            # already added above, before the if statement). Alternative names
            # are put in all caps.
            alt_names = row[3].upper().split(',')

            for name in alt_names:
                setLatLng(country_code, country_code, name)

    read_tsv(CACHE_DIR / 'cities1000.txt', process_cities)

    #
    # Load the coordinates from the geo_cache file that were
    # manually obtained. Some team locations have to be manually
    # obtained because their locations cannot be resolved using
    # the GeoNames data alone, often due to incomplete data from
    # TBA. This usually involves the user of the scraper finding
    # the actual location of the team by looking at information
    # on TBA, etc., and then finding the lat/lng coordinates on
    # Google Maps. The user is walked through this when running
    # the ask_google script.
    #
    print('Loading manually cached locations...')
    geo_names['googLocs'] = {}

    # geo_cache file format:
    # place name|latitude coordinate|longitude coordinate
    def processGeoCache(row):
        geo_names['googLocs'][row[0]] = {
            'lat': row[1],
            'lng': row[2]
        }

    read_tsv(Path.cwd() / 'geo_cache', processGeoCache, '|')

    return geo_names


def get_team_data(tba):
    """Download all of the team information from The Blue Alliance."""
    print('Downloading team data from The Blue Alliance...')
    return tba.teams(page=None, year=YEAR)


def strip_unicode(str):
    """Replace unicode characters with ascii characters (e.g., replace é with e)."""
    # Documentation for normalize function:
    # https://docs.python.org/3/library/unicodedata.html#unicodedata.normalize
    # Basically, (from what I understand) this splits the characters with accent
    # marks, etc. (e.g. é) into two parts: the latin character (e.g. e) and a
    # special "combining" character that represents the accent. The string is then
    # encoded into ascii with the 'ignore' option, so it ignores characters that
    # cannot be represented in ascii, thus removing the special combining characters
    # but leaving behind the regular ones. The resulting binary is then decoded back
    # into utf-8.
    return (unicodedata.normalize('NFD', str)
            .encode('ascii', 'ignore')
            .decode('utf-8'))


def process_team_data(geo_names, team_data):
    """
    Process all of the data that has been downloaded and write it to
    teams.json and teamFullInfo.json.
    """
    print('Processing and writing team info...')

    short_team_list = []
    long_short_team_list = []

    for team in team_data:
        # Only include the home_championship attribute for the current year
        home_champ = team.get('home_championship')
        if home_champ:
            team['home_championship'] = home_champ.get(YEAR)

        # Get the team's city name and convert it to uppercase and ASCII (must
        # be converted to ASCII because load_geonames_data loads location names
        # as ASCII). Also remove leading and trailing spaces from the city name
        # because sometimes the city name comes with them.
        city_no_format = team.get('city') or ''
        city = strip_unicode(city_no_format.upper().strip(' '))

        # Get the country code for the team's country.
        country_code = geo_names['ccodes'].get(team.get('country')) or ''

        # Get the team's state/provice/administrative division and convert to
        # uppercase ASCII.
        prov_no_format = team.get('state_prov') or ''
        province = strip_unicode(prov_no_format.upper())

        # Team's postal code
        zip_code = team.get('postal_code') or ''

        # Needs to be uppercase (postal codes in some countries have letters)
        zip_code = zip_code.upper()

        # ====== special fixes for Guam, zip weirdness, and some typos ======
        if not country_code and zip_code:
            # If there is no country code, determine it by the format of the
            # postal code.
            if zip_code == '11073':
                country_code = 'TW'
            elif zip_code == '34912' or zip_code == '34469':
                country_code = 'TR'
            elif zip_code == '93810':
                country_code = 'IL'
            elif re.search('^[0-9]{4}$', zip_code):
                country_code = 'AU'
            elif re.search('^[0-9]{5}$', zip_code) or re.search('^[0-9]{5}-[0-9]{4}$', zip_code):
                country_code = 'US'
            elif re.search('^[0-9]{5}-[0-9]{3}$', zip_code):
                country_code = 'BR'
            elif re.search('^[A-Z][0-9][A-Z] [0-9][A-Z][0-9]$', zip_code):
                country_code = 'CA'
            elif re.search('^[0-9]{7}$', zip_code):
                country_code = 'IL'

        if country_code == 'SE' and re.search('^[0-9]{5}', zip_code):
            # For Sweden, put a space between the first three and last two
            # postal code digits (e.g., 12345 becomes 123 45)
            zip_code = f'{zip_code[0:3]} {zip_code[3:5]}'

        if country_code == 'US':
            if province == 'GUAM':
                country_code = 'GU'
            elif province == 'PUERTO RICO':
                country_code = 'PR'
            elif city == 'NEW YORK':
                city = 'NEW YORK CITY'
            elif province == 'PA' and city == 'WARMINSTER':
                city = 'WARMINSTER HEIGHTS'
            elif province == 'MO' and city == 'LEES SUMMIT':
                city = "LEE'S SUMMIT"

        if country_code == 'CL' and province == 'REGION METROPOLITANA DE SANTIAGO':
            province = 'SANTIAGO METROPOLITAN'

        if country_code == 'GR' and province == 'THESSALIA':
            province = 'THESSALY'

        if country_code == 'MX':
            if city == 'SAN LUIS POTOTOSI':
                city = 'SAN LUIS POTOSI'
            if province == 'DISTRITO FEDERAL':
                province = 'MEXICO CITY'

        if country_code == 'TR' and city == 'CEKMEKOY':
            city = 'CEKMEKOEY'

        if country_code == 'NL' and province == 'NOORD-BRABANT':
            province = 'NORTH BRABANT'

        if country_code == 'DO' and province == 'SANTO DOMINGO' and city == province:
            province = 'NACIONAL'

        if country_code == 'IL':
            # Israel has multiple names for administrative divisions, so this
            # scraper just ignores them completely.
            province = 'IL'

        if country_code == 'JP' and len(zip_code) == 7:
            # For Japan, separate first three and last four digits with a dash
            # (e.g., 1234567 becomes 123-4567)
            f'{zip_code[0:3]}-{zip_code[3:7]}'

        if country_code == 'CA':
            # special for Canada, only first three digits of zip code
            zip_code = zip_code[0:3]
            
        if country_code == 'TW':
            # This fixes certain locations in Taiwan where the province name has
            # SPECIAL MUNICIPALITY or MUNICIPALITY tacked on the end some of the
            # time.
            if province.endswith(' SPECIAL MUNICIPALITY'):
                province = province[:-len(' SPECIAL MUNICIPALITY')]
            elif province.endswith(' MUNICIPALITY'):
                province = province[:-len(' MUNICIPALITY')]
        # ======== end of special fixes ========

        # The latitude and longitude coordinates of the team
        lat = lng = None

        # Retrieve the latitude and longitude of the team from the zip code,
        # if available.
        zip_country = geo_names['zipLocs'].get(country_code)

        if zip_country:
            zip_loc = zip_country.get(zip_code)

            if zip_loc:
                lat = zip_loc['lat']
                lng = zip_loc['lng']

        # If the location was not retrieved...
        if lat is None and country_code in geo_names['cities']:
            # Retrieve the latitude and longitude of the team from the city,
            # state/provice/administrative division, and country code
            city_country = geo_names['cities'][country_code]

            if province in city_country:
                city_prov = city_country[province]

                if city in city_prov:
                    city_loc = city_prov.get(city)
                    lat = city_loc['lat']
                    lng = city_loc['lng']

        # If the location was still not retrieved...
        if lat is None:
            # Get the location from cached locations that were manually
            # retrieved (see googLocs section of load_geonames_data)
            place = f'{city}, {province} {zip_code}, {country_code}'
            goog_loc = geo_names['googLocs'].get(place)

            if goog_loc:
                lat = goog_loc['lat']
                lng = goog_loc['lng']

        # If the location was STILL not retrieved...
        if lat is None:
            # Notify the user that the location was not found and needs to be
            # manually retrieved. Append the place to the broken_places file
            # (the file is emptied at the beginning of the script).
            print(f'Did not find team {team.get("key")} @ place {place}')

            with open(BROKEN_PLACES_FILE, 'a') as broken_places:
                broken_places.write(place + '\n')

            lat = 0
            lng = 0

        # Convert lat and lng to numbers (so they don't have quotation
        # marks around them in the JSON) and round them to 3 digits after
        # the decimal.
        lat = round(float(lat), 3)
        lng = round(float(lng), 3)

        team['lat'] = lat
        team['lng'] = lng

        # Write the team number and lat/lng
        short_team = {
            'team_number': team.get('team_number'),
            'lat': team.get('lat'),
            'lng': team.get('lng')
        }

        short_team_list.append(short_team)

        # Write out the full team info
        long_short_team = {}

        for att in TEAM_ATTRIBS:
            long_short_team[att] = team.get(att)

        long_short_team_list.append(long_short_team)

    with open(Path.cwd() / 'teams.json', 'w') as out:
        # When creating the JSON for the team location data, these string
        # replaces put each team on its own line. It looks like this:
        # [
        #   # ...more teams...
        #   {"team_number": 404, "lat": 1.234, "lng": 5.678},
        #   # ...more teams...
        # ]
        # This is compact but readable (making it easy to tell what changed
        # when looking at a diff), but the main reason I format it this way is
        # that this was the format on the previous scraper.
        output = (json.dumps(short_team_list)
                  .replace('[{', '[\n\t{')
                  .replace('}, ', '},\n\t')
                  .replace('}]', '}\n]'))
        out.write(output)

    with open(Path.cwd() / 'teamFullInfo.json', 'w') as outFull:
        # For full team data, just output with standard JSON formatting
        output = json.dumps(long_short_team_list, indent=4)
        outFull.write(output)


# If the program is run with the command line argument usecache, any of the
# GeoNames files that have already been downloaded to the cache directory will
# be used instead of redownloading them. The purpose of this is to not have to
# redownload the Geonames data every time if the program has to be run several
# times in a row to resolve issues, etc.
use_cache = False

if len(sys.argv) > 1 and sys.argv[1].lower() == 'usecache'.lower():
    use_cache = True

tba = tbapy.TBA(AUTH_KEY)

get_geonames_data(use_cache)
geo_names = load_geonames_data()
team_data = get_team_data(tba)
process_team_data(geo_names, team_data)
