#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# file: script.py
#
#
# Usage: python script.py -h
#
# Please note that this script is only compatible with the Python version 3.
#
# Dependencies:
#     external tool pdftotext and the 'subprocess' module
#     'os' module : tree walker
#     'argparse' module
#     'time' module : measure runtime of the script
#     're' module : parse the PDF files
#     'functools' module : functional programming support

from subprocess import check_output
from subprocess import CalledProcessError
from functools import reduce

import os
import argparse
import time
import sys
import re
import configparser

DOC_TYPES = {
    "UZNESENIE" : "uznesenie",
    "Žiadosť" : "ziadost",
    "Upovedomenie" : "upovedomenie",
    "EXEKUČNÝ PRÍKAZ" : "ep",
    "Oznámenie" : "oznamenie",
    "Oznámenie o ukončení exekúcie" : "oznamenie_ukonceni_exekucie",
    "Konečné vyúčtovanie" : "vyuctovanie",
    "Platobný predpis" : "prikaz_na_uhradu",
}

DOC_TYPES_REGEX = "|".join(DOC_TYPES.keys())

# The file contains names of all executors in Slovakia (surname first)
# There can also be a row which is only the same name in a different
# (grammar) case. In this situation, the row also contains an offset to the
# nominative, i.e.
#
# ...
# Hojdová Soňa
# Hojdovej Soni,1
# Hojdovú Soňu,2
#
def executors(filename):
    with open(filename) as f:
        content = [x.strip().split(",") for x in f.readlines()]
    for arr in content:
        if len(arr) == 1:
            arr.append(0)
        else:
            arr[1] = int(arr[1])
    return content

# Returns an array of arrays of "EČV" plate ids
# Caveat: there can be more than one "EČV" for one district.
def districts(fname):
    districtAbbrColOrder = 2
    mainDelimiter = ","
    subDelimiter = ";"
    content = []
    with open(fname) as f:
        content = [ l.split(mainDelimiter)[districtAbbrColOrder].split(subDelimiter) \
                    for l in f.readlines()]
    return content

# Colored output in Python simplified
redC    = lambda x : ("\033[91m {}\033[00m" .format(x))
greenC  = lambda x : ("\033[92m {}\033[00m" .format(x))
yellowC = lambda x : ("\033[93m {}\033[00m" .format(x))

def walkTree(rootDir, executors, districts):
    countDict = {}
    okEntries = 0
    entries = 0
    fixMeId = 1
    newAdepts = set()
    for dirPath, subdirList, fileList in os.walk(rootDir):
        print(greenC('DIR: %s' % dirPath))
        for fname in [ f for f in fileList if f.endswith(".pdf")]:
            dirPath = os.path.abspath(dirPath)
            fullName = os.path.join(dirPath, fname)
            text = ""
            try:
                text = [l.decode("utf-8") for l in check_output(["pdftotext",
                        fullName, "-"]).split(b'\x0A')]
            except CalledProcessError:
                print(redC("FATAL: could not read the file '%s'." % fname))
                continue
            doctype=""
            issuer="" # Either a court or an executor
            mark="" # Either Ex or Er
            for l in text:
                doctypeSearch = re.search("(" + DOC_TYPES_REGEX + ")", l)
                if(doctypeSearch is not None) and \
                  (u"Oznámenie musí byť doložené" not in l) and not doctype:
                    doctype = DOC_TYPES[doctypeSearch.group(1)]
                courtSearch = re.search("\:OS(\w\w\d*)\:", l)
                if(courtSearch is not None) and not issuer:
                    # This search is quite intensive and most of the documents
                    # contain this mark at the very beginning of the file,
                    # we should therefore skip searching for others.
                    for districtArr in districts:
                        if courtSearch.group(1) in districtArr:
                            issuer = "OS" + courtSearch.group(1)
                execSearch = re.search("JUDr\.\s*(\w+)\s(\w+)(\,?\s*.*)", l)
                if(execSearch is not None) and not issuer:
                    executor = execSearch.group(2).replace("-", "") + \
                               " " + execSearch.group(1).replace("-", "")
                    executor = executor.strip()
                    for index, (ex, offset) in enumerate(executors):
                        if executor in ex:
                            issuer = "-".join(executors[index - offset][0].split(" "))
                            break
                exSearch = re.search("(E[xX])\s+(\d+/\d+)", l)
                if (exSearch is not None) and not mark:
                    mark = (exSearch.group(1) + "/" + exSearch.group(2)).replace("/", "-")
                # Possible bug: the algorithm does not take into account sequences
                # like DEr/DDD/DDDD- (D is a digit)
                erSearch = re.search("(\d+E[rR]/\d+/\d+)(\s*[\-\–]\s*)?(\d+)?", l)
                if (erSearch is not None) and not mark:
                    appendix = ""
                    if(erSearch.group(2) is not None):
                        appendix = "-"
                    if(erSearch.group(3) is not None):
                        appendix += erSearch.group(3)
                    mark = (erSearch.group(1) + appendix).replace("/", "-")
                if (bool(reduce((lambda x,y : x and len(y)), [doctype, issuer, mark]))):
                    okEntries += 1
                    newName = u"_".join([doctype, issuer, mark]) + ".pdf"
                    newFullName = os.path.join(dirPath, newName)
                    print(yellowC("Renaming " + fname + " to -> " + newName))
                    os.replace(fullName, newFullName)
                    break
            if(not bool(reduce((lambda x,y : x and len(y)), [doctype, issuer, mark]))):
                newName = "FIX_ME" + str(fixMeId) + "_" + "_".join([doctype,issuer,mark]) + ".pdf"
                newFullName = os.path.join(dirPath, newName)
                fixMeId += 1
                print(redC("Could not transform the document %s, please update manually." % fullName))
                os.replace(fullName, newFullName)
            entries += 1
    print(countDict)
    print(sorted(newAdepts))
    print("There are %d entries out of %d which were processed." % (okEntries, entries))

class rwDir(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        prospective_dir=values
        if not os.path.isdir(prospective_dir):
            raise argparse.ArgumentTypeError("'{0}' is not a valid path."
                                             .format(prospective_dir))
        rw_OK = os.R_OK | os.W_OK
        if os.access(prospective_dir, rw_OK):
            setattr(namespace,self.dest,prospective_dir)
        else:
            raise argparse.ArgumentTypeError("'{0}' is not both a readable " + \
                              "and writable directory".format(prospective_dir))

def parseCmdArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", help="Input root directory of " + \
                        "the input PDF files.", action=rwDir, required=True)
    return parser.parse_args()


# Helper function which takes a string containing a filename (without ANY path)
# and prepends the absolute path from which the script is being executed.
# Useful when the script needs to take sources from the same directory it is
# being executed from.
def absolutePath(filename):
    prefix = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(prefix, filename)

def checkLocalFileExists(filename):
    return os.path.isfile(absolutePath(filename))

def allSourcesAvailable(config):
    return bool(reduce((lambda x, y : x and checkLocalFileExists(config["sources"][y])), \
                config["sources"]))

def loadConfig():
    conf = configparser.ConfigParser()
    succ = conf.read(absolutePath("config.ini"))
    # https://docs.python.org/3.5/library/configparser.html#configparser.ConfigParser.read
    if len(succ) != 1:
        sys.stderr.write("Could not read the configuration file.\n" + \
                         "Please make sure that the directory from which the " + \
                         "script is run also contains a 'config.ini' file.\n")
    return conf

# The function takes a configparser.ConfigParser object (which acts as a map)
# and examines whether it is safe to run the script.
def sanityCheck(conf):
    if not allSourcesAvailable(conf):
        sys.stderr.write("Sanity check failed. Aborting execution of the script.\n")
        sys.exit()

if __name__ == "__main__":
    conf = loadConfig()
    sanityCheck(conf)
    args = parseCmdArgs()
    rootDir = args.input
    start = time.time()
    sources = conf["sources"]
    execPath = absolutePath(sources["executors"])
    districtPath = absolutePath(sources["districts"])
    walkTree(rootDir, executors(execPath), districts(districtPath))
    print(greenC("Finished: " + str(time.time() - start) + " s"))
