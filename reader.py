#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import logging
log = logging.getLogger('main')

import os
import sys
import time
import string
import struct
import argparse

from config import *

sys.path.append('/home/pi/nfc-reader-web/nfcpy')
import nfc

# Command Line Arguments
parser = argparse.ArgumentParser(description='Define output format and storage path', epilog='You can also change the default values in \'_config.py\'.')
parser.add_argument('-d', '--device', action='store', help='path to NFC reader device <default: ' + default_device +'>', default='')
parser.add_argument('-f', '--format', action='store', help='specify the output format <default: ' + default_format +'>', choices=['xml', 'json'], default='')
parser.add_argument('-p', '--path', action='store', help='specify the storage path <default: ' + default_path +'>', default='')
parser.add_argument('-q', '--quiet', action='store_true', help='only print error messages', default='false')

args = parser.parse_args()

if args.device:
    default_device = args.device

if args.format:
    default_format = args.format

if args.path:
    default_path = args.path

#
