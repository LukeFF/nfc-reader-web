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
import string
import struct
import argparse

import urllib
import urllib2

from xml.etree.ElementTree import Element, SubElement, Comment, tostring
from ElementTree_pretty import prettify


sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/nfcpy')
import nfc

from config import *

tt1_card_map = {
    "\x11\x48": "Topaz-96 (IRT-5011)",
    "\x12\x4C": "Topaz-512 (TPZ-505-016)"
}
tt3_card_map = {
    "\x00\xF0": "FeliCa Lite RC-S965",
    "\x00\xF1": "FeliCa Lite-S RC-S966",
    "\x01\xE0": "FeliCa Plug RC-S801/RC-S802",
    "\x01\x20": "FeliCa Card RC-S962 [424 kbps, 4KB FRAM]",
    "\x03\x01": "FeliCa Card RC-S860 [212 kbps, 4KB FEPROM]",
    "\x0f\x0d": "FeliCa Card RC-S889 [424 kbps, 9KB FRAM]",
}


def format_data(data, w=16):
    printable = string.digits + string.letters + string.punctuation + ' '
    if type(data) is not type(str()):
        data = str(data)
    s = []
    for i in range(0, len(data), w):
        s.append("  {offset:04x}: ".format(offset=i))
        s[-1] += ' '.join(["%02x" % ord(c) for c in data[i:i + w]]) + ' '
        s[-1] += (8 + w * 3 - len(s[-1])) * ' '
        s[-1] += ''.join([c if c in printable else '.' for c in data[i:i + w]])
    return '\n'.join(s)


def tt3_determine_block_count(tag):
    block = 0
    try:
        while True:
            data = tag.read([block], 9)
            block += 1
    except Exception:
        return block


def tt3_determine_block_read_once_count(tag, block_count):
    try:
        for i in range(block_count):
            tag.read(range(i + 1))
        else:
            return block_count
    except Exception:
        return i


def tt3_determine_block_write_once_count(tag, block_count):
    try:
        for i in range(block_count):
            data = tag.read(range(i + 1))
            tag.write(data, range(i + 1))
        else:
            return block_count
    except Exception:
        return i

class Reader(object):
    def __init__(self):
        parser = ArgumentParser(description='Define output format and storage path',
                                epilog='You can also change the default values in \'_config.py\'.')
        parser.add_argument('-d', '--device', action='store',
                            help='path to NFC reader device <default: %(default)s>', default=default_device)
        parser.add_argument('-f', '--format', action='append',
                            help='specify the output format <default: %(default)s>', choices=['xml', 'json'], default=default_format)
        parser.add_argument('-p', '--path', action='store',
                            help='specify the storage path <default: %(default)s>', default=default_path)
        parser.add_argument('--quiet', action='store_true',
                            help='disable all output except errors <default: %(default)s>', default=False)
        parser.add_argument('--debug', action='store_true',
                            help='enable debug output <default: %(default)s>', default=False)

        self.options = parser.parse_args()
        self.options.wait = True

        ch = logging.StreamHandler()
        if self.options.quiet:
            lv = logging.ERROR
        elif self.options.debug:
            lv = logging.DEBUG
        else:
            lv = logging.INFO
        ch.setLevel(lv)
        ch.setFormatter(logging.Formatter('[%(name)s] %(message)s'))
        logging.getLogger().addHandler(ch)

        logging.getLogger().setLevel(logging.NOTSET)
        logging.getLogger('main').setLevel(logging.DEBUG)

        log.debug(self.options)

    def on_rdwr_startup(self, clf, targets):
        log.info("waiting for a new tag")
        return targets

    def on_rdwr_connect(self, tag):
        tag.timestamp = str(datetime.datetime.now())
        #self.show_tag(tag)
        export = ''
        if self.options.format == 'json':
            pass
        else:
            export = self.generateXML(tag)

        if self.options.path.startswith("http://"):
            export = {'xml': export}
            export = urllib.urlencode(export)
            urllib2.Request(self.options.path, data=export)
        else:
            with open(self.options.path + '/' + str(tag.uid).encode("hex") + '.xml', 'w') as file_:
                file_.write(export)
            log.info('Saved data to: ' + self.options.path + '/' + str(tag.uid).encode("hex") + '.xml')


        return self.options.wait

    def generateXML(self, tag):
        #print(dir(tag.atq))
        xml = Element('nfctag')
        xml.set('type', tag.type)
        uid = SubElement(xml, 'uid')
        uid.text = str(tag.uid).encode("hex")
        #atq = SubElement(xml, 'atq')
        #atq.text = str(tag.atq)
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
            message.text = str(tag.ndef.message).encode("hex")

        if tag.type == "Type1Tag":
            mem_size = {0x11: 120, 0x12: 512}.get(tag._hr[0], 2048)
            mem_data = bytearray()
            for offset in range(0, mem_size, 8):
                try:
                    mem_data += tag[offset:offset + 8]
                except nfc.clf.DigitalProtocolError as error:
                    log.error(repr(error))
                    break
            memdump = SubElement(xml, 'memdump')
            memdump.text = str(mem_data).encode("hex")
            tag.clf.sense([nfc.clf.TTA(uid=tag.uid)])
        elif tag.type == "Type2Tag":
            memory = bytearray()
            for offset in range(0, 256 * 4, 16):
                try:
                    memory += tag[offset:offset + 16]
                except nfc.clf.DigitalProtocolError as error:
                    log.error(repr(error))
                    break
            memdump = SubElement(xml, 'memdump')
            memdump.text = str(memory).encode("hex")
            tag.clf.sense([nfc.clf.TTA(uid=tag.uid)])
        elif tag.type == "Type3Tag":
            pass
        elif tag.type == "Type4Tag":
            pass

        timestamp = SubElement(xml, 'timestamp')
        timestamp.text = str(tag.timestamp)
        reader = SubElement(xml, 'reader')
        reader.text = os.uname()[1]

        #print(prettify(xml))
        return prettify(xml)

    def show_tag(self, tag):
        # print(dir(tag))
        if tag.type == "Type1Tag":
            tag._hr = tag.read_id()[0:2]
            print("  " + tt1_card_map.get(str(tag._hr), "unknown card"))
        elif tag.type == "Type2Tag":
            pass
        elif tag.type == "Type3Tag":
            icc = str(tag.pmm[0:2])  # ic code
            print("  " + tt3_card_map.get(icc, "unknown card"))
        elif tag.type == "Type4Tag":
            pass
        if tag.ndef:
            print("NDEF capabilities:")
            if tag.type == "Type3Tag":
                print("  [%s]" % tag.ndef.attr.pretty())
            print("  version   = %s" % tag.ndef.version)
            print("  readable  = %s" % ("no", "yes")[tag.ndef.readable])
            print("  writeable = %s" % ("no", "yes")[tag.ndef.writeable])
            print("  capacity  = %d byte" % tag.ndef.capacity)
            print("  message   = %d byte" % tag.ndef.length)
            if tag.ndef.length > 0:
                print("NDEF message dump:")
                print(format_data(tag.ndef.message))
                print("NDEF record list:")
                print(tag.ndef.message.pretty())
        if tag.type == "Type1Tag":
            mem_size = {0x11: 120, 0x12: 512}.get(tag._hr[0], 2048)
            mem_data = bytearray()
            for offset in range(0, mem_size, 8):
                try:
                    mem_data += tag[offset:offset + 8]
                except nfc.clf.DigitalProtocolError as error:
                    log.error(repr(error))
                    break
            print("TAG memory dump:")
            print(format_data(mem_data, w=8))
            tag.clf.sense([nfc.clf.TTA(uid=tag.uid)])
        elif tag.type == "Type2Tag":
            memory = bytearray()
            for offset in range(0, 256 * 4, 16):
                try:
                    memory += tag[offset:offset + 16]
                except nfc.clf.DigitalProtocolError as error:
                    log.error(repr(error))
                    break
            print("TAG memory dump:")
            print(format_data(memory))
            tag.clf.sense([nfc.clf.TTA(uid=tag.uid)])
        elif tag.type == "Type3Tag":
            pass
        elif tag.type == "Type4Tag":
            pass

    def run_once(self):
        try:
            clf = nfc.ContactlessFrontend(self.options.device)
        except IOError:
            pass

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
            log.info("*** RESTART ***")


class ArgparseError(SystemExit):
    pass


class ArgumentParser(argparse.ArgumentParser):

    def error(self, message):
        raise ArgparseError(2, '{0}: error: {1}'.format(self.prog, message))

if __name__ == '__main__':
    try:
        Reader().run()
    except ArgparseError as e:
        sys.argv = sys.argv + ['show']
        try:
            Reader().run()
        except ArgparseError:
            print(e.args[1], file=sys.stderr)
