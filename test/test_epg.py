import pytest
import tutils
from kubernetes import client, config, utils
from kubernetes.stream import stream
from kubernetes.client import configuration
from os import path

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
        ping_cmd = ['ping', '-c', '3']
        for ip in ips:
            v1 = client.CoreV1Api()
            cmd = list(ping_cmd)
            cmd.append(ip)
            resp = stream(v1.connect_get_namespaced_pod_exec, pod.metadata.name, 'default',
                          command=cmd, stderr=True, stdin=False, stdout=True, tty=False)
            #out = resp.read_stdout()
            print("=>Resp is {}".format(resp))
            assert "3 packets received" in resp

        k8s_api.delete_namespaced_replication_controller("busybox", "default", client.V1DeleteOptions())
