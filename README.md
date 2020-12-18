Readme file for FIRSTMap Scraper
===

This scraper is likely to be a high-maintenance item, as there are a number
of hacks to work around incomplete team info from thebluealliance and
differences between place names in different databases. This scraper makes use
of [FRC 1418's tbapy](https://github.com/frc1418/tbapy), a Python wrapper for
The Blue Alliance API.

The scraper was built on Python 3.8.

## Usage:
1. Copy/extract/clone the files to a directory.
2. Install the tbapy and lockfile libraries (`pip3 install tbapy lockfile`).
3. Get a Read API Key from TheBlueAlliance.com/account and put it in a file
   called `TBA-auth`.
3. Run "python scraper.py" (assuming you already have Python 3 installed; if
   not, install it).
4. Manually find any places that could not be found (such as by using
   ask_google, which works some of the time).

If the program has to be run multiple times in a row (such as to make
adjustments to it, correct issues, etc.), the program can be called with the
`usecache` argument to reuse the already-downloaded GeoNames files instead of
taking the time to redownload them every time. Example usage:
`python scraper.py usecache`

## Descriptions of Files

**README.md** - This file.

**[scraper.py](scraper.py)** - The scraper python script, which gets the postal
code data, location data, and team data from GeoNames and TheBlueAlliance and
uses the data to create the teams.json and teamFullInfo.json. Intermediate
downloaded data is stored in the data subdirectory, which is created by the
script if it does not exist. Comments within the file explain the process in
more detail.

**[ask_google](ask_google)** - Script to get a lat/lon from the
`data/broken_places` file.<br>
&nbsp;&nbsp;&nbsp;&nbsp;Usage: `./ask_google >> geo_cache`<br>
&nbsp;&nbsp;&nbsp;&nbsp;This file must be run manually; it is not run from<br>
&nbsp;&nbsp;&nbsp;&nbsp;scraper.py. It works some of the time.

**[geo_cache](geo_cache)** - A pipe delimited file where each line os of the
format `<location string>|<latitude>|<longitude>`. This file is manually built
from previous calls to ask_google and other sources.

**[make_latlng](make_latlng)** - Extracts the lat/lon from a google place file.
Called from ask_google.

**TBA-auth** - A file containing a TheBlueAlliance (TBA)
authorization token. This is not in the repository, but is required for the
scraper to function. The user is expected to get a token from TheBlueAlliance.
A logged-in TBA user can create a Read API Key from the Account page. It simply
needs to be pasted into a file called TBA-auth. This is used by the scraper to
access TheBlueAlliance API.

**[YEAR](YEAR)** - A file containing the current year for purposes of
retrieving team lists from thebluealliance.com.

**[explanation of process.md](explanation%20of%20process.md)** - This file
contains some details reguarding the changes made between the old scraper and
the new scraper. It was mostly created to assist in rewriting the scraper in
Python. Most of the documentation of how the new process works is found in
the code comments of [scraper.py](scraper.py).