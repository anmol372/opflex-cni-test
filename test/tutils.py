from time import sleep
import logging
import os
from kubernetes import client

def assertEventually(checker, delay, count):
    ix = 0
    err = ""
    while (ix < count):
        err = checker()
        if err == "":
            return
        ix += 1
        sleep(delay)
    print("Error is: {}".format(err))
    assert err == ""

class SafeDict(dict):
    'Provide a default value for missing keys'
    def __missing__(self, key):
        return 'missing'

def tcLog(descr):
    print("\n*** TEST CASE: {}\n".format(descr))

def logSetup():
    supportedLogLevels = ['INFO', 'DEBUG', 'ERROR']
    logLevel = os.getenv('LOG_LEVEL', 'INFO')
    if logLevel == "":
        logLevel = 'INFO'

    if logLevel not in supportedLogLevels:
        print("Supported log levels are:{}".format(supportedLogLevels))
        print("Overriding to INFO\n")
        logLevel = 'INFO'

    logging.basicConfig(level=logLevel)

def checkPodDeleted(kapi, ns, name, timeout=30):
    def deleteChecker():
        resp = kapi.list_namespaced_pod(ns)
        for pod in resp.items:
            if pod.metadata.name == name:
                return "{} still present".format(name)

        return ""

    assertEventually(deleteChecker, 1, timeout)
