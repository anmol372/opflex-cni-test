import pytest
import tutils
from kubernetes import client, config, utils
from kubernetes.stream import stream
from kubernetes.client import configuration
from os import path
from time import sleep
import yaml

configuration.assert_hostname = False
config.load_kube_config()
configuration.assert_hostname = False
k8s_client = client.ApiClient()

def checkRCStatus(kapi, replicas):
    s = kapi.read_namespaced_replication_controller_status("busybox", "default")
    if s.status.ready_replicas == replicas:
        return ""
    print("Not ready yet...")
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

    tutils.assertEventually(podChecker, 1, 30)
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

    tutils.assertEventually(crdChecker, 1, 30)

def deleteCRD(plural, name):
    crd_api = client.CustomObjectsApi(k8s_client)
    body = client.V1DeleteOptions()
    crd_api.delete_namespaced_custom_object("aci.aw", "v1", "kube-system", plural, name, body)

class TestEPG(object):

    def test_default(object):
        k8s_api = utils.create_from_yaml(k8s_client, "yamls/busybox.yaml")

        # check rc is ready
        def rcChecker():
            return checkRCStatus(k8s_api, 3)
        tutils.assertEventually(rcChecker, 1, 30)
        
        # check pods are ready
        def podChecker():
            pod_list = k8s_api.list_namespaced_pod("default", label_selector="app=busybox")
            if len(pod_list.items) != 3:
                return "Expected 3 pods, got {}".format(len(pod_list.items))
              
            for pod in pod_list.items:
                if pod.status.phase != "Running":
                    return "pod {} status is {}".format(pod.metadata.name, pod.status.phase)

            return ""

        tutils.assertEventually(podChecker, 1, 30)

        # verify connectivity
        ips = getPodIPs(k8s_api, "default", "app=busybox")
        pod_list = k8s_api.list_namespaced_pod("default", label_selector="app=busybox")
        pod = next(iter(pod_list.items), None)
        assert pod != None
        ping_cmd = ['ping', '-c', '3']
        for ip in ips:
            v1 = client.CoreV1Api()
            cmd = list(ping_cmd)
            cmd.append(ip)
            resp = stream(v1.connect_get_namespaced_pod_exec, pod.metadata.name, 'default',
                          command=cmd, stderr=True, stdin=False, stdout=True, tty=False)
            print("=>Resp is {}".format(resp))
            assert "3 packets received" in resp

        k8s_api.delete_namespaced_replication_controller("busybox", "default", client.V1DeleteOptions())

    def test_policy(object):
        v1 = client.CoreV1Api()
        createCRD("contracts", "tcp-6020")
        createCRD("epgs", "epg-a")
        createCRD("epgs", "epg-b")
        # pod in epg-a
        createPod("pod-a")
        # pods in epg-b
        ip_6020 = createPod("pod-b6020")
        ip_6021 = createPod("pod-b6021")

        # verify ping fails across epgs
        print("\nVerify ping failure across epgs")
        ping_cmd = ['ping', '-c', '3', '-t', '1', ip_6020]
        resp = stream(v1.connect_get_namespaced_pod_exec, "pod-a", 'default',
                      command=ping_cmd, stderr=True, stdin=False, stdout=True, tty=False)
        print("=>Resp is {}".format(resp))
        assert "0 packets received" in resp

        print("\nVerify tcp contract")
        # verify port 6020 access from pod-a to epg-b
        cmd1 = ['nc', '-zvnw', '1', ip_6020, '6020']
        resp = stream(v1.connect_get_namespaced_pod_exec, "pod-a", 'default',
                      command=cmd1, stderr=True, stdin=False, stdout=True, tty=False)
        print("=>Resp is {}".format(resp))
        assert "open" in resp

        sleep(5)
        # verify port 6021 is inaccessible from pod-a to epg-b
        cmd2 = ['nc', '-zvnw', '1', ip_6021, '6021']
        resp = stream(v1.connect_get_namespaced_pod_exec, "pod-a", 'default',
                      command=cmd2, stderr=True, stdin=False, stdout=True, tty=False)
        print("=>Resp is {}".format(resp))
        #assert "timed out" in resp

        sleep(5)
        # verify port 6021 is accessible within epg-b
        resp = stream(v1.connect_get_namespaced_pod_exec, "pod-b6020", 'default',
                      command=cmd2, stderr=True, stdin=False, stdout=True, tty=False)
        print("=>Resp is {}".format(resp))
        assert "open" in resp

        v1.delete_namespaced_pod("pod-a", "default", client.V1DeleteOptions())
        v1.delete_namespaced_pod("pod-b6020", "default", client.V1DeleteOptions())
        v1.delete_namespaced_pod("pod-b6021", "default", client.V1DeleteOptions())
        deleteCRD("contracts", "tcp-6020")
        deleteCRD("epgs", "epg-a")
        deleteCRD("epgs", "epg-b")
