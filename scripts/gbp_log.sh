#!/bin/bash
pod=$(kubectl --kubeconfig=../data/kubeconfig get pods -n kube-system | grep "aci-containers-controller" | awk '{print $1}')
kubectl --kubeconfig=../data/kubeconfig logs $pod -n kube-system -c aci-gbpserver
