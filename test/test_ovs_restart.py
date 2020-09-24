import pytest
import tutils
import logging
from kubernetes import client, config, utils
from kubernetes.stream import stream
from kubernetes.client import configuration
from time import sleep
import yaml
import os

tutils.logSetup()
configuration.assert_hostname = False
tutils.configSetup()
configuration.assert_hostname = False
kapi = client.ApiClient()
v1 = client.CoreV1Api()

class TestOVSRestart(object):

    def test_ovs_restart(object):
        tutils.tcLog("Getting list of ovs pods")
        node_list = v1.list_node()
        ns = tutils.getSysNs()
        pod_list = v1.list_namespaced_pod(ns, label_selector="name=aci-containers-openvswitch")
        assert len(node_list.items) > 0
        assert len(node_list.items) == len(pod_list.items)
        tutils.tcLog("Delete current ovs pods")
        for pod in pod_list.items:
            tutils.deletePod(ns, pod.metadata.name)

        tutils.tcLog("Check new ovs pods")
        def checker():
            new_pod_list = v1.list_namespaced_pod(ns, label_selector="name=aci-containers-openvswitch")
            if len(pod_list.items) == len(new_pod_list.items):
                return ""
            return "{} ne {}".format(len(new_pod_list.items), len(pod_list.items))
 
        tutils.assertEventually(checker, 2, 30)
