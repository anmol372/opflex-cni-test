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

def getNodeIPs(kapi):
    ips = []
    node_list = kapi.list_node()
    for node in node_list.items:
        for addr in node.status.addresses:
            if addr.type == "InternalIP":
                ips.append(addr.address)
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

class TestConnectivity(object):

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
        pod_ips = getPodIPs(k8s_api, "default", "app=busybox")

        tutils.tcLog("Verify EPs are populated")
        def remEPChecker():
            res = tutils.verifyAgentEPs(pod_ips)
            if res == "":
                print("{} present".format(pod_ips))
            else:
                print(res)

            return res

        tutils.assertEventually(remEPChecker, 1, 10)

        node_ips = getNodeIPs(k8s_api)
        ips = pod_ips + node_ips
        print("ip's are: {}".format(ips))
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
                print("=>Resp is {}".format(resp))
                if "3 packets received" not in resp:
                    return "3 packets not received"
            return ""

        tutils.assertEventually(pingChecker, 1, 60)
        tutils.tcLog("Check pods access to API server")

        v1 = client.CoreV1Api()
        s = v1.read_namespaced_service("kubernetes", "default")
        svcIP = s.spec.cluster_ip
        logging.debug("=>K8s svc IP is {}".format(svcIP))

        pod_list = k8s_api.list_namespaced_pod("default", label_selector="app=busybox")
        cmd2 = ['nc', '-zvnw', '1', svcIP, '443']
        def k8sChecker():
            for pod in pod_list.items:
                resp = stream(v1.connect_get_namespaced_pod_exec, pod.metadata.name, 'default',
                              command=cmd2, stderr=True, stdin=False, stdout=True, tty=False)
                logging.debug("=>Resp is {}".format(resp))
                if "open" not in resp:
                    return resp

            return ""

        tutils.assertEventually(k8sChecker, 1, 10)

        tutils.tcLog("Delete pods")
        tutils.scaleRc("busybox", 0)
        k8s_api.delete_namespaced_replication_controller("busybox", "default", client.V1DeleteOptions())


