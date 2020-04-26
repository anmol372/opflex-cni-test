#!/bin/bash
kubectl --kubeconfig=data/kubeconfig delete rc busybox
kubectl --kubeconfig=data/kubeconfig delete pod pod-a pod-b6020 pod-b6021 alpine-pod
kubectl --kubeconfig=data/kubeconfig delete deployment hostnames-dep
kubectl --kubeconfig=data/kubeconfig delete networkpolicy hostnames-allow-prod
kubectl --kubeconfig=data/kubeconfig delete namespace dev prod
kubectl --kubeconfig=data/kubeconfig delete svc hostnames-svc
kubectl --kubeconfig=data/kubeconfig delete svc dns-test-svc
kubectl --kubeconfig=data/kubeconfig delete epg epg-a epg-b -n kube-system
kubectl --kubeconfig=data/kubeconfig delete contract tcp-6020 tcp-6021 -n kube-system
for file in $(ls test/yamls/ext)
do
    kubectl --kubeconfig=data/kubeconfig delete -f test/yamls/ext/$file
done
kubectl --kubeconfig=data/kubeconfig get namespaces | grep "prod|dev"
agentPod=$(kubectl --kubeconfig=data/kubeconfig get pods -n kube-system -o wide | grep "aci-containers-host" | grep test-node | awk '{print $1}')
kubectl --kubeconfig=data/kubeconfig exec -it $agentPod -n kube-system -c aci-containers-host -- ifconfig veth_host 0.0.0.0
kubectl --kubeconfig=data/kubeconfig exec -it $agentPod -n kube-system -c aci-containers-host -- ip route add 11.3.0.0/16 dev veth_host src 1.100.201.12
