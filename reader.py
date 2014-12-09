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

sys.path.insert(1, os.path.split(sys.path[0])[0])
from cli import CommandLineInterface

import nfcpy.nfc

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
        s[-1] += ' '.join(["%02x" % ord(c) for c in data[i:i+w]]) + ' '
        s[-1] += (8 + w*3 - len(s[-1])) * ' '
        s[-1] += ''.join([c if c in printable else '.' for c in data[i:i+w]])
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
            tag.read(range(i+1))
        else:
            return block_count
    except Exception:
        return i

def tt3_determine_block_write_once_count(tag, block_count):
    try:
        for i in range(block_count):
            data = tag.read(range(i+1))
            tag.write(data, range(i+1))
        else:
            return block_count
    except Exception:
        return i

#
# command parsers
#
def add_show_parser(parser):
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="show more tag information")

def add_dump_parser(parser):
    parser.add_argument(
        "-o", dest="output", metavar="FILE",
        type=argparse.FileType('w'), default="-",
        help="save ndef to FILE (writes binary data)")

def add_load_parser(parser):
    parser.add_argument(
        "input", metavar="FILE", type=argparse.FileType('r'),
        help="ndef data file ('-' reads from stdin)")

def add_format_parser(parser):
    subparsers = parser.add_subparsers(title="Tag Types", dest="tagtype")
    add_format_tt1_parser(subparsers.add_parser(
            'tt1', help='format type 1 tag'))
    add_format_tt3_parser(subparsers.add_parser(
            'tt3', help='format type 3 tag'))

def add_format_tt1_parser(parser):
    pass

def add_format_tt3_parser(parser):
    parser.add_argument(
        "--ver", metavar="STR", default="1.0",
        help="ndef mapping version number (default: %(default)s)")
    parser.add_argument(
        "--nbr", metavar="INT", type=int,
        help="number of blocks that can be written at once")
    parser.add_argument(
        "--nbw", metavar="INT", type=int,
        help="number of blocks that can be read at once")
    parser.add_argument(
        "--max", metavar="INT", type=int,
        help="maximum number of blocks (nmaxb x 16 == capacity)")
    parser.add_argument(
        "--rfu", metavar="INT", type=int, default=0,
        help="value to set for reserved bytes (default: %(default)s)")
    parser.add_argument(
        "--wf", metavar="INT", type=int, default=0,
        help="write-flag attribute value (default: %(default)s)")
    parser.add_argument(
        "--rw", metavar="INT", type=int, default=1,
        help="read-write flag attribute value (default: %(default)s)")
    parser.add_argument(
        "--len", metavar="INT", type=int, default=0,
        help="ndef length attribute value (default: %(default)s)")
    parser.add_argument(
        "--crc", metavar="INT", type=int,
        help="checksum attribute value (default: computed)")

def add_emulate_parser(parser):
    parser.description = "Emulate an ndef tag."
    parser.add_argument(
        "-l", "--loop", action="store_true",
        help="continue (restart) after tag release")
    parser.add_argument(
        "-k", "--keep", action="store_true",
        help="keep tag memory (when --loop is set)")
    parser.add_argument(
        "-s", dest="size", type=int, default="1024",
        help="minimum ndef data area size (default: %(default)s)")
    parser.add_argument(
        "-p", dest="preserve", metavar="FILE", type=argparse.FileType('wb'),
        help="preserve tag memory when released")
    parser.add_argument(
        "input", metavar="FILE", type=argparse.FileType('r'),
        nargs="?", default=None,
        help="ndef message to serve ('-' reads from stdin)")
    subparsers = parser.add_subparsers(title="Tag Types", dest="tagtype")
    add_emulate_tt3_parser(subparsers.add_parser(
            'tt3', help='emulate a type 3 tag'))

def add_emulate_tt3_parser(parser):
    parser.add_argument(
        "--idm", metavar="HEX", default="03FEFFE011223344",
        help="manufacture identifier (default: %(default)s)")
    parser.add_argument(
        "--pmm", metavar="HEX", default="01E0000000FFFF00",
        help="manufacture parameter (default: %(default)s)")
    parser.add_argument(
        "--sys", "--sc", metavar="HEX", default="12FC",
        help="system code (default: %(default)s)")
    parser.add_argument(
        "--bitrate", choices=["212", "424"], default="212",
        help="bitrate to listen (default: %(default)s)")
    parser.add_argument(
        "--ver", metavar="STR", default="1.0",
        help="ndef mapping version number (default: %(default)s)")
    parser.add_argument(
        "--nbr", metavar="INT", type=int, default=12,
        help="max write blocks at once (default: %(default)s)")
    parser.add_argument(
        "--nbw", metavar="INT", type=int, default=8,
        help="max read blocks at once (default: %(default)s)")
    parser.add_argument(
        "--max", metavar="INT", type=int,
        help="maximum number of blocks (default: computed)")
    parser.add_argument(
        "--rfu", metavar="INT", type=int, default=0,
        help="value to set for reserved bytes (default: %(default)s)")
    parser.add_argument(
        "--wf", metavar="INT", type=int, default=0,
        help="write-flag attribute value (default: %(default)s)")
    parser.add_argument(
        "--rw", metavar="INT", type=int, default=1,
        help="read-write flag attribute value (default: %(default)s)")
    parser.add_argument(
        "--crc", metavar="INT", type=int,
        help="checksum attribute value (default: computed)")

class TagTool(CommandLineInterface):
    def __init__(self):
        parser = ArgumentParser(
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description="")
        parser.add_argument(
            "-v", "--verbose", action="store_true",
            help="show more information")
        subparsers = parser.add_subparsers(
            title="commands", dest="command")
        add_show_parser(subparsers.add_parser(
                'show', help='pretty print ndef data'))
        add_dump_parser(subparsers.add_parser(
                'dump', help='read ndef data from tag'))
        add_load_parser(subparsers.add_parser(
                'load', help='write ndef data to tag'))
        add_format_parser(subparsers.add_parser(
                'format', help='format ndef tag'))
        add_emulate_parser(subparsers.add_parser(
                'emulate', help='emulate ndef tag'))

        super(TagTool, self).__init__(
            parser, groups="rdwr card dbg clf")

    def on_rdwr_startup(self, clf, targets):
        if self.options.command in ("show", "dump", "load", "format"):
            log.info("touch a tag")
            return targets

    def on_rdwr_connect(self, tag):
        commands = {"show": self.show_tag, "dump": self.dump_tag,
                    "load": self.load_tag, "format": self.format_tag}
        commands[self.options.command](tag)
        return self.options.wait or self.options.loop

    def on_card_startup(self, clf, targets):
        if self.options.command == "emulate":
            target = self.prepare_tag()
            log.info("touch a reader")
            return [target]

    def on_card_connect(self, tag, command):
        log.info("tag activated")
        return self.emulate_tag_start(tag, command)

    def on_card_release(self, tag):
        log.info("tag released")
        self.emulate_tag_stop(tag)
        return True

    def show_tag(self, tag):
        print(tag)
        if self.options.verbose:
            if tag.type == "Type1Tag":
                tag._hr = tag.read_id()[0:2]
                print("  " + tt1_card_map.get(str(tag._hr), "unknown card"))
            elif tag.type == "Type2Tag":
                pass
            elif tag.type == "Type3Tag":
                icc = str(tag.pmm[0:2]) # ic code
                print("  " + tt3_card_map.get(icc, "unknown card"))
            elif tag.type == "Type4Tag":
                pass
        if tag.ndef:
            print("NDEF capabilities:")
            if self.options.verbose and tag.type == "Type3Tag":
                print("  [%s]" % tag.ndef.attr.pretty())
            print("  version   = %s" % tag.ndef.version)
            print("  readable  = %s" % ("no", "yes")[tag.ndef.readable])
            print("  writeable = %s" % ("no", "yes")[tag.ndef.writeable])
            print("  capacity  = %d byte" % tag.ndef.capacity)
            print("  message   = %d byte" % tag.ndef.length)
            if tag.ndef.length > 0:
                if self.options.verbose:
                    print("NDEF message dump:")
                    print(format_data(tag.ndef.message))
                print("NDEF record list:")
                print(tag.ndef.message.pretty())
        if self.options.verbose:
            if tag.type == "Type1Tag":
                mem_size = {0x11: 120, 0x12: 512}.get(tag._hr[0], 2048)
                mem_data = bytearray()
                for offset in range(0, mem_size, 8):
                    try: mem_data += tag[offset:offset+8]
                    except nfc.clf.DigitalProtocolError as error:
                        log.error(repr(error)); break
                print("TAG memory dump:")
                print(format_data(mem_data, w=8))
                tag.clf.sense([nfc.clf.TTA(uid=tag.uid)])
            elif tag.type == "Type2Tag":
                memory = bytearray()
                for offset in range(0, 256 * 4, 16):
                    try: memory += tag[offset:offset+16]
                    except nfc.clf.DigitalProtocolError as error:
                        log.error(repr(error)); break
                print("TAG memory dump:")
                print(format_data(memory))
                tag.clf.sense([nfc.clf.TTA(uid=tag.uid)])
            elif tag.type == "Type3Tag":
                pass
            elif tag.type == "Type4Tag":
                pass

    def dump_tag(self, tag):
        if tag.ndef:
            data = tag.ndef.message
            if self.options.output.name == "<stdout>":
                self.options.output.write(str(data).encode("hex"))
                if self.options.loop:
                    self.options.output.write('\n')
                else:
                    self.options.output.flush()
            else:
                self.options.output.write(str(data))

    def load_tag(self, tag):
        try: self.options.data
        except AttributeError:
            self.options.data = self.options.input.read()
            try: self.options.data = self.options.data.decode("hex")
            except TypeError: pass

        if tag.ndef is None:
            log.info("not an ndef tag")
            return

        log.info("old message: \n" + tag.ndef.message.pretty())
        try:
            tag.ndef.message = nfc.ndef.Message(self.options.data)
            if tag.ndef.changed:
                log.info("new message: \n" + tag.ndef.message.pretty())
            else:
                log.info("new message is same as old message")
        except nfc.tag.AccessError:
            log.error("this tag is not writeable")
        except nfc.tag.CapacityError:
            log.error("message exceeds tag capacity")

    def format_tag(self, tag):
        if tag.type == "Type1Tag" and self.options.tagtype == "tt1":
            formatted = self.format_tt1_tag(tag)
        elif tag.type == "Type3Tag" and self.options.tagtype == "tt3":
            formatted = self.format_tt3_tag(tag)
        else:
            print("This is not a type %s tag" % self.options.tagtype[2])
            return

        if formatted:
            print("Formatted %s:" % tag.type)
            print("  version   = %s" % tag.ndef.version)
            print("  readable  = %s" % ("no", "yes")[tag.ndef.readable])
            print("  writeable = %s" % ("no", "yes")[tag.ndef.writeable])
            print("  capacity  = %d byte" % tag.ndef.capacity)
            print("  message   = %d byte" % tag.ndef.length)
        else:
            print("Sorry, I don't know how to format this %s." % tag.type)

    def format_tt1_tag(self, tag):
        hr = tag.read_id()[0:2]
        if hr[0] == 0x11:
            for i, v in enumerate(bytearray.fromhex("E1100E0003000000")):
                tag.write_byte(8 + i, v)
        elif hr[0] == 0x12:
            tag.write_block(1, bytearray.fromhex("E1103F000103F230"))
            tag.write_block(2, bytearray.fromhex("330203F002030300"))
        else:
            return False
        # re-read the ndef capabilities
        tag.ndef = nfc.tag.tt1.NDEF(tag)
        return True

    def format_tt3_tag(self, tag):
        block_count = tt3_determine_block_count(tag)
        if tag.pmm[0:2] in ("\x00\xF0", "\x00\xF1"):
            block_count -= 1 # last block on FeliCa Lite/S is unusable
        print("tag has %d user data blocks" % block_count)
        nbr = tt3_determine_block_read_once_count(tag, block_count)
        print("%d block(s) can be read at once" % nbr)
        nbw = tt3_determine_block_write_once_count(tag, block_count)
        print("%d block(s) can be written at once" % nbw)
        if self.options.max is not None: block_count = self.options.max + 1
        if self.options.nbw is not None: nbw = self.options.nbw
        if self.options.nbr is not None: nbr = self.options.nbr

        if tag.pmm[0:2] in ("\x00\xF0", "\x00\xF1"):
            # Check NDEF system code support on FeliCa Lite-S
            mc = tag.read(blocks=[0x88])
            if mc[3] != 0x01:
                tag.write(mc[0:3]+"\x01"+mc[4:16], blocks=[0x88])

        attr = nfc.tag.tt3.NdefAttributeData()
        attr.version = self.options.ver
        attr.nbr, attr.nbw = (nbr, nbw)
        attr.capacity = (block_count - 1) * 16
        attr.rfu = 4 * [self.options.rfu]
        attr.wf = self.options.wf
        attr.writing = bool(self.options.wf)
        attr.rw = self.options.rw
        attr.writeable = bool(self.options.rw)
        attr.length = self.options.len
        attr = bytearray(str(attr))
        if self.options.crc is not None:
            attr[14:16] = (self.options.crc / 256, self.options.crc % 256)
        tag.write(attr, [0])
        # re-read the ndef capabilities
        tag.ndef = nfc.tag.tt3.NDEF(tag)
        return True

    def prepare_tag(self):
        if self.options.tagtype == "tt3":
            return self.prepare_tt3_tag()

    def prepare_tt3_tag(self):
        if self.options.size % 16 != 0:
            self.options.size = ((self.options.size + 15) // 16) * 16
            log.warning("tt3 ndef data area size rounded to {0}"
                        .format(self.options.size))

        try: self.options.data
        except AttributeError:
            if self.options.input:
                self.options.data = self.options.input.read()
                try: self.options.data = self.options.data.decode("hex")
                except TypeError: pass
            else:
                self.options.data = ""

        if not (hasattr(self.options, "tt3_data") and self.options.keep):
            if self.options.input:
                ndef_data_size = len(self.options.data)
                ndef_area_size = ((ndef_data_size + 15) // 16) * 16
                ndef_area_size = max(ndef_area_size, self.options.size)
                ndef_data_area = bytearray(self.options.data) + \
                                 bytearray(ndef_area_size - ndef_data_size)
            else:
                ndef_data_area = bytearray(self.options.size)

            # set attribute data
            attr = nfc.tag.tt3.NdefAttributeData()
            attr.version = self.options.ver
            attr.nbr, attr.nbw = self.options.nbr, self.options.nbw
            attr.capacity = len(ndef_data_area)
            if self.options.max is not None:
                attr.capacity = self.options.max * 16
            attr.rfu = 4 * [self.options.rfu]
            attr.wf = self.options.wf
            attr.rw = self.options.rw
            attr.length = len(self.options.data)
            attr.writing = bool(self.options.wf)
            attr.writeable = bool(self.options.rw)
            attribute_data = bytearray(str(attr))
            if self.options.crc is not None:
                attribute_data[14] = self.options.crc / 256
                attribute_data[15] = self.options.crc % 256

            log.info(nfc.tag.tt3.NdefAttributeData(attribute_data).pretty())
            self.options.tt3_data = attribute_data + ndef_data_area

        idm = bytearray.fromhex(self.options.idm)
        pmm = bytearray.fromhex(self.options.pmm)
        sys = bytearray.fromhex(self.options.sys)
        return nfc.clf.TTF(self.options.bitrate, idm, pmm, sys)

    def emulate_tag_start(self, tag, command):
        if self.options.tagtype == "tt3":
            return self.emulate_tt3_tag(tag, command)

    def emulate_tag_stop(self, tag):
        if self.options.preserve:
            self.options.preserve.seek(0)
            self.options.preserve.write(self.options.tt3_data)
            log.info("wrote tag memory to file '{0}'"
                     .format(self.options.preserve.name))

    def emulate_tt3_tag(self, tag, command):
        def ndef_read(block_number, rb, re):
            log.debug("tt3 read block #{0}".format(block_number))
            if block_number < len(self.options.tt3_data) / 16:
                first, last = block_number*16, (block_number+1)*16
                block_data = self.options.tt3_data[first:last]
                return block_data
        def ndef_write(block_number, block_data, wb, we):
            log.debug("tt3 write block #{0}".format(block_number))
            if block_number < len(self.options.tt3_data) / 16:
                first, last = block_number*16, (block_number+1)*16
                self.options.tt3_data[first:last] = block_data
                return True

        tag.add_service(0x0009, ndef_read, ndef_write)
        tag.add_service(0x000B, ndef_read, lambda: False)
        return True

class ArgparseError(SystemExit):
    pass

class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ArgparseError(2, '{0}: error: {1}'.format(self.prog, message))

if __name__ == '__main__':
    try:
        TagTool().run()
    except ArgparseError as e:
        sys.argv = sys.argv + ['show']
        try:
            TagTool().run()
        except ArgparseError:
            print(e.args[1], file=sys.stderr)
