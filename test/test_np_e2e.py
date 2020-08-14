import pytest
import tutils
import logging
from kubernetes import client, config, utils
from kubernetes.stream import stream
from kubernetes.client import configuration
from os import path
from time import sleep
import yaml

tutils.logSetup()
configuration.assert_hostname = False
config.load_kube_config()
configuration.assert_hostname = False
k8s_client = client.ApiClient()

def getPodNames(kapi, ns, selector):
    names = []
    pod_list = kapi.list_namespaced_pod(ns, label_selector=selector)
    for pod in pod_list.items:
        if pod.status.phase == "Running":
            names.append(pod.metadata.name)
    return names

# yaml filename must match the object name, per our convention
def nameToYaml(name):
    return "yamls/e2e/{}.yaml".format(name)

def createNs(name):
    v1 = client.CoreV1Api()
    with open(path.abspath(nameToYaml(name))) as f:
        ns_obj = yaml.load(f)
        v1.create_namespace(ns_obj)

def createNsPod(ns, name):
    v1 = client.CoreV1Api()
    with open(path.abspath(nameToYaml(name))) as f:
        pod_obj = yaml.load(f)
        v1.create_namespaced_pod(ns, pod_obj)

    # check pod is ready
    def podChecker():
        s = v1.read_namespaced_pod_status(name, ns)
        if s.status.phase == "Running":
            return ""
        return "Pod not ready"

    tutils.assertEventually(podChecker, 1, 180)

def createNsSvc(ns, name):
    v1 = client.CoreV1Api()
    with open(path.abspath(nameToYaml(name))) as f:
        svc_obj = yaml.load(f)
        v1.create_namespaced_service(ns, svc_obj)

    s = v1.read_namespaced_service(name, ns)
    return s.spec.cluster_ip

def createNsNetPol(ns, name):
    nv1 = client.NetworkingV1Api()
    with open(path.abspath(nameToYaml(name))) as f:
        np_obj = yaml.load(f)
        nv1.create_namespaced_network_policy(ns, np_obj)

def replaceNsNetPol(ns, name):
    nv1 = client.NetworkingV1Api()
    with open(path.abspath(nameToYaml(name))) as f:
        np_obj = yaml.load(f)
        nv1.replace_namespaced_network_policy(np_obj["metadata"]["name"], ns, np_obj)

def lbWorkaround():
    sleep(10)  # shortterm work around LB issue

def verifyAccess(ns, pod, ip, port, exp_str):
    v1 = client.CoreV1Api()
    def checker():
        cmd = ['nc', '-zvnw', '1', ip, port]
        resp = stream(v1.connect_get_namespaced_pod_exec, pod,
                      ns, command=cmd, stderr=True, stdin=False,
                      stdout=True, tty=False)
        if exp_str not in resp:
            return "{} gave {}".format(ip, resp)
        return ""
    tutils.assertEventually(checker, 1, 10)

def deleteNsNetPol(ns, npName):
    nv1 = client.NetworkingV1Api()
    nv1.delete_namespaced_network_policy(npName, ns, client.V1DeleteOptions())
    def delChecker():
        npList = nv1.list_namespaced_network_policy(ns)
        for np in npList.items:
            if np.metadata.name is npName:
                return "exists"
        return ""

    tutils.assertEventually(delChecker, 1, 30)

class TestNetworkPolicyE2E(object):

    def test_np(object):
        tutils.tcLog("Verify GW flows are present")
        tutils.checkGwFlows("11.3.0.1")
        tutils.tcLog("Create a namespace, with simple service")
        createNs("e2e")
        createNsPod("e2e", "srvr-80")
        createNsPod("e2e", "srvr-81")
        svcIP = createNsSvc("e2e", "simple-svc")
        
        tutils.tcLog("Create two client pods")
        client_pods = ["client-a", "client-b"]
        for pod in client_pods:
            createNsPod("e2e", pod)
        tutils.tcLog("Verify access without netpol")
        for pod in client_pods:
            verifyAccess("e2e", pod, svcIP, "80", "open")
            verifyAccess("e2e", pod, svcIP, "81", "open")

        tutils.tcLog("Delete clients")
        for pod in client_pods:
            tutils.deletePod("e2e", pod)

        tutils.tcLog("Apply network policy client-a->port80")
        createNsNetPol("e2e", "upd_policy1")
        tutils.tcLog("Create two client pods")
        for pod in client_pods:
            createNsPod("e2e", pod)
        tutils.tcLog("Verify client-a can access port 80")
        verifyAccess("e2e", "client-a", svcIP, "80", "open")
        tutils.tcLog("Verify failures for a/81, b/[80,81]")
        verifyAccess("e2e", "client-a", svcIP, "81", "timed out")
        verifyAccess("e2e", "client-b", svcIP, "80", "timed out")
        verifyAccess("e2e", "client-b", svcIP, "81", "timed out")
        tutils.tcLog("Delete clients")
        for pod in client_pods:
            tutils.deletePod("e2e", pod)

        tutils.tcLog("Update network policy client-b->port81")
        replaceNsNetPol("e2e", "upd_policy2")
        tutils.tcLog("Create two client pods")
        for pod in client_pods:
            createNsPod("e2e", pod)

        tutils.tcLog("Verify client-b can access port 81")
        verifyAccess("e2e", "client-b", svcIP, "81", "open")
        tutils.tcLog("Verify failures for b/81, a/[80,81]")
        verifyAccess("e2e", "client-b", svcIP, "80", "timed out")
        verifyAccess("e2e", "client-a", svcIP, "80", "timed out")
        verifyAccess("e2e", "client-a", svcIP, "81", "timed out")
        v1 = client.CoreV1Api()
        v1.delete_namespace("e2e", client.V1DeleteOptions())
        def nsDelChecker():
            if tutils.namespaceExists("e2e"):
                return "e2e exists"
            return ""

        tutils.tcLog("Verify ns is deleted")
        tutils.assertEventually(nsDelChecker, 2, 40)


