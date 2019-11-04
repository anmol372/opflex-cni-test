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

def getPodNames(kapi, ns, selector):
    names = []
    pod_list = kapi.list_namespaced_pod(ns, label_selector=selector)
    for pod in pod_list.items:
        if pod.status.phase == "Running":
            names.append(pod.metadata.name)
    return names

# yaml filename must match the object name, per our convention
def nameToYaml(name):
    return "yamls/{}.yaml".format(name)

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

    tutils.assertEventually(podChecker, 1, 30)

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

class TestNetworkPolicy(object):

    def test_np(object):
        # create a service/deployment in default namespace
        svcIP = createNsSvc("default", "hostnames-svc")
        k8s_api = utils.create_from_yaml(k8s_client, "yamls/hostnames-dep.yaml")
        v1 = client.CoreV1Api()

        # check deployment is ready
        svc_hosts = []
        def depChecker():
            svc_hosts = getPodNames(v1, "default", "app=hostnames")
            if len(svc_hosts) == 3:
                return ""
            return "Need 3 hosts, have {}".format(len(svc_hosts))

        tutils.assertEventually(depChecker, 1, 30)

        # create two namespaces, with a client pod in each
        nsList = ["prod", "dev"]
        for ns in nsList:
            createNs(ns)
        print("\nWaiting for namespaces to be available")
        sleep(3)
        for ns in nsList:
            createNsPod(ns, "client-pod")
        
        print("\nVerify loadbalancing")
        # verify both clients can access the service, and the service load balances.
        for ns in nsList:
            cmd = ['curl', '--connect-timeout', '1', '-s', svcIP]
            backends = dict()
            for count in range(0, 30):
                resp = stream(v1.connect_get_namespaced_pod_exec, "client-pod", ns,
                              command=cmd, stderr=True, stdin=False, stdout=True, tty=False)
                if resp == "":
                    sleep(1)
                    continue

                backends[resp] = True
                if len(backends) == 2:
                    break
            assert len(backends) == 2
            print("backends: {}".format(backends.keys()))

        # apply networkpolicy allowing access only to prod
        createNsNetPol("default", "hostnames-allow-prod")

        cmd = ['curl', '--connect-timeout', '1', svcIP]
        # wait for netpol to take effect
        def waiter():
            count = 0
            for ix in range(0, 10):
                resp1 = stream(v1.connect_get_namespaced_pod_exec, "client-pod", "dev",
                              command=cmd, stderr=True, stdin=False, stdout=True, tty=False)
                if "timed out" in resp1:
                    count += 1
                else:
                    sleep(1)

                if count == 10:
                    return ""
            return "still accessible"

        print("\nVerify k8s network policy")
        tutils.assertEventually(waiter, 1, 5)

        # verify prod can access the svc
        for ix in range(0, 5):
            cmd2 = ['nc', '-zvnw', '1', svcIP, '80']
            resp2 = stream(v1.connect_get_namespaced_pod_exec, "client-pod", "prod",
                          command=cmd2, stderr=True, stdin=False, stdout=True, tty=False)
            print("prod: {}".format(resp2))
            assert "open" in resp2

        # and dev can't
        for ix in range(0, 5):
            resp3 = stream(v1.connect_get_namespaced_pod_exec, "client-pod", "dev",
                          command=cmd2, stderr=True, stdin=False, stdout=True, tty=False)
            print("dev: {}".format(resp3))
            assert "timed out" in resp3

        # delete everything
        for ns in nsList:
            v1.delete_namespace(ns, client.V1DeleteOptions()) # deletes the client-pod too

        nv1 = client.NetworkingV1Api()
        nv1.delete_namespaced_network_policy("hostnames-allow-prod", "default", client.V1DeleteOptions())
        v1.delete_namespaced_service("hostnames-svc", "default", client.V1DeleteOptions())
        av1 = client.AppsV1Api()
        av1.delete_namespaced_deployment("hostnames-dep", "default", client.V1DeleteOptions())
        

