#!/usr/bin/env python3
"""
MIT License

Copyright (c) 2020 Ethan Shaw

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib import request
from zipfile import ZipFile

import requests
import tbapy
from cachecontrol import CacheControl
from cachecontrol.caches import FileCache

"""
Define constants that the program uses
"""

AUTH_KEY = Path('TBA-auth').read_text().strip()

YEAR = Path('YEAR').read_text().strip()

CACHE_DIR = Path.cwd() / 'cache'

# When the lattitude/longitude location of a place cannot be found, it is put
# into the broken_places file. This file is deleted (and recreated if needed)
# with each run of the scraper.
BROKEN_PLACES_FILE = CACHE_DIR / 'broken_places'

# What files to download, name to save them as (within CACHE_DIR), and whether or not they need to be unzipped.
POSTAL_FILES = [
    [ 'https://download.geonames.org/export/zip/allCountries.zip',       'allCountries.zip',     True  ],
    [ 'https://download.geonames.org/export/dump/readme.txt',            'allCountries.readme',  False ],
    [ 'https://download.geonames.org/export/dump/cities1000.zip',        'cities1000.zip',       True  ],
    [ 'https://download.geonames.org/export/dump/readme.txt',            'cities1000.readme',    False ],
    [ 'https://download.geonames.org/export/dump/admin1CodesASCII.txt',  'admin1CodesASCII.txt', False ],
    [ 'https://download.geonames.org/export/dump/countryInfo.txt',       'countryInfo.txt',      False ]
]

# The attributes to copy from teams into the output. In the original AWK scripts,
# this was automatically loaded from a file called `attribs`
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
# countries listed as Czechia Prague and Taiwan, respectively.
# It also adds the mapping of USA to US because TBA returns USA
# but Geonames has the country name United States.
# This dictionary is used in load_geonames_data
EXTRA_COUNTRY_CODES = {
    'Chinese Taipei': 'TW',
    'Czech Republic': 'CZ',
    'USA': 'US'
}


"""
Define global variables
"""

tba = tbapy.TBA(AUTH_KEY)
teamData = None
geoNames = {}

# Set up caching
if not CACHE_DIR.exists():
    CACHE_DIR.mkdir()
elif CACHE_DIR.is_file():
    print(f'Error: file "{str(CACHE_DIR)}" exists where the cache directory is supposed to be created!')
    print('Please delete the file!')
    sys.exit()

cache = CacheControl(requests.Session(), cache=FileCache(CACHE_DIR / '.geo_cache'))

# Delete the current broken_places file if it exists
if BROKEN_PLACES_FILE.exists():
    BROKEN_PLACES_FILE.unlink()

"""
Function definitions
"""

# Downloads and unzips all the information from GeoNames into CACHE_DIR
def get_geonames_data():
    print ("Downloading GeoNames data...")

    for file in POSTAL_FILES:
        print(f'Downloading {file[0]}...')

        path = CACHE_DIR / file[1]

        # Download the file from the URL and save it. Download in
        # streaming mode so the entire file is not loaded into memory
        # before saving.
        with cache.get(file[0], stream=True) as req:
            # If there is an error downloading, just crash
            req.raise_for_status()

            with open(path, 'wb') as writer:
                for chunk in req.iter_content(chunk_size=16384):
                    writer.write(chunk)

        # If the file is a zip file, extract it to the data directory
        if file[2]:
            print("Unzipping...")
            with ZipFile(path, 'r') as zip:
                zip.extractall(CACHE_DIR)


# Loads all the GeoNames data from the downloaded files
def load_geonames_data():
    print("Loading GeoNames data...")

    """ Definitions """
    global geoNames

    # Function to read this specific format of TSV files GeoNames provides. It
    # reads the file line by line (row by row) and breaks each row into
    # columns, calling callback with each row (as a list of columns). The sep
    # parameter changes the separator, so it can read CSV files, etc. as well.
    def readTSV(file, callback, sep='\t'):
        with open(file, 'rt', encoding='utf-8') as reader:
            for line in reader:
                # Skip empty and blank lines and comments (which start with #)
                if line.lstrip().startswith('#') or not line or line.isspace():
                    continue
                row = line.split(sep)
                callback(row)


    """ Initialize the country codes table """
    print ("Loading country code mappings...")
    geoNames['ccodes'] = {}

    # Fill in the country codes table with data from CACHE_DIR/countryInfo.txt
    def processCCodeRow(row):
        geoNames['ccodes'][row[4]] = row[0]
    
    readTSV(CACHE_DIR / 'countryInfo.txt', processCCodeRow)

    # Add/replace additional country code mappings
    for country in EXTRA_COUNTRY_CODES:
        geoNames['ccodes'][country] = EXTRA_COUNTRY_CODES[country]
    
    # Remove the empty string key from the table, if it exists
    geoNames['ccodes'].pop('', None)


    """
        Initialize the zipLocs dictionary, which contains lattitude and
        longitude coordinates for every zip code of every country in
        allCountries.txt.
    """
    print("Loading zip code locations...")
    geoNames['zipLocs'] = {}

    # Fill in the zipLocs table with data from CACHE_DIR/allCountries.txt
    # The first key is the country code (row[0]), the second key is the zip
    # (row[1]), and row[9] and row[10] are lattitude and longitude coordinates,
    # respectively.
    def processZipDataCol(row):
        # Name the country and zip all uppercase (some zip codes have letters)
        ccode = row[0].upper()
        zip = row[1].upper()

        # If the country's entry doesn't exist, initialize it.
        if not ccode in geoNames['zipLocs']:
            geoNames['zipLocs'][ccode] = {}
        
        # Assign the zip's lat and lng in the dictionary.
        geoNames['zipLocs'][ccode][zip] = {
            'lat': row[9],
            'lng': row[10]
        }

    readTSV(CACHE_DIR / 'allCountries.txt', processZipDataCol)


    """
        Initialize the adms dictionary, which maps administrative division
        codes to their ASCII encoded English names. For example, the
        administrative division code US.AK maps to the name Alaska. These
        mappings come from admin1CodesASCII.txt
    """
    print ("Loading administrative division names...")
    geoNames['adms'] = {}

    def proccessAdminCodes(row):
        # row[0] is the administrative division code, row[2] is the ASCII
        # encoded English name of the administrative division code. For
        # example, the ascii encoded name for São Paulo would be Sao Paulo (ã
        # is replaced with a)
        geoNames['adms'][row[0]] = row[2].upper()

    readTSV(CACHE_DIR / 'admin1CodesASCII.txt', proccessAdminCodes)


    """
        Initialize the cities dictionary, which holds the lattitude and
        longitude coordinates for each city in cities1000.txt. The dictionary
        is actually a dictionary with country names as the keys, where each key
        maps to a dictionary with state/province names as keys, where each key
        maps to a dictionary with cities as keys, where each key maps to a
        dictionary with a lat and lng entry for the lattitude and longitude of
        that city.

        In other words, the format is:

        geoNames['cities'] = {
            'United States': {
                'New Hampshire': {
                    'Manchester': {
                        'lat': 42.99564,
                        'lng': -71.45479
                    }
                    # ... more cities in New Hampshire
                }
                # ... more states in the US
            }
            # ... more countries
        }
    """
    print ("Loading city locations...")
    geoNames['cities'] = {}

    # Load the lattitude and longitude for each city in cities1000.txt and put
    # them in geoNames['cities']
    def proccessCities(row):
        cityNameAscii = row[2].upper()
        countryCode = row[8]
        stateCode = row[10]
        # Name of the administrative division (state, province, etc.)
        # See comment above about the adms dictionary for further explanation.
        adminNameAscii = geoNames['adms'].get(f'{countryCode}.{stateCode}')

        # Ignore nonexistant administrative divisions
        if not adminNameAscii:
            return
        
        # This helper function puts the lattitude and longitude of the city
        # into the cities table (see comment at the beginning of this section
        # for information about the format of the cities table)
        def setLatLng(country, state, city):
            if not country in geoNames['cities']:
                geoNames['cities'][country] = {}
            
            if not state in geoNames['cities'][country]:
                geoNames['cities'][country][state] = {}

            geoNames['cities'][country][state][city] = {
                'lat': row[4],
                'lng': row[5]
            }
        
        # Set the lattitude and longitude of the city for the current row
        setLatLng(countryCode, adminNameAscii, cityNameAscii)
        
        if countryCode == 'TW':
            # For Taiwan, use the city name for both the city name and
            # administrative division name (this is how the locations come from
            # TBA)
            setLatLng(countryCode, cityNameAscii, cityNameAscii)
        elif countryCode == 'IL':
            # Apparently Israel has bad district names and sometimes uses the
            # alternative city names, so the country code is used for the
            # administrative division name and all alternative names for cities
            # are added (in addition to the regular city name, which was
            # already added above, before the if statement). Alternative names
            # are put in all caps.
            altNames = row[3].upper().split(',')

            for name in altNames:
                setLatLng(countryCode, countryCode, name)

    readTSV(CACHE_DIR / 'cities1000.txt', proccessCities)


    """
        Load the coordinates from the geo_cache file that were
        manually obtained. Some team locations have to be manually
        obtained because their locations cannot be resolved using
        the GeoNames data alone, often due to incomplete data from
        TBA. This usually involves the user of the scraper finding
        the actual location of the team by looking at information
        on TBA, etc., and then finding the lat/lng coordinates on
        Google Maps. The user is walked through this when running
        the fix_locations script.
    """
    print ("Loading manually cached locations...")
    geoNames['googLocs'] = { }

    # geo_cache file format:
    # place name|lattitude coordinate|logitude coordinate
    def processGeoCache(row):
        geoNames['googLocs'][row[0]] = {
            'lat': row[1],
            'lng': row[2]
        }

    readTSV(Path.cwd() / 'geo_cache', processGeoCache, '|')


# Downloads all of the team information from The Blue Alliance
def get_team_data():
    global teamData

    print("Downloading team data from The Blue Alliance...")
    teamData = tba.teams(page=None, year=YEAR)


# Replaces unicode characters with ascii characters (e.g., replace é with e)
def strip_unicode(str):
    # Documentation for normalize function:
    # https://docs.python.org/3/library/unicodedata.html#unicodedata.normalize
    # Basically, (from what I understand) this splits the characters with accent
    # marks, etc. (e.g. é) into two parts: the latin character (e.g. e) and a
    # special "combining" character that represents the accent. The string is then
    # encoded into ascii with the 'ignore' option, so it ignores characters that
    # cannot be represented in ascii, thus removing the special combining characters
    # but leaving behind the regular ones. The resulting binary is then decoded back
    # into utf-8.
    return unicodedata.normalize('NFD', str)\
                .encode('ascii', 'ignore')\
                .decode('utf-8')


# Process all of the data that has been downloaded and write it to teams.json
# and teamFullInfo.json
def process_team_data():
    print('Processing and writing team info...')

    shortTeamList = []
    longShortTeamList = []

    for team in teamData:
        # Only include the home_championship attribute for the current year
        homeChamp = team.get('home_championship')
        if homeChamp:
            team['home_championship'] = homeChamp.get(YEAR)

        # Get the team's city name and convert it to uppercase and ASCII (must
        # be converted to ASCII because load_geonames_data loads location names
        # as ASCII). Also remove leading and trailing spaces from the city name
        # because sometimes the city name comes with them.
        cityNoFormat = team.get('city') or ''
        city = strip_unicode(cityNoFormat.upper().strip(' '))
        
        # Get the country code for the team's country.
        countryCode = geoNames['ccodes'].get(team.get('country')) or ''

        # Get the team's state/provice/administrative division and convert to
        # uppercase ASCII.
        provNoFormat = team.get('state_prov') or ''
        province = strip_unicode(provNoFormat.upper())

        # Team's postal code
        zipCode = team.get('postal_code') or ''

        # Needs to be uppercase (postal codes in some countries have letters)
        zipCode = zipCode.upper()

        # ====== special fixes for Guam, zip weirdness, and some typoes ======
        if not countryCode and zipCode:
            # If there is no country code, determine it by the format of the
            # postal code.
            if zipCode == '11073':
                countryCode = 'TW'
            elif zipCode == '34912' or zipCode == '34469':
                countryCode = 'TR'
            elif zipCode == '93810':
                countryCode = 'IL'
            elif re.search('^[0-9]{4}$', zipCode):
                countryCode = 'AU'
            elif re.search('^[0-9]{5}$', zipCode) or re.search('^[0-9]{5}-[0-9]{4}$', zipCode):
                countryCode = 'US'
            elif re.search('^[0-9]{5}-[0-9]{3}$', zipCode):
                countryCode = 'BR'
            elif re.search('^[A-Z][0-9][A-Z] [0-9][A-Z][0-9]$', zipCode):
                countryCode = 'CA'
            elif re.search('^[0-9]{7}$', zipCode):
                countryCode = 'IL'

        if countryCode == 'SE' and re.search('^[0-9]{5}', zipCode):
            # For Sweden, put a space between the first three and last two
            # postal code digits (e.g., 12345 becomes 123 45)
            zipCode = f'{zipCode[0:3]} {zipCode[3:5]}'

        if countryCode == 'US':
            if province == 'GUAM':
                countryCode = 'GU'
            elif province == 'PUERTO RICO':
                countryCode = 'PR'
            elif city == 'NEW YORK':
                city = 'NEW YORK CITY'
            elif province == 'PA' and city == 'WARMINSTER':
                city = 'WARMINSTER HEIGHTS'
            elif province =='MO' and city == 'LEES SUMMIT':
                city = "LEE'S SUMMIT"
        
        if countryCode == 'CL' and province == 'REGION METROPOLITANA DE SANTIAGO':
            province = 'SANTIAGO METROPOLITAN'

        if countryCode == 'CN' and province == 'HUNAN':
            province = 'HENAN'
        
        if countryCode == 'GR' and province == 'THESSALIA':
            province = 'THESSALY'

        if countryCode == 'MX':
            if city == 'SAN LUIS POTOTOSI':
                city = 'SAN LUIS POTOSI'
            if province == 'DISTRITO FEDERAL':
                province = 'MEXICO CITY'

        if countryCode == 'TR' and city == 'CEKMEKOY':
            city = 'CEKMEKOEY'

        if countryCode == 'NL' and province == 'NOORD-BRABANT':
            province = 'NORTH BRABANT'

        if countryCode == 'DO' and province == 'SANTO DOMINGO' and city == province:
            province = 'NACIONAL'

        if countryCode == 'IL':
            # Israel has multiple names for administrative divisions, so this
            # scraper just ignores them completely.
            province = 'IL'

        if countryCode == 'JP' and len(zipCode) == 7:
            # For Japan, separate first three and last four digits with a dash
            # (e.g., 1234567 becomes 123-4567)
            f'{zipCode[0:3]}-{zipCode[3:7]}'

        if countryCode == 'CA':
            # special for Canada, only first three digits of zip code
            zipCode = zipCode[0:3]
        # ======== end of special fixes ========

        # The lattitude and longitude coordinates of the team
        lat = lng = None

        # Retrieve the lattitude and longitude of the team from the zip code,
        # if available.
        zipCountry = geoNames['zipLocs'].get(countryCode)

        if zipCountry:
            zipLoc = zipCountry.get(zipCode)
            
            if zipLoc:
                lat = zipLoc['lat']
                lng = zipLoc['lng']

        # If the location was not retrieved...
        if lat is None and countryCode in geoNames['cities']:
            # Retrieve the lattitude and longitude of the team from the city,
            # state/provice/administrative division, and country code
            cityCountry = geoNames['cities'][countryCode]

            if province in cityCountry:
                cityProv = cityCountry[province]

                if city in cityProv:
                    cityLoc = cityProv.get(city)
                    lat = cityLoc['lat']
                    lng = cityLoc['lng']

        # If the location was still not retrieved...
        if lat is None:
            # Get the location from cached locations that were manually
            # retrieved (see googLocs section of load_geonames_data)
            place = f'{city}, {province} {zipCode}, {countryCode}'
            googLoc = geoNames['googLocs'].get(place)

            if googLoc:
                lat = googLoc['lat']
                lng = googLoc['lng']
        
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
        shortTeam = {
            'team_number': team.get('team_number'),
            'lat': team.get('lat'),
            'lng': team.get('lng')
        }

        shortTeamList.append(shortTeam)

        # Write out the full team info
        longShortTeam = {}

        for att in TEAM_ATTRIBS:
            longShortTeam[att] = team.get(att)

        longShortTeamList.append(longShortTeam)

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
        output = json.dumps(shortTeamList)\
            .replace('[{','[\n\t{')\
            .replace('}, ', '},\n\t')\
            .replace('}]','}\n]')
        out.write(output)

    with open(Path.cwd() / 'teamFullInfo.json', 'w') as outFull:
        # For full team data, just output with standard JSON formatting
        output = json.dumps(longShortTeamList, indent=4)
        outFull.write(output)


get_geonames_data()
load_geonames_data()
get_team_data()
process_team_data()
