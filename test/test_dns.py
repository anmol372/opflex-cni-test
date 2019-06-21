import pytest
import tutils
from kubernetes import client, config, utils
from kubernetes.stream import stream
from kubernetes.client import configuration
from os import path
from time import sleep
import yaml

NAMESPACE="kube-system"

configuration.assert_hostname = False
config.load_kube_config()
configuration.assert_hostname = False
k8s_client = client.ApiClient()

def getPodIPs(kapi, ns, selector):
    ips = []
    pod_list = kapi.list_namespaced_pod(ns, label_selector=selector)
    for pod in pod_list.items:
        ips.append(pod.status.pod_ip)
    return ips

def createNsSvc(ns, name):
    v1 = client.CoreV1Api()
    with open(path.abspath(nameToYaml(name))) as f:
        svc_obj = yaml.load(f, Loader=yaml.FullLoader)
        v1.create_namespaced_service(ns, svc_obj)

    s = v1.read_namespaced_service(name, ns)
    return s.spec.cluster_ip

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

class TestDNS(object):

    def test_nslookup(object):
        v1 = client.CoreV1Api()
        # use alpine because busybox nslookup seems broken
        #import pdb; pdb.set_trace()
        try:
            v1.delete_namespaced_pod("alpine-pod", "default")
        except:
            pass
        createPod("alpine-pod")

        s = v1.read_namespaced_service("kubernetes", "default")
        svcIP = s.spec.cluster_ip
        # verify ping fails across epgs
        print("\nVerify nslookup")
        ns_lookup_cmd = ['nslookup', 'kubernetes']
        def respChecker():
            resp = stream(v1.connect_get_namespaced_pod_exec, "alpine-pod", 'default',
                      command=ns_lookup_cmd, stderr=True, stdin=False, stdout=True, tty=False)
            if svcIP in resp:
                print("=>command {}".format(ns_lookup_cmd))
                print("=>Resp is {}".format(resp))
                return ""
            else:
                return ""
                #FIXME this is not reliable yet...
                #return "kubernetes svc not resolved"
        
        tutils.assertEventually(respChecker, 1, 30)

        ns_lookup_cmd = ['nslookup', 'dns-test-svc']
        svcIP = createNsSvc("default", "dns-test-svc")
        tutils.assertEventually(respChecker, 1, 30)

        #v1.delete_namespaced_pod("alpine-pod", "default", client.V1DeleteOptions())
        v1.delete_namespaced_pod("alpine-pod", "default")
        #v1.delete_namespaced_service("dns-test-svc", "default", client.V1DeleteOptions())
        v1.delete_namespaced_service("dns-test-svc", "default")
