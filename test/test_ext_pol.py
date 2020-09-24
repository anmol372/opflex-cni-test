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
tutils.configSetup()
configuration.assert_hostname = False
k8s_client = client.ApiClient()

# yaml filename must match the object name, per our convention
def nameToYaml(name):
    return "yamls/ext/{}.yaml".format(name)

def createPod(name):
    k8s_api = utils.create_from_yaml(k8s_client, nameToYaml(name))

    # check pod is ready
    def podChecker():
        s = k8s_api.read_namespaced_pod_status(name, "default")
        if s.status.phase == "Running":
            return ""
        return "Pod not ready"

    tutils.assertEventually(podChecker, 1, 60)
    # return IP
    s = k8s_api.read_namespaced_pod_status(name, "default")
    return s.status.pod_ip

# To create a CRD, create a yaml spec file named yamls/<crdname>.yaml
def createCRD(plural, name):
    crd_api = client.CustomObjectsApi(k8s_client)
    crd_name = ""
    with open(path.abspath(nameToYaml(name))) as f:
        crd_obj = yaml.load(f)
        crd_api.create_namespaced_custom_object("aci.aw", "v1", "kube-system", plural, crd_obj)
        crd_name = crd_obj['metadata']['name']

    # check contract is ready
    def crdChecker():
        resp = crd_api.get_namespaced_custom_object("aci.aw", "v1", "kube-system", plural, crd_name)
        if 'spec' in resp or 'status' in resp:
            return ""
        return "CRD {}/{} not created".format(plural, crd_name)

    tutils.assertEventually(crdChecker, 1, 60)

def replaceCRD(plural, name, new_file):
    crd_api = client.CustomObjectsApi(k8s_client)
    orig_obj = crd_api.get_namespaced_custom_object("aci.aw", "v1", "kube-system", plural, name)

    print(orig_obj)
    with open(path.abspath(nameToYaml(new_file))) as f:
        crd_obj = yaml.load(f)
        crd_obj['metadata']['resourceVersion'] = orig_obj['metadata']['resourceVersion']
        crd_api.replace_namespaced_custom_object("aci.aw", "v1", "kube-system", plural, name, crd_obj)

def deleteCRD(plural, name):
    crd_api = client.CustomObjectsApi(k8s_client)
    body = client.V1DeleteOptions()
    crd_api.delete_namespaced_custom_object("aci.aw", "v1", "kube-system", plural, name, body)

class TestExtPol(object):
    def test_policy(object):
        tutils.tcLog("Verify GW flows are present")
        tutils.checkGwFlows("11.3.0.1")
        tutils.tcLog("Setup nettools")
        tutils.setupNettools()
        tutils.tcLog("Setup contracts, epgs and external EP")
        v1 = client.CoreV1Api()
        createCRD("contracts", "tcp-53")
        createCRD("contracts", "icmp")
        createCRD("epgs", "epg-c-icmp-dns")
        createCRD("epgs", "epg-ext-icmp-dns")
        createCRD("podifs", "ep")
        # pod in epg-c
        podIP = createPod("pod-c")
        
        tutils.tcLog("Verify contracts are present")
        contractsToVerify = ["GbpeL24Classifier/tcp-53", "GbpeL24Classifier/icmp"]
        def contractChecker():
            resp = tutils.verifyAgentContracts(contractsToVerify, True)
            if resp == "":
                print("{} present".format(contractsToVerify))
            else:
                print(resp)

            return resp

        tutils.assertEventually(contractChecker, 1, 10)

        tutils.tcLog("Verify ep's are present")
        epIPs = [podIP, "8.8.8.0"]
        def epChecker():
            res = tutils.verifyAgentEPs(epIPs)
            if res == "":
                print("{} present".format(epIPs))
            else:
                print(res)

            return res
        tutils.assertEventually(epChecker, 1, 10)
        tutils.tcLog("Setup node routing for external access")
        tutils.setupNodeRouting("pod-c", "test-node1", "8.8.8.8")
        tutils.tcLog("Verify icmp access to external IP")
        tutils.verifyPing("pod-c", "default", "8.8.8.8")
        tutils.tcLog("Verify tcp 53 access to external IP")
        tutils.verifyTCP("pod-c", "default", "8.8.8.8", "53")

        tutils.tcLog("Change epg-c to consume only dns")
        replaceCRD("epgs", "epg-c", "epg-c-dns")
        sleep(1)
        tutils.tcLog("Verify icmp failure to external IP")
        tutils.verifyPing("pod-c", "default", "8.8.8.8", False)
        tutils.tcLog("Verify tcp 53 access to external IP")
        tutils.verifyTCP("pod-c", "default", "8.8.8.8", "53")

        tutils.tcLog("Change epg-ext to allow only icmp")
        replaceCRD("epgs", "epg-ext", "epg-ext-icmp")
        sleep(1)
        tutils.tcLog("Verify dns failure to external IP")
        tutils.verifyTCP("pod-c", "default", "8.8.8.8", "53", False)
        tutils.verifyPing("pod-c", "default", "8.8.8.8", False)

        tutils.tcLog("Change epg-ext to allow icmp and dns")
        replaceCRD("epgs", "epg-ext", "epg-ext-icmp-dns")
        tutils.tcLog("Verify tcp 53 access to external IP")
        tutils.verifyTCP("pod-c", "default", "8.8.8.8", "53")
        tutils.tcLog("Verify icmp failure to external IP")
        tutils.verifyPing("pod-c", "default", "8.8.8.8", False)

        tutils.tcLog("Change epg-c to consume nothing")
        replaceCRD("epgs", "epg-c", "epg-c-deny")
        tutils.tcLog("Verify icmp failure to external IP")
        tutils.verifyPing("pod-c", "default", "8.8.8.8", False)
        tutils.tcLog("Verify dns failure to external IP")
        tutils.verifyTCP("pod-c", "default", "8.8.8.8", "53", False)

        tutils.tcLog("Change epg-c to allow icmp and dns")
        replaceCRD("epgs", "epg-c", "epg-c-icmp-dns")
        tutils.tcLog("Verify icmp access to external IP")
        tutils.verifyPing("pod-c", "default", "8.8.8.8")
        tutils.tcLog("Verify tcp 53 access to external IP")
        tutils.verifyTCP("pod-c", "default", "8.8.8.8", "53")

        tutils.tcLog("Delete the external ep")
        deleteCRD("podifs", "extnet-dns")

        def epDelChecker():
            res = tutils.verifyAgentEPs(["8.8.8.0"])
            if res == "":
                print("still present")
                return "still present"
            return ""

        tutils.tcLog("Verify external ep removed")
        tutils.assertEventually(epDelChecker, 1, 10)
        tutils.tcLog("Verify icmp failure to external IP")
        tutils.verifyPing("pod-c", "default", "8.8.8.8", False)
        tutils.tcLog("Verify dns failure to external IP")
        tutils.verifyTCP("pod-c", "default", "8.8.8.8", "53", False)

        tutils.setupNodeRouting("pod-c", "test-node1", "8.8.8.8", True)
        tutils.deletePod("default", "pod-c")
        deleteCRD("contracts", "tcp-53")
        deleteCRD("contracts", "icmp")
        deleteCRD("epgs", "epg-c")
        deleteCRD("epgs", "epg-ext")
