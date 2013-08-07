""" Module that contains classes for setting up connections to QualysGuard API
and requesting data from it.
"""
import requests, urlparse
import logging
import lxml.etree
import qualysapi.version
import qualysapi.api_methods
import subprocess
import urllib

from collections import defaultdict

__author__ = 'Parag Baxi <parag.baxi@gmail.com>'
__copyright__ = 'Copyright 2013, Parag Baxi'
__license__ = 'Apache License 2.0'

# Setup module level logging.
logger = logging.getLogger(__name__)

class QGConnector:
    """ Qualys Connection class which allows requests to the QualysGuard API using HTTP-Basic Authentication (over SSL).

    """


    def __init__(self, username, password, server='qualysapi.qualys.com', proxies=None, curl_path=None, curl_use_subprocess=False):
        # Read username & password from file, if possible.
        self.auth = (username, password,)
        # Remember QualysGuard API server.
        self.server = server
        # Remember rate limits per call.
        self.rate_limit_remaining = defaultdict(int)
        # api_methods: Define method algorithm in a dict of set.
        # Naming convention: api_methods[api_version optional_blah] due to api_methods_with_trailing_slash testing.
        self.api_methods = qualysapi.api_methods.api_methods
        #
        # Keep track of methods with ending slashes to autocorrect user when they forgot slash.
        self.api_methods_with_trailing_slash = qualysapi.api_methods.api_methods_with_trailing_slash
        self.proxies = proxies
        logger.debug('proxies = \n%s' % proxies)
        self.curl_path = curl_path
        logger.debug('curl_path = \n%s' % curl_path)
        # Library human_curl may have issues, see if subprocess will be used.
        self.curl_use_subprocess = False
        if curl_path:
            # Replace requests with curl.
            import human_curl as requests
            if curl_use_subprocess:
                # Use subprocess to call curl.
                self.curl_use_subprocess = True


    def __call__(self):
        return self


    def format_api_version(self, api_version):
        """ Return QualysGuard API version for api_version specified.

        """
        # Convert to int.
        if type(api_version) == str:
            api_version = api_version.lower()
            if api_version[0] == 'v' and api_version[1].isdigit():
                # Remove first 'v' in case the user typed 'v1' or 'v2', etc.
                api_version = api_version[1:]
            # Check for input matching Qualys modules.
            if api_version in ('asset management', 'assets', 'tag',  'tagging', 'tags'):
                # Convert to Asset Management API.
                api_version = 'am'
            elif api_version in ('webapp', 'web application scanning', 'webapp scanning'):
                # Convert to WAS API.
                api_version = 'was'
            elif api_version in ('pol', 'pc'):
                # Convert PC module to API number 2.
                api_version = 2
            else:
                api_version = int(api_version)
        return api_version


    def which_api_version(self, api_call):
        """ Return QualysGuard API version for api_call specified.

        """
        # Leverage patterns of calls to API methods.
        if api_call.endswith('.php'):
            # API v1.
            return 1
        elif api_call.startswith('api/2.0/'):
            # API v2.
            return 2
        elif '/am/' in api_call:
            # Asset Management API.
            return 'am'
        elif '/was/' in api_call:
            # WAS API.
            return 'was'
        return False


    def url_api_version(self, api_version):
        """ Return base API url string for the QualysGuard api_version and server.

        """
        # Set base url depending on API version.
        if api_version == 1:
            # QualysGuard API v1 url.
            url = "https://%s/msp/" % (self.server,)
        elif api_version == 2:
            # QualysGuard API v2 url.
            url = "https://%s/" % (self.server,)
        elif api_version == 'was':
            # QualysGuard REST v3 API url (Portal API).
            url = "https://%s/qps/rest/3.0/" % (self.server,)
        elif api_version == 'am':
            # QualysGuard REST v1 API url (Portal API).
            url = "https://%s/qps/rest/1.0/" % (self.server,)
        else:
            raise Exception("Unknown QualysGuard API Version Number (%s)" % (api_version,))
        logger.debug("Base url =\n%s" % (url))
        return url


    def format_http_method(self, api_version, api_call, data):
        """ Return QualysGuard API http method, with POST preferred..

        """
        # Define get methods for automatic http request methodology.
        #
        # All API v2 requests are POST methods.
        if api_version == 2:
            return 'post'
        elif api_version == 1:
            if api_call in self.api_methods['1 post']:
                return 'post'
            else:
                return 'get'
        elif api_version == 'was':
            # WAS API call.
            if api_call in self.api_methods['was get']:
                return 'get'
            # Post calls with no payload will result in HTTPError: 415 Client Error: Unsupported Media Type.
            if not data:
                # No post data. Some calls change to GET with no post data.
                if api_call in self.api_methods['was no data get']:
                    return 'get'
                else:
                    return 'post'
            else:
                # Call with post data.
                return 'post'
        else:
            # Asset Management API call.
            if api_call in self.api_methods['am get']:
                return 'get'
            else:
                return 'post'


    def preformat_call(self, api_call):
        """ Return properly formatted QualysGuard API call.

        """
        # Remove possible starting slashes or trailing question marks in call.
        api_call_formatted = api_call.lstrip('/')
        api_call_formatted = api_call_formatted.rstrip('?')
        if api_call != api_call_formatted:
            # Show difference
            logger.debug('api_call post strip =\n%s' % api_call_formatted)
        return api_call_formatted


    def format_call(self, api_version, api_call):
        """ Return properly formatted QualysGuard API call according to api_version etiquette.

        """
        # Remove possible starting slashes or trailing question marks in call.
        api_call = api_call.lstrip('/')
        api_call = api_call.rstrip('?')
        logger.debug('api_call post strip =\n%s' % api_call)
        # Make sure call always ends in slash for API v2 calls.
        if (api_version == 2 and api_call[-1] != '/'):
            # Add slash.
            logger.debug('Adding "/" to api_call.')
            api_call += '/'
        if api_call in self.api_methods_with_trailing_slash[api_version]:
            # Add slash.
            logger.debug('Adding "/" to api_call.')
            api_call += '/'
        return api_call


    def format_payload(self, api_version, data):
        """ Return appropriate QualysGuard API call.

        """
        # Check if payload is for API v1 or API v2.
        if (api_version in (1, 2)):
            # Check if string type.
            if type(data) == str:
                # Convert to dictionary.
                logger.debug('Converting string to dict:\n%s' % data)
                # Remove possible starting question mark & ending ampersands.
                data = data.lstrip('?')
                data = data.rstrip('&')
                # Convert to dictionary.
                data = urlparse.parse_qs(data)
                logger.debug('Converted:\n%s' % str(data))
        elif api_version in ('am', 'was'):
            if type(data) == lxml.etree._Element:
                logger.debug('Converting lxml.builder.E to string')
                data = lxml.etree.tostring(data)
                logger.debug('Converted:\n%s' % data)
        return data


    def request(self, api_call, data=None, api_version=None, http_method=None):
        """ Return QualysGuard API response.

        """
        logger.debug('api_call =\n%s' % api_call)
        logger.debug('api_version =\n%s' % api_version)
        logger.debug('data %s =\n %s' % (type(data), str(data)))
        logger.debug('http_method =\n%s' % http_method)
        #
        # Determine API version.
        # Preformat call.
        api_call = self.preformat_call(api_call)
        if api_version:
            # API version specified, format API version inputted.
            api_version = self.format_api_version(api_version)
        else:
            # API version not specified, determine automatically.
            api_version = self.which_api_version(api_call)
        #
        # Set up base url.
        url = self.url_api_version(api_version)
        #
        # Set up headers.
        headers = {"X-Requested-With": "Parag Baxi QualysAPI (python) v%s"%(qualysapi.version.__version__,)}
        logger.debug('headers =\n%s' % (str(headers)))
        # Portal API takes in XML text, requiring custom header.
        if api_version in ('am', 'was'):
            headers['Content-type'] = 'text/xml'
        #
        # Set up http request method, if not specified.
        if not http_method:
            http_method = self.format_http_method(api_version, api_call, data)
        logger.debug('http_method =\n%s' % http_method)
        #
        # Format API call.
        api_call = self.format_call(api_version, api_call)
        logger.debug('api_call =\n%s' % (api_call))
        # Append api_call to url.
        url += api_call
        #
        # Format data, if applicable.
        if data is not None:
            data = self.format_payload(api_version, data)
        #
        # Make request.
        logger.debug('url =\n%s' % (str(url)))
        logger.debug('data =\n%s' % (str(data)))
        logger.debug('headers =\n%s' % (str(headers)))
        if self.curl_use_subprocess:
            # Use Subprocess to call curl.
            curl_call = ['curl', '-k', '-u', '%s:%s' % (self.auth[0], self.auth[1]), url]
            # Insert headers.
            for header in headers:
                for i in ['-H', '%s: %s' % (header, headers[header])]:
                    curl_call.insert(len(curl_call)-1, i)
            # Check for POST data.
            if data:
                # Always being sent a dictionary.
                if type(data) == dict:
                    for i in data:
                        # Convert one item list to a string.
                        if type(data[i])==list:
                            data[i]=data[i][0]
                    # Parameterize data.
                    data = urllib.urlencode(data)
                # Insert data.
                for i in ['-d', data]:
                    curl_call.insert(len(curl_call)-1, i)
            # Check for proxy.
            if self.proxies:
                # Insert proxy info before url.
                for i in ['--proxy', self.proxies['https']]:
                    curl_call.insert(len(curl_call)-1, i)
            logger.debug('curl_call =\n%s' % (str(curl_call)))
            print 'curl_call =\n%s' % (str(curl_call))
            request = subprocess.call(curl_call)
            logger.debug('response text =\n%s' % (str(request)))
            return request
        else:
            # Do not use Subprocess to call curl.
            if http_method == 'get':
                # GET
                logger.debug('GET request.')
                request = requests.get(url, params=data, auth=self.auth, headers=headers, proxies=self.proxies)
            else:
                # POST
                logger.debug('POST request.')
                # Make POST request.
                request = requests.post(url, data=data, auth=self.auth, headers=headers, proxies=self.proxies)
            logger.debug('response headers =\n%s' % (str(request.headers)))
            #
            # Remember how many times left user can make against api_call.
            try:
                self.rate_limit_remaining[api_call] = int(request.headers['x-ratelimit-remaining'])
                logger.debug('rate limit for api_call, %s = %s' % (api_call, self.rate_limit_remaining[api_call]))
            except KeyError, e:
                # Likely a bad api_call.
                logger.debug(e)
                pass
            except TypeError, e:
                # Likely an asset search api_call.
                logger.debug(e)
                pass
            logger.debug('response text =\n%s' % (str(request.content)))
            # Check to see if there was an error.
            request.raise_for_status()
            return request.content