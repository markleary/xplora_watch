"""
Custom Version - Edit by Ludy87
Geocoder module.
https://github.com/OpenCageData/python-opencage-geocoder/
https://raw.githubusercontent.com/OpenCageData/python-opencage-geocoder/master/LICENSE.txt
"""
from datetime import datetime
from decimal import Decimal
import collections

from random import randint
import requests
import json

from lxml import html

try:
    import aiohttp
    aiohttp_avaiable = True
except ImportError:
    aiohttp_avaiable = False


class OpenCageGeocodeError(Exception):
    """Base class for all errors/exceptions that can happen when geocoding."""


class InvalidInputError(OpenCageGeocodeError):
    """
    There was a problem with the input you provided.

    :var bad_value: The value that caused the problem
    """

    def __init__(self, bad_value):
        super().__init__()
        self.bad_value = bad_value

    def __unicode__(self):
        return "Input must be a unicode string, not " + repr(self.bad_value)[:100]

    __str__ = __unicode__


class UnknownError(OpenCageGeocodeError):
    """There was a problem with the OpenCage server."""


class RateLimitExceededError(OpenCageGeocodeError):
    """
    Exception raised when account has exceeded it's limit.

    :var datetime reset_time: When your account limit will be reset.
    :var int reset_to: What your account will be reset to.
    """

    def __init__(self, reset_time, reset_to):
        """Constructor."""
        super().__init__()
        self.reset_time = reset_time
        self.reset_to = reset_to

    def __unicode__(self):
        """Convert exception to a string."""
        return "Your rate limit has expired. It will reset to {0} on {1}".format(self.reset_to, self.reset_time.isoformat())

    __str__ = __unicode__


class NotAuthorizedError(OpenCageGeocodeError):
    """
    Exception raised when an unautorized API key is used.
    """

    def __unicode__(self):
        """Convert exception to a string."""
        return "Your API key is not authorized. You may have entered it incorrectly."

    __str__ = __unicode__


class ForbiddenError(OpenCageGeocodeError):
    """
    Exception raised when a blocked or suspended API key is used.
    """

    def __unicode__(self):
        """Convert exception to a string."""
        return "Your API key has been blocked or suspended."

    __str__ = __unicode__


class AioHttpError(OpenCageGeocodeError):
    """
    Exceptions related to async HTTP calls with aiohttp
    """


class OpenCageGeocodeUA:
    """
    Geocoder object.

    Initialize it with your API key:

        >>> geocoder = OpenCageGeocode('your-key-here')

    Query:

        >>> geocoder.geocode("London")

    Reverse geocode a latitude & longitude into a point:

        >>> geocoder.reverse_geocode(51.5104, -0.1021)
    """

    url = 'https://api.opencagedata.com/geocode/v1/json'
    key = ''
    session = None

    def __init__(self, key):
        """Constructor."""
        self.key = key

    def __enter__(self):
        self.session = requests.Session()
        return self

    def __exit__(self, *args):
        self.session.close()
        self.session = None
        return False

    async def __aenter__(self):
        if not aiohttp_avaiable:
            raise AioHttpError("You must install `aiohttp` to use async methods")

        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args):
        await self.session.close()
        self.session = None
        return False

    async def geocode_async(self, query, **kwargs):
        """
        Aync version of `geocode`.

        Given a string to search for, return the results from OpenCage's Geocoder.

        :param string query: String to search for

        :returns: Dict results
        :raises InvalidInputError: if the query string is not a unicode string
        :raises RateLimitExceededError: if you have exceeded the number of queries you can make. Exception says when you can try again
        :raises UnknownError: if something goes wrong with the OpenCage API
        """

        if not aiohttp_avaiable:
            raise AioHttpError("You must install `aiohttp` to use async methods.")

        if not self.session:
            raise AioHttpError("Async methods must be used inside an async context.")

        if not isinstance(self.session, aiohttp.client.ClientSession):
            raise AioHttpError("You must use `geocode_async` in an async context.")

        request = self._parse_request(query, kwargs)
        response = await self._opencage_async_request(request)

        return floatify_latlng(response['results'])

    async def reverse_geocode_async(self, lat, lng, **kwargs):
        """
        Aync version of `reverse_geocode`.

        Given a latitude & longitude, return an address for that point from OpenCage's Geocoder.

        :param lat: Latitude
        :param lng: Longitude
        :return: Results from OpenCageData
        :rtype: dict
        :raises RateLimitExceededError: if you have exceeded the number of queries you can make. Exception says when you can try again
        :raises UnknownError: if something goes wrong with the OpenCage API
        """
        return await self.geocode_async(_query_for_reverse_geocoding(lat, lng), **kwargs)

    async def _opencage_async_request(self, params):
        headers = {
            'User-Agent': await self.getUA()
        }
        async with self.session.get(self.url, params=params, headers=headers) as response:
            try:
                response_json = await response.json()
            except ValueError as e:
                if response.status == 200:
                    raise UnknownError("Non-JSON result from server") from e

            if response.status == 401:
                raise NotAuthorizedError()

            if response.status == 403:
                raise ForbiddenError()

            if (response.status == 402 or response.status == 429):
                # Rate limit exceeded
                reset_time = datetime.utcfromtimestamp(response_json['rate']['reset'])
                raise RateLimitExceededError(reset_to=int(response_json['rate']['limit']), reset_time=reset_time)

            if response.status == 500:
                raise UnknownError("500 status code from API")

            if 'results' not in response_json:
                raise UnknownError("JSON from API doesn't have a 'results' key")

            return response_json

    def _parse_request(self, query, params):
        if not isinstance(query, str):
            raise InvalidInputError(bad_value=query)

        data = { 'q': query, 'key': self.key }
        data.update(params)  # Add user parameters
        return data

    async def getUA(self):
        url = (
            "https://webcache.googleusercontent.com/"
            "search?q=cache:FxxmQW9XrRcJ:https://techblog.willshouse.com/"
            "2012/01/03/most-common-user-agents/+&cd=4&hl=de&ct=clnk&gl=us"
        )
        xpath = '//*[@id="post-2229"]/div[2]/textarea[2]'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36'
        }
        async with self.session.get(url, headers=headers) as response:
            xml = html.fromstring(await response.text())
            elem = xml.xpath(xpath)[0]
            data = json.loads(elem.text)
            i = randint(0, len(data) - 1)
            return data[i]['useragent']


def _query_for_reverse_geocoding(lat, lng):
    """
    Given a lat & lng, what's the string search query.

    If the API changes, change this function. Only for internal use.
    """
    # have to do some stupid f/Decimal/str stuff to (a) ensure we get as much
    # decimal places as the user already specified and (b) to ensure we don't
    # get e-5 stuff
    return "{0:f},{1:f}".format(Decimal(str(lat)), Decimal(str(lng)))


def float_if_float(float_string):
    """
    Given a float string, returns the float value.
    On value error returns the original string.
    """
    try:
        float_val = float(float_string)
        return float_val
    except ValueError:
        return float_string


def floatify_latlng(input_value):
    """
    Work around a JSON dict with string, not float, lat/lngs.

    Given anything (list/dict/etc) it will return that thing again, *but* any
    dict (at any level) that has only 2 elements lat & lng, will be replaced
    with the lat & lng turned into floats.

    If the API returns the lat/lng as strings, and not numbers, then this
    function will 'clean them up' to be floats.
    """
    if isinstance(input_value, collections.abc.Mapping):
        if len(input_value) == 2 and sorted(input_value.keys()) == ['lat', 'lng']:
            # This dict has only 2 keys 'lat' & 'lon'
            return {'lat': float_if_float(input_value["lat"]), 'lng': float_if_float(input_value["lng"])}
        else:
            return dict((key, floatify_latlng(value)) for key, value in input_value.items())
    elif isinstance(input_value, collections.abc.MutableSequence):
        return [floatify_latlng(x) for x in input_value]
    else:
        return input_value
