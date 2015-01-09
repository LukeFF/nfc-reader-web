#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 2014 Lukas Thoma <lukasthoma@gmail.com>
from __future__ import print_function

import logging
log = logging.getLogger('main')

import os
import sys
import time
import datetime
import inspect
import string
import struct
import argparse
import itertools
from threading import Thread

import urllib
import urllib2

from xml.etree.ElementTree import Element, SubElement, Comment, tostring
from ElementTree_pretty import prettify

import config

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/nfcpy')
import nfc

class Reader(object):
    def __init__(self):
        parser = ArgumentParser(description='Define output format and storage path',
                                epilog='You can also change the default values in \'config.py\'.')
        parser.add_argument('-d', '--device', action='store',
                            help='path to NFC reader device <default: %(default)s>', default=config.default_device)
        parser.add_argument('-p', '--path', action='store',
                            help='specify the storage path <default: %(default)s>', default=config.default_path)
        parser.add_argument('--quiet', action='store_true',
                            help='disable all output except errors <default: %(default)s>', default=False)
        parser.add_argument('--debug', action='store_true',
                            help='enable debug output <default: %(default)s>', default=False)

        self.options = parser.parse_args()

        ch = logging.StreamHandler()
        if self.options.quiet:
            logLevel = logging.ERROR
        elif self.options.debug:
            logLevel = logging.DEBUG
        else:
            logLevel = logging.INFO
        ch.setLevel(logLevel)
        ch.setFormatter(logging.Formatter('[%(name)s] %(message)s'))
        logging.getLogger().addHandler(ch)

        logging.getLogger().setLevel(logging.NOTSET)
        logging.getLogger('main').setLevel(logging.INFO)
        log.debug(self.options)

    def on_rdwr_startup(self, clf, targets):
        log.info('reader ready, please touch a tag')
        return targets

    def on_rdwr_connect(self, tag):
        log.info('Tag found: ' + str(tag.uid).encode('hex'))
        tag.timestamp = str(datetime.datetime.now())
        export = self.generateXML(tag)

        if self.options.path.startswith('http://'):
            values = {'xml': export}
            data = urllib.urlencode(values)
            req = urllib2.Request(self.options.path, data)
            log.info('Sent data via HTTP Post Request to ' + self.options.path)
            response = urllib2.urlopen(req)
            log.info(response.read())
        else:
            with open(self.options.path + '/' + str(tag.uid).encode('hex') + '_' + tag.timestamp + '.xml', 'w') as file_:
                file_.write(export)
            log.info('Saved data to: ' + self.options.path + '/' + str(tag.uid).encode('hex') + '_' + tag.timestamp + '.xml')
        return True

    def generateXML(self, tag):
        xml = Element('nfctag')
        xml.set('type', tag.type)
        uid = SubElement(xml, 'uid')
        uid.text = str(tag.uid).encode('hex')
        atq = SubElement(xml, 'atq')
        atq.text = str(tag.atq)
        sak = SubElement(xml, 'sak')
        sak.text = str(tag.sak)
        timestamp = SubElement(xml, 'timestamp')
        timestamp.text = str(tag.timestamp)
        reader = SubElement(xml, 'reader')
        reader.text = os.uname()[1]
        if tag.ndef:
            ndef = SubElement(xml, 'ndef')
            version = SubElement(ndef, 'version')
            version.text = str(tag.ndef.version)
            readable = SubElement(ndef, 'readable')
            readable.text = str(tag.ndef.readable)
            writeable = SubElement(ndef, 'writeable')
            writeable.text = str(tag.ndef.writeable)
            capacity = SubElement(ndef, 'capacity')
            capacity.text = str(tag.ndef.capacity)
            length = SubElement(ndef, 'length')
            length.text = str(tag.ndef.length)
            message = SubElement(ndef, 'message')
            message.text = str(tag.ndef.message).encode('hex')

        return prettify(xml)

    def run_once(self):
        if self.options.device is None:
            self.options.device = config.default_device

        for device in self.options.device:
            try: clf = nfc.ContactlessFrontend(device)
            except IOError: pass
            else: break
        else:
            log.error('no nfc reader found')
            raise SystemExit(1)

        rdwr_options = {
            'on-startup': self.on_rdwr_startup,
            'on-connect': self.on_rdwr_connect,
            }

        try:
            kwargs = {'rdwr': rdwr_options}
            return clf.connect(**kwargs)
        finally:
            clf.close()

    def run(self):
        while self.run_once():
            log.info('*** RESTART ***')

class ArgparseError(SystemExit):
    pass

class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ArgparseError(2, '{0}: error: {1}'.format(self.prog, message))

if __name__ == '__main__':
    try:
        Reader().run()
    except ArgparseError as e:
        print(e.args[1], file=sys.stderr)
