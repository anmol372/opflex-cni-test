import pytest
import logging
import tutils
from kubernetes import client, config, utils
from kubernetes.stream import stream
from kubernetes.client import configuration
from kubernetes.client.rest import ApiException
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

def assertPodReady(ns, name, timeout):
    v1 = client.CoreV1Api()

    # check pod is ready
    def podChecker():
        s = v1.read_namespaced_pod_status(name, ns)
        if s.status.phase != "Running":
            return "Pod not running"
            
        for cond in s.status.conditions:
            if cond.type == "ContainersReady" and cond.status == "True":
                return ""

        return "Containers not ready"

    tutils.assertEventually(podChecker, 1, timeout)

def kafkaChecker(epKeys, respWord, attempts=2):
    v1 = client.CoreV1Api()
    def checkIt():
        for epid in epKeys:
            cmd = ['./kafkakv', '-key']
            cmd.append(epid)
            resp = stream(v1.connect_get_namespaced_pod_exec, "kafkakv", 'default', command=cmd, stderr=True, stdin=False, stdout=True, tty=False)
            #print("cmd:{} resp: {}".format(cmd, resp))
            if respWord in resp and epid in resp:
                continue

            return "{} -- not yet {}".format(epid, respWord)

        return ""

    tutils.assertEventually(checkIt, 1, attempts)

def kafkaSyncChecker(epKeys, attempts=2):
    v1 = client.CoreV1Api()
    def checkIt():
        cmd = ['./kafkakv', '-time-out', '30', '-key-list', ",".join(epKeys)]
        logging.debug("Command: {}".format(cmd))
        resp = stream(v1.connect_get_namespaced_pod_exec, "kafkakv", 'default', command=cmd, stderr=True, stdin=False, stdout=True, tty=False)
            #print("cmd:{} resp: {}".format(cmd, resp))
        if "exact match" in resp:
            return ""

        return "Got: {}".format(resp)

    tutils.assertEventually(checkIt, 1, attempts)

def scaleDep(ns, name, replicas):
    v1 = client.AppsV1Api()
    scale = v1.read_namespaced_deployment_scale(name, ns)
    scale.spec.replicas = replicas
    resp = v1.replace_namespaced_deployment_scale(name, ns, scale)
    def scaleChecker():
        curr = v1.read_namespaced_deployment_status(name, ns)
        if curr.status.ready_replicas is None and replicas == 0:
            return ""

        if curr.status.ready_replicas == replicas:
            return ""

        return "expected {} replicas, got {}".format(replicas, curr.status.ready_replicas)

    tutils.assertEventually(scaleChecker, 1, 30)

def readCniEPList():
    crdApi = client.CustomObjectsApi()
    group = "aci.aw"
    ns = "kube-system"
    epList = crdApi.list_namespaced_custom_object(group, "v1", ns, "podifs")
    cniEPList = []
    for k, eps in epList.items():
        if type(eps) is not list:
            continue
        for ep in eps:
            epStatus = tutils.SafeDict(ep['status'])
            if epStatus['podns'] is 'missing':
                logging.debug("MarkerID is {}".format(epStatus['containerID']))
                continue

            epID = "{}.{}.{}".format(epStatus['podns'],epStatus['podname'], epStatus['ifname'])
            cniEPList.append(epID)

    return cniEPList


kafkaYamls = ["zookeeper-ss.yaml", "zookeeper-hl.yaml", "zookeeper-svc.yaml", "kafka-ss.yaml", "kafka-hl.yaml", "kafka-svc.yaml", "kkv.yaml"]

class TestKafkaInterface(object):

    def test_kafka(object):
        # setup kafka services
        tutils.tcLog("Setup kafka services")
        for ky in kafkaYamls:
            try:
                utils.create_from_yaml(k8s_client, "yamls/"+ky)
            except ApiException as e:
                logging.debug("{} - ignored".format(e.reason))

        k8s_api = client.CoreV1Api()
        # check kafka server is ready
        assertPodReady("default", "ut-kafka-0", 120)
        assertPodReady("default", "kafkakv", 120)
        sleep(5)

        # collect the current list of ep's from k8s
        tutils.tcLog("Collect ep's from k8s")
        initialEPList = readCniEPList()
        logging.debug("EPList is {}".format(initialEPList))

        tutils.tcLog("Verifying initial EPList with kafka")
        kafkaSyncChecker(initialEPList)

        tutils.tcLog("Adding a pod and checking it in kafka")
        utils.create_from_yaml(k8s_client, "yamls/alpine-pod.yaml")
        assertPodReady("default", "alpine-pod", 45)

        tutils.tcLog("Check for podif")
        crdApi = client.CustomObjectsApi()
        group = "aci.aw"
        ns = "kube-system"
        p = crdApi.get_namespaced_custom_object(group, "v1", ns, "podifs", "default.alpine-pod")
        logging.debug("podif: {}".format(p))
        epStatus = p['status']
        epID = "{}.{}.{}".format(epStatus['podns'], epStatus['podname'], epStatus['ifname'])
        toCheck = []
        toCheck.append(epID)
        kafkaChecker(toCheck, "found")
        tutils.tcLog("Delete a pod and check removal from kafka")
        k8s_api.delete_namespaced_pod("alpine-pod", "default", client.V1DeleteOptions())
        kafkaChecker(toCheck, "missing", 8)

        tutils.tcLog("Recheck ep sync between k8s and kafka")
        kafkaSyncChecker(initialEPList)
        tutils.tcLog("Add more endpoints")
        utils.create_from_yaml(k8s_client, "yamls/busybox.yaml")
        tutils.rcCheckScale("busybox", 3)
        tutils.tcLog("Get new eplist from k8s")
        EPList1 = readCniEPList()
        assert EPList1 != initialEPList
        tutils.tcLog("Recheck ep sync between k8s and kafka")
        kafkaSyncChecker(EPList1)

        tutils.tcLog("Bring controller down")
        scaleDep("kube-system", "aci-containers-controller", 0)
        sleep(10)
        tutils.tcLog("Change some endpoints")
        tutils.scaleRc("busybox", 0)
        tutils.checkPodsRemoved("app=busybox")
        EPList2 = readCniEPList()
        assert EPList2 != EPList1
        tutils.scaleRc("busybox", 2)
        sleep(5)

        logging.debug("previous ep list:{}".format(EPList1))
        EPList3 = readCniEPList()
        logging.debug("new ep list:{}".format(EPList3))
        assert EPList3 != EPList1
        tutils.tcLog("Bring controller up")
        scaleDep("kube-system", "aci-containers-controller", 1)
        sleep(10)
        tutils.tcLog("Check ep sync again")
        kafkaSyncChecker(EPList3, 4)
        
