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

def lbWorkaround():
    sleep(10)  # shortterm work around LB issue

def verifyAccess(ns, exp_str, podIPs):
    v1 = client.CoreV1Api()
    def checker():
        for ip in podIPs:
            cmd = ['nc', '-zvnw', '1', ip, '9376']
            resp = stream(v1.connect_get_namespaced_pod_exec, "client-pod",
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

class TestNetworkPolicyDetailed(object):

    def test_np(object):
        tutils.tcLog("Verify GW flows are present")
        tutils.checkGwFlows("11.3.0.1")
        createNs("prod")
        # create a deployment in default namespace
        k8s_api = utils.create_from_yaml(k8s_client, "yamls/hostnames-dep.yaml")
        v1 = client.CoreV1Api()

        # check deployment is ready
        svc_hosts = []
        def depChecker():
            svc_hosts = getPodNames(v1, "default", "app=hostnames")
            if len(svc_hosts) >= 3:
                return ""
            return "Need 3 hosts, have {}".format(len(svc_hosts))

        tutils.assertEventually(depChecker, 1, 180)
        createNsPod("default", "client-pod")
        
        tutils.tcLog("Verify access without netpol")
        podIPs = tutils.getPodIPs("default", "app=hostnames")
        assert len(podIPs) == 3
        verifyAccess('default', 'open', podIPs)
        # apply networkpolicy allowing access only to prod
        tutils.tcLog("Create k8s network policy")
        createNsNetPol("default", "np/hostnames-deny-all")
        tutils.tcLog("Verify access denied")
        verifyAccess('default', 'timed out', podIPs)

        tutils.tcLog("Setup a netpol to allow access from prod")
        createNsNetPol("default", "hostnames-allow-prod")
        createNsPod("prod", "client-pod")
        tutils.tcLog("Verify allow from prod")
        verifyAccess('prod', 'open', podIPs)
        tutils.tcLog("Verify deny from default")
        verifyAccess('default', 'timed out', podIPs)

        tutils.tcLog("Delete deny-all")
        deleteNsNetPol('default', 'hostnames-deny-all')
        tutils.tcLog("Verify allow from prod")
        verifyAccess('prod', 'open', podIPs)
        tutils.tcLog("Verify deny from default")
        verifyAccess('default', 'timed out', podIPs)
        tutils.tcLog("Delete allow-prod")
        deleteNsNetPol('default', 'hostnames-allow-prod')
        tutils.tcLog("Verify allow from default")
        verifyAccess('default', 'open', podIPs)
        tutils.tcLog("Verify allow from prod")
        verifyAccess('prod', 'open', podIPs)

        tutils.tcLog("Allow port 9000 from prod")
        createNsNetPol("default", "np/hostnames-allow-prod9000")
        tutils.tcLog("Verify deny from default")
        verifyAccess('default', 'timed out', podIPs)
        tutils.tcLog("Verify deny 9376 from prod")
        verifyAccess('prod', 'timed out', podIPs)
        tutils.tcLog("Delete allow-prod9000")
        deleteNsNetPol('default', 'hostnames-allow-prod9000')

        tutils.tcLog("Allow port 9376 from prod")
        createNsNetPol("default", "np/hostnames-allow-prod9376")
        tutils.tcLog("Verify allow from prod")
        verifyAccess('prod', 'open', podIPs)
        tutils.tcLog("Verify deny from default")
        verifyAccess('default', 'timed out', podIPs)

        tutils.tcLog("Delete allow-prod9376")
        deleteNsNetPol('default', 'hostnames-allow-prod9376')
        tutils.tcLog("Verify allow from default")
        verifyAccess('default', 'open', podIPs)
        tutils.tcLog("Verify allow from prod")
        verifyAccess('prod', 'open', podIPs)

        tutils.scaleDep("default", "hostnames-dep", 0)
        v1.delete_namespace('prod', client.V1DeleteOptions()) # deletes the client-pod too
        av1 = client.AppsV1Api()
        av1.delete_namespaced_deployment("hostnames-dep", "default", client.V1DeleteOptions())
        tutils.deletePod("default", "client-pod")
        def delChecker():
            dList = av1.list_namespaced_deployment("default")
            for dep in dList.items:
                if dep.metadata.name == "hostnames-dep":
                    return "hostnames-dep still present"
            if tutils.namespaceExists('prod'):
                return "prod exists"
            return ""

        tutils.tcLog("Verify cleanup")
        tutils.assertEventually(delChecker, 2, 40)

