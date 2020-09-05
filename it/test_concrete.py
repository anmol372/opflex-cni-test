import pytest
import os
import json
import paramiko
import base64
import ipaddress
from acc_provision import acc_provision, apic_provision
import logging
import tutils
from time import sleep
from kubernetes import client, config

tutils.logSetup()
config.load_kube_config()
v1 = client.CoreV1Api()

def setup_config():
    prov_inp_file = os.getenv('PROV_INP_FILE', "./provision_input.yaml")
    uc = acc_provision.config_user(prov_inp_file)
    admin_pw = os.getenv('PSWD', "")
    uc["aci_config"]["apic_login"] = {}
    uc["aci_config"]["apic_login"]["username"] = "admin"
    uc["aci_config"]["apic_login"]["password"] = admin_pw
    uc["aci_config"]["apic_login"]["timeout"] = None
    uc["aci_config"]["capic"] = True
    uc["aci_config"]["apic_proxy"] = None
    uc["provision"] = {
            "prov_apic": True,
            "debug_apic": False,
            "save_to": "",
            "skip-kafka-certs": True,
        }
    acc_provision.deep_merge(uc, acc_provision.config_default())
    return uc

class TestBasic(object):
    def setup(object):
        object.config = setup_config()
        object.apic = acc_provision.get_apic(object.config)


    def verifyClusterInfo(object):
        vmm_name = object.config["aci_config"]["system_id"]
        tn_name = object.config["aci_config"]["tenant"]["name"]
        tutils.tcLog("Verify cluster info objects for {}/{}".format(tn_name,vmm_name))
        moClasses = ["compClusterInfo", "hcloudClusterInfo"]
        for moCl in moClasses:
            qry = '/api/class/{}.json?query-target-filter=and(eq({}.name,"{}"),eq({}.accountName,"{}"))'.format(moCl, moCl, moCl, vmm_name, tn_name)
            resp = object.apic.get(path=qry)
            resJson = json.loads(resp.content)
            assert len(resJson["imdata"]) == 1

    def countCompHv(object):
        vmm_name = object.config["aci_config"]["system_id"]
        tutils.tcLog("Count compHv objects for {}".format(vmm_name))
        qry = '/api/mo/comp/prov-Kubernetes/ctrlr-[{}]-{}.json?query-target=children&target-subtree-class=compHv'.format(vmm_name, vmm_name)
        resp = object.apic.get(path=qry)
        resJson = json.loads(resp.content)
        return len(resJson["imdata"])

    def getCSRs(object):
        tutils.tcLog("Get csr objects")
        qry = '/api/class/hcloudCsr.json'
        resp = object.apic.get(path=qry)
        resJson = json.loads(resp.content)
        return resJson["imdata"]

    def getCniTep(object):
        tutils.tcLog("Get CniTep objects")
        qry = '/api/class/hcl3CniTep.json'
        resp = object.apic.get(path=qry)
        resJson = json.loads(resp.content)
        tepList = []
        for mo in resJson['imdata']:
            addr = mo['hcl3CniTep']['attributes']['addr']
            tep = addr.split("/")[0]
            tepList.append(tep)
        return tepList

    def verifyCsr(object, csr, tunnelInfo, vrf_encap_id):
        dn = csr["hcloudCsr"]["attributes"]["dn"]
        qry = '/api/mo/{}.json?query-target=subtree&target-subtree-class=hcloudEndPointOper&query-target-filter=and(ne(hcloudEndPointOper.publicIpv4Addr,"0.0.0.0"))'.format(dn)
        resp = object.apic.get(path=qry)
        resJson = json.loads(resp.content)

        def getCsrIP():
            for epOper in resJson["imdata"]:
                if "hcloudEndPointOper" in epOper:
                    att = epOper["hcloudEndPointOper"]["attributes"]
                    operDn = att["dn"]
                    if "nwif-0" in operDn:
                        print("CSR IP: {}".format(att["publicIpv4Addr"]))
                        return att["publicIpv4Addr"]
            return None
        csrIP = getCsrIP()
        assert csrIP is not None
        print(csrIP)
        csr_c = paramiko.SSHClient()
        csr_c.load_system_host_keys()
        csr_c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        pw = object.config["aci_config"]["apic_login"]["password"]
        csr_c.connect(csrIP, username='admin', password=pw)
        stdin, stdout, stderr = csr_c.exec_command('show run | sec interface Tunn')
        # format output
        out_dict = {}
        key = ""
        for line in stdout:
            ll = line.strip('\n')
            #print(ll)
            if "interface Tunnel" in ll:
                key = ll.split()[1]
                out_dict[key] = {}
            else:
              if key:
                  out_dict[key][ll.strip()] = True
        csr_c.close()
        object.verifyTunnels(out_dict, tunnelInfo, vrf_encap_id)
        object.verifyCsrRoutes(csr_c, csrIP)

    def verifyTunnels(object, out, tunnelInfo, vrf_encap_id):
        macSetting = "tunnel mode vxlan ipv4 0000.5e00.5213 0022.bdf8.19ff"
        vnidSetting = "tunnel vxlan vni {}".format(vrf_encap_id)
        tutils.tcLog("Verify tunnels {} is in CSR".format(tunnelInfo))
        #print(out)
        for id in tunnelInfo:
            intf = "Tunnel{}".format(id)
            assert intf in out
            tun_dest = "tunnel destination {}".format(tunnelInfo[id])
            assert tun_dest in out[intf]
            assert vnidSetting in out[intf]
            assert macSetting in out[intf]

    def verifyCsrRoutes(object, csr_c, csrIP):
        def gwToSubnet(gw):
            u_gw = '{}'.format(str(gw))
            nw = str(ipaddress.ip_network(u_gw, strict=False))
            return nw.split("/")[0]

        pw = object.config["aci_config"]["apic_login"]["password"]
        csr_c.connect(csrIP, username='admin', password=pw)
        stdin, stdout, stderr = csr_c.exec_command('show run | sec ip route')
        ulCidr = gwToSubnet(object.config["net_config"]["machine_cidr"])
        olCidr = gwToSubnet(object.config["net_config"]["pod_subnet"])
        vmCidr = os.getenv('VM_CIDR', "121.1.0.0")
        reqd_routes = [ulCidr, olCidr, vmCidr]
        print(reqd_routes)
        for line in stdout:
            if len(reqd_routes) == 0:
                break

            for route in reqd_routes:
                if route in line:
                    reqd_routes.remove(route)
                    break
            print('++ ' + line.strip('\n'))
        csr_c.close()
        #assert len(reqd_routes) == 0
        if len(reqd_routes) != 0:
            print("FAIL!!! {} not found".format(reqd_routes))

    def verifyULConnectivity(object, tepList):
        tutils.tcLog("Create pods in host ns")
        pods = tutils.createTesterDs()
        tutils.tcLog("Verify connectivity from host ns to teps {}".format(tepList))
        for pod in pods:
            for tep in tepList:
                tutils.verifyPing(pod, "default", tep)
        tutils.tcLog("Delete pods in host ns")
        tutils.deleteTesterDs()

    def getTunnelInfo(object):
        csrTunnelOffset = 54001
        tunnel_to_ip = {}
        tunnel_ids = tutils.read_gbps_tunnel_ids()
        assert len(tunnel_ids) > 0
        for key in tunnel_ids:
            tunnel_to_ip[tunnel_ids[key] + csrTunnelOffset] = key
        return tunnel_to_ip

    def test_concrete(object):
        object.setup()
        addr = object.config["aci_config"]["apic_hosts"][0]
        tutils.tcLog("Verify capic {} access".format(addr))
        assert object.apic is not None
        object.verifyClusterInfo()
        nodeCount = object.countCompHv()
        print("nodeCount: {}".format(nodeCount))
        csrList = object.getCSRs()
        csrCount = len(csrList)
        print("csrCount: {}".format(csrCount))
        if nodeCount == 0 or csrCount == 0:
            print("No further tests possible with these csr/compHv count")
            return
        tepList = object.getCniTep() 
        assert len(tepList) > 0
        object.verifyULConnectivity(tepList)
        tunnelInfo = object.getTunnelInfo()
        print(tunnelInfo)
        vrf_encap_id = tutils.read_vrf_encap_id()
        print("vrf-encap-id is {}".format(vrf_encap_id))
        for csr in csrList:
            object.verifyCsr(csr, tunnelInfo, vrf_encap_id)
