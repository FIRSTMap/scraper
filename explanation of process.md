# Here's what happens:

## New Process:
[scraper.py](scraper.py) contains all code for the program (except for ask_google, which is still used as previously to find broken locations). Please refer to the inline comments for documentation. The program uses the Python library tbapy (`pip3 install tbapy`) to get data from The Blue Alliance. The program was built on Python 3. Some adjustments to the process have been made that make more sense in Python. For example, instead of having separate ziplats and ziplngs tables, there is one table called zipLocs that contains both lattitude and longitude data for each location.

List of what replaces what:
 - ./get_postal is replaced by the `get_geonames_data` and `load_geonames_data` functions.
 - ./get_events is obsolete.
 - ./get_lists and ./merge_lists are replaced by tbapy, which is used in the `get_team_data` function.
 - ./merge_lists is replaced by the `load_geonames_data` and `process_team_data` functions.
 - The `unicodes.ascii` file is replaced by the `strip_unicode` function.
 - The `attribs` file has been replaced with a list called `TEAM_ATTRIBS` near the top of `scraper.py`.

For more detailed documentation of how the scraper words, consult the comments (and the code) in (scraper.py)[scraper.py].

## Old Process:
This process was written with commit [a54b2a6](https://github.com/FIRSTMap/scraper/commit/a54b2a6422ca2a3eb879927a95f30b4784cf31f7), so all references to lines in files are from then. HOWEVER, merge_lists needed the year updated to the year in the `YEAR` file (2020 as of now), otherwise merge_lists will fail.

Note: awk indices (at least for tables made with the split function) are one-based, so the column with index 1 is the same as column 1 and the first column.

Run ./get_all_data
1. ./get_postal is run
    - Downloads and unzips all the information from GeoNames.
2. ./get_events is run
    - Downloads events from TBA for the `YEAR` and formats them into JSON and puts them into events.js (obsolete because FIRSTMap does this automatically now).
3. ./get_lists is run
    - Write the current UTC time in seconds to `data/team-time`
    - Download every page of teams from `[TBA API endpoint]/teams/[YEAR]/[page number]` where the page number is incremented until the page of teams an empty list. Each list is stored in a file called `data/teams.[page number]`.
4. ./merge_lists is run
    - Merges the team files together into a single file (`data/merged`), kind of line a JSON list but without square brackets enclosing it.
    - Only leaves one value (for the current `YEAR`) for the home championship of each team instead of a dictionary for each year for each team.
5. ./build_teamInfo is run. Note: input file is `data/merged`. Output is `teamFullInfo.json`. AWK record separator is `"` (so basically, split each line of the file on `"`).
    - Has a prebuilt list of fields loaded from a file called `attribs`. The fields are loaded into a list called `idx` (lines 5-6).
    - \[Lines 7-10\]: Load the unicode -> ascii table from `unicodes.ascii` is stored in a table called unicode (where the key is the unicode character escape sequence in upper case and the value is the ascii character that is similar (also uppercase) (this table translates characters like ä to a)). This is used later in the program to make using GeoNames data easier.
    - \[Line 11\]: (Commented out) dump the unicode/ascii table to file `unicode-dump`.
    - \[Lines 12-16\]: Takes each line in `data/countryInfo.txt`, splits the lines by \\t (tab), then creates a table (called `ccode` for country codes) where each key is the fifth column and each value is the first column of each line. Basically, it makes the keys of the table the country names (the fifth column of `data/countryInfo.txt`) and the values of the table the country codes (the first column). Note: it appears that the comments in `data/countryInfo.txt` are treated as normal lines with no negative outcome, but it might be a good idea to look into actually skipping lines that start with `#`.
    - \[Lines 17-18\]: Add country codes for Czech Republic (CZ) and Chinese Taipei (TW) because those are the names used by FIRST/TBA, but `data/countryInfo.txt` has those countries listed as Czechia Prague and Taiwan, respectively.
    - \[Line 19\]: Delete the empty string key from the `ccode` table (TODO figure out why this is important, probably something to do with if the country name is an empty string and this could end up being filled in into the table maybe with the comments in `data/countryInfo.txt` not being ignored, etc.).
    - \[Line 20\]: (Commented out) dump all country codes to file `ccode-dump`.
    - \[Lines 21-27\]: Split each line of `data/allCountries` on \\t (tab). Creates a table called `ziplats` where the key is the first column (in all uppercase) and the second column (in all uppercase) concatenated together with a | in the middle (first + "|" + second), and where the value is the tenth column. Creates a table called `ziplngs` where the key is the same as for `ziplats` and the value is the eleventh column.
    - \[Lines 28-29\]: (Commented out) dump `ziplats` and `ziplngs` to files `ziplats-dump` and `ziplngs-dump`, respectively.
    - \[Lines 30-33\]: Go through each line of `data/admin1CodesASCII.txt` and split into columns by \\t (tab). Create a table called adms with the key equal to the admin code (column 1), and the value equal to the administrative division name in ascii (in English) (column 3) in upper case.
    - \[Line 34\]: (Commented out) dump `adms` to file `adms-dump`.
    - \[Lines 35-52\]:
        - \[Lines 36-37\]: For each line of `data/cities1000`, split the line by \\t (tab). Make column 3 all uppercase.
        - \[Line 38\]: Create a variable called `adm` that is equal to the value of `adms[column9 + "." + column11]` (where the columns are columns of the current line). This makes adm the name of the administrative division, which is retrieved using the admin code created by concatonating column9 (country code) with column11 (state/province/admininistrative division/etc. code) with a dot in the middle. 
        - \[Line 39-40\]: Make tables `citilats` and `citilngs` with keys that are `country code (column 9) + "|" + administrative division name (adm) + "|" + ascii city name (column 3)` and values that are column5 (lattitude) and column6 (longitude), respectively.
        - \[Line 41-43\]: If the country code is TW (Taiwan), add the keys to `citilats` and `citilngs` that are the same format as the previous step except instead of using the admin name in the middle, use the ascii city name again (colunm 3) (so `country code (column 9) + "|" + ascii city name (column 3) + "|" + ascii city name (column 3)`). Use the same lattitude and longitude values.
        - \[Lines 44-49\]: Israel apparently has bad districts and alternate city names, so if the country code is IL (Israel), split column 4 (alternate names) by comma, and for each altername name in the list that is created, add an entries to citilats and citilngs with the same lattitude and longitude values (columns 5 and 6 respectively), but with the key "IL|IL|" + the alternate name.
    - \[Lines 53-54\]: Dump `citilats` and `citilngs` to files `citilats-dump` and `citilngs-dump`, respectively.
    - \[Lines 55-59\]: For each line in geo_cache, split on "|". Make tables called `googlats` and `googlngs` with the key being the first column of each line (the location name) and the values being the second (lattitude) and third (longitude), respectively. Basically, load the manually-entered lattitudes and longitudes from geo_cache into `googlats` and `googlngs`.
    - \[Line 60\]: Print out "read data files" to standard error (so that it shows up in the console, since standard output is going to the file).
    - \[Lines 61-69\]: Define the following variables: `start=1`, `dfmt="     %11s: %d,\n"`, `ffmt="     %11s: %.3f,\n"`, `afmt="     %11s: \"%s\""`, `afmt1=afmt ",\n"`, `afmt2=afmt "\n    }"`. Then "\[" is printed to standard output (`teamFullInfo.json`) and also to `teams.json`. Thus ends BEGIN (setup code).
    - \[Lines 71-74\]: Match lines of input (which is `data/merged`) that start with any amount of spaces (including 0) and a `{`. This marks the beginning of a team. At that point, populate the indices of the table `atts` with the prebuilt list of attributes that were loaded at the beginning into the list `idx` and clear the values of `atts` by setting them all to empty strings (so that the table is ready for the next team).
    - \[Lines 75-187\]: Match lines that start with any amount of spaces (including 0) and a `}`. This marks the end of a team. At this point, all the attributes that have been filled into the `atts` table by the code on lines 188-196 are processed.
        - \[Lines 76-78\]: Converts the city name to uppercase and removes spaces at the end of it. For each unicode character in the `unicode` table, replace any occurances of said characters with their equivalent ascii characters (as defined in the `unicode` table). Stores the city name in a variable called `city`.
        - \[Line 79\]: Gets the country name from atts (`atts["country"]`) and uses it to get the country code from ccode. Stores the country code in a variable called `country`.
        - \[Line 80\]: Gets the state/province name from atts (`atts["state_prov"]`), converts it to uppercase, and stores it in the variable `prov`.
        - \[Line 81\]: Does the same thing with unicode characters in `prov` as was done 3 steps above with the unicode characters in `city`
        - \[Line 82\]: Store `atts["postal_code"]` in variable `zip`.
        - \[Lines 84-147\]: \[Comment on line 84: special fixes for Guam, zip weirdness, and some typoes\].
            - \[Lines 84-99\]: If `country` (the country code) is an empty string, switch on `zip` (in this order):
                - \[Line 87\]: case 11073: `country="TW"`.
                - \[Line 88\]: case 34912: `country="TR"`.
                - \[Line 89\]: case 34469: `country="TR"`.
                - \[Line 90\]: case 93810: `country="IL"`.
                - \[Line 91\]: `case /^[0-9]{4}$/`: `country="AU"`. (If the zip code only has 4 digits, it is an Australian postal code.)
                - \[Line 92-93\]: `case /^[0-9]{5}$/` and `case /^[0-9]{5}-[0-9]{4}$/`: `country="US"`. (If the postal code has 5 digits, or it has 5 digits, a dash, and then 4 digits, it is a US postal code.)
                - \[Line 94\]:  `case /^[0-9]{5}-[0-9]{3}$/`: `country="BR"`. (If the postal code is 5 digits, a dash, and then 3 digits, it is a Brazil postal code.)
                - \[Line 95-96\]: `case /^[A-Z][0-9][A-Z] [0-9][A-Z][0-9]$/`: `country="CA"`. (If the postal code is a capital letter, number, capital letter, and then a space and number, capital letter, and number, it is a Canada postal code.)
                - \[Line 97\]: `case /^[0-9]{7}$/`: `country="IL"`. (If the postal code is 7 digits (all numbers), the country is Israel).
            - \[Line 100\]: If the `country` is `"SE"` and the `zip` starts with a 5 digit number, insert a space between the third and fourth digits of the zip code (e.g., if `zip` is `"12345"`, it becomes `"123 45"`).
            - \[Line 101\]: If the `country` is `"US"` and the `prov` is `"GUAM"`, set `country` to `"GU"`.
            - \[Line 102\]: If the `country` is `"US"` and the `prov` is `"PUERTO RICO"`, set `country` to `"PR"`.
            - \[Lines 103-105\]: If the `country` is `"CL"` and the `prov` is `"REGION METROPOLITANA DE SANTIAGO"`, set `prov` to `"SANTIAGO METROPOLITAN"`.
            - \[Lines 106-108\]: If the `country` is `"CN"` and the `prov` is `"HUNAN"`, set `prov` to `"HENAN"`.
            - \[Lines 109-111\]: If the `country` is `"GR"` and the `prov` is `"THESSALIA"`, set `prov` to `"THESSALY"`.
            - \[Lines 112-114\]: If the `country` is `"MX"` and the `city` is `"SAN LUIS POTOTOSI"`, set `city` to `"SAN LUIS POTOSI"`.
            - \[Lines 115-117\]: If the `country` is `"MX"` and the `prov` is `"DISTRITO FEDERAL"`, set `prov` to `"MEXICO CITY"`.
            - \[Lines 118-120\]: If the `country` is `"TR"` and the `city` is `"CEKMEKOY"`, set `city` to `"CEKMEKOEY"`.
            - \[Lines 121-123\]: If the `country` is `"US"` and the `city` is `"NEW YORK"`, set `city` to `"NEW YORK CITY"`.
            - \[Lines 124-126\]: If the `country` is `"US"` and the `prov` is `"PA"` and the `city` is `"WARMINSTER"`, set `city` to `"WARMINSTER HEIGHTS"`.
            - \[Lines 127-129\]: If the `country` is `"US"` and the `prov` is `"MO"` and the `city` is `"LEES SUMMIT"`, set `city` to `"LEE\047S SUMMIT"`.
            - \[Lines 130-132\]: If the `country` is `"NL"` and the `prov` is `"NOORD-BRABANT"`, set `prov` to `"NORTH BRABANT"`.
            - \[Lines 133-135\]: If the `country` is `"DO"` and the `prov` is `"SANTO DOMINGO"` and the `city` equals the `prov`, set `prov` to `"NACIONAL"`.
            - \[Lines 136-142\]: If the `country` is `"IL"`, set `prov` to `"IL"`.
            - \[Lines 143-145\]: If the `country` is `"JP"` and the length of `zip` is 7, insert a dash between the third and fourth character of the `zip`.
            - \[Line 146\]: If the `country` is `"CA"`, `zip` is truncated to its first 3 characters (e.g., if `zip` is `"12345"`, it becomes `"123"`) \[Comment: special for Canada\].
            - \[Line 147\]: \[Comment on line 147: end fixes\].
        - \[Lines 149-168\]: Get the lat and lng coordinates for the team and store them in `atts["lat"]` and `atts["lng"]`.
            - \[Lines 149-150\]: Define variables `lat` and `lon`, both with values equal to an empty string. These appear to be unused, and are maybe left over from some previous version of the code.
            - \[Lines 151-153\]: Written in pseudocode, `key = country + "|" + zip`. If `ziplats` contains the key (`key`), `atts["lat"]` is set to `ziplats[key]` and `atts["lng"]` is set to `ziplngs[key]`.
            - \[Lines 154-156\]: Else, do the following: Written in pseudocode, `key = country + "|" + prov + "|" + city`. If `citilats` contains the key (`key`), `atts["lat"]` is set to `citilats[key]` and `atts["lng"]` is set to `citilngs[key]`.
            - \[Lines 157-168\]: Else, do the following: Written in pseudocode, `place = city + ", " + prov + " " + zip + ", " + country"`. If `googlats` contains the key (`place`), `atts["lat"]` is set to `googlats[key]` and `atts["lng"]` is set to `googlngs[key]`. Else, write `place` to the file `data/places`, and print `"Did not find team " + atts["key"] + " @ place " + place` to standard error. The place will then have to be resolved with the ask_google script.
            - \[Lines 169-171\]: Print the following attributes from `atts` to `teams.json` (in JSON format with one object for each team): `team_number`, `lat`, and `lng`.
            - \[Lines 173-185\]: Prints in the same format to `teamFullInfo.json`, except with the attributes `team_number`, `rookie_year`, `lat`, `lng`, `website`, `nickname`, `motto`, and `location` in the format of `place` specified in the description of lines 157-168 above.
            - \[Line 186\]: `next;`
    - \[Lines 188-196\]: Match lines that start with any amount of spaces (including 0) and a `"` (lines that haven't been matched already by the `{` and `}` checks). Store the keys and values of each line in the `atts` table (basically, parse all the attributes of the team from the JSON).

Run ./ask_google for any team location information that wasn't sucessfully resolved.
