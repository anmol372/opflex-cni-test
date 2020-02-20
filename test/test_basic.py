import pytest
import tutils
import logging
from time import sleep
from kubernetes import client, config

tutils.logSetup()
config.load_kube_config()
v1 = client.CoreV1Api()

def assertEventually(checker, delay, count):
    ix = 0
    err = ""
    while (ix < count):
        err = checker()
        if err == "":
            return
        ix += 1
        sleep(delay)
    assert err == ""
        
def checkPodStatus():
        pod_list = v1.list_namespaced_pod("kube-system")
        for pod in pod_list.items:
            if pod.status.phase != "Running":
                return "pod {} status is {}".format(pod.metadata.name, pod.status.phase)
        return ""

class TestBasic(object):
    def test_cni_status(object):
        tutils.tcLog("Verify status of system pods")
        assertEventually(checkPodStatus, 1, 90)
        tutils.checkAgentLog()
