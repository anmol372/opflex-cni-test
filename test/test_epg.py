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

def checkRCStatus(kapi, replicas):
    s = kapi.read_namespaced_replication_controller_status("busybox", "default")
    if s.status.ready_replicas == replicas:
        return ""
    logging.debug("busybox: Not ready yet...")
    return "Expected {} ready replicas, got {}".format(replicas, s.status.ready_replicas)

def getPodIPs(kapi, ns, selector):
    ips = []
    pod_list = kapi.list_namespaced_pod(ns, label_selector=selector)
    for pod in pod_list.items:
        ips.append(pod.status.pod_ip)
    return ips

# yaml filename must match the object name, per our convention
def nameToYaml(name):
    return "yamls/{}.yaml".format(name)

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
    with open(path.abspath(nameToYaml(name))) as f:
        crd_obj = yaml.load(f)
        crd_api.create_namespaced_custom_object("aci.aw", "v1", "kube-system", plural, crd_obj)

    # check contract is ready
    def crdChecker():
        resp = crd_api.get_namespaced_custom_object("aci.aw", "v1", "kube-system", plural, name)
        if 'spec' in resp:
            return ""
        return "CRD {}/{} not created".format(plural, name)

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

class TestEPG(object):

    def test_default(object):
        tutils.tcLog("Create 3 pods in default epg")
        k8s_api = utils.create_from_yaml(k8s_client, "yamls/busybox.yaml")

        # check rc is ready
        def rcChecker():
            return checkRCStatus(k8s_api, 3)
        tutils.assertEventually(rcChecker, 1, 60)
        tutils.checkAgentLog()
        
        # check pods are ready
        def podChecker():
            pod_list = k8s_api.list_namespaced_pod("default", label_selector="app=busybox")
            if len(pod_list.items) != 3:
                return "Expected 3 pods, got {}".format(len(pod_list.items))
              
            for pod in pod_list.items:
                if pod.status.phase != "Running":
                    return "pod {} status is {}".format(pod.metadata.name, pod.status.phase)

            return ""

        tutils.assertEventually(podChecker, 1, 60)

        # verify connectivity
        ips = getPodIPs(k8s_api, "default", "app=busybox")
        pod_list = k8s_api.list_namespaced_pod("default", label_selector="app=busybox")
        pod = next(iter(pod_list.items), None)
        assert pod != None

        tutils.tcLog("Verify default connectivity")
        def pingChecker():
            ping_cmd = ['ping', '-c', '3']
            for ip in ips:
                v1 = client.CoreV1Api()
                cmd = list(ping_cmd)
                cmd.append(ip)
                resp = stream(v1.connect_get_namespaced_pod_exec, pod.metadata.name, 'default',
                              command=cmd, stderr=True, stdin=False, stdout=True, tty=False)
                logging.debug("=>Resp is {}".format(resp))
                if "3 packets received" not in resp:
                    return "3 packets not received"
            return ""

        tutils.assertEventually(pingChecker, 1, 60)

        tutils.tcLog("Delete pods")
        tutils.scaleRc("busybox", 0)
        k8s_api.delete_namespaced_replication_controller("busybox", "default", client.V1DeleteOptions())

    def test_policy(object):
        v1 = client.CoreV1Api()
        createCRD("contracts", "tcp-6020")
        createCRD("contracts", "tcp-6021")
        sleep(1)
        createCRD("epgs", "epg-a")
        createCRD("epgs", "epg-b")
        # pod in epg-a
        createPod("pod-a")
        # pods in epg-b
        ip_6020 = createPod("pod-b6020")
        ip_6021 = createPod("pod-b6021")
        tutils.checkAgentLog()

        # verify ping fails across epgs
        tutils.tcLog("Verify ping failure across epgs")
        ping_cmd = ['ping', '-c', '6', '-t', '1', ip_6020]
        resp = stream(v1.connect_get_namespaced_pod_exec, "pod-a", 'default',
                      command=ping_cmd, stderr=True, stdin=False, stdout=True, tty=False)
        logging.debug("=>Resp is {}".format(resp))
        assert "0 packets received" in resp

        tutils.tcLog("Verify tcp contract")
        # verify port 6020 access from pod-a to epg-b
        tutils.tcLog("port 6020 access from pod-a to epg-b")
        cmd1 = ['nc', '-zvnw', '1', ip_6020, '6020']
        resp = stream(v1.connect_get_namespaced_pod_exec, "pod-a", 'default',
                      command=cmd1, stderr=True, stdin=False, stdout=True, tty=False)
        logging.debug("=>pod-a to epg-b[6020] Resp is {}".format(resp))
        assert "open" in resp

        sleep(5)
        # verify port 6021 is inaccessible from pod-a to epg-b
        tutils.tcLog("port 6021 deny from pod-a to epg-b")
        cmd2 = ['nc', '-zvnw', '1', ip_6021, '6021']
        resp = stream(v1.connect_get_namespaced_pod_exec, "pod-a", 'default',
                      command=cmd2, stderr=True, stdin=False, stdout=True, tty=False)
        logging.debug("=>pod-a to epg-b[6021] Resp is {}".format(resp))
        assert "timed out" in resp

        sleep(5)
        # verify port 6021 is accessible within epg-b
        tutils.tcLog("port 6021 accessible within epg-b")
        resp = stream(v1.connect_get_namespaced_pod_exec, "pod-b6020", 'default',
                      command=cmd2, stderr=True, stdin=False, stdout=True, tty=False)
        logging.debug("=>pod-b6020 to pod-b[6021] Resp is {}".format(resp))
        assert "open" in resp

        tutils.tcLog("Change allowed port to 6021")
        replaceCRD("epgs", "epg-a", "epg-a-upd")
        replaceCRD("epgs", "epg-b", "epg-b-upd")
        tutils.tcLog("Verify new contract is on agents")
        def contractChecker():
            resp = tutils.verifyAgentContracts(["GbpeL24Classifier/tcp-6021"], True)
            if resp == "":
                print("GbpeL24Classifier/tcp-6021 present")
            else:
                print(resp)

            return resp

        tutils.assertEventually(contractChecker, 1, 10)
        sleep(5)
        tutils.tcLog("port 6021 now allowed from pod-a to epg-b")
        cmd2 = ['nc', '-zvnw', '1', ip_6021, '6021']
        resp = stream(v1.connect_get_namespaced_pod_exec, "pod-a", 'default',
                      command=cmd2, stderr=True, stdin=False, stdout=True, tty=False)
        logging.debug("=>pod-a to epg-b[6021] Resp is {}".format(resp))
        assert "open" in resp

        def contractRemChecker():
            resp = tutils.verifyAgentContracts(["GbpEpGroupToConsContractRSrc/288/tcp-6020", "GbpEpGroupToProvContractRSrc/288/tcp-6020"], False)
            if resp == "":
                print("GbpEpGroupToConsContractRSrc/288/tcp-6020, GbpEpGroupToProvContractRSrc/288/tcp-6020 removed")
            else:
                print(resp)

            return resp

        tutils.assertEventually(contractRemChecker, 1, 10)
        tutils.tcLog("port 6020 now denied from pod-a to epg-b")
        cmd1 = ['nc', '-zvnw', '1', ip_6020, '6020']
        resp = stream(v1.connect_get_namespaced_pod_exec, "pod-a", 'default',
                      command=cmd1, stderr=True, stdin=False, stdout=True, tty=False)
        logging.debug("=>pod-a to epg-b[6020] Resp is {}".format(resp))
        assert "timed out" in resp

        toDelete = ["pod-a", "pod-b6020", "pod-b6021"]
        logging.info("Deleting {}\n".format(toDelete))
        for pod in toDelete:
            v1.delete_namespaced_pod(pod, "default", client.V1DeleteOptions())
        for pod in toDelete:
            tutils.checkPodDeleted(v1, "default", pod, 120)

        deleteCRD("contracts", "tcp-6020")
        deleteCRD("contracts", "tcp-6021")
        deleteCRD("epgs", "epg-a")
        deleteCRD("epgs", "epg-b")
        tutils.checkAgentLog()
