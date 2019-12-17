from time import sleep
import logging
import os
from kubernetes import client

def assertEventually(checker, delay, count, inspector=None):
    ix = 0
    err = ""
    while (ix < count):
        err = checker()
        if err == "":
            return
        ix += 1
        sleep(delay)
    print("Error is: {}".format(err))
    if inspector is not None:
        inspector()
    assert False

class SafeDict(dict):
    'Provide a default value for missing keys'
    def __missing__(self, key):
        return 'missing'

def tcLog(descr):
    print("\n*** TEST CASE: {}\n".format(descr))

def inspectLog(descr):
    print("\n!!! ONFAIL: {}\n".format(descr))

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

def scaleRc(name, replicas, ns="default"):
    v1 = client.CoreV1Api()
    scale = v1.read_namespaced_replication_controller_scale(name, ns)
    scale.spec.replicas = replicas
    resp = v1.replace_namespaced_replication_controller_scale(name, ns, scale)
    rcCheckScale(name, replicas, ns)

def rcCheckScale(name, replicas, ns="default"):
    v1 = client.CoreV1Api()
    def scaleChecker():
        curr = v1.read_namespaced_replication_controller_status(name, ns)
        if curr.status.ready_replicas is None and replicas == 0:
            return ""

        if curr.status.ready_replicas == replicas:
            return ""

        return "expected {} replicas, got {}".format(replicas, curr.status.ready_replicas)

    assertEventually(scaleChecker, 1, 30)

def checkPodsRemoved(selector, ns="default"):
    v1 = client.CoreV1Api()
    def checker():
        resp = v1.list_namespaced_pod(ns, label_selector=selector)
        if len(resp.items) == 0:
            return ""

        return "{} pods still present".format(len(resp.items))

    assertEventually(checker, 1, 45)

def getPodIP(name, ns):
    v1 = client.CoreV1Api()
    resp = v1.read_namespaced_pod_status(name, ns)
    return resp.status.pod_ip
