#!/bin/bash
kubectl --kubeconfig=data/kubeconfig delete rc busybox
kubectl --kubeconfig=data/kubeconfig delete pod pod-a pod-b6020 pod-b6021
kubectl --kubeconfig=data/kubeconfig delete deployment hostnames-dep
kubectl --kubeconfig=data/kubeconfig delete networkpolicy hostnames-allow-prod
kubectl --kubeconfig=data/kubeconfig delete namespace dev prod
kubectl --kubeconfig=data/kubeconfig delete svc hostnames-svc
kubectl --kubeconfig=data/kubeconfig delete epg epg-a epg-b -n kube-system
kubectl --kubeconfig=data/kubeconfig delete contract tcp-6020 -n kube-system
kubectl --kubeconfig=data/kubeconfig get pods 2> /dev/stdout | grep "No resources found"
while [[ $? -ne 0 ]]
do
    sleep 2
    kubectl --kubeconfig=data/kubeconfig get pods 2> /dev/stdout | grep "No resources found"
done
kubectl --kubeconfig=data/kubeconfig get namespaces | grep "prod|dev"
