""" A set of utility functions for QualysConnect module. """
import logging

import qualysapi.config as qcconf
import qualysapi.connector as qcconn
import qualysapi.version

__author__ = "Parag Baxi <parag.baxi@gmail.com> & Colin Bell <colin.bell@uwaterloo.ca>"
__copyright__ = "Copyright 2011-2013, Parag Baxi & University of Waterloo"
__license__ = 'Apache License 2.0'

# Set module level logger.
logger = logging.getLogger(__name__)

def connect(remember_me=False, remember_me_always=False):
    """ Return a QGAPIConnect object for v1 API pulling settings from config
    file.
    """
    # Retrieve login credentials.
    conf = qcconf.QualysConnectConfig(remember_me=remember_me, remember_me_always=remember_me_always)
    connect = qcconn.QGConnector(conf.get_username(),
                                  conf.get_password(),
                                  conf.get_hostname(),
                                  conf.proxies, conf.curl_path, conf.curl_use_subprocess)
    logger.info("Finished building connector.")
    return connect